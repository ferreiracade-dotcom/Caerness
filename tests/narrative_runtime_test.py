"""Scripted HTTP integration only. Never claimed as real-model literary evaluation."""
import json
import os
import re
import sys
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'tools'))
from planning_demo import fixture,composed_spec,EXAMPLES
from engine import ai_planning as plans
from engine.narrative_runtime import play,person,memory,scene
from engine.local_model import set_runtime_config,runtime_config,chat_local,local_health
from engine.model_gateway import import_response,apply_model_request
from engine.planning_gateway import start_request


def main():
 c,ids=fixture(); packets=[]; auth=[]; responses=[]
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   auth.append(self.headers.get('Authorization'))
   self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[]}')
  def do_POST(self):
   auth.append(self.headers.get('Authorization')); data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
   prompt=data['messages'][-1]['content'];packets.append(prompt)
   rid=int(re.search(r'"request_id":\s*(\d+)',prompt).group(1))
   prop=responses.pop(0)
   if 'http_error' in prop:
    self.send_response(prop['http_error']);self.end_headers();return
   response={'task_type':'action_interpretation','request_id':rid,'proposal':prop}
   body=json.dumps({'choices':[{'message':{'content':json.dumps(response)}}],'usage':{'prompt_tokens':100,'completion_tokens':20}}).encode()
   self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  set_runtime_config(c,local_backend='openai_compatible',local_endpoint=f'http://127.0.0.1:{server.server_port}/v1/chat/completions',local_model='explicit-narrative-test-stub',local_max_context_tokens=32000,local_heavy_context_tokens=40000)
  # Secret is transport-only; do not print it or persist it in configs, requests, speech.
  with patch.dict(os.environ,{'CAERNESS_MODEL_API_KEY':'test-secret-not-real'}):
   assert local_health(c)['ok']
   before=c.execute('SELECT COUNT(*) FROM interactions').fetchone()[0];today=plans.day(c)
   sid=None
   for i in range(20):
    responses[:]=[{'mode':'inspect','calls':[{'tool':'person','arguments':{'actor_id':ids['mara']}}]}, {'mode':'discuss','text':f'[SCRIPTED] Mara replies conversationally, exchange {i}.'}]
    out=play(c,'Let us talk about our old journeys and then the ordinary market.' if i==0 else f'Follow-up {i}: What do you think about that?',sid)
    assert out['status']=='discussed',out
    sid=out['session_id']
   assert plans.day(c)==today and c.execute('SELECT COUNT(*) FROM interactions').fetchone()[0]==before
   assert 'participants' in packets[-1] and 'Mara Vale' in packets[-1]
   assert memory(c,sid,offset=0)['excerpts'][0]['text'].startswith('Let us talk')
   plans.message(c,sid,'player','Please remember the green ribbon, a recollection rather than a verified possession.')
   for i in range(40):plans.message(c,sid,'assistant','A quiet ordinary exchange '+str(i))
   assert any('green ribbon' in str(x['text']) for x in memory(c,sid,query='green ribbon')['excerpts'])
   c.commit(); from engine.db import connect
   c.close();c=connect();assert len(json.loads(plans.session(c,sid)['messages_json']))>=81
   print('20 conversational HTTP exchanges + old source retrieval + reload, without social rolls/time/commitments PASS (scripted responses)')
   assert auth and all(x=='Bearer test-secret-not-real' for x in auth)
   assert 'test-secret-not-real' not in '\n'.join(packets)+json.dumps(runtime_config(c))
  # Explicit directive vs hypothetical uses independent verification, never regex recognition.
  def timespec(source,days=2):
   return {'source_text':source,'summary':'Pass time','coverage':[{'start':0,'end':len(source),'handling':'planned','step_ids':['time']}],'unresolved':[],'steps':[{'id':'time','operation':'advance_time','arguments':{'days':days},'depends_on':[]}]}
  text='I will rest here for two days.'
  responses[:]=[{'mode':'plan','plan':timespec(text)}, {'authorized':True,'complete':True,'evidence':[{'start':0,'end':len(text)}],'omissions':[],'reason':'A clear current directive.'}, {'mode':'discuss','text':'[SCRIPTED] Two days pass; your conversations remain saved.'}]
  out=play(c,text);assert out['status']=='discussed',out;assert plans.day(c)==today+2
  assert c.execute("SELECT 1 FROM ai_plan_events WHERE kind='conversational_authorization'").fetchone()
  print('Routine directive → independent scope verification → automatic native time → post-state narration PASS')
  text='What if I stayed here for two days?'
  responses[:]=[{'mode':'plan','plan':timespec(text)}, {'authorized':False,'complete':True,'evidence':[],'omissions':[],'reason':'Hypothetical discussion.'}]
  out=play(c,text);assert out['status']=='awaiting_plan_review';assert plans.day(c)==today+2
  print('Hypothetical plan does not authorize or advance time PASS')
  # 100% source coverage but irrelevant operation: span checker cannot prove semantics.
  text='Give Mara my black horse and wait two days.'
  spec=timespec(text);spec['coverage'][0]['handling']='context';spec['coverage'][0]['step_ids']=[]
  plans.check_spec(spec,text) # Deliberate counterexample to syntactic completeness.
  responses[:]=[{'mode':'plan','plan':spec},{'authorized':False,'complete':False,'evidence':[],'omissions':['The black horse gift is not in the executable scope.'],'reason':'Incomplete.'}]
  out=play(c,text);p=out['plan'];assert out['verification']['omissions'] and plans.day(c)==today+2
  try:plans.approve_plan(c,p['id'],p['digest']);raise AssertionError('Incomplete scope committed')
  except ValueError:pass
  print('Fully covered but semantically incomplete plan remains unexecuted, including direct approval bypass PASS')
  text=EXAMPLES['survey']['text'];responses[:]=[{'mode':'plan','plan':composed_spec(ids,'survey')},{'authorized':True,'complete':True,'evidence':[{'start':0,'end':len(text)}],'omissions':[],'reason':'Full directive.'}]
  out=play(c,text);assert out['status']=='awaiting_plan_review';assert not c.execute('SELECT 1 FROM institutional_roles').fetchone()
  print('Durable delegation and budget retain meaningful review PASS')
  # Scoped person history must not leak globally known or hidden history.
  secret=c.execute("INSERT INTO events(day,event_type,title,summary,severity) VALUES (0,'test','SECRET NEVER KNOWN','HIDDEN SENTINEL',1)").lastrowid
  c.execute("INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,truth_event_id,learned_day) VALUES (?,?,?,1,?,0)",(ids['mara'],'private-test','Hidden',secret))
  assert 'HIDDEN SENTINEL' not in json.dumps(person(c,ids['owner'],ids['mara']))
  try:person(c,ids['owner'],1);raise AssertionError('Absent person accessible')
  except ValueError:pass
  # Native travel uses same general plan and no phrase parsing.
  loc=c.execute('SELECT current_location_id FROM actors WHERE id=?',(ids['owner'],)).fetchone()[0]
  dest=c.execute("INSERT INTO locations(name,kind) VALUES ('[DEMO] Adjacent market','settlement')").lastrowid
  c.execute('INSERT INTO location_links(location_a_id,location_b_id,travel_days) VALUES (?,?,1)',(loc,dest))
  text='I take the road to the adjacent market.';spec=timespec(text);spec['steps'][0].update(operation='travel',arguments={'destination_id':dest})
  responses[:]=[{'mode':'plan','plan':spec},{'authorized':True,'complete':True,'evidence':[{'start':0,'end':len(text)}],'omissions':[],'reason':'Exact current directive.'},{'mode':'discuss','text':'[SCRIPTED] You arrive at the market.'}]
  out=play(c,text);assert out['status']=='discussed',out
  assert c.execute('SELECT current_location_id FROM actors WHERE id=?',(ids['owner'],)).fetchone()[0]==dest
  assert plans.day(c)==today+3
  print('Scoped established travel → native shared world time/arrival → narration PASS')
  print('Credential transport, private history exclusion and native travel PASS')
  text='I decide to stay here for one day.'
  responses[:]=[{'mode':'plan','plan':timespec(text,1)},{'authorized':True,'complete':True,'evidence':[{'start':0,'end':len(text)}],'omissions':[],'reason':'Explicit directive.'},{'http_error':503}]
  out=play(c,text);assert out['status']=='external_recommended'
  assert plans.day(c)==today+4
  request=c.execute('SELECT input_json,status FROM model_requests WHERE id=?',(out['request_id'],)).fetchone()
  assert json.loads(request[0])['phase']=='consequences' and request[1]=='pending'
  c.commit();c.close();c=connect();assert plans.day(c)==today+4
  import_response(c,out['request_id'],json.dumps({'task_type':'action_interpretation','request_id':out['request_id'],'proposal':{'mode':'discuss','text':'[SCRIPTED] The confirmed day has passed.'}}))
  assert apply_model_request(c,out['request_id'])['status']=='discussed'
  assert plans.day(c)==today+4
  print('Narration service failure preserves confirmed consequences and resumable response without replay PASS')
  metrics=[dict(r) for r in c.execute('SELECT COUNT(*) calls,SUM(latency_seconds) seconds FROM ai_model_calls')]
  print('Explicit HTTP stub transport timing (not real model latency): '+json.dumps(metrics))
  print('NARRATIVE RUNTIME INTEGRATION PASS; real-model reasoning/literary acceptance remains UNTESTED')
 finally:server.shutdown();server.server_close();thread.join(timeout=2);c.close()
if __name__=='__main__':main()
