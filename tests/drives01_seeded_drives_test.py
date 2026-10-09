"""DRIVES-01: no character decides as a featureless average. Characters without drives get a stable seeded
draw (basis 'seeded_draw') at migration and at each simulation checkpoint; owner-written drives are never
changed; the old near-constant crystallization formula is redrawn only at day 0."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.db import connect, init_db, reset_db
from engine.drives import DRIVES, POPULATION, ensure_character_drives, redraw_copied_drives, seeded_drives, standing_out
from engine.simulation import advance_connection


def _char(conn, name):
    return int(conn.execute("INSERT INTO actors(name,actor_type) VALUES (?,'character')", (name,)).lastrowid)


def run():
    reset_db()
    init_db()
    with connect() as conn:
        assert "basis" in {r[1] for r in conn.execute("PRAGMA table_info(actor_drives)")}
        owned = _char(conn, "[DRV] Owned")
        conn.execute("INSERT INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) "
                     "VALUES (?,0.9,0.1,0.9,0.1,0.9,0.1)", (owned,))
        bare = _char(conn, "[DRV] Bare")
        copied = _char(conn, "[DRV] Copied")
        conn.execute("INSERT INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) "
                     "VALUES (?,.4,.5,.6,.55,.62,.68)", (copied,))
        conn.execute("INSERT INTO actors(name,actor_type) VALUES ('[DRV] Some House','institution')")

        # Stable: the same world and person always draw the same values, within bounds.
        a, b = seeded_drives(conn, bare), seeded_drives(conn, bare)
        assert a == b and set(a) == set(DRIVES) and all(0.05 <= v <= 0.95 for v in a.values())
        assert seeded_drives(conn, bare) != seeded_drives(conn, copied)

        # Day 0: the copied formula is redrawn; owner-written drives are untouched; the bare character is filled.
        assert redraw_copied_drives(conn) == 1
        assert ensure_character_drives(conn) >= 1
        row = lambda aid: conn.execute("SELECT * FROM actor_drives WHERE actor_id=?", (aid,)).fetchone()
        assert row(owned)["basis"] is None and row(owned)["aggression"] == 0.9
        assert row(bare)["basis"] == "seeded_draw" and {d: row(bare)[d] for d in DRIVES} == a
        assert row(copied)["basis"] == "seeded_draw" and row(copied)["ambition"] != 0.62
        assert conn.execute("SELECT COUNT(*) FROM actor_drives d JOIN actors a ON a.id=d.actor_id "
                            "WHERE a.actor_type='institution'").fetchone()[0] == 0
        assert ensure_character_drives(conn) == 0

        # Across many people the draw has the intended centre and spread, and most people have a distinct trait.
        many = [seeded_drives(conn, 10_000 + i) for i in range(2000)]
        for d in DRIVES:
            vals = [m[d] for m in many]
            mean = sum(vals) / len(vals)
            sd = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
            assert abs(mean - POPULATION[d][0]) < 0.01 and abs(sd - POPULATION[d][1]) < 0.015, (d, mean, sd)
        assert sum(1 for m in many if standing_out(m)) / len(many) > 0.85

        # After day 0 a copied row is history and stays; a newcomer is filled at the next checkpoint.
        conn.execute("UPDATE world_state SET current_day=5 WHERE id=1")
        later_copied = _char(conn, "[DRV] Later copied")
        conn.execute("INSERT INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) "
                     "VALUES (?,.4,.5,.6,.55,.62,.68)", (later_copied,))
        assert redraw_copied_drives(conn) == 0
        newborn = _char(conn, "[DRV] Newborn")
        assert row(newborn) is None
        advance_connection(conn, 2)
        assert row(newborn)["basis"] == "seeded_draw"
        assert row(later_copied)["ambition"] == 0.62

    print("DRIVES-01 seeded drives test passed")


if __name__ == "__main__":
    run()
