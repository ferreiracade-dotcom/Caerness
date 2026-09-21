from __future__ import annotations
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.stress import contradiction_scan

def run():
    path=Path(tempfile.gettempdir())/f'caerness_tenyear02_historical_scan_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit()
    try:
        rows=c.execute("""select a.id,a.name,a.status,lp.life_status from actors a join actor_life_profiles lp on lp.actor_id=a.id
                          where a.status='historical' and lp.life_status='deceased' order by a.id""").fetchall()
        assert len(rows)>=2,rows
        issues=[x for x in contradiction_scan(c,deep_integrity=False) if x['issue_key']=='life_status_mirror']
        assert not issues,issues
        print('TENYEAR02 historical/deceased stress-scan PASS',[(r['name'],r['status'],r['life_status']) for r in rows])
    finally:
        c.close()
        try:path.unlink()
        except FileNotFoundError:pass
if __name__=='__main__':run()
