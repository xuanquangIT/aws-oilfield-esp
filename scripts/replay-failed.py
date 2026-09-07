"""Replay tool for a Kinesis on-failure S3 destination payload (M2).

When the realtime EventSourceMapping (infrastructure/realtime_stack.py)
exhausts its retries for a batch, it writes a small JSON pointer object to
S3 -- not the actual records -- describing which stream/shard/sequence
range failed (the "KinesisBatchInfo" shape documented at
https://docs.aws.amazon.com/lambda/latest/dg/kinesis-on-failure-destination.html).
This tool:

1. Downloads and parses that pointer object.
2. Re-fetches the actual failed records from Kinesis by sequence number.
   This only works while the stream still exists and the records are still
   within its 24-hour retention window (infrastructure/realtime_stack.py);
   the disposable realtime stack does not outlive a demo session, so replay
   only makes sense while it is still deployed.
3. Runs each record through the exact same validate-and-apply logic as the
   live StreamProcessor Lambda (src/stream_processor/handler.process_record),
   so a replay has identical accept/quarantine/supersede semantics -- not a
   reimplementation that could drift from production behavior.
4. Writes a replay receipt (JSON) recording what was replayed and the
   outcome counts.

Dry-run by default: classifies each record (what WOULD happen) with no S3 or
DynamoDB side effects, and needs no AWS credentials beyond reading the
failure object and the Kinesis records. Pass --execute to actually apply
records via process_record; that additionally requires DATA_BUCKET and
STATE_TABLE in the environment (the same variables the live Lambda uses),
e.g.:

    $env:DATA_BUCKET = (Get-CoreOutput 'DataBucketName')
    $env:STATE_TABLE = (Get-CoreOutput 'StateTableName')
    python scripts/replay-failed.py --bucket <bucket> --key <failure-key> --execute
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from contract import validate  # noqa: E402
from stream_processor.handler import process_record  # noqa: E402


def _load_failure_payload(s3_client, bucket: str, key: str) -> dict:
    body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(body)


def _stream_name_from_arn(arn: str) -> str:
    # arn:aws:kinesis:<region>:<account>:stream/<name>
    return arn.split("/", 1)[1]


def _fetch_failed_records(kinesis_client, payload: dict) -> list:
    info = payload["KinesisBatchInfo"]
    stream_name = _stream_name_from_arn(info["streamArn"])
    shard_iterator = kinesis_client.get_shard_iterator(
        StreamName=stream_name,
        ShardId=info["shardId"],
        ShardIteratorType="AT_SEQUENCE_NUMBER",
        StartingSequenceNumber=info["startSequenceNumber"],
    )["ShardIterator"]
    response = kinesis_client.get_records(
        ShardIterator=shard_iterator, Limit=info["batchSize"]
    )
    return response["Records"]


def _classify_only(raw_payload: bytes) -> dict:
    """Dry-run outcome: validate only, no S3/DynamoDB side effects."""
    try:
        parsed = json.loads(raw_payload.decode())
    except (ValueError, UnicodeDecodeError) as exc:
        return {
            "outcome": "would_quarantine",
            "rule_id": "MALFORMED_PAYLOAD",
            "reason": str(exc),
        }
    result = validate(parsed)
    if not result.accepted:
        return {
            "outcome": "would_quarantine",
            "rule_id": result.rule_id,
            "reason": result.reason,
        }
    return {
        "outcome": "would_process",
        "esp_id": result.event["esp_id"],
        "event_id": result.event["event_id"],
    }


def _tally(outcomes: list) -> dict:
    counts: dict = {}
    for o in outcomes:
        counts[o["outcome"]] = counts.get(o["outcome"], 0) + 1
    return counts


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--bucket", required=True, help="Bucket holding the failure-destination object"
    )
    p.add_argument(
        "--key", required=True, help="Key of the failure-destination JSON object"
    )
    p.add_argument(
        "--execute",
        action="store_true",
        help="Apply outcomes for real via process_record; default is dry-run (classify only)",
    )
    p.add_argument(
        "--receipt-dir",
        default="data/replay-receipts",
        help="Local directory to write the replay receipt JSON",
    )
    args = p.parse_args()

    s3 = boto3.client("s3")
    kinesis = boto3.client("kinesis")

    payload = _load_failure_payload(s3, args.bucket, args.key)
    records = _fetch_failed_records(kinesis, payload)

    outcomes = []
    for record in records:
        raw_payload = record["Data"]  # boto3 already base64-decodes this to bytes
        if args.execute:
            outcome = process_record(raw_payload, datetime.now(timezone.utc))
        else:
            outcome = _classify_only(raw_payload)
        outcomes.append({"sequence_number": record["SequenceNumber"], **outcome})

    replayed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    receipt = {
        "source_bucket": args.bucket,
        "source_key": args.key,
        "dry_run": not args.execute,
        "replayed_at": replayed_at,
        "record_count": len(records),
        "counts": _tally(outcomes),
        "outcomes": outcomes,
    }

    receipt_dir = Path(args.receipt_dir)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"replay-{replayed_at.replace(':', '')}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))

    print(json.dumps(receipt, indent=2))
    print(f"Replay receipt written to {receipt_path}")


if __name__ == "__main__":
    main()
