"""Places: a building with a kind, an owner, a legal owner (a straw), a landlord, rent, upkeep and a condition that moves.

Place kinds, their upkeep and decay come from the package's business data. Upkeep is paid from the owner every 30 days
through the ledger; what the owner cannot pay lowers the condition by the kind's decay times the unpaid share. A gone
owner leaves the legal owner paying, else the place decays unpaid and says "no owner". Condition status words
(strained, derelict) are labels read from package figures, not limits. A building that reaches nothing is destroyed.
"""
from __future__ import annotations

import json
import sqlite3

from . import agreement_terms, business_data, ledger

PERIOD = 30


def _holder_parts(ref: str) -> tuple[str, int]:
    kind, _, raw = str(ref).partition(":")
    return kind, int(raw)


def make_place(conn: sqlite3.Connection, *, name: str, place_kind: str, location_id: int, owner_ref: str, day: int,
               legal_owner_ref: str | None = None, landlord_ref: str | None = None, rent_usd_30: float = 0.0,
               condition: float = 100.0, prestige: float = 50.0, enterprise_id: int | None = None) -> int:
    """A place and its details; returns the buildings id. With a landlord and rent, a rent term is made."""
    spec = business_data.place_kind(conn, place_kind)
    for ref in (owner_ref, legal_owner_ref, landlord_ref):
        if ref is not None:
            ledger.parse_holder(ref, 0, conn)
    okind, oid = _holder_parts(owner_ref)
    bid = int(conn.execute(
        """INSERT INTO buildings(name,building_kind,location_id,owner_actor_id,institution_actor_id,capacity,condition,prestige,
                                 maintenance_burden,completed_day,status,updated_day)
           VALUES (?,?,?,?,?,?,?,?,?,?,'active',?)""",
        (name, spec["building_kind"], int(location_id), oid if okind == "person" else None,
         oid if okind == "institution" else None, float(spec["base_capacity"]), float(condition), float(prestige),
         float(spec["upkeep_usd_30"]), int(day), int(day))).lastrowid)
    conn.execute(
        """INSERT INTO place_details(building_id,place_kind,owner_ref,legal_owner_ref,landlord_ref,rent_usd_30,upkeep_usd_30,
                                     enterprise_id,next_due_day) VALUES (?,?,?,?,?,?,?,?,?)""",
        (bid, place_kind, owner_ref, legal_owner_ref, landlord_ref, float(rent_usd_30), float(spec["upkeep_usd_30"]),
         enterprise_id, int(day) + PERIOD))
    if landlord_ref is not None and float(rent_usd_30) > 0:
        word = spec.get("rent_breach_word")
        if word is None:
            raise business_data.BusinessDataError(f"business.json: place_kinds.{place_kind}: rent_breach_word is needed for a rented place")
        tid = agreement_terms.add_term(conn, ref_kind="place", ref_id=bid, debtor_ref=owner_ref, creditor_ref=landlord_ref,
                                       amount_usd=float(rent_usd_30), first_due_day=int(day) + PERIOD, every_days=PERIOD,
                                       grace_days=int(spec.get("rent_grace_days", 0)), breach_word=word,
                                       purpose=f"rent for {name}", day=int(day))
        conn.execute("UPDATE place_details SET rent_term_id=? WHERE building_id=?", (tid, bid))
    return bid


def place(conn: sqlite3.Connection, building_id: int) -> dict | None:
    r = conn.execute(
        """SELECT b.id,b.name,b.building_kind,b.location_id,b.condition,b.status,b.prestige,b.capacity,d.*
           FROM buildings b JOIN place_details d ON d.building_id=b.id WHERE b.id=?""", (int(building_id),)).fetchone()
    if r is None:
        return None
    out = dict(r)
    out["legal_owner"] = r["legal_owner_ref"] or r["owner_ref"]
    out["who_pays_upkeep"] = r["owner_ref"]
    return out


def _label(conn: sqlite3.Connection, condition: float) -> str:
    cal = business_data.calibration(conn, "place_condition")
    if condition <= 0:
        return "destroyed"
    if condition < float(cal["derelict_below"]):
        return "derelict"
    if condition < float(cal["strained_below"]):
        return "strained"
    return "active"


def _set_condition(conn: sqlite3.Connection, building_id: int, condition: float, day: int) -> float:
    condition = max(0.0, min(100.0, float(condition)))
    conn.execute("UPDATE buildings SET condition=?,status=?,updated_day=? WHERE id=?",
                 (condition, _label(conn, condition), int(day), int(building_id)))
    return condition


def damage_place(conn: sqlite3.Connection, building_id: int, amount: float, cause: str, day: int) -> float:
    """Lower a place's condition; returns the new value. At nothing the building is destroyed."""
    r = conn.execute("SELECT condition,metadata_json FROM buildings WHERE id=?", (int(building_id),)).fetchone()
    meta = json.loads(r["metadata_json"] or "{}")
    meta.setdefault("damage", []).append({"day": int(day), "amount": float(amount), "cause": cause})
    conn.execute("UPDATE buildings SET metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), int(building_id)))
    return _set_condition(conn, building_id, float(r["condition"]) - float(amount), day)


def transfer_place(conn: sqlite3.Connection, building_id: int, new_owner_ref: str, day: int, *, legal: bool = True) -> None:
    """The place passes to a new owner. With `legal` the title moves too; without it only the man who really owns it changes
    and the straw named on the title stays."""
    ledger.parse_holder(new_owner_ref, 0, conn)
    d = conn.execute("SELECT rent_term_id FROM place_details WHERE building_id=?", (int(building_id),)).fetchone()
    kind, i = _holder_parts(new_owner_ref)
    if legal:
        conn.execute("UPDATE place_details SET owner_ref=?,legal_owner_ref=NULL WHERE building_id=?", (new_owner_ref, int(building_id)))
    else:
        conn.execute("UPDATE place_details SET owner_ref=? WHERE building_id=?", (new_owner_ref, int(building_id)))
    conn.execute("UPDATE buildings SET owner_actor_id=?,institution_actor_id=?,updated_day=? WHERE id=?",
                 (i if kind == "person" else None, i if kind == "institution" else None, int(day), int(building_id)))
    if d is not None and d["rent_term_id"] is not None:
        conn.execute("UPDATE agreement_terms SET debtor_ref=? WHERE id=? AND status='active'", (new_owner_ref, int(d["rent_term_id"])))


def next_places_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    r = conn.execute("""SELECT MIN(d.next_due_day) FROM place_details d JOIN buildings b ON b.id=d.building_id
                        WHERE b.status<>'destroyed' AND d.next_due_day>? AND d.next_due_day<=?""", (int(after_day), int(end_day))).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _payer(conn: sqlite3.Connection, d: sqlite3.Row) -> str | None:
    for ref in (d["owner_ref"], d["legal_owner_ref"]):
        if ref is not None:
            got = agreement_terms._resolve(conn, ref)
            if got is not None:
                return got
    return None


def _due_one(conn: sqlite3.Connection, d: sqlite3.Row) -> None:
    bid, due = int(d["building_id"]), int(d["next_due_day"])
    b = conn.execute("SELECT condition,metadata_json FROM buildings WHERE id=?", (bid,)).fetchone()
    spec = business_data.place_kind(conn, d["place_kind"])
    upkeep = float(d["upkeep_usd_30"])
    payer = _payer(conn, d)
    paid, reason = 0.0, None
    if payer is None:
        reason = "no owner"
    elif upkeep > 0:
        paid = float(ledger.spend(conn, ledger.parse_holder(payer, 0), upkeep, purpose=f"upkeep of place {bid}", allow_partial=True) or 0.0) \
            if ledger.balance(conn, ledger.parse_holder(payer, 0)) > 1e-9 else 0.0
    short = max(0.0, upkeep - paid)
    cond = float(b["condition"])
    if short > 1e-9 and upkeep > 0:
        cond -= float(spec["decay_per_30_unpaid"]) * (short / upkeep)
        if reason is None:
            reason = "owner short of money"
    meta = json.loads(b["metadata_json"] or "{}")
    if reason:
        meta["upkeep"] = {"day": due, "reason": reason}
        conn.execute("UPDATE buildings SET metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), bid))
    _set_condition(conn, bid, cond, due)
    conn.execute("UPDATE place_details SET next_due_day=? WHERE building_id=?", (due + PERIOD, bid))


def process_due_places(conn: sqlite3.Connection, day: int) -> dict:
    """Settle every upkeep period up to `day`, earliest first. Returns {building_id: periods settled}; empty for a package with no business data."""
    done: dict[int, int] = {}
    if business_data.load(conn) is None:
        return done
    while True:
        d = conn.execute("""SELECT d.* FROM place_details d JOIN buildings b ON b.id=d.building_id
                            WHERE b.status<>'destroyed' AND d.next_due_day<=? ORDER BY d.next_due_day, d.building_id LIMIT 1""",
                         (int(day),)).fetchone()
        if d is None:
            return done
        _due_one(conn, d)
        done[int(d["building_id"])] = done.get(int(d["building_id"]), 0) + 1
