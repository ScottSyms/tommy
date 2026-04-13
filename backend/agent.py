from __future__ import annotations

import re
from typing import Any

from backend.data.loader import get_ship_detail
from backend.sql.service import SQLServiceError, run_sql_analytics
from backend.tools.crud import add_position, get_merge_candidate, merge_positions
from backend.tools.destinations import get_recent_destinations_tool
from backend.tools.history import get_position_history
from backend.tools.identity import get_ship_identity


SYSTEM_PROMPT = """
You are a maritime COP assistant. You help analysts query, edit, and understand
AIS ship data through natural language.

Always resolve commands to one of: SELECT, QUERY, ADD, EDIT, DELETE, MERGE.
If the user's intent is ambiguous, ask exactly one clarifying question.
If a required parameter is missing, ask for it - do not guess.
If a conflict is detected during MERGE or EDIT, return a structured conflict
report rather than proceeding silently.

The user's current map selection context will be provided with each query.
Prefer the selected ship as the implicit subject when MMSI is not stated.
Keep all spoken responses under 3 sentences. Be direct and precise.
""".strip()


def run_agent_query(
    transcript: str,
    selection_context: dict[str, Any] | None,
    chat_history: list[dict[str, Any]] | None,
    conversation_memory: dict[str, Any] | None,
) -> dict[str, Any]:
    text = transcript.strip()
    if not text:
        return {"reply": "I did not catch that.", "action": None, "payload": None}

    normalized = text.lower()
    subject_mmsi = resolve_subject_mmsi(text, selection_context, conversation_memory)

    if is_identity_query(normalized):
        if subject_mmsi is None:
            return clarify_missing_subject()

        detail = get_ship_detail(subject_mmsi)
        if detail is None:
            return not_found_reply(subject_mmsi)

        identity = get_ship_identity(subject_mmsi)
        last_position = detail["last_position"]
        vessel_name = vessel_label(
            identity=identity, selection_context=selection_context
        )
        reply = (
            f"{vessel_name} is flagged {identity['flag'] or 'unknown'} and is currently making "
            f"{last_position['sog']} knots."
        )
        return {
            "reply": reply,
            "action": "SHOW_PANEL",
            "payload": {"mmsi": subject_mmsi, "ship_detail": detail},
        }

    if is_track_query(normalized):
        if subject_mmsi is None:
            return clarify_missing_subject()

        history = get_position_history(subject_mmsi, 24)
        if history is None:
            return not_found_reply(subject_mmsi)

        detail = get_ship_detail(subject_mmsi)
        vessel_name = vessel_label(
            identity=detail["identity"] if detail else None,
            selection_context=selection_context,
        )

        return {
            "reply": f"I’m showing the last 24 hours for {vessel_name}.",
            "action": "SHOW_TRACK",
            "payload": {"mmsi": subject_mmsi, "history": history},
        }

    if is_recent_destinations_query(normalized):
        if subject_mmsi is None:
            return clarify_missing_subject()

        destinations = get_recent_destinations_tool(subject_mmsi, 5)
        if not destinations:
            return not_found_reply(subject_mmsi)

        detail = get_ship_detail(subject_mmsi)
        vessel_name = vessel_label(
            identity=detail["identity"] if detail else None,
            selection_context=selection_context,
        )
        latest_names = ", ".join(entry["destination"] for entry in destinations[:3])
        return {
            "reply": f"Here are the latest destinations for {vessel_name}. Recent ports include {latest_names}.",
            "action": "SHOW_PANEL",
            "payload": {"mmsi": subject_mmsi, "destinations": destinations},
        }

    if is_add_query(normalized):
        coordinates = extract_coordinates(text)
        if subject_mmsi is None:
            return clarify_missing_subject()
        if coordinates is None:
            return {
                "reply": "I need latitude and longitude before I can add a position here.",
                "action": None,
                "payload": None,
            }

        lat, lon = coordinates
        timestamp = (
            selection_context.get("last_position", {}).get("timestamp")
            if selection_context
            else None
        )
        if timestamp is None:
            return {
                "reply": "I need a reference timestamp before I can add that position.",
                "action": None,
                "payload": None,
            }

        position = add_position(subject_mmsi, lat, lon, timestamp)
        detail = get_ship_detail(subject_mmsi)
        vessel_name = vessel_label(
            identity=detail["identity"] if detail else None,
            selection_context=selection_context,
        )
        return {
            "reply": f"I added a new position for {vessel_name} and refreshed the track.",
            "action": "SHOW_TRACK",
            "payload": {
                "mmsi": subject_mmsi,
                "position": serialize_position(position),
                "history": get_position_history(subject_mmsi, 24),
            },
        }

    if is_merge_query(normalized):
        if subject_mmsi is None:
            return clarify_missing_subject()

        candidate = get_merge_candidate(subject_mmsi)
        detail = get_ship_detail(subject_mmsi)
        vessel_name = vessel_label(
            identity=detail["identity"] if detail else None,
            selection_context=selection_context,
        )
        if candidate is None:
            return {
                "reply": f"I did not find any duplicate positions to merge for {vessel_name}.",
                "action": None,
                "payload": None,
            }

        result = merge_positions(
            candidate[0]["position_id"], candidate[1]["position_id"]
        )
        if result and result.get("conflict_type"):
            return {
                "reply": f"I found a timestamp conflict for {vessel_name}. Most recent wins by default.",
                "action": "SHOW_CONFLICT",
                "payload": result | {"mmsi": subject_mmsi},
            }

        return {
            "reply": f"I merged the duplicate positions for {vessel_name} and refreshed the track.",
            "action": "SHOW_TRACK",
            "payload": {
                "mmsi": subject_mmsi,
                "history": get_position_history(subject_mmsi, 24),
            },
        }

    if is_edit_query(normalized):
        vessel_name = vessel_label(selection_context=selection_context)
        return {
            "reply": f"Which position should I edit for {vessel_name}? Give me the position identifier or updated coordinates.",
            "action": None,
            "payload": None,
        }

    if is_delete_query(normalized):
        vessel_name = vessel_label(selection_context=selection_context)
        return {
            "reply": f"Which position should I delete for {vessel_name}? I need a specific position identifier before I proceed.",
            "action": None,
            "payload": None,
        }

    if should_route_to_sql(
        normalized, selection_context, chat_history, conversation_memory
    ):
        try:
            resolved_question = resolve_analytics_question(
                text,
                selection_context,
                chat_history,
                conversation_memory,
            )
            return run_sql_analytics(
                resolved_question,
                selection_context,
                chat_history,
                conversation_memory,
            )
        except SQLServiceError as exc:
            return {
                "reply": f"I could not complete that analytics query: {exc}",
                "action": None,
                "payload": None,
            }

    return {
        "reply": "I can identify a ship, show its last 24 hours, list recent destinations, or help with a merge conflict.",
        "action": None,
        "payload": {"chat_history_count": len((chat_history or [])[-6:])},
    }


def resolve_subject_mmsi(
    text: str,
    selection_context: dict[str, Any] | None,
    conversation_memory: dict[str, Any] | None,
) -> int | None:
    explicit = re.search(r"\b(\d{9})\b", text)
    if explicit:
        return int(explicit.group(1))
    if selection_context and selection_context.get("mmsi"):
        return int(selection_context["mmsi"])
    remembered_vessel = (conversation_memory or {}).get("active_vessel") or {}
    if remembered_vessel.get("mmsi"):
        return int(remembered_vessel["mmsi"])
    return None


def extract_coordinates(text: str) -> tuple[float, float] | None:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(numbers) < 2:
        return None
    lat, lon = float(numbers[0]), float(numbers[1])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def extract_destination_name(text: str) -> str | None:
    match = re.search(
        r"\b(?:to|been to|visit|visited)\s+([a-zA-Z.'\-\s]+)\??$", text, re.IGNORECASE
    )
    if not match:
        return None
    return match.group(1).strip(" ?.!")


def resolve_followup_destination(
    chat_history: list[dict[str, Any]] | None,
    conversation_memory: dict[str, Any] | None,
) -> str | None:
    remembered_destination = (conversation_memory or {}).get("last_destination")
    if remembered_destination:
        return remembered_destination
    if not chat_history:
        return None
    for entry in chat_history:
        if entry.get("role") != "user":
            continue
        destination_name = extract_destination_name(entry.get("text", ""))
        if destination_name:
            return destination_name
    return None


def format_time(timestamp: str | None) -> str:
    if not timestamp:
        return "an unknown time"
    return timestamp.replace("T", " ").replace("+00:00", "Z")


def clarify_missing_subject() -> dict[str, Any]:
    return {
        "reply": "Which ship should I use? Select one on the map or tell me its MMSI.",
        "action": None,
        "payload": None,
    }


def not_found_reply(mmsi: int) -> dict[str, Any]:
    return {
        "reply": f"I could not find a ship with MMSI {mmsi}. Select another ship or verify the MMSI.",
        "action": None,
        "payload": None,
    }


def vessel_label(
    identity: dict[str, Any] | None = None,
    selection_context: dict[str, Any] | None = None,
    conversation_memory: dict[str, Any] | None = None,
) -> str:
    if identity and identity.get("name"):
        return identity["name"]
    if selection_context and selection_context.get("name"):
        return selection_context["name"]
    remembered_vessel = (conversation_memory or {}).get("active_vessel") or {}
    if remembered_vessel.get("name"):
        return remembered_vessel["name"]
    return "the selected vessel"


def is_identity_query(text: str) -> bool:
    return (
        "what is this vessel" in text
        or "show me this ship" in text
        or "what is this ship" in text
    )


def is_track_query(text: str) -> bool:
    return "last 24 hours" in text or "24 hour" in text or "24h" in text


def is_recent_destinations_query(text: str) -> bool:
    return "destination" in text and (
        "last" in text or "recent" in text or text.startswith("show")
    )


def is_add_query(text: str) -> bool:
    return text.startswith("add a position") or "add position" in text


def is_merge_query(text: str) -> bool:
    return "merge" in text and "track" in text


def is_edit_query(text: str) -> bool:
    return text.startswith("edit")


def is_delete_query(text: str) -> bool:
    return text.startswith("delete")


def should_route_to_sql(
    text: str,
    selection_context: dict[str, Any] | None,
    chat_history: list[dict[str, Any]] | None,
    conversation_memory: dict[str, Any] | None,
) -> bool:
    analytics_keywords = {
        "been to",
        "visited",
        "when",
        "fastest",
        "top speed",
        "max speed",
        "how many",
        "count",
        "average",
        "avg",
        "most recent",
        "first seen",
    }
    if any(keyword in text for keyword in analytics_keywords):
        return True
    if text.endswith("?"):
        return True
    if selection_context and chat_history:
        return text in {"when", "when?", "how many", "how many times?"}
    if conversation_memory and text in {
        "when",
        "when?",
        "how many",
        "how many times?",
        "what about that?",
        "what about the previous one?",
        "what about the last one?",
        "show that again",
    }:
        return True
    return False


def resolve_analytics_question(
    text: str,
    selection_context: dict[str, Any] | None,
    chat_history: list[dict[str, Any]] | None,
    conversation_memory: dict[str, Any] | None,
) -> str:
    normalized = text.strip().lower()
    destination_name = resolve_followup_destination(chat_history, conversation_memory)
    vessel_name = (selection_context or {}).get("name") or (
        (conversation_memory or {}).get("active_vessel") or {}
    ).get("name")

    if normalized in {"when", "when?"} and destination_name:
        return f"When was this ship at {destination_name}?"
    if normalized in {"how many", "how many times?"} and destination_name:
        return f"How many times has this ship been to {destination_name}?"
    if normalized in {
        "what about that?",
        "what about the previous one?",
        "what about the last one?",
        "show that again",
    }:
        previous_question = (conversation_memory or {}).get("last_analytics_question")
        if previous_question:
            return previous_question
    if normalized in {"what was the max?", "what was the maximum?"}:
        if vessel_name:
            return f"What was the maximum speed for {vessel_name}?"
        return "What was the maximum speed for this ship?"
    return text


def serialize_position(position: dict[str, Any]) -> dict[str, Any]:
    serialized = position.copy()
    if hasattr(serialized.get("timestamp"), "isoformat"):
        serialized["timestamp"] = serialized["timestamp"].isoformat()
    return serialized
