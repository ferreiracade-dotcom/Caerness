"""INTEGRATION-01 acceptance: care capacity, harvest/weather propagation, and general law procedure."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.health import (add_condition, create_care_site, assign_care_provider, request_care, process_due_health)
from engine.civilian import create_household, create_enterprise, ensure_good, set_market_condition
from engine.ecology import configure_environment, add_environmental_condition, add_route
from engine.agriculture import create_field, process_due_agriculture
from engine.growth import configure_public_treasury, regional_state
from engine.law import create_jurisdiction, add_rule, create_office, resolve_jurisdiction, file_case, add_case_evidence, process_due_law


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_integration01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); return connect(),path

def set_day(c,d): c.execute("UPDATE world_state SET current_day=? WHERE id=1",(int(d),))

def actor(c,name,loc):
    return int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id,status) VALUES (?,'character',?,?,'active')",(name,loc,loc)).lastrowid)

def polity(c,name,loc,ruler):
    inst=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'institution',?,'active')",(name,loc)).lastrowid)
    c.execute("INSERT INTO institution_profiles(actor_id,institution_kind) VALUES (?,'state')",(inst,))
    return int(c.execute("""INSERT INTO political_polities(institution_actor_id,polity_kind,ruler_actor_id,administrative_capacity,military_capacity,status,next_review_day)
                            VALUES (?,'kingdom',?,70,55,'active',30)""",(inst,ruler)).lastrowid)

def competence(c,aid,domain,score):
    did=int(c.execute("SELECT id FROM competence_domains WHERE domain_key=?",(domain,)).fetchone()[0])
    c.execute("INSERT INTO actor_competence(actor_id,domain_id,score,source_kind,updated_day) VALUES (?,?,?,'generated',0)",(aid,did,score))


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=68
    c,path=bootstrap()
    town=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[INT01] Market Town','town')").lastrowid)
    country=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[INT01] Grain Vale','village')").lastrowid)
    add_route(c,town,country,base_days=2,reliability=90)

    # HEALTH-01: two equally serious injuries, but only one patient has accessible care.
    healer=actor(c,'[INT01] Physician',town); competence(c,healer,'medicine',90)
    patient_fast=actor(c,'[INT01] Early Patient',town); patient_slow=actor(c,'[INT01] Delayed Patient',town)
    c1=add_condition(c,patient_fast,'injury','serious fracture',severity=62,body_system='limb',capacity_impact=45,pain_impact=55,
                     recovery_rate_per_30=2,progression_rate_per_30=18,next_review_days=7,metadata={'can_leave_disability':True})
    c2=add_condition(c,patient_slow,'injury','serious fracture',severity=62,body_system='limb',capacity_impact=45,pain_impact=55,
                     recovery_rate_per_30=2,progression_rate_per_30=18,next_review_days=7,metadata={'can_leave_disability':True})
    open_site=create_care_site(c,'int01-open','[INT01] Town Physic',location_id=town,quality=90,capacity_per_day=1)
    closed_site=create_care_site(c,'int01-closed','[INT01] Shuttered Ward',location_id=town,quality=90,capacity_per_day=1,status='closed')
    assign_care_provider(c,open_site,healer,domain_key='medicine',capacity_per_day=1)
    assign_care_provider(c,closed_site,healer,domain_key='medicine',capacity_per_day=1)
    request_care(c,patient_fast,c1,site_id=open_site,treatment_kind='ordinary_medicine',urgency=80)
    request_care(c,patient_slow,c2,site_id=closed_site,treatment_kind='ordinary_medicine',urgency=80)
    for d in (1,7,21): set_day(c,d); process_due_health(c,d)
    fast=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(c1,)).fetchone()[0])
    slow=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(c2,)).fetchone()[0])
    assert slow>fast+1.0,(fast,slow)
    req=c.execute("SELECT * FROM health_care_requests WHERE condition_id=?",(c2,)).fetchone()
    assert req['status']=='waiting' and int(req['delay_days'])>=20
    c.execute("UPDATE health_care_sites SET status='active' WHERE id=?",(closed_site,))
    set_day(c,22); process_due_health(c,22)
    req=c.execute("SELECT * FROM health_care_requests WHERE condition_id=?",(c2,)).fetchone()
    assert req['status']=='treated' and int(req['treated_day'])==22

    # AGRI-01: drought affects a real field -> physical grain stock + local market + GROWTH food stress.
    farmer=actor(c,'[INT01] Farmer',country)
    hh=create_household(c,'[INT01] Farm Household',head_actor_id=farmer,location_id=country,wealth=25,liquidity=2)
    farm=create_enterprise(c,'[INT01] Vale Farm','estate',owner_actor_id=farmer,household_id=hh,location_id=country,cash=40,capital=120,labor_capacity=80)
    grain=ensure_good(c,'ordinary-grain','Ordinary Grain','food',1)
    set_market_condition(c,country,grain,supply=80,demand=80)
    configure_environment(c,country,climate_label='temperate',terrain_kind='farmland',year_length=365)
    add_environmental_condition(c,country,'drought','[INT01] hard drought',0,end_day=200,production_factor=.25,health_pressure=8)
    field=create_field(c,'int01-field','[INT01] South Field',enterprise_id=farm,location_id=country,crop_good_id=grain,
                       hectares=10,base_yield_per_hectare=10,soil_quality=80,labor_capacity=80,harvest_day_of_year=30,next_harvest_day=30)
    ruler=actor(c,'[INT01] Grain Lord',country); pid=polity(c,'[INT01] Vale Lordship',country,ruler)
    c.execute("INSERT INTO territorial_control(location_id,controller_polity_id,since_day) VALUES (?,?,0)",(country,pid))
    configure_public_treasury(c,pid,cash=100,tax_rate=.05)
    before_price=float(c.execute("SELECT current_price FROM market_conditions WHERE location_id=? AND good_id=?",(country,grain)).fetchone()[0])
    before_stress=float(regional_state(c,pid,country,day=29)['food_stress'])
    set_day(c,30); out=process_due_agriculture(c,30)
    harvest=c.execute("SELECT * FROM agriculture_harvests WHERE field_id=?",(field,)).fetchone()
    assert out['poor_harvests']==1 and float(harvest['actual_quantity']) < float(harvest['expected_quantity'])*.3,dict(harvest)
    stock=float(c.execute("SELECT quantity FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",(farm,country,grain)).fetchone()[0])
    assert abs(stock-float(harvest['actual_quantity']))<1e-6
    after_market=c.execute("SELECT * FROM market_conditions WHERE location_id=? AND good_id=?",(country,grain)).fetchone()
    assert float(after_market['current_price'])>before_price and float(after_market['supply'])<80,dict(after_market)
    after_stress=float(regional_state(c,pid,country,day=30)['food_stress'])
    assert after_stress>before_stress and after_stress>0,(before_stress,after_stress)

    # LAW-01: local charter law outranks kingdom law, then evidence/capacity/delay -> judgment -> real cash enforcement.
    buyer_owner=actor(c,'[INT01] Buyer Owner',town); seller_owner=actor(c,'[INT01] Seller Owner',town)
    bh=create_household(c,'[INT01] Buyer House',head_actor_id=buyer_owner,location_id=town,wealth=30,liquidity=20)
    sh=create_household(c,'[INT01] Seller House',head_actor_id=seller_owner,location_id=town,wealth=30,liquidity=20)
    buyer=create_enterprise(c,'[INT01] Buyer Co','merchant_house',owner_actor_id=buyer_owner,household_id=bh,location_id=town,cash=20,capital=80)
    seller=create_enterprise(c,'[INT01] Seller Co','merchant_house',owner_actor_id=seller_owner,household_id=sh,location_id=town,cash=100,capital=80)
    king=actor(c,'[INT01] King',town); kpid=polity(c,'[INT01] Kingdom',town,king)
    c.execute("INSERT INTO territorial_control(location_id,controller_polity_id,since_day) VALUES (?,?,0)",(town,kpid))
    kj=create_jurisdiction(c,'int01-king-law','[INT01] Kingdom Law','kingdom',polity_id=kpid,priority=40)
    kr=add_rule(c,kj,'contract-default','Kingdom Contract Rule','contract',evidence_threshold=70,default_remedy='damages')
    cj=create_jurisdiction(c,'int01-charter-law','[INT01] Town Charter','charter',location_id=town,priority=80)
    cr=add_rule(c,cj,'merchant-breach','Charter Merchant Breach','contract',evidence_threshold=50,default_remedy='damages')
    magistrate=actor(c,'[INT01] Magistrate',town)
    office=create_office(c,'int01-court','[INT01] Charter Court',cj,location_id=town,presiding_actor_id=magistrate,capacity=85,integrity=90,corruption_pressure=5)
    resolved=resolve_jurisdiction(c,town,'contract')
    assert resolved==(cj,cr),resolved
    case=file_case(c,location_id=town,matter_kind='contract',claim_text='Seller failed a paid delivery.',
                   claimant_enterprise_id=buyer,respondent_enterprise_id=seller,subject_kind='commercial_dispute',subject_id=1,amount_claimed=40)
    add_case_evidence(c,case,'written_contract','Signed contract and receipt.',strength=100,source_kind='record',source_id=1)
    # Each procedural stage respects its own next_review_day rather than resolving instantly.
    stages=[]
    for _ in range(6):
        row=c.execute("SELECT * FROM law_cases WHERE id=?",(case,)).fetchone();
        if row['status']=='closed': break
        d=int(row['next_review_day']); set_day(c,d); process_due_law(c,d); stages.append(c.execute("SELECT status FROM law_cases WHERE id=?",(case,)).fetchone()[0])
    assert 'evidence' in stages and 'hearing' in stages and 'decided' in stages and 'enforcement' in stages and stages[-1]=='closed',stages
    judgment=c.execute("SELECT * FROM law_judgments WHERE case_id=?",(case,)).fetchone()
    assert judgment['finding']=='claimant' and float(judgment['amount_enforced'])==40 and judgment['status']=='enforced',dict(judgment)
    assert float(c.execute("SELECT cash FROM civilian_enterprises WHERE id=?",(buyer,)).fetchone()[0])==60
    assert float(c.execute("SELECT cash FROM civilian_enterprises WHERE id=?",(seller,)).fetchone()[0])==60
    assert c.execute("SELECT COUNT(*) FROM actor_beliefs WHERE actor_id IN (?,?) AND claim_id IN (SELECT id FROM information_claims WHERE subject_kind='law_case' AND subject_id=?)",(buyer_owner,seller_owner,case)).fetchone()[0]==2

    # Capacity is causal: a second case assigned to a collapsed office stalls instead of jumping to judgment.
    c.execute("UPDATE law_offices SET capacity=5,status='strained' WHERE id=?",(office,))
    case2=file_case(c,location_id=town,matter_kind='contract',claim_text='Second dispute with no functioning docket.',
                    claimant_enterprise_id=buyer,respondent_enterprise_id=seller,subject_kind='commercial_dispute',subject_id=2,amount_claimed=10)
    add_case_evidence(c,case2,'written_record','Clear written record.',strength=100)
    d=int(c.execute("SELECT next_review_day FROM law_cases WHERE id=?",(case2,)).fetchone()[0]); set_day(c,d); process_due_law(c,d)
    assert c.execute("SELECT status FROM law_cases WHERE id=?",(case2,)).fetchone()[0]=='stalled'

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError: pass
    print('INTEGRATION-01 health/agriculture/law acceptance: PASS')

if __name__=='__main__': run()
