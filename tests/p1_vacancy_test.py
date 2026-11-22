"""P1 Task 9: vacancies filled by each office's rule.

Run: PYTHONPATH=. python tests/p1_vacancy_test.py"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

MAYOR = "office:city-hall:mayor"
WARD1 = "office:council:ward-3"
WORKS1 = "office:works:board-seat-1"
CHAIR = "office:party:county-chairman"
COUNCIL = "office:council:body"


def _die(c, key, day):
    """The holder dies: the term ends with that cause and the vacancy is queued under the office's rule."""
    from engine import offices
    for t in offices._open_terms(c, key):
        c.execute("UPDATE actors SET status='dead' WHERE id=?", (int(t["actor_id"]),))
        offices.end_term(c, int(t["id"]), "died", day)


def _vac(c, key):
    return c.execute("SELECT v.* FROM office_vacancies v JOIN offices o ON o.id=v.office_id WHERE o.office_key=? ORDER BY v.id DESC LIMIT 1", (key,)).fetchone()


def test_each_vacancy_rule_fills():
    from engine import civic_votes, offices, races
    w = _open_world()
    c = w.conn
    day = 100
    for key in (MAYOR, WARD1, WORKS1):
        _die(c, key, day)
    for t in offices._open_terms(c, CHAIR):
        offices.end_term(c, int(t["id"]), "resigned", day)
    for key in (MAYOR, WARD1, WORKS1, CHAIR):
        assert offices.holder(c, key) is None and _vac(c, key)["status"] == "pending"
    wait = 21
    assert offices.process_vacancies(c, day + wait - 1) == 0  # not yet: the rule waits
    filled = {}
    for s in range(1, 40):
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (s,))
        offices.process_vacancies(c, day + wait + s)
        civic_votes.advance(c, day + wait + s)
        for key in (WARD1, WORKS1, CHAIR):
            if offices.holder(c, key) is not None:
                filled.setdefault(key, (s, _vac(c, key)["filled_how"]))
        if len(filled) == 3:
            break
    assert set(filled) == {WARD1, WORKS1, CHAIR}, filled
    assert filled[WARD1][1] == "elected" and filled[WORKS1][1] == "appointed" and filled[CHAIR][1] == "succeeded", filled
    # the special election is dated from the vacancy, runs, and seats its winner (a void race is called again by the rule)
    race = c.execute("SELECT r.* FROM races r JOIN offices o ON o.id=r.office_id WHERE o.office_key=? AND r.special=1 ORDER BY r.id", (MAYOR,)).fetchone()
    assert race is not None and int(race["election_day"]) > day + wait
    d = day + wait
    while offices.holder(c, MAYOR) is None and d < day + 900:
        d += 7
        offices.process_vacancies(c, d)
        races.advance(c, d)
    assert offices.holder(c, MAYOR) is not None
    assert _vac(c, MAYOR)["filled_how"] == "elected"


def test_held_in_custody_is_not_vacant_until_rule_says():
    from engine import civic_votes, offices
    w = _open_world()
    c = w.conn
    ms = [a for _, _, a in offices.members(c, COUNCIL)]
    m = ms[0]
    c.execute("INSERT INTO custody(actor_id,kind,charge,since_day) VALUES (?,?,?,?)", (m, "held", "test", 10))
    offices.process_vacancies(c, 200)
    assert m in offices.holders(c, WARD1) + offices.holders(c, "office:council:ward-2") + [a for _, _, a in offices.members(c, COUNCIL)]  # still holds the seat
    iid = civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": ms[1], "title": "t"}, vote_day=210, day=205)
    v, why = civic_votes.member_vote(c, iid, m, 210)
    assert v == "absent" and why["absent"] == "in_custody"
    # a package that sets the days vacates the seat once he has been held that long
    real = offices.spec
    offices.spec = lambda conn, key: {**real(conn, key), "custody_vacates_after_days": 90} if offices.holder(conn, key) == m else real(conn, key)
    try:
        offices.process_vacancies(c, 99)
        assert m in [a for _, _, a in offices.members(c, COUNCIL)]
        offices.process_vacancies(c, 101)
    finally:
        offices.spec = real
    assert m not in [a for _, _, a in offices.members(c, COUNCIL)]


def test_protagonist_vacancy_rules_alike():
    from engine import offices, player
    w = _open_world()
    c = w.conn
    player.set_player(c, w.capo)
    offices.seat_holder(c, "office:council:ward-3", w.capo, how="elected", day=1)
    _die(c, "office:council:ward-3", 50)  # the engine kills the holder as it would any; the rule is the same
    assert _vac(c, "office:council:ward-3")["status"] == "pending"
    for s in range(1, 30):
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (s,))
        offices.process_vacancies(c, 80 + s)
        from engine import civic_votes
        civic_votes.advance(c, 80 + s)
        if offices.holder(c, "office:council:ward-3") is not None:
            break
    h = offices.holder(c, "office:council:ward-3")
    assert h is not None and h != w.capo  # the engine never puts the player in by itself


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
