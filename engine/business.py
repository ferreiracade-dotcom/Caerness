from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any


# Caerness's business vocabulary is package data: worlds/caerness/archetypes.json.
CAERNESS_ARCHETYPES_PATH = Path(__file__).resolve().parent.parent / "worlds" / "caerness" / "archetypes.json"


_CONTEXT_DEFAULTS = {
    "foot_traffic": 50.0,
    "traveler_flow": 50.0,
    "disposable_income": 50.0,
    "trade_flow": 50.0,
    "elite_patronage": 50.0,
    "cultural_activity": 50.0,
    "credit_demand": 50.0,
    "military_demand": 50.0,
    "health_demand": 50.0,
    "craft_demand": 50.0,
    "construction_demand": 50.0,
    "regulation": 50.0,
    "security": 50.0,
    "event_activity": 50.0,
    "reputation_climate": 50.0,
}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _loads(text: str | None) -> dict[str, Any]:
    try:
        return json.loads(text or "{}")
    except Exception:
        return {}


def _package_archetypes_path(conn: sqlite3.Connection | None) -> Path | None:
    if conn is not None and conn.execute("SELECT 1 FROM engine_meta WHERE key='world_package_id'").fetchone():
        from .world_package import package_for
        return package_for(conn).data.get("archetypes")
    return None


def package_has_own_archetypes(conn: sqlite3.Connection | None) -> bool:
    """True when the campaign's package supplies an archetypes file other than the Caerness one."""
    path = _package_archetypes_path(conn)
    return path is not None and Path(path).resolve() != CAERNESS_ARCHETYPES_PATH.resolve()


def archetypes(conn: sqlite3.Connection | None = None) -> dict[str, dict[str, Any]]:
    """The world package's archetypes.json when it defines one, else worlds/caerness/archetypes.json."""
    path = _package_archetypes_path(conn) or CAERNESS_ARCHETYPES_PATH
    return json.loads(Path(path).read_text(encoding="utf-8"))


def seed_business_archetypes(conn: sqlite3.Connection) -> int:
    count = 0
    catalog = archetypes(conn)
    if package_has_own_archetypes(conn):  # a package with its own vocabulary: drop the unused Caerness rows seeded at init
        conn.execute("DELETE FROM business_archetypes WHERE archetype_key NOT IN (%s) AND id NOT IN (SELECT archetype_id FROM enterprise_business_profiles)"
                     % ",".join("?" * len(catalog)), tuple(catalog))
    for key, spec in catalog.items():
        conn.execute(
            """INSERT INTO business_archetypes(
                   archetype_key,name,sector,default_enterprise_kind,base_revenue_per_30,base_cost_ratio,
                   demand_weights_json,regulation_exposure,skill_sensitive,capital_sensitive,notes
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(archetype_key) DO UPDATE SET
                   name=excluded.name,sector=excluded.sector,default_enterprise_kind=excluded.default_enterprise_kind,
                   base_revenue_per_30=excluded.base_revenue_per_30,base_cost_ratio=excluded.base_cost_ratio,
                   demand_weights_json=excluded.demand_weights_json,regulation_exposure=excluded.regulation_exposure,
                   skill_sensitive=excluded.skill_sensitive,capital_sensitive=excluded.capital_sensitive""",
            (
                key, spec["name"], spec["sector"], spec["enterprise_kind"], float(spec["base_revenue"]),
                float(spec["cost_ratio"]), json.dumps(spec["weights"], sort_keys=True), float(spec.get("regulation", 0)),
                1 if spec.get("skill_sensitive") else 0, 1 if spec.get("capital_sensitive") else 0,
                "Engine business archetype; existence in a campaign is not implied by this vocabulary.",
            ),
        )
        count += 1
    return count


def business_catalog(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    seed_business_archetypes(conn)
    rows = conn.execute(
        "SELECT archetype_key,name,sector,default_enterprise_kind,base_revenue_per_30,base_cost_ratio,regulation_exposure,skill_sensitive,capital_sensitive FROM business_archetypes ORDER BY sector,name"
    ).fetchall()
    return [dict(r) for r in rows]


def set_commercial_context(conn: sqlite3.Connection, location_id: int, **values: float) -> None:
    day = _day(conn)
    current = conn.execute("SELECT * FROM location_commercial_context WHERE location_id=?", (location_id,)).fetchone()
    data = dict(_CONTEXT_DEFAULTS)
    if current:
        for k in _CONTEXT_DEFAULTS:
            data[k] = float(current[k])
    for key, value in values.items():
        if key not in _CONTEXT_DEFAULTS:
            raise ValueError(f"Unknown commercial context field: {key}")
        data[key] = _clamp(value)
    conn.execute(
        """INSERT INTO location_commercial_context(
               location_id,foot_traffic,traveler_flow,disposable_income,trade_flow,elite_patronage,cultural_activity,
               credit_demand,military_demand,health_demand,craft_demand,construction_demand,regulation,security,
               event_activity,reputation_climate,updated_day
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(location_id) DO UPDATE SET
               foot_traffic=excluded.foot_traffic,traveler_flow=excluded.traveler_flow,
               disposable_income=excluded.disposable_income,trade_flow=excluded.trade_flow,
               elite_patronage=excluded.elite_patronage,cultural_activity=excluded.cultural_activity,
               credit_demand=excluded.credit_demand,military_demand=excluded.military_demand,
               health_demand=excluded.health_demand,craft_demand=excluded.craft_demand,
               construction_demand=excluded.construction_demand,regulation=excluded.regulation,
               security=excluded.security,event_activity=excluded.event_activity,
               reputation_climate=excluded.reputation_climate,updated_day=excluded.updated_day""",
        (location_id, *[data[k] for k in _CONTEXT_DEFAULTS], day),
    )


def commercial_context(conn: sqlite3.Connection, location_id: int | None) -> dict[str, float]:
    data = dict(_CONTEXT_DEFAULTS)
    if location_id is None:
        return data
    row = conn.execute("SELECT * FROM location_commercial_context WHERE location_id=?", (location_id,)).fetchone()
    if row:
        for key in _CONTEXT_DEFAULTS:
            data[key] = float(row[key])
    return data


def configure_enterprise_business(
    conn: sqlite3.Connection,
    enterprise_id: int,
    archetype_key: str,
    *,
    quality: float = 50,
    price_position: float = 50,
    capacity: float = 50,
    clientele_fit: float = 50,
    service_reliability: float = 50,
    regulatory_pressure: float = 0,
    cadence_days: int = 30,
    metadata: dict[str, Any] | None = None,
) -> int:
    seed_business_archetypes(conn)
    enterprise = conn.execute("SELECT * FROM civilian_enterprises WHERE id=?", (enterprise_id,)).fetchone()
    if not enterprise:
        raise ValueError(f"Unknown enterprise #{enterprise_id}")
    archetype = conn.execute("SELECT * FROM business_archetypes WHERE archetype_key=?", (archetype_key,)).fetchone()
    if not archetype:
        raise ValueError(f"Unknown business archetype: {archetype_key}")
    day = _day(conn)
    conn.execute(
        """INSERT INTO enterprise_business_profiles(
               enterprise_id,archetype_id,quality,price_position,capacity,utilization,clientele_fit,
               service_reliability,regulatory_pressure,last_resolved_day,next_review_day,metadata_json
           ) VALUES (?,?,?,?,?,0,?,?,?,?,?,?)
           ON CONFLICT(enterprise_id) DO UPDATE SET
               archetype_id=excluded.archetype_id,quality=excluded.quality,price_position=excluded.price_position,
               capacity=excluded.capacity,clientele_fit=excluded.clientele_fit,
               service_reliability=excluded.service_reliability,regulatory_pressure=excluded.regulatory_pressure,
               next_review_day=excluded.next_review_day,metadata_json=excluded.metadata_json""",
        (enterprise_id, int(archetype["id"]), _clamp(quality), _clamp(price_position), max(1.0, float(capacity)),
         _clamp(clientele_fit), _clamp(service_reliability), _clamp(regulatory_pressure), day, day + max(1, int(cadence_days)),
         json.dumps(metadata or {}, sort_keys=True)),
    )
    # Keep broad enterprise_kind consistent enough for existing systems without making
    # the archetype itself depend on the broad kind.
    if str(enterprise["enterprise_kind"]) == "other":
        conn.execute("UPDATE civilian_enterprises SET enterprise_kind=?,updated_day=? WHERE id=?",
                     (archetype["default_enterprise_kind"], day, enterprise_id))
    return enterprise_id


def _skill_factor(conn: sqlite3.Connection, enterprise_id: int, enterprise: sqlite3.Row) -> float:
    vals = [float(enterprise["labor_capacity"])]
    rows = conn.execute("SELECT skilled_labor,efficiency FROM production_sites WHERE enterprise_id=? AND active=1", (enterprise_id,)).fetchall()
    for row in rows:
        vals.extend([float(row["skilled_labor"]), float(row["efficiency"])])
    return sum(vals) / len(vals) if vals else 50.0


def _demand_score(weights: dict[str, float], ctx: dict[str, float]) -> float:
    total = 0.0
    denom = 0.0
    for key, weight in weights.items():
        w = float(weight)
        if key == "security_inverse":
            value = 100.0 - ctx.get("security", 50.0)
        else:
            value = ctx.get(key, 50.0)
        total += value * abs(w)
        denom += abs(w)
    return 50.0 if denom <= 0 else _clamp(total / denom)


def resolve_business_cycle(conn: sqlite3.Connection, enterprise_id: int, day: int | None = None) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    row = conn.execute(
        """SELECT p.*,e.name enterprise_name,e.location_id,e.cash,e.capital,e.debt,e.reputation,e.admin_quality,e.labor_capacity,e.status enterprise_status,
                  a.archetype_key,a.name archetype_name,a.sector,a.base_revenue_per_30,a.base_cost_ratio,a.demand_weights_json,
                  a.regulation_exposure,a.skill_sensitive,a.capital_sensitive
           FROM enterprise_business_profiles p
           JOIN civilian_enterprises e ON e.id=p.enterprise_id
           JOIN business_archetypes a ON a.id=p.archetype_id
           WHERE p.enterprise_id=?""",
        (enterprise_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Enterprise #{enterprise_id} has no business profile")
    if row["enterprise_status"] in ("closed", "historical"):
        return {"enterprise_id": enterprise_id, "day": day, "status": row["enterprise_status"], "skipped": True}
    elapsed = max(0, day - int(row["last_resolved_day"]))
    if elapsed <= 0:
        return {"enterprise_id": enterprise_id, "day": day, "status": "no_elapsed_time", "skipped": True}

    ctx = commercial_context(conn, row["location_id"])
    weights = _loads(row["demand_weights_json"])
    context_demand = _demand_score(weights, ctx)
    reputation = float(row["reputation"])
    quality = float(row["quality"])
    reliability = float(row["service_reliability"])
    clientele = float(row["clientele_fit"])
    admin = float(row["admin_quality"])
    skill = _skill_factor(conn, enterprise_id, row)

    # Price position is not a universal "high is good" stat. Very high pricing needs a strong
    # clientele/reputation base; very low pricing supports volume but reduces revenue per client.
    price = float(row["price_position"])
    price_fit = _clamp(100.0 - abs(price - (0.55 * ctx["disposable_income"] + 0.45 * ctx["elite_patronage"])))

    demand_index = (
        context_demand * 0.48 + reputation * 0.14 + quality * 0.12 + reliability * 0.08 +
        clientele * 0.08 + admin * 0.05 + price_fit * 0.05
    )
    if int(row["skill_sensitive"]):
        demand_index = demand_index * 0.82 + skill * 0.18

    exposure = float(row["regulation_exposure"])
    regulation_load = (ctx["regulation"] * 0.65 + float(row["regulatory_pressure"]) * 0.35) / 100.0
    regulation_factor = max(0.45, 1.0 - exposure * regulation_load)
    security_factor = 0.88 + 0.12 * (ctx["security"] / 100.0)
    utilization_target = _clamp(demand_index * regulation_factor * security_factor)
    old_util = float(row["utilization"])
    utilization = _clamp(old_util * 0.35 + utilization_target * 0.65)

    capacity_scale = max(0.2, float(row["capacity"]) / 50.0)
    time_scale = elapsed / 30.0
    price_multiplier = 0.70 + 0.006 * price
    capital_factor = 1.0
    if int(row["capital_sensitive"]):
        capital_base = max(0.0, float(row["capital"]) + float(row["cash"]) - 0.5 * float(row["debt"]))
        capital_factor = max(0.45, min(1.75, 0.60 + math.log1p(capital_base) / 8.0))

    gross = float(row["base_revenue_per_30"]) * capacity_scale * (utilization / 100.0) * time_scale * price_multiplier * capital_factor
    drivers_note = ""
    from . import business_data
    if business_data.load(conn) is not None:  # a package with BZ1 business data: the shared drivers say what else moved this month
        from . import business_drivers
        cond_row = conn.execute("""SELECT MIN(b.condition) FROM place_details d JOIN buildings b ON b.id=d.building_id
                                   WHERE d.enterprise_id=? AND b.status<>'destroyed'""", (enterprise_id,)).fetchone()
        factors = business_drivers.reading(conn, "enterprise", enterprise_id, day, sector=row["sector"], location_id=row["location_id"],
                                           quality=quality, condition=float(cond_row[0]) if cond_row and cond_row[0] is not None else 100.0,
                                           demand_weights=weights)
        business_drivers.record(conn, "enterprise", enterprise_id, day, factors)
        # the cycle already weighs local demand and the firm's quality (demand_index); the other drivers multiply the month
        applied = business_drivers.total({k: f for k, f in factors.items() if k not in ("demand", "form")})
        gross *= applied
        drivers_note = f"; drivers x{applied:.3f}"

    # Finance businesses additionally earn a bounded return from actual outstanding credit they carry.
    credit_income = 0.0
    if row["sector"] == "finance":
        cr = conn.execute(
            "SELECT COALESCE(SUM(outstanding),0) FROM credit_agreements WHERE lender_enterprise_id=? AND status IN ('current','late')",
            (enterprise_id,),
        ).fetchone()[0]
        credit_income = float(cr or 0.0) * 0.008 * time_scale * (0.7 + demand_index / 160.0)
        gross += credit_income

    # Craft firms with active production already receive sale revenue from the production layer.
    # Their business-cycle revenue is therefore reduced to represent commissions, repairs and front-of-house work.
    if row["sector"] == "craft":
        sites = int(conn.execute("SELECT COUNT(*) FROM production_sites WHERE enterprise_id=? AND active=1", (enterprise_id,)).fetchone()[0])
        if sites:
            gross *= 0.45

    cost_ratio = float(row["base_cost_ratio"])
    # Low utilization still carries overhead. High skill and admin quality reduce waste, not wages to zero.
    efficiency_factor = 1.12 - 0.0012 * admin - (0.0008 * skill if int(row["skill_sensitive"]) else 0.0)
    operating_cost = max(0.0, gross * cost_ratio * efficiency_factor + float(row["capacity"]) * 0.035 * time_scale)
    net = gross - operating_cost

    # Persist accounting as authoritative economic history.
    if gross > 0:
        conn.execute(
            """INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,source_kind,source_id)
               VALUES (?,?,?,?,?,'business_cycle',?)""",
            (enterprise_id, day, "revenue", round(gross, 4), f"{row['archetype_name']} operating revenue", enterprise_id),
        )
    if operating_cost > 0:
        conn.execute(
            """INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,source_kind,source_id)
               VALUES (?,?,?,?,?,'business_cycle',?)""",
            (enterprise_id, day, "expense", round(operating_cost, 4), f"{row['archetype_name']} operating costs", enterprise_id),
        )
    raw_cash = float(row["cash"]) + net
    debt = float(row["debt"])
    unfunded_deficit = max(0.0, -raw_cash)
    # Cash is liquid balance, not an implicit overdraft. Costs that cannot be met become
    # generic operating liabilities; no lender is invented and no contractual credit agreement
    # is implied by this aggregate accounting state.
    cash = max(0.0, raw_cash)
    if unfunded_deficit > 0:
        debt += unfunded_deficit
    status = str(row["enterprise_status"])
    if debt > max(10.0, float(row["capital"]) * 1.5) or (unfunded_deficit > 0 and float(row["capital"]) <= 0):
        status = "insolvent"
    elif unfunded_deficit > 0 or debt > max(10.0, float(row["capital"]) * 1.2):
        status = "strained"
    elif status in ("strained", "insolvent") and cash > 0 and debt <= max(10.0, float(row["capital"]) * 1.2):
        status = "active"
    # PROFESSION-01 business ecology: insolvency is persistent world state, not a one-cycle label.
    # A firm that stays insolvent for roughly six months closes, while all accounts/debts/history remain.
    eco = conn.execute("SELECT * FROM enterprise_ecology_state WHERE enterprise_id=?", (enterprise_id,)).fetchone() if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_ecology_state'").fetchone() else None
    if eco is None and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_ecology_state'").fetchone():
        conn.execute("""INSERT INTO enterprise_ecology_state(enterprise_id,founded_day,crystallized_day,structural_origin,last_review_day,metadata_json)
                        VALUES (?,NULL,0,'preexisting',?,?)""", (enterprise_id,day,json.dumps({"opening_founded_day_unknown":True},sort_keys=True)))
        eco = conn.execute("SELECT * FROM enterprise_ecology_state WHERE enterprise_id=?", (enterprise_id,)).fetchone()
    if eco is not None:
        profitable = int(eco["profitable_streak_days"] or 0)
        profitable = profitable + elapsed if net > 0 else 0
        insolvent_since = eco["insolvent_since_day"]
        if status == "insolvent":
            if insolvent_since is None:
                insolvent_since = day
            if day - int(insolvent_since) >= 180:
                status = "closed"
                conn.execute("UPDATE enterprise_ecology_state SET profitable_streak_days=?,insolvent_since_day=?,closed_day=?,closure_reason='sustained_insolvency',last_review_day=? WHERE enterprise_id=?",
                             (profitable,int(insolvent_since),day,day,enterprise_id))
            else:
                conn.execute("UPDATE enterprise_ecology_state SET profitable_streak_days=?,insolvent_since_day=?,last_review_day=? WHERE enterprise_id=?",
                             (profitable,int(insolvent_since),day,enterprise_id))
        else:
            conn.execute("UPDATE enterprise_ecology_state SET profitable_streak_days=?,insolvent_since_day=NULL,last_review_day=? WHERE enterprise_id=?",
                         (profitable,day,enterprise_id))
    conn.execute("UPDATE civilian_enterprises SET cash=?,debt=?,status=?,updated_day=? WHERE id=?", (cash, debt, status, day, enterprise_id))
    from .payroll import run_business_payroll
    run_business_payroll(conn, enterprise_id, operating_cost, unfunded_deficit, day)
    if status == "active" and debt <= 0 and net > 0:
        _owner_draw(conn, enterprise_id, operating_cost)
    conn.execute(
        """UPDATE enterprise_business_profiles SET utilization=?,last_resolved_day=?,next_review_day=?,updated_day=? WHERE enterprise_id=?""",
        (utilization, day, day + 30, day, enterprise_id),
    )
    cur = conn.execute(
        """INSERT INTO business_cycles(
               enterprise_id,day,elapsed_days,demand_index,utilization,gross_revenue,operating_cost,net_income,
               context_json,notes
           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (enterprise_id, day, elapsed, demand_index, utilization, gross, operating_cost, net,
         json.dumps(ctx, sort_keys=True), f"Resolved as {row['archetype_key']}; credit income {credit_income:.2f}; unfunded operating deficit {unfunded_deficit:.2f} capitalized as generic liabilities.{drivers_note}"),
    )
    return {
        "cycle_id": int(cur.lastrowid), "enterprise_id": enterprise_id, "enterprise": row["enterprise_name"],
        "archetype": row["archetype_key"], "sector": row["sector"], "day": day, "elapsed_days": elapsed,
        "context_demand": round(context_demand, 3), "demand_index": round(demand_index, 3),
        "utilization": round(utilization, 3), "gross_revenue": round(gross, 4),
        "operating_cost": round(operating_cost, 4), "net_income": round(net, 4), "status": status,
    }


def _owner_draw(conn: sqlite3.Connection, enterprise_id: int, operating_cost: float) -> float:
    """Monthly draw: an active, debt-free business pays its natural-person owner up to half of its cash
    above a working floor (two months of operating cost), into the owner's household, else purse."""
    row = conn.execute("SELECT owner_actor_id,household_id,cash FROM civilian_enterprises WHERE id=?", (enterprise_id,)).fetchone()
    if not row:
        return 0.0
    floor = 2.0 * max(0.0, float(operating_cost))
    amount = round(0.5 * (float(row["cash"]) - floor), 4)
    if amount < 0.01:
        return 0.0
    from . import ledger
    if row["owner_actor_id"] is None:
        # No natural-person owner: a front's profit goes to the outfit that holds it.
        link = conn.execute("""SELECT l.organization_id FROM underworld_business_links l JOIN underworld_organizations o ON o.id=l.organization_id
                               WHERE l.enterprise_id=? AND l.status='active' AND l.link_kind IN ('owned_front','controlled_front')
                               AND o.status IN ('active','strained','fragmented') ORDER BY l.id LIMIT 1""", (enterprise_id,)).fetchone()
        if link is None:
            return 0.0
        try:
            return ledger.transfer(conn, ("business", enterprise_id), ("outfit", int(link[0])), amount, flow_kind="distribution", purpose="front's take")
        except ValueError:
            return 0.0
    owner = int(row["owner_actor_id"])
    hid = row["household_id"]
    if hid is None:
        r = conn.execute("""SELECT h.id FROM households h WHERE h.head_actor_id=? AND h.status NOT IN ('dissolved','historical')
                            ORDER BY h.id LIMIT 1""", (owner,)).fetchone()
        hid = r[0] if r else None
    dst = ("household", int(hid)) if hid is not None else ("person", owner)
    try:
        return ledger.transfer(conn, ("business", enterprise_id), dst, amount, flow_kind="distribution", purpose="owner's draw")
    except ValueError:
        return 0.0


def next_business_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    row = conn.execute(
        """SELECT MIN(p.next_review_day)
           FROM enterprise_business_profiles p JOIN civilian_enterprises e ON e.id=p.enterprise_id
           WHERE e.status IN ('active','strained','insolvent') AND p.next_review_day>? AND p.next_review_day<=?""",
        (after_day, end_day),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def process_due_businesses(conn: sqlite3.Connection, day: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT p.enterprise_id FROM enterprise_business_profiles p
           JOIN civilian_enterprises e ON e.id=p.enterprise_id
           WHERE e.status IN ('active','strained','insolvent') AND p.next_review_day<=?
           ORDER BY p.next_review_day,p.enterprise_id""",
        (day,),
    ).fetchall()
    return [resolve_business_cycle(conn, int(r[0]), day) for r in rows]


def business_profile(conn: sqlite3.Connection, enterprise_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT p.*,e.name enterprise_name,e.enterprise_kind,e.location_id,e.cash,e.capital,e.debt,e.reputation,e.status enterprise_status,
                  a.archetype_key,a.name archetype_name,a.sector,a.demand_weights_json,a.regulation_exposure
           FROM enterprise_business_profiles p
           JOIN civilian_enterprises e ON e.id=p.enterprise_id
           JOIN business_archetypes a ON a.id=p.archetype_id
           WHERE p.enterprise_id=?""",
        (enterprise_id,),
    ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["demand_weights"] = _loads(out.pop("demand_weights_json", "{}"))
    out["commercial_context"] = commercial_context(conn, out.get("location_id"))
    from . import business_drivers
    out["why"] = business_drivers.why(conn, "enterprise", enterprise_id)
    out["recent_cycles"] = [dict(r) for r in conn.execute(
        "SELECT id,day,elapsed_days,demand_index,utilization,gross_revenue,operating_cost,net_income,notes FROM business_cycles WHERE enterprise_id=? ORDER BY day DESC,id DESC LIMIT 12",
        (enterprise_id,),
    ).fetchall()]
    return out


def business_ecology_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    seed_business_archetypes(conn)
    return {
        "archetypes": int(conn.execute("SELECT COUNT(*) FROM business_archetypes").fetchone()[0]),
        "configured_businesses": int(conn.execute("SELECT COUNT(*) FROM enterprise_business_profiles").fetchone()[0]),
        "commercial_contexts": int(conn.execute("SELECT COUNT(*) FROM location_commercial_context").fetchone()[0]),
        "business_cycles": int(conn.execute("SELECT COUNT(*) FROM business_cycles").fetchone()[0]),
        "by_sector": {r["sector"]: int(r["n"]) for r in conn.execute(
            """SELECT a.sector,COUNT(*) n FROM enterprise_business_profiles p JOIN business_archetypes a ON a.id=p.archetype_id GROUP BY a.sector ORDER BY a.sector"""
        ).fetchall()},
        "principle": "Business archetypes change demand, cost, regulation and clientele behavior; they are not cosmetic labels.",
    }
