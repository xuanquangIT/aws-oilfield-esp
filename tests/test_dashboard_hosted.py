"""Offline security tests for the optional hosted dashboard boundary."""

import json

import aws_cdk as cdk
from aws_cdk.assertions import Template

from infrastructure.core_stack import CoreStack
from infrastructure.dashboard_hosted_stack import DashboardHostedStack


def hosted_template(tmp_path):
    app = cdk.App(outdir=str(tmp_path))
    core = CoreStack(app, "test-core", project_prefix="test-esp")
    hosted = DashboardHostedStack(app, "test-dashboard-hosted", project_prefix="test-esp", core=core)
    app.synth()
    return Template.from_stack(hosted)


def test_hosted_dashboard_has_no_always_on_compute_or_public_s3(tmp_path):
    template = hosted_template(tmp_path)
    template.resource_count_is("AWS::EC2::NatGateway", 0)
    template.resource_count_is("AWS::ElasticLoadBalancingV2::LoadBalancer", 0)
    template.resource_count_is("AWS::Kinesis::Stream", 0)
    bucket = next(iter(template.find_resources("AWS::S3::Bucket").values()))["Properties"]
    assert bucket["PublicAccessBlockConfiguration"]["BlockPublicPolicy"] is True
    assert bucket["BucketEncryption"]["ServerSideEncryptionConfiguration"]
    assert template.find_resources("AWS::CloudFront::OriginAccessControl")


def test_hosted_api_is_jwt_protected_and_lambda_is_read_only(tmp_path):
    template = hosted_template(tmp_path)
    routes = template.find_resources("AWS::ApiGatewayV2::Route")
    protected = [r["Properties"] for r in routes.values() if r["Properties"].get("RouteKey") != "GET /api/v1/config"]
    assert protected and all(route["AuthorizationType"] == "JWT" for route in protected)
    policies = template.find_resources("AWS::IAM::Policy")
    read_policy = next(p["Properties"]["PolicyDocument"] for p in policies.values() if "ReadApiServiceRole" in json.dumps(p["Properties"].get("Roles", [])))
    policy_text = json.dumps(read_policy)
    assert "dynamodb:BatchGetItem" in policy_text and "s3:GetObject" in policy_text
    for forbidden in ("dynamodb:Scan", "kinesis:", "sns:", "cloudformation:", "s3:PutObject"):
        assert forbidden not in policy_text


def test_github_oidc_trust_is_pinned_to_protected_environment(tmp_path):
    template = hosted_template(tmp_path)
    role = next(
        value["Properties"] for value in template.find_resources("AWS::IAM::Role").values()
        if "GitHub Actions OIDC entry role" in value["Properties"].get("Description", "")
    )
    trust = json.dumps(role["AssumeRolePolicyDocument"])
    assert "token.actions.githubusercontent.com" in trust
    assert "repo:xuanquangIT/aws-oilfield-esp:environment:dashboard-production" in trust
    policy = next(
        value["Properties"]["PolicyDocument"] for value in template.find_resources("AWS::IAM::Policy").values()
        if "GitHubDeployRole" in json.dumps(value["Properties"].get("Roles", []))
    )
    action = json.loads(json.dumps(policy))["Statement"][0]["Action"]
    assert ({action} if isinstance(action, str) else set(action)) == {"sts:AssumeRole"}
