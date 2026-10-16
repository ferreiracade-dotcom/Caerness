"""resume: the rulebook plus the current scene, for the start of every chat."""
from __future__ import annotations

from pathlib import Path

from connector.views import compact_scene
from engine.player import get_player

RULEBOOK_PATH = Path(__file__).with_name("rulebook.md")
HOW_TO_PLAY = """1. Check established facts with scene or lookup; where the engine is silent, invent plausibly and never contradict it.
2. Consequential intentions go through act first; then write the scene, dialogue and detail around what it returns.
3. Passing time goes through advance; the player directs significant skips.
4. Record lasting improvised details with note.
5. Every act, advance and note needs a fresh call_id; reuse it only to retry the same call."""


def load_rulebook() -> str:
    return RULEBOOK_PATH.read_text(encoding="utf-8")


def resume(conn) -> dict:
    player = get_player(conn)
    if not player:
        return {"needs_setup": True,
                "how": 'Run: python connector/setup_campaign.py --campaign NAME --actor "Full Name"'}
    scene = compact_scene(conn)
    conn.execute("INSERT INTO connector_meta(key,value) VALUES ('last_resume_at',datetime('now')) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    conn.commit()
    return {"rulebook": load_rulebook(), "campaign": player["campaign_name"], "protagonist": scene["protagonist"],
            "scene": scene, "how_to_play": HOW_TO_PLAY}
