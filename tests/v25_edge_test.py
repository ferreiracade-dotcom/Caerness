from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION,connect,init_db,reset_db
from engine.player import set_player,designate_camera_successor,process_camera_succession,revoke_camera_successor
from engine.household_life import mark_actor_deceased
from engine.stress import contradiction_scan,run_horizon
from engine.continuity import create_latent_entity
from engine.crystallization import prepare_crystallization_context,validate_crystallization_proposal,apply_crystallization_proposal


def actor(c,n,status='active'):
    c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character',?)",(n,status)); return int(c.execute('SELECT id FROM actors WHERE name=?',(n,)).fetchone()[0])
def fail(fn):
    try: fn()
    except Exception: return
    raise AssertionError('expected failure')


def run():
    reset_db(); init_db(); assert ENGINE_VERSION in {'0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
    with connect() as c:
        a=actor(c,'Camera A'); b=actor(c,'Camera B'); d=actor(c,'Dead Camera Candidate','deceased')
        set_player(c,a,'Camera Audit')
        fail(lambda: designate_camera_successor(c,a,a))
        fail(lambda: designate_camera_successor(c,a,d))
        did=designate_camera_successor(c,a,b,priority=100)
        mark_actor_deceased(c,b,reason='pre-handoff test')
        mark_actor_deceased(c,a,reason='camera audit')
        # Dead designated candidate is marked unavailable; no arbitrary stranger is invented.
        assert process_camera_succession(c) is None
        assert c.execute('SELECT status FROM player_camera_successors WHERE id=?',(did,)).fetchone()[0]=='unavailable'
        stranger=actor(c,'Camera Stranger')
        assert int(c.execute('SELECT player_actor_id FROM player_state WHERE id=1').fetchone()[0])==a
        fail(lambda: designate_camera_successor(c,a,a))
        # Explicit new designation works even after death of previous focus.
        designate_camera_successor(c,a,stranger,priority=200)
        assert process_camera_succession(c)==stranger
        assert not contradiction_scan(c)

        # Crystallization consistency: applied campaign history remains traceable after decades.
        c.execute("INSERT INTO locations(name,kind) VALUES ('Crystal Town','town')"); loc=int(c.execute("SELECT id FROM locations WHERE name='Crystal Town'").fetchone()[0])
        latent=create_latent_entity(c,'person','archivist',location_id=loc,count_estimate=1,constraints={'age_range':[25,45]})
        ctx=prepare_crystallization_context(c,latent,requested_depth='shallow')
        run_id=ctx['run_id']; birth=ctx['birth_window']['latest_day']-365
        proposal={'name':'Crystal Person','actor_type':'character','subtype':'archivist','birth_day':birth,'home_location_id':loc,'current_location_id':loc,
                  'continuity':{'identity':{}},'anchors':[],'career':None,'connections':[],'resolution_level':'TRACKED'}
        val=validate_crystallization_proposal(c,run_id,proposal); assert val['valid']
        aid=apply_crystallization_proposal(c,run_id); assert aid
        assert not contradiction_scan(c)
        out=run_horizon(c,25,label='crystallization continuity audit',scenario_kind='crystallization_consistency',checkpoint_years=5)
        assert out['contradictions']==0
        assert c.execute("SELECT status FROM crystallization_runs WHERE id=?",(run_id,)).fetchone()[0]=='applied'
        assert c.execute("SELECT COUNT(*) FROM crystallization_lineage WHERE run_id=?",(run_id,)).fetchone()[0]>=2
        c.commit()
    print('v0.25 adversarial long-run/camera/crystallization audit PASS')
if __name__=='__main__': run()
