"""Mock HTTP integration, NOT live inference or literary-quality evidence."""
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'tools'))
from planning_demo import fixture
from engine import ai_providers as providers
from engine import ai_planning as plans
from engine.local_model import chat_local,runtime_config,set_runtime_config,_post_json,_headers
from engine.narrative_runtime import play,resume
from engine.narrative_diagnostics import report
from engine.db import connect

FREE='example/narrator:free'
def catalogs(url,**kw):
    if 'api.groq.com' in url:return json.dumps({'data':[{'id':'openai/gpt-oss-120b'},{'id':'not-reviewed'}]})
    if 'docs/pricing' in url:
        return '<h2 id="gemini-3.8-flash">Flash</h2><table><tr><td>Input price</td><td>Free of charge</td><td>$1</td></tr><tr><td>Output price (including thinking tokens)</td><td>Free of charge</td><td>$2</td></tr></table><h2 id="gemini-4-argon">Paid</h2><table><tr><td>Input price</td><td>Not available</td></tr></table>'
    if 'googleapis.com' in url:return json.dumps({'models':[{'name':'models/gemini-3.8-flash','inputTokenLimit':1048576,'outputTokenLimit':65536,'supportedGenerationMethods':['generateContent']},{'name':'models/gemini-4-argon','inputTokenLimit':1048576,'outputTokenLimit':65536,'supportedGenerationMethods':['generateContent']}]})
    if 'openrouter' in url:return json.dumps({'data':[
        {'id':FREE,'pricing':{'prompt':'0','completion':'0','request':'0'},'context_length':32000,'supported_parameters':['response_format','structured_outputs']},
        {'id':'paid:free','pricing':{'prompt':'0.01','completion':'0'},'context_length':32000,'supported_parameters':['response_format']},
        {'id':'extra-fee:free','pricing':{'prompt':'0','completion':'0','request':'1'},'context_length':32000,'supported_parameters':['response_format']},
        {'id':'missing-price:free','pricing':{},'context_length':32000,'supported_parameters':['response_format']},
        {'id':'no-json:free','pricing':{'prompt':'0','completion':'0'},'context_length':32000,'supported_parameters':[]}]})
    raise AssertionError(url)

def main():
    c,ids=fixture();seen=[];queue=[]
    secret='private-provider-key-SENTINEL'
    from engine.planning_gateway import response_schema
    shape=response_schema(7,{'protocol':'narrative_play_v1','read_tools':[{'name':'context'},{'name':'person'}],'capabilities':[{'name':'advance_time'}]})
    converted=providers.groq_schema(providers.provider_schema(shape))
    seen_modes=[]
    for branch in converted['properties']['proposal']['anyOf']:
        modes=branch['properties']['mode']['enum'];assert not set(modes)&set(seen_modes);seen_modes+=modes
    cfg={'device_profile':'desktop_free_cloud_groq'}
    decoded=json.loads(providers.decode_response(cfg,json.dumps({'task_type':'action_interpretation','request_id':7,'proposal':{'mode':'discuss','text':'Ordinary talk','details':[]}}),shape))
    assert set(decoded['proposal'])=={'mode','text'}
    for wire in ('[]','{bad','{"actor_id":1,"actor_id":2}','{"value":NaN}','{"value":Infinity}'):
        try:providers.decode_response(cfg,json.dumps({'task_type':'action_interpretation','request_id':7,'proposal':{'mode':'inspect','calls':[{'tool':'person','arguments':wire}]}}),shape);raise AssertionError('Bad encoded arguments accepted')
        except providers.ProviderError:pass
    context=json.loads(providers.decode_response(cfg,json.dumps({'task_type':'action_interpretation','request_id':7,'proposal':{'mode':'inspect','calls':[{'tool':'context','arguments':{'institution_id':1}}]}}),shape))
    assert context['proposal']['calls'][0]['arguments']=={'institution_id':1}
    class MockProvider(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append({'headers':dict(self.headers),'payload':payload})
            value=queue.pop(0)
            if isinstance(value,tuple):
                status,body=value;self.send_response(status);self.send_header('retry-after','2')
                if 300<=status<400:self.send_header('Location',f'http://127.0.0.1:{self.server.server_port}/credential-leak')
                self.end_headers();self.wfile.write(json.dumps(body).encode());return
            rid=re.search(r'"request_id":\s*(\d+)',payload['messages'][-1]['content'])
            if isinstance(value,str):text=value
            else:
                if payload.get('response_format',{}).get('json_schema',{}).get('strict'):
                    value=dict(value)
                    if value.get('mode')=='inspect':value['calls']=[{**call,'arguments':json.dumps(call['arguments'])} for call in value['calls']]
                    if value.get('mode')=='plan':value['plan']={**value['plan'],'steps':[{**step,'arguments':json.dumps(step['arguments'])} for step in value['plan']['steps']]}
                text=json.dumps({'task_type':'action_interpretation','request_id':int(rid.group(1)),'proposal':value})
            data={'choices':[{'message':{'content':text},'finish_reason':'stop'}],'usage':{'prompt_tokens':111,'completion_tokens':22,'prompt_tokens_details':{'cached_tokens':40},'completion_tokens_details':{'reasoning_tokens':2},'completion_time':.5,'ignored_private_field':secret}}
            self.send_response(200);self.send_header('x-ratelimit-remaining-tokens','5432');self.send_header('X-Private-Key',secret);self.end_headers();self.wfile.write(json.dumps(data).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),MockProvider);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    original_open=__import__('engine.local_model',fromlist=['_urlopen'])._urlopen
    def redirect_to_mock(req,timeout):
        # Test harness replaces transport only; production still validates official HTTPS URL.
        assert req.full_url in {p['endpoint'] for p in providers.PROVIDERS.values()}
        forwarded=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/chat',data=req.data,headers=dict(req.headers),method=req.method)
        return original_open(forwarded,timeout)
    discussion={'mode':'discuss','text':'[MOCK] A quiet ordinary afternoon.'}
    try:
      with patch('engine.ai_providers.read_public',side_effect=catalogs),patch('engine.local_model._urlopen',side_effect=redirect_to_mock):
        for provider,model in [('groq','openai/gpt-oss-120b'),('gemini','gemini-3.8-flash'),('openrouter',FREE)]:
            providers.activate(c,provider,model,secret,consent=True,free_account=True)
            assert runtime_config(c)['credential_available'] and not runtime_config(c)['free_local']
            queue[:]=[discussion];before=len(seen)
            out=play(c,'I look around without looking for trouble.')
            assert out['status']=='discussed' and len(seen)==before+1
            sent=seen[-1];assert sent['headers']['Authorization']=='Bearer '+secret
            assert sent['headers']['User-Agent']=='Caerness/1.0'
            assert sent['payload']['model']==model
            if provider=='groq':
                assert sent['payload']['response_format']['type']=='json_schema' and sent['payload']['response_format']['json_schema']['strict'] is True
                assert 'GROQ WIRE FORMAT:' in sent['payload']['messages'][-1]['content']
                assert 'never combine forms or add unused/null fields' in sent['payload']['messages'][-1]['content']
            else:
                assert sent['payload']['response_format']['type']=='json_schema'
                assert sent['payload']['response_format']['json_schema']['strict'] is False
                shape=sent['payload']['response_format']['json_schema']['schema']['properties']
                assert shape['task_type']=={'type':'string','enum':['action_interpretation']}
                assert shape['request_id']['type']=='integer' and len(shape['request_id']['enum'])==1
            if provider=='openrouter':assert sent['payload']['provider']=={'require_parameters':True,'max_price':{'prompt':0,'completion':0},'allow_fallbacks':False}
            safe=report(c);assert secret not in json.dumps(safe) and 'X-Private-Key' not in json.dumps(safe)
            assert safe['requests'][0]['calls'][0]['reported_rate_limits']['x-ratelimit-remaining-tokens']==5432
            assert safe['requests'][0]['calls'][0]['provider_usage']=={'cached_prompt_tokens':40,'reasoning_tokens':2,'provider_generation_seconds':.5,'generation_tokens_per_second':44}
            print(provider,'mock observation: 1 call, synthetic 111 input / 22 output tokens')
        # Paid/missing/free-suffix-with-extra-fee/no-JSON models cannot be selected.
        assert [m['id'] for m in providers.discover('openrouter')]==[FREE]
        before=len(seen)
        for candidate in ('paid:free','extra-fee:free','missing-price:free','no-json:free'):
            try:providers.activate(c,'openrouter',candidate,secret,consent=True,free_account=True);raise AssertionError('Paid or unverifiable model accepted')
            except providers.ProviderError:pass
        assert len(seen)==before
        providers.activate(c,'groq','openai/gpt-oss-120b',secret,consent=True,free_account=True)
        # Real engine read, second-round quota failure, persisted continuation only retried.
        inspection={'mode':'inspect','calls':[{'tool':'person','arguments':{'actor_id':ids['mara']}}]}
        queue[:]=[inspection,(429,{'error':{'message':secret+' rate limited'}})]
        out=play(c,'Ask Mara about her working day.');rid=out['request_id'];sid=out['session_id']
        assert out['failure']['code']=='rate_limit' and c.execute('SELECT status FROM model_requests WHERE id=?',(rid-1,)).fetchone()[0]=='applied'
        assert report(c)['requests'][0]['failure']['measurements']['retry-after']==2
        c.close();c=connect();queue[:]=[discussion];before=len(seen)
        assert resume(c,rid)['status']=='discussed' and len(seen)==before+1
        assert len([m for m in json.loads(plans.session(c,sid)['messages_json']) if m['role']=='player'])==1
        print('read + quota failure + reload + safe retry: 3 total mock calls, no repeated read')
        # Invalid successful reply remains distinguishable and retryable.
        queue[:]=['{not-json'];out=play(c,'I listen.');assert out['failure']['code']=='invalid_response'
        queue[:]=[discussion];assert resume(c,out['request_id'])['status']=='discussed'
        for malformed in ({'proposal':discussion},{'task_type':'action_interpretation','request_id':999999,'proposal':discussion}):
            today=plans.day(c);queue[:]=[json.dumps(malformed)]
            out=play(c,'I quietly listen.');assert out['failure']['code']=='invalid_response' and plans.day(c)==today
            queue[:]=[discussion];assert resume(c,out['request_id'])['status']=='discussed'
        queue[:]=[(307,{'error':{'message':secret}})];before=len(seen)
        out=play(c,'I pause to look around.')
        assert out['failure']['code']=='continuation_failed' and len(seen)==before+1
        assert report(c)['requests'][0]['failure']['measurements']['http_status']==307
        # Committed world time remains committed through failed cloud consequence narration.
        text='I decide to remain here for one day.'
        plan={'source_text':text,'summary':'Stay one day','coverage':[{'start':0,'end':len(text),'handling':'planned','step_ids':['time']}],'unresolved':[],'steps':[{'id':'time','operation':'advance_time','arguments':{'days':1},'depends_on':[]}]}
        verdict={'authorized':True,'complete':True,'evidence':[{'start':0,'end':len(text)}],'omissions':[],'reason':'Exact directive.'}
        today=plans.day(c);queue[:]=[{'mode':'plan','plan':plan},verdict,(503,{'error':{'message':secret}})]
        out=play(c,text);assert plans.day(c)==today+1 and out['failure']['code']=='continuation_failed'
        queue[:]=[discussion];assert resume(c,out['request_id'])['status']=='discussed' and plans.day(c)==today+1
        for status,body,code in [(401,{'error':{'message':secret}},'authentication'),(402,{'error':{}},'quota_exhausted'),(404,{'error':{}},'model_unavailable'),(422,{'error':{'message':'response_format '+secret}},'provider_contract'),(400,{'error':{'code':'json_validate_failed','message':secret}},'invalid_response'),(403,{'error':{'message':'error code: 1010'}},'provider_access'),(429,{'error':{'message':'tokens per day (TPD): Please try again in 12m59.76s.'}},'quota_exhausted')]:
            queue[:]=[(status,body)];out=play(c,'I observe.');assert out['failure']['code']==code
            assert secret not in json.dumps(out['diagnostics'])
        queue[:]=[discussion]
        queue[:]=[(200,{'error':{'code':429,'message':secret}})]
        out=play(c,'I listen again.');assert out['failure']['code']=='rate_limit'
        queue[:]=[(200,{'choices':[{'message':{'content':'{"incomplete":'},'finish_reason':'length'}],'usage':{'prompt_tokens':10,'completion_tokens':4}})]
        out=play(c,'I look at the street.');assert out['failure']['code']=='incomplete_response'
        assert report(c)['requests'][0]['failure']['measurements']['completion_tokens']==4
        queue[:]=[discussion]
        with patch('engine.local_model._urlopen',side_effect=TimeoutError(secret)):
            out=play(c,'I wait to hear a reply.');assert out['failure']['code']=='timeout'
        assert resume(c,out['request_id'])['status']=='discussed'
        # Local switch never uses vault or inherited cloud key, and preserves story history.
        history=c.execute('SELECT messages_json FROM ai_sessions ORDER BY id').fetchall()
        providers.clear_keys()
        from tools.local_ai import configure_save
        configure_save(c,'http://127.0.0.1:1234/v1/chat/completions','local-model')
        with patch.dict(os.environ,{'OPENAI_API_KEY':secret,'CAERNESS_FREE_LOCAL':'1'}):assert 'Authorization' not in _headers(local_only=True)
        assert c.execute('SELECT messages_json FROM ai_sessions ORDER BY id').fetchall()==history
        # Restart has no session key; saved cloud preference cannot infer a secret.
        set_runtime_config(c,device_profile='desktop_free_cloud_groq',local_endpoint=providers.PROVIDERS['groq']['endpoint'],local_model='openai/gpt-oss-120b')
        try:providers.validate(runtime_config(c));raise AssertionError('Missing restart key accepted')
        except providers.ProviderError as e:assert e.code=='authentication'
        # Consent denial prevents any network use.
        before=len(seen)
        try:providers.activate(c,'groq','openai/gpt-oss-120b',secret,consent=False,free_account=True);raise AssertionError('No consent')
        except providers.ProviderError:pass
        assert len(seen)==before
        print('Mock quota/auth/schema/timeout/redaction, state preservation and local credential isolation PASS')
    finally:providers.clear_keys();providers._catalogs.clear();c.close();server.shutdown();server.server_close();thread.join(2)

if __name__=='__main__':main()
