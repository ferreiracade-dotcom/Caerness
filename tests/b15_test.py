"""B15: kinds without a hierarchy of their own still get a new head when theirs dies, and a man never keeps answering to someone gone.

Run: PYTHONPATH=. python tests/b15_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect


def _open():
    path = build_saintjude(Path(tempfile.mkdtemp()))
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    import engine.simulation  # noqa: F401
    return connect(path)


def _head_seat(conn, key, role):
    return conn.execute("SELECT s.actor_id,s.org_actor_id FROM org_seats s JOIN org_profiles o ON o.org_actor_id=s.org_actor_id "
                        "WHERE o.package_key=? AND s.role_key=? AND s.status='active' ORDER BY s.actor_id", (key, role)).fetchone()


def test_a_gang_whose_head_dies_gets_a_new_head():
    from engine.household_life import mark_actor_deceased
    from engine.simulation import advance_connection
    conn = _open()
    picked = []
    for key, role in (("russians", "senior"), ("hijackers", "principal"), ("horsemen", "president")):
        h = _head_seat(conn, key, role)
        assert h is not None, key
        mark_actor_deceased(conn, int(h[0]))
        picked.append((key, role, int(h[0]), int(h[1])))
    conn.commit()
    advance_connection(conn, 21)
    conn.commit()
    for key, role, old, org in picked:
        new = conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active'", (org, role)).fetchall()
        assert new and int(new[0][0]) != old, f"{key} has no new {role}"
        under = conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND status='active' AND superior_actor_id=?", (org, old)).fetchone()[0]
        assert under == 0, f"{key}: {under} men still answer to the dead {role}"


def test_a_man_with_no_living_superior_is_attached_to_his_leader_or_head():
    from engine import org_lifecycle
    conn = _open()
    r = conn.execute("SELECT s.actor_id,s.org_actor_id,s.unit_id FROM org_seats s WHERE s.role_key='soldier' AND s.status='active' AND s.unit_id IS NOT NULL ORDER BY s.actor_id").fetchone()
    a, org, unit = int(r[0]), int(r[1]), int(r[2])
    leader = int(conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (unit,)).fetchone()[0])
    conn.execute("UPDATE org_seats SET superior_actor_id=NULL WHERE actor_id=? AND org_actor_id=?", (a, org))
    assert org_lifecycle._reattach(conn, 100) >= 1
    sup = conn.execute("SELECT superior_actor_id FROM org_seats WHERE actor_id=? AND org_actor_id=?", (a, org)).fetchone()[0]
    assert sup is not None and int(sup) == leader


def test_a_surviving_co_leader_does_not_answer_to_the_dead_one():
    from engine import org_lifecycle
    from engine.household_life import mark_actor_deceased
    conn = _open()
    r = conn.execute("SELECT s.actor_id,s.org_actor_id,s.unit_id,s.superior_actor_id FROM org_seats s WHERE s.role_key='capo' AND s.status='active' ORDER BY s.actor_id").fetchone()
    old, org, unit, above = int(r[0]), int(r[1]), int(r[2]), r[3]
    other = int(conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND unit_id=? AND role_key='soldier' AND status='active' ORDER BY actor_id", (org, unit)).fetchone()[0])
    # a second capo in the same unit who answers to the first: the first dies
    conn.execute("UPDATE org_seats SET role_key='capo', superior_actor_id=? WHERE actor_id=? AND org_actor_id=?", (old, other, org))
    conn.execute("UPDATE org_units SET leader_actor_id=? WHERE id=?", (other, unit))
    mark_actor_deceased(conn, old)
    conn.execute("UPDATE org_seats SET status='dead', left_day=1 WHERE actor_id=? AND org_actor_id=?", (old, org))
    org_lifecycle._process_vacancies(conn, 5)
    sup = conn.execute("SELECT superior_actor_id FROM org_seats WHERE actor_id=? AND org_actor_id=?", (other, org)).fetchone()[0]
    assert sup is None or int(sup) != old, "still answers to the dead man"
    assert sup is not None, "answers to no one (his own leader's superior or the head was available)"


def test_a_family_left_with_no_head_and_nothing_open_takes_the_matter_up():
    from engine import orgs, org_lifecycle
    conn = _open()
    r = conn.execute("SELECT s.actor_id,s.org_actor_id FROM org_seats s JOIN org_profiles o ON o.org_actor_id=s.org_actor_id WHERE o.package_key='sabatini' AND s.role_key='boss' AND s.status='active'").fetchone()
    old, org = int(r[0]), int(r[1])
    conn.execute("UPDATE org_seats SET status='dead', left_day=1 WHERE actor_id=? AND org_actor_id=?", (old, org))  # a vacancy nobody took up
    assert orgs.head_of(conn, org) is None
    assert org_lifecycle._fill_headless(conn, 10) >= 1
    assert orgs.head_of(conn, org) is not None, "still no one in the head's seat"


def test_the_head_who_rose_from_a_unit_is_not_picked_to_lead_it_again():
    from engine import org_lifecycle
    conn = _open()
    r = conn.execute("SELECT s.actor_id,s.org_actor_id,s.unit_id FROM org_seats s WHERE s.role_key='capo' AND s.status='active' ORDER BY s.actor_id").fetchone()
    a, org, unit = int(r[0]), int(r[1]), int(r[2])
    conn.execute("UPDATE org_seats SET role_key='boss' WHERE actor_id=? AND org_actor_id=?", (a, org))  # he rose to head and kept his unit id
    conn.execute("UPDATE org_units SET leader_actor_id=NULL WHERE id=?", (unit,))
    assert a not in {int(x["actor_id"]) for x in org_lifecycle.unit_pool(conn, unit, 10)}


def test_the_law_and_the_organisation_act_on_the_protagonist_as_on_anyone():
    """The protagonist lives under the same rules: made a soldier of the family and named on a homicide report, the law holds, charges and
    disposes of him like the other men, and the organisation's money passes through him like theirs."""
    import json
    from engine import crime_response as cr
    from engine.org_money import Roster, post_period
    from engine.player import set_player
    from tests.outfit_choice_fixture import DAY, forced_roll, open_world
    w = open_world()
    c = w.conn
    cr.ensure_tables(c)
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    men = [int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND role_key='soldier' ORDER BY actor_id LIMIT 4", (w.org,))]
    me, others = men[0], men[1:]
    set_player(c, me)  # the protagonist is the lead on the report
    rid = cr.open_report(c, crime_kind="homicide", day=DAY, offender_actor_id=me, victim_actor_id=None, location_id=w.ground,
                         metadata={"identified": True, "public": True, "co_defendants": others})
    with forced_roll("pad_publicity", "identify"):
        for day in range(DAY + 1, DAY + 4):
            c.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))
            cr.process_due(c, day)
    rep = c.execute("SELECT * FROM crime_reports WHERE id=?", (rid,)).fetchone()
    assert rep["status"] == "arrest", rep["status"]
    assert c.execute("SELECT 1 FROM custody WHERE actor_id=? AND case_id=? AND kind IN ('held','bailed')", (me, rep["case_id"])).fetchone() is not None, "the law did not hold the protagonist"
    meta = json.loads(c.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (rep["case_id"],)).fetchone()[0])
    day = DAY + 4
    while day <= int(meta["disposition_day"]) + 3:
        c.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))
        cr.process_due(c, day)
        day += 1
    assert c.execute("SELECT 1 FROM case_dispositions WHERE actor_id=? AND case_id=?", (me, rep["case_id"])).fetchone() is not None, "the protagonist got no disposition"
    # and the organisation's money: his kick-up and his share are posted as for the others
    before = c.execute("SELECT COUNT(*) FROM org_money WHERE from_actor_id=? OR to_actor_id=?", (me, me)).fetchone()[0]
    post_period(c, day + 60, 60)
    after = c.execute("SELECT COUNT(*) FROM org_money WHERE from_actor_id=? OR to_actor_id=?", (me, me)).fetchone()[0]
    assert after > before, "no organisation money passed through the protagonist"


def _run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {name}: {exc!r}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
