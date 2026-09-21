from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.cultivation import process_due_cultivation


def run():
    assert ENGINE_VERSION in {'0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.54.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=42
    reset_db(); init_db()
    with connect() as c:
        cols={r[1] for r in c.execute('PRAGMA table_info(cultivation_profiles)').fetchall()}
        assert {'realization_aptitude','next_realization_check_day'} <= cols
        assert 'final_stage' not in cols and 'predetermined_ceiling' not in cols
        import_current_seed(c)
        activate_existing_loops(c)
        opening={str(r[0] or 'NONE'):int(r[1]) for r in c.execute("SELECT current_stage,COUNT(*) FROM cultivation_profiles WHERE core_state='Open-Core' GROUP BY current_stage")}
        assert opening.get('Sixth')==40,opening
        assert opening.get('First',0)>0 and opening.get('Temper',0)>0
        # Long-run cultivation-only calibration: early Vessel maturation should move serious named
        # practitioners upward, while Temper remains populated and the mastery wall preserves plateau.
        total_opp=total_break=0
        for day in range(30,3651,30):
            c.execute('UPDATE world_state SET current_day=? WHERE id=1',(day,))
            out=process_due_cultivation(c,day)
            total_opp+=out['realization_opportunities']; total_break+=out['breakthroughs']
        ending={str(r[0] or 'NONE'):int(r[1]) for r in c.execute("SELECT current_stage,COUNT(*) FROM cultivation_profiles WHERE core_state='Open-Core' GROUP BY current_stage")}
        assert ending.get('Temper',0)>=20,ending
        assert ending.get('Third',0)>=100,ending
        assert 34<=ending.get('Sixth',0)<=46,(opening,ending)
        opening_open_core=sum(opening.values())
        assert total_break/opening_open_core < 0.60,(total_break,opening_open_core)
        # ~40 is a demographic centre, not a hard lock. This seed may stay near it.
        # Some people genuinely progress and some genuinely plateau.
        assert total_opp>0 and total_break>0
        assert c.execute("SELECT COUNT(*) FROM cultivation_history WHERE history_kind='breakthrough_failure'").fetchone()[0]>0
        # Aptitude varies across people but is not a hidden final Stage.
        amin,amax=c.execute('SELECT MIN(realization_aptitude),MAX(realization_aptitude) FROM cultivation_profiles').fetchone()
        assert float(amin)<0.8 and float(amax)>1.2,(amin,amax)
        c.commit()
    print('v0.42.0 long-run cultivation demography regression PASS')

if __name__=='__main__': run()
