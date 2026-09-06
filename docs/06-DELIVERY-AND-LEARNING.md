# Delivery, acceptance and DEA-C01 learning

This document is the implementation backlog, release gate and exam-learning map. The committed Phase 1 scope is a complete flow from both ingestion paths through publication, query and consumer dashboard. Planned capabilities remain planned until code, tests and the stated evidence exist.

## Delivery plan

### Scope and priorities

One coherent Phase 1 product: historical CSV and realtime ESP ingestion -> validation/raw/quarantine -> trustworthy operational state plus reconciled silver/gold KPIs -> approved publication and Athena query -> local realtime web dashboard -> reproducible customer evidence. Minimize idle cost and operator effort before adding more services.

The current revision delivers documentation/workspace organization and foundation fixes. The milestones below are the implementation backlog, not a claim that the finished platform already exists. Estimates are planning ranges for one developer, excluding environment access delays.

### Milestones

| Milestone | Dependency / effort | Work and exit gate |
|---|---|---|
| M0 Foundation | Current revision | Offline tests + synth, actual stack wiring, checked lifecycle scripts, cost/source review, honest status ledger |
| M1 Contract and fixtures | M0 / 1-2 days | Versioned schema, deterministic seed/run IDs, shared validation, typed units, pump metadata; fixtures for valid, null, malformed, duplicate, late and incompatible versions |
| M2 Reliable streaming | M1 / 2-3 days | Stable event IDs, conditional latest state, failure/quarantine separation, alert cooldown/history, bounded producer retry, replay command; behavioral tests show no backward state or duplicate side effects |
| M3 Integrated batch | M1 + M2 raw contract / 3-4 days | CSV/JSON union, pump join, DQ + dedupe, run-scoped output, stable catalog, date backfill, gold KPI SQL; counts and rerun results reconcile |
| M4 Operations/security | M2 + M3 / 2-3 days | Cloud batch completion, scoped retry/catch, publish gate, expiry lease, drain/lock, least privilege, alarms, restore/deny drills and residual cost inventory |
| M5 Dashboard and customer release | UI scaffold alongside M1-M4; final integration after M4 / 2-3 days | Localhost web dashboard + local read API, latest-state and KPI views, redacted evidence, two clean rehearsals, recreate test, measured freshness/incremental usage, customer recording |
| M6 Exam extensions | Alongside, isolated / 3-5 days | DEA task exercises for CDC/warehouse/windows/governance/Iceberg and study-only modern data/AI topics |

Phase 1 is M0-M5 and is not complete without both source paths reaching the approved publication and the dashboard consuming real latest-state and KPI data. UI layout, fixture mode and local API contract can be built alongside M1-M4; live integration and release evidence remain gated by M2-M4. M6 enriches exam breadth but must not add persistent baseline infrastructure.

### M1: data quality is an interface

Implement the [contract](03-DATA-DOMAIN-AND-CONTRACT.md), with one validator used by the producer fixtures and ingest transformations. Preserve raw bytes before normalization where feasible. Use explicit rule IDs and reason codes. Seed generation takes --seed and --start-time so a fixture checksum is repeatable.

Exit: all expected-valid rows pass; all deliberately invalid rows are rejected for the right reason; optional additions are backward-compatible; invalid versions cannot silently enter silver. Commit synthetic fixtures only.

### M2: streaming correctness before visual polish

Use event_id for replay identity and source sequence only as transport metadata. A conditional DynamoDB update accepts a newer event timestamp; late valid records remain in history. Define equal-time conflict behavior. Store numbers as numbers.

An alert history/outbox design must handle a crash between dedupe persistence and SNS publish. Do not claim exactly-once SNS delivery; use deterministic alert IDs so downstream consumers can deduplicate. Cooldown is per pump/rule, with recovery state. Partition by pump to keep relevant order.

Producer retries transient/throttle failures with bounded exponential backoff, preserves event IDs, and records acknowledged/failed sends. Consumer tests inject an S3/DynamoDB/SNS failure and verify recovery. Replay tool validates an S3 failure payload, supports dry-run and records a replay receipt.

Exit: duplicate, late and invalid fixtures have expected counts; state is monotonic; no event disappears without accepted/rejected/failed accounting; alert behavior is explained. Low-flow detection uses measurements. Gas-slug/stuck-sensor temporal detection can remain explicitly deferred.

### M3: one analytical pipeline

Use the same schema for historical and realtime records. Join small versioned pump metadata. Write staging output per run; derive row counts and data-quality report before publishing an approved catalog location. A failed run must leave the prior published dataset queryable.

Choose immutable run output for this single-writer capstone. Do not use append without dedupe or wholesale overwrite for incremental workloads. Record input manifest/checksums, schema/rules version and output path. Parameterize date range and late-arrival lookback.

Exit: batch and realtime events appear together; input accounting balances; rerunning the same manifest yields the same canonical results; one-day backfill does not change unrelated days; SQL demonstrates partition pruning with actual bytes scanned.

### M4: survive operator absence

Move crawler/catalog/publication completion into Step Functions; keep CLI as launcher/observer. Use bounded retries only for transient errors and explicit failure state with diagnostic output. Prevent overlapping publish runs.

Create an independent one-shot expiry workflow before stream use; lease includes stack identity, region, expiry and run owner. Delete only realtime. Verify DELETE_COMPLETE and alert if denied or stuck. A laptop-disconnection test must leave no running stream past the agreed deadline. Do not grant broad administrator cleanup permissions.

Drain gate compares acknowledged producer event IDs to archived accepted/invalid records and consumer outcomes before normal deletion. Timeout reports incomplete delivery; it must not silently mark a run successful. Expiry cleanup may sacrifice unprocessed records to stop spend, so save producer fixtures and label incomplete runs.

Complete [security tests](05-COST-AND-SECURITY.md), export/restore drill, CloudTrail/log evidence and service-created log-retention policy. Estimate any additional monitoring/expiry costs.

### M5: Phase 1 dashboard and customer release

Implement the [dashboard design](07-DEMO-AND-DASHBOARD.md) as part of Phase 1. Deliver a responsive single-page web UI and small local read API. The service binds to `127.0.0.1` by default and uses the operator's existing AWS credential chain on the server side; credentials never enter HTML or JavaScript.

The local API performs a batched read of the known ESP IDs from DynamoDB and maintains a 10–15 second cache shared by all local browser tabs. It fetches approved KPI JSON from S3 only when the publication identifier changes or on explicit refresh. It never runs Athena per poll, scans DynamoDB, reads raw/failure prefixes, or listens on the LAN by default.

The UI shows pump status, data age, last observation time, active synthetic alert severity, flow/temperature/current, and batch KPI/quality timestamp. It visibly shows `Synthetic data`, `Local demo`, `Last refreshed`, `Data age`, and the published batch run ID. API failure keeps the last value only with an explicit stale state, then becomes unavailable after the configured threshold.

Build the UI shell and fixture mode alongside M1-M4. Connect live DynamoDB after M2 and approved KPI JSON after M3. Complete security, cleanup, failure and cost evidence after M4. The optional CloudFront/API Gateway/Cognito/Lambda hosted profile is a later deployment option and is not a Phase 1 pass requirement.

Exit: the local dashboard starts with one command, opens from localhost, never exposes credentials, returns only allow-listed fields, shows normal and low-flow state within the measured target, handles stale/error state, consumes the verified published KPI run, stops cleanly, and passes two complete demo rehearsals. A 60-minute run records cache behavior, DynamoDB/S3 requests and incremental usage. Dashboard evidence cannot replace M1-M4 reconciliation evidence.

#### M5 release evidence

Target p95 freshness <=15 seconds at the small demo rate; clean core rebuild <=20 minutes and full preparation <=30 minutes, measured rather than promised. Run normal and faulty scenarios, recovery, integrated batch, report generation, park and rebuild twice. Record cost later when AWS billing data becomes available.

Do not block a supervised internal demo on the optional M6 service labs. Do block a customer-ready claim on missing reconciliation, cleanup or unsupported KPI claims.

### Change control

Maintain PROJECT-STATUS.md, CHANGELOG.md, acceptance evidence and the appropriate ADR together. One backlog item should include problem, implementation scope, negative test, cleanup and artifact. Avoid renaming working folders solely for appearance. Keep secrets, generated datasets and unredacted run records outside version control.

## Acceptance and evidence

### Evidence levels

- Offline: unit tests, source checks and synthesized CloudFormation.
- AWS smoke: specific service deployment and a bounded observed operation.
- Integrated: producer -> storage/state -> batch -> published KPI with reconciled IDs/counts.
- Rehearsed: integrated run plus fault recovery, cleanup, rebuild and observed costs.

Never promote a lower level by renaming a report. Record not_run/unknown for missing checks, not pass.

### Release checklist

| Gate | Required result |
|---|---|
| G0 Foundation | Local tests + synth; core independent of realtime; checked script exits |
| G1 Contract | Valid/invalid/evolution fixtures have exact expected results |
| G2 Realtime | Duplicate/out-of-order/retry tests; no backward latest state; alert dedupe semantics documented |
| G3 Batch | Unified data, zero unexplained count gap, deterministic rerun, unaffected backfill dates unchanged |
| G4 Security | Positive and negative permissions tested with intended principals |
| G5 Recovery | Failure payload replay and failed publication preserve prior result |
| G6 Lifecycle | Normal cleanup plus laptop-loss expiry; no running stream/jobs after deadline |
| G7 Rebuild | Export/reset/recreate/restore or regenerate succeeds twice with lockfiles |
| G8 Customer | KPI report, observed p95 freshness and scan bytes, redacted recording |
| G9 Cost | Usage worksheet plus later bill, residual resource inventory, assumptions stated |
| G10 Dashboard | Localhost-only web dashboard, no browser credentials, allow-listed API, cache/stale-state behavior and measured 60-minute rehearsal; hosted profile optional |

Target latency is <=15 seconds p95 at approximately three records/second. Measure end-to-end by polling the latest-state view and joining producer timestamps; Lambda duration alone is not end-to-end freshness. Set clock synchronization and polling interval in evidence.

### Failure fixtures

Include malformed JSON, missing ID, invalid numeric value, incompatible schema, repeated event, older event, transient throttle, denied storage, failed batch and process interruption. Each fixture needs expected accepted/rejected counts, recovery action and teardown.

A clean run should prove acknowledged producer IDs reconcile after drain. On failed runs, explicitly distinguish producer-unacknowledged events, validation rejects, duplicates, archive success, latest-state exclusion for old events and failed delivery destinations.

### Run artifacts

Start from [cloud run template](../evidence/templates/cloud-run.json). Save under evidence/runs/<run-id>/ (ignored by Git). Include source hashes/commit when available, dependency locks, account/region privately, start/end, stack events, input manifest, Lambda metrics, Glue/crawler execution IDs, SQL results and scanned bytes, cleanup read-backs and cost status.

Only publish a redacted copy. Do not fabricate a run ID, cost, screenshot or service success to complete the template.

Current evidence: [local validation](../evidence/LOCAL-VALIDATION.md). Cloud acceptance remains not_run until actual AWS operations are completed.

## AWS DEA-C01 coverage

Official English guide reviewed 2026-09-05: domains carry **34%, 26%, 22%, 18%**. This matrix addresses every task group, not every possible exam question or every service. Current scope includes topics beyond this small runtime; do those as isolated labs or design exercises. [Exam guide](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01.html).

**Code** = present but not cloud-proven. **Plan** = implementation required. **Lab** = optional isolated exercise. **Study** = explain/design without deploying. Evidence must carry one of these labels; no service-count-based readiness score.

| Task | Current basis | Required project evidence / next exercise |
|---|---|---|
| 1.1 Ingestion | Code: CSV, Kinesis, two consumers | M2 duplicate/late/invalid/replay drill; Lab compare DMS CDC, API pagination and Firehose |
| 1.2 Transformation | Code: Spark CSV -> Parquet and derived oil rate | M3 union/join, normalization, rejects, performance comparison; Study LLM enrichment boundaries |
| 1.3 Orchestration | Code: Glue task, client-side crawler | M4 cloud-owned publish workflow, retry/catch and controlled failure |
| 1.4 Programming | Code: Python, CDK, PowerShell, offline CI | Tests and locked dependencies; explain partition parallelism and deployment change review |
| 2.1 Store selection | Code: S3 history, DynamoDB latest state | ADR access-pattern comparison; Lab Iceberg; Study Redshift/RDS, vectors HNSW/IVF |
| 2.2 Catalogs | Code: crawler and Glue database | M3 stable schema/partitions; Study business catalog ownership and SageMaker Catalog |
| 2.3 Lifecycle | Code: S3 expiry, explicit reset | M4 export/restore and residual inventory; Lab TTL/versioning and deletion policy |
| 2.4 Modeling/evolution | Code: flat telemetry/date partitions | M1 v1/v2 contract fixture; M3 pump dimension and lineage; Study vectorization |
| 3.1 Automation | Code: SDK producer and lifecycle wrappers | M4 automated completion with laptop disconnected; Lab API/backoff |
| 3.2 Analysis | Code: Athena SQL templates | M5 KPI report; measured scan savings and missing-data interpretation |
| 3.3 Monitoring/support | Code: retained app logs; failure payloads | M4 alarm/recovery evidence, correlation IDs and CloudTrail review |
| 3.4 Quality | Plan: quality contract and SQL checks | M1/M3 rejected rows, freshness, reconciliation, skew and rerun tests |
| 4.1 Authentication | Code: workload roles; profile instructions | M4 temporary credentials / denied expired session; Study VPC endpoints and rotation |
| 4.2 Authorization | Code: scoped resources; broad Glue managed baseline | M4 publisher/analyst negative tests; Lab Lake Formation row/column access |
| 4.3 Encryption/masking | Code: S3 encryption and TLS | M4 denied insecure request; Lab KMS key-policy failure and synthetic masking |
| 4.4 Audit | Code: application log groups | M4 deploy/query attribution; Lab CloudTrail evidence and query; cost scope recorded |
| 4.5 Governance | Study: synthetic data, region and ownership policy | M4 glossary/lineage/deletion record; Study Macie, Config, sovereignty and sharing |

Domain references: [D1](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain1.html), [D2](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain2.html), [D3](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain3.html), [D4](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain4.html).

### Coverage outside the base runtime

Use [M6 labs](06-DELIVERY-AND-LEARNING.md) for warehouse design and Redshift SQL/COPY/Spectrum, CDC ordering and delete events, Flink windows/watermarks/checkpoints, Lake Formation governance, KMS, Iceberg and migration. Compare Glue/EMR, Step Functions/Airflow, Kinesis/MSK/Firehose, S3/warehouse/key-value stores based on latency, access pattern and cost.

The current guide also includes LLM processing, open table formats, vector indexes/vectorization, SageMaker Catalog and Unified Studio. Explain these through a maintenance-note enrichment and searchable pump-document scenario; no paid AI endpoint is required for the core demo. Recheck the official guide before booking an exam.

### Completion rule

For each task, link an artifact plus a short explanation of service choice, failure mode, recovery and cost. A study-only entry may close a learning exercise, but cannot be relabeled as AWS hands-on evidence. Preserve remaining subskills in the learning backlog rather than claiming 100% certification coverage.

## Guided learning labs

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

### Teach-back prompts and answer anchors

1. Why not keep Kinesis running? It has time-based capacity charges; intermittent demonstration does not need an always-available stream.
2. Why is a successful Lambda invocation insufficient? Other invocations can fail, duplicates repeat side effects, and raw/state/alerts are separate writes.
3. Why keep event time and ingestion time? Late events must enrich history without regressing latest state; freshness and latency need both.
4. Why not overwrite all Parquet for every backfill? It can remove unrelated good data and expose partial results to readers.
5. Why not deploy every exam service? Exam breadth is learned through comparisons and isolated labs; persistent extras add cost without improving this workload.
6. What does a budget guarantee? Notification behavior only; it does not impose a hard spend cap.
7. Why is latest state not a warehouse? It answers key-based operational reads, while historical grouping/joining needs a different access path.
8. Why do quality counts matter? A visually plausible chart can hide missing, duplicated or rejected observations.

For each completed lab save: objective, chosen service and alternative, exact inputs, result, failure, recovery, cost, cleanup and a two-minute explanation. Map the artifact to the appropriate task in [DEA-C01 coverage](06-DELIVERY-AND-LEARNING.md).

## Learning method

For every module, explain five things before deployment: input, output, failure behavior, cost driver and evidence. Build or change one layer, predict the outcome, run the smallest useful test, inject one failure, recover, and record cleanup. A successful template synthesis is offline evidence; it is not an AWS runtime result.

Recommended order: trace the two dataflows; implement the canonical contract; harden realtime delivery; integrate batch publication; add cloud-owned lifecycle; then connect the dashboard. Use the guided labs for DEA-C01 breadth without adding persistent services to the baseline.

Final self-check:

1. Trace one ESP event through archive, latest state, alert and analytical publication.
2. Explain why realtime depends on core and why the reverse dependency is forbidden.
3. Identify the largest 24x7 cost and the code change that reduces it.
4. Distinguish local, AWS smoke, integrated and rehearsed evidence.
5. Explain what is lost when realtime is parked versus when the core is reset.
6. Name the remaining gate before presenting the project as customer-ready.
