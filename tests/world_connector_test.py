"""Task 4: package-aware campaign creation."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from world_package_loader_test import _write_pkg  # noqa: E402


def run():
    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(tmp / "camps")
        import connector.campaign as cc
        from engine.world_package import WorldPackageError, current_package

        # default: caerness
        p = cc.open_campaign("d1")
        with cc.connect_campaign() as conn:
            assert current_package(conn).id == "caerness"
            conn.execute("INSERT INTO connector_meta(key,value) VALUES ('marker','1')")
        # unknown package: raises, leaves no file
        try:
            cc.open_campaign("bad", package="nope")
        except WorldPackageError:
            pass
        else:
            raise AssertionError("unknown package must raise")
        assert not (cc.campaign_dir() / "bad.db").exists()
        assert not list(cc.campaign_dir().glob("bad*"))
        # existing campaign ignores package and is not re-copied
        os.environ["CAERNESS_DB_PATH"] = str(p)
        cc.open_campaign("d1", package="nope")
        with cc.connect_campaign() as conn:
            assert conn.execute("SELECT value FROM connector_meta WHERE key='marker'").fetchone()[0] == "1"
            assert current_package(conn).id == "caerness"

        # non-caerness package copies data/<id>.db and binds it
        worlds = tmp / "worlds"
        worlds.mkdir()
        _write_pkg(worlds, "saintjude")
        _write_pkg(worlds, "caerness", display_name="Caerness", calendar={"kind": "sv"})
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        fake_root = tmp / "root"
        (fake_root / "data").mkdir(parents=True)
        shutil.copy2(cc.PACKAGED_DB, fake_root / "data" / "saintjude.db")
        real_root = cc.ROOT
        cc.ROOT = fake_root
        import engine.canon as canon
        calls = []
        real_index = canon.index_canon
        canon.index_canon = lambda path, *a, **k: calls.append(Path(path))
        try:
            cc.open_campaign("sj1", package="saintjude")
            with cc.connect_campaign() as conn:
                pkg = current_package(conn)
                assert pkg.id == "saintjude"
            assert calls and calls[-1].resolve() == pkg.bible_path.resolve(), calls
            # missing packaged DB: raises and leaves nothing
            _write_pkg(worlds, "nodb")
            try:
                cc.open_campaign("nd", package="nodb")
            except (FileNotFoundError, WorldPackageError):
                pass
            else:
                raise AssertionError("missing packaged db must raise")
            assert not list(cc.campaign_dir().glob("nd*"))
        finally:
            cc.ROOT = real_root
            canon.index_canon = real_index
    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    print("world_connector_test passed")


def run_no_cultivation():
    """A package without cultivation: Stage is ignored in proposals and the scene never says martial/Stage/cultivat."""
    import hashlib
    import json
    from world_activation_switches_test import _install_caerness
    from world_seed_import_test import _build, _fresh, _person, _seed

    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        good = hashlib.sha256(b"x").hexdigest()
        persons = [_person("p:a", "Ann Rossi", 40), _person("p:b", "Bob Rossi", 41)]
        for p in persons:
            p["runtime_v1_1"] = {"current_location_ref": "pl:main"}
        seed = _seed(good, persons)
        seed["places"] = [{"id": "pl:main", "name": "Main Street", "kind": "settlement", "political_owner": "Saint Jude", "population": 5000}]
        worlds = _build(tmp, "nocult", seed, pkg_hash=good)
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        _install_caerness(worlds)
        from engine.activation import activate_existing_loops
        from engine.current_seed import import_current_seed
        from engine.player import set_player
        from engine.world_package import load_package, set_campaign_package
        from connector import store
        from connector.authoring import author
        from connector.views import compact_scene

        conn = _fresh(tmp, "nocult")
        set_campaign_package(conn, "nocult")
        import_current_seed(conn, package=load_package("nocult"))
        activate_existing_loops(conn)
        store.ensure_connector_schema(conn)
        me = int(conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0])
        set_player(conn, me)
        conn.commit()
        conn.execute("UPDATE background_person_profiles SET current_location_id=? WHERE current_location_id IS NULL", (conn.execute("SELECT id FROM locations").fetchone()[0],))
        before = conn.execute("SELECT COUNT(*) FROM cultivation_profiles").fetchone()[0]
        r = author(conn, "nc-1", "person", {"sex": "male", "age": 36, "stage": "Sixth", "from_elsewhere": True})
        assert r["status"] == "created", r
        assert conn.execute("SELECT COUNT(*) FROM cultivation_profiles").fetchone()[0] == before == 0
        text = json.dumps(compact_scene(conn)).lower()
        for bad in ("martial", "stage", "cultivat"):
            assert bad not in text, bad
        from engine.manners_canon import manners_for
        lid = conn.execute("SELECT id FROM locations").fetchone()[0]
        (worlds / "nocult" / "manners.json").write_text(json.dumps({"settlement": "Neighbours greet by first name.", "default": "Plain."}), encoding="utf-8")
        m = json.loads((worlds / "nocult" / "world.json").read_text(encoding="utf-8"))
        m["data"] = {"manners": "manners.json"}
        (worlds / "nocult" / "world.json").write_text(json.dumps(m), encoding="utf-8")
        assert manners_for(conn, lid) == "Neighbours greet by first name." and manners_for(conn, None) == "Plain."
        conn.close()
    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    print("world_connector_test (no cultivation) passed")


def run_package_surface():
    """Tasks 14-15: rulebook = shared core + the campaign's world section; lore, rulebook and date follow the package."""
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(tmp / "camps")
        worlds = tmp / "worlds"
        worlds.mkdir()
        _write_pkg(worlds, "caerness", display_name="Caerness", calendar={"kind": "sv"})
        sj = _write_pkg(worlds, "saintjude", display_name="Saint Jude", calendar={"kind": "gregorian", "start": "1985-03-04"},
                        bible_path="bible.md", rulebook_section="rb.md", creation_section="cr.md")
        (sj / "bible.md").write_text("# Harbour\n\nThe zorblat quay smells of diesel and salt.\n", encoding="utf-8")
        (sj / "rb.md").write_text("{{intro}}\nYou are the game master for Saint Jude. Binding.\n", encoding="utf-8")
        (sj / "cr.md").write_text("Design a Saint Jude resident.\n", encoding="utf-8")
        bare = _write_pkg(worlds, "bare", display_name="Bare", bible_path="b.md")
        (bare / "b.md").write_text("# Bare\n\nPlain.\n", encoding="utf-8")
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        import connector.campaign as cc
        import engine.canon as canon
        from connector.lore import lore
        from connector.session import load_creation, load_rulebook, resume
        from engine.player import set_player

        fake_root = tmp / "root"
        (fake_root / "data").mkdir(parents=True)
        for n in ("saintjude", "bare"):
            shutil.copy2(cc.PACKAGED_DB, fake_root / "data" / f"{n}.db")
        real_root = cc.ROOT
        cc.ROOT = fake_root
        try:
            cc.open_campaign("sj1", package="saintjude")
            with cc.connect_campaign() as conn:
                assert [r[0] for r in conn.execute("SELECT heading_path FROM canon_chunks")] == ["Harbour"]
                got = lore(conn, "zorblat")["passages"]
                assert got and "diesel" in got[0]["text"], got
                assert not lore(conn, "Cairnholt")["passages"]
                rb = load_rulebook(conn)
                assert rb.startswith("You are the game master for Saint Jude."), rb[:80]
                assert "Caerness" not in rb and load_creation(conn) .startswith("Design a Saint Jude resident.")
                assert resume(conn)["creation"] == load_creation(conn)
                me = int(conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0])
                set_player(conn, me)
                conn.commit()
                out = resume(conn)
                assert out["rulebook"] == rb and out["scene"]["date"] == "Monday 4 March 1985", out["scene"]["date"]
            cc.open_campaign("bare1", package="bare")
            with cc.connect_campaign() as conn:
                rb = load_rulebook(conn)
                for word in ("Caerness", "Stage", "cultivat", "House", "SV", "Hollow"):
                    assert word not in rb, word
                assert "Close third person" in rb and rb.count("\n\n\n") == 0
                assert "Stage" not in load_creation(conn) and "Caerness" not in load_creation(conn)
        finally:
            cc.ROOT = real_root
            os.environ.pop("CAERNESS_WORLDS_DIR", None)
    print("world_connector_test (package surface) passed")


if __name__ == "__main__":
    run()
    run_no_cultivation()
    run_package_surface()
