# Getting started

## Local setup: no AWS resources

Install Python 3.12, Node.js 24 and AWS CLI v2 for later cloud work. The project uses a virtual environment and a local pinned CDK CLI; no global CDK installation is needed. Node/Python support should be rechecked when upgrading dependencies.

From the project root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
npm ci
.\scripts\validate.ps1
```

If the Python launcher has no interpreter, use the absolute path to an installed Python 3.12 executable with -m venv .venv. Do not accidentally install into another project's Python environment.

Validation runs tests, checks documentation links and synthesizes both stacks without deploying. See [validation report](../evidence/LOCAL-VALIDATION.md). Synthesis does not validate AWS credentials, quotas or runtime permissions.

## Build in this order

Treat the project as a sequence of small evidence-backed exercises, not one large deployment. Do not begin a later milestone until the confirmation for the current one is understood and recorded.

| Step | Do | Learn / confirm before continuing |
|---|---|---|
| 1. M0 local foundation | Install dependencies and run `validate.ps1` | Trace both data paths in [architecture](02-ARCHITECTURE.md); understand that local success is not AWS proof. |
| 2. Read the baseline code | Read `app.py`, both stacks, the three handlers and the lifecycle scripts | Identify the persistent core, disposable realtime stack, raw S3 history, DynamoDB latest state, SNS alerts and Glue output. |
| 3. Prepare AWS | Select one sandbox profile and region, then bootstrap | `aws sts get-caller-identity` returns the intended account and region. |
| 4. Deploy core | Deploy the persistent stack with a budget email | CloudFormation exposes bucket, table, workflow, crawler, database and workgroup outputs. |
| 5. Run M3 batch | Generate/upload historical CSV, retain a bounded realtime run, then create a manifest and run the workflow/crawler | A checksum-bound mixed-source run writes immutable silver/gold and an approved publication pointer. |
| 6. Run realtime baseline | Run `normal`, then `low_flow`; observe state, raw objects and an optional SNS email | The one-shard stream and mappings are removed after each bounded demo. |
| 7. M1 contract | Completed; verify the schema-v1 batch/quarantine smoke evidence | Valid, invalid, duplicate and late events have explicit outcomes. |
| 8. M2 streaming correctness | Completed; verify conditional state and cooldown evidence | A duplicate or older event cannot regress state or create unexplained side effects. |
| 9. M3 analytical publication | Implemented locally; run its AWS acceptance scenario | Counts reconcile and a rerun/backfill does not damage an earlier good result. |
| 10. M4 operations and security | Move completion/expiry into AWS, tighten roles and run recovery drills | The project can stop, recover and rebuild without depending on one laptop session. |
| 11. M5 consumer dashboard | Build the local read API and dashboard from real DynamoDB and approved KPI data | Two rehearsals pass with measured freshness, stale/error behavior and cost evidence. |

M1-M5 are implementation work, not features already provided by the baseline. Read the exact exit gates and tests in [delivery and learning](06-DELIVERY-AND-LEARNING.md) before changing each layer.

## Select an AWS sandbox

The following commands make AWS requests, and deployment can incur charges. Use a dedicated sandbox, one region and one project prefix. Select the profile explicitly in each shell:

```powershell
$env:AWS_PROFILE = 'your-sandbox-profile'
$env:AWS_DEFAULT_REGION = 'us-east-1'
$env:AWS_REGION = $env:AWS_DEFAULT_REGION
aws sso login --profile $env:AWS_PROFILE
aws sts get-caller-identity
```

Use your existing authentication method if it is not IAM Identity Center. Confirm account and region before continuing. us-east-1 is the cost-example region, not a residency recommendation. Boto3 and CLI must use the same profile and region.

## Bootstrap and review

Load the project helper before invoking CDK directly. It selects the project virtual environment and keeps jsii's temporary package cache inside this workspace, avoiding an inaccessible shared cache on Windows:

```powershell
. .\scripts\common.ps1
Invoke-Checked $script:ProjectCdk @('bootstrap')
Invoke-Checked $script:ProjectCdk @('diff', "$script:ProjectPrefix-core")
```

The default prefix is in cdk.json. Scripts read it from there; do not supply an inconsistent prefix only on the CDK command line. Changing it creates another deployment rather than renaming the old one. Bootstrap is shared account/region infrastructure and persists after project reset.

## First cloud walkthrough

Keep the AWS Console open on CloudFormation, S3, DynamoDB, Step Functions, Glue, Athena and CloudWatch while running the commands below. Stop after each command and inspect its output; the point is to trace the data, not only reach a successful status.

## Core and batch

```powershell
.\scripts\deploy-core.ps1 -BudgetEmail 'your-real-email-address'
.\.venv\Scripts\python.exe scripts/seed-batch-data.py
.\scripts\upload-batch.ps1
.\scripts\run-batch.ps1
```

Replace the email placeholder. Pass the same email on subsequent core deploys or notifications are removed. The USD 5 budget is filtered to the project tag after that cost-allocation tag is activated. SNS anomaly subscription is separate; see [operations](04-OPERATIONS.md).

After the first tagged resources appear, open AWS Billing and Cost Management -> Cost allocation tags, activate the user-defined `Project` tag, and verify that `oilfield-esp` appears before relying on the filtered budget. Tag activation and cost data are not retroactive evidence for earlier usage.

The batch wrapper waits for Step Functions success, then starts and checks the crawler. Query through the project Athena workgroup using [batch instructions](04-OPERATIONS.md).

For a true M3 acceptance run, first retain at least one bounded realtime scenario (it parks Kinesis afterward but leaves its raw JSON), then run the batch command with an inclusive UTC date window. Verify the generated input manifest contains `historical_csv` and `realtime_json`, inspect `staging/m3/<run-id>/quality-report.json`, then read `curated/publication/current.json`. The crawler targets `curated/silver/`; verify its discovered table name before running the supplied SQL with the pointer's `published_run_id`. Explain why raw input, staging, immutable Parquet, the publication pointer and Athena results are separate prefixes in the same bucket.

## Realtime and parking

```powershell
.\scripts\realtime-start.ps1 -DurationMinutes 5 -Scenario low_flow
.\scripts\realtime-stop.ps1
```

The first command attempts teardown automatically. The second is the recovery command if interrupted or cleanup failed. Observe DynamoDB/SNS during the run; S3 and logs remain afterward. Do not run concurrent demo sessions against the same prefix: either session can destroy the other's stream.

The 30-second grace period is not a drain guarantee. Do not promise delivery completeness until the reconciliation gate is implemented.

Start with `normal` to learn the data path without alerts. Then use `low_flow` only after confirming the SNS email subscription. Observe a fresh DynamoDB item for each pump, the matching S3 raw object and the alert behavior before the script removes Kinesis. If the terminal is interrupted, use `realtime-stop.ps1` and complete the park checklist in [operations](04-OPERATIONS.md).

## Full reset

Export any data/evidence you need. Then:

```powershell
.\scripts\destroy-all.ps1 -DeleteData
```

This removes both project stacks and their S3/DynamoDB data. It does not remove shared CDK bootstrap assets or all service-created logs. Follow the [post-reset checklist](04-OPERATIONS.md).

To rebuild, repeat core deployment, seed/upload/batch and realtime. Original customer data is not recoverable merely by redeploying IaC; synthetic input can be regenerated.
