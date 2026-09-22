"""ORGPRESS-01 / SUCCESSION-02: defeats create pressure; deaths create real vacancies and causal succession."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, SCHEMA_VERSION
from engine.household_life import set_life_profile, mark_actor_deceased
from engine.combat import create_duel, resolve_duel_exchange


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_orgpress_succession02_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); return connect(),path


def actor(c,name,stage='Third'):
    aid=int(c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')",(name,)).lastrowid)
    set_life_profile(c,aid,birth_day=-40*365,demographic_sex='male',family_formation_eligible=True)
    c.execute("INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,training_effort,resource_access,teacher_support,next_realization_check_day,last_review_day,next_review_day,status) VALUES (?,'Open-Core',?,1,70,60,50,50,20,365,0,30,'active')",(aid,stage))
    return aid


def institution(c,name):
    iid=int(c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'institution','active')",(name,)).lastrowid)
    c.execute("INSERT INTO institution_profiles(actor_id,institution_kind,founded_day,governance_json,culture_json,capacity_json,trajectory,last_review_day) VALUES (?,'sect',0,'{}','{}','{}','stable',0)",(iid,))
    c.execute("INSERT INTO organization_agency_profiles(institution_actor_id,governance_mode,last_review_day) VALUES (?,'institutional',0)",(iid,))
    c.execute("INSERT INTO organization_lifecycle_profiles(institution_actor_id,lifecycle_kind,lifecycle_status,vitality,cohesion,continuity,expansion_capacity,review_cadence_days,next_review_day,last_review_day,metadata_json) VALUES (?,'sect','stable',55,55,55,50,90,90,0,'{}')",(iid,))
    return iid


def member(c,iid,aid,role):
    c.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,role_text,status,joined_day,provenance_json,metadata_json) VALUES (?,?,?,'active',0,'[]','{}')",(iid,aid,role))


def run():
    assert SCHEMA_VERSION>=106
    c,path=bootstrap()

    # Public internal defeat changes institutional pressure/social memory but does not auto-depose the head.
    iid=institution(c,'[ORG02] Sect'); head=actor(c,'[ORG02] Head','Fifth'); challenger=actor(c,'[ORG02] Challenger','Sixth')
    member(c,iid,head,'head'); member(c,iid,challenger,'senior master')
    c.execute("INSERT INTO institutional_authority_slots(institution_actor_id,authority_key,authority_kind,incumbent_actor_id,required_stage,status,created_day,metadata_json) VALUES (?,'head','named_incumbent',?,'Fifth','active',0,'{}')",(iid,head))
    duel=create_duel(c,'[ORG02] internal challenge',challenger,head,stakes=5,capability_a=100,capability_b=1,metadata={'nonlethal':True})
    result=None
    for _ in range(40):
        result=resolve_duel_exchange(c,duel)
        if result.get('status')=='resolved':break
    assert result and int(result['outcome']['winner_actor_id'])==challenger,result
    slot=c.execute("SELECT * FROM institutional_authority_slots WHERE institution_actor_id=? AND authority_key='head'",(iid,)).fetchone()
    assert int(slot['incumbent_actor_id'])==head and slot['status']=='active'
    pressure=c.execute("SELECT * FROM organization_pressures WHERE institution_actor_id=? AND pressure_key='leadership_legitimacy' AND status='active'",(iid,)).fetchone()
    assert pressure and float(pressure['intensity'])>0
    assert c.execute("SELECT COUNT(*) FROM relationship_history WHERE source_kind='duel' AND source_id=?",(duel,)).fetchone()[0]==2

    # A leader death creates a real vacancy and selects a clearly qualified pre-existing successor.
    iid2=institution(c,'[SUC02] Clear Sect'); old=actor(c,'[SUC02] Old Head','Fifth'); heir=actor(c,'[SUC02] Heir','Fifth'); ordinary=actor(c,'[SUC02] Ordinary','Fifth')
    for aid,role in ((old,'head'),(heir,'designated successor'),(ordinary,'member')):member(c,iid2,aid,role)
    c.execute("INSERT INTO institutional_authority_slots(institution_actor_id,authority_key,authority_kind,incumbent_actor_id,required_stage,status,created_day,metadata_json) VALUES (?,'head','named_incumbent',?,'Fifth','active',0,'{}')",(iid2,old))
    mark_actor_deceased(c,old,reason='test succession')
    slot2=c.execute("SELECT * FROM institutional_authority_slots WHERE institution_actor_id=? AND authority_key='head'",(iid2,)).fetchone()
    assert slot2['status']=='active' and int(slot2['incumbent_actor_id'])==heir,dict(slot2)
    case=c.execute("SELECT * FROM leadership_transition_cases WHERE institution_actor_id=? ORDER BY id DESC LIMIT 1",(iid2,)).fetchone()
    assert case and case['status']=='resolved' and int(case['chosen_actor_id'])==heir
    assert c.execute("SELECT 1 FROM organization_lifecycle_events WHERE institution_actor_id=? AND event_type='leadership_transition'",(iid2,)).fetchone()

    # Equal qualified contenders create a contested/deferred succession and real factions, not a random winner.
    iid3=institution(c,'[SUC02] Contested Sect'); old2=actor(c,'[SUC02] Old Head 2','Fifth'); x=actor(c,'[SUC02] X','Fifth'); y=actor(c,'[SUC02] Y','Fifth')
    for aid,role in ((old2,'head'),(x,'elder'),(y,'elder')):member(c,iid3,aid,role)
    c.execute("INSERT INTO institutional_authority_slots(institution_actor_id,authority_key,authority_kind,incumbent_actor_id,required_stage,status,created_day,metadata_json) VALUES (?,'head','named_incumbent',?,'Fifth','active',0,'{}')",(iid3,old2))
    mark_actor_deceased(c,old2,reason='test contested succession')
    case3=c.execute("SELECT * FROM leadership_transition_cases WHERE institution_actor_id=? ORDER BY id DESC LIMIT 1",(iid3,)).fetchone()
    assert case3 and case3['status']=='deferred' and case3['chosen_actor_id'] is None,dict(case3)
    assert c.execute("SELECT COUNT(*) FROM organization_factions WHERE institution_actor_id=? AND status='active'",(iid3,)).fetchone()[0]>=2
    slot3=c.execute("SELECT * FROM institutional_authority_slots WHERE institution_actor_id=? AND authority_key='head'",(iid3,)).fetchone()
    assert slot3['status']=='vacant' and slot3['incumbent_actor_id'] is None

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError:pass
    print('ORGPRESS-01 / SUCCESSION-02: PASS')

if __name__=='__main__':run()
