"""A settlement's nameable people grow from its population on demand, instead of running dry at the first sample."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.background_population import load_partition
from engine.person_ecology import FIRST_FEMALE, FIRST_MALE, resolve_background_person


def run():
    path=Path(tempfile.gettempdir())/f'caerness_reservoir_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect()
    import_current_seed(c); activate_existing_loops(c); c.commit()

    loc=int(c.execute("SELECT id FROM locations WHERE name=?",("Toll’s Reach",)).fetchone()[0])
    src=c.execute("SELECT id,population_estimate FROM background_population_sources WHERE location_id=?",(loc,)).fetchone()
    pid=int(c.execute("SELECT id FROM background_population_partitions WHERE source_id=?",(int(src[0]),)).fetchone()[0])
    before=load_partition(c,pid)[1].sample_size

    # Forty working-age men are wanted in one city of ~110,000: every one is a local.
    # The underworld already drew on this city's sample (gap 4a): keep asking until the sample has to grow.
    got=[]
    while load_partition(c,pid)[1].sample_size==before and len(got)<1000:
        got.append(resolve_background_person(c,reason='test demand',location_id=loc,min_age=24,max_age=58,demographic_sex='male'))
    got+=[resolve_background_person(c,reason='test demand',location_id=loc,min_age=24,max_age=58,demographic_sex='male') for _ in range(40)]
    assert all(got) and len(set(got))==len(got)>=40
    rows=c.execute(f"""SELECT a.current_location_id,lp.demographic_sex,a.name FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
                       WHERE a.id IN ({','.join('?'*len(got))})""",got).fetchall()
    assert all(r[0]==loc and r[1]=='male' and r[2].split()[0] in FIRST_MALE for r in rows), rows[:5]

    # The sample grew in batches drawn from the population, and every identity has a profile.
    row,state=load_partition(c,pid)
    assert before < state.sample_size <= int(src[1]), (before,state.sample_size)
    assert int(row['sample_size'])==state.sample_size
    assert c.execute("SELECT COUNT(*) FROM background_person_profiles WHERE partition_id=?",(pid,)).fetchone()[0]==state.sample_size
    # Drawn blind: the new identities are not all of the demanded kind (both sexes, all ages).
    new=c.execute("SELECT demographic_sex,given_name FROM background_person_profiles WHERE partition_id=? AND local_uid>?",(pid,before)).fetchall()
    assert {r[0] for r in new}=={'female','male'}
    assert all(r[1] in (FIRST_FEMALE if r[0]=='female' else FIRST_MALE) for r in new)

    # A month of life-course stepping still works on the grown sample.
    from engine.background_population import step_partition_month
    step_partition_month(c,pid,day=int(row['next_step_day']))
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    for suffix in ('','-wal','-shm'):
        try: Path(str(path)+suffix).unlink()
        except FileNotFoundError: pass
    print('identity_reservoir_growth_test: ok')


if __name__=='__main__':
    run()
