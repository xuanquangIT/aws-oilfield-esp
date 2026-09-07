"""Generate synthetic historical ESP telemetry as schema v1 CSV.

With --seed and --start-time, generation is fully deterministic (same rows,
same event_id values), matching the M1 requirement that seed generation take
--seed/--start-time so a fixture checksum is repeatable. Without them,
behavior is unchanged from before: current time minus 7 days, non-seeded
randomness.
"""

import argparse
import csv
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from contract import SCHEMA_VERSION, iso_z, new_event_id, parse_iso_utc  # noqa: E402

ESP_IDS = ["ESP-101", "ESP-102", "ESP-103"]
COLUMNS = [
    "schema_version",
    "event_id",
    "timestamp",
    "esp_id",
    "source",
    "run_id",
    "flow_rate",
    "water_cut",
    "intake_pressure",
    "discharge_pressure",
    "motor_temperature",
    "motor_current",
    "vibration",
    "status",
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Deterministic RNG seed and event_id namespace key, for a repeatable fixture checksum.",
    )
    p.add_argument(
        "--start-time",
        default=None,
        help="ISO-8601 UTC start of the 7-day window, e.g. 2026-01-01T00:00:00Z. "
        "Defaults to (now - 7 days) when omitted.",
    )
    p.add_argument("--out", default="data/historical.csv")
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
        start = datetime.now(timezone.utc) - timedelta(days=7)
    run_id = (
        new_event_id(f"batch|{a.seed}|{a.start_time}")
        if deterministic
        else new_event_id()
    )

    out = Path(a.out)
    rows = []
    for i in range(7 * 24):
        ts = start + timedelta(hours=i)
        for esp in ESP_IDS:
            flow = 110 + rng.uniform(-10, 10)
            id_key = f"{run_id}|{esp}|{i}" if deterministic else None
            rows.append(
                [
                    SCHEMA_VERSION,
                    new_event_id(id_key),
                    iso_z(ts),
                    esp,
                    "historical",
                    run_id,
                    round(flow, 2),
                    0.35,
                    700,
                    1600,
                    92,
                    68,
                    2.5,
                    "RUNNING",
                ]
            )

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(out)


if __name__ == "__main__":
    main()
