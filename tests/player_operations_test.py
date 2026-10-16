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


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "ops.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine import ledger, player_operations as po
        from fixtures_protagonist import make_boss

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            w = make_boss(conn)
            me, biz, outfit = w["me"], w["business"], w["outfit"]
            actors0 = conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
            ev0 = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='player_operation'").fetchone()[0]

            b0, p0 = ledger.balance(conn, ("business", biz)), ledger.balance(conn, ("person", me))
            r = po.execute(conn, me, "pay", target_actor_id=None,
                           details={"from": f"business:{biz}", "to": "me", "amount": "substantial"}, intent="I draw from the till.")
            assert r["status"] == "applied", r
            assert abs(b0 - ledger.balance(conn, ("business", biz)) - 8) < 1e-9
            assert abs(ledger.balance(conn, ("person", me)) - p0 - 8) < 1e-9
            assert "substantial" in r["summary"] and not re.search(r"\d", r["summary"]), r
            assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type='player_operation'").fetchone()[0] == ev0 + 1

            from engine import civilian
            other_id = civilian.create_enterprise(conn, "Foreign Stall", "shop", owner_actor_id=w["bystander"], cash=9)
            ob = ledger.balance(conn, ("business", other_id))
            r = po.execute(conn, me, "pay", target_actor_id=None,
                           details={"from": f"business:{other_id}", "to": "me", "amount": "small"}, intent="I raid it.")
            assert r["status"] == "refused" and ledger.balance(conn, ("business", other_id)) == ob, r
            r = po.execute(conn, me, "pay", target_actor_id=None,
                           details={"from": "me", "to": f"person:{w['bystander']}", "amount": "fortune"}, intent="Too much.")
            assert r["status"] == "refused", r

            # hire: crew leader into the business (tier 1, already the protagonist's personnel)
            r = po.execute(conn, me, "hire", target_actor_id=w["crew_leader"],
                           details={"into": f"business:{biz}", "role": "factor"}, intent="Mind my stall.")
            assert r["status"] == "applied", r
            assert conn.execute("SELECT 1 FROM enterprise_staff WHERE enterprise_id=? AND actor_id=? AND status='active'",
                                (biz, w["crew_leader"])).fetchone()

            # hire the bystander into the outfit (tier 2)
            r = po.execute(conn, me, "hire", target_actor_id=w["bystander"],
                           details={"into": f"outfit:{outfit}", "role": "member", "amount": "modest"}, intent="Join us.")
            row = conn.execute("SELECT status FROM underworld_personnel WHERE actor_id=?", (w["bystander"],)).fetchone()
            if r["status"] == "applied":
                assert row and row["status"] == "active", (r, row)
            else:
                assert r["status"] == "refused" and row is None, (r, row)

            # dismiss the crew leader from the outfit
            res0 = conn.execute("SELECT COALESCE(MAX(resentment),0) FROM relationships WHERE actor_a_id=? AND actor_b_id=?",
                                (w["crew_leader"], me)).fetchone()[0]
            r = po.execute(conn, me, "hire", target_actor_id=w["crew_leader"],
                           details={"into": f"outfit:{outfit}", "role": "none"}, intent="You are done.")
            assert r["status"] == "applied", r
            assert conn.execute("SELECT status FROM underworld_personnel WHERE actor_id=?", (w["crew_leader"],)).fetchone()[0] == "expelled"
            res1 = conn.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?",
                                (w["crew_leader"], me)).fetchone()[0]
            assert res1 > res0, (res0, res1)

            # mistakes are results, never exceptions
            assert po.execute(conn, me, "pay", target_actor_id=None, details={"to": "bank:1", "amount": "small"}, intent="x")["status"] == "refused"
            assert po.execute(conn, me, "pay", target_actor_id=None, details={"to": "me", "amount": "lots"}, intent="x")["status"] == "refused"
            assert po.execute(conn, me, "hire", target_actor_id=None, details={"into": "outfit:1"}, intent="x")["status"] == "refused"

            assert conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0] == actors0
    print("player_operations_test passed")


if __name__ == "__main__":
    run()
