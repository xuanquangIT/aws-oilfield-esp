# ADR 001: Small core and disposable realtime

Status: accepted, 2026-09-05.

Context: three synthetic pumps emit a tiny intermittent workload; the owner values reconstructability and minimal parked cost.

Decision: core owns durable demo data and service definitions. Realtime owns a one-shard provisioned stream, mappings and stream-specific policies. Dependencies point realtime -> core. Realtime start attempts cleanup; full reset explicitly deletes data.

Alternatives: on-demand stream simplifies variable scale but is unnecessary for this tiny load; direct Lambda ingestion removes Kinesis cost but loses a useful buffering/replay learning surface; permanently deployed Flink/Kafka is disproportionate.

Consequences: demos need deployment lead time; deleting the stream removes its replay buffer. Current finally cleanup is best-effort until M4 cloud expiry. One shard is not a production capacity claim. Core uses destructive removal only for explicit full reset; preserving data means parking, not deleting core. Bootstrap and logs can retain small costs.
