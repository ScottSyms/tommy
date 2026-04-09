from __future__ import annotations

import math
import random
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT_DIR / "data" / "seed"

SHIP_TYPES = [60, 70, 71, 79]
FLAGS = ["CA", "US", "GB", "NO", "DK", "PA", "LR"]
DESTINATIONS = [
    "Halifax",
    "Saint John",
    "New York",
    "St. John's",
    "Boston",
    "Rotterdam",
]
NAV_STATUSES = [0, 0, 0, 0, 5]


def build_ship_identity(index: int) -> dict:
    mmsi = 316000000 + index
    ship_type = SHIP_TYPES[index % len(SHIP_TYPES)]
    flag = FLAGS[index % len(FLAGS)]
    return {
        "mmsi": mmsi,
        "imo": 9300000 + index,
        "name": f"MV ATLANTIC {index:03d}",
        "call_sign": f"C{index:03d}A",
        "ship_type": ship_type,
        "flag": flag,
        "length": round(140 + (index % 50) * 2.5, 1),
        "beam": round(22 + (index % 14) * 0.9, 1),
    }


def vessel_track(
    index: int, timestamp: datetime, rng: random.Random
) -> tuple[float, float, float, float]:
    hours_from_start = (
        timestamp - (datetime.now(UTC) - timedelta(days=7))
    ).total_seconds() / 3600
    origin_lat = 43.8 + (index % 20) * 0.08
    origin_lon = -65.8 + (index % 25) * 0.12
    angle = (hours_from_start * 6 + index * 11) % 360
    radius_lat = 0.25 + (index % 7) * 0.04
    radius_lon = 0.4 + (index % 9) * 0.05
    lat = (
        origin_lat
        + math.sin(math.radians(angle)) * radius_lat
        + rng.uniform(-0.015, 0.015)
    )
    lon = (
        origin_lon
        + math.cos(math.radians(angle)) * radius_lon
        + rng.uniform(-0.02, 0.02)
    )
    sog = round(8 + (index % 6) * 1.2 + rng.uniform(-1.2, 1.2), 1)
    cog = round((angle + rng.uniform(-12, 12)) % 360, 1)
    return lat, lon, sog, cog


def generate_rows() -> list[dict]:
    rng = random.Random(7)
    rows: list[dict] = []
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(
        days=7
    )
    interval = timedelta(minutes=10)
    steps = int((timedelta(days=7) / interval))

    for index in range(200):
        identity = build_ship_identity(index)
        duplicate_at = rng.randint(max(12, steps - 144), steps - 12)
        for step in range(steps + 1):
            timestamp = start + step * interval
            lat, lon, sog, cog = vessel_track(index, timestamp, rng)
            destination = DESTINATIONS[(step // 48 + index) % len(DESTINATIONS)]
            row = {
                "position_id": str(uuid.uuid4()),
                **identity,
                "timestamp": timestamp,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "sog": sog,
                "cog": cog,
                "heading": round((cog + rng.uniform(-4, 4)) % 360, 1),
                "nav_status": NAV_STATUSES[(step + index) % len(NAV_STATUSES)],
                "destination": destination,
            }
            rows.append(row)

            if step == duplicate_at:
                duplicate_row = row.copy()
                duplicate_row["position_id"] = str(uuid.uuid4())
                duplicate_row["lat"] = round(row["lat"] + rng.uniform(-0.01, 0.01), 5)
                duplicate_row["lon"] = round(row["lon"] + rng.uniform(-0.01, 0.01), 5)
                duplicate_row["sog"] = round(
                    max(0.0, row["sog"] + rng.uniform(-0.8, 0.8)), 1
                )
                duplicate_row["cog"] = round((row["cog"] + rng.uniform(-8, 8)) % 360, 1)
                duplicate_row["heading"] = round(
                    (duplicate_row["cog"] + rng.uniform(-4, 4)) % 360, 1
                )
                rows.append(duplicate_row)

    return rows


def write_seed_data(rows: list[dict]) -> None:
    if SEED_DIR.exists():
        shutil.rmtree(SEED_DIR)
    SEED_DIR.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(rows)
    frame["date"] = frame["timestamp"].dt.strftime("%Y-%m-%d")

    for date_value, partition in frame.groupby("date"):
        partition_dir = SEED_DIR / f"date={date_value}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        partition.drop(columns=["date"]).to_parquet(
            partition_dir / "positions.parquet",
            index=False,
        )


def main() -> None:
    rows = generate_rows()
    write_seed_data(rows)
    print(f"Wrote {len(rows)} synthetic AIS positions to {SEED_DIR}")


if __name__ == "__main__":
    main()
