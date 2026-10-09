"""DRIVES-01: every character has drives, so nobody decides as a featureless average.

Until schema 109, characters created without an actor_drives row (most of the opening seed, newborns, and
people revealed or created by several systems) were read as exactly 0.5 on every drive by the decision runtime,
interactions, careers, tournaments and the underworld. Speaker cards meanwhile portrayed a temperament for
them. Now a missing row is filled once with a stable, bell-shaped draw (POPULATION) from the world seed and the
person's id, recorded with basis 'seeded_draw', at opening resolution (migration 109) and at each simulation
checkpoint for anyone created since. Existing rows, written by their owning systems, are never changed.
"""
from __future__ import annotations

import hashlib
import sqlite3

DRIVES = ("aggression", "risk_tolerance", "patience", "loyalty", "ambition", "pragmatism")

# Centre of each drive: the midpoint of the ranges the general-population generator already uses for people
# crystallized from the background (person_ecology), so a seeded person is the same kind of person. The schema-108
# cast's own averages were not used: 264 of its 320 rows came from a near-constant formula (see migration 109).
# Spread: bell-shaped with sd 0.12, so about 95% of people fall within 0.24 of the centre. Fixed here so a draw
# never depends on when it is made.
POPULATION = {
    "aggression": (0.510, 0.12), "risk_tolerance": (0.550, 0.12), "patience": (0.550, 0.12),
    "loyalty": (0.575, 0.12), "ambition": (0.550, 0.12), "pragmatism": (0.610, 0.12),
}


def _fraction(*parts: object) -> float:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _world_seed(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def seeded_drives(conn: sqlite3.Connection, actor_id: int) -> dict[str, float]:
    """Human variation, bell-shaped (mean of three uniforms) on the population's centre and spread, stable for this
    world and person."""
    seed = _world_seed(conn)
    out = {}
    for d in DRIVES:
        z = (sum(_fraction("drives", seed, int(actor_id), d, i) for i in range(3)) / 3.0 - 0.5) / (1 / 6)
        mean, sd = POPULATION[d]
        out[d] = round(min(0.95, max(0.05, mean + sd * z)), 3)
    return out


def standing_out(drives: dict[str, float], threshold: float = 1.0) -> dict[str, int]:
    """Drives that stand out from the population: +1 well above typical, -1 well below."""
    out = {}
    for d, v in drives.items():
        mean, sd = POPULATION[d]
        z = (float(v) - mean) / sd
        if abs(z) >= threshold:
            out[d] = 1 if z > 0 else -1
    return out


def ensure_character_drives(conn: sqlite3.Connection) -> int:
    """Give every character without drives their seeded draw. Returns how many were filled."""
    missing = [int(r[0]) for r in conn.execute(
        """SELECT a.id FROM actors a LEFT JOIN actor_drives d ON d.actor_id=a.id
           WHERE a.actor_type='character' AND d.actor_id IS NULL ORDER BY a.id""")]
    for aid in missing:
        v = seeded_drives(conn, aid)
        conn.execute(
            f"INSERT INTO actor_drives(actor_id,{','.join(DRIVES)},basis) VALUES (?,{','.join('?' * len(DRIVES))},'seeded_draw')",
            (aid, *(v[d] for d in DRIVES)),
        )
    return len(missing)


# The near-constant formula latent crystallization used before schema 109 (resolution_controller): loyalty .55,
# ambition .62 and pragmatism .68 for everyone, the other three varying only with the actor id.
def _is_copied_pattern(row: sqlite3.Row) -> bool:
    return abs(row["loyalty"] - .55) < 1e-9 and abs(row["ambition"] - .62) < 1e-9 and abs(row["pragmatism"] - .68) < 1e-9


def redraw_copied_drives(conn: sqlite3.Connection) -> int:
    """At day 0 only (nothing has used them yet), replace drives written by the old near-constant formula."""
    if int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]) != 0:
        return 0
    n = 0
    for row in conn.execute("SELECT * FROM actor_drives").fetchall():
        if _is_copied_pattern(row):
            v = seeded_drives(conn, int(row["actor_id"]))
            conn.execute(f"UPDATE actor_drives SET {','.join(f'{d}=?' for d in DRIVES)},basis='seeded_draw' WHERE actor_id=?",
                         (*(v[d] for d in DRIVES), int(row["actor_id"])))
            n += 1
    return n
