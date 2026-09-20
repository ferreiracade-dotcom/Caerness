from __future__ import annotations

import heapq
import json
import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _actor_alive(conn: sqlite3.Connection, actor_id: int) -> bool:
    row = conn.execute("SELECT status FROM actors WHERE id=?", (actor_id,)).fetchone()
    return bool(row and str(row[0]).lower() not in {"dead", "deceased", "destroyed", "dissolved"})


def configure_environment(conn: sqlite3.Connection, location_id: int, *, climate_label: str | None = None,
                          terrain_kind: str | None = None, year_length: int = 360, phase_offset: int = 0,
                          base_travel_factor: float = 1.0, base_production_factor: float = 1.0,
                          base_health_pressure: float = 0.0, current_density: float = 50,
                          current_stability: float = 50, current_replenishment: float = 50,
                          current_breadth: float = 50, current_concentration: float = 50,
                          current_carrying_capacity: float = 100, current_load: float = 0,
                          metadata: dict[str, Any] | None = None) -> None:
    if year_length < 30:
        raise ValueError("year_length must be >= 30")
    if base_travel_factor <= 0 or base_production_factor <= 0:
        raise ValueError("environment factors must be positive")
    if not conn.execute("SELECT 1 FROM locations WHERE id=?", (location_id,)).fetchone():
        raise ValueError("Unknown location")
    day = _day(conn)
    conn.execute(
        """INSERT INTO location_environment_profiles(
               location_id,climate_label,terrain_kind,year_length,phase_offset,base_travel_factor,base_production_factor,
               base_health_pressure,current_density,current_stability,current_replenishment,current_breadth,current_concentration,
               current_carrying_capacity,current_load,last_review_day,next_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(location_id) DO UPDATE SET
             climate_label=excluded.climate_label,terrain_kind=excluded.terrain_kind,year_length=excluded.year_length,
             phase_offset=excluded.phase_offset,base_travel_factor=excluded.base_travel_factor,
             base_production_factor=excluded.base_production_factor,base_health_pressure=excluded.base_health_pressure,
             current_density=excluded.current_density,current_stability=excluded.current_stability,
             current_replenishment=excluded.current_replenishment,current_breadth=excluded.current_breadth,
             current_concentration=excluded.current_concentration,current_carrying_capacity=excluded.current_carrying_capacity,
             current_load=excluded.current_load,metadata_json=excluded.metadata_json""",
        (location_id, climate_label, terrain_kind, int(year_length), int(phase_offset), float(base_travel_factor),
         float(base_production_factor), max(0.0, min(100.0, float(base_health_pressure))),
         max(0.0, min(100.0, float(current_density))), max(0.0, min(100.0, float(current_stability))),
         max(0.0, min(100.0, float(current_replenishment))), max(0.0, min(100.0, float(current_breadth))),
         max(0.0, min(100.0, float(current_concentration))), max(0.0, float(current_carrying_capacity)),
         max(0.0, float(current_load)), day, day + 30, json.dumps(metadata or {}, sort_keys=True)),
    )


def add_seasonal_window(conn: sqlite3.Connection, location_id: int, name: str, start_day_of_year: int,
                        end_day_of_year: int, *, travel_factor: float = 1.0, production_factor: float = 1.0,
                        health_pressure: float = 0.0, current_replenishment_factor: float = 1.0,
                        route_risk_delta: float = 0.0, metadata: dict[str, Any] | None = None) -> int:
    p = conn.execute("SELECT year_length FROM location_environment_profiles WHERE location_id=?", (location_id,)).fetchone()
    if not p:
        raise ValueError("Configure the location environment first")
    year = int(p[0])
    if not (0 <= int(start_day_of_year) < year and 0 <= int(end_day_of_year) < year):
        raise ValueError("seasonal window days must fit the configured year")
    if travel_factor <= 0 or production_factor <= 0 or current_replenishment_factor < 0:
        raise ValueError("invalid seasonal factor")
    cur = conn.execute(
        """INSERT INTO seasonal_windows(location_id,name,start_day_of_year,end_day_of_year,travel_factor,production_factor,
              health_pressure,current_replenishment_factor,route_risk_delta,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (location_id, name, int(start_day_of_year), int(end_day_of_year), float(travel_factor), float(production_factor),
         max(0.0, min(100.0, float(health_pressure))), float(current_replenishment_factor), float(route_risk_delta),
         json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def add_environmental_condition(conn: sqlite3.Connection, location_id: int, condition_kind: str, label: str,
                                start_day: int, *, end_day: int | None = None, travel_factor: float = 1.0,
                                production_factor: float = 1.0, health_pressure: float = 0.0,
                                current_replenishment_factor: float = 1.0, route_risk_delta: float = 0.0,
                                metadata: dict[str, Any] | None = None) -> int:
    if end_day is not None and int(end_day) < int(start_day):
        raise ValueError("end_day cannot precede start_day")
    if travel_factor <= 0 or production_factor <= 0 or current_replenishment_factor < 0:
        raise ValueError("invalid environmental factor")
    cur = conn.execute(
        """INSERT INTO environmental_conditions(location_id,condition_kind,label,start_day,end_day,travel_factor,
              production_factor,health_pressure,current_replenishment_factor,route_risk_delta,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (location_id, condition_kind, label, int(start_day), end_day, float(travel_factor), float(production_factor),
         max(0.0, min(100.0, float(health_pressure))), float(current_replenishment_factor), float(route_risk_delta),
         json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _window_active(start: int, end: int, pos: int) -> bool:
    if start <= end:
        return start <= pos <= end
    return pos >= start or pos <= end


def environment_effects(conn: sqlite3.Connection, location_id: int, day: int | None = None) -> dict[str, float | str | None]:
    day = _day(conn) if day is None else int(day)
    p = conn.execute("SELECT * FROM location_environment_profiles WHERE location_id=? AND status!='inactive'", (location_id,)).fetchone()
    if not p:
        return {"travel_factor": 1.0, "production_factor": 1.0, "health_pressure": 0.0,
                "current_replenishment_factor": 1.0, "route_risk_delta": 0.0, "season_name": None}
    year = int(p["year_length"])
    pos = (day + int(p["phase_offset"])) % year
    travel = float(p["base_travel_factor"])
    production = float(p["base_production_factor"])
    health = float(p["base_health_pressure"])
    repl = 1.0
    risk = 0.0
    season_names: list[str] = []
    for row in conn.execute("SELECT * FROM seasonal_windows WHERE location_id=? AND status='active' ORDER BY id", (location_id,)).fetchall():
        if _window_active(int(row["start_day_of_year"]), int(row["end_day_of_year"]), pos):
            sensitivity = 1.0
            travel *= max(0.05, 1.0 + (float(row["travel_factor"]) - 1.0) * sensitivity)
            production *= max(0.05, float(row["production_factor"]))
            health += float(row["health_pressure"])
            repl *= max(0.0, float(row["current_replenishment_factor"]))
            risk += float(row["route_risk_delta"])
            season_names.append(str(row["name"]))
    for row in conn.execute(
        """SELECT * FROM environmental_conditions
           WHERE location_id=? AND status='active' AND start_day<=? AND (end_day IS NULL OR end_day>=?) ORDER BY id""",
        (location_id, day, day),
    ).fetchall():
        travel *= max(0.05, float(row["travel_factor"]))
        production *= max(0.05, float(row["production_factor"]))
        health += float(row["health_pressure"])
        repl *= max(0.0, float(row["current_replenishment_factor"]))
        risk += float(row["route_risk_delta"])
    return {
        "travel_factor": max(0.05, travel),
        "production_factor": max(0.05, production),
        "health_pressure": max(0.0, min(100.0, health)),
        "current_replenishment_factor": max(0.0, repl),
        "route_risk_delta": risk,
        "season_name": ", ".join(season_names) if season_names else None,
    }


def production_factor(conn: sqlite3.Connection, location_id: int | None, day: int, category: str | None = None) -> float:
    if location_id is None:
        return 1.0
    raw = float(environment_effects(conn, int(location_id), day)["production_factor"])
    cat = (category or "").lower()
    if cat in {"agriculture", "crop", "grain", "food", "farming"}:
        return raw
    # Non-agricultural work still feels transport/material/weather friction, but less strongly.
    return 1.0 + (raw - 1.0) * 0.35


def environmental_transport_pressure(conn: sqlite3.Connection, location_id: int | None, day: int) -> float:
    if location_id is None:
        return 0.0
    e = environment_effects(conn, int(location_id), day)
    factor = float(e["travel_factor"])
    return max(0.0, (factor - 1.0) * 45.0 + max(0.0, float(e["route_risk_delta"])))


def current_sustainability(conn: sqlite3.Connection, location_id: int) -> dict[str, float]:
    p = conn.execute("SELECT * FROM location_environment_profiles WHERE location_id=?", (location_id,)).fetchone()
    if not p:
        return {"capacity": 0.0, "load": 0.0, "available": 0.0, "load_ratio": 0.0}
    cap = float(p["current_carrying_capacity"])
    load = float(p["current_load"])
    return {"capacity": cap, "load": load, "available": max(0.0, cap - load), "load_ratio": 0.0 if cap <= 0 else load / cap}


def register_current_use(conn: sqlite3.Connection, location_id: int, amount: float, *, source_kind: str = "simulation",
                         source_id: int | None = None, description: str | None = None,
                         metadata: dict[str, Any] | None = None) -> int:
    amount = max(0.0, float(amount))
    if not conn.execute("SELECT 1 FROM location_environment_profiles WHERE location_id=?", (location_id,)).fetchone():
        raise ValueError("Configure the location environment first")
    day = _day(conn)
    conn.execute("UPDATE location_environment_profiles SET current_load=current_load+? WHERE location_id=?", (amount, location_id))
    cur = conn.execute(
        """INSERT INTO current_usage_events(location_id,day,amount,source_kind,source_id,description,metadata_json)
           VALUES (?,?,?,?,?,?,?)""",
        (location_id, day, amount, source_kind, source_id, description, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def add_route(conn: sqlite3.Connection, from_location_id: int, to_location_id: int, *, route_kind: str = "road",
              base_days: float, capacity: float = 50, reliability: float = 80, seasonal_sensitivity: float = 1.0,
              bidirectional: bool = True, metadata: dict[str, Any] | None = None) -> int:
    if int(from_location_id) == int(to_location_id):
        raise ValueError("route endpoints must differ")
    if base_days <= 0:
        raise ValueError("base_days must be positive")
    cur = conn.execute(
        """INSERT INTO travel_routes(from_location_id,to_location_id,route_kind,base_days,capacity,reliability,
              seasonal_sensitivity,bidirectional,metadata_json) VALUES (?,?,?,?,?,?,?,?,?)""",
        (from_location_id, to_location_id, route_kind, float(base_days), max(0.0, min(100.0, float(capacity))),
         max(0.0, min(100.0, float(reliability))), max(0.0, float(seasonal_sensitivity)), 1 if bidirectional else 0,
         json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def add_route_condition(conn: sqlite3.Connection, route_id: int, condition_kind: str, label: str, start_day: int, *,
                        end_day: int | None = None, accessibility: float = 100, delay_factor: float = 1.0,
                        hazard_pressure: float = 0.0, metadata: dict[str, Any] | None = None) -> int:
    if end_day is not None and int(end_day) < int(start_day):
        raise ValueError("end_day cannot precede start_day")
    cur = conn.execute(
        """INSERT INTO route_conditions(route_id,condition_kind,label,start_day,end_day,accessibility,delay_factor,hazard_pressure,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (route_id, condition_kind, label, int(start_day), end_day, max(0.0, min(100.0, float(accessibility))),
         max(0.05, float(delay_factor)), max(0.0, min(100.0, float(hazard_pressure))),
         json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _route_endpoints(row: sqlite3.Row, from_location: int) -> int | None:
    if int(row["from_location_id"]) == from_location:
        return int(row["to_location_id"])
    if int(row["bidirectional"]) and int(row["to_location_id"]) == from_location:
        return int(row["from_location_id"])
    return None


def _route_eval(conn: sqlite3.Connection, route: sqlite3.Row, from_location: int, day: int) -> dict[str, float | int | bool]:
    target = _route_endpoints(route, from_location)
    if target is None or str(route["status"]) in {"closed", "destroyed"}:
        return {"usable": False, "target": -1, "days": math.inf, "hazard": 0.0, "accessibility": 0.0}
    source_eff = environment_effects(conn, from_location, day)
    target_eff = environment_effects(conn, target, day)
    env_factor = (float(source_eff["travel_factor"]) + float(target_eff["travel_factor"])) / 2.0
    sensitivity = float(route["seasonal_sensitivity"])
    factor = max(0.05, 1.0 + (env_factor - 1.0) * sensitivity)
    accessibility = 100.0 if str(route["status"]) == "open" else 65.0
    delay = 1.0
    hazard = max(0.0, (100.0 - float(route["reliability"])) * 0.15)
    for c in conn.execute(
        """SELECT * FROM route_conditions WHERE route_id=? AND status='active' AND start_day<=?
           AND (end_day IS NULL OR end_day>=?) ORDER BY id""", (route["id"], day, day)
    ).fetchall():
        accessibility = min(accessibility, float(c["accessibility"]))
        delay *= float(c["delay_factor"])
        hazard += float(c["hazard_pressure"])
    if accessibility <= 0:
        return {"usable": False, "target": target, "days": math.inf, "hazard": hazard, "accessibility": accessibility}
    access_delay = 1.0 + (100.0 - accessibility) / 140.0
    days = max(1.0, float(route["base_days"]) * factor * delay * access_delay)
    hazard += max(0.0, float(source_eff["health_pressure"]) + float(target_eff["health_pressure"])) * 0.25
    return {"usable": True, "target": target, "days": days, "hazard": max(0.0, hazard), "accessibility": accessibility}


def _adjacent_routes(conn: sqlite3.Connection, location_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT * FROM travel_routes WHERE status IN ('open','restricted') AND
           (from_location_id=? OR (bidirectional=1 AND to_location_id=?)) ORDER BY id""",
        (location_id, location_id),
    ).fetchall()


@dataclass(frozen=True)
class RoutePathSnapshot:
    """Read-only route graph for one simulation day.

    SQL remains authoritative.  The snapshot is deliberately short-lived: callers build it
    inside one domain process/checkpoint and discard it afterwards, so route/environment
    mutation never has to invalidate a second source of truth.
    """
    day: int
    adjacency: dict[int, tuple[tuple[int, int, float], ...]]


def build_route_path_snapshot(conn: sqlite3.Connection, *, day: int | None = None) -> RoutePathSnapshot:
    day = _day(conn) if day is None else int(day)
    adjacency: dict[int, list[tuple[int, int, float]]] = {}
    routes = conn.execute(
        "SELECT * FROM travel_routes WHERE status IN ('open','restricted') ORDER BY id"
    ).fetchall()
    for route in routes:
        rid = int(route["id"])
        a = int(route["from_location_id"]); b = int(route["to_location_id"])
        ev = _route_eval(conn, route, a, day)
        if bool(ev["usable"]):
            adjacency.setdefault(a, []).append((rid, int(ev["target"]), float(ev["days"])))
        if int(route["bidirectional"]):
            ev = _route_eval(conn, route, b, day)
            if bool(ev["usable"]):
                adjacency.setdefault(b, []).append((rid, int(ev["target"]), float(ev["days"])))
    return RoutePathSnapshot(
        day=day,
        adjacency={loc: tuple(sorted(edges, key=lambda x: x[0])) for loc, edges in adjacency.items()},
    )


def find_route_path_snapshot(snapshot: RoutePathSnapshot, origin_location_id: int, destination_location_id: int) -> list[int]:
    origin = int(origin_location_id); destination = int(destination_location_id)
    if origin == destination:
        return []
    dist: dict[int, float] = {origin: 0.0}
    prev: dict[int, tuple[int, int]] = {}
    q: list[tuple[float, int]] = [(0.0, origin)]
    seen: set[int] = set()
    while q:
        cost, loc = heapq.heappop(q)
        if loc in seen:
            continue
        seen.add(loc)
        if loc == destination:
            break
        for rid, target, days in snapshot.adjacency.get(loc, ()):
            nc = cost + days
            if nc < dist.get(target, math.inf):
                dist[target] = nc
                prev[target] = (loc, rid)
                heapq.heappush(q, (nc, target))
    if destination not in dist:
        return []
    path: list[int] = []
    cur = destination
    while cur != origin:
        prior, rid = prev[cur]
        path.append(rid)
        cur = prior
    path.reverse()
    return path


def route_information_lag_snapshot(snapshot: RoutePathSnapshot, origin_location_id: int, destination_location_id: int) -> int | None:
    origin = int(origin_location_id); destination = int(destination_location_id)
    if origin == destination:
        return 0
    path = find_route_path_snapshot(snapshot, origin, destination)
    if not path:
        return None
    current = origin; lag = 0
    for rid in path:
        edge = next((e for e in snapshot.adjacency.get(current, ()) if e[0] == rid), None)
        if edge is None:
            return None
        _, current, days = edge
        lag += max(1, int(math.ceil(days)))
    return lag


def find_route_path(conn: sqlite3.Connection, origin_location_id: int, destination_location_id: int, *, day: int | None = None) -> list[int]:
    day = _day(conn) if day is None else int(day)
    if origin_location_id == destination_location_id:
        return []
    dist: dict[int, float] = {int(origin_location_id): 0.0}
    prev: dict[int, tuple[int, int]] = {}
    q: list[tuple[float, int]] = [(0.0, int(origin_location_id))]
    seen: set[int] = set()
    while q:
        cost, loc = heapq.heappop(q)
        if loc in seen:
            continue
        seen.add(loc)
        if loc == int(destination_location_id):
            break
        for route in _adjacent_routes(conn, loc):
            ev = _route_eval(conn, route, loc, day)
            if not bool(ev["usable"]):
                continue
            target = int(ev["target"])
            nc = cost + float(ev["days"])
            if nc < dist.get(target, math.inf):
                dist[target] = nc
                prev[target] = (loc, int(route["id"]))
                heapq.heappush(q, (nc, target))
    if int(destination_location_id) not in dist:
        return []
    path: list[int] = []
    cur = int(destination_location_id)
    while cur != int(origin_location_id):
        p, rid = prev[cur]
        path.append(rid)
        cur = p
    path.reverse()
    return path


def evaluate_route_leg(conn: sqlite3.Connection, route_id: int, from_location_id: int, *, day: int | None = None) -> dict[str, float | int | bool]:
    """Public read-only route-leg evaluation for other movement owners such as logistics."""
    route = conn.execute("SELECT * FROM travel_routes WHERE id=?", (route_id,)).fetchone()
    if not route:
        raise ValueError("Unknown travel route")
    return _route_eval(conn, route, int(from_location_id), _day(conn) if day is None else int(day))


def _subject_location(conn: sqlite3.Connection, subject_kind: str, subject_id: int) -> int:
    if subject_kind == "actor":
        row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (subject_id,)).fetchone()
    elif subject_kind == "household":
        row = conn.execute("SELECT location_id FROM households WHERE id=?", (subject_id,)).fetchone()
    else:
        raise ValueError("Unsupported travel subject")
    if not row or row[0] is None:
        raise ValueError("Travel subject has no current location")
    return int(row[0])


def _move_subject(conn: sqlite3.Connection, subject_kind: str, subject_id: int, location_id: int) -> None:
    if subject_kind == "actor":
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (location_id, subject_id))
    else:
        conn.execute("UPDATE households SET location_id=?,updated_day=? WHERE id=?", (location_id, _day(conn), subject_id))
        conn.execute(
            """UPDATE actors SET current_location_id=? WHERE id IN
               (SELECT actor_id FROM household_members WHERE household_id=? AND status='active')""",
            (location_id, subject_id),
        )


def _begin_next_segment(conn: sqlite3.Connection, plan_id: int, day: int) -> bool:
    plan = conn.execute("SELECT * FROM travel_plans WHERE id=?", (plan_id,)).fetchone()
    if not plan or str(plan["status"]) not in {"active", "stalled"}:
        return False
    current = int(plan["current_location_id"])
    destination = int(plan["destination_location_id"])
    if current == destination:
        conn.execute("UPDATE travel_plans SET status='arrived',arrived_day=?,current_route_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?",
                     (day, day, plan_id))
        return True
    path = find_route_path(conn, current, destination, day=day)
    if not path:
        conn.execute("UPDATE travel_plans SET status='stalled',current_route_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?",
                     (day + 3, plan_id))
        return False
    route = conn.execute("SELECT * FROM travel_routes WHERE id=?", (path[0],)).fetchone()
    ev = _route_eval(conn, route, current, day)
    if not bool(ev["usable"]):
        conn.execute("UPDATE travel_plans SET status='stalled',next_review_day=? WHERE id=?", (day + 3, plan_id))
        return False
    due = day + max(1, int(math.ceil(float(ev["days"]))))
    meta = json.loads(plan["metadata_json"] or "{}")
    meta["segment_target_location_id"] = int(ev["target"])
    meta["segment_hazard_pressure"] = float(ev["hazard"])
    meta["planned_path"] = path
    conn.execute(
        """UPDATE travel_plans SET status='active',current_route_id=?,segment_started_day=?,segment_due_day=?,next_review_day=?,metadata_json=? WHERE id=?""",
        (int(route["id"]), day, due, due, json.dumps(meta, sort_keys=True), plan_id),
    )
    return True


def start_travel(conn: sqlite3.Connection, subject_kind: str, subject_id: int, destination_location_id: int, *,
                 metadata: dict[str, Any] | None = None) -> int:
    if subject_kind == "actor" and not _actor_alive(conn, subject_id):
        raise ValueError("Dead/inactive actors cannot begin travel")
    origin = _subject_location(conn, subject_kind, subject_id)
    if origin == int(destination_location_id):
        raise ValueError("Travel destination is the current location")
    if conn.execute("SELECT 1 FROM travel_plans WHERE subject_kind=? AND subject_id=? AND status IN ('active','stalled')",
                    (subject_kind, subject_id)).fetchone():
        raise ValueError("Subject already has active travel")
    if not find_route_path(conn, origin, int(destination_location_id), day=_day(conn)):
        raise ValueError("No traversable route to destination")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO travel_plans(subject_kind,subject_id,origin_location_id,destination_location_id,current_location_id,
              started_day,next_review_day,metadata_json) VALUES (?,?,?,?,?,?,?,?)""",
        (subject_kind, subject_id, origin, int(destination_location_id), origin, day, day,
         json.dumps(metadata or {}, sort_keys=True)),
    )
    pid = int(cur.lastrowid)
    _begin_next_segment(conn, pid, day)
    return pid


def cancel_travel(conn: sqlite3.Connection, plan_id: int) -> None:
    row = conn.execute("SELECT status FROM travel_plans WHERE id=?", (plan_id,)).fetchone()
    if not row:
        raise ValueError("Unknown travel plan")
    if str(row[0]) in {"arrived", "cancelled"}:
        return
    conn.execute("UPDATE travel_plans SET status='cancelled',current_route_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?",
                 (_day(conn), plan_id))


def _review_environment(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> None:
    elapsed = max(0, day - int(row["last_review_day"]))
    if elapsed <= 0:
        return
    eff = environment_effects(conn, int(row["location_id"]), day)
    cap = float(row["current_carrying_capacity"])
    load = float(row["current_load"])
    # Replenishment is bounded by both the site's intrinsic rate and current environmental conditions.
    recovery_per_30 = cap * (float(row["current_replenishment"]) / 100.0) * 0.35 * float(eff["current_replenishment_factor"])
    load = max(0.0, load - recovery_per_30 * elapsed / 30.0)
    conn.execute(
        "UPDATE location_environment_profiles SET current_load=?,last_review_day=?,next_review_day=? WHERE location_id=?",
        (load, day, day + 30, row["location_id"]),
    )


def _travel_health_consequence(conn: sqlite3.Connection, plan: sqlite3.Row, day: int) -> None:
    exposure = float(plan["exposure_pressure"])
    if exposure < 30 or plan["subject_kind"] != "actor" or not _actor_alive(conn, int(plan["subject_id"])):
        return
    # This is intentionally abstract: ecology creates a fatigue/exposure condition; health owns its resolution.
    from .health import add_condition
    actor_id = int(plan["subject_id"])
    existing = conn.execute(
        "SELECT 1 FROM health_conditions WHERE actor_id=? AND condition_kind='fatigue' AND status IN ('active','recovering','chronic') AND label='Travel exposure'",
        (actor_id,),
    ).fetchone()
    if existing:
        return
    severity = min(45.0, 8.0 + exposure * 0.22)
    add_condition(conn, actor_id, "fatigue", "Travel exposure", severity=severity,
                  capacity_impact=min(30.0, severity * 0.55), recovery_rate_per_30=18.0,
                  progression_rate_per_30=0.0, fatality_pressure=0.0, next_review_days=7,
                  metadata={"source": "ecology_travel", "travel_plan_id": int(plan["id"])})


def _process_travel_plan(conn: sqlite3.Connection, row: sqlite3.Row, day: int, event_logger: Callable[..., int] | None) -> None:
    if row["subject_kind"] == "actor" and not _actor_alive(conn, int(row["subject_id"])):
        conn.execute("UPDATE travel_plans SET status='cancelled',next_review_day=? WHERE id=?", (day, row["id"]))
        return
    if str(row["status"]) == "stalled":
        _begin_next_segment(conn, int(row["id"]), day)
        return
    due = row["segment_due_day"]
    if due is None or int(due) > day:
        return
    meta = json.loads(row["metadata_json"] or "{}")
    target = meta.get("segment_target_location_id")
    if target is None:
        conn.execute("UPDATE travel_plans SET status='stalled',next_review_day=? WHERE id=?", (day + 3, row["id"]))
        return
    seg_elapsed = max(1, day - int(row["segment_started_day"] or row["started_day"]))
    hazard = max(0.0, float(meta.get("segment_hazard_pressure", 0.0)))
    exposure_add = hazard * seg_elapsed / 10.0
    new_exposure = float(row["exposure_pressure"]) + exposure_add
    _move_subject(conn, str(row["subject_kind"]), int(row["subject_id"]), int(target))
    conn.execute("UPDATE travel_plans SET current_location_id=?,exposure_pressure=?,current_route_id=NULL,segment_due_day=NULL WHERE id=?",
                 (int(target), new_exposure, row["id"]))
    fresh = conn.execute("SELECT * FROM travel_plans WHERE id=?", (row["id"],)).fetchone()
    if int(target) == int(row["destination_location_id"]):
        conn.execute("UPDATE travel_plans SET status='arrived',arrived_day=?,next_review_day=? WHERE id=?", (day, day, row["id"]))
        final = conn.execute("SELECT * FROM travel_plans WHERE id=?", (row["id"],)).fetchone()
        _travel_health_consequence(conn, final, day)
        if row["subject_kind"] == "household":
            mid = meta.get("migration_plan_id")
            if mid is not None:
                conn.execute("UPDATE household_migration_plans SET status='completed',completed_day=? WHERE id=? AND status='in_transit'", (day, int(mid)))
        if event_logger:
            name = None
            if row["subject_kind"] == "actor":
                r = conn.execute("SELECT name FROM actors WHERE id=?", (row["subject_id"],)).fetchone(); name = r[0] if r else None
            else:
                r = conn.execute("SELECT name FROM households WHERE id=?", (row["subject_id"],)).fetchone(); name = r[0] if r else None
            loc = conn.execute("SELECT name FROM locations WHERE id=?", (target,)).fetchone()
            event_logger(day=day, event_type="travel_arrival", title="Travel completed",
                         summary=f"{name or 'A travelling party'} arrived at {loc[0] if loc else 'its destination'}.",
                         severity=1, source_actor_id=int(row["subject_id"]) if row["subject_kind"] == "actor" else None,
                         location_id=int(target), visibility="limited", secrecy=0.0, rumorability=0.2, reliability=1.0)
    else:
        _begin_next_segment(conn, int(row["id"]), day)


def next_ecology_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals: list[int] = []
    for sql in (
        "SELECT MIN(next_review_day) FROM location_environment_profiles WHERE status!='inactive' AND next_review_day>? AND next_review_day<=?",
        "SELECT MIN(next_review_day) FROM travel_plans WHERE status IN ('active','stalled') AND next_review_day>? AND next_review_day<=?",
    ):
        v = conn.execute(sql, (after_day, end_day)).fetchone()[0]
        if v is not None:
            vals.append(int(v))
    return min(vals) if vals else None


def process_due_ecology(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    stats = {"environment_reviews": 0, "travel_updates": 0, "arrivals": 0}
    rows = conn.execute("SELECT * FROM location_environment_profiles WHERE status!='inactive' AND next_review_day<=? ORDER BY next_review_day,location_id", (day,)).fetchall()
    for row in rows:
        _review_environment(conn, row, day)
        stats["environment_reviews"] += 1
    plans = conn.execute("SELECT * FROM travel_plans WHERE status IN ('active','stalled') AND next_review_day<=? ORDER BY next_review_day,id", (day,)).fetchall()
    for row in plans:
        before = str(row["status"])
        _process_travel_plan(conn, row, day, event_logger)
        stats["travel_updates"] += 1
        after = conn.execute("SELECT status FROM travel_plans WHERE id=?", (row["id"],)).fetchone()[0]
        if before != "arrived" and after == "arrived":
            stats["arrivals"] += 1
    conn.execute("UPDATE environmental_conditions SET status='ended' WHERE status='active' AND end_day IS NOT NULL AND end_day<?", (day,))
    conn.execute("UPDATE route_conditions SET status='ended' WHERE status='active' AND end_day IS NOT NULL AND end_day<?", (day,))
    return stats


def ecology_context(conn: sqlite3.Connection, location_id: int, day: int | None = None) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    p = conn.execute("SELECT * FROM location_environment_profiles WHERE location_id=?", (location_id,)).fetchone()
    effects = environment_effects(conn, location_id, day)
    current = current_sustainability(conn, location_id)
    routes = []
    for r in _adjacent_routes(conn, location_id):
        ev = _route_eval(conn, r, location_id, day)
        if bool(ev["usable"]):
            target = conn.execute("SELECT name FROM locations WHERE id=?", (int(ev["target"]),)).fetchone()
            routes.append({"route_id": int(r["id"]), "to": target[0] if target else int(ev["target"]),
                           "route_kind": r["route_kind"], "estimated_days": int(math.ceil(float(ev["days"]))),
                           "hazard_pressure": round(float(ev["hazard"]), 2)})
    return {"profile": dict(p) if p else None, "effects": effects, "current": current, "routes": routes}


def ecology_summary(conn: sqlite3.Connection) -> dict[str, int]:
    q = lambda sql: int(conn.execute(sql).fetchone()[0])
    return {
        "environment_profiles": q("SELECT COUNT(*) FROM location_environment_profiles"),
        "seasonal_windows": q("SELECT COUNT(*) FROM seasonal_windows WHERE status='active'"),
        "environmental_conditions": q("SELECT COUNT(*) FROM environmental_conditions WHERE status='active'"),
        "travel_routes": q("SELECT COUNT(*) FROM travel_routes WHERE status IN ('open','restricted')"),
        "active_travel": q("SELECT COUNT(*) FROM travel_plans WHERE status IN ('active','stalled')"),
        "current_usage_events": q("SELECT COUNT(*) FROM current_usage_events"),
    }
