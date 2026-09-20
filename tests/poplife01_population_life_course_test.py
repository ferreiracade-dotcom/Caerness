from __future__ import annotations

import os
os.environ.setdefault('CAERNESS_TEST_MODE','1')
os.environ['CAERNESS_DB_PATH']='/tmp/caerness_poplife01_acceptance.db'

from engine.db import SCHEMA_VERSION, reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.background_population import (
    current_world_population, current_bucket_population,
    process_due_population_life_course, transfer_population,
)
from engine.aggregate_trade import process_due_aggregate_trade


def close(a,b,tol=1e-6):
    return abs(float(a)-float(b)) <= tol*max(1.0,abs(float(a)),abs(float(b)))


def run():
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activated=activate_existing_loops(c); c.commit()
    try:
        assert SCHEMA_VERSION>=74
        assert activated['background_population_sources']==68
        assert activated['population_age_cohorts']==408
        assert activated['population_dynamics_sources']==68
        assert current_world_population(c)==52_000_000
        assert c.execute('select count(*) from background_population_age_cohorts').fetchone()[0]==408
        assert c.execute('select count(*) from background_population_dynamics').fetchone()[0]==68
        for s in c.execute('select id,population_estimate,baseline_population_estimate from background_population_sources'):
            cohorts=float(c.execute('select sum(population) from background_population_age_cohorts where source_id=?',(s['id'],)).fetchone()[0])
            assert close(cohorts,s['population_estimate'])
            assert int(s['baseline_population_estimate'])>=0

        # One full year: live population diverges causally from the opening 52m anchor.
        c.execute('update world_state set current_day=365 where id=1')
        out=process_due_population_life_course(c,365); c.commit()
        assert out['sources_reviewed']==68 and out['source_year_periods']==68
        assert close(out['births'],52_000_000*.016)
        assert out['deaths']>0
        live_after=current_world_population(c)
        assert live_after!=52_000_000
        balances=c.execute('select * from background_population_yearly_balances where period_day=365').fetchall()
        assert len(balances)==68
        for b in balances:
            assert close(b['opening_population']+b['births']-b['deaths']+b['movement_net'],b['closing_population'])
        aggregate_close=sum(float(b['closing_population']) for b in balances)
        age_close=float(c.execute('select sum(population) from background_population_age_cohorts').fetchone()[0])
        assert close(aggregate_close,age_close)

        # Explicit movement conserves world population and age structure; it is not a hidden random migration roll.
        origin=c.execute("""select s.id from background_population_sources s join locations l on l.id=s.location_id
                            where l.name='Aldergate'""").fetchone()[0]
        dest=c.execute("select id from background_population_sources where source_key='rural:underheaven'").fetchone()[0]
        before_world=float(c.execute('select sum(population) from background_population_age_cohorts').fetchone()[0])
        before_o=float(c.execute('select sum(population) from background_population_age_cohorts where source_id=?',(origin,)).fetchone()[0])
        before_d=float(c.execute('select sum(population) from background_population_age_cohorts where source_id=?',(dest,)).fetchone()[0])
        movement_id=transfer_population(c,int(origin),int(dest),10_000,reason='POPLIFE acceptance displacement test',day=365)
        c.commit()
        after_world=float(c.execute('select sum(population) from background_population_age_cohorts').fetchone()[0])
        after_o=float(c.execute('select sum(population) from background_population_age_cohorts where source_id=?',(origin,)).fetchone()[0])
        after_d=float(c.execute('select sum(population) from background_population_age_cohorts where source_id=?',(dest,)).fetchone()[0])
        assert close(before_world,after_world)
        assert close(before_o-after_o,10_000)
        assert close(after_d-before_d,10_000)
        assert c.execute('select count(*) from background_population_movements where id=?',(movement_id,)).fetchone()[0]==1

        # Re-running activation must not reset a year of demographic history to SCALE-01 opening values.
        current_before_reactivation=float(c.execute('select sum(population_estimate) from background_population_sources').fetchone()[0])
        activate_existing_loops(c); c.commit()
        current_after_reactivation=float(c.execute('select sum(population_estimate) from background_population_sources').fetchone()[0])
        assert close(current_before_reactivation,current_after_reactivation)
        baseline=float(c.execute('select sum(baseline_population_estimate) from background_population_sources').fetchone()[0])
        assert close(baseline,52_000_000)

        # TRADE-01 now consumes the live regional population, not the frozen opening anchor.
        under_live=current_bucket_population(c,'underheaven')
        profile=c.execute("""select p.good_id,p.monthly_consumption_per_capita from aggregate_trade_profiles p
                             where p.bucket_key='underheaven' order by p.good_id limit 1""").fetchone()
        c.execute("insert or replace into engine_meta(key,value) values ('aggregate_trade_next_cycle_day','365')")
        process_due_aggregate_trade(c,365); c.commit()
        bal=c.execute('select consumption_requirement from aggregate_trade_balances where period_day=365 and bucket_key=\'underheaven\' and good_id=?',(profile['good_id'],)).fetchone()
        assert bal is not None
        assert close(bal['consumption_requirement'],under_live*float(profile['monthly_consumption_per_capita']))

        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('POPLIFE-01 acceptance PASS', {
            'opening_population':52_000_000,
            'year1_births':round(float(out['births']),3),
            'year1_deaths':round(float(out['deaths']),3),
            'year1_live_population':live_after,
            'movement_conserved':10_000,
            'underheaven_live_population':under_live,
            'trade_uses_live_population':True,
        })
    finally:
        c.close()

if __name__=='__main__': run()
