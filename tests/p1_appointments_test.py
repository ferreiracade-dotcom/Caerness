"""P1 Task 7: appointments through sponsor chains.

Run: PYTHONPATH=. python tests/p1_appointments_test.py"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

MAYOR = "office:city-hall:mayor"
COMM = "office:sjpd:police-commissioner"
PROS = "office:county-prosecutor:killbuck-county-prosecutor"
SENATE = "office:state:senate-killbuck"


def _org(c, key):
    return int(c.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def _vacate(c, key, day=5):
    from engine import offices
    for t in offices._open_terms(c, key):
        offices.end_term(c, int(t["id"]), "resigned", day)


def _trial(c, seed, fn):
    """Run fn under a seed and roll every change back, so one opening serves many trials."""
    c.execute("SAVEPOINT trial")
    try:
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (seed,))
        return fn()
    finally:
        c.execute("ROLLBACK TO trial")
        c.execute("RELEASE trial")


def test_commissioner_appointed_by_mayor():
    from engine import appointments, civic_seams, offices, orgs
    w = _open_world()
    c = w.conn
    club = _org(c, "reform_clubs")
    new_mayor = orgs.head_of(c, club)
    assert offices.holder(c, COMM) is not None

    def trial():
        offices.seat_holder(c, MAYOR, new_mayor, how="elected", day=30)
        before = offices.holder(c, COMM)
        n = appointments.review_on_change(c, MAYOR, 31)
        after = offices.holder(c, COMM)
        if n:
            assert after is not None and after != before
            assert appointments.sponsor_of(c, after, COMM) is not None
            assert [e for e in civic_seams.ledger_open(c, after, kind="favour") if e["debtor_ref"] == f"person:{after}"]
        return n
    got = [_trial(c, s, trial) for s in range(1, 25)]
    assert any(got) and not all(got), got  # sometimes replaced, sometimes kept


def test_courtesy_blocks():
    from engine import appointments, offices, orgs
    w = _open_world()
    c = w.conn
    club = _org(c, "reform_clubs")
    _vacate(c, PROS)
    offices.seat_holder(c, SENATE, orgs.head_of(c, club), how="elected", day=1)  # a senator of the other side
    won = [_trial(c, s, lambda: appointments.fill(c, PROS, 40)) for s in range(1, 8)]
    assert not any(won), won  # every man the sponsor can put forward is hostile to him
    c.execute("SAVEPOINT p")
    appointments.fill(c, PROS, 41)
    cause = c.execute("SELECT cause FROM office_vacancies WHERE office_id=(SELECT id FROM offices WHERE office_key=?) AND status='pending' ORDER BY id DESC LIMIT 1", (PROS,)).fetchone()
    assert cause and "courtesy" in cause[0], tuple(cause)
    c.execute("ROLLBACK TO p")
    c.execute("RELEASE p")
    # a senator of the sponsor's own side does not block
    offices.seat_holder(c, SENATE, orgs.head_of(c, _org(c, "county_party")), how="elected", day=2)
    won = [_trial(c, s, lambda: appointments.fill(c, PROS, 40)) for s in range(1, 8)]
    assert any(won), won


def test_sponsor_is_whoever_holds_the_seat():
    from engine import appointments, civic_field, offices, orgs
    w = _open_world()
    c = w.conn
    machine, club = _org(c, "county_party"), _org(c, "reform_clubs")
    assert appointments.sponsor_actor(c, PROS) == orgs.head_of(c, machine)
    sid = int(c.execute("SELECT id FROM field_holdings WHERE stake_kind='sponsor' AND stake_ref=? AND ended_day IS NULL", (PROS,)).fetchone()[0])
    civic_field.transfer(c, sid, "org", club, day=20, cause_kind="defeat")
    _vacate(c, PROS, 21)
    offices.seat_holder(c, SENATE, orgs.head_of(c, club), how="elected", day=1)
    appointee = None
    for s in range(1, 20):
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (s,))
        appointee = appointments.fill(c, PROS, 40)
        if appointee is not None:
            break
    assert appointee is not None
    assert appointments.sponsor_of(c, appointee, PROS) == orgs.head_of(c, club)
    assert c.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (appointee, club)).fetchone()


def test_protagonist_can_sponsor_or_be_appointed():
    from engine import appointments, civic_field, civic_patronage, offices, player
    w = _open_world()
    c = w.conn
    player.set_player(c, w.capo)
    # appointed: the same appointer and consent checks as any nominee, with a veto's reason
    seated = None
    for s in range(1, 30):
        def go():
            try:
                appointments.put_forward(c, w.capo, "office:licensing:board", 50)
                return offices.holder(c, "office:licensing:board", 1) == w.capo or w.capo in offices.holders(c, "office:licensing:board")
            except ValueError as e:
                assert str(e) in ("appointer", "courtesy", "min_age", "no_vacant_seat", "residence", "conviction_bar", "not_living"), e
                return str(e)
        res = _trial(c, s, go)
        if res is True:
            seated = s
            break
        if res == "no_vacant_seat":
            for t in offices._open_terms(c, "office:licensing:board")[:1]:
                offices.end_term(c, int(t["id"]), "resigned", 49)
    assert seated is not None
    # sponsoring: he holds a sponsor stake and puts forward a man who owes him
    sid = int(c.execute("SELECT id FROM field_holdings WHERE stake_kind='sponsor' AND stake_ref=? AND ended_day IS NULL", (PROS,)).fetchone()[0])
    civic_field.transfer(c, sid, "actor", w.capo, day=20, cause_kind="gift")
    civic_patronage.favour(c, w.capo, w.soldier, "a job", day=21)
    _vacate(c, PROS, 22)
    got = None
    for s in range(1, 30):
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (s,))
        got = appointments.fill(c, PROS, 40)
        if got is not None:
            break
    assert got == w.soldier and appointments.sponsor_of(c, got, PROS) == w.capo


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
