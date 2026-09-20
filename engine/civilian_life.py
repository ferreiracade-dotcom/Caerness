from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def create_building(conn: sqlite3.Connection, name: str, building_kind: str, *, location_id: int | None = None,
                    owner_actor_id: int | None = None, household_id: int | None = None,
                    institution_actor_id: int | None = None, project_id: int | None = None,
                    style_key: str | None = None, capacity: float = 50, condition: float = 100,
                    prestige: float = 50, utility: float = 50, maintenance_burden: float = 10,
                    completed_day: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn) if completed_day is None else int(completed_day)
    cur = conn.execute(
        """INSERT INTO buildings(name,building_kind,location_id,owner_actor_id,household_id,institution_actor_id,project_id,
                                  style_key,capacity,condition,prestige,utility,maintenance_burden,completed_day,status,metadata_json,updated_day)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?,?)""",
        (name, building_kind, location_id, owner_actor_id, household_id, institution_actor_id, project_id,
         style_key, capacity, condition, prestige, utility, maintenance_burden, day,
         json.dumps(metadata or {}, sort_keys=True), day),
    )
    return int(cur.lastrowid)


def ensure_style_movement(conn: sqlite3.Connection, style_key: str, name: str, style_domain: str, *,
                          origin_location_id: int | None = None, origin_actor_id: int | None = None,
                          prestige: float = 50, novelty: float = 50, accessibility: float = 50,
                          durability: float = 50, status: str = "emerging",
                          metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    conn.execute(
        """INSERT OR IGNORE INTO style_movements(style_key,name,style_domain,origin_location_id,origin_actor_id,
                                                  prestige,novelty,accessibility,durability,status,created_day,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (style_key, name, style_domain, origin_location_id, origin_actor_id, prestige, novelty, accessibility,
         durability, status, day, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(conn.execute("SELECT id FROM style_movements WHERE style_key=?", (style_key,)).fetchone()[0])


def set_style_adoption(conn: sqlite3.Connection, style_id: int, location_id: int, *, adoption: float = 0,
                       elite_support: float = 0, craft_capacity: float = 50, resistance: float = 20,
                       metadata: dict[str, Any] | None = None) -> None:
    conn.execute(
        """INSERT INTO style_adoption(style_id,location_id,adoption,elite_support,craft_capacity,resistance,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(style_id,location_id) DO UPDATE SET adoption=excluded.adoption,elite_support=excluded.elite_support,
             craft_capacity=excluded.craft_capacity,resistance=excluded.resistance,last_review_day=excluded.last_review_day,
             metadata_json=excluded.metadata_json""",
        (style_id, location_id, adoption, elite_support, craft_capacity, resistance, _day(conn),
         json.dumps(metadata or {}, sort_keys=True)),
    )


def link_object_style(conn: sqlite3.Connection, object_id: int, style_id: int, *, strength: float = 100,
                      relation_kind: str = "made_in") -> None:
    conn.execute(
        "INSERT OR REPLACE INTO object_style_links(object_id,style_id,strength,relation_kind) VALUES (?,?,?,?)",
        (object_id, style_id, strength, relation_kind),
    )


def set_succession_plan(conn: sqlite3.Connection, household_id: int, *, designated_heir_actor_id: int | None = None,
                        succession_method: str = "designated", certainty: float = 50,
                        dispute_pressure: float = 0, notes: str | None = None) -> None:
    conn.execute(
        """INSERT INTO household_succession_plans(household_id,designated_heir_actor_id,succession_method,certainty,dispute_pressure,status,notes,updated_day)
           VALUES (?,?,?,?,?,'active',?,?)
           ON CONFLICT(household_id) DO UPDATE SET designated_heir_actor_id=excluded.designated_heir_actor_id,
             succession_method=excluded.succession_method,certainty=excluded.certainty,dispute_pressure=excluded.dispute_pressure,
             status='active',notes=excluded.notes,updated_day=excluded.updated_day""",
        (household_id, designated_heir_actor_id, succession_method, certainty, dispute_pressure, notes, _day(conn)),
    )


def set_inheritance_claim(conn: sqlite3.Connection, household_id: int, actor_id: int, *, priority: float = 50,
                          legitimacy: float = 50, support: float = 0, status: str = "potential",
                          notes: str | None = None) -> int:
    conn.execute(
        """INSERT INTO inheritance_claims(household_id,actor_id,priority,legitimacy,support,status,notes)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(household_id,actor_id) DO UPDATE SET priority=excluded.priority,legitimacy=excluded.legitimacy,
             support=excluded.support,status=excluded.status,notes=excluded.notes""",
        (household_id, actor_id, priority, legitimacy, support, status, notes),
    )
    return int(conn.execute("SELECT id FROM inheritance_claims WHERE household_id=? AND actor_id=?",
                            (household_id, actor_id)).fetchone()[0])


def resolve_household_succession(conn: sqlite3.Connection, household_id: int, *, new_head_actor_id: int | None = None,
                                 event_logger: Callable[..., int] | None = None) -> dict[str, Any]:
    h = conn.execute("SELECT * FROM households WHERE id=?", (household_id,)).fetchone()
    if not h:
        raise ValueError("Unknown household")
    former = h["head_actor_id"]
    plan = conn.execute("SELECT * FROM household_succession_plans WHERE household_id=?", (household_id,)).fetchone()
    resolution = "manual" if new_head_actor_id is not None else "vacant"
    disputed = 0
    if new_head_actor_id is None and plan and plan["designated_heir_actor_id"] is not None and float(plan["certainty"]) >= 50:
        new_head_actor_id = int(plan["designated_heir_actor_id"])
        resolution = "designated"
        disputed = 1 if float(plan["dispute_pressure"]) >= 60 else 0
    if new_head_actor_id is None:
        claims = conn.execute(
            """SELECT *, (priority*0.45 + legitimacy*0.35 + support*0.20) AS score
               FROM inheritance_claims WHERE household_id=? AND status IN ('potential','active')
               ORDER BY score DESC,id""", (household_id,)).fetchall()
        if claims:
            new_head_actor_id = int(claims[0]["actor_id"])
            resolution = "claim_strength"
            if len(claims) > 1 and float(claims[0]["score"]) - float(claims[1]["score"]) < 12:
                disputed = 1
    day = _day(conn)
    conn.execute("UPDATE households SET head_actor_id=?,status=?,updated_day=? WHERE id=?",
                 (new_head_actor_id, "active" if new_head_actor_id is not None else "declining", day, household_id))
    if former is not None:
        conn.execute("UPDATE household_members SET role='former_head',status='former',left_day=? WHERE household_id=? AND actor_id=?",
                     (day, household_id, former))
    if new_head_actor_id is not None:
        conn.execute(
            """INSERT INTO household_members(household_id,actor_id,role,authority,dependency,joined_day,status)
               VALUES (?,?,?,?,?,?, 'active')
               ON CONFLICT(household_id,actor_id) DO UPDATE SET role='head',authority=100,status='active',left_day=NULL""",
            (household_id, new_head_actor_id, "head", 100, 0, day),
        )
        # Personal cultural property of the former head passes to the successor as campaign history.
        objects = conn.execute("SELECT id FROM cultural_objects WHERE current_owner_actor_id=? AND status!='destroyed'", (former,)).fetchall() if former else []
        from .civilian import add_provenance
        for obj in objects:
            oid = int(obj[0])
            conn.execute("UPDATE cultural_objects SET current_owner_actor_id=? WHERE id=?", (new_head_actor_id, oid))
            add_provenance(conn, oid, "inherited", "Passed through household succession.",
                           from_actor_id=former, to_actor_id=new_head_actor_id, location_id=h["location_id"], day=day)
        conn.execute("UPDATE inheritance_claims SET status=CASE WHEN actor_id=? THEN 'satisfied' ELSE status END WHERE household_id=?",
                     (new_head_actor_id, household_id))
    summary = f"{h['name']} succession resolved" + (f" under {new_head_actor_id}" if new_head_actor_id else " without a settled head")
    conn.execute("INSERT INTO succession_events(household_id,day,former_head_actor_id,new_head_actor_id,resolution_kind,disputed,summary) VALUES (?,?,?,?,?,?,?)",
                 (household_id, day, former, new_head_actor_id, resolution, disputed, summary))
    if plan:
        conn.execute("UPDATE household_succession_plans SET status=?,updated_day=? WHERE household_id=?",
                     ("contested" if disputed else "resolved", day, household_id))
    if event_logger:
        event_logger(day=day, event_type="civilian:succession", title=f"Succession: {h['name']}", summary=summary,
                     severity=2 if disputed else 1, source_actor_id=former,
                     target_actor_ids=tuple([new_head_actor_id] if new_head_actor_id else []), location_id=h["location_id"])
    return {"household_id": household_id, "former_head_actor_id": former,
            "new_head_actor_id": new_head_actor_id, "resolution_kind": resolution, "disputed": bool(disputed)}


def create_credit_agreement(conn: sqlite3.Connection, *, principal: float,
                            lender_actor_id: int | None = None, lender_enterprise_id: int | None = None,
                            borrower_actor_id: int | None = None, borrower_enterprise_id: int | None = None,
                            interest_rate_per_30: float = 0, due_day: int | None = None,
                            collateral_object_id: int | None = None, risk: float = 20,
                            metadata: dict[str, Any] | None = None) -> int:
    if not (lender_actor_id or lender_enterprise_id) or not (borrower_actor_id or borrower_enterprise_id):
        raise ValueError("Credit needs a lender and a borrower")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO credit_agreements(lender_actor_id,lender_enterprise_id,borrower_actor_id,borrower_enterprise_id,
                                          principal,outstanding,interest_rate_per_30,opened_day,due_day,collateral_object_id,
                                          status,risk,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?, 'current', ?,?,?)""",
        (lender_actor_id, lender_enterprise_id, borrower_actor_id, borrower_enterprise_id, principal, principal,
         interest_rate_per_30, day, due_day, collateral_object_id, risk, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    if borrower_enterprise_id is not None:
        conn.execute("UPDATE civilian_enterprises SET cash=cash+?,debt=debt+?,updated_day=? WHERE id=?",
                     (principal, principal, day, borrower_enterprise_id))
    if lender_enterprise_id is not None:
        conn.execute("UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?", (principal, day, lender_enterprise_id))
    return int(cur.lastrowid)


def make_credit_payment(conn: sqlite3.Connection, agreement_id: int, amount: float) -> float:
    row = conn.execute("SELECT * FROM credit_agreements WHERE id=?", (agreement_id,)).fetchone()
    if not row:
        raise ValueError("Unknown credit agreement")
    if amount <= 0:
        raise ValueError("Payment must be positive")
    amount = min(float(row["outstanding"]), float(amount))
    outstanding = max(0.0, float(row["outstanding"]) - amount)
    status = "repaid" if outstanding <= 1e-9 else "current"
    day = _day(conn)
    conn.execute("UPDATE credit_agreements SET outstanding=?,status=?,last_review_day=? WHERE id=?",
                 (outstanding, status, day, agreement_id))
    if row["borrower_enterprise_id"] is not None:
        conn.execute("UPDATE civilian_enterprises SET cash=cash-?,debt=max(0,debt-?),updated_day=? WHERE id=?",
                     (amount, amount, day, row["borrower_enterprise_id"]))
    if row["lender_enterprise_id"] is not None:
        conn.execute("UPDATE civilian_enterprises SET cash=cash+?,updated_day=? WHERE id=?",
                     (amount, day, row["lender_enterprise_id"]))
    return outstanding


def set_enterprise_partner(conn: sqlite3.Connection, enterprise_id: int, actor_id: int, *, ownership_share: float = 0,
                           governance_weight: float = 0, capital_committed: float = 0,
                           role: str = "partner") -> None:
    conn.execute(
        """INSERT INTO enterprise_partners(enterprise_id,actor_id,ownership_share,governance_weight,capital_committed,role,joined_day,status)
           VALUES (?,?,?,?,?,?,?, 'active')
           ON CONFLICT(enterprise_id,actor_id) DO UPDATE SET ownership_share=excluded.ownership_share,
             governance_weight=excluded.governance_weight,capital_committed=excluded.capital_committed,role=excluded.role,
             status='active',left_day=NULL""",
        (enterprise_id, actor_id, ownership_share, governance_weight, capital_committed, role, _day(conn)),
    )


def create_professional_membership(conn: sqlite3.Connection, actor_id: int, institution_actor_id: int,
                                   profession_domain: str, *, role: str = "member", standing: float = 50,
                                   influence: float = 10, dues_per_30: float = 0,
                                   metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO professional_memberships(actor_id,institution_actor_id,profession_domain,role,standing,seniority_days,
                                                 influence,dues_per_30,eligibility_state,joined_day,last_review_day,status,metadata_json)
           VALUES (?,?,?,?,?,0,?,?,'ordinary',?,?, 'active',?)""",
        (actor_id, institution_actor_id, profession_domain, role, standing, influence, dues_per_30,
         day, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _resolve_buildings(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    for b in conn.execute("SELECT * FROM buildings WHERE status IN ('active','strained','derelict') AND updated_day<?", (day,)).fetchall():
        elapsed = day - int(b["updated_day"])
        burden = float(b["maintenance_burden"]) * elapsed / 30.0
        funded = False
        if b["household_id"] is not None:
            hh = conn.execute("SELECT liquidity FROM households WHERE id=?", (b["household_id"],)).fetchone()
            if hh and float(hh[0]) >= burden * 0.02:
                cost = burden * 0.02
                conn.execute("UPDATE households SET liquidity=liquidity-? WHERE id=?", (cost, b["household_id"]))
                funded = True
        elif b["owner_actor_id"] is not None or b["institution_actor_id"] is not None:
            funded = True  # abstracted non-household maintenance budget at this resolution.
        condition = float(b["condition"])
        if funded:
            condition = min(100.0, condition + 0.02 * elapsed)
        else:
            condition = max(0.0, condition - (0.08 + float(b["maintenance_burden"]) / 400.0) * elapsed)
        status = "active" if condition >= 55 else "strained" if condition >= 25 else "derelict"
        conn.execute("UPDATE buildings SET condition=?,status=?,updated_day=? WHERE id=?", (condition, status, day, b["id"]))
        count += 1
    return count


def _resolve_styles(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    for a in conn.execute("""SELECT sa.*,sm.prestige,sm.novelty,sm.accessibility,sm.durability,sm.status AS style_status
                             FROM style_adoption sa JOIN style_movements sm ON sm.id=sa.style_id
                             WHERE sa.last_review_day<?""", (day,)).fetchall():
        elapsed = day - int(a["last_review_day"])
        months = elapsed / 30.0
        pull = (float(a["prestige"]) * 0.35 + float(a["novelty"]) * 0.15 + float(a["accessibility"]) * 0.15 +
                float(a["elite_support"]) * 0.2 + float(a["craft_capacity"]) * 0.15) / 100.0
        resistance = float(a["resistance"]) / 100.0
        adoption = float(a["adoption"])
        growth = max(-2.0, (pull - resistance - adoption / 160.0) * 8.0) * months
        if a["style_status"] in ("declining", "historical"):
            growth -= (2.5 + (100.0 - float(a["durability"])) / 30.0) * months
        adoption = max(0.0, min(100.0, adoption + growth))
        conn.execute("UPDATE style_adoption SET adoption=?,last_review_day=? WHERE style_id=? AND location_id=?",
                     (adoption, day, a["style_id"], a["location_id"]))
        count += 1
    return count


def _resolve_credit(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    for c in conn.execute("SELECT * FROM credit_agreements WHERE status IN ('current','late') AND last_review_day<?", (day,)).fetchall():
        elapsed = day - int(c["last_review_day"])
        interest = float(c["outstanding"]) * float(c["interest_rate_per_30"]) * elapsed / 30.0
        outstanding = float(c["outstanding"]) + interest
        status = str(c["status"])
        if c["due_day"] is not None and day > int(c["due_day"]):
            lateness = day - int(c["due_day"])
            status = "defaulted" if lateness >= 90 or float(c["risk"]) >= 85 else "late"
        conn.execute("UPDATE credit_agreements SET outstanding=?,status=?,last_review_day=? WHERE id=?",
                     (outstanding, status, day, c["id"]))
        if c["borrower_enterprise_id"] is not None:
            conn.execute("UPDATE civilian_enterprises SET debt=debt+?,updated_day=? WHERE id=?",
                         (interest, day, c["borrower_enterprise_id"]))
            if status == "defaulted":
                conn.execute("UPDATE civilian_enterprises SET status='strained' WHERE id=? AND status='active'", (c["borrower_enterprise_id"],))
        count += 1
    return count


def _resolve_professional_memberships(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    for m in conn.execute("SELECT * FROM professional_memberships WHERE status='active' AND last_review_day<?", (day,)).fetchall():
        elapsed = day - int(m["last_review_day"])
        seniority = int(m["seniority_days"]) + elapsed
        standing = float(m["standing"])
        before_elig = str(m["eligibility_state"])
        elig = before_elig
        # Membership can make someone eligible for review, but never auto-promotes role/office.
        if seniority >= 365 and standing >= 65 and before_elig == "ordinary":
            elig = "eligible_for_review"
        conn.execute("UPDATE professional_memberships SET seniority_days=?,eligibility_state=?,last_review_day=? WHERE id=?",
                     (seniority, elig, day, m["id"]))
        if elig != before_elig:
            conn.execute("INSERT INTO professional_reviews(membership_id,day,standing_before,standing_after,eligibility_before,eligibility_after,reason) VALUES (?,?,?,?,?,?,?)",
                         (m["id"], day, standing, standing, before_elig, elig, "Seniority and standing reached review threshold; no office was granted automatically."))
        count += 1
    return count


def _resolve_succession_triggers(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None = None) -> int:
    count = 0
    rows = conn.execute("""SELECT h.id AS household_id,h.head_actor_id,a.status AS actor_status
                           FROM households h JOIN actors a ON a.id=h.head_actor_id
                           WHERE h.status IN ('active','declining') AND lower(a.status) IN ('dead','deceased')""").fetchall()
    for r in rows:
        already = conn.execute("SELECT 1 FROM succession_events WHERE household_id=? AND former_head_actor_id=?", (r["household_id"], r["head_actor_id"])).fetchone()
        if not already:
            resolve_household_succession(conn, int(r["household_id"]), event_logger=event_logger)
            count += 1
    return count


def process_due_civilian_life(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    return {
        "buildings": _resolve_buildings(conn, day),
        "styles": _resolve_styles(conn, day),
        "credit": _resolve_credit(conn, day),
        "professional_memberships": _resolve_professional_memberships(conn, day),
        "successions": _resolve_succession_triggers(conn, day, event_logger),
    }


def civilian_life_summary(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "buildings": int(conn.execute("SELECT COUNT(*) FROM buildings WHERE status!='destroyed'").fetchone()[0]),
        "styles": int(conn.execute("SELECT COUNT(*) FROM style_movements WHERE status!='historical'").fetchone()[0]),
        "style_adoptions": int(conn.execute("SELECT COUNT(*) FROM style_adoption").fetchone()[0]),
        "open_credit": int(conn.execute("SELECT COUNT(*) FROM credit_agreements WHERE status IN ('current','late','defaulted')").fetchone()[0]),
        "enterprise_partners": int(conn.execute("SELECT COUNT(*) FROM enterprise_partners WHERE status='active'").fetchone()[0]),
        "professional_memberships": int(conn.execute("SELECT COUNT(*) FROM professional_memberships WHERE status='active'").fetchone()[0]),
        "succession_plans": int(conn.execute("SELECT COUNT(*) FROM household_succession_plans WHERE status IN ('active','contested')").fetchone()[0]),
    }
