from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.ecology import (
    configure_environment, add_seasonal_window, add_route, start_travel, register_current_use,
    ecology_context, current_sustainability, environment_effects,
)
from engine.civilian import create_enterprise, ensure_good, set_market_condition, add_production_site
from engine.household_life import set_life_profile
from engine.player import set_player, build_scene_packet
from engine.simulation import advance_connection


def actor(c,name,loc):
    c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES (?,'character',?,?)",(name,loc,loc))
    return int(c.execute("SELECT id FROM actors WHERE name=?",(name,)).fetchone()[0])


def run():
    reset_db(); init_db(); assert ENGINE_VERSION in {'0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0'}
    with connect() as c:
        # No campaign geography/calendar is silently invented by the engine.
        assert c.execute("SELECT COUNT(*) FROM location_environment_profiles").fetchone()[0]==0
        assert c.execute("SELECT COUNT(*) FROM seasonal_windows").fetchone()[0]==0
        assert c.execute("SELECT COUNT(*) FROM travel_routes").fetchone()[0]==0

        for n,k in [('Lowfield','town'),('High Pass','pass'),('Riverport','town')]:
            c.execute("INSERT INTO locations(name,kind) VALUES (?,?)",(n,k))
        low=int(c.execute("SELECT id FROM locations WHERE name='Lowfield'").fetchone()[0])
        high=int(c.execute("SELECT id FROM locations WHERE name='High Pass'").fetchone()[0])
        port=int(c.execute("SELECT id FROM locations WHERE name='Riverport'").fetchone()[0])

        configure_environment(c,low,climate_label='campaign-lowland',terrain_kind='plain',year_length=120,
                              current_replenishment=60,current_carrying_capacity=100)
        configure_environment(c,high,climate_label='campaign-upland',terrain_kind='pass',year_length=120,
                              base_health_pressure=4,current_replenishment=35,current_carrying_capacity=70)
        configure_environment(c,port,climate_label='campaign-river',terrain_kind='river',year_length=120)
        add_seasonal_window(c,low,'Campaign wet period',0,29,travel_factor=1.5,production_factor=.55,
                            health_pressure=8,current_replenishment_factor=.7,route_risk_delta=5)
        assert environment_effects(c,low,0)['season_name']=='Campaign wet period'

        r1=add_route(c,low,high,route_kind='road',base_days=2)
        r2=add_route(c,high,port,route_kind='road',base_days=3)
        assert r1 and r2
        traveller=actor(c,'Teren Vale',low)
        set_life_profile(c,traveller,birth_day=-30*365)
        plan=start_travel(c,'actor',traveller,port)
        assert plan>0

        # Ecology changes market/production constraints through the shared story clock.
        ent=create_enterprise(c,'Lowfield Grain Yard','estate',location_id=low,cash=100,capital=100)
        good=ensure_good(c,'grain_test','Test Grain','grain',base_price=10)
        set_market_condition(c,low,good,supply=50,demand=50,transport_pressure=0,risk_pressure=0,tax_pressure=0)
        add_production_site(c,ent,good,capacity_per_30=20,efficiency=100,material_access=100,skilled_labor=100)

        register_current_use(c,low,80,description='heavy cultivation test load')
        assert current_sustainability(c,low)['load']==80
        advance_connection(c,12)
        assert c.execute("SELECT status FROM travel_plans WHERE id=?",(plan,)).fetchone()[0]=='arrived'
        assert int(c.execute("SELECT current_location_id FROM actors WHERE id=?",(traveller,)).fetchone()[0])==port
        assert c.execute("SELECT COUNT(*) FROM events WHERE event_type='travel_arrival'").fetchone()[0]>=1

        # The environmental transport modifier is used by the ordinary market resolver.
        advance_connection(c,18)
        price=float(c.execute("SELECT current_price FROM market_conditions WHERE location_id=? AND good_id=?",(low,good)).fetchone()[0])
        assert price>10.0
        # Current load recovers rather than freezing off-camera.
        cur=current_sustainability(c,low)
        assert 0 <= cur['load'] < 80
        # Seasonal production factor actually reduced output relative to a 20-unit unconstrained month.
        produced_and_left=float(c.execute("SELECT inventory FROM production_sites WHERE enterprise_id=? AND good_id=?",(ent,good)).fetchone()[0])
        revenue=float(c.execute("SELECT COALESCE(SUM(amount),0) FROM enterprise_accounts WHERE enterprise_id=? AND account_kind='revenue'",(ent,)).fetchone()[0])
        assert produced_and_left + revenue/price < 20.0

        set_player(c,traveller,campaign_name='Ecology test')
        packet=build_scene_packet(c,'I consider the roads and local conditions.')
        assert 'environment_context' in packet
        assert packet['environment_context']['profile'] is not None
        ctx=ecology_context(c,port)
        assert 'current' in ctx and 'routes' in ctx
        c.commit()
    print('v0.22 ecology/seasons/travel regression PASS')

if __name__=='__main__': run()
