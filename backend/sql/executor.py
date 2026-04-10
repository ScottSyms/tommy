from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd

from backend.data.loader import (
    get_all_ship_identity,
    get_all_ship_positions,
    normalize_destination,
)


def execute_sql(sql: str) -> dict[str, Any]:
    positions = pd.DataFrame(get_all_ship_positions())
    if positions.empty:
        positions = pd.DataFrame(
            columns=[
                "position_id",
                "mmsi",
                "imo",
                "name",
                "call_sign",
                "ship_type",
                "flag",
                "length",
                "beam",
                "timestamp",
                "lat",
                "lon",
                "sog",
                "cog",
                "heading",
                "nav_status",
                "destination",
            ]
        )
    if "destination" in positions.columns:
        positions["destination_normalized"] = (
            positions["destination"].fillna("").map(normalize_destination)
        )

    identity = pd.DataFrame(get_all_ship_identity())
    latest = (
        positions.sort_values(["mmsi", "timestamp", "position_id"])
        .groupby("mmsi", as_index=False)
        .tail(1)
    )

    conn = duckdb.connect(database=":memory:")
    try:
        conn.register("cop_ship_positions_df", positions)
        conn.register("cop_ship_identity_df", identity)
        conn.register("cop_latest_ship_positions_df", latest)
        conn.execute(
            "CREATE VIEW cop_ship_positions AS SELECT * FROM cop_ship_positions_df"
        )
        conn.execute(
            "CREATE VIEW cop_ship_identity AS SELECT * FROM cop_ship_identity_df"
        )
        conn.execute(
            "CREATE VIEW cop_latest_ship_positions AS SELECT * FROM cop_latest_ship_positions_df"
        )
        frame = conn.execute(sql).fetch_df()
    finally:
        conn.close()

    preview = frame.head(10)
    return {
        "columns": preview.columns.tolist(),
        "rows": preview.to_dict(orient="records"),
        "row_count": int(len(frame.index)),
    }
