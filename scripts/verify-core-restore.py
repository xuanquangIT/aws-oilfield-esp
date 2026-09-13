"""Read back an M4 core restore and compare it byte-for-byte to its export."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3


def _sha256_bytes(body) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: body.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _canonical_items(items: list[dict]) -> list[str]:
    return sorted(json.dumps(item, sort_keys=True, separators=(",", ":")) for item in items)


def verify(export_dir: Path, bucket: str, region: str, table_map: dict[str, str]) -> dict:
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "oilfield-esp-core-export-v1":
        raise ValueError("Not an oilfield ESP core export v1")
    s3 = boto3.client("s3", region_name=region)
    dynamodb = boto3.client("dynamodb", region_name=region)
    def verify_object(item: dict) -> None:
        response = s3.get_object(Bucket=bucket, Key=item["key"])
        actual = _sha256_bytes(response["Body"])
        if actual != item["sha256"]:
            raise ValueError(f"S3 checksum mismatch: {item['key']}")
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(verify_object, manifest["objects"]))
    verified_tables = 0
    for table in manifest["tables"]:
        source_table = table["name"]
        target_table = table_map.get(source_table)
        if not target_table:
            raise ValueError(f"No target table mapping supplied for {source_table!r}")
        expected = [json.loads(line) for line in (export_dir / table["path"]).read_text(encoding="utf-8").splitlines() if line]
        actual: list[dict] = []
        for page in dynamodb.get_paginator("scan").paginate(TableName=target_table):
            actual.extend(page.get("Items", []))
        if _canonical_items(actual) != _canonical_items(expected):
            raise ValueError(f"DynamoDB content mismatch: {target_table}")
        verified_tables += 1
    return {"verified_objects": len(manifest["objects"]), "verified_tables": verified_tables, "bucket": bucket}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-dir", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--table-map", action="append", default=[], metavar="EXPORTED=TARGET")
    args = parser.parse_args()
    try:
        table_map = dict(item.split("=", 1) for item in args.table_map)
    except ValueError:
        parser.error("--table-map must be EXPORTED=TARGET")
    print(json.dumps(verify(Path(args.export_dir), args.bucket, args.region, table_map), indent=2))


if __name__ == "__main__":
    main()
