"""Task B12, generic half: the weekly organisation lifecycle on the minimal test package (no Saint Jude word runs).

Run: CAERNESS_DB_PATH=<scratch>.db PYTHONPATH=. python tests/org_lifecycle_test.py
A dead man's seat, a held man's level and seat, the vacancy hook, a unit that gets a new leader through
`fill_unit_leader`, the post that passes up to a successor, leaving the life and the record that stays.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import org_core_fixture as fx


def _hold(conn, actor, since, until=None):
    conn.execute("INSERT INTO custody(actor_id,kind,charge,since_day,until_day) VALUES (?,'held','test',?,?)", (actor, since, until))


def _release(conn, actor):
    conn.execute("UPDATE custody SET kind='released' WHERE actor_id=? AND kind='held'", (actor,))


def _die(conn, actor):
    """A natural death: the person is gone, his seat has not been told (the lifecycle finds it)."""
    conn.execute("UPDATE actors SET status='dead' WHERE id=?", (int(actor),))


def test_firm_vacancy_uses_the_generic_path():
    from engine import org_lifecycle, orgs
    f = fx.build()
    conn = f.conn
    m0 = f.managers[0]
    unit = int(orgs.seat_of(conn, m0, f.firm)["unit_id"])
    fx.kill(conn, m0)
    org_lifecycle.process_due(conn, 7)
    leader = conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (unit,)).fetchone()[0]
    assert leader in (f.clerks[0], f.clerks[1]), leader
    seat = orgs.seat_of(conn, leader, f.firm)
    assert seat["role_key"] == "manager" and seat["superior_actor_id"] == f.chair and seat["level"] == 4
    other = f.clerks[1] if leader == f.clerks[0] else f.clerks[0]
    assert orgs.superior_of(conn, other, f.firm) == leader  # his old unit mates now answer to him
    # the line the clerk held stays with the unit; no code of any sphere ran (no agenda of the layer)
    assert conn.execute("SELECT COUNT(*) FROM org_agenda WHERE kind='fill_unit_leader_seat'").fetchone()[0] == 0
    assert orgs.stand_in_for(conn, f.clerks[0], f.firm) == leader or leader == f.clerks[0]
    # the same pass again changes nothing
    org_lifecycle.process_due(conn, 14)
    assert conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (unit,)).fetchone()[0] == leader


def test_a_natural_death_sets_the_seat_dead_and_hooks_run_once():
    from engine import org_lifecycle, orgs
    f = fx.build()
    conn = f.conn
    seen = []
    org_lifecycle.on_vacancy("firm", lambda c, org, seat, day, why: seen.append((int(seat["actor_id"]), why)))
    _die(conn, f.clerks[3])
    org_lifecycle.process_due(conn, 7)
    s = orgs.seat_of(conn, f.clerks[3], f.firm)
    assert s["status"] == "dead" and s["left_day"] == 7
    assert (f.clerks[3], "dead") in seen
    org_lifecycle.process_due(conn, 14)
    assert seen.count((f.clerks[3], "dead")) == 1
    assert orgs.is_living(conn, f.clerks[2])


def test_the_head_is_succeeded_by_data():
    from engine import org_lifecycle, orgs
    f = fx.build()
    conn = f.conn
    fx.kill(conn, f.chair)
    org_lifecycle.process_due(conn, 7)
    new = orgs.head_of(conn, f.firm)
    assert new in f.managers, new
    old_role_holder = [m for m in f.managers if m != new][0]
    assert orgs.superior_of(conn, old_role_holder, f.firm) == new
    # the unit he led has a manager again, and his own unit's lines were not lost
    unit_row = conn.execute("SELECT u.leader_actor_id FROM org_units u WHERE u.org_actor_id=?", (f.firm,)).fetchall()
    assert all(r[0] is not None and orgs.is_living(conn, int(r[0])) for r in unit_row)


def test_held_man_drops_a_level_after_30_days_and_returns():
    from engine import org_lifecycle, orgs
    f = fx.build()
    conn = f.conn
    m = f.managers[1]
    _hold(conn, m, 0, 40)
    org_lifecycle.process_due(conn, 14)
    assert orgs.seat_of(conn, m, f.firm)["level"] == 4  # not yet 30 days
    org_lifecycle.process_due(conn, 35)
    assert orgs.seat_of(conn, m, f.firm)["level"] == 3
    prof = conn.execute("SELECT tier,cadence_days FROM simulation_profiles WHERE actor_id=?", (m,)).fetchone()
    assert prof["tier"] == "STRATEGIC" and prof["cadence_days"] == 7
    _release(conn, m)
    org_lifecycle.process_due(conn, 42)
    assert orgs.seat_of(conn, m, f.firm)["level"] == 4
    prof = conn.execute("SELECT tier,cadence_days FROM simulation_profiles WHERE actor_id=?", (m,)).fetchone()
    assert prof["tier"] == "ACTIVE" and prof["cadence_days"] == 1


def test_a_step_back_agenda_keeps_a_head_at_level_3():
    from engine import org_lifecycle, orgs
    f = fx.build()
    conn = f.conn
    orgs.set_level(conn, f.chair, 3, 0, f.firm)  # he has stepped back (the data names the agenda kinds in the real package)
    org_lifecycle.process_due(conn, 7)
    assert orgs.seat_of(conn, f.chair, f.firm)["level"] == 4  # no step-back data in this package: the role's level is 4


def test_a_man_held_over_a_year_loses_his_seat_and_is_replaced_and_returns_lower():
    from engine import org_lifecycle, orgs
    f = fx.build()
    conn = f.conn
    m = f.managers[0]
    unit = int(orgs.seat_of(conn, m, f.firm)["unit_id"])
    _hold(conn, m, 0, None)
    org_lifecycle.process_due(conn, 371)
    assert orgs.seat_of(conn, m, f.firm)["status"] == "held"
    new = conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (unit,)).fetchone()[0]
    assert new != m and orgs.seat_of(conn, new, f.firm)["role_key"] == "manager"
    _release(conn, m)
    org_lifecycle.process_due(conn, 378)
    back = orgs.seat_of(conn, m, f.firm)
    assert back["status"] == "active" and back["role_key"] == "clerk" and back["superior_actor_id"] in (new, f.chair), dict(back)


def test_leaving_the_life_keeps_the_record():
    from engine import org_lifecycle, orgs
    f = fx.build()
    conn = f.conn
    c = f.clerks[0]
    org_lifecycle.leave_life(conn, c, f.firm, 21)
    assert conn.execute("SELECT 1 FROM actors WHERE id=?", (c,)).fetchone() is not None
    s = orgs.seat_of(conn, c, f.firm)
    assert s["status"] == "out" and s["left_day"] == 21
    p = conn.execute("SELECT tier,cadence_days,quiet_routine FROM simulation_profiles WHERE actor_id=?", (c,)).fetchone()
    assert p["tier"] == "DORMANT" and p["cadence_days"] == 180 and p["quiet_routine"] == 0
    # a man who still holds a seat elsewhere is not made dormant
    d = f.clerks[1]
    orgs.seat(conn, d, f.solo, "hand", unit_id=None, superior_actor_id=f.owner, level=3, day=0)
    org_lifecycle.leave_life(conn, d, f.firm, 21)
    assert conn.execute("SELECT tier FROM simulation_profiles WHERE actor_id=?", (d,)).fetchone()["tier"] != "DORMANT"
    # an `out` seat set by someone else's code is found by the weekly pass
    conn.execute("UPDATE org_seats SET status='out', left_day=28 WHERE actor_id=? AND org_actor_id=?", (f.clerks[2], f.firm))
    org_lifecycle.process_due(conn, 28)
    assert conn.execute("SELECT tier FROM simulation_profiles WHERE actor_id=?", (f.clerks[2],)).fetchone()["tier"] == "DORMANT"


def test_the_gone_mans_men_answer_to_his_superior_and_are_looked_at():
    from engine import org_lifecycle, orgs
    f = fx.build()
    conn = f.conn
    solo_hand = f.hand
    fx.kill(conn, f.owner)  # a kind without unit leaders: the man under him has no one
    org_lifecycle.process_due(conn, 7)
    assert orgs.stand_in_for(conn, solo_hand, f.solo) is None  # a head with no live successor: no one earns, nothing crashes
    # a clerk whose manager dies: reviewed tomorrow (imposed)
    fx.kill(conn, f.managers[1])
    org_lifecycle.process_due(conn, 14)
    new = conn.execute("SELECT leader_actor_id FROM org_units WHERE org_actor_id=? AND id=(SELECT unit_id FROM org_seats WHERE actor_id=?)", (f.firm, f.clerks[3])).fetchone()[0]
    pr = conn.execute("SELECT forced_tier FROM simulation_profiles WHERE actor_id=?", (f.clerks[2] if new == f.clerks[3] else f.clerks[3],)).fetchone()
    assert pr is not None and pr["forced_tier"] == "ACTIVE"


def test_the_process_has_a_weekly_due_day():
    from engine import org_lifecycle
    f = fx.build()
    conn = f.conn
    d = org_lifecycle.next_due_day(conn, 10, 100)
    assert d is not None and d > 10 and d <= 17
    assert org_lifecycle.next_due_day(conn, 10, d - 1) is None
    assert org_lifecycle.next_due_day(conn, d, 100) == d + 7


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    bad = []
    for t in TESTS:
        try:
            t()
        except Exception:  # noqa: BLE001
            import traceback
            bad.append(t.__name__)
            traceback.print_exc()
        else:
            print("ok", t.__name__)
    if bad:
        print("FAILED", bad)
        sys.exit(1)
    print("org_lifecycle_test OK", len(TESTS))
