"""Authority, transport failure and delegated-presence regressions on copies."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'tools'))
from planning_demo import fixture,composed_spec,EXAMPLES
from engine import ai_planning as plans
from engine.local_model import runtime_config,set_runtime_config,_post_json,_validate_endpoint,_NoRedirect
from engine.world_capabilities import quote


def fail(fn):
 try:fn()
 except (ValueError,ConnectionError):return
 raise AssertionError('Expected denial')

def main():
 c,ids=fixture()
 for url in ('http://example.org/v1/chat/completions','https://user:secret@example.org/v1/chat/completions','https://example.org/v1/chat/completions?api_key=secret'):
  fail(lambda:_validate_endpoint(url))
 with patch.dict(os.environ,{'CAERNESS_MODEL_ENDPOINT':'https://example.org/v1/chat/completions','CAERNESS_MODEL_NAME':'capable-configured-model','CAERNESS_MODEL_API_KEY':'test-key'}):
  cfg=runtime_config(c);assert cfg['remote_model'] and cfg['credential_available'] and cfg['local_model']=='capable-configured-model'
  assert 'test-key' not in json.dumps(cfg)
 with patch('engine.local_model._urlopen',side_effect=urllib.error.HTTPError('https://x',401,'secret-key-in-error',{},None)):
  try:_post_json('https://example.org/v1/chat/completions',{},5)
  except ConnectionError as exc:assert '401' in str(exc) and 'secret-key' not in str(exc)
 assert _NoRedirect().redirect_request(None,None,302,'',{},'https://another.example') is None
 print('Environment-selected remote model, HTTPS-only credentials, redacted errors and no credential forwarding PASS')
 # The owner can legitimately leave after consent, before commissioning. No new contact is invented.
 source=EXAMPLES['survey']['text'];full=composed_spec(ids,'survey');prefix=json.loads(json.dumps(full));prefix['steps']=prefix['steps'][:3];prefix['coverage'][0]['step_ids']=[x['id'] for x in prefix['steps']]
 sid=plans.session(c)['id'];view=plans.draft_plan(c,sid,source,prefix);done=plans.approve_plan(c,view['id'],view['digest'])['plan'];assert done['status']=='completed'
 remote=c.execute("INSERT INTO locations(name,kind) VALUES ('[DEMO] Commander away','settlement')").lastrowid
 c.execute('UPDATE actors SET current_location_id=? WHERE id=?',(remote,ids['owner']));c.execute('UPDATE player_state SET current_location_id=?',(remote,))
 fail(lambda:quote(c,ids['owner'],ids['survey']))
 service=done['steps']['consent']['result']['engagement_id']
 assert quote(c,ids['owner'],ids['survey'],service)['offering_id']==ids['survey']
 view=plans.draft_plan(c,sid,source,full,view['id']);result=plans.approve_plan(c,view['id'],view['digest'])['plan']
 assert result['status']=='active',result
 assert result['steps']['work']['status']=='active'
 assert c.execute('SELECT current_location_id FROM actors WHERE id=?',(ids['mara'],)).fetchone()[0]!=remote
 print('Accepted scoped delegation can begin at its real site after the commanding player leaves PASS')
 c.close()
if __name__=='__main__':main()
