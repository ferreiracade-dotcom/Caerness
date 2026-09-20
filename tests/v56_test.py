from __future__ import annotations
import os,sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.cultivation import (
    REQUIREMENTS,process_due_cultivation,_cultivation_context,_external_realization_weight,
    record_realization_anchor,
)


def _bootstrap(path:str,seed:int):
    os.environ['CAERNESS_DB_PATH']=path
    reset_db(force=True); init_db(); c=connect(); c.execute('UPDATE world_state SET rng_seed=? WHERE id=1',(seed,))
    import_current_seed(c); activate_existing_loops(c)
    return c


def run():
    assert SCHEMA_VERSION>=48
    # Bible-facing transition architecture: lower ladder is Vessel maturation; mastery begins at Breach.
    assert REQUIREMENTS[None]['transition_mode']=='vessel_maturation'
    assert REQUIREMENTS['First']['transition_mode']=='vessel_maturation'
    assert REQUIREMENTS['Temper']['transition_mode']=='vessel_maturation'
    for stage in ('Third','Breach','Fifth'):
        assert REQUIREMENTS[stage]['transition_mode']=='realization_wall',stage
    assert REQUIREMENTS['Third']['practice_cap'] < REQUIREMENTS['Third']['realization']

    old=os.environ.get('CAERNESS_DB_PATH')
    try:
        c=_bootstrap('/tmp/caerness_v056_mechanism.db',11)
        # A structurally ready First matures without requiring a rare Realization opportunity roll.
        aid=int(c.execute("SELECT actor_id FROM cultivation_profiles WHERE current_stage='First' LIMIT 1").fetchone()[0])
        req=REQUIREMENTS['First']
        c.execute("""UPDATE cultivation_profiles SET vessel_adaptation=?,realization_integration=?,training_effort=80,
                     injury_constraint=0,next_review_day=30,next_realization_check_day=30 WHERE actor_id=?""",
                  (req['vessel']+2,req['realization']+2,aid))
        c.execute('UPDATE cultivation_profiles SET next_review_day=999999 WHERE actor_id<>?',(aid,))
        c.execute('UPDATE world_state SET current_day=30 WHERE id=1')
        out=process_due_cultivation(c,30)
        assert c.execute('SELECT current_stage FROM cultivation_profiles WHERE actor_id=?',(aid,)).fetchone()[0]=='Temper'
        assert out['breakthroughs']==1
        assert c.execute("SELECT COUNT(*) FROM cultivation_history WHERE actor_id=? AND history_kind='realization_opportunity'",(aid,)).fetchone()[0]==0
        meta=c.execute("SELECT metadata_json FROM cultivation_history WHERE actor_id=? AND history_kind='breakthrough_success' ORDER BY id DESC LIMIT 1",(aid,)).fetchone()[0]
        assert 'vessel_maturation' in meta

        # Whole-Vessel Third development is condition-sensitive, not region-capped.
        temp=int(c.execute("SELECT actor_id FROM cultivation_profiles WHERE current_stage='Temper' LIMIT 1").fetchone()[0])
        bell=int(c.execute("SELECT id FROM locations WHERE name='Bell Hollow'").fetchone()[0])
        north=int(c.execute("SELECT id FROM locations WHERE name='Northwatch'").fetchone()[0])
        c.execute('UPDATE actors SET current_location_id=? WHERE id=?',(bell,temp)); rich=_cultivation_context(c,temp,'Temper')
        c.execute('UPDATE actors SET current_location_id=? WHERE id=?',(north,temp)); outer=_cultivation_context(c,temp,'Temper')
        assert rich['whole_vessel_current_factor'] > outer['whole_vessel_current_factor']
        assert rich['vessel_growth_factor'] > outer['vessel_growth_factor']
        assert outer['vessel_growth_factor']>0.0  # never a Stage cap

        # Stage-bound insights cannot be banked through later Stages.
        first2=int(c.execute("SELECT actor_id FROM cultivation_profiles WHERE current_stage='First' AND actor_id<>? LIMIT 1",(aid,)).fetchone()[0])
        record_realization_anchor(c,first2,'fixture_insight',source_kind='fixture',weight=4.0,day=30)
        assert _external_realization_weight(c,first2)>=4.0
        c.execute("UPDATE cultivation_profiles SET current_stage='Temper' WHERE actor_id=?",(first2,))
        assert _external_realization_weight(c,first2)==0.0
        c.close()

        # Population calibration: same universal mechanics, different ordinary outcomes from context.
        c=_bootstrap('/tmp/caerness_v056_cohort.db',3)
        opening={}
        for r in c.execute("SELECT actor_id,current_stage FROM cultivation_profiles WHERE core_state='Open-Core' AND current_stage IN ('First','Temper','Third')"):
            aid0=int(r['actor_id']); st=r['current_stage']
            opening[aid0]=(st,bool(_cultivation_context(c,aid0,st)['hearth_context']))
        for day in range(30,3651,30):
            c.execute('UPDATE world_state SET current_day=? WHERE id=1',(day,)); process_due_cultivation(c,day)
        def finals(stage,hearth):
            ids=[a for a,(s,h) in opening.items() if s==stage and h==hearth]
            return ids,collections.Counter(c.execute('SELECT current_stage FROM cultivation_profiles WHERE actor_id=?',(a,)).fetchone()[0] for a in ids)
        h1,h1f=finals('First',True); o1,o1f=finals('First',False)
        ht,htf=finals('Temper',True); ot,otf=finals('Temper',False)
        h3,h3f=finals('Third',True); o3,o3f=finals('Third',False)
        assert len(h1)>20 and len(o1)>10 and len(ht)>20 and len(ot)>10
        # Churn Firsts usually move toward the mature-professional Third ecology over a decade.
        assert h1f['Third']/len(h1) >= 0.60,(h1f,len(h1))
        # Outer Firsts most commonly mature to Temper rather than matching Churn Third density.
        assert o1f['Temper']/len(o1) >= 0.50,(o1f,len(o1))
        assert o1f['Third']/len(o1) <= 0.40,(o1f,len(o1))
        # Existing Churn Tempers usually complete whole-Vessel Third development under these named-practitioner conditions.
        assert htf['Third']/len(ht) >= 0.70,(htf,len(ht))
        # Outer Temper remains a durable mature-professional state for a meaningful minority.
        assert otf['Temper']/len(ot) >= 0.20,(otf,len(ot))
        # Breach is the selective wall, not the routine next stop.
        assert h3f['Breach']/len(h3) <= 0.15,(h3f,len(h3))
        assert o3f['Breach']/len(o3) <= 0.15,(o3f,len(o3))
        c.close()
    finally:
        if old is None: os.environ.pop('CAERNESS_DB_PATH',None)
        else: os.environ['CAERNESS_DB_PATH']=old
    print('v0.56 Vessel-led lower ladder / Realization-wall mastery regression PASS')

if __name__=='__main__': run()
