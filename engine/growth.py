from __future__ import annotations

import json
import math
import sqlite3
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()
    return int(row[0]) if row else 0


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(v)))


def _administration_competence(conn: sqlite3.Connection, actor_id: int | None) -> float:
    if actor_id is None:
        return 0.0
    row = conn.execute(
        """SELECT MAX(ac.score) FROM actor_competence ac
           JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key IN ('administration','regional','politics')""",
        (int(actor_id),),
    ).fetchone()
    return _clamp(float(row[0] or 0.0))


def configure_public_treasury(
    conn: sqlite3.Connection,
    polity_id: int,
    *,
    cash: float,
    debt: float = 0.0,
    tax_rate: float = 0.05,
    toll_rate: float = 0.0,
    debt_interest_rate_per_30: float = 0.015,
    review_cadence_days: int = 30,
    metadata: dict[str, Any] | None = None,
) -> int:
    if not conn.execute("SELECT 1 FROM political_polities WHERE id=? AND status<>'dissolved'", (polity_id,)).fetchone():
        raise ValueError("public treasury requires an active polity")
    if cash < 0 or debt < 0:
        raise ValueError("public cash/debt cannot be negative")
    if not (0 <= tax_rate <= 0.5) or not (0 <= toll_rate <= 0.5):
        raise ValueError("tax/toll rates must be between 0 and 0.5")
    day = _day(conn)
    conn.execute(
        """INSERT INTO regional_public_treasuries(
               polity_id,cash,debt,tax_rate,toll_rate,debt_interest_rate_per_30,status,
               last_collection_day,next_review_day,review_cadence_days,metadata_json
           ) VALUES (?,?,?,?,?,?,'active',?,?,?,?)
           ON CONFLICT(polity_id) DO UPDATE SET cash=excluded.cash,debt=excluded.debt,
             tax_rate=excluded.tax_rate,toll_rate=excluded.toll_rate,
             debt_interest_rate_per_30=excluded.debt_interest_rate_per_30,
             status=CASE WHEN regional_public_treasuries.status='suspended' THEN 'suspended' ELSE 'active' END,
             review_cadence_days=excluded.review_cadence_days,metadata_json=excluded.metadata_json""",
        (polity_id, float(cash), float(debt), float(tax_rate), float(toll_rate),
         float(debt_interest_rate_per_30), day, day + max(1, int(review_cadence_days)),
         max(1, int(review_cadence_days)), json.dumps(metadata or {}, sort_keys=True)),
    )
    return polity_id


def _fiscal_entry(
    conn: sqlite3.Connection,
    polity_id: int,
    day: int,
    direction: str,
    entry_kind: str,
    amount: float,
    *,
    counterparty_kind: str | None = None,
    counterparty_id: int | None = None,
    source_kind: str | None = None,
    source_id: int | None = None,
    description: str = "",
) -> int | None:
    amount = float(amount)
    if amount <= 1e-9:
        return None
    if direction not in {"inflow", "outflow"}:
        raise ValueError("invalid fiscal direction")
    cur = conn.execute(
        """INSERT INTO regional_fiscal_entries(
               polity_id,day,direction,entry_kind,amount,counterparty_kind,counterparty_id,
               source_kind,source_id,description
           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (polity_id, day, direction, entry_kind, amount, counterparty_kind, counterparty_id,
         source_kind, source_id, description),
    )
    return int(cur.lastrowid)


def borrow_public_funds(conn: sqlite3.Connection, polity_id: int, amount: float, *,
                        lender_kind: str = "public_credit", lender_id: int | None = None,
                        description: str = "Public borrowing") -> None:
    amount = float(amount)
    if amount <= 0:
        raise ValueError("borrowing must be positive")
    day = _day(conn)
    row = conn.execute("SELECT * FROM regional_public_treasuries WHERE polity_id=?", (polity_id,)).fetchone()
    if not row:
        raise ValueError("public treasury not configured")
    conn.execute("UPDATE regional_public_treasuries SET cash=cash+?,debt=debt+? WHERE polity_id=?", (amount, amount, polity_id))
    _fiscal_entry(conn, polity_id, day, "inflow", "borrowing", amount,
                  counterparty_kind=lender_kind, counterparty_id=lender_id, description=description)


def _controlled_locations(conn: sqlite3.Connection, polity_id: int) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        "SELECT location_id FROM territorial_control WHERE controller_polity_id=? ORDER BY location_id", (polity_id,)
    ).fetchall()]


def _recent_enterprise_revenue(conn: sqlite3.Connection, location_id: int, start_day: int, end_day: int) -> list[tuple[int, float]]:
    rows = conn.execute(
        """SELECT e.id,COALESCE(SUM(a.amount),0) gross
           FROM civilian_enterprises e
           LEFT JOIN enterprise_accounts a ON a.enterprise_id=e.id AND a.account_kind='revenue'
             AND a.day>? AND a.day<=?
           WHERE e.location_id=? AND e.status IN ('active','strained','insolvent')
           GROUP BY e.id ORDER BY e.id""",
        (start_day, end_day, location_id),
    ).fetchall()
    return [(int(r["id"]), max(0.0, float(r["gross"] or 0.0))) for r in rows]


def _collect_revenue(conn: sqlite3.Connection, treasury: sqlite3.Row, day: int) -> dict[str, float]:
    polity_id = int(treasury["polity_id"])
    start = int(treasury["last_collection_day"])
    if day <= start:
        return {"tax": 0.0, "toll": 0.0, "debt_interest": 0.0}
    tax_rate = float(treasury["tax_rate"])
    toll_rate = float(treasury["toll_rate"])
    tax_total = 0.0
    toll_total = 0.0
    tolled_contract_ids: set[int] = set()
    for loc in _controlled_locations(conn, polity_id):
        for eid, gross in _recent_enterprise_revenue(conn, loc, start, day):
            due = gross * tax_rate
            if due <= 1e-9:
                continue
            erow = conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?", (eid,)).fetchone()
            paid = min(due, max(0.0, float(erow["cash"] if erow else 0.0)))
            if paid <= 1e-9:
                continue
            conn.execute("UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?", (paid, day, eid))
            conn.execute("UPDATE regional_public_treasuries SET cash=cash+? WHERE polity_id=?", (paid, polity_id))
            _fiscal_entry(conn, polity_id, day, "inflow", "business_tax", paid,
                          counterparty_kind="enterprise", counterparty_id=eid,
                          source_kind="enterprise_revenue", source_id=eid,
                          description=f"Collected {tax_rate:.3f} tax against realized enterprise revenue in location #{loc}.")
            tax_total += paid

        if toll_rate > 0:
            contracts = conn.execute(
                """SELECT c.* FROM merchant_trade_contracts c
                   WHERE c.status='fulfilled' AND c.fulfilled_day>? AND c.fulfilled_day<=?
                     AND (c.origin_location_id=? OR c.destination_location_id=?)
                   ORDER BY c.id""", (start, day, loc, loc)
            ).fetchall()
            for c in contracts:
                cid = int(c["id"])
                if cid in tolled_contract_ids:
                    continue
                tolled_contract_ids.add(cid)
                amount = float(c["quantity"]) * float(c["unit_price"]) * toll_rate
                payer = int(c["buyer_enterprise_id"])
                erow = conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?", (payer,)).fetchone()
                paid = min(amount, max(0.0, float(erow["cash"] if erow else 0.0)))
                if paid <= 1e-9:
                    continue
                conn.execute("UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?", (paid, day, payer))
                conn.execute("UPDATE regional_public_treasuries SET cash=cash+? WHERE polity_id=?", (paid, polity_id))
                _fiscal_entry(conn, polity_id, day, "inflow", "trade_toll", paid,
                              counterparty_kind="enterprise", counterparty_id=payer,
                              source_kind="merchant_contract", source_id=int(c["id"]),
                              description=f"Collected {toll_rate:.3f} toll on fulfilled trade contract #{int(c['id'])}.")
                toll_total += paid

    current = conn.execute("SELECT cash,debt,debt_interest_rate_per_30 FROM regional_public_treasuries WHERE polity_id=?", (polity_id,)).fetchone()
    elapsed = day - start
    interest_due = float(current["debt"]) * float(current["debt_interest_rate_per_30"]) * elapsed / 30.0
    interest_paid = min(max(0.0, interest_due), max(0.0, float(current["cash"])))
    if interest_paid > 1e-9:
        conn.execute("UPDATE regional_public_treasuries SET cash=cash-? WHERE polity_id=?", (interest_paid, polity_id))
        _fiscal_entry(conn, polity_id, day, "outflow", "debt_service", interest_paid,
                      description="Public debt carrying cost.")
    unpaid = max(0.0, interest_due - interest_paid)
    if unpaid > 1e-9:
        conn.execute("UPDATE regional_public_treasuries SET debt=debt+?,status='strained' WHERE polity_id=?", (unpaid, polity_id))
    conn.execute("UPDATE regional_public_treasuries SET last_collection_day=? WHERE polity_id=?", (day, polity_id))
    return {"tax": tax_total, "toll": toll_total, "debt_interest": interest_paid, "unpaid_interest": unpaid}


def create_public_project(
    conn: sqlite3.Connection,
    polity_id: int,
    location_id: int,
    project_kind: str,
    title: str,
    *,
    route_id: int | None = None,
    required_cash: float = 0.0,
    required_labor_days: float = 0.0,
    material_good_id: int | None = None,
    required_material_quantity: float = 0.0,
    target_day: int | None = None,
    effects: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    if project_kind not in {"road_repair", "security_post", "market_warehouse", "administrative_office"}:
        raise ValueError("unsupported public project kind")
    if not conn.execute("SELECT 1 FROM regional_public_treasuries WHERE polity_id=?", (polity_id,)).fetchone():
        raise ValueError("public project requires a configured treasury")
    control = conn.execute("SELECT 1 FROM territorial_control WHERE location_id=? AND controller_polity_id=?", (location_id, polity_id)).fetchone()
    if not control:
        raise ValueError("public project location is not controlled by the polity")
    if route_id is not None and not conn.execute("SELECT 1 FROM travel_routes WHERE id=?", (route_id,)).fetchone():
        raise ValueError("unknown project route")
    if required_material_quantity > 0 and material_good_id is None:
        raise ValueError("material requirement needs a good")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO regional_public_projects(
               polity_id,location_id,route_id,project_kind,title,required_cash,required_labor_days,
               material_good_id,required_material_quantity,started_day,target_day,status,next_review_day,
               effects_json,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
        (polity_id, location_id, route_id, project_kind, title, max(0.0, float(required_cash)),
         max(0.0, float(required_labor_days)), material_good_id, max(0.0, float(required_material_quantity)),
         day, target_day, day + 30, json.dumps(effects or {}, sort_keys=True), json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def assign_project_household_labor(conn: sqlite3.Connection, project_id: int, household_id: int, *,
                                   labor_days: float, wage_per_day: float) -> None:
    p = conn.execute("SELECT location_id,status FROM regional_public_projects WHERE id=?", (project_id,)).fetchone()
    h = conn.execute("SELECT location_id,status FROM households WHERE id=?", (household_id,)).fetchone()
    if not p or str(p["status"]) not in {"active", "blocked"}:
        raise ValueError("project unavailable")
    if not h or str(h["status"]) not in {"active", "declining"} or h["location_id"] is None or int(h["location_id"]) != int(p["location_id"]):
        raise ValueError("project labor must come from an active local household")
    if labor_days <= 0 or wage_per_day < 0:
        raise ValueError("invalid labor commitment")
    conn.execute(
        """INSERT INTO regional_project_labor(project_id,household_id,labor_days_committed,labor_days_used,wage_per_day,status)
           VALUES (?,?,?,0,?,'active')
           ON CONFLICT(project_id,household_id) DO UPDATE SET
             labor_days_committed=MAX(regional_project_labor.labor_days_committed,excluded.labor_days_committed),
             wage_per_day=excluded.wage_per_day,status='active'""",
        (project_id, household_id, float(labor_days), float(wage_per_day)),
    )


def add_security_assignment(conn: sqlite3.Connection, polity_id: int, *, route_id: int | None = None,
                            location_id: int | None = None, monthly_cost: float = 5.0,
                            strength: float = 40.0, metadata: dict[str, Any] | None = None) -> int:
    if route_id is None and location_id is None:
        raise ValueError("security assignment needs a route or location")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO regional_security_assignments(
               polity_id,route_id,location_id,monthly_cost,strength,status,last_paid_day,next_review_day,metadata_json
           ) VALUES (?,?,?,?,?,'active',?, ?,?)""",
        (polity_id, route_id, location_id, max(0.0, float(monthly_cost)), _clamp(strength), day, day + 30,
         json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _local_material_options(conn: sqlite3.Connection, project: sqlite3.Row) -> list[sqlite3.Row]:
    gid = project["material_good_id"]
    if gid is None:
        return []
    return conn.execute(
        """SELECT s.*,e.cash enterprise_cash,e.status enterprise_status,
                  COALESCE(mc.current_price,g.base_price) unit_price
           FROM commercial_stock s
           JOIN civilian_enterprises e ON e.id=s.enterprise_id
           JOIN market_goods g ON g.id=s.good_id
           LEFT JOIN market_conditions mc ON mc.location_id=s.location_id AND mc.good_id=s.good_id
           WHERE s.location_id=? AND s.good_id=? AND s.quantity>0 AND e.status IN ('active','strained')
           ORDER BY unit_price,s.id""",
        (int(project["location_id"]), int(gid)),
    ).fetchall()


def _buy_project_materials(conn: sqlite3.Connection, p: sqlite3.Row, day: int) -> tuple[float, float]:
    need = max(0.0, float(p["required_material_quantity"]) - float(p["material_quantity_used"]))
    if need <= 1e-9 or p["material_good_id"] is None:
        return 0.0, 0.0
    polity_id = int(p["polity_id"])
    bought = spent = 0.0
    for st in _local_material_options(conn, p):
        if need <= 1e-9:
            break
        treasury = conn.execute("SELECT cash FROM regional_public_treasuries WHERE polity_id=?", (polity_id,)).fetchone()
        cash = max(0.0, float(treasury["cash"] if treasury else 0.0))
        price = max(0.01, float(st["unit_price"]))
        qty = min(need, float(st["quantity"]), cash / price)
        if qty <= 1e-9:
            continue
        cost = qty * price
        conn.execute("UPDATE commercial_stock SET quantity=quantity-? WHERE id=?", (qty, int(st["id"])))
        conn.execute("UPDATE civilian_enterprises SET cash=cash+?,updated_day=? WHERE id=?", (cost, day, int(st["enterprise_id"])))
        conn.execute("UPDATE regional_public_treasuries SET cash=cash-? WHERE polity_id=?", (cost, polity_id))
        conn.execute(
            """INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,related_good_id,source_kind,source_id)
               VALUES (?,?, 'revenue', ?, ?, ?, 'public_project', ?)""",
            (int(st["enterprise_id"]), day, cost, f"Materials supplied to public project #{int(p['id'])}",
             int(p["material_good_id"]), int(p["id"])),
        )
        conn.execute(
            """INSERT INTO regional_project_materials(
                   project_id,supplier_enterprise_id,stock_id,good_id,quantity,unit_price,delivered_day,paid_amount
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (int(p["id"]), int(st["enterprise_id"]), int(st["id"]), int(p["material_good_id"]), qty, price, day, cost),
        )
        _fiscal_entry(conn, polity_id, day, "outflow", "project_material", cost,
                      counterparty_kind="enterprise", counterparty_id=int(st["enterprise_id"]),
                      source_kind="public_project", source_id=int(p["id"]),
                      description=f"Purchased {qty:.2f} material units for {p['title']}.")
        bought += qty
        spent += cost
        need -= qty
    if bought > 0:
        conn.execute("UPDATE regional_public_projects SET material_quantity_used=material_quantity_used+?,cash_spent=cash_spent+? WHERE id=?",
                     (bought, spent, int(p["id"])))
    return bought, spent


def _pay_project_labor(conn: sqlite3.Connection, p: sqlite3.Row, day: int) -> tuple[float, float]:
    remaining = max(0.0, float(p["required_labor_days"]) - float(p["labor_days_used"]))
    if remaining <= 1e-9:
        return 0.0, 0.0
    polity_id = int(p["polity_id"])
    used = spent = 0.0
    rows = conn.execute(
        """SELECT l.*,h.liquidity,h.status household_status FROM regional_project_labor l
           JOIN households h ON h.id=l.household_id
           WHERE l.project_id=? AND l.status='active' ORDER BY l.household_id""", (int(p["id"]),)
    ).fetchall()
    for l in rows:
        if remaining <= 1e-9:
            break
        avail = max(0.0, float(l["labor_days_committed"]) - float(l["labor_days_used"]))
        if avail <= 1e-9 or str(l["household_status"]) not in {"active", "declining"}:
            continue
        wage = max(0.0, float(l["wage_per_day"]))
        treasury = conn.execute("SELECT cash FROM regional_public_treasuries WHERE polity_id=?", (polity_id,)).fetchone()
        cash = max(0.0, float(treasury["cash"] if treasury else 0.0))
        affordable = remaining if wage <= 1e-9 else cash / wage
        days_used = min(avail, remaining, max(0.0, affordable), 30.0)
        if days_used <= 1e-9:
            continue
        pay = days_used * wage
        if pay > 0:
            conn.execute("UPDATE regional_public_treasuries SET cash=cash-? WHERE polity_id=?", (pay, polity_id))
            conn.execute("UPDATE households SET liquidity=liquidity+?,updated_day=? WHERE id=?", (pay, day, int(l["household_id"])))
            _fiscal_entry(conn, polity_id, day, "outflow", "project_wage", pay,
                          counterparty_kind="household", counterparty_id=int(l["household_id"]),
                          source_kind="public_project", source_id=int(p["id"]),
                          description=f"Public-works wages for {days_used:.2f} labor-days on {p['title']}.")
        conn.execute("UPDATE regional_project_labor SET labor_days_used=labor_days_used+? WHERE project_id=? AND household_id=?",
                     (days_used, int(p["id"]), int(l["household_id"])))
        used += days_used
        spent += pay
        remaining -= days_used
    if used > 0:
        conn.execute("UPDATE regional_public_projects SET labor_days_used=labor_days_used+?,cash_spent=cash_spent+? WHERE id=?",
                     (used, spent, int(p["id"])))
    return used, spent


def _pay_project_overhead(conn: sqlite3.Connection, p: sqlite3.Row, day: int) -> float:
    # required_cash is the non-material/non-wage administrative/contracting requirement.
    direct_spent = max(0.0, float(p["cash_spent"]) - float(conn.execute(
        "SELECT COALESCE(SUM(paid_amount),0) FROM regional_project_materials WHERE project_id=?", (int(p["id"]),)
    ).fetchone()[0]) - float(conn.execute(
        "SELECT COALESCE(SUM(labor_days_used*wage_per_day),0) FROM regional_project_labor WHERE project_id=?", (int(p["id"]),)
    ).fetchone()[0]))
    remaining = max(0.0, float(p["required_cash"]) - direct_spent)
    if remaining <= 1e-9:
        return 0.0
    polity_id = int(p["polity_id"])
    cash = float(conn.execute("SELECT cash FROM regional_public_treasuries WHERE polity_id=?", (polity_id,)).fetchone()[0])
    pay = min(remaining, max(0.0, cash), max(1.0, float(p["required_cash"]) / 4.0))
    if pay <= 1e-9:
        return 0.0
    conn.execute("UPDATE regional_public_treasuries SET cash=cash-? WHERE polity_id=?", (pay, polity_id))
    conn.execute("UPDATE regional_public_projects SET cash_spent=cash_spent+? WHERE id=?", (pay, int(p["id"])))
    _fiscal_entry(conn, polity_id, day, "outflow", "project_overhead", pay,
                  source_kind="public_project", source_id=int(p["id"]),
                  description=f"Administrative/contracting expenditure on {p['title']}.")
    return pay


def _project_resource_fractions(conn: sqlite3.Connection, project_id: int) -> dict[str, float]:
    p = conn.execute("SELECT * FROM regional_public_projects WHERE id=?", (project_id,)).fetchone()
    if not p:
        return {"material": 0.0, "labor": 0.0, "cash": 0.0}
    material = 1.0 if float(p["required_material_quantity"]) <= 0 else min(1.0, float(p["material_quantity_used"]) / float(p["required_material_quantity"]))
    labor = 1.0 if float(p["required_labor_days"]) <= 0 else min(1.0, float(p["labor_days_used"]) / float(p["required_labor_days"]))
    material_spend = float(conn.execute("SELECT COALESCE(SUM(paid_amount),0) FROM regional_project_materials WHERE project_id=?", (project_id,)).fetchone()[0])
    labor_spend = float(conn.execute("SELECT COALESCE(SUM(labor_days_used*wage_per_day),0) FROM regional_project_labor WHERE project_id=?", (project_id,)).fetchone()[0])
    overhead = max(0.0, float(p["cash_spent"]) - material_spend - labor_spend)
    cash = 1.0 if float(p["required_cash"]) <= 0 else min(1.0, overhead / float(p["required_cash"]))
    return {"material": material, "labor": labor, "cash": cash}


def _complete_public_project(conn: sqlite3.Connection, p: sqlite3.Row, day: int, event_logger: Callable[..., int] | None) -> None:
    kind = str(p["project_kind"])
    effects = json.loads(p["effects_json"] or "{}")
    if kind == "road_repair" and p["route_id"] is not None:
        rid = int(p["route_id"])
        route = conn.execute("SELECT * FROM travel_routes WHERE id=?", (rid,)).fetchone()
        if route:
            reliability_gain = float(effects.get("reliability_gain", 25.0))
            days_factor = float(effects.get("base_days_factor", 0.82))
            conn.execute("UPDATE travel_routes SET reliability=?,base_days=? WHERE id=?",
                         (_clamp(float(route["reliability"]) + reliability_gain), max(1.0, float(route["base_days"]) * days_factor), rid))
            # Repair can resolve specifically physical-maintenance conditions, not banditry or war damage by fiat.
            conn.execute(
                """UPDATE route_conditions SET status='ended',end_day=COALESCE(end_day,?)
                   WHERE route_id=? AND status='active' AND condition_kind IN ('disrepair','washout','bridge_damage','road_damage')""",
                (day, rid),
            )
    elif kind == "security_post" and p["route_id"] is not None:
        if not conn.execute("SELECT 1 FROM regional_security_assignments WHERE polity_id=? AND route_id=? AND status='active'",
                            (int(p["polity_id"]), int(p["route_id"]))).fetchone():
            add_security_assignment(conn, int(p["polity_id"]), route_id=int(p["route_id"]),
                                    location_id=int(p["location_id"]),
                                    monthly_cost=float(effects.get("monthly_cost", 5.0)),
                                    strength=float(effects.get("strength", 45.0)),
                                    metadata={"source_project_id": int(p["id"])})
    elif kind == "market_warehouse":
        conn.execute(
            """INSERT INTO buildings(name,building_kind,location_id,institution_actor_id,capacity,condition,utility,
                   maintenance_burden,completed_day,status,metadata_json,updated_day)
               SELECT ?, 'warehouse', ?, pp.institution_actor_id, ?,100,75,5,?,'active',?,?
               FROM political_polities pp WHERE pp.id=?""",
            (str(p["title"]), int(p["location_id"]), float(effects.get("capacity", 60.0)), day,
             json.dumps({"public_project_id": int(p["id"])}, sort_keys=True), day, int(p["polity_id"])),
        )
    elif kind == "administrative_office":
        conn.execute(
            """INSERT INTO buildings(name,building_kind,location_id,institution_actor_id,capacity,condition,utility,
                   maintenance_burden,completed_day,status,metadata_json,updated_day)
               SELECT ?, 'public_building', ?, pp.institution_actor_id, ?,100,70,4,?,'active',?,?
               FROM political_polities pp WHERE pp.id=?""",
            (str(p["title"]), int(p["location_id"]), float(effects.get("capacity", 45.0)), day,
             json.dumps({"public_project_id": int(p["id"])}, sort_keys=True), day, int(p["polity_id"])),
        )
        gain = float(effects.get("administrative_capacity_gain", 4.0))
        conn.execute("UPDATE political_polities SET administrative_capacity=MIN(100,administrative_capacity+?) WHERE id=?",
                     (gain, int(p["polity_id"])))
    conn.execute("UPDATE regional_public_projects SET status='completed',completed_day=?,next_review_day=? WHERE id=?",
                 (day, day, int(p["id"])))
    if event_logger:
        event_logger(day=day, event_type="growth:project_completed", title=str(p["title"]),
                     summary=f"Public project #{int(p['id'])} completed after consuming its tracked cash, material and labor requirements.",
                     severity=2, location_id=int(p["location_id"]), visibility="public", rumorability=.5, reliability=1.0)


def _review_project(conn: sqlite3.Connection, p: sqlite3.Row, day: int, event_logger: Callable[..., int] | None) -> str:
    _buy_project_materials(conn, p, day)
    fresh = conn.execute("SELECT * FROM regional_public_projects WHERE id=?", (int(p["id"]),)).fetchone()
    _pay_project_labor(conn, fresh, day)
    fresh = conn.execute("SELECT * FROM regional_public_projects WHERE id=?", (int(p["id"]),)).fetchone()
    _pay_project_overhead(conn, fresh, day)
    fresh = conn.execute("SELECT * FROM regional_public_projects WHERE id=?", (int(p["id"]),)).fetchone()
    frac = _project_resource_fractions(conn, int(p["id"]))
    complete = all(v >= 0.999999 for v in frac.values())
    if complete:
        _complete_public_project(conn, fresh, day, event_logger)
        return "completed"
    reasons: list[str] = []
    if frac["material"] < 1:
        reasons.append("materials")
    if frac["labor"] < 1:
        reasons.append("labor")
    if frac["cash"] < 1:
        reasons.append("cash")
    treasury = conn.execute("SELECT cash FROM regional_public_treasuries WHERE polity_id=?", (int(p["polity_id"]),)).fetchone()
    if treasury and float(treasury["cash"]) <= 1e-9 and reasons:
        reasons.append("treasury_empty")
    conn.execute("UPDATE regional_public_projects SET status='blocked',blocked_reason=?,next_review_day=? WHERE id=?",
                 (",".join(reasons), day + 30, int(p["id"])))
    return "blocked"


def _review_security(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> bool:
    polity_id = int(row["polity_id"])
    treasury = conn.execute("SELECT cash FROM regional_public_treasuries WHERE polity_id=?", (polity_id,)).fetchone()
    if not treasury:
        return False
    cost = float(row["monthly_cost"])
    if float(treasury["cash"]) + 1e-9 < cost:
        conn.execute("UPDATE regional_security_assignments SET status='unfunded',next_review_day=? WHERE id=?", (day + 30, int(row["id"])))
        return False
    if cost > 0:
        conn.execute("UPDATE regional_public_treasuries SET cash=cash-? WHERE polity_id=?", (cost, polity_id))
        _fiscal_entry(conn, polity_id, day, "outflow", "security_payroll", cost,
                      source_kind="security_assignment", source_id=int(row["id"]),
                      description="Regional security deployment payroll/supply cost.")
    if row["route_id"] is not None:
        strength = float(row["strength"])
        conds = conn.execute(
            """SELECT * FROM route_conditions WHERE route_id=? AND status='active'
               AND condition_kind IN ('banditry','crime','insecurity','raiding') ORDER BY id""",
            (int(row["route_id"]),),
        ).fetchall()
        for c in conds:
            hazard = max(0.0, float(c["hazard_pressure"]) - strength * .08)
            access = min(100.0, float(c["accessibility"]) + strength * .10)
            delay = max(1.0, float(c["delay_factor"]) - strength * .0025)
            status = "ended" if hazard <= 1.0 and access >= 95.0 and delay <= 1.02 else "active"
            conn.execute("UPDATE route_conditions SET hazard_pressure=?,accessibility=?,delay_factor=?,status=?,end_day=? WHERE id=?",
                         (hazard, access, delay, status, day if status == "ended" else c["end_day"], int(c["id"])))
    conn.execute("UPDATE regional_security_assignments SET status='active',last_paid_day=?,next_review_day=? WHERE id=?",
                 (day, day + 30, int(row["id"])))
    return True


def _food_stress(conn: sqlite3.Connection, location_id: int) -> float:
    row = conn.execute(
        """SELECT mc.current_price,g.base_price FROM market_conditions mc JOIN market_goods g ON g.id=mc.good_id
           WHERE mc.location_id=? AND g.good_key='ordinary-grain'""", (location_id,)
    ).fetchone()
    if not row or float(row["base_price"]) <= 0:
        return 0.0
    ratio = float(row["current_price"]) / float(row["base_price"])
    return _clamp((ratio - 1.0) * 65.0)


def regional_state(conn: sqlite3.Connection, polity_id: int, location_id: int, *, day: int | None = None) -> dict[str, Any]:
    from .ecology import evaluate_route_leg
    day = _day(conn) if day is None else int(day)
    route_rows = conn.execute(
        """SELECT * FROM travel_routes WHERE status IN ('open','restricted') AND
           (from_location_id=? OR (bidirectional=1 AND to_location_id=?)) ORDER BY id""", (location_id, location_id)
    ).fetchall()
    route_evals: list[dict[str, Any]] = []
    for r in route_rows:
        try:
            ev = evaluate_route_leg(conn, int(r["id"]), location_id, day=day)
            if ev.get("usable"):
                route_evals.append({"route_id": int(r["id"]), **ev})
        except Exception:
            continue
    if route_evals:
        accessibility = sum(float(x["accessibility"]) for x in route_evals) / len(route_evals)
        hazard = sum(float(x["hazard"]) for x in route_evals) / len(route_evals)
        travel_days = sum(float(x["days"]) for x in route_evals) / len(route_evals)
    else:
        accessibility, hazard, travel_days = 0.0, 100.0, math.inf
    enterprises = conn.execute(
        "SELECT COUNT(*) n,COALESCE(SUM(cash),0) cash FROM civilian_enterprises WHERE location_id=? AND status IN ('active','strained','insolvent')",
        (location_id,),
    ).fetchone()
    households = int(conn.execute("SELECT COUNT(*) FROM households WHERE location_id=? AND status IN ('active','declining')", (location_id,)).fetchone()[0])
    named_people = int(conn.execute(
        """SELECT COUNT(DISTINCT hm.actor_id) FROM household_members hm JOIN households h ON h.id=hm.household_id
           WHERE h.location_id=? AND h.status IN ('active','declining') AND hm.status='active'""", (location_id,)
    ).fetchone()[0])
    population_est = float(conn.execute(
        """SELECT COALESCE(SUM(population_estimate),0) FROM latent_population_scopes
           WHERE scope_kind='location' AND scope_id=? AND status='active'""", (location_id,)
    ).fetchone()[0] or 0.0)
    # SCALE-01 owns the opening settlement calibration; POPLIFE-01 owns the live current
    # population once that source exists. Latent scopes remain the fallback for unresolved places.
    live_pop = conn.execute("SELECT population_estimate FROM background_population_sources WHERE source_kind='settlement' AND location_id=?", (location_id,)).fetchone()
    if live_pop is not None:
        population_est = float(live_pop[0])
    else:
        scale_pop = conn.execute("SELECT population_estimate FROM settlement_scale_profiles WHERE location_id=?", (location_id,)).fetchone()
        if scale_pop is not None:
            population_est = float(scale_pop[0])
        elif population_est <= 0:
            population_est = float(named_people)
    trade = int(conn.execute(
        """SELECT COUNT(*) FROM merchant_trade_contracts WHERE status='fulfilled' AND fulfilled_day>? AND fulfilled_day<=?
           AND (origin_location_id=? OR destination_location_id=?)""", (day - 365, day, location_id, location_id)
    ).fetchone()[0])
    from .aggregate_trade import bucket_for_location
    trade_bucket = bucket_for_location(conn, location_id)
    aggregate_trade_volume = 0.0
    aggregate_trade_coverage = 0.0
    aggregate_trade_per_1000 = 0.0
    if trade_bucket:
        aggregate_trade_volume = float(conn.execute(
            """SELECT COALESCE(SUM(dispatched_quantity),0) FROM aggregate_trade_flows
               WHERE period_day>? AND period_day<=? AND (origin_bucket_key=? OR destination_bucket_key=?)""",
            (day - 365, day, trade_bucket, trade_bucket),
        ).fetchone()[0] or 0.0)
        latest = conn.execute(
            "SELECT MAX(period_day) FROM aggregate_trade_balances WHERE bucket_key=? AND period_day<=?",
            (trade_bucket, day),
        ).fetchone()[0]
        if latest is not None:
            agg = conn.execute(
                """SELECT COALESCE(SUM(consumption_requirement),0) need,
                          COALESCE(SUM(local_absorption+import_quantity),0) covered
                   FROM aggregate_trade_balances WHERE bucket_key=? AND period_day=?""",
                (trade_bucket, int(latest)),
            ).fetchone()
            need = float(agg['need'] or 0.0)
            aggregate_trade_coverage = 1.0 if need <= 1e-9 else max(0.0, min(1.0, float(agg['covered'] or 0.0) / need))
        from .background_population import current_bucket_population
        bucket_pop = current_bucket_population(conn, trade_bucket)
        if bucket_pop > 0:
            aggregate_trade_per_1000 = aggregate_trade_volume / float(bucket_pop) * 1000.0
    treasury = conn.execute("SELECT cash,debt,tax_rate,toll_rate,status FROM regional_public_treasuries WHERE polity_id=?", (polity_id,)).fetchone()
    tax_year = float(conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN direction='inflow' THEN amount ELSE -amount END),0)
           FROM regional_fiscal_entries WHERE polity_id=? AND day>? AND day<=?""", (polity_id, day - 365, day)
    ).fetchone()[0] or 0.0)
    return {
        "polity_id": polity_id, "location_id": location_id, "day": day,
        "route_accessibility": round(accessibility, 3), "route_hazard": round(hazard, 3),
        "average_route_days": None if math.isinf(travel_days) else round(travel_days, 3),
        "route_details": route_evals, "active_enterprises": int(enterprises["n"]),
        "enterprise_cash": round(float(enterprises["cash"]), 3), "households": households,
        "population_estimate": round(population_est, 3), "trade_contracts_365": trade,
        "aggregate_trade_bucket": trade_bucket,
        "aggregate_trade_volume_365": round(aggregate_trade_volume, 3),
        "aggregate_trade_per_1000_365": round(aggregate_trade_per_1000, 6),
        "aggregate_trade_coverage": round(aggregate_trade_coverage, 6),
        "food_stress": round(_food_stress(conn, location_id), 3),
        "treasury_cash": round(float(treasury["cash"]), 3) if treasury else 0.0,
        "public_debt": round(float(treasury["debt"]), 3) if treasury else 0.0,
        "tax_rate": float(treasury["tax_rate"]) if treasury else 0.0,
        "toll_rate": float(treasury["toll_rate"]) if treasury else 0.0,
        "net_public_flow_365": round(tax_year, 3),
    }


def _refresh_commercial_context(conn: sqlite3.Connection, polity_id: int, location_id: int, day: int) -> None:
    state = regional_state(conn, polity_id, location_id, day=day)
    # These are low-resolution local-context projections derived from actual routes/activity;
    # they are not an authoritative prosperity score and can be rebuilt from source objects.
    security = _clamp(100.0 - float(state["route_hazard"]) * 2.5)
    access = float(state["route_accessibility"])
    # TRADE-01: public commercial context is now driven mainly by population-scaled bulk
    # circulation/coverage. Tracked contracts remain useful high-resolution evidence but no
    # longer pretend to measure the ordinary economy of an entire settlement.
    aggregate_signal = min(25.0, math.log10(1.0 + max(0.0, float(state["aggregate_trade_per_1000_365"]))) * 8.0)
    trade = _clamp(10.0 + access * .30 + state["active_enterprises"] * 1.5
                   + float(state["aggregate_trade_coverage"]) * 45.0 + aggregate_signal
                   + min(6.0, state["trade_contracts_365"] * 1.0) - state["food_stress"] * .1)
    traveler = _clamp(access * .62 + security * .28)
    foot = _clamp(20.0 + state["households"] * 1.8 + state["active_enterprises"] * 3.0 + traveler * .25)
    conn.execute(
        """INSERT INTO location_commercial_context(location_id,foot_traffic,traveler_flow,trade_flow,security,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(location_id) DO UPDATE SET foot_traffic=excluded.foot_traffic,
             traveler_flow=excluded.traveler_flow,trade_flow=excluded.trade_flow,security=excluded.security,
             updated_day=excluded.updated_day,
             metadata_json=json_patch(COALESCE(location_commercial_context.metadata_json,'{}'),excluded.metadata_json)""",
        (location_id, foot, traveler, trade, security, day,
         json.dumps({"growth01_projection": True, "source_day": day}, sort_keys=True)),
    )


def queue_regional_report(conn: sqlite3.Connection, polity_id: int, recipient_actor_id: int, location_id: int, *,
                          route_id: int | None = None, report_kind: str = "regional_condition") -> int:
    day = _day(conn)
    if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (recipient_actor_id,)).fetchone():
        raise ValueError("report recipient unavailable")
    skill = _administration_competence(conn, recipient_actor_id)
    lag = max(1, int(round(12.0 - skill * .10)))
    reliability = max(.55, min(.96, .58 + skill / 260.0))
    state = regional_state(conn, polity_id, location_id, day=day)
    if route_id is not None:
        detail = next((x for x in state["route_details"] if int(x["route_id"]) == int(route_id)), None)
        state["focus_route"] = detail
    cur = conn.execute(
        """INSERT INTO regional_administrative_reports(
               polity_id,recipient_actor_id,location_id,route_id,report_kind,observed_day,received_day,
               reliability,report_json,status
           ) VALUES (?,?,?,?,?,?,?,?,?,'pending')""",
        (polity_id, recipient_actor_id, location_id, route_id, report_kind, day, day + lag,
         reliability, json.dumps(state, sort_keys=True, default=str)),
    )
    return int(cur.lastrowid)


def _deliver_report(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> None:
    from .belief import ensure_claim, add_claim_evidence, observe_claim
    data = json.loads(row["report_json"] or "{}")
    focus = data.get("focus_route") or None
    if focus:
        access = float(focus.get("accessibility", 0.0))
        hazard = float(focus.get("hazard", 0.0))
        proposition = f"Route #{int(row['route_id'])} serving location #{int(row['location_id'])} has accessibility about {access:.1f} and hazard pressure about {hazard:.1f}."
        subject_kind, subject_id = "route", int(row["route_id"])
    else:
        proposition = (f"Location #{int(row['location_id'])} currently has {int(data.get('active_enterprises',0))} active enterprises, "
                       f"route accessibility about {float(data.get('route_accessibility',0)):.1f}, and food stress about {float(data.get('food_stress',0)):.1f}.")
        subject_kind, subject_id = "location", int(row["location_id"])
    claim_id = ensure_claim(conn, f"growth01:report:{int(row['id'])}", proposition,
                            subject_kind=subject_kind, subject_id=subject_id, created_day=int(row["observed_day"]),
                            source_kind="regional_administration")
    evidence_id = add_claim_evidence(
        conn, claim_id, evidence_kind="administrative_report", source_id=int(row["id"]), summary=proposition,
        reliability=float(row["reliability"]), salience=.8, domain_key="administration",
        location_id=int(row["location_id"]), available_from_day=int(row["received_day"]),
        metadata={"observed_day": int(row["observed_day"]), "regional_report_id": int(row["id"])},
    )
    observe_claim(conn, int(row["recipient_actor_id"]), claim_id, evidence_id,
                  received_day=int(row["received_day"]), access_kind="official_report", reason="regional_report_received")
    conn.execute("UPDATE regional_administrative_reports SET status='delivered',delivered_day=?,claim_id=?,evidence_id=? WHERE id=?",
                 (day, claim_id, evidence_id, int(row["id"])))


def _queue_periodic_reports(conn: sqlite3.Connection, treasury: sqlite3.Row, day: int) -> int:
    polity = conn.execute("SELECT ruler_actor_id FROM political_polities WHERE id=?", (int(treasury["polity_id"]),)).fetchone()
    if not polity or polity["ruler_actor_id"] is None:
        return 0
    actor_id = int(polity["ruler_actor_id"])
    made = 0
    for loc in _controlled_locations(conn, int(treasury["polity_id"])):
        recent = conn.execute(
            """SELECT 1 FROM regional_administrative_reports WHERE polity_id=? AND recipient_actor_id=? AND location_id=?
               AND observed_day>? ORDER BY id DESC LIMIT 1""", (int(treasury["polity_id"]), actor_id, loc, day - 90)
        ).fetchone()
        if recent:
            continue
        routes = conn.execute(
            """SELECT id FROM travel_routes WHERE status IN ('open','restricted') AND
               (from_location_id=? OR (bidirectional=1 AND to_location_id=?)) ORDER BY reliability ASC,id LIMIT 1""", (loc, loc)
        ).fetchone()
        queue_regional_report(conn, int(treasury["polity_id"]), actor_id, loc,
                              route_id=int(routes["id"]) if routes else None)
        made += 1
    return made


def _location_appeal(conn: sqlite3.Connection, location_id: int) -> float:
    ctx = conn.execute("SELECT * FROM location_commercial_context WHERE location_id=?", (location_id,)).fetchone()
    trade = float(ctx["trade_flow"]) if ctx else 30.0
    security = float(ctx["security"]) if ctx else 40.0
    jobs = int(conn.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE location_id=? AND status IN ('active','strained')", (location_id,)).fetchone()[0])
    food = _food_stress(conn, location_id)
    controller = conn.execute("SELECT controller_polity_id FROM territorial_control WHERE location_id=?", (location_id,)).fetchone()
    tax = 0.0
    if controller:
        tr = conn.execute("SELECT tax_rate,toll_rate FROM regional_public_treasuries WHERE polity_id=?", (int(controller[0]),)).fetchone()
        if tr:
            tax = (float(tr["tax_rate"]) + float(tr["toll_rate"])) * 100.0
    return trade * .35 + security * .35 + min(25.0, jobs * 3.0) - food * .35 - tax * .20


def _migration_response(conn: sqlite3.Connection, polity_id: int, day: int) -> int:
    from .household_life import schedule_household_migration
    from .ecology import find_route_path
    controlled = set(_controlled_locations(conn, polity_id))
    if not controlled:
        return 0
    candidates: list[tuple[float, int, int, int]] = []
    # Named households react only when materially pressured; we do not make every household optimize the map.
    rows = conn.execute(
        """SELECT * FROM households WHERE location_id IS NOT NULL AND status IN ('active','declining')
           AND NOT EXISTS(SELECT 1 FROM household_migration_plans mp WHERE mp.household_id=households.id AND mp.status IN ('planned','in_transit'))
           ORDER BY id"""
    ).fetchall()
    for h in rows:
        source = int(h["location_id"])
        pressured = str(h["status"]) == "declining" or float(h["liquidity"]) < 4.0
        if not pressured:
            continue
        source_score = _location_appeal(conn, source)
        possible: set[int] = set()
        for r in conn.execute(
            """SELECT * FROM travel_routes WHERE status IN ('open','restricted') AND
               (from_location_id=? OR (bidirectional=1 AND to_location_id=?))""", (source, source)
        ).fetchall():
            if int(r["from_location_id"]) == source:
                possible.add(int(r["to_location_id"]))
            elif int(r["bidirectional"]):
                possible.add(int(r["from_location_id"]))
        # For inward response, prioritize controlled destinations. For outward response, a household already
        # inside the county may leave for any adjacent materially better location.
        if source not in controlled:
            possible &= controlled
        best: tuple[float, int] | None = None
        for dest in sorted(possible):
            if not find_route_path(conn, source, dest, day=day):
                continue
            gain = _location_appeal(conn, dest) - source_score
            if gain >= 12.0 and (best is None or gain > best[0]):
                best = (gain, dest)
        if best:
            candidates.append((best[0], int(h["id"]), source, best[1]))
    moved = 0
    for gain, hid, source, dest in sorted(candidates, reverse=True)[:2]:
        try:
            mpid = schedule_household_migration(
                conn, hid, dest, day + 7,
                reason=f"experienced opportunity/security difference (appeal gap {gain:.1f})",
            )
            conn.execute(
                """INSERT INTO regional_migration_responses(
                       household_id,source_location_id,destination_location_id,day,appeal_gap,migration_plan_id,reason_json
                   ) VALUES (?,?,?,?,?,?,?)""",
                (hid, source, dest, day, gain, mpid,
                 json.dumps({"source_appeal": _location_appeal(conn, source), "destination_appeal": _location_appeal(conn, dest)}, sort_keys=True)),
            )
            moved += 1
        except Exception:
            continue
    return moved


def _snapshot(conn: sqlite3.Connection, polity_id: int, location_id: int, day: int) -> None:
    s = regional_state(conn, polity_id, location_id, day=day)
    conn.execute(
        """INSERT INTO regional_growth_snapshots(
               polity_id,location_id,day,population_estimate,households,active_enterprises,enterprise_cash,
               route_accessibility,route_hazard,average_route_days,trade_contracts_365,food_stress,
               treasury_cash,public_debt,net_public_flow_365,details_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (polity_id, location_id, day, s["population_estimate"], s["households"], s["active_enterprises"],
         s["enterprise_cash"], s["route_accessibility"], s["route_hazard"], s["average_route_days"],
         s["trade_contracts_365"], s["food_stress"], s["treasury_cash"], s["public_debt"],
         s["net_public_flow_365"], json.dumps(s, sort_keys=True, default=str)),
    )


def next_growth_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals: list[int] = []
    queries = [
        ("SELECT MIN(next_review_day) FROM regional_public_treasuries WHERE status IN ('active','strained') AND next_review_day>? AND next_review_day<=?",),
        ("SELECT MIN(next_review_day) FROM regional_public_projects WHERE status IN ('active','blocked') AND next_review_day>? AND next_review_day<=?",),
        ("SELECT MIN(next_review_day) FROM regional_security_assignments WHERE status IN ('active','unfunded') AND next_review_day>? AND next_review_day<=?",),
        ("SELECT MIN(received_day) FROM regional_administrative_reports WHERE status='pending' AND received_day>? AND received_day<=?",),
    ]
    try:
        for q in queries:
            r = conn.execute(q[0], (after_day, end_day)).fetchone()
            if r and r[0] is not None:
                vals.append(int(r[0]))
    except sqlite3.OperationalError:
        return None
    return min(vals) if vals else None


def process_due_growth(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict[str, int]:
    try:
        reports = conn.execute("SELECT * FROM regional_administrative_reports WHERE status='pending' AND received_day<=? ORDER BY received_day,id", (day,)).fetchall()
    except sqlite3.OperationalError:
        return {"treasuries": 0, "projects": 0, "completed_projects": 0, "security": 0, "reports": 0, "migrations": 0}
    for r in reports:
        _deliver_report(conn, r, day)

    security_rows = conn.execute(
        "SELECT * FROM regional_security_assignments WHERE status IN ('active','unfunded') AND next_review_day<=? ORDER BY next_review_day,id", (day,)
    ).fetchall()
    security_paid = sum(1 for r in security_rows if _review_security(conn, r, day))

    projects = conn.execute(
        "SELECT * FROM regional_public_projects WHERE status IN ('active','blocked') AND next_review_day<=? ORDER BY next_review_day,id", (day,)
    ).fetchall()
    completed = 0
    for p in projects:
        if _review_project(conn, p, day, event_logger) == "completed":
            completed += 1

    treasuries = conn.execute(
        "SELECT * FROM regional_public_treasuries WHERE status IN ('active','strained') AND next_review_day<=? ORDER BY next_review_day,polity_id", (day,)
    ).fetchall()
    migrations = queued_reports = 0
    for t in treasuries:
        _collect_revenue(conn, t, day)
        polity_id = int(t["polity_id"])
        for loc in _controlled_locations(conn, polity_id):
            _refresh_commercial_context(conn, polity_id, loc, day)
            _snapshot(conn, polity_id, loc, day)
        # Quarterly rather than monthly: migration is a consequential response, not a constant shuffle.
        if day % 90 < int(t["review_cadence_days"]):
            migrations += _migration_response(conn, polity_id, day)
        queued_reports += _queue_periodic_reports(conn, t, day)
        fresh = conn.execute("SELECT debt,cash,review_cadence_days FROM regional_public_treasuries WHERE polity_id=?", (polity_id,)).fetchone()
        status = "strained" if float(fresh["debt"]) > max(1.0, float(fresh["cash"]) * 2.5) else "active"
        conn.execute("UPDATE regional_public_treasuries SET status=?,next_review_day=? WHERE polity_id=?",
                     (status, day + int(fresh["review_cadence_days"]), polity_id))
    return {"treasuries": len(treasuries), "projects": len(projects), "completed_projects": completed,
            "security": len(security_rows), "security_paid": security_paid,
            "reports": len(reports), "reports_queued": queued_reports, "migrations": migrations}


def _best_material_good(conn: sqlite3.Connection, location_id: int) -> int | None:
    row = conn.execute(
        """SELECT g.id FROM market_goods g
           LEFT JOIN market_conditions mc ON mc.good_id=g.id AND mc.location_id=?
           WHERE g.good_key IN ('ordinary-timber','metalwork') OR g.category IN ('construction','timber','material')
           ORDER BY CASE WHEN mc.current_price IS NULL THEN 1 ELSE 0 END,COALESCE(mc.current_price,g.base_price),g.id LIMIT 1""",
        (location_id,),
    ).fetchone()
    return int(row[0]) if row else None


def growth_decision_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]):
    from .decision_runtime import DecisionCandidate
    out: list[DecisionCandidate] = []
    polities = conn.execute(
        """SELECT p.*,t.cash,t.debt,t.tax_rate,t.toll_rate FROM political_polities p
           JOIN regional_public_treasuries t ON t.polity_id=p.id
           WHERE p.ruler_actor_id=? AND p.status<>'dissolved' AND t.status IN ('active','strained') ORDER BY p.id""",
        (actor_id,),
    ).fetchall()
    if not polities:
        return out
    admin = _administration_competence(conn, actor_id)
    for p in polities:
        pid = int(p["id"])
        reports = conn.execute(
            """SELECT * FROM regional_administrative_reports
               WHERE polity_id=? AND recipient_actor_id=? AND status='delivered' AND delivered_day<=?
               ORDER BY observed_day DESC,id DESC LIMIT 6""", (pid, actor_id, day)
        ).fetchall()
        for r in reports:
            data = json.loads(r["report_json"] or "{}")
            focus = data.get("focus_route") or None
            if not focus or r["route_id"] is None:
                continue
            rid = int(r["route_id"])
            loc = int(r["location_id"])
            access = float(focus.get("accessibility", 100.0))
            hazard = float(focus.get("hazard", 0.0))
            age = max(0, day - int(r["observed_day"]))
            evidence_ids = (int(r["evidence_id"]),) if r["evidence_id"] is not None else ()
            claim_ids = (int(r["claim_id"]),) if r["claim_id"] is not None else ()
            if access < 82.0 and not conn.execute(
                "SELECT 1 FROM regional_public_projects WHERE polity_id=? AND route_id=? AND project_kind='road_repair' AND status IN ('active','blocked')",
                (pid, rid),
            ).fetchone():
                gid = _best_material_good(conn, loc)
                if gid is not None:
                    cost = 18.0 + max(0.0, 82.0 - access) * .7
                    out.append(DecisionCandidate(
                        key=f"growth:repair_route:{pid}:{rid}", provider_key="growth", action_kind="repair_route",
                        utility=4.3 + (82.0 - access) / 18.0 + min(.5, admin / 200.0) - min(.8, age / 180.0),
                        rationale=f"Commission repairs to specifically reported route #{rid}; its reported accessibility is {access:.1f}.",
                        execution_kind="growth_action",
                        payload={"polity_id": pid, "location_id": loc, "route_id": rid, "material_good_id": gid,
                                 "required_cash": round(cost, 2), "required_material_quantity": 12.0, "required_labor_days": 40.0},
                        information_basis={"regional_report_id": int(r["id"]), "observed_day": int(r["observed_day"]),
                                           "received_day": int(r["received_day"]), "administration_competence": admin},
                        claim_ids=claim_ids, evidence_ids=evidence_ids,
                        tags=("public_finance", "specific_route", "reported_condition"), estimated_cost=cost + 25.0, risk=.18,
                    ))
            if hazard > 10.0 and not conn.execute(
                "SELECT 1 FROM regional_security_assignments WHERE polity_id=? AND route_id=? AND status IN ('active','unfunded')",
                (pid, rid),
            ).fetchone():
                out.append(DecisionCandidate(
                    key=f"growth:secure_route:{pid}:{rid}", provider_key="growth", action_kind="secure_route",
                    utility=4.0 + min(2.3, hazard / 16.0) + min(.4, admin / 220.0) - min(.8, age / 180.0),
                    rationale=f"Fund a security assignment on specifically reported route #{rid}; reported hazard is {hazard:.1f}.",
                    execution_kind="growth_action",
                    payload={"polity_id": pid, "location_id": loc, "route_id": rid,
                             "monthly_cost": round(4.0 + hazard * .08, 2), "strength": min(75.0, 35.0 + admin * .25)},
                    information_basis={"regional_report_id": int(r["id"]), "observed_day": int(r["observed_day"]),
                                       "received_day": int(r["received_day"]), "administration_competence": admin},
                    claim_ids=claim_ids, evidence_ids=evidence_ids,
                    tags=("public_finance", "specific_route", "security"), estimated_cost=4.0 + hazard * .08, risk=.12,
                ))
        # Borrowing is a bounded option only when an active project is blocked by an empty treasury.
        blocked = conn.execute(
            """SELECT * FROM regional_public_projects WHERE polity_id=? AND status='blocked' AND blocked_reason LIKE '%treasury_empty%'
               ORDER BY id LIMIT 1""", (pid,)
        ).fetchone()
        if blocked and float(p["debt"]) < max(30.0, float(p["cash"]) * 3.0 + 40.0):
            amount = min(40.0, max(10.0, float(blocked["required_cash"]) * .5 + 10.0))
            out.append(DecisionCandidate(
                key=f"growth:borrow:{pid}:{int(blocked['id'])}", provider_key="growth", action_kind="borrow_for_project",
                utility=3.6 + min(.5, admin / 220.0), rationale=f"Borrow a bounded sum to keep public project #{int(blocked['id'])} from stalling for lack of cash.",
                execution_kind="growth_action", payload={"polity_id": pid, "project_id": int(blocked["id"]), "amount": amount},
                information_basis={"own_treasury": True, "project_id": int(blocked["id"]), "administration_competence": admin},
                tags=("public_credit", "specific_project"), estimated_cost=amount, risk=.38,
            ))
    return out


def _auto_assign_local_labor(conn: sqlite3.Connection, project_id: int, location_id: int, required_labor_days: float) -> int:
    rows = conn.execute(
        """SELECT * FROM households WHERE location_id=? AND status IN ('active','declining') ORDER BY liquidity ASC,id LIMIT 4""",
        (location_id,),
    ).fetchall()
    if not rows or required_labor_days <= 0:
        return 0
    remaining = required_labor_days
    count = 0
    for h in rows:
        share = min(remaining, max(8.0, required_labor_days / max(1, len(rows))))
        assign_project_household_labor(conn, project_id, int(h["id"]), labor_days=share, wage_per_day=0.35)
        remaining -= share
        count += 1
        if remaining <= 1e-9:
            break
    return count


def execute_growth_action(conn: sqlite3.Connection, actor_id: int, action_kind: str,
                          payload: dict[str, Any], day: int) -> dict[str, Any]:
    pid = int(payload.get("polity_id") or 0)
    row = conn.execute("SELECT ruler_actor_id FROM political_polities WHERE id=?", (pid,)).fetchone()
    if not row or row["ruler_actor_id"] is None or int(row["ruler_actor_id"]) != actor_id:
        return {"summary": "Public action blocked: actor is not the polity's current ruler.", "blocked": True}
    try:
        if action_kind == "repair_route":
            project_id = create_public_project(
                conn, pid, int(payload["location_id"]), "road_repair", f"Repair route #{int(payload['route_id'])}",
                route_id=int(payload["route_id"]), required_cash=float(payload.get("required_cash", 25.0)),
                required_labor_days=float(payload.get("required_labor_days", 40.0)),
                material_good_id=int(payload["material_good_id"]),
                required_material_quantity=float(payload.get("required_material_quantity", 12.0)),
                target_day=day + 180, effects={"reliability_gain": 28.0, "base_days_factor": .82},
                metadata={"ordered_by_actor_id": actor_id, "information_bounded": True},
            )
            _auto_assign_local_labor(conn, project_id, int(payload["location_id"]), float(payload.get("required_labor_days", 40.0)))
            return {"summary": f"Authorized tracked road-repair project #{project_id}; it must still acquire material, labor and cash over time.", "project_id": project_id}
        if action_kind == "secure_route":
            sid = add_security_assignment(
                conn, pid, route_id=int(payload["route_id"]), location_id=int(payload["location_id"]),
                monthly_cost=float(payload.get("monthly_cost", 5.0)), strength=float(payload.get("strength", 45.0)),
                metadata={"ordered_by_actor_id": actor_id, "information_bounded": True},
            )
            return {"summary": f"Authorized funded route-security assignment #{sid}; effectiveness now depends on recurring treasury payment.", "security_assignment_id": sid}
        if action_kind == "borrow_for_project":
            borrow_public_funds(conn, pid, float(payload["amount"]), description=f"Borrowing to continue public project #{int(payload['project_id'])}")
            conn.execute("UPDATE regional_public_projects SET status='active',blocked_reason=NULL,next_review_day=? WHERE id=? AND polity_id=?",
                         (day + 1, int(payload["project_id"]), pid))
            return {"summary": f"Borrowed {float(payload['amount']):.2f} into the public treasury for project #{int(payload['project_id'])}; debt service now applies.", "project_id": int(payload["project_id"])}
        return {"summary": f"Public action blocked: unsupported action {action_kind}.", "blocked": True}
    except Exception as exc:
        return {"summary": f"Public action blocked: {exc}", "blocked": True}
