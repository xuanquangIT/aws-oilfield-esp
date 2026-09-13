"""Typed runtime configuration.  No AWS values are sent to browser clients."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

DashboardMode = Literal["fixture", "aws"]
FixtureState = Literal["normal", "low-flow", "stale", "unavailable"]


@dataclass(frozen=True)
class Settings:
    mode: DashboardMode = "fixture"
    fixture_state: FixtureState = "normal"
    host: str = "127.0.0.1"
    port: int = 8765
    cache_ttl_seconds: int = 10
    unavailable_after_seconds: int = 45
    aws_region: str = "us-east-1"
    aws_profile: str | None = None
    core_stack_name: str = "oilfield-esp-core"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mode=os.getenv("DASHBOARD_MODE", "fixture"),
            fixture_state=os.getenv("DASHBOARD_FIXTURE_STATE", "normal"),
            aws_region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
            aws_profile=os.getenv("AWS_PROFILE"),
        )
