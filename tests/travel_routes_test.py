"""act travel runs over the world's travel_routes (location_links is only a fallback), on the real packaged world."""
from __future__ import annotations

import heapq
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _route_days(conn, a, b):
    g = {}
    for r in conn.execute("SELECT from_location_id f,to_location_id t,base_days d,bidirectional bi FROM travel_routes WHERE status IN ('open','restricted')"):
        g.setdefault(r["f"], []).append((r["t"], r["d"]))
        if r["bi"]:
            g.setdefault(r["t"], []).append((r["f"], r["d"]))
    dist, pq = {a: 0.0}, [(0.0, a)]
    while pq:
        c, n = heapq.heappop(pq)
        if c > dist.get(n, 1e9):
            continue
        for m, d in g.get(n, []):
            if c + d < dist.get(m, 1e9):
                dist[m] = c + d
                heapq.heappush(pq, (c + d, m))
    return dist.get(b)


def run():
    tmp = Path(tempfile.mkdtemp(prefix="travel_routes_"))
    db = tmp / "w.db"
    shutil.copy(ROOT / "data" / "caerness.db", db)
    os.environ["CAERNESS_DB_PATH"] = str(db)
    from connector.acting import act
    from connector.store import ensure_connector_schema
    from engine.actions import shortest_route
    from engine.db import connect
    from fixtures_protagonist import make_boss

    with connect() as conn:
        conn.execute("PRAGMA busy_timeout=30000")
        ensure_connector_schema(conn)
        assert conn.execute("SELECT COUNT(*) FROM location_links").fetchone()[0] == 0
        w = make_boss(conn)
        toll = w["location"]
        loc = {r["name"]: int(r["id"]) for r in conn.execute("SELECT id,name FROM locations")}
        saltmere, pass_ = loc["Saltmere"], loc["Kingsway Pass"]

        def here():
            return conn.execute("SELECT current_location_id FROM player_state WHERE id=1").fetchone()[0]

        def day():
            return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])

        for i, dest in enumerate((saltmere, pass_)):
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (toll, w["me"]))
            conn.execute("UPDATE player_state SET current_location_id=? WHERE id=1", (toll,))
            conn.commit()
            expect = math.ceil(_route_days(conn, toll, dest) - 1e-9)
            d0 = day()
            r = act(conn, f"t{i}", "travel", "I set out.", target_location_id=dest)
            assert r["status"] == "applied", r
            assert r["elapsed_days"] == expect, (r, expect)
            assert day() == d0 + expect
            assert here() == dest, (here(), dest)

        # a district of the current settlement is local movement; so is going back up
        kids = conn.execute("SELECT id,parent_location_id p FROM locations WHERE parent_location_id IS NOT NULL").fetchall()
        kid = next(k for k in kids if conn.execute("SELECT 1 FROM locations WHERE id=? AND parent_location_id IS NULL", (k["p"],)).fetchone())
        parent = int(kid["p"])
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (parent, w["me"]))
        conn.execute("UPDATE player_state SET current_location_id=? WHERE id=1", (parent,))
        conn.commit()
        d0 = day()
        r = act(conn, "k1", "travel", "I walk to the district.", target_location_id=int(kid["id"]))
        assert r["status"] == "applied" and r["elapsed_days"] == 0 and day() == d0 and here() == int(kid["id"]), r
        r = act(conn, "k2", "travel", "I walk back.", target_location_id=parent)
        assert r["status"] == "applied" and r["elapsed_days"] == 0 and here() == parent, r

        # an unreachable place is explained, not a flat refusal
        isl = conn.execute("""SELECT id,name FROM locations l WHERE NOT EXISTS (SELECT 1 FROM travel_routes WHERE from_location_id=l.id OR to_location_id=l.id)
                              AND NOT EXISTS (SELECT 1 FROM locations c WHERE c.parent_location_id=l.id)
                              AND parent_location_id IS NULL AND kind NOT LIKE '%district%' AND kind NOT IN ('sea','lake','river') ORDER BY id LIMIT 1""").fetchone()
        r = act(conn, "u1", "travel", "I go there.", target_location_id=int(isl["id"]))
        assert r["status"] != "applied" and len(r["summary"]) > 40 and "route" in r["summary"].lower(), r
        print("unreachable sample:", isl["name"], "->", r["summary"])

        # a sea, a river or a region cannot be walked to: the journey goes to the nearest port, settlement or pass on it
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (toll, w["me"]))
        conn.execute("UPDATE player_state SET current_location_id=? WHERE id=1", (toll,))
        conn.commit()
        sea = loc["Glassen Sea"]
        r = act(conn, "sea1", "travel", "I take ship on the Glassen Sea.", target_location_id=sea)
        assert r["status"] == "applied" and r.get("destination_note") and here() != sea, r
        assert "port" in conn.execute("SELECT kind FROM locations WHERE id=?", (here(),)).fetchone()[0], here()
        print("sea ->", r["destination_note"])

        # reachability sweep from Toll's Reach over settlements
        sett = [int(r["id"]) for r in conn.execute("SELECT id FROM locations WHERE kind='settlement'")]
        ok = sum(1 for s in sett if shortest_route(conn, toll, s) is not None)
        frac = ok / len(sett)
        print(f"reachable settlements from Toll's Reach: {ok}/{len(sett)} = {frac:.1%}")
        assert frac >= 0.95, frac
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK")


if __name__ == "__main__":
    run()
