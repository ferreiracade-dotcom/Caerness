"""Connector-owned tables: idempotent call log, GM notes, meta."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
NOTE_KINDS = ("actor", "location", "general")


def ensure_connector_schema(conn) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
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
        table = "actors" if subject_kind == "actor" else "locations"
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


def notes_for(conn, subject_kind: str, subject_id: int, limit: int = 5) -> list[str]:
    rows = conn.execute(
        "SELECT text FROM gm_notes WHERE subject_kind=? AND subject_id=? ORDER BY id DESC LIMIT ?",
        (subject_kind, int(subject_id), limit),
    ).fetchall()
    return [r["text"] for r in reversed(rows)]
