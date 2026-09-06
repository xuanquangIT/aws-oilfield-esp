# ADR 002: Canonical events and gated publication

Status: accepted design, implementation M1-M3.

Context: current historical CSV and realtime JSON have different fields and do not reconcile. Current Glue overwrite can replace all published telemetry.

Decision: normalize both sources to telemetry v1, retain provenance, deduplicate by stable event_id, quarantine bad records, write immutable run-scoped output and publish only after quality checks. Use explicit catalog schema for the stable product. Keep crawler as a learning exercise.

Alternatives: append-only Parquet without dedupe corrupts aggregates under retries; whole-prefix overwrite risks previous results; Iceberg is useful for concurrent updates but adds concepts and maintenance beyond the first single-writer demo.

Consequences: manifests and publication control are required; old run cleanup must retain the last good result. The first release does not claim distributed exactly-once transactions. Iceberg becomes appropriate when update/concurrent-write requirements justify it.
