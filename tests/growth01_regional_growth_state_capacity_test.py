"""GROWTH-01 acceptance: conserved public finance -> information-bounded public action -> real infrastructure/security -> migration."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.civilian import create_household, create_enterprise, ensure_good, set_market_condition
from engine.ecology import add_route, add_route_condition, evaluate_route_leg, process_due_ecology
from engine.expertise import set_actor_competence
from engine.growth import (configure_public_treasury, queue_regional_report, process_due_growth,
                           regional_state, create_public_project, assign_project_household_labor,
                           add_security_assignment)
from engine.decisions import build_actor_context, candidate_to_proposal, apply_decision
from engine.decision_runtime import generate_candidates
from engine.household_life import process_due_household_life


def bootstrap(name: str):
    path=Path(tempfile.gettempdir())/f'{name}_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); return connect(),path


def actor(conn,name,loc,tier='STRATEGIC'):
    aid=int(conn.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id,status) VALUES (?,'character',?,?,'active')",(name,loc,loc)).lastrowid)
    conn.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days,last_review_day,next_review_day) VALUES (?,?,?,?,?)",(aid,tier,30,0,30))
    return aid


def polity(conn,name,loc,ruler,admin=60):
    inst=int(conn.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'institution',?,'active')",(name,loc)).lastrowid)
    conn.execute("INSERT INTO institution_profiles(actor_id,institution_kind) VALUES (?,'state')",(inst,))
    pid=int(conn.execute("""INSERT INTO political_polities(institution_actor_id,polity_kind,ruler_actor_id,administrative_capacity,
                       military_capacity,status,next_review_day) VALUES (?,'county',?,?,45,'active',30)""",(inst,ruler,admin)).lastrowid)
    conn.execute("INSERT INTO territorial_control(location_id,controller_polity_id,since_day) VALUES (?,?,0)",(loc,pid))
    return pid


def set_day(conn,day):
    conn.execute("UPDATE world_state SET current_day=? WHERE id=1",(int(day),))


def funded_case():
    c,path=bootstrap('caerness_growth01_funded')
    county=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[GROWTH01] Fellmarch Backwater','town')").lastrowid)
    outside=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[GROWTH01] Old Road Market','city')").lastrowid)
    rid=add_route(c,county,outside,base_days=4,reliability=45)
    physical=add_route_condition(c,rid,'disrepair','neglected road',0,accessibility=55,delay_factor=1.35,hazard_pressure=0)
    danger=add_route_condition(c,rid,'banditry','roadside predation',0,accessibility=70,delay_factor=1.20,hazard_pressure=35)

    ruler=actor(c,'[GROWTH01] Countess',county)
    set_actor_competence(c,ruler,'administration',72,source_kind='admin')
    pid=polity(c,'[GROWTH01] Fellmarch County',county,ruler,admin=58)
    configure_public_treasury(c,pid,cash=180,tax_rate=.10,toll_rate=.02)

    worker=actor(c,'[GROWTH01] Road Worker',county,'DORMANT')
    wh=create_household(c,'[GROWTH01] Road Workers',head_actor_id=worker,location_id=county,wealth=8,liquidity=1)
    timber_owner=actor(c,'[GROWTH01] Timberer',county,'DORMANT')
    timber_house=create_household(c,'[GROWTH01] Timber Household',head_actor_id=timber_owner,location_id=county,wealth=20,liquidity=8)
    yard=create_enterprise(c,'[GROWTH01] Timber Yard','shop',owner_actor_id=timber_owner,household_id=timber_house,location_id=county,cash=100,capital=80)
    timber=ensure_good(c,'ordinary-timber','Timber','timber',2)
    grain=ensure_good(c,'ordinary-grain','Grain','food',1)
    set_market_condition(c,county,timber,supply=70,demand=40)
    set_market_condition(c,county,grain,supply=65,demand=45)
    set_market_condition(c,outside,grain,supply=15,demand=90)
    stock=int(c.execute("INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day) VALUES (?,?,?,?,0)",(yard,county,timber,80)).lastrowid)

    # Realized sales are the tax base; both account and cash exist before the collection.
    c.execute("INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description) VALUES (?,?,?,?,?)",(yard,1,'revenue',60,'ordinary local sales'))
    c.execute("UPDATE civilian_enterprises SET cash=cash+60 WHERE id=?",(yard,))

    # The bad road is not magically known to the ruler through world truth.
    report=queue_regional_report(c,pid,ruler,county,route_id=rid)
    received=int(c.execute("SELECT received_day FROM regional_administrative_reports WHERE id=?",(report,)).fetchone()[0])
    before=generate_candidates(c,ruler,'STRATEGIC',0,build_actor_context(c,ruler,0))
    assert not [x for x in before if x.provider_key=='growth'], 'undelivered report leaked hidden regional truth into decisions'

    set_day(c,received); process_due_growth(c,received)
    rr=c.execute("SELECT * FROM regional_administrative_reports WHERE id=?",(report,)).fetchone()
    assert rr['status']=='delivered' and rr['claim_id'] is not None and rr['evidence_id'] is not None
    candidates=generate_candidates(c,ruler,'STRATEGIC',received,build_actor_context(c,ruler,received))
    repair=next(x for x in candidates if x.provider_key=='growth' and x.action_kind=='repair_route')
    secure=next(x for x in candidates if x.provider_key=='growth' and x.action_kind=='secure_route')
    assert int(repair.information_basis['regional_report_id'])==report and repair.evidence_ids==(int(rr['evidence_id']),)

    old_route=dict(c.execute("SELECT reliability,base_days FROM travel_routes WHERE id=?",(rid,)).fetchone())
    old_eval=evaluate_route_leg(c,rid,county,day=received)
    old_stock=float(c.execute("SELECT quantity FROM commercial_stock WHERE id=?",(stock,)).fetchone()[0])
    old_worker_liq=float(c.execute("SELECT liquidity FROM households WHERE id=?",(wh,)).fetchone()[0])
    old_supplier_cash=float(c.execute("SELECT cash FROM civilian_enterprises WHERE id=?",(yard,)).fetchone()[0])
    apply_decision(c,ruler,'STRATEGIC',received,candidate_to_proposal(repair))
    apply_decision(c,ruler,'STRATEGIC',received,candidate_to_proposal(secure))
    project=int(c.execute("SELECT id FROM regional_public_projects WHERE polity_id=? AND route_id=? AND project_kind='road_repair'",(pid,rid)).fetchone()[0])
    assert dict(c.execute("SELECT reliability,base_days FROM travel_routes WHERE id=?",(rid,)).fetchone())==old_route, 'authorization changed route before resources/work'

    # Reviews consume actual stock, pay actual households/suppliers and gradually fund the project.
    for day in sorted(set([30, received+30,60,received+60,90,received+90,120,received+120,150,180])):
        set_day(c,day); process_due_growth(c,day)
    proj=c.execute("SELECT * FROM regional_public_projects WHERE id=?",(project,)).fetchone()
    assert proj['status']=='completed', dict(proj)
    assert float(c.execute("SELECT quantity FROM commercial_stock WHERE id=?",(stock,)).fetchone()[0])<old_stock
    assert float(c.execute("SELECT cash FROM civilian_enterprises WHERE id=?",(yard,)).fetchone()[0])>old_supplier_cash-10
    assert float(c.execute("SELECT liquidity FROM households WHERE id=?",(wh,)).fetchone()[0])>old_worker_liq
    assert c.execute("SELECT COUNT(*) FROM regional_project_materials WHERE project_id=?",(project,)).fetchone()[0]>0
    assert c.execute("SELECT COALESCE(SUM(amount),0) FROM regional_fiscal_entries WHERE polity_id=? AND entry_kind='business_tax'",(pid,)).fetchone()[0]>0

    new_route=c.execute("SELECT reliability,base_days FROM travel_routes WHERE id=?",(rid,)).fetchone()
    assert float(new_route['reliability'])>float(old_route['reliability']) and float(new_route['base_days'])<float(old_route['base_days'])
    assert c.execute("SELECT status FROM route_conditions WHERE id=?",(physical,)).fetchone()[0]=='ended'
    # Physical repair does not itself erase crime; funded security is the mechanism for that.
    danger_row=c.execute("SELECT * FROM route_conditions WHERE id=?",(danger,)).fetchone()
    assert float(danger_row['hazard_pressure'])<35
    assert evaluate_route_leg(c,rid,county,day=180)['accessibility']>old_eval['accessibility']

    # Fiscal ledger is conserved relative to configured opening cash (no borrowing in this case).
    cash=float(c.execute("SELECT cash FROM regional_public_treasuries WHERE polity_id=?",(pid,)).fetchone()[0])
    inflow=float(c.execute("SELECT COALESCE(SUM(amount),0) FROM regional_fiscal_entries WHERE polity_id=? AND direction='inflow'",(pid,)).fetchone()[0])
    outflow=float(c.execute("SELECT COALESCE(SUM(amount),0) FROM regional_fiscal_entries WHERE polity_id=? AND direction='outflow'",(pid,)).fetchone()[0])
    assert abs(cash-(180+inflow-outflow))<1e-6,(cash,inflow,outflow)

    # Regional improvement creates an ordinary migration incentive, then the existing routed household system moves the household.
    migrant=actor(c,'[GROWTH01] Pressured Migrant',outside,'DORMANT')
    mh=create_household(c,'[GROWTH01] Pressured Outsiders',head_actor_id=migrant,location_id=outside,wealth=2,liquidity=.5)
    c.execute("UPDATE households SET status='declining' WHERE id=?",(mh,))
    c.execute("""INSERT INTO location_commercial_context(location_id,trade_flow,security,foot_traffic,traveler_flow,updated_day)
                 VALUES (?,5,5,10,10,180) ON CONFLICT(location_id) DO UPDATE SET trade_flow=5,security=5,foot_traffic=10,traveler_flow=10,updated_day=180""",(outside,))
    # Make 180 a treasury review so the quarterly response runs after the improved local context has been rebuilt.
    c.execute("UPDATE regional_public_treasuries SET next_review_day=180 WHERE polity_id=?",(pid,))
    set_day(c,180); out=process_due_growth(c,180)
    assert out['migrations']>=1
    mp=c.execute("SELECT * FROM household_migration_plans WHERE household_id=? ORDER BY id DESC LIMIT 1",(mh,)).fetchone()
    assert mp and int(mp['destination_location_id'])==county and mp['status']=='planned'
    depart=int(mp['planned_day']); set_day(c,depart); process_due_household_life(c,depart)
    mp=c.execute("SELECT * FROM household_migration_plans WHERE id=?",(int(mp['id']),)).fetchone()
    assert mp['status']=='in_transit'
    travel=c.execute("SELECT * FROM travel_plans WHERE subject_kind='household' AND subject_id=? AND status='active'",(mh,)).fetchone()
    assert travel
    arrive=int(travel['segment_due_day']); set_day(c,arrive); process_due_ecology(c,arrive)
    assert int(c.execute("SELECT location_id FROM households WHERE id=?",(mh,)).fetchone()[0])==county
    assert c.execute("SELECT status FROM household_migration_plans WHERE id=?",(int(mp['id']),)).fetchone()[0]=='completed'

    # Ten-year bounded run: recurring real business activity can support security/public capacity; snapshots remain causal fields, no prosperity column exists.
    current=arrive
    for _ in range(120):
        current+=30; set_day(c,current)
        c.execute("INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description) VALUES (?,?,?,?,?)",(yard,current,'revenue',100,'long-horizon commercial activity'))
        c.execute("UPDATE civilian_enterprises SET cash=cash+100 WHERE id=?",(yard,))
        c.execute("UPDATE regional_public_treasuries SET next_review_day=MIN(next_review_day,?) WHERE polity_id=?",(current,pid))
        process_due_growth(c,current)
    end_state=regional_state(c,pid,county,day=current)
    assert end_state['public_debt']==0 and end_state['treasury_cash']>0
    assert c.execute("SELECT COUNT(*) FROM regional_growth_snapshots WHERE polity_id=? AND location_id=?",(pid,county)).fetchone()[0]>=100
    assert not [r for r in c.execute("PRAGMA table_info(regional_growth_snapshots)").fetchall() if 'prosper' in str(r[1]).lower() or 'development_score' in str(r[1]).lower()]
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close();
    try:path.unlink()
    except FileNotFoundError:pass
    return {'route_access_before':old_eval['accessibility'],'route_access_after':end_state['route_accessibility'],'treasury_cash':end_state['treasury_cash']}


def constrained_case():
    c,path=bootstrap('caerness_growth01_constrained')
    a=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[GROWTH01] Debt County','town')").lastrowid)
    b=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[GROWTH01] Debt Neighbor','town')").lastrowid)
    rid=add_route(c,a,b,base_days=4,reliability=45)
    add_route_condition(c,rid,'disrepair','unfunded road',0,accessibility=50,delay_factor=1.5,hazard_pressure=0)
    add_route_condition(c,rid,'banditry','persistent bandits',0,accessibility=60,delay_factor=1.3,hazard_pressure=40)
    ruler=actor(c,'[GROWTH01] Indebted Count',a); pid=polity(c,'[GROWTH01] Debt County Polity',a,ruler,admin=35)
    configure_public_treasury(c,pid,cash=2,debt=100,tax_rate=.05,debt_interest_rate_per_30=.02)
    material=ensure_good(c,'growth01_absent_stone','Building Stone','construction',3)
    worker=actor(c,'[GROWTH01] Debt Worker',a,'DORMANT'); hh=create_household(c,'[GROWTH01] Debt Workers',head_actor_id=worker,location_id=a,liquidity=1)
    project=create_public_project(c,pid,a,'road_repair','Unfunded road repair',route_id=rid,required_cash=30,required_labor_days=20,
                                  material_good_id=material,required_material_quantity=20,effects={'reliability_gain':30,'base_days_factor':.8})
    assign_project_household_labor(c,project,hh,labor_days=20,wage_per_day=.5)
    sec=add_security_assignment(c,pid,route_id=rid,location_id=a,monthly_cost=10,strength=50)
    opening_rel=float(c.execute("SELECT reliability FROM travel_routes WHERE id=?",(rid,)).fetchone()[0])
    # Ten-year stressed case: no supplier/material or revenue arrives, so debt service, project and security cannot be wished into existence.
    for day in range(30,3651,30):
        set_day(c,day); c.execute("UPDATE regional_public_treasuries SET next_review_day=MIN(next_review_day,?) WHERE polity_id=?",(day,pid)); process_due_growth(c,day)
    t=c.execute("SELECT * FROM regional_public_treasuries WHERE polity_id=?",(pid,)).fetchone()
    p=c.execute("SELECT * FROM regional_public_projects WHERE id=?",(project,)).fetchone()
    s=c.execute("SELECT * FROM regional_security_assignments WHERE id=?",(sec,)).fetchone()
    assert float(t['debt'])>100 and t['status']=='strained'
    assert p['status']=='blocked' and 'materials' in str(p['blocked_reason'])
    assert s['status']=='unfunded'
    assert float(c.execute("SELECT reliability FROM travel_routes WHERE id=?",(rid,)).fetchone()[0])==opening_rel
    assert c.execute("SELECT status FROM route_conditions WHERE route_id=? AND condition_kind='banditry'",(rid,)).fetchone()[0]=='active'
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    debt=float(t['debt']); c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError:pass
    return debt


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=66
    healthy=funded_case(); debt=constrained_case()
    assert healthy['route_access_after']>healthy['route_access_before'] and debt>100
    print('GROWTH-01 regional growth/state-capacity acceptance: PASS',healthy,'constrained_debt',round(debt,2))

if __name__=='__main__': run()
