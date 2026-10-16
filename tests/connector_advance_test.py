from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.canon import DEFAULT_CANON, index_canon
from engine.db import connect, init_db, reset_db
from engine.simulation import seed_demo


def _day(conn):
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def run():
    reset_db()
    init_db()
    index_canon(DEFAULT_CANON)
    seed_demo()
    from connector.store import ensure_connector_schema
    from connector.timeflow import MAX_ADVANCE_DAYS, advance

    assert MAX_ADVANCE_DAYS == 30
    with connect() as conn:
        conn.execute("PRAGMA busy_timeout=30000")
        ensure_connector_schema(conn)
        results = []

        r = advance(conn, "v1", 5, "rest")
        results.append(r)
        assert r["day_ended"] - r["day_started"] == r["elapsed_days"] and 1 <= r["elapsed_days"] <= 5, r
        assert r["day_ended"] == _day(conn)
        assert isinstance(r["interrupted"], bool) and isinstance(r["noticed"], list) and len(r["noticed"]) <= 8
        if r["interrupted"]:
            assert r["interruption"]

        d = _day(conn)
        again = advance(conn, "v1", 5, "rest")
        assert again["replayed"] is True and _day(conn) == d

        t0 = time.time()
        big = advance(conn, "v2", 45, "wait out the season")
        results.append(big)
        took = time.time() - t0
        assert big["elapsed_days"] <= 30
        assert big["remaining_days"] == 15
        if not big["interrupted"]:
            assert big["elapsed_days"] == 30, big
        else:
            assert big["remaining_days"] == 15
        print(f"45-day request took {took:.1f}s, elapsed {big['elapsed_days']}")

        try:
            advance(conn, "v3", 0, "nothing")
        except ValueError:
            pass
        else:
            raise AssertionError("days=0 accepted")
        assert _day(conn) == big["day_ended"]

        for res in results:
            assert len(json.dumps(res, ensure_ascii=False)) <= 2400
            assert not any(v is None for v in res.values())
    print("connector_advance_test passed")


if __name__ == "__main__":
    run()
