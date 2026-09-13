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
                by_id[esp_id] = PumpSnapshot(esp_id, str(row.get("timestamp", "")), str(row.get("status", "UNKNOWN")), str(row.get("scenario", "unknown")), _number(row.get("flow_rate")), _number(row.get("motor_temperature")), _number(row.get("motor_current")), _number(row.get("vibration")))
        return [by_id[pump] for pump in PUMP_IDS if pump in by_id]

    def fetch_latest_publication(self) -> PublicationSnapshot:
        bucket = self._core_outputs()["DataBucketName"]
        pointer = json.loads(self._s3.get_object(Bucket=bucket, Key="curated/publication/current.json")["Body"].read())
        uri = urlparse(pointer["quality_report"])
        report = json.loads(self._s3.get_object(Bucket=uri.netloc, Key=uri.path.lstrip("/"))["Body"].read())
        if not report.get("quality_passed"):
            raise ValueError("unapproved publication")
        return PublicationSnapshot(pointer["published_run_id"], pointer["published_at"], True, report.get("counts", {}), pointer.get("kpi_summary", []))
