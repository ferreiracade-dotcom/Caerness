from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,connect,init_db,reset_db
from engine.cultivation import process_due_cultivation,cultivation_summary,record_realization_anchor
from engine.health import ensure_health_profile


def _actor(c,name):
    c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')",(name,))
    aid=int(c.execute('SELECT id FROM actors WHERE name=?',(name,)).fetchone()[0])
    c.execute("INSERT INTO actor_life_profiles(actor_id,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) VALUES (?,'adult',0,'living',0,'{}')",(aid,))
    ensure_health_profile(c,aid,longevity_class='first')
    return aid


def run():
    assert ENGINE_VERSION in {'0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.54.0','0.56.0','0.58.0','0.59.0'} and SCHEMA_VERSION>=32
    reset_db(); init_db()
    with connect() as c:
        cols={r[1] for r in c.execute('PRAGMA table_info(cultivation_profiles)').fetchall()}
        assert 'final_stage' not in cols and 'predetermined_ceiling' not in cols
        blocked=_actor(c,'Cultivation Blocked Fixture')
        ready=_actor(c,'Cultivation Ready Fixture')
        c.execute("""INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,
                  training_effort,resource_access,teacher_support,injury_constraint,observed_stage_days,plateau_days,last_review_day,next_review_day,status,metadata_json)
                  VALUES (?,'Open-Core','First',1,40,20,20,80,80,90,100,0,0,30,'active','{}')""",(blocked,))
        c.execute("""INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,
                  training_effort,resource_access,teacher_support,injury_constraint,realization_aptitude,next_realization_check_day,observed_stage_days,plateau_days,last_review_day,next_review_day,status,metadata_json)
                  VALUES (?,'Open-Core','First',1,100,100,90,90,90,0,1.75,30,900,0,0,30,'active','{}')""",(ready,))
        # Time alone cannot promote the unready actor. At First, a genuinely ready Vessel now
        # consolidates through ordinary maturation rather than a rare Realization lottery.
        record_realization_anchor(c,ready,'fixture_crucible',source_kind='test_fixture',weight=10,description='Explicit test opportunity pressure')
        for day in range(30,1501,30):
            c.execute('UPDATE world_state SET current_day=? WHERE id=1',(day,))
            process_due_cultivation(c,day)
            if c.execute('SELECT current_stage FROM cultivation_profiles WHERE actor_id=?',(ready,)).fetchone()[0]=='Temper':
                break
        assert c.execute('SELECT current_stage FROM cultivation_profiles WHERE actor_id=?',(blocked,)).fetchone()[0]=='First'
        assert c.execute('SELECT current_stage FROM cultivation_profiles WHERE actor_id=?',(ready,)).fetchone()[0]=='Temper'
        kinds={r[0] for r in c.execute('SELECT history_kind FROM cultivation_history WHERE actor_id=?',(ready,)).fetchall()}
        assert {'breakthrough_attempt','breakthrough_success'} <= kinds,kinds
        assert 'realization_opportunity' not in kinds,kinds
        assert c.execute('SELECT longevity_class FROM actor_health_profiles WHERE actor_id=?',(ready,)).fetchone()[0]=='temper'
        # No promotion event is represented as merely "one year passed".
        assert not c.execute("SELECT 1 FROM cultivation_history WHERE history_kind='breakthrough_success' AND summary LIKE '%annual%'").fetchone()
        s=cultivation_summary(c)
        assert s['breakthroughs']>=1 and s['profiles']==2
        c.commit()
    print('v0.32.0 causal cultivation/Realization regression PASS')

if __name__=='__main__': run()
