"""Provider-agnostic dashboard read models and port definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

PUMP_IDS = ("ESP-101", "ESP-102", "ESP-103")


@dataclass(frozen=True)
class PumpSnapshot:
    esp_id: str
    timestamp: str
    status: str
    scenario: str
    flow_rate: float | None = None
    motor_temperature: float | None = None
    motor_current: float | None = None
    vibration: float | None = None
    severity: str = "unknown"
    finding: str | None = None


@dataclass(frozen=True)
class PublicationSnapshot:
    published_run_id: str
    published_at: str
    quality_passed: bool
    counts: dict[str, int]
    kpis: list[dict]


class DashboardReadRepository(Protocol):
    def fetch_pumps(self) -> list[PumpSnapshot]: ...
    def fetch_latest_publication(self) -> PublicationSnapshot: ...
