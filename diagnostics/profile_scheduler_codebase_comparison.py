from __future__ import annotations
import cProfile, io, json, os, pstats, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.simulation import advance_connection
from tests.arch01_process_registry_test import build_registry, advance_via_registry


def bootstrap(name:str):
    path=Path(tempfile.gettempdir())/name
    os.environ['CAERNESS_DB_PATH']=str(path)
    os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db()
    c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def profile_run(kind:str, days:int):
    c=bootstrap(f'caerness_profile_{kind}_{days}.db')
    pr=cProfile.Profile(); t=time.perf_counter(); pr.enable()
    if kind=='baseline':
        advance_connection(c,days)
    elif kind=='registry':
        advance_via_registry(c,days,build_registry())
    else: raise ValueError(kind)
    pr.disable(); elapsed=time.perf_counter()-t
    c.commit()
    summary={
      'kind':kind,'days':days,'elapsed_s':elapsed,
      'day':c.execute('select current_day from world_state where id=1').fetchone()[0],
      'events':c.execute('select count(*) from events').fetchone()[0],
      'decisions':c.execute('select count(*) from decisions').fetchone()[0],
      'process_logs':c.execute('select count(*) from process_execution_log').fetchone()[0],
      'population':c.execute('select coalesce(sum(population_estimate),0) from background_population_sources').fetchone()[0],
      'trade_periods':c.execute('select count(distinct period_day) from aggregate_trade_balances').fetchone()[0],
    }
    s=io.StringIO(); pstats.Stats(pr,stream=s).strip_dirs().sort_stats('cumulative').print_stats(60)
    summary['profile_text']=s.getvalue()
    c.close(); return summary

if __name__=='__main__':
    days=int(sys.argv[1]) if len(sys.argv)>1 else 90
    out=[]
    for kind in ('baseline','registry'):
        r=profile_run(kind,days); out.append(r)
        print(json.dumps({k:v for k,v in r.items() if k!='profile_text'},indent=2))
        print(r['profile_text'])
    dest=ROOT/'diagnostics'/f'scheduler_profile_{days}d.json'
    dest.write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(dest)
