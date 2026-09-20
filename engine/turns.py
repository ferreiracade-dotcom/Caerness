from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from typing import Any, Protocol

from .actions import PlayerActionProvider, begin_player_action, finalize_player_action
from .agency import assess_handoff, build_segment_outline, persist_checkpoint
from .competence import process_competence
from .player import build_scene_packet, get_player
from .presence import actors_plausibly_present
from .simulation import advance_connection, current_day


class NarratorProvider(Protocol):
    def narrate(self, envelope: dict[str, Any]) -> str:
        ...


class TemplateNarratorProvider:
    """Offline narrator used for testing boundaries, not literary gameplay."""

    def narrate(self, envelope: dict[str, Any]) -> str:
        result = envelope["action_result"]
        scene = envelope["scene_after"]
        location = scene.get("location", {}).get("name") or "an unknown place"
        lines = [result.get("summary", "The moment passes.")]
        cues = scene.get("attention_cues") or []
        for cue in cues[-2:]:
            if cue.get("cue_type") in {"automatic", "reminder", "warning"}:
                lines.append(str(cue["text"]))
        rumours = scene.get("known_rumours") or []
        if rumours:
            lines.append(f"Unverified word nearby says: {rumours[-1]['text']}")
        lines.append(f"The scene settles at {location}.")
        # Deliberately no 'What do you do?' prompt. The UI input field is the handoff.
        return " ".join(lines)


def build_narration_envelope(
    raw_input: str,
    pre_scene: dict[str, Any],
    action_result: dict[str, Any],
    post_scene: dict[str, Any],
    *,
    agency_handoff: dict[str, Any] | None = None,
    segment_outline: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "raw_player_input": raw_input,
        "action_result": action_result,
        "scene_before": pre_scene,
        "scene_after": post_scene,
        "protagonist_embodiment": post_scene.get("embodiment", {}),
        "professional_context": post_scene.get("professional_context", {}),
        "agency_handoff": agency_handoff or {},
        "segment_outline": segment_outline or [],
        "narration_rules": [
            "The player is the camera focus, not the world's causal center.",
            "Narrate only information available in scene_after plus the explicit resolved player action.",
            "Do not reveal off-screen events merely because the engine simulated them.",
            "Do not make NPCs care about the player unless persisted relationships, goals, events, or direct circumstances justify it.",
            "Do not create permanent state in prose. The database has already decided what changed.",
            "Allow evidence of a world already in motion: arrivals, departures, rumours, business, feuds, consequences, and unrelated agendas.",
            "Do not frame unrelated world events as foreshadowing for the player unless state actually connects them.",
            "Character competence has already handled obvious follow-through. Do not ask the player to repeat routine actions.",
            "Use professional_context to express what the protagonist can professionally infer from accessible evidence; expertise does not grant omniscience.",
            "Keep character professional reading distinct from reports, advisor opinions, and the player's final decision.",
            "The prose may span multiple scenes, transitions, or days when no unresolved agency point exists between them.",
            "Never end with generic prompts such as 'What do you do?', 'What happens next?', or a forced menu of choices.",
            "When a handoff exists, end naturally in the situation itself; the persistent input field signals that the player may act.",
            "Do not manufacture a request or question from an NPC merely to justify returning control.",
            "Keep the protagonist's voice and incidental behavior consistent with protagonist_embodiment.",
            "Treat the player's wording as intent/content/tone unless they explicitly request exact dialogue.",
            "Do not autonomously make major commitments for the protagonist; stop at the agency boundary instead.",
        ],
    }


def _persist_segments(
    conn: sqlite3.Connection,
    turn_id: int,
    outline: list[dict[str, Any]],
    day_started: int,
    day_ended: int,
    scene_packet_id: int,
    handoff: dict[str, Any],
) -> list[int]:
    ids: list[int] = []
    elapsed = max(0, day_ended - day_started)
    cumulative = 0.0
    for i, seg in enumerate(outline):
        start = day_started + int(round(elapsed * cumulative))
        weight = float(seg.get("weight") or 0.0)
        cumulative += weight
        end = day_ended if i == len(outline) - 1 else day_started + int(round(elapsed * min(1.0, cumulative)))
        is_last = i == len(outline) - 1
        cur = conn.execute(
            """INSERT INTO narrative_segments(
                   turn_id,segment_index,day_started,day_ended,segment_kind,outline_json,scene_packet_id,
                   handoff_type,handoff_reason
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                turn_id, i, start, end, str(seg.get("kind") or "scene"), json.dumps(seg, ensure_ascii=False),
                scene_packet_id if is_last else None,
                str(handoff.get("handoff_type") or "none") if is_last else "none",
                str(handoff.get("reason") or "") if is_last else None,
            ),
        )
        ids.append(int(cur.lastrowid))
    return ids


def resolve_turn_state(
    conn: sqlite3.Connection,
    raw_input: str,
    *,
    action_provider: PlayerActionProvider | None = None,
    canon_limit: int = 6,
) -> dict[str, Any]:
    """Resolve authoritative state for one player input.

    A *player input* is not the same as a fictional scene boundary. The resulting narration
    may cover several scenes/time transitions before naturally handing agency back.
    """
    player = get_player(conn)
    if not player:
        raise ValueError("No player is configured. Use player-set first.")
    player_id = int(player["player_actor_id"])
    day_started = current_day(conn)
    pre_scene = build_scene_packet(conn, raw_input, canon_limit=canon_limit)

    proposal, initial_result = begin_player_action(conn, raw_input, provider=action_provider)
    offscreen_event_ids: list[int] = []
    if initial_result.status == "applied" and initial_result.advance_days > 0:
        generated = advance_connection(conn, initial_result.advance_days)
        offscreen_event_ids = [int(r["id"]) for r in generated]

    final_result = finalize_player_action(conn, proposal, initial_result)
    day_ended = current_day(conn)

    # Arrival is a competence trigger, but routine actor-present intentions are also handled
    # when the post-scene packet is built. This remains idempotent through intention status.
    if final_result.status == "applied" and final_result.action_type == "travel":
        refreshed = get_player(conn)
        if refreshed:
            loc = int(refreshed["current_location_id"]) if refreshed["current_location_id"] is not None else None
            present = (
                {aid for aid in actors_plausibly_present(conn, loc, purpose=f"arrival_competence:{player_id}") if aid != player_id}
                if loc is not None else set()
            )
            process_competence(conn, player_id, current_location_id=loc, present_actor_ids=present, trigger="on_arrival")

    post_scene = build_scene_packet(conn, raw_input, canon_limit=canon_limit)
    public_result = asdict(final_result)
    audit_result = {
        "action": public_result,
        "offscreen_event_ids_during_elapsed_time": offscreen_event_ids,
        "elapsed_days": day_ended - day_started,
    }
    handoff_obj = assess_handoff(pre_scene, post_scene, public_result)
    handoff = handoff_obj.as_dict()
    outline = build_segment_outline(public_result, pre_scene, post_scene)
    envelope = build_narration_envelope(
        raw_input, pre_scene, public_result, post_scene,
        agency_handoff=handoff, segment_outline=outline,
    )
    cur = conn.execute(
        """INSERT INTO turns(
               player_actor_id,day_started,day_ended,raw_input,player_action_id,
               pre_scene_packet_id,post_scene_packet_id,result_json,narration_text
           ) VALUES (?,?,?,?,?,?,?,?,NULL)""",
        (
            player_id, day_started, day_ended, raw_input, final_result.action_id,
            pre_scene["scene_packet_id"], post_scene["scene_packet_id"], json.dumps(audit_result),
        ),
    )
    turn_id = int(cur.lastrowid)
    segment_ids = _persist_segments(conn, turn_id, outline, day_started, day_ended, post_scene["scene_packet_id"], handoff)
    checkpoint_id = persist_checkpoint(conn, turn_id, handoff_obj, segment_id=segment_ids[-1] if segment_ids else None)
    return {
        "turn_id": turn_id,
        "day_started": day_started,
        "day_ended": day_ended,
        "elapsed_days": day_ended - day_started,
        "proposal": asdict(proposal),
        "action_result": public_result,
        "scene_packet_id": post_scene["scene_packet_id"],
        "narration_envelope": envelope,
        "agency_handoff": handoff,
        "segment_outline": outline,
        "segment_ids": segment_ids,
        "agency_checkpoint_id": checkpoint_id,
        "audit": audit_result,
    }


def play_turn(
    conn: sqlite3.Connection,
    raw_input: str,
    *,
    action_provider: PlayerActionProvider | None = None,
    narrator: NarratorProvider | None = None,
    canon_limit: int = 6,
) -> dict[str, Any]:
    resolved = resolve_turn_state(conn, raw_input, action_provider=action_provider, canon_limit=canon_limit)
    narration = (narrator or TemplateNarratorProvider()).narrate(resolved["narration_envelope"])
    conn.execute("UPDATE turns SET narration_text=? WHERE id=?", (narration, resolved["turn_id"]))
    # The prose belongs to the whole player-facing section; technical segment boundaries remain invisible.
    if resolved.get("segment_ids"):
        conn.execute("UPDATE narrative_segments SET narration_text=? WHERE id=?", (narration, resolved["segment_ids"][-1]))
    return {**resolved, "narration": narration}


def recent_turns(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT t.*,a.name player_name FROM turns t
           JOIN actors a ON a.id=t.player_actor_id
           ORDER BY t.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    out = []
    for row in reversed(rows):
        item = dict(row)
        try:
            item["result"] = json.loads(item.pop("result_json") or "{}")
        except Exception:
            item["result"] = {}
        out.append(item)
    return out


def export_journal(conn: sqlite3.Connection, path: str) -> str:
    """Export player-facing turn history as Markdown without hidden state."""
    from pathlib import Path

    player = get_player(conn)
    campaign = str(player["campaign_name"]) if player else "Caerness Campaign"
    rows = conn.execute(
        """SELECT t.id,t.day_started,t.day_ended,t.raw_input,t.narration_text,a.name player_name
           FROM turns t JOIN actors a ON a.id=t.player_actor_id ORDER BY t.id"""
    ).fetchall()
    lines = [f"# {campaign}", "", "> Player-facing campaign journal. Hidden simulation state is intentionally excluded.", ""]
    for row in rows:
        lines.extend([
            f"## Turn {row['id']} — Day {row['day_started']} to {row['day_ended']}",
            "",
            f"**{row['player_name']}:** {row['raw_input']}",
            "",
            str(row["narration_text"] or ""),
            "",
        ])
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return str(out)
