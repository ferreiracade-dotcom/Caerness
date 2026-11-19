"""Helpers for the Saint Jude choice tests (task B10): a scratch opening, a soldier with his capo and boss, forced rolls."""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect

DAY = 100


class World:
    pass


def open_world() -> World:
    tmp = Path(tempfile.mkdtemp())
    path = build_saintjude(tmp)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    import engine.simulation  # noqa: F401  (registers the org provider and the mob's choices)
    w = World()
    w.conn = conn = connect(path)
    row = conn.execute(
        """SELECT s.actor_id,s.superior_actor_id,s.unit_id,s.org_actor_id FROM org_seats s
           WHERE s.role_key='soldier' AND s.status='active' AND s.unit_id IN
             (SELECT unit_id FROM org_seats WHERE role_key='soldier' AND status='active' GROUP BY unit_id HAVING COUNT(*)>=3)
           ORDER BY s.actor_id LIMIT 1""").fetchone()
    w.soldier, w.capo, w.unit, w.org = (int(row[0]), int(row[1]), int(row[2]), int(row[3]))
    from engine import orgs
    w.boss = orgs.head_of(conn, w.org)
    w.ground = int(conn.execute("SELECT ground_location_id FROM org_units WHERE id=?", (w.unit,)).fetchone()[0])
    return w


def rel(conn, a: int, b: int, **cols) -> None:
    from engine.relationships import ensure_relationship
    ensure_relationship(conn, a, b, 0)
    sets = ",".join(f"{k}=?" for k in cols)
    conn.execute(f"UPDATE relationships SET {sets} WHERE actor_a_id=? AND actor_b_id=?", (*cols.values(), a, b))


def drives(conn, actor: int, **cols) -> None:
    sets = ",".join(f"{k}=?" for k in cols)
    conn.execute(f"UPDATE actor_drives SET {sets} WHERE actor_id=?", (*cols.values(), actor))


@contextlib.contextmanager
def forced_roll(*streams: str):
    """Every named stream draws 0.0 (it passes); the others draw 0.99."""
    from engine import org_motives
    old = org_motives._roll
    org_motives._roll = lambda conn, actor, day, stream: 0.0 if stream in streams else 0.99
    try:
        yield
    finally:
        org_motives._roll = old


def run_review(conn, actor: int, day: int = DAY):
    from engine.decisions import decide_actor
    did = decide_actor(conn, actor, "STRATEGIC", day)
    return conn.execute("SELECT * FROM decisions WHERE id=?", (did,)).fetchone()
