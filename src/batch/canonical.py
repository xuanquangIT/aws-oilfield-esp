"""Pure, deterministic helpers shared by the M3 batch tooling and tests.

The Glue runtime performs the distributed read/write work.  Keeping manifest
and event-identity decisions here makes the rules reviewable without a Spark
or AWS installation: one canonical event per event_id, an explicit conflict
for different payloads sharing an ID, and a byte-stable input manifest.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from contract import validate


MANIFEST_VERSION = 1
METADATA_VERSION = "pump-metadata-v1"


@dataclass(frozen=True)
class RejectedEvent:
    source_uri: str
    event_id: str | None
    rule_id: str
    reason: str


def canonical_json(value: Any) -> str:
    """Encode JSON in a portable, deterministic form for hashes/manifests."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def event_payload(event: dict) -> dict:
    """Return fields whose equality defines a duplicate event identity.

    Provenance (S3 URI and batch execution) is deliberately excluded.  Two
    identical deliveries from different raw objects are duplicates; two
    payloads with the same event_id but differing contract fields are a data
    quality conflict and neither is silently selected.
    """
    result = validate(event)
    if not result.accepted or result.event is None:
        raise ValueError(f"cannot canonicalize invalid event: {result.rule_id}")
    return result.event


def payload_sha256(event: dict) -> str:
    return sha256_bytes(canonical_json(event_payload(event)).encode("utf-8"))


def build_manifest(
    *,
    manifest_id: str,
    start_date: str,
    end_date: str,
    late_arrival_lookback_days: int,
    objects: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Build the immutable M3 input manifest.

    Each object needs ``uri``, ``source_kind``, ``sha256`` and ``size_bytes``.
    Sorting makes a rerun with the same selected objects byte-identical.
    """
    if late_arrival_lookback_days < 0:
        raise ValueError("late_arrival_lookback_days must be >= 0")
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")
    normalized = []
    for item in objects:
        required = {"uri", "source_kind", "sha256", "size_bytes"}
        missing = required.difference(item)
        if missing:
            raise ValueError(f"manifest object is missing {sorted(missing)}")
        normalized_item = {key: item[key] for key in sorted(required)}
        if "last_modified_utc" in item:
            normalized_item["last_modified_utc"] = item["last_modified_utc"]
        normalized.append(normalized_item)
    return {
        "manifest_version": MANIFEST_VERSION,
        "manifest_id": manifest_id,
        "schema_version": 1,
        "metadata_version": METADATA_VERSION,
        "start_date": start_date,
        "end_date": end_date,
        "late_arrival_lookback_days": late_arrival_lookback_days,
        "objects": sorted(normalized, key=lambda item: item["uri"]),
    }


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(manifest).encode("utf-8"))


def selected_start_date(start_date: str, late_arrival_lookback_days: int) -> str:
    return (date.fromisoformat(start_date) - timedelta(days=late_arrival_lookback_days)).isoformat()


def classify_events(
    rows: Iterable[tuple[str, dict]],
) -> tuple[list[tuple[str, dict]], list[RejectedEvent], int]:
    """Validate and deduplicate rows deterministically for local M3 tests.

    Returns ``(accepted, rejected, duplicate_delivery_count)``.  A duplicate
    identical payload keeps the lexicographically first source URI.  A shared
    event_id with different normalized payload hashes rejects every conflicting
    row; this is fail-closed rather than arbitrary last-writer-wins.
    """
    valid: dict[str, list[tuple[str, dict, str]]] = defaultdict(list)
    rejected: list[RejectedEvent] = []
    for source_uri, raw in rows:
        result = validate(raw)
        if not result.accepted or result.event is None:
            rejected.append(
                RejectedEvent(
                    source_uri=source_uri,
                    event_id=raw.get("event_id") if isinstance(raw, dict) else None,
                    rule_id=result.rule_id,
                    reason=result.reason,
                )
            )
            continue
        normalized = result.event
        valid[normalized["event_id"]].append(
            (source_uri, normalized, payload_sha256(normalized))
        )

    accepted: list[tuple[str, dict]] = []
    duplicate_count = 0
    for event_id in sorted(valid):
        entries = sorted(valid[event_id], key=lambda entry: entry[0])
        hashes = {entry[2] for entry in entries}
        if len(hashes) != 1:
            for source_uri, _, _ in entries:
                rejected.append(
                    RejectedEvent(
                        source_uri=source_uri,
                        event_id=event_id,
                        rule_id="DUPLICATE_EVENT_ID_CONFLICT",
                        reason="same event_id has different normalized payloads",
                    )
                )
            continue
        accepted.append((entries[0][0], entries[0][1]))
        duplicate_count += len(entries) - 1
    return accepted, rejected, duplicate_count
