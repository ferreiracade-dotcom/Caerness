"""HARM-01: violence projects once into health/death with provenance and controlled-risk separation."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, SCHEMA_VERSION
from engine.household_life import set_life_profile
from engine.health import ensure_health_profile
from engine.harm import record_harm
from engine.combat import create_duel, resolve_duel_exchange


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_harm01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); return connect(),path


def actor(c,name):
    aid=int(c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')",(name,)).lastrowid)
    set_life_profile(c,aid,birth_day=-30*365,demographic_sex='male',family_formation_eligible=True)
    ensure_health_profile(c,aid,baseline_health=80)
    return aid


def run():
    assert SCHEMA_VERSION>=105
    c,path=bootstrap()
    a=actor(c,'[H01] A'); b=actor(c,'[H01] B'); c_actor=actor(c,'[H01] C')

    # Controlled low harm is never immediately fatal and is idempotent by source provenance.
    h1=record_harm(c,a,source_kind='test_controlled',source_ref_id=1,severity=18,intent_class='controlled',harm_kind='sparring',exposure=35)
    assert h1['outcome'] in {'transient','persistent'} and int(h1['fatal'])==0
    h1b=record_harm(c,a,source_kind='test_controlled',source_ref_id=1,severity=99,intent_class='controlled',harm_kind='sparring',exposure=100)
    assert int(h1b['id'])==int(h1['id'])

    # Authoritative serious wound becomes a real health condition with exact harm provenance.
    h2=record_harm(c,b,source_kind='test_ambush',source_ref_id=2,severity=82,intent_class='hostile',harm_kind='blade',exposure=90,outcome_override='persistent')
    assert h2['condition_id'] is not None and h2['outcome']=='persistent'
    cond=c.execute("SELECT * FROM health_conditions WHERE id=?",(h2['condition_id'],)).fetchone()
    assert cond and int(__import__('json').loads(cond['metadata_json'])['source_harm_incident_id'])==int(h2['id'])

    # Known lethal casualty flows through the same interface and records death once.
    h3=record_harm(c,c_actor,source_kind='test_lethal',source_ref_id=3,severity=100,intent_class='lethal',harm_kind='battle',exposure=100,outcome_override='fatal')
    assert h3['outcome']=='fatal' and int(c.execute("SELECT fatal FROM harm_incidents WHERE id=?",(h3['id'],)).fetchone()[0])==1
    assert c.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?",(c_actor,)).fetchone()[0]=='deceased'

    # Controlled duel resolution automatically projects final HARM-01 rows for both fighters.
    d1=actor(c,'[H01] Duel A'); d2=actor(c,'[H01] Duel B')
    duel=create_duel(c,'[H01] controlled duel',d1,d2,stakes=2,capability_a=85,capability_b=45,metadata={'nonlethal':True})
    result=None
    for _ in range(30):
        result=resolve_duel_exchange(c,duel)
        if result.get('status')=='resolved': break
    assert result and result.get('status')=='resolved',result
    harms=c.execute("SELECT * FROM harm_incidents WHERE source_kind='duel' AND source_ref_id=? ORDER BY actor_id",(duel,)).fetchall()
    assert len(harms)==2 and all(str(x['intent_class'])=='controlled' and not int(x['fatal']) for x in harms)
    assert all(c.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?",(int(x['actor_id']),)).fetchone()[0]=='living' for x in harms)

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError:pass
    print('HARM-01 shared consequence projection: PASS')

if __name__=='__main__': run()
