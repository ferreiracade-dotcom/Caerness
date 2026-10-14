from __future__ import annotations

import json
import os
import time
import socket
from urllib.parse import urlsplit
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LocalModelResult:
    text: str
    backend: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw: dict[str, Any] | None = None
    latency_seconds: float = 0.0


class ModelResponseError(ValueError):
    def __init__(self,message,code,usage,latency):
        super().__init__(message)
        self.code=code
        self.measurements={'prompt_tokens':_token_count(usage.get('prompt_tokens')),'completion_tokens':_token_count(usage.get('completion_tokens')),'latency_seconds':round(latency,4)}


def _token_count(value):
    return value if type(value)is int and value>=0 else None


def runtime_config(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM runtime_config WHERE id=1").fetchone()
    if not row:
        conn.execute("INSERT INTO runtime_config(id) VALUES (1)")
        row = conn.execute("SELECT * FROM runtime_config WHERE id=1").fetchone()
    config = dict(row)
    # Deployment overrides are non-secret; the key remains exclusively in memory.
    for env, key in (("CAERNESS_MODEL_ENDPOINT", "local_endpoint"), ("CAERNESS_MODEL_NAME", "local_model")):
        if os.environ.get(env): config[key] = os.environ[env]
    if os.environ.get("CAERNESS_MODEL_ENDPOINT"): config["local_backend"] = "openai_compatible"
    config["remote_model"] = urlsplit(str(config["local_endpoint"])).hostname not in {"localhost", "127.0.0.1", "::1"}
    config["credential_available"] = bool(os.environ.get("CAERNESS_MODEL_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    config["free_local"] = config.get("device_profile") == "desktop_free_local"
    from .ai_providers import provider_id, key_for
    config['ai_provider'] = provider_id(config) or ('local' if config['free_local'] else 'custom')
    if provider_id(config):config['credential_available'] = bool(key_for(provider_id(config)))
    if config["free_local"]:
        if config["remote_model"] or 'cloud' in str(config["local_model"]).lower():
            raise ValueError("Free local play requires a loopback server and a local model. Use explicit remote configuration to change this.")
        config["credential_available"] = False
    return config


def set_runtime_config(conn: sqlite3.Connection, **changes: Any) -> dict[str, Any]:
    allowed = {
        "device_profile", "local_backend", "local_endpoint", "local_model", "local_timeout_seconds",
        "local_max_context_tokens", "local_heavy_context_tokens", "local_max_output_tokens",
        "referral_sensitivity", "referral_for_quality", "referral_for_reasoning", "referral_for_hardware",
        "auto_backup_every_turns",
    }
    invalid = set(changes) - allowed
    if invalid:
        raise ValueError(f"Unsupported runtime setting(s): {sorted(invalid)}")
    if "realtime_calendar_progression" in changes:
        raise ValueError("Real-world calendar progression is intentionally disabled in Caerness.")
    if "local_endpoint" in changes:
        _validate_endpoint(str(changes["local_endpoint"]))
    if changes:
        sets = ",".join(f"{k}=?" for k in changes) + ",updated_at=CURRENT_TIMESTAMP"
        conn.execute(f"UPDATE runtime_config SET {sets} WHERE id=1", tuple(changes.values()))
    return runtime_config(conn)


def estimate_tokens(value: Any) -> int:
    """Cheap hardware-safe estimate. Exact tokenizer coupling is deliberately avoided."""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    # English-heavy Caerness packets average roughly 3.5-4 chars/token; use 3.4 to err high.
    return max(1, int(len(value) / 3.4) + 1)


def _validate_endpoint(url):
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Model endpoint must not contain credentials, query parameters or fragments.")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise ValueError("Use HTTPS for remote models or HTTP on loopback for a local server.")
    if not parsed.hostname: raise ValueError("Model endpoint requires a hostname.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a bearer credential to another endpoint.


def _urlopen(request, timeout):
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)


def _headers(*, local_only=False, provider=None):
    if provider:
        from .ai_providers import key_for, ProviderError
        key=key_for(provider)
        if not key:raise ProviderError('Enter the provider key in the launch window.', 'authentication')
        return {'Content-Type':'application/json','Authorization':'Bearer '+key}
    if local_only or os.environ.get("CAERNESS_FREE_LOCAL") == "1":
        return {"Content-Type": "application/json"}
    key = os.environ.get("CAERNESS_MODEL_API_KEY") or os.environ.get("OPENAI_API_KEY")
    return {"Content-Type": "application/json", **({"Authorization": "Bearer " + key} if key else {})}


def _post_json(url: str, payload: dict[str, Any], timeout: int, *, local_only=False, provider=None) -> dict[str, Any]:
    _validate_endpoint(url)
    if provider:
        from .ai_providers import PROVIDERS,ProviderError
        if provider not in PROVIDERS or url!=PROVIDERS[provider]['endpoint'] or local_only:
            raise ProviderError('Cloud credentials are restricted to the selected official endpoint.')
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers(local_only=local_only,provider=provider),
        method="POST",
    )
    try:
        with _urlopen(request, timeout) as response:
            body = response.read().decode("utf-8")
            transport = safe_rate_headers(response.headers)
    except urllib.error.HTTPError as exc:
        # Classify service failures without forwarding its possibly private body.
        detail=exc.read(8192).decode('utf-8',errors='replace').lower()
        if provider:
            from .ai_providers import ProviderError
            code='continuation_failed'
            if exc.code in (401,403):code='authentication'
            elif exc.code==402 or 'insufficient_quota' in detail or 'quota exhausted' in detail:code='quota_exhausted'
            elif exc.code==429:code='rate_limit'
            elif exc.code==404:code='model_unavailable'
            elif 'context' in detail and any(x in detail for x in ('limit','exceed','long')):code='context_limit'
            elif exc.code in (400,422):code='provider_contract'
            raise ProviderError('The cloud request failed. See safe diagnostics; no provider or paid model was substituted.',code,{'http_status':exc.code,**safe_rate_headers(exc.headers)}) from None
        if any(x in detail for x in ('out of memory','not enough memory','insufficient memory','cuda out','requires more system memory','failed to allocate','cannot allocate memory')):
            error=ConnectionError('Model service reported insufficient memory.');error.code='out_of_memory';error.measurements={'http_status':exc.code};raise error from None
        if local_only:
            message=f"Local model service returned HTTP {exc.code}; check the installed model, runtime version and available memory. No API key is required."
        else:message=f"Model service returned HTTP {exc.code}; check credentials, model access and endpoint configuration."
        error=ConnectionError(message);error.code='continuation_failed' if exc.code>=500 else 'unavailable';error.measurements={'http_status':exc.code}
        raise error from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if isinstance(exc,(TimeoutError,socket.timeout)) or isinstance(getattr(exc,'reason',None),(TimeoutError,socket.timeout)):
            raise TimeoutError('Model request timed out.') from None
        raise ConnectionError("Model service could not be reached. Check endpoint and connectivity.") from None
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("Local model returned non-object JSON.")
    if provider and isinstance(data.get('error'),dict):
        from .ai_providers import ProviderError
        status=data['error'].get('code')
        code={401:'authentication',403:'authentication',402:'quota_exhausted',429:'rate_limit',404:'model_unavailable',400:'provider_contract',422:'provider_contract'}.get(status,'continuation_failed')
        raise ProviderError('The cloud provider returned an error instead of a completion; no outcome was applied.',code,{'http_status':status if type(status)is int else None,**transport})
    if provider:data['_caerness_transport']=transport
    return data


def safe_rate_headers(headers):
    """Only numerical quota headers, with explicit provider units; never arbitrary headers."""
    result={}
    for name in ('retry-after','x-ratelimit-limit-requests','x-ratelimit-remaining-requests','x-ratelimit-limit-tokens','x-ratelimit-remaining-tokens'):
        value=headers.get(name) if headers else None
        try:
            number=float(value)
            if 0<=number<1e12:result[name]=number
        except (TypeError,ValueError):pass
    return result


def local_health(conn: sqlite3.Connection) -> dict[str, Any]:
    cfg = runtime_config(conn)
    if cfg.get('ai_provider') in {'groq','gemini','openrouter'}:
        from .ai_providers import validate,ProviderError
        try:
            validate(cfg)
            return {'ok':True,'status':'catalog_verified_not_inference','backend':cfg['local_backend'],'model':cfg['local_model']}
        except ProviderError as error:return {'ok':False,'status':error.code,'error':str(error)}
    if cfg["local_backend"] == "disabled":
        return {"ok": False, "status": "disabled", "backend": "disabled", "model": cfg["local_model"]}

    endpoint = str(cfg["local_endpoint"])
    timeout = min(5, int(cfg["local_timeout_seconds"]))
    _validate_endpoint(endpoint)
    candidates: list[str] = []
    if cfg["local_backend"] == "openai_compatible":
        base = endpoint.split("/v1/chat/completions")[0].rstrip("/")
        candidates = [base + "/health", base + "/v1/models"]
    elif cfg["local_backend"] == "ollama_native":
        base = endpoint.split("/api/chat")[0].rstrip("/")
        candidates = [base + "/api/tags"]

    last_error = ""
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers=_headers(local_only=not cfg.get('remote_model')), method="GET")
            with _urlopen(req, timeout) as response:
                if 200 <= response.status < 300:
                    return {
                        "ok": True,
                        "status": "available",
                        "backend": cfg["local_backend"],
                        "endpoint": endpoint,
                        "model": cfg["local_model"],
                    }
        except Exception as exc:  # diagnostics only
            last_error = f"HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) else "Model service could not be reached."
    return {
        "ok": False,
        "status": "unavailable",
        "backend": cfg["local_backend"],
        "endpoint": endpoint,
        "model": cfg["local_model"],
        "error": last_error,
    }


def chat_local(
    conn: sqlite3.Connection,
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float = 0.65,
    require_json: bool = False,
    response_schema: dict[str, Any] | None = None,
) -> LocalModelResult:
    cfg = runtime_config(conn)
    from .ai_providers import provider_id,validate,adapt_payload
    cloud=provider_id(cfg)
    cloud_choice=validate(cfg) if cloud else None
    backend = str(cfg["local_backend"])
    if backend == "disabled":
        raise RuntimeError("Local model backend is disabled.")
    endpoint = str(cfg["local_endpoint"])
    model = str(cfg["local_model"])
    timeout = int(cfg["local_timeout_seconds"])
    max_tokens = int(max_tokens or cfg["local_max_output_tokens"])
    # Chat models tokenize content, not JSON transport escaping. Local structured
    # output schemas compile to grammar, not input tokens. Reserve template margin.
    input_estimate=sum(estimate_tokens(m['content'])+8 for m in messages)+64
    if cloud_choice:
        max_tokens=min(max_tokens,cloud_choice['output'])
        # Remote schemas may count towards provider context. Never silently trim history.
        input_estimate+=estimate_tokens(response_schema) if response_schema else 0
    if (cfg.get("free_local") or cloud) and input_estimate + max_tokens > min(int(cfg['local_heavy_context_tokens']),cloud_choice['context'] if cloud_choice else int(cfg['local_heavy_context_tokens'])):
        raise ValueError("This request exceeds the configured local context budget. No truncated interpretation was applied.")
    if cfg.get("free_local") and urlsplit(endpoint).port == 11434:
        parsed = urlsplit(endpoint)
        info = _post_json(f"{parsed.scheme}://{parsed.netloc}/api/show", {"model": model}, min(timeout, 10), local_only=True)
        if info.get("remote_model") or info.get("remote_host"):
            raise ValueError("This model alias delegates to a cloud service; free local inference was not started.")

    started = time.perf_counter()
    if backend == "openai_compatible":
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": max_tokens,
            "stream": False,
        }
        if require_json:
            # llama.cpp and several compatible servers accept this; servers that ignore it are still validated later.
            payload["response_format"] = {"type": "json_object"}
        if response_schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "caerness_response", "strict": True, "schema": response_schema}}
        if cfg.get("free_local") and urlsplit(endpoint).port == 11434:
            payload["reasoning_effort"] = "none"
        if cloud:
            payload=adapt_payload(cfg,payload,response_schema)
            data=_post_json(endpoint,payload,timeout,provider=cloud)
        else:data = _post_json(endpoint, payload, timeout, local_only=not cfg.get('remote_model'))
        usage=data.get('usage') if isinstance(data.get('usage'),dict) else {}
        try:
            choice=data['choices'][0]
            text = choice['message']['content']
            if not isinstance(text,str) or not text.strip():raise ValueError('Missing text')
            finish=choice.get('finish_reason')
        except Exception as exc:
            raise ModelResponseError('The model response lacked usable message content.','invalid_response',usage,time.perf_counter()-started) from None
        if finish == "length":
            raise ModelResponseError("Model output reached its token limit; no incomplete response was applied.",'incomplete_response',usage,time.perf_counter()-started)
        if cloud and finish not in ('stop',):
            raise ModelResponseError('The provider did not finish a usable JSON response.','invalid_response',usage,time.perf_counter()-started)
        return LocalModelResult(
            text=text,
            backend=backend,
            model=model,
            prompt_tokens=_token_count(usage.get("prompt_tokens")),
            completion_tokens=_token_count(usage.get("completion_tokens")),
            raw=data,
            latency_seconds=round(time.perf_counter() - started, 4),
        )

    if backend == "ollama_native":
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": float(temperature), "num_predict": max_tokens},
        }
        if require_json:
            payload["format"] = "json"
        if response_schema is not None:payload['format']=response_schema
        if cfg.get('free_local'):payload['think']=False
        data = _post_json(endpoint, payload, timeout,local_only=not cfg.get('remote_model'))
        if data.get('done_reason')=='length':raise ModelResponseError('Model output reached its token limit; no incomplete response was applied.','incomplete_response',{'prompt_tokens':data.get('prompt_eval_count'),'completion_tokens':data.get('eval_count')},time.perf_counter()-started)
        try:
            text = str(data["message"]["content"])
        except Exception as exc:
            raise ValueError("Ollama-native local response lacked message.content") from exc
        return LocalModelResult(
            text=text,
            backend=backend,
            model=model,
            prompt_tokens=_token_count(data.get("prompt_eval_count")),
            completion_tokens=_token_count(data.get("eval_count")),
            raw=data,
            latency_seconds=round(time.perf_counter() - started, 4),
        )

    raise ValueError(f"Unsupported local backend: {backend}")
