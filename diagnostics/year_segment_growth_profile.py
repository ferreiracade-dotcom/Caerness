from __future__ import annotations
import json, os, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.simulation import advance_connection
from tests.arch01_process_registry_test import build_registry,advance_via_registry

def bootstrap(kind):
    p=Path(tempfile.gettempdir())/f'caerness_yearseg_{kind}.db'
    os.environ['CAERNESS_DB_PATH']=str(p); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c

def count(c,t):
    try:return int(c.execute(f'select count(*) from {t}').fetchone()[0])
    except:return -1

def run(kind):
    c=bootstrap(kind); reg=build_registry() if kind in ('registry','registry_eager') else None; out=[]; remaining=365
    if kind=='registry_eager': reg._eager_requery=True
    while remaining:
        step=min(30,remaining); before=int(c.execute('select current_day from world_state where id=1').fetchone()[0]); t=time.perf_counter()
        if kind in ('registry','registry_eager'): advance_via_registry(c,step,reg)
        else: advance_connection(c,step)
        elapsed=time.perf_counter()-t; c.commit(); day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        row={'kind':kind,'from_day':before,'day':day,'elapsed_s':round(elapsed,6),'events':count(c,'events'),'rumours':count(c,'rumours'),'transmissions':count(c,'rumour_transmissions'),'exposures':count(c,'rumour_exposures'),'knowledge':count(c,'knowledge'),'beliefs':count(c,'actor_beliefs'),'information_links':count(c,'information_links'),'enterprise_accounts':count(c,'enterprise_accounts'),'process_logs':count(c,'process_execution_log'),'trade_periods':int(c.execute('select count(distinct period_day) from aggregate_trade_balances').fetchone()[0]),'population':round(float(c.execute('select coalesce(sum(population_estimate),0) from background_population_sources').fetchone()[0]),3)}
        out.append(row); print(json.dumps(row),flush=True); remaining-=step
    dest=ROOT/'diagnostics'/f'year_segment_growth_{kind}.json'; dest.write_text(json.dumps(out,indent=2),encoding='utf-8'); print(dest,flush=True); c.close()
if __name__=='__main__': run(sys.argv[1] if len(sys.argv)>1 else 'registry')
