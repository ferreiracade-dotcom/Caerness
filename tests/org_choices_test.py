"""Generic organisation choices (task B10): a choice registered for an undeclared kind is never offered; a toy kind round-trips.

Run: PYTHONPATH=. python tests/org_choices_test.py   (builds its own scratch DB on the tiny non-Saint-Jude package)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import org_core_fixture as fx


def _forced(value=0.0):
    from engine import org_motives
    old = org_motives._roll
    org_motives._roll = lambda conn, actor_id, day, stream: value
    return old


def test_undeclared_kind_offers_nothing():
    """A choice registered for "family" is never offered to a firm clerk (the package does not declare that kind)."""
    from engine import org_choices, org_motives
    f = fx.build()
    conn = f.conn
    called = []
    org_choices.register_choice("family", "promote", lambda c, a, o, d: called.append(a) or [{"utility": 9.0, "payload": {}}],
                                lambda c, a, k, p, d: {"summary": "no"})
    org_motives.register_motive("promote", "restless", lambda c, a, d: 1.0)
    old = _forced()
    try:
        assert org_choices.org_provider(conn, f.clerks[0], "STRATEGIC", 10, {}) == []
        assert not called
        assert not org_choices._reason(conn, f.clerks[0], 10)
    finally:
        org_motives._roll = old
        org_choices.clear_choices()


def test_toy_kind_choice_round_trip():
    """Register a "firm" choice with one motive; a forced roll makes an org_action decision that executes it."""
    from engine import org_choices, org_motives
    from engine.decisions import decide_actor
    f = fx.build()
    conn = f.conn
    clerk = f.clerks[0]

    def candidates(c, actor, org, day):
        return [{"kind": "promote", "utility": 20.0, "rationale": "Asks for the next seat.", "payload": {"org": org}}]

    def execute(c, actor, kind, payload, day):
        c.execute("UPDATE org_seats SET standing=standing+1 WHERE actor_id=? AND org_actor_id=?", (actor, payload["org"]))
        return {"summary": "He asked."}

    org_choices.register_choice("firm", "promote", candidates, execute)
    org_motives.register_motive("promote", "restless", lambda c, a, d: 1.0)
    p, parts = org_motives.pressure(conn, clerk, 10, "promote")
    assert parts == {"restless": 1.0} and abs(p - 0.8) < 1e-9, (p, parts)
    assert abs(org_motives.weekly_chance(conn, clerk, 10, "promote") - 0.8) < 1e-9
    old = _forced(0.99)
    try:
        assert not org_choices._reason(conn, clerk, 10) and org_choices.org_provider(conn, clerk, "STRATEGIC", 10, {}) == []
        org_motives._roll = lambda c, a, d, s: 0.0
        assert org_choices._reason(conn, clerk, 10)
        did = decide_actor(conn, clerk, "STRATEGIC", 10)
    finally:
        org_motives._roll = old
        org_choices.clear_choices()
    row = conn.execute("SELECT action_type,outcome_summary FROM decisions WHERE id=?", (did,)).fetchone()
    assert row["action_type"] == "org_action" and row["outcome_summary"] == "He asked.", dict(row)
    assert conn.execute("SELECT standing FROM org_seats WHERE actor_id=? AND org_actor_id=?", (clerk, f.firm)).fetchone()[0] == 1


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    bad = []
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            bad.append(t.__name__)
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, repr(e)[:300])
        else:
            print("ok", t.__name__)
    print(f"{len(TESTS) - len(bad)} passed" + (f", {len(bad)} FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)
