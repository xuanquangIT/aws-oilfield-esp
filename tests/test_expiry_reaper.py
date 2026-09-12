"""Offline exit-gate tests for the M4 expiry reaper (src/expiry_reaper/handler.py)."""

from botocore.exceptions import ClientError

from expiry_reaper.handler import handler, reap


def _client_error(message="Simulated failure", code="Test"):
    return ClientError({"Error": {"Code": code, "Message": message}}, "Operation")


class FakeCfn:
    def __init__(self, statuses, delete_error=None):
        # One entry consumed per describe_stacks call; the last entry
        # repeats once exhausted so a test can supply just enough history.
        self._statuses = list(statuses)
        self.delete_error = delete_error
        self.delete_calls = 0

    def describe_stacks(self, StackName):
        status = self._statuses.pop(0) if len(self._statuses) > 1 else self._statuses[0]
        if status is None:
            raise _client_error(
                f"Stack with id {StackName} does not exist", code="ValidationError"
            )
        return {"Stacks": [{"StackStatus": status}]}

    def delete_stack(self, StackName):
        self.delete_calls += 1
        if self.delete_error:
            raise self.delete_error


class FakeSns:
    def __init__(self):
        self.published = []

    def publish(self, TopicArn, Subject, Message):
        self.published.append(
            {"TopicArn": TopicArn, "Subject": Subject, "Message": Message}
        )


def test_already_gone_stack_is_a_no_op(monkeypatch):
    monkeypatch.setattr("expiry_reaper.handler.time.sleep", lambda s: None)
    cfn = FakeCfn(statuses=[None])
    sns = FakeSns()

    result = reap(cfn, sns, "topic-arn", "oilfield-esp-realtime", "tester")

    assert result["outcome"] == "already_gone"
    assert cfn.delete_calls == 0
    assert sns.published == []


def test_deletes_and_confirms_a_running_stack(monkeypatch):
    monkeypatch.setattr("expiry_reaper.handler.time.sleep", lambda s: None)
    cfn = FakeCfn(statuses=["CREATE_COMPLETE", "DELETE_IN_PROGRESS", "DELETE_COMPLETE"])
    sns = FakeSns()

    result = reap(
        cfn,
        sns,
        "topic-arn",
        "oilfield-esp-realtime",
        "tester",
        poll_interval_seconds=0,
        max_wait_seconds=60,
    )

    assert result["outcome"] == "deleted"
    assert cfn.delete_calls == 1
    assert sns.published == []


def test_skips_delete_call_if_already_in_progress(monkeypatch):
    monkeypatch.setattr("expiry_reaper.handler.time.sleep", lambda s: None)
    cfn = FakeCfn(statuses=["DELETE_IN_PROGRESS", "DELETE_COMPLETE"])
    sns = FakeSns()

    result = reap(
        cfn,
        sns,
        "topic-arn",
        "oilfield-esp-realtime",
        "tester",
        poll_interval_seconds=0,
        max_wait_seconds=60,
    )

    assert result["outcome"] == "deleted"
    assert cfn.delete_calls == 0


def test_alerts_when_delete_is_denied(monkeypatch):
    monkeypatch.setattr("expiry_reaper.handler.time.sleep", lambda s: None)
    cfn = FakeCfn(
        statuses=["CREATE_COMPLETE"], delete_error=_client_error("AccessDenied")
    )
    sns = FakeSns()

    result = reap(cfn, sns, "topic-arn", "oilfield-esp-realtime", "tester")

    assert result["outcome"] == "denied"
    assert len(sns.published) == 1
    assert "DENIED" in sns.published[0]["Message"]


def test_alerts_on_delete_failed(monkeypatch):
    monkeypatch.setattr("expiry_reaper.handler.time.sleep", lambda s: None)
    cfn = FakeCfn(statuses=["CREATE_COMPLETE", "DELETE_FAILED"])
    sns = FakeSns()

    result = reap(
        cfn,
        sns,
        "topic-arn",
        "oilfield-esp-realtime",
        "tester",
        poll_interval_seconds=0,
        max_wait_seconds=60,
    )

    assert result["outcome"] == "delete_failed"
    assert len(sns.published) == 1


def test_alerts_when_stuck_past_the_deadline(monkeypatch):
    monkeypatch.setattr("expiry_reaper.handler.time.sleep", lambda s: None)
    cfn = FakeCfn(statuses=["CREATE_COMPLETE", "DELETE_IN_PROGRESS"])
    sns = FakeSns()

    result = reap(
        cfn,
        sns,
        "topic-arn",
        "oilfield-esp-realtime",
        "tester",
        poll_interval_seconds=0,
        max_wait_seconds=0,
    )

    assert result["outcome"] == "stuck"
    assert len(sns.published) == 1
    assert (
        "stuck" in sns.published[0]["Message"]
        or "check manually" in sns.published[0]["Message"]
    )


def test_handler_rejects_a_payload_for_any_stack_but_the_realtime_stack(monkeypatch):
    monkeypatch.setenv("EXPECTED_REALTIME_STACK", "oilfield-esp-realtime")
    monkeypatch.setenv("ALERT_TOPIC_ARN", "topic-arn")

    with __import__("pytest").raises(ValueError, match="Refusing expiry request"):
        handler({"stack_name": "oilfield-esp-core"}, None)
