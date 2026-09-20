from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.civilian import create_household, create_enterprise, create_project
from engine.opportunity import register_capability
from engine.patronage import configure_preference, ensure_patronage_attention
from engine.attention import process_attention_case
from engine.reputation import adjust as adjust_reputation, value as reputation_value
from engine.simulation import advance_connection_registry
from engine.interactions import apply_player_response


def setup_world():
    reset_db(force=True, backup=False)
    init_db()
    c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def add_actor(c,name,subtype,loc):
    day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    aid=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character',?,?,?,'active','PATRON-01 acceptance actor',0)",(name,subtype,loc,loc)).lastrowid)
    c.execute("insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,'STRATEGIC',30,.2,.7,?,?,2)",(aid,day,day+30))
    return aid


def main():
    c=setup_world()
    try:
        assert int(c.execute("select value from engine_meta where key='schema_version'").fetchone()[0])>=86
        day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        loc=int(c.execute("select id from locations where name='Crownhold'").fetchone()[0])
        merchant=add_actor(c,'PATRON Merchant Collector','merchant patron',loc)
        noble=add_actor(c,'PATRON Noble Collector','noble patron',loc)
        artist=add_actor(c,'PATRON Independent Painter','artist',loc)
        mh=create_household(c,'PATRON Merchant Household',head_actor_id=merchant,location_id=loc,wealth=260,liquidity=24)
        nh=create_household(c,'PATRON Noble Household',head_actor_id=noble,location_id=loc,wealth=500,liquidity=180)
        ah=create_household(c,'PATRON Artist Household',head_actor_id=artist,location_id=loc,wealth=8,liquidity=4)
        me=create_enterprise(c,'PATRON Merchant Concern','merchant_house',owner_actor_id=merchant,household_id=mh,location_id=loc,capital=300,cash=220,reputation=76,admin_quality=75,labor_capacity=60,risk_tolerance=50)

        register_capability(c,'actor',artist,'art_culture','painting',quality=91,capacity=72,public_visibility=82,availability=85,source_kind='accepted_work')
        adjust_reputation(c,'actor',artist,'art_culture',25,day=day)  # 75 public cultural reputation
        configure_preference(c,merchant,'art_culture',interest_level=88,prestige_motive=70,developmental_motive=35,preferred_support_kind='stipend',max_amount_per_cycle=6,recurrence_days=30,openness_to_emerging=45)
        configure_preference(c,noble,'art_culture',interest_level=83,prestige_motive=45,developmental_motive=70,preferred_support_kind='workshop_support',max_amount_per_cycle=5,recurrence_days=30,openness_to_emerging=80)

        assert ensure_patronage_attention(c,day)==2
        cases=c.execute("select * from strategic_attention_cases where target_actor_id=? and interest_kind='patronize' order by id",(artist,)).fetchall()
        assert len(cases)==2
        proposals=[]
        for case in cases:
            res=process_attention_case(c,int(case['id']),day)
            assert res['action']=='opportunity_offer'
            proposals.append((int(case['observer_actor_id']),int(res['proposal_id']),int(res['interaction_id'])))
        # The artist can accept both non-exclusive patrons and does not become an employee/member of either.
        for patron,pid,iid in proposals:
            apply_player_response(c,iid,artist,'accept',day)
        rels=c.execute("select * from patronage_relationships where beneficiary_actor_id=? and status='active' order by id",(artist,)).fetchall()
        assert len(rels)==2 and all(float(r['exclusivity'])==0 for r in rels)
        assert not c.execute("select 1 from institutional_appointments where holder_actor_id=? and status='active'",(artist,)).fetchone()
        assert not c.execute("select 1 from institution_memberships where member_actor_id=? and status='active'",(artist,)).fetchone()
        assert any(r['patron_enterprise_id']==me for r in rels)
        assert any(r['patron_household_id']==nh for r in rels)

        merchant_cash=float(c.execute('select cash from civilian_enterprises where id=?',(me,)).fetchone()[0])
        noble_cash=float(c.execute('select liquidity from households where id=?',(nh,)).fetchone()[0])
        artist_cash=float(c.execute('select liquidity from households where id=?',(ah,)).fetchone()[0])

        # Independent work during patronage remains the artist's/unassigned property, not automatically the patron's.
        p1=create_project(c,'PATRON Independent River Study','artwork',creator_actor_id=artist,location_id=loc,target_day=day+30,quality_potential=92,funding=100,material_access=100,skilled_labor=100)
        advance_connection_registry(c,30)
        pays=c.execute("select * from patronage_payments order by id").fetchall()
        assert len(pays)==2 and all(str(p['status'])=='paid' for p in pays)
        assert float(c.execute('select cash from civilian_enterprises where id=?',(me,)).fetchone()[0]) < merchant_cash
        assert float(c.execute('select liquidity from households where id=?',(nh,)).fetchone()[0]) < noble_cash
        assert float(c.execute('select liquidity from households where id=?',(ah,)).fetchone()[0]) > artist_cash
        obj=c.execute("select * from cultural_objects where project_id=?",(p1,)).fetchone()
        assert obj and obj['current_owner_actor_id'] is None
        assert reputation_value(c,'actor',merchant,['art_culture'],default=50)>50
        assert reputation_value(c,'actor',noble,['art_culture'],default=50)>50

        # A separate explicit commission is different: the commissioning patron owns that work.
        now=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        p2=create_project(c,'PATRON Merchant Portrait','artwork',patron_actor_id=merchant,creator_actor_id=artist,location_id=loc,target_day=now+30,quality_potential=90,funding=100,material_access=100,skilled_labor=100)
        advance_connection_registry(c,30)
        obj2=c.execute("select * from cultural_objects where project_id=?",(p2,)).fetchone()
        assert obj2 and int(obj2['current_owner_actor_id'])==merchant

        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('PATRON-01 merchant/noble independent patronage acceptance PASS')
    finally:
        c.close()

if __name__=='__main__': main()
