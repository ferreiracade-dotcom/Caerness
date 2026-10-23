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


if __name__ == "__main__":
    run()
