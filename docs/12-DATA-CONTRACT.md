# Telemetry contract

## Current wire formats

Realtime JSON contains timestamp, esp_id, scenario, status and all signals in [domain notes](10-DOMAIN-NOTES.md). Historical CSV contains timestamp, esp_id, flow_rate, water_cut, intake_pressure, discharge_pressure, motor_temperature, motor_current, vibration and status.

Current code does not enforce the target contract below. There is no event_id/schema_version; historical data lacks several realtime fields. Missing values must not be silently interpreted as physical zero.

## Target telemetry v1: M1

| Field | Type / rule |
|---|---|
| schema_version | Integer 1; unknown incompatible versions quarantined |
| event_id | Producer-generated UUID/string; stable across retries/replays |
| timestamp | ISO-8601 UTC with Z; observation/event time |
| ingested_at | Platform-assigned UTC time, separate from event time |
| esp_id | Registered synthetic pump identifier |
| source | historical or realtime |
| run_id | Producer run identity; separate batch/replay execution identities |
| status | RUNNING, SHUTDOWN, UNKNOWN |
| flow_rate, water_cut | Finite numbers; flow >=0; fraction within 0..1 |
| motor_temperature, motor_current, vibration | Finite numbers with declared units; current/vibration >=0 |
| pressure/frequency/other temperature fields | Optional where historical source omits them; preserve null |
| scenario | Optional test label, excluded from production-style rule inputs |

Event identity is not the Kinesis sequence number, which changes when republishing. Historical adapters derive a stable ID from immutable source checksum and row number. Equal event IDs with differing payloads are conflicts, not arbitrary last-writer-wins.

## Validation and evolution

1. Parse JSON/CSV and reject malformed encoding or invalid shape.
2. Validate version, required identity, UTC timestamp and finite numeric values.
3. Validate pump ID and physical/type constraints. Treat unusual but possible operating values as quality flags rather than automatically deleting them.
4. Keep valid late events in raw/silver, but do not allow them to regress latest state.
5. Preserve rejected payload/source reference with rule ID and reason.
6. Add optional fields compatibly; renaming, unit changes and type changes require a new version/adapter.

Future timestamp skew tolerance is a configured rule (proposed five minutes), not yet implemented. A fixed timestamp alone is not a duplicate; event identity decides. Sample intervals and source granularity must be retained for KPI interpretation.

## Storage and lineage target

- raw: immutable input plus source checksum, run manifest and arrival metadata.
- quarantine: rejected content, rule, source pointer, schema version, review outcome.
- silver: canonical typed event, event_id and provenance.
- gold: per-pump/day aggregations with sample coverage and source run.
- publication manifest: selected successful run, input/output counts and quality result.

Proposed conservation rule for a bounded fixture: received = accepted unique + duplicate identical + rejected/conflicting. Track transport failures separately; only acknowledged sends belong to delivered-input reconciliation.

Raw and failure retention currently differ (7/14 days); the target replay window cannot exceed available sources. Export a fixture or extend retention deliberately before promising older recovery.
