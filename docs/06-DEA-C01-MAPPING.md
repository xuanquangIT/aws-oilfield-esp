# AWS DEA-C01 coverage

Official English guide reviewed 2026-09-05: domains carry **34%, 26%, 22%, 18%**. This matrix addresses every task group, not every possible exam question or every service. Current scope includes topics beyond this small runtime; do those as isolated labs or design exercises. [Exam guide](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01.html).

**Code** = present but not cloud-proven. **Plan** = implementation required. **Lab** = optional isolated exercise. **Study** = explain/design without deploying. Evidence must carry one of these labels; no service-count-based readiness score.

| Task | Current basis | Required project evidence / next exercise |
|---|---|---|
| 1.1 Ingestion | Code: CSV, Kinesis, two consumers | M2 duplicate/late/invalid/replay drill; Lab compare DMS CDC, API pagination and Firehose |
| 1.2 Transformation | Code: Spark CSV -> Parquet and derived oil rate | M3 union/join, normalization, rejects, performance comparison; Study LLM enrichment boundaries |
| 1.3 Orchestration | Code: Glue task, client-side crawler | M4 cloud-owned publish workflow, retry/catch and controlled failure |
| 1.4 Programming | Code: Python, CDK, PowerShell, offline CI | Tests and locked dependencies; explain partition parallelism and deployment change review |
| 2.1 Store selection | Code: S3 history, DynamoDB latest state | ADR access-pattern comparison; Lab Iceberg; Study Redshift/RDS, vectors HNSW/IVF |
| 2.2 Catalogs | Code: crawler and Glue database | M3 stable schema/partitions; Study business catalog ownership and SageMaker Catalog |
| 2.3 Lifecycle | Code: S3 expiry, explicit reset | M4 export/restore and residual inventory; Lab TTL/versioning and deletion policy |
| 2.4 Modeling/evolution | Code: flat telemetry/date partitions | M1 v1/v2 contract fixture; M3 pump dimension and lineage; Study vectorization |
| 3.1 Automation | Code: SDK producer and lifecycle wrappers | M4 automated completion with laptop disconnected; Lab API/backoff |
| 3.2 Analysis | Code: Athena SQL templates | M5 KPI report; measured scan savings and missing-data interpretation |
| 3.3 Monitoring/support | Code: retained app logs; failure payloads | M4 alarm/recovery evidence, correlation IDs and CloudTrail review |
| 3.4 Quality | Plan: quality contract and SQL checks | M1/M3 rejected rows, freshness, reconciliation, skew and rerun tests |
| 4.1 Authentication | Code: workload roles; profile instructions | M4 temporary credentials / denied expired session; Study VPC endpoints and rotation |
| 4.2 Authorization | Code: scoped resources; broad Glue managed baseline | M4 publisher/analyst negative tests; Lab Lake Formation row/column access |
| 4.3 Encryption/masking | Code: S3 encryption and TLS | M4 denied insecure request; Lab KMS key-policy failure and synthetic masking |
| 4.4 Audit | Code: application log groups | M4 deploy/query attribution; Lab CloudTrail evidence and query; cost scope recorded |
| 4.5 Governance | Study: synthetic data, region and ownership policy | M4 glossary/lineage/deletion record; Study Macie, Config, sovereignty and sharing |

Domain references: [D1](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain1.html), [D2](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain2.html), [D3](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain3.html), [D4](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain4.html).

## Coverage outside the base runtime

Use [M6 labs](15-LEARNING-LABS.md) for warehouse design and Redshift SQL/COPY/Spectrum, CDC ordering and delete events, Flink windows/watermarks/checkpoints, Lake Formation governance, KMS, Iceberg and migration. Compare Glue/EMR, Step Functions/Airflow, Kinesis/MSK/Firehose, S3/warehouse/key-value stores based on latency, access pattern and cost.

The current guide also includes LLM processing, open table formats, vector indexes/vectorization, SageMaker Catalog and Unified Studio. Explain these through a maintenance-note enrichment and searchable pump-document scenario; no paid AI endpoint is required for the core demo. Recheck the official guide before booking an exam.

## Completion rule

For each task, link an artifact plus a short explanation of service choice, failure mode, recovery and cost. A study-only entry may close a learning exercise, but cannot be relabeled as AWS hands-on evidence. Preserve remaining subskills in the learning backlog rather than claiming 100% certification coverage.
