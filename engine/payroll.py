"""Gap 4b: wages. Outfits pay their named people from the treasury by role, businesses pay staff out of their operating cost,
households pay servants and stewards from their liquidity (then the head's purse). Unpaid months are counted as arrears,
never as a negative balance, and are caught up when money allows or when the boss pays them through `act`.
"""
from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

UNIT = 0.15  # one weight of wage, per month. A typical named roster (about ten weights) costs 35-45% of a median outfit's gross.
ANON_WEIGHT = 0.1  # rank and file who are not named people already live off the rackets; this is only the treasury's upkeep of them
ROLE_WEIGHT = {"underboss": 3.0, "lieutenant": 2.0, "crew_leader": 2.0, "accountant": 1.5, "fixer": 1.5, "specialist": 1.5,
               "enforcer": 1.0, "collector": 1.0, "member": 1.0, "associate": 0.5}
HOUSEHOLD_WAGE = {"steward": 0.15, "retainer": 0.12, "guard": 0.12, "tutor": 0.12, "clerk": 0.12, "servant": 0.08, "apprentice": 0.05, "other": 0.08}
LABOUR_SHARE = 0.45  # of a business's operating cost


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def get_arrears(conn: sqlite3.Connection, kind: str, hid: int) -> dict[str, float]:
    r = conn.execute("SELECT months_behind,owed,last_paid_day FROM payroll_arrears WHERE holder_kind=? AND holder_id=?", (kind, hid)).fetchone()
    return {"months": int(r["months_behind"]), "owed": float(r["owed"]), "last_paid_day": r["last_paid_day"]} if r else {"months": 0, "owed": 0.0, "last_paid_day": None}


def set_arrears(conn: sqlite3.Connection, kind: str, hid: int, months: int, owed: float, *, paid_day: int | None = None) -> None:
    day = _day(conn)
    conn.execute(
        """INSERT INTO payroll_arrears(holder_kind,holder_id,months_behind,owed,last_paid_day,updated_day) VALUES (?,?,?,?,?,?)
           ON CONFLICT(holder_kind,holder_id) DO UPDATE SET months_behind=excluded.months_behind,owed=excluded.owed,
           last_paid_day=COALESCE(excluded.last_paid_day,payroll_arrears.last_paid_day),updated_day=excluded.updated_day""",
        (kind, hid, max(0, int(months)), round(max(0.0, owed), 4), paid_day, day))


def _months_behind(owed: float, month_due: float) -> int:
    """Months unpaid, from what is owed against one month's wages (so it does not depend on how often the books are closed)."""
    if owed <= 0.01 or month_due <= 0.0:
        return 0
    return max(1, math.ceil(owed / month_due - 1e-9))


# -- outfits ---------------------------------------------------------------------------------------------------

def outfit_roster(conn: sqlite3.Connection, oid: int) -> tuple[list[tuple[int, float]], float]:
    """Named people on the payroll (the boss draws instead) with their weights, and the anonymous rank-and-file weight."""
    org = conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    leader = int(org[0]) if org and org[0] is not None else -1
    named = [(int(r["actor_id"]), ROLE_WEIGHT.get(str(r["role_kind"]), 1.0)) for r in conn.execute(
        """SELECT p.actor_id,p.role_kind FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id
           WHERE p.organization_id=? AND p.status='active' AND a.status='active' AND p.role_kind<>'boss' AND p.actor_id<>? ORDER BY p.actor_id""", (oid, leader))]
    prof = conn.execute("SELECT COALESCE(core_members,0)+COALESCE(active_members,0) FROM underworld_membership_profiles WHERE organization_id=?", (oid,)).fetchone()
    full = float(prof[0]) if prof and prof[0] is not None else 0.0
    anon = max(0.0, full - len(named) - 1) * ANON_WEIGHT
    return named, anon


def run_outfit_payroll(conn: sqlite3.Connection, oid: int, day: int | None = None) -> dict[str, Any]:
    from . import ledger
    from .underworld_rebuild import _finance
    day = _day(conn) if day is None else day
    named, anon = outfit_roster(conn, oid)
    month_due = (sum(w for _, w in named) + anon) * UNIT
    prior = get_arrears(conn, "outfit", oid)
    if month_due <= 0.001:
        if prior["owed"] > 0:
            set_arrears(conn, "outfit", oid, 0, 0.0)
        return {"due": 0.0, "paid": 0.0, "owed": 0.0, "months": 0}
    scale = 1.0 + prior["owed"] / month_due
    paid = 0.0
    for aid, w in sorted(named, key=lambda x: (-x[1], x[0])):
        want = w * UNIT * scale
        if want < 0.005:
            continue
        try:
            paid += ledger.transfer(conn, ("outfit", oid), ("person", aid), want, flow_kind="wage", purpose="wages", allow_partial=True)
        except ValueError:
            pass
    left = float(conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0])
    anon_pay = min(left, anon * UNIT * scale)
    if anon_pay > 0.005:
        conn.execute("UPDATE underworld_organizations SET treasury=MAX(0,treasury-?) WHERE id=?", (anon_pay, oid))
        paid += anon_pay
    total_due = month_due * scale
    shortfall = max(0.0, total_due - paid)
    months = _months_behind(shortfall, month_due)
    set_arrears(conn, "outfit", oid, months, shortfall, paid_day=day if shortfall <= 0.01 else None)
    if paid > 0:
        _finance(conn, oid, "payroll", -paid, metadata={"due": round(total_due, 3), "arrears_months": months})
    return {"due": total_due, "paid": paid, "owed": shortfall, "months": months}


# -- businesses --------------------------------------------------------------------------------------------------

def business_staff(conn: sqlite3.Connection, eid: int) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        """SELECT s.actor_id FROM enterprise_staff s JOIN actors a ON a.id=s.actor_id JOIN civilian_enterprises e ON e.id=s.enterprise_id
           WHERE s.enterprise_id=? AND s.status='active' AND a.status='active' AND s.actor_id<>COALESCE(e.owner_actor_id,-1) ORDER BY s.actor_id""", (eid,))]


def run_business_payroll(conn: sqlite3.Connection, eid: int, operating_cost: float, unfunded_deficit: float, day: int | None = None) -> dict[str, Any]:
    """The labour share of the month's operating cost is the payroll line: staff are paid from what the business has already
    spent on running itself; when it could not meet its costs, wages are the part that goes unpaid."""
    from . import ledger
    from .underworld_rebuild import _record_economic_flow
    day = _day(conn) if day is None else day
    named = business_staff(conn, eid)
    cap = conn.execute("SELECT capacity FROM enterprise_business_profiles WHERE enterprise_id=?", (eid,)).fetchone()
    anon = max(1, round(float(cap[0]) / 15.0)) if cap else 1
    labour = LABOUR_SHARE * max(0.0, operating_cost)
    prior = get_arrears(conn, "business", eid)
    if labour <= 0.001:
        return {"due": 0.0, "paid": 0.0, "owed": prior["owed"], "months": prior["months"]}
    fraction = 1.0 if operating_cost <= 0 else max(0.0, min(1.0, 1.0 - unfunded_deficit / operating_cost))
    paid = labour * fraction
    if named:
        per = labour * len(named) / (len(named) + anon) / len(named) * fraction
        for aid in named:
            if per >= 0.005:
                ledger._credit(conn, ("person", aid), per)
                _record_economic_flow(conn, "wage", per, source_enterprise_id=eid, target_actor_id=aid, cadence_kind="monthly")
    shortfall = max(0.0, labour - paid) + prior["owed"]
    if prior["owed"] > 0 and fraction >= 0.999:
        cash = float(conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?", (eid,)).fetchone()[0])
        catch = min(prior["owed"], cash * 0.5)
        if catch > 0.005:
            if named:
                for aid in named:
                    ledger._credit(conn, ("person", aid), catch / len(named))
                    _record_economic_flow(conn, "wage", catch / len(named), source_enterprise_id=eid, target_actor_id=aid, cadence_kind="one_off")
            ledger._debit(conn, ("business", eid), catch)
            shortfall = max(0.0, shortfall - catch)
    months = _months_behind(shortfall, labour)
    set_arrears(conn, "business", eid, months, shortfall, paid_day=day if shortfall <= 0.01 else None)
    from .loyalty import business_morale
    business_morale(conn, eid, months)
    return {"due": labour, "paid": paid, "owed": shortfall, "months": months}


# -- households --------------------------------------------------------------------------------------------------

def service_terms(conn: sqlite3.Connection, hid: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT t.* FROM household_service_terms t JOIN actors a ON a.id=t.actor_id WHERE t.household_id=? AND t.status='active' AND a.status='active' ORDER BY t.id""", (hid,)).fetchall()


def run_household_payroll(conn: sqlite3.Connection, h: sqlite3.Row, elapsed_days: int, day: int | None = None) -> float:
    """Pay servants and stewards from the household's liquidity, then from the head's purse. Returns what left household liquidity."""
    from . import ledger
    from .underworld_rebuild import _record_economic_flow
    day = _day(conn) if day is None else day
    hid = int(h["id"])
    terms = service_terms(conn, hid)
    if not terms:
        prior = get_arrears(conn, "household", hid)
        if prior["owed"] > 0:
            set_arrears(conn, "household", hid, 0, 0.0)
        return 0.0
    month_due = sum(HOUSEHOLD_WAGE.get(str(t["service_role"]), .08) for t in terms)
    prior = get_arrears(conn, "household", hid)
    due = month_due * elapsed_days / 30.0
    scale = 1.0 + prior["owed"] / max(month_due, 0.001)
    liquidity = float(h["liquidity"])
    head = h["head_actor_id"]
    paid_total = from_house = 0.0
    for t in terms:
        want = HOUSEHOLD_WAGE.get(str(t["service_role"]), .08) * elapsed_days / 30.0 * scale
        got = min(max(0.0, liquidity - from_house), want)
        if got > 0.0001:
            ledger._credit(conn, ("person", int(t["actor_id"])), got)
            _record_economic_flow(conn, "wage", got, source_household_id=hid, target_actor_id=int(t["actor_id"]), cadence_kind="monthly")
            from_house += got
        rest = want - got
        if rest > 0.0001 and head is not None and int(head) != int(t["actor_id"]):
            try:
                got += ledger.transfer(conn, ("person", int(head)), ("person", int(t["actor_id"])), rest, flow_kind="wage", purpose="household wages", allow_partial=True)
            except ValueError:
                pass
        paid_total += got
    total_due = due * scale
    shortfall = max(0.0, total_due - paid_total)
    months = _months_behind(shortfall, month_due)
    set_arrears(conn, "household", hid, months, shortfall, paid_day=day if shortfall <= 0.01 else None)
    from .loyalty import household_morale
    household_morale(conn, hid, months, day, elapsed_days)
    return from_house


# -- paying arrears by order -------------------------------------------------------------------------------------

def pay_arrears(conn: sqlite3.Connection, kind: str, hid: int, source: tuple[str, int], amount: float) -> float:
    """The boss pays what is owed (up to `amount`) from `source` to the people concerned. Gradual: morale recovers by its own rule."""
    from . import ledger
    from .underworld_rebuild import _record_economic_flow
    prior = get_arrears(conn, kind, hid)
    pay = min(float(amount), prior["owed"], ledger.balance(conn, source))
    if pay <= 0.005:
        return 0.0
    if kind == "outfit":
        named, anon = outfit_roster(conn, hid)
        total_w = sum(w for _, w in named) + anon
        recipients = [(aid, pay * w / total_w) for aid, w in named] if total_w > 0 else []
        month_due = total_w * UNIT
    elif kind == "business":
        named = business_staff(conn, hid)
        recipients = [(aid, pay / len(named)) for aid in named]
        month_due = prior["owed"]
    else:
        terms = service_terms(conn, hid)
        tw = sum(HOUSEHOLD_WAGE.get(str(t["service_role"]), .08) for t in terms) or 1.0
        recipients = [(int(t["actor_id"]), pay * HOUSEHOLD_WAGE.get(str(t["service_role"]), .08) / tw) for t in terms]
        month_due = tw
    ledger._debit(conn, source, pay)
    for aid, amt in recipients:
        if amt > 0.0001:
            ledger._credit(conn, ("person", aid), amt)
            ep = {{"person": "source_actor_id", "business": "source_enterprise_id", "outfit": "source_organization_id", "household": "source_household_id"}[source[0]]: source[1]}
            _record_economic_flow(conn, "wage", amt, **ep, target_actor_id=aid, cadence_kind="one_off", metadata={"arrears": True})
    owed = max(0.0, prior["owed"] - pay)
    months = 0 if owed <= 0.01 else max(1, math.ceil(owed / max(month_due, 0.001)))
    set_arrears(conn, kind, hid, months, owed, paid_day=_day(conn) if owed <= 0.01 else None)
    return pay


def arrears_words(months: int) -> str:
    if months <= 0:
        return ""
    if months == 1:
        return "a month behind on pay"
    return f"{months} months behind on pay" if months < 5 else "long unpaid"
