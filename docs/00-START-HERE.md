# Documentation hub

**Goal:** one coherent ESP data product showing batch engineering, streaming reliability, cost control and explainable business outputs.

For the owner: start with [status](../PROJECT-STATUS.md), [delivery plan](11-DELIVERY-PLAN.md) and [cost model](03-COST-CONTROL.md). The most valuable next implementation is a shared telemetry contract and replay-safe ingestion, followed by batch/realtime reconciliation.

## Reading routes

| Audience | Route |
|---|---|
| Builder | Quickstart -> architecture -> data contract -> delivery plan -> operations |
| Customer / interviewer | Portfolio -> architecture -> evidence and acceptance |
| DEA-C01 learner | Mapping -> guided labs -> batch/realtime runbooks -> teach-back |
| Operator | Quickstart -> cost control -> operations -> troubleshooting |

## Index

1. [Quickstart](01-QUICKSTART.md): local checks and explicit AWS steps.
2. [Architecture](02-ARCHITECTURE.md): current implementation and target pipeline.
3. [Cost control](03-COST-CONTROL.md): operating states, guardrails and residual costs.
4. [Realtime](04-REALTIME-DEMO.md): scenarios, expected results, limitations.
5. [Batch](05-BATCH-ANALYTICS.md): existing job, SQL, evolution.
6. [DEA-C01 mapping](06-DEA-C01-MAPPING.md): all 17 task groups.
7. [Operations](07-OPERATIONS.md): start, inspect, park, reset, recover.
8. [Troubleshooting](08-TROUBLESHOOTING.md): symptoms and recovery.
9. [Portfolio](09-PORTFOLIO.md): customer narrative and rehearsal.
10. [Domain notes](10-DOMAIN-NOTES.md): synthetic signal assumptions and units.
11. [Delivery plan](11-DELIVERY-PLAN.md): dependencies, work items, pass criteria.
12. [Data contract](12-DATA-CONTRACT.md): current fields and target v1.
13. [Security](13-SECURITY-GOVERNANCE.md): access matrix, audit, privacy.
14. [Acceptance](14-ACCEPTANCE-EVIDENCE.md): measurable gates and evidence.
15. [Learning labs](15-LEARNING-LABS.md): build, break, recover, explain, clean.
16. [Sources](16-SOURCES.md): official references reviewed on 2026-09-05.
17. [Realtime web dashboard](17-REALTIME-WEB-DASHBOARD.md): required Phase 1 local dashboard and optional hosted profile.
18. [Monthly cost estimate](18-MONTHLY-COST-ESTIMATE.md): frozen, intermittent, daily and continuous scenarios.
19. [Operating time estimate](19-OPERATING-TIME-ESTIMATE.md): parked-to-demo, warm-up, freeze and rebuild timings.
20. [Build it yourself](20-BUILD-IT-YOURSELF.md): reconstruct the project layer by layer and prove each decision.
21. [Decisions](adr/README.md): choices and their consequences.

Documents are English for reuse with customers and contributors. Operational commands target Windows PowerShell. Use links from this hub rather than copying isolated commands without their preconditions.
