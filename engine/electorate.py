"""Voter groups as audiences, and what a group does at an election (politics P1).

A voter group is a named block of the electorate: a district, some words (descent, class, religion), a size and a base turnout.
It is an information-1b audience under the package's `voter_group` rule, so what the voters think of a person is a regard held by
the audience, not a number of this module's own. Turnout and delivery are driven by figures: a group votes more when a race names
what it is angry about, when someone is working to bring it out, and less on a bitter day; a delivery stake is worth what the
holder can still give (its jobs), never a fixed count.
"""
from __future__ import annotations

import json
import math
import re

from . import civic_field, civic_seams, claims, offices
from .design import figure
from .world_package import package_for, politics_rules


def _rules(conn) -> dict:
    return politics_rules(package_for(conn))


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


# ---- the groups ---------------------------------------------------------------------------------------------------

def seed_groups(conn) -> int:
    """Insert the package's voter groups (idempotent), give each its audience, and expand delivery stakes over them."""
    spec = _rules(conn).get("voter_groups") or {}
    n = 0
    for g in spec.get("groups") or []:
        if conn.execute("SELECT 1 FROM voter_groups WHERE group_key=?", (g["key"],)).fetchone():
            continue
        loc = conn.execute("SELECT id FROM locations WHERE name=?", (g.get("district"),)).fetchone()
        gid = int(conn.execute(
            "INSERT INTO voter_groups(group_key,district_ref,location_id,words_json,size,turnout_base,grievances_json) VALUES (?,?,?,?,?,?,?)",
            (g["key"], g.get("district"), int(loc[0]) if loc else None, json.dumps(g.get("words") or {}, sort_keys=True), int(g["size"]),
             float(g.get("turnout_base", 0.5)), json.dumps(list(g.get("grievances") or [])))).lastrowid)
        a = civic_seams.group_audience(conn, gid)
        conn.execute("UPDATE voter_groups SET audience_id=? WHERE id=?", (a["id"], gid))
        n += 1
    civic_field.seed_delivery(conn)
    return n


def groups(conn) -> list:
    return conn.execute("SELECT * FROM voter_groups ORDER BY id").fetchall()


def group(conn, group_id: int):
    return conn.execute("SELECT * FROM voter_groups WHERE id=?", (int(group_id),)).fetchone()


# ---- membership (the audience rule) -------------------------------------------------------------------------------

def _age_ok(words: dict, age: float | None) -> bool:
    w = str(words.get("age") or "")
    if not w:
        return True
    if age is None:
        return False
    m = re.match(r"^(\d+) plus$", w)
    if m:
        return age >= int(m.group(1))
    m = re.match(r"^(\d+) to (\d+)$", w)
    if m:
        return int(m.group(1)) <= age < int(m.group(2)) + 1
    return True


def _is_member(conn, actor: int, aud: dict) -> bool:
    g = group(conn, aud["ref"])
    if g is None or g["location_id"] is None:
        return False
    home = claims._home(conn, int(actor))
    if home is None or not offices._inside(conn, home, int(g["location_id"])):
        return False
    return _age_ok(json.loads(g["words_json"] or "{}"), offices._age(conn, int(actor), _day(conn)))


def _district_groups(conn, office_key: str) -> list:
    o = offices.office(conn, office_key)
    loc = offices._district_location(conn, o, offices.spec(conn, office_key))
    gs = groups(conn)
    if loc is None:
        return gs
    return [g for g in gs if g["location_id"] is not None and offices._inside(conn, int(g["location_id"]), loc)]


def _of_subject(conn, subject: int, key: str, df: dict) -> list[dict]:
    """Groups that hold a view of him: in whose district he stands or serves (a citywide office reaches all) and those whose
    turnout someone's delivery stake names in his hand."""
    ids: dict[int, None] = {}
    keys = set(offices.offices_of(conn, int(subject)))
    for r in conn.execute("SELECT o.office_key FROM race_candidates c JOIN races r ON r.id=c.race_id JOIN offices o ON o.id=r.office_id "
                          "WHERE c.actor_id=? AND c.dropped_day IS NULL AND r.status='open'", (int(subject),)):
        keys.add(str(r[0]))
    for k in keys:
        for g in _district_groups(conn, k):
            ids[int(g["id"])] = None
    for r in conn.execute("SELECT g.id FROM field_holdings h JOIN voter_groups g ON g.group_key=h.stake_ref "
                          "WHERE h.stake_kind='delivery' AND h.holder_kind='actor' AND h.holder_id=? AND h.ended_day IS NULL", (int(subject),)):
        ids[int(r[0])] = None
    return [civic_seams.group_audience(conn, gid) for gid in ids]


claims.register_audience_rule("voter_group", of_subject=_of_subject, is_member=_is_member, members=lambda conn, aud: [])


def regard(conn, group_id: int, subject: int, day: int | None = None) -> float:
    return civic_seams.group_regard(conn, int(group_id), int(subject), _day(conn) if day is None else int(day))


# ---- what a group does --------------------------------------------------------------------------------------------

def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def jobs_held(conn, org_id: int) -> int:
    """The public jobs an organisation can still give: active lines of its units or its people described as the package's job kind."""
    kind = str(_rules(conn).get("patronage_line_kind") or "")
    if not kind:
        return 0
    return int(conn.execute(
        """SELECT COUNT(*) FROM org_lines l WHERE l.status='active' AND l.description LIKE ? AND
           (l.unit_id IN (SELECT id FROM org_units WHERE org_actor_id=?) OR l.holder_actor_id IN
            (SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active'))""", ("%" + kind + "%", int(org_id), int(org_id))).fetchone()[0])


def delivery(conn, group_id: int, holder_kind: str, holder_id: int) -> float:
    """What a holder's stake brings out of one group: the stake's strength, a part of it held by loyalty alone and the rest
    following the jobs the holder can still give."""
    g = group(conn, group_id)
    s = conn.execute("SELECT COALESCE(SUM(strength),0) FROM field_holdings WHERE holder_kind=? AND holder_id=? AND stake_kind='delivery' "
                     "AND stake_ref=? AND ended_day IS NULL", (holder_kind, int(holder_id), g["group_key"])).fetchone()[0]
    base = float(figure(conn, "delivery_base_share", 0.5))
    scale = float(figure(conn, "delivery_line_scale", 20.0))
    jobs = jobs_held(conn, int(holder_id)) if holder_kind == "org" else 0
    return float(s) * (base + (1.0 - base) * jobs / (jobs + scale))


def drive(conn, group_id: int) -> float:
    return sum(delivery(conn, group_id, r["holder_kind"], int(r["holder_id"]))
               for r in civic_field.holders_of(conn, "delivery", group(conn, group_id)["group_key"]))


def _agenda_words(conn, race_id: int) -> set[str]:
    out: set[str] = set()
    for (a,) in conn.execute("SELECT agenda_json FROM race_candidates WHERE race_id=? AND dropped_day IS NULL", (int(race_id),)):
        out.update(str(x) for x in json.loads(a or "[]"))
    return out


def turnout(conn, group_id: int, race_id: int | None = None, day: int | None = None) -> float:
    """The share of the group that votes: its base turnout moved, on the logistic scale, by the grievances the race names that the
    group holds, by the delivery working on it and by winter on election day. No cap: the logistic stays inside zero and one."""
    g = group(conn, group_id)
    day = _day(conn) if day is None else int(day)
    z = _logit(float(g["turnout_base"]))
    if race_id is not None:
        named = _agenda_words(conn, int(race_id))
        z += float(figure(conn, "turnout_w_grievance", 0.35)) * len(named & set(json.loads(g["grievances_json"] or "[]")))
    z += float(figure(conn, "turnout_w_drive", 0.8)) * drive(conn, group_id)
    if offices.date_of(conn, day).month in (12, 1, 2, 3):
        z += float(figure(conn, "turnout_w_winter", -0.15))
    return 1.0 / (1.0 + math.exp(-z))
