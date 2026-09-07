"""Synthetic normalized ESP telemetry producer.

The generated event fuses placeholder downhole-gauge, surface VSD/SCADA, and
production-meter signals. It is not the raw output of a single sensor such as
the Phoenix xt150. Business meaning and units for its normalized fields:

    flow_rate             liquid production rate, m3/day (instantaneous)
    water_cut             fraction of liquid that is water, 0..1
    intake_pressure       pump intake pressure, psi
    discharge_pressure    pump discharge pressure, psi
    tubing_pressure       tubing pressure, psi
    casing_pressure       casing pressure, psi
    intake_temperature    intake temperature, degrees Celsius
    motor_temperature     motor temperature, degrees Celsius
    vibration             illustrative vibration amplitude, mm/s
    motor_current         motor electrical current, A
    pump_frequency        pump operating frequency, Hz

``timestamp`` is the UTC observation time. ``esp_id``, ``scenario`` and
``status`` identify the synthetic pump and operating condition. These values
are educational synthetic signals, not calibrated field measurements. The
field provenance and scope are documented in ``docs/03-DATA-DOMAIN-AND-CONTRACT.md``.

Every event sent to Kinesis is wrapped in the schema v1 contract envelope
(schema_version, event_id, source, run_id) defined in ``src/contract.py``.
With ``--seed`` and ``--start-time``, generation is fully deterministic:
signal values, timestamps and event_ids are all reproducible, which is what
lets a fixture checksum stay stable across runs (see docs/06-DELIVERY-AND-LEARNING.md, M1).

M2: each send is retried with bounded exponential backoff on a transient or
throttling failure, always resending the exact same event (event_id is never
regenerated on retry). A send that still fails after all attempts is appended
to ``data/producer-failures.jsonl`` for manual reconciliation or replay,
rather than crashing the run or silently vanishing; the run prints an
acknowledged/failed summary at the end.
"""

import argparse
import json
import math
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from contract import SCHEMA_VERSION, iso_z, new_event_id, parse_iso_utc  # noqa: E402

ESP_IDS = ["ESP-101", "ESP-102", "ESP-103"]


def signal(esp, tick, scenario, rng=random):
    """Compute the physical signal fields only (no contract envelope)."""
    flow, intake, discharge = (
        120 + rng.uniform(-4, 4),
        700 + rng.uniform(-8, 8),
        1600 + rng.uniform(-15, 15),
    )
    temp, vib, current = (
        92 + rng.uniform(-2, 2),
        2.5 + rng.uniform(-0.3, 0.3),
        68 + rng.uniform(-2, 2),
    )
    tubing, casing, freq = 700 + rng.uniform(-10, 10), 500 + rng.uniform(-10, 10), 60.0
    status = "RUNNING"
    if scenario == "gas_slug":
        wave = math.sin(tick / 5) * 35
        flow += wave
        intake -= wave * 0.6
        current += abs(wave) * 0.15
    elif scenario == "low_flow":
        flow, temp, current, discharge = (
            42 + rng.uniform(-3, 3),
            137 + rng.uniform(-3, 3),
            82 + rng.uniform(-2, 2),
            1510,
        )
    elif scenario == "mechanical":
        vib = min(16, 3 + tick * 0.08) + rng.uniform(-0.5, 0.5)
        current = 72 + tick * 0.06
        discharge -= min(220, tick * 1.5)
    elif scenario == "blockage":
        tubing, flow, discharge, current, temp = (
            1000 + rng.uniform(-20, 20),
            42 + rng.uniform(-3, 3),
            1630,
            84,
            125,
        )
    elif scenario == "sensor_fault":
        temp = 91.0
    elif scenario == "shutdown":
        status, flow, current, freq, vib, temp = "SHUTDOWN", 0.0, 0.0, 0.0, 0.0, 75.0
    return {
        "status": status,
        "intake_pressure": round(intake, 2),
        "discharge_pressure": round(discharge, 2),
        "intake_temperature": 78.0,
        "motor_temperature": round(temp, 2),
        "vibration": round(max(vib, 0), 2),
        "motor_current": round(max(current, 0), 2),
        "pump_frequency": freq,
        "tubing_pressure": round(tubing, 2),
        "casing_pressure": round(casing, 2),
        "flow_rate": round(max(flow, 0), 2),
        "water_cut": 0.35,
    }


def put_with_retry(
    client, stream_name, event, max_attempts=5, base_delay=0.2, max_delay=5.0
):
    """Send one event with bounded exponential backoff and jitter.

    Always retries the same event dict (its event_id is never regenerated),
    so a retried send is a true redelivery, not a new logical event. Returns
    True if any attempt succeeded, False if every attempt failed.
    """
    data = (json.dumps(event) + "\n").encode()
    for attempt in range(1, max_attempts + 1):
        try:
            client.put_record(
                StreamName=stream_name, Data=data, PartitionKey=event["esp_id"]
            )
            return True
        except (ClientError, EndpointConnectionError):
            if attempt == max_attempts:
                return False
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            time.sleep(delay + random.uniform(0, delay * 0.25))
    return False


def build_event(esp, tick, scenario, rng, event_time, run_id, deterministic):
    """Wrap a signal reading in the schema v1 contract envelope."""
    measurements = signal(esp, tick, scenario, rng)
    id_key = f"{run_id}|{esp}|{tick}" if deterministic else None
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": new_event_id(id_key),
        "timestamp": iso_z(event_time),
        "esp_id": esp,
        "source": "realtime",
        "run_id": run_id,
        "scenario": scenario,
        **measurements,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stream-name", required=True)
    p.add_argument(
        "--scenario",
        default="normal",
        choices=[
            "normal",
            "gas_slug",
            "low_flow",
            "mechanical",
            "blockage",
            "sensor_fault",
            "shutdown",
        ],
    )
    p.add_argument("--seconds", type=int, default=600)
    p.add_argument("--interval", type=float, default=1)
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Deterministic RNG seed and event_id namespace key, for repeatable fixtures.",
    )
    p.add_argument(
        "--start-time",
        default=None,
        help="ISO-8601 UTC start time for deterministic event timestamps, e.g. 2026-01-01T00:00:00Z. "
        "Requires --seed. Defaults to current time when omitted.",
    )
    a = p.parse_args()

    deterministic = a.seed is not None
    rng = random.Random(a.seed) if deterministic else random
    if a.start_time:
        start = parse_iso_utc(a.start_time)
        if start is None:
            raise SystemExit(
                f"--start-time {a.start_time!r} is not a valid UTC ISO-8601 timestamp"
            )
    else:
        start = datetime.now(timezone.utc)
    run_id = (
        new_event_id(f"run|{a.seed}|{a.start_time}")
        if deterministic
        else new_event_id()
    )

    k = boto3.client("kinesis")
    acknowledged, failed = 0, 0
    failures_path = Path("data/producer-failures.jsonl")
    for tick in range(a.seconds):
        event_time = (
            start + timedelta(seconds=tick)
            if deterministic
            else datetime.now(timezone.utc)
        )
        for esp in ESP_IDS:
            event = build_event(
                esp, tick, a.scenario, rng, event_time, run_id, deterministic
            )
            if put_with_retry(k, a.stream_name, event):
                acknowledged += 1
            else:
                failed += 1
                failures_path.parent.mkdir(parents=True, exist_ok=True)
                with failures_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(event) + "\n")
        time.sleep(a.interval)

    print(f"Producer summary: acknowledged={acknowledged} failed={failed}")
    if failed:
        print(
            f"{failed} send(s) failed after retries and were appended to "
            f"{failures_path} for manual reconciliation or replay."
        )


if __name__ == "__main__":
    main()
