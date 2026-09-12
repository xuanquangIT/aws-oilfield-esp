# Operations runbook

This is the single operator guide for batch, realtime, parking, reset, recovery, timing and troubleshooting. Commands target Windows PowerShell and the current implementation.

## Safe operation and resource inspection

### Before a run

Select profile/region, verify STS identity and read PROJECT-STATUS.md. Check core stack outputs. Ensure no other operator is using the same prefix. Confirm available spend allowance and subscribed alert destination.

Run validate.ps1 after code changes. Review CDK diff before deployment. The scripts use --require-approval never because their resource changes must be reviewed before invoking them.

### Inspect current resources

```powershell
. ./scripts/common.ps1
Invoke-Checked aws @('cloudformation','describe-stacks','--stack-name',"$script:ProjectPrefix-core")
Invoke-Checked aws @('cloudformation','describe-stacks','--stack-name',"$script:ProjectPrefix-realtime")
```

The realtime query failing with a specific stack-not-found error can be expected when parked. Authentication, permissions or network failures do not prove absence.

Use stack Resources/Outputs in CloudFormation to locate the generated names for Lambda, bucket, DynamoDB, crawler, state machine and workgroup. Avoid reconstructing physical names.

### Optional SNS email

```powershell
. ./scripts/common.ps1
$topic = Get-CoreOutput 'AlertTopicArn'
Invoke-Checked aws @('sns','subscribe','--topic-arn',$topic,'--protocol','email','--notification-endpoint','your-real-email-address')
```

Replace the placeholder and confirm the email. This subscription is a manual post-deploy step and must be recreated after a full reset. Budget email is separately passed to deploy-core.ps1.

### Park and verify

1. Run realtime-stop.ps1; require successful completion.
2. Verify realtime CloudFormation stack deletion and Kinesis stream absence in the selected region.
3. Verify no Kinesis event mappings remain attached to the two application functions.
4. Inspect the Glue job for RUNNING/STARTING/STOPPING runs and the state machine for running executions.
5. Inspect crawler activity and any manual Athena queries or interactive sessions.
6. Confirm the daily EventBridge rule remains disabled.
7. Record residual storage and review billing when data arrives.

Stopping a Step Functions execution is not evidence that every downstream resource stopped. Inspect Glue directly and stop a running job if necessary. Avoid automatically restarting failed batches until the cause is understood.

### Reset and restore

Create a checksum-bound export before destructive reset. It exports every current object in the selected project bucket and raw DynamoDB AttributeValue maps for both state tables; it makes no AWS writes. Keep the export outside version control and protect it like the data it contains.

```powershell
. .\scripts\common.ps1
$bucket = Get-CoreOutput 'DataBucketName'
$state = Get-CoreOutput 'StateTableName'
$alerts = Get-CoreOutput 'AlertStateTableName'
.\.venv\Scripts\python.exe scripts\export-core-data.py --bucket $bucket --table $state --table $alerts --destination data/exports/<utc-run-id>
```

After recreating the core stack, restore only a verified export to the newly-created bucket. Physical DynamoDB names change after reset, so map each name recorded in `manifest.json` to its newly-created target table. This writes objects and `PutItem`s, so it requires an explicit confirmation and may overwrite matching keys/items:

```powershell
.\.venv\Scripts\python.exe scripts\restore-core-data.py --export-dir data/exports/<utc-run-id> --bucket <new-bucket> --table-map '<exported-state>=<new-state>' --table-map '<exported-alert-state>=<new-alert-state>' --confirm-restore
```

Current latest state can also be rebuilt only after replay tooling exists. Save SQL results and redact account IDs in shareable evidence.

Run destroy-all.ps1 -DeleteData. The bucket uses auto-delete and the table uses DESTROY; bypassing this wrapper with direct CDK destroy can also erase data.

Afterward inspect shared CDKToolkit assets/ECR and Glue/provider-created log groups. Do not delete shared bootstrap infrastructure used by other projects. Record any residual resources instead of reporting an account-wide zero footprint.

Rebuild with the same configuration and lockfiles, then seed/upload the synthetic dataset. Generated physical names may change. Restore real exported data explicitly if needed; IaC restores resources, not deleted content.

### M4 reliability controls (local implementation; live proof pending)

`run-batch.ps1` is now only a Step Functions launcher/observer: the state machine itself runs Glue, starts the crawler, and polls until it is `READY` after a fresh crawl. It has bounded transient-only retry and an explicit overlapping-publish failure.

`realtime-start.ps1` creates an EventBridge Scheduler one-shot expiry before the stream is deployed. The expiry reaper can only inspect/delete the exact realtime CloudFormation stack; it cannot delete the core stack or subordinate resources directly. The normal path waits briefly, runs the ledger-based drain gate, then deletes both the realtime stack and the schedule. A failed drain check is deliberately a loud incomplete receipt, not a teardown blocker; expiry also favors stopping spend over preserving unprocessed events.

The implementation has offline tests and synthesis evidence only. Before claiming M4 complete, run the live acceptance procedure in runbook section 6.8, including a disconnected-client expiry, IAM denial simulation and export/restore on synthetic data. Alarm requirements remain Lambda Errors/Throttles/IteratorAge, failure-destination delivery failures, Glue failures, workflow timeouts and quarantine spikes; scope and cost any paid alarms first.

## Batch analytics

### M3 runnable path (implementation; AWS acceptance not yet run)

The seed generator creates seven days × 24 hourly samples × three pumps = **504 rows**. Pass `--seed` and `--start-time` for a reproducible historical fixture; without them, it uses current UTC time and random flow values.

```powershell
.\.venv\Scripts\python.exe scripts/seed-batch-data.py
.\scripts\upload-batch.ps1
.\scripts\run-batch.ps1
```

`run-batch.ps1` creates a checksum-bound input manifest under `manifests/<manifest-id>/`, starts one Step Functions execution with a unique publication run ID, then observes that execution. The state machine waits for Glue, starts the crawler, and polls for `READY` after a new crawl; the client can disconnect once execution has started. The manifest freezes all selected raw batch files and event-date-selected `raw/realtime/` JSON objects; its SHA-256 is carried into silver, gold and the quality report. Use `-ManifestKey` to execute a new run from an existing manifest and compare the canonical data SHA-256.

Glue runs in UTC, revalidates both inputs through the shared schema-v1 contract, preserves `source_uri`/S3 object time/checksum, joins `pump_metadata_v1.csv`, rejects invalid rows, drops exact redeliveries deterministically and fails closed when one `event_id` has different normalized payloads. It writes per-run staging under `staging/m3/<run-id>/`, then only after its quality gate publishes immutable Parquet partitions under `curated/silver/` and `curated/gold/` and advances `curated/publication/current.json`. A failed run never advances that pointer.

The default date window is the current UTC date plus the preceding six days; `-LateArrivalLookbackDays` widens the reprocessed event-date window (0–30 days). A one-day backfill is a new run with a one-day `-StartDate`/`-EndDate`; it writes a different `publication_run_id` partition and cannot overwrite an earlier run. A wrapper timeout does not cancel AWS jobs. Inspect remote execution before retrying. Concurrent batch sessions are unsupported.

### Query

List catalog tables and obtain the configured workgroup:

```powershell
. ./scripts/common.ps1
$db = Get-CoreOutput 'GlueDatabaseName'
$wg = Get-CoreOutput 'AthenaWorkGroup'
Invoke-Checked aws @('glue','get-tables','--database-name',$db,'--query','TableList[].Name','--output','table')
```

In Athena select that workgroup and database. The crawler targets `curated/silver/`; verify the discovered table name (normally `silver`) before using [daily SQL](../sql/01-daily-kpis.sql) or [quality SQL](../sql/02-quality-checks.sql). Read `curated/publication/current.json` first and filter Athena by its `published_run_id`; raw staging is not approved data. A query failing the 10 MiB workgroup limit is a guardrail event, not a reason to switch to an unrestricted workgroup.

For AWS acceptance, save the quality report and confirm its accounting identity: `input_rows = invalid_rows + out_of_scope_rows + conflict_rows + duplicate_delivery_dropped_rows + silver_rows`, with `unexplained_rows = 0`. Verify historical and realtime source kinds both appear in the manifest, then compare canonical data hashes for a manifest rerun and inspect a one-day backfill without replacing an earlier run partition.

### Analytical interpretation

Average oil_rate is a rate, not daily oil volume. Production volume requires time-weighted integration and a sampling-gap policy. Current hourly synthetic samples support descriptive comparisons only.

### M3 acceptance still required on AWS

The implementation is covered by pure offline contract tests and CDK synthesis only. Before marking M3 AWS-verified, run a bounded mixed-source scenario and retain a private run receipt with the manifest, quality report, publication pointer, Glue/crawler IDs, Athena result IDs and bytes scanned. The acceptance checks are: both source kinds appear, `unexplained_rows=0`, a fresh run of the same manifest has the same `canonical_data_sha256`, a one-day backfill leaves earlier run partitions unchanged, and an `event_date`-filtered Athena query scans fewer bytes than its unfiltered counterpart. Iceberg MERGE/time travel remains an optional M6 lab.

## Realtime demonstration

Prerequisites: deploy core, select the same AWS profile/region for CLI and Boto3, optionally confirm the SNS email subscription. Keep another console window open for DynamoDB and CloudWatch.

```powershell
.\scripts\realtime-start.ps1 -DurationMinutes 5 -Scenario low_flow
```

The wrapper creates the stream and both mappings, runs three synthetic pumps, allows a 30-second grace period, then destroys realtime. Core history, state, alerts topic and application logs remain.

| Scenario | What the current generator does | Expected current rule behavior |
|---|---|---|
| normal | Stable noisy signals | No anomaly publish |
| low_flow | Flow below 60, motor temperature above 120 | Warning |
| mechanical | Vibration and current grow with tick | Warning only after thresholds are crossed; use five minutes |
| blockage | High tubing pressure plus low flow/heat | Multiple rule reasons, critical |
| gas_slug | Oscillating pressure/flow | Label-based alert; not measured temporal detection |
| sensor_fault | Temperature fixed at 91 | No stuck-sensor detector exists yet |
| shutdown | Zero flow/current/frequency, SHUTDOWN status | Critical by current rule; planned shutdown context absent |

Thresholds use synthetic units described in [domain notes](03-DATA-DOMAIN-AND-CONTRACT.md). The scenario label currently leaks into the gas-slug rule. Customer evidence must identify this as a scripted demonstration.

### Observe

1. Confirm both event source mappings are enabled before interpreting missing output.
2. Inspect latest-state items for ESP-101/102/103 and compare their timestamp to current run.
3. Inspect raw/realtime objects and application logs.
4. For low_flow, inspect a confirmed SNS notification; unconfirmed email is not a delivery test.
5. Inspect aws/lambda failure payloads if errors occurred.
6. Verify the stream and mappings are gone after the command ends.

Raw objects and DynamoDB items do not prove every producer event arrived. M2 stores latest-state measurements as DynamoDB Numbers, accepts only a strictly newer timestamp (equal timestamps are first-writer-wins), and applies per-pump/rule alert cooldown/recovery. M4 still needs a cloud-owned drain gate to reconcile acknowledged producer IDs to archived consumer outcomes after a real stream run.

### Recovery and next tests

If the producer errors or the shell is interrupted, run realtime-stop.ps1. If cleanup fails, inspect CloudFormation events and retry using the original prefix/profile/region. Treat an access-denied response as unknown state, not proof of deletion.

M2 fixture tests cover malformed input, duplicate events, out-of-order events, throttling and replay. M3 adds manifest-based input accounting and canonical dedupe; M4 owns the full producer-to-consumer drain reconciliation and laptop-loss recovery drill.

## Operating time estimates

Reviewed 2026-09-06. This is an operational planning guide for the current implementation. It is not measured AWS evidence yet: CloudFormation time, account quotas, credentials, first deployment, AWS service load and network conditions can change the result. Record actual timestamps in every cloud run and replace these estimates after two successful rehearsals.

### Parked to live demo

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

### Freeze after a demo

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

### Rebuild paths

| Starting state | Scope | Planning time | Notes |
|---|---|---:|---|
| Parked core | Realtime customer demo | 3–7 minutes | Preferred demo path; reserve 10 minutes operationally |
| Core absent, synthetic data retained locally | Deploy core only | 10–20 minutes | Includes CloudFormation creation; does not establish batch KPI data |
| Core absent | Core + seed/upload + Glue + crawler + Athena preflight | 30–45 minutes | Glue is capped at 10 minutes and crawler has a 10-minute minimum; use this path before a meeting, not during one |
| Full reset after export | Recreate complete project | 30–45+ minutes | Infrastructure can be recreated, but deleted real data needs explicit restore; synthetic input can be regenerated |

The delivery plan has a future acceptance target of a clean core rebuild within 20 minutes and full preparation within 30 minutes. That target is unmeasured and should not yet be promised to a customer. The current sequential Glue and crawler settings alone reserve up to 20 minutes, so reserve 30–45 minutes until rehearsal evidence proves a faster path.

### Demo scheduling rule

For a customer session, keep core parked before the meeting, activate realtime 10 minutes beforehand, validate fresh state, then run the scenario. Freeze realtime immediately after the evidence window. This preserves the low parked-cost model while avoiding a long live deploy during the presentation.

The local-first dashboard is a required Phase 1 deliverable but has not yet been implemented. It must be started and verified separately once available; do not include it in the current timing claim.

### Evidence to collect

Record these UTC timestamps in the cloud-run record:

1. Realtime deploy command start and CloudFormation completion.
2. First producer record sent.
3. First and p95 latest-state observation for each ESP.
4. Scenario start and final record sent.
5. Teardown request, deletion completion and absence verification.
6. Core deploy start/end, Glue job start/end and crawler start/end for rebuild rehearsals.

After two successful runs, publish the median and p95 timing in this document and use those observed values in the customer demo plan.

## Troubleshooting

| Symptom | Check | Recovery |
|---|---|---|
| Wrong Python / missing packages | .venv/Scripts/python.exe exists and dependencies match lock | Recreate the project venv; never install into another project |
| CDK schema mismatch | Local CLI and Python library versions | npm ci and pip install -r requirements-lock.txt |
| Bootstrap failure | Account, region, credentials, bootstrap stack events | Reauthenticate; bootstrap selected sandbox |
| Realtime deployment fails | Core exists; core template is updated; stack events | Deploy core, then retry realtime; inspect rollback leftovers |
| Lambda cannot read stream | Realtime IAM policy and mapping state | Inspect cloud error; do not guess function names |
| No state | Producer region, mapping state, Lambda logs, failure payloads | Fix root cause, rerun supervised demo |
| No alert | Scenario threshold, SNS subscription confirmed, Lambda logs | Use low_flow; sensor_fault has no detector yet |
| Repeated alerts | Expected current per-record rule behavior | Limit demo duration; implement cooldown in M2 |
| Old state replaces new | Unconditional current DynamoDB writes | M2 conditional event-time update required |
| Glue failure | Input exists, role rights, script path, log error | Fix and run one new execution |
| Athena table missing | Wrapper completed crawler; catalog database | Inspect crawler LastCrawl result; verify actual table name |
| Athena scan cutoff | Correct workgroup; partition predicate | Narrow date range; review a controlled limit change |
| Empty/null dates | CSV timestamp and Spark parsing | Fail publication; implement M3 contract checks |
| Teardown failed | Exact CloudFormation event and credentials | Run realtime-stop with original account/region/prefix |
| Unexpected bill | Stream lifetime, job history, sessions, logs, bootstrap | Stop runtime and inspect cost by service; budget cannot cap it |

S3 failed invocation payloads live under aws/lambda/. Their presence means a consumer failed; it does not mean semantic quarantine, replay or alert delivery succeeded.

A timeout in a local script means state is uncertain. Check remote service state before another run. Never record access denied, network failure or missing permissions as successful cleanup.

For every incident capture: timestamp, command, selected region, exact error, affected resource ID, recovery action and read-back result. Redact secrets and personal/account identifiers before sharing.
