# Cost control

## Operating states

| State | What remains | Cost interpretation |
|---|---|---|
| Local | Files, tests, generated fixtures | No AWS charge from these operations |
| Parked | Core metadata/functions plus bounded S3/DynamoDB/log data | Small storage and any incidental requests; not guaranteed zero |
| Demo | Parked resources + Kinesis + active Lambda/Glue/Athena | Billed usage; remove realtime afterward |
| Reset | Project stacks removed | Bootstrap storage, service-created logs and unrelated account services can remain |

Target parked storage envelope: total S3 including bootstrap <=1 GB, DynamoDB <=10 MB, logs <=100 MB, no recurring compute. **Target under USD 1/month for project idle footprint**, excluding unrelated services, tax, data transfer and unmeasured residuals. This is an engineering target requiring a billing observation, not an estimate guaranteed by the stack.

## Planning estimate

The detailed, reproducible scenario model is in [monthly cost estimate](18-MONTHLY-COST-ESTIMATE.md). Current gross estimates are about **$0.03 parked**, **$0.66 for two demos**, **$0.97 for three demos**, **$9.46 for one full demo per day**, and **$67.90 for continuous streaming plus daily batch**. Credits and shared free-tier allowances are excluded.

Assume us-east-1, three approximately 1 KB records/second, one five-minute demo, one Glue run of up to ten billed minutes at two DPUs, and ten small SQL queries. Ignore credits/free-tier eligibility when planning.

| Item | Calculation / method |
|---|---|
| Stream | Provisioned shard billed duration × regional shard-hour price + PUT units; include deploy, grace and delete time and billing rounding |
| Glue | 2 DPUs × 10/60 hour × illustrative USD 0.44/DPU-hour = about USD 0.147 for ETL alone |
| Crawler | Billed DPUs × duration and crawler minimum; add separately to ETL |
| S3 raw writes | Approximately 900 events per five nominal minutes; current producer/API overhead affects count |
| Lambda / DynamoDB / SNS | Two consumers; count retries and repeated alert publications |
| Athena | Sum billed bytes per query × regional scan price; each query can have minimum billable bytes |
| Storage | Bytes retained across data, failure payloads, results, logs and bootstrap assets |

The modeled current-code cost is about USD 0.31 per short full rehearsal. Reserve **USD 0.50 per rehearsal**, use USD 1.50 as the project target for three monthly demos, and retain the existing USD 5 account-wide alert. These are control allowances, not hard maximums. Repeated retries, alert storms, abandoned streams or larger data can exceed them.

Glue's USD 0.44 figure is an illustrative published rate; region, execution class and minimum billing rules matter. [Glue pricing](https://aws.amazon.com/glue/pricing/). Check capacity modes and region on [Kinesis pricing](https://aws.amazon.com/kinesis/data-streams/pricing/) before deployment. On-demand Advantage has a commitment unsuitable for this tiny intermittent baseline.

## Implemented controls

- One provisioned shard; 24-hour stream retention; no enhanced fan-out.
- Realtime wrapper attempts teardown in finally; explicit recovery stop command.
- Glue two G.1X workers, ten-minute timeout, zero job retries, one concurrent run.
- Daily trigger disabled; no notebook, Spark session or scheduled compactor.
- Athena enforced workgroup with 10 MiB scan cutoff per query.
- Raw realtime expires after 7 days; failed invocation payloads after 14 days; query results after 1 day.
- Incomplete multipart uploads aborted after 1 day; application Lambda logs expire after 7 days.
- USD 5 account-wide budget; optional email alerts at 50% and 100% actual spend.

No automatic expiry yet exists for raw/batch or curated data. They must remain inside the storage envelope or be explicitly exported and removed. Glue and CDK provider-created logs need separate inspection.

## Gaps to close before unattended use

A finally block cannot handle laptop loss, killed process or expired credentials. M4 adds a cloud-side one-shot expiry workflow that deletes only the named realtime stack after a lease, then verifies deletion and reports failure. It must be independent of the laptop and must never delete core. Until tested, run supervised demos only.

AWS Budgets can notify after spend has already passed a threshold. It cannot stop spend by itself. [Budget limitations](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html).

## Review after each rehearsal

Record stack creation/deletion timestamps, Glue billed duration, Athena bytes scanned, object sizes/counts, log bytes and eventual billing evidence in the [run record](../evidence/templates/cloud-run.json). Reconcile later when billing data is available; do not record an unavailable cost as zero.

Keep NAT Gateway, provisioned concurrency, managed notebooks, MWAA, OpenSearch, managed Kafka, persistent warehouses and paid BI subscriptions outside the baseline. Do not enable paid data-event trails, KMS customer keys or cross-region replication merely to populate an architecture diagram.

## Phase 1 web dashboard cost boundary

The Phase 1 dashboard is required, but its default deployment profile is local. HTML, CSS, JavaScript and the small read API run on the operator's laptop and bind to localhost. This creates no new CloudFront, API Gateway, Cognito, Lambda, container, VM or S3 web-assets resource and therefore no new fixed AWS dashboard charge.

The local API performs one batched DynamoDB read for the known ESP IDs no more frequently than the 10–15 second cache window. It fetches the approved KPI JSON from S3 only when the publication identifier changes or on an explicit refresh. It does not scan DynamoDB, query Athena from a polling loop, stream raw objects to the browser, or create custom CloudWatch metrics. These choices minimize requests but cannot guarantee zero incremental request cost.

Measure a 60-minute local dashboard rehearsal: number of polls, cache hits, DynamoDB read requests/capacity, S3 GET/LIST requests, bytes transferred and observed billing when available. Keep `dashboard incremental cost` separate from existing ingestion costs; an unavailable bill is not zero.

The optional hosted profile uses CloudFront, a private S3 web-assets bucket, API Gateway HTTP API, Cognito and a read-only Lambda. It is excluded from the parked baseline, deployed only when an external customer link is needed, and destroyed after the evidence window. API Gateway HTTP APIs are request-priced with no minimum fee; CloudFront publishes a Free plan with usage allowances, but S3, Lambda, DynamoDB, Cognito and overage remain measurable usage. [API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/), [CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/), [Athena pricing](https://aws.amazon.com/athena/pricing/).

Do not enable QuickSight as a baseline component: its user subscriptions conflict with the no-new-fixed-cost goal. See the [dashboard design](17-REALTIME-WEB-DASHBOARD.md).
