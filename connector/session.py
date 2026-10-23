"""resume: the rulebook plus the current scene, for the start of every chat."""
from __future__ import annotations

import re
from pathlib import Path

from connector import store
from connector.views import compact_scene
from engine.player import get_player
from engine.world_package import configured_package_id, current_package, load_package

RULEBOOK_CORE_PATH = Path(__file__).with_name("rulebook_core.md")
CREATION_CORE_PATH = Path(__file__).with_name("creation_core.md")
_MARK = re.compile(r"^\{\{world:(\w+)\}\}\n", re.M)
_HEAD = re.compile(r"^\{\{(\w+)\}\}\n", re.M)
HOW_TO_PLAY = """1. Check established facts with scene or lookup, and the setting with lore; where the engine is silent, invent plausibly and never contradict it.
2. Consequential intentions go through act first (pay, hire, lend, demand, attack, trade, order, or the scene actions); then write the scene, dialogue and detail around what it returns.
3. Passing time goes through advance; the player directs significant skips.
4. Record what should last with note (kind=detail|recap|sheet|rule|error); make someone or something new real with author.
5. Every act, advance, note and author needs a fresh call_id; reuse it only to retry the same call."""

SHEET_MISSING = "Draft the protagonist's sheet from scene, lookup and play so far; save each field with note kind=sheet."


def _package(conn):
    return current_package(conn) if conn is not None else load_package(configured_package_id())


def _blocks(path) -> dict[str, str]:
    """A world section: `{{name}}` header lines, each followed by the text that replaces `{{world:name}}` in the core."""
    parts = _HEAD.split(path.read_text(encoding="utf-8")) if path else [""]
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def load_rulebook(conn=None) -> str:
    """The shared core with the campaign's world section spliced in at its markers."""
    blocks = _blocks(_package(conn).rulebook_section)
    core = RULEBOOK_CORE_PATH.read_text(encoding="utf-8")
    out = _MARK.sub(lambda m: blocks.get(m.group(1), ""), core)
    return out if all(k in blocks for k in _MARK.findall(core)) else re.sub(r"\n{3,}", "\n\n", out)


def load_creation(conn=None) -> str:
    return (_package(conn).creation_section or CREATION_CORE_PATH).read_text(encoding="utf-8")


def resume(conn) -> dict:
    player = get_player(conn)
    if not player:  # a new campaign: design the protagonist with the player (creation text is returned only now)
        return {"needs_character": True, "creation": load_creation(conn), "rulebook": load_rulebook(conn)}
    scene = compact_scene(conn)
    conn.execute("INSERT INTO connector_meta(key,value) VALUES ('last_resume_at',datetime('now')) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    conn.commit()
    out = {"rulebook": load_rulebook(conn), "campaign": player["campaign_name"], "protagonist": scene["protagonist"],
           "scene": scene, "how_to_play": HOW_TO_PLAY}
    story = store.continuity(conn)
    if story:
        out["story"] = story
    if not story.get("character_sheet"):
        out["sheet_missing"] = SHEET_MISSING
    return out
