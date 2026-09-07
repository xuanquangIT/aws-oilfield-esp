"""Threshold-based anomaly detection with per-pump/per-rule alert cooldown
and recovery state (M2), backed by a small DynamoDB outbox/dedupe table
(`AlertState`, partition key esp_id, sort key rule_id).

Without cooldown, every anomalous record triggers one SNS publish: a
multi-minute `low_flow` demo with three pumps ticking every second produced
159 emails in one run. Cooldown fixes that by tracking, per (esp_id,
rule_id) pair, whether an "episode" is already active and when it may next
re-alert; a matching recovery notification fires exactly once when the rule
stops triggering.

Ordering for a crash between dedupe persistence and SNS publish: SNS is
published FIRST; the DynamoDB state row is only written after `publish`
returns successfully. So:
  - A crash before publish: nothing was sent; state is unchanged, and the
    next delivery attempt (Kinesis redelivers the same batch on a Lambda
    error) will publish it.
  - A crash after publish but before the state write: the next delivery
    attempt recomputes the exact same deterministic alert_id and may send a
    duplicate. This is a disclosed, deliberate choice -- SNS delivery here
    is at-least-once, never exactly-once -- mitigated by embedding the
    deterministic alert_id in every message so a downstream subscriber can
    dedupe. An alert is never silently dropped; at worst it is sent twice.

Concurrency assumption: the realtime Kinesis stream is provisioned with a
single shard (infrastructure/realtime_stack.py), and Kinesis delivers each
shard's records to at most one Lambda invocation at a time, in order. That
makes the plain (non-conditional) reads/writes below safe for this project's
scope. Scaling this consumer to multiple shards would require making the
AlertState write conditional the same way src/stream_processor/handler.py's
latest-state write is.

This handler does not run records through src/contract.py: it is a parallel,
independent consumer of the same stream as StreamProcessor (see
infrastructure/realtime_stack.py), not the system of record. A record this
handler cannot parse is skipped and counted, not retried indefinitely.
"""

import base64
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3

from contract import iso_z, parse_iso_utc

_ALERT_NAMESPACE = uuid.UUID("7c3a9f1e-2b6d-4b8b-9b0a-0f7f2a6a5b40")

RULES = (
    ("SHUTDOWN", lambda x: x.get("status") == "SHUTDOWN"),
    (
        "LOW_FLOW_OVERHEAT",
        lambda x: float(x.get("flow_rate", 0)) < 60
        and float(x.get("motor_temperature", 0)) > 120,
    ),
    (
        "HIGH_VIBRATION_CURRENT",
        lambda x: float(x.get("vibration", 0)) > 12
        and float(x.get("motor_current", 0)) > 75,
    ),
    (
        "HIGH_TUBING_LOW_FLOW",
        lambda x: float(x.get("tubing_pressure", 0)) > 900
        and float(x.get("flow_rate", 0)) < 60,
    ),
    ("GAS_SLUG_SIMULATION", lambda x: x.get("scenario") == "gas_slug"),
)

RULE_LABELS = {
    "SHUTDOWN": "pump shutdown",
    "LOW_FLOW_OVERHEAT": "low flow + motor overheating",
    "HIGH_VIBRATION_CURRENT": "high vibration + elevated current",
    "HIGH_TUBING_LOW_FLOW": "high tubing pressure + low flow",
    "GAS_SLUG_SIMULATION": "gas-slug simulation",
}

_sns = None
_table = None


def _sns_client():
    global _sns
    if _sns is None:
        _sns = boto3.client("sns")
    return _sns


def _state_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["ALERT_STATE_TABLE"])
    return _table


def _cooldown_seconds() -> int:
    return int(os.environ.get("ALERT_COOLDOWN_SECONDS", "300"))


def triggered_rules(item: dict) -> list:
    return [rule_id for rule_id, test in RULES if test(item)]


def severity_for(rule_ids) -> str:
    if not rule_ids:
        return "normal"
    if "SHUTDOWN" in rule_ids or len(rule_ids) >= 2:
        return "critical"
    return "warning"


def _alert_id(episode_id: str, event_id: str, kind: str) -> str:
    return str(uuid.uuid5(_ALERT_NAMESPACE, f"{episode_id}|{event_id}|{kind}"))


def _add_seconds(iso_ts: str, seconds: int) -> str:
    dt = parse_iso_utc(iso_ts) or datetime.now(timezone.utc)
    return iso_z(dt + timedelta(seconds=seconds))


def decide(
    state: dict | None,
    rule_id: str,
    esp_id: str,
    event_id: str,
    triggered: bool,
    now_iso: str,
    cooldown_seconds: int,
):
    """Pure decision for one (esp_id, rule_id) pair. No I/O, no AWS calls.

    Returns (alert, new_state):
      alert: None (nothing to send), or a dict with kind "trigger"/"recovery"
        plus alert_id/episode_id/esp_id/rule_id.
      new_state: None (no DynamoDB write needed) or the full AlertState item
        to put_item after a successful publish.
    """
    active = bool(state and state.get("active"))

    if triggered:
        if not active:
            episode_id = str(
                uuid.uuid5(_ALERT_NAMESPACE, f"{esp_id}|{rule_id}|{event_id}")
            )
            should_alert = True
        else:
            episode_id = state["episode_id"]
            cooldown_until = state.get("cooldown_until")
            should_alert = cooldown_until is None or now_iso >= cooldown_until
        if not should_alert:
            return None, None
        alert_id = _alert_id(episode_id, event_id, "trigger")
        if state and state.get("last_notified_alert_id") == alert_id:
            return None, None  # exact mechanical retry of an already-notified decision
        new_state = {
            "esp_id": esp_id,
            "rule_id": rule_id,
            "active": True,
            "episode_id": episode_id,
            "cooldown_until": _add_seconds(now_iso, cooldown_seconds),
            "last_notified_alert_id": alert_id,
            "last_event_id": event_id,
            "updated_at": now_iso,
        }
        alert = {
            "kind": "trigger",
            "alert_id": alert_id,
            "episode_id": episode_id,
            "esp_id": esp_id,
            "rule_id": rule_id,
        }
        return alert, new_state

    # Not triggered this record: only interesting if a prior episode is active.
    if not active:
        return None, None
    episode_id = state["episode_id"]
    alert_id = _alert_id(episode_id, event_id, "recovery")
    if state.get("last_notified_alert_id") == alert_id:
        return None, None
    new_state = {
        "esp_id": esp_id,
        "rule_id": rule_id,
        "active": False,
        "episode_id": episode_id,
        "cooldown_until": None,
        "last_notified_alert_id": alert_id,
        "last_event_id": event_id,
        "updated_at": now_iso,
    }
    alert = {
        "kind": "recovery",
        "alert_id": alert_id,
        "episode_id": episode_id,
        "esp_id": esp_id,
        "rule_id": rule_id,
    }
    return alert, new_state


def handler(event, context):
    counts = {"alerts_sent": 0, "suppressed": 0, "skipped": 0}
    table = _state_table()
    topic_arn = os.environ["ALERT_TOPIC_ARN"]
    cooldown_seconds = _cooldown_seconds()

    for record in event.get("Records", []):
        try:
            item = json.loads(base64.b64decode(record["kinesis"]["data"]).decode())
            esp_id = item["esp_id"]
        except Exception:
            # Not this consumer's job to quarantine (StreamProcessor owns
            # that); skip so one bad record cannot block the rest of a batch.
            counts["skipped"] += 1
            continue

        event_id = item.get("event_id", "unknown")
        now_iso = item.get("timestamp") or iso_z(datetime.now(timezone.utc))
        rule_ids = set(triggered_rules(item))

        for rule_id, _test in RULES:
            existing = table.get_item(Key={"esp_id": esp_id, "rule_id": rule_id}).get(
                "Item"
            )
            triggered = rule_id in rule_ids
            alert, new_state = decide(
                existing,
                rule_id,
                esp_id,
                event_id,
                triggered,
                now_iso,
                cooldown_seconds,
            )
            if alert is None:
                if triggered and existing and existing.get("active"):
                    counts["suppressed"] += 1
                continue

            severity = severity_for(rule_ids) if alert["kind"] == "trigger" else "info"
            message = {
                "alert_id": alert["alert_id"],
                "episode_id": alert["episode_id"],
                "kind": alert["kind"],
                "esp_id": esp_id,
                "rule_id": rule_id,
                "finding": RULE_LABELS[rule_id],
                "severity": severity,
                "timestamp": item.get("timestamp"),
                "event_id": event_id,
                "signals": item,
            }
            _sns_client().publish(
                TopicArn=topic_arn,
                Subject=f"ESP {esp_id} {alert['kind'].upper()} {rule_id}",
                Message=json.dumps(message, indent=2, default=str),
            )
            table.put_item(Item=new_state)
            counts["alerts_sent"] += 1

    return counts
