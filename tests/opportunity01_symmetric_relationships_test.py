from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.civilian import create_enterprise, add_production_site
from engine.business import configure_enterprise_business
from engine.attention import ensure_horse_breeder_attention, process_attention_case
from engine.interactions import apply_player_response
from engine.organization_agency import start_regime
from engine.opportunity import (
    create_proposal, add_term, present_proposal, register_asset, create_search, discover_search,
    propose_talent_recruitment, make_unsolicited_asset_offer, register_capability, propose_service_contract,
)
from engine.reputation import adjust as adjust_reputation
from engine.decision_runtime import generate_candidates
from engine.decisions import build_actor_context, candidate_to_proposal, apply_decision


def setup_world():
    reset_db(force=True, backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def add_actor(c,name,subtype,loc,tier='ACTIVE'):
    day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    aid=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character',?,?,?,'active','OPPORTUNITY-01 acceptance actor',0)",(name,subtype,loc,loc)).lastrowid)
    c.execute("insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,?,7,.3,.75,?,?,2)",(aid,tier,day,day+7))
    return aid


def add_institution(c,name,kind,loc,leader):
    day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    iid=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'institution',?,?,?,'active','OPPORTUNITY-01 acceptance institution',0)",(name,kind,loc,loc)).lastrowid)
    c.execute("insert into institution_profiles(actor_id,institution_kind,founded_day,primary_location_id,last_review_day,notes) values (?,?,?,?,?,'OPPORTUNITY-01 test')",(iid,kind,day,loc,day))
    c.execute("insert into institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json) values (?,?,'leadership','Head','active',?,'[]','{}')",(iid,leader,day))
    start_regime(c,iid,leader_actor_id=leader,regime_kind='test_leadership')
    return iid


def set_competence(c,actor,domain,score):
    day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    did=int(c.execute('select id from competence_domains where domain_key=?',(domain,)).fetchone()[0])
    c.execute("insert into actor_competence(actor_id,domain_id,score,source_kind,updated_day) values (?,?,?,'campaign',?) on conflict(actor_id,domain_id,specialty_key) do update set score=excluded.score,updated_day=excluded.updated_day",(actor,did,score,day))


def main():
    c=setup_world()
    try:
        assert int(c.execute("select value from engine_meta where key='schema_version'").fetchone()[0])>=84
        day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        crownhold=int(c.execute("select id from locations where name='Crownhold'").fetchone()[0])
        horses=int(c.execute("select id from market_goods where good_key='horses_remounts'").fetchone()[0])
        crown_inst=int(c.execute("select institution_actor_id from political_polities where id=1").fetchone()[0])
        crown_actor=int(c.execute("select decision_actor_id from polity_government_actors where polity_id=1").fetchone()[0])

        # 1. Crown Horsebreeder is an incorporation proposal: the stud changes control, the breeder remains operator/master.
        breeder=add_actor(c,'OPP Royal Breeder','horse breeder',crownhold)
        c.execute("insert or replace into player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) values (1,?,?,?,?)",(breeder,crownhold,'OPPORTUNITY breeder incorporation',day))
        stud=create_enterprise(c,'OPP Royal Stud Candidate','estate',owner_actor_id=breeder,location_id=crownhold,capital=220,cash=120,reputation=92,admin_quality=82,labor_capacity=75,risk_tolerance=40)
        configure_enterprise_business(c,stud,'horse_breeder',quality=93,capacity=78,clientele_fit=90,service_reliability=92)
        add_production_site(c,stud,horses,capacity_per_30=16,efficiency=90,material_access=82,skilled_labor=93,inventory=36)
        assert ensure_horse_breeder_attention(c,day)>=1
        case=c.execute("select * from strategic_attention_cases where target_actor_id=? and interest_kind='appoint' order by id desc limit 1",(breeder,)).fetchone()
        res=process_attention_case(c,int(case['id']),day)
        assert res['action']=='opportunity_offer'
        pid=int(res['proposal_id']); iid=int(res['interaction_id'])
        terms={r['term_kind'] for r in c.execute('select * from opportunity_proposal_terms where proposal_id=?',(pid,)).fetchall()}
        assert {'enterprise_legal_ownership','enterprise_beneficial_control','enterprise_operation','appointment'} <= terms
        assert c.execute('select status from interactions where id=?',(iid,)).fetchone()[0]=='pending'
        apply_player_response(c,iid,breeder,'accept',day+1)
        ent=c.execute('select owner_actor_id,status from civilian_enterprises where id=?',(stud,)).fetchone()
        assert ent['owner_actor_id'] is None and ent['status']=='active'
        legal=c.execute("select * from enterprise_control_interests where enterprise_id=? and interest_kind='legal_owner' and status='active'",(stud,)).fetchone()
        op=c.execute("select * from enterprise_control_interests where enterprise_id=? and interest_kind='operator' and status='active'",(stud,)).fetchone()
        assert int(legal['holder_institution_actor_id'])==crown_inst and int(op['holder_actor_id'])==breeder
        assert c.execute("select 1 from institutional_appointments where holder_actor_id=? and appointing_institution_actor_id=? and status='active'",(breeder,crown_inst)).fetchone()

        # 2. A first-refusal deal is materially different: private ownership stays private.
        private_breeder=add_actor(c,'OPP Private Breeder','horse breeder',crownhold)
        private_stud=create_enterprise(c,'OPP Private Stud','estate',owner_actor_id=private_breeder,location_id=crownhold,capital=150,cash=80,reputation=80,admin_quality=72,labor_capacity=70,risk_tolerance=45)
        p2=create_proposal(c,crown_actor,'first_refusal','horse_breeding','Royal first refusal on war-quality remounts',proposer_institution_actor_id=crown_inst,target_actor_id=private_breeder)
        add_term(c,p2,'first_refusal',subject_kind='enterprise',subject_id=private_stud,value={'grantor_kind':'actor','grantor_id':private_breeder,'grantee_kind':'institution','grantee_id':crown_inst,'scope':{'good_key':'horses_remounts','quality_floor':80}},execution_order=20)
        iid2=present_proposal(c,p2)
        c.execute("update player_state set player_actor_id=?,current_location_id=?,updated_day=? where id=1",(private_breeder,crownhold,day))
        apply_player_response(c,iid2,private_breeder,'accept',day+2)
        assert int(c.execute('select owner_actor_id from civilian_enterprises where id=?',(private_stud,)).fetchone()[0])==private_breeder
        assert c.execute("select 1 from contractual_rights where subject_kind='enterprise' and subject_id=? and right_kind='first_refusal' and status='active'",(private_stud,)).fetchone()

        # 3. Kingdom-building talent search finds real people and exposes obligations rather than spawning specialists.
        independent=add_actor(c,'OPP Independent Master Smith','independent master smith',crownhold,'ACTIVE')
        occupied=add_actor(c,'OPP House Master Smith','great-house smith',crownhold,'ACTIVE')
        set_competence(c,independent,'craft',86); set_competence(c,occupied,'craft',94)
        adjust_reputation(c,'actor',independent,'craft',24,day=day); adjust_reputation(c,'actor',occupied,'craft',30,day=day)
        house_leader=add_actor(c,'OPP House Lord','noble house head',crownhold)
        house=add_institution(c,'OPP Ashen House','noble_house',crownhold,house_leader)
        c.execute("insert into institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json) values (?,?,'service','House Master Smith','active',?,'[]','{}')",(house,occupied,day))
        c.execute("insert into enterprise_staff(enterprise_id,actor_id,role,authority,specialty,status,joined_day,metadata_json) values (?,?,?,?,?,'active',?,'{}')",(private_stud,occupied,'master smith',80,'craft',day))
        before_actors=int(c.execute("select count(*) from actors").fetchone()[0])
        search=create_search(c,crown_actor,'talent','craft',seeker_institution_actor_id=crown_inst,role_key='royal_master_smith',min_quality=80,intensity=85,willingness_to_poach=20)
        results=discover_search(c,search)
        by={r['candidate_id']:r for r in results}
        assert independent in by and occupied in by
        assert by[independent]['availability'] > by[occupied]['availability']
        assert int(c.execute("select count(*) from actors").fetchone()[0])==before_actors, 'talent search spawned a person'
        rp,ri=propose_talent_recruitment(c,search,independent,title='Royal Master Smith',appointment_key='royal_master_smith',obligations={'oversee_royal_forge':True},privileges={'found_workshop':True})
        assert int(c.execute('select target_actor_id from opportunity_proposals where id=?',(rp,)).fetchone()[0])==independent

        # A clan/house can use the same search architecture; Crown is not privileged as a seeker class.
        hsearch=create_search(c,house_leader,'talent','craft',seeker_institution_actor_id=house,role_key='house_forge_master',min_quality=80,intensity=70,willingness_to_poach=10)
        hresults=discover_search(c,hsearch)
        assert any(r['candidate_id']==independent for r in hresults)

        # A non-state institution can originate the same search autonomously from its own persisted pressure.
        sect_leader=add_actor(c,'OPP Sect Head','sect master',crownhold,'STRATEGIC')
        sect=add_institution(c,'OPP River Forge Sect','sect',crownhold,sect_leader)
        specialist=add_actor(c,'OPP Independent Weaponsmith','independent weaponsmith',crownhold,'ACTIVE')
        set_competence(c,specialist,'craft',88); adjust_reputation(c,'actor',specialist,'craft',22,day=day)
        pressure_meta={'opportunity_need':{'search_kind':'talent','domain_key':'craft','role_key':'sect_forge_master','min_quality':82,'willingness_to_poach':15,
                       'proposal':{'proposal_kind':'appointment','title':'Forge Master of River Forge Sect','appointment_key':'sect_forge_master','obligations':{'maintain_sect_forge':True},'privileges':{'workshop_access':True}}}}
        c.execute("insert into organization_pressures(institution_actor_id,pressure_key,domain,intensity,urgency,source_kind,status,created_day,updated_day,metadata_json) values (?,?,?,70,72,'institution_state','active',?,?,?)",
                  (sect,'forge_capacity_gap','craft',day,day,__import__('json').dumps(pressure_meta,sort_keys=True)))
        env=build_actor_context(c,sect_leader,day)
        cands=generate_candidates(c,sect_leader,'STRATEGIC',day,env)
        start=next(x for x in cands if x.provider_key=='opportunity' and x.action_kind=='start_opportunity_search' and int(x.payload['institution_actor_id'])==sect)
        apply_decision(c,sect_leader,'STRATEGIC',day,candidate_to_proposal(start))
        auto_search=c.execute("select * from opportunity_searches where seeker_institution_actor_id=? and status='searching' order by id desc limit 1",(sect,)).fetchone()
        assert auto_search
        env2=build_actor_context(c,sect_leader,day+1)
        cands2=generate_candidates(c,sect_leader,'STRATEGIC',day+1,env2)
        approach=[x for x in cands2 if x.provider_key=='opportunity' and x.action_kind=='approach_opportunity_candidate' and int(x.payload['search_id'])==int(auto_search['id'])]
        assert approach and any(int(x.payload['candidate_id'])==specialist for x in approach)

        # 4. Ownership itself can attract offers: an unlisted famous horse is discoverable and can receive an unsolicited bid.
        collector=add_actor(c,'OPP Horse Collector','merchant collector',crownhold)
        buyer=add_actor(c,'OPP Noble Buyer','wealthy noble',crownhold)
        asset=register_asset(c,'exceptional_horse','Ashwind',owner_actor_id=collector,location_id=crownhold,quality=97,rarity=94,public_visibility=88,estimated_value=120,offered_for_sale=False)
        asearch=create_search(c,buyer,'asset','exceptional_horse',min_quality=90,intensity=75)
        ares=discover_search(c,asearch)
        ar=next(r for r in ares if r['candidate_id']==asset)
        assert 'owner has not offered asset for sale' in ar['blockers']
        ap,ai=make_unsolicited_asset_offer(c,buyer,asset,title='Offer for Ashwind')
        c.execute("update player_state set player_actor_id=?,current_location_id=?,updated_day=? where id=1",(collector,crownhold,day))
        assert c.execute('select status from interactions where id=?',(ai,)).fetchone()[0]=='pending'
        apply_player_response(c,ai,collector,'accept',day+3)
        transferred=c.execute('select owner_actor_id,offered_for_sale from strategic_assets where id=?',(asset,)).fetchone()
        assert int(transferred['owner_actor_id'])==buyer and int(transferred['offered_for_sale'])==0

        # 5. Organizations and individuals advertise/disclose capabilities, not bespoke quest hooks.
        # A Crown can discover a mercenary company; a noble house can discover an independent fixer.
        captain=add_actor(c,'OPP Free Company Captain','mercenary captain',crownhold)
        company=add_institution(c,'OPP Iron Road Company','mercenary_company',crownhold,captain)
        register_capability(c,'institution',company,'military_service','frontier_security',quality=84,capacity=72,public_visibility=76,availability=90,metadata={'company_kind':'mercenary'})
        ssearch=create_search(c,crown_actor,'service_provider','military_service',seeker_institution_actor_id=crown_inst,role_key='frontier_security',min_quality=70,intensity=80)
        sresults=discover_search(c,ssearch)
        assert any(r['candidate_kind']=='institution' and r['candidate_id']==company for r in sresults)
        service,si=propose_service_contract(c,ssearch,'institution',company,title='Three-month frontier service contract',service_kind='frontier_security',duration_days=90,scope={'region':'western marches'})
        c.execute("update player_state set player_actor_id=?,current_location_id=?,updated_day=? where id=1",(captain,crownhold,day))
        assert c.execute('select status from interactions where id=?',(si,)).fetchone()[0]=='pending'
        apply_player_response(c,si,captain,'accept',day+4)
        assert c.execute("select 1 from opportunity_agreements where proposal_id=? and status='active'",(service,)).fetchone()
        assert c.execute("select 1 from service_engagements where source_proposal_id=? and provider_kind='institution' and provider_id=? and service_kind='frontier_security' and status='active'",(service,company)).fetchone()

        fixer=add_actor(c,'OPP Independent Fixer','independent fixer',crownhold)
        register_capability(c,'actor',fixer,'covert_service','difficult_problem',quality=89,capacity=45,public_visibility=58,availability=75,metadata={'style':'discreet'})
        fsearch=create_search(c,house_leader,'service_provider','covert_service',seeker_institution_actor_id=house,role_key='difficult_problem',min_quality=75,intensity=70)
        fresults=discover_search(c,fsearch)
        assert any(r['candidate_kind']=='actor' and r['candidate_id']==fixer for r in fresults)

        assassin_leader=add_actor(c,'OPP Night Knife Master','assassin master',crownhold)
        assassin_order=add_institution(c,'OPP Night Knife Order','assassin_order',crownhold,assassin_leader)
        register_capability(c,'institution',assassin_order,'covert_service','targeted_killing',quality=91,capacity=35,public_visibility=42,availability=60,metadata={'illegal_or_secretive':True})
        a2=create_search(c,house_leader,'service_provider','covert_service',seeker_institution_actor_id=house,role_key='targeted_killing',min_quality=80,intensity=60)
        a2r=discover_search(c,a2)
        assert any(r['candidate_kind']=='institution' and r['candidate_id']==assassin_order for r in a2r)

        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('OPPORTUNITY-01 symmetric relationships/ownership/search acceptance PASS')
    finally:
        c.close()

if __name__=='__main__': main()
