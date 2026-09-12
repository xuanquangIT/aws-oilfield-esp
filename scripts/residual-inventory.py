"""Read-only M4 inventory of billable project residue after a run/reset."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import boto3


def _s3_summary(s3, bucket: str) -> dict:
    count = size = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            count += 1
            size += item["Size"]
    return {"object_count": count, "bytes": size}


def inventory(prefix: str, region: str, bucket: str | None = None) -> dict:
    session = boto3.session.Session(region_name=region)
    cfn = session.client("cloudformation")
    stacks = []
    paginator = cfn.get_paginator("describe_stacks")
    for page in paginator.paginate():
        for stack in page["Stacks"]:
            if stack["StackName"].startswith(prefix) and stack["StackStatus"] != "DELETE_COMPLETE":
                stacks.append({"name": stack["StackName"], "status": stack["StackStatus"]})
    kinesis = session.client("kinesis")
    streams = [
        name for name in kinesis.list_streams().get("StreamNames", []) if name.startswith(prefix)
    ]
    scheduler = session.client("scheduler")
    schedules = [
        {"name": item["Name"], "state": item["State"]}
        for item in scheduler.list_schedules(NamePrefix=prefix).get("Schedules", [])
    ]
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": {"prefix": prefix, "region": region, "bucket": bucket},
        "cloudformation_stacks": stacks,
        "kinesis_streams": streams,
        "scheduler_schedules": schedules,
        "s3": _s3_summary(session.client("s3"), bucket) if bucket else None,
        "note": "This is a scoped resource inventory, not a billing statement. Check Cost Explorer after its normal delay.",
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="oilfield-esp")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--bucket")
    args = parser.parse_args()
    print(json.dumps(inventory(args.prefix, args.region, args.bucket), indent=2))


if __name__ == "__main__":
    main()
