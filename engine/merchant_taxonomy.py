from __future__ import annotations

"""MERCHANT-HOUSE-TAXONOMY — social/institutional House status is not a profit label."""

import json
import sqlite3
from typing import Any


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(v: Any) -> str:
    return json.dumps(v if v is not None else {}, sort_keys=True, ensure_ascii=False)


def _institutional_house(conn: sqlite3.Connection, institution_actor_id: int | None) -> bool:
    if institution_actor_id is None:
        return False
    r = conn.execute("SELECT institution_kind FROM institution_profiles WHERE actor_id=?", (int(institution_actor_id),)).fetchone()
    if not r:
        return False
    k = str(r[0] or "").strip().lower()
    return k in {"merchant-noble house","merchant house","great merchant house","merchant dynasty"}


def review_enterprise_merchant_house(conn: sqlite3.Connection, enterprise_id: int, *, day: int | None = None) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    e = conn.execute("SELECT * FROM civilian_enterprises WHERE id=?", (enterprise_id,)).fetchone()
    if not e:
        raise ValueError("unknown enterprise")
    eco = conn.execute("SELECT * FROM enterprise_ecology_state WHERE enterprise_id=?", (enterprise_id,)).fetchone()
    founded = None
    if eco and eco["founded_day"] is not None:
        founded = int(eco["founded_day"])
    elif e["created_day"] is not None:
        founded = int(e["created_day"])
    age_days = max(0, day - founded) if founded is not None else 0
    staff = int(conn.execute("SELECT COUNT(*) FROM enterprise_staff WHERE enterprise_id=? AND status='active'", (enterprise_id,)).fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_staff'").fetchone() else 0
    contracts = int(conn.execute("SELECT COUNT(*) FROM merchant_trade_contracts WHERE (buyer_enterprise_id=? OR seller_enterprise_id=?) AND status IN ('fulfilled','settled','delivered')", (enterprise_id,enterprise_id)).fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchant_trade_contracts'").fetchone() else 0
    markets = int(conn.execute("SELECT COUNT(DISTINCT destination_location_id) FROM merchant_trade_contracts WHERE (buyer_enterprise_id=? OR seller_enterprise_id=?) AND destination_location_id IS NOT NULL", (enterprise_id,enterprise_id)).fetchone()[0]) if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchant_trade_contracts'").fetchone() else 0
    # Multiple ventures are measured by a shared pre-existing institution or a truly broad trade network.
    ventures = 0
    if e["institution_actor_id"] is not None:
        ventures = int(conn.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE institution_actor_id=? AND status IN ('active','strained','insolvent')", (int(e["institution_actor_id"]),)).fetchone()[0])
    elif e["household_id"] is not None:
        ventures = int(conn.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE household_id=? AND status IN ('active','strained','insolvent')", (int(e["household_id"]),)).fetchone()[0])
    durable = int(age_days >= 3*365 and (staff >= 2 or contracts >= 12 or ventures >= 2))
    dynastic = int(_institutional_house(conn, int(e["institution_actor_id"]) if e["institution_actor_id"] is not None else None))
    multi = int(ventures >= 2 or (contracts >= 12 and markets >= 3))
    # A canonically/pre-existing merchant House is already a social institution; its operating arm
    # need not re-earn that historical status from day-zero accounting counters. New ordinary firms
    # require all three forms of evidence and can never qualify on profit/cash alone.
    preexisting_house = bool(dynastic)
    recognized = int(preexisting_house or (durable and dynastic and multi))
    evidence = {
        "enterprise_kind_is_not_social_status": True,
        "profitability_alone_never_qualifies": True,
        "age_days": age_days, "active_staff": staff, "completed_trade_contracts": contracts,
        "distinct_trade_locations": markets, "controlled_ventures": ventures,
        "preexisting_institutional_house": preexisting_house,
    }
    conn.execute(
        """INSERT INTO merchant_house_qualifications(enterprise_id,institution_actor_id,durable_depth,dynastic_or_family_continuity,multi_venture_depth,recognized_house_status,reviewed_day,evidence_json)
           VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(enterprise_id) DO UPDATE SET
           institution_actor_id=excluded.institution_actor_id,durable_depth=excluded.durable_depth,
           dynastic_or_family_continuity=excluded.dynastic_or_family_continuity,multi_venture_depth=excluded.multi_venture_depth,
           recognized_house_status=excluded.recognized_house_status,reviewed_day=excluded.reviewed_day,evidence_json=excluded.evidence_json""",
        (enterprise_id,e["institution_actor_id"],durable,dynastic,multi,recognized,day,_j(evidence)),
    )
    return {"enterprise_id":enterprise_id,"durable_depth":durable,"dynastic_or_family_continuity":dynastic,"multi_venture_depth":multi,"recognized_house_status":recognized,"evidence":evidence}


def activate_merchant_taxonomy(conn: sqlite3.Connection) -> dict[str, int]:
    reviewed = recognized = 0
    for r in conn.execute("SELECT id FROM civilian_enterprises ORDER BY id").fetchall():
        out = review_enterprise_merchant_house(conn,int(r[0])); reviewed += 1; recognized += int(out["recognized_house_status"])
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('merchant_taxonomy_activation_version','1')")
    return {"merchant_enterprises_reviewed":reviewed,"recognized_merchant_house_enterprises":recognized}


def is_recognized_merchant_house(conn: sqlite3.Connection, enterprise_id: int) -> bool:
    r = conn.execute("SELECT recognized_house_status FROM merchant_house_qualifications WHERE enterprise_id=?", (enterprise_id,)).fetchone()
    if not r:
        return bool(review_enterprise_merchant_house(conn,enterprise_id)["recognized_house_status"])
    return bool(r[0])
