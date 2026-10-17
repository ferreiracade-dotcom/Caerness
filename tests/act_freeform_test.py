"""act rework: free-form operations, amounts, partial results, counters, memory paging. One packaged-world copy, sections in order."""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def t_amounts(conn, w):
    from engine import ledger, player_operations as po
    me, biz, outfit, hh = w["me"], w["business"], w["outfit"], w["household"]
    assert ledger.amount_of(37) == 37.0 and ledger.amount_of("37 silver") == 37.0 and ledger.amount_of("3 modest") == 9.0
    assert ledger.amount_of("half", 10) == 5.0 and ledger.amount_of("all of it", 7) == 7.0 and ledger.amount_of("25%", 8) == 2.0
    for bad in ("lots", "", -1, True):
        try:
            ledger.amount_of(bad)
        except ValueError:
            continue
        raise AssertionError(bad)

    # money to an institution, a polity, a household; and spent with no recipient
    inst = int(conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND id NOT IN (SELECT institution_actor_id FROM political_polities) LIMIT 1").fetchone()[0])
    pol = conn.execute("SELECT id,institution_actor_id FROM political_polities ORDER BY id LIMIT 1").fetchone()
    ledger.transfer(conn, ("business", biz), ("person", me), 1.0, flow_kind="other", purpose="t")
    conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=50 WHERE actor_id=?", (me,)) if conn.execute(
        "SELECT 1 FROM underworld_leader_wealth WHERE actor_id=?", (me,)).fetchone() else conn.execute(
        "UPDATE resources SET amount=50 WHERE actor_id=? AND resource_type='cash'", (me,))
    b0 = ledger.balance(conn, ("institution", inst))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"institution:{inst}", "amount": 12}, intent="A gift to the house.")
    assert r["status"] == "applied" and abs(ledger.balance(conn, ("institution", inst)) - b0 - 12) < 1e-9, r
    p0 = ledger.balance(conn, ("polity", pol["id"]))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"polity:{pol['id']}", "amount": "5 silver"}, intent="Tax paid.")
    assert r["status"] == "applied" and abs(ledger.balance(conn, ("polity", pol["id"])) - p0 - 5) < 1e-9, r
    assert abs(ledger.balance(conn, ("institution", pol["institution_actor_id"])) - p0 - 5) < 1e-9  # a polity's seat is its treasury
    h0 = ledger.balance(conn, ("household", hh))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"household:{hh}", "amount": "half"}, intent="Keep.")
    assert r["status"] == "applied" and ledger.balance(conn, ("household", hh)) > h0, r
    m0 = ledger.balance(conn, ("person", me))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": "spend", "amount": 4, "purpose": "a feast"}, intent="A feast.")
    assert r["status"] == "applied" and abs(m0 - ledger.balance(conn, ("person", me)) - 4) < 1e-9, r
    # the sink needs rights: an institution he does not lead cannot be drawn on
    assert po.execute(conn, me, "pay", target_actor_id=None, details={"from": f"institution:{inst}", "to": "me", "amount": 1}, intent="x")["status"] == "refused"

    # an oversized sum pays what is there and says so
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"institution:{inst}", "amount": 100000}, intent="All of it.")
    assert r["status"] == "partial" and r.get("short_of") and not re.search(r"\d", r["summary"]), r
    assert ledger.balance(conn, ("person", me)) < 1e-6


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "act.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from fixtures_protagonist import make_boss

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            w = make_boss(conn)
            for fn in (t_amounts,):
                fn(conn, w)
                print(fn.__name__, "ok")
    print("act_freeform_test passed")


if __name__ == "__main__":
    run()
