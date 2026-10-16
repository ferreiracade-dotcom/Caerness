"""Single-owner OAuth 2.1 authorization server for the remote connector.

Built on the SDK's OAuthAuthorizationServerProvider hooks. One person (the owner) signs in with a
passphrase on /login; Claude registers itself (dynamic client registration, restricted to the
claude.ai callback), uses PKCE S256, and receives rotating refresh tokens.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import json
import secrets
import time
import uuid
from urllib.parse import parse_qs, urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from connector.auth_store import AuthStore
from connector.settings import Settings

SCOPE = "play"
ACCESS_TTL = 3600
REFRESH_TTL = 90 * 86400
CODE_TTL = 300
PENDING_TTL = 600
MAX_CLIENTS = 200
CLIENT_UNUSED_TTL = 86400
LOGIN_WINDOW = 900
LOGIN_MAX_FAILURES = 5
MAX_LOGIN_BODY = 4096

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**15, 8, 1
_SCRYPT_MAXMEM = 128 * 1024 * 1024


# --- passphrase hashing ---------------------------------------------------------------------------------
def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_passphrase(passphrase: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                         maxmem=_SCRYPT_MAXMEM, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(key)}"


def verify_passphrase(passphrase: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        if not (2**10 <= n <= 2**20 and 1 <= r <= 16 and 1 <= p <= 4):
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(key_b64)
        key = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                             maxmem=_SCRYPT_MAXMEM, dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(key, expected)


# --- provider ------------------------------------------------------------------------------------------------
class OwnerOAuthProvider:
    def __init__(self, store: AuthStore, settings: Settings, now=time.time):
        self.store = store
        self.settings = settings
        self.now = now
        self.store.ensure_schema()

    @property
    def resource(self) -> str:
        return f"{self.settings.public_url}/mcp"

    # clients
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        raw = self.store.get_client_json(client_id)
        return OAuthClientInformationFull.model_validate_json(raw) if raw else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        allowed = set(self.settings.owner_redirect_uris)
        uris = [str(u) for u in (client_info.redirect_uris or [])]
        if not uris or any(u not in allowed for u in uris):
            raise RegistrationError("invalid_redirect_uri", "redirect_uri is not allowed for this server")
        if not set(client_info.grant_types) <= {"authorization_code", "refresh_token"}:
            raise RegistrationError("invalid_client_metadata", "unsupported grant_types")
        if list(client_info.response_types) != ["code"]:
            raise RegistrationError("invalid_client_metadata", "response_types must be ['code']")
        now = self.now()
        self.store.prune_unused_clients(now - CLIENT_UNUSED_TTL)
        if self.store.count_clients() >= MAX_CLIENTS:
            raise RegistrationError("invalid_client_metadata", "too many registered clients")
        # Always a public client with PKCE: no secret is minted or accepted.
        client_info.token_endpoint_auth_method = "none"
        client_info.client_secret = None
        client_info.client_secret_expires_at = None
        client_info.grant_types = ["authorization_code", "refresh_token"]
        if client_info.client_name:
            client_info.client_name = client_info.client_name[:100]
        self.store.put_client(client_info.client_id, client_info.model_dump_json(exclude_none=True), now)

    # authorization
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if str(params.redirect_uri) not in self.settings.owner_redirect_uris:
            raise AuthorizeError("invalid_request", "redirect_uri is not allowed for this server")
        if params.resource is not None and params.resource.rstrip("/") != self.resource:
            raise AuthorizeError("invalid_target", "unknown resource")
        scopes = list(params.scopes or [SCOPE])
        if scopes != [SCOPE]:
            raise AuthorizeError("invalid_scope", "only the play scope exists")
        req_id = secrets.token_urlsafe(32)
        stored = params.model_copy(update={"scopes": scopes}).model_dump_json()
        self.store.put_pending(req_id, client.client_id, stored, self.now() + PENDING_TTL)
        return f"{self.settings.public_url}/login?req={req_id}"

    def pending(self, req_id: str) -> tuple[OAuthClientInformationFull, AuthorizationParams] | None:
        row = self.store.get_pending(req_id, self.now()) if req_id else None
        if row is None:
            return None
        raw = self.store.get_client_json(row["client_id"])
        if raw is None:
            return None
        return (OAuthClientInformationFull.model_validate_json(raw),
                AuthorizationParams.model_validate_json(row["params_json"]))

    def finish_login(self, req_id: str) -> str | None:
        """After a correct passphrase: consume the pending request and return the redirect to the client."""
        row = self.store.take_pending(req_id, self.now())
        if row is None:
            return None
        params = AuthorizationParams.model_validate_json(row["params_json"])
        if str(params.redirect_uri) not in self.settings.owner_redirect_uris:
            return None
        code = secrets.token_urlsafe(32)
        payload = {"scopes": params.scopes or [SCOPE], "client_id": row["client_id"],
                   "code_challenge": params.code_challenge, "redirect_uri": str(params.redirect_uri),
                   "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                   "resource": self.resource, "subject": "owner"}
        self.store.put_code(code, json.dumps(payload), self.now() + CODE_TTL, uuid.uuid4().hex)
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str):
        row = self.store.get_code(authorization_code)
        if row is None:
            return None
        if row["used"]:  # a replayed code: everything issued from it is revoked
            self.store.revoke_family(row["family_id"])
            return None
        payload = json.loads(row["payload_json"])
        if payload["client_id"] != client.client_id:
            return None
        return AuthorizationCode(code=authorization_code, expires_at=row["expires_at"], **payload)

    def _issue(self, client_id: str, scopes: list[str], family_id: str) -> OAuthToken:
        now = self.now()
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        scope = " ".join(scopes)
        self.store.put_token(access, "access", client_id, scope, now + ACCESS_TTL, family_id)
        self.store.put_token(refresh, "refresh", client_id, scope, now + REFRESH_TTL, family_id)
        self.store.prune_tokens(now)
        return OAuthToken(access_token=access, expires_in=ACCESS_TTL, scope=scope, refresh_token=refresh)

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        row = self.store.get_code(authorization_code.code)
        if row is None or not self.store.use_code(authorization_code.code):
            raise TokenError("invalid_grant", "authorization code already used")
        return self._issue(client.client_id, list(authorization_code.scopes), row["family_id"])

    # refresh
    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        row = self.store.get_token(refresh_token)
        if row is None or row["kind"] != "refresh" or row["client_id"] != client.client_id:
            return None
        if row["rotated"]:  # an already-used refresh token came back: assume it leaked, end the whole family
            self.store.revoke_family(row["family_id"])
            return None
        if row["revoked"] or row["expires_at"] < self.now():
            return None
        return RefreshToken(token=refresh_token, client_id=row["client_id"], scopes=row["scopes"].split(),
                            expires_at=int(row["expires_at"]), resource=self.resource, subject="owner")

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken,
                                     scopes: list[str]) -> OAuthToken:
        if not self.store.rotate_refresh(refresh_token.token, client.client_id):
            raise TokenError("invalid_grant", "refresh token is no longer valid")
        row = self.store.get_token(refresh_token.token)
        return self._issue(client.client_id, list(scopes or refresh_token.scopes), row["family_id"])

    # access
    async def load_access_token(self, token: str) -> AccessToken | None:
        row = self.store.get_token(token)
        if row is None or row["kind"] != "access" or row["revoked"] or row["expires_at"] < self.now():
            return None
        return AccessToken(token=token, client_id=row["client_id"], scopes=row["scopes"].split(),
                           expires_at=int(row["expires_at"]), resource=self.resource, subject="owner")

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        row = self.store.get_token(token.token)
        if row is not None:
            self.store.revoke_family(row["family_id"])

    # login throttle: global, because the proxy hides client addresses from the app
    def login_locked(self) -> bool:
        return self.store.count_login_failures(self.now() - LOGIN_WINDOW) >= LOGIN_MAX_FAILURES

    def record_login_failure(self, ip: str | None) -> None:
        self.store.add_login_failure(self.now(), ip)


# --- login page ------------------------------------------------------------------------------------------------
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
}

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Caerness sign-in</title>
<style>body{{font-family:system-ui,sans-serif;max-width:26rem;margin:3rem auto;padding:0 1rem;line-height:1.4}}
input,button{{font:inherit;padding:.6rem;width:100%;box-sizing:border-box;margin-top:.6rem}}
.msg{{color:#9a1c1c}}</style></head><body>
<h1>Caerness</h1>
{body}
</body></html>"""


def _page(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(body=body), status_code=status, headers=_SECURITY_HEADERS)


def _form(req_id: str, client_name: str, redirect_host: str, message: str = "") -> HTMLResponse:
    msg = f'<p class="msg">{html.escape(message)}</p>' if message else ""
    body = (f"<p>Allow <strong>{html.escape(client_name)}</strong> ({html.escape(redirect_host)}) to play Caerness?</p>{msg}"
            f'<form method="post" action="/login"><input type="hidden" name="req" value="{html.escape(req_id)}">'
            '<label>Passphrase<input type="password" name="passphrase" autocomplete="current-password" required autofocus></label>'
            '<button type="submit">Sign in</button></form>')
    return _page(body)


async def _read_form(request: Request) -> dict[str, str] | None:
    if "application/x-www-form-urlencoded" not in request.headers.get("content-type", ""):
        return None
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_LOGIN_BODY:
        return None
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_LOGIN_BODY:
            return None
    try:
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    except UnicodeDecodeError:
        return None
    return {k: v[0] for k, v in parsed.items()}


def register_login_routes(mcp, provider: OwnerOAuthProvider) -> None:
    expired = ("<p>This sign-in link has expired or was already used. Start again from Claude.</p>")

    def describe(client: OAuthClientInformationFull, params: AuthorizationParams) -> tuple[str, str]:
        return (client.client_name or "An application", urlparse(str(params.redirect_uri)).netloc)

    @mcp.custom_route("/login", methods=["GET"])
    async def login_form(request: Request) -> Response:
        req_id = request.query_params.get("req", "")
        found = provider.pending(req_id)
        if found is None:
            return _page(expired, 400)
        name, host = describe(*found)
        return _form(req_id, name, host)

    @mcp.custom_route("/login", methods=["POST"])
    async def login_submit(request: Request) -> Response:
        form = await _read_form(request)
        if form is None:
            return _page("<p>Bad request.</p>", 400)
        req_id, passphrase = form.get("req", ""), form.get("passphrase", "")
        found = provider.pending(req_id)
        if found is None:
            return _page(expired, 400)
        name, host = describe(*found)
        if provider.login_locked():
            return _form(req_id, name, host, "That did not work. Too many attempts; try again later.")
        stored = provider.settings.passphrase_hash or ""
        ok = await asyncio.to_thread(verify_passphrase, passphrase, stored)
        if not ok:
            provider.record_login_failure(request.client.host if request.client else None)
            return _form(req_id, name, host, "That did not work.")
        target = provider.finish_login(req_id)
        if target is None:
            return _page(expired, 400)
        return RedirectResponse(target, status_code=303, headers=_SECURITY_HEADERS)
