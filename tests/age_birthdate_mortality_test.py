from __future__ import annotations
import os, tempfile
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
os.environ['CAERNESS_TEST_MODE']='1'
os.environ['CAERNESS_DB_PATH']=str(Path(tempfile.gettempdir())/'caerness_age_birthdate_mortality_test.db')

from engine.db import reset_db, init_db, connect
from engine.household_life import set_life_profile
from engine.health import configure_health_profile
from engine.simulation import advance_connection


def run():
    reset_db(force=True, backup=False); init_db()
    with connect() as c:
        c.execute("INSERT INTO locations(name,kind) VALUES ('Mortality Audit Hamlet','village')")
        loc=int(c.execute("SELECT id FROM locations WHERE name='Mortality Audit Hamlet'").fetchone()[0])
        c.execute("INSERT INTO actors(name,actor_type,status,current_location_id,home_location_id) VALUES ('Mortality Audit Elder','character','active',?,?)",(loc,loc))
        aid=int(c.execute("SELECT id FROM actors WHERE name='Mortality Audit Elder'").fetchone()[0])
        # Disposable manufactured trigger: an ordinary 105-year-old, deliberately older than the
        # ordinary longevity midpoint, used only to prove the production mortality path wakes.
        set_life_profile(c,aid,birth_day=-(105*365),family_formation_eligible=False)
        configure_health_profile(c,aid,longevity_class='ordinary',baseline_health=75)
        c.commit()
        start=c.execute("SELECT mortality_pressure,aging_phase,longevity_class FROM actor_health_profiles WHERE actor_id=?",(aid,)).fetchone()
        assert start['longevity_class']=='ordinary'
        assert start['aging_phase']=='late_decline'

        # Let the production scheduler perform the first physiological review. The persisted
        # mortality pressure is deliberately a derived health value, not precomputed at insert.
        advance_connection(c,30)
        row=c.execute("SELECT status FROM actors WHERE id=?",(aid,)).fetchone()
        died_day=None
        if row and row['status']=='deceased':
            died_day=int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        else:
            reviewed=c.execute("SELECT mortality_pressure,aging_phase FROM actor_health_profiles WHERE actor_id=?",(aid,)).fetchone()
            assert reviewed['aging_phase']=='late_decline'
            assert float(reviewed['mortality_pressure']) >= 8.0, dict(reviewed)

        # Use the real production scheduler, not a direct death call. Ten years is ample for the
        # deterministic audit seed while still leaving the death stochastic within the health owner.
        for _ in range(40):
            if died_day is not None: break
            advance_connection(c,90)
            row=c.execute("SELECT status FROM actors WHERE id=?",(aid,)).fetchone()
            if row and row['status']=='deceased':
                died_day=int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]); break
        assert died_day is not None, 'ordinary elderly mortality did not wake within 10 years of production scheduling'
        life=c.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?",(aid,)).fetchone()
        assert life and life['life_status']=='deceased'
        assert c.execute("PRAGMA integrity_check").fetchone()[0]=='ok'
        assert not c.execute("PRAGMA foreign_key_check").fetchall()
        print(f'age/birthdate mortality trigger PASS — death day {died_day}')

if __name__=='__main__':
    run()
