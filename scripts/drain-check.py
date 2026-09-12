"""M4 drain gate: prove every acknowledged event was actually archived.

Compares the producer's own ledger of acknowledged sends for one run
(``data/producer-runs/<run_id>.jsonl``, written by ``simulator/esp_simulator.py``)
against what the realtime consumers actually recorded in S3: either
``raw/realtime/...`` (accepted, or accepted-then-superseded -- both keep a raw
copy per the M2 design) or ``quarantine/realtime/...`` (rejected, but never
silently dropped).

This is deliberately a client-side, timeout-bounded check: it polls, because
Kinesis consumers lag slightly behind the producer, but it must never report
"clean" just because it got tired of waiting. A non-empty missing set after
the timeout means the run is INCOMPLETE, printed and saved as a receipt, and
the process exits non-zero so a calling script's normal teardown can decide
what to do (do not silently mark an incomplete run successful).

Usage:
    python scripts/drain-check.py --bucket <bucket> --run-id <run_id>
        [--timeout-seconds 90] [--poll-interval-seconds 10]
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

QUARANTINE_SCAN_MARGIN = timedelta(minutes=5)


def _load_ledger(run_id: str) -> list[dict]:
    path = Path(f"data/producer-runs/{run_id}.jsonl")
    if not path.exists():
        raise SystemExit(
            f"No producer ledger at {path}. The drain gate needs the "
            "acknowledged-event file esp_simulator.py writes for this run; "
            "it cannot reconcile a run it has no local record of."
        )
    events = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _raw_key(event: dict) -> str:
    ts = datetime.strptime(event["timestamp"][:19], "%Y-%m-%dT%H:%M:%S")
    return f"raw/realtime/{event['esp_id']}/{ts:%Y/%m/%d/%H}/{event['event_id']}.json"


def _raw_exists(s3, bucket: str, event: dict) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=_raw_key(event))
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        # A denied or unavailable bucket is not evidence that a record is
        # missing. Fail closed with its real diagnostic instead of printing a
        # misleading incomplete receipt.
        raise


def _quarantined_event_ids(s3, bucket: str, since: datetime) -> set[str]:
    """Best-effort scan: decode each quarantine object's raw payload and
    collect whatever event_id it carries, if any. A payload that is not
    even valid JSON (e.g. MALFORMED_PAYLOAD) has no event_id to recover;
    that record's own presence in quarantine is still real accounting, it
    is just not attributable back to one producer-side event_id here."""
    ids: set[str] = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="quarantine/realtime/"):
        for item in page.get("Contents", []):
            if item["LastModified"] < since:
                continue
            body = s3.get_object(Bucket=bucket, Key=item["Key"])["Body"].read()
            try:
                envelope = json.loads(body)
                raw = json.loads(base64.b64decode(envelope["raw_base64"]))
                event_id = raw.get("event_id")
            except (ValueError, KeyError, TypeError):
                event_id = None
            if event_id:
                ids.add(event_id)
    return ids


def drain_check(
    bucket: str,
    run_id: str,
    timeout_seconds: int = 90,
    poll_interval_seconds: int = 10,
) -> dict:
    s3 = boto3.client("s3")
    ledger = _load_ledger(run_id)
    by_id = {e["event_id"]: e for e in ledger}
    since = (
        min(
            (
                datetime.strptime(e["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
                for e in ledger
            ),
            default=datetime.now(timezone.utc),
        )
        - QUARANTINE_SCAN_MARGIN
    )

    missing = set(by_id)
    deadline = time.monotonic() + timeout_seconds
    accounted_raw: set[str] = set()
    accounted_quarantine: set[str] = set()
    while True:
        still_missing = set()
        for event_id in missing:
            if _raw_exists(s3, bucket, by_id[event_id]):
                accounted_raw.add(event_id)
            else:
                still_missing.add(event_id)
        if still_missing:
            quarantined = _quarantined_event_ids(s3, bucket, since)
            for event_id in list(still_missing):
                if event_id in quarantined:
                    accounted_quarantine.add(event_id)
                    still_missing.discard(event_id)
        missing = still_missing
        if not missing or time.monotonic() >= deadline:
            break
        time.sleep(poll_interval_seconds)

    report = {
        "run_id": run_id,
        "bucket": bucket,
        "acknowledged": len(by_id),
        "accounted_raw": len(accounted_raw),
        "accounted_quarantine": len(accounted_quarantine),
        "missing": sorted(missing),
        "complete": not missing,
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--timeout-seconds", type=int, default=90)
    p.add_argument("--poll-interval-seconds", type=int, default=10)
    args = p.parse_args()
    if args.timeout_seconds < 0 or args.poll_interval_seconds < 0:
        p.error("timeout and poll interval must be non-negative")

    report = drain_check(
        args.bucket, args.run_id, args.timeout_seconds, args.poll_interval_seconds
    )

    receipts_dir = Path("data/drain-receipts")
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts_dir / f"{args.run_id}.json"
    receipt_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2))
    if report["complete"]:
        print(
            f"Drain check PASSED: all {report['acknowledged']} acknowledged events accounted for."
        )
    else:
        print(
            f"Drain check INCOMPLETE: {len(report['missing'])} of "
            f"{report['acknowledged']} acknowledged events are not yet in "
            f"raw/ or quarantine/. This run is NOT confirmed fully drained; "
            f"see {receipt_path}. Do not delete the stream based on this "
            f"result alone -- investigate or wait, then rerun this check."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
