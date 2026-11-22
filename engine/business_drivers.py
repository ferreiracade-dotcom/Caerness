"""The shared business drivers: what moves a business or a venture, each with its value and where it came from.

A reading is eight multipliers around 1.0, each carrying a `source` in words. The total is their product; nothing
clamps it. Only the latest reading per subject is kept (no per-tick history). Package words (sector seasonality and
dated shocks) come from the package's business data; a world with none gets 1.0 and says so.
"""
from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import date

from . import business, business_data, design, world_calendar
from .world_package import package_for

_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December")
KEYS = ("calendar", "shock", "demand", "form", "condition", "capacity", "rivals", "roll")


@dataclass
class Factor:
    value: float
    source: str


def _day_date(conn: sqlite3.Connection, day: int):
    return world_calendar._date(package_for(conn), int(day))


def _calendar(conn, data, sector: str, day: int) -> Factor:
    months = ((data or {}).get("seasonality") or {}).get(sector)
    if not months:
        return Factor(1.0, f"seasonality: no seasonality given for {sector}")
    d = _day_date(conn, day)
    return Factor(float(months[d.month - 1]), f"seasonality: {sector}, {_MONTHS[d.month - 1]}")


def _shock(conn, data, sector: str, day: int) -> Factor:
    d = _day_date(conn, day)
    value, names = 1.0, []
    for s in (data or {}).get("shocks") or []:
        mult = (s.get("sectors") or {}).get(sector)
        if mult is None:
            continue
        start = date.fromisoformat(s["from"])
        end = date.fromisoformat(s["to"]) if s.get("to") else None
        if start <= d and (end is None or d <= end):
            value *= float(mult)
            names.append(f"{s['name']} x{mult}")
    return Factor(value, "shocks: " + ("; ".join(names) if names else f"none active for {sector}"))


def _rivals(conn, subject_kind: str, subject_id: int, sector: str, location_id: int | None) -> Factor:
    if location_id is None:
        return Factor(1.0, "rivals: no place given")
    rows = conn.execute(
        """SELECT e.id, e.name FROM civilian_enterprises e
           JOIN enterprise_business_profiles p ON p.enterprise_id=e.id
           JOIN business_archetypes a ON a.id=p.archetype_id
           WHERE e.location_id=? AND e.status='active' AND a.sector=? ORDER BY e.id""", (int(location_id), sector)).fetchall()
    mine = int(subject_id) if subject_kind == "enterprise" else None
    others = [r for r in rows if int(r["id"]) != mine]
    n = len(others)
    named = ", ".join(r["name"] for r in others[:3])
    return Factor(1.0 / (1.0 + 0.15 * n), f"rivals: {n} in {sector} here" + (f" ({named})" if named else ""))


def reading(conn: sqlite3.Connection, subject_kind: str, subject_id: int, day: int, *, sector: str,
            location_id: int | None, quality: float = 50.0, condition: float = 100.0,
            capacity_used: float | None = None, demand_weights: dict[str, float] | None = None) -> dict[str, Factor]:
    data = business_data.load(conn)
    ctx = business.commercial_context(conn, location_id) if location_id is not None else {}
    if demand_weights:
        score = business._demand_score(demand_weights, ctx)
        demand = Factor(score / 50.0, f"demand: weighted local conditions score {score:.0f} of 100 against a par of 50")
    else:
        demand = Factor(1.0, "demand: no demand weights given")
    if capacity_used is None or capacity_used <= 1.0:
        capacity = Factor(1.0, "capacity: within what the place can serve")
    else:
        capacity = Factor(1.0 / capacity_used, f"capacity: {capacity_used:.2f} times what the place can serve; the rest is not served")
    seed = design.run_seed(conn)
    u = random.Random(f"{seed}:{subject_kind}:{int(subject_id)}:{int(day)}").random()
    out = {
        "calendar": _calendar(conn, data, sector, day),
        "shock": _shock(conn, data, sector, day),
        "demand": demand,
        "form": Factor(0.5 + float(quality) / 100.0, f"form: quality {float(quality):.0f}"),
        "condition": Factor(0.6 + 0.4 * float(condition) / 100.0, f"condition: {float(condition):.0f} of 100"),
        "capacity": capacity,
        "rivals": _rivals(conn, subject_kind, subject_id, sector, location_id),
        "roll": Factor(0.9 + 0.2 * u, "roll: the seeded luck of this day"),
    }
    return {k: out[k] for k in KEYS}


def total(factors: dict[str, Factor]) -> float:
    t = 1.0
    for f in factors.values():
        t *= float(f.value)
    return t


def record(conn: sqlite3.Connection, subject_kind: str, subject_id: int, day: int, factors: dict[str, Factor]) -> None:
    blob = {k: {"value": f.value, "source": f.source} for k, f in factors.items()}
    conn.execute(
        """INSERT INTO driver_readings(subject_kind,subject_id,day,factors_json,total) VALUES (?,?,?,?,?)
           ON CONFLICT(subject_kind,subject_id) DO UPDATE SET day=excluded.day, factors_json=excluded.factors_json, total=excluded.total""",
        (subject_kind, int(subject_id), int(day), json.dumps(blob, sort_keys=True), total(factors)))


def why(conn: sqlite3.Connection, subject_kind: str, subject_id: int) -> list[str]:
    row = conn.execute("SELECT factors_json FROM driver_readings WHERE subject_kind=? AND subject_id=?",
                       (subject_kind, int(subject_id))).fetchone()
    if row is None:
        return []
    blob = json.loads(row[0])
    return [f"{k}: {blob[k]['value']:.3f} ({blob[k]['source']})" for k in KEYS if k in blob]
