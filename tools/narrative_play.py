"""Launch narrative play on a save copy; credentials stay in environment variables."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--save',default='game/narrative-session.db')
 p.add_argument('--endpoint');p.add_argument('--model');p.add_argument('--port',type=int,default=8765)
 p.add_argument('--open-browser',action='store_true',help='Open the local game in your default desktop browser.')
 p.add_argument('--configure',action='store_true',help='Simple endpoint/model setup with a hidden key prompt; no key written to disk.')
 p.add_argument('--choose-ai',action='store_true',help='Choose free cloud or local AI in the launch window; preserve this campaign.')
 p.add_argument('--local',action='store_true',help='Free local setup; never asks for an API key.')
 p.add_argument('--change-model',action='store_true',help='Choose another local model without replacing the campaign.')
 p.add_argument('--local-server',choices=['ollama','lmstudio'],default='ollama')
 p.add_argument('--evaluate',action='store_true',help='Record real-model gameplay on an isolated test campaign, then exit.')
 p.add_argument('--probe',action='store_true',help='Check model connectivity; does not claim actual gameplay.')
 a=p.parse_args()
 if a.local and a.configure:p.error('Choose local setup or explicit remote setup, not both.')
 if a.choose_ai and (a.local or a.configure):p.error('Choose the AI selector or a direct local/custom launcher, not both.')
 if a.choose_ai and (a.endpoint or a.model):p.error('Use the selector’s advanced custom option for endpoint/model overrides; free presets cannot be overridden.')
 if a.local and (a.endpoint or a.model):p.error('Local setup selects a verified local model. Use --change-model rather than endpoint/model overrides.')
 if a.change_model and not a.local:p.error('--change-model requires --local.')
 if a.configure:
  os.environ.pop('CAERNESS_FREE_LOCAL',None)
  import getpass
  a.endpoint=input('Advanced custom endpoint (may be paid; no default): ').strip()
  a.model=input('Explicit available model ID (no default): ').strip()
  if not a.endpoint or not a.model:raise ValueError('An explicit custom endpoint and model are required. Choose AI.cmd offers verified free presets.')
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
  if a.choose_ai:
   from tools.choose_ai import choose
   selected=choose(c,save.parent)
   if selected in ('ollama','lmstudio'):a.local=True;a.local_server=selected
   elif selected=='custom':
    import getpass
    a.endpoint=input('Custom OpenAI-compatible HTTPS endpoint (may be paid): ').strip()
    a.model=input('Exact model ID: ').strip()
    if not a.endpoint or not a.model:raise ValueError('Custom endpoint and model are required.')
    key=getpass.getpass('Custom API key (hidden; kept only in memory): ')
    if key:os.environ['CAERNESS_MODEL_API_KEY']=key
   else:
    c.commit()
    from tools.local_ai import inference_probe
    print('Testing actual provider inference (not proof of RPG quality)...',flush=True)
    evidence=inference_probe(c,max_tokens=512)
    import json
    (save.parent/'cloud-inference-check.json').write_text(json.dumps({'provider':selected,**evidence},indent=2),encoding='utf-8')
    print(f"Structured test reply passed in {evidence['latency_seconds']:.1f} seconds. Resume your existing story in the browser.")
  if a.local:
   import json
   from tools.local_ai import hardware,prepare_ollama,configure_save,inference_probe,local_name
   from engine.local_model import runtime_config
   os.environ['CAERNESS_FREE_LOCAL']='1'
   # Inherited cloud credentials are irrelevant and never sent to a local process.
   os.environ.pop('CAERNESS_MODEL_API_KEY',None);os.environ.pop('OPENAI_API_KEY',None)
   os.environ.pop('CAERNESS_MODEL_ENDPOINT',None);os.environ.pop('CAERNESS_MODEL_NAME',None)
   hw=hardware()
   print(f"Memory: {hw['ram_gib']:.1f} GB RAM" if hw['ram_gib'] is not None else 'Memory could not be measured.')
   for gpu in hw['gpus']:
    memory=f"{gpu['vram_gib']:.1f} GB dedicated graphics memory" if gpu.get('vram_gib') is not None else 'graphics memory unknown'
    print('Graphics:',gpu['name'],'—',memory)
   if not hw['gpus']:print('No GPU was detected. CPU inference may be slow.')
   print(f"Model drive: {hw['disk_free_gib']:.1f} GB free")
   for warning in hw['warnings']:print(warning)
   previous=runtime_config(c)
   if a.local_server=='ollama':
    preferred=previous['local_model'] if previous.get('free_local') and ':11434/' in previous['local_endpoint'] else None
    model,info=prepare_ollama(hw,preferred=preferred,change=a.change_model)
    endpoint='http://127.0.0.1:11434/v1/chat/completions'
    details=info.get('details') or {}
    print('Installed model:',model,details.get('parameter_size',''),details.get('quantization_level',''))
   else:
    print('In LM Studio, load a LOCAL GGUF model, set context to 8192, turn thinking off, and start its local server on port 1234.')
    endpoint='http://127.0.0.1:1234/v1/chat/completions'
    from engine.local_model import _urlopen
    import urllib.request
    with _urlopen(urllib.request.Request('http://127.0.0.1:1234/v1/models'),5) as response:
     available=json.load(response)['data']
    names=[local_name(m['id']) for m in available if 'cloud' not in m['id'].lower()]
    if not names:raise ValueError('LM Studio exposes no loaded local model.')
    print('Available local model IDs:',', '.join(names))
    model=input(f'Model ID [{names[0]}]: ').strip() or names[0]
    if model not in names:raise ValueError('Choose an available model ID from the list.')
   configure_save(c,endpoint,model)
   c.commit()
   print('Testing actual model inference (the first load can take a while)...',flush=True)
   evidence=inference_probe(c)
   evidence['hardware']=hw
   if a.local_server=='ollama':
    from tools.local_ai import api,ollama_performance_probe
    evidence['loaded_models']=api('/api/ps')
    try:evidence['generation_diagnostic']=ollama_performance_probe(model)
    except (OSError,ValueError,KeyError) as error:evidence['generation_diagnostic']={'status':'UNAVAILABLE','error':type(error).__name__}
   report=save.parent/'local-inference-check.json'
   report.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
   print(f"Real structured reply passed in {evidence['latency_seconds']:.1f} seconds. Gameplay quality still needs review.")
   speed=(evidence.get('generation_diagnostic') or {}).get('generation_tokens_per_second')
   if speed is not None:print(f'Warm diagnostic generation: {speed:.1f} tokens/second (not whole-turn latency).')
   print('Detailed diagnostic saved:',report)
  changes={}
  if a.endpoint:changes['local_endpoint']=a.endpoint
  if a.model:changes['local_model']=a.model
  if changes:set_runtime_config(c,local_backend='openai_compatible',device_profile='desktop_configured',**changes)
  set_model_config(c,packet_dir=str(save.parent/'narrative_packets'))
  c.commit()
  if a.probe:
   import json
   print(json.dumps(local_health(c),indent=2));return
 print('Campaign save:',save)
 print('Free local inference; no API key or paid account required.' if a.local else 'Cloud/custom credentials remain server-side and are never stored in the save. Close this window to forget session keys.')
 if a.evaluate:
  if not a.local and not a.choose_ai:p.error('Select local or free-cloud AI before evaluation.')
  if a.local:os.environ['CAERNESS_MODEL_ENDPOINT']=endpoint;os.environ['CAERNESS_MODEL_NAME']=model
  from datetime import datetime
  from tools.evaluate_narrative import main as evaluate
  output=ROOT/'runs'/('local-gameplay-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
  if a.local:sys.argv=['evaluate_narrative','--local','--approve-reviewed','--out',str(output)]
  elif selected in ('groq','gemini','openrouter'):
   from engine.local_model import runtime_config
   with connect() as c:chosen_model=runtime_config(c)['local_model']
   sys.argv=['evaluate_narrative','--cloud-provider',selected,'--model',chosen_model,'--approve-reviewed','--out',str(output)]
  else:p.error('Custom evaluation is separate from verified free cloud.')
  print('Recording real gameplay in',output,'— this runs twenty dialogue turns and can take a while.',flush=True)
  evaluate();return
 from engine.mobile_server import serve
 if a.open_browser:
  import webbrowser
  serve(port=a.port,on_ready=lambda:webbrowser.open_new_tab(f'http://127.0.0.1:{a.port}'))
 else:serve(port=a.port)
if __name__=='__main__':
 try:main()
 except KeyboardInterrupt:print('\nGame stopped. Your campaign remains saved.')
 except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
  print('Caerness could not start:',error)
  print('See WINDOWS_PLAY.md for setup and troubleshooting. Your campaign has not been replaced.')
  sys.exit(1)
