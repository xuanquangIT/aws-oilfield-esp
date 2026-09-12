# Runbook: deploy, run and destroy

This is the single hands-on command reference for this project: environment setup, AWS authentication, core deployment, batch run, every realtime scenario, cost-safety verification, and full teardown. It consolidates commands already described in [Getting started](01-GETTING-STARTED.md) and [Operations](04-OPERATIONS.md) into one linear runbook, plus the fixes and pitfalls found while first deploying this stack. Commands target Windows PowerShell and assume the project root as the working directory.

Read [Getting started](01-GETTING-STARTED.md) first if this is your first pass; use this file afterward as the fast reference.

## 0. Prerequisites checklist

- Python 3.12, Node.js 24, AWS CLI v2 installed.
- A dedicated IAM user (not root) with sufficient permissions for CDK deploy (Administrator for a personal sandbox, or a scoped policy covering S3, DynamoDB, Glue, Athena, Kinesis, Lambda, Step Functions, CloudFormation, IAM role creation, Budgets, SNS, EventBridge).
- One AWS account/region dedicated to this sandbox.

Never use the AWS account root user's access keys for CLI/CDK work. Create an IAM user for this instead; see step 2.

## 1. Local environment setup (no AWS calls)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
npm ci
.\scripts\validate.ps1
```

If a fresh PowerShell session blocks script execution with "cannot be loaded... not digitally signed", allow unsigned scripts for that session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

This only applies to the current window; repeat it in every new PowerShell session before running any `.ps1` script here.

## 2. AWS authentication

Create a dedicated IAM user (Console: IAM -> Users -> Create user -> Access key, programmatic use) and attach a policy sufficient for this project (`AdministratorAccess` is acceptable for a personal sandbox). Do not use the root user's access keys. Then configure a named profile:

```powershell
aws configure --profile oilfield-esp-deployer
```

Set it for every new shell before running project scripts:

```powershell
$env:AWS_PROFILE = 'oilfield-esp-deployer'
$env:AWS_DEFAULT_REGION = 'us-east-1'
$env:AWS_REGION = $env:AWS_DEFAULT_REGION
aws sts get-caller-identity
```

Confirm the `Arn` in the output is the IAM user, never `:root`. If you use IAM Identity Center (SSO) instead, run `aws configure sso` first, then `aws sso login --profile <name>` before `get-caller-identity`.

## 3. Bootstrap CDK (one-time per account/region)

```powershell
. .\scripts\common.ps1
Invoke-Checked $script:ProjectCdk @('bootstrap')
Invoke-Checked $script:ProjectCdk @('diff', "$script:ProjectPrefix-core")
```

Bootstrap creates shared CDK infrastructure (asset S3 bucket, IAM roles) that persists across project resets. Re-run `diff` any time to preview drift before deploying.

## 4. Deploy the core stack

```powershell
.\scripts\deploy-core.ps1 -BudgetEmail 'your-real-email-address'
```

Deploys `oilfield-esp-core`: S3 data bucket, DynamoDB latest-state table, SNS alert topic, both Lambdas, Glue role/database/job/crawler, Athena workgroup, Step Functions batch workflow (with a disabled daily schedule), and a USD 5 monthly budget filtered to the `Project` tag.

Reuse the same `-BudgetEmail` on every subsequent core deploy, or the budget notification subscriber is removed.

### 4.1 Activate the cost-allocation tag (one-time, after first deploy)

Console: Billing and Cost Management -> Cost allocation tags -> search for tag key `Project` (not the value `oilfield-esp`) -> Activate. This can take up to 24 hours to appear after the first tagged resources exist, and is not retroactive.

### 4.2 Subscribe an email to the alert SNS topic (optional, needed before `low_flow` or similar scenarios)

```powershell
. .\scripts\common.ps1
$topic = Get-CoreOutput 'AlertTopicArn'
aws sns subscribe --topic-arn $topic --protocol email --notification-endpoint 'your-real-email-address'
```

Confirm the subscription from the email AWS sends ("AWS Notification - Subscription Confirmation"). This is a real SNS subscription and requires manual confirmation, unlike the Budget email notifications in step 4, which do not.

### 4.3 Verify core outputs

```powershell
aws cloudformation describe-stacks --stack-name oilfield-esp-core --query 'Stacks[0].Outputs' --output table
```

Expect: `DataBucketName`, `StateTableName`, `AlertStateTableName`, `AlertTopicArn`, `StateMachineArn`, `GlueCrawlerName`, `GlueJobName`, `GlueDatabaseName`, `AthenaWorkGroup`.

## 5. M3 batch scenario: deploy, run, verify

```powershell
.\.venv\Scripts\python.exe scripts/seed-batch-data.py
.\scripts\upload-batch.ps1
.\scripts\run-batch.ps1
```

- `seed-batch-data.py` generates 504 rows (7 days x 24 hours x 3 pumps) of synthetic, schema-v1 CSV under `data/`.
- `upload-batch.ps1` uploads it to `raw/batch/historical.csv` in the data bucket.
- `run-batch.ps1` builds a content-SHA-256 input manifest, starts the Step Functions workflow with a unique publication run ID, waits for Glue to write `staging/m3/<run-id>/`, and only then starts the crawler for `curated/silver/`. Glue advances `curated/publication/current.json` only if its quality gate passes. This can take 3-6 minutes on a Glue cold start.

Every M3 run is immutable. To prove a deterministic rerun, retain the printed manifest key and execute `run-batch.ps1 -ManifestKey '<key>'`; it creates a new publication run partition from the identical input. To run a one-day backfill, pass `-StartDate` and `-EndDate` for that UTC day (and the desired `-LateArrivalLookbackDays`). It cannot overwrite an earlier run partition.

For a reproducible fixture (same rows, same `event_id` values every run), pass `--seed`/`--start-time`:

```powershell
.\.venv\Scripts\python.exe scripts/seed-batch-data.py --seed 42 --start-time 2026-08-31T00:00:00Z
```

### 5.1 Verify with Athena

```powershell
. .\scripts\common.ps1
$db = Get-CoreOutput 'GlueDatabaseName'
$wg = Get-CoreOutput 'AthenaWorkGroup'
Invoke-Checked aws @('glue','get-tables','--database-name',$db,'--query','TableList[].Name','--output','table')
```

Read `curated/publication/current.json` and copy its `published_run_id`. Confirm the crawler's silver table exists, replace `<published_run_id>` in [`sql/02-quality-checks.sql`](../sql/02-quality-checks.sql) and [`sql/01-daily-kpis.sql`](../sql/01-daily-kpis.sql), then run them in Athena using workgroup `$wg` and database `$db`. Save the quality report and Athena query IDs/bytes scanned.

### 5.2 M3 AWS acceptance checklist

The preceding historical-only sequence tests the path but does not complete M3. For acceptance, retain a bounded realtime scenario first, run a date window covering both sources, and then verify: (1) the manifest has `historical_csv` and `realtime_json`; (2) `quality-report.json` has `unexplained_rows = 0`; (3) a new run from the same manifest has the same `canonical_data_sha256`; (4) a one-day backfill produces a distinct `publication_run_id` without changing earlier partitions; and (5) an `event_date`-filtered Athena query has fewer `DataScannedInBytes` than its unfiltered counterpart. Record these in a private cloud-run receipt before claiming M3 AWS verification.

## 6. Realtime scenarios: deploy, run, stop

Available scenarios (`-Scenario` parameter): `normal`, `gas_slug`, `low_flow`, `mechanical`, `blockage`, `sensor_fault`, `shutdown`. `normal` produces no anomaly; every other scenario is designed to trigger the `AnomalyDetector` Lambda and publish to SNS.

```powershell
.\scripts\realtime-start.ps1 -DurationMinutes <N> -Scenario <name>
```

This single command: deploys the disposable `oilfield-esp-realtime` stack (one-shard Kinesis stream plus event source mappings), runs `simulator/esp_simulator.py` for `DurationMinutes * 60` seconds, waits a 30-second grace period, then destroys the realtime stack in a `finally` block regardless of success or failure.

### 6.1 Known caveats before you run a scenario with alerts

- **M2 cooldown is active.** A sustained anomaly emits one trigger alert per `(esp_id, rule_id)` episode, then a recovery alert when it clears; it does not promise exactly-once SNS delivery. The 2026-09-07 AWS check produced five SNS publishes for a two-minute `low_flow` run, compared with 159 before M2. Keep demo runs bounded and confirm the SNS subscription when email delivery, rather than publish count, matters.
- **Actual runtime is longer than `-DurationMinutes`** if your network latency to `us-east-1` is high. The simulator issues 3 synchronous `put_record` calls per tick and only then sleeps 1 second; it does not subtract the API call time from the sleep interval. From regions with ~200-500 ms round-trip latency to `us-east-1`, a "5 minute" run can take 10-13 minutes wall clock. This is expected, not a hang.
- **Do not run two realtime sessions concurrently.** Either can tear down the other's Kinesis stream.

### 6.2 Observe during a run

Open, in parallel: DynamoDB (`LatestState` table, item per `esp_id`), S3 (`raw/realtime/` prefix, one JSON object per processed batch), and your inbox if a scenario other than `normal` is running.

```powershell
. .\scripts\common.ps1
$table = Get-CoreOutput 'StateTableName'
aws dynamodb scan --table-name $table --output json
```

### 6.3 Interrupted or stuck session recovery

If you interrupt the terminal (Ctrl+C) or the session fails before the automatic `finally` cleanup runs, do not assume Kinesis was removed. Always run the recovery command:

```powershell
.\scripts\realtime-stop.ps1
```

Then verify no stream remains:

```powershell
aws cloudformation describe-stacks --stack-name oilfield-esp-realtime --query 'Stacks[0].StackStatus' --output text
aws kinesis list-streams --output json
```

The first command should error with "does not exist"; the second should return empty lists.

### 6.4 Stop receiving alert emails without redeploying

```powershell
aws sns unsubscribe --subscription-arn '<SubscriptionArn from the email footer or list-subscriptions-by-topic>'
```

Re-subscribe later (step 4.2) when you are ready to test again, ideally after implementing cooldown logic in M2.

### 6.5 Quarantine smoke test: prove the schema v1 contract in realtime (M1)

This proves delivery gate G1 ("Contract") end-to-end in AWS: a deliberately invalid record must be quarantined and must never reach `raw/realtime/` or the `LatestState` DynamoDB table, while a valid record must reach both.

Deploy the realtime stack on its own (skip the simulator, since you are injecting records by hand):

```powershell
. .\scripts\common.ps1
Invoke-Checked $script:ProjectCdk @('deploy', "$script:ProjectPrefix-realtime", '--exclusively', '--require-approval', 'never')
```

Write four small JSON payloads to a scratch folder: one valid schema-v1 event, and three deliberately invalid ones (unknown `esp_id`, an out-of-range `water_cut`, and a non-JSON payload). See `src/contract.py` for the full rule list (`MALFORMED_PAYLOAD`, `SCHEMA_VERSION_UNSUPPORTED`, `MISSING_FIELD`, `UNKNOWN_ESP_ID`, `INVALID_SOURCE`, `INVALID_STATUS`, `INVALID_TIMESTAMP`, `NON_FINITE_NUMBER`, `OUT_OF_RANGE`). Send each with `aws kinesis put-record --stream-name oilfield-esp-realtime --partition-key <esp_id> --data fileb://<path>`, then wait ~20-30 seconds for the `StreamProcessor` Lambda to drain the shard.

Verify the outcome:

```powershell
$bucket = Get-CoreOutput 'DataBucketName'
aws s3 ls "s3://$bucket/quarantine/realtime/" --recursive
aws s3 ls "s3://$bucket/raw/realtime/" --recursive
$table = Get-CoreOutput 'StateTableName'
aws dynamodb get-item --table-name $table --key '{"esp_id":{"S":"<valid esp_id used above>"}}' --output json
```

Expected outcome: the three invalid payloads each produce one object under `quarantine/realtime/<RULE_ID>/<esp_id or "unknown">/...`, containing `rule_id`, `reason`, and the original `raw_base64` payload. None of them appear under `raw/realtime/`, and none of their `event_id` values appear in the `LatestState` table. The valid payload appears under both `raw/realtime/<esp_id>/...` and as the `LatestState` item for that `esp_id`.

Always destroy the realtime stack manually afterward, since it was deployed outside `realtime-start.ps1`'s automatic cleanup:

```powershell
Invoke-Checked $script:ProjectCdk @('destroy', "$script:ProjectPrefix-realtime", '--exclusively', '--force')
```

### 6.6 Verify M2: conditional state, alert cooldown, and the replay tool

This proves the M2 exit gate in AWS: state is monotonic, a sustained anomaly sends one alert per episode (not one per record), and the replay tool can reprocess a failed batch.

> **Verified 2026-09-07.** Conditional state: a newer-timestamp `ESP-101` record was accepted (numeric fields confirmed as DynamoDB `N`, not `S`); an older-timestamp record sent afterward for the same pump was rejected by the `ConditionExpression` and `LatestState` stayed unchanged, while both events still landed as distinct `event_id`-keyed objects in `raw/realtime/`. Alert cooldown: a 2-minute `low_flow` run (360 records across 3 pumps) produced exactly 4 `AlertState` episodes (3 active, 1 recovered) and exactly 5 `AWS/SNS NumberOfMessagesPublished` (CloudWatch), versus 159 emails for a comparable pre-M2 run. Test artifacts were deleted from `LatestState`/`AlertState`/S3 afterward. The replay tool was not exercised against a live failure payload in this pass (see the note at the end of this section).

Deploy the realtime stack on its own, as in 6.5:

```powershell
. .\scripts\common.ps1
Invoke-Checked $script:ProjectCdk @('deploy', "$script:ProjectPrefix-realtime", '--exclusively', '--require-approval', 'never')
```

**Conditional latest state.** Send a valid record, then a second valid record for the same `esp_id` with an _earlier_ `timestamp` (a manufactured late arrival). Confirm both land in `raw/realtime/` (two objects, keyed by their distinct `event_id`s) but the `LatestState` item still shows the first (newer) timestamp, and its numeric fields (`flow_rate`, `motor_temperature`, `motor_current`, `vibration`) are DynamoDB Number type, not strings:

```powershell
$table = Get-CoreOutput 'StateTableName'
aws dynamodb get-item --table-name $table --key '{"esp_id":{"S":"ESP-101"}}' --output json
```

A `Number` value appears in the JSON as `{"N": "120.0"}`, not `{"S": "120.0"}`.

**Alert cooldown.** Run a short anomaly scenario (`low_flow` produced 159 emails before M2; it should now produce at most one or two):

```powershell
.\scripts\realtime-start.ps1 -DurationMinutes 2 -Scenario low_flow
```

Inspect the cooldown/recovery state:

```powershell
$alertTable = Get-CoreOutput 'AlertStateTableName'
aws dynamodb scan --table-name $alertTable --output json
```

Expect one item per (esp_id, rule_id) that fired, each with `active=true`, an `episode_id`, and a `cooldown_until` roughly 5 minutes (`ALERT_COOLDOWN_SECONDS`, default 300) after the first trigger. Check your inbox: a 2-minute run should deliver far fewer than 159 emails (one per pump/rule that triggered, not one per record).

**Replay tool.** The replay tool (`scripts/replay-failed.py`) reprocesses records referenced by a Kinesis on-failure-destination S3 pointer object. Triggering a real failure deliberately (for example, temporarily breaking the `StreamProcessor` function's S3 permission, sending a batch, then restoring it) is the only way to generate one; once you have a failure object's bucket/key:

```powershell
. .\scripts\common.ps1
$env:DATA_BUCKET = Get-CoreOutput 'DataBucketName'
$env:STATE_TABLE = Get-CoreOutput 'StateTableName'
python scripts/replay-failed.py --bucket $env:DATA_BUCKET --key '<aws/lambda/... failure object key>'
```

This dry-run prints and saves a JSON receipt classifying each record (`would_process`/`would_quarantine`) with no side effects. Add `--execute` to actually apply them through the same `process_record` path the live Lambda uses. This step is optional and not required to consider M2 verified; the conditional-state and cooldown checks above are the primary evidence.

Always destroy the realtime stack manually afterward if you deployed it outside `realtime-start.ps1`:

```powershell
Invoke-Checked $script:ProjectCdk @('destroy', "$script:ProjectPrefix-realtime", '--exclusively', '--force')
```

## 7. Cost and idle-safety audit (run before parking the project)

Use this whenever you stop working and want confirmation that nothing keeps accruing cost or sending notifications.

```powershell
. .\scripts\common.ps1

Write-Host '--- CloudFormation stacks (expect only core + CDKToolkit) ---'
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE --query 'StackSummaries[].{Name:StackName,Status:StackStatus}' --output table

Write-Host '--- EventBridge DailySchedule (expect DISABLED) ---'
aws events list-rules --query 'Rules[].{Name:Name,State:State}' --output table

Write-Host '--- Kinesis streams (expect none) ---'
aws kinesis list-streams --output json

Write-Host '--- Step Functions running executions (expect none) ---'
$sm = Get-CoreOutput 'StateMachineArn'
aws stepfunctions list-executions --state-machine-arn $sm --status-filter RUNNING --output json

Write-Host '--- Glue job runs in progress (expect none) ---'
$job = Get-CoreOutput 'GlueJobName'
aws glue get-job-runs --job-name $job --query 'JobRuns[?JobRunState==`RUNNING`]' --output json

Write-Host '--- Glue crawler state (expect READY) ---'
$crawler = Get-CoreOutput 'GlueCrawlerName'
aws glue get-crawler --name $crawler --query 'Crawler.State' --output text

Write-Host '--- S3 data bucket size ---'
$bucket = Get-CoreOutput 'DataBucketName'
aws s3 ls "s3://$bucket" --recursive --summarize | Select-Object -Last 5

Write-Host '--- DynamoDB billing mode (expect PAY_PER_REQUEST) ---'
$table = Get-CoreOutput 'StateTableName'
aws dynamodb describe-table --table-name $table --query 'Table.{BillingMode:BillingModeSummary.BillingMode,ItemCount:ItemCount}' --output table

Write-Host '--- Budgets ---'
aws budgets describe-budgets --account-id (aws sts get-caller-identity --query Account --output text) --query 'Budgets[].{Name:BudgetName,Limit:BudgetLimit.Amount,Actual:CalculatedSpend.ActualSpend.Amount}' --output table
```

Expected safe/parked state: only `oilfield-esp-core` (plus `CDKToolkit`) exists; the daily schedule is `DISABLED`; no Kinesis streams; no running Step Functions executions or Glue job runs; the crawler is `READY`; DynamoDB is on-demand billing; the S3 bucket only holds the small batch/curated data (realtime raw objects expire automatically after 7 days via the `ExpireRawRealtime` lifecycle rule); the budget's actual spend is near zero.

Residual idle cost at this state is well under USD 0.05/month (S3 storage for a few hundred KB and the CDK bootstrap asset bucket). No component in this list auto-triggers further spend.

## 8. Full reset (destroy everything, including data)

```powershell
.\scripts\destroy-all.ps1 -DeleteData
```

Removes both project stacks and their S3/DynamoDB data. It does not remove the shared CDK bootstrap stack (`CDKToolkit`) or all service-created CloudWatch logs. Export any evidence you need first; original data is not recoverable by redeploying IaC (only synthetic data can be regenerated).

To rebuild from scratch later: repeat steps 3 (bootstrap, if the account/region bootstrap was also removed manually), 4, 5 and 6.

## 9. Infrastructure bugs already fixed in this repo

Recorded here so they are not re-diagnosed on a future clone or environment rebuild.

| Symptom                                                                                                                                                                   | Root cause                                                                                                                                                                                                                                                         | Fix                                                                                                                                    |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `AWS::Glue::Job BatchJob` fails to create: "Script location cannot be null or empty for glueetl command"                                                                  | `infrastructure/core_stack.py` passed a plain Python `dict` for `CfnJob`'s `command` and `execution_property` props; `python_version` and `script_location` were silently dropped during synthesis, leaving only `Name` in the synthesized template                | Use the typed structs `glue.CfnJob.JobCommandProperty(...)` and `glue.CfnJob.ExecutionPropertyProperty(...)` instead of raw dicts      |
| `AWS::Lambda::EventSourceMapping AnomalyMapping` (and `ProcessorMapping`) fail to create: "The function execution role does not have permissions to call PutObject on S3" | `infrastructure/realtime_stack.py` granted `s3:PutObject` only under the `aws/lambda/*` object prefix, but the on-failure S3 destination for a stream event source mapping writes objects under a Lambda-generated key that is not guaranteed to match that prefix | Grant `s3:PutObject` on all objects in the data bucket (`arn_for_objects("*")`), scoped by the existing `s3:ResourceAccount` condition |

Both fixes are already applied in `infrastructure/core_stack.py` and `infrastructure/realtime_stack.py`. If a future `cdk diff`/`deploy` on a fresh checkout reproduces either symptom, check that these files still contain the typed-struct and wildcard-prefix forms described above.

## 10. Quick command reference

| Action                                 | Command                                                                                                         |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Open execution policy for this session | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`                                                    |
| Set AWS context                        | `$env:AWS_PROFILE='...'; $env:AWS_DEFAULT_REGION='us-east-1'; $env:AWS_REGION=$env:AWS_DEFAULT_REGION`          |
| Verify identity                        | `aws sts get-caller-identity`                                                                                   |
| Bootstrap CDK                          | `. .\scripts\common.ps1; Invoke-Checked $script:ProjectCdk @('bootstrap')`                                      |
| Preview core changes                   | `Invoke-Checked $script:ProjectCdk @('diff', "$script:ProjectPrefix-core")`                                     |
| Deploy core                            | `.\scripts\deploy-core.ps1 -BudgetEmail '...'`                                                                  |
| Seed + upload + run batch              | `.\.venv\Scripts\python.exe scripts/seed-batch-data.py; .\scripts\upload-batch.ps1; .\scripts\run-batch.ps1`    |
| Start a realtime scenario              | `.\scripts\realtime-start.ps1 -DurationMinutes N -Scenario <name>`                                              |
| Recover/stop realtime                  | `.\scripts\realtime-stop.ps1`                                                                                   |
| Subscribe alert email                  | `aws sns subscribe --topic-arn (Get-CoreOutput 'AlertTopicArn') --protocol email --notification-endpoint '...'` |
| Unsubscribe alert email                | `aws sns unsubscribe --subscription-arn '...'`                                                                  |
| Cost/idle audit                        | See section 7                                                                                                   |
| Full reset                             | `.\scripts\destroy-all.ps1 -DeleteData`                                                                         |
