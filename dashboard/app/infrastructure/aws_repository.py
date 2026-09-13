"""Read-only AWS adapter. It is the only dashboard module that imports boto3."""

from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import urlparse

import boto3
from boto3.dynamodb.types import TypeDeserializer

from dashboard.app.domain.models import PUMP_IDS, PublicationSnapshot, PumpSnapshot


def _number(value):
    return None if value is None else float(value) if isinstance(value, Decimal) else value


class AwsDashboardRepository:
    def __init__(self, region: str, profile: str | None, stack_name: str):
        session = boto3.Session(region_name=region, profile_name=profile)
        self._ddb, self._s3, self._cfn = session.client("dynamodb"), session.client("s3"), session.client("cloudformation")
        self._stack_name, self._outputs = stack_name, None

    def _core_outputs(self) -> dict[str, str]:
        if self._outputs is None:
            stack = self._cfn.describe_stacks(StackName=self._stack_name)["Stacks"][0]
            self._outputs = {item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])}
        return self._outputs

    def fetch_pumps(self) -> list[PumpSnapshot]:
        table = self._core_outputs()["StateTableName"]
        response = self._ddb.batch_get_item(RequestItems={table: {"Keys": [{"esp_id": {"S": pump}} for pump in PUMP_IDS]}})
        decoder = TypeDeserializer()
        by_id = {}
        for item in response.get("Responses", {}).get(table, []):
            row = {key: decoder.deserialize(value) for key, value in item.items()}
            esp_id = row.get("esp_id")
            if esp_id in PUMP_IDS:
                flow = _number(row.get("flow_rate"))
                temp = _number(row.get("motor_temperature"))
                curr = _number(row.get("motor_current"))
                vib = _number(row.get("vibration"))
                status_val = str(row.get("status", "UNKNOWN"))
                scenario_val = str(row.get("scenario", "unknown"))
                severity = str(row.get("severity", "")) or "normal"
                finding = row.get("finding")
                if not finding or severity == "normal":
                    if status_val == "SHUTDOWN":
                        severity = "critical"
                        finding = "Pump shutdown"
                    elif flow is not None and temp is not None and flow < 60 and temp > 120:
                        severity = "critical"
                        finding = "Low flow + motor overheating"
                    elif vib is not None and curr is not None and vib > 12 and curr > 75:
                        severity = "critical"
                        finding = "High vibration + elevated current"
                    elif flow is not None and flow < 60:
                        severity = "warning"
                        finding = "Low flow rate"
                    elif scenario_val == "low_flow":
                        severity = "warning"
                        finding = "Low flow rate"
                by_id[esp_id] = PumpSnapshot(
                    esp_id,
                    str(row.get("timestamp", "")),
                    status_val,
                    scenario_val,
                    flow,
                    temp,
                    curr,
                    vib,
                    severity,
                    finding,
                )
        return [by_id[pump] for pump in PUMP_IDS if pump in by_id]

    def fetch_latest_publication(self) -> PublicationSnapshot:
        bucket = self._core_outputs()["DataBucketName"]
        pointer = json.loads(self._s3.get_object(Bucket=bucket, Key="curated/publication/current.json")["Body"].read())
        uri = urlparse(pointer["quality_report"])
        report = json.loads(self._s3.get_object(Bucket=uri.netloc, Key=uri.path.lstrip("/"))["Body"].read())
        if not report.get("quality_passed"):
            raise ValueError("unapproved publication")
        summary_key = pointer.get("kpi_summary_key")
        if not isinstance(summary_key, str) or not summary_key.startswith("curated/publication/runs/"):
            raise ValueError("publication lacks dashboard KPI summary")
        summary = json.loads(self._s3.get_object(Bucket=bucket, Key=summary_key)["Body"].read())
        if summary.get("schema_version") != "dashboard-kpi-summary.v1" or summary.get("run_id") != pointer["published_run_id"] or not isinstance(summary.get("rows"), list):
            raise ValueError("invalid dashboard KPI summary")
        return PublicationSnapshot(pointer["published_run_id"], pointer["published_at"], True, report.get("counts", {}), summary["rows"])
