"""Deterministic planning estimate for the ESP capstone in us-east-1.

This is a gross-cost model: it deliberately ignores account credits and shared
free-tier allowances. Replace assumptions with Cost Explorer and service usage
after each cloud run.
"""

from __future__ import annotations

import argparse
import json


PRICE = {
    "kinesis_shard_hour": 0.015,
    "kinesis_million_put_units": 0.014,
    "s3_gb_month": 0.023,
    "s3_thousand_put": 0.005,
    "dynamodb_million_wru": 0.625,
    "dynamodb_million_rru": 0.125,
    "lambda_million_requests": 0.20,
    "lambda_gb_second": 0.0000166667,
    "cloudwatch_log_ingest_gb": 0.50,
    "cloudwatch_log_storage_gb_month": 0.03,
    "glue_dpu_hour": 0.44,
    "athena_tb_scanned": 5.00,
    "step_functions_transition": 0.000025,
    "sns_million_requests": 0.50,
    "sns_hundred_thousand_email": 2.00,
}

ASSUMPTION = {
    "days_per_month": 30,
    "events_per_second": 3,
    "record_bytes": 389,
    "records_per_lambda_batch": 6,
    "ingest_lambda_seconds": 0.5,
    "anomaly_lambda_seconds": 0.1,
    "lambda_memory_gb": 0.25,
    "log_bytes_per_invocation": 500,
    "glue_job_dpus": 2,
    "glue_job_minutes": 10,
    "crawler_dpus": 2,
    "crawler_billed_minutes": 10,
    "athena_queries_per_batch": 10,
    "athena_minimum_mib_per_query": 10,
    "parked_s3_gb_envelope": 1.0,
    "parked_dynamodb_gb_envelope": 0.01,
    "parked_log_gb_envelope": 0.1,
}


def parked_cost() -> dict[str, float]:
    return {
        "S3/storage envelope": ASSUMPTION["parked_s3_gb_envelope"] * PRICE["s3_gb_month"],
        "DynamoDB/storage envelope": ASSUMPTION["parked_dynamodb_gb_envelope"] * 0.25,
        "CloudWatch/stored logs envelope": ASSUMPTION["parked_log_gb_envelope"]
        * PRICE["cloudwatch_log_storage_gb_month"],
    }


def glue_batch_cost(runs: int) -> dict[str, float]:
    job = (
        runs
        * ASSUMPTION["glue_job_dpus"]
        * ASSUMPTION["glue_job_minutes"]
        / 60
        * PRICE["glue_dpu_hour"]
    )
    crawler = (
        runs
        * ASSUMPTION["crawler_dpus"]
        * ASSUMPTION["crawler_billed_minutes"]
        / 60
        * PRICE["glue_dpu_hour"]
    )
    queries = runs * ASSUMPTION["athena_queries_per_batch"]
    athena = (
        queries
        * ASSUMPTION["athena_minimum_mib_per_query"]
        / 1024
        / 1024
        * PRICE["athena_tb_scanned"]
    )
    return {
        "Glue/job": job,
        "Glue/crawler": crawler,
        "Athena": athena,
        "Step Functions": runs * 3 * PRICE["step_functions_transition"],
    }


def realtime_cost(hours: float, *, reserve_shard_hours: float | None = None,
                  batch_s3_writes: bool = False, alert_every_event: bool = False) -> dict[str, float]:
    events = hours * 3600 * ASSUMPTION["events_per_second"]
    batches_per_consumer = events / ASSUMPTION["records_per_lambda_batch"]
    invocations = batches_per_consumer * 2
    s3_puts = batches_per_consumer if batch_s3_writes else events
    shard_hours = hours if reserve_shard_hours is None else reserve_shard_hours
    lambda_gb_seconds = batches_per_consumer * ASSUMPTION["lambda_memory_gb"] * (
        ASSUMPTION["ingest_lambda_seconds"] + ASSUMPTION["anomaly_lambda_seconds"]
    )
    result = {
        "Kinesis/shard": shard_hours * PRICE["kinesis_shard_hour"],
        "Kinesis/PUT units": events / 1_000_000 * PRICE["kinesis_million_put_units"],
        "S3/raw PUT": s3_puts / 1000 * PRICE["s3_thousand_put"],
        "DynamoDB/writes": events / 1_000_000 * PRICE["dynamodb_million_wru"],
        "Lambda/requests": invocations / 1_000_000 * PRICE["lambda_million_requests"],
        "Lambda/compute": lambda_gb_seconds * PRICE["lambda_gb_second"],
        "CloudWatch/log ingestion": invocations
        * ASSUMPTION["log_bytes_per_invocation"]
        / 1_000_000_000
        * PRICE["cloudwatch_log_ingest_gb"],
    }
    if alert_every_event:
        result["SNS/publish requests"] = events / 1_000_000 * PRICE["sns_million_requests"]
        result["SNS/email delivery"] = events / 100_000 * PRICE["sns_hundred_thousand_email"]
    return result


def scenario(name: str, demos: int = 3) -> dict[str, float]:
    costs = parked_cost()
    if name == "parked":
        return costs
    if name in {"demo", "daily-demo"}:
        runs = demos if name == "demo" else ASSUMPTION["days_per_month"]
        demo_hours = 5 / 60
        # Reserve one shard-hour per deploy/run/destroy cycle to avoid understating
        # short-lived stream billing and teardown overhead.
        parts = realtime_cost(demo_hours * runs, reserve_shard_hours=float(runs))
        for key, value in glue_batch_cost(runs).items():
            parts[key] = parts.get(key, 0) + value
        for key, value in parts.items():
            costs[key] = costs.get(key, 0) + value
        return costs
    if name in {"continuous", "continuous-batched-s3", "alert-storm"}:
        hours = ASSUMPTION["days_per_month"] * 24
        parts = realtime_cost(
            hours,
            batch_s3_writes=name == "continuous-batched-s3",
            alert_every_event=name == "alert-storm",
        )
        for key, value in glue_batch_cost(ASSUMPTION["days_per_month"]).items():
            parts[key] = parts.get(key, 0) + value
        for key, value in parts.items():
            costs[key] = costs.get(key, 0) + value
        return costs
    raise ValueError(name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "scenario",
        choices=["parked", "demo", "daily-demo", "continuous", "continuous-batched-s3", "alert-storm"],
    )
    parser.add_argument("--demos", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    costs = scenario(args.scenario, args.demos)
    output = {
        "scenario": args.scenario,
        "region": "us-east-1",
        "currency": "USD",
        "free_tier_or_credits_applied": False,
        "components": {key: round(value, 6) for key, value in costs.items()},
        "total": round(sum(costs.values()), 2),
    }
    if args.json:
        print(json.dumps(output, indent=2))
        return
    print(f"{output['scenario']} ({output['region']}): USD {output['total']:.2f}/month")
    for key, value in sorted(costs.items(), key=lambda item: item[1], reverse=True):
        print(f"  {key:<34} USD {value:>10.4f}")


if __name__ == "__main__":
    main()
