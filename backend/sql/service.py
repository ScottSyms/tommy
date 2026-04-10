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
) -> dict[str, Any]:
    try:
        system_prompt, user_prompt = build_sql_prompts(
            transcript, selection_context, chat_history
        )
        provider = get_llm_provider()
        generated = provider.generate_sql(system_prompt, user_prompt)
        sql = validate_sql(generated.sql)
        execution = execute_sql(sql)
        summary = summarize_result(execution)
        return {
            "reply": summary,
            "action": "SHOW_PANEL",
            "payload": {
                "mmsi": selection_context.get("mmsi") if selection_context else None,
                "insight": {
                    "title": "Analytics Query",
                    "summary": summary,
                    "generated_sql": sql,
                    "result_preview": execution,
                    "provider": generated.provider,
                    "model": generated.model,
                },
            },
        }
    except Exception as exc:
        raise SQLServiceError(str(exc)) from exc


def summarize_result(execution: dict[str, Any]) -> str:
    row_count = execution["row_count"]
    rows = execution["rows"]
    columns = execution["columns"]
    if row_count == 0:
        return "I did not find any matching records."

    first_row = rows[0]
    if row_count == 1 and len(columns) == 1:
        return f"The result is {first_row[columns[0]]}."

    if row_count == 1:
        details = ", ".join(f"{column}={first_row[column]}" for column in columns[:3])
        return f"I found one matching record: {details}."

    if columns:
        details = ", ".join(f"{column}={first_row[column]}" for column in columns[:3])
        return f"I found {row_count} matching rows. The first result is {details}."

    return f"I found {row_count} matching rows."
