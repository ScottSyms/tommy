from __future__ import annotations

from backend.data.loader import get_recent_destinations


def get_recent_destinations_tool(mmsi: int, limit: int) -> list[dict]:
    return get_recent_destinations(mmsi, limit)
