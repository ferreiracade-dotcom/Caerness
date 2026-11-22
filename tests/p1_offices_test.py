"""P1 Task 1: offices, terms, the calendar, eligibility and vacancies.

Run: PYTHONPATH=. python tests/p1_offices_test.py"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

MAYOR = "office:city-hall:mayor"


def _age(c, actor, years, day=0):
    c.execute("UPDATE actor_life_profiles SET birth_day=? WHERE actor_id=?", (int(day - years * 365.25), actor))


def test_offices_load_from_package_only():
    from engine import offices
    w = _open_world()
    c = w.conn
    assert c.execute("SELECT COUNT(*) FROM offices").fetchone()[0] > 20
    assert offices.load_offices(c) == c.execute("SELECT COUNT(*) FROM offices").fetchone()[0]  # idempotent
    assert len(offices.holders(c, "office:council:ward-1")) == 1
    assert len(offices.holders(c, "office:zoning:board")) == 5
    assert offices.holder(c, MAYOR) is not None  # the world fact's holder is the opening term
    # a package without politics data has nothing to build, and no error
    saved = offices.rules
    offices.rules = lambda conn: {}
    try:
        assert offices.build(c, 0) == {} and not offices.enabled(c)
    finally:
        offices.rules = saved


def test_holder_mirrors_world_fact():
    from engine import offices
    w = _open_world()
    c = w.conn
    old = offices.holder(c, MAYOR)
    t = offices.seat_holder(c, MAYOR, w.soldier, how="elected", day=500)
    assert c.execute("SELECT holder_actor_id FROM world_facts WHERE key=?", (MAYOR,)).fetchone()[0] == w.soldier
    assert offices.holder(c, MAYOR) == w.soldier
    prior = c.execute("SELECT end_day,ended_how FROM office_terms WHERE actor_id=? AND end_day IS NOT NULL", (old,)).fetchone()
    assert prior["end_day"] == 500 and prior["ended_how"] == "succeeded"
    assert c.execute("SELECT how FROM office_terms WHERE id=?", (t,)).fetchone()[0] == "elected"


def test_eligibility_vetoes_with_reason():
    from engine import offices, player
    w = _open_world()
    c = w.conn
    for who in (w.soldier, w.capo):  # an NPC, then the protagonist, under the same age
        if who == w.capo:
            player.set_player(c, who)
        _age(c, who, 24)
        assert offices.eligible(c, who, MAYOR, 0) == (False, "min_age")
        _age(c, who, 40)
        assert offices.eligible(c, who, MAYOR, 0) == (True, None)
        c.execute("INSERT INTO sentences(actor_id,crime_kind,term_days,start_day,earliest_release_day,end_day) VALUES (?,?,?,?,?,?)",
                  (who, "bribery", 100, 1, 50, 101))
        assert offices.eligible(c, who, MAYOR, 0) == (False, "conviction_bar")
        c.execute("DELETE FROM sentences WHERE actor_id=?", (who,))


def test_calendar_dates():
    from engine import offices
    w = _open_world()
    c = w.conn
    d = offices.next_dates(c, MAYOR, offices.day_of(c, 1975, 1, 1))
    assert d["election_day"] == offices.day_of(c, 1975, 11, 4), d
    assert offices.date_of(c, d["primary_day"]).month == 9 and offices.date_of(c, d["primary_day"]).year == 1975
    d2 = offices.next_dates(c, "office:council:ward-1", offices.day_of(c, 1975, 1, 1))
    assert d2["election_day"] == offices.day_of(c, 1977, 11, 8), d2
    assert offices.next_dates(c, "office:state:governor", 0) == {}  # the real calendar is P2's


def test_vacancy_queues_rule():
    from engine import offices
    w = _open_world()
    c = w.conn
    key = "office:council:ward-3"
    t = c.execute("SELECT t.id FROM office_terms t JOIN offices o ON o.id=t.office_id WHERE o.office_key=? AND t.end_day IS NULL", (key,)).fetchone()[0]
    offices.end_term(c, t, "died", 100)
    v = offices.pending_vacancies(c)
    assert len(v) == 1 and v[0]["office_key"] == key and v[0]["cause"] == "died"
    assert offices.vacancy_rule(c, key) == {"how": "body_chooses", "by": "office:council:body"}
    assert offices.holder(c, key) is None


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
