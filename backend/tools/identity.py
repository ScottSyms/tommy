from __future__ import annotations

from backend.data.loader import get_ship_detail


def get_ship_identity(mmsi: int) -> dict | None:
    detail = get_ship_detail(mmsi)
    if detail is None:
        return None
    return detail["identity"]
