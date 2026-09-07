"""M1 exit gate: valid rows pass, invalid rows are rejected for the right
reason, additions are backward-compatible, and incompatible versions cannot
silently pass. Duplicate/late fixtures document the M1/M2 boundary: they are
structurally valid single records, but identity-based conflict handling is
explicitly out of scope for this validator (see src/contract.py docstring).
"""

import json
from pathlib import Path

from contract import SCHEMA_VERSION, validate

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "telemetry_v1.json").read_text()
)


def test_valid_events_are_accepted():
    for case in FIXTURES["valid"]:
        result = validate(case["event"])
        assert result.accepted, (
            f"expected accept, got {result.rule_id}: {result.reason}"
        )
        assert result.rule_id == "OK"
        assert result.event["timestamp"].endswith("Z")


def test_missing_or_null_required_fields_are_rejected():
    for case in FIXTURES["invalid_null"]:
        result = validate(case["event"])
        assert not result.accepted
        assert result.rule_id == case["expected_rule_id"], case.get("note")


def test_malformed_values_are_rejected_with_expected_rule():
    for case in FIXTURES["invalid_malformed"]:
        result = validate(case["event"])
        assert not result.accepted
        assert result.rule_id == case["expected_rule_id"], case.get("note")


def test_incompatible_schema_version_is_rejected():
    for case in FIXTURES["incompatible_version"]:
        result = validate(case["event"])
        assert not result.accepted
        assert result.rule_id == "SCHEMA_VERSION_UNSUPPORTED"


def test_unknown_optional_field_is_backward_compatible():
    base = FIXTURES["valid"][0]["event"]
    evolved = dict(base, future_optional_field="added-by-a-later-minor-change")
    result = validate(evolved)
    assert result.accepted, result.reason


def test_duplicate_fixture_is_structurally_valid_at_m1():
    for case in FIXTURES["duplicate"]:
        a = validate(case["event_a"])
        b = validate(case["event_b"])
        assert a.accepted and b.accepted
        assert case["event_a"]["event_id"] == case["event_b"]["event_id"]


def test_late_fixture_is_structurally_valid_at_m1():
    for case in FIXTURES["late"]:
        prior = validate(case["prior_event"])
        late = validate(case["late_event"])
        assert prior.accepted and late.accepted
        assert late.event["timestamp"] < prior.event["timestamp"]


def test_schema_version_constant_matches_fixtures():
    assert SCHEMA_VERSION == 1
