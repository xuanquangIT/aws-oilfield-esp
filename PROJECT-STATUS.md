# Project status

Reviewed: 2026-09-06. This file is the implementation ledger; the delivery plan describes future work.

| Area | Implemented now | Outstanding / proof required |
|---|---|---|
| Infrastructure | Core + disposable Kinesis; actual Lambda references; stream IAM owned by realtime | AWS create/delete/recreate smoke, permissions and service compatibility |
| Idle cost | One shard only during demos; no ETL schedule; application logs expire after 7 days; Glue concurrency 1 / 10-minute timeout; reproducible gross-cost model | Cloud watchdog, runtime drain reconciliation, measured bill, service-created log retention |
| Budget | Account-wide USD 5 monthly budget; optional actual-spend emails at 50/100% | Supply email on each core deploy; verify delivery; never a hard cap |
| Batch | 504-row synthetic CSV -> Glue Spark -> partitioned Parquet; wrapper waits then runs crawler | Realtime union, quarantine, incremental/backfill, atomic publication, stable catalog |
| Realtime | Three pumps, two Lambda consumers; S3 history, latest state, threshold SNS; bounded retry and S3 failure destination | Validation, event identity, idempotency, event-time ordering, cooldown, replay tool |
| Operations | Checked native exit codes; root-relative paths; local dependency locks; finally cleanup; explicit data-delete switch | Cloud-side workflow completion and cleanup verification; client-independent expiry |
| Security | S3 private / TLS / SSE-S3; workload roles; no embedded credentials | Prefix-level IAM refinement; negative access tests; governance and audit evidence |
| Learning | All 17 DEA-C01 task groups mapped to project exercises or extension labs | Completing the matrix is not the same as passing the exam or implementing all skills |
| Customer demo | Storyboard, Phase 1 local-first dashboard design, optional hosted profile, acceptance targets, evidence schema, SQL, architecture and risks | Local dashboard code, integrated KPI report, successful live rehearsal, controlled recovery and recorded incremental usage |
| Validation | See [latest local report](evidence/LOCAL-VALIDATION.md) | Local success is not AWS integration proof |

## Findings addressed in this revision

1. Realtime guessed physical Lambda names; wiring now uses CDK references and stream-specific policies live in realtime to prevent dependency cycles.
2. Native process failures could pass unnoticed in PowerShell; shared helpers check exit codes.
3. Realtime needed manual teardown; the wrapper now attempts teardown on success or failure. Process termination or laptop loss can still bypass it.
4. Kinesis was on-demand for a three-event/second lab; default is now one provisioned shard.
5. Batch command returned before completion and required a manual crawler; wrapper now waits and checks both results. This is still client-side orchestration.
6. Full reset silently deleted data and hid a teardown error; reset now requires -DeleteData and stops on failure.
7. Long-lived Lambda logs and implicit Glue retries/concurrency lacked bounds; explicit controls added.
8. Documentation contained unresolved citation tokens and service-name-only exam mapping; replaced with source links and an evidence-based plan.
9. Core resource/output shared the AthenaWorkGroup construct ID and synthesis failed; output construct renamed while preserving the CloudFormation output key.

## Release gates

- Foundation: offline checks pass, commands are documented, limitations are explicit.
- Phase 1 complete product: M1-M5 in the [delivery plan](docs/11-DELIVERY-PLAN.md) pass, including the local web dashboard.
- Customer rehearsal: Phase 1 passes twice, including dashboard startup, teardown and reconstruction.
- Exam coverage: M6 exercises completed and explained; no inferred percentage of exam readiness.

Do not mark a planned capability as implemented without its code, negative test and evidence.
