"""Offline assertions for cost, deletion boundaries and cross-stack wiring."""

import json

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infrastructure.core_stack import CoreStack
from infrastructure.realtime_stack import RealtimeStack


def stacks(tmp_path, context=None):
    app = cdk.App(outdir=str(tmp_path), context=context or {})
    core = CoreStack(app, "test-core", project_prefix="test-esp")
    realtime = RealtimeStack(app, "test-realtime", project_prefix="test-esp", core=core)
    app.synth()  # Also rejects circular stack references.
    return Template.from_stack(core), Template.from_stack(realtime)


def test_disposable_runtime_and_cost_guards(tmp_path):
    core, realtime = stacks(tmp_path)
    core.resource_count_is("AWS::Kinesis::Stream", 0)
    realtime.resource_count_is("AWS::Kinesis::Stream", 1)
    realtime.has_resource_properties(
        "AWS::Kinesis::Stream", {"ShardCount": 1, "RetentionPeriodHours": 24}
    )
    mappings = realtime.find_resources("AWS::Lambda::EventSourceMapping")
    assert len(mappings) == 2
    for resource in mappings.values():
        p = resource["Properties"]
        assert "Fn::ImportValue" in json.dumps(p["FunctionName"])
        assert p["MaximumRetryAttempts"] == 3
        assert p["MaximumRecordAgeInSeconds"] == 300
        assert p["DestinationConfig"]["OnFailure"]["Destination"]
        assert resource["DependsOn"]
    # Stream-specific IAM stays in realtime, avoiding core -> realtime dependency.
    assert "Fn::ImportValue" not in json.dumps(core.to_json())
    core.has_resource_properties(
        "AWS::Glue::Job",
        {"MaxRetries": 0, "ExecutionProperty": {"MaxConcurrentRuns": 1}, "Timeout": 10},
    )
    core.has_resource_properties("AWS::Events::Rule", {"State": "DISABLED"})
    core.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": Match.object_like(
                {"BlockPublicAcls": True, "BlockPublicPolicy": True}
            )
        },
    )
    core.resource_count_is("AWS::EC2::NatGateway", 0)
    core.has_resource_properties("AWS::Logs::LogGroup", {"RetentionInDays": 7})


def test_alert_cooldown_state_table_and_wiring(tmp_path):
    core, _ = stacks(tmp_path)
    core.resource_count_is("AWS::DynamoDB::Table", 2)
    core.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "KeySchema": [
                {"AttributeName": "esp_id", "KeyType": "HASH"},
                {"AttributeName": "rule_id", "KeyType": "RANGE"},
            ]
        },
    )
    core.has_resource_properties(
        "AWS::Lambda::Function", {"Handler": "anomaly_detector.handler.handler"}
    )
    core.has_resource_properties(
        "AWS::Lambda::Function", {"Handler": "stream_processor.handler.handler"}
    )


def test_m4_expiry_reaper_is_scoped_to_the_realtime_stack_only(tmp_path):
    """M4: the reaper can delete the named realtime stack and the specific
    resources CloudFormation deletes underneath it, and nothing broader --
    in particular, never the core stack or an unscoped iam:*/cloudformation:*."""
    core, _ = stacks(tmp_path)
    reaper_fn = next(
        r
        for r in core.find_resources("AWS::Lambda::Function").values()
        if r["Properties"].get("Handler") == "expiry_reaper.handler.handler"
    )
    assert reaper_fn["Properties"]["Timeout"] == 300

    policy = next(
        p
        for p in core.find_resources("AWS::IAM::Policy").values()
        if "ExpiryReaperServiceRole"
        in json.dumps(p.get("Properties", {}).get("Roles", []))
    )
    statements = policy["Properties"]["PolicyDocument"]["Statement"]
    text = json.dumps(statements)
    assert "cloudformation:DeleteStack" in text
    assert "-realtime/" in text
    # Never a bare service-wide grant, and never anything that could touch
    # the core stack's own CloudFormation resource.
    assert "cloudformation:*" not in text
    assert "iam:*" not in text
    # CloudFormation owns deletion of its subordinate stream/mappings.  The
    # reaper must never gain direct cleanup permissions as a workaround.
    for forbidden in (
        "kinesis:DeleteStream",
        "iam:DeleteRolePolicy",
        "lambda:DeleteEventSourceMapping",
        '\"Resource\": \"*\"',
    ):
        assert forbidden not in text
    for statement in statements:
        if statement["Action"] in (
            "cloudformation:DescribeStacks",
            ["cloudformation:DescribeStacks", "cloudformation:DeleteStack"],
        ) or (
            isinstance(statement["Action"], list)
            and "cloudformation:DeleteStack" in statement["Action"]
        ):
            resource_text = json.dumps(statement["Resource"])
            assert "-core" not in resource_text

    scheduler_role = next(
        r
        for r in core.find_resources("AWS::IAM::Role").values()
        if r["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Principal"][
            "Service"
        ]
        == "scheduler.amazonaws.com"
    )
    assert scheduler_role


def test_budget_email_is_explicit(tmp_path):
    core, _ = stacks(tmp_path, {"budget_email": "test@example.invalid"})
    budget = next(iter(core.find_resources("AWS::Budgets::Budget").values()))[
        "Properties"
    ]
    assert budget["Budget"]["CostFilters"] == {"TagKeyValue": ["user:Project$test-esp"]}
    assert [
        n["Notification"]["Threshold"] for n in budget["NotificationsWithSubscribers"]
    ] == [50, 100]


def test_core_resources_inherit_project_cost_allocation_tag(tmp_path):
    core, _ = stacks(tmp_path)
    glue_job = next(iter(core.find_resources("AWS::Glue::Job").values()))["Properties"]
    assert glue_job["Tags"]["Project"] == "test-esp"


def test_m3_glue_receives_manifest_arguments_and_crawls_silver(tmp_path):
    core, _ = stacks(tmp_path)
    glue_job = next(iter(core.find_resources("AWS::Glue::Job").values()))["Properties"]
    assert "--DATA_BUCKET" in glue_job["DefaultArguments"]
    assert "/scripts/contract.py" in json.dumps(
        glue_job["DefaultArguments"]["--extra-py-files"]
    )
    crawler = next(iter(core.find_resources("AWS::Glue::Crawler").values()))[
        "Properties"
    ]
    assert "/curated/silver/" in json.dumps(crawler["Targets"]["S3Targets"][0]["Path"])
    state_machine = next(
        iter(core.find_resources("AWS::StepFunctions::StateMachine").values())
    )["Properties"]
    definition = json.dumps(state_machine["DefinitionString"])
    assert "--RUN_ID.$" in definition
    assert "--INPUT_MANIFEST_KEY.$" in definition


def _state_machine_definition(core) -> dict:
    state_machine = next(
        iter(core.find_resources("AWS::StepFunctions::StateMachine").values())
    )["Properties"]
    # DefinitionString is an Fn::Join of literal fragments and Refs; the ASL
    # text lives in the literal string fragments, so concatenate those to
    # parse it without needing to resolve CloudFormation intrinsics.
    fragments = state_machine["DefinitionString"]["Fn::Join"][1]
    text = "".join(f for f in fragments if isinstance(f, str))
    return json.loads(text)


def test_m4_state_machine_owns_crawler_completion_end_to_end(tmp_path):
    """M4: the CLI is a launcher/observer; the state machine finishes the
    publish run (crawler start + poll-until-ready) without further client
    involvement, with bounded retry only for transient errors and an
    explicit terminal failure state for everything else."""
    core, _ = stacks(tmp_path)
    definition = _state_machine_definition(core)
    states = definition["States"]

    assert definition["StartAt"] == "GetCrawlerBeforeRun"
    assert states["GetCrawlerBeforeRun"]["Resource"].endswith("getCrawler")

    run_glue = states["RunGlue"]
    assert run_glue["Resource"].endswith("glue:startJobRun.sync")
    retry_errors = {e for r in run_glue["Retry"] for e in r["ErrorEquals"]}
    assert retry_errors == {
        "Glue.AWSGlueException",
        "Glue.InternalServiceException",
        "States.Timeout",
    }
    catch_targets = {tuple(c["ErrorEquals"]): c["Next"] for c in run_glue["Catch"]}
    assert catch_targets[("Glue.ConcurrentRunsExceededException",)] == (
        "AnotherPublishRunInProgress"
    )
    assert catch_targets[("States.ALL",)] == "BatchJobFailed"

    start_crawler = states["StartCrawler"]
    assert start_crawler["Resource"].endswith("startCrawler")
    assert start_crawler["Retry"][0]["ErrorEquals"] == ["Glue.CrawlerRunningException"]
    assert start_crawler["Catch"][0]["Next"] == "CrawlerFailed"

    assert states["WaitForCrawler"]["Type"] == "Wait"
    assert states["PollCrawler"]["Resource"].endswith("getCrawler")

    choice = states["IsCrawlerReadyAndFresh"]
    assert choice["Type"] == "Choice"
    # "Never crawled before" must be checked with IsPresent, not a direct
    # comparison, or a first-ever run would throw a JSONPath runtime error.
    never_crawled_rule = next(
        c
        for c in choice["Choices"]
        if c.get("Variable") == "$.crawler_before.Crawler.LastCrawl"
    )
    assert never_crawled_rule == {
        "Variable": "$.crawler_before.Crawler.LastCrawl",
        "IsPresent": False,
        "Next": "DidCrawlSucceed",
    }
    stale_rule = next(c for c in choice["Choices"] if "StringEqualsPath" in c)
    assert stale_rule["Next"] == "WaitForCrawler"
    assert choice["Default"] == "DidCrawlSucceed"

    did_crawl_succeed = states["DidCrawlSucceed"]
    assert did_crawl_succeed["Choices"][0]["StringEquals"] == "SUCCEEDED"
    assert did_crawl_succeed["Choices"][0]["Next"] == "PublicationComplete"
    assert did_crawl_succeed["Default"] == "CrawlerFailed"

    for terminal in ("CrawlerFailed", "AnotherPublishRunInProgress", "BatchJobFailed"):
        assert states[terminal]["Type"] == "Fail"
        assert states[terminal]["Comment"]
    assert states["PublicationComplete"]["Type"] == "Succeed"


def test_m4_state_machine_role_is_scoped_to_named_resources(tmp_path):
    """Least privilege: the orchestrator can only call getCrawler/
    startCrawler on this one crawler and StartJobRun/GetJobRun*/
    BatchStopJobRun on this one job -- never a bare glue:* grant."""
    core, _ = stacks(tmp_path)
    policy = next(
        p
        for p in core.find_resources("AWS::IAM::Policy").values()
        if "BatchStateMachineRole"
        in json.dumps(p.get("Properties", {}).get("Roles", []))
    )
    statements = policy["Properties"]["PolicyDocument"]["Statement"]
    actions = set()
    for statement in statements:
        action = statement["Action"]
        actions.update(action if isinstance(action, list) else [action])
    assert actions == {
        "glue:getCrawler",
        "glue:startCrawler",
        "glue:StartJobRun",
        "glue:GetJobRun",
        "glue:GetJobRuns",
        "glue:BatchStopJobRun",
    }
    assert "glue:*" not in json.dumps(statements)
