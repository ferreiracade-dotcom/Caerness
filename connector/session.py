"""resume: the rulebook plus the current scene, for the start of every chat."""
from __future__ import annotations

from pathlib import Path

from connector import store
from connector.views import compact_scene
from engine.player import get_player

RULEBOOK_PATH = Path(__file__).with_name("rulebook.md")
CREATION_PATH = Path(__file__).with_name("creation.md")
HOW_TO_PLAY = """1. Check established facts with scene or lookup, and the setting with lore; where the engine is silent, invent plausibly and never contradict it.
2. Consequential intentions go through act first (pay, hire, lend, demand, attack, trade, order, or the scene actions); then write the scene, dialogue and detail around what it returns.
3. Passing time goes through advance; the player directs significant skips.
4. Record what should last with note (kind=detail|recap|sheet|rule|error); make someone or something new real with author.
5. Every act, advance, note and author needs a fresh call_id; reuse it only to retry the same call."""

SHEET_MISSING = "Draft the protagonist's sheet from scene, lookup and play so far; save each field with note kind=sheet."


def load_rulebook() -> str:
    return RULEBOOK_PATH.read_text(encoding="utf-8")


def load_creation() -> str:
    return CREATION_PATH.read_text(encoding="utf-8")


def resume(conn) -> dict:
    player = get_player(conn)
    if not player:  # a new campaign: design the protagonist with the player (creation text is returned only now)
        return {"needs_character": True, "creation": load_creation(), "rulebook": load_rulebook()}
    scene = compact_scene(conn)
    conn.execute("INSERT INTO connector_meta(key,value) VALUES ('last_resume_at',datetime('now')) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    conn.commit()
    out = {"rulebook": load_rulebook(), "campaign": player["campaign_name"], "protagonist": scene["protagonist"],
           "scene": scene, "how_to_play": HOW_TO_PLAY}
    story = store.continuity(conn)
    if story:
        out["story"] = story
    if not story.get("character_sheet"):
        out["sheet_missing"] = SHEET_MISSING
    return out
