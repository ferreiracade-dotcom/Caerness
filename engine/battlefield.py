from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from .simulation import current_day


def _clamp(value: float, low: float = -100.0, high: float = 100.0) -> float:
    return round(max(low, min(high, float(value))), 3)


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (json.JSONDecodeError, TypeError):
        return default



def set_command_profile(conn: sqlite3.Connection, actor_id: int, *, planning: float = 50, adaptation: float = 50,
                        presence: float = 50, delegation: float = 50, nerve: float = 50, notes: str | None = None) -> None:
    if not conn.execute("SELECT 1 FROM actors WHERE id=?", (actor_id,)).fetchone():
        raise ValueError("Actor does not exist")
    vals = [max(0,min(100,float(v))) for v in (planning,adaptation,presence,delegation,nerve)]
    conn.execute(
        """INSERT INTO battle_command_profiles(actor_id,planning,adaptation,presence,delegation,nerve,notes,updated_at)
           VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(actor_id) DO UPDATE SET planning=excluded.planning,adaptation=excluded.adaptation,
           presence=excluded.presence,delegation=excluded.delegation,nerve=excluded.nerve,notes=excluded.notes,updated_at=CURRENT_TIMESTAMP""",
        (actor_id,*vals,notes),
    )


def command_profile(conn: sqlite3.Connection, actor_id: int | None) -> dict[str,float]:
    if actor_id is None:
        return {"planning":50.0,"adaptation":50.0,"presence":50.0,"delegation":50.0,"nerve":50.0}
    row = conn.execute("SELECT * FROM battle_command_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    if not row:
        return {"planning":50.0,"adaptation":50.0,"presence":50.0,"delegation":50.0,"nerve":50.0}
    return {k:float(row[k]) for k in ("planning","adaptation","presence","delegation","nerve")}

def add_battle_zone(conn: sqlite3.Connection, engagement_id: int, name: str, *, importance: float = 50,
                    metadata: dict[str, Any] | None = None) -> int:
    eng = conn.execute("SELECT engagement_kind FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng or eng[0] != "battle":
        raise ValueError("Battle engagement does not exist")
    cur = conn.execute(
        "INSERT INTO battle_zones(engagement_id,name,importance,metadata_json) VALUES (?,?,?,?)",
        (engagement_id, name, max(0.0, min(100.0, float(importance))), json.dumps(metadata or {}, ensure_ascii=False)),
    )
    return int(cur.lastrowid)


def ensure_default_zone(conn: sqlite3.Connection, engagement_id: int) -> int:
    row = conn.execute("SELECT id FROM battle_zones WHERE engagement_id=? ORDER BY id LIMIT 1", (engagement_id,)).fetchone()
    if row:
        return int(row[0])
    return add_battle_zone(conn, engagement_id, "Main Front", importance=60)


def assign_unit_to_zone(conn: sqlite3.Connection, unit_id: int, zone_id: int, *, assignment_kind: str = "primary",
                        assigned_round: int | None = None) -> None:
    if assignment_kind not in {"primary", "support", "reserve"}:
        raise ValueError("Invalid assignment kind")
    unit = conn.execute("SELECT u.id,s.engagement_id FROM battle_units u JOIN battle_sides s ON s.id=u.side_id WHERE u.id=?", (unit_id,)).fetchone()
    zone = conn.execute("SELECT id,engagement_id FROM battle_zones WHERE id=?", (zone_id,)).fetchone()
    if not unit or not zone or int(unit["engagement_id"]) != int(zone["engagement_id"]):
        raise ValueError("Unit and zone must belong to the same battle")
    if assigned_round is None:
        eng = conn.execute("SELECT round_index FROM combat_engagements WHERE id=?", (zone["engagement_id"],)).fetchone()
        assigned_round = int(eng[0]) if eng else 0
    conn.execute(
        "INSERT OR REPLACE INTO battle_unit_zones(unit_id,zone_id,assigned_round,assignment_kind) VALUES (?,?,?,?)",
        (unit_id, zone_id, int(assigned_round), assignment_kind),
    )


def auto_assign_unzoned_units(conn: sqlite3.Connection, engagement_id: int) -> int:
    zone_id = ensure_default_zone(conn, engagement_id)
    rows = conn.execute(
        """SELECT u.id,u.unit_role FROM battle_units u JOIN battle_sides s ON s.id=u.side_id
           LEFT JOIN battle_unit_zones z ON z.unit_id=u.id
           WHERE s.engagement_id=? AND z.unit_id IS NULL ORDER BY u.id""",
        (engagement_id,),
    ).fetchall()
    for row in rows:
        kind = "reserve" if row["unit_role"] == "reserve" else "primary"
        assign_unit_to_zone(conn, int(row["id"]), zone_id, assignment_kind=kind)
    return zone_id


def set_command_link(conn: sqlite3.Connection, engagement_id: int, side_id: int, *, senior_actor_id: int | None,
                     junior_actor_id: int | None = None, junior_unit_id: int | None = None,
                     authority_scope: str = "unit", communication_quality: float = 70,
                     discretion: float = 60, trust: float = 60) -> int:
    if authority_scope not in {"side", "zone", "unit"}:
        raise ValueError("Invalid authority scope")
    if junior_actor_id is None and junior_unit_id is None:
        raise ValueError("A command link needs a junior actor or unit")
    cur = conn.execute(
        """INSERT OR REPLACE INTO battle_command_links(
               engagement_id,side_id,senior_actor_id,junior_actor_id,junior_unit_id,authority_scope,
               communication_quality,discretion,trust,status
           ) VALUES (?,?,?,?,?,?,?,?,?,'active')""",
        (engagement_id, side_id, senior_actor_id, junior_actor_id, junior_unit_id, authority_scope,
         max(0,min(100,float(communication_quality))), max(0,min(100,float(discretion))), max(0,min(100,float(trust)))),
    )
    return int(cur.lastrowid)


def issue_battle_order(conn: sqlite3.Connection, engagement_id: int, side_id: int, directive_key: str, *,
                       issuer_actor_id: int | None = None, recipient_actor_id: int | None = None,
                       unit_id: int | None = None, zone_id: int | None = None,
                       priority: int = 2, objective: str | None = None) -> int:
    if directive_key not in {"hold","probe","press","support","reposition","recover","commit","disengage"}:
        raise ValueError("Invalid directive")
    eng = conn.execute("SELECT round_index FROM combat_engagements WHERE id=? AND engagement_kind='battle'", (engagement_id,)).fetchone()
    if not eng:
        raise ValueError("Battle does not exist")
    issued_round = int(eng[0])
    delay = 1
    link = None
    if unit_id is not None:
        link = conn.execute(
            """SELECT * FROM battle_command_links WHERE engagement_id=? AND side_id=? AND status='active'
               AND (junior_unit_id=? OR (? IS NOT NULL AND junior_actor_id=?)) ORDER BY id DESC LIMIT 1""",
            (engagement_id, side_id, unit_id, recipient_actor_id, recipient_actor_id),
        ).fetchone()
    if link:
        quality = float(link["communication_quality"])
        delay = 0 if quality >= 82 else (1 if quality >= 45 else 2)
    effective = issued_round + max(1, delay)
    cur = conn.execute(
        """INSERT INTO battle_orders(
               engagement_id,side_id,issuer_actor_id,recipient_actor_id,unit_id,zone_id,issued_round,effective_round,
               directive_key,priority,objective_text,status,created_day
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'issued',?)""",
        (engagement_id, side_id, issuer_actor_id, recipient_actor_id, unit_id, zone_id, issued_round, effective,
         directive_key, max(1,min(3,int(priority))), objective, current_day(conn)),
    )
    return int(cur.lastrowid)


def effective_order_for_unit(conn: sqlite3.Connection, engagement_id: int, unit_id: int, round_index: int) -> sqlite3.Row | None:
    row = conn.execute(
        """SELECT * FROM battle_orders WHERE engagement_id=? AND unit_id=? AND status IN ('issued','received')
           AND effective_round<=? ORDER BY priority DESC,effective_round DESC,id DESC LIMIT 1""",
        (engagement_id, unit_id, round_index),
    ).fetchone()
    if row and row["status"] == "issued":
        conn.execute("UPDATE battle_orders SET status='received' WHERE id=?", (row["id"],))
        row = conn.execute("SELECT * FROM battle_orders WHERE id=?", (row["id"],)).fetchone()
    return row


def _action_force(action: str) -> float:
    # Abstract narrative pressure only; not a real-world tactical model.
    return {
        "hold": 0.0, "probe": 1.0, "press": 5.0, "support": 2.5,
        "reposition": -0.5, "recover": -2.0, "commit": 7.0, "disengage": -4.0,
    }.get(action, 0.0)


def _band_pressure(p: float) -> str:
    a = abs(p)
    if a < 12: return "contested"
    if a < 32: return "leaning"
    return "decisive"


def _report_delay(info_quality: float, command_score: float = 50.0) -> int:
    effective = info_quality * 0.75 + command_score * 0.25
    if effective >= 78: return 0
    if effective >= 45: return 1
    return 2


def apply_battlefield_flow(conn: sqlite3.Connection, engagement_id: int, round_index: int, seed: int) -> dict[str, Any]:
    auto_assign_unzoned_units(conn, engagement_id)
    zones = conn.execute("SELECT * FROM battle_zones WHERE engagement_id=? AND status!='abandoned' ORDER BY id", (engagement_id,)).fetchall()
    sides = conn.execute("SELECT * FROM battle_sides WHERE engagement_id=? ORDER BY id", (engagement_id,)).fetchall()
    rng = random.Random(seed ^ 0x14B47)
    zone_results: list[dict[str, Any]] = []
    turning_points: list[dict[str, Any]] = []

    for zone in zones:
        previous = float(zone["pressure"])
        contributions: dict[int, float] = {}
        names: dict[int, str] = {}
        for side in sides:
            sid = int(side["id"]); names[sid] = str(side["name"])
            rows = conn.execute(
                """SELECT u.*,a.action_key,a.competence_score,z.assignment_kind FROM battle_units u
                   JOIN battle_unit_zones z ON z.unit_id=u.id
                   LEFT JOIN battle_unit_actions a ON a.unit_id=u.id AND a.engagement_id=? AND a.round_index=?
                   WHERE z.zone_id=? AND u.side_id=? AND u.status NOT IN ('disengaged','broken')""",
                (engagement_id, round_index, zone["id"], sid),
            ).fetchall()
            value = 0.0
            for u in rows:
                action = str(u["action_key"] or "hold")
                assignment_weight = {"primary": 1.0, "support": 0.72, "reserve": 0.35}.get(str(u["assignment_kind"]), 1.0)
                competence = float(u["competence_score"] or 35.0)
                value += assignment_weight * (
                    float(u["combat_capacity"]) * 0.23 + float(u["morale"]) * 0.14 + float(u["cohesion"]) * 0.14
                    + float(u["readiness"]) * 0.12 + (100-float(u["fatigue"])) * 0.08
                    + competence * 0.09 + _action_force(action)
                )
            contributions[sid] = value

        ranked = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)
        if len(ranked) >= 2:
            lead_sid, lead = ranked[0]
            second = ranked[1][1]
            delta = (lead-second) * 0.12 + rng.uniform(-3.0,3.0)
            # pressure sign is stable by lowest side id, allowing a compact two-side representation.
            sign = 1.0 if lead_sid == min(contributions) else -1.0
            new_pressure = _clamp(previous * 0.72 + sign * delta, -100, 100)
            initiative_side = lead_sid if abs(new_pressure) >= 8 else None
        else:
            lead_sid = ranked[0][0] if ranked else None
            new_pressure = previous * 0.8
            initiative_side = lead_sid

        control = _band_pressure(new_pressure)
        conn.execute("UPDATE battle_zones SET pressure=?,initiative_side_id=?,control_state=? WHERE id=?",
                     (new_pressure, initiative_side, control, zone["id"]))

        crossed = (abs(previous) < 30 <= abs(new_pressure)) or (previous * new_pressure < 0 and abs(new_pressure) >= 12)
        if crossed:
            kind = "local_crisis" if abs(new_pressure) >= 30 else "local_swing"
            significance = 3 if kind == "local_crisis" else 2
            summary = f"{zone['name']} shifted enough to change the local battle picture."
            cur = conn.execute(
                """INSERT INTO battle_turning_points(
                       engagement_id,round_index,zone_id,side_id,turning_kind,significance,summary_text,effects_json,created_day
                   ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (engagement_id, round_index, zone["id"], initiative_side, kind, significance, summary,
                 json.dumps({"pressure_before":previous,"pressure_after":new_pressure}, ensure_ascii=False), current_day(conn)),
            )
            turning_points.append({"id":int(cur.lastrowid),"kind":kind,"zone_id":int(zone["id"]),"significance":significance,"summary":summary})

        # Generate delayed side-controller reports. Reports describe local state without exposing exact enemy internals.
        for side in sides:
            recipient = side["controller_actor_id"]
            if recipient is None:
                continue
            info = float(side["information_quality"])
            profile = command_profile(conn, int(recipient))
            effective_info = max(0.0, min(100.0, info * 0.82 + profile["planning"] * 0.18))
            delay = _report_delay(effective_info)
            if initiative_side is None:
                summary = f"{zone['name']} remains broadly contested."
            elif int(initiative_side) == int(side["id"]):
                summary = f"Reports from {zone['name']} indicate improving local initiative."
            else:
                summary = f"Reports from {zone['name']} indicate growing local pressure."
            conn.execute(
                """INSERT INTO battle_reports(
                       engagement_id,side_id,recipient_actor_id,zone_id,observed_round,available_round,confidence,report_kind,
                       summary_text,payload_json,created_day
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (engagement_id, side["id"], recipient, zone["id"], round_index, round_index+delay,
                 max(15,min(95,effective_info)), "situation", summary,
                 json.dumps({"zone_name":zone["name"],"control_state":control}, ensure_ascii=False), current_day(conn)),
            )

        zone_results.append({
            "zone_id": int(zone["id"]), "name": zone["name"], "importance": float(zone["importance"]),
            "control_state": control, "initiative_side_id": initiative_side,
            "pressure_band": "strong" if abs(new_pressure) >= 55 else ("meaningful" if abs(new_pressure) >= 25 else "limited"),
        })

    # Phase emerges from duration + local crises rather than fixed boss-style scripting.
    crises = sum(1 for z in zone_results if z["control_state"] == "decisive")
    active_sides = conn.execute("SELECT COUNT(*) FROM battle_sides WHERE engagement_id=? AND status IN ('engaged','withdrawing')", (engagement_id,)).fetchone()[0]
    if active_sides <= 1:
        phase = "aftermath"
    elif crises >= max(1, len(zone_results)//2) and round_index >= 2:
        phase = "crisis"
    elif round_index <= 1:
        phase = "opening"
    elif round_index <= 3:
        phase = "developing"
    else:
        phase = "contested"
    conn.execute("UPDATE combat_engagements SET phase=? WHERE id=?", (phase, engagement_id))

    return {"zones": zone_results, "turning_points": turning_points, "phase": phase}


def local_shock(conn: sqlite3.Connection, engagement_id: int, zone_id: int, side_id: int, *, magnitude: float,
                source: str = "local_event", summary: str = "A notable local event affected confidence nearby.") -> int:
    """Apply an abstract local morale/initiative shock. It is intentionally bounded and never resolves a whole battle by itself."""
    mag = max(-20.0, min(20.0, float(magnitude)))
    zone = conn.execute("SELECT * FROM battle_zones WHERE id=? AND engagement_id=?", (zone_id, engagement_id)).fetchone()
    if not zone:
        raise ValueError("Battle zone does not exist")
    units = conn.execute(
        """SELECT u.id,u.side_id,u.morale,u.cohesion FROM battle_units u JOIN battle_unit_zones z ON z.unit_id=u.id
           WHERE z.zone_id=? AND u.status NOT IN ('disengaged','broken')""", (zone_id,)).fetchall()
    for u in units:
        aligned = int(u["side_id"]) == int(side_id)
        delta = mag if aligned else -mag * 0.55
        conn.execute("UPDATE battle_units SET morale=? WHERE id=?", (max(0,min(100,float(u["morale"])+delta)), u["id"]))
    round_index = conn.execute("SELECT round_index FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()[0]
    cur = conn.execute(
        """INSERT INTO battle_turning_points(
               engagement_id,round_index,zone_id,side_id,turning_kind,significance,summary_text,effects_json,created_day
           ) VALUES (?,?,?,?, 'morale_surge',2,?,?,?)""",
        (engagement_id, round_index, zone_id, side_id, summary,
         json.dumps({"magnitude":mag,"source":source}, ensure_ascii=False), current_day(conn)),
    )
    return int(cur.lastrowid)


def battlefield_view(conn: sqlite3.Connection, engagement_id: int, actor_id: int, *, role: dict[str, Any] | None = None) -> dict[str, Any]:
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng:
        raise ValueError("Battle does not exist")
    if role is None:
        role = {"role":"observer","side_id":None,"unit_id":None}
    current_round = int(eng["round_index"])
    zone_rows = conn.execute("SELECT * FROM battle_zones WHERE engagement_id=? ORDER BY id", (engagement_id,)).fetchall()
    own_zone_ids: set[int] = set()
    if role.get("unit_id") is not None:
        r = conn.execute("SELECT zone_id FROM battle_unit_zones WHERE unit_id=?", (role["unit_id"],)).fetchone()
        if r: own_zone_ids.add(int(r[0]))

    zones = []
    for z in zone_rows:
        item = {"zone_id":int(z["id"]),"name":z["name"],"importance":"major" if float(z["importance"])>=70 else ("meaningful" if float(z["importance"])>=40 else "limited")}
        if role.get("role") == "unit_commander" and int(z["id"]) not in own_zone_ids:
            item["knowledge"] = "outside immediate local picture"
        elif role.get("role") == "side_controller":
            report = conn.execute(
                """SELECT * FROM battle_reports WHERE engagement_id=? AND recipient_actor_id=? AND zone_id=? AND available_round<=?
                   ORDER BY observed_round DESC,id DESC LIMIT 1""", (engagement_id,actor_id,z["id"],current_round)).fetchone()
            if report:
                item.update({"knowledge":"reported","report":report["summary_text"],"confidence":"high" if float(report["confidence"])>=75 else ("moderate" if float(report["confidence"])>=45 else "low")})
            else:
                item["knowledge"] = "report pending or unavailable"
        else:
            item["knowledge"] = "local" if int(z["id"]) in own_zone_ids else "limited"
        zones.append(item)

    orders = []
    if role.get("unit_id") is not None:
        rows = conn.execute(
            """SELECT * FROM battle_orders WHERE engagement_id=? AND unit_id=? AND effective_round<=? ORDER BY id DESC LIMIT 5""",
            (engagement_id,role["unit_id"],current_round+1),
        ).fetchall()
        orders = [{"directive":r["directive_key"],"objective":r["objective_text"],"status":r["status"],"effective_round":int(r["effective_round"])} for r in rows]
    return {"zones":zones,"received_or_pending_orders":orders,"information_rule":"Reports are delayed and partial; this view never substitutes for objective battle state."}
