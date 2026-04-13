from __future__ import annotations

from typing import Any

from backend.llm.factory import get_llm_provider
from backend.sql.executor import execute_sql
from backend.sql.prompt_builder import build_sql_prompts
from backend.sql.validator import validate_sql


class SQLServiceError(RuntimeError):
    pass


def run_sql_analytics(
    transcript: str,
    selection_context: dict[str, Any] | None,
    chat_history: list[dict[str, Any]] | None,
    conversation_memory: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        system_prompt, user_prompt = build_sql_prompts(
            transcript, selection_context, chat_history, conversation_memory
        )
        provider = get_llm_provider()
        generated = provider.generate_sql(system_prompt, user_prompt)
        sql = validate_sql(generated.sql)
        execution = execute_sql(sql)
        summary = summarize_result(execution, selection_context, conversation_memory)
        return {
            "reply": summary,
            "action": "SHOW_PANEL",
            "payload": {
                "mmsi": selection_context.get("mmsi") if selection_context else None,
                "insight": {
                    "title": "Analytics Query",
                    "summary": summary,
                    "result_preview": execution,
                    "provider": generated.provider,
                    "model": generated.model,
                },
            },
        }
    except Exception as exc:
        raise SQLServiceError(str(exc)) from exc


def summarize_result(
    execution: dict[str, Any],
    selection_context: dict[str, Any] | None,
    conversation_memory: dict[str, Any] | None,
) -> str:
    row_count = execution["row_count"]
    rows = execution["rows"]
    columns = execution["columns"]
    subject = resolve_subject_name(execution, selection_context, conversation_memory)
    if row_count == 0:
        if subject:
            return f"I did not find any matching records for {subject}."
        return "I did not find any matching records."

    first_row = rows[0]
    natural_summary = summarize_common_patterns(subject, first_row, columns, row_count)
    if natural_summary:
        return natural_summary

    if row_count == 1 and len(columns) == 1:
        if subject:
            return f"For {subject}, the result is {first_row[columns[0]]}."
        return f"The result is {first_row[columns[0]]}."

    if row_count == 1:
        details = ", ".join(f"{column}={first_row[column]}" for column in columns[:3])
        if subject:
            return f"For {subject}, I found one matching record: {details}."
        return f"I found one matching record: {details}."

    if columns:
        details = ", ".join(f"{column}={first_row[column]}" for column in columns[:3])
        if subject:
            return f"For {subject}, I found {row_count} matching rows. The first result is {details}."
        return f"I found {row_count} matching rows. The first result is {details}."

    return f"I found {row_count} matching rows."


def resolve_subject_name(
    execution: dict[str, Any],
    selection_context: dict[str, Any] | None,
    conversation_memory: dict[str, Any] | None,
) -> str | None:
    rows = execution.get("rows") or []
    if rows:
        first_row = rows[0]
        if first_row.get("name"):
            return str(first_row["name"])
    if selection_context and selection_context.get("name"):
        return str(selection_context["name"])
    remembered_vessel = (conversation_memory or {}).get("active_vessel") or {}
    if remembered_vessel.get("name"):
        return str(remembered_vessel["name"])
    return None


def summarize_common_patterns(
    subject: str | None,
    first_row: dict[str, Any],
    columns: list[str],
    row_count: int,
) -> str | None:
    named_subject = subject or "This ship"

    if row_count == 1 and "max_sog" in first_row:
        return (
            f"{named_subject} reached a maximum speed of {first_row['max_sog']} knots."
        )

    if row_count == 1 and "avg_sog" in first_row:
        return f"{named_subject} averaged {first_row['avg_sog']} knots over the requested period."

    if row_count == 1 and "count" in first_row:
        return f"{named_subject} matched that query {first_row['count']} times."

    if row_count == 1 and "destination" in first_row and "timestamp" in first_row:
        return (
            f"{named_subject} was recorded near {first_row['destination']} at "
            f"{first_row['timestamp']}."
        )

    if row_count == 1 and "destination" in first_row and "last_seen" in first_row:
        return (
            f"{named_subject} was last seen with destination {first_row['destination']} "
            f"at {first_row['last_seen']}."
        )

    if row_count == 1 and "lat" in first_row and "lon" in first_row:
        timestamp = first_row.get("timestamp")
        if timestamp:
            return (
                f"{named_subject} was at latitude {first_row['lat']} and longitude {first_row['lon']} "
                f"at {timestamp}."
            )
        return f"{named_subject} was at latitude {first_row['lat']} and longitude {first_row['lon']}."

    if row_count > 1 and "destination" in columns:
        destinations = [
            row.get("destination") for row in [first_row] if row.get("destination")
        ]
        if destinations:
            return f"I found {row_count} matching records for {named_subject}. The first destination is {destinations[0]}."

    return None
