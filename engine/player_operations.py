"""Consequential player operations: general parameters (who, what, with what, toward whom, under what terms).

Each operation returns a result dict and never raises for player mistakes; refusals are results.
Amounts leave this module only as scale words.
"""
from __future__ import annotations

import math
import sqlite3
from typing import Any, Callable

from . import ledger
from .interactions import InteractionResult, _capacity, _log_event, create_interaction, resolve_interaction
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


def _authority(me: int, d: dict) -> int:
    """Whose money and standing an operation draws on: the protagonist when a subordinate carries out his order."""
    return int(d.get("_principal", me))


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

def _pay_wages(conn, me: int, boss: int, d: dict) -> dict:
    """Pay what an outfit, a business or a household owes its people, from the named purse."""
    from . import payroll
    try:
        src = ledger.parse_holder(d.get("from") or "me", boss, conn)
        owing = ledger.parse_holder(d.get("for") or (f"{src[0]}:{src[1]}" if src[0] != "person" else ""), boss, conn)
    except ValueError as e:
        return _refuse(str(e) if d.get("for") or (d.get("from") or "me") != "me" else "Say whose wages: for is outfit:<id>, business:<id> or household:<id>.")
    if owing[0] == "person":
        return _refuse("Wages are owed by an outfit, a business or a household.")
    if not ledger.can_draw(conn, boss, src) or not ledger.can_draw(conn, boss, owing):
        return _refuse("He has no right to settle those wages.")
    due = payroll.get_arrears(conn, owing[0], owing[1])
    if due["owed"] <= 0.005:
        return _refuse("Nobody there is owed anything.")
    try:
        amount = ledger.amount_of(d["amount"]) if d.get("amount") else due["owed"]
    except ValueError as e:
        return _refuse(str(e))
    paid = payroll.pay_arrears(conn, owing[0], owing[1], src, amount)
    if paid <= 0:
        return _refuse(f"There is not enough in {_holder_label(conn, src, boss)} to pay what is owed.")
    left = payroll.get_arrears(conn, owing[0], owing[1])["owed"]
    who = _holder_label(conn, owing, boss)
    summary = f"He pays the wages owed at {who}" + (", all of it." if left <= 0.005 else ", though not all of it.")
    _record(conn, me, "Wages paid", summary)
    return {"status": "applied", "summary": summary, "amount": ledger.scale_word(paid)}


def _pay(conn, me: int, target: int | None, d: dict, intent: str) -> dict:
    boss = _authority(me, d)
    if str(d.get("to") or "").lower() == "wages":
        return _pay_wages(conn, me, boss, d)
    try:
        src = ledger.parse_holder(d.get("from") or "me", boss, conn)
        to_ref = d.get("to") or (f"person:{target}" if target is not None else None)
        if to_ref is None:
            return _refuse("Say who is to be paid.")
        dst = ledger.parse_holder(to_ref, boss, conn)
        amount = ledger.amount_of(d.get("amount", ""))
    except ValueError as e:
        return _refuse(str(e))
    if src == dst:
        return _refuse("That would be paying money to the same pocket.")
    if not ledger.can_draw(conn, boss, src):
        return _refuse("He has no right to draw on that purse.")
    if dst[0] == "person" and not _living(conn, dst[1]):
        return _refuse("There is no living person there to be paid.")
    purpose = str(d.get("purpose") or intent)
    flow = "wage" if "wage" in purpose.lower() else "other"
    try:
        ledger.transfer(conn, src, dst, amount, flow_kind=flow, purpose=purpose)
    except ValueError as e:
        if "not enough" in str(e):
            return _refuse(f"There is not enough in {_holder_label(conn, src, boss)} for a {ledger.scale_word(amount)} sum.")
        return _refuse(str(e))
    word = ledger.scale_word(amount)
    summary = f"A {word} sum passes from {_holder_label(conn, src, boss)} to {_holder_label(conn, dst, boss)}."
    _record(conn, me, "Payment made", summary, targets=(dst[1],) if dst[0] == "person" and dst[1] != me else ())
    return {"status": "applied", "summary": summary, "amount": word}


# ---------------------------------------------------------------- hire

def _outfit_row(conn, actor_id: int):
    return conn.execute("SELECT * FROM underworld_personnel WHERE actor_id=? AND status='active'", (actor_id,)).fetchone()


def _outranks(conn, me: int, target: int, holding: ledger.Holder) -> bool:
    """True when ``me`` stands above ``target`` in that holding (so may order, demote or dismiss him)."""
    kind, i = holding
    if target == me:
        return False
    if kind == "outfit":
        org = conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (i,)).fetchone()
        leader = org[0] if org else None
        if leader is not None and int(leader) == target:
            return False
        if leader is not None and int(leader) == me:
            return True
        def rank(a):
            r = conn.execute("SELECT role_kind FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'", (a, i)).fetchone()
            return OUTFIT_RANK.index(str(r[0])) if r and str(r[0]) in OUTFIT_RANK else -1
        return rank(target) < rank(me)
    if kind == "business":
        biz = conn.execute("SELECT owner_actor_id FROM civilian_enterprises WHERE id=?", (i,)).fetchone()
        owner = biz[0] if biz else None
        if owner is not None and int(owner) == target:
            return False
        if owner is not None and int(owner) == me:
            return True
        def auth(a):
            r = conn.execute("SELECT authority FROM enterprise_staff WHERE enterprise_id=? AND actor_id=? AND status='active'", (i, a)).fetchone()
            return float(r[0]) if r else 0.0
        return auth(target) < auth(me)
    row = conn.execute("SELECT head_actor_id FROM households WHERE id=?", (i,)).fetchone()
    return bool(row) and row[0] is not None and int(row[0]) == me


def _is_my_person(conn, me: int, target: int, into: ledger.Holder) -> bool:
    """Target already works for a holding the protagonist controls (tier 1)."""
    for r in conn.execute("SELECT organization_id FROM underworld_personnel WHERE actor_id=? AND status='active'", (target,)):
        if ledger.can_draw(conn, me, ("outfit", int(r[0]))) and _outranks(conn, me, target, ("outfit", int(r[0]))):
            return True
    for r in conn.execute("SELECT enterprise_id FROM enterprise_staff WHERE actor_id=? AND status='active'", (target,)):
        if ledger.can_draw(conn, me, ("business", int(r[0]))) and _outranks(conn, me, target, ("business", int(r[0]))):
            return True
    for r in conn.execute("SELECT household_id FROM household_service_terms WHERE actor_id=? AND status='active'", (target,)):
        if ledger.can_draw(conn, me, ("household", int(r[0]))) and _outranks(conn, me, target, ("household", int(r[0]))):
            return True
    return False


def _serves_in(conn, target: int, holding: ledger.Holder) -> bool:
    kind, i = holding
    sql = {"outfit": "SELECT 1 FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'",
           "business": "SELECT 1 FROM enterprise_staff WHERE actor_id=? AND enterprise_id=? AND status='active'",
           "household": "SELECT 1 FROM household_service_terms WHERE actor_id=? AND household_id=? AND status='active'"}[kind]
    return conn.execute(sql, (target, i)).fetchone() is not None


def _sour(conn, me: int, target: int, weight: float) -> None:
    adjust_relationship_pair(conn, target, me, _day(conn), a_to_b={"trust_delta": -6.0 * weight, "resentment_delta": 6.0 * weight})


def _hire(conn, me: int, target: int | None, d: dict, intent: str) -> dict:
    if target is None or not _living(conn, target):
        return _refuse("There is no living person named to take on.")
    if target == me:
        return _refuse("He cannot hire himself.")
    boss = _authority(me, d)
    try:
        into = ledger.parse_holder(d.get("into", ""), boss, conn)
    except ValueError:
        return _refuse("Say where: business:<id>, outfit:<id> or household:<id>.")
    if into[0] == "person":
        return _refuse("Say where: business:<id>, outfit:<id> or household:<id>.")
    if not ledger.can_draw(conn, boss, into):
        return _refuse("He has no authority to take people on there.")
    role = str(d.get("role") or "").strip().lower()
    name = _name(conn, target)
    where = _holder_label(conn, into, me)
    if _serves_in(conn, target, into) and not _outranks(conn, boss, target, into):
        return _refuse(f"{name} does not answer to him there.")
    if role == "none":
        return _dismiss(conn, me, target, into, name, where)
    mine = _is_my_person(conn, boss, target, into)
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
    iid, res = _offer(conn, me, target, "offer", day, intent, {"incentive": min(2.0, amount / 1.5)}, op="hire", d=d)
    if iid is None:
        return res
    countered = _countered(conn, me, target, iid, res)
    if countered:
        return countered
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


def _offer(conn, me: int, target: int, kind: str, day: int, intent: str, terms: dict, stakes: int = 2, *,
           op: str, d: dict):
    """Create an interaction and resolve it at once. Returns (interaction_id, result) or (None, refusal dict).

    The operation travels in the terms, so a counter-offer the protagonist later accepts completes it
    (settle_accepted). When ``d`` carries ``_accepted`` the other side has already agreed: no new interaction.
    """
    if d.get("_accepted"):
        iid = int(d["_accepted"])
        return iid, InteractionResult(iid, "accepted", "accept", "The counter-offer was accepted.")
    clean = {k: v for k, v in d.items() if not str(k).startswith("_")}
    terms = {**terms, "player_operation": {"op": op, "details": clean}}
    iid = create_interaction(conn, me, target, kind, day, stakes=stakes, rationale=intent, terms=terms)
    pending = conn.execute("SELECT status FROM interactions WHERE id=?", (iid,)).fetchone()
    if not pending or str(pending[0]) != "pending":
        return None, _refuse(f"{_name(conn, target)} will not hear it again so soon.")
    global _OFFERING
    _OFFERING += 1  # the caller settles an immediate acceptance itself
    try:
        return iid, resolve_interaction(conn, iid, day)
    finally:
        _OFFERING -= 1


_OFFERING = 0


def settle_npc_accepted(conn: sqlite3.Connection, interaction) -> dict | None:
    """The other party accepted the protagonist's own pending offer later, during the simulation: carry it out."""
    import json
    if _OFFERING:
        return None
    terms = json.loads(interaction["terms_json"] or "{}")
    po = terms.get("player_operation")
    if not isinstance(po, dict) or po.get("op") not in ("hire", "lend", "demand", "trade"):
        return None
    row = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    if not row or row[0] is None or int(row[0]) != int(interaction["proposer_actor_id"]):
        return None
    details = {**(po.get("details") or {}), "_accepted": int(interaction["id"])}
    return execute(conn, int(interaction["proposer_actor_id"]), str(po["op"]),
                   target_actor_id=int(interaction["recipient_actor_id"]), details=details,
                   intent=str(interaction["rationale"] or "accepted offer"), _trusted=True)


def _countered(conn, me: int, target: int, iid: int, res) -> dict | None:
    """A counter is an open negotiation: a pending offer back to the protagonist, answered with respond."""
    if res.response != "counter":
        return None
    summary = f"{_name(conn, target)} answers with terms of their own."
    _record(conn, me, "Counter-offer", summary, targets=(target,))
    return {"status": "countered", "summary": summary, "interaction_id": iid,
            "counter_interaction_id": res.child_interaction_id, "answer": res.summary}


def _lend(conn, me: int, target: int | None, d: dict, intent: str) -> dict:
    if target is None or not _living(conn, target) or target == me:
        return _refuse("There is no living person named to lend to.")
    name = _name(conn, target)
    boss = _authority(me, d)
    try:
        src = ledger.parse_holder(d.get("from") or "me", boss, conn)
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
    if src[0] in ("outfit", "household"):
        return _refuse("Loans are made from his own purse or one of his houses.")
    if (src[0] == "person" and src[1] != boss) or not ledger.can_draw(conn, boss, src):
        return _refuse("He has no right to draw on that purse.")
    if ledger.balance(conn, src) + 1e-9 < amount:
        return _refuse(f"There is not enough in {_holder_label(conn, src, boss)} for a {ledger.scale_word(amount)} loan.")
    if not _same_place(conn, me, target):
        return _refuse(f"{name} is not here to be asked.")
    day = _day(conn)
    need = 1.0 if ledger.balance(conn, ("person", target)) < amount else 0.0
    iid, res = _offer(conn, me, target, "offer", day, intent, {"incentive": 1.0 + need}, op="lend", d=d)
    if iid is None:
        return res
    countered = _countered(conn, me, target, iid, res)
    if countered:
        return countered
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
        kw["lender_actor_id"] = boss
    cid = civilian_life.create_credit_agreement(conn, principal=amount, interest_rate_per_30=RATES[rate_word],
                                                due_day=day + due_days, metadata={"source": f"{src[0]}:{src[1]}"}, **kw)
    if src[0] == "business":  # create_credit_agreement debits the lender enterprise itself; the ledger already did
        conn.execute("UPDATE civilian_enterprises SET cash=cash+? WHERE id=?", (amount, src[1]))
    summary = f"{name} took a {ledger.scale_word(amount)} loan at {rate_word} interest from {_holder_label(conn, src, boss)}."
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


def _backer_list(conn, me: int, target: int | None, d: dict) -> list[tuple[int | None, float]] | str:
    """Those standing with him as (actor id, or None for an unnamed crew hand; capacity), or a refusal string."""
    out: list[tuple[int | None, float]] = []
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
        out.append((aid, _capacity(conn, aid)))
    crew_ref = d.get("crew")
    if crew_ref:
        ref = str(crew_ref)
        raw = ref.partition(":")[2] if ref.startswith("crew:") else ""
        if not raw.isdigit():
            return "Name the crew as crew:<id>."
        crew = conn.execute("SELECT * FROM underworld_crews WHERE id=?", (int(raw),)).fetchone()
        if crew is None:
            return f"unknown crew {raw}"
        if not ledger.can_draw(conn, _authority(me, d), ("outfit", int(crew["organization_id"]))):
            return "That crew does not answer to him."
        leader = crew["leader_actor_id"]
        if leader is not None:
            if leader in seen:
                return "The same person is named twice."
            if not _living(conn, int(leader)) or not _same_place(conn, me, int(leader)):
                return "The crew is not here."
            out.append((int(leader), _capacity(conn, int(leader))))
        out.extend([(None, 1.0)] * int(min(float(crew["size_estimate"]), 8)))
    return out


def _backers(conn, me: int, target: int | None, d: dict) -> list[float] | str:
    """Capacities of those standing with him, or a refusal string."""
    got = _backer_list(conn, me, target, d)
    return got if isinstance(got, str) else [c for _, c in got]


def _protectors(conn, recipient: int, exclude: int | None = None) -> tuple[list[int], float]:
    """Household members present with the recipient (actor ids) and the extra weight of the recipient's outfit."""
    ids: list[int] = []
    for r in conn.execute("SELECT DISTINCT hm.actor_id FROM household_members hm JOIN household_members me2 ON me2.household_id=hm.household_id "
                          "WHERE me2.actor_id=? AND hm.status='active' AND me2.status='active' AND hm.actor_id<>?", (recipient, recipient)):
        aid = int(r[0])
        if aid not in ids and aid != exclude and _living(conn, aid) and _same_place(conn, recipient, aid):
            ids.append(aid)
    org = conn.execute("SELECT o.violence_capacity FROM underworld_personnel p JOIN underworld_organizations o ON o.id=p.organization_id "
                       "WHERE p.actor_id=? AND p.status='active' LIMIT 1", (recipient,)).fetchone()
    return ids, (float(org[0]) / 25.0 if org else 0.0)


def coercion(conn, proposer: int, backers: list, recipient: int) -> float:
    """0-3: the weight of force standing with the proposer against the recipient and those who stand with him.

    `backers` are actor ids (int) or ready-made capacities (float, e.g. crew men).
    """
    total = _capacity(conn, proposer)
    for b in backers:
        total += _capacity(conn, b) if isinstance(b, int) else float(b)
    ids, extra = _protectors(conn, recipient, exclude=proposer)
    protection = sum(_capacity(conn, aid) for aid in ids) + extra
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
    boss = _authority(me, d)
    my_outfit = _my_outfit(conn, boss)
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
        debts = _open_debts(conn, boss, target)
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
    if d.get("_reluctant"):  # a man doing it against his will leans on them less
        force = max(0.0, force - 1.0)
    openly = bool(d.get("open"))
    kind = "negotiation" if what in OUTFIT_TERMS else ("threat" if openly else "demand")
    day = _day(conn)
    iid, res = _offer(conn, me, target, kind, day, intent, {"coercion": round(force, 3), "what": what}, op="demand", d=d,
                      stakes=3 if their_outfit else 2)
    if iid is None:
        return res
    countered = _countered(conn, me, target, iid, res)
    if countered:
        return countered
    if res.response not in ("comply", "accept"):
        if openly and my_outfit is not None:
            from .underworld_rebuild import add_heat
            add_heat(conn, my_outfit, public=2, violence=0)
        summary = f"{name} would not give way."
        if what not in OUTFIT_TERMS and what != "tribute":
            vo, vz = _org_behind(conn, target, None)
            _leave_trace(conn, my_outfit, vo, vz, "extortion_attempt", 35, 10 if openly else 5, {"victim_actor_id": target, "what": what, "outcome": "refused"})
        _record(conn, me, "Demand refused", summary, severity=2 if openly else 1, targets=(target,))
        return {"status": "refused", "summary": summary, "interaction_id": iid, "answer": res.summary}
    if what not in OUTFIT_TERMS and what != "tribute":
        vo, vz = _org_behind(conn, target, None)
        _leave_trace(conn, my_outfit, vo, vz, "extortion_attempt", 22, 4, {"victim_actor_id": target, "what": what, "outcome": "conceded"})
    return _concede(conn, me, target, name, what, d, amount, debts, my_outfit, their_outfit, iid, openly)


def _open_debts(conn, me: int, target: int) -> list:
    rows = conn.execute("SELECT * FROM credit_agreements WHERE borrower_actor_id=? AND outstanding>0 "
                        "AND status IN ('current','late','defaulted') ORDER BY id", (target,)).fetchall()
    return [r for r in rows if r["lender_actor_id"] == me or (
        r["lender_enterprise_id"] is not None and ledger.can_draw(conn, me, ("business", int(r["lender_enterprise_id"]))))]


def _concede(conn, me, target, name, what, d, amount, debts, my_outfit, their_outfit, iid, openly) -> dict:
    mine: ledger.Holder = ("person", _authority(me, d))
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
        still = sum(float(r["outstanding"]) for r in _open_debts(conn, _authority(me, d), target))
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


def settle_accepted(conn: sqlite3.Connection, interaction, player_actor_id: int) -> dict | None:
    """The protagonist accepted a counter-offer to one of his operations: carry the operation out on its terms."""
    import json
    terms = json.loads(interaction["terms_json"] or "{}")
    po = terms.get("player_operation")
    if not isinstance(po, dict) or po.get("op") not in ("hire", "lend", "demand", "trade"):
        return None
    details = {**(po.get("details") or {}), "_accepted": int(interaction["id"])}
    return execute(conn, int(player_actor_id), str(po["op"]), target_actor_id=int(interaction["proposer_actor_id"]),
                   details=details, intent=str(interaction["rationale"] or "accepted counter-offer"), _trusted=True)


def _org_behind(conn, actor_id: int | None, business) -> tuple[int | None, int | None]:
    """The outfit that stands behind a victim, and the zone: the victim's own outfit, else the protector of the business
    (or of a business the victim owns), else the outfit linked to it, else whoever holds the ground where it stands."""
    def protector(enterprise_id: int):
        r = conn.execute("SELECT protector_organization_id,zone_id FROM underworld_protection_accounts WHERE enterprise_id=? AND status='active' ORDER BY id LIMIT 1", (enterprise_id,)).fetchone()
        if r:
            return int(r[0]), (int(r[1]) if r[1] is not None else None)
        r = conn.execute("SELECT organization_id,zone_id FROM underworld_business_links WHERE enterprise_id=? AND status='active' ORDER BY id LIMIT 1", (enterprise_id,)).fetchone()
        if r:
            return int(r[0]), (int(r[1]) if r[1] is not None else None)
        return None
    if business is None and actor_id is not None:
        r = conn.execute("SELECT organization_id FROM underworld_personnel WHERE actor_id=? AND status='active' ORDER BY authority DESC LIMIT 1", (actor_id,)).fetchone()
        if r:
            z = conn.execute("SELECT zone_id FROM underworld_zone_claims WHERE organization_id=? AND claim_kind='controller' AND status='active' LIMIT 1", (int(r[0]),)).fetchone()
            return int(r[0]), (int(z[0]) if z else None)
        for e in conn.execute("SELECT id FROM civilian_enterprises WHERE owner_actor_id=? AND status IN ('active','strained') ORDER BY id", (actor_id,)):
            got = protector(int(e[0]))
            if got:
                return got
        return None, None
    if business is not None:
        got = protector(int(business["id"]))
        if got:
            return got
        r = conn.execute("""SELECT c.organization_id,c.zone_id FROM underworld_zone_claims c JOIN underworld_zones z ON z.id=c.zone_id
                            WHERE c.claim_kind='controller' AND c.status='active' AND z.city_location_id=? ORDER BY c.strength DESC LIMIT 1""", (business["location_id"],)).fetchone()
        if r:
            return int(r[0]), int(r[1])
    return None, None


def _leave_trace(conn, my_outfit: int | None, victim_org: int | None, zone_id: int | None, kind: str, severity: float, hostility: float, meta: dict) -> int | None:
    """What a rival can see: an incident against its outfit, a harder relation, and heat on both."""
    import json
    if victim_org is None or (my_outfit is not None and victim_org == my_outfit):
        return None
    from .underworld_rebuild import add_heat, change_relation
    iid = int(conn.execute(
        """INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
           VALUES (?,?,?,?,?,?,'open',?)""", (_day(conn), zone_id, my_outfit, victim_org, kind, severity, json.dumps(meta, sort_keys=True))).lastrowid)
    if my_outfit is not None:
        change_relation(conn, my_outfit, victim_org, kind="rival", hostility_delta=hostility, respect_delta=-1, metadata={"player_operation": kind})
        add_heat(conn, my_outfit, public=1.5, violence=2 if kind != "extortion_attempt" else 0)
    add_heat(conn, victim_org, public=1.0, violence=2 if kind != "extortion_attempt" else 0)
    return iid



# ---------------------------------------------------------------- attack

INTENT_KINDS = ("drive_off", "beat", "kill")
HARM_SEVERITY = {"drive_off": 15, "beat": 45, "kill": 90}
CAPITAL_LOSS = {"drive_off": 0.05, "beat": 0.15, "kill": 0.4}


def _attack_rng(conn, me: int, subject, d: dict, day: int):
    import random
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    call_id = d.get("_call_id")
    return random.Random(f"attack:{seed}:{call_id}" if call_id else f"attack:{seed}:{me}:{subject}:{day}")


def _attack(conn, me: int, target: int | None, d: dict, intent: str) -> dict:
    kind = str(d.get("intent_kind") or "beat").lower()
    if kind not in INTENT_KINDS:
        return _refuse(f"intent_kind must be one of {', '.join(INTENT_KINDS)}.")
    business = None
    victim = None
    if d.get("business"):
        ref = str(d["business"])
        raw = ref.partition(":")[2] if ref.startswith("business:") else ""
        if not raw.isdigit():
            return _refuse("Name the place as business:<id>.")
        business = conn.execute("SELECT * FROM civilian_enterprises WHERE id=?", (int(raw),)).fetchone()
        if business is None:
            return _refuse(f"unknown business {raw}")
        if business["owner_actor_id"] == _authority(me, d) or ledger.can_draw(conn, _authority(me, d), ("business", int(business["id"]))):
            return _refuse("He will not wreck what is his own.")
        here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
        if business["location_id"] is None or here != business["location_id"]:
            return _refuse(f"{business['name']} is not here.")
    else:
        if target is None or target == me or not _living(conn, target):
            return _refuse("There is no living person named to attack.")
        if not _same_place(conn, me, target):
            return _refuse(f"{_name(conn, target)} is not here.")
        victim = target
    backers = _backer_list(conn, me, victim, d)
    if isinstance(backers, str):
        return _refuse(backers)
    day = _day(conn)
    rng = _attack_rng(conn, me, victim if business is None else f"b{business['id']}", d, day)

    attackers = [(me, _capacity(conn, me))] + [(i, c) for i, c in backers if i is not None]
    att_cap = _capacity(conn, me) + sum(c for _, c in backers) * (0.7 if d.get("_reluctant") else 1.0)
    if business is None:
        backing = {i for i, _ in backers}
        prot_ids, extra = _protectors(conn, victim, exclude=me)
        defenders = [victim] + [a for a in prot_ids if a not in backing]
        label = _name(conn, victim)
    else:
        defenders = [int(r[0]) for r in conn.execute(
            "SELECT s.actor_id FROM enterprise_staff s JOIN actors a ON a.id=s.actor_id "
            "WHERE s.enterprise_id=? AND s.status='active' AND a.current_location_id=? ORDER BY s.actor_id",
            (business["id"], business["location_id"])) if int(r[0]) != me and _living(conn, int(r[0]))]
        extra = _protectors(conn, int(business["owner_actor_id"]))[1] if business["owner_actor_id"] is not None else 0.0
        label = str(business["name"])
    def_cap = sum(_capacity(conn, a) for a in defenders) + extra
    roll = att_cap / max(0.01, def_cap) * rng.uniform(0.75, 1.25)

    lesser = attackers[1:] or attackers  # a lone attacker takes his own knocks; otherwise the weakest follower does
    weakest = min(lesser, key=lambda t: (t[1], t[0]))[0]
    front = defenders[0] if defenders else None
    plan: list[tuple[int, float]] = []
    if roll > 1.35:
        outcome = "won"
        if front is not None:
            plan.append((front, HARM_SEVERITY[kind]))
    elif roll < 0.75:
        outcome = "lost"
        plan.append((weakest, 35))
    else:
        outcome = "stalemate"
        plan.append((weakest, 20))
        if front is not None:
            plan.append((front, 20))

    heavy = kind == "kill"
    if business is None:
        verb = {"drive_off": "drove off", "beat": "beat", "kill": "went for the life of"}[kind]
        summary = {"won": f"He {verb} {label} and carried the day.", "lost": f"He moved on {label} and was beaten back.",
                   "stalemate": f"The clash with {label} ended with neither side the master."}[outcome]
    else:
        verb = {"drive_off": "frightened off the custom of", "beat": "wrecked", "kill": "set fire to"}[kind]
        summary = {"won": f"He {verb} {label}.", "lost": f"The people of {label} drove him off.",
                   "stalemate": f"The fight at {label} ended with nothing decided."}[outcome]
    event_id = _record(conn, me, "Attack" if business is None else "Attack on a place", summary,
                       severity=4 if heavy else 3, targets=(victim,) if victim is not None else ())

    if business is not None and outcome == "won":
        conn.execute("UPDATE civilian_enterprises SET capital=capital-capital*?, reputation=MAX(0,reputation-8), "
                     "labor_capacity=MAX(0,labor_capacity-10), updated_day=? WHERE id=?", (CAPITAL_LOSS[kind], day, business["id"]))
    from . import harm
    hurt = []
    my_org = _my_outfit(conn, _authority(me, d))
    for aid, sev in plan:
        if not _living(conn, aid):
            continue
        spot = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (aid,)).fetchone()[0]
        # The blow carries the outfit it came from, so a boss whose kin or lieutenant it fell on remembers who did it.
        inc = harm.record_harm(conn, aid, source_kind="player_operation", source_ref_id=event_id, severity=sev,
                               intent_class="hostile", location_id=spot,
                               metadata={"source_organization_id": my_org} if (my_org is not None and aid != me and aid not in {i for i, _ in attackers}) else None)
        hurt.append({"name": _name(conn, aid), "how": inc["outcome"]})

    foe = victim if business is None else business["owner_actor_id"]
    if foe is not None and int(foe) != me:
        adjust_relationship_pair(
            conn, me, int(foe), day,
            a_to_b={"trust_delta": -12.0, "stance_delta": -15.0, "resentment_delta": 8.0},
            b_to_a={"trust_delta": -15.0, "stance_delta": -18.0, "fear_delta": 5.0, "resentment_delta": 12.0})
    outfit = _my_outfit(conn, _authority(me, d))
    victim_org, trace_zone = _org_behind(conn, victim if business is None else None, business)
    _leave_trace(conn, outfit, victim_org, trace_zone, "attack_on_member" if business is None else "attack_on_client",
                 55 if heavy else 40, 30 if heavy else 15, {"enterprise_id": int(business["id"]) if business is not None else None,
                                                             "victim_actor_id": victim, "outcome": outcome, "player_operation": "attack"})
    if outfit is not None:
        from .underworld_rebuild import add_heat
        if business is None:
            add_heat(conn, outfit, public=3, violence=10 if heavy else 4, investigative=6 if heavy else 0)
        else:
            add_heat(conn, outfit, public=4, violence=8 if heavy else 4, investigative=5 if heavy else 0)
    return {"status": "applied", "outcome": outcome, "hurt": hurt, "summary": summary, "event_id": event_id}


# ---------------------------------------------------------------- trade

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _trade(conn, me: int, target: int | None, d: dict, intent: str) -> dict:
    deal = str(d.get("deal") or "").lower()
    if deal not in ("buy", "sell"):
        return _refuse("deal must be buy or sell.")
    ref = str(d.get("business") or "")
    raw = ref.partition(":")[2] if ref.startswith("business:") else ""
    if not raw.isdigit():
        return _refuse("Name the business as business:<id>.")
    biz = conn.execute("SELECT * FROM civilian_enterprises WHERE id=?", (int(raw),)).fetchone()
    if biz is None:
        return _refuse(f"unknown business {raw}")
    boss = _authority(me, d)
    if target is None or target in (me, boss) or not _living(conn, target):
        return _refuse("There is no living person named to deal with.")
    name = _name(conn, target)
    if not _same_place(conn, me, target):
        return _refuse(f"{name} is not here to deal with.")
    try:
        price = ledger.amount_of(d.get("amount", ""))
    except ValueError as e:
        return _refuse(str(e))
    value = float(biz["capital"]) + float(biz["cash"]) - float(biz["debt"])
    word = ledger.scale_word(price)
    if deal == "buy":
        if biz["owner_actor_id"] != target:
            return _refuse(f"{biz['name']} is not {name}'s to sell.")
        try:
            payer = ledger.parse_holder(d.get("from") or "me", boss, conn)
        except ValueError as e:
            return _refuse(str(e))
        payee: ledger.Holder = ("person", target)
        if not ledger.can_draw(conn, boss, payer):
            return _refuse("He has no right to draw on that purse.")
        if ledger.balance(conn, payer) + 1e-9 < price:
            return _refuse(f"There is not enough in {_holder_label(conn, payer, boss)} for a {word} price.")
        incentive = 2.0 * (price - value) / max(1.0, value)
        new_owner = boss
    else:
        if biz["owner_actor_id"] != boss:
            return _refuse("He cannot sell what is not his.")
        try:
            payee = ledger.parse_holder(d.get("to") or "me", boss, conn)
        except ValueError as e:
            return _refuse(str(e))
        payer = ("person", target)
        if ledger.balance(conn, payer) + 1e-9 < price:
            return _refuse(f"{name} cannot afford a {word} price.")
        incentive = 2.0 * (value - price) / max(1.0, value)
        new_owner = target
    day = _day(conn)
    iid, res = _offer(conn, me, target, "offer", day, intent, {"incentive": _clamp(incentive, -2.0, 2.0)}, op="trade", d=d)
    if iid is None:
        return res
    countered = _countered(conn, me, target, iid, res)
    if countered:
        return countered
    if res.response != "accept":
        summary = f"{name} would not agree a price for {biz['name']}."
        _record(conn, me, "Sale refused", summary, targets=(target,))
        return {"status": "refused", "summary": summary, "interaction_id": iid}
    try:
        ledger.transfer(conn, payer, payee, price, flow_kind="other", purpose=f"sale of {biz['name']}")
    except ValueError as e:
        return _refuse(str(e))
    old_owner = biz["owner_actor_id"]
    conn.execute("UPDATE civilian_enterprises SET owner_actor_id=?, updated_day=? WHERE id=?", (new_owner, day, biz["id"]))
    if old_owner is not None:
        conn.execute("DELETE FROM enterprise_staff WHERE enterprise_id=? AND actor_id=? AND role='owner'", (biz["id"], old_owner))
    from .merchant import add_enterprise_staff
    add_enterprise_staff(conn, int(biz["id"]), int(new_owner), role="owner", authority=100)
    summary = (f"{biz['name']} passes to him for a {word} price." if deal == "buy"
               else f"{biz['name']} passes to {name} for a {word} price.")
    _record(conn, me, "Business traded", summary, targets=(target,))
    return {"status": "applied", "summary": summary, "interaction_id": iid, "amount": word}


# ---------------------------------------------------------------- order

ORDERABLE = ("pay", "demand", "attack", "lend", "hire")
ATTACK_DANGER = {"drive_off": 1, "beat": 2, "kill": 3}


def _is_subordinate(conn, boss: int, sub: int) -> bool:
    if sub == boss:
        return False
    for r in conn.execute("SELECT organization_id FROM underworld_personnel WHERE actor_id=? AND status='active'", (sub,)):
        if ledger.can_draw(conn, boss, ("outfit", int(r[0]))) and _outranks(conn, boss, sub, ("outfit", int(r[0]))):
            return True
    return conn.execute("SELECT 1 FROM enterprise_staff s JOIN civilian_enterprises e ON e.id=s.enterprise_id "
                        "WHERE s.actor_id=? AND s.status='active' AND e.owner_actor_id=?", (sub, boss)).fetchone() is not None


HARD_ROLES = ("crew_leader", "enforcer", "lieutenant", "underboss")


def _role_bonus(conn, boss: int, sub: int) -> float:
    """Men whose trade is violence take an order to fight more readily than a clerk does."""
    row = conn.execute("SELECT role_kind FROM underworld_personnel WHERE actor_id=? AND status='active' LIMIT 1", (sub,)).fetchone()
    if row is not None:
        return 0.25 if str(row[0]) in HARD_ROLES else 0.10
    return 0.0


def _obedience(conn, boss: int, sub: int, do: str, toward: int | None, d: dict) -> str:
    """'yes', 'reluctantly' or 'refused': would this man carry out a risky order?"""
    stronger = toward is not None and _capacity(conn, toward) > _capacity(conn, sub)
    if do == "attack":
        base = ATTACK_DANGER.get(str(d.get("intent_kind") or "beat").lower(), 2)
    elif do == "demand" and (d.get("open") or stronger):
        base = 1
    else:
        return "yes"
    danger = base + (1 if stronger else 0)
    drives = conn.execute("SELECT loyalty,aggression,risk_tolerance FROM actor_drives WHERE actor_id=?", (sub,)).fetchone()
    loyalty, aggression, risk = (float(drives[0]), float(drives[1]), float(drives[2])) if drives else (0.5, 0.5, 0.5)
    from .relationships import relationship_view
    fear = relationship_view(conn, sub, boss)["fear"]
    import random
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    call_id = d.get("_call_id")
    rng = random.Random(f"order:{seed}:{call_id}" if call_id else f"order:{seed}:{boss}:{sub}:{do}:{toward}:{_day(conn)}")
    role_bonus = _role_bonus(conn, boss, sub)
    will = (0.9 * loyalty + 0.6 * fear / 100.0 + 0.4 * aggression + role_bonus
            - 0.18 * danger * (1.0 - risk) + rng.uniform(-0.15, 0.15))
    return "refused" if will < 0.35 else ("reluctantly" if will < 0.55 else "yes")


def _order(conn, me: int, target: int | None, d: dict, intent: str) -> dict:
    do = str(d.get("do") or "").lower()
    if do not in ORDERABLE:
        return _refuse(f"do must be one of {', '.join(ORDERABLE)}.")
    if target is None or not _living(conn, target) or not _is_subordinate(conn, me, target):
        return _refuse("He has no subordinate like that to give orders to.")
    sub = int(target)
    name = _name(conn, sub)
    toward = d.get("toward")
    if toward is not None:
        try:
            toward = int(toward)
        except (TypeError, ValueError):
            return _refuse("toward must be an actor id.")
        if not _living(conn, toward):
            return _refuse("There is no living person to direct that toward.")
        if not _same_place(conn, sub, toward):
            return _refuse(f"{name} is not in town with them.")
    mood = _obedience(conn, me, sub, do, toward, d)
    if mood == "refused":
        adjust_relationship_pair(conn, me, sub, _day(conn), a_to_b={"trust_delta": -4.0})
        summary = f"{name} would not do it."
        _record(conn, me, "Order refused", summary, targets=(sub,))
        return {"status": "refused", "summary": summary, "report": summary, "by": name, "obeyed": "refused"}
    inner = {k: v for k, v in d.items() if k not in ("do", "toward")}
    inner["_principal"] = me
    if mood == "reluctantly":
        inner["_reluctant"] = True
    res = execute(conn, sub, do, target_actor_id=toward, details=inner, intent=intent, _trusted=True)
    out = dict(res)
    out.update({"report": res.get("summary", ""), "by": name, "obeyed": mood})
    return out


# ---------------------------------------------------------------- dispatch

_HANDLERS: dict[str, Callable[..., dict]] = {"pay": _pay, "hire": _hire, "lend": _lend, "demand": _demand, "attack": _attack,
                                              "trade": _trade, "order": _order}


def execute(conn: sqlite3.Connection, actor_id: int, op: str, *, target_actor_id: int | None,
            details: dict, intent: str, _trusted: bool = False) -> dict:
    handler = _HANDLERS.get(op)
    if handler is None:
        if op in OPERATIONS:
            return _refuse("That kind of action is not available yet.")
        return _refuse(f"Unknown operation; use one of {', '.join(OPERATIONS)}.")
    d = details if isinstance(details, dict) else {}
    if not _trusted:  # internal keys (authority borrowed by an order, an agreement already given) never come from callers
        d = {k: v for k, v in d.items() if k not in ("_principal", "_reluctant", "_accepted")}
    conn.execute("SAVEPOINT player_op")
    try:
        result = handler(conn, int(actor_id), target_actor_id, d, intent)
    except ValueError as e:
        conn.execute("ROLLBACK TO SAVEPOINT player_op")
        conn.execute("RELEASE SAVEPOINT player_op")
        return _refuse(str(e))
    except BaseException:
        conn.execute("ROLLBACK TO SAVEPOINT player_op")
        conn.execute("RELEASE SAVEPOINT player_op")
        raise
    conn.execute("RELEASE SAVEPOINT player_op")
    return result
