from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any, Callable

from .civilian_life import create_building, process_due_civilian_life, civilian_life_summary
from .business import next_business_due_day, process_due_businesses, business_ecology_summary
from .household_life import next_household_life_due_day, process_due_household_life, household_life_summary
from .ecology import production_factor as ecology_production_factor, environmental_transport_pressure


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _seed(conn: sqlite3.Connection, salt: int) -> int:
    row = conn.execute("SELECT rng_seed,current_day FROM world_state WHERE id=1").fetchone()
    return int(row[0]) * 1_000_003 + int(row[1]) * 9_973 + int(salt)


def create_household(conn: sqlite3.Connection, name: str, *, head_actor_id: int | None = None,
                     location_id: int | None = None, wealth: float = 0, liquidity: float = 0,
                     staff_capacity: float = 50, cohesion: float = 70, hospitality: float = 50,
                     metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO households(name,head_actor_id,location_id,wealth,liquidity,staff_capacity,cohesion,hospitality,metadata_json,created_day,updated_day)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (name, head_actor_id, location_id, wealth, liquidity, staff_capacity, cohesion, hospitality,
         json.dumps(metadata or {}, sort_keys=True), day, day),
    )
    hid = int(cur.lastrowid)
    if head_actor_id is not None:
        conn.execute(
            "INSERT OR IGNORE INTO household_members(household_id,actor_id,role,authority,dependency,joined_day) VALUES (?,?,?,?,?,?)",
            (hid, head_actor_id, "head", 100, 0, day),
        )
    return hid


def add_household_member(conn: sqlite3.Connection, household_id: int, actor_id: int, *, role: str = "member",
                         authority: float = 20, dependency: float = 20) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO household_members(household_id,actor_id,role,authority,dependency,joined_day,status)
           VALUES (?,?,?,?,?,?, 'active')""",
        (household_id, actor_id, role, authority, dependency, _day(conn)),
    )


def create_enterprise(conn: sqlite3.Connection, name: str, enterprise_kind: str, *, owner_actor_id: int | None = None,
                      institution_actor_id: int | None = None, household_id: int | None = None,
                      location_id: int | None = None, capital: float = 0, cash: float = 0, debt: float = 0,
                      reputation: float = 50, admin_quality: float = 50, labor_capacity: float = 50,
                      risk_tolerance: float = 50, metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO civilian_enterprises(name,enterprise_kind,owner_actor_id,institution_actor_id,household_id,location_id,
                                             capital,cash,debt,reputation,admin_quality,labor_capacity,risk_tolerance,metadata_json,created_day,updated_day)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (name, enterprise_kind, owner_actor_id, institution_actor_id, household_id, location_id, capital, cash, debt,
         reputation, admin_quality, labor_capacity, risk_tolerance, json.dumps(metadata or {}, sort_keys=True), day, day),
    )
    return int(cur.lastrowid)


def ensure_good(conn: sqlite3.Connection, good_key: str, name: str, category: str, base_price: float, *,
                unit: str = "unit", perishability: float = 0, skill_intensity: float = 0.5,
                luxury: float = 0, notes: str | None = None) -> int:
    conn.execute(
        """INSERT OR IGNORE INTO market_goods(good_key,name,category,base_price,unit,perishability,skill_intensity,luxury,notes)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (good_key, name, category, base_price, unit, perishability, skill_intensity, luxury, notes),
    )
    return int(conn.execute("SELECT id FROM market_goods WHERE good_key=?", (good_key,)).fetchone()[0])


def set_market_condition(conn: sqlite3.Connection, location_id: int, good_id: int, *, supply: float = 50,
                         demand: float = 50, transport_pressure: float = 0, risk_pressure: float = 0,
                         tax_pressure: float = 0, cadence_days: int = 30,
                         metadata: dict[str, Any] | None = None) -> None:
    base = float(conn.execute("SELECT base_price FROM market_goods WHERE id=?", (good_id,)).fetchone()[0])
    price = _price(base, supply, demand, transport_pressure, risk_pressure, tax_pressure)
    day = _day(conn)
    conn.execute(
        """INSERT INTO market_conditions(location_id,good_id,supply,demand,transport_pressure,risk_pressure,tax_pressure,current_price,last_review_day,next_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(location_id,good_id) DO UPDATE SET supply=excluded.supply,demand=excluded.demand,
             transport_pressure=excluded.transport_pressure,risk_pressure=excluded.risk_pressure,tax_pressure=excluded.tax_pressure,
             current_price=excluded.current_price,last_review_day=excluded.last_review_day,next_review_day=excluded.next_review_day,
             metadata_json=excluded.metadata_json""",
        (location_id, good_id, supply, demand, transport_pressure, risk_pressure, tax_pressure, price,
         day, day + max(1, cadence_days), json.dumps(metadata or {}, sort_keys=True)),
    )


def _price(base: float, supply: float, demand: float, transport: float, risk: float, tax: float) -> float:
    # Bounded directional economics. Supply/demand dominate; friction adds premiums.
    scarcity = (demand + 10.0) / (supply + 10.0)
    scarcity = max(0.35, min(3.0, scarcity))
    friction = 1.0 + 0.0035 * max(0, transport) + 0.0025 * max(0, risk) + 0.002 * max(0, tax)
    return round(max(0.01, base * scarcity * friction), 4)


def add_production_site(conn: sqlite3.Connection, enterprise_id: int, good_id: int, *, capacity_per_30: float = 10,
                        efficiency: float = 50, material_access: float = 50, skilled_labor: float = 50,
                        inventory: float = 0, notes: str | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO production_sites(enterprise_id,good_id,capacity_per_30,efficiency,material_access,skilled_labor,inventory,last_resolved_day,notes)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (enterprise_id, good_id, capacity_per_30, efficiency, material_access, skilled_labor, inventory, _day(conn), notes),
    )
    return int(cur.lastrowid)


def create_project(conn: sqlite3.Connection, title: str, project_kind: str, *, patron_actor_id: int | None = None,
                   creator_actor_id: int | None = None, enterprise_id: int | None = None,
                   location_id: int | None = None, target_day: int | None = None,
                   quality_potential: float = 50, funding: float = 50, material_access: float = 50,
                   skilled_labor: float = 50, metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO civilian_projects(title,project_kind,patron_actor_id,creator_actor_id,enterprise_id,location_id,
                                         started_day,target_day,quality_potential,funding,material_access,skilled_labor,status,last_resolved_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?,?)""",
        (title, project_kind, patron_actor_id, creator_actor_id, enterprise_id, location_id, day, target_day,
         quality_potential, funding, material_access, skilled_labor, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def create_cultural_object(conn: sqlite3.Connection, title: str, object_kind: str, *, creator_actor_id: int | None = None,
                           workshop_actor_id: int | None = None, created_day: int | None = None,
                           project_id: int | None = None, owner_actor_id: int | None = None,
                           household_id: int | None = None, location_id: int | None = None,
                           quality: float = 50, market_value: float = 0, significance: str = "ordinary",
                           metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn) if created_day is None else int(created_day)
    cur = conn.execute(
        """INSERT INTO cultural_objects(title,object_kind,creator_actor_id,workshop_actor_id,created_day,project_id,
                                        current_owner_actor_id,current_household_id,current_location_id,quality,market_value,significance,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (title, object_kind, creator_actor_id, workshop_actor_id, day, project_id, owner_actor_id, household_id,
         location_id, quality, market_value, significance, json.dumps(metadata or {}, sort_keys=True)),
    )
    oid = int(cur.lastrowid)
    add_provenance(conn, oid, "created", f"{title} was created.", to_actor_id=owner_actor_id,
                   location_id=location_id, day=day, reliability=1.0)
    return oid


def add_provenance(conn: sqlite3.Connection, object_id: int, provenance_kind: str, record_text: str, *,
                   from_actor_id: int | None = None, to_actor_id: int | None = None,
                   location_id: int | None = None, day: int | None = None, reliability: float = 1.0,
                   source_record_id: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO object_provenance(object_id,day,provenance_kind,from_actor_id,to_actor_id,location_id,record_text,reliability,source_record_id,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (object_id, _day(conn) if day is None else day, provenance_kind, from_actor_id, to_actor_id,
         location_id, record_text, reliability, source_record_id, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def create_auction(conn: sqlite3.Connection, title: str, scheduled_day: int, *, location_id: int | None = None,
                   institution_actor_id: int | None = None, prestige: float = 50,
                   metadata: dict[str, Any] | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO auctions(title,location_id,institution_actor_id,scheduled_day,prestige,metadata_json) VALUES (?,?,?,?,?,?)",
        (title, location_id, institution_actor_id, scheduled_day, prestige, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def add_auction_lot(conn: sqlite3.Connection, auction_id: int, object_id: int, *, seller_actor_id: int | None = None,
                    reserve_price: float = 0, estimate_low: float = 0, estimate_high: float = 0) -> int:
    cur = conn.execute(
        """INSERT INTO auction_lots(auction_id,object_id,seller_actor_id,reserve_price,estimate_low,estimate_high)
           VALUES (?,?,?,?,?,?)""",
        (auction_id, object_id, seller_actor_id, reserve_price, estimate_low, max(estimate_low, estimate_high)),
    )
    return int(cur.lastrowid)


def set_auction_interest(conn: sqlite3.Connection, lot_id: int, actor_id: int, *, interest: float = 50,
                         budget: float = 0, taste_fit: float = 50, status_motive: float = 0) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO auction_interest(lot_id,actor_id,interest,budget,taste_fit,status_motive)
           VALUES (?,?,?,?,?,?)""",
        (lot_id, actor_id, interest, budget, taste_fit, status_motive),
    )


def add_shadow_link(conn: sqlite3.Connection, subject_kind: str, subject_id: int, link_kind: str, *,
                    pressure: float = 0, exposure: float = 0, notes: str | None = None) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO shadow_market_links(subject_kind,subject_id,link_kind,pressure,exposure,notes,created_day,updated_day)
           VALUES (?,?,?,?,?,?,?,?)""",
        (subject_kind, subject_id, link_kind, pressure, exposure, notes, day, day),
    )
    return int(cur.lastrowid)


def _record_account(conn: sqlite3.Connection, enterprise_id: int, day: int, kind: str, amount: float, desc: str,
                    good_id: int | None = None) -> None:
    conn.execute(
        """INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,related_good_id)
           VALUES (?,?,?,?,?,?)""",
        (enterprise_id, day, kind, max(0.0, amount), desc, good_id),
    )


def _resolve_market(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> None:
    meta = json.loads(row["metadata_json"] or "{}")
    elapsed = max(1, day - int(row["last_review_day"]))
    rng = random.Random(_seed(conn, int(row["location_id"]) * 100003 + int(row["good_id"]) * 97 + day))
    supply = max(0.0, float(row["supply"]) + float(meta.get("supply_trend_per_30", 0)) * elapsed / 30 + rng.gauss(0, 1.5))
    demand = max(0.0, float(row["demand"]) + float(meta.get("demand_trend_per_30", 0)) * elapsed / 30 + rng.gauss(0, 1.5))
    good = conn.execute("SELECT base_price FROM market_goods WHERE id=?", (row["good_id"],)).fetchone()
    eco_transport = environmental_transport_pressure(conn, int(row["location_id"]), day)
    price = _price(float(good[0]), supply, demand, float(row["transport_pressure"]) + eco_transport, float(row["risk_pressure"]), float(row["tax_pressure"]))
    cadence = int(meta.get("cadence_days", 30))
    conn.execute(
        "UPDATE market_conditions SET supply=?,demand=?,current_price=?,last_review_day=?,next_review_day=? WHERE location_id=? AND good_id=?",
        (supply, demand, price, day, day + max(1, cadence), row["location_id"], row["good_id"]),
    )


def _resolve_production(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> None:
    # CRAFT-01 tracked sites are resolved only by engine.craft; the legacy aggregate
    # material_access formula must never mint parallel output for them.
    if "production_mode" in row.keys() and str(row["production_mode"]) == "tracked":
        return
    elapsed = max(0, day - int(row["last_resolved_day"]))
    if elapsed <= 0:
        return
    ent = conn.execute("SELECT location_id,labor_capacity FROM civilian_enterprises WHERE id=?", (row["enterprise_id"],)).fetchone()
    market = None
    if ent and ent["location_id"] is not None:
        market = conn.execute("SELECT demand,current_price FROM market_conditions WHERE location_id=? AND good_id=?",
                              (ent["location_id"], row["good_id"])).fetchone()
    bottleneck = min(float(row["efficiency"]), float(row["material_access"]), float(row["skilled_labor"]), float(ent["labor_capacity"] if ent else 50)) / 100.0
    good_row = conn.execute("SELECT category FROM market_goods WHERE id=?", (row["good_id"],)).fetchone()
    eco_factor = ecology_production_factor(conn, int(ent["location_id"]) if ent and ent["location_id"] is not None else None, day, str(good_row[0]) if good_row else None)
    produced = float(row["capacity_per_30"]) * elapsed / 30.0 * bottleneck * eco_factor
    inventory = float(row["inventory"]) + max(0.0, produced)
    sold = 0.0
    revenue = 0.0
    if market:
        demand_fraction = max(0.05, min(1.0, float(market["demand"]) / 100.0))
        sold = min(inventory, float(row["capacity_per_30"]) * elapsed / 30.0 * demand_fraction)
        revenue = sold * float(market["current_price"])
        inventory -= sold
    cost = max(0.0, produced * (0.2 + (100 - float(row["efficiency"])) / 250.0))
    conn.execute("UPDATE production_sites SET inventory=?,last_resolved_day=? WHERE id=?", (inventory, day, row["id"]))
    erow = conn.execute("SELECT cash,debt,capital FROM civilian_enterprises WHERE id=?", (row["enterprise_id"],)).fetchone()
    if erow:
        raw_cash = float(erow["cash"]) + revenue - cost
        shortfall = max(0.0, -raw_cash)
        new_cash = max(0.0, raw_cash)
        new_debt = float(erow["debt"]) + shortfall
        new_capital = max(0.0, float(erow["capital"]) + revenue * 0.15 - cost * 0.08)
        conn.execute("UPDATE civilian_enterprises SET cash=?,debt=?,capital=?,updated_day=? WHERE id=?",
                     (new_cash, new_debt, new_capital, day, row["enterprise_id"]))
    if revenue:
        _record_account(conn, int(row["enterprise_id"]), day, "revenue", revenue, "Sales from ordinary production", int(row["good_id"]))
    if cost:
        _record_account(conn, int(row["enterprise_id"]), day, "expense", cost, "Production costs", int(row["good_id"]))


def _resolve_project(conn: sqlite3.Connection, row: sqlite3.Row, day: int, event_logger: Callable[..., int] | None) -> None:
    elapsed = max(0, day - int(row["last_resolved_day"]))
    if elapsed <= 0 or row["status"] != "active":
        return
    bottleneck = min(float(row["funding"]), float(row["material_access"]), float(row["skilled_labor"])) / 100.0
    pace = 100.0 / max(30.0, float((row["target_day"] or (int(row["started_day"]) + 180)) - int(row["started_day"])))
    progress = min(100.0, float(row["progress"]) + elapsed * pace * (0.35 + 0.9 * bottleneck))
    status = "completed" if progress >= 100 else "active"
    conn.execute("UPDATE civilian_projects SET progress=?,status=?,last_resolved_day=? WHERE id=?", (progress, status, day, row["id"]))
    if status == "completed":
        # Projects create durable history. Art/craft projects may also crystallize into cultural objects.
        if row["project_kind"] in {"artwork", "textile", "manuscript", "craft"}:
            kind_map = {"artwork":"painting", "textile":"textile", "manuscript":"manuscript", "craft":"other"}
            q = max(1.0, min(100.0, float(row["quality_potential"]) * (0.7 + 0.3 * bottleneck)))
            obj = create_cultural_object(conn, str(row["title"]), kind_map[row["project_kind"]],
                                         creator_actor_id=row["creator_actor_id"], project_id=int(row["id"]),
                                         owner_actor_id=row["patron_actor_id"], location_id=row["location_id"],
                                         quality=q, market_value=q * 1.2,
                                         significance="valuable" if q >= 75 else "ordinary")
            add_provenance(conn, obj, "commissioned", "Completed as a commissioned project.",
                           to_actor_id=row["patron_actor_id"], location_id=row["location_id"], day=day)
            if row["creator_actor_id"] is not None:
                try:
                    from .patronage import note_cultural_success
                    note_cultural_success(conn, int(row["creator_actor_id"]), q, day=day, object_id=obj)
                except sqlite3.OperationalError:
                    pass
        elif row["project_kind"] in {"architecture", "public_work"}:
            meta = json.loads(row["metadata_json"] or "{}")
            q = max(1.0, min(100.0, float(row["quality_potential"]) * (0.7 + 0.3 * bottleneck)))
            create_building(
                conn, str(row["title"]),
                str(meta.get("building_kind", "public_building" if row["project_kind"] == "public_work" else "other")),
                location_id=row["location_id"], owner_actor_id=meta.get("owner_actor_id", row["patron_actor_id"]),
                household_id=meta.get("household_id"), institution_actor_id=meta.get("institution_actor_id"),
                project_id=int(row["id"]), style_key=meta.get("style_key"), capacity=float(meta.get("capacity", 50)),
                condition=100, prestige=float(meta.get("prestige", q)), utility=float(meta.get("utility", q)),
                maintenance_burden=float(meta.get("maintenance_burden", max(5.0, q / 8.0))), completed_day=day,
                metadata={"quality_at_completion": q},
            )
        conn.execute(
            """INSERT INTO historical_anchors(entity_kind,entity_id,anchor_type,start_day,end_day,summary,source_kind,certainty,canon_scope,created_day)
               VALUES ('thread',?,'project_completed',?,?,?,'admin',1,'campaign',?)""",
            (int(row["id"]), int(row["started_day"]), day, f"Project completed: {row['title']}", day),
        )
        if event_logger:
            event_logger(day=day, event_type="civilian:project_completed", title=f"Completed: {row['title']}",
                         summary=f"The {row['project_kind']} project '{row['title']}' was completed.", severity=1,
                         source_actor_id=row["creator_actor_id"], target_actor_ids=tuple(x for x in [row["patron_actor_id"], row["creator_actor_id"]] if x),
                         location_id=row["location_id"])


def resolve_auction(conn: sqlite3.Connection, auction_id: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, Any]:
    auction = conn.execute("SELECT * FROM auctions WHERE id=?", (auction_id,)).fetchone()
    if not auction:
        raise ValueError("Unknown auction")
    day = _day(conn)
    results = []
    for lot in conn.execute("SELECT * FROM auction_lots WHERE auction_id=? AND status='listed' ORDER BY id", (auction_id,)).fetchall():
        obj = conn.execute("SELECT * FROM cultural_objects WHERE id=?", (lot["object_id"],)).fetchone()
        candidates = []
        for bid in conn.execute("SELECT * FROM auction_interest WHERE lot_id=?", (lot["id"],)).fetchall():
            rng = random.Random(_seed(conn, auction_id * 100000 + int(lot["id"]) * 100 + int(bid["actor_id"])))
            desire = (float(bid["interest"]) * 0.45 + float(bid["taste_fit"]) * 0.35 + float(bid["status_motive"]) * 0.20)
            max_bid = min(float(bid["budget"]), max(float(lot["estimate_low"]), float(obj["market_value"])) * (0.65 + desire / 100.0 * 0.8) * rng.uniform(0.93, 1.07))
            candidates.append((max_bid, int(bid["actor_id"])))
        candidates.sort(reverse=True)
        winner = None
        hammer = None
        if candidates and candidates[0][0] >= float(lot["reserve_price"]):
            winner = candidates[0][1]
            second = candidates[1][0] if len(candidates) > 1 else float(lot["reserve_price"])
            hammer = round(max(float(lot["reserve_price"]), min(candidates[0][0], second * 1.05)), 2)
            conn.execute("UPDATE auction_lots SET winning_actor_id=?,hammer_price=?,status='sold' WHERE id=?", (winner, hammer, lot["id"]))
            seller = lot["seller_actor_id"]
            conn.execute("UPDATE cultural_objects SET current_owner_actor_id=?,current_household_id=NULL,current_location_id=?,market_value=? WHERE id=?",
                         (winner, auction["location_id"], hammer, lot["object_id"]))
            add_provenance(conn, int(lot["object_id"]), "sold", f"Sold at {auction['title']} for {hammer:.2f}.",
                           from_actor_id=seller, to_actor_id=winner, location_id=auction["location_id"], day=day)
        else:
            conn.execute("UPDATE auction_lots SET status='unsold' WHERE id=?", (lot["id"],))
        results.append({"lot_id": int(lot["id"]), "object_id": int(lot["object_id"]), "winner_actor_id": winner, "hammer_price": hammer})
    conn.execute("UPDATE auctions SET status='resolved',resolved_day=? WHERE id=?", (day, auction_id))
    if event_logger:
        event_logger(day=day, event_type="civilian:auction", title=str(auction["title"]),
                     summary=f"{auction['title']} concluded with {sum(1 for r in results if r['winner_actor_id'])} sold lots.",
                     severity=1, source_actor_id=auction["institution_actor_id"], target_actor_ids=(), location_id=auction["location_id"])
    return {"auction_id": auction_id, "resolved_day": day, "lots": results}


def _resolve_households(conn: sqlite3.Connection, day: int) -> None:
    for h in conn.execute("SELECT * FROM households WHERE status IN ('active','declining')").fetchall():
        metadata = json.loads(h["metadata_json"] or "{}")
        # A structurally known household with unquantified canon finances is not a zero-money household.
        # Keep it persistent, but do not invent a budget simply to feed the economic resolver.
        if metadata.get("economic_resolution") == "STRUCTURAL_ONLY" or metadata.get("economic_state") == "NOT_SEPARATELY_QUANTIFIED":
            continue
        elapsed = max(0, day - int(h["updated_day"]))
        if elapsed <= 0:
            continue
        # Servants and stewards on service terms are paid as wages (to their purses) instead of an implicit per-head charge.
        from .payroll import run_household_payroll
        wages = run_household_payroll(conn, h, elapsed, day)
        # Households quantified from their means earn: working members a margin over their keep, wealth a yield (household_staff).
        from .household_staff import _upkeep, household_income
        income = household_income(conn, int(h["id"])) * elapsed / 30.0 if metadata.get("economic_basis") == "family_means" else 0.0
        upkeep = _upkeep(conn, h) * elapsed / 30.0
        liquidity = float(h["liquidity"]) + income - wages - upkeep
        wealth = float(h["wealth"])
        status = str(h["status"])
        if liquidity < 0:
            wealth = max(0.0, wealth + liquidity)
            liquidity = 0.0
            status = "declining" if wealth > 0 else "dissolved"
        elif status == "declining" and liquidity > 5:
            status = "active"
        conn.execute("UPDATE households SET liquidity=?,wealth=?,status=?,updated_day=? WHERE id=?",
                     (liquidity, wealth, status, day, h["id"]))


def _resolve_enterprise_status(conn: sqlite3.Connection, day: int) -> None:
    for e in conn.execute("SELECT * FROM civilian_enterprises WHERE status IN ('active','strained','insolvent')").fetchall():
        elapsed = max(0, day - int(e["updated_day"]))
        if elapsed <= 0:
            continue
        cash, debt, capital = float(e["cash"]), float(e["debt"]), float(e["capital"])
        interest = debt * 0.0025 * elapsed / 30.0
        cash -= interest
        if interest:
            _record_account(conn, int(e["id"]), day, "expense", interest, "Debt carrying cost")
        if cash < 0:
            # Unpaid carrying cost becomes additional liability rather than a negative cash balance.
            debt += -cash
            cash = 0.0
        defaulted_credit = conn.execute(
            "SELECT 1 FROM credit_agreements WHERE borrower_enterprise_id=? AND status='defaulted' LIMIT 1",
            (e["id"],),
        ).fetchone()
        if debt > max(1.0, capital * 1.5):
            status = "insolvent"
        elif defaulted_credit or debt > max(1.0, capital * 1.2):
            status = "strained"
        else:
            status = "active"
        conn.execute("UPDATE civilian_enterprises SET cash=?,debt=?,status=?,updated_day=? WHERE id=?", (cash, debt, status, day, e["id"]))



_BUSINESS_LABEL = {"wholesaler": "warehouse", "inn": "inn", "physician_practice": "physic house", "smithy": "smithy",
                   "moneylender": "counting house", "food_shop": "cookshop"}


def _emergent_business_name(conn: sqlite3.Connection, operator_id: int, archetype: str, location_id: int | None) -> str:
    """A new business takes its operator's name, as small concerns do: "Harrow's inn", else "Bren Harrow's inn"."""
    person = str(conn.execute("SELECT name FROM actors WHERE id=?", (int(operator_id),)).fetchone()[0])
    tokens = [t for t in person.split() if not t.isdigit()]
    label = _BUSINESS_LABEL.get(archetype, archetype.replace("_", " "))
    place = conn.execute("SELECT name FROM locations WHERE id=?", (location_id,)).fetchone() if location_id is not None else None
    for name in (f"{tokens[-1]}'s {label}", f"{' '.join(tokens)}'s {label}",
                 f"{' '.join(tokens)}'s {label}, {place[0] if place else ''}".rstrip(", ")):
        if not conn.execute("SELECT 1 FROM civilian_enterprises WHERE name=?", (name,)).fetchone():
            return name
    return f"{' '.join(tokens)}'s {label} {int(operator_id)}"


def _commercial_emergence_archetype(ctx: sqlite3.Row) -> str:
    choices = [
        (float(ctx["trade_flow"]), "wholesaler"),
        (float(ctx["traveler_flow"]), "inn"),
        (float(ctx["health_demand"]), "physician_practice"),
        (float(ctx["craft_demand"]), "smithy"),
        (float(ctx["credit_demand"]), "moneylender"),
        (float(ctx["foot_traffic"]), "food_shop"),
    ]
    return max(choices, key=lambda x: x[0])[1]


def _review_latent_commercial_emergence(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    """Annual structural business formation from existing local population and demand.

    This does not assign wealth to named characters. A one-person latent merchant/operator is
    resolved from the already-existing urban population, and the business receives a structural
    label rather than a canonized proper name. Sustained regional consequence can later raise
    that latent person to TRACKED resolution or form an unnamed merchant-house candidate.
    """
    meta = conn.execute("SELECT value FROM engine_meta WHERE key='commercial_emergence_next_day'").fetchone()
    next_day = int(meta[0]) if meta else 365
    if day < next_day:
        return {"commercial_emergence_reviews": 0, "latent_merchants_created": 0, "structural_enterprises_created": 0, "merchant_house_candidates": 0}
    while next_day <= day:
        next_day += 365
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('commercial_emergence_next_day',?)", (str(next_day),))

    reviewed = created = candidates = 0
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])

    # First update consequence for already-emergent merchants from actual enterprise history.
    rows = conn.execute("""SELECT e.*, l.id latent_id, l.historical_context_json
                           FROM civilian_enterprises e LEFT JOIN latent_entities l
                             ON json_extract(e.metadata_json,'$.latent_owner_entity_id')=l.id
                           WHERE json_extract(e.metadata_json,'$.emergent_business')=1
                           ORDER BY e.id""").fetchall()
    from .resolution_controller import create_institution_candidate, update_institution_candidate
    for e in rows:
        reviewed += 1
        age_days = max(0, day - int(e["created_day"]))
        material = max(0.0, float(e["capital"]) + float(e["cash"]) - float(e["debt"]))
        consequence = max(0.0, min(35.0, math.log1p(material) * 4.2 + max(0.0, float(e["reputation"]) - 45.0) * 0.22 + age_days / 365.0 * 1.4))
        try:
            hist = json.loads(e["historical_context_json"] or "{}")
        except Exception:
            hist = {}
        hist.update({
            "enterprise_id": int(e["id"]),
            "enterprise_status": str(e["status"]),
            "commercial_age_days": age_days,
            "regional_significance": round(consequence, 3),
            "consequence_score": round(consequence, 3),
        })
        if e["latent_id"] is not None:
            conn.execute("UPDATE latent_entities SET historical_context_json=?,updated_day=? WHERE id=?", (json.dumps(hist, sort_keys=True), day, int(e["latent_id"])))

        if age_days >= 3 * 365 and consequence >= 22.0 and str(e["status"]) in {"active", "strained"}:
            # A wholesaler is an enterprise, not automatically a merchant *house*.  Institutional
            # formation requires evidence that the business has grown beyond one operator into a
            # durable organization.  Family/dynastic merchant-house identity is a later, stronger
            # social form and is not fabricated here.
            existing = conn.execute("SELECT * FROM emergent_institution_candidates WHERE enterprise_id=? AND candidate_kind IN ('merchant firm','merchant house') AND status IN ('forming','eligible') ORDER BY id DESC LIMIT 1", (int(e["id"]),)).fetchone()
            active_staff = int(conn.execute("SELECT COUNT(*) FROM enterprise_staff WHERE enterprise_id=? AND status='active'", (int(e["id"]),)).fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_staff'").fetchone() else 0
            completed_contracts = int(conn.execute("SELECT COUNT(*) FROM merchant_trade_contracts WHERE (buyer_enterprise_id=? OR seller_enterprise_id=?) AND status IN ('fulfilled','settled','delivered')", (int(e["id"]),int(e["id"]))).fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchant_trade_contracts'").fetchone() else 0
            distinct_trade_locations = int(conn.execute("SELECT COUNT(DISTINCT destination_location_id) FROM merchant_trade_contracts WHERE (buyer_enterprise_id=? OR seller_enterprise_id=?) AND destination_location_id IS NOT NULL", (int(e["id"]),int(e["id"]))).fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchant_trade_contracts'").fetchone() else 0
            resources = {
                "capital":float(e["capital"]), "cash":float(e["cash"]), "debt":float(e["debt"]),
                "business_age_days":age_days, "active_staff":active_staff,
                "completed_trade_contracts":completed_contracts, "distinct_trade_locations":distinct_trade_locations,
                "branch_count":0, "institutional_form":"merchant_firm",
            }
            evidence = {"kind": "sustained_commercial_consequence", "enterprise_id": int(e["id"]), "age_days": age_days, "regional_significance": round(consequence,3),
                        "active_staff":active_staff, "completed_trade_contracts":completed_contracts, "distinct_trade_locations":distinct_trade_locations}
            score = min(70.0, 18.0 + consequence + min(15.0, age_days / 365.0 * 2.0))
            if existing is None:
                cid=create_institution_candidate(conn, "merchant firm", location_id=e["location_id"], enterprise_id=int(e["id"]), proposed_name=None, significance_score=score, resources=resources, participants=[], evidence=[evidence], day=day)
                # create_institution_candidate deliberately starts at forming; run the same domain
                # threshold immediately so truly institutional firms need not wait another year.
                update_institution_candidate(conn, cid, significance_score=score, resources=resources, day=day)
                candidates += 1
            else:
                if str(existing["candidate_kind"]) == "merchant house":
                    conn.execute("UPDATE emergent_institution_candidates SET candidate_kind='merchant firm' WHERE id=?", (int(existing["id"]),))
                update_institution_candidate(conn, int(existing["id"]), significance_score=score, resources=resources, evidence_append=evidence, day=day)

    # Then allow sparse new businesses where commercial context is strong enough.
    contexts = conn.execute("SELECT lc.*,l.name location_name FROM location_commercial_context lc JOIN locations l ON l.id=lc.location_id ORDER BY lc.location_id").fetchall()
    year_index = max(1, day // 365)
    from .business import configure_enterprise_business
    for ctx in contexts:
        loc = int(ctx["location_id"])
        opportunity = max(float(ctx[k]) for k in ("trade_flow","traveler_flow","foot_traffic","health_demand","craft_demand","credit_demand"))
        if opportunity < 65.0:
            continue
        existing_count = int(conn.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE location_id=? AND json_extract(metadata_json,'$.emergent_business')=1 AND status IN ('active','strained','insolvent')", (loc,)).fetchone()[0])
        capacity = max(1, min(3, 1 + int((opportunity - 65.0) // 15.0)))
        if existing_count >= capacity:
            continue
        rng = random.Random(seed * 1000003 + loc * 7919 + year_index * 104729)
        chance = min(0.42, 0.12 + max(0.0, opportunity - 65.0) / 100.0)
        if rng.random() >= chance:
            continue
        archetype = _commercial_emergence_archetype(ctx)
        # Formation needs a real operator. Resolve one from the pre-existing POPBACK ecology;
        # if none is suitable locally, no business appears this year. Demand never spawns an adult.
        from .person_ecology import resolve_background_person
        operator_id = resolve_background_person(
            conn, reason=f"local commercial opportunity at {ctx['location_name']}", location_id=loc,
            occupation_domains=("merchant","clerk","artisan","transport","hospitality"), min_age=20, max_age=70,
            economic_weight=1.0, command_weight=.15, subtype="Local business operator",
        )
        if operator_id is None:
            continue
        label = _emergent_business_name(conn, operator_id, archetype, loc)
        capital = round(12.0 + opportunity * 0.16 + rng.uniform(-2.0, 3.0), 3)
        cash = round(7.0 + opportunity * 0.09 + rng.uniform(-1.5, 2.0), 3)
        broad_kind = {"wholesaler":"other","inn":"service","physician_practice":"service","smithy":"workshop","moneylender":"service","food_shop":"shop"}[archetype]
        eid = create_enterprise(conn, label, broad_kind,
                                owner_actor_id=operator_id, location_id=loc, capital=max(8.0,capital), cash=max(4.0,cash), reputation=45+rng.random()*12, admin_quality=42+rng.random()*18, labor_capacity=42+rng.random()*20, risk_tolerance=35+rng.random()*40,
                                metadata={"emergent_business":True,"background_operator_actor_id":operator_id,"authority":"ENGINE_DERIVED_FROM_PREEXISTING_POPBACK_PLUS_CAMPAIGN_CALIBRATION","display_name_status":"GENERATED_NAME_NOT_CANON","opportunity_score":opportunity,"institutional_form":"ordinary_firm","population_delta":0})
        configure_enterprise_business(conn, eid, archetype, quality=46+rng.random()*12, price_position=45+rng.random()*12, capacity=35+rng.random()*18, clientele_fit=45+rng.random()*15, service_reliability=45+rng.random()*15, regulatory_pressure=10+rng.random()*15, cadence_days=30, metadata={"authority":"ENGINE_DERIVED_STRUCTURAL_BUSINESS","background_operator_actor_id":operator_id,"population_delta":0})
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_ecology_state'").fetchone():
            conn.execute("""INSERT INTO enterprise_ecology_state(enterprise_id,founded_day,crystallized_day,structural_origin,last_review_day,metadata_json)
                            VALUES (?,?,?,'formed_during_simulation',?,?) ON CONFLICT(enterprise_id) DO NOTHING""",
                         (eid,day,day,day,json.dumps({"real_popback_operator":True,"population_delta":0},sort_keys=True)))
        created += 1
    return {"commercial_emergence_reviews": reviewed, "latent_merchants_created": created, "structural_enterprises_created": created, "merchant_house_candidates": candidates}

def next_civilian_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals = []
    r = conn.execute("SELECT MIN(next_review_day) FROM market_conditions WHERE next_review_day>? AND next_review_day<=?", (after_day, end_day)).fetchone()[0]
    if r is not None: vals.append(int(r))
    r = conn.execute("SELECT MIN(scheduled_day) FROM auctions WHERE status='scheduled' AND scheduled_day>? AND scheduled_day<=?", (after_day, end_day)).fetchone()[0]
    if r is not None: vals.append(int(r))
    b = next_business_due_day(conn, after_day, end_day)
    if b is not None: vals.append(int(b))
    h = next_household_life_due_day(conn, after_day, end_day)
    if h is not None: vals.append(int(h))
    # Active civilian systems are updated at a coarse 30-day cadence; exact scheduled events still interrupt earlier.
    next_month = ((after_day // 30) + 1) * 30
    if next_month <= end_day and conn.execute(
        """SELECT 1 FROM civilian_projects WHERE status='active'
           UNION SELECT 1 FROM production_sites WHERE active=1
           UNION SELECT 1 FROM buildings WHERE status IN ('active','strained','derelict')
           UNION SELECT 1 FROM style_adoption
           UNION SELECT 1 FROM credit_agreements WHERE status IN ('current','late')
           UNION SELECT 1 FROM professional_memberships WHERE status='active'
           LIMIT 1"""
    ).fetchone():
        vals.append(next_month)
    return min(vals) if vals else None


def process_due_civilian(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    markets = conn.execute("SELECT * FROM market_conditions WHERE next_review_day<=? ORDER BY next_review_day,location_id,good_id", (day,)).fetchall()
    for row in markets:
        _resolve_market(conn, row, day)
    sites = conn.execute("SELECT * FROM production_sites WHERE active=1 AND last_resolved_day<?", (day,)).fetchall()
    for row in sites:
        _resolve_production(conn, row, day)
    projects = conn.execute("SELECT * FROM civilian_projects WHERE status='active' AND last_resolved_day<?", (day,)).fetchall()
    for row in projects:
        _resolve_project(conn, row, day, event_logger)
    auctions = conn.execute("SELECT id FROM auctions WHERE status='scheduled' AND scheduled_day<=? ORDER BY scheduled_day,id", (day,)).fetchall()
    for a in auctions:
        resolve_auction(conn, int(a[0]), event_logger=event_logger)
    _resolve_households(conn, day)
    _resolve_enterprise_status(conn, day)
    careers = review_careers(conn, day, event_logger=event_logger)
    shadow = _resolve_shadow_links(conn, day)
    businesses = process_due_businesses(conn, day)
    emergence = _review_latent_commercial_emergence(conn, day)
    deep = process_due_civilian_life(conn, day, event_logger=event_logger)
    household_life = process_due_household_life(conn, day, event_logger=event_logger)
    return {"markets": len(markets), "production_sites": len(sites), "projects": len(projects), "auctions": len(auctions),
            "careers": careers, "shadow_links": shadow, "business_cycles": len(businesses), **emergence, **deep, **household_life}


def civilian_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    base = {
        "day": _day(conn),
        "households": int(conn.execute("SELECT COUNT(*) FROM households WHERE status!='historical'").fetchone()[0]),
        "enterprises": int(conn.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE status!='historical'").fetchone()[0]),
        "market_conditions": int(conn.execute("SELECT COUNT(*) FROM market_conditions").fetchone()[0]),
        "production_sites": int(conn.execute("SELECT COUNT(*) FROM production_sites WHERE active=1").fetchone()[0]),
        "active_projects": int(conn.execute("SELECT COUNT(*) FROM civilian_projects WHERE status='active'").fetchone()[0]),
        "cultural_objects": int(conn.execute("SELECT COUNT(*) FROM cultural_objects WHERE status!='destroyed'").fetchone()[0]),
        "scheduled_auctions": int(conn.execute("SELECT COUNT(*) FROM auctions WHERE status='scheduled'").fetchone()[0]),
        "shadow_links": int(conn.execute("SELECT COUNT(*) FROM shadow_market_links WHERE status IN ('latent','active')").fetchone()[0]),
    }
    base.update(civilian_life_summary(conn))
    base["business_ecology"] = business_ecology_summary(conn)
    base["household_life"] = household_life_summary(conn)
    return base


def ensure_career_track(conn: sqlite3.Connection, key: str, name: str, domain: str, *, description: str | None = None,
                        typical_entry_age: int | None = None, institution_kind: str | None = None,
                        stages: list[dict[str, Any]] | None = None) -> int:
    conn.execute(
        """INSERT OR IGNORE INTO career_tracks(key,name,domain,description,typical_entry_age,institution_kind)
           VALUES (?,?,?,?,?,?)""",
        (key, name, domain, description, typical_entry_age, institution_kind),
    )
    tid = int(conn.execute("SELECT id FROM career_tracks WHERE key=?", (key,)).fetchone()[0])
    for idx, st in enumerate(stages or []):
        conn.execute(
            """INSERT OR IGNORE INTO career_stages(track_id,stage_key,stage_name,sequence_index,description,entry_requirements_json,responsibilities_json,exit_paths_json)
               VALUES (?,?,?,?,?,?,?,?)""",
            (tid, st["key"], st.get("name", st["key"]), int(st.get("sequence", idx)), st.get("description"),
             json.dumps(st.get("requirements", {}), sort_keys=True), json.dumps(st.get("responsibilities", {}), sort_keys=True),
             json.dumps(st.get("exit_paths", []), sort_keys=True)),
        )
    return tid


def start_career(conn: sqlite3.Connection, actor_id: int, track_id: int, *, stage_key: str | None = None,
                 institution_actor_id: int | None = None, mentor_actor_id: int | None = None) -> int:
    day = _day(conn)
    if stage_key:
        stage = conn.execute("SELECT id FROM career_stages WHERE track_id=? AND stage_key=?", (track_id, stage_key)).fetchone()
    else:
        stage = conn.execute("SELECT id FROM career_stages WHERE track_id=? ORDER BY sequence_index,id LIMIT 1", (track_id,)).fetchone()
    sid = int(stage[0]) if stage else None
    cur = conn.execute(
        """INSERT INTO actor_careers(actor_id,track_id,current_stage_id,institution_actor_id,mentor_actor_id,started_day,stage_started_day,status,experience_json,reputation_json)
           VALUES (?,?,?,?,?,?,?,'active','{}','{}')""",
        (actor_id, track_id, sid, institution_actor_id, mentor_actor_id, day, day),
    )
    return int(cur.lastrowid)


def review_careers(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> int:
    reviewed = 0
    for c in conn.execute("SELECT * FROM actor_careers WHERE status='active'").fetchall():
        exp = json.loads(c["experience_json"] or "{}")
        base_last = c["stage_started_day"] if c["stage_started_day"] is not None else (c["started_day"] if c["started_day"] is not None else day)
        last = int(exp.get("last_review_day", base_last))
        elapsed = max(0, day - last)
        if elapsed <= 0:
            continue
        reviewed += 1
        exp["days_in_career"] = int(exp.get("days_in_career", 0)) + elapsed
        exp["days_in_stage"] = int(exp.get("days_in_stage", 0)) + elapsed
        exp["last_review_day"] = day
        current = conn.execute("SELECT * FROM career_stages WHERE id=?", (c["current_stage_id"],)).fetchone() if c["current_stage_id"] else None
        next_stage = None
        if current:
            next_stage = conn.execute("SELECT * FROM career_stages WHERE track_id=? AND sequence_index>? ORDER BY sequence_index,id LIMIT 1",
                                      (c["track_id"], current["sequence_index"])).fetchone()
        if next_stage:
            req = json.loads(next_stage["entry_requirements_json"] or "{}")
            min_days = int(req.get("min_days_in_stage", 0))
            eligible = int(exp.get("days_in_stage", 0)) >= min_days
            domain = req.get("competence_domain")
            min_score = float(req.get("min_competence", 0))
            if domain:
                row = conn.execute("SELECT ac.score FROM actor_competence ac JOIN competence_domains cd ON cd.id=ac.domain_id WHERE ac.actor_id=? AND cd.domain_key=?", (c["actor_id"], domain)).fetchone()
                eligible = eligible and bool(row and float(row[0]) >= min_score)
            if eligible:
                exp["eligible_stage_id"] = int(next_stage["id"])
                exp["eligible_since_day"] = exp.get("eligible_since_day", day)
                if bool(req.get("auto_advance", False)):
                    conn.execute("UPDATE actor_careers SET current_stage_id=?,stage_started_day=?,experience_json=? WHERE id=?",
                                 (next_stage["id"], day, json.dumps({**exp, "days_in_stage":0, "last_review_day":day}, sort_keys=True), c["id"]))
                    if event_logger:
                        actor = conn.execute("SELECT name,current_location_id FROM actors WHERE id=?", (c["actor_id"],)).fetchone()
                        event_logger(day=day,event_type="civilian:career_advance",title=f"Career advancement: {actor['name']}",
                                     summary=f"{actor['name']} advanced to {next_stage['stage_name']}.",severity=1,
                                     source_actor_id=c["actor_id"],target_actor_ids=(c["actor_id"],),location_id=actor["current_location_id"])
                    continue
        conn.execute("UPDATE actor_careers SET experience_json=? WHERE id=?", (json.dumps(exp, sort_keys=True), c["id"]))
    return reviewed


def _resolve_shadow_links(conn: sqlite3.Connection, day: int) -> int:
    # Exposure is a world-time process, not a checkpoint-count process. Before v0.37 every
    # invocation advanced exposure once, so adding unrelated simulation checkpoints could make
    # crime easier to discover. Use updated_day as the exposure clock instead.
    changed = 0
    for row in conn.execute("SELECT * FROM shadow_market_links WHERE status IN ('latent','active')").fetchall():
        elapsed = max(0, int(day) - int(row["updated_day"]))
        if elapsed <= 0:
            continue
        periods = elapsed / 30.0
        rng = random.Random(_seed(conn, 9000000 + int(row["id"]) * 211 + day))
        pressure = float(row["pressure"])
        drift = pressure * 0.015 * periods
        noise = rng.uniform(-1.0, 1.0) * max(0.15, periods ** 0.5)
        exposure = min(100.0, max(0.0, float(row["exposure"]) + drift + noise))
        status = "active" if pressure >= 25 else str(row["status"])
        if exposure >= 85:
            status = "exposed"
        conn.execute("UPDATE shadow_market_links SET exposure=?,status=?,updated_day=? WHERE id=?", (exposure,status,day,row["id"]))
        changed += 1
    return changed
