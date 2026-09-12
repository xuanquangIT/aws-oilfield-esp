"""M4 G4: read-only IAM simulation of essential denial boundaries.

This is deliberately an IAM-policy simulation, not a replacement for an
application smoke test.  It evaluates the actual deployed workload-role
policies and fails unless each listed unsafe action is denied.  The deployer
profile is intentionally not a test principal: it manages this sandbox and
therefore is expected to have wider permissions than runtime workloads.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import boto3


ROLE_LOGICAL_PREFIXES = {
    "processor": "StreamProcessorServiceRole",
    "anomaly": "AnomalyDetectorServiceRole",
    "expiry": "ExpiryReaperServiceRole",
}


def _role_arns(cloudformation, iam, core_stack: str) -> dict[str, str]:
    resources = cloudformation.list_stack_resources(StackName=core_stack)[
        "StackResourceSummaries"
    ]
    names: dict[str, str] = {}
    for kind, prefix in ROLE_LOGICAL_PREFIXES.items():
        match = next(
            (
                item
                for item in resources
                if item["ResourceType"] == "AWS::IAM::Role"
                and item["LogicalResourceId"].startswith(prefix)
            ),
            None,
        )
        if not match:
            raise RuntimeError(f"Could not find deployed {kind} role in {core_stack}")
        names[kind] = match["PhysicalResourceId"]
    return {kind: iam.get_role(RoleName=name)["Role"]["Arn"] for kind, name in names.items()}


def _cases(account: str, bucket: str, region: str, roles: dict[str, str]) -> list[dict]:
    return [
        {
            "name": "processor cannot read curated output",
            "principal": roles["processor"],
            "action": "s3:GetObject",
            "resource": f"arn:aws:s3:::{bucket}/curated/silver/private.parquet",
        },
        {
            "name": "processor cannot delete raw evidence",
            "principal": roles["processor"],
            "action": "s3:DeleteObject",
            "resource": f"arn:aws:s3:::{bucket}/raw/realtime/ESP-101/x.json",
        },
        {
            "name": "anomaly worker cannot write raw telemetry",
            "principal": roles["anomaly"],
            "action": "s3:PutObject",
            "resource": f"arn:aws:s3:::{bucket}/raw/realtime/ESP-101/x.json",
        },
        {
            "name": "expiry worker cannot delete core",
            "principal": roles["expiry"],
            "action": "cloudformation:DeleteStack",
            "resource": f"arn:aws:cloudformation:{region}:{account}:stack/oilfield-esp-core/*",
        },
        {
            "name": "expiry worker cannot pass unrelated roles",
            "principal": roles["expiry"],
            "action": "iam:PassRole",
            "resource": f"arn:aws:iam::{account}:role/oilfield-esp-unrelated",
        },
    ]


def run(core_stack: str, bucket: str, region: str) -> dict:
    session = boto3.session.Session(region_name=region)
    cfn = session.client("cloudformation")
    iam = session.client("iam")
    account = session.client("sts").get_caller_identity()["Account"]
    roles = _role_arns(cfn, iam, core_stack)
    results = []
    for case in _cases(account, bucket, region, roles):
        evaluation = iam.simulate_principal_policy(
            PolicySourceArn=case["principal"],
            ActionNames=[case["action"]],
            ResourceArns=[case["resource"]],
        )["EvaluationResults"][0]
        decision = evaluation["EvalDecision"]
        results.append({**case, "decision": decision})
    failures = [item for item in results if item["decision"] == "allowed"]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "core_stack": core_stack,
        "all_denied": not failures,
        "results": results,
        "unexpected_allows": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-stack", default="oilfield-esp-core")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--receipt")
    args = parser.parse_args()
    report = run(args.core_stack, args.bucket, args.region)
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.receipt:
        with open(args.receipt, "w", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
    if not report["all_denied"]:
        sys.exit("G4 FAILED: one or more prohibited actions evaluated as allowed")


if __name__ == "__main__":
    main()
