from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "manners.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine.manners_canon import LOCATORS, MANNERS, manners_for

        init_db()
        want = {"hearth", "churn", "empire", "court", "dunmoor", "greywood", "windmere", "sunreach", "thornward",
                "stormhollow", "undertow", "road", "default"}
        assert set(MANNERS) == want and set(LOCATORS) == want
        for k, text in MANNERS.items():
            assert 0 < len(text) <= 300, (k, len(text))
            assert LOCATORS[k] and all(l.startswith("[") for l in LOCATORS[k]), k
        with connect() as conn:
            def loc(name):
                return int(conn.execute("SELECT id FROM locations WHERE name LIKE ?", (name,)).fetchone()[0])
            assert manners_for(conn, loc("Toll%")) == MANNERS["hearth"]
            assert manners_for(conn, loc("Toll%"), churn=True) == MANNERS["churn"]
            assert manners_for(conn, loc("Stoneford")) == MANNERS["dunmoor"]
            assert manners_for(conn, loc("Eldenfell")) == MANNERS["greywood"]
            assert manners_for(conn, loc("Saltmere")) == MANNERS["windmere"]
            assert manners_for(conn, loc("The Waystone")) == MANNERS["road"]
            assert manners_for(conn, loc("Crownhold")) == MANNERS["court"]
            assert manners_for(conn, None) == MANNERS["default"]
            assert manners_for(conn, 999999) == MANNERS["default"]
            # every settlement in the packaged world resolves to some line
            for (lid,) in conn.execute("SELECT id FROM locations WHERE kind='settlement'").fetchall():
                assert manners_for(conn, int(lid)) in MANNERS.values()
    print("manners_canon_test passed")


if __name__ == "__main__":
    run()
