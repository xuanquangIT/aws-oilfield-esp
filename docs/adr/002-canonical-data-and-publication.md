# ADR 002: Canonical events and gated publication

Status: accepted; M3 code implemented locally, AWS acceptance pending.

Context: current historical CSV and realtime JSON have different fields and do not reconcile. Current Glue overwrite can replace all published telemetry.

Decision: normalize both sources to telemetry v1, retain provenance, deduplicate by stable event_id, quarantine bad records, write immutable run-scoped output and publish only after quality checks. A manifest freezes selected raw S3 URIs plus byte SHA-256 values; a publication attempt has its own run ID and can reuse a prior manifest. Identical redeliveries retain the lexicographically first source URI; a shared event ID with differing normalized payload is a `DUPLICATE_EVENT_ID_CONFLICT` and blocks publication. The approved handoff is the atomically updated `curated/publication/current.json` pointer, written only after silver/gold and its quality report exist. Keep crawler as a learning exercise; it is not the approval mechanism.

Alternatives: append-only Parquet without dedupe corrupts aggregates under retries; whole-prefix overwrite risks previous results; Iceberg is useful for concurrent updates but adds concepts and maintenance beyond the first single-writer demo.

Consequences: manifests and publication control are required; old run cleanup must retain the last good result. Date-range plus late-lookback defines the reprocessed event-date window, so a one-day backfill writes a distinct run partition rather than overwriting another run. The first release does not claim distributed exactly-once transactions or live AWS completion until the mixed-source, rerun, backfill and Athena scan evidence is recorded. Iceberg becomes appropriate when update/concurrent-write requirements justify it.
