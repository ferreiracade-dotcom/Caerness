from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, SCHEMA_VERSION, connect, init_db, reset_db
from engine.civilian import create_enterprise, ensure_good, set_market_condition, add_production_site
from engine.ecology import add_route, add_route_condition
from engine.decisions import decide_actor
from engine.logistics import logistics_summary, process_due_logistics


def run():
    assert ENGINE_VERSION in {'0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION >= 29
    reset_db(); init_db()
    with connect() as c:
        a=int(c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('Logistics A','town',0)").lastrowid)
        b=int(c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('Logistics B','town',0)").lastrowid)
        d=int(c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('Logistics C','town',0)").lastrowid)
        owner=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES ('Logistics Merchant','character',?,'active')",(a,)).lastrowid)
        c.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day) VALUES (?,'ACTIVE',30,.2,.6,0,30)",(owner,))
        e=create_enterprise(c,'Logistics Mill','workshop',owner_actor_id=owner,location_id=a,capital=30,cash=10,reputation=40,admin_quality=50,labor_capacity=50,risk_tolerance=45)
        g=ensure_good(c,'fixture-grain','Fixture Grain','food',10,unit='sack')
        set_market_condition(c,a,g,supply=80,demand=35,transport_pressure=0,risk_pressure=0,tax_pressure=0)
        set_market_condition(c,d,g,supply=25,demand=90,transport_pressure=0,risk_pressure=0,tax_pressure=0)
        ps=add_production_site(c,e,g,capacity_per_30=20,efficiency=60,material_access=60,skilled_labor=50,inventory=20)
        r1=add_route(c,a,b,route_kind='road',base_days=1,reliability=90)
        r2=add_route(c,b,d,route_kind='road',base_days=1,reliability=90)

        # The actor autonomously dispatches real inventory to a real higher-price connected market.
        did=decide_actor(c,owner,'ACTIVE',0)
        dec=c.execute("SELECT * FROM decisions WHERE id=?",(did,)).fetchone()
        assert dec['action_type']=='domain_action', dict(dec)
        assert c.execute("SELECT COUNT(*) FROM autonomous_action_attempts WHERE actor_id=? AND action_kind='arrange_shipment' AND status='applied'",(owner,)).fetchone()[0]==1
        sh=c.execute("SELECT * FROM commercial_shipments ORDER BY id DESC LIMIT 1").fetchone(); assert sh
        qty=float(sh['quantity'])
        assert abs(float(c.execute("SELECT inventory FROM production_sites WHERE id=?",(ps,)).fetchone()[0]) + qty - 20.0) < 1e-8
        assert logistics_summary(c)['cargo_quantity']==qty

        # A route closure delays the cargo at the intermediate location; cargo is neither duplicated nor teleported.
        add_route_condition(c,r2,'closure','fixture closure',1,end_day=3,accessibility=0,delay_factor=1,hazard_pressure=0)
        c.execute("UPDATE world_state SET current_day=1 WHERE id=1")
        process_due_logistics(c,1)
        sh=c.execute("SELECT * FROM commercial_shipments WHERE id=?",(sh['id'],)).fetchone()
        assert sh['status']=='stalled' and int(sh['current_location_id'])==b
        source=float(c.execute("SELECT inventory FROM production_sites WHERE id=?",(ps,)).fetchone()[0])
        stock=float(c.execute("SELECT COALESCE(SUM(quantity),0) FROM commercial_stock WHERE enterprise_id=? AND good_id=?",(e,g)).fetchone()[0])
        cargo=float(c.execute("SELECT COALESCE(SUM(quantity),0) FROM commercial_shipments WHERE enterprise_id=? AND good_id=? AND status IN ('in_transit','stalled')",(e,g)).fetchone()[0])
        assert abs(source+stock+cargo-20.0)<1e-8 and stock==0 and cargo==qty

        # Once the route reopens, the same cargo arrives exactly once and becomes destination stock.
        c.execute("UPDATE world_state SET current_day=4 WHERE id=1")
        process_due_logistics(c,4)
        c.execute("UPDATE world_state SET current_day=5 WHERE id=1")
        process_due_logistics(c,5)
        sh=c.execute("SELECT * FROM commercial_shipments WHERE id=?",(sh['id'],)).fetchone()
        assert sh['status']=='delivered' and int(sh['current_location_id'])==d
        stock=float(c.execute("SELECT quantity FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",(e,d,g)).fetchone()[0])
        cargo=float(c.execute("SELECT COALESCE(SUM(quantity),0) FROM commercial_shipments WHERE enterprise_id=? AND good_id=? AND status IN ('in_transit','stalled')",(e,g)).fetchone()[0])
        assert abs(source+stock+cargo-20.0)<1e-8 and stock==qty and cargo==0
        # Reprocessing the terminal day cannot duplicate delivery.
        process_due_logistics(c,5)
        stock2=float(c.execute("SELECT quantity FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",(e,d,g)).fetchone()[0])
        assert stock2==stock
        c.commit()
    print('v0.29.0 commercial logistics conservation regression PASS')

if __name__=='__main__': run()
