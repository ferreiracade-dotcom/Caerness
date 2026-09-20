from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.civilian import create_enterprise, add_production_site
from engine.business import configure_enterprise_business
from engine.seeking import (
    publish_enterprise_offering, publish_personal_instruction,
    ensure_military_remount_intents, create_seek_intent, process_seek_intent,
)
from engine.interactions import apply_player_response
from engine.simulation import advance_connection


def setup_world():
    reset_db(force=True, backup=False)
    init_db()
    c=connect()
    import_current_seed(c)
    activate_existing_loops(c)
    c.commit()
    return c


def add_actor(c,name,subtype,loc,tier='STRATEGIC'):
    day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    aid=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character',?,?,?,'active','SEEK-01 acceptance actor',0)",(name,subtype,loc,loc)).lastrowid)
    c.execute("insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,?,7,.3,.75,?,?,2)",(aid,tier,day,day+7))
    return aid


def main():
    c=setup_world()
    try:
        assert int(c.execute("select value from engine_meta where key='schema_version'").fetchone()[0])>=84
        day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        horses=int(c.execute("select id from market_goods where good_key='horses_remounts'").fetchone()[0])

        # Player-run horse breeder: national remount demand must discover and approach the player.
        crownhold=int(c.execute("select id from locations where name='Crownhold'").fetchone()[0])
        breeder=add_actor(c,'SEEK Test Breeder','horse breeder',crownhold,'ACTIVE')
        c.execute("insert or replace into player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) values (1,?,?,?,?)",(breeder,crownhold,'SEEK breeder acceptance',day))
        eid=create_enterprise(c,'SEEK Test Stud','estate',owner_actor_id=breeder,location_id=crownhold,capital=180,cash=90,reputation=91,admin_quality=78,labor_capacity=72,risk_tolerance=42)
        configure_enterprise_business(c,eid,'horse_breeder',quality=92,capacity=75,clientele_fit=88,service_reliability=91)
        site=add_production_site(c,eid,horses,capacity_per_30=14,efficiency=88,material_access=80,skilled_labor=91,inventory=40)
        offering=publish_enterprise_offering(c,eid,'goods','military_logistics','remounts',good_id=horses,access_mode='appointment',scarcity=72)
        before=tuple(c.execute("select readiness,transport_capacity from military_logistics_profiles where polity_id=1").fetchone())
        ensure_military_remount_intents(c,day)
        emperor=int(c.execute("select decision_actor_id from polity_government_actors where polity_id=1").fetchone()[0])
        intent=c.execute("select * from actor_seek_intents where seeker_actor_id=? and subject_key='remounts' and status='searching' order by id desc limit 1",(emperor,)).fetchone()
        assert intent
        res=process_seek_intent(c,int(intent['id']),day)
        assert res['action']=='approach' and int(res['provider_actor_id'])==breeder
        inter=c.execute("select * from interactions where id=?",(int(res['interaction_id']),)).fetchone()
        assert int(inter['recipient_actor_id'])==breeder and str(inter['status'])=='pending'
        # Player agency: the request remains pending until explicit response.
        advance_connection(c,5)
        assert c.execute("select status from interactions where id=?",(int(inter['id']),)).fetchone()[0]=='pending'
        now=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        apply_player_response(c,int(inter['id']),breeder,'accept',now)
        contract=c.execute("select * from seek_procurement_contracts where intent_id=?",(int(intent['id']),)).fetchone()
        assert contract and str(contract['status'])=='fulfilled' and int(contract['offering_id'])==offering
        assert float(c.execute("select inventory from production_sites where id=?",(site,)).fetchone()[0]) < 40
        after=tuple(c.execute("select readiness,transport_capacity from military_logistics_profiles where polity_id=1").fetchone())
        assert after[0]>before[0] and after[1]>before[1]
        assert c.execute("select status from actor_seek_intents where id=?",(int(intent['id']),)).fetchone()[0]=='fulfilled'

        # Player hermit master: a distant seeker physically travels, then asks the player.
        cairn=int(c.execute("select id from locations where name='Cairnholt'").fetchone()[0])
        peak=int(c.execute("select id from locations where name='Silent Peak outer approach'").fetchone()[0])
        master=add_actor(c,'SEEK Test Hermit','secluded martial master',peak,'ACTIVE')
        student=add_actor(c,'SEEK Test Disciple','wandering martial aspirant',cairn,'STRATEGIC')
        did=int(c.execute("select id from competence_domains where domain_key='martial_instruction'").fetchone()[0])
        c.execute("insert into actor_competence(actor_id,domain_id,score,source_kind,updated_day) values (?,?,94,'campaign',?)",(master,did,now))
        c.execute("insert into actor_competence(actor_id,domain_id,score,source_kind,updated_day) values (?,?,18,'campaign',?)",(student,did,now))
        c.execute("update player_state set player_actor_id=?,current_location_id=?,campaign_name='SEEK hermit acceptance',updated_day=? where id=1",(master,peak,now))
        publish_personal_instruction(c,master,'martial_instruction',subject_key='martial_instruction',reputation=93,visibility=86,access_mode='visit',capacity=3,duration_days=240,completion_gain=10)
        sint=create_seek_intent(c,student,'instruction','martial_instruction','martial_instruction',intensity=82,min_quality=70,source_kind='martial_aspiration',expires_in_days=180)
        first=process_seek_intent(c,sint,now)
        assert first['action']=='started_travel'
        advance_connection(c,20)
        assert int(c.execute("select current_location_id from actors where id=?",(student,)).fetchone()[0])==peak
        req=c.execute("select * from interactions where proposer_actor_id=? and recipient_actor_id=? and status='pending' order by id desc limit 1",(student,master)).fetchone()
        assert req, 'seeker arrived but did not approach player master'
        now=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        apply_player_response(c,int(req['id']),master,'accept',now)
        assert c.execute("select 1 from education_enrollments where actor_id=? and primary_teacher_actor_id=? and status='active'",(student,master)).fetchone()
        assert c.execute("select 1 from teaching_relationships where teacher_actor_id=? and student_actor_id=? and relation_kind='personal_master' and status='active'",(master,student)).fetchone()
        assert c.execute("select status from actor_seek_intents where id=?",(sint,)).fetchone()[0]=='fulfilled'

        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('SEEK-01 inbound demand/player gravity acceptance PASS')
    finally:
        c.close()


if __name__=='__main__':
    main()
