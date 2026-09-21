from __future__ import annotations
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.health import ensure_health_profile,add_condition
from engine.expertise import set_actor_competence
from engine.underworld_medicine import process_due_underworld_medicine,record_medical_misconduct,create_medical_access
from engine.coverage import snapshot_coverage


def _actor(c,name,loc):
    aid=int(c.execute("insert into actors(name,actor_type,current_location_id,status) values (?,'character',?,'active')",(name,loc)).lastrowid)
    c.execute("insert into actor_life_profiles(actor_id,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) values (?,'adult',0,'living',0,'{}')",(aid,));ensure_health_profile(c,aid);return aid

def run():
    assert ENGINE_VERSION in {'0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=40
    reset_db();init_db()
    with connect() as c:
        loc=int(c.execute("insert into locations(name,kind,is_canon) values ('Medical Test Ward','district',1)").lastrowid)
        org=int(c.execute("insert into actors(name,actor_type,current_location_id,status) values ('Test Underworld House','institution',?,'active')",(loc,)).lastrowid)
        c.execute("insert into institution_profiles(actor_id,institution_kind) values (?,'criminal dynasty')",(org,))
        c.execute("insert into underworld_institution_profiles(institution_actor_id,primary_location_id,operating_model,status,next_review_day,metadata_json) values (?,?,'test','active',30,'{}')",(org,loc))
        patient=_actor(c,'Injured Smuggler',loc); doctor=_actor(c,'Discreet Physician',loc);set_actor_competence(c,doctor,'medicine',70)
        c.execute("insert into institution_memberships(institution_actor_id,member_actor_id,membership_kind,status,provenance_json,metadata_json) values (?,?,'member','active','[]','{}')",(org,patient))
        cond=add_condition(c,patient,'injury','Knife wound',severity=55,pain_impact=50,capacity_impact=30,recovery_rate_per_30=4)
        c.execute("update world_state set current_day=30 where id=1"); out=process_due_underworld_medicine(c,30)
        assert out['access_created']==1 and out['treatments_created']==1,out
        access=c.execute("select * from underworld_medical_access where patient_actor_id=? and condition_id=?",(patient,cond)).fetchone();assert access and access['consent_status']=='voluntary'
        treatment=c.execute("select * from medical_treatments where actor_id=? and condition_id=?",(patient,cond)).fetchone();assert treatment and int(treatment['provider_actor_id'])==doctor
        # Confidential care is not itself criminal evidence.
        assert not c.execute("select 1 from underworld_evidence where subject_kind='actor' and subject_id=?",(doctor,)).fetchone()
        old=float(c.execute("select severity from health_conditions where id=?",(cond,)).fetchone()[0])
        ev=record_medical_misconduct(c,int(access['id']),treatment_id=int(treatment['id']),misconduct_kind='concealed_injury',harm=40,financial_extraction=25,evidence_visibility='local',evidence_strength=75)
        new=float(c.execute("select severity from health_conditions where id=?",(cond,)).fetchone()[0]);assert new>old
        assert c.execute("select 1 from pressures where actor_id=? and kind='medical_exploitation' and intensity>0",(patient,)).fetchone()
        evidence=c.execute("select * from underworld_evidence where source_kind='medical_misconduct' and source_id=?",(ev,)).fetchone();assert evidence and evidence['visibility']=='local'
        # A coercive access relationship can exist without pretending all underworld care is coercive.
        patient2=_actor(c,'Coerced Patient',loc)
        aid=create_medical_access(c,patient2,provider_actor_id=doctor,purpose_kind='concealed_treatment',consent_status='coerced',coercion=85)
        assert c.execute("select consent_status from underworld_medical_access where id=?",(aid,)).fetchone()[0]=='coerced'
        cov={x['domain_key']:x for x in snapshot_coverage(c,None,phase='v40-test')}
        assert cov['42_exploitation_medicine']['mechanism_status']=='RUNNABLE' and cov['42_exploitation_medicine']['populated_count']>=1,cov['42_exploitation_medicine']
        c.commit()
    print('v0.40.0 underworld medicine / exploitation regression PASS')
if __name__=='__main__':run()
