from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.civilian import create_enterprise, add_production_site
from engine.business import configure_enterprise_business
from engine.attention import ensure_horse_breeder_attention, process_attention_case
from engine.interactions import apply_player_response, process_due_interactions


def setup_world():
    reset_db(force=True, backup=False)
    init_db()
    c=connect()
    import_current_seed(c)
    activate_existing_loops(c)
    c.commit()
    return c


def add_actor(c,name,subtype,loc,tier='ACTIVE'):
    day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    aid=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character',?,?,?,'active','ATTENTION-01 acceptance actor',0)",(name,subtype,loc,loc)).lastrowid)
    c.execute("insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,?,7,.3,.75,?,?,2)",(aid,tier,day,day+7))
    return aid


def main():
    c=setup_world()
    try:
        assert int(c.execute("select value from engine_meta where key='schema_version'").fetchone()[0])>=84
        day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        crownhold=int(c.execute("select id from locations where name='Crownhold'").fetchone()[0])
        horses=int(c.execute("select id from market_goods where good_key='horses_remounts'").fetchone()[0])
        breeder=add_actor(c,'ATTENTION Test Breeder','horse breeder',crownhold)
        c.execute("insert or replace into player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) values (1,?,?,?,?)",(breeder,crownhold,'ATTENTION breeder acceptance',day))
        eid=create_enterprise(c,'ATTENTION Test Stud','estate',owner_actor_id=breeder,location_id=crownhold,capital=220,cash=120,reputation=92,admin_quality=82,labor_capacity=75,risk_tolerance=40)
        configure_enterprise_business(c,eid,'horse_breeder',quality=93,capacity=78,clientele_fit=90,service_reliability=92)
        add_production_site(c,eid,horses,capacity_per_30=16,efficiency=90,material_access=82,skilled_labor=93,inventory=36)

        assert ensure_horse_breeder_attention(c,day)==1
        case=c.execute("select * from strategic_attention_cases where target_actor_id=? and interest_kind='appoint'",(breeder,)).fetchone()
        assert case and float(case['salience'])>=64
        res=process_attention_case(c,int(case['id']),day)
        assert res['action']=='opportunity_offer'
        interaction=c.execute("select * from interactions where id=?",(int(res['interaction_id']),)).fetchone()
        assert str(interaction['interaction_type'])=='offer' and str(interaction['status'])=='pending'
        # Incoming strategic opportunities never auto-answer the player.
        process_due_interactions(c,day+30)
        assert c.execute("select status from interactions where id=?",(int(interaction['id']),)).fetchone()[0]=='pending'
        apply_player_response(c,int(interaction['id']),breeder,'accept',day+1)
        appt=c.execute("select * from institutional_appointments where holder_actor_id=? and status='active'",(breeder,)).fetchone()
        assert appt and str(appt['appointment_key'])=='state_remount_master'
        assert c.execute("select 1 from institution_memberships where member_actor_id=? and membership_kind='appointed_office' and status='active'",(breeder,)).fetchone()
        # The Crown Horsebreeder offer is an incorporation, not a side appointment: the Crown takes the stud while the breeder remains operator/master.
        ent=c.execute("select owner_actor_id,status from civilian_enterprises where id=?",(eid,)).fetchone()
        assert ent['owner_actor_id'] is None and str(ent['status'])=='active'
        crown=int(c.execute("select institution_actor_id from political_polities where id=1").fetchone()[0])
        assert c.execute("select 1 from enterprise_control_interests where enterprise_id=? and interest_kind='legal_owner' and holder_institution_actor_id=? and status='active'",(eid,crown)).fetchone()
        assert c.execute("select 1 from enterprise_control_interests where enterprise_id=? and interest_kind='operator' and holder_actor_id=? and status='active'",(eid,breeder)).fetchone()
        assert c.execute("select status from strategic_attention_cases where id=?",(int(case['id']),)).fetchone()[0]=='fulfilled'

        # Ordinary worlds with no qualifying breeder do not manufacture attention targets.
        other_cases=c.execute("select count(*) from strategic_attention_cases where id<>?",(int(case['id']),)).fetchone()[0]
        assert int(other_cases)==0
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('ATTENTION-01 strategic relevance/appointment acceptance PASS')
    finally:
        c.close()


if __name__=='__main__':
    main()
