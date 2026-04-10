from __future__ import annotations

from backend.data.loader import get_speed_extremes, query_destination_history


def query_destination_history_tool(mmsi: int, destination: str) -> dict:
    return query_destination_history(mmsi, destination)


def query_speed_summary_tool(mmsi: int) -> dict | None:
    return get_speed_extremes(mmsi)
