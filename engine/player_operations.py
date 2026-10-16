"""Consequential player operations: general parameters (who, what, with what, toward whom, under what terms).

Each operation returns a result dict and never raises for player mistakes; refusals are results.
Amounts leave this module only as scale words.
"""
from __future__ import annotations

import math
import sqlite3
from typing import Any, Callable

from . import ledger
from .interactions import _capacity, _log_event, create_interaction, resolve_interaction
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


# ---------------------------------------------------------------- lend

RATES = {"low": 0.02, "usual": 0.05, "steep": 0.12}


def _offer(conn, me: int, target: int, kind: str, day: int, intent: str, terms: dict, stakes: int = 2):
    """Create an interaction and resolve it at once. Returns (interaction_id, result) or (None, refusal dict)."""
    iid = create_interaction(conn, me, target, kind, day, stakes=stakes, rationale=intent, terms=terms)
    pending = conn.execute("SELECT status FROM interactions WHERE id=?", (iid,)).fetchone()
    if not pending or str(pending[0]) != "pending":
        return None, _refuse(f"{_name(conn, target)} will not hear it again so soon.")
    return iid, resolve_interaction(conn, iid, day)


def _lend(conn, me: int, target: int | None, d: dict, intent: str) -> dict:
    if target is None or not _living(conn, target) or target == me:
        return _refuse("There is no living person named to lend to.")
    name = _name(conn, target)
    try:
        src = ledger.parse_holder(d.get("from") or "me", me, conn)
        amount = ledger.amount_of(d.get("amount", ""))
    except ValueError as e:
        return _refuse(str(e))
    rate_word = str(d.get("rate") or "usual").lower()
    if rate_word not in RATES:
        return _refuse(f"Rate must be one of {', '.join(RATES)}.")
    try:
        due_days = max(1, int(d.get("due_days") or 90))
    except (TypeError, ValueError):
        return _refuse("due_days must be a number of days.")
    if (src[0] == "person" and src[1] != me) or not ledger.can_draw(conn, me, src):
        return _refuse("He has no right to draw on that purse.")
    if ledger.balance(conn, src) + 1e-9 < amount:
        return _refuse(f"There is not enough in {_holder_label(conn, src, me)} for a {ledger.scale_word(amount)} loan.")
    if not _same_place(conn, me, target):
        return _refuse(f"{name} is not here to be asked.")
    day = _day(conn)
    need = 1.0 if ledger.balance(conn, ("person", target)) < amount else 0.0
    iid, res = _offer(conn, me, target, "offer", day, intent, {"incentive": 1.0 + need, "operation": "lend"})
    if iid is None:
        return res
    if res.response != "accept":
        summary = f"{name} would not take the loan."
        _record(conn, me, "Loan refused", summary, targets=(target,))
        return {"status": "refused", "summary": summary, "interaction_id": iid}
    ledger.transfer(conn, src, ("person", target), amount, flow_kind="other", purpose=f"loan: {intent}")
    from . import civilian_life
    kw: dict[str, Any] = {"borrower_actor_id": target}
    if src[0] == "business":
        kw["lender_enterprise_id"] = src[1]
    else:
        kw["lender_actor_id"] = me
    cid = civilian_life.create_credit_agreement(conn, principal=amount, interest_rate_per_30=RATES[rate_word],
                                                due_day=day + due_days, metadata={"source": f"{src[0]}:{src[1]}"}, **kw)
    if src[0] == "business":  # create_credit_agreement debits the lender enterprise itself; the ledger already did
        conn.execute("UPDATE civilian_enterprises SET cash=cash+? WHERE id=?", (amount, src[1]))
    summary = f"{name} took a {ledger.scale_word(amount)} loan at {rate_word} interest from {_holder_label(conn, src, me)}."
    _record(conn, me, "Loan made", summary, targets=(target,))
    return {"status": "applied", "summary": summary, "interaction_id": iid, "credit_agreement_id": cid}


# ---------------------------------------------------------------- demand

DEMAND_KINDS = ("payment", "debt", "stop", "information", "other", "truce", "alliance", "tribute", "split")
OUTFIT_TERMS = {"truce": "truce", "alliance": "ally", "split": "hostile_peace"}
TRIBUTE_RATES = {"small": 0.05, "modest": 0.10, "substantial": 0.20}


def _my_outfit(conn, me: int) -> int | None:
    row = conn.execute("SELECT organization_id FROM underworld_personnel WHERE actor_id=? AND status='active' "
                       "AND role_kind IN ('boss','underboss') ORDER BY organization_id LIMIT 1", (me,)).fetchone()
    return int(row[0]) if row else None


def _backers(conn, me: int, target: int, d: dict) -> list[float] | str:
    """Capacities of those standing with him, or a refusal string."""
    caps: list[float] = []
    seen = {me, target}
    for raw in d.get("with") or []:
        try:
            aid = int(raw)
        except (TypeError, ValueError):
            return "Name companions by actor id."
        if aid in seen:
            return "The same person is named twice."
        seen.add(aid)
        if not _living(conn, aid) or not _same_place(conn, me, aid):
            return f"{_name(conn, aid)} is not here to stand with him."
        caps.append(_capacity(conn, aid))
    crew_ref = d.get("crew")
    if crew_ref:
        ref = str(crew_ref)
        raw = ref.partition(":")[2] if ref.startswith("crew:") else ""
        if not raw.isdigit():
            return "Name the crew as crew:<id>."
        crew = conn.execute("SELECT * FROM underworld_crews WHERE id=?", (int(raw),)).fetchone()
        if crew is None:
            return f"unknown crew {raw}"
        if not ledger.can_draw(conn, me, ("outfit", int(crew["organization_id"]))):
            return "That crew does not answer to him."
        leader = crew["leader_actor_id"]
        if leader is not None:
            if leader in seen:
                return "The same person is named twice."
            if not _living(conn, int(leader)) or not _same_place(conn, me, int(leader)):
                return "The crew is not here."
            caps.append(_capacity(conn, int(leader)))
        caps.extend([1.0] * int(min(float(crew["size_estimate"]), 8)))
    return caps


def coercion(conn, proposer: int, backers: list, recipient: int) -> float:
    """0-3: the weight of force standing with the proposer against the recipient and those who stand with him.

    `backers` are actor ids (int) or ready-made capacities (float, e.g. crew men).
    """
    total = _capacity(conn, proposer)
    for b in backers:
        total += _capacity(conn, b) if isinstance(b, int) else float(b)
    protection = 0.0
    seen: set[int] = set()
    for r in conn.execute("SELECT DISTINCT hm.actor_id FROM household_members hm JOIN household_members me2 ON me2.household_id=hm.household_id "
                          "WHERE me2.actor_id=? AND hm.status='active' AND me2.status='active' AND hm.actor_id<>?", (recipient, recipient)):
        aid = int(r[0])
        if aid not in seen and aid != proposer and _living(conn, aid) and _same_place(conn, recipient, aid):
            seen.add(aid)
            protection += _capacity(conn, aid)
    org = conn.execute("SELECT o.violence_capacity FROM underworld_personnel p JOIN underworld_organizations o ON o.id=p.organization_id "
                       "WHERE p.actor_id=? AND p.status='active' LIMIT 1", (recipient,)).fetchone()
    if org:
        protection += float(org[0]) / 25.0
    ratio = total / max(0.5, _capacity(conn, recipient) + protection)
    return min(3.0, max(0.0, 1.5 * math.log2(max(ratio, 1e-9)) + 1.0))


def _demand(conn, me: int, target: int | None, d: dict, intent: str) -> dict:
    if target is None or not _living(conn, target) or target == me:
        return _refuse("There is no living person named to make the demand of.")
    name = _name(conn, target)
    what = str(d.get("what") or "other").lower()
    if what not in DEMAND_KINDS:
        return _refuse(f"What is demanded must be one of {', '.join(DEMAND_KINDS)}.")
    if not _same_place(conn, me, target):
        return _refuse(f"{name} is not here.")
    amount = None
    if what == "payment":
        try:
            amount = ledger.amount_of(d.get("amount", ""))
        except ValueError as e:
            return _refuse(str(e))
    my_outfit = _my_outfit(conn, me)
    their_outfit = None
    if what in OUTFIT_TERMS or what == "tribute":
        if my_outfit is None:
            return _refuse("He has no outfit to speak for.")
        row = conn.execute("SELECT id FROM underworld_organizations WHERE current_leader_actor_id=? AND id<>?", (target, my_outfit)).fetchone()
        if row is None:
            return _refuse(f"{name} is not an outfit's boss.")
        their_outfit = int(row[0])
    debts: list = []
    if what == "debt":
        debts = _open_debts(conn, me, target)
        if not debts:
            return _refuse(f"{name} owes him nothing.")
        if d.get("amount"):
            try:
                ledger.amount_of(d["amount"])
            except ValueError as e:
                return _refuse(str(e))
    backers = _backers(conn, me, target, d)
    if isinstance(backers, str):
        return _refuse(backers)
    force = coercion(conn, me, backers, target)
    openly = bool(d.get("open"))
    kind = "negotiation" if what in OUTFIT_TERMS else ("threat" if openly else "demand")
    day = _day(conn)
    iid, res = _offer(conn, me, target, kind, day, intent, {"coercion": round(force, 3), "what": what},
                      stakes=3 if their_outfit else 2)
    if iid is None:
        return res
    if res.response not in ("comply", "accept"):
        if openly and my_outfit is not None:
            from .underworld_rebuild import add_heat
            add_heat(conn, my_outfit, public=2, violence=0)
        summary = f"{name} would not give way."
        _record(conn, me, "Demand refused", summary, severity=2 if openly else 1, targets=(target,))
        return {"status": "refused", "summary": summary, "interaction_id": iid, "answer": res.summary}
    return _concede(conn, me, target, name, what, d, amount, debts, my_outfit, their_outfit, iid, openly)


def _open_debts(conn, me: int, target: int) -> list:
    rows = conn.execute("SELECT * FROM credit_agreements WHERE borrower_actor_id=? AND outstanding>0 "
                        "AND status IN ('current','late','defaulted') ORDER BY id", (target,)).fetchall()
    return [r for r in rows if r["lender_actor_id"] == me or (
        r["lender_enterprise_id"] is not None and ledger.can_draw(conn, me, ("business", int(r["lender_enterprise_id"]))))]


def _concede(conn, me, target, name, what, d, amount, debts, my_outfit, their_outfit, iid, openly) -> dict:
    mine: ledger.Holder = ("person", me)
    theirs: ledger.Holder = ("person", target)
    if what == "payment":
        paid = ledger.transfer(conn, theirs, mine, amount, flow_kind="other", purpose="payment demanded", allow_partial=True)
        if paid <= 0:
            return {"status": "refused", "summary": f"{name} gave way but has nothing to give.", "interaction_id": iid}
        status = "applied" if paid >= amount - 1e-9 else "partial"
        summary = f"{name} hands over a {ledger.scale_word(paid)} sum" + ("." if status == "applied" else ", all that can be had.")
    elif what == "debt":
        from . import civilian_life
        limit = ledger.amount_of(d["amount"]) if d.get("amount") else float("inf")
        remaining = min(sum(float(r["outstanding"]) for r in debts), limit, ledger.balance(conn, theirs))
        paid = 0.0
        for r in debts:
            if remaining <= 1e-9:
                break
            part = min(float(r["outstanding"]), remaining)
            dst: ledger.Holder = ("business", int(r["lender_enterprise_id"])) if r["lender_enterprise_id"] is not None else mine
            got = ledger.transfer(conn, theirs, dst, part, flow_kind="other", purpose="debt collected", allow_partial=True)
            if got <= 0:
                break
            civilian_life.make_credit_payment(conn, int(r["id"]), got)
            if dst[0] == "business":  # make_credit_payment credits the lender enterprise itself; the ledger already did
                conn.execute("UPDATE civilian_enterprises SET cash=MAX(0,cash-?) WHERE id=?", (got, dst[1]))
            paid += got
            remaining -= got
        if paid <= 0:
            return {"status": "refused", "summary": f"{name} gave way but has nothing to give.", "interaction_id": iid}
        still = sum(float(r["outstanding"]) for r in _open_debts(conn, me, target))
        status = "partial" if still > 1e-9 else "applied"
        summary = f"{name} pays back a {ledger.scale_word(paid)} sum" + (", and still owes." if status == "partial" else ", and the debt is settled.")
    elif what in OUTFIT_TERMS:
        from .underworld_rebuild import change_relation
        meta = {"split": d.get("terms")} if what == "split" else None
        change_relation(conn, my_outfit, their_outfit, kind=OUTFIT_TERMS[what], hostility_delta=-15, respect_delta=5, metadata=meta)
        status = "applied"
        summary = f"{name} agrees to {'a truce' if what == 'truce' else 'an alliance' if what == 'alliance' else 'a divided peace'}."
    elif what == "tribute":
        from .underworld_rebuild import change_relation
        rate = TRIBUTE_RATES.get(str(d.get("amount") or ""), 0.10)
        change_relation(conn, my_outfit, their_outfit, kind="tributary", tribute_rate=rate, patron_organization_id=my_outfit)
        status, summary = "applied", f"{name} agrees to pay tribute."
    else:
        status, summary = "applied", f"{name} gives way on the {what}."
    _record(conn, me, "Demand met", summary, severity=2 if openly else 1, targets=(target,))
    return {"status": status, "summary": summary, "interaction_id": iid}


# ---------------------------------------------------------------- dispatch

_HANDLERS: dict[str, Callable[..., dict]] = {"pay": _pay, "hire": _hire, "lend": _lend, "demand": _demand}


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
