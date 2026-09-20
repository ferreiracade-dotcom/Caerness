from __future__ import annotations

import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.health import (
    configure_health_profile, add_condition, add_treatment, add_disability,
    health_summary, set_demographic_mortality,
)
from engine.expertise import set_actor_competence
from engine.household_life import set_life_profile, set_demographic_cohort
from engine.player import set_player, build_scene_packet
from engine.simulation import advance_connection


def _actor(conn,name,birth_day,loc):
    conn.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES (?,'character',?,?)",(name,loc,loc))
    aid=int(conn.execute("SELECT id FROM actors WHERE name=?",(name,)).fetchone()[0])
    set_life_profile(conn,aid,birth_day=birth_day,family_formation_eligible=True)
    return aid


def run():
    reset_db(); init_db()
    assert ENGINE_VERSION in {'0.20.1','0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0'}
    with connect() as c:
        c.execute("INSERT INTO locations(name,kind) VALUES ('Health Test','town')")
        loc=int(c.execute("SELECT id FROM locations WHERE name='Health Test'").fetchone()[0])
        ordinary=_actor(c,'Ordinary Elder',-90*365,loc)
        master=_actor(c,'Fifth Elder',-90*365,loc)
        configure_health_profile(c,ordinary,longevity_class='ordinary')
        configure_health_profile(c,master,longevity_class='fifth')
        advance_connection(c,31)
        po=c.execute("SELECT aging_phase,recovery_capacity FROM actor_health_profiles WHERE actor_id=?",(ordinary,)).fetchone()
        pm=c.execute("SELECT aging_phase,recovery_capacity FROM actor_health_profiles WHERE actor_id=?",(master,)).fetchone()
        assert po['aging_phase']=='late_decline'
        assert pm['aging_phase']=='prime'
        assert float(po['recovery_capacity']) < float(pm['recovery_capacity'])

        # Specialized Vessel pathology responds much more strongly to Vein-Mending than ordinary care.
        a=_actor(c,'Patient A',-35*365,loc); b=_actor(c,'Patient B',-35*365,loc)
        mender=_actor(c,'Qualified Mender',-45*365,loc)
        physician=_actor(c,'Qualified Physician',-45*365,loc)
        set_actor_competence(c,mender,'vein_mending',85)
        set_actor_competence(c,physician,'medicine',80)
        configure_health_profile(c,a,longevity_class='third'); configure_health_profile(c,b,longevity_class='third')
        ca=add_condition(c,a,'vein_channel','Channel tear',severity=60,capacity_impact=40,recovery_rate_per_30=8,
                         specialist_requirement='vein_mender')
        cb=add_condition(c,b,'vein_channel','Channel tear',severity=60,capacity_impact=40,recovery_rate_per_30=8,
                         specialist_requirement='vein_mender')
        add_treatment(c,a,'ordinary_medicine',condition_id=ca,provider_actor_id=physician,quality=90,adherence=90)
        add_treatment(c,b,'vein_mending',condition_id=cb,provider_actor_id=mender,quality=90,adherence=90)
        advance_connection(c,60)
        sa=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(ca,)).fetchone()[0])
        sb=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(cb,)).fetchone()[0])
        assert sb < sa
        # add_condition must not silently downgrade cultivation longevity class.
        assert c.execute("SELECT longevity_class FROM actor_health_profiles WHERE actor_id=?",(a,)).fetchone()[0]=='third'

        # Disability is persistent capacity state rather than an unresolved injury alias.
        add_disability(c,a,'Permanent limp',mobility_impact=35,stamina_impact=10,capacity_impact=10)
        advance_connection(c,31)
        hs=health_summary(c,a)
        assert hs['profile']['mobility'] < 100
        assert hs['disabilities'][0]['status'] in ('active','adapted')

        # A truly catastrophic pathology can cause authoritative death and lifecycle cleanup.
        doomed=_actor(c,'Doomed Patient',-50*365,loc)
        configure_health_profile(c,doomed,longevity_class='ordinary')
        add_condition(c,doomed,'illness','Terminal fever',severity=100,capacity_impact=100,fatality_pressure=100,
                      progression_rate_per_30=0,recovery_rate_per_30=0,next_review_days=1)
        advance_connection(c,2)
        assert c.execute("SELECT status FROM actors WHERE id=?",(doomed,)).fetchone()[0]=='deceased'
        assert c.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?",(doomed,)).fetchone()[0]=='deceased'

        # Aggregate mortality operates without instantiating named people.
        cid=set_demographic_cohort(c,loc,'ordinary_population','60_plus',1000,annual_birth_pressure=0,annual_migration_rate=0)
        set_demographic_mortality(c,cid,0.10)
        before=float(c.execute("SELECT population FROM demographic_cohorts WHERE id=?",(cid,)).fetchone()[0])
        advance_connection(c,365)
        after=float(c.execute("SELECT population FROM demographic_cohorts WHERE id=?",(cid,)).fetchone()[0])
        assert after < before
        assert after > 0

        # Health state is available to the player-facing camera without exposing hidden state.
        set_player(c,a,campaign_name='Health test')
        packet=build_scene_packet(c,'I try to travel all day.')
        assert 'health_context' in packet
        assert packet['health_context']['mobility'] < 100
        c.commit()
    print('v0.20 health/aging regression PASS')

if __name__=='__main__': run()
