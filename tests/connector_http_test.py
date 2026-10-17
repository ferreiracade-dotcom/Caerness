from __future__ import annotations

import concurrent.futures
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HOST = "game.example.duckdns.org"
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client, method, params=None, rid=1, headers=None):
    body = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
    return client.post("/mcp", json=body, headers={**HEADERS, **(headers or {})})


def initialize(client):
    return rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "t", "version": "0"}})


def call_tool(client, name, args=None, rid=2):
    r = rpc(client, "tools/call", {"name": name, "arguments": args or {}}, rid=rid)
    assert r.status_code == 200, r.text
    return json.loads(r.json()["result"]["content"][0]["text"])


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["CAERNESS_CAMPAIGN_DIR"] = tmp
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        from starlette.testclient import TestClient

        from connector.campaign import connect_campaign, open_campaign
        from connector.http_app import build_app
        from connector.settings import ENV_KEYS, Settings
        from engine.player import set_player

        # Settings defaults and parsing.
        s = Settings.from_env({})
        assert s.public_url is None and s.campaign == "main" and s.max_advance_days == 30
        assert s.owner_redirect_uris == ("https://claude.ai/api/mcp/auth_callback",)
        assert s.backup_dir is None and s.passphrase_hash is None
        s2 = Settings.from_env({"CAERNESS_PUBLIC_URL": "https://h.example/", "CAERNESS_MAX_ADVANCE_DAYS": "7",
                                "CAERNESS_REDIRECT_URIS": "https://a.example/cb, https://b.example/cb"})
        assert s2.public_url == "https://h.example" and s2.max_advance_days == 7
        assert s2.owner_redirect_uris == ("https://a.example/cb", "https://b.example/cb")
        assert "CAERNESS_PUBLIC_URL" in ENV_KEYS and "CAERNESS_PASSPHRASE_HASH" in ENV_KEYS

        open_campaign("http")
        with connect_campaign() as conn:
            row = conn.execute(
                "SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()
            set_player(conn, int(row["id"]), campaign_name="http")
            conn.commit()

        # Unauthenticated public deployment must be refused until auth exists (Task 2 replaces this with a provider).
        try:
            build_app(Settings.from_env({"CAERNESS_PUBLIC_URL": "https://" + HOST}))
        except Exception:
            pass
        else:
            raise AssertionError("public_url without auth was accepted")

        app = build_app(Settings.from_env({}), allowed_hosts=[HOST])
        with TestClient(app, base_url="https://" + HOST) as client:
            r = initialize(client)
            assert r.status_code == 200, r.text
            r = rpc(client, "tools/list")
            assert r.status_code == 200, r.text
            names = sorted(t["name"] for t in r.json()["result"]["tools"])
            assert names == ["act", "advance", "author", "lookup", "lore", "note", "resume", "scene"], names

            res = call_tool(client, "resume")
            assert "rulebook" in res, list(res)
            who = call_tool(client, "scene")["present"][0]["id"]
            first = call_tool(client, "note", {"call_id": "h-note-1", "subject_kind": "actor",
                                               "subject_id": who, "text": "hums while working"})
            assert "error" not in first and not first.get("replayed"), first
            again = call_tool(client, "note", {"call_id": "h-note-1", "subject_kind": "actor",
                                               "subject_id": who, "text": "hums while working"})
            assert again.get("replayed") is True, again

            # Host header not in the allow-list is refused.
            bad = rpc(client, "tools/list", headers={"Host": "other.example.com"})
            assert bad.status_code == 421, bad.status_code

            h = client.get("/health")
            assert h.status_code == 200 and h.json() == {"ok": True}, h.text

            # Stdout guard over HTTP.
            import engine.player as player_mod
            orig = player_mod.build_scene_packet

            def noisy(*a, **k):
                print("NOISE")
                return orig(*a, **k)

            player_mod.build_scene_packet = noisy
            out = io.StringIO()
            err = io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    res = call_tool(client, "scene")
            finally:
                player_mod.build_scene_packet = orig
            assert "NOISE" not in out.getvalue(), out.getvalue()
            assert "NOISE" in err.getvalue() and "error" not in res

            # Two concurrent calls both succeed.
            with concurrent.futures.ThreadPoolExecutor(2) as ex:
                futs = [ex.submit(call_tool, client, "scene", None, 10 + i) for i in range(2)]
                results = [f.result() for f in futs]
            assert all("error" not in x and x["present"] for x in results), results

        # Wire test: one preadvance snapshot per interval when CAERNESS_BACKUP_DIR is set.
        snaps_dir = Path(tmp) / "backups"
        os.environ["CAERNESS_BACKUP_DIR"] = str(snaps_dir)
        try:
            with TestClient(build_app(Settings.from_env({}), allowed_hosts=[HOST]), base_url="https://" + HOST) as client:
                r1 = call_tool(client, "advance", {"call_id": "h-adv-1", "days": 1, "purpose": "wait"})
                assert "error" not in r1, r1
                assert len(list(snaps_dir.glob("*-preadvance.db"))) == 1
                r2 = call_tool(client, "advance", {"call_id": "h-adv-2", "days": 1, "purpose": "wait"})
                assert "error" not in r2, r2
                assert len(list(snaps_dir.glob("*-preadvance.db"))) == 1
        finally:
            os.environ.pop("CAERNESS_BACKUP_DIR", None)

        # The per-call advance cap comes from CAERNESS_MAX_ADVANCE_DAYS.
        from connector.timeflow import advance, max_advance_days
        os.environ["CAERNESS_MAX_ADVANCE_DAYS"] = "7"
        try:
            assert max_advance_days() == 7
            with connect_campaign() as conn:
                r = advance(conn, "h-cap-1", 20, "wait")
            assert 1 <= r["elapsed_days"] <= 7, r
            os.environ["CAERNESS_MAX_ADVANCE_DAYS"] = "999"
            assert max_advance_days() == 30
            os.environ["CAERNESS_MAX_ADVANCE_DAYS"] = "junk"
            assert max_advance_days() == 30
        finally:
            os.environ.pop("CAERNESS_MAX_ADVANCE_DAYS", None)
    print("connector_http_test passed")


if __name__ == "__main__":
    run()
