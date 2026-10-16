"""Consequential player operations: general parameters (who, what, with what, toward whom, under what terms).

Each operation returns a result dict and never raises for player mistakes; refusals are results.
Amounts leave this module only as scale words.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Callable

from . import ledger
from .interactions import _log_event, create_interaction, resolve_interaction
from .relationships import adjust_relationship_pair

OPERATIONS = ("pay", "hire", "lend", "demand", "attack", "trade", "order")

OUTFIT_RANK = ["associate", "member", "enforcer", "collector", "accountant", "fixer", "specialist",
               "crew_leader", "lieutenant", "underboss", "boss"]
OUTFIT_ROLES = set(OUTFIT_RANK)
BUSINESS_AUTHORITY = {"owner": 100, "manager": 80, "steward": 75, "factor": 60, "clerk": 40, "guard": 30, "hand": 20}
SERVICE_ROLES = {"servant", "retainer", "guard", "steward", "tutor", "apprentice", "clerk", "other"}


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _name(conn, actor_id: int) -> str:
    row = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()
    return str(row[0]) if row else "someone"


def _refuse(summary: str) -> dict[str, Any]:
    return {"status": "refused", "summary": summary}


def _living(conn, actor_id: int | None) -> bool:
    if actor_id is None:
        return False
    row = conn.execute("SELECT status FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not row or str(row[0]) in ("deceased", "dead"):
        return False
    prof = conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    return not prof or str(prof[0]) == "living"


def _same_place(conn, a: int, b: int) -> bool:
    rows = conn.execute("SELECT current_location_id FROM actors WHERE id IN (?,?)", (a, b)).fetchall()
    locs = {r[0] for r in rows}
    return len(rows) == 2 and None not in locs and len(locs) == 1


def _holder_label(conn, h: ledger.Holder, me: int) -> str:
    kind, i = h
    if kind == "person":
        return "his own purse" if i == me else _name(conn, i)
    table, col = {"business": ("civilian_enterprises", "name"), "outfit": ("underworld_organizations", "name"),
                  "household": ("households", "name")}[kind]
    row = conn.execute(f"SELECT {col} FROM {table} WHERE id=?", (i,)).fetchone()
    return str(row[0]) if row else kind


def _record(conn, actor_id: int, title: str, summary: str, *, severity: int = 1, targets: tuple[int, ...] = ()) -> int:
    return _log_event(conn, _day(conn), "player_operation", title, summary, severity, actor_id, tuple(targets))


# ---------------------------------------------------------------- pay

def _pay(conn, me: int, target: int | None, d: dict, intent: str) -> dict:
    try:
        src = ledger.parse_holder(d.get("from") or "me", me, conn)
        to_ref = d.get("to") or (f"person:{target}" if target is not None else None)
        if to_ref is None:
            return _refuse("Say who is to be paid.")
        dst = ledger.parse_holder(to_ref, me, conn)
        amount = ledger.amount_of(d.get("amount", ""))
    except ValueError as e:
        return _refuse(str(e))
    if src == dst:
        return _refuse("That would be paying money to the same pocket.")
    if not ledger.can_draw(conn, me, src):
        return _refuse("He has no right to draw on that purse.")
    if dst[0] == "person" and not _living(conn, dst[1]):
        return _refuse("There is no living person there to be paid.")
    purpose = str(d.get("purpose") or intent)
    flow = "wage" if "wage" in purpose.lower() else "other"
    try:
        ledger.transfer(conn, src, dst, amount, flow_kind=flow, purpose=purpose)
    except ValueError as e:
        if "not enough" in str(e):
            return _refuse(f"There is not enough in {_holder_label(conn, src, me)} for a {ledger.scale_word(amount)} sum.")
        return _refuse(str(e))
    word = ledger.scale_word(amount)
    summary = f"A {word} sum passes from {_holder_label(conn, src, me)} to {_holder_label(conn, dst, me)}."
    _record(conn, me, "Payment made", summary, targets=(dst[1],) if dst[0] == "person" and dst[1] != me else ())
    return {"status": "applied", "summary": summary, "amount": word}


# ---------------------------------------------------------------- hire

def _outfit_row(conn, actor_id: int):
    return conn.execute("SELECT * FROM underworld_personnel WHERE actor_id=? AND status='active'", (actor_id,)).fetchone()


def _is_my_person(conn, me: int, target: int, into: ledger.Holder) -> bool:
    """Target already works for a holding the protagonist controls (tier 1)."""
    for r in conn.execute("SELECT organization_id FROM underworld_personnel WHERE actor_id=? AND status='active'", (target,)):
        if ledger.can_draw(conn, me, ("outfit", int(r[0]))):
            return True
    for r in conn.execute("SELECT enterprise_id FROM enterprise_staff WHERE actor_id=? AND status='active'", (target,)):
        if ledger.can_draw(conn, me, ("business", int(r[0]))):
            return True
    for r in conn.execute("SELECT household_id FROM household_service_terms WHERE actor_id=? AND status='active'", (target,)):
        if ledger.can_draw(conn, me, ("household", int(r[0]))):
            return True
    return False


def _sour(conn, me: int, target: int, weight: float) -> None:
    adjust_relationship_pair(conn, target, me, _day(conn), a_to_b={"trust_delta": -6.0 * weight, "resentment_delta": 6.0 * weight})


def _hire(conn, me: int, target: int | None, d: dict, intent: str) -> dict:
    if target is None or not _living(conn, target):
        return _refuse("There is no living person named to take on.")
    if target == me:
        return _refuse("He cannot hire himself.")
    try:
        into = ledger.parse_holder(d.get("into", ""), me, conn)
    except ValueError:
        return _refuse("Say where: business:<id>, outfit:<id> or household:<id>.")
    if into[0] == "person":
        return _refuse("Say where: business:<id>, outfit:<id> or household:<id>.")
    if not ledger.can_draw(conn, me, into):
        return _refuse("He has no authority to take people on there.")
    role = str(d.get("role") or "").strip().lower()
    name = _name(conn, target)
    where = _holder_label(conn, into, me)
    if role == "none":
        return _dismiss(conn, me, target, into, name, where)
    mine = _is_my_person(conn, me, target, into)
    if mine:
        return _reassign(conn, me, target, into, role, name, where)
    if not _same_place(conn, me, target):
        return _refuse(f"{name} is not here to be asked.")
    if into[0] == "outfit" and conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=? AND status='active'", (target,)).fetchone():
        return _refuse(f"{name} already answers to another outfit.")
    amount = 1.0
    if d.get("amount"):
        try:
            amount = ledger.amount_of(d["amount"])
        except ValueError as e:
            return _refuse(str(e))
    day = _day(conn)
    iid = create_interaction(conn, me, target, "offer", day, stakes=2, rationale=intent,
                             terms={"incentive": min(2.0, amount / 1.5), "operation": "hire"})
    pending = conn.execute("SELECT status FROM interactions WHERE id=?", (iid,)).fetchone()
    if not pending or str(pending[0]) != "pending":
        return _refuse(f"{name} will not hear the offer again so soon.")
    res = resolve_interaction(conn, iid, day)
    if res.response != "accept":
        summary = f"{name} turned the offer down."
        _record(conn, me, "Offer refused", summary, targets=(target,))
        return {"status": "refused", "summary": summary, "interaction_id": iid}
    _install(conn, me, target, into, role)
    summary = f"{name} accepted a place with {where}."
    _record(conn, me, "Person taken on", summary, targets=(target,))
    return {"status": "applied", "summary": summary, "interaction_id": iid}


def _install(conn, me: int, target: int, into: ledger.Holder, role: str) -> None:
    kind, i = into
    if kind == "business":
        from .merchant import add_enterprise_staff
        add_enterprise_staff(conn, i, target, role=role or "hand", authority=BUSINESS_AUTHORITY.get(role or "hand", 30))
    elif kind == "outfit":
        from .underworld_rebuild import create_personnel
        kind_role = role if role in OUTFIT_ROLES and role not in ("boss", "underboss") else "member"
        create_personnel(conn, i, role_kind=kind_role, actor_id=target)
    else:
        from .household_life import add_service_term
        add_service_term(conn, i, target, role if role in SERVICE_ROLES else "retainer")


def _reassign(conn, me, target, into, role, name, where) -> dict:
    kind, i = into
    weight = 0.0
    if kind == "business":
        row = conn.execute("SELECT authority FROM enterprise_staff WHERE enterprise_id=? AND actor_id=? AND status='active'", (i, target)).fetchone()
        new_auth = BUSINESS_AUTHORITY.get(role or "hand", 30)
        if row is not None and new_auth < float(row[0]):
            weight = 0.5
        from .merchant import add_enterprise_staff
        add_enterprise_staff(conn, i, target, role=role or "hand", authority=new_auth)
    elif kind == "outfit":
        row = conn.execute("SELECT role_kind FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'", (target, i)).fetchone()
        if row is None:
            return _refuse(f"{name} belongs to a different outfit.")
        new = role if role in OUTFIT_ROLES else "member"
        if new in ("boss",):
            return _refuse("There is only one boss.")
        if OUTFIT_RANK.index(new) < OUTFIT_RANK.index(str(row[0])):
            weight = 0.5
        conn.execute("UPDATE underworld_personnel SET role_kind=? WHERE actor_id=?", (new, target))
    else:
        from .household_life import add_service_term
        add_service_term(conn, i, target, role if role in SERVICE_ROLES else "retainer")
    if weight:
        _sour(conn, me, target, weight)
    summary = f"{name} is moved to a {'lesser' if weight else 'new'} post with {where}."
    _record(conn, me, "Post changed", summary, targets=(target,))
    return {"status": "applied", "summary": summary}


def _dismiss(conn, me, target, into, name, where) -> dict:
    kind, i = into
    day = _day(conn)
    if kind == "business":
        n = conn.execute("DELETE FROM enterprise_staff WHERE enterprise_id=? AND actor_id=? AND status='active'", (i, target)).rowcount
    elif kind == "outfit":
        n = conn.execute("UPDATE underworld_personnel SET status='expelled' WHERE actor_id=? AND organization_id=? AND status='active'", (target, i)).rowcount
    else:
        n = conn.execute("UPDATE household_service_terms SET status='former',end_day=? WHERE household_id=? AND actor_id=? AND status='active'", (day, i, target)).rowcount
    if not n:
        return _refuse(f"{name} does not work for {where}.")
    _sour(conn, me, target, 1.0)
    summary = f"{name} is dismissed from {where}."
    _record(conn, me, "Person dismissed", summary, targets=(target,))
    return {"status": "applied", "summary": summary}


# ---------------------------------------------------------------- dispatch

_HANDLERS: dict[str, Callable[..., dict]] = {"pay": _pay, "hire": _hire}


def execute(conn: sqlite3.Connection, actor_id: int, op: str, *, target_actor_id: int | None,
            details: dict, intent: str) -> dict:
    handler = _HANDLERS.get(op)
    if handler is None:
        if op in OPERATIONS:
            return _refuse("That kind of action is not available yet.")
        return _refuse(f"Unknown operation; use one of {', '.join(OPERATIONS)}.")
    d = details if isinstance(details, dict) else {}
    try:
        return handler(conn, int(actor_id), target_actor_id, d, intent)
    except ValueError as e:
        return _refuse(str(e))
