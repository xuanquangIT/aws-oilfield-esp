"""Tests for the dashboard UI static assets, root routing, security headers,
and G10 acceptance criteria (no leaked credentials, loopback-only bind).
"""

from pathlib import Path
import re
import pytest
from fastapi.testclient import TestClient

from dashboard.app.core.config import Settings
from dashboard.app.domain.models import PublicationSnapshot, PumpSnapshot
from dashboard.app.infrastructure.fixture_repository import FixtureDashboardRepository
from dashboard.app.main import STATIC_DIR, create_app


class MockRepository:
    def fetch_pumps(self):
        return [
            PumpSnapshot("ESP-101", "2026-09-13T00:00:00Z", "RUNNING", "normal", 105.0, 78.0, 38.0, 2.1, "normal", None),
            PumpSnapshot("ESP-102", "2026-09-13T00:00:00Z", "RUNNING", "low_flow", 42.0, 94.0, 39.0, 2.2, "warning", "Low flow rate"),
            PumpSnapshot("ESP-103", "2026-09-13T00:00:00Z", "RUNNING", "normal", 107.0, 80.0, 40.0, 2.3, "normal", None),
        ]

    def fetch_latest_publication(self):
        return PublicationSnapshot(
            "test-run-001",
            "2026-09-13T00:00:00Z",
            True,
            {"silver_rows": 252, "gold_rows": 6, "unexplained_rows": 0},
            [{"esp_id": "ESP-101", "avg_liquid_rate_m3_day": 105.0}],
        )


def make_client(repository=None, host="127.0.0.1"):
    settings = Settings(mode="fixture", host=host, cache_ttl_seconds=10)
    return TestClient(create_app(settings, repository or MockRepository()))


def test_root_serves_html_with_security_headers():
    client = make_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ESP Surveillance Mission Control" in response.text
    # Security headers applied
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "no-store" in response.headers["cache-control"]


def test_static_css_and_js_served_successfully():
    client = make_client()
    css_res = client.get("/static/css/dashboard.css")
    assert css_res.status_code == 200
    assert "text/css" in css_res.headers.get("content-type", "")
    assert "--bg-app" in css_res.text

    js_res = client.get("/static/js/app.js")
    assert js_res.status_code == 200
    assert "javascript" in js_res.headers.get("content-type", "")
    assert "Offshore ESP SCADA" in js_res.text


def test_static_assets_contain_no_credentials_or_aws_sdks():
    """G10 Criterion 2: Browser assets must contain no credential-like strings,
    AWS SDK imports, physical bucket names, or account identifiers.
    """
    assert STATIC_DIR.is_dir()
    forbidden_patterns = [
        re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key ID
        re.compile(r"ASIA[0-9A-Z]{16}"),  # AWS Temp Access Key ID
        re.compile(r"import boto3"),
        re.compile(r"from boto3"),
        re.compile(r"@aws-sdk"),
        re.compile(r"aws-sdk"),
        re.compile(r"https?://(?:unpkg\.com|cdn\.|cdnjs\.|fonts\.googleapis\.com)"), # No external CDNs (air-gapped)
    ]

    for file_path in STATIC_DIR.rglob("*"):
        if file_path.is_file() and file_path.suffix in (".html", ".js", ".css"):
            content = file_path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                match = pattern.search(content)
                assert not match, f"Forbidden pattern '{pattern.pattern}' found in {file_path.name}: {match.group(0)}"


def test_non_loopback_binding_is_rejected():
    with pytest.raises(ValueError, match="Dashboard API must bind to 127.0.0.1"):
        create_app(Settings(host="0.0.0.0"))


def test_fixture_repository_states():
    # Normal state
    normal_repo = FixtureDashboardRepository("normal")
    pumps = normal_repo.fetch_pumps()
    assert len(pumps) == 3
    assert all(p.severity == "normal" for p in pumps)

    # Low-flow state
    low_flow_repo = FixtureDashboardRepository("low-flow")
    pumps_lf = low_flow_repo.fetch_pumps()
    esp_102 = next(p for p in pumps_lf if p.esp_id == "ESP-102")
    assert esp_102.severity == "warning"
    assert esp_102.finding == "Low flow rate"
    assert esp_102.flow_rate == 42.0

    # Unavailable state
    unavail_repo = FixtureDashboardRepository("unavailable")
    with pytest.raises(RuntimeError, match="fixture dependency unavailable"):
        unavail_repo.fetch_pumps()
