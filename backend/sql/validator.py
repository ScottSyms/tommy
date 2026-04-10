from __future__ import annotations

import re

from backend.config import get_settings
from backend.sql.schema_registry import APPROVED_VIEWS


BANNED_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "attach",
    "copy",
    "pragma",
    "install",
    "load",
    "call",
    "truncate",
    "replace",
    "merge",
}


def validate_sql(sql: str) -> str:
    candidate = sql.strip().rstrip(";")
    lowered = candidate.lower()

    if not lowered.startswith(("select", "with")):
        raise ValueError("Generated SQL must start with SELECT or WITH.")
    if ";" in candidate:
        raise ValueError("Generated SQL must contain only one statement.")
    if any(re.search(rf"\b{keyword}\b", lowered) for keyword in BANNED_KEYWORDS):
        raise ValueError("Generated SQL contains a disallowed keyword.")

    cte_names = set(
        re.findall(r"(?:with|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", lowered)
    )
    referenced_names = set(
        re.findall(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", lowered)
    )
    allowed_names = set(APPROVED_VIEWS) | cte_names
    disallowed = [name for name in referenced_names if name not in allowed_names]
    if disallowed:
        raise ValueError(
            f"Generated SQL references unapproved views: {', '.join(sorted(disallowed))}."
        )

    if not re.search(r"\blimit\b", lowered) and not is_aggregate_query(lowered):
        candidate = f"{candidate}\nLIMIT {get_settings().sql_result_limit}"

    return candidate


def is_aggregate_query(lowered_sql: str) -> bool:
    return bool(
        re.search(r"\b(count|min|max|avg|sum|arg_max|arg_min)\s*\(", lowered_sql)
    )
