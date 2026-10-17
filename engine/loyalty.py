"""Gap 4b: loyalty moves, and unpaid or mistreated people leave, defect, inform or steal.

Monthly drift (outfit crews and named people, servants): down with arrears (-4 to -8 a month) and with harm done to them by their own
head, up slowly (+1 to +2, toward 60) when paid and untroubled. Consequences are rare and thresholded, each recorded with an event.
Named people carry loyalty in underworld_personnel.metadata_json; crews and service terms already have columns.
"""
from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

DEFAULT_LOYALTY = 55.0
TARGET = 60.0


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def drift(months_behind: int, mistreated: int, value: float) -> float:
    """One month's change."""
    if months_behind > 0:
        return -(4.0 + min(4.0, float(months_behind)))
    if mistreated > 0:
        return -3.0 * min(2, mistreated)
    if value < TARGET:
        return min(2.0, 1.0 + (TARGET - value) / 40.0)
    return 0.0


def personnel_loyalty(row: sqlite3.Row) -> float:
    try:
        v = json.loads(row["metadata_json"] or "{}").get("loyalty")
    except Exception:
        v = None
    return DEFAULT_LOYALTY if v is None else float(v)


def mistreated_count(conn: sqlite3.Connection, oid: int, day: int, window: int = 60) -> int:
    """Harm done to the outfit's own people by their own head or outfit in the recent past."""
    return int(conn.execute(
        """SELECT COUNT(*) FROM harm_incidents h WHERE h.day>? AND h.actor_id IN
           (SELECT actor_id FROM underworld_personnel WHERE organization_id=? AND status='active')
           AND (h.source_kind='player_operation' OR json_extract(h.metadata_json,'$.source_organization_id')=?)""", (day - window, oid, oid)).fetchone()[0])


def _event(conn: sqlite3.Connection, day: int, kind: str, title: str, summary: str, loc: int | None, actor: int | None = None, rumorability: float | None = None) -> None:
    from .simulation import SimEvent, log_event
    log_event(conn, SimEvent(day=day, event_type=kind, title=title, summary=summary, severity=2, source_actor_id=actor, location_id=loc, rumorability=rumorability))


def _name(conn: sqlite3.Connection, actor_id: int) -> str:
    return str(conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()[0])


def outfit_morale(conn: sqlite3.Connection, oid: int, months_behind: int, day: int | None = None, rng: random.Random | None = None) -> dict[str, Any]:
    """Monthly drift for an outfit's crews and named people, then the rare consequences."""
    from .relationships import adjust_relationship
    day = _day(conn) if day is None else day
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    if not org or str(org["status"]) not in ("active", "strained", "fragmented"):
        return {}
    rng = rng or random.Random(int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0]) * 31 + oid * 977 + day)
    mist = mistreated_count(conn, oid, day)
    leader = org["current_leader_actor_id"]
    out = {"left": 0, "defected": 0, "informed": 0, "stole": 0}
    for c in conn.execute("SELECT * FROM underworld_crews WHERE organization_id=? AND status='active'", (oid,)).fetchall():
        d = drift(months_behind, mist, float(c["loyalty"]))
        dc = d * .8 if d < 0 else d * .7
        conn.execute("UPDATE underworld_crews SET loyalty=?,cohesion=? WHERE id=?", (_clamp(float(c["loyalty"]) + d), _clamp(float(c["cohesion"]) + dc), int(c["id"])))
    people = conn.execute(
        """SELECT p.* FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id WHERE p.organization_id=? AND p.status='active' AND a.status='active'
           AND p.role_kind<>'boss' AND p.actor_id<>COALESCE(?,-1) ORDER BY p.actor_id""", (oid, leader)).fetchall()
    for p in people:
        meta = json.loads(p["metadata_json"] or "{}")
        cur = personnel_loyalty(p)
        new = _clamp(cur + drift(months_behind, mist, cur))
        meta["loyalty"] = round(new, 2)
        if new < 25:
            meta.setdefault("low_since", day)
        else:
            meta.pop("low_since", None)
        conn.execute("UPDATE underworld_personnel SET metadata_json=? WHERE actor_id=?", (json.dumps(meta, sort_keys=True), int(p["actor_id"])))
        if leader is not None and new != cur:
            adjust_relationship(conn, int(p["actor_id"]), int(leader), day, loyalty_delta=(new - cur) * .5)
    loc = int(org["primary_location_id"]) if org["primary_location_id"] is not None else None
    # ---- consequences, each rare ----
    people = conn.execute(
        """SELECT p.* FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id WHERE p.organization_id=? AND p.status='active' AND a.status='active'
           AND p.role_kind<>'boss' AND p.actor_id<>COALESCE(?,-1) ORDER BY p.actor_id""", (oid, leader)).fetchall()
    rival = _rival_in_city(conn, oid, loc)
    defected_once = False
    for p in people:
        meta = json.loads(p["metadata_json"] or "{}")
        lo = float(meta.get("loyalty", DEFAULT_LOYALTY))
        aid = int(p["actor_id"])
        if lo < 20 and rival is not None and not defected_once and rng.random() < .40:
            defect(conn, aid, oid, rival, day)
            out["defected"] += 1; defected_once = True
            continue
        low_since = meta.get("low_since")
        if lo < 25 and low_since is not None and day - int(low_since) >= 60 and rng.random() < .35:
            desert(conn, aid, oid, day, loc)
            out["left"] += 1
            continue
        if lo < 30 and rng.random() < .12:
            inform(conn, aid, oid, day, loc)
            out["informed"] += 1
        if lo < 35 and str(p["role_kind"]) == "accountant" and rng.random() < .30:
            if skim(conn, aid, oid, day, loc):
                out["stole"] += 1
    # a whole crew that has turned against its outfit may go over with its men
    if rival is not None and not defected_once:
        for c in conn.execute("SELECT * FROM underworld_crews WHERE organization_id=? AND status='active' AND loyalty<20 ORDER BY loyalty,id LIMIT 1", (oid,)).fetchall():
            if rng.random() < .35:
                defect_crew(conn, int(c["id"]), oid, rival, day)
                out["defected"] += 1
    return out


def _rival_in_city(conn: sqlite3.Connection, oid: int, loc: int | None) -> int | None:
    if loc is None:
        return None
    r = conn.execute(
        """SELECT o.id FROM underworld_organizations o WHERE o.primary_location_id=? AND o.id<>? AND o.status='active'
           AND json_extract(o.metadata_json,'$.role') IS NOT 'specialist' ORDER BY o.cohesion DESC,o.treasury DESC,o.id LIMIT 1""", (loc, oid)).fetchone()
    return int(r[0]) if r else None


def desert(conn: sqlite3.Connection, aid: int, oid: int, day: int, loc: int | None) -> None:
    """Leaves for ordinary life: occupation follows Stage, and a former member is never labelled criminal."""
    from .person_ecology import make_former_member_ordinary
    conn.execute("UPDATE underworld_personnel SET status='retired',crew_id=NULL WHERE actor_id=?", (aid,))
    make_former_member_ordinary(conn, aid)
    _event(conn, day, "underworld_desertion", f"{_name(conn, aid)} walked away", f"{_name(conn, aid)} left {_org(conn, oid)} and went back to ordinary life.", loc, aid, .4)


def _org(conn: sqlite3.Connection, oid: int) -> str:
    return str(conn.execute("SELECT name FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0])


def defect(conn: sqlite3.Connection, aid: int, oid: int, rival: int, day: int) -> None:
    from .underworld_rebuild import change_relation
    from .underworld import record_underworld_membership_flow
    conn.execute("UPDATE underworld_personnel SET organization_id=?,crew_id=NULL,role_kind=CASE WHEN role_kind IN ('underboss','lieutenant','crew_leader') THEN 'member' ELSE role_kind END,"
                 "metadata_json=json_set(COALESCE(metadata_json,'{}'),'$.loyalty',55) WHERE actor_id=?", (rival, aid))
    conn.execute("UPDATE underworld_personnel SET metadata_json=json_remove(metadata_json,'$.low_since') WHERE actor_id=?", (aid,))
    record_underworld_membership_flow(conn, oid, "defection", 1, from_tier="active", metadata={"to_organization_id": rival, "actor_id": aid})
    record_underworld_membership_flow(conn, rival, "recruitment", 1, to_tier="active", metadata={"from_organization_id": oid, "actor_id": aid})
    _incident(conn, rival, oid, day, {"actor_id": aid})
    change_relation(conn, rival, oid, kind="rival", hostility_delta=10)
    loc = conn.execute("SELECT primary_location_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0]
    _event(conn, day, "underworld_defection", f"{_name(conn, aid)} went over to {_org(conn, rival)}",
           f"{_name(conn, aid)} left {_org(conn, oid)} for {_org(conn, rival)}, and the old outfit knows it.", loc, aid, .5)


def defect_crew(conn: sqlite3.Connection, crew_id: int, oid: int, rival: int, day: int) -> None:
    from .underworld_rebuild import change_relation
    from .underworld import record_underworld_membership_flow
    c = conn.execute("SELECT * FROM underworld_crews WHERE id=?", (crew_id,)).fetchone()
    name = str(c["name"])
    if conn.execute("SELECT 1 FROM underworld_crews WHERE organization_id=? AND name=?", (rival, name)).fetchone():
        name = f"{name} (from {_org(conn, oid)})"
    conn.execute("UPDATE underworld_crews SET organization_id=?,name=?,home_zone_id=NULL,loyalty=55,cohesion=MAX(cohesion,50) WHERE id=?", (rival, name, crew_id))
    conn.execute("UPDATE underworld_personnel SET organization_id=? WHERE crew_id=? AND status='active'", (rival, crew_id))
    n = float(c["size_estimate"])
    record_underworld_membership_flow(conn, oid, "defection", n, from_tier="active", metadata={"to_organization_id": rival, "crew_id": crew_id})
    record_underworld_membership_flow(conn, rival, "recruitment", n, to_tier="active", metadata={"from_organization_id": oid, "crew_id": crew_id})
    _incident(conn, rival, oid, day, {"crew_id": crew_id})
    change_relation(conn, rival, oid, kind="rival", hostility_delta=14)
    loc = conn.execute("SELECT primary_location_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0]
    _event(conn, day, "underworld_defection", f"A crew left {_org(conn, oid)} for {_org(conn, rival)}",
           f"The {name} crew walked out on {_org(conn, oid)} and took service with {_org(conn, rival)}.", loc, None, .6)


def _incident(conn: sqlite3.Connection, source: int, target: int, day: int, meta: dict[str, Any]) -> None:
    conn.execute("""INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
                    VALUES (?,NULL,?,?,'defection',45,'open',?)""", (day, source, target, json.dumps(meta, sort_keys=True)))


def inform(conn: sqlite3.Connection, aid: int, oid: int, day: int, loc: int | None) -> None:
    from .underworld_rebuild import add_heat
    add_heat(conn, oid, public=2, investigative=7)
    _event(conn, day, "underworld_informant", "Word of an outfit's business reached the watch",
           f"Someone close to {_org(conn, oid)} has been talking to the watch.", loc, None, .6)


def skim(conn: sqlite3.Connection, aid: int, oid: int, day: int, loc: int | None) -> bool:
    from . import ledger
    tr = float(conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0])
    amt = round(min(tr * .15, 3.0), 3)
    if amt < .05:
        return False
    ledger.transfer(conn, ("outfit", oid), ("person", aid), amt, flow_kind="other", purpose="skimmed")
    _event(conn, day, "underworld_theft", f"{_org(conn, oid)}'s books do not add up",
           f"Money has gone missing from {_org(conn, oid)}, and its keeper of accounts is the likeliest hand.", loc, aid, .5)
    return True


# -- households ---------------------------------------------------------------------------------------------------

def household_morale(conn: sqlite3.Connection, hid: int, months_behind: int, day: int | None = None, rng: random.Random | None = None) -> int:
    """Servants and stewards: satisfaction and loyalty follow pay and treatment; a badly paid or unhappy one may leave mid-term."""
    from .household_life import _record_life_event
    day = _day(conn) if day is None else day
    rng = rng or random.Random(int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0]) * 17 + hid * 613 + day)
    left = 0
    for t in conn.execute("SELECT * FROM household_service_terms WHERE household_id=? AND status='active' ORDER BY id", (hid,)).fetchall():
        harmed = int(conn.execute("SELECT COUNT(*) FROM harm_incidents WHERE actor_id=? AND day>? AND source_kind='player_operation'", (int(t["actor_id"]), day - 60)).fetchone()[0])
        ds = drift(months_behind, harmed, float(t["satisfaction"]))
        dl = ds * .6 if ds < 0 else ds * .5
        sat, loy = _clamp(float(t["satisfaction"]) + ds), _clamp(float(t["loyalty"]) + dl)
        conn.execute("UPDATE household_service_terms SET satisfaction=?,loyalty=? WHERE id=?", (sat, loy, int(t["id"])))
        if sat < 25 or months_behind >= 2:
            # a steward whose loyalty holds stays longer than a servant whose does not
            p = .45 if loy < 40 else .15
            if (sat < 25 or months_behind >= 3) and rng.random() < p:
                conn.execute("UPDATE household_service_terms SET status='former',end_day=? WHERE id=?", (day, int(t["id"])))
                conn.execute("UPDATE household_members SET status='former',left_day=? WHERE household_id=? AND actor_id=? AND role=? AND status='active'",
                             (day, hid, int(t["actor_id"]), t["service_role"]))
                _record_life_event(conn, "service_change", f"{_name(conn, int(t['actor_id']))} left service in household #{hid}: unpaid or ill used.",
                                   actor_id=int(t["actor_id"]), household_id=hid, day=day)
                hh = conn.execute("SELECT name,location_id FROM households WHERE id=?", (hid,)).fetchone()
                _event(conn, day, "household_service_quit", f"{_name(conn, int(t['actor_id']))} left {hh['name']}",
                       f"{_name(conn, int(t['actor_id']))} walked out of service at {hh['name']}.", hh["location_id"], int(t["actor_id"]), .4)
                left += 1
    return left


def business_morale(conn: sqlite3.Connection, eid: int, months_behind: int) -> None:
    """Two or more months of unpaid staff cost a business its capacity and standing."""
    if months_behind >= 2:
        conn.execute("UPDATE civilian_enterprises SET labor_capacity=MAX(0,labor_capacity-3),reputation=MAX(0,reputation-1) WHERE id=?", (eid,))
        conn.execute("UPDATE enterprise_business_profiles SET capacity=MAX(1,capacity-2) WHERE enterprise_id=?", (eid,))


# -- words for the table (never numbers) ---------------------------------------------------------------------------

def outfit_mood(conn: sqlite3.Connection, oid: int) -> str:
    from .payroll import get_arrears
    a = get_arrears(conn, "outfit", oid)
    crews = conn.execute("SELECT AVG(loyalty) FROM underworld_crews WHERE organization_id=? AND status='active'", (oid,)).fetchone()[0]
    parts = []
    if a["months"] >= 1:
        parts.append("the crews are a month behind on pay" if a["months"] == 1 else f"the crews are {_nword(a['months'])} months behind on pay")
    if crews is not None and float(crews) < 35:
        parts.append("the crews are close to walking")
    elif crews is not None and float(crews) < 50:
        parts.append("the crews are grumbling")
    return "; ".join(parts)


def _nword(n: int) -> str:
    return {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}.get(n, "many")
