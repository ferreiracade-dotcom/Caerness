from __future__ import annotations

import heapq
import math
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
    changes: dict | None = None  # new terms the protagonist puts to a counter-offer


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


def _travel_graph(conn: sqlite3.Connection) -> dict[int, list[tuple[int, float]]]:
    """Edges by travel time. travel_routes is the world's graph; location_links (if any) is a fallback;
    a district and its parent are joined at zero cost (local movement needs no route)."""
    graph: dict[int, list[tuple[int, float]]] = {}
    for row in conn.execute("SELECT from_location_id,to_location_id,base_days,bidirectional FROM travel_routes WHERE status IN ('open','restricted')"):
        a, b, days = int(row[0]), int(row[1]), float(row[2])
        graph.setdefault(a, []).append((b, days))
        if row[3]:
            graph.setdefault(b, []).append((a, days))
    try:
        for row in conn.execute("SELECT location_a_id,location_b_id,travel_days FROM location_links WHERE active=1"):
            a, b, days = int(row[0]), int(row[1]), float(row[2])
            graph.setdefault(a, []).append((b, days))
            graph.setdefault(b, []).append((a, days))
    except sqlite3.OperationalError:
        pass
    for row in conn.execute("SELECT id,parent_location_id FROM locations WHERE parent_location_id IS NOT NULL"):
        graph.setdefault(int(row[0]), []).append((int(row[1]), 0.0))
        graph.setdefault(int(row[1]), []).append((int(row[0]), 0.0))
    return graph


def shortest_route(conn: sqlite3.Connection, start_location_id: int, end_location_id: int) -> tuple[int, list[int], list[str]] | None:
    if start_location_id == end_location_id:
        name = conn.execute("SELECT name FROM locations WHERE id=?", (start_location_id,)).fetchone()[0]
        return 0, [start_location_id], [str(name)]

    graph = _travel_graph(conn)
    pq: list[tuple[float, int]] = [(0.0, start_location_id)]
    dist = {start_location_id: 0.0}
    prev: dict[int, int] = {}
    while pq:
        cost, node = heapq.heappop(pq)
        if cost != dist.get(node):
            continue
        if node == end_location_id:
            break
        for nxt, weight in graph.get(node, []):
            new_cost = cost + weight
            if new_cost < dist.get(nxt, 1e18):
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
    days = math.ceil(dist[end_location_id] - 1e-9)  # whole days; local movement stays 0
    return int(days), path, names


_SETTLED = re.compile(r"settlement|pass|port|quay|city|inn|waystone|district|fortress|monastery|node", re.I)
_UNSETTLED = re.compile(r"region|area|sea|river|lake$|range|isles|island|country|approach|frontier|basin|sphere", re.I)


def nearest_on(conn: sqlite3.Connection, start_location_id: int | None, target_location_id: int) -> tuple[int, str] | None:
    """A region, sea, river, lake or range cannot be walked to: the nearest settlement, pass or port on it can.

    Returns (location id, how it was chosen) or None when the target is a place one can simply go to, or nothing on it is reachable."""
    row = conn.execute("SELECT name,kind FROM locations WHERE id=?", (target_location_id,)).fetchone()
    if row is None or start_location_id is None:
        return None
    name, kind = str(row[0]), str(row[1] or "")
    chain, cur = set(), target_location_id  # going into or out of the place he stands in is local movement
    for _ in range(8):
        r = conn.execute("SELECT parent_location_id FROM locations WHERE id=?", (cur,)).fetchone()
        cur = r[0] if r else None
        if cur is None:
            break
        chain.add(int(cur))
    up, cur = set(), int(start_location_id)
    for _ in range(8):
        r = conn.execute("SELECT parent_location_id FROM locations WHERE id=?", (cur,)).fetchone()
        cur = r[0] if r else None
        if cur is None:
            break
        up.add(int(cur))
    if int(start_location_id) in chain or target_location_id in up:
        return None
    if _SETTLED.search(kind) and not _UNSETTLED.search(kind.replace("mountain pass", "pass")):
        return None
    kids: set[int] = set()
    frontier = [target_location_id]
    while frontier:
        nxt = [int(r[0]) for r in conn.execute(f"SELECT id FROM locations WHERE parent_location_id IN ({','.join('?' * len(frontier))})", frontier)]
        frontier = [i for i in nxt if i not in kids]
        kids.update(frontier)
    pool = set(kids)
    ends = {int(r[0]) for r in conn.execute(
        f"SELECT to_location_id FROM travel_routes WHERE status IN ('open','restricted') AND from_location_id IN ({','.join('?' * (len(kids) + 1))})",
        [target_location_id, *kids])}
    ends |= {int(r[0]) for r in conn.execute(
        f"SELECT from_location_id FROM travel_routes WHERE status IN ('open','restricted') AND to_location_id IN ({','.join('?' * (len(kids) + 1))})",
        [target_location_id, *kids])}
    pool |= ends
    low = kind.lower()
    if low in ("sea", "lake", "river"):
        if low == "river":
            pool |= {int(r[0]) for r in conn.execute("SELECT from_location_id FROM travel_routes WHERE route_kind='river' AND status IN ('open','restricted')")}
            pool |= {int(r[0]) for r in conn.execute("SELECT to_location_id FROM travel_routes WHERE route_kind='river' AND status IN ('open','restricted')")}
        else:
            ports = [(int(r[0]), str(r[1])) for r in conn.execute("SELECT id,name FROM locations WHERE kind LIKE ?", ("%lake port%" if low == "lake" else "%port%",))]
            coastal = [i for i, n in ports if re.search(r"sea|coast|shore|bay|harbo", n, re.I)]
            pool |= set(coastal or [i for i, _ in ports])
    best = None
    for cand in sorted(pool):
        cr = conn.execute("SELECT name,kind FROM locations WHERE id=?", (cand,)).fetchone()
        if cr is None or cand == target_location_id or _UNSETTLED.search(str(cr[1] or "")) and not _SETTLED.search(str(cr[1] or "")):
            continue
        got = shortest_route(conn, int(start_location_id), cand)
        if got is None:
            continue
        if best is None or got[0] < best[0]:
            best = (got[0], cand, str(cr[0]), str(cr[1] or "place"))
    if best is None:
        return None
    return best[1], f"{name} is not a place one can go to; the nearest {best[3]} on it is {best[2]}, and the journey goes there."


def explain_no_route(conn: sqlite3.Connection, start_location_id: int | None, end_location_id: int) -> str:
    """Say in words why no route is known, so the GM can improvise within it rather than meet a flat refusal."""
    dest = conn.execute("SELECT name,kind FROM locations WHERE id=?", (end_location_id,)).fetchone()
    if dest is None:
        return "No such place is known."
    name, kind = str(dest[0]), str(dest[1])
    kinds = sorted({str(r[0]) for r in conn.execute(
        "SELECT route_kind FROM travel_routes WHERE status IN ('open','restricted') AND (from_location_id=? OR to_location_id=?)",
        (end_location_id, end_location_id))})
    if start_location_id is None:
        return f"The protagonist has no recorded position, so no route to {name} can be worked out."
    if not kinds:
        extra = " It lies across water, and no crossing is charted." if kind in ("island group", "sea", "lake") else ""
        return (f"No road, pass, river or sea route to {name} is charted from here or from anywhere else the engine knows."
                f"{extra} Any way there is unrecorded: a guide, a ship or a smuggler's path would have to be found in play.")
    way = " and ".join(kinds)
    return (f"{name} is joined to the known map only by {way} routes, and none of them connects to where the protagonist is. "
            f"The missing link between here and there is unrecorded; it would take a ferry, a ship or an unmapped road to bridge it.")


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

        locations = conn.execute("SELECT id,name,kind FROM locations ORDER BY length(name) DESC").fetchall()
        location = _named_match(list(locations), raw_text)
        if location is not None and any(v in low for v in ("travel", "go to", "head to", "ride to", "walk to", "leave for", "journey to", "set out for")):
            if current_location_id is None:
                return PlayerActionProposal(raw_text, "travel", 0.95, target_location_id=int(location["id"]), target_location_name=str(location["name"]), needs_interpretation=True, note="Player has no persisted current location.")
            route = shortest_route(conn, current_location_id, int(location["id"]))
            if route is None:
                return PlayerActionProposal(raw_text, "travel", 0.92, target_location_id=int(location["id"]), target_location_name=str(location["name"]), needs_interpretation=True, note=explain_no_route(conn, current_location_id, int(location["id"])))
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
            day, player_id, proposal.raw_text, proposal.action_type, proposal.target_actor_id,
            proposal.target_location_id, proposal.interaction_id, proposal.response_choice,
            json.dumps(asdict(proposal)), proposal.duration_days,
        ),
    )
    return int(cur.lastrowid)


def _record_result(conn: sqlite3.Connection, action_id: int, day: int, status: str, result: dict[str, Any]) -> None:
    conn.execute(
        "UPDATE player_actions SET day_resolved=?,status=?,result_json=? WHERE id=?",
        (day, status, json.dumps(result), action_id),
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
            counter_terms={"purpose": proposal.purpose, **({"changes": proposal.changes} if proposal.changes else {})} if proposal.response_choice == "counter" else None,
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
