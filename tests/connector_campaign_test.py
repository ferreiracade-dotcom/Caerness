from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    packaged = ROOT / "data" / "caerness.db"
    before = _sha(packaged)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["CAERNESS_CAMPAIGN_DIR"] = tmp
        from connector.campaign import campaign_dir, connect_campaign, open_campaign

        p = open_campaign("t1")
        assert p.exists() and p.parent == campaign_dir()
        assert os.environ["CAERNESS_DB_PATH"] == str(p)
        with connect_campaign() as conn:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
            assert conn.execute("SELECT name FROM sqlite_master WHERE name='connector_calls'").fetchone()
        with connect_campaign() as conn:
            conn.execute("INSERT INTO connector_meta(key,value) VALUES ('marker','1')")
        p2 = open_campaign("t1")  # must not re-copy over the campaign
        assert p2 == p
        with connect_campaign() as conn:
            assert conn.execute("SELECT value FROM connector_meta WHERE key='marker'").fetchone()[0] == "1"
        for bad in ("bad name!", "", "x" * 41, "../x"):
            try:
                open_campaign(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"accepted {bad!r}")
    assert _sha(packaged) == before, "packaged DB changed"
    print("connector_campaign_test passed")


if __name__ == "__main__":
    run()
