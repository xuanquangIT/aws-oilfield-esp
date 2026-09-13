from fastapi.testclient import TestClient

from dashboard.app.application.cache import ResilientTtlCache
from dashboard.app.core.config import Settings
from dashboard.app.domain.models import PublicationSnapshot, PumpSnapshot
from dashboard.app.infrastructure.aws_repository import AwsDashboardRepository
from dashboard.app.main import create_app


class FakeRepository:
    def fetch_pumps(self):
        return [PumpSnapshot("ESP-101", "2026-09-13T00:00:00Z", "RUNNING", "normal", 100.0, 80.0, 38.0, 2.0)]

    def fetch_latest_publication(self):
        return PublicationSnapshot("run-1", "2026-09-13T00:00:00Z", True, {"gold_rows": 3}, [])


def client(repository=None):
    return TestClient(create_app(Settings(mode="fixture", cache_ttl_seconds=10), repository or FakeRepository()))


def test_fixture_api_is_versioned_and_allow_listed():
    response = client().get("/api/v1/pumps")
    assert response.status_code == 200
    assert response.json()["schema_version"] == "dashboard.v1"
    assert set(response.json()["data"][0]) == {"esp_id", "timestamp", "status", "scenario", "flow_rate", "motor_temperature", "motor_current", "vibration", "severity", "finding"}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_unknown_pump_is_rejected_without_querying_provider():
    response = client().get("/api/v1/pumps/not-a-pump")
    assert response.status_code == 404
    assert response.json()["detail"] == "unknown pump"


def test_health_exposes_metrics_not_cached_data():
    response = client().get("/api/v1/health")
    assert response.status_code == 200
    assert "value" not in response.text
    assert set(response.json()["pump_cache"]) == {"hits", "misses", "last_success_at"}


def test_unavailable_dependency_is_sanitized():
    class FailingRepository(FakeRepository):
        def fetch_pumps(self):
            raise RuntimeError("AWS secret-like failure must not escape")
    response = client(FailingRepository()).get("/api/v1/pumps")
    assert response.status_code == 503
    assert response.json()["detail"] == "dependency unavailable"
    assert "secret" not in response.text


def test_cache_returns_stale_only_after_a_success():
    cache = ResilientTtlCache(ttl_seconds=0, unavailable_after_seconds=45)
    first = cache.get(lambda: {"ok": True})
    stale = cache.get(lambda: (_ for _ in ()).throw(RuntimeError("failure")))
    assert first.state == "fresh"
    assert stale.state == "stale"
    assert stale.value == {"ok": True}


def test_aws_repository_uses_batch_get_without_scan():
    class FakeDdb:
        def batch_get_item(self, **kwargs):
            assert list(kwargs["RequestItems"].values())[0]["Keys"][0] == {"esp_id": {"S": "ESP-101"}}
            return {"Responses": {"state": [{"esp_id": {"S": "ESP-101"}, "timestamp": {"S": "2026-09-13T00:00:00Z"}, "flow_rate": {"N": "88.5"}}]}}
    repository = AwsDashboardRepository.__new__(AwsDashboardRepository)
    repository._ddb, repository._outputs = FakeDdb(), {"StateTableName": "state"}
    rows = repository.fetch_pumps()
    assert rows[0].esp_id == "ESP-101"
    assert rows[0].flow_rate == 88.5
