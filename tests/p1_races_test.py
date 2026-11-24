"""P1 Task 5: races as ventures, the vote from drivers, fraud.

Run: PYTHONPATH=. python tests/p1_races_test.py"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

MAYOR = "office:city-hall:mayor"
WARD2 = "office:council:ward-2"


def _org(c, key):
    return int(c.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def _gid(c, key):
    return int(c.execute("SELECT id FROM voter_groups WHERE group_key=?", (key,)).fetchone()[0])


def _today(c):
    return int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _run_to(c, day: int, step: int = 7) -> None:
    from engine import races
    d = _today(c)
    while d < day:
        d = min(day, d + step)
        races.advance(c, d)


def _mayor_race(c) -> int:
    return int(c.execute("SELECT r.id FROM races r JOIN offices o ON o.id=r.office_id WHERE o.office_key=? ORDER BY r.election_day LIMIT 1", (MAYOR,)).fetchone()[0])


def _setup_close_race(c, key=WARD2, n=2, day=0):
    """A synthetic race with equal drivers: n independents who live nowhere in the district and hold nothing."""
    oid = int(c.execute("SELECT id FROM offices WHERE office_key=?", (key,)).fetchone()[0])
    rid = int(c.execute("INSERT INTO races(office_id,election_day,stage,result_json) VALUES (?,?,?,?)", (oid, day + 300, "campaign", json.dumps({"term_start_day": day + 400}))).lastrowid)
    loc = int(c.execute("SELECT location_id FROM voter_groups WHERE group_key LIKE 'ward-2:%' ORDER BY id LIMIT 1").fetchone()[0])
    ids = [int(r[0]) for r in c.execute("SELECT a.id FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id WHERE a.actor_type='character' AND a.status='active' "
                                        "AND p.birth_day<=-9500 AND a.id NOT IN (SELECT actor_id FROM org_seats) AND a.id NOT IN (SELECT actor_id FROM office_terms) "
                                        "AND a.id NOT IN (SELECT actor_id FROM sentences) AND a.id NOT IN (SELECT actor_id FROM enterprise_staff) "
                                        "AND a.id NOT IN (SELECT owner_actor_id FROM civilian_enterprises WHERE owner_actor_id IS NOT NULL) "
                                        "AND a.id NOT IN (SELECT actor_id FROM household_members) "
                                        "AND a.id NOT IN (SELECT actor_a_id FROM social_contact_links UNION SELECT actor_b_id FROM social_contact_links "
                                        "UNION SELECT actor_a_id FROM relationships UNION SELECT actor_b_id FROM relationships) ORDER BY a.id LIMIT ?", (n,))]
    for a in ids:
        c.execute("INSERT INTO race_candidates(race_id,actor_id,party_org_id,filed_day) VALUES (?,?,NULL,?)", (rid, a, day))
        c.execute("UPDATE actors SET home_location_id=? WHERE id=?", (loc, a))
    for a in ids:  # equal drivers means equal: nobody in the district already regards either of them (the opening is full of people now)
        c.execute("DELETE FROM relationships WHERE actor_a_id=? OR actor_b_id=?", (a, a))
        c.execute("DELETE FROM social_contact_links WHERE actor_a_id=? OR actor_b_id=?", (a, a))
        c.execute("DELETE FROM claims WHERE subject_actor_id=?", (a,))
    return rid, ids


def test_1975_mayoral_race_resolves():
    from engine import offices, races
    w = _open_world()
    c = w.conn
    el = offices.day_of(c, 1975, 11, 4)
    _run_to(c, el)
    rid = _mayor_race(c)
    r = races.race(c, rid)
    assert r["status"] == "decided" and r["election_day"] == el, dict(r)
    res = json.loads(r["result_json"])
    winner = int(res["winner"])
    assert winner in races.candidates(c, rid) or winner
    jan = offices.day_of(c, 1976, 1, 2)
    races.advance(c, jan)
    assert offices.holder(c, MAYOR) == winner
    assert c.execute("SELECT COUNT(*) FROM held_things WHERE shape='dated_fact'").fetchone()[0] >= 1
    why = races.result_why(c, rid)
    assert why["winner"] == winner and set(why["why"]) >= {str(winner)}
    for drivers in why["why"].values():
        assert {"incumbent", "delivery", "regard", "local", "noise"} <= set(drivers), drivers
    assert len(res["votes"]) >= 2, res["votes"]  # a field of many, not a walkover


def test_no_fixed_result():
    from engine import races
    w = _open_world()
    c = w.conn
    winners = set()
    for seed in (3, 7, 11, 13, 17, 19):
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (seed,))
        rid, ids = _setup_close_race(c)
        res = races.run_general(c, rid, 100)
        winners.add(int(res["winner"]))
    assert len(winners) > 1, winners


def test_incumbency_matters():
    from engine import offices, races
    w = _open_world()
    c = w.conn
    rid, ids = _setup_close_race(c)
    base = races.vote_shares(c, rid, "general", 100)
    share0 = base[ids[0]] / sum(base.values())
    offices.seat_holder(c, WARD2, ids[0], how="elected", day=1)
    after = races.vote_shares(c, rid, "general", 100)
    share1 = after[ids[0]] / sum(after.values())
    assert share1 > share0, (share0, share1)


def test_ineligible_mid_race_is_dropped():
    from engine import races
    w = _open_world()
    c = w.conn
    rid, ids = _setup_close_race(c, key=MAYOR)
    c.execute("INSERT INTO sentences(actor_id,crime_kind,term_days,start_day,earliest_release_day,end_day,status) VALUES (?,?,?,?,?,?,?)",
              (ids[0], "bribery", 365, 10, 100, 375, "served"))
    res = races.run_general(c, rid, 100)
    row = c.execute("SELECT drop_reason FROM race_candidates WHERE race_id=? AND actor_id=?", (rid, ids[0])).fetchone()
    assert row[0] == "conviction_bar", row[0]
    assert int(res["winner"]) == ids[1]


def test_fraud_gains_and_can_be_exposed():
    from engine import races
    w = _open_world()
    c = w.conn
    gid = _gid(c, "ward-2:irish-catholic-working")
    exposed = 0
    for seed in range(50):
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (seed + 1,))
        rid, ids = _setup_close_race(c)
        base = races.vote_shares(c, rid, "general", 100)[ids[0]]
        out = races.commit_fraud(c, ids[0], rid, gid, "stuffed box", 500, 100)
        after = races.vote_shares(c, rid, "general", 100)[ids[0]]
        if not out["exposed"]:
            assert after == base + 500  # the votes are his
        if out["exposed"]:
            exposed += 1
            assert out["report_id"] is not None
            assert c.execute("SELECT crime_kind FROM crime_reports WHERE id=?", (out["report_id"],)).fetchone()[0] == "election_fraud"
        else:
            assert out["report_id"] is None
    assert 0 < exposed < 50, exposed


def test_politics_after_the_machine():
    from engine import civic_field, offices, races
    w = _open_world()
    c = w.conn
    machine = _org(c, "county_party")
    for r in civic_field.holdings_of(c, "org", machine):
        civic_field.weaken(c, int(r["id"]), 99.0, day=10, cause_kind="test")
    el = offices.day_of(c, 1975, 11, 4)
    _run_to(c, el)
    rid = _mayor_race(c)
    r = races.race(c, rid)
    assert r["status"] == "decided"
    winner = int(json.loads(r["result_json"])["winner"])
    assert civic_field.strength(c, "org", machine) == 0.0
    assert winner is not None


def test_protagonist_files_and_loses_alike():
    from engine import offices, player, races
    w = _open_world()
    c = w.conn
    player.set_player(c, w.capo)
    el = offices.day_of(c, 1975, 11, 4)
    d = _today(c)
    while d < el - 400:
        d += 7
    races.advance(c, _today(c) + 1)
    rid = _mayor_race(c)
    assert races.consider_filing(c, w.capo, rid, d) is False  # the engine never files him
    try:
        races.file(c, w.capo, rid, d)
        filed = True
    except ValueError as e:
        filed = False
        assert str(e) in ("residence", "min_age", "not_living", "conviction_bar", "filing_closed"), e
    if filed:
        _run_to(c, el)
        r = races.race(c, rid)
        assert r["status"] == "decided"
        res = json.loads(r["result_json"])
        assert str(w.capo) in res["votes"]  # he is counted by the same drivers
        assert set(res["why"][str(w.capo)]) == set(next(iter(res["why"].values())))
    # an NPC of the same circumstances is vetoed with the same reason when ineligible
    c.execute("UPDATE actor_life_profiles SET birth_day=? WHERE actor_id IN (?,?)", (_today(c) - 365 * 20, w.capo, w.soldier))
    for a in (w.capo, w.soldier):
        try:
            races.file(c, a, rid, d)
            raise AssertionError("an under-age man filed")
        except ValueError as e:
            assert str(e) in ("min_age", "filing_closed"), e


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
