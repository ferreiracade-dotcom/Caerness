from __future__ import annotations

import json
import math
import sqlite3
from typing import Any


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _obj(raw: str | None) -> dict[str, Any]:
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(v)))


def _institution_exists(conn: sqlite3.Connection, institution_actor_id: int) -> bool:
    row = conn.execute("SELECT actor_type FROM actors WHERE id=?", (institution_actor_id,)).fetchone()
    return bool(row and str(row[0]) == "institution")


def _active_members(conn: sqlite3.Connection, institution_actor_id: int) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=? AND status='active'",
        (institution_actor_id,),
    ).fetchone()[0])


def _active_enterprises(conn: sqlite3.Connection, institution_actor_id: int) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) FROM civilian_enterprises WHERE institution_actor_id=? AND status IN ('active','strained','insolvent')",
        (institution_actor_id,),
    ).fetchone()[0])


def _capability_mean(conn: sqlite3.Connection, institution_actor_id: int) -> float | None:
    row = conn.execute(
        "SELECT AVG((capacity+readiness)/2.0) FROM organization_capabilities WHERE institution_actor_id=?",
        (institution_actor_id,),
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _numeric_capacity(raw: str | None) -> float | None:
    obj = _obj(raw)
    vals = [float(v) for v in obj.values() if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None


def record_lifecycle_event(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    event_type: str,
    summary: str,
    *,
    other_institution_actor_id: int | None = None,
    polity_id: int | None = None,
    other_polity_id: int | None = None,
    cause_kind: str | None = None,
    cause_id: int | None = None,
    detail: dict[str, Any] | None = None,
    day: int | None = None,
) -> int:
    if not _institution_exists(conn, institution_actor_id):
        raise ValueError("lifecycle event requires institution actor")
    day = _day(conn) if day is None else int(day)
    cur = conn.execute(
        """INSERT INTO organization_lifecycle_events(
               day,event_type,institution_actor_id,other_institution_actor_id,polity_id,other_polity_id,
               cause_kind,cause_id,summary,detail_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (day, event_type, institution_actor_id, other_institution_actor_id, polity_id, other_polity_id,
         cause_kind, cause_id, summary, _j(detail or {})),
    )
    return int(cur.lastrowid)


def ensure_lifecycle_profile(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    *,
    lifecycle_kind: str | None = None,
    parent_institution_actor_id: int | None = None,
    review_cadence_days: int = 90,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not _institution_exists(conn, institution_actor_id):
        raise ValueError("organization lifecycle requires institution actor")
    day = _day(conn)
    ip = conn.execute(
        "SELECT institution_kind,trajectory,capacity_json,parent_institution_actor_id FROM institution_profiles WHERE actor_id=?",
        (institution_actor_id,),
    ).fetchone()
    if lifecycle_kind is None:
        lifecycle_kind = str(ip["institution_kind"]) if ip else "institution"
    if parent_institution_actor_id is None and ip and ip["parent_institution_actor_id"] is not None:
        parent_institution_actor_id = int(ip["parent_institution_actor_id"])
    cap = _numeric_capacity(ip["capacity_json"] if ip else None)
    cap2 = _capability_mean(conn, institution_actor_id)
    base = max(35.0, cap2 if cap2 is not None else (cap if cap is not None else 50.0))
    members = _active_members(conn, institution_actor_id)
    enterprises = _active_enterprises(conn, institution_actor_id)
    vitality = _clamp(base * 0.72 + min(14.0, math.log1p(members) * 3.5) + min(10.0, enterprises * 2.0) + 8.0)
    cohesion = 55.0
    continuity = 55.0
    expansion = _clamp((base + vitality) / 2.0)
    conn.execute(
        """INSERT INTO organization_lifecycle_profiles(
               institution_actor_id,lifecycle_kind,lifecycle_status,vitality,cohesion,continuity,expansion_capacity,
               sovereignty_status,parent_institution_actor_id,last_review_day,next_review_day,review_cadence_days,metadata_json)
           VALUES (?,?, 'stable',?,?,?,?, 'nonstate',?,?,?, ?,?)
           ON CONFLICT(institution_actor_id) DO UPDATE SET
               lifecycle_kind=excluded.lifecycle_kind,
               parent_institution_actor_id=COALESCE(organization_lifecycle_profiles.parent_institution_actor_id,excluded.parent_institution_actor_id),
               review_cadence_days=excluded.review_cadence_days,
               metadata_json=json_patch(organization_lifecycle_profiles.metadata_json,excluded.metadata_json)""",
        (institution_actor_id, lifecycle_kind, vitality, cohesion, continuity, expansion,
         parent_institution_actor_id, day, day + review_cadence_days, review_cadence_days, _j(metadata or {})),
    )


def _polity_row_for_institution(conn: sqlite3.Connection, institution_actor_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM political_polities WHERE institution_actor_id=?", (institution_actor_id,)).fetchone()


def _polity_sovereignty_status(conn: sqlite3.Connection, polity: sqlite3.Row) -> str:
    pid = int(polity["id"])
    if str(polity["status"]) == "dissolved":
        return "dissolved"
    if str(polity["status"]) == "fragmenting":
        return "fragmenting"
    if conn.execute("SELECT 1 FROM political_links WHERE junior_polity_id=? AND status='active' LIMIT 1", (pid,)).fetchone():
        return "dependent"
    if str(polity["status"]) in {"succession_crisis", "regency"}:
        return "contested"
    return "sovereign"


def refresh_polity_lifecycle(conn: sqlite3.Connection, polity_id: int, *, schedule_next: bool = False) -> dict[str, float | str]:
    p = conn.execute("SELECT * FROM political_polities WHERE id=?", (polity_id,)).fetchone()
    if not p:
        raise ValueError("unknown polity")
    iid = int(p["institution_actor_id"])
    ensure_lifecycle_profile(conn, iid, lifecycle_kind="polity", metadata={"polity_id": polity_id})
    territories = conn.execute(
        "SELECT control_kind,legitimacy,integration FROM territorial_control WHERE controller_polity_id=? ORDER BY location_id",
        (polity_id,),
    ).fetchall()
    avg_integration = sum(float(r["integration"]) for r in territories) / len(territories) if territories else 0.0
    contested = sum(1 for r in territories if str(r["control_kind"]) == "disputed")
    territorial_integrity = _clamp(avg_integration - contested * 7.5) if territories else 0.0
    legitimacy = float(p["legitimacy"])
    stability = float(p["stability"])
    admin = float(p["administrative_capacity"])
    military = float(p["military_capacity"])
    treasury = float(p["treasury_pressure"])
    center_control = _clamp((stability + admin + avg_integration) / 3.0 - contested * 4.0)
    elite_cohesion = _clamp((legitimacy + stability) / 2.0)

    sep_rows = conn.execute(
        """SELECT accumulator,threshold,rate_per_30_days,location_id FROM political_processes
           WHERE polity_id=? AND active=1 AND process_type='separatism'""",
        (polity_id,),
    ).fetchall()
    separatist_pressure = 0.0
    for r in sep_rows:
        threshold = max(1.0, float(r["threshold"]))
        pressure = min(100.0, 100.0 * float(r["accumulator"]) / threshold)
        if float(r["rate_per_30_days"]) > 0:
            pressure = max(pressure, min(80.0, 20.0 + float(r["rate_per_30_days"]) * 8.0))
        separatist_pressure = max(separatist_pressure, pressure)
    if str(p["status"]) == "fragmenting":
        separatist_pressure = max(separatist_pressure, 72.0)

    sovereignty = _polity_sovereignty_status(conn, p)
    vitality = _clamp((legitimacy + stability + admin + military + (100.0 - treasury)) / 5.0)
    continuity = _clamp((legitimacy + admin + center_control) / 3.0)
    expansion = _clamp((admin + military + (100.0 - treasury)) / 3.0)
    status = "stable"
    if sovereignty == "dissolved":
        status = "dissolved"
    elif sovereignty == "fragmenting":
        status = "fragmenting"
    elif vitality < 25 or separatist_pressure >= 85:
        status = "crisis"
    elif vitality < 42 or separatist_pressure >= 60:
        status = "declining"
    elif vitality >= 70 and expansion >= 65 and separatist_pressure < 35:
        status = "rising"

    day = _day(conn)
    conn.execute(
        """INSERT INTO polity_lifecycle_profiles(
               polity_id,sovereignty_status,territorial_integrity,center_control,elite_cohesion,separatist_pressure,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(polity_id) DO UPDATE SET sovereignty_status=excluded.sovereignty_status,
               territorial_integrity=excluded.territorial_integrity,center_control=excluded.center_control,
               elite_cohesion=excluded.elite_cohesion,separatist_pressure=excluded.separatist_pressure,
               last_review_day=excluded.last_review_day,metadata_json=excluded.metadata_json""",
        (polity_id, sovereignty, territorial_integrity, center_control, elite_cohesion, separatist_pressure, day,
         _j({"territory_count": len(territories), "disputed_territory_count": contested, "derived_from_persisted_politics": True})),
    )
    conn.execute(
        """UPDATE organization_lifecycle_profiles SET lifecycle_kind='polity',lifecycle_status=?,vitality=?,cohesion=?,continuity=?,
               expansion_capacity=?,sovereignty_status=?,last_review_day=?,
               next_review_day=CASE WHEN ? THEN ? + review_cadence_days ELSE next_review_day END,
               metadata_json=json_patch(metadata_json,?) WHERE institution_actor_id=?""",
        (status, vitality, elite_cohesion, continuity, expansion, sovereignty, day,
         1 if schedule_next else 0, day, _j({"polity_id": polity_id, "country_lifecycle": True}), iid),
    )
    return {
        "lifecycle_status": status,
        "sovereignty_status": sovereignty,
        "vitality": vitality,
        "cohesion": elite_cohesion,
        "continuity": continuity,
        "expansion_capacity": expansion,
        "territorial_integrity": territorial_integrity,
        "center_control": center_control,
        "separatist_pressure": separatist_pressure,
    }


def refresh_institution_lifecycle(conn: sqlite3.Connection, institution_actor_id: int, *, schedule_next: bool = False) -> dict[str, float | str]:
    polity = _polity_row_for_institution(conn, institution_actor_id)
    if polity:
        return refresh_polity_lifecycle(conn, int(polity["id"]), schedule_next=schedule_next)
    ensure_lifecycle_profile(conn, institution_actor_id)
    row = conn.execute(
        """SELECT olp.*,ip.trajectory,ip.capacity_json,a.status AS actor_status
           FROM organization_lifecycle_profiles olp
           JOIN actors a ON a.id=olp.institution_actor_id
           LEFT JOIN institution_profiles ip ON ip.actor_id=olp.institution_actor_id
           WHERE olp.institution_actor_id=?""",
        (institution_actor_id,),
    ).fetchone()
    cap = _capability_mean(conn, institution_actor_id)
    if cap is None:
        cap = _numeric_capacity(row["capacity_json"]) if row and row["capacity_json"] is not None else None
    base = max(35.0, cap if cap is not None else 50.0)
    members = _active_members(conn, institution_actor_id)
    enterprises = _active_enterprises(conn, institution_actor_id)
    factions = conn.execute(
        "SELECT influence,cohesion FROM organization_factions WHERE institution_actor_id=? AND status='active'",
        (institution_actor_id,),
    ).fetchall()
    pressure = conn.execute(
        "SELECT COALESCE(SUM(intensity * (0.5 + urgency/200.0)),0) FROM organization_pressures WHERE institution_actor_id=? AND status='active'",
        (institution_actor_id,),
    ).fetchone()[0]
    pressure = min(100.0, float(pressure or 0.0))
    member_signal = min(5.0, math.log1p(members) * 1.5)
    enterprise_signal = min(4.0, enterprises * 1.0)
    if factions:
        weighted = sum(float(r["cohesion"]) * max(1.0, float(r["influence"])) for r in factions)
        denom = sum(max(1.0, float(r["influence"])) for r in factions)
        faction_cohesion = weighted / denom
        fragmentation_penalty = min(20.0, max(0, len(factions) - 1) * 3.0)
        cohesion = _clamp(faction_cohesion - fragmentation_penalty - pressure * 0.08)
    else:
        cohesion = _clamp(58.0 - pressure * 0.12)
    continuity_cap = conn.execute(
        "SELECT capacity,readiness FROM organization_capabilities WHERE institution_actor_id=? AND capability_key='organizational_continuity'",
        (institution_actor_id,),
    ).fetchone()
    continuity = _clamp((float(continuity_cap[0]) + float(continuity_cap[1])) / 2.0) if continuity_cap else _clamp((cohesion + 55.0) / 2.0)
    trajectory_hint = str(row["trajectory"] or "stable") if row else "stable"
    trajectory_offset = {"rising": 7.0, "stable": 0.0, "declining": -7.0, "transforming": 0.0, "crisis": -14.0, "dormant": -10.0}.get(trajectory_hint, 0.0)
    # Health is not scale.  A small organization can be robust; raw capacity mainly limits
    # what it can expand into, while continuity/cohesion/pressure determine whether it is healthy.
    vitality = _clamp(50.0 + (continuity - 50.0) * .24 + (cohesion - 50.0) * .20 + member_signal + enterprise_signal + trajectory_offset - pressure * .28)
    expansion = _clamp(base * .58 + vitality * .42 - pressure * 0.12)
    actor_status = str(row["actor_status"])
    prior_status = str(row["lifecycle_status"])
    if actor_status in {"destroyed", "dissolved", "inactive"}:
        status = "dissolved"
    elif pressure >= 85 or (vitality < 25 and cohesion < 35):
        status = "crisis"
    elif vitality < 42 or cohesion < 38:
        status = "declining"
    elif vitality >= 70 and expansion >= 65 and pressure < 30:
        status = "rising"
    else:
        status = "stable"
    day = _day(conn)
    conn.execute(
        """UPDATE organization_lifecycle_profiles SET lifecycle_status=?,vitality=?,cohesion=?,continuity=?,expansion_capacity=?,
               last_review_day=?,next_review_day=CASE WHEN ? THEN ? + review_cadence_days ELSE next_review_day END,
               metadata_json=json_patch(metadata_json,?) WHERE institution_actor_id=?""",
        (status, vitality, cohesion, continuity, expansion, day, 1 if schedule_next else 0, day,
         _j({"last_pressure_load": pressure, "member_count": members, "enterprise_count": enterprises}), institution_actor_id),
    )
    # Project only the broad lifecycle trajectory; domain-specific state remains authoritative.
    projected = {"rising": "rising", "stable": "stable", "declining": "declining", "crisis": "crisis", "dissolved": "dormant"}.get(status)
    if projected and conn.execute("SELECT 1 FROM institution_profiles WHERE actor_id=?", (institution_actor_id,)).fetchone():
        conn.execute("UPDATE institution_profiles SET trajectory=?,last_review_day=? WHERE actor_id=?", (projected, day, institution_actor_id))
    return {"lifecycle_status": status, "vitality": vitality, "cohesion": cohesion, "continuity": continuity, "expansion_capacity": expansion}


def activate_organization_lifecycle(conn: sqlite3.Connection) -> dict[str, int]:
    day = _day(conn)
    created = 0
    for row in conn.execute(
        """SELECT ip.actor_id,ip.institution_kind FROM institution_profiles ip
           JOIN actors a ON a.id=ip.actor_id WHERE a.status='active' ORDER BY ip.actor_id"""
    ).fetchall():
        iid = int(row["actor_id"])
        before = conn.execute("SELECT 1 FROM organization_lifecycle_profiles WHERE institution_actor_id=?", (iid,)).fetchone()
        ensure_lifecycle_profile(conn, iid, lifecycle_kind=str(row["institution_kind"]), metadata={"activation":"ORGLIFE-01"})
        # If the opening seed explicitly declares a required role/capability, project its current
        # unmet need at activation rather than pretending all organization needs begin after day 0.
        from .organization_needs import refresh_organization_needs
        refresh_organization_needs(conn, iid, day=day)
        refresh_institution_lifecycle(conn, iid, schedule_next=False)
        if not before:
            created += 1
    polities = 0
    for p in conn.execute("SELECT id FROM political_polities ORDER BY id").fetchall():
        refresh_polity_lifecycle(conn, int(p[0]), schedule_next=False)
        polities += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('orglife01_activation_version','1')")
    return {"organization_lifecycle_profiles_created": created, "polity_lifecycle_profiles": polities}


def next_organization_lifecycle_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    row = conn.execute(
        """SELECT MIN(next_review_day) FROM organization_lifecycle_profiles
           WHERE lifecycle_status NOT IN ('dissolved','absorbed') AND next_review_day>? AND next_review_day<=?""",
        (after_day, end_day),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _eligible_breakaway_location(conn: sqlite3.Connection, polity_id: int) -> sqlite3.Row | None:
    # Country fission requires an actual active separatist process tied to a territory. A low
    # stability score by itself never manufactures a new country.
    return conn.execute(
        """SELECT pp.*,tc.integration,tc.control_kind
           FROM political_processes pp
           JOIN territorial_control tc ON tc.location_id=pp.location_id AND tc.controller_polity_id=pp.polity_id
           WHERE pp.polity_id=? AND pp.active=1 AND pp.process_type='separatism' AND pp.location_id IS NOT NULL
             AND (pp.auto_action='fragment' OR EXISTS(SELECT 1 FROM political_polities p WHERE p.id=pp.polity_id AND p.status='fragmenting'))
             AND tc.integration<=25
           ORDER BY tc.integration ASC,pp.id ASC LIMIT 1""",
        (polity_id,),
    ).fetchone()


def _structural_polity_name(conn: sqlite3.Connection, parent_polity_id: int, location_id: int, day: int) -> str:
    base = f"[STRUCTURAL] polity from parent {parent_polity_id} / territory {location_id} / day {day}"
    name = base
    n = 2
    while conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
        name = f"{base} #{n}"
        n += 1
    return name


def form_breakaway_polity(
    conn: sqlite3.Connection,
    parent_polity_id: int,
    location_ids: list[int],
    *,
    name: str | None = None,
    polity_kind: str = "breakaway",
    ruler_actor_id: int | None = None,
    reason: str = "territorial secession",
    cause_kind: str = "separatism",
    cause_id: int | None = None,
) -> int:
    from .politics import configure_polity, transfer_territory
    parent = conn.execute("SELECT * FROM political_polities WHERE id=?", (parent_polity_id,)).fetchone()
    if not parent or str(parent["status"]) == "dissolved":
        raise ValueError("parent polity is not active")
    owned = [int(r[0]) for r in conn.execute("SELECT location_id FROM territorial_control WHERE controller_polity_id=? ORDER BY location_id", (parent_polity_id,)).fetchall()]
    requested = sorted(set(int(x) for x in location_ids))
    if not requested or any(x not in owned for x in requested):
        raise ValueError("breakaway territory must currently belong to parent polity")
    if len(requested) >= len(owned):
        raise ValueError("breakaway must leave the parent with at least one controlled territory; use succession/absorption for full replacement")
    day = _day(conn)
    parent_iid = int(parent["institution_actor_id"])
    final_name = str(name).strip() if name and str(name).strip() else _structural_polity_name(conn, parent_polity_id, requested[0], day)
    unresolved = not bool(name and str(name).strip())
    primary_location = requested[0]
    cur = conn.execute(
        """INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo)
           VALUES (?,'institution','polity',?,?,'active',?,0)""",
        (final_name, primary_location, primary_location,
         "STRUCTURAL polity identity created from causal secession; ordinary/social name unresolved." if unresolved else "Polity formed from causal secession."),
    )
    iid = int(cur.lastrowid)
    conn.execute(
        """INSERT INTO institution_profiles(actor_id,institution_kind,founded_day,parent_institution_actor_id,primary_location_id,
               governance_json,culture_json,capacity_json,trajectory,last_review_day,notes)
           VALUES (?,?,?,?,?,?,?,?, 'transforming',?,?)""",
        (iid, "polity", day, parent_iid, primary_location,
         _j({"formation":"secession","name_resolution":"unresolved" if unresolved else "grounded"}),
         _j({"inheritance_from_polity_id": parent_polity_id}),
         _j({"initial_territory_count": len(requested)}), day,
         "Country-scale organization created from persisted political/territorial causes; no prehistory invented."),
    )
    conn.execute(
        """INSERT INTO entity_resolution(entity_kind,entity_id,resolution_level,reason,review_cadence_days,next_review_day,last_changed_day,locked_min_level,metadata_json)
           VALUES ('institution',?,'STRUCTURAL','causal polity formation',90,?,?, 'STRUCTURAL',?)""",
        (iid, day + 90, day, _j({"country_formation": True, "unresolved_name": unresolved})),
    )
    pid = configure_polity(
        conn, iid, polity_kind=polity_kind, ruler_actor_id=ruler_actor_id,
        succession_method="unsettled" if ruler_actor_id is None else str(parent["succession_method"]),
        legitimacy=max(25.0, float(parent["legitimacy"]) * 0.72),
        stability=max(20.0, float(parent["stability"]) * 0.65),
        administrative_capacity=max(18.0, float(parent["administrative_capacity"]) * 0.58),
        military_capacity=max(15.0, float(parent["military_capacity"]) * 0.48),
        treasury_pressure=min(85.0, float(parent["treasury_pressure"]) + 18.0),
        founded_day=day,
        metadata={"formation":"secession","parent_polity_id": parent_polity_id,"unresolved_name": unresolved,"cause_kind": cause_kind,"cause_id": cause_id},
    )
    try:
        from .polity_agency import ensure_polity_government_actor
        ensure_polity_government_actor(conn, pid)
    except (sqlite3.OperationalError, ImportError):
        pass
    for loc in requested:
        transfer_territory(conn, loc, pid, control_kind="direct", legitimacy=42, integration=20,
                           reason=f"{reason}; territory entered newly formed polity #{pid}")
    _rehome_conflict_channels(conn, parent_polity_id, pid, only_locations=set(requested))
    _seed_secession_relation(conn, parent_polity_id, pid, location_id=requested[0])
    ensure_lifecycle_profile(conn, iid, lifecycle_kind="polity", parent_institution_actor_id=parent_iid,
                             metadata={"polity_id": pid, "country_formation": True, "unresolved_name": unresolved})
    refresh_polity_lifecycle(conn, pid)
    conn.execute(
        """INSERT OR IGNORE INTO organization_lineage_links(predecessor_institution_actor_id,successor_institution_actor_id,link_kind,day,metadata_json)
           VALUES (?,?, 'secession',?,?)""",
        (parent_iid, iid, day, _j({"parent_polity_id": parent_polity_id,"successor_polity_id": pid,"territory_ids": requested,"reason": reason})),
    )
    record_lifecycle_event(conn, parent_iid, "polity_fission", f"Polity #{parent_polity_id} lost territory to a newly formed polity #{pid}.",
                           other_institution_actor_id=iid, polity_id=parent_polity_id, other_polity_id=pid,
                           cause_kind=cause_kind, cause_id=cause_id, detail={"territory_ids": requested,"reason": reason})
    record_lifecycle_event(conn, iid, "polity_formation", f"Polity #{pid} formed through secession from polity #{parent_polity_id}.",
                           other_institution_actor_id=parent_iid, polity_id=pid, other_polity_id=parent_polity_id,
                           cause_kind=cause_kind, cause_id=cause_id, detail={"territory_ids": requested,"reason": reason,"unresolved_name": unresolved})
    # Avoid immediately reusing the same separatist process as a second country-formation trigger.
    if cause_id is not None and cause_kind == "separatism":
        conn.execute("UPDATE political_processes SET active=0 WHERE id=?", (int(cause_id),))
    return pid



def _copy_external_relation(conn: sqlite3.Connection, source_polity_id: int, successor_polity_id: int, other_polity_id: int) -> None:
    if successor_polity_id == other_polity_id:
        return
    lo, hi = sorted((source_polity_id, other_polity_id))
    row = conn.execute("SELECT * FROM political_relations WHERE polity_a_id=? AND polity_b_id=?", (lo, hi)).fetchone()
    if not row:
        return
    nlo, nhi = sorted((successor_polity_id, other_polity_id))
    existing = conn.execute("SELECT * FROM political_relations WHERE polity_a_id=? AND polity_b_id=?", (nlo, nhi)).fetchone()
    if existing:
        # Preserve the more tense current relationship rather than silently softening it.
        tension = max(float(existing["tension"]), float(row["tension"]))
        stance = (float(existing["stance"]) + float(row["stance"])) / 2.0
        trust = min(float(existing["trust"]), float(row["trust"]))
        kind_rank = {"allied":0,"friendly":1,"neutral":2,"truce":3,"rival":4,"hostile":5,"war":6}
        kind = str(existing["relation_kind"]) if kind_rank.get(str(existing["relation_kind"]),2) >= kind_rank.get(str(row["relation_kind"]),2) else str(row["relation_kind"])
    else:
        tension = float(row["tension"]); stance = float(row["stance"]); trust = float(row["trust"]); kind = str(row["relation_kind"])
    conn.execute(
        """INSERT INTO political_relations(polity_a_id,polity_b_id,relation_kind,stance,trust,tension,updated_day,notes)
           VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(polity_a_id,polity_b_id) DO UPDATE SET
           relation_kind=excluded.relation_kind,stance=excluded.stance,trust=excluded.trust,tension=excluded.tension,
           updated_day=excluded.updated_day,notes=excluded.notes""",
        (nlo,nhi,kind,_clamp(stance,-100,100),_clamp(trust,-100,100),_clamp(tension),_day(conn),
         f"Provisional relationship inherited through polity succession from polity #{source_polity_id}."),
    )


def _rehome_conflict_channels(conn: sqlite3.Connection, source_polity_id: int, successor_polity_id: int, *, only_locations: set[int] | None = None) -> int:
    """Carry geographically relevant active conflict channels into a successor polity.

    This prevents a secession/union from leaving live frontier pressure attached to a polity that
    no longer controls the channel's endpoint.  Channels between predecessor and successor are
    simply resolved rather than recreated as self-conflict.
    """
    day = _day(conn)
    rows = conn.execute(
        "SELECT * FROM conflict_channels WHERE status='active' AND (polity_a_id=? OR polity_b_id=?) ORDER BY id",
        (source_polity_id, source_polity_id),
    ).fetchall()
    moved = 0
    for ch in rows:
        source_is_a = int(ch["polity_a_id"]) == source_polity_id
        source_loc = ch["location_a_id"] if source_is_a else ch["location_b_id"]
        if only_locations is not None and (source_loc is None or int(source_loc) not in only_locations):
            continue
        other = int(ch["polity_b_id"] if source_is_a else ch["polity_a_id"])
        if other == successor_polity_id:
            conn.execute("UPDATE conflict_channels SET status='resolved',last_review_day=? WHERE id=?", (day,int(ch["id"])))
            continue
        a = successor_polity_id if source_is_a else other
        b = other if source_is_a else successor_polity_id
        la = ch["location_a_id"] if source_is_a else ch["location_a_id"]
        lb = ch["location_b_id"] if not source_is_a else ch["location_b_id"]
        if not source_is_a:
            # Original A was the external polity; only B changes.
            a = other; b = successor_polity_id
            la = ch["location_a_id"]; lb = ch["location_b_id"]
        key = f"successor:{successor_polity_id}:from-channel:{int(ch['id'])}:day:{day}"
        cur = conn.execute(
            """INSERT OR IGNORE INTO conflict_channels(channel_key,polity_a_id,polity_b_id,issue_kind,location_a_id,location_b_id,
                   base_pressure,volatility,restraint,incident_threshold,accumulated_pressure,review_cadence_days,last_review_day,next_review_day,status,metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?)""",
            (key,a,b,str(ch["issue_kind"]),la,lb,float(ch["base_pressure"]),float(ch["volatility"]),float(ch["restraint"]),
             float(ch["incident_threshold"]),float(ch["accumulated_pressure"]),int(ch["review_cadence_days"]),day,day+int(ch["review_cadence_days"]),
             _j({"inherited_from_conflict_channel_id":int(ch["id"]),"source_polity_id":source_polity_id,"successor_polity_id":successor_polity_id})),
        )
        newrow = conn.execute("SELECT id FROM conflict_channels WHERE channel_key=?", (key,)).fetchone()
        conn.execute("UPDATE conflict_channels SET status='resolved',last_review_day=?,metadata_json=json_patch(metadata_json,?) WHERE id=?",
                     (day,_j({"successor_channel_id":int(newrow[0]) if newrow else None,"successor_polity_id":successor_polity_id}),int(ch["id"])))
        _copy_external_relation(conn, source_polity_id, successor_polity_id, other)
        moved += 1
    return moved


def _seed_secession_relation(conn: sqlite3.Connection, parent_polity_id: int, new_polity_id: int, *, location_id: int) -> None:
    lo, hi = sorted((parent_polity_id,new_polity_id))
    conn.execute(
        """INSERT INTO political_relations(polity_a_id,polity_b_id,relation_kind,stance,trust,tension,updated_day,notes)
           VALUES (?,?,'rival',-28,-22,58,?,?)
           ON CONFLICT(polity_a_id,polity_b_id) DO UPDATE SET relation_kind='rival',stance=MIN(political_relations.stance,-28),
           trust=MIN(political_relations.trust,-22),tension=MAX(political_relations.tension,58),updated_day=excluded.updated_day,notes=excluded.notes""",
        (lo,hi,_day(conn),f"Relationship created by secession around territory #{location_id}; may later de-escalate or escalate causally."),
    )
    key=f"secession:{parent_polity_id}:{new_polity_id}:{location_id}"
    for a,b,posture,pressure,restraint in [
        (parent_polity_id,new_polity_id,"hardline",68,38),
        (new_polity_id,parent_polity_id,"hardline",72,32),
    ]:
        conn.execute(
            """INSERT INTO polity_issue_states(polity_id,other_polity_id,issue_key,issue_kind,interest,pressure,restraint,preferred_posture,updated_day,metadata_json)
               VALUES (?,?,?,?,78,?,?,?,?,?) ON CONFLICT(polity_id,other_polity_id,issue_key) DO UPDATE SET
               pressure=MAX(polity_issue_states.pressure,excluded.pressure),restraint=MIN(polity_issue_states.restraint,excluded.restraint),
               preferred_posture=excluded.preferred_posture,updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
            (a,b,key,"sovereignty",pressure,restraint,posture,_day(conn),_j({"secession_location_id":location_id,"structural_lifecycle_origin":True})),
        )


def merge_polities(conn: sqlite3.Connection, survivor_polity_id: int, absorbed_polity_id: int, *, reason: str = "political absorption") -> None:
    from .politics import dissolve_polity
    if survivor_polity_id == absorbed_polity_id:
        raise ValueError("cannot merge polity into itself")
    survivor = conn.execute("SELECT * FROM political_polities WHERE id=?", (survivor_polity_id,)).fetchone()
    absorbed = conn.execute("SELECT * FROM political_polities WHERE id=?", (absorbed_polity_id,)).fetchone()
    if not survivor or not absorbed:
        raise ValueError("unknown polity")
    if str(survivor["status"]) == "dissolved" or str(absorbed["status"]) == "dissolved":
        raise ValueError("cannot merge a dissolved polity")
    day = _day(conn)
    survivor_iid = int(survivor["institution_actor_id"])
    absorbed_iid = int(absorbed["institution_actor_id"])
    territory_ids = [int(r[0]) for r in conn.execute("SELECT location_id FROM territorial_control WHERE controller_polity_id=? ORDER BY location_id", (absorbed_polity_id,)).fetchall()]
    dissolve_polity(conn, absorbed_polity_id, successor_polity_id=survivor_polity_id, reason=reason)
    conn.execute(
        """INSERT OR IGNORE INTO organization_lineage_links(predecessor_institution_actor_id,successor_institution_actor_id,link_kind,day,metadata_json)
           VALUES (?,?, 'absorption',?,?)""",
        (absorbed_iid, survivor_iid, day, _j({"absorbed_polity_id": absorbed_polity_id,"survivor_polity_id": survivor_polity_id,"territory_ids": territory_ids,"reason": reason})),
    )
    conn.execute(
        "UPDATE organization_lifecycle_profiles SET lifecycle_status='absorbed',sovereignty_status='dissolved',last_review_day=?,metadata_json=json_patch(metadata_json,?) WHERE institution_actor_id=?",
        (day, _j({"absorbed_into_polity_id": survivor_polity_id}), absorbed_iid),
    )
    refresh_polity_lifecycle(conn, survivor_polity_id)
    record_lifecycle_event(conn, survivor_iid, "polity_absorption", f"Polity #{survivor_polity_id} absorbed polity #{absorbed_polity_id}.",
                           other_institution_actor_id=absorbed_iid, polity_id=survivor_polity_id, other_polity_id=absorbed_polity_id,
                           detail={"territory_ids": territory_ids,"reason": reason})



def unify_polities(
    conn: sqlite3.Connection,
    predecessor_polity_ids: list[int],
    *,
    name: str | None = None,
    polity_kind: str = "union",
    ruler_actor_id: int | None = None,
    reason: str = "political unification",
) -> int:
    """Create a new country from two or more predecessor polities.

    This is distinct from :func:`merge_polities`, where one existing country survives and
    absorbs another.  Here the successor is a new institutional/political identity and every
    predecessor becomes historical.  A socially grounded name is optional; structural identity
    is enough for the country to exist in the simulation.
    """
    from .politics import configure_polity, transfer_territory, dissolve_polity
    ids = sorted(set(int(x) for x in predecessor_polity_ids))
    if len(ids) < 2:
        raise ValueError("political unification requires at least two predecessor polities")
    preds = []
    for pid in ids:
        row = conn.execute("SELECT * FROM political_polities WHERE id=?", (pid,)).fetchone()
        if not row or str(row["status"]) == "dissolved":
            raise ValueError("all predecessor polities must be active")
        preds.append(row)
    day = _day(conn)
    territories: list[int] = []
    for pid in ids:
        territories.extend(int(r[0]) for r in conn.execute(
            "SELECT location_id FROM territorial_control WHERE controller_polity_id=? ORDER BY location_id", (pid,)
        ).fetchall())
    if not territories:
        raise ValueError("cannot form a territorial union from polities with no controlled territory")
    final_name = str(name).strip() if name and str(name).strip() else f"[STRUCTURAL] union polity {'-'.join(str(x) for x in ids)} / day {day}"
    unresolved = not bool(name and str(name).strip())
    if conn.execute("SELECT 1 FROM actors WHERE name=?", (final_name,)).fetchone():
        final_name += f" #{max(ids)+1}"
    primary_location = territories[0]
    cur = conn.execute(
        """INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo)
           VALUES (?,'institution','polity',?,?,'active',?,0)""",
        (final_name,primary_location,primary_location,
         "STRUCTURAL successor country created by political union; ordinary/social name unresolved." if unresolved else "Successor country created by political union."),
    )
    iid = int(cur.lastrowid)
    avg = lambda key: sum(float(r[key]) for r in preds)/len(preds)
    conn.execute(
        """INSERT INTO institution_profiles(actor_id,institution_kind,founded_day,primary_location_id,governance_json,culture_json,capacity_json,trajectory,last_review_day,notes)
           VALUES (?,'polity',?,?,?, ?,?,'transforming',?,?)""",
        (iid,day,primary_location,
         _j({"formation":"political_union","predecessor_polity_ids":ids,"name_resolution":"unresolved" if unresolved else "grounded"}),
         _j({"inheritance_from_polities":ids}),
         _j({"initial_territory_count":len(territories)}),day,
         "New country formed from existing polities; predecessor histories remain separate and queryable."),
    )
    conn.execute(
        """INSERT INTO entity_resolution(entity_kind,entity_id,resolution_level,reason,review_cadence_days,next_review_day,last_changed_day,locked_min_level,metadata_json)
           VALUES ('institution',?,'STRUCTURAL','causal polity union',90,?,?, 'STRUCTURAL',?)""",
        (iid,day+90,day,_j({"country_union":True,"predecessor_polity_ids":ids,"unresolved_name":unresolved})),
    )
    new_pid = configure_polity(
        conn,iid,polity_kind=polity_kind,ruler_actor_id=ruler_actor_id,
        succession_method="unsettled" if ruler_actor_id is None else str(preds[0]["succession_method"]),
        legitimacy=_clamp(avg("legitimacy")*.92),stability=_clamp(avg("stability")*.88),
        administrative_capacity=_clamp(avg("administrative_capacity")*.90),
        military_capacity=_clamp(avg("military_capacity")*.88),
        treasury_pressure=_clamp(avg("treasury_pressure")+12),founded_day=day,
        metadata={"formation":"political_union","predecessor_polity_ids":ids,"unresolved_name":unresolved},
    )
    try:
        from .polity_agency import ensure_polity_government_actor
        ensure_polity_government_actor(conn,new_pid)
    except (sqlite3.OperationalError, ImportError):
        pass
    for loc in sorted(set(territories)):
        transfer_territory(conn,loc,new_pid,control_kind="direct",legitimacy=48,integration=35,
                           reason=f"{reason}; territory transferred into successor polity #{new_pid}")
    ensure_lifecycle_profile(conn,iid,lifecycle_kind="polity",metadata={"polity_id":new_pid,"country_union":True,"unresolved_name":unresolved})
    refresh_polity_lifecycle(conn,new_pid)
    for pred in preds:
        pid=int(pred["id"]); piid=int(pred["institution_actor_id"])
        conn.execute(
            """INSERT OR IGNORE INTO organization_lineage_links(predecessor_institution_actor_id,successor_institution_actor_id,link_kind,day,metadata_json)
               VALUES (?,?,'merger',?,?)""",
            (piid,iid,day,_j({"predecessor_polity_id":pid,"successor_polity_id":new_pid,"reason":reason})),
        )
        dissolve_polity(conn,pid,successor_polity_id=new_pid,reason=f"{reason}; predecessor polity entered successor union #{new_pid}")
        record_lifecycle_event(conn,piid,"polity_merger_exit",f"Polity #{pid} ceased as a separate country through union into polity #{new_pid}.",
                               other_institution_actor_id=iid,polity_id=pid,other_polity_id=new_pid,detail={"reason":reason})
    record_lifecycle_event(conn,iid,"polity_formation",f"Polity #{new_pid} formed through political union of predecessor polities {ids}.",
                           polity_id=new_pid,detail={"predecessor_polity_ids":ids,"reason":reason,"unresolved_name":unresolved})
    return new_pid


def mark_polity_dissolved(conn: sqlite3.Connection, polity_id: int, *, successor_polity_id: int | None = None, reason: str = "polity dissolved") -> None:
    row = conn.execute("SELECT institution_actor_id FROM political_polities WHERE id=?", (polity_id,)).fetchone()
    if not row:
        return
    iid = int(row[0])
    ensure_lifecycle_profile(conn, iid, lifecycle_kind="polity", metadata={"polity_id": polity_id})
    day = _day(conn)
    if successor_polity_id is not None:
        _rehome_conflict_channels(conn, polity_id, successor_polity_id)
        # Carry existing external relations into the successor where they remain relevant.
        others = set()
        for rr in conn.execute("SELECT polity_a_id,polity_b_id FROM political_relations WHERE polity_a_id=? OR polity_b_id=?", (polity_id,polity_id)).fetchall():
            other = int(rr["polity_b_id"] if int(rr["polity_a_id"]) == polity_id else rr["polity_a_id"])
            if other != successor_polity_id:
                others.add(other)
        for other in sorted(others):
            _copy_external_relation(conn, polity_id, successor_polity_id, other)
    conn.execute("UPDATE conflict_channels SET status='resolved',last_review_day=? WHERE status='active' AND (polity_a_id=? OR polity_b_id=?)", (day,polity_id,polity_id))
    conn.execute("UPDATE conflict_incidents SET status='expired' WHERE status='open' AND (initiator_polity_id=? OR target_polity_id=?)", (polity_id,polity_id))
    conn.execute("UPDATE organization_regimes SET status='ended',ended_day=? WHERE institution_actor_id=? AND status='active'", (day,iid))
    conn.execute("UPDATE actors SET status='inactive' WHERE id=?", (iid,))
    conn.execute(
        "UPDATE organization_lifecycle_profiles SET lifecycle_status='dissolved',sovereignty_status='dissolved',last_review_day=?,metadata_json=json_patch(metadata_json,?) WHERE institution_actor_id=?",
        (day, _j({"dissolved_reason": reason,"successor_polity_id": successor_polity_id}), iid),
    )
    conn.execute(
        """INSERT INTO polity_lifecycle_profiles(polity_id,sovereignty_status,territorial_integrity,center_control,elite_cohesion,separatist_pressure,last_review_day,metadata_json)
           VALUES (?, 'dissolved',0,0,0,0,?,?)
           ON CONFLICT(polity_id) DO UPDATE SET sovereignty_status='dissolved',territorial_integrity=0,center_control=0,last_review_day=excluded.last_review_day,
               metadata_json=json_patch(polity_lifecycle_profiles.metadata_json,excluded.metadata_json)""",
        (polity_id, day, _j({"dissolved_reason": reason,"successor_polity_id": successor_polity_id})),
    )
    # Avoid duplicate lifecycle records if merge_polities called dissolve_polity and then annotates absorption.
    if not conn.execute("SELECT 1 FROM organization_lifecycle_events WHERE institution_actor_id=? AND event_type='polity_dissolution' AND day=?", (iid, day)).fetchone():
        other_iid = None
        if successor_polity_id is not None:
            r = conn.execute("SELECT institution_actor_id FROM political_polities WHERE id=?", (successor_polity_id,)).fetchone()
            other_iid = int(r[0]) if r else None
        record_lifecycle_event(conn, iid, "polity_dissolution", reason,
                               other_institution_actor_id=other_iid, polity_id=polity_id, other_polity_id=successor_polity_id,
                               detail={"successor_polity_id": successor_polity_id})


def record_absorption(conn: sqlite3.Connection, winner_institution_actor_id: int, loser_institution_actor_id: int, *, domain: str, detail: dict[str, Any] | None = None) -> None:
    day = _day(conn)
    ensure_lifecycle_profile(conn, winner_institution_actor_id, metadata={"domain": domain})
    ensure_lifecycle_profile(conn, loser_institution_actor_id, metadata={"domain": domain})
    conn.execute(
        """INSERT OR IGNORE INTO organization_lineage_links(predecessor_institution_actor_id,successor_institution_actor_id,link_kind,day,metadata_json)
           VALUES (?,?,'absorption',?,?)""",
        (loser_institution_actor_id, winner_institution_actor_id, day, _j({"domain": domain, **(detail or {})})),
    )
    conn.execute(
        "UPDATE organization_lifecycle_profiles SET lifecycle_status='absorbed',last_review_day=?,metadata_json=json_patch(metadata_json,?) WHERE institution_actor_id=?",
        (day, _j({"absorbed_into_institution_actor_id": winner_institution_actor_id,"domain": domain}), loser_institution_actor_id),
    )
    record_lifecycle_event(conn, winner_institution_actor_id, "organization_absorption", "An organization absorbed another existing organization.",
                           other_institution_actor_id=loser_institution_actor_id, detail={"domain": domain, **(detail or {})})


def record_formation(conn: sqlite3.Connection, institution_actor_id: int, *, candidate_id: int | None = None, unresolved_name: bool = False, detail: dict[str, Any] | None = None) -> None:
    ensure_lifecycle_profile(conn, institution_actor_id, metadata={"formation_candidate_id": candidate_id,"unresolved_name": unresolved_name})
    # New organizations join the shared agency substrate immediately; domain modules can later
    # add richer leadership, faction, strategy and capability semantics.
    try:
        from .organization_agency import ensure_agency_profile, start_regime
        ip=conn.execute("SELECT institution_kind,culture_json,governance_json FROM institution_profiles WHERE actor_id=?",(institution_actor_id,)).fetchone()
        inheritance={"institution_kind":str(ip["institution_kind"])} if ip else {}
        if ip:
            inheritance.update({"culture":_obj(ip["culture_json"]),"governance":_obj(ip["governance_json"])})
        ensure_agency_profile(conn,institution_actor_id,governance_mode="institutional",inheritance=inheritance,
                              metadata={"formed_under_orglife01":True,"formation_candidate_id":candidate_id})
        start_regime(conn,institution_actor_id,regime_kind="formation",metadata={"formation_candidate_id":candidate_id})
    except (sqlite3.OperationalError, ImportError):
        pass
    if not conn.execute("SELECT 1 FROM organization_lifecycle_events WHERE institution_actor_id=? AND event_type='formation' LIMIT 1", (institution_actor_id,)).fetchone():
        record_lifecycle_event(conn, institution_actor_id, "formation", "A causally formed organization crossed into persistent structural identity.",
                               cause_kind="emergent_institution_candidate" if candidate_id is not None else None,
                               cause_id=candidate_id, detail={"unresolved_name": unresolved_name, **(detail or {})})


def _process_polity_fission_if_grounded(conn: sqlite3.Connection, polity_id: int) -> int | None:
    p = conn.execute("SELECT * FROM political_polities WHERE id=?", (polity_id,)).fetchone()
    if not p or str(p["status"]) != "fragmenting":
        return None
    owned = int(conn.execute("SELECT COUNT(*) FROM territorial_control WHERE controller_polity_id=?", (polity_id,)).fetchone()[0])
    if owned < 2:
        return None
    sep = _eligible_breakaway_location(conn, polity_id)
    if not sep:
        return None
    # Require a substantially developed separatist cause, not just the existence of a process row.
    threshold = max(1.0, float(sep["threshold"]))
    developed = float(sep["accumulator"]) >= threshold * 0.45 or float(sep["rate_per_30_days"]) >= 4.0
    if not developed:
        return None
    return form_breakaway_polity(conn, polity_id, [int(sep["location_id"])],
                                 reason="causal separatist process produced a breakaway polity",
                                 cause_kind="separatism", cause_id=int(sep["id"]))


def process_due_organization_lifecycle(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict[str, int]:
    rows = conn.execute(
        """SELECT institution_actor_id,lifecycle_status FROM organization_lifecycle_profiles
           WHERE lifecycle_status NOT IN ('dissolved','absorbed') AND next_review_day<=?
           ORDER BY next_review_day,institution_actor_id""",
        (day,),
    ).fetchall()
    changed = 0
    polity_fissions = 0
    needs_created = 0
    needs_resolved = 0
    for row in rows:
        iid = int(row["institution_actor_id"])
        before = str(row["lifecycle_status"])
        # ORGNEED-01 projects only explicit role/capability requirements before lifecycle
        # health is calculated, so a real unresolved need can contribute to pressure load.
        from .organization_needs import refresh_organization_needs
        needs = refresh_organization_needs(conn, iid, day=day)
        needs_created += int(needs["needs_created"])
        needs_resolved += int(needs["needs_resolved"])
        state = refresh_institution_lifecycle(conn, iid, schedule_next=True)
        after = str(state["lifecycle_status"])
        if before != after:
            changed += 1
            record_lifecycle_event(conn, iid, "trajectory_change",
                                   f"Organization lifecycle shifted from {before} to {after}.",
                                   polity_id=(int(_polity_row_for_institution(conn, iid)["id"]) if _polity_row_for_institution(conn, iid) else None),
                                   detail={"prior_status": before, "new_status": after, **{k:v for k,v in state.items() if isinstance(v,(int,float,str))}})
        p = _polity_row_for_institution(conn, iid)
        if p and str(p["status"]) != "dissolved":
            new_pid = _process_polity_fission_if_grounded(conn, int(p["id"]))
            if new_pid is not None:
                polity_fissions += 1
                if event_logger is not None:
                    event_logger(day=day,event_type="politics:polity_formation",title="New polity formed",
                                 summary=f"A separatist political process produced new polity #{new_pid} from polity #{int(p['id'])}.",severity=4)
    return {"organization_lifecycle_reviews": len(rows), "organization_trajectory_changes": changed, "polity_fissions": polity_fissions,
            "organization_needs_created": needs_created, "organization_needs_resolved": needs_resolved}


def lifecycle_summary(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "profiles": int(conn.execute("SELECT COUNT(*) FROM organization_lifecycle_profiles").fetchone()[0]),
        "polity_profiles": int(conn.execute("SELECT COUNT(*) FROM polity_lifecycle_profiles").fetchone()[0]),
        "formations": int(conn.execute("SELECT COUNT(*) FROM organization_lifecycle_events WHERE event_type IN ('formation','polity_formation')").fetchone()[0]),
        "fissions": int(conn.execute("SELECT COUNT(*) FROM organization_lifecycle_events WHERE event_type='polity_fission'").fetchone()[0]),
        "absorptions": int(conn.execute("SELECT COUNT(*) FROM organization_lineage_links WHERE link_kind='absorption'").fetchone()[0]),
        "dissolved": int(conn.execute("SELECT COUNT(*) FROM organization_lifecycle_profiles WHERE lifecycle_status='dissolved'").fetchone()[0]),
    }
