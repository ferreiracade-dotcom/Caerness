"""Non-secret model failure reports: never export prompts, dialogue or endpoints."""
import json

MESSAGES={
    'free_quota_unavailable':'Google reports no available free inference quota or free-tier eligibility for this project/model. Model discovery can still work. Check your project and model limits in Google AI Studio; keep billing disabled. Choose another free provider or local AI explicitly if needed. No reset time or paid fallback is assumed.',
    'authentication':'The cloud provider did not accept this key or account. Restart Choose AI.cmd and enter the key privately in the launch window.',
    'rate_limit':'The provider’s free request or token rate limit was reached. Wait before retrying; earlier outcomes are saved. Copy Diagnostics may include its retry-after seconds.',
    'quota_exhausted':'The provider’s available free quota is exhausted. Wait for its reset or explicitly select another free provider or local AI. No paid fallback was attempted.',
    'model_unavailable':'This cloud model is unavailable. Choose another verified free model explicitly; your campaign remains saved.',
    'provider_contract':'The provider rejected the response-format or request options. Copy Diagnostics for support. The response was not applied.',
    'provider_access':'The cloud service denied this client connection before returning a usable API response. Check provider/network access and Copy Diagnostics; this does not establish an invalid key.',
    'provider_policy':'The selected model or endpoint could not be verified under the free-cloud policy. Use Choose AI.cmd to select a verified free option.',
    'repeated_read':'The model asked again for information it had already received. This turn was stopped to avoid a long loop. The results are saved; retry or choose another model.',
    'interrupted':'You paused this conversation. The unfinished response is saved; retry resumes it without replaying confirmed actions.',
    'timeout':'The model took too long to respond. Your conversation is saved; retry the unfinished response.',
    'unavailable':'The model service could not be reached. Check your internet connection for cloud play, or start your local server, then retry.',
    'invalid_response':'The model returned an invalid response. No incomplete response was applied; retry or change model.',
    'incomplete_response':'The model stopped before completing its response. Retry or adjust the output budget in local settings.',
    'context_limit':'This conversation exceeded the configured model context. Nothing was silently truncated. Increase context if memory permits, or start a new conversation.',
    'out_of_memory':'The model service reported insufficient memory. Close other applications or choose a smaller model, then retry.',
    'continuation_failed':'The narrative continuation could not finish. Earlier confirmed outcomes are saved; retry the unfinished response.',
}

def classify(error):
    code=getattr(error,'code',None)
    if code in MESSAGES:return code
    text=str(error).lower()
    if 'context' in text and ('exceed' in text or 'limit' in text):return 'context_limit'
    if 'token limit' in text or 'incomplete' in text:return 'incomplete_response'
    if 'backend is disabled' in text:return 'unavailable'
    if isinstance(error,TimeoutError) or 'timed out' in text:return 'timeout'
    if isinstance(error,ConnectionError):return 'unavailable'
    if isinstance(error,(ValueError,KeyError,TypeError)):return 'invalid_response'
    return 'continuation_failed'

def ensure(c):
    c.execute('CREATE TABLE IF NOT EXISTS narrative_failures(id INTEGER PRIMARY KEY,request_id INTEGER,code TEXT,phase TEXT,elapsed_seconds REAL,measurements_json TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    if 'elapsed_seconds' not in {r[1] for r in c.execute('PRAGMA table_info(narrative_failures)')}:
        c.execute('ALTER TABLE narrative_failures ADD COLUMN elapsed_seconds REAL')
    if 'measurements_json' not in {r[1] for r in c.execute('PRAGMA table_info(narrative_failures)')}:
        c.execute('ALTER TABLE narrative_failures ADD COLUMN measurements_json TEXT')

def record_failure(c,rid,error,elapsed=None):
    ensure(c)
    row=c.execute('SELECT input_json FROM model_requests WHERE id=?',(rid,)).fetchone()
    payload=json.loads(row[0]) if row else {}
    phase=payload.get('phase') or payload.get('protocol','unknown')
    c.execute('INSERT INTO narrative_failures(request_id,code,phase,elapsed_seconds,measurements_json) VALUES (?,?,?,?,?)',(rid,classify(error),phase,round(elapsed,4) if elapsed is not None else None,json.dumps({'error_type':type(error).__name__,**getattr(error,'measurements',{})})))

def report(c,session_id=None):
    from .ai_planning import current_actor,ensure_schema
    ensure_schema(c);ensure(c)
    owner=current_actor(c)
    rows=c.execute("SELECT r.id,r.status,r.input_json FROM model_requests r JOIN ai_sessions s ON s.id=r.target_id WHERE r.target_kind='ai_session' AND s.owner_actor_id=? AND (? IS NULL OR s.id=?) ORDER BY r.id DESC LIMIT 12",(owner,session_id,session_id)).fetchall()
    reports=[]
    has_calls=c.execute("SELECT 1 FROM sqlite_master WHERE name='ai_model_calls'").fetchone()
    for row in rows:
        payload=json.loads(row['input_json'])
        f=c.execute('SELECT code,phase,elapsed_seconds,created_at,measurements_json FROM narrative_failures WHERE request_id=? ORDER BY id DESC LIMIT 1',(row['id'],)).fetchone()
        failure=dict(f) if f else None
        if failure:
            failure['measurements']=json.loads(failure.pop('measurements_json') or '{}')
            failure['error_type']=failure['measurements'].pop('error_type',None)
        calls=[dict(r) for r in c.execute('SELECT latency_seconds,prompt_tokens,completion_tokens FROM ai_model_calls WHERE request_id=?',(row['id'],))] if has_calls else []
        if has_calls and 'provider' in {r[1] for r in c.execute('PRAGMA table_info(ai_model_calls)')}:
            calls=[dict(r) for r in c.execute('SELECT provider,model,latency_seconds,prompt_tokens,completion_tokens,usage_json FROM ai_model_calls WHERE request_id=?',(row['id'],))]
            for call in calls:
                extra=json.loads(call.pop('usage_json') or '{}')
                call['reported_rate_limits']=extra.get('rate_limits',extra)
                call['provider_usage']=extra.get('provider_usage',{})
        newer=c.execute("SELECT 1 FROM model_requests WHERE target_kind='ai_session' AND target_id=? AND id>? LIMIT 1",(payload.get('session_id'),row['id'])).fetchone()
        reports.append({'request_id':row['id'],'status':row['status'],'retryable':row['status'] in ('pending','responded') and not newer,'phase':payload.get('phase') or payload.get('protocol'),'round':payload.get('rounds',0),'failure':failure,'calls':calls})
    from .local_model import runtime_config
    cfg=runtime_config(c)
    return {'format':'caerness-diagnostics-v1','privacy':'No prompts, dialogue, world facts, credentials or endpoints included.','runtime':{k:cfg[k] for k in ('ai_provider','local_backend','local_model','local_timeout_seconds','local_max_output_tokens','local_heavy_context_tokens')},'requests':reports}

def paused(c,rid):
    ensure(c)
    f=c.execute('SELECT code,phase FROM narrative_failures WHERE request_id=? ORDER BY id DESC LIMIT 1',(rid,)).fetchone()
    code=f['code'] if f else 'continuation_failed'
    out={'status':'external_recommended','request_id':rid,'reason':MESSAGES[code],'failure':{'code':code,'phase':f['phase'] if f else 'unknown','request_id':rid},'diagnostics':report(c)}
    if code=='rate_limit' and out['diagnostics']['requests']:
        failure=out['diagnostics']['requests'][0].get('failure') or {}
        measurements=failure.get('measurements',{})
        waits=[measurements[k] for k in ('retry-after','provider_retry_after_seconds') if type(measurements.get(k)) in (int,float)]
        if waits:out['reason']+=f' The provider asks waiting at least {max(waits):.1f} seconds before trying again.'
    # Preserve the existing opt-in manual handoff, separate from safe diagnostics.
    # Render in memory so a missing/unwritable export folder cannot break recovery.
    from .model_gateway import render_packet
    row=c.execute('SELECT task_type,input_json FROM model_requests WHERE id=?',(rid,)).fetchone()
    if row:
        packet=json.loads(row['input_json'])
        for provider in ('chatgpt','claude'):out[provider]={'packet':render_packet(provider,rid,row['task_type'],packet)}
    return out
