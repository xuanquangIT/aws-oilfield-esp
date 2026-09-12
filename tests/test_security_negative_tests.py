"""Offline shape tests for the M4 IAM-simulation deny matrix."""

import importlib.util
import sys
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location(
    "security_negative_tests",
    Path(__file__).resolve().parent.parent / "scripts" / "security-negative-tests.py",
)
module = importlib.util.module_from_spec(_SPEC)
sys.modules["security_negative_tests"] = module
_SPEC.loader.exec_module(module)


def test_g4_matrix_has_five_distinct_unsafe_actions():
    cases = module._cases(
        "123456789012",
        "test-bucket",
        "ap-southeast-1",
        {"processor": "p", "anomaly": "a", "expiry": "e"},
    )

    assert len(cases) == 5
    assert {case["action"] for case in cases} == {
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:PutObject",
        "cloudformation:DeleteStack",
        "iam:PassRole",
    }
    assert "ap-southeast-1" in cases[3]["resource"]


def test_g4_role_prefixes_match_the_cdk_function_service_roles():
    assert module.ROLE_LOGICAL_PREFIXES == {
        "processor": "StreamProcessorServiceRole",
        "anomaly": "AnomalyDetectorServiceRole",
        "expiry": "ExpiryReaperServiceRole",
    }
