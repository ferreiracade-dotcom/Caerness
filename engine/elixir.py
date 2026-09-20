from __future__ import annotations

import json
import sqlite3
from typing import Any

from .health import add_condition
from .cultivation import CORE_CAPACITY


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _json(raw: str | None, default):
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def initialize_cultivation_physiology(conn: sqlite3.Connection) -> dict[str, int]:
    """Fill v0.33 fuel physiology for existing profiles without changing canon Stage facts.

    Capacity/reserve are explicitly campaign-calibration runtime quantities. Sediment starts at zero
    only as 'no specific burden seeded', not a claim that every cultivator has historically used clean product.
    """
    rows = conn.execute("SELECT actor_id,core_state,current_stage,core_capacity,current_reserve FROM cultivation_profiles").fetchall()
    changed = 0
    for r in rows:
        if str(r['core_state']) != 'Open-Core':
            cap = reserve = 0.0
        else:
            stage = r['current_stage'] if r['current_stage'] in CORE_CAPACITY else None
            cap = CORE_CAPACITY[stage]
            reserve = cap * 0.60
        if float(r['core_capacity'] or 0) <= 0 and cap > 0:
            conn.execute(
                "UPDATE cultivation_profiles SET core_capacity=?,current_reserve=? WHERE actor_id=?",
                (cap, reserve, int(r['actor_id'])),
            )
            changed += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('cultivation_physiology_calibration','v0.33-stage-relative-neutral')")
    return {'cultivation_physiology_initialized': changed}


def configure_elixir_supply(
    conn: sqlite3.Connection,
    enterprise_id: int,
    product_grade: str,
    *,
    refinement_quality: float,
    sediment_risk: float,
    provenance_standard: float,
    source_basis: str,
    metadata: dict[str, Any] | None = None,
) -> int:
    if product_grade not in {'refined','high_grade'}:
        raise ValueError('Supply profile grade must be refined or high_grade')
    if not conn.execute("SELECT 1 FROM civilian_enterprises WHERE id=?", (enterprise_id,)).fetchone():
        raise ValueError('Unknown enterprise')
    conn.execute(
        """INSERT INTO elixir_supply_profiles(enterprise_id,product_grade,default_refinement_quality,default_sediment_risk,
               provenance_standard,status,source_basis,metadata_json)
           VALUES (?,?,?,?,?,'active',?,?)
           ON CONFLICT(enterprise_id,product_grade) DO UPDATE SET
             default_refinement_quality=excluded.default_refinement_quality,
             default_sediment_risk=excluded.default_sediment_risk,
             provenance_standard=excluded.provenance_standard,status='active',source_basis=excluded.source_basis,
             metadata_json=excluded.metadata_json""",
        (enterprise_id, product_grade, max(0,min(100,float(refinement_quality))), max(0,min(100,float(sediment_risk))),
         max(0,min(100,float(provenance_standard))), source_basis, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(conn.execute("SELECT id FROM elixir_supply_profiles WHERE enterprise_id=? AND product_grade=?", (enterprise_id,product_grade)).fetchone()[0])


def create_elixir_batch(
    conn: sqlite3.Connection,
    batch_key: str,
    product_grade: str,
    *,
    units: float,
    usable_current_per_unit: float,
    refinement_quality: float,
    sediment_risk: float,
    source_location_id: int | None = None,
    refiner_actor_id: int | None = None,
    producer_enterprise_id: int | None = None,
    actual_provenance: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    if product_grade not in {'raw_root','refined','high_grade'}:
        raise ValueError('Unsupported elixir grade')
    if units <= 0 or usable_current_per_unit <= 0:
        raise ValueError('Batch units/current must be positive')
    cur = conn.execute(
        """INSERT INTO elixir_batches(batch_key,product_grade,source_location_id,refiner_actor_id,producer_enterprise_id,
               usable_current_per_unit,refinement_quality,sediment_risk,remaining_units,created_day,status,actual_provenance_json,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,'available',?,?)""",
        (batch_key,product_grade,source_location_id,refiner_actor_id,producer_enterprise_id,float(usable_current_per_unit),
         max(0,min(100,float(refinement_quality))),max(0,min(100,float(sediment_risk))),float(units),_day(conn),
         json.dumps(actual_provenance or {},sort_keys=True),json.dumps(metadata or {},sort_keys=True)),
    )
    return int(cur.lastrowid)


def refine_batch_from_root_stock(
    conn: sqlite3.Connection,
    batch_key: str,
    *,
    enterprise_id: int,
    stock_id: int,
    root_units: float,
    product_grade: str = 'refined',
    refinement_quality: float = 70,
    sediment_risk: float = 5,
    actual_provenance: dict[str, Any] | None = None,
) -> int:
    """Consume existing Vein-Root commercial stock once and create a traceable refined batch."""
    if product_grade not in {'refined','high_grade'}:
        raise ValueError('Refinement output must be refined or high_grade')
    if root_units <= 0:
        raise ValueError('root_units must be positive')
    if conn.execute("SELECT 1 FROM elixir_batches WHERE batch_key=?", (batch_key,)).fetchone():
        raise ValueError('Batch key already exists; refinement cannot be replayed')
    stock = conn.execute(
        """SELECT cs.*,mg.good_key,e.location_id AS enterprise_location
           FROM commercial_stock cs JOIN market_goods mg ON mg.id=cs.good_id
           JOIN civilian_enterprises e ON e.id=cs.enterprise_id WHERE cs.id=?""", (stock_id,)
    ).fetchone()
    if not stock or int(stock['enterprise_id']) != int(enterprise_id):
        raise ValueError('Root stock does not belong to producer enterprise')
    if str(stock['good_key']) != 'vein-root':
        raise ValueError('Refinement requires Vein-Root stock')
    if float(stock['quantity']) + 1e-9 < float(root_units):
        raise ValueError('Insufficient Vein-Root stock')
    supply = conn.execute(
        "SELECT * FROM elixir_supply_profiles WHERE enterprise_id=? AND product_grade=? AND status='active'",
        (enterprise_id,product_grade),
    ).fetchone()
    if not supply:
        raise ValueError('Enterprise lacks an active elixir supply/refining profile for this grade')
    # Output yield is simulation calibration, not an in-world conversion law. High-grade output is scarcer.
    yield_factor = 0.80 if product_grade == 'refined' else 0.42
    output_units = float(root_units) * yield_factor
    current_per = (8.0 if product_grade == 'refined' else 16.0) * (0.75 + max(0,min(100,float(refinement_quality)))/400.0)
    conn.execute("UPDATE commercial_stock SET quantity=quantity-?,updated_day=? WHERE id=?", (float(root_units),_day(conn),stock_id))
    prov = dict(actual_provenance or {})
    prov.setdefault('input_stock_id', int(stock_id)); prov.setdefault('root_units_consumed', float(root_units))
    prov.setdefault('source_location_id', int(stock['location_id']))
    return create_elixir_batch(
        conn,batch_key,product_grade,units=output_units,usable_current_per_unit=current_per,
        refinement_quality=refinement_quality,sediment_risk=sediment_risk,
        source_location_id=int(stock['location_id']),producer_enterprise_id=enterprise_id,actual_provenance=prov,
        metadata={'authority':'SIMULATION_EVENT','yield_factor':yield_factor,'yield_status':'CAMPAIGN_CALIBRATION'},
    )


def add_batch_claim(
    conn: sqlite3.Connection,
    batch_id: int,
    claim_kind: str,
    claim_text: str,
    *,
    claimant_actor_id: int | None = None,
    confidence: float = 50,
    truth_status: str = 'unknown',
    metadata: dict[str, Any] | None = None,
) -> int:
    if truth_status not in {'unknown','supported','false','disputed'}:
        raise ValueError('Invalid truth status')
    if not conn.execute("SELECT 1 FROM elixir_batches WHERE id=?", (batch_id,)).fetchone():
        raise ValueError('Unknown batch')
    cur=conn.execute(
        """INSERT INTO elixir_batch_claims(batch_id,day,claimant_actor_id,claim_kind,claim_text,confidence,truth_status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (batch_id,_day(conn),claimant_actor_id,claim_kind,claim_text,max(0,min(100,float(confidence))),truth_status,
         json.dumps(metadata or {},sort_keys=True)),
    )
    return int(cur.lastrowid)


def consume_elixir(conn: sqlite3.Connection, actor_id: int, batch_id: int, units: float) -> dict[str, Any]:
    """Apply traceable cultivation fuel without granting Realization.

    Clean refined product is safe under ordinary assimilation. Sediment comes from batch risk; Rupture comes
    from physiological overload, not from the mere fact that the product is an elixir.
    """
    if units <= 0:
        raise ValueError('units must be positive')
    live=conn.execute("SELECT a.status,lp.life_status FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?",(actor_id,)).fetchone()
    if not live or str(live[0])!='active' or (live[1] is not None and str(live[1])!='living'):
        raise ValueError('Elixir consumption requires a living active actor')
    p=conn.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if not p or str(p['core_state'])!='Open-Core':
        raise ValueError('Cultivation-fuel assimilation requires an Open Core')
    b=conn.execute("SELECT * FROM elixir_batches WHERE id=?",(batch_id,)).fetchone()
    if not b or str(b['status'])!='available' or float(b['remaining_units'])+1e-9<float(units):
        raise ValueError('Batch unavailable or insufficient')

    quality=float(b['refinement_quality']); risk=float(b['sediment_risk'])
    assimilated=float(units)*float(b['usable_current_per_unit'])*(0.65+0.003*quality)
    capacity=max(1.0,float(p['core_capacity'])); reserve=float(p['current_reserve'])
    room=max(0.0,capacity-reserve)
    reserve_target=assimilated*0.80
    reserve_gain=min(room,reserve_target)
    adaptation_current=max(0.0,assimilated-reserve_gain)*0.35
    vessel_gain=min(3.0,(adaptation_current/capacity)*5.0) if int(p['active']) else 0.0
    sediment_gain=float(units)*(risk/100.0)*3.0
    new_sediment=min(100.0,float(p['sediment_burden'])+sediment_gain)

    # Overload is current delivered beyond normal storage/adaptation tolerance. It is independent of dirtiness:
    # even a perfectly clean huge dose can rupture an underdeveloped Vessel.
    tolerance=room + capacity*0.35
    overload=max(0.0,assimilated-tolerance)
    rupture_id=None
    if overload > capacity*0.50:
        severity=min(78.0,18.0 + 42.0*(overload/capacity) + new_sediment*0.08)
        rupture_id=add_condition(
            conn,actor_id,'rupture','Elixir Assimilation Rupture',severity=severity,body_system='Vessel/Channels',
            capacity_impact=severity*0.65,pain_impact=severity*0.5,recovery_rate_per_30=1.2,
            specialist_requirement='vein_mender',metadata={'cause':'excessive_elixir_assimilation','batch_id':batch_id,'overload':overload},
        )
        conn.execute("UPDATE cultivation_profiles SET injury_constraint=MIN(100,injury_constraint+?) WHERE actor_id=?",(severity*0.7,actor_id))
        conn.execute(
            """INSERT INTO cultivation_history(actor_id,day,history_kind,stage_before,stage_after,summary,vessel_snapshot,realization_snapshot,metadata_json)
               VALUES (?,?,'rupture',?,?,?, ?,?,?)""",
            (actor_id,_day(conn),p['current_stage'],p['current_stage'],'Excessive elixir assimilation caused anatomical Rupture.',
             float(p['vessel_adaptation']),float(p['realization_integration']),json.dumps({'batch_id':batch_id,'health_condition_id':rupture_id},sort_keys=True)),
        )

    new_reserve=min(capacity,reserve+reserve_gain)
    new_vessel=min(100.0,float(p['vessel_adaptation'])+vessel_gain)
    # Realization deliberately unchanged.
    conn.execute(
        "UPDATE cultivation_profiles SET current_reserve=?,vessel_adaptation=?,sediment_burden=? WHERE actor_id=?",
        (new_reserve,new_vessel,new_sediment,actor_id),
    )
    remaining=max(0.0,float(b['remaining_units'])-float(units))
    conn.execute("UPDATE elixir_batches SET remaining_units=?,status=? WHERE id=?",(remaining,'depleted' if remaining<=1e-9 else 'available',batch_id))
    cur=conn.execute(
        """INSERT INTO elixir_exposures(batch_id,actor_id,day,units_consumed,assimilated_current,reserve_gain,vessel_gain,sediment_gain,rupture_condition_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (batch_id,actor_id,_day(conn),float(units),assimilated,reserve_gain,vessel_gain,sediment_gain,rupture_id,
         json.dumps({'realization_gain':0.0,'quality':quality,'sediment_risk':risk,'overload':overload},sort_keys=True)),
    )
    return {'exposure_id':int(cur.lastrowid),'assimilated_current':assimilated,'reserve_gain':reserve_gain,
            'vessel_gain':vessel_gain,'sediment_gain':sediment_gain,'rupture_condition_id':rupture_id,'remaining_units':remaining}


def elixir_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        'supply_profiles':int(conn.execute("SELECT COUNT(*) FROM elixir_supply_profiles WHERE status='active'").fetchone()[0]),
        'batches':int(conn.execute("SELECT COUNT(*) FROM elixir_batches").fetchone()[0]),
        'available_batches':int(conn.execute("SELECT COUNT(*) FROM elixir_batches WHERE status='available'").fetchone()[0]),
        'claims':int(conn.execute("SELECT COUNT(*) FROM elixir_batch_claims").fetchone()[0]),
        'exposures':int(conn.execute("SELECT COUNT(*) FROM elixir_exposures").fetchone()[0]),
        'sediment_exposures':int(conn.execute("SELECT COUNT(*) FROM elixir_exposures WHERE sediment_gain>0").fetchone()[0]),
        'ruptures':int(conn.execute("SELECT COUNT(*) FROM elixir_exposures WHERE rupture_condition_id IS NOT NULL").fetchone()[0]),
    }
