"""Caerness MCP server (stdio). Six tools; every call opens and closes its own connection."""
from __future__ import annotations

import contextlib
import os
import sys

from mcp.server.mcpserver import MCPServer

mcp = MCPServer(
    "caerness",
    instructions="Caerness game connector. At the start of a Caerness chat call resume and follow the rulebook it returns.",
)


def _call(fn) -> dict:
    """Run fn(conn) with stdout redirected to stderr (stdout is the MCP protocol channel)."""
    with contextlib.redirect_stdout(sys.stderr):
        try:
            from connector.campaign import connect_campaign

            conn = connect_campaign()
            try:
                return fn(conn)
            finally:
                conn.close()
        except Exception as e:  # tools never raise tracebacks at the model
            return {"error": str(e) or type(e).__name__}


@mcp.tool(structured_output=False)
def resume() -> dict:
    """Start of every chat: returns the GM rulebook, how to play, and the current scene."""
    from connector.session import resume as _resume
    return _call(_resume)


@mcp.tool(structured_output=False)
def scene() -> dict:
    """Current scene: place, people present, news, competence, condition, notes."""
    from connector.views import compact_scene
    return _call(compact_scene)


@mcp.tool(structured_output=False)
def lookup(query: str) -> dict:
    """What the protagonist knows about a person or place, by name or id."""
    from connector.views import lookup as _lookup
    return _call(lambda c: _lookup(c, query))


@mcp.tool(structured_output=False)
def act(call_id: str, action_type: str, intent: str, target_actor_id: int | None = None,
        target_location_id: int | None = None, interaction_id: int | None = None,
        response_choice: str | None = None) -> dict:
    """Attempt a consequential action (observe, speak, investigate, respond, travel); narrate only what returns."""
    from connector.acting import act as _act
    return _call(lambda c: _act(c, call_id, action_type, intent, target_actor_id=target_actor_id,
                                target_location_id=target_location_id, interaction_id=interaction_id,
                                response_choice=response_choice))


@mcp.tool(structured_output=False)
def advance(call_id: str, days: int, purpose: str) -> dict:
    """Let days pass (max 30 per call); stops early at real interruptions."""
    from connector.timeflow import advance as _advance
    return _call(lambda c: _advance(c, call_id, days, purpose))


@mcp.tool(structured_output=False)
def note(call_id: str, subject_kind: str, subject_id: int | None, text: str) -> dict:
    """Record a lasting improvised detail about an actor, location or general."""
    from connector import store

    def go(conn):
        return store.run_once(conn, call_id, "note",
                              {"subject_kind": subject_kind, "subject_id": subject_id, "text": text},
                              lambda: store.add_note(conn, subject_kind, subject_id, text, call_id))
    return _call(go)


def main() -> None:
    from connector.campaign import open_campaign

    with contextlib.redirect_stdout(sys.stderr):
        open_campaign(os.environ.get("CAERNESS_CAMPAIGN", "main"))
    mcp.run()
