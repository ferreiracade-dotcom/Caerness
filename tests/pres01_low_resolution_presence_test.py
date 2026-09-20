"""PRES-01 acceptance: shared low-resolution presence with explicit override precedence."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.ecology import add_route, start_travel
from engine.presence import (
    assess_presence, add_presence_habit, actors_plausibly_present,
    seed_presence_from_existing_state,
)
from engine.information import _expose_present_actors


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_pres01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect(); return c,path


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=61
    c,path=bootstrap()
    assert c.execute("SELECT value FROM engine_meta WHERE key='presence_model_version'").fetchone()[0]=='1'

    city=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[PRES] Great City','city')").lastrowid)
    district=int(c.execute("INSERT INTO locations(name,kind,parent_location_id) VALUES ('[PRES] Counting House Ward','district',?)",(city,)).lastrowid)
    far=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[PRES] Far City','city')").lastrowid)
    a=int(c.execute("INSERT INTO actors(name,actor_type,home_location_id,current_location_id) VALUES ('[PRES] Ada','character',?,?)",(city,city)).lastrowid)
    b=int(c.execute("INSERT INTO actors(name,actor_type,home_location_id,current_location_id) VALUES ('[PRES] Bram','character',?,?)",(city,city)).lastrowid)
    c.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days) VALUES (?,'DORMANT',30)",(b,))

    # Same broad city assignment is not exact co-presence.
    broad=assess_presence(c,a,city,day=0)
    assert broad.resolution=='habitual' and 0.0 < broad.probability < 1.0, broad
    exact_absent=assess_presence(c,a,city,day=0,exact_present_actor_ids=(),exact_scene_complete=True)
    assert exact_absent.resolution=='exact_scene' and exact_absent.probability==0.0

    # A habitual workplace materially raises encounter probability at that actual place.
    before=assess_presence(c,a,district,day=0).probability
    add_presence_habit(c,a,district,habit_kind='work',weight=0.95,confidence=1.0,cadence_days=1,basis_kind='test_workplace',basis_id=1,effective_from_day=0)
    after=assess_presence(c,a,district,day=0).probability
    assert after > before + 0.5, (before,after)

    # Explicit tracked travel overrides stale habits.
    add_route(c,city,far,base_days=3.0,reliability=100)
    start_travel(c,'actor',a,far)
    travelling=assess_presence(c,a,district,day=0)
    assert travelling.resolution=='tracked_travel' and travelling.probability==0.0, travelling

    # Exact scene state is the highest-resolution fact and overrides travel/habits.
    exact_here=assess_presence(c,a,district,day=0,exact_present_actor_ids=(a,),exact_scene_complete=True)
    assert exact_here.resolution=='exact_scene' and exact_here.probability==1.0

    # Dormant NPCs use the identical API/rules; no protagonist privilege.
    add_presence_habit(c,b,district,habit_kind='work',weight=1.0,confidence=1.0,cadence_days=1,basis_kind='test_workplace',basis_id=2,effective_from_day=0)
    present=actors_plausibly_present(c,district,day=0,purpose='pres01_acceptance')
    assert b in present and a not in present, present

    # Rumour exposure consumes that same shared presence substrate.
    rid=int(c.execute("INSERT INTO rumours(created_day,origin_location_id,text,distortion,reach) VALUES (0,?,'[PRES] dock rumour',0,1)",(district,)).lastrowid)
    c.execute("INSERT INTO rumour_locations(rumour_id,location_id,first_arrived_day,last_updated_day,prevalence,fidelity,hop_count) VALUES (?,?,0,0,1,1,0)",(rid,district))
    _expose_present_actors(c,rid,district,0)
    assert c.execute("SELECT 1 FROM rumour_exposures WHERE rumour_id=? AND actor_id=?",(rid,b)).fetchone()
    assert not c.execute("SELECT 1 FROM rumour_exposures WHERE rumour_id=? AND actor_id=?",(rid,a)).fetchone()

    # Migration/late seeding creates only present-day derived anchors, never invented history.
    c.execute("UPDATE world_state SET current_day=123 WHERE id=1")
    late=int(c.execute("INSERT INTO actors(name,actor_type,home_location_id,current_location_id) VALUES ('[PRES] Late Actor','character',?,?)",(city,city)).lastrowid)
    seed_presence_from_existing_state(c,effective_day=123)
    prow=c.execute("SELECT effective_from_day FROM actor_presence_profiles WHERE actor_id=?",(late,)).fetchone()
    hdays=[int(r[0]) for r in c.execute("SELECT effective_from_day FROM actor_presence_habits WHERE actor_id=?",(late,)).fetchall()]
    assert prow and int(prow[0])==123 and hdays and min(hdays)==123

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    c.commit(); c.close()
    print('PRES-01 low-resolution presence tests: PASS')

if __name__=='__main__': run()
