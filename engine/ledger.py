"""Money layer: one place that moves coin between purses, businesses, outfit treasuries and households."""
from __future__ import annotations

import math
import sqlite3
from typing import Any

from .underworld_rebuild import _record_economic_flow

Holder = tuple[str, int]

KINDS = ("person", "business", "outfit", "household")
_TABLES = {"person": "actors", "business": "civilian_enterprises", "outfit": "underworld_organizations", "household": "households"}

SCALES = {"token": 0.2, "small": 1.0, "modest": 3.0, "substantial": 8.0, "large": 20.0, "fortune": 60.0}


def parse_holder(ref: str, me: int, conn: sqlite3.Connection | None = None) -> Holder:
    ref = str(ref).strip()
    if ref == "me":
        h: Holder = ("person", int(me))
    else:
        kind, sep, raw = ref.partition(":")
        if not sep or kind not in KINDS or not raw.strip().lstrip("-").isdigit():
            raise ValueError("holder must be me, person:<id>, business:<id>, outfit:<id> or household:<id>")
        h = (kind, int(raw))
    if conn is not None:
        _check_exists(conn, h)
    return h


def _check_exists(conn: sqlite3.Connection, h: Holder) -> None:
    if not conn.execute(f"SELECT 1 FROM {_TABLES[h[0]]} WHERE id=?", (h[1],)).fetchone():
        raise ValueError(f"unknown {h[0]} {h[1]}")


def balance(conn: sqlite3.Connection, h: Holder) -> float:
    kind, i = h
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
    kind, i = h
    if kind == "person":
        if conn.execute("SELECT 1 FROM underworld_leader_wealth WHERE actor_id=?", (i,)).fetchone():
            conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=MAX(0,liquid_wealth-?) WHERE actor_id=?", (amount, i))
        else:
            conn.execute("UPDATE resources SET amount=MAX(0,amount-?) WHERE actor_id=? AND resource_type='cash'", (amount, i))
    elif kind == "business":
        conn.execute("UPDATE civilian_enterprises SET cash=MAX(0,cash-?) WHERE id=?", (amount, i))
    elif kind == "outfit":
        conn.execute("UPDATE underworld_organizations SET treasury=MAX(0,treasury-?) WHERE id=?", (amount, i))
    else:
        conn.execute("UPDATE households SET liquidity=MAX(0,liquidity-?) WHERE id=?", (amount, i))


def _credit(conn: sqlite3.Connection, h: Holder, amount: float) -> None:
    kind, i = h
    if kind == "person":
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
    col = {"person": "actor_id", "business": "enterprise_id", "outfit": "organization_id", "household": "household_id"}[h[0]]
    return {f"{prefix}_{col}": h[1]}


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
    _record_economic_flow(conn, flow_kind, amount, **_endpoint("source", src), **_endpoint("target", dst),
                          metadata={"purpose": purpose})
    return amount


def amount_of(word: str) -> float:
    key = str(word).strip().lower()
    if key not in SCALES:
        raise ValueError("amount must be one of: " + ", ".join(SCALES))
    return SCALES[key]


def scale_word(x: float) -> str:
    if x < 0.05:
        return "nothing"
    return min(SCALES, key=lambda k: abs(math.log(x) - math.log(SCALES[k])))


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
    return conn.execute("SELECT 1 FROM households WHERE id=? AND head_actor_id=?", (i, int(me))).fetchone() is not None
