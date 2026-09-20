from __future__ import annotations

import json
import math
import sqlite3
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def create_recipe(conn: sqlite3.Connection, recipe_key: str, name: str, output_good_id: int, *,
                  output_quantity: float = 1.0, base_duration_days: float = 1.0,
                  skill_domain: str = "craft", min_skill: float = 0.0,
                  metadata: dict[str, Any] | None = None) -> int:
    if output_quantity <= 0 or base_duration_days <= 0:
        raise ValueError("recipe output quantity and duration must be positive")
    if not conn.execute("SELECT 1 FROM market_goods WHERE id=?", (output_good_id,)).fetchone():
        raise ValueError("unknown recipe output good")
    conn.execute(
        """INSERT INTO craft_recipes(recipe_key,name,output_good_id,output_quantity,base_duration_days,
               skill_domain,min_skill,active,metadata_json)
           VALUES (?,?,?,?,?,?,?,1,?)
           ON CONFLICT(recipe_key) DO UPDATE SET name=excluded.name,output_good_id=excluded.output_good_id,
             output_quantity=excluded.output_quantity,base_duration_days=excluded.base_duration_days,
             skill_domain=excluded.skill_domain,min_skill=excluded.min_skill,active=1,metadata_json=excluded.metadata_json""",
        (recipe_key, name, output_good_id, float(output_quantity), float(base_duration_days), skill_domain,
         max(0.0, min(100.0, float(min_skill))), _json(metadata or {})),
    )
    return int(conn.execute("SELECT id FROM craft_recipes WHERE recipe_key=?", (recipe_key,)).fetchone()[0])


def add_recipe_input(conn: sqlite3.Connection, recipe_id: int, input_good_id: int, *,
                     group_key: str, units_per_batch: float = 1.0, preference_weight: float = 1.0,
                     metadata: dict[str, Any] | None = None) -> int:
    if units_per_batch <= 0 or preference_weight <= 0:
        raise ValueError("recipe input quantity and preference weight must be positive")
    cur = conn.execute(
        """INSERT INTO craft_recipe_inputs(recipe_id,group_key,input_good_id,units_per_batch,preference_weight,active,metadata_json)
           VALUES (?,?,?,?,?,1,?)
           ON CONFLICT(recipe_id,group_key,input_good_id) DO UPDATE SET units_per_batch=excluded.units_per_batch,
             preference_weight=excluded.preference_weight,active=1,metadata_json=excluded.metadata_json""",
        (recipe_id, group_key, input_good_id, float(units_per_batch), float(preference_weight), _json(metadata or {})),
    )
    if cur.lastrowid:
        return int(cur.lastrowid)
    return int(conn.execute(
        "SELECT id FROM craft_recipe_inputs WHERE recipe_id=? AND group_key=? AND input_good_id=?",
        (recipe_id, group_key, input_good_id),
    ).fetchone()[0])


def add_recipe_facility_requirement(conn: sqlite3.Connection, recipe_id: int, facility_kind: str, *,
                                    minimum_capacity: float = 1.0, minimum_condition: float = 20.0) -> None:
    conn.execute(
        """INSERT INTO craft_recipe_facility_requirements(recipe_id,facility_kind,minimum_capacity,minimum_condition)
           VALUES (?,?,?,?)
           ON CONFLICT(recipe_id,facility_kind) DO UPDATE SET minimum_capacity=excluded.minimum_capacity,
             minimum_condition=excluded.minimum_condition""",
        (recipe_id, facility_kind, max(0.01, float(minimum_capacity)), max(0.0, min(100.0, float(minimum_condition)))),
    )


def add_facility(conn: sqlite3.Connection, enterprise_id: int, location_id: int, facility_kind: str, name: str, *,
                 capacity: float = 1.0, condition: float = 100.0,
                 metadata: dict[str, Any] | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO craft_facilities(enterprise_id,location_id,facility_kind,name,capacity,condition,active,metadata_json)
           VALUES (?,?,?,?,?,?,1,?)""",
        (enterprise_id, location_id, facility_kind, name, max(0.01, float(capacity)),
         max(0.0, min(100.0, float(condition))), _json(metadata or {})),
    )
    return int(cur.lastrowid)


def bind_recipe_to_site(conn: sqlite3.Connection, production_site_id: int, recipe_id: int, *, is_default: bool = True) -> None:
    site = conn.execute("SELECT good_id FROM production_sites WHERE id=? AND active=1", (production_site_id,)).fetchone()
    recipe = conn.execute("SELECT output_good_id FROM craft_recipes WHERE id=? AND active=1", (recipe_id,)).fetchone()
    if not site or not recipe:
        raise ValueError("active site and recipe required")
    if int(site["good_id"]) != int(recipe["output_good_id"]):
        raise ValueError("recipe output does not match production-site good")
    if is_default:
        conn.execute("UPDATE craft_site_recipes SET is_default=0 WHERE production_site_id=?", (production_site_id,))
    conn.execute(
        """INSERT INTO craft_site_recipes(production_site_id,recipe_id,is_default,active)
           VALUES (?,?,?,1)
           ON CONFLICT(production_site_id,recipe_id) DO UPDATE SET is_default=excluded.is_default,active=1""",
        (production_site_id, recipe_id, 1 if is_default else 0),
    )
    conn.execute("UPDATE production_sites SET production_mode='tracked' WHERE id=?", (production_site_id,))


def assign_site_worker(conn: sqlite3.Connection, production_site_id: int, actor_id: int, *,
                       role: str = "craftsperson", capacity_share: float = 1.0, active: bool = True) -> None:
    conn.execute(
        """INSERT INTO craft_site_workers(production_site_id,actor_id,role,capacity_share,status,assigned_day)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(production_site_id,actor_id) DO UPDATE SET role=excluded.role,
             capacity_share=excluded.capacity_share,status=excluded.status""",
        (production_site_id, actor_id, role, max(0.01, float(capacity_share)), "active" if active else "inactive", _day(conn)),
    )


def _craft_skill(conn: sqlite3.Connection, production_site_id: int, skill_domain: str, site_skill: float) -> tuple[float, list[int]]:
    rows = conn.execute(
        """SELECT w.actor_id,w.capacity_share,COALESCE(MAX(ac.score),0) AS score
           FROM craft_site_workers w
           LEFT JOIN competence_domains d ON d.domain_key=?
           LEFT JOIN actor_competence ac ON ac.actor_id=w.actor_id AND ac.domain_id=d.id
           WHERE w.production_site_id=? AND w.status='active'
           GROUP BY w.actor_id,w.capacity_share ORDER BY score DESC,w.actor_id""",
        (skill_domain, production_site_id),
    ).fetchall()
    if not rows:
        return max(0.0, min(100.0, float(site_skill))), []
    total = sum(float(r["capacity_share"]) for r in rows) or 1.0
    weighted = sum(float(r["score"]) * float(r["capacity_share"]) for r in rows) / total
    return max(0.0, min(100.0, weighted)), [int(r["actor_id"]) for r in rows]


def validate_recipe_dependency_closure(conn: sqlite3.Connection, recipe_id: int, enterprise_id: int | None = None) -> dict[str, Any]:
    """Validate structural material/facility closure at the selected tracked resolution."""
    recipe = conn.execute("SELECT * FROM craft_recipes WHERE id=? AND active=1", (recipe_id,)).fetchone()
    if not recipe:
        return {"closed": False, "missing": ["recipe"]}
    target_loc = None
    if enterprise_id is not None:
        erow = conn.execute("SELECT location_id FROM civilian_enterprises WHERE id=?", (enterprise_id,)).fetchone()
        target_loc = int(erow[0]) if erow and erow[0] is not None else None
    if target_loc is not None:
        from .ecology import find_route_path

    groups = conn.execute(
        "SELECT DISTINCT group_key FROM craft_recipe_inputs WHERE recipe_id=? AND active=1 ORDER BY group_key", (recipe_id,)
    ).fetchall()
    missing: list[str] = []
    for grow in groups:
        group = str(grow[0])
        opts = conn.execute(
            "SELECT input_good_id FROM craft_recipe_inputs WHERE recipe_id=? AND group_key=? AND active=1",
            (recipe_id, group),
        ).fetchall()
        possible = False
        for opt in opts:
            gid = int(opt[0])
            if enterprise_id is not None and conn.execute(
                "SELECT 1 FROM commercial_stock WHERE enterprise_id=? AND good_id=? AND quantity>0 LIMIT 1", (enterprise_id, gid)
            ).fetchone():
                possible = True
            if not possible:
                offers = conn.execute(
                    """SELECT o.location_id FROM merchant_trade_offers o JOIN commercial_stock s ON s.id=o.stock_id
                       WHERE o.good_id=? AND o.status='open' AND o.quantity_available>0 AND s.quantity>0""", (gid,)
                ).fetchall()
                for off in offers:
                    source_loc = int(off[0])
                    if target_loc is None or source_loc == target_loc or find_route_path(conn, source_loc, target_loc, day=_day(conn)):
                        possible = True; break
            if not possible:
                sources = conn.execute(
                    """SELECT e.location_id FROM production_sites ps JOIN civilian_enterprises e ON e.id=ps.enterprise_id
                       WHERE ps.good_id=? AND ps.active=1 AND e.location_id IS NOT NULL""", (gid,)
                ).fetchall()
                for src in sources:
                    source_loc = int(src[0])
                    if target_loc is None or source_loc == target_loc or find_route_path(conn, source_loc, target_loc, day=_day(conn)):
                        possible = True; break
            if possible:
                break
        if not possible:
            missing.append(f"input_group:{group}:no_source_path")
    if enterprise_id is not None:
        for req in conn.execute(
            "SELECT * FROM craft_recipe_facility_requirements WHERE recipe_id=? ORDER BY facility_kind", (recipe_id,)
        ).fetchall():
            q = """SELECT 1 FROM craft_facilities WHERE enterprise_id=? AND facility_kind=? AND active=1
                   AND capacity>=? AND condition>=?"""
            args: list[Any] = [enterprise_id, str(req["facility_kind"]), float(req["minimum_capacity"]), float(req["minimum_condition"])]
            if target_loc is not None:
                q += " AND location_id=?"; args.append(target_loc)
            q += " LIMIT 1"
            if not conn.execute(q, tuple(args)).fetchone():
                missing.append(f"facility:{req['facility_kind']}")
    return {"closed": not missing, "missing": missing}


def create_production_order(conn: sqlite3.Connection, production_site_id: int, requested_output_qty: float, *,
                            recipe_id: int | None = None, priority: int = 50, due_day: int | None = None,
                            metadata: dict[str, Any] | None = None) -> int:
    if requested_output_qty <= 0:
        raise ValueError("production quantity must be positive")
    site = conn.execute(
        """SELECT ps.*,e.location_id FROM production_sites ps JOIN civilian_enterprises e ON e.id=ps.enterprise_id
           WHERE ps.id=? AND ps.active=1""", (production_site_id,)
    ).fetchone()
    if not site:
        raise ValueError("unknown active production site")
    if recipe_id is None:
        r = conn.execute(
            """SELECT recipe_id FROM craft_site_recipes WHERE production_site_id=? AND active=1
               ORDER BY is_default DESC,recipe_id LIMIT 1""", (production_site_id,)
        ).fetchone()
        if not r:
            raise ValueError("production site has no bound craft recipe")
        recipe_id = int(r[0])
    if not conn.execute(
        "SELECT 1 FROM craft_site_recipes WHERE production_site_id=? AND recipe_id=? AND active=1",
        (production_site_id, recipe_id),
    ).fetchone():
        raise ValueError("recipe is not bound to production site")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO craft_production_orders(production_site_id,recipe_id,requested_output_qty,priority,status,
               created_day,due_day,next_review_day,blocked_reason,blocked_detail_json,metadata_json)
           VALUES (?,?,?,?, 'queued',?,?,?,NULL,'{}',?)""",
        (production_site_id, recipe_id, float(requested_output_qty), max(0, min(100, int(priority))), day,
         due_day, day + 1, _json(metadata or {})),
    )
    return int(cur.lastrowid)


def _observed_unit_price(conn: sqlite3.Connection, enterprise_id: int, location_id: int, good_id: int, day: int) -> float | None:
    row = conn.execute(
        """SELECT observed_price FROM merchant_market_observations
           WHERE enterprise_id=? AND location_id=? AND good_id=? AND received_day<=?
           ORDER BY observed_day DESC,received_day DESC,id DESC LIMIT 1""",
        (enterprise_id, location_id, good_id, day),
    ).fetchone()
    return float(row[0]) if row else None


def inspect_order(conn: sqlite3.Connection, order_id: int, *, day: int | None = None) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    row = conn.execute(
        """SELECT o.*,ps.enterprise_id,ps.location_id AS ignored,ps.capacity_per_30,ps.efficiency,ps.skilled_labor,
                  e.location_id,r.output_quantity,r.base_duration_days,r.skill_domain,r.min_skill,r.output_good_id
           FROM craft_production_orders o
           JOIN production_sites ps ON ps.id=o.production_site_id
           JOIN civilian_enterprises e ON e.id=ps.enterprise_id
           JOIN craft_recipes r ON r.id=o.recipe_id WHERE o.id=?""".replace(",ps.location_id AS ignored", ""),
        (order_id,),
    ).fetchone()
    if not row:
        raise ValueError("unknown craft order")
    if row["location_id"] is None:
        return {"feasible": False, "reason": "site_has_no_location", "missing": []}
    enterprise_id = int(row["enterprise_id"]); loc = int(row["location_id"])
    batches = float(row["requested_output_qty"]) / float(row["output_quantity"])
    facility_rows = []
    missing_facilities = []
    for req in conn.execute("SELECT * FROM craft_recipe_facility_requirements WHERE recipe_id=?", (int(row["recipe_id"]),)).fetchall():
        f = conn.execute(
            """SELECT * FROM craft_facilities WHERE enterprise_id=? AND location_id=? AND facility_kind=? AND active=1
               AND capacity>=? AND condition>=? ORDER BY condition DESC,capacity DESC,id LIMIT 1""",
            (enterprise_id, loc, str(req["facility_kind"]), float(req["minimum_capacity"]), float(req["minimum_condition"])),
        ).fetchone()
        if not f:
            missing_facilities.append(str(req["facility_kind"]))
        else:
            facility_rows.append(f)
    skill, workers = _craft_skill(conn, int(row["production_site_id"]), str(row["skill_domain"]), float(row["skilled_labor"]))
    if skill + 1e-9 < float(row["min_skill"]):
        return {"feasible": False, "reason": "insufficient_labor_skill", "skill": skill,
                "minimum_skill": float(row["min_skill"]), "workers": workers, "missing": []}
    if missing_facilities:
        return {"feasible": False, "reason": "missing_facility", "missing_facilities": missing_facilities,
                "skill": skill, "workers": workers, "missing": []}
    groups = conn.execute(
        "SELECT DISTINCT group_key FROM craft_recipe_inputs WHERE recipe_id=? AND active=1 ORDER BY group_key",
        (int(row["recipe_id"]),),
    ).fetchall()
    selections: list[dict[str, Any]] = []; missing: list[dict[str, Any]] = []
    for grow in groups:
        group = str(grow[0]); choices = []
        for opt in conn.execute(
            """SELECT * FROM craft_recipe_inputs WHERE recipe_id=? AND group_key=? AND active=1 ORDER BY id""",
            (int(row["recipe_id"]), group),
        ).fetchall():
            needed = float(opt["units_per_batch"]) * batches
            stock = conn.execute(
                """SELECT * FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=? AND quantity>=?
                   ORDER BY quantity DESC,id LIMIT 1""",
                (enterprise_id, loc, int(opt["input_good_id"]), needed),
            ).fetchone()
            observed = _observed_unit_price(conn, enterprise_id, loc, int(opt["input_good_id"]), day)
            score = (observed * needed / float(opt["preference_weight"])) if observed is not None else (needed / float(opt["preference_weight"]))
            choices.append((stock is not None, score, int(opt["id"]), opt, stock, needed, observed))
        # Choose the technically permitted material from enterprise-accessible price records first.
        # Do not silently fall back to a dearer alternative merely because it is already on the shelf:
        # a deliberate steel choice with insufficient steel is a procurement shortage, not copper production.
        chosen = min(choices, key=lambda c: (c[1], c[2]))
        opt, stock, needed, observed = chosen[3], chosen[4], chosen[5], chosen[6]
        if stock is None:
            missing.append({
                "group_key": group,
                "preferred_input_good_id": int(opt["input_good_id"]),
                "options": [{"input_good_id": int(opt["input_good_id"]), "required_qty": needed,
                             "observed_unit_price": observed}],
                "technically_valid_alternatives": [int(c[3]["input_good_id"]) for c in choices],
            })
            continue
        selections.append({"group_key": group, "recipe_input_id": int(opt["id"]), "input_good_id": int(opt["input_good_id"]),
                           "stock_id": int(stock["id"]), "required_qty": needed, "observed_unit_price": observed})
    facility_condition = min([float(f["condition"]) for f in facility_rows], default=100.0)
    return {"feasible": not missing, "reason": None if not missing else "missing_input", "missing": missing,
            "selections": selections, "skill": skill, "workers": workers, "facility_condition": facility_condition,
            "batches": batches, "enterprise_id": enterprise_id, "location_id": loc, "output_good_id": int(row["output_good_id"]),
            "base_duration_days": float(row["base_duration_days"]), "capacity_per_30": float(row["capacity_per_30"]),
            "efficiency": float(row["efficiency"])}


def _event(conn: sqlite3.Connection, order_id: int, day: int, event_kind: str, detail: dict[str, Any]) -> None:
    conn.execute("INSERT INTO craft_order_events(order_id,day,event_kind,detail_json) VALUES (?,?,?,?)",
                 (order_id, day, event_kind, _json(detail)))


def _reserve_and_start(conn: sqlite3.Connection, order: sqlite3.Row, inspection: dict[str, Any], day: int) -> None:
    for sel in inspection["selections"]:
        stock = conn.execute("SELECT quantity FROM commercial_stock WHERE id=?", (int(sel["stock_id"]),)).fetchone()
        qty = float(sel["required_qty"])
        if not stock or float(stock[0]) + 1e-9 < qty:
            raise RuntimeError("input stock changed before reservation")
        conn.execute("UPDATE commercial_stock SET quantity=quantity-?,updated_day=? WHERE id=?", (qty, day, int(sel["stock_id"])))
        conn.execute(
            """INSERT INTO craft_input_reservations(order_id,recipe_input_id,stock_id,good_id,quantity_reserved,
                   quantity_consumed,status,reserved_day,consumed_day)
               VALUES (?,?,?,?,?,?,'consumed',?,?)""",
            (int(order["id"]), int(sel["recipe_input_id"]), int(sel["stock_id"]), int(sel["input_good_id"]),
             qty, qty, day, day),
        )
    efficiency = max(0.1, float(inspection["efficiency"]) / 100.0)
    skill_factor = max(0.25, float(inspection["skill"]) / 100.0)
    facility_factor = max(0.25, float(inspection["facility_condition"]) / 100.0)
    capacity_days = 30.0 * float(order["requested_output_qty"]) / max(0.01, float(inspection["capacity_per_30"]))
    recipe_days = float(inspection["base_duration_days"]) * float(inspection["batches"])
    duration = max(recipe_days, capacity_days) / max(0.1, (efficiency * skill_factor * facility_factor) ** (1/3))
    completion = day + max(1, int(math.ceil(duration)))
    conn.execute(
        """UPDATE craft_production_orders SET status='in_progress',started_day=COALESCE(started_day,?),next_review_day=?,
           blocked_reason=NULL,blocked_detail_json='{}',selected_inputs_json=? WHERE id=?""",
        (day, completion, _json(inspection["selections"]), int(order["id"])),
    )
    _event(conn, int(order["id"]), day, "started", {"completion_day": completion, "inputs": inspection["selections"],
                                                     "skill": inspection["skill"], "workers": inspection["workers"]})


def _complete_order(conn: sqlite3.Connection, order: sqlite3.Row, day: int) -> None:
    details = inspect_order(conn, int(order["id"]), day=day)
    recipe = conn.execute("SELECT * FROM craft_recipes WHERE id=?", (int(order["recipe_id"]),)).fetchone()
    site = conn.execute("SELECT * FROM production_sites WHERE id=?", (int(order["production_site_id"]),)).fetchone()
    ent = conn.execute("SELECT location_id FROM civilian_enterprises WHERE id=?", (int(site["enterprise_id"]),)).fetchone()
    loc = int(ent[0])
    qty = float(order["requested_output_qty"])
    skill = float(details.get("skill", site["skilled_labor"]))
    facility = float(details.get("facility_condition", 100.0))
    quality = max(1.0, min(100.0, 0.40 * skill + 0.35 * float(site["efficiency"]) + 0.25 * facility))
    conn.execute(
        """INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?) ON CONFLICT(enterprise_id,location_id,good_id) DO UPDATE SET
             quantity=commercial_stock.quantity+excluded.quantity,updated_day=excluded.updated_day""",
        (int(site["enterprise_id"]), loc, int(recipe["output_good_id"]), qty, day,
         _json({"authority":"ENGINE_DERIVED", "source":"craft_order", "order_id":int(order["id"]), "quality":quality})),
    )
    stock_id = int(conn.execute(
        "SELECT id FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",
        (int(site["enterprise_id"]), loc, int(recipe["output_good_id"])),
    ).fetchone()[0])
    conn.execute(
        "INSERT INTO craft_output_lots(order_id,stock_id,good_id,quantity,quality,produced_day) VALUES (?,?,?,?,?,?)",
        (int(order["id"]), stock_id, int(recipe["output_good_id"]), qty, quality, day),
    )
    conn.execute(
        "UPDATE craft_production_orders SET status='completed',completed_day=?,next_review_day=?,quality=? WHERE id=?",
        (day, day, quality, int(order["id"])),
    )
    _event(conn, int(order["id"]), day, "completed", {"stock_id": stock_id, "quantity": qty, "quality": quality})


def process_order(conn: sqlite3.Connection, order_id: int, day: int) -> bool:
    order = conn.execute("SELECT * FROM craft_production_orders WHERE id=?", (order_id,)).fetchone()
    if not order or str(order["status"]) in {"completed", "cancelled"}:
        return False
    if str(order["status"]) == "in_progress":
        if int(order["next_review_day"]) <= day:
            _complete_order(conn, order, day)
            return True
        return False
    inspection = inspect_order(conn, order_id, day=day)
    if inspection["feasible"]:
        _reserve_and_start(conn, order, inspection, day)
        return True
    reason = str(inspection["reason"] or "blocked")
    status = {"missing_input":"waiting_input", "missing_facility":"waiting_facility",
              "insufficient_labor_skill":"waiting_labor"}.get(reason, "blocked")
    conn.execute(
        """UPDATE craft_production_orders SET status=?,blocked_reason=?,blocked_detail_json=?,next_review_day=? WHERE id=?""",
        (status, reason, _json(inspection), day + 3, order_id),
    )
    _event(conn, order_id, day, "blocked", {"reason": reason, "detail": inspection})
    return True


def next_craft_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    row = conn.execute(
        """SELECT MIN(next_review_day) FROM craft_production_orders
           WHERE status IN ('queued','waiting_input','waiting_facility','waiting_labor','in_progress','blocked')
             AND next_review_day>? AND next_review_day<=?""", (after_day, end_day)
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def process_due_craft(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    rows = conn.execute(
        """SELECT id FROM craft_production_orders
           WHERE status IN ('queued','waiting_input','waiting_facility','waiting_labor','in_progress','blocked')
             AND next_review_day<=? ORDER BY priority DESC,next_review_day,id""", (day,)
    ).fetchall()
    changed = 0
    for row in rows:
        before = conn.execute("SELECT status FROM craft_production_orders WHERE id=?", (int(row[0]),)).fetchone()[0]
        if process_order(conn, int(row[0]), day):
            after = conn.execute("SELECT status FROM craft_production_orders WHERE id=?", (int(row[0]),)).fetchone()[0]
            changed += int(before != after or after in {"waiting_input","waiting_facility","waiting_labor","blocked"})
            if event_logger and after == "completed":
                event_logger(day=day, event_type="craft:order_completed", title="Production order completed",
                             summary=f"Tracked production order #{int(row[0])} completed with conserved inputs and output.",
                             severity=1, source_actor_id=None, target_actor_ids=())
    return {"due": len(rows), "changed": changed}


def _missing_good_needs(conn: sqlite3.Connection, order: sqlite3.Row) -> list[dict[str, Any]]:
    try:
        detail = json.loads(order["blocked_detail_json"] or "{}")
    except Exception:
        return []
    needs = []
    for group in detail.get("missing") or []:
        for opt in group.get("options") or []:
            needs.append({"group_key": group.get("group_key"), **opt})
    return needs


def craft_decision_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]):
    """Procurement candidates for actual blocked orders, executed by the merchant domain owner."""
    from .decision_runtime import DecisionCandidate
    try:
        from .merchant import authorized_enterprises
        enterprise_ids = [int(e["id"]) for e in authorized_enterprises(conn, actor_id)]
    except Exception:
        return []
    out: list[DecisionCandidate] = []
    for eid in enterprise_ids:
        orders = conn.execute(
            """SELECT o.* FROM craft_production_orders o JOIN production_sites ps ON ps.id=o.production_site_id
               WHERE ps.enterprise_id=? AND o.status='waiting_input' ORDER BY o.priority DESC,o.id LIMIT 4""", (eid,)
        ).fetchall()
        ent = conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?", (eid,)).fetchone()
        cash = float(ent[0] if ent else 0)
        for order in orders:
            for need in _missing_good_needs(conn, order):
                gid = int(need["input_good_id"]); required = float(need["required_qty"])
                offers = conn.execute(
                    """SELECT a.received_day AS awareness_received,o.* FROM merchant_offer_awareness a
                       JOIN merchant_trade_offers o ON o.id=a.offer_id
                       WHERE a.enterprise_id=? AND a.received_day<=? AND o.good_id=? AND o.status='open'
                         AND o.quantity_available>0 AND (o.expires_day IS NULL OR o.expires_day>=?)
                       ORDER BY o.unit_price,o.id""", (eid, day, gid, day)
                ).fetchall()
                for offer in offers:
                    if int(offer["seller_enterprise_id"]) == eid:
                        continue
                    qty = min(required, float(offer["quantity_available"]))
                    cost = qty * float(offer["unit_price"])
                    if qty + 1e-9 < required or cost > cash + 1e-9:
                        continue
                    out.append(DecisionCandidate(
                        key=f"craft:procure:{int(order['id'])}:{int(offer['id'])}", provider_key="craft",
                        action_kind="accept_trade_offer", utility=6.2 + float(order["priority"]) / 100.0,
                        rationale=f"Procure the specific missing input for tracked production order #{int(order['id'])} from an observed offer.",
                        execution_kind="merchant_action",
                        payload={"enterprise_id": eid, "offer_id": int(offer["id"]), "quantity": qty,
                                 "settlement_kind": "cash_on_delivery", "production_order_id": int(order["id"])},
                        information_basis={"production_order_id": int(order["id"]), "offer_awareness_received_day": int(offer["awareness_received"]),
                                           "missing_group": need.get("group_key"), "required_qty": required},
                        tags=("craft", "procurement", "bounded_information"), estimated_cost=cost, risk=.12,
                    ))
                    break
    return out


def craft_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "recipes": int(conn.execute("SELECT COUNT(*) FROM craft_recipes WHERE active=1").fetchone()[0]),
        "facilities": int(conn.execute("SELECT COUNT(*) FROM craft_facilities WHERE active=1").fetchone()[0]),
        "open_orders": int(conn.execute("SELECT COUNT(*) FROM craft_production_orders WHERE status NOT IN ('completed','cancelled')").fetchone()[0]),
        "completed_orders": int(conn.execute("SELECT COUNT(*) FROM craft_production_orders WHERE status='completed'").fetchone()[0]),
        "reserved_or_consumed_input": float(conn.execute("SELECT COALESCE(SUM(quantity_consumed),0) FROM craft_input_reservations").fetchone()[0]),
        "output_quantity": float(conn.execute("SELECT COALESCE(SUM(quantity),0) FROM craft_output_lots").fetchone()[0]),
    }
