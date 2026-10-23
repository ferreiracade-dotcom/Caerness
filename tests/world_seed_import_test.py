"""Task 6: seed import reads the world package."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from world_package_loader_test import _write_pkg  # noqa: E402

START = "1980-01-01"  # day 0 = Tuesday 1 January 1980


def _person(pid, name, age, **kw):
    from datetime import date, timedelta
    birth_day = -age * 365
    d = date.fromisoformat(START) + timedelta(days=birth_day)
    wd = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[d.weekday()]
    months = ("January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December")
    p = {"id": pid, "name": name, "age": age, "birth_day": birth_day, "life_status": "living",
         "birth_date": f"{wd} {d.day} {months[d.month - 1]} {d.year}", "role": "citizen"}
    p.update(kw)
    return p


def _seed(bible_hash, persons):
    return {"meta": {"world_bible_sha256": bible_hash}, "places": [], "routes": [], "institutions": [],
            "persons": persons, "relationships": [], "households": [], "cohorts": [], "claims": [], "processes": []}


def _build(tmp, name, seed, *, pkg_hash):
    worlds = tmp / "worlds"
    worlds.mkdir(exist_ok=True)
    d = _write_pkg(worlds, name, calendar={"kind": "gregorian", "start": START},
                   bible_sha256=pkg_hash, seed_namespace="sj_seed")
    (d / "seed.json").write_text(json.dumps(seed), encoding="utf-8")
    return worlds


def _fresh(tmp, tag):
    os.environ["CAERNESS_DB_PATH"] = str(tmp / f"{tag}.db")
    from engine.db import connect, init_db
    init_db()
    return connect()


def run():
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        good = hashlib.sha256(b"x").hexdigest()  # _write_pkg writes bible.docx = b"x"
        persons = [_person("p:a", "Ann Rossi", 40), _person("p:b", "Bob Rossi", 12),
                   _person("p:c", "Carl Rossi", 70, stage="Sixth")]
        worlds = _build(tmp, "sj", _seed(good, persons), pkg_hash=good)
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        # caerness package must still resolve for init_db
        import shutil
        shutil.copytree(ROOT / "worlds" / "caerness", worlds / "caerness")
        # relative paths in caerness manifest point at repo files; rewrite to absolute
        m = json.loads((worlds / "caerness" / "world.json").read_text(encoding="utf-8"))
        for k in ("bible_path", "seed_path", "rulebook_section", "creation_section"):
            if m.get(k):
                m[k] = str((ROOT / "worlds" / "caerness" / m[k]).resolve())
        (worlds / "caerness" / "world.json").write_text(json.dumps(m), encoding="utf-8")

        from engine.current_seed import SOURCE_NAMESPACE, import_current_seed
        from engine.world_package import load_package

        sj = load_package("sj")
        conn = _fresh(tmp, "a")
        out = import_current_seed(conn, package=sj)
        conn.commit()
        assert out["source_namespace"] == "sj_seed" and out["persons"] == 3, out
        assert conn.execute("SELECT COUNT(*) FROM source_identity_map WHERE source_namespace='sj_seed'").fetchone()[0] >= 3
        assert conn.execute("SELECT COUNT(*) FROM source_identity_map WHERE source_namespace=?", (SOURCE_NAMESPACE,)).fetchone()[0] == 0
        # non-cultivation package: stage is ignored
        sixth = conn.execute("""SELECT h.longevity_class FROM actor_health_profiles h JOIN actors a ON a.id=h.actor_id
                                WHERE a.name='Carl Rossi'""").fetchone()[0]
        assert sixth == "ordinary", sixth
        conn.close()

        # wrong birth date names the person
        bad = [_person("p:a", "Ann Rossi", 40)]
        bad[0]["birth_date"] = "Monday 1 January 1900"
        worlds = _build(tmp, "sjbad", _seed(good, bad), pkg_hash=good)
        conn = _fresh(tmp, "b")
        try:
            import_current_seed(conn, package=load_package("sjbad"))
        except ValueError as e:
            assert "Ann Rossi" in str(e), str(e)
        else:
            raise AssertionError("wrong birth_date must raise")
        conn.close()

        # bible hash: mismatch raises only when the package has a hash
        worlds = _build(tmp, "sjhash", _seed("deadbeef", [_person("p:a", "Ann Rossi", 40)]), pkg_hash=good)
        conn = _fresh(tmp, "c")
        try:
            import_current_seed(conn, package=load_package("sjhash"))
        except ValueError as e:
            assert "bible" in str(e).lower()
        else:
            raise AssertionError("hash mismatch must raise when package has a hash")
        conn.close()
        worlds = _build(tmp, "sjnohash", _seed("deadbeef", [_person("p:a", "Ann Rossi", 40)]), pkg_hash=None)
        conn = _fresh(tmp, "d")
        import_current_seed(conn, package=load_package("sjnohash"))
        conn.close()
    print("world_seed_import_test passed")


if __name__ == "__main__":
    run()
