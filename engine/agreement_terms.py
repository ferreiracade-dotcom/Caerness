"""Terms that fall due between two parties, paid through the ledger, with a path to take when they are missed.

A term is a payment (once, or every N days) from a debtor to a creditor. Each due date is settled in date order, so a
long time-skip gives the same missed counts and breaches as a day-by-day run. A shortfall carries as `owed_usd`; when the
oldest unpaid date is older than the grace the term is breached once, by the path its package word maps to
(tension between organisations, a debt, a grudge, or a civil claim that nothing reads yet). A party who is gone and has
no one standing in leaves the term `orphaned`, with the reason written down. No cap, no cooldown.
"""
from __future__ import annotations

import json
import sqlite3

from . import business_data, ledger, org_dealings, org_money, org_tension, orgs, relationships

_STOP = 1e-9


# ---- who is a party ----

def _org_of(conn: sqlite3.Connection, ref: str) -> int | None:
    """The organisation a holder ref stands for: an organisation's own actor, the business an organisation owns, or the person
    who holds a purse role in one (the first such seat)."""
    kind, _, raw = str(ref).partition(":")
    if not raw.strip().lstrip("-").isdigit():
        return None
    i = int(raw)
    if kind == "institution":
        return i if conn.execute("SELECT 1 FROM org_profiles WHERE org_actor_id=?", (i,)).fetchone() else None
    if kind == "business":
        r = conn.execute("SELECT institution_actor_id FROM civilian_enterprises WHERE id=?", (i,)).fetchone()
        if r and r[0] is not None and conn.execute("SELECT 1 FROM org_profiles WHERE org_actor_id=?", (int(r[0]),)).fetchone():
            return int(r[0])
        return None
    if kind == "person":
        for seat in orgs.seats_of(conn, i):
            if seat["status"] != "active":
                continue
            roles = set(orgs.kind_rules(conn, int(seat["org_actor_id"])).get("purse_roles") or [])
            if seat["role_key"] in roles:
                return int(seat["org_actor_id"])
    return None


def _resolve(conn: sqlite3.Connection, ref: str) -> str | None:
    """A holder ref that can still pay or be paid, or None. A dead person's term passes to his household's designated heir,
    else to the household's living head; an organisation's obligations are paid from its head's purse."""
    kind, _, raw = str(ref).partition(":")
    if kind not in ledger.KINDS or not raw.strip().lstrip("-").isdigit():
        return None
    i = int(raw)
    try:
        ledger._check_exists(conn, (kind, i))
    except ValueError:
        return None
    if kind == "person":
        if orgs.is_living(conn, i):
            return ref
        row = conn.execute("SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?", (i,)).fetchone()
        hh = int(row[0]) if row and row[0] is not None else None
        if hh is None:
            return None
        plan = conn.execute("SELECT designated_heir_actor_id FROM household_succession_plans WHERE household_id=?", (hh,)).fetchone()
        for cand in ((plan[0] if plan else None), (conn.execute("SELECT head_actor_id FROM households WHERE id=?", (hh,)).fetchone() or [None])[0]):
            if cand is not None and int(cand) != i and orgs.is_living(conn, int(cand)):
                return f"person:{int(cand)}"
        return None
    org = _org_of(conn, ref) if kind == "institution" else None
    if org is not None:
        return org_money.purse_ref(conn, org) or ref
    return ref


# ---- terms ----

def add_term(conn: sqlite3.Connection, *, ref_kind: str, ref_id: int | None, debtor_ref: str, creditor_ref: str,
             amount_usd: float, first_due_day: int, every_days: int | None, grace_days: int, breach_word: str,
             purpose: str, day: int) -> int:
    """A payment owed from `debtor_ref` to `creditor_ref`; every_days=None is a one-time payment. The breach word must be one the
    package declares."""
    business_data.breach_path(conn, breach_word)
    if every_days is not None and int(every_days) <= 0:
        raise ValueError("every_days must be above zero (or None for a one-time payment)")
    for ref in (debtor_ref, creditor_ref):
        ledger.parse_holder(ref, 0, conn)
    return int(conn.execute(
        """INSERT INTO agreement_terms(ref_kind,ref_id,debtor_ref,creditor_ref,amount_usd,every_days,next_due_day,grace_days,
                                       breach_word,purpose,created_day) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ref_kind, ref_id, debtor_ref, creditor_ref, float(amount_usd), None if every_days is None else int(every_days),
         int(first_due_day), int(grace_days), breach_word, purpose, int(day))).lastrowid)


def end_term(conn: sqlite3.Connection, term_id: int, day: int, reason: str) -> None:
    conn.execute("UPDATE agreement_terms SET status='ended' WHERE id=? AND status='active'", (int(term_id),))
    conn.execute("INSERT INTO agreement_breaches(term_id,day,path,owed_usd,effect_json) VALUES (?,?,?,?,?)",
                 (int(term_id), int(day), "ended", 0.0, json.dumps({"reason": reason})))


def next_terms_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    r = conn.execute("SELECT MIN(next_due_day) FROM agreement_terms WHERE status='active' AND next_due_day>? AND next_due_day<=?",
                     (int(after_day), int(end_day))).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _orphan(conn: sqlite3.Connection, t: sqlite3.Row, day: int, why: str) -> None:
    conn.execute("UPDATE agreement_terms SET status='orphaned' WHERE id=?", (int(t["id"]),))
    conn.execute("INSERT INTO agreement_breaches(term_id,day,path,owed_usd,effect_json) VALUES (?,?,?,?,?)",
                 (int(t["id"]), int(day), "orphaned", float(t["owed_usd"]), json.dumps({"reason": why})))


def _settle(conn: sqlite3.Connection, t: sqlite3.Row, due: int) -> None:
    """One due date of one term."""
    tid = int(t["id"])
    debtor, creditor = _resolve(conn, t["debtor_ref"]), _resolve(conn, t["creditor_ref"])
    if debtor is None or creditor is None:
        _orphan(conn, t, due, "debtor is gone" if debtor is None else "creditor is gone")
        return
    if debtor != t["debtor_ref"] or creditor != t["creditor_ref"]:
        conn.execute("UPDATE agreement_terms SET debtor_ref=?,creditor_ref=? WHERE id=?", (debtor, creditor, tid))
    owe = float(t["amount_usd"]) + float(t["owed_usd"])
    paid = 0.0
    if owe > _STOP and ledger.balance(conn, ledger.parse_holder(debtor, 0)) > _STOP:
        paid = float(ledger.transfer(conn, ledger.parse_holder(debtor, 0), ledger.parse_holder(creditor, 0), owe,
                                     flow_kind="other", purpose=t["purpose"], allow_partial=True) or 0.0)
    short = owe - paid
    missed, since = int(t["missed_count"]), t["unpaid_since_day"]
    if short > _STOP:
        missed += 1
        since = due if since is None else since
        owed = short
    else:
        owed, since = 0.0, None
    breached = owed > _STOP and int(due) - int(since) > int(t["grace_days"])
    every = t["every_days"]
    if breached:
        nxt = int(t["next_due_day"])
    elif every is not None:
        nxt = int(t["next_due_day"]) + int(every)
    elif owed > _STOP:
        nxt = int(since) + int(t["grace_days"]) + 1  # a one-time payment still owing: try again when the grace has run
    else:
        nxt = int(t["next_due_day"])
    status = "breached" if breached else ("ended" if (every is None and owed <= _STOP) else "active")
    conn.execute("UPDATE agreement_terms SET owed_usd=?,missed_count=?,unpaid_since_day=?,next_due_day=?,status=? WHERE id=?",
                 (owed, missed, since, nxt, status, tid))
    if breached:
        breach(conn, tid, due)


def process_due_terms(conn: sqlite3.Connection, day: int) -> dict:
    """Settle every due date up to `day`, earliest first (ties by term id). Returns what happened, by term id."""
    done: dict[int, int] = {}
    if business_data.load(conn) is None:
        return done
    while True:
        t = conn.execute("""SELECT * FROM agreement_terms WHERE status='active' AND next_due_day<=?
                            ORDER BY next_due_day, id LIMIT 1""", (int(day),)).fetchone()
        if t is None:
            return done
        _settle(conn, t, int(t["next_due_day"]))
        done[int(t["id"])] = done.get(int(t["id"]), 0) + 1


# ---- breach ----

def breach(conn: sqlite3.Connection, term_id: int, day: int) -> int:
    """Take the term's breach path once; returns the agreement_breaches id."""
    t = conn.execute("SELECT * FROM agreement_terms WHERE id=?", (int(term_id),)).fetchone()
    path = business_data.breach_path(conn, t["breach_word"])
    cal = business_data.calibration(conn, "breach")
    owed = float(t["owed_usd"])
    c_org, d_org = _org_of(conn, t["creditor_ref"]), _org_of(conn, t["debtor_ref"])
    effect: dict = {"word": t["breach_word"], "calibration": dict(cal)}
    c_person = int(t["creditor_ref"].split(":")[1]) if t["creditor_ref"].startswith("person:") else None
    d_person = int(t["debtor_ref"].split(":")[1]) if t["debtor_ref"].startswith("person:") else None

    def between_people(extra: str) -> None:
        if c_person is None or d_person is None:
            effect["note"] = "no person on one side: nothing to sour"
            return
        relationships.adjust_relationship(conn, c_person, d_person, int(day), resentment_delta=float(cal["creditor_resentment"]),
                                          trust_delta=float(cal["creditor_trust"]))
        share = float(cal["debtor_share"])
        relationships.adjust_relationship(conn, d_person, c_person, int(day), resentment_delta=float(cal["creditor_resentment"]) * share,
                                          trust_delta=float(cal["creditor_trust"]) * share)
        effect["effect"] = extra

    if path == "tension":
        if c_org is not None and d_org is not None:
            delta = owed / 1000.0 * float(cal["tension_per_1000_usd"])
            org_tension.add(conn, c_org, d_org, "breach", delta, int(day), note=f"term {term_id}: {t['purpose']}")
            effect["tension_delta"] = delta
        else:
            effect["note"] = "tension needs two organisations; none on at least one side"
    elif path == "debt":
        if c_org is not None and d_org is not None:
            effect["debt_id"] = org_dealings.owe(conn, c_org, d_org, owed, f"term {term_id}: {t['purpose']}", int(day))
        else:
            between_people("street debt between persons: no org")
    elif path == "grudge":
        between_people("grudge between persons")
    else:  # claim: civil law is not built, so nothing reads this yet
        effect["unread"] = "civil claim"
    return int(conn.execute("INSERT INTO agreement_breaches(term_id,day,path,owed_usd,effect_json) VALUES (?,?,?,?,?)",
                            (int(term_id), int(day), path, owed, json.dumps(effect, sort_keys=True))).lastrowid)
