"""Create a portable, checksum-bound export before a destructive core reset.

Exports every S3 object and the two DynamoDB tables as raw DynamoDB AttributeValue
maps.  It performs no AWS writes.  Its paired restore command requires an
explicit confirmation and verifies the local hashes before it writes anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath

import boto3


def _safe_destination(root: Path, key: str) -> Path:
    parsed = PurePosixPath(key)
    # S3 object keys use POSIX separators.  Reject all forms that Windows
    # could reinterpret as a path escape before constructing a local path.
    if parsed.is_absolute() or "\\" in key or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ValueError(f"Unsafe S3 key for local export: {key!r}")
    return root / "s3" / Path(*parsed.parts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export(bucket: str, tables: list[str], destination: Path, region: str) -> dict:
    destination.mkdir(parents=True, exist_ok=False)
    # Create the root before resolving child paths.  On Windows a missing
    # intermediate directory can make ``Path.resolve`` reject a safe key.
    (destination / "s3").mkdir()
    s3 = boto3.client("s3", region_name=region)
    dynamodb = boto3.client("dynamodb", region_name=region)
    source_objects = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        source_objects.extend(page.get("Contents", []))

    def export_object(item: dict) -> dict:
        key = item["Key"]
        target = _safe_destination(destination, key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as fh:
            body = s3.get_object(Bucket=bucket, Key=key)["Body"]
            for chunk in iter(lambda: body.read(1024 * 1024), b""):
                fh.write(chunk)
        return {"key": key, "size": target.stat().st_size, "sha256": _sha256(target)}

    # Each S3 key has an independent local destination.  Bounded parallelism
    # keeps destructive-recovery export practical without weakening hashes.
    with ThreadPoolExecutor(max_workers=16) as pool:
        objects = list(pool.map(export_object, source_objects))
    exported_tables = []
    for table in tables:
        target = destination / "dynamodb" / f"{table}.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        paginator = dynamodb.get_paginator("scan")
        with target.open("w", encoding="utf-8") as fh:
            for page in paginator.paginate(TableName=table):
                for item in page.get("Items", []):
                    fh.write(json.dumps(item, sort_keys=True) + "\n")
                    count += 1
        exported_tables.append(
            {"name": table, "items": count, "path": str(target.relative_to(destination)), "sha256": _sha256(target)}
        )
    manifest = {
        "format": "oilfield-esp-core-export-v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "bucket": bucket,
        "region": region,
        "objects": objects,
        "tables": exported_tables,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--table", action="append", required=True, help="Repeat for each DynamoDB table")
    parser.add_argument("--destination", required=True)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    report = export(args.bucket, args.table, Path(args.destination), args.region)
    print(json.dumps({"objects": len(report["objects"]), "tables": report["tables"]}, indent=2))


if __name__ == "__main__":
    main()
