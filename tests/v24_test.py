from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION,connect,init_db,reset_db
from engine.expertise import set_actor_competence
from engine.education import *
from engine.simulation import advance_connection


def actor(c,n,t='character'):
    c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,?, 'active')",(n,t)); return int(c.execute("SELECT id FROM actors WHERE name=?",(n,)).fetchone()[0])

def run():
    reset_db(); init_db(); assert ENGINE_VERSION in {'0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
    with connect() as c:
        inst=actor(c,'Test Hall','institution'); teacher=actor(c,'Teacher One'); student=actor(c,'Student One')
        set_actor_competence(c,teacher,'martial',80); set_actor_competence(c,student,'martial',20)
        line=create_transmission_line(c,'test_line','Test Line','martial',institution_actor_id=inst,founding_teacher_actor_id=teacher,interpretation_summary='Campaign test line.')
        manual=create_knowledge_asset(c,'Test Foundation Manual','manual','martial',institution_actor_id=inst,lineage_key='test_line',access_tier='inner',preservation_mode='documented')
        add_knowledge_custody(c,manual,'archive',institution_actor_id=inst)
        grant_knowledge_access(c,manual,teacher,'teach')
        program=create_program(c,'foundation','Foundation Course','martial','martial_foundation',institution_actor_id=inst,duration_days=60,capacity=4,min_teacher_score=60,completion_gain=10,max_score_from_program=45,certificate_key='foundation_complete',lineage_key='test_line',review_cadence_days=15)
        link_program_knowledge(c,program,manual,'required_teacher_access')
        create_teaching_relationship(c,teacher,student,'instructor','martial',institution_actor_id=inst)
        configure_reproduction(c,inst,recruitment_capacity=70,training_capacity=65,instructor_depth=75,archival_resilience=80,review_cadence_days=30)
        cand=set_successor_candidate(c,inst,student,'principal_instructor',readiness=69,legitimacy=70,transmission_depth=60)
        enr=enroll(c,student,program,primary_teacher_actor_id=teacher)
        advance_connection(c,90)
        e=c.execute("SELECT * FROM education_enrollments WHERE id=?",(enr,)).fetchone(); assert e['status']=='completed'
        assert 29.9 <= competence_score(c,student,'martial') <= 30.1
        assert c.execute("SELECT COUNT(*) FROM professional_certifications WHERE actor_id=? AND certificate_key='foundation_complete' AND status='active'",(student,)).fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM actor_transmissions WHERE line_id=? AND actor_id=? AND status='active'",(line,student)).fetchone()[0]==1
        rp=c.execute("SELECT * FROM institution_reproduction_profiles WHERE institution_actor_id=?",(inst,)).fetchone(); assert rp and rp['pipeline_health']>0
        sc=c.execute("SELECT status FROM institutional_successor_candidates WHERE id=?",(cand,)).fetchone()[0]; assert sc in ('candidate','eligible') and sc!='chosen'
        assert c.execute("SELECT COUNT(*) FROM events WHERE event_type='education:completion'").fetchone()[0]>=1
        s=education_summary(c); assert s['programs']==1 and s['knowledge_assets']==1 and s['history_entries']>=2
        c.commit()
    print('v0.24 education/transmission regression PASS')
if __name__=='__main__': run()
