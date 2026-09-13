"""Deterministic offline read models for dashboard development and tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

PUMP_IDS = ("ESP-101", "ESP-102", "ESP-103")


def fixture_pumps(state: str, now: datetime) -> list[dict]:
    if state not in {"normal", "low-flow", "stale", "unavailable"}:
        raise ValueError("Unknown fixture state")
    if state == "unavailable":
        raise RuntimeError("fixture dependency unavailable")
    age = 55 if state == "stale" else 4
    observed = now - timedelta(seconds=age)
    result = []
    for index, esp_id in enumerate(PUMP_IDS):
        low = state == "low-flow" and esp_id == "ESP-102"
        result.append(
            {
                "esp_id": esp_id, "timestamp": observed.isoformat().replace("+00:00", "Z"),
                "status": "RUNNING", "scenario": "low_flow" if low else "normal",
                "flow_rate": 42.0 if low else 105.0 + index,
                "motor_temperature": 94.0 if low else 78.0 + index,
                "motor_current": 38.0 + index, "vibration": 2.1 + index / 10,
                "severity": "warning" if low else "normal",
                "finding": "Low flow rate" if low else None,
            }
        )
    return result


def fixture_kpis(state: str, now: datetime) -> dict:
    if state == "unavailable":
        raise RuntimeError("fixture dependency unavailable")
    return {
        "published_run_id": "fixture-m5-run-001",
        "published_at": now.isoformat().replace("+00:00", "Z"),
        "quality_passed": True,
        "counts": {"silver_rows": 252, "gold_rows": 6, "unexplained_rows": 0},
        "kpis": [{"esp_id": pump, "avg_liquid_rate_m3_day": 102.0} for pump in PUMP_IDS],
    }
