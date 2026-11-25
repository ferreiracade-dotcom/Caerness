"""The `correct` tool: the game master's corrections, applied once per call_id."""
from __future__ import annotations

from connector import store
from engine import corrections


def correct(conn, call_id: str, op: str, player_said: str, details: dict | None) -> dict:
    details = dict(details or {})
    op = str(op or "").strip().lower()
    if op == "preview":
        return corrections.preview(conn, details)
    request = {"op": op, "player_said": player_said, "details": details}
    return store.run_once(conn, call_id, "correct", request,
                          lambda: corrections.apply(conn, op, player_said, details, call_id))
