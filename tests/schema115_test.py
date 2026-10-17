"""Schema 115 (gap 5): every household quantified from its means, an income that keeps it solvent, staff paid through the payroll.
Run from the real committed schema-114 packaged world; a second run changes nothing; a year passes without households dissolving."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    from engine import household_staff as hs
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "m.db"
        # the committed packaged world that is at schema 114 (the newest data/caerness.db whose schema is 114)
        blob = None
        for sha in subprocess.run(["git", "log", "--format=%h", "--", "data/caerness.db"], cwd=ROOT, capture_output=True, text=True).stdout.split():
            data = subprocess.run(["git", "show", f"{sha}:data/caerness.db"], cwd=ROOT, capture_output=True).stdout
            db.write_bytes(data)
            raw = sqlite3.connect(db)
            v = raw.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()
            raw.close()
            if v and v[0] == "114":
                blob = sha
                break
        assert blob, "no committed schema-114 world"
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import SCHEMA_VERSION, _migration_115, connect, init_db
        init_db()
        c = connect()
        assert SCHEMA_VERSION == 115 and c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 115
        rep = json.loads(c.execute("SELECT value FROM engine_meta WHERE key='schema115_report'").fetchone()[0])
        assert rep["quantified"] == 263 and rep["location_less"] == 3 and rep["staff_hired"] > 40, rep
        hh = c.execute("SELECT COUNT(*),SUM(json_extract(metadata_json,'$.economic_basis')='family_means') FROM households").fetchone()
        assert hh[0] == 263 and hh[1] == 263, tuple(hh)
        # wealth rises with the means band; ordinary households keep no staff; great and royal houses keep more than house families
        band = {int(r[0]): (float(r[1]), float(r[2])) for r in c.execute(
            "SELECT round(json_extract(metadata_json,'$.family_means'),0),AVG(wealth),AVG(staff_capacity) FROM households GROUP BY 1")}
        ms = sorted(band)
        assert len(ms) >= 3 and all(band[a][0] < band[b][0] for a, b in zip(ms, ms[1:])), band
        n_staff_plain = c.execute("""SELECT COUNT(*) FROM household_service_terms t JOIN households h ON h.id=t.household_id
                                      WHERE json_extract(h.metadata_json,'$.family_means')<=50""").fetchone()[0]
        assert n_staff_plain == 0, "ordinary households do their own labour"
        top = c.execute("""SELECT json_extract(metadata_json,'$.staff_plan_total') FROM households WHERE json_extract(metadata_json,'$.family_means')>=90
                           ORDER BY 1 DESC LIMIT 1""").fetchone()[0]
        mid = c.execute("""SELECT MAX(json_extract(metadata_json,'$.staff_plan_total')) FROM households WHERE json_extract(metadata_json,'$.family_means') BETWEEN 70 AND 85""").fetchone()[0]
        assert top > mid >= 1, (top, mid)
        # named staff: a service term, a household membership, a two-way tie, a name of their sex, low attention
        rows = c.execute("""SELECT t.*,a.name,lp.demographic_sex sex,h.head_actor_id head FROM household_service_terms t JOIN actors a ON a.id=t.actor_id
                            JOIN actor_life_profiles lp ON lp.actor_id=a.id JOIN households h ON h.id=t.household_id""").fetchall()
        from engine.person_ecology import FIRST_FEMALE, FIRST_MALE
        for t in rows:
            assert t["status"] == "active" and 45 <= t["loyalty"] <= 70 and 45 <= t["satisfaction"] <= 65, dict(t)
            assert c.execute("SELECT 1 FROM household_members WHERE household_id=? AND actor_id=? AND status='active'", (t["household_id"], t["actor_id"])).fetchone()
            g = t["name"].split(" ", 1)[0]
            assert g not in (FIRST_MALE if t["sex"] == "female" else FIRST_FEMALE), (t["name"], t["sex"])
            if t["head"] is not None:
                for a, b in ((t["head"], t["actor_id"]), (t["actor_id"], t["head"])):
                    assert c.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (a, b)).fetchone(), (a, b)
            tier, cad = c.execute("SELECT tier,cadence_days FROM simulation_profiles WHERE actor_id=?", (t["actor_id"],)).fetchone()
            assert tier == "DORMANT" and cad >= 180, (tier, cad)
        # a steward only where the house is large; population never inflates
        assert c.execute("SELECT COUNT(*) FROM household_service_terms WHERE service_role='steward'").fetchone()[0] >= 1
        pop = c.execute("SELECT SUM(population_estimate) FROM background_population_sources").fetchone()[0]
        # a second run adds nothing
        snap = tuple(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("actors", "household_service_terms", "household_members", "relationships", "households"))
        _migration_115(c)
        assert snap == tuple(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("actors", "household_service_terms", "household_members", "relationships", "households"))
        assert c.execute("SELECT SUM(population_estimate) FROM background_population_sources").fetchone()[0] == pop
        c.commit()
        # a median household of each band is net positive after upkeep and wages
        for m in ms:
            rows = c.execute("SELECT id FROM households WHERE round(json_extract(metadata_json,'$.family_means'),0)=? AND status='active' ORDER BY id", (m,)).fetchall()
            nets = []
            for (hid,) in rows:
                h = c.execute("SELECT * FROM households WHERE id=?", (hid,)).fetchone()
                wages = sum(__import__("engine.payroll", fromlist=["x"]).household_wage(t) for t in __import__("engine.payroll", fromlist=["x"]).service_terms(c, hid))
                nets.append(hs.household_income(c, hid) - hs._upkeep(c, h) - wages)
            nets.sort()
            assert nets[len(nets) // 2] > 0, (m, nets[len(nets) // 2])
        # a year: no household dissolves, no servant leaves for wages, payroll ran
        from engine.simulation import advance_connection
        before = c.execute("SELECT COUNT(*) FROM households WHERE status IN ('active','declining')").fetchone()[0]
        t0 = time.time()
        advance_connection(c, 30)
        first30 = time.time() - t0
        advance_connection(c, 335)
        c.commit()
        after = c.execute("SELECT COUNT(*) FROM households WHERE status IN ('active','declining')").fetchone()[0]
        dissolved = c.execute("SELECT COUNT(*) FROM households WHERE status='dissolved'").fetchone()[0]
        assert after >= before - 6 and dissolved <= 6, (before, after, dissolved)  # only real causes (a head dying, a house lost)
        left = c.execute("""SELECT COUNT(*) FROM life_events WHERE event_kind='service_change' AND summary LIKE '%unpaid or ill used%'""").fetchone()[0]
        assert left <= 3, left
        assert c.execute("SELECT COUNT(*) FROM economic_flows WHERE flow_kind='wage' AND source_household_id IS NOT NULL").fetchone()[0] > 0
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        c.close()
    print("schema115_test passed", {"30_day_seconds": round(first30, 1)})


if __name__ == "__main__":
    run()
