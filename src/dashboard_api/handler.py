"""Hosted dashboard read API.

The handler deliberately has no route that exposes raw events, AWS resource
identifiers, stack outputs, or provider exception details.  Authentication is
enforced by API Gateway before this code is invoked.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse

import boto3
from boto3.dynamodb.types import TypeDeserializer

PUMP_IDS = ("ESP-101", "ESP-102", "ESP-103")
_ttl = max(10, int(os.environ.get("CACHE_TTL_SECONDS", "15")))
_ddb = boto3.client("dynamodb")
_s3 = boto3.client("s3")
_pump_cache: tuple[float, list[dict]] | None = None
_publication_cache: tuple[float, dict] | None = None


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        },
        "body": json.dumps(body, default=str, separators=(",", ":")),
    }


def _number(value):
    return float(value) if isinstance(value, Decimal) else value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _envelope(data: object) -> dict:
    return {
        "schema_version": "dashboard.v1",
        "state": "fresh",
        "fetched_at": _now(),
        "data_age_seconds": 0,
        "data": data,
    }


def _pump_from_row(row: dict) -> dict:
    flow, temp = _number(row.get("flow_rate")), _number(row.get("motor_temperature"))
    current, vibration = _number(row.get("motor_current")), _number(row.get("vibration"))
    status = str(row.get("status", "UNKNOWN"))
    severity = str(row.get("severity", "")) or "normal"
    finding = row.get("finding")
    if not finding or severity == "normal":
        if status == "SHUTDOWN":
            severity, finding = "critical", "Pump shutdown"
        elif flow is not None and temp is not None and flow < 60 and temp > 120:
            severity, finding = "critical", "Low flow + motor overheating"
        elif vibration is not None and current is not None and vibration > 12 and current > 75:
            severity, finding = "critical", "High vibration + elevated current"
        elif flow is not None and flow < 60:
            severity, finding = "warning", "Low flow rate"
    return {
        "esp_id": str(row["esp_id"]), "timestamp": str(row.get("timestamp", "")),
        "status": status, "scenario": str(row.get("scenario", "unknown")),
        "flow_rate": flow, "motor_temperature": temp, "motor_current": current,
        "vibration": vibration, "severity": severity, "finding": finding,
    }


def _pumps() -> list[dict]:
    global _pump_cache
    if _pump_cache and time.monotonic() - _pump_cache[0] < _ttl:
        return _pump_cache[1]
    response = _ddb.batch_get_item(RequestItems={
        os.environ["STATE_TABLE"]: {"Keys": [{"esp_id": {"S": pump}} for pump in PUMP_IDS]}
    })
    decoder, by_id = TypeDeserializer(), {}
    for item in response.get("Responses", {}).get(os.environ["STATE_TABLE"], []):
        row = {key: decoder.deserialize(value) for key, value in item.items()}
        if row.get("esp_id") in PUMP_IDS:
            by_id[row["esp_id"]] = _pump_from_row(row)
    result = [by_id[pump] for pump in PUMP_IDS if pump in by_id]
    _pump_cache = (time.monotonic(), result)
    return result


def _publication() -> dict:
    global _publication_cache
    if _publication_cache and time.monotonic() - _publication_cache[0] < _ttl:
        return _publication_cache[1]
    bucket = os.environ["DATA_BUCKET"]
    pointer = json.loads(_s3.get_object(Bucket=bucket, Key="curated/publication/current.json")["Body"].read())
    report_uri = urlparse(pointer["quality_report"])
    if report_uri.scheme != "s3" or report_uri.netloc != bucket:
        raise ValueError("invalid approved publication")
    report = json.loads(_s3.get_object(Bucket=bucket, Key=report_uri.path.lstrip("/"))["Body"].read())
    key = pointer.get("kpi_summary_key")
    if not report.get("quality_passed") or not isinstance(key, str) or not key.startswith("curated/publication/runs/"):
        raise ValueError("no approved publication")
    summary = json.loads(_s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    if summary.get("schema_version") != "dashboard-kpi-summary.v1" or summary.get("run_id") != pointer.get("published_run_id") or not isinstance(summary.get("rows"), list):
        raise ValueError("invalid KPI publication")
    result = {
        "published_run_id": pointer["published_run_id"], "published_at": pointer["published_at"],
        "quality_passed": True, "counts": report.get("counts", {}), "kpis": summary["rows"],
    }
    _publication_cache = (time.monotonic(), result)
    return result


def lambda_handler(event, _context):
    path = event.get("rawPath") or event.get("requestContext", {}).get("http", {}).get("path", "")
    try:
        if path == "/api/v1/config":
            return _response(200, {"auth": {"issuer": os.environ["COGNITO_ISSUER"], "client_id": os.environ["COGNITO_CLIENT_ID"], "domain": os.environ["COGNITO_DOMAIN"]}})
        if path == "/api/v1/pumps":
            return _response(200, _envelope(_pumps()))
        if path.startswith("/api/v1/pumps/"):
            esp_id = path.rsplit("/", 1)[-1]
            pump = next((item for item in _pumps() if item["esp_id"] == esp_id), None)
            return _response(200, _envelope(pump)) if pump else _response(404, {"detail": "pump not found"})
        if path == "/api/v1/kpis/latest":
            return _response(200, _envelope(_publication()))
        if path == "/api/v1/health":
            return _response(200, {"schema_version": "dashboard.v1", "mode": "aws", "status": "ok"})
        return _response(404, {"detail": "not found"})
    except Exception:
        # Never reflect AWS/provider details to an unauthenticated browser.
        return _response(503, {"detail": "dependency unavailable"})
