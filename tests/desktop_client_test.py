"""Real browser-server API contracts, without a scripted model or gameplay claims."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from engine.db import connect,init_db,DEFAULT_DB_PATH
from engine.mobile_server import CaernessHandler
from engine.ai_planning import session,message


def main():
 path=Path(os.environ['CAERNESS_DB_PATH']);shutil.copy2(DEFAULT_DB_PATH,path);init_db()
 server=ThreadingHTTPServer(('127.0.0.1',0),CaernessHandler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 def api(path,body=None):
  request=Request(f'http://127.0.0.1:{server.server_port}'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
  with urlopen(request,timeout=10) as r:return json.loads(r.read())
 def denied(path,body=None):
  try:api(path,body)
  except HTTPError:return
  raise AssertionError('Expected access denial')
 try:
  assert api('/api/ledger')['setup']['available_locations']>0
  choices=api('/api/campaign/characters?query=Robert%20Baird');assert choices
  assert set(choices[0])=={'id','name','role','location'}
  owner=choices[0]['id'];denied('/api/campaign/select',{'actor_id':True});denied('/api/campaign/select',{'actor_id':-1})
  api('/api/campaign/select',{'actor_id':owner})
  assert api('/api/state')['player']['name']=='Robert Baird'
  assert api('/api/ledger')['setup']['setup']['player_setup_complete']==1
  denied('/api/campaign/characters?query=secret');denied('/api/campaign/select',{'actor_id':owner})
  with connect() as c:
   for i in range(8):
    row=session(c);message(c,row['id'],'player',f'Existing conversation {i}')
   first=c.execute('SELECT MIN(id) FROM ai_sessions').fetchone()[0]
   c.commit()
  assert len(api('/api/state')['conversations'])==5
  assert len(api('/api/conversations'))==8
  assert api(f'/api/conversation/{first}')['messages'][0]['text']=='Existing conversation 0'
  denied('/api/conversation/999999')
  with connect() as c:
   from engine.player import set_player
   other=c.execute("SELECT id FROM actors WHERE name='Petra Fenn'").fetchone()[0];set_player(c,other);c.commit()
  assert api('/api/conversations')==[]
  denied(f'/api/conversation/{first}')
  print('Character selection/create setup, private-field exclusion, repeat selection denial, older conversation retrieval and camera ownership PASS')
 finally:server.shutdown();server.server_close();thread.join(2)
if __name__=='__main__':main()
