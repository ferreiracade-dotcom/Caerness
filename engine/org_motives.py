"""What moves a man to choose: motives read from his situation in the world (sphere-free).

A choice (an open name such as the ones a sphere registers in `org_choices`) has several motives. Each motive is a
reader `fn(conn, actor_id, day) -> 0..1` that looks at real state (relationships, money rows, lines, seats, cases) and
says how hard that part of his situation pushes him. Readers are registered by the sphere module with
`register_motive(choice, name, fn)`; which readers a choice uses, and their weights, are package data, so a new motive is
a data line plus a reader and touches no choice code.

Where the data lives, in order: the `motives` (and `rates`) of the man's organisation kind in orgs.json
(`kinds[k].motives[choice] = [{"name", "weight"}]`, `kinds[k].rates[choice]`), then the sphere file's own top-level
`motives` / `rates` (outfits.json for the underworld). A weight is a number or the key of a design figure. `rates[choice]`:
`base_rate` (a figure key or number, chance per week at full pressure), `base_rate_by_role` (role -> figure key), and
`temperament`: [{"trait", "weight", "sign"}] over the drives (ambition, loyalty, aggression, risk_tolerance, patience,
pragmatism) and the seat's greed and reliability, the weight a figure key or number.

`pressure` combines the motives as 1 - prod(1 - weight * m): several moderate reasons add up, one strong reason is
enough. `weekly_chance` is base_rate * pressure * temperament_factor. `should_choose` is the weekly roll that lets a man
consider a choice at all: one draw per (actor, day, choice) from the run seed through the single point `_roll`.
"""
from __future__ import annotations

import json
import random
import sqlite3
from typing import Callable

from .design import figure, run_seed
from .orgs import clamp01, kind_rules as _kind_rules, seats_of
from .world_package import outfit_rules, package_for

Motive = Callable[[sqlite3.Connection, int, int], float]
_READERS: dict[tuple[str, str], Motive] = {}

_TRAITS = ("ambition", "loyalty", "aggression", "risk_tolerance", "patience", "pragmatism")


def register_motive(choice: str, name: str, fn: Motive) -> None:
    """The reader for motive `name` of `choice`. Registering again replaces it (idempotent across reloads)."""
    _READERS[(str(choice), str(name))] = fn


def _fig(conn: sqlite3.Connection, key: str, default=None):
    """A design figure's run value. Read straight from the drawn figures when it is there (the weekly roll runs for every
    seated man, and `figure` parses the package's figure file on each call); otherwise through `figure`."""
    try:
        r = conn.execute("SELECT value,text_value FROM design_figures WHERE key=?", (str(key),)).fetchone()
    except sqlite3.OperationalError:
        r = None
    if r is not None:
        return r[0] if r[0] is not None else json.loads(r[1])
    return figure(conn, str(key), default=default)


def _value(conn: sqlite3.Connection, spec, default: float = 0.0) -> float:
    """A number as written, or the run's value of the design figure it names."""
    if isinstance(spec, (int, float)):
        return float(spec)
    if spec is None:
        return default
    v = _fig(conn, str(spec), default=None)
    return default if v is None else float(v)


_SNAP: dict = {"key": None, "kinds": {}, "sphere": None}


def db_key(conn: sqlite3.Connection):
    """Which database this connection is on (a cache key that survives a freed connection's address being reused)."""
    return (id(conn), conn.execute("PRAGMA database_list").fetchone()[2])


def _snap(conn: sqlite3.Connection) -> dict:
    """Package data read once per connection and day (the weekly roll runs for every seated man on every review, and
    reading the package's files and rules each time was the hot path of a long advance)."""
    r = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()
    key = (db_key(conn), None if r is None else int(r[0]))
    if _SNAP["key"] != key:
        _SNAP.update(key=key, kinds={}, sphere=None)
    return _SNAP


def kind_rules(conn: sqlite3.Connection, org_actor_id: int) -> dict:
    """`orgs.kind_rules`, kept for the day."""
    kinds = _snap(conn)["kinds"]
    if org_actor_id not in kinds:
        kinds[org_actor_id] = _kind_rules(conn, org_actor_id)
    return kinds[org_actor_id]


def _sphere_data(conn: sqlite3.Connection) -> dict:
    snap = _snap(conn)
    if snap["sphere"] is None:
        snap["sphere"] = outfit_rules(package_for(conn))
    return snap["sphere"]


def spec_for(conn: sqlite3.Connection, actor_id: int, choice: str) -> tuple[dict, object] | None:
    """(the choice's data, the seat it applies through) for a man: the first of his active seats whose organisation kind
    lists the choice; else, through his first active seat, the sphere file's. None when no data names the choice."""
    rows = [s for s in seats_of(conn, actor_id) if s["status"] == "active"]
    for s in rows:
        kind = kind_rules(conn, int(s["org_actor_id"]))
        if choice in (kind.get("motives") or {}):
            return {"motives": kind["motives"][choice], "rates": (kind.get("rates") or {}).get(choice) or {}}, s
    sphere = _sphere_data(conn)
    if rows and choice in (sphere.get("motives") or {}):
        return {"motives": sphere["motives"][choice], "rates": (sphere.get("rates") or {}).get(choice) or {}}, rows[0]
    return None


def pressure(conn: sqlite3.Connection, actor_id: int, day: int, choice: str) -> tuple[float, dict[str, float]]:
    """(1 - prod(1 - weight_i * m_i), {motive name: m_i}) over the choice's motives that have a reader."""
    found = spec_for(conn, actor_id, choice)
    if found is None:
        return 0.0, {}
    parts: dict[str, float] = {}
    rest = 1.0
    for m in found[0]["motives"]:
        reader = _READERS.get((choice, str(m["name"])))
        if reader is None:
            continue
        v = clamp01(reader(conn, int(actor_id), int(day)))
        parts[str(m["name"])] = v
        rest *= 1.0 - clamp01(_value(conn, m.get("weight"))) * v
    return 1.0 - rest, parts


def weight_of(conn: sqlite3.Connection, actor_id: int, choice: str, name: str) -> float:
    """The package's weight for one motive of a choice (0.0 when the data does not list it)."""
    found = spec_for(conn, actor_id, choice)
    for m in (found[0]["motives"] if found else []):
        if str(m["name"]) == name:
            return clamp01(_value(conn, m.get("weight")))
    return 0.0


def _drive(conn: sqlite3.Connection, actor_id: int, trait: str, seat) -> float:
    if trait == "greed":
        return float(seat["greed"])
    if trait == "reliability":
        return float(seat["reliability"])
    row = conn.execute("SELECT * FROM actor_drives WHERE actor_id=?", (int(actor_id),)).fetchone()
    return float(row[trait]) if row is not None and trait in row.keys() else 0.5


def _temperament(conn: sqlite3.Connection, actor_id: int, found) -> float:
    terms = found[0]["rates"].get("temperament") or []
    f = 1.0
    for t in terms:
        f += float(t.get("sign", 1)) * _value(conn, t.get("weight")) * (_drive(conn, actor_id, str(t["trait"]), found[1]) - 0.5) * 2.0
    lo = float(_fig(conn, "temperament_factor_lo", default=0.25))
    hi = float(_fig(conn, "temperament_factor_hi", default=2.0))
    return max(lo, min(hi, f))


def temperament_factor(conn: sqlite3.Connection, actor_id: int, choice: str) -> float:
    """1 + sum(sign * weight * (trait - 0.5) * 2) over the choice's temperament terms, kept inside the figures'
    `temperament_factor_lo` / `temperament_factor_hi` (1.0 when the package gives the choice no temperament)."""
    found = spec_for(conn, actor_id, choice)
    return 1.0 if found is None else _temperament(conn, actor_id, found)


def _base_rate(conn: sqlite3.Connection, found) -> float:
    rates, seat = found[0]["rates"], found[1]
    spec = (rates.get("base_rate_by_role") or {}).get(str(seat["role_key"]), rates.get("base_rate"))
    return max(0.0, _value(conn, spec))


def base_rate(conn: sqlite3.Connection, actor_id: int, choice: str) -> float:
    """The chance per week at full pressure: by his seat's role when the package says so, else the choice's own."""
    found = spec_for(conn, actor_id, choice)
    return 0.0 if found is None else _base_rate(conn, found)


def weekly_chance(conn: sqlite3.Connection, actor_id: int, day: int, choice: str) -> float:
    """base_rate * pressure * temperament_factor, per week."""
    found = spec_for(conn, actor_id, choice)
    base = 0.0 if found is None else _base_rate(conn, found)
    if base <= 0.0:
        return 0.0
    return base * pressure(conn, actor_id, day, choice)[0] * _temperament(conn, actor_id, found)


def _roll(conn: sqlite3.Connection, actor_id: int, day: int, stream: str) -> float:
    """The one point where a seeded draw is made for a man's choices (tests patch it). Same seed, actor, day, stream: same draw."""
    return random.Random(f"{run_seed(conn)}:org:{stream}:{int(actor_id)}:{int(day)}").random()


def _review_scale(conn: sqlite3.Connection, actor_id: int, day: int) -> float:
    """The share of a week this review stands for: a man reviewed daily rolls a seventh of the weekly chance each day,
    one reviewed weekly rolls all of it (so the chance per week does not depend on his cadence)."""
    row = conn.execute("SELECT last_review_day FROM simulation_profiles WHERE actor_id=?", (int(actor_id),)).fetchone()
    if row is None or row[0] is None:
        return 1.0
    return max(1, min(7, int(day) - int(row[0]))) / 7.0


_CEILINGS: dict = {"db": None, "by": {}}
CEILING_DAYS = 28  # how long a man's ceiling (base rate x temperament) is reused; drives and roles move slowly


def _ceiling(conn: sqlite3.Connection, actor_id: int, day: int, choice: str) -> float:
    """base rate x temperament for a man, reused for CEILING_DAYS (the weekly roll runs for every seated man on every review)."""
    dk = db_key(conn)
    if _CEILINGS["db"] != dk:
        _CEILINGS.update(db=dk, by={})
    k = (int(actor_id), choice)
    ent = _CEILINGS["by"].get(k)
    if ent is None or not 0 <= int(day) - ent[0] < CEILING_DAYS:
        found = spec_for(conn, actor_id, choice)
        base = 0.0 if found is None else _base_rate(conn, found)
        ent = (int(day), 0.0 if base <= 0.0 else base * _temperament(conn, actor_id, found))
        _CEILINGS["by"][k] = ent
    return ent[1]


def should_choose(conn: sqlite3.Connection, actor_id: int, day: int, choice: str) -> bool:
    """Does he consider this choice today? One draw against the weekly chance, scaled to the days since his last review.
    The draw is compared with the ceiling (base rate x temperament) first, so most men are settled by it alone."""
    ceiling = _ceiling(conn, actor_id, day, choice)
    if ceiling <= 0.0:
        return False
    scale = _review_scale(conn, actor_id, day)
    roll = _roll(conn, actor_id, day, choice)
    if roll >= ceiling * scale:
        return False
    found = spec_for(conn, actor_id, choice)
    return roll < _base_rate(conn, found) * pressure(conn, actor_id, day, choice)[0] * _temperament(conn, actor_id, found) * scale
