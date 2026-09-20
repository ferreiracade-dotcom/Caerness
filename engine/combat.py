from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from .simulation import current_day
from .battlefield import effective_order_for_unit, apply_battlefield_flow, battlefield_view, ensure_default_zone, auto_assign_unzoned_units
from .battle_tactics import apply_tactical_layer, tactical_view, apply_personal_combat_consequence

BATTLE_INTENTS = {"hold", "probe", "press", "reposition", "reinforce", "commit_reserve", "recover", "disengage"}
DUEL_INTENTS = {"measure", "press", "defend", "conserve", "commit", "control", "disengage"}
RISK = {"low", "balanced", "high"}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, float(value))), 3)


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (json.JSONDecodeError, TypeError):
        return default


def _actor_exists(conn: sqlite3.Connection, actor_id: int) -> None:
    if not conn.execute("SELECT 1 FROM actors WHERE id=?", (actor_id,)).fetchone():
        raise ValueError(f"Actor #{actor_id} does not exist")


def _competence(conn: sqlite3.Connection, actor_id: int | None, domain_key: str, default: float = 35.0) -> float:
    if actor_id is None:
        return default
    row = conn.execute(
        """SELECT ac.score FROM actor_competence ac
           JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key=?
           ORDER BY CASE WHEN ac.specialty IS NULL THEN 0 ELSE 1 END, ac.score DESC LIMIT 1""",
        (actor_id, domain_key),
    ).fetchone()
    return float(row[0]) if row else default


def _world_seed(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()
    return int(row[0]) if row else 812197


def _round_seed(conn: sqlite3.Connection, engagement_id: int, round_index: int, salt: int = 0) -> int:
    # Stable per-round seed: prose regeneration and repeated reads never reroll combat truth.
    return (_world_seed(conn) * 1000003 + engagement_id * 9176 + round_index * 131 + salt) & 0x7FFFFFFF


def _band(value: float, *, labels: tuple[str, str, str, str, str] = ("critical", "strained", "steady", "strong", "dominant")) -> str:
    if value < 20:
        return labels[0]
    if value < 40:
        return labels[1]
    if value < 65:
        return labels[2]
    if value < 85:
        return labels[3]
    return labels[4]


def create_battle(
    conn: sqlite3.Connection,
    title: str,
    *,
    location_id: int | None = None,
    player_actor_id: int | None = None,
    objective: str | None = None,
    stakes: int = 3,
    metadata: dict[str, Any] | None = None,
) -> int:
    if player_actor_id is not None:
        _actor_exists(conn, player_actor_id)
    day = current_day(conn)
    cur = conn.execute(
        """INSERT INTO combat_engagements(
               engagement_kind,title,location_id,player_actor_id,objective_text,stakes,status,phase,round_index,day_started,metadata_json
           ) VALUES ('battle',?,?,?,?,?,'prepared','opening',0,?,?)""",
        (title, location_id, player_actor_id, objective, max(1, min(5, int(stakes))), day,
         json.dumps(metadata or {}, ensure_ascii=False)),
    )
    return int(cur.lastrowid)


def add_battle_side(
    conn: sqlite3.Connection,
    engagement_id: int,
    name: str,
    *,
    controller_actor_id: int | None = None,
    objective: str | None = None,
    posture: str = "balanced",
    morale: float = 70,
    cohesion: float = 70,
    logistics: float = 70,
    information_quality: float = 50,
    reserve_capacity: float = 50,
    metadata: dict[str, Any] | None = None,
) -> int:
    eng = conn.execute("SELECT engagement_kind,status FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng or eng["engagement_kind"] != "battle":
        raise ValueError("Battle engagement does not exist")
    if controller_actor_id is not None:
        _actor_exists(conn, controller_actor_id)
    if posture not in {"cautious", "balanced", "assertive"}:
        raise ValueError("Invalid battle posture")
    cur = conn.execute(
        """INSERT INTO battle_sides(
               engagement_id,name,controller_actor_id,objective_text,posture,morale,cohesion,logistics,information_quality,reserve_capacity,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (engagement_id, name, controller_actor_id, objective, posture, _clamp(morale), _clamp(cohesion),
         _clamp(logistics), _clamp(information_quality), _clamp(reserve_capacity), json.dumps(metadata or {}, ensure_ascii=False)),
    )
    conn.execute("UPDATE combat_engagements SET status='active' WHERE id=? AND status='prepared'", (engagement_id,))
    return int(cur.lastrowid)


def add_battle_unit(
    conn: sqlite3.Connection,
    side_id: int,
    name: str,
    *,
    commander_actor_id: int | None = None,
    unit_role: str = "line",
    combat_capacity: float = 70,
    morale: float = 70,
    cohesion: float = 70,
    fatigue: float = 10,
    readiness: float = 70,
    metadata: dict[str, Any] | None = None,
) -> int:
    if unit_role not in {"line", "support", "reserve", "specialist", "command"}:
        raise ValueError("Invalid unit role")
    if not conn.execute("SELECT 1 FROM battle_sides WHERE id=?", (side_id,)).fetchone():
        raise ValueError("Battle side does not exist")
    if commander_actor_id is not None:
        _actor_exists(conn, commander_actor_id)
    cur = conn.execute(
        """INSERT INTO battle_units(
               side_id,name,commander_actor_id,unit_role,combat_capacity,morale,cohesion,fatigue,readiness,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (side_id, name, commander_actor_id, unit_role, _clamp(combat_capacity), _clamp(morale), _clamp(cohesion),
         _clamp(fatigue), _clamp(readiness), json.dumps(metadata or {}, ensure_ascii=False)),
    )
    return int(cur.lastrowid)


def _battle_role(conn: sqlite3.Connection, engagement_id: int, actor_id: int) -> dict[str, Any]:
    side = conn.execute(
        "SELECT * FROM battle_sides WHERE engagement_id=? AND controller_actor_id=? LIMIT 1",
        (engagement_id, actor_id),
    ).fetchone()
    if side:
        return {"role": "side_controller", "side_id": int(side["id"]), "unit_id": None}
    unit = conn.execute(
        """SELECT u.*,s.engagement_id FROM battle_units u JOIN battle_sides s ON s.id=u.side_id
           WHERE s.engagement_id=? AND u.commander_actor_id=? ORDER BY u.id LIMIT 1""",
        (engagement_id, actor_id),
    ).fetchone()
    if unit:
        return {"role": "unit_commander", "side_id": int(unit["side_id"]), "unit_id": int(unit["id"])}
    return {"role": "observer", "side_id": None, "unit_id": None}


def submit_battle_intent(
    conn: sqlite3.Connection,
    engagement_id: int,
    actor_id: int,
    intent_key: str,
    *,
    unit_id: int | None = None,
    risk_level: str = "balanced",
    commitment: float = 0.5,
    objective: str | None = None,
    source_kind: str = "player",
) -> int:
    if intent_key not in BATTLE_INTENTS:
        raise ValueError(f"Unknown battle intent: {intent_key}")
    if risk_level not in RISK:
        raise ValueError("Invalid risk level")
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng or eng["engagement_kind"] != "battle" or eng["status"] not in {"active", "prepared"}:
        raise ValueError("Battle is not active")
    role = _battle_role(conn, engagement_id, actor_id)
    if role["role"] == "observer":
        raise ValueError("Actor has no command role in this battle")
    if role["role"] == "unit_commander":
        unit_id = role["unit_id"]
    elif unit_id is not None:
        unit = conn.execute("SELECT side_id FROM battle_units WHERE id=?", (unit_id,)).fetchone()
        if not unit or int(unit["side_id"]) != int(role["side_id"]):
            raise ValueError("Unit is not under this side controller")
    round_index = int(eng["round_index"]) + 1
    if unit_id is None:
        # SQLite treats NULLs as distinct in UNIQUE constraints; explicitly replace the current side-level intent.
        conn.execute(
            "DELETE FROM battle_intents WHERE engagement_id=? AND actor_id=? AND round_index=? AND unit_id IS NULL",
            (engagement_id, actor_id, round_index),
        )
    cur = conn.execute(
        """INSERT OR REPLACE INTO battle_intents(
               engagement_id,side_id,actor_id,unit_id,round_index,intent_key,risk_level,commitment,objective_text,source_kind,status,result_json,created_day
           ) VALUES (?,?,?,?,?,?,?,?,?,?, 'submitted','{}',?)""",
        (engagement_id, int(role["side_id"]), actor_id, unit_id, round_index, intent_key, risk_level,
         max(0.0, min(1.0, float(commitment))), objective, source_kind, current_day(conn)),
    )
    return int(cur.lastrowid)


def _npc_side_intent(conn: sqlite3.Connection, side: sqlite3.Row, round_index: int) -> dict[str, Any]:
    morale = float(side["morale"])
    cohesion = float(side["cohesion"])
    reserve = float(side["reserve_capacity"])
    posture = str(side["posture"])
    if morale < 22 or cohesion < 20:
        intent = "disengage"
        risk = "low"
        commitment = 0.35
    elif morale < 40 or cohesion < 40:
        intent = "hold" if posture != "assertive" else "reinforce"
        risk = "low"
        commitment = 0.45
    elif reserve > 55 and posture == "assertive" and round_index >= 2:
        intent = "commit_reserve"
        risk = "high"
        commitment = 0.75
    elif posture == "assertive":
        intent = "press"
        risk = "high"
        commitment = 0.7
    elif posture == "cautious":
        intent = "probe"
        risk = "low"
        commitment = 0.4
    else:
        intent = "probe" if round_index <= 1 else "press"
        risk = "balanced"
        commitment = 0.55
    return {"intent_key": intent, "risk_level": risk, "commitment": commitment, "source_kind": "npc_rules"}


def _ensure_side_intent(conn: sqlite3.Connection, engagement_id: int, side: sqlite3.Row, round_index: int) -> sqlite3.Row:
    controller = side["controller_actor_id"]
    if controller is not None:
        row = conn.execute(
            """SELECT * FROM battle_intents WHERE engagement_id=? AND side_id=? AND actor_id=? AND round_index=? AND unit_id IS NULL
               ORDER BY id DESC LIMIT 1""",
            (engagement_id, side["id"], controller, round_index),
        ).fetchone()
        if row:
            return row
    # No controller or no submitted side-level command: create an NPC/rules intent.
    choice = _npc_side_intent(conn, side, round_index)
    actor_id = int(controller) if controller is not None else _fallback_actor_for_side(conn, int(side["id"]))
    cur = conn.execute(
        """INSERT INTO battle_intents(
               engagement_id,side_id,actor_id,unit_id,round_index,intent_key,risk_level,commitment,source_kind,status,result_json,created_day
           ) VALUES (?,?,?,NULL,?,?,?,?,?, 'submitted','{}',?)""",
        (engagement_id, side["id"], actor_id, round_index, choice["intent_key"], choice["risk_level"], choice["commitment"],
         choice["source_kind"], current_day(conn)),
    )
    return conn.execute("SELECT * FROM battle_intents WHERE id=?", (cur.lastrowid,)).fetchone()


def _fallback_actor_for_side(conn: sqlite3.Connection, side_id: int) -> int:
    row = conn.execute("SELECT commander_actor_id FROM battle_units WHERE side_id=? AND commander_actor_id IS NOT NULL ORDER BY id LIMIT 1", (side_id,)).fetchone()
    if row:
        return int(row[0])
    # Anonymous command is represented by an existing institutional actor if present; if none exists, create a battle-local institution.
    side = conn.execute("SELECT name,engagement_id FROM battle_sides WHERE id=?", (side_id,)).fetchone()
    name = f"[COMBAT] {side['name']} command {side['engagement_id']}"
    existing = conn.execute("SELECT id FROM actors WHERE name=?", (name,)).fetchone()
    if existing:
        return int(existing[0])
    cur = conn.execute("INSERT INTO actors(name,actor_type,subtype,status,notes,is_demo) VALUES (?,'institution','battle_command','active','Generated battle command identity',1)", (name,))
    return int(cur.lastrowid)


def _risk_mod(risk: str) -> tuple[float, float]:
    # impact modifier, exposure/fatigue modifier
    return {"low": (-4.0, -2.0), "balanced": (0.0, 0.0), "high": (6.0, 5.0)}[risk]


def _intent_mod(intent: str) -> dict[str, float]:
    return {
        "hold": {"power": 1, "morale": 1, "cohesion": 2, "fatigue": 1, "reserve": 0},
        "probe": {"power": -1, "morale": 0, "cohesion": 1, "fatigue": 2, "reserve": 0},
        "press": {"power": 7, "morale": 0, "cohesion": -1, "fatigue": 5, "reserve": 0},
        "reposition": {"power": -3, "morale": 0, "cohesion": 3, "fatigue": 2, "reserve": 0},
        "reinforce": {"power": 4, "morale": 2, "cohesion": 3, "fatigue": 2, "reserve": -6},
        "commit_reserve": {"power": 10, "morale": 2, "cohesion": 0, "fatigue": 5, "reserve": -14},
        "recover": {"power": -8, "morale": 2, "cohesion": 3, "fatigue": -6, "reserve": 1},
        "disengage": {"power": -10, "morale": 0, "cohesion": 1, "fatigue": 2, "reserve": 0},
    }[intent]


def _unit_action_for(conn: sqlite3.Connection, engagement_id: int, side: sqlite3.Row, unit: sqlite3.Row, side_intent: sqlite3.Row, round_index: int) -> tuple[str, str, float]:
    commander = unit["commander_actor_id"]
    if commander is not None:
        explicit = conn.execute(
            """SELECT * FROM battle_intents WHERE engagement_id=? AND actor_id=? AND round_index=? AND unit_id=? ORDER BY id DESC LIMIT 1""",
            (engagement_id, commander, round_index, unit["id"]),
        ).fetchone()
        if explicit:
            return str(explicit["intent_key"]), "unit_intent", _competence(conn, int(commander), "command")
    order = effective_order_for_unit(conn, engagement_id, int(unit["id"]), round_index)
    if order is not None:
        competence = _competence(conn, int(commander) if commander is not None else None, "command")
        link = conn.execute(
            """SELECT * FROM battle_command_links WHERE engagement_id=? AND junior_unit_id=? AND status='active'
               ORDER BY id DESC LIMIT 1""", (engagement_id, unit["id"])
        ).fetchone()
        discretion = float(link["discretion"]) if link else 40.0
        # Subordinate initiative is bounded: a capable commander may adapt an order when local
        # conditions have materially changed, but does not rewrite the senior objective at whim.
        if discretion >= 55 and competence >= 50:
            if float(unit["fatigue"]) > 82 or float(unit["morale"]) < 22:
                if str(order["directive_key"]) in {"press", "commit"}:
                    return "recover", "commander_judgment", competence
        return str(order["directive_key"]), "received_order", competence
    competence = _competence(conn, int(commander) if commander is not None else None, "command")
    fatigue = float(unit["fatigue"])
    morale = float(unit["morale"])
    base = str(side_intent["intent_key"])
    if fatigue > 78 or morale < 25:
        return ("recover" if base != "disengage" else "disengage"), "commander_judgment", competence
    if unit["unit_role"] == "reserve" and base not in {"commit_reserve", "reinforce", "disengage"}:
        return "hold", "side_intent", competence
    mapping = {"reinforce": "support", "commit_reserve": "commit"}
    return mapping.get(base, base), "side_intent", competence



def _unit_zone_modifier(conn: sqlite3.Connection, engagement_id: int, unit_id: int, side_id: int) -> float:
    """Convert previously established/local tactical pressure into current-round leverage.

    Battle-zone pressure is a structural abstraction, not real formation geometry. A unit assigned
    to a front benefits when its side holds local initiative and suffers when the opposing side does.
    This is what makes v0.14/v0.15 fronts and tactical choices causally affect the authoritative
    battle resolver rather than existing only as post-hoc narration metadata.
    """
    rows = conn.execute(
        """SELECT z.pressure,z.initiative_side_id,uz.assignment_kind
           FROM battle_unit_zones uz
           JOIN battle_zones z ON z.id=uz.zone_id
           WHERE uz.unit_id=? AND z.engagement_id=? AND z.status!='abandoned'""",
        (unit_id, engagement_id),
    ).fetchall()
    if not rows:
        return 0.0
    side_ids = [int(r[0]) for r in conn.execute(
        "SELECT id FROM battle_sides WHERE engagement_id=? ORDER BY id", (engagement_id,)
    ).fetchall()]
    total = 0.0
    weight_sum = 0.0
    for row in rows:
        weight = {"primary": 1.0, "support": 0.65, "reserve": 0.30}.get(str(row["assignment_kind"]), 1.0)
        pressure = float(row["pressure"])
        initiative = row["initiative_side_id"]
        if len(side_ids) == 2 and abs(pressure) >= 1.0:
            # The zone pressure scalar uses positive for the lower side id and negative for the
            # other side. Use the live pressure first so a current-round tactical choice can alter
            # current-round leverage before the post-round initiative marker is recomputed.
            favored = side_ids[0] if pressure > 0 else side_ids[1]
            aligned = 1.0 if int(favored) == int(side_id) else -1.0
        elif initiative is not None:
            aligned = 1.0 if int(initiative) == int(side_id) else -1.0
        else:
            aligned = 0.0
        total += aligned * min(10.0, abs(pressure) * 0.10) * weight
        weight_sum += weight
    return total / max(1.0, weight_sum)


def _unit_power(unit: sqlite3.Row, command_score: float, action: str, side: sqlite3.Row, risk: str, rng: random.Random) -> float:
    action_power = {
        "hold": 0, "probe": -1, "press": 6, "support": 3, "reposition": -2,
        "recover": -8, "commit": 9, "disengage": -10,
    }[action]
    risk_power, _ = _risk_mod(risk)
    value = (
        float(unit["combat_capacity"]) * 0.32
        + float(unit["morale"]) * 0.14
        + float(unit["cohesion"]) * 0.14
        + float(unit["readiness"]) * 0.13
        + (100 - float(unit["fatigue"])) * 0.08
        + command_score * 0.11
        + float(side["logistics"]) * 0.04
        + float(side["momentum"]) * 0.04
        + action_power + risk_power
        + rng.uniform(-4.0, 4.0)
    )
    return max(0.0, value)


def _battle_player_requirement(conn: sqlite3.Connection, engagement_id: int, round_index: int) -> dict[str, Any] | None:
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    player = eng["player_actor_id"] if eng else None
    if player is None:
        return None
    role = _battle_role(conn, engagement_id, int(player))
    if role["role"] == "side_controller":
        row = conn.execute(
            """SELECT 1 FROM battle_intents WHERE engagement_id=? AND actor_id=? AND round_index=? AND unit_id IS NULL""",
            (engagement_id, player, round_index),
        ).fetchone()
        if not row:
            return {"needs_player": True, "role": "side_controller", "round_index": round_index, "reason": "A strategic intent is required before this battle round can resolve."}
    elif role["role"] == "unit_commander":
        row = conn.execute(
            """SELECT 1 FROM battle_intents WHERE engagement_id=? AND actor_id=? AND round_index=? AND unit_id=?""",
            (engagement_id, player, round_index, role["unit_id"]),
        ).fetchone()
        if not row:
            return {"needs_player": True, "role": "unit_commander", "unit_id": role["unit_id"], "round_index": round_index, "reason": "A local unit intent is required before this battle round can resolve."}
    return None


def _resolve_battle_round_base(conn: sqlite3.Connection, engagement_id: int) -> dict[str, Any]:
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng or eng["engagement_kind"] != "battle":
        raise ValueError("Battle does not exist")
    if eng["status"] == "resolved":
        return {"status": "resolved", "engagement_id": engagement_id, "outcome": _jload(eng["outcome_json"], {})}
    if eng["status"] == "cancelled":
        raise ValueError("Battle is cancelled")
    sides = conn.execute("SELECT * FROM battle_sides WHERE engagement_id=? AND status IN ('engaged','withdrawing') ORDER BY id", (engagement_id,)).fetchall()
    if len(sides) < 2:
        raise ValueError("Battle requires at least two active sides")
    round_index = int(eng["round_index"]) + 1
    existing = conn.execute("SELECT summary_json FROM battle_rounds WHERE engagement_id=? AND round_index=?", (engagement_id, round_index)).fetchone()
    if existing:
        return _jload(existing[0], {})
    requirement = _battle_player_requirement(conn, engagement_id, round_index)
    if requirement:
        return requirement

    seed = _round_seed(conn, engagement_id, round_index, 13)
    rng = random.Random(seed)
    side_results: dict[int, dict[str, Any]] = {}
    powers: dict[int, float] = {}

    # First derive all side and subordinate actions before mutating state.
    derived: dict[int, dict[str, Any]] = {}
    for side in sides:
        side_intent = _ensure_side_intent(conn, engagement_id, side, round_index)
        units = conn.execute("SELECT * FROM battle_units WHERE side_id=? AND status NOT IN ('disengaged','broken') ORDER BY id", (side["id"],)).fetchall()
        actions = []
        unit_powers = []
        for unit in units:
            action, source, command_score = _unit_action_for(conn, engagement_id, side, unit, side_intent, round_index)
            power = _unit_power(unit, command_score, action, side, str(side_intent["risk_level"]), rng)
            power += _unit_zone_modifier(conn, engagement_id, int(unit["id"]), int(side["id"]))
            unit_powers.append(power)
            actions.append((unit, action, source, command_score, power))
        avg_power = sum(unit_powers) / max(1, len(unit_powers))
        controller_score = _competence(conn, int(side["controller_actor_id"]) if side["controller_actor_id"] is not None else None, "command")
        mod = _intent_mod(str(side_intent["intent_key"]))
        risk_power, _ = _risk_mod(str(side_intent["risk_level"]))
        aggregate = avg_power + controller_score * 0.06 + mod["power"] + risk_power + float(side["information_quality"]) * 0.03
        powers[int(side["id"])] = aggregate
        derived[int(side["id"])] = {"side": side, "intent": side_intent, "actions": actions, "aggregate": aggregate}

    for side_id, item in derived.items():
        side = item["side"]
        side_intent = item["intent"]
        opponents = [v for k, v in powers.items() if k != side_id]
        opposition = sum(opponents) / max(1, len(opponents))
        swing = item["aggregate"] - opposition + rng.uniform(-5.0, 5.0)
        mod = _intent_mod(str(side_intent["intent_key"]))
        _, risk_exposure = _risk_mod(str(side_intent["risk_level"]))

        morale_delta = swing * 0.075 + mod["morale"]
        cohesion_delta = swing * 0.055 + mod["cohesion"]
        momentum_delta = swing * 0.18
        reserve_delta = mod["reserve"] * float(side_intent["commitment"])
        new_morale = _clamp(float(side["morale"]) + morale_delta)
        new_cohesion = _clamp(float(side["cohesion"]) + cohesion_delta)
        new_momentum = _clamp(float(side["momentum"]) + momentum_delta, -100, 100)
        new_reserve = _clamp(float(side["reserve_capacity"]) + reserve_delta)

        intent_key = str(side_intent["intent_key"])
        status = str(side["status"])
        if intent_key == "disengage":
            # Cohesive forces can generally execute an orderly withdrawal; badly disrupted ones may break instead.
            status = "withdrawn" if new_cohesion >= 24 and new_morale >= 20 else "broken"
        elif new_morale < 14 or new_cohesion < 14:
            status = "broken"
        elif new_morale < 28 or new_cohesion < 28:
            status = "withdrawing"
        else:
            status = "engaged"

        conn.execute(
            "UPDATE battle_sides SET morale=?,cohesion=?,reserve_capacity=?,momentum=?,status=? WHERE id=?",
            (new_morale, new_cohesion, new_reserve, new_momentum, status, side_id),
        )

        action_summaries = []
        for unit, action, source, command_score, unit_power in item["actions"]:
            fatigue_change = max(-8.0, mod["fatigue"] + risk_exposure + {"recover": -8, "disengage": 1, "hold": 0}.get(action, 2))
            readiness_change = swing * 0.03 + (3 if action in {"support", "hold", "recover"} else 0) - max(0, fatigue_change) * 0.15
            capacity_change = min(0.0, swing * 0.035) - (1.5 if action in {"press", "commit"} and swing < 0 else 0)
            unit_morale = _clamp(float(unit["morale"]) + morale_delta * 0.7)
            unit_cohesion = _clamp(float(unit["cohesion"]) + cohesion_delta * 0.7)
            unit_fatigue = _clamp(float(unit["fatigue"]) + fatigue_change)
            unit_readiness = _clamp(float(unit["readiness"]) + readiness_change)
            unit_capacity = _clamp(float(unit["combat_capacity"]) + capacity_change)
            unit_status = "broken" if unit_morale < 15 or unit_cohesion < 15 else ("strained" if unit_morale < 35 or unit_fatigue > 75 else "engaged")
            if status in {"withdrawn", "broken"}:
                unit_status = "disengaged" if status == "withdrawn" else "broken"
            conn.execute(
                """UPDATE battle_units SET combat_capacity=?,morale=?,cohesion=?,fatigue=?,readiness=?,commitment=?,status=? WHERE id=?""",
                (unit_capacity, unit_morale, unit_cohesion, unit_fatigue, unit_readiness,
                 _clamp(float(unit["commitment"]) + float(side_intent["commitment"]) * 10), unit_status, unit["id"]),
            )
            result = {
                "power_band": _band(unit_power),
                "capacity_band": _band(unit_capacity),
                "morale_band": _band(unit_morale),
                "cohesion_band": _band(unit_cohesion),
                "fatigue_band": _band(100 - unit_fatigue, labels=("exhausted", "tired", "working", "fresh", "very_fresh")),
            }
            conn.execute(
                """INSERT INTO battle_unit_actions(
                       engagement_id,side_id,unit_id,commander_actor_id,round_index,action_key,autonomy_source,competence_score,result_json,created_day
                   ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (engagement_id, side_id, unit["id"], unit["commander_actor_id"], round_index, action, source,
                 command_score, json.dumps(result, ensure_ascii=False), current_day(conn)),
            )
            action_summaries.append({"unit_id": int(unit["id"]), "action": action, **result})

        result = {
            "side_id": side_id,
            "name": side["name"],
            "intent": intent_key,
            "risk": side_intent["risk_level"],
            "swing": round(swing, 3),
            "morale_band": _band(new_morale),
            "cohesion_band": _band(new_cohesion),
            "reserve_band": _band(new_reserve),
            "momentum": round(new_momentum, 3),
            "status": status,
            "unit_actions": action_summaries,
        }
        side_results[side_id] = result
        conn.execute(
            "UPDATE battle_intents SET status='resolved',result_json=? WHERE id=?",
            (json.dumps(result, ensure_ascii=False), side_intent["id"]),
        )

    active_after = conn.execute("SELECT * FROM battle_sides WHERE engagement_id=? AND status IN ('engaged','withdrawing') ORDER BY id", (engagement_id,)).fetchall()
    resolved = len(active_after) <= 1
    outcome: dict[str, Any] = {}
    if resolved:
        remaining = active_after[0] if active_after else None
        if remaining:
            conn.execute("UPDATE battle_sides SET status='victorious' WHERE id=?", (remaining["id"],))
            outcome = {"winner_side_id": int(remaining["id"]), "winner": remaining["name"], "resolution": "field_control"}
        else:
            outcome = {"winner_side_id": None, "winner": None, "resolution": "mutual_disengagement"}
        conn.execute("UPDATE combat_engagements SET status='resolved',phase='aftermath',round_index=?,day_ended=?,outcome_json=? WHERE id=?",
                     (round_index, current_day(conn), json.dumps(outcome, ensure_ascii=False), engagement_id))
    else:
        phase = "developing" if round_index <= 2 else "contested"
        conn.execute("UPDATE combat_engagements SET status='active',phase=?,round_index=? WHERE id=?", (phase, round_index, engagement_id))

    summary = {
        "engagement_id": engagement_id,
        "kind": "battle",
        "round_index": round_index,
        "status": "resolved" if resolved else "active",
        "phase": "aftermath" if resolved else ("developing" if round_index <= 2 else "contested"),
        "sides": list(side_results.values()),
        "outcome": outcome,
    }
    conn.execute("INSERT INTO battle_rounds(engagement_id,round_index,day,summary_json,seed) VALUES (?,?,?,?,?)",
                 (engagement_id, round_index, current_day(conn), json.dumps(summary, ensure_ascii=False), seed))
    event_title = f"Battle round {round_index}: {eng['title']}"
    event_summary = "Battle conditions changed through command decisions, unit cohesion, morale, reserves, and subordinate execution."
    conn.execute("INSERT INTO events(day,event_type,title,summary,severity,location_id,source_actor_id) VALUES (?,?,?,?,?,?,NULL)",
                 (current_day(conn), "battle_round", event_title, event_summary, min(5, max(2, int(eng["stakes"]))), eng["location_id"]))
    return summary


def resolve_battle_round(conn: sqlite3.Connection, engagement_id: int) -> dict[str, Any]:
    """Resolve one authoritative battle round with tactics and fronts inside causality.

    v0.15.1 audit hardening corrects an ordering flaw in v0.14/v0.15: tactical/front state
    must shape the same authoritative round, not merely be appended after the base resolver.
    Tactical choices are therefore applied before unit/side power is calculated; existing zone
    pressure feeds unit power; the multi-front flow pass then records the new local result and
    delayed reports after the round resolves.
    """
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng or eng["engagement_kind"] != "battle":
        raise ValueError("Battle does not exist")
    if eng["status"] == "resolved":
        return {"status": "resolved", "engagement_id": engagement_id, "outcome": _jload(eng["outcome_json"], {})}

    round_index = int(eng["round_index"]) + 1
    existing = conn.execute("SELECT summary_json FROM battle_rounds WHERE engagement_id=? AND round_index=?", (engagement_id, round_index)).fetchone()
    if existing:
        return _jload(existing[0], {})
    requirement = _battle_player_requirement(conn, engagement_id, round_index)
    if requirement:
        return requirement

    ensure_default_zone(conn, engagement_id)
    auto_assign_unzoned_units(conn, engagement_id)
    seed = _round_seed(conn, engagement_id, round_index, 13)
    tactical = apply_tactical_layer(conn, engagement_id, round_index, seed)

    result = _resolve_battle_round_base(conn, engagement_id)
    if result.get("needs_player"):
        raise RuntimeError("Player requirement changed after tactical pre-resolution; state would be inconsistent")
    actual_round = int(result.get("round_index", 0))
    if actual_round <= 0:
        return result
    flow = apply_battlefield_flow(conn, engagement_id, actual_round, seed)
    result["tactical_layer"] = tactical
    result["battlefield_flow"] = flow
    result["phase"] = flow["phase"]
    conn.execute("UPDATE battle_rounds SET summary_json=? WHERE engagement_id=? AND round_index=?",
                 (json.dumps(result, ensure_ascii=False), engagement_id, actual_round))
    return result


def battle_view(conn: sqlite3.Connection, engagement_id: int, actor_id: int) -> dict[str, Any]:
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng or eng["engagement_kind"] != "battle":
        raise ValueError("Battle does not exist")
    role = _battle_role(conn, engagement_id, actor_id)
    command_score = _competence(conn, actor_id, "command", 0.0)
    role_depth = "strategic" if role["role"] == "side_controller" else ("local" if role["role"] == "unit_commander" else "observer")
    sides = conn.execute("SELECT * FROM battle_sides WHERE engagement_id=? ORDER BY id", (engagement_id,)).fetchall()
    visible = []
    for side in sides:
        is_own = role["side_id"] is not None and int(side["id"]) == int(role["side_id"])
        item: dict[str, Any] = {
            "side_id": int(side["id"]),
            "name": side["name"],
            "status": side["status"],
            "morale": _band(float(side["morale"])),
            "cohesion": _band(float(side["cohesion"])),
            "momentum": "favorable" if float(side["momentum"]) > 18 else ("unfavorable" if float(side["momentum"]) < -18 else "contested"),
        }
        units = conn.execute("SELECT * FROM battle_units WHERE side_id=? ORDER BY id", (side["id"],)).fetchall()
        if is_own and role_depth == "strategic":
            item["units"] = [
                {"unit_id": int(u["id"]), "name": u["name"], "role": u["unit_role"], "status": u["status"],
                 "capacity": _band(float(u["combat_capacity"])), "morale": _band(float(u["morale"])),
                 "cohesion": _band(float(u["cohesion"])), "fatigue": _band(100-float(u["fatigue"]), labels=("exhausted","tired","working","fresh","very_fresh"))}
                for u in units
            ]
            item["logistics"] = _band(float(side["logistics"]))
            item["reserve"] = _band(float(side["reserve_capacity"]))
        elif is_own and role_depth == "local":
            own = [u for u in units if int(u["id"]) == int(role["unit_id"])]
            item["units"] = [
                {"unit_id": int(u["id"]), "name": u["name"], "role": u["unit_role"], "status": u["status"],
                 "capacity": _band(float(u["combat_capacity"])), "morale": _band(float(u["morale"])),
                 "cohesion": _band(float(u["cohesion"])), "fatigue": _band(100-float(u["fatigue"]), labels=("exhausted","tired","working","fresh","very_fresh"))}
                for u in own
            ]
        elif not is_own:
            info = float(next((s["information_quality"] for s in sides if role["side_id"] is not None and int(s["id"]) == int(role["side_id"])), 20))
            if role_depth == "strategic" and info + command_score * 0.2 >= 55:
                item["observed_units"] = [{"name": u["name"], "role": u["unit_role"], "status": u["status"]} for u in units if u["status"] != "disengaged"]
            else:
                item["observed_units"] = []
                item["uncertainty"] = "Enemy detail remains incomplete from this position."
        visible.append(item)
    flow_view = battlefield_view(conn, engagement_id, actor_id, role=role)
    tactics_view = tactical_view(conn, engagement_id, actor_id, role)
    return {
        "engagement_id": engagement_id,
        "title": eng["title"],
        "phase": eng["phase"],
        "round_index": int(eng["round_index"]),
        "status": eng["status"],
        "viewer": {"actor_id": actor_id, "role": role["role"], "information_depth": role_depth, "command_competence": command_score},
        "sides": visible,
        "battlefield": flow_view,
        "tactics": tactics_view,
        "guardrails": {
            "not_omniscient": True,
            "hidden_enemy_state_withheld": True,
            "player_intent_is_high_level": True,
            "technical_execution_is_character_and_subordinate_work": True,
            "reports_may_be_delayed": True,
            "local_events_do_not_auto_resolve_the_whole_battle": True,
            "personal_combat_consequence_is_contextual": True,
            "vein_assets_are_strategic_but_not_automatic_victory": True,
            "tactical_families_are_abstract_tradeoffs_not_scripted_winning_moves": True,
        },
    }


def create_duel(
    conn: sqlite3.Connection,
    title: str,
    actor_a_id: int,
    actor_b_id: int,
    *,
    location_id: int | None = None,
    player_actor_id: int | None = None,
    objective: str | None = None,
    stakes: int = 3,
    capability_a: float | None = None,
    capability_b: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    if actor_a_id == actor_b_id:
        raise ValueError("A duel requires two different actors")
    _actor_exists(conn, actor_a_id)
    _actor_exists(conn, actor_b_id)
    if player_actor_id is not None and player_actor_id not in {actor_a_id, actor_b_id}:
        raise ValueError("Player actor must be a duel combatant")
    day = current_day(conn)
    cur = conn.execute(
        """INSERT INTO combat_engagements(
               engagement_kind,title,location_id,player_actor_id,objective_text,stakes,status,phase,round_index,day_started,metadata_json
           ) VALUES ('duel',?,?,?,?,?,'active','opening',0,?,?)""",
        (title, location_id, player_actor_id, objective, max(1,min(5,int(stakes))), day, json.dumps(metadata or {}, ensure_ascii=False)),
    )
    eid = int(cur.lastrowid)
    for actor_id, capability in ((actor_a_id, capability_a), (actor_b_id, capability_b)):
        conn.execute(
            "INSERT INTO duel_combatants(engagement_id,actor_id,capability_override) VALUES (?,?,?)",
            (eid, actor_id, capability),
        )
    return eid



def link_duel_to_battle(
    conn: sqlite3.Connection,
    duel_engagement_id: int,
    battle_engagement_id: int,
    zone_id: int,
    actor_a_asset_id: int,
    actor_b_asset_id: int,
) -> None:
    """Link a duel to the battlefield context it can actually affect.

    The link is explicit so a personal fight never gains strategic meaning merely because it exists.
    When the duel resolves, the winner/loser are mapped back to their persisted Vein assets and the
    normal contextual consequence resolver decides whether the effect is minor, local, operational,
    or strategic.
    """
    duel = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (duel_engagement_id,)).fetchone()
    battle = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (battle_engagement_id,)).fetchone()
    if not duel or duel["engagement_kind"] != "duel":
        raise ValueError("Duel engagement does not exist")
    if not battle or battle["engagement_kind"] != "battle":
        raise ValueError("Battle engagement does not exist")
    zone = conn.execute("SELECT * FROM battle_zones WHERE id=? AND engagement_id=?", (zone_id, battle_engagement_id)).fetchone()
    if not zone:
        raise ValueError("Battle zone does not belong to battle")
    combatants = conn.execute("SELECT actor_id FROM duel_combatants WHERE engagement_id=? ORDER BY id", (duel_engagement_id,)).fetchall()
    if len(combatants) != 2:
        raise ValueError("Linked duel requires exactly two duel combatants")
    actor_a_id, actor_b_id = int(combatants[0][0]), int(combatants[1][0])
    asset_a = conn.execute("SELECT * FROM battle_vein_assets WHERE id=?", (actor_a_asset_id,)).fetchone()
    asset_b = conn.execute("SELECT * FROM battle_vein_assets WHERE id=?", (actor_b_asset_id,)).fetchone()
    if not asset_a or not asset_b:
        raise ValueError("Both linked combatants require battle Vein assets")
    if int(asset_a["engagement_id"]) != battle_engagement_id or int(asset_b["engagement_id"]) != battle_engagement_id:
        raise ValueError("Vein assets must belong to linked battle")
    if int(asset_a["actor_id"] or -1) != actor_a_id or int(asset_b["actor_id"] or -1) != actor_b_id:
        raise ValueError("Vein assets must correspond to the duel combatants in duel order")
    if int(asset_a["zone_id"] or -1) != zone_id or int(asset_b["zone_id"] or -1) != zone_id:
        raise ValueError("Linked Vein assets must currently be assigned to the duel's battle zone")
    conn.execute(
        """INSERT OR REPLACE INTO duel_battle_links(
               duel_engagement_id,battle_engagement_id,zone_id,actor_a_id,actor_b_id,
               actor_a_asset_id,actor_b_asset_id,consequence_id,created_day
           ) VALUES (?,?,?,?,?,?,?,NULL,?)""",
        (duel_engagement_id,battle_engagement_id,zone_id,actor_a_id,actor_b_id,actor_a_asset_id,actor_b_asset_id,current_day(conn)),
    )


def _apply_linked_duel_consequence(conn: sqlite3.Connection, duel_engagement_id: int, outcome: dict[str, Any]) -> dict[str, Any] | None:
    link = conn.execute("SELECT * FROM duel_battle_links WHERE duel_engagement_id=?", (duel_engagement_id,)).fetchone()
    if not link or link["consequence_id"] is not None:
        return None
    winner_actor = outcome.get("winner_actor_id")
    if winner_actor is None:
        return None
    winner_actor = int(winner_actor)
    if winner_actor == int(link["actor_a_id"]):
        winner_asset, loser_asset = int(link["actor_a_asset_id"]), int(link["actor_b_asset_id"])
    elif winner_actor == int(link["actor_b_id"]):
        winner_asset, loser_asset = int(link["actor_b_asset_id"]), int(link["actor_a_asset_id"])
    else:
        raise ValueError("Duel winner does not match linked battlefield combatants")
    result = apply_personal_combat_consequence(
        conn, int(link["battle_engagement_id"]), int(link["zone_id"]),
        winner_asset_id=winner_asset, loser_asset_id=loser_asset,
        summary="A linked personal confrontation changed the battle according to the strategic value of the people and position involved.",
    )
    conn.execute("UPDATE duel_battle_links SET consequence_id=? WHERE duel_engagement_id=?", (result["id"], duel_engagement_id))
    return result


def submit_duel_intent(
    conn: sqlite3.Connection,
    engagement_id: int,
    actor_id: int,
    intent_key: str,
    *,
    risk_level: str = "balanced",
    reserve_commitment: float = 0.25,
    objective: str | None = None,
    source_kind: str = "player",
) -> int:
    if intent_key not in DUEL_INTENTS:
        raise ValueError(f"Unknown duel intent: {intent_key}")
    if risk_level not in RISK:
        raise ValueError("Invalid risk level")
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng or eng["engagement_kind"] != "duel" or eng["status"] != "active":
        raise ValueError("Duel is not active")
    combatant = conn.execute("SELECT * FROM duel_combatants WHERE engagement_id=? AND actor_id=?", (engagement_id, actor_id)).fetchone()
    if not combatant or combatant["status"] != "engaged":
        raise ValueError("Actor is not an active duel combatant")
    round_index = int(eng["round_index"]) + 1
    cur = conn.execute(
        """INSERT OR REPLACE INTO duel_intents(
               engagement_id,combatant_id,actor_id,round_index,intent_key,risk_level,reserve_commitment,objective_text,source_kind,status,result_json,created_day
           ) VALUES (?,?,?,?,?,?,?,?,?,'submitted','{}',?)""",
        (engagement_id, combatant["id"], actor_id, round_index, intent_key, risk_level,
         max(0.0,min(1.0,float(reserve_commitment))), objective, source_kind, current_day(conn)),
    )
    return int(cur.lastrowid)


def _npc_duel_intent(combatant: sqlite3.Row) -> dict[str, Any]:
    readiness = float(combatant["readiness"])
    stamina = float(combatant["stamina"])
    reserve = float(combatant["reserve"])
    if readiness < 28 or stamina < 20:
        return {"intent_key": "disengage", "risk_level": "low", "reserve_commitment": 0.1}
    if stamina < 40:
        return {"intent_key": "conserve", "risk_level": "low", "reserve_commitment": 0.12}
    if reserve > 65 and float(combatant["momentum"]) > 15:
        return {"intent_key": "commit", "risk_level": "high", "reserve_commitment": 0.5}
    if float(combatant["momentum"]) < -18:
        return {"intent_key": "defend", "risk_level": "low", "reserve_commitment": 0.18}
    return {"intent_key": "measure", "risk_level": "balanced", "reserve_commitment": 0.22}


def _ensure_duel_intent(conn: sqlite3.Connection, engagement_id: int, combatant: sqlite3.Row, round_index: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM duel_intents WHERE engagement_id=? AND actor_id=? AND round_index=? ORDER BY id DESC LIMIT 1",
                       (engagement_id, combatant["actor_id"], round_index)).fetchone()
    if row:
        return row
    choice = _npc_duel_intent(combatant)
    cur = conn.execute(
        """INSERT INTO duel_intents(
               engagement_id,combatant_id,actor_id,round_index,intent_key,risk_level,reserve_commitment,source_kind,status,result_json,created_day
           ) VALUES (?,?,?,?,?,?,?,'npc_rules','submitted','{}',?)""",
        (engagement_id, combatant["id"], combatant["actor_id"], round_index, choice["intent_key"], choice["risk_level"],
         choice["reserve_commitment"], current_day(conn)),
    )
    return conn.execute("SELECT * FROM duel_intents WHERE id=?", (cur.lastrowid,)).fetchone()


def _duel_player_requirement(conn: sqlite3.Connection, eng: sqlite3.Row, round_index: int) -> dict[str, Any] | None:
    player = eng["player_actor_id"]
    if player is None:
        return None
    c = conn.execute("SELECT * FROM duel_combatants WHERE engagement_id=? AND actor_id=?", (eng["id"], player)).fetchone()
    if not c or c["status"] != "engaged":
        return None
    row = conn.execute("SELECT 1 FROM duel_intents WHERE engagement_id=? AND actor_id=? AND round_index=?", (eng["id"], player, round_index)).fetchone()
    if not row:
        return {"needs_player": True, "role": "duelist", "round_index": round_index, "reason": "A high-level duel intent is required before the next exchange can resolve."}
    return None


def _duel_intent_mod(intent: str) -> dict[str, float]:
    return {
        "measure": {"score": 1, "fatigue": 3, "defense": 2, "control": 1},
        "press": {"score": 7, "fatigue": 8, "defense": -2, "control": 0},
        "defend": {"score": -1, "fatigue": 3, "defense": 8, "control": 2},
        "conserve": {"score": -4, "fatigue": -1, "defense": 4, "control": 1},
        "commit": {"score": 11, "fatigue": 10, "defense": -4, "control": 0},
        "control": {"score": 2, "fatigue": 5, "defense": 3, "control": 7},
        "disengage": {"score": -6, "fatigue": 2, "defense": 6, "control": 0},
    }[intent]


def resolve_duel_exchange(conn: sqlite3.Connection, engagement_id: int) -> dict[str, Any]:
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng or eng["engagement_kind"] != "duel":
        raise ValueError("Duel does not exist")
    if eng["status"] == "resolved":
        return {"status": "resolved", "engagement_id": engagement_id, "outcome": _jload(eng["outcome_json"], {})}
    combatants = conn.execute("SELECT * FROM duel_combatants WHERE engagement_id=? AND status='engaged' ORDER BY id", (engagement_id,)).fetchall()
    if len(combatants) != 2:
        raise ValueError("Active duel resolution currently requires exactly two engaged combatants")
    round_index = int(eng["round_index"]) + 1
    existing = conn.execute("SELECT summary_json FROM duel_exchanges WHERE engagement_id=? AND round_index=?", (engagement_id, round_index)).fetchone()
    if existing:
        return _jload(existing[0], {})
    requirement = _duel_player_requirement(conn, eng, round_index)
    if requirement:
        return requirement

    intents = {int(c["id"]): _ensure_duel_intent(conn, engagement_id, c, round_index) for c in combatants}
    seed = _round_seed(conn, engagement_id, round_index, 29)
    rng = random.Random(seed)
    scored: dict[int, float] = {}
    details: dict[int, dict[str, Any]] = {}
    for c in combatants:
        intent = intents[int(c["id"])]
        capability = float(c["capability_override"]) if c["capability_override"] is not None else _competence(conn, int(c["actor_id"]), "martial", 35.0)
        mod = _duel_intent_mod(str(intent["intent_key"]))
        risk_power, _ = _risk_mod(str(intent["risk_level"]))
        commit = float(intent["reserve_commitment"])
        usable_reserve = min(float(c["reserve"]), commit * 100.0)
        score = (
            capability * 0.38
            + float(c["readiness"]) * 0.17
            + float(c["stamina"]) * 0.12
            + float(c["composure"]) * 0.12
            + usable_reserve * 0.09
            + float(c["momentum"]) * 0.06
            + mod["score"] + risk_power + rng.uniform(-5, 5)
        )
        scored[int(c["id"])] = score
        details[int(c["id"])] = {"combatant": c, "intent": intent, "capability": capability, "mod": mod, "usable_reserve": usable_reserve}

    c1, c2 = combatants
    diff = scored[int(c1["id"])] - scored[int(c2["id"])]
    results: list[dict[str, Any]] = []
    for c, opponent, sign in ((c1, c2, 1.0), (c2, c1, -1.0)):
        d = details[int(c["id"])]
        intent = d["intent"]
        mod = d["mod"]
        local_diff = diff * sign
        # Readiness is an abstract ability-to-continue state, not anatomical injury modeling.
        readiness_loss = max(0.5, 4.0 - local_diff * 0.10 + (2.0 if intent["risk_level"] == "high" else 0.0))
        stamina_loss = max(1.0, mod["fatigue"] + d["usable_reserve"] * 0.03 + (2.0 if intent["risk_level"] == "high" else 0.0))
        if intent["intent_key"] == "conserve":
            stamina_loss = max(0.5, stamina_loss - 3.0)
        reserve_loss = d["usable_reserve"] * 0.45
        composure_change = local_diff * 0.05 + mod["control"] * 0.2
        momentum_change = local_diff * 0.30
        new_readiness = _clamp(float(c["readiness"]) - readiness_loss)
        new_stamina = _clamp(float(c["stamina"]) - stamina_loss)
        new_reserve = _clamp(float(c["reserve"]) - reserve_loss)
        new_composure = _clamp(float(c["composure"]) + composure_change)
        new_momentum = _clamp(float(c["momentum"]) + momentum_change, -100, 100)
        status = "engaged"
        if intent["intent_key"] == "disengage" and local_diff >= -8:
            status = "disengaged"
        elif new_readiness <= 18 or new_composure <= 8:
            status = "defeated"
        conn.execute(
            "UPDATE duel_combatants SET readiness=?,stamina=?,composure=?,reserve=?,momentum=?,status=? WHERE id=?",
            (new_readiness, new_stamina, new_composure, new_reserve, new_momentum, status, c["id"]),
        )
        result = {
            "actor_id": int(c["actor_id"]),
            "intent": intent["intent_key"],
            "risk": intent["risk_level"],
            "readiness": _band(new_readiness),
            "stamina": _band(new_stamina, labels=("spent","low","working","fresh","full")),
            "composure": _band(new_composure),
            "reserve": _band(new_reserve),
            "momentum": "advantage" if new_momentum > 18 else ("under_pressure" if new_momentum < -18 else "contested"),
            "status": status,
        }
        results.append(result)
        conn.execute("UPDATE duel_intents SET status='resolved',result_json=? WHERE id=?", (json.dumps(result, ensure_ascii=False), intent["id"]))

    active = conn.execute("SELECT * FROM duel_combatants WHERE engagement_id=? AND status='engaged' ORDER BY id", (engagement_id,)).fetchall()
    resolved = len(active) < 2
    outcome: dict[str, Any] = {}
    if resolved:
        all_c = conn.execute("SELECT * FROM duel_combatants WHERE engagement_id=? ORDER BY id", (engagement_id,)).fetchall()
        standing = [c for c in all_c if c["status"] == "engaged"]
        if len(standing) == 1:
            winner = standing[0]
            conn.execute("UPDATE duel_combatants SET status='victorious' WHERE id=?", (winner["id"],))
            outcome = {"winner_actor_id": int(winner["actor_id"]), "resolution": "opponent_unable_or_unwilling_to_continue"}
        else:
            outcome = {"winner_actor_id": None, "resolution": "disengagement"}
        conn.execute("UPDATE combat_engagements SET status='resolved',phase='aftermath',round_index=?,day_ended=?,outcome_json=? WHERE id=?",
                     (round_index, current_day(conn), json.dumps(outcome, ensure_ascii=False), engagement_id))
    else:
        conn.execute("UPDATE combat_engagements SET phase='exchange',round_index=? WHERE id=?", (round_index, engagement_id))

    battle_consequence = _apply_linked_duel_consequence(conn, engagement_id, outcome) if resolved else None
    summary = {
        "engagement_id": engagement_id,
        "kind": "duel",
        "round_index": round_index,
        "status": "resolved" if resolved else "active",
        "combatants": results,
        "outcome": outcome,
        "battle_consequence": battle_consequence,
        "note": "Duel resolution is intentionally abstract. Specific injury/medical consequences belong to the later health resolver.",
    }
    conn.execute("INSERT INTO duel_exchanges(engagement_id,round_index,day,seed,summary_json) VALUES (?,?,?,?,?)",
                 (engagement_id, round_index, current_day(conn), seed, json.dumps(summary, ensure_ascii=False)))
    conn.execute("INSERT INTO events(day,event_type,title,summary,severity,location_id,source_actor_id) VALUES (?,?,?,?,?,?,NULL)",
                 (current_day(conn), "duel_exchange", f"Duel exchange {round_index}: {eng['title']}",
                  "The duel changed through intent, competence, reserves, stamina, composure, and momentum.", min(5,max(2,int(eng["stakes"]))), eng["location_id"]))
    return summary


def duel_view(conn: sqlite3.Connection, engagement_id: int, actor_id: int) -> dict[str, Any]:
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng or eng["engagement_kind"] != "duel":
        raise ValueError("Duel does not exist")
    rows = conn.execute(
        """SELECT c.*,a.name FROM duel_combatants c JOIN actors a ON a.id=c.actor_id
           WHERE c.engagement_id=? ORDER BY c.id""",
        (engagement_id,),
    ).fetchall()
    viewer_is_combatant = any(int(r["actor_id"]) == actor_id for r in rows)
    martial = _competence(conn, actor_id, "martial", 0.0)
    visible = []
    for r in rows:
        own = int(r["actor_id"]) == actor_id
        item = {"actor_id": int(r["actor_id"]), "name": r["name"], "status": r["status"]}
        if own:
            item.update({"readiness": _band(float(r["readiness"])), "stamina": _band(float(r["stamina"]), labels=("spent","low","working","fresh","full")),
                         "composure": _band(float(r["composure"])), "reserve": _band(float(r["reserve"])),
                         "momentum": "advantage" if float(r["momentum"]) > 18 else ("under_pressure" if float(r["momentum"]) < -18 else "contested")})
        elif viewer_is_combatant:
            item["apparent_readiness"] = _band(float(r["readiness"]) + (0 if martial >= 60 else 8))
            item["apparent_stamina"] = _band(float(r["stamina"]) + (0 if martial >= 60 else 10), labels=("spent","low","working","fresh","full"))
            item["reading_note"] = "This is your character's combat reading, not omniscient access to the opponent's exact state."
        visible.append(item)
    return {
        "engagement_id": engagement_id,
        "title": eng["title"],
        "phase": eng["phase"],
        "round_index": int(eng["round_index"]),
        "status": eng["status"],
        "viewer_martial_competence": martial,
        "combatants": visible,
        "guardrails": {"high_level_intent_only": True, "technical_exchange_hidden": True, "injury_detail_deferred": True},
    }


def engagement_summary(conn: sqlite3.Connection, engagement_id: int) -> dict[str, Any] | None:
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not eng:
        return None
    out = dict(eng)
    out["outcome"] = _jload(out.pop("outcome_json"), {})
    out["metadata"] = _jload(out.pop("metadata_json"), {})
    if eng["engagement_kind"] == "battle":
        out["sides"] = [dict(r) for r in conn.execute("SELECT * FROM battle_sides WHERE engagement_id=? ORDER BY id", (engagement_id,)).fetchall()]
        out["rounds"] = [dict(r) for r in conn.execute("SELECT * FROM battle_rounds WHERE engagement_id=? ORDER BY round_index", (engagement_id,)).fetchall()]
    else:
        out["combatants"] = [dict(r) for r in conn.execute("SELECT * FROM duel_combatants WHERE engagement_id=? ORDER BY id", (engagement_id,)).fetchall()]
        out["exchanges"] = [dict(r) for r in conn.execute("SELECT * FROM duel_exchanges WHERE engagement_id=? ORDER BY round_index", (engagement_id,)).fetchall()]
    return out
