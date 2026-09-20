from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from .scale import OWNER_TO_BUCKET, POPULATION_BUCKETS

# Ordinary/background goods only. Cultivation resources and named strategic lots remain on the
# tracked material/merchant path rather than being silently commoditized at population scale.
REPRESENTATIVE_HUBS = {
    "underheaven": "Cairnholt",
    "dunmoor": "Northmarch",
    "greywood": "Eldenfell",
    "sunreach": "Sunreach",
    "windmere": "Saltmere",
    "thornward": "Westgate",
    "stormhollow": "Stormhollow",
}

GOOD_CALIBRATION: dict[str, tuple[float, dict[str, float]]] = {
    # monthly per-capita bulk-equivalent demand, production factor by population bucket
    "ordinary-grain": (1.00, {
        "underheaven": 1.06, "dunmoor": .96, "greywood": .97, "sunreach": 1.16,
        "windmere": .96, "thornward": 1.05, "stormhollow": .86, "independent_frontier": 1.00,
    }),
    "ordinary-cloth": (.080, {
        "underheaven": 1.09, "dunmoor": .91, "greywood": .96, "sunreach": 1.06,
        "windmere": 1.08, "thornward": .91, "stormhollow": .86, "independent_frontier": .82,
    }),
    "ordinary-timber": (.040, {
        "underheaven": .93, "dunmoor": 1.08, "greywood": 1.32, "sunreach": .83,
        "windmere": 1.14, "thornward": 1.03, "stormhollow": .94, "independent_frontier": 1.10,
    }),
    "ordinary-medicine": (.012, {
        "underheaven": 1.08, "dunmoor": .86, "greywood": .92, "sunreach": .87,
        "windmere": 1.02, "thornward": .82, "stormhollow": .80, "independent_frontier": .76,
    }),
    "metalwork": (.018, {
        "underheaven": 1.08, "dunmoor": 1.08, "greywood": .88, "sunreach": .88,
        "windmere": 1.02, "thornward": .94, "stormhollow": 1.18, "independent_frontier": .86,
    }),
    "travel-supplies": (.025, {
        "underheaven": 1.10, "dunmoor": .92, "greywood": .92, "sunreach": 1.02,
        "windmere": 1.18, "thornward": .84, "stormhollow": .88, "independent_frontier": 1.04,
    }),
    "naval-supplies": (.004, {
        "underheaven": .78, "dunmoor": .50, "greywood": .62, "sunreach": .95,
        "windmere": 1.55, "thornward": .56, "stormhollow": .56, "independent_frontier": .68,
    }),
}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def bucket_for_location(conn: sqlite3.Connection, location_id: int) -> str | None:
    row = conn.execute("SELECT bucket_key FROM settlement_scale_profiles WHERE location_id=?", (location_id,)).fetchone()
    if row:
        return str(row[0])
    owner = conn.execute("SELECT political_owner FROM locations WHERE id=?", (location_id,)).fetchone()
    if owner and owner[0]:
        return OWNER_TO_BUCKET.get(str(owner[0]))
    return None


def _ensure_ordinary_markets(conn: sqlite3.Connection) -> int:
    """Give each resolved named settlement an aggregate ordinary market book.

    This does not assert a named market institution or local manufacture. It is the low-resolution
    price/supply interface for ordinary goods consumed by the represented population.
    """
    day = _day(conn)
    created = 0
    goods = {str(r["good_key"]): r for r in conn.execute(
        "SELECT id,good_key,base_price FROM market_goods WHERE good_key IN (%s)" % ",".join("?" for _ in GOOD_CALIBRATION),
        tuple(GOOD_CALIBRATION.keys()),
    ).fetchall()}
    settlements = conn.execute("SELECT location_id FROM settlement_scale_profiles ORDER BY location_id").fetchall()
    for sr in settlements:
        lid = int(sr[0])
        for key in GOOD_CALIBRATION:
            g = goods.get(key)
            if not g:
                continue
            exists = conn.execute("SELECT 1 FROM market_conditions WHERE location_id=? AND good_id=?", (lid, int(g["id"]))).fetchone()
            if exists:
                continue
            conn.execute(
                """INSERT INTO market_conditions(location_id,good_id,supply,demand,transport_pressure,risk_pressure,tax_pressure,
                       current_price,last_review_day,next_review_day,metadata_json)
                   VALUES (?,?,65,65,5,3,5,?,?,?,?)""",
                (lid, int(g["id"]), float(g["base_price"]), day, day + 30, json.dumps({
                    "authority": "TRADE01_AGGREGATE_MARKET",
                    "aggregate_market_only": True,
                    "does_not_imply_named_market_institution": True,
                }, sort_keys=True)),
            )
            created += 1
    return created


def activate_aggregate_trade(conn: sqlite3.Connection) -> dict[str, int]:
    day = _day(conn)
    goods = {str(r["good_key"]): (int(r["id"]), float(r["base_price"])) for r in conn.execute(
        "SELECT id,good_key,base_price FROM market_goods WHERE good_key IN (%s)" % ",".join("?" for _ in GOOD_CALIBRATION),
        tuple(GOOD_CALIBRATION.keys()),
    ).fetchall()}
    profiles = reserves = 0
    for good_key, (consumption, factors) in GOOD_CALIBRATION.items():
        if good_key not in goods:
            continue
        gid = goods[good_key][0]
        for bucket_key, (_, population, _) in POPULATION_BUCKETS.items():
            factor = float(factors[bucket_key])
            conn.execute(
                """INSERT INTO aggregate_trade_profiles(bucket_key,good_id,monthly_consumption_per_capita,production_factor,reserve_target_months,metadata_json)
                   VALUES (?,?,?,?,.05,?) ON CONFLICT(bucket_key,good_id) DO UPDATE SET
                     monthly_consumption_per_capita=excluded.monthly_consumption_per_capita,
                     production_factor=excluded.production_factor,reserve_target_months=excluded.reserve_target_months,
                     metadata_json=excluded.metadata_json""",
                (bucket_key, gid, consumption, factor, json.dumps({
                    "authority":"TRADE01_CAMPAIGN_CALIBRATION",
                    "quantity_unit":"abstract bulk-equivalent unit",
                    "not_canon_consumption_statistic":True,
                }, sort_keys=True)),
            )
            profiles += 1
            demand = population * consumption
            target = demand * .05
            if not conn.execute("SELECT 1 FROM aggregate_trade_reserves WHERE bucket_key=? AND good_id=?", (bucket_key, gid)).fetchone():
                conn.execute("INSERT INTO aggregate_trade_reserves(bucket_key,good_id,quantity,updated_day) VALUES (?,?,?,?)",
                             (bucket_key, gid, target, day))
                reserves += 1
    market_rows = _ensure_ordinary_markets(conn)

    # Crystallized route geography outranks aggregate geography. Record only pairs whose
    # representative hubs are currently connected through the authoritative route graph.
    # If one of these corridors later closes, TRADE-01 may not silently fall back to teleportation.
    corridor_rows = 0
    try:
        from .ecology import find_route_path
        hubs: dict[str, int] = {}
        for bucket_key, name in REPRESENTATIVE_HUBS.items():
            row = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
            if row:
                hubs[bucket_key] = int(row[0])
        keys = sorted(hubs)
        for i, a in enumerate(keys):
            for b in keys[i+1:]:
                path = find_route_path(conn, hubs[a], hubs[b], day=day)
                if not path:
                    continue
                conn.execute(
                    """INSERT INTO aggregate_trade_corridors(bucket_a,bucket_b,location_a_id,location_b_id,route_resolution,metadata_json)
                       VALUES (?,?,?,?, 'tracked_route', ?) ON CONFLICT(bucket_a,bucket_b) DO UPDATE SET
                         location_a_id=excluded.location_a_id,location_b_id=excluded.location_b_id,metadata_json=excluded.metadata_json""",
                    (a,b,hubs[a],hubs[b],json.dumps({"authority":"TRADE01_DERIVED_FROM_ROUTE_GRAPH","activation_path":list(map(int,path))},sort_keys=True)),
                )
                corridor_rows += 1
    except Exception:
        corridor_rows = 0

    if not conn.execute("SELECT 1 FROM engine_meta WHERE key='aggregate_trade_next_cycle_day'").fetchone():
        conn.execute("INSERT INTO engine_meta(key,value) VALUES ('aggregate_trade_next_cycle_day',?)", (str(day + 1),))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('trade01_activation_version','1')")
    return {"aggregate_trade_profiles": profiles, "aggregate_trade_reserves_created": reserves,
            "aggregate_market_rows_created": market_rows, "aggregate_trade_tracked_corridors": corridor_rows}


def next_aggregate_trade_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    row = conn.execute("SELECT value FROM engine_meta WHERE key='aggregate_trade_next_cycle_day'").fetchone()
    if not row:
        return None
    try:
        due = int(row[0])
    except (TypeError, ValueError):
        return None
    return due if after_day < due <= end_day else None


def _transport_context(conn: sqlite3.Connection, good_id: int, origin: str, destination: str, day: int) -> dict[str, Any]:
    per = conn.execute("SELECT perishability FROM market_goods WHERE id=?", (good_id,)).fetchone()
    perishability = float(per[0] if per else 0.0)
    a,b = sorted((origin,destination))
    corridor = conn.execute("SELECT * FROM aggregate_trade_corridors WHERE bucket_a=? AND bucket_b=?", (a,b)).fetchone()
    if corridor:
        from .ecology import find_route_path, evaluate_route_leg
        if origin == a:
            start,end = int(corridor['location_a_id']),int(corridor['location_b_id'])
        else:
            start,end = int(corridor['location_b_id']),int(corridor['location_a_id'])
        path = find_route_path(conn,start,end,day=day)
        if not path:
            return {"usable":False,"resolution":"tracked_route","loss_rate":0.0,"cost":math.inf,"path":[]}
        current=start; hazard=0.0; days=0.0; accessibility=100.0
        for rid in path:
            ev=evaluate_route_leg(conn,int(rid),current,day=day)
            if not ev.get('usable'):
                return {"usable":False,"resolution":"tracked_route","loss_rate":0.0,"cost":math.inf,"path":list(map(int,path))}
            hazard=max(hazard,float(ev.get('hazard',0.0))); days+=float(ev.get('days',0.0)); accessibility=min(accessibility,float(ev.get('accessibility',100.0)))
            current=int(ev['target'])
        loss=min(.15,.003 + perishability*.03 + hazard/2500.0 + max(0.0,100.0-accessibility)/5000.0)
        return {"usable":True,"resolution":"tracked_route","loss_rate":loss,"cost":1.0+days/30.0+hazard/200.0,"path":list(map(int,path))}
    # No exact cross-bucket route has been crystallized. Low-resolution circulation is allowed,
    # but it cannot be used as evidence that any particular road/river/port connection exists.
    loss=min(.08,.010 + perishability*.035)
    return {"usable":True,"resolution":"aggregate_macro","loss_rate":loss,"cost":1.0+loss*5.0,"path":[]}


def _update_market_projection(conn: sqlite3.Connection, period_day: int) -> int:
    rows = conn.execute(
        """SELECT b.bucket_key,b.good_id,b.consumption_requirement,b.local_absorption,b.import_quantity,
                  b.unmet_demand,b.closing_reserve,g.base_price
           FROM aggregate_trade_balances b JOIN market_goods g ON g.id=b.good_id
           WHERE b.period_day=?""", (period_day,)
    ).fetchall()
    by_key = {(str(r["bucket_key"]), int(r["good_id"])): r for r in rows}
    changed = 0
    markets = conn.execute(
        """SELECT mc.location_id,mc.good_id,mc.supply,mc.demand,mc.current_price,mc.metadata_json
           FROM market_conditions mc ORDER BY mc.location_id,mc.good_id"""
    ).fetchall()
    for mc in markets:
        bucket = bucket_for_location(conn, int(mc["location_id"]))
        if not bucket:
            continue
        bal = by_key.get((bucket, int(mc["good_id"])))
        if not bal:
            continue
        need = max(1e-9, float(bal["consumption_requirement"]))
        covered = min(1.0, (float(bal["local_absorption"]) + float(bal["import_quantity"])) / need)
        unmet = min(1.0, float(bal["unmet_demand"]) / need)
        reserve_ratio = min(.5, float(bal["closing_reserve"]) / need)
        target_supply = _clamp(25 + covered * 70 + reserve_ratio * 20 - unmet * 30)
        target_demand = _clamp(55 + unmet * 45)
        supply = _clamp(float(mc["supply"]) * .55 + target_supply * .45)
        demand = _clamp(float(mc["demand"]) * .65 + target_demand * .35)
        target_price = float(bal["base_price"]) * max(.55, 1.0 + unmet * 1.4 - reserve_ratio * .22)
        price = max(.01, float(mc["current_price"]) * .60 + target_price * .40)
        try:
            meta = json.loads(mc["metadata_json"] or "{}")
        except Exception:
            meta = {}
        meta.update({"trade01_projection_day": period_day, "aggregate_coverage": round(covered, 6),
                     "aggregate_unmet_ratio": round(unmet, 6)})
        conn.execute(
            "UPDATE market_conditions SET supply=?,demand=?,current_price=?,last_review_day=?,next_review_day=?,metadata_json=? WHERE location_id=? AND good_id=?",
            (supply, demand, price, period_day, period_day + 30, json.dumps(meta, sort_keys=True), int(mc["location_id"]), int(mc["good_id"])),
        )
        changed += 1
    return changed


def process_due_aggregate_trade(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict[str, int | float]:
    row = conn.execute("SELECT value FROM engine_meta WHERE key='aggregate_trade_next_cycle_day'").fetchone()
    if not row or int(row[0]) > day:
        return {"aggregate_trade_cycles": 0, "aggregate_trade_flows": 0, "aggregate_market_updates": 0}

    # Re-running the same due day is idempotent: delete only this derived period and rebuild it
    # from the authoritative opening reserve/profile state as it exists at the call boundary.
    if conn.execute("SELECT 1 FROM aggregate_trade_balances WHERE period_day=? LIMIT 1", (day,)).fetchone():
        conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('aggregate_trade_next_cycle_day',?)", (str(day + 30),))
        return {"aggregate_trade_cycles": 0, "aggregate_trade_flows": 0, "aggregate_market_updates": 0}

    profiles = conn.execute(
        """SELECT p.*,b.population_estimate,g.good_key,g.perishability
           FROM aggregate_trade_profiles p JOIN population_scale_buckets b ON b.bucket_key=p.bucket_key
           JOIN market_goods g ON g.id=p.good_id ORDER BY p.good_id,p.bucket_key"""
    ).fetchall()
    from .background_population import current_bucket_population
    state: dict[tuple[str, int], dict[str, float]] = {}
    for p in profiles:
        bucket = str(p["bucket_key"]); gid = int(p["good_id"])
        # POPLIFE-01 live population may causally diverge from the opening SCALE-01 anchor.
        pop = current_bucket_population(conn, bucket) or int(p["population_estimate"])
        reserve_row = conn.execute("SELECT quantity FROM aggregate_trade_reserves WHERE bucket_key=? AND good_id=?", (bucket, gid)).fetchone()
        opening = float(reserve_row[0] if reserve_row else 0.0)
        demand = pop * float(p["monthly_consumption_per_capita"])
        production = demand * float(p["production_factor"])
        available = opening + production
        local = min(demand, available)
        deficit = max(0.0, demand - local)
        target_reserve = demand * float(p["reserve_target_months"])
        exportable = max(0.0, available - local - target_reserve)
        state[(bucket, gid)] = {
            "population": float(pop), "opening": opening, "production": production, "demand": demand,
            "local": local, "deficit": deficit, "exportable": exportable, "imports": 0.0,
            "exports": 0.0, "losses": 0.0, "target_reserve": target_reserve,
        }

    flow_count = 0
    goods = sorted({gid for _, gid in state})
    for gid in goods:
        exporters = [(b, s) for (b, g), s in state.items() if g == gid and s["exportable"] > 1e-9]
        importers = [(b, s) for (b, g), s in state.items() if g == gid and s["deficit"] > 1e-9]
        # Biggest shortages first; then stable bucket-key order. This is a deterministic macro
        # clearing rule, not actor omniscience or a claim about one physical route.
        importers.sort(key=lambda x: (-x[1]["deficit"] / max(1.0, x[1]["demand"]), x[0]))
        exporters.sort(key=lambda x: (-x[1]["exportable"], x[0]))
        for dest, ds in importers:
            remaining = ds["deficit"] - ds["imports"]
            if remaining <= 1e-9:
                continue
            for origin, os in exporters:
                if origin == dest:
                    continue
                available = os["exportable"] - os["exports"]
                if available <= 1e-9:
                    continue
                transport = _transport_context(conn, gid, origin, dest, day)
                if not transport["usable"]:
                    continue
                loss_rate = float(transport["loss_rate"])
                dispatch_needed = remaining / max(1e-9, 1.0 - loss_rate)
                dispatched = min(available, dispatch_needed)
                if dispatched <= 1e-9:
                    continue
                loss = dispatched * loss_rate
                delivered = dispatched - loss
                conn.execute(
                    """INSERT INTO aggregate_trade_flows(period_day,origin_bucket_key,destination_bucket_key,good_id,
                           dispatched_quantity,delivered_quantity,loss_quantity,transport_cost_index,route_resolution,metadata_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (day, origin, dest, gid, dispatched, delivered, loss, float(transport["cost"]),
                     str(transport["resolution"]), json.dumps({"authority":"TRADE01_DERIVED",
                                 "exact_route_not_asserted": str(transport["resolution"]) != "tracked_route",
                                 "route_ids": transport["path"],
                                 "tracked_contracts_are_crystallized_sample_not_additive":True}, sort_keys=True)),
                )
                os["exports"] += dispatched; os["losses"] += loss; ds["imports"] += delivered
                remaining -= delivered; flow_count += 1
                if remaining <= 1e-9:
                    break

    total_dispatched = total_delivered = total_loss = total_unmet = 0.0
    for (bucket, gid), s in state.items():
        closing = max(0.0, s["opening"] + s["production"] - s["local"] - s["exports"])
        unmet = max(0.0, s["demand"] - s["local"] - s["imports"])
        unused = max(0.0, closing - s["target_reserve"])
        conn.execute(
            """INSERT INTO aggregate_trade_balances(period_day,bucket_key,good_id,population_served,opening_reserve,
                   production_quantity,consumption_requirement,local_absorption,import_quantity,export_quantity,
                   transport_loss,closing_reserve,unmet_demand,unused_surplus,metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (day, bucket, gid, int(s["population"]), s["opening"], s["production"], s["demand"], s["local"],
             s["imports"], s["exports"], s["losses"], closing, unmet, unused,
             json.dumps({"authority":"TRADE01_DERIVED","resolution":"regional_bulk"}, sort_keys=True)),
        )
        conn.execute(
            """INSERT INTO aggregate_trade_reserves(bucket_key,good_id,quantity,updated_day) VALUES (?,?,?,?)
               ON CONFLICT(bucket_key,good_id) DO UPDATE SET quantity=excluded.quantity,updated_day=excluded.updated_day""",
            (bucket, gid, closing, day),
        )
        total_unmet += unmet
    fr = conn.execute("SELECT COALESCE(SUM(dispatched_quantity),0),COALESCE(SUM(delivered_quantity),0),COALESCE(SUM(loss_quantity),0) FROM aggregate_trade_flows WHERE period_day=?", (day,)).fetchone()
    total_dispatched, total_delivered, total_loss = map(float, fr)
    updates = _update_market_projection(conn, day)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('aggregate_trade_next_cycle_day',?)", (str(day + 30),))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('aggregate_trade_last_cycle_day',?)", (str(day),))
    if event_logger and (total_unmet > 1e-6 or total_loss > 1e-6):
        event_logger(day=day,event_type="economy:aggregate_trade_cycle",title="Ordinary trade cycle cleared",
                     summary=f"Background markets moved {total_delivered:.0f} bulk-equivalent units with {total_loss:.0f} explicit transport loss and {total_unmet:.0f} unmet demand.",severity=1)
    return {"aggregate_trade_cycles": 1, "aggregate_trade_flows": flow_count,
            "aggregate_market_updates": updates, "aggregate_dispatched": round(total_dispatched, 3),
            "aggregate_delivered": round(total_delivered, 3), "aggregate_transport_loss": round(total_loss, 3),
            "aggregate_unmet_demand": round(total_unmet, 3)}


def aggregate_trade_snapshot(conn: sqlite3.Connection, *, day: int | None = None) -> dict[str, Any]:
    if day is None:
        row = conn.execute("SELECT MAX(period_day) FROM aggregate_trade_balances").fetchone()
        if not row or row[0] is None:
            return {"period_day": None, "flows": 0, "dispatched": 0.0, "delivered": 0.0, "loss": 0.0, "unmet": 0.0}
        day = int(row[0])
    f = conn.execute("SELECT COUNT(*),COALESCE(SUM(dispatched_quantity),0),COALESCE(SUM(delivered_quantity),0),COALESCE(SUM(loss_quantity),0) FROM aggregate_trade_flows WHERE period_day=?", (day,)).fetchone()
    b = conn.execute("SELECT COALESCE(SUM(unmet_demand),0),COALESCE(SUM(consumption_requirement),0) FROM aggregate_trade_balances WHERE period_day=?", (day,)).fetchone()
    return {"period_day": day, "flows": int(f[0]), "dispatched": round(float(f[1]),3), "delivered": round(float(f[2]),3),
            "loss": round(float(f[3]),3), "unmet": round(float(b[0]),3), "consumption_requirement": round(float(b[1]),3)}
