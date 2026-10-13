"""Launch narrative play on a save copy; credentials stay in environment variables."""
import argparse
import os
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--save',default='game/narrative-session.db')
 p.add_argument('--endpoint');p.add_argument('--model');p.add_argument('--port',type=int,default=8765)
 p.add_argument('--configure',action='store_true',help='Simple endpoint/model setup with a hidden key prompt; no key written to disk.')
 p.add_argument('--probe',action='store_true',help='Check model connectivity; does not claim actual gameplay.')
 a=p.parse_args()
 if a.configure:
  import getpass
  a.endpoint=input('Model endpoint [https://api.openai.com/v1/chat/completions]: ').strip() or 'https://api.openai.com/v1/chat/completions'
  a.model=input('Available model name [gpt-4.1]: ').strip() or 'gpt-4.1'
  if not (os.environ.get('CAERNESS_MODEL_API_KEY') or os.environ.get('OPENAI_API_KEY')):
   key=getpass.getpass('API key (hidden, kept only for this running session; blank for an unauthenticated local server): ')
   if key:os.environ['CAERNESS_MODEL_API_KEY']=key
 save=Path(a.save).resolve()
 if save==(ROOT/'data/caerness.db').resolve():p.error('Use a campaign copy, never the canonical opening.')
 save.parent.mkdir(parents=True,exist_ok=True)
 if not save.exists():shutil.copy2(ROOT/'data/caerness.db',save)
 os.environ['CAERNESS_DB_PATH']=str(save)
 from engine.db import connect,init_db
 from engine.local_model import set_runtime_config,local_health
 from engine.model_gateway import set_model_config
 init_db()
 with connect() as c:
  changes={}
  if a.endpoint:changes['local_endpoint']=a.endpoint
  if a.model:changes['local_model']=a.model
  if changes:set_runtime_config(c,local_backend='openai_compatible',**changes)
  set_model_config(c,packet_dir=str(save.parent/'narrative_packets'))
  c.commit()
  if a.probe:
   import json
   print(json.dumps(local_health(c),indent=2));return
 print('Campaign save:',save)
 print('API credentials are read from CAERNESS_MODEL_API_KEY or OPENAI_API_KEY; never stored in the save.')
 from engine.mobile_server import serve
 serve(port=a.port)
if __name__=='__main__':main()
