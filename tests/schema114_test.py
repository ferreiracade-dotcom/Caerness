"""Schema 114 (gap 4b fix pass): from the real committed schema-113 packaged world, fronts run as businesses, city businesses have owners,
outfits have named people, loyalty starts dispersed; a second run changes nothing."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REAL_113 = "bff7fff"  # the commit that packaged the schema-113 world


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "m.db"
        db.write_bytes(subprocess.run(["git", "show", f"{REAL_113}:data/caerness.db"], cwd=ROOT, capture_output=True, check=True).stdout)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        raw = sqlite3.connect(db)
        assert raw.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()[0] == "113"
        before = raw.execute("SELECT COUNT(*) FROM underworld_personnel WHERE status='active'").fetchone()[0]
        raw.close()
        from engine.db import SCHEMA_VERSION, _migration_114, connect, init_db
        init_db()
        c = connect()
        assert SCHEMA_VERSION == 114 and c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 114
        rep = json.loads(c.execute("SELECT value FROM engine_meta WHERE key='schema114_report'").fetchone()[0])
        assert rep["named_people_seeded"] > 150 and rep["front_profiles_backfilled"] > 50, rep
        assert c.execute("SELECT COUNT(*) FROM underworld_personnel WHERE status='active'").fetchone()[0] == before + rep["named_people_seeded"]
        assert c.execute("""SELECT COUNT(*) FROM civilian_enterprises e WHERE e.metadata_json LIKE '%underworld_front%' AND e.status<>'closed'
                            AND NOT EXISTS (SELECT 1 FROM enterprise_business_profiles p WHERE p.enterprise_id=e.id)""").fetchone()[0] == 0
        snap = (c.execute("SELECT COUNT(*) FROM underworld_personnel").fetchone()[0], c.execute("SELECT COUNT(*) FROM enterprise_business_profiles").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM actors").fetchone()[0])
        _migration_114(c)
        assert snap == (c.execute("SELECT COUNT(*) FROM underworld_personnel").fetchone()[0], c.execute("SELECT COUNT(*) FROM enterprise_business_profiles").fetchone()[0],
                        c.execute("SELECT COUNT(*) FROM actors").fetchone()[0]), "a second run changed the world"
        assert c.execute("SELECT value FROM engine_meta WHERE key='schema114_report'").fetchone()[0] == json.dumps(rep, sort_keys=True)
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        c.close()
    print("schema114_test passed")


if __name__ == "__main__":
    run()
