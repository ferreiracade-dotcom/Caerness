"""Paired native-world benchmark with four long-running planning fixtures, no model."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))

def setup(path):
 os.environ['CAERNESS_DB_PATH']=str(path)
 from planning_demo import fixture
 from engine.health import ensure_health_profile
 from engine.civilian import create_project
 from engine.ai_planning import ensure_schema,session,draft_plan
 from engine.world_capabilities import dump,digest
 c,ids=fixture();ensure_schema(c);sid=session(c)['id'];loc=c.execute('SELECT current_location_id FROM actors WHERE id=?',(ids['owner'],)).fetchone()[0]
 for i in range(4):
  person=c.execute("INSERT INTO actors(name,actor_type,subtype,current_location_id,status,is_demo) VALUES (?,'character','benchmark craft worker',?,'active',1)",(f'[DEMO] Benchmark worker {i}',loc)).lastrowid
  ensure_health_profile(c,person)
  domain=c.execute("SELECT id FROM competence_domains WHERE domain_key='craft'").fetchone()[0]
  c.execute('INSERT INTO actor_competence(actor_id,domain_id,score) VALUES (?,?,75)',(person,domain))
  project=create_project(c,f'[DEMO] Benchmark ongoing work {i}','architecture',creator_actor_id=person,patron_actor_id=ids['institution'],location_id=loc,target_day=3650,funding=100,material_access=100,skilled_labor=75,metadata={'site_id':ids['yard']})
  eng=c.execute("INSERT INTO service_engagements(client_institution_actor_id,provider_kind,provider_id,domain_key,service_kind,scope_json,started_day,status) VALUES (?,'actor',?,'craft','benchmark','{}',0,'active')",(ids['institution'],person)).lastrowid
  # Tracking-only fixtures, not player interpretation or gameplay intelligence evidence.
  step={'id':'work','operation':'commission_work','arguments':{'institution_id':ids['institution'],'allocation_id':1,'engagement_id':eng,'offering_id':ids['build'],'quotation_digest':ids['build_digest'],'site_id':ids['yard'],'title':f'Benchmark {i}'},'depends_on':[]}
  spec={'source_text':'Benchmark tracking fixture','summary':'Track existing native work','coverage':[{'start':0,'end':26,'handling':'planned','step_ids':['work']}],'unresolved':[],'steps':[step]}
  view=draft_plan(c,sid,spec['source_text'],spec);pid=view['id']
  c.execute("UPDATE ai_plans SET status='active',approved_digest=digest WHERE id=?",(pid,))
  c.execute("UPDATE ai_plan_steps SET status='active',result_json=? WHERE plan_id=?",(dump({'state':'active','project_id':project,'summary':'Benchmark native work'}),pid))
  c.execute('INSERT INTO ai_work_links(project_id,plan_id,site_id,offering_id,service_engagement_id) VALUES (?,?,?,?,?)',(project,pid,ids['yard'],ids['build'],eng))
 c.commit();c.close()

def run(path,days,tracking):
 os.environ['CAERNESS_DB_PATH']=str(path)
 from engine.db import connect
 from engine.simulation import advance_connection
 import cProfile,pstats
 with connect() as c:
  if not tracking:c.execute('DELETE FROM ai_work_links');c.execute('DELETE FROM ai_plan_events');c.execute('DELETE FROM ai_plan_steps');c.execute('DELETE FROM ai_plans');c.commit()
  initial=c.execute("SELECT COUNT(*) FROM ai_plans WHERE status='active'").fetchone()[0]
  profiler=cProfile.Profile();start=time.perf_counter();profiler.enable();advance_connection(c,days);profiler.disable();elapsed=time.perf_counter()-start;c.commit()
  stats=pstats.Stats(profiler)
  planning=sum(v[3] for k,v in stats.stats.items() if k[0].endswith('ai_planning.py') and k[2]=='process_due_planning')
  calls=sum(v[0] for k,v in stats.stats.items() if k[0].endswith('ai_planning.py') and k[2]=='process_due_planning')
  native=[tuple(r) for r in c.execute('SELECT id,status,current_location_id FROM actors ORDER BY id')]+[tuple(r) for r in c.execute('SELECT id,status,progress FROM civilian_projects ORDER BY id')]+[tuple(r) for r in c.execute('SELECT day,event_type,title,summary FROM events ORDER BY id')]
  import hashlib
  fingerprint=hashlib.sha256(json.dumps(native,sort_keys=True).encode()).hexdigest()
  return {'native_fingerprint':fingerprint,'days':days,'tracking':tracking,'wall_seconds':round(elapsed,3),'planning_cumulative_seconds':round(planning,3),'planning_review_calls':calls,'initial_active_plans':initial,'final_active_plans':c.execute("SELECT COUNT(*) FROM ai_plans WHERE status='active'").fetchone()[0],'final_day':c.execute('SELECT current_day FROM world_state').fetchone()[0]}

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--late-repeat',action='store_true');a=p.parse_args()
 out=[]
 with tempfile.TemporaryDirectory(prefix='caerness-active-bench-') as tmp:
  base=Path(tmp)/'base.db';setup(base)
  for age in ((1095,) if a.late_repeat else (0,1095)):
   aged=Path(tmp)/f'age{age}.db';shutil.copy2(base,aged)
   if age:
    os.environ['CAERNESS_DB_PATH']=str(aged)
    from engine.db import connect
    from engine.simulation import advance_connection
    with connect() as c:advance_connection(c,age);c.commit()
   for days in ((90,90) if a.late_repeat else (90,365)):
    pair=[]
    for tracking in (False,True):
     copy=Path(tmp)/f'{age}-{days}-{tracking}.db';shutil.copy2(aged,copy)
     r=run(copy,days,tracking);r['save_age_days']=age;out.append(r);pair.append(r);print(json.dumps(r),flush=True)
    pair[1]['relative_overhead_percent']=round((pair[1]['wall_seconds']/pair[0]['wall_seconds']-1)*100,1)
    Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps({'label':'four active tracking fixtures; cProfile on both; not a phone benchmark','measurements':out},indent=2))
if __name__=='__main__':main()
