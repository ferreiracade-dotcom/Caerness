from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.civilian import create_enterprise, add_production_site
from engine.business import configure_enterprise_business
from engine.seeking import process_due_seeking


def main():
    reset_db(force=True, backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit()
    try:
        day=0
        crownhold=int(c.execute("select id from locations where name='Crownhold'").fetchone()[0])
        horses=int(c.execute("select id from market_goods where good_key='horses_remounts'").fetchone()[0])
        breeder=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values ('SEEK Auto Studmaster','character','horse breeder',?,?, 'active','SEEK enterprise projection',0)",(crownhold,crownhold)).lastrowid)
        c.execute("insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,'ACTIVE',7,.3,.75,0,7,2)",(breeder,))
        c.execute("insert or replace into player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) values (1,?,?, 'SEEK auto enterprise',0)",(breeder,crownhold))
        eid=create_enterprise(c,'SEEK Automatically Discoverable Stud','estate',owner_actor_id=breeder,location_id=crownhold,capital=180,cash=90,reputation=92,admin_quality=80,labor_capacity=75,risk_tolerance=40)
        configure_enterprise_business(c,eid,'horse_breeder',quality=94,capacity=78,clientele_fit=90,service_reliability=92)
        add_production_site(c,eid,horses,capacity_per_30=14,efficiency=90,material_access=82,skilled_labor=92,inventory=36)
        assert not c.execute("select 1 from seekable_offerings where provider_enterprise_id=?",(eid,)).fetchone()
        process_due_seeking(c,day)
        process_due_seeking(c,day+1)
        offer=c.execute("select * from seekable_offerings where provider_enterprise_id=? and domain_key='military_logistics' and subject_key='remounts' and status='active'",(eid,)).fetchone()
        assert offer, 'real horse-breeding capability was not projected into discoverable provider state'
        pending=c.execute("select * from interactions where recipient_actor_id=? and status='pending' and interaction_type='contract' order by id limit 1",(breeder,)).fetchone()
        assert pending, 'ordinary polity need did not independently discover the player business'
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('SEEK-01 enterprise capability projection acceptance PASS')
    finally:
        c.close()

if __name__=='__main__': main()
