from __future__ import annotations

"""Opening world-state completion without invented history.

Day-zero seed rows sometimes omit ordinary present location or the ordinary identity of an
institutional officeholder. Those are incomplete current-state facts, not deliberate mysteries.
This module resolves them deterministically from evidence already present at opening. Every
working placement is explicitly provenance-marked and is never represented as a historical event.
"""

import hashlib
import json
import sqlite3
from typing import Any

from .person_ecology import resolve_background_person

MARTIAL_KINDS = {
    "sect", "sect/school", "martial school", "military school", "military academy",
    "military college", "order", "clan/house", "coven", "state martial establishment",
    "martial/religious order", "martial religious order", "martial institution",
    "noble martial house", "military tradition",
}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(v: Any) -> str:
    return json.dumps(v if v is not None else {}, sort_keys=True, ensure_ascii=False)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def _source_payload(conn: sqlite3.Connection, actor_id: int, entity_kind: str = "actor") -> dict[str, Any]:
    row = conn.execute(
        """SELECT source_payload_json FROM source_identity_map
           WHERE entity_kind=? AND entity_id=? ORDER BY CASE WHEN source_key LIKE 'person:%' OR source_key LIKE 'institution:%' THEN 0 ELSE 1 END,id LIMIT 1""",
        (entity_kind, actor_id),
    ).fetchone()
    return _loads(row[0], {}) if row else {}


def _stable_index(key: str, n: int) -> int:
    if n <= 1:
        return 0
    h = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") % n


def _owner_from_state(state: str | None) -> str | None:
    s = (state or "").strip().lower()
    if not s:
        return None
    if "windmere" in s:
        return "Windmere"
    if "dunmoor" in s:
        return "Dunmoor"
    if "greywood" in s:
        return "Greywood"
    if "sunreach" in s:
        return "Sunreach Confederacy"
    if "stormhollow" in s:
        return "Stormhollow"
    if "thornward" in s:
        return "Thornward"
    if "hearth" in s or "underheaven" in s or "cairnholt" in s:
        return "Underheaven Empire"
    return None


def _location_by_name(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def _location_pool(conn: sqlite3.Connection, owner: str | None) -> list[int]:
    if owner:
        rows = conn.execute(
            """SELECT id FROM locations WHERE political_owner=? AND kind IN
               ('settlement','medical city/node','scholarly/appraisal node','road-river city','cultivation settlement/site')
               ORDER BY id""", (owner,),
        ).fetchall()
        if rows:
            return [int(r[0]) for r in rows]
    # The unanchored opening martial ecology is overwhelmingly Hearth/Long Road. Waymeet is the
    # neutral current-state fallback: a working placement, not a claim of residence or origin.
    wid = _location_by_name(conn, "Waymeet")
    if wid is not None:
        return [wid]
    return [int(r[0]) for r in conn.execute("SELECT id FROM locations WHERE kind='settlement' ORDER BY id LIMIT 1").fetchall()]


def _working_location(conn: sqlite3.Connection, key: str, *, state: str | None = None, preferred: str | None = None) -> tuple[int | None, str, float]:
    if preferred:
        lid = _location_by_name(conn, preferred)
        if lid is not None:
            return lid, "explicit_or_strong_named_anchor", .92
    owner = _owner_from_state(state)
    pool = _location_pool(conn, owner)
    if not pool:
        return None, "unresolved", 0.0
    return pool[_stable_index(key, len(pool))], "state_sphere_working_placement" if owner else "hearth_road_working_placement", .62 if owner else .48


def _record_location(conn: sqlite3.Connection, actor_id: int, location_id: int, kind: str, confidence: float, metadata: dict[str, Any]) -> None:
    day = _day(conn)
    conn.execute("UPDATE actors SET current_location_id=? WHERE id=? AND current_location_id IS NULL", (location_id, actor_id))
    conn.execute(
        """INSERT INTO actor_location_provenance(actor_id,location_id,provenance_kind,confidence,resolved_day,metadata_json)
           VALUES (?,?,?,?,?,?) ON CONFLICT(actor_id) DO UPDATE SET
           location_id=excluded.location_id,provenance_kind=excluded.provenance_kind,
           confidence=excluded.confidence,resolved_day=excluded.resolved_day,metadata_json=excluded.metadata_json""",
        (actor_id, location_id, kind, max(0.0, min(1.0, confidence)), day, _j(metadata)),
    )


def resolve_opening_institution_locations(conn: sqlite3.Connection) -> int:
    """Resolve ordinary current institutional placement without fabricating founding/travel history."""
    count = 0
    rows = conn.execute(
        """SELECT a.id,a.name,a.notes,ip.institution_kind,ip.primary_location_id,a.current_location_id
           FROM actors a JOIN institution_profiles ip ON ip.actor_id=a.id
           WHERE a.status='active' AND a.actor_type='institution' ORDER BY a.id"""
    ).fetchall()
    for r in rows:
        iid = int(r["id"])
        existing = r["current_location_id"] if r["current_location_id"] is not None else r["primary_location_id"]
        if existing is not None:
            if r["current_location_id"] is None:
                conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (int(existing), iid))
            if r["primary_location_id"] is None:
                conn.execute("UPDATE institution_profiles SET primary_location_id=? WHERE actor_id=?", (int(existing), iid))
            continue
        # Existing enterprise footprint is stronger current evidence than any geographic inference.
        er = conn.execute(
            "SELECT location_id FROM civilian_enterprises WHERE institution_actor_id=? AND location_id IS NOT NULL AND status IN ('active','strained','insolvent') ORDER BY id LIMIT 1",
            (iid,),
        ).fetchone()
        if er:
            lid, pkind, conf = int(er[0]), "existing_enterprise_footprint", .86
            state = None
        else:
            payload = _source_payload(conn, iid, "institution")
            state = payload.get("state") or payload.get("state_sphere")
            notes = str(r["notes"] or "")
            preferred = None
            # Strong named present-tense anchors in existing notes only; no new historical claim.
            for name in ("Aldergate", "Saltmere", "Cairnholt", "Crownhold", "Waymeet", "Lysmere"):
                if name.lower() in notes.lower():
                    preferred = name; break
            if preferred is None and str(r["name"]) == "Concord":
                preferred = "Cairnholt"
            if preferred is None and str(r["name"]) == "[STRUCTURAL] Greywood government":
                preferred = "Eldenfell"
            lid, pkind, conf = _working_location(conn, f"institution:{iid}:{r['name']}", state=state, preferred=preferred)
        if lid is None:
            continue
        conn.execute("UPDATE institution_profiles SET primary_location_id=COALESCE(primary_location_id,?) WHERE actor_id=?", (lid, iid))
        _record_location(conn, iid, lid, pkind, conf, {
            "opening_state": True, "non_canon_working_placement": pkind not in {"existing_enterprise_footprint","explicit_or_strong_named_anchor"},
            "history_invented": False, "state_sphere": state, "institution_kind": str(r["institution_kind"] or ""),
        })
        count += 1
    return count


def resolve_opening_character_locations(conn: sqlite3.Connection) -> dict[str, int]:
    day = _day(conn)
    before = int(conn.execute("SELECT COUNT(*) FROM actors WHERE actor_type='character' AND status='active' AND current_location_id IS NULL").fetchone()[0])
    resolved = 0
    rows = conn.execute("SELECT id,name,subtype,home_location_id FROM actors WHERE actor_type='character' AND status='active' AND current_location_id IS NULL ORDER BY id").fetchall()
    for r in rows:
        aid = int(r["id"]); lid = None; kind = ""; conf = 0.0; meta: dict[str, Any] = {"opening_state": True, "history_invented": False}
        if r["home_location_id"] is not None:
            lid, kind, conf = int(r["home_location_id"]), "existing_home_location", .96
        if lid is None:
            ir = conn.execute(
                """SELECT COALESCE(i.current_location_id,ip.primary_location_id) lid,i.id,i.name
                   FROM institution_memberships m JOIN actors i ON i.id=m.institution_actor_id
                   LEFT JOIN institution_profiles ip ON ip.actor_id=i.id
                   WHERE m.member_actor_id=? AND m.status='active' AND COALESCE(i.current_location_id,ip.primary_location_id) IS NOT NULL
                   ORDER BY CASE WHEN lower(COALESCE(m.role_text,'')) GLOB '*head*' THEN 0 ELSE 1 END,m.id LIMIT 1""",
                (aid,),
            ).fetchone()
            if ir:
                lid, kind, conf = int(ir[0]), "active_institution_current_location", .82
                meta["institution_actor_id"] = int(ir[1])
        if lid is None:
            # Explicit active teaching/travel relationships can ground current co-presence only when
            # the counterpart already has a location. This is weaker than institution/home evidence.
            tr = conn.execute(
                """SELECT b.current_location_id,b.id FROM teaching_relationships t
                   JOIN actors b ON b.id=CASE WHEN t.teacher_actor_id=? THEN t.student_actor_id ELSE t.teacher_actor_id END
                   WHERE (t.teacher_actor_id=? OR t.student_actor_id=?) AND t.status='active' AND b.current_location_id IS NOT NULL
                   ORDER BY t.id LIMIT 1""", (aid, aid, aid),
            ).fetchone()
            if tr:
                lid, kind, conf = int(tr[0]), "active_teaching_network_working_location", .58
                meta["counterpart_actor_id"] = int(tr[1])
        if lid is None:
            payload = _source_payload(conn, aid, "actor")
            state = payload.get("state_sphere")
            preferred = None
            subtype = str(r["subtype"] or "").lower()
            # Present-role location cues are used only as working placement anchors.
            for name in ("Toll’s Reach", "Waymeet", "Cairnholt", "Aldergate", "Saltmere"):
                if name.lower() in subtype:
                    preferred = name; break
            if preferred is None and any(x in subtype for x in ("wander", "road", "escort", "bounty", "contract", "travelling", "mercenary")):
                preferred = "Waymeet"
            lid, kind, conf = _working_location(conn, f"character:{aid}:{r['name']}", state=state, preferred=preferred)
            meta.update({"state_sphere": state, "non_canon_working_placement": True, "ordinary_missing_fact_completed": True})
        if lid is not None:
            _record_location(conn, aid, lid, kind, conf, meta)
            resolved += 1
    remaining = int(conn.execute("SELECT COUNT(*) FROM actors WHERE actor_type='character' AND status='active' AND current_location_id IS NULL").fetchone()[0])
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('opening_location_completion_version','1')")
    return {"opening_characters_missing_before": before, "opening_character_locations_resolved": resolved, "opening_characters_missing_after": remaining}


def _collective_authority(kind: str, name: str) -> bool:
    return kind.strip().lower() in {"federation", "financial institution", "guild", "association", "company ecosystem"} or name.strip().lower() in {"concord", "counting house"}


def _named_head(conn: sqlite3.Connection, institution_actor_id: int) -> int | None:
    payload = _source_payload(conn, institution_actor_id, "institution")
    ids = ((payload.get("continuity_core") or {}).get("leadership_ids") or [])
    for skey in ids:
        row = conn.execute("SELECT entity_id FROM source_identity_map WHERE entity_kind='actor' AND source_key=? ORDER BY id LIMIT 1", (str(skey),)).fetchone()
        if row and conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (int(row[0]),)).fetchone():
            return int(row[0])
    # Fallback only to roles that explicitly say head/leader, never merely senior master.
    row = conn.execute(
        """SELECT m.member_actor_id FROM institution_memberships m JOIN actors a ON a.id=m.member_actor_id
           WHERE m.institution_actor_id=? AND m.status='active' AND a.status='active'
           AND (lower(COALESCE(m.role_text,'')) GLOB '*head*' OR lower(COALESCE(a.subtype,'')) GLOB '* head*' OR lower(COALESCE(a.subtype,'')) GLOB '*leader*')
           ORDER BY m.id LIMIT 1""", (institution_actor_id,),
    ).fetchone()
    return int(row[0]) if row else None


def activate_institutional_authority(conn: sqlite3.Connection, resolve_selected_martial_heads: bool = True) -> dict[str, int]:
    day = _day(conn)
    counts = {"authority_slots":0,"named_incumbents":0,"collective_authority":0,"unresolved_incumbents":0,"background_heads_resolved":0}
    rows = conn.execute(
        """SELECT a.id,a.name,a.current_location_id,ip.institution_kind,ip.primary_location_id
           FROM actors a JOIN institution_profiles ip ON ip.actor_id=a.id
           WHERE a.actor_type='institution' AND a.status='active' ORDER BY a.id"""
    ).fetchall()
    for r in rows:
        iid = int(r["id"]); kind = str(r["institution_kind"] or ""); name = str(r["name"])
        slot = conn.execute("SELECT * FROM institutional_authority_slots WHERE institution_actor_id=? AND authority_key='head'", (iid,)).fetchone()
        if slot is None:
            head = _named_head(conn, iid)
            if head is not None:
                akind, incumbent = "named_incumbent", head
            elif _collective_authority(kind, name):
                akind, incumbent = "collective", None
            else:
                akind, incumbent = "unresolved_incumbent", None
            required = "Fifth" if kind.strip().lower() in MARTIAL_KINDS else None
            conn.execute(
                """INSERT INTO institutional_authority_slots(institution_actor_id,authority_key,authority_kind,incumbent_actor_id,required_stage,status,created_day,metadata_json)
                   VALUES (?,'head',?,?,?,'active',?,?)""",
                (iid, akind, incumbent, required, day, _j({"opening_state":True,"missing_name_is_not_vacancy":True,"senior_master_not_assumed_head":True})),
            )
            slot = conn.execute("SELECT * FROM institutional_authority_slots WHERE institution_actor_id=? AND authority_key='head'", (iid,)).fetchone()
        counts["authority_slots"] += 1
        akind = str(slot["authority_kind"])
        if akind == "named_incumbent": counts["named_incumbents"] += 1
        elif akind == "collective": counts["collective_authority"] += 1
        else: counts["unresolved_incumbents"] += 1

        if not resolve_selected_martial_heads or akind != "unresolved_incumbent" or kind.strip().lower() not in MARTIAL_KINDS:
            continue
        loc = r["current_location_id"] if r["current_location_id"] is not None else r["primary_location_id"]
        if loc is None:
            continue
        member_n = int(conn.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=? AND status='active'", (iid,)).fetchone()[0])
        # Reveal a pre-existing head only for institutions that already have a concrete opening
        # membership footprint. A demandless empty shell remains unresolved, never gets a conjured head.
        if member_n <= 0:
            continue
        required = "Fifth" if member_n >= 8 else "Breach"
        aid = resolve_background_person(
            conn, reason=f"opening officeholder for pre-existing {name}", location_id=int(loc),
            occupation_domains=("teacher","soldier","artisan","labor"), min_age=28, max_age=78,
            require_open_core=True, required_stage=required, command_weight=1.0, teaching_weight=.35,
            subtype=f"Head of {name}",
        )
        if aid is None and required == "Fifth":
            aid = resolve_background_person(
                conn, reason=f"opening officeholder for pre-existing {name}", location_id=int(loc),
                occupation_domains=("teacher","soldier","artisan","labor"), min_age=28, max_age=82,
                require_open_core=True, required_stage="Third", command_weight=1.0, teaching_weight=.35,
                subtype=f"Head of {name}",
            )
        if aid is None:
            continue
        conn.execute(
            "UPDATE institutional_authority_slots SET authority_kind='named_incumbent',incumbent_actor_id=?,required_stage=?,metadata_json=? WHERE id=?",
            (aid, required, _j({"opening_state":True,"resolved_from_preexisting_POPBACK":True,"population_delta":0,"senior_master_not_assumed_head":True}), int(slot["id"])),
        )
        if not conn.execute("SELECT 1 FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=? AND status='active'", (iid,aid)).fetchone():
            conn.execute(
                """INSERT INTO institution_memberships(institution_actor_id,member_actor_id,role_text,status,joined_day,provenance_json,metadata_json)
                   VALUES (?,?,'head','active',NULL,?,?)""",
                (iid, aid, _j(["pre-existing officeholder crystallized at opening"]), _j({"joined_day_unknown_preexisting":True,"population_delta":0,"note":"Pre-existing officeholder crystallized at opening; historical joining date unknown."})),
            )
        counts["background_heads_resolved"] += 1
        counts["unresolved_incumbents"] -= 1
        counts["named_incumbents"] += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('institutional_authority_activation_version','1')")
    return counts
