# Changelog

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
