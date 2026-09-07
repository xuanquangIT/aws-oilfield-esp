"""Realtime ingest transformation.

Validates each Kinesis record against the schema v1 telemetry contract
(src/contract.py, shared with the producer and historical seed generator)
before it can affect raw history or the DynamoDB latest-state table.
Rejected records are quarantined with their rule ID and reason, never
silently dropped or promoted. See docs/03-DATA-DOMAIN-AND-CONTRACT.md.

M1 scope only: this still writes DynamoDB unconditionally (last write wins)
and stores numbers as strings. M2 replaces that with a conditional update
keyed on event time, alert cooldown and numeric DynamoDB types.
"""

import base64
import json
import os
import uuid
from datetime import datetime, timezone

import boto3

from contract import validate

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])
bucket = os.environ["DATA_BUCKET"]


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
    s3.put_object(
        Bucket=bucket, Key=key, Body=body.encode(), ContentType="application/json"
    )


def handler(event, context):
    processed, quarantined = 0, 0
    for record in event.get("Records", []):
        received_at = datetime.now(timezone.utc)
        raw_payload = base64.b64decode(record["kinesis"]["data"])

        try:
            parsed = json.loads(raw_payload.decode())
        except (ValueError, UnicodeDecodeError) as exc:
            _quarantine(
                raw_payload, "MALFORMED_PAYLOAD", str(exc), "unknown", received_at
            )
            quarantined += 1
            continue

        result = validate(parsed)
        if not result.accepted:
            esp_hint = (
                parsed.get("esp_id", "unknown")
                if isinstance(parsed, dict)
                else "unknown"
            )
            _quarantine(
                raw_payload, result.rule_id, result.reason, esp_hint, received_at
            )
            quarantined += 1
            continue

        item = result.event
        item["ingested_at"] = received_at.isoformat().replace("+00:00", "Z")
        esp = item["esp_id"]
        dt = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))

        # Preserve the original bytes exactly as received, before normalization.
        key = f"raw/realtime/{esp}/{dt:%Y/%m/%d/%H}/{record['kinesis']['sequenceNumber']}.json"
        s3.put_object(
            Bucket=bucket, Key=key, Body=raw_payload, ContentType="application/json"
        )

        table.put_item(
            Item={
                "esp_id": esp,
                "timestamp": item["timestamp"],
                "event_id": item["event_id"],
                "status": item.get("status", "UNKNOWN"),
                "flow_rate": str(item.get("flow_rate", "")),
                "motor_temperature": str(item.get("motor_temperature", "")),
                "motor_current": str(item.get("motor_current", "")),
                "vibration": str(item.get("vibration", "")),
                "scenario": item.get("scenario", "unknown"),
            }
        )
        processed += 1
    return {"processed": processed, "quarantined": quarantined}
