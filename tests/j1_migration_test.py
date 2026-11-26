"""Prison J1 schema 128: the eight tables are in the schema; a 127 save migrates keeping every row and the money; ensure_tables then does nothing.

Run: PYTHONPATH=. python tests/j1_migration_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.j1_admission_test import _convict, _run  # noqa: E402
from tests.outfit_choice_fixture import open_world  # noqa: E402

TABLES = ("facilities", "facility_groups", "inmate_stays", "prison_channels", "prison_contacts", "prison_events", "law_reviews", "inmate_ties")


def _has(c, t):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


def test_fresh_opening_has_the_tables_without_ensure():
    from engine.db import SCHEMA_VERSION
    c = open_world().conn
    assert SCHEMA_VERSION == 133
    for t in TABLES:
        assert _has(c, t), t


def test_a_127_save_migrates_keeps_rows_and_money():
    from engine import prison
    from engine.db import connect, init_db
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    _convict(c, w.soldier, 1000)
    _run(c)
    stays = c.execute("SELECT COUNT(*) FROM inmate_stays").fetchone()[0]
    assert stays >= 1
    money = c.execute("SELECT COALESCE(SUM(amount),0) FROM resources").fetchone()[0]
    actors = c.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
    sents = c.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    # an old save has none of the tables: drop them (and the rows that point at them), mark it 127
    for t in TABLES:
        c.execute(f"DROP TABLE {t}")
    c.execute("UPDATE sentences SET metadata_json=json_remove(metadata_json,'$.stay_id')")  # the old save never had a stay
    c.execute("DELETE FROM schema_migrations WHERE version=128")
    c.execute("UPDATE engine_meta SET value='127' WHERE key='schema_version'")
    c.commit()
    c.close()
    init_db()
    c2 = connect()
    from engine.db import SCHEMA_VERSION
    assert c2.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION == 133
    for t in TABLES:
        assert _has(c2, t), t
        assert c2.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
    assert c2.execute("SELECT COUNT(*) FROM actors").fetchone()[0] == actors
    assert c2.execute("SELECT COUNT(*) FROM sentences").fetchone()[0] == sents
    assert c2.execute("SELECT COALESCE(SUM(amount),0) FROM resources").fetchone()[0] == money
    # the layer picks the old sentence up on its next pass: admitted into a fresh stay
    prison.ensure_facilities(c2)
    c2.execute("UPDATE world_state SET current_day=current_day+1 WHERE id=1")
    prison.process_due(c2, int(c2.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]))
    assert c2.execute("SELECT COUNT(*) FROM inmate_stays WHERE status='inside'").fetchone()[0] >= 1


def test_ensure_tables_is_a_no_op_once_they_exist():
    from engine import prison
    c = open_world().conn
    before = sorted(r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
    prison._READY["key"] = None
    prison.ensure_tables(c)
    after = sorted(r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
    assert before == after


def main() -> None:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        f()
        print("ok", n)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
