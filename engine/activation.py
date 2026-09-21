from __future__ import annotations

import json
import sqlite3
from typing import Any

from .business import configure_enterprise_business, set_commercial_context
from .civilian import (
    add_production_site,
    create_auction,
    create_cultural_object,
    create_enterprise,
    ensure_good,
    set_market_condition,
)
from .civilian_life import create_building
from .education import (
    _set_competence_floor, add_knowledge_custody, configure_reproduction, create_knowledge_asset,
    create_program, create_teaching_relationship, enroll, ensure_structural_training_cohorts,
)
from .ecology import configure_environment
from .cultivation import seed_cultivation_from_current_source
from .elixir import configure_elixir_supply, initialize_cultivation_physiology
from .politics import configure_polity, set_territorial_control
from .religion import configure_cultural_institution, configure_religious_institution

MARTIAL_INSTITUTION_KINDS={
    'sect','sect/school','martial school','military school','military academy','military college','order','clan/house','coven',
    'state martial establishment','martial/religious order','martial religious order','martial institution','noble martial house','military tradition'
}

# Opening-world activation is versioned separately from the SQL schema. A database can be
# schema-current yet still be missing newer opening projections. Long-horizon release gates
# verify this value before accepting the opening world.
CURRENT_CANON_ACTIVATION_VERSION = 20


def _load(raw: str | None, default):
    try: return json.loads(raw) if raw else default
    except Exception: return default


def _common_institution(conn: sqlite3.Connection, a: int, b: int) -> int | None:
    row=conn.execute('''SELECT x.institution_actor_id FROM institution_memberships x
                        JOIN institution_memberships y ON y.institution_actor_id=x.institution_actor_id
                        WHERE x.member_actor_id=? AND y.member_actor_id=? AND x.status='active' AND y.status='active'
                        ORDER BY x.institution_actor_id LIMIT 1''',(a,b)).fetchone()
    return int(row[0]) if row else None


def activate_explicit_teaching(conn: sqlite3.Connection) -> dict[str,int]:
    created_rel=0; competence=0
    rows=conn.execute("SELECT * FROM typed_relationship_facts WHERE status='active' AND relation_type IN ('direct_transmission','teacher_of') ORDER BY id").fetchall()
    for r in rows:
        teacher,student=int(r['actor_a_id']),int(r['actor_b_id'])
        if not conn.execute("SELECT 1 FROM actor_life_profiles WHERE actor_id=? AND life_status='living'",(teacher,)).fetchone(): continue
        if not conn.execute("SELECT 1 FROM actor_life_profiles WHERE actor_id=? AND life_status='living'",(student,)).fetchone(): continue
        # The explicit fact that A teaches B establishes teaching competence. No combat competence or Stage is inferred.
        _set_competence_floor(conn,teacher,'martial_instruction',60,source_kind='canon'); competence+=1
        kind='personal_master' if r['relation_type']=='direct_transmission' else 'instructor'
        existing=conn.execute("SELECT id FROM teaching_relationships WHERE teacher_actor_id=? AND student_actor_id=? AND relation_kind=? AND domain_key='martial_instruction' AND status='active'",(teacher,student,kind)).fetchone()
        if not existing:
            create_teaching_relationship(conn,teacher,student,kind,'martial_instruction',institution_actor_id=_common_institution(conn,teacher,student),responsibility=60,notes='Activated from explicit current-seed teaching/transmission fact; does not infer Stage progression.')
            created_rel+=1
    return {'explicit_teaching_relationships_created':created_rel,'teaching_competence_anchors':competence}


def activate_institution_training_contexts(conn: sqlite3.Connection) -> dict[str,int]:
    programs=0; enrollments=0; reproduction=0
    insts=conn.execute("SELECT ip.actor_id,ip.institution_kind FROM institution_profiles ip JOIN actors a ON a.id=ip.actor_id WHERE a.status='active'").fetchall()
    for inst in insts:
        kind=str(inst['institution_kind'] or '').lower()
        if kind not in MARTIAL_INSTITUTION_KINDS: continue
        iid=int(inst['actor_id'])
        configure_reproduction(conn,iid,recruitment_capacity=50,training_capacity=50,instructor_depth=50,archival_resilience=50,review_cadence_days=90,
                               metadata={'authority':'CAMPAIGN_CALIBRATION','meaning':'neutral initial capacities; not canon headcounts or quality rankings'})
        reproduction+=1
        key='aggregate-foundation-context'
        row=conn.execute("SELECT id FROM education_programs WHERE institution_actor_id=? AND program_key=?",(iid,key)).fetchone()
        if row: pid=int(row[0])
        else:
            pid=create_program(conn,key,'Aggregate foundation training context','martial_foundation','martial_foundation',institution_actor_id=iid,
                               duration_days=730,capacity=max(8,int(conn.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=? AND status='active'",(iid,)).fetchone()[0])*2),
                               min_entry_score=0,min_teacher_score=0,completion_gain=3,max_score_from_program=40,review_cadence_days=30,
                               metadata={'authority':'CAMPAIGN_ASSUMPTION','basis':'martial institution + active named trainee state','does_not_mean':'uniform curriculum, exclusive instruction, or Stage progression'})
            programs+=1
        # Named low-stage members already marked as actively training are safe participants in an aggregate context.
        candidates=conn.execute('''SELECT m.member_actor_id,s.source_payload_json FROM institution_memberships m
            JOIN source_identity_map s ON s.entity_kind='actor' AND s.entity_id=m.member_actor_id AND s.source_namespace='caerness_seed_v1_1'
            WHERE m.institution_actor_id=? AND m.status='active' ''',(iid,)).fetchall()
        for c in candidates:
            payload=_load(c['source_payload_json'],{})
            rt=payload.get('runtime_v1_1') or {}; tr=rt.get('training_state') or {}
            if not tr.get('active') or payload.get('stage') not in {'First','Temper'}: continue
            aid=int(c['member_actor_id'])
            if conn.execute("SELECT 1 FROM education_enrollments WHERE actor_id=? AND program_id=? AND status IN ('active','paused','completed')",(aid,pid)).fetchone(): continue
            enroll(conn,aid,pid,practice_quality=1.0,metadata={'authority':'CAMPAIGN_ASSUMPTION','basis':'explicit active training state + institution membership','stage_progression':False})
            enrollments+=1
    return {'training_programs_created':programs,'training_enrollments_created':enrollments,'reproduction_profiles_configured':reproduction}


def _archetype_for(name: str, kind: str) -> str | None:
    k=kind.lower(); n=name.lower()
    if k=='financial institution': return 'loan_house'
    if k=='merchant-noble house': return 'warehouse'
    if k=='company ecosystem': return 'warehouse'
    if k=='smuggling power': return 'warehouse'
    if k=='gambling/fight syndicate': return 'gambling_house'
    if k=='criminal dynasty': return 'warehouse'
    if 'brass lantern' in n: return 'appraiser'
    if 'still hand' in n: return 'refiner'
    return None


def activate_commercial_anchors(conn: sqlite3.Connection) -> dict[str,int]:
    created=0; profiled=0
    rows=conn.execute('''SELECT a.id,a.name,a.current_location_id,ip.institution_kind,ip.economic_json
                         FROM actors a JOIN institution_profiles ip ON ip.actor_id=a.id
                         WHERE a.actor_type='institution' AND a.status='active' ORDER BY a.id''').fetchall()
    for r in rows:
        archetype=_archetype_for(str(r['name']),str(r['institution_kind'] or ''))
        if not archetype: continue
        iid=int(r['id'])
        existing=conn.execute("SELECT id FROM civilian_enterprises WHERE institution_actor_id=? AND json_extract(metadata_json,'$.activation_key')='current-canon-aggregate-arm' LIMIT 1",(iid,)).fetchone()
        if existing: eid=int(existing[0])
        else:
            econ=_load(r['economic_json'],{})
            eid=create_enterprise(conn,f"{r['name']} — aggregate commercial arm",'other',institution_actor_id=iid,location_id=r['current_location_id'],
                                  capital=50,cash=25,debt=0,reputation=50,admin_quality=50,labor_capacity=50,risk_tolerance=50,
                                  metadata={'activation_key':'current-canon-aggregate-arm','authority':'CAMPAIGN_CALIBRATION','source_economic_state':econ,
                                            'meaning':'one aggregate operating footprint, not a claim that the institution owns exactly one business'})
            created+=1
        configure_enterprise_business(conn,eid,archetype,quality=50,price_position=50,capacity=50,clientele_fit=50,service_reliability=50,regulatory_pressure=20 if archetype in {'gambling_house'} else 5,
                                      cadence_days=30,metadata={'authority':'CAMPAIGN_CALIBRATION','institution_actor_id':iid})
        profiled+=1
    return {'aggregate_enterprises_created':created,'business_profiles_configured':profiled}


def _location(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def _institution(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def _aggregate_enterprise(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    location_id: int,
    archetype: str,
    *,
    institution_actor_id: int | None = None,
    enterprise_kind: str = 'other',
    capital: float = 50,
    cash: float = 25,
    quality: float = 50,
    capacity: float = 50,
    notes: str,
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM civilian_enterprises WHERE json_extract(metadata_json,'$.activation_key')=? LIMIT 1",
        (key,),
    ).fetchone()
    created = False
    if row:
        eid = int(row[0])
        conn.execute(
            "UPDATE civilian_enterprises SET location_id=COALESCE(location_id,?),institution_actor_id=COALESCE(institution_actor_id,?) WHERE id=?",
            (location_id, institution_actor_id, eid),
        )
    else:
        eid = create_enterprise(
            conn, name, enterprise_kind, institution_actor_id=institution_actor_id, location_id=location_id,
            capital=capital, cash=cash, debt=0, reputation=50, admin_quality=50, labor_capacity=50,
            risk_tolerance=45,
            metadata={
                'activation_key': key,
                'authority': 'CAMPAIGN_CALIBRATION',
                'basis': notes,
                'resolution': 'AGGREGATE_SECTOR',
                'does_not_mean': 'one literal firm, universal prices, or a complete local economy',
            },
        )
        created = True
    configure_enterprise_business(
        conn, eid, archetype, quality=quality, price_position=50, capacity=capacity,
        clientele_fit=55, service_reliability=55, regulatory_pressure=5, cadence_days=30,
        metadata={'authority':'CAMPAIGN_CALIBRATION','activation_key':key,'basis':notes},
    )
    return eid, created


def _ensure_production(
    conn: sqlite3.Connection,
    enterprise_id: int,
    good_id: int,
    *,
    capacity: float,
    inventory: float,
    efficiency: float = 55,
    material_access: float = 60,
    skilled_labor: float = 55,
    notes: str,
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM production_sites WHERE enterprise_id=? AND good_id=?",
        (enterprise_id, good_id),
    ).fetchone()
    if row:
        return int(row[0]), False
    pid = add_production_site(
        conn, enterprise_id, good_id, capacity_per_30=capacity, efficiency=efficiency,
        material_access=material_access, skilled_labor=skilled_labor, inventory=inventory,
        notes=notes,
    )
    return pid, True


def _ensure_aggregate_building(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    building_kind: str,
    location_id: int,
    *,
    institution_actor_id: int | None = None,
    basis: str,
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM buildings WHERE json_extract(metadata_json,'$.activation_key')=? LIMIT 1",
        (key,),
    ).fetchone()
    if row:
        return int(row[0]), False
    bid = create_building(
        conn, name, building_kind, location_id=location_id, institution_actor_id=institution_actor_id,
        capacity=60, condition=90, prestige=50, utility=75, maintenance_burden=8,
        metadata={
            'activation_key': key,
            'authority': 'CAMPAIGN_CALIBRATION',
            'basis': basis,
            'resolution': 'AGGREGATE_INFRASTRUCTURE',
            'does_not_mean': 'one literal building or a complete district census',
        },
    )
    return bid, True


def activate_economic_substrate(conn: sqlite3.Connection) -> dict[str, int]:
    """Seed a sparse, explicitly aggregate current-canon economy.

    The World Bible gives commercial *roles* and hubs but intentionally does not provide a
    continent-wide price/capacity table.  Therefore all numerical values below are campaign
    calibration in abstract economic units.  We seed market presence broadly, but production
    only where the Bible explicitly supports making/refining/assembling the relevant goods.
    Specific loans, debts, counterparties and ownership shares are not invented here.
    """
    # Abstract price indices, not an in-world currency declaration.
    goods = {
        'ordinary-grain': ('Grain and staple food', 'food', 1.0, 'bulk unit', 0.20, 0.10, 0.00),
        'ordinary-cloth': ('Cloth and ordinary textiles', 'textile', 2.0, 'bolt', 0.02, 0.45, 0.15),
        'ordinary-timber': ('Timber and building material', 'material', 1.4, 'load', 0.02, 0.20, 0.00),
        'ordinary-medicine': ('Ordinary medicines and medical supplies', 'medicine', 4.0, 'lot', 0.08, 0.65, 0.20),
        'vein-root': ('Vein-Root', 'cultivation_resource', 8.0, 'lot', 0.08, 0.70, 0.45),
        'metalwork': ('Tools, arms and metalwork', 'craft', 5.0, 'lot', 0.00, 0.75, 0.30),
        'travel-supplies': ('Travel and caravan supplies', 'material', 2.5, 'load', 0.05, 0.35, 0.05),
        'naval-supplies': ('Shipbuilding and naval supplies', 'material', 4.5, 'load', 0.00, 0.60, 0.20),
    }
    good_ids: dict[str, int] = {}
    for key, spec in goods.items():
        good_ids[key] = ensure_good(
            conn, key, spec[0], spec[1], spec[2], unit=spec[3], perishability=spec[4],
            skill_intensity=spec[5], luxury=spec[6],
            notes='v0.30 campaign-calibration price index; category/existence is setting-supported, number is not canon currency.',
        )

    # Current Bible commercial geography. Values are relative pressures only.
    hub_context = {
        'Toll’s Reach': dict(foot_traffic=80, traveler_flow=82, trade_flow=92, credit_demand=70, craft_demand=65, security=55, event_activity=65),
        'Aldergate': dict(foot_traffic=78, traveler_flow=72, trade_flow=95, credit_demand=88, craft_demand=70, security=68, construction_demand=65),
        'Cairnholt': dict(foot_traffic=78, traveler_flow=72, trade_flow=72, elite_patronage=88, cultural_activity=78, event_activity=82, health_demand=68),
        'Waymeet': dict(foot_traffic=75, traveler_flow=94, trade_flow=76, credit_demand=62, event_activity=70, security=62),
        'Lysmere': dict(foot_traffic=62, traveler_flow=68, trade_flow=62, health_demand=96, craft_demand=70, elite_patronage=65, security=82),
        'Aldenmoor': dict(foot_traffic=58, traveler_flow=55, trade_flow=58, elite_patronage=72, cultural_activity=92, craft_demand=70, reputation_climate=85),
        'Saltmere': dict(foot_traffic=86, traveler_flow=88, trade_flow=98, credit_demand=82, craft_demand=82, construction_demand=80, security=62, cultural_activity=72),
        'Stonecross': dict(foot_traffic=58, traveler_flow=62, trade_flow=68, craft_demand=90, military_demand=72, construction_demand=68, security=66),
        'Redford': dict(foot_traffic=55, traveler_flow=58, trade_flow=70, craft_demand=58, health_demand=55, security=62),
    }
    contexts = 0
    for name, values in hub_context.items():
        lid = _location(conn, name)
        if lid is not None:
            set_commercial_context(conn, lid, **values)
            contexts += 1

    # Markets describe circulation/demand, not local manufacture. Supply/demand are relative
    # starting pressures chosen to make hubs behave differently without claiming exact prices.
    market_plan = {
        'Toll’s Reach': {
            'ordinary-grain': (70,72), 'ordinary-cloth':(72,74), 'ordinary-timber':(68,72),
            'ordinary-medicine':(62,72), 'vein-root':(52,68), 'metalwork':(62,75),
            # Toll is a provisioning/export hub. Local consumption is deliberately below
            # aggregate provisioning output so exportable stock can exist for the logistics
            # subsystem instead of every unit being silently sold at origin.
            'travel-supplies':(82,34), 'naval-supplies':(70,78),
        },
        'Aldergate': {
            'ordinary-grain':(88,76), 'ordinary-cloth':(82,76), 'ordinary-timber':(78,74),
            'ordinary-medicine':(65,70), 'vein-root':(58,64), 'metalwork':(72,76), 'travel-supplies':(78,80),
        },
        'Cairnholt': {
            'ordinary-grain':(60,82), 'ordinary-cloth':(58,84), 'ordinary-timber':(55,68),
            'ordinary-medicine':(55,82), 'vein-root':(45,84), 'metalwork':(55,80), 'travel-supplies':(58,75),
        },
        'Waymeet': {
            'ordinary-grain':(62,80), 'ordinary-cloth':(60,72), 'ordinary-medicine':(52,75),
            'metalwork':(58,70), 'travel-supplies':(50,92),
        },
        'Lysmere': {
            'ordinary-grain':(62,74), 'ordinary-medicine':(85,92), 'vein-root':(60,82), 'travel-supplies':(62,68),
        },
        'Aldenmoor': {
            'ordinary-grain':(65,70), 'ordinary-cloth':(62,74), 'ordinary-medicine':(55,64), 'metalwork':(54,60),
        },
        'Saltmere': {
            'ordinary-grain':(76,78), 'ordinary-cloth':(82,78), 'ordinary-timber':(82,86),
            'ordinary-medicine':(78,76), 'vein-root':(75,72), 'metalwork':(75,82),
            # Dovell's explicit shipbuilding/naval-supply base is export-facing.
            'travel-supplies':(82,78), 'naval-supplies':(90,28),
        },
        'Stonecross': {'ordinary-grain':(58,70), 'metalwork':(88,62), 'travel-supplies':(62,68)},
        'Redford': {'ordinary-grain':(68,72), 'vein-root':(72,62), 'travel-supplies':(58,66)},
    }
    market_rows = 0
    for loc_name, plan in market_plan.items():
        lid = _location(conn, loc_name)
        if lid is None:
            continue
        for good_key, (supply, demand) in plan.items():
            set_market_condition(
                conn, lid, good_ids[good_key], supply=supply, demand=demand,
                transport_pressure=8 if loc_name in {'Waymeet','Redford','Stonecross'} else 4,
                risk_pressure=6 if loc_name in {'Toll’s Reach','Waymeet'} else 3,
                tax_pressure=5, cadence_days=30,
                metadata={
                    'authority':'CAMPAIGN_CALIBRATION',
                    'basis':'World Bible commercial geography and ordinary material economy',
                    'cadence_days':30,
                    'numeric_status':'relative simulation index, not canon price/volume',
                },
            )
            market_rows += 1

    # Correct the location of three explicit institutions whose v1.1 structured seed omitted
    # place_ref but whose MASTER FINAL Bible states their principal seat/headquarters.
    explicit_seats = {
        'Counting House': 'Aldergate',
        'Still Hand': 'Toll’s Reach',
        'Brass Lantern House': 'Toll’s Reach',
    }
    explicit_location_updates = 0
    for inst_name, loc_name in explicit_seats.items():
        iid, lid = _institution(conn, inst_name), _location(conn, loc_name)
        if iid is not None and lid is not None:
            # Canon-explicit present seats outrank any earlier non-canon opening working placement.
            # This is current-state correction, not invented travel/history.
            conn.execute("UPDATE actors SET home_location_id=?,current_location_id=? WHERE id=?", (lid,lid,iid))
            conn.execute("UPDATE institution_profiles SET primary_location_id=? WHERE actor_id=?", (lid,iid))
            conn.execute("UPDATE civilian_enterprises SET location_id=? WHERE institution_actor_id=?", (lid,iid))
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            conn.execute(
                """INSERT INTO actor_location_provenance(actor_id,location_id,provenance_kind,confidence,resolved_day,metadata_json)
                   VALUES (?,?, 'explicit_canon_seat',1.0,?,?)
                   ON CONFLICT(actor_id) DO UPDATE SET location_id=excluded.location_id,
                     provenance_kind=excluded.provenance_kind,confidence=excluded.confidence,
                     resolved_day=excluded.resolved_day,metadata_json=excluded.metadata_json""",
                (iid,lid,day,json.dumps({'opening_state':True,'history_invented':False,'authority':'MASTER_FINAL_EXPLICIT_SEAT'},sort_keys=True)),
            )
            explicit_location_updates += 1

    enterprises_created = 0
    production_created = 0

    # Explicitly supported making/assembling nodes only.
    # Still Hand: provision/procurement guild assembling mixed travel supplies at Toll's Reach.
    still = _institution(conn, 'Still Hand'); toll = _location(conn, 'Toll’s Reach')
    if still is not None and toll is not None:
        row = conn.execute("SELECT id FROM civilian_enterprises WHERE institution_actor_id=? ORDER BY id LIMIT 1", (still,)).fetchone()
        if row:
            eid = int(row[0]); conn.execute("UPDATE civilian_enterprises SET location_id=? WHERE id=?", (toll,eid))
        else:
            eid, made = _aggregate_enterprise(conn,'econ:still-hand-provisioning','Still Hand — aggregate provisioning arm',toll,'wholesaler',institution_actor_id=still,notes='MASTER FINAL: Still Hand headquarters in Toll’s Reach assembles mixed orders and travel supplies.')
            enterprises_created += int(made)
        _, made = _ensure_production(conn,eid,good_ids['travel-supplies'],capacity=18,inventory=8,notes='Aggregate provisioning/assembly, not raw-goods manufacture; campaign calibration grounded in Still Hand mixed-order role.')
        production_created += int(made)

    # House Dovell: explicit shipbuilding and naval supply at Saltmere.
    dovell = _institution(conn, 'House Dovell'); saltmere = _location(conn, 'Saltmere')
    if dovell is not None and saltmere is not None:
        row = conn.execute("SELECT id FROM civilian_enterprises WHERE institution_actor_id=? ORDER BY id LIMIT 1", (dovell,)).fetchone()
        if row:
            eid = int(row[0]); conn.execute("UPDATE civilian_enterprises SET location_id=? WHERE id=?", (saltmere,eid))
            configure_enterprise_business(conn,eid,'shipping_house',quality=55,capacity=65,clientele_fit=60,service_reliability=60,regulatory_pressure=8,cadence_days=30,metadata={'authority':'CAMPAIGN_CALIBRATION','basis':'MASTER FINAL: House Dovell shipbuilding and naval supply.'})
        else:
            eid, made = _aggregate_enterprise(conn,'econ:house-dovell-supply','House Dovell — aggregate naval supply arm',saltmere,'shipping_house',institution_actor_id=dovell,notes='MASTER FINAL: House Dovell dominates a large part of Windmere shipbuilding and naval supply.')
            enterprises_created += int(made)
        _, made = _ensure_production(conn,eid,good_ids['naval-supplies'],capacity=22,inventory=10,efficiency=60,material_access=65,skilled_labor=65,notes='Campaign-calibrated aggregate output grounded in explicit Dovell shipbuilding/naval-supply role.')
        production_created += int(made)

    # Lysmere explicitly contains refiners and medical manufacturing/services. This anonymous
    # aggregate avoids inventing a named school or proprietor.
    lys = _location(conn, 'Lysmere')
    if lys is not None:
        eid, made = _aggregate_enterprise(conn,'econ:lysmere-medical-sector','Lysmere — aggregate medical supply sector',lys,'medicine_shop',notes='MASTER FINAL: Lysmere contains rival medical schools, refiners, prosthetic makers and rehabilitation establishments.')
        enterprises_created += int(made)
        _, made2 = _ensure_production(conn,eid,good_ids['ordinary-medicine'],capacity=14,inventory=5,efficiency=60,material_access=60,skilled_labor=70,notes='Aggregate medicine/refining output; no named firm or monopoly implied.')
        production_created += int(made2)

    # Stonecross explicitly has smiths and Ore trade; model aggregate ordinary metalwork, not a
    # claim of Veinsteel volume or a named workshop.
    stone = _location(conn, 'Stonecross')
    if stone is not None:
        eid, made = _aggregate_enterprise(conn,'econ:stonecross-metal-sector','Stonecross — aggregate metalworking sector',stone,'smithy',notes='MASTER FINAL: Stonecross is a junction of smiths, Ore, guides and appraisers.')
        enterprises_created += int(made)
        _, made2 = _ensure_production(conn,eid,good_ids['metalwork'],capacity=16,inventory=6,efficiency=58,material_access=65,skilled_labor=62,notes='Ordinary tools/arms/metalwork aggregate; does not quantify Vein Ore or Veinsteel output.')
        production_created += int(made2)

    # Redroot Vale is the strongest explicit commercial Root-production geography, but the current
    # route graph has no direct Vale node connection. Keep production local; do not teleport freight.
    redroot = _location(conn, 'Redroot Vale')
    if redroot is not None:
        eid, made = _aggregate_enterprise(conn,'econ:redroot-production','Redroot Vale — aggregate Root production sector',redroot,'refiner',notes='MASTER FINAL: Redroot Vale is reliable enough for organized Vein-Root production.')
        enterprises_created += int(made)
        _, made2 = _ensure_production(conn,eid,good_ids['vein-root'],capacity=6,inventory=3,efficiency=52,material_access=75,skilled_labor=55,notes='Aggregate sustainable Root production calibration; does not fix acreage, owners, or harvest law.')
        production_created += int(made2)

    # Material infrastructure is represented as aggregate footprints, not exact building counts.
    building_specs = [
        ('econ:bld:toll-warehouses','Toll’s Reach — aggregate warehouse footprint','warehouse','Toll’s Reach','MASTER FINAL: dense warehouse districts at the River and Sea Quays.'),
        ('econ:bld:aldergate-warehouses','Aldergate — aggregate warehouse and caravan footprint','warehouse','Aldergate','MASTER FINAL: Exchange Quarter, warehouses and caravan wards.'),
        ('econ:bld:waymeet-caravan','Waymeet — aggregate caravan-court footprint','other','Waymeet','MASTER FINAL: inn yards, caravan courts and Contract Row.'),
        ('econ:bld:lysmere-medical','Lysmere — aggregate medical-establishment footprint','public_building','Lysmere','MASTER FINAL: rival medical schools, rehabilitation establishments, refiners and prosthetic makers.'),
        ('econ:bld:saltmere-port','Saltmere — aggregate port and warehouse footprint','warehouse','Saltmere','MASTER FINAL: principal international port with long-distance trade and overseas warehouse networks.'),
    ]
    buildings_created = 0
    for key,name,kind,loc_name,basis in building_specs:
        lid = _location(conn,loc_name)
        if lid is not None:
            _, made = _ensure_aggregate_building(conn,key,name,kind,lid,basis=basis)
            buildings_created += int(made)

    # The Brass Lantern explicitly runs four Grand Sales. The shared SV civil calendar is fixed,
    # but canon does not assign these sales exact dates, so these remain campaign-relative quarterly
    # placements until an in-world schedule is causally established. No lots are invented.
    auctions_created = 0
    brass = _institution(conn,'Brass Lantern House'); toll = _location(conn,'Toll’s Reach')
    if brass is not None and toll is not None:
        for idx, due in enumerate((90,180,270,360),1):
            key=f'econ:brass-grand-sale:{idx}'
            if conn.execute("SELECT 1 FROM auctions WHERE json_extract(metadata_json,'$.activation_key')=?",(key,)).fetchone():
                continue
            create_auction(conn,f'Brass Lantern Grand Sale — cycle {idx}',due,location_id=toll,institution_actor_id=brass,prestige=80,
                           metadata={'activation_key':key,'authority':'CAMPAIGN_CALIBRATION','basis':'MASTER FINAL states four major Grand Sales per year','calendar_status':'shared SV calendar fixed; exact Grand Sale dates not canonically assigned','no_lots_invented':True})
            auctions_created += 1

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('economic_substrate_activation_version','1')")
    return {
        'market_goods_configured': len(good_ids),
        'commercial_contexts_configured': contexts,
        'market_conditions_configured': market_rows,
        'explicit_institution_locations_applied': explicit_location_updates,
        'economic_aggregate_enterprises_created': enterprises_created,
        'production_sites_created': production_created,
        'aggregate_buildings_created': buildings_created,
        'brass_lantern_grand_sales_created': auctions_created,
    }


def activate_missing_merchant_anchors(conn: sqlite3.Connection) -> dict[str,int]:
    """Complete explicitly named Part Eleven institution identities omitted from the first structured seed.

    Identity is canonical/working from MASTER FINAL; headquarters remain unset unless the Bible actually fixes them.
    """
    specs = {
        'House Fenwick': ('merchant-noble house','MASTER FINAL Part 11: large inland merchant dynasty tied to caravans, grain, warehousing, road commerce and the Aldergate exchange.'),
        'House Merevale': ('merchant-noble house','MASTER FINAL Part 11: maritime and foreign-trade dynasty with ships and port factors.'),
        'House Serrick': ('merchant-noble house','MASTER FINAL Part 11: finance, urban property, wholesale credit and ordinary relationship lending.'),
        'House Orlan': ('merchant-noble house','MASTER FINAL Part 11: medicinal goods, refiners and cultivation-resource commerce.'),
        'Salt Road Consortium': ('company ecosystem','MASTER FINAL Part 11: association coordinating major coastal and cross-sea interests rather than one family.'),
    }
    created=0
    for name,(kind,basis) in specs.items():
        row=conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?",(name,)).fetchone()
        if row:
            iid=int(row[0])
        else:
            cur=conn.execute("INSERT INTO actors(name,actor_type,subtype,status,notes,is_demo) VALUES (?,'institution',?,'active',?,0)",(name,kind,basis))
            iid=int(cur.lastrowid); created += 1
        conn.execute("""INSERT OR IGNORE INTO institution_profiles(actor_id,institution_kind,governance_json,culture_json,pipeline_json,capacity_json,economic_json,reputation_json,succession_json,trajectory,last_review_day,notes)
                        VALUES (?,?, '{}','{}','{}','{}','{}','{}','{}','stable',0,?)""",(iid,kind,basis))
        conn.execute("""INSERT OR IGNORE INTO source_identity_map(source_namespace,source_key,entity_kind,entity_id,canon_status,provenance_json,source_payload_json,created_day,updated_day)
                        VALUES ('caerness_world_bible_master_final',?,'institution',?,'working',?,'{}',0,0)""",
                     ('institution:'+name.lower().replace(' ','-'),iid,json.dumps([basis])))
        conn.execute("""INSERT OR IGNORE INTO entity_resolution(entity_kind,entity_id,resolution_level,reason,review_cadence_days,next_review_day,last_changed_day,metadata_json)
                        VALUES ('institution',?,'STRUCTURAL','Named persistent World Bible institution anchor',90,90,0,?)""",
                     (iid,json.dumps({'authority':'WORLD_BIBLE','precise_headquarters':'UNSET_UNLESS_EXPLICIT'},sort_keys=True)))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('merchant_anchor_completion_version','1')")
    return {'named_merchant_institution_anchors_created':created}


def activate_elixir_substrate(conn: sqlite3.Connection) -> dict[str,int]:
    """Activate the source-supported elixir market/refining substrate without inventing batches or consumers."""
    refined=ensure_good(conn,'refined-elixir','Ordinary refined Vein-Root elixir','cultivation_resource',18.0,unit='batch unit',perishability=0.03,skill_intensity=0.90,luxury=0.65,
                        notes='v0.33 abstract price index; MASTER FINAL supports ordinary refined elixir as routine legitimate martial/medical commodity.')
    high=ensure_good(conn,'high-grade-elixir','High-grade Vein-Root elixir','cultivation_resource',48.0,unit='batch unit',perishability=0.02,skill_intensity=0.98,luxury=0.92,
                     notes='v0.33 abstract price index; MASTER FINAL supports scarce contracted/reserved high-grade elixir. Price is campaign calibration.')
    plans={
        'Toll’s Reach': ((62,74),(32,58)), 'Aldergate':((68,72),(36,62)), 'Cairnholt':((52,82),(24,72)),
        'Lysmere':((78,90),(38,74)), 'Saltmere':((70,76),(34,66)), 'Redford':((58,62),(18,42)),
    }
    markets=0
    for name,(ordinary,elite) in plans.items():
        lid=_location(conn,name)
        if lid is None: continue
        for gid,(sup,dem),grade in [(refined,ordinary,'refined'),(high,elite,'high_grade')]:
            set_market_condition(conn,lid,gid,supply=sup,demand=dem,transport_pressure=6,risk_pressure=5,tax_pressure=5,cadence_days=30,
                metadata={'authority':'CAMPAIGN_CALIBRATION','basis':'MASTER FINAL elixir economy and commercial geography','grade':grade,'numeric_status':'relative simulation index'})
            markets += 1

    suppliers=0
    # Lysmere explicitly contains refiners. This is an anonymous aggregate sector, not a named monopoly.
    lys=_location(conn,'Lysmere')
    if lys is not None:
        row=conn.execute("SELECT id FROM civilian_enterprises WHERE name='Lysmere — aggregate medical supply sector' ORDER BY id LIMIT 1").fetchone()
        if row:
            configure_elixir_supply(conn,int(row[0]),'refined',refinement_quality=72,sediment_risk=4,provenance_standard=70,
                source_basis='MASTER FINAL: Lysmere contains refiners and is the great concentration of cultivation medicine.',
                metadata={'authority':'SOURCE_ROLE_PLUS_CAMPAIGN_CALIBRATION','high_grade_not_assumed':True})
            suppliers += 1

    # House Orlan is explicitly a refiner/cultivation-resource merchant and explicitly deeply established in Aldergate.
    orlan=_institution(conn,'House Orlan'); ald=_location(conn,'Aldergate')
    if orlan is not None and ald is not None:
        row=conn.execute("SELECT id FROM civilian_enterprises WHERE institution_actor_id=? AND location_id=? ORDER BY id LIMIT 1",(orlan,ald)).fetchone()
        if row: eid=int(row[0])
        else:
            eid,_=_aggregate_enterprise(conn,'econ:orlan-aldergate','House Orlan — Aldergate aggregate refining/commercial footprint',ald,'refiner',institution_actor_id=orlan,
                 notes='MASTER FINAL: House Orlan handles medicinal goods, refiners and cultivation resources; Orlan is deeply established in Aldergate. This is an aggregate local footprint, not a claimed headquarters.')
        configure_elixir_supply(conn,eid,'refined',refinement_quality=76,sediment_risk=3,provenance_standard=78,
            source_basis='MASTER FINAL: House Orlan medicinal goods/refiners/cultivation-resource commerce; deep Aldergate establishment.',
            metadata={'authority':'SOURCE_ROLE_PLUS_CAMPAIGN_CALIBRATION','principal_seat':'UNRESOLVED','high_grade_not_assumed':True})
        suppliers += 1
    out=initialize_cultivation_physiology(conn)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('elixir_substrate_activation_version','1')")
    return {'elixir_market_conditions_configured':markets,'elixir_supply_profiles_configured':suppliers,**out}



def _person(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM actors WHERE actor_type='character' AND name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def activate_current_ecology(conn: sqlite3.Connection) -> dict[str, int]:
    """Activate only qualitatively established current ecology.

    Numeric values are coarse campaign calibration bands required by the legacy resolver; they are
    not canonical measurements and do not create seasonal timers the World Bible leaves qualitative.
    """
    specs = {
        'Hearthlands': (50,55,50,70,40,120,'broad Hearth baseline'),
        'Central Hearth': (55,60,55,80,40,150,'richer and broader central Hearth baseline'),
        'Eastern Hearth': (35,45,40,60,35,90,'thinner and patchier on average east of Ember Range'),
        'Fellmarch': (45,45,45,60,45,90,'mixed Fellmarch baseline'),
        'Ashgrave': (25,30,30,40,25,60,'damaged ecological/infrastructural region; not magical corruption'),
        'The Spine': (35,55,40,45,65,70,'concentrated and variable mountain current'),
        'White Laurel Heights': (80,75,55,35,85,50,'rich mountain ground with limited best-capacity portions'),
        'Stillwater': (60,90,65,45,55,60,'old stable ancestral ground'),
        'Bell Hollow': (65,70,65,90,55,140,'broad moderate-to-rich basin supporting many disciples'),
        'Stonepool': (75,65,55,30,85,35,'small dense ancestral ground with restricted high-value access'),
        'Brackwater Springs': (60,60,60,55,65,60,'several useful concentrations across the district'),
        'Deepwell Basin': (65,70,65,80,55,100,'broad reliable chartered/semi-neutral cultivation ground'),
        'Clearwell': (45,65,60,60,40,70,'weaker but dependable commercial cultivation ground'),
        'Stonewake Caverns': (65,45,45,30,80,35,'rich scattered chambers with variable recharge'),
        'Redroot Vale': (60,65,70,80,60,120,'major Root environment with mixed economic control'),
        'Ashgrave Wells': (30,30,35,50,35,50,'surviving and damaged remnants with fragmented claims'),
        'Silent Peak': (30,95,60,35,45,35,'thin but exceptionally coherent and stable current'),
    }
    configured = 0
    for name, (density, stability, replenishment, breadth, concentration, capacity, basis) in specs.items():
        lid = _location(conn, name)
        if lid is None:
            continue
        configure_environment(
            conn, lid,
            current_density=density, current_stability=stability, current_replenishment=replenishment,
            current_breadth=breadth, current_concentration=concentration, current_carrying_capacity=capacity,
            metadata={
                'activation_key': f'current-ecology:{name}', 'authority': 'CAMPAIGN_CALIBRATION',
                'basis': basis, 'source': 'Caerness World Bible MASTER FINAL',
                'no_hidden_cycle': True, 'numeric_values_are_inworld': False,
            },
        )
        configured += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_ecology_activation_version','1')")
    return {'current_ecology_profiles_configured': configured}


def activate_knowledge_assets(conn: sqlite3.Connection) -> dict[str, int]:
    # These aggregate records represent known institutional transmission corpora, not one invented
    # physical book. Named arts remain arts unless the Bible actually establishes a manual/text.
    institutions = [
        'House Halloway','House Corr','White Laurel Sect','Grey Bell Sect','Amberlight Sect',
        'Wrenfield Sect','Ragged Order','Grand Coven','House Renlow','Red Cedar Sect',
    ]
    created = custody = 0
    for name in institutions:
        iid = _institution(conn, name)
        if iid is None:
            continue
        key = f'knowledge:aggregate-canon:{name}'
        row = conn.execute("SELECT id FROM knowledge_assets WHERE json_extract(metadata_json,'$.activation_key')=?", (key,)).fetchone()
        if row:
            aid = int(row[0])
        else:
            aid = create_knowledge_asset(
                conn, f'{name} institutional transmission corpus (aggregate)', 'other', 'martial_instruction',
                institution_actor_id=iid, access_tier='member', completeness=1.0, teachability=0.65,
                preservation_mode='mixed', metadata={
                    'activation_key': key, 'authority': 'STRUCTURAL_AGGREGATE',
                    'basis': 'MASTER FINAL establishes a continuing martial inheritance/transmission canon',
                    'not_a_claim_of': 'one physical manual, universal member access, complete mastery, or a newly named text',
                },
            )
            created += 1
        if not conn.execute("SELECT 1 FROM knowledge_custody WHERE asset_id=? AND institution_actor_id=? AND status='active'", (aid, iid)).fetchone():
            add_knowledge_custody(conn, aid, 'archive', institution_actor_id=iid, notes='Aggregate institutional custody; exact copy/keeper distribution remains unresolved.')
            custody += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('knowledge_activation_version','1')")
    return {'knowledge_assets_created': created, 'knowledge_custody_created': custody}


def activate_polities(conn: sqlite3.Connection) -> dict[str, int]:
    specs = [
        ('Underheaven Empire','Underheaven','imperial state','Emperor Osric Varen','designated'),
        ('Dunmoor','Dunmoor','landed warrior monarchy','King Nicholas Ternwell','hereditary'),
        ('Windmere','Windmere','charter monarchy','Queen Maren Norwyn','hereditary'),
        ('Greywood','Greywood','institutional monarchy',None,'hereditary'),
        ('Sunreach Confederacy','Sunreach','confederated league',None,'custom'),
        ('Thornward','Thornward','elective ward-kingdom','King Corwin Hartfell','elective'),
        ('Stormhollow','Stormhollow','hereditary highland monarchy','King Roric Dunross','hereditary'),
    ]
    configured = controls = 0
    for inst_name, state_name, kind, ruler_name, method in specs:
        iid = _institution(conn, inst_name)
        if iid is None:
            continue
        ruler = _person(conn, ruler_name) if ruler_name else None
        # Capture current state-tagged places before set_territorial_control rewrites political_owner
        # to the polity actor's display name (notably Underheaven -> Underheaven Empire).
        locs = [int(r[0]) for r in conn.execute("SELECT id FROM locations WHERE political_owner=?", (state_name,)).fetchall()]
        pid = configure_polity(
            conn, iid, polity_kind=kind, ruler_actor_id=ruler, succession_method=method,
            legitimacy=50, stability=50, administrative_capacity=50, military_capacity=50, treasury_pressure=0,
            metadata={
                'authority':'WORLD_BIBLE_STRUCTURE_PLUS_CAMPAIGN_CALIBRATION',
                'basis':f'MASTER FINAL political form for {state_name}',
                'neutral_numeric_start':True,
                'ruler_omission_is_authoritative_open': inst_name in {'Greywood','Sunreach Confederacy'},
            },
        )
        configured += 1
        for lid in locs:
            set_territorial_control(
                conn, pid, lid, control_kind='direct', legitimacy=50, integration=50,
                notes='Imported from current seed state/polity containment; neutral numeric calibration.',
                reason='Current-canon territorial containment activated.',
            )
            controls += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('polity_activation_version','1')")
    return {'polities_configured': configured, 'territorial_controls_configured': controls}


def activate_religion_and_culture(conn: sqlite3.Connection) -> dict[str, int]:
    religious = 0
    for inst_name, tradition, authority, capacity in [
        ('Grand Coven','hollow_faith',85,75),
        ('Order of Marek','dunmoor_pantheon',60,55),
        ('Order of the Pilgrim Shield','witness',55,45),
        ('Underheaven Empire','imperial_observance',80,70),
    ]:
        iid = _institution(conn, inst_name)
        if iid is None:
            continue
        configure_religious_institution(
            conn, iid, tradition, authority=authority, ritual_capacity=capacity, treasury=0,
            metadata={
                'authority':'WORLD_BIBLE_STRUCTURE_PLUS_CAMPAIGN_CALIBRATION',
                'basis':'MASTER FINAL establishes religious/institutional role',
                'no_calendar_inferred':True,
                'treasury_zero_means':'unquantified religious treasury; no patronage spending is seeded',
            },
        )
        religious += 1

    cultural_profiles = 0
    brass = _institution(conn, 'Brass Lantern House')
    if brass is not None:
        configure_cultural_institution(
            conn, brass, 'auction_provenance_and_collecting', prestige=75, resources=50, public_reach=70, continuity=70,
            metadata={
                'authority':'WORLD_BIBLE_STRUCTURE_PLUS_CAMPAIGN_CALIBRATION',
                'basis':'MASTER FINAL establishes Brass Lantern as premier auction/cultural-market institution',
                'no_program_calendar_inferred':True,
            },
        )
        cultural_profiles += 1

    objects_created = 0
    for title, kind, creator_name, significance in [
        ('Arrival at Amber Court','painting','Liora Kelso','valuable'),
        ('Mercy at Caelshore','painting','Aurelia Morn','historical'),
        ('Glass Map of Saltmere','sculpture','Corvin Latch','historical'),
    ]:
        key=f'culture:object:{title}'
        if conn.execute("SELECT 1 FROM cultural_objects WHERE json_extract(metadata_json,'$.activation_key')=?",(key,)).fetchone():
            continue
        creator=_person(conn,creator_name)
        create_cultural_object(
            conn,title,kind,creator_actor_id=creator,quality=50,market_value=0,significance=significance,
            metadata={
                'activation_key':key,'authority':'WORLD_BIBLE',
                'basis':'MASTER FINAL named cultural exemplar',
                'current_owner_location_value_unresolved':True,
                'quality_value_is_neutral_runtime_placeholder':True,
            },
        )
        objects_created += 1

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('religion_culture_activation_version','1')")
    return {'religious_institutions_configured': religious, 'cultural_profiles_configured': cultural_profiles, 'cultural_objects_created': objects_created}


def activate_information_channels(conn: sqlite3.Connection) -> dict[str, int]:
    # Aggregate channel classes established by Part Twenty-Three; these are not invented newspaper titles.
    specs = [
        ('Hearth commercial-sheet circulation (aggregate)','commercial_sheet',0.8,0.78,0.15,1,
         ['Toll’s Reach','Aldergate','Cairnholt','Waymeet','Saltmere']),
        ('Long Road oral circulation (aggregate)','oral_network',1.0,0.55,0.20,1,
         ['Waymeet','Toll’s Reach','Cairnholt','Stonecross','Redford','Blackfen']),
        ('Concord correspondence network (aggregate)','institutional_correspondence',0.75,0.88,0.55,0,
         ['Cairnholt','Highford','Stonecross','Rivermoor']),
        ('Port and maritime correspondence (aggregate)','merchant_correspondence',0.7,0.82,0.35,0,
         ['Toll’s Reach','Saltmere','Stormwatch','Silvercove']),
    ]
    channels = links = 0
    for name, kind, speed, fidelity, secrecy, public, locations in specs:
        row=conn.execute("SELECT id FROM information_channels WHERE name=?",(name,)).fetchone()
        if row:
            cid=int(row[0])
        else:
            cur=conn.execute(
                """INSERT INTO information_channels(name,channel_kind,speed_multiplier,fidelity,secrecy,public_access,notes,is_demo)
                   VALUES (?,?,?,?,?,?,?,0)""",
                (name,kind,speed,fidelity,secrecy,public,
                 'STRUCTURAL_AGGREGATE from MASTER FINAL Part 23; channel class/network, not a uniquely named publication.'),
            )
            cid=int(cur.lastrowid); channels += 1
        for loc_name in locations:
            lid=_location(conn,loc_name)
            if lid is None: continue
            before=conn.total_changes
            conn.execute("INSERT OR IGNORE INTO channel_locations(channel_id,location_id,strength) VALUES (?,?,?)",(cid,lid,0.75))
            if conn.total_changes>before: links += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('information_channel_activation_version','1')")
    return {'information_channels_created':channels,'information_channel_location_links_created':links}


def activate_military_logistics(conn: sqlite3.Connection) -> dict[str,int]:
    from .war import configure_military_logistics_profile
    day=int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    source_names={'Underheaven Empire':'Crownhold','Dunmoor':None,'Windmere':None,'Greywood':None,'Sunreach Confederacy':None,'Thornward':None,'Stormhollow':None}
    count=0
    for row in conn.execute("SELECT p.id,a.name,p.military_capacity,p.administrative_capacity FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id WHERE p.status!='dissolved'").fetchall():
        name=str(row['name']); source=_location(conn,source_names.get(name)) if source_names.get(name) else None
        mil=float(row['military_capacity']); admin=float(row['administrative_capacity'])
        configure_military_logistics_profile(conn,int(row['id']),source_location_id=source,food_fodder_capacity=(mil+admin)/2,medical_capacity=45+mil*0.1,equipment_capacity=45+mil*0.1,elixir_reserve_capacity=25,transport_capacity=(mil+admin)/2,readiness=mil,metadata={'authority':'WORLD_BIBLE_STRUCTURE_PLUS_CAMPAIGN_CALIBRATION','basis':'MASTER FINAL establishes every polity military; numerical capacities are neutral campaign calibration','quiet_opening_does_not_imply_mobilization':True})
        count+=1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('military_logistics_activation_version','1')")
    return {'military_logistics_profiles_configured':count}


def activate_integration_opening_substrate(conn: sqlite3.Connection) -> dict[str,int]:
    """Populate shallow ordinary-world health/agriculture/law capacity without inventing named people.

    These rows are structural campaign substrate. Named physicians, farmers, judges and clerks remain
    latent until they become causally important and crystallize through the resolution layer.
    """
    from .health import create_care_site
    from .agriculture import create_field
    from .law import create_jurisdiction, add_rule, create_office

    day=int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    out={'opening_health_sites_created':0,'opening_agriculture_fields_created':0,
         'opening_law_jurisdictions_created':0,'opening_law_offices_created':0,'opening_law_rules_created':0}

    # Health: one structural ordinary-care network per economically active hub with health demand.
    # Capacity represents latent ordinary providers, not invented named doctors.
    health_rows=conn.execute("""SELECT c.location_id,l.name,c.health_demand
                                FROM location_commercial_context c JOIN locations l ON l.id=c.location_id
                                WHERE c.health_demand>0 ORDER BY c.health_demand DESC,c.location_id""").fetchall()
    for r in health_rows:
        lid=int(r['location_id']); key=f"opening:care:{lid}"
        if conn.execute("SELECT 1 FROM health_care_sites WHERE site_key=?",(key,)).fetchone():
            continue
        demand=float(r['health_demand']); quality=max(42.0,min(72.0,42.0+demand*.22)); capacity=max(1.0,min(5.0,1.0+demand/35.0))
        enterprise=conn.execute("""SELECT e.id FROM civilian_enterprises e
                                   WHERE e.location_id=? AND e.status IN ('active','strained')
                                   ORDER BY CASE WHEN lower(e.enterprise_kind) LIKE '%medicine%' THEN 0 ELSE 1 END,e.id LIMIT 1""",(lid,)).fetchone()
        create_care_site(conn,key,f"[STRUCTURAL] {r['name']} ordinary care network",location_id=lid,
                         enterprise_id=int(enterprise[0]) if enterprise else None,quality=quality,capacity_per_day=capacity,
                         beds=max(1,int(round(capacity*2))),metadata={
                             'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                             'not_named_canon_provider':True,
                             'aggregate_provider_domains':{
                                 'medicine':{'competence':max(48.0,min(68.0,quality)),'capacity_per_day':capacity},
                                 'surgery':{'competence':max(44.0,min(62.0,quality-4)),'capacity_per_day':max(.5,capacity*.35)},
                             },
                             'basis':'ordinary medical capacity implied by populated commercial hubs; named providers remain latent',
                         })
        out['opening_health_sites_created']+=1

    # Agriculture: food markets need a physical local/regional harvest substrate. The anonymous
    # enterprise/field is aggregate hinterland capacity, not a claim about a named farm or owner.
    grain=conn.execute("SELECT id FROM market_goods WHERE good_key='ordinary-grain'").fetchone()
    if grain:
        gid=int(grain[0])
        food_locs=conn.execute("""SELECT DISTINCT mc.location_id,l.name
                                  FROM market_conditions mc JOIN locations l ON l.id=mc.location_id
                                  WHERE mc.good_id=? ORDER BY mc.location_id""",(gid,)).fetchall()
        for r in food_locs:
            lid=int(r['location_id']); fkey=f"opening:grain:{lid}"
            if conn.execute("SELECT 1 FROM agriculture_fields WHERE field_key=?",(fkey,)).fetchone():
                continue
            erow=conn.execute("""SELECT id FROM civilian_enterprises WHERE location_id=?
                                AND json_extract(metadata_json,'$.activation_key')=? LIMIT 1""",(lid,f"opening-grain-hinterland:{lid}")).fetchone()
            if erow: eid=int(erow[0])
            else:
                eid=create_enterprise(conn,f"[STRUCTURAL] {r['name']} grain hinterland",'other',location_id=lid,
                                      capital=35,cash=12,debt=0,reputation=45,admin_quality=45,labor_capacity=65,risk_tolerance=35,
                                      metadata={'activation_key':f'opening-grain-hinterland:{lid}','authority':'CAMPAIGN_CALIBRATION',
                                                'opening_structural_substrate':True,'not_named_canon_enterprise':True,
                                                'meaning':'aggregate farms supplying the local/regional grain market'})
            create_field(conn,fkey,f"[STRUCTURAL] {r['name']} grain fields",enterprise_id=eid,location_id=lid,crop_good_id=gid,
                         hectares=24,base_yield_per_hectare=2.2,soil_quality=65,labor_capacity=68,
                         harvest_day_of_year=270,metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                                          'not_named_canon_farm':True,'aggregate_hinterland':True})
            out['opening_agriculture_fields_created']+=1

    # Law: every active polity receives a structural ordinary jurisdiction and docket. This does
    # not invent a named judge, specific statute book or disputed constitutional detail.
    polities=conn.execute("""SELECT p.*,a.name AS polity_name,a.current_location_id AS actor_location
                             FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id
                             WHERE p.status IN ('active','regency','succession_crisis','fragmenting') ORDER BY p.id""").fetchall()
    for pty in polities:
        pid=int(pty['id']); jkey=f"opening:polity-law:{pid}"
        jr=conn.execute("SELECT id FROM law_jurisdictions WHERE jurisdiction_key=?",(jkey,)).fetchone()
        if jr: jid=int(jr[0])
        else:
            jid=create_jurisdiction(conn,jkey,f"[STRUCTURAL] {pty['polity_name']} ordinary jurisdiction",'other',polity_id=pid,
                                    priority=45,metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                                          'not_named_canon_court':True,'constitutional_detail_protected':True})
            out['opening_law_jurisdictions_created']+=1
        for matter,threshold,remedy in (('contract',55,'damages'),('property',58,'order'),('commercial',52,'restitution'),('criminal',62,'fine')):
            rkey=f"opening:{pid}:{matter}"
            if not conn.execute("SELECT 1 FROM law_rules WHERE jurisdiction_id=? AND rule_key=?",(jid,rkey)).fetchone():
                add_rule(conn,jid,rkey,f"[STRUCTURAL] ordinary {matter} rule",matter,evidence_threshold=threshold,default_remedy=remedy,
                         metadata={'authority':'CAMPAIGN_CALIBRATION','ordinary_rule_family':True,'not_verbatim_canon_statute':True})
                out['opening_law_rules_created']+=1
        okey=f"opening:ordinary-court:{pid}"
        if not conn.execute("SELECT 1 FROM law_offices WHERE office_key=?",(okey,)).fetchone():
            loc=int(pty['actor_location']) if pty['actor_location'] is not None else None
            create_office(conn,okey,f"[STRUCTURAL] {pty['polity_name']} ordinary court",jid,location_id=loc,
                          institution_actor_id=int(pty['institution_actor_id']),capacity=max(35,float(pty['administrative_capacity'])),
                          integrity=65,corruption_pressure=15,metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                                                       'presiding_person_remains_latent':True})
            out['opening_law_offices_created']+=1
    return out


def activate_ordinary_economic_state_substrate(conn: sqlite3.Connection) -> dict[str, int]:
    """Seed the minimum ordinary MERCHANT/CRAFT/GROWTH substrate required by an unattended world.

    This deliberately uses existing named house principals only where the current seed already supplies
    them. Workshop labor remains structural through the production site's aggregate skilled-labor value;
    no named craftsperson is invented. Physical opening stock is transferred or materialized from an
    aggregate market with corresponding market-supply/cash conservation.
    """
    from .merchant import add_enterprise_staff, record_market_observation, apply_supply_shock
    from .craft import create_recipe, add_recipe_input, add_recipe_facility_requirement, add_facility, bind_recipe_to_site, create_production_order
    from .growth import configure_public_treasury

    day=int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    out={
        'opening_merchant_staff_configured':0,'opening_merchant_observations_created':0,
        'opening_physical_stock_bridges_created':0,'opening_craft_recipes_created':0,
        'opening_craft_facilities_created':0,'opening_craft_orders_created':0,
        'opening_public_treasuries_created':0,
    }

    # Merchant houses with explicit current-seed members receive authority through those existing people.
    for house in ('House Selwick','House Morrick','House Dovell'):
        inst=conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?",(house,)).fetchone()
        if not inst: continue
        ent=conn.execute("""SELECT id,location_id FROM civilian_enterprises WHERE institution_actor_id=?
                            AND json_extract(metadata_json,'$.activation_key')='current-canon-aggregate-arm' ORDER BY id LIMIT 1""",(int(inst[0]),)).fetchone()
        member=conn.execute("""SELECT member_actor_id FROM institution_memberships WHERE institution_actor_id=? AND status='active'
                               ORDER BY member_actor_id LIMIT 1""",(int(inst[0]),)).fetchone()
        if not ent or not member: continue
        add_enterprise_staff(conn,int(ent['id']),int(member[0]),role='house_principal',authority=72,specialty='commerce',
                             metadata={'authority':'WORLD_BIBLE_ROLE_PLUS_CAMPAIGN_CALIBRATION',
                                       'basis':'existing named active member authorizes the house aggregate commercial arm',
                                       'not_claim':'exclusive factor or exact historical office'})
        # Material commercial authority is a real reason for strategic review cadence; this is not camera privilege.
        conn.execute("""UPDATE simulation_profiles SET tier='STRATEGIC',cadence_days=MIN(cadence_days,30),
                      next_review_day=MIN(next_review_day,?) WHERE actor_id=?""",(day+30,int(member[0])))
        out['opening_merchant_staff_configured']+=1
        if ent['location_id'] is not None:
            lid=int(ent['location_id'])
            for mr in conn.execute("SELECT good_id FROM market_conditions WHERE location_id=? ORDER BY good_id",(lid,)).fetchall():
                gid=int(mr[0])
                if conn.execute("""SELECT 1 FROM merchant_market_observations WHERE enterprise_id=? AND observer_actor_id=?
                                  AND location_id=? AND good_id=? AND source_kind='opening_local_market_book' LIMIT 1""",
                                (int(ent['id']),int(member[0]),lid,gid)).fetchone():
                    continue
                record_market_observation(conn,int(ent['id']),lid,gid,observer_actor_id=int(member[0]),observed_day=day,received_day=day,
                                          source_kind='opening_local_market_book',reliability=.9,
                                          metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                                    'basis':'principal is physically based at the enterprise local market'})
                out['opening_merchant_observations_created']+=1

    # Move already-existing aggregate opening inventories into the physical-stock owner where a
    # merchant-facing lot is useful. This is a transfer, not duplication: legacy inventory is zeroed.
    for site_name in ('Still Hand — aggregate commercial arm','House Dovell — aggregate commercial arm'):
        row=conn.execute("""SELECT ps.id AS site_id,ps.inventory,ps.good_id,e.id AS enterprise_id,e.location_id
                            FROM production_sites ps JOIN civilian_enterprises e ON e.id=ps.enterprise_id
                            WHERE e.name=? AND ps.active=1 ORDER BY ps.id LIMIT 1""",(site_name,)).fetchone()
        if not row or row['location_id'] is None or float(row['inventory'])<=1e-9: continue
        marker=f"opening_stock_bridge_site_{int(row['site_id'])}"
        if conn.execute("SELECT 1 FROM engine_meta WHERE key=?",(marker,)).fetchone(): continue
        qty=float(row['inventory'])
        conn.execute("""INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json)
                        VALUES (?,?,?,?,?,?) ON CONFLICT(enterprise_id,location_id,good_id) DO UPDATE SET
                        quantity=commercial_stock.quantity+excluded.quantity,updated_day=excluded.updated_day""",
                     (int(row['enterprise_id']),int(row['location_id']),int(row['good_id']),qty,day,
                      json.dumps({'authority':'MIGRATED_OPENING_STATE','source':'legacy_production_site_inventory',
                                  'opening_resolution_bridge':True,'production_site_id':int(row['site_id'])},sort_keys=True)))
        conn.execute("UPDATE production_sites SET inventory=0 WHERE id=?",(int(row['site_id']),))
        conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?)",(marker,'1'))
        out['opening_physical_stock_bridges_created']+=1

    # One explicit ordinary tracked workshop: Dovell's already-established naval-supply activity.
    # It uses structural labor (production_sites.skilled_labor) until a worker becomes important enough to crystallize.
    site=conn.execute("""SELECT ps.*,e.location_id,e.cash,e.id AS eid FROM production_sites ps
                         JOIN civilian_enterprises e ON e.id=ps.enterprise_id
                         WHERE e.name='House Dovell — aggregate commercial arm' AND ps.active=1 ORDER BY ps.id LIMIT 1""").fetchone()
    if site and site['location_id'] is not None:
        naval=conn.execute("SELECT id FROM market_goods WHERE good_key='naval-supplies'").fetchone()
        timber=conn.execute("SELECT id FROM market_goods WHERE good_key='ordinary-timber'").fetchone()
        metal=conn.execute("SELECT id FROM market_goods WHERE good_key='metalwork'").fetchone()
        cloth=conn.execute("SELECT id FROM market_goods WHERE good_key='ordinary-cloth'").fetchone()
        if naval and timber and metal and cloth:
            existed=conn.execute("SELECT id FROM craft_recipes WHERE recipe_key='opening:dovell-naval-supplies'").fetchone()
            rid=create_recipe(conn,'opening:dovell-naval-supplies','Dovell ordinary naval-supply batch',int(naval[0]),
                              output_quantity=1,base_duration_days=2,skill_domain='craft',min_skill=45,
                              metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                        'basis':'Dovell shipbuilding/naval-supply role; ratios are coarse runtime calibration'})
            if not existed: out['opening_craft_recipes_created']+=1
            add_recipe_input(conn,rid,int(timber[0]),group_key='timber',units_per_batch=1.0)
            add_recipe_input(conn,rid,int(metal[0]),group_key='metal fittings',units_per_batch=.25)
            add_recipe_input(conn,rid,int(cloth[0]),group_key='cloth/rigging',units_per_batch=.25)
            add_recipe_facility_requirement(conn,rid,'shipyard_workshop',minimum_capacity=1,minimum_condition=40)
            fac=conn.execute("""SELECT id FROM craft_facilities WHERE enterprise_id=? AND location_id=? AND facility_kind='shipyard_workshop'
                                AND json_extract(metadata_json,'$.activation_key')='opening:dovell-shipyard' LIMIT 1""",
                             (int(site['eid']),int(site['location_id']))).fetchone()
            if not fac:
                add_facility(conn,int(site['eid']),int(site['location_id']),'shipyard_workshop','[STRUCTURAL] Dovell shipyard workshop',
                             capacity=1.5,condition=72,metadata={'activation_key':'opening:dovell-shipyard','authority':'CAMPAIGN_CALIBRATION',
                                                               'opening_structural_substrate':True,'named_workers_remain_latent':True})
                out['opening_craft_facilities_created']+=1
            bind_recipe_to_site(conn,int(site['id']),rid,is_default=True)

            # Materialize a small opening working lot from the already-existing aggregate Saltmere market.
            # The tracked enterprise pays cash and aggregate market supply falls by the same physical quantity.
            marker='opening_dovell_craft_inputs_seeded'
            if not conn.execute("SELECT 1 FROM engine_meta WHERE key=?",(marker,)).fetchone():
                needs=((int(timber[0]),3.0),(int(metal[0]),.75),(int(cloth[0]),.75))
                priced=[]; total=0.0
                for gid,qty in needs:
                    mc=conn.execute("SELECT current_price,supply FROM market_conditions WHERE location_id=? AND good_id=?",
                                    (int(site['location_id']),gid)).fetchone()
                    if not mc or float(mc['supply'])+1e-9<qty:
                        priced=[]; break
                    cost=qty*float(mc['current_price']); priced.append((gid,qty,cost)); total+=cost
                cash=float(conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?",(int(site['eid']),)).fetchone()[0])
                if priced and cash+1e-9>=total:
                    for gid,qty,cost in priced:
                        apply_supply_shock(conn,int(site['location_id']),gid,-qty,source='opening_tracked_working_inventory_bridge')
                        conn.execute("""INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json)
                                        VALUES (?,?,?,?,?,?) ON CONFLICT(enterprise_id,location_id,good_id) DO UPDATE SET
                                        quantity=commercial_stock.quantity+excluded.quantity,updated_day=excluded.updated_day""",
                                     (int(site['eid']),int(site['location_id']),gid,qty,day,
                                      json.dumps({'authority':'CAMPAIGN_CALIBRATION','source':'aggregate_market_resolution_bridge',
                                                  'opening_working_inventory':True},sort_keys=True)))
                    conn.execute("UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?",(total,day,int(site['eid'])))
                    conn.execute("""INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,source_kind)
                                    VALUES (?,?,?,?,?,'opening_resolution_bridge')""",
                                 (int(site['eid']),day,'purchase',total,'Opening tracked working inventory purchased from aggregate Saltmere market'))
                    conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?)",(marker,'1'))
            if not conn.execute("""SELECT 1 FROM craft_production_orders WHERE production_site_id=?
                                  AND json_extract(metadata_json,'$.activation_key')='opening:dovell-order' LIMIT 1""",(int(site['id']),)).fetchone():
                create_production_order(conn,int(site['id']),3.0,recipe_id=rid,priority=55,due_day=day+45,
                                        metadata={'activation_key':'opening:dovell-order','authority':'CAMPAIGN_CALIBRATION',
                                                  'opening_structural_substrate':True})
                out['opening_craft_orders_created']+=1

    # Every active polity needs a public-finance owner even if it takes no discretionary action this year.
    for pty in conn.execute("SELECT id,administrative_capacity FROM political_polities WHERE status IN ('active','regency','succession_crisis','fragmenting') ORDER BY id").fetchall():
        pid=int(pty['id'])
        if conn.execute("SELECT 1 FROM regional_public_treasuries WHERE polity_id=?",(pid,)).fetchone(): continue
        admin=float(pty['administrative_capacity'])
        configure_public_treasury(conn,pid,cash=max(60.0,admin*1.5),debt=0,tax_rate=.04,toll_rate=.005,
                                  review_cadence_days=30,metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                                                  'cash_is_simulation_liquidity_not_canon_treasury_amount':True,
                                                                  'basis':'active polity requires a fiscal owner for ordinary unattended state capacity'})
        out['opening_public_treasuries_created']+=1

    if not conn.execute("SELECT 1 FROM engine_meta WHERE key='merchant_next_market_cycle_day'").fetchone():
        conn.execute("INSERT INTO engine_meta(key,value) VALUES ('merchant_next_market_cycle_day',?)",(str(day+1),))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('ordinary_economic_substrate_activation_version','1')")
    return out

def activate_post76_agency_conflict(conn: sqlite3.Connection) -> dict[str,Any]:
    """Activate only the schema-77..80 agency/conflict layers on an existing campaign.

    This is deliberately narrow so upgrading a mature save does not re-run older opening
    activators and fabricate present-day copies of historical setup events.
    """
    out={}
    from .organization_agency import activate_shared_organization_agency
    out.update(activate_shared_organization_agency(conn))
    from .polity_agency import activate_polity_agency
    out.update(activate_polity_agency(conn))
    from .conflict import activate_conflict_channels
    out.update(activate_conflict_channels(conn))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('orgagency_conflict_activation_version','1')")
    return out

def activate_post80_organization_lifecycle(conn: sqlite3.Connection) -> dict[str,Any]:
    """Activate only ORGLIFE-01 on an already-running schema-80 campaign.

    This intentionally projects current organization/polity state into the new lifecycle
    owner without backdating formation, split, merger, or dissolution events.
    """
    from .organization_lifecycle import activate_organization_lifecycle
    out = activate_organization_lifecycle(conn)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('orglife01_narrow_activation_version','1')")
    return out


def activate_existing_loops(conn: sqlite3.Connection) -> dict[str,Any]:
    out={}
    from .opening_world_state import resolve_opening_institution_locations, resolve_opening_character_locations
    out['opening_institution_locations_resolved']=resolve_opening_institution_locations(conn)
    out.update({f'opening_character_locations_{k}':v for k,v in resolve_opening_character_locations(conn).items()})
    out.update(activate_missing_merchant_anchors(conn))
    out['opening_institution_locations_post_anchors']=resolve_opening_institution_locations(conn)
    out.update(activate_explicit_teaching(conn))
    out.update({f'opening_character_locations_post_teaching_{k}':v for k,v in resolve_opening_character_locations(conn).items()})
    from .teaching_ecology import refresh_teacher_market
    out.update(refresh_teacher_market(conn))
    out.update(activate_institution_training_contexts(conn))
    out['structural_training_cohorts_created']=ensure_structural_training_cohorts(conn,0)
    out.update(activate_commercial_anchors(conn))
    out.update(activate_economic_substrate(conn))
    from .scale import activate_scale_authority
    out.update(activate_scale_authority(conn))
    from .background_population import activate_population_sources, activate_population_life_course
    out.update(activate_population_sources(conn))
    out.update(activate_population_life_course(conn))
    from .person_ecology import activate_background_people
    out.update(activate_background_people(conn))
    from .profession_runtime import activate_profession_runtime
    out.update(activate_profession_runtime(conn))
    from .opening_world_state import activate_institutional_authority
    out.update(activate_institutional_authority(conn))
    from .aggregate_trade import activate_aggregate_trade
    out.update(activate_aggregate_trade(conn))
    out.update(activate_elixir_substrate(conn))
    out.update(activate_current_ecology(conn))
    from .conflict_geometry import activate_conflict_geometry
    out.update(activate_conflict_geometry(conn))
    out.update(activate_knowledge_assets(conn))
    out.update(activate_polities(conn))
    out.update(activate_military_logistics(conn))
    out.update(activate_ordinary_economic_state_substrate(conn))
    out.update(activate_religion_and_culture(conn))
    out.update(activate_information_channels(conn))
    out.update(seed_cultivation_from_current_source(conn))
    from .groundbinding import seed_current_groundbinding
    out.update(seed_current_groundbinding(conn))
    from .tournaments import activate_tournament_substrate
    out.update(activate_tournament_substrate(conn))
    from .spectacle import activate_spectacle_substrate
    out.update(activate_spectacle_substrate(conn))
    from .underworld_rebuild import enforce_rebuild_firewall
    out['v060_legacy_underworld_retired'] = enforce_rebuild_firewall(conn)
    from .underworld import activate_underworld_substrate
    # v0.60 keeps the old module only for generic law/evidence compatibility. Legacy named
    # underworld institutions are retired by the schema firewall and therefore do not reactivate.
    out.update(activate_underworld_substrate(conn))
    from .underworld_rebuild import seed_city_underworld
    aldergate = conn.execute("SELECT id FROM locations WHERE name='Aldergate'").fetchone()
    if aldergate:
        snap = seed_city_underworld(conn, city_location_id=int(aldergate[0]))
        out.update({
            'v060_underworld_organizations': int(snap.get('organizations',0)),
            'v060_underworld_zones': int(snap.get('zones',0)),
            'v060_underworld_crews': int(snap.get('crews',0)),
            'v060_underworld_rackets': int(snap.get('rackets',0)),
            'v060_underworld_protection_accounts': int(snap.get('protection_accounts',0)),
        })
    out.update(activate_post76_agency_conflict(conn))
    out.update(activate_post80_organization_lifecycle(conn))
    from .hollow import activate_hollow_substrate
    out.update(activate_hollow_substrate(conn))
    out.update(activate_integration_opening_substrate(conn))
    from .merchant_taxonomy import activate_merchant_taxonomy
    out.update(activate_merchant_taxonomy(conn))
    from .service_fulfillment import activate_structural_provider_contracts
    out.update(activate_structural_provider_contracts(conn))
    conn.execute(
        "INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_canon_activation_version',?)",
        (str(CURRENT_CANON_ACTIVATION_VERSION),),
    )
    return out
