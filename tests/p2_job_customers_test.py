"""A paid job comes from outside the worker's family and household, from somebody who has what it takes and a reason."""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server
        from engine import life_matters as lm
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("jobs", package="saintjude")
        made = server.author("a1", "protagonist", {
            "name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic", "accept": True,
            "family": {"parents": {"father": "alive", "mother": "alive"}, "siblings": [{"sex": "male", "age": 21}]},
            "family_business": {"owner": "father", "type": "auto repair garage", "name": "Basile Auto Repair", "works": ["self", "siblings"]}})
        assert made["status"] == "created", made
        me = made["actor_id"]
        with connect() as conn:
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            jobs = lm.data(conn)["jobs"]
            family = {int(r[0]) for r in conn.execute("SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND ended_day IS NULL", (me,))}
            assert family
            # money is no obstacle to anyone here, so only family and need decide who comes as a customer
            conn.execute("""INSERT OR IGNORE INTO resources(actor_id,resource_type,amount)
                            SELECT actor_id,'cash',100000 FROM actor_life_profiles WHERE life_status='living'""")
            p = lm._Pass(conn, day)
            workers = [me] * 100 + [int(r[0]) for r in conn.execute(
                "SELECT actor_id FROM enterprise_staff WHERE status='active' ORDER BY actor_id")]
            for i, s in enumerate(workers):
                lm._open_work(p, s, random.Random(i))
            rows = conn.execute("SELECT subject_actor_id s,other_actor_id o,data_json,summary FROM life_matters WHERE kind='work'").fetchall()
            assert len(rows) > 30, len(rows)
            seen = set()
            for r in rows:
                s, o, d = int(r["s"]), int(r["o"]), json.loads(r["data_json"])
                assert not lm.family_of(conn, s) & {o}, ("family asked for a paid job", r["summary"])
                spec = jobs[d["trade"]]  # only trades that take such jobs
                assert d["job"] in spec["for"] and d["job"] in r["summary"], (d, r["summary"])
                if spec.get("needs"):
                    assert lm.has(p, o, spec["needs"]), ("a customer without one", r["summary"])
                seen.add(d["trade"])
            assert "barber shop" not in seen and len(seen) > 2, seen
            # not everybody has a car
            some = [int(r[0]) for r in conn.execute("SELECT actor_id FROM enterprise_staff WHERE status='active' ORDER BY actor_id LIMIT 200")]
            have = sum(lm.has(p, a, "car") for a in some)
            assert 0 < have < len(some), have
    print("PASS p2_job_customers_test")


if __name__ == "__main__":
    main()
