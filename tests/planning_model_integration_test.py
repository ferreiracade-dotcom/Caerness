"""Actual configured OpenAI-compatible HTTP adapter with explicitly fake model outputs."""
from __future__ import annotations

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'tools'))
from planning_demo import fixture, composed_spec, EXAMPLES
from engine.planning_gateway import start_request, run_local
from engine.local_model import set_runtime_config
from engine.ai_planning import approve_plan


def main():
    c,ids=fixture()
    replies=iter([
        {'mode':'inspect','calls':[{'tool':'context','arguments':{'institution_id':ids['institution']}},{'tool':'offerings','arguments':{}}]},
        {'mode':'plan','plan':composed_spec(ids,'survey')},
    ])
    packets=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            prompt=data['messages'][-1]['content']; packets.append(prompt)
            rid=int(re.search(r'"request_id":\s*(\d+)',prompt).group(1))
            response={'task_type':'action_interpretation','request_id':rid,'proposal':next(replies)}
            body=json.dumps({'choices':[{'message':{'content':json.dumps(response)}}]}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        set_runtime_config(c,local_backend='openai_compatible',local_endpoint=f'http://127.0.0.1:{server.server_port}/v1/chat/completions',local_model='explicit-test-stub')
        req=start_request(c,EXAMPLES['survey']['text'],'local')
        out=run_local(c,req['request_id'],force=True)
        assert out['status']=='awaiting_plan_review',out
        assert len(packets)==2 and 'define_role' in packets[0] and 'tool' in packets[1]
        assert not c.execute('SELECT 1 FROM institutional_roles').fetchone()
        p=out['plan']; result=approve_plan(c,p['id'],p['digest'])
        assert result['plan']['status']=='active'
        print('Configured HTTP adapter: discover capabilities → inspect scoped context → plan → stop for player review → validated execution PASS')
        print('Model outputs in this test are scripted; this is integration evidence, not a real LLM reasoning-quality evaluation.')
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2); c.close()


if __name__=='__main__': main()
