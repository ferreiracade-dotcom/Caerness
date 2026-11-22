"""P1 Task 8: corruption and the law.

Run: PYTHONPATH=. python tests/p1_corruption_test.py"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

COUNCIL = "office:council:body"
WARD3 = "office:council:ward-3"
MAYOR = "office:city-hall:mayor"
PROS = "office:county-prosecutor:killbuck-county-prosecutor"


def _org(c, key):
    return int(c.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def _trial(c, seed, fn):
    c.execute("SAVEPOINT trial")
    try:
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (seed,))
        return fn()
    finally:
        c.execute("ROLLBACK TO trial")
        c.execute("RELEASE trial")


def _yes_rate(c, member, sponsor, seeds=80):
    from engine import civic_votes
    yes = 0
    for s in range(1, seeds + 1):
        def go():
            iid = civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": sponsor, "title": f"x{s}"}, vote_day=60, day=50)
            return civic_votes.member_vote(c, iid, member, 60)[0]
        yes += _trial(c, s, go) == "yes"
    return yes / seeds


def test_bribed_member_votes_the_payers_way_more_often():
    from engine import civic_corruption, offices
    w = _open_world()
    c = w.conn
    member = [a for _, _, a in offices.members(c, COUNCIL) if a not in (w.capo, w.soldier)][0]
    payer = w.soldier
    before = _yes_rate(c, member, payer)
    civic_corruption.put_on(c, "actor", payer, member, 400.0, day=10)
    after = _yes_rate(c, member, payer)
    assert after > before + 0.05, (before, after)
    assert 0.0 < after < 1.0, after  # a lean, not a lock


def test_exposure_opens_a_case_and_conviction_vacates():
    from engine import civic_corruption, offices
    w = _open_world()
    c = w.conn
    holder = offices.holder(c, WARD3)
    civic_corruption.put_on(c, "actor", w.soldier, holder, 2000.0, day=10)
    opened = None
    for s in range(1, 400):
        c.execute("SAVEPOINT x")
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (s,))
        ids = civic_corruption.exposure_check(c, 100 + s)
        if ids:
            opened = (s, ids)
            row = c.execute("SELECT crime_kind,offender_actor_id FROM crime_reports WHERE id=?", (ids[0],)).fetchone()
            assert row[0] == "bribery" and row[1] == holder
            assert c.execute("SELECT status FROM org_arrangements WHERE official_actor_id=?", (holder,)).fetchone()[0] == "ended"
            break
        c.execute("ROLLBACK TO x")
        c.execute("RELEASE x")
    assert opened is not None
    # a conviction of a barred kind vacates the seat, and the vacancy is queued under the office's rule
    c.execute("INSERT INTO sentences(actor_id,crime_kind,term_days,start_day,earliest_release_day,end_day,status) VALUES (?,?,?,?,?,?,?)",
              (holder, "bribery", 365, 200, 300, 565, "serving"))
    assert holder in offices.holders(c, WARD3)
    assert civic_corruption.convictions(c, 210) == 1
    assert holder not in offices.holders(c, WARD3)
    assert any(v["office_key"] == WARD3 and v["cause"].startswith("convicted") for v in offices.pending_vacancies(c))


def test_deal_pressure_applies_to_politicians():
    from engine import offices, org_informing
    w = _open_world()
    c = w.conn
    machine = _org(c, "county_party")
    holder = int(c.execute("SELECT leader_actor_id FROM org_units WHERE org_actor_id=? AND leader_actor_id IS NOT NULL ORDER BY id LIMIT 1", (machine,)).fetchone()[0])
    offices.seat_holder(c, WARD3, holder, how="elected", day=1)
    party = [r for r in c.execute("SELECT org_actor_id,role_key FROM org_seats WHERE actor_id=? AND status='active'", (holder,)).fetchall()
             if r["role_key"] in ((org_informing.idata(c).get("roles") or {}).get("party") or [])]
    assert party, "a party man is among those the law can turn"
    org = int(party[0]["org_actor_id"])
    assert org_informing._turnable(c, holder, org)
    f = org_informing._man_factors(c, holder, org, 100)
    assert set(f) >= {"leverage", "arrested", "greed", "disloyal", "afraid"}
    assert f["leverage"] == 0
    from engine import crime_response
    crime_response.open_report(c, crime_kind="bribery", day=95, offender_actor_id=holder)
    g = org_informing._man_factors(c, holder, org, 100)
    assert g["leverage"] + g["arrested"] > 0, c.execute("SELECT status FROM crime_reports WHERE offender_actor_id=?", (holder,)).fetchall()  # a case against him leans him toward turning, as for any man


def test_ambition_scales_with_rank():
    from engine import civic_corruption, offices
    w = _open_world()
    c = w.conn
    pros = offices.holder(c, PROS)
    mayor = offices.holder(c, MAYOR)
    member = offices.holder(c, WARD3)
    assert civic_corruption.ambition(c, pros, mayor) > civic_corruption.ambition(c, pros, member) > 0
    c.execute("UPDATE actor_drives SET ambition=? WHERE actor_id=?", (0.9, pros))
    hi = civic_corruption.ambition(c, pros, mayor)
    c.execute("UPDATE actor_drives SET ambition=? WHERE actor_id=?", (0.1, pros))
    assert hi > civic_corruption.ambition(c, pros, mayor)


def test_protagonist_bribes_and_is_exposed_alike():
    from engine import civic_corruption, offices, player
    w = _open_world()
    c = w.conn
    player.set_player(c, w.capo)
    npc = offices.holder(c, "office:council:ward-1")
    offices.seat_holder(c, WARD3, w.capo, how="elected", day=1)
    a_npc = civic_corruption.put_on(c, "actor", w.soldier, npc, 500.0, day=10)
    a_pc = civic_corruption.put_on(c, "actor", w.soldier, w.capo, 500.0, day=10)
    rows = {i: c.execute("SELECT * FROM org_arrangements WHERE id=?", (i,)).fetchone() for i in (a_npc, a_pc)}
    p1, t1 = civic_corruption.exposure_chance(c, rows[a_npc], 100)
    p2, t2 = civic_corruption.exposure_chance(c, rows[a_pc], 100)
    assert set(t1) == set(t2) and 0 < p1 < 1 and 0 < p2 < 1
    hit = False
    for s in range(1, 600):
        c.execute("SAVEPOINT y")
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (s,))
        ids = civic_corruption.exposure_check(c, 100 + s)
        who = {c.execute("SELECT offender_actor_id FROM crime_reports WHERE id=?", (i,)).fetchone()[0] for i in ids}
        c.execute("ROLLBACK TO y")
        c.execute("RELEASE y")
        if w.capo in who:
            hit = True
            break
    assert hit, "the protagonist's payment comes to light by the same draw"


if __name__ == "__main__":
    failed = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f()
                print("PASS", n)
            except Exception:
                failed += 1
                print("FAIL", n)
                traceback.print_exc()
    sys.exit(1 if failed else 0)
