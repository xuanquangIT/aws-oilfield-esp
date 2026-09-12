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
    crawler = next(iter(core.find_resources("AWS::Glue::Crawler").values()))["Properties"]
    assert "/curated/silver/" in json.dumps(crawler["Targets"]["S3Targets"][0]["Path"])
    state_machine = next(iter(core.find_resources("AWS::StepFunctions::StateMachine").values()))[
        "Properties"
    ]
    definition = json.dumps(state_machine["DefinitionString"])
    assert "--RUN_ID.$" in definition
    assert "--INPUT_MANIFEST_KEY.$" in definition
