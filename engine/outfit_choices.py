"""What a made man can choose (Saint Jude): start a racket, ask leave to take out his capo or do it, and the agenda a
killing or a request puts on the boss's and others' lists.

The generic machinery (provider, weekly roll, pressure) is `org_choices` and `org_motives`; this module registers the
mob's choices for the family kind and the actions for the agenda items they create:

  choices:  start_racket  (soldiers, capos, associates)       remove_superior (soldiers; two paths)
  offers:   start_racket | seek_permission | remove_superior
  agenda:   grant_or_refuse (the boss: grant_leave, refuse_leave, warn_capo)   hit (carry it out)
            discipline_hunt (the boss: order_hunt, let_it_lie)                 fill_capo_seat (the boss fills the seat)

Tasks 11-13 add the rest of the agenda. A man weighs taking out his capo only after his weekly roll passed; then he
either asks the boss (`seek_permission`, an agenda item for the boss) or acts alone (`remove_superior`), the first
the more the more cautious and tied to the boss he is, the second the more fear or the boss's own wish pushes him.
"""
from __future__ import annotations

import json
import sqlite3

from . import ledger, org_motives, outfit_motives as om
from .org_motives import _fig as figure
from .org_choices import register_agenda_action, register_choice, register_executor
from .org_lifecycle import fill_unit_leader, mark_for_history
from .orgs import add_agenda, clamp01, head_of, imposed, is_living, kind_rules, resolve_agenda, seat_of
from .relationships import adjust_relationship

FAMILY = "family"
REMOVE, START = om.REMOVE, om.START


def _utility(conn: sqlite3.Connection, x: float) -> float:
    return float(figure(conn, "org_choice_utility_base", default=8.0)) + float(figure(conn, "org_choice_utility_span", default=10.0)) * clamp01(x)


def _delay(conn: sqlite3.Connection) -> int:
    return int(figure(conn, "seat_fill_delay_days", default=3))


def _name(conn: sqlite3.Connection, actor_id: int | None) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone() if actor_id is not None else None
    return str(r[0]) if r else "someone"


def _open_item(conn: sqlite3.Connection, actor_id: int, kind: str, subject: int | None = None):
    q, a = "SELECT id FROM org_agenda WHERE actor_id=? AND kind=? AND status='open'", [int(actor_id), kind]
    if subject is not None:
        q += " AND subject_id=?"
        a.append(int(subject))
    return conn.execute(q, a).fetchone()


# ---- the two paths to taking out a capo ----

def remove_candidates(conn: sqlite3.Connection, actor_id: int, org: int, day: int) -> list[dict]:
    ctx = om.context(conn, actor_id, REMOVE)
    if ctx is None or ctx[0] != org:
        return []
    _, seat, capo, head = ctx
    if _open_item(conn, actor_id, "hit", capo) or (head is not None and _open_item(conn, head, "grant_or_refuse", actor_id)):
        return []
    p, parts = org_motives.pressure(conn, actor_id, day, REMOVE)
    top = ", ".join(k for k, v in sorted(parts.items(), key=lambda kv: -kv[1]) if v > 0.2) or "no one reason"
    payload = {"org": org, "target": capo, "unit_id": seat["unit_id"]}
    why = f"Weighs taking out {_name(conn, capo)} (pressure {p:.2f}: {top})."
    if head is None or head == capo:
        return [{"kind": REMOVE, "utility": _utility(conn, 1.0), "rationale": why, "payload": {**payload, "sanctioned": False}, "target_actor_id": capo, "risk": 0.8}]
    caution = 1.0 - om._drive(conn, actor_id, "risk_tolerance")
    tie_row = om._rel(conn, actor_id, head)
    tie = clamp01(float(tie_row["trust"]) / 100.0) if tie_row is not None else 0.0
    push = max(parts.get("fear", 0.0), parts.get("boss_wants_it", 0.0))
    ask = clamp01((1.0 - (1.0 - caution) * (1.0 - tie)) * (1.0 - 0.5 * push))  # caution or a tie to the boss alone leads him to ask
    return [
        {"kind": "seek_permission", "utility": _utility(conn, ask), "rationale": why + " He asks the boss first.", "payload": payload,
         "target_actor_id": head, "risk": 0.2},
        {"kind": REMOVE, "utility": _utility(conn, 1.0 - ask), "rationale": why + " He does it himself.",
         "payload": {**payload, "sanctioned": False}, "target_actor_id": capo, "risk": 0.8},
    ]


def execute_seek_permission(conn: sqlite3.Connection, actor_id: int, kind: str, payload: dict, day: int) -> dict:
    org, capo = int(payload["org"]), int(payload["target"])
    head = head_of(conn, org)
    if head is None or not is_living(conn, head):
        return {"summary": "There was no one to ask.", "blocked": True}
    add_agenda(conn, head, "grant_or_refuse", int(day) + _delay(conn), subject_kind="actor", subject_id=int(actor_id),
               metadata={"target": capo, "org": org})
    return {"summary": f"{_name(conn, actor_id)} asked {_name(conn, head)} for leave to be rid of {_name(conn, capo)}."}


def kill(conn: sqlite3.Connection, killer: int, victim: int, day: int, *, sanctioned: bool) -> str:
    """A killing inside the organisation: the victim dies through the harm system, his seats go dead; a dead unit leader
    puts `fill_capo_seat` on the boss's list; an unsanctioned killing puts `discipline_hunt` there unless the boss wanted
    it (then the killer gains standing). History is flagged for both."""
    from .harm import record_harm
    seats = conn.execute("SELECT org_actor_id,role_key,unit_id FROM org_seats WHERE actor_id=? AND status='active'", (int(victim),)).fetchall()
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(victim),)).fetchone()
    record_harm(conn, int(victim), source_kind="org_action", source_ref_id=int(day) * 10_000_000 + int(killer), severity=100.0,
                intent_class="lethal", location_id=loc[0] if loc else None, outcome_override="fatal",
                metadata={"offender_actor_id": int(killer), "public": False})
    for (sub,) in conn.execute("SELECT actor_id FROM org_seats WHERE superior_actor_id=? AND status='active' AND actor_id<>?",
                               (int(victim), int(victim))).fetchall():
        imposed(conn, int(sub))  # the men who answered to him are looked at again tomorrow
    conn.execute("UPDATE org_seats SET status='dead', left_day=? WHERE actor_id=? AND status='active'", (int(day), int(victim)))
    mark_for_history(conn, int(victim), f"killed by {_name(conn, killer)}", int(day))
    mark_for_history(conn, int(killer), f"killed {_name(conn, victim)}", int(day))
    for s in seats:
        org = int(s["org_actor_id"])
        head = head_of(conn, org)
        if s["role_key"] == kind_rules(conn, org).get("unit_leader") and s["unit_id"] and head is not None:
            add_agenda(conn, head, "fill_capo_seat", int(day) + _delay(conn), subject_kind="unit", subject_id=int(s["unit_id"]), metadata={"org": org})
        if not sanctioned and head is not None and head not in (int(killer), int(victim)):
            wants = om.boss_wants(conn, head, int(victim))
            if wants > 0.5:
                conn.execute("UPDATE org_seats SET standing=standing+? WHERE actor_id=? AND org_actor_id=?",
                             (float(figure(conn, "unasked_kill_standing", default=0.25)), int(killer), org))
            else:
                add_agenda(conn, head, "discipline_hunt", int(day) + _delay(conn), subject_kind="actor", subject_id=int(killer),
                           metadata={"victim": int(victim), "org": org, "boss_wants": wants})
    return f"{_name(conn, killer)} killed {_name(conn, victim)}."


def execute_remove(conn: sqlite3.Connection, actor_id: int, kind: str, payload: dict, day: int) -> dict:
    victim = int(payload["target"])
    if not is_living(conn, victim):
        return {"summary": "His target was already dead.", "blocked": True}
    return {"summary": kill(conn, int(actor_id), victim, int(day), sanctioned=bool(payload.get("sanctioned")))}


# ---- agenda: the boss's and the killer's lists ----

def grant_or_refuse_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = json.loads(item["metadata_json"] or "{}")
    applicant, capo = int(item["subject_id"]), int(meta["target"])
    wants = om.boss_wants(conn, actor_id, capo)
    tie = om._rel(conn, actor_id, capo)
    fond = clamp01(float(tie["trust"]) / 100.0) if tie is not None else 0.0
    payload = {"applicant": applicant, "target": capo, "org": meta.get("org")}
    return [
        {"kind": "grant_leave", "utility": _utility(conn, wants), "rationale": f"Lets {_name(conn, applicant)} have {_name(conn, capo)}.", "payload": payload},
        {"kind": "refuse_leave", "utility": _utility(conn, 1.0 - wants), "rationale": f"Tells {_name(conn, applicant)} no.", "payload": payload},
        {"kind": "warn_capo", "utility": _utility(conn, fond * (1.0 - wants)), "rationale": f"Warns {_name(conn, capo)} about {_name(conn, applicant)}.", "payload": payload},
    ]


def _finish(conn: sqlite3.Connection, payload: dict, day: int) -> None:
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))


def execute_grant(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    add_agenda(conn, int(payload["applicant"]), "hit", int(day) + 1, subject_kind="actor", subject_id=int(payload["target"]),
               metadata={"sanctioned": True, "ordered_by": int(actor_id), "org": payload.get("org")})
    return {"summary": f"{_name(conn, actor_id)} gave {_name(conn, payload['applicant'])} leave to kill {_name(conn, payload['target'])}."}


def execute_refuse(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    adjust_relationship(conn, int(payload["applicant"]), int(actor_id), int(day),
                        resentment_delta=float(figure(conn, "refuse_resentment_delta", default=8)))
    return {"summary": f"{_name(conn, actor_id)} refused {_name(conn, payload['applicant'])}."}


def execute_warn(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    adjust_relationship(conn, int(payload["target"]), int(payload["applicant"]), int(day),
                        resentment_delta=float(figure(conn, "warn_resentment_delta", default=12)))
    return {"summary": f"{_name(conn, actor_id)} warned {_name(conn, payload['target'])} that {_name(conn, payload['applicant'])} wants him gone."}


def hit_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = json.loads(item["metadata_json"] or "{}")
    return [{"kind": "hit", "utility": _utility(conn, 1.0), "rationale": f"Carries out the hit on {_name(conn, item['subject_id'])}.",
             "payload": {"target": int(item["subject_id"]), "sanctioned": bool(meta.get("sanctioned"))}, "target_actor_id": int(item["subject_id"])}]


def execute_hit(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    victim = int(payload["target"])
    if not is_living(conn, victim):
        return {"summary": "The man was already dead."}
    return {"summary": kill(conn, int(actor_id), victim, int(day), sanctioned=bool(payload.get("sanctioned")))}


def hunt_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    """Hunt the killer, or let it lie: the less the boss wanted the capo gone, and the more he valued the capo against the killer
    (his respect for each), the more likely a hunt."""
    meta = json.loads(item["metadata_json"] or "{}")
    killer = int(item["subject_id"])
    wants = float(meta.get("boss_wants") or 0.0)

    def valued(a):
        r = om._rel(conn, actor_id, a)
        return max(0.01, clamp01(float(r["respect"]) / 100.0)) if r is not None else 0.01

    lost, kept = valued(meta.get("victim")), valued(killer)
    hunt = (1.0 - wants) * lost / (lost + kept)
    payload = {"killer": killer, "org": meta.get("org")}
    return [
        {"kind": "order_hunt", "utility": _utility(conn, hunt), "rationale": f"Has {_name(conn, killer)} hunted.", "payload": payload},
        {"kind": "let_it_lie", "utility": _utility(conn, 1.0 - hunt), "rationale": f"Lets the killing by {_name(conn, killer)} pass.", "payload": payload},
    ]


def execute_order_hunt(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    org, killer = int(payload["org"]), int(payload["killer"])
    best, best_l = None, -1.0
    for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND inducted_day IS NOT NULL AND actor_id NOT IN (?,?) ORDER BY actor_id",
                          (org, int(actor_id), killer)).fetchall():
        rel = om._rel(conn, r[0], actor_id)
        loyal = float(rel["loyalty"]) if rel is not None else 0.0
        if loyal > best_l:
            best, best_l = int(r[0]), loyal
    if best is None:
        return {"summary": "There was no one to send."}
    add_agenda(conn, best, "hit", int(day) + 1, subject_kind="actor", subject_id=killer, metadata={"sanctioned": True, "ordered_by": int(actor_id), "org": org})
    return {"summary": f"{_name(conn, actor_id)} sent {_name(conn, best)} after {_name(conn, killer)}."}


def execute_let_lie(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    return {"summary": f"{_name(conn, actor_id)} let the killing by {_name(conn, payload['killer'])} pass."}


def fill_seat_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    return [{"kind": "fill_capo_seat", "utility": _utility(conn, 1.0), "rationale": "Fills the vacant capo's seat.", "payload": {"unit_id": int(item["subject_id"])}}]


def execute_fill_capo_seat(conn, actor_id, kind, payload, day):
    new = fill_unit_leader(conn, int(payload["unit_id"]), int(day))
    _finish(conn, payload, day)
    return {"summary": f"{_name(conn, new)} took the seat." if new is not None else "No one was fit to take the seat."}


# ---- starting a racket ----

def start_candidates(conn: sqlite3.Connection, actor_id: int, org: int, day: int) -> list[dict]:
    ctx = om.context(conn, actor_id, START)
    if ctx is None or ctx[0] != org:
        return []
    seat = ctx[1]
    cost = om.start_cost(conn, seat["role_key"])
    if ledger.balance(conn, ("person", int(actor_id))) < cost:
        return []
    best = om._best(conn, actor_id, day, seat)
    if best is None:
        return []
    loc, pool, opp = best
    p, parts = org_motives.pressure(conn, actor_id, day, START)
    label = (org_motives._sphere_data(conn).get("line_kinds") or {}).get(pool, pool)
    place = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()[0]
    return [{"kind": START, "utility": _utility(conn, p), "cost": cost, "risk": 0.3,
             "rationale": f"Weighs starting {label} in {place} (pressure {p:.2f}).",
             "payload": {"org": org, "location_id": loc, "pool": pool, "opportunity": opp, "cost": cost}}]


def execute_start_racket(conn: sqlite3.Connection, actor_id: int, kind: str, payload: dict, day: int) -> dict:
    org, loc, pool = int(payload["org"]), int(payload["location_id"]), str(payload["pool"])
    seat = seat_of(conn, actor_id, org)
    cost = float(payload["cost"])
    if seat is None or ledger.balance(conn, ("person", int(actor_id))) < cost:
        return {"summary": "He could not find the money to start it.", "blocked": True}
    ledger.spend(conn, ("person", int(actor_id)), cost, purpose="starting a racket")
    weekly = om.line_weekly(conn, seat["role_key"]) * (0.5 + float(payload["opportunity"]))
    from . import outfit_money
    pools = outfit_money.design_pools(conn)
    total = float((pools.get(pool) or {}).get("default_m") or 0.0) * 1_000_000.0
    holding = conn.execute(
        "INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,source,started_day) VALUES (?,?,?,?,'started',?)",
        (org, pool, round(100.0 * weekly * 52.0 / total, 4) if total > 0 else 0.0, weekly * 52.0, int(day))).lastrowid
    caution = 1.0 - om._drive(conn, actor_id, "risk_tolerance")
    loyalty = om._drive(conn, actor_id, "loyalty")
    greed = float(seat["greed"])
    hidden = 1 if org_motives._roll(conn, actor_id, int(day), "hidden") < greed / (greed + loyalty + caution) else 0
    holder = int(seat["superior_actor_id"]) if seat["role_key"] in (org_motives._sphere_data(conn).get("under_patron") or ["associate"]) and seat["superior_actor_id"] else int(actor_id)
    label = (org_motives._sphere_data(conn).get("line_kinds") or {}).get(pool, pool)
    place = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()[0]
    conn.execute(
        """INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,location_id,weekly_take,hidden,started_day)
           VALUES (?,?,?,?,?,?,?,?)""",
        (holding, seat["unit_id"], holder, f"{label} in {place}", loc, weekly, hidden, int(day)))
    return {"summary": f"{_name(conn, actor_id)} started {label} in {place}, about ${weekly:,.0f} a week" + (", kept from the books." if hidden else ".")}


register_choice(FAMILY, REMOVE, remove_candidates, execute_remove)
register_choice(FAMILY, START, start_candidates, execute_start_racket)
for _kind, _fn in (("seek_permission", execute_seek_permission), ("grant_leave", execute_grant), ("refuse_leave", execute_refuse),
                   ("warn_capo", execute_warn), ("hit", execute_hit), ("order_hunt", execute_order_hunt), ("let_it_lie", execute_let_lie),
                   ("fill_capo_seat", execute_fill_capo_seat)):
    register_executor(_kind, _fn)
for _kind, _fn in (("grant_or_refuse", grant_or_refuse_offers), ("hit", hit_offers), ("discipline_hunt", hunt_offers),
                   ("fill_capo_seat", fill_seat_offers)):
    register_agenda_action(_kind, _fn)
