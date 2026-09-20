from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.db import connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.simulation import advance_connection, current_day
from engine.health import add_condition
from engine.law import file_case, add_case_evidence
from engine.war import (
    create_campaign_operation,
    add_campaign_force,
    configure_force_supply,
    link_operation_engagement,
    attach_force_to_battle_side,
    process_due_war,
)
from engine.combat import create_battle, add_battle_side, add_battle_unit, resolve_battle_round
from diagnostics.oneyear01_integrated_run import hard_invariants

OUT = Path(os.environ.get("CAERNESS_ONEYEAR_OUT", "/mnt/data/oneyear01_output_v2"))
SOURCE = OUT / "ONEYEAR01_diagnostic.db"
REPORT = OUT / "ONEYEAR01_conditional_trigger_audit.json"


def _copy(name: str) -> Path:
    dst = OUT / f"ONEYEAR01_trigger_{name}.db"
    if dst.exists():
        dst.unlink()
    shutil.copy2(SOURCE, dst)
    return dst


def _open(path: Path):
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_TEST_MODE"] = "1"
    return connect()


def health_trigger() -> dict[str, Any]:
    path = _copy("health")
    c = _open(path)
    start = current_day(c)
    # A real opening-world merchant principal in Saltmere, where structural ordinary care exists.
    actor = c.execute("SELECT id,name FROM actors WHERE name='Amory Selwick' AND status='active'").fetchone()
    if not actor:
        raise AssertionError("Amory Selwick unavailable for health trigger")
    aid = int(actor["id"])
    site = c.execute("SELECT id,name FROM health_care_sites WHERE location_id=38 AND status IN ('active','strained') ORDER BY id LIMIT 1").fetchone()
    if not site:
        raise AssertionError("Saltmere opening structural care site missing")
    cid = add_condition(
        c, aid, "injury", "[ONEYEAR-TRIGGER] serious warehouse fall",
        severity=68, body_system="limb", capacity_impact=38, pain_impact=50,
        recovery_rate_per_30=3, progression_rate_per_30=8,
        next_review_days=1,
        metadata={"manufactured_acceptance_trigger": True, "source": "ONEYEAR-01 conditional-domain audit"},
    )
    c.commit()
    # The production scheduler, not a direct health call, must discover demand and treatment.
    advance_connection(c, 7)
    c.commit()
    req = c.execute("SELECT * FROM health_care_requests WHERE actor_id=? AND condition_id=? ORDER BY id DESC LIMIT 1", (aid, cid)).fetchone()
    treatment = c.execute("SELECT * FROM medical_treatments WHERE actor_id=? AND condition_id=? ORDER BY id DESC LIMIT 1", (aid, cid)).fetchone()
    cond = c.execute("SELECT * FROM health_conditions WHERE id=?", (cid,)).fetchone()
    inv = hard_invariants(c)
    result = {
        "pass": bool(req and req["status"] == "treated" and treatment and int(req["site_id"]) == int(site["id"]) and inv["pass"]),
        "start_day": start,
        "end_day": current_day(c),
        "actor_id": aid,
        "actor_name": actor["name"],
        "condition_id": cid,
        "condition_status": cond["status"],
        "condition_severity": float(cond["severity"]),
        "care_site_id": int(site["id"]),
        "care_site_name": site["name"],
        "request_status": req["status"] if req else None,
        "treated_day": int(req["treated_day"]) if req and req["treated_day"] is not None else None,
        "provider_actor_id": int(req["assigned_provider_actor_id"]) if req and req["assigned_provider_actor_id"] is not None else None,
        "structural_provider_pool": bool(treatment and json.loads(treatment["metadata_json"] or "{}").get("structural_provider_pool")),
        "invariants": inv,
    }
    c.close()
    if not result["pass"]:
        raise AssertionError(("health trigger failed", result))
    return result


def law_trigger() -> dict[str, Any]:
    path = _copy("law")
    c = _open(path)
    start = current_day(c)
    buyer = c.execute("SELECT id,name,cash FROM civilian_enterprises WHERE name LIKE 'House Selwick — aggregate commercial arm' AND status='active'").fetchone()
    seller = c.execute("SELECT id,name,cash FROM civilian_enterprises WHERE name LIKE 'House Morrick — aggregate commercial arm' AND status='active'").fetchone()
    if not buyer or not seller:
        raise AssertionError("real Saltmere merchant houses unavailable for law trigger")
    before_buyer = float(buyer["cash"]); before_seller = float(seller["cash"])
    case_id = file_case(
        c, location_id=38, matter_kind="contract",
        claim_text="[ONEYEAR-TRIGGER] Paid delivery was materially short.",
        claimant_enterprise_id=int(buyer["id"]), respondent_enterprise_id=int(seller["id"]),
        subject_kind="conditional_trigger", subject_id=1, amount_claimed=2.0,
        metadata={"manufactured_acceptance_trigger": True, "source": "ONEYEAR-01 conditional-domain audit"},
    )
    add_case_evidence(
        c, case_id, "warehouse_record", "[ONEYEAR-TRIGGER] signed receipt and short-delivery tally",
        strength=100, source_kind="manufactured_acceptance_record", source_id=1,
        metadata={"manufactured_acceptance_trigger": True},
    )
    c.commit()
    # Procedure must advance through the production scheduler over real court delays.
    advance_connection(c, 90)
    c.commit()
    case = c.execute("SELECT * FROM law_cases WHERE id=?", (case_id,)).fetchone()
    judgment = c.execute("SELECT * FROM law_judgments WHERE case_id=? ORDER BY id DESC LIMIT 1", (case_id,)).fetchone()
    after_buyer = float(c.execute("SELECT cash FROM civilian_enterprises WHERE id=?", (int(buyer["id"]),)).fetchone()[0])
    after_seller = float(c.execute("SELECT cash FROM civilian_enterprises WHERE id=?", (int(seller["id"]),)).fetchone()[0])
    steps = int(c.execute("SELECT COUNT(*) FROM law_enforcement_steps WHERE case_id=?", (case_id,)).fetchone()[0])
    inv = hard_invariants(c)
    result = {
        "pass": bool(case and case["status"] == "closed" and judgment and judgment["status"] in {"enforced", "partially_enforced"} and float(judgment["amount_enforced"] or 0) > 0 and steps > 0 and inv["pass"]),
        "start_day": start,
        "end_day": current_day(c),
        "case_id": case_id,
        "case_status": case["status"] if case else None,
        "jurisdiction_id": int(case["jurisdiction_id"]) if case else None,
        "office_id": int(case["office_id"]) if case and case["office_id"] is not None else None,
        "judgment_status": judgment["status"] if judgment else None,
        "finding": judgment["finding"] if judgment else None,
        "amount_awarded": float(judgment["amount_awarded"] or 0) if judgment else None,
        "amount_enforced": float(judgment["amount_enforced"] or 0) if judgment else None,
        "enforcement_steps": steps,
        "buyer_cash_before": before_buyer,
        "buyer_cash_after": after_buyer,
        "seller_cash_before": before_seller,
        "seller_cash_after": after_seller,
        "invariants": inv,
    }
    c.close()
    if not result["pass"]:
        raise AssertionError(("law trigger failed", result))
    return result


def war_trigger() -> dict[str, Any]:
    path = _copy("war")
    c = _open(path)
    start = current_day(c)
    attacker_polity = 3  # Windmere
    defender_polity = 1  # Underheaven Empire
    commander = int(c.execute("SELECT ruler_actor_id FROM political_polities WHERE id=?", (attacker_polity,)).fetchone()[0])
    defender_ruler = int(c.execute("SELECT ruler_actor_id FROM political_polities WHERE id=?", (defender_polity,)).fetchone()[0])
    origin = 38   # Saltmere
    target = 15   # Toll's Reach; actual route 9 connects them and Underheaven controls it.
    route = c.execute("SELECT id FROM travel_routes WHERE ((from_location_id=? AND to_location_id=?) OR (from_location_id=? AND to_location_id=?)) AND status='open' ORDER BY id LIMIT 1", (origin,target,target,origin)).fetchone()
    if not route:
        raise AssertionError("real Saltmere–Toll's Reach route unavailable")
    depot = 6  # House Dovell aggregate commercial arm, a real opening merchant house.
    grain = int(c.execute("SELECT id FROM market_goods WHERE good_key='ordinary-grain'").fetchone()[0])
    stock = c.execute("SELECT id,quantity FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?", (depot,origin,grain)).fetchone()
    if not stock or float(stock["quantity"]) < 4:
        raise AssertionError("real Windmere grain stock insufficient for manufactured campaign")
    stock_before = float(stock["quantity"])
    warehouse = c.execute("SELECT id,condition FROM buildings WHERE location_id=? ORDER BY id LIMIT 1", (target,)).fetchone()
    warehouse_before = float(warehouse["condition"]) if warehouse else None

    op = create_campaign_operation(
        c, "[ONEYEAR-TRIGGER] Windmere punitive march",
        objective_text="Test a real routed campaign and battle consequence projection.",
        origin_location_id=origin, target_location_id=target,
        attacker_polity_id=attacker_polity, defender_polity_id=defender_polity,
        commander_actor_id=commander, objective_kind="limited",
        metadata={"manufactured_acceptance_trigger": True, "source": "ONEYEAR-01 conditional-domain audit"},
    )
    af = add_campaign_force(c, op, "[ONEYEAR-TRIGGER] Windmere field force", personnel=360, polity_id=attacker_polity, current_location_id=origin)
    df = add_campaign_force(c, op, "[ONEYEAR-TRIGGER] Toll reserve", personnel=240, polity_id=defender_polity, current_location_id=target)
    configure_force_supply(c, af, grain, supply_kind="food", source_enterprise_id=depot, source_location_id=origin,
                           weekly_need=1.2, max_on_hand=4.0, initial_on_hand=4.0)
    c.commit()
    # The production scheduler must move the force over the actual route and consume/resupply physical stock.
    advance_connection(c, 7)
    c.commit()
    afrow = c.execute("SELECT * FROM war_campaign_forces WHERE id=?", (af,)).fetchone()
    if int(afrow["current_location_id"]) != target or afrow["status"] not in {"deployed", "engaged"}:
        raise AssertionError(("manufactured campaign did not arrive", dict(afrow)))
    stock_after_march = float(c.execute("SELECT quantity FROM commercial_stock WHERE id=?", (int(stock["id"]),)).fetchone()[0])

    battle = create_battle(c, "[ONEYEAR-TRIGGER] Toll's Reach engagement", location_id=target,
                           objective="test conditional war activation", stakes=4,
                           metadata={"manufactured_acceptance_trigger": True})
    aside = add_battle_side(c, battle, "Windmere", controller_actor_id=commander,
                            morale=84, cohesion=82, logistics=76, information_quality=70, reserve_capacity=70,
                            metadata={"polity_id": attacker_polity})
    dside = add_battle_side(c, battle, "Underheaven", controller_actor_id=defender_ruler,
                            morale=40, cohesion=38, logistics=58, information_quality=55, reserve_capacity=40,
                            metadata={"polity_id": defender_polity})
    add_battle_unit(c, aside, "Windmere main", combat_capacity=84, morale=84, cohesion=82, readiness=82)
    add_battle_unit(c, dside, "Toll reserve", combat_capacity=45, morale=42, cohesion=40, readiness=52)
    link_operation_engagement(c, op, battle)
    attach_force_to_battle_side(c, af, aside)
    attach_force_to_battle_side(c, df, dside)
    process_due_war(c, current_day(c))
    c.commit()
    for _ in range(12):
        eng = c.execute("SELECT * FROM combat_engagements WHERE id=?", (battle,)).fetchone()
        if eng["status"] == "resolved":
            break
        resolve_battle_round(c, battle)
    eng = c.execute("SELECT * FROM combat_engagements WHERE id=?", (battle,)).fetchone()
    if eng["status"] != "resolved":
        raise AssertionError(("manufactured battle did not resolve", dict(eng)))
    # WAR process projects the resolved engagement into persistent world owners.
    process_due_war(c, int(eng["day_ended"] or current_day(c)))
    c.commit()
    aftermath = c.execute("SELECT * FROM war_battle_aftermath WHERE engagement_id=?", (battle,)).fetchone()
    afr = c.execute("SELECT * FROM war_campaign_forces WHERE id=?", (af,)).fetchone()
    dfr = c.execute("SELECT * FROM war_campaign_forces WHERE id=?", (df,)).fetchone()
    reports = int(c.execute("SELECT COUNT(*) FROM war_battle_reports WHERE engagement_id=?", (battle,)).fetchone()[0])
    damage = int(c.execute("SELECT COUNT(*) FROM war_damage_events WHERE engagement_id=?", (battle,)).fetchone()[0])
    warehouse_after = float(c.execute("SELECT condition FROM buildings WHERE id=?", (int(warehouse["id"]),)).fetchone()[0]) if warehouse else None
    inv = hard_invariants(c)
    aggregate_losses = (int(afr["aggregate_killed"]) + int(afr["aggregate_wounded"]) + int(dfr["aggregate_killed"]) + int(dfr["aggregate_wounded"]))
    result = {
        "pass": bool(aftermath and aggregate_losses > 0 and reports >= 2 and damage > 0 and stock_after_march < stock_before and inv["pass"]),
        "start_day": start,
        "battle_day": int(eng["day_ended"] or current_day(c)),
        "operation_id": op,
        "battle_id": battle,
        "attacker_force_location_after_march": int(afrow["current_location_id"]),
        "attacker_force_status_after_march": afrow["status"],
        "grain_stock_before": stock_before,
        "grain_stock_after_march": stock_after_march,
        "attacker_killed": int(afr["aggregate_killed"]),
        "attacker_wounded": int(afr["aggregate_wounded"]),
        "defender_killed": int(dfr["aggregate_killed"]),
        "defender_wounded": int(dfr["aggregate_wounded"]),
        "battle_reports": reports,
        "damage_events": damage,
        "warehouse_condition_before": warehouse_before,
        "warehouse_condition_after": warehouse_after,
        "invariants": inv,
    }
    c.close()
    if not result["pass"]:
        raise AssertionError(("war trigger failed", result))
    return result


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    out = {
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "source_database": str(SOURCE),
        "source_day": 365,
        "method": "three independent branches copied from the accepted peaceful day-365 diagnostic save; each branch receives one explicit causal trigger and then runs the real production owners",
    }
    out["health"] = health_trigger()
    out["law"] = law_trigger()
    out["war"] = war_trigger()
    out["pass"] = all(out[k]["pass"] for k in ("health", "law", "war"))
    REPORT.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    if not out["pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
