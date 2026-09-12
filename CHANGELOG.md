# Changelog

## Unreleased — 2026-09-12 (M4 AWS partial acceptance)

- Started an independent Step Functions execution against a frozen M3 manifest and verified cloud-owned completion end-to-end: Glue succeeded, then the workflow started/polled the crawler to a fresh `READY`/`SUCCEEDED` crawl, with no client-side crawler operation.
- Deployed M4 core controls and verified the five G4 workload-role denial cases with `iam:SimulatePrincipalPolicy`; every prohibited action returned `implicitDeny`.
- Ran a normal one-minute realtime scenario: the M4 drain receipt reconciled 180 acknowledged producer events to 180 raw S3 objects, with no quarantine or missing events. The realtime stack was then removed and Kinesis was empty.
- Proved client-independent expiry with a separate no-producer realtime stack: a one-shot Scheduler target invoked `ExpiryReaper` at `2026-09-12T08:38:13Z`; its CloudWatch log recorded `outcome: deleted` at `08:38:47Z`, and the stack/schedule were absent afterward. Final scoped inventory found core only, no Kinesis/schedules, and 1,928,217 retained S3 bytes. Export/reset/recreate/restore remains a deliberately unrun destructive acceptance drill.

## Unreleased — 2026-09-12 (M4 local implementation; AWS acceptance pending)

- Moved batch completion into Step Functions: Glue, crawler start, fresh-crawl polling and terminal outcome are cloud-owned; the PowerShell command only launches/observes. Retry is limited to transient Glue/time-out failures and overlapping publish runs fail explicitly.
- Added the disposable-runtime expiry lease and drain gate. `realtime-start.ps1` creates an EventBridge Scheduler one-shot before deployment; the reaper is restricted to `DescribeStacks`/`DeleteStack` on the one realtime stack and rejects wrong-stack payloads. The producer writes acknowledged-event ledgers; teardown saves a bounded raw/quarantine reconciliation receipt and labels incomplete runs without blocking cost-protecting teardown.
- Added read-only G4 IAM denial simulation (five workload-role cases), checksum-bound S3/DynamoDB export plus confirmation-gated restore tooling, and a scoped residual-resource inventory. All are offline-validated; no M4 AWS deployment, expiry invocation, IAM simulation, or restore drill has been claimed yet.

## Unreleased — 2026-09-12 (M3 AWS acceptance)

- Verified all five M3 exit-gate criteria in AWS. Mixed sources: a corrected run's quality report showed `historical_silver_rows=72` and `realtime_silver_rows=180` together with `quality_passed=true`. Accounting: `unexplained_rows=0` (`accounted_rows == input_rows`, 684) on every passing run. Deterministic rerun: replaying the same frozen manifest in a second independent Glue run produced an identical `canonical_data_sha256`. Backfill isolation: a backfill run for an unrelated day (2026-09-13) left the previously published day's Parquet object's S3 ETag and size byte-for-byte unchanged, writing its own new immutable `publication_run_id` partition instead. Partition pruning: an Athena query against the crawled `silver` table scanned 7,351 bytes unfiltered versus 632 bytes filtered by `event_date` (~91% less), per `aws athena get-query-execution`'s `Statistics.DataScannedInBytes`. Republished a final run spanning both dates (325 silver rows, 6 gold rows) as the current approved pointer. Documented in `docs/09-RUNBOOK.md` section 6.7.

## Unreleased — 2026-09-12 (M3 live fixes)

- Fixed historical CSV projection in Glue: optional realtime-only fields are now added as typed nulls by header name rather than shifting all later CSV fields by position. M3 quality publication also requires accepted silver rows from both `historical_csv` and `realtime_json`; a one-source run cannot advance the approved pointer.
- Fixed overlapping CDK S3 deployment prefixes: one deployment owns `scripts/`, preserving `scripts/contract.py` for Glue `--extra-py-files` instead of pruning it after upload.

## Unreleased — 2026-09-12 (M3 local implementation)

- Implemented the M3 analytical path in code: `scripts/create-m3-manifest.py` freezes selected raw S3 objects with byte SHA-256 checksums; `scripts/run-batch.ps1` creates an independent publication run ID and passes the manifest to Glue; `src/batch/transform.py` unions/revalidates historical CSV and archived realtime JSON, joins `pump_metadata_v1.csv`, deduplicates exact event redeliveries, rejects conflicting event IDs, and emits silver, gold and a data-quality report.
- M3 writes immutable staging data under `staging/m3/<run-id>/`, then final run partitions under `curated/silver/` and `curated/gold/`; only a passing quality gate updates `curated/publication/current.json`. A failed run leaves the previous pointer unchanged. The source window is parameterized by start/end UTC date and late-arrival lookback.
- Added pure offline tests for manifest determinism, duplicate redelivery, conflicting event IDs and invalid-record accounting. Updated CDK to package the shared validator for Glue, pass run/manifest values through Step Functions and crawl the M3 silver prefix.
- Updated the M1/M2/M3 runbooks, operations guide, ADR and SQL templates so they no longer describe M2 as planned or M3 as a CSV overwrite. M3 AWS acceptance has **not** yet run: mixed-source reconciliation, same-manifest rerun, isolated backfill and Athena partition-pruning bytes remain required evidence.

## Unreleased — 2026-09-07 (M2)

- Implemented M2 (reliable streaming) per `docs/06-DELIVERY-AND-LEARNING.md`:
    - `src/stream_processor/handler.py`: DynamoDB latest-state writes are now conditional on `timestamp` (accepts a strictly newer event only; an exact tie is first-writer-wins), so late-arriving or duplicate-delivered records can never regress or duplicate state. Measurements are stored as DynamoDB Number types (`Decimal`) instead of strings. The raw history object key is now the event's own `event_id` (stable replay identity) instead of the Kinesis sequence number (transport metadata), so replaying/redelivering the same event is an idempotent overwrite.
    - `src/anomaly_detector/handler.py`: rewritten around a per-(esp_id, rule_id) cooldown/recovery outbox in a new `AlertState` DynamoDB table, with deterministic alert IDs (`uuid5`) so a downstream subscriber can dedupe a possible duplicate send. SNS is published before the state row is recorded, so a crash between the two can at most duplicate an alert, never silently drop one. Fixes the alert-storm behavior that sent 159 emails in one `low_flow` demo; a sustained anomaly now sends exactly one trigger alert per episode plus one recovery alert when it clears.
    - `simulator/esp_simulator.py`: each Kinesis `put_record` is retried with bounded exponential backoff and jitter on a transient/throttling failure, always resending the same event (`event_id` is never regenerated on retry). A send that exhausts all retries is appended to `data/producer-failures.jsonl` instead of crashing the run; the run prints an acknowledged/failed summary.
    - Added `scripts/replay-failed.py`: downloads a Kinesis on-failure-destination S3 pointer object, re-fetches the failed records from Kinesis by sequence number, and replays them through the exact same `process_record` logic as the live Lambda (dry-run by default; `--execute` to apply), writing a JSON replay receipt.
    - `infrastructure/core_stack.py`: added the `AlertState` DynamoDB table (partition key `esp_id`, sort key `rule_id`); `AnomalyDetector` is now bundled from `src/` (not `src/anomaly_detector/`) so it can share `contract.py`, matching `StreamProcessor`'s M1 bundling.
    - Added `tests/test_stream_processor.py` and `tests/test_anomaly_detector.py`: offline exit-gate tests using hand-rolled S3/DynamoDB/SNS fakes (no AWS calls) proving monotonic state, no-event-disappears accounting against the `duplicate`/`late` fixtures, and the cooldown/recovery regression (50 consecutive anomalies -> 1 alert).
    - Historical+realtime union into silver/gold remains explicitly out of scope until M3.
- Verified M2 end-to-end in AWS: redeployed `oilfield-esp-core` (new `AlertState` table, rebundled `AnomalyDetector`) and the realtime stack standalone. Conditional state: sent a newer-timestamp `ESP-101` record (accepted, numeric fields confirmed as DynamoDB `N` type), then an older-timestamp record for the same pump (rejected by the `ConditionExpression`, `LatestState` unchanged), with both events preserved as distinct `event_id`-keyed objects under `raw/realtime/`. Alert cooldown: ran the `low_flow` scenario for 2 minutes (360 records across 3 pumps); `AlertState` recorded exactly 4 episodes (3 active, 1 recovered) and CloudWatch's `AWS/SNS NumberOfMessagesPublished` metric showed exactly 5 messages, versus 159 emails for a comparable pre-M2 run. Test artifacts cleaned up from `LatestState`/`AlertState`/S3 afterward; realtime stack destroyed; parked-state audit confirmed only `oilfield-esp-core` + `CDKToolkit` remain, no Kinesis streams, `DailySchedule` disabled. Documented in `docs/09-RUNBOOK.md` section 6.6.

## Unreleased — 2026-09-07

- Fixed `AWS::Glue::Job BatchJob` failing to deploy ("Script location cannot be null or empty") by replacing raw dicts with typed `glue.CfnJob.JobCommandProperty`/`ExecutionPropertyProperty` structs in `infrastructure/core_stack.py`.
- Fixed `AWS::Lambda::EventSourceMapping` failing to deploy in the realtime stack (missing `s3:PutObject`) by widening the on-failure-destination IAM grant to the whole data bucket in `infrastructure/realtime_stack.py`.
- Added `docs/09-RUNBOOK.md`: a single linear command reference for deploy/run/verify/park/destroy across every realtime scenario, plus a cost-and-idle-safety audit checklist.
- Implemented M1 contract and fixtures: added `src/contract.py` as the single schema-v1 validator shared by the producer (simulator), the historical seed generator and the realtime ingest transformation.
- `simulator/esp_simulator.py` and `scripts/seed-batch-data.py` now take `--seed`/`--start-time` for fully deterministic, reproducible output, and emit the schema v1 envelope (`schema_version`, `event_id`, `source`, `run_id`).
- `src/stream_processor/handler.py` now validates every record before it can reach raw history or DynamoDB latest state; rejected records are quarantined under `quarantine/realtime/<rule_id>/...` with rule ID and reason, never silently dropped or promoted.
- `src/batch/transform.py` Glue schema updated to match the new CSV envelope columns.
- Added `tests/fixtures/telemetry_v1.json` (valid, null, malformed, incompatible-version, duplicate, late) and `tests/test_contract.py`; duplicate/late fixtures document the explicit M1/M2 boundary (structurally valid now, identity-based conflict handling is M2).
- Numeric DynamoDB typing, conditional latest-state updates, alert dedupe/cooldown and the historical/realtime union remain explicitly out of scope until M2/M3.
- Verified M1 end-to-end in AWS: redeployed `oilfield-esp-core` (updated `StreamProcessor` code asset and Glue script), reran the batch pipeline (504/504 rows, 0 quality errors, 504 distinct `event_id`s, `schema_version=1` confirmed via Athena), and ran a manual Kinesis quarantine smoke test against a disposable realtime stack: three deliberately invalid records (`MALFORMED_PAYLOAD`, `UNKNOWN_ESP_ID`, `OUT_OF_RANGE`) landed under `quarantine/realtime/<rule_id>/...` and never reached `raw/realtime/` or the `LatestState` table, while one valid record reached both. Documented the smoke-test procedure in `docs/09-RUNBOOK.md` section 6.5.

## Unreleased — 2026-09-06

- Consolidated 21 overlapping topic files into eight primary guides with one source of truth for setup, data, operations, cost/security, delivery/learning, dashboard/demo and references.
- Retained the full M1–M5 plan, DEA-C01 coverage, acceptance gates, cost/time models and synthetic equipment provenance while removing repeated navigation and explanations.
- Declared the complete ingest-to-consumer flow as committed Phase 1 scope: both sources, validation, raw/quarantine, silver/gold, publication, Athena and the local dashboard.
- Added a reproducible us-east-1 gross-cost calculator covering frozen, intermittent, daily-demo, continuous and alert-storm operation.
- Identified per-event S3 PUTs and per-event SNS alerts as the main continuous-runtime cost risks; documented batching and notification cooldown priorities.
- Made a local-first realtime web dashboard a required Phase 1 deliverable rather than a later hosted-only release item.
- Defined a localhost read API, shared 10–15 second cache, batched latest-state reads, version-based KPI fetch and stale/unavailable behavior.
- Moved CloudFront/API Gateway/Cognito/Dashboard Lambda to an optional on-demand hosted profile outside the parked-cost baseline.
- Updated architecture, cost, security, portfolio, acceptance and run-evidence documents; dashboard implementation remains outstanding.

## 0.2.0 — 2026-09-05

- Reworked navigation, current-state architecture, target design, cost model, all 17 DEA-C01 task groups and guided learning labs.
- Added delivery milestones, data contract, security matrix, customer storyboard, ADRs and acceptance/evidence templates.
- Fixed realtime Lambda wiring with one-way stack dependencies; switched the tiny demo to one provisioned shard.
- Fixed the existing duplicate Athena construct ID that prevented template synthesis.
- Added retry/age limits and S3 failed-invocation destination, application log expiry, Glue concurrency/retry bounds and optional budget emails.
- Reworked lifecycle scripts with checked native failures, project-root resolution, local Python/CDK, finally cleanup and explicit full-data reset switch.
- Batch wrapper now waits for ETL and runs/checks the crawler.
- Added dependency locks, offline infrastructure/script validation, SQL checks and CI scaffolding.
- Integrated contract, replay-safe ingestion, unified batch publication and cloud expiry remain planned. No AWS deployment was performed for this revision.
