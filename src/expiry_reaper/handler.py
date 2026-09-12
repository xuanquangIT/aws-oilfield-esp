"""M4: independent one-shot expiry for the disposable realtime stack.

A one-time EventBridge Scheduler schedule (created by
``scripts/realtime-start.ps1`` alongside the realtime stack, deleted again
by the same script's normal teardown) invokes this Lambda once, at an
agreed deadline, regardless of whether the operator's laptop or terminal is
still connected. Its only job is to delete the realtime stack -- and only
that stack -- if it still exists, then verify DELETE_COMPLETE, alerting on
the existing SNS topic if the delete is denied or gets stuck.

This function's own IAM role is scoped to the realtime stack's specific
resources (see infrastructure/core_stack.py); it is never granted broad
administrator cleanup permissions and cannot delete the core stack.

Expiry cleanup may sacrifice unprocessed records to stop spend -- it does
not run the M4 drain gate (scripts/drain-check.py), which needs the
producer's local ledger file and is meant for the operator-present path.
An expiry-triggered deletion is therefore always worth treating as a
possibly-incomplete run; the producer's own saved fixtures are the record
of what it believes it sent.
"""

import json
import os
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

_cfn = None
_sns = None

TERMINAL_DELETED_STATUSES = {"DELETE_COMPLETE"}
IN_PROGRESS_STATUSES = {"DELETE_IN_PROGRESS"}
FAILED_STATUSES = {"DELETE_FAILED"}


def _cfn_client(region: str):
    global _cfn
    if _cfn is None:
        _cfn = boto3.client("cloudformation", region_name=region)
    return _cfn


def _sns_client():
    global _sns
    if _sns is None:
        _sns = boto3.client("sns")
    return _sns


def _alert(sns, topic_arn: str, message: str) -> None:
    sns.publish(
        TopicArn=topic_arn,
        Subject="[oilfield-esp] Expiry reaper needs attention",
        Message=message,
    )


def _stack_status(cfn, stack_name: str) -> str | None:
    """None means the stack name is not known to CloudFormation at all."""
    try:
        stacks = cfn.describe_stacks(StackName=stack_name)["Stacks"]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ValidationError" and (
            "does not exist" in str(exc)
        ):
            return None
        raise
    return stacks[0]["StackStatus"] if stacks else None


def reap(
    cfn,
    sns,
    topic_arn: str,
    stack_name: str,
    owner: str,
    poll_interval_seconds: int = 15,
    max_wait_seconds: int = 240,
) -> dict:
    """Delete one named stack if it still exists, then confirm completion.

    Pure of Lambda/event plumbing so it can be exercised offline with fake
    cfn/sns clients; ``handler`` below is the only place that resolves real
    AWS clients and environment variables.
    """
    status = _stack_status(cfn, stack_name)
    if status is None or status in TERMINAL_DELETED_STATUSES:
        return {"outcome": "already_gone", "stack_name": stack_name, "status": status}
    if status in IN_PROGRESS_STATUSES:
        # Someone (normal teardown, a previous reaper invocation) already
        # started deleting it; fall through to the same poll loop instead
        # of calling DeleteStack again.
        pass
    else:
        try:
            cfn.delete_stack(StackName=stack_name)
        except ClientError as exc:
            _alert(
                sns,
                topic_arn,
                f"Expiry reaper was DENIED deleting {stack_name} (owner={owner}): {exc}. "
                "This stack is past its agreed deadline and still exists. "
                "Check the reaper role's permissions and delete it manually.",
            )
            return {
                "outcome": "denied",
                "stack_name": stack_name,
                "error": str(exc),
            }

    deadline = time.monotonic() + max_wait_seconds
    while True:
        status = _stack_status(cfn, stack_name)
        if status is None or status in TERMINAL_DELETED_STATUSES:
            return {"outcome": "deleted", "stack_name": stack_name}
        if status in FAILED_STATUSES:
            _alert(
                sns,
                topic_arn,
                f"Expiry reaper: {stack_name} is DELETE_FAILED (owner={owner}). "
                "Past its agreed deadline and stuck; manual cleanup required.",
            )
            return {"outcome": "delete_failed", "stack_name": stack_name}
        if time.monotonic() >= deadline:
            _alert(
                sns,
                topic_arn,
                f"Expiry reaper: {stack_name} deletion is still {status} after "
                f"{max_wait_seconds}s (owner={owner}). Past its agreed deadline; "
                "check manually -- it may just be slow, or it may be stuck.",
            )
            return {"outcome": "stuck", "stack_name": stack_name, "status": status}
        time.sleep(poll_interval_seconds)


def handler(event, context):
    stack_name = event["stack_name"]
    expected_stack = os.environ["EXPECTED_REALTIME_STACK"]
    if stack_name != expected_stack:
        # IAM also rejects any other stack ARN.  This explicit application
        # check makes an accidentally reused/malformed scheduler payload
        # harmless even before it reaches CloudFormation.
        raise ValueError(
            f"Refusing expiry request for {stack_name!r}; expected {expected_stack!r}"
        )
    region = event.get("region") or os.environ.get("AWS_REGION")
    owner = event.get("run_owner", "unknown")
    topic_arn = os.environ["ALERT_TOPIC_ARN"]

    result = reap(_cfn_client(region), _sns_client(), topic_arn, stack_name, owner)
    result["expires_at_utc"] = event.get("expires_at_utc")
    result["checked_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    print(json.dumps(result))
    return result
