"""World package loader and campaign binding (Task 3)."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SYSTEM_KEYS = ["cultivation", "elixir", "hollow", "groundbinding", "caerness_underworld",
               "caerness_religions", "caerness_trade", "merchant_houses"]


def _write_pkg(worlds: Path, pkg_id: str, **over):
    d = worlds / pkg_id
    d.mkdir(parents=True)
    (d / "bible.docx").write_bytes(b"x")
    (d / "seed.json").write_text("{}", encoding="utf-8")
    m = {"id": pkg_id, "display_name": "Saint Jude", "calendar": {"kind": "gregorian"},
         "bible_path": "bible.docx", "bible_sha256": None, "seed_path": "seed.json",
         "seed_namespace": "sj_seed", "rulebook_section": None, "creation_section": None,
         "systems": {k: False for k in SYSTEM_KEYS}, "data": {}, "name_pools": {}}
    m.update(over)
    (d / "world.json").write_text(json.dumps(m), encoding="utf-8")
    return d


def run():
    from engine import world_package as wp
    from engine.world_package import WorldPackageError

    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    p = wp.load_package("caerness")
    assert p.id == "caerness" and p.display_name == "Caerness"
    assert p.calendar["kind"] == "sv"
    assert p.bible_path.resolve() == (ROOT / "canon" / "world_bible_current.docx").resolve()
    assert p.bible_sha256
    assert set(p.systems) == set(SYSTEM_KEYS) and all(p.systems.values())
    assert p.seed_namespace == "caerness_seed_v1_1"
    assert p.seed_path.exists()
    assert "caerness" in wp.list_packages()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        worlds = tmp / "worlds"
        worlds.mkdir()
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        _write_pkg(worlds, "saintjude")
        _write_pkg(worlds, "broken", seed_path="nope.json")

        for bad, needle in (("nosuch", "nosuch"), ("broken", "nope.json")):
            try:
                wp.load_package(bad)
            except WorldPackageError as e:
                assert bad in str(e) and needle in str(e), str(e)
            else:
                raise AssertionError(f"{bad} should raise")
        assert wp.list_packages() == ["broken", "saintjude"]
        sj = wp.load_package("saintjude")
        assert sj.calendar["kind"] == "gregorian" and sj.bible_sha256 is None and not any(sj.systems.values())

        # fresh DB via init_db defaults to caerness; world_name from package
        db = tmp / "a.db"
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine import db as edb
        os.environ.pop("CAERNESS_WORLDS_DIR")
        edb.init_db()
        conn = sqlite3.connect(db)
        assert wp.current_package(conn).id == "caerness"
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        assert conn.execute("SELECT world_name FROM world_state WHERE id=1").fetchone()[0] == "Caerness"
        # binding
        wp.set_campaign_package(conn, "saintjude")
        assert wp.current_package(conn).id == "saintjude"
        try:
            wp.set_campaign_package(conn, "nosuch")
        except WorldPackageError:
            pass
        else:
            raise AssertionError("binding to unknown package must raise")
        assert wp.current_package(conn).id == "saintjude"
        conn.close()

        # existing DB with world_state but no meta row loads as caerness, also after re-init
        db2 = tmp / "b.db"
        c2 = sqlite3.connect(db2)
        c2.execute("CREATE TABLE world_state(id INTEGER PRIMARY KEY, world_name TEXT, current_day INTEGER)")
        c2.execute("INSERT INTO world_state VALUES (1,'Caerness',0)")
        os.environ.pop("CAERNESS_WORLDS_DIR")
        assert wp.current_package(c2).id == "caerness"
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        c2.close()

        # env override sets world_name on a new DB
        os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
        db3 = tmp / "c.db"
        os.environ["CAERNESS_DB_PATH"] = str(db3)
        edb.init_db()
        c4 = sqlite3.connect(db3)
        assert c4.execute("SELECT world_name FROM world_state WHERE id=1").fetchone()[0] == "Saint Jude"
        c4.close()
        os.environ.pop("CAERNESS_WORLD_PACKAGE")
    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    print("world_package_loader_test passed")


if __name__ == "__main__":
    run()
