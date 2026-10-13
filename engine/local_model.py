from __future__ import annotations

import json
import os
import time
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


def _headers(*, local_only=False):
    if local_only or os.environ.get("CAERNESS_FREE_LOCAL") == "1":
        return {"Content-Type": "application/json"}
    key = os.environ.get("CAERNESS_MODEL_API_KEY") or os.environ.get("OPENAI_API_KEY")
    return {"Content-Type": "application/json", **({"Authorization": "Bearer " + key} if key else {})}


def _post_json(url: str, payload: dict[str, Any], timeout: int, *, local_only=False) -> dict[str, Any]:
    _validate_endpoint(url)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers(local_only=local_only),
        method="POST",
    )
    try:
        with _urlopen(request, timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if local_only:
            raise ConnectionError(f"Local model service returned HTTP {exc.code}; check the installed model, runtime version and available memory. No API key is required.") from None
        raise ConnectionError(f"Model service returned HTTP {exc.code}; check credentials, model access and endpoint configuration.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ConnectionError("Model service could not be reached or timed out. Check endpoint and connectivity.") from None
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("Local model returned non-object JSON.")
    return data


def local_health(conn: sqlite3.Connection) -> dict[str, Any]:
    cfg = runtime_config(conn)
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
            req = urllib.request.Request(url, headers=_headers(local_only=cfg.get("free_local", False)), method="GET")
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
    backend = str(cfg["local_backend"])
    if backend == "disabled":
        raise RuntimeError("Local model backend is disabled.")
    endpoint = str(cfg["local_endpoint"])
    model = str(cfg["local_model"])
    timeout = int(cfg["local_timeout_seconds"])
    max_tokens = int(max_tokens or cfg["local_max_output_tokens"])
    if cfg.get("free_local") and estimate_tokens(messages) + max_tokens > 8192:
        raise ValueError("This request exceeds the configured 8K local context. No truncated interpretation was applied.")
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
        data = _post_json(endpoint, payload, timeout, local_only=cfg.get("free_local", False))
        try:
            text = str(data["choices"][0]["message"]["content"])
        except Exception as exc:
            raise ValueError("OpenAI-compatible local response lacked choices[0].message.content") from exc
        usage = data.get("usage") or {}
        if data["choices"][0].get("finish_reason") == "length":
            raise ValueError("Model output reached its token limit; no incomplete response was applied.")
        return LocalModelResult(
            text=text,
            backend=backend,
            model=model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
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
        data = _post_json(endpoint, payload, timeout)
        try:
            text = str(data["message"]["content"])
        except Exception as exc:
            raise ValueError("Ollama-native local response lacked message.content") from exc
        return LocalModelResult(
            text=text,
            backend=backend,
            model=model,
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            raw=data,
            latency_seconds=round(time.perf_counter() - started, 4),
        )

    raise ValueError(f"Unsupported local backend: {backend}")
