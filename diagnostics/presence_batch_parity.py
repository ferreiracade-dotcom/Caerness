from __future__ import annotations
import os, tempfile, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
os.environ['CAERNESS_TEST_MODE']='1'; os.environ['CAERNESS_DB_PATH']=str(Path(tempfile.gettempdir())/'caerness_presence_batch_parity.db')
from engine.db import reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.presence import actor_is_present_candidate, actors_plausibly_present, _current_day

def old_reference(conn, location_id, *, day=None, purpose='ordinary_contact', exact_present_actor_ids=None, exact_scene_complete=False):
    day=_current_day(conn) if day is None else int(day)
    ids={int(r[0]) for r in conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active'").fetchall()}
    if exact_present_actor_ids is not None:
        ids.update(int(x) for x in exact_present_actor_ids)
    return sorted(aid for aid in ids if actor_is_present_candidate(conn,aid,location_id,day=day,purpose=purpose,
        exact_present_actor_ids=exact_present_actor_ids,exact_scene_complete=exact_scene_complete))

def run():
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit()
    locations=[int(r[0]) for r in c.execute("""select distinct location_id from actor_presence_habits where location_id is not null order by location_id limit 12""").fetchall()]
    # Add travel endpoints and the largest named settlements to exercise the important branches.
    locations += [int(r[0]) for r in c.execute("select distinct current_location_id from travel_plans where current_location_id is not null limit 4").fetchall() if int(r[0]) not in locations]
    locations += [int(r[0]) for r in c.execute("select s.location_id from settlement_scale_profiles s order by population_estimate desc limit 4").fetchall() if int(r[0]) not in locations]
    checks=0
    for day in (0,1,30,90):
        for loc in locations:
            for purpose in ('ordinary_contact',f'rumour:{loc}'):
                a=old_reference(c,loc,day=day,purpose=purpose)
                b=actors_plausibly_present(c,loc,day=day,purpose=purpose)
                assert a==b,(day,loc,purpose,a,b)
                checks+=1
    # exact-scene semantics, including an id outside the active-character query.
    loc=locations[0]
    active=int(c.execute("select id from actors where actor_type='character' and status='active' order by id limit 1").fetchone()[0])
    fake=99999999
    for complete in (False,True):
        a=old_reference(c,loc,day=30,purpose='scene',exact_present_actor_ids=(active,fake),exact_scene_complete=complete)
        b=actors_plausibly_present(c,loc,day=30,purpose='scene',exact_present_actor_ids=(active,fake),exact_scene_complete=complete)
        assert a==b,(complete,a,b); checks+=1
    print('PRESENCE BATCH PARITY PASS',{'checks':checks,'locations':len(locations),'days':4})
    c.close()
if __name__=='__main__': run()
