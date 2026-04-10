from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.sql.schema_registry import schema_summary


SKILL_PATH = Path(__file__).with_name("analytics_skill.md")


def build_sql_prompts(
    question: str,
    selection_context: dict[str, Any] | None,
    chat_history: list[dict[str, Any]] | None,
) -> tuple[str, str]:
    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    system_prompt = f"{skill_text}\n\n## Registered Schema\n{schema_summary()}"

    recent_turns = chat_history or []
    turns_text = (
        "\n".join(
            f"- {turn['role']}: {turn['text']} ({turn['timestamp']})"
            for turn in recent_turns[-6:]
        )
        or "- none"
    )

    selection_text = selection_context or {}
    user_prompt = (
        "Generate SQL for the resolved maritime analytics request.\n"
        f"Current question: {question}\n"
        f"Selection context: {selection_text}\n"
        f"Recent chat turns:\n{turns_text}\n"
    )
    return system_prompt, user_prompt
