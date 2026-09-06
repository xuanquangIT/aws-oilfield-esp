# Quickstart

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

Activate the virtual environment so CDK's configured python app resolves correctly:

```powershell
.\.venv\Scripts\Activate.ps1
.\node_modules\.bin\cdk.cmd bootstrap
.\node_modules\.bin\cdk.cmd diff oilfield-esp-core
```

The default prefix is in cdk.json. Scripts read it from there; do not supply an inconsistent prefix only on the CDK command line. Changing it creates another deployment rather than renaming the old one. Bootstrap is shared account/region infrastructure and persists after project reset.

## Core and batch

```powershell
.\scripts\deploy-core.ps1 -BudgetEmail 'your-real-email-address'
.\.venv\Scripts\python.exe scripts/seed-batch-data.py
.\scripts\upload-batch.ps1
.\scripts\run-batch.ps1
```

Replace the email placeholder. Pass the same email on subsequent core deploys or notifications are removed. Budget is account-wide, USD 5, actual-spend alerts at 50/100%. SNS anomaly subscription is separate; see [operations](07-OPERATIONS.md).

The batch wrapper waits for Step Functions success, then starts and checks the crawler. Query through the project Athena workgroup using [batch instructions](05-BATCH-ANALYTICS.md).

## Realtime and parking

```powershell
.\scripts\realtime-start.ps1 -DurationMinutes 5 -Scenario low_flow
.\scripts\realtime-stop.ps1
```

The first command attempts teardown automatically. The second is the recovery command if interrupted or cleanup failed. Observe DynamoDB/SNS during the run; S3 and logs remain afterward. Do not run concurrent demo sessions against the same prefix: either session can destroy the other's stream.

The 30-second grace period is not a drain guarantee. Do not promise delivery completeness until the reconciliation gate is implemented.

## Full reset

Export any data/evidence you need. Then:

```powershell
.\scripts\destroy-all.ps1 -DeleteData
```

This removes both project stacks and their S3/DynamoDB data. It does not remove shared CDK bootstrap assets or all service-created logs. Follow the [post-reset checklist](07-OPERATIONS.md).

To rebuild, repeat core deployment, seed/upload/batch and realtime. Original customer data is not recoverable merely by redeploying IaC; synthetic input can be regenerated.
