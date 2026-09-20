from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .continuity import add_cohort_member, create_cohort, create_latent_entity, set_institution_profile, set_resolution
from .db import ROOT
from .expertise import set_actor_competence
from .health import ensure_health_profile
from .household_life import set_demographic_cohort, set_life_profile
from .player import set_player
from .politics import configure_polity, set_territorial_control

DEFAULT_SEED = ROOT / "canon" / "core_seed_v2.json"

_STAGE_LONGEVITY = {
    "First": "first", "Temper": "temper", "Third": "third", "Breach": "breach", "Fifth": "fifth", "Sixth": "sixth"
}
_STAGE_COMPETENCE = {"First": 25, "Temper": 40, "Third": 56, "Breach": 71, "Fifth": 85, "Sixth": 95}
_STAGE_TIER = {"First": "DORMANT", "Temper": "DORMANT", "Third": "DORMANT", "Breach": "STRATEGIC", "Fifth": "STRATEGIC", "Sixth": "STRATEGIC"}
# Operational review cadence for the shallow named registry, not a canon statement about
# how often people "make decisions." Specialized domain clocks (health, politics, education,
# travel, etc.) can still wake or alter them between these coarse personal reviews.
_STAGE_CADENCE = {"First": 360, "Temper": 270, "Third": 180, "Breach": 120, "Fifth": 90, "Sixth": 60}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _review_phase(actor_id: int, cadence: int, bucket_days: int = 30) -> int:
    """Spread bootstrap reviews across coarse buckets without creating a unique daily frontier.

    This preserves deterministic staggering and avoids hundreds of distinct scheduler wakeups per
    year in a realistically inhabited seed. Cadences remain actor-specific and authoritative.
    """
    cadence = max(1, int(cadence)); bucket_days = max(1, min(int(bucket_days), cadence))
    slot = (int(actor_id) * 17) % cadence
    return 1 + (slot // bucket_days) * bucket_days


def load_seed(path: str | Path | None = None, *, verification_canon_path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path or DEFAULT_SEED)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("seed_id") or not data.get("seed_version"):
        raise ValueError("Invalid Caerness campaign seed manifest")
    # Production/default callers always verify against the current canonical retrieval source.
    # A caller may provide an explicit historical canon only for a pinned regression fixture;
    # this never changes or blesses the packaged production seed.
    source = Path(verification_canon_path) if verification_canon_path is not None else ROOT / "canon" / "world_bible_current.docx"
    expected = str(data.get("world_bible_sha256") or "").strip()
    if source.exists() and expected:
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("Campaign seed manifest does not match canon/world_bible_current.docx; regenerate the seed before bootstrapping")
    return data


def _record_seed_entity(conn: sqlite3.Connection, run_id: int, kind: str, entity_id: int, seed_key: str,
                        status: str, source_ref: str, metadata: dict[str, Any] | None = None) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO campaign_seed_entities(
               seed_run_id,entity_kind,entity_id,seed_key,source_status,source_ref,metadata_json
           ) VALUES (?,?,?,?,?,?,?)""",
        (run_id, kind, entity_id, seed_key, status, source_ref, json.dumps(metadata or {}, sort_keys=True)),
    )


def _ensure_location(conn: sqlite3.Connection, item: dict[str, Any], ids: dict[str, int]) -> int:
    parent_id = ids.get(str(item.get("parent") or ""))
    conn.execute(
        """INSERT INTO locations(name,kind,parent_location_id,notes,is_canon)
           VALUES (?,?,?,?,1)
           ON CONFLICT(name) DO UPDATE SET
             kind=excluded.kind,
             parent_location_id=COALESCE(excluded.parent_location_id,locations.parent_location_id),
             notes=CASE WHEN locations.notes IS NULL OR locations.notes='' THEN excluded.notes ELSE locations.notes END,
             is_canon=1""",
        (item["name"], item["kind"], parent_id, item.get("notes")),
    )
    return int(conn.execute("SELECT id FROM locations WHERE name=?", (item["name"],)).fetchone()[0])


def _ensure_institution(conn: sqlite3.Connection, item: dict[str, Any], loc_ids: dict[str, int]) -> int:
    primary = loc_ids.get(str(item.get("primary_location") or "")) or loc_ids.get("Hearthlands")
    row = conn.execute("SELECT id,actor_type FROM actors WHERE name=?", (item["name"],)).fetchone()
    if row and str(row["actor_type"]) != "institution":
        raise ValueError(f"Campaign seed name collision: {item['name']} already exists as a character")
    if not row:
        cur = conn.execute(
            """INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo)
               VALUES (?,'institution',?,?,?,'active',?,0)""",
            (item["name"], item.get("subtype") or item["kind"], primary, primary,
             f"Campaign bootstrap seed ({item.get('status','working')})."),
        )
        actor_id = int(cur.lastrowid)
    else:
        actor_id = int(row["id"])
        conn.execute(
            "UPDATE actors SET subtype=COALESCE(subtype,?),home_location_id=COALESCE(home_location_id,?),current_location_id=COALESCE(current_location_id,?) WHERE id=?",
            (item.get("subtype") or item["kind"], primary, primary, actor_id),
        )
    set_institution_profile(
        conn, actor_id, item["kind"], primary_location_id=primary,
        culture={"seed_status": item.get("status", "working")},
        pipeline={"bootstrap_seed": True}, capacity={"bootstrap_seed": True},
        trajectory="stable", notes="Seeded from the current World Bible; exact unestablished details remain latent.",
    )
    conn.execute(
        """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day)
           VALUES (?,?,90,0.2,0.55,0,?)
           ON CONFLICT(actor_id) DO NOTHING""",
        (actor_id, "STRATEGIC", _review_phase(actor_id, 90)),
    )
    set_resolution(conn, "actor", actor_id, "TRACKED", reason="campaign bootstrap institution", source_kind="admin",
                   review_cadence_days=90, next_review_day=_review_phase(actor_id, 90),
                   metadata={"bootstrap_seed": True, "seed_status": item.get("status", "working")})
    return actor_id


def _ensure_named_character(conn: sqlite3.Connection, item: dict[str, Any], institution_ids: dict[str, int],
                            loc_ids: dict[str, int]) -> int:
    name = str(item["name"])
    stage = str(item["stage"])
    aff = item.get("affiliation")
    sphere = item.get("sphere")
    if aff and aff in institution_ids:
        row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (institution_ids[aff],)).fetchone()
        location_id = int(row[0]) if row and row[0] is not None else loc_ids.get("Hearthlands")
    elif sphere == "Long Road":
        location_id = loc_ids.get("Waymeet") or loc_ids.get("Hearthlands")
    elif sphere == "Independent Hollow":
        location_id = loc_ids.get("Eastern Hearth") or loc_ids.get("Hearthlands")
    elif aff == "House Greaves":
        location_id = loc_ids.get("Silent Peak") or loc_ids.get("Hearthlands")
    else:
        location_id = loc_ids.get("Hearthlands")

    existing = conn.execute("SELECT id,actor_type FROM actors WHERE name=?", (name,)).fetchone()
    if existing and str(existing["actor_type"]) != "character":
        raise ValueError(f"Campaign seed name collision: {name} already exists as an institution")
    notes = f"{stage} Stage. {item.get('role') or ''} Working registry seed; deeper biography remains provisional unless separately established."
    subtype = f"{stage}-stage martial artist"
    if existing:
        actor_id = int(existing["id"])
        conn.execute("UPDATE actors SET subtype=COALESCE(subtype,?),home_location_id=COALESCE(home_location_id,?),current_location_id=COALESCE(current_location_id,?),notes=COALESCE(notes,?) WHERE id=?",
                     (subtype, location_id, location_id, notes, actor_id))
    else:
        cur = conn.execute(
            """INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo)
               VALUES (?,'character',?,?,?,'active',?,0)""",
            (name, subtype, location_id, location_id, notes),
        )
        actor_id = int(cur.lastrowid)

    age = int(item["age"])
    birth_day = item.get("birth_day")
    if not isinstance(birth_day, int):
        raise ValueError(f"Named campaign seed character {name} requires explicit birth_day")
    derived_age = max(0, (_day(conn) - int(birth_day)) // 365)
    if derived_age != age:
        raise ValueError(f"Named campaign seed character {name} age/birth_day mismatch: age={age}, derived={derived_age}")
    set_life_profile(conn, actor_id, birth_day=int(birth_day),
                     metadata={"bootstrap_seed": True, "registry_status": item.get("status", "working"),
                               "cultivation_stage": stage, "affiliation": aff, "sphere": sphere})
    ensure_health_profile(conn, actor_id, longevity_class=_STAGE_LONGEVITY[stage], baseline_health=80,
                          metadata={"bootstrap_stage": stage, "source": "working registry"})
    # Internal competence calibration gives systems a usable starting point without treating Stage as destiny.
    jitter = ((sum(ord(c) for c in name) % 9) - 4)
    set_actor_competence(conn, actor_id, "martial", max(5, min(100, _STAGE_COMPETENCE[stage] + jitter)),
                         source_kind="campaign",
                         training={"basis": "working registry Stage calibration"},
                         notes="Operational bootstrap calibration; not a canon claim that equal Stage implies equal skill.")
    tier = _STAGE_TIER[stage]
    cadence = _STAGE_CADENCE[stage]
    conn.execute(
        """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day)
           VALUES (?,?,?,?,?,0,?)
           ON CONFLICT(actor_id) DO UPDATE SET tier=excluded.tier,cadence_days=excluded.cadence_days,
             volatility=excluded.volatility,agency=excluded.agency""",
        (actor_id, tier, cadence, 0.25, 0.65, _review_phase(actor_id, cadence)),
    )
    level = "TRACKED" if stage in {"Sixth", "Fifth", "Breach"} else "STRUCTURAL"
    set_resolution(conn, "actor", actor_id, level, reason="working named registry bootstrap", source_kind="admin",
                   review_cadence_days=cadence, next_review_day=_review_phase(actor_id, cadence),
                   metadata={"bootstrap_seed": True, "stage": stage, "registry_status": item.get("status", "working")})
    return actor_id


def bootstrap_campaign(conn: sqlite3.Connection, *, seed_path: str | Path | None = None,
                       verification_canon_path: str | Path | None = None) -> dict[str, Any]:
    """Apply the versioned World-Bible-derived production seed.

    The seed intentionally does not invent the open detailed road map, exact feast calendar,
    outer-kingdom martial systems, or a player character. Those remain campaign choices/latent detail.
    """
    manifest = load_seed(seed_path, verification_canon_path=verification_canon_path)
    seed_id = str(manifest["seed_id"]); seed_version = int(manifest["seed_version"])
    existing = conn.execute("SELECT * FROM campaign_seed_runs WHERE seed_id=? AND seed_version=? AND status='applied'",
                            (seed_id, seed_version)).fetchone()
    if existing:
        return json.loads(existing["summary_json"] or "{}") | {"idempotent": True, "seed_run_id": int(existing["id"])}

    # Apply atomically even when callers catch an exception and continue using the same
    # connection. Failed/partial bootstrap must never leave half a world behind.
    conn.execute("SAVEPOINT campaign_bootstrap")
    conn.execute(
        """INSERT INTO campaign_seed_runs(seed_id,seed_version,source_name,source_hash,status,summary_json,finished_at)
           VALUES (?,?,?,?, 'applying','{}',NULL)
           ON CONFLICT(seed_id,seed_version) DO UPDATE SET
             source_name=excluded.source_name,source_hash=excluded.source_hash,status='applying',
             summary_json='{}',started_at=CURRENT_TIMESTAMP,finished_at=NULL""",
        (seed_id, seed_version, manifest.get("source_name"), manifest.get("world_bible_sha256")),
    )
    run_id = int(conn.execute(
        "SELECT id FROM campaign_seed_runs WHERE seed_id=? AND seed_version=?", (seed_id, seed_version)
    ).fetchone()[0])
    try:
        loc_ids: dict[str, int] = {}
        # First pass creates roots; second pass repairs parents once every named location exists.
        for item in manifest.get("locations", []):
            loc_ids[item["name"]] = _ensure_location(conn, item | {"parent": None}, loc_ids)
        for item in manifest.get("locations", []):
            if item.get("parent"):
                pid = loc_ids.get(str(item["parent"]))
                if pid:
                    conn.execute("UPDATE locations SET parent_location_id=? WHERE id=?", (pid, loc_ids[item["name"]]))
            _record_seed_entity(conn, run_id, "location", loc_ids[item["name"]], f"location:{item['name']}",
                                item.get("status", "working"), "World Bible geography/site tables", item)

        institution_ids: dict[str, int] = {}
        for item in manifest.get("institutions", []):
            aid = _ensure_institution(conn, item, loc_ids)
            institution_ids[item["name"]] = aid
            _record_seed_entity(conn, run_id, "actor", aid, f"institution:{item['name']}", item.get("status", "working"),
                                "World Bible institutional architecture", item)

        # Underheaven political sovereignty is seeded only where the current Bible states it directly.
        imperial_actor = institution_ids.get("Underheaven Empire")
        if imperial_actor:
            polity_id = configure_polity(conn, imperial_actor, polity_kind="empire", succession_method="unsettled",
                                         legitimacy=75, stability=70, administrative_capacity=80, military_capacity=80,
                                         review_cadence_days=90,
                                         metadata={"bootstrap_seed": True, "exact_borders_map_dependent": True})
            imperial_control_names = {
                "Hearthlands", "Crownlands", "Central Hearth", "Eastern Hearth", "Fellmarch", "Ashgrave",
                "Crownhold", "Highford", "Cairnholt", "Rivermoor", "Redford", "Blackfen", "Stonecross", "Mirehold",
                "Aldergate", "Mapleford", "Talonkeep", "Eastwatch", "Waymeet", "Oakridge", "Britterwatch", "Verenwood", "Greywatch"
            }
            for name in imperial_control_names:
                if name in loc_ids:
                    set_territorial_control(conn, polity_id, loc_ids[name], control_kind="direct", legitimacy=75, integration=75,
                                            reason="Seeded from current World Bible sovereignty statement")

        # Windmere and Dunmoor are directly established as independent kingdoms. Their detailed
        # institutions, rulers, borders beyond the named kingdom locations, and martial systems
        # remain deliberately uncrystallized.
        for kingdom_name in ("Windmere", "Dunmoor"):
            kaid = institution_ids.get(kingdom_name)
            kloc = loc_ids.get(kingdom_name)
            if kaid and kloc:
                kpid = configure_polity(conn, kaid, polity_kind="kingdom", succession_method="unsettled",
                                       legitimacy=65, stability=65, administrative_capacity=55, military_capacity=55,
                                       review_cadence_days=120,
                                       metadata={"bootstrap_seed": True, "details_banked": True})
                set_territorial_control(conn, kpid, kloc, control_kind="direct", legitimacy=70, integration=70,
                                        reason="Seeded from current World Bible independent-kingdom statement")

        # Affiliation cohorts let shallow registry people belong to institutions without inventing offices.
        cohort_ids: dict[str, int] = {}
        for name, aid in institution_ids.items():
            cohort_ids[name] = create_cohort(conn, f"{name} — living registry", "institution_registry",
                                             institution_actor_id=aid, start_day=0, status="active",
                                             shared_context={"bootstrap_seed": True, "source": "working named registry"})
        for category in ("Independent Unsworn", "Independent Hollow", "Long Road", "Independent local"):
            cohort_ids[category] = create_cohort(conn, f"{category} — living registry", "social_registry",
                                                 location_id=loc_ids.get("Hearthlands"), start_day=0, status="active",
                                                 shared_context={"bootstrap_seed": True, "category": category})

        character_ids: dict[str, int] = {}
        stage_named_counts: dict[str, int] = {}
        for item in manifest.get("named_characters", []):
            aid = _ensure_named_character(conn, item, institution_ids, loc_ids)
            character_ids[item["name"]] = aid
            stage_named_counts[item["stage"]] = stage_named_counts.get(item["stage"], 0) + 1
            key = item.get("affiliation") or item.get("sphere")
            if key and key in cohort_ids:
                add_cohort_member(conn, cohort_ids[key], aid, role=item.get("role"), joined_day=None,
                                  significance=0.8 if item["stage"] in {"Sixth", "Fifth"} else 0.45,
                                  notes="Working named registry seed")
            _record_seed_entity(conn, run_id, "actor", aid, f"character:{item['name']}", "working",
                                f"World Bible working registry table {item.get('source_table')}", item)

        # Population calibration: source midpoint is from the World Bible; age split and vital rates are explicit campaign assumptions.
        demo = manifest.get("demography") or {}
        hearth_id = loc_ids.get("Hearthlands")
        demographic_ids: list[int] = []
        if hearth_id:
            total = float(demo.get("hearthlands_midpoint") or 0)
            distribution = demo.get("age_distribution_assumption") or {}
            # annual_birth_pressure is an absolute annual inflow attached to the 0-4 cohort in the existing aggregate model.
            annual_births = round(total * 0.016, 2)
            for band, share in distribution.items():
                cid = set_demographic_cohort(
                    conn, hearth_id, "hearth_population", band, total * float(share),
                    annual_birth_pressure=annual_births if band == "0_4" else 0,
                    annual_migration_rate=0,
                    metadata={"bootstrap_seed": True, "source_population_midpoint": True,
                              "age_distribution": "campaign_assumption_v1", "annual_births": "campaign_assumption_v1"},
                )
                demographic_ids.append(cid)
                _record_seed_entity(conn, run_id, "demographic_cohort", cid, f"demography:hearth_population:{band}", "campaign",
                                    "v0.26 bootstrap assumption anchored to World Bible Hearthlands midpoint",
                                    {"age_band": band, "share": share, "population_midpoint": total})

            # Stage counts remain latent structural population after subtracting named working-registry seeds.
            for stage, count in (demo.get("hearth_stage_counts") or {}).items():
                remainder = max(1, int(count) - int(stage_named_counts.get(stage, 0)))
                lid = create_latent_entity(conn, "character", f"{stage}-stage Hearth cultivator",
                                           location_id=hearth_id, count_estimate=remainder,
                                           constraints={"cultivation_stage": stage, "scope": "Hearth"},
                                           historical_context={"source": "World Bible working global Stage distribution"},
                                           notes="Aggregate latent pool; not exact in-world census knowledge.")
                _record_seed_entity(conn, run_id, "latent_entity", lid, f"latent:hearth:{stage}", "working",
                                    "World Bible working Stage distribution", {"stage": stage, "count_estimate": remainder})

        summary = {
            "seed_id": seed_id, "seed_version": seed_version, "seed_run_id": run_id,
            "locations": len(loc_ids), "institutions": len(institution_ids), "named_characters": len(character_ids),
            "demographic_cohorts": len(demographic_ids), "latent_stage_pools": len((manifest.get("demography") or {}).get("hearth_stage_counts") or {}),
            "player_created": False,
            "open_boundaries_preserved": ["detailed Hearth routes", "exact feast calendar", "outer-kingdom martial systems", "player identity"],
        }
        conn.execute("UPDATE campaign_seed_runs SET status='applied',finished_at=CURRENT_TIMESTAMP,summary_json=? WHERE id=?",
                     (json.dumps(summary, sort_keys=True), run_id))
        conn.execute(
            """INSERT INTO campaign_setup_state(id,seed_id,seed_version,bootstrap_complete,player_setup_complete,setup_notes_json)
               VALUES (1,?,?,1,0,?)
               ON CONFLICT(id) DO UPDATE SET seed_id=excluded.seed_id,seed_version=excluded.seed_version,
                 bootstrap_complete=1,setup_notes_json=excluded.setup_notes_json,updated_at=CURRENT_TIMESTAMP""",
            (seed_id, seed_version, json.dumps({"source_hash": manifest.get("world_bible_sha256")}, sort_keys=True)),
        )
        conn.execute("RELEASE SAVEPOINT campaign_bootstrap")
        return summary
    except Exception as exc:
        conn.execute("ROLLBACK TO SAVEPOINT campaign_bootstrap")
        conn.execute("RELEASE SAVEPOINT campaign_bootstrap")
        # Recording a failed attempt is safe after the world-state rollback. If the outer
        # transaction itself is later rolled back, this diagnostic row naturally rolls back too.
        conn.execute(
            """INSERT INTO campaign_seed_runs(seed_id,seed_version,source_name,source_hash,status,finished_at,summary_json)
               VALUES (?,?,?,?, 'failed',CURRENT_TIMESTAMP,?)
               ON CONFLICT(seed_id,seed_version) DO UPDATE SET status='failed',finished_at=CURRENT_TIMESTAMP,
                 summary_json=excluded.summary_json""",
            (seed_id, seed_version, manifest.get("source_name"), manifest.get("world_bible_sha256"),
             json.dumps({"error": str(exc)}, sort_keys=True)),
        )
        raise


def create_player_character(conn: sqlite3.Connection, name: str, *, start_location: str = "Cairnholt",
                            age: int | None = None, subtype: str = "player character",
                            campaign_name: str = "Caerness Campaign") -> int:
    name = str(name).strip()
    if not name:
        raise ValueError("Player name is required")
    if conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
        raise ValueError("An actor with that name already exists")
    loc = conn.execute("SELECT id FROM locations WHERE name=?", (start_location,)).fetchone()
    if not loc:
        raise ValueError("Unknown start location. Bootstrap the campaign first or choose an existing location.")
    if age is not None and (age < 0 or age > 200):
        raise ValueError("Player age must be between 0 and 200 when supplied")
    cur = conn.execute(
        """INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo)
           VALUES (?,'character',?,?,?,'active','Player-created campaign actor.',0)""",
        (name, subtype, int(loc[0]), int(loc[0])),
    )
    actor_id = int(cur.lastrowid)
    if age is not None:
        set_life_profile(conn, actor_id, birth_day=_day(conn) - int(age) * 365,
                         metadata={"source": "player_setup"})
    else:
        set_life_profile(conn, actor_id, metadata={"source": "player_setup", "age_unset": True})
    ensure_health_profile(conn, actor_id, metadata={"source": "player_setup"})
    conn.execute(
        """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,forced_tier)
           VALUES (?,'ACTIVE',1,0.25,1.0,0,1,'ACTIVE')""", (actor_id,)
    )
    set_resolution(conn, "actor", actor_id, "SCENE", reason="player character", source_kind="player",
                   review_cadence_days=1, next_review_day=1, locked_min_level="ACTIVE",
                   metadata={"player_character": True})
    set_player(conn, actor_id, campaign_name)
    conn.execute("UPDATE campaign_setup_state SET player_setup_complete=1,updated_at=CURRENT_TIMESTAMP WHERE id=1")
    return actor_id


def bootstrap_status(conn: sqlite3.Connection) -> dict[str, Any]:
    setup = conn.execute("SELECT * FROM campaign_setup_state WHERE id=1").fetchone()
    latest = conn.execute("SELECT * FROM campaign_seed_runs ORDER BY id DESC LIMIT 1").fetchone()
    counts = {
        "locations": int(conn.execute("SELECT COUNT(*) FROM locations WHERE is_canon=1").fetchone()[0]),
        "named_characters": int(conn.execute("SELECT COUNT(*) FROM actors WHERE actor_type='character' AND is_demo=0").fetchone()[0]),
        "institutions": int(conn.execute("SELECT COUNT(*) FROM actors WHERE actor_type='institution' AND is_demo=0").fetchone()[0]),
        "latent_entities": int(conn.execute("SELECT COUNT(*) FROM latent_entities WHERE status='latent'").fetchone()[0]),
        "aggregate_population": float(conn.execute("SELECT COALESCE(SUM(population),0) FROM demographic_cohorts").fetchone()[0]),
    }
    return {
        "setup": dict(setup) if setup else None,
        "latest_seed": dict(latest) if latest else None,
        "counts": counts,
        "default_seed": str(DEFAULT_SEED),
    }
