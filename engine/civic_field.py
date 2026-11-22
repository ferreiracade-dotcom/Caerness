"""The field's actors and what each holds (politics P1).

Every actor (an organisation or a person) holds stakes: party posts, an office's patronage, a seat in an appointment chain, a voter
group's delivery, a bundle of favours. A stake is a row in `field_holdings`; it can be transferred, weakened or ended, and nothing
here knows who holds what: the package's `holdings_1975` data gives the opening and every later move comes from drivers. The
Machine is one organisation among the field's actors with no code of its own.
"""
from __future__ import annotations

import json
import re
import sqlite3

from . import offices, orgs
from .design import figure
from .world_package import package_for, politics_rules


def _rules(conn) -> dict:
    return politics_rules(package_for(conn))


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


# ---- reading ----------------------------------------------------------------------------------------------------

def holdings_of(conn, holder_kind: str, holder_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM field_holdings WHERE holder_kind=? AND holder_id=? AND ended_day IS NULL ORDER BY id",
                        (holder_kind, int(holder_id))).fetchall()


def holder_of(conn, stake_kind: str, stake_ref: str) -> tuple[str, int] | None:
    """The strongest active holder of a stake (a post has one; a voter group may be reached by several)."""
    r = conn.execute("SELECT holder_kind,holder_id FROM field_holdings WHERE stake_kind=? AND stake_ref=? AND ended_day IS NULL "
                     "ORDER BY strength DESC,id LIMIT 1", (stake_kind, str(stake_ref))).fetchone()
    return (str(r[0]), int(r[1])) if r else None


def holders_of(conn, stake_kind: str, stake_ref: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM field_holdings WHERE stake_kind=? AND stake_ref=? AND ended_day IS NULL ORDER BY strength DESC,id",
                        (stake_kind, str(stake_ref))).fetchall()


def strength(conn, holder_kind: str, holder_id: int) -> float:
    """The sum of the holder's active stakes over the package's scale."""
    total = conn.execute("SELECT COALESCE(SUM(strength),0) FROM field_holdings WHERE holder_kind=? AND holder_id=? AND ended_day IS NULL",
                         (holder_kind, int(holder_id))).fetchone()[0]
    return float(total) / float(figure(conn, "field_strength_scale", 10.0))


# ---- moving stakes ----------------------------------------------------------------------------------------------

def _filler(conn, org_id: int, stake_ref: str) -> int | None:
    """Who in an organisation fills a party post: its head for a chairmanship, a unit leader for the n-th district, else its head."""
    m = re.search(r"-(\d+)$", stake_ref)
    if m:
        leaders = [int(r[0]) for r in conn.execute("SELECT leader_actor_id FROM org_units WHERE org_actor_id=? AND leader_actor_id IS NOT NULL ORDER BY id", (int(org_id),))]
        if leaders:
            return leaders[(int(m.group(1)) - 1) % len(leaders)]
    return orgs.head_of(conn, int(org_id))


def _seat_post(conn, holder_kind: str, holder_id: int, stake_ref: str, day: int) -> None:
    if not conn.execute("SELECT 1 FROM offices WHERE office_key=? AND filled_by='org'", (stake_ref,)).fetchone():
        return
    who = int(holder_id) if holder_kind == "actor" else _filler(conn, int(holder_id), stake_ref)
    if who is not None and offices.holder(conn, stake_ref) != who:
        offices.seat_holder(conn, stake_ref, who, how="succeeded", day=day)


def _open(conn, holder_kind, holder_id, stake_kind, stake_ref, strength_, day, cause_kind=None, cause_id=None) -> int:
    sid = int(conn.execute("INSERT INTO field_holdings(holder_kind,holder_id,stake_kind,stake_ref,strength,since_day,cause_kind,cause_id) VALUES (?,?,?,?,?,?,?,?)",
                           (holder_kind, int(holder_id), stake_kind, str(stake_ref), float(strength_), int(day), cause_kind, cause_id)).lastrowid)
    if stake_kind == "party_office":
        _seat_post(conn, holder_kind, holder_id, str(stake_ref), day)
    return sid


def transfer(conn, stake_id: int, to_kind: str, to_id: int, *, day: int, cause_kind: str, cause_id: int | None = None) -> int:
    """End the old holder's row and start the new holder's with the cause recorded; returns the new row."""
    s = conn.execute("SELECT * FROM field_holdings WHERE id=? AND ended_day IS NULL", (int(stake_id),)).fetchone()
    if s is None:
        raise ValueError(f"stake {stake_id} is not active")
    conn.execute("UPDATE field_holdings SET ended_day=?,cause_kind=?,cause_id=? WHERE id=?", (int(day), cause_kind, cause_id, int(stake_id)))
    return _open(conn, to_kind, int(to_id), s["stake_kind"], s["stake_ref"], float(s["strength"]), day, cause_kind, cause_id)


def weaken(conn, stake_id: int, delta: float, *, day: int, cause_kind: str, cause_id: int | None = None) -> None:
    """Take `delta` off a stake's strength; at zero the stake ends (it is not held by nobody, it is simply gone)."""
    s = conn.execute("SELECT * FROM field_holdings WHERE id=? AND ended_day IS NULL", (int(stake_id),)).fetchone()
    if s is None:
        return
    left = float(s["strength"]) - float(delta)
    if left <= 0.0:
        conn.execute("UPDATE field_holdings SET strength=0,ended_day=?,cause_kind=?,cause_id=? WHERE id=?", (int(day), cause_kind, cause_id, int(stake_id)))
    else:
        conn.execute("UPDATE field_holdings SET strength=?,cause_kind=?,cause_id=? WHERE id=?", (left, cause_kind, cause_id, int(stake_id)))


# ---- the opening ------------------------------------------------------------------------------------------------

def _resolve(conn, holder: dict) -> int | None:
    if "org" in holder:
        r = conn.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (holder["org"],)).fetchone()
        return int(r[0]) if r else None
    if "institution" in holder:
        r = conn.execute("SELECT id FROM actors WHERE name=? AND actor_type='institution'", (holder["institution"],)).fetchone()
        return int(r[0]) if r else None
    return None


def _district_no(group_key: str) -> int | None:
    m = re.match(r"[a-z]+-(\d+)", group_key or "")
    return int(m.group(1)) if m else None


def seed_field(conn, day: int | None = None) -> dict:
    """Give every holder its 1975 stakes from the package data (idempotent: a stake already held by that holder is skipped).
    Delivery stakes name districts by number and are expanded over the voter groups that exist (see `seed_delivery`)."""
    day = _day(conn) if day is None else int(day)
    out = {"stakes": 0, "unresolved": 0}
    for h in _rules(conn).get("holdings_1975") or []:
        hid = _resolve(conn, h["holder"])
        if hid is None:
            out["unresolved"] += 1
            continue
        if h["stake_kind"] == "delivery":
            continue
        if conn.execute("SELECT 1 FROM field_holdings WHERE holder_kind='org' AND holder_id=? AND stake_kind=? AND stake_ref=? AND ended_day IS NULL",
                        (hid, h["stake_kind"], h["stake_ref"])).fetchone():
            continue
        _open(conn, "org", hid, h["stake_kind"], h["stake_ref"], float(h.get("strength", 1.0)), day, "opening")
        out["stakes"] += 1
    out["stakes"] += seed_delivery(conn, day)
    return out


def seed_delivery(conn, day: int | None = None) -> int:
    """Delivery stakes over the voter groups of the named districts (run again when the groups exist)."""
    day = _day(conn) if day is None else int(day)
    groups = conn.execute("SELECT group_key FROM voter_groups ORDER BY id").fetchall()
    n = 0
    for h in _rules(conn).get("holdings_1975") or []:
        if h["stake_kind"] != "delivery":
            continue
        hid = _resolve(conn, h["holder"])
        if hid is None:
            continue
        for g in groups:
            if _district_no(g[0]) in set(h.get("districts") or []):
                if conn.execute("SELECT 1 FROM field_holdings WHERE holder_kind='org' AND holder_id=? AND stake_kind='delivery' AND stake_ref=? AND ended_day IS NULL",
                                (hid, g[0])).fetchone():
                    continue
                _open(conn, "org", hid, "delivery", g[0], float(h.get("strength", 1.0)), day, "opening")
                n += 1
    return n
