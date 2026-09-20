from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .actions import HeuristicPlayerActionProvider, PlayerActionProposal, shortest_route
from .decisions import DecisionProposal, apply_decision, build_actor_context, candidate_to_proposal
from .decision_runtime import generate_candidates, record_external_selection
from .player import build_scene_packet, get_player, sync_player_location
from .presence import actor_is_present_candidate
from .simulation import advance_connection, current_day
from .local_model import chat_local, runtime_config
from .router import assess_model_task
from .turns import build_narration_envelope, resolve_turn_state

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKET_DIR = ROOT / "game" / "campaign_01" / "model_requests"
PROVIDERS = {"chatgpt", "claude", "generic", "local"}


class FixedActionProvider:
    def __init__(self, proposal: PlayerActionProposal):
        self.proposal = proposal

    def propose(self, conn: sqlite3.Connection, raw_text: str) -> PlayerActionProposal:
        return self.proposal


def _provider_label(provider: str) -> str:
    return {"chatgpt": "ChatGPT", "claude": "Claude", "generic": "LLM", "local": "Local model"}[provider]


def _config(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM model_config WHERE id=1").fetchone()
    if not row:
        conn.execute("INSERT INTO model_config(id) VALUES (1)")
        row = conn.execute("SELECT * FROM model_config WHERE id=1").fetchone()
    return dict(row)


def model_status(conn: sqlite3.Connection) -> dict[str, Any]:
    cfg = _config(conn)
    counts = {
        row["status"]: int(row["n"])
        for row in conn.execute("SELECT status,COUNT(*) n FROM model_requests GROUP BY status")
    }
    return {"config": cfg, "request_counts": counts}


def set_model_config(
    conn: sqlite3.Connection,
    *,
    action_provider: str | None = None,
    decision_provider: str | None = None,
    narrator_provider: str | None = None,
    packet_dir: str | None = None,
) -> dict[str, Any]:
    allowed = {"rules", "local", "manual_chatgpt", "manual_claude"}
    changes: dict[str, Any] = {}
    for key, value in {
        "action_provider": action_provider,
        "decision_provider": decision_provider,
        "narrator_provider": narrator_provider,
    }.items():
        if value is not None:
            if value not in allowed:
                raise ValueError(f"{key} must be one of {sorted(allowed)}")
            changes[key] = value
    if packet_dir is not None:
        changes["packet_dir"] = packet_dir
    if changes:
        sets = ",".join(f"{k}=?" for k in changes) + ",updated_at=CURRENT_TIMESTAMP"
        conn.execute(f"UPDATE model_config SET {sets} WHERE id=1", tuple(changes.values()))
    return _config(conn)


def configured_provider(conn: sqlite3.Connection, task: str) -> str:
    cfg = _config(conn)
    key = {
        "action_interpretation": "action_provider",
        "npc_decision": "decision_provider",
        "narration": "narrator_provider",
    }[task]
    value = str(cfg[key])
    if value == "manual_chatgpt":
        return "chatgpt"
    if value == "manual_claude":
        return "claude"
    if value == "local":
        return "local"
    return "generic"


def _packet_dir(conn: sqlite3.Connection) -> Path:
    configured = str(_config(conn).get("packet_dir") or "")
    path = Path(configured)
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _task_contract(task_type: str, request_id: int) -> dict[str, Any]:
    if task_type == "action_interpretation":
        return {
            "task_type": task_type,
            "request_id": request_id,
            "proposal": {
                "action_type": "observe|wait|travel|speak|investigate|respond|attempt",
                "confidence": "0.0-1.0",
                "target_actor_name": None,
                "target_location_name": None,
                "interaction_id": None,
                "response_choice": "accept|reject|counter|null",
                "duration_days": 0,
                "purpose": "brief description of what the player is trying to do",
                "needs_interpretation": False,
                "note": "brief uncertainty/constraint note",
            },
            "reasoning_summary": "brief, non-chain-of-thought explanation",
        }
    if task_type == "npc_decision":
        return {
            "task_type": task_type,
            "request_id": request_id,
            "proposal": {
                "candidate_key": "one exact key from candidate_options",
                "rationale": "brief reason this feasible candidate fits the actor's accessible information",
            },
            "reasoning_summary": "brief, non-chain-of-thought explanation",
        }
    return {
        "task_type": "narration",
        "request_id": request_id,
        "narration": "player-facing prose only; no hidden-state exposition",
    }


def _common_rules(task_type: str) -> list[str]:
    base = [
        "Treat the supplied packet as authoritative for this bounded task.",
        "Do not invent permanent canon, named institutions, locations, possessions, relationships, or world events not supported by the packet.",
        "The player is the story's camera focus, not the world's causal center.",
        "The wider world has independent agendas and continues moving off camera.",
        "Never make an actor care about the player merely because the narrative camera follows the player.",
        "Return a brief reasoning_summary when requested; do not provide hidden chain-of-thought.",
    ]
    if task_type == "narration":
        base.extend([
            "Narrate only player-accessible information from the envelope.",
            "Rumours remain rumours unless separately verified.",
            "Do not create state changes in prose; the engine has already resolved reality.",
            "Make local life feel independent of the player: people can be busy, distracted, absent, or pursuing unrelated business.",
        ])
    elif task_type == "npc_decision":
        base.extend([
            "Decide only from the actor-safe information envelope and the engine-generated candidate_options.",
            "Select exactly one existing candidate_key; do not invent a new action, target, fact, or hidden premise.",
            "Do not target the player without a persisted causal bridge.",
        ])
    else:
        base.extend([
            "Interpret intent only. Do not decide success, NPC reaction, or create consequences.",
            "Use only persisted actor/location/interaction names or IDs that are supported by the scene/canon context.",
            "If the intent cannot be represented safely by the allowed action types, use action_type=attempt and needs_interpretation=true.",
        ])
    return base


def render_packet(provider: str, request_id: int, task_type: str, payload: dict[str, Any]) -> str:
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    label = _provider_label(provider)
    contract = _task_contract(task_type, request_id)
    rules = _common_rules(task_type)
    return "\n".join([
        f"# Caerness Engine — {label} Bridge Request #{request_id}",
        "",
        f"You are serving as a bounded `{task_type}` component for a persistent simulation.",
        "The SQLite engine, not you, owns world truth and state mutation.",
        "",
        "## Rules",
        *[f"- {r}" for r in rules],
        "",
        "## Task packet",
        "```json",
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        "```",
        "",
        "## Required response contract",
        "Return **one JSON object only**. No markdown fence and no text before or after it.",
        "The engine is tolerant of fences if the chat UI adds them, but raw JSON is preferred.",
        "",
        "```json",
        json.dumps(contract, indent=2, ensure_ascii=False),
        "```",
        "",
        "Do not add fields that try to directly mutate the database.",
    ])


def create_request(
    conn: sqlite3.Connection,
    task_type: str,
    payload: dict[str, Any],
    *,
    provider: str,
    target_kind: str | None = None,
    target_id: int | None = None,
) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {sorted(PROVIDERS)}")
    day = current_day(conn)
    cur = conn.execute(
        """INSERT INTO model_requests(day,task_type,provider,target_kind,target_id,input_json)
           VALUES (?,?,?,?,?,?)""",
        (day, task_type, provider, target_kind, target_id, json.dumps(payload, ensure_ascii=False, default=str)),
    )
    request_id = int(cur.lastrowid)
    text = render_packet(provider, request_id, task_type, payload)
    path = _packet_dir(conn) / f"request_{request_id:05d}_{task_type}_{provider}.md"
    path.write_text(text, encoding="utf-8")
    conn.execute("UPDATE model_requests SET packet_path=? WHERE id=?", (str(path), request_id))
    return {"request_id": request_id, "task_type": task_type, "provider": provider, "packet_path": str(path), "packet": text}


def create_action_request(conn: sqlite3.Connection, raw_text: str, provider: str) -> dict[str, Any]:
    sync_player_location(conn)
    scene = build_scene_packet(conn, raw_text)
    payload = {
        "raw_player_input": raw_text,
        "scene": scene,
        "allowed_action_types": ["observe", "wait", "travel", "speak", "investigate", "respond", "attempt"],
        "important_boundary": "Interpret what the player attempts. Do not resolve success or mutate world state.",
    }
    return create_request(conn, "action_interpretation", payload, provider=provider, target_kind="scene_packet", target_id=scene["scene_packet_id"])


def create_decision_request(conn: sqlite3.Connection, actor_id: int, tier: str, provider: str, canon_limit: int = 6) -> dict[str, Any]:
    day = current_day(conn)
    context = build_actor_context(conn, actor_id, day, canon_limit=canon_limit)
    candidates = generate_candidates(conn, actor_id, tier, day, context)
    payload = {
        "actor_context": context,
        "simulation_tier": tier,
        "candidate_options": [
            {"candidate_key":c.key,"provider_key":c.provider_key,"action_kind":c.action_kind,"utility_hint":c.utility,
             "rationale":c.rationale,"target_actor_id":c.target_actor_id,"interaction_type":c.interaction_type,
             "information_basis":c.information_basis,"tags":list(c.tags),"estimated_cost":c.estimated_cost,"risk":c.risk}
            for c in candidates
        ],
        "important_boundary": "Choose one supplied candidate_key. Candidate generation and feasibility belong to the engine; do not invent another action.",
    }
    return create_request(conn, "npc_decision", payload, provider=provider, target_kind="actor", target_id=actor_id)


def create_narration_request(conn: sqlite3.Connection, turn_id: int, envelope: dict[str, Any], provider: str) -> dict[str, Any]:
    payload = {
        "narration_envelope": envelope,
        "style": {
            "mode": "immersive, grounded, long-form when appropriate",
            "camera": "limited to player-accessible state",
            "world_rule": "Caerness is already alive; do not make the scene orbit the player unnecessarily",
            "handoff_rule": "Never end with 'What do you do?'. End naturally where player agency becomes useful.",
            "continuity_rule": "One response may cover several scenes or time transitions if no meaningful intervention point exists between them.",
        },
    }
    return create_request(conn, "narration", payload, provider=provider, target_kind="turn", target_id=turn_id)


def request_row(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM model_requests WHERE id=?", (request_id,)).fetchone()
    if not row:
        raise ValueError(f"No model request #{request_id}")
    item = dict(row)
    for field in ("input_json", "response_json"):
        raw = item.get(field)
        if raw:
            try:
                item[field[:-5] if field.endswith('_json') else field] = json.loads(raw)
            except Exception:
                pass
    return item


def pending_requests(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id,day,task_type,provider,status,target_kind,target_id,packet_path FROM model_requests WHERE status IN ('pending','responded') ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    # Gracefully accept brief prose around one JSON object.
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        value = json.loads(text[start:end + 1])
        if isinstance(value, dict):
            return value
    raise ValueError("Could not parse one JSON object from the model response.")


def _validate_response_shape(request_id: int, task_type: str, data: dict[str, Any]) -> None:
    if str(data.get("task_type")) != task_type:
        raise ValueError(f"Response task_type must be {task_type!r}")
    if int(data.get("request_id", -1)) != request_id:
        raise ValueError(f"Response request_id must be {request_id}")
    if task_type in {"action_interpretation", "npc_decision"} and not isinstance(data.get("proposal"), dict):
        raise ValueError("Response must contain a proposal object.")
    if task_type == "narration" and not isinstance(data.get("narration"), str):
        raise ValueError("Narration response must contain a narration string.")


def import_response(conn: sqlite3.Connection, request_id: int, raw: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM model_requests WHERE id=?", (request_id,)).fetchone()
    if not row:
        raise ValueError(f"No model request #{request_id}")
    if row["status"] not in {"pending", "responded"}:
        raise ValueError(f"Request #{request_id} has status {row['status']}; it cannot accept a response.")
    data = _extract_json(raw)
    _validate_response_shape(request_id, str(row["task_type"]), data)
    conn.execute(
        "UPDATE model_requests SET status='responded',response_raw=?,response_json=?,responded_at=CURRENT_TIMESTAMP WHERE id=?",
        (raw, json.dumps(data, ensure_ascii=False), request_id),
    )
    return data


def _match_named(conn: sqlite3.Connection, table: str, name: str | None) -> sqlite3.Row | None:
    if not name:
        return None
    row = conn.execute(f"SELECT * FROM {table} WHERE lower(name)=lower(?)", (name,)).fetchone()
    if row:
        return row
    rows = conn.execute(f"SELECT * FROM {table} WHERE lower(name) LIKE ? ORDER BY length(name),name LIMIT 4", (f"%{name.lower()}%",)).fetchall()
    return rows[0] if len(rows) == 1 else None


def proposal_from_action_response(conn: sqlite3.Connection, raw_text: str, response: dict[str, Any]) -> PlayerActionProposal:
    p = response["proposal"]
    action_type = str(p.get("action_type") or "attempt")
    allowed = {"observe", "wait", "travel", "speak", "investigate", "respond", "attempt"}
    if action_type not in allowed:
        raise ValueError(f"Unsupported player action_type: {action_type}")
    confidence = max(0.0, min(1.0, float(p.get("confidence", 0.5))))
    duration = max(0, int(p.get("duration_days") or 0))
    purpose = str(p.get("purpose") or raw_text)
    note = str(p.get("note") or "")
    needs = bool(p.get("needs_interpretation", False))
    target_actor = _match_named(conn, "actors", p.get("target_actor_name"))
    target_location = _match_named(conn, "locations", p.get("target_location_name"))
    interaction_id = int(p["interaction_id"]) if p.get("interaction_id") is not None else None
    response_choice = p.get("response_choice")

    route_ids: tuple[int, ...] = ()
    route_names: tuple[str, ...] = ()
    if action_type == "travel":
        player = get_player(conn)
        if not player or target_location is None or player["current_location_id"] is None:
            needs = True
            note = note or "Travel destination/current location was not grounded in persisted state."
        else:
            route = shortest_route(conn, int(player["current_location_id"]), int(target_location["id"]))
            if route is None:
                needs = True
                note = note or "No persisted route connects the requested destination."
            else:
                days, ids, names = route
                duration = days
                route_ids, route_names = tuple(ids), tuple(names)

    if action_type in {"speak", "investigate"} and target_actor is None:
        needs = True
        note = note or "Named target actor was not uniquely grounded in persisted state."
    if action_type == "speak" and target_actor is not None:
        player = get_player(conn)
        available = False
        if player and player["current_location_id"] is not None:
            loc = int(player["current_location_id"])
            if str(target_actor["actor_type"]) == "institution":
                available = target_actor["current_location_id"] is not None and int(target_actor["current_location_id"]) == loc
            else:
                available = actor_is_present_candidate(
                    conn, int(target_actor["id"]), loc,
                    purpose=f"player_speak:{int(player['player_actor_id'])}:{int(target_actor['id'])}",
                )
        if not available:
            needs = True
            note = note or "Conversation target is not plausibly present for a direct conversation here."
    if action_type == "respond":
        if interaction_id is None or response_choice not in {"accept", "reject", "counter"}:
            needs = True
            note = note or "Response did not identify a valid pending interaction and response choice."
        elif not conn.execute("SELECT 1 FROM interactions WHERE id=? AND status='pending'", (interaction_id,)).fetchone():
            needs = True
            note = note or "Referenced interaction is not currently pending."

    return PlayerActionProposal(
        raw_text=raw_text,
        action_type=action_type,
        confidence=confidence,
        target_actor_id=int(target_actor["id"]) if target_actor else None,
        target_actor_name=str(target_actor["name"]) if target_actor else None,
        target_location_id=int(target_location["id"]) if target_location else None,
        target_location_name=str(target_location["name"]) if target_location else None,
        interaction_id=interaction_id,
        response_choice=response_choice,
        duration_days=duration,
        purpose=purpose,
        route_location_ids=route_ids,
        route_location_names=route_names,
        needs_interpretation=needs,
        note=note,
    )


def proposal_from_decision_response(
    conn: sqlite3.Connection, actor_id: int, tier: str, day: int, response: dict[str, Any], requested_keys: set[str]
) -> DecisionProposal:
    p=response["proposal"]
    candidate_key=str(p.get("candidate_key") or "")
    if not candidate_key or candidate_key not in requested_keys:
        raise ValueError("npc_decision must choose one candidate_key supplied in the request")
    context=build_actor_context(conn,actor_id,day)
    candidates=generate_candidates(conn,actor_id,tier,day,context)
    by_key={c.key:c for c in candidates}
    candidate=by_key.get(candidate_key)
    if candidate is None:
        raise ValueError("selected candidate is no longer feasible in current state")
    evaluation_id=record_external_selection(conn,actor_id,tier,day,context,candidates,candidate_key)
    proposal=candidate_to_proposal(candidate,evaluation_id)
    rationale=str(p.get("rationale") or response.get("reasoning_summary") or proposal.rationale)
    return DecisionProposal(proposal.action_type,proposal.score,rationale,proposal.goal_id,proposal.pressure_id,proposal.canon_chunk_ids,proposal.effects,proposal.target_actor_id,proposal.interaction_type)


def bridge_play(conn: sqlite3.Connection, raw_text: str, provider: str) -> dict[str, Any]:
    """Start a no-API ChatGPT/Claude turn.

    If deterministic interpretation is sufficient, state resolves immediately and only narration
    is queued. Otherwise no state mutates and an action-interpretation packet is queued first.
    """
    sync_player_location(conn)
    heuristic = HeuristicPlayerActionProvider().propose(conn, raw_text)
    if heuristic.needs_interpretation:
        req = create_action_request(conn, raw_text, provider)
        return {"status": "awaiting_action_interpretation", **req}

    resolved = resolve_turn_state(conn, raw_text, action_provider=FixedActionProvider(heuristic))
    nreq = create_narration_request(conn, int(resolved["turn_id"]), resolved["narration_envelope"], provider)
    conn.execute("UPDATE turns SET narration_text=? WHERE id=?", (f"[Awaiting {provider} narration request #{nreq['request_id']}]", resolved["turn_id"]))
    return {"status": "awaiting_narration", "turn": resolved, "next_request": nreq}


def apply_model_request(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM model_requests WHERE id=?", (request_id,)).fetchone()
    if not row:
        raise ValueError(f"No model request #{request_id}")
    if row["status"] != "responded":
        raise ValueError(f"Request #{request_id} must be responded before apply; current status={row['status']}")
    response = json.loads(row["response_json"])
    input_data = json.loads(row["input_json"])
    task = str(row["task_type"])
    provider = str(row["provider"])

    if task == "action_interpretation":
        raw_text = str(input_data["raw_player_input"])
        proposal = proposal_from_action_response(conn, raw_text, response)
        if proposal.needs_interpretation:
            summary = proposal.note or "Model could not safely ground the requested action."
            conn.execute("UPDATE model_requests SET status='error',applied_summary=?,applied_at=CURRENT_TIMESTAMP WHERE id=?", (summary, request_id))
            return {"status": "not_applied", "summary": summary, "proposal": asdict(proposal)}
        resolved = resolve_turn_state(conn, raw_text, action_provider=FixedActionProvider(proposal))
        nreq = create_narration_request(conn, int(resolved["turn_id"]), resolved["narration_envelope"], provider)
        conn.execute("UPDATE turns SET narration_text=? WHERE id=?", (f"[Awaiting {provider} narration request #{nreq['request_id']}]", resolved["turn_id"]))
        summary = f"Action interpretation applied as {proposal.action_type}; turn #{resolved['turn_id']} resolved and narration queued."
        conn.execute("UPDATE model_requests SET status='applied',applied_summary=?,applied_at=CURRENT_TIMESTAMP WHERE id=?", (summary, request_id))
        return {"status": "applied", "summary": summary, "turn": resolved, "next_request": nreq}

    if task == "npc_decision":
        actor_id = int(row["target_id"])
        tier = str(input_data.get("simulation_tier") or "STRATEGIC")
        requested_keys={str(c.get("candidate_key")) for c in input_data.get("candidate_options",[]) if c.get("candidate_key")}
        proposal = proposal_from_decision_response(conn, actor_id, tier, int(row["day"]), response, requested_keys)
        did = apply_decision(conn, actor_id, tier, int(row["day"]), proposal)
        summary = f"Applied model-backed decision #{did} for actor #{actor_id}: {proposal.action_type}."
        conn.execute("UPDATE model_requests SET status='applied',applied_summary=?,applied_at=CURRENT_TIMESTAMP WHERE id=?", (summary, request_id))
        return {"status": "applied", "summary": summary, "decision_id": did}

    if task == "narration":
        turn_id = int(row["target_id"])
        narration = str(response["narration"]).strip()
        if not narration:
            raise ValueError("Narration may not be empty.")
        if not conn.execute("SELECT 1 FROM turns WHERE id=?", (turn_id,)).fetchone():
            raise ValueError(f"Target turn #{turn_id} does not exist.")
        conn.execute("UPDATE turns SET narration_text=? WHERE id=?", (narration, turn_id))
        summary = f"Applied narration to turn #{turn_id}."
        conn.execute("UPDATE model_requests SET status='applied',applied_summary=?,applied_at=CURRENT_TIMESTAMP WHERE id=?", (summary, request_id))
        return {"status": "applied", "summary": summary, "turn_id": turn_id, "narration": narration}

    raise ValueError(f"Unsupported task type: {task}")


def assess_request_route(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM model_requests WHERE id=?", (request_id,)).fetchone()
    if not row:
        raise ValueError(f"No model request #{request_id}")
    payload = json.loads(row["input_json"])
    assessment = assess_model_task(
        conn, str(row["task_type"]), payload,
        target_kind=str(row["target_kind"]) if row["target_kind"] is not None else None,
        target_id=int(row["target_id"]) if row["target_id"] is not None else None,
    )
    return assessment.as_dict()


def _run_segmented_local_narration(conn: sqlite3.Connection, request_id: int, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Generate one player-facing section across several technical local-model calls.

    The player sees one continuous passage. Scene/model boundaries are implementation details,
    never reasons to demand a 'continue' input.
    """
    envelope = payload.get("narration_envelope") or {}
    outline = envelope.get("segment_outline") or []
    if len(outline) <= 1:
        raise ValueError("Segmented narration requires at least two outline beats.")
    cfg = runtime_config(conn)
    per_segment_cap = max(320, min(720, int(cfg["local_max_output_tokens"] * 0.6)))
    pieces: list[str] = []
    token_usage = {"prompt": 0, "completion": 0}
    for index, segment in enumerate(outline):
        final = index == len(outline) - 1
        compact = {
            "resolved_action": envelope.get("action_result"),
            "scene_after": envelope.get("scene_after"),
            "agency_handoff": envelope.get("agency_handoff") if final else {"handoff_type": "none"},
            "current_beat": segment,
            "beat_index": index + 1,
            "beat_count": len(outline),
            "previous_tail": pieces[-1][-900:] if pieces else "",
        }
        prompt = "\n".join([
            "Write only immersive Caerness narration for this one beat of a larger continuous section.",
            "Reality is already resolved in the supplied data. Do not invent permanent state or hidden facts.",
            "Do not ask 'What do you do?' and do not present a menu of choices.",
            "Do not manufacture an NPC question merely to create a stopping point.",
            "Maintain continuity with previous_tail without repeating it.",
            "If this is not the final beat, end in motion so the next beat can continue seamlessly.",
            "If it is the final beat, end naturally at the supplied agency handoff.",
            json.dumps(compact, ensure_ascii=False, default=str),
        ])
        result = chat_local(
            conn,
            [
                {"role": "system", "content": "You narrate a bounded segment of a persistent simulation. Prose only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=per_segment_cap,
            temperature=0.7,
            require_json=False,
        )
        text = result.text.strip()
        if not text:
            raise ValueError(f"Local narrator returned an empty segment at beat {index + 1}.")
        pieces.append(text)
        token_usage["prompt"] += int(result.prompt_tokens or 0)
        token_usage["completion"] += int(result.completion_tokens or 0)
    return "\n\n".join(pieces), token_usage


def run_request_local(conn: sqlite3.Connection, request_id: int, *, force: bool = False, apply: bool = False) -> dict[str, Any]:
    """Run one bounded request on a phone-local model server.

    The quality router can decline automatic local execution when ChatGPT/Claude is likely
    to be materially better or when the configured 12 GB profile would be pushed too hard.
    `force=True` is always available to preserve player choice.
    """
    row = conn.execute("SELECT * FROM model_requests WHERE id=?", (request_id,)).fetchone()
    if not row:
        raise ValueError(f"No model request #{request_id}")
    if row["status"] not in {"pending", "responded"}:
        raise ValueError(f"Request #{request_id} has status {row['status']}")
    payload = json.loads(row["input_json"])
    assessment = assess_model_task(
        conn, str(row["task_type"]), payload,
        target_kind=str(row["target_kind"]) if row["target_kind"] is not None else None,
        target_id=int(row["target_id"]) if row["target_id"] is not None else None,
    )
    if assessment.recommendation in {"external_recommended", "external_strongly_recommended"} and not force:
        chatgpt_path = export_request(conn, request_id, provider="chatgpt")
        claude_path = export_request(conn, request_id, provider="claude")
        return {
            "status": "external_recommended",
            "assessment": assessment.as_dict(),
            "chatgpt_packet": chatgpt_path,
            "claude_packet": claude_path,
            "message": "Local execution was not started; use ChatGPT/Claude or force local execution.",
        }

    if str(row["task_type"]) == "narration" and len((payload.get("narration_envelope") or {}).get("segment_outline") or []) > 1:
        narration, usage = _run_segmented_local_narration(conn, request_id, payload)
        synthetic = json.dumps({"task_type": "narration", "request_id": request_id, "narration": narration}, ensure_ascii=False)
        response = import_response(conn, request_id, synthetic)
        cfg = runtime_config(conn)
        out: dict[str, Any] = {
            "status": "responded",
            "assessment": assessment.as_dict(),
            "backend": str(cfg["local_backend"]),
            "model": str(cfg["local_model"]),
            "prompt_tokens": usage["prompt"],
            "completion_tokens": usage["completion"],
            "segmented_generation": True,
            "segment_count": len((payload.get("narration_envelope") or {}).get("segment_outline") or []),
            "response": response,
        }
    else:
        contract_packet = render_packet("local", request_id, str(row["task_type"]), payload)
        result = chat_local(
            conn,
            [
                {"role": "system", "content": "You are a bounded component of the Caerness simulation. Follow the supplied response contract exactly. Return only the requested JSON object."},
                {"role": "user", "content": contract_packet},
            ],
            require_json=True,
        )
        response = import_response(conn, request_id, result.text)
        out = {
            "status": "responded",
            "assessment": assessment.as_dict(),
            "backend": result.backend,
            "model": result.model,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "segmented_generation": False,
            "response": response,
        }
    if apply:
        out["applied"] = apply_model_request(conn, request_id)
        out["status"] = "applied"
    return out


def export_request(conn: sqlite3.Connection, request_id: int, provider: str | None = None, path: str | None = None) -> str:
    row = conn.execute("SELECT * FROM model_requests WHERE id=?", (request_id,)).fetchone()
    if not row:
        raise ValueError(f"No model request #{request_id}")
    provider = provider or str(row["provider"])
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    payload = json.loads(row["input_json"])
    text = render_packet(provider, request_id, str(row["task_type"]), payload)
    out = Path(path) if path else _packet_dir(conn) / f"request_{request_id:05d}_{row['task_type']}_{provider}.md"
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    if provider == row["provider"]:
        conn.execute("UPDATE model_requests SET packet_path=? WHERE id=?", (str(out), request_id))
    return str(out)
