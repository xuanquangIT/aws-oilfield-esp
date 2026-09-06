# Security and governance

## Current baseline

S3 blocks public access, uses SSE-S3 and enforces TLS. Workload code uses IAM roles and SDK credentials; no keys are embedded. Realtime read/failure-destination policies are attached from realtime and removed with it. Data remains in the selected region. The Glue role still uses the AWSGlueServiceRole managed policy and bucket-wide read/write access; this is a baseline to narrow, not a least-privilege completion claim.

## Target access matrix: M4

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

## Negative evidence

Test access with the actual intended principal: producer reading S3 denied; analyst writing raw denied; wrong bucket denied; insecure S3 request denied; expiry worker deleting core denied. Save redacted policy/version and error evidence. Template assertions alone cannot establish effective authorization.

Optional governance lab: Lake Formation row/column access; KMS key-policy denial and recovery; synthetic PII masking. Cost and tear down these separately. Do not enable broad Macie scans, Config recorders or paid CloudTrail data events on the entire account just for this demo.

## Ownership, audit and privacy

Owner: capstone maintainer. Steward: demo operator. Data classification: synthetic public-shareable only after account IDs, emails and credentials are removed from artifacts. Customer telemetry must never be substituted without a separate data agreement and access design.

Maintain glossary, schema version, input lineage, published run, retention policy and deletion record. Application logs should contain IDs and counters rather than full payloads. CloudTrail event history can support management-operation review; it is not a substitute for deliberately configured data-access audit coverage.

No cross-region replication is in the base design. Region choice, deletion obligations and backup recovery belong in a customer deployment ADR. Full reset is irreversible without an export; current data resources are not production-protected.
