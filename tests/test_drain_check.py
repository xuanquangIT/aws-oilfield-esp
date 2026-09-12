"""Offline exit-gate tests for the M4 drain gate (scripts/drain-check.py)."""

import base64
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

_SPEC = importlib.util.spec_from_file_location(
    "drain_check", Path(__file__).resolve().parent.parent / "scripts" / "drain-check.py"
)
drain_check_module = importlib.util.module_from_spec(_SPEC)
sys.modules["drain_check"] = drain_check_module
_SPEC.loader.exec_module(drain_check_module)
drain_check = drain_check_module.drain_check


class FakeS3:
    """Enough of the boto3 S3 surface for the drain gate: head_object for
    exact raw-key existence, and list/get for a quarantine body scan."""

    def __init__(self, raw_keys, quarantine_objects):
        self.raw_keys = set(raw_keys)
        self.quarantine_objects = (
            quarantine_objects  # list of (key, last_modified, body_bytes)
        )
    def head_object(self, Bucket, Key):
        if Key in self.raw_keys:
            return {}
        raise ClientError({"Error": {"Code": "404", "Message": "NoSuchKey"}}, "HeadObject")

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        outer = self

        class _Paginator:
            def paginate(self, Bucket, Prefix):
                contents = [
                    {"Key": key, "LastModified": last_modified}
                    for key, last_modified, _ in outer.quarantine_objects
                ]
                yield {"Contents": contents}

        return _Paginator()

    def get_object(self, Bucket, Key):
        for key, _, body in self.quarantine_objects:
            if key == Key:
                return {"Body": io.BytesIO(body)}
        raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")


def _quarantine_body(raw_event: dict) -> bytes:
    envelope = {
        "rule_id": "OUT_OF_RANGE",
        "reason": "test",
        "received_at": "2026-01-01T00:00:05Z",
        "raw_base64": base64.b64encode(json.dumps(raw_event).encode()).decode(),
    }
    return json.dumps(envelope).encode()


def _write_ledger(tmp_path, monkeypatch, run_id: str, events: list[dict]):
    monkeypatch.chdir(tmp_path)
    ledger_dir = tmp_path / "data" / "producer-runs"
    ledger_dir.mkdir(parents=True)
    with (ledger_dir / f"{run_id}.jsonl").open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")


def _event(event_id, esp_id="ESP-101", ts="2026-01-01T00:00:00.000000Z"):
    return {"event_id": event_id, "esp_id": esp_id, "timestamp": ts}


def test_drain_check_passes_when_every_event_is_in_raw(tmp_path, monkeypatch):
    events = [_event("a"), _event("b")]
    _write_ledger(tmp_path, monkeypatch, "run-1", events)
    fake = FakeS3(
        raw_keys={
            drain_check_module._raw_key(events[0]),
            drain_check_module._raw_key(events[1]),
        },
        quarantine_objects=[],
    )
    monkeypatch.setattr(drain_check_module.boto3, "client", lambda *_a, **_k: fake)

    report = drain_check("bucket", "run-1", timeout_seconds=0, poll_interval_seconds=0)

    assert report["complete"] is True
    assert report["accounted_raw"] == 2
    assert report["missing"] == []


def test_drain_check_finds_events_preserved_in_quarantine(tmp_path, monkeypatch):
    events = [_event("a")]
    _write_ledger(tmp_path, monkeypatch, "run-2", events)
    fake = FakeS3(
        raw_keys=set(),
        quarantine_objects=[
            (
                "quarantine/realtime/OUT_OF_RANGE/ESP-101/2026/01/01/00/x.json",
                __import__("datetime").datetime(
                    2026, 1, 1, tzinfo=__import__("datetime").timezone.utc
                ),
                _quarantine_body(events[0]),
            ),
        ],
    )
    monkeypatch.setattr(drain_check_module.boto3, "client", lambda *_a, **_k: fake)

    report = drain_check("bucket", "run-2", timeout_seconds=0, poll_interval_seconds=0)

    assert report["complete"] is True
    assert report["accounted_quarantine"] == 1
    assert report["missing"] == []


def test_drain_check_reports_incomplete_run_after_timeout(tmp_path, monkeypatch):
    events = [_event("a"), _event("missing-one")]
    _write_ledger(tmp_path, monkeypatch, "run-3", events)
    fake = FakeS3(
        raw_keys={drain_check_module._raw_key(events[0])},
        quarantine_objects=[],
    )
    monkeypatch.setattr(drain_check_module.boto3, "client", lambda *_a, **_k: fake)

    report = drain_check("bucket", "run-3", timeout_seconds=0, poll_interval_seconds=0)

    assert report["complete"] is False
    assert report["missing"] == ["missing-one"]


def test_drain_check_requires_a_local_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        drain_check_module._load_ledger("no-such-run")
