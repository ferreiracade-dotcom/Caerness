from __future__ import annotations
import os, sys, json, subprocess, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, SCHEMA_VERSION, DEFAULT_DB_PATH, connect, database_path, init_db, migration_status, reset_db
from engine.bootstrap import bootstrap_campaign, bootstrap_status, create_player_character

LEGACY_V026_CANON = ROOT / 'tests' / 'fixtures' / 'v026_world_bible_current.docx'

from engine.stress import contradiction_scan


def run():
    # The regression harness must be isolated from the packaged/live campaign path.
    assert ENGINE_VERSION in {'0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
    assert SCHEMA_VERSION >= 26
    assert database_path() != DEFAULT_DB_PATH
    reset_db(); init_db()
    with connect() as c:
        ms=migration_status(c)
        assert ms['schema_version']==SCHEMA_VERSION
        assert len(ms['applied'])>=26
        first=bootstrap_campaign(c, verification_canon_path=LEGACY_V026_CANON)
        assert first['locations']==48
        assert first['institutions']==36
        assert first['named_characters']==388
        assert first['demographic_cohorts']==6
        assert first['latent_stage_pools']==6
        assert first['player_created'] is False
        second=bootstrap_campaign(c, verification_canon_path=LEGACY_V026_CANON)
        assert second['idempotent'] is True
        st=bootstrap_status(c)
        assert st['counts']['locations']==48
        assert st['counts']['institutions']==36
        assert st['counts']['named_characters']==388
        assert round(st['counts']['aggregate_population'])==3_500_000
        # Open World-Bible boundaries are not silently crystallized by production setup.
        assert c.execute('SELECT COUNT(*) FROM travel_routes').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM religious_observances').fetchone()[0]==0
        assert c.execute('SELECT player_actor_id FROM player_state WHERE id=1').fetchone() is None
        assert c.execute("SELECT COUNT(*) FROM campaign_seed_entities").fetchone()[0] >= 48+36+388+6+6
        aid=create_player_character(c,'v26 Player',start_location='Cairnholt',age=27,campaign_name='v26 audit')
        assert aid>0
        ps=c.execute('SELECT player_actor_id,current_location_id FROM player_state WHERE id=1').fetchone()
        assert int(ps['player_actor_id'])==aid
        assert ps['current_location_id']==c.execute('SELECT current_location_id FROM actors WHERE id=?',(aid,)).fetchone()[0]
        assert not contradiction_scan(c)
        c.commit()

    # A non-test process cannot destructively reset a campaign without explicit --force.
    guard_db=Path(tempfile.gettempdir())/'caerness_v26_reset_guard.db'
    for suffix in ('','-wal','-shm'):
        Path(str(guard_db)+suffix).unlink(missing_ok=True)
    env=os.environ.copy(); env.pop('CAERNESS_TEST_MODE',None); env['CAERNESS_DB_PATH']=str(guard_db)
    subprocess.run([sys.executable,str(ROOT/'run.py'),'init'],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
    denied=subprocess.run([sys.executable,str(ROOT/'run.py'),'reset'],cwd=ROOT,env=env,capture_output=True,text=True)
    assert denied.returncode!=0
    assert guard_db.exists()
    allowed=subprocess.run([sys.executable,str(ROOT/'run.py'),'reset','--force','--no-backup'],cwd=ROOT,env=env,capture_output=True,text=True)
    assert allowed.returncode==0, allowed.stderr
    assert not guard_db.exists()
    print('v0.26.1 integration/bootstrap/save-safety regression PASS')

if __name__=='__main__': run()
