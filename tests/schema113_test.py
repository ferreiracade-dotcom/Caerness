"""Schema 113 (gap 4b): every outfit ticks and has a treasury, own fronts are not protected by rivals, ground and relations seeded."""
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


REAL_112 = "39b35da"  # the last commit that carried the real schema-112 packaged world


def run():
    import subprocess
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "m.db"
        blob = subprocess.run(["git", "show", f"{REAL_112}:data/caerness.db"], cwd=ROOT, capture_output=True, check=True).stdout
        db.write_bytes(blob)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        raw = sqlite3.connect(db)
        raw.row_factory = sqlite3.Row
        assert raw.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()[0] == "112", "not a real schema-112 save"
        assert raw.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 112
        ids = [int(r[0]) for r in raw.execute("SELECT id FROM underworld_organizations WHERE status='active' ORDER BY id LIMIT 3")]
        for i in ids[:2]:  # the real save has heat rows for its outfits; two that never ticked, as in the older saves
            raw.execute("DELETE FROM underworld_heat WHERE organization_id=?", (i,))
        missing_heat = raw.execute("""SELECT COUNT(*) FROM underworld_organizations o WHERE o.status IN ('active','strained','fragmented')
                                      AND NOT EXISTS (SELECT 1 FROM underworld_heat h WHERE h.organization_id=o.id)""").fetchone()[0]
        assert missing_heat >= 2, missing_heat
        earned = ids[2]
        raw.execute("UPDATE underworld_organizations SET treasury=7.5 WHERE id=?", (earned,))
        raw.execute("INSERT INTO underworld_finance_transactions(organization_id,day,transaction_kind,amount,metadata_json) VALUES (?,0,'criminal_income_kickup',3,'{}')", (earned,))
        raw.commit()
        raw.close()

        from engine.db import connect, init_db, SCHEMA_VERSION
        init_db()
        c = connect()
        assert SCHEMA_VERSION >= 113 and c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
        rep = json.loads(c.execute("SELECT value FROM engine_meta WHERE key='schema113_report'").fetchone()[0])
        for key in ("heat_rows_added", "treasuries_seeded", "own_front_protection_ended", "outfits_given_ground", "baseline_relations_seeded"):
            assert key in rep, (key, rep)
        assert rep["heat_rows_added"] == missing_heat, (rep, missing_heat)
        assert c.execute("""SELECT COUNT(*) FROM underworld_organizations o WHERE o.status IN ('active','strained','fragmented')
                            AND NOT EXISTS (SELECT 1 FROM underworld_heat h WHERE h.organization_id=o.id)""").fetchone()[0] == 0
        assert abs(c.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (earned,)).fetchone()[0] - 7.5) < 1e-9, "an outfit that had earned money was touched"
        seeded = c.execute("SELECT COUNT(*) FROM underworld_organizations WHERE status='active' AND treasury>0 AND id<>?", (earned,)).fetchone()[0]
        assert seeded == rep["treasuries_seeded"] and seeded > 200, (seeded, rep)
        # no rival protects another outfit's own front
        bad = c.execute("""SELECT COUNT(*) FROM underworld_protection_accounts p JOIN underworld_business_links l ON l.enterprise_id=p.enterprise_id
                           WHERE p.status='active' AND l.status='active' AND l.link_kind IN ('owned_front','controlled_front') AND l.organization_id<>p.protector_organization_id""").fetchone()[0]
        assert bad == 0, bad
        assert c.execute("SELECT COUNT(*) FROM underworld_incidents WHERE incident_kind='protection_dispute'").fetchone()[0] >= rep["own_front_protection_ended"]
        # outfits sharing a city know each other
        pairs = missing = 0
        by_city: dict = {}
        for r in c.execute("SELECT id,primary_location_id FROM underworld_organizations WHERE status='active' AND primary_location_id IS NOT NULL"):
            by_city.setdefault(int(r[1]), []).append(int(r[0]))
        for orgs in by_city.values():
            for i, x in enumerate(orgs):
                for y in orgs[i + 1:]:
                    pairs += 1
                    a, b = sorted((x, y))
                    if not c.execute("SELECT 1 FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a, b)).fetchone():
                        missing += 1
        assert pairs > 500 and missing == 0, (pairs, missing)
        hostility = c.execute("SELECT MIN(hostility),MAX(hostility) FROM underworld_relations").fetchone()
        assert hostility[0] >= 0 and hostility[1] <= 100
        # specialists and canon durable families still hold fronts, not ground
        held = c.execute("""SELECT COUNT(*) FROM underworld_zone_claims z JOIN underworld_organizations o ON o.id=z.organization_id
                            WHERE z.status='active' AND (json_extract(o.metadata_json,'$.role')='specialist' OR json_extract(o.metadata_json,'$.source')='world_bible')""").fetchone()[0]
        assert held == 0, held
        # the new tables are there
        for t in ("underworld_temperament", "underworld_grudges", "payroll_arrears"):
            assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone(), t
        # idempotent
        snap = (c.execute("SELECT SUM(treasury) FROM underworld_organizations").fetchone()[0], c.execute("SELECT COUNT(*) FROM underworld_relations").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM underworld_zone_claims").fetchone()[0], c.execute("SELECT COUNT(*) FROM underworld_incidents").fetchone()[0])
        from engine.db import _migration_113
        rep0 = c.execute("SELECT value FROM engine_meta WHERE key='schema113_report'").fetchone()[0]
        _migration_113(c)
        assert c.execute("SELECT value FROM engine_meta WHERE key='schema113_report'").fetchone()[0] == rep0, "a re-run overwrote the report of the run that did the work"
        again = (c.execute("SELECT SUM(treasury) FROM underworld_organizations").fetchone()[0], c.execute("SELECT COUNT(*) FROM underworld_relations").fetchone()[0],
                 c.execute("SELECT COUNT(*) FROM underworld_zone_claims").fetchone()[0], c.execute("SELECT COUNT(*) FROM underworld_incidents").fetchone()[0])
        assert snap == again, (snap, again)
        c.execute("PRAGMA integrity_check")
        c.close()
    print("schema113_test passed")


if __name__ == "__main__":
    run()
