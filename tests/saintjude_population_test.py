"""Saint Jude's background population is the bible's (Part I 4.1), not Caerness's 52m, and follows the Design decline."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CAERNESS_BUCKETS = {"underheaven", "dunmoor", "greywood", "sunreach", "windmere", "thornward", "stormhollow", "independent_frontier"}


def run():
    from engine import design, veto
    from engine.db import connect
    from engine.simulation import advance_connection
    from engine.scale import scale_snapshot
    from tools.build_opening import build_opening

    path = Path(tempfile.mkdtemp()) / "sj_pop.db"
    build_opening(path, package="saintjude")
    os.environ["CAERNESS_DB_PATH"] = str(path)
    with connect() as conn:
        total = conn.execute("SELECT SUM(population_estimate) FROM background_population_sources").fetchone()[0]
        assert round(total) == 2_400_000, total
        buckets = {r[0] for r in conn.execute("SELECT DISTINCT bucket_key FROM background_population_sources")}
        assert not (buckets & CAERNESS_BUCKETS), buckets
        assert buckets == {"saintjude_city", "saintjude_metro_remainder"}, buckets
        sj = conn.execute("SELECT id FROM locations WHERE name='Saint Jude'").fetchone()[0]
        city = conn.execute("SELECT id,population_estimate FROM background_population_sources WHERE location_id=?", (sj,)).fetchone()
        assert round(city[1]) == 1_100_000, tuple(city)
        assert conn.execute("SELECT COUNT(*) FROM background_population_sources WHERE location_id IS NOT NULL").fetchone()[0] == 1
        oak = conn.execute("SELECT id FROM locations WHERE name='Oakridge'").fetchone()
        if oak:
            assert not conn.execute("SELECT 1 FROM background_population_sources WHERE location_id=?", (oak[0],)).fetchone()
        assert scale_snapshot(conn)["world_population"] == 2_400_000
        pier = conn.execute("SELECT id FROM locations WHERE name='Pier 4 Diner'").fetchone()[0]
        assert veto.settlement_of(conn, pier) == sj, veto.settlement_of(conn, pier)
        rate = design.figure(conn, "population_decline_pct")
        assert 0.4 <= rate <= 1.5, rate
        start = float(city[1])
        remainder_start = float(conn.execute(
            "SELECT population_estimate FROM background_population_sources WHERE bucket_key='saintjude_metro_remainder'").fetchone()[0])
        conn.commit()
        t0 = time.time()
        for _ in range(5):
            advance_connection(conn, 365)
            conn.commit()
        print(f"5-year advance: {time.time() - t0:.1f}s")
        now = conn.execute("SELECT SUM(c.population) FROM background_population_age_cohorts c WHERE c.source_id=?", (city[0],)).fetchone()[0]
        want = start * (1 - rate / 100) ** 5
        assert abs(now - want) / want < 0.001, (now, want, rate)
        nets = [r[0] for r in conn.execute("SELECT movement_net FROM background_population_yearly_balances WHERE source_id=? ORDER BY period_day", (city[0],))]
        assert len(nets) >= 5 and all(n != 0 for n in nets), nets
        # the unplaced remainder has no path: natural change only, no movement
        rem = conn.execute("SELECT id FROM background_population_sources WHERE bucket_key='saintjude_metro_remainder'").fetchone()[0]
        assert all(r[0] == 0 for r in conn.execute("SELECT movement_net FROM background_population_yearly_balances WHERE source_id=?", (rem,)))
        rem_now = conn.execute("SELECT population_estimate FROM background_population_sources WHERE id=?", (rem,)).fetchone()[0]
        assert abs(rem_now / remainder_start - 1) < 0.05, (rem_now, remainder_start)
    print("saintjude_population_test PASS")


if __name__ == "__main__":
    run()
