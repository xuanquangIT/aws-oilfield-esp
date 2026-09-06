# Sources and references

Reviewed 2026-09-06. Sources support service/exam behavior; the project design, cost allowance and acceptance targets are engineering proposals. Prices and exam scope can change. Follow the English current guide rather than older static PDFs with different weights.

## AWS and certification

| Topic | Source |
|---|---|
| DEA-C01 scope and weights | [Exam guide](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01.html) |
| Ingestion/transformation | [Domain 1](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain1.html) |
| Data stores | [Domain 2](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain2.html) |
| Operations/quality | [Domain 3](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain3.html) |
| Security/governance | [Domain 4](https://docs.aws.amazon.com/aws-certification/latest/data-engineer-associate-01/data-engineer-associate-01-domain4.html) |
| Kinesis capacity pricing | [Pricing](https://aws.amazon.com/kinesis/data-streams/pricing/) |
| S3 storage and requests | [Pricing](https://aws.amazon.com/s3/pricing/) |
| DynamoDB on-demand requests and storage | [Pricing](https://aws.amazon.com/dynamodb/pricing/) |
| Lambda requests and duration | [Pricing](https://aws.amazon.com/lambda/pricing/) |
| Glue ETL/crawler/catalog charges | [Pricing](https://aws.amazon.com/glue/pricing/) |
| Glue crawler billing minimum | [AWS data-lake cost model](https://docs.aws.amazon.com/pdfs/whitepapers/latest/cost-modeling-data-lakes/cost-modeling-data-lakes.pdf) |
| Athena scan pricing and query minimum | [Pricing](https://aws.amazon.com/athena/pricing/) |
| Step Functions transitions | [Pricing](https://aws.amazon.com/step-functions/pricing/) |
| CloudWatch Logs | [Pricing](https://aws.amazon.com/cloudwatch/pricing/) |
| SNS requests and email delivery | [Pricing FAQ](https://aws.amazon.com/sns/faqs/) |
| AWS Budgets | [Pricing](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/) |
| Budget timing and limitations | [Budget guide](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html) |
| Failed Kinesis Lambda batches | [S3 failure destinations](https://docs.aws.amazon.com/lambda/latest/dg/kinesis-on-failure-destination.html) |
| Stateful streaming cost comparison | [Managed Flink pricing](https://aws.amazon.com/managed-service-apache-flink/pricing/) |
| Dashboard HTTP API pricing | [API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/) |
| Private static dashboard origin | [CloudFront S3 Origin Access Control](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/GettingStarted.SimpleDistribution.html) |
| Dashboard delivery pricing | [CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/) |
| Dashboard authentication pricing | [Amazon Cognito pricing](https://aws.amazon.com/cognito/pricing/) |

## Equipment and telemetry context

These references explain representative signal origins. They do not certify the simulator or turn its normalized synthetic events into vendor telemetry.

| Topic | Source |
|---|---|
| Downhole intake, temperature, vibration and optional discharge signals | [SLB Phoenix xt150](https://www.slb.com/zh-cn/products-and-services/innovating-in-oil-and-gas/completions/artificial-lift/intelligent-lift/gauges/phoenix-xt150-downhole-monitoring-system) |
| ESP motor context | [REDA Maximus motor](https://www.slb.com/-/media/files/al/product-sheet/reda-maximus-bolt-on-motors-ps.ashx) |
| Dedicated flow and water-cut monitoring | [SLB FloWatcher](https://www.slb.com/products-and-services/innovating-in-oil-and-gas/completions/well-completions/permanent-monitoring/permanent-downhole-gauges/flowatcher-monitoring-system) |
| VFD output current and frequency | [Rockwell PowerFlex manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/22d-um001_-en-e.pdf) |
| ESP VSD operating context | [SLB VSD overview](https://www.slb.com/-/media/files/oilfield-review/p30-43-2) |
| Surface tubing/casing pressure context | [Emerson production case study](https://www.emerson.com/en/measurement-instrumentation/industries/oil-and-gas/oil-production-company-increases-operational-efficiency-by-reducing-time-spent-at-wellsite) |
| Surface multiphase flow measurement | [SLB Vx Spectra](https://www.slb.com/es/products-and-services/innovating-in-oil-and-gas/reservoir-characterization/reservoir-testing/surface-testing/surface-multiphase-flowmetering/vx-spectra-surface-multiphase-flowmeter) |
| Virtual-rate workflow using ESP gauge data | [SPE-145542](https://www.slb.com/resource-library/technical-paper/al/spe-145542) |
| SCADA state and alarm/event context | [AVEVA Plant SCADA](https://www.aveva.com/content/dam/aveva/documents/onesheet/OneSheet_AVEVA_PlantSCADA-2003R2What%27sNew_24-01.pdf) |

Before AWS release, refresh selected-region service prices and runtime support, review the actual CDK diff and test the chosen account's permissions/quotas. Published examples are not a quote for this deployment. Equipment references establish terminology and representative provenance only; the simulator remains synthetic and uncalibrated.
