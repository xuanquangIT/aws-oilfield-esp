"""Realtime ingest transformation.

Validates each Kinesis record against the schema v1 telemetry contract
(src/contract.py, shared with the producer and historical seed generator)
before it can affect raw history or the DynamoDB latest-state table.
Rejected records are quarantined with their rule ID and reason, never
silently dropped or promoted. See docs/03-DATA-DOMAIN-AND-CONTRACT.md.

M2: the latest-state write is conditional on event_id/timestamp so a
late-arriving or duplicate-delivered record can never regress or duplicate
DynamoDB state, and measurements are stored as DynamoDB Number types
(Decimal), not strings. The raw history object key is the event_id (stable
replay identity per docs/06-DELIVERY-AND-LEARNING.md M2), not the Kinesis
sequence number (transport metadata only), so replaying or redelivering the
same event is an idempotent overwrite rather than a duplicate object.

A record that loses the conditional check is "superseded", not an error:
its raw copy is still preserved (written before the conditional check) and
it is counted explicitly under its own outcome, so no event can disappear
without accepted/quarantined/superseded accounting (M2 exit gate).

Equal-time conflict rule: two records for the same esp_id with the exact
same timestamp are resolved first-writer-wins (the second is superseded).
This deliberately simple rule covers the common case of a Kinesis
at-least-once redelivery of an unchanged event; it does not attempt a total
order across distinct event_ids that happen to share a timestamp.
"""

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from contract import validate

# Fields stored as DynamoDB Number types in the latest-state item. Optional
# fields (pressures, frequency) are not part of the operational "latest
# state" view and stay out of DynamoDB; they remain available in raw/.
NUMERIC_STATE_FIELDS = ("flow_rate", "motor_temperature", "motor_current", "vibration")

_s3 = None
_table = None


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _state_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])
    return _table


def _bucket() -> str:
    return os.environ["DATA_BUCKET"]


def _quarantine(
    raw_payload: bytes, rule_id: str, reason: str, esp_hint: str, received_at: datetime
) -> None:
    key = (
        f"quarantine/realtime/{rule_id}/{esp_hint}/"
        f"{received_at:%Y/%m/%d/%H}/{uuid.uuid4()}.json"
    )
    body = json.dumps(
        {
            "rule_id": rule_id,
            "reason": reason,
            "received_at": received_at.isoformat().replace("+00:00", "Z"),
            "raw_base64": base64.b64encode(raw_payload).decode(),
        }
    )
    _s3_client().put_object(
        Bucket=_bucket(), Key=key, Body=body.encode(), ContentType="application/json"
    )


def _to_state_item(item: dict) -> dict:
    state = {
        "esp_id": item["esp_id"],
        "timestamp": item["timestamp"],
        "event_id": item["event_id"],
        "status": item.get("status", "UNKNOWN"),
        "scenario": item.get("scenario", "unknown"),
        "ingested_at": item["ingested_at"],
    }
    for name in NUMERIC_STATE_FIELDS:
        value = item.get(name)
        if value is not None:
            state[name] = Decimal(str(value))
    return state


def _write_latest_state(item: dict) -> bool:
    """Conditionally accept `item` as the new latest state for its esp_id.

    Returns True if written, False if superseded by an existing item whose
    timestamp is already greater than or equal to this one (a late arrival
    or an exact-timestamp duplicate/retry).
    """
    state_item = _to_state_item(item)
    try:
        _state_table().put_item(
            Item=state_item,
            ConditionExpression="attribute_not_exists(esp_id) OR #ts < :new_ts",
            ExpressionAttributeNames={"#ts": "timestamp"},
            ExpressionAttributeValues={":new_ts": item["timestamp"]},
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def process_record(raw_payload: bytes, received_at: datetime) -> dict:
    """Validate and apply one raw Kinesis record; return an outcome dict.

    Used directly by `handler` for live records, and reused as-is by
    `scripts/replay-failed.py` in `--execute` mode so a replay has exactly
    the same accept/quarantine/supersede semantics as live ingestion.
    """
    try:
        parsed = json.loads(raw_payload.decode())
    except (ValueError, UnicodeDecodeError) as exc:
        _quarantine(raw_payload, "MALFORMED_PAYLOAD", str(exc), "unknown", received_at)
        return {"outcome": "quarantined", "rule_id": "MALFORMED_PAYLOAD"}

    result = validate(parsed)
    if not result.accepted:
        esp_hint = (
            parsed.get("esp_id", "unknown") if isinstance(parsed, dict) else "unknown"
        )
        _quarantine(raw_payload, result.rule_id, result.reason, esp_hint, received_at)
        return {"outcome": "quarantined", "rule_id": result.rule_id}

    item = dict(result.event)
    item["ingested_at"] = received_at.isoformat().replace("+00:00", "Z")
    esp = item["esp_id"]
    event_id = item["event_id"]
    dt = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))

    # Preserve the original bytes exactly as received, before normalization.
    # Keyed by event_id (stable replay identity), not the Kinesis sequence
    # number, so replaying or redelivering the same event is idempotent.
    key = f"raw/realtime/{esp}/{dt:%Y/%m/%d/%H}/{event_id}.json"
    _s3_client().put_object(
        Bucket=_bucket(), Key=key, Body=raw_payload, ContentType="application/json"
    )

    accepted = _write_latest_state(item)
    return {
        "outcome": "processed" if accepted else "superseded",
        "esp_id": esp,
        "event_id": event_id,
        "timestamp": item["timestamp"],
    }


def handler(event, context):
    counts = {"processed": 0, "quarantined": 0, "superseded": 0}
    for record in event.get("Records", []):
        received_at = datetime.now(timezone.utc)
        raw_payload = base64.b64decode(record["kinesis"]["data"])
        outcome = process_record(raw_payload, received_at)
        counts[outcome["outcome"]] += 1
    return counts
