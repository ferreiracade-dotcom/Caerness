# Remote Connector on Oracle Cloud Always Free: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The engine, the campaign database and the connector run on an Oracle Cloud Always Free VM, and the owner plays Caerness from any Claude app (phone included, Claude Pro) by adding the VM as a custom connector on claude.ai, with no laptop involved.

**Architecture:** The existing six-tool `MCPServer` in `connector/server.py` gains a second entry point that serves it over Streamable HTTP (stateless, JSON responses) behind Caddy, which terminates HTTPS on a free DuckDNS hostname. Authentication is a small single-owner OAuth 2.1 authorization server built on the SDK's `OAuthAuthorizationServerProvider` hooks (dynamic client registration, PKCE, refresh rotation, one passphrase login page), with tokens persisted in a separate SQLite file. Tools, per-call connections, the stdout guard and idempotent `call_id`s are unchanged. The campaign file lives in `/var/lib/caerness/campaigns`, is snapshotted automatically with the SQLite backup API, and is updated by `git pull` plus `systemctl restart`.

**Tech Stack:** Python 3.13, `mcp==2.3.0` (adds Starlette and uvicorn), numpy, SQLite (WAL), Caddy 2, systemd, Ubuntu on Oracle Ampere A1 (arm64), DuckDNS.

**Spec:** `docs/superpowers/specs/2026-10-16-claude-connector-design.md` (§2 "PC only for now", §3 non-goals, §4 shape, §5 tools, §6 idempotent retries, §9 token budget). Style and conventions follow `docs/superpowers/plans/2026-10-16-claude-connector-step1.md`. Owner decision of 2026-10-16 (this conversation): the connector is hosted remotely so no laptop is needed; this **supersedes** the spec's "PC only for now, no paid hosting, phone later" decision (Task 0 records it).

## Verified facts this plan relies on (sources)

Verified by reading the pages on 2026-10-16:

- **Custom connectors on Pro, used on mobile.** "You add custom connectors to your own account" on Free, Pro, Max (Free limited to one); add via Customize > Connectors > Add custom connector. A connected connector "is available in your conversations on the web, desktop, and mobile"; the Claude mobile app supports remote connectors. Source: https://claude.com/docs/connectors/custom/add-unlisted and https://claude.com/docs/connectors/getting-started.md
- **Transport.** Streamable HTTP is the recommended transport; HTTP+SSE is legacy and being deprecated. Source: https://claude.com/docs/connectors/building/index.md
- **Limits.** claude.ai and Desktop: max tool result about 150,000 characters; tool call timeout 240 seconds. Source: same page.
- **Auth types.** OAuth 2.0 with Dynamic Client Registration (`oauth_dcr`) and with Client ID Metadata Documents (`oauth_cimd`) are supported by default; no-auth is supported. Static request-header credentials ("static_headers") are **beta, limited organizations, entered by an organization Owner**, so they are not available to a personal Pro account. Because an authless public URL would be open to anyone, this plan uses OAuth. Source: https://claude.com/docs/connectors/building/authentication
- **OAuth requirements of Claude's client** (same page): a `401` with `WWW-Authenticate: Bearer resource_metadata="..."` is required to start sign-in (a header on a `200` is ignored); protected-resource metadata `resource` must equal the connector URL exactly, and only the first `authorization_servers` entry is used; PKCE S256 is sent on every authorization request; redirect URI for the hosted apps (web, desktop, mobile, Cowork) is exactly `https://claude.ai/api/mcp/auth_callback`; `/token` must accept `application/x-www-form-urlencoded`; refresh tokens must be rotated for public clients and an invalid one must return `invalid_grant`; discovery, registration and token endpoints must answer within 10 s (refresh 30 s); Anthropic's outbound range is `160.79.104.0/21`. "Register automatically" in the Add dialog uses DCR; "Use Claude's published identity" uses CIMD and falls back to DCR unless the server advertises both CIMD values.
- **Oracle Always Free** (https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm): up to 2 AMD `VM.Standard.E2.1.Micro` instances (1/8 OCPU, 1 GB RAM, 50 Mbps each); Arm `VM.Standard.A1.Flex` allowance, as that page reads on 2026-10-16, of **1,500 OCPU-hours and 9,000 GB-hours a month (= 2 OCPU and 12 GB running continuously)** (older material says 4 OCPU / 24 GB, so re-read the figure in the console when sizing); 200 GB total boot+block storage; 5 volume backups; 10 TB/month outbound; compute and volumes must be in the **home region**; 2 VCNs. **Idle reclamation:** an Always Free instance is idle, and may be reclaimed, if over 7 days the 95th-percentile CPU and network utilization are each below 20% (and memory below 20% on A1). A quiet single-player game will meet that definition. Converting the account to Pay As You Go removes the reclamation risk, and nothing is charged while usage stays within the Always Free limits (Oracle notice quoted at https://blog.51sec.org/2023/02/oracle-cloud-cleaning-up-idle-compute.html; third-party quote of an Oracle notice, so treat the exemption as **unverified against Oracle's current docs** and re-read the Free Tier page at upgrade time).
- **SDK (`mcp` 2.3.0, read locally at `Lib/site-packages/mcp/server/`).** `MCPServer(auth_server_provider=..., auth=AuthSettings(issuer_url, resource_server_url, client_registration_options, revocation_options, required_scopes, validate_token_resource))` makes `streamable_http_app()` mount the OAuth endpoints (`/.well-known/oauth-authorization-server`, `/authorize`, `/token`, `/register`, optional `/revoke`), the protected-resource metadata route, and `RequireAuthMiddleware` returning `401` with `resource_metadata`. `@mcp.custom_route(path, methods)` adds unauthenticated routes (used for the login page and `/health`). `streamable_http_app(stateless_http=True, json_response=True, transport_security=...)` works; I confirmed a stateless `initialize` and `tools/list` round trip against the current `server.mcp` with Starlette's `TestClient`. **Finding:** with the default settings the app answers `421 Invalid Host header` for any Host other than localhost, so behind Caddy `TransportSecuritySettings(allowed_hosts=[<public host>])` is mandatory (Task 1 test pins it). Sync tool functions run in worker threads (`anyio.to_thread.run_sync`), so a long `advance` does not block the event loop. `python-multipart` is not installed, so the login form is parsed by hand.

**Not verified (marked again where used):** (a) whether the Claude **mobile** app can *add* a custom connector (docs say mobile *uses* connectors you add; the plan adds it once from claude.ai in a browser); (b) exact Oracle sign-up requirements and A1 capacity in the owner's chosen region ("Out of host capacity" is common for A1; unverified here); (c) Ubuntu/Oracle image firewall defaults (believed to block 80/443 in iptables until opened; verify on the VM); (d) numpy 2.x and uv Python 3.13 wheels for aarch64 (expected to exist; Task 4 verifies on the VM); (e) DuckDNS terms/reliability and that Caddy HTTP-01 works with it (Caddy's automatic HTTPS needs A record + ports 80/443 per https://caddyserver.com/docs/automatic-https; DuckDNS sign-in and 5 free subdomains per a third-party guide); (f) whether Claude honours `refresh_token` expiry values we choose (we choose long ones and rely on rotation).

## Decisions (with reasons)

1. **Auth: single-owner OAuth 2.1 authorization server inside the connector process, passphrase login.** Static headers are not available to a personal Pro account, and authless would expose a game-state-changing endpoint to anyone who learns the URL. The SDK already implements DCR, PKCE, metadata and bearer enforcement; we implement the provider protocol (storage plus a login page). DCR is restricted so only `https://claude.ai/api/mcp/auth_callback` is an accepted redirect URI, and `/authorize` only completes after the passphrase. The passphrase is stored as a scrypt hash in a root-only env file; failed attempts are throttled.
2. **HTTPS: Caddy + DuckDNS, HTTP-01 challenge.** Free, one binary, certificates issued and renewed with no tooling (https://caddyserver.com/docs/automatic-https). Cloudflare Tunnel was rejected: a stable hostname needs a domain owned and delegated to Cloudflare (a cost), and the free "quick tunnel" URL changes whenever it restarts, which would force re-adding the connector (unverified here, widely documented). The hostname is a random, unguessable DuckDNS label to cut scanner noise; security does not depend on it.
3. **Stateless Streamable HTTP with JSON responses.** The server holds no per-session memory (each call opens its own SQLite connection already), so service restarts, deploys and phone network changes never strand a session.
4. **One writer at a time.** Tool calls run in threads; the `_call` helper in `connector/server.py` gains a process-wide `threading.Lock` so two concurrent calls never interleave on one campaign (also protects the global `redirect_stdout` guard).
5. **Backups use `sqlite3.Connection.backup()`**, never file copy (WAL). Daily timer, plus a throttled snapshot before every `advance`, rotated.
6. **Instance:** Ampere A1 if capacity allows (1 OCPU / 6 GB is plenty; an `advance` is single-threaded), else AMD E2.1.Micro with 2 GB swap (works only if peak memory in Task 6 is under about 700 MB).

## Global Constraints

- Never write the packaged `data/caerness.db`. Campaigns are copies under `CAERNESS_CAMPAIGN_DIR`. Tests use temp directories.
- No raw SQL tool, no Python-exec tool, no tool that edits arbitrary world data. The six tools and their schemas do not change (existing `tests/connector_server_test.py` size limits still pass).
- Stdio must keep working exactly as today: `connector/run_server.py` with no flag still serves stdio; `tests/connector_server_test.py` stays green.
- Every tool call still opens and closes its own connection and runs with stdout redirected to stderr.
- No secrets in the repository or in URLs. Tokens never in query strings. Tokens and passphrases are stored hashed (SHA-256 for random 256-bit tokens, scrypt for the passphrase). Secrets live in `/etc/caerness/caerness.env`, mode 600.
- The public hostname, passphrase and campaign file are never committed. `.gitignore` already excludes `*.db`-sidecars; add `deploy/*.env` and `*.bak`.
- Tests follow the repo convention: `tests/<name>_test.py`, a `run()` function, `if __name__ == "__main__": run()`, plain `assert`s, final `print(...passed...)`. Run one with `PYTHONPATH=. "$PY" tests/<name>_test.py` where `PY="$LOCALAPPDATA/Programs/Python/Python313/python.exe"`. They are picked up by `tools/run_suite.py`.
- Commit after each task on `feat/claude-connector`. **Do not push** until the owner says so (the VM pulls from GitHub, so the owner pushes when ready for Task 7).
- Time budget: one tool call must finish well inside Claude's 240 s limit. Acceptance target for a 30-day `advance` on the VM: under 90 s; abort-and-lower-the-cap above 150 s (Task 6).
- Python 3.13 on the VM. Dependencies: `connector/requirements.txt` (`mcp==2.3.0`) plus numpy.

## Review Focus

1. **Host header rejected behind the proxy (`421`).** Caddy forwards the public Host; the SDK rejects it unless allowed. Test in Task 1: request with `Host: game.example.duckdns.org` succeeds when configured, and a different Host is refused.
2. **Open registration is an open door.** Anyone can POST `/register`. A client registered with an attacker redirect URI must not be able to receive a code. Test in Task 2: `/register` with a redirect URI other than the claude.ai callback is rejected.
3. **Passphrase brute force on the public login page.** Test in Task 2: after 5 wrong attempts within the window every attempt is refused (even the right passphrase) until the window passes; the response never says which part was wrong.
4. **Restart or redeploy must not sign the phone out.** Tokens and registered clients persist. Test in Task 2: build a second provider on the same auth DB file and the old access and refresh tokens still verify; a rotated-away refresh token returns `invalid_grant` semantics.
5. **A lost laptop-side campaign overwritten by an upload.** `import_campaign` refuses to replace an existing campaign without `--replace` and snapshots the old file first. Test in Task 3. Related: importing a corrupted or non-Caerness SQLite file is refused (integrity check, schema version, a protagonist).

---

## File structure

| File | Responsibility |
|---|---|
| `connector/settings.py` (create) | `Settings` dataclass read from environment; the single place for public URL, auth DB path, passphrase hash, backup dir, caps |
| `connector/auth_store.py` (create) | SQLite persistence for OAuth clients, pending authorizations, codes, access/refresh tokens, login throttle |
| `connector/oauth.py` (create) | `OwnerOAuthProvider` (SDK provider protocol), passphrase hashing, `register_login_routes(mcp, provider)` |
| `connector/http_app.py` (create) | `build_server(settings) -> MCPServer` wiring auth + routes, `build_app(settings) -> Starlette`, `/health` |
| `connector/server.py` (modify) | Expose tools on a reusable `MCPServer`; add the call lock; keep `main()` (stdio) |
| `connector/run_server.py` (modify) | `--transport stdio|http` flag; http runs uvicorn |
| `connector/set_passphrase.py` (create) | CLI that prints the scrypt hash line for the env file (reads passphrase from a prompt, never argv) |
| `connector/backup.py` (create) | `snapshot`, `prune`, `pre_advance_snapshot`, CLI for the timer |
| `connector/import_campaign.py` (create) | Validate and install an uploaded campaign file on the VM |
| `tools/export_campaign.py` (create) | Laptop: consistent single-file export of a campaign via the backup API |
| `connector/timeflow.py` (modify) | Cap read from settings (`CAERNESS_MAX_ADVANCE_DAYS`, default 30) |
| `deploy/` (create) | `caerness.service`, `caerness-backup.service`, `caerness-backup.timer`, `Caddyfile`, `caerness.env.example`, `install.sh`, `update.sh`, `duckdns-update.sh` + `.service/.timer` |
| `tests/connector_http_test.py`, `connector_oauth_test.py`, `connector_backup_test.py`, `connector_import_test.py`, `deploy_files_test.py` (create) | Tests per task |
| `AGENTS.md`, `docs/superpowers/specs/2026-10-16-claude-connector-design.md`, `connector/README.md` (modify) | Supersession and runbook |

---

### Task 0: Record the supersession (docs only)

**Files:**
- Modify: `docs/superpowers/specs/2026-10-16-claude-connector-design.md` (§2 first bullet; §3 non-goals "phone access"; §4 diagram)
- Modify: `AGENTS.md` (§2 "Current direction" paragraph; §3 "Interface" rule)

**Interfaces:** none.

- [ ] **Step 1: Edit the spec.** Add a dated note under the §2 first bullet: "Superseded 2026-10-16 (owner decision): the connector is hosted remotely on an Oracle Cloud Always Free VM and used from any Claude app including mobile, via a custom connector; implementation plan `docs/superpowers/plans/2026-10-16-remote-connector-oracle.md`. 'PC only', 'no paid hosting' and 'phone later' no longer apply (hosting stays free). stdio remains supported for local development." Remove "phone access" from the §3 non-goals list and add a one-line note to the §4 diagram that the transport can also be Streamable HTTP.
- [ ] **Step 2: Edit `AGENTS.md`.** In §2 "Current direction" replace "only through the Claude desktop app (Windows, Claude Pro) via a local MCP connector" with "through the Claude apps (desktop and phone, Claude Pro) via a custom connector hosted on an Oracle Cloud Always Free VM; stdio on the PC remains for development", and list this plan under "Next work". In §3 replace the "Interface" rule with the same decision, keeping "No 20–30 minute waits. Never end narration on a bare 'continue'...".
- [ ] **Step 3: Verify.** `git diff --stat` shows only those two files; `grep -n "PC only" AGENTS.md docs/superpowers/specs/2026-10-16-claude-connector-design.md` returns nothing except inside the superseded note.
- [ ] **Step 4: Commit** `docs: remote Oracle hosting supersedes PC-only connector decision`.

---

### Task 1: HTTP entry point alongside stdio

**Files:**
- Create: `connector/settings.py`, `connector/http_app.py`
- Modify: `connector/server.py`, `connector/run_server.py`, `connector/requirements.txt`
- Test: `tests/connector_http_test.py`

**Interfaces:**
- Produces:
  - `connector.settings.Settings` (frozen dataclass): `public_url: str | None`, `auth_db_path: Path`, `passphrase_hash: str | None`, `owner_redirect_uris: tuple[str, ...]` (default `("https://claude.ai/api/mcp/auth_callback",)`), `campaign: str` (env `CAERNESS_CAMPAIGN`, default `"main"`), `max_advance_days: int` (default 30), `backup_dir: Path | None`. `Settings.from_env(env: Mapping[str, str] = os.environ) -> Settings`. Env names: `CAERNESS_PUBLIC_URL`, `CAERNESS_AUTH_DB`, `CAERNESS_PASSPHRASE_HASH`, `CAERNESS_REDIRECT_URIS` (comma list), `CAERNESS_CAMPAIGN`, `CAERNESS_MAX_ADVANCE_DAYS`, `CAERNESS_BACKUP_DIR`.
  - `connector.http_app.build_app(settings: Settings, provider=None) -> Starlette`: `server.mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(allowed_hosts=[<host of public_url>, "127.0.0.1:*", "localhost:*"], allowed_origins=["https://claude.ai", "https://claude.com"]), host="127.0.0.1")`, plus an unauthenticated `GET /health` returning `{"ok": true}` and nothing else. When `provider` is None (Task 1 only) the app is **unauthenticated and `build_app` raises unless `settings.public_url` is None**; Task 2 makes auth mandatory whenever `public_url` is set.
  - `connector.run_server` accepts `--transport {stdio,http}` (default `stdio`), `--host` (default `127.0.0.1`), `--port` (default `8765`); `http` calls `open_campaign(settings.campaign)` once, then `uvicorn.run(build_app(settings), host=..., port=..., proxy_headers=True, forwarded_allow_ips="127.0.0.1")`.
- Modifies: `connector/server.py::_call(fn)` takes a module-level `threading.Lock` around the existing body; `connector/timeflow.py::MAX_ADVANCE_DAYS` becomes `max_advance_days()` reading `CAERNESS_MAX_ADVANCE_DAYS` (default 30, clamp 1–30).

- [ ] **Step 1: Write the failing test** `tests/connector_http_test.py` (temp `CAERNESS_CAMPAIGN_DIR`, campaign created and protagonist set exactly as `tests/connector_server_test.py` does; Starlette `TestClient`, `base_url="https://game.example.duckdns.org"`, headers `Accept: application/json, text/event-stream`):
  - `initialize` then `tools/list` over `POST /mcp` return 200; tool names equal `["act","advance","lookup","note","resume","scene"]`.
  - `tools/call resume` returns JSON text containing `"rulebook"`; `tools/call note` with the same `call_id` twice returns `replayed: true` the second time (idempotency survives the HTTP path).
  - A request with `Host: other.example.com` returns 421.
  - `GET /health` returns `{"ok": true}`.
  - Stdout guard: monkeypatch `engine.player.get_player` to `print("NOISE")`; run `tools/call scene`; captured real stdout contains no `NOISE` (it goes to stderr).
  - Two threads call `scene` concurrently (via `concurrent.futures`) and both succeed.
  - `Settings.from_env({})` defaults; `CAERNESS_MAX_ADVANCE_DAYS=7` makes `advance(conn, "x", 20, "wait")` run at most 7 days (reuse `tests/connector_advance_test.py` fixtures).
- [ ] **Step 2: Run it, expect failure** (modules missing): `PYTHONPATH=. "$PY" tests/connector_http_test.py`.
- [ ] **Step 3: Install and pin.** `"$PY" -m pip install mcp==2.3.0 uvicorn` (already present locally: uvicorn 0.54.0, starlette 1.8.0); add `uvicorn==0.54.0` and `starlette==1.8.0` to `connector/requirements.txt`.
- [ ] **Step 4: Implement** `connector/settings.py`, `connector/http_app.py`, the `_call` lock and `timeflow.max_advance_days()`, and the `--transport` flag per Interfaces. `run_server.py` keeps its stream `reconfigure` lines; stdio path is byte-for-byte the current `server.main()`.
- [ ] **Step 5: Run the new test and the existing `tests/connector_server_test.py`, `connector_advance_test.py`**; expect all pass (stdio unchanged).
- [ ] **Step 6: Commit** `feat(connector): streamable HTTP entry point (stateless) beside stdio`.

---

### Task 2: Owner authentication (OAuth 2.1 server with passphrase login)

**Files:**
- Create: `connector/auth_store.py`, `connector/oauth.py`, `connector/set_passphrase.py`
- Modify: `connector/http_app.py`
- Test: `tests/connector_oauth_test.py`

**Interfaces:**
- Consumes: `Settings` and `build_app` from Task 1; SDK types `mcp.server.auth.provider.{AuthorizationParams, AuthorizationCode, RefreshToken, AccessToken, AuthorizeError, TokenError, RegistrationError, construct_redirect_uri}`, `mcp.shared.auth.{OAuthClientInformationFull, OAuthToken}`.
- Produces:
  - `connector.auth_store.AuthStore(path: Path)` with `ensure_schema()` and thin methods for each table: `clients` (`client_id`, `client_json`, `created_at`), `pending` (`req_id`, `client_id`, `params_json`, `expires_at`), `codes` (`code_hash`, `payload_json`, `expires_at`, `used`), `tokens` (`token_hash`, `kind` access|refresh, `client_id`, `scopes`, `expires_at`, `revoked`, `family_id`), `login_attempts` (`ts`, `ip`). Uses WAL, one short-lived connection per call, file mode 600.
  - `connector.oauth.hash_passphrase(passphrase: str) -> str` / `verify_passphrase(passphrase: str, stored: str) -> bool` (scrypt, `scrypt$n$r$p$salt_b64$hash_b64`, constant-time compare).
  - `connector.oauth.OwnerOAuthProvider(store: AuthStore, settings: Settings)` implementing the SDK `OAuthAuthorizationServerProvider` protocol: `get_client`, `register_client` (raises `RegistrationError` unless every redirect URI is in `settings.owner_redirect_uris`; forces public client, no secret), `authorize` (stores a pending request valid 10 minutes and returns `f"{public_url}/login?req={req_id}"`), `load_authorization_code`, `exchange_authorization_code` (single use; issues a 1-hour access token and a 90-day refresh token, 256-bit `secrets.token_urlsafe`, stored as SHA-256), `load_refresh_token`, `exchange_refresh_token` (rotates: marks the old refresh token used, issues a new pair; reuse of a rotated refresh token revokes the whole family), `load_access_token`, `revoke_token`.
  - `connector.oauth.register_login_routes(mcp: MCPServer, provider: OwnerOAuthProvider) -> None` adds `GET /login` (HTML form showing the client name and the redirect host, a hidden `req`, no external assets, `Cache-Control: no-store`) and `POST /login` (reads the urlencoded body by hand; verifies passphrase; on success issues an authorization code and returns a `303` redirect to `construct_redirect_uri(redirect_uri, code=..., state=...)`; on failure re-renders the form with a generic message). Throttle: more than 5 failed attempts in 15 minutes (any client IP, because the proxy hides the IP unless `X-Forwarded-For` is trusted from 127.0.0.1) locks all attempts for the rest of the window.
  - `connector.http_app.build_server(settings) -> MCPServer`: when `settings.public_url` is set, builds `MCPServer` with `auth=AuthSettings(issuer_url=public_url, resource_server_url=f"{public_url}/mcp", client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=["play"], default_scopes=["play"]), revocation_options=RevocationOptions(enabled=True), required_scopes=["play"], validate_token_resource=True)` and `auth_server_provider=provider`; startup fails with a clear error if `passphrase_hash` is missing. The access token's `resource` is set to `{public_url}/mcp`. The six tools are registered on this server by moving the tool definitions in `connector/server.py` into `register_tools(mcp)` (called by both the stdio `mcp` and the HTTP server), with identical names, docstrings and signatures.
  - CLI `python -m connector.set_passphrase` prompts twice (getpass), refuses under 12 characters, prints `CAERNESS_PASSPHRASE_HASH=...`.

- [ ] **Step 1: Write the failing test** `tests/connector_oauth_test.py` with a `TestClient` over `build_app`, `public_url="https://game.example.duckdns.org"`, a temp auth DB, passphrase hash from `hash_passphrase("correct horse battery")`. Assert:
  - `POST /mcp` with no token returns 401 and `WWW-Authenticate` contains `resource_metadata="https://game.example.duckdns.org/.well-known/oauth-protected-resource/mcp"`.
  - `GET /.well-known/oauth-protected-resource/mcp` has `resource == "https://game.example.duckdns.org/mcp"` and `authorization_servers == ["https://game.example.duckdns.org"]`; `/.well-known/oauth-authorization-server` lists `registration_endpoint`, `code_challenge_methods_supported == ["S256"]`, and `token_endpoint_auth_methods_supported` contains `"none"`.
  - Full flow: `POST /register` with redirect `https://claude.ai/api/mcp/auth_callback` succeeds; `GET /authorize` (PKCE S256 challenge, state) redirects to `/login?req=...`; `GET /login` returns 200 HTML; `POST /login` with the wrong passphrase returns 200 with the form again and no `Location`; with the right one returns 303 whose `Location` starts with `https://claude.ai/api/mcp/auth_callback?code=` and echoes `state`; `POST /token` (form-encoded, `code_verifier`) returns access and refresh tokens; `POST /mcp tools/call scene` with `Authorization: Bearer <access>` succeeds; the same call with a wrong bearer returns 401.
  - Refresh rotation: `grant_type=refresh_token` returns a new pair; the old refresh token then returns `400 invalid_grant`; presenting the rotated-away token a second time also revokes the new access token (family revocation).
  - Authorization code is single-use (second exchange fails); a code with a wrong `code_verifier` fails.
  - **Review Focus 2:** `/register` with `https://evil.example/cb` returns 400 `invalid_redirect_uri`/`invalid_client_metadata`.
  - **Review Focus 3:** 5 wrong passphrases, then the correct one is still refused (no `Location`); with the clock advanced past 15 minutes (inject a `now` function) the correct one works. The failure page text is identical for wrong passphrase and locked-out apart from a "try later" line, and never echoes the input.
  - **Review Focus 4:** construct a fresh `OwnerOAuthProvider` over the same auth DB path; the earlier access token still passes `load_access_token`; a token past `expires_at` does not.
  - Tokens at rest: grep the auth DB bytes for the plaintext access token and refresh token; neither appears. File mode is 600 on POSIX (skip the mode assert on Windows).
  - `build_server` with `public_url` set and `passphrase_hash=None` raises `ValueError`.
  - The `/login` page contains the redirect host (`claude.ai`) and no `<script>` or external URLs.
  - `GET /health` works with no token.
- [ ] **Step 2: Run it, expect failure.**
- [ ] **Step 3: Implement** `auth_store.py`, `oauth.py`, `set_passphrase.py`, the `register_tools` refactor in `server.py`, and `build_server`/`build_app` auth wiring. Use `secrets` for all tokens, `hmac.compare_digest` for hash compare, `hashlib.scrypt` with n=2**15, r=8, p=1. Clock access goes through `provider.now()` so tests can inject time.
- [ ] **Step 4: Run `tests/connector_oauth_test.py`, `connector_http_test.py`, `connector_server_test.py`**; expect all pass (stdio test confirms the refactor kept tool names and the size limit).
- [ ] **Step 5: Run the SDK-independent conformance check manually once** (not in the suite): `npx @modelcontextprotocol/inspector` against a local `--transport http` run with `CAERNESS_PUBLIC_URL=http://localhost:8765`, completing the OAuth flow in a browser. Record the result in the commit message. (Unverified tool; skip if Node is unavailable.)
- [ ] **Step 6: Commit** `feat(connector): single-owner OAuth 2.1 login for the HTTP transport`.

---

### Task 3: Campaign location, automatic backups, upload from the laptop

**Files:**
- Create: `connector/backup.py`, `connector/import_campaign.py`, `tools/export_campaign.py`
- Modify: `connector/server.py` (advance tool calls the pre-advance snapshot)
- Test: `tests/connector_backup_test.py`, `tests/connector_import_test.py`

**Interfaces:**
- Produces (`connector/backup.py`):
  - `snapshot(src: Path, dest_dir: Path, label: str, now: datetime | None = None) -> Path`: writes `<dest_dir>/<stem>-<UTC yyyymmddTHHMMSSZ>-<label>.db` using `sqlite3.connect(src).backup(dst)`, then `PRAGMA integrity_check` on the copy (raises `RuntimeError` and deletes it if not `ok`); `label` in `{"daily","preadvance","manual","preimport"}`.
  - `prune(dest_dir: Path, stem: str, keep_daily: int = 7, keep_weekly: int = 4, keep_preadvance: int = 5, keep_preimport: int = 3, now=None) -> list[Path]`: returns deleted paths; weekly = the oldest daily of each ISO week beyond the daily window; never deletes the newest snapshot of any label.
  - `pre_advance_snapshot(campaign_path: Path, backup_dir: Path | None, min_interval_s: int = 3600) -> Path | None`: no-op when `backup_dir` is None or the newest `preadvance` snapshot is younger than `min_interval_s`.
  - CLI `python -m connector.backup --campaign NAME [--label daily]` (reads `CAERNESS_CAMPAIGN_DIR`, `CAERNESS_BACKUP_DIR`), snapshots then prunes, exit code 1 on failure.
- Produces (`connector/import_campaign.py`): `install_campaign(src: Path, name: str, *, replace: bool = False) -> Path` and CLI `python -m connector.import_campaign SRC --campaign NAME [--replace]`. Validation: valid campaign name (`campaign._NAME`), `PRAGMA integrity_check == ok`, has table `actors` and `connector_calls`-compatible schema after `ensure_connector_schema` (the file is opened through `init_db` on a temp copy), and exactly one player row. Refuses an existing target unless `replace`; with `replace`, takes a `preimport` snapshot of the old file first. Installs by copy to a temp name beside the target then `os.replace` (same atomic pattern as `open_campaign`).
- Produces (`tools/export_campaign.py`, laptop): `python tools/export_campaign.py --campaign ansel --out ansel-export.db` backs up `%LOCALAPPDATA%\Caerness\campaigns\ansel.db` through the backup API (so WAL content is included even while the desktop app is running), runs the integrity check, prints size and SHA-256. Never modifies the source.

- [ ] **Step 1: Write the failing tests.**
  - `connector_backup_test.py`: `snapshot` of a WAL-mode DB with uncommitted-to-main-file rows (write rows, keep the connection open, do not checkpoint) contains those rows; the file name has the label; a corrupted copy path (monkeypatch integrity result) raises and leaves no file; `prune` with 10 fake daily snapshots across 3 weeks keeps the newest 7 and one per older week, keeps the newest of each label, and returns exactly the deleted paths; `pre_advance_snapshot` with `backup_dir=None` returns `None`, creates one file on first call, and `None` on an immediate second call (throttle) but a new file after `min_interval_s`; the source DB bytes and mtime are unchanged by all of the above.
  - `connector_import_test.py`: export of a campaign created by `open_campaign("src")` + `set_player` installs as `dst` and `get_player` returns the same actor; second install to `dst` raises without `--replace`; with `replace=True` the old file is first present as a `preimport` snapshot; a random non-SQLite file, a SQLite file with no `actors` table, and a campaign with no player are each refused with a clear error and leave `dst` untouched; packaged `data/caerness.db` SHA-256 unchanged.
  - Wire test (in `connector_http_test.py`): with `CAERNESS_BACKUP_DIR` set, calling the `advance` tool creates one `preadvance` snapshot and a second call within the interval creates none.
- [ ] **Step 2: Run them, expect failure.**
- [ ] **Step 3: Implement** the three modules and the one-line call in the `advance` tool (before `_call`, resolving the campaign path from `CAERNESS_DB_PATH`; a snapshot failure is logged to stderr and does **not** block the advance... except when the snapshot itself raised on integrity, which blocks and returns `{"error": ...}` so a corrupt campaign is never advanced further).
- [ ] **Step 4: Run both tests plus `connector_advance_test.py`**; expect pass.
- [ ] **Step 5: Commit** `feat(connector): rotating SQLite-API backups, pre-advance snapshot, campaign import/export`.

---

### Task 4: Deployment artifacts (systemd, Caddy, install and update scripts)

**Files:**
- Create: `deploy/caerness.service`, `deploy/caerness-backup.service`, `deploy/caerness-backup.timer`, `deploy/Caddyfile`, `deploy/caerness.env.example`, `deploy/install.sh`, `deploy/update.sh`, `deploy/duckdns-update.sh`, `deploy/duckdns.service`, `deploy/duckdns.timer`
- Modify: `.gitignore` (`deploy/*.env`, `*.bak`)
- Test: `tests/deploy_files_test.py`

**Interfaces:**
- Paths on the VM (all fixed here so scripts and units agree): code `/opt/caerness` (git clone of `https://github.com/ferreiracade-dotcom/Caerness.git`, public), venv `/opt/caerness/.venv`, state `/var/lib/caerness/{campaigns,backups,auth.db}`, env `/etc/caerness/caerness.env` (root:caerness 640), service user `caerness` (no login), listener `127.0.0.1:8765`.
- `caerness.service`: `User=caerness`, `EnvironmentFile=/etc/caerness/caerness.env`, `ExecStart=/opt/caerness/.venv/bin/python /opt/caerness/connector/run_server.py --transport http --host 127.0.0.1 --port 8765`, `Restart=always`, `RestartSec=3`, hardening (`NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths=/var/lib/caerness`, `ProtectHome=yes`, `PrivateTmp=yes`), `TimeoutStopSec=120` (lets an in-flight advance finish).
- `caerness-backup.timer`: daily 04:30 UTC, `Persistent=true`, runs `python -m connector.backup --campaign $CAERNESS_CAMPAIGN --label daily`.
- `Caddyfile`: `{$CAERNESS_HOST} { encode zstd gzip; reverse_proxy 127.0.0.1:8765 { flush_interval -1 } }` (no response buffering for streaming), request body limit 1 MB, and a header block that sets `X-Content-Type-Options nosniff`.
- `install.sh` (idempotent, run as root, arguments `HOST`): installs Caddy from its apt repository, `uv` and Python 3.13 (`uv python install 3.13`), creates user and directories, `git clone`, `uv venv` + `pip install -r connector/requirements.txt numpy`, opens ports 80/443 in the instance firewall (Ubuntu images from Oracle ship restrictive iptables rules: unverified, the script prints the resulting `iptables -S` for the owner to see), enables `unattended-upgrades`, copies units, writes `/etc/caerness/caerness.env` from the example if absent (never overwrites), enables and starts `caerness`, `caerness-backup.timer`, `caddy`.
- `update.sh`: `git -C /opt/caerness pull --ff-only`, `pip install -r connector/requirements.txt`, run the smoke subset (`tests/connector_http_test.py`, `tests/connector_oauth_test.py`) against a temp campaign dir as the service user, only then `systemctl restart caerness`; prints `curl -fsS http://127.0.0.1:8765/health`. Any failing step aborts before the restart.
- `duckdns-update.sh`: updates the A record with the instance's current public IP using the token from the env file (token never on the command line of a logged unit; use `curl --data-urlencode` from a here-string).

- [ ] **Step 1: Write the failing test** `tests/deploy_files_test.py` (no VM needed): parse each unit with `configparser` (`strict=False`); assert `ExecStart` of `caerness.service` references `connector/run_server.py` and the flags `--transport http`; the env keys in `caerness.env.example` equal the set `Settings.from_env` reads (import the constant list from `connector/settings.py`: `ENV_KEYS`); the Caddy upstream port equals the service `--port`; `bash -n` passes for every `*.sh` when `bash` exists (skip otherwise); `install.sh` contains no passphrase or token literal; `caerness.env.example` has placeholder values only and mode-comment lines; the timer's `ExecStart` module `connector.backup` imports.
- [ ] **Step 2: Run it, expect failure.**
- [ ] **Step 3: Implement** the files per Interfaces; add `ENV_KEYS` to `connector/settings.py`.
- [ ] **Step 4: Run `tests/deploy_files_test.py`**; expect pass.
- [ ] **Step 5: Commit** `feat(deploy): systemd units, Caddy, install and update scripts for the Oracle VM`.

---

### Task 5: Owner runbook and phone acceptance checklist (docs)

**Files:**
- Modify: `connector/README.md` (add "Remote hosting" section: manual steps below, update procedure, restore procedure, troubleshooting table)
- Modify: `AGENTS.md` §4 table (rows: remote update `deploy/update.sh`, backup restore, export campaign)

**Interfaces:** none.

- [ ] **Step 1: Write the README section** with exactly the steps in "Owner manual steps" below (copy, then add the restore steps: stop service, `python -m connector.import_campaign <snapshot> --campaign NAME --replace`, start service) and the troubleshooting table: "Couldn't reach the MCP server" (check `curl https://HOST/health`, Caddy logs, DNS), "Authorization with the MCP server failed" (login throttled, wrong passphrase, redirect URI mismatch), `421` in logs (public host not in allowed hosts), tool timeout after 240 s (lower `CAERNESS_MAX_ADVANCE_DAYS`).
- [ ] **Step 2: Verify** every command in the section exists: run `grep -n` for each script/module name against the repo; expect no missing names.
- [ ] **Step 3: Commit** `docs(connector): remote hosting runbook`.

---

### Task 6: Measured 30-day advance on the VM (needs the VM; owner has done manual steps 1–7)

**Files:**
- Create: `benchmarks/results/oracle_a1_engine.json` (output of the existing benchmark tool)
- Modify: `connector/timeflow.py` default only if the measurement fails the budget

**Interfaces:**
- Consumes: `tools/bench_sim.py` (`--db`, `--label`, `--segments`), `tools/run_years.py`, the imported `ansel` campaign.

- [ ] **Step 1: Baseline on the PC** (already-supported tools): `"$PY" tools/bench_sim.py --db "$LOCALAPPDATA/Caerness/campaigns/ansel.db" --label pc-ansel --segments 1,30`. It copies the DB; the source is untouched. Record the 30-day seconds and peak RSS.
- [ ] **Step 2: Same on the VM**: `/opt/caerness/.venv/bin/python tools/bench_sim.py --db /var/lib/caerness/campaigns/ansel.db --label oracle-a1 --segments 1,30` (copies the campaign to a temp dir; run as the `caerness` user). Also record `uname -m`, `python -V`, `numpy.__version__` and `sqlite3.sqlite_version` (expected to confirm unverified item (d)).
- [ ] **Step 3: Apply the budget.** Pass: 30-day segment under 90 s and peak RSS under 700 MB (under 5 GB is fine on A1; 700 MB only matters for the E2.1.Micro fallback). 90–150 s: set `CAERNESS_MAX_ADVANCE_DAYS=15` in the env file and record it. Over 150 s: set it to 7 and open a PERF follow-up in `AGENTS.md`. Commit the JSON.
- [ ] **Step 4: End-to-end timing through the connector:** from the laptop, time one real `advance` of 30 days from the Claude app (stopwatch, manual) and note it beside the benchmark number; the difference is network plus Claude, expected under 5 s.
- [ ] **Step 5: Commit** `bench: Oracle A1 30-day advance measurement`.

---

### Task 7: Go-live and phone acceptance (manual with Claude present; no code)

- [ ] **Step 1: Owner pushes `feat/claude-connector`** (the VM pulls `master` by default; for the first install pass `BRANCH=feat/claude-connector` to `install.sh`, switch to `master` after the owner merges).
- [ ] **Step 2: Run the install** (owner manual steps 8–12 below).
- [ ] **Step 3: Phone acceptance checklist** (record pass/fail in the final commit message):
  1. In a desktop or laptop browser on claude.ai, Customize > Connectors > Add custom connector, URL `https://HOST/mcp`, Authentication "Sign in now", OAuth client "Register automatically" (fall back to "Use Claude's published identity" if offered and DCR is refused). The browser lands on the Caerness login page; entering the passphrase returns to claude.ai with the connector **Connected**.
  2. Open the Claude app on the phone (same account). New chat, **+** > Connectors, confirm the Caerness toggle is on. Type `resume`. Expect: the rulebook is followed and an opening scene appears without any engine talk.
  3. Play three turns including one `act` and one `note`. Airplane-mode for 30 seconds, then continue: the chat recovers with no re-login.
  4. Ask for a 7-day wait; then (after Task 6) a 30-day skip; neither times out.
  5. With the **laptop switched off**, repeat step 2 from a different network (mobile data).
  6. Retry safety: ask Claude to repeat the last `note`; the reply is `replayed`.
  7. On the VM, confirm `systemctl status caerness` active, a `daily` or `preadvance` snapshot exists in `/var/lib/caerness/backups`, and `journalctl -u caerness` contains no tracebacks or `421`.
  8. Reboot the VM from the console; within 3 minutes the phone resumes without re-login (tokens and campaign survive).
  9. Wrong token check: `curl -i https://HOST/mcp` returns 401 with `resource_metadata`.
- [ ] **Step 4: Add a Claude Desktop (stdio) entry check:** the existing laptop stdio config still starts and `resume` works against a local copy (confirms stdio stayed intact).

---

## Owner manual steps (minimal; everything else is scripted)

Hand steps, in order. Claude cannot do 1–7 (they need your identity, card and console).

1. **Oracle sign-up.** Create an Oracle Cloud Free Tier account (card and phone verification; a small authorization hold is normal). Pick the **home region** carefully (it cannot be changed, and Always Free resources must live there); choose one with Ampere A1 capacity near you. *If A1 shows "Out of host capacity", retry later or in another availability domain, or use the AMD micro fallback.*
2. **(Recommended) Upgrade to Pay As You Go**, then in Billing set a **budget alert at 1 USD**. This is the documented way to avoid idle-instance reclamation; usage within the Always Free limits is not charged (quoted Oracle notice, third-party copy: re-check Oracle's Free Tier page when you upgrade). Create only the one instance and the default 50 GB boot volume described below.
3. **SSH key.** On the laptop: `ssh-keygen -t ed25519`; keep the private key, paste the public key in the next step.
4. **Create the VM.** Compute > Create instance: image **Ubuntu 24.04 (arm64)**, shape **VM.Standard.A1.Flex, 1 OCPU, 6 GB**, public IPv4, paste the public key, boot volume 50 GB.
5. **Open the network.** In the VCN's default security list add ingress TCP **80** and **443** from `0.0.0.0/0` (keep 22 as is; optionally restrict 22 to your own IP).
6. **DuckDNS name.** Sign in at https://www.duckdns.org with GitHub or Google, create a subdomain with a random-looking name (for example `caerness-k7q3m9`), set its IP to the VM's public IP, and copy the account token. Keep both.
7. **Choose the passphrase** for the game (12+ characters, not reused anywhere). You will type it once on the VM and once on the claude.ai login page.
8. **SSH in and run** `curl -fsSL https://raw.githubusercontent.com/ferreiracade-dotcom/Caerness/<branch>/deploy/install.sh | sudo bash -s -- <HOST>` (or `git clone` then `sudo deploy/install.sh <HOST>`; Claude can read the script with you first). When it pauses, enter the DuckDNS token and run `sudo -u caerness /opt/caerness/.venv/bin/python -m connector.set_passphrase`, paste the printed line into `/etc/caerness/caerness.env`, then `sudo systemctl restart caerness`.
9. **Copy the campaign up** (laptop, PowerShell, with the desktop Claude app closed or open, both are safe): `python tools/export_campaign.py --campaign ansel --out $env:TEMP\ansel-export.db` then `scp -i <key> $env:TEMP\ansel-export.db ubuntu@<ip>:/tmp/` and, on the VM, `sudo -u caerness /opt/caerness/.venv/bin/python -m connector.import_campaign /tmp/ansel-export.db --campaign ansel` and set `CAERNESS_CAMPAIGN=ansel` in the env file (restart the service). Delete `/tmp/ansel-export.db` afterwards.
10. **Add the connector on claude.ai** (Task 7 step 3.1) and sign in with the passphrase. From now on the laptop copy of `ansel` is a stale archive: play only through the connector (two copies diverge; `export_campaign` is one-way laptop to VM).
11. **Phone check** (Task 7 step 3.2 onward).
12. **To update later:** SSH in, run `sudo /opt/caerness/deploy/update.sh`. To fetch a backup to the laptop: `scp -i <key> ubuntu@<ip>:/var/lib/caerness/backups/<file> .`.

## Self-review

- **Spec/request coverage:** HTTP alongside stdio (Task 1); auth strong for a public endpoint, matching what claude.ai supports (Task 2, Decisions 1); stdout guard, per-call connections, idempotency (Task 1 tests, Global Constraints); campaign location, automatic backups, laptop upload of `ansel` (Task 3); systemd, Python 3.13 + numpy on ARM, git pull update (Task 4); measured 30-day advance (Task 6); manual steps separated (end section); phone acceptance (Task 7); supersession as a planned doc edit (Task 0); AGENTS.md rules kept (Global Constraints: no write to `data/caerness.db`, campaigns are copies, no raw SQL tool).
- **Type consistency:** `Settings` fields and `ENV_KEYS` are defined in Task 1 and consumed by Tasks 2 to 4; `OwnerOAuthProvider`, `AuthStore`, `register_tools`, `build_server`, `build_app` signatures are fixed in Tasks 1 and 2; `snapshot/prune/pre_advance_snapshot/install_campaign` in Task 3 are the names used in Tasks 4 to 7.
- **Proportion:** most code bodies are deliberately left to the implementer; the tests carry the exact assertions.
- **Risks still open:** DuckDNS or Oracle outage (mitigation: a paid domain is a drop-in for the Caddy host; backups can restore on any VM); OAuth quirks in Claude's real client are only provable in Task 7, so keep Task 2's tests close to the documented handshake and budget a debugging pass; if DCR is refused for any reason, CIMD (`client_id_metadata_document_supported`) is the documented alternative and would be a small follow-up.
