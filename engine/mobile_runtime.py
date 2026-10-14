from __future__ import annotations

import json
import sqlite3
from typing import Any

from .actions import HeuristicPlayerActionProvider
from .agency import consume_interrupt
from .db import backup_db
from .discovery import player_information_hub
from .competence import pending_attention
from .local_model import local_health, runtime_config
from .model_gateway import (
    apply_model_request,
    bridge_play,
    create_action_request,
    export_request,
    request_row,
    run_request_local,
)
from .player import build_scene_packet, get_player
from .router import assess_model_task
from .simulation import current_day
from .turns import play_turn, recent_turns


def _packet_text(path: str) -> str:
    from pathlib import Path
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


def referral_for_request(conn: sqlite3.Connection, request_id: int, assessment: dict[str, Any], *, reason: str = "") -> dict[str, Any]:
    chatgpt = export_request(conn, request_id, provider="chatgpt")
    claude = export_request(conn, request_id, provider="claude")
    return {
        "status": "external_recommended",
        "request_id": request_id,
        "assessment": assessment,
        "reason": reason,
        "chatgpt": {"path": chatgpt, "packet": _packet_text(chatgpt)},
        "claude": {"path": claude, "packet": _packet_text(claude)},
        "local_force_available": True,
    }


def _finish_local_request(conn: sqlite3.Connection, request_id: int, *, force_local: bool) -> dict[str, Any]:
    try:
        result = run_request_local(conn, request_id, force=force_local, apply=True)
    except Exception as exc:
        row = request_row(conn, request_id)
        assessment = assess_model_task(conn, row["task_type"], row.get("input") or json.loads(row["input_json"]), target_kind=row.get("target_kind"), target_id=row.get("target_id")).as_dict()
        return referral_for_request(conn, request_id, assessment, reason=f"Local model unavailable or failed: {exc}")
    if result.get("status") == "external_recommended":
        return referral_for_request(conn, request_id, result["assessment"], reason=result.get("message", ""))
    return result


def process_player_input(
    conn: sqlite3.Connection,
    text: str,
    *,
    mode: str = "auto",
    force_local: bool = False,
    session_id: int | None = None,
    plan_id: int | None = None,
) -> dict[str, Any]:
    """Phone-first orchestration for one player input.

    Modes:
    - auto: rules for routine resolution, local model when useful, external referral when worthwhile.
    - local: prefer local and only refer on failure unless force_local=False and router strongly recommends external.
    - rules: deterministic/template fallback.
    - chatgpt / claude: create manual bridge packets.
    """
    text = text.strip()
    if not text:
        raise ValueError("Player input may not be empty.")
    if mode == "narrative":
        from .narrative_runtime import play
        return play(conn,text,session_id,plan_id)
    if mode in {"planner", "plan_chatgpt", "plan_claude"}:
        from .planning_gateway import play
        return play(conn, text, session_id, plan_id, provider={"planner":"local", "plan_chatgpt":"chatgpt", "plan_claude":"claude"}[mode],force_local=force_local)
    if consume_interrupt(conn):
        # A previous interrupt request is considered consumed at the next safe player-input boundary.
        pass
    if mode == "rules":
        result = play_turn(conn, text)
        return {"status": "complete", "source": "rules", "turn": result, "narration": result["narration"]}
    if mode in {"chatgpt", "claude"}:
        return bridge_play(conn, text, mode)

    if mode not in {"auto", "local"}:
        raise ValueError("mode must be auto, local, rules, chatgpt, or claude")

    heuristic = HeuristicPlayerActionProvider().propose(conn, text)
    if heuristic.needs_interpretation:
        areq = create_action_request(conn, text, "local")
        assessment = assess_model_task(
            conn, "action_interpretation", json.loads(conn.execute("SELECT input_json FROM model_requests WHERE id=?", (areq["request_id"],)).fetchone()[0]),
            target_kind="scene_packet", target_id=areq.get("target_id"),
        ).as_dict()
        if not force_local and assessment["recommendation"] in {"external_recommended", "external_strongly_recommended"}:
            return referral_for_request(conn, areq["request_id"], assessment)
        action_run = _finish_local_request(conn, areq["request_id"], force_local=force_local)
        if action_run.get("status") == "external_recommended":
            return action_run
        applied = action_run.get("applied") or {}
        nreq = applied.get("next_request")
        if not nreq:
            return {"status": "complete", "source": "local", "result": action_run}
    else:
        bridge = bridge_play(conn, text, "local")
        nreq = bridge.get("next_request")
        if not nreq:
            return bridge

    if consume_interrupt(conn):
        return {"status": "interrupted", "message": "Automatic progression stopped at the latest safe boundary.", "next_request": nreq}

    narration_id = int(nreq["request_id"])
    nrow = request_row(conn, narration_id)
    npayload = nrow.get("input") or json.loads(nrow["input_json"])
    nassessment = assess_model_task(
        conn, "narration", npayload, target_kind=nrow.get("target_kind"), target_id=nrow.get("target_id")
    ).as_dict()
    if not force_local and nassessment["recommendation"] in {"external_recommended", "external_strongly_recommended"}:
        return referral_for_request(conn, narration_id, nassessment)

    narr_run = _finish_local_request(conn, narration_id, force_local=force_local)
    if narr_run.get("status") == "external_recommended":
        return narr_run
    applied = narr_run.get("applied") or {}
    turn_id = applied.get("turn_id")
    turn = None
    if turn_id is not None:
        row = conn.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone()
        turn = dict(row) if row else None
    return {
        "status": "complete",
        "source": "local",
        "turn_id": turn_id,
        "turn": turn,
        "narration": applied.get("narration", ""),
        "assessment": nassessment,
    }


def mobile_state(conn: sqlite3.Connection) -> dict[str, Any]:
    player = get_player(conn)
    turns = recent_turns(conn, 30) if player else []
    hub = player_information_hub(conn) if player else {"player": None, "attention": [], "matters": {}, "people": [], "places": [], "claims": []}
    if player:
        from .player_appointments import known_appointments
        hub.setdefault("matters", {})["appointments"] = known_appointments(conn, int(player["player_actor_id"]))
        # Mobile popups are contextual attention, not a permanent quest HUD. Return them once
        # and mark them shown; the underlying Matter/Intention remains available in reference screens.
        hub["attention"] = pending_attention(conn, int(player["player_actor_id"]), mark_shown=True, limit=12)
    latest_handoff = None
    if turns:
        row = conn.execute(
            """SELECT ac.* FROM agency_checkpoints ac WHERE ac.turn_id=? ORDER BY ac.id DESC LIMIT 1""",
            (turns[-1]["id"],),
        ).fetchone()
        latest_handoff = dict(row) if row else None
    cfg = runtime_config(conn)
    from .ai_planning import available, plan_view
    planning = []
    sessions = []
    if player and available(conn):
        planning = [plan_view(conn,int(r[0])) for r in conn.execute("SELECT id FROM ai_plans WHERE owner_actor_id=? ORDER BY id DESC LIMIT 20",(player["player_actor_id"],))]
        sessions = [{"id":r["id"],"messages":json.loads(r["messages_json"])} for r in conn.execute("SELECT id,messages_json FROM ai_sessions WHERE owner_actor_id=? ORDER BY id DESC LIMIT 5",(player["player_actor_id"],))]
    return {
        "world": {"day": current_day(conn), "name": "Caerness"},
        "player": hub.get("player"),
        "turns": turns,
        "attention": hub.get("attention", []),
        "matters": hub.get("matters", {}),
        "scope_reviews": [json.loads(r[0]) for r in conn.execute("SELECT result_json FROM player_actions WHERE player_actor_id=? AND status='proposed' AND result_json IS NOT NULL", (int(player["player_actor_id"]),)).fetchall()] if player else [],
        "plans": planning,
        "conversations": sessions,
        "people": hub.get("people", []),
        "places": hub.get("places", []),
        "claims": hub.get("claims", []),
        "agency_handoff": latest_handoff,
        "runtime": {
            "ai_provider":cfg.get('ai_provider','custom'),
            "local_heavy_context_tokens":cfg['local_heavy_context_tokens'],
            "local_max_output_tokens":cfg['local_max_output_tokens'],
            "device_profile": cfg["device_profile"],
            "local_model": cfg["local_model"],
            "local_backend": cfg["local_backend"],
            "model_endpoint": cfg["local_endpoint"],
            "remote_model": cfg.get("remote_model",False),
            "credential_available": cfg.get("credential_available",False),
            "referral_sensitivity": cfg["referral_sensitivity"],
            "story_time_only": not bool(cfg["realtime_calendar_progression"]),
        },
    }


def maybe_auto_backup(conn: sqlite3.Connection) -> str | None:
    cfg = runtime_config(conn)
    every = int(cfg["auto_backup_every_turns"])
    if every <= 0:
        return None
    count = int(conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0])
    if count <= 0 or count % every != 0:
        return None
    # Caller should commit before invoking; backup_db opens a separate consistent connection.
    return backup_db("auto")
