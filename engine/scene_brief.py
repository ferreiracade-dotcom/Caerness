"""SCENE-01 step 1: reading lenses and culture briefs carried by every scene packet.

The World Bible keeps formality, manners, dress and custom as prose canon for the narrative layer
(Part 25 §XII). Keyword search over the canon almost never delivered them: in 400 simulated scenes the
etiquette, dress and regional-culture sections were sent about zero times, while the simulation registry
took 36% of the slots (docs/research/2026-10-09-world-bible-narrator-coverage.md). So the scene packet now
carries short briefs condensed from named World Bible sections (canon/scene_briefs.json), and canon search
for the narrator excludes the parts that are engine data or undecided canon.

Each brief records a digest of its source sections. brief_staleness() reports briefs whose sources changed
since they were written, so a World Bible edit cannot silently leave a brief behind (no grandfathering).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

BRIEFS_PATH = Path(__file__).resolve().parent.parent / "canon" / "scene_briefs.json"

# Never handed to the narrator by search: the title chunk, canon-status rules (Part Zero's reading lenses
# reach the narrator through the lenses brief instead), the simulation registry and the open-questions ledger.
NARRATOR_EXCLUDED_PARTS = ("Caerness World Bible", "Part Zero —", "Part Twenty-Four —", "Part Twenty-Five —")


@lru_cache(maxsize=1)
def load_briefs() -> dict[str, Any]:
    return json.loads(BRIEFS_PATH.read_text(encoding="utf-8"))


def narrator_may_receive(heading_path: str | None) -> bool:
    return not str(heading_path or "").startswith(NARRATOR_EXCLUDED_PARTS)


def location_culture(conn: sqlite3.Connection, location_id: int | None) -> str | None:
    """Culture key of a place: the Hearth by its own membership rule, otherwise the nearest political owner."""
    if location_id is None:
        return None
    from .cultivation import _location_chain, location_in_hearth
    if location_in_hearth(conn, location_id):
        return "hearth"
    owners = load_briefs()["owner_culture"]
    for row in _location_chain(conn, location_id):
        owner = row["political_owner"]
        if owner:
            return owners.get(str(owner))
    return None


def actor_culture(conn: sqlite3.Connection, actor_id: int) -> str | None:
    """Where a person is from, read from their home place (their current place if no home is recorded)."""
    row = conn.execute("SELECT home_location_id,current_location_id FROM actors WHERE id=?", (int(actor_id),)).fetchone()
    if not row:
        return None
    return location_culture(conn, row["home_location_id"] if row["home_location_id"] is not None else row["current_location_id"])


def build_scene_brief(conn: sqlite3.Connection, location_id: int | None, present_actor_ids: Iterable[int] = (),
                      *, max_cultures: int = 3) -> dict[str, Any]:
    """The fixed part of a scene's canon: the reading lenses, the place's culture, and the cultures of
    present people who are from elsewhere (most common first)."""
    briefs = load_briefs()
    cultures = briefs["cultures"]
    out: list[dict[str, Any]] = []
    place = location_culture(conn, location_id)
    if place in cultures:
        out.append({"culture": place, "applies": "this place", **_culture_view(cultures[place])})
    visitors: dict[str, int] = {}
    for aid in present_actor_ids:
        key = actor_culture(conn, int(aid))
        if key and key != place and key in cultures:
            visitors[key] = visitors.get(key, 0) + 1
    for key in sorted(visitors, key=lambda k: (-visitors[k], k))[: max(0, max_cultures - len(out))]:
        out.append({"culture": key, "applies": "people present from elsewhere", **_culture_view(cultures[key])})
    lenses = briefs["lenses"]
    return {"reading_lenses": {"title": lenses["title"], "text": lenses["text"]}, "cultures": out}


def _culture_view(brief: dict[str, Any]) -> dict[str, Any]:
    return {"name": brief["name"], "depth": brief["depth"], "text": brief["text"]}


def source_digest(conn: sqlite3.Connection, headings: Iterable[str]) -> str:
    """Digest of the indexed World Bible text under these headings (whole sections, in index order)."""
    h = hashlib.sha256()
    for heading in headings:
        rows = conn.execute("SELECT text FROM canon_chunks WHERE heading_path=? ORDER BY id", (heading,)).fetchall()
        if not rows:
            h.update(f"<missing:{heading}>".encode("utf-8"))
        for (text,) in rows:
            h.update(text.encode("utf-8"))
    return h.hexdigest()[:16]


def _all_briefs(briefs: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("lenses", briefs["lenses"])] + [(f"culture:{k}", v) for k, v in briefs["cultures"].items()]


def brief_staleness(conn: sqlite3.Connection) -> list[dict[str, str]]:
    """Briefs whose World Bible sources differ from when they were written. Needs an indexed canon."""
    stale = []
    for key, brief in _all_briefs(load_briefs()):
        now = source_digest(conn, brief["sources"])
        if now != brief.get("digest"):
            stale.append({"brief": key, "recorded": str(brief.get("digest")), "current": now})
    return stale


def stamp_digests(conn: sqlite3.Connection) -> int:
    """Record current source digests in canon/scene_briefs.json. Run only after re-reading changed sources
    and rewriting the affected briefs; stamping is the author's statement that the brief is current."""
    briefs = json.loads(BRIEFS_PATH.read_text(encoding="utf-8"))
    changed = 0
    for _key, brief in _all_briefs(briefs):
        now = source_digest(conn, brief["sources"])
        if brief.get("digest") != now:
            brief["digest"] = now
            changed += 1
    BRIEFS_PATH.write_text(json.dumps(briefs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    load_briefs.cache_clear()
    return changed
