"""Disposable stream, consumer mappings and stream-specific IAM policies."""

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_kinesis as kinesis,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from constructs import Construct


class RealtimeStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, project_prefix: str, core, **kwargs
    ):
        super().__init__(scope, construct_id, **kwargs)
        stream = kinesis.Stream(
            self,
            "TelemetryStream",
            stream_name=f"{project_prefix}-realtime",
            stream_mode=kinesis.StreamMode.PROVISIONED,
            shard_count=1,
            retention_period=Duration.hours(24),
            removal_policy=RemovalPolicy.DESTROY,
        )
        for name, function in (
            ("Processor", core.processor),
            ("Anomaly", core.anomaly),
        ):
            # Own policies here: core must never depend on the disposable stream.
            policy = iam.Policy(
                self,
                f"{name}StreamPolicy",
                roles=[function.role],
                statements=[
                    iam.PolicyStatement(
                        actions=[
                            "kinesis:DescribeStream",
                            "kinesis:DescribeStreamSummary",
                            "kinesis:GetRecords",
                            "kinesis:GetShardIterator",
                            "kinesis:ListShards",
                        ],
                        resources=[stream.stream_arn],
                    ),
                    iam.PolicyStatement(
                        actions=["s3:PutObject"],
                        resources=[core.data_bucket.arn_for_objects("*")],
                        conditions={
                            "StringEquals": {"s3:ResourceAccount": self.account}
                        },
                    ),
                    iam.PolicyStatement(
                        actions=["s3:ListBucket"],
                        resources=[core.data_bucket.bucket_arn],
                    ),
                ],
            )
            mapping = lambda_.CfnEventSourceMapping(
                self,
                f"{name}Mapping",
                function_name=function.function_arn,
                event_source_arn=stream.stream_arn,
                starting_position="TRIM_HORIZON",
                batch_size=10,
                maximum_batching_window_in_seconds=2,
                bisect_batch_on_function_error=True,
                maximum_retry_attempts=3,
                maximum_record_age_in_seconds=300,
                destination_config=lambda_.CfnEventSourceMapping.DestinationConfigProperty(
                    on_failure=lambda_.CfnEventSourceMapping.OnFailureProperty(
                        destination=core.data_bucket.bucket_arn
                    )
                ),
            )
            mapping.node.add_dependency(policy)
        for key, value in {
            "Project": project_prefix,
            "Environment": "demo",
            "Lifecycle": "ephemeral",
            "CostCenter": "realtime",
        }.items():
            Tags.of(self).add(key, value)
        CfnOutput(self, "RealtimeStreamName", value=stream.stream_name)
