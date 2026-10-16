"""Caerness MCP server (stdio). Six tools; every call opens and closes its own connection."""
from __future__ import annotations

import contextlib
import os
import sys
import threading

from mcp.server.mcpserver import MCPServer

INSTRUCTIONS = ("Caerness is the user's text role-playing game. When the user says \"resume\", \"play\" or mentions Caerness, "
                "call the resume tool first and follow the game-master rulebook it returns.")


def make_mcp(**kwargs) -> MCPServer:
    """A fresh MCPServer (the HTTP deployment passes auth settings); call register_tools on it."""
    return MCPServer("caerness", instructions=INSTRUCTIONS, **kwargs)


def register_tools(server: MCPServer) -> MCPServer:
    for fn in (resume, scene, lookup, lore, act, advance, note):
        server.tool(structured_output=False)(fn)
    return server


_CALL_LOCK = threading.Lock()  # one campaign writer at a time; also guards the global stdout redirect


FRESH_CHAT_HINT = "A good moment to suggest a fresh chat once this scene ends."


def _call(fn, tool: str) -> dict:
    """Run fn(conn) with stdout redirected to stderr (stdout is the MCP protocol channel)."""
    with _CALL_LOCK, contextlib.redirect_stdout(sys.stderr):
        try:
            from connector import store
            from connector.campaign import connect_campaign

            conn = connect_campaign()
            try:
                result = fn(conn)
                if isinstance(result, dict) and "error" not in result:
                    n = store.bump_calls(conn, tool)
                    long_chat = n >= store.HINT_AFTER_CALLS and n % 10 == 0
                    if long_chat or (tool == "advance" and int(result.get("elapsed_days") or 0) >= 7):
                        result["fresh_chat_hint"] = FRESH_CHAT_HINT
                return result
            finally:
                conn.close()
        except Exception as e:  # tools never raise tracebacks at the model
            return {"error": str(e) or type(e).__name__}


def _snapshot_before_advance() -> None:
    """Throttled backup before time passes. Runs inside _call (stdout already guarded, lock held).

    A snapshot that fails its integrity check stops the advance (the campaign may be damaged);
    any other backup trouble is logged and play continues.
    """
    from connector.backup import SnapshotIntegrityError, pre_advance_snapshot
    from connector.settings import Settings
    from engine.db import database_path

    backup_dir = Settings.from_env().backup_dir
    if backup_dir is None:
        return
    try:
        pre_advance_snapshot(database_path(), backup_dir)
    except SnapshotIntegrityError as e:
        raise RuntimeError(f"the campaign failed its integrity check before advancing; not advancing ({e})") from e
    except Exception as e:  # backups must not stop play
        print(f"pre-advance snapshot failed: {e}", file=sys.stderr)


def resume() -> dict:
    """Caerness game: call first when the user says resume or wants to play; returns the GM rulebook and current scene."""
    from connector.session import resume as _resume
    return _call(_resume, "resume")


def scene() -> dict:
    """Caerness game: current scene (place, people present, news, competence, condition, notes)."""
    from connector.views import compact_scene
    return _call(compact_scene, "scene")


def lookup(query: str) -> dict:
    """Caerness game: what the protagonist knows about a person or place, by name or id."""
    from connector.views import lookup as _lookup
    return _call(lambda c: _lookup(c, query), "lookup")


def lore(query: str) -> dict:
    """Caerness game: World Bible passages on the setting (cultivation stages, institutions, places, customs, history)."""
    from connector.lore import lore as _lore
    return _call(lambda c: _lore(c, query), "lore")


def act(call_id: str, action_type: str, intent: str, target_actor_id: int | None = None,
        target_location_id: int | None = None, interaction_id: int | None = None,
        response_choice: str | None = None, details: dict | None = None) -> dict:
    """Attempt a consequential action; narrate only what returns. Types: observe, speak, investigate, respond, travel, pay, hire, lend, demand, attack, trade, order. details: from/to ('me','business:<id>','outfit:<id>','household:<id>','person:<id>'), amount (token|small|modest|substantial|large|fortune), role, what, with (ids), crew, intent_kind, deal, business, do."""
    from connector.acting import act as _act
    return _call(lambda c: _act(c, call_id, action_type, intent, target_actor_id=target_actor_id,
                                target_location_id=target_location_id, interaction_id=interaction_id,
                                response_choice=response_choice, details=details), "act")


def advance(call_id: str, days: int, purpose: str) -> dict:
    """Let days pass (max 30 per call); stops early at real interruptions."""
    from connector.timeflow import advance as _advance

    def go(conn):
        _snapshot_before_advance()
        return _advance(conn, call_id, days, purpose)
    return _call(go, "advance")


def note(call_id: str, text: str, kind: str = "detail", subject_kind: str = "general", subject_id: int | None = None,
         threads: list[str] | None = None, field: str | None = None) -> dict:
    """Caerness game: record what should last. kind=detail (a fact about an actor/location/general), recap (after a meaningful moment; threads = open threads), rule (a standing rule the player approved; field=retire with its exact text retires it), sheet (protagonist's field), error (an engine or GM mistake)."""
    from connector import store

    request = {"kind": kind, "text": text, "subject_kind": subject_kind, "subject_id": subject_id,
               "threads": threads, "field": field}

    def go(conn):
        return store.run_once(conn, call_id, "note", request,
                              lambda: store.record(conn, kind, text, call_id, subject_kind=subject_kind,
                                                   subject_id=subject_id, threads=threads, field=field))
    return _call(go, "note")


mcp = register_tools(make_mcp())  # the stdio server


def main() -> None:
    from connector.campaign import open_campaign

    with contextlib.redirect_stdout(sys.stderr):
        open_campaign(os.environ.get("CAERNESS_CAMPAIGN", "main"))
    mcp.run()
