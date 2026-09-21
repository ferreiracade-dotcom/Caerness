from __future__ import annotations
import os, json
os.environ['CAERNESS_TEST_MODE']='1'
os.environ['CAERNESS_DB_PATH']='/tmp/caerness_schema104_reconstructed_parity.db'

from engine.db import SCHEMA_VERSION, reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.merchant_taxonomy import review_enterprise_merchant_house
from engine.civilian import create_enterprise
from engine.seeking import create_seek_intent, process_seek_intent
from engine.education import create_teaching_relationship
from engine.teaching_ecology import refresh_teacher_market, formalize_teaching_circle
from engine.service_fulfillment import create_service_request, fulfill_service_request
from engine.conflict_geometry import military_geometry_between, direct_military_travel_days
from engine.coverage import ten_year_gate, record_one_year_acceptance


def bootstrap():
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c)
    missing=int(c.execute("select count(*) from actors where actor_type='character' and status='active' and current_location_id is null").fetchone()[0])
    out=activate_existing_loops(c); c.commit()
    pop=int(c.execute("select sum(population_estimate) from population_scale_buckets").fetchone()[0])
    return c,missing,pop,out


def run():
    c,missing,pop0,out=bootstrap()
    try:
        assert SCHEMA_VERSION==104
        assert missing==233, missing
        assert int(c.execute("select count(*) from actors where actor_type='character' and status='active' and current_location_id is null").fetchone()[0])==0
        assert out['opening_character_locations_opening_characters_missing_before']==233
        assert out['opening_character_locations_opening_character_locations_resolved']==233
        assert int(c.execute('select count(*) from institutional_authority_slots').fetchone()[0])==96
        # Conrad is explicitly a senior master, not silently promoted to Head.
        rc=c.execute("select id from actors where name='Red Cedar Sect'").fetchone()[0]
        conrad=c.execute("select id from actors where name='Conrad Slate'").fetchone()[0]
        slot=c.execute("select * from institutional_authority_slots where institution_actor_id=? and authority_key='head'",(rc,)).fetchone()
        assert slot is not None and slot['incumbent_actor_id'] is not None and int(slot['incumbent_actor_id'])!=int(conrad)
        prov=c.execute('select * from person_resolution_provenance where actor_id=?',(int(slot['incumbent_actor_id']),)).fetchone()
        assert prov is not None
        assert int(c.execute("select sum(population_estimate) from population_scale_buckets").fetchone()[0])==pop0

        # Both pre-authored and resolved teachers share one capacity market. Halric has 2 students / 3 places.
        halric=int(c.execute("select id from actors where name='Halric Sten'").fetchone()[0])
        hp=c.execute('select * from teaching_capacity_profiles where teacher_actor_id=?',(halric,)).fetchone()
        assert (int(hp['personal_capacity']),int(hp['occupied_places']),int(hp['spare_places']))==(3,2,1), dict(hp)
        assert int(c.execute('select count(distinct teacher_actor_id) from teaching_relationships where status=\'active\'').fetchone()[0])==50

        # Real unmet demand may reveal a pre-existing POPBACK teacher; it cannot add population.
        c.execute("update seekable_offerings set status='closed' where offer_kind='instruction'")
        locrow=c.execute("""select p.current_location_id,count(*) n from background_person_profiles p
                            where p.status='background' and p.open_core=1 and p.current_stage is not null
                            and p.occupation_domain in ('teacher','soldier','artisan','labor') and p.current_location_id is not null
                            and p.birth_day<=-24*365 and p.birth_day>=-76*365
                            and exists(select 1 from actors ax where ax.actor_type='character' and ax.status='active' and ax.current_location_id=p.current_location_id)
                            group by p.current_location_id order by n desc,p.current_location_id limit 1""").fetchone()
        assert locrow is not None
        loc=int(locrow[0])
        seeker=c.execute("select id from actors where actor_type='character' and status='active' and current_location_id=? order by id limit 1",(loc,)).fetchone()
        assert seeker is not None
        before_res=int(c.execute('select count(*) from person_resolution_provenance').fetchone()[0])
        sint=create_seek_intent(c,int(seeker[0]),'instruction','martial_instruction','martial_instruction',intensity=90,min_quality=45,source_kind='schema104_test',expires_in_days=180)
        process_seek_intent(c,sint,day=0)
        after_res=int(c.execute('select count(*) from person_resolution_provenance').fetchone()[0])
        assert after_res==before_res+1,(before_res,after_res)
        assert int(c.execute("select sum(population_estimate) from population_scale_buckets").fetchone()[0])==pop0

        # Three real students create an informal circle, not a school. One year + explicit teacher decision can form a candidate.
        student=c.execute("""select a.id from actors a join actor_life_profiles lp on lp.actor_id=a.id
                              where a.actor_type='character' and a.status='active' and lp.life_status='living' and a.id<>?
                              and not exists(select 1 from teaching_relationships t where t.teacher_actor_id=? and t.student_actor_id=a.id and t.status='active')
                              order by a.id limit 1""",(halric,halric)).fetchone()
        create_teaching_relationship(c,halric,int(student[0]),'instructor','martial_instruction',responsibility=40,notes='schema104 parity fixture')
        refresh_teacher_market(c)
        circle=c.execute("select * from informal_teaching_circles where teacher_actor_id=? and status='active'",(halric,)).fetchone()
        assert circle is not None and int(circle['active_students'])>=3
        assert c.execute("select 1 from actors where actor_type='institution' and name like '%Halric%' and id<>?",(halric,)).fetchone() is None
        c.execute('update world_state set current_day=365 where id=1')
        cid=formalize_teaching_circle(c,int(circle['id']),halric,proposed_name='[TEST] Halric School Candidate')
        cand=c.execute('select * from emergent_institution_candidates where id=?',(cid,)).fetchone()
        assert cand is not None and str(cand['candidate_kind'])=='martial school'
        assert json.loads(cand['participants_json'])[0]==halric
        assert int(c.execute("select sum(population_estimate) from population_scale_buckets").fetchone()[0])==pop0

        # Profit and a legacy broad enterprise_kind do not constitute Merchant House status.
        ordinary=create_enterprise(c,'[TEST] Very Profitable Ordinary Wholesaler','merchant_house',owner_actor_id=int(seeker[0]),location_id=loc,capital=10000,cash=50000,reputation=99,admin_quality=95,labor_capacity=90,risk_tolerance=50)
        q=review_enterprise_merchant_house(c,ordinary,day=3650)
        assert q['recognized_house_status']==0 and q['dynastic_or_family_continuity']==0,q

        # Institutional structural provider contract can fulfill without manufacturing a messenger/CEO.
        inst=int(c.execute("select id from actors where name='Concord'").fetchone()[0])
        iloc=int(c.execute('select current_location_id from actors where id=?',(inst,)).fetchone()[0])
        provider=create_enterprise(c,'[TEST] Structural Medical Provider','service',location_id=iloc,capital=100,cash=100,reputation=70,admin_quality=70,labor_capacity=65,risk_tolerance=20)
        c.execute("""insert into service_engagements(client_institution_actor_id,provider_kind,provider_id,domain_key,service_kind,scope_json,compensation_json,exclusivity,started_day,status,metadata_json)
                     values (?,'enterprise',?,'medicine','ordinary_care','{}','{}',0,0,'active','{}')""",(inst,provider))
        from engine.service_fulfillment import activate_structural_provider_contracts
        activate_structural_provider_contracts(c)
        req=create_service_request(c,'medicine',requester_institution_actor_id=inst,need_level=55,requested_day=365,due_day=365)
        fulfilled=fulfill_service_request(c,req)
        assert fulfilled['status']=='fulfilled' and int(fulfilled['provider_enterprise_id'])==provider and fulfilled['provider_actor_id'] is None

        # Military frontier is real geometry without inventing a civilian road.
        east=int(c.execute("select id from locations where name='Eastwatch'").fetchone()[0]); west=int(c.execute("select id from locations where name='Westgate'").fetchone()[0])
        direct_route=c.execute("select 1 from travel_routes where ((from_location_id=? and to_location_id=?) or (from_location_id=? and to_location_id=?)) and status in ('open','restricted')",(east,west,west,east)).fetchone()
        assert direct_route is None
        geo=military_geometry_between(c,east,west); assert geo is not None and geo['geometry_kind']=='military_frontier'
        assert direct_military_travel_days(c,east,west) is not None

        # Schema-70 historical evidence cannot unlock schema-104 TENYEAR. Current acceptance epoch can.
        c.execute("insert or replace into engine_meta(key,value) values ('one_year_unattended_acceptance','passed')")
        c.execute("update acceptance_epochs set status='pending',evidence_json='{}' where acceptance_key='ONEYEAR_RECOVERY_SCHEMA104'")
        assert not ten_year_gate(c)['pass']
        record_one_year_acceptance(c,evidence={'test':'schema104 parity'},status='passed')
        assert ten_year_gate(c)['pass']

        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('SCHEMA104 reconstructed parity PASS',{'authority_slots':96,'halric_spare':1,'background_teacher_resolved':1,'merchant_profit_not_house':True,'military_frontier':True})
    finally:
        c.close()

if __name__=='__main__': run()
