"""Who is with the protagonist: those they travel with, are shown beside them or are dealing with today, their household at
home and the people of their workplace. These are there; whether they are is not drawn from habit."""
from __future__ import annotations

import sqlite3
from typing import Iterable

from .presence import _active_travel, _location_is_large, actor_is_present_candidate


def _me(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("""SELECT a.id,a.home_location_id,a.current_location_id,w.current_day FROM player_state p
                           JOIN actors a ON a.id=p.player_actor_id JOIN world_state w ON w.id=1 WHERE p.id=1""").fetchone()


def _kept(conn: sqlite3.Connection) -> bool:
    """A save from before this record has no one on it."""
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='company'").fetchone() is not None


def join(conn: sqlite3.Connection, ids: Iterable[int]) -> None:
    """These people are with the protagonist where they stand, for the rest of the day."""
    me = _me(conn)
    if me is None or me["current_location_id"] is None or not _kept(conn):
        return
    for aid in ids:
        if aid is None or int(aid) == int(me["id"]):
            continue
        conn.execute("""INSERT INTO company(actor_id,location_id,day) VALUES (?,?,?)
                        ON CONFLICT(actor_id) DO UPDATE SET location_id=excluded.location_id,day=excluded.day""",
                     (int(aid), int(me["current_location_id"]), int(me["current_day"])))


def leave_all(conn: sqlite3.Connection) -> None:
    if _kept(conn):
        conn.execute("DELETE FROM company")


def with_player(conn: sqlite3.Connection, location_id: int | None = None) -> set[int]:
    """The living people certainly with the protagonist where they stand; empty for any other place."""
    me = _me(conn)
    if me is None or me["current_location_id"] is None:
        return set()
    here, mine = int(me["current_location_id"]), int(me["id"])
    if location_id is not None and int(location_id) != here:
        return set()
    ids = {int(r[0]) for r in conn.execute(
        "SELECT actor_id FROM company WHERE location_id=? AND day>=?", (here, int(me["current_day"])))} if _kept(conn) else set()
    steady: set[int] = set()
    if me["home_location_id"] is not None and int(me["home_location_id"]) == here:
        steady |= {int(r[0]) for r in conn.execute(
            """SELECT m.actor_id FROM household_members m JOIN actors a ON a.id=m.actor_id
               WHERE m.status='active' AND a.home_location_id=? AND m.household_id IN
                 (SELECT household_id FROM household_members WHERE actor_id=? AND status='active')""", (here, mine))}
    for e in conn.execute(
            """SELECT id,owner_actor_id FROM civilian_enterprises WHERE location_id=? AND status IN ('active','strained','insolvent')
               AND (owner_actor_id=? OR id IN (SELECT enterprise_id FROM enterprise_staff WHERE actor_id=? AND status='active'))""",
            (here, mine, mine)).fetchall():
        steady |= {int(r[0]) for r in conn.execute(
            "SELECT actor_id FROM enterprise_staff WHERE enterprise_id=? AND status='active'", (int(e["id"]),))}
        if e["owner_actor_id"] is not None:
            steady.add(int(e["owner_actor_id"]))
    ids |= {i for i in steady if _active_travel(conn, i) is None}  # someone on the road is not at home or at work
    ids.discard(mine)
    if not ids:
        return set()
    marks = ",".join("?" for _ in ids)
    return {int(r[0]) for r in conn.execute(f"SELECT id FROM actors WHERE status='active' AND id IN ({marks})", tuple(ids))}


def is_with(conn: sqlite3.Connection, actor_id: int, other_id: int) -> bool:
    """Whether `other_id` is with the protagonist `actor_id`; False for anyone who is not the protagonist."""
    me = _me(conn)
    return me is not None and int(me["id"]) == int(actor_id) and int(other_id) in with_player(conn)


def in_earshot(conn: sqlite3.Connection, actor_id: int, other_id: int) -> bool:
    """Whether the protagonist can speak to this person where they stand: with them, of this place today, or plausibly
    about it."""
    me = _me(conn)
    if me is None or int(me["id"]) != int(actor_id) or me["current_location_id"] is None:
        return False
    here, other = int(me["current_location_id"]), int(other_id)
    if other in with_player(conn):
        return True
    row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (other,)).fetchone()
    if row and row[0] == here and not _location_is_large(conn, here) and _active_travel(conn, other) is None:
        return True
    return actor_is_present_candidate(conn, other, here, purpose=f"scene:{int(me['id'])}")
