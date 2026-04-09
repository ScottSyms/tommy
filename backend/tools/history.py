from __future__ import annotations

from backend.data.loader import get_ship_history


def get_position_history(mmsi: int, time_range_hours: int) -> dict | None:
    return get_ship_history(mmsi, time_range_hours)
