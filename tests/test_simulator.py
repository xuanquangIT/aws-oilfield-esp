import random
from datetime import datetime, timezone

from contract import SCHEMA_VERSION, validate
from simulator.esp_simulator import build_event, signal


def test_normal():
    x = signal("ESP-101", 1, "normal")
    assert x["status"] == "RUNNING"
    assert x["flow_rate"] > 0


def test_low_flow():
    x = signal("ESP-101", 1, "low_flow")
    assert x["flow_rate"] < 60
    assert x["motor_temperature"] > 120


def test_shutdown():
    x = signal("ESP-101", 1, "shutdown")
    assert x["status"] == "SHUTDOWN"
    assert x["flow_rate"] == 0


def test_seeded_signal_is_deterministic():
    a = signal("ESP-101", 3, "gas_slug", random.Random(42))
    b = signal("ESP-101", 3, "gas_slug", random.Random(42))
    assert a == b


def test_build_event_is_contract_valid_and_reproducible():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = build_event(
        "ESP-101", 5, "low_flow", random.Random(7), now, "run-x", deterministic=True
    )
    b = build_event(
        "ESP-101", 5, "low_flow", random.Random(7), now, "run-x", deterministic=True
    )
    assert a == b
    result = validate(a)
    assert result.accepted, result.reason
    assert a["schema_version"] == SCHEMA_VERSION


def test_build_event_non_deterministic_ids_differ():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = build_event(
        "ESP-101", 5, "normal", random.Random(1), now, "run-y", deterministic=False
    )
    b = build_event(
        "ESP-101", 5, "normal", random.Random(2), now, "run-y", deterministic=False
    )
    assert a["event_id"] != b["event_id"]
