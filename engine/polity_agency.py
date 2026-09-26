from __future__ import annotations

import json
import sqlite3
from typing import Any

from .organization_agency import ensure_agency_profile, start_regime, set_capability, set_strategy_position


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _polity_by_name(conn: sqlite3.Connection, name: str):
    return conn.execute("""SELECT p.*,a.name institution_name FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id
                           WHERE a.name=? AND p.status!='dissolved'""", (name,)).fetchone()


def _ensure_sim_profile(conn: sqlite3.Connection, actor_id: int, cadence: int = 30) -> None:
    day = _day(conn)
    row = conn.execute("SELECT tier,cadence_days,next_review_day FROM simulation_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    if row:
        conn.execute("""UPDATE simulation_profiles SET tier='STRATEGIC',cadence_days=MIN(cadence_days,?),next_review_day=MIN(next_review_day,?)
                        WHERE actor_id=?""", (cadence, day+cadence, actor_id))
    else:
        conn.execute("""INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold)
                        VALUES (?,'STRATEGIC',?,.25,.65,?,?,3)""", (actor_id,cadence,day,day+cadence))


def _ensure_structural_government_actor(conn: sqlite3.Connection, polity: sqlite3.Row) -> int:
    pid = int(polity["id"]); iid = int(polity["institution_actor_id"])
    existing = conn.execute("SELECT decision_actor_id FROM polity_government_actors WHERE polity_id=?", (pid,)).fetchone()
    if existing:
        return int(existing[0])
    if polity["ruler_actor_id"] is not None:
        aid = int(polity["ruler_actor_id"])
        conn.execute("INSERT INTO polity_government_actors(polity_id,decision_actor_id,authority_kind,metadata_json) VALUES (?,?,?,?)",
                     (pid,aid,"ruler",json.dumps({"basis":"political_polities.ruler_actor_id"},sort_keys=True)))
        _ensure_sim_profile(conn, aid)
        return aid
    parent = conn.execute("SELECT name,home_location_id,current_location_id FROM actors WHERE id=?", (iid,)).fetchone()
    base = f"[STRUCTURAL] {parent['name']} government"
    name = base
    n = 2
    while conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
        name = f"{base} {n}"; n += 1
    cur = conn.execute("""INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo)
                          VALUES (?,'institution','government_decision_body',?,?,'active',?,0)""",
                       (name,parent["home_location_id"],parent["current_location_id"],
                        "Structural decision authority for a polity whose named sovereign/executive remains unresolved; not a newly canonized named office."))
    aid = int(cur.lastrowid)
    conn.execute("""INSERT INTO institution_profiles(actor_id,institution_kind,parent_institution_actor_id,primary_location_id,governance_json,culture_json,capacity_json,trajectory,last_review_day,notes)
                    VALUES (?,'government_decision_body',?,?,?,'{}','{}','stable',?,?)""",
                 (aid,iid,parent["current_location_id"],json.dumps({"delegated_from_polity_id":pid},sort_keys=True),_day(conn),
                  "Structural organ; political_polities remains the state authority."))
    conn.execute("INSERT INTO polity_government_actors(polity_id,decision_actor_id,authority_kind,metadata_json) VALUES (?,?,?,?)",
                 (pid,aid,"collective_government",json.dumps({"structural":True,"not_named_canon_office":True},sort_keys=True)))
    _ensure_sim_profile(conn, aid)
    return aid


def _relation(conn: sqlite3.Connection, a: int, b: int, kind: str, stance: float, trust: float, tension: float, notes: str) -> None:
    lo, hi = sorted((a,b))
    conn.execute("""INSERT INTO political_relations(polity_a_id,polity_b_id,relation_kind,stance,trust,tension,updated_day,notes)
                    VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(polity_a_id,polity_b_id) DO UPDATE SET
                    relation_kind=excluded.relation_kind,stance=excluded.stance,trust=excluded.trust,tension=excluded.tension,updated_day=excluded.updated_day,notes=excluded.notes""",
                 (lo,hi,kind,stance,trust,tension,_day(conn),notes))


def _issue(conn: sqlite3.Connection, a: int, b: int, key: str, kind: str, interest: float, pressure: float, restraint: float, posture: str, meta: dict[str,Any]) -> None:
    conn.execute("""INSERT INTO polity_issue_states(polity_id,other_polity_id,issue_key,issue_kind,interest,pressure,restraint,preferred_posture,updated_day,metadata_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(polity_id,other_polity_id,issue_key) DO UPDATE SET
                    issue_kind=excluded.issue_kind,interest=excluded.interest,pressure=excluded.pressure,restraint=excluded.restraint,
                    preferred_posture=excluded.preferred_posture,updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
                 (a,b,key,kind,interest,pressure,restraint,posture,_day(conn),json.dumps(meta,sort_keys=True)))


def ensure_polity_government_actor(conn: sqlite3.Connection, polity_id: int) -> int:
    """Ensure one active polity has a decision authority without re-seeding diplomatic opening state."""
    p = conn.execute("SELECT * FROM political_polities WHERE id=? AND status!='dissolved'", (polity_id,)).fetchone()
    if not p:
        raise ValueError("Unknown or dissolved polity")
    pid=int(p["id"]); iid=int(p["institution_actor_id"])
    decision_actor=_ensure_structural_government_actor(conn,p)
    ensure_agency_profile(conn,iid,governance_mode="state",
                          inheritance={"polity_kind":str(p["polity_kind"]),"succession_method":str(p["succession_method"])},
                          metadata={"polity_id":pid,"country_persists_across_regimes":True})
    start_regime(conn,iid,leader_actor_id=decision_actor,regime_kind="government",
                 metadata={"polity_id":pid,"decision_actor_id":decision_actor})
    set_capability(conn,iid,"administration","politics",float(p["administrative_capacity"]),basis={"political_polity_id":pid})
    set_capability(conn,iid,"military_command","politics",float(p["military_capacity"]),basis={"political_polity_id":pid})
    ml=conn.execute("SELECT readiness,transport_capacity,food_fodder_capacity FROM military_logistics_profiles WHERE polity_id=?",(pid,)).fetchone()
    if ml:
        readiness=(float(ml["readiness"])+float(ml["transport_capacity"])+float(ml["food_fodder_capacity"]))/3.0
        set_capability(conn,iid,"campaign_logistics","war",readiness,basis={"military_logistics_profile":True})
    # If decision authority is itself a structural institution (rather than a character ruler),
    # it participates in ORGLIFE as an organ of the country without becoming the country.
    arow=conn.execute("SELECT actor_type FROM actors WHERE id=?",(decision_actor,)).fetchone()
    if arow and str(arow[0])=='institution':
        try:
            from .organization_lifecycle import ensure_lifecycle_profile
            ensure_lifecycle_profile(conn,decision_actor,lifecycle_kind='government_decision_body',
                                     parent_institution_actor_id=iid,metadata={'polity_id':pid,'government_organ':True})
        except (sqlite3.OperationalError, ImportError):
            pass
    return decision_actor


# Opening diplomatic geometry. These are relationship-specific; no global aggression trait is inferred.
OPENING_GEOMETRY = [
    ("Greywood","Dunmoor","rival",-30,-15,58,"westbrook_stoneford","territorial",78,55,42,"hardline"),
    ("Dunmoor","Underheaven Empire","neutral",-5,0,28,"great_power_caution","security",62,22,72,"cautious"),
    ("Greywood","Windmere","friendly",45,38,12,"church_trade","trade",64,8,75,"cooperative"),
    ("Windmere","Sunreach Confederacy","rival",-10,5,42,"maritime_competition","maritime",72,42,50,"competitive"),
    ("Sunreach Confederacy","Underheaven Empire","neutral",-12,-5,38,"maritime_trade_wariness","trade",67,35,57,"cautious"),
    ("Underheaven Empire","Thornward","rival",-25,-20,62,"armed_corridor","frontier",80,62,38,"hardline"),
    # "Thornward–Stormhollow: Broken southern ridges. Tense local peace. Raids, forts, cattle, disputed valleys."
    ("Stormhollow","Thornward","rival",-20,-15,50,"southern_ridges","security",68,50,42,"hardline"),
    ]


def ensure_missing_opening_geometry(conn: sqlite3.Connection) -> int:
    """Add opening relations/issues that do not exist yet, without resetting any that a run has already moved."""
    polities = {str(r[1]): int(r[0]) for r in conn.execute(
        "SELECT p.id,a.name FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id WHERE p.status!='dissolved'")}
    added = 0
    for an, bn, rkind, stance, trust, tension, key, ikind, interest, pressure, restraint, posture in OPENING_GEOMETRY:
        if an not in polities or bn not in polities:
            continue
        a, b = polities[an], polities[bn]
        if conn.execute("SELECT 1 FROM polity_issue_states WHERE polity_id=? AND other_polity_id=? AND issue_key=?", (a, b, key)).fetchone():
            continue
        lo, hi = sorted((a, b))
        if not conn.execute("SELECT 1 FROM political_relations WHERE polity_a_id=? AND polity_b_id=?", (lo, hi)).fetchone():
            _relation(conn, a, b, rkind, stance, trust, tension, f"Opening relationship geometry: {key}; relationship-specific state, not national personality.")
        _issue(conn, a, b, key, ikind, interest, pressure, restraint, posture, {"opening_geometry": True})
        reverse_posture = "cautious" if posture in {"hardline", "hostile"} else posture
        _issue(conn, b, a, key, ikind, interest, max(0, pressure-5), min(100, restraint+5), reverse_posture, {"opening_geometry": True, "reverse_view": True})
        added += 1
    return added


def activate_polity_agency(conn: sqlite3.Connection) -> dict[str,int]:
    polities = {str(r["institution_name"]):r for r in conn.execute("""SELECT p.*,a.name institution_name FROM political_polities p
                  JOIN actors a ON a.id=p.institution_actor_id WHERE p.status!='dissolved'""").fetchall()}
    government_actors = 0
    for p in polities.values():
        pid=int(p["id"]); iid=int(p["institution_actor_id"])
        had=conn.execute("SELECT 1 FROM polity_government_actors WHERE polity_id=?",(pid,)).fetchone()
        decision_actor=ensure_polity_government_actor(conn,pid)
        if not had: government_actors += 1
    specs=OPENING_GEOMETRY
    relation_count=0; issue_count=0
    for an,bn,rkind,stance,trust,tension,key,ikind,interest,pressure,restraint,posture in specs:
        if an not in polities or bn not in polities: continue
        a=int(polities[an]["id"]); b=int(polities[bn]["id"])
        _relation(conn,a,b,rkind,stance,trust,tension,f"Opening relationship geometry: {key}; relationship-specific state, not national personality.")
        relation_count += 1
        _issue(conn,a,b,key,ikind,interest,pressure,restraint,posture,{"opening_geometry":True})
        # Reverse side shares the issue but can hold a different posture in later simulation.
        reverse_posture = "cautious" if posture in {"hardline","hostile"} else posture
        _issue(conn,b,a,key,ikind,interest,max(0,pressure-5),min(100,restraint+5),reverse_posture,{"opening_geometry":True,"reverse_view":True})
        issue_count += 2
        set_strategy_position(conn,int(polities[an]["institution_actor_id"]),f"polity:{b}:{key}","politics",{"posture":posture,"pressure":pressure},target_kind="polity",target_id=b,confidence=.8)
        set_strategy_position(conn,int(polities[bn]["institution_actor_id"]),f"polity:{a}:{key}","politics",{"posture":reverse_posture,"pressure":max(0,pressure-5)},target_kind="polity",target_id=a,confidence=.8)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('polity_agency_activation_version','1')")
    return {"polity_government_actors_configured":government_actors,"opening_political_relations_configured":relation_count,"polity_issue_states_configured":issue_count}
