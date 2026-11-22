"""Task I-1/7: play-check of the intake core through the connector only.

Three lasting things (a legal floor thing, an illegal holding-shaped thing, a custom) and a free operation that settles into a
fourth; three 30-day advances. Structural truths are asserted; what happened (happenings, growth, heat) is printed, never asserted.

Run: PYTHONPATH=. python tests/intake_play_test.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world


def run():
    from connector import store
    from connector.acting import act
    from connector.authoring import author
    from connector.timeflow import advance
    from connector.views import lookup
    from engine import ledger, org_heat
    from engine.player import set_player

    w = open_world()
    c = w.conn
    store.ensure_connector_schema(c)
    set_player(c, w.capo)
    ledger.receive(c, ("person", w.capo), 2000, purpose="play-check funding")  # the fixture's purses start empty
    c.commit()

    tally = []  # (kind, purpose, amount, balance delta): the ledger moved exactly what each held-thing call said
    real_receive, real_spend = ledger.receive, ledger.spend

    def receive(conn, dst, amount, *, purpose):
        before = ledger.balance(conn, dst)
        got = real_receive(conn, dst, amount, purpose=purpose)
        if ":" in purpose and purpose.endswith("takings"):
            tally.append(("in", purpose, got, ledger.balance(conn, dst) - before))
        return got

    def spend(conn, src, amount, *, purpose, allow_partial=True):
        before = ledger.balance(conn, src)
        got = real_spend(conn, src, amount, purpose=purpose, allow_partial=allow_partial)
        if purpose.endswith(": upkeep"):
            tally.append(("out", purpose, got, before - ledger.balance(conn, src)))
        return got

    ledger.receive, ledger.spend = receive, spend
    try:
        a = author(c, "p1", "a pigeon club", {"what": "the Ferry Street pigeon club", "people": [w.capo, w.soldier],
                                              "money": {"start": 100, "income": "80 a week", "upkeep": "30 a week"}, "legality": "legal"})
        b = author(c, "p2", "a warehouse", {"what": "the warehouse on Ferry Street, for hijacked loads", "legality": "illegal",
                                            "money": {"income": "500 a week"}, "agenda": "keep the loads moving"})
        k = author(c, "p3", "a custom", {"what": "the Feast of Saint Rocco truce, every year on 16 August", "recurrence_days": 365,
                                         "consequences": ["the families keep the peace that day"]})
        for r in (a, b, k):
            assert r["status"] in ("created", "scaled_down") and r["held_thing_id"], r
        assert b["kind"] == "holding" and k["kind"] == "custom", (b["kind"], k["kind"])
        op = act(c, "p4", "operation", "set up a bookmaking wire in the back of the Ferry Street candy store", details={"time": "a week"})
        assert op.get("status") != "refused", op
        t0 = time.time()
        for i in range(3):
            advance(c, f"p-adv-{i}", 30, "go about my business")
        print(f"  3 x 30 days in {time.time() - t0:.0f}s")
        rows = c.execute("SELECT * FROM held_things ORDER BY id").fetchall()
        assert len(rows) >= 4, [r["name"] for r in rows]  # none vanished; the settled wire is the fourth
        for r in rows:
            assert r["status"] in ("active", "failing", "ended", "building"), dict(r)
            if r["status"] == "ended":
                assert r["ended_reason"], dict(r)
        gaps = {g["shape"] for g in lookup(c, "gaps")["gaps"]}
        assert {"holding", "custom", "thing"} <= gaps, gaps
        for kind, purpose, amount, delta in tally:
            assert abs(amount - delta) < 0.01, (kind, purpose, amount, delta)
        assert tally, "the tick never moved any money"
        print(f"  held rows: {[(r['name'][:28], r['status'], round(r['income_weekly'], 1)) for r in rows]}")
        print(f"  money calls: {len(tally)}; heat on his organisation: {org_heat.read(c, w.org, int(c.execute('SELECT current_day FROM world_state WHERE id=1').fetchone()[0]))}")
    finally:
        ledger.receive, ledger.spend = real_receive, real_spend
    print("intake_play_test passed")


if __name__ == "__main__":
    run()
