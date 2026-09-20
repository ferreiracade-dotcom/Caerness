from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.ecology import (
    configure_environment, add_seasonal_window, add_environmental_condition, add_route, add_route_condition,
    start_travel, register_current_use, current_sustainability, environment_effects, find_route_path,
)
from engine.civilian import create_household, add_household_member
from engine.household_life import mark_actor_deceased
from engine.simulation import advance_connection


def loc(c,n):
    c.execute("INSERT INTO locations(name,kind) VALUES (?,'town')",(n,)); return int(c.execute("SELECT id FROM locations WHERE name=?",(n,)).fetchone()[0])

def actor(c,n,l):
    c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES (?,'character',?,?)",(n,l,l)); return int(c.execute("SELECT id FROM actors WHERE name=?",(n,)).fetchone()[0])

def expect_error(fn):
    try: fn()
    except (ValueError, Exception): return
    raise AssertionError('expected error')


def run():
    reset_db(); init_db(); assert ENGINE_VERSION in {'0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0'}
    with connect() as c:
        a,b,d,e=[loc(c,n) for n in ('A','B','D','E')]
        for x in (a,b,d,e): configure_environment(c,x,year_length=100,current_carrying_capacity=50,current_replenishment=50)

        # No season names/calendar are generated unless campaign state defines them.
        assert c.execute("SELECT COUNT(*) FROM seasonal_windows").fetchone()[0]==0
        expect_error(lambda: add_seasonal_window(c,a,'bad',0,100))
        wrap=add_seasonal_window(c,a,'wrap',80,10,travel_factor=1.4)
        assert wrap>0 and environment_effects(c,a,95)['season_name']=='wrap' and environment_effects(c,a,5)['season_name']=='wrap'
        assert environment_effects(c,a,50)['season_name'] is None

        # One-way routes really are one-way.
        one=add_route(c,a,b,base_days=2,bidirectional=False)
        assert find_route_path(c,a,b)
        assert find_route_path(c,b,a)==[]

        # A blocked onward segment stalls rather than teleporting or ignoring the closure.
        bd=add_route(c,b,d,base_days=2)
        add_route_condition(c,bd,'closure','campaign closure',1,end_day=4,accessibility=0)
        t=actor(c,'Walker',a)
        p=start_travel(c,'actor',t,d)
        expect_error(lambda: start_travel(c,'actor',t,d))
        advance_connection(c,3)
        assert int(c.execute("SELECT current_location_id FROM actors WHERE id=?",(t,)).fetchone()[0])==b
        assert c.execute("SELECT status FROM travel_plans WHERE id=?",(p,)).fetchone()[0]=='stalled'
        advance_connection(c,5)
        assert c.execute("SELECT status FROM travel_plans WHERE id=?",(p,)).fetchone()[0]=='arrived'

        # Temporary environment pressure expires instead of becoming permanent climate.
        add_environmental_condition(c,d,'storm','temporary pressure',7,end_day=8,travel_factor=2,health_pressure=25)
        assert float(environment_effects(c,d,7)['travel_factor'])>1
        assert float(environment_effects(c,d,9)['travel_factor'])==1.0

        # Current load may exceed carrying capacity, but availability floors at zero and replenishment never makes load negative.
        register_current_use(c,e,80)
        cur=current_sustainability(c,e); assert cur['load']==80 and cur['available']==0
        advance_connection(c,120)
        cur=current_sustainability(c,e); assert cur['load']>=0 and cur['load']<80

        # Household travel moves its active members together.
        h1=actor(c,'Head',d); h2=actor(c,'Member',d)
        hh=create_household(c,'Road Household',head_actor_id=h1,location_id=d,wealth=10,liquidity=10)
        add_household_member(c,hh,h2,role='family')
        de=add_route(c,d,e,base_days=1)
        hp=start_travel(c,'household',hh,e)
        advance_connection(c,2)
        assert c.execute("SELECT status FROM travel_plans WHERE id=?",(hp,)).fetchone()[0]=='arrived'
        assert int(c.execute("SELECT current_location_id FROM actors WHERE id=?",(h2,)).fetchone()[0])==e


        # Scheduled household migration uses crystallized route geography instead of instant relocation.
        from engine.household_life import schedule_household_migration
        mhead=actor(c,'Migration Head',a)
        mhh=create_household(c,'Migration Household',head_actor_id=mhead,location_id=a,wealth=10,liquidity=10)
        now=int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        mid=schedule_household_migration(c,mhh,b,planned_day=now+1,reason='route audit')
        advance_connection(c,1)
        assert c.execute("SELECT status FROM household_migration_plans WHERE id=?",(mid,)).fetchone()[0]=='in_transit'
        assert int(c.execute("SELECT location_id FROM households WHERE id=?",(mhh,)).fetchone()[0])==a
        advance_connection(c,4)
        assert c.execute("SELECT status FROM household_migration_plans WHERE id=?",(mid,)).fetchone()[0]=='completed'
        assert int(c.execute("SELECT location_id FROM households WHERE id=?",(mhh,)).fetchone()[0])==b

        # High travel hazard can create an abstract health consequence, but ecology does not own recovery.
        f=loc(c,'F'); g=loc(c,'G')
        configure_environment(c,f,year_length=100); configure_environment(c,g,year_length=100)
        fg=add_route(c,f,g,base_days=4,reliability=0)
        now=int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        add_route_condition(c,fg,'hazard','hard journey',now,hazard_pressure=100)
        exposed=actor(c,'Exposed',f)
        ep=start_travel(c,'actor',exposed,g)
        advance_connection(c,5)
        assert c.execute("SELECT COUNT(*) FROM health_conditions WHERE actor_id=? AND label='Travel exposure'",(exposed,)).fetchone()[0]==1

        # Death during travel cancels the plan; dead actors never arrive later.
        deathstart=actor(c,'Doomed Traveller',f)
        dp=start_travel(c,'actor',deathstart,g)
        mark_actor_deceased(c,deathstart,reason='test')
        advance_connection(c,5)
        assert c.execute("SELECT status FROM travel_plans WHERE id=?",(dp,)).fetchone()[0]=='cancelled'
        c.commit()
    print('v0.22 adversarial ecology/travel edge-case audit PASS')

if __name__=='__main__': run()
