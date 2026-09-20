from __future__ import annotations

import json
import math
import sqlite3
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _next_harvest_day(current_day: int, day_of_year: int, *, allow_today: bool = False) -> int:
    year = current_day // 365
    candidate = year * 365 + int(day_of_year)
    if candidate < current_day or (candidate == current_day and not allow_today):
        candidate += 365
    return candidate


def create_field(conn: sqlite3.Connection, field_key: str, name: str, *, enterprise_id: int,
                 location_id: int, crop_good_id: int, hectares: float, base_yield_per_hectare: float,
                 soil_quality: float = 70, labor_capacity: float = 70, harvest_day_of_year: int = 270,
                 next_harvest_day: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    if hectares <= 0 or base_yield_per_hectare < 0:
        raise ValueError("field size/yield invalid")
    day = _day(conn)
    next_day = _next_harvest_day(day, harvest_day_of_year) if next_harvest_day is None else int(next_harvest_day)
    cur = conn.execute(
        """INSERT INTO agriculture_fields(field_key,name,enterprise_id,location_id,crop_good_id,hectares,
               base_yield_per_hectare,soil_quality,labor_capacity,harvest_day_of_year,next_harvest_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (field_key, name, enterprise_id, location_id, crop_good_id, float(hectares), float(base_yield_per_hectare),
         max(0,min(100,float(soil_quality))), max(0,min(100,float(labor_capacity))), int(harvest_day_of_year),
         next_day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def add_disruption(conn: sqlite3.Connection, field_id: int, disruption_kind: str, *, start_day: int | None = None,
                   end_day: int | None = None, yield_factor: float = 0.5, source_kind: str | None = None,
                   source_id: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn) if start_day is None else int(start_day)
    if end_day is not None and int(end_day) < day:
        raise ValueError("end_day cannot precede start_day")
    cur = conn.execute(
        """INSERT INTO agriculture_disruptions(field_id,disruption_kind,start_day,end_day,yield_factor,source_kind,source_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (field_id, disruption_kind, day, end_day, max(0,min(1,float(yield_factor))), source_kind, source_id,
         json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _disruption_factor(conn: sqlite3.Connection, field_id: int, day: int) -> float:
    rows = conn.execute(
        """SELECT yield_factor FROM agriculture_disruptions WHERE field_id=? AND start_day<=?
           AND (end_day IS NULL OR end_day>=?) ORDER BY id""", (field_id, day, day)
    ).fetchall()
    factor = 1.0
    for r in rows:
        factor *= float(r[0])
    return max(0.0, min(1.0, factor))


def _stock_upsert(conn: sqlite3.Connection, enterprise_id: int, location_id: int, good_id: int, quantity: float, day: int) -> int:
    row = conn.execute(
        "SELECT id FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",
        (enterprise_id, location_id, good_id),
    ).fetchone()
    if row:
        sid = int(row[0])
        conn.execute("UPDATE commercial_stock SET quantity=quantity+?,updated_day=? WHERE id=?", (quantity, day, sid))
        return sid
    cur = conn.execute(
        "INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json) VALUES (?,?,?,?,?,'{}')",
        (enterprise_id, location_id, good_id, quantity, day),
    )
    return int(cur.lastrowid)


def _ensure_market(conn: sqlite3.Connection, location_id: int, good_id: int, day: int) -> None:
    if conn.execute("SELECT 1 FROM market_conditions WHERE location_id=? AND good_id=?", (location_id,good_id)).fetchone():
        return
    base = conn.execute("SELECT base_price FROM market_goods WHERE id=?", (good_id,)).fetchone()
    if not base:
        raise ValueError("unknown crop good")
    conn.execute(
        """INSERT INTO market_conditions(location_id,good_id,supply,demand,current_price,last_review_day,next_review_day)
           VALUES (?,?,50,50,?,?,?)""", (location_id,good_id,float(base[0]),day,day+30)
    )


def _resolve_field(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> dict[str, Any]:
    from .ecology import production_factor
    from .merchant import apply_supply_shock

    expected = float(row['hectares']) * float(row['base_yield_per_hectare']) * max(.15,float(row['soil_quality'])/100.0)
    ent = conn.execute("SELECT labor_capacity FROM civilian_enterprises WHERE id=?", (int(row['enterprise_id']),)).fetchone()
    labor = min(float(row['labor_capacity']), float(ent[0]) if ent else 50.0) / 100.0
    ecology = max(0.0, float(production_factor(conn, int(row['location_id']), day, 'food')))
    disruption = _disruption_factor(conn, int(row['id']), day)
    actual = max(0.0, expected * labor * ecology * disruption)
    stock_id = _stock_upsert(conn, int(row['enterprise_id']), int(row['location_id']), int(row['crop_good_id']), actual, day)
    cur = conn.execute(
        """INSERT INTO agriculture_harvests(field_id,harvest_day,expected_quantity,actual_quantity,ecology_factor,labor_factor,
               disruption_factor,stock_id,metadata_json) VALUES (?,?,?,?,?,?,?,?,?)""",
        (int(row['id']),day,expected,actual,ecology,labor,disruption,stock_id,
         json.dumps({'yield_ratio': (actual/expected if expected>0 else 0)}, sort_keys=True)),
    )
    _ensure_market(conn, int(row['location_id']), int(row['crop_good_id']), day)
    ratio = actual / expected if expected > 0 else 1.0
    # Market supply is an abstract local availability index; shift it by deviation from a normal harvest,
    # while the physical crop itself lives in commercial_stock.
    supply_delta = (ratio - 1.0) * 35.0 + min(8.0, ratio * 4.0)
    apply_supply_shock(conn, int(row['location_id']), int(row['crop_good_id']), supply_delta,
                       source=f"agriculture_harvest:{int(cur.lastrowid)}")
    next_day = _next_harvest_day(day, int(row['harvest_day_of_year']))
    conn.execute("UPDATE agriculture_fields SET last_harvest_day=?,next_harvest_day=?,status=? WHERE id=?",
                 (day,next_day,'damaged' if disruption < .45 else 'active',int(row['id'])))
    return {'field_id':int(row['id']),'harvest_id':int(cur.lastrowid),'expected':expected,'actual':actual,
            'yield_ratio':ratio,'stock_id':stock_id,'supply_delta':supply_delta}


def next_agriculture_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    r = conn.execute(
        "SELECT MIN(next_harvest_day) FROM agriculture_fields WHERE status IN ('active','damaged') AND next_harvest_day>? AND next_harvest_day<=?",
        (after_day,end_day),
    ).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def process_due_agriculture(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT * FROM agriculture_fields WHERE status IN ('active','damaged') AND next_harvest_day<=? ORDER BY next_harvest_day,id", (day,)
    ).fetchall()
    resolved = [_resolve_field(conn,r,day) for r in rows]
    return {'harvests':len(resolved),'poor_harvests':sum(1 for x in resolved if x['yield_ratio']<.7),
            'quantity':round(sum(x['actual'] for x in resolved),3)}


def agriculture_summary(conn: sqlite3.Connection) -> dict[str, int | float]:
    return {
        'fields': int(conn.execute("SELECT COUNT(*) FROM agriculture_fields WHERE status IN ('active','damaged','fallow')").fetchone()[0]),
        'harvests': int(conn.execute("SELECT COUNT(*) FROM agriculture_harvests").fetchone()[0]),
        'disruptions': int(conn.execute("SELECT COUNT(*) FROM agriculture_disruptions").fetchone()[0]),
    }
