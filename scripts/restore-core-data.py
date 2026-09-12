"""Restore a verified local export.  Requires --confirm-restore for writes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import boto3


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_verified(export_dir: Path) -> dict:
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "oilfield-esp-core-export-v1":
        raise ValueError("Not an oilfield ESP core export v1")
    for item in manifest["objects"]:
        local = export_dir / "s3" / item["key"]
        if _sha256(local) != item["sha256"]:
            raise ValueError(f"Checksum mismatch: {item['key']}")
    for item in manifest["tables"]:
        local = export_dir / item["path"]
        if _sha256(local) != item["sha256"]:
            raise ValueError(f"Checksum mismatch: {item['path']}")
    return manifest


def restore(export_dir: Path, bucket: str, region: str, table_map: dict[str, str]) -> dict:
    manifest = _load_verified(export_dir)
    s3 = boto3.client("s3", region_name=region)
    dynamodb = boto3.client("dynamodb", region_name=region)
    for item in manifest["objects"]:
        s3.put_object(Bucket=bucket, Key=item["key"], Body=(export_dir / "s3" / item["key"]).read_bytes())
    restored_items = 0
    for table in manifest["tables"]:
        source_table = table["name"]
        target_table = table_map.get(source_table)
        if not target_table:
            raise ValueError(
                f"No target table mapping supplied for exported table {source_table!r}"
            )
        with (export_dir / table["path"]).open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    dynamodb.put_item(TableName=target_table, Item=json.loads(line))
                    restored_items += 1
    return {"objects": len(manifest["objects"]), "items": restored_items, "bucket": bucket}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-dir", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument(
        "--table-map",
        action="append",
        default=[],
        metavar="EXPORTED=TARGET",
        help="Repeat once for every exported table; physical table names change after reset.",
    )
    parser.add_argument("--confirm-restore", action="store_true")
    args = parser.parse_args()
    if not args.confirm_restore:
        parser.error("restore writes S3/DynamoDB; re-run with --confirm-restore")
    try:
        table_map = dict(item.split("=", 1) for item in args.table_map)
    except ValueError:
        parser.error("--table-map must be EXPORTED=TARGET")
    print(
        json.dumps(
            restore(Path(args.export_dir), args.bucket, args.region, table_map), indent=2
        )
    )


if __name__ == "__main__":
    main()
