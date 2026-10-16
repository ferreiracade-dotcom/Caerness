from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.canon import DEFAULT_CANON, index_canon
from engine.db import connect, init_db, reset_db
from engine.simulation import seed_demo


def _day(conn):
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _n(conn):
    return conn.execute("SELECT COUNT(*) FROM player_actions").fetchone()[0]


def run():
    reset_db()
    init_db()
    index_canon(DEFAULT_CANON)
    seed_demo()
    from connector.acting import act
    from connector.store import ensure_connector_schema

    with connect() as conn:
        conn.execute("PRAGMA busy_timeout=30000")
        ensure_connector_schema(conn)
        ids = {r["name"]: int(r["id"]) for r in conn.execute("SELECT id,name FROM actors")}
        locs = {r["name"]: int(r["id"]) for r in conn.execute("SELECT id,name FROM locations")}
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (locs["Toll's Reach"], ids["[DEMO] House of Seven Ledgers"]))
        conn.commit()
        results = []

        r = act(conn, "a1", "speak", "I ask about the road.", target_actor_id=ids["[DEMO] House of Seven Ledgers"])
        results.append(r)
        assert r["status"] == "applied" and r["elapsed_days"] == 0, r

        r = act(conn, "a2", "observe", "I take stock.")
        results.append(r)
        assert r["status"] == "applied"

        d0 = _day(conn)
        t = act(conn, "a3", "travel", "I ride to Cairnholt.", target_location_id=locs["Cairnholt"])
        results.append(t)
        assert t["status"] == "applied" and t["elapsed_days"] >= 1, t
        assert _day(conn) == d0 + t["elapsed_days"] == t["day_ended"]
        here = conn.execute("SELECT a.current_location_id FROM player_state ps JOIN actors a ON a.id=ps.player_actor_id").fetchone()[0]
        assert here == locs["Cairnholt"]
        assert conn.execute("SELECT current_location_id FROM player_state WHERE id=1").fetchone()[0] == locs["Cairnholt"]

        d1, n1 = _day(conn), _n(conn)
        again = act(conn, "a3", "travel", "I ride to Cairnholt.", target_location_id=locs["Cairnholt"])
        assert again["replayed"] is True and _day(conn) == d1 and _n(conn) == n1

        try:
            act(conn, "a3", "travel", "I ride elsewhere.", target_location_id=locs["Cairnholt"])
        except ValueError:
            pass
        else:
            raise AssertionError("call_id reuse with other arguments accepted")

        r = act(conn, "a4", "seize_castle", "I take the castle.")
        results.append(r)
        assert r["status"] == "refused" and "observe" in r["summary"]
        assert _day(conn) == d1 and _n(conn) == n1
        assert act(conn, "a4", "seize_castle", "I take the castle.")["replayed"] is True  # refusals are stored

        r = act(conn, "a5", "speak", "Hello?", target_actor_id=99999999)
        results.append(r)
        assert r["status"] != "applied" and _day(conn) == d1 and _n(conn) == n1
        r = act(conn, "a6", "travel", "Go.", target_location_id=99999999)
        results.append(r)
        assert r["status"] != "applied" and _day(conn) == d1 and _n(conn) == n1
        r = act(conn, "a7", "respond", "Yes.", interaction_id=99999999, response_choice="accept")
        results.append(r)
        assert r["status"] != "applied" and _n(conn) == n1
        r = act(conn, "a8", "respond", "Maybe.", interaction_id=1, response_choice="dither")
        assert r["status"] != "applied" and _n(conn) == n1

        for res in results:
            assert len(json.dumps(res, ensure_ascii=False)) <= 2400
            assert not any(v is None for v in res.values())
    print("connector_act_test passed")


if __name__ == "__main__":
    run()
