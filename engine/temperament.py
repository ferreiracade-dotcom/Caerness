"""Gap 4b: violence temperament of an outfit, and its grudges.

Temperament is never black and white. Each outfit has a *tradition* (its type and canon character, its place, the Stage
of its fighters), a *base* (tradition moved by the boss's own drives) and a *current* value that events push around
and that drifts back to the base (half-life 150 days). A new boss re-derives the base from his own drives, partly
anchored to the tradition. A grudge is toward one rival, decays with a half-life of two years and adds to the
propensity and hostility toward that rival only.
"""
from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

STYLES = ("intimidation", "beating", "hired_beating", "smashed_premises", "seized_goods", "abduction", "duel", "hired_killing", "public_example", "assault")
STAGE_RANK = {"First": 0, "Temper": 1, "Third": 2, "Breach": 3, "Fifth": 4, "Sixth": 5}
STAGE_WEIGHT = {"First": 1.0, "Temper": 2.2, "Third": 5.0, "Breach": 12.0, "Fifth": 30.0, "Sixth": 60.0}
FIGHTER_ROLES = ("boss", "underboss", "lieutenant", "crew_leader", "enforcer", "collector")
REVERT_HALF_LIFE = 150.0
GRUDGE_HALF_LIFE = 730.0
COERCIVE_RACKETS = ("high-risk debt", "brothel protection", "protection collections")

_STYLE_WEIGHTS = {
    "street": {"beating": 3.0, "smashed_premises": 2.2, "intimidation": 2.0, "assault": 1.6, "seized_goods": 1.2, "abduction": 0.8, "duel": 0.5, "public_example": 0.6},
    "durable": {"intimidation": 3.0, "public_example": 1.4, "seized_goods": 1.4, "hired_killing": 1.2, "hired_beating": 1.0, "duel": 0.7, "smashed_premises": 0.8},
    "specialist": {"intimidation": 3.0, "hired_beating": 2.2, "hired_killing": 1.8, "seized_goods": 1.2},
}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _meta(org: sqlite3.Row) -> dict[str, Any]:
    try:
        return json.loads(org["metadata_json"] or "{}")
    except Exception:
        return {}


def outfit_class(conn: sqlite3.Connection, oid: int) -> str:
    org = conn.execute("SELECT organization_type,metadata_json FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    if not org:
        return "specialist"
    role = _meta(org).get("role")
    if role == "street_gang":
        return "street"
    if role == "specialist" or org["organization_type"] == "network":
        return "specialist"
    if org["organization_type"] == "gang":
        return "street"
    return "durable"


def drives_of(conn: sqlite3.Connection, actor_id: int | None) -> dict[str, float]:
    base = {"aggression": .5, "patience": .5, "ambition": .5, "pragmatism": .5, "loyalty": .5}
    if actor_id is None:
        return base
    row = conn.execute("SELECT * FROM actor_drives WHERE actor_id=?", (int(actor_id),)).fetchone()
    if row:
        for k in base:
            try:
                base[k] = float(row[k])
            except (IndexError, KeyError, TypeError):
                pass
    return base


def stage_weight(conn: sqlite3.Connection, actor_id: int) -> float:
    r = conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?", (int(actor_id),)).fetchone()
    return STAGE_WEIGHT.get(str(r[0]), 1.0) if r and r[0] else 1.0


def _fighters(conn: sqlite3.Connection, oid: int) -> list[sqlite3.Row]:
    marks = ",".join("?" * len(FIGHTER_ROLES))
    return conn.execute(
        f"""SELECT p.actor_id,p.role_kind,COALESCE(cp.current_stage,'First') stage FROM underworld_personnel p
            JOIN actors a ON a.id=p.actor_id LEFT JOIN cultivation_profiles cp ON cp.actor_id=p.actor_id
            WHERE p.organization_id=? AND p.status='active' AND a.status='active' AND p.role_kind IN ({marks}) ORDER BY p.authority DESC,p.actor_id""",
        (oid, *FIGHTER_ROLES)).fetchall()


def stage_power(conn: sqlite3.Connection, oid: int) -> float:
    """Stage-weighted strength of the named fighters (the top eight)."""
    return sum(STAGE_WEIGHT.get(str(r["stage"]), 1.0) for r in _fighters(conn, oid)[:8])


def fighting_strength(conn: sqlite3.Connection, oid: int) -> float:
    org = conn.execute("SELECT violence_capacity FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    prof = conn.execute("SELECT COALESCE(core_members,0)+COALESCE(active_members,0) FROM underworld_membership_profiles WHERE organization_id=?", (oid,)).fetchone()
    members = float(prof[0]) if prof and prof[0] is not None else 5.0
    return 0.5 * float(org[0] if org else 20) + 0.4 * members + 2.0 * stage_power(conn, oid)


def _tradition(conn: sqlite3.Connection, oid: int) -> float:
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    meta = _meta(org)
    cls = outfit_class(conn, oid)
    if meta.get("violence") == "controlled":
        t = .38
    elif meta.get("violence") == "contingency":
        t = .28
    elif cls == "street":
        t = .70 if meta.get("role") == "street_gang" else .55
    elif cls == "specialist":
        t = .10 if org["organization_type"] == "network" else .14
    elif org["organization_type"] in ("mafia_family", "criminal_dynasty", "syndicate"):
        t = .38
    else:
        t = .30
    kinds = {r[0] for r in conn.execute("SELECT racket_kind FROM underworld_racket_sites WHERE organization_id=? AND status='active'", (oid,))}
    if kinds & set(COERCIVE_RACKETS):
        t += .08 if cls != "street" else .04
    if org["primary_location_id"] is not None:
        try:
            from .underworld_ecology import _character
            t += .10 * (float(_character(conn, int(org["primary_location_id"]))[0]["street"]) - .5)
        except Exception:
            pass
    fighters = _fighters(conn, oid)[:6]
    if fighters:
        t += min(.10, .025 * sum(STAGE_RANK.get(str(f["stage"]), 0) for f in fighters) / len(fighters))
    return _clamp(t, .03, .92)


def _leader_mod(drives: dict[str, float]) -> float:
    return .28 * (drives["aggression"] - .5) - .16 * (drives["patience"] - .5)


def _style_for(conn: sqlite3.Connection, oid: int) -> str:
    return styles_for(conn, oid)[0]


def styles_for(conn: sqlite3.Connection, oid: int) -> list[str]:
    cls = outfit_class(conn, oid)
    w = dict(_STYLE_WEIGHTS[cls])
    kinds = {r[0] for r in conn.execute("SELECT racket_kind FROM underworld_racket_sites WHERE organization_id=? AND status='active'", (oid,))}
    if cls == "specialist" and kinds & set(COERCIVE_RACKETS):
        w["beating"] = 1.5
    if sum(STAGE_RANK.get(str(f["stage"]), 0) for f in _fighters(conn, oid)[:6]) >= 6 and "duel" not in w:
        w["duel"] = 1.0
    return [k for k, _ in sorted(w.items(), key=lambda kv: (-kv[1], kv[0]))]


def style_weights(conn: sqlite3.Connection, oid: int) -> dict[str, float]:
    cls = outfit_class(conn, oid)
    w = dict(_STYLE_WEIGHTS[cls])
    for k in styles_for(conn, oid):
        w.setdefault(k, 1.0)
    return w


def _derive(conn: sqlite3.Connection, oid: int) -> tuple[float, float, str, int | None]:
    org = conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    leader = int(org[0]) if org and org[0] is not None else None
    tradition = _tradition(conn, oid)
    base = _clamp(tradition + _leader_mod(drives_of(conn, leader)), .03, .95)
    return tradition, base, _style_for(conn, oid), leader


def ensure_temperament(conn: sqlite3.Connection, oid: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM underworld_temperament WHERE organization_id=?", (oid,)).fetchone()
    day = _day(conn)
    if row is None:
        tradition, base, style, leader = _derive(conn, oid)
        conn.execute("INSERT INTO underworld_temperament(organization_id,tradition,base,current,style,leader_actor_id,last_day) VALUES (?,?,?,?,?,?,?)",
                     (oid, tradition, base, base, style, leader, day))
        return conn.execute("SELECT * FROM underworld_temperament WHERE organization_id=?", (oid,)).fetchone()
    cur = conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    leader = int(cur[0]) if cur and cur[0] is not None else None
    if leader is not None and row["leader_actor_id"] != leader:
        if row["leader_actor_id"] is None:
            rederive(conn, oid)
        else:
            on_succession(conn, oid)
        row = conn.execute("SELECT * FROM underworld_temperament WHERE organization_id=?", (oid,)).fetchone()
    return row


def rederive(conn: sqlite3.Connection, oid: int) -> None:
    """Hard reset of base and current to what the outfit's tradition and present boss give."""
    ensure = conn.execute("SELECT 1 FROM underworld_temperament WHERE organization_id=?", (oid,)).fetchone()
    tradition, base, style, leader = _derive(conn, oid)
    if not ensure:
        conn.execute("INSERT INTO underworld_temperament(organization_id,tradition,base,current,style,leader_actor_id,last_day) VALUES (?,?,?,?,?,?,?)",
                     (oid, tradition, base, base, style, leader, _day(conn)))
        return
    conn.execute("UPDATE underworld_temperament SET tradition=?,base=?,current=?,style=?,leader_actor_id=?,last_day=? WHERE organization_id=?",
                 (tradition, base, base, style, leader, _day(conn), oid))


def on_succession(conn: sqlite3.Connection, oid: int) -> None:
    """A new boss brings his own drives; the outfit's mood carries over half-way."""
    row = conn.execute("SELECT * FROM underworld_temperament WHERE organization_id=?", (oid,)).fetchone()
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES (?,?)", (f"uw_succ:{oid}", str(_day(conn))))  # people remember a change of head
    cur_eff = _eff(row, _day(conn))
    tradition, base, style, leader = _derive(conn, oid)
    conn.execute("UPDATE underworld_temperament SET tradition=?,base=?,current=?,style=?,leader_actor_id=?,last_day=? WHERE organization_id=?",
                 (tradition, base, _clamp(.5 * cur_eff + .5 * base, .02, .98), style, leader, _day(conn), oid))


def _eff(row: sqlite3.Row, day: int) -> float:
    k = .5 ** (max(0, day - int(row["last_day"])) / REVERT_HALF_LIFE)
    return float(row["base"]) + (float(row["current"]) - float(row["base"])) * k


def effective_current(conn: sqlite3.Connection, oid: int, day: int | None = None) -> float:
    row = ensure_temperament(conn, oid)
    return _eff(row, _day(conn) if day is None else int(day))


def adjust(conn: sqlite3.Connection, oid: int, delta: float, day: int | None = None) -> float:
    """Defeats, costly fights and crackdowns (negative) make an outfit cautious; easy wins (positive) make it bolder."""
    ensure_temperament(conn, oid)
    day = _day(conn) if day is None else int(day)
    new = _clamp(effective_current(conn, oid, day) + delta, .02, .98)
    conn.execute("UPDATE underworld_temperament SET current=?,last_day=? WHERE organization_id=?", (new, day, oid))
    return new


def faction_push(conn: sqlite3.Connection, oid: int) -> float:
    """A hotter faction (a lieutenant or crew leader with high aggression) pushes a controlled outfit."""
    org = conn.execute("SELECT current_leader_actor_id,cohesion FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    if not org:
        return 0.0
    leader_aggr = drives_of(conn, org[0])["aggression"]
    hot = 0.0
    for r in conn.execute("SELECT actor_id FROM underworld_personnel WHERE organization_id=? AND status='active' AND role_kind IN ('underboss','lieutenant','crew_leader') AND actor_id<>COALESCE(?,-1)", (oid, org[0])):
        hot = max(hot, drives_of(conn, int(r[0]))["aggression"])
    return .3 * max(0.0, hot - leader_aggr - .15) * (1.0 if float(org[1]) < 70 else .6)


def propensity(conn: sqlite3.Connection, oid: int, toward: int | None = None, day: int | None = None) -> float:
    day = _day(conn) if day is None else int(day)
    p = effective_current(conn, oid, day) + faction_push(conn, oid)
    if toward is not None:
        p += .5 * grudge_level(conn, oid, toward, day) / 100.0
    return _clamp(p)


# -- grudges -------------------------------------------------------------------------------------------------

def grudge_level(conn: sqlite3.Connection, oid: int, rival: int, day: int | None = None) -> float:
    row = conn.execute("SELECT intensity,last_day FROM underworld_grudges WHERE organization_id=? AND rival_organization_id=?", (oid, rival)).fetchone()
    if not row:
        return 0.0
    day = _day(conn) if day is None else int(day)
    return float(row["intensity"]) * .5 ** (max(0, day - int(row["last_day"])) / GRUDGE_HALF_LIFE)


def add_grudge(conn: sqlite3.Connection, oid: int, rival: int, amount: float, cause_kind: str, cause_actor_id: int | None = None) -> float:
    from .underworld_rebuild import change_relation, ensure_relation
    if oid == rival:
        return 0.0
    day = _day(conn)
    level = min(100.0, grudge_level(conn, oid, rival, day) + float(amount))
    conn.execute(
        """INSERT INTO underworld_grudges(organization_id,rival_organization_id,intensity,last_day,cause_kind,cause_actor_id,started_day)
           VALUES (?,?,?,?,?,?,?) ON CONFLICT(organization_id,rival_organization_id) DO UPDATE SET
           intensity=excluded.intensity,last_day=excluded.last_day,cause_kind=excluded.cause_kind,cause_actor_id=excluded.cause_actor_id""",
        (oid, rival, level, day, cause_kind, cause_actor_id, day))
    rel = ensure_relation(conn, oid, rival)
    lift = max(0.0, 62.0 - float(rel["hostility"])) if amount >= 50 else float(amount) * .5
    change_relation(conn, oid, rival, kind="war" if level >= 85 else "rival", hostility_delta=lift, respect_delta=-2,
                    metadata={"grudge": cause_kind})
    return level


_KIN_OF_LEADER = ("parent", "child", "sibling", "spouse", "adoptive_parent", "adoptive_child", "guardian", "ward")


def note_personal_blow(conn: sqlite3.Connection, victim_actor_id: int, source_org_id: int, outcome: str) -> list[int]:
    """A rival killed ('fatal') or maimed ('persistent') someone: a boss's kin, or a lieutenant or the boss himself.
    The outfit that lost them takes a sharp grudge against the source."""
    if outcome not in ("fatal", "persistent") or source_org_id is None:
        return []
    fatal = outcome == "fatal"
    hit: dict[int, tuple[float, str]] = {}
    kin_ids = {int(r[0]) for r in conn.execute("SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND legal_status<>'former'", (victim_actor_id,))}
    kin_ids |= {int(r[0]) for r in conn.execute("SELECT actor_a_id FROM kinship_links WHERE actor_b_id=? AND legal_status<>'former'", (victim_actor_id,))}
    for k in kin_ids:
        for o in conn.execute(
                """SELECT o.id,p.role_kind FROM underworld_personnel p JOIN underworld_organizations o ON o.id=p.organization_id
                   WHERE p.actor_id=? AND p.status='active' AND p.role_kind IN ('boss','underboss','lieutenant')
                   AND o.status IN ('active','strained','fragmented')""", (k,)):
            amount = (70.0 if fatal else 45.0) if o["role_kind"] == "boss" else (40.0 if fatal else 25.0)
            hit[int(o["id"])] = (max(hit.get(int(o["id"]), (0, ""))[0], amount), "kin_killed" if fatal else "kin_maimed")
    for o in conn.execute(
            """SELECT o.id,p.role_kind FROM underworld_personnel p JOIN underworld_organizations o ON o.id=p.organization_id
               WHERE p.actor_id=? AND p.role_kind IN ('boss','underboss','lieutenant') AND p.status IN ('active','dead')
               AND o.status IN ('active','strained','fragmented')""", (victim_actor_id,)):
        amount = (60.0 if fatal else 38.0) if o["role_kind"] != "lieutenant" else (55.0 if fatal else 35.0)
        if amount > hit.get(int(o["id"]), (0, ""))[0]:
            hit[int(o["id"])] = (amount, "leader_killed" if fatal else "leader_maimed")
    # Crew leaders are remembered too, a little less than the boss's own; any killing of a member leaves a small grudge.
    if victim_actor_id is not None:
        for o in conn.execute(
                """SELECT o.id,p.role_kind FROM underworld_personnel p JOIN underworld_organizations o ON o.id=p.organization_id
                   WHERE p.actor_id=? AND p.status IN ('active','dead') AND o.status IN ('active','strained','fragmented')""", (victim_actor_id,)):
            if o["role_kind"] in ("boss", "underboss", "lieutenant"):
                continue
            if o["role_kind"] == "crew_leader":
                amount, kind = (30.0, "crew_leader_killed") if fatal else (16.0, "crew_leader_maimed")
            elif fatal:
                amount, kind = 8.0, "member_killed"
            else:
                continue
            if amount > hit.get(int(o["id"]), (0, ""))[0]:
                hit[int(o["id"])] = (amount, kind)
    done = []
    for oid, (amount, kind) in sorted(hit.items()):
        if oid == int(source_org_id):
            continue
        add_grudge(conn, oid, int(source_org_id), amount, kind, victim_actor_id)
        done.append(oid)
    return done
