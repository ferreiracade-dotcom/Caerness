"""Violence from each man's own temperament (task B12e). Generic; the package's figures are outfits data `temperament`.

There is no outfit-level number for violence. A man's `aggression` and `risk_tolerance` (his drives) are what a killing, a hit or a strike
weighs, and every family has a spread: a calm head can have a killer under him and a hot one cautious men. At the opening each man's
aggression is drawn around the package's guideline for his organisation (the culture text of the bible, cited in the data) with a wide
spread and a shift by role; the guideline is a mean to draw around, never a value a man has. After that his drives move with what
happens to him: a man of his unit killed, his kin killed, a war around him, prison, each year of age, a step up the ladder. Nothing is
clamped except the natural 0..1 of a drive. No world words here.
"""
from __future__ import annotations

import random
import sqlite3

from . import org_motives
from .design import run_seed
from .orgs import clamp01


def data(conn: sqlite3.Connection) -> dict:
    return org_motives._sphere_data(conn).get("temperament") or {}


def _v(conn, spec, default: float = 0.0) -> float:
    return org_motives._value(conn, spec, default)


def draw_opening(conn: sqlite3.Connection) -> int:
    """Redraw aggression and risk tolerance for every seated man of an organisation the package gives a guideline for. Deterministic from
    the run's seed; returns how many men were drawn."""
    d = data(conn).get("opening") or {}
    if not d:
        return 0
    sd = _v(conn, d.get("sd"), 0.2)
    corr = _v(conn, d.get("risk_follows_aggression"), 0.0)
    shifts = {r: _v(conn, s) for r, s in (d.get("role_shift") or {}).items()}
    n = 0
    for key, spec in sorted((d.get("outfits") or {}).items()):
        mean = _v(conn, spec["mean"] if isinstance(spec, dict) else spec)
        for r in conn.execute(
                """SELECT s.actor_id,s.role_key FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id
                   WHERE p.package_key=? AND s.status='active' ORDER BY s.actor_id""", (key,)).fetchall():
            rng = random.Random(f"{run_seed(conn)}:temperament:{int(r[0])}")
            agg = clamp01(rng.gauss(mean + shifts.get(r[1], 0.0), sd))
            risk = clamp01(rng.gauss(0.5 + corr * (agg - 0.5), sd))
            conn.execute("""INSERT INTO actor_drives(actor_id,aggression,risk_tolerance) VALUES (?,?,?)
                            ON CONFLICT(actor_id) DO UPDATE SET aggression=excluded.aggression,risk_tolerance=excluded.risk_tolerance""", (int(r[0]), agg, risk))
            n += 1
    return n


def drift(conn: sqlite3.Connection, actor: int, cause: str, day: int, scale: float = 1.0) -> None:
    """Move a man's drives by what happened to him (data `temperament.drift[cause]`: a change per trait; a cause the package does not
    list moves nothing)."""
    spec = (data(conn).get("drift") or {}).get(cause)
    if not spec:
        return
    row = conn.execute("SELECT aggression,risk_tolerance,patience,loyalty,ambition,pragmatism FROM actor_drives WHERE actor_id=?", (int(actor),)).fetchone()
    if row is None:
        return
    cols = ("aggression", "risk_tolerance", "patience", "loyalty", "ambition", "pragmatism")
    new = {c: clamp01(float(row[i]) + _v(conn, spec.get(c), 0.0) * scale) for i, c in enumerate(cols)}
    conn.execute("UPDATE actor_drives SET aggression=?,risk_tolerance=?,patience=?,loyalty=?,ambition=?,pragmatism=? WHERE actor_id=?",
                 (*[new[c] for c in cols], int(actor)))


def age_year(conn: sqlite3.Connection, day: int) -> int:
    """Once a year every seated man of an organisation settles a little (data `drift.age_year`)."""
    if "age_year" not in (data(conn).get("drift") or {}):
        return 0
    ids = [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT s.actor_id FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id WHERE s.status='active' AND p.sphere='underworld' ORDER BY 1")]
    for a in ids:
        drift(conn, a, "age_year", day)
    return len(ids)
