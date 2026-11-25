"""Undo points: a copy of the save taken before every skip, so the last one can be taken back."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from connector.backup import copy_consistent
from connector.store import _day

KEEP = 3


def _folder(db: Path) -> Path:
    return db.parent / "undo"


def points(db: Path) -> list[Path]:
    """The save's undo points, newest first."""
    return sorted(_folder(db).glob(f"undo-{db.stem}-*.db"), reverse=True)


def take(db: Path) -> Path:
    held = points(db)
    seq = 1 + (int(held[0].stem.rsplit("-", 1)[1]) if held else 0)
    path = _folder(db) / f"undo-{db.stem}-{seq:06d}.db"
    copy_consistent(db, path)
    for old in points(db)[KEEP:]:
        old.unlink(missing_ok=True)
    return path


def _date(conn, day: int) -> str:
    from engine import world_calendar
    from engine.world_package import current_package

    return world_calendar.format_date(current_package(conn), day)


def undo(conn, db: Path, call_id: str, confirm: bool) -> dict:
    """Without confirm: what would be lost. With it: the save as it was before the last skip."""
    row = conn.execute("SELECT tool,result_json FROM connector_calls WHERE call_id=?", (call_id,)).fetchone()
    if row:
        if row["tool"] != "undo":
            raise ValueError("call_id reused with different arguments")
        return {**json.loads(row["result_json"]), "replayed": True}
    held = points(db)
    if not held:
        return {"status": "refused", "reason": "There is no skip left to take back."}
    past = sqlite3.connect(f"{held[0].resolve().as_uri()}?mode=ro", uri=True)
    try:
        day = int(past.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        before = {r[0] for r in past.execute("SELECT call_id FROM connector_calls")}
        lost = []
        for r in conn.execute("SELECT call_id,tool,result_json,world_day FROM connector_calls ORDER BY rowid"):
            if r["call_id"] not in before:
                said = str(json.loads(r["result_json"]).get("summary") or "")
                lost.append({"tool": r["tool"], "day": r["world_day"], "summary": said[:100]})
        out = {"restores_day": day, "restores_date": _date(conn, day), "would_lose": lost[:20]}
        if len(lost) > 20:
            out["would_lose_more"] = len(lost) - 20
        if not confirm:
            return {"status": "preview", "now_day": _day(conn), **out,
                    "to_do_it": "Tell the player what goes, then advance with undo=true, confirm=true and a new call_id."}
        conn.commit()
        past.backup(conn)
    finally:
        past.close()
    held[0].unlink(missing_ok=True)
    done = {"status": "undone", "day": day, "date": out["restores_date"], "lost": out["would_lose"],
            "summary": f"The last skip was taken back; it is day {day} again."}
    conn.execute("INSERT INTO connector_calls(call_id,tool,request_json,result_json,world_day) VALUES (?,?,?,?,?)",
                 (call_id, "undo", "{}", json.dumps(done, ensure_ascii=False), day))
    conn.commit()
    return done
