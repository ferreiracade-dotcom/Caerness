"""Who holds the posts of an organisation, decided by men (generic layer, driven by the package's data; names no role).

Three things live here; `org_coup` holds the violent half (plots, coups, civil war, a split) and calls `install_head` below.

  appointments  A vacant unit-leader post is filled by the head, a name for the books is put forward by the unit leader: each
                a weighed choice on the man's agenda (`fill_unit_leader_seat`, `propose_member`), one offer per man, weighed on
                trust, kin, favours owed, money offered, merit and fear, bent by the chooser's temperament (`appoint`).
  the heir      A head holds a succession preference (an open `heir` agenda row, formed from his temperament and his
                relationships, revised over time). It is private until he shows it (the leaders and the rivals then react).
                A head who names nobody leaves the contest open.
  the contest   A vacant head seat (any cause but a coup, see org_coup) opens a `contest` row that plays out over weeks: the
                customary roles stand (weighted) and any ambitious man with standing may; every backer (unit leaders and the roles
                the data lists) backs one candidate each week on trust, kin, debts, fear, money and the late head's heir; outside
                organisations' heads weigh in; the outcome is agreed, forced (fear), bought (money), a killing, or civil war.
                An acting head holds the seat meanwhile.

Everything is data (`orgs.json` kind `lifecycle`: `appoint`, `heir`, `contest`, ...); a number or the key of a design figure.
A kind with no `contest` data keeps the older formula in `org_lifecycle._promote`.
"""
from __future__ import annotations

import json
import math
import sqlite3

from . import ledger, org_motives, orgs
from .org_choices import register_agenda_action, register_executor
from .org_lifecycle import fill_post, mark_for_history, membership_text, on_head_vacancy, on_post_vacancy, on_return, on_unit_vacancy, on_week, role_level, unit_pool
from .orgs import add_agenda, clamp01, head_of, imposed, is_living, kind_rules, seat_of
from .relationships import adjust_relationship

WEEK = 7
_KIN = ("spouse", "parent_of", "grandparent_of", "sibling_of", "child_of")


# ---- reading the package's data ----

def lifecycle(conn: sqlite3.Connection, org: int) -> dict:
    return orgs.kind_rules(conn, int(org)).get("lifecycle") or {}


def block(conn: sqlite3.Connection, org: int, name: str) -> dict:
    return lifecycle(conn, org).get(name) or {}


def v(conn: sqlite3.Connection, spec) -> float:
    """A number as written, or the run's value of the design figure it names. A figure the data does not give fails loudly:
    no number is hidden in code."""
    if spec is None:
        raise KeyError("a figure this layer needs is missing from the package's lifecycle data")
    if isinstance(spec, (int, float)) and not isinstance(spec, bool):
        return float(spec)
    x = org_motives._fig(conn, str(spec))
    if x is None:
        raise KeyError(f"design figure {spec!r} is not in the package's figures")
    return float(x)


def lean(conn: sqlite3.Connection, org: int, x: float) -> float:
    """A trait bends a rate or a weight around a floor: floor + trait (the floor is the kind's lifecycle `trait_floor`)."""
    return v(conn, lifecycle(conn, org)["trait_floor"]) + x


def name_of(conn: sqlite3.Connection, actor_id: int | None) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone() if actor_id is not None else None
    return str(r[0]) if r else "someone"


def roll(conn: sqlite3.Connection, actor: int, day: int, stream: str) -> float:
    """The one point where a seeded draw is made (org_motives._roll, which tests patch)."""
    return org_motives._roll(conn, int(actor), int(day), stream)


def pick(conn: sqlite3.Connection, actor: int, day: int, stream: str, items: list[tuple], temp: float):
    """One of (item, score) drawn with weight exp(score / temp) from one seeded draw; None for an empty list."""
    if not items:
        return None
    top = max(s for _i, s in items)
    ws = [math.exp((s - top) / max(1e-6, temp)) for _i, s in items]
    x = roll(conn, actor, day, stream) * sum(ws)
    for (item, _s), w in zip(items, ws):
        x -= w
        if x < 0:
            return item
    return items[-1][0]


def _utility(conn: sqlite3.Connection, x: float) -> float:
    return float(org_motives._fig(conn, "org_choice_utility_base", default=8.0)) + float(org_motives._fig(conn, "org_choice_utility_span", default=10.0)) * clamp01(x)


def rel(conn: sqlite3.Connection, a: int | None, b: int | None):
    if a is None or b is None:
        return None
    return conn.execute("SELECT * FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(a), int(b))).fetchone()


def drive(conn: sqlite3.Connection, actor_id: int, trait: str, org: int | None = None) -> float:
    if trait in ("greed", "reliability"):
        r = conn.execute(f"SELECT {trait} FROM org_seats WHERE actor_id=? ORDER BY (org_actor_id=?) DESC, id LIMIT 1", (int(actor_id), int(org or 0))).fetchone()
    else:
        r = conn.execute(f"SELECT {trait} FROM actor_drives WHERE actor_id=?", (int(actor_id),)).fetchone()
    return 0.5 if r is None or r[0] is None else float(r[0])


def active_seat(conn: sqlite3.Connection, actor_id: int | None, org: int):
    if actor_id is None:
        return None
    s = seat_of(conn, int(actor_id), org)
    return s if s is not None and s["status"] == "active" and is_living(conn, int(actor_id)) else None


def meta_of(row) -> dict:
    return json.loads(row["metadata_json"] or "{}")


def save_meta(conn: sqlite3.Connection, row_id: int, meta: dict) -> None:
    conn.execute("UPDATE org_agenda SET metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), int(row_id)))


def put_row(conn: sqlite3.Connection, actor: int, kind: str, day: int, subject: int | None, meta: dict, subject_kind: str = "actor") -> int:
    """An agenda row that is state, not a task for the man: no speed-up, no review of him (the weekly passes read it)."""
    return int(conn.execute(
        "INSERT INTO org_agenda(actor_id,kind,due_day,subject_kind,subject_id,created_day,metadata_json) VALUES (?,?,?,?,?,?,?)",
        (int(actor), kind, int(day), subject_kind, subject, int(day), json.dumps(meta, sort_keys=True))).lastrowid)


def close_row(conn: sqlite3.Connection, row_id: int, day: int, **extra) -> None:
    if extra:
        r = conn.execute("SELECT metadata_json FROM org_agenda WHERE id=?", (int(row_id),)).fetchone()
        save_meta(conn, row_id, {**json.loads(r[0] or "{}"), **extra})
    conn.execute("UPDATE org_agenda SET status='resolved', resolved_day=? WHERE id=?", (int(day), int(row_id)))


def contest_orgs(conn: sqlite3.Connection) -> list[int]:
    return [int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_profiles ORDER BY org_actor_id") if block(conn, int(r[0]), "contest")]


# ---- weighing a man (appointments, the heir, backing in a contest) ----
TERMS: dict = {}


def term(name: str):
    def deco(fn):
        TERMS[name] = fn
        return fn
    return deco


@term("trust")
def _t_trust(conn, org, a, c, day, ctx, blk):
    r = rel(conn, a, c)
    return 0.0 if r is None else clamp01((float(r["trust"]) + float(r["loyalty"])) / 200.0)


@term("kin")
def _t_kin(conn, org, a, c, day, ctx, blk):
    return 1.0 if conn.execute(
        "SELECT 1 FROM typed_relationship_facts WHERE status='active' AND relation_type IN (%s) AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)) LIMIT 1"
        % ",".join("?" * len(_KIN)), (*_KIN, int(a), int(c), int(c), int(a))).fetchone() else 0.0


@term("favour")
def _t_favour(conn, org, a, c, day, ctx, blk):
    r = rel(conn, a, c)
    return 0.0 if r is None else clamp01(float(r["obligation"]) / 100.0)  # what he (the chooser) owes the man


@term("money")
def _t_money(conn, org, a, c, day, ctx, blk):
    """What the man could put up: his purse x the share he would offer x his ambition, against the scale."""
    m = blk.get("money") or {}
    return clamp01(ledger.balance(conn, ("person", int(c))) * v(conn, m.get("share")) * drive(conn, int(c), "ambition") / max(1e-9, v(conn, m.get("scale"))))


@term("merit")
def _t_merit(conn, org, a, c, day, ctx, blk):
    if ctx.get("merit") is not None:
        return ctx["merit"](c)
    s = seat_of(conn, int(c), org)
    if s is None:
        return 0.0
    m = blk.get("merit") or {}
    ws, wy = v(conn, m.get("w_standing")), v(conn, m.get("w_years"))
    yrs = 0.0 if s["inducted_day"] is None else min(1.0, max(0.0, (int(day) - int(s["inducted_day"])) / 365.0) / max(1e-9, v(conn, m.get("years_cap"))))
    return (ws * float(s["standing"]) + wy * yrs) / max(1e-9, ws + wy)


@term("fear")
def _t_fear(conn, org, a, c, day, ctx, blk):
    r = rel(conn, a, c)
    return 0.0 if r is None else clamp01(float(r["fear"]) / 100.0)  # he fears the man


@term("cowed")
def _t_cowed(conn, org, a, c, day, ctx, blk):
    r = rel(conn, c, a)
    return 0.0 if r is None else clamp01(float(r["fear"]) / 100.0)  # the man fears him


@term("heir")
def _t_heir(conn, org, a, c, day, ctx, blk):
    return 1.0 if ctx.get("heir") is not None and int(ctx["heir"]) == int(c) else 0.0


@term("own")
def _t_own(conn, org, a, c, day, ctx, blk):
    return 1.0 if int(a) == int(c) else 0.0


@term("customary")
def _t_customary(conn, org, a, c, day, ctx, blk):
    return clamp01((ctx.get("customary") or {}).get(int(c), 0.0))


@term("muscle")
def _t_muscle(conn, org, a, c, day, ctx, blk):
    """In a war: the men under him against the men of the organisation, and his temper."""
    if not ctx.get("war"):
        return 0.0
    total = conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND status='active'", (int(org),)).fetchone()[0] or 1
    under = len(_under(conn, org, int(c)))
    crew = v(conn, blk["muscle_crew"])
    return clamp01(crew * under / total * v(conn, blk["muscle_scale"]) + (1.0 - crew) * drive(conn, int(c), "aggression"))


@term("resentment")
def _t_resentment(conn, org, a, c, day, ctx, blk):
    r = rel(conn, a, c)
    return 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0)


@term("tainted")
def _t_tainted(conn, org, a, c, day, ctx, blk):
    return 1.0 if ctx.get("tainted") is not None and int(ctx["tainted"]) == int(c) else 0.0


def _under(conn: sqlite3.Connection, org: int, man: int) -> list[int]:
    """Everyone below him in the chain of command (active seats)."""
    seen: set[int] = set()
    todo = [int(man)]
    while todo:
        cur = todo.pop()
        for (a,) in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND superior_actor_id=?", (int(org), cur)):
            if int(a) not in seen and int(a) != int(man):
                seen.add(int(a))
                todo.append(int(a))
    return sorted(seen)


def weigh(conn: sqlite3.Connection, org: int, chooser: int, cand: int, day: int, blk: dict, ctx: dict | None = None, *, detail: bool = False):
    """How much the chooser is drawn to the candidate, 0..1: the weighted mean of the block's `weights` terms (each a design
    figure or number), less the block's `against` terms. The chooser's temperament bends each term's weight: `temperament`
    maps a term to a trait (a drive, or the seat's greed or reliability); the bend is `temperament.weight` x (trait - 0.5) x 2.
    With `detail`, returns (score, {term: its weighted contribution}) for the rationale."""
    ctx = ctx or {}
    temper = blk.get("temperament") or {}
    bend = v(conn, temper["weight"]) if temper else 0.0
    num = den = 0.0
    parts: dict[str, float] = {}
    for key, spec in (blk.get("weights") or {}).items():
        w = v(conn, spec)
        fn = TERMS.get(key)
        if w <= 0.0 or fn is None:
            continue
        if bend and temper.get(key):
            w *= max(0.1, 1.0 + bend * (drive(conn, int(chooser), temper[key], org) - 0.5) * 2.0)
        m = w * clamp01(fn(conn, org, int(chooser), int(cand), int(day), ctx, blk))
        parts[key] = m
        num += m
        den += w
    neg = 0.0
    for key, spec in (blk.get("against") or {}).items():
        fn = TERMS.get(key)
        if fn is not None and v(conn, spec) > 0.0:
            neg += v(conn, spec) * clamp01(fn(conn, org, int(chooser), int(cand), int(day), ctx, blk))
    score = clamp01(num / den - neg) if den else 0.0
    return (score, parts) if detail else score


def lead_terms(parts: dict[str, float], n: int = 2) -> str:
    return ", ".join(k for k, x in sorted(parts.items(), key=lambda kv: -kv[1])[:n] if x > 0)


# ---- appointments ----

def paid_for(conn: sqlite3.Connection, org: int, chooser: int, cand: int, day: int, blk: dict) -> float:
    """The man chosen pays what he offered (a share of his purse, by his ambition), through the ledger and the money rows;
    he is then owed the post and the chooser is owed nothing: the chooser's obligation to him falls, his rises."""
    m = blk.get("money") or {}
    if not m:
        return 0.0
    offer = ledger.balance(conn, ("person", int(cand))) * v(conn, m.get("share")) * drive(conn, int(cand), "ambition")
    if offer <= 0.0 or not m.get("flow"):
        return 0.0
    kinds = org_motives._sphere_data(conn)  # ledger kinds come from the package's organisation data
    from .world_package import org_rules, package_for
    lk = org_rules(package_for(conn))["ledger_kinds"][m["flow"]]
    paid = ledger.transfer(conn, ("person", int(cand)), ("person", int(chooser)), offer, flow_kind=lk, purpose="what he paid for the post", allow_partial=True)
    if paid > 0.0:
        conn.execute("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,line_id,amount,org_actor_id) VALUES (?,?,?,?,?,?,?)",
                     (int(day), m["flow"], int(cand), int(chooser), None, paid, int(org)))
    return paid


def after_choice(conn: sqlite3.Connection, org: int, chooser: int, chosen: int, passed: list[int], day: int, blk: dict) -> None:
    """The man chosen trusts and owes the chooser; the men passed over resent him (more if they stood higher in the weighing)."""
    if int(chosen) != int(chooser):  # a head who names himself has no one to thank
        adjust_relationship(conn, chosen, chooser, int(day), trust_delta=v(conn, blk.get("chosen_trust")), loyalty_delta=v(conn, blk.get("chosen_loyalty")),
                            obligation_delta=v(conn, blk.get("chosen_obligation")))
    for p in passed:
        if int(p) == int(chooser):
            continue
        adjust_relationship(conn, int(p), chooser, int(day), resentment_delta=v(conn, blk.get("passed_resentment")))
        imposed(conn, int(p))
    imposed(conn, int(chosen))


def appointment_offers(conn: sqlite3.Connection, head: int, item, day: int) -> list[dict] | None:
    """One offer for each man of the vacant unit the head could name; None when the package has no `appoint` data for the
    organisation (the caller then keeps the older single offer)."""
    meta = meta_of(item)
    org, unit = int(meta.get("org") or 0), int(item["subject_id"])
    blk = block(conn, org, "appoint")
    if not blk:
        return None
    pool = unit_pool(conn, unit, int(day))
    if not pool:
        return [{"kind": "fill_unit_leader_seat", "utility": _utility(conn, 1.0), "rationale": "No one in the unit is fit; the seat is filled as it can be.", "payload": {"unit_id": unit}}]
    out = []
    for r in pool:
        a = int(r["actor_id"])
        sc, parts = weigh(conn, org, int(head), a, int(day), blk, detail=True)
        lead = lead_terms(parts)
        out.append({"kind": "fill_unit_leader_seat", "utility": _utility(conn, sc), "target_actor_id": a,
                    "rationale": f"Names {name_of(conn, a)} to lead the unit ({sc:.2f}{', mostly ' + lead if lead else ''}).", "payload": {"unit_id": unit, "candidate": a, "org": org}})
    return out


def after_appointment(conn: sqlite3.Connection, org: int, chooser: int, chosen: int, unit: int, day: int) -> None:
    blk = block(conn, org, "appoint")
    if not blk or chosen is None:
        return
    paid_for(conn, org, chooser, chosen, int(day), blk)
    after_choice(conn, org, chooser, int(chosen), [int(r["actor_id"]) for r in unit_pool(conn, unit, int(day)) if int(r["actor_id"]) != int(chosen)], int(day), blk)


def seat_the_unit(conn: sqlite3.Connection, org: int, unit: int, day: int, *, deciding: int | None = None) -> bool:
    """Put the choice of a unit's leader on the deciding man's list (the head's, else the acting head's); False when no one
    can decide it."""
    head = deciding if deciding is not None else head_of(conn, org)
    if head is None or not is_living(conn, head) or not block(conn, org, "appoint"):
        return False
    if conn.execute("SELECT 1 FROM org_agenda WHERE kind='fill_unit_leader_seat' AND status='open' AND subject_id=? AND json_extract(metadata_json,'$.org')=? LIMIT 1", (int(unit), int(org))).fetchone():
        return True
    delay = int(v(conn, block(conn, org, "appoint").get("delay_days")))
    add_agenda(conn, head, "fill_unit_leader_seat", int(day) + delay, subject_kind="unit", subject_id=int(unit), metadata={"org": int(org)})
    return True


def _unit_vacancy(conn: sqlite3.Connection, org: int, seat, day: int, why: str) -> bool:
    """A unit leader's seat fell vacant: when the unit already has a living leader there is nothing to do; else the head's list."""
    if not block(conn, org, "appoint"):
        return False
    cur = conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (int(seat["unit_id"]),)).fetchone()
    role = kind_rules(conn, org).get("unit_leader")
    if cur is not None and cur[0] is not None and int(cur[0]) != int(seat["actor_id"]):
        s = active_seat(conn, int(cur[0]), org)
        if s is not None and s["role_key"] == role:
            return True
    return seat_the_unit(conn, org, int(seat["unit_id"]), int(day))


def stuck_units(conn: sqlite3.Connection, day: int) -> int:
    """A unit with no living leader and nothing on anyone's list gets the choice put to the head; an item that sat open past
    the fallback time (the head is gone or never answers) is closed and the unit takes the older best-man rule, so no unit is
    leaderless for ever."""
    from .org_lifecycle import fill_unit_leader
    n = 0
    for (org,) in conn.execute("SELECT org_actor_id FROM org_profiles ORDER BY org_actor_id").fetchall():
        blk = block(conn, int(org), "appoint")
        role = kind_rules(conn, int(org)).get("unit_leader")
        if not blk or not role:
            continue
        fall = int(v(conn, blk.get("fallback_days")))
        for u in conn.execute("SELECT id,leader_actor_id FROM org_units WHERE org_actor_id=? AND status='active'", (int(org),)).fetchall():
            s = active_seat(conn, u["leader_actor_id"], int(org)) if u["leader_actor_id"] is not None else None
            if s is not None and s["role_key"] == role:
                continue
            item = conn.execute("SELECT id,due_day FROM org_agenda WHERE kind='fill_unit_leader_seat' AND status='open' AND subject_id=? AND json_extract(metadata_json,'$.org')=?",
                                (int(u["id"]), int(org))).fetchone()
            if item is not None and int(day) - int(item["due_day"]) < fall:
                continue
            if item is None and conn.execute("SELECT 1 FROM org_seats WHERE unit_id=? AND status='active' LIMIT 1", (int(u["id"]),)).fetchone() is None:
                continue
            if item is None and seat_the_unit(conn, int(org), int(u["id"]), int(day)):
                n += 1
                continue
            if item is not None:
                close_row(conn, int(item["id"]), int(day))
            n += 1 if fill_unit_leader(conn, int(u["id"]), int(day), force=True) is not None else 0
    return n


# ---- posts below the head: the head chooses among the men the data names ----

def _post_vacancy(conn: sqlite3.Connection, org: int, role: str, day: int) -> bool:
    """A post with a succession in the data fell vacant: put the choice on the head's list (the acting head's while a contest runs).
    False when the package gives no `appoint` data, there is no head to choose, or the head is not living."""
    prefs = (lifecycle(conn, org).get("succession") or {}).get(role)
    head = head_of(conn, org)
    blk = block(conn, org, "appoint")
    if not prefs or not blk or head is None or not is_living(conn, head):
        return False
    if any(meta_of(r).get("role") == role for r in conn.execute("SELECT * FROM org_agenda WHERE kind='fill_post' AND status='open' AND subject_id=?", (int(org),))):
        return True
    add_agenda(conn, head, "fill_post", int(day) + int(v(conn, blk["delay_days"])), subject_kind="org", subject_id=int(org), metadata={"org": int(org), "role": role})
    return True


def post_offers(conn: sqlite3.Connection, head: int, item, day: int) -> list[dict]:
    """One offer for each man of the roles the data lists as successors to the vacant post, weighed on the `appoint` terms and
    on how far down the data's list his role is (`post_order_decay` per place)."""
    meta = meta_of(item)
    org, role = int(meta["org"]), str(meta["role"])
    blk = block(conn, org, "appoint")
    prefs = (lifecycle(conn, org).get("succession") or {}).get(role) or []
    decay = v(conn, blk["post_order_decay"])
    cust: dict[int, float] = {}
    for i, pref in enumerate(prefs):
        for r in orgs.members(conn, org, pref):
            if is_living(conn, int(r["actor_id"])) and int(r["actor_id"]) != int(head):
                cust.setdefault(int(r["actor_id"]), decay ** i)
    payload = {"org": org, "role": role}
    if not cust:
        return [{"kind": "fill_post", "utility": _utility(conn, 1.0), "rationale": f"No one is fit for the vacant {_label(conn, org, role)}'s post.", "payload": payload}]
    out = []
    for a in sorted(cust):
        sc, parts = weigh(conn, org, int(head), a, int(day), blk, {"customary": cust}, detail=True)
        lead = lead_terms(parts)
        out.append({"kind": "fill_post", "utility": _utility(conn, sc), "target_actor_id": a,
                    "rationale": f"Names {name_of(conn, a)} {_label(conn, org, role)} ({sc:.2f}{', mostly ' + lead if lead else ''}).", "payload": {**payload, "candidate": a}})
    return out


def execute_fill_post(conn: sqlite3.Connection, actor_id: int, kind: str, payload: dict, day: int) -> dict:
    from .org_lifecycle import _promote
    org, role = int(payload["org"]), str(payload["role"])
    if payload.get("agenda_id") is not None:
        orgs.resolve_agenda(conn, int(payload["agenda_id"]), int(day))
    cand = payload.get("candidate")
    new = _promote(conn, org, role, int(day), chosen=cand)
    if new is None:
        return {"summary": "No one could take the post.", "blocked": True}
    blk = block(conn, org, "appoint")
    if cand is not None and blk:
        prefs = (lifecycle(conn, org).get("succession") or {}).get(role) or []
        passed = [int(r["actor_id"]) for pref in prefs for r in orgs.members(conn, org, pref) if int(r["actor_id"]) not in (int(new), int(actor_id))]
        paid_for(conn, org, int(actor_id), int(new), int(day), blk)
        after_choice(conn, org, int(actor_id), int(new), passed, int(day), blk)
    return {"summary": f"{name_of(conn, actor_id)} named {name_of(conn, new)} {_label(conn, org, role)}."}


def stuck_posts(conn: sqlite3.Connection, day: int) -> int:
    """A vacant post nobody put on a head's list, or whose item sat unanswered past the fallback time (no head, or one who never
    answers), is filled by the data's formula so no post stays empty for ever."""
    from .org_lifecycle import _promote
    n = 0
    for (org,) in conn.execute("SELECT org_actor_id FROM org_profiles ORDER BY org_actor_id").fetchall():
        blk = block(conn, int(org), "appoint")
        succ = lifecycle(conn, int(org)).get("succession") or {}
        if not blk or not succ:
            continue
        fall = int(v(conn, blk["fallback_days"]))
        for item in conn.execute("SELECT * FROM org_agenda WHERE kind='fill_post' AND status='open' AND subject_id=?", (int(org),)).fetchall():
            if int(day) - int(item["due_day"]) >= fall:
                close_row(conn, int(item["id"]), int(day))
                n += 1 if _promote(conn, int(org), str(meta_of(item)["role"]), int(day)) is not None else 0
    return n


# ---- the heir ----

def heir_row(conn: sqlite3.Connection, head: int):
    return conn.execute("SELECT * FROM org_agenda WHERE actor_id=? AND kind='heir' AND status='open' ORDER BY id DESC LIMIT 1", (int(head),)).fetchone()


def heir_of(conn: sqlite3.Connection, org: int, head: int, *, shown_only: bool = False) -> int | None:
    """The man the head holds as his heir while he is living and still seated; None when he names nobody."""
    r = heir_row(conn, head)
    if r is None or (shown_only and not meta_of(r).get("shown")):
        return None
    return int(r["subject_id"]) if active_seat(conn, int(r["subject_id"]), org) is not None else None


def customary(conn: sqlite3.Connection, org: int, exclude: tuple = ()) -> dict[int, float]:
    """The men of the roles the data names as the usual successors, each with the role's weight."""
    out: dict[int, float] = {}
    for role, spec in (block(conn, org, "contest").get("customary") or {}).items():
        w = v(conn, spec)
        for s in orgs.members(conn, org, role):
            if int(s["actor_id"]) not in exclude and is_living(conn, int(s["actor_id"])):
                out[int(s["actor_id"])] = max(out.get(int(s["actor_id"]), 0.0), w)
    return out


def ambitious(conn: sqlite3.Connection, org: int, exclude: tuple = ()) -> list[int]:
    """Inducted men with standing and ambition enough to want the seat though no custom names them."""
    a = block(conn, org, "contest").get("ambitious") or {}
    if not a:
        return []
    return [int(r[0]) for r in conn.execute(
        """SELECT s.actor_id FROM org_seats s JOIN actor_drives d ON d.actor_id=s.actor_id WHERE s.org_actor_id=? AND s.status='active' AND s.inducted_day IS NOT NULL
             AND s.standing>=? AND d.ambition>=? ORDER BY s.actor_id""", (int(org), v(conn, a.get("standing")), v(conn, a.get("ambition")))).fetchall()
            if int(r[0]) not in exclude and is_living(conn, int(r[0]))]


def candidates(conn: sqlite3.Connection, org: int, exclude: tuple = ()) -> dict[int, float]:
    """Everyone who could hold the head's seat: the customary men and the ambitious (weight 0 for the latter's custom)."""
    out = customary(conn, org, exclude)
    for a in ambitious(conn, org, exclude):
        out.setdefault(a, 0.0)
    return out


def _age_factor(conn: sqlite3.Connection, head: int, blk: dict, day: int) -> float:
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (int(head),)).fetchone()
    if r is None or r[0] is None:
        return 0.5
    age = (int(day) - int(r[0])) / 365.0
    return clamp01((age - v(conn, blk.get("age_from"))) / max(1e-9, v(conn, blk.get("age_span"))))


def form_heir(conn: sqlite3.Connection, org: int, head: int, day: int, *, force: bool = False) -> int | None:
    """The head settles on a man (or on no one): the candidates weighed by him on the `heir` block; a man below the `min_score`
    is no one's choice. Returns the heir's id, None when he names nobody."""
    blk = block(conn, org, "heir")
    cust = candidates(conn, org, exclude=(int(head),))
    scores = [(c, weigh(conn, org, head, c, int(day), blk, {"customary": cust})) for c in sorted(cust)]
    old = heir_row(conn, head)
    if old is not None:
        close_row(conn, int(old["id"]), int(day))
    scores = [(c, s) for c, s in scores if s >= v(conn, blk.get("min_score"))]
    chosen = pick(conn, head, int(day), "heir_pick", scores, v(conn, blk.get("pick_temp")))
    if chosen is None:
        return None
    shown = bool(old is not None and int(old["subject_id"]) == chosen and meta_of(old).get("shown"))
    put_row(conn, head, "heir", int(day), int(chosen), {"org": int(org), "shown": shown, "formed": int(day), "score": dict(scores).get(chosen)})
    return int(chosen)


def show_heir(conn: sqlite3.Connection, org: int, head: int, day: int) -> None:
    """The head makes his choice visible (he tells the unit leaders): they trust the heir more or less by their own temper, the
    men who would have wanted the seat are passed over, and all of them are looked at again."""
    r = heir_row(conn, head)
    if r is None:
        return
    blk = block(conn, org, "heir")
    heir = int(r["subject_id"])
    save_meta(conn, int(r["id"]), {**meta_of(r), "shown": True, "shown_day": int(day)})
    cust = candidates(conn, org, exclude=(int(head), heir))
    for b in backers(conn, org):
        if b in (heir, head):
            continue
        adjust_relationship(conn, b, heir, int(day), trust_delta=v(conn, blk.get("show_trust")) * lean(conn, org, drive(conn, b, "loyalty")),
                            respect_delta=v(conn, blk.get("show_respect")))
        if b in cust:
            adjust_relationship(conn, b, heir, int(day), resentment_delta=v(conn, blk.get("show_resentment")) * lean(conn, org, drive(conn, b, "ambition")))
            imposed(conn, b)
    imposed(conn, heir)
    mark_for_history(conn, head, f"showed {name_of(conn, heir)} as his heir", int(day))


def _heirs(conn: sqlite3.Connection, day: int) -> dict:
    formed = shown = 0
    for org in contest_orgs(conn):
        head = head_of(conn, org)
        blk = block(conn, org, "heir")
        if head is None or not blk or not is_living(conn, head):
            continue
        row = heir_row(conn, head)
        if row is not None and active_seat(conn, int(row["subject_id"]), org) is None:
            close_row(conn, int(row["id"]), int(day), why="gone")
            row = None
        floor = v(conn, blk.get("age_floor"))
        age = floor + (1.0 - floor) * _age_factor(conn, head, blk, day)
        if row is None:
            if roll(conn, head, int(day), "heir_form") < v(conn, blk.get("form_week")) * age and form_heir(conn, org, head, int(day)) is not None:
                formed += 1
            row = heir_row(conn, head)
            if row is None:
                continue
        if roll(conn, head, int(day), "heir_revise") < v(conn, blk.get("revise_week")):
            before = int(row["subject_id"])
            if form_heir(conn, org, head, int(day)) not in (None, before):
                formed += 1
            row = heir_row(conn, head)
            if row is None:
                continue
        if not meta_of(row).get("shown") and roll(conn, head, int(day), "heir_show") < v(conn, blk.get("show_week")) * age:
            show_heir(conn, org, head, int(day))
            shown += 1
    return {"heirs": formed, "heirs_shown": shown}


# ---- the contest ----

def backers(conn: sqlite3.Connection, org: int) -> list[int]:
    """The men who back a candidate: the unit leaders and the roles the data lists, living and seated."""
    blk = block(conn, org, "contest")
    roles = set(blk.get("backer_roles") or []) | {kind_rules(conn, org).get("unit_leader")}
    return [int(s["actor_id"]) for r in sorted(r for r in roles if r) for s in orgs.members(conn, org, r) if is_living(conn, int(s["actor_id"]))]


def backer_weight(conn: sqlite3.Connection, org: int, b: int, blk: dict) -> float:
    """A backer counts for more the more men stand behind him (his crew), up to the data's cap."""
    return 1.0 + v(conn, blk.get("crew_weight")) * min(1.0, len(_under(conn, org, b)) / max(1e-9, v(conn, blk.get("crew_scale"))))


def _label(conn: sqlite3.Connection, org: int, role: str) -> str:
    return str((kind_rules(conn, org).get("labels") or {}).get(role, role))


def _cause(conn: sqlite3.Connection, late: int, org: int, why: str) -> dict:
    """How the head went: killed by an insider, killed by someone of another organisation, or none of those (law, illness,
    accident, leaving, custody)."""
    row = conn.execute("SELECT subject_id FROM org_agenda WHERE kind='killed_by' AND actor_id=? ORDER BY id DESC LIMIT 1", (int(late),)).fetchone()
    killer = int(row[0]) if row is not None and row[0] is not None else None
    if killer is None:
        h = conn.execute("SELECT json_extract(metadata_json,'$.offender_actor_id') FROM harm_incidents WHERE actor_id=? AND json_extract(metadata_json,'$.offender_actor_id') IS NOT NULL "
                         "ORDER BY id DESC LIMIT 1", (int(late),)).fetchone()
        killer = int(h[0]) if h is not None and h[0] is not None else None
    if killer is None or why != "dead":
        return {"kind": why, "killer": None}
    inside = conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (killer, int(org))).fetchone() is not None
    return {"kind": "killed_inside" if inside else "killed_outside", "killer": killer}


def set_acting(conn: sqlite3.Connection, org: int, man: int, late: int, day: int, contest_id: int | None) -> None:
    """The man holds the head's seat while the contest runs: his seat takes the head role (his unit and lines stay), the men who
    answered to the late head answer to him, and a marker remembers the role he held."""
    rules = kind_rules(conn, org)
    s = seat_of(conn, man, org)
    put_row(conn, man, "acting_head", int(day), int(org), {"org": int(org), "prior_role": s["role_key"], "prior_superior": s["superior_actor_id"], "late": int(late), "contest": contest_id}, "org")
    conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=NULL WHERE id=?", (rules["head"], int(s["id"])))
    conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND status='active' AND superior_actor_id=? AND actor_id<>?", (man, int(org), int(late), man))
    membership_text(conn, org, man, rules["head"])
    lv = role_level(conn, org, rules["head"])
    if lv is not None:
        orgs.set_level(conn, man, lv, int(day), org)
    imposed(conn, man)
    mark_for_history(conn, man, f"took the {_label(conn, org, rules['head'])}'s seat for now", int(day))


def acting_marker(conn: sqlite3.Connection, org: int):
    return conn.execute("SELECT * FROM org_agenda WHERE kind='acting_head' AND status='open' AND subject_id=? ORDER BY id DESC LIMIT 1", (int(org),)).fetchone()


def step_back(conn: sqlite3.Connection, org: int, marker, new_head: int | None, day: int) -> None:
    """The acting man goes back to the role he held; the men who answered to him answer to the head."""
    m = meta_of(marker)
    a = int(marker["actor_id"])
    s = seat_of(conn, a, org)
    if s is not None and s["status"] == "active" and new_head != a:
        conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=? WHERE id=?", (m["prior_role"], new_head, int(s["id"])))
        membership_text(conn, org, a, m["prior_role"])
        lv = role_level(conn, org, m["prior_role"])
        if lv is not None:
            orgs.set_level(conn, a, lv, int(day), org)
        if new_head is not None:
            conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND status='active' AND superior_actor_id=? AND actor_id NOT IN (?,?)", (new_head, int(org), a, new_head, a))
        imposed(conn, a)
    close_row(conn, int(marker["id"]), int(day))


def install_head(conn: sqlite3.Connection, org: int, man: int, day: int, how: str) -> int:
    """The man holds the head's seat: any acting man steps back, the men who answered to the late head and the acting man answer
    to him; if he led a unit it is put to him to name its leader, and the post he left is filled as the data says."""
    rules = kind_rules(conn, org)
    head_role, unit_role = rules["head"], rules.get("unit_leader")
    seat = seat_of(conn, man, org)
    marker = acting_marker(conn, org)
    prior_role = None
    if marker is not None:
        if int(marker["actor_id"]) == int(man):
            prior_role = meta_of(marker)["prior_role"]
            close_row(conn, int(marker["id"]), int(day))
        else:
            step_back(conn, org, marker, int(man), int(day))
    late_ids = [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key=? AND status<>'active'", (int(org), head_role))]
    if seat["role_key"] != head_role:
        prior_role = seat["role_key"]
        if prior_role == unit_role and seat["unit_id"]:
            seat_the_unit(conn, org, int(seat["unit_id"]), int(day), deciding=int(man))
            conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=NULL WHERE id=?", (head_role, int(seat["id"])))
        else:
            conn.execute("UPDATE org_seats SET role_key=?, unit_id=NULL, superior_actor_id=NULL WHERE id=?", (head_role, int(seat["id"])))
    else:
        conn.execute("UPDATE org_seats SET superior_actor_id=NULL WHERE id=?", (int(seat["id"]),))
    if late_ids:
        conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND status='active' AND superior_actor_id IN (%s) AND actor_id<>?" % ",".join("?" * len(late_ids)),
                     (int(man), int(org), *late_ids, int(man)))
    membership_text(conn, org, man, head_role)
    lv = role_level(conn, org, head_role)
    if lv is not None:
        orgs.set_level(conn, man, lv, int(day), org)
    imposed(conn, man)
    for (sub,) in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND superior_actor_id=?", (int(org), int(man))).fetchall():
        imposed(conn, int(sub))
    mark_for_history(conn, man, f"rose to {_label(conn, org, head_role)}", int(day))
    if prior_role and prior_role != head_role:
        fill_post(conn, org, prior_role, int(day))
    for late in late_ids:
        r = heir_row(conn, late)
        if r is not None:
            close_row(conn, int(r["id"]), int(day), succeeded_by=int(man), how=how)
    return int(man)


def _acting_choice(conn: sqlite3.Connection, org: int, cust: dict[int, float], blk: dict) -> int:
    """Who holds the seat meanwhile when no heir is shown: the man with the heaviest custom, then standing (`acting_standing`)."""
    w = v(conn, blk.get("acting_standing"))
    return int(sorted(cust.items(), key=lambda kv: (-(kv[1] + w * float(seat_of(conn, kv[0], org)["standing"])), kv[0]))[0][0])


def open_contest(conn: sqlite3.Connection, org: int, seat, day: int, why: str) -> bool:
    """The head's seat is vacant: a contest opens (False when the package has no contest data, or nobody could stand: the
    older formula then fills the seat)."""
    blk = block(conn, org, "contest")
    late = int(seat["actor_id"])
    if not blk:
        return False
    cust = candidates(conn, org, exclude=(late,))
    if not cust:
        return False
    live = conn.execute("SELECT * FROM org_agenda WHERE kind='contest' AND status='open' AND actor_id=? ORDER BY id DESC LIMIT 1", (int(org),)).fetchone()
    if live is not None:  # the acting head went too: the contest goes on with a new acting man
        mk = acting_marker(conn, org)
        if mk is not None and int(mk["actor_id"]) == late:
            close_row(conn, int(mk["id"]), int(day))
        set_acting(conn, org, _acting_choice(conn, org, cust, blk), late, int(day), int(live["id"]))
        return True
    cause = _cause(conn, late, org, why)
    heir = heir_of(conn, org, late)
    heir_r = heir_row(conn, late)
    shown = bool(heir_r is not None and meta_of(heir_r).get("shown"))
    meta = {"org": int(org), "late": late, "opened": int(day), "cause": cause["kind"], "killer": cause["killer"], "heir": heir, "heir_shown": shown, "stood": [],
            "picks": {}, "forced": 0, "bought": 0, "killed": 0, "war": cause["kind"] == "killed_outside"}
    cid = put_row(conn, int(org), "contest", int(day), late, meta, "actor")
    if cause["kind"] == "killed_inside":
        from . import org_coup
        if org_coup.coup(conn, org, late, int(cause["killer"]), cid, int(day)):
            return True
    acting = heir if heir is not None and shown else _acting_choice(conn, org, cust, blk)
    set_acting(conn, org, int(acting), late, int(day), cid)
    for a in {int(acting)} | ({heir} if heir is not None and shown else set()):
        imposed(conn, a)
    if cause["kind"] == "killed_outside":
        from .org_happenings import killed_across
        killed_across(conn, int(cause["killer"]), late, [seat], int(day))
    mark_for_history(conn, late, f"left the {_label(conn, org, kind_rules(conn, org)['head'])}'s seat vacant", int(day))
    return True


def _stand(conn: sqlite3.Connection, org: int, meta: dict, blk: dict, day: int, cid: int) -> dict[int, float]:
    """Who stands this week: those who stood before and are still living and seated, the acting man, the shown heir, and any
    customary or ambitious man whose draw passes (his custom weight and his ambition)."""
    cust = candidates(conn, org, exclude=(int(meta["late"]),))
    marker = acting_marker(conn, org)
    must = {int(marker["actor_id"])} if marker is not None else set()
    if meta.get("heir") is not None and meta.get("heir_shown"):
        must.add(int(meta["heir"]))
    stood = {a for a in meta["stood"] if active_seat(conn, a, org) is not None} | {a for a in must if active_seat(conn, a, org) is not None}
    for a, w in sorted(cust.items()):
        if a in stood:
            continue
        amb = drive(conn, a, "ambition")
        want = (w if w > 0.0 else v(conn, blk["ambitious"]["stand"])) * lean(conn, org, amb)
        if roll(conn, a, int(day), f"stand:{cid}") < v(conn, blk.get("stand_week")) * want:
            stood.add(a)
    meta["stood"] = sorted(stood)
    return {a: cust.get(a, 0.0) for a in stood}


def _ctx(meta: dict, cust: dict[int, float], tainted: int | None = None) -> dict:
    return {"heir": meta.get("heir"), "customary": cust, "war": bool(meta.get("war")), "tainted": tainted}


def outside_heads(conn: sqlite3.Connection, org: int) -> list[int]:
    """The heads of the other organisations of the same kind."""
    kind = conn.execute("SELECT org_kind FROM org_profiles WHERE org_actor_id=?", (int(org),)).fetchone()[0]
    return [int(r[0]) for r in conn.execute(
        "SELECT s.actor_id FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id WHERE s.org_actor_id<>? AND p.org_kind=? AND s.role_key=? AND s.status='active' ORDER BY s.actor_id",
        (int(org), kind, kind_rules(conn, org)["head"]))]


def outside_liking(conn: sqlite3.Connection, head: int, cand: int) -> float:
    """How much another outfit's head likes a man: trust and respect less resentment, 0..1."""
    r = rel(conn, int(head), int(cand))
    return 0.0 if r is None else clamp01((float(r["trust"]) + float(r["respect"])) / 200.0 - float(r["resentment"]) / 200.0)


def early(conn: sqlite3.Connection, weeks: float, scale, floor) -> float:
    """How far a young matter has got: `floor` at its start, rising to 1 as the weeks pass (1 - exp(-weeks / scale)). A quick
    agreement, war or settlement is unlikely in the first days but never impossible."""
    f = v(conn, floor)
    return f + (1.0 - f) * (1.0 - math.exp(-max(0.0, weeks) / v(conn, scale)))


def men_lost(conn: sqlite3.Connection, org: int, since: int) -> int:
    """Men of the organisation killed since a day (the `killed_by` rows)."""
    return int(conn.execute("SELECT COUNT(*) FROM org_agenda a WHERE a.kind='killed_by' AND a.created_day>=? AND EXISTS "
                            "(SELECT 1 FROM org_seats s WHERE s.actor_id=a.actor_id AND s.org_actor_id=?)", (int(since), int(org))).fetchone()[0])


def law_heat(conn: sqlite3.Connection, org: int) -> int:
    """Open cases against the organisation's inducted men."""
    return int(conn.execute("SELECT COUNT(*) FROM crime_reports r JOIN org_seats s ON s.actor_id=r.offender_actor_id WHERE r.status='open' AND s.org_actor_id=? AND s.inducted_day IS NOT NULL",
                            (int(org),)).fetchone()[0])


def pressure(conn: sqlite3.Connection, org: int, press: dict, *, opened: int, day: int, typical, spent: float, leaders: list[int]) -> float:
    """The weighted mean (0..1) of what presses a matter to an end: weariness (1 - exp(-weeks / typical): the typical duration only
    shapes the curve and ends nothing), the money spent, the men lost since it began, law heat, the other outfits' heads who like a
    front-runner (they want it settled), and the leaders' even tempers. Each weight and scale is the data's."""
    w = press["weights"]
    weeks = (int(day) - int(opened)) / WEEK
    heads = outside_heads(conn, org)
    base = v(conn, press["outside_base"])  # the neighbours' own interest in a settled house, whoever they like
    parts = {"weary": 1.0 - math.exp(-weeks / v(conn, typical)),
             "money": clamp01(float(spent) / v(conn, press["money_scale"])),
             "men": clamp01(men_lost(conn, org, opened) / v(conn, press["men_scale"])),
             "law": clamp01(law_heat(conn, org) / v(conn, press["heat_scale"])),
             "outside": (sum(clamp01(base + max(outside_liking(conn, h, c) for c in leaders)) for h in heads) / len(heads)) if heads and leaders else 0.0,
             "temper": 1.0 - (sum(drive(conn, c, "aggression") for c in leaders) / len(leaders) if leaders else 0.0)}
    den = sum(v(conn, w[k]) for k in parts)
    return sum(v(conn, w[k]) * x for k, x in parts.items()) / den


def tally(conn: sqlite3.Connection, org: int, meta: dict, blk: dict, cands: dict[int, float], day: int, cid: int) -> dict[int, float]:
    """Each backer backs one candidate (weighed; the one he backed last week is favoured by `stick`); the heads of other
    organisations add a voice for the man they like. Returns each candidate's share of the backing, 0..1."""
    ctx = _ctx(meta, cands, meta.get("tainted"))
    picks, weight = {}, {}
    for b in backers(conn, org):
        w = backer_weight(conn, org, b, blk)
        sc = [(c, weigh(conn, org, b, c, int(day), blk, ctx) + (v(conn, blk.get("stick")) if meta["picks"].get(str(b)) == c else 0.0)) for c in sorted(cands)]
        got = pick(conn, b, int(day), f"back:{cid}", sc, v(conn, blk.get("pick_temp")))
        if got is not None:
            picks[str(b)], weight[b] = got, w
    out_w = v(conn, blk["outside"]["weight"])
    voice, bs = None, v(conn, blk["outside"]["min"])
    for oh in outside_heads(conn, org):
        for c in cands:
            x = outside_liking(conn, oh, c)
            if x > bs:
                voice, bs = c, x
    total = sum(weight.values()) + (out_w if voice is not None else 0.0)
    meta["picks"] = picks
    share = {c: 0.0 for c in cands}
    for b, c in picks.items():
        share[c] += weight[int(b)] / total if total else 0.0
    if voice is not None and total:
        share[voice] += out_w / total
    return share


def _lean(conn: sqlite3.Connection, org: int, meta: dict, blk: dict, share: dict[int, float], day: int, cid: int) -> None:
    """The leaders lean on the men who back someone else: a hard man frightens them, a rich man pays them; the effect is on the
    relationships the next week's weighing reads (fear, obligation)."""
    ranked = sorted(share.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
    for c, _s in ranked:
        swing = [int(b) for b, p in meta["picks"].items() if int(p) != c and int(b) != c]
        if not swing:
            continue
        b = swing[int(roll(conn, c, int(day), f"lean_who:{cid}") * len(swing)) % len(swing)]
        if roll(conn, c, int(day), f"force:{cid}") < v(conn, blk.get("force_week")) * drive(conn, c, "aggression"):
            adjust_relationship(conn, b, c, int(day), fear_delta=v(conn, blk.get("force_fear")), resentment_delta=v(conn, blk.get("force_resentment")))
            meta["forced"] += 1
            meta.setdefault("forced_by", []).append(c)
            imposed(conn, b)
        if roll(conn, c, int(day), f"bribe:{cid}") < v(conn, blk.get("bribe_week")) * drive(conn, c, "ambition"):
            pay = ledger.balance(conn, ("person", c)) * v(conn, blk.get("bribe_share"))
            if pay > 0.0:
                from .world_package import org_rules, package_for
                lk = org_rules(package_for(conn))["ledger_kinds"][blk["bribe_flow"]]
                got = ledger.transfer(conn, ("person", c), ("person", b), pay, flow_kind=lk, purpose="what he paid for a man's backing", allow_partial=True)
                if got > 0.0:
                    adjust_relationship(conn, b, c, int(day), obligation_delta=v(conn, blk.get("bribe_obligation")))
                    meta["bought"] += 1
                    meta["spent"] = float(meta.get("spent", 0.0)) + got
                    meta.setdefault("bought_by", []).append(c)
                    imposed(conn, b)


def _finish_contest(conn: sqlite3.Connection, row, meta: dict, winner: int | None, outcome: str, day: int) -> None:
    org = int(meta["org"])
    if winner is not None:
        loser_backers = [int(b) for b, p in meta["picks"].items() if int(p) != winner]
        blk = block(conn, org, "contest")
        for b in loser_backers:
            if b != winner:
                adjust_relationship(conn, b, winner, int(day), resentment_delta=v(conn, blk.get("lose_resentment")))
        for b in [int(b) for b, p in meta["picks"].items() if int(p) == winner and int(b) != winner]:
            adjust_relationship(conn, b, winner, int(day), loyalty_delta=v(conn, blk.get("win_loyalty")))
        install_head(conn, org, winner, int(day), outcome)
        for b in meta["picks"]:
            imposed(conn, int(b))  # backers of the winner and of the men who lost: all looked at again
        rv = lifecycle(conn, org).get("rivals")
        for rival in meta.get("stood", []):
            if int(rival) != int(winner) and rv and active_seat(conn, int(rival), org) is not None:
                add_agenda(conn, int(winner), "rival", int(day) + int(v(conn, rv["delay_days"])), subject_kind="actor", subject_id=int(rival), metadata={"org": org, "rival": int(rival), "how": outcome})
    close_row(conn, int(row["id"]), int(day), **{**meta, "outcome": outcome, "winner": winner, "closed": int(day), "weeks": (int(day) - int(meta["opened"])) // WEEK})


def agree_chance(conn: sqlite3.Connection, org: int, meta: dict, blk: dict, ranked: list, day: int) -> float:
    """The chance that the contest ends in agreement this week: the weekly figure x the early factor (thin while the matter is
    young) x the front-runner's clarity (his share and his lead) mixed with the pressure to end it (weariness, money, men lost, law
    heat, outside pressure, even tempers). Never zero for long: weariness only rises."""
    ag = blk["agree"]
    s1 = ranked[0][1]
    s2 = ranked[1][1] if len(ranked) > 1 else 0.0
    clear = v(conn, ag["w_share"]) * s1 + (1.0 - v(conn, ag["w_share"])) * clamp01((s1 - s2) / v(conn, ag["lead_scale"]))
    press = pressure(conn, org, ag["press"], opened=meta["opened"], day=day, typical=ag["typical_weeks"], spent=float(meta.get("spent", 0.0)), leaders=[c for c, _s in ranked[:2]])
    weeks = (int(day) - int(meta["opened"])) / WEEK
    return v(conn, ag["week"]) * early(conn, weeks, ag["early_weeks"], ag["early_floor"]) * clamp01(v(conn, ag["w_clear"]) * clear + v(conn, ag["w_press"]) * press)


def tick_contest(conn: sqlite3.Connection, row, day: int) -> str | None:
    """One week of one contest. Returns its outcome when it ends (agreed, forced, bought, killing, civil_war, no_one). Nothing ends
    it by the calendar: each week an agreement has a chance (the front-runner's clarity and the pressure to end it, thinned while the
    matter is young), and so has a war (two real sides, bitter claimants, thinned while it is young)."""
    meta = meta_of(row)
    org, cid = int(meta["org"]), int(row["id"])
    blk = block(conn, org, "contest")
    weeks = (int(day) - int(meta["opened"])) / WEEK
    cands = _stand(conn, org, meta, blk, day, cid)
    if not cands:
        _finish_contest(conn, row, meta, None, "no_one", day)
        return "no_one"
    share = tally(conn, org, meta, blk, cands, day, cid)
    ranked = sorted(share.items(), key=lambda kv: (-kv[1], kv[0]))
    lead, s1 = ranked[0]
    s2 = ranked[1][1] if len(ranked) > 1 else 0.0
    _lean(conn, org, meta, blk, share, day, cid)
    chance = agree_chance(conn, org, meta, blk, ranked, int(day))
    if roll(conn, org, int(day), f"agree:{cid}") < chance:
        # the label names how the winner got there: leaning on men, paying them, a killing on the way, or plain agreement
        out = "forced" if lead in meta.get("forced_by", []) else "bought" if lead in meta.get("bought_by", []) else "killing" if meta["killed"] else "agreed"
        _finish_contest(conn, row, meta, lead, out, day)
        return out
    for c in sorted(cands):  # a candidate losing ground may have the man in front killed
        if c != lead and share.get(c, 0.0) < s1 and roll(conn, c, int(day), f"cut:{cid}") < v(conn, blk["kill_week"]) * drive(conn, c, "aggression") * drive(conn, c, "ambition") * (s1 - share.get(c, 0.0)):
            from .outfit_choices import kill
            kill(conn, c, lead, int(day), sanctioned=False)
            meta["killed"] += 1
            break
    if len(ranked) > 1:
        from . import org_coup
        wr = blk["war"]
        tension = org_coup.tension(conn, org, [lead, ranked[1][0]])
        p_war = v(conn, wr["week"]) * early(conn, weeks, wr["early_weeks"], wr["early_floor"]) * tension * clamp01(s2 / v(conn, wr["ref_share"]))
        if roll(conn, org, int(day), f"war:{cid}") < p_war:
            _finish_contest(conn, row, meta, None, "civil_war", day)
            org_coup.start_civil_war(conn, org, [lead, ranked[1][0]], int(day), cause="contest", late=int(meta["late"]))
            return "civil_war"
    save_meta(conn, cid, meta)
    return None


def _contests(conn: sqlite3.Connection, day: int) -> dict:
    out = {"contests": 0}
    for row in conn.execute("SELECT * FROM org_agenda WHERE kind='contest' AND status='open' ORDER BY id").fetchall():
        tick_contest(conn, row, int(day))
        out["contests"] += 1
    return out


def _returned(conn: sqlite3.Connection, org: int, man: int, day: int) -> bool:
    """A head who was held and is released while his contest still runs takes his seat back; the acting man steps back."""
    row = conn.execute("SELECT * FROM org_agenda WHERE kind='contest' AND status='open' AND subject_id=? AND actor_id=?", (int(man), int(org))).fetchone()
    if row is None:
        return False
    marker = acting_marker(conn, org)
    if marker is not None:
        step_back(conn, org, marker, int(man), int(day))
    close_row(conn, int(row["id"]), int(day), outcome="returned")
    return True


def _weekly(conn: sqlite3.Connection, day: int) -> dict:
    if not contest_orgs(conn) and not any(block(conn, int(r[0]), "appoint") for r in conn.execute("SELECT org_actor_id FROM org_profiles")):
        return {}
    out = {"stuck": stuck_units(conn, int(day)) + stuck_posts(conn, int(day))}
    out.update(_heirs(conn, int(day)))
    out.update(_contests(conn, int(day)))
    from . import org_coup
    for k, n in (org_coup.weekly(conn, int(day)) or {}).items():
        out[k] = out.get(k, 0) + n
    return out


# ---- choices on the agenda (the GM sees them) ----

def _name(conn, a):
    return name_of(conn, a)


on_unit_vacancy(_unit_vacancy)
on_post_vacancy(_post_vacancy)
register_executor("fill_post", execute_fill_post)
register_agenda_action("fill_post", post_offers)
on_head_vacancy(lambda conn, org, seat, day, why: open_contest(conn, org, seat, day, why))
on_return(_returned)
on_week(_weekly)
