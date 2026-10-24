"""Task 21: a Saint Jude opening, advanced 30 days with the bible indexed, carries no Caerness or old-bible vocabulary."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CAERNESS_TEST_MODE", "1")


def run():
    t0 = time.time()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "sj.db"
        os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
        from tools.build_opening import build_opening
        build_opening(db, package="saintjude")
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect
        from engine.simulation import advance_connection
        from engine.world_package import current_package
        from engine.canon import index_canon

        with connect() as conn:
            advance_connection(conn, 30)
            conn.commit()
            bible = current_package(conn).bible_path
        index_canon(bible)

        from tools import leak_scan
        assert leak_scan.OLD_BIBLE and leak_scan.FORBIDDEN

        # negative controls on a copy: the scanner must see planted leaks
        ctl = Path(tmp) / "ctl.db"
        src = sqlite3.connect(db)
        dst = sqlite3.connect(ctl)
        src.backup(dst)
        src.close()
        dst.execute("UPDATE world_state SET epoch_label = 'the Vein-Root trade'")
        dst.execute("UPDATE locations SET notes = 'Pietro Castellano held court here' WHERE id = (SELECT MIN(id) FROM locations)")
        dst.commit()
        dst.close()
        found = leak_scan.scan(ctl)
        assert any(l.matched == "Vein-Root" and l.kind == "caerness" for l in found), "Vein-Root not found"
        assert any(l.matched == "Pietro Castellano" and l.kind == "old_bible" for l in found), "Pietro Castellano not found"

        leaks = leak_scan.scan(db)
        if leaks:
            print(leak_scan.summarize(leaks))
        assert leaks == [], f"{len(leaks)} leaks"
    print(f"saintjude_leak_scan_test passed ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    run()
