"""Trusted terminal setup: passwords never pass through the game browser."""
import getpass
import json
import os
from pathlib import Path
import warnings

def hidden_key(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        try:return getpass.getpass(prompt)
        except getpass.GetPassWarning:
            raise ValueError('A hidden key prompt is unavailable in this terminal. Launch the Windows .cmd file in its normal console; no key was read.') from None

def choose(conn, folder, *, input_fn=input, password_fn=hidden_key):
    from engine import ai_providers as providers
    from engine.local_model import runtime_config
    preferences=Path(folder)/'ai-choice.json'
    try:previous=json.loads(preferences.read_text(encoding='utf-8'))
    except (OSError,ValueError):previous={}
    options=['groq','gemini','openrouter','ollama','lmstudio','custom']
    labels=[providers.PROVIDERS[k]['label'] if k in providers.PROVIDERS else {'ollama':'Ollama — Local AI','lmstudio':'LM Studio — Local AI','custom':'Advanced custom endpoint (may be paid)'}[k] for k in options]
    print('\nChoose AI — this does not select, reset or replace your campaign.')
    for i,label in enumerate(labels,1):print(f'{i}. {label}')
    default=options.index(previous.get('provider'))+1 if previous.get('provider') in options else 1
    answer=input_fn(f'Choice [{default}]: ').strip() or str(default)
    if not answer.isdigit() or not 1<=int(answer)<=len(options):raise ValueError('Choose a number from the list.')
    provider=options[int(answer)-1]
    # Remove stale deployment overrides before changing mode. Do not mutate proxy
    # credentials or provider-specific injected credential variables.
    for name in ('CAERNESS_FREE_LOCAL','CAERNESS_MODEL_ENDPOINT','CAERNESS_MODEL_NAME','CAERNESS_MODEL_API_KEY','OPENAI_API_KEY'):
        os.environ.pop(name,None)
    providers.clear_keys()
    if provider in ('ollama','lmstudio','custom'):
        preferences.write_text(json.dumps({'provider':provider}),encoding='utf-8')
        return provider
    info=providers.PROVIDERS[provider]
    print('\nCloud play sends selected scene, dialogue and planning context to this provider, not the campaign database.')
    print('Do not include real personal information. Local AI keeps these requests on your computer.')
    if provider=='gemini':print('Google’s free tier may use inputs and outputs to improve products, with human review. South Africa is listed as supported.')
    elif provider=='groq':print('Groq normally does not retain inference content, but reliability/abuse logs may last up to 30 days. Enable Zero Data Retention in Data Controls if desired. Review https://console.groq.com/docs/your-data.')
    else:print('OpenRouter’s own prompt logging/use is opt-in, but inference providers’ retention/training rules vary (including free models). Review https://openrouter.ai/docs/guides/privacy/provider-logging.')
    if input_fn('Send selected game context to this provider? Type YES: ').strip()!='YES':raise ValueError('Cloud play was not enabled. Relaunch to choose local AI.')
    print('Create a FREE developer account and key at',info['key_url'])
    print('Keep billing disabled; do not add a card, upgrade, purchase credits or enable auto-top-up.')
    print('Groq/Gemini do not expose billing status to Caerness. A paid account may be charged even for these presets.')
    if provider=='openrouter':print('Only live-catalog :free models with zero prices are offered. The unpaid allowance is limited; no paid fallback is configured.')
    if input_fn('Confirm your account/project has billing disabled and you want only free usage. Type FREE: ').strip()!='FREE':raise ValueError('Free account confirmation is required.')
    key=os.environ.get(info['key_env']) or password_fn('Paste provider API key (hidden; remembered only until this window closes): ')
    if not key or any(ch in key for ch in '\r\n'):raise ValueError('A provider API key is required.')
    providers._keys[provider]=key.strip()
    models=providers.discover(provider,refresh=True)
    print('\nVerified free choices (recommendations provisional: gameplay quality is not yet demonstrated):')
    for i,model in enumerate(models,1):print(f"{i}. {model['id']} — context {model['context']:,} tokens"+(' — first candidate to try' if model['recommended'] else ''))
    prior=previous.get('model');default=next((i for i,m in enumerate(models,1) if m['id']==prior),1)
    answer=input_fn(f'Model [{default}]: ').strip() or str(default)
    if not answer.isdigit() or not 1<=int(answer)<=len(models):raise ValueError('Choose an available free model number.')
    model=models[int(answer)-1]['id']
    # activate refreshes availability/pricing and binds credentials to the exact endpoint.
    providers.activate(conn,provider,model,key,consent=True,free_account=True)
    preferences.write_text(json.dumps({'provider':provider,'model':model}),encoding='utf-8')
    print('Model selection changed; campaign and conversation history are unchanged.')
    print('Limits belong to your provider account. No quota balance is inferred; quota failures pause safely without a fallback.')
    return provider
