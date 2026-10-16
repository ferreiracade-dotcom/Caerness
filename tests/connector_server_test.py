from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["CAERNESS_CAMPAIGN_DIR"] = tmp
        from connector import server
        from connector.campaign import connect_campaign, open_campaign
        from engine.player import set_player

        open_campaign("srv")
        with connect_campaign() as conn:
            row = conn.execute(
                "SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()
            set_player(conn, int(row["id"]), campaign_name="srv")
            conn.commit()

        tools = asyncio.run(server.mcp.list_tools())
        assert sorted(t.name for t in tools) == ["act", "advance", "lookup", "lore", "note", "resume", "scene"]
        size = len(json.dumps([t.model_dump(by_alias=True, exclude_none=True) for t in tools], ensure_ascii=False))
        print(f"tool definitions: {size} chars")
        assert size <= 6000, size

        r = server.resume()
        assert "error" not in r and "rulebook" in r, r
        print(f"resume: {len(json.dumps(r, ensure_ascii=False))} chars")
        s = server.scene()
        assert "error" not in s and s["present"], s
        who = s["present"][0]
        assert "error" not in server.lookup(who["name"])
        a = server.act("s-act-1", "observe", "I take stock.")
        assert "error" not in a and a["status"] == "applied", a
        adv = server.advance("s-adv-1", 1, "wait")
        assert "error" not in adv, adv
        n = server.note("s-note-1", "actor", who["id"], "keeps a limp")
        assert "error" not in n, n

        # Errors become dicts, not exceptions.
        assert "error" in server.note("s-note-2", "actor", 99999999, "ghost")
        assert "error" in server.advance("s-adv-2", 0, "nothing")
        assert "error" in server.note("s-note-1", "actor", who["id"], "different text")  # call_id reuse

        # The same tools through the MCP layer return JSON text.
        res = asyncio.run(server.mcp.call_tool("lookup", {"query": who["name"]}))
        assert json.loads(res.content[0].text)["found"] is True

        # Stdout guard: engine noise must not reach stdout.
        import engine.player as player_mod
        orig = player_mod.build_scene_packet

        def noisy(*a, **k):
            print("noise")
            return orig(*a, **k)

        player_mod.build_scene_packet = noisy
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                s2 = server.scene()
        finally:
            player_mod.build_scene_packet = orig
        assert out.getvalue() == "", out.getvalue()
        assert "noise" in err.getvalue() and "error" not in s2
    print("connector_server_test passed")


if __name__ == "__main__":
    run()
