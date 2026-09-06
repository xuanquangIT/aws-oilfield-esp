# Operating time estimate

Reviewed 2026-09-06. This is an operational planning guide for the current implementation. It is not measured AWS evidence yet: CloudFormation time, account quotas, credentials, first deployment, AWS service load and network conditions can change the result. Record actual timestamps in every cloud run and replace these estimates after two successful rehearsals.

## Parked to live demo

Parked means the core stack remains deployed and the disposable realtime stack is absent. The core contains S3, DynamoDB, Lambda functions, Glue, Data Catalog, Athena, Step Functions and the budget. It has no active Kinesis stream, event-source mappings, simulator or scheduled ETL.

| Stage | Expected time | Operator action | Ready condition |
|---|---:|---|---|
| Verify account and core | 30–60 seconds | Confirm AWS profile/region and core stack outputs | Correct account, region and core stack exist |
| Create realtime stack | 2–5 minutes | Run `realtime-start.ps1` | Kinesis stream and both Lambda mappings are created |
| Warm-up and preflight | 30–60 seconds | Run normal telemetry and inspect latest state | At least one fresh state is visible for each of ESP-101, ESP-102 and ESP-103 |
| Begin customer demo | **3–7 minutes total** | Start the selected scenario | Freshness and alert state are visibly normal |

Use a **10-minute operating slot** from parked state to a presenter-ready realtime demo. It includes a margin for a failed command retry or console inspection, but it is not a substitute for recording measured deployment times.

The current realtime script starts the simulator immediately after CDK reports a successful realtime deployment. It does not independently wait until a first event reaches DynamoDB. The 30-second wait at the end of the script is a **drain grace period before teardown**, not a warm-up check.

```powershell
.\scripts\realtime-start.ps1 -DurationMinutes 5 -Scenario low_flow
```

The script runs the selected scenario for the requested duration, waits 30 seconds, then attempts to destroy the realtime stack in `finally`. Do not start presenting before observing fresh latest-state data.

## Freeze after a demo

| Stage | Expected time | Completion evidence |
|---|---:|---|
| Producer ends and drain grace | 30 seconds | Script enters teardown after its fixed grace period |
| Destroy realtime stack | 2–5 minutes | CloudFormation reports deletion complete |
| Verify parked state | 1–5 minutes | No realtime stack, no Kinesis stream, no event-source mappings, no active Glue/crawler work |
| Operational slot | **5–10 minutes** | Park checklist complete |

Run the recovery command if the demo shell was interrupted:

```powershell
.\scripts\realtime-stop.ps1
```

The project is frozen only after the deletion and absence checks succeed. A closed terminal, expired credentials or an access-denied response does not prove that the stream stopped.

## Rebuild paths

| Starting state | Scope | Planning time | Notes |
|---|---|---:|---|
| Parked core | Realtime customer demo | 3–7 minutes | Preferred demo path; reserve 10 minutes operationally |
| Core absent, synthetic data retained locally | Deploy core only | 10–20 minutes | Includes CloudFormation creation; does not establish batch KPI data |
| Core absent | Core + seed/upload + Glue + crawler + Athena preflight | 30–45 minutes | Glue is capped at 10 minutes and crawler has a 10-minute minimum; use this path before a meeting, not during one |
| Full reset after export | Recreate complete project | 30–45+ minutes | Infrastructure can be recreated, but deleted real data needs explicit restore; synthetic input can be regenerated |

The delivery plan has a future acceptance target of a clean core rebuild within 20 minutes and full preparation within 30 minutes. That target is unmeasured and should not yet be promised to a customer. The current sequential Glue and crawler settings alone reserve up to 20 minutes, so reserve 30–45 minutes until rehearsal evidence proves a faster path.

## Demo scheduling rule

For a customer session, keep core parked before the meeting, activate realtime 10 minutes beforehand, validate fresh state, then run the scenario. Freeze realtime immediately after the evidence window. This preserves the low parked-cost model while avoiding a long live deploy during the presentation.

The local-first dashboard is a required Phase 1 deliverable but has not yet been implemented. It must be started and verified separately once available; do not include it in the current timing claim.

## Evidence to collect

Record these UTC timestamps in the cloud-run record:

1. Realtime deploy command start and CloudFormation completion.
2. First producer record sent.
3. First and p95 latest-state observation for each ESP.
4. Scenario start and final record sent.
5. Teardown request, deletion completion and absence verification.
6. Core deploy start/end, Glue job start/end and crawler start/end for rebuild rehearsals.

After two successful runs, publish the median and p95 timing in this document and use those observed values in the customer demo plan.
