from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,connect,init_db,reset_db
from engine.business import set_commercial_context,configure_enterprise_business
from engine.civilian import create_household,add_household_member,create_enterprise
from engine.household_life import set_life_profile,add_kinship,mark_actor_deceased,process_due_household_life
from engine.domain_actions import domain_action_options,execute_domain_action,apply_accepted_interaction_domain_action


def actor(c,name,loc,stage='adult'):
    c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id,status) VALUES (?,'character',?,?,'active')",(name,loc,loc))
    aid=int(c.execute('SELECT id FROM actors WHERE name=?',(name,)).fetchone()[0])
    set_life_profile(c,aid,birth_day=-30*365 if stage=='adult' else -10*365,current_household_id=None,family_formation_eligible=(stage=='adult'))
    c.execute('UPDATE actor_life_profiles SET life_stage=? WHERE actor_id=?',(stage,aid))
    return aid


def accepted(c, option, initiator, day=0):
    result=execute_domain_action(c,initiator,option,day)
    iid=int(result['interaction_id'])
    row=c.execute('SELECT * FROM interactions WHERE id=?',(iid,)).fetchone()
    applied=apply_accepted_interaction_domain_action(c,row,day)
    assert applied and not applied.get('blocked'),applied
    return applied


def run():
    assert ENGINE_VERSION in {'0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=34
    reset_db(); init_db()
    with connect() as c:
        c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('Hardtown','city',0)")
        c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('Safeport','city',0)")
        hard=int(c.execute("SELECT id FROM locations WHERE name='Hardtown'").fetchone()[0])
        safe=int(c.execute("SELECT id FROM locations WHERE name='Safeport'").fetchone()[0])
        set_commercial_context(c,hard,security=30,trade_flow=40,health_demand=40,credit_demand=70)
        set_commercial_context(c,safe,security=72,trade_flow=72,health_demand=68,credit_demand=55)
        c.execute("INSERT INTO travel_routes(from_location_id,to_location_id,route_kind,base_days,capacity,reliability,bidirectional,status,metadata_json) VALUES (?,?,'road',4,70,85,1,'open','{}')",(hard,safe))

        # Guardianship is a consequence of real sponsor loss, using an existing same-household adult.
        sponsor=actor(c,'Sponsor Parent',hard)
        survivor=actor(c,'Surviving Parent',hard)
        child=actor(c,'Dependent Child',hard,'child')
        hid=create_household(c,'Test Family',head_actor_id=survivor,location_id=hard,wealth=40,liquidity=20,metadata={'economic_resolution':'QUANTITATIVE'})
        for aid,role,auth,dep in [(sponsor,'parent',70,10),(child,'child',0,100)]: add_household_member(c,hid,aid,role=role,authority=auth,dependency=dep)
        c.execute('UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id IN (?,?,?)',(hid,sponsor,survivor,child))
        add_kinship(c,sponsor,child,'parent',reciprocal_kind='child'); add_kinship(c,survivor,child,'parent',reciprocal_kind='child')
        c.execute("INSERT INTO household_dependencies(household_id,dependent_actor_id,sponsor_actor_id,dependency_kind,support_level,status,started_day) VALUES (?,?,?,'child',90,'active',0)",(hid,child,sponsor))
        mark_actor_deceased(c,sponsor,reason='fixture death')
        c.execute('UPDATE world_state SET current_day=30 WHERE id=1')
        res=process_due_household_life(c,30)
        assert res['guardianship_resolutions']==1,res
        assert c.execute("SELECT 1 FROM guardianships WHERE guardian_actor_id=? AND ward_actor_id=? AND status='active'",(survivor,child)).fetchone()
        assert int(c.execute("SELECT sponsor_actor_id FROM household_dependencies WHERE dependent_actor_id=? AND status='active'",(child,)).fetchone()[0])==survivor
        # Repeat is idempotent.
        assert process_due_household_life(c,30)['guardianship_resolutions']==0

        # Quantitatively resolved household service can arise; structural-only household cannot be used as fake demand.
        head=actor(c,'Hiring Head',hard); worker=actor(c,'Service Seeker',hard)
        staff_h=create_household(c,'Hiring Household',head_actor_id=head,location_id=hard,wealth=100,liquidity=50,staff_capacity=60,metadata={'economic_resolution':'QUANTITATIVE'})
        opts=domain_action_options(c,worker,'ACTIVE',30)
        service=next((o for o in opts if o.kind=='seek_household_service'),None)
        assert service and int(service.payload['household_id'])==staff_h,[o.kind for o in opts]
        a=accepted(c,service,worker,30)
        assert c.execute("SELECT 1 FROM household_service_terms WHERE id=? AND status='active'",(a['service_term_id'],)).fetchone()

        structural_head=actor(c,'Structural Head',hard)
        structural=create_household(c,'Structural Household',head_actor_id=structural_head,location_id=hard,wealth=0,liquidity=0,staff_capacity=90,metadata={'economic_resolution':'STRUCTURAL_ONLY'})
        c.execute("UPDATE households SET status='declining' WHERE id=?",(structural,))
        assert not any(o.kind=='schedule_household_migration' for o in domain_action_options(c,structural_head,'ACTIVE',30))

        # A genuinely declining quantitative household can schedule migration only toward a real better adjacent node.
        c.execute("UPDATE households SET status='declining' WHERE id=?",(staff_h,))
        m=next((o for o in domain_action_options(c,head,'ACTIVE',30) if o.kind=='schedule_household_migration'),None)
        assert m and int(m.payload['destination_location_id'])==safe
        mr=execute_domain_action(c,head,m,30)
        assert c.execute("SELECT 1 FROM household_migration_plans WHERE id=? AND status='planned'",(mr['migration_plan_id'],)).fetchone()

        # Real lender + genuinely cash-stressed owned enterprise -> negotiated credit; then real payment conserves cash.
        owner=actor(c,'Borrower Owner',hard)
        borrower=create_enterprise(c,'Cash-Stressed Shop','shop',owner_actor_id=owner,location_id=hard,capital=40,cash=1,debt=0)
        c.execute("UPDATE civilian_enterprises SET status='strained' WHERE id=?",(borrower,))
        c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id,status) VALUES ('Fixture Loan House','institution',?,?,'active')",(hard,hard))
        lender_actor=int(c.execute("SELECT id FROM actors WHERE name='Fixture Loan House'").fetchone()[0])
        lender=create_enterprise(c,'Fixture Loan House Arm','other',institution_actor_id=lender_actor,location_id=hard,capital=80,cash=60)
        configure_enterprise_business(c,lender,'loan_house',capacity=60)
        credit=next((o for o in domain_action_options(c,owner,'ACTIVE',30) if o.kind=='seek_credit'),None)
        assert credit, [o.kind for o in domain_action_options(c,owner,'ACTIVE',30)]
        lender_before=float(c.execute('SELECT cash FROM civilian_enterprises WHERE id=?',(lender,)).fetchone()[0])
        borrower_before=float(c.execute('SELECT cash FROM civilian_enterprises WHERE id=?',(borrower,)).fetchone()[0])
        cr=accepted(c,credit,owner,30)
        cid=int(cr['credit_agreement_id']); principal=float(cr['principal'])
        assert abs(float(c.execute('SELECT cash FROM civilian_enterprises WHERE id=?',(lender,)).fetchone()[0])-(lender_before-principal))<1e-9
        assert abs(float(c.execute('SELECT cash FROM civilian_enterprises WHERE id=?',(borrower,)).fetchone()[0])-(borrower_before+principal))<1e-9
        outstanding=float(c.execute('SELECT outstanding FROM credit_agreements WHERE id=?',(cid,)).fetchone()[0])
        pay=next((o for o in domain_action_options(c,owner,'ACTIVE',30) if o.kind=='service_credit'),None)
        assert pay
        pr=execute_domain_action(c,owner,pay,30)
        assert float(pr['outstanding'])<outstanding
        assert float(c.execute('SELECT debt FROM civilian_enterprises WHERE id=?',(borrower,)).fetchone()[0])>=0

        # Coverage no longer demands fabricated wards/migrations/loans merely to prove these owners exist.
        from engine.coverage import snapshot_coverage
        cov={x['domain_key']:x for x in snapshot_coverage(c)}
        for key in ('21_guardianship','22_service_migration','32_credit_inheritance'):
            assert cov[key]['mechanism_status']=='RUNNABLE' and cov[key]['blocked_reason']!='not populated',(key,cov[key])
        c.commit()
    print('v0.34.0 family/civilian consequence regression PASS')

if __name__=='__main__': run()
