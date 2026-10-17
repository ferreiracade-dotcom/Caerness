"""Money layer: one place that moves coin between purses, businesses, outfit treasuries, households, institutions and polities."""
from __future__ import annotations

import math
import re
import sqlite3
from typing import Any

from .underworld_rebuild import _record_economic_flow

Holder = tuple[str, int]

KINDS = ("person", "business", "outfit", "household", "institution", "polity")
_TABLES = {"person": "actors", "business": "civilian_enterprises", "outfit": "underworld_organizations", "household": "households",
           "institution": "actors", "polity": "political_polities"}

SCALES = {"token": 0.2, "small": 1.0, "modest": 3.0, "substantial": 8.0, "large": 20.0, "fortune": 60.0}


def parse_holder(ref: str, me: int, conn: sqlite3.Connection | None = None) -> Holder:
    ref = str(ref).strip()
    if ref == "me":
        h: Holder = ("person", int(me))
    else:
        kind, sep, raw = ref.partition(":")
        if not sep or kind not in KINDS or not raw.strip().lstrip("-").isdigit():
            raise ValueError("holder must be me, person:<id>, business:<id>, outfit:<id>, household:<id>, institution:<id> or polity:<id>")
        h = (kind, int(raw))
    if conn is not None:
        _check_exists(conn, h)
    return h


def _check_exists(conn: sqlite3.Connection, h: Holder) -> None:
    if not conn.execute(f"SELECT 1 FROM {_TABLES[h[0]]} WHERE id=?", (h[1],)).fetchone():
        raise ValueError(f"unknown {h[0]} {h[1]}")


def _route(conn: sqlite3.Connection, h: Holder) -> Holder:
    """An institution that is a polity's own seat keeps its money in the polity treasury; any other institution holds a purse like a person."""
    if h[0] == "institution":
        row = conn.execute("SELECT id FROM political_polities WHERE institution_actor_id=?", (h[1],)).fetchone()
        return ("polity", int(row[0])) if row else ("person", h[1])
    return h


def balance(conn: sqlite3.Connection, h: Holder) -> float:
    kind, i = _route(conn, h)
    if kind == "polity":
        row = conn.execute("SELECT cash FROM regional_public_treasuries WHERE polity_id=?", (i,)).fetchone()
        return float(row[0]) if row else 0.0
    if kind == "person":
        row = conn.execute("SELECT liquid_wealth FROM underworld_leader_wealth WHERE actor_id=?", (i,)).fetchone()
        if row:
            return float(row[0])
        row = conn.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type='cash'", (i,)).fetchone()
        return float(row[0]) if row else 0.0
    sql = {
        "business": "SELECT cash FROM civilian_enterprises WHERE id=?",
        "outfit": "SELECT treasury FROM underworld_organizations WHERE id=?",
        "household": "SELECT liquidity FROM households WHERE id=?",
    }[kind]
    row = conn.execute(sql, (i,)).fetchone()
    return float(row[0]) if row else 0.0


def _debit(conn: sqlite3.Connection, h: Holder, amount: float) -> None:
    kind, i = _route(conn, h)
    if kind == "polity":
        conn.execute("UPDATE regional_public_treasuries SET cash=MAX(0,cash-?) WHERE polity_id=?", (amount, i))
    elif kind == "person":
        if conn.execute("SELECT 1 FROM underworld_leader_wealth WHERE actor_id=?", (i,)).fetchone():
            conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=MAX(0,liquid_wealth-?) WHERE actor_id=?", (amount, i))
        else:
            conn.execute("UPDATE resources SET amount=MAX(0,amount-?) WHERE actor_id=? AND resource_type='cash'", (amount, i))
    elif kind == "business":
        conn.execute("UPDATE civilian_enterprises SET cash=MAX(0,cash-?) WHERE id=?", (amount, i))
    elif kind == "outfit":
        conn.execute("UPDATE underworld_organizations SET treasury=MAX(0,treasury-?) WHERE id=?", (amount, i))
    else:
        conn.execute("UPDATE households SET liquidity=MAX(0,liquidity-?),wealth=MAX(0,wealth-?) WHERE id=?", (amount, amount, i))


def _credit(conn: sqlite3.Connection, h: Holder, amount: float) -> None:
    kind, i = _route(conn, h)
    if kind == "polity":
        if not conn.execute("SELECT 1 FROM regional_public_treasuries WHERE polity_id=?", (i,)).fetchone():
            conn.execute("INSERT INTO regional_public_treasuries(polity_id,cash) VALUES (?,0)", (i,))
        conn.execute("UPDATE regional_public_treasuries SET cash=cash+? WHERE polity_id=?", (amount, i))
    elif kind == "person":
        if conn.execute("SELECT 1 FROM underworld_leader_wealth WHERE actor_id=?", (i,)).fetchone():
            conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=liquid_wealth+? WHERE actor_id=?", (amount, i))
        elif conn.execute("SELECT 1 FROM resources WHERE actor_id=? AND resource_type='cash'", (i,)).fetchone():
            conn.execute("UPDATE resources SET amount=amount+? WHERE actor_id=? AND resource_type='cash'", (amount, i))
        else:
            conn.execute("INSERT INTO resources(actor_id,resource_type,amount) VALUES (?,'cash',?)", (i, amount))
    elif kind == "business":
        conn.execute("UPDATE civilian_enterprises SET cash=cash+? WHERE id=?", (amount, i))
    elif kind == "outfit":
        conn.execute("UPDATE underworld_organizations SET treasury=treasury+? WHERE id=?", (amount, i))
    else:
        conn.execute("UPDATE households SET liquidity=liquidity+?,wealth=wealth+? WHERE id=?", (amount, amount, i))


def _endpoint(prefix: str, h: Holder) -> dict[str, int]:
    col = {"person": "actor_id", "business": "enterprise_id", "outfit": "organization_id", "household": "household_id",
           "institution": "actor_id"}.get(h[0])
    return {f"{prefix}_{col}": h[1]} if col else {}


def transfer(conn: sqlite3.Connection, src: Holder, dst: Holder, amount: float, *,
             flow_kind: str, purpose: str, allow_partial: bool = False) -> float:
    amount = float(amount)
    if amount <= 0:
        raise ValueError("amount must be positive")
    _check_exists(conn, src)
    _check_exists(conn, dst)
    have = balance(conn, src)
    if amount > have + 1e-9:
        if not allow_partial:
            raise ValueError("not enough money")
        amount = have
    if amount <= 0:
        return 0.0
    _debit(conn, src, amount)
    _credit(conn, dst, amount)
    s_end, d_end = _endpoint("source", src), _endpoint("target", dst)
    if s_end and d_end:  # a polity treasury has no flow column: the player_operation event records that leg
        _record_economic_flow(conn, flow_kind, amount, **s_end, **d_end, metadata={"purpose": purpose})
    return amount


def spend(conn: sqlite3.Connection, src: Holder, amount: float, *, purpose: str, allow_partial: bool = True) -> float:
    """Money that leaves a purse for goods, upkeep, favours or a fund: no recipient is named. Returns what was spent."""
    amount = float(amount)
    if amount <= 0:
        raise ValueError("amount must be positive")
    _check_exists(conn, src)
    have = balance(conn, src)
    if amount > have + 1e-9:
        if not allow_partial:
            raise ValueError("not enough money")
        amount = have
    if amount <= 0:
        return 0.0
    _debit(conn, src, amount)
    return amount


_SHARES = {"all": 1.0, "everything": 1.0, "the lot": 1.0, "whole": 1.0, "half": 0.5, "third": 1 / 3, "quarter": 0.25,
           "fifth": 0.2, "tenth": 0.1}


def amount_of(word, base: float | None = None) -> float:
    """A sum in engine units from a scale word, a number (37, "37 silver"), a multiple of a scale word ("three modest")
    or a share of ``base`` ("half", "all", "a third of the till", "25%"). Raises ValueError saying how to put it."""
    if isinstance(word, bool):
        raise ValueError("amount must be a number, a scale word or a share")
    if isinstance(word, (int, float)):
        if not math.isfinite(word) or word <= 0:
            raise ValueError("amount must be positive")
        return float(word)
    key = str(word).strip().lower()
    if key in SCALES:
        return SCALES[key]
    m = re.match(r"^(\d+(?:\.\d+)?)\s*%", key)
    if m and base is not None:
        return float(m.group(1)) / 100.0 * base
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(token|small|modest|substantial|large|fortune)s?\b", key)
    if m:
        return float(m.group(1)) * SCALES[m.group(2)]
    m = re.match(r"^(\d+(?:\.\d+)?)(?:\s|$)", key)
    if m and float(m.group(1)) > 0:
        return float(m.group(1))
    for share, frac in _SHARES.items():
        if re.match(rf"^(?:a |the |one )?{share}\b", key):
            if base is None:
                break
            return frac * base
    raise ValueError("amount not understood: give a number, a scale word (" + ", ".join(SCALES) + ") or a share such as half or all")


def scale_word(x: float) -> str:
    if x < 0.05:
        return "nothing"
    return min(SCALES, key=lambda k: abs(math.log(x) - math.log(SCALES[k])))


_LEADER = re.compile(r"head|lead|lord|master|abbot|abbess|prior|patriarch|chief|chair|treasur|bursar|steward|ruler|elder|warden|director|principal|founder|owner")


def can_draw(conn: sqlite3.Connection, me: int, h: Holder) -> bool:
    kind, i = h
    if kind == "person":
        return i == int(me)
    if kind == "business":
        from .merchant import authorized_enterprises
        return any(int(r["id"]) == i for r in authorized_enterprises(conn, int(me), minimum_authority=60))
    if kind == "outfit":
        return conn.execute(
            "SELECT 1 FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active' AND role_kind IN ('boss','underboss')",
            (int(me), i)).fetchone() is not None
    if kind == "polity":
        return conn.execute("SELECT 1 FROM political_polities WHERE id=? AND ruler_actor_id=?", (i, int(me))).fetchone() is not None
    if kind == "institution":
        if conn.execute("SELECT 1 FROM political_polities WHERE institution_actor_id=? AND ruler_actor_id=?", (i, int(me))).fetchone():
            return True
        return any(_LEADER.search(f"{r[0] or ''} {r[1] or ''}".lower()) for r in conn.execute(
            "SELECT role_text,membership_kind FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=? AND status='active'",
            (i, int(me))))
    return conn.execute("SELECT 1 FROM households WHERE id=? AND head_actor_id=? AND status='active'", (i, int(me))).fetchone() is not None
