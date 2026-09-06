# Operations

## Before a run

Select profile/region, verify STS identity and read PROJECT-STATUS.md. Check core stack outputs. Ensure no other operator is using the same prefix. Confirm available spend allowance and subscribed alert destination.

Run validate.ps1 after code changes. Review CDK diff before deployment. The scripts use --require-approval never because their resource changes must be reviewed before invoking them.

## Inspect current resources

```powershell
. ./scripts/common.ps1
Invoke-Checked aws @('cloudformation','describe-stacks','--stack-name',"$script:ProjectPrefix-core")
Invoke-Checked aws @('cloudformation','describe-stacks','--stack-name',"$script:ProjectPrefix-realtime")
```

The realtime query failing with a specific stack-not-found error can be expected when parked. Authentication, permissions or network failures do not prove absence.

Use stack Resources/Outputs in CloudFormation to locate the generated names for Lambda, bucket, DynamoDB, crawler, state machine and workgroup. Avoid reconstructing physical names.

## Optional SNS email

```powershell
. ./scripts/common.ps1
$topic = Get-CoreOutput 'AlertTopicArn'
Invoke-Checked aws @('sns','subscribe','--topic-arn',$topic,'--protocol','email','--notification-endpoint','your-real-email-address')
```

Replace the placeholder and confirm the email. This subscription is a manual post-deploy step and must be recreated after a full reset. Budget email is separately passed to deploy-core.ps1.

## Park and verify

1. Run realtime-stop.ps1; require successful completion.
2. Verify realtime CloudFormation stack deletion and Kinesis stream absence in the selected region.
3. Verify no Kinesis event mappings remain attached to the two application functions.
4. Inspect the Glue job for RUNNING/STARTING/STOPPING runs and the state machine for running executions.
5. Inspect crawler activity and any manual Athena queries or interactive sessions.
6. Confirm the daily EventBridge rule remains disabled.
7. Record residual storage and review billing when data arrives.

Stopping a Step Functions execution is not evidence that every downstream resource stopped. Inspect Glue directly and stop a running job if necessary. Avoid automatically restarting failed batches until the cause is understood.

## Reset and restore

Copy required S3 content to a controlled local export before destructive reset; separately export DynamoDB data if latest state must be kept. Current latest state can also be rebuilt only after replay tooling exists. Save SQL results and redact account IDs in shareable evidence.

Run destroy-all.ps1 -DeleteData. The bucket uses auto-delete and the table uses DESTROY; bypassing this wrapper with direct CDK destroy can also erase data.

Afterward inspect shared CDKToolkit assets/ECR and Glue/provider-created log groups. Do not delete shared bootstrap infrastructure used by other projects. Record any residual resources instead of reporting an account-wide zero footprint.

Rebuild with the same configuration and lockfiles, then seed/upload the synthetic dataset. Generated physical names may change. Restore real exported data explicitly if needed; IaC restores resources, not deleted content.

## Planned reliability controls

M4 adds a cloud expiry lease, deployment lock, observed stream drain and cloud-owned batch completion. Alarm requirements: Lambda Errors/Throttles/IteratorAge, failure-destination delivery failures, Glue failures, workflow timeouts and quarantine spikes. Keep paid alarms and dashboards scoped and costed.

Until then, operators inspect native metrics/logs manually. A hard-killed shell can leave a billed stream running.
