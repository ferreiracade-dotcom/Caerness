from __future__ import annotations
import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.health import ensure_health_profile
from engine.cultivation import (
    process_due_cultivation,_opening_depth_calibration,_realization_aptitude,_vessel_aptitude,
    _next_check_day,CORE_CAPACITY,LONGEVITY,
)

SCENARIOS={
    'sella': {'name':'[SIM] Sella Marrin','age':24,'stage':'Temper','location':'Waymeet','seed':9102,'resource':60.0,'institution':None,
              'basis':'Established Long Road professional in the Churn; Temper is the neutral opening state.'},
    'tobin': {'name':'[SIM] Tobin Verra','age':23,'stage':'Temper','location':'Wrenfield seat district','seed':9103,'resource':65.0,'institution':'Wrenfield Sect',
              'basis':'Normally trained Wrenfield developing disciple; Temper is ordinary at opening.'},
    'ansel': {'name':'[SIM] Ansel Rooke','age':31,'stage':'Temper','location':'Northwatch','seed':9104,'resource':60.0,'institution':None,
              'basis':'Established Dunmoor retainer; Temper is the more ordinary mature-professional outer level.'},
}

def run_one(key:str,out_dir:Path):
    cfg=SCENARIOS[key]; db=out_dir/f'{key}.db'; os.environ['CAERNESS_DB_PATH']=str(db)
    reset_db(force=True);init_db();c=connect();c.execute('UPDATE world_state SET rng_seed=? WHERE id=1',(cfg['seed'],));import_current_seed(c);activate_existing_loops(c)
    lid=int(c.execute('SELECT id FROM locations WHERE name=?',(cfg['location'],)).fetchone()[0])
    cur=c.execute("INSERT INTO actors(name,actor_type,status,current_location_id) VALUES (?,'character','active',?)",(cfg['name'],lid));aid=int(cur.lastrowid)
    birth=-int(cfg['age']*365)
    c.execute("INSERT INTO actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) VALUES (?,?, 'adult',1,'living',0,?)",
              (aid,birth,json.dumps({'authority':'V0_56_CALIBRATION'})))
    ensure_health_profile(c,aid,longevity_class=LONGEVITY[cfg['stage']])
    if cfg['institution']:
        inst=int(c.execute('SELECT id FROM actors WHERE name=?',(cfg['institution'],)).fetchone()[0])
        c.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json) VALUES (?,?,?,'developing disciple','active',-1825,'{}','{}')",
                  (inst,aid,'disciple'))
    va=_vessel_aptitude(c,aid);ra=_realization_aptitude(c,aid)
    vessel,real,_=_opening_depth_calibration(c,aid,cfg['stage'],cfg['age'],va,ra)
    cap=CORE_CAPACITY[cfg['stage']]
    c.execute("""INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,
              training_effort,resource_access,teacher_support,injury_constraint,realization_aptitude,vessel_aptitude,next_realization_check_day,
              core_capacity,current_reserve,sediment_burden,observed_stage_days,plateau_days,last_review_day,next_review_day,status,metadata_json)
              VALUES (?,'Open-Core',?,1,?,?,70,?,20,0,?,?,180,?, ?,0,0,0,0,30,'active',?)""",
              (aid,cfg['stage'],vessel,real,cfg['resource'],ra,va,cap,cap*.6,json.dumps({'basis':cfg['basis'],'attainment_day':'UNKNOWN'})))
    c.execute('UPDATE cultivation_profiles SET next_realization_check_day=? WHERE actor_id=?',(_next_check_day(c,aid,0,cfg['stage']),aid))
    snapshots=[]
    for year in range(1,11):
        target=365*year
        while int(c.execute('SELECT current_day FROM world_state WHERE id=1').fetchone()[0])<target:
            now=int(c.execute('SELECT current_day FROM world_state WHERE id=1').fetchone()[0]); day=min(target,now+30)
            c.execute('UPDATE world_state SET current_day=? WHERE id=1',(day,));process_due_cultivation(c,day)
        p=c.execute('SELECT current_stage,vessel_adaptation,realization_integration,teacher_support FROM cultivation_profiles WHERE actor_id=?',(aid,)).fetchone()
        snapshots.append({'year':year,'age':cfg['age']+year,'stage':p['current_stage'],'vessel':round(float(p['vessel_adaptation']),2),'realization':round(float(p['realization_integration']),2),'teacher_support':round(float(p['teacher_support']),2)})
    histories=[]
    for r in c.execute("SELECT day,history_kind,stage_before,stage_after,metadata_json FROM cultivation_history WHERE actor_id=? AND history_kind IN ('breakthrough_attempt','breakthrough_success','breakthrough_failure','realization_opportunity') ORDER BY day,id",(aid,)):
        histories.append({'day':int(r['day']),'kind':r['history_kind'],'before':r['stage_before'],'after':r['stage_after'],'metadata':json.loads(r['metadata_json'])})
    final=c.execute('SELECT current_stage,vessel_adaptation,realization_integration FROM cultivation_profiles WHERE actor_id=?',(aid,)).fetchone()
    out={'scenario':key,'actor':cfg['name'],'opening_age':cfg['age'],'opening_stage':cfg['stage'],'basis':cfg['basis'],'vessel_aptitude':va,'realization_aptitude':ra,
         'final_stage':final['current_stage'],'final_age':cfg['age']+10,'snapshots':snapshots,'breakthrough_history':histories}
    (out_dir/f'{key}_report.json').write_text(json.dumps(out,indent=2,sort_keys=True));c.close();return out

if __name__=='__main__':
    out=ROOT/'diagnostics'/'v56_focus';out.mkdir(parents=True,exist_ok=True)
    reports=[run_one(k,out) for k in SCENARIOS]
    print(json.dumps([{k:v for k,v in r.items() if k in ('scenario','opening_stage','final_stage','final_age','vessel_aptitude','realization_aptitude')} for r in reports],indent=2))
