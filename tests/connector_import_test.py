from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expect_refused(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except (ValueError, FileExistsError) as e:
        assert str(e), "refusals need a clear message"
        return str(e)
    raise AssertionError("import was not refused")


def run():
    packaged_before = sha(ROOT / "data" / "caerness.db")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(tmp / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        from connector.campaign import campaign_dir, connect_campaign, open_campaign
        from connector.import_campaign import install_campaign
        from engine.player import get_player, set_player
        from tools.export_campaign import export

        open_campaign("src")
        with connect_campaign() as conn:
            row = conn.execute(
                "SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()
            set_player(conn, int(row["id"]), campaign_name="src")
            conn.commit()
            src_actor = int(get_player(conn)["player_actor_id"])

        out = tmp / "export" / "src-export.db"
        info = export("src", out)
        assert out.exists() and info["sha256"] == sha(out) and info["bytes"] == out.stat().st_size

        backups = tmp / "backups"
        target = install_campaign(out, "dst", backup_dir=backups)
        assert target == campaign_dir() / "dst.db" and target.exists()
        open_campaign("dst")
        with connect_campaign() as conn:
            assert int(get_player(conn)["player_actor_id"]) == src_actor
        assert not list(campaign_dir().glob("*.tmp")) and not list(campaign_dir().glob("*.import*"))

        # An existing campaign is never replaced without --replace.
        msg = expect_refused(install_campaign, out, "dst", backup_dir=backups)
        assert "replace" in msg.lower()

        # With replace the old file is first kept as a preimport snapshot.
        before_old = sha(target)
        install_campaign(out, "dst", replace=True, backup_dir=backups)
        old = list(backups.glob("dst-*-preimport.db"))
        assert len(old) == 1, old
        conn = sqlite3.connect(old[0])
        assert conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0] > 0
        conn.close()
        assert before_old  # the pre-import content existed

        # Refusals leave the target untouched.
        target_hash = sha(target)
        junk = tmp / "junk.db"
        junk.write_bytes(os.urandom(4096))
        expect_refused(install_campaign, junk, "dst", replace=True, backup_dir=backups)
        no_actors = tmp / "empty.db"
        c = sqlite3.connect(no_actors)
        c.execute("CREATE TABLE t(x)")
        c.commit()
        c.close()
        expect_refused(install_campaign, no_actors, "dst", replace=True, backup_dir=backups)

        open_campaign("blank")  # packaged opening world, no protagonist chosen
        with connect_campaign() as conn:
            assert get_player(conn) is None
        blank_out = tmp / "export" / "blank.db"
        export("blank", blank_out)
        expect_refused(install_campaign, blank_out, "dst", replace=True, backup_dir=backups)
        expect_refused(install_campaign, out, "../evil", backup_dir=backups)
        expect_refused(install_campaign, tmp / "missing.db", "other", backup_dir=backups)
        assert sha(target) == target_hash
        assert not (campaign_dir() / "other.db").exists() and not (campaign_dir() / "evil.db").exists()
        assert not [p for p in campaign_dir().iterdir() if "tmp" in p.name or "import" in p.name]

        # The exporter never modifies its source and refuses to overwrite it.
        src_path = campaign_dir() / "src.db"
        before_src = sha(src_path)
        export("src", tmp / "export" / "again.db")
        assert sha(src_path) == before_src
        try:
            export("src", src_path)
        except ValueError:
            pass
        else:
            raise AssertionError("export onto the source was allowed")
    assert sha(ROOT / "data" / "caerness.db") == packaged_before, "packaged database was modified"
    print("connector_import_test passed")


if __name__ == "__main__":
    run()
