from __future__ import annotations

import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.religion import (
    set_affiliation, configure_religious_institution, add_religious_office, add_observance,
    add_obligation, fulfill_obligation, configure_cultural_institution, add_cultural_program,
    add_patronage, religion_context, religion_summary,
)
from engine.civilian import create_household
from engine.civilian_life import ensure_style_movement, set_style_adoption
from engine.player import set_player, build_scene_packet
from engine.simulation import advance_connection


def _actor(c,name,kind='character',loc=None):
    c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES (?,?,?,?)",(name,kind,loc,loc))
    return int(c.execute("SELECT id FROM actors WHERE name=?",(name,)).fetchone()[0])


def run():
    reset_db(); init_db(); assert ENGINE_VERSION in {'0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
    with connect() as c:
        # Engine vocabulary exists, but no calendar/practice is silently invented.
        assert c.execute("SELECT COUNT(*) FROM religious_traditions").fetchone()[0] == 10
        assert c.execute("SELECT COUNT(*) FROM religious_observances").fetchone()[0] == 0
        keys={r[0] for r in c.execute("SELECT tradition_key FROM religious_traditions").fetchall()}
        assert {'witness','hearth_rites','vigil','imperial_observance','dunmoor_pantheon','hollow_faith','tidefaith','dayfire','thornward_old_gods','keeping_of_names'} == keys

        c.execute("INSERT INTO locations(name,kind) VALUES ('Riteford','town')")
        loc=int(c.execute("SELECT id FROM locations WHERE name='Riteford'").fetchone()[0])
        person=_actor(c,'Mara Vale','character',loc)
        clergy=_actor(c,'Orin Pell','character',loc)
        shrine=_actor(c,'Riteford Vigil Hall','institution',loc)
        theatre=_actor(c,'Riteford Players','institution',loc)

        # Religion is multi-axis lived state, not a faction switch.
        a1=set_affiliation(c,person,'hearth_rites',practice_intensity=70,publicness=80)
        a2=set_affiliation(c,person,'vigil',affiliation_kind='participant',practice_intensity=35,publicness=45)
        assert a1 != a2
        assert c.execute("SELECT COUNT(*) FROM religious_affiliations WHERE actor_id=? AND status='active'",(person,)).fetchone()[0]==2

        configure_religious_institution(c,shrine,'vigil',treasury=100,charity_commitment=20)
        office=add_religious_office(c,clergy,shrine,'keeper',standing=70)
        assert office>0
        obs=add_observance(c,'vigil','Autumn Vigil',due_day=10,recurrence_days=30,institution_actor_id=shrine,location_id=loc,significance=70)
        obl=add_obligation(c,'Attend the family memorial observance',obligation_kind='family_memorial',due_day=12,actor_id=person,tradition='hearth_rites',reputation_stakes=20)

        # Cultural institutions persist separately from commercial enterprises.
        configure_cultural_institution(c,theatre,'theatre',resources=30,prestige=55,public_reach=70)
        style=ensure_style_movement(c,'riteford_stage','Riteford Stage Dress','dress',origin_location_id=loc)
        set_style_adoption(c,style,loc,adoption=20)
        prog=add_cultural_program(c,theatre,'Founders Play','performance',due_day=8,recurrence_days=20,location_id=loc,style_id=style,prestige_effect=2,reach=80)
        assert prog>0

        # Patronage is actual economic state transfer.
        hh=create_household(c,'Vale Household',head_actor_id=person,location_id=loc,wealth=200,liquidity=100)
        pat=add_patronage(c,15,due_day=5,source_household_id=hh,target_religious_actor_id=shrine,recurrence_days=30)
        assert pat>0
        advance_connection(c,10)
        assert c.execute("SELECT COUNT(*) FROM religious_observance_instances WHERE observance_id=?",(obs,)).fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM cultural_program_instances WHERE program_id=?",(prog,)).fetchone()[0]==1
        assert float(c.execute("SELECT liquidity FROM households WHERE id=?",(hh,)).fetchone()[0]) < 100
        assert float(c.execute("SELECT treasury FROM religious_institutions WHERE institution_actor_id=?",(shrine,)).fetchone()[0]) > 100
        assert float(c.execute("SELECT adoption FROM style_adoption WHERE style_id=? AND location_id=?",(style,loc)).fetchone()[0]) > 20

        # Obligations affect a dedicated reputation domain rather than global moral alignment.
        advance_connection(c,3)
        assert c.execute("SELECT status FROM religious_obligations WHERE id=?",(obl,)).fetchone()[0]=='overdue'
        before=float(c.execute("SELECT value FROM social_reputation WHERE subject_kind='actor' AND subject_id=? AND domain='religious_reliability'",(person,)).fetchone()[0])
        fulfill_obligation(c,obl)
        after=float(c.execute("SELECT value FROM social_reputation WHERE subject_kind='actor' AND subject_id=? AND domain='religious_reliability'",(person,)).fetchone()[0])
        assert after>before

        ctx=religion_context(c,person,loc)
        assert len(ctx['affiliations'])==2
        set_player(c,person,campaign_name='Religion test')
        packet=build_scene_packet(c,'I attend to my ordinary obligations in town.')
        assert 'religious_context' in packet
        assert len(packet['religious_context']['local_religious_institutions'])==1
        assert len(packet['cultural_context']['local_cultural_institutions'])==1
        assert int(c.execute("SELECT seniority_days FROM religious_offices WHERE id=?",(office,)).fetchone()[0])>0
        s=religion_summary(c)
        assert s['religious_institutions']==1 and s['cultural_institutions']==1
        c.commit()
    print('v0.21 religion/cultural institutions regression PASS')

if __name__=='__main__': run()
