from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any


_LOCK = Lock()
_ADDED: dict[str, dict[str, Any]] = {}
_UPDATED: dict[str, dict[str, Any]] = {}
_DELETED: set[str] = set()


def compose_rows(mmsi: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with _LOCK:
        composed: list[dict[str, Any]] = []
        for row in rows:
            position_id = row["position_id"]
            if position_id in _DELETED:
                continue
            if position_id in _UPDATED:
                composed.append(deepcopy(_UPDATED[position_id]))
            else:
                composed.append(deepcopy(row))

        for added_row in _ADDED.values():
            if added_row["mmsi"] == mmsi and added_row["position_id"] not in _DELETED:
                composed.append(deepcopy(added_row))

    composed.sort(key=lambda row: (row["timestamp"], row["position_id"]))
    return composed


def overlay_position(position_id: str) -> dict[str, Any] | None:
    with _LOCK:
        if position_id in _DELETED:
            return None
        if position_id in _UPDATED:
            return deepcopy(_UPDATED[position_id])
        if position_id in _ADDED:
            return deepcopy(_ADDED[position_id])
    return None


def add_position(row: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        _ADDED[row["position_id"]] = deepcopy(row)
        _DELETED.discard(row["position_id"])
        _UPDATED.pop(row["position_id"], None)
    return deepcopy(row)


def update_position(row: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        if row["position_id"] in _ADDED:
            _ADDED[row["position_id"]] = deepcopy(row)
        else:
            _UPDATED[row["position_id"]] = deepcopy(row)
        _DELETED.discard(row["position_id"])
    return deepcopy(row)


def delete_position(position_id: str) -> None:
    with _LOCK:
        _DELETED.add(position_id)
        _ADDED.pop(position_id, None)
        _UPDATED.pop(position_id, None)
