from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from .db import connect, init_db

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANON = ROOT / "canon" / "world_bible_current.docx"
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class CanonChunk:
    id: int
    source: str
    heading_path: str
    text: str
    score: float = 0.0


def _sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _text_of(element: ET.Element) -> str:
    pieces: list[str] = []
    for node in element.iter():
        if node.tag == W_NS + "t" and node.text:
            pieces.append(node.text)
        elif node.tag == W_NS + "tab":
            pieces.append("\t")
        elif node.tag in (W_NS + "br", W_NS + "cr"):
            pieces.append("\n")
    return "".join(pieces).strip()


def _paragraph_style(paragraph: ET.Element, styles: dict[str, str]) -> str:
    ppr = paragraph.find(W_NS + "pPr")
    if ppr is None:
        return ""
    pstyle = ppr.find(W_NS + "pStyle")
    if pstyle is None:
        return ""
    style_id = pstyle.attrib.get(W_NS + "val", "")
    return styles.get(style_id, style_id)


def _read_styles(zf: zipfile.ZipFile) -> dict[str, str]:
    try:
        root = ET.fromstring(zf.read("word/styles.xml"))
    except KeyError:
        return {}
    styles: dict[str, str] = {}
    for style in root.findall(W_NS + "style"):
        style_id = style.attrib.get(W_NS + "styleId", "")
        name = style.find(W_NS + "name")
        if style_id and name is not None:
            styles[style_id] = name.attrib.get(W_NS + "val", style_id)
    return styles


def extract_docx_blocks(path: Path) -> list[tuple[str, str]]:
    """Return (style, text) blocks from paragraphs and table rows using only stdlib OOXML."""
    with zipfile.ZipFile(path) as zf:
        styles = _read_styles(zf)
        root = ET.fromstring(zf.read("word/document.xml"))

    body = root.find(W_NS + "body")
    if body is None:
        return []

    blocks: list[tuple[str, str]] = []
    for child in body:
        if child.tag == W_NS + "p":
            text = _text_of(child)
            if text:
                blocks.append((_paragraph_style(child, styles), text))
        elif child.tag == W_NS + "tbl":
            for row in child.findall(W_NS + "tr"):
                cells = []
                for cell in row.findall(W_NS + "tc"):
                    cell_texts = [_text_of(p) for p in cell.findall(W_NS + "p")]
                    cell_text = " ".join(t for t in cell_texts if t).strip()
                    cells.append(cell_text)
                if any(cells):
                    blocks.append(("Table Row", " | ".join(cells)))
    return blocks


def _heading_level(style: str) -> int | None:
    m = re.search(r"heading\s*([1-9])", style, re.I)
    return int(m.group(1)) if m else None


def _chunk_blocks(blocks: list[tuple[str, str]], target_chars: int = 1800) -> list[tuple[str, str]]:
    headings: list[str] = []
    chunks: list[tuple[str, str]] = []
    buffer: list[str] = []
    buffer_heading = ""
    size = 0

    def flush() -> None:
        nonlocal buffer, size, buffer_heading
        text = "\n".join(buffer).strip()
        if text:
            chunks.append((buffer_heading, text))
        buffer = []
        size = 0

    for style, text in blocks:
        level = _heading_level(style)
        if level:
            flush()
            headings[:] = headings[: level - 1]
            while len(headings) < level - 1:
                headings.append("")
            if len(headings) == level - 1:
                headings.append(text)
            else:
                headings[level - 1] = text
            buffer_heading = " > ".join(h for h in headings if h)
            # Include the heading text in the chunk so FTS can match it.
            buffer.append(text)
            size += len(text)
            continue

        if not buffer_heading:
            buffer_heading = "Document"
        if buffer and size + len(text) > target_chars:
            flush()
            buffer_heading = " > ".join(h for h in headings if h) or "Document"
        buffer.append(text)
        size += len(text)
    flush()
    return chunks


def _ensure_fts(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS canon_chunks_fts
               USING fts5(chunk_id UNINDEXED, heading_path, text, tokenize='unicode61')"""
        )
        return True
    except sqlite3.OperationalError:
        return False


def index_canon(path: Path | str = DEFAULT_CANON, force: bool = False) -> dict:
    init_db()
    path = Path(path).resolve()
    try:
        source_key = str(path.relative_to(ROOT))
    except ValueError:
        source_key = str(path)
    raw = path.read_bytes()
    digest = _sha256(raw)
    blocks = extract_docx_blocks(path)
    chunks = _chunk_blocks(blocks)

    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM canon_sources WHERE source_path=?", (source_key,)
        ).fetchone()
        if existing and existing["content_hash"] == digest and not force:
            return {
                "source": source_key,
                "chunks": int(existing["chunk_count"]),
                "changed": False,
                "fts": _ensure_fts(conn),
            }

        if existing:
            source_id = int(existing["id"])
            conn.execute("DELETE FROM canon_chunks WHERE source_id=?", (source_id,))
            conn.execute(
                "UPDATE canon_sources SET content_hash=?, indexed_at=CURRENT_TIMESTAMP, chunk_count=? WHERE id=?",
                (digest, len(chunks), source_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO canon_sources(source_path,display_name,content_hash,chunk_count) VALUES (?,?,?,?)",
                (source_key, path.name, digest, len(chunks)),
            )
            source_id = int(cur.lastrowid)

        inserted: list[tuple[int, str, str]] = []
        for idx, (heading, text) in enumerate(chunks):
            cur = conn.execute(
                "INSERT INTO canon_chunks(source_id,chunk_index,heading_path,text,content_hash) VALUES (?,?,?,?,?)",
                (source_id, idx, heading, text, _sha256(heading + "\n" + text)),
            )
            inserted.append((int(cur.lastrowid), heading, text))

        fts = _ensure_fts(conn)
        if fts:
            # Rebuild the small index deterministically.
            conn.execute("DELETE FROM canon_chunks_fts")
            for row in conn.execute("SELECT id,heading_path,text FROM canon_chunks ORDER BY id"):
                conn.execute(
                    "INSERT INTO canon_chunks_fts(chunk_id,heading_path,text) VALUES (?,?,?)",
                    (row["id"], row["heading_path"] or "", row["text"]),
                )
        conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('canon_index_version','4')")
        conn.commit()
        return {"source": source_key, "chunks": len(inserted), "changed": True, "fts": fts}


def _fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]*", query)
    # OR is intentionally forgiving for names + concepts. Ranking handles relevance.
    return " OR ".join(f'"{t.replace(chr(34), "")}"' for t in terms[:18])


def _search_canon_with_conn(conn: sqlite3.Connection, query: str, limit: int = 6,
                            exclude_prefixes: tuple[str, ...] = ()) -> list[CanonChunk]:
    if not query.strip():
        return []
    # Heading prefixes a caller must never receive (the narrator excludes engine-only and open Parts).
    excluded = "".join(" AND c.heading_path NOT LIKE ?" for _ in exclude_prefixes)
    excluded_args = tuple(f"{p}%" for p in exclude_prefixes)
    fts = _ensure_fts(conn)
    rows = []
    if fts:
        q = _fts_query(query)
        if q:
            try:
                rows = conn.execute(
                    """SELECT c.id,c.heading_path,c.text,s.display_name,bm25(canon_chunks_fts) AS rank
                       FROM canon_chunks_fts
                       JOIN canon_chunks c ON c.id=canon_chunks_fts.chunk_id
                       JOIN canon_sources s ON s.id=c.source_id
                       WHERE canon_chunks_fts MATCH ?""" + excluded + """
                       ORDER BY rank LIMIT ?""",
                    (q, *excluded_args, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
    if not rows:
        terms = {t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]*", query) if len(t) > 2}
        candidates = conn.execute(
            """SELECT c.id,c.heading_path,c.text,s.display_name
               FROM canon_chunks c JOIN canon_sources s ON s.id=c.source_id WHERE 1=1""" + excluded,
            excluded_args,
        ).fetchall()
        scored = []
        for row in candidates:
            hay = ((row["heading_path"] or "") + " " + row["text"]).lower()
            score = sum(2 if t in (row["heading_path"] or "").lower() else 1 for t in terms if t in hay)
            if score:
                scored.append((score, row))
        scored.sort(key=lambda x: (-x[0], int(x[1]["id"])))
        return [
            CanonChunk(int(r["id"]), str(r["display_name"]), str(r["heading_path"] or ""), str(r["text"]), float(score))
            for score, r in scored[:limit]
        ]

    return [
        CanonChunk(
            int(r["id"]),
            str(r["display_name"]),
            str(r["heading_path"] or ""),
            str(r["text"]),
            float(-r["rank"] if r["rank"] is not None else 0.0),
        )
        for r in rows
    ]


def search_canon(query: str, limit: int = 6, conn: sqlite3.Connection | None = None,
                 exclude_prefixes: tuple[str, ...] = ()) -> list[CanonChunk]:
    """Search indexed canon. Pass the active simulation connection to avoid nested SQLite locks."""
    if conn is not None:
        return _search_canon_with_conn(conn, query, limit, exclude_prefixes)

    init_db()
    with connect() as owned:
        has_chunks = owned.execute("SELECT COUNT(*) FROM canon_chunks").fetchone()[0]
    if not has_chunks and DEFAULT_CANON.exists():
        index_canon(DEFAULT_CANON)
    with connect() as owned:
        return _search_canon_with_conn(owned, query, limit, exclude_prefixes)

def get_chunks(ids: list[int]) -> list[CanonChunk]:
    if not ids:
        return []
    with connect() as conn:
        marks = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"""SELECT c.id,c.heading_path,c.text,s.display_name
                FROM canon_chunks c JOIN canon_sources s ON s.id=c.source_id
                WHERE c.id IN ({marks})""",
            ids,
        ).fetchall()
        by_id = {int(r["id"]): r for r in rows}
        return [
            CanonChunk(i, str(by_id[i]["display_name"]), str(by_id[i]["heading_path"] or ""), str(by_id[i]["text"]))
            for i in ids if i in by_id
        ]


def canon_status() -> dict:
    init_db()
    with connect() as conn:
        sources = [dict(r) for r in conn.execute("SELECT * FROM canon_sources ORDER BY id")]
        return {"sources": sources, "fts5": _ensure_fts(conn)}
