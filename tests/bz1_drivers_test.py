"""BZ1.3: the shared drivers, each with its value and its source.

Run: PYTHONPATH=. python tests/bz1_drivers_test.py"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

KEYS = ("calendar", "shock", "demand", "form", "condition", "capacity", "rivals", "roll")


def _bar(conn, name, loc, owner=None):
    from engine import business, civilian
    eid = civilian.create_enterprise(conn, name, "service", owner_actor_id=owner, location_id=loc, capital=1000, cash=1000)
    business.configure_enterprise_business(conn, eid, "bar")
    return eid


def _day_of(conn, iso):
    from datetime import date
    from engine.world_package import package_for
    from engine import world_calendar
    return (date.fromisoformat(iso) - world_calendar._start(package_for(conn))).days


def test_every_factor_has_a_source():
    from engine import business, business_drivers as bd
    w = _open_world()
    c = w.conn
    eid = _bar(c, "Driver Bar", w.ground)
    weights = business.archetypes(c)["bar"]["weights"]
    f = bd.reading(c, "enterprise", eid, _day_of(c, "1975-03-01"), sector="hospitality", location_id=w.ground,
                   demand_weights=weights)
    assert tuple(f) == KEYS
    assert all(x.source for x in f.values())
    prod = 1.0
    for x in f.values():
        prod *= x.value
    assert abs(bd.total(f) - prod) < 1e-12


def test_shock_dates_bite():
    from engine import business_drivers as bd
    w = _open_world()
    c = w.conn
    a = bd.reading(c, "venture", 1, _day_of(c, "1975-03-01"), sector="construction", location_id=None)
    b = bd.reading(c, "venture", 1, _day_of(c, "1977-03-01"), sector="construction", location_id=None)
    assert abs(a["shock"].value - 0.8) < 1e-9 and b["shock"].value == 1.0
    assert "recession" in a["shock"].source
    assert abs(a["shock"].value / b["shock"].value - 0.8) < 1e-9


def test_rivals_named():
    from engine import business_drivers as bd
    w = _open_world()
    c = w.conn
    me = _bar(c, "Mine Bar", w.ground)
    alone = bd.reading(c, "enterprise", me, 10, sector="hospitality", location_id=w.ground)["rivals"]
    base = int(c.execute("SELECT COUNT(*) FROM civilian_enterprises e JOIN enterprise_business_profiles p ON p.enterprise_id=e.id "
                         "JOIN business_archetypes a ON a.id=p.archetype_id WHERE e.location_id=? AND a.sector='hospitality' AND e.id<>?",
                         (w.ground, me)).fetchone()[0])
    _bar(c, "Rival Alpha", w.ground)
    _bar(c, "Rival Beta", w.ground)
    r = bd.reading(c, "enterprise", me, 10, sector="hospitality", location_id=w.ground)["rivals"]
    assert abs(r.value - 1.0 / (1.0 + 0.15 * (base + 2))) < 1e-9, (r, base)
    assert "Rival Alpha" in r.source or base >= 1  # named up to three
    only = bd.reading(c, "enterprise", me, 10, sector="logistics", location_id=w.ground)["rivals"]
    assert only.value == 1.0 / (1.0 + 0.15 * int(c.execute(
        "SELECT COUNT(*) FROM civilian_enterprises e JOIN enterprise_business_profiles p ON p.enterprise_id=e.id "
        "JOIN business_archetypes a ON a.id=p.archetype_id WHERE e.location_id=? AND a.sector='logistics'", (w.ground,)).fetchone()[0]))
    del alone


def test_record_keeps_latest_only():
    from engine import business_drivers as bd
    w = _open_world()
    c = w.conn
    for day in (10, 40):
        bd.record(c, "enterprise", 7, day, bd.reading(c, "enterprise", 7, day, sector="retail", location_id=None))
    rows = c.execute("SELECT day FROM driver_readings WHERE subject_kind='enterprise' AND subject_id=7").fetchall()
    assert [r[0] for r in rows] == [40]
    assert len(bd.why(c, "enterprise", 7)) == 8 and bd.why(c, "enterprise", 99) == []


def test_roll_is_seeded():
    from engine import business_drivers as bd
    w1 = _open_world()
    r1 = bd.reading(w1.conn, "venture", 3, 55, sector="retail", location_id=None)["roll"].value
    w2 = _open_world()
    r2 = bd.reading(w2.conn, "venture", 3, 55, sector="retail", location_id=None)["roll"].value
    r3 = bd.reading(w2.conn, "venture", 3, 56, sector="retail", location_id=None)["roll"].value
    assert r1 == r2 and 0.9 <= r1 <= 1.1 and r3 != r1


tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
tests.sort(key=lambda f: f.__code__.co_firstlineno)


def _run_all():
    ok = 0
    for t in tests:
        try:
            t()
            ok += 1
        except Exception:
            print("FAIL", t.__name__)
            traceback.print_exc()
    print(f"{ok}/{len(tests)} passed")
    return ok == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
