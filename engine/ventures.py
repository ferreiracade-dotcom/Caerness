"""Ventures: something a backer pays to build, open or win, in stages, with parties, approvals and a weighed outcome.

A venture is a `civilian_projects` row (kind 'business') with side rows. Its kind comes from the package's business data
(stages with a length, a share of the budget, the approvals the stage needs and the sector whose drivers weigh it). Every
30 days or at the stage's end the backer pays the stage's share for the time gone by; a backer who cannot pay stalls the
stage, and the venture fails only when the stall runs past the kind's `stall_days`. At each stage's end the drivers are
weighed: well enough completes it, a little short makes it late, far short fails it on a seeded roll against the reading.
Where those lines fall is a package calibration figure, reported and never tuned. Pending approvals do not block (nothing
decides them yet) and the venture says so; a refused approval fails it. The Caerness project resolver never touches these rows.
"""
from __future__ import annotations

import json
import random
import sqlite3

from . import agreement_terms, business, business_data, business_drivers, design, ledger, places

PERIOD = 30
_EPS = 1e-6


ON_FINISH: list = []  # layers that hold a venture's result (the intake) register here: fn(conn, project_id, outcome, reason, day)


def _state(v: sqlite3.Row) -> dict:
    return json.loads(v["payoff_json"] or "{}")


def _save_state(conn: sqlite3.Connection, pid: int, st: dict) -> None:
    conn.execute("UPDATE venture_details SET payoff_json=? WHERE project_id=?", (json.dumps(st, sort_keys=True), int(pid)))


def _stage_approvals(conn: sqlite3.Connection, pid: int, stage: dict) -> None:
    for kind in stage.get("approvals") or []:
        conn.execute("INSERT INTO venture_approvals(project_id,approval_kind,status) VALUES (?,?, 'pending')", (int(pid), kind))


def start_venture(conn: sqlite3.Connection, *, kind: str, title: str, backer_ref: str, location_id: int | None,
                  budget_usd: float, day: int, parties: list[dict] | None = None, payoff: dict | None = None) -> int:
    """Begin a venture at its first stage; returns the project id. `payoff` overrides the kind's own."""
    spec = business_data.venture_kind(conn, kind)
    ledger.parse_holder(backer_ref, 0, conn)
    first = spec["stages"][0]
    bkind, _, braw = backer_ref.partition(":")
    pid = int(conn.execute(
        """INSERT INTO civilian_projects(title,project_kind,patron_actor_id,location_id,started_day,target_day,status,last_resolved_day,metadata_json)
           VALUES (?,'business',?,?,?,?,'active',?,?)""",
        (title, int(braw) if bkind == "person" else None, location_id, int(day), int(day) + int(sum(s["days"] for s in spec["stages"])),
         int(day), json.dumps({"venture": kind}, sort_keys=True))).lastrowid)
    state = {"payoff": dict(payoff) if payoff is not None else dict(spec.get("payoff") or {"kind": "none"}), "_last_day": int(day)}
    due = int(day) + int(first["days"])
    conn.execute(
        """INSERT INTO venture_details(project_id,venture_kind,backer_ref,budget_usd,stage_key,stage_started_day,stage_due_day,
                                       payoff_json,next_due_day) VALUES (?,?,?,?,?,?,?,?,?)""",
        (pid, kind, backer_ref, float(budget_usd), first["key"], int(day), due, json.dumps(state, sort_keys=True),
         min(int(day) + PERIOD, due)))
    for p in parties or []:
        ledger.parse_holder(p["ref"], 0, conn)
        tid = None
        if p.get("term"):
            tid = agreement_terms.add_term(conn, day=int(day), **p["term"])
        conn.execute("INSERT INTO venture_parties(project_id,role,party_ref,term_id) VALUES (?,?,?,?)",
                     (pid, p["role"], p["ref"], tid))
    _stage_approvals(conn, pid, first)
    return pid


def decide_approval(conn: sqlite3.Connection, approval_id: int, status: str, day: int, *, by_actor_id: int | None, reason: str) -> None:
    """Politics' hook: grant or refuse an approval a stage asked for."""
    if status not in ("granted", "refused", "not_needed"):
        raise ValueError(f"an approval is decided as granted, refused or not_needed, not {status!r}")
    conn.execute("UPDATE venture_approvals SET status=?,decided_day=?,decided_by_actor_id=?,reason=? WHERE id=?",
                 (status, int(day), by_actor_id, reason, int(approval_id)))


def next_ventures_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    r = conn.execute("SELECT MIN(next_due_day) FROM venture_details WHERE outcome IS NULL AND next_due_day>? AND next_due_day<=?",
                     (int(after_day), int(end_day))).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _sector_weights(conn: sqlite3.Connection, sector: str) -> dict[str, float]:
    """The demand weights a sector's archetypes share, averaged; empty when the package has none for it."""
    arch = [a for a in business.archetypes(conn).values() if a.get("sector") == sector]
    keys = sorted({k for a in arch for k in a["weights"]})
    return {k: sum(float(a["weights"].get(k, 0.0)) for a in arch) / len(arch) for k in keys} if arch else {}


def _finish(conn: sqlite3.Connection, pid: int, outcome: str, reason: str | None, day: int) -> None:
    conn.execute("UPDATE venture_details SET outcome=?,outcome_reason=?,next_due_day=? WHERE project_id=?",
                 (outcome, reason, int(day), int(pid)))
    conn.execute("UPDATE civilian_projects SET status=?,last_resolved_day=? WHERE id=?",
                 ("completed" if outcome == "completed" else "failed", int(day), int(pid)))
    for hook in ON_FINISH:
        hook(conn, int(pid), outcome, reason, int(day))


def _weakest(factors: dict) -> str:
    return min(factors, key=lambda k: factors[k].value)


def _pay_off(conn: sqlite3.Connection, v: sqlite3.Row, pay: dict, day: int) -> None:
    kind = pay.get("kind", "none")
    if kind == "money":
        ledger.receive(conn, ledger.parse_holder(v["backer_ref"], 0, conn), float(pay["amount_usd"]), purpose=f"payoff of venture {v['project_id']}")
    elif kind == "place":
        places.make_place(conn, day=int(day), **pay["place"])
    elif kind == "terms":
        for t in pay["terms"]:
            agreement_terms.add_term(conn, day=int(day), **t)


def _event(conn: sqlite3.Connection, v: sqlite3.Row, E: int) -> None:
    pid = int(v["project_id"])
    spec = business_data.venture_kind(conn, v["venture_kind"])
    cal = business_data.calibration(conn, "venture_outcome")
    stages = spec["stages"]
    idx = next(i for i, s in enumerate(stages) if s["key"] == v["stage_key"])
    st = stages[idx]
    state = _state(v)
    refused = conn.execute("SELECT approval_kind FROM venture_approvals WHERE project_id=? AND status='refused' ORDER BY id LIMIT 1", (pid,)).fetchone()
    if refused is not None:
        _finish(conn, pid, "failed", f"approval {refused[0]} refused", E)
        return
    backer = agreement_terms._resolve(conn, v["backer_ref"])
    if backer is None:
        _finish(conn, pid, "failed", "backer gone", E)
        return
    due, stalled, spent = int(v["stage_due_day"]), int(v["stalled_days"]), float(v["spent_usd"])
    last = int(state.get("_last_day", v["stage_started_day"]))
    prior = sum(float(s["cost_share"]) for s in stages[:idx])
    frac = min(1.0, max(0.0, 1.0 - (due - E) / float(st["days"])))
    need = max(0.0, float(v["budget_usd"]) * (prior + float(st["cost_share"]) * frac) - spent)
    pay = 0.0
    holder = ledger.parse_holder(backer, 0)
    if state.get("prepaid"):  # the backer paid it all at the door (the intake): nothing more is drawn, and nothing can run dry
        pay = need
    elif need > _EPS and ledger.balance(conn, holder) > _EPS:
        pay = float(ledger.spend(conn, holder, need, purpose=f"venture {pid} stage {st['key']}", allow_partial=True) or 0.0)
    spent += pay
    state.pop("_stall_reason", None)
    if need > _EPS and pay < need - _EPS:
        add = max(1, int(round((E - last) * (1.0 - pay / need))))
        stalled += add
        due += add
        state["_stall_reason"] = "backer short of money"
    else:
        stalled = 0
    state["_last_day"] = int(E)
    if stalled > int(spec["stall_days"]):
        conn.execute("UPDATE venture_details SET spent_usd=?,stalled_days=?,stage_due_day=? WHERE project_id=?", (spent, stalled, due, pid))
        _save_state(conn, pid, state)
        _finish(conn, pid, "failed", "backer short of money", E)
        return
    nxt = min(E + PERIOD, due)
    if E >= due:  # the stage's time is done: weigh it
        loc = conn.execute("SELECT location_id FROM civilian_projects WHERE id=?", (pid,)).fetchone()[0]
        f = business_drivers.reading(conn, "venture", pid, E, sector=st["driver_sector"], location_id=loc,
                                     demand_weights=_sector_weights(conn, st["driver_sector"]))
        business_drivers.record(conn, "venture", pid, E, f)
        t = business_drivers.total(f)
        late_before = state.get("_late_stage") == st["key"]
        outcome = "done"
        if t < float(cal["complete_at"]):
            if t >= float(cal["late_below"]) and not late_before:
                outcome = "late"
            elif t < float(cal["late_below"]):
                u = random.Random(f"{design.run_seed(conn)}:venture:{pid}:{st['key']}:{E}:fail").random()
                if u >= t / float(cal["late_below"]):
                    outcome = "failed"
        if outcome == "late":
            add = max(1, int(round(float(st["days"]) * (1.0 - t))))
            due += add
            state["_late_stage"] = st["key"]
            state["_late_reason"] = f"{_weakest(f)} held it back"
            nxt = min(E + PERIOD, due)
        elif outcome == "failed":
            conn.execute("UPDATE venture_details SET spent_usd=?,stalled_days=?,stage_due_day=? WHERE project_id=?", (spent, stalled, due, pid))
            _save_state(conn, pid, state)
            _finish(conn, pid, "failed", f"{_weakest(f)} was too weak ({f[_weakest(f)].source})", E)
            return
        else:
            state.pop("_late_stage", None)
            state.pop("_late_reason", None)
            if idx + 1 >= len(stages):
                conn.execute("UPDATE venture_details SET spent_usd=?,stalled_days=0,stage_due_day=? WHERE project_id=?", (spent, due, pid))
                _save_state(conn, pid, state)
                _pay_off(conn, conn.execute("SELECT * FROM venture_details WHERE project_id=?", (pid,)).fetchone(), state.get("payoff") or {"kind": "none"}, E)
                _finish(conn, pid, "completed", None, E)
                return
            nstage = stages[idx + 1]
            conn.execute("UPDATE venture_details SET stage_key=?,stage_started_day=?,stage_due_day=?,spent_usd=?,stalled_days=0,next_due_day=? WHERE project_id=?",
                         (nstage["key"], E, E + int(nstage["days"]), spent, min(E + PERIOD, E + int(nstage["days"])), pid))
            _stage_approvals(conn, pid, nstage)
            _save_state(conn, pid, state)
            return
    conn.execute("UPDATE venture_details SET spent_usd=?,stalled_days=?,stage_due_day=?,next_due_day=? WHERE project_id=?",
                 (spent, stalled, due, nxt, pid))
    _save_state(conn, pid, state)


def process_due_ventures(conn: sqlite3.Connection, day: int) -> dict:
    """Run every venture event up to `day`, earliest first. Returns {project_id: events}; empty for a package with no business data."""
    done: dict[int, int] = {}
    if business_data.load(conn) is None:
        return done
    while True:
        v = conn.execute("SELECT * FROM venture_details WHERE outcome IS NULL AND next_due_day<=? ORDER BY next_due_day,project_id LIMIT 1",
                         (int(day),)).fetchone()
        if v is None:
            return done
        _event(conn, v, int(v["next_due_day"]))
        done[int(v["project_id"])] = done.get(int(v["project_id"]), 0) + 1


def venture(conn: sqlite3.Connection, project_id: int) -> dict | None:
    v = conn.execute("SELECT * FROM venture_details WHERE project_id=?", (int(project_id),)).fetchone()
    if v is None:
        return None
    out = dict(v)
    state = _state(v)
    out["parties"] = [dict(r) for r in conn.execute("SELECT * FROM venture_parties WHERE project_id=? ORDER BY id", (int(project_id),))]
    out["approvals"] = [dict(r) for r in conn.execute("SELECT * FROM venture_approvals WHERE project_id=? ORDER BY id", (int(project_id),))]
    why = list(business_drivers.why(conn, "venture", int(project_id)))
    for a in out["approvals"]:
        if a["status"] == "pending":
            why.append(f"approval {a['approval_kind']} pending with the city")
    if state.get("_stall_reason") and v["outcome"] is None:
        why.append(f"stalled: {state['_stall_reason']}")
    if state.get("_late_reason") and v["outcome"] is None:
        why.append(f"late: {state['_late_reason']}")
    if v["outcome_reason"]:
        why.append(f"{v['outcome']}: {v['outcome_reason']}")
    out["why"] = why
    return out
