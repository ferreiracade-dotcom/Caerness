from __future__ import annotations

import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.religion import (
    set_affiliation, end_affiliation, configure_religious_institution, add_religious_office,
    add_observance, add_obligation, fulfill_obligation, configure_cultural_institution,
    add_cultural_program, add_patronage, process_due_religion,
)
from engine.civilian import create_household
from engine.simulation import advance_connection


def _actor(c,name,kind,loc):
    c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES (?,?,?,?)",(name,kind,loc,loc))
    return int(c.execute("SELECT id FROM actors WHERE name=?",(name,)).fetchone()[0])


def _raises(fn):
    try:
        fn(); return False
    except ValueError:
        return True


def run():
    reset_db(); init_db(); assert ENGINE_VERSION in {'0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0'}
    with connect() as c:
        c.execute("INSERT INTO locations(name,kind) VALUES ('Edge Rite','town')")
        loc=int(c.execute("SELECT id FROM locations WHERE name='Edge Rite'").fetchone()[0])
        p=_actor(c,'Edge Person','character',loc)
        dead=_actor(c,'Dead Keeper','character',loc)
        inst=_actor(c,'Edge Vigil Hall','institution',loc)
        culture=_actor(c,'Edge Archive','institution',loc)
        wrong=_actor(c,'Ordinary Person Institution Error','character',loc)

        # 1. Repeated affiliation configuration is idempotent; history survives ending.
        x=set_affiliation(c,p,'hearth_rites',practice_intensity=20)
        y=set_affiliation(c,p,'hearth_rites',practice_intensity=80)
        assert x==y
        assert c.execute("SELECT COUNT(*) FROM religious_affiliations WHERE actor_id=? AND tradition_id=(SELECT id FROM religious_traditions WHERE tradition_key='hearth_rites')",(p,)).fetchone()[0]==1
        end_affiliation(c,x)
        assert c.execute("SELECT status,left_day FROM religious_affiliations WHERE id=?",(x,)).fetchone()['status']=='former'
        z=set_affiliation(c,p,'hearth_rites')
        assert z!=x

        # 2. Actor type and tradition ownership are validated.
        assert _raises(lambda: configure_religious_institution(c,wrong,'vigil'))
        configure_religious_institution(c,inst,'vigil',treasury=0,charity_commitment=80)
        assert _raises(lambda: add_observance(c,'hearth_rites','Mismatch',due_day=5,institution_actor_id=inst))

        # 3. No backdated calendars or obligations.
        c.execute("UPDATE world_state SET current_day=10 WHERE id=1")
        assert _raises(lambda: add_observance(c,'vigil','Past Day',due_day=9,institution_actor_id=inst))
        assert _raises(lambda: add_obligation(c,'Past obligation',obligation_kind='rite',due_day=9,actor_id=p))
        c.execute("UPDATE world_state SET current_day=0 WHERE id=1")

        # 4. Due processing is idempotent on the same day and recurrence cannot duplicate instances.
        obs=add_observance(c,'vigil','Recurring Vigil',due_day=5,recurrence_days=10,institution_actor_id=inst,location_id=loc)
        advance_connection(c,5)
        assert c.execute("SELECT COUNT(*) FROM religious_observance_instances WHERE observance_id=?",(obs,)).fetchone()[0]==1
        process_due_religion(c,5)
        assert c.execute("SELECT COUNT(*) FROM religious_observance_instances WHERE observance_id=?",(obs,)).fetchone()[0]==1
        advance_connection(c,10)
        assert c.execute("SELECT COUNT(*) FROM religious_observance_instances WHERE observance_id=?",(obs,)).fetchone()[0]==2

        # 5. Dead office holder does not remain active.
        office=add_religious_office(c,dead,inst,'keeper')
        c.execute("UPDATE actors SET status='deceased' WHERE id=?",(dead,))
        process_due_religion(c,30)
        assert c.execute("SELECT status FROM religious_offices WHERE id=?",(office,)).fetchone()[0]=='former'

        # 6. Patronage cannot overdraft or mint money; insufficient funding becomes strained.
        hh=create_household(c,'Poor Household',head_actor_id=p,location_id=loc,wealth=1,liquidity=3)
        before_t=float(c.execute("SELECT treasury FROM religious_institutions WHERE institution_actor_id=?",(inst,)).fetchone()[0])
        pat=add_patronage(c,20,due_day=31,source_household_id=hh,target_religious_actor_id=inst)
        advance_connection(c,16)  # day 31
        after_liq=float(c.execute("SELECT liquidity FROM households WHERE id=?",(hh,)).fetchone()[0])
        assert after_liq >= 0 and after_liq > -10
        assert float(c.execute("SELECT treasury FROM religious_institutions WHERE institution_actor_id=?",(inst,)).fetchone()[0])<=before_t
        assert c.execute("SELECT status FROM institutional_patronage WHERE id=?",(pat,)).fetchone()[0]=='strained'

        # 7. Fulfilment is idempotent and cannot repeatedly farm reputation.
        obl=add_obligation(c,'Remember the dead',obligation_kind='memorial',due_day=32,actor_id=p,tradition='hearth_rites',reputation_stakes=40)
        advance_connection(c,2)  # day 33 -> overdue
        fulfill_obligation(c,obl)
        rep1=float(c.execute("SELECT value FROM social_reputation WHERE subject_kind='actor' AND subject_id=? AND domain='religious_reliability'",(p,)).fetchone()[0])
        fulfill_obligation(c,obl)
        rep2=float(c.execute("SELECT value FROM social_reputation WHERE subject_kind='actor' AND subject_id=? AND domain='religious_reliability'",(p,)).fetchone()[0])
        assert rep1==rep2

        # 8. Cultural programs stop when their institution is dissolved/deceased and cannot fire posthumously.
        configure_cultural_institution(c,culture,'archive',resources=5)
        prog=add_cultural_program(c,culture,'Public Reading','reading',due_day=40,recurrence_days=20,location_id=loc)
        c.execute("UPDATE actors SET status='dissolved' WHERE id=?",(culture,))
        advance_connection(c,7)  # day 40
        assert c.execute("SELECT COUNT(*) FROM cultural_program_instances WHERE program_id=?",(prog,)).fetchone()[0]==0
        assert c.execute("SELECT status FROM cultural_programs WHERE id=?",(prog,)).fetchone()[0]=='paused'

        # 9. The religion model contains no faction/alignment column: belief is not inferred from Churn affiliation.
        cols=[r[1] for r in c.execute("PRAGMA table_info(religious_affiliations)").fetchall()]
        assert 'faction' not in cols and 'alignment' not in cols

        # 10. Current religious vocabulary is present, but exact feast days are never auto-seeded.
        keys={r[0] for r in c.execute("SELECT tradition_key FROM religious_traditions").fetchall()}
        assert 'witness' in keys and 'true_faith' not in keys and 'keeping_of_names' in keys
        # Only test-created observances exist.
        names={r[0] for r in c.execute("SELECT name FROM religious_observances").fetchall()}
        assert names=={'Recurring Vigil'}
        c.commit()
    print('v0.21 adversarial religion/cultural edge-case audit PASS')

if __name__=='__main__': run()
