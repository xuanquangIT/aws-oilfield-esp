"""Safe read-only adapters for the existing core data stores."""

from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import urlparse

import boto3
from boto3.dynamodb.types import TypeDeserializer

from dashboard.fixtures import PUMP_IDS

ALLOWED_PUMP_FIELDS = {
    "esp_id", "timestamp", "status", "scenario", "flow_rate", "motor_temperature",
    "motor_current", "vibration", "severity", "finding",
}


def _json_value(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return value


def allow_pump(item: dict) -> dict:
    result = {key: _json_value(value) for key, value in item.items() if key in ALLOWED_PUMP_FIELDS}
    result.setdefault("severity", "unknown")
    result.setdefault("finding", None)
    return result


class AwsReadModels:
    def __init__(self, region: str, profile: str | None = None, stack_name: str = "oilfield-esp-core"):
        session = boto3.Session(region_name=region, profile_name=profile)
        self.ddb = session.client("dynamodb")
        self.s3 = session.client("s3")
        self.cfn = session.client("cloudformation")
        self.stack_name = stack_name
        self._outputs: dict[str, str] | None = None

    def outputs(self) -> dict[str, str]:
        if self._outputs is None:
            stack = self.cfn.describe_stacks(StackName=self.stack_name)["Stacks"][0]
            self._outputs = {item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])}
        return self._outputs

    def pumps(self) -> list[dict]:
        table = self.outputs()["StateTableName"]
        response = self.ddb.batch_get_item(RequestItems={table: {"Keys": [{"esp_id": {"S": value}} for value in PUMP_IDS]}})
        decoder = TypeDeserializer()
        rows = [allow_pump({key: decoder.deserialize(value) for key, value in item.items()}) for item in response.get("Responses", {}).get(table, [])]
        by_id = {row["esp_id"]: row for row in rows if "esp_id" in row}
        return [by_id[pump] for pump in PUMP_IDS if pump in by_id]

    def kpis(self) -> dict:
        bucket = self.outputs()["DataBucketName"]
        pointer = json.loads(self.s3.get_object(Bucket=bucket, Key="curated/publication/current.json")["Body"].read())
        quality_uri = pointer["quality_report"]
        parsed = urlparse(quality_uri)
        quality = json.loads(self.s3.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))["Body"].read())
        if not quality.get("quality_passed"):
            raise ValueError("unapproved publication")
        # Future M3 publications add kpi_summary; old published runs remain
        # safely usable for run/quality metadata but do not invent KPI values.
        return {
            "published_run_id": pointer["published_run_id"], "published_at": pointer["published_at"],
            "quality_passed": True, "counts": quality.get("counts", {}),
            "kpis": pointer.get("kpi_summary", []),
        }
