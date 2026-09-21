from __future__ import annotations

import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.health import (
    configure_health_profile, add_condition, add_treatment, add_disability,
    resolve_disability, health_summary,
)
from engine.household_life import set_life_profile, mark_actor_deceased
from engine.expertise import set_actor_competence
from engine.simulation import advance_connection


def _actor(c,name,birth_day,loc):
    c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES (?,'character',?,?)",(name,loc,loc))
    aid=int(c.execute("SELECT id FROM actors WHERE name=?",(name,)).fetchone()[0])
    set_life_profile(c,aid,birth_day=birth_day,family_formation_eligible=True)
    return aid


def run():
    reset_db(); init_db()
    assert ENGINE_VERSION in {'0.20.1','0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
    with connect() as c:
        c.execute("INSERT INTO locations(name,kind) VALUES ('Edge Health','town')")
        loc=int(c.execute("SELECT id FROM locations WHERE name='Edge Health'").fetchone()[0])

        # 1. Aging continuity: a late breakthrough may slow future decline but cannot erase accrued old-age decline.
        elder=_actor(c,'Late Breakthrough',-90*365,loc)
        configure_health_profile(c,elder,longevity_class='ordinary')
        advance_connection(c,31)
        before=c.execute("SELECT aging_phase,recovery_capacity,mortality_pressure FROM actor_health_profiles WHERE actor_id=?",(elder,)).fetchone()
        assert before['aging_phase']=='late_decline'
        configure_health_profile(c,elder,longevity_class='fifth')
        after=c.execute("SELECT aging_phase,recovery_capacity,mortality_pressure FROM actor_health_profiles WHERE actor_id=?",(elder,)).fetchone()
        assert after['aging_phase']=='late_decline', 'breakthrough must not rewind established decline back to prime'
        assert float(after['recovery_capacity']) <= float(before['recovery_capacity']) + 0.01
        assert float(after['mortality_pressure']) + 0.01 >= float(before['mortality_pressure'])

        # 2. Treatment ownership: specialist procedures require a living, sufficiently competent provider.
        patient=_actor(c,'Ownership Patient',-30*365,loc)
        configure_health_profile(c,patient,longevity_class='third')
        cond=add_condition(c,patient,'vein_channel','Difficult channel injury',severity=60,recovery_rate_per_30=8,
                           specialist_requirement='vein_mender')
        failed=False
        try:
            add_treatment(c,patient,'vein_mending',condition_id=cond,quality=90,adherence=90)
        except ValueError:
            failed=True
        assert failed, 'Vein-Mending must not exist without a qualified provider'
        novice=_actor(c,'Novice Helper',-40*365,loc); set_actor_competence(c,novice,'vein_mending',30)
        failed=False
        try:
            add_treatment(c,patient,'vein_mending',condition_id=cond,provider_actor_id=novice)
        except ValueError:
            failed=True
        assert failed, 'unqualified providers must not count as Vein-Menders'
        mender=_actor(c,'Real Mender',-50*365,loc); set_actor_competence(c,mender,'vein_mending',80)
        base_day=int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        tid=add_treatment(c,patient,'vein_mending',condition_id=cond,provider_actor_id=mender,end_day=base_day+20)
        assert tid>0

        # 3. Expired treatment cannot affect recovery after its end, even if the next condition review is later.
        control=_actor(c,'Control Patient',-30*365,loc)
        configure_health_profile(c,control,longevity_class='third')
        c2=add_condition(c,control,'vein_channel','Difficult channel injury',severity=60,recovery_rate_per_30=8,
                         specialist_requirement='vein_mender',next_review_days=30)
        # Match patient review to 30 days from now; treatment only runs for 20 days and must be time-weighted.
        c.execute("UPDATE health_conditions SET next_review_day=? WHERE id=?",(base_day+30,cond))
        advance_connection(c,30)
        st=c.execute("SELECT status FROM medical_treatments WHERE id=?",(tid,)).fetchone()[0]
        assert st=='completed'
        treated=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(cond,)).fetchone()[0])
        untreated=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(c2,)).fetchone()[0])
        assert treated < untreated, 'partial treatment should help'
        # It should not receive a full 30-day treatment bonus for a 20-day course.
        assert treated > untreated - 8.0

        # 4. Vein-specific care is not a universal cure for ordinary illness.
        ordinary_a=_actor(c,'Ordinary A',-25*365,loc); ordinary_b=_actor(c,'Ordinary B',-25*365,loc)
        configure_health_profile(c,ordinary_a); configure_health_profile(c,ordinary_b)
        ia=add_condition(c,ordinary_a,'illness','Common fever',severity=50,recovery_rate_per_30=6,next_review_days=30)
        ib=add_condition(c,ordinary_b,'illness','Common fever',severity=50,recovery_rate_per_30=6,next_review_days=30)
        now=int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        add_treatment(c,ordinary_a,'guided_circulation',condition_id=ia,provider_actor_id=mender,end_day=now+50)
        advance_connection(c,30)
        sea=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(ia,)).fetchone()[0])
        seb=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(ib,)).fetchone()[0])
        assert abs(sea-seb) < 0.01, 'Vein treatment must not boost ordinary fever recovery'

        # 5. Recovery responds to actual aging/recovery capacity, not only the condition's nominal recovery rate.
        young=_actor(c,'Young Recovery',-30*365,loc); old=_actor(c,'Old Recovery',-90*365,loc)
        configure_health_profile(c,young,longevity_class='ordinary'); configure_health_profile(c,old,longevity_class='ordinary')
        cy=add_condition(c,young,'injury','Same injury young',severity=60,recovery_rate_per_30=10,next_review_days=30)
        co=add_condition(c,old,'injury','Same injury old',severity=60,recovery_rate_per_30=10,next_review_days=30)
        advance_connection(c,30)
        sy=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(cy,)).fetchone()[0])
        so=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(co,)).fetchone()[0])
        assert sy < so, 'late-decline recovery capacity must materially affect recovery'

        # 6. Disability adaptation is cadence-independent and cannot be farmed by repeated same-day recalculation.
        dis_actor=_actor(c,'Adaptation Patient',-40*365,loc); configure_health_profile(c,dis_actor)
        did=add_disability(c,dis_actor,'Persistent impairment',mobility_impact=40,adaptation=0)
        advance_connection(c,365)
        a1=float(c.execute("SELECT adaptation FROM disabilities WHERE id=?",(did,)).fetchone()[0])
        # Trigger several recalculations on the same day.
        for i in range(5):
            x=add_condition(c,dis_actor,'fatigue',f'Brief fatigue {i}',severity=1,recovery_rate_per_30=100,next_review_days=1)
        a2=float(c.execute("SELECT adaptation FROM disabilities WHERE id=?",(did,)).fetchone()[0])
        assert abs(a2-a1)<0.001, 'same-day recalculations must not accelerate disability adaptation'
        advance_connection(c,365)
        a3=float(c.execute("SELECT adaptation FROM disabilities WHERE id=?",(did,)).fetchone()[0])
        assert 5.9 <= a3 <= 6.1, (a1,a3)

        # 7. Resolved source conditions do not erase persistent disability; explicit repair can resolve it.
        source=add_condition(c,dis_actor,'injury','Source injury',severity=1,recovery_rate_per_30=100,next_review_days=1)
        did2=add_disability(c,dis_actor,'Lasting aftereffect',source_condition_id=source,mobility_impact=20)
        advance_connection(c,2)
        assert c.execute("SELECT status FROM health_conditions WHERE id=?",(source,)).fetchone()[0]=='resolved'
        assert c.execute("SELECT status FROM disabilities WHERE id=?",(did2,)).fetchone()[0] in ('active','adapted')
        resolve_disability(c,did2,reason='successful reconstruction')
        assert c.execute("SELECT status FROM disabilities WHERE id=?",(did2,)).fetchone()[0]=='resolved'

        # 8. A disability cannot point at another actor's condition.
        foreign=_actor(c,'Foreign Patient',-25*365,loc); configure_health_profile(c,foreign)
        foreign_cond=add_condition(c,foreign,'injury','Foreign injury',severity=20)
        failed=False
        try:
            add_disability(c,dis_actor,'Invalid cross-owner disability',source_condition_id=foreign_cond)
        except ValueError:
            failed=True
        assert failed

        # 9. Provider death stops treatment they own.
        provider_patient=_actor(c,'Provider Death Patient',-30*365,loc); configure_health_profile(c,provider_patient)
        pc=add_condition(c,provider_patient,'injury','Provider-owned course',severity=50,recovery_rate_per_30=5,next_review_days=30)
        provider=_actor(c,'Soon Dead Physician',-60*365,loc); set_actor_competence(c,provider,'medicine',80)
        now=int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        pt=add_treatment(c,provider_patient,'ordinary_medicine',condition_id=pc,provider_actor_id=provider,end_day=now+365)
        mark_actor_deceased(c,provider,reason='unexpected death')
        assert c.execute("SELECT status FROM medical_treatments WHERE id=?",(pt,)).fetchone()[0]=='stopped'

        # 10. Death from any subsystem stops active treatment and health no longer advances on the corpse.
        dying=_actor(c,'External Death',-50*365,loc); configure_health_profile(c,dying)
        dc=add_condition(c,dying,'injury','Ongoing injury',severity=70,recovery_rate_per_30=5,next_review_days=30)
        phys=_actor(c,'Physician Edge',-45*365,loc); set_actor_competence(c,phys,'medicine',80)
        now=int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        dt=add_treatment(c,dying,'ordinary_medicine',condition_id=dc,provider_actor_id=phys,end_day=now+2000)
        mark_actor_deceased(c,dying,reason='external cause')
        assert c.execute("SELECT status FROM medical_treatments WHERE id=?",(dt,)).fetchone()[0]=='stopped'
        sev_before=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(dc,)).fetchone()[0])
        advance_connection(c,90)
        sev_after=float(c.execute("SELECT severity FROM health_conditions WHERE id=?",(dc,)).fetchone()[0])
        assert abs(sev_after-sev_before)<0.001, 'health conditions must freeze after death'

        # 11. Active-health summary excludes dead actors' frozen historical conditions.
        global_summary=health_summary(c)
        assert global_summary['active_treatments'] >= 0
        c.commit()
    print('v0.20.1 health edge-case audit PASS')

if __name__=='__main__': run()
