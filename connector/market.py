"""What money could buy, as the scene sees it: the prices of what is in play, what is on his mind and the chances open."""
from __future__ import annotations

from connector import store
from engine import price_book, temptations, wants
from engine.player import get_player


def _me(conn) -> int:
    pl = get_player(conn)
    if not pl:
        raise ValueError("no protagonist is set")
    return int(pl["player_actor_id"])


def want_note(conn, field, subject_id, text) -> dict:
    return wants.say(conn, _me(conn), field, subject_id, text)


def chance_note(conn, field, subject_id) -> dict:
    return temptations.say(conn, _me(conn), field, subject_id)


def wants_of(conn, who: str, me: int | None) -> dict:
    """What someone wants, for the game master to play them by; no name means the protagonist."""
    if who:
        row = conn.execute("SELECT id,name FROM actors WHERE actor_type='character' AND (name=? COLLATE NOCASE OR CAST(id AS TEXT)=?)",
                           (who, who)).fetchone()
    else:
        row = conn.execute("SELECT id,name FROM actors WHERE id=?", (me,)).fetchone() if me is not None else None
    if row is None:
        return {"found": False, "hint": "ask as 'wants <full name or id>'"}
    return {"found": True, "kind": "wants", "who": row[1], "wants": wants.view(conn, int(row[0]), 6)}


def _talk(conn) -> list[str]:
    """What the story is on just now: the last scene as recorded, and the open threads."""
    kept = store.last_scene(conn) or {}
    live = store.continuity(conn).get("live_thread") or {}
    return [kept.get("text") or "", *(live.get("open_threads") or [])]


def scene_block(conn, me: int) -> dict | None:
    out = {}
    prices = price_book.in_play(conn, _talk(conn), me)
    if prices:
        out["prices"] = prices
    wants.refresh(conn, me)
    on_mind = wants.view(conn, me)
    if on_mind:
        out["wants"] = on_mind
    chances = temptations.open_for(conn, me)
    if chances:
        out["chances"] = chances
    today = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    gone = temptations.gone_for(conn, me, today - 14)
    if gone:
        out["chances_gone"] = gone
    conn.commit()
    return out or None
