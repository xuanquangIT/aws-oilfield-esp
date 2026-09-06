# Offshore ESP Data Platform

A cost-aware AWS data engineering capstone for synthetic electric submersible pump (ESP) surveillance. The business story connects operational fault visibility with historical production analysis.

**Scope: this repository will implement the complete batch-and-realtime data product from ingestion through consumer use.** Current status is foundation only: no AWS deployment, dashboard implementation, real Glue run, billing result or end-to-end cloud evidence is claimed. See [project status](PROJECT-STATUS.md).

## Phase 1 scope commitment

```text
Historical CSV + realtime ESP events
  -> validate and normalize
  -> raw archive or quarantine
  -> canonical silver and daily gold KPIs
  -> catalog and Athena query
  -> approved KPI publication
  -> local read API and realtime customer dashboard
```

Both sources must reconcile into the published analytical result. The dashboard consumes latest operational state from DynamoDB and the approved KPI publication from S3; it is not a mock or a separate data store. The hosted CloudFront/API Gateway/Cognito profile remains optional because the local-first dashboard completes the required consumer flow with no new fixed AWS cost.

## Start here

| Intent | Read / run |
|---|---|
| Understand the product and navigate | [Documentation hub](docs/00-START-HERE.md) |
| Install, validate and deploy | [Getting started](docs/01-GETTING-STARTED.md) |
| Understand current and target architecture | [Architecture](docs/02-ARCHITECTURE.md) |
| Understand telemetry and domain scope | [Data domain and contract](docs/03-DATA-DOMAIN-AND-CONTRACT.md) |
| Run, park, recover and troubleshoot | [Operations](docs/04-OPERATIONS.md) |
| Control cost, access and governance | [Cost and security](docs/05-COST-AND-SECURITY.md) |
| Implement milestones and study DEA-C01 | [Delivery and learning](docs/06-DELIVERY-AND-LEARNING.md) |
| Build and present the dashboard | [Demo and dashboard](docs/07-DEMO-AND-DASHBOARD.md) |

## Operating model

- **Local:** tests and template synthesis; no AWS calls or deployment required.
- **Parked:** core resources and small datasets remain; no Kinesis, no scheduled ETL.
- **Demo:** add a one-shard Kinesis stream and two consumers; run a bounded scenario; remove realtime in a finally block.
- **Dashboard demo:** run the web UI and read API on localhost only; use existing DynamoDB/S3 data; stop the local process afterward.
- **Reset:** export what matters, then explicitly delete project data and both stacks. Shared bootstrap resources need separate accounting.

Near-zero idle spend is a design objective, not a guaranteed zero bill. A budget is an alert, not a spending cap.

Current gross planning estimates in `us-east-1` are approximately **$0.03/month parked**, **$0.66–$0.97/month for two or three controlled demos**, **$9.46/month for one complete demo each day**, and **$67.90/month for continuous streaming plus daily batch**. Credits and shared free-tier allowances are excluded; use measured billing to replace modeled values.

## Workspace map

```text
docs/                 eight primary guides plus architecture decisions
docs/adr/             architectural decisions and trade-offs
infrastructure/       two AWS CDK stacks
src/                  deployed stream, anomaly and Glue code
simulator/            synthetic realtime producer
scripts/              checked PowerShell lifecycle commands
sql/                  current Athena analytics
tests/                offline behavioral and template checks
data/                 generated synthetic input; not customer data
evidence/             validation report and cloud evidence template
.github/workflows/    offline CI; no AWS deployment
```

Use the project virtual environment and pinned local CDK CLI. The existing directory was not a Git repository at review time; CI becomes active only after you put it in a repository and enable Actions.

Synthetic telemetry and simplified rules support a cloud engineering demonstration. They do not establish equipment diagnostic accuracy or suitability for offshore control.
