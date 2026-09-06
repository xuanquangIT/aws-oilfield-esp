# Troubleshooting

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
