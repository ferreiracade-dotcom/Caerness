"""Streamable HTTP entry point (stateless, JSON responses) for the remote connector."""
from __future__ import annotations

from urllib.parse import urlparse

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from connector.settings import Settings

ALLOWED_ORIGINS = ["https://claude.ai", "https://claude.com"]


def _host_of(public_url: str) -> str:
    return urlparse(public_url).netloc


def build_app(settings: Settings, provider=None, *, allowed_hosts=()) -> Starlette:
    from connector import server

    if settings.public_url is not None and provider is None:
        raise RuntimeError("a public deployment requires authentication; refusing to serve it open")
    hosts = [h for h in [_host_of(settings.public_url) if settings.public_url else None, *allowed_hosts] if h]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[*hosts, "127.0.0.1:*", "localhost:*"],
        allowed_origins=list(ALLOWED_ORIGINS),
    )

    @server.mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    return server.mcp.streamable_http_app(
        stateless_http=True, json_response=True, transport_security=security, host="127.0.0.1")
