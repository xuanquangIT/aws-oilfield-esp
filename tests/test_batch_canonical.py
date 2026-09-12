"""Offline M3 contract tests; no Spark, Glue, S3 or AWS credential required."""

import json
from pathlib import Path

from batch.canonical import (
    build_manifest,
    classify_events,
    manifest_sha256,
    selected_start_date,
)


FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "telemetry_v1.json").read_text()
)


def test_manifest_is_byte_stable_when_input_listing_order_changes():
    objects = [
        {
            "uri": "s3://bucket/raw/realtime/ESP-101/2026/01/01/00/event.json",
            "source_kind": "realtime_json",
            "sha256": "b" * 64,
            "size_bytes": 100,
            "last_modified_utc": "2026-01-01T00:01:00Z",
        },
        {
            "uri": "s3://bucket/raw/batch/historical.csv",
            "source_kind": "historical_csv",
            "sha256": "a" * 64,
            "size_bytes": 200,
        },
    ]
    first = build_manifest(
        manifest_id="fixture-manifest",
        start_date="2026-01-01",
        end_date="2026-01-02",
        late_arrival_lookback_days=1,
        objects=objects,
    )
    second = build_manifest(
        manifest_id="fixture-manifest",
        start_date="2026-01-01",
        end_date="2026-01-02",
        late_arrival_lookback_days=1,
        objects=reversed(objects),
    )
    assert first == second
    assert manifest_sha256(first) == manifest_sha256(second)
    assert selected_start_date("2026-01-01", 1) == "2025-12-31"


def test_identical_redelivery_is_deduplicated_by_event_id_deterministically():
    event = FIXTURES["valid"][0]["event"]
    accepted, rejected, duplicate_count = classify_events(
        [
            ("s3://bucket/raw/realtime/z.json", event),
            ("s3://bucket/raw/realtime/a.json", dict(event)),
        ]
    )
    assert rejected == []
    assert duplicate_count == 1
    assert accepted == [("s3://bucket/raw/realtime/a.json", event)]


def test_conflicting_payloads_with_one_event_id_fail_closed():
    fixture = FIXTURES["duplicate"][0]
    accepted, rejected, duplicate_count = classify_events(
        [
            ("s3://bucket/raw/realtime/a.json", fixture["event_a"]),
            ("s3://bucket/raw/realtime/b.json", fixture["event_b"]),
        ]
    )
    assert accepted == []
    assert duplicate_count == 0
    assert {item.rule_id for item in rejected} == {"DUPLICATE_EVENT_ID_CONFLICT"}
    assert len(rejected) == 2


def test_invalid_record_is_accounted_as_a_rejection_not_silently_dropped():
    invalid = FIXTURES["invalid_null"][0]["event"]
    accepted, rejected, duplicate_count = classify_events(
        [("s3://bucket/raw/batch/historical.csv", invalid)]
    )
    assert accepted == []
    assert duplicate_count == 0
    assert rejected[0].rule_id == FIXTURES["invalid_null"][0]["expected_rule_id"]
