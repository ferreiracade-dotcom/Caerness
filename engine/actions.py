from __future__ import annotations

import heapq
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .interactions import apply_player_response, create_interaction, resolve_interaction
from .player import get_player, sync_player_location
from .presence import actor_is_present_candidate


@dataclass(frozen=True)
class PlayerActionProposal:
    raw_text: str
    action_type: str
    confidence: float
    target_actor_id: int | None = None
    target_actor_name: str | None = None
    target_location_id: int | None = None
    target_location_name: str | None = None
    interaction_id: int | None = None
    response_choice: str | None = None
    duration_days: int = 0
    purpose: str = ""
    route_location_ids: tuple[int, ...] = ()
    route_location_names: tuple[str, ...] = ()
    needs_interpretation: bool = False
    note: str = ""
    institution_name: str | None = None
    role_title: str | None = None
    additional_terms: bool = False
    review_action_id: int | None = None


@dataclass(frozen=True)
class PlayerActionResult:
    action_id: int
    status: str
    action_type: str
    summary: str
    duration_days: int = 0
    advance_days: int = 0
    deferred_location_id: int | None = None
    interaction_id: int | None = None
    event_ids: tuple[int, ...] = ()
    knowledge_ids: tuple[int, ...] = ()
    detail: dict[str, Any] | None = None


class PlayerActionProvider(Protocol):
    def propose(self, conn: sqlite3.Connection, raw_text: str) -> PlayerActionProposal:
        ...


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def is_appointment_request(conn: sqlite3.Connection, text: str) -> bool:
    """Legacy appointment bridge only; unrelated offers remain ordinary input."""
    low = _normalize(text)
    if re.search(r"\b(?:appoint|promote)\b", low):
        return True
    return bool(re.search(r"\boffer\b", low) and any(
        str(row[0]).lower() in low for row in conn.execute("SELECT title FROM institutional_roles WHERE status='active'")
    ))


def _extract_duration_days(text: str, default: int = 1) -> int:
    low = _normalize(text)
    # Keep player-time coarse for v0.5. Sub-day clocks are a later concern.
    patterns = [
        (r"\b(\d+)\s*(?:day|days)\b", 1),
        (r"\b(\d+)\s*(?:week|weeks)\b", 7),
        (r"\b(\d+)\s*(?:month|months)\b", 30),
    ]
    for pattern, mult in patterns:
        m = re.search(pattern, low)
        if m:
            return max(1, int(m.group(1)) * mult)
    if "tomorrow" in low or "overnight" in low:
        return 1
    if "a week" in low or "one week" in low:
        return 7
    if "a month" in low or "one month" in low:
        return 30
    return max(0, default)


def _named_match(rows: list[sqlite3.Row], text: str, *, name_key: str = "name") -> sqlite3.Row | None:
    low = _normalize(text)
    candidates: list[tuple[int, sqlite3.Row]] = []
    for row in rows:
        name = str(row[name_key])
        nlow = name.lower()
        plain = re.sub(r"\[demo\]\s*", "", nlow).strip()
        if nlow in low or (plain and plain in low):
            candidates.append((len(plain), row))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def _find_pending_player_interaction(conn: sqlite3.Connection, player_id: int, text: str) -> sqlite3.Row | None:
    m = re.search(r"(?:#|interaction\s+)(\d+)", text.lower())
    if m:
        return conn.execute(
            "SELECT * FROM interactions WHERE id=? AND status='pending' AND recipient_actor_id=?",
            (int(m.group(1)), player_id),
        ).fetchone()
    rows = conn.execute(
        "SELECT * FROM interactions WHERE status='pending' AND recipient_actor_id=? ORDER BY response_due_day,id",
        (player_id,),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


def shortest_route(conn: sqlite3.Connection, start_location_id: int, end_location_id: int) -> tuple[int, list[int], list[str]] | None:
    if start_location_id == end_location_id:
        name = conn.execute("SELECT name FROM locations WHERE id=?", (start_location_id,)).fetchone()[0]
        return 0, [start_location_id], [str(name)]

    graph: dict[int, list[tuple[int, int]]] = {}
    for row in conn.execute("SELECT location_a_id,location_b_id,travel_days FROM location_links WHERE active=1"):
        a, b, days = int(row[0]), int(row[1]), int(row[2])
        graph.setdefault(a, []).append((b, days))
        graph.setdefault(b, []).append((a, days))

    pq: list[tuple[int, int]] = [(0, start_location_id)]
    dist = {start_location_id: 0}
    prev: dict[int, int] = {}
    while pq:
        cost, node = heapq.heappop(pq)
        if cost != dist.get(node):
            continue
        if node == end_location_id:
            break
        for nxt, weight in graph.get(node, []):
            new_cost = cost + weight
            if new_cost < dist.get(nxt, 10**9):
                dist[nxt] = new_cost
                prev[nxt] = node
                heapq.heappush(pq, (new_cost, nxt))

    if end_location_id not in dist:
        return None
    path = [end_location_id]
    while path[-1] != start_location_id:
        path.append(prev[path[-1]])
    path.reverse()
    names = []
    for lid in path:
        row = conn.execute("SELECT name FROM locations WHERE id=?", (lid,)).fetchone()
        names.append(str(row[0]) if row else f"Location {lid}")
    return int(dist[end_location_id]), path, names


class HeuristicPlayerActionProvider:
    """Conservative freeform -> structured action adapter.

    It resolves only intents that are well-grounded in persisted state. Unknown freeform
    remains `attempt` + `needs_interpretation` rather than hallucinating a state mutation.
    A future model adapter can replace only this interpretation layer while keeping the
    same validator and authoritative resolver.
    """

    def propose(self, conn: sqlite3.Connection, raw_text: str) -> PlayerActionProposal:
        sync_player_location(conn)
        player = get_player(conn)
        if not player:
            raise ValueError("No player is configured.")
        player_id = int(player["player_actor_id"])
        current_location_id = int(player["current_location_id"]) if player["current_location_id"] is not None else None
        low = _normalize(raw_text)

        if not low:
            return PlayerActionProposal(raw_text, "observe", 0.95, note="Empty input treated as taking stock of the scene.")

        response_words = {
            "accept": ("accept", "agree", "yes", "take the offer"),
            "reject": ("reject", "refuse", "decline", "no"),
            "counter": ("counter", "counteroffer", "counter offer", "renegotiate"),
        }
        for choice, words in response_words.items():
            if any(re.search(rf"\b{re.escape(w)}\b", low) for w in words):
                interaction = _find_pending_player_interaction(conn, player_id, raw_text)
                if interaction:
                    return PlayerActionProposal(
                        raw_text, "respond", 0.98,
                        interaction_id=int(interaction["id"]), response_choice=choice,
                        purpose=raw_text,
                    )

        # Existing responses resolve first (including 'I accept the offer'). New
        # consequential offers reach the interpreter before approach/speak/wait.
        if is_appointment_request(conn, raw_text):
            return PlayerActionProposal(raw_text, "attempt", 0.5, purpose=raw_text,
                needs_interpretation=True,
                note="This proposal needs an intention interpreter; no appointment or promise has been made yet.")

        locations = conn.execute("SELECT id,name,kind FROM locations ORDER BY length(name) DESC").fetchall()
        location = _named_match(list(locations), raw_text)
        if location is not None and any(v in low for v in ("travel", "go to", "head to", "ride to", "walk to", "leave for", "journey to", "set out for")):
            if current_location_id is None:
                return PlayerActionProposal(raw_text, "travel", 0.95, target_location_id=int(location["id"]), target_location_name=str(location["name"]), needs_interpretation=True, note="Player has no persisted current location.")
            route = shortest_route(conn, current_location_id, int(location["id"]))
            if route is None:
                return PlayerActionProposal(raw_text, "travel", 0.92, target_location_id=int(location["id"]), target_location_name=str(location["name"]), needs_interpretation=True, note="No persisted route connects the two locations.")
            days, ids, names = route
            return PlayerActionProposal(
                raw_text, "travel", 0.99,
                target_location_id=int(location["id"]), target_location_name=str(location["name"]),
                duration_days=days, route_location_ids=tuple(ids), route_location_names=tuple(names),
                purpose=raw_text,
            )

        if any(v in low for v in ("wait", "rest", "sleep", "stay here", "pass the time", "lay low")):
            return PlayerActionProposal(raw_text, "wait", 0.97, duration_days=_extract_duration_days(raw_text, 1), purpose=raw_text)

        actors = conn.execute("SELECT id,name,actor_type,subtype,current_location_id FROM actors WHERE status='active' ORDER BY length(name) DESC").fetchall()
        actor = _named_match(list(actors), raw_text)

        if actor is not None and any(v in low for v in ("investigate", "follow", "look into", "find out about", "ask around about", "watch ")):
            return PlayerActionProposal(
                raw_text, "investigate", 0.93,
                target_actor_id=int(actor["id"]), target_actor_name=str(actor["name"]),
                duration_days=max(1, _extract_duration_days(raw_text, 1)), purpose=raw_text,
            )

        if actor is not None and any(v in low for v in ("talk", "speak", "ask ", "approach", "tell ", "meet ", "confront")):
            if current_location_id is None:
                available = False
            elif str(actor["actor_type"]) == "institution":
                available = actor["current_location_id"] is not None and int(actor["current_location_id"]) == current_location_id
            else:
                available = actor_is_present_candidate(
                    conn, int(actor["id"]), current_location_id,
                    purpose=f"player_speak:{player_id}:{int(actor['id'])}",
                )
            return PlayerActionProposal(
                raw_text, "speak", 0.94,
                target_actor_id=int(actor["id"]), target_actor_name=str(actor["name"]), purpose=raw_text,
                needs_interpretation=not available,
                note="Target is not plausibly present for a direct conversation here." if not available else "",
            )

        if any(v in low for v in ("look around", "observe", "listen", "take stock", "survey", "watch the room", "check the room")):
            return PlayerActionProposal(raw_text, "observe", 0.96, purpose=raw_text)

        return PlayerActionProposal(
            raw_text, "attempt", 0.35, purpose=raw_text, needs_interpretation=True,
            note="Freeform intent requires a richer action interpreter; no permanent state is guessed.",
        )


def _insert_player_action(conn: sqlite3.Connection, player_id: int, day: int, proposal: PlayerActionProposal) -> int:
    cur = conn.execute(
        """INSERT INTO player_actions(
               day_started,player_actor_id,raw_text,action_type,target_actor_id,target_location_id,
               interaction_id,response_choice,proposed_json,status,duration_days
           ) VALUES (?,?,?,?,?,?,?,?,?,'proposed',?)""",
        (
            # Schema 108 stores domain intentions under attempt; the typed proposal
            # and result preserve appoint. Existing saves need no schema rewrite.
            day, player_id, proposal.raw_text, "attempt" if proposal.action_type == "appoint" else proposal.action_type, proposal.target_actor_id,
            proposal.target_location_id, proposal.interaction_id, proposal.response_choice,
            json.dumps(asdict(proposal)), proposal.duration_days,
        ),
    )
    return int(cur.lastrowid)


def _record_result(conn: sqlite3.Connection, action_id: int, day: int, status: str, result: dict[str, Any]) -> None:
    stored_status = {"blocked": "invalid", "refused": "failed", "countered": "applied", "needs_confirmation": "proposed"}.get(status, status)
    conn.execute(
        "UPDATE player_actions SET day_resolved=?,status=?,result_json=? WHERE id=?",
        (day, stored_status, json.dumps(result), action_id),
    )


def _causal_link(conn: sqlite3.Connection, day: int, action_id: int, target_kind: str, target_id: int, relation: str) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO causal_links(day,source_kind,source_id,target_kind,target_id,relation)
           VALUES (?,'player_action',?,?,?,?)""",
        (day, action_id, target_kind, target_id, relation),
    )


def begin_player_action(
    conn: sqlite3.Connection,
    raw_text: str,
    provider: PlayerActionProvider | None = None,
) -> tuple[PlayerActionProposal, PlayerActionResult]:
    sync_player_location(conn)
    player = get_player(conn)
    if not player:
        raise ValueError("No player is configured. Use player-set first.")
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    player_id = int(player["player_actor_id"])
    proposal = (provider or HeuristicPlayerActionProvider()).propose(conn, raw_text)
    action_id = _insert_player_action(conn, player_id, day, proposal)

    if proposal.needs_interpretation:
        result = PlayerActionResult(
            action_id, "needs_interpretation", proposal.action_type,
            proposal.note or "Action requires interpretation before the engine can mutate state.",
            duration_days=proposal.duration_days,
            detail={"proposal": asdict(proposal)},
        )
        _record_result(conn, action_id, day, result.status, asdict(result))
        return proposal, result

    if proposal.action_type == "observe":
        result = PlayerActionResult(action_id, "applied", "observe", "The player takes stock of the current scene.", detail={})
        _record_result(conn, action_id, day, result.status, asdict(result))
        return proposal, result

    if proposal.action_type == "appoint":
        if proposal.review_action_id is None:
            result = PlayerActionResult(action_id, "needs_confirmation", "appoint",
                f"Proposed scope: offer {proposal.role_title or 'an existing role'} to {proposal.target_actor_name or 'the named person'}. "
                "This includes no gifts, transfers, pay or additional promises. Review this limited scope against your full instruction before confirming; nothing has been offered yet.",
                detail={"committed": False, "review_action_id": action_id, "original_instruction": raw_text})
            _record_result(conn, action_id, day, result.status, asdict(result))
            return proposal, result
        from .player_appointments import execute_appointment
        result = execute_appointment(conn, player_id, day, action_id, proposal)
        if result.interaction_id:
            _causal_link(conn, day, action_id, "interaction", result.interaction_id, "proposed")
        _record_result(conn, action_id, day, result.status, asdict(result))
        return proposal, result

    if proposal.action_type == "wait":
        result = PlayerActionResult(
            action_id, "applied", "wait",
            f"The player chooses to remain in place while {proposal.duration_days} day(s) pass.",
            duration_days=proposal.duration_days, advance_days=proposal.duration_days,
            detail={"purpose": proposal.purpose},
        )
        # Final resolved day is filled after world time advances by finalize_player_action.
        return proposal, result

    if proposal.action_type == "travel":
        if proposal.target_location_id is None:
            result = PlayerActionResult(action_id, "invalid", "travel", "No valid destination was resolved.")
            _record_result(conn, action_id, day, result.status, asdict(result))
            return proposal, result
        result = PlayerActionResult(
            action_id, "applied", "travel",
            f"Travel begins toward {proposal.target_location_name} along the persisted route.",
            duration_days=proposal.duration_days, advance_days=proposal.duration_days,
            deferred_location_id=proposal.target_location_id,
            detail={"route": list(proposal.route_location_names)},
        )
        return proposal, result

    if proposal.action_type == "respond":
        if proposal.interaction_id is None or proposal.response_choice is None:
            result = PlayerActionResult(action_id, "invalid", "respond", "No unique pending interaction was resolved.")
            _record_result(conn, action_id, day, result.status, asdict(result))
            return proposal, result
        ir = apply_player_response(
            conn, proposal.interaction_id, player_id, proposal.response_choice, day,
            counter_terms={"purpose": proposal.purpose} if proposal.response_choice == "counter" else None,
        )
        result = PlayerActionResult(
            action_id, "applied", "respond", ir.summary,
            interaction_id=proposal.interaction_id,
            event_ids=(ir.event_id,) if ir.event_id else (),
            detail={"response": ir.response, "agreement_id": ir.agreement_id, "child_interaction_id": ir.child_interaction_id},
        )
        _causal_link(conn, day, action_id, "interaction", proposal.interaction_id, "answered")
        _record_result(conn, action_id, day, result.status, asdict(result))
        return proposal, result

    if proposal.action_type == "speak":
        if proposal.target_actor_id is None:
            result = PlayerActionResult(action_id, "invalid", "speak", "No valid conversation target was resolved.")
            _record_result(conn, action_id, day, result.status, asdict(result))
            return proposal, result
        iid = create_interaction(
            conn, player_id, proposal.target_actor_id, "conversation", day,
            urgency=5, stakes=1, terms={"purpose": proposal.purpose},
            rationale="Direct player conversation", response_due_day=day,
        )
        ir = resolve_interaction(conn, iid, day)
        result = PlayerActionResult(
            action_id, "applied", "speak", ir.summary,
            interaction_id=iid, event_ids=(ir.event_id,) if ir.event_id else (),
            detail={"interaction_status": ir.status, "response": ir.response},
        )
        _causal_link(conn, day, action_id, "interaction", iid, "initiated")
        _record_result(conn, action_id, day, result.status, asdict(result))
        return proposal, result

    if proposal.action_type == "investigate":
        if proposal.target_actor_id is None:
            result = PlayerActionResult(action_id, "invalid", "investigate", "No valid investigation target was resolved.")
            _record_result(conn, action_id, day, result.status, asdict(result))
            return proposal, result
        iid = create_interaction(
            conn, player_id, proposal.target_actor_id, "investigation", day,
            urgency=3, stakes=2, terms={"purpose": proposal.purpose},
            rationale="Explicit player investigation", response_due_day=day,
        )
        # Investigation resolves after its declared time cost in the turn pipeline; the interaction is kept pending for now.
        result = PlayerActionResult(
            action_id, "applied", "investigate",
            f"The player begins investigating {proposal.target_actor_name}.",
            duration_days=proposal.duration_days, advance_days=proposal.duration_days,
            interaction_id=iid,
            detail={"target_actor_id": proposal.target_actor_id},
        )
        _causal_link(conn, day, action_id, "interaction", iid, "initiated")
        return proposal, result

    result = PlayerActionResult(
        action_id, "needs_interpretation", "attempt",
        "The freeform action was not specific enough for the deterministic resolver; state was left unchanged.",
        detail={"proposal": asdict(proposal)},
    )
    _record_result(conn, action_id, day, result.status, asdict(result))
    return proposal, result


def confirm_appointment_scope(conn: sqlite3.Connection, action_id: int) -> dict[str, Any]:
    """Only a direct player confirmation endpoint calls this; model fields cannot."""
    from dataclasses import replace
    from .model_gateway import FixedActionProvider
    from .turns import play_turn
    player = get_player(conn)
    row = conn.execute("SELECT * FROM player_actions WHERE id=?", (action_id,)).fetchone()
    if not player or not row or row["player_actor_id"] != player["player_actor_id"] or row["status"] != "proposed":
        raise ValueError("This scope review is not pending for the current player.")
    proposal = PlayerActionProposal(**json.loads(row["proposed_json"]))
    if proposal.action_type != "appoint":
        raise ValueError("This is not an appointment scope review.")
    conn.execute("UPDATE player_actions SET status='applied' WHERE id=?", (action_id,))
    return play_turn(conn, proposal.raw_text, action_provider=FixedActionProvider(replace(proposal, review_action_id=action_id)))


def finalize_player_action(conn: sqlite3.Connection, proposal: PlayerActionProposal, result: PlayerActionResult) -> PlayerActionResult:
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    player = get_player(conn)
    if not player:
        raise ValueError("No player configured.")
    player_id = int(player["player_actor_id"])
    event_ids = list(result.event_ids)
    knowledge_ids = list(result.knowledge_ids)
    summary = result.summary
    detail = dict(result.detail or {})

    if result.status != "applied":
        _record_result(conn, result.action_id, day, result.status, asdict(result))
        return result

    if proposal.action_type == "travel" and result.deferred_location_id is not None:
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (result.deferred_location_id, player_id))
        conn.execute(
            "UPDATE player_state SET current_location_id=?,updated_day=? WHERE id=1",
            (result.deferred_location_id, day),
        )
        summary = f"The player arrived at {proposal.target_location_name} after {proposal.duration_days} day(s)."
        detail["arrived"] = proposal.target_location_name

    if proposal.action_type == "investigate" and result.interaction_id is not None:
        ir = resolve_interaction(conn, result.interaction_id, day)
        summary = ir.summary
        if ir.event_id:
            event_ids.append(ir.event_id)
        rows = conn.execute(
            "SELECT id FROM knowledge WHERE knower_actor_id=? AND fact_key=?",
            (player_id, f"investigation:{result.interaction_id}"),
        ).fetchall()
        knowledge_ids.extend(int(r[0]) for r in rows)

    final = PlayerActionResult(
        action_id=result.action_id,
        status=result.status,
        action_type=result.action_type,
        summary=summary,
        duration_days=result.duration_days,
        advance_days=result.advance_days,
        deferred_location_id=result.deferred_location_id,
        interaction_id=result.interaction_id,
        event_ids=tuple(event_ids),
        knowledge_ids=tuple(knowledge_ids),
        detail=detail,
    )
    _record_result(conn, result.action_id, day, final.status, asdict(final))
    return final
