"""R1 schema 127: the history tables and held_things.basis_json; a 126 save migrates with every row kept.

Run: PYTHONPATH=. python tests/history_schema_test.py
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

TABLES = ("history_entries", "divergences", "tech_level", "real_figures")


def test_fresh_opening_has_the_tables():
    from engine.db import SCHEMA_VERSION
    c = _open_world().conn
    assert SCHEMA_VERSION == 132
    for t in TABLES:
        assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone(), t
    assert "basis_json" in {r[1] for r in c.execute("PRAGMA table_info(held_things)")}


def test_a_126_save_migrates_and_keeps_rows():
    from engine.db import connect, init_db
    w = _open_world()
    c = w.conn
    c.execute("INSERT INTO held_things(name,shape,start_day,created_day,updated_day) VALUES ('x','thing',0,0,0)")
    for t in TABLES:
        c.execute(f"DROP TABLE {t}")
    c.execute("ALTER TABLE held_things DROP COLUMN basis_json")
    c.execute("DELETE FROM schema_migrations WHERE version=127")
    c.execute("UPDATE engine_meta SET value='126' WHERE key='schema_version'")
    actors = c.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
    c.commit()
    c.close()
    init_db()
    c2 = connect()
    from engine.db import SCHEMA_VERSION
    assert c2.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
    for t in TABLES:
        assert c2.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone(), t
    assert c2.execute("SELECT COUNT(*) FROM actors").fetchone()[0] == actors
    row = c2.execute("SELECT name,basis_json FROM held_things WHERE name='x'").fetchone()
    assert row and row["basis_json"] == "{}"


tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
tests.sort(key=lambda f: f.__code__.co_firstlineno)


def _run_all():
    ok = 0
    for t in tests:
        try:
            t()
            ok += 1
        except Exception:
            print("FAIL", t.__name__)
            traceback.print_exc()
    print(f"{ok}/{len(tests)} passed")
    return ok == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
