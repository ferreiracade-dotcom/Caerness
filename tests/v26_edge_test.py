from __future__ import annotations
import sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import connect, init_db, reset_db
from engine.bootstrap import bootstrap_campaign

LEGACY_V026_CANON = ROOT / 'tests' / 'fixtures' / 'v026_world_bible_current.docx'

from engine.simulation import advance_connection
from engine.stress import contradiction_scan
from engine.player import set_player
from engine.ecology import add_route, add_route_condition
from engine.information import register_event_information, process_information
from engine.household_life import set_life_profile, mark_actor_deceased


def actor(c,name,loc=None):
    cur=c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'character',?,'active')",(name,loc)); return int(cur.lastrowid)

def issue_keys(c): return {x['issue_key'] for x in contradiction_scan(c)}


def run():
    # Ownership-mirror scanner catches deliberate divergence in each authoritative/mirror pair.
    reset_db(); init_db()
    with connect() as c:
        c.execute("INSERT INTO locations(name,kind) VALUES ('Mirror Place','town')"); loc=int(c.execute("SELECT id FROM locations WHERE name='Mirror Place'").fetchone()[0])
        a=actor(c,'Mirror Person',loc); set_life_profile(c,a,birth_day=-30*365)
        set_player(c,a,'Mirror Audit')
        c.execute("UPDATE actor_life_profiles SET life_status='deceased' WHERE actor_id=?",(a,))
        c.execute("UPDATE player_state SET current_location_id=NULL WHERE id=1")
        keys=issue_keys(c)
        assert 'life_status_mirror' in keys
        assert 'player_location_mirror' in keys

    # Normal profile cadence is authoritative: DORMANT no longer gets silently clamped to 60 days.
    reset_db(); init_db()
    with connect() as c:
        a=actor(c,'Slow Structural Actor')
        c.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day) VALUES (?,'DORMANT',120,0,0.5,0,120)",(a,))
        advance_connection(c,119)
        assert c.execute('SELECT COUNT(*) FROM decisions WHERE actor_id=?',(a,)).fetchone()[0]==0
        advance_connection(c,1)
        assert c.execute('SELECT COUNT(*) FROM decisions WHERE actor_id=?',(a,)).fetchone()[0]==1


    # Death retires autonomous scheduling immediately; no posthumous decisions are allowed.
    reset_db(); init_db()
    with connect() as c:
        a=actor(c,'Retired By Death')
        set_life_profile(c,a,birth_day=-70*365)
        c.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day) VALUES (?,'DORMANT',30,0,0.5,0,30)",(a,))
        advance_connection(c,30)
        before=int(c.execute('SELECT COUNT(*) FROM decisions WHERE actor_id=?',(a,)).fetchone()[0])
        mark_actor_deceased(c,a,reason='scheduler retirement audit')
        assert c.execute('SELECT 1 FROM simulation_profiles WHERE actor_id=?',(a,)).fetchone() is None
        advance_connection(c,365)
        assert int(c.execute('SELECT COUNT(*) FROM decisions WHERE actor_id=?',(a,)).fetchone()[0])==before
        assert 'deceased_actor_scheduled' not in issue_keys(c)
        assert 'posthumous_decision' not in issue_keys(c)

    # v0.22 travel_routes own physical reachability once a location's route geography is crystallized.
    # The old v0.4 location_links graph remains fallback only and cannot leak a rumour through a closed road.
    reset_db(); init_db()
    with connect() as c:
        c.execute("INSERT INTO locations(name,kind) VALUES ('Route A','town'),('Route B','town')")
        a_id=int(c.execute("SELECT id FROM locations WHERE name='Route A'").fetchone()[0]); b_id=int(c.execute("SELECT id FROM locations WHERE name='Route B'").fetchone()[0])
        # Legacy link says connected, but crystallized physical route is closed.
        c.execute("INSERT INTO location_links(location_a_id,location_b_id,route_kind,travel_days,traffic) VALUES (?,?,'road',1,1)",(a_id,b_id))
        rid=add_route(c,a_id,b_id,route_kind='road',base_days=1,bidirectional=True)
        add_route_condition(c,rid,'closure','washed out',0,end_day=20,accessibility=0)
        cur=c.execute("INSERT INTO events(day,event_type,title,summary,severity,location_id) VALUES (0,'public:test','Route news','A public route test occurred.',3,?)",(a_id,))
        eid=int(cur.lastrowid); register_event_information(c,eid,visibility='public',rumorability=1,reliability=1)
        process_information(c,10)
        assert c.execute('SELECT COUNT(*) FROM rumour_locations WHERE location_id=?',(b_id,)).fetchone()[0]==0
        # Once the condition is over, a new rumour can use the authoritative route.
        cur=c.execute("INSERT INTO events(day,event_type,title,summary,severity,location_id) VALUES (21,'public:test','Route reopened news','A second public route test occurred.',3,?)",(a_id,))
        eid2=int(cur.lastrowid); register_event_information(c,eid2,visibility='public',rumorability=1,reliability=1)
        process_information(c,30)
        assert c.execute('SELECT COUNT(*) FROM rumour_locations WHERE location_id=?',(b_id,)).fetchone()[0]>=1

    # Realistic production seed survives a non-trivial shared-clock run without contradictions
    # and without reverting to the pre-v0.26 ~60-day universal structural cadence flood.
    reset_db(); init_db()
    with connect() as c:
        bootstrap_campaign(c, verification_canon_path=LEGACY_V026_CANON)
        started=time.perf_counter(); advance_connection(c,365); elapsed=time.perf_counter()-started
        assert not contradiction_scan(c)
        decisions=int(c.execute('SELECT COUNT(*) FROM decisions').fetchone()[0])
        assert 0 < decisions < 3000, decisions
        # Broad guardrail rather than a hardware benchmark; this catches accidental O(N*days) regressions.
        assert elapsed < 30, elapsed
        assert c.execute('SELECT COUNT(*) FROM travel_routes').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM religious_observances').fetchone()[0]==0
        c.commit()
    print('v0.26.1 adversarial ownership/cadence/seeded-scale audit PASS')

if __name__=='__main__': run()
