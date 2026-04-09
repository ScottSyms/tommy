from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from threading import Lock
from typing import Any

import duckdb

from backend.data.overlay import compose_rows, overlay_position


ROOT_DIR = Path(__file__).resolve().parents[2]
SEED_GLOB = str(ROOT_DIR / "data" / "seed" / "**" / "*.parquet")


class DataNotLoadedError(RuntimeError):
    pass


_CONNECTION: duckdb.DuckDBPyConnection | None = None
_CONNECTION_LOCK = Lock()
_LATEST_SHIPS_CACHE: list[dict[str, Any]] | None = None
_LATEST_SHIPS_LOCK = Lock()


def _connect() -> duckdb.DuckDBPyConnection:
    global _CONNECTION
    if _CONNECTION is None:
        with _CONNECTION_LOCK:
            if _CONNECTION is None:
                conn = duckdb.connect(database=":memory:")
                conn.execute(
                    f"CREATE VIEW seed_positions AS SELECT * FROM read_parquet('{SEED_GLOB}', hive_partitioning=true)"
                )
                _CONNECTION = conn
    return _CONNECTION


def ensure_seed_data() -> None:
    if not list((ROOT_DIR / "data" / "seed").glob("date=*/*.parquet")):
        raise DataNotLoadedError(
            "No seed data found under data/seed. Run `python data/generate_seed.py` first."
        )


def _read_records(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    ensure_seed_data()
    conn = _connect()
    frame = conn.execute(query, params or []).fetch_df()
    return frame.to_dict(orient="records")


def _base_scan() -> str:
    return "seed_positions"


def get_latest_ship_features(
    bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    rows = _get_latest_ship_rows()

    features = []
    for row in rows:
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            if not (
                min_lon <= row["lon"] <= max_lon and min_lat <= row["lat"] <= max_lat
            ):
                continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["lon"], row["lat"]],
                },
                "properties": {
                    "mmsi": row["mmsi"],
                    "name": row["name"],
                    "flag": row["flag"],
                    "ship_type": row["ship_type"],
                    "position_id": row["position_id"],
                    "timestamp": row["timestamp"].isoformat(),
                    "sog": row["sog"],
                    "cog": row["cog"],
                    "nav_status": row["nav_status"],
                    "destination": row["destination"],
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def _get_latest_ship_rows() -> list[dict[str, Any]]:
    global _LATEST_SHIPS_CACHE
    if _LATEST_SHIPS_CACHE is None:
        with _LATEST_SHIPS_LOCK:
            if _LATEST_SHIPS_CACHE is None:
                _LATEST_SHIPS_CACHE = _read_records(
                    f"""
                    WITH ranked AS (
                        SELECT *,
                            row_number() OVER (
                                PARTITION BY mmsi
                                ORDER BY timestamp DESC, position_id DESC
                            ) AS row_num
                        FROM {_base_scan()}
                    )
                    SELECT
                        mmsi,
                        imo,
                        name,
                        call_sign,
                        ship_type,
                        flag,
                        length,
                        beam,
                        position_id,
                        timestamp,
                        lat,
                        lon,
                        sog,
                        cog,
                        heading,
                        nav_status,
                        destination
                    FROM ranked
                    WHERE row_num = 1
                    ORDER BY mmsi
                    """
                )
    return _LATEST_SHIPS_CACHE


def get_ship_detail(mmsi: int) -> dict[str, Any] | None:
    rows = get_ship_positions(mmsi)

    if not rows:
        return None

    row = rows[-1]
    return {
        "identity": {
            "mmsi": row["mmsi"],
            "imo": row["imo"],
            "name": row["name"],
            "call_sign": row["call_sign"],
            "ship_type": row["ship_type"],
            "flag": row["flag"],
            "length": row["length"],
            "beam": row["beam"],
        },
        "last_position": {
            "position_id": row["position_id"],
            "timestamp": row["timestamp"].isoformat(),
            "lat": row["lat"],
            "lon": row["lon"],
            "sog": row["sog"],
            "cog": row["cog"],
            "heading": row["heading"],
            "nav_status": row["nav_status"],
            "destination": row["destination"],
        },
    }


def get_ship_positions(mmsi: int) -> list[dict[str, Any]]:
    rows = _read_records(
        f"""
        SELECT
            position_id,
            mmsi,
            imo,
            name,
            call_sign,
            ship_type,
            flag,
            length,
            beam,
            timestamp,
            lat,
            lon,
            sog,
            cog,
            heading,
            nav_status,
            destination
        FROM {_base_scan()}
        WHERE mmsi = ?
        ORDER BY timestamp, position_id
        """,
        [mmsi],
    )
    return compose_rows(mmsi, rows)


def get_position_by_id(position_id: str) -> dict[str, Any] | None:
    overlay_row = overlay_position(position_id)
    if overlay_row is not None:
        return overlay_row

    rows = _read_records(
        f"""
        SELECT
            position_id,
            mmsi,
            imo,
            name,
            call_sign,
            ship_type,
            flag,
            length,
            beam,
            timestamp,
            lat,
            lon,
            sog,
            cog,
            heading,
            nav_status,
            destination
        FROM {_base_scan()}
        WHERE position_id = ?
        LIMIT 1
        """,
        [position_id],
    )
    if not rows:
        return None
    return rows[0]


def get_ship_history(mmsi: int, hours: int) -> dict[str, Any] | None:
    all_rows = get_ship_positions(mmsi)
    if not all_rows:
        return None

    latest_timestamp = all_rows[-1]["timestamp"]
    time_window_start = latest_timestamp - timedelta(hours=hours)
    rows = [row for row in all_rows if row["timestamp"] >= time_window_start]

    coordinates = [[row["lon"], row["lat"]] for row in rows]
    positions = []
    for row in rows:
        positions.append(
            {
                "position_id": row["position_id"],
                "timestamp": row["timestamp"].isoformat(),
                "lat": row["lat"],
                "lon": row["lon"],
                "cog": row["cog"],
                "sog": row["sog"],
                "heading": row["heading"],
                "nav_status": row["nav_status"],
                "destination": row["destination"],
            }
        )

    return {
        "mmsi": mmsi,
        "hours": hours,
        "track": {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "properties": {
                "point_count": len(rows),
                "start_time": rows[0]["timestamp"].isoformat(),
                "end_time": rows[-1]["timestamp"].isoformat(),
            },
        },
        "positions": positions,
    }


def get_recent_destinations(mmsi: int, limit: int) -> list[dict[str, Any]]:
    rows = _read_records(
        f"""
        WITH ranked_destinations AS (
            SELECT
                destination,
                timestamp,
                row_number() OVER (
                    PARTITION BY destination
                    ORDER BY timestamp DESC, position_id DESC
                ) AS row_num
            FROM {_base_scan()}
            WHERE mmsi = ?
              AND destination IS NOT NULL
              AND trim(destination) <> ''
        )
        SELECT destination, timestamp AS last_seen
        FROM ranked_destinations
        WHERE row_num = 1
        ORDER BY last_seen DESC, destination
        LIMIT ?
        """,
        [mmsi, limit],
    )

    return [
        {
            "destination": row["destination"],
            "last_seen": row["last_seen"].isoformat(),
        }
        for row in rows
    ]
