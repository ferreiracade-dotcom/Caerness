"""Optional cloud policy on the existing gateway. No campaign or credential storage.

Free account status is not exposed by Groq/Gemini APIs: the owner must confirm
billing is disabled. Catalog verification does not establish account billing status.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import json
import re
import time
import urllib.request

PROVIDERS = {
    'groq': {'label':'GroqCloud — Free Cloud AI', 'endpoint':'https://api.groq.com/openai/v1/chat/completions', 'models':'https://api.groq.com/openai/v1/models', 'key_url':'https://console.groq.com/keys', 'key_env':'GROQ_API_KEY'},
    'gemini': {'label':'Google Gemini — Free Cloud AI', 'endpoint':'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions', 'models':'https://generativelanguage.googleapis.com/v1beta/models', 'key_url':'https://aistudio.google.com/apikey', 'key_env':'GEMINI_API_KEY'},
    'openrouter': {'label':'OpenRouter — Free Cloud AI', 'endpoint':'https://openrouter.ai/api/v1/chat/completions', 'models':'https://openrouter.ai/api/v1/models', 'key_url':'https://openrouter.ai/settings/keys', 'key_env':'OPENROUTER_API_KEY'},
}
# Dated, expiring review rather than an indefinite claim that every Groq model is free.
# Other providers expose pricing which is checked live. Groq lists availability only.
GROQ_REVIEW_EXPIRES = date(2026, 11, 13)
GROQ_REVIEWED = {'openai/gpt-oss-120b':131072}
_keys = {}
_catalogs = {}

class ProviderError(ConnectionError):
    def __init__(self, message, code='provider_policy', measurements=None):
        super().__init__(message)
        self.code = code
        self.measurements = measurements or {}

def provider_id(config):
    profile = str(config.get('device_profile',''))
    return profile.removeprefix('desktop_free_cloud_') if profile.startswith('desktop_free_cloud_') else None

def key_for(provider):
    return _keys.get(provider)

def clear_keys():
    _keys.clear()

def read_public(url, *, provider=None, native=False):
    from .local_model import _urlopen
    headers = {'Accept':'application/json', 'User-Agent':'Caerness/1.0'}
    if provider and key_for(provider):
        headers['x-goog-api-key' if native else 'Authorization'] = key_for(provider) if native else 'Bearer '+key_for(provider)
    try:
        with _urlopen(urllib.request.Request(url,headers=headers),20) as response:
            return response.read(4_000_000).decode('utf-8')
    except Exception:
        raise ProviderError('Could not verify the provider catalog. Check your key, internet connection and provider status; no model was substituted.') from None

class PricingParser(HTMLParser):
    """Read Gemini's first (standard) pricing table for each model heading."""
    def __init__(self):
        super().__init__(); self.model=None; self.table=False; self.done=set(); self.rows={}; self.cells=[]; self.cell=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='h2':
            ident=attrs.get('id','')
            self.model=ident if re.fullmatch(r'gemini-[\w.-]*flash(?:-lite)?',ident) else None
        if tag=='table': self.table=bool(self.model and self.model not in self.done)
        if self.table and tag=='tr': self.cells=[]
        if self.table and tag=='td': self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag=='td' and self.cell is not None:
            self.cells.append(' '.join(self.cell).strip());self.cell=None
        if tag=='tr' and self.table and len(self.cells)>=2:
            self.rows.setdefault(self.model,{})[self.cells[0]]=self.cells[1]
        if tag=='table' and self.table:self.done.add(self.model);self.table=False
    def free_models(self):
        return {m for m,rows in self.rows.items() if rows.get('Input price')=='Free of charge' and any(k.startswith('Output price') and v=='Free of charge' for k,v in rows.items())}

def _zero(value):
    try:return Decimal(str(value)) == 0
    except (InvalidOperation,ValueError):return False

def discover(provider, *, refresh=False):
    if provider not in PROVIDERS:raise ProviderError('Unknown cloud provider.')
    if provider=='groq' and date.today()>GROQ_REVIEW_EXPIRES:
        raise ProviderError('The dated Groq free-plan review has expired. Update Caerness before using this free-cloud preset; local play remains available.')
    cached=_catalogs.get(provider)
    if cached and not refresh and time.monotonic()-cached[0]<900:return cached[1]
    info=PROVIDERS[provider]
    if provider!='openrouter' and not key_for(provider):raise ProviderError('Enter this provider’s API key in the launch window.', 'authentication')
    data=json.loads(read_public(info['models'],provider=provider if provider!='openrouter' else None,native=provider=='gemini'))
    choices=[]
    if provider=='groq':
        for model in data.get('data',[]):
            ident=model.get('id')
            if ident in GROQ_REVIEWED and model.get('active',True):
                choices.append({'id':ident,'context':min(GROQ_REVIEWED[ident],int(model.get('context_window') or GROQ_REVIEWED[ident])),'output':min(65536,int(model.get('max_completion_tokens') or 65536)),'format':'schema','recommended':True})
    elif provider=='gemini':
        parser=PricingParser();parser.feed(read_public('https://ai.google.dev/gemini-api/docs/pricing'))
        free=parser.free_models()
        for model in data.get('models',[]):
            ident=model.get('name','').removeprefix('models/')
            if ident in free and 'generateContent' in model.get('supportedGenerationMethods',[]):
                choices.append({'id':ident,'context':int(model.get('inputTokenLimit',0)),'output':int(model.get('outputTokenLimit',0)),'format':'schema','recommended':ident=='gemini-3.8-flash'})
    else:
        for model in data.get('data',[]):
            pricing=model.get('pricing',{}); params=model.get('supported_parameters',[])
            # All supplied price components must be zero; missing token prices fail closed.
            if not str(model.get('id','')).endswith(':free') or not all(_zero(pricing.get(k)) for k in ('prompt','completion')):continue
            if not all(_zero(v) for v in pricing.values()) or 'response_format' not in params:continue
            top=model.get('top_provider') or {}
            choices.append({'id':model['id'],'context':int(model.get('context_length',0)),'output':int(top.get('max_completion_tokens') or 4096),'format':'schema' if 'structured_outputs' in params else 'json','recommended':False})
    choices=[m for m in choices if m['context']>=8192 and m['output']>=1024]
    choices.sort(key=lambda m:(not m['recommended'],m['id']))
    if not choices:raise ProviderError('No currently verified free text model with JSON support is available. No paid fallback was attempted.')
    _catalogs[provider]=(time.monotonic(),choices)
    return choices

def activate(conn, provider, model, key, *, consent=False, free_account=False):
    """Only called from the trusted launch window, not a browser key form."""
    from .local_model import set_runtime_config
    if not consent:raise ProviderError('Cloud privacy consent is required.')
    if not free_account:raise ProviderError('Confirm a free, billing-disabled account before cloud play.')
    if provider not in PROVIDERS or not isinstance(key,str) or not key.strip() or any(ch in key for ch in '\r\n'):
        raise ProviderError('A valid provider-specific key is required.', 'authentication')
    _keys[provider]=key.strip()
    try:
        candidates=discover(provider,refresh=True)
        chosen=next((m for m in candidates if m['id']==model),None)
        if not chosen:raise ProviderError('This model is not currently verified free. No request was sent to it.')
        return set_runtime_config(conn,device_profile='desktop_free_cloud_'+provider,local_backend='openai_compatible',local_endpoint=PROVIDERS[provider]['endpoint'],local_model=model,local_timeout_seconds=90,local_max_context_tokens=min(6000,chosen['context']),local_heavy_context_tokens=min(32768,chosen['context']),local_max_output_tokens=min(2048,chosen['output']))
    except Exception:
        _keys.pop(provider,None);raise

def validate(config):
    provider=provider_id(config)
    if not provider:return None
    if provider not in PROVIDERS or config.get('local_endpoint')!=PROVIDERS[provider]['endpoint'] or config.get('local_backend')!='openai_compatible':
        raise ProviderError('Free-cloud presets require the exact official HTTPS endpoint. Use advanced custom setup separately.')
    if not key_for(provider):raise ProviderError('Restart with Choose AI.cmd and enter this provider’s key in the launch window.', 'authentication')
    choice=next((m for m in discover(provider) if m['id']==config.get('local_model')),None)
    if not choice:raise ProviderError('The selected model is no longer verified free; choose another explicitly.')
    return choice

def adapt_payload(config,payload,schema):
    choice=validate(config)
    provider=provider_id(config)
    if not choice:return payload
    if schema and choice['format']=='schema':
        # Caerness schemas contain general-purpose argument objects, outside the
        # closed-object strict subset. Provider best-effort schema + unchanged
        # engine validation avoids either restricting capabilities or lying about strictness.
        payload['response_format']={'type':'json_schema','json_schema':{'name':'caerness_response','strict':False,'schema':schema}}
    else:payload['response_format']={'type':'json_object'}
    if provider=='groq':payload['reasoning_effort']='low';payload['include_reasoning']=False
    elif provider=='gemini':payload['reasoning_effort']='low'
    else:
        # One explicit free model, no model list, paid endpoint or model fallback.
        payload['provider']={'require_parameters':True,'max_price':{'prompt':0,'completion':0},'allow_fallbacks':False}
    return payload
