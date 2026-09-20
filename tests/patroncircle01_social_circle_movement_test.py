from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.civilian import create_household, create_enterprise, create_cultural_object
from engine.opportunity import register_capability, accept_proposal
from engine.patronage import (
    configure_preference, propose_patronage, refresh_patronage_circles,
    host_due_patronage_circles, evaluate_cultural_movements, patronage_circle_network,
)


def setup_world():
    reset_db(force=True, backup=False); init_db()
    c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def add_actor(c,name,subtype,loc):
    day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    aid=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character',?,?,?,'active','PATRONCIRCLE-01 actor',0)",(name,subtype,loc,loc)).lastrowid)
    c.execute("insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,'STRATEGIC',30,.2,.7,?,?,2)",(aid,day,day+30))
    return aid


def accept_patronage(c,patron,artist,domain='art_culture',amount=3):
    pid,iid=propose_patronage(c,patron,artist,domain,amount_per_cycle=amount,recurrence_days=30,duration_days=360,exclusivity=0)
    accept_proposal(c,pid,artist,iid,day=int(c.execute('select current_day from world_state where id=1').fetchone()[0]))
    return pid


def main():
    c=setup_world()
    try:
        assert int(c.execute("select value from engine_meta where key='schema_version'").fetchone()[0])>=88
        loc=int(c.execute("select id from locations where name='Crownhold'").fetchone()[0])
        institution_count_before=int(c.execute("select count(*) from institution_profiles").fetchone()[0])
        private_patron=add_actor(c,'Private Collector','merchant patron',loc)
        salon_patron=add_actor(c,'Salon Merchant','merchant patron',loc)
        artists=[add_actor(c,f'Circle Artist {i}','artist',loc) for i in range(1,4)]
        private_artists=[add_actor(c,f'Private Artist {i}','artist',loc) for i in range(1,3)]
        # Real funding sources.
        for patron,wealth in [(private_patron,250),(salon_patron,420)]:
            hh=create_household(c,f'HH {patron}',head_actor_id=patron,location_id=loc,wealth=wealth,liquidity=wealth/2)
            create_enterprise(c,f'Concern {patron}','merchant_house',owner_actor_id=patron,household_id=hh,location_id=loc,capital=wealth,cash=wealth/2,reputation=80,admin_quality=75,labor_capacity=60,risk_tolerance=45)
        for a in artists+private_artists:
            create_household(c,f'HH {a}',head_actor_id=a,location_id=loc,wealth=8,liquidity=3)
            register_capability(c,'actor',a,'art_culture','art_culture',quality=84,capacity=65,public_visibility=65,availability=90,source_kind='accepted_work')

        # Supporting several artists privately is not enough to create a circle.
        configure_preference(c,private_patron,'art_culture',interest_level=85,max_amount_per_cycle=4,networking_motive=0)
        for a in private_artists: accept_patronage(c,private_patron,a)

        # This patron explicitly likes convening beneficiaries.
        configure_preference(c,salon_patron,'art_culture',interest_level=92,max_amount_per_cycle=5,
                             networking_motive=88,circle_cadence_days=30,
                             metadata={'circle_visibility':78,'circle_kind':'salon'})
        for a in artists: accept_patronage(c,salon_patron,a)

        summary=refresh_patronage_circles(c,0)
        assert summary['created']==1
        assert c.execute("select count(*) from patronage_circles where patron_actor_id=?",(private_patron,)).fetchone()[0]==0
        circle=c.execute("select * from patronage_circles where patron_actor_id=? and domain_key='art_culture'",(salon_patron,)).fetchone()
        assert circle and str(circle['status'])=='active'
        cid=int(circle['id'])
        assert c.execute("select count(*) from patronage_circle_members where circle_id=? and status='active'",(cid,)).fetchone()[0]==3

        # No gathering means no inferred social relationships and no artistic movement.
        assert c.execute("select count(*) from patronage_circle_introductions where circle_id=?",(cid,)).fetchone()[0]==0
        assert evaluate_cultural_movements(c,0)==0

        c.execute("update world_state set current_day=30 where id=1")
        g=host_due_patronage_circles(c,30)
        assert g['gatherings']==1 and g['introductions']==3
        assert c.execute("select count(*) from patronage_circle_introductions where circle_id=?",(cid,)).fetchone()[0]==3
        # Gathering creates actual acquaintance/familiarity, not just network metadata.
        rel=c.execute("select familiarity,professional_confidence from relationships where actor_a_id=? and actor_b_id=?",(artists[0],artists[1])).fetchone()
        assert rel and float(rel['familiarity'])>=12 and float(rel['professional_confidence'])>=3

        # Shared patron + acquaintance still does not create a school. Output evidence is required.
        create_cultural_object(c,'First Luminous Work','painting',creator_actor_id=artists[0],created_day=31,owner_actor_id=artists[0],location_id=loc,quality=88,metadata={'style_tags':['luminous-naturalism']})
        create_cultural_object(c,'Second Luminous Work','painting',creator_actor_id=artists[1],created_day=32,owner_actor_id=artists[1],location_id=loc,quality=87,metadata={'style_tags':['luminous-naturalism']})
        assert evaluate_cultural_movements(c,32)==0
        assert c.execute("select count(*) from cultural_movements").fetchone()[0]==0

        # Three connected creators with three strong works can now produce an emerging style.
        create_cultural_object(c,'Third Luminous Work','painting',creator_actor_id=artists[2],created_day=33,owner_actor_id=artists[2],location_id=loc,quality=90,metadata={'style_tags':['luminous-naturalism']})
        assert evaluate_cultural_movements(c,33)==1
        mov=c.execute("select * from cultural_movements where circle_id=? and style_tag='luminous-naturalism'",(cid,)).fetchone()
        assert mov and str(mov['status'])=='emerging' and int(mov['member_count'])==3 and int(mov['work_count'])==3
        assert mov['display_name'] is None  # style can exist structurally before society supplies a settled name.

        # More excellent shared output can make the movement publicly recognizable without creating a formal institution.
        create_cultural_object(c,'Fourth Luminous Work','painting',creator_actor_id=artists[0],created_day=34,owner_actor_id=artists[0],location_id=loc,quality=92,metadata={'style_tags':['luminous-naturalism']})
        create_cultural_object(c,'Fifth Luminous Work','painting',creator_actor_id=artists[1],created_day=35,owner_actor_id=artists[1],location_id=loc,quality=91,metadata={'style_tags':['luminous-naturalism']})
        evaluate_cultural_movements(c,35)
        mov=c.execute("select * from cultural_movements where id=?",(int(mov['id']),)).fetchone()
        assert str(mov['status'])=='recognized' and int(mov['work_count'])==5 and mov['recognized_day'] is not None
        # A movement is not automatically an institution/academy/sect.
        assert int(c.execute("select count(*) from institution_profiles").fetchone()[0])==institution_count_before
        net=patronage_circle_network(c,'art_culture')
        assert net=={'circles':1,'members':3,'gatherings':1,'introductions':3,'movements':1}
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('PATRONCIRCLE-01 convened circles + evidence-bound movement acceptance PASS')
    finally:
        c.close()

if __name__=='__main__': main()
