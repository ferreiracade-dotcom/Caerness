"""Streamable HTTP entry point (stateless, JSON responses) for the remote connector."""
from __future__ import annotations

from urllib.parse import urlparse

from mcp.server.auth.routes import build_metadata, cors_middleware
from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from connector.settings import Settings

ALLOWED_ORIGINS = ["https://claude.ai", "https://claude.com"]
METADATA_PATH = "/.well-known/oauth-authorization-server"


def _host_of(public_url: str) -> str:
    return urlparse(public_url).netloc


def _auth_settings(public_url: str) -> AuthSettings:
    return AuthSettings(
        issuer_url=public_url,
        resource_server_url=f"{public_url}/mcp",
        client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=["play"], default_scopes=["play"]),
        revocation_options=RevocationOptions(enabled=True),
        required_scopes=["play"],
        validate_token_resource=True,
    )


def build_server(settings: Settings, provider=None) -> MCPServer:
    """The six tools on a fresh MCPServer; with a public URL it also carries the OAuth server and /login."""
    from connector import server

    if settings.public_url is None:
        mcp = server.register_tools(server.make_mcp())
    else:
        from connector.auth_store import AuthStore
        from connector.oauth import OwnerOAuthProvider, register_login_routes

        if not settings.passphrase_hash:
            raise ValueError("CAERNESS_PASSPHRASE_HASH is required when CAERNESS_PUBLIC_URL is set "
                             "(run python -m connector.set_passphrase)")
        provider = provider or OwnerOAuthProvider(AuthStore(settings.auth_db_path), settings)
        mcp = server.make_mcp(auth_server_provider=provider, auth=_auth_settings(settings.public_url))
        server.register_tools(mcp)
        register_login_routes(mcp, provider)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    return mcp


def _advertise_public_clients(app: Starlette, mcp: MCPServer) -> None:
    """Claude registers as a public client (PKCE, no secret); say so in the discovery document.

    The SDK's metadata only lists client_secret_* methods, so the route is replaced with one that
    lists "none" (register_client forces every client to that method).
    """
    auth = mcp.settings.auth
    metadata = build_metadata(auth.issuer_url, auth.service_documentation_url,
                              auth.client_registration_options, auth.revocation_options)
    metadata.token_endpoint_auth_methods_supported = ["none"]
    if metadata.revocation_endpoint:
        metadata.revocation_endpoint_auth_methods_supported = ["none"]
    route = Route(METADATA_PATH, endpoint=cors_middleware(MetadataHandler(metadata).handle, ["GET", "OPTIONS"]),
                  methods=["GET", "OPTIONS"])
    app.router.routes.insert(0, route)


def build_app(settings: Settings, provider=None, *, allowed_hosts=()) -> Starlette:
    mcp = build_server(settings, provider)
    hosts = [h for h in [_host_of(settings.public_url) if settings.public_url else None, *allowed_hosts] if h]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[*hosts, "127.0.0.1:*", "localhost:*"],
        allowed_origins=list(ALLOWED_ORIGINS),
    )
    app = mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=security, host="127.0.0.1")
    if settings.public_url is not None:
        _advertise_public_clients(app, mcp)
    return app
