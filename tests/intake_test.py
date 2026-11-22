"""The intake core (I-1): held things, depth gaps, the shape registry, the weekly B tick.

Run: PYTHONPATH=. python tests/intake_test.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, open_world as _open_world


def _caerness():
    """A Caerness copy (the live data/caerness.db is only read, never written) with a protagonist; returns (conn, me)."""
    tmp = tempfile.mkdtemp()
    db = Path(tmp) / "c.db"
    shutil.copy2(ROOT / "data" / "caerness.db", db)
    os.environ["CAERNESS_DB_PATH"] = str(db)
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    from engine.db import connect, init_db
    from engine.player import set_player
    init_db()
    conn = connect()
    me = int(conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0])
    set_player(conn, me)
    conn.commit()
    return conn, me


def test_tables_exist_and_saintjude_has_intake_rules():
    from engine.world_package import intake_rules, package_for
    w = _open_world()
    c = w.conn
    for t in ("held_things", "depth_gaps"):
        assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone(), t
    r = intake_rules(package_for(c))
    assert set(r) >= {"shape_words", "readers", "tick"}
    assert r["tick"]["arrears_weeks_to_fail"] == 4


def test_caerness_has_no_intake_rules():
    from engine.world_package import intake_rules, package_for
    conn, _me = _caerness()
    assert intake_rules(package_for(conn)) == {}


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
