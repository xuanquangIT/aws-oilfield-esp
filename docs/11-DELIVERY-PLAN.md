# Delivery plan

## Scope and priorities

One coherent Phase 1 product: synthetic ESP ingestion -> trustworthy operational state -> reconciled historical KPIs -> local realtime web dashboard -> reproducible customer evidence. Minimize idle cost and operator effort before adding more services.

The current revision delivers documentation/workspace organization and foundation fixes. The milestones below are the implementation backlog, not a claim that the finished platform already exists. Estimates are planning ranges for one developer, excluding environment access delays.

## Milestones

| Milestone | Dependency / effort | Work and exit gate |
|---|---|---|
| M0 Foundation | Current revision | Offline tests + synth, actual stack wiring, checked lifecycle scripts, cost/source review, honest status ledger |
| M1 Contract and fixtures | M0 / 1-2 days | Versioned schema, deterministic seed/run IDs, shared validation, typed units, pump metadata; fixtures for valid, null, malformed, duplicate, late and incompatible versions |
| M2 Reliable streaming | M1 / 2-3 days | Stable event IDs, conditional latest state, failure/quarantine separation, alert cooldown/history, bounded producer retry, replay command; behavioral tests show no backward state or duplicate side effects |
| M3 Integrated batch | M1 + M2 raw contract / 3-4 days | CSV/JSON union, pump join, DQ + dedupe, run-scoped output, stable catalog, date backfill, gold KPI SQL; counts and rerun results reconcile |
| M4 Operations/security | M2 + M3 / 2-3 days | Cloud batch completion, scoped retry/catch, publish gate, expiry lease, drain/lock, least privilege, alarms, restore/deny drills and residual cost inventory |
| M5 Dashboard and customer release | UI scaffold alongside M1-M4; final integration after M4 / 2-3 days | Localhost web dashboard + local read API, latest-state and KPI views, redacted evidence, two clean rehearsals, recreate test, measured freshness/incremental usage, customer recording |
| M6 Exam extensions | Alongside, isolated / 3-5 days | DEA task exercises for CDC/warehouse/windows/governance/Iceberg and study-only modern data/AI topics |

Phase 1 is M0-M5 and is not complete without the dashboard. UI layout, fixture mode and local API contract can be built alongside M1-M4; live integration and release evidence remain gated by M2-M4. M6 enriches exam breadth but must not add persistent baseline infrastructure.

## M1: data quality is an interface

Implement the [contract](12-DATA-CONTRACT.md), with one validator used by the producer fixtures and ingest transformations. Preserve raw bytes before normalization where feasible. Use explicit rule IDs and reason codes. Seed generation takes --seed and --start-time so a fixture checksum is repeatable.

Exit: all expected-valid rows pass; all deliberately invalid rows are rejected for the right reason; optional additions are backward-compatible; invalid versions cannot silently enter silver. Commit synthetic fixtures only.

## M2: streaming correctness before visual polish

Use event_id for replay identity and source sequence only as transport metadata. A conditional DynamoDB update accepts a newer event timestamp; late valid records remain in history. Define equal-time conflict behavior. Store numbers as numbers.

An alert history/outbox design must handle a crash between dedupe persistence and SNS publish. Do not claim exactly-once SNS delivery; use deterministic alert IDs so downstream consumers can deduplicate. Cooldown is per pump/rule, with recovery state. Partition by pump to keep relevant order.

Producer retries transient/throttle failures with bounded exponential backoff, preserves event IDs, and records acknowledged/failed sends. Consumer tests inject an S3/DynamoDB/SNS failure and verify recovery. Replay tool validates an S3 failure payload, supports dry-run and records a replay receipt.

Exit: duplicate, late and invalid fixtures have expected counts; state is monotonic; no event disappears without accepted/rejected/failed accounting; alert behavior is explained. Low-flow detection uses measurements. Gas-slug/stuck-sensor temporal detection can remain explicitly deferred.

## M3: one analytical pipeline

Use the same schema for historical and realtime records. Join small versioned pump metadata. Write staging output per run; derive row counts and data-quality report before publishing an approved catalog location. A failed run must leave the prior published dataset queryable.

Choose immutable run output for this single-writer capstone. Do not use append without dedupe or wholesale overwrite for incremental workloads. Record input manifest/checksums, schema/rules version and output path. Parameterize date range and late-arrival lookback.

Exit: batch and realtime events appear together; input accounting balances; rerunning the same manifest yields the same canonical results; one-day backfill does not change unrelated days; SQL demonstrates partition pruning with actual bytes scanned.

## M4: survive operator absence

Move crawler/catalog/publication completion into Step Functions; keep CLI as launcher/observer. Use bounded retries only for transient errors and explicit failure state with diagnostic output. Prevent overlapping publish runs.

Create an independent one-shot expiry workflow before stream use; lease includes stack identity, region, expiry and run owner. Delete only realtime. Verify DELETE_COMPLETE and alert if denied or stuck. A laptop-disconnection test must leave no running stream past the agreed deadline. Do not grant broad administrator cleanup permissions.

Drain gate compares acknowledged producer event IDs to archived accepted/invalid records and consumer outcomes before normal deletion. Timeout reports incomplete delivery; it must not silently mark a run successful. Expiry cleanup may sacrifice unprocessed records to stop spend, so save producer fixtures and label incomplete runs.

Complete [security tests](13-SECURITY-GOVERNANCE.md), export/restore drill, CloudTrail/log evidence and service-created log-retention policy. Estimate any additional monitoring/expiry costs.

## M5: Phase 1 dashboard and customer release

Implement the [dashboard design](17-REALTIME-WEB-DASHBOARD.md) as part of Phase 1. Deliver a responsive single-page web UI and small local read API. The service binds to `127.0.0.1` by default and uses the operator's existing AWS credential chain on the server side; credentials never enter HTML or JavaScript.

The local API performs a batched read of the known ESP IDs from DynamoDB and maintains a 10–15 second cache shared by all local browser tabs. It fetches approved KPI JSON from S3 only when the publication identifier changes or on explicit refresh. It never runs Athena per poll, scans DynamoDB, reads raw/failure prefixes, or listens on the LAN by default.

The UI shows pump status, data age, last observation time, active synthetic alert severity, flow/temperature/current, and batch KPI/quality timestamp. It visibly shows `Synthetic data`, `Local demo`, `Last refreshed`, `Data age`, and the published batch run ID. API failure keeps the last value only with an explicit stale state, then becomes unavailable after the configured threshold.

Build the UI shell and fixture mode alongside M1-M4. Connect live DynamoDB after M2 and approved KPI JSON after M3. Complete security, cleanup, failure and cost evidence after M4. The optional CloudFront/API Gateway/Cognito/Lambda hosted profile is a later deployment option and is not a Phase 1 pass requirement.

Exit: the local dashboard starts with one command, opens from localhost, never exposes credentials, returns only allow-listed fields, shows normal and low-flow state within the measured target, handles stale/error state, consumes the verified published KPI run, stops cleanly, and passes two complete demo rehearsals. A 60-minute run records cache behavior, DynamoDB/S3 requests and incremental usage. Dashboard evidence cannot replace M1-M4 reconciliation evidence.

### M5 release evidence

Target p95 freshness <=15 seconds at the small demo rate; clean core rebuild <=20 minutes and full preparation <=30 minutes, measured rather than promised. Run normal and faulty scenarios, recovery, integrated batch, report generation, park and rebuild twice. Record cost later when AWS billing data becomes available.

Do not block a supervised internal demo on the optional M6 service labs. Do block a customer-ready claim on missing reconciliation, cleanup or unsupported KPI claims.

## Change control

Maintain PROJECT-STATUS.md, CHANGELOG.md, acceptance evidence and the appropriate ADR together. One backlog item should include problem, implementation scope, negative test, cleanup and artifact. Avoid renaming working folders solely for appearance. Keep secrets, generated datasets and unredacted run records outside version control.
