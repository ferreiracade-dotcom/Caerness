"""Prison J1.2: admission, assignment and the facility a man goes to, for NPCs and the protagonist alike.

Run: PYTHONPATH=. python tests/j1_admission_test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, open_world  # noqa: E402

from engine import orgs, prison  # noqa: E402
from engine.player import set_player  # noqa: E402

_CASE = [0]


def _profile(c, authority: str) -> int:
    r = c.execute("SELECT id FROM law_enforcement_profiles WHERE authority_kind=? ORDER BY id LIMIT 1", (authority,)).fetchone()
    return int(r[0]) if r is not None else 0


def _convict(c, actor: int, term: int, authority: str = "municipal", day: int = DAY) -> int:
    """What the case chain leaves behind: a serving sentence and a held custody row (the chain itself is tested in crime_response_test)."""
    _CASE[0] += 1
    case = 8_000_000 + _CASE[0]
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))
    sid = c.execute(
        """INSERT INTO sentences(actor_id,case_id,crime_kind,term_days,start_day,earliest_release_day,end_day,facility,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,'serving',?)""",
        (actor, case, "robbery", term, day, day + term // 3, day + term, "the county jail", json.dumps({"agency_profile_id": _profile(c, authority)}))).lastrowid
    c.execute("INSERT INTO custody(actor_id,case_id,agency_profile_id,kind,charge,since_day,until_day) VALUES (?,?,?,'held','robbery',?,?)",
              (actor, case, _profile(c, authority), day, day + term // 3))
    return int(sid)


def _remand(c, actor: int, authority: str = "municipal", day: int = DAY) -> None:
    _CASE[0] += 1
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))
    c.execute("INSERT INTO custody(actor_id,case_id,agency_profile_id,kind,charge,since_day,until_day) VALUES (?,?,?,'held','robbery',?,NULL)",
              (actor, 8_000_000 + _CASE[0], _profile(c, authority), day))


def _men(c, n: int) -> list[int]:
    return [int(r[0]) for r in c.execute("SELECT DISTINCT actor_id FROM org_seats WHERE status='active' ORDER BY actor_id LIMIT ?", (n,))]


def _stay(c, actor: int):
    return c.execute("SELECT * FROM inmate_stays WHERE actor_id=? AND status='inside'", (actor,)).fetchone()


def _fac(c, stay):
    return c.execute("SELECT * FROM facilities WHERE id=?", (stay["facility_id"],)).fetchone()


def _run(c, day: int = DAY + 1) -> dict:
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))
    return prison.process_due(c, day)


def _as_protagonist(c, actor: int) -> None:
    set_player(c, actor)


def test_conviction_admits_to_the_facility_the_data_names():
    for protagonist in (False, True):
        w = open_world()
        c = w.conn
        prison.ensure_facilities(c)
        a = w.soldier
        if protagonist:
            _as_protagonist(c, a)
        sid = _convict(c, a, 1000)
        out = _run(c)
        assert out["admitted"] >= 1 and _stay(c, a) is not None, out  # the lived opening already holds a man
        st = _stay(c, a)
        fac = _fac(c, st)
        assert fac["key"] == "ironhaven", dict(fac)  # a state felony term over a year goes to the state prison
        assert st["sentence_id"] == sid and st["until_day"] is not None
        assert c.execute("SELECT facility FROM sentences WHERE id=?", (sid,)).fetchone()[0] == fac["name"]
        assert c.execute("SELECT current_location_id FROM actors WHERE id=?", (a,)).fetchone()[0] == fac["location_id"]
        if protagonist:
            assert c.execute("SELECT current_location_id FROM player_state WHERE id=1").fetchone()[0] == fac["location_id"]
        assert c.execute("SELECT COUNT(*) FROM inmate_stays WHERE actor_id=? AND status='inside'", (a,)).fetchone()[0] == 1
        # his seat in the group, and the group's headcount went up
        grp = c.execute("SELECT * FROM facility_groups WHERE id=?", (st["group_id"],)).fetchone()
        seat = orgs.seat_of(c, a, grp["org_actor_id"])
        assert seat is not None and seat["status"] == "active" and seat["role_key"] == "member"
        assert _run(c, DAY + 2)["admitted"] == 0  # once only


def test_a_man_of_the_life_goes_to_the_connected_group():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    _convict(c, w.soldier, 1000)
    _run(c)
    st = _stay(c, w.soldier)
    assert c.execute("SELECT group_key FROM facility_groups WHERE id=?", (st["group_id"],)).fetchone()[0] == "connected"


def test_pretrial_man_goes_to_remand_and_federal_remand_to_the_detention_center():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    a, b = _men(c, 2)
    _remand(c, a, "municipal")
    _remand(c, b, "federal")
    out = _run(c)
    assert out["admitted"] >= 2 and _stay(c, a) and _stay(c, b), out  # the lived opening already holds a man
    assert _fac(c, _stay(c, a))["key"] == "county_jail"
    assert _fac(c, _stay(c, b))["key"] == "federal_detention_center"
    assert _stay(c, a)["sentence_id"] is None


def test_sentence_after_remand_moves_him_or_keeps_the_stay():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    a, b = _men(c, 2)
    _remand(c, a)
    _remand(c, b)
    _run(c)
    first_a, first_b = int(_stay(c, a)["id"]), int(_stay(c, b)["id"])
    _convict(c, a, 200, day=DAY + 5)  # a short term: the county jail again, the same stay
    c.execute("UPDATE custody SET until_day=? WHERE actor_id=? AND kind='held'", (DAY + 70, a))
    _convict(c, b, 1500, day=DAY + 5)  # a long term: the state prison
    _run(c, DAY + 6)
    assert int(_stay(c, a)["id"]) == first_a and _stay(c, a)["sentence_id"] is not None
    assert int(_stay(c, b)["id"]) != first_b and _fac(c, _stay(c, b))["key"] == "ironhaven"
    assert c.execute("SELECT status FROM inmate_stays WHERE id=?", (first_b,)).fetchone()[0] == "transferred"
    assert c.execute("SELECT COUNT(*) FROM inmate_stays WHERE actor_id=? AND status='inside'", (b,)).fetchone()[0] == 1


def test_federal_case_to_federal_facility():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    a, b = _men(c, 2)
    _convict(c, a, 5000, "federal")  # the longest terms: a penitentiary, far off
    _convict(c, b, 1000, "federal")
    _run(c)
    fa, fb = _fac(c, _stay(c, a)), _fac(c, _stay(c, b))
    assert fa["level"] == "federal_penitentiary" and json.loads(fa["metadata_json"])["off_map"], dict(fa)
    assert fb["level"] in ("federal_penitentiary", "federal_camp"), dict(fb)
    assert fa["key"] != "danbury"  # the camp takes terms up to five years


def test_woman_held_apart():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    a, b, p = _men(c, 3)
    for x in (a, b, p):
        c.execute("INSERT INTO actor_life_profiles(actor_id,demographic_sex) VALUES (?, 'female') ON CONFLICT(actor_id) DO UPDATE SET demographic_sex='female'", (x,))
    _remand(c, a)
    _convict(c, b, 1000)
    _as_protagonist(c, p)
    _convict(c, p, 1000)
    _run(c)
    assert _fac(c, _stay(c, a))["key"] == "county_jail_women"
    assert _fac(c, _stay(c, b))["key"] == "ironhaven_women"
    assert _fac(c, _stay(c, p))["key"] == "ironhaven_women"
    men = c.execute("""SELECT COUNT(*) FROM inmate_stays t JOIN facilities f ON f.id=t.facility_id
                       WHERE f.key IN ('county_jail','ironhaven') AND t.actor_id IN (?,?,?)""", (a, b, p)).fetchone()[0]
    assert men == 0


def test_cooperator_goes_to_protective_custody():
    for protagonist in (False, True):
        w = open_world()
        c = w.conn
        prison.ensure_facilities(c)
        a = w.soldier
        if protagonist:
            _as_protagonist(c, a)
        c.execute("INSERT INTO org_incidents(day,kind,offender_actor_id,status) VALUES (?, 'informs', ?, 'open')", (DAY - 3, a))
        _convict(c, a, 1000)
        _run(c)
        st = _stay(c, a)
        assert st["protective"] == 1
        assert c.execute("SELECT group_key FROM facility_groups WHERE id=?", (st["group_id"],)).fetchone()[0] == "protective"


def test_no_room_falls_to_declared_fallback_and_a_woman_to_one_that_takes_her():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    a, b = _men(c, 2)
    c.execute("INSERT INTO actor_life_profiles(actor_id,demographic_sex) VALUES (?, 'female') ON CONFLICT(actor_id) DO UPDATE SET demographic_sex='female'", (b,))
    f1 = prison.assign_facility(c, a, term_days=100, authority="nowhere", pretrial=False, day=DAY)
    f2 = prison.assign_facility(c, b, term_days=100, authority="nowhere", pretrial=False, day=DAY)
    key = lambda fid: c.execute("SELECT key FROM facilities WHERE id=?", (fid,)).fetchone()[0]  # noqa: E731
    assert key(f1) == prison.rules(c)["fallback_facility"]
    assert key(f2) == "county_jail_women"


def test_release_closes_the_stay_and_sends_him_back():
    for protagonist in (False, True):
        w = open_world()
        c = w.conn
        prison.ensure_facilities(c)
        a = w.soldier
        if protagonist:
            _as_protagonist(c, a)
        before = c.execute("SELECT current_location_id FROM actors WHERE id=?", (a,)).fetchone()[0]
        sid = _convict(c, a, 1000)
        _run(c)
        st = _stay(c, a)
        head_before = c.execute("SELECT headcount FROM facilities WHERE id=?", (st["facility_id"],)).fetchone()[0]
        c.execute("UPDATE sentences SET status='released', released_day=? WHERE id=?", (DAY + 400, sid))
        c.execute("UPDATE custody SET kind='released', until_day=? WHERE actor_id=?", (DAY + 400, a))
        out = _run(c, DAY + 400)
        assert out["left"] == 1, out
        assert c.execute("SELECT status FROM inmate_stays WHERE id=?", (st["id"],)).fetchone()[0] == "released"
        assert c.execute("SELECT current_location_id FROM actors WHERE id=?", (a,)).fetchone()[0] == before
        assert c.execute("SELECT headcount FROM facilities WHERE id=?", (st["facility_id"],)).fetchone()[0] == head_before - 1
        grp = c.execute("SELECT * FROM facility_groups WHERE id=?", (st["group_id"],)).fetchone()
        assert orgs.seat_of(c, a, grp["org_actor_id"])["status"] == "out"
        # back inside later: the same seat row comes back (one seat per man and group)
        _convict(c, a, 1000, day=DAY + 500)
        _run(c, DAY + 501)
        assert _stay(c, a) is not None and orgs.seat_of(c, a, grp["org_actor_id"])["status"] == "active"


def test_a_hold_with_no_case_is_a_term_by_its_length():
    """The lived opening holds a man for a sentence he began before the game, and an organisation's arrests hold men for days: neither has a case row."""
    for protagonist in (False, True):
        w = open_world()
        c = w.conn
        prison.ensure_facilities(c)
        a, b = _men(c, 2)
        if protagonist:
            _as_protagonist(c, a)
        c.execute("DELETE FROM custody")
        c.execute("INSERT INTO custody(actor_id,case_id,kind,charge,since_day,until_day) VALUES (?,NULL,'held','x',?,?)", (a, DAY - 365, DAY + 600))
        c.execute("INSERT INTO custody(actor_id,case_id,kind,charge,since_day,until_day) VALUES (?,NULL,'held','x',?,?)", (b, DAY, DAY + 20))
        _run(c)
        assert _fac(c, _stay(c, a))["key"] == "ironhaven"  # a term of nearly three years
        assert _fac(c, _stay(c, b))["key"] == "county_jail"  # a few weeks
        assert _stay(c, a)["until_day"] == DAY + 600
        c.execute("UPDATE custody SET kind='released' WHERE actor_id=?", (b,))
        _run(c, DAY + 25)
        assert _stay(c, b) is None and _stay(c, a) is not None


def test_next_due_day_is_tomorrow_only_when_there_is_work():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    c.execute("UPDATE custody SET kind='released' WHERE kind='held'")  # the lived opening's man held at the start is not what this is about
    assert prison.next_due_day(c, DAY, DAY + 30) is None
    _convict(c, w.soldier, 1000)
    assert prison.next_due_day(c, DAY, DAY + 30) == DAY + 1
    _run(c)
    # men are inside now, so the next work is the inside week (the cadence), not tomorrow
    assert prison.next_due_day(c, DAY + 1, DAY + 30) == DAY + 1 + prison.rules(c)["cadence_days"]


def test_the_module_names_no_player_branch():
    src = (ROOT / "engine" / "prison.py").read_text(encoding="utf-8")
    assert "get_player" not in src and "is_player" not in src and "protagonist" not in src.lower().replace("the protagonist", "")


def main() -> None:
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            ran += 1
            print("ok", name)
    print(f"{ran} tests passed")


if __name__ == "__main__":
    main()
