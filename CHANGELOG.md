# Changelog

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
