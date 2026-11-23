"""The entry date: where in the world's history the protagonist's story opens.

The default is the day the world package opens (day 0 of the opening world, already carrying its lived history). A player may ask for a
later entry: the engine then simulates the years in between BEFORE the protagonist exists, one chunk of at most a year per call, so no single
call runs long and a stall is visible. Nothing is invented for the gap: it is the ordinary run. The time a chunk took is measured and
reported, and the rest is estimated from it, so the player is told the real cost on the machine that is running it.

No world words here: the dates come from the package calendar.
"""
from __future__ import annotations

import re
import sqlite3
import time
from datetime import date

from . import world_calendar
from .world_package import package_for

CHUNK_DAYS = 365  # one simulated year per call at most


class EntryRefused(ValueError):
    reason_kind = "contradiction"


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _target_day(conn: sqlite3.Connection, details: dict) -> int:
    pkg = package_for(conn)
    if details.get("years") is not None:
        y = details["years"]
        if isinstance(y, bool) or not isinstance(y, (int, float)) or y <= 0:
            raise EntryRefused("years must be a positive number of years after the opening")
        return _day(conn) + int(round(float(y) * 365.25))
    text = str(details.get("date") or details.get("year") or "").strip()
    if re.fullmatch(r"\d{4}", text):
        text += "-01-01"
    try:
        want = date.fromisoformat(text)
    except ValueError:
        raise EntryRefused("give the entry as a year (\"1980\") or an ISO date (\"1980-01-01\"), or as a number of years after the opening") from None
    return int((want - world_calendar._date(pkg, 0)).days)


def describe(conn: sqlite3.Connection, details: dict) -> dict:
    """The entry the player asked for, without running anything: where the story stands, where it would open, the years the engine would
    simulate and an honest note on the time."""
    pkg = package_for(conn)
    now = _day(conn)
    target = _target_day(conn, details)
    if target < now:
        raise EntryRefused(f"the world already stands at {world_calendar.format_date(pkg, now)}; an entry cannot be earlier than that")
    days = target - now
    out = {"status": "draft", "kind": "entry", "from": world_calendar.format_date(pkg, now), "to": world_calendar.format_date(pkg, target),
           "days": days, "years": round(days / 365.25, 2), "default": days == 0}
    if days:
        out["note"] = (f"This simulates the {out['years']} years in between, before the character exists, so the city, its families, outfits, "
                       "businesses and politics have really lived them. It runs one year per call and each call takes minutes on the server "
                       "(the engine reports the measured time after the first year). Tell the player this and ask before starting. The "
                       "alternative is the default entry, with no waiting.")
    return out


def run_chunk(conn: sqlite3.Connection, details: dict) -> dict:
    """Simulate up to one year toward the entry date and say how far it got. Call again until `reached`."""
    from .player import get_player
    from .simulation import advance_connection
    if get_player(conn):
        raise EntryRefused("the story has already begun with a protagonist; the entry date cannot change")
    pkg = package_for(conn)
    now = _day(conn)
    target = _target_day(conn, details)
    if target < now:
        raise EntryRefused(f"the world already stands at {world_calendar.format_date(pkg, now)}; an entry cannot be earlier than that")
    left = target - now
    if left == 0:
        return {"status": "reached", "kind": "entry", "date": world_calendar.format_date(pkg, now), "day": now, "remaining_days": 0}
    step = min(CHUNK_DAYS, left)
    t0 = time.time()
    advance_connection(conn, step)
    took = time.time() - t0
    now = _day(conn)
    remaining = target - now
    out = {"status": "reached" if remaining <= 0 else "running", "kind": "entry", "date": world_calendar.format_date(pkg, now), "day": now,
           "simulated_days": step, "seconds_taken": round(took, 1), "remaining_days": max(0, remaining)}
    if remaining > 0:
        out["estimated_seconds_left"] = int(took * remaining / max(1, step))
        out["note"] = "Call again with the same details to continue; it is finished when status is reached."
    return out
