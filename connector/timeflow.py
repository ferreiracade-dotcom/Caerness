"""advance: pass time through the engine's time-skip runner, capped per call."""
from __future__ import annotations

import json
import os
from pathlib import Path

from connector import store, undo
from engine import money_records
from engine.player import get_player
from engine.timeskip import prepare_time_skip, resolve_time_skip

MAX_ADVANCE_DAYS = 30  # hard ceiling; CAERNESS_MAX_ADVANCE_DAYS can only lower it
POLICIES = ("all", "meaningful", "critical_only")
SOMETHING = "something"  # stop at the first thing worth playing


def max_advance_days() -> int:
    from connector.settings import parse_max_advance_days

    return min(MAX_ADVANCE_DAYS, parse_max_advance_days(os.environ.get("CAERNESS_MAX_ADVANCE_DAYS")))


def _clip(text, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _focus(conn, purpose: str, focus, domain) -> list[dict]:
    """What the days are spent on: the stated focus, else the purpose, practised in the discipline it names."""
    from engine.free_operation import domain_for

    items = []
    if isinstance(focus, list) and focus:
        for i, f in enumerate(focus):
            f = f if isinstance(f, dict) else {"description": str(f)}
            items.append({"key": f.get("key") or f.get("domain") or f"focus_{i + 1}", "domain": f.get("domain") or domain_for(str(f.get("description") or "")),
                          "description": str(f.get("description") or purpose)[:200], "weight": float(f.get("weight", 1.0 / len(focus)))})
        return items
    dom = domain or domain_for(purpose)
    return [{"key": dom or "purpose", "domain": dom, "description": _clip(purpose, 200), "weight": 1.0}]


def _delegation(conn, me: int, purpose: str, delegate) -> dict:
    """Who minds what meanwhile: named people and the matters (obligations, kinds of dealing) they handle, kept on the skip."""
    out: dict = {"purpose": _clip(purpose, 200)}
    if not delegate:
        return out
    d = delegate if isinstance(delegate, dict) else {"to": delegate}
    out["to"] = d.get("to")
    out["note"] = _clip(d.get("note") or "", 200)
    out["delegated_obligation_ids"] = [int(x) for x in (d.get("obligations") or d.get("delegated_obligation_ids") or [])]
    out["delegated_interaction_types"] = [str(x) for x in (d.get("interaction_types") or d.get("delegated_interaction_types") or [])]
    if d.get("everything_routine"):  # the routine matters ride with the steward; only real trouble reaches him
        out["delegated_obligation_ids"] += [int(r[0]) for r in conn.execute(
            "SELECT id FROM obligations WHERE actor_id=? AND status='active' AND importance<=3", (me,))]
    return out


def recent(conn, limit: int = 3) -> list[dict]:
    """The latest skips, oldest first: what days have already passed and what they were spent on."""
    from engine import world_calendar
    from engine.world_package import current_package

    pkg = current_package(conn)
    rows = conn.execute("SELECT call_id,request_json,result_json FROM connector_calls WHERE tool='advance' ORDER BY rowid DESC LIMIT ?", (limit,))
    out = []
    for r in reversed(rows.fetchall()):
        req, res = json.loads(r["request_json"]), json.loads(r["result_json"])
        out.append({"call_id": r["call_id"], "from_day": res["day_started"], "to_day": res["day_ended"],
                    "to_date": world_calendar.format_date(pkg, res["day_ended"]), "purpose": _clip(req.get("purpose"), 120)})
    return out


def _db_file(conn) -> Path:
    return Path(conn.execute("PRAGMA database_list").fetchone()[2])


def _moved(conn, from_day: int, today: int) -> dict:
    """The refusal for a skip asked from a day the clock has left, with what already passed from there."""
    out = {"status": "refused", "reason": f"The clock has already moved: it is day {today}, not day {from_day}. Nothing was advanced.",
           "recent_advances": recent(conn)}
    for r in conn.execute("SELECT result_json FROM connector_calls WHERE tool='advance' ORDER BY rowid DESC"):
        done = json.loads(r[0])
        if done.get("day_started") == from_day:
            out["already_advanced"] = {k: done[k] for k in ("operation_id", "day_started", "day_ended", "summary", "noticed") if k in done}
            break
    return out


def advance(conn, call_id: str, days: int, purpose: str, *, focus=None, domain: str | None = None, delegate=None,
            interrupt: str | None = None, from_day: int | None = None) -> dict:
    if not isinstance(days, int) or days < 1:
        raise ValueError("days must be an integer >= 1")
    if interrupt is not None and interrupt not in (*POLICIES, SOMETHING):
        raise ValueError(f"interrupt must be one of {(*POLICIES, SOMETHING)}")

    def go() -> dict:
        player = get_player(conn)
        if not player:
            raise ValueError("No protagonist is set.")
        me = int(player["player_actor_id"])
        run_days = min(days, max_advance_days())
        delegation = _delegation(conn, me, purpose, delegate)
        if interrupt == SOMETHING:
            delegation["stop_on"] = SOMETHING
        run_id = prepare_time_skip(conn, me, run_days, focus=_focus(conn, purpose, focus, domain), delegation=delegation,
                                   interruption_policy="meaningful" if interrupt in (None, SOMETHING) else interrupt,
                                   max_chunk_days=7 if interrupt == SOMETHING else 30)
        heard = money_records.last_news(conn)
        run = resolve_time_skip(conn, run_id)
        start, end = int(run["start_day"]), int(run["actual_end_day"])
        interrupted = run["status"] == "interrupted"
        noticed = [_clip(r[0], 140) for r in conn.execute(
            """SELECT belief_text FROM knowledge WHERE knower_actor_id=? AND learned_day>? AND learned_day<=?
               ORDER BY learned_day DESC,id DESC LIMIT 8""", (me, start, end))]
        out = {"summary": _clip((run.get("summary") or {}).get("player_summary", ""), 300),
               "day_started": start, "day_ended": end, "elapsed_days": end - start,
               "interrupted": interrupted, "noticed": noticed, "operation_id": call_id}
        spent = [{"on": r["description"], "days": round(float(r["accumulated_days"]), 1)} for r in conn.execute(
            "SELECT description,accumulated_days FROM time_skip_focus_progress WHERE run_id=?", (run_id,)) if float(r["accumulated_days"]) > 0]
        if spent:
            out["spent_on"] = spent
        from engine import free_operation
        settled = free_operation.settle_due(conn, me)
        if settled:
            out["settled"] = settled
        paid = money_records.news_since(conn, heard)
        if paid:  # money that moved, or fell due, among what is his
            out["money"] = paid[:20]
            if len(paid) > 20:
                out["money_more"] = len(paid) - 20
        from engine import history
        due = history.due_prompt(conn, start, end)
        if due:  # what the real world had coming in these days: the GM looks up what his sphere touches and proposes it
            out["history_due"] = due
        if interrupted and run["interruptions"]:
            out["interruption"] = _clip(run["interruptions"][0]["reason"], 300)
        if days > end - start:  # an interruption also leaves the rest of the request undone
            out["remaining_days"] = days - (end - start)
        from engine import hearsay
        out.update(hearsay.material(conn, me, start, end))  # who it happened to, who told him, what is at stake, what is open
        waiting = hearsay.waiting(conn, me)
        if waiting:
            out["waiting_on_you"] = waiting
        if interrupt == SOMETHING and not interrupted:
            out["quiet"] = "Nothing worth stopping for reached them in these days."
        from engine import texture
        loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()
        tex = texture.block(conn, me, loc[0] if loc else None, [])
        if tex is not None:
            out["texture"] = tex
        return out

    point = None
    if not conn.execute("SELECT 1 FROM connector_calls WHERE call_id=?", (call_id,)).fetchone():  # a new skip, not a retry
        today = store._day(conn)
        if from_day is not None and int(from_day) != today:
            return _moved(conn, int(from_day), today)
        conn.commit()
        point = undo.take(_db_file(conn))
    try:
        return store.run_once(conn, call_id, "advance", {"days": days, "purpose": purpose, "focus": focus, "domain": domain,
                                                         "delegate": delegate, "interrupt": interrupt}, go)
    except BaseException:
        if point is not None:
            point.unlink(missing_ok=True)
        raise
