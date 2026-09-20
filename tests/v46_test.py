from __future__ import annotations
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.cultivation import (
    REQUIREMENTS,_can_seek_breakthrough,record_realization_anchor,process_due_cultivation,_cultivation_context,
)


def _bootstrap(path:str,seed:int):
    os.environ['CAERNESS_DB_PATH']=path
    reset_db(force=True);init_db()
    c=connect();c.execute('UPDATE world_state SET rng_seed=? WHERE id=1',(seed,))
    import_current_seed(c);activate_existing_loops(c)
    return c


def run():
    assert ENGINE_VERSION in {'0.46.0','0.47.0','0.54.0','0.56.0','0.58.0','0.59.0'} and SCHEMA_VERSION>=46
    old_path=os.environ.get('CAERNESS_DB_PATH')
    try:
        c=_bootstrap('/tmp/caerness_v46_core.db',1)
        cols={r[1] for r in c.execute('PRAGMA table_info(cultivation_profiles)').fetchall()}
        assert {'realization_aptitude','vessel_aptitude','observed_stage_days','next_realization_check_day'} <= cols
        assert all('average_stage_days' not in REQUIREMENTS[s] for s in (None,'First','Temper','Third','Breach','Fifth'))
        # Opening people at the same Stage must not all be cloned to one internal depth.
        for stage in ('First','Temper','Third','Breach','Fifth'):
            v=c.execute("SELECT COUNT(DISTINCT ROUND(vessel_adaptation,1)),COUNT(DISTINCT ROUND(realization_integration,1)) FROM cultivation_profiles WHERE current_stage=?",(stage,)).fetchone()
            assert int(v[0])>=8 and int(v[1])>=8,(stage,tuple(v))
        amin,amax=c.execute('SELECT MIN(vessel_aptitude),MAX(vessel_aptitude) FROM cultivation_profiles').fetchone()
        assert float(amin)<0.7 and float(amax)>1.7,(amin,amax)


        # Location/ecology shapes rates, not ceilings. The same First should receive a stronger
        # ordinary cultivation context in rich Hearth infrastructure than in an outer-kingdom
        # settlement, while Silent Peak's stability must not masquerade as rich ordinary current.
        first_actor=int(c.execute("SELECT actor_id FROM cultivation_profiles WHERE current_stage='First' LIMIT 1").fetchone()[0])
        locs={n:int(c.execute('SELECT id FROM locations WHERE name=?',(n,)).fetchone()[0]) for n in ('Bell Hollow','Silent Peak','Northwatch','Cairnholt')}
        contexts={}
        for name,lid in locs.items():
            c.execute('UPDATE actors SET current_location_id=? WHERE id=?',(lid,first_actor))
            contexts[name]=_cultivation_context(c,first_actor,'First')
        assert contexts['Bell Hollow']['hearth_context'] is True
        assert contexts['Northwatch']['hearth_context'] is False
        assert contexts['Bell Hollow']['ecology_quality'] > contexts['Silent Peak']['ecology_quality'] > contexts['Northwatch']['ecology_quality']
        assert contexts['Bell Hollow']['vessel_growth_factor'] > contexts['Cairnholt']['vessel_growth_factor'] > contexts['Northwatch']['vessel_growth_factor']
        # Outer geography is never a hard ceiling: if the person is actually ready, they remain
        # eligible even at Northwatch.
        c.execute('UPDATE actors SET current_location_id=? WHERE id=?',(locs['Northwatch'],first_actor))
        req=REQUIREMENTS['First']
        c.execute("UPDATE cultivation_profiles SET vessel_adaptation=?,realization_integration=?,training_effort=90,injury_constraint=0,observed_stage_days=0 WHERE actor_id=?",
                  (float(req['vessel'])+2,float(req['practice_cap'])+2,first_actor))
        assert _can_seek_breakthrough(c,c.execute('SELECT * FROM cultivation_profiles WHERE actor_id=?',(first_actor,)).fetchone())

        # Time-at-Stage is never an eligibility gate. If the actual body/understanding is ready,
        # even an observed_stage_days=0 practitioner may encounter the next Stage problem.
        chosen=[]
        for stage in ('First','Temper','Third','Breach','Fifth'):
            aid=int(c.execute("SELECT actor_id FROM cultivation_profiles WHERE current_stage=? LIMIT 1",(stage,)).fetchone()[0])
            req=REQUIREMENTS[stage]
            c.execute("""UPDATE cultivation_profiles SET vessel_adaptation=?,realization_integration=?,training_effort=90,
                         injury_constraint=0,observed_stage_days=0,next_realization_check_day=99999,status='active',active=1 WHERE actor_id=?""",
                      (float(req['vessel'])+1.0,float(req['practice_cap'])+1.0,aid))
            row=c.execute('SELECT * FROM cultivation_profiles WHERE actor_id=?',(aid,)).fetchone()
            assert _can_seek_breakthrough(c,row),stage
            chosen.append(aid)

        # At the true Realization wall (Third -> Breach), a real external insight can bypass a
        # distant scheduled check rather than waiting for an arbitrary average duration.
        aid=chosen[2]
        record_realization_anchor(c,aid,'fixture_crisis',source_kind='fixture',weight=5.0,description='Regression external realization trigger',day=30)
        c.execute('UPDATE cultivation_profiles SET last_review_day=0,next_review_day=30,next_realization_check_day=99999 WHERE actor_id=?',(aid,))
        c.execute('UPDATE cultivation_profiles SET next_review_day=99999 WHERE actor_id<>?',(aid,))
        c.execute('UPDATE world_state SET current_day=30 WHERE id=1')
        process_due_cultivation(c,30)
        nxt=int(c.execute('SELECT next_realization_check_day FROM cultivation_profiles WHERE actor_id=?',(aid,)).fetchone()[0])
        assert nxt<99999,nxt
        c.close()

        # Two deterministic decade seeds demonstrate that ~40 is a centre rather than a lock.
        endings=[]
        sixth_events=[]
        for seed in (4,5):
            c=_bootstrap(f'/tmp/caerness_v46_seed_{seed}.db',seed)
            for day in range(30,3651,30):
                c.execute('UPDATE world_state SET current_day=? WHERE id=1',(day,))
                process_due_cultivation(c,day)
            dist={str(r[0] or 'NONE'):int(r[1]) for r in c.execute("SELECT current_stage,COUNT(*) FROM cultivation_profiles WHERE core_state='Open-Core' GROUP BY current_stage")}
            endings.append(dist.get('Sixth',0))
            sixth_events.append(int(c.execute("SELECT COUNT(*) FROM cultivation_history WHERE history_kind='breakthrough_success' AND stage_after='Sixth'").fetchone()[0]))
            assert dist.get('Temper',0)>10 and dist.get('Third',0)>100,dist
            assert 34<=dist.get('Sixth',0)<=46,dist
            assert c.execute("SELECT COUNT(*) FROM cultivation_profiles WHERE plateau_days>=1825 AND current_stage!='Sixth'").fetchone()[0]>20
            c.close()
        if ENGINE_VERSION in {'0.58.0','0.59.0'}:
            # v0.58 deliberately removed census feedback. A quiet two-seed decade is legal: the
            # opening ~40 Sixths are an ecological baseline, not a quota the runtime must refill.
            # Test permeability causally instead by presenting many already-ready Fifths with a
            # genuine Stage-bound summit problem; at least one must be able to attain Sixth.
            c=_bootstrap('/tmp/caerness_v58_summit_probe.db',77)
            fifths=[int(r[0]) for r in c.execute("SELECT actor_id FROM cultivation_profiles WHERE current_stage='Fifth'").fetchall()]
            req=REQUIREMENTS['Fifth']
            for fid in fifths:
                c.execute("""UPDATE cultivation_profiles SET vessel_adaptation=?,realization_integration=?,training_effort=95,
                             resource_access=90,teacher_support=80,injury_constraint=0,next_review_day=30,last_review_day=0,
                             next_realization_check_day=99999,status='active',active=1 WHERE actor_id=?""",
                          (float(req['vessel'])+2,float(req['practice_cap'])+2,fid))
                record_realization_anchor(c,fid,'fixture_summit_problem',source_kind='fixture',weight=5.0,
                                          description='Regression summit problem',day=30)
            c.execute('UPDATE world_state SET current_day=30 WHERE id=1')
            process_due_cultivation(c,30)
            successes=int(c.execute("SELECT COUNT(*) FROM cultivation_history WHERE history_kind='breakthrough_success' AND stage_after='Sixth'").fetchone()[0])
            assert successes>=1,successes
            meta=[r[0] for r in c.execute("SELECT metadata_json FROM cultivation_history WHERE history_kind='breakthrough_success' AND stage_after='Sixth'").fetchall()]
            assert all('\"population_counts_are_runtime_quota\": false' in m for m in meta),meta
            c.close()
        else:
            assert len(set(endings))>1,(endings,sixth_events)
            assert max(sixth_events)>=1,(endings,sixth_events)
    finally:
        if old_path is None: os.environ.pop('CAERNESS_DB_PATH',None)
        else: os.environ['CAERNESS_DB_PATH']=old_path
    print('v0.46.0 probabilistic stage timing / summit variability regression PASS')

if __name__=='__main__': run()
