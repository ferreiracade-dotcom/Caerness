from __future__ import annotations
import os, sys, tempfile, random
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.underworld import create_underworld_organization
from engine.underworld_rebuild import create_personnel, create_crew, create_zone, set_zone_controller, ensure_zone_staffing, ensure_crew_leadership
import engine.person_ecology as person_ecology

def run():
    path=Path(tempfile.gettempdir())/f'caerness_tenyear02_underworld_defer_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c)
    try:
        loc=int(c.execute("select id from locations where name='Aldergate'").fetchone()[0])
        org=create_underworld_organization(c,'test-tenyear02-staff-defer','gang',name='[TEST] Staffing Defer Gang',primary_location_id=loc,member_count_estimate=20,command_depth=1)
        boss=create_personnel(c,org,role_kind='boss',rng=random.Random(1))
        z1=create_zone(c,loc,'test-staffed-zone','[TEST] Staffed Zone')
        z2=create_zone(c,loc,'test-unstaffed-zone','[TEST] Unstaffed Zone')
        set_zone_controller(c,z1,org); set_zone_controller(c,z2,org)
        crew=create_crew(c,org,'[TEST] Donor Crew',home_zone_id=z1,size_estimate=24,rng=random.Random(2))
        before_n=int(c.execute("select count(*) from underworld_crews where organization_id=? and status='active'",(org,)).fetchone()[0])
        before_man=float(c.execute("select sum(size_estimate) from underworld_crews where organization_id=? and status='active'",(org,)).fetchone()[0])
        original=person_ecology.resolve_background_person
        person_ecology.resolve_background_person=lambda *a,**k: None
        try:
            out=ensure_zone_staffing(c,org,rng=random.Random(3))
            after_n=int(c.execute("select count(*) from underworld_crews where organization_id=? and status='active'",(org,)).fetchone()[0])
            after_man=float(c.execute("select sum(size_estimate) from underworld_crews where organization_id=? and status='active'",(org,)).fetchone()[0])
            assert z2 in out['understaffed_zones'], out
            assert before_n==after_n==1,(before_n,after_n)
            assert abs(before_man-after_man)<1e-9,(before_man,after_man)
            # A low-resolution command vacancy also defers without inventing a person or aborting.
            c.execute("update underworld_crews set leader_actor_id=null where id=?",(crew,))
            assert ensure_crew_leadership(c,org,rng=random.Random(4))==0
            assert c.execute("select leader_actor_id from underworld_crews where id=?",(crew,)).fetchone()[0] is None
        finally:
            person_ecology.resolve_background_person=original
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('TENYEAR02 underworld person-reservoir deferral PASS', {'organization':org,'deferred_zone':z2,'manpower':before_man,'boss':boss})
    finally:
        c.close()
        try: path.unlink()
        except FileNotFoundError: pass
if __name__=='__main__': run()
