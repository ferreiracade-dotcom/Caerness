from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.db import connect, init_db, reset_db
from engine.bootstrap import bootstrap_campaign


from engine.simulation import advance_connection
from engine.stress import contradiction_scan, run_horizon, world_snapshot
from engine.ecology import add_route
from engine.information import register_event_information, process_information
from engine.civilian import create_enterprise
from engine.business import configure_enterprise_business, set_commercial_context


def _fresh(name: str) -> Path:
    path = Path(tempfile.gettempdir()) / f"caerness_candidate_{name}.db"
    os.environ["CAERNESS_DB_PATH"] = str(path)
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    init_db()
    return path


def _errors(conn):
    return [x for x in contradiction_scan(conn) if x["severity"] == "error"]


def _production_120() -> dict:
    path = _fresh("production120")
    with connect() as c:
        bootstrap_campaign(c)
        c.commit()
        checkpoints = []
        total_start = time.perf_counter()
        for years, label in ((20, "year20"), (20, "year40"), (80, "year120")):
            t = time.perf_counter()
            summary = run_horizon(
                c, years, label=f"candidate_{label}", scenario_kind="production_seed",
                checkpoint_years=5, fail_on_contradiction=True,
            )
            elapsed = time.perf_counter() - t
            snap = world_snapshot(c)
            checkpoints.append({
                "label": label,
                "day": snap["day"],
                "elapsed_seconds": elapsed,
                "database_bytes": snap["database_bytes_approx"],
                "decisions": snap["decisions"],
                "events": snap["events"],
                "living_characters": snap["living_characters"],
                "deceased_characters": snap["deceased_characters"],
                "demographic_population": snap["demographic_population"],
                "contradictions": summary["contradictions"],
            })
        total = time.perf_counter() - total_start
        assert c.execute(
            """SELECT COUNT(*) FROM actor_life_profiles lp
               WHERE lp.life_status='deceased' AND EXISTS(
                   SELECT 1 FROM decisions d WHERE d.actor_id=lp.actor_id AND d.day>lp.last_review_day
               )"""
        ).fetchone()[0] == 0
        # Every remaining character simulation profile must belong to a living character.
        assert c.execute(
            """SELECT COUNT(*) FROM simulation_profiles sp JOIN actors a ON a.id=sp.actor_id
               WHERE a.actor_type='character' AND lower(a.status) IN ('dead','deceased')"""
        ).fetchone()[0] == 0
        assert not _errors(c)
        return {"database": str(path), "total_seconds": total, "checkpoints": checkpoints, "final": world_snapshot(c)}


def _alternate_seed(seed: int, years: int = 40) -> dict:
    path = _fresh(f"seed{seed}")
    with connect() as c:
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (int(seed),))
        bootstrap_campaign(c)
        c.commit()
        t = time.perf_counter()
        run_horizon(c, years, label=f"candidate_seed_{seed}", scenario_kind="alternate_seed", checkpoint_years=10)
        elapsed = time.perf_counter() - t
        assert not _errors(c)
        snap = world_snapshot(c)
        return {"seed": seed, "years": years, "elapsed_seconds": elapsed, "snapshot": snap}


def _dense_same_day(count: int = 1500) -> dict:
    _fresh("dense")
    with connect() as c:
        for i in range(count):
            cur = c.execute(
                "INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')",
                (f"Dense Actor {i:04d}",),
            )
            aid = int(cur.lastrowid)
            c.execute(
                """INSERT INTO simulation_profiles(
                       actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day
                   ) VALUES (?,'DORMANT',365,0.1,0.5,0,1)""",
                (aid,),
            )
        c.commit()
        t = time.perf_counter()
        advance_connection(c, 1)
        elapsed = time.perf_counter() - t
        decisions = int(c.execute("SELECT COUNT(*) FROM decisions WHERE day=1").fetchone()[0])
        assert decisions == count, (decisions, count)
        assert not _errors(c)
        return {"actors_due_same_day": count, "elapsed_seconds": elapsed, "decisions": decisions}


def _large_route_information_graph(width: int = 8, height: int = 8, actors_per_location: int = 3) -> dict:
    _fresh("routeinfo")
    with connect() as c:
        locs = []
        for y in range(height):
            row = []
            for x in range(width):
                cur = c.execute("INSERT INTO locations(name,kind) VALUES (?, 'town')", (f"Grid {x},{y}",))
                lid = int(cur.lastrowid)
                row.append(lid)
                for j in range(actors_per_location):
                    c.execute(
                        "INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'character',?,'active')",
                        (f"Grid Person {x}-{y}-{j}", lid),
                    )
            locs.append(row)
        route_count = 0
        for y in range(height):
            for x in range(width):
                if x + 1 < width:
                    add_route(c, locs[y][x], locs[y][x + 1], base_days=1, capacity=95, reliability=95, bidirectional=True)
                    route_count += 1
                if y + 1 < height:
                    add_route(c, locs[y][x], locs[y + 1][x], base_days=1, capacity=95, reliability=95, bidirectional=True)
                    route_count += 1
        origin = locs[0][0]
        cur = c.execute(
            """INSERT INTO events(day,event_type,title,summary,severity,location_id)
               VALUES (0,'public:scale','Grid announcement','A widely discussed public announcement occurred.',4,?)""",
            (origin,),
        )
        eid = int(cur.lastrowid)
        register_event_information(c, eid, visibility="public", rumorability=1.0, reliability=1.0, secrecy=0.0)
        c.commit()
        t = time.perf_counter()
        process_information(c, 60)
        # This synthetic graph test resolves the full information frontier in one batch; align
        # authoritative story time with that batch horizon before integrity scanning.
        c.execute("UPDATE world_state SET current_day=60,updated_at=CURRENT_TIMESTAMP WHERE id=1")
        elapsed = time.perf_counter() - t
        rumour_locations = int(c.execute("SELECT COUNT(*) FROM rumour_locations").fetchone()[0])
        delivered = int(c.execute("SELECT COUNT(*) FROM rumour_transmissions WHERE status='delivered'").fetchone()[0])
        exposures = int(c.execute("SELECT COUNT(*) FROM rumour_exposures").fetchone()[0])
        # One rumour should be able to traverse the full crystallized 8x8 physical graph.
        assert rumour_locations == width * height, (rumour_locations, width * height)
        assert delivered >= width * height - 1
        assert exposures > 0
        assert not _errors(c)
        return {
            "locations": width * height,
            "travel_routes": route_count,
            "actors": width * height * actors_per_location,
            "elapsed_seconds": elapsed,
            "rumour_locations": rumour_locations,
            "delivered_transmissions": delivered,
            "rumour_exposures": exposures,
        }



def _enterprise_scale(locations: int = 10, enterprises: int = 200, years: int = 5) -> dict:
    _fresh("enterprises")
    with connect() as c:
        loc_ids = []
        for i in range(locations):
            cur = c.execute("INSERT INTO locations(name,kind) VALUES (?, 'town')", (f"Trade Town {i:02d}",))
            lid = int(cur.lastrowid)
            loc_ids.append(lid)
            # Deliberately vary commercial conditions without asserting one universal economy.
            set_commercial_context(
                c, lid,
                foot_traffic=40 + (i * 7) % 55,
                traveler_flow=35 + (i * 11) % 60,
                disposable_income=30 + (i * 9) % 65,
                trade_flow=40 + (i * 13) % 55,
                elite_patronage=20 + (i * 17) % 75,
                cultural_activity=25 + (i * 19) % 70,
                credit_demand=30 + (i * 23) % 65,
                military_demand=20 + (i * 29) % 75,
                health_demand=30 + (i * 31) % 65,
                craft_demand=35 + (i * 37) % 60,
                construction_demand=30 + (i * 41) % 65,
                regulation=20 + (i * 43) % 75,
                security=35 + (i * 47) % 60,
                event_activity=20 + (i * 53) % 75,
                reputation_climate=35 + (i * 59) % 60,
            )

        archetypes = [str(r[0]) for r in c.execute(
            "SELECT archetype_key FROM business_archetypes ORDER BY archetype_key"
        ).fetchall()]
        assert archetypes
        enterprise_ids = []
        initial_cash = 0.0
        for i in range(enterprises):
            cash = 250.0 + (i % 17) * 15.0
            initial_cash += cash
            eid = create_enterprise(
                c, f"Scale Enterprise {i:03d}", "other",
                location_id=loc_ids[i % len(loc_ids)],
                capital=500 + (i % 13) * 20, cash=cash, debt=(i % 7) * 10,
                reputation=35 + (i % 61), admin_quality=35 + ((i * 3) % 61),
                labor_capacity=35 + ((i * 5) % 61), risk_tolerance=25 + ((i * 7) % 71),
            )
            configure_enterprise_business(
                c, eid, archetypes[i % len(archetypes)],
                quality=35 + ((i * 11) % 61), price_position=30 + ((i * 13) % 66),
                capacity=25 + ((i * 17) % 76), clientele_fit=30 + ((i * 19) % 66),
                service_reliability=40 + ((i * 23) % 56), regulatory_pressure=(i * 29) % 71,
                cadence_days=30,
            )
            enterprise_ids.append(eid)
        c.commit()
        t = time.perf_counter()
        advance_connection(c, years * 365)
        elapsed = time.perf_counter() - t
        cycles = int(c.execute("SELECT COUNT(*) FROM business_cycles").fetchone()[0])
        profiles = int(c.execute("SELECT COUNT(*) FROM enterprise_business_profiles").fetchone()[0])
        changed = int(c.execute(
            "SELECT COUNT(*) FROM civilian_enterprises WHERE updated_day>0"
        ).fetchone()[0])
        ending_cash = float(c.execute("SELECT COALESCE(SUM(cash),0) FROM civilian_enterprises").fetchone()[0])
        assert profiles == enterprises, (profiles, enterprises)
        assert cycles >= enterprises * years * 10, cycles
        assert changed == enterprises, (changed, enterprises)
        assert ending_cash != initial_cash
        assert not _errors(c)
        return {
            "locations": locations, "enterprises": enterprises, "years": years,
            "business_cycles": cycles, "elapsed_seconds": elapsed,
            "initial_cash": round(initial_cash, 2), "ending_cash": round(ending_cash, 2),
            "database_bytes": int(Path(os.environ["CAERNESS_DB_PATH"]).stat().st_size),
        }

def _worker(name: str) -> dict:
    if name == "production":
        return _production_120()
    if name == "seed271828":
        return _alternate_seed(271828)
    if name == "seed314159":
        return _alternate_seed(314159)
    if name == "dense":
        return _dense_same_day()
    if name == "graph":
        return _large_route_information_graph()
    if name == "enterprise":
        return _enterprise_scale()
    raise ValueError(name)


def _run_isolated(name: str) -> dict:
    # Each case selects and recreates its own temporary database via _fresh(). Running the
    # cases in-process avoids a reproducible child-process finalization stall seen in some
    # Android/container Python environments while preserving database isolation between cases.
    return _worker(name)


def run() -> dict:
    report = {}
    for key, worker in (
        ("production_20_40_120", "production"),
        ("alternate_seed_271828", "seed271828"),
        ("alternate_seed_314159", "seed314159"),
        ("dense_same_day_scheduler", "dense"),
        ("large_route_information_graph", "graph"),
        ("enterprise_business_scale", "enterprise"),
    ):
        print(f"[candidate-scale] {worker}...", flush=True)
        report[key] = _run_isolated(worker)
    report["alternate_deterministic_seeds"] = [
        report.pop("alternate_seed_271828"), report.pop("alternate_seed_314159")
    ]
    print(json.dumps(report, indent=2, sort_keys=True))
    print("v0.26.1 candidate-scale validation PASS")
    return report


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        result = _worker(sys.argv[2])
        print("RESULT_JSON=" + json.dumps(result, sort_keys=True))
    else:
        run()
