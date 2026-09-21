from __future__ import annotations
"""CONFLICTGEO-01 — military geography is not identical to the civilian road graph."""
import json, sqlite3
from typing import Any

def _j(v:Any)->str: return json.dumps(v if v is not None else {},sort_keys=True,ensure_ascii=False)
def _pair(a:int,b:int)->tuple[int,int]: return (a,b) if a<=b else (b,a)

def add_conflict_geometry(conn,location_a_id,location_b_id,geometry_kind,*,traversable=True,military_feasibility=50,civilian_feasibility=50,source_kind='engine_derived',source_id=None,metadata=None):
    if int(location_a_id)==int(location_b_id): raise ValueError('conflict geometry requires distinct locations')
    a,b=_pair(int(location_a_id),int(location_b_id))
    for loc in (a,b):
        if not conn.execute('SELECT 1 FROM locations WHERE id=?',(loc,)).fetchone(): raise ValueError('unknown location')
    conn.execute("""INSERT INTO conflict_geometries(location_a_id,location_b_id,geometry_kind,traversable,military_feasibility,civilian_feasibility,source_kind,source_id,metadata_json)
                    VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(location_a_id,location_b_id,geometry_kind) DO UPDATE SET traversable=excluded.traversable,military_feasibility=excluded.military_feasibility,civilian_feasibility=excluded.civilian_feasibility,source_kind=excluded.source_kind,source_id=excluded.source_id,metadata_json=excluded.metadata_json""",
                 (a,b,str(geometry_kind),1 if traversable else 0,max(0,min(100,float(military_feasibility))),max(0,min(100,float(civilian_feasibility))),str(source_kind),source_id,_j(metadata)))
    return int(conn.execute('SELECT id FROM conflict_geometries WHERE location_a_id=? AND location_b_id=? AND geometry_kind=?',(a,b,str(geometry_kind))).fetchone()[0])

def activate_conflict_geometry(conn):
    road_rows=0
    for r in conn.execute("SELECT id,from_location_id,to_location_id,status,reliability FROM travel_routes WHERE status IN ('open','restricted') ORDER BY id"):
        add_conflict_geometry(conn,int(r['from_location_id']),int(r['to_location_id']),'civilian_route',traversable=True,military_feasibility=max(25,float(r['reliability'])),civilian_feasibility=max(20,float(r['reliability'])),source_kind='travel_route',source_id=int(r['id']),metadata={'projected_from_existing_route':True}); road_rows+=1
    east=conn.execute("SELECT id FROM locations WHERE name='Eastwatch' ORDER BY id LIMIT 1").fetchone(); west=conn.execute("SELECT id FROM locations WHERE name='Westgate' ORDER BY id LIMIT 1").fetchone(); frontier=0
    if east and west:
        add_conflict_geometry(conn,int(east[0]),int(west[0]),'military_frontier',traversable=True,military_feasibility=72,civilian_feasibility=8,source_kind='recovered_opening_geography',metadata={'direct_military_contact':True,'civilian_road_not_required':True,'does_not_imply_active_war':True}); frontier=1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('conflictgeo01_runtime_version','1')")
    return {'conflict_geometry_route_rows':road_rows,'eastwatch_westgate_frontier':frontier}

def military_geometry_between(conn,location_a_id,location_b_id):
    a,b=_pair(int(location_a_id),int(location_b_id))
    return conn.execute("""SELECT * FROM conflict_geometries WHERE location_a_id=? AND location_b_id=? AND traversable=1 ORDER BY CASE geometry_kind WHEN 'military_frontier' THEN 0 WHEN 'wilderness_corridor' THEN 1 WHEN 'maritime' THEN 2 ELSE 3 END,military_feasibility DESC,id LIMIT 1""",(a,b)).fetchone()

def direct_military_travel_days(conn,location_a_id,location_b_id):
    row=military_geometry_between(conn,location_a_id,location_b_id)
    if not row or float(row['military_feasibility'])<=0: return None
    meta=json.loads(row['metadata_json'] or '{}')
    if meta.get('base_days') is not None: return max(1.0,float(meta['base_days']))
    feasibility=max(1.0,float(row['military_feasibility']))
    return max(2.0,min(21.0,2.0+(100.0-feasibility)/8.0))

def military_access_exists(conn,location_a_id,location_b_id):
    if int(location_a_id)==int(location_b_id): return True
    return military_geometry_between(conn,location_a_id,location_b_id) is not None
