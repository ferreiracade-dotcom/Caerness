"""What passes between organisations besides blows (task B12f): debts, men who change sides (poached or leaving), and one organisation
taking another in. Generic; figures and words are outfits data `tension.dealings`, each a Design proposal with its reasoning.

Debts. Redress agreed and not paid in full, a levy a head could only part pay, a council's ruling he could not meet: what is not paid
becomes a debt between the two organisations. Each week the debtor's head weighs paying what he owes with his own means and fears;
what stays unpaid keeps the creditor aggrieved, by how much is owed and who owes it, for as long as it is owed. Nothing is forgiven
on a timer.

Sides. A man who goes over to another organisation (a rival head makes him an offer he weighs, or he leaves) takes his lines with him
and raises his old organisation's tension toward the new one, by his rank and by what he earned.

Taking in. A head weighs absorbing a much smaller organisation, an act like any other the voices weigh each week; the other head weighs
coming in. When it happens the men and lines pass over. The same drivers that make one family stronger make this likelier.
"""
from __future__ import annotations

import sqlite3

from . import ledger, org_tension as ot, outfit_motives as om
from .orgs import clamp01, head_of, imposed, kind_rules, seat_of
from .relationships import adjust_relationship


def dd(conn: sqlite3.Connection) -> dict:
    return ot.data(conn).get("dealings") or {}


def _v(conn, spec, default: float = 0.0) -> float:
    return ot._v(conn, spec, default)


def _rng(conn, stream: str, *keys):
    return ot._rng(conn, "dealings:" + stream, *keys)


def _flush(conn, day: int) -> None:
    t = ot._today(conn, day)
    t.update(orgs=None, places={}, maxheat=None, press={}, cp=None, sz=None)


# ---- debts ----

def owe(conn: sqlite3.Connection, creditor: int, debtor: int, amount: float, origin: str, day: int) -> int | None:
    """`debtor` (an organisation) owes `creditor` this much; returns the debt id."""
    if amount <= 0 or int(creditor) == int(debtor) or not ot.enabled(conn):
        return None
    return int(conn.execute(
        "INSERT INTO org_debts(creditor_org,debtor_org,amount,origin,since_day,accrued_day,debtor_actor_id,creditor_actor_id) VALUES (?,?,?,?,?,?,?,?)",
        (int(creditor), int(debtor), float(amount), origin, int(day), int(day), head_of(conn, debtor), head_of(conn, creditor))).lastrowid)


def settle_up(conn: sqlite3.Connection, payer: int, payee: int, amount: float, origin: str, day: int) -> float:
    """The head of `payer` pays `payee`'s head what he can; the rest is a debt. Returns what was paid."""
    ph, qh = head_of(conn, payer), head_of(conn, payee)
    paid = 0.0
    if ph is not None and qh is not None and amount > 0:
        paid = ledger.transfer(conn, ("person", int(ph)), ("person", int(qh)), float(amount), flow_kind="tribute", purpose=origin, allow_partial=True) or 0.0
    owe(conn, payee, payer, float(amount) - float(paid), origin, day)
    return float(paid)


def remaining(row) -> float:
    return max(0.0, float(row["amount"]) - float(row["paid"]))


def _debts(conn, day: int) -> int:
    d = dd(conn).get("debt") or {}
    if not d:
        return 0
    n = 0
    rows = conn.execute("SELECT * FROM org_debts WHERE status='open' ORDER BY id").fetchall()
    for r in rows:
        C, D = int(r["creditor_org"]), int(r["debtor_org"])
        hd, hc = head_of(conn, D), head_of(conn, C)
        left = remaining(r)
        if hd is not None and hc is not None and ot._free(conn, hd):
            f = ot.factors(conn, hd, D, C, day)
            bal = ledger.balance(conn, ("person", int(hd)))
            f["can_pay"] = clamp01(bal / left) if left > 0 else 1.0
            f["owed_much"] = left / (left + max(1e-9, _v(conn, d.get("scale"), 1.0)))
            if _rng(conn, "pay", r["id"], day).random() < _blend(conn, d["pay"], f):
                got = ledger.transfer(conn, ("person", int(hd)), ("person", int(hc)), left, flow_kind="tribute", purpose="a debt", allow_partial=True) or 0.0
                if got > 0:
                    left -= got
                    conn.execute("UPDATE org_debts SET paid=paid+? WHERE id=?", (got, r["id"]))
                    imposed(conn, hd)
                    if left <= 1e-9:
                        conn.execute("UPDATE org_debts SET status='paid' WHERE id=?", (r["id"],))
                        ot.add(conn, C, D, "debt_paid", -_v(conn, d.get("ease")), day, actor=hd)
                        n += 1
                        continue
        days = max(0, int(day) - int(r["accrued_day"]))
        seat = seat_of(conn, hd, D) if hd is not None else None
        who = _v(conn, d.get("who_base"), 1.0) + _v(conn, d.get("who_rank"), 0.0) * (ot._rank(conn, seat["role_key"]) if seat is not None else 0.0)
        share = left / (left + max(1e-9, _v(conn, d.get("scale"), 1.0)))
        if days and left > 0:
            ot.add(conn, C, D, "debt_unpaid", _v(conn, d.get("rate")) * days * share * who, day, actor=hd, note=r["origin"])
        conn.execute("UPDATE org_debts SET accrued_day=? WHERE id=?", (int(day), r["id"]))
    return n


def _blend(conn, terms, f):
    return ot._blend(conn, terms, f)


# ---- men who change sides ----

def dependent_role(conn: sqlite3.Connection, org: int) -> str | None:
    return (kind_rules(conn, int(org)).get("opening") or {}).get("dependent_role")


def _lines_of(conn, man: int, org: int) -> list:
    return conn.execute("SELECT l.id,l.weekly_take,l.holding_id,h.pool_key FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id "
                        "WHERE l.holder_actor_id=? AND h.org_actor_id=? AND l.status='active' ORDER BY l.id", (int(man), int(org))).fetchall()


def change_side(conn: sqlite3.Connection, man: int, old: int, new: int, how: str, day: int, *, by: int | None = None, role: str | None = None) -> bool:
    """A man leaves one organisation for another: a new seat under `by` (or the new head), his lines moved over, the old seat out. The
    old organisation is aggrieved at the new one by his rank and by what he earned."""
    from . import orgs, outfit_money
    from .org_lifecycle import leave_life
    old_seat = seat_of(conn, man, old)
    role = role or dependent_role(conn, new)
    if old_seat is None or role is None or seat_of(conn, man, new) is not None:
        return False
    sup = by if by is not None else head_of(conn, new)
    sup_seat = seat_of(conn, int(sup), new) if sup is not None else None
    take = 0.0
    orgs.seat(conn, int(man), int(new), role, unit_id=sup_seat["unit_id"] if sup_seat is not None else None, superior_actor_id=sup,
              level=int(old_seat["level"]), day=int(day), inducted_day=None, standing=0.0, provenance=how)
    for ln in _lines_of(conn, man, old):
        weekly = float(ln["weekly_take"] or 0.0)
        take += weekly
        total = float((outfit_money.design_pools(conn).get(ln["pool_key"]) or {}).get("default_m") or 0.0) * 1_000_000.0
        hid = int(conn.execute("INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,source,started_day) VALUES (?,?,?,?,?,?)",
                               (int(new), ln["pool_key"], round(100.0 * weekly * 52.0 / total, 4) if total > 0 else 0.0, weekly * 52.0, "taken", int(day))).lastrowid)
        conn.execute("UPDATE org_lines SET holding_id=? WHERE id=?", (hid, ln["id"]))
        conn.execute("UPDATE org_holdings SET yearly_take=MAX(0,yearly_take-?) WHERE id=?", (weekly * 52.0, ln["holding_id"]))
    leave_life(conn, int(man), int(old), int(day))
    imposed(conn, int(man))
    _flush(conn, day)
    if how != "absorbed":  # an organisation that comes in by its head's word has no quarrel with the one that took it in
        on_side_change(conn, int(man), int(old), int(new), old_seat["role_key"], take, how, day, by)
    return True


def on_side_change(conn: sqlite3.Connection, man: int, old: int, new: int, role: str | None, take: float, how: str, day: int, by: int | None = None) -> None:
    """The old organisation is aggrieved at the new: by who he was (his rank) and how much he earned."""
    d = dd(conn).get("side") or {}
    rank = ot._rank(conn, role)
    delta = _v(conn, d.get("raise")) * (_v(conn, d.get("rank_base"), 1.0) + _v(conn, d.get("rank"), 0.0) * rank) + _v(conn, d.get("raise_take")) * take / (take + max(1e-9, _v(conn, d.get("take_scale"), 1.0)))
    ot.add(conn, int(old), int(new), how, delta, day, actor=by, victim=man, note=str(role or ""))
    h = head_of(conn, old)
    if h is not None:
        adjust_relationship(conn, h, man, int(day), resentment_delta=_v(conn, d.get("resentment"), 0.0))
        imposed(conn, h)


# ---- poaching ----

def _poach_target(conn, F: int, T: int) -> int | None:
    """The best earner of T who can be reached: a seated man with lines, not its head, not already of F."""
    hT = head_of(conn, T)
    best, who = 0.0, None
    for r in conn.execute("SELECT l.holder_actor_id a,SUM(l.weekly_take) w FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active' "
                          "AND l.holder_actor_id IS NOT NULL GROUP BY 1 ORDER BY 2 DESC,1", (int(T),)).fetchall():
        a = int(r[0])
        if a != hT and ot._free(conn, a) and seat_of(conn, a, T) is not None and seat_of(conn, a, F) is None and float(r[1] or 0.0) > best:
            best, who = float(r[1]), a
            break
    return who


def feasible_poach(conn, voice: int, F: int, T: int, day: int) -> bool:
    return head_of(conn, T) is not None and dependent_role(conn, F) is not None and _poach_target(conn, F, T) is not None


def do_poach(conn, voice, F, T, day, name, spec, f):
    """An offer to one of T's earners. He weighs it with his own greed, his grudge against the man he answers to, his loyalty and his ties."""
    p = dd(conn).get("poach") or {}
    man = _poach_target(conn, F, T)
    if man is None:
        return {"summary": "There was no one to approach."}
    from .org_happenings import _resentment
    seat = seat_of(conn, man, T)
    gain = sum(float(x["weekly_take"] or 0.0) for x in _lines_of(conn, man, T))
    fm = {"always": 1.0, "greed": float(seat["greed"]), "resentful": _resentment(conn, man, day, seat, T), "disloyal": 1.0 - om._drive(conn, man, "loyalty"),
          "loyal": om._drive(conn, man, "loyalty"), "ambition": om._drive(conn, man, "ambition"), "standing": clamp01(float(seat["standing"])),
          "bold": om._drive(conn, man, "risk_tolerance"), "their_pull": clamp01(f["stronger"]), "weaker": f["weaker"],
          "earner": gain / (gain + max(1e-9, _v(conn, p.get("earn_scale"), 1.0)))}
    imposed(conn, man)
    if _rng(conn, "poach", man, day).random() < _blend(conn, p["accept"], fm):
        if change_side(conn, man, T, F, "poached", day, by=voice):
            return {"summary": f"{ot._name(conn, voice)} took {ot._name(conn, man)} from {ot._name(conn, head_of(conn, T))}."}
    ot.add(conn, T, F, "poach_refused", _v(conn, p.get("refused_raise"), 0.0), day, actor=voice, victim=man)
    return {"summary": f"{ot._name(conn, man)} turned {ot._name(conn, voice)} down."}


# ---- taking in ----

def feasible_absorb(conn, voice: int, F: int, T: int, day: int) -> bool:
    from .org_happenings import _size
    return head_of(conn, T) is not None and dependent_role(conn, F) is not None and 0 < _size(conn, T) < _size(conn, F)


def do_absorb(conn, voice, F, T, day, name, spec, f):
    """The other head weighs coming in. Refusing sours; accepting passes his men and lines over, and his organisation is no more."""
    a = dd(conn).get("absorb") or {}
    hT = head_of(conn, T)
    fT = ot.factors(conn, hT, T, F, day)
    fT["head_weak"] = ot._head_weak(conn, hT, day)
    fT["small"] = fT["weaker"]
    imposed(conn, hT)
    if _rng(conn, "absorb", F, T, day).random() < _blend(conn, a["accept"], fT):
        men = [(int(r[0]), r[1]) for r in conn.execute("SELECT actor_id,role_key FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY actor_id", (int(T),))]
        lines = int(conn.execute("SELECT COUNT(*) FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active'", (int(T),)).fetchone()[0])
        moved = 0
        top = kind_rules(conn, F).get("unit_leader")
        for m, role in men:
            if change_side(conn, m, T, F, "absorbed", day, by=voice, role=top if m == hT and top else None):
                moved += 1
        conn.execute("INSERT INTO org_absorptions(day,absorber_org,absorbed_org,men,lines,how) VALUES (?,?,?,?,?,?)", (int(day), int(F), int(T), moved, lines, "accepted"))
        return {"summary": f"{ot._name(conn, hT)} brought {moved} men in under {ot._name(conn, voice)}.", "absorbed": T}
    ot.add(conn, T, F, "absorb_refused", _v(conn, a.get("refused_raise"), 0.0), day, actor=voice)
    adjust_relationship(conn, hT, voice, int(day), resentment_delta=_v(conn, a.get("relation"), 0.0))
    return {"summary": f"{ot._name(conn, hT)} would not come in under {ot._name(conn, voice)}."}


# ---- the weekly pass ----

def process_due(conn: sqlite3.Connection, day: int) -> dict:
    if not ot.enabled(conn) or not dd(conn):
        return {}
    n = _debts(conn, int(day))
    return {"debts_paid": n} if n else {}
