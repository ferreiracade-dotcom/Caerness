from __future__ import annotations
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, SCHEMA_VERSION, connect, init_db, reset_db
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.decisions import decide_actor
from engine.domain_actions import domain_action_options, execute_domain_action, apply_accepted_interaction_domain_action
from engine.business import set_commercial_context
from engine.civilian import ensure_career_track, create_enterprise
from engine.health import add_condition, ensure_health_profile
from engine.expertise import set_actor_competence
from engine.interactions import create_interaction
from engine.coverage import snapshot_coverage
from engine.continuity import set_institution_profile
from engine.competence import add_obligation

SEED=ROOT/'game'/'seeds'/'Caerness_Initial_World_State_Seed_v1_4.json'

def _actor(c,name,loc,tier='ACTIVE'):
    aid=c.execute("INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status) VALUES (?,'character','fixture',?,?,'active')",(name,loc,loc)).lastrowid
    c.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) VALUES (?,?,30,.25,.5,0,30,3)",(aid,tier))
    c.execute("INSERT INTO actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) VALUES (?,-10950,'adult',1,'living',0,'{}')",(aid,))
    ensure_health_profile(c,aid)
    return int(aid)

def run():
    assert ENGINE_VERSION in {'0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=28
    reset_db(); init_db()
    with connect() as c:
        # Current-canon active training now produces an authoritative domain decision rather than generic consolidation.
        imported=import_current_seed(c,SEED); assert imported['persons']==464
        activate_existing_loops(c)
        row=c.execute("SELECT e.actor_id,e.id,e.practice_quality,sp.tier FROM education_enrollments e JOIN simulation_profiles sp ON sp.actor_id=e.actor_id WHERE e.status='active' ORDER BY e.id LIMIT 1").fetchone()
        assert row
        c.execute("UPDATE world_state SET current_day=180 WHERE id=1")
        before=float(row['practice_quality'])
        did=decide_actor(c,int(row['actor_id']),str(row['tier']),180)
        d=c.execute("SELECT * FROM decisions WHERE id=?",(did,)).fetchone()
        assert d['action_type']=='domain_action', dict(d)
        after=float(c.execute("SELECT practice_quality FROM education_enrollments WHERE id=?",(row['id'],)).fetchone()[0])
        assert 0.70 <= after <= 1.30 and abs(after-before)>1e-9
        assert c.execute("SELECT COUNT(*) FROM autonomous_action_attempts WHERE actor_id=? AND action_kind='adjust_training_effort' AND status='applied'",(row['actor_id'],)).fetchone()[0]==1

        # An institution can offer a real open place to a grounded current-source pupil; acceptance owns enrollment.
        e=c.execute("""SELECT e.id,e.actor_id,e.program_id,p.institution_actor_id FROM education_enrollments e
                       JOIN education_programs p ON p.id=e.program_id
                       JOIN source_identity_map sim ON sim.entity_kind='actor' AND sim.entity_id=e.actor_id
                        AND sim.source_namespace='caerness_seed_v1_1'
                       WHERE e.status='active' AND p.institution_actor_id IS NOT NULL ORDER BY e.id LIMIT 1""").fetchone()
        assert e
        c.execute("DELETE FROM education_enrollments WHERE id=?",(e['id'],))
        inst=int(e['institution_actor_id'])
        opts=domain_action_options(c,inst,'STRATEGIC',180,drives={'ambition':.5,'risk_tolerance':.5,'patience':.5,'pragmatism':.5})
        admission=next(o for o in opts if o.kind=='admit_pupil')
        rr=execute_domain_action(c,inst,admission,180)
        ii=c.execute("SELECT * FROM interactions WHERE id=?",(rr['interaction_id'],)).fetchone()
        applied=apply_accepted_interaction_domain_action(c,ii,181)
        assert applied and not applied.get('blocked')
        assert c.execute("SELECT COUNT(*) FROM education_enrollments WHERE actor_id=? AND program_id=? AND status='active'",(admission.target_actor_id,admission.payload['program_id'])).fetchone()[0]==1

    # Isolated fixture: real capital + explicit local demand can found an enterprise through the decision layer.
    reset_db(); init_db()
    with connect() as c:
        loc=c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('Fixture Port','city',0)").lastrowid
        founder=_actor(c,'Fixture Merchant',loc)
        c.execute("INSERT INTO resources(actor_id,resource_type,amount,unit,updated_day) VALUES (?,'capital',60,'abstract capital',0)",(founder,))
        set_commercial_context(c,loc,traveler_flow=90,trade_flow=75,foot_traffic=70,security=70)
        did=decide_actor(c,founder,'ACTIVE',30)
        d=c.execute("SELECT action_type FROM decisions WHERE id=?",(did,)).fetchone()[0]
        assert d=='domain_action'
        ent=c.execute("SELECT * FROM civilian_enterprises WHERE owner_actor_id=?",(founder,)).fetchone()
        assert ent and ent['status']=='active'
        assert c.execute("SELECT COUNT(*) FROM enterprise_business_profiles WHERE enterprise_id=?",(ent['id'],)).fetchone()[0]==1
        assert float(c.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type='capital'",(founder,)).fetchone()[0]) < 60
        cov={x['domain_key']:x for x in snapshot_coverage(c)}
        assert cov['29_business_lifecycle']['mechanism_status']=='PARTIAL'
        assert cov['29_business_lifecycle']['blocked_reason'] != 'autonomous initiation missing'

    # Accepted bilateral health request invokes the health owner rather than merely creating an agreement.
    reset_db(); init_db()
    with connect() as c:
        loc=c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('Fixture Clinic','city',0)").lastrowid
        patient=_actor(c,'Fixture Patient',loc)
        provider=_actor(c,'Fixture Physician',loc)
        set_actor_competence(c,provider,'medicine',70,source_kind='campaign')
        cid=add_condition(c,patient,'illness','Fixture fever',severity=55,specialist_requirement='physician',recovery_rate_per_30=2)
        opts=domain_action_options(c,patient,'ACTIVE',0,drives={'ambition':.5,'risk_tolerance':.5,'patience':.5,'pragmatism':.8})
        opt=next(o for o in opts if o.kind=='seek_treatment')
        result=execute_domain_action(c,patient,opt,0)
        interaction=c.execute("SELECT * FROM interactions WHERE id=?",(result['interaction_id'],)).fetchone()
        applied=apply_accepted_interaction_domain_action(c,interaction,1)
        assert applied and not applied.get('blocked')
        assert c.execute("SELECT COUNT(*) FROM medical_treatments WHERE actor_id=? AND condition_id=? AND provider_actor_id=? AND status='active'",(patient,cid,provider)).fetchone()[0]==1

        # Household formation is never roster-filling: it needs explicit eligibility + a sustained positive relationship.
        partner=_actor(c,'Fixture Partner',loc)
        c.execute("INSERT INTO relationships(actor_a_id,actor_b_id,stance,trust,obligation,updated_day) VALUES (?,?,?,?,?,?)",(patient,partner,35,45,5,-240))
        opts=domain_action_options(c,patient,'ACTIVE',0,drives={'ambition':.5,'risk_tolerance':.5,'patience':.5,'pragmatism':.5})
        union=next(o for o in opts if o.kind=='propose_union')
        r=execute_domain_action(c,patient,union,0)
        i=c.execute("SELECT * FROM interactions WHERE id=?",(r['interaction_id'],)).fetchone()
        applied=apply_accepted_interaction_domain_action(c,i,1)
        assert applied and not applied.get('blocked')
        assert c.execute("SELECT COUNT(*) FROM household_unions WHERE status='active' AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))",(patient,partner,partner,patient)).fetchone()[0]==1
        cov={x['domain_key']:x for x in snapshot_coverage(c)}
        assert cov['19_new_unions']['mechanism_status']=='PARTIAL'
        assert cov['19_new_unions']['blocked_reason'] != 'autonomous initiation missing'
        c.commit()

    # Career seeking, obligation renegotiation, and distressed-enterprise sale use real configured state.
    reset_db(); init_db()
    with connect() as c:
        loc=c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('Fixture Market','city',0)").lastrowid
        guild=c.execute("INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status) VALUES ('Fixture Guild','institution','guild',?,?,'active')",(loc,loc)).lastrowid
        set_institution_profile(c,int(guild),'guild',primary_location_id=int(loc),culture={},pipeline={},capacity={},trajectory='stable')
        track=ensure_career_track(c,'fixture-clerk','Fixture Clerk','commerce',institution_kind='guild',stages=[{'key':'entry','name':'Entry','requirements':{'competence_domain':'commerce','min_competence':20}}])
        worker=_actor(c,'Fixture Worker',loc)
        set_actor_competence(c,worker,'commerce',45,source_kind='campaign')
        opts=domain_action_options(c,worker,'ACTIVE',0,drives={'ambition':.6,'risk_tolerance':.4,'patience':.5,'pragmatism':.7})
        work=next(o for o in opts if o.kind=='seek_work')
        rr=execute_domain_action(c,worker,work,0)
        ii=c.execute("SELECT * FROM interactions WHERE id=?",(rr['interaction_id'],)).fetchone()
        applied=apply_accepted_interaction_domain_action(c,ii,1)
        assert applied and c.execute("SELECT COUNT(*) FROM actor_careers WHERE actor_id=? AND institution_actor_id=? AND status='active'",(worker,guild)).fetchone()[0]==1

        counter=_actor(c,'Fixture Creditor',loc)
        oid=add_obligation(c,worker,'Deliver agreed records',counterparty_actor_id=counter,due_day=10,importance=4)
        opts=domain_action_options(c,worker,'ACTIVE',0,drives={'ambition':.5,'risk_tolerance':.5,'patience':.5,'pragmatism':.8})
        reneg=next(o for o in opts if o.kind=='renegotiate_obligation')
        rr=execute_domain_action(c,worker,reneg,0)
        ii=c.execute("SELECT * FROM interactions WHERE id=?",(rr['interaction_id'],)).fetchone()
        applied=apply_accepted_interaction_domain_action(c,ii,1)
        assert applied and int(c.execute("SELECT due_day FROM obligations WHERE id=?",(oid,)).fetchone()[0])>10

        seller=_actor(c,'Fixture Seller',loc)
        buyer=_actor(c,'Fixture Buyer',loc)
        c.execute("UPDATE actor_life_profiles SET family_formation_eligible=0 WHERE actor_id IN (?,?)",(seller,buyer))
        c.execute("INSERT INTO relationships(actor_a_id,actor_b_id,stance,trust,obligation,updated_day) VALUES (?,?,?,?,?,?)",(seller,buyer,15,25,0,0))
        c.execute("INSERT INTO resources(actor_id,resource_type,amount,unit,updated_day) VALUES (?,'capital',100,'fixture coin',0)",(buyer,))
        eid=create_enterprise(c,'Distressed Fixture','shop',owner_actor_id=seller,location_id=loc,capital=30,cash=5,debt=20,reputation=30,admin_quality=35,labor_capacity=25,risk_tolerance=40)
        c.execute("UPDATE civilian_enterprises SET status='strained' WHERE id=?",(eid,))
        opts=domain_action_options(c,seller,'ACTIVE',0,drives={'ambition':.4,'risk_tolerance':.3,'patience':.5,'pragmatism':.9})
        sale=next(o for o in opts if o.kind=='sell_enterprise')
        price=float(sale.payload['price'])
        rr=execute_domain_action(c,seller,sale,0)
        ii=c.execute("SELECT * FROM interactions WHERE id=?",(rr['interaction_id'],)).fetchone()
        applied=apply_accepted_interaction_domain_action(c,ii,1)
        assert applied and int(c.execute("SELECT owner_actor_id FROM civilian_enterprises WHERE id=?",(eid,)).fetchone()[0])==buyer
        assert float(c.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type='capital'",(buyer,)).fetchone()[0])==100-price
        assert float(c.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type='capital'",(seller,)).fetchone()[0])==price
        c.commit()
    print('v0.28.0 autonomous domain-actions regression PASS')

if __name__=='__main__': run()
