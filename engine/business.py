from __future__ import annotations

import json
import math
import sqlite3
from typing import Any


# Engine-level business vocabulary. These are simulation archetypes, not setting-canon
# claims that every city must contain every type. Campaigns instantiate only what exists.
_ARCHETYPES: dict[str, dict[str, Any]] = {
    # Hospitality / travel
    "inn": {"name":"Inn", "sector":"hospitality", "enterprise_kind":"service", "base_revenue":34, "cost_ratio":0.62,
            "weights":{"traveler_flow":0.42,"foot_traffic":0.18,"event_activity":0.16,"disposable_income":0.10,"security":0.14}, "regulation":0.05},
    "tavern": {"name":"Tavern", "sector":"hospitality", "enterprise_kind":"service", "base_revenue":30, "cost_ratio":0.58,
               "weights":{"foot_traffic":0.30,"traveler_flow":0.20,"disposable_income":0.18,"event_activity":0.20,"security":0.12}, "regulation":0.08},
    "bathhouse": {"name":"Bathhouse", "sector":"hospitality", "enterprise_kind":"service", "base_revenue":29, "cost_ratio":0.64,
                  "weights":{"foot_traffic":0.24,"disposable_income":0.24,"traveler_flow":0.12,"elite_patronage":0.12,"security":0.12,"event_activity":0.16}, "regulation":0.06},
    "stable": {"name":"Stable", "sector":"logistics", "enterprise_kind":"service", "base_revenue":26, "cost_ratio":0.67,
               "weights":{"traveler_flow":0.34,"trade_flow":0.28,"foot_traffic":0.12,"security":0.16,"event_activity":0.10}, "regulation":0.03},
    "horse_breeder": {"name":"Horse Breeder / Stud", "sector":"agriculture_logistics", "enterprise_kind":"estate", "base_revenue":31, "cost_ratio":0.71,
               "weights":{"military_demand":0.30,"elite_patronage":0.22,"trade_flow":0.16,"security":0.10,"reputation_climate":0.22}, "regulation":0.04, "skill_sensitive":True},
    # Entertainment / social venues. Pleasure houses are represented only as non-explicit
    # economic/social institutions: clientele, reputation, regulation, staffing and information flow.
    "theatre": {"name":"Theatre", "sector":"entertainment", "enterprise_kind":"service", "base_revenue":42, "cost_ratio":0.70,
                "weights":{"cultural_activity":0.34,"disposable_income":0.24,"elite_patronage":0.14,"foot_traffic":0.12,"event_activity":0.16}, "regulation":0.08},
    "music_hall": {"name":"Music Hall", "sector":"entertainment", "enterprise_kind":"service", "base_revenue":36, "cost_ratio":0.68,
                   "weights":{"cultural_activity":0.30,"disposable_income":0.24,"foot_traffic":0.18,"event_activity":0.18,"elite_patronage":0.10}, "regulation":0.08},
    "gambling_house": {"name":"Gambling House", "sector":"regulated_entertainment", "enterprise_kind":"service", "base_revenue":48, "cost_ratio":0.55,
                       "weights":{"foot_traffic":0.22,"disposable_income":0.24,"traveler_flow":0.14,"event_activity":0.20,"elite_patronage":0.10,"security":0.10}, "regulation":0.46},
    "pleasure_house": {"name":"Pleasure / Courtesan House", "sector":"regulated_entertainment", "enterprise_kind":"service", "base_revenue":44, "cost_ratio":0.66,
                       "weights":{"foot_traffic":0.20,"disposable_income":0.22,"traveler_flow":0.12,"elite_patronage":0.18,"event_activity":0.14,"security":0.14}, "regulation":0.42},
    "salon": {"name":"Private Salon", "sector":"entertainment", "enterprise_kind":"service", "base_revenue":31, "cost_ratio":0.62,
              "weights":{"elite_patronage":0.34,"cultural_activity":0.26,"disposable_income":0.16,"reputation_climate":0.14,"security":0.10}, "regulation":0.04},
    # Finance
    "moneylender": {"name":"Moneylender", "sector":"finance", "enterprise_kind":"service", "base_revenue":24, "cost_ratio":0.36,
                    "weights":{"credit_demand":0.48,"trade_flow":0.18,"disposable_income":0.08,"security":0.10,"reputation_climate":0.16}, "regulation":0.15, "capital_sensitive":True},
    "loan_house": {"name":"Loan House", "sector":"finance", "enterprise_kind":"service", "base_revenue":33, "cost_ratio":0.40,
                   "weights":{"credit_demand":0.42,"trade_flow":0.24,"elite_patronage":0.10,"security":0.10,"reputation_climate":0.14}, "regulation":0.18, "capital_sensitive":True},
    "pawnbroker": {"name":"Pawnbroker", "sector":"finance", "enterprise_kind":"shop", "base_revenue":23, "cost_ratio":0.48,
                   "weights":{"credit_demand":0.34,"foot_traffic":0.22,"trade_flow":0.12,"disposable_income":0.10,"security":0.10,"reputation_climate":0.12}, "regulation":0.12, "capital_sensitive":True},
    # Craft / manufacturing
    "smithy": {"name":"Smithy", "sector":"craft", "enterprise_kind":"workshop", "base_revenue":24, "cost_ratio":0.61,
               "weights":{"craft_demand":0.28,"trade_flow":0.18,"military_demand":0.26,"foot_traffic":0.08,"security":0.08,"disposable_income":0.12}, "regulation":0.02, "skill_sensitive":True},
    "armorer": {"name":"Armorer", "sector":"craft", "enterprise_kind":"workshop", "base_revenue":29, "cost_ratio":0.66,
                "weights":{"military_demand":0.40,"craft_demand":0.22,"trade_flow":0.16,"elite_patronage":0.10,"security":0.12}, "regulation":0.04, "skill_sensitive":True},
    "tailor": {"name":"Tailor", "sector":"craft", "enterprise_kind":"workshop", "base_revenue":25, "cost_ratio":0.57,
               "weights":{"disposable_income":0.24,"craft_demand":0.18,"foot_traffic":0.12,"elite_patronage":0.22,"cultural_activity":0.14,"reputation_climate":0.10}, "regulation":0.01, "skill_sensitive":True},
    "weaver": {"name":"Weaver", "sector":"craft", "enterprise_kind":"workshop", "base_revenue":25, "cost_ratio":0.63,
               "weights":{"craft_demand":0.30,"trade_flow":0.22,"disposable_income":0.18,"cultural_activity":0.12,"elite_patronage":0.08,"security":0.10}, "regulation":0.01, "skill_sensitive":True},
    "jeweler": {"name":"Jeweler", "sector":"craft", "enterprise_kind":"workshop", "base_revenue":34, "cost_ratio":0.60,
                "weights":{"elite_patronage":0.34,"disposable_income":0.24,"cultural_activity":0.12,"trade_flow":0.10,"reputation_climate":0.20}, "regulation":0.03, "skill_sensitive":True},
    "carpenter": {"name":"Carpenter", "sector":"craft", "enterprise_kind":"workshop", "base_revenue":24, "cost_ratio":0.60,
                  "weights":{"craft_demand":0.34,"trade_flow":0.14,"construction_demand":0.30,"disposable_income":0.10,"security":0.12}, "regulation":0.01, "skill_sensitive":True},
    "instrument_maker": {"name":"Instrument Maker", "sector":"craft", "enterprise_kind":"workshop", "base_revenue":27, "cost_ratio":0.60,
                         "weights":{"cultural_activity":0.28,"elite_patronage":0.22,"craft_demand":0.18,"disposable_income":0.18,"reputation_climate":0.14}, "regulation":0.01, "skill_sensitive":True},
    "refiner": {"name":"Refiner", "sector":"craft", "enterprise_kind":"workshop", "base_revenue":31, "cost_ratio":0.69,
                "weights":{"craft_demand":0.22,"trade_flow":0.24,"health_demand":0.14,"military_demand":0.14,"elite_patronage":0.10,"security":0.16}, "regulation":0.10, "skill_sensitive":True},
    # Retail
    "food_shop": {"name":"Food Shop", "sector":"retail", "enterprise_kind":"shop", "base_revenue":27, "cost_ratio":0.73,
                  "weights":{"foot_traffic":0.30,"disposable_income":0.12,"traveler_flow":0.14,"trade_flow":0.18,"event_activity":0.14,"security":0.12}, "regulation":0.03},
    "cloth_shop": {"name":"Cloth Shop", "sector":"retail", "enterprise_kind":"shop", "base_revenue":28, "cost_ratio":0.67,
                   "weights":{"foot_traffic":0.20,"disposable_income":0.20,"trade_flow":0.22,"cultural_activity":0.12,"elite_patronage":0.12,"reputation_climate":0.14}, "regulation":0.02},
    "bookshop": {"name":"Book / Manuscript Shop", "sector":"retail", "enterprise_kind":"shop", "base_revenue":24, "cost_ratio":0.61,
                 "weights":{"cultural_activity":0.28,"elite_patronage":0.18,"disposable_income":0.14,"foot_traffic":0.10,"trade_flow":0.12,"reputation_climate":0.18}, "regulation":0.05},
    "medicine_shop": {"name":"Medicine Shop", "sector":"retail", "enterprise_kind":"shop", "base_revenue":29, "cost_ratio":0.66,
                      "weights":{"health_demand":0.42,"foot_traffic":0.16,"trade_flow":0.16,"disposable_income":0.10,"reputation_climate":0.16}, "regulation":0.08},
    "luxury_goods": {"name":"Luxury Goods Shop", "sector":"retail", "enterprise_kind":"shop", "base_revenue":38, "cost_ratio":0.64,
                     "weights":{"elite_patronage":0.34,"disposable_income":0.26,"cultural_activity":0.12,"trade_flow":0.10,"reputation_climate":0.18}, "regulation":0.03},
    # Professional services
    "physician_practice": {"name":"Physician Practice", "sector":"professional", "enterprise_kind":"service", "base_revenue":31, "cost_ratio":0.48,
                           "weights":{"health_demand":0.46,"disposable_income":0.14,"foot_traffic":0.08,"elite_patronage":0.10,"reputation_climate":0.22}, "regulation":0.07, "skill_sensitive":True},
    "vein_mender_practice": {"name":"Vein-Mender Practice", "sector":"professional", "enterprise_kind":"service", "base_revenue":43, "cost_ratio":0.52,
                            "weights":{"health_demand":0.30,"military_demand":0.18,"elite_patronage":0.20,"trade_flow":0.08,"reputation_climate":0.24}, "regulation":0.08, "skill_sensitive":True},
    "appraiser": {"name":"Appraiser / Authenticator", "sector":"professional", "enterprise_kind":"service", "base_revenue":28, "cost_ratio":0.43,
                  "weights":{"elite_patronage":0.26,"cultural_activity":0.22,"trade_flow":0.18,"reputation_climate":0.28,"security":0.06}, "regulation":0.03, "skill_sensitive":True},
    "architectural_practice": {"name":"Architectural Practice", "sector":"professional", "enterprise_kind":"service", "base_revenue":34, "cost_ratio":0.51,
                               "weights":{"construction_demand":0.38,"elite_patronage":0.24,"disposable_income":0.10,"cultural_activity":0.10,"reputation_climate":0.18}, "regulation":0.03, "skill_sensitive":True},
    # Trade / logistics
    "warehouse": {"name":"Warehouse", "sector":"trade", "enterprise_kind":"other", "base_revenue":26, "cost_ratio":0.56,
                  "weights":{"trade_flow":0.46,"traveler_flow":0.08,"security":0.20,"event_activity":0.08,"credit_demand":0.08,"foot_traffic":0.10}, "regulation":0.04},
    "wholesaler": {"name":"Wholesaler", "sector":"trade", "enterprise_kind":"other", "base_revenue":34, "cost_ratio":0.70,
                   "weights":{"trade_flow":0.48,"credit_demand":0.12,"security":0.14,"disposable_income":0.08,"traveler_flow":0.08,"reputation_climate":0.10}, "regulation":0.04},
    "caravan_firm": {"name":"Caravan Firm", "sector":"logistics", "enterprise_kind":"shipping", "base_revenue":35, "cost_ratio":0.72,
                     "weights":{"trade_flow":0.38,"traveler_flow":0.16,"security":0.22,"credit_demand":0.08,"event_activity":0.06,"reputation_climate":0.10}, "regulation":0.03},
    "shipping_house": {"name":"Shipping House", "sector":"logistics", "enterprise_kind":"shipping", "base_revenue":41, "cost_ratio":0.76,
                       "weights":{"trade_flow":0.44,"security":0.20,"credit_demand":0.08,"elite_patronage":0.06,"event_activity":0.08,"reputation_climate":0.14}, "regulation":0.06},
    "courier": {"name":"Courier Service", "sector":"logistics", "enterprise_kind":"service", "base_revenue":25, "cost_ratio":0.61,
                "weights":{"trade_flow":0.26,"traveler_flow":0.18,"security":0.20,"credit_demand":0.06,"event_activity":0.12,"reputation_climate":0.18}, "regulation":0.02},
    "cartage_firm": {"name":"Cartage Firm", "sector":"logistics", "enterprise_kind":"service", "base_revenue":28, "cost_ratio":0.70,
                     "weights":{"trade_flow":0.34,"traveler_flow":0.14,"construction_demand":0.16,"security":0.18,"event_activity":0.08,"reputation_climate":0.10}, "regulation":0.02},
    # Security
    "escort_office": {"name":"Escort Office", "sector":"security", "enterprise_kind":"service", "base_revenue":36, "cost_ratio":0.68,
                      "weights":{"trade_flow":0.28,"traveler_flow":0.16,"military_demand":0.20,"security_inverse":0.20,"reputation_climate":0.16}, "regulation":0.05, "skill_sensitive":True},
    "bodyguard_firm": {"name":"Bodyguard Firm", "sector":"security", "enterprise_kind":"service", "base_revenue":37, "cost_ratio":0.67,
                       "weights":{"elite_patronage":0.28,"military_demand":0.16,"security_inverse":0.22,"disposable_income":0.10,"reputation_climate":0.24}, "regulation":0.05, "skill_sensitive":True},
    # Culture / market institutions
    "auction_house": {"name":"Auction House", "sector":"culture_trade", "enterprise_kind":"service", "base_revenue":35, "cost_ratio":0.48,
                      "weights":{"elite_patronage":0.30,"cultural_activity":0.24,"trade_flow":0.16,"disposable_income":0.10,"reputation_climate":0.20}, "regulation":0.05},
}

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


def seed_business_archetypes(conn: sqlite3.Connection) -> int:
    count = 0
    for key, spec in _ARCHETYPES.items():
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
         json.dumps(ctx, sort_keys=True), f"Resolved as {row['archetype_key']}; credit income {credit_income:.2f}; unfunded operating deficit {unfunded_deficit:.2f} capitalized as generic liabilities."),
    )
    return {
        "cycle_id": int(cur.lastrowid), "enterprise_id": enterprise_id, "enterprise": row["enterprise_name"],
        "archetype": row["archetype_key"], "sector": row["sector"], "day": day, "elapsed_days": elapsed,
        "context_demand": round(context_demand, 3), "demand_index": round(demand_index, 3),
        "utilization": round(utilization, 3), "gross_revenue": round(gross, 4),
        "operating_cost": round(operating_cost, 4), "net_income": round(net, 4), "status": status,
    }


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
