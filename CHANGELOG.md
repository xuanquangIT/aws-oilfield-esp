# Changelog

## Unreleased — 2026-09-06

- Added a reproducible us-east-1 gross-cost calculator and a researched monthly estimate for frozen, intermittent, daily-demo, continuous and alert-storm operation.
- Added an operating-time estimate for parked-to-demo start, warm-up, freeze and full rebuild paths; all timings remain unmeasured until cloud rehearsals complete.
- Added a build-it-yourself learning path that treats the current implementation as an answer key and teaches each batch, realtime, reliability, cost and dashboard layer separately.
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
