# Cost, security and governance

This document is the single control point for monthly cost, operating boundaries, access control and governance. Estimates model the current code in `us-east-1` for a 30-day month, before tax and without relying on promotional credits or shared free-tier allowances.

## Operating states and implemented controls

| State | What remains | Cost interpretation |
|---|---|---|
| Local | Files, tests and generated fixtures | No AWS charge from these operations |
| Parked | Core metadata/functions plus bounded S3, DynamoDB and log data | Approximately $0.03/month under the documented envelope |
| Demo | Parked core plus temporary Kinesis and active processing | Usage billed; destroy realtime immediately afterward |
| Reset | Both project stacks removed | Bootstrap storage, service-created logs and unrelated account services can remain |

Implemented controls: one provisioned shard only during demos; 24-hour stream retention; no enhanced fan-out; Glue two G.1X workers, ten-minute timeout, zero retry and one concurrent run; disabled daily schedule; Athena 10 MiB query cutoff; raw realtime seven-day expiry; failure payload 14-day expiry; query result one-day expiry; Lambda logs retained seven days; and a project-tag-filtered USD 5 monthly budget when the cost allocation tag is activated.

A budget reports spend and is not a hard cap. The local `finally` cleanup cannot survive every laptop, credential or process failure; cloud-owned expiry remains M4 work.

## Monthly cost estimate

Reviewed 2026-09-06. This estimate models the code currently in this repository in `us-east-1` for a 30-day month. Values are USD before tax and deliberately exclude promotional credits and account-wide free-tier allowances. They are planning figures, not an AWS quote; replace modeled Lambda duration, log volume and short-lived stream time with measured billing after a rehearsal.

### Decision table

| Operating pattern | What runs | Estimated month | Control allowance |
|---|---|---:|---:|
| Frozen / parked | Core stack retained; no stream, simulator, Glue run or Athena query | **$0.03** | **$0.10** |
| Two demos | Two 5-minute streaming runs; two ETL jobs; two crawlers; 20 queries | **$0.66** | **$1.25** |
| Three demos | Three 5-minute streaming runs; three ETL jobs; three crawlers; 30 queries | **$0.97** | **$1.50** |
| One full demo every day | 5-minute streaming + one batch/crawler + 10 queries on each of 30 days | **$9.46** | **$12** |
| Streaming 24x7 + daily batch | 7.776 million events; current per-event S3 writes | **$67.90** | **$75** |
| Streaming 24x7 after batching S3 writes | Same load; approximately six events per S3 object | **$35.50** | **$42** |
| 24x7 worst alert storm | Every event publishes to one confirmed email subscriber | **$227.31** | Do not operate |

The recommended portfolio operating model is **two or three controlled demos, then frozen**. Expect about **$0.66–$0.97/month** for the project itself and use **$1.50** as the working ceiling. Keep the project-tag-filtered $5 budget after activating and verifying the `Project` cost-allocation tag. AWS Budgets reports after usage and is not a hard stop.

“Full every day” can mean two different things. Running the complete demonstration once each day is about **$9.46/month**. Leaving the stream and simulator active continuously while also running batch daily is about **$67.90/month** with the current handler.

### Current implementation assumptions

- Three ESP IDs emit one event each per second: 3 events/second.
- A generated normal event averages 389 bytes in the current simulator and consumes one Kinesis 25 KB PUT payload unit, one S3 PUT and one DynamoDB WRU.
- One provisioned Kinesis shard has 24-hour retention and no enhanced fan-out.
- Both Kinesis consumers use batch size 10 and a two-second maximum batching window. The model uses approximately six records per invocation, or 2.592 million Lambda invocations in a continuous month.
- Lambda gross cost uses 256 MB, 500 ms for the ingest batch and 100 ms for the normal anomaly batch. These durations must be replaced with CloudWatch `Duration` evidence.
- Log ingestion uses a planning value of 500 bytes per Lambda invocation. The functions do not intentionally log every payload.
- Every batch run reserves the Glue job's configured maximum: two G.1X workers for 10 minutes. Every crawler run reserves two DPUs and its 10-minute minimum.
- Ten Athena queries are allowed per full run. Each is modeled at Athena's 10 MiB minimum because the workgroup also stops a query above 10 MiB.
- A short demo reserves one Kinesis shard-hour for create, warm-up, run and destroy. Actual billing duration must be read from Cost and Usage data.
- The local dashboard uses the existing DynamoDB table and S3 KPI object. Its cached 10–15 second polling adds less than $0.001 per short demo at this scale and creates no fixed AWS resource.

### Unit prices used

| Service | us-east-1 planning rate |
|---|---:|
| Kinesis provisioned | $0.015/shard-hour + $0.014/million 25 KB PUT units |
| S3 Standard | $0.023/GB-month; $0.005/1,000 PUT/COPY/POST/LIST; $0.0004/1,000 GET |
| DynamoDB on-demand Standard | $0.625/million WRUs; $0.125/million RRUs; $0.25/GB-month storage |
| Lambda x86 | $0.20/million requests + $0.0000166667/GB-second |
| Glue | $0.44/DPU-hour; Glue 2.0+ job one-minute minimum; crawler 10-minute minimum |
| Athena SQL | $5/TB scanned; 10 MB minimum per query |
| Step Functions Standard | $0.025/1,000 state transitions |
| CloudWatch Logs | $0.50/GB ingested and $0.03/GB-month stored at the first tier |
| SNS Standard/email | $0.50/million API requests + $2/100,000 email deliveries |
| AWS Budgets | Cost/usage monitoring and notifications are free |

Official references: [Kinesis](https://aws.amazon.com/kinesis/data-streams/pricing/), [S3](https://aws.amazon.com/s3/pricing/), [DynamoDB](https://aws.amazon.com/dynamodb/pricing/), [Lambda](https://aws.amazon.com/lambda/pricing/), [Glue](https://aws.amazon.com/glue/pricing/), [crawler minimum](https://docs.aws.amazon.com/pdfs/whitepapers/latest/cost-modeling-data-lakes/cost-modeling-data-lakes.pdf), [Athena](https://aws.amazon.com/athena/pricing/), [Step Functions](https://aws.amazon.com/step-functions/pricing/), [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/), [SNS](https://aws.amazon.com/sns/faqs/), and [AWS Budgets](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/).

The following deployed definitions have no project charge while unused: CloudFormation stacks, IAM roles/policies, Lambda function definitions without invocations, an idle SNS topic, Glue job/crawler definitions, an idle Step Functions state machine, an Athena workgroup, and the disabled EventBridge schedule. Glue Data Catalog remains free while this project stays within the first one million stored objects and one million monthly requests. The budget in this stack only monitors and notifies, so it is free under AWS Budgets pricing. The required dashboard runs locally and adds no hosted service. Same-region service transfers are assumed; unusual internet or cross-region transfer is outside the model and must be measured if introduced.

### Continuous-month breakdown

| Component | Calculation | Cost |
|---|---|---:|
| S3 raw PUT | 7,776,000 objects / 1,000 × $0.005 | $38.88 |
| Kinesis shard | 720 hours × $0.015 | $10.80 |
| DynamoDB writes | 7.776 million WRUs × $0.625 | $4.86 |
| Glue job | 30 × 2 DPUs × 10/60 hour × $0.44 | $4.40 |
| Glue crawler | 30 × 2 DPUs × 10/60 hour × $0.44 | $4.40 |
| Lambda compute | 194,400 modeled GB-seconds × $0.0000166667 | $3.24 |
| CloudWatch ingestion | 2.592 million invocations × 500 bytes × $0.50/GB | $0.65 |
| Lambda requests | 2.592 million × $0.20/million | $0.52 |
| Kinesis PUT units | 7.776 million × $0.014/million | $0.11 |
| Storage envelope | S3 <=1 GB, DynamoDB <=10 MB, logs <=100 MB | $0.03 |
| Athena | 300 × 10 MiB × $5/TiB | $0.014 |
| Step Functions | 30 runs × 3 modeled transitions | $0.002 |
| **Total** | Gross, normal data, no SNS alert deliveries | **$67.90** |

Free tiers can reduce Lambda, CloudWatch, DynamoDB, Step Functions or other lines when still available to the account. They are shared with unrelated workloads and therefore are not subtracted from the control estimate.

### Why an alert storm is dangerous

The anomaly Lambda publishes once per anomalous event. A continuous `low_flow`, `blockage` or `shutdown` run can therefore attempt 7.776 million SNS publications and email deliveries in a month. The modeled SNS addition is **$159.41**: $3.89 in publish requests and $155.52 in email delivery, before free allowances or delivery throttling. It would also generate unusable customer notifications.

Do not run a non-normal scenario unattended. Before any long-running test, implement a per-pump/per-rule cooldown, state-change deduplication and a maximum notification rate. Alarm on publication count as well as spend.

### Highest-value cost changes

1. Change the ingest Lambda from one S3 object per event to one JSON Lines object per Lambda batch. At the modeled six events per batch, continuous S3 PUT cost falls from **$38.88 to $6.48/month**, and the total falls from **$67.90 to $35.50**.
2. M2 anomaly cooldown and state-change deduplication are implemented; keep unattended scenarios blocked until M4 adds cloud-owned expiry and drain controls. Cooldown removes the $159/month modeled alert-storm exposure, but not all runtime/cost risk.
3. Run the crawler only for schema-learning exercises or schema changes. Prefer explicit stable catalog tables and partition registration for routine publication; skipping 30 crawler runs saves up to **$4.40/month** in this model.
4. Start Glue only when new batch input exists. The current batch file is small, so repeating an unchanged job adds cost without producing new evidence.
5. Keep the dashboard local by default and cache reads. Do not query Athena on browser polling.
6. Destroy the realtime stack immediately after each demonstration and verify that the stream and both event-source mappings are absent.

### Frozen-state checklist

Frozen means the core stack may remain, while the realtime stack is absent and no Glue, crawler, Athena or simulator process is active. The $0.03 estimate assumes the documented storage envelope: S3 including CDK bootstrap <=1 GB, DynamoDB <=10 MB and retained logs <=100 MB. Every extra retained S3 GB adds about $0.023/month. `raw/batch/` and `curated/` currently have no automatic expiry, so inspect them rather than assuming frozen means zero.

After a demo, run the documented realtime stop command, verify deletion in AWS, check for active Glue/crawler executions, and inspect Cost Explorer when billing data arrives. S3 lifecycle expiry is asynchronous; recent raw objects can remain briefly after their configured age.

### Reproduce the estimate

The calculator contains every assumption and unit price:

```powershell
.\.venv\Scripts\python.exe scripts\estimate-cost.py parked
.\.venv\Scripts\python.exe scripts\estimate-cost.py demo --demos 2
.\.venv\Scripts\python.exe scripts\estimate-cost.py demo --demos 3
.\.venv\Scripts\python.exe scripts\estimate-cost.py daily-demo
.\.venv\Scripts\python.exe scripts\estimate-cost.py continuous
.\.venv\Scripts\python.exe scripts\estimate-cost.py continuous-batched-s3
.\.venv\Scripts\python.exe scripts\estimate-cost.py alert-storm
```

The calculator is intentionally deterministic and conservative. Update its prices when changing region or after AWS changes a price. Use `--json` to capture the estimate beside a cloud run record.

## Security and governance

### Current baseline

S3 blocks public access, uses SSE-S3 and enforces TLS. Workload code uses IAM roles and SDK credentials; no keys are embedded. Realtime read/failure-destination policies are attached from realtime and removed with it. Data remains in the selected region. The Glue role still uses the AWSGlueServiceRole managed policy and bucket-wide read/write access; this is a baseline to narrow, not a least-privilege completion claim.

### Target access matrix: M4

| Principal | Allowed | Must be denied |
|---|---|---|
| Producer | Put telemetry to the one stream | Read curated/customer data; delete stacks |
| Ingest | Write raw/quarantine; conditional update latest state | Modify curated publication |
| Detector | Read required state/rules; write alert history; publish one topic | Mutate analytics or infrastructure |
| Batch | Read approved raw/metadata; write run output; catalog operations | Read unrelated buckets |
| Local dashboard server | Bind to loopback; read allow-listed latest state and one approved KPI JSON location with operator credentials | LAN/public listener, raw/failure data, Kinesis, SNS publish, infrastructure writes |
| Local dashboard browser | Read the loopback API without receiving AWS credentials | Direct S3/DynamoDB access, AWS Console, environment/configuration secrets |
| Optional hosted Dashboard Lambda | Read allow-listed latest state and one approved KPI JSON location | Raw/failure data, Kinesis, SNS publish, infrastructure writes |
| Optional hosted customer | Read authenticated dashboard API | Direct S3/DynamoDB access or another customer's view |
| Analyst | Query approved catalog/workgroup and read approved data/results | Write raw, read quarantine, delete data |
| Expiry worker | Delete/inspect exact realtime stack and required owned resources | Delete core or unrelated deployments |
| Deployer | Manage this sandbox's project with reviewed changes | General production account access |

Use IAM Identity Center/temporary credentials for operators. Future CI deployment should use constrained OIDC roles and protected environments. The included CI only performs offline checks and has no AWS credentials.

### Negative evidence

Test access with the actual intended principal: producer reading S3 denied; analyst writing raw denied; wrong bucket denied; insecure S3 request denied; expiry worker deleting core denied. Save redacted policy/version and error evidence. Template assertions alone cannot establish effective authorization.

Optional governance lab: Lake Formation row/column access; KMS key-policy denial and recovery; synthetic PII masking. Cost and tear down these separately. Do not enable broad Macie scans, Config recorders or paid CloudTrail data events on the entire account just for this demo.

### Ownership, audit and privacy

Owner: capstone maintainer. Steward: demo operator. Data classification: synthetic public-shareable only after account IDs, emails and credentials are removed from artifacts. Customer telemetry must never be substituted without a separate data agreement and access design.

Maintain glossary, schema version, input lineage, published run, retention policy and deletion record. Application logs should contain IDs and counters rather than full payloads. CloudTrail event history can support management-operation review; it is not a substitute for deliberately configured data-access audit coverage.

No cross-region replication is in the base design. Region choice, deletion obligations and backup recovery belong in a customer deployment ADR. Full reset is irreversible without an export; current data resources are not production-protected.
