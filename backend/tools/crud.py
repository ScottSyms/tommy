from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backend.data.loader import get_position_by_id, get_ship_detail, get_ship_positions
from backend.data.overlay import add_position as overlay_add_position
from backend.data.overlay import delete_position as overlay_delete_position
from backend.data.overlay import update_position as overlay_update_position


def add_position(mmsi: int, lat: float, lon: float, timestamp: str) -> dict:
    detail = get_ship_detail(mmsi)
    parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    identity = detail["identity"] if detail else {}
    last_position = detail["last_position"] if detail else {}
    position = {
        "position_id": str(uuid4()),
        "mmsi": mmsi,
        "imo": identity.get("imo"),
        "name": identity.get("name"),
        "call_sign": identity.get("call_sign"),
        "ship_type": identity.get("ship_type"),
        "flag": identity.get("flag"),
        "length": identity.get("length"),
        "beam": identity.get("beam"),
        "timestamp": parsed_timestamp.astimezone(UTC),
        "lat": lat,
        "lon": lon,
        "sog": last_position.get("sog", 0.0),
        "cog": last_position.get("cog", 0.0),
        "heading": last_position.get("heading"),
        "nav_status": last_position.get("nav_status"),
        "destination": last_position.get("destination"),
    }
    return overlay_add_position(position)


def edit_position(position_id: str, updates: dict) -> dict | None:
    row = get_position_by_id(position_id)
    if row is None:
        return None

    updated = row.copy()
    for key, value in updates.items():
        if key == "timestamp" and isinstance(value, str):
            updated[key] = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).astimezone(UTC)
        else:
            updated[key] = value
    return overlay_update_position(updated)


def delete_position(position_id: str) -> bool:
    row = get_position_by_id(position_id)
    if row is None:
        return False
    overlay_delete_position(position_id)
    return True


def get_merge_candidate(mmsi: int) -> tuple[dict, dict] | None:
    positions = get_ship_positions(mmsi)
    if not positions:
        return None

    latest_timestamp = positions[-1]["timestamp"]
    cutoff = latest_timestamp - timedelta(hours=24)
    positions = [row for row in positions if row["timestamp"] >= cutoff]

    seen: dict[datetime, dict] = {}
    for row in reversed(positions):
        timestamp = row["timestamp"]
        existing = seen.get(timestamp)
        if existing is not None:
            return existing, row
        seen[timestamp] = row
    return None


def merge_positions(
    position_id_1: str, position_id_2: str, resolution: str | None = None
) -> dict | None:
    position_1 = get_position_by_id(position_id_1)
    position_2 = get_position_by_id(position_id_2)
    if position_1 is None or position_2 is None:
        return None

    delta_seconds = abs(
        (position_1["timestamp"] - position_2["timestamp"]).total_seconds()
    )
    if delta_seconds <= 30 and resolution is None:
        return {
            "conflict_type": "timestamp_collision",
            "message": "These positions conflict on timestamp within 30 seconds of each other.",
            "position_1": serialize_position(position_1),
            "position_2": serialize_position(position_2),
            "suggested_resolution": "keep_most_recent",
        }

    if resolution == "keep_other":
        keep_row, delete_row = position_2, position_1
    elif resolution == "keep_1":
        keep_row, delete_row = position_1, position_2
    elif resolution == "keep_2":
        keep_row, delete_row = position_2, position_1
    elif resolution == "manual":
        keep_row, delete_row = manual_merge(position_1, position_2), None
    else:
        keep_row, delete_row = sorted(
            [position_1, position_2],
            key=lambda row: (row["timestamp"], row["position_id"]),
            reverse=True,
        )

    if resolution == "manual":
        overlay_update_position(keep_row)
        overlay_delete_position(position_1["position_id"])
        overlay_delete_position(position_2["position_id"])
        return serialize_position(keep_row)

    overlay_delete_position(delete_row["position_id"])
    return serialize_position(keep_row)


def manual_merge(position_1: dict, position_2: dict) -> dict:
    newest = max(
        [position_1, position_2], key=lambda row: (row["timestamp"], row["position_id"])
    )
    merged = newest.copy()
    merged["lat"] = round((position_1["lat"] + position_2["lat"]) / 2, 5)
    merged["lon"] = round((position_1["lon"] + position_2["lon"]) / 2, 5)
    merged["position_id"] = str(uuid4())
    return merged


def serialize_position(position: dict) -> dict:
    return {
        "position_id": position["position_id"],
        "timestamp": position["timestamp"].isoformat(),
        "lat": position["lat"],
        "lon": position["lon"],
        "sog": position.get("sog"),
        "cog": position.get("cog"),
        "heading": position.get("heading"),
        "nav_status": position.get("nav_status"),
        "destination": position.get("destination"),
    }
