# Guided learning labs

Use each lab to build, break, recover, explain and clean. A design/tabletop lab is valid learning evidence but does not prove AWS implementation.

| Lab | Procedure | Failure/recovery and evidence | Mode |
|---|---|---|---|
| L1 Pipeline foundation | Validate locally; inspect core/realtime templates and dependencies | Break a function reference in a disposable copy; explain synth vs runtime failures | Local; runnable now |
| L2 Batch baseline | Generate/upload 504 rows; run job/crawler; execute SQL | Omit upload in a sandbox, inspect failure, then upload/rerun; save execution + counts | AWS; runnable now, paid |
| L3 Realtime baseline | Run low_flow five minutes; observe state/SNS/raw and cleanup | Use unconfirmed SNS email to distinguish publish from delivery; confirm and retest | AWS; runnable now, paid |
| L4 Reliable events | Implement M1/M2 then feed duplicate/older/invalid events | Predict counts first; verify latest state and replay after a transient failure | Implementation lab |
| L5 Analytical integrity | Implement M3; backfill one date and rerun manifest | Inject bad water_cut; preserve prior publication; compare result hashes | Implementation lab |
| L6 Data-store choice | Model pump-day fact and pump dimension; compare S3, DynamoDB, Redshift | Explain distribution/sort keys, COPY, Spectrum, skew and query concurrency; optional bounded Redshift test | Study first; AWS optional |
| L7 CDC | Create insert/update/delete sequence with source offsets in a local fixture | Replay duplicate update and delayed delete; explain DMS full-load + CDC and ordering | Local model; no DMS claim |
| L8 Stateful streaming | Define five-minute windows, late tolerance and watermark examples | Classify late arrival and checkpoint restart; optionally run a local Flink fixture | Study/local; no managed Flink claim |
| L9 Governance | Write analyst/publisher matrix and deny-case expectations | Optional Lake Formation/KMS sandbox test; recover permissions, remove lab resources | Study then optional AWS |
| L10 Open tables | Compare immutable Parquet publication with Iceberg MERGE/snapshots | Plan concurrent writer and rollback exercise; cost compaction and metadata retention | Study then optional isolated lab |
| L11 Operations | Implement expiry lease and cloud workflow in M4 | Disconnect laptop; verify remote stop; test denied deletion alarm | Implementation/AWS |
| L12 Modern data/AI | Sketch maintenance-note enrichment, embeddings and catalog ownership | Explain hallucination/DQ boundaries, HNSW vs IVF, retention and authorization | Study; no AI runtime needed |

Local lab tools beyond existing Python/CDK are not installed or implemented by these instructions. Choose/pin them explicitly when beginning that extension and record their own validation.

## Teach-back prompts and answer anchors

1. Why not keep Kinesis running? It has time-based capacity charges; intermittent demonstration does not need an always-available stream.
2. Why is a successful Lambda invocation insufficient? Other invocations can fail, duplicates repeat side effects, and raw/state/alerts are separate writes.
3. Why keep event time and ingestion time? Late events must enrich history without regressing latest state; freshness and latency need both.
4. Why not overwrite all Parquet for every backfill? It can remove unrelated good data and expose partial results to readers.
5. Why not deploy every exam service? Exam breadth is learned through comparisons and isolated labs; persistent extras add cost without improving this workload.
6. What does a budget guarantee? Notification behavior only; it does not impose a hard spend cap.
7. Why is latest state not a warehouse? It answers key-based operational reads, while historical grouping/joining needs a different access path.
8. Why do quality counts matter? A visually plausible chart can hide missing, duplicated or rejected observations.

For each completed lab save: objective, chosen service and alternative, exact inputs, result, failure, recovery, cost, cleanup and a two-minute explanation. Map the artifact to the appropriate task in [DEA-C01 coverage](06-DEA-C01-MAPPING.md).
