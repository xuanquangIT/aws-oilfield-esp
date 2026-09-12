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
                "src",
                exclude=[
                    "anomaly_detector",
                    "batch",
                    "expiry_reaper",
                    "**/__pycache__",
                ],
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
                "src",
                exclude=[
                    "stream_processor",
                    "batch",
                    "expiry_reaper",
                    "**/__pycache__",
                ],
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

        # M4: an independent one-shot expiry so a disposable realtime
        # stack cannot outlive its agreed deadline just because a laptop or
        # terminal disconnected. scripts/realtime-start.ps1 schedules one
        # EventBridge Scheduler invocation of this Lambda per demo (deleted
        # again on normal teardown); it is a safety net, not the normal
        # path. This role is deliberately narrow: it can request deletion
        # and inspect status for the named realtime stack, and nothing else.
        # CloudFormation, not this Lambda, owns the subordinate Kinesis,
        # Lambda mapping and IAM-policy cleanup -- see the target access matrix
        # in docs/05-COST-AND-SECURITY.md.
        realtime_stack_name = f"{project_prefix}-realtime"
        reaper = lambda_.Function(
            self,
            "ExpiryReaper",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="expiry_reaper.handler.handler",
            code=lambda_.Code.from_asset(
                "src",
                exclude=[
                    "stream_processor",
                    "anomaly_detector",
                    "batch",
                    "**/__pycache__",
                ],
            ),
            timeout=Duration.minutes(5),
            memory_size=128,
            environment={
                "ALERT_TOPIC_ARN": topic.topic_arn,
                "EXPECTED_REALTIME_STACK": realtime_stack_name,
            },
            log_group=logs.LogGroup(
                self,
                "ExpiryReaperLogs",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        topic.grant_publish(reaper)
        reaper.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudformation:DescribeStacks", "cloudformation:DeleteStack"],
                resources=[
                    f"arn:aws:cloudformation:{self.region}:{self.account}:stack/"
                    f"{realtime_stack_name}/*"
                ],
            )
        )
        scheduler_role = iam.Role(
            self,
            "ExpirySchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
        )
        reaper.grant_invoke(scheduler_role)

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
            # One deployment owns the whole scripts/ prefix. Separate
            # deployments at scripts/ and scripts/m3-lib/ caused the broader
            # deployment to prune contract.py after it was uploaded.
            sources=[
                s3deploy.Source.asset(
                    "src",
                    exclude=[
                        "anomaly_detector",
                        "stream_processor",
                        "expiry_reaper",
                        "**/__pycache__",
                    ],
                )
            ],
            destination_bucket=bucket,
            destination_key_prefix="scripts",
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
                script_location=f"s3://{bucket.bucket_name}/scripts/batch/transform.py",
            ),
            default_arguments={
                "--job-language": "python",
                "--DATA_BUCKET": bucket.bucket_name,
                "--extra-py-files": f"s3://{bucket.bucket_name}/scripts/contract.py",
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
            # Athena refuses to delete a workgroup that retains its own query
            # execution history, even when it has no named/prepared queries.
            # This project owns this workgroup and its result prefix, so a
            # destructive core reset must be able to remove those artifacts
            # without a manual console cleanup.
            recursive_delete_option=True,
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                enforce_work_group_configuration=True,
                bytes_scanned_cutoff_per_query=10 * 1024 * 1024,
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{bucket.bucket_name}/athena-results/"
                ),
            ),
        )

        crawler_arn = f"arn:aws:glue:{self.region}:{self.account}:crawler/{crawler.ref}"

        # M4: the state machine, not the CLI, owns completion end to end.
        # A publish run is not "done" until the crawler finishes; the wrapper
        # script is now a thin launcher/observer (see scripts/run-batch.ps1).
        get_crawler_before = tasks.CallAwsService(
            self,
            "GetCrawlerBeforeRun",
            service="glue",
            action="getCrawler",
            parameters={"Name": crawler.ref},
            iam_resources=[crawler_arn],
            result_path="$.crawler_before",
        )

        fail_concurrent_publish = sfn.Fail(
            self,
            "AnotherPublishRunInProgress",
            comment=(
                "Glue's max-concurrent-runs=1 rejected this execution because "
                "another M3 publish run is already in progress. This execution "
                "changed nothing; wait for the other run to finish (or fail) "
                "before retrying, or inspect the Glue console for the running job."
            ),
        )
        fail_glue = sfn.Fail(
            self,
            "BatchJobFailed",
            comment=(
                "Glue job failed, timed out or was denied after allowed retries. "
                "curated/publication/current.json is unchanged. Inspect "
                "staging/m3/<run_id>/quality-report.json (if it exists) and "
                "this execution's history for the cause."
            ),
        )
        fail_crawler = sfn.Fail(
            self,
            "CrawlerFailed",
            comment=(
                "Crawler run failed or was cancelled after the Glue job "
                "succeeded. curated/publication/current.json was already "
                "updated by Glue; rerun the crawler independently (it is a "
                "catalog-discovery step, not the approval gate) or inspect "
                "/aws-glue/crawlers logs."
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
            result_path=sfn.JsonPath.DISCARD,
        )
        # Bounded retry only for transient service errors on the synchronous
        # StartJobRun call itself. A real job failure (bad manifest, quality
        # gate) surfaces as a generic States.TaskFailed and is not retried;
        # retrying it would waste DPU-minutes reprocessing the same bad input.
        run_glue.add_retry(
            errors=[
                "Glue.AWSGlueException",
                "Glue.InternalServiceException",
                "States.Timeout",
            ],
            interval=Duration.seconds(30),
            max_attempts=2,
            backoff_rate=2.0,
        )
        # Evaluated in order: the specific overlap case gets its own clear
        # diagnostic before the catch-all, so operators can tell "someone
        # else is publishing" apart from "the job actually failed".
        run_glue.add_catch(
            fail_concurrent_publish,
            errors=["Glue.ConcurrentRunsExceededException"],
            result_path="$.glue_error",
        )
        run_glue.add_catch(fail_glue, errors=["States.ALL"], result_path="$.glue_error")

        start_crawler = tasks.CallAwsService(
            self,
            "StartCrawler",
            service="glue",
            action="startCrawler",
            parameters={"Name": crawler.ref},
            iam_resources=[crawler_arn],
            result_path=sfn.JsonPath.DISCARD,
        )
        # A crawler can only have one active run ever; retry the rare case
        # where a stray previous crawl is still finishing.
        start_crawler.add_retry(
            errors=["Glue.CrawlerRunningException"],
            interval=Duration.seconds(20),
            max_attempts=5,
            backoff_rate=1.5,
        )
        start_crawler.add_catch(
            fail_crawler, errors=["States.ALL"], result_path="$.crawler_error"
        )

        wait_for_crawler = sfn.Wait(
            self,
            "WaitForCrawler",
            time=sfn.WaitTime.duration(Duration.seconds(20)),
        )
        get_crawler_status = tasks.CallAwsService(
            self,
            "PollCrawler",
            service="glue",
            action="getCrawler",
            parameters={"Name": crawler.ref},
            iam_resources=[crawler_arn],
            result_path="$.crawler_status",
        )

        succeed = sfn.Succeed(self, "PublicationComplete")

        crawl_result_choice = sfn.Choice(self, "DidCrawlSucceed")
        crawl_result_choice.when(
            sfn.Condition.string_equals(
                "$.crawler_status.Crawler.LastCrawl.Status", "SUCCEEDED"
            ),
            succeed,
        )
        crawl_result_choice.otherwise(fail_crawler)

        # Choice rules are evaluated in the order added, first match wins, so
        # this correctly handles "never crawled before" (no LastCrawl to
        # compare) without a JSONPath error on a field that does not exist.
        crawler_ready_and_fresh = sfn.Choice(self, "IsCrawlerReadyAndFresh")
        crawler_ready_and_fresh.when(
            sfn.Condition.not_(
                sfn.Condition.string_equals("$.crawler_status.Crawler.State", "READY")
            ),
            wait_for_crawler,
        )
        crawler_ready_and_fresh.when(
            sfn.Condition.is_not_present("$.crawler_before.Crawler.LastCrawl"),
            crawl_result_choice,
        )
        crawler_ready_and_fresh.when(
            sfn.Condition.string_equals_json_path(
                "$.crawler_status.Crawler.LastCrawl.StartTime",
                "$.crawler_before.Crawler.LastCrawl.StartTime",
            ),
            wait_for_crawler,
        )
        crawler_ready_and_fresh.otherwise(crawl_result_choice)

        wait_for_crawler.next(get_crawler_status)
        get_crawler_status.next(crawler_ready_and_fresh)

        definition = (
            get_crawler_before.next(run_glue).next(start_crawler).next(wait_for_crawler)
        )
        state_machine = sfn.StateMachine(
            self,
            "BatchStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
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
        CfnOutput(self, "ExpiryReaperArn", value=reaper.function_arn)
        CfnOutput(self, "ExpirySchedulerRoleArn", value=scheduler_role.role_arn)
        self.processor = processor
        self.anomaly = anomaly
        self.data_bucket = bucket
