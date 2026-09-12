from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import (
    aws_athena as athena,
)
from aws_cdk import (
    aws_budgets as budgets,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_events as events,
)
from aws_cdk import (
    aws_events_targets as targets,
)
from aws_cdk import (
    aws_glue as glue,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_s3_deployment as s3deploy,
)
from aws_cdk import (
    aws_sns as sns,
)
from aws_cdk import (
    aws_stepfunctions as sfn,
)
from aws_cdk import (
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct


class CoreStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, project_prefix: str, **kwargs
    ):
        super().__init__(scope, construct_id, **kwargs)

        # Apply the project boundary to every taggable core resource so Billing
        # can attribute its eligible charges to this project.
        for key, value in {
            "Project": project_prefix,
            "Environment": "portfolio",
            "Lifecycle": "persistent",
            "CostCenter": "demo",
        }.items():
            Tags.of(self).add(key, value)

        bucket = s3.Bucket(
            self,
            "DataBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireRawRealtime",
                    prefix="raw/realtime/",
                    expiration=Duration.days(7),
                ),
                s3.LifecycleRule(
                    id="ExpireAthena",
                    prefix="athena-results/",
                    expiration=Duration.days(1),
                ),
                s3.LifecycleRule(
                    id="ExpireFailedInvocations",
                    prefix="aws/lambda/",
                    expiration=Duration.days(14),
                ),
                s3.LifecycleRule(
                    id="AbortUploads",
                    abort_incomplete_multipart_upload_after=Duration.days(1),
                ),
            ],
        )

        state = dynamodb.Table(
            self,
            "LatestState",
            partition_key=dynamodb.Attribute(
                name="esp_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Per-(esp_id, rule_id) alert cooldown/recovery outbox for the
        # AnomalyDetector Lambda (M2). See src/anomaly_detector/handler.py.
        alert_state = dynamodb.Table(
            self,
            "AlertState",
            partition_key=dynamodb.Attribute(
                name="esp_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="rule_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        topic = sns.Topic(self, "Alerts", display_name="ESP anomaly alerts")

        processor = lambda_.Function(
            self,
            "StreamProcessor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="stream_processor.handler.handler",
            # Bundled from src/ (not src/stream_processor/) so the shared
            # contract.py module is available at runtime as a top-level
            # import, matching how tests/conftest.py exposes it locally.
            code=lambda_.Code.from_asset(
                "src", exclude=["anomaly_detector", "batch", "**/__pycache__"]
            ),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "DATA_BUCKET": bucket.bucket_name,
                "STATE_TABLE": state.table_name,
            },
            log_group=logs.LogGroup(
                self,
                "ProcessorLogs",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        bucket.grant_put(processor)
        state.grant_write_data(processor)

        anomaly = lambda_.Function(
            self,
            "AnomalyDetector",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="anomaly_detector.handler.handler",
            # Bundled from src/ (not src/anomaly_detector/) so the shared
            # contract.py module is available at runtime as a top-level
            # import, matching StreamProcessor's bundling (see below) and
            # tests/conftest.py's local import resolution.
            code=lambda_.Code.from_asset(
                "src", exclude=["stream_processor", "batch", "**/__pycache__"]
            ),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "ALERT_TOPIC_ARN": topic.topic_arn,
                "ALERT_STATE_TABLE": alert_state.table_name,
                "ALERT_COOLDOWN_SECONDS": "300",
            },
            log_group=logs.LogGroup(
                self,
                "AnomalyLogs",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        topic.grant_publish(anomaly)
        alert_state.grant_read_write_data(anomaly)

        role = iam.Role(
            self,
            "GlueRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSGlueServiceRole"
                )
            ],
        )
        bucket.grant_read_write(role)

        s3deploy.BucketDeployment(
            self,
            "GlueScript",
            sources=[s3deploy.Source.asset("src/batch")],
            destination_bucket=bucket,
            destination_key_prefix="scripts",
        )
        # Glue receives the contract as an extra Python file so M3 validates
        # historical CSV and archived realtime JSON with the same v1 rules as
        # the producer and stream processor.
        s3deploy.BucketDeployment(
            self,
            "GlueContract",
            sources=[
                s3deploy.Source.asset(
                    "src",
                    exclude=[
                        "anomaly_detector",
                        "stream_processor",
                        "batch",
                        "**/__pycache__",
                    ],
                )
            ],
            destination_bucket=bucket,
            destination_key_prefix="scripts/m3-lib",
        )

        database = glue.CfnDatabase(
            self,
            "Database",
            catalog_id=self.account,
            database_input={"name": f"{project_prefix.replace('-', '_')}_db"},
        )

        job = glue.CfnJob(
            self,
            "BatchJob",
            name=f"{project_prefix}-batch",
            role=role.role_arn,
            glue_version="5.0",
            worker_type="G.1X",
            number_of_workers=2,
            timeout=10,
            max_retries=0,
            execution_property=glue.CfnJob.ExecutionPropertyProperty(
                max_concurrent_runs=1
            ),
            command=glue.CfnJob.JobCommandProperty(
                name="glueetl",
                python_version="3",
                script_location=f"s3://{bucket.bucket_name}/scripts/transform.py",
            ),
            default_arguments={
                "--job-language": "python",
                "--DATA_BUCKET": bucket.bucket_name,
                "--extra-py-files": f"s3://{bucket.bucket_name}/scripts/m3-lib/contract.py",
            },
        )

        crawler = glue.CfnCrawler(
            self,
            "Crawler",
            name=f"{project_prefix}-crawler",
            role=role.role_arn,
            database_name=database.ref,
            targets={
                "s3Targets": [{"path": f"s3://{bucket.bucket_name}/curated/silver/"}]
            },
            schema_change_policy={
                "updateBehavior": "UPDATE_IN_DATABASE",
                "deleteBehavior": "LOG",
            },
        )
        crawler.add_resource_dependency(job)

        workgroup = athena.CfnWorkGroup(
            self,
            "AthenaWorkGroup",
            name=f"{project_prefix}-wg",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                enforce_work_group_configuration=True,
                bytes_scanned_cutoff_per_query=10 * 1024 * 1024,
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{bucket.bucket_name}/athena-results/"
                ),
            ),
        )

        run_glue = tasks.GlueStartJobRun(
            self,
            "RunGlue",
            glue_job_name=job.ref,
            arguments=sfn.TaskInput.from_object(
                {
                    "--RUN_ID": sfn.JsonPath.string_at("$.run_id"),
                    "--INPUT_MANIFEST_KEY": sfn.JsonPath.string_at(
                        "$.input_manifest_key"
                    ),
                }
            ),
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,
        )
        state_machine = sfn.StateMachine(
            self,
            "BatchStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(run_glue),
            timeout=Duration.minutes(15),
        )

        events.Rule(
            self,
            "DailySchedule",
            enabled=False,
            schedule=events.Schedule.rate(Duration.days(1)),
            targets=[targets.SfnStateMachine(state_machine)],
        )

        budget_email = self.node.try_get_context("budget_email")
        notifications = None
        if budget_email:
            notifications = [
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        comparison_operator="GREATER_THAN",
                        notification_type="ACTUAL",
                        threshold=threshold,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            address=budget_email, subscription_type="EMAIL"
                        )
                    ],
                )
                for threshold in (50, 100)
            ]
        budgets.CfnBudget(
            self,
            "MonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                cost_filters={"TagKeyValue": [f"user:Project${project_prefix}"]},
                budget_limit=budgets.CfnBudget.SpendProperty(amount=5.0, unit="USD"),
            ),
            notifications_with_subscribers=notifications,
        )

        CfnOutput(self, "DataBucketName", value=bucket.bucket_name)
        CfnOutput(self, "StateTableName", value=state.table_name)
        CfnOutput(self, "AlertStateTableName", value=alert_state.table_name)
        CfnOutput(self, "AlertTopicArn", value=topic.topic_arn)
        CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
        CfnOutput(self, "GlueCrawlerName", value=crawler.ref)
        workgroup_output = CfnOutput(
            self, "AthenaWorkGroupOutput", value=workgroup.name
        )
        workgroup_output.override_logical_id("AthenaWorkGroup")
        CfnOutput(self, "GlueJobName", value=job.ref)
        CfnOutput(self, "GlueDatabaseName", value=database.ref)
        self.processor = processor
        self.anomaly = anomaly
        self.data_bucket = bucket
