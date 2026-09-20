from __future__ import annotations

"""Population conservation bridges for migration and excess mortality.

Tracked people are manifestations of the aggregate population, not additional population.  When
an event supplies an aggregate death count, named/tracked deaths are a subset and are never added
on top.  When a source cannot be resolved, the ledger remains unresolved rather than inventing an
origin.
"""

import json
import sqlite3
from typing import Any

from .background_population import transfer_population


def _j(v: Any) -> str:
    return json.dumps(v if v is not None else {}, sort_keys=True, ensure_ascii=False)


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def population_source_for_location(conn: sqlite3.Connection, location_id: int | None) -> int | None:
    if location_id is None:
        return None
    row = conn.execute(
        """SELECT id FROM background_population_sources
           WHERE location_id=? ORDER BY CASE source_kind WHEN 'settlement' THEN 0 ELSE 1 END,id LIMIT 1""",
        (int(location_id),),
    ).fetchone()
    return int(row[0]) if row else None


def _apply_deaths_to_source(conn: sqlite3.Connection, source_id: int, deaths: float, *, adult_only: bool = True) -> float:
    rows = conn.execute(
        "SELECT age_band,population FROM background_population_age_cohorts WHERE source_id=? ORDER BY age_band",
        (int(source_id),),
    ).fetchall()
    if not rows:
        return 0.0
    eligible = [r for r in rows if (not adult_only or str(r['age_band']) in {'18_39','40_59','60_plus'})]
    total = sum(float(r['population']) for r in eligible)
    amount = min(max(0.0, float(deaths)), total)
    if amount <= 0 or total <= 0:
        return 0.0
    remaining = amount
    for i, r in enumerate(eligible):
        pop = float(r['population'])
        take = remaining if i == len(eligible)-1 else amount * (pop/total)
        take = min(pop, max(0.0, take))
        conn.execute(
            "UPDATE background_population_age_cohorts SET population=MAX(0,population-?) WHERE source_id=? AND age_band=?",
            (take,int(source_id),str(r['age_band'])),
        )
        remaining -= take
    # Source population remains a cached summary of the authoritative age cohorts.
    total_after = conn.execute(
        "SELECT COALESCE(SUM(population),0) FROM background_population_age_cohorts WHERE source_id=?", (int(source_id),)
    ).fetchone()[0]
    conn.execute("UPDATE background_population_sources SET population_estimate=? WHERE id=?", (int(round(float(total_after))),int(source_id)))
    return amount


def record_excess_mortality(
    conn: sqlite3.Connection, *, source_kind: str, source_id: int | None,
    aggregate_deaths: float, tracked_deaths: int = 0, population_source_id: int | None = None,
    metadata: dict[str, Any] | None = None, adult_only: bool = True,
) -> dict[str, Any]:
    """Record and, when possible, apply one aggregate death claim idempotently."""
    day = _day(conn)
    if source_id is not None:
        prior = conn.execute(
            "SELECT * FROM excess_mortality_ledger WHERE source_kind=? AND source_id=?", (source_kind,int(source_id))
        ).fetchone()
        if prior:
            return dict(prior)
    aggregate = max(0.0,float(aggregate_deaths))
    tracked = max(0,int(tracked_deaths))
    # Tracked deaths are manifestations of aggregate casualties. They are audit information, not
    # an additive population decrement.
    applied = 0.0; status = 'unresolved'
    if population_source_id is not None:
        applied = _apply_deaths_to_source(conn,int(population_source_id),aggregate,adult_only=adult_only)
        status = 'applied'
    cur = conn.execute(
        """INSERT INTO excess_mortality_ledger(day,source_kind,source_id,population_source_id,aggregate_deaths,
             tracked_deaths,applied_population_deaths,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (day,source_kind,source_id,population_source_id,aggregate,tracked,applied,status,
         _j({"tracked_deaths_are_subset":True,"adult_only":adult_only,**(metadata or {})})),
    )
    return dict(conn.execute("SELECT * FROM excess_mortality_ledger WHERE id=?", (int(cur.lastrowid),)).fetchone())


def reconcile_pending_excess_mortality(conn: sqlite3.Connection) -> dict[str, int]:
    applied = 0
    for row in conn.execute("SELECT * FROM excess_mortality_ledger WHERE status='unresolved' ORDER BY id").fetchall():
        meta = json.loads(row['metadata_json'] or '{}')
        loc = meta.get('location_id')
        source = population_source_for_location(conn,int(loc)) if loc is not None else None
        if source is None:
            continue
        amount = _apply_deaths_to_source(conn,source,float(row['aggregate_deaths']),adult_only=bool(meta.get('adult_only',True)))
        conn.execute(
            "UPDATE excess_mortality_ledger SET population_source_id=?,applied_population_deaths=?,status='applied' WHERE id=?",
            (source,amount,int(row['id'])),
        )
        applied += 1
    return {"excess_mortality_rows_applied":applied}


def route_aware_transfer(
    conn: sqlite3.Connection, from_source_id: int, to_source_id: int, population: float, *, reason: str,
    route_id: int | None = None, metadata: dict[str, Any] | None = None,
) -> int:
    """Create and complete a migration only when geography provides an explicit route or shared location context."""
    if from_source_id == to_source_id:
        raise ValueError("migration requires distinct population sources")
    fs = conn.execute("SELECT * FROM background_population_sources WHERE id=?",(int(from_source_id),)).fetchone()
    ts = conn.execute("SELECT * FROM background_population_sources WHERE id=?",(int(to_source_id),)).fetchone()
    if not fs or not ts:
        raise ValueError("unknown population source")
    if route_id is None and fs['location_id'] is not None and ts['location_id'] is not None:
        rr = conn.execute(
            """SELECT id FROM travel_routes WHERE status IN ('open','restricted') AND
               ((from_location_id=? AND to_location_id=?) OR (bidirectional=1 AND from_location_id=? AND to_location_id=?))
               ORDER BY id LIMIT 1""",
            (int(fs['location_id']),int(ts['location_id']),int(ts['location_id']),int(fs['location_id'])),
        ).fetchone()
        route_id = int(rr[0]) if rr else None
    cur = conn.execute(
        """INSERT INTO population_migration_requests(from_source_id,to_source_id,requested_population,route_id,requested_day,status,reason,metadata_json)
           VALUES (?,?,?,?,?,'pending',?,?)""",
        (int(from_source_id),int(to_source_id),float(population),route_id,_day(conn),reason,_j(metadata)),
    )
    rid = int(cur.lastrowid)
    if route_id is None and fs['location_id'] is not None and ts['location_id'] is not None:
        conn.execute("UPDATE population_migration_requests SET status='blocked',metadata_json=? WHERE id=?",
                     (_j({"blocked_reason":"no_explicit_route",**(metadata or {})}),rid))
        return rid
    movement_id = transfer_population(conn,int(from_source_id),int(to_source_id),float(population),reason=reason,day=_day(conn),metadata={"migration_request_id":rid,"route_id":route_id,**(metadata or {})})
    conn.execute("UPDATE population_migration_requests SET status='completed',completed_day=?,metadata_json=? WHERE id=?",
                 (_day(conn),_j({"population_movement_id":movement_id,"route_id":route_id,**(metadata or {})}),rid))
    return rid
