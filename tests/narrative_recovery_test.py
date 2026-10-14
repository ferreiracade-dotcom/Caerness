"""Repeatable interrupted-runtime tests. Model replies are stubs, not inference."""
import json
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'tools'))
from planning_demo import fixture
from engine import ai_planning as plans
from engine.planning_gateway import READ_TOOLS,start_request,response_schema
from engine.narrative_runtime import play,resume,read,memory,relevant_history
from engine.narrative_diagnostics import report,classify
from engine.local_model import LocalModelResult,estimate_tokens,set_runtime_config,chat_local,_post_json
from engine.db import connect

def main():
 c,ids=fixture();queue=[];calls=[]
 def model(conn,messages,**kwargs):
  prompt=messages[-1]['content'];import re
  rid=int(re.search(r'"request_id":\s*(\d+)',prompt).group(1))
  calls.append({'request_id':rid,'estimated_prompt_tokens':estimate_tokens(messages),'schema_tokens_estimate':estimate_tokens(kwargs.get('response_schema'))})
  value=queue.pop(0)
  if isinstance(value,Exception):raise value
  if isinstance(value,dict) and value.pop('_pause_after_inference',False):
   from engine.agency import request_interrupt
   request_interrupt(conn)
  if isinstance(value,str):text=value
  else:text=json.dumps({'task_type':'action_interpretation','request_id':rid,'proposal':value})
  return LocalModelResult(text,'stub','explicit-recovery-stub',100,20)
 discuss={'mode':'discuss','text':'[STUB] An ordinary quiet moment.'}
 inspect={'mode':'inspect','calls':[{'tool':'person','arguments':{'actor_id':ids['mara']}}]}
 with patch('engine.model_gateway.chat_local',side_effect=model):
  # Global read catalogue used to grow by seven tools every turn/continuation.
  for _ in range(10):
   req=start_request(c,'I observe the street.',narrative=True)
   payload=json.loads(c.execute('SELECT input_json FROM model_requests WHERE id=?',(req['request_id'],)).fetchone()[0])
   assert len(payload['read_tools'])==len({t['name'] for t in payload['read_tools']})
   assert 'scene' not in {t['name'] for t in payload['read_tools']} and payload['context']['scene']
  assert len(READ_TOOLS)==3
  history=plans.session(c)
  for i in range(40):plans.message(c,history['id'],'assistant','Saved historical line '+str(i))
  window=memory(c,history['id'])
  assert window['omitted_messages']==20 and len(window['excerpts'])==20
  assert any('line 12' in str(m['text']) for m in memory(c,history['id'],query='line 12')['excerpts'])
  anchored=plans.session(c)
  plans.message(c,anchored['id'],'assistant','The pattern is a lattice; I liked its negative space and quiet echo.')
  for i in range(24):plans.message(c,anchored['id'],'assistant','A different topic about ordinary life '+str(i))
  recalled=relevant_history(c,anchored['id'],'What did you like about that original pattern?',memory(c,anchored['id']))
  # First anchors may already include the source; no duplicate is necessary.
  assert not recalled
  more=plans.session(c)
  for i in range(6):plans.message(c,more['id'],'assistant','Early opening '+str(i))
  plans.message(c,more['id'],'assistant','The pattern is a lattice; I liked its negative space and quiet echo.')
  for i in range(24):plans.message(c,more['id'],'assistant','A different topic about ordinary life '+str(i))
  recalled=relevant_history(c,more['id'],'What did you like about that original pattern?',memory(c,more['id']))
  assert len(recalled)==1 and 'lattice' in recalled[0]['text'] and recalled[0]['index']==6
  assert 'not objective world truth' in recalled[0]['authority']
  large={'visible':{'records':['a long public record '*500+'PAGINGTAIL']}}
  req=start_request(c,'Read these records.',provider='local',narrative=True,feedback=[{'tool':'context','arguments':{},'result':large}])
  payload=json.loads(c.execute('SELECT input_json FROM model_requests WHERE id=?',(req['request_id'],)).fetchone()[0])
  assert 'PAGINGTAIL' not in req['packet'] and 'saved_request_id' in req['packet']
  offset=0;pieces=[]
  while True:
   page=read(c,payload['session_id'],'read_result',{'request_id':req['request_id'],'index':0,'path':['visible'],'offset':offset})
   pieces.append(page['text'])
   if not page['more']:break
   offset=page['next_offset']
  assert json.loads(''.join(pieces))==large['visible']
  private=c.execute("INSERT INTO model_requests(day,task_type,provider,target_kind,target_id,input_json) VALUES (0,'action_interpretation','local','ai_session',?,?)",(payload['session_id'],json.dumps({'protocol':'narrative_authoring_review_v1','feedback':[{'result':{'private':'PRIVATE PROMPT SENTINEL'}}]}))).lastrowid
  try:read(c,payload['session_id'],'read_result',{'request_id':private});raise AssertionError('Private reviewer data exposed')
  except ValueError:pass
  for name,text in [('observation','I look around.'),('conversation','To Mara Vale: How is your day?')]:
   queue[:]=[discuss];before=len(calls);out=play(c,text)
   assert out['status']=='discussed' and len(calls)-before==1
   print(name,'one call',calls[-1])
  queue[:]=[inspect,TimeoutError('A timeout containing PRIVATE PROMPT SENTINEL')]
  before=len(calls);out=play(c,'Ask Mara what she remembers.');sid=out['session_id'];rid=out['request_id']
  assert out['failure']['code']=='timeout' and len(calls)-before==2
  prior=c.execute('SELECT status FROM model_requests WHERE id=?',(rid-1,)).fetchone()[0]
  assert prior=='applied' and c.execute('SELECT status FROM model_requests WHERE id=?',(rid,)).fetchone()[0]=='pending'
  blocked=play(c,'A new message that must not overwrite the pending turn.',sid)
  assert blocked['input_not_recorded'] and blocked['request_id']==rid
  assert 'PRIVATE PROMPT SENTINEL' not in json.dumps(report(c))
  c.close();c=connect();queue[:]=[discuss];before=len(calls)
  assert resume(c,rid)['status']=='discussed' and len(calls)-before==1 and calls[-1]['request_id']==rid
  assert len([m for m in json.loads(plans.session(c,sid)['messages_json']) if m['role']=='player'])==1
  try:resume(c,rid);raise AssertionError('Completed turn replayed')
  except ValueError:pass
  print('read continuation timeout + reload + same-request retry, no duplicated input',calls[-3:])
  queue[:]=[{**discuss,'_pause_after_inference':True}];before=len(calls)
  out=play(c,'I pause to listen.');rid=out['request_id']
  assert out['failure']['code']=='interrupted' and c.execute('SELECT status FROM model_requests WHERE id=?',(rid,)).fetchone()[0]=='responded'
  assert resume(c,rid)['status']=='discussed' and len(calls)==before+1
  print('Explicit pause preserves parsed response; resume applies it with zero extra model calls PASS')
  queue[:]=[inspect,inspect];before=len(calls);out=play(c,'Ask Mara about the same records.')
  assert out['failure']['code']=='repeated_read' and len(calls)==before+2 and not queue
  queue[:]=[discuss];assert resume(c,out['request_id'])['status']=='discussed'
  print('Repeated unchanged read stops after two calls; retry does not repeat its engine operation PASS')
  # Malformed successful HTTP content remains retryable, with a distinct error.
  queue[:]=['{not JSON'];out=play(c,'I listen.');assert out['failure']['code']=='invalid_response'
  queue[:]=[discuss];assert resume(c,out['request_id'])['status']=='discussed'
  # An action committed before a failed consequences call must not happen twice.
  text='I decide to remain here for one day.'
  spec={'source_text':text,'summary':'Stay one day','coverage':[{'start':0,'end':len(text),'handling':'planned','step_ids':['time']}],'unresolved':[],'steps':[{'id':'time','operation':'advance_time','arguments':{'days':1},'depends_on':[]}]}
  verdict={'authorized':True,'complete':True,'evidence':[{'start':0,'end':len(text)}],'omissions':[],'reason':'Exact directive.'}
  today=plans.day(c);queue[:]=[{'mode':'plan','plan':spec},verdict,TimeoutError('timed out')]
  out=play(c,text);assert plans.day(c)==today+1 and out['failure']['phase']=='consequences'
  rid=out['request_id'];c.close();c=connect();assert plans.day(c)==today+1
  queue[:]=[discuss];assert resume(c,rid)['status']=='discussed' and plans.day(c)==today+1
  print('Committed day preserved through interruption/reload/retry; no action replay PASS')
  # Oversized context is reported before inference, never silently shortened.
  set_runtime_config(c,device_profile='desktop_free_local',local_backend='openai_compatible',local_max_context_tokens=512,local_heavy_context_tokens=512)
  with patch('engine.model_gateway.chat_local',wraps=__import__('engine.local_model',fromlist=['chat_local']).chat_local):
   out=play(c,'I observe.');assert out['failure']['code']=='context_limit'
  assert classify(ValueError('Model output reached its token limit'))=='incomplete_response'
  memory_error=ConnectionError('No private details');memory_error.code='out_of_memory'
  assert classify(memory_error)=='out_of_memory'
  assert 'PRIVATE PROMPT SENTINEL' not in json.dumps(report(c))
  # Content tokens are not the escaped HTTP-JSON envelope. The latter used to
  # reject a fitting prompt. Structured grammar is not text input to local models.
  messages=[{'role':'user','content':'"quoted"\n'*130}]
  budget=sum(estimate_tokens(m['content'])+8 for m in messages)+64+128
  legacy=estimate_tokens(messages)+128
  assert legacy>budget
  set_runtime_config(c,device_profile='desktop_free_local',local_backend='openai_compatible',local_endpoint='http://127.0.0.1:1234/v1/chat/completions',local_max_context_tokens=512,local_heavy_context_tokens=budget,local_max_output_tokens=128)
  with patch('engine.local_model._post_json',return_value={'choices':[{'message':{'content':'{}'}}]}):
   assert chat_local(c,messages,require_json=True,response_schema={'type':'object'}).text=='{}'
  with patch('engine.local_model._urlopen',side_effect=TimeoutError('private timeout detail')):
   try:_post_json('http://127.0.0.1:1234/v1/chat/completions',{},1,local_only=True);raise AssertionError('Timeout was hidden')
   except TimeoutError as error:assert str(error)=='Model request timed out.'
  import io,urllib.error
  failure=urllib.error.HTTPError('http://127.0.0.1:1234',500,'Error',{},io.BytesIO(b'CUDA out of memory PRIVATE PROMPT SENTINEL'))
  with patch('engine.local_model._urlopen',side_effect=failure):
   try:_post_json('http://127.0.0.1:1234/v1/chat/completions',{},1,local_only=True);raise AssertionError('Memory failure was hidden')
   except ConnectionError as error:assert error.code=='out_of_memory' and 'PRIVATE PROMPT SENTINEL' not in str(error)
 print('NARRATIVE RECOVERY PASS: all inference replies above were explicit stubs.')
 c.close()

if __name__=='__main__':main()
