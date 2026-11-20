"""Organisation lifecycle (sphere-free): who takes a vacant unit, and what is noted for the GM's history.

This file holds `fill_unit_leader` and `mark_for_history`; the weekly lifecycle process (deaths, held men, leaving the
life, levels) is added here later. Roles and labels come from the package's orgs.json (`orgs.kind_rules`).
"""
from __future__ import annotations

import json
import sqlite3

from . import orgs

_DAYS_PER_YEAR = 365.0
RISE_REASON = "rose to lead a unit"  # the history note `fill_unit_leader` leaves; readers use its day as the day the seat was filled


def mark_for_history(conn: sqlite3.Connection, actor_id: int, reason: str, day: int | None = None) -> None:
    """Flag every seat he holds as owing the GM a history and record why, as an agenda row of kind `history` (an item
    that needs no action from the man himself)."""
    d = orgs._today(conn) if day is None else int(day)
    conn.execute("UPDATE org_seats SET history_due=1 WHERE actor_id=?", (int(actor_id),))
    conn.execute(
        """INSERT INTO org_agenda(actor_id,kind,due_day,subject_kind,subject_id,created_day,metadata_json) VALUES (?,?,?,?,?,?,?)""",
        (int(actor_id), "history", d, "actor", int(actor_id), d, json.dumps({"reason": str(reason)}, sort_keys=True)))


def _head_loyalty(conn: sqlite3.Connection, actor_id: int, head: int | None) -> float:
    """His loyalty to the head, 0..1: the relationship's loyalty where there is one, else his own drive."""
    if head is not None:
        r = conn.execute("SELECT loyalty FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(actor_id), int(head))).fetchone()
        if r is not None:
            return max(0.0, min(1.0, float(r[0]) / 100.0))
    d = conn.execute("SELECT loyalty FROM actor_drives WHERE actor_id=?", (int(actor_id),)).fetchone()
    return float(d[0]) if d is not None else 0.5


def fill_unit_leader(conn: sqlite3.Connection, unit_id: int, day: int) -> int | None:
    """Give a unit whose leader is gone a new one. The unit member with the best standing, years inducted and loyalty to
    the head (inducted members first; any member when no one is inducted) takes the unit-leader role, under the old
    leader's superior; the men who answered to the old leader now answer to him; the lines the old leader held and the
    unit's lines stay with the unit under him. Returns the new leader's actor id; None when the unit's leader is alive,
    the kind has no unit leaders, or there is no one to take the place."""
    unit = conn.execute("SELECT * FROM org_units WHERE id=?", (int(unit_id),)).fetchone()
    if unit is None:
        return None
    org = int(unit["org_actor_id"])
    role = orgs.kind_rules(conn, org).get("unit_leader")
    old = unit["leader_actor_id"]
    if not role:
        return None
    if old is not None and orgs.is_living(conn, int(old)):
        seat = orgs.seat_of(conn, int(old), org)
        if seat is not None and seat["status"] == "active":
            return None
    old_seat = orgs.seat_of(conn, int(old), org) if old is not None else None
    head = orgs.head_of(conn, org)
    members = [r for r in orgs.members(conn, org) if r["unit_id"] == int(unit_id) and r["role_key"] != role
               and (old is None or int(r["actor_id"]) != int(old)) and orgs.is_living(conn, int(r["actor_id"]))]
    pool = [r for r in members if r["inducted_day"] is not None] or members
    if not pool:
        return None

    def years(r) -> float:
        return 0.0 if r["inducted_day"] is None else max(0.0, (int(day) - int(r["inducted_day"])) / _DAYS_PER_YEAR)

    top = max((years(r) for r in pool), default=0.0) or 1.0
    best = max(pool, key=lambda r: (float(r["standing"]) + years(r) / top + _head_loyalty(conn, int(r["actor_id"]), head), -int(r["actor_id"])))
    new = int(best["actor_id"])
    superior = old_seat["superior_actor_id"] if old_seat is not None else head
    level = int(old_seat["level"]) if old_seat is not None else int(best["level"])
    conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=? WHERE actor_id=? AND org_actor_id=?", (role, superior, new, org))
    if old is not None:
        conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND superior_actor_id=? AND actor_id<>?",
                     (new, org, int(old), new))
        conn.execute("UPDATE org_lines SET holder_actor_id=? WHERE holder_actor_id=? AND unit_id=? AND status='active'", (new, int(old), int(unit_id)))
    conn.execute("UPDATE org_units SET leader_actor_id=? WHERE id=?", (new, int(unit_id)))
    label = (orgs.kind_rules(conn, org).get("labels") or {}).get(role, role)
    name = conn.execute("SELECT name FROM actors WHERE id=?", (org,)).fetchone()[0]
    conn.execute("UPDATE institution_memberships SET role_text=? WHERE institution_actor_id=? AND member_actor_id=? AND membership_kind='member'",
                 (f"{label} in the {name}", org, new))
    orgs.set_level(conn, new, level, int(day), org)
    orgs.imposed(conn, new)  # he and the men who now answer to him are looked at again tomorrow
    for (sub,) in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND superior_actor_id=? AND status='active' AND actor_id<>?",
                               (org, new, new)).fetchall():
        orgs.imposed(conn, int(sub))
    mark_for_history(conn, new, RISE_REASON, int(day))
    return new
