from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,connect,init_db,reset_db
from engine.simulation import advance_connection
from engine.stress import run_horizon, contradiction_scan, stress_report
from engine.player import set_player, designate_camera_successor, process_camera_succession
from engine.civilian import create_household, create_enterprise
from engine.business import set_commercial_context, configure_enterprise_business
from engine.household_life import set_life_profile, set_demographic_cohort, mark_actor_deceased
from engine.ecology import configure_environment, add_route
from engine.politics import configure_polity, set_territorial_control, add_territorial_claim
from engine.education import create_program, enroll, configure_reproduction, set_successor_candidate, choose_successor_candidate
from engine.expertise import set_actor_competence
from engine.religion import configure_cultural_institution, add_cultural_program


def actor(c,name,kind='character',loc=None):
    c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,?,?,'active')",(name,kind,loc))
    return int(c.execute('SELECT id FROM actors WHERE name=?',(name,)).fetchone()[0])

def location(c,name,kind='town'):
    c.execute('INSERT INTO locations(name,kind) VALUES (?,?)',(name,kind))
    return int(c.execute('SELECT id FROM locations WHERE name=?',(name,)).fetchone()[0])


def run():
    reset_db(); init_db(); assert ENGINE_VERSION in {'0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
    with connect() as c:
        home=location(c,'Stressford'); border=location(c,'Riverside')
        configure_environment(c,home,climate_label='temperate',terrain_kind='plain',current_carrying_capacity=120,current_replenishment=70)
        configure_environment(c,border,climate_label='temperate',terrain_kind='river',current_carrying_capacity=90,current_replenishment=60)
        add_route(c,home,border,route_kind='road',base_days=4,bidirectional=True)

        player=actor(c,'Stress Player',loc=home); heir=actor(c,'Stress Heir',loc=home)
        teacher=actor(c,'Stress Teacher',loc=home); student=actor(c,'Stress Student',loc=home)
        polity_actor=actor(c,'Stress Polity','institution',home); academy=actor(c,'Stress Academy','institution',home)
        culture=actor(c,'Stress Cultural Hall','institution',home)
        set_life_profile(c,player,birth_day=-35*365)
        set_life_profile(c,heir,birth_day=-18*365)
        set_life_profile(c,teacher,birth_day=-38*365)
        set_life_profile(c,student,birth_day=-16*365)
        set_player(c,player,'Stress Campaign'); designate_camera_successor(c,player,heir,priority=100)

        hh=create_household(c,'Stress Household',head_actor_id=player,location_id=home,wealth=5000,liquidity=2000,cohesion=80)
        ent=create_enterprise(c,'Stress Inn','service',owner_actor_id=player,household_id=hh,location_id=home,capital=3000,cash=1500,reputation=75,admin_quality=75,labor_capacity=80)
        set_commercial_context(c,home,foot_traffic=90,traveler_flow=90,disposable_income=80,trade_flow=75,security=80)
        configure_enterprise_business(c,ent,'inn',quality=85,capacity=85,clientele_fit=90,service_reliability=90,cadence_days=30)

        # Aggregate population has enough age structure to prove turnover over a century.
        for band,pop in [('0_4',200),('5_12',350),('13_17',200),('18_39',900),('40_59',500),('60_plus',180)]:
            set_demographic_cohort(c,home,'townsfolk',band,pop,annual_birth_pressure=0.015 if band=='18_39' else 0,annual_migration_rate=0.001)

        set_actor_competence(c,teacher,'scholarship',80); set_actor_competence(c,student,'scholarship',10)
        prog=create_program(c,'stress_course','Stress Course','scholarship','scholarly_training',institution_actor_id=academy,duration_days=3*365,capacity=4,min_teacher_score=60,completion_gain=20,max_score_from_program=45,review_cadence_days=30)
        enroll(c,student,prog,primary_teacher_actor_id=teacher)
        configure_reproduction(c,academy,recruitment_capacity=75,training_capacity=75,instructor_depth=70,archival_resilience=80,review_cadence_days=90)
        set_successor_candidate(c,academy,student,'head_teacher',readiness=72,legitimacy=70,transmission_depth=60)

        configure_cultural_institution(c,culture,'theatre',location_id=home,prestige=60,resources=500,public_reach=70,continuity=75,review_days=30)
        add_cultural_program(c,culture,'Seasonal Performance','performance',due_day=180,recurrence_days=365,prestige_effect=.2,reach=60)

        polity=configure_polity(c,polity_actor,polity_kind='city_state',legitimacy=70,stability=70,review_cadence_days=90)
        set_territorial_control(c,polity,home)
        # A configured campaign claim creates real divergence later without a balancing script.
        add_territorial_claim(c,polity,border,claim_kind='charter',pressure=5,rate_per_30_days=.35,threshold=60,resolution_policy='transfer')

        # 20-year quiet/extreme-success run: ordinary prosperity must be able to persist without a catastrophe debt.
        s20=run_horizon(c,20,label='20-year quiet prosperity',scenario_kind='quiet_life_extreme_success',checkpoint_years=5)
        assert s20['contradictions']==0 and s20['snapshot']['day']==20*365
        assert c.execute('SELECT COUNT(*) FROM enterprise_accounts WHERE enterprise_id=?',(ent,)).fetchone()[0]>0
        assert c.execute("SELECT COUNT(*) FROM pressures WHERE actor_id=?",(player,)).fetchone()[0]==0

        # Protagonist death changes the camera, not world causality.
        mark_actor_deceased(c,player,reason='stress-suite camera succession')
        assert process_camera_succession(c)==heir
        assert int(c.execute('SELECT player_actor_id FROM player_state WHERE id=1').fetchone()[0])==heir
        assert c.execute('SELECT COUNT(*) FROM player_camera_history').fetchone()[0]>=1

        # Continue to 40 years total: training and institutions have had a generation to change.
        s40=run_horizon(c,20,label='40-year generational continuation',scenario_kind='institutional_generation',checkpoint_years=5)
        assert s40['contradictions']==0 and s40['snapshot']['day']==40*365
        assert c.execute("SELECT status FROM education_enrollments WHERE actor_id=?",(student,)).fetchone()[0] in ('completed','paused')
        cand=c.execute("SELECT id,status FROM institutional_successor_candidates WHERE institution_actor_id=? AND actor_id=?",(academy,student)).fetchone()
        assert cand and cand['status']=='eligible'; choose_successor_candidate(c,int(cand['id']))
        assert c.execute("SELECT status FROM institutional_successor_candidates WHERE id=?",(cand['id'],)).fetchone()[0]=='chosen'
        assert c.execute('SELECT COUNT(*) FROM cultural_program_instances').fetchone()[0]>10

        # Continue past a century. We care about continuity, turnover, divergence and bounded DB growth.
        s120=run_horizon(c,80,label='120-year macro history',scenario_kind='century_scale',checkpoint_years=10)
        assert s120['contradictions']==0 and s120['snapshot']['day']==120*365
        assert c.execute('SELECT COUNT(*) FROM political_history').fetchone()[0]>0
        assert c.execute('SELECT controller_polity_id FROM territorial_control WHERE location_id=?',(border,)).fetchone()[0]==polity
        assert c.execute('SELECT SUM(population) FROM demographic_cohorts WHERE location_id=?',(home,)).fetchone()[0]>0
        assert not contradiction_scan(c)
        assert s120['snapshot']['database_bytes_approx'] < 250_000_000
        rep=stress_report(c,s120['run_id']); assert rep['status']=='passed' and len(rep['checkpoints'])>=9
        c.commit()
    print('v0.25 long-run 20/40/120-year stress regression PASS')

if __name__=='__main__': run()
