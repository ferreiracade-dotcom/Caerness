"""Live-model acceptance recorder. Never synthesizes model replies or structured plans.

Uses existing opening people/history, isolated saves, actual HTTP model requests and
engine audits. Inaccessibility produces BLOCKED gates, not simulated gameplay.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

CONVERSATION=[
 'It has been a long time since we had a quiet conversation. How have you been?',
 'What do you remember most clearly about our early acquaintance?',
 'I remember feeling less certain of myself then. Did it show?',
 'You need not flatter me. What was difficult about knowing me?',
 'That is fair. I can laugh about some of it now.',
 'Let us change the subject. What is ordinary life here like these days?',
 'What have you actually heard, and what are people merely guessing?',
 'Does that concern you, or is it just part of the routine?',
 'I sometimes miss having fewer responsibilities.',
 'Would you rather have a peaceful life or a chance at something larger?',
 'I am not making an offer. I am curious about your answer.',
 'And what would you refuse, even if it looked advantageous?',
 'You sound rather different when we speak privately.',
 'What do you think I have misunderstood about this place?',
 'Tell me something small rather than a grand history.',
 'Do you remember what I said earlier about uncertainty?',
 'I did not mean I regretted everything. There have been good years too.',
 'Thank you for listening. We do not have to solve anything today.',
 'Perhaps we can sit quietly for a moment and watch people go about their work.',
 'Before we part, is there anything you wanted to ask me?',
]
OTHER={
 'B':['I would like to arrange a practical exchange of local experience: someone who understands the roads could prepare a short account for people who teach young travellers. First find out who is actually available and what I can legitimately promise. Do not spend money or promise positions without telling me the terms.'],
 'C':['I have decided to remain here for ninety days, letting any agreed undertakings continue. Do not claim that remaining here will finish them.', 'I return to our conversation. What has actually changed since we last spoke? Distinguish what you know from what you only suspect.'],
 'D':['I pause and take in the ordinary surroundings, without looking for trouble.', 'I greet someone who is actually nearby and ask about their day.', 'What nearby places can I reach by the established roads?', 'I would like to investigate the most ordinary, mildly interesting thing I can actually see. Do not invent a mystery.', 'I decide to rest here for two days.'],
}

def audit(c):
 return {'day':c.execute('SELECT current_day FROM world_state').fetchone()[0],
         'player_location':c.execute('SELECT current_location_id FROM player_state').fetchone()[0],
         'events':c.execute('SELECT COUNT(*) FROM events').fetchone()[0],
         'interactions':c.execute('SELECT COUNT(*) FROM interactions').fetchone()[0],
         'resources':[dict(r) for r in c.execute('SELECT actor_id,resource_type,amount FROM resources ORDER BY actor_id,resource_type')],
         'active_projects':[dict(r) for r in c.execute('SELECT id,status,progress FROM civilian_projects ORDER BY id')],
         'plans':[dict(r) for r in c.execute('SELECT id,status,digest FROM ai_plans ORDER BY id')] if c.execute("SELECT 1 FROM sqlite_master WHERE name='ai_plans'").fetchone() else []}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--player');p.add_argument('--npc');p.add_argument('--approve-reviewed',action='store_true',help='Test-player approval of complete, displayed scopes; no approval of unresolved scopes.')
 a=p.parse_args();out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True);save=out/'session.db'
 if save.exists():p.error('Use a fresh output directory to preserve prior evidence.')
 shutil.copy2(ROOT/'data/caerness.db',save);os.environ['CAERNESS_DB_PATH']=str(save)
 from engine.db import connect,init_db
 from engine.player import set_player
 from engine.local_model import local_health,runtime_config
 from engine.model_gateway import set_model_config
 from engine.narrative_runtime import play,person,after_execution
 from engine.planning_gateway import run_local
 from engine.ai_planning import approve_plan
 init_db()
 with connect() as c:
  set_model_config(c,packet_dir=str(out/'packets'))
  row=c.execute("SELECT a.id owner,a.name owner_name,b.id npc,b.name npc_name,r.started_day FROM relationships r JOIN actors a ON a.id=r.actor_a_id JOIN actors b ON b.id=r.actor_b_id WHERE a.actor_type='character' AND b.actor_type='character' AND a.status='active' AND b.status='active' AND a.current_location_id=b.current_location_id AND r.familiarity>=50 AND (? IS NULL OR a.name=?) AND (? IS NULL OR b.name=?) ORDER BY r.started_day,a.id LIMIT 1",(a.player,a.player,a.npc,a.npc)).fetchone()
  if not row:p.error('No co-located established pair matches. Select a different existing player/NPC; do not invent a history.')
  set_player(c,row['owner'],'Live narrative evaluation');c.commit()
  health=local_health(c)
  manifest={'real_model_available':health['ok'],'model':runtime_config(c)['local_model'],'health':health,'pair':dict(row),'opening_sha256':hashlib.sha256((ROOT/'data/caerness.db').read_bytes()).hexdigest(),'gates':{},'scripted_responses':False}
  if not health['ok']:
   # Try actual inference too: an arbitrary authenticated server might not support /models.
   result=play(c,'I pause to look around and consider starting a quiet conversation.')
   c.commit()
   if result['status']=='external_recommended':
    for gate in ('A','B','C','D'):manifest['gates'][gate]={'status':'BLOCKED','reason':'No reachable configured model; no real-model gameplay evaluated.'}
    manifest['inference_attempt']={'status':result['status'],'reason':result.get('reason')}
    (out/'evaluation.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2));return
   manifest['real_model_available']=True
  sid=None;transcript=[]
  for gate,inputs in [('A',CONVERSATION),*OTHER.items()]:
   records=[]
   for text in inputs:
    if gate=='A':text=f'To {row["npc_name"]}: '+text
    before=audit(c);start=time.perf_counter();first=c.execute('SELECT COALESCE(MAX(id),0) FROM model_requests').fetchone()[0]
    result=play(c,text,sid);sid=result['session_id'];record={'test':gate,'player':text,'before':before,'result':result,'wall_seconds':round(time.perf_counter()-start,3)}
    if result['status']=='awaiting_plan_review' and a.approve_reviewed and result.get('verification',{}).get('complete') and not result['plan']['unresolved']:
     view=result['plan'];record['test_player_review']={'original':view['original_instruction'],'engine_scope':view['review_scope'],'decision':'Approve exactly the displayed complete scope.'}
     committed=approve_plan(c,view['id'],view['digest']);queued=after_execution(c,committed)
     if queued.get('next_request'):result=run_local(c,queued['next_request']['request_id'],force=True)
     record['after_review']=result
    c.commit();record['after']=audit(c)
    record['model_requests']=[dict(r) for r in c.execute('SELECT id,input_json,response_json,status,applied_summary FROM model_requests WHERE id>? ORDER BY id',(first,))]
    record['model_latency']=[dict(r) for r in c.execute('SELECT request_id,latency_seconds,prompt_tokens,completion_tokens FROM ai_model_calls WHERE request_id>? ORDER BY id',(first,))] if c.execute("SELECT 1 FROM sqlite_master WHERE name='ai_model_calls'").fetchone() else []
    records.append(record);transcript.append(record)
    (out/'transcript.json').write_text(json.dumps(transcript,indent=2))
    print(gate,result['status'],round(time.perf_counter()-start,2),flush=True)
    if result['status']=='external_recommended':break
   manifest['gates'][gate]={'status':'RECORDED_REQUIRES_QUALITATIVE_REVIEW','turns':len(records)}
  c.commit()
 (out/'evaluation.json').write_text(json.dumps(manifest,indent=2))
 with connect() as c:(out/'reload-state.json').write_text(json.dumps(audit(c),indent=2))
if __name__=='__main__':main()
