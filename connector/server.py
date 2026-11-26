"""Narrative Engine MCP server (stdio). A few tools; every call opens and closes its own connection."""
from __future__ import annotations

import contextlib
import os
import sys
import threading

from mcp.server.mcpserver import MCPServer

INSTRUCTIONS_TEMPLATE = ("{name} is the user's text role-playing game. When the user says \"resume\" or \"play\", "
                         "call the resume tool with no arguments first: it loads the only save, or lists the playable worlds and their saves. When it lists "
                         "them, ask the player which world and which save (or a new one); never choose for them. Then call resume with world and "
                         "save (new_save=true for a new save) and follow the game-master rulebook it returns.")


INSTRUCTIONS = INSTRUCTIONS_TEMPLATE.format(name="Narrative Engine")


def make_mcp(**kwargs) -> MCPServer:
    """A fresh MCPServer (the HTTP deployment passes auth settings); call register_tools on it."""
    from connector import apps_probe
    if apps_probe.enabled():  # opt-in test card; the game tools are unchanged
        kwargs.setdefault("extensions", [apps_probe.make_apps()])
    return MCPServer("narrative-engine", instructions=INSTRUCTIONS, **kwargs)


def register_tools(server: MCPServer) -> MCPServer:
    for fn in (resume, scene, lookup, lore, act, advance, note, author, money, correct):
        server.tool(structured_output=False)(fn)
    return server


_CALL_LOCK = threading.Lock()  # one campaign writer at a time; also guards the global stdout redirect


FRESH_CHAT_HINT = "A good moment to suggest a fresh chat once this scene ends."


def _call(fn, tool: str, before=None) -> dict:
    """Run fn(conn) with stdout redirected to stderr (stdout is the MCP protocol channel).

    `before`, when given, runs inside the lock first (a campaign switch); if it raises nothing else runs.
    """
    with _CALL_LOCK, contextlib.redirect_stdout(sys.stderr):
        try:
            if before is not None:
                before()
            from connector import store
            from connector.campaign import connect_campaign

            conn = connect_campaign()
            try:
                result = fn(conn)
                if isinstance(result, dict) and "error" not in result:
                    n = store.bump_calls(conn, tool)
                    if tool == "note" and result.get("saved") == "recap" and n >= store.HINT_AFTER_CALLS:  # between scenes only
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


def resume_current() -> dict:
    """Continue whichever campaign is open now: the rulebook and scene (a new campaign gets the creation text). Not a tool."""
    from connector.session import resume as _resume
    from connector.session import world_info

    def go(conn):
        out = _resume(conn)
        return out if "error" in out else {**out, **world_info(conn)}

    return _call(go, "resume")


def resume(world: str | None = None, save: str | None = None, new_save: bool = False) -> dict:
    """Narrative Engine game: call first. No arguments loads the only save, else lists worlds and their saves: ask the player which, then call again with world and save. new_save=true starts a new save. Returns the GM rulebook and scene."""
    from connector import campaign

    def pick():
        with _CALL_LOCK, contextlib.redirect_stdout(sys.stderr):
            try:
                if world is None or not str(world).strip():
                    kept = [(x["world"], s["save"]) for x in campaign.worlds_and_saves() for s in x["saves"]]
                    if len(kept) == 1 and not new_save:  # one save only: there is nothing to choose
                        campaign.switch_to(*kept[0])
                        return None
                    return {"ask": "Ask the player which world to play and, if that world has several saves, which save (or whether to start a new one). "
                                   "Then call resume again with world and save (new_save=true starts a new save). Do not pick for them and do not play yet.",
                            "worlds": campaign.worlds_and_saves()}
                w = _resolve_world(str(world))
                if w not in {x["world"] for x in campaign.worlds_and_saves()}:
                    return {"error": f"unknown world '{world}'; playable: {', '.join(x['name'] for x in campaign.worlds_and_saves()) or 'none'}"}
                saves = campaign.list_saves(w)
                wanted = str(save).strip() if save is not None and str(save).strip() else None
                if not new_save and wanted is None and len(saves) > 1:
                    return {"ask": "This world has several saves: ask the player which one (or whether to start a new one), then call resume with world and save.",
                            "world": w, "saves": saves}
                campaign.switch_to(w, wanted, new=bool(new_save))
            except Exception as e:
                return {"error": str(e) or type(e).__name__}
        return None

    early = pick()
    return early if early is not None else resume_current()


def _resolve_world(text: str) -> str:
    """A world given by id or by display name (any case) -> its package id; anything else is passed on to fail in switch_to."""
    from connector.campaign import list_worlds
    t = text.strip().lower()
    for w in list_worlds():
        if t in (w["world"].lower(), w["display_name"].lower()):
            return w["world"]
    return text.strip()


def scene() -> dict:
    """Narrative Engine game: current scene (place, people present, news, competence, condition, notes)."""
    from connector.views import compact_scene
    return _call(compact_scene, "scene")


def lookup(query: str, offset: int = 0) -> dict:
    """Narrative Engine game: what the protagonist knows of a person, place, business, outfit, household, crew, institution or role, by name or id. known_more/notes_more say older entries exist; raise offset to read them."""
    from connector.views import lookup as _lookup
    return _call(lambda c: _lookup(c, query, offset), "lookup")


def lore(query: str) -> dict:
    """Narrative Engine game: World Bible passages on the setting (institutions, places, customs, history, the world's own rules)."""
    from connector.lore import lore as _lore
    return _call(lambda c: _lore(c, query), "lore")


def act(call_id: str, action_type: str, intent: str, target_actor_id: int | None = None,
        target_location_id: int | None = None, interaction_id: int | None = None,
        response_choice: str | None = None, details: dict | None = None) -> dict:
    """Do anything with consequences; narrate only what returns (partial results and counter-terms included). action_type "operation" takes any intent in intent, with details: actors, resources {money (number, word or share), men, wage, from}, targets (ids like actor:3, outfit:2, or names), conditions, time (days or "a month"), kind (optional hint). Shortcuts: observe, speak (tells, asks), investigate (subject, business, outfit; duration_days), respond (changes), travel, pay, hire (count, wage), lend, demand, attack, trade, order, outing (night out; then target, details.move talk|dance|number|leave together), answer (details.matter from waiting_on_you, details.answer yes|no|settled, details.how). Holders: me, business:/outfit:/household:/institution:/polity:<id>. A refusal has reason_kind: input_gap means rephrase and retry."""
    from connector.acting import act as _act
    return _call(lambda c: _act(c, call_id, action_type, intent, target_actor_id=target_actor_id,
                                target_location_id=target_location_id, interaction_id=interaction_id,
                                response_choice=response_choice, details=details), "act")


def advance(call_id: str, days: int, purpose: str, domain: str | None = None, delegate: dict | None = None,
            interrupt: str | None = None, from_day: int | None = None, undo: bool = False, confirm: bool = False) -> dict:
    """Let days pass (max 30 per call); stops early at real interruptions. from_day (required): the scene's current day, so no skip runs twice. purpose is kept and practised (domain optional); delegate {to, obligations, interaction_types, everything_routine} minds matters; interrupt: something (stops at the first thing worth playing; for "skip until something happens") | all|meaningful|critical_only. material = what reached them and by whom. undo=true shows what taking back the last skip loses; with confirm=true does it."""
    from connector.timeflow import advance as _advance

    def go(conn):
        if undo:
            from connector import undo as points
            from engine.db import database_path
            return points.undo(conn, database_path(), call_id, confirm)
        if from_day is None:
            from connector.store import _day
            return {"error": f"from_day is required: the current day on the scene (now {_day(conn)}), so that a skip is never applied twice."}
        _snapshot_before_advance()
        return _advance(conn, call_id, days, purpose, domain=domain, delegate=delegate, interrupt=interrupt, from_day=from_day)
    return _call(go, "advance")


def note(call_id: str, text: str, kind: str = "detail", subject_kind: str = "general", subject_id: int | None = None,
         threads: list[str] | None = None, field: str | None = None, cause: str | None = None, present: list | None = None) -> dict:
    """Narrative Engine game: record what should last. kind=detail (a fact about an actor/location/business/outfit/household/crew/institution/general), recap (after a meaningful moment; threads = open threads), scene (before telling a scene: where it stands and the last words; present = who is there, ids or names), rule (a lasting rule the player stated; field=retire with its exact text retires it), sheet (protagonist's field), error (an engine or GM mistake; field=settled with a `corrections` entry's text or id closes it), want (field matters|drop|met, subject_id; or text = a wish), chance (field taken|refused, subject_id), fact (change a tagged world fact: field = its key or name from lookup, text = new value; a Fixed fact needs `cause`, the event that changed it)."""
    from connector import store

    request = {"kind": kind, "text": text, "subject_kind": subject_kind, "subject_id": subject_id,
               "threads": threads, "field": field, **({"cause": cause} if cause else {}), **({"present": present} if present else {})}

    def go(conn):
        return store.run_once(conn, call_id, "note", request,
                              lambda: store.record(conn, kind, text, call_id, subject_kind=subject_kind,
                                                   subject_id=subject_id, threads=threads, field=field, cause=cause, present=present))
    return _call(go, "note")


def author(call_id: str, kind: str, details: dict | None = None) -> dict:
    """Narrative Engine game: make something new real. kind is free text: anything lasting the world has no mechanism for is still held (owners, money {start, income, upkeep, from}, agenda, place, dates, legality, knows, consequences) and flagged for deeper build; person (age, work, name, stage, ties as {actor_id, as: relation in words}, wants, from_elsewhere; sex optional; holds = an Open office taken, once only), business (name, trade, amount), organisation (name, type, members), rumour (text, spread) protagonist (a whole proposal when the campaign has none; see the creation text) and entry (details date; accept=true runs up to a year toward it) keep their fields. The engine only vetoes contradictions, scales down what the place cannot supply (scaled_down) and fills the rest; a refusal names the clash and has a reason_kind."""
    from connector.authoring import author as _author
    return _call(lambda c: _author(c, call_id, kind, details), "author")


def money(call_id: str, op: str, details: dict | None = None) -> dict:
    """Narrative Engine game: money in the world's currency; people are an id, "me" or a name. op and details: set_cash {holder, amount, reason}; deal {customer, job, quote, deposit, parts, due_in_days, referrer, collateral, provider, status quoted}; owe {debtor, creditor, amount, what, due_in_days}; pay {deal_id, amount} or {to, amount, what, from}; collateral {deal_id, what, status held|returned|kept}; close {deal_id, status declined|written_off|void, reason}; wage {worker, business, weekly}; share {to, share, applies all|referred|tag:x, basis profit|gross, from}; show. Others pay what falls due from what they have; his own debts he pays."""
    from connector.money import money as _money
    return _call(lambda c: _money(c, call_id, op, details), "money")


def correct(call_id: str, op: str, player_said: str = "", details: dict | None = None) -> dict:
    """Narrative Engine game: fix a wrong record, only on the player's explicit yes (player_said quotes it). People: id, "me" or name. op {details}: preview {as undo_event}; undo_event {actors, day | event_id | life_event_id | interaction_id; reverse [{table, id|where, action delete|set, values}] for untraced effects}; person {person, work, business, role, location, home, age, birth_day, sex}; relationship {from, to, values {trust..}, both}; kinship {a, b, change add|end|remove, kind: what a is to b}; household {person, household, change join|leave}; cash {holder, amount}; any takes cause (needed against a Fixed canon fact)."""
    from connector.correct import correct as _correct
    return _call(lambda c: _correct(c, call_id, op, player_said, details), "correct")


mcp = register_tools(make_mcp())  # the stdio server


def main() -> None:
    from connector.campaign import open_startup

    with contextlib.redirect_stdout(sys.stderr):
        open_startup(os.environ.get("CAERNESS_CAMPAIGN", "main"))
    mcp.run()
