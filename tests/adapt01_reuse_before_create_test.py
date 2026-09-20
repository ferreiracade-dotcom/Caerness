from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.organization_agency import start_regime
from engine.opportunity import create_search, discover_search
from engine.adaptive_planning import create_role, adapt_and_propose_talent, ensure_program
from engine.reputation import adjust as adjust_reputation
from engine.interactions import apply_player_response


def setup_world():
    reset_db(force=True, backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def add_actor(c, name, subtype, loc):
    day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    aid=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character',?,?,?,'active','ADAPT-01 test',0)",(name,subtype,loc,loc)).lastrowid)
    c.execute("insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,'ACTIVE',7,.3,.75,?,?,2)",(aid,day,day+7))
    return aid


def set_competence(c, actor, domain, score):
    day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    did=int(c.execute('select id from competence_domains where domain_key=?',(domain,)).fetchone()[0])
    c.execute("insert into actor_competence(actor_id,domain_id,score,source_kind,updated_day) values (?,?,?,'campaign',?) on conflict(actor_id,domain_id,specialty_key) do update set score=excluded.score,updated_day=excluded.updated_day",(actor,did,score,day))


def find_candidate(c, search_id, actor_id):
    rows=discover_search(c,search_id)
    assert any(r['candidate_kind']=='actor' and int(r['candidate_id'])==actor_id for r in rows), rows


def main():
    c=setup_world()
    try:
        assert int(c.execute("select value from engine_meta where key='schema_version'").fetchone()[0])>=85
        day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        crownhold=int(c.execute("select id from locations where name='Crownhold'").fetchone()[0])
        crown_inst=int(c.execute("select institution_actor_id from political_polities where id=1").fetchone()[0])
        crown_actor=int(c.execute("select decision_actor_id from polity_government_actors where polity_id=1").fetchone()[0])

        # Existing durable program and existing office: discovery should reshape/reuse, not create another role.
        program_id,_=ensure_program(c,crown_inst,{
            'program_key':'royal_works','program_title':'Royal Works','domain_key':'craft','program_kind':'standing_program','horizon':'durable','program_priority':55,
        },source_kind='opening_structure',source_id=None,day=day)
        role_id=create_role(c,crown_inst,'master_of_works','Master of Works','craft',role_kind='technical_role',capacity_slots=1,source_kind='opening_structure',day=day)
        master=add_actor(c,'ADAPT Master Builder','master builder',crownhold); set_competence(c,master,'craft',92); adjust_reputation(c,'actor',master,'craft',28,day=day)
        s1=create_search(c,crown_actor,'talent','craft',seeker_institution_actor_id=crown_inst,role_key='master_of_works',min_quality=80,intensity=85)
        find_candidate(c,s1,master)
        roles_before=int(c.execute('select count(*) from institutional_roles where institution_actor_id=?',(crown_inst,)).fetchone()[0])
        r1=adapt_and_propose_talent(c,s1,master,{'adaptive_plan':{
            'program_key':'royal_works','program_title':'Royal Works','domain_key':'craft','horizon':'durable','program_priority':82,
            'role_key':'master_of_works','internal_authority_required':True,'allow_role_creation':True,'structural_need':95,
            'obligations':{'oversee_public_works':True}
        }},day=day)
        assert r1['adaptation_kind']=='reuse_role' and int(r1['role_id'])==role_id
        assert int(c.execute('select count(*) from institutional_roles where institution_actor_id=?',(crown_inst,)).fetchone()[0])==roles_before
        assert int(c.execute('select priority from institutional_programs where id=?',(program_id,)).fetchone()[0])>=82
        term=c.execute("select value_json from opportunity_proposal_terms where proposal_id=? and term_kind='appointment'",(r1['proposal_id'],)).fetchone()
        assert f'"role_id": {role_id}' in term[0]
        c.execute("insert or replace into player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) values (1,?,?,?,?)",(master,crownhold,'ADAPT reuse',day))
        apply_player_response(c,int(r1['interaction_id']),master,'accept',day+1)
        assert c.execute("select 1 from institutional_appointments where holder_actor_id=? and role_id=? and status='active'",(master,role_id)).fetchone()

        # A bounded need uses a contract. No office is created even though role creation is allowed in principle.
        bridge=add_actor(c,'ADAPT Bridge Engineer','bridge engineer',crownhold); set_competence(c,bridge,'craft',88); adjust_reputation(c,'actor',bridge,'craft',24,day=day)
        s2=create_search(c,crown_actor,'talent','craft',seeker_institution_actor_id=crown_inst,role_key='bridge_engineer',min_quality=80,intensity=75)
        find_candidate(c,s2,bridge)
        before=int(c.execute('select count(*) from institutional_roles where institution_actor_id=?',(crown_inst,)).fetchone()[0])
        r2=adapt_and_propose_talent(c,s2,bridge,{'adaptive_plan':{
            'program_key':'west_bridge_repair','program_title':'West Bridge Repair','domain_key':'craft','program_kind':'project','horizon':'temporary',
            'role_key':'bridge_engineer','relationship_preference':'temporary_service','duration_days':120,
            'internal_authority_required':False,'allow_role_creation':True,'structural_need':95,
        }},day=day)
        assert r2['adaptation_kind']=='temporary_contract'
        assert int(c.execute('select count(*) from institutional_roles where institution_actor_id=?',(crown_inst,)).fetchone()[0])==before
        assert c.execute("select 1 from opportunity_proposal_terms where proposal_id=? and term_kind='service_commitment'",(r2['proposal_id'],)).fetchone()

        # Durable access that does not require internal authority becomes a retainer/standing service, still no new role.
        adviser=add_actor(c,'ADAPT Metallurgy Adviser','metallurgy adviser',crownhold); set_competence(c,adviser,'craft',90); adjust_reputation(c,'actor',adviser,'craft',25,day=day)
        s3=create_search(c,crown_actor,'talent','craft',seeker_institution_actor_id=crown_inst,role_key='metallurgy_adviser',min_quality=80,intensity=70)
        find_candidate(c,s3,adviser)
        before=int(c.execute('select count(*) from institutional_roles where institution_actor_id=?',(crown_inst,)).fetchone()[0])
        r3=adapt_and_propose_talent(c,s3,adviser,{'adaptive_plan':{
            'program_key':'arsenal_quality','program_title':'Arsenal Quality Program','domain_key':'craft','horizon':'durable',
            'role_key':'metallurgy_adviser','internal_authority_required':False,'allow_role_creation':True,'structural_need':90,
        }},day=day)
        assert r3['adaptation_kind']=='standing_service'
        assert int(c.execute('select count(*) from institutional_roles where institution_actor_id=?',(crown_inst,)).fetchone()[0])==before

        # Only a genuinely durable internal structural gap creates a new role.
        water=add_actor(c,'ADAPT Hydraulic Master','hydraulic engineer',crownhold); set_competence(c,water,'craft',94); adjust_reputation(c,'actor',water,'craft',30,day=day)
        s4=create_search(c,crown_actor,'talent','craft',seeker_institution_actor_id=crown_inst,role_key='master_waterworks',min_quality=85,intensity=92)
        find_candidate(c,s4,water)
        before=int(c.execute('select count(*) from institutional_roles where institution_actor_id=?',(crown_inst,)).fetchone()[0])
        cfg={'adaptive_plan':{
            'program_key':'royal_waterworks','program_title':'Royal Waterworks','domain_key':'craft','program_kind':'standing_program','horizon':'durable',
            'role_key':'master_waterworks','role_title':'Master of Waterworks','internal_authority_required':True,
            'allow_role_creation':True,'structural_need':96,'role_creation_threshold':80,
        }}
        r4=adapt_and_propose_talent(c,s4,water,cfg,day=day)
        assert r4['adaptation_kind']=='create_role' and r4['role_id'] is not None
        assert int(c.execute('select count(*) from institutional_roles where institution_actor_id=?',(crown_inst,)).fetchone()[0])==before+1
        # A second search for the same need sees and reuses the newly created role instead of creating a duplicate.
        water2=add_actor(c,'ADAPT Second Hydraulic Master','hydraulic engineer',crownhold); set_competence(c,water2,'craft',91); adjust_reputation(c,'actor',water2,'craft',27,day=day)
        s5=create_search(c,crown_actor,'talent','craft',seeker_institution_actor_id=crown_inst,role_key='master_waterworks',min_quality=85,intensity=80)
        find_candidate(c,s5,water2)
        r5=adapt_and_propose_talent(c,s5,water2,cfg,day=day)
        assert r5['adaptation_kind']=='reuse_role'
        assert int(r5['role_id'])==int(r4['role_id'])
        assert int(c.execute("select count(*) from institutional_roles where institution_actor_id=? and role_key='master_waterworks'",(crown_inst,)).fetchone()[0])==1

        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('ADAPT-01 reuse-before-role-creation acceptance PASS')
    finally:
        c.close()

if __name__=='__main__': main()
