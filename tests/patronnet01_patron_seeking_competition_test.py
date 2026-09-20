from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.civilian import create_household, create_enterprise
from engine.opportunity import register_capability, accept_proposal
from engine.patronage import (
    configure_preference, configure_seeking_profile, ensure_patronage_seeking,
    propose_patronage, refresh_patronage_competitions, patronage_network,
)
from engine.reputation import adjust as adjust_reputation


def setup_world():
    reset_db(force=True, backup=False); init_db()
    c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def add_actor(c,name,subtype,loc):
    day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    aid=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character',?,?,?,'active','PATRONNET-01 actor',0)",(name,subtype,loc,loc)).lastrowid)
    c.execute("insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,'STRATEGIC',30,.2,.7,?,?,2)",(aid,day,day+30))
    return aid


def main():
    c=setup_world()
    try:
        assert int(c.execute("select value from engine_meta where key='schema_version'").fetchone()[0])>=87
        day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        loc=int(c.execute("select id from locations where name='Crownhold'").fetchone()[0])
        p1=add_actor(c,'PATRONNET Merchant Patron','merchant patron',loc)
        p2=add_actor(c,'PATRONNET Noble Patron','noble patron',loc)
        artist=add_actor(c,'PATRONNET Seeking Painter','artist',loc)
        rival_artist=add_actor(c,'PATRONNET Rising Sculptor','artist',loc)
        h1=create_household(c,'PATRONNET Merchant HH',head_actor_id=p1,location_id=loc,wealth=350,liquidity=80)
        h2=create_household(c,'PATRONNET Noble HH',head_actor_id=p2,location_id=loc,wealth=600,liquidity=250)
        ah=create_household(c,'PATRONNET Artist HH',head_actor_id=artist,location_id=loc,wealth=5,liquidity=2)
        rh=create_household(c,'PATRONNET Sculptor HH',head_actor_id=rival_artist,location_id=loc,wealth=6,liquidity=3)
        e1=create_enterprise(c,'PATRONNET Merchant Concern','merchant_house',owner_actor_id=p1,household_id=h1,location_id=loc,capital=320,cash=240,reputation=82,admin_quality=80,labor_capacity=70,risk_tolerance=50)

        for aid,q,vis in [(artist,88,70),(rival_artist,94,90)]:
            register_capability(c,'actor',aid,'art_culture','painting' if aid==artist else 'sculpture',quality=q,capacity=70,public_visibility=vis,availability=90,source_kind='accepted_work')
            # Patron candidate discovery searches the domain, not only the exact capability key.
            register_capability(c,'actor',aid,'art_culture','art_culture',quality=q,capacity=70,public_visibility=vis,availability=90,source_kind='accepted_work')
            adjust_reputation(c,'actor',aid,'art_culture',22 if aid==artist else 30,day=day)
        configure_preference(c,p1,'art_culture',interest_level=90,prestige_motive=65,developmental_motive=55,max_amount_per_cycle=7,recurrence_days=30,openness_to_emerging=70)
        configure_preference(c,p2,'art_culture',interest_level=92,prestige_motive=80,developmental_motive=45,max_amount_per_cycle=8,recurrence_days=30,openness_to_emerging=60)

        # Beneficiary-side intent can actively seek real patrons; two simultaneous requests are allowed here.
        configure_seeking_profile(c,artist,'art_culture',desire_level=92,min_amount_per_cycle=3,max_simultaneous_requests=2,
                                  funding_priority=85,prestige_priority=55,independence_priority=80,metadata={'desired_exclusivity':0})
        assert ensure_patronage_seeking(c,day)==2
        requests=c.execute("select * from opportunity_proposals where proposer_actor_id=? and proposal_kind='patronage' and source_kind='patronage_seek_profile' and status='pending' order by id",(artist,)).fetchall()
        assert len(requests)==2 and {int(r['target_actor_id']) for r in requests}=={p1,p2}
        # Patrons may both accept non-exclusive support requests: patronage is a network, not employment.
        for r in requests:
            iid=int(c.execute("select id from interactions where status='pending' and json_extract(terms_json,'$.opportunity_proposal_id')=? order by id desc limit 1",(int(r['id']),)).fetchone()[0])
            accept_proposal(c,int(r['id']),int(r['target_actor_id']),iid,day=day)
        rels=c.execute("select * from patronage_relationships where beneficiary_actor_id=? and status='active'",(artist,)).fetchall()
        assert len(rels)==2 and all(float(r['exclusivity'])==0 for r in rels)
        net=patronage_network(c,'art_culture')
        assert net['relationships']>=2 and net['multi_patron_beneficiaries']>=1

        # Two patrons can independently compete for a rising talent with exclusive offers.
        a_pid,a_iid=propose_patronage(c,p1,rival_artist,'art_culture',title='Exclusive Merchant Patronage',amount_per_cycle=9,recurrence_days=30,duration_days=360,exclusivity=1)
        b_pid,b_iid=propose_patronage(c,p2,rival_artist,'art_culture',title='Exclusive Noble Patronage',amount_per_cycle=10,recurrence_days=30,duration_days=360,exclusivity=1)
        assert refresh_patronage_competitions(c,day)==1
        comp=c.execute("select * from patronage_competitions where beneficiary_actor_id=? and domain_key='art_culture' and status='active'",(rival_artist,)).fetchone()
        assert comp
        entries=c.execute("select * from patronage_competition_entries where competition_id=?",(int(comp['id']),)).fetchall()
        assert len(entries)==2
        # Talent accepts the noble's exclusive offer; the rival proposal is closed and competition records winner/loser.
        accept_proposal(c,b_pid,rival_artist,b_iid,day=day)
        comp2=c.execute("select * from patronage_competitions where id=?",(int(comp['id']),)).fetchone()
        assert str(comp2['status'])=='resolved' and int(comp2['winning_patron_actor_id'])==p2
        assert str(c.execute("select status from opportunity_proposals where id=?",(a_pid,)).fetchone()[0])=='withdrawn'
        erows=c.execute("select proposal_id,status from patronage_competition_entries where competition_id=? order by proposal_id",(int(comp['id']),)).fetchall()
        assert {str(x['status']) for x in erows}=={'won','lost'}
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('PATRONNET-01 beneficiary seeking + patron competition acceptance PASS')
    finally:
        c.close()

if __name__=='__main__': main()
