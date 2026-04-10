from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewSchema:
    name: str
    columns: dict[str, str]


APPROVED_VIEWS = {
    "cop_ship_positions": ViewSchema(
        name="cop_ship_positions",
        columns={
            "position_id": "text",
            "mmsi": "bigint",
            "imo": "bigint",
            "name": "text",
            "call_sign": "text",
            "ship_type": "integer",
            "flag": "text",
            "length": "double",
            "beam": "double",
            "timestamp": "timestamp",
            "lat": "double",
            "lon": "double",
            "sog": "double",
            "cog": "double",
            "heading": "double",
            "nav_status": "integer",
            "destination": "text",
            "destination_normalized": "text",
        },
    ),
    "cop_ship_identity": ViewSchema(
        name="cop_ship_identity",
        columns={
            "mmsi": "bigint",
            "imo": "bigint",
            "name": "text",
            "call_sign": "text",
            "ship_type": "integer",
            "flag": "text",
            "length": "double",
            "beam": "double",
        },
    ),
    "cop_latest_ship_positions": ViewSchema(
        name="cop_latest_ship_positions",
        columns={
            "position_id": "text",
            "mmsi": "bigint",
            "name": "text",
            "timestamp": "timestamp",
            "lat": "double",
            "lon": "double",
            "sog": "double",
            "cog": "double",
            "destination": "text",
            "destination_normalized": "text",
        },
    ),
}


def schema_summary() -> str:
    lines: list[str] = []
    for view in APPROVED_VIEWS.values():
        lines.append(f"- {view.name}")
        for column, column_type in view.columns.items():
            lines.append(f"  - {column}: {column_type}")
    return "\n".join(lines)
