from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _raises(fn, text):
    try:
        fn()
    except ValueError as e:
        assert text in str(e), str(e)
        return
    raise AssertionError(f"expected ValueError containing {text!r}")


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "ledger.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine import civilian, ledger

        init_db()
        with connect() as conn:
            rows = conn.execute(
                "SELECT id FROM actors WHERE actor_type='character' ORDER BY id LIMIT 2"
            ).fetchall()
            me, other = int(rows[0]["id"]), int(rows[1]["id"])
            e = civilian.create_enterprise(conn, "Ledger Test Stall", "shop", owner_actor_id=me, cash=10)
            e2 = civilian.create_enterprise(conn, "Foreign Stall", "shop", owner_actor_id=other, cash=5)

            assert ledger.parse_holder("me", me) == ("person", me)
            assert ledger.parse_holder(f"business:{e}", me) == ("business", e)
            _raises(lambda: ledger.parse_holder("bank:1", me), "holder must be me")
            _raises(lambda: ledger.parse_holder("outfit:999999", me, conn), "unknown outfit")

            flows = lambda: conn.execute("SELECT COUNT(*) FROM economic_flows").fetchone()[0]
            before_person = ledger.balance(conn, ("person", me))
            n = flows()
            assert ledger.transfer(conn, ("business", e), ("person", me), 4, flow_kind="other", purpose="t") == 4
            assert ledger.balance(conn, ("business", e)) == 6
            assert abs(ledger.balance(conn, ("person", me)) - (before_person + 4)) < 1e-9
            assert flows() == n + 1

            n = flows()
            _raises(lambda: ledger.transfer(conn, ("business", e), ("person", me), 100, flow_kind="other", purpose="t"), "not enough money")
            assert ledger.balance(conn, ("business", e)) == 6 and flows() == n

            assert ledger.transfer(conn, ("business", e), ("person", me), 100, flow_kind="other", purpose="t", allow_partial=True) == 6
            assert ledger.balance(conn, ("business", e)) == 0

            assert ledger.scale_word(8) == "substantial"
            assert ledger.scale_word(0.01) == "nothing"
            assert ledger.amount_of("modest") == 3.0
            _raises(lambda: ledger.amount_of("lots"), "token")

            assert ledger.can_draw(conn, me, ("person", me))
            assert ledger.can_draw(conn, me, ("business", e))
            assert not ledger.can_draw(conn, me, ("business", e2))
            assert not ledger.can_draw(conn, me, ("person", other))
    print("ledger_test passed")


if __name__ == "__main__":
    run()
