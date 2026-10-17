"""Schema 111: unrevealed people's occupation follows Stage; the migration reports what it did."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "m.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        raw = sqlite3.connect(db)
        ver = int(raw.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()[0])
        if ver >= 111:  # the packaged save is already migrated: make it a schema-110 save with the old independent draw
            raw.execute("DELETE FROM schema_migrations WHERE version>=111")
            raw.execute("DELETE FROM engine_meta WHERE key='schema111_report'")
            raw.execute("UPDATE engine_meta SET value='110' WHERE key='schema_version'")
            raw.execute("""UPDATE background_person_profiles SET occupation_domain='physician',social_archetype='ordinary_physician'
                           WHERE status='background' AND current_stage IN ('Breach','Fifth')""")
            raw.commit()
        raw.close()
        from engine.db import connect, init_db
        init_db()
        c = connect()
        assert c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] >= 111
        assert int(c.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()[0]) >= 111
        rep = json.loads(c.execute("SELECT value FROM engine_meta WHERE key='schema111_report'").fetchone()[0])
        assert {"changed", "changed_by_stage", "resolved_mismatch_count", "resolved_mismatches"} <= set(rep), rep
        assert len(rep["resolved_mismatches"]) <= 50
        assert not c.execute("SELECT 1 FROM background_person_profiles WHERE status='background' AND current_stage IN ('Breach','Fifth') "
                             "AND occupation_domain NOT IN ('soldier','criminal') AND json_extract(metadata_json,'$.martial_past') IS NOT 1").fetchone()
        c.close()
    print("schema111_occupation_test passed")


if __name__ == "__main__":
    run()
