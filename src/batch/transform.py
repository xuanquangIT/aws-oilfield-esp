"""M3 canonical batch publication: historical CSV + realtime JSON -> silver/gold.

This Glue job consumes a checksum-bound input manifest. It validates each
record with the shared v1 contract, fails closed on conflicting event IDs,
joins versioned pump metadata, writes immutable run-scoped staging/final
Parquet, and advances the small publication pointer only after quality gates
pass. The pointer is the approved consumer/catalog handoff; unapproved
staging or failed-run data is never selected by it.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from contract import validate


args = getResolvedOptions(
    sys.argv, ["JOB_NAME", "DATA_BUCKET", "RUN_ID", "INPUT_MANIFEST_KEY"]
)
bucket = args["DATA_BUCKET"]
run_id = args["RUN_ID"]
manifest_key = args["INPUT_MANIFEST_KEY"]

sc = SparkContext()
gc = GlueContext(sc)
spark = gc.spark_session
spark.conf.set("spark.sql.session.timeZone", "UTC")
job = Job(gc)
job.init(args["JOB_NAME"], args)

EVENT_FIELDS = [
    "schema_version", "event_id", "timestamp", "esp_id", "source", "run_id",
    "flow_rate", "water_cut", "intake_pressure", "discharge_pressure",
    "tubing_pressure", "casing_pressure", "intake_temperature",
    "motor_temperature", "motor_current", "vibration", "pump_frequency",
    "status", "scenario",
]
EVENT_SCHEMA = T.StructType(
    [
        T.StructField("schema_version", T.IntegerType()),
        T.StructField("event_id", T.StringType()),
        T.StructField("timestamp", T.StringType()),
        T.StructField("esp_id", T.StringType()),
        T.StructField("source", T.StringType()),
        T.StructField("run_id", T.StringType()),
        T.StructField("flow_rate", T.DoubleType()),
        T.StructField("water_cut", T.DoubleType()),
        T.StructField("intake_pressure", T.DoubleType()),
        T.StructField("discharge_pressure", T.DoubleType()),
        T.StructField("tubing_pressure", T.DoubleType()),
        T.StructField("casing_pressure", T.DoubleType()),
        T.StructField("intake_temperature", T.DoubleType()),
        T.StructField("motor_temperature", T.DoubleType()),
        T.StructField("motor_current", T.DoubleType()),
        T.StructField("vibration", T.DoubleType()),
        T.StructField("pump_frequency", T.DoubleType()),
        T.StructField("status", T.StringType()),
        T.StructField("scenario", T.StringType()),
    ]
)
VALIDATION_SCHEMA = T.StructType(
    [
        T.StructField("accepted", T.BooleanType(), nullable=False),
        T.StructField("rule_id", T.StringType(), nullable=False),
        T.StructField("reason", T.StringType(), nullable=False),
        T.StructField("normalized_json", T.StringType()),
    ]
)


def validate_event(row):
    raw = row.asDict(recursive=True) if row is not None else None
    result = validate(raw)
    return (
        result.accepted,
        result.rule_id,
        result.reason,
        json.dumps(result.event, sort_keys=True) if result.event else None,
    )


validate_event_udf = F.udf(validate_event, VALIDATION_SCHEMA)


def s3_uri(key: str) -> str:
    return f"s3://{bucket}/{key}"


def manifest_digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def load_manifest() -> tuple[dict, str]:
    response = boto3.client("s3").get_object(Bucket=bucket, Key=manifest_key)
    manifest = json.loads(response["Body"].read())
    expected = response.get("Metadata", {}).get("sha256")
    actual = manifest_digest(manifest)
    if expected and expected != actual:
        raise RuntimeError("input manifest checksum does not match S3 object metadata")
    required = {
        "manifest_version", "manifest_id", "schema_version", "metadata_version",
        "start_date", "end_date", "late_arrival_lookback_days", "objects",
    }
    missing = required.difference(manifest)
    if missing:
        raise RuntimeError(f"input manifest is missing {sorted(missing)}")
    if manifest["manifest_version"] != 1 or manifest["schema_version"] != 1:
        raise RuntimeError("input manifest has an unsupported version")
    if manifest["start_date"] > manifest["end_date"]:
        raise RuntimeError("input manifest start_date is after end_date")
    return manifest, actual


manifest, manifest_sha256 = load_manifest()
historical_uris = [
    item["uri"] for item in manifest["objects"] if item["source_kind"] == "historical_csv"
]
realtime_uris = [
    item["uri"] for item in manifest["objects"] if item["source_kind"] == "realtime_json"
]
if not historical_uris and not realtime_uris:
    raise RuntimeError("input manifest selected no raw objects")

source_inventory = spark.createDataFrame(
    [
        (item["uri"], item["source_kind"], item.get("last_modified_utc"), item["sha256"])
        for item in manifest["objects"]
    ],
    "source_uri string, source_kind string, object_last_modified_utc string, source_sha256 string",
).withColumn("ingested_at", F.to_timestamp("object_last_modified_utc"))


def read_csv(uris):
    # Historical CSV intentionally omits optional realtime-only fields. Spark
    # maps a supplied CSV schema by position, which would shift every column
    # after the first omitted field. Read the header first and project/cast by
    # name so omitted optional fields become null instead of corrupting rows.
    headered = spark.read.option("header", True).csv(uris)
    projected = []
    available = set(headered.columns)
    for field in EVENT_SCHEMA.fields:
        if field.name in available:
            projected.append(F.col(field.name).cast(field.dataType).alias(field.name))
        else:
            projected.append(F.lit(None).cast(field.dataType).alias(field.name))
    return headered.select(*projected).withColumn(
        "source_uri", F.regexp_replace(F.input_file_name(), "^s3a?://", "s3://")
    )


def read_json(uris):
    return (
        spark.read.schema(EVENT_SCHEMA).json(uris)
        .withColumn("source_uri", F.regexp_replace(F.input_file_name(), "^s3a?://", "s3://"))
    )


frames = []
if historical_uris:
    frames.append(read_csv(historical_uris))
if realtime_uris:
    frames.append(read_json(realtime_uris))
raw = frames[0]
for frame in frames[1:]:
    raw = raw.unionByName(frame, allowMissingColumns=True)

validated = (
    raw.join(F.broadcast(source_inventory), "source_uri", "inner")
    .withColumn("validation", validate_event_udf(F.struct(*EVENT_FIELDS)))
    .select("source_uri", "source_kind", "ingested_at", "source_sha256", "validation")
)
invalid = validated.filter(~F.col("validation.accepted")).select(
    "source_uri", "source_kind", "ingested_at", "source_sha256",
    F.lit(None).cast("string").alias("event_id"),
    F.col("validation.rule_id").alias("rule_id"),
    F.col("validation.reason").alias("reason"),
)
normalized = (
    validated.filter(F.col("validation.accepted"))
    .select(
        "source_uri", "source_kind", "ingested_at", "source_sha256",
        F.from_json(F.col("validation.normalized_json"), EVENT_SCHEMA).alias("event"),
    )
    .select("source_uri", "source_kind", "ingested_at", "source_sha256", "event.*")
    .withColumn("event_ts", F.to_timestamp("timestamp"))
    .withColumn("event_date", F.to_date("event_ts"))
)

# The lookback widens the reprocessed event-date window. It does not alter
# unrelated days because this immutable run holds only this bounded range.
effective_start = F.date_sub(
    F.to_date(F.lit(manifest["start_date"])), int(manifest["late_arrival_lookback_days"])
)
window_predicate = (F.col("event_date") >= effective_start) & (
    F.col("event_date") <= F.to_date(F.lit(manifest["end_date"]))
)
in_scope = normalized.filter(window_predicate)
out_of_scope = normalized.filter(~window_predicate)
payload_columns = [F.col(name) for name in EVENT_FIELDS]
with_hash = in_scope.withColumn(
    "payload_sha256",
    F.sha2(F.to_json(F.struct(*payload_columns), {"ignoreNullFields": "false"}), 256),
)
identity = with_hash.groupBy("event_id").agg(
    F.count(F.lit(1)).alias("identity_count"),
    F.countDistinct("payload_sha256").alias("payload_count"),
)
classified = with_hash.join(identity, "event_id", "inner")
conflicts = classified.filter(F.col("payload_count") > 1).select(
    "source_uri", "source_kind", "ingested_at", "source_sha256", "event_id",
    F.lit("DUPLICATE_EVENT_ID_CONFLICT").alias("rule_id"),
    F.lit("same event_id has different normalized payloads").alias("reason"),
)
dedupe_window = Window.partitionBy("event_id").orderBy("source_uri")
silver_unjoined = (
    classified.filter(F.col("payload_count") == 1)
    .withColumn("identity_rank", F.row_number().over(dedupe_window))
    .filter(F.col("identity_rank") == 1)
    .drop("identity_rank", "identity_count", "payload_count")
)

metadata = (
    spark.read.option("header", True).option("inferSchema", True)
    .csv(s3_uri("scripts/batch/pump_metadata_v1.csv"))
)
silver = silver_unjoined.join(F.broadcast(metadata), "esp_id", "left")
missing_metadata = silver.filter(F.col("metadata_version").isNull())
silver = silver.withColumn("publication_run_id", F.lit(run_id)).withColumn(
    "manifest_sha256", F.lit(manifest_sha256)
)

warning = (F.col("flow_rate") < F.col("min_flow_rate")) | (
    F.col("motor_temperature") > F.col("max_motor_temperature")
)
gold = (
    silver.groupBy(
        "publication_run_id", "manifest_sha256", "event_date", "esp_id", "field",
        "metadata_version", "baseline_liquid_rate_m3_day",
    )
    .agg(
        F.count(F.lit(1)).alias("sample_count"),
        F.avg("flow_rate").alias("avg_liquid_rate_m3_day"),
        F.avg(F.col("flow_rate") * (F.lit(1.0) - F.col("water_cut"))).alias("avg_oil_rate_m3_day"),
        F.avg("motor_temperature").alias("avg_motor_temperature_c"),
        F.max("vibration").alias("peak_vibration_mm_s"),
        F.sum(F.when(warning, F.lit(1)).otherwise(F.lit(0))).alias("warning_samples"),
    )
    .withColumn("sample_coverage", F.col("sample_count") / F.lit(24.0))
    .withColumn("warning_duration_minutes", F.col("warning_samples") * F.lit(60))
    .withColumn("missing_data_minutes", F.greatest(F.lit(0), F.lit(24) - F.col("sample_count")) * F.lit(60))
    .withColumn(
        "relative_flow_deficit",
        F.greatest(
            F.lit(0.0),
            (F.col("baseline_liquid_rate_m3_day") - F.col("avg_liquid_rate_m3_day"))
            / F.col("baseline_liquid_rate_m3_day"),
        ),
    )
)

staging_root = s3_uri(f"staging/m3/{run_id}")
silver.write.mode("errorifexists").partitionBy("event_date").parquet(f"{staging_root}/silver")
gold.write.mode("errorifexists").partitionBy("event_date").parquet(f"{staging_root}/gold")
quarantine = invalid.unionByName(conflicts)
quarantine.write.mode("errorifexists").partitionBy("rule_id").parquet(f"{staging_root}/quarantine")


def count_rows(frame):
    return frame.count()


input_rows = count_rows(validated)
invalid_rows = count_rows(invalid)
out_of_scope_rows = count_rows(out_of_scope)
conflict_rows = count_rows(conflicts)
silver_rows = count_rows(silver)
duplicate_delivery_ids = count_rows(
    identity.filter((F.col("payload_count") == 1) & (F.col("identity_count") > 1))
)
duplicate_delivery_dropped_rows = (
    count_rows(classified.filter((F.col("payload_count") == 1) & (F.col("identity_count") > 1)))
    - duplicate_delivery_ids
)
missing_metadata_rows = count_rows(missing_metadata)
source_kind_counts = {
    row["source_kind"]: row["count"]
    for row in silver.groupBy("source_kind").count().collect()
}
historical_silver_rows = source_kind_counts.get("historical_csv", 0)
realtime_silver_rows = source_kind_counts.get("realtime_json", 0)
canonical_data_sha256 = (
    silver.agg(
        F.sha2(F.concat_ws("\n", F.sort_array(F.collect_list("payload_sha256"))), 256).alias("hash")
    ).first()["hash"]
)
quality_passed = (
    conflict_rows == 0
    and missing_metadata_rows == 0
    and historical_silver_rows > 0
    and realtime_silver_rows > 0
)
report = {
    "run_id": run_id,
    "manifest_id": manifest["manifest_id"],
    "manifest_key": manifest_key,
    "manifest_sha256": manifest_sha256,
    "schema_version": manifest["schema_version"],
    "rules_version": "telemetry-contract-v1",
    "metadata_version": manifest["metadata_version"],
    "window": {
        "start_date": manifest["start_date"],
        "end_date": manifest["end_date"],
        "late_arrival_lookback_days": manifest["late_arrival_lookback_days"],
    },
    "counts": {
        "input_rows": input_rows, "invalid_rows": invalid_rows,
        "out_of_scope_rows": out_of_scope_rows, "conflict_rows": conflict_rows,
        "duplicate_delivery_ids": duplicate_delivery_ids,
        "duplicate_delivery_dropped_rows": duplicate_delivery_dropped_rows,
        "silver_rows": silver_rows, "missing_metadata_rows": missing_metadata_rows,
        "historical_silver_rows": historical_silver_rows,
        "realtime_silver_rows": realtime_silver_rows,
        "gold_rows": count_rows(gold),
    },
    "canonical_data_sha256": canonical_data_sha256,
    "staging_root": staging_root,
    "quality_passed": quality_passed,
    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}
accounted_rows = (
    invalid_rows
    + out_of_scope_rows
    + conflict_rows
    + duplicate_delivery_dropped_rows
    + silver_rows
)
report["counts"]["accounted_rows"] = accounted_rows
report["counts"]["unexplained_rows"] = input_rows - accounted_rows
if report["counts"]["unexplained_rows"] != 0:
    quality_passed = False
    report["quality_passed"] = False
boto3.client("s3").put_object(
    Bucket=bucket,
    Key=f"staging/m3/{run_id}/quality-report.json",
    Body=(json.dumps(report, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    ContentType="application/json",
)
if not quality_passed:
    raise RuntimeError(f"M3 quality gate failed; see {staging_root}/quality-report.json")

# The final pointer is a one-object S3 update. Readers therefore observe the
# previous approved run or a complete new run, never a partially written run.
def assert_prefix_empty(prefix: str):
    existing = boto3.client("s3").list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
    if existing.get("KeyCount", 0):
        raise RuntimeError(f"immutable run output already exists at s3://{bucket}/{prefix}")


silver_partition = f"curated/silver/publication_run_id={run_id}/"
gold_partition = f"curated/gold/publication_run_id={run_id}/"
assert_prefix_empty(silver_partition)
assert_prefix_empty(gold_partition)
silver.write.mode("append").partitionBy("publication_run_id", "event_date").parquet(s3_uri("curated/silver"))
gold.write.mode("append").partitionBy("publication_run_id", "event_date").parquet(s3_uri("curated/gold"))

# The dashboard must not query Athena or deserialize Parquet on every browser
# refresh. Publish a bounded, immutable JSON projection beside the Parquet
# result and advance the small pointer only after it exists.
kpi_summary_key = f"curated/publication/runs/{run_id}/kpi-summary.json"
kpi_summary = []
for row in gold.orderBy(F.desc("event_date"), "esp_id").limit(250).collect():
    kpi_summary.append(
        {
            "event_date": str(row["event_date"]),
            "esp_id": row["esp_id"],
            "avg_liquid_rate_m3_day": float(row["avg_liquid_rate_m3_day"]),
            "avg_oil_rate_m3_day": float(row["avg_oil_rate_m3_day"]),
            "avg_motor_temperature_c": float(row["avg_motor_temperature_c"]),
            "peak_vibration_mm_s": float(row["peak_vibration_mm_s"]),
            "samples": int(row["sample_count"]),
            "relative_flow_deficit": float(row["relative_flow_deficit"]),
        }
    )
boto3.client("s3").put_object(
    Bucket=bucket,
    Key=kpi_summary_key,
    Body=(json.dumps({"schema_version": "dashboard-kpi-summary.v1", "run_id": run_id, "rows": kpi_summary}, sort_keys=True) + "\n").encode("utf-8"),
    ContentType="application/json",
)
publication = {
    "publication_version": 2,
    "published_run_id": run_id,
    "manifest_sha256": manifest_sha256,
    "canonical_data_sha256": canonical_data_sha256,
    "silver_location": s3_uri(silver_partition),
    "gold_location": s3_uri(gold_partition),
    "quality_report": f"{staging_root}/quality-report.json",
    "kpi_summary_key": kpi_summary_key,
    "published_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
}
boto3.client("s3").put_object(
    Bucket=bucket,
    Key="curated/publication/current.json",
    Body=(json.dumps(publication, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    ContentType="application/json",
)
job.commit()
