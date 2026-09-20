from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from .simulation import current_day

FAMILIES = (
    "pressure", "fixing", "misdirection", "isolation", "depth",
    "reserve_play", "mobility", "attrition", "disruption", "exploitation",
)

STAGE_WEIGHT = {
    "First": 1.0,
    "Temper": 2.0,
    "Third": 4.0,
    "Breach": 8.0,
    "Fifth": 18.0,
    "Sixth": 35.0,
}


def _clamp(v: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, float(v))), 3)


def set_battle_doctrine(conn: sqlite3.Connection, actor_id: int, **weights: float) -> None:
    if not conn.execute("SELECT 1 FROM actors WHERE id=?", (actor_id,)).fetchone():
        raise ValueError("Actor does not exist")
    values = {k: _clamp(weights.get(k, 50.0)) for k in FAMILIES}
    conn.execute(
        """INSERT INTO battle_doctrines(
               actor_id,pressure,fixing,misdirection,isolation,depth,reserve_play,mobility,attrition,disruption,exploitation,notes,updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(actor_id) DO UPDATE SET
               pressure=excluded.pressure,fixing=excluded.fixing,misdirection=excluded.misdirection,
               isolation=excluded.isolation,depth=excluded.depth,reserve_play=excluded.reserve_play,
               mobility=excluded.mobility,attrition=excluded.attrition,disruption=excluded.disruption,
               exploitation=excluded.exploitation,notes=excluded.notes,updated_at=CURRENT_TIMESTAMP""",
        (actor_id, *(values[k] for k in FAMILIES), weights.get("notes")),
    )


def doctrine(conn: sqlite3.Connection, actor_id: int | None) -> dict[str, float]:
    if actor_id is None:
        return {k: 50.0 for k in FAMILIES}
    row = conn.execute("SELECT * FROM battle_doctrines WHERE actor_id=?", (actor_id,)).fetchone()
    if not row:
        return {k: 50.0 for k in FAMILIES}
    return {k: float(row[k]) for k in FAMILIES}


def set_zone_current(conn: sqlite3.Connection, zone_id: int, *, density: float = 50, stability: float = 50,
                     replenishment: float = 50, notes: str | None = None) -> None:
    if not conn.execute("SELECT 1 FROM battle_zones WHERE id=?", (zone_id,)).fetchone():
        raise ValueError("Battle zone does not exist")
    conn.execute(
        """INSERT INTO battle_zone_current(zone_id,density,stability,replenishment,notes,updated_at)
           VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(zone_id) DO UPDATE SET density=excluded.density,stability=excluded.stability,
           replenishment=excluded.replenishment,notes=excluded.notes,updated_at=CURRENT_TIMESTAMP""",
        (zone_id, _clamp(density), _clamp(stability), _clamp(replenishment), notes),
    )


def add_vein_asset(conn: sqlite3.Connection, engagement_id: int, side_id: int, stage_key: str, *,
                   actor_id: int | None = None, unit_id: int | None = None, zone_id: int | None = None,
                   battlefield_role: str = "flexible", readiness: float = 100, reserve: float = 100,
                   commitment: float = 0.5, metadata: dict[str, Any] | None = None) -> int:
    if stage_key not in STAGE_WEIGHT:
        raise ValueError("Invalid Vein stage")
    if battlefield_role not in {"anchor","reserve","screen","support","hunter","flexible"}:
        raise ValueError("Invalid battlefield role")
    side = conn.execute("SELECT engagement_id FROM battle_sides WHERE id=?", (side_id,)).fetchone()
    if not side or int(side[0]) != int(engagement_id):
        raise ValueError("Side does not belong to battle")
    if zone_id is not None:
        z = conn.execute("SELECT engagement_id FROM battle_zones WHERE id=?", (zone_id,)).fetchone()
        if not z or int(z[0]) != int(engagement_id):
            raise ValueError("Zone does not belong to battle")
    cur = conn.execute(
        """INSERT INTO battle_vein_assets(
               engagement_id,side_id,actor_id,unit_id,zone_id,stage_key,battlefield_role,readiness,reserve,commitment,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,'available',?)""",
        (engagement_id, side_id, actor_id, unit_id, zone_id, stage_key, battlefield_role,
         _clamp(readiness), _clamp(reserve), max(0.0,min(1.0,float(commitment))), json.dumps(metadata or {}, ensure_ascii=False)),
    )
    return int(cur.lastrowid)


def assign_vein_asset(conn: sqlite3.Connection, asset_id: int, zone_id: int | None, *, commitment: float | None = None) -> None:
    asset = conn.execute("SELECT * FROM battle_vein_assets WHERE id=?", (asset_id,)).fetchone()
    if not asset:
        raise ValueError("Vein asset does not exist")
    if zone_id is not None:
        zone = conn.execute("SELECT engagement_id FROM battle_zones WHERE id=?", (zone_id,)).fetchone()
        if not zone or int(zone[0]) != int(asset["engagement_id"]):
            raise ValueError("Zone does not belong to same battle")
    c = float(asset["commitment"]) if commitment is None else max(0.0,min(1.0,float(commitment)))
    conn.execute("UPDATE battle_vein_assets SET zone_id=?,commitment=?,status=? WHERE id=?",
                 (zone_id,c,"committed" if zone_id is not None else "available",asset_id))


def submit_tactical_choice(conn: sqlite3.Connection, engagement_id: int, side_id: int, family_key: str, *,
                           actor_id: int | None = None, focus_zone_id: int | None = None,
                           commitment: float = 0.5, source_kind: str = "player") -> int:
    if family_key not in FAMILIES:
        raise ValueError("Invalid tactical family")
    if source_kind not in {"player","doctrine","npc_rules","npc_model","delegated"}:
        raise ValueError("Invalid source kind")
    round_index = int(conn.execute("SELECT round_index FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()[0]) + 1
    if focus_zone_id is not None:
        zone = conn.execute("SELECT engagement_id FROM battle_zones WHERE id=?", (focus_zone_id,)).fetchone()
        if not zone or int(zone[0]) != int(engagement_id):
            raise ValueError("Zone does not belong to battle")
    cur = conn.execute(
        """INSERT OR REPLACE INTO battle_tactical_choices(
               engagement_id,side_id,actor_id,round_index,family_key,focus_zone_id,commitment,source_kind,status,result_json,created_day
           ) VALUES (?,?,?,?,?,?,?,?, 'submitted','{}',?)""",
        (engagement_id,side_id,actor_id,round_index,family_key,focus_zone_id,max(0.0,min(1.0,float(commitment))),source_kind,current_day(conn)),
    )
    return int(cur.lastrowid)


def _best_zone(conn: sqlite3.Connection, engagement_id: int, *, prefer_opportunity: bool = False) -> int | None:
    rows = conn.execute("SELECT * FROM battle_zones WHERE engagement_id=? AND status!='abandoned' ORDER BY id", (engagement_id,)).fetchall()
    if not rows:
        return None
    if prefer_opportunity:
        rows = sorted(rows, key=lambda z: (abs(float(z["pressure"])), float(z["importance"])), reverse=True)
    else:
        rows = sorted(rows, key=lambda z: float(z["importance"]), reverse=True)
    return int(rows[0]["id"])


def _ensure_choice(conn: sqlite3.Connection, engagement_id: int, side: sqlite3.Row, round_index: int, rng: random.Random) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM battle_tactical_choices WHERE engagement_id=? AND side_id=? AND round_index=? ORDER BY id DESC LIMIT 1",
        (engagement_id,side["id"],round_index),
    ).fetchone()
    if row:
        return row
    actor_id = side["controller_actor_id"]
    d = doctrine(conn, int(actor_id) if actor_id is not None else None)
    # Context nudges preferences without scripting a single correct response.
    reserve = float(side["reserve_capacity"]); morale = float(side["morale"]); momentum = float(side["momentum"])
    scores = dict(d)
    if reserve > 60: scores["reserve_play"] += 10
    if reserve < 30: scores["depth"] += 12; scores["attrition"] += 8
    if morale < 40: scores["depth"] += 10; scores["disruption"] += 5
    if momentum > 20: scores["exploitation"] += 18; scores["pressure"] += 8
    if momentum < -20: scores["misdirection"] += 8; scores["depth"] += 10
    weighted = sorted(scores.items(), key=lambda kv: (kv[1] + rng.uniform(-8,8)), reverse=True)
    family = weighted[0][0]
    focus = _best_zone(conn, engagement_id, prefer_opportunity=family in {"exploitation","isolation","pressure"})
    conn.execute(
        """INSERT INTO battle_tactical_choices(
               engagement_id,side_id,actor_id,round_index,family_key,focus_zone_id,commitment,source_kind,status,result_json,created_day
           ) VALUES (?,?,?,?,?,?,0.5,'doctrine','submitted','{}',?)""",
        (engagement_id,side["id"],actor_id,round_index,family,focus,current_day(conn)),
    )
    return conn.execute("SELECT * FROM battle_tactical_choices WHERE engagement_id=? AND side_id=? AND round_index=?",
                        (engagement_id,side["id"],round_index)).fetchone()


def _zone_current_factor(conn: sqlite3.Connection, zone_id: int) -> float:
    row = conn.execute("SELECT * FROM battle_zone_current WHERE zone_id=?", (zone_id,)).fetchone()
    if not row:
        return 1.0
    # Current helps sustain powerful cultivators, especially when stable/replenishing, but never substitutes for Stage.
    score = float(row["density"]) * 0.45 + float(row["stability"]) * 0.35 + float(row["replenishment"]) * 0.20
    return 0.78 + (score / 100.0) * 0.44


def _vein_zone_influence(conn: sqlite3.Connection, engagement_id: int, side_id: int, zone_id: int, round_index: int) -> float:
    assets = conn.execute(
        """SELECT * FROM battle_vein_assets WHERE engagement_id=? AND side_id=? AND zone_id=?
           AND status IN ('available','committed','strained') ORDER BY id""",
        (engagement_id,side_id,zone_id),
    ).fetchall()
    ecology = _zone_current_factor(conn, zone_id)
    total = 0.0
    for a in assets:
        if float(a["readiness"]) <= 10 or float(a["reserve"]) <= 5:
            continue
        weight = STAGE_WEIGHT[str(a["stage_key"])]
        commitment = float(a["commitment"])
        sustainability = (float(a["readiness"])/100.0) * (0.55 + float(a["reserve"])/220.0)
        role_mod = {"anchor":1.08,"reserve":0.75,"screen":0.85,"support":0.92,"hunter":1.02,"flexible":1.0}[str(a["battlefield_role"])]
        contribution = weight * commitment * sustainability * ecology * role_mod
        total += contribution
        spend = max(0.5, weight * 0.05 * commitment * (1.08 if ecology < 0.95 else 0.92))
        new_reserve = _clamp(float(a["reserve"]) - spend)
        new_readiness = _clamp(float(a["readiness"]) - max(0.2, spend*0.25))
        status = "strained" if new_reserve < 25 or new_readiness < 35 else "committed"
        conn.execute("UPDATE battle_vein_assets SET reserve=?,readiness=?,status=? WHERE id=?",
                     (new_reserve,new_readiness,status,a["id"]))
    return min(28.0, total)


def apply_tactical_layer(conn: sqlite3.Connection, engagement_id: int, round_index: int, seed: int) -> dict[str, Any]:
    """Apply abstract tactical families and Vein-specific battlefield leverage.

    The families are narrative/simulation categories, not real-world tactical instructions.
    They alter opportunity costs, information, reserves, pressure, and endurance at a high level.
    """
    rng = random.Random(seed ^ 0x15CAE)  # deterministic salt
    sides = conn.execute("SELECT * FROM battle_sides WHERE engagement_id=? ORDER BY id", (engagement_id,)).fetchall()
    zones = conn.execute("SELECT * FROM battle_zones WHERE engagement_id=? AND status!='abandoned' ORDER BY id", (engagement_id,)).fetchall()
    out: list[dict[str, Any]] = []

    for side in sides:
        choice = _ensure_choice(conn, engagement_id, side, round_index, rng)
        family = str(choice["family_key"]); commitment = float(choice["commitment"])
        focus = int(choice["focus_zone_id"]) if choice["focus_zone_id"] is not None else (_best_zone(conn, engagement_id) or 0)
        side_delta = {"reserve":0.0,"logistics":0.0,"information":0.0,"momentum":0.0,"morale":0.0,"cohesion":0.0}
        zone_delta = 0.0
        note = ""

        if family == "pressure":
            zone_delta = 6.0 * commitment; side_delta["reserve"] = -3.0*commitment; side_delta["momentum"] = 2.0*commitment
            note = "Concentrated effort seeks local initiative at a cost in flexibility."
        elif family == "fixing":
            zone_delta = 2.5 * commitment; side_delta["cohesion"] = 1.0*commitment
            note = "The side spends effort keeping an opposing element occupied rather than chasing immediate gain."
        elif family == "misdirection":
            side_delta["information"] = 4.0*commitment; side_delta["reserve"] = -1.5*commitment
            note = "The side trades certainty and effort for a chance to distort the opponent's reading of priorities."
        elif family == "isolation":
            zone_delta = 4.0*commitment; side_delta["reserve"] = -2.0*commitment
            note = "The side tries to separate a local problem from support rather than overpower the whole field."
        elif family == "depth":
            zone_delta = -2.0*commitment; side_delta["cohesion"] = 3.0*commitment; side_delta["morale"] = 1.5*commitment
            note = "The side accepts less immediate pressure in exchange for resilience and time."
        elif family == "reserve_play":
            side_delta["reserve"] = 2.5*commitment; side_delta["momentum"] = -1.0*commitment
            note = "The side preserves flexible strength rather than committing it to the current problem."
        elif family == "mobility":
            zone_delta = 2.0*commitment; side_delta["information"] = 1.5*commitment; side_delta["cohesion"] = -0.8*commitment
            note = "The side prioritizes changing where its strength matters, accepting coordination strain."
        elif family == "attrition":
            side_delta["logistics"] = -1.5*commitment; side_delta["cohesion"] = 1.0*commitment
            note = "The side accepts a slower contest intended to make endurance and resources matter."
        elif family == "disruption":
            side_delta["information"] = 2.0*commitment; side_delta["reserve"] = -1.5*commitment
            note = "The side targets coordination and clarity rather than immediate territorial pressure."
        elif family == "exploitation":
            existing = 0.0
            if focus:
                z = conn.execute("SELECT pressure,initiative_side_id FROM battle_zones WHERE id=?", (focus,)).fetchone()
                if z and z["initiative_side_id"] is not None and int(z["initiative_side_id"]) == int(side["id"]):
                    existing = min(1.0, abs(float(z["pressure"]))/50.0)
            zone_delta = (1.0 + 8.0*existing) * commitment
            side_delta["reserve"] = -4.0*commitment
            if existing < 0.25:
                side_delta["cohesion"] = -2.0*commitment
            note = "The side tries to enlarge an existing opening; without one, the effort risks overreach."

        # Fantasy-specific Vein influence: current-bearing elites are strategic resources whose effect
        # depends on where they are, how much reserve they retain, and local current conditions.
        vein = _vein_zone_influence(conn, engagement_id, int(side["id"]), focus, round_index) if focus else 0.0
        zone_delta += vein * (0.30 + 0.45*commitment)

        if focus:
            zone = conn.execute("SELECT pressure FROM battle_zones WHERE id=?", (focus,)).fetchone()
            if zone:
                sign = 1.0 if int(side["id"]) == min(int(s["id"]) for s in sides) else -1.0
                conn.execute("UPDATE battle_zones SET pressure=? WHERE id=?",
                             (max(-100,min(100,float(zone["pressure"]) + sign*zone_delta)),focus))

        updates = {
            "reserve_capacity": _clamp(float(side["reserve_capacity"]) + side_delta["reserve"]),
            "logistics": _clamp(float(side["logistics"]) + side_delta["logistics"]),
            "information_quality": _clamp(float(side["information_quality"]) + side_delta["information"]),
            "momentum": max(-100,min(100,float(side["momentum"]) + side_delta["momentum"])),
            "morale": _clamp(float(side["morale"]) + side_delta["morale"]),
            "cohesion": _clamp(float(side["cohesion"]) + side_delta["cohesion"]),
        }
        conn.execute(
            """UPDATE battle_sides SET reserve_capacity=?,logistics=?,information_quality=?,momentum=?,morale=?,cohesion=? WHERE id=?""",
            (*updates.values(), side["id"]),
        )
        payload = {"family":family,"focus_zone_id":focus or None,"vein_influence":round(vein,3),"side_delta":side_delta,"zone_delta":round(zone_delta,3)}
        conn.execute("UPDATE battle_tactical_choices SET status='resolved',result_json=? WHERE id=?",
                     (json.dumps(payload, ensure_ascii=False), choice["id"]))
        conn.execute(
            """INSERT INTO battle_tactical_effects(
                   engagement_id,round_index,side_id,zone_id,effect_kind,magnitude,summary_text,payload_json,created_day
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (engagement_id,round_index,side["id"],focus or None,family,zone_delta,note,json.dumps(payload,ensure_ascii=False),current_day(conn)),
        )
        out.append({"side_id":int(side["id"]),"family":family,"focus_zone_id":focus or None,"vein_influence":round(vein,3),"summary":note})

    return {"choices":out,"principle":"Tactical families alter trade-offs and opportunities; they are not scripted winning moves."}


def apply_personal_combat_consequence(conn: sqlite3.Connection, engagement_id: int, zone_id: int, *,
                                      winner_asset_id: int | None, loser_asset_id: int | None,
                                      summary: str = "A consequential personal confrontation changed the local battle picture.") -> dict[str, Any]:
    """Translate an important personal-combat result into battlefield consequences.

    This does not award victory merely because a duel occurred. Consequence depends on the defeated
    person's Stage, command significance, the importance of the location, the side's existing fragility,
    and whether replacement/containment remains plausible.
    """
    zone = conn.execute("SELECT * FROM battle_zones WHERE id=? AND engagement_id=?", (zone_id,engagement_id)).fetchone()
    if not zone:
        raise ValueError("Battle zone does not exist")
    winner = conn.execute("SELECT * FROM battle_vein_assets WHERE id=?", (winner_asset_id,)).fetchone() if winner_asset_id else None
    loser = conn.execute("SELECT * FROM battle_vein_assets WHERE id=?", (loser_asset_id,)).fetchone() if loser_asset_id else None
    if not loser:
        raise ValueError("A losing Vein asset is required")
    loser_side = conn.execute("SELECT * FROM battle_sides WHERE id=?", (loser["side_id"],)).fetchone()
    winner_side_id = int(winner["side_id"]) if winner else None

    stage_value = STAGE_WEIGHT[str(loser["stage_key"])]
    zone_value = float(zone["importance"]) / 100.0
    meta = json.loads(loser["metadata_json"] or "{}")
    command_factor = 1.35 if meta.get("command_role") in {"side_controller","zone_commander","critical_command"} else 1.0
    replacement = max(0.35, min(1.0, float(meta.get("replacement_depth", 0.7))))
    fragility = (100.0 - min(float(loser_side["morale"]),float(loser_side["cohesion"]))) / 100.0
    score = stage_value * zone_value * command_factor * (1.25 - 0.5*replacement) * (0.8 + 0.7*fragility)

    if score >= 18: scale = "strategic"
    elif score >= 9: scale = "operational"
    elif score >= 3.5: scale = "local"
    else: scale = "minor"

    morale_hit = {"minor":1.0,"local":4.0,"operational":8.0,"strategic":14.0}[scale]
    cohesion_hit = {"minor":0.5,"local":2.0,"operational":6.0,"strategic":10.0}[scale]
    momentum_hit = {"minor":1.0,"local":5.0,"operational":10.0,"strategic":18.0}[scale]
    conn.execute("UPDATE battle_vein_assets SET status='defeated',readiness=0 WHERE id=?", (loser_asset_id,))
    conn.execute("UPDATE battle_sides SET morale=?,cohesion=?,momentum=? WHERE id=?",
                 (_clamp(float(loser_side["morale"])-morale_hit),_clamp(float(loser_side["cohesion"])-cohesion_hit),
                  max(-100,min(100,float(loser_side["momentum"])-momentum_hit)),loser_side["id"]))

    # Exceptional cascade: a strategically important loss can break an already-fragile side.
    # The duel is the trigger, not a universal victory switch.
    post = conn.execute("SELECT morale,cohesion,status FROM battle_sides WHERE id=?", (loser_side["id"],)).fetchone()
    cascade = False
    if scale == "strategic" and min(float(post["morale"]),float(post["cohesion"])) < 16 and post["status"] in {"engaged","withdrawing"}:
        conn.execute("UPDATE battle_sides SET status='broken' WHERE id=?", (loser_side["id"],))
        cascade = True

    round_index = int(conn.execute("SELECT round_index FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()[0])
    effects = {"score":round(score,3),"morale_hit":morale_hit,"cohesion_hit":cohesion_hit,"momentum_hit":momentum_hit,"cascade":cascade}
    cur = conn.execute(
        """INSERT INTO battle_personal_consequences(
               engagement_id,round_index,zone_id,winner_side_id,loser_side_id,winner_asset_id,loser_asset_id,
               consequence_scale,summary_text,effects_json,created_day
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (engagement_id,round_index,zone_id,winner_side_id,loser["side_id"],winner_asset_id,loser_asset_id,
         scale,summary,json.dumps(effects,ensure_ascii=False),current_day(conn)),
    )
    return {"id":int(cur.lastrowid),"scale":scale,"cascade":cascade,"effects":effects}


def tactical_view(conn: sqlite3.Connection, engagement_id: int, actor_id: int, role: dict[str, Any]) -> dict[str, Any]:
    round_index = int(conn.execute("SELECT round_index FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()[0])
    own_side = role.get("side_id")
    own = None
    if own_side is not None:
        row = conn.execute("SELECT * FROM battle_tactical_choices WHERE engagement_id=? AND side_id=? AND round_index=? ORDER BY id DESC LIMIT 1",
                           (engagement_id,own_side,round_index)).fetchone()
        if row:
            own = {"family":row["family_key"],"focus_zone_id":row["focus_zone_id"],"status":row["status"]}
    # Enemy tactical family is not automatically exposed; it may only be inferred in prose from reports/evidence.
    assets = []
    if own_side is not None:
        rows = conn.execute("SELECT * FROM battle_vein_assets WHERE engagement_id=? AND side_id=? ORDER BY id", (engagement_id,own_side)).fetchall()
        assets = [{"asset_id":int(r["id"]),"stage":r["stage_key"],"role":r["battlefield_role"],"status":r["status"],
                   "zone_id":r["zone_id"],"readiness_band":"strong" if float(r["readiness"])>=65 else ("strained" if float(r["readiness"])>=30 else "spent"),
                   "reserve_band":"deep" if float(r["reserve"])>=65 else ("limited" if float(r["reserve"])>=30 else "low")} for r in rows]
    return {"own_tactical_family":own,"own_vein_assets":assets,
            "guardrail":"Enemy doctrine and exact Vein reserves remain hidden unless learned through ordinary information channels."}
