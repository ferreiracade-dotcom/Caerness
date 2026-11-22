"""The only module politics (P1) uses to reach what other layers built. Thin calls with argument mapping, no logic of its own.

Real names behind each seam (read at build time, 2026-11-22):
- the history intake core (I-1): `intake.take_in(conn, me, kind, details, call_id)` writes one `held_things` row; a lasting political
  outcome uses the registered `dated_fact` shape (not floor-backed: it is the finished record, so it bumps no depth gap).
- the shared business layer (BZ1): ventures are `ventures.start_venture` (kind from the package's business data, `venture_details`,
  `ventures.decide_approval`), and the agreements ledger is `agreement_terms` (`add_term`, `breach`, one row per obligation).
- information 1a: the delivery ledger (`texture._enter`, table `delivery_ledger`) is the push.
- information 1b: `claims.record` (holder_kind 'audience'), `claims.impression`, and the audience rows (`claims._aud`).
A name changing in any of those changes this file only.
"""
from __future__ import annotations

import json
import sqlite3

_NO_INTAKE = "the history intake core is not available (engine.intake could not be imported)"


def _intake():
    try:
        from . import intake
    except ImportError as e:  # pragma: no cover - exercised by a test that blocks the import
        raise RuntimeError(_NO_INTAKE) from e
    return intake


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


# ---- ventures (BZ1) ----------------------------------------------------------------------------------------------

def open_venture(conn, kind: str, backer: int, *, stages_key: str | None = None, due_day: int | None = None, meta: dict | None = None) -> int:
    """A venture of a package-declared kind, backed by a person. `meta` carries title, budget_usd, location_id, parties, payoff.
    `stages_key` is accepted for the plan's name and ignored: the kind IS the stages key in the package's business data."""
    from . import ventures
    meta = dict(meta or {})
    day = int(meta.pop("day", _day(conn)))
    return ventures.start_venture(
        conn, kind=kind, title=str(meta.pop("title", kind)), backer_ref=f"person:{int(backer)}", location_id=meta.pop("location_id", None),
        budget_usd=float(meta.pop("budget_usd", 0.0)), day=day, parties=meta.pop("parties", None), payoff=meta.pop("payoff", None))


def advance_venture(conn, venture_id: int, stage: str, day: int, outcome: dict | None = None) -> None:
    """Move a venture to a named stage, or (with `outcome` {'outcome','reason'}) finish it. The stage's own length is its window."""
    from . import business_data, ventures
    v = conn.execute("SELECT * FROM venture_details WHERE project_id=?", (int(venture_id),)).fetchone()
    if v is None:
        raise ValueError(f"venture {venture_id} does not exist")
    if outcome is not None:
        ventures._finish(conn, int(venture_id), str(outcome["outcome"]), outcome.get("reason"), int(day))
        return
    stages = business_data.venture_kind(conn, v["venture_kind"])["stages"]
    st = next((s for s in stages if s["key"] == stage), None)
    if st is None:
        raise ValueError(f"venture kind {v['venture_kind']!r} has no stage {stage!r}")
    due = int(day) + int(st["days"])
    conn.execute("UPDATE venture_details SET stage_key=?,stage_started_day=?,stage_due_day=?,stalled_days=0,next_due_day=? WHERE project_id=?",
                 (stage, int(day), due, min(int(day) + ventures.PERIOD, due), int(venture_id)))
    ventures._stage_approvals(conn, int(venture_id), st)


# ---- the agreements ledger (BZ1 terms) ---------------------------------------------------------------------------

def ledger_entry(conn, a: int, b: int, *, kind: str, terms: dict, due_day: int | None, day: int) -> int:
    """`a` owes `b`. A term with money is `terms['amount_usd']`; a favour is an entry of amount zero. The terms are kept in the
    purpose text as JSON; `terms['breach_word']` must be one of the package's breach words (default 'grudge')."""
    from . import agreement_terms
    terms = dict(terms or {})
    return agreement_terms.add_term(
        conn, ref_kind=kind, ref_id=terms.get("ref_id"), debtor_ref=f"person:{int(a)}", creditor_ref=f"person:{int(b)}",
        amount_usd=float(terms.get("amount_usd", 0.0)), first_due_day=int(due_day if due_day is not None else day), every_days=terms.get("every_days"),
        grace_days=int(terms.get("grace_days", 0)), breach_word=str(terms.get("breach_word", "grudge")),
        purpose=json.dumps({"kind": kind, **{k: v for k, v in terms.items() if k not in ("amount_usd", "every_days", "grace_days", "breach_word", "ref_id")}},
                           sort_keys=True), day=int(day))


def ledger_breach(conn, entry_id: int, by: int, day: int, why: str) -> None:
    """Run BZ1's breach path for the entry (the path is its breach word's)."""
    from . import agreement_terms
    agreement_terms.breach(conn, int(entry_id), int(day))
    conn.execute("UPDATE agreement_terms SET status='breached' WHERE id=? AND status='active'", (int(entry_id),))


def ledger_open(conn, actor: int, *, kind: str | None = None) -> list[sqlite3.Row]:
    """Active entries the person owes or is owed."""
    ref = f"person:{int(actor)}"
    q = "SELECT * FROM agreement_terms WHERE status='active' AND (debtor_ref=? OR creditor_ref=?)"
    args: list = [ref, ref]
    if kind is not None:
        q += " AND ref_kind=?"
        args.append(kind)
    return conn.execute(q + " ORDER BY id", args).fetchall()


# ---- the intake (I-1) --------------------------------------------------------------------------------------------

DATED_FACT = "dated_fact"


def _register_shape() -> None:
    intake = _intake()
    intake.register_shape(intake.Shape(DATED_FACT, (), (), None, False))


def hold_outcome(conn, *, what: str, people: list[int], dates: dict, consequences: list[str], day: int) -> int:
    """A lasting political outcome (a result, an appointment, an ordinance) as one held_things row at depth B. The consequences are
    kept in the row's agenda text: they are words for the GM, not rules a reader must understand (so no depth gap is raised)."""
    intake = _intake()
    if not people:
        raise ValueError("an outcome needs at least one person")
    _register_shape()
    dates = dict(dates or {})
    details = {"what": what, "people": [int(p) for p in people], "legality": "legal", "agenda": "; ".join(consequences)[:300],
               "start_day": int(dates.get("start_day", day)), "source": "politics"}
    for k in ("end_day", "real_date"):
        if dates.get(k) is not None:
            details[k] = dates[k]
    out = intake.take_in(conn, int(people[0]), DATED_FACT, details, f"politics:{what}:{int(day)}:{int(people[0])}")
    return int(out["held_thing_id"])


# ---- approvals (BZ1 ventures ask, politics answers) --------------------------------------------------------------

def approval_requests(conn, day: int) -> list[dict]:
    rows = conn.execute("""SELECT a.id,a.project_id,a.approval_kind,v.backer_ref,v.venture_kind,p.location_id FROM venture_approvals a
                           JOIN venture_details v ON v.project_id=a.project_id JOIN civilian_projects p ON p.id=a.project_id
                           WHERE a.status='pending' AND v.outcome IS NULL ORDER BY a.id""").fetchall()
    return [dict(r) for r in rows]


def answer_approval(conn, request_id: int, granted: bool, by_office_key: str, why: dict, day: int) -> None:
    from . import ventures
    by = why.get("by_actor_id")
    ventures.decide_approval(conn, int(request_id), "granted" if granted else "refused", int(day), by_actor_id=by,
                             reason=json.dumps({"office": by_office_key, **why}, sort_keys=True))


# ---- push (I1a) --------------------------------------------------------------------------------------------------

def push(conn, actor: int, kind: str, text: str, day: int, ref: dict) -> None:
    """Enter one item in the person's delivery ledger (entered once by its key)."""
    from . import texture
    key = f"politics:{kind}:{json.dumps(ref, sort_keys=True)}"
    texture._enter(conn, int(actor), key, kind, text, "politics", 1.0, int(day))


# ---- audiences and impressions (I1b) -----------------------------------------------------------------------------

def _electorate_key(conn) -> str:
    from . import bearing
    for key, df in (bearing.data(conn).get("audiences") or {}).items():
        if df.get("rule") == "voter_group":
            return key
    raise RuntimeError("the package declares no audience with the voter_group rule")


def group_audience(conn, group_id: int) -> dict:
    from . import claims
    row = conn.execute("SELECT group_key,words_json FROM voter_groups WHERE id=?", (int(group_id),)).fetchone()
    if row is None:
        raise ValueError(f"voter group {group_id} does not exist")
    return claims._aud(conn, _electorate_key(conn), int(group_id), f"the voters: {row['group_key']}")


def tell_group(conn, group_id: int, subject: int, text: str, *, source: str, confidence: float, valence: float, force: float = 0.0,
               costly: bool = False, day: int) -> int:
    from . import claims
    a = group_audience(conn, group_id)
    return claims.record(conn, int(subject), "audience", a["id"], text, source, confidence, valence, force, costly, day=int(day), check=False)


def group_regard(conn, group_id: int, subject: int, day: int) -> float:
    from . import claims
    return float(claims.impression(conn, group_audience(conn, group_id), int(subject), int(day))["regard"])
