"""lore: World Bible passages (setting canon) for the GM, searched in the campaign's canon index."""
from __future__ import annotations

from engine.canon import search_canon

MAX_PASSAGES = 3
PASSAGE_CHARS = 1800


def lore(conn, query: str) -> dict:
    q = " ".join(str(query or "").split())
    hits = search_canon(q, limit=MAX_PASSAGES, conn=conn) if q else []
    passages = [{"section": h.heading_path or h.source,
                 "text": h.text if len(h.text) <= PASSAGE_CHARS else h.text[: PASSAGE_CHARS - 1].rstrip() + "…"}
                for h in hits]
    out = {"query": q, "passages": passages}
    if not passages:
        out["hint"] = "No World Bible passage matched; try other words (names, terms, places)."
    return out
