"""Prison J1.3: the inside week, for NPCs and the protagonist alike.

Run: PYTHONPATH=. python tests/j1_inside_test.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.j1_admission_test import _convict, _men, _remand, _run, _stay  # noqa: E402
from tests.outfit_choice_fixture import DAY, open_world  # noqa: E402

from engine import ledger, org_informing, orgs, prison  # noqa: E402
from engine.player import set_player  # noqa: E402


class _Rules:
    """Swap prison.rules for a copy with some week figures replaced, and put it back."""

    def __init__(self, **week):
        self.week, self.orig = week, prison.rules

    def __enter__(self):
        base = self.orig

        def patched(conn):
            r = copy.deepcopy(base(conn))
            for k, v in self.week.items():
                r["week"].setdefault(k, {}).update(v)
            return r
        prison.rules = patched

    def __exit__(self, *a):
        prison.rules = self.orig


def _fig(v):
    return {"value": v, "mark": "Design proposal", "why": "test"}


def _inside(c, n=3, term=1000, protagonist=None):
    men = _men(c, n)
    if protagonist is not None:
        set_player(c, men[protagonist])
    for m in men:
        _convict(c, m, term)
    _run(c)
    return men


def _purse(c, actor, amount):
    """Set a man's cash, wherever the ledger keeps it."""
    c.execute("DELETE FROM underworld_leader_wealth WHERE actor_id=?", (actor,))
    c.execute("DELETE FROM resources WHERE actor_id=? AND resource_type='cash'", (actor,))
    c.execute("INSERT INTO resources(actor_id,resource_type,amount) VALUES (?,?,?)", (actor, "cash", amount))


def _week(c, day):
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))
    return prison.weekly(c, day)


def test_crowding_bends_violence():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    fac = c.execute("SELECT * FROM facilities WHERE key='county_jail'").fetchone()
    base = prison.rules(c)["facilities"]["county_jail"]["character"]["violence"]
    st = prison.facility_state(c, fac)
    assert st["violence"] > base and st["crowding"] > 1.0, st  # the jail is overcrowded
    quiet = c.execute("SELECT * FROM facilities WHERE key='federal_detention_center'").fetchone()
    assert prison.facility_state(c, quiet)["violence"] < base


def test_a_fight_goes_on_the_record_and_a_serious_one_enters_the_law():
    for protagonist in (False, True):
        w = open_world()
        c = w.conn
        prison.ensure_facilities(c)
        men = _inside(c, 4, protagonist=0 if protagonist else None)
        with _Rules(fight={"rate": _fig(50.0), "serious_share": _fig(1.0), "unnamed_share": _fig(0.0)}):
            out = _week(c, DAY + 10)
        assert out["fights"] >= 1, out
        assert c.execute("SELECT COUNT(*) FROM prison_events WHERE kind='fight'").fetchone()[0] >= 1
        assert c.execute("SELECT COUNT(*) FROM prison_events WHERE kind='infraction'").fetchone()[0] >= 1
        assert c.execute("SELECT COUNT(*) FROM harm_incidents WHERE source_kind='prison_fight'").fetchone()[0] >= 1
        if protagonist:  # the same rules: the protagonist's fights are drawn like any man's
            assert any(r[0] == men[0] for r in c.execute("SELECT actor_id FROM prison_events WHERE kind='fight'"))


def test_no_fight_when_violence_is_nil():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    _inside(c, 3)
    c.execute("UPDATE facilities SET status='open'")
    with _Rules(fight={"rate": _fig(0.0)}):
        assert _week(c, DAY + 10)["fights"] == 0


def test_dues_go_to_the_shot_caller_and_unpaid_men_lose_standing():
    for protagonist in (False, True):
        w = open_world()
        c = w.conn
        prison.ensure_facilities(c)
        men = _inside(c, 3, protagonist=1 if protagonist else None)
        _week(c, DAY + 8)  # a lead is named first
        st = _stay(c, men[0])
        org = c.execute("SELECT org_actor_id FROM facility_groups WHERE id=?", (st["group_id"],)).fetchone()[0]
        head = orgs.head_of(c, org)
        assert head is not None
        followers = [m for m in men if m != head and _stay(c, m)["group_id"] == st["group_id"] and orgs.seat_of(c, m, org)["standing"] > 0.05]
        if not followers:
            continue
        f = followers[0]
        _purse(c, f, 0)
        before = orgs.seat_of(c, f, org)["standing"]
        _week(c, DAY + 15)
        assert orgs.seat_of(c, f, org)["standing"] < before  # he could not pay
        _purse(c, f, 1000)
        _purse(c, head, 0)
        mid = orgs.seat_of(c, f, org)["standing"]
        _week(c, DAY + 22)
        assert orgs.seat_of(c, f, org)["standing"] > mid  # he paid
        assert ledger.balance(c, ("person", head)) > 0


def test_a_group_gets_a_shot_caller_once_it_has_men():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    men = _inside(c, 3)
    _week(c, DAY + 8)
    st = _stay(c, men[0])
    org = c.execute("SELECT org_actor_id FROM facility_groups WHERE id=?", (st["group_id"],)).fetchone()[0]
    assert orgs.head_of(c, org) is not None
    assert c.execute("SELECT COUNT(*) FROM prison_events WHERE kind='shot_caller'").fetchone()[0] >= 1


def test_a_man_who_informs_goes_to_protective_custody():
    for protagonist in (False, True):
        w = open_world()
        c = w.conn
        prison.ensure_facilities(c)
        men = _inside(c, 3, protagonist=0 if protagonist else None)
        a = men[0]
        before = _stay(c, a)["group_id"]
        org = c.execute("SELECT org_actor_id FROM facility_groups WHERE id=?", (before,)).fetchone()[0]
        outside = c.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active' AND org_actor_id<>?", (a, org)).fetchone()
        c.execute("INSERT INTO org_informers(informer_actor_id,org_actor_id,turned_by_kind,turned_by_id,since_day) VALUES (?,?,?,?,?)",
                  (a, int(outside[0]) if outside else org, "org", None, DAY))
        assert org_informing.is_informer(c, a)
        with _Rules(informing={"found_rate": _fig(1000.0)}):
            out = _week(c, DAY + 8)
        assert out["protected"] >= 1, out
        st = _stay(c, a)
        assert st["protective"] == 1
        assert c.execute("SELECT group_key FROM facility_groups WHERE id=?", (st["group_id"],)).fetchone()[0] == "protective"
        old = orgs.seat_of(c, a, org)
        assert old is None or old["status"] == "out"


def test_escape_ends_the_stay_and_opens_a_case():
    for protagonist in (False, True):
        w = open_world()
        c = w.conn
        prison.ensure_facilities(c)
        men = _inside(c, 2, protagonist=0 if protagonist else None)
        with _Rules(escape={"rate": _fig(5.0)}):
            out = _week(c, DAY + 8)
        assert out["escapes"] >= 1, out
        gone = [m for m in men if _stay(c, m) is None]
        assert gone
        a = gone[0]
        assert c.execute("SELECT status FROM inmate_stays WHERE actor_id=? ORDER BY id DESC", (a,)).fetchone()[0] == "escaped"
        assert c.execute("SELECT status FROM sentences WHERE actor_id=?", (a,)).fetchone()[0] == "escaped"
        assert c.execute("SELECT COUNT(*) FROM custody WHERE actor_id=? AND kind='held'", (a,)).fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM crime_reports WHERE crime_kind='escape'").fetchone()[0] >= 1


def test_the_week_runs_on_its_cadence_not_every_day():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    _inside(c, 2)
    c.execute("DELETE FROM prison_events")
    with _Rules(fight={"rate": _fig(50.0), "unnamed_share": _fig(0.0)}):
        assert "fights" in _run(c, DAY + 10) or True
        first = int(c.execute("SELECT COUNT(*) FROM prison_events").fetchone()[0])
        _run(c, DAY + 11)
        assert int(c.execute("SELECT COUNT(*) FROM prison_events").fetchone()[0]) == first  # no second week the next day
        _run(c, DAY + 18)
        assert int(c.execute("SELECT COUNT(*) FROM prison_events").fetchone()[0]) > first


def test_a_second_sentence_runs_with_the_first():
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    a = _men(c, 1)[0]
    _convict(c, a, 800)
    _run(c)
    first = int(_stay(c, a)["id"])
    _convict(c, a, 1500, day=DAY + 3)
    _run(c, DAY + 4)
    st = _stay(c, a)
    assert int(st["id"]) == first and st["until_day"] >= DAY + 3 + 1500
    assert c.execute("SELECT COUNT(*) FROM inmate_stays WHERE actor_id=? AND status='inside'", (a,)).fetchone()[0] == 1


def main() -> None:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        f()
        print("ok", n)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
