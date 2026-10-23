from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .continuity import create_cohort, set_institution_profile, set_resolution, upsert_continuity_core
from .civilian import add_household_member, create_household
from .health import ensure_health_profile
from .household_life import add_kinship, create_union
from . import world_calendar
from .world_package import WorldPackage, current_package

SOURCE_NAMESPACE = "caerness_seed_v1_1"
DEFAULT_CURRENT_SEED = Path(__file__).resolve().parent.parent / "game" / "seeds" / "Caerness_Initial_World_State_Seed_v1_4.json"
REJECTED_NAMES = {"malcolm vane"}

# Package in force during an import (namespace, calendar, switches).  Set by import_current_seed.
_ACTIVE: dict[str, Any] = {}


def _namespace() -> str:
    pkg = _ACTIVE.get("package")
    return pkg.seed_namespace if pkg is not None else SOURCE_NAMESPACE


def _calendar_pkg():
    pkg = _ACTIVE.get("package")
    return pkg if pkg is not None else current_package_default()


def current_package_default() -> WorldPackage:
    from .world_package import load_package, DEFAULT_PACKAGE
    return load_package(DEFAULT_PACKAGE)


def _birth_text(item: dict[str, Any]) -> Any:
    return item.get("birth_date") if item.get("birth_date") is not None else item.get("birth_date_sv")


def _death_text(item: dict[str, Any]) -> Any:
    return item.get("death_date") if item.get("death_date") is not None else item.get("death_date_sv")


def _j(v: Any) -> str:
    return json.dumps(v if v is not None else {}, ensure_ascii=False, sort_keys=True)


def _prov(v: Any) -> list[Any]:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _mapped(conn: sqlite3.Connection, source_key: str) -> tuple[str, int] | None:
    r = conn.execute(
        "SELECT entity_kind,entity_id FROM source_identity_map WHERE source_namespace=? AND source_key=?",
        (_namespace(), source_key),
    ).fetchone()
    return (str(r[0]), int(r[1])) if r else None


def _map(conn: sqlite3.Connection, source_key: str, entity_kind: str, entity_id: int, item: dict[str, Any], *, canon_status: str | None = None) -> None:
    conn.execute(
        """INSERT INTO source_identity_map(source_namespace,source_key,entity_kind,entity_id,canon_status,provenance_json,source_payload_json,created_day,updated_day)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source_namespace,source_key) DO UPDATE SET entity_kind=excluded.entity_kind,entity_id=excluded.entity_id,
             canon_status=excluded.canon_status,provenance_json=excluded.provenance_json,source_payload_json=excluded.source_payload_json,
             updated_day=excluded.updated_day""",
        (_namespace(), source_key, entity_kind, entity_id, canon_status, _j(_prov(item.get("provenance"))), _j(item), 0, 0),
    )


def _id(conn: sqlite3.Connection, source_key: str, expected: str | None = None) -> int | None:
    x = _mapped(conn, source_key)
    if not x:
        return None
    if expected and x[0] != expected:
        raise ValueError(f"{source_key} mapped as {x[0]}, expected {expected}")
    return x[1]


def _route_days(text: str | None) -> float:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text or "")]
    if not nums:
        return 1.0
    return max(0.25, sum(nums[:2]) / min(2, len(nums)))


def _ensure_place(conn: sqlite3.Connection, item: dict[str, Any]) -> int:
    existing = _id(conn, item["id"], "location")
    if existing:
        return existing
    row = conn.execute("SELECT id FROM locations WHERE name=?", (item["name"],)).fetchone()
    if row:
        lid = int(row[0])
    else:
        cur = conn.execute(
            """INSERT INTO locations(name,kind,political_owner,notes,is_canon,identity_certainty,placement_certainty,coordinate_status,source_anchor)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (item["name"], item.get("kind") or "other", item.get("state"), item.get("notes"),
             1 if item.get("canon_status") == "canonical" else 0, item.get("identity_certainty") or "UNSPECIFIED",
             item.get("placement_certainty") or "UNSPECIFIED", item.get("coordinate_status") or "OPEN_NOT_REQUIRED",
             item.get("source_anchor") or "; ".join(str(x) for x in _prov(item.get("provenance")))),
        )
        lid = int(cur.lastrowid)
    conn.execute(
        """UPDATE locations SET kind=?,political_owner=?,notes=COALESCE(?,notes),identity_certainty=?,placement_certainty=?,coordinate_status=?,source_anchor=? WHERE id=?""",
        (item.get("kind") or "other", item.get("state"), item.get("notes"), item.get("identity_certainty") or "UNSPECIFIED",
         item.get("placement_certainty") or "UNSPECIFIED", item.get("coordinate_status") or "OPEN_NOT_REQUIRED",
         item.get("source_anchor") or "; ".join(str(x) for x in _prov(item.get("provenance"))), lid),
    )
    _map(conn, item["id"], "location", lid, item, canon_status=item.get("canon_status"))
    return lid


def _ensure_institution(conn: sqlite3.Connection, item: dict[str, Any]) -> int:
    if str(item.get("name", "")).strip().lower() in REJECTED_NAMES:
        raise ValueError(f"Rejected stale name in current seed: {item['name']}")
    existing = _id(conn, item["id"], "institution")
    if existing:
        return existing
    loc = _id(conn, item.get("place_ref") or "", "location") if item.get("place_ref") else None
    row = conn.execute("SELECT id FROM actors WHERE name=?", (item["name"],)).fetchone()
    if row:
        aid = int(row[0])
        typ = conn.execute("SELECT actor_type FROM actors WHERE id=?", (aid,)).fetchone()[0]
        if typ != "institution":
            raise ValueError(f"Name collision: {item['name']} is not an institution")
    else:
        cur = conn.execute(
            "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) VALUES (?,'institution',?,?,?,?,?,0)",
            (item["name"], item.get("category"), loc, loc, "active" if item.get("status") == "active" else str(item.get("status") or "active"), item.get("notes")),
        )
        aid = int(cur.lastrowid)
    core = dict(item.get("continuity_core") or {})
    core.update({"source_id": item["id"], "current": item.get("current"), "state": item.get("state"), "place_resolution": item.get("place_resolution")})
    upsert_continuity_core(conn, "institution", aid, core, source_kind="canon", notes="Imported from current v1.1 seed; World Bible remains setting authority.")
    set_institution_profile(
        conn, aid, item.get("category") or "other", primary_location_id=loc,
        culture={"current": item.get("current"), "state": item.get("state")},
        pipeline={"seeded_member_count": len(item.get("seeded_members") or []), "named_person_policy": item.get("named_person_policy")},
        capacity={"membership_scale_band": core.get("membership_scale_band")}, economic=item.get("economic_state") or {},
        succession={"rule": core.get("succession_rule"), "leadership_source_ids": core.get("leadership_ids") or []},
        trajectory="stable", notes=item.get("notes"),
    )
    conn.execute(
        """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold)
           VALUES (?,'DORMANT',180,0.20,0.50,0,180,3)
           ON CONFLICT(actor_id) DO NOTHING""", (aid,)
    )
    set_resolution(conn, "institution", aid, "TRACKED", reason="current-canon institutional anchor", locked_min_level="STRUCTURAL", review_cadence_days=90, next_review_day=90, metadata={"source_id": item["id"]})
    _map(conn, item["id"], "institution", aid, item, canon_status=item.get("canon_status"))
    return aid


def _life_stage(item: dict[str, Any]) -> str:
    """Resolve opening life stage from chronology, not stale descriptive labels.

    Current living named people now require concrete age/birth_day chronology.  The
    household life-course owner defines the stage boundaries (<2 infant, <13 child,
    <18 youth, <60 adult, otherwise elder), so importing an older runtime label such as
    ``youth`` for a known 19-year-old creates an immediate false coming-of-age event.
    For living people the known age therefore owns the derived stage.  Historical/dead
    people may retain an explicit source label because their ``age`` is age-at-death and
    the opening runtime does not advance them.
    """
    raw = str((item.get("runtime_v1_1") or {}).get("life_stage") or "").lower()
    age = item.get("age")
    if item.get("life_status") != "living" and raw in {"infant", "child", "youth", "adult", "elder"}:
        return raw
    if age is None:
        return raw if raw in {"infant", "child", "youth", "adult", "elder"} else "adult"
    if age < 2: return "infant"
    if age < 13: return "child"
    if age < 18: return "youth"
    if age >= 60: return "elder"
    return "adult"


def _validate_person_chronology(item: dict[str, Any]) -> None:
    name = str(item.get("name") or item.get("id") or "<unnamed>")
    age = item.get("age")
    birth_day = item.get("birth_day")
    if not isinstance(age, int) or age < 0:
        raise ValueError(f"Named person {name} requires a concrete non-negative integer age")
    if not isinstance(birth_day, int):
        raise ValueError(f"Named person {name} requires an explicit opening-relative birth_day")
    cal = _calendar_pkg()
    expected_birth_date = world_calendar.birth_date_for(cal, birth_day)
    if _birth_text(item) != expected_birth_date:
        raise ValueError(f"Named person {name} birth_date_sv mismatch: expected {expected_birth_date!r}, got {_birth_text(item)!r}")
    if item.get("life_status") == "living":
        derived = max(0, (-birth_day) // 365)
        if derived != age:
            raise ValueError(f"Named person {name} age/birth_day mismatch: age={age}, derived={derived}")
    else:
        death_day = item.get("death_day")
        if not isinstance(death_day, int):
            raise ValueError(f"Historical named person {name} requires an explicit death_day")
        if death_day <= birth_day:
            raise ValueError(f"Historical named person {name} has death_day before/equal birth_day")
        expected_death_date = world_calendar.format_date(cal, death_day)
        if _death_text(item) != expected_death_date:
            raise ValueError(f"Historical named person {name} death_date_sv mismatch: expected {expected_death_date!r}, got {_death_text(item)!r}")
        derived = max(0, (death_day - birth_day) // 365)
        if derived != age:
            raise ValueError(f"Historical named person {name} age-at-death mismatch: age={age}, derived={derived}")


def _repair_existing_person_chronology(conn: sqlite3.Connection, actor_id: int, item: dict[str, Any]) -> None:
    """Apply newly-settled registry chronology without resetting mutable campaign state."""
    _validate_person_chronology(item)
    runtime = item.get("runtime_v1_1") or {}
    conn.execute(
        """UPDATE actor_life_profiles SET birth_day=?, life_stage=CASE WHEN life_stage IS NULL OR life_stage='' THEN ? ELSE life_stage END,
                   metadata_json=json_set(COALESCE(metadata_json,'{}'),'$.source_age',?,'$.age_status','KNOWN',
                                          '$.birth_date_status','KNOWN_SV','$.birth_date_sv',?,'$.age_basis',?,'$.death_day',?)
           WHERE actor_id=?""",
        (int(item["birth_day"]), _life_stage(item), int(item["age"]), _birth_text(item), item.get("age_basis") or "opening_age", item.get("death_day"), actor_id),
    )
    # Keep continuity/source payload aligned while leaving campaign-evolved facts untouched.
    row = conn.execute("SELECT core_json FROM continuity_cores WHERE entity_kind='actor' AND entity_id=?", (actor_id,)).fetchone()
    if row:
        try:
            core = json.loads(row[0] or '{}')
        except Exception:
            core = {}
        core['age'] = int(item['age']); core['age_known'] = True; core['birth_day'] = int(item['birth_day'])
        core['birth_date_sv'] = _birth_text(item)
        core['age_basis'] = item.get('age_basis') or 'opening_age'
        if item.get('death_day') is not None: core['death_day'] = int(item['death_day'])
        if _death_text(item) is not None: core['death_date_sv'] = _death_text(item)
        conn.execute("UPDATE continuity_cores SET core_json=? WHERE entity_kind='actor' AND entity_id=?", (_j(core), actor_id))


def _ensure_person(conn: sqlite3.Connection, item: dict[str, Any]) -> int:
    if str(item.get("name", "")).strip().lower() in REJECTED_NAMES:
        raise ValueError(f"Rejected stale name in current seed: {item['name']}")
    _validate_person_chronology(item)
    existing = _id(conn, item["id"], "actor")
    if existing:
        _repair_existing_person_chronology(conn, existing, item)
        _map(conn, item["id"], "actor", existing, item, canon_status=item.get("canon_status"))
        return existing
    runtime = item.get("runtime_v1_1") or {}
    loc_ref = runtime.get("current_location_ref") if runtime.get("location_status") not in {"UNKNOWN", "UNRESOLVED"} else None
    loc = _id(conn, loc_ref, "location") if loc_ref else None
    status = "active" if item.get("life_status") == "living" else "historical"
    row = conn.execute("SELECT id FROM actors WHERE name=?", (item["name"],)).fetchone()
    if row:
        aid = int(row[0])
        typ = conn.execute("SELECT actor_type FROM actors WHERE id=?", (aid,)).fetchone()[0]
        if typ != "character":
            raise ValueError(f"Name collision: {item['name']} is not a character")
    else:
        cur = conn.execute(
            "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) VALUES (?,'character',?,?,?,?,?,0)",
            (item["name"], item.get("role"), loc, loc, status, item.get("public_identity_text") or item.get("role")),
        )
        aid = int(cur.lastrowid)

    age = int(item["age"])
    birth_day = int(item["birth_day"])
    conn.execute(
        """INSERT INTO actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(actor_id) DO UPDATE SET birth_day=excluded.birth_day,life_stage=excluded.life_stage,life_status=excluded.life_status,metadata_json=excluded.metadata_json""",
        (aid, birth_day, _life_stage(item), 0, "living" if item.get("life_status") == "living" else "deceased", 0,
         _j({"source_age": age, "age_status": "KNOWN", "birth_date_status": "KNOWN_SV", "birth_date_sv": _birth_text(item), "age_basis": item.get("age_basis") or "opening_age", "death_day": item.get("death_day"), "death_date_sv": _death_text(item), "core_state": item.get("core_state"), "retirement_eligible": runtime.get("retirement_eligible")})),
    )
    if item.get("life_status") == "living":
        tier = runtime.get("resolution_tier") or ("STRATEGIC" if item.get("strategic_hint") else "DORMANT")
        if tier not in {"ACTIVE", "STRATEGIC", "DORMANT"}: tier = "DORMANT"
        cadence = 30 if tier == "ACTIVE" else (90 if tier == "STRATEGIC" else 180)
        conn.execute(
            """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(actor_id) DO UPDATE SET tier=excluded.tier,cadence_days=excluded.cadence_days,next_review_day=excluded.next_review_day""",
            (aid, tier, cadence, 0.25, 0.5, 0, cadence, 3),
        )
        longevity = str(item.get("stage") or "ordinary").lower()
        if longevity not in {"first","temper","third","breach","fifth","sixth"}: longevity = "ordinary"
        pkg = _ACTIVE.get("package")
        if pkg is not None and not pkg.systems.get("cultivation", True): longevity = "ordinary"
        ensure_health_profile(conn, aid, longevity_class=longevity)

    core = {
        "source_id": item["id"], "age": age, "age_known": True, "birth_day": birth_day, "birth_date_sv": _birth_text(item), "age_basis": item.get("age_basis") or "opening_age", "death_day": item.get("death_day"), "death_date_sv": _death_text(item), "core_state": item.get("core_state"),
        "stage": item.get("stage"), "current": item.get("current"), "long_road": item.get("long_road"),
        "state_sphere": item.get("state_sphere"), "role": item.get("role"), "training_provenance_text": item.get("training_provenance_text"),
        "public_identity_text": item.get("public_identity_text"), "training_state": runtime.get("training_state"),
    }
    upsert_continuity_core(conn, "actor", aid, core, source_kind="canon", notes="Current seed identity; competence is not derived from Stage.")
    level = "TRACKED" if item.get("life_status") == "living" else "STRUCTURAL"
    set_resolution(conn, "actor", aid, level, reason=runtime.get("resolution_reason") or "named persistent seed", locked_min_level="STRUCTURAL", review_cadence_days=90 if level == "TRACKED" else 365, next_review_day=90 if level == "TRACKED" else 365, metadata={"source_id": item["id"], "seed_tier": runtime.get("resolution_tier")})
    _map(conn, item["id"], "actor", aid, item, canon_status=item.get("canon_status"))
    return aid


def _relationship_key(idx: int, rel: dict[str, Any]) -> str:
    return f"relationship:{idx:04d}:{rel.get('type')}:{rel.get('from')}:{rel.get('to')}"


def import_current_seed(conn: sqlite3.Connection, seed_path: str | Path | None = None, package: WorldPackage | None = None) -> dict[str, Any]:
    package = package if package is not None else current_package(conn)
    _ACTIVE["package"] = package
    try:
        return _import_current_seed(conn, seed_path, package)
    finally:
        _ACTIVE.clear()


def _import_current_seed(conn: sqlite3.Connection, seed_path: str | Path | None, package: WorldPackage) -> dict[str, Any]:
    ns = package.seed_namespace
    seed_path = Path(seed_path) if seed_path is not None else package.seed_path
    current_maps = int(conn.execute("SELECT COUNT(*) FROM source_identity_map WHERE source_namespace=?", (ns,)).fetchone()[0])
    existing_actors = int(conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0])
    if existing_actors and current_maps == 0:
        raise ValueError("Refusing to import the current Caerness seed into a non-empty unmapped runtime. Use a clean database or a deliberate migration path; do not append current canon to a legacy campaign.")
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    # Canon firewall: the current engine-facing seed must be generated against the exact
    # World Bible bytes packaged as canon authority.  This prevents a newer Library master
    # and an older tested seed from silently drifting apart again.
    expected_hash = str((seed.get("meta") or {}).get("world_bible_sha256") or "").strip()
    if package.bible_sha256:
        actual_hash = hashlib.sha256(package.bible_path.read_bytes()).hexdigest()
        if not expected_hash or expected_hash != actual_hash:
            raise ValueError(f"Current {package.display_name} seed does not match {package.bible_path.parent.name}/{package.bible_path.name}; reconcile/version the seed before import")
    # Canon firewall + chronology completeness: current named registry may not contain age/birth nulls.
    for p in seed.get("persons", []):
        if str(p.get("name", "")).strip().lower() in REJECTED_NAMES:
            raise ValueError(f"Rejected stale name in current seed: {p['name']}")
        _validate_person_chronology(p)

    counts: dict[str, int] = {}
    for item in seed.get("places", []):
        _ensure_place(conn, item)
    for item in seed.get("places", []):
        if item.get("parent_ref"):
            lid, parent = _id(conn, item["id"], "location"), _id(conn, item["parent_ref"], "location")
            if lid and parent: conn.execute("UPDATE locations SET parent_location_id=? WHERE id=?", (parent, lid))
    counts["places"] = len(seed.get("places", []))

    for item in seed.get("routes", []):
        existing = _id(conn, item["id"], "route")
        if existing is None:
            def endpoint(name: str):
                row = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
                if row:
                    return row
                inst = next((x for x in seed.get("institutions", []) if x.get("name") == name and x.get("place_ref")), None)
                if inst:
                    lid = _id(conn, inst["place_ref"], "location")
                    return (lid,) if lid else None
                return None
            a = endpoint(item["from_name"])
            b = endpoint(item["to_name"])
            if not a or not b:
                raise ValueError(f"Route endpoints unresolved: {item['id']}")
            row = conn.execute("SELECT id FROM travel_routes WHERE from_location_id=? AND to_location_id=? AND route_kind='road'", (int(a[0]), int(b[0]))).fetchone()
            if row: rid = int(row[0])
            else:
                cur = conn.execute(
                    "INSERT INTO travel_routes(from_location_id,to_location_id,route_kind,base_days,status,metadata_json) VALUES (?,?,'road',?,?,?)",
                    (int(a[0]), int(b[0]), _route_days(item.get("ordinary")), "open" if item.get("status") == "working" else "restricted", _j({"ordinary":item.get("ordinary"),"courier":item.get("courier"),"cultivated_light":item.get("cultivated_light"),"coordinates_required":item.get("coordinates_required")})),
                )
                rid = int(cur.lastrowid)
            _map(conn, item["id"], "route", rid, item, canon_status=item.get("status"))
    counts["routes"] = len(seed.get("routes", []))

    for item in seed.get("institutions", []): _ensure_institution(conn, item)
    counts["institutions"] = len(seed.get("institutions", []))
    for item in seed.get("persons", []): _ensure_person(conn, item)
    counts["persons"] = len(seed.get("persons", []))

    # Memberships are explicit in person records and institution seed lists; either route is accepted, never inferred.
    for person in seed.get("persons", []):
        pid = _id(conn, person["id"], "actor")
        for iref in person.get("institutions") or []:
            iid = _id(conn, iref, "institution")
            if pid and iid:
                conn.execute(
                    """INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json)
                       VALUES (?,?, 'member',?,'active',NULL,?,?)
                       ON CONFLICT(institution_actor_id,member_actor_id,membership_kind) DO UPDATE SET role_text=excluded.role_text,provenance_json=excluded.provenance_json""",
                    (iid, pid, person.get("role"), _j(_prov(person.get("provenance"))), _j({"source_person": person["id"]})),
                )

    rel_count = 0
    spouse_pairs: list[tuple[int,int]] = []
    for idx, rel in enumerate(seed.get("relationships", []), 1):
        a, b = _id(conn, rel.get("from") or "", "actor"), _id(conn, rel.get("to") or "", "actor")
        if not a or not b: continue
        key = _relationship_key(idx, rel)
        conn.execute(
            """INSERT INTO typed_relationship_facts(source_key,actor_a_id,actor_b_id,relation_type,note,status,provenance_json,metadata_json)
               VALUES (?,?,?,?,?,'active',?,?) ON CONFLICT(source_key) DO UPDATE SET note=excluded.note,provenance_json=excluded.provenance_json,metadata_json=excluded.metadata_json""",
            (key, a, b, rel.get("type") or "other", rel.get("note"), _j(_prov(rel.get("provenance"))), _j(rel.get("runtime_v1_1") or {})),
        )
        typ = rel.get("type")
        if typ == "parent_of": add_kinship(conn, a, b, "parent", reciprocal_kind="child", metadata={"source": key})
        elif typ == "sibling": add_kinship(conn, a, b, "sibling", reciprocal_kind="sibling", metadata={"source": key})
        elif typ == "spouse":
            add_kinship(conn, a, b, "spouse", reciprocal_kind="spouse", metadata={"source": key}); spouse_pairs.append((a,b))
        rel_count += 1
    counts["relationships"] = rel_count

    household_ids: dict[str,int] = {}
    for h in seed.get("households", []):
        existing = _id(conn, h["id"], "household")
        if existing is None:
            loc = _id(conn, h.get("place_ref") or "", "location") if h.get("place_ref") else None
            name = "Household — " + h["id"].split(":",1)[-1].replace("-"," ").title()
            hid = create_household(conn, name, location_id=loc, metadata={"source_id":h["id"],"basis":h.get("basis"),"status":h.get("status"),"marriage_or_kinship_state":h.get("marriage_or_kinship_state"),"economic_state":h.get("economic_state"),"economic_resolution":"STRUCTURAL_ONLY" if h.get("economic_state") in (None,"NOT_SEPARATELY_QUANTIFIED") else "QUANTIFIED"})
            _map(conn, h["id"], "household", hid, h, canon_status=h.get("status"))
        else: hid = existing
        household_ids[h["id"]] = hid
        for pref in h.get("member_refs") or []:
            aid = _id(conn, pref, "actor")
            if aid:
                add_household_member(conn, hid, aid, role="member", authority=20, dependency=20)
                conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (hid, aid))
    # Materialize only explicit spouse relationships; attach to an explicit household if both are there.
    for a,b in spouse_pairs:
        hid = None
        row = conn.execute("SELECT hm1.household_id FROM household_members hm1 JOIN household_members hm2 ON hm2.household_id=hm1.household_id WHERE hm1.actor_id=? AND hm2.actor_id=? AND hm1.status='active' AND hm2.status='active' LIMIT 1", (a,b)).fetchone()
        if row: hid = int(row[0])
        if conn.execute("SELECT 1 FROM actor_life_profiles WHERE actor_id=? AND life_status='living'", (a,)).fetchone() and conn.execute("SELECT 1 FROM actor_life_profiles WHERE actor_id=? AND life_status='living'", (b,)).fetchone():
            create_union(conn, a, b, household_id=hid, family_plan={"mode":"UNRESOLVED","auto_children":False,"source":"explicit spouse relationship"})
    counts["households"] = len(seed.get("households", []))

    for c in seed.get("cohorts", []):
        existing = _id(conn, c["id"], "cohort")
        if existing is None:
            pop = c.get("population_working", c.get("count_working"))
            name = c.get("polity") or f"{c.get('stage','Unknown')} Stage working cohort"
            name = f"{name} — {c.get('type','cohort')}"
            cid = create_cohort(conn, name, c.get("type") or "other", population_estimate=int(pop) if pop is not None else None, shared_context=c, historical_summary="Current v1.1 structural population anchor", status="active", is_canon=False)
            _map(conn, c["id"], "cohort", cid, c, canon_status=c.get("canon_status"))
        else: cid=existing
        # Aggregate cohort anchors are fixed structural state, not autonomous resolution
        # candidates.  They intentionally have no review clock.
        set_resolution(conn, "cohort", cid, "STRUCTURAL", reason="aggregate current-canon population anchor", locked_min_level="STRUCTURAL", metadata={"source_id":c["id"]})
    counts["cohorts"] = len(seed.get("cohorts", []))

    for target in (seed.get("latent_population_controls") or {}).get("named_layer_targets", []):
        iid = _id(conn, target.get("institution_ref") or "", "institution")
        source_key = f"latent-scope:{target.get('institution_ref')}"
        conn.execute(
            """INSERT INTO latent_population_scopes(source_key,scope_kind,scope_id,archetype,population_estimate,minimum_named_layer,opening_named_count,crystallization_rule,constraints_json,historical_context_json,status,created_day,updated_day)
               VALUES (?,'institution',?,'institutional population',NULL,?,?,?,?,?,'active',0,0)
               ON CONFLICT(source_key) DO UPDATE SET scope_id=excluded.scope_id,minimum_named_layer=excluded.minimum_named_layer,opening_named_count=excluded.opening_named_count,crystallization_rule=excluded.crystallization_rule""",
            (source_key, iid, target.get("minimum_named_layer"), target.get("opening_named_living"), target.get("crystallization_rule"), _j({"population_count_intentionally_unknown":True}), _j({"rule":(seed.get("latent_population_controls") or {}).get("rule")})),
        )
    counts["latent_scopes"] = len((seed.get("latent_population_controls") or {}).get("named_layer_targets", []))

    for cl in seed.get("claims", []):
        conn.execute(
            """INSERT INTO world_claims(source_key,claim_type,claim_text,confidence_label,canon_status,provenance_json,metadata_json,status,created_day,updated_day)
               VALUES (?,?,?,?,?,?,?,'active',0,0)
               ON CONFLICT(source_key) DO UPDATE SET claim_text=excluded.claim_text,confidence_label=excluded.confidence_label,metadata_json=excluded.metadata_json""",
            (cl["id"], cl.get("type") or "claim", cl.get("text") or "", cl.get("confidence"), cl.get("canon_status"), _j(_prov(cl.get("provenance"))), _j({"carrier_types":cl.get("carrier_types") or []})),
        )
        claim_id = int(conn.execute("SELECT id FROM world_claims WHERE source_key=?", (cl["id"],)).fetchone()[0])
        _map(conn, cl["id"], "claim", claim_id, cl, canon_status=cl.get("canon_status"))
        for pref in cl.get("subjects") or []:
            aid = _id(conn, pref, "actor")
            if aid: conn.execute("INSERT OR IGNORE INTO world_claim_subjects(claim_id,actor_id) VALUES (?,?)", (claim_id,aid))
        for field, state in (("origin_place_refs","origin"),("known_at_opening","known_at_opening")):
            for pref in cl.get(field) or []:
                lid = _id(conn, pref, "location")
                if lid: conn.execute("INSERT OR IGNORE INTO world_claim_locations(claim_id,location_id,knowledge_state) VALUES (?,?,?)", (claim_id,lid,state))
    counts["claims"] = len(seed.get("claims", []))

    for p in seed.get("processes", []):
        ent = _id(conn, p.get("entity") or "", "institution")
        conn.execute(
            """INSERT INTO canon_process_anchors(source_key,process_type,entity_actor_id,status,facts_json,cadence,metadata_json)
               VALUES (?,?,?,?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET status=excluded.status,facts_json=excluded.facts_json,cadence=excluded.cadence,metadata_json=excluded.metadata_json""",
            (p["id"], p.get("type") or "other", ent, p.get("status") or "unknown", _j(p.get("facts") or []), p.get("cadence"), _j(p)),
        )
        pid = int(conn.execute("SELECT id FROM canon_process_anchors WHERE source_key=?", (p["id"],)).fetchone()[0])
        _map(conn, p["id"], "process", pid, p, canon_status=p.get("status"))
    counts["processes"] = len(seed.get("processes", []))

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_seed_namespace',?)", (ns,))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_seed_version','1.4')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_seed_world_bible_sha256',?)", (expected_hash,))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('civil_calendar_version','sv_624_fixed_365_v1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('named_person_chronology_contract','explicit_age_birth_day_and_sv_date_required')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_seed_import_complete','1')")
    return {"source_namespace": ns, **counts}
