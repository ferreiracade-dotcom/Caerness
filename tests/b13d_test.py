"""Task B13d: what a man weighs before he takes out his leader or hunts a killer (counter-terms), one-pass presence seeding, a table asked once.

Run: CAERNESS_DB_PATH=<scratch db> PYTHONPATH=. python tests/b13d_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_FAILURES: set[str] = set()


def _world():
    from tests.outfit_choice_fixture import open_world
    return open_world()


def test_the_counter_terms_read_the_leaders_protection():
    from engine import outfit_motives as om, org_tension as ot
    w = _world()
    g, l = ot.protection(w.conn, w.capo)
    assert g > 0.0, "the fixture's capo has men under him"
    assert om.leader_guarded(w.conn, w.soldier, 200) == g
    assert om.leader_loved(w.conn, w.soldier, 200) == l
    assert 0.0 <= om.head_backs_leader(w.conn, w.soldier, 200) <= 1.0


def test_a_guarded_leader_takes_a_share_off_the_pressure_to_remove_him_and_never_all_of_it():
    from engine import org_motives
    from engine import outfit_motives as om
    w = _world()
    c = w.conn
    saved = dict(org_motives._READERS)
    try:
        for (choice, name) in list(org_motives._READERS):
            if choice == om.REMOVE and name not in ("leader_guarded", "leader_loved", "head_backs_leader"):
                org_motives._READERS[(choice, name)] = lambda *a: 1.0
        found = org_motives.spec_for(c, w.soldier, om.REMOVE)
        assert found is not None
        rates = found[0]["rates"]
        against = rates.get("against")
        assert against, "the package names counter-terms for removing a leader"
        with_terms, _ = org_motives.pressure(c, w.soldier, 200, om.REMOVE)
        rates["against"] = []
        try:
            without, _ = org_motives.pressure(c, w.soldier, 200, om.REMOVE)
        finally:
            rates["against"] = against
    finally:
        org_motives._READERS.clear()
        org_motives._READERS.update(saved)
    assert without > 0.0
    assert 0.0 < with_terms < without, (with_terms, without)


def test_presence_seeding_is_stable_and_writes_nothing_the_second_time():
    from engine.presence import seed_presence_from_existing_state
    w = _world()
    c = w.conn
    seed_presence_from_existing_state(c)
    seed_presence_from_existing_state(c)  # a profile whose habit was just added carries that habit's values until the next pass writes the derived ones back
    before = (c.execute("SELECT COUNT(*) FROM actor_presence_habits").fetchone()[0], tuple(tuple(r) for r in c.execute("SELECT * FROM actor_presence_profiles ORDER BY actor_id")))
    n0 = c.total_changes
    assert seed_presence_from_existing_state(c) == 0
    after = (c.execute("SELECT COUNT(*) FROM actor_presence_habits").fetchone()[0], tuple(tuple(r) for r in c.execute("SELECT * FROM actor_presence_profiles ORDER BY actor_id")))
    assert before == after
    assert c.total_changes - n0 < 20, c.total_changes - n0


def test_the_mortality_audit_table_is_asked_once():
    from engine import health
    w = _world()
    c = w.conn
    assert health._has_mortality_audit(c) is True


def run():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"FAIL {name}: {exc!r}")
            import traceback
            traceback.print_exc()
    print(f"{len(tests) - len(failed)}/{len(tests)} passed")
    return 1 if [n for n in failed if n not in EXPECTED_FAILURES] else 0


if __name__ == "__main__":
    sys.exit(run())
