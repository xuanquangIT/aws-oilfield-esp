"""Create and upload a checksum-bound M3 input manifest.

The manifest is deliberately created before the Glue run.  It freezes the
exact raw S3 objects selected for the run, including their content hashes, so
an M3 rerun is reproducible even if later telemetry arrives.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from batch.canonical import (  # noqa: E402
    build_manifest,
    manifest_sha256,
    selected_start_date,
    sha256_bytes,
)


def _date_from_realtime_key(key: str) -> str | None:
    """Extract YYYY-MM-DD from the M2 raw/realtime event-time key."""
    parts = key.split("/")
    # raw/realtime/<esp_id>/YYYY/MM/DD/HH/<event_id>.json
    if len(parts) < 8 or parts[:2] != ["raw", "realtime"]:
        return None
    try:
        return date(int(parts[3]), int(parts[4]), int(parts[5])).isoformat()
    except ValueError:
        return None


def _listed_objects(s3, bucket: str, prefix: str):
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        yield from page.get("Contents", [])


def _checksum_object(s3, bucket: str, item: dict, source_kind: str) -> dict:
    key = item["Key"]
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return {
        "uri": f"s3://{bucket}/{key}",
        "source_kind": source_kind,
        "sha256": sha256_bytes(body),
        "size_bytes": len(body),
        "last_modified_utc": item["LastModified"].isoformat().replace("+00:00", "Z"),
    }


def select_objects(s3, bucket: str, start_date: str, end_date: str, lookback_days: int):
    """Return selected batch files plus event-date-selected realtime files."""
    lower = selected_start_date(start_date, lookback_days)
    selected = []
    for item in _listed_objects(s3, bucket, "raw/batch/"):
        selected.append(_checksum_object(s3, bucket, item, "historical_csv"))
    for item in _listed_objects(s3, bucket, "raw/realtime/"):
        event_date = _date_from_realtime_key(item["Key"])
        if event_date is not None and lower <= event_date <= end_date:
            selected.append(_checksum_object(s3, bucket, item, "realtime_json"))
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--manifest-id", required=True)
    parser.add_argument("--start-date", required=True, help="UTC YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="UTC YYYY-MM-DD")
    parser.add_argument("--late-arrival-lookback-days", type=int, default=1)
    parser.add_argument("--out", default=None, help="Optional local copy of the JSON manifest")
    args = parser.parse_args()

    # Validate dates early and consistently with the manifest helper.
    date.fromisoformat(args.start_date)
    date.fromisoformat(args.end_date)
    s3 = boto3.client("s3")
    manifest = build_manifest(
        manifest_id=args.manifest_id,
        start_date=args.start_date,
        end_date=args.end_date,
        late_arrival_lookback_days=args.late_arrival_lookback_days,
        objects=select_objects(
            s3,
            args.bucket,
            args.start_date,
            args.end_date,
            args.late_arrival_lookback_days,
        ),
    )
    body = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    key = f"manifests/{args.manifest_id}/input-manifest.json"
    s3.put_object(
        Bucket=args.bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        Metadata={"sha256": manifest_sha256(manifest)},
    )
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(body)
    print(json.dumps({"manifest_key": key, "manifest_sha256": manifest_sha256(manifest)}))


if __name__ == "__main__":
    main()
