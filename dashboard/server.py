"""Loopback-only HTTP API for the M5 dashboard."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from dashboard.cache import RefreshCache
from dashboard.fixtures import PUMP_IDS, fixture_kpis, fixture_pumps
from dashboard.read_models import AwsReadModels


class DashboardService:
    def __init__(self, mode: str = "fixture", fixture_state: str = "normal", region: str = "us-east-1", profile: str | None = None):
        self.mode, self.fixture_state = mode, fixture_state
        self.source = None if mode == "fixture" else AwsReadModels(region, profile)
        self.pumps_cache, self.kpis_cache = RefreshCache(), RefreshCache()

    def _pumps(self):
        now = datetime.now(timezone.utc)
        return fixture_pumps(self.fixture_state, now) if self.mode == "fixture" else self.source.pumps()

    def _kpis(self):
        now = datetime.now(timezone.utc)
        return fixture_kpis(self.fixture_state, now) if self.mode == "fixture" else self.source.kpis()

    @staticmethod
    def _envelope(state, data, fetched_at):
        age = None if fetched_at is None else max(0, int((datetime.now(timezone.utc) - fetched_at).total_seconds()))
        return {"schema_version": "dashboard.v1", "state": state, "fetched_at": fetched_at.isoformat().replace("+00:00", "Z") if fetched_at else None, "data_age_seconds": age, "data": data}

    @staticmethod
    def _cache_health(cache):
        entry = cache.entry
        return {
            "hits": entry.hits, "misses": entry.misses,
            "last_success_at": entry.fetched_at.isoformat().replace("+00:00", "Z") if entry.fetched_at else None,
        }

    def route(self, path: str):
        if path == "/api/v1/health":
            return 200, {"schema_version": "dashboard.v1", "mode": self.mode, "pump_cache": self._cache_health(self.pumps_cache), "kpi_cache": self._cache_health(self.kpis_cache)}
        if path == "/api/v1/pumps":
            state, data, fetched = self.pumps_cache.read(self._pumps)
            return 200 if state != "unavailable" else 503, self._envelope(state, data or [], fetched)
        if path.startswith("/api/v1/pumps/"):
            esp_id = path.rsplit("/", 1)[-1]
            if esp_id not in PUMP_IDS:
                return 404, {"error": "unknown pump"}
            state, data, fetched = self.pumps_cache.read(self._pumps)
            pump = next((row for row in (data or []) if row.get("esp_id") == esp_id), None)
            return (200 if state != "unavailable" else 503), self._envelope(state, pump, fetched)
        if path == "/api/v1/kpis/latest":
            state, data, fetched = self.kpis_cache.read(self._kpis)
            return 200 if state != "unavailable" else 503, self._envelope(state, data or {}, fetched)
        return 404, {"error": "not found"}


def make_handler(service: DashboardService):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "").split(":")[0]
            if host not in {"127.0.0.1", "localhost"}:
                self.send_error(403, "loopback only")
                return
            status, payload = service.route(urlparse(self.path).path)
            body = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args):
            pass
    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("fixture", "aws"), default=os.getenv("DASHBOARD_MODE", "fixture"))
    parser.add_argument("--fixture-state", choices=("normal", "low-flow", "stale", "unavailable"), default=os.getenv("DASHBOARD_FIXTURE_STATE", "normal"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE"))
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 8765), make_handler(DashboardService(args.mode, args.fixture_state, args.region, args.profile)))
    print("Dashboard API listening on http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
