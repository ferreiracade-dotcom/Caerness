"""The weekly B tick for held things: owner, money, heat, happenings, dates (generic layer; every figure from the package's intake data).

A held thing lives at B depth: it has an owner and a purse behind it, and it earns, costs, draws notice, grows, shrinks, passes
on when its owner dies, and ends with a reason. Nothing here caps anything: arrears are counted, growth and shrinkage are shares.
"""
from __future__ import annotations

import json
import random
import sqlite3

from . import findings, ledger, orgs, org_heat
from .org_succession import v

WEEK = 7
LIVE = ("active", "failing")


def _rules(conn) -> dict:
    from .world_package import intake_rules, package_for
    return intake_rules(package_for(conn))


def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    if not _rules(conn):
        return None
    if not conn.execute("SELECT 1 FROM held_things WHERE status IN ('active','failing') LIMIT 1").fetchone():
        return None
    due = (int(after_day) // WEEK + 1) * WEEK
    return due if due <= int(end_day) else None


def _living(conn, actor_id) -> bool:
    from .player_operations import _living
    return _living(conn, actor_id)


def _end(conn, row, day: int, reason: str) -> None:
    conn.execute("UPDATE held_things SET status='ended',ended_reason=?,updated_day=? WHERE id=?", (reason, day, row["id"]))
    if row["owner_actor_id"] is not None and _living(conn, row["owner_actor_id"]):
        findings.tell(conn, int(row["owner_actor_id"]), [f"{row['name']} is over: {reason}"], source=int(row["owner_actor_id"]))


def _new_owner(conn, row) -> int | None:
    """The next living person among its people, then the head of the dead owner's organisation."""
    for pid in json.loads(row["people_json"]):
        if int(pid) != row["owner_actor_id"] and _living(conn, pid):
            return int(pid)
    if row["owner_actor_id"] is not None:
        for s in orgs.seats_of(conn, int(row["owner_actor_id"])):
            if s["status"] != "active":
                continue
            h = orgs.head_of(conn, int(s["org_actor_id"]))
            if h is not None and h != row["owner_actor_id"] and _living(conn, h):
                return int(h)
    return None


def _owner_orgs(conn, owner: int) -> list[int]:
    return [int(s["org_actor_id"]) for s in orgs.seats_of(conn, owner) if s["status"] == "active"]


def _heat(conn, row, owner: int, day: int, tick: dict) -> None:
    if row["legality"] != "illegal":
        return
    for org in _owner_orgs(conn, owner):
        org_heat.add(conn, org, day, investigative=v(conn, tick["illegal_weekly_investigative_heat"]))


def _pay(conn, row, owner: int, day: int) -> tuple[bool, float]:
    """Takings in, upkeep out. Returns (upkeep fully paid, income received)."""
    holder = ("person", owner)
    income = float(row["income_weekly"])
    upkeep = float(row["upkeep_weekly"])
    if income > 0:
        ledger.receive(conn, holder, income, purpose=f"{row['name']}: takings")
    if upkeep <= 0:
        return True, income
    return ledger.spend(conn, holder, upkeep, purpose=f"{row['name']}: upkeep", allow_partial=True) >= upkeep - 1e-9, income


def _log(conn, event_logger, row, owner: int, day: int, title: str, summary: str) -> None:
    if event_logger is not None:
        event_logger(day=day, event_type="held_thing", title=title, summary=summary, severity=1, source_actor_id=owner,
                     target_actor_ids=(owner,), location_id=row["location_id"], visibility="limited", rumorability=.10, reliability=.95)
        return
    from .player import get_player
    p = get_player(conn)
    if p is not None and int(p["player_actor_id"]) == owner:
        from .player_operations import _record
        _record(conn, owner, title, summary)


def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict:
    rules = _rules(conn)
    out = {"paid": 0, "failing": 0, "ended": 0, "passed_on": 0, "happenings": 0}
    if not rules:
        return out
    tick = rules["tick"]
    day = int(day)
    for row in conn.execute("SELECT * FROM held_things WHERE status IN ('active','failing') ORDER BY id").fetchall():
        owner = row["owner_actor_id"]
        if owner is None or not _living(conn, owner):
            nxt = _new_owner(conn, row)
            if nxt is None:
                _end(conn, row, day, "its owner died and no one took it up")
                out["ended"] += 1
                continue
            conn.execute("UPDATE held_things SET owner_actor_id=?,updated_day=? WHERE id=?", (nxt, day, row["id"]))
            row = conn.execute("SELECT * FROM held_things WHERE id=?", (row["id"],)).fetchone()
            owner = nxt
            out["passed_on"] += 1
        owner = int(owner)
        if row["end_day"] is not None and day >= int(row["end_day"]):
            _end(conn, row, day, "its time ran out")
            out["ended"] += 1
            continue
        if row["recurrence_days"]:  # a custom acts on its own day: its readers (money, heat) act then, once
            if day - int(row["updated_day"]) < int(row["recurrence_days"]):
                continue
            conn.execute("UPDATE held_things SET updated_day=? WHERE id=?", (day, row["id"]))
        paid, _income = _pay(conn, row, owner, day)
        arrears = 0 if paid else int(row["arrears_weeks"]) + 1
        if paid:
            out["paid"] += 1
        else:
            out["failing"] += 1
        if arrears >= int(v(conn, tick["arrears_weeks_to_fail"])):
            conn.execute("UPDATE held_things SET arrears_weeks=?,updated_day=? WHERE id=?", (arrears, day, row["id"]))
            _end(conn, row, day, "it could not pay its way")
            out["ended"] += 1
            continue
        conn.execute("UPDATE held_things SET arrears_weeks=?,status=?,updated_day=? WHERE id=?",
                     (arrears, "active" if paid else "failing", day, row["id"]))
        _heat(conn, row, owner, day, tick)
        rng = random.Random(f"held:{row['id']}:{day}")
        if rng.random() < v(conn, tick["happening_week_rate"]):
            which = rng.randrange(3)
            if which == 0:
                conn.execute("UPDATE held_things SET income_weekly=income_weekly*(1+?) WHERE id=?", (v(conn, tick["grow_share"]), row["id"]))
                title, summary = f"{row['name']} grew", f"{row['name']} is bringing in more."
            elif which == 1:
                conn.execute("UPDATE held_things SET income_weekly=income_weekly*(1-?) WHERE id=?", (v(conn, tick["shrink_share"]), row["id"]))
                title, summary = f"{row['name']} shrank", f"{row['name']} is bringing in less."
            else:
                findings.tell(conn, owner, [f"{row['name']} drew notice"], source=owner)
                _heat(conn, row, owner, day, tick)
                title, summary = f"{row['name']} drew notice", f"{row['name']} was noticed by people it would rather not have been."
            out["happenings"] += 1
            _log(conn, event_logger, row, owner, day, title, summary)
    return out
