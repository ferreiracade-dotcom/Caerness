from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HOST = "game.example.duckdns.org"
BASE = "https://" + HOST
CB = "https://claude.ai/api/mcp/auth_callback"
PASSPHRASE = "correct horse battery"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def mcp_scene(client, token=None):
    headers = dict(MCP_HEADERS)
    if token:
        headers["Authorization"] = "Bearer " + token
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": "scene", "arguments": {}}}, headers=headers)


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["CAERNESS_CAMPAIGN_DIR"] = tmp
        from starlette.testclient import TestClient

        from connector.auth_store import AuthStore
        from connector.campaign import connect_campaign, open_campaign
        from connector.http_app import build_app, build_server
        from connector.oauth import OwnerOAuthProvider, hash_passphrase, verify_passphrase
        from connector.settings import Settings
        from engine.player import set_player

        open_campaign("oauth")
        with connect_campaign() as conn:
            row = conn.execute(
                "SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()
            set_player(conn, int(row["id"]), campaign_name="oauth")
            conn.commit()

        stored = hash_passphrase(PASSPHRASE)
        assert stored.startswith("scrypt$") and PASSPHRASE not in stored
        assert verify_passphrase(PASSPHRASE, stored) and not verify_passphrase("wrong", stored)
        assert not verify_passphrase(PASSPHRASE, "garbage") and not verify_passphrase(PASSPHRASE, "")

        from connector.set_passphrase import build_line
        line = build_line("a twelve+ char phrase")
        assert line.startswith("CAERNESS_PASSPHRASE_HASH=scrypt$") and "twelve" not in line
        assert verify_passphrase("a twelve+ char phrase", line.split("=", 1)[1])
        try:
            build_line("short")
        except ValueError:
            pass
        else:
            raise AssertionError("short passphrase accepted")

        auth_db = Path(tmp) / "auth.db"
        settings = Settings(public_url=BASE, auth_db_path=auth_db, passphrase_hash=stored)

        # build_server refuses a public deployment with no passphrase.
        try:
            build_server(Settings(public_url=BASE, auth_db_path=Path(tmp) / "x.db", passphrase_hash=None))
        except ValueError:
            pass
        else:
            raise AssertionError("missing passphrase hash accepted")

        offset = [0.0]

        def clock():
            return time.time() + offset[0]

        provider = OwnerOAuthProvider(AuthStore(auth_db), settings, now=clock)
        app = build_app(settings, provider)

        with TestClient(app, base_url=BASE, follow_redirects=False) as client:
            # --- discovery and challenge ---------------------------------------------------
            r = mcp_scene(client)
            assert r.status_code == 401, r.status_code
            assert f'resource_metadata="{BASE}/.well-known/oauth-protected-resource/mcp"' in r.headers["www-authenticate"], r.headers
            assert mcp_scene(client, "not-a-token").status_code == 401

            prm = client.get("/.well-known/oauth-protected-resource/mcp").json()
            assert prm["resource"] == BASE + "/mcp", prm  # claude.ai needs this to match exactly
            assert prm["authorization_servers"] == [BASE], prm
            meta = client.get("/.well-known/oauth-authorization-server").json()
            assert meta["registration_endpoint"].startswith(BASE)
            assert meta["code_challenge_methods_supported"] == ["S256"]
            assert "none" in meta["token_endpoint_auth_methods_supported"], meta
            assert client.get("/health").json() == {"ok": True}

            # --- registration is locked to the claude.ai callback (Review Focus 2) ---------
            evil = client.post("/register", json={"redirect_uris": ["https://evil.example/cb"], "client_name": "x",
                                                  "token_endpoint_auth_method": "none"})
            assert evil.status_code == 400 and evil.json()["error"] in ("invalid_redirect_uri", "invalid_client_metadata"), evil.text
            mixed = client.post("/register", json={"redirect_uris": [CB, "https://evil.example/cb"], "client_name": "x"})
            assert mixed.status_code == 400, mixed.text

            reg = client.post("/register", json={"redirect_uris": [CB], "client_name": "Claude <b>x</b>",
                                                 "token_endpoint_auth_method": "client_secret_post",
                                                 "grant_types": ["authorization_code", "refresh_token"],
                                                 "response_types": ["code"], "scope": "play"})
            assert reg.status_code == 201, reg.text
            info = reg.json()
            client_id = info["client_id"]
            assert info["token_endpoint_auth_method"] == "none" and not info.get("client_secret"), info

            def authorize(state="st-1", redirect=CB, challenge=None):
                verifier, chal = pkce()
                resp = client.get("/authorize", params={
                    "response_type": "code", "client_id": client_id, "redirect_uri": redirect,
                    "code_challenge": challenge or chal, "code_challenge_method": "S256",
                    "state": state, "scope": "play", "resource": BASE + "/mcp"})
                return verifier, resp

            def req_of(resp):
                loc = resp.headers["location"]
                assert loc.startswith(BASE + "/login?req="), loc
                return parse_qs(urlparse(loc).query)["req"][0]

            # An unregistered redirect never reaches the login page.
            _, bad = authorize(redirect="https://evil.example/cb")
            assert bad.status_code == 400 and "location" not in bad.headers, (bad.status_code, bad.headers)

            def sign_in(state="st-1", passphrase=PASSPHRASE):
                verifier, resp = authorize(state)
                assert resp.status_code == 302, resp.text
                req = req_of(resp)
                return verifier, req, client.post("/login", data={"req": req, "passphrase": passphrase})

            def exchange(code, verifier, **extra):
                return client.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": CB,
                                                   "client_id": client_id, "code_verifier": verifier, **extra})

            # --- the login page ---------------------------------------------------------------
            verifier, resp = authorize()
            req = req_of(resp)
            page = client.get("/login", params={"req": req})
            assert page.status_code == 200 and "claude.ai" in page.text, page.text
            low = page.text.lower()
            assert "<script" not in low and "http" not in low, page.text
            assert "<b>" not in page.text  # client name is escaped
            assert "no-store" in page.headers["cache-control"] and page.headers.get("x-frame-options") == "DENY"
            assert client.get("/login", params={"req": "nope"}).status_code in (400, 404)

            # wrong passphrase: form again, no redirect, input never echoed
            wrong = client.post("/login", data={"req": req, "passphrase": "totally wrong value 1"})
            assert wrong.status_code == 200 and "location" not in wrong.headers
            assert "totally wrong value 1" not in wrong.text and "<form" in wrong.text

            # right passphrase: 303 to the claude.ai callback with code and echoed state
            ok = client.post("/login", data={"req": req, "passphrase": PASSPHRASE})
            assert ok.status_code == 303, ok.status_code
            loc = ok.headers["location"]
            assert loc.startswith(CB + "?code="), loc
            q = parse_qs(urlparse(loc).query)
            assert q["state"] == ["st-1"]
            code = q["code"][0]
            # the pending request is single use
            again = client.post("/login", data={"req": req, "passphrase": PASSPHRASE})
            assert again.status_code != 303, again.status_code

            # --- code exchange ----------------------------------------------------------------
            tok = exchange(code, verifier)
            assert tok.status_code == 200, tok.text
            t1 = tok.json()
            assert t1["token_type"] == "Bearer" and t1["refresh_token"] and t1["access_token"]
            assert 0 < t1["expires_in"] <= 3600

            ok_call = mcp_scene(client, t1["access_token"])
            assert ok_call.status_code == 200, ok_call.text
            payload = json.loads(ok_call.json()["result"]["content"][0]["text"])
            assert "error" not in payload and payload["present"], payload
            assert mcp_scene(client, t1["access_token"] + "x").status_code == 401

            # single-use code; replay revokes what the code issued
            replay = exchange(code, verifier)
            assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant", replay.text
            assert mcp_scene(client, t1["access_token"]).status_code == 401

            # wrong code_verifier
            v2, req2, ok2 = sign_in("st-2")
            code2 = parse_qs(urlparse(ok2.headers["location"]).query)["code"][0]
            badv = exchange(code2, "x" * 50)
            assert badv.status_code == 400 and badv.json()["error"] == "invalid_grant", badv.text
            # an authorization code cannot be used by another client id
            other = client.post("/register", json={"redirect_uris": [CB], "client_name": "other"}).json()["client_id"]
            steal = client.post("/token", data={"grant_type": "authorization_code", "code": code2, "redirect_uri": CB,
                                                "client_id": other, "code_verifier": v2})
            assert steal.status_code == 400, steal.text

            # --- refresh rotation + family revocation -----------------------------------------
            good = exchange(code2, v2)
            assert good.status_code == 200, good.text
            a1, r1 = good.json()["access_token"], good.json()["refresh_token"]

            def refresh(token):
                return client.post("/token", data={"grant_type": "refresh_token", "refresh_token": token, "client_id": client_id})

            rot = refresh(r1)
            assert rot.status_code == 200, rot.text
            a2, r2 = rot.json()["access_token"], rot.json()["refresh_token"]
            assert r2 != r1 and a2 != a1
            assert mcp_scene(client, a2).status_code == 200
            stale = refresh(r1)
            assert stale.status_code == 400 and stale.json()["error"] == "invalid_grant", stale.text
            assert mcp_scene(client, a2).status_code == 401  # family revoked
            assert refresh(r2).status_code == 400
            assert refresh("not-a-refresh-token").status_code == 400

            # --- Review Focus 4: restart does not sign the phone out ---------------------------
            v3, req3, ok3 = sign_in("st-3")
            code3 = parse_qs(urlparse(ok3.headers["location"]).query)["code"][0]
            t3 = exchange(code3, v3).json()
            fresh = OwnerOAuthProvider(AuthStore(auth_db), settings, now=clock)
            loaded = asyncio.run(fresh.load_access_token(t3["access_token"]))
            assert loaded is not None and loaded.scopes == ["play"] and loaded.resource == BASE + "/mcp", loaded
            reg_client = asyncio.run(fresh.get_client(client_id))
            assert reg_client is not None and reg_client.client_id == client_id
            old = asyncio.run(fresh.load_refresh_token(reg_client, t3["refresh_token"]))
            assert old is not None
            offset[0] = 2 * 3600
            assert asyncio.run(fresh.load_access_token(t3["access_token"])) is None  # expired
            offset[0] = 0

            # --- tokens at rest are hashed --------------------------------------------------------
            blob = b""
            for suffix in ("", "-wal", "-shm"):
                p = Path(str(auth_db) + suffix)
                if p.exists():
                    blob += p.read_bytes()
            for secret in (t1["access_token"], t1["refresh_token"], t3["access_token"], t3["refresh_token"], code, code2, code3):
                assert secret.encode() not in blob, "plaintext secret in auth db"
            assert PASSPHRASE.encode() not in blob
            if os.name == "posix":
                assert (auth_db.stat().st_mode & 0o777) == 0o600

            # --- Review Focus 3: throttle -------------------------------------------------------------
            v4, resp4 = authorize("st-4")
            req4 = req_of(resp4)
            wrong_pages = []
            for i in range(5):
                w = client.post("/login", data={"req": req4, "passphrase": f"bad-guess-{i}"})
                assert w.status_code == 200 and "location" not in w.headers
                wrong_pages.append(w.text)
            locked = client.post("/login", data={"req": req4, "passphrase": PASSPHRASE})
            assert locked.status_code == 200 and "location" not in locked.headers, "right passphrase accepted while locked"
            assert PASSPHRASE not in locked.text and "bad-guess" not in locked.text
            strip = lambda s: " ".join(s.split())  # noqa: E731
            assert strip(wrong_pages[0]) in strip(locked.text) or strip(locked.text).startswith(strip(wrong_pages[0])[:200])
            assert "try again later" in locked.text.lower() and "try again later" not in wrong_pages[0].lower()
            offset[0] = 16 * 60
            v5, resp5 = authorize("st-5")
            req5 = req_of(resp5)
            unlocked = client.post("/login", data={"req": req5, "passphrase": PASSPHRASE})
            assert unlocked.status_code == 303, unlocked.status_code
            offset[0] = 0

    print("connector_oauth_test passed")


if __name__ == "__main__":
    run()
