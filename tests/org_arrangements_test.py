"""Organisation core (task C3): the Pad is one kind of arrangement with an official.

Run: CAERNESS_DB_PATH=<scratch>.db PYTHONPATH=. python tests/org_arrangements_test.py
The first tests run on tests/org_core_fixture.py (a minimal non-Saint-Jude package); the last one runs the Saint Jude
opening and checks the envelope flow of one period against tests/fixtures/org_refactor_baseline.json.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import org_core_fixture as fx


def _fund(conn, actor_id, amount):
    from engine import ledger
    ledger.receive(conn, ("person", actor_id), amount, purpose="test funds")


def _cash(conn, actor_id):
    from engine import ledger
    return ledger.balance(conn, ("person", actor_id))


def test_person_pays_an_official():
    from engine import org_money
    f = fx.build()
    conn = f.conn
    inspector = fx.person(conn, "Inspector One")
    _fund(conn, f.chair, 1000.0)
    org_money.add_arrangement(conn, kind="envelope", payer_kind="actor", payer_id=f.chair, official_actor_id=inspector,
                              weekly_usd=50.0, day=0)
    org_money.post_period(conn, 28, 28)
    rows = conn.execute("SELECT from_actor_id,to_actor_id,amount,org_actor_id,kind FROM org_money WHERE kind='gift'").fetchall()
    assert len(rows) == 1, [tuple(r) for r in rows]
    r = rows[0]
    assert (r["from_actor_id"], r["to_actor_id"]) == (f.chair, inspector) and abs(r["amount"] - 200.0) < 0.01
    assert r["org_actor_id"] == f.firm  # the chair holds exactly one seat
    assert abs(_cash(conn, f.chair) - 800.0) < 0.01 and abs(_cash(conn, inspector) - 200.0) < 0.01
    flow = conn.execute("SELECT flow_kind,amount FROM economic_flows WHERE flow_kind='bribe'").fetchall()
    assert len(flow) == 1 and abs(flow[0]["amount"] - 200.0) < 0.01, [tuple(x) for x in flow]


def test_person_pays_through_a_go_between():
    from engine import org_money
    f = fx.build()
    conn = f.conn
    inspector, runner = fx.person(conn, "Inspector Two"), fx.person(conn, "Runner Two")
    _fund(conn, f.chair, 1000.0)
    org_money.add_arrangement(conn, kind="envelope", payer_kind="actor", payer_id=f.chair, official_actor_id=inspector,
                              weekly_usd=50.0, day=0, go_between_actor_id=runner)
    out = org_money.post_arrangements(conn, 28, 28, org_money.Roster(conn))
    assert abs(out - 200.0) < 0.01, out
    got = sorted((r["from_actor_id"], r["to_actor_id"], round(r["amount"], 2)) for r in conn.execute("SELECT * FROM org_money WHERE kind='gift'"))
    assert got == sorted([(f.chair, runner, 200.0), (runner, inspector, 200.0)]), got
    assert abs(_cash(conn, inspector) - 200.0) < 0.01 and abs(_cash(conn, runner)) < 0.01


def test_arrangement_needs_a_live_payer():
    from engine import org_money
    f = fx.build()
    conn = f.conn
    inspector = fx.person(conn, "Inspector Three")
    _fund(conn, f.chair, 1000.0)
    arr = org_money.add_arrangement(conn, kind="envelope", payer_kind="actor", payer_id=f.chair, official_actor_id=inspector,
                                    weekly_usd=50.0, day=0)
    fx.kill(conn, f.chair)
    org_money.post_period(conn, 28, 28)
    assert conn.execute("SELECT COUNT(*) FROM org_money WHERE kind='gift'").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM org_arrangements WHERE id=?", (arr,)).fetchone()[0] == "lapsed"
    assert abs(_cash(conn, inspector)) < 0.01


def test_org_pays_by_purse_role_weight():
    from engine import org_money
    f = fx.build()
    conn = f.conn
    inspector = fx.person(conn, "Inspector Four")
    for m in f.managers:
        _fund(conn, m, 1000.0)
    org_money.add_arrangement(conn, kind="envelope", payer_kind="org", payer_id=f.firm, official_actor_id=inspector,
                              weekly_usd=70.0, day=0)
    # clerk 1 (manager 1) and clerk 3 (manager 2) each earn 500 a week: equal weights
    org_money.post_period(conn, 28, 28)
    got = {r["from_actor_id"]: r["amount"] for r in conn.execute("SELECT * FROM org_money WHERE kind='gift'")}
    assert set(got) == set(f.managers) and all(abs(v - 140.0) < 0.01 for v in got.values()), got
    # manager 1 dies: his men's take counts toward the head, who pays that share
    fx.kill(conn, f.managers[0])
    _fund(conn, f.chair, 1000.0)
    org_money.post_period(conn, 56, 28)
    got2 = {r["from_actor_id"]: r["amount"] for r in conn.execute("SELECT * FROM org_money WHERE kind='gift' AND day=56")}
    assert set(got2) == {f.chair, f.managers[1]}, got2


def test_dead_official_is_skipped_for_an_org_payer():
    from engine import org_money
    f = fx.build()
    conn = f.conn
    inspector = fx.person(conn, "Inspector Five")
    for m in f.managers:
        _fund(conn, m, 1000.0)
    arr = org_money.add_arrangement(conn, kind="envelope", payer_kind="org", payer_id=f.firm, official_actor_id=inspector,
                                    weekly_usd=70.0, day=0)
    fx.kill(conn, inspector)
    org_money.post_period(conn, 28, 28)
    assert conn.execute("SELECT COUNT(*) FROM org_money WHERE kind='gift'").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM org_arrangements WHERE id=?", (arr,)).fetchone()[0] == "active"  # the position is still paid


def test_saintjude_pad_totals_unchanged():
    """One 28-day period of the Saint Jude opening: the envelope flow matches the pre-refactor sum."""
    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    from tests.make_org_refactor_baseline import main
    want = json.loads((ROOT / "tests" / "fixtures" / "org_refactor_baseline.json").read_text(encoding="utf-8"))
    got = main()
    assert abs(got["pad"] - want["pad"]) <= 1.0, (got["pad"], want["pad"])


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and k != "test_saintjude_pad_totals_unchanged"]
TESTS.append(test_saintjude_pad_totals_unchanged)  # last: it re-points the environment at Saint Jude

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
