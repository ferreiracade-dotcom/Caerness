"""WAR-01 acceptance: political objective -> routed campaign/supply -> battle -> persistent world consequences -> actor-relative reports."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.civilian import create_household, create_enterprise, ensure_good, set_market_condition
from engine.civilian_life import create_building
from engine.ecology import add_route, add_route_condition, process_due_ecology
from engine.combat import create_battle, add_battle_side, add_battle_unit, resolve_battle_round
from engine.war import (configure_military_logistics_profile, create_campaign_operation, add_campaign_force,
                        add_force_member, configure_force_supply, link_operation_engagement,
                        attach_force_to_battle_side, process_due_war)
from engine.politics import add_succession_claim, process_due_politics
from engine.household_life import process_due_household_life
from engine.decisions import build_actor_context, candidate_to_proposal, apply_decision
from engine.decision_runtime import generate_candidates


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_war01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); return connect(),path


def actor(c,name,loc,tier='STRATEGIC'):
    aid=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id,status) VALUES (?,'character',?,?,'active')",(name,loc,loc)).lastrowid)
    c.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days,last_review_day,next_review_day) VALUES (?,?,?,?,?)",(aid,tier,30,0,30))
    return aid


def polity(c,name,loc,ruler,military=65):
    inst=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'institution',?,'active')",(name,loc)).lastrowid)
    c.execute("INSERT INTO institution_profiles(actor_id,institution_kind) VALUES (?,'state')",(inst,))
    pid=int(c.execute("""INSERT INTO political_polities(institution_actor_id,polity_kind,ruler_actor_id,administrative_capacity,
                     military_capacity,status,next_review_day) VALUES (?,'kingdom',?,60,?,'active',30)""",(inst,ruler,military)).lastrowid)
    return pid


def set_day(c,day): c.execute("UPDATE world_state SET current_day=? WHERE id=1",(int(day),))


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=67
    c,path=bootstrap()
    # Real geography: source -> pass -> contested front, with a separate refuge route.
    source=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[WAR01] North Supply City','city')").lastrowid)
    mid=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[WAR01] Wolf Pass','pass')").lastrowid)
    front=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[WAR01] Red Ford','town')").lastrowid)
    refuge=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[WAR01] Refuge Vale','village')").lastrowid)
    r1=add_route(c,source,mid,base_days=2,reliability=96)
    r2=add_route(c,mid,front,base_days=2,reliability=94)
    rr=add_route(c,front,refuge,base_days=2,reliability=82)

    attacker=actor(c,'[WAR01] Queen North',source)
    defender=actor(c,'[WAR01] Duke Ford',front)
    heir=actor(c,'[WAR01] Ford Heir',front)
    ap=polity(c,'[WAR01] Northern Crown',source,attacker,75)
    dp=polity(c,'[WAR01] Ford Duchy',front,defender,45)
    c.execute("INSERT INTO territorial_control(location_id,controller_polity_id,since_day) VALUES (?,?,0)",(source,ap))
    c.execute("INSERT INTO territorial_control(location_id,controller_polity_id,since_day) VALUES (?,?,0)",(front,dp))
    add_succession_claim(c,dp,heir,legitimacy=85,support=80,priority=90)
    configure_military_logistics_profile(c,ap,source_location_id=source,food_fodder_capacity=75,medical_capacity=65,equipment_capacity=70,transport_capacity=75,readiness=80)
    configure_military_logistics_profile(c,dp,source_location_id=front,food_fodder_capacity=60,medical_capacity=55,equipment_capacity=55,transport_capacity=45,readiness=55)

    # Physical military depot stock. Mobilization must reduce these rows; later resupply must require route access.
    depot_owner=actor(c,'[WAR01] Quartermaster',source,'DORMANT')
    depot_hh=create_household(c,'[WAR01] Quartermaster Household',head_actor_id=depot_owner,location_id=source,wealth=30,liquidity=10)
    depot=create_enterprise(c,'[WAR01] Crown Depot','other',owner_actor_id=depot_owner,household_id=depot_hh,location_id=source,cash=100,capital=300)
    grain=ensure_good(c,'war01-grain','Campaign Grain','food',1)
    gear=ensure_good(c,'war01-gear','Campaign Equipment','equipment',5)
    set_market_condition(c,source,grain,supply=90,demand=55); set_market_condition(c,source,gear,supply=80,demand=60)
    grain_stock=int(c.execute("INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day) VALUES (?,?,?,?,0)",(depot,source,grain,900)).lastrowid)
    gear_stock=int(c.execute("INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day) VALUES (?,?,?,?,0)",(depot,source,gear,180)).lastrowid)

    # Civilian world at the future battlefield: property, cargo, and households that can be harmed/displaced.
    witness=actor(c,'[WAR01] Ford Witness',front,'DORMANT')
    witness_hh=create_household(c,'[WAR01] Ford Family',head_actor_id=witness,location_id=front,wealth=12,liquidity=3)
    local_owner=actor(c,'[WAR01] Ford Merchant',front,'DORMANT')
    local_hh=create_household(c,'[WAR01] Ford Merchants',head_actor_id=local_owner,location_id=front,wealth=40,liquidity=15)
    local_shop=create_enterprise(c,'[WAR01] Ford Storehouse','shop',owner_actor_id=local_owner,household_id=local_hh,location_id=front,cash=90,capital=120)
    local_stock=int(c.execute("INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day) VALUES (?,?,?,?,0)",(local_shop,front,grain,120)).lastrowid)
    building=create_building(c,'[WAR01] Ford Warehouse','warehouse',location_id=front,owner_actor_id=local_owner,condition=100,capacity=85)
    c.commit()

    # Political objective becomes a tracked operation, then real forces.
    op=create_campaign_operation(c,'[WAR01] Red Ford Campaign',objective_text='Force passage at Red Ford without occupying the whole duchy.',
                                 origin_location_id=source,target_location_id=front,attacker_polity_id=ap,defender_polity_id=dp,
                                 commander_actor_id=attacker,objective_kind='limited')
    af=add_campaign_force(c,op,'Northern Field Army',personnel=1000,polity_id=ap,current_location_id=source)
    df=add_campaign_force(c,op,'Ford Defence',personnel=700,polity_id=dp,current_location_id=front,role='garrison')
    configure_force_supply(c,af,grain,supply_kind='food',source_enterprise_id=depot,source_location_id=source,weekly_need=100,max_on_hand=200)
    configure_force_supply(c,af,gear,supply_kind='equipment',source_enterprise_id=depot,source_location_id=source,weekly_need=18,max_on_hand=36)
    # Defender ruler is individually tracked inside an otherwise aggregate force.
    add_force_member(c,df,defender,duty_kind='commander',exposure=100)
    # A named subset on the winning side proves wounds/deaths persist individually while the other hundreds stay aggregate.
    attacker_named=[]
    for i in range(20):
        a=actor(c,f'[WAR01] North Named {i+1}',source,'DORMANT'); attacker_named.append(a); add_force_member(c,af,a,exposure=95-i)

    after_mob_grain=float(c.execute("SELECT quantity FROM commercial_stock WHERE id=?",(grain_stock,)).fetchone()[0])
    assert after_mob_grain==700, after_mob_grain
    # March uses the route graph instead of teleporting.
    set_day(c,0); process_due_war(c,0)
    f=c.execute("SELECT * FROM war_campaign_forces WHERE id=?",(af,)).fetchone(); assert int(f['current_location_id'])==source and f['current_route_id']==r1
    set_day(c,2); process_due_war(c,2)
    f=c.execute("SELECT * FROM war_campaign_forces WHERE id=?",(af,)).fetchone(); assert int(f['current_location_id'])==mid
    set_day(c,4); process_due_war(c,4)
    f=c.execute("SELECT * FROM war_campaign_forces WHERE id=?",(af,)).fetchone(); assert int(f['current_location_id'])==front and f['status']=='deployed'

    # Battle is one engagement inside the operation, with aggregate units plus named force members.
    battle=create_battle(c,'[WAR01] Battle of Red Ford',location_id=front,objective='control the ford',stakes=5)
    aside=add_battle_side(c,battle,'North',controller_actor_id=attacker,morale=88,cohesion=86,logistics=82,information_quality=72,reserve_capacity=75,metadata={'polity_id':ap})
    dside=add_battle_side(c,battle,'Ford',controller_actor_id=defender,morale=18,cohesion=16,logistics=48,information_quality=45,reserve_capacity=25,metadata={'polity_id':dp})
    add_battle_unit(c,aside,'North Main',combat_capacity=88,morale=88,cohesion=86,readiness=88)
    add_battle_unit(c,dside,'Ford Main',combat_capacity=38,morale=20,cohesion=18,readiness=48)
    link_operation_engagement(c,op,battle); attach_force_to_battle_side(c,af,aside); attach_force_to_battle_side(c,df,dside)
    process_due_war(c,4)  # registers legacy battle logistics too

    # Cut the real supply road. Existing carried stores can be consumed, but source stock cannot teleport across the closure.
    add_route_condition(c,r2,'closure','enemy cuts Wolf Pass road',5,end_day=80,accessibility=0,delay_factor=1,hazard_pressure=45)
    source_before_cut=float(c.execute("SELECT quantity FROM commercial_stock WHERE id=?",(grain_stock,)).fetchone()[0])
    for day in (11,18,25):
        set_day(c,day); process_due_war(c,day)
    source_after_cut=float(c.execute("SELECT quantity FROM commercial_stock WHERE id=?",(grain_stock,)).fetchone()[0])
    assert source_after_cut==source_before_cut, (source_before_cut,source_after_cut)
    fs=c.execute("SELECT * FROM war_force_supplies WHERE force_id=? AND good_id=?",(af,grain)).fetchone()
    assert float(fs['on_hand']) < 100, dict(fs)
    slog=c.execute("SELECT * FROM campaign_side_logistics WHERE battle_side_id=?",(aside,)).fetchone()
    assert slog and float(slog['route_access'])==0 and float(slog['shortage_pressure'])>0

    # Resolve through the existing battle engine. Deliberately weak Ford side should break/withdraw quickly.
    for _ in range(8):
        row=c.execute("SELECT status FROM combat_engagements WHERE id=?",(battle,)).fetchone()
        if row['status']=='resolved': break
        resolve_battle_round(c,battle)
    eng=c.execute("SELECT * FROM combat_engagements WHERE id=?",(battle,)).fetchone()
    assert eng['status']=='resolved', dict(eng)
    end_day=int(eng['day_ended']); set_day(c,end_day); out=process_due_war(c,end_day)
    assert out['battle_consequences_applied']==1
    # Idempotence: processing again must not re-kill or re-damage.
    process_due_war(c,end_day)
    assert c.execute("SELECT COUNT(*) FROM war_battle_aftermath WHERE engagement_id=?",(battle,)).fetchone()[0]==1

    # Aggregate force losses persist without crystallizing all hundreds of soldiers.
    afrow=c.execute("SELECT * FROM war_campaign_forces WHERE id=?",(af,)).fetchone(); dfrow=c.execute("SELECT * FROM war_campaign_forces WHERE id=?",(df,)).fetchone()
    assert int(afrow['personnel_available'])<1000 and int(dfrow['personnel_available'])<700
    assert int(dfrow['aggregate_killed'])>0 and int(dfrow['aggregate_wounded'])>0
    assert c.execute("SELECT COUNT(*) FROM war_force_members WHERE force_id=?",(df,)).fetchone()[0]==1
    # The tracked defender ruler was among the high-exposure named consequences: household/politics sees real death.
    assert c.execute("SELECT status FROM actors WHERE id=?",(defender,)).fetchone()[0]=='deceased'
    # Winning side also has at least one persistent health consequence among its tracked subset.
    wounded=c.execute("SELECT actor_id,health_condition_id FROM war_force_members WHERE force_id=? AND status='wounded' AND health_condition_id IS NOT NULL",(af,)).fetchall()
    assert wounded and c.execute("SELECT COUNT(*) FROM health_conditions WHERE id=? AND condition_kind='injury'",(int(wounded[0]['health_condition_id']),)).fetchone()[0]==1

    # Ruler death creates a real vacancy and established political succession resolves it.
    process_due_politics(c,end_day,event_logger=lambda **kwargs: 0)
    dpstate=c.execute("SELECT ruler_actor_id,status FROM political_polities WHERE id=?",(dp,)).fetchone()
    assert int(dpstate['ruler_actor_id'])==heir and dpstate['status']=='active', dict(dpstate)

    # Battle changes actual civilian owners, not a war_damage meter.
    assert float(c.execute("SELECT condition FROM buildings WHERE id=?",(building,)).fetchone()[0])<100
    assert c.execute("SELECT COUNT(*) FROM route_conditions WHERE condition_kind='war_damage' AND metadata_json LIKE ?",(f'%{battle}%',)).fetchone()[0]>=1
    assert float(c.execute("SELECT quantity FROM commercial_stock WHERE id=?",(local_stock,)).fetchone()[0])<120
    assert c.execute("SELECT COUNT(*) FROM war_damage_events WHERE engagement_id=?",(battle,)).fetchone()[0]>=2
    assert c.execute("SELECT COUNT(*) FROM war_displacement_events WHERE engagement_id=?",(battle,)).fetchone()[0]>=1

    # A crystallized displaced household enters the existing migration/travel system and moves through real geography.
    disp=c.execute("SELECT * FROM war_displacement_events WHERE engagement_id=? AND migration_plan_id IS NOT NULL ORDER BY id LIMIT 1",(battle,)).fetchone()
    assert disp
    plan=c.execute("SELECT * FROM household_migration_plans WHERE id=?",(int(disp['migration_plan_id']),)).fetchone(); depart=int(plan['planned_day'])
    set_day(c,depart); process_due_household_life(c,depart)
    travel=c.execute("SELECT * FROM travel_plans WHERE subject_kind='household' AND subject_id=? AND status='active'",(int(disp['household_id']),)).fetchone()
    assert travel
    # Complete any routed legs until arrived.
    for _ in range(4):
        tr=c.execute("SELECT * FROM travel_plans WHERE id=?",(int(travel['id']),)).fetchone()
        if tr['status']=='arrived': break
        due=int(tr['next_review_day']); set_day(c,due); process_due_ecology(c,due)
    assert int(c.execute("SELECT location_id FROM households WHERE id=?",(int(disp['household_id']),)).fetchone()[0]) != front

    # Official and eyewitness versions coexist and are not globally injected into actors.
    reports=c.execute("SELECT * FROM war_battle_reports WHERE engagement_id=? ORDER BY id",(battle,)).fetchall()
    assert {str(r['version_kind']) for r in reports}>={'official','eyewitness'}
    official=next(r for r in reports if r['version_kind']=='official' and int(r['recipient_actor_id'])==attacker)
    eyewitness=next(r for r in reports if r['version_kind']=='eyewitness')
    assert official['claim_id'] is None and eyewitness['claim_id'] is None  # queued, not known yet
    first=min(int(official['received_day']),int(eyewitness['received_day'])); set_day(c,first); process_due_war(c,first)
    # Eventually deliver both.
    last=max(int(official['received_day']),int(eyewitness['received_day'])); set_day(c,last); process_due_war(c,last)
    official=c.execute("SELECT * FROM war_battle_reports WHERE id=?",(int(official['id']),)).fetchone(); eyewitness=c.execute("SELECT * FROM war_battle_reports WHERE id=?",(int(eyewitness['id']),)).fetchone()
    assert official['status']=='delivered' and eyewitness['status']=='delivered'
    assert c.execute("SELECT 1 FROM actor_evidence_access WHERE actor_id=? AND evidence_id=?",(attacker,int(official['evidence_id']))).fetchone()
    assert not c.execute("SELECT 1 FROM actor_evidence_access WHERE actor_id=? AND evidence_id=?",(attacker,int(eyewitness['evidence_id']))).fetchone()
    assert c.execute("SELECT 1 FROM actor_evidence_access WHERE actor_id=? AND evidence_id=?",(int(eyewitness['recipient_actor_id']),int(eyewitness['evidence_id']))).fetchone()
    assert not c.execute("SELECT 1 FROM actor_evidence_access WHERE actor_id=? AND evidence_id=?",(int(eyewitness['recipient_actor_id']),int(official['evidence_id']))).fetchone()

    # DEC-01 sees own force records plus the actually received report, not hidden enemy truth.
    candidates=generate_candidates(c,attacker,'STRATEGIC',last,build_actor_context(c,attacker,last))
    warc=[x for x in candidates if x.provider_key=='war']
    assert warc, [(x.provider_key,x.action_kind) for x in candidates]
    chosen=warc[0]
    assert int(chosen.information_basis.get('war_report_id',0))==int(official['id']) and int(official['evidence_id']) in chosen.evidence_ids
    assert 'enemy_personnel' not in chosen.information_basis and 'enemy_supply' not in chosen.information_basis
    # If the candidate is resupply, the still-cut road prevents magical replenishment.
    if chosen.action_kind=='resupply_force':
        before=float(c.execute("SELECT on_hand FROM war_force_supplies WHERE force_id=? AND good_id=?",(af,grain)).fetchone()[0])
        apply_decision(c,attacker,'STRATEGIC',last,candidate_to_proposal(chosen))
        after=float(c.execute("SELECT on_hand FROM war_force_supplies WHERE force_id=? AND good_id=?",(af,grain)).fetchone()[0])
        assert after<=before+1e-9

    # Aftermath survives combat and closes later; it does not reset world damage/casualties.
    opstate=c.execute("SELECT * FROM war_campaign_operations WHERE id=?",(op,)).fetchone(); assert opstate['status']=='aftermath'
    close=int(opstate['next_review_day']); set_day(c,close); process_due_war(c,close)
    assert c.execute("SELECT status FROM war_campaign_operations WHERE id=?",(op,)).fetchone()[0]=='closed'
    assert c.execute("SELECT status FROM buildings WHERE id=?",(building,)).fetchone()[0] in {'active','strained','derelict','destroyed'}
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError: pass
    print('WAR-01 campaign/battle/world-consequences acceptance: PASS')


if __name__=='__main__': run()
