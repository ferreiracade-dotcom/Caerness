"""Gap 4b: loyalty, and what unpaid, humiliated or pulled-away people do about it.

Loyalty is a bond first and pay second (owner ruling 2026-10-17). The Hearth is a culture of family, discipleship, face and
obligation running both ways; the other regions of oath, fealty, retainers and honour; commercial regions (Windmere, Sunreach)
bind less. A person's *bond* is made of kin to the head or a crew leader, a sworn / disciple / retainer family, years of
service, shared fights and dead comrades, and the regional culture, with a per-person spread.

Pay in an outfit follows the racket. Rank and file and crews earn from what they work and kick a share up; their grievance is a
falling share (a suppressed racket, lost ground, a boss who takes more or does not share in hard times). Only people on the
stipend (payroll.STIPEND_WEIGHT) can fall into arrears. Bonds damp the commercial grievances; bonded people are moved instead by
what moves the bonded: cruelty from their own head, a humiliation or defeat, dead comrades nobody avenged, a succession dispute,
a stronger branch pulling people away.

The hazard of leaving is smooth (no thresholds): grievance minus bond, arrears and a falling share weighted by how commercial the
person's bond is. Betrayal costs standing: the old head resents the man, the outfit that takes him in does not trust him.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any

HEARTH_BOND = 0.76
REGION_BOND = {"Dunmoor": 0.72, "Stormhollow": 0.55, "Underheaven Empire": 0.55, "Greywood": 0.50, "Thornward": 0.50,
               "Sunreach Confederacy": 0.30, "Windmere": 0.25}
TIE = {"blood_family": 1.0, "sworn_member": 0.8, "member": 0.4, "associate": 0.15, "employee": 0.1}
HOUSE_TIE = {"retainer": 0.8, "steward": 0.7, "guard": 0.5, "apprentice": 0.45, "tutor": 0.4, "clerk": 0.3, "servant": 0.3, "other": 0.3}
HOSTILE_OPS = ("hostile_move", "targeted_hit", "territorial_attack", "challenge_zone", "poach_protection")


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, x))))


# -- culture and bond ------------------------------------------------------------------------------------------------

def _region(conn: sqlite3.Connection, loc: int | None) -> str:
    seen = 0
    while loc is not None and seen < 5:
        r = conn.execute("SELECT name,parent_location_id,political_owner FROM locations WHERE id=?", (loc,)).fetchone()
        if not r:
            break
        if r["political_owner"]:
            return str(r["political_owner"])
        loc, seen = r["parent_location_id"], seen + 1
    return ""


def culture_bond(conn: sqlite3.Connection, loc: int | None) -> float:
    """How much the place's culture binds people to their head: highest in the Hearth and Dunmoor, lowest in commercial Windmere."""
    if loc is None:
        return 0.45
    from .underworld_canon import HEARTH_CITIES
    n = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()
    if n and str(n[0]) in HEARTH_CITIES:
        return HEARTH_BOND
    return REGION_BOND.get(_region(conn, loc), 0.45)


def _spread(actor_id: int, meta: dict[str, Any] | None = None) -> float:
    if meta and meta.get("bond_spread") is not None:
        return float(meta["bond_spread"])
    return ((int(actor_id) * 2654435761) % 1000 / 1000.0 - 0.5) * 0.16


def leave_stress(bond: float, months_behind: float = 0.0, grievance: float = 0.0, pull: float = 0.0, share_drop: float = 0.0) -> float:
    """Grievance weighed against the bond. The commercial side of a person (1 - bond) is moved by pay and a falling share and by a
    richer rival; the bonded side by grievances of honour, harder the stronger the bond."""
    commercial = 1.0 - bond
    return (commercial * (1.0 - math.exp(-max(0.0, months_behind) / 2.0)) + commercial * min(1.0, 2.2 * max(0.0, share_drop))
            + grievance * (0.9 + 0.6 * bond) + 0.6 * pull * commercial)


def leave_hazard(bond: float, months_behind: float = 0.0, grievance: float = 0.0, pull: float = 0.0, share_drop: float = 0.0) -> float:
    """Monthly chance that a person walks away or goes over. Smooth in every input."""
    s = leave_stress(bond, months_behind, grievance, pull, share_drop)
    return 0.30 * _sig((s - 0.45 - 0.45 * bond) / 0.12)


def drift_target(bond: float, stress: float) -> float:
    return (55.0 + 35.0 * bond) * (1.0 - min(1.0, max(0.0, stress)))


# -- an outfit's context ---------------------------------------------------------------------------------------------

def mistreated_count(conn: sqlite3.Connection, oid: int, day: int, window: int = 60) -> int:
    """Harm done to the outfit's own people by their own head in the recent past: the head's own blows (the player's, if he leads it)
    or an order from this outfit. A rival's beating is not the head's mistreatment."""
    from .underworld_aggression import leader_is_player
    own_head_player = leader_is_player(conn, oid)
    return int(conn.execute(
        """SELECT COUNT(*) FROM harm_incidents h WHERE h.day>? AND h.actor_id IN
           (SELECT actor_id FROM underworld_personnel WHERE organization_id=? AND status='active')
           AND ((? AND h.source_kind='player_operation') OR json_extract(h.metadata_json,'$.source_organization_id')=?)""",
        (day - window, oid, 1 if own_head_player else 0, oid)).fetchone()[0])


def household_mistreated(conn: sqlite3.Connection, hid: int, actor_id: int, day: int, window: int = 60) -> int:
    """Blows from the household's own head on a servant: only when the head is the player (else no such harm is recorded)."""
    r = conn.execute("SELECT head_actor_id FROM households WHERE id=?", (hid,)).fetchone()
    p = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    if not r or r[0] is None or not p or p[0] is None or int(r[0]) != int(p[0]):
        return 0
    return int(conn.execute("SELECT COUNT(*) FROM harm_incidents WHERE actor_id=? AND day>? AND source_kind='player_operation'", (actor_id, day - window)).fetchone()[0])


def outfit_context(conn: sqlite3.Connection, oid: int, day: int) -> dict[str, Any]:
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    leader = org["current_leader_actor_id"]
    crews = conn.execute("SELECT * FROM underworld_crews WHERE organization_id=? AND status='active' ORDER BY id", (oid,)).fetchall()
    heads = [int(leader)] if leader is not None else []
    heads += [int(c["leader_actor_id"]) for c in crews if c["leader_actor_id"] is not None]
    kin: set[int] = set()
    if heads:
        marks = ",".join("?" * len(heads))
        kin |= {int(r[0]) for r in conn.execute(f"SELECT actor_b_id FROM kinship_links WHERE actor_a_id IN ({marks}) AND legal_status<>'former'", heads)}
        kin |= {int(r[0]) for r in conn.execute(f"SELECT actor_a_id FROM kinship_links WHERE actor_b_id IN ({marks}) AND legal_status<>'former'", heads)}
    hardship = int(conn.execute("SELECT COUNT(*) FROM underworld_operations WHERE organization_id=? AND day>? AND operation_kind IN (%s)" % ",".join("?" * len(HOSTILE_OPS)),
                                (oid, day - 365, *HOSTILE_OPS)).fetchone()[0])
    hardship += int(conn.execute("SELECT COUNT(*) FROM underworld_incidents WHERE target_organization_id=? AND day>?", (oid, day - 365)).fetchone()[0])
    return {"oid": oid, "org": org, "leader": leader, "crews": crews, "kin": kin, "hardship": hardship,
            "culture": culture_bond(conn, org["primary_location_id"]), "day": day}


def bond_strength(conn: sqlite3.Connection, ctx: dict[str, Any], p: sqlite3.Row, day: int) -> float:
    """0..1: kin to the head or a crew leader, a sworn, disciple or retainer family, years of service, shared fights, the regional culture."""
    try:
        meta = json.loads(p["metadata_json"] or "{}")
    except Exception:
        meta = {}
    aid = int(p["actor_id"])
    tie = TIE.get(str(p["membership_status"]), 0.4)
    if aid in ctx["kin"]:
        tie = 1.0
    if str(p["role_kind"]) in ("underboss", "lieutenant", "crew_leader"):
        tie = min(1.0, tie + 0.1)
    service = 1.0 - math.exp(-max(0.0, day - int(p["inducted_day"])) / 365.0 / 4.0)
    shared = 1.0 - math.exp(-ctx["hardship"] / 3.0)
    return max(0.0, min(1.0, 0.35 * ctx["culture"] + 0.35 * tie + 0.15 * service + 0.10 * shared + _spread(aid, meta)))


def grievance(conn: sqlite3.Connection, oid: int, day: int, ctx: dict[str, Any] | None = None, pull: float = 0.0) -> dict[str, float]:
    """What moves bonded people: cruelty from their own head, humiliation and defeat, dead comrades nobody avenged, a succession
    dispute, a stronger branch pulling people away. Components add up; the total is smooth and below one."""
    cruelty = 0.5 * mistreated_count(conn, oid, day)
    lost = int(conn.execute("SELECT COUNT(*) FROM underworld_operations WHERE organization_id=? AND day>? AND result IN ('repulsed','failed','lost')", (oid, day - 90)).fetchone()[0])
    crack = int(conn.execute("SELECT COUNT(*) FROM underworld_enforcement_actions WHERE organization_id=? AND day>? AND action_kind='city_crackdown'", (oid, day - 90)).fetchone()[0])
    humiliation = 0.3 * lost + 0.5 * crack
    dead = int(conn.execute(
        """SELECT COUNT(*) FROM harm_incidents h WHERE h.fatal=1 AND h.day>? AND h.actor_id IN (SELECT actor_id FROM underworld_personnel WHERE organization_id=?)
           AND COALESCE(json_extract(h.metadata_json,'$.source_organization_id'),-1)<>?""", (day - 150, oid, oid)).fetchone()[0])
    answered = int(conn.execute("SELECT COUNT(*) FROM underworld_operations WHERE organization_id=? AND day>? AND operation_kind IN (%s)" % ",".join("?" * len(HOSTILE_OPS)),
                                (oid, day - 150, *HOSTILE_OPS)).fetchone()[0])
    unavenged = 0.5 * max(0, dead - answered)
    succ = conn.execute("SELECT value FROM engine_meta WHERE key=?", (f"uw_succ:{oid}",)).fetchone()
    succession = 0.8 * math.exp(-(day - int(succ[0])) / 120.0) if succ and 0 <= day - int(succ[0]) < 400 else 0.0
    faction = 0.35 * pull
    total = 1.0 - math.exp(-(cruelty + humiliation + unavenged + succession + faction))
    return {"cruelty": cruelty, "humiliation": humiliation, "unavenged": unavenged, "succession": succession, "faction": faction, "total": total}


def rival_pull(conn: sqlite3.Connection, ctx: dict[str, Any], rival: int | None) -> float:
    """How strongly a stronger, richer or more generous outfit in town draws this one's people."""
    if rival is None:
        return 0.0
    from . import temperament as tp
    from .underworld_rebuild import kick_rate
    oid = ctx["oid"]
    cache = ctx.setdefault("_strength", {})
    for o in (rival, oid):
        if o not in cache:
            cache[o] = tp.fighting_strength(conn, o)
    ratio = math.log((cache[rival] + 4.0) / (cache[oid] + 4.0))
    tr_r = float(conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (rival,)).fetchone()[0])
    richer = 1.0 if tr_r > float(ctx["org"]["treasury"]) else 0.0
    cut = max(0.0, kick_rate(conn, oid) - kick_rate(conn, rival)) / 0.25
    return max(0.0, min(1.0, 0.5 * math.tanh(ratio) + 0.2 * richer + 0.4 * min(1.0, cut)))


def _event(conn: sqlite3.Connection, day: int, kind: str, title: str, summary: str, loc: int | None, actor: int | None = None, rumorability: float | None = None) -> None:
    from .simulation import SimEvent, log_event
    log_event(conn, SimEvent(day=day, event_type=kind, title=title, summary=summary, severity=2, source_actor_id=actor, location_id=loc, rumorability=rumorability))


def _name(conn: sqlite3.Connection, actor_id: int) -> str:
    return str(conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()[0])


def _org(conn: sqlite3.Connection, oid: int) -> str:
    return str(conn.execute("SELECT name FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0])


# -- the monthly turn of an outfit ---------------------------------------------------------------------------------------

def _crew_drops(conn: sqlite3.Connection, oid: int, crews: list[sqlite3.Row]) -> dict[int, float]:
    """The fall in each crew's take against what it had grown used to (slow memory), updating that memory."""
    from .payroll import crew_earnings
    take = crew_earnings(conn, oid)
    drops: dict[int, float] = {}
    for c in crews:
        cid = int(c["id"])
        meta = json.loads(c["metadata_json"] or "{}")
        ema = float(meta.get("earn_ema", take.get(cid, 0.0)))
        now = take.get(cid, 0.0)
        drops[cid] = max(0.0, 1.0 - now / ema) if ema > 0.01 else 0.0
        meta["earn_ema"] = round(ema + 0.25 * (now - ema), 4)
        conn.execute("UPDATE underworld_crews SET metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), cid))
    return drops


def outfit_morale(conn: sqlite3.Connection, oid: int, months_behind: int, day: int | None = None, rng: random.Random | None = None) -> dict[str, Any]:
    """Monthly: crews' and named people's loyalty follow their bonds, their share and what the head does; then the rare departures."""
    from .relationships import adjust_relationship
    day = _day(conn) if day is None else day
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    if not org or str(org["status"]) not in ("active", "strained", "fragmented"):
        return {}
    rng = rng or random.Random(int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0]) * 31 + oid * 977 + day)
    ctx = outfit_context(conn, oid, day)
    leader = org["current_leader_actor_id"]
    loc = int(org["primary_location_id"]) if org["primary_location_id"] is not None else None
    rival = _rival_in_city(conn, oid, loc, ctx)
    pull = rival_pull(conn, ctx, rival)
    gr = grievance(conn, oid, day, ctx, pull)
    g = gr["total"]
    crews = ctx["crews"]
    drops = _crew_drops(conn, oid, crews)
    sizes = {int(c["id"]): float(c["size_estimate"]) for c in crews}
    org_drop = sum(drops[c] * sizes[c] for c in drops) / max(1e-9, sum(sizes.values())) if drops else 0.0
    # hoarding in hard times: a falling share while the treasury sits full is felt more
    if org_drop > 0.05 and float(org["treasury"]) > 6.0:
        org_drop *= 1.25
        drops = {c: d * 1.25 for c, d in drops.items()}
    out = {"left": 0, "defected": 0, "informed": 0, "stole": 0}
    cb = ctx["culture"]
    for c in crews:
        cid = int(c["id"])
        cbond = max(0.0, min(1.0, cb + 0.05))  # a crew's bond is the culture's, with a little for its own pride
        stress = leave_stress(cbond, 0.0, g, pull, drops[cid])
        tgt = drift_target(cbond, stress)
        loy = _clamp(float(c["loyalty"]) + 0.4 * (tgt - float(c["loyalty"])))
        coh = _clamp(float(c["cohesion"]) + 0.25 * (tgt - float(c["cohesion"])))
        conn.execute("UPDATE underworld_crews SET loyalty=?,cohesion=? WHERE id=?", (loy, coh, cid))
    people = conn.execute(
        """SELECT p.* FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id WHERE p.organization_id=? AND p.status='active' AND a.status='active'
           AND p.role_kind<>'boss' AND p.actor_id<>COALESCE(?,-1) ORDER BY p.actor_id""", (oid, leader)).fetchall()
    from .payroll import STIPEND_WEIGHT
    heat = conn.execute("SELECT investigative_heat,violence_heat FROM underworld_heat WHERE organization_id=?", (oid,)).fetchone()
    heatf = min(1.5, (float(heat[0]) / 60.0 + float(heat[1]) / 90.0) if heat else 0.0)
    for p in people:
        aid = int(p["actor_id"])
        meta = json.loads(p["metadata_json"] or "{}")
        bond = bond_strength(conn, ctx, p, day)
        stipended = str(p["role_kind"]) in STIPEND_WEIGHT
        a_months = float(months_behind) if stipended else 0.0
        drop = 0.0 if stipended else (drops.get(int(p["crew_id"]), org_drop) if p["crew_id"] is not None else org_drop)
        stress = leave_stress(bond, a_months, g, pull, drop)
        cur = float(meta.get("loyalty", drift_target(bond, 0.0)))
        new = _clamp(cur + 0.4 * (drift_target(bond, stress) - cur))
        if abs(round(new, 1) - float(meta.get("loyalty", -99))) >= 0.1 or "bond" not in meta:
            meta["loyalty"] = round(new, 2)
            meta["bond"] = round(bond, 3)
            conn.execute("UPDATE underworld_personnel SET metadata_json=? WHERE actor_id=?", (json.dumps(meta, sort_keys=True), aid))
        if leader is not None and abs(new - cur) >= 4.0:
            adjust_relationship(conn, aid, int(leader), day, loyalty_delta=(new - cur) * .5)
        h_leave = 0.30 * _sig((stress - 0.45 - 0.45 * bond) / 0.12)
        h_inform = 0.12 * _sig((stress - 0.50 - 0.40 * bond) / 0.15) * (0.3 + heatf)
        h_theft = 0.25 * _sig((stress - 0.45 - 0.40 * bond) / 0.12) if str(p["role_kind"]) == "accountant" else 0.0
        u = rng.random()
        if u < h_leave:
            p_def = 0.0 if rival is None else max(0.0, min(1.0, 0.15 + 0.7 * pull)) * ((1.0 - bond) + bond * g)
            if rival is not None and rng.random() < p_def:
                defect(conn, aid, oid, rival, day, bond=bond)
                out["defected"] += 1
            else:
                desert(conn, aid, oid, day, loc)
                out["left"] += 1
        elif u < h_leave + h_inform:
            inform(conn, aid, oid, day, loc)
            out["informed"] += 1
        elif u < h_leave + h_inform + h_theft:
            if skim(conn, aid, oid, day, loc, h_theft):
                out["stole"] += 1
    # a whole crew that has turned against its outfit may go over with its men
    if rival is not None:
        for c in conn.execute("SELECT * FROM underworld_crews WHERE organization_id=? AND status='active' ORDER BY loyalty,id", (oid,)).fetchall():
            cid = int(c["id"])
            cbond = max(0.0, min(1.0, cb + 0.05))
            stress = leave_stress(cbond, 0.0, g, pull, drops.get(cid, 0.0))
            h = 0.25 * _sig((stress - 0.50 - 0.5 * cbond) / 0.12) * (1.0 - cbond * (1.0 - g))
            if rng.random() < h:
                defect_crew(conn, cid, oid, rival, day)
                out["defected"] += 1
                break
    return out


def _rival_in_city(conn: sqlite3.Connection, oid: int, loc: int | None, ctx: dict[str, Any] | None = None) -> int | None:
    """The outfit in town a man could plausibly go over to: not an ally, patron or tributary, not a specialist, and never the player's
    outfit (nobody joins it without his order)."""
    if loc is None:
        return None
    from .underworld_aggression import leader_is_player
    best, best_pull = None, -1.0
    for r in conn.execute(
            """SELECT o.id FROM underworld_organizations o WHERE o.primary_location_id=? AND o.id<>? AND o.status='active'
               AND json_extract(o.metadata_json,'$.role') IS NOT 'specialist' ORDER BY o.cohesion DESC,o.treasury DESC,o.id LIMIT 4""", (loc, oid)).fetchall():
        rid = int(r[0])
        if leader_is_player(conn, rid):
            continue
        a, b = (oid, rid) if oid < rid else (rid, oid)
        rel = conn.execute("SELECT relation_kind FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a, b)).fetchone()
        if rel and str(rel[0]) in ("ally", "tributary", "patron"):
            continue
        if ctx is None:
            ctx = {"oid": oid, "org": conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (oid,)).fetchone()}
        pl = rival_pull(conn, ctx, rid)
        if pl > best_pull:
            best, best_pull = rid, pl
    return best


def desert(conn: sqlite3.Connection, aid: int, oid: int, day: int, loc: int | None) -> None:
    """Leaves for ordinary life: occupation follows Stage, and a former member is never labelled criminal."""
    from .person_ecology import make_former_member_ordinary
    from .underworld import record_underworld_membership_flow
    conn.execute("UPDATE underworld_personnel SET status='retired',crew_id=NULL WHERE actor_id=?", (aid,))
    conn.execute("UPDATE underworld_crews SET leader_actor_id=NULL WHERE leader_actor_id=? AND organization_id=?", (aid, oid))
    for tier in ("active", "core", "peripheral"):
        if conn.execute("SELECT 1 FROM underworld_membership_profiles WHERE organization_id=? AND %s>=1" % {"active": "active_members", "core": "core_members", "peripheral": "peripheral_associates"}[tier], (oid,)).fetchone():
            record_underworld_membership_flow(conn, oid, "desistance", 1, from_tier=tier, metadata={"actor_id": aid, "reason": "walked away"})
            break
    make_former_member_ordinary(conn, aid)
    _event(conn, day, "underworld_desertion", f"{_name(conn, aid)} walked away", f"{_name(conn, aid)} left {_org(conn, oid)} and went back to ordinary life.", loc, aid, .15)


def defect(conn: sqlite3.Connection, aid: int, oid: int, rival: int, day: int, bond: float = 0.4) -> None:
    """Goes over to a rival. Betrayal costs standing: the old head resents him (the more so the stronger the bond he broke), and
    the outfit taking him in does not trust him."""
    from .relationships import adjust_relationship
    from .underworld_rebuild import change_relation
    from .underworld import record_underworld_membership_flow
    conn.execute("UPDATE underworld_personnel SET organization_id=?,crew_id=NULL,role_kind=CASE WHEN role_kind IN ('underboss','lieutenant','crew_leader') THEN 'member' ELSE role_kind END,"
                 "metadata_json=json_set(COALESCE(metadata_json,'{}'),'$.loyalty',45,'$.distrusted_since',?) WHERE actor_id=?", (rival, day, aid))
    conn.execute("UPDATE underworld_personnel SET metadata_json=json_remove(metadata_json,'$.low_since') WHERE actor_id=?", (aid,))
    conn.execute("UPDATE underworld_crews SET leader_actor_id=NULL WHERE leader_actor_id=? AND organization_id=?", (aid, oid))
    record_underworld_membership_flow(conn, oid, "defection", 1, from_tier="active", metadata={"to_organization_id": rival, "actor_id": aid})
    record_underworld_membership_flow(conn, rival, "recruitment", 1, to_tier="active", metadata={"from_organization_id": oid, "actor_id": aid})
    _incident(conn, rival, oid, day, {"actor_id": aid})
    change_relation(conn, rival, oid, kind="rival", hostility_delta=10)
    heads = [r[0] for r in conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id IN (?,?)", (oid, rival)) if r[0] is not None]
    old = conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0]
    new = conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (rival,)).fetchone()[0]
    scale = 1.0 + float(bond)
    if old is not None:
        adjust_relationship(conn, int(old), aid, day, trust_delta=-25 * scale, resentment_delta=22 * scale, respect_delta=-10 * scale, stance_delta=-15 * scale)
    if new is not None:
        adjust_relationship(conn, int(new), aid, day, trust_delta=-14 * scale, stance_delta=-6)
    loc = conn.execute("SELECT primary_location_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0]
    _event(conn, day, "underworld_defection", f"{_name(conn, aid)} went over to {_org(conn, rival)}",
           f"{_name(conn, aid)} left {_org(conn, oid)} for {_org(conn, rival)}, and the old outfit knows it.", loc, aid, .3)


def defect_crew(conn: sqlite3.Connection, crew_id: int, oid: int, rival: int, day: int) -> None:
    from .underworld_rebuild import change_relation
    from .underworld import record_underworld_membership_flow
    c = conn.execute("SELECT * FROM underworld_crews WHERE id=?", (crew_id,)).fetchone()
    name = str(c["name"])
    if conn.execute("SELECT 1 FROM underworld_crews WHERE organization_id=? AND name=?", (rival, name)).fetchone():
        name = f"{name} (from {_org(conn, oid)})"
    conn.execute("UPDATE underworld_crews SET organization_id=?,name=?,home_zone_id=NULL,loyalty=50,cohesion=MAX(cohesion,50) WHERE id=?", (rival, name, crew_id))
    conn.execute("UPDATE underworld_personnel SET organization_id=? WHERE crew_id=? AND status='active'", (rival, crew_id))
    n = float(c["size_estimate"])
    record_underworld_membership_flow(conn, oid, "defection", n, from_tier="active", metadata={"to_organization_id": rival, "crew_id": crew_id})
    record_underworld_membership_flow(conn, rival, "recruitment", n, to_tier="active", metadata={"from_organization_id": oid, "crew_id": crew_id})
    _incident(conn, rival, oid, day, {"crew_id": crew_id})
    change_relation(conn, rival, oid, kind="rival", hostility_delta=14)
    loc = conn.execute("SELECT primary_location_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0]
    _event(conn, day, "underworld_defection", f"A crew left {_org(conn, oid)} for {_org(conn, rival)}",
           f"The {name} crew walked out on {_org(conn, oid)} and took service with {_org(conn, rival)}.", loc, None, .35)


def _incident(conn: sqlite3.Connection, source: int, target: int, day: int, meta: dict[str, Any]) -> None:
    conn.execute("""INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
                    VALUES (?,NULL,?,?,'defection',45,'open',?)""", (day, source, target, json.dumps(meta, sort_keys=True)))


def inform(conn: sqlite3.Connection, aid: int, oid: int, day: int, loc: int | None) -> None:
    from .underworld_rebuild import add_heat
    add_heat(conn, oid, public=2, investigative=7)
    _event(conn, day, "underworld_informant", "Word of an outfit's business reached the watch",
           f"Someone close to {_org(conn, oid)} has been talking to the watch.", loc, None, .3)


def skim(conn: sqlite3.Connection, aid: int, oid: int, day: int, loc: int | None, hazard: float = 0.1) -> bool:
    """The keeper of accounts takes a share of the treasury that grows with how badly he is placed to resent the outfit."""
    from . import ledger
    tr = float(conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0])
    amt = round(tr * min(0.5, 0.08 + 0.6 * hazard), 3)
    if amt < .05:
        return False
    ledger.transfer(conn, ("outfit", oid), ("person", aid), amt, flow_kind="other", purpose="skimmed")
    _event(conn, day, "underworld_theft", f"{_org(conn, oid)}'s books do not add up",
           f"Money has gone missing from {_org(conn, oid)}, and its keeper of accounts is the likeliest hand.", loc, aid, .25)
    return True


# -- households ---------------------------------------------------------------------------------------------------

def household_morale(conn: sqlite3.Connection, hid: int, months_behind: int, day: int | None = None, elapsed_days: int = 30, rng: random.Random | None = None) -> int:
    """Servants and stewards: bond (the culture of the place, the kind of service, years) against unpaid wages and ill use; a smooth
    hazard decides who leaves mid-term."""
    from .household_life import _record_life_event
    day = _day(conn) if day is None else day
    rng = rng or random.Random(int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0]) * 17 + hid * 613 + day)
    hh = conn.execute("SELECT name,location_id FROM households WHERE id=?", (hid,)).fetchone()
    cb = culture_bond(conn, hh["location_id"]) if hh else 0.45
    k = max(0.0, min(1.5, elapsed_days / 30.0))  # the books close every few days, not every month
    left = 0
    for t in conn.execute("SELECT * FROM household_service_terms WHERE household_id=? AND status='active' ORDER BY id", (hid,)).fetchall():
        aid = int(t["actor_id"])
        service = 1.0 - math.exp(-max(0.0, day - int(t["start_day"])) / 365.0 / 4.0)
        bond = max(0.0, min(1.0, 0.35 * cb + 0.35 * HOUSE_TIE.get(str(t["service_role"]), 0.3) + 0.15 * service + _spread(aid)))
        harmed = household_mistreated(conn, hid, aid, day)
        g = 1.0 - math.exp(-0.5 * harmed)
        stress = leave_stress(bond, float(months_behind), g)
        tgt = drift_target(bond, stress)
        sat = _clamp(float(t["satisfaction"]) + 0.4 * k * (tgt - float(t["satisfaction"])))
        loy = _clamp(float(t["loyalty"]) + 0.3 * k * (tgt - float(t["loyalty"])))
        conn.execute("UPDATE household_service_terms SET satisfaction=?,loyalty=? WHERE id=?", (sat, loy, int(t["id"])))
        if rng.random() < leave_hazard(bond, float(months_behind), g) * k:
            conn.execute("UPDATE household_service_terms SET status='former',end_day=? WHERE id=?", (day, int(t["id"])))
            conn.execute("UPDATE household_members SET status='former',left_day=? WHERE household_id=? AND actor_id=? AND role=? AND status='active'",
                         (day, hid, aid, t["service_role"]))
            _record_life_event(conn, "service_change", f"{_name(conn, aid)} left service in household #{hid}: unpaid or ill used.",
                               actor_id=aid, household_id=hid, day=day)
            _event(conn, day, "household_service_quit", f"{_name(conn, aid)} left {hh['name']}",
                   f"{_name(conn, aid)} walked out of service at {hh['name']}.", hh["location_id"], aid, .4)
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
        parts.append("the retainers are a month behind on pay" if a["months"] == 1 else f"the retainers are {_nword(a['months'])} months behind on pay")
    if crews is not None and float(crews) < 30:
        parts.append("the crews are close to walking")
    elif crews is not None and float(crews) < 45:
        parts.append("the crews are grumbling")
    return "; ".join(parts)


def _nword(n: int) -> str:
    return {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}.get(n, "many")
