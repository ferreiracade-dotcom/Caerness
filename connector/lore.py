"""lore: World Bible passages (setting canon) for the GM, searched in the campaign's canon index."""
from __future__ import annotations

import re

from engine.canon import search_canon

MAX_PASSAGES = 3
PASSAGE_CHARS = 4000  # a passage is returned whole up to this size, cut only at a paragraph boundary
_CONTINUE = re.compile(r"^chunk\s+(\d+)\s+part\s+(\d+)$", re.I)


def _pages(text: str, cap: int = PASSAGE_CHARS) -> list[str]:
    """Split text into pages of at most `cap` characters, breaking at paragraph (line) boundaries.

    A single paragraph longer than `cap` is broken at its last sentence end (else space) before `cap`.
    """
    pages: list[str] = []
    cur: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal cur, size
        if cur:
            pages.append("\n".join(cur))
        cur, size = [], 0

    for para in text.split("\n"):
        while len(para) > cap:
            window = para[:cap]
            cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
            cut = cut + 1 if cut > cap // 3 else (window.rfind(" ") if window.rfind(" ") > 0 else cap)
            flush()
            pages.append(para[:cut].rstrip())
            para = para[cut:].lstrip()
        if cur and size + len(para) + 1 > cap:
            flush()
        cur.append(para)
        size += len(para) + 1
    flush()
    return pages or [""]


def _passage(chunk_id: int, section: str, text: str, part: int = 1) -> dict:
    pages = _pages(text)
    part = min(max(part, 1), len(pages))
    out = {"section": section, "chunk": chunk_id, "text": pages[part - 1]}
    if len(pages) > 1:
        out["part"] = f"{part} of {len(pages)}"
    if part < len(pages):
        out["text"] += f"\n(continues: ask lore for 'chunk {chunk_id} part {part + 1}')"
    return out


def lore(conn, query: str) -> dict:
    q = " ".join(str(query or "").split())
    m = _CONTINUE.match(q)
    if m:  # a continuation request: the rest of one long passage
        row = conn.execute(
            """SELECT c.id,c.heading_path,c.text,s.display_name FROM canon_chunks c
               JOIN canon_sources s ON s.id=c.source_id WHERE c.id=?""", (int(m.group(1)),)).fetchone()
        if row is None:
            return {"query": q, "passages": [], "hint": "No such passage; search by words instead."}
        return {"query": q, "passages": [_passage(int(row["id"]), row["heading_path"] or row["display_name"],
                                                  row["text"], int(m.group(2)))]}
    hits = search_canon(q, limit=MAX_PASSAGES, conn=conn) if q else []
    passages = [_passage(h.id, h.heading_path or h.source, h.text) for h in hits]
    out = {"query": q, "passages": passages}
    if not passages:
        out["hint"] = "No World Bible passage matched; try other words (names, terms, places)."
    return out
