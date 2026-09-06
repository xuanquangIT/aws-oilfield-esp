# Official references

Reviewed 2026-09-06. Sources support service/exam behavior; the project design, cost allowance and acceptance targets are engineering proposals. Prices and exam scope can change. Follow the English current guide rather than older static PDFs with different weights.

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

Before AWS release, refresh selected-region service prices and runtime support, review the actual CDK diff and test the chosen account's permissions/quotas. Published examples are not a quote for this deployment.
