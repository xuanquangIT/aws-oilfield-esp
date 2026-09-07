"""M2 exit gate for src/anomaly_detector/handler.py: per-pump/rule alert
cooldown and recovery. Directly regression-tests the incident this milestone
fixes: a sustained anomaly used to send one SNS email per record (159 emails
in one multi-minute `low_flow` demo); it must now send exactly one trigger
alert per episode, plus one recovery alert when the condition clears.
"""

import base64
import json

import pytest

import anomaly_detector.handler as ad


class FakeSns:
    def __init__(self):
        self.messages = []

    def publish(self, TopicArn, Subject, Message):
        self.messages.append(json.loads(Message))


class FakeAlertTable:
    def __init__(self):
        self.items = {}

    def get_item(self, Key):
        item = self.items.get((Key["esp_id"], Key["rule_id"]))
        return {"Item": item} if item else {}

    def put_item(self, Item):
        self.items[(Item["esp_id"], Item["rule_id"])] = Item


@pytest.fixture(autouse=True)
def fake_clients(monkeypatch):
    monkeypatch.setenv("ALERT_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:topic")
    monkeypatch.setenv("ALERT_STATE_TABLE", "test-alert-table")
    sns = FakeSns()
    table = FakeAlertTable()
    monkeypatch.setattr(ad, "_sns_client", lambda: sns)
    monkeypatch.setattr(ad, "_state_table", lambda: table)
    return sns, table


def _record(item: dict) -> dict:
    return {"kinesis": {"data": base64.b64encode(json.dumps(item).encode())}}


LOW_FLOW_BASE = {
    "esp_id": "ESP-101",
    "status": "RUNNING",
    "scenario": "low_flow",
    "flow_rate": 42.0,
    "motor_temperature": 137.0,
    "motor_current": 82.0,
    "vibration": 2.5,
    "tubing_pressure": 700.0,
}


def test_sustained_anomaly_sends_one_alert_not_one_per_record(fake_clients):
    sns, table = fake_clients
    records = [
        _record(
            dict(
                LOW_FLOW_BASE,
                event_id=f"evt-{i}",
                timestamp=f"2026-01-01T00:00:{i:02d}.000000Z",
            )
        )
        for i in range(50)
    ]
    result = ad.handler({"Records": records}, None)
    assert result["alerts_sent"] == 1
    assert len(sns.messages) == 1
    assert sns.messages[0]["kind"] == "trigger"
    assert sns.messages[0]["rule_id"] == "LOW_FLOW_OVERHEAT"
    assert result["suppressed"] == 49


def test_recovery_alert_fires_once_when_condition_clears(fake_clients):
    sns, table = fake_clients
    trigger = _record(
        dict(LOW_FLOW_BASE, event_id="evt-1", timestamp="2026-01-01T00:00:00.000000Z")
    )
    normal = _record(
        dict(
            LOW_FLOW_BASE,
            flow_rate=120.0,
            motor_temperature=92.0,
            event_id="evt-2",
            timestamp="2026-01-01T00:01:00.000000Z",
        )
    )
    result = ad.handler({"Records": [trigger, normal]}, None)
    assert result["alerts_sent"] == 2
    kinds = [m["kind"] for m in sns.messages]
    assert kinds == ["trigger", "recovery"]
    # Same episode_id ties the trigger and its recovery together.
    assert sns.messages[0]["episode_id"] == sns.messages[1]["episode_id"]


def test_re_trigger_after_cooldown_expires_sends_a_new_alert():
    state = None
    alert1, state1 = ad.decide(
        state,
        "LOW_FLOW_OVERHEAT",
        "ESP-101",
        "evt-1",
        True,
        "2026-01-01T00:00:00.000000Z",
        300,
    )
    assert alert1["kind"] == "trigger"
    # Still within cooldown: suppressed.
    alert2, state2 = ad.decide(
        state1,
        "LOW_FLOW_OVERHEAT",
        "ESP-101",
        "evt-2",
        True,
        "2026-01-01T00:01:00.000000Z",
        300,
    )
    assert alert2 is None and state2 is None
    # Cooldown has elapsed: re-alerts, same episode.
    alert3, state3 = ad.decide(
        state1,
        "LOW_FLOW_OVERHEAT",
        "ESP-101",
        "evt-3",
        True,
        "2026-01-01T00:10:00.000000Z",
        300,
    )
    assert alert3["kind"] == "trigger"
    assert alert3["episode_id"] == alert1["episode_id"]


def test_identical_retry_of_same_decision_is_not_re_sent():
    """A mechanical Lambda/Kinesis retry of the exact same record must not
    re-publish, even before any cooldown-based suppression applies."""
    alert, state = ad.decide(
        None, "SHUTDOWN", "ESP-101", "evt-1", True, "2026-01-01T00:00:00.000000Z", 300
    )
    assert alert is not None
    # Re-run the identical decision against the state that resulted from it.
    alert_retry, state_retry = ad.decide(
        state, "SHUTDOWN", "ESP-101", "evt-1", True, "2026-01-01T00:00:00.000000Z", 300
    )
    assert alert_retry is None and state_retry is None


def test_no_active_episode_and_not_triggered_is_a_no_op():
    alert, state = ad.decide(
        None,
        "LOW_FLOW_OVERHEAT",
        "ESP-101",
        "evt-1",
        False,
        "2026-01-01T00:00:00.000000Z",
        300,
    )
    assert alert is None and state is None


def test_malformed_record_is_skipped_not_fatal(fake_clients):
    sns, table = fake_clients
    bad = {"kinesis": {"data": base64.b64encode(b"not json {")}}
    result = ad.handler({"Records": [bad]}, None)
    assert result["skipped"] == 1
    assert result["alerts_sent"] == 0
