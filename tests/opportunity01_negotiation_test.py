from __future__ import annotations
import json
from engine.db import reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.civilian import create_enterprise
from engine.opportunity import create_proposal,add_term,present_proposal
from engine.interactions import apply_player_response


def add_actor(c,name,loc):
    d=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    aid=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character','horse breeder',?,?,'active','OPP negotiation',0)",(name,loc,loc)).lastrowid)
    c.execute("insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,'ACTIVE',7,.3,.7,?,?,2)",(aid,d,d+7))
    return aid


def main():
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c)
    try:
        day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        loc=int(c.execute("select id from locations where name='Crownhold'").fetchone()[0])
        crown=int(c.execute("select decision_actor_id from polity_government_actors where polity_id=1").fetchone()[0])
        crown_inst=int(c.execute("select institution_actor_id from political_polities where id=1").fetchone()[0])
        breeder=add_actor(c,'OPP Negotiating Breeder',loc)
        e=create_enterprise(c,'OPP Negotiating Stud','estate',owner_actor_id=breeder,location_id=loc,capital=100,cash=50,reputation=80,admin_quality=70,labor_capacity=70,risk_tolerance=45)

        # Rejection closes the proposal and creates no right/transfer.
        p1=create_proposal(c,crown,'first_refusal','horse_breeding','First refusal proposal',proposer_institution_actor_id=crown_inst,target_actor_id=breeder)
        add_term(c,p1,'first_refusal',subject_kind='enterprise',subject_id=e,value={'grantor_kind':'actor','grantor_id':breeder,'grantee_kind':'institution','grantee_id':crown_inst,'scope':{'quality_floor':80}})
        i1=present_proposal(c,p1)
        apply_player_response(c,i1,breeder,'reject',day+1)
        assert c.execute('select status from opportunity_proposals where id=?',(p1,)).fetchone()[0]=='rejected'
        assert not c.execute('select 1 from contractual_rights where source_proposal_id=?',(p1,)).fetchone()
        assert int(c.execute('select owner_actor_id from civilian_enterprises where id=?',(e,)).fetchone()[0])==breeder

        # Counter creates a new linked proposal with changed terms; original is never executed.
        p2=create_proposal(c,crown,'first_refusal','horse_breeding','First refusal proposal',proposer_institution_actor_id=crown_inst,target_actor_id=breeder)
        add_term(c,p2,'first_refusal',subject_kind='enterprise',subject_id=e,value={'grantor_kind':'actor','grantor_id':breeder,'grantee_kind':'institution','grantee_id':crown_inst,'scope':{'quality_floor':80}})
        i2=present_proposal(c,p2)
        res=apply_player_response(c,i2,breeder,'counter',day+2,counter_terms={'title':'Counter: only elite remounts','proposal_term_overrides':[{
            'term_kind':'first_refusal','subject_kind':'enterprise','subject_id':e,
            'value':{'grantor_kind':'actor','grantor_id':breeder,'grantee_kind':'institution','grantee_id':crown_inst,'scope':{'quality_floor':92}}
        }]})
        assert res.status=='countered'
        assert c.execute('select status from opportunity_proposals where id=?',(p2,)).fetchone()[0]=='countered'
        cp=c.execute('select * from opportunity_proposals where parent_proposal_id=? order by id desc limit 1',(p2,)).fetchone()
        assert cp and cp['status']=='pending'
        term=c.execute('select * from opportunity_proposal_terms where proposal_id=?',(int(cp['id']),)).fetchone()
        assert json.loads(term['value_json'])['scope']['quality_floor']==92
        assert not c.execute('select 1 from contractual_rights where source_proposal_id in (?,?)',(p2,int(cp['id']))).fetchone()
        # Crown accepts the counter; only the counter terms execute.
        child=c.execute("select * from interactions where proposer_actor_id=? and recipient_actor_id=? and status='pending' order by id desc limit 1",(breeder,crown)).fetchone()
        assert child
        apply_player_response(c,int(child['id']),crown,'accept',day+3)
        right=c.execute("select * from contractual_rights where source_proposal_id=? and right_kind='first_refusal' and status='active'",(int(cp['id']),)).fetchone()
        assert right and json.loads(right['scope_json'])['quality_floor']==92
        assert not c.execute('select 1 from contractual_rights where source_proposal_id=?',(p2,)).fetchone()
        assert int(c.execute('select owner_actor_id from civilian_enterprises where id=?',(e,)).fetchone()[0])==breeder
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('OPPORTUNITY-01 negotiation/rejection/counter acceptance PASS')
    finally:
        c.close()

if __name__=='__main__': main()
