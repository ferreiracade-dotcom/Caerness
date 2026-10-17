"""Connector-owned tables: idempotent call log, GM notes, meta."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
NOTE_KINDS = ("actor", "location", "general", "business", "outfit", "household", "crew", "institution")
_NOTE_TABLES = {"actor": "actors", "institution": "actors", "location": "locations", "business": "civilian_enterprises",
                "outfit": "underworld_organizations", "household": "households", "crew": "underworld_crews"}


def ensure_connector_schema(conn) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='gm_notes'").fetchone()
    if row and "'household'" not in row[0]:  # an older campaign: widen the subject kinds the notes may be about
        conn.executescript("""
            ALTER TABLE gm_notes RENAME TO gm_notes_old;
            DROP INDEX IF EXISTS idx_gm_notes_subject;
        """)
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO gm_notes(id,subject_kind,subject_id,text,provenance,world_day,call_id) "
                     "SELECT id,subject_kind,subject_id,text,provenance,world_day,call_id FROM gm_notes_old")
        conn.execute("DROP TABLE gm_notes_old")
    conn.commit()


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def run_once(conn, call_id: str, tool: str, request: dict, fn: Callable[[], dict]) -> dict:
    """Run fn() at most once per call_id; the result is stored in the same transaction."""
    req = _canon(request)
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")  # waits up to busy_timeout for a concurrent writer
    try:
        row = conn.execute("SELECT tool,request_json,result_json FROM connector_calls WHERE call_id=?", (call_id,)).fetchone()
        if row:
            conn.rollback()
            if row["tool"] != tool or row["request_json"] != req:
                raise ValueError("call_id reused with different arguments")
            return {**json.loads(row["result_json"]), "replayed": True}
        result = fn()
        conn.execute(
            "INSERT INTO connector_calls(call_id,tool,request_json,result_json,world_day) VALUES (?,?,?,?,?)",
            (call_id, tool, req, json.dumps(result, ensure_ascii=False, default=str), _day(conn)),
        )
        conn.commit()
        return result
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise


def recent_operations(conn, limit: int = 3) -> list[dict]:
    out = []
    for r in conn.execute("SELECT call_id,tool,result_json,world_day FROM connector_calls ORDER BY rowid DESC LIMIT ?", (limit,)):
        try:
            summary = json.loads(r["result_json"]).get("summary", "")
        except Exception:
            summary = ""
        out.append({"call_id": r["call_id"], "tool": r["tool"], "summary": summary, "day": r["world_day"]})
    return out


def add_note(conn, subject_kind: str, subject_id: int | None, text: str, call_id: str) -> dict:
    """Insert a GM note. Does not commit: callers run it inside run_once."""
    if subject_kind not in NOTE_KINDS:
        raise ValueError(f"subject_kind must be one of {NOTE_KINDS}")
    text = (text or "").strip()
    if not 1 <= len(text) <= 500:
        raise ValueError("note text must be 1-500 characters")
    if subject_kind == "general":
        subject_id = None
    else:
        table = _NOTE_TABLES[subject_kind]
        if subject_id is None or not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (int(subject_id),)).fetchone():
            raise ValueError(f"unknown {subject_kind} id {subject_id}")
        subject_id = int(subject_id)
    cur = conn.execute(
        "INSERT INTO gm_notes(subject_kind,subject_id,text,world_day,call_id) VALUES (?,?,?,?,?)",
        (subject_kind, subject_id, text, _day(conn), call_id),
    )
    out = {"note_id": int(cur.lastrowid), "subject_kind": subject_kind, "subject_id": subject_id,
           "summary": f"Noted ({subject_kind}): {text[:80]}"}
    return {k: v for k, v in out.items() if v is not None}


def notes_for(conn, subject_kind: str, subject_id: int, limit: int = 5, offset: int = 0) -> list[str]:
    rows = conn.execute(
        "SELECT text FROM gm_notes WHERE subject_kind=? AND subject_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
        (subject_kind, int(subject_id), limit, offset),
    ).fetchall()
    return [r["text"] for r in reversed(rows)]


def notes_count(conn, subject_kind: str, subject_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM gm_notes WHERE subject_kind=? AND subject_id=?", (subject_kind, int(subject_id))).fetchone()[0])


NOTE_TYPES = ("detail", "recap", "rule", "sheet", "error")
SHEET_FIELDS = ("appearance", "voice", "temperament", "ambitions", "habits", "history", "standing")
_CLIP = {"recap": 600, "thread": 160, "sheet": 300, "rule": 300, "error": 500}
MAX_THREADS = 8
MAX_RULES = 8  # newest active rules returned by resume
MAX_CORRECTIONS = 5  # newest open error reports returned by resume


def _clip(text, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def record(conn, kind: str, text: str, call_id: str, *, subject_kind: str = "general", subject_id: int | None = None,
           threads: list[str] | None = None, field: str | None = None) -> dict:
    """Record something that should last across chats. Does not commit: callers run it inside run_once."""
    if kind not in NOTE_TYPES:
        raise ValueError(f"kind must be one of {NOTE_TYPES}")
    if kind == "detail":
        return add_note(conn, subject_kind, subject_id, text, call_id)
    body = _clip(text, _CLIP[kind])
    if not body:
        raise ValueError("text must not be empty")
    clipped = {"clipped": f"{kind} text was cut to {_CLIP[kind]} characters"} if len(" ".join(str(text).split())) > _CLIP[kind] else {}
    day = _day(conn)
    if kind == "recap":
        wanted = [t for t in (threads or []) if str(t or "").strip()]
        open_threads = [_clip(t, _CLIP["thread"]) for t in wanted][:MAX_THREADS]
        conn.execute("INSERT INTO campaign_recaps(world_day,text,threads_json,call_id) VALUES (?,?,?,?)",
                     (day, body, json.dumps(open_threads, ensure_ascii=False), call_id))
        out = {"saved": "recap", "threads": len(open_threads), "summary": f"Recap saved: {body[:80]}", **clipped}
        if len(wanted) > MAX_THREADS:
            out["threads_dropped"] = f"{len(wanted) - MAX_THREADS} threads over the limit of {MAX_THREADS} were not kept; fold them into others or the recap text"
        return out
    if kind == "sheet":
        if field not in SHEET_FIELDS and not re.fullmatch(r"[a-z][a-z _]{1,28}", str(field or "")):
            raise ValueError(f"field must be one of {SHEET_FIELDS}, or a short lower-case label of your own")
        conn.execute("INSERT INTO character_sheet(field,text,world_day,call_id) VALUES (?,?,?,?) "
                     "ON CONFLICT(field) DO UPDATE SET text=excluded.text,world_day=excluded.world_day,call_id=excluded.call_id",
                     (field, body, day, call_id))
        return {"saved": "sheet", "field": field, "summary": f"Sheet {field} saved", **clipped}
    if kind == "rule" and field == "retire":
        row = conn.execute("SELECT id FROM standing_rules WHERE status='active' AND text=? ORDER BY id DESC LIMIT 1", (body,)).fetchone()
        if not row:
            raise ValueError("no active rule matches that text exactly")
        conn.execute("UPDATE standing_rules SET status='retired' WHERE id=?", (int(row[0]),))
        return {"saved": "rule", "retired": True, "summary": f"Rule retired: {body[:80]}"}
    if kind == "error" and field == "fixed":
        rows = conn.execute("SELECT id,text FROM error_reports WHERE status='open' ORDER BY id DESC").fetchall()
        row = next((r for r in rows if (body.isdigit() and r["id"] == int(body)) or r["text"] == body), None)
        if not row:
            raise ValueError("no open error report matches that text or id")
        conn.execute("UPDATE error_reports SET status='fixed' WHERE id=?", (int(row["id"]),))
        return {"saved": "error", "fixed": True, "summary": f"Correction done: {row['text'][:80]}"}
    table = "standing_rules" if kind == "rule" else "error_reports"
    conn.execute(f"INSERT INTO {table}(world_day,text,call_id) VALUES (?,?,?)", (day, body, call_id))
    return {"saved": kind, "summary": f"{kind.capitalize()} saved: {body[:80]}", **clipped}


def continuity(conn) -> dict:
    """The story so far for a new chat: recent recaps, open threads, the protagonist's sheet, standing rules."""
    recaps = conn.execute("SELECT text,threads_json FROM campaign_recaps ORDER BY id DESC LIMIT 3").fetchall()
    out: dict = {}
    if recaps:
        live = {"recent": [r["text"] for r in reversed(recaps)]}
        threads = json.loads(recaps[0]["threads_json"] or "[]")
        if threads:
            live["open_threads"] = threads
        older = int(conn.execute("SELECT COUNT(*) FROM campaign_recaps").fetchone()[0]) - len(recaps)
        if older > 0:
            live["older_recaps"] = older
        out["live_thread"] = live
    sheet = {r["field"]: r["text"] for r in conn.execute("SELECT field,text FROM character_sheet")}
    if sheet:
        out["character_sheet"] = {**{f: sheet[f] for f in SHEET_FIELDS if f in sheet}, **{f: t for f, t in sheet.items() if f not in SHEET_FIELDS}}
    rules = [r["text"] for r in conn.execute("SELECT text FROM standing_rules WHERE status='active' ORDER BY id DESC LIMIT ?", (MAX_RULES,))][::-1]
    if rules:
        out["standing_rules"] = rules
        total = int(conn.execute("SELECT COUNT(*) FROM standing_rules WHERE status='active'").fetchone()[0])
        if total > len(rules):
            out["standing_rules_more"] = total - len(rules)
    open_errors = [r["text"] for r in conn.execute("SELECT text FROM error_reports WHERE status='open' ORDER BY id DESC LIMIT ?", (MAX_CORRECTIONS,))]
    if open_errors:
        out["corrections"] = open_errors
        total = int(conn.execute("SELECT COUNT(*) FROM error_reports WHERE status='open'").fetchone()[0])
        if total > len(open_errors):
            out["corrections_more"] = total - len(open_errors)
    return out


HINT_AFTER_CALLS = 40


def bump_calls(conn, tool: str) -> int:
    """Count tool calls since the last resume (stored, so restarts keep it); resume resets the count."""
    if tool == "resume":
        n = 0
    else:
        row = conn.execute("SELECT value FROM connector_meta WHERE key='calls_since_resume'").fetchone()
        n = (int(row[0]) if row else 0) + 1
    conn.execute("INSERT INTO connector_meta(key,value) VALUES ('calls_since_resume',?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(n),))
    conn.commit()
    return n
