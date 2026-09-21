from __future__ import annotations
import sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION,connect,init_db,reset_db
from engine.expertise import set_actor_competence
from engine.education import *
from engine.simulation import advance_connection

def actor(c,n,t='character',status='active'):
    c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,?,?)",(n,t,status)); return int(c.execute("SELECT id FROM actors WHERE name=?",(n,)).fetchone()[0])
def fail(fn):
    try: fn()
    except Exception as e:
        if isinstance(e,AssertionError): raise
        return
    raise AssertionError('expected failure')

def run():
    reset_db(); init_db(); assert ENGINE_VERSION in {'0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
    with connect() as c:
        inst=actor(c,'Edge Academy','institution'); t1=actor(c,'Edge Teacher'); t2=actor(c,'Replacement Teacher'); s=actor(c,'Edge Student'); s2=actor(c,'Second Student')
        set_actor_competence(c,t1,'martial',75); set_actor_competence(c,t2,'martial',70); set_actor_competence(c,s,'martial',10); set_actor_competence(c,s2,'martial',10)
        # A manual existing or being accessible never grants competence by itself.
        asset=create_knowledge_asset(c,'Inner Manual','manual','martial',institution_actor_id=inst,preservation_mode='documented')
        add_knowledge_custody(c,asset,'archive',institution_actor_id=inst); grant_knowledge_access(c,asset,s,'study')
        before=competence_score(c,s,'martial'); advance_connection(c,30); assert competence_score(c,s,'martial')==before
        # Advanced instruction requires a qualified teacher and appropriate access.
        prog=create_program(c,'advanced','Advanced Instruction','martial','advanced_instruction',institution_actor_id=inst,duration_days=40,capacity=1,min_entry_score=10,min_teacher_score=65,completion_gain=8,max_score_from_program=35,review_cadence_days=10)
        link_program_knowledge(c,prog,asset,'required_teacher_access')
        fail(lambda: enroll(c,s,prog))
        fail(lambda: enroll(c,s,prog,primary_teacher_actor_id=t1))
        # Access history can be revoked, regranted, and revoked again without corrupting history.
        grant_knowledge_access(c,asset,t2,'teach'); revoke_knowledge_access(c,asset,t2); grant_knowledge_access(c,asset,t2,'teach')
        assert c.execute("SELECT COUNT(*) FROM knowledge_access WHERE asset_id=? AND actor_id=?",(asset,t2)).fetchone()[0]>=2
        grant_knowledge_access(c,asset,t1,'teach'); e=enroll(c,s,prog,primary_teacher_actor_id=t1)
        fail(lambda: enroll(c,s,prog,primary_teacher_actor_id=t1))
        fail(lambda: enroll(c,s2,prog,primary_teacher_actor_id=t2)) # capacity
        # Multiple teachers can exist; true transmission is relational rather than global ownership.
        create_teaching_relationship(c,t1,s,'personal_master','martial',institution_actor_id=inst)
        create_teaching_relationship(c,t2,s,'instructor','martial',institution_actor_id=inst)
        # Teacher death pauses rather than silently completing training.
        c.execute("UPDATE actors SET status='dead' WHERE id=?",(t1,)); advance_connection(c,10)
        er=c.execute("SELECT status,interruption_reason FROM education_enrollments WHERE id=?",(e,)).fetchone(); assert er['status']=='paused' and 'teacher' in er['interruption_reason']
        assert c.execute("SELECT status FROM teaching_relationships WHERE teacher_actor_id=? AND student_actor_id=? AND relation_kind='personal_master'",(t1,s)).fetchone()[0]=='interrupted'
        resume_enrollment(c,e,teacher_actor_id=t2); advance_connection(c,10)
        # Revoking required teacher access interrupts further progress.
        revoke_knowledge_access(c,asset,t2); advance_connection(c,10)
        er=c.execute("SELECT status,interruption_reason FROM education_enrollments WHERE id=?",(e,)).fetchone(); assert er['status']=='paused' and 'knowledge' in er['interruption_reason']
        # Oral/embodied knowledge with no viable custody can genuinely be lost, but only after configured threshold.
        oral=create_knowledge_asset(c,'Living Oral Method','oral_lineage','martial',institution_actor_id=inst,preservation_mode='oral',loss_threshold_days=30)
        keeper=actor(c,'Last Keeper'); add_knowledge_custody(c,oral,'keeper',actor_id=keeper)
        c.execute("UPDATE actors SET status='dead' WHERE id=?",(keeper,)); advance_connection(c,31)
        assert c.execute("SELECT status FROM knowledge_assets WHERE id=?",(oral,)).fetchone()[0] in ('endangered','lost')
        advance_connection(c,365)
        assert c.execute("SELECT status FROM knowledge_assets WHERE id=?",(oral,)).fetchone()[0]=='lost'
        # A transmission line can go dormant without fabricating a replacement teacher.
        lone=actor(c,'Lone Master'); set_actor_competence(c,lone,'martial',80)
        line=create_transmission_line(c,'fragile_line','Fragile Line','martial',institution_actor_id=inst,founding_teacher_actor_id=lone,vitality=5,fragility_per_year=100)
        c.execute("UPDATE actors SET status='dead' WHERE id=?",(lone,)); advance_connection(c,365)
        assert c.execute("SELECT status FROM transmission_lines WHERE id=?",(line,)).fetchone()[0]=='dormant'
        # Institutional successor eligibility never auto-appoints or rewrites other office/ruler systems.
        configure_reproduction(c,inst,review_cadence_days=30)
        cid=set_successor_candidate(c,inst,s,'head_instructor',readiness=75,legitimacy=70,transmission_depth=70)
        advance_connection(c,30)
        assert c.execute("SELECT status FROM institutional_successor_candidates WHERE id=?",(cid,)).fetchone()[0]=='eligible'
        assert c.execute("SELECT COUNT(*) FROM institutional_successor_candidates WHERE status='chosen'").fetchone()[0]==0
        # Dead successor candidate becomes unavailable.
        c.execute("UPDATE actors SET status='dead' WHERE id=?",(s,)); advance_connection(c,30)
        assert c.execute("SELECT status FROM institutional_successor_candidates WHERE id=?",(cid,)).fetchone()[0]=='deceased'
        fail(lambda: choose_successor_candidate(c,cid))
        # Training cannot elevate a student beyond the actual competence of the living teacher merely by setting a generous program gain.
        cap_teacher=actor(c,'Cap Teacher'); cap_student=actor(c,'Cap Student'); set_actor_competence(c,cap_teacher,'craft',40); set_actor_competence(c,cap_student,'craft',35)
        cp=create_program(c,'cap_course','Cap Course','craft','craft_training',duration_days=10,min_teacher_score=35,completion_gain=50,max_score_from_program=95,review_cadence_days=5)
        ce=enroll(c,cap_student,cp,primary_teacher_actor_id=cap_teacher); advance_connection(c,10)
        assert competence_score(c,cap_student,'craft')<=40.0001
        fail(lambda: enroll(c,cap_student,cp,primary_teacher_actor_id=cap_teacher))  # completed programs do not farm competence/certificates
        c.commit()
    print('v0.24 adversarial education/transmission edge audit PASS')
if __name__=='__main__': run()
