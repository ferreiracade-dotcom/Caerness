"""Narrative Engine MCP server (stdio). Six tools; every call opens and closes its own connection."""
from __future__ import annotations

import contextlib
import os
import sys
import threading

from mcp.server.mcpserver import MCPServer

INSTRUCTIONS_TEMPLATE = ("{name} is the user's text role-playing game. When the user says \"resume\", \"play\" or mentions {name}, "
                         "call the resume tool first and follow the game-master rulebook it returns.")


def _display_name() -> str:
    from engine.world_package import configured_package_id, load_package
    try:
        return load_package(configured_package_id()).display_name
    except Exception:  # an unreadable package must not stop the server from starting
        return "Caerness"


INSTRUCTIONS = INSTRUCTIONS_TEMPLATE.format(name="Caerness")


def make_mcp(**kwargs) -> MCPServer:
    """A fresh MCPServer (the HTTP deployment passes auth settings); call register_tools on it."""
    return MCPServer("narrative-engine", instructions=INSTRUCTIONS_TEMPLATE.format(name=_display_name()), **kwargs)


def register_tools(server: MCPServer) -> MCPServer:
    name = _display_name()
    for fn in (resume, scene, lookup, lore, act, advance, note, author):
        if name != "Caerness" and (fn.__doc__ or "").startswith("Caerness game:"):
            fn.__doc__ = f"{name} game:" + fn.__doc__[len("Caerness game:"):]
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


def lookup(query: str, offset: int = 0) -> dict:
    """Caerness game: what the protagonist knows of a person, place, business, outfit, household, crew, institution or role, by name or id. known_more/notes_more say older entries exist; raise offset to read them."""
    from connector.views import lookup as _lookup
    return _call(lambda c: _lookup(c, query, offset), "lookup")


def lore(query: str) -> dict:
    """Caerness game: World Bible passages on the setting (cultivation stages, institutions, places, customs, history)."""
    from connector.lore import lore as _lore
    return _call(lambda c: _lore(c, query), "lore")


def act(call_id: str, action_type: str, intent: str, target_actor_id: int | None = None,
        target_location_id: int | None = None, interaction_id: int | None = None,
        response_choice: str | None = None, details: dict | None = None) -> dict:
    """Do anything with consequences; narrate only what returns (partial results and counter-terms included). action_type "operation" takes any intent in intent, with details: actors, resources {money (number, word or share), men, wage, from}, targets (ids like actor:3, outfit:2, or names), conditions, time (days or "a month"), kind (optional hint). Shortcuts: observe, speak (tells, asks), investigate (subject, business, outfit; duration_days), respond (changes), travel, pay, hire (count, wage), lend, demand, attack, trade, order. Holders: me, business:/outfit:/household:/institution:/polity:<id>. A refusal has reason_kind: input_gap means rephrase and retry."""
    from connector.acting import act as _act
    return _call(lambda c: _act(c, call_id, action_type, intent, target_actor_id=target_actor_id,
                                target_location_id=target_location_id, interaction_id=interaction_id,
                                response_choice=response_choice, details=details), "act")


def advance(call_id: str, days: int, purpose: str, domain: str | None = None, delegate: dict | None = None,
            interrupt: str | None = None) -> dict:
    """Let days pass (max 30 per call); stops early at real interruptions. purpose is kept and practised (domain optional); delegate {to, obligations, interaction_types, everything_routine} names who minds matters meanwhile; interrupt: all|meaningful|critical_only."""
    from connector.timeflow import advance as _advance

    def go(conn):
        _snapshot_before_advance()
        return _advance(conn, call_id, days, purpose, domain=domain, delegate=delegate, interrupt=interrupt)
    return _call(go, "advance")


def note(call_id: str, text: str, kind: str = "detail", subject_kind: str = "general", subject_id: int | None = None,
         threads: list[str] | None = None, field: str | None = None, cause: str | None = None) -> dict:
    """Caerness game: record what should last. kind=detail (a fact about an actor/location/business/outfit/household/crew/institution/general), recap (after a meaningful moment; threads = open threads), rule (a standing rule the player approved; field=retire with its exact text retires it), sheet (protagonist's field), error (an engine or GM mistake; field=fixed with a `corrections` entry's text or id marks it done), fact (change a tagged world fact: field = its key or name from lookup, text = new value; a Fixed fact needs `cause`, the event that changed it)."""
    from connector import store

    request = {"kind": kind, "text": text, "subject_kind": subject_kind, "subject_id": subject_id,
               "threads": threads, "field": field, **({"cause": cause} if cause else {})}

    def go(conn):
        return store.run_once(conn, call_id, "note", request,
                              lambda: store.record(conn, kind, text, call_id, subject_kind=subject_kind,
                                                   subject_id=subject_id, threads=threads, field=field, cause=cause))
    return _call(go, "note")


def author(call_id: str, kind: str, details: dict | None = None) -> dict:
    """Caerness game: make something new real. kind is free text: person (age, work, name, stage, ties as {actor_id, as: relation in words}, wants, from_elsewhere; sex optional; holds = an Open office taken, once only), business (name, trade, amount), organisation (name, type, members), rumour (text, spread), or protagonist (a whole proposal when the campaign has none; see the creation text). The engine only vetoes contradictions, scales down what the place cannot supply (scaled_down) and fills the rest; a refusal names the clash and has a reason_kind."""
    from connector.authoring import author as _author
    return _call(lambda c: _author(c, call_id, kind, details), "author")


mcp = register_tools(make_mcp())  # the stdio server


def main() -> None:
    from connector.campaign import open_campaign

    with contextlib.redirect_stdout(sys.stderr):
        open_campaign(os.environ.get("CAERNESS_CAMPAIGN", "main"))
    mcp.run()
