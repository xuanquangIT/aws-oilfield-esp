"""Deterministic fixture implementation of the dashboard repository port."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dashboard.app.domain.models import PUMP_IDS, PublicationSnapshot, PumpSnapshot


class FixtureDashboardRepository:
    def __init__(self, state: str = "normal"):
        self.state = state

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def fetch_pumps(self) -> list[PumpSnapshot]:
        if self.state == "unavailable":
            raise RuntimeError("fixture dependency unavailable")
        now, age = self._now(), 55 if self.state == "stale" else 4
        timestamp = (now - timedelta(seconds=age)).isoformat().replace("+00:00", "Z")
        return [
            PumpSnapshot(pump, timestamp, "RUNNING", "low_flow" if self.state == "low-flow" and pump == "ESP-102" else "normal", 42.0 if self.state == "low-flow" and pump == "ESP-102" else 105.0 + index, 94.0 if self.state == "low-flow" and pump == "ESP-102" else 78.0 + index, 38.0 + index, 2.1 + index / 10, "warning" if self.state == "low-flow" and pump == "ESP-102" else "normal", "Low flow rate" if self.state == "low-flow" and pump == "ESP-102" else None)
            for index, pump in enumerate(PUMP_IDS)
        ]

    def fetch_latest_publication(self) -> PublicationSnapshot:
        if self.state == "unavailable":
            raise RuntimeError("fixture dependency unavailable")
        now = self._now().isoformat().replace("+00:00", "Z")
        return PublicationSnapshot("fixture-m5-run-001", now, True, {"silver_rows": 252, "gold_rows": 6, "unexplained_rows": 0}, [{"esp_id": pump, "avg_liquid_rate_m3_day": 102.0} for pump in PUMP_IDS])
