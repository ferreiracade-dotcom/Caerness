from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Any, Callable

from .ecology import find_route_path, evaluate_route_leg


def _day(conn):
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _clamp(x, lo=0, hi=100):
    return max(lo, min(hi, float(x)))


def _j(v):
    try:
        return json.loads(v or '{}')
    except Exception:
        return {}


def _stable_fraction(*parts: object) -> float:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def configure_military_logistics_profile(conn: sqlite3.Connection, polity_id: int, *, source_location_id: int | None = None,
                                         food_fodder_capacity=50, medical_capacity=50, equipment_capacity=50,
                                         elixir_reserve_capacity=25, transport_capacity=50, readiness=50,
                                         metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    conn.execute(
        """INSERT INTO military_logistics_profiles(polity_id,source_location_id,food_fodder_capacity,medical_capacity,equipment_capacity,
                  elixir_reserve_capacity,transport_capacity,readiness,status,next_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,'ready',?,?) ON CONFLICT(polity_id) DO UPDATE SET
             source_location_id=COALESCE(excluded.source_location_id,military_logistics_profiles.source_location_id),
             metadata_json=excluded.metadata_json""",
        (polity_id, source_location_id, food_fodder_capacity, medical_capacity, equipment_capacity,
         elixir_reserve_capacity, transport_capacity, readiness, day + 30, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(conn.execute("SELECT id FROM military_logistics_profiles WHERE polity_id=?", (polity_id,)).fetchone()[0])


# ---------------------------------------------------------------------------
# WAR-01 strategic campaign owner / force movement / physical supply


def create_campaign_operation(conn: sqlite3.Connection, name: str, *, objective_text: str,
                              origin_location_id: int, target_location_id: int,
                              attacker_polity_id: int | None = None, defender_polity_id: int | None = None,
                              commander_actor_id: int | None = None, objective_kind: str = "limited",
                              metadata: dict[str, Any] | None = None) -> int:
    if origin_location_id == target_location_id:
        raise ValueError("campaign origin and target must differ")
    for loc in (origin_location_id, target_location_id):
        if not conn.execute("SELECT 1 FROM locations WHERE id=?", (loc,)).fetchone():
            raise ValueError("unknown campaign location")
    if commander_actor_id is not None and not conn.execute(
        "SELECT 1 FROM actors WHERE id=? AND status='active'", (commander_actor_id,)
    ).fetchone():
        raise ValueError("campaign commander unavailable")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO war_campaign_operations(name,attacker_polity_id,defender_polity_id,commander_actor_id,
               objective_kind,objective_text,origin_location_id,target_location_id,status,started_day,next_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,'mobilizing',?,?,?)""",
        (name, attacker_polity_id, defender_polity_id, commander_actor_id, objective_kind, objective_text,
         origin_location_id, target_location_id, day, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def add_campaign_force(conn: sqlite3.Connection, operation_id: int, name: str, *, personnel: int,
                       polity_id: int | None = None, role: str = "field_force",
                       current_location_id: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    op = conn.execute("SELECT * FROM war_campaign_operations WHERE id=?", (operation_id,)).fetchone()
    if not op:
        raise ValueError("unknown campaign operation")
    if personnel < 0:
        raise ValueError("personnel cannot be negative")
    loc = int(current_location_id if current_location_id is not None else op["origin_location_id"])
    day = _day(conn)
    from .population_reconciliation import population_source_for_location
    force_meta = dict(metadata or {})
    pop_source = population_source_for_location(conn, loc)
    if pop_source is not None:
        force_meta.setdefault("population_source_id", int(pop_source))
        force_meta.setdefault("population_source_location_id", loc)
    cur = conn.execute(
        """INSERT INTO war_campaign_forces(operation_id,polity_id,name,role,personnel_initial,personnel_available,
               current_location_id,status,last_review_day,next_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,'mobilized',?,?,?)""",
        (operation_id, polity_id, name, role, int(personnel), int(personnel), loc, day, day,
         json.dumps(force_meta, sort_keys=True)),
    )
    conn.execute("UPDATE war_campaign_operations SET status='marching',next_review_day=? WHERE id=?", (day, operation_id))
    return int(cur.lastrowid)


def add_force_member(conn: sqlite3.Connection, force_id: int, actor_id: int, *, duty_kind: str = "soldier",
                     exposure: float = 50, metadata: dict[str, Any] | None = None) -> None:
    if not conn.execute("SELECT 1 FROM war_campaign_forces WHERE id=?", (force_id,)).fetchone():
        raise ValueError("unknown campaign force")
    if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (actor_id,)).fetchone():
        raise ValueError("force member unavailable")
    conn.execute(
        """INSERT OR REPLACE INTO war_force_members(force_id,actor_id,duty_kind,exposure,status,updated_day,metadata_json)
           VALUES (?,?,?,?,'active',?,?)""",
        (force_id, actor_id, duty_kind, _clamp(exposure), _day(conn), json.dumps(metadata or {}, sort_keys=True)),
    )


def _stock_row(conn: sqlite3.Connection, enterprise_id: int, location_id: int, good_id: int):
    return conn.execute(
        "SELECT * FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",
        (enterprise_id, location_id, good_id),
    ).fetchone()


def _withdraw_source_stock(conn: sqlite3.Connection, force_id: int, *, enterprise_id: int, location_id: int,
                           good_id: int, quantity: float, entry_kind: str) -> float:
    if quantity <= 0:
        return 0.0
    stock = _stock_row(conn, enterprise_id, location_id, good_id)
    if not stock:
        return 0.0
    take = min(float(stock["quantity"]), float(quantity))
    if take <= 0:
        return 0.0
    day = _day(conn)
    conn.execute("UPDATE commercial_stock SET quantity=quantity-?,updated_day=? WHERE id=?", (take, day, int(stock["id"])))
    conn.execute(
        """INSERT INTO war_supply_ledger(force_id,day,good_id,entry_kind,quantity,source_stock_id,location_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (force_id, day, good_id, entry_kind, take, int(stock["id"]), location_id,
         json.dumps({"authority": "physical_stock_transfer"}, sort_keys=True)),
    )
    return take


def configure_force_supply(conn: sqlite3.Connection, force_id: int, good_id: int, *, supply_kind: str,
                           source_enterprise_id: int, source_location_id: int, weekly_need: float,
                           max_on_hand: float | None = None, initial_on_hand: float | None = None) -> None:
    force = conn.execute("SELECT * FROM war_campaign_forces WHERE id=?", (force_id,)).fetchone()
    if not force:
        raise ValueError("unknown campaign force")
    if weekly_need < 0:
        raise ValueError("weekly need cannot be negative")
    max_on_hand = float(max_on_hand if max_on_hand is not None else max(weekly_need * 2.0, weekly_need))
    desired = float(initial_on_hand if initial_on_hand is not None else max_on_hand)
    loaded = _withdraw_source_stock(
        conn, force_id, enterprise_id=source_enterprise_id, location_id=source_location_id,
        good_id=good_id, quantity=min(desired, max_on_hand), entry_kind="mobilized",
    )
    day = _day(conn)
    conn.execute(
        """INSERT INTO war_force_supplies(force_id,good_id,supply_kind,source_enterprise_id,source_location_id,
               on_hand,weekly_need,max_on_hand,last_review_day)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(force_id,good_id) DO UPDATE SET supply_kind=excluded.supply_kind,
             source_enterprise_id=excluded.source_enterprise_id,source_location_id=excluded.source_location_id,
             on_hand=excluded.on_hand,weekly_need=excluded.weekly_need,max_on_hand=excluded.max_on_hand,last_review_day=excluded.last_review_day""",
        (force_id, good_id, supply_kind, source_enterprise_id, source_location_id, loaded,
         float(weekly_need), max_on_hand, day),
    )


def link_operation_engagement(conn: sqlite3.Connection, operation_id: int, engagement_id: int, *, sequence_no: int = 1) -> None:
    op = conn.execute("SELECT 1 FROM war_campaign_operations WHERE id=?", (operation_id,)).fetchone()
    eng = conn.execute("SELECT engagement_kind FROM combat_engagements WHERE id=?", (engagement_id,)).fetchone()
    if not op or not eng or str(eng[0]) != "battle":
        raise ValueError("operation and battle engagement required")
    conn.execute(
        "INSERT OR REPLACE INTO war_operation_engagements(operation_id,engagement_id,sequence_no,linked_day) VALUES (?,?,?,?)",
        (operation_id, engagement_id, sequence_no, _day(conn)),
    )
    conn.execute("UPDATE war_campaign_operations SET status='engaged',next_review_day=? WHERE id=?", (_day(conn), operation_id))


def attach_force_to_battle_side(conn: sqlite3.Connection, force_id: int, battle_side_id: int) -> None:
    force = conn.execute("SELECT operation_id,polity_id FROM war_campaign_forces WHERE id=?", (force_id,)).fetchone()
    side = conn.execute("SELECT engagement_id,metadata_json FROM battle_sides WHERE id=?", (battle_side_id,)).fetchone()
    if not force or not side:
        raise ValueError("force and battle side required")
    link = conn.execute(
        "SELECT 1 FROM war_operation_engagements WHERE operation_id=? AND engagement_id=?",
        (int(force["operation_id"]), int(side["engagement_id"])),
    ).fetchone()
    if not link:
        raise ValueError("battle is not linked to force operation")
    conn.execute("UPDATE war_campaign_forces SET battle_side_id=?,status='engaged' WHERE id=?", (battle_side_id, force_id))


def _segment_target(conn: sqlite3.Connection, route_id: int, current_location_id: int) -> int:
    r = conn.execute("SELECT from_location_id,to_location_id,bidirectional FROM travel_routes WHERE id=?", (route_id,)).fetchone()
    if not r:
        raise ValueError("unknown route")
    if int(r["from_location_id"]) == current_location_id:
        return int(r["to_location_id"])
    if int(r["to_location_id"]) == current_location_id and int(r["bidirectional"]) == 1:
        return int(r["from_location_id"])
    raise ValueError("route is not traversable from force location")


def _begin_force_segment(conn: sqlite3.Connection, force: sqlite3.Row, day: int) -> bool:
    op = conn.execute("SELECT * FROM war_campaign_operations WHERE id=?", (int(force["operation_id"]),)).fetchone()
    current = int(force["current_location_id"])
    target = int(op["origin_location_id"] if str(force["status"]) == "withdrawing" else op["target_location_id"])
    if current == target:
        status = "demobilized" if str(force["status"]) == "withdrawing" else "deployed"
        conn.execute(
            "UPDATE war_campaign_forces SET status=?,current_route_id=NULL,segment_target_location_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?",
            (status, day + 7, int(force["id"])),
        )
        return True
    path = find_route_path(conn, current, target, day=day)
    if not path:
        try:
            from .conflict_geometry import military_geometry_between, direct_military_travel_days
            geo = military_geometry_between(conn, current, target)
        except sqlite3.OperationalError:
            geo = None
        if geo is not None and str(geo["geometry_kind"]) != "civilian_route":
            days = direct_military_travel_days(conn, current, target) or 7.0
            due = day + max(1, int(math.ceil(days)))
            meta = _j(force["metadata_json"])
            meta["active_conflict_geometry_id"] = int(geo["id"])
            meta["military_geometry_kind"] = str(geo["geometry_kind"])
            conn.execute(
                "UPDATE war_campaign_forces SET status=?,current_route_id=NULL,segment_target_location_id=?,segment_due_day=?,next_review_day=?,metadata_json=? WHERE id=?",
                ("withdrawing" if str(force["status"]) == "withdrawing" else "marching", target, due, due, json.dumps(meta, sort_keys=True), int(force["id"])),
            )
            return True
        conn.execute(
            "UPDATE war_campaign_forces SET status='stalled',current_route_id=NULL,segment_target_location_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?",
            (day + 3, int(force["id"])),
        )
        return False
    rid = int(path[0])
    ev = evaluate_route_leg(conn, rid, current, day=day)
    if not bool(ev["usable"]):
        conn.execute("UPDATE war_campaign_forces SET status='stalled',next_review_day=? WHERE id=?", (day + 3, int(force["id"])))
        return False
    seg_target = int(ev["target"])
    due = day + max(1, int(math.ceil(float(ev["days"]))))
    conn.execute(
        """UPDATE war_campaign_forces SET status=?,current_route_id=?,segment_target_location_id=?,segment_due_day=?,next_review_day=? WHERE id=?""",
        ("withdrawing" if str(force["status"]) == "withdrawing" else "marching", rid, seg_target, due, due, int(force["id"])),
    )
    return True


def _review_force_movement(conn: sqlite3.Connection, force: sqlite3.Row, day: int) -> str:
    # An active route segment is already a committed movement process. Strategic operation
    # reviews may happen more frequently than travel completion; they must not restart the
    # same leg and slide its due date forward indefinitely.
    if force["segment_due_day"] is not None:
        if int(force["segment_due_day"]) > day:
            return str(force["status"])
        if force["segment_target_location_id"] is not None:
            conn.execute(
                """UPDATE war_campaign_forces SET current_location_id=segment_target_location_id,current_route_id=NULL,
                   segment_target_location_id=NULL,segment_due_day=NULL,last_review_day=?,next_review_day=? WHERE id=?""",
                (day, day, int(force["id"])),
            )
            force = conn.execute("SELECT * FROM war_campaign_forces WHERE id=?", (int(force["id"]),)).fetchone()
    if str(force["status"]) in {"mobilized", "marching", "stalled", "withdrawing"}:
        _begin_force_segment(conn, force, day)
    return str(conn.execute("SELECT status FROM war_campaign_forces WHERE id=?", (int(force["id"]),)).fetchone()[0])


def _supply_route_access(conn: sqlite3.Connection, supply: sqlite3.Row, force: sqlite3.Row, day: int) -> bool:
    src = int(supply["source_location_id"])
    dst = int(force["current_location_id"])
    return src == dst or bool(find_route_path(conn, src, dst, day=day))


def _review_physical_force_supply(conn: sqlite3.Connection, force_id: int, day: int) -> float:
    force = conn.execute("SELECT * FROM war_campaign_forces WHERE id=?", (force_id,)).fetchone()
    rows = conn.execute("SELECT * FROM war_force_supplies WHERE force_id=? ORDER BY good_id", (force_id,)).fetchall()
    if not rows:
        return 0.0
    worst = 0.0
    for s in rows:
        elapsed = max(1, day - int(s["last_review_day"]))
        need = float(s["weekly_need"]) * elapsed / 7.0
        on_hand = float(s["on_hand"])
        consumed = min(on_hand, need)
        if consumed > 0:
            conn.execute(
                "INSERT INTO war_supply_ledger(force_id,day,good_id,entry_kind,quantity,location_id,metadata_json) VALUES (?,?,?,?,?,?,?)",
                (force_id, day, int(s["good_id"]), "consumed", consumed, int(force["current_location_id"]),
                 json.dumps({"elapsed_days": elapsed}, sort_keys=True)),
            )
        on_hand -= consumed
        missing = max(0.0, need - consumed)
        if need > 1e-9:
            worst = max(worst, missing / need)
        if _supply_route_access(conn, s, force, day) and s["source_enterprise_id"] is not None:
            want = max(0.0, float(s["max_on_hand"]) - on_hand)
            got = _withdraw_source_stock(
                conn, force_id, enterprise_id=int(s["source_enterprise_id"]), location_id=int(s["source_location_id"]),
                good_id=int(s["good_id"]), quantity=want, entry_kind="resupplied",
            )
            on_hand += got
        conn.execute(
            "UPDATE war_force_supplies SET on_hand=?,last_review_day=? WHERE force_id=? AND good_id=?",
            (on_hand, day, force_id, int(s["good_id"])),
        )
    conn.execute(
        """UPDATE war_campaign_forces SET last_review_day=?,
           next_review_day=CASE WHEN segment_due_day IS NOT NULL THEN MIN(segment_due_day,?) ELSE ? END WHERE id=?""",
        (day, day + 7, day + 7, force_id),
    )
    return _clamp(worst * 100.0)


def _review_operation(conn: sqlite3.Connection, op: sqlite3.Row, day: int) -> dict[str, int]:
    moved = stalled = supplied = 0
    forces = conn.execute(
        "SELECT * FROM war_campaign_forces WHERE operation_id=? AND status NOT IN ('demobilized','destroyed') ORDER BY id",
        (int(op["id"]),),
    ).fetchall()
    for force in forces:
        before_loc = int(force["current_location_id"])
        status = _review_force_movement(conn, force, day)
        after = conn.execute("SELECT * FROM war_campaign_forces WHERE id=?", (int(force["id"]),)).fetchone()
        if int(after["current_location_id"]) != before_loc:
            moved += 1
        if status == "stalled":
            stalled += 1
        shortage = _review_physical_force_supply(conn, int(force["id"]), day)
        if conn.execute("SELECT 1 FROM war_force_supplies WHERE force_id=?", (int(force["id"]),)).fetchone():
            supplied += 1
        if after["battle_side_id"] is not None and shortage > 0:
            sid = int(after["battle_side_id"])
            conn.execute(
                "UPDATE battle_sides SET logistics=MAX(0,logistics-?) WHERE id=?",
                (shortage * .08, sid),
            )
            conn.execute(
                "UPDATE battle_units SET readiness=MAX(0,readiness-?),fatigue=MIN(100,fatigue+?) WHERE side_id=? AND status NOT IN ('broken','disengaged')",
                (shortage * .05, shortage * .03, sid),
            )
    op_status = str(op["status"])
    if forces and all(str(conn.execute("SELECT status FROM war_campaign_forces WHERE id=?", (int(f["id"]),)).fetchone()[0]) in {"deployed", "engaged"} for f in forces):
        op_status = "engaged"
    elif stalled and stalled == len(forces):
        op_status = "stalled"
    elif op_status not in {"aftermath", "closed", "cancelled"}:
        op_status = "marching"
    conn.execute("UPDATE war_campaign_operations SET status=?,next_review_day=? WHERE id=?", (op_status, day + 3, int(op["id"])))
    return {"forces_moved": moved, "forces_stalled": stalled, "forces_supplied": supplied}


# ---------------------------------------------------------------------------
# Existing battle-linked logistics retained as the coarse/legacy resolution.


def register_campaign_for_battle(conn: sqlite3.Connection, engagement_id: int, *, campaign_kind='limited_campaign') -> int:
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=? AND engagement_kind='battle'", (engagement_id,)).fetchone()
    if not eng:
        raise ValueError('battle engagement required')
    row = conn.execute("SELECT id FROM military_campaigns WHERE battle_engagement_id=?", (engagement_id,)).fetchone()
    if row:
        return int(row[0])
    day = _day(conn)
    cur = conn.execute(
        "INSERT INTO military_campaigns(battle_engagement_id,campaign_kind,location_id,status,started_day,next_review_day,metadata_json) VALUES (?,?,?,'active',?,?,?)",
        (engagement_id, campaign_kind, eng['location_id'], day, day, json.dumps({'authority': 'ENGINE_DERIVED', 'source': 'battle_engagement'}, sort_keys=True)),
    )
    cid = int(cur.lastrowid)
    for side in conn.execute("SELECT * FROM battle_sides WHERE engagement_id=? ORDER BY id", (engagement_id,)).fetchall():
        meta = _j(side['metadata_json']); polity_id = meta.get('polity_id')
        prof = conn.execute("SELECT * FROM military_logistics_profiles WHERE polity_id=?", (polity_id,)).fetchone() if polity_id else None
        cultivated = float(meta.get('cultivated_share', 0) or 0)
        vals = (
            float(prof['food_fodder_capacity']) if prof else float(side['logistics']),
            float(prof['medical_capacity']) if prof else float(side['logistics']),
            float(prof['equipment_capacity']) if prof else float(side['logistics']),
            float(prof['elixir_reserve_capacity']) if prof else max(0, float(side['reserve_capacity']) * 0.5),
        )
        conn.execute(
            """INSERT INTO campaign_side_logistics(campaign_id,battle_side_id,polity_id,food_fodder,medical,equipment,elixir_reserve,
                      cultivated_share,last_review_day,next_review_day,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, int(side['id']), polity_id, *vals, cultivated, day, day, json.dumps({'authority': 'ENGINE_DERIVED'}, sort_keys=True)),
        )
        if prof:
            conn.execute("UPDATE military_logistics_profiles SET status='mobilized',next_review_day=? WHERE id=?", (day + 7, int(prof['id'])))
    return cid


def _route_access(conn, row, campaign):
    if row['polity_id'] is None or campaign['location_id'] is None:
        return 70.0
    prof = conn.execute("SELECT * FROM military_logistics_profiles WHERE polity_id=?", (int(row['polity_id']),)).fetchone()
    if not prof or prof['source_location_id'] is None:
        return 70.0
    src = int(prof['source_location_id']); dst = int(campaign['location_id'])
    if src == dst:
        return 100.0
    return 100.0 if find_route_path(conn, src, dst, day=_day(conn)) else 0.0


def _review_active_side(conn, row, campaign, day):
    elapsed = max(1, day - int(row['last_review_day']))
    factor = elapsed / 7.0
    route = _route_access(conn, row, campaign)
    food = float(row['food_fodder']); med = float(row['medical']); equip = float(row['equipment']); elixir = float(row['elixir_reserve']); share = float(row['cultivated_share'])
    food = _clamp(food - 2.4 * factor + (1.4 * factor if route >= 50 else 0))
    med = _clamp(med - 0.7 * factor + (0.35 * factor if route >= 50 else 0))
    equip = _clamp(equip - 1.0 * factor + (0.55 * factor if route >= 50 else 0))
    if share > 0:
        ground = float(row['current_ground_factor']); draw = max(0.0, 1.2 * share * (1.0 - ground / 100.0)) * factor
        elixir = _clamp(elixir - draw)
    shortage = _clamp((35 - food) * 1.2 if food < 35 else 0) + _clamp((25 - med) * 0.8 if med < 25 else 0) + _clamp((25 - equip) * 0.8 if equip < 25 else 0)
    if route < 50:
        shortage += 18
    # WAR-01 physical force shortage is additive where configured; no physical rows means legacy behavior.
    force = conn.execute("SELECT id FROM war_campaign_forces WHERE battle_side_id=?", (int(row['battle_side_id']),)).fetchone()
    if force and conn.execute("SELECT 1 FROM war_force_supplies WHERE force_id=?", (int(force[0]),)).fetchone():
        # Do not consume the same physical stores twice when the strategic operation
        # already reviewed this force on the same day.  Legacy battle logistics may
        # read the resulting shortage, but physical stock remains owned by WAR-01.
        srows = conn.execute("SELECT on_hand,weekly_need,last_review_day FROM war_force_supplies WHERE force_id=?", (int(force[0]),)).fetchall()
        if srows and min(int(r['last_review_day']) for r in srows) < day:
            phys = _review_physical_force_supply(conn, int(force[0]), day)
        else:
            phys = max((max(0.0, 1.0 - float(r['on_hand']) / max(float(r['weekly_need']), 1e-9)) * 100.0 for r in srows), default=0.0)
        shortage = max(shortage, phys)
    shortage = _clamp(shortage)
    conn.execute(
        "UPDATE campaign_side_logistics SET food_fodder=?,medical=?,equipment=?,elixir_reserve=?,route_access=?,shortage_pressure=?,last_review_day=?,next_review_day=? WHERE id=?",
        (food, med, equip, elixir, route, shortage, day, day + 7, int(row['id'])),
    )
    side = conn.execute("SELECT logistics FROM battle_sides WHERE id=?", (int(row['battle_side_id']),)).fetchone()
    if side:
        newlog = _clamp(float(side[0]) - shortage * 0.05)
        conn.execute("UPDATE battle_sides SET logistics=? WHERE id=?", (newlog, int(row['battle_side_id'])))
        if shortage > 0:
            conn.execute(
                "UPDATE battle_units SET readiness=MAX(0,readiness-?), fatigue=MIN(100,fatigue+?) WHERE side_id=? AND status NOT IN ('broken','disengaged')",
                (shortage * 0.02, shortage * 0.015, int(row['battle_side_id'])),
            )
    if shortage >= 15:
        conn.execute(
            "INSERT INTO war_logistics_events(campaign_id,side_logistics_id,day,event_kind,magnitude,metadata_json) VALUES (?,?,?,'supply_shortage',?,?)",
            (int(campaign['id']), int(row['id']), day, shortage, json.dumps({'route_access': route}, sort_keys=True)),
        )
    return shortage


# ---------------------------------------------------------------------------
# Battle -> world consequence projection


def _named_member_consequences(conn: sqlite3.Connection, force: sqlite3.Row, *, killed: int, wounded: int,
                               captured: int, engagement_id: int, day: int) -> dict[str, int]:
    from .health import add_condition
    from .household_life import mark_actor_deceased

    members = conn.execute(
        "SELECT * FROM war_force_members WHERE force_id=? AND status='active' ORDER BY exposure DESC,actor_id",
        (int(force['id']),),
    ).fetchall()
    total_affected = killed + wounded + captured
    if not members or total_affected <= 0:
        return {"named_killed": 0, "named_wounded": 0, "named_captured": 0}
    casualty_fraction = min(1.0, total_affected / max(1, int(force['personnel_available'])))
    named_n = min(len(members), max(1, int(round(len(members) * casualty_fraction))))
    ranked = sorted(
        members,
        key=lambda r: (-(float(r['exposure']) + _stable_fraction('war-member', engagement_id, int(r['actor_id'])) * 25.0), int(r['actor_id'])),
    )[:named_n]
    slots: list[str] = []
    if killed > 0:
        slots.append('killed')
    if captured > 0 and len(slots) < named_n:
        slots.append('captured')
    while len(slots) < named_n:
        slots.append('wounded')
    out = {"named_killed": 0, "named_wounded": 0, "named_captured": 0}
    for member, result in zip(ranked, slots):
        aid = int(member['actor_id'])
        if result == 'killed':
            mark_actor_deceased(conn, aid, reason=f"killed in battle engagement #{engagement_id}")
            conn.execute("UPDATE war_force_members SET status='killed',updated_day=? WHERE force_id=? AND actor_id=?", (day, int(force['id']), aid))
            conn.execute("UPDATE political_polities SET next_review_day=MIN(next_review_day,?) WHERE ruler_actor_id=?", (day, aid))
            out['named_killed'] += 1
        elif result == 'captured':
            conn.execute("UPDATE war_force_members SET status='captured',updated_day=? WHERE force_id=? AND actor_id=?", (day, int(force['id']), aid))
            out['named_captured'] += 1
        else:
            severity = 28.0 + float(member['exposure']) * .25
            cid = add_condition(
                conn, aid, 'injury', f"Battle wound from engagement #{engagement_id}", severity=severity,
                capacity_impact=min(60.0, severity * .65), pain_impact=min(70.0, severity * .75),
                recovery_rate_per_30=10.0, next_review_days=10,
                metadata={'source_engagement_id': engagement_id, 'source_force_id': int(force['id'])},
            )
            conn.execute(
                "UPDATE war_force_members SET status='wounded',health_condition_id=?,updated_day=? WHERE force_id=? AND actor_id=?",
                (cid, day, int(force['id']), aid),
            )
            out['named_wounded'] += 1
    return out


def _apply_force_casualties(conn: sqlite3.Connection, force: sqlite3.Row, engagement: sqlite3.Row, winner_side_id: int | None, day: int) -> dict[str, Any]:
    side = conn.execute("SELECT * FROM battle_sides WHERE id=?", (int(force['battle_side_id']),)).fetchone() if force['battle_side_id'] is not None else None
    if not side:
        return {}
    stakes = int(engagement['stakes'])
    losing = winner_side_id is not None and int(side['id']) != int(winner_side_id)
    broken = str(side['status']) in {'broken', 'withdrawn'}
    slog = conn.execute("SELECT shortage_pressure FROM campaign_side_logistics WHERE battle_side_id=?", (int(side['id']),)).fetchone()
    shortage = float(slog[0]) if slog else 0.0
    casualty_rate = .015 + .012 * stakes + (.045 if losing else 0.0) + (.045 if broken else 0.0) + shortage / 1800.0
    casualty_rate = max(.01, min(.28, casualty_rate))
    available = int(force['personnel_available'])
    affected = min(available, max(0, int(round(available * casualty_rate))))
    killed = min(affected, int(round(affected * (.30 if losing else .22))))
    captured = min(max(0, affected - killed), int(round(affected * (.18 if losing and broken else .04))))
    wounded = max(0, affected - killed - captured)
    deserted = min(max(0, available - affected), int(round(available * (.025 if broken else .004))))
    new_available = max(0, available - killed - wounded - captured - deserted)
    conn.execute(
        """UPDATE war_campaign_forces SET personnel_available=?,aggregate_killed=aggregate_killed+?,aggregate_wounded=aggregate_wounded+?,
           aggregate_captured=aggregate_captured+?,aggregate_deserted=aggregate_deserted+?,status=? WHERE id=?""",
        (new_available, killed, wounded, captured, deserted, 'destroyed' if new_available <= 0 else str(force['status']), int(force['id'])),
    )
    named = _named_member_consequences(conn, force, killed=killed, wounded=wounded, captured=captured, engagement_id=int(engagement['id']), day=day)
    # Aggregate killed already includes any named/tracked deaths.  Apply it once to the source
    # population and retain the named count only as subset/audit information.
    from .population_reconciliation import record_excess_mortality, population_source_for_location
    fmeta = _j(force['metadata_json'])
    pop_source = fmeta.get('population_source_id')
    if pop_source is None:
        pop_source = population_source_for_location(conn, int(force['current_location_id']) if force['current_location_id'] is not None else None)
    mortality_source_id = int(engagement['id']) * 100000 + int(force['id'])
    ledger = record_excess_mortality(
        conn, source_kind='war_force_engagement', source_id=mortality_source_id, aggregate_deaths=killed,
        tracked_deaths=int(named.get('named_killed',0)), population_source_id=int(pop_source) if pop_source is not None else None,
        metadata={'engagement_id':int(engagement['id']),'force_id':int(force['id']),
                  'location_id':int(force['current_location_id']) if force['current_location_id'] is not None else None},
        adult_only=True,
    )
    conn.execute(
        """INSERT OR IGNORE INTO population_casualty_links(casualty_kind,casualty_source_id,population_source_id,aggregate_deaths,
             tracked_actor_deaths,applied,applied_day,metadata_json) VALUES (?,?,?,?,?,?,?,?)""",
        ('war_force_engagement',mortality_source_id,pop_source,killed,int(named.get('named_killed',0)),
         1 if str(ledger.get('status'))=='applied' else 0,day,json.dumps({'engagement_id':int(engagement['id']),'force_id':int(force['id'])},sort_keys=True)),
    )
    return {"force_id": int(force['id']), "casualty_rate": round(casualty_rate, 4), "killed": killed, "wounded": wounded,
            "captured": captured, "deserted": deserted, "remaining": new_available, **named}


def _damage_local_world(conn: sqlite3.Connection, operation_id: int | None, engagement: sqlite3.Row, day: int) -> list[dict[str, Any]]:
    location_id = engagement['location_id']
    if location_id is None:
        return []
    loc = int(location_id); stakes = int(engagement['stakes']); magnitude = min(70.0, 8.0 + stakes * 7.0)
    out: list[dict[str, Any]] = []
    building = conn.execute("SELECT * FROM buildings WHERE location_id=? AND status IN ('active','strained') ORDER BY capacity DESC,id LIMIT 1", (loc,)).fetchone()
    if building:
        loss = magnitude * .55
        new_condition = max(0.0, float(building['condition']) - loss)
        status = 'destroyed' if new_condition <= 5 else ('derelict' if new_condition < 25 else ('strained' if new_condition < 60 else str(building['status'])))
        conn.execute("UPDATE buildings SET condition=?,status=?,updated_day=? WHERE id=?", (new_condition, status, day, int(building['id'])))
        effects = {'condition_before': float(building['condition']), 'condition_after': new_condition, 'status': status}
        cur = conn.execute("INSERT INTO war_damage_events(operation_id,engagement_id,day,location_id,target_kind,target_id,magnitude,effects_json) VALUES (?,?,?,?,?,?,?,?)",
                           (operation_id, int(engagement['id']), day, loc, 'building', int(building['id']), loss, json.dumps(effects, sort_keys=True)))
        out.append({'damage_event_id': int(cur.lastrowid), 'target_kind': 'building', **effects})
    route = conn.execute(
        "SELECT * FROM travel_routes WHERE status IN ('open','restricted') AND (from_location_id=? OR (bidirectional=1 AND to_location_id=?)) ORDER BY reliability ASC,id LIMIT 1",
        (loc, loc),
    ).fetchone()
    if route:
        access = max(20.0, 100.0 - magnitude)
        delay = 1.0 + magnitude / 100.0
        curc = conn.execute(
            """INSERT INTO route_conditions(route_id,condition_kind,label,start_day,accessibility,delay_factor,hazard_pressure,status,metadata_json)
               VALUES (?,'war_damage',?,?,?, ?,?,'active',?)""",
            (int(route['id']), f"damage from battle #{int(engagement['id'])}", day, access, delay, min(60.0, magnitude * .55),
             json.dumps({'source_engagement_id': int(engagement['id'])}, sort_keys=True)),
        )
        effects = {'route_condition_id': int(curc.lastrowid), 'accessibility': access, 'delay_factor': delay}
        cur = conn.execute("INSERT INTO war_damage_events(operation_id,engagement_id,day,location_id,target_kind,target_id,magnitude,effects_json) VALUES (?,?,?,?,?,?,?,?)",
                           (operation_id, int(engagement['id']), day, loc, 'route', int(route['id']), magnitude, json.dumps(effects, sort_keys=True)))
        out.append({'damage_event_id': int(cur.lastrowid), 'target_kind': 'route', **effects})
    # AGRI-01: war can disrupt a real field rather than only writing a generic war-damage meter.
    try:
        field = conn.execute("SELECT * FROM agriculture_fields WHERE location_id=? AND status IN ('active','damaged') ORDER BY hectares DESC,id LIMIT 1", (loc,)).fetchone()
    except sqlite3.OperationalError:
        field = None
    if field:
        from .agriculture import add_disruption
        factor = max(0.10, 1.0 - magnitude / 100.0)
        did = add_disruption(conn, int(field['id']), 'war', start_day=day, end_day=day+180, yield_factor=factor,
                             source_kind='combat_engagement', source_id=int(engagement['id']),
                             metadata={'operation_id': operation_id, 'magnitude': magnitude})
        effects = {'agriculture_disruption_id': did, 'yield_factor': factor}
        cur = conn.execute("INSERT INTO war_damage_events(operation_id,engagement_id,day,location_id,target_kind,target_id,magnitude,effects_json) VALUES (?,?,?,?,?,?,?,?)",
                           (operation_id, int(engagement['id']), day, loc, 'agriculture', int(field['id']), magnitude, json.dumps(effects, sort_keys=True)))
        out.append({'damage_event_id': int(cur.lastrowid), 'target_kind': 'agriculture', **effects})
    stock = conn.execute("SELECT * FROM commercial_stock WHERE location_id=? AND quantity>0 ORDER BY quantity DESC,id LIMIT 1", (loc,)).fetchone()
    if stock:
        lost = min(float(stock['quantity']), max(0.0, float(stock['quantity']) * magnitude / 220.0))
        if lost > 0:
            conn.execute("UPDATE commercial_stock SET quantity=quantity-?,updated_day=? WHERE id=?", (lost, day, int(stock['id'])))
            effects = {'quantity_lost': lost, 'good_id': int(stock['good_id']), 'enterprise_id': int(stock['enterprise_id'])}
            cur = conn.execute("INSERT INTO war_damage_events(operation_id,engagement_id,day,location_id,target_kind,target_id,magnitude,effects_json) VALUES (?,?,?,?,?,?,?,?)",
                               (operation_id, int(engagement['id']), day, loc, 'stock', int(stock['id']), magnitude, json.dumps(effects, sort_keys=True)))
            out.append({'damage_event_id': int(cur.lastrowid), 'target_kind': 'stock', **effects})
    conn.execute(
        "UPDATE market_conditions SET risk_pressure=MIN(100,risk_pressure+?),transport_pressure=MIN(100,transport_pressure+?),next_review_day=MIN(next_review_day,?) WHERE location_id=?",
        (magnitude * .45, magnitude * .35, day, loc),
    )
    return out


def _adjacent_safe_location(conn: sqlite3.Connection, source: int, day: int) -> int | None:
    routes = conn.execute(
        "SELECT * FROM travel_routes WHERE status IN ('open','restricted') AND (from_location_id=? OR (bidirectional=1 AND to_location_id=?)) ORDER BY reliability DESC,id",
        (source, source),
    ).fetchall()
    for r in routes:
        try:
            ev = evaluate_route_leg(conn, int(r['id']), source, day=day)
        except ValueError:
            continue
        if bool(ev['usable']) and float(ev['hazard']) < 80:
            return int(ev['target'])
    return None


def _displace_households(conn: sqlite3.Connection, operation_id: int | None, engagement: sqlite3.Row, day: int, magnitude: float) -> list[int]:
    from .household_life import schedule_household_migration
    if engagement['location_id'] is None or magnitude < 20:
        return []
    source = int(engagement['location_id'])
    destination = _adjacent_safe_location(conn, source, day)
    households = conn.execute("SELECT * FROM households WHERE location_id=? AND status IN ('active','declining') ORDER BY liquidity ASC,id", (source,)).fetchall()
    if not households:
        return []
    count = min(len(households), max(1, int(math.ceil(len(households) * min(.65, magnitude / 120.0)))))
    ids: list[int] = []
    for h in households[:count]:
        plan_id = None; status = 'stranded'
        if destination is not None:
            try:
                plan_id = schedule_household_migration(conn, int(h['id']), destination, day + 1,
                                                       reason=f"displaced by battle #{int(engagement['id'])}")
                status = 'planned'
            except ValueError:
                plan_id = None
        cur = conn.execute(
            """INSERT INTO war_displacement_events(operation_id,engagement_id,household_id,source_location_id,destination_location_id,
                   migration_plan_id,day,status,metadata_json) VALUES (?,?,?,?,?,?,?,?,?)""",
            (operation_id, int(engagement['id']), int(h['id']), source, destination, plan_id, day, status,
             json.dumps({'damage_magnitude': magnitude}, sort_keys=True)),
        )
        ids.append(int(cur.lastrowid))
    return ids


def _communication_lag(conn: sqlite3.Connection, from_location: int | None, recipient_actor_id: int, day: int) -> int:
    row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (recipient_actor_id,)).fetchone()
    if not row or row[0] is None or from_location is None or int(row[0]) == int(from_location):
        return 1
    current = int(from_location); total = 0.0
    path = find_route_path(conn, current, int(row[0]), day=day)
    if not path:
        return 14
    for rid in path:
        ev = evaluate_route_leg(conn, int(rid), current, day=day)
        total += float(ev['days']); current = int(ev['target'])
    return max(1, int(math.ceil(total)))


def _queue_battle_reports(conn: sqlite3.Connection, operation_id: int | None, engagement: sqlite3.Row,
                          casualty_summary: list[dict[str, Any]], day: int) -> list[int]:
    outcome = _j(engagement['outcome_json']); winner = outcome.get('winner') or 'no uncontested victor'
    total_k = sum(int(x.get('killed', 0)) for x in casualty_summary)
    total_w = sum(int(x.get('wounded', 0)) for x in casualty_summary)
    recipients: list[tuple[int, str, int | None]] = []
    if operation_id is not None:
        op = conn.execute("SELECT * FROM war_campaign_operations WHERE id=?", (operation_id,)).fetchone()
        for pid in (op['attacker_polity_id'], op['defender_polity_id']):
            if pid is None:
                continue
            r = conn.execute("SELECT ruler_actor_id FROM political_polities WHERE id=?", (int(pid),)).fetchone()
            if r and r[0] is not None and conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (int(r[0]),)).fetchone():
                recipients.append((int(r[0]), 'official', op['commander_actor_id']))
    # A local civilian head can carry a materially different eyewitness version.
    if engagement['location_id'] is not None:
        witness = conn.execute(
            """SELECT h.head_actor_id FROM households h JOIN actors a ON a.id=h.head_actor_id
               WHERE h.location_id=? AND h.status IN ('active','declining') AND a.status='active' ORDER BY h.id LIMIT 1""",
            (int(engagement['location_id']),),
        ).fetchone()
        if witness and all(int(witness[0]) != r[0] for r in recipients):
            recipients.append((int(witness[0]), 'eyewitness', int(witness[0])))
    ids: list[int] = []
    for recipient, kind, source_actor in recipients:
        if kind == 'official':
            est_k = max(0, int(round(total_k * .85)))
            est_w = max(0, int(round(total_w * .75)))
            text = f"Official dispatch: {winner} held the field after battle #{int(engagement['id'])}; reported losses are about {est_k} killed and {est_w} wounded."
            reliability = .78
        else:
            est_k = max(0, int(round(total_k * 1.35 + 1)))
            est_w = max(0, int(round(total_w * 1.20 + 1)))
            text = f"Eyewitness account: battle #{int(engagement['id'])} was confused and costly; the witness estimates roughly {est_k} killed and {est_w} wounded and is less certain about field control."
            reliability = .62
        lag = _communication_lag(conn, int(engagement['location_id']) if engagement['location_id'] is not None else None, recipient, day)
        cur = conn.execute(
            """INSERT INTO war_battle_reports(operation_id,engagement_id,version_kind,source_actor_id,recipient_actor_id,
                   observed_day,received_day,reliability,report_text,status,metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,'pending',?)""",
            (operation_id, int(engagement['id']), kind, source_actor, recipient, day, day + lag, reliability, text,
             json.dumps({'estimated_killed': est_k, 'estimated_wounded': est_w, 'winner_label': winner}, sort_keys=True)),
        )
        ids.append(int(cur.lastrowid))
    return ids


def _deliver_war_report(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> None:
    from .belief import ensure_claim, add_claim_evidence, observe_claim
    claim_id = ensure_claim(
        conn, f"war01:report:{int(row['id'])}", str(row['report_text']), subject_kind='battle',
        subject_id=int(row['engagement_id']), created_day=int(row['observed_day']), source_kind=f"war_{str(row['version_kind'])}_report",
    )
    evidence_id = add_claim_evidence(
        conn, claim_id, evidence_kind=f"war_{str(row['version_kind'])}_report", source_id=int(row['id']),
        source_actor_id=(int(row['source_actor_id']) if row['source_actor_id'] is not None else None),
        summary=str(row['report_text']), reliability=float(row['reliability']), salience=.9, domain_key='command',
        location_id=conn.execute("SELECT location_id FROM combat_engagements WHERE id=?", (int(row['engagement_id']),)).fetchone()[0],
        available_from_day=int(row['received_day']), metadata={'war_report_id': int(row['id']), 'version_kind': str(row['version_kind'])},
    )
    observe_claim(conn, int(row['recipient_actor_id']), claim_id, evidence_id, received_day=int(row['received_day']),
                  access_kind=f"war_{str(row['version_kind'])}", reason='war_report_received')
    conn.execute("UPDATE war_battle_reports SET status='delivered',delivered_day=?,claim_id=?,evidence_id=? WHERE id=?",
                 (day, claim_id, evidence_id, int(row['id'])))


def apply_battle_world_consequences(conn: sqlite3.Connection, engagement_id: int) -> dict[str, Any]:
    prior = conn.execute("SELECT summary_json FROM war_battle_aftermath WHERE engagement_id=?", (engagement_id,)).fetchone()
    if prior:
        return _j(prior[0])
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=? AND engagement_kind='battle'", (engagement_id,)).fetchone()
    if not eng or str(eng['status']) != 'resolved':
        raise ValueError("resolved battle required")
    link = conn.execute("SELECT operation_id FROM war_operation_engagements WHERE engagement_id=?", (engagement_id,)).fetchone()
    operation_id = int(link[0]) if link else None
    outcome = _j(eng['outcome_json']); winner_side_id = outcome.get('winner_side_id')
    day = int(eng['day_ended']) if eng['day_ended'] is not None else _day(conn)
    casualties: list[dict[str, Any]] = []
    if operation_id is not None:
        for force in conn.execute("SELECT * FROM war_campaign_forces WHERE operation_id=? AND battle_side_id IS NOT NULL ORDER BY id", (operation_id,)).fetchall():
            result = _apply_force_casualties(conn, force, eng, int(winner_side_id) if winner_side_id is not None else None, day)
            if result:
                casualties.append(result)
    damage = _damage_local_world(conn, operation_id, eng, day)
    magnitude = max([float(x.get('magnitude', 0)) for x in damage] + [8.0 + int(eng['stakes']) * 7.0])
    displaced = _displace_households(conn, operation_id, eng, day, magnitude)
    reports = _queue_battle_reports(conn, operation_id, eng, casualties, day)
    summary = {'engagement_id': engagement_id, 'operation_id': operation_id, 'casualties': casualties,
               'damage_events': damage, 'displacement_event_ids': displaced, 'report_ids': reports}
    conn.execute("INSERT INTO war_battle_aftermath(engagement_id,operation_id,applied_day,summary_json) VALUES (?,?,?,?)",
                 (engagement_id, operation_id, day, json.dumps(summary, sort_keys=True)))
    if operation_id is not None:
        conn.execute("UPDATE war_campaign_operations SET status='aftermath',ended_day=COALESCE(ended_day,?),next_review_day=? WHERE id=?",
                     (day, day + 30, operation_id))
    return summary


# ---------------------------------------------------------------------------
# WAR-01 information-bounded decision provider


def war_decision_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]):
    from .decision_runtime import DecisionCandidate
    out = []
    ops = conn.execute(
        """SELECT DISTINCT o.* FROM war_campaign_operations o LEFT JOIN political_polities ap ON ap.id=o.attacker_polity_id
           LEFT JOIN political_polities dp ON dp.id=o.defender_polity_id
           WHERE o.status NOT IN ('closed','cancelled') AND (o.commander_actor_id=? OR ap.ruler_actor_id=? OR dp.ruler_actor_id=?) ORDER BY o.id""",
        (actor_id, actor_id, actor_id),
    ).fetchall()
    for op in ops:
        report = conn.execute(
            "SELECT * FROM war_battle_reports WHERE operation_id=? AND recipient_actor_id=? AND status='delivered' ORDER BY delivered_day DESC,id DESC LIMIT 1",
            (int(op['id']), actor_id),
        ).fetchone()
        for force in conn.execute("SELECT * FROM war_campaign_forces WHERE operation_id=? AND status NOT IN ('demobilized','destroyed') ORDER BY id", (int(op['id']),)).fetchall():
            supplies = conn.execute("SELECT * FROM war_force_supplies WHERE force_id=?", (int(force['id']),)).fetchall()
            shortage = 0.0
            for s in supplies:
                need = max(1e-9, float(s['weekly_need']))
                shortage = max(shortage, max(0.0, 1.0 - float(s['on_hand']) / need))
            loss_fraction = 1.0 - float(force['personnel_available']) / max(1.0, float(force['personnel_initial']))
            basis = {'operation_id': int(op['id']), 'own_force_id': int(force['id']), 'own_force_records': True}
            claims = (); evidence = ()
            if report and report['claim_id'] is not None and report['evidence_id'] is not None:
                basis['war_report_id'] = int(report['id']); claims = (int(report['claim_id']),); evidence = (int(report['evidence_id']),)
            if shortage >= .25:
                out.append(DecisionCandidate(
                    key=f"war:resupply:{int(force['id'])}", provider_key='war', action_kind='resupply_force',
                    utility=5.2 + shortage * 3.0, rationale=f"Use known supply records to attempt resupply of {force['name']} through currently traversable routes.",
                    execution_kind='war_action', payload={'operation_id': int(op['id']), 'force_id': int(force['id'])},
                    information_basis={**basis, 'known_supply_shortage': round(shortage, 3)}, claim_ids=claims, evidence_ids=evidence,
                    tags=('war','supply','own_records'), risk=.2,
                ))
            if loss_fraction >= .18 or str(force['status']) == 'stalled':
                out.append(DecisionCandidate(
                    key=f"war:withdraw:{int(force['id'])}", provider_key='war', action_kind='withdraw_force',
                    utility=4.8 + loss_fraction * 3.0 + (1.0 if str(force['status']) == 'stalled' else 0.0),
                    rationale=f"Order {force['name']} to withdraw toward its campaign origin because own records show heavy loss or stalled movement.",
                    execution_kind='war_action', payload={'operation_id': int(op['id']), 'force_id': int(force['id'])},
                    information_basis={**basis, 'known_loss_fraction': round(loss_fraction, 3), 'known_status': str(force['status'])},
                    claim_ids=claims, evidence_ids=evidence, tags=('war','withdrawal','own_records'), risk=.3,
                ))
    return out


def execute_war_action(conn: sqlite3.Connection, actor_id: int, action_kind: str, payload: dict[str, Any], day: int) -> dict[str, Any]:
    force_id = int(payload.get('force_id') or 0)
    force = conn.execute("SELECT * FROM war_campaign_forces WHERE id=?", (force_id,)).fetchone()
    if not force:
        return {'summary': 'War action blocked: unknown force.', 'blocked': True}
    op = conn.execute("SELECT * FROM war_campaign_operations WHERE id=?", (int(force['operation_id']),)).fetchone()
    polities = [p for p in (op['attacker_polity_id'], op['defender_polity_id']) if p is not None]
    authorized = op['commander_actor_id'] is not None and int(op['commander_actor_id']) == actor_id
    for pid in polities:
        r = conn.execute("SELECT ruler_actor_id FROM political_polities WHERE id=?", (int(pid),)).fetchone()
        if r and r[0] is not None and int(r[0]) == actor_id:
            authorized = True
    if not authorized:
        return {'summary': 'War action blocked: actor lacks campaign authority.', 'blocked': True}
    if action_kind == 'resupply_force':
        before = {int(r['good_id']): float(r['on_hand']) for r in conn.execute("SELECT * FROM war_force_supplies WHERE force_id=?", (force_id,)).fetchall()}
        shortage = _review_physical_force_supply(conn, force_id, day)
        after = {int(r['good_id']): float(r['on_hand']) for r in conn.execute("SELECT * FROM war_force_supplies WHERE force_id=?", (force_id,)).fetchall()}
        gained = sum(max(0.0, after.get(k, 0.0) - v) for k, v in before.items())
        return {'summary': f'Resupply review for force #{force_id} moved {gained:.2f} physical supply units; remaining shortage pressure is {shortage:.1f}.', 'force_id': force_id}
    if action_kind == 'withdraw_force':
        conn.execute(
            "UPDATE war_campaign_forces SET status='withdrawing',current_route_id=NULL,segment_target_location_id=NULL,segment_due_day=NULL,next_review_day=? WHERE id=?",
            (day, force_id),
        )
        conn.execute("UPDATE war_campaign_operations SET status='marching',next_review_day=? WHERE id=?", (day, int(force['operation_id'])))
        return {'summary': f'Force #{force_id} has been ordered to withdraw through the ordinary route graph.', 'force_id': force_id}
    return {'summary': f'War action blocked: unsupported action {action_kind}.', 'blocked': True}


# ---------------------------------------------------------------------------
# Scheduler integration


def next_war_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    # A campaign/force/report can be created at the current world day by another owner or
    # an external trigger.  The simulation cursor asks for work strictly *after* that day;
    # without an overdue bridge, same-day WAR work would disappear from the event queue
    # until the terminal catch-up of a large advance.  Treat already-due WAR work as due
    # on the next simulated day.  Direct same-day process_due_war() calls remain valid.
    overdue = conn.execute(
        """SELECT 1 WHERE EXISTS (
               SELECT 1 FROM combat_engagements e WHERE e.engagement_kind='battle'
                 AND e.status IN ('prepared','active','resolved') AND e.day_started<=?
                 AND NOT EXISTS (SELECT 1 FROM military_campaigns c WHERE c.battle_engagement_id=e.id)
           ) OR EXISTS (SELECT 1 FROM military_campaigns WHERE status IN ('active','aftermath') AND next_review_day<=?)
             OR EXISTS (SELECT 1 FROM war_campaign_operations WHERE status NOT IN ('closed','cancelled') AND next_review_day<=?)
             OR EXISTS (SELECT 1 FROM war_campaign_forces WHERE status NOT IN ('demobilized','destroyed') AND next_review_day<=?)
             OR EXISTS (SELECT 1 FROM war_battle_reports WHERE status='pending' AND received_day<=?)""",
        (after_day, after_day, after_day, after_day, after_day),
    ).fetchone()
    candidates = []
    if overdue and after_day < end_day:
        candidates.append(after_day + 1)
    row = conn.execute(
        "SELECT MIN(day_started) FROM combat_engagements e WHERE e.engagement_kind='battle' AND e.status IN ('prepared','active','resolved') "
        "AND NOT EXISTS (SELECT 1 FROM military_campaigns c WHERE c.battle_engagement_id=e.id) AND day_started>? AND day_started<=?",
        (after_day, end_day),
    ).fetchone()
    if row and row[0] is not None:
        candidates.append(int(row[0]))
    for query in (
        "SELECT MIN(next_review_day) FROM military_campaigns WHERE status IN ('active','aftermath') AND next_review_day>? AND next_review_day<=?",
        "SELECT MIN(next_review_day) FROM war_campaign_operations WHERE status NOT IN ('closed','cancelled') AND next_review_day>? AND next_review_day<=?",
        "SELECT MIN(next_review_day) FROM war_campaign_forces WHERE status NOT IN ('demobilized','destroyed') AND next_review_day>? AND next_review_day<=?",
        "SELECT MIN(received_day) FROM war_battle_reports WHERE status='pending' AND received_day>? AND received_day<=?",
    ):
        r = conn.execute(query, (after_day, end_day)).fetchone()
        if r and r[0] is not None:
            candidates.append(int(r[0]))
    return min(candidates) if candidates else None


def process_due_war(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    created = reviewed = aftermath = closed = 0
    operations_reviewed = reports_delivered = consequences_applied = forces_moved = forces_stalled = 0
    # Deliver actor-relative reports only when their actual receipt day arrives.
    for report in conn.execute("SELECT * FROM war_battle_reports WHERE status='pending' AND received_day<=? ORDER BY received_day,id", (day,)).fetchall():
        _deliver_war_report(conn, report, day); reports_delivered += 1
    # Review strategic operations / route movement / physical stocks.
    for op in conn.execute(
        """SELECT DISTINCT o.* FROM war_campaign_operations o
           LEFT JOIN war_campaign_forces f ON f.operation_id=o.id
           WHERE o.status IN ('mobilizing','marching','engaged','stalled')
             AND (o.next_review_day<=? OR (f.status NOT IN ('demobilized','destroyed') AND f.next_review_day<=?))
           ORDER BY o.id""",
        (day, day),
    ).fetchall():
        r = _review_operation(conn, op, day); operations_reviewed += 1; forces_moved += r['forces_moved']; forces_stalled += r['forces_stalled']
    # Discover battles that are actual battle engagements, never duels/tournaments.
    for eng in conn.execute(
        "SELECT id FROM combat_engagements e WHERE engagement_kind='battle' AND status IN ('prepared','active','resolved') AND day_started<=? "
        "AND NOT EXISTS (SELECT 1 FROM military_campaigns c WHERE c.battle_engagement_id=e.id)", (day,)
    ).fetchall():
        register_campaign_for_battle(conn, int(eng[0])); created += 1
    # Project every resolved linked battle exactly once into the wider world.
    for eng in conn.execute(
        """SELECT e.id FROM combat_engagements e JOIN war_operation_engagements l ON l.engagement_id=e.id
           WHERE e.status='resolved' AND e.day_ended<=? AND NOT EXISTS (SELECT 1 FROM war_battle_aftermath a WHERE a.engagement_id=e.id) ORDER BY e.id""", (day,)
    ).fetchall():
        apply_battle_world_consequences(conn, int(eng[0])); consequences_applied += 1
    # Existing battle-linked military logistics / lagged aftermath.
    for camp in conn.execute("SELECT * FROM military_campaigns WHERE status IN ('active','aftermath') AND next_review_day<=? ORDER BY id", (day,)).fetchall():
        eng = conn.execute("SELECT * FROM combat_engagements WHERE id=?", (int(camp['battle_engagement_id']),)).fetchone()
        if camp['status'] == 'active' and eng and eng['status'] in ('prepared', 'active'):
            for row in conn.execute("SELECT * FROM campaign_side_logistics WHERE campaign_id=?", (int(camp['id']),)).fetchall():
                _review_active_side(conn, row, camp, day)
            conn.execute("UPDATE military_campaigns SET next_review_day=? WHERE id=?", (day + 7, int(camp['id']))); reviewed += 1
        elif camp['status'] == 'active':
            for row in conn.execute("SELECT * FROM campaign_side_logistics WHERE campaign_id=?", (int(camp['id']),)).fetchall():
                units = conn.execute("SELECT COALESCE(AVG(fatigue),0),COALESCE(AVG(100-readiness),0) FROM battle_units WHERE side_id=?", (int(row['battle_side_id']),)).fetchone()
                burden = _clamp(float(row['shortage_pressure']) * 0.5 + float(units[0]) * 0.25 + float(units[1]) * 0.25)
                conn.execute("UPDATE campaign_side_logistics SET aftermath_burden=?,next_review_day=? WHERE id=?", (burden, day + 30, int(row['id'])))
            conn.execute("UPDATE military_campaigns SET status='aftermath',ended_day=COALESCE(ended_day,?),next_review_day=? WHERE id=?",
                         (eng['day_ended'] if eng and eng['day_ended'] is not None else day, day + 30, int(camp['id'])))
            conn.execute("INSERT INTO war_logistics_events(campaign_id,day,event_kind,magnitude,metadata_json) VALUES (?,?,'demobilization_started',0,'{}')", (int(camp['id']), day)); aftermath += 1
        else:
            for row in conn.execute("SELECT * FROM campaign_side_logistics WHERE campaign_id=?", (int(camp['id']),)).fetchall():
                if row['polity_id'] is not None:
                    conn.execute("UPDATE military_logistics_profiles SET status='recovering',readiness=MAX(0,readiness-?),next_review_day=? WHERE polity_id=?",
                                 (float(row['aftermath_burden']) * 0.1, day + 30, int(row['polity_id'])))
            conn.execute("UPDATE military_campaigns SET status='closed',next_review_day=? WHERE id=?", (day, int(camp['id']))); closed += 1
    # Strategic operation aftermath also persists before closure.
    for op in conn.execute("SELECT * FROM war_campaign_operations WHERE status='aftermath' AND next_review_day<=? ORDER BY id", (day,)).fetchall():
        conn.execute("UPDATE war_campaign_operations SET status='closed',next_review_day=? WHERE id=?", (day, int(op['id'])))
        conn.execute("UPDATE war_campaign_forces SET status=CASE WHEN status='destroyed' THEN status ELSE 'demobilized' END,next_review_day=? WHERE operation_id=?",
                     (day, int(op['id'])))
    return {
        'campaigns_created': created, 'campaigns_reviewed': reviewed, 'aftermath_started': aftermath, 'campaigns_closed': closed,
        'operations_reviewed': operations_reviewed, 'forces_moved': forces_moved, 'forces_stalled': forces_stalled,
        'battle_consequences_applied': consequences_applied, 'reports_delivered': reports_delivered,
    }


def war_summary(conn):
    return {
        'profiles': int(conn.execute("SELECT COUNT(*) FROM military_logistics_profiles").fetchone()[0]),
        'active_campaigns': int(conn.execute("SELECT COUNT(*) FROM military_campaigns WHERE status='active'").fetchone()[0]),
        'aftermath_campaigns': int(conn.execute("SELECT COUNT(*) FROM military_campaigns WHERE status='aftermath'").fetchone()[0]),
        'events': int(conn.execute("SELECT COUNT(*) FROM war_logistics_events").fetchone()[0]),
        'operations': int(conn.execute("SELECT COUNT(*) FROM war_campaign_operations").fetchone()[0]),
        'active_forces': int(conn.execute("SELECT COUNT(*) FROM war_campaign_forces WHERE status NOT IN ('demobilized','destroyed')").fetchone()[0]),
        'battle_aftermath': int(conn.execute("SELECT COUNT(*) FROM war_battle_aftermath").fetchone()[0]),
        'displaced_households': int(conn.execute("SELECT COUNT(*) FROM war_displacement_events").fetchone()[0]),
    }
