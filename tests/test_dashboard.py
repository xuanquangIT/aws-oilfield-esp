from decimal import Decimal

from dashboard.cache import RefreshCache
from dashboard.read_models import ALLOWED_PUMP_FIELDS, AwsReadModels, allow_pump
from dashboard.server import DashboardService


def test_fixture_dashboard_returns_allow_listed_pumps():
    status, payload = DashboardService(mode="fixture").route("/api/v1/pumps")
    assert status == 200
    assert payload["state"] == "fresh"
    assert [item["esp_id"] for item in payload["data"]] == ["ESP-101", "ESP-102", "ESP-103"]
    assert set(payload["data"][0]).issubset(ALLOWED_PUMP_FIELDS)


def test_unknown_pump_is_not_a_query_escape_hatch():
    status, payload = DashboardService(mode="fixture").route("/api/v1/pumps/not-a-pump")
    assert status == 404
    assert payload == {"error": "unknown pump"}


def test_unavailable_fixture_has_no_fabricated_measurements():
    status, payload = DashboardService(mode="fixture", fixture_state="unavailable").route("/api/v1/pumps")
    assert status == 503
    assert payload["state"] == "unavailable"
    assert payload["data"] == []


def test_refresh_cache_returns_stale_only_after_a_successful_value():
    cache = RefreshCache(ttl_seconds=0, unavailable_after_seconds=45)
    state, value, fetched = cache.read(lambda: {"ok": True})
    assert (state, value) == ("fresh", {"ok": True})
    state, value, _ = cache.read(lambda: (_ for _ in ()).throw(RuntimeError("nope")))
    assert (state, value) == ("stale", {"ok": True})
    assert fetched is not None


def test_aws_adapter_uses_batch_get_and_filters_fields():
    class FakeDdb:
        def batch_get_item(self, **kwargs):
            assert list(kwargs["RequestItems"].values())[0]["Keys"] == [
                {"esp_id": {"S": "ESP-101"}}, {"esp_id": {"S": "ESP-102"}}, {"esp_id": {"S": "ESP-103"}}
            ]
            return {"Responses": {"state": [{"esp_id": {"S": "ESP-101"}, "flow_rate": {"N": "88.5"}, "secret": {"S": "no"}}]}}
    reader = AwsReadModels.__new__(AwsReadModels)
    reader.ddb, reader._outputs = FakeDdb(), {"StateTableName": "state"}
    assert reader.pumps() == [{"esp_id": "ESP-101", "flow_rate": 88.5, "severity": "unknown", "finding": None}]
    assert allow_pump({"esp_id": "ESP-101", "flow_rate": Decimal("2"), "secret": "no"})["flow_rate"] == 2
