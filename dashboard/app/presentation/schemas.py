"""Public HTTP DTOs; these are the only objects serialized to clients."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Freshness = Literal["fresh", "stale", "unavailable"]


class PumpDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    esp_id: str
    timestamp: str
    status: str
    scenario: str
    flow_rate: float | None = None
    motor_temperature: float | None = None
    motor_current: float | None = None
    vibration: float | None = None
    severity: str
    finding: str | None = None


class PublicationDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    published_run_id: str
    published_at: str
    quality_passed: bool
    counts: dict[str, int]
    kpis: list[dict]


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["dashboard.v1"] = "dashboard.v1"
    state: Freshness
    fetched_at: str | None
    data_age_seconds: int | None = Field(default=None, ge=0)
    data: object


class HealthDto(BaseModel):
    schema_version: Literal["dashboard.v1"] = "dashboard.v1"
    mode: Literal["fixture", "aws"]
    pump_cache: dict[str, object]
    publication_cache: dict[str, object]
