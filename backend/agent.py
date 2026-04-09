from __future__ import annotations

import re
from typing import Any

from backend.data.loader import get_ship_detail
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
) -> dict[str, Any]:
    text = transcript.strip()
    if not text:
        return {"reply": "I did not catch that.", "action": None, "payload": None}

    normalized = text.lower()
    subject_mmsi = resolve_subject_mmsi(text, selection_context)

    if is_identity_query(normalized):
        if subject_mmsi is None:
            return clarify_missing_subject()

        detail = get_ship_detail(subject_mmsi)
        if detail is None:
            return not_found_reply(subject_mmsi)

        identity = get_ship_identity(subject_mmsi)
        last_position = detail["last_position"]
        reply = (
            f"{identity['name'] or 'The selected vessel'} is MMSI {subject_mmsi}, "
            f"flagged {identity['flag'] or 'unknown'}, currently making {last_position['sog']} knots."
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

        return {
            "reply": "Showing the last 24 hours for the selected vessel.",
            "action": "SHOW_TRACK",
            "payload": {"mmsi": subject_mmsi, "history": history},
        }

    if is_destination_query(normalized):
        if subject_mmsi is None:
            return clarify_missing_subject()

        destinations = get_recent_destinations_tool(subject_mmsi, 5)
        if not destinations:
            return not_found_reply(subject_mmsi)

        latest_names = ", ".join(entry["destination"] for entry in destinations[:3])
        return {
            "reply": f"Showing the last destinations for this vessel. Recent ports include {latest_names}.",
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
        return {
            "reply": "Added the new position to the overlay store.",
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
        if candidate is None:
            return {
                "reply": "I did not find any duplicate positions to merge for the selected vessel.",
                "action": None,
                "payload": None,
            }

        result = merge_positions(
            candidate[0]["position_id"], candidate[1]["position_id"]
        )
        if result and result.get("conflict_type"):
            return {
                "reply": "These positions conflict on timestamp within 30 seconds of each other. Most recent wins by default.",
                "action": "SHOW_CONFLICT",
                "payload": result | {"mmsi": subject_mmsi},
            }

        return {
            "reply": "Merged the duplicate positions and refreshed the track.",
            "action": "SHOW_TRACK",
            "payload": {
                "mmsi": subject_mmsi,
                "history": get_position_history(subject_mmsi, 24),
            },
        }

    if is_edit_query(normalized):
        return {
            "reply": "Which position should I edit? Select a vessel first, then provide the position identifier or updated coordinates.",
            "action": None,
            "payload": None,
        }

    if is_delete_query(normalized):
        return {
            "reply": "Which position should I delete from this track? I need a specific position identifier before I proceed.",
            "action": None,
            "payload": None,
        }

    return {
        "reply": "I can identify a vessel, show its 24 hour track, list destinations, or help with a merge conflict.",
        "action": None,
        "payload": {"chat_history_count": len((chat_history or [])[-6:])},
    }


def resolve_subject_mmsi(
    text: str, selection_context: dict[str, Any] | None
) -> int | None:
    explicit = re.search(r"\b(\d{9})\b", text)
    if explicit:
        return int(explicit.group(1))
    if selection_context and selection_context.get("mmsi"):
        return int(selection_context["mmsi"])
    return None


def extract_coordinates(text: str) -> tuple[float, float] | None:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(numbers) < 2:
        return None
    lat, lon = float(numbers[0]), float(numbers[1])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def clarify_missing_subject() -> dict[str, Any]:
    return {
        "reply": "Which vessel should I use? Select one on the map or say the MMSI.",
        "action": None,
        "payload": None,
    }


def not_found_reply(mmsi: int) -> dict[str, Any]:
    return {
        "reply": f"I could not find vessel {mmsi}. Select another ship or verify the MMSI.",
        "action": None,
        "payload": None,
    }


def is_identity_query(text: str) -> bool:
    return (
        "what is this vessel" in text
        or "show me this ship" in text
        or "what is this ship" in text
    )


def is_track_query(text: str) -> bool:
    return "last 24 hours" in text or "24 hour" in text or "24h" in text


def is_destination_query(text: str) -> bool:
    return "destination" in text


def is_add_query(text: str) -> bool:
    return text.startswith("add a position") or "add position" in text


def is_merge_query(text: str) -> bool:
    return "merge" in text and "track" in text


def is_edit_query(text: str) -> bool:
    return text.startswith("edit")


def is_delete_query(text: str) -> bool:
    return text.startswith("delete")


def serialize_position(position: dict[str, Any]) -> dict[str, Any]:
    serialized = position.copy()
    if hasattr(serialized.get("timestamp"), "isoformat"):
        serialized["timestamp"] = serialized["timestamp"].isoformat()
    return serialized
