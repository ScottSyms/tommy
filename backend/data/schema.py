from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Position(BaseModel):
    position_id: str
    mmsi: int
    imo: int | None
    timestamp: datetime
    lat: float
    lon: float
    sog: float
    cog: float
    heading: float | None
    nav_status: int | None
    ship_type: int | None
    flag: str | None
    destination: str | None


class ShipIdentity(BaseModel):
    mmsi: int
    imo: int | None
    name: str | None
    call_sign: str | None
    ship_type: int | None
    flag: str | None
    length: float | None
    beam: float | None
