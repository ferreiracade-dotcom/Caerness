from __future__ import annotations

import importlib.util
import json
import sqlite3
import time
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

SIZES=(10_000,100_000,1_000_000)
STEPS=12
SEED=812197

@dataclass
class Result:
    backend:str; people:int; init_seconds:float; step_seconds:float; bytes_estimate:int
    alive:int; migration_eligible:int; occupation_changes:int; core_assessments:int


def seed_arrays(n:int):
    rng=np.random.default_rng(SEED+n)
    return {
        'age_days':rng.integers(0,80*365,size=n,dtype=np.int32),
        'alive':np.ones(n,dtype=np.bool_),
        'region':rng.integers(0,8,size=n,dtype=np.uint8),
        'occupation':rng.integers(0,24,size=n,dtype=np.uint8),
        'household':rng.integers(0,max(1,n//4),size=n,dtype=np.int32),
        'core_assessed':(rng.random(n)<.12),
        'mobility_pressure':rng.random(n).astype(np.float32),
        'transition_draw':rng.random((STEPS,n),dtype=np.float32),
        'mortality_draw':rng.random((STEPS,n),dtype=np.float32),
    }


def mortality_probability(age_days):
    age=age_days/365.0
    return np.where(age<1,.018,np.where(age<15,.0004,np.where(age<50,.0018,np.where(age<65,.009,np.where(age<75,.03,.085)))))/12.0


def run_numpy(n:int)->Result:
    t=time.perf_counter(); d=seed_arrays(n); init=time.perf_counter()-t
    changes=assess=0; mig=0
    t=time.perf_counter()
    for step in range(STEPS):
        d['age_days'][d['alive']]+=30
        p=mortality_probability(d['age_days'])
        deaths=d['alive'] & (d['mortality_draw'][step] < p)
        d['alive'][deaths]=False
        adult=d['age_days']>=18*365
        migration=d['alive'] & adult & (d['mobility_pressure']>.82)
        mig=int(migration.sum())
        occ_change=migration & (d['transition_draw'][step] < .08)
        d['occupation'][occ_change]=(d['occupation'][occ_change]+1)%24
        changes += int(occ_change.sum())
        newly_assess=d['alive'] & adult & ~d['core_assessed'] & (d['transition_draw'][step] < .002)
        d['core_assessed'][newly_assess]=True; assess += int(newly_assess.sum())
    elapsed=time.perf_counter()-t
    mem=sum(v.nbytes for v in d.values())
    return Result('numpy',n,init,elapsed,mem,int(d['alive'].sum()),mig,changes,assess)


def run_pandas(n:int)->Result:
    t=time.perf_counter(); d=seed_arrays(n)
    draws_m=d.pop('mortality_draw'); draws_t=d.pop('transition_draw')
    df=pd.DataFrame(d); init=time.perf_counter()-t
    changes=assess=0; mig=0
    t=time.perf_counter()
    for step in range(STEPS):
        alive=df['alive'].to_numpy(copy=False)
        ages=df['age_days'].to_numpy(copy=False); ages[alive]+=30
        p=mortality_probability(ages)
        deaths=alive & (draws_m[step]<p); alive[deaths]=False
        adult=ages>=18*365
        migration=alive & adult & (df['mobility_pressure'].to_numpy(copy=False)>.82); mig=int(migration.sum())
        occ_change=migration & (draws_t[step]<.08)
        occ=df['occupation'].to_numpy(copy=False); occ[occ_change]=(occ[occ_change]+1)%24; changes+=int(occ_change.sum())
        core=df['core_assessed'].to_numpy(copy=False)
        new=alive & adult & ~core & (draws_t[step]<.002); core[new]=True; assess+=int(new.sum())
    elapsed=time.perf_counter()-t
    mem=int(df.memory_usage(index=True,deep=True).sum()+draws_m.nbytes+draws_t.nbytes)
    return Result('pandas',n,init,elapsed,mem,int(df['alive'].sum()),mig,changes,assess)


def run_sqlite(n:int)->Result:
    rng=np.random.default_rng(SEED+n)
    age=rng.integers(0,80*365,size=n,dtype=np.int32)
    region=rng.integers(0,8,size=n,dtype=np.uint8)
    occupation=rng.integers(0,24,size=n,dtype=np.uint8)
    household=rng.integers(0,max(1,n//4),size=n,dtype=np.int32)
    core=(rng.random(n)<.12).astype(np.uint8)
    mobility=rng.random(n).astype(np.float32)
    conn=sqlite3.connect(':memory:'); conn.execute('pragma journal_mode=off'); conn.execute('pragma synchronous=off')
    conn.execute('create table people(id integer primary key,age_days integer,alive integer,region integer,occupation integer,household integer,core_assessed integer,mobility real)')
    t=time.perf_counter()
    conn.executemany('insert into people values (?,?,?,?,?,?,?,?)',((i+1,int(age[i]),1,int(region[i]),int(occupation[i]),int(household[i]),int(core[i]),float(mobility[i])) for i in range(n)))
    conn.commit(); init=time.perf_counter()-t
    changes=assess=0; mig=0
    # SQLite control intentionally uses deterministic hash-like modular predicates rather than
    # Python per-row RNG, so the benchmark measures set-based state updates rather than random generation.
    t=time.perf_counter()
    for step in range(STEPS):
        conn.execute('update people set age_days=age_days+30 where alive=1')
        # age-banded monthly mortality approximation, deterministically sampled by id/step
        conn.execute('''update people set alive=0 where alive=1 and
          ((age_days<365 and ((id*1103515245+?*12345)&2147483647)%1000000 < 1500)
           or (age_days>=27375 and ((id*1664525+?*1013904223)&2147483647)%1000000 < 7000))''',(step,step))
        mig=int(conn.execute('select count(*) from people where alive=1 and age_days>=6570 and mobility>.82').fetchone()[0])
        before=conn.total_changes
        conn.execute('''update people set occupation=(occupation+1)%24 where alive=1 and age_days>=6570 and mobility>.82
                        and ((id*22695477+?*1)&2147483647)%10000 < 800''',(step,))
        changes += conn.total_changes-before
        before=conn.total_changes
        conn.execute('''update people set core_assessed=1 where alive=1 and age_days>=6570 and core_assessed=0
                        and ((id*214013+?*2531011)&2147483647)%100000 < 200''',(step,))
        assess += conn.total_changes-before
    conn.commit(); elapsed=time.perf_counter()-t
    pages=conn.execute('pragma page_count').fetchone()[0]; page_size=conn.execute('pragma page_size').fetchone()[0]
    alive=int(conn.execute('select count(*) from people where alive=1').fetchone()[0]); mem=pages*page_size; conn.close()
    return Result('sqlite_set_based',n,init,elapsed,mem,alive,mig,changes,assess)


def main():
    availability={m:bool(importlib.util.find_spec(m)) for m in ('polars','neworder','starsim')}
    results=[]
    for n in SIZES:
        for fn in (run_numpy,run_pandas,run_sqlite):
            r=fn(n); results.append(asdict(r)); print(json.dumps(asdict(r),sort_keys=True),flush=True)
    print(json.dumps({'optional_backend_availability':availability,'steps':STEPS,'sizes':SIZES},sort_keys=True))

if __name__=='__main__': main()
