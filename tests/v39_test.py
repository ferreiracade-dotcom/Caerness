from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.health import ensure_health_profile,add_condition
from engine.psych import record_dependency_exposure,begin_dependency_recovery,record_psychological_stressor,record_psychological_support,process_due_psychology
from engine.elixir import create_elixir_batch,consume_elixir
from engine.coverage import snapshot_coverage


def _actor(c,name):
    aid=int(c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')",(name,)).lastrowid)
    c.execute("INSERT INTO actor_life_profiles(actor_id,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) VALUES (?,'adult',0,'living',0,'{}')",(aid,))
    ensure_health_profile(c,aid)
    return aid


def _open_core(c,aid):
    c.execute("""INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,training_effort,resource_access,teacher_support,injury_constraint,core_capacity,current_reserve,sediment_burden,observed_stage_days,plateau_days,last_review_day,next_review_day,status,metadata_json)
                 VALUES (?,'Open-Core','First',1,40,20,50,50,40,0,30,5,0,100,0,0,30,'active','{}')""",(aid,))


def run():
    assert ENGINE_VERSION in {'0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=39
    reset_db(); init_db()
    with connect() as c:
        a=_actor(c,'Dependency Fixture')
        # Ordinary isolated exposure is risk, not automatic addiction.
        record_dependency_exposure(c,a,'chemical_medication',source_kind='pain_relief',amount=1,reinforcing_value=45)
        p=c.execute("SELECT * FROM dependency_profiles WHERE actor_id=? AND dependency_kind='chemical_medication'",(a,)).fetchone()
        assert p['status']=='risk' and int(p['exposure_count'])==1
        # Repeated strongly reinforcing use can become dependence and create practical pressure.
        record_dependency_exposure(c,a,'chemical_medication',source_kind='pain_relief',amount=4,reinforcing_value=80,adverse_consequence=15)
        record_dependency_exposure(c,a,'chemical_medication',source_kind='pain_relief',amount=4,reinforcing_value=80,adverse_consequence=25)
        p=c.execute("SELECT * FROM dependency_profiles WHERE actor_id=? AND dependency_kind='chemical_medication'",(a,)).fetchone()
        assert p['status']=='dependent',dict(p)
        assert c.execute("SELECT 1 FROM pressures WHERE actor_id=? AND kind='dependency:chemical_medication' AND intensity>0",(a,)).fetchone()

        # Recovery exists and is not cultivation magic; sustained quiet/support can resolve state.
        begin_dependency_recovery(c,a,'chemical_medication',support_quality=90)
        for day in (30,60,90,120,150,180):
            c.execute("UPDATE world_state SET current_day=? WHERE id=1",(day,)); process_due_psychology(c,day)
        assert c.execute("SELECT status FROM dependency_profiles WHERE actor_id=? AND dependency_kind='chemical_medication'",(a,)).fetchone()[0] in ('recovering','resolved')

        # Elixir exposure is autonomously classified as performance dependence risk, never chemical addiction.
        e=_actor(c,'Elixir Reliance Fixture'); _open_core(c,e)
        batch=create_elixir_batch(c,'v39-elixir','refined',units=2,usable_current_per_unit=5,refinement_quality=90,sediment_risk=0)
        consume_elixir(c,e,batch,0.5)
        c.execute("UPDATE world_state SET current_day=181 WHERE id=1"); process_due_psychology(c,181)
        ep=c.execute("SELECT * FROM dependency_profiles WHERE actor_id=? AND dependency_kind='elixir_performance'",(e,)).fetchone()
        assert ep and ep['status']=='risk'
        assert not c.execute("SELECT 1 FROM dependency_profiles WHERE actor_id=? AND dependency_kind='chemical_medication'",(e,)).fetchone()

        # One ordinary stressor remains a stressor; a very severe/repeated burden can become persistent impairment.
        t=_actor(c,'Trauma Fixture')
        record_psychological_stressor(c,t,'trauma',burden=35,source_kind='fright',source_ref_kind='test',source_ref_id=1)
        process_due_psychology(c,181)
        assert not c.execute("SELECT 1 FROM psychological_conditions WHERE actor_id=?",(t,)).fetchone()
        record_psychological_stressor(c,t,'trauma',burden=85,source_kind='violence',source_ref_kind='test',source_ref_id=2)
        process_due_psychology(c,181)
        pc=c.execute("SELECT * FROM psychological_conditions WHERE actor_id=? AND condition_family='trauma'",(t,)).fetchone(); assert pc
        assert c.execute("SELECT 1 FROM pressures WHERE actor_id=? AND kind='psychological:trauma' AND intensity>0",(t,)).fetchone()
        record_psychological_support(c,t,condition_id=int(pc['id']),support_kind='family',helpfulness=100)
        c.execute("UPDATE world_state SET current_day=211 WHERE id=1"); process_due_psychology(c,211)
        pc2=c.execute("SELECT * FROM psychological_conditions WHERE id=?",(int(pc['id']),)).fetchone()
        assert float(pc2['severity']) < float(pc['severity'])

        # Severe physical conditions generate a causal stressor, but not automatic persistent trauma.
        s=_actor(c,'Severe Injury Fixture')
        cid=add_condition(c,s,'injury','Severe test injury',severity=80,pain_impact=70,capacity_impact=60,recovery_rate_per_30=4)
        c.execute("UPDATE world_state SET current_day=212 WHERE id=1"); process_due_psychology(c,212)
        assert c.execute("SELECT 1 FROM psychological_stressors WHERE actor_id=? AND source_ref_kind='health_condition' AND source_ref_id=?",(s,cid)).fetchone()
        assert not c.execute("SELECT 1 FROM psychological_conditions WHERE actor_id=? AND condition_family='trauma'",(s,)).fetchone()

        cov={x['domain_key']:x for x in snapshot_coverage(c,None,phase='v39-test')}
        assert cov['26_addiction_psych']['mechanism_status']=='RUNNABLE' and cov['26_addiction_psych']['populated_count']>=1,cov['26_addiction_psych']
        c.commit()
    print('v0.39.0 addiction / psychological consequence regression PASS')

if __name__=='__main__': run()
