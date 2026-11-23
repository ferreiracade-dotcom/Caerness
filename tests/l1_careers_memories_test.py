"""L1 task 4: the people of the opening have worked for years and know and remember things, tiered by what they hold."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.sj_fixture import build_saintjude, connect  # noqa: E402

CFG = json.loads((ROOT / "worlds" / "saintjude" / "neighbourhood.json").read_text(encoding="utf-8"))["lived_past"]


def _conn(tmp):
    return connect(build_saintjude(Path(tmp)))


def test_leaders_have_work_history_facts_and_memories():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        ph = ",".join("?" * len(CFG["leader_roles"]))
        leaders = c.execute(f"""SELECT s.actor_id,lp.birth_day FROM org_seats s JOIN actor_life_profiles lp ON lp.actor_id=s.actor_id
                                JOIN actors a ON a.id=s.actor_id WHERE s.status='active' AND a.actor_type='character'
                                AND s.role_key IN ({ph})""", CFG["leader_roles"]).fetchall()
        assert len(leaders) > 50
        for r in leaders:
            aid = r["actor_id"]
            car = c.execute("SELECT started_day,status FROM actor_careers WHERE actor_id=?", (aid,)).fetchall()
            assert car, aid
            years = -car[0]["started_day"] / 365.0
            age = -r["birth_day"] / 365.0
            assert 0 < years <= age - CFG["working_age"] + 0.01, (aid, years, age)
            assert c.execute("SELECT COUNT(*) FROM actor_memories WHERE actor_id=?", (aid,)).fetchone()[0] >= 1, aid
            nk = c.execute("SELECT COUNT(*) FROM knowledge WHERE knower_actor_id=?", (aid,)).fetchone()[0]
            assert nk >= CFG["depth"]["staff"][0], (aid, nk)
        c.close()


def test_rows_are_history_and_consistent():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        assert c.execute("SELECT COUNT(*) FROM actor_memories WHERE created_day>0 OR last_reinforced_day>0").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM knowledge WHERE learned_day>0").fetchone()[0] == 0
        assert c.execute("""SELECT COUNT(*) FROM actor_memories m LEFT JOIN actors a ON a.id=m.subject_actor_id
                            WHERE m.subject_actor_id IS NOT NULL AND a.id IS NULL""").fetchone()[0] == 0
        # a stage is never ahead of the years worked
        for r in c.execute("""SELECT ac.started_day,s.stage_key FROM actor_careers ac JOIN career_stages s ON s.id=ac.current_stage_id"""):
            years = -r["started_day"] / 365.0
            need = {k: y for k, _n, y in CFG["career_stages"]}[r["stage_key"]]
            assert years + 0.01 >= need, (tuple(r), need)
        # a person's memory of an incident matches an incident that happened to them
        for r in c.execute("SELECT actor_id,memory_key FROM actor_memories WHERE memory_key LIKE 'incident:%' LIMIT 200"):
            iid = int(r["memory_key"].split(":")[1])
            assert c.execute("SELECT 1 FROM org_incidents WHERE id=? AND (offender_actor_id=? OR victim_actor_id=?)", (iid, r["actor_id"], r["actor_id"])).fetchone()
        c.close()


def test_tiers_bound_the_size():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        nk = c.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        who = c.execute("SELECT COUNT(DISTINCT knower_actor_id) FROM knowledge").fetchone()[0]
        assert nk > 3000 and nk < 40 * who, (nk, who)    # at most the leader depth per holder: no row for every person in the city
        # someone who holds nothing (a spouse revealed for the opening) gets no invented history
        spouse = c.execute("""SELECT u.actor_b_id FROM household_unions u WHERE NOT EXISTS (SELECT 1 FROM org_seats s WHERE s.actor_id=u.actor_b_id)
                              AND NOT EXISTS (SELECT 1 FROM civilian_enterprises e WHERE e.owner_actor_id=u.actor_b_id)
                              AND NOT EXISTS (SELECT 1 FROM enterprise_staff f WHERE f.actor_id=u.actor_b_id) LIMIT 1""").fetchone()
        assert spouse and c.execute("SELECT COUNT(*) FROM knowledge WHERE knower_actor_id=?", (spouse[0],)).fetchone()[0] == 0
        c.close()


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
