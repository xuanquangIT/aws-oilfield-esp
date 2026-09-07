"""M2 exit gate for src/stream_processor/handler.py: latest state is
monotonic, no event disappears without accepted/quarantined/superseded
accounting, raw history is keyed by the stable event_id, and measurements
are stored as DynamoDB Number types, not strings.

Uses small hand-rolled fakes for S3/DynamoDB (no `moto` dependency): the
fake state table implements exactly the one ConditionExpression shape the
handler emits, which is enough to prove the accept/late/duplicate decision
logic end-to-end offline. The real ConditionExpression was also verified
against live DynamoDB as part of the M1 AWS smoke test pattern; see
docs/09-RUNBOOK.md.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

import stream_processor.handler as sp

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "telemetry_v1.json").read_text()
)


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.objects[Key] = Body


class FakeStateTable:
    """Implements only the single ConditionExpression shape used by
    stream_processor.handler._write_latest_state: allow the write if the
    item does not exist yet, or the currently stored timestamp is strictly
    less than the new one.
    """

    def __init__(self):
        self.items = {}

    def put_item(
        self,
        Item,
        ConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
    ):
        pk = Item["esp_id"]
        if ConditionExpression:
            existing = self.items.get(pk)
            new_ts = ExpressionAttributeValues[":new_ts"]
            allowed = existing is None or existing["timestamp"] < new_ts
            if not allowed:
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ConditionalCheckFailedException",
                            "Message": "test",
                        }
                    },
                    "PutItem",
                )
        self.items[pk] = Item


@pytest.fixture(autouse=True)
def fake_clients(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    monkeypatch.setenv("STATE_TABLE", "test-table")
    s3 = FakeS3()
    table = FakeStateTable()
    monkeypatch.setattr(sp, "_s3_client", lambda: s3)
    monkeypatch.setattr(sp, "_state_table", lambda: table)
    return s3, table


def _payload(event: dict) -> bytes:
    return (json.dumps(event) + "\n").encode()


def test_valid_event_is_processed_and_stored_with_numeric_types(fake_clients):
    s3, table = fake_clients
    event = FIXTURES["valid"][0]["event"]
    outcome = sp.process_record(_payload(event), datetime.now(timezone.utc))
    assert outcome["outcome"] == "processed"
    stored = table.items[event["esp_id"]]
    assert isinstance(stored["flow_rate"], Decimal)
    assert isinstance(stored["vibration"], Decimal)
    assert any(k.endswith(f"{event['event_id']}.json") for k in s3.objects)


def test_invalid_event_is_quarantined_never_reaches_state_or_raw(fake_clients):
    s3, table = fake_clients
    event = FIXTURES["invalid_malformed"][1]["event"]  # OUT_OF_RANGE water_cut
    outcome = sp.process_record(_payload(event), datetime.now(timezone.utc))
    assert outcome["outcome"] == "quarantined"
    assert outcome["rule_id"] == "OUT_OF_RANGE"
    assert event["esp_id"] not in table.items
    assert not any(k.startswith("raw/realtime") for k in s3.objects)
    assert any(k.startswith("quarantine/realtime/OUT_OF_RANGE/") for k in s3.objects)


def test_malformed_json_is_quarantined_as_unknown_esp(fake_clients):
    s3, table = fake_clients
    outcome = sp.process_record(b"not json {", datetime.now(timezone.utc))
    assert outcome["outcome"] == "quarantined"
    assert outcome["rule_id"] == "MALFORMED_PAYLOAD"
    assert any(
        k.startswith("quarantine/realtime/MALFORMED_PAYLOAD/unknown/")
        for k in s3.objects
    )
    assert not table.items


def test_duplicate_event_id_is_superseded_not_double_counted(fake_clients):
    s3, table = fake_clients
    case = FIXTURES["duplicate"][0]
    first = sp.process_record(_payload(case["event_a"]), datetime.now(timezone.utc))
    second = sp.process_record(_payload(case["event_b"]), datetime.now(timezone.utc))
    assert first["outcome"] == "processed"
    assert second["outcome"] == "superseded"
    esp = case["event_a"]["esp_id"]
    # Same event_id -> same raw key -> idempotent overwrite, not two objects.
    raw_keys = [k for k in s3.objects if k.startswith(f"raw/realtime/{esp}/")]
    assert len(raw_keys) == 1


def test_late_event_stays_in_raw_history_but_does_not_regress_state(fake_clients):
    s3, table = fake_clients
    case = FIXTURES["late"][0]
    prior, late = case["prior_event"], case["late_event"]
    r1 = sp.process_record(_payload(prior), datetime.now(timezone.utc))
    r2 = sp.process_record(_payload(late), datetime.now(timezone.utc))
    assert r1["outcome"] == "processed"
    assert r2["outcome"] == "superseded"
    assert table.items[prior["esp_id"]]["timestamp"] == prior["timestamp"]
    esp = prior["esp_id"]
    raw_keys = {k for k in s3.objects if k.startswith(f"raw/realtime/{esp}/")}
    assert len(raw_keys) == 2  # both events preserved in raw history


def test_no_event_disappears_without_accounting(fake_clients):
    """Every fixture record maps to exactly one outcome bucket."""
    events = [c["event"] for c in FIXTURES["valid"]]
    events += [c["event"] for c in FIXTURES["invalid_null"]]
    events += [c["event"] for c in FIXTURES["invalid_malformed"]]
    events += [c["event"] for c in FIXTURES["incompatible_version"]]
    counts = {"processed": 0, "quarantined": 0, "superseded": 0}
    for event in events:
        outcome = sp.process_record(_payload(event), datetime.now(timezone.utc))
        counts[outcome["outcome"]] += 1
    assert sum(counts.values()) == len(events)
