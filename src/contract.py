"""Shared telemetry contract (schema v1).

This is the single validator used by the realtime producer (simulator), the
historical seed generator, and the realtime ingest transformation
(stream_processor Lambda). It has no AWS or third-party dependencies so it
can run unmodified inside a Lambda deployment package, in local scripts, and
in offline tests. See docs/03-DATA-DOMAIN-AND-CONTRACT.md for the full
contract narrative and units.

M1 scope only: structural/type/range validation and schema-version gating.
Cross-record concerns (duplicate suppression, late-arrival state handling,
conditional writes, alert cooldown) belong to M2 and are intentionally not
implemented here; see the `duplicate` and `late` fixtures for the boundary.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

SCHEMA_VERSION = 1

KNOWN_ESP_IDS = {"ESP-101", "ESP-102", "ESP-103"}
KNOWN_SOURCES = {"historical", "realtime"}
KNOWN_STATUSES = {"RUNNING", "SHUTDOWN", "UNKNOWN"}

REQUIRED_FIELDS = (
    "schema_version",
    "event_id",
    "timestamp",
    "esp_id",
    "source",
    "run_id",
    "status",
)
REQUIRED_NUMERIC_FIELDS = (
    "flow_rate",
    "water_cut",
    "motor_temperature",
    "motor_current",
    "vibration",
)
OPTIONAL_NUMERIC_FIELDS = (
    "intake_pressure",
    "discharge_pressure",
    "tubing_pressure",
    "casing_pressure",
    "intake_temperature",
    "pump_frequency",
)

# Fixed namespace so uuid5-derived event IDs are reproducible across runs and machines.
_EVENT_ID_NAMESPACE = uuid.UUID("2f1b1a54-8f9a-4a9a-9b9e-6e8a2f6a9b30")


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    rule_id: str
    reason: str
    event: Optional[dict] = None  # normalized event, only set when accepted


def new_event_id(deterministic_key: Optional[str] = None) -> str:
    """Return a producer-generated event identity.

    Deterministic (uuid5) when `deterministic_key` is given, so fixtures and
    demo runs built from the same seed/start-time reproduce the same
    event_id on every run. Otherwise a random uuid4, for live/non-seeded
    runs where reproducibility is not required.
    """
    if deterministic_key:
        return str(uuid.uuid5(_EVENT_ID_NAMESPACE, deterministic_key))
    return str(uuid.uuid4())


def iso_z(dt: datetime) -> str:
    """Format a timezone-aware datetime as ISO-8601 UTC with a 'Z' suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (
        dt.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def parse_iso_utc(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp (with 'Z' or explicit offset) to UTC.

    Returns None (never raises) for anything that is not a valid,
    timezone-aware ISO-8601 string, so callers can treat it as a validation
    outcome rather than an exception path.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate(raw: Any) -> ValidationResult:
    """Validate one telemetry event against schema v1.

    `raw` must already be a decoded JSON value. Callers are responsible for
    catching decode/decoding errors themselves and reporting them with a
    MALFORMED_PAYLOAD-style outcome before ever calling this function; a
    non-dict value is still handled defensively here for safety.
    """
    if not isinstance(raw, dict):
        return ValidationResult(
            False, "MALFORMED_PAYLOAD", "event is not a JSON object"
        )

    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        return ValidationResult(
            False,
            "SCHEMA_VERSION_UNSUPPORTED",
            f"schema_version {version!r} is not supported (expected {SCHEMA_VERSION})",
        )

    for name in REQUIRED_FIELDS:
        if raw.get(name) in (None, ""):
            return ValidationResult(
                False, "MISSING_FIELD", f"required field '{name}' is missing"
            )

    esp_id = raw["esp_id"]
    if esp_id not in KNOWN_ESP_IDS:
        return ValidationResult(
            False, "UNKNOWN_ESP_ID", f"esp_id '{esp_id}' is not a registered pump"
        )

    if raw["source"] not in KNOWN_SOURCES:
        return ValidationResult(
            False,
            "INVALID_SOURCE",
            f"source '{raw['source']}' must be one of {sorted(KNOWN_SOURCES)}",
        )

    if raw["status"] not in KNOWN_STATUSES:
        return ValidationResult(
            False,
            "INVALID_STATUS",
            f"status '{raw['status']}' must be one of {sorted(KNOWN_STATUSES)}",
        )

    event_time = parse_iso_utc(raw["timestamp"])
    if event_time is None:
        return ValidationResult(
            False, "INVALID_TIMESTAMP", "timestamp is not a UTC ISO-8601 value"
        )

    for name in REQUIRED_NUMERIC_FIELDS:
        if not _is_finite_number(raw.get(name)):
            return ValidationResult(
                False, "NON_FINITE_NUMBER", f"field '{name}' must be a finite number"
            )

    if not (0.0 <= float(raw["water_cut"]) <= 1.0):
        return ValidationResult(False, "OUT_OF_RANGE", "water_cut must be within 0..1")
    if float(raw["flow_rate"]) < 0:
        return ValidationResult(False, "OUT_OF_RANGE", "flow_rate must be >= 0")
    if float(raw["motor_current"]) < 0:
        return ValidationResult(False, "OUT_OF_RANGE", "motor_current must be >= 0")
    if float(raw["vibration"]) < 0:
        return ValidationResult(False, "OUT_OF_RANGE", "vibration must be >= 0")

    for name in OPTIONAL_NUMERIC_FIELDS:
        value = raw.get(name)
        if value is not None and not _is_finite_number(value):
            return ValidationResult(
                False,
                "NON_FINITE_NUMBER",
                f"optional field '{name}' must be a finite number or null",
            )

    normalized = dict(raw)
    normalized["timestamp"] = iso_z(event_time)
    return ValidationResult(True, "OK", "valid", normalized)
