# Offshore ESP Data Platform

A cost-aware AWS data engineering capstone for synthetic electric submersible pump (ESP) surveillance. The business story connects operational fault visibility with historical production analysis.

**Status: foundation hardened; the Phase 1 complete-product scope now includes a local-first realtime web dashboard, with implementation gates still open.** No AWS deployment, dashboard implementation, real Glue run, billing result or end-to-end cloud evidence is claimed. See [project status](PROJECT-STATUS.md).

## Start here

| Intent | Read / run |
|---|---|
| Understand the product and navigate | [Documentation hub](docs/00-START-HERE.md) |
| Install and validate without AWS | [Quickstart](docs/01-QUICKSTART.md) |
| Understand current and target architecture | [Architecture](docs/02-ARCHITECTURE.md) |
| Control spend and downtime | [Cost control](docs/03-COST-CONTROL.md) |
| Compare monthly operating scenarios | [Monthly cost estimate](docs/18-MONTHLY-COST-ESTIMATE.md) |
| Plan demo start and freeze time | [Operating time estimate](docs/19-OPERATING-TIME-ESTIMATE.md) |
| Learn by rebuilding each layer | [Build it yourself](docs/20-BUILD-IT-YOURSELF.md) |
| Implement the next milestone | [Delivery plan](docs/11-DELIVERY-PLAN.md) |
| Prepare a customer demonstration | [Demo and portfolio](docs/09-PORTFOLIO.md) |
| Track AWS DEA-C01 learning | [Coverage matrix](docs/06-DEA-C01-MAPPING.md) |

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
docs/                 architecture, runbooks, plan, sources, learning
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
