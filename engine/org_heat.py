"""Heat on an organisation: what its violence and its visible crimes have drawn from the law and the press (task B12e).

The organisation layer's twin of `underworld_heat` (that table is keyed by the old layer's organisation rows, which a package built on
organisations does not have). The figures are the package's (outfits data `tension.heat`): what a killing writes by the rank of the dead
man, how much of it is public, how fast heat fades. Nothing here is capped: heat is a running sum that fades by half-life, and the
readers turn it into a 0..1 pressure against a data figure (`*_full`) when a head weighs what a feud would cost. No world words.
"""
from __future__ import annotations

import sqlite3

from . import org_motives
from .orgs import clamp01

COLS = ("public_heat", "investigative_heat", "violence_heat")


def _data(conn: sqlite3.Connection) -> dict:
    return (org_motives._sphere_data(conn).get("tension") or {}).get("heat") or {}


def _v(conn, spec, default: float = 0.0) -> float:
    return org_motives._value(conn, spec, default)


def enabled(conn: sqlite3.Connection) -> bool:
    return bool(_data(conn))


def _fade(conn: sqlite3.Connection, value: float, since: int, day: int) -> float:
    half = _v(conn, _data(conn).get("half_life_days"), 0.0)
    if half <= 0 or day <= since:
        return float(value)
    return float(value) * 0.5 ** ((int(day) - int(since)) / half)


def read(conn: sqlite3.Connection, org: int, day: int) -> dict[str, float]:
    """The organisation's three heats as of `day` (faded from the day they were last written)."""
    r = conn.execute("SELECT public_heat,investigative_heat,violence_heat,updated_day FROM org_heat WHERE org_actor_id=?", (int(org),)).fetchone()
    if r is None:
        return {c: 0.0 for c in COLS}
    return {c: _fade(conn, r[i], r[3], day) for i, c in enumerate(COLS)}


def add(conn: sqlite3.Connection, org: int, day: int, *, public: float = 0.0, investigative: float = 0.0, violence: float = 0.0) -> None:
    now = read(conn, org, day)
    vals = (now["public_heat"] + public, now["investigative_heat"] + investigative, now["violence_heat"] + violence)
    conn.execute(
        """INSERT INTO org_heat(org_actor_id,public_heat,investigative_heat,violence_heat,updated_day) VALUES (?,?,?,?,?)
           ON CONFLICT(org_actor_id) DO UPDATE SET public_heat=excluded.public_heat,investigative_heat=excluded.investigative_heat,
             violence_heat=excluded.violence_heat,updated_day=excluded.updated_day""", (int(org), *vals, int(day)))


def own_factor(conn: sqlite3.Connection, org: int, day: int) -> float:
    """0..1: the organisation's own violence and investigative heat against the package's `own_full`."""
    h = read(conn, org, day)
    return clamp01((h["violence_heat"] + h["investigative_heat"]) / max(1e-9, _v(conn, _data(conn).get("own_full"), 1.0)))


def city_factor(conn: sqlite3.Connection, day: int) -> float:
    """0..1: the public heat of every organisation together against the package's `city_full` (the city's attention is shared)."""
    total = 0.0
    for r in conn.execute("SELECT public_heat,updated_day FROM org_heat").fetchall():
        total += _fade(conn, r[0], r[1], day)
    return clamp01(total / max(1e-9, _v(conn, _data(conn).get("city_full"), 1.0)))


def on_killing(conn: sqlite3.Connection, killer_orgs, victim_orgs, rank: float, day: int, *, public: bool = True, civilian: bool = False) -> None:
    """A killing writes heat on the killer's organisations (all of it) and the victim's (the part that is the law's attention to what
    happened on its ground), by the rank of the dead man; a civilian's death (a bystander) is public whoever he was."""
    d = _data(conn).get("kill") or {}
    if not d:
        return
    scale = _v(conn, d.get("base"), 1.0) + _v(conn, d.get("rank"), 0.0) * float(rank)
    pub = _v(conn, d.get("public"), 0.0) * (1.0 if public else _v(conn, d.get("hidden_share"), 0.0)) + (_v(conn, d.get("civilian_public"), 0.0) if civilian else 0.0)
    inv = _v(conn, d.get("investigative"), 0.0) * (1.0 if public else _v(conn, d.get("hidden_share"), 0.0))
    vio = _v(conn, d.get("violence"), 0.0)
    for o in sorted(set(int(x) for x in killer_orgs)):
        add(conn, o, day, public=pub * scale, investigative=inv * scale, violence=vio * scale)
    share = _v(conn, d.get("victim_share"), 0.0)
    for o in sorted(set(int(x) for x in victim_orgs) - set(int(x) for x in killer_orgs)):
        add(conn, o, day, public=pub * scale * share, investigative=inv * scale * share, violence=vio * scale * share)
