"""P2: resume brings back the last scene, every standing rule and long sheets; a settled correction is not raised again; the
only save loads without asking; a fresh chat is suggested only when a scene is closed with a recap."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402

PROTAGONIST = {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic, engine tuning",
               "family": {"parents": {"father": "alive", "mother": "alive"}}, "accept": True}
_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"r{_n[0]:03d}"


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        os.environ.pop("CAERNESS_SHELVED_WORLDS", None)
        from connector import campaign, server, store

        campaign._packaged_db = lambda pkg_id: base
        first = server.resume(world="saintjude")
        assert first.get("needs_character"), first
        me = server.author(cid(), "protagonist", PROTAGONIST)["actor_id"]
        friend = server.author(cid(), "person", {"name": "Wendell Pryor", "sex": "male", "age": 24, "place": "Greenwood"})["actor_id"]

        # the scene as it stands, recorded before it is told
        words = "Wendell leans on the Camaro. \"Saturday, then?\" Dominic has not answered. " * 12
        got = server.note(cid(), words, kind="scene", present=["Wendell Pryor", 999999, "Nobody Atall"])
        assert got["saved"] == "scene" and got["present"] == ["Wendell Pryor"] and got["not_here"] == [999999, "Nobody Atall"], got
        assert server.act(cid(), "speak", "Saturday.", target_actor_id=friend)["status"] == "applied"

        rules = [f"standing rule number {i}: " + "price fairly, never cheaply; " * 15 for i in range(12)]
        for text in rules:
            assert "clipped" not in server.note(cid(), text, kind="rule")
        history = "He learned engines at his uncle's yard. " * 20
        assert "clipped" not in server.note(cid(), history, kind="sheet", field="history")
        server.note(cid(), "Frank's surname was told wrong.", kind="error")
        server.note(cid(), "Frank's surname was told wrong.", kind="error", field="settled")

        for _ in range(45):
            assert "fresh_chat_hint" not in server.scene()
        assert "fresh_chat_hint" not in server.act(cid(), "observe", "Look around.")
        week = server.advance(cid(), 8, "work", from_day=server.scene()["day"])
        assert not week.get("error") and "fresh_chat_hint" not in week, week
        closed = server.note(cid(), "The week's work is done.", kind="recap", threads=["Wendell's Saturday offer"])
        assert "fresh_chat_hint" in closed, closed

        # one save only: straight back in, without being asked which
        back = server.resume()
        assert "ask" not in back and back["protagonist"]["name"] == "Dominic Basile", list(back)
        scene = back["last_scene"]
        assert scene["place"] == "South Hill" and scene["present"] == ["Wendell Pryor"] and scene["days_since"] >= 1, scene
        assert scene["text"] == " ".join(words.split()), scene["text"][-80:]
        assert back["story"]["standing_rules"] == [" ".join(r.split()) for r in rules]
        assert back["story"]["character_sheet"]["history"] == " ".join(history.split())
        assert "corrections" not in back["story"], back["story"]
        assert back["story"]["live_thread"]["open_threads"] == ["Wendell's Saturday offer"]

        # two saves: asked again
        server.resume(world="saintjude", new_save=True)
        assert "ask" in server.resume()
        assert store.NOTE_TYPES.count("scene") == 1 and me
    print("PASS p2_resume_test")


if __name__ == "__main__":
    main()
