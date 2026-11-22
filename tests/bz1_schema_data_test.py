"""BZ1.2: the side tables, the migration and the package `business` file.

Run: PYTHONPATH=. python tests/bz1_schema_data_test.py"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

TABLES = ("driver_readings", "venture_details", "venture_parties", "venture_approvals", "place_details",
          "agreement_terms", "agreement_breaches")


def _has(conn, t):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


def test_tables_exist_fresh_and_migrated():
    from engine.db import SCHEMA_VERSION, connect, init_db
    path = Path(tempfile.mkdtemp()) / "fresh.db"
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    init_db()
    conn = connect()
    assert SCHEMA_VERSION >= 125
    for t in TABLES:
        assert _has(conn, t), t
    # a DB left at the previous schema: the tables are gone and the migration row is not there yet
    for t in TABLES:
        conn.execute(f"DROP TABLE {t}")
    conn.execute("DELETE FROM schema_migrations WHERE version>=125")
    conn.execute("UPDATE engine_meta SET value='124' WHERE key='schema_version'")
    conn.commit()
    conn.close()
    init_db()
    conn = connect()
    for t in TABLES:
        assert _has(conn, t), ("migrated", t)
    assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
    conn.close()


def test_saintjude_business_file_loads():
    from engine import business_data as bd
    w = _open_world()
    c = w.conn
    data = bd.load(c)
    assert data["venture_kinds"]["open_business"]["stages"][0]["key"]
    assert bd.breach_path(c, "street") == "debt"
    assert bd.place_kind(c, "garage")["building_kind"] == "workshop"
    assert {"open_business", "build_or_refit", "bid_contract"} <= set(data["venture_kinds"])
    assert len(data["venture_kinds"]["bid_contract"]["stages"]) == 1


def test_unknown_word_is_named():
    from engine import business_data as bd
    w = _open_world()
    sectors = {"construction", "hospitality"}
    good = json.loads((ROOT / "worlds" / "saintjude" / "business.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp())

    def refused(mutate, *needles):
        data = json.loads(json.dumps(good))
        mutate(data)
        p = tmp / "business.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        try:
            bd.parse(p, sectors | {"retail", "logistics", "trade", "entertainment", "regulated_entertainment"})
        except bd.BusinessDataError as e:
            for n in needles:
                assert n in str(e), (n, str(e))
            return
        raise AssertionError(f"not refused: {needles}")

    refused(lambda d: d["venture_kinds"]["open_business"]["stages"][0].update(approvals=["no_such"]),
            "business.json", "open_business", "no_such")
    refused(lambda d: d["place_kinds"]["garage"].update(building_kind="spaceport"), "business.json", "garage", "spaceport")
    refused(lambda d: d["breach_words"].update(sue="vengeance"), "business.json", "sue", "vengeance")
    refused(lambda d: d.update(mystery=1), "business.json", "mystery")
    refused(lambda d: d["seasonality"].update(farming=[1.0] * 12), "business.json", "farming")


def test_caerness_has_no_business_data():
    from engine import business_data as bd
    from engine.db import connect, init_db
    path = Path(tempfile.mkdtemp()) / "c.db"
    shutil.copy2(ROOT / "data" / "caerness.db", path)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    init_db()
    conn = connect()
    assert bd.load(conn) is None
    conn.close()


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
