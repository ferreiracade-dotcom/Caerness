from __future__ import annotations
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.cultivation import (
    _opening_depth_calibration,_record_stage_attainment,REQUIREMENTS,record_realization_anchor,process_due_cultivation
)


def run():
    assert ENGINE_VERSION in {'0.54.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=48
    old=os.environ.get('CAERNESS_DB_PATH'); os.environ['CAERNESS_DB_PATH']='/tmp/caerness_v054_attainment.db'
    try:
        reset_db(force=True);init_db();c=connect();import_current_seed(c);activate_existing_loops(c)
        # Cross-sectional current age/current Stage must never be silently converted into attainment age.
        known=c.execute("SELECT COUNT(*) FROM cultivation_stage_attainments WHERE chronology_certainty='known'").fetchone()[0]
        assert int(known)==0,known
        assert c.execute("SELECT COUNT(*) FROM cultivation_stage_attainments WHERE attained_age_days IS NOT NULL").fetchone()[0]==0

        # Current age alone cannot change the opening within-Stage calibration.
        aid=int(c.execute("SELECT actor_id FROM cultivation_profiles WHERE current_stage='First' LIMIT 1").fetchone()[0])
        va=float(c.execute("SELECT vessel_aptitude FROM cultivation_profiles WHERE actor_id=?",(aid,)).fetchone()[0])
        ra=float(c.execute("SELECT realization_aptitude FROM cultivation_profiles WHERE actor_id=?",(aid,)).fetchone()[0])
        young=_opening_depth_calibration(c,aid,'First',18,va,ra)
        old_age=_opening_depth_calibration(c,aid,'First',68,va,ra)
        assert young==old_age,(young,old_age)

        # A real historical attainment records exact chronology when birth date is known.
        c.execute("INSERT OR REPLACE INTO actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) VALUES (?,?,?,?,?,?,?)",
                  (aid,-20*365,'adult',0,'living',0,'{}'))
        _record_stage_attainment(c,aid,'Temper',day=365,provenance='runtime_breakthrough',chronology_certainty='known',metadata={'fixture':True})
        row=c.execute("SELECT attained_day,attained_age_days,chronology_certainty,provenance FROM cultivation_stage_attainments WHERE actor_id=? AND stage='Temper'",(aid,)).fetchone()
        assert int(row['attained_day'])==365
        assert int(row['attained_age_days'])==21*365
        assert row['chronology_certainty']=='known' and row['provenance']=='runtime_breakthrough'

        # Having an older birth date must not create a catch-up advancement rule: readiness is still causal state.
        req=REQUIREMENTS['First']
        c.execute("UPDATE cultivation_profiles SET vessel_adaptation=?,realization_integration=?,observed_stage_days=0 WHERE actor_id=?",
                  (float(req['vessel'])-15,float(req['practice_cap'])-10,aid))
        before=c.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?",(aid,)).fetchone()[0]
        c.execute("UPDATE actor_life_profiles SET birth_day=? WHERE actor_id=?",(-70*365,aid))
        c.execute("UPDATE world_state SET current_day=30 WHERE id=1")
        c.execute("UPDATE cultivation_profiles SET next_review_day=30,next_realization_check_day=30 WHERE actor_id=?",(aid,))
        c.execute("UPDATE cultivation_profiles SET next_review_day=999999 WHERE actor_id<>?",(aid,))
        process_due_cultivation(c,30)
        after=c.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?",(aid,)).fetchone()[0]
        assert before==after=='First',(before,after)
        c.close()
    finally:
        if old is None: os.environ.pop('CAERNESS_DB_PATH',None)
        else: os.environ['CAERNESS_DB_PATH']=old
    print('v0.54 inverse age-stage / attainment chronology regression PASS')

if __name__=='__main__': run()
