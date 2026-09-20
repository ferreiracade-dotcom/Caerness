from __future__ import annotations
import sqlite3, tempfile
from pathlib import Path

from engine.db import init_db
from engine.current_seed import import_current_seed, DEFAULT_CURRENT_SEED
from engine.activation import activate_existing_loops
from engine.ecology import build_route_path_snapshot, find_route_path, find_route_path_snapshot, evaluate_route_leg, route_information_lag_snapshot
from engine.merchant import _route_information_lag


def run():
    td=tempfile.TemporaryDirectory(); p=Path(td.name)/'r.db'
    c=sqlite3.connect(p); c.row_factory=sqlite3.Row; c.execute('pragma foreign_keys=on')
    # init_db owns the normal connection path, so use schema directly for isolated test.
    c.executescript((Path(__file__).resolve().parents[1]/'engine'/'schema.sql').read_text())
    # Minimal world/routes with deterministic equal and unequal alternatives.
    c.execute("insert into world_state(id,current_day,rng_seed) values (1,10,42)")
    for i,n in [(1,'A'),(2,'B'),(3,'C'),(4,'D')]:
        c.execute("insert into locations(id,name,kind) values (?,?, 'town')",(i,n))
    for i in range(1,5):
        c.execute("insert into location_environment_profiles(location_id,year_length,base_travel_factor,base_production_factor,base_health_pressure,current_density,current_stability,current_replenishment,current_breadth,current_concentration,current_carrying_capacity,current_load,last_review_day,next_review_day,metadata_json) values (?,360,1,1,0,50,50,50,50,50,100,0,0,30,'{}')",(i,))
    routes=[(1,1,2,2.0),(2,2,4,2.0),(3,1,3,1.0),(4,3,4,5.0)]
    for rid,a,b,d in routes:
        c.execute("insert into travel_routes(id,from_location_id,to_location_id,route_kind,base_days,capacity,reliability,bidirectional,seasonal_sensitivity,status,metadata_json) values (?,?,?,'road',?,100,100,1,1,'open','{}')",(rid,a,b,d))
    snap=build_route_path_snapshot(c,day=10)
    for o in range(1,5):
        for d in range(1,5):
            p1=find_route_path(c,o,d,day=10); p2=find_route_path_snapshot(snap,o,d)
            assert p1==p2,(o,d,p1,p2)
            assert _route_information_lag(c,o,d,10)==route_information_lag_snapshot(snap,o,d)
    # Same-day restriction is reflected by a newly built snapshot, while old snapshot is immutable.
    c.execute("insert into route_conditions(route_id,condition_kind,label,start_day,end_day,accessibility,delay_factor,hazard_pressure,status,metadata_json) values (1,'closure','test',10,10,0,1,0,'active','{}')")
    fresh=build_route_path_snapshot(c,day=10)
    assert find_route_path_snapshot(fresh,1,4)==find_route_path(c,1,4,day=10)
    assert find_route_path_snapshot(fresh,1,4)!=find_route_path_snapshot(snap,1,4)
    assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
    assert not c.execute('pragma foreign_key_check').fetchall()
    c.close(); td.cleanup(); print('ROUTE01 PASS')

if __name__=='__main__': run()
