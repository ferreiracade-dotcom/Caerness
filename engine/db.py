from __future__ import annotations

import math
import os
import random
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "caerness.db"
# Compatibility only: callers should use database_path() rather than assuming this path.
DB_PATH = DEFAULT_DB_PATH
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_BACKUP_DIR = ROOT / "game" / "campaign_01" / "backups"
ENGINE_VERSION = "0.60.0"
SCHEMA_VERSION = 104


def _running_tests() -> bool:
    if os.environ.get("CAERNESS_TEST_MODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    try:
        parts = [p.lower() for p in Path(sys.argv[0]).parts]
        return "tests" in parts or Path(sys.argv[0]).name.startswith("test_")
    except Exception:
        return False


def database_path() -> Path:
    configured = os.environ.get("CAERNESS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    if _running_tests():
        root = Path(tempfile.gettempdir()) / "caerness_engine_tests"
        root.mkdir(parents=True, exist_ok=True)
        stem = Path(sys.argv[0]).stem or "tests"
        return root / f"{stem}_{os.getpid()}.db"
    return DEFAULT_DB_PATH


def backup_dir() -> Path:
    configured = os.environ.get("CAERNESS_BACKUP_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if database_path() == DEFAULT_DB_PATH:
        return DEFAULT_BACKUP_DIR
    return database_path().parent / "backups"


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _looks_like_caerness(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    probe = sqlite3.connect(path)
    try:
        return probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_state'").fetchone() is not None
    except sqlite3.DatabaseError:
        return False
    finally:
        probe.close()


def _infer_schema_version_from_engine(value: str | None) -> int:
    if not value:
        return 0
    try:
        parts = str(value).lstrip("v").split(".")
        if len(parts) >= 2 and int(parts[0]) == 0:
            return max(0, int(parts[1]))
        return 0
    except Exception:
        return 0


def _existing_schema_version(path: Path) -> int:
    if not _looks_like_caerness(path):
        return 0
    probe = sqlite3.connect(path)
    try:
        if not _has_table(probe, "engine_meta"):
            return 1
        row = probe.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()
        if row:
            try:
                return int(row[0])
            except Exception:
                pass
        row = probe.execute("SELECT value FROM engine_meta WHERE key='engine_version'").fetchone()
        return _infer_schema_version_from_engine(row[0] if row else None) or 1
    finally:
        probe.close()


def _backup_raw(path: Path, label: str, *, keep: int = 20) -> str:
    if not _looks_like_caerness(path):
        raise ValueError("Source does not look like a Caerness database.")
    dest_dir = backup_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_label = "" if not label else "_" + "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:80]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_path = dest_dir / f"caerness_{stamp}{safe_label}.db"
    src = sqlite3.connect(path)
    dest = sqlite3.connect(dest_path)
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()
    backups = sorted(dest_dir.glob("caerness_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if keep > 0:
        for old in backups[keep:]:
            old.unlink(missing_ok=True)
    return str(dest_path)


def _model_requests_accepts_local(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='model_requests'").fetchone()
    if not row or not row[0]:
        return True
    return "'local'" in str(row[0])


def _migrate_model_requests_for_local(conn: sqlite3.Connection) -> None:
    """Rebuild the legacy model_requests CHECK constraint when required."""
    if _model_requests_accepts_local(conn):
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript(
            """
            ALTER TABLE model_requests RENAME TO model_requests_v06;
            CREATE TABLE model_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day INTEGER NOT NULL,
                task_type TEXT NOT NULL CHECK (task_type IN ('action_interpretation','npc_decision','narration')),
                provider TEXT NOT NULL CHECK (provider IN ('chatgpt','claude','generic','local')),
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','responded','applied','cancelled','error')),
                target_kind TEXT,
                target_id INTEGER,
                input_json TEXT NOT NULL,
                response_raw TEXT,
                response_json TEXT,
                packet_path TEXT,
                applied_summary TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                responded_at TEXT,
                applied_at TEXT
            );
            INSERT INTO model_requests(
                id,day,task_type,provider,status,target_kind,target_id,input_json,response_raw,response_json,
                packet_path,applied_summary,created_at,responded_at,applied_at
            )
            SELECT id,day,task_type,provider,status,target_kind,target_id,input_json,response_raw,response_json,
                   packet_path,applied_summary,created_at,responded_at,applied_at
            FROM model_requests_v06;
            DROP TABLE model_requests_v06;
            CREATE INDEX IF NOT EXISTS idx_model_requests_status ON model_requests(status,task_type,id);
            CREATE INDEX IF NOT EXISTS idx_model_requests_target ON model_requests(target_kind,target_id,id);
            """
        )
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _seed_resolution_from_profiles(conn: sqlite3.Connection) -> None:
    mapping = {"ACTIVE": "ACTIVE", "STRATEGIC": "TRACKED", "DORMANT": "STRUCTURAL"}
    rows = conn.execute(
        """SELECT sp.actor_id,sp.tier,sp.cadence_days,sp.next_review_day,a.actor_type
           FROM simulation_profiles sp JOIN actors a ON a.id=sp.actor_id"""
    ).fetchall()
    for row in rows:
        actor_type = str(row["actor_type"] or "")
        if actor_type == "character":
            entity_kind = "actor"
        elif actor_type == "institution":
            entity_kind = "institution"
        else:
            # Simulation profiles can exist for other structural actor rows, but the
            # resolution controller owns only characters and institutions.  Do not create
            # permanently overdue resolution records for unsupported kinds.
            continue
        entity_id = int(row["actor_id"])
        # Do not use INSERT OR IGNORE on this AUTOINCREMENT table: SQLite can advance
        # sqlite_sequence even when the uniqueness conflict causes the row to be ignored.
        # Migration timing would then perturb later surrogate IDs and break restart replay.
        if conn.execute(
            "SELECT 1 FROM entity_resolution WHERE entity_kind=? AND entity_id=?",
            (entity_kind, entity_id),
        ).fetchone():
            continue
        conn.execute(
            """INSERT INTO entity_resolution(
                   entity_kind,entity_id,resolution_level,reason,review_cadence_days,next_review_day,last_changed_day,metadata_json
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (entity_kind, entity_id, mapping[str(row["tier"])], "migrated from v0.7 simulation profile",
             int(row["cadence_days"]), int(row["next_review_day"]), 0, '{"scheduler_source":"simulation_profiles"}'),
        )


def _ensure_player_embodiment(conn: sqlite3.Connection) -> None:
    player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    if not player or player[0] is None:
        return
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    conn.execute(
        """INSERT OR IGNORE INTO character_embodiment(
               actor_id,voice_json,temperament_json,values_json,habits_json,social_json,
               relationship_style_json,expression_policy_json,current_state_json,development_json,
               source_kind,updated_day
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (int(player[0]), '{"register":"natural","verbosity":"contextual","directness":"contextual"}', '{}', '{}', '{}',
         '{"formality":"contextual","social_confidence":"unknown"}', '{}',
         '{"autonomous_expression_min_confidence":0.8,"ask_below_confidence":0.7,"max_autonomous_stakes":2,"allow_low_stakes_expression":true,"major_commitments_require_player":true,"avoid_caricature":true,"prefer_small_expression_over_irreversible_action":true}',
         '{}', '{"behavioral_inertia":true,"change_requires_evidence":true}', 'campaign', day),
    )


def _seed_competence_domains(conn: sqlite3.Connection) -> None:
    default_domains = [
        ("martial", "Martial practice"), ("command", "Command"), ("politics", "Politics"),
        ("administration", "Administration"), ("commerce", "Commerce"), ("medicine", "Medicine"),
        ("vein_mending", "Vein-Mending"), ("craft", "Craft"), ("architecture", "Architecture"),
        ("scholarship", "Scholarship"), ("social", "Social judgment"), ("law", "Law"),
        ("art_culture", "Art and culture"), ("regional", "Regional knowledge"),
    ]
    for key, name in default_domains:
        conn.execute(
            "INSERT OR IGNORE INTO competence_domains(domain_key,name,description,default_visibility) VALUES (?,?,NULL,'private')",
            (key, name),
        )


def _seed_business_vocab(conn: sqlite3.Connection) -> None:
    from .business import seed_business_archetypes
    seed_business_archetypes(conn)


def _seed_religion_vocab(conn: sqlite3.Connection) -> None:
    from .religion import seed_religious_traditions
    seed_religious_traditions(conn)


def _migration_7(conn: sqlite3.Connection) -> None:
    _migrate_model_requests_for_local(conn)
    conn.execute("UPDATE runtime_config SET realtime_calendar_progression=0 WHERE id=1")


def _migration_8(conn: sqlite3.Connection) -> None:
    _seed_resolution_from_profiles(conn)


def _migration_10(conn: sqlite3.Connection) -> None:
    _ensure_player_embodiment(conn)


def _migration_11(conn: sqlite3.Connection) -> None:
    _seed_competence_domains(conn)


def _migration_18(conn: sqlite3.Connection) -> None:
    _seed_business_vocab(conn)


def _migration_21(conn: sqlite3.Connection) -> None:
    _seed_religion_vocab(conn)


def _migration_26(conn: sqlite3.Connection) -> None:
    # These fields are mirrors. Rebuild them from their authoritative owners.
    conn.execute(
        """UPDATE locations SET political_owner=(
               SELECT a.name FROM territorial_control tc
               JOIN political_polities p ON p.id=tc.controller_polity_id
               JOIN actors a ON a.id=p.institution_actor_id
               WHERE tc.location_id=locations.id
           ) WHERE EXISTS(SELECT 1 FROM territorial_control tc WHERE tc.location_id=locations.id)"""
    )
    conn.execute(
        """UPDATE player_state SET current_location_id=(
               SELECT a.current_location_id FROM actors a WHERE a.id=player_state.player_actor_id
           ), updated_day=(SELECT current_day FROM world_state WHERE id=1)
           WHERE id=1 AND player_actor_id IS NOT NULL"""
    )
    conn.execute("INSERT OR IGNORE INTO campaign_setup_state(id,bootstrap_complete,player_setup_complete) VALUES (1,0,0)")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('ownership_rules_version','1')")




def _migration_27(conn: sqlite3.Connection) -> None:
    """Broaden resolution/continuity to institutions and install the current-canon bridge.

    schema.sql creates the new v0.27 support tables idempotently before this function runs.
    Existing v0.26 saves still need two CHECK-constrained tables rebuilt because
    CREATE TABLE IF NOT EXISTS cannot widen an existing CHECK constraint.
    """
    def table_sql(name: str) -> str:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        return str(row[0] or "") if row else ""

    if "'institution'" not in table_sql("continuity_cores"):
        conn.executescript(
            """
            ALTER TABLE continuity_cores RENAME TO continuity_cores_v26;
            CREATE TABLE continuity_cores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_kind TEXT NOT NULL CHECK (entity_kind IN ('actor','institution','location','possession','thread','cohort')),
                entity_id INTEGER NOT NULL,
                core_type TEXT NOT NULL DEFAULT 'general',
                core_json TEXT NOT NULL DEFAULT '{}',
                schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version >= 1),
                historical_depth TEXT NOT NULL DEFAULT 'present' CHECK (historical_depth IN ('present','shallow','developed','deep')),
                last_crystallized_day INTEGER,
                last_updated_day INTEGER NOT NULL DEFAULT 0,
                source_kind TEXT NOT NULL DEFAULT 'engine' CHECK (source_kind IN ('canon','campaign','engine','admin')),
                notes TEXT,
                UNIQUE(entity_kind,entity_id,core_type)
            );
            INSERT INTO continuity_cores
            SELECT * FROM continuity_cores_v26;
            DROP TABLE continuity_cores_v26;
            CREATE INDEX IF NOT EXISTS idx_continuity_entity ON continuity_cores(entity_kind,entity_id);
            CREATE INDEX IF NOT EXISTS idx_continuity_depth ON continuity_cores(historical_depth,last_updated_day);
            """
        )

    if "'institution'" not in table_sql("entity_resolution"):
        conn.executescript(
            """
            ALTER TABLE entity_resolution RENAME TO entity_resolution_v26;
            CREATE TABLE entity_resolution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_kind TEXT NOT NULL CHECK (entity_kind IN ('actor','institution','location','possession','thread','cohort')),
                entity_id INTEGER NOT NULL,
                resolution_level TEXT NOT NULL CHECK (resolution_level IN ('SCENE','ACTIVE','TRACKED','STRUCTURAL','LATENT')),
                previous_level TEXT CHECK (previous_level IN ('SCENE','ACTIVE','TRACKED','STRUCTURAL','LATENT')),
                reason TEXT,
                promoted_by_kind TEXT,
                promoted_by_id INTEGER,
                review_cadence_days INTEGER CHECK (review_cadence_days IS NULL OR review_cadence_days >= 1),
                next_review_day INTEGER,
                last_changed_day INTEGER NOT NULL DEFAULT 0,
                locked_min_level TEXT CHECK (locked_min_level IN ('SCENE','ACTIVE','TRACKED','STRUCTURAL','LATENT')),
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(entity_kind,entity_id)
            );
            INSERT INTO entity_resolution
            SELECT * FROM entity_resolution_v26;
            DROP TABLE entity_resolution_v26;
            CREATE INDEX IF NOT EXISTS idx_entity_resolution_level
            ON entity_resolution(resolution_level,next_review_day,entity_kind,entity_id);
            """
        )

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_canon_bridge_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('resolution_controller_version','1')")


def _migration_28(conn: sqlite3.Connection) -> None:
    # Phase 3 domain actions reuse the v0.27 autonomous_action_attempts ledger and
    # authoritative subsystem tables; no parallel domain truth is introduced.
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('domain_action_bridge_version','1')")


def _migration_29(conn: sqlite3.Connection) -> None:
    # Logistics owns cargo-in-transit and destination commercial stock.
    # Goods are removed from production inventory exactly once at dispatch and
    # materialize at destination stock exactly once on delivery.
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('commercial_logistics_version','1')")


def _migration_30(conn: sqlite3.Connection) -> None:
    # Current-canon aggregate economic substrate. Numerical quantities are campaign
    # calibration; activation code keeps explicit source/basis metadata.
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('economic_substrate_version','1')")


def _migration_31(conn: sqlite3.Connection) -> None:
    # Prose-geography completion: place identity, relative containment and exact placement
    # are separate.  Coordinates remain intentionally absent until the prose graph is stable.
    cols={str(r[1]) for r in conn.execute("PRAGMA table_info(locations)").fetchall()}
    additions=[
        ("identity_certainty", "TEXT NOT NULL DEFAULT 'UNSPECIFIED'"),
        ("placement_certainty", "TEXT NOT NULL DEFAULT 'UNSPECIFIED'"),
        ("coordinate_status", "TEXT NOT NULL DEFAULT 'OPEN_NOT_REQUIRED'"),
        ("source_anchor", "TEXT"),
    ]
    for name,decl in additions:
        if name not in cols:
            conn.execute(f"ALTER TABLE locations ADD COLUMN {name} {decl}")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('prose_geography_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_seed_version','1.2')")


def _migration_32(conn: sqlite3.Connection) -> None:
    # Cultivation is causal body/training history, not an annual promotion roll or hidden final Stage.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cultivation_profiles (
        actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        core_state TEXT NOT NULL DEFAULT 'Unknown' CHECK (core_state IN ('Open-Core','Closed-Core','Damaged-Core','Destroyed-Core','Unknown')),
        current_stage TEXT CHECK (current_stage IN ('First','Temper','Third','Breach','Fifth','Sixth') OR current_stage IS NULL),
        active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0,1)),
        vessel_adaptation REAL NOT NULL DEFAULT 0 CHECK (vessel_adaptation BETWEEN 0 AND 100),
        realization_integration REAL NOT NULL DEFAULT 0 CHECK (realization_integration BETWEEN 0 AND 100),
        training_effort REAL NOT NULL DEFAULT 50 CHECK (training_effort BETWEEN 0 AND 100),
        resource_access REAL NOT NULL DEFAULT 50 CHECK (resource_access BETWEEN 0 AND 100),
        teacher_support REAL NOT NULL DEFAULT 0 CHECK (teacher_support BETWEEN 0 AND 100),
        injury_constraint REAL NOT NULL DEFAULT 0 CHECK (injury_constraint BETWEEN 0 AND 100),
        observed_stage_days INTEGER NOT NULL DEFAULT 0 CHECK (observed_stage_days>=0),
        plateau_days INTEGER NOT NULL DEFAULT 0 CHECK (plateau_days>=0),
        last_realization_day INTEGER,
        last_breakthrough_attempt_day INTEGER,
        last_review_day INTEGER NOT NULL DEFAULT 0,
        next_review_day INTEGER NOT NULL DEFAULT 30,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','retired','incapacitated','ended')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_cultivation_due ON cultivation_profiles(active,status,next_review_day,actor_id);
    CREATE TABLE IF NOT EXISTS cultivation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        history_kind TEXT NOT NULL CHECK (history_kind IN ('opening_observation','practice_review','plateau','realization_opportunity','breakthrough_attempt','breakthrough_success','breakthrough_failure','rupture','retirement','resume')),
        stage_before TEXT,
        stage_after TEXT,
        summary TEXT NOT NULL,
        vessel_snapshot REAL,
        realization_snapshot REAL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_cultivation_history_actor ON cultivation_history(actor_id,day,id);
    CREATE TABLE IF NOT EXISTS realization_anchors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        anchor_kind TEXT NOT NULL,
        source_kind TEXT NOT NULL,
        source_id INTEGER,
        weight REAL NOT NULL DEFAULT 1 CHECK (weight>0),
        description TEXT,
        consumed_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_realization_actor ON realization_anchors(actor_id,consumed_day,day,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('cultivation_realization_version','1')")


def _migration_33(conn: sqlite3.Connection) -> None:
    # Elixir physiology keeps fuel, bodily maturation and Realization distinct. Batch truth and
    # public/commercial claims are separate so forged provenance never rewrites actual history.
    cols={str(r[1]) for r in conn.execute("PRAGMA table_info(cultivation_profiles)").fetchall()}
    for name,decl in [
        ("core_capacity", "REAL NOT NULL DEFAULT 0 CHECK (core_capacity>=0)"),
        ("current_reserve", "REAL NOT NULL DEFAULT 0 CHECK (current_reserve>=0)"),
        ("sediment_burden", "REAL NOT NULL DEFAULT 0 CHECK (sediment_burden BETWEEN 0 AND 100)"),
    ]:
        if name not in cols:
            conn.execute(f"ALTER TABLE cultivation_profiles ADD COLUMN {name} {decl}")
    conn.executescript(r"""
    CREATE TABLE IF NOT EXISTS elixir_supply_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        product_grade TEXT NOT NULL CHECK (product_grade IN ('refined','high_grade')),
        default_refinement_quality REAL NOT NULL CHECK (default_refinement_quality BETWEEN 0 AND 100),
        default_sediment_risk REAL NOT NULL CHECK (default_sediment_risk BETWEEN 0 AND 100),
        provenance_standard REAL NOT NULL DEFAULT 50 CHECK (provenance_standard BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','inactive')),
        source_basis TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(enterprise_id,product_grade)
    );
    CREATE TABLE IF NOT EXISTS elixir_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_key TEXT NOT NULL UNIQUE,
        product_grade TEXT NOT NULL CHECK (product_grade IN ('raw_root','refined','high_grade')),
        source_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        refiner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        producer_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        usable_current_per_unit REAL NOT NULL CHECK (usable_current_per_unit>0),
        refinement_quality REAL NOT NULL CHECK (refinement_quality BETWEEN 0 AND 100),
        sediment_risk REAL NOT NULL CHECK (sediment_risk BETWEEN 0 AND 100),
        remaining_units REAL NOT NULL CHECK (remaining_units>=0),
        created_day INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','depleted','seized','destroyed')),
        actual_provenance_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_elixir_batches_status ON elixir_batches(status,product_grade,id);
    CREATE TABLE IF NOT EXISTS elixir_batch_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL REFERENCES elixir_batches(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        claimant_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        claim_kind TEXT NOT NULL,
        claim_text TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 50 CHECK (confidence BETWEEN 0 AND 100),
        truth_status TEXT NOT NULL DEFAULT 'unknown' CHECK (truth_status IN ('unknown','supported','false','disputed')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_elixir_claims_batch ON elixir_batch_claims(batch_id,day,id);
    CREATE TABLE IF NOT EXISTS elixir_exposures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL REFERENCES elixir_batches(id) ON DELETE RESTRICT,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        units_consumed REAL NOT NULL CHECK (units_consumed>0),
        assimilated_current REAL NOT NULL DEFAULT 0 CHECK (assimilated_current>=0),
        reserve_gain REAL NOT NULL DEFAULT 0 CHECK (reserve_gain>=0),
        vessel_gain REAL NOT NULL DEFAULT 0 CHECK (vessel_gain>=0),
        sediment_gain REAL NOT NULL DEFAULT 0 CHECK (sediment_gain>=0),
        rupture_condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_elixir_exposure_actor ON elixir_exposures(actor_id,day,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('elixir_physiology_version','1')")


def _migration_34(conn: sqlite3.Connection) -> None:
    # v0.34 is a behavior/coverage completion pass over existing authoritative tables.
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('family_civilian_consequences_version','1')")


def _migration_35(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS martial_challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposer_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        recipient_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        interaction_id INTEGER REFERENCES interactions(id) ON DELETE SET NULL,
        duel_engagement_id INTEGER REFERENCES combat_engagements(id) ON DELETE SET NULL,
        terms_kind TEXT NOT NULL DEFAULT 'controlled' CHECK (terms_kind IN ('controlled','first_blood','submission','weapon_limited','lethal')),
        lethal INTEGER NOT NULL DEFAULT 0 CHECK (lethal IN (0,1)),
        status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','accepted','declined','active','resolved','cancelled')),
        created_day INTEGER NOT NULL,
        next_review_day INTEGER NOT NULL,
        resolved_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK (proposer_actor_id<>recipient_actor_id)
    );
    CREATE INDEX IF NOT EXISTS idx_martial_challenge_status ON martial_challenges(status,created_day,id);

    CREATE TABLE IF NOT EXISTS tournament_series (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        series_key TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        recurrence_days INTEGER NOT NULL DEFAULT 365 CHECK (recurrence_days>0),
        next_registration_day INTEGER NOT NULL,
        registration_lead_days INTEGER NOT NULL DEFAULT 60 CHECK (registration_lead_days>=0),
        event_duration_days INTEGER NOT NULL DEFAULT 21 CHECK (event_duration_days>0),
        cycle_index INTEGER NOT NULL DEFAULT 0 CHECK (cycle_index>=0),
        convergence_every INTEGER NOT NULL DEFAULT 5 CHECK (convergence_every>=2),
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','ended')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_tournament_series_due ON tournament_series(status,next_registration_day,id);

    CREATE TABLE IF NOT EXISTS tournament_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        series_id INTEGER NOT NULL REFERENCES tournament_series(id) ON DELETE CASCADE,
        event_kind TEXT NOT NULL CHECK (event_kind IN ('annual','convergence','circuit','other')),
        name TEXT NOT NULL,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        registration_day INTEGER NOT NULL,
        start_day INTEGER NOT NULL,
        end_day INTEGER NOT NULL,
        next_review_day INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'registration' CHECK (status IN ('registration','active','resolved','cancelled')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(series_id,start_day)
    );
    CREATE INDEX IF NOT EXISTS idx_tournament_events_due ON tournament_events(status,next_review_day,id);

    CREATE TABLE IF NOT EXISTS tournament_fields (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES tournament_events(id) ON DELETE CASCADE,
        field_key TEXT NOT NULL CHECK (field_key IN ('open','rising','companies','grand_open','rising_court','company_contest','masters_invitation')),
        simulation_mode TEXT NOT NULL DEFAULT 'individual' CHECK (simulation_mode IN ('individual','structural')),
        capacity INTEGER NOT NULL DEFAULT 8 CHECK (capacity>=0),
        status TEXT NOT NULL DEFAULT 'registration' CHECK (status IN ('registration','active','resolved','structural','cancelled')),
        round_index INTEGER NOT NULL DEFAULT 0 CHECK (round_index>=0),
        champion_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(event_id,field_key)
    );

    CREATE TABLE IF NOT EXISTS tournament_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES tournament_events(id) ON DELETE CASCADE,
        field_id INTEGER NOT NULL REFERENCES tournament_fields(id) ON DELETE CASCADE,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        origin_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        seed_score REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'registered' CHECK (status IN ('registered','arrived','active','eliminated','champion','withdrawn')),
        registered_day INTEGER NOT NULL,
        eliminated_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(event_id,actor_id)
    );
    CREATE INDEX IF NOT EXISTS idx_tournament_entries_field ON tournament_entries(field_id,status,seed_score DESC,id);

    CREATE TABLE IF NOT EXISTS tournament_bouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES tournament_events(id) ON DELETE CASCADE,
        field_id INTEGER NOT NULL REFERENCES tournament_fields(id) ON DELETE CASCADE,
        round_index INTEGER NOT NULL,
        actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        duel_engagement_id INTEGER REFERENCES combat_engagements(id) ON DELETE SET NULL,
        winner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','active','resolved','cancelled')),
        scheduled_day INTEGER NOT NULL,
        resolved_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(actor_a_id<>actor_b_id)
    );
    CREATE INDEX IF NOT EXISTS idx_tournament_bouts_status ON tournament_bouts(event_id,field_id,status,round_index,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('autonomous_combat_tournament_version','1')")


Migration = tuple[str, str, Callable[[sqlite3.Connection], None] | None]

def _migration_36(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS spectacle_books (
        id INTEGER PRIMARY KEY AUTOINCREMENT, book_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
        institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE, book_kind TEXT NOT NULL CHECK (book_kind IN ('network_branch','independent_market')),
        legal_profile TEXT NOT NULL DEFAULT 'tolerated' CHECK (legal_profile IN ('licensed','tolerated','mixed')),
        reliability REAL NOT NULL DEFAULT 70 CHECK (reliability BETWEEN 0 AND 100), information_quality REAL NOT NULL DEFAULT 55 CHECK (information_quality BETWEEN 0 AND 100),
        margin_rate REAL NOT NULL DEFAULT 0.08 CHECK (margin_rate BETWEEN 0 AND 0.4), status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','closed')), metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_spectacle_books_location ON spectacle_books(location_id,status,id);
    CREATE TABLE IF NOT EXISTS prizefight_markets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, market_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        market_kind TEXT NOT NULL DEFAULT 'prize_hall' CHECK (market_kind IN ('prize_hall','back_room','pit','private_club')), legality TEXT NOT NULL DEFAULT 'licensed' CHECK (legality IN ('licensed','tolerated','unlicensed','criminal')),
        coercion_profile TEXT NOT NULL DEFAULT 'voluntary' CHECK (coercion_profile IN ('voluntary','mixed','coercive')), cadence_days INTEGER NOT NULL DEFAULT 30 CHECK (cadence_days>=7),
        next_card_day INTEGER NOT NULL, latent_pool_id INTEGER REFERENCES latent_entities(id) ON DELETE SET NULL, pool_size INTEGER NOT NULL DEFAULT 20 CHECK (pool_size>=4),
        public_form REAL NOT NULL DEFAULT 50 CHECK (public_form BETWEEN 0 AND 100), injury_load REAL NOT NULL DEFAULT 5 CHECK (injury_load BETWEEN 0 AND 100),
        champion_streak INTEGER NOT NULL DEFAULT 0 CHECK (champion_streak>=0), champion_profile_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','closed')), metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_prizefight_markets_due ON prizefight_markets(status,next_card_day,id);
    CREATE TABLE IF NOT EXISTS prizefight_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT, market_id INTEGER NOT NULL REFERENCES prizefight_markets(id) ON DELETE CASCADE, scheduled_day INTEGER NOT NULL, resolved_day INTEGER,
        status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','resolved','cancelled')), bout_count INTEGER NOT NULL DEFAULT 0 CHECK (bout_count>=0),
        attendance_index REAL NOT NULL DEFAULT 50 CHECK (attendance_index BETWEEN 0 AND 100), gross_purse REAL NOT NULL DEFAULT 0 CHECK (gross_purse>=0), metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(market_id,scheduled_day)
    );
    CREATE INDEX IF NOT EXISTS idx_prizefight_cards_status ON prizefight_cards(status,scheduled_day,id);
    CREATE TABLE IF NOT EXISTS prizefight_bouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, card_id INTEGER NOT NULL REFERENCES prizefight_cards(id) ON DELETE CASCADE, bout_index INTEGER NOT NULL,
        public_form_a REAL NOT NULL CHECK (public_form_a BETWEEN 0 AND 100), public_form_b REAL NOT NULL CHECK (public_form_b BETWEEN 0 AND 100),
        true_form_a REAL NOT NULL CHECK (true_form_a BETWEEN 0 AND 100), true_form_b REAL NOT NULL CHECK (true_form_b BETWEEN 0 AND 100),
        winner_side TEXT NOT NULL CHECK (winner_side IN ('A','B')), injury_a REAL NOT NULL DEFAULT 0 CHECK (injury_a BETWEEN 0 AND 100), injury_b REAL NOT NULL DEFAULT 0 CHECK (injury_b BETWEEN 0 AND 100),
        metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(card_id,bout_index)
    );
    CREATE TABLE IF NOT EXISTS betting_markets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, market_key TEXT NOT NULL UNIQUE, book_id INTEGER NOT NULL REFERENCES spectacle_books(id) ON DELETE CASCADE,
        source_kind TEXT NOT NULL CHECK (source_kind IN ('tournament_bout','prizefight_card')), source_id INTEGER NOT NULL, location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        opened_day INTEGER NOT NULL, close_day INTEGER NOT NULL, settled_day INTEGER, status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','settled','cancelled')),
        outcome_a_key TEXT NOT NULL, outcome_b_key TEXT NOT NULL, public_probability_a REAL NOT NULL CHECK (public_probability_a BETWEEN 0.02 AND 0.98),
        decimal_odds_a REAL NOT NULL CHECK (decimal_odds_a>=1.01), decimal_odds_b REAL NOT NULL CHECK (decimal_odds_b>=1.01), handle REAL NOT NULL DEFAULT 0 CHECK (handle>=0),
        stake_share_a REAL NOT NULL DEFAULT 0.5 CHECK (stake_share_a BETWEEN 0 AND 1), payout REAL NOT NULL DEFAULT 0 CHECK (payout>=0), book_result REAL NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_betting_markets_status ON betting_markets(status,source_kind,source_id,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('spectacle_economy_version','1');
    """)

def _migration_37(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS underworld_institution_profiles (
        institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        primary_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        operating_model TEXT NOT NULL,
        legal_fronts_json TEXT NOT NULL DEFAULT '[]',
        criminal_activities_json TEXT NOT NULL DEFAULT '[]',
        continuity_depth REAL NOT NULL DEFAULT 50 CHECK (continuity_depth BETWEEN 0 AND 100),
        hidden_exposure REAL NOT NULL DEFAULT 0 CHECK (hidden_exposure BETWEEN 0 AND 100),
        corrupt_access REAL NOT NULL DEFAULT 0 CHECK (corrupt_access BETWEEN 0 AND 100),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        next_review_day INTEGER NOT NULL DEFAULT 30,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','dormant','ended')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_profiles_due ON underworld_institution_profiles(status,next_review_day,institution_actor_id);

    CREATE TABLE IF NOT EXISTS underworld_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        subject_kind TEXT NOT NULL CHECK (subject_kind IN ('enterprise','institution','smuggling_operation','actor','shadow_link')),
        subject_id INTEGER NOT NULL,
        evidence_kind TEXT NOT NULL,
        visibility TEXT NOT NULL DEFAULT 'hidden' CHECK (visibility IN ('hidden','local','public')),
        strength REAL NOT NULL DEFAULT 0 CHECK (strength BETWEEN 0 AND 100),
        source_kind TEXT NOT NULL,
        source_id INTEGER,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','discredited','resolved')),
        created_day INTEGER NOT NULL,
        updated_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(source_kind,source_id,evidence_kind)
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_evidence_subject ON underworld_evidence(subject_kind,subject_id,status,visibility,id);
    CREATE INDEX IF NOT EXISTS idx_underworld_evidence_location ON underworld_evidence(location_id,status,visibility,id);

    CREATE TABLE IF NOT EXISTS smuggling_operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_key TEXT UNIQUE,
        organizer_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        destination_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE,
        quantity REAL NOT NULL CHECK (quantity>0),
        origin_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        destination_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        current_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        current_route_id INTEGER REFERENCES travel_routes(id) ON DELETE SET NULL,
        segment_due_day INTEGER,
        next_review_day INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'in_transit' CHECK (status IN ('in_transit','stalled','delivered','seized','cancelled')),
        violation_kind TEXT NOT NULL,
        concealment REAL NOT NULL DEFAULT 60 CHECK (concealment BETWEEN 0 AND 100),
        evidence_score REAL NOT NULL DEFAULT 0 CHECK (evidence_score BETWEEN 0 AND 100),
        detected_day INTEGER,
        detected_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        started_day INTEGER NOT NULL,
        arrived_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_smuggling_due ON smuggling_operations(status,next_review_day,id);
    CREATE INDEX IF NOT EXISTS idx_smuggling_organizer ON smuggling_operations(organizer_institution_actor_id,status,id);

    CREATE TABLE IF NOT EXISTS law_enforcement_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_key TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        authority_kind TEXT NOT NULL,
        capacity REAL NOT NULL DEFAULT 50 CHECK (capacity BETWEEN 0 AND 100),
        integrity REAL NOT NULL DEFAULT 60 CHECK (integrity BETWEEN 0 AND 100),
        corruption_pressure REAL NOT NULL DEFAULT 20 CHECK (corruption_pressure BETWEEN 0 AND 100),
        inspection_focus REAL NOT NULL DEFAULT 50 CHECK (inspection_focus BETWEEN 0 AND 100),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        next_review_day INTEGER NOT NULL DEFAULT 30,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','inactive')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_law_profiles_due ON law_enforcement_profiles(status,next_review_day,location_id,id);

    CREATE TABLE IF NOT EXISTS law_enforcement_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL REFERENCES law_enforcement_profiles(id) ON DELETE CASCADE,
        subject_kind TEXT NOT NULL CHECK (subject_kind IN ('smuggling_operation','enterprise','institution','actor')),
        subject_id INTEGER NOT NULL,
        allegation_kind TEXT NOT NULL,
        evidence_score REAL NOT NULL DEFAULT 0 CHECK (evidence_score BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'monitoring' CHECK (status IN ('monitoring','open','actionable','referred','closed')),
        opened_day INTEGER NOT NULL,
        last_review_day INTEGER NOT NULL,
        next_review_day INTEGER NOT NULL,
        closed_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(profile_id,subject_kind,subject_id,allegation_kind)
    );
    CREATE INDEX IF NOT EXISTS idx_law_cases_due ON law_enforcement_cases(status,next_review_day,profile_id,id);

    CREATE TABLE IF NOT EXISTS law_enforcement_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL REFERENCES law_enforcement_cases(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        action_kind TEXT NOT NULL CHECK (action_kind IN ('inquiry','inspection','referral')),
        evidence_score REAL NOT NULL CHECK (evidence_score BETWEEN 0 AND 100),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(case_id,action_kind)
    );
    CREATE INDEX IF NOT EXISTS idx_law_actions_case ON law_enforcement_actions(case_id,day,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_ecology_version','1');
    """)


def _migration_38(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS hollow_practice_profiles (
        actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        hollow_status TEXT NOT NULL CHECK (hollow_status IN ('formal_coven','independent','associated')),
        coven_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        accepts_extraction INTEGER NOT NULL DEFAULT 0 CHECK (accepts_extraction IN (0,1)),
        practiced_extraction INTEGER CHECK (practiced_extraction IN (0,1) OR practiced_extraction IS NULL),
        mantle_eligibility TEXT NOT NULL DEFAULT 'unknown' CHECK (mantle_eligibility IN ('eligible','ineligible','unknown')),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','former','deceased')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_hollow_profiles_coven ON hollow_practice_profiles(coven_institution_actor_id,status,actor_id);

    CREATE TABLE IF NOT EXISTS hollow_extraction_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day INTEGER NOT NULL,
        practitioner_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        source_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        context_kind TEXT NOT NULL DEFAULT 'practice' CHECK (context_kind IN ('practice','combat','rite','other')),
        requested_current REAL NOT NULL CHECK (requested_current>0),
        transferred_current REAL NOT NULL DEFAULT 0 CHECK (transferred_current>=0),
        source_reserve_before REAL NOT NULL DEFAULT 0 CHECK (source_reserve_before>=0),
        source_reserve_after REAL NOT NULL DEFAULT 0 CHECK (source_reserve_after>=0),
        recipient_reserve_before REAL NOT NULL DEFAULT 0 CHECK (recipient_reserve_before>=0),
        recipient_reserve_after REAL NOT NULL DEFAULT 0 CHECK (recipient_reserve_after>=0),
        status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('completed','partial','failed')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(practitioner_actor_id <> source_actor_id)
    );
    CREATE INDEX IF NOT EXISTS idx_hollow_extraction_actor ON hollow_extraction_events(practitioner_actor_id,day,id);

    CREATE TABLE IF NOT EXISTS grand_coven_succession_state (
        institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        inheritor_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        foremost_heir_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        succession_status TEXT NOT NULL DEFAULT 'open' CHECK (succession_status IN ('open','contested','sealed','vacant')),
        mantle_sealed INTEGER NOT NULL DEFAULT 0 CHECK (mantle_sealed IN (0,1)),
        sealed_day INTEGER,
        transfer_available INTEGER NOT NULL DEFAULT 1 CHECK (transfer_available IN (0,1)),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        next_review_day INTEGER NOT NULL DEFAULT 90,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_grand_coven_succession_due ON grand_coven_succession_state(next_review_day,succession_status,institution_actor_id);

    CREATE TABLE IF NOT EXISTS grand_coven_heirs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        claim_kind TEXT NOT NULL CHECK (claim_kind IN ('recognized_heir','rival_heir','carrion_riser','other_exalted')),
        formal_status TEXT NOT NULL DEFAULT 'potential' CHECK (formal_status IN ('potential','recognized','pressed','withdrawn','settled','ineligible','deceased')),
        teaching_access REAL NOT NULL DEFAULT 0 CHECK (teaching_access BETWEEN 0 AND 100),
        authority_support REAL NOT NULL DEFAULT 0 CHECK (authority_support BETWEEN 0 AND 100),
        martial_credibility REAL NOT NULL DEFAULT 0 CHECK (martial_credibility BETWEEN 0 AND 100),
        political_support REAL NOT NULL DEFAULT 0 CHECK (political_support BETWEEN 0 AND 100),
        current_choice INTEGER NOT NULL DEFAULT 0 CHECK (current_choice IN (0,1)),
        created_day INTEGER NOT NULL DEFAULT 0,
        updated_day INTEGER NOT NULL DEFAULT 0,
        mantle_eligible INTEGER NOT NULL DEFAULT 1 CHECK (mantle_eligible IN (0,1)),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(institution_actor_id,actor_id)
    );
    CREATE INDEX IF NOT EXISTS idx_grand_coven_heirs ON grand_coven_heirs(institution_actor_id,formal_status,current_choice,id);

    CREATE TABLE IF NOT EXISTS grand_coven_power_brokers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        role_kind TEXT NOT NULL CHECK (role_kind IN ('deep_court_elder','senior_power','hall_lord','order_command','keeper','family_line','other')),
        institutional_weight REAL NOT NULL DEFAULT 0 CHECK (institutional_weight BETWEEN 0 AND 100),
        stance TEXT NOT NULL DEFAULT 'uncommitted' CHECK (stance IN ('supports','opposes','uncommitted','fractured')),
        supported_heir_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        created_day INTEGER NOT NULL DEFAULT 0,
        updated_day INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(institution_actor_id,actor_id,role_kind)
    );
    CREATE INDEX IF NOT EXISTS idx_grand_coven_power_brokers ON grand_coven_power_brokers(institution_actor_id,role_kind,stance,id);

    CREATE TABLE IF NOT EXISTS grand_coven_mantle_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        event_kind TEXT NOT NULL CHECK (event_kind IN ('recognition','claim_pressed','choice_changed','sealed','passing','accession','ascension','sudden_death_transition')),
        actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        other_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        current_transferred REAL NOT NULL DEFAULT 0 CHECK (current_transferred>=0),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_grand_coven_mantle_events ON grand_coven_mantle_events(institution_actor_id,day,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('hollow_succession_version','1');
    """)


def _migration_39(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS dependency_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        dependency_kind TEXT NOT NULL CHECK (dependency_kind IN ('chemical_medication','intoxicant','stimulant','gambling','elixir_performance','other')),
        status TEXT NOT NULL DEFAULT 'risk' CHECK (status IN ('risk','dependent','recovering','resolved')),
        exposure_count INTEGER NOT NULL DEFAULT 0 CHECK (exposure_count>=0), reinforcement_load REAL NOT NULL DEFAULT 0 CHECK (reinforcement_load>=0),
        urge_load REAL NOT NULL DEFAULT 0 CHECK (urge_load BETWEEN 0 AND 100), tolerance_load REAL NOT NULL DEFAULT 0 CHECK (tolerance_load BETWEEN 0 AND 100),
        functional_impairment REAL NOT NULL DEFAULT 0 CHECK (functional_impairment BETWEEN 0 AND 100), consequence_load REAL NOT NULL DEFAULT 0 CHECK (consequence_load BETWEEN 0 AND 100),
        last_exposure_day INTEGER, last_review_day INTEGER NOT NULL DEFAULT 0, next_review_day INTEGER NOT NULL DEFAULT 30, metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(actor_id,dependency_kind));
    CREATE INDEX IF NOT EXISTS idx_dependency_profiles_due ON dependency_profiles(status,next_review_day,actor_id);
    CREATE TABLE IF NOT EXISTS dependency_exposures (
        id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        dependency_kind TEXT NOT NULL CHECK (dependency_kind IN ('chemical_medication','intoxicant','stimulant','gambling','elixir_performance','other')),
        day INTEGER NOT NULL, source_kind TEXT NOT NULL, amount REAL NOT NULL CHECK (amount>0), reinforcing_value REAL NOT NULL DEFAULT 50 CHECK (reinforcing_value BETWEEN 0 AND 100),
        adverse_consequence REAL NOT NULL DEFAULT 0 CHECK (adverse_consequence BETWEEN 0 AND 100), source_ref_kind TEXT, source_ref_id INTEGER, metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(actor_id,source_ref_kind,source_ref_id,dependency_kind));
    CREATE INDEX IF NOT EXISTS idx_dependency_exposures_actor ON dependency_exposures(actor_id,dependency_kind,day,id);
    CREATE TABLE IF NOT EXISTS psychological_stressors (
        id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        stress_family TEXT NOT NULL CHECK (stress_family IN ('trauma','grief','anxiety','depression','nightmares','obsession','severe_mental_illness','other')), day INTEGER NOT NULL,
        burden REAL NOT NULL CHECK (burden BETWEEN 0 AND 100), source_kind TEXT NOT NULL, source_ref_kind TEXT, source_ref_id INTEGER, metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(actor_id,stress_family,source_ref_kind,source_ref_id));
    CREATE INDEX IF NOT EXISTS idx_psychological_stressors_actor ON psychological_stressors(actor_id,stress_family,day,id);
    CREATE TABLE IF NOT EXISTS psychological_conditions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        condition_family TEXT NOT NULL CHECK (condition_family IN ('trauma','grief','anxiety','depression','nightmares','obsession','severe_mental_illness','other')),
        severity REAL NOT NULL CHECK (severity BETWEEN 0 AND 100), functional_impairment REAL NOT NULL DEFAULT 0 CHECK (functional_impairment BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','recovering','chronic','resolved')), onset_day INTEGER NOT NULL, last_review_day INTEGER NOT NULL, next_review_day INTEGER NOT NULL,
        resolved_day INTEGER, metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_psychological_conditions_due ON psychological_conditions(status,next_review_day,actor_id);
    CREATE TABLE IF NOT EXISTS psychological_support (
        id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE, condition_id INTEGER REFERENCES psychological_conditions(id) ON DELETE CASCADE,
        day INTEGER NOT NULL, support_kind TEXT NOT NULL, helpfulness REAL NOT NULL DEFAULT 50 CHECK (helpfulness BETWEEN -100 AND 100), metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_psychological_support_actor ON psychological_support(actor_id,day,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('psychology_dependency_version','1');
    """)


def _migration_40(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS underworld_medical_access (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE, condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL, provider_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, provider_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL, sponsor_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL, purpose_kind TEXT NOT NULL, consent_status TEXT NOT NULL DEFAULT 'voluntary' CHECK (consent_status IN ('voluntary','coerced','unknown')), confidentiality REAL NOT NULL DEFAULT 80 CHECK (confidentiality BETWEEN 0 AND 100), coercion REAL NOT NULL DEFAULT 0 CHECK (coercion BETWEEN 0 AND 100), status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended')), started_day INTEGER NOT NULL, last_review_day INTEGER NOT NULL, next_review_day INTEGER NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}', CHECK (provider_actor_id IS NOT NULL OR provider_enterprise_id IS NOT NULL));
    CREATE INDEX IF NOT EXISTS idx_underworld_medical_access_due ON underworld_medical_access(status,next_review_day,patient_actor_id);
    CREATE TABLE IF NOT EXISTS medical_misconduct_events (id INTEGER PRIMARY KEY AUTOINCREMENT, access_id INTEGER NOT NULL REFERENCES underworld_medical_access(id) ON DELETE CASCADE, treatment_id INTEGER REFERENCES medical_treatments(id) ON DELETE SET NULL, condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL, day INTEGER NOT NULL, misconduct_kind TEXT NOT NULL, harm REAL NOT NULL DEFAULT 0 CHECK (harm BETWEEN 0 AND 100), financial_extraction REAL NOT NULL DEFAULT 0 CHECK (financial_extraction>=0), evidence_visibility TEXT NOT NULL DEFAULT 'hidden' CHECK (evidence_visibility IN ('hidden','local','public')), evidence_strength REAL NOT NULL DEFAULT 0 CHECK (evidence_strength BETWEEN 0 AND 100), status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','resolved')), metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_medical_misconduct_access ON medical_misconduct_events(access_id,day,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_medicine_version','1');
    """)


def _migration_41(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS military_logistics_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        polity_id INTEGER NOT NULL UNIQUE REFERENCES political_polities(id) ON DELETE CASCADE,
        source_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        food_fodder_capacity REAL NOT NULL DEFAULT 50 CHECK (food_fodder_capacity BETWEEN 0 AND 100),
        medical_capacity REAL NOT NULL DEFAULT 50 CHECK (medical_capacity BETWEEN 0 AND 100),
        equipment_capacity REAL NOT NULL DEFAULT 50 CHECK (equipment_capacity BETWEEN 0 AND 100),
        elixir_reserve_capacity REAL NOT NULL DEFAULT 25 CHECK (elixir_reserve_capacity BETWEEN 0 AND 100),
        transport_capacity REAL NOT NULL DEFAULT 50 CHECK (transport_capacity BETWEEN 0 AND 100),
        readiness REAL NOT NULL DEFAULT 50 CHECK (readiness BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'ready' CHECK (status IN ('ready','mobilized','strained','recovering')),
        next_review_day INTEGER NOT NULL DEFAULT 30,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_military_logistics_profiles_due ON military_logistics_profiles(status,next_review_day,id);
    CREATE TABLE IF NOT EXISTS military_campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        battle_engagement_id INTEGER NOT NULL UNIQUE REFERENCES combat_engagements(id) ON DELETE CASCADE,
        campaign_kind TEXT NOT NULL DEFAULT 'limited_campaign',
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','aftermath','closed','cancelled')),
        started_day INTEGER NOT NULL,
        ended_day INTEGER,
        next_review_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_military_campaigns_due ON military_campaigns(status,next_review_day,id);
    CREATE TABLE IF NOT EXISTS campaign_side_logistics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL REFERENCES military_campaigns(id) ON DELETE CASCADE,
        battle_side_id INTEGER NOT NULL UNIQUE REFERENCES battle_sides(id) ON DELETE CASCADE,
        polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
        food_fodder REAL NOT NULL DEFAULT 70 CHECK (food_fodder BETWEEN 0 AND 100),
        medical REAL NOT NULL DEFAULT 70 CHECK (medical BETWEEN 0 AND 100),
        equipment REAL NOT NULL DEFAULT 70 CHECK (equipment BETWEEN 0 AND 100),
        elixir_reserve REAL NOT NULL DEFAULT 30 CHECK (elixir_reserve BETWEEN 0 AND 100),
        route_access REAL NOT NULL DEFAULT 100 CHECK (route_access BETWEEN 0 AND 100),
        current_ground_factor REAL NOT NULL DEFAULT 50 CHECK (current_ground_factor BETWEEN 0 AND 100),
        shortage_pressure REAL NOT NULL DEFAULT 0 CHECK (shortage_pressure BETWEEN 0 AND 100),
        aftermath_burden REAL NOT NULL DEFAULT 0 CHECK (aftermath_burden BETWEEN 0 AND 100),
        cultivated_share REAL NOT NULL DEFAULT 0 CHECK (cultivated_share BETWEEN 0 AND 1),
        last_review_day INTEGER NOT NULL,
        next_review_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(campaign_id,battle_side_id)
    );
    CREATE INDEX IF NOT EXISTS idx_campaign_side_logistics_due ON campaign_side_logistics(campaign_id,next_review_day,id);
    CREATE TABLE IF NOT EXISTS war_logistics_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL REFERENCES military_campaigns(id) ON DELETE CASCADE,
        side_logistics_id INTEGER REFERENCES campaign_side_logistics(id) ON DELETE SET NULL,
        day INTEGER NOT NULL,
        event_kind TEXT NOT NULL,
        magnitude REAL NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_war_logistics_events_campaign ON war_logistics_events(campaign_id,day,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('war_logistics_version','1');
    """)


def _migration_42(conn: sqlite3.Connection) -> None:
    # Long-run cultivation demography: Realization opportunities are sparse causal events,
    # not a monthly retry loop. Aptitude modifies hazard without encoding a final Stage.
    cols={str(r[1]) for r in conn.execute("PRAGMA table_info(cultivation_profiles)").fetchall()}
    if "realization_aptitude" not in cols:
        conn.execute("ALTER TABLE cultivation_profiles ADD COLUMN realization_aptitude REAL NOT NULL DEFAULT 1.0 CHECK (realization_aptitude BETWEEN 0.35 AND 1.75)")
    if "next_realization_check_day" not in cols:
        conn.execute("ALTER TABLE cultivation_profiles ADD COLUMN next_realization_check_day INTEGER NOT NULL DEFAULT 365 CHECK (next_realization_check_day>=0)")
    seed_row=conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()
    seed=int(seed_row[0]) if seed_row else 1
    for row in conn.execute("SELECT actor_id,realization_aptitude,next_realization_check_day FROM cultivation_profiles ORDER BY actor_id").fetchall():
        aid=int(row[0])
        # Stable actor-specific calibration, deliberately broad but never a ceiling.
        rng=random.Random(seed*1000003 + aid*17011 + 420042)
        aptitude=round(0.55 + rng.random()*0.90, 6)
        first_check=180 + int(rng.random()*240)
        conn.execute("UPDATE cultivation_profiles SET realization_aptitude=?, next_realization_check_day=CASE WHEN next_realization_check_day<=365 THEN ? ELSE next_realization_check_day END WHERE actor_id=?",(aptitude,first_check,aid))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('cultivation_demography_version','1')")


def _migration_43(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS social_contact_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        context_kind TEXT NOT NULL CHECK (context_kind IN ('institution','household','work','locality')),
        context_id INTEGER,
        affinity REAL NOT NULL DEFAULT 50 CHECK (affinity BETWEEN 0 AND 100),
        started_day INTEGER NOT NULL,
        last_review_day INTEGER NOT NULL,
        next_review_day INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','dormant','ended')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(actor_a_id,actor_b_id,context_kind,context_id),
        CHECK(actor_a_id < actor_b_id)
    );
    CREATE INDEX IF NOT EXISTS idx_social_contacts_due ON social_contact_links(status,next_review_day,actor_a_id,actor_b_id);
    CREATE TABLE IF NOT EXISTS structural_training_cohorts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        program_id INTEGER NOT NULL REFERENCES education_programs(id) ON DELETE CASCADE,
        cohort_index INTEGER NOT NULL,
        estimated_count INTEGER NOT NULL CHECK (estimated_count>=0),
        started_day INTEGER NOT NULL,
        expected_completion_day INTEGER NOT NULL,
        completed_day INTEGER,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','cancelled')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(program_id,cohort_index)
    );
    CREATE INDEX IF NOT EXISTS idx_structural_training_active ON structural_training_cohorts(program_id,status,expected_completion_day,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('generational_continuity_version','1');
    """)


def _migration_44(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS latent_resolution_profiles (
        latent_entity_id INTEGER PRIMARY KEY REFERENCES latent_entities(id) ON DELETE CASCADE,
        resolution_level TEXT NOT NULL DEFAULT 'LATENT' CHECK (resolution_level IN ('LATENT','STRUCTURAL','TRACKED')),
        significance_score REAL NOT NULL DEFAULT 0 CHECK (significance_score BETWEEN 0 AND 100),
        previous_level TEXT CHECK (previous_level IN ('LATENT','STRUCTURAL','TRACKED') OR previous_level IS NULL),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        next_review_day INTEGER NOT NULL DEFAULT 180,
        last_changed_day INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_latent_resolution_due ON latent_resolution_profiles(next_review_day,resolution_level,latent_entity_id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('autonomous_resolution_version','1');
    """)


def _migration_45(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('decade_integrity_emergence_version','1')")


def _migration_46(conn: sqlite3.Connection) -> None:
    # Stage duration is a probabilistic calibration, never a minimum-time gate.
    # Vessel response is persisted separately from Realization aptitude so fast physical
    # adaptation and fast insight can occur independently.
    cols={str(r[1]) for r in conn.execute("PRAGMA table_info(cultivation_profiles)").fetchall()}
    if "vessel_aptitude" not in cols:
        conn.execute("ALTER TABLE cultivation_profiles ADD COLUMN vessel_aptitude REAL NOT NULL DEFAULT 1.0 CHECK (vessel_aptitude BETWEEN 0.35 AND 2.50)")
    seed_row=conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()
    seed=int(seed_row[0]) if seed_row else 1
    for row in conn.execute("SELECT actor_id,vessel_aptitude FROM cultivation_profiles ORDER BY actor_id").fetchall():
        aid=int(row[0])
        rng=random.Random(seed*1000003 + aid*19001 + 460046)
        # Log-normal-like response: most people cluster around 1, with rare fast/slow tails.
        aptitude=max(0.40,min(2.35,math.exp(rng.gauss(-0.05,0.34))))
        conn.execute("UPDATE cultivation_profiles SET vessel_aptitude=? WHERE actor_id=?",(round(aptitude,6),aid))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('stage_variability_version','1')")


def _migration_47(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS groundbinding_profiles (
        actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        bound_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        binding_status TEXT NOT NULL DEFAULT 'bound' CHECK (binding_status IN ('settling','bound','failed','ended')),
        dependency_state TEXT NOT NULL DEFAULT 'comfortable' CHECK (dependency_state IN ('comfortable','straining','failing','catastrophic')),
        binding_depth REAL NOT NULL DEFAULT 100 CHECK (binding_depth BETWEEN 0 AND 100),
        mismatch_burden REAL NOT NULL DEFAULT 0 CHECK (mismatch_burden BETWEEN 0 AND 100),
        last_inside_day INTEGER,
        last_review_day INTEGER NOT NULL DEFAULT 0,
        next_review_day INTEGER NOT NULL DEFAULT 14,
        catastrophic_condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(actor_id,bound_location_id)
    );
    CREATE INDEX IF NOT EXISTS idx_groundbinding_due ON groundbinding_profiles(binding_status,next_review_day,actor_id);
    CREATE TABLE IF NOT EXISTS groundbinding_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        state_before TEXT,
        state_after TEXT,
        burden_before REAL NOT NULL,
        burden_after REAL NOT NULL,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        summary TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_groundbinding_history_actor ON groundbinding_history(actor_id,day,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('groundbinding_version','1');
    """)


def _migration_48(conn: sqlite3.Connection) -> None:
    # Stage calibration is inverse: this ledger records when a Stage was attained.
    # Current age/current Stage is never treated as an expected-Stage-by-age schedule.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cultivation_stage_attainments (
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        stage TEXT NOT NULL CHECK (stage IN ('First','Temper','Third','Breach','Fifth','Sixth')),
        attained_day INTEGER,
        attained_age_days INTEGER CHECK (attained_age_days IS NULL OR attained_age_days>=0),
        chronology_certainty TEXT NOT NULL DEFAULT 'unknown' CHECK (chronology_certainty IN ('known','bounded','unknown')),
        provenance TEXT NOT NULL CHECK (provenance IN ('runtime_breakthrough','source_explicit','opening_current_stage','opening_prior_stage')),
        source_history_id INTEGER REFERENCES cultivation_history(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(actor_id,stage)
    );
    CREATE INDEX IF NOT EXISTS idx_stage_attainment_stage_age
        ON cultivation_stage_attainments(stage,chronology_certainty,attained_age_days,actor_id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('stage_attainment_ledger_version','1');
    """)

    # Existing saves know current Stage but generally do not know historical attainment dates.
    # Backfill only the fact of prior attainment; never infer dates from current age.
    stages=('First','Temper','Third','Breach','Fifth','Sixth')
    rows=conn.execute("SELECT actor_id,current_stage FROM cultivation_profiles WHERE current_stage IS NOT NULL").fetchall()
    for actor_id,current_stage in rows:
        if current_stage not in stages:
            continue
        upto=stages.index(current_stage)
        for i,stage in enumerate(stages[:upto+1]):
            conn.execute(
                """INSERT OR IGNORE INTO cultivation_stage_attainments
                   (actor_id,stage,attained_day,attained_age_days,chronology_certainty,provenance,metadata_json)
                   VALUES (?,?,NULL,NULL,'unknown',?,?)""",
                (int(actor_id),stage,'opening_current_stage' if i==upto else 'opening_prior_stage',
                 '{"attainment_date_inferred":false,"inverse_age_stage_rule":true}')
            )


def _migration_49(conn: sqlite3.Connection) -> None:
    # Organizational form is not a power ladder: gangs, Mafia-style families, syndicates,
    # criminal enterprises and networks are parallel forms whose scale/depth vary independently.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS underworld_organizations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_key TEXT NOT NULL UNIQUE,
        organization_type TEXT NOT NULL CHECK (organization_type IN ('gang','mafia_family','criminal_dynasty','syndicate','criminal_enterprise','network','crew','other')),
        name TEXT,
        founder_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        anchor_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        primary_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        member_count_estimate REAL NOT NULL DEFAULT 1 CHECK (member_count_estimate>=0),
        command_depth INTEGER NOT NULL DEFAULT 1 CHECK (command_depth>=0),
        territorial_presence REAL NOT NULL DEFAULT 0 CHECK (territorial_presence BETWEEN 0 AND 100),
        racket_breadth REAL NOT NULL DEFAULT 0 CHECK (racket_breadth BETWEEN 0 AND 100),
        front_depth REAL NOT NULL DEFAULT 0 CHECK (front_depth BETWEEN 0 AND 100),
        corrupt_access REAL NOT NULL DEFAULT 0 CHECK (corrupt_access BETWEEN 0 AND 100),
        reputation_deterrence REAL NOT NULL DEFAULT 0 CHECK (reputation_deterrence BETWEEN 0 AND 100),
        violence_capacity REAL NOT NULL DEFAULT 0 CHECK (violence_capacity BETWEEN 0 AND 100),
        cohesion REAL NOT NULL DEFAULT 50 CHECK (cohesion BETWEEN 0 AND 100),
        membership_stability REAL NOT NULL DEFAULT 50 CHECK (membership_stability BETWEEN 0 AND 100),
        succession_depth REAL NOT NULL DEFAULT 0 CHECK (succession_depth BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','strained','fragmented','dormant','destroyed','merged')),
        created_day INTEGER NOT NULL DEFAULT 0,
        updated_day INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK (NOT (organization_type='mafia_family' AND metadata_json LIKE '%auto_promoted_from_gang%'))
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_org_actor ON underworld_organizations(founder_actor_id,status,id);
    CREATE INDEX IF NOT EXISTS idx_underworld_org_enterprise ON underworld_organizations(anchor_enterprise_id,status,id);
    CREATE INDEX IF NOT EXISTS idx_underworld_org_type ON underworld_organizations(organization_type,status,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_organization_forms_version','1');
    """)



def _migration_50(conn: sqlite3.Connection) -> None:
    # Gang membership is dynamic even when net headcount is stable. Preserve the
    # current stock by tier and the flows of people entering, leaving, or becoming
    # more deeply embedded. This is separate from organization form and scale.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS underworld_membership_profiles (
        organization_id INTEGER PRIMARY KEY REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        core_members REAL NOT NULL DEFAULT 1 CHECK (core_members>=0),
        active_members REAL NOT NULL DEFAULT 0 CHECK (active_members>=0),
        peripheral_associates REAL NOT NULL DEFAULT 0 CHECK (peripheral_associates>=0),
        lifetime_entries REAL NOT NULL DEFAULT 0 CHECK (lifetime_entries>=0),
        lifetime_exits REAL NOT NULL DEFAULT 0 CHECK (lifetime_exits>=0),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS underworld_membership_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        flow_kind TEXT NOT NULL CHECK (flow_kind IN ('recruitment','desistance','defection','custody','death_or_incapacitation','relocation','associate_to_active','active_to_core','return_to_periphery')),
        count REAL NOT NULL CHECK (count>0),
        from_tier TEXT CHECK (from_tier IN ('core','active','peripheral')),
        to_tier TEXT CHECK (to_tier IN ('core','active','peripheral')),
        source_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_membership_flows_org ON underworld_membership_flows(organization_id,day,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_membership_flow_version','1');
    """)

def _migration_51(conn: sqlite3.Connection) -> None:
    # v0.60 underworld rebuild: organization form is persistent institutional grammar,
    # while legacy named underworld answers are retired to quarry rather than grandfathered.
    cols={str(r[1]) for r in conn.execute("PRAGMA table_info(underworld_organizations)").fetchall()}
    if "current_leader_actor_id" not in cols:
        conn.execute("ALTER TABLE underworld_organizations ADD COLUMN current_leader_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL")
    if "treasury" not in cols:
        conn.execute("ALTER TABLE underworld_organizations ADD COLUMN treasury REAL NOT NULL DEFAULT 0 CHECK (treasury>=0)")
    if "monthly_leader_draw_rate" not in cols:
        conn.execute("ALTER TABLE underworld_organizations ADD COLUMN monthly_leader_draw_rate REAL NOT NULL DEFAULT 0.08 CHECK (monthly_leader_draw_rate BETWEEN 0 AND 0.5)")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS underworld_organization_culture (
        organization_id INTEGER PRIMARY KEY REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        membership_model TEXT NOT NULL DEFAULT 'fluid' CHECK (membership_model IN ('fluid','sworn','blood_household','contractual','networked')),
        continuity_model TEXT NOT NULL DEFAULT 'personalist' CHECK (continuity_model IN ('personalist','corporate','dynastic','federated','commercial')),
        territorial_orientation REAL NOT NULL DEFAULT 50 CHECK (territorial_orientation BETWEEN 0 AND 100),
        formality REAL NOT NULL DEFAULT 30 CHECK (formality BETWEEN 0 AND 100),
        violence_governance REAL NOT NULL DEFAULT 35 CHECK (violence_governance BETWEEN 0 AND 100),
        open_core_command_bias REAL NOT NULL DEFAULT 75 CHECK (open_core_command_bias BETWEEN 0 AND 100),
        identity_strength REAL NOT NULL DEFAULT 50 CHECK (identity_strength BETWEEN 0 AND 100),
        induction_required INTEGER NOT NULL DEFAULT 0 CHECK (induction_required IN (0,1)),
        hereditary_headship_preference REAL NOT NULL DEFAULT 0 CHECK (hereditary_headship_preference BETWEEN 0 AND 100),
        taboo_policy_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS underworld_rebuild_quarry (
        actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        retired_name TEXT NOT NULL,
        retired_day INTEGER NOT NULL,
        reason TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_rebuild_firewall_version','1');
    """)
    legacy=("Tallow Family","Greyhook Wharf Company","Saltwake Combine")
    day=int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    for name in legacy:
        row=conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?",(name,)).fetchone()
        if not row:
            continue
        aid=int(row[0])
        conn.execute("INSERT OR IGNORE INTO underworld_rebuild_quarry(actor_id,retired_name,retired_day,reason,metadata_json) VALUES (?,?,?,?,?)",
                     (aid,name,day,'v0.60 clean underworld rebuild; retained only as historical quarry','{\"not_grandfathered\":true}'))
        conn.execute("UPDATE actors SET status='retired' WHERE id=?",(aid,))
        if _has_table(conn,'underworld_institution_profiles'):
            conn.execute("UPDATE underworld_institution_profiles SET status='retired' WHERE institution_actor_id=?",(aid,))
        if _has_table(conn,'civilian_enterprises'):
            conn.execute("UPDATE civilian_enterprises SET status='historical' WHERE institution_actor_id=? AND json_extract(metadata_json,'$.underworld_front')=1",(aid,))
        conn.execute("UPDATE underworld_organizations SET status='dormant' WHERE institution_actor_id=?",(aid,))


def _migration_52(conn: sqlite3.Connection) -> None:
    # Concrete territorial sovereignty and command structure. Aggregate territory remains a summary only.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS underworld_zones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        city_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        zone_key TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        zone_kind TEXT NOT NULL DEFAULT 'mixed',
        population_scale REAL NOT NULL DEFAULT 50 CHECK (population_scale BETWEEN 0 AND 100),
        commercial_intensity REAL NOT NULL DEFAULT 50 CHECK (commercial_intensity BETWEEN 0 AND 100),
        street_visibility REAL NOT NULL DEFAULT 50 CHECK (street_visibility BETWEEN 0 AND 100),
        policing_pressure REAL NOT NULL DEFAULT 50 CHECK (policing_pressure BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disrupted','abandoned')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(city_location_id,name)
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_zones_city ON underworld_zones(city_location_id,status,id);
    CREATE TABLE IF NOT EXISTS underworld_zone_adjacency (
        zone_a_id INTEGER NOT NULL REFERENCES underworld_zones(id) ON DELETE CASCADE,
        zone_b_id INTEGER NOT NULL REFERENCES underworld_zones(id) ON DELETE CASCADE,
        permeability REAL NOT NULL DEFAULT 50 CHECK (permeability BETWEEN 0 AND 100),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(zone_a_id,zone_b_id), CHECK(zone_a_id<zone_b_id)
    );
    CREATE TABLE IF NOT EXISTS underworld_zone_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zone_id INTEGER NOT NULL REFERENCES underworld_zones(id) ON DELETE CASCADE,
        organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        claim_kind TEXT NOT NULL CHECK (claim_kind IN ('controller','challenger','presence')),
        strength REAL NOT NULL DEFAULT 50 CHECK (strength BETWEEN 0 AND 100),
        local_support REAL NOT NULL DEFAULT 50 CHECK (local_support BETWEEN 0 AND 100),
        fear REAL NOT NULL DEFAULT 50 CHECK (fear BETWEEN 0 AND 100),
        started_day INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','lost','withdrawn')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_underworld_zone_controller ON underworld_zone_claims(zone_id) WHERE claim_kind='controller' AND status='active';
    CREATE INDEX IF NOT EXISTS idx_underworld_claim_org ON underworld_zone_claims(organization_id,status,zone_id);
    CREATE TABLE IF NOT EXISTS underworld_operating_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zone_id INTEGER NOT NULL REFERENCES underworld_zones(id) ON DELETE CASCADE,
        controller_organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        guest_organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        activity_kind TEXT NOT NULL,
        tribute_rate REAL NOT NULL DEFAULT 0 CHECK (tribute_rate BETWEEN 0 AND 1),
        started_day INTEGER NOT NULL, expiry_day INTEGER,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked','expired')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(zone_id,guest_organization_id,activity_kind,status)
    );
    CREATE TABLE IF NOT EXISTS underworld_crews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        leader_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        home_zone_id INTEGER REFERENCES underworld_zones(id) ON DELETE SET NULL,
        purpose_kind TEXT NOT NULL DEFAULT 'general',
        size_estimate REAL NOT NULL DEFAULT 5 CHECK (size_estimate>=0),
        open_core_estimate REAL NOT NULL DEFAULT 0 CHECK (open_core_estimate>=0),
        staged_estimate REAL NOT NULL DEFAULT 0 CHECK (staged_estimate>=0),
        assigned_patrol_strength REAL NOT NULL DEFAULT 0 CHECK (assigned_patrol_strength>=0),
        cohesion REAL NOT NULL DEFAULT 60 CHECK (cohesion BETWEEN 0 AND 100),
        loyalty REAL NOT NULL DEFAULT 60 CHECK (loyalty BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','depleted','split','absorbed','destroyed')),
        created_day INTEGER NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(organization_id,name)
    );
    CREATE TABLE IF NOT EXISTS underworld_personnel (
        actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        crew_id INTEGER REFERENCES underworld_crews(id) ON DELETE SET NULL,
        role_kind TEXT NOT NULL CHECK (role_kind IN ('boss','underboss','lieutenant','crew_leader','enforcer','collector','accountant','fixer','specialist','member','associate')),
        membership_status TEXT NOT NULL DEFAULT 'member' CHECK (membership_status IN ('associate','member','sworn_member','blood_family','employee')),
        authority REAL NOT NULL DEFAULT 20 CHECK (authority BETWEEN 0 AND 100),
        earning_power REAL NOT NULL DEFAULT 20 CHECK (earning_power BETWEEN 0 AND 100),
        inducted_day INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','missing','retired','dead','defected','expelled')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_personnel_org ON underworld_personnel(organization_id,status,role_kind,actor_id);
    CREATE TABLE IF NOT EXISTS underworld_incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day INTEGER NOT NULL, zone_id INTEGER REFERENCES underworld_zones(id) ON DELETE SET NULL,
        source_organization_id INTEGER REFERENCES underworld_organizations(id),
        target_organization_id INTEGER REFERENCES underworld_organizations(id),
        incident_kind TEXT NOT NULL, severity REAL NOT NULL DEFAULT 25 CHECK (severity BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','answered','settled','expired')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_incidents_open ON underworld_incidents(status,day,zone_id,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_territorial_model_version','1');
    """)


def _migration_53(conn: sqlite3.Connection) -> None:
    # Concrete criminal economy: protection clients, racket sites, fronts and money flows.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS underworld_business_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        zone_id INTEGER REFERENCES underworld_zones(id) ON DELETE SET NULL,
        link_kind TEXT NOT NULL CHECK (link_kind IN ('owned_front','controlled_front','protected_client','partner','supplier','laundering_client','neutral_client')),
        ownership_share REAL NOT NULL DEFAULT 0 CHECK (ownership_share BETWEEN 0 AND 1),
        started_day INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','ended','seized','lost')),
        metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(organization_id,enterprise_id,link_kind,status)
    );
    CREATE TABLE IF NOT EXISTS underworld_protection_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        protector_organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        zone_id INTEGER NOT NULL REFERENCES underworld_zones(id) ON DELETE CASCADE,
        payment_per_30 REAL NOT NULL DEFAULT 1 CHECK(payment_per_30>=0),
        service_strength REAL NOT NULL DEFAULT 50 CHECK(service_strength BETWEEN 0 AND 100),
        fear_component REAL NOT NULL DEFAULT 50 CHECK(fear_component BETWEEN 0 AND 100),
        disputed INTEGER NOT NULL DEFAULT 0 CHECK(disputed IN (0,1)),
        started_day INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','ended','defaulted')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_active_protection_enterprise ON underworld_protection_accounts(enterprise_id) WHERE status='active';
    CREATE TABLE IF NOT EXISTS underworld_racket_sites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        zone_id INTEGER REFERENCES underworld_zones(id) ON DELETE SET NULL,
        enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        racket_kind TEXT NOT NULL,
        gross_income_per_30 REAL NOT NULL DEFAULT 2 CHECK(gross_income_per_30>=0),
        labor_required REAL NOT NULL DEFAULT 2 CHECK(labor_required>=0),
        violence_requirement REAL NOT NULL DEFAULT 10 CHECK(violence_requirement BETWEEN 0 AND 100),
        secrecy REAL NOT NULL DEFAULT 50 CHECK(secrecy BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suppressed','seized','abandoned')),
        created_day INTEGER NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_rackets_org ON underworld_racket_sites(organization_id,status,zone_id,id);
    CREATE TABLE IF NOT EXISTS underworld_finance_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        day INTEGER NOT NULL, transaction_kind TEXT NOT NULL, amount REAL NOT NULL, crew_id INTEGER REFERENCES underworld_crews(id) ON DELETE SET NULL,
        enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL, counterparty_organization_id INTEGER REFERENCES underworld_organizations(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_finance_org ON underworld_finance_transactions(organization_id,day,id);
    CREATE TABLE IF NOT EXISTS underworld_leader_wealth (
        actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        organization_id INTEGER REFERENCES underworld_organizations(id) ON DELETE SET NULL,
        liquid_wealth REAL NOT NULL DEFAULT 0 CHECK(liquid_wealth>=0),
        property_value REAL NOT NULL DEFAULT 0 CHECK(property_value>=0),
        lifestyle_level REAL NOT NULL DEFAULT 10 CHECK(lifestyle_level BETWEEN 0 AND 100),
        residence_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        residence_building_id INTEGER REFERENCES buildings(id) ON DELETE SET NULL,
        last_review_day INTEGER NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_asset_model_version','1');
    """)


def _migration_54(conn: sqlite3.Connection) -> None:
    # Inter-organization politics, operations and succession.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS underworld_relations (
        organization_a_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        organization_b_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        relation_kind TEXT NOT NULL DEFAULT 'neutral' CHECK(relation_kind IN ('neutral','rival','war','truce','ally','tributary','patron','hostile_peace')),
        hostility REAL NOT NULL DEFAULT 20 CHECK(hostility BETWEEN 0 AND 100),
        respect REAL NOT NULL DEFAULT 20 CHECK(respect BETWEEN 0 AND 100),
        tribute_rate REAL NOT NULL DEFAULT 0 CHECK(tribute_rate BETWEEN 0 AND 1),
        patron_organization_id INTEGER REFERENCES underworld_organizations(id) ON DELETE SET NULL,
        started_day INTEGER NOT NULL DEFAULT 0, last_changed_day INTEGER NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(organization_a_id,organization_b_id), CHECK(organization_a_id<organization_b_id)
    );
    CREATE TABLE IF NOT EXISTS underworld_operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER NOT NULL, organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        operation_kind TEXT NOT NULL, zone_id INTEGER REFERENCES underworld_zones(id) ON DELETE SET NULL,
        target_organization_id INTEGER REFERENCES underworld_organizations(id),
        target_actor_id INTEGER REFERENCES actors(id), enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        crew_id INTEGER REFERENCES underworld_crews(id) ON DELETE SET NULL, result TEXT NOT NULL DEFAULT 'attempted', success REAL NOT NULL DEFAULT 0 CHECK(success BETWEEN 0 AND 1),
        event_id INTEGER REFERENCES events(id) ON DELETE SET NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_operations_org ON underworld_operations(organization_id,day,id);
    CREATE TABLE IF NOT EXISTS underworld_succession_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        day INTEGER NOT NULL, former_leader_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, new_leader_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        succession_kind TEXT NOT NULL, contested INTEGER NOT NULL DEFAULT 0 CHECK(contested IN (0,1)), metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_politics_version','1');
    """)


def _migration_55(conn: sqlite3.Connection) -> None:
    # Enforcement pressure belongs to organizations and rises from concrete visible activity.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS underworld_heat (
        organization_id INTEGER PRIMARY KEY REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        public_heat REAL NOT NULL DEFAULT 0 CHECK(public_heat BETWEEN 0 AND 100),
        investigative_heat REAL NOT NULL DEFAULT 0 CHECK(investigative_heat BETWEEN 0 AND 100),
        violence_heat REAL NOT NULL DEFAULT 0 CHECK(violence_heat BETWEEN 0 AND 100),
        corruption_cover REAL NOT NULL DEFAULT 0 CHECK(corruption_cover BETWEEN 0 AND 100),
        last_review_day INTEGER NOT NULL DEFAULT 0, next_review_day INTEGER NOT NULL DEFAULT 30, metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS underworld_enforcement_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        day INTEGER NOT NULL, action_kind TEXT NOT NULL, severity REAL NOT NULL DEFAULT 25 CHECK(severity BETWEEN 0 AND 100),
        zone_id INTEGER REFERENCES underworld_zones(id) ON DELETE SET NULL, enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        result TEXT NOT NULL DEFAULT 'applied', metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_underworld_enforcement_org ON underworld_enforcement_actions(organization_id,day,id);
    INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_heat_version','1');
    """)


def _migration_58(conn: sqlite3.Connection) -> None:
    """ECON-01: explicit economic interests/flows and protection-racket linkage.

    This is deliberately smaller than the future personal-estate system. It makes ownership,
    control, operation and money paths representable without pretending every criminal asset
    belongs personally to the boss.
    """
    # organization_id used to imply ownership of a racket. Rebuild the table once so it can
    # instead mean optional organizational affiliation/umbrella authority.
    cols = {str(r[1]): r for r in conn.execute("PRAGMA table_info(underworld_racket_sites)").fetchall()}
    if cols and int(cols["organization_id"][3]) == 1:
        conn.executescript("""
        ALTER TABLE underworld_racket_sites RENAME TO underworld_racket_sites_pre_econ01;
        CREATE TABLE underworld_racket_sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER REFERENCES underworld_organizations(id) ON DELETE SET NULL,
            zone_id INTEGER REFERENCES underworld_zones(id) ON DELETE SET NULL,
            enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
            racket_kind TEXT NOT NULL,
            gross_income_per_30 REAL NOT NULL DEFAULT 2 CHECK(gross_income_per_30>=0),
            labor_required REAL NOT NULL DEFAULT 2 CHECK(labor_required>=0),
            violence_requirement REAL NOT NULL DEFAULT 10 CHECK(violence_requirement BETWEEN 0 AND 100),
            secrecy REAL NOT NULL DEFAULT 50 CHECK(secrecy BETWEEN 0 AND 100),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suppressed','seized','abandoned')),
            created_day INTEGER NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        INSERT INTO underworld_racket_sites
            (id,organization_id,zone_id,enterprise_id,racket_kind,gross_income_per_30,labor_required,violence_requirement,secrecy,status,created_day,metadata_json)
        SELECT id,organization_id,zone_id,enterprise_id,racket_kind,gross_income_per_30,labor_required,violence_requirement,secrecy,status,created_day,metadata_json
        FROM underworld_racket_sites_pre_econ01;
        DROP TABLE underworld_racket_sites_pre_econ01;
        CREATE INDEX IF NOT EXISTS idx_underworld_rackets_org ON underworld_racket_sites(organization_id,status,zone_id,id);
        CREATE INDEX IF NOT EXISTS idx_underworld_rackets_zone ON underworld_racket_sites(zone_id,status,id);
        """)

    pcols = {str(r[1]) for r in conn.execute("PRAGMA table_info(underworld_protection_accounts)").fetchall()}
    if "racket_id" not in pcols:
        conn.execute("ALTER TABLE underworld_protection_accounts ADD COLUMN racket_id INTEGER REFERENCES underworld_racket_sites(id) ON DELETE SET NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_underworld_protection_racket ON underworld_protection_accounts(racket_id,status,id)")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS economic_interests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        holder_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
        holder_crew_id INTEGER REFERENCES underworld_crews(id) ON DELETE CASCADE,
        holder_organization_id INTEGER REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        holder_household_id INTEGER REFERENCES households(id) ON DELETE CASCADE,
        target_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        target_racket_id INTEGER REFERENCES underworld_racket_sites(id) ON DELETE CASCADE,
        interest_kind TEXT NOT NULL CHECK(interest_kind IN ('legal_owner','beneficial_controller','operator','manager','tenant','revenue_share','creditor')),
        share_fraction REAL CHECK(share_fraction IS NULL OR (share_fraction BETWEEN 0 AND 1)),
        started_day INTEGER NOT NULL,
        ended_day INTEGER,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','ended','disputed')),
        source_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK ((holder_actor_id IS NOT NULL)+(holder_crew_id IS NOT NULL)+(holder_organization_id IS NOT NULL)+(holder_household_id IS NOT NULL)=1),
        CHECK ((target_enterprise_id IS NOT NULL)+(target_racket_id IS NOT NULL)=1)
    );
    CREATE INDEX IF NOT EXISTS idx_economic_interests_enterprise ON economic_interests(target_enterprise_id,status,interest_kind,id);
    CREATE INDEX IF NOT EXISTS idx_economic_interests_racket ON economic_interests(target_racket_id,status,interest_kind,id);
    CREATE INDEX IF NOT EXISTS idx_economic_interests_org ON economic_interests(holder_organization_id,status,interest_kind,id);
    CREATE INDEX IF NOT EXISTS idx_economic_interests_actor ON economic_interests(holder_actor_id,status,interest_kind,id);

    CREATE TABLE IF NOT EXISTS economic_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day INTEGER NOT NULL,
        flow_kind TEXT NOT NULL CHECK(flow_kind IN ('tribute','share','wage','distribution','leader_draw','bribe','support','protection_payment','reimbursement','racket_kickup','other')),
        amount REAL NOT NULL CHECK(amount>=0),
        source_actor_id INTEGER REFERENCES actors(id),
        source_crew_id INTEGER REFERENCES underworld_crews(id),
        source_organization_id INTEGER REFERENCES underworld_organizations(id),
        source_household_id INTEGER REFERENCES households(id),
        source_enterprise_id INTEGER REFERENCES civilian_enterprises(id),
        source_racket_id INTEGER REFERENCES underworld_racket_sites(id),
        target_actor_id INTEGER REFERENCES actors(id),
        target_crew_id INTEGER REFERENCES underworld_crews(id),
        target_organization_id INTEGER REFERENCES underworld_organizations(id),
        target_household_id INTEGER REFERENCES households(id),
        target_enterprise_id INTEGER REFERENCES civilian_enterprises(id),
        target_racket_id INTEGER REFERENCES underworld_racket_sites(id),
        racket_id INTEGER REFERENCES underworld_racket_sites(id) ON DELETE SET NULL,
        protection_account_id INTEGER REFERENCES underworld_protection_accounts(id) ON DELETE SET NULL,
        cadence_kind TEXT NOT NULL DEFAULT 'one_off' CHECK(cadence_kind IN ('one_off','monthly','percentage')),
        rate REAL CHECK(rate IS NULL OR rate>=0),
        status TEXT NOT NULL DEFAULT 'realized' CHECK(status IN ('planned','active','realized','cancelled','defaulted')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK ((source_actor_id IS NOT NULL)+(source_crew_id IS NOT NULL)+(source_organization_id IS NOT NULL)+(source_household_id IS NOT NULL)+(source_enterprise_id IS NOT NULL)+(source_racket_id IS NOT NULL)=1),
        CHECK ((target_actor_id IS NOT NULL)+(target_crew_id IS NOT NULL)+(target_organization_id IS NOT NULL)+(target_household_id IS NOT NULL)+(target_enterprise_id IS NOT NULL)+(target_racket_id IS NOT NULL)=1)
    );
    CREATE INDEX IF NOT EXISTS idx_economic_flows_day ON economic_flows(day,flow_kind,id);
    CREATE INDEX IF NOT EXISTS idx_economic_flows_org_source ON economic_flows(source_organization_id,day,id);
    CREATE INDEX IF NOT EXISTS idx_economic_flows_org_target ON economic_flows(target_organization_id,day,id);
    """)

    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])

    # Existing rackets: organization_id is now affiliation, while explicit interests say who
    # controls/operates them. We can safely infer the old organization as the current controller
    # and default operator because that is exactly what the pre-ECON-01 schema meant.
    for r in conn.execute("SELECT id,organization_id FROM underworld_racket_sites WHERE organization_id IS NOT NULL").fetchall():
        rid, oid = int(r[0]), int(r[1])
        for kind in ('beneficial_controller','operator'):
            conn.execute("""INSERT INTO economic_interests(holder_organization_id,target_racket_id,interest_kind,share_fraction,started_day,status,metadata_json)
                            SELECT ?,?,?,NULL,?,'active',?
                            WHERE NOT EXISTS (SELECT 1 FROM economic_interests WHERE holder_organization_id=? AND target_racket_id=? AND interest_kind=? AND status='active')""",
                         (oid,rid,kind,day,'{"econ01_backfill":true}',oid,rid,kind))

    # Existing fronts: preserve their recorded legal actor ownership while separating criminal
    # beneficial control from ownership. If the enterprise is institution-owned by the same org,
    # the organization itself is the legal owner.
    links = conn.execute("""SELECT bl.*,ce.owner_actor_id,ce.institution_actor_id,o.institution_actor_id AS org_institution_actor_id
                            FROM underworld_business_links bl
                            JOIN civilian_enterprises ce ON ce.id=bl.enterprise_id
                            JOIN underworld_organizations o ON o.id=bl.organization_id
                            WHERE bl.link_kind IN ('owned_front','controlled_front') AND bl.status='active'""").fetchall()
    for l in links:
        eid, oid = int(l['enterprise_id']), int(l['organization_id'])
        if l['owner_actor_id'] is not None:
            aid=int(l['owner_actor_id'])
            conn.execute("""INSERT INTO economic_interests(holder_actor_id,target_enterprise_id,interest_kind,share_fraction,started_day,status,metadata_json)
                            SELECT ?,?,'legal_owner',1,?,'active',? WHERE NOT EXISTS
                            (SELECT 1 FROM economic_interests WHERE holder_actor_id=? AND target_enterprise_id=? AND interest_kind='legal_owner' AND status='active')""",
                         (aid,eid,day,'{"econ01_backfill":true}',aid,eid))
        if l['institution_actor_id'] is not None and l['org_institution_actor_id'] is not None and int(l['institution_actor_id'])==int(l['org_institution_actor_id']):
            conn.execute("""INSERT INTO economic_interests(holder_organization_id,target_enterprise_id,interest_kind,share_fraction,started_day,status,metadata_json)
                            SELECT ?,?,'legal_owner',1,?,'active',? WHERE NOT EXISTS
                            (SELECT 1 FROM economic_interests WHERE holder_organization_id=? AND target_enterprise_id=? AND interest_kind='legal_owner' AND status='active')""",
                         (oid,eid,day,'{"econ01_backfill":true}',oid,eid))
        for kind in ('beneficial_controller','operator'):
            conn.execute("""INSERT INTO economic_interests(holder_organization_id,target_enterprise_id,interest_kind,share_fraction,started_day,status,metadata_json)
                            SELECT ?,?,?,NULL,?,'active',? WHERE NOT EXISTS
                            (SELECT 1 FROM economic_interests WHERE holder_organization_id=? AND target_enterprise_id=? AND interest_kind=? AND status='active')""",
                         (oid,eid,kind,day,'{"econ01_backfill":true}',oid,eid,kind))

    # Backfill each active protection account under a concrete protection racket. One per org/zone
    # is only a migration default, not a uniqueness constraint: later crews may run separate books.
    accounts = conn.execute("SELECT * FROM underworld_protection_accounts WHERE status='active' ORDER BY id").fetchall()
    for a in accounts:
        oid,zid=int(a['protector_organization_id']),int(a['zone_id'])
        rr=conn.execute("SELECT id FROM underworld_racket_sites WHERE organization_id=? AND zone_id=? AND racket_kind='protection collections' AND status='active' ORDER BY id LIMIT 1",(oid,zid)).fetchone()
        if rr:
            rid=int(rr[0])
        else:
            rid=int(conn.execute("""INSERT INTO underworld_racket_sites(organization_id,zone_id,enterprise_id,racket_kind,gross_income_per_30,labor_required,violence_requirement,secrecy,status,created_day,metadata_json)
                                   VALUES (?,?,NULL,'protection collections',0,2,30,55,'active',?,?)""",
                                 (oid,zid,day,'{"econ01_protection_container":true,"backfilled":true}')).lastrowid)
            for kind in ('beneficial_controller','operator'):
                conn.execute("INSERT INTO economic_interests(holder_organization_id,target_racket_id,interest_kind,started_day,status,metadata_json) VALUES (?,?,?,?,'active',?)",
                             (oid,rid,kind,day,'{"econ01_backfill":true}'))
        conn.execute("UPDATE underworld_protection_accounts SET racket_id=? WHERE id=?",(rid,int(a['id'])))

    # The current World Bible explicitly retains these institutions/ecologies independently of
    # the old city-by-city crime-family build. Repair only retirements whose recorded cause was
    # the v0.60 clean-rebuild firewall; never resurrect a later campaign retirement, and do not
    # force these actors into the new underworld_organizations model.
    # Restore only actors that this firewall itself retired. Statuses mirror the current seed/
    # World Bible registry: Red Board remains explicitly working; the other retained institutions
    # are active. This is not re-adoption of old city crime families.
    preserved = {
        "Painted Veil": "active",
        "The Hush": "active",
        "The Reckoning": "active",
        "Cormorants": "active",
        "Red Board": "working",
    }
    for pname, restore_status in preserved.items():
        rec = conn.execute("""SELECT q.actor_id,a.status,q.reason FROM underworld_rebuild_quarry q
                             JOIN actors a ON a.id=q.actor_id WHERE q.retired_name=?""",(pname,)).fetchone()
        if rec and str(rec['reason']).startswith('v0.60 clean underworld rebuild'):
            aid=int(rec['actor_id'])
            if str(rec['status'])=='retired':
                conn.execute("UPDATE actors SET status=? WHERE id=?",(restore_status,aid))
                # Institution-profile lifecycle is operational, not canon-status prose; an actor
                # restored from this specific firewall retirement returns to active operation.
                if _has_table(conn,'underworld_institution_profiles'):
                    conn.execute("UPDATE underworld_institution_profiles SET status='active' WHERE institution_actor_id=? AND status='retired'",(aid,))
            conn.execute("DELETE FROM underworld_rebuild_quarry WHERE actor_id=?",(aid,))

    # Active protection accounts are not free-floating client rows: they must belong to a live
    # protection racket under the same organization and zone. These guards make the new ontology
    # an invariant rather than a convention followed only by protect_business().
    conn.executescript("""
    DROP TRIGGER IF EXISTS trg_active_protection_account_insert;
    DROP TRIGGER IF EXISTS trg_active_protection_account_update;
    CREATE TRIGGER trg_active_protection_account_insert
    BEFORE INSERT ON underworld_protection_accounts
    WHEN NEW.status='active'
    BEGIN
      SELECT CASE WHEN NEW.racket_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM underworld_racket_sites r
        WHERE r.id=NEW.racket_id AND r.status='active'
          AND r.racket_kind='protection collections'
          AND r.organization_id=NEW.protector_organization_id
          AND r.zone_id=NEW.zone_id
      ) THEN RAISE(ABORT,'active protection account requires matching active protection racket') END;
    END;
    CREATE TRIGGER trg_active_protection_account_update
    BEFORE UPDATE OF racket_id,status,protector_organization_id,zone_id ON underworld_protection_accounts
    WHEN NEW.status='active'
    BEGIN
      SELECT CASE WHEN NEW.racket_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM underworld_racket_sites r
        WHERE r.id=NEW.racket_id AND r.status='active'
          AND r.racket_kind='protection collections'
          AND r.organization_id=NEW.protector_organization_id
          AND r.zone_id=NEW.zone_id
      ) THEN RAISE(ABORT,'active protection account requires matching active protection racket') END;
    END;
    """)

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_econ01_version','1')")



def _migration_59(conn: sqlite3.Connection) -> None:
    """EVENTS-01: bounded event-sourcing spike for territorial sovereignty only.

    Current underworld SQL remains authoritative. These tables prove an immutable event stream,
    replayable projection, snapshot+tail recovery, branching, and version evolution before any
    broader cutover decision.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS territorial_event_branches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        branch_key TEXT NOT NULL UNIQUE,
        parent_branch_id INTEGER REFERENCES territorial_event_branches(id) ON DELETE RESTRICT,
        fork_event_id INTEGER,
        created_day INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','closed')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS territorial_domain_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        branch_id INTEGER NOT NULL REFERENCES territorial_event_branches(id) ON DELETE RESTRICT,
        stream_key TEXT NOT NULL,
        stream_sequence INTEGER NOT NULL,
        day INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        event_version INTEGER NOT NULL CHECK(event_version>=1),
        payload_json TEXT NOT NULL,
        cause_kind TEXT,
        cause_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(branch_id,stream_key,stream_sequence)
    );
    CREATE INDEX IF NOT EXISTS idx_territorial_events_branch_id ON territorial_domain_events(branch_id,id);
    CREATE INDEX IF NOT EXISTS idx_territorial_events_stream ON territorial_domain_events(branch_id,stream_key,stream_sequence);

    CREATE TABLE IF NOT EXISTS territorial_projection_zones (
        branch_id INTEGER NOT NULL REFERENCES territorial_event_branches(id) ON DELETE CASCADE,
        zone_id INTEGER NOT NULL REFERENCES underworld_zones(id) ON DELETE CASCADE,
        controller_organization_id INTEGER REFERENCES underworld_organizations(id) ON DELETE SET NULL,
        strength REAL,
        local_support REAL,
        fear REAL,
        started_day INTEGER,
        contested INTEGER NOT NULL DEFAULT 0 CHECK(contested IN (0,1)),
        last_event_id INTEGER REFERENCES territorial_domain_events(id) ON DELETE SET NULL,
        PRIMARY KEY(branch_id,zone_id)
    );
    CREATE TABLE IF NOT EXISTS territorial_projection_challengers (
        branch_id INTEGER NOT NULL REFERENCES territorial_event_branches(id) ON DELETE CASCADE,
        zone_id INTEGER NOT NULL REFERENCES underworld_zones(id) ON DELETE CASCADE,
        organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        strength REAL NOT NULL,
        started_day INTEGER NOT NULL,
        last_event_id INTEGER REFERENCES territorial_domain_events(id) ON DELETE SET NULL,
        PRIMARY KEY(branch_id,zone_id,organization_id)
    );
    CREATE TABLE IF NOT EXISTS territorial_projection_permissions (
        branch_id INTEGER NOT NULL REFERENCES territorial_event_branches(id) ON DELETE CASCADE,
        permission_id INTEGER NOT NULL,
        zone_id INTEGER NOT NULL REFERENCES underworld_zones(id) ON DELETE CASCADE,
        controller_organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        guest_organization_id INTEGER NOT NULL REFERENCES underworld_organizations(id) ON DELETE CASCADE,
        activity_kind TEXT NOT NULL,
        tribute_rate REAL NOT NULL DEFAULT 0,
        started_day INTEGER NOT NULL,
        expiry_day INTEGER,
        last_event_id INTEGER REFERENCES territorial_domain_events(id) ON DELETE SET NULL,
        PRIMARY KEY(branch_id,permission_id)
    );
    CREATE TABLE IF NOT EXISTS territorial_event_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        branch_id INTEGER NOT NULL REFERENCES territorial_event_branches(id) ON DELETE CASCADE,
        through_event_id INTEGER NOT NULL,
        day INTEGER NOT NULL,
        state_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_territorial_snapshots_branch ON territorial_event_snapshots(branch_id,through_event_id DESC,id DESC);

    DROP TRIGGER IF EXISTS trg_territorial_events_no_update;
    DROP TRIGGER IF EXISTS trg_territorial_events_no_delete;
    CREATE TRIGGER trg_territorial_events_no_update
    BEFORE UPDATE ON territorial_domain_events
    BEGIN SELECT RAISE(ABORT,'territorial domain events are immutable'); END;
    CREATE TRIGGER trg_territorial_events_no_delete
    BEFORE DELETE ON territorial_domain_events
    BEGIN SELECT RAISE(ABORT,'territorial domain events are immutable'); END;
    INSERT OR IGNORE INTO territorial_event_branches(branch_key,parent_branch_id,fork_event_id,created_day,status,metadata_json)
    SELECT 'main',NULL,NULL,current_day,'active','{"events01":true}' FROM world_state WHERE id=1;
    """)

    # Existing schema-58 worlds have current territorial truth but no event history. Establish a
    # migration baseline as explicit domain events; future mutations append normally. This does
    # not pretend to reconstruct chronology that the old schema never stored.
    if int(conn.execute("SELECT COUNT(*) FROM territorial_domain_events").fetchone()[0]) == 0:
        from .territorial_events import append_territorial_event, ensure_base_branch
        bid = ensure_base_branch(conn)
        for r in conn.execute("""SELECT zone_id,organization_id,strength,local_support,fear,started_day,id
                                 FROM underworld_zone_claims WHERE claim_kind='controller' AND status='active'
                                 ORDER BY zone_id,id""").fetchall():
            append_territorial_event(conn, 'territory.zone_control_set', {
                'zone_id': int(r['zone_id']), 'new_controller_organization_id': int(r['organization_id']),
                'strength': float(r['strength']), 'local_support': float(r['local_support']), 'fear': float(r['fear']),
                'started_day': int(r['started_day']), 'baseline_import': True,
            }, branch=bid, day=int(r['started_day']), cause_kind='underworld_zone_claim', cause_id=int(r['id']))
        for r in conn.execute("""SELECT zone_id,organization_id,strength,started_day,id
                                 FROM underworld_zone_claims WHERE claim_kind='challenger' AND status='active'
                                 ORDER BY zone_id,organization_id,id""").fetchall():
            append_territorial_event(conn, 'territory.challenger_added', {
                'zone_id': int(r['zone_id']), 'organization_id': int(r['organization_id']),
                'strength': float(r['strength']), 'started_day': int(r['started_day']), 'baseline_import': True,
            }, branch=bid, day=int(r['started_day']), cause_kind='underworld_zone_claim', cause_id=int(r['id']))
        for r in conn.execute("""SELECT id,zone_id,controller_organization_id,guest_organization_id,activity_kind,tribute_rate,started_day,expiry_day
                                 FROM underworld_operating_permissions WHERE status='active' ORDER BY id""").fetchall():
            append_territorial_event(conn, 'territory.permission_granted', {
                'permission_id': int(r['id']), 'zone_id': int(r['zone_id']),
                'controller_organization_id': int(r['controller_organization_id']), 'guest_organization_id': int(r['guest_organization_id']),
                'activity_kind': str(r['activity_kind']), 'tribute_rate': float(r['tribute_rate']),
                'started_day': int(r['started_day']), 'expiry_day': int(r['expiry_day']) if r['expiry_day'] is not None else None,
                'baseline_import': True,
            }, branch=bid, day=int(r['started_day']), cause_kind='underworld_permission', cause_id=int(r['id']))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('territorial_event_sourcing_spike_version','1')")


def _migration_60(conn: sqlite3.Connection) -> None:
    """REL-01: make social/evaluative relationships explicitly directional.

    actor_a_id is the source/observer and actor_b_id is the target. Existing pre-REL-01
    rows are mirrored once so old campaigns retain the shared meaning they previously had;
    after migration the two rows are independent. Structural ties remain in their own tables.
    """
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(relationships)").fetchall()}
    additions = [
        ("familiarity", "REAL NOT NULL DEFAULT 0 CHECK (familiarity BETWEEN 0 AND 100)"),
        ("affection", "REAL NOT NULL DEFAULT 0 CHECK (affection BETWEEN -100 AND 100)"),
        ("respect", "REAL NOT NULL DEFAULT 0 CHECK (respect BETWEEN -100 AND 100)"),
        ("fear", "REAL NOT NULL DEFAULT 0 CHECK (fear BETWEEN -100 AND 100)"),
        ("loyalty", "REAL NOT NULL DEFAULT 0 CHECK (loyalty BETWEEN -100 AND 100)"),
        ("resentment", "REAL NOT NULL DEFAULT 0 CHECK (resentment BETWEEN -100 AND 100)"),
        ("professional_confidence", "REAL NOT NULL DEFAULT 0 CHECK (professional_confidence BETWEEN -100 AND 100)"),
    ]
    for name, ddl in additions:
        if name not in cols:
            conn.execute(f"ALTER TABLE relationships ADD COLUMN {name} {ddl}")
    # Snapshot first: inserting reverse rows must not recursively become source material.
    rows = conn.execute("SELECT * FROM relationships ORDER BY id").fetchall()
    for r in rows:
        if conn.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?",
                        (int(r['actor_b_id']), int(r['actor_a_id']))).fetchone():
            continue
        conn.execute(
            """INSERT INTO relationships(
                   actor_a_id,actor_b_id,stance,familiarity,trust,affection,respect,fear,loyalty,resentment,obligation,professional_confidence,updated_day
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (int(r['actor_b_id']),int(r['actor_a_id']),float(r['stance']),float(r['familiarity']),float(r['trust']),
             float(r['affection']),float(r['respect']),float(r['fear']),float(r['loyalty']),float(r['resentment']),
             float(r['obligation']),float(r['professional_confidence']),int(r['updated_day'])),
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(actor_a_id,updated_day DESC,actor_b_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(actor_b_id,updated_day DESC,actor_a_id)")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('directed_relationship_model_version','1')")


def _migration_61(conn: sqlite3.Connection) -> None:
    """PRES-01: shared low-resolution presence profiles; explicit travel remains authoritative."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS actor_presence_profiles (
        actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        base_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        source_kind TEXT NOT NULL DEFAULT 'campaign',
        confidence REAL NOT NULL DEFAULT 0.7 CHECK (confidence BETWEEN 0 AND 1),
        effective_from_day INTEGER NOT NULL DEFAULT 0,
        notes TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS actor_presence_habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        habit_kind TEXT NOT NULL DEFAULT 'frequented',
        weight REAL NOT NULL DEFAULT 0.5 CHECK (weight BETWEEN 0 AND 1),
        cadence_days INTEGER NOT NULL DEFAULT 7 CHECK (cadence_days >= 1),
        time_window TEXT,
        basis_kind TEXT,
        basis_id INTEGER,
        source_kind TEXT NOT NULL DEFAULT 'campaign',
        confidence REAL NOT NULL DEFAULT 0.7 CHECK (confidence BETWEEN 0 AND 1),
        effective_from_day INTEGER NOT NULL,
        effective_to_day INTEGER,
        notes TEXT NOT NULL DEFAULT '',
        UNIQUE(actor_id,location_id,habit_kind,basis_kind,basis_id,effective_from_day)
    );
    CREATE INDEX IF NOT EXISTS idx_presence_habits_actor_day ON actor_presence_habits(actor_id,effective_from_day,effective_to_day,location_id);
    CREATE INDEX IF NOT EXISTS idx_presence_habits_location_day ON actor_presence_habits(location_id,effective_from_day,effective_to_day,actor_id);
    """)
    from .presence import seed_presence_from_existing_state
    seed_presence_from_existing_state(conn)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('presence_model_version','1')")


def _migration_62(conn: sqlite3.Connection) -> None:
    """BELIEF-01: provenance-bearing claims/evidence, actor-relative stances, correction history."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS information_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        claim_key TEXT NOT NULL UNIQUE,
        proposition_text TEXT NOT NULL,
        subject_kind TEXT,
        subject_id INTEGER,
        authoritative_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
        created_day INTEGER NOT NULL,
        source_kind TEXT NOT NULL DEFAULT 'simulation',
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retracted','superseded'))
    );
    CREATE TABLE IF NOT EXISTS claim_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        claim_id INTEGER NOT NULL REFERENCES information_claims(id) ON DELETE CASCADE,
        evidence_kind TEXT NOT NULL,
        source_id INTEGER,
        source_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        polarity TEXT NOT NULL DEFAULT 'supports' CHECK (polarity IN ('supports','contradicts','context')),
        reliability REAL NOT NULL DEFAULT 0.7 CHECK (reliability BETWEEN 0 AND 1),
        salience REAL NOT NULL DEFAULT 0.6 CHECK (salience BETWEEN 0 AND 1),
        domain_key TEXT,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        summary TEXT NOT NULL,
        available_from_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim ON claim_evidence(claim_id,id);
    CREATE INDEX IF NOT EXISTS idx_claim_evidence_domain ON claim_evidence(domain_key,claim_id,id);
    CREATE TABLE IF NOT EXISTS actor_evidence_access (
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        evidence_id INTEGER NOT NULL REFERENCES claim_evidence(id) ON DELETE CASCADE,
        received_day INTEGER NOT NULL,
        access_kind TEXT NOT NULL DEFAULT 'observed',
        weight REAL NOT NULL DEFAULT 1.0 CHECK (weight BETWEEN 0 AND 1),
        notes TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(actor_id,evidence_id)
    );
    CREATE INDEX IF NOT EXISTS idx_actor_evidence_access_actor ON actor_evidence_access(actor_id,received_day,evidence_id);
    CREATE TABLE IF NOT EXISTS actor_beliefs (
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        claim_id INTEGER NOT NULL REFERENCES information_claims(id) ON DELETE CASCADE,
        stance TEXT NOT NULL DEFAULT 'uncertain' CHECK (stance IN ('unaware','uncertain','accepts','rejects')),
        confidence REAL NOT NULL DEFAULT 0.0 CHECK (confidence BETWEEN 0 AND 1),
        first_received_day INTEGER NOT NULL,
        updated_day INTEGER NOT NULL,
        correction_count INTEGER NOT NULL DEFAULT 0 CHECK (correction_count >= 0),
        basis_json TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY(actor_id,claim_id)
    );
    CREATE INDEX IF NOT EXISTS idx_actor_beliefs_actor ON actor_beliefs(actor_id,updated_day DESC,claim_id);
    CREATE TABLE IF NOT EXISTS belief_revisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        claim_id INTEGER NOT NULL REFERENCES information_claims(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        old_stance TEXT NOT NULL,
        new_stance TEXT NOT NULL,
        old_confidence REAL NOT NULL,
        new_confidence REAL NOT NULL,
        reason TEXT NOT NULL,
        evidence_ids_json TEXT NOT NULL DEFAULT '[]'
    );
    CREATE INDEX IF NOT EXISTS idx_belief_revisions_actor_claim ON belief_revisions(actor_id,claim_id,day,id);
    """)
    from .belief import import_existing_knowledge
    import_existing_knowledge(conn)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('belief_model_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('competence_lens_version','1')")



def _migration_63(conn: sqlite3.Connection) -> None:
    """DEC-01: information-bounded candidate evaluations and inspectable weighted selection."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS decision_evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day INTEGER NOT NULL,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        tier TEXT NOT NULL CHECK (tier IN ('ACTIVE','STRATEGIC','DORMANT')),
        temperature REAL NOT NULL CHECK (temperature>0),
        random_draw REAL NOT NULL CHECK (random_draw BETWEEN 0 AND 1),
        selected_candidate_key TEXT NOT NULL,
        envelope_summary_json TEXT NOT NULL DEFAULT '{}',
        decision_id INTEGER REFERENCES decisions(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_decision_evaluations_actor_day ON decision_evaluations(actor_id,day,id);
    CREATE TABLE IF NOT EXISTS decision_candidate_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evaluation_id INTEGER NOT NULL REFERENCES decision_evaluations(id) ON DELETE CASCADE,
        candidate_key TEXT NOT NULL,
        provider_key TEXT NOT NULL,
        action_kind TEXT NOT NULL,
        utility REAL NOT NULL,
        selection_probability REAL NOT NULL DEFAULT 0 CHECK (selection_probability BETWEEN 0 AND 1),
        plausible INTEGER NOT NULL DEFAULT 1 CHECK (plausible IN (0,1)),
        selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0,1)),
        target_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        interaction_type TEXT,
        information_basis_json TEXT NOT NULL DEFAULT '{}',
        payload_json TEXT NOT NULL DEFAULT '{}',
        tags_json TEXT NOT NULL DEFAULT '[]',
        estimated_cost REAL NOT NULL DEFAULT 0,
        risk REAL NOT NULL DEFAULT 0 CHECK (risk BETWEEN 0 AND 1),
        UNIQUE(evaluation_id,candidate_key)
    );
    CREATE INDEX IF NOT EXISTS idx_decision_candidate_eval ON decision_candidate_audit(evaluation_id,selected DESC,utility DESC,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('decision_runtime_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('decision_information_rule','actor_accessible_only')")
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    conn.execute("""UPDATE simulation_profiles SET tier='STRATEGIC',cadence_days=MIN(cadence_days,30),
                    next_review_day=MIN(next_review_day,?)
                    WHERE actor_id IN (SELECT actor_id FROM underworld_personnel WHERE status='active' AND role_kind='boss')""", (day+30,))


def _migration_64(conn: sqlite3.Connection) -> None:
    """MERCHANT-01: enterprise records, observed offers, contracts, conserved settlement and input substitution."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS enterprise_staff (
        enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        role TEXT NOT NULL DEFAULT 'factor', authority REAL NOT NULL DEFAULT 50 CHECK(authority BETWEEN 0 AND 100),
        specialty TEXT NOT NULL DEFAULT 'trade', status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','former')),
        joined_day INTEGER NOT NULL, left_day INTEGER, metadata_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(enterprise_id,actor_id));
    CREATE INDEX IF NOT EXISTS idx_enterprise_staff_actor ON enterprise_staff(actor_id,status,authority DESC,enterprise_id);
    CREATE TABLE IF NOT EXISTS merchant_market_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        observer_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE, observed_day INTEGER NOT NULL, received_day INTEGER NOT NULL,
        observed_price REAL NOT NULL CHECK(observed_price>0), observed_supply REAL NOT NULL CHECK(observed_supply>=0), observed_demand REAL NOT NULL CHECK(observed_demand>=0),
        source_kind TEXT NOT NULL, source_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        reliability REAL NOT NULL DEFAULT .8 CHECK(reliability BETWEEN 0 AND 1), metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_market_obs_enterprise ON merchant_market_observations(enterprise_id,received_day,location_id,good_id,observed_day DESC);
    CREATE TABLE IF NOT EXISTS merchant_trade_offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, seller_enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        stock_id INTEGER NOT NULL REFERENCES commercial_stock(id) ON DELETE CASCADE, location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
        good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT, quantity_available REAL NOT NULL CHECK(quantity_available>=0), unit_price REAL NOT NULL CHECK(unit_price>0),
        published_day INTEGER NOT NULL, expires_day INTEGER, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','filled','withdrawn','expired')), metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_trade_offers_market ON merchant_trade_offers(status,location_id,good_id,published_day,id);
    CREATE TABLE IF NOT EXISTS merchant_offer_awareness (
        enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE, actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        offer_id INTEGER NOT NULL REFERENCES merchant_trade_offers(id) ON DELETE CASCADE, observed_day INTEGER NOT NULL, received_day INTEGER NOT NULL,
        PRIMARY KEY(enterprise_id,offer_id));
    CREATE TABLE IF NOT EXISTS merchant_trade_contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, offer_id INTEGER NOT NULL REFERENCES merchant_trade_offers(id) ON DELETE RESTRICT,
        buyer_enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE RESTRICT, seller_enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE RESTRICT,
        good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT, quantity REAL NOT NULL CHECK(quantity>0), unit_price REAL NOT NULL CHECK(unit_price>0),
        origin_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT, destination_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
        settlement_kind TEXT NOT NULL CHECK(settlement_kind IN ('cash_on_delivery','seller_credit')), agreed_day INTEGER NOT NULL, due_day INTEGER NOT NULL,
        shipped_quantity REAL NOT NULL DEFAULT 0, delivered_quantity REAL NOT NULL DEFAULT 0, amount_paid REAL NOT NULL DEFAULT 0,
        shipment_id INTEGER REFERENCES commercial_shipments(id) ON DELETE SET NULL, fulfilled_day INTEGER,
        status TEXT NOT NULL DEFAULT 'accepted' CHECK(status IN ('accepted','in_transit','fulfilled','breached','cancelled')), metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_trade_contracts_due ON merchant_trade_contracts(status,due_day,id);
    CREATE TABLE IF NOT EXISTS commercial_cash_transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER NOT NULL,
        from_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        to_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        amount REAL NOT NULL CHECK(amount>0), transfer_kind TEXT NOT NULL,
        trade_contract_id INTEGER REFERENCES merchant_trade_contracts(id) ON DELETE SET NULL, metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_cash_transfer_contract ON commercial_cash_transfers(trade_contract_id,day,id);
    CREATE TABLE IF NOT EXISTS production_input_options (
        id INTEGER PRIMARY KEY AUTOINCREMENT, production_site_id INTEGER NOT NULL REFERENCES production_sites(id) ON DELETE CASCADE,
        input_good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE,
        units_per_output REAL NOT NULL DEFAULT 1 CHECK(units_per_output>0), substitution_group TEXT NOT NULL DEFAULT 'primary',
        preference_weight REAL NOT NULL DEFAULT 1 CHECK(preference_weight>0), current_share REAL NOT NULL DEFAULT .5 CHECK(current_share BETWEEN 0 AND 1),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), last_review_day INTEGER NOT NULL DEFAULT 0, next_review_day INTEGER NOT NULL DEFAULT 30,
        UNIQUE(production_site_id,input_good_id));
    CREATE INDEX IF NOT EXISTS idx_input_options_due ON production_input_options(active,next_review_day,production_site_id);
    """)
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(commercial_shipments)").fetchall()}
    additions = [
        ("source_stock_id", "INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL"),
        ("recipient_enterprise_id", "INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL"),
        ("trade_contract_id", "INTEGER REFERENCES merchant_trade_contracts(id) ON DELETE SET NULL"),
        ("carrier_enterprise_id", "INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL"),
        ("freight_cost", "REAL NOT NULL DEFAULT 0 CHECK(freight_cost>=0)"),
    ]
    for name, ddl in additions:
        if name not in cols:
            conn.execute(f"ALTER TABLE commercial_shipments ADD COLUMN {name} {ddl}")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('merchant_vertical_slice_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('merchant_information_rule','enterprise_records_only')")

def _migration_65(conn: sqlite3.Connection) -> None:
    """CRAFT-01: tracked recipe/facility/order execution over conserved commercial stock."""
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(production_sites)").fetchall()}
    if "production_mode" not in cols:
        conn.execute("ALTER TABLE production_sites ADD COLUMN production_mode TEXT NOT NULL DEFAULT 'aggregate' CHECK(production_mode IN ('aggregate','tracked'))")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS craft_recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, recipe_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
        output_good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
        output_quantity REAL NOT NULL DEFAULT 1 CHECK(output_quantity>0), base_duration_days REAL NOT NULL DEFAULT 1 CHECK(base_duration_days>0),
        skill_domain TEXT NOT NULL DEFAULT 'craft', min_skill REAL NOT NULL DEFAULT 0 CHECK(min_skill BETWEEN 0 AND 100),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_craft_recipe_output ON craft_recipes(output_good_id,active,id);
    CREATE TABLE IF NOT EXISTS craft_recipe_inputs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, recipe_id INTEGER NOT NULL REFERENCES craft_recipes(id) ON DELETE CASCADE,
        group_key TEXT NOT NULL, input_good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
        units_per_batch REAL NOT NULL CHECK(units_per_batch>0), preference_weight REAL NOT NULL DEFAULT 1 CHECK(preference_weight>0),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(recipe_id,group_key,input_good_id));
    CREATE INDEX IF NOT EXISTS idx_craft_recipe_input_good ON craft_recipe_inputs(input_good_id,active,recipe_id);
    CREATE TABLE IF NOT EXISTS craft_recipe_facility_requirements (
        recipe_id INTEGER NOT NULL REFERENCES craft_recipes(id) ON DELETE CASCADE, facility_kind TEXT NOT NULL,
        minimum_capacity REAL NOT NULL DEFAULT 1 CHECK(minimum_capacity>0), minimum_condition REAL NOT NULL DEFAULT 20 CHECK(minimum_condition BETWEEN 0 AND 100),
        PRIMARY KEY(recipe_id,facility_kind));
    CREATE TABLE IF NOT EXISTS craft_facilities (
        id INTEGER PRIMARY KEY AUTOINCREMENT, enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT, facility_kind TEXT NOT NULL, name TEXT NOT NULL,
        capacity REAL NOT NULL DEFAULT 1 CHECK(capacity>0), condition REAL NOT NULL DEFAULT 100 CHECK(condition BETWEEN 0 AND 100),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_craft_facility_lookup ON craft_facilities(enterprise_id,location_id,facility_kind,active,id);
    CREATE TABLE IF NOT EXISTS craft_site_recipes (
        production_site_id INTEGER NOT NULL REFERENCES production_sites(id) ON DELETE CASCADE,
        recipe_id INTEGER NOT NULL REFERENCES craft_recipes(id) ON DELETE CASCADE,
        is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)), active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        PRIMARY KEY(production_site_id,recipe_id));
    CREATE TABLE IF NOT EXISTS craft_site_workers (
        production_site_id INTEGER NOT NULL REFERENCES production_sites(id) ON DELETE CASCADE,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE, role TEXT NOT NULL DEFAULT 'craftsperson',
        capacity_share REAL NOT NULL DEFAULT 1 CHECK(capacity_share>0), status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','former')),
        assigned_day INTEGER NOT NULL, PRIMARY KEY(production_site_id,actor_id));
    CREATE INDEX IF NOT EXISTS idx_craft_workers_actor ON craft_site_workers(actor_id,status,production_site_id);
    CREATE TABLE IF NOT EXISTS craft_production_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, production_site_id INTEGER NOT NULL REFERENCES production_sites(id) ON DELETE CASCADE,
        recipe_id INTEGER NOT NULL REFERENCES craft_recipes(id) ON DELETE RESTRICT, requested_output_qty REAL NOT NULL CHECK(requested_output_qty>0),
        priority INTEGER NOT NULL DEFAULT 50 CHECK(priority BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','waiting_input','waiting_facility','waiting_labor','in_progress','completed','cancelled','blocked')),
        created_day INTEGER NOT NULL, due_day INTEGER, started_day INTEGER, completed_day INTEGER, next_review_day INTEGER NOT NULL,
        blocked_reason TEXT, blocked_detail_json TEXT NOT NULL DEFAULT '{}', selected_inputs_json TEXT NOT NULL DEFAULT '[]', quality REAL,
        metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_craft_orders_due ON craft_production_orders(status,next_review_day,priority DESC,id);
    CREATE INDEX IF NOT EXISTS idx_craft_orders_site ON craft_production_orders(production_site_id,status,id);
    CREATE TABLE IF NOT EXISTS craft_input_reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES craft_production_orders(id) ON DELETE CASCADE,
        recipe_input_id INTEGER NOT NULL REFERENCES craft_recipe_inputs(id) ON DELETE RESTRICT,
        stock_id INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL, good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
        quantity_reserved REAL NOT NULL CHECK(quantity_reserved>0), quantity_consumed REAL NOT NULL DEFAULT 0 CHECK(quantity_consumed>=0),
        status TEXT NOT NULL DEFAULT 'reserved' CHECK(status IN ('reserved','consumed','released')), reserved_day INTEGER NOT NULL,
        consumed_day INTEGER, released_day INTEGER);
    CREATE INDEX IF NOT EXISTS idx_craft_reservation_order ON craft_input_reservations(order_id,status,id);
    CREATE TABLE IF NOT EXISTS craft_output_lots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES craft_production_orders(id) ON DELETE CASCADE,
        stock_id INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL, good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
        quantity REAL NOT NULL CHECK(quantity>0), quality REAL NOT NULL CHECK(quality BETWEEN 0 AND 100), produced_day INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_craft_output_order ON craft_output_lots(order_id,id);
    CREATE TABLE IF NOT EXISTS craft_order_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES craft_production_orders(id) ON DELETE CASCADE,
        day INTEGER NOT NULL, event_kind TEXT NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_craft_event_order ON craft_order_events(order_id,day,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('craft_vertical_slice_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('craft_stock_rule','commercial_stock_conserved')")


def _migration_56(conn: sqlite3.Connection) -> None:
    # v0.60 Phase 2A: shared-geography anchoring. city_location_id keeps meaning "which
    # city"; anchor_location_id is an optional finer district/ward-scale locations row so
    # future merchant/law/household systems can resolve a zone's real place without parsing
    # zone_key strings. Nullable and additive: existing zones are unaffected until seeded.
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(underworld_zones)").fetchall()}
    if "anchor_location_id" not in cols:
        conn.execute("ALTER TABLE underworld_zones ADD COLUMN anchor_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_territorial_model_version','2')")


def _migration_57(conn: sqlite3.Connection) -> None:
    # ARCH-01 ProcessRegistry spike: durable one-off/scheduled tasks. Recurring domain
    # processes stay owned by their existing next_X_due_day/process_due_X pairs; this
    # table is only for the new one-off scheduling capability (schedule_once/cancel),
    # since that has no existing SQL home anywhere in the engine. Persisted so a task
    # survives a connection close/reopen, which an in-memory-only scheduler could not do.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS process_registry_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        process_key TEXT NOT NULL,
        run_day INTEGER NOT NULL,
        task_kind TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','cancelled')),
        created_day INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_process_registry_tasks_due ON process_registry_tasks(status,run_day,id);
    """)


def _migration_66(conn: sqlite3.Connection) -> None:
    """GROWTH-01: conserved public finance, concrete public works/security, delayed reports and causal regional snapshots."""
    conn.executescript("""

-- GROWTH-01: regional growth / state-capacity vertical slice.
-- These tables own conserved public finance, concrete public projects, delayed
-- administrative reports, and causal snapshots. There is intentionally no
-- authoritative prosperity/development score.
CREATE TABLE IF NOT EXISTS regional_public_treasuries (
    polity_id INTEGER PRIMARY KEY REFERENCES political_polities(id) ON DELETE CASCADE,
    cash REAL NOT NULL DEFAULT 0 CHECK(cash>=0),
    debt REAL NOT NULL DEFAULT 0 CHECK(debt>=0),
    tax_rate REAL NOT NULL DEFAULT .05 CHECK(tax_rate BETWEEN 0 AND .5),
    toll_rate REAL NOT NULL DEFAULT 0 CHECK(toll_rate BETWEEN 0 AND .5),
    debt_interest_rate_per_30 REAL NOT NULL DEFAULT .015 CHECK(debt_interest_rate_per_30>=0),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','strained','suspended')),
    last_collection_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL DEFAULT 30,
    review_cadence_days INTEGER NOT NULL DEFAULT 30 CHECK(review_cadence_days>0),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_regional_treasury_due ON regional_public_treasuries(status,next_review_day,polity_id);

CREATE TABLE IF NOT EXISTS regional_fiscal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('inflow','outflow')),
    entry_kind TEXT NOT NULL,
    amount REAL NOT NULL CHECK(amount>0),
    counterparty_kind TEXT,
    counterparty_id INTEGER,
    source_kind TEXT,
    source_id INTEGER,
    description TEXT
);
CREATE INDEX IF NOT EXISTS idx_regional_fiscal_polity_day ON regional_fiscal_entries(polity_id,day,id);

CREATE TABLE IF NOT EXISTS regional_public_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    route_id INTEGER REFERENCES travel_routes(id) ON DELETE SET NULL,
    project_kind TEXT NOT NULL CHECK(project_kind IN ('road_repair','security_post','market_warehouse','administrative_office')),
    title TEXT NOT NULL,
    required_cash REAL NOT NULL DEFAULT 0 CHECK(required_cash>=0),
    cash_spent REAL NOT NULL DEFAULT 0 CHECK(cash_spent>=0),
    required_labor_days REAL NOT NULL DEFAULT 0 CHECK(required_labor_days>=0),
    labor_days_used REAL NOT NULL DEFAULT 0 CHECK(labor_days_used>=0),
    material_good_id INTEGER REFERENCES market_goods(id) ON DELETE RESTRICT,
    required_material_quantity REAL NOT NULL DEFAULT 0 CHECK(required_material_quantity>=0),
    material_quantity_used REAL NOT NULL DEFAULT 0 CHECK(material_quantity_used>=0),
    started_day INTEGER NOT NULL,
    target_day INTEGER,
    completed_day INTEGER,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','blocked','completed','cancelled')),
    blocked_reason TEXT,
    next_review_day INTEGER NOT NULL,
    effects_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_regional_project_due ON regional_public_projects(status,next_review_day,polity_id,id);
CREATE INDEX IF NOT EXISTS idx_regional_project_route ON regional_public_projects(route_id,status,id);

CREATE TABLE IF NOT EXISTS regional_project_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES regional_public_projects(id) ON DELETE CASCADE,
    supplier_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    stock_id INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK(quantity>0),
    unit_price REAL NOT NULL CHECK(unit_price>=0),
    delivered_day INTEGER NOT NULL,
    paid_amount REAL NOT NULL CHECK(paid_amount>=0)
);
CREATE INDEX IF NOT EXISTS idx_regional_project_material ON regional_project_materials(project_id,good_id,id);

CREATE TABLE IF NOT EXISTS regional_project_labor (
    project_id INTEGER NOT NULL REFERENCES regional_public_projects(id) ON DELETE CASCADE,
    household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    labor_days_committed REAL NOT NULL CHECK(labor_days_committed>0),
    labor_days_used REAL NOT NULL DEFAULT 0 CHECK(labor_days_used>=0),
    wage_per_day REAL NOT NULL DEFAULT 0 CHECK(wage_per_day>=0),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','withdrawn')),
    PRIMARY KEY(project_id,household_id)
);

CREATE TABLE IF NOT EXISTS regional_security_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    route_id INTEGER REFERENCES travel_routes(id) ON DELETE CASCADE,
    location_id INTEGER REFERENCES locations(id) ON DELETE CASCADE,
    monthly_cost REAL NOT NULL DEFAULT 0 CHECK(monthly_cost>=0),
    strength REAL NOT NULL DEFAULT 40 CHECK(strength BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','unfunded','ended','cancelled')),
    last_paid_day INTEGER NOT NULL DEFAULT 0,
    next_review_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(route_id IS NOT NULL OR location_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_regional_security_due ON regional_security_assignments(status,next_review_day,polity_id,id);

CREATE TABLE IF NOT EXISTS regional_administrative_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    recipient_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    route_id INTEGER REFERENCES travel_routes(id) ON DELETE SET NULL,
    report_kind TEXT NOT NULL,
    observed_day INTEGER NOT NULL,
    received_day INTEGER NOT NULL,
    delivered_day INTEGER,
    reliability REAL NOT NULL DEFAULT .7 CHECK(reliability BETWEEN 0 AND 1),
    report_json TEXT NOT NULL DEFAULT '{}',
    claim_id INTEGER REFERENCES information_claims(id) ON DELETE SET NULL,
    evidence_id INTEGER REFERENCES claim_evidence(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','delivered','lost'))
);
CREATE INDEX IF NOT EXISTS idx_regional_report_due ON regional_administrative_reports(status,received_day,id);
CREATE INDEX IF NOT EXISTS idx_regional_report_recipient ON regional_administrative_reports(recipient_actor_id,delivered_day,id);

CREATE TABLE IF NOT EXISTS regional_migration_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    source_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    destination_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    day INTEGER NOT NULL,
    appeal_gap REAL NOT NULL,
    migration_plan_id INTEGER REFERENCES household_migration_plans(id) ON DELETE SET NULL,
    reason_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_regional_migration_day ON regional_migration_responses(day,household_id,id);

CREATE TABLE IF NOT EXISTS regional_growth_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    population_estimate REAL NOT NULL DEFAULT 0,
    households INTEGER NOT NULL DEFAULT 0,
    active_enterprises INTEGER NOT NULL DEFAULT 0,
    enterprise_cash REAL NOT NULL DEFAULT 0,
    route_accessibility REAL NOT NULL DEFAULT 0,
    route_hazard REAL NOT NULL DEFAULT 0,
    average_route_days REAL,
    trade_contracts_365 INTEGER NOT NULL DEFAULT 0,
    food_stress REAL NOT NULL DEFAULT 0,
    treasury_cash REAL NOT NULL DEFAULT 0,
    public_debt REAL NOT NULL DEFAULT 0,
    net_public_flow_365 REAL NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_regional_snapshot_location_day ON regional_growth_snapshots(polity_id,location_id,day,id);

    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('growth_vertical_slice_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('regional_growth_rule','causal_objects_no_prosperity_score')")


def _migration_67(conn: sqlite3.Connection) -> None:
    """WAR-01: campaign operations, physical force supply, persistent casualties/damage/displacement and actor-relative battle reports."""
    conn.executescript(r"""
-- WAR-01: strategic campaign owner above individual engagements.
CREATE TABLE IF NOT EXISTS war_campaign_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    attacker_polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
    defender_polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
    commander_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    objective_kind TEXT NOT NULL DEFAULT 'limited' CHECK(objective_kind IN ('limited','territorial','raid','relief','defence','siege','other')),
    objective_text TEXT NOT NULL,
    origin_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    target_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'mobilizing' CHECK(status IN ('mobilizing','marching','engaged','aftermath','closed','cancelled','stalled')),
    started_day INTEGER NOT NULL,
    ended_day INTEGER,
    next_review_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK(origin_location_id <> target_location_id)
);
CREATE INDEX IF NOT EXISTS idx_war_operation_due ON war_campaign_operations(status,next_review_day,id);

CREATE TABLE IF NOT EXISTS war_operation_engagements (
    operation_id INTEGER NOT NULL REFERENCES war_campaign_operations(id) ON DELETE CASCADE,
    engagement_id INTEGER NOT NULL UNIQUE REFERENCES combat_engagements(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL DEFAULT 1,
    linked_day INTEGER NOT NULL,
    PRIMARY KEY(operation_id,engagement_id)
);

CREATE TABLE IF NOT EXISTS war_campaign_forces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER NOT NULL REFERENCES war_campaign_operations(id) ON DELETE CASCADE,
    polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
    battle_side_id INTEGER UNIQUE REFERENCES battle_sides(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'field_force' CHECK(role IN ('field_force','garrison','raiding_force','relief_force','escort','other')),
    personnel_initial INTEGER NOT NULL CHECK(personnel_initial>=0),
    personnel_available INTEGER NOT NULL CHECK(personnel_available>=0),
    aggregate_killed INTEGER NOT NULL DEFAULT 0 CHECK(aggregate_killed>=0),
    aggregate_wounded INTEGER NOT NULL DEFAULT 0 CHECK(aggregate_wounded>=0),
    aggregate_captured INTEGER NOT NULL DEFAULT 0 CHECK(aggregate_captured>=0),
    aggregate_deserted INTEGER NOT NULL DEFAULT 0 CHECK(aggregate_deserted>=0),
    current_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    current_route_id INTEGER REFERENCES travel_routes(id) ON DELETE SET NULL,
    segment_target_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    segment_due_day INTEGER,
    status TEXT NOT NULL DEFAULT 'mobilized' CHECK(status IN ('mobilized','marching','deployed','engaged','withdrawing','stalled','demobilized','destroyed')),
    last_review_day INTEGER NOT NULL,
    next_review_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(operation_id,name)
);
CREATE INDEX IF NOT EXISTS idx_war_force_due ON war_campaign_forces(status,next_review_day,operation_id,id);
CREATE INDEX IF NOT EXISTS idx_war_force_location ON war_campaign_forces(current_location_id,status,id);

CREATE TABLE IF NOT EXISTS war_force_members (
    force_id INTEGER NOT NULL REFERENCES war_campaign_forces(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    duty_kind TEXT NOT NULL DEFAULT 'soldier',
    exposure REAL NOT NULL DEFAULT 50 CHECK(exposure BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','wounded','killed','captured','missing','deserted','released','demobilized')),
    health_condition_id INTEGER REFERENCES health_conditions(id) ON DELETE SET NULL,
    updated_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(force_id,actor_id)
);
CREATE INDEX IF NOT EXISTS idx_war_force_member_actor ON war_force_members(actor_id,status,force_id);

CREATE TABLE IF NOT EXISTS war_force_supplies (
    force_id INTEGER NOT NULL REFERENCES war_campaign_forces(id) ON DELETE CASCADE,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    supply_kind TEXT NOT NULL CHECK(supply_kind IN ('food','fodder','equipment','medical','elixir','other')),
    source_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    source_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    on_hand REAL NOT NULL DEFAULT 0 CHECK(on_hand>=0),
    weekly_need REAL NOT NULL DEFAULT 0 CHECK(weekly_need>=0),
    max_on_hand REAL NOT NULL DEFAULT 0 CHECK(max_on_hand>=0),
    last_review_day INTEGER NOT NULL,
    PRIMARY KEY(force_id,good_id)
);

CREATE TABLE IF NOT EXISTS war_supply_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    force_id INTEGER NOT NULL REFERENCES war_campaign_forces(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    entry_kind TEXT NOT NULL CHECK(entry_kind IN ('mobilized','resupplied','consumed','lost','captured','returned')),
    quantity REAL NOT NULL CHECK(quantity>0),
    source_stock_id INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_war_supply_force_day ON war_supply_ledger(force_id,day,id);

CREATE TABLE IF NOT EXISTS war_battle_aftermath (
    engagement_id INTEGER PRIMARY KEY REFERENCES combat_engagements(id) ON DELETE CASCADE,
    operation_id INTEGER REFERENCES war_campaign_operations(id) ON DELETE SET NULL,
    applied_day INTEGER NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS war_damage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER REFERENCES war_campaign_operations(id) ON DELETE SET NULL,
    engagement_id INTEGER REFERENCES combat_engagements(id) ON DELETE SET NULL,
    day INTEGER NOT NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    target_kind TEXT NOT NULL CHECK(target_kind IN ('route','building','stock','market','agriculture','other')),
    target_id INTEGER,
    magnitude REAL NOT NULL CHECK(magnitude BETWEEN 0 AND 100),
    effects_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_war_damage_location ON war_damage_events(location_id,day,id);

CREATE TABLE IF NOT EXISTS war_displacement_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER REFERENCES war_campaign_operations(id) ON DELETE SET NULL,
    engagement_id INTEGER REFERENCES combat_engagements(id) ON DELETE SET NULL,
    household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
    source_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    destination_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    migration_plan_id INTEGER REFERENCES household_migration_plans(id) ON DELETE SET NULL,
    day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'displaced' CHECK(status IN ('displaced','planned','in_transit','resettled','stranded')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_war_displacement_day ON war_displacement_events(day,source_location_id,id);

CREATE TABLE IF NOT EXISTS war_battle_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER REFERENCES war_campaign_operations(id) ON DELETE SET NULL,
    engagement_id INTEGER NOT NULL REFERENCES combat_engagements(id) ON DELETE CASCADE,
    version_kind TEXT NOT NULL CHECK(version_kind IN ('official','eyewitness','rumour')),
    source_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    recipient_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    observed_day INTEGER NOT NULL,
    received_day INTEGER NOT NULL,
    delivered_day INTEGER,
    reliability REAL NOT NULL DEFAULT .7 CHECK(reliability BETWEEN 0 AND 1),
    report_text TEXT NOT NULL,
    claim_id INTEGER REFERENCES information_claims(id) ON DELETE SET NULL,
    evidence_id INTEGER REFERENCES claim_evidence(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','delivered','lost')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_war_report_due ON war_battle_reports(status,received_day,id);
CREATE INDEX IF NOT EXISTS idx_war_report_recipient ON war_battle_reports(recipient_actor_id,delivered_day,id);
""")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('war_vertical_slice_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('war_resolution_rule','same_people_goods_routes_institutions_information')")


def _migration_68(conn: sqlite3.Connection) -> None:
    """INTEGRATION-01: treatment capacity, agriculture/harvest, and general law/jurisdiction/procedure."""
    conn.executescript(r"""
-- HEALTH-01: care access/capacity is separate from condition progression.
CREATE TABLE IF NOT EXISTS health_care_sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    quality REAL NOT NULL DEFAULT 50 CHECK(quality BETWEEN 0 AND 100),
    capacity_per_day REAL NOT NULL DEFAULT 1 CHECK(capacity_per_day>=0),
    beds INTEGER NOT NULL DEFAULT 0 CHECK(beds>=0),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','strained','closed')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_health_care_site_location ON health_care_sites(location_id,status,id);

CREATE TABLE IF NOT EXISTS health_provider_assignments (
    site_id INTEGER NOT NULL REFERENCES health_care_sites(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    domain_key TEXT NOT NULL DEFAULT 'medicine',
    capacity_per_day REAL NOT NULL DEFAULT 1 CHECK(capacity_per_day>=0),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','absent','ended')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(site_id,actor_id,domain_key)
);
CREATE INDEX IF NOT EXISTS idx_health_provider_actor ON health_provider_assignments(actor_id,status,site_id);

CREATE TABLE IF NOT EXISTS health_care_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    condition_id INTEGER NOT NULL REFERENCES health_conditions(id) ON DELETE CASCADE,
    site_id INTEGER REFERENCES health_care_sites(id) ON DELETE SET NULL,
    requested_day INTEGER NOT NULL,
    urgency REAL NOT NULL DEFAULT 50 CHECK(urgency BETWEEN 0 AND 100),
    treatment_kind TEXT NOT NULL DEFAULT 'ordinary_medicine' CHECK(treatment_kind IN ('rest','ordinary_medicine','surgery','rehabilitation','vein_mending','guided_circulation','elixir_stabilization','other')),
    status TEXT NOT NULL DEFAULT 'waiting' CHECK(status IN ('waiting','scheduled','treated','abandoned')),
    assigned_provider_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    next_review_day INTEGER NOT NULL,
    treated_day INTEGER,
    delay_days INTEGER NOT NULL DEFAULT 0 CHECK(delay_days>=0),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_health_care_request_due ON health_care_requests(status,next_review_day,urgency DESC,id);
CREATE INDEX IF NOT EXISTS idx_health_care_request_actor ON health_care_requests(actor_id,status,id);

-- AGRI-01: fields and harvests produce physical market goods under ecology/weather.
CREATE TABLE IF NOT EXISTS agriculture_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    crop_good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
    hectares REAL NOT NULL CHECK(hectares>0),
    base_yield_per_hectare REAL NOT NULL CHECK(base_yield_per_hectare>=0),
    soil_quality REAL NOT NULL DEFAULT 70 CHECK(soil_quality BETWEEN 0 AND 100),
    labor_capacity REAL NOT NULL DEFAULT 70 CHECK(labor_capacity BETWEEN 0 AND 100),
    harvest_day_of_year INTEGER NOT NULL DEFAULT 270 CHECK(harvest_day_of_year BETWEEN 0 AND 364),
    last_harvest_day INTEGER,
    next_harvest_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','fallow','damaged','abandoned')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_agriculture_field_due ON agriculture_fields(status,next_harvest_day,location_id,id);

CREATE TABLE IF NOT EXISTS agriculture_disruptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id INTEGER NOT NULL REFERENCES agriculture_fields(id) ON DELETE CASCADE,
    disruption_kind TEXT NOT NULL CHECK(disruption_kind IN ('war','fire','flood','drought','pest','requisition','other')),
    start_day INTEGER NOT NULL,
    end_day INTEGER,
    yield_factor REAL NOT NULL DEFAULT 1 CHECK(yield_factor BETWEEN 0 AND 1),
    source_kind TEXT,
    source_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_agriculture_disruption_active ON agriculture_disruptions(field_id,start_day,end_day,id);

CREATE TABLE IF NOT EXISTS agriculture_harvests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id INTEGER NOT NULL REFERENCES agriculture_fields(id) ON DELETE CASCADE,
    harvest_day INTEGER NOT NULL,
    expected_quantity REAL NOT NULL CHECK(expected_quantity>=0),
    actual_quantity REAL NOT NULL CHECK(actual_quantity>=0),
    ecology_factor REAL NOT NULL DEFAULT 1 CHECK(ecology_factor>=0),
    labor_factor REAL NOT NULL DEFAULT 1 CHECK(labor_factor>=0),
    disruption_factor REAL NOT NULL DEFAULT 1 CHECK(disruption_factor>=0),
    stock_id INTEGER REFERENCES commercial_stock(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(field_id,harvest_day)
);
CREATE INDEX IF NOT EXISTS idx_agriculture_harvest_location_day ON agriculture_harvests(harvest_day,field_id);

-- LAW-01: general rules/jurisdiction/procedure. Underworld policing remains a separate evidence/investigation owner.
CREATE TABLE IF NOT EXISTS law_jurisdictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jurisdiction_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    authority_kind TEXT NOT NULL CHECK(authority_kind IN ('imperial','kingdom','charter','local','churn','institutional','other')),
    polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    priority INTEGER NOT NULL DEFAULT 50,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended','historical')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_law_jurisdiction_scope ON law_jurisdictions(status,location_id,polity_id,priority DESC,id);

CREATE TABLE IF NOT EXISTS law_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jurisdiction_id INTEGER NOT NULL REFERENCES law_jurisdictions(id) ON DELETE CASCADE,
    rule_key TEXT NOT NULL,
    name TEXT NOT NULL,
    matter_kind TEXT NOT NULL CHECK(matter_kind IN ('contract','property','criminal','administrative','family','commercial','other')),
    evidence_threshold REAL NOT NULL DEFAULT 55 CHECK(evidence_threshold BETWEEN 0 AND 100),
    default_remedy TEXT NOT NULL DEFAULT 'order' CHECK(default_remedy IN ('damages','restitution','fine','injunction','dismissal','order','custody','other')),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended','repealed')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(jurisdiction_id,rule_key)
);
CREATE INDEX IF NOT EXISTS idx_law_rule_matter ON law_rules(jurisdiction_id,matter_kind,status,id);

CREATE TABLE IF NOT EXISTS law_offices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    office_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    jurisdiction_id INTEGER NOT NULL REFERENCES law_jurisdictions(id) ON DELETE CASCADE,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    presiding_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    capacity REAL NOT NULL DEFAULT 50 CHECK(capacity BETWEEN 0 AND 100),
    integrity REAL NOT NULL DEFAULT 70 CHECK(integrity BETWEEN 0 AND 100),
    corruption_pressure REAL NOT NULL DEFAULT 10 CHECK(corruption_pressure BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','strained','inactive')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_law_office_jurisdiction ON law_offices(jurisdiction_id,status,capacity DESC,id);

CREATE TABLE IF NOT EXISTS law_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jurisdiction_id INTEGER NOT NULL REFERENCES law_jurisdictions(id) ON DELETE RESTRICT,
    rule_id INTEGER NOT NULL REFERENCES law_rules(id) ON DELETE RESTRICT,
    office_id INTEGER REFERENCES law_offices(id) ON DELETE SET NULL,
    matter_kind TEXT NOT NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
    claimant_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    respondent_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    claimant_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    respondent_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
    subject_kind TEXT NOT NULL,
    subject_id INTEGER,
    claim_text TEXT NOT NULL,
    amount_claimed REAL NOT NULL DEFAULT 0 CHECK(amount_claimed>=0),
    evidence_score REAL NOT NULL DEFAULT 0 CHECK(evidence_score BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'complaint' CHECK(status IN ('complaint','evidence','hearing','decided','enforcement','closed','stalled','dismissed')),
    filed_day INTEGER NOT NULL,
    last_review_day INTEGER NOT NULL,
    next_review_day INTEGER NOT NULL,
    decision_text TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_law_case_due ON law_cases(status,next_review_day,jurisdiction_id,id);
CREATE INDEX IF NOT EXISTS idx_law_case_subject ON law_cases(subject_kind,subject_id,status,id);

CREATE TABLE IF NOT EXISTS law_case_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES law_cases(id) ON DELETE CASCADE,
    evidence_kind TEXT NOT NULL,
    source_kind TEXT,
    source_id INTEGER,
    summary TEXT NOT NULL,
    strength REAL NOT NULL CHECK(strength BETWEEN 0 AND 100),
    submitted_day INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_law_case_evidence_case ON law_case_evidence(case_id,submitted_day,id);

CREATE TABLE IF NOT EXISTS law_judgments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL UNIQUE REFERENCES law_cases(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    finding TEXT NOT NULL CHECK(finding IN ('claimant','respondent','mixed','dismissed')),
    remedy_kind TEXT NOT NULL,
    amount_awarded REAL NOT NULL DEFAULT 0 CHECK(amount_awarded>=0),
    amount_enforced REAL NOT NULL DEFAULT 0 CHECK(amount_enforced>=0),
    status TEXT NOT NULL DEFAULT 'entered' CHECK(status IN ('entered','partially_enforced','enforced','unenforceable')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS law_enforcement_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES law_cases(id) ON DELETE CASCADE,
    judgment_id INTEGER REFERENCES law_judgments(id) ON DELETE SET NULL,
    day INTEGER NOT NULL,
    step_kind TEXT NOT NULL,
    success INTEGER NOT NULL CHECK(success IN (0,1)),
    summary TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_law_enforcement_case ON law_enforcement_steps(case_id,day,id);
""")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('integration01_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('health_capacity_rule','condition_progression_separate_from_care_access')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('agriculture_authority_rule','physical_harvest_to_commercial_stock')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('law_authority_rule','jurisdiction_rule_procedure_enforcement')")


def _migration_69(conn: sqlite3.Connection) -> None:
    """COVERAGE-01: richer population policy/process metadata for the pre-one-year gate."""
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(coverage_registry)").fetchall()}
    if 'population_policy' not in cols:
        conn.execute("ALTER TABLE coverage_registry ADD COLUMN population_policy TEXT NOT NULL DEFAULT 'opening_required'")
    if 'process_keys_json' not in cols:
        conn.execute("ALTER TABLE coverage_registry ADD COLUMN process_keys_json TEXT NOT NULL DEFAULT '[]'")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('coverage01_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('coverage_gate_rule','mechanism_population_autonomy_resolution_cross_domain')")


def _migration_70(conn: sqlite3.Connection) -> None:
    """ONEYEAR-01 accepted integrated unattended-world gate.

    This migration records engine capability, not campaign history. It deliberately creates no
    simulated events, contracts, harvests, projects, people, or other world-state history.
    """
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('one_year_unattended_acceptance','passed')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('one_year_unattended_acceptance_version','2')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('ordinary_economic_substrate_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('conditional_domain_trigger_audit','health_law_war_passed')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('ten_year_gate_rule','coverage_plus_accepted_one_year')")


def _migration_71(conn: sqlite3.Connection) -> None:
    """SCALE-01: population and organizational scale authority.

    The tables hold simulation calibration/denominators, not immutable setting canon.
    They are intentionally independent of rich named-person state so that tens of millions
    of background people do not need to be materialized as actors.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS population_scale_buckets (
        bucket_key TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        population_estimate INTEGER NOT NULL CHECK(population_estimate>=0),
        urban_population INTEGER NOT NULL DEFAULT 0 CHECK(urban_population>=0),
        rural_population INTEGER NOT NULL DEFAULT 0 CHECK(rural_population>=0),
        calibration_status TEXT NOT NULL DEFAULT 'CAMPAIGN_CALIBRATION',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(urban_population+rural_population=population_estimate)
    );
    CREATE TABLE IF NOT EXISTS settlement_scale_profiles (
        location_id INTEGER PRIMARY KEY REFERENCES locations(id) ON DELETE CASCADE,
        bucket_key TEXT NOT NULL REFERENCES population_scale_buckets(bucket_key) ON DELETE RESTRICT,
        population_estimate INTEGER NOT NULL CHECK(population_estimate>=0),
        settlement_tier TEXT NOT NULL,
        named_urban INTEGER NOT NULL DEFAULT 1 CHECK(named_urban IN (0,1)),
        calibration_status TEXT NOT NULL DEFAULT 'CAMPAIGN_CALIBRATION',
        updated_day INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_settlement_scale_bucket ON settlement_scale_profiles(bucket_key,population_estimate DESC);
    CREATE TABLE IF NOT EXISTS institution_scale_profiles (
        institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        scale_band TEXT NOT NULL,
        core_household INTEGER NOT NULL DEFAULT 0 CHECK(core_household>=0),
        direct_members INTEGER NOT NULL DEFAULT 0 CHECK(direct_members>=0),
        active_practitioners INTEGER NOT NULL DEFAULT 0 CHECK(active_practitioners>=0),
        staff_retainers INTEGER NOT NULL DEFAULT 0 CHECK(staff_retainers>=0),
        dependants INTEGER NOT NULL DEFAULT 0 CHECK(dependants>=0),
        affiliates INTEGER NOT NULL DEFAULT 0 CHECK(affiliates>=0),
        sphere_population INTEGER NOT NULL DEFAULT 0 CHECK(sphere_population>=0),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS military_scale_profiles (
        bucket_key TEXT PRIMARY KEY REFERENCES population_scale_buckets(bucket_key) ON DELETE CASCADE,
        standing_professional INTEGER NOT NULL DEFAULT 0 CHECK(standing_professional>=0),
        local_garrison_establishment INTEGER NOT NULL DEFAULT 0 CHECK(local_garrison_establishment>=0),
        trained_reserve INTEGER NOT NULL DEFAULT 0 CHECK(trained_reserve>=0),
        sustainable_field_capacity INTEGER NOT NULL DEFAULT 0 CHECK(sustainable_field_capacity>=0),
        emergency_mobilization_ceiling INTEGER NOT NULL DEFAULT 0 CHECK(emergency_mobilization_ceiling>=0),
        military_age_pool INTEGER NOT NULL DEFAULT 0 CHECK(military_age_pool>=0),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('scale01_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('world_population_calibration','52000000')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('urban_population_calibration','7172000')")


def _migration_72(conn: sqlite3.Connection) -> None:
    """TRADE-01: population-scaled aggregate ordinary trade beneath tracked merchant contracts."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS aggregate_trade_profiles (
        bucket_key TEXT NOT NULL REFERENCES population_scale_buckets(bucket_key) ON DELETE CASCADE,
        good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE,
        monthly_consumption_per_capita REAL NOT NULL CHECK(monthly_consumption_per_capita>=0),
        production_factor REAL NOT NULL CHECK(production_factor>=0),
        reserve_target_months REAL NOT NULL DEFAULT 0.15 CHECK(reserve_target_months>=0),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(bucket_key,good_id)
    );
    CREATE TABLE IF NOT EXISTS aggregate_trade_reserves (
        bucket_key TEXT NOT NULL REFERENCES population_scale_buckets(bucket_key) ON DELETE CASCADE,
        good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE,
        quantity REAL NOT NULL DEFAULT 0 CHECK(quantity>=0),
        updated_day INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(bucket_key,good_id)
    );
    CREATE TABLE IF NOT EXISTS aggregate_trade_corridors (
        bucket_a TEXT NOT NULL REFERENCES population_scale_buckets(bucket_key) ON DELETE CASCADE,
        bucket_b TEXT NOT NULL REFERENCES population_scale_buckets(bucket_key) ON DELETE CASCADE,
        location_a_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        location_b_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        route_resolution TEXT NOT NULL DEFAULT 'tracked_route',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(bucket_a,bucket_b),
        CHECK(bucket_a<bucket_b)
    );
    CREATE TABLE IF NOT EXISTS aggregate_trade_balances (
        period_day INTEGER NOT NULL,
        bucket_key TEXT NOT NULL REFERENCES population_scale_buckets(bucket_key) ON DELETE CASCADE,
        good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE,
        population_served INTEGER NOT NULL CHECK(population_served>=0),
        opening_reserve REAL NOT NULL DEFAULT 0 CHECK(opening_reserve>=0),
        production_quantity REAL NOT NULL DEFAULT 0 CHECK(production_quantity>=0),
        consumption_requirement REAL NOT NULL DEFAULT 0 CHECK(consumption_requirement>=0),
        local_absorption REAL NOT NULL DEFAULT 0 CHECK(local_absorption>=0),
        import_quantity REAL NOT NULL DEFAULT 0 CHECK(import_quantity>=0),
        export_quantity REAL NOT NULL DEFAULT 0 CHECK(export_quantity>=0),
        transport_loss REAL NOT NULL DEFAULT 0 CHECK(transport_loss>=0),
        closing_reserve REAL NOT NULL DEFAULT 0 CHECK(closing_reserve>=0),
        unmet_demand REAL NOT NULL DEFAULT 0 CHECK(unmet_demand>=0),
        unused_surplus REAL NOT NULL DEFAULT 0 CHECK(unused_surplus>=0),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(period_day,bucket_key,good_id)
    );
    CREATE INDEX IF NOT EXISTS idx_aggregate_trade_balance_good_day ON aggregate_trade_balances(good_id,period_day,bucket_key);
    CREATE TABLE IF NOT EXISTS aggregate_trade_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period_day INTEGER NOT NULL,
        origin_bucket_key TEXT NOT NULL REFERENCES population_scale_buckets(bucket_key) ON DELETE CASCADE,
        destination_bucket_key TEXT NOT NULL REFERENCES population_scale_buckets(bucket_key) ON DELETE CASCADE,
        good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE CASCADE,
        dispatched_quantity REAL NOT NULL CHECK(dispatched_quantity>0),
        delivered_quantity REAL NOT NULL CHECK(delivered_quantity>=0),
        loss_quantity REAL NOT NULL DEFAULT 0 CHECK(loss_quantity>=0),
        transport_cost_index REAL NOT NULL DEFAULT 1 CHECK(transport_cost_index>0),
        route_resolution TEXT NOT NULL DEFAULT 'aggregate_macro',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(delivered_quantity+loss_quantity<=dispatched_quantity+0.000001)
    );
    CREATE INDEX IF NOT EXISTS idx_aggregate_trade_flow_day_good ON aggregate_trade_flows(period_day,good_id,origin_bucket_key,destination_bucket_key);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('trade01_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('aggregate_trade_authority_rule','background_bulk_trade_separate_from_tracked_contracts')")



def _migration_73(conn: sqlite3.Connection) -> None:
    """POPBACK-01: disjoint scale-backed population sources + bounded identity reservoirs.

    SCALE-01 remains authoritative for the 52m population denominator.  POPBACK sources are a
    lossless operational decomposition of those scale buckets (named settlements plus residual
    population).  A partition is a bounded identity-resolution sample from exactly one source;
    its sample_size is never added to population totals.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS background_population_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_key TEXT NOT NULL UNIQUE,
        source_kind TEXT NOT NULL CHECK(source_kind IN ('settlement','rural_residual','structural_urban')),
        bucket_key TEXT NOT NULL REFERENCES population_scale_buckets(bucket_key) ON DELETE CASCADE,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        population_estimate INTEGER NOT NULL CHECK(population_estimate>=0),
        urban INTEGER NOT NULL DEFAULT 0 CHECK(urban IN (0,1)),
        calibration_status TEXT NOT NULL DEFAULT 'CAMPAIGN_CALIBRATION',
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_background_population_source_bucket
      ON background_population_sources(bucket_key,source_kind,id);

    CREATE TABLE IF NOT EXISTS background_population_partitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partition_key TEXT NOT NULL UNIQUE,
        source_id INTEGER NOT NULL UNIQUE REFERENCES background_population_sources(id) ON DELETE CASCADE,
        sample_size INTEGER NOT NULL CHECK(sample_size>0),
        source_population_at_seed REAL NOT NULL CHECK(source_population_at_seed>=sample_size),
        state_codec TEXT NOT NULL DEFAULT 'caerness_numpy_npz_v1',
        state_blob BLOB NOT NULL,
        state_sha256 TEXT NOT NULL,
        seed INTEGER NOT NULL,
        last_step_day INTEGER NOT NULL,
        next_step_day INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','retired')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_background_population_due
      ON background_population_partitions(status,next_step_day,id);

    CREATE TABLE IF NOT EXISTS background_population_exposures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day INTEGER NOT NULL,
        partition_id INTEGER NOT NULL REFERENCES background_population_partitions(id) ON DELETE CASCADE,
        local_uid INTEGER NOT NULL,
        domain TEXT NOT NULL,
        delta REAL NOT NULL,
        reason TEXT NOT NULL,
        source_kind TEXT,
        source_id INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_background_population_exposure_identity
      ON background_population_exposures(partition_id,local_uid,day,id);

    CREATE TABLE IF NOT EXISTS background_population_identity_links (
        partition_id INTEGER NOT NULL REFERENCES background_population_partitions(id) ON DELETE CASCADE,
        local_uid INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'background' CHECK(status IN ('background','latent','crystallized','dead','retired')),
        latent_entity_id INTEGER REFERENCES latent_entities(id) ON DELETE SET NULL,
        actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        first_link_day INTEGER NOT NULL,
        last_update_day INTEGER NOT NULL,
        snapshot_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(partition_id,local_uid)
    );
    CREATE INDEX IF NOT EXISTS idx_background_population_link_latent
      ON background_population_identity_links(latent_entity_id,status);
    CREATE INDEX IF NOT EXISTS idx_background_population_link_actor
      ON background_population_identity_links(actor_id,status);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('popback01_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('background_population_authority_rule','scale01_owns_population_totals_sources_are_disjoint_decomposition_partitions_preserve_identity_only')")


def _migration_74(conn: sqlite3.Connection) -> None:
    """POPLIFE-01: live aggregate life-course state over the disjoint POPBACK sources."""
    # Preserve the SCALE-01-derived opening size separately from the live current population.
    cols={str(r[1]) for r in conn.execute("PRAGMA table_info(background_population_sources)").fetchall()}
    if 'baseline_population_estimate' not in cols:
        conn.execute("ALTER TABLE background_population_sources ADD COLUMN baseline_population_estimate INTEGER")
        conn.execute("UPDATE background_population_sources SET baseline_population_estimate=population_estimate WHERE baseline_population_estimate IS NULL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS background_population_age_cohorts (
        source_id INTEGER NOT NULL REFERENCES background_population_sources(id) ON DELETE CASCADE,
        age_band TEXT NOT NULL CHECK(age_band IN ('0_4','5_12','13_17','18_39','40_59','60_plus')),
        population REAL NOT NULL CHECK(population>=0),
        baseline_population REAL NOT NULL CHECK(baseline_population>=0),
        annual_mortality_rate REAL NOT NULL CHECK(annual_mortality_rate>=0 AND annual_mortality_rate<=1),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(source_id,age_band)
    );
    CREATE INDEX IF NOT EXISTS idx_background_population_age_band
      ON background_population_age_cohorts(age_band,source_id);

    CREATE TABLE IF NOT EXISTS background_population_dynamics (
        source_id INTEGER PRIMARY KEY REFERENCES background_population_sources(id) ON DELETE CASCADE,
        annual_birth_rate REAL NOT NULL DEFAULT 0.016 CHECK(annual_birth_rate>=0 AND annual_birth_rate<=1),
        health_modifier REAL NOT NULL DEFAULT 1 CHECK(health_modifier>=0),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','retired')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS background_population_yearly_balances (
        source_id INTEGER NOT NULL REFERENCES background_population_sources(id) ON DELETE CASCADE,
        period_day INTEGER NOT NULL,
        opening_population REAL NOT NULL CHECK(opening_population>=0),
        births REAL NOT NULL CHECK(births>=0),
        deaths REAL NOT NULL CHECK(deaths>=0),
        movement_net REAL NOT NULL DEFAULT 0,
        closing_population REAL NOT NULL CHECK(closing_population>=0),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(source_id,period_day)
    );

    CREATE TABLE IF NOT EXISTS background_population_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day INTEGER NOT NULL,
        from_source_id INTEGER NOT NULL REFERENCES background_population_sources(id) ON DELETE RESTRICT,
        to_source_id INTEGER NOT NULL REFERENCES background_population_sources(id) ON DELETE RESTRICT,
        population REAL NOT NULL CHECK(population>0),
        reason TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(from_source_id<>to_source_id)
    );
    CREATE INDEX IF NOT EXISTS idx_background_population_movement_day
      ON background_population_movements(day,from_source_id,to_source_id,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('poplife01_version','1')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('population_runtime_authority_rule','scale01_is_opening_anchor_live_poplife_sources_may_diverge_causally')")


def _migration_75(conn: sqlite3.Connection) -> None:
    """INFOIDX-01: indexes for causal information scheduling and rumour seeding."""
    conn.executescript("""
    CREATE INDEX IF NOT EXISTS idx_rumours_truth_event
      ON rumours(truth_event_id);
    CREATE INDEX IF NOT EXISTS idx_event_information_rumourable
      ON event_information(visibility,rumorability,event_id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('infoidx01_version','1')")



def _migration_76(conn: sqlite3.Connection) -> None:
    """RESCLEAN-01: remove stale resolution rows that no current owner can process.

    Historical compatibility seeding labeled every simulation profile as entity_kind='actor',
    including institution actors.  Current-canon import separately created the correct
    entity_kind='institution' rows, leaving duplicate institution-as-actor records whose
    clocks could remain overdue forever.  Cohort resolution anchors are fixed aggregate
    anchors and have no autonomous review owner, so they must not advertise due dates.
    """
    # Preserve legacy row identity rather than deleting duplicates.  Deleting these rows at
    # different migration dates changes later INTEGER PRIMARY KEY allocation and therefore
    # breaks restart/replay byte-equivalence even though domain state is identical.  The
    # correct institution row remains authoritative; the historical duplicate is inert.
    conn.execute(
        """UPDATE entity_resolution
           SET review_cadence_days=NULL, next_review_day=NULL,
               reason='legacy compatibility duplicate; proper institution resolution row authoritative',
               metadata_json='{"legacy_compatibility_duplicate":true,"authoritative_kind":"institution"}'
           WHERE entity_kind='actor'
             AND EXISTS (SELECT 1 FROM actors a WHERE a.id=entity_resolution.entity_id AND a.actor_type='institution')
             AND EXISTS (SELECT 1 FROM entity_resolution proper
                         WHERE proper.entity_kind='institution' AND proper.entity_id=entity_resolution.entity_id)"""
    )
    conn.execute(
        """UPDATE entity_resolution
           SET review_cadence_days=NULL,next_review_day=NULL
           WHERE entity_kind='cohort' AND locked_min_level='STRUCTURAL'"""
    )
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('resclean01_version','1')")


def _migration_77(conn: sqlite3.Connection) -> None:
    """ORGAGENCY-01: shared institutional inheritance/regime/faction/pressure/capability substrate."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS organization_agency_profiles (
        institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        institutional_inheritance_json TEXT NOT NULL DEFAULT '{}', culture_inertia REAL NOT NULL DEFAULT .75 CHECK(culture_inertia BETWEEN 0 AND 1),
        culture_drift_rate REAL NOT NULL DEFAULT .04 CHECK(culture_drift_rate BETWEEN 0 AND 1), governance_mode TEXT NOT NULL DEFAULT 'institutional',
        last_review_day INTEGER NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE IF NOT EXISTS organization_regimes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        leader_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, regime_kind TEXT NOT NULL DEFAULT 'continuity', mandate_json TEXT NOT NULL DEFAULT '{}',
        worldview_json TEXT NOT NULL DEFAULT '{}', started_day INTEGER NOT NULL, ended_day INTEGER, status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','ended','disputed')),
        metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE UNIQUE INDEX IF NOT EXISTS idx_org_regime_one_active ON organization_regimes(institution_actor_id) WHERE status='active';
    CREATE TABLE IF NOT EXISTS organization_factions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE, faction_key TEXT NOT NULL,
        name TEXT, sponsor_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, influence REAL NOT NULL DEFAULT 0 CHECK(influence BETWEEN 0 AND 100),
        cohesion REAL NOT NULL DEFAULT 50 CHECK(cohesion BETWEEN 0 AND 100), positions_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','dormant','defeated','merged','dissolved')), created_day INTEGER NOT NULL DEFAULT 0,
        updated_day INTEGER NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(institution_actor_id,faction_key));
    CREATE TABLE IF NOT EXISTS organization_pressures (
        id INTEGER PRIMARY KEY AUTOINCREMENT, institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE, pressure_key TEXT NOT NULL,
        domain TEXT NOT NULL, target_kind TEXT, target_id INTEGER, intensity REAL NOT NULL DEFAULT 0 CHECK(intensity>=0), urgency REAL NOT NULL DEFAULT 0 CHECK(urgency BETWEEN 0 AND 100),
        source_kind TEXT, source_id INTEGER, status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','resolved','expired')), created_day INTEGER NOT NULL DEFAULT 0,
        updated_day INTEGER NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(institution_actor_id,pressure_key,status));
    CREATE INDEX IF NOT EXISTS idx_org_pressures_active ON organization_pressures(institution_actor_id,status,intensity DESC,id);
    CREATE TABLE IF NOT EXISTS organization_capabilities (
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE, capability_key TEXT NOT NULL, domain TEXT NOT NULL,
        capacity REAL NOT NULL DEFAULT 0 CHECK(capacity BETWEEN 0 AND 100), readiness REAL NOT NULL DEFAULT 0 CHECK(readiness BETWEEN 0 AND 100),
        basis_json TEXT NOT NULL DEFAULT '{}', updated_day INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(institution_actor_id,capability_key));
    CREATE TABLE IF NOT EXISTS organization_strategy_positions (
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE, issue_key TEXT NOT NULL, domain TEXT NOT NULL, target_kind TEXT, target_id INTEGER,
        position_json TEXT NOT NULL DEFAULT '{}', confidence REAL NOT NULL DEFAULT .5 CHECK(confidence BETWEEN 0 AND 1), updated_day INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(institution_actor_id,issue_key));
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('orgagency01_version','1')")


def _migration_78(conn: sqlite3.Connection) -> None:
    """ORGIDENT-01: underworld organizations participate through institution identity rather than a parallel ontology."""
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('underworld_orgagency_bridge_version','1')")


def _migration_79(conn: sqlite3.Connection) -> None:
    """POLITYAGENCY-01: issue-specific government agency and structural government actors."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS polity_issue_states (
        polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE, other_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
        issue_key TEXT NOT NULL, issue_kind TEXT NOT NULL, interest REAL NOT NULL DEFAULT 50 CHECK(interest BETWEEN 0 AND 100), pressure REAL NOT NULL DEFAULT 0 CHECK(pressure BETWEEN 0 AND 100),
        restraint REAL NOT NULL DEFAULT 50 CHECK(restraint BETWEEN 0 AND 100), preferred_posture TEXT NOT NULL DEFAULT 'cautious' CHECK(preferred_posture IN ('cooperative','cautious','competitive','hardline','hostile')),
        updated_day INTEGER NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(polity_id,other_polity_id,issue_key), CHECK(polity_id<>other_polity_id));
    CREATE INDEX IF NOT EXISTS idx_polity_issue_pair ON polity_issue_states(polity_id,other_polity_id,pressure DESC,issue_key);
    CREATE TABLE IF NOT EXISTS polity_government_actors (
        polity_id INTEGER PRIMARY KEY REFERENCES political_polities(id) ON DELETE CASCADE, decision_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        authority_kind TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}');
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('polityagency01_version','1')")


def _migration_80(conn: sqlite3.Connection) -> None:
    """CONFLICT-01: causal geopolitical pressure/incidents/response layer feeding WAR-01."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS conflict_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT, channel_key TEXT NOT NULL UNIQUE, polity_a_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
        polity_b_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE, issue_kind TEXT NOT NULL, location_a_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        location_b_id INTEGER REFERENCES locations(id) ON DELETE SET NULL, base_pressure REAL NOT NULL DEFAULT 0 CHECK(base_pressure BETWEEN 0 AND 100),
        volatility REAL NOT NULL DEFAULT .2 CHECK(volatility BETWEEN 0 AND 1), restraint REAL NOT NULL DEFAULT 50 CHECK(restraint BETWEEN 0 AND 100),
        incident_threshold REAL NOT NULL DEFAULT 55 CHECK(incident_threshold BETWEEN 1 AND 100), accumulated_pressure REAL NOT NULL DEFAULT 0 CHECK(accumulated_pressure>=0),
        review_cadence_days INTEGER NOT NULL DEFAULT 30 CHECK(review_cadence_days>=1), last_review_day INTEGER NOT NULL DEFAULT 0, next_review_day INTEGER NOT NULL DEFAULT 30,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','dormant','resolved')), metadata_json TEXT NOT NULL DEFAULT '{}', CHECK(polity_a_id<>polity_b_id));
    CREATE INDEX IF NOT EXISTS idx_conflict_channels_due ON conflict_channels(status,next_review_day,id);
    CREATE TABLE IF NOT EXISTS conflict_incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER REFERENCES conflict_channels(id) ON DELETE SET NULL, day INTEGER NOT NULL,
        initiator_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE, target_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE,
        incident_kind TEXT NOT NULL, severity REAL NOT NULL CHECK(severity BETWEEN 0 AND 100), location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','responded','escalated','settled','expired')),
        response_state TEXT NOT NULL DEFAULT 'none' CHECK(response_state IN ('none','formal_demand','retaliation','settlement','campaign','other')),
        responded_day INTEGER, response_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL, metadata_json TEXT NOT NULL DEFAULT '{}', CHECK(initiator_polity_id<>target_polity_id));
    CREATE INDEX IF NOT EXISTS idx_conflict_incidents_target ON conflict_incidents(target_polity_id,status,day,id);
    CREATE TABLE IF NOT EXISTS conflict_responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id INTEGER NOT NULL REFERENCES conflict_incidents(id) ON DELETE CASCADE, day INTEGER NOT NULL,
        responding_polity_id INTEGER NOT NULL REFERENCES political_polities(id) ON DELETE CASCADE, actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        response_kind TEXT NOT NULL, operation_id INTEGER REFERENCES war_campaign_operations(id) ON DELETE SET NULL, metadata_json TEXT NOT NULL DEFAULT '{}');
    CREATE UNIQUE INDEX IF NOT EXISTS idx_conflict_one_formal_response ON conflict_responses(incident_id,responding_polity_id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('conflict01_version','1')")


def _migration_81(conn: sqlite3.Connection) -> None:
    """ORGLIFE-01: causal organization life cycles, including polity/country formation, fission, absorption and dissolution."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS organization_lifecycle_profiles (
        institution_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        lifecycle_kind TEXT NOT NULL,
        lifecycle_status TEXT NOT NULL DEFAULT 'stable' CHECK(lifecycle_status IN ('forming','rising','stable','declining','crisis','fragmenting','absorbing','absorbed','dissolving','dissolved')),
        vitality REAL NOT NULL DEFAULT 50 CHECK(vitality BETWEEN 0 AND 100),
        cohesion REAL NOT NULL DEFAULT 50 CHECK(cohesion BETWEEN 0 AND 100),
        continuity REAL NOT NULL DEFAULT 50 CHECK(continuity BETWEEN 0 AND 100),
        expansion_capacity REAL NOT NULL DEFAULT 50 CHECK(expansion_capacity BETWEEN 0 AND 100),
        sovereignty_status TEXT NOT NULL DEFAULT 'nonstate' CHECK(sovereignty_status IN ('nonstate','sovereign','dependent','contested','fragmenting','dissolved')),
        parent_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        last_review_day INTEGER NOT NULL DEFAULT 0,
        next_review_day INTEGER NOT NULL DEFAULT 90,
        review_cadence_days INTEGER NOT NULL DEFAULT 90 CHECK(review_cadence_days>=1),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_org_lifecycle_due ON organization_lifecycle_profiles(lifecycle_status,next_review_day,institution_actor_id);

    CREATE TABLE IF NOT EXISTS polity_lifecycle_profiles (
        polity_id INTEGER PRIMARY KEY REFERENCES political_polities(id) ON DELETE CASCADE,
        sovereignty_status TEXT NOT NULL DEFAULT 'sovereign' CHECK(sovereignty_status IN ('sovereign','dependent','contested','fragmenting','dissolved')),
        territorial_integrity REAL NOT NULL DEFAULT 50 CHECK(territorial_integrity BETWEEN 0 AND 100),
        center_control REAL NOT NULL DEFAULT 50 CHECK(center_control BETWEEN 0 AND 100),
        elite_cohesion REAL NOT NULL DEFAULT 50 CHECK(elite_cohesion BETWEEN 0 AND 100),
        separatist_pressure REAL NOT NULL DEFAULT 0 CHECK(separatist_pressure BETWEEN 0 AND 100),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS organization_lifecycle_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        other_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
        other_polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
        cause_kind TEXT,
        cause_id INTEGER,
        summary TEXT NOT NULL,
        detail_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_org_lifecycle_events_entity ON organization_lifecycle_events(institution_actor_id,day,id);
    CREATE INDEX IF NOT EXISTS idx_org_lifecycle_events_type ON organization_lifecycle_events(event_type,day,id);

    CREATE TABLE IF NOT EXISTS organization_lineage_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        predecessor_institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        successor_institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        link_kind TEXT NOT NULL CHECK(link_kind IN ('formation','secession','split','merger','absorption','replacement','federation')),
        day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(predecessor_institution_actor_id,successor_institution_actor_id,link_kind,day),
        CHECK(predecessor_institution_actor_id<>successor_institution_actor_id)
    );
    CREATE INDEX IF NOT EXISTS idx_org_lineage_successor ON organization_lineage_links(successor_institution_actor_id,day,id);
    """)

    # Commercial taxonomy repair.  Historical slices used ``merchant house`` as the generic
    # enterprise kind for wholesalers, which is not evidence that every successful one-person
    # concern had become a durable merchant institution.  Preserve the enterprise and candidate
    # history, but reinterpret still-uncrystallized candidates as merchant *firms* and recompute
    # whether organizational depth actually warrants institution persistence.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='emergent_institution_candidates'").fetchone():
        import json
        day_row = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()
        now = int(day_row[0]) if day_row else 0
        candidates = conn.execute("""SELECT * FROM emergent_institution_candidates
                                   WHERE candidate_kind='merchant house' AND status IN ('forming','eligible')
                                   ORDER BY id""").fetchall()
        has_staff = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enterprise_staff'").fetchone() is not None
        has_contracts = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchant_trade_contracts'").fetchone() is not None
        for candidate in candidates:
            eid = candidate['enterprise_id']
            resources = json.loads(candidate['resources_json'] or '{}')
            active_staff = 0
            completed = 0
            markets = 0
            age_days = 0
            if eid is not None:
                ent = conn.execute("SELECT created_day,capital,cash,debt FROM civilian_enterprises WHERE id=?", (int(eid),)).fetchone()
                if ent is not None:
                    age_days = max(0, now - int(ent['created_day']))
                    resources.update({'capital':float(ent['capital']), 'cash':float(ent['cash']), 'debt':float(ent['debt'])})
                if has_staff:
                    active_staff = int(conn.execute("SELECT COUNT(*) FROM enterprise_staff WHERE enterprise_id=? AND status='active'", (int(eid),)).fetchone()[0])
                if has_contracts:
                    completed = int(conn.execute("""SELECT COUNT(*) FROM merchant_trade_contracts
                                                    WHERE (buyer_enterprise_id=? OR seller_enterprise_id=?)
                                                      AND status IN ('fulfilled','settled','delivered')""", (int(eid),int(eid))).fetchone()[0])
                    markets = int(conn.execute("""SELECT COUNT(DISTINCT destination_location_id) FROM merchant_trade_contracts
                                                  WHERE (buyer_enterprise_id=? OR seller_enterprise_id=?)
                                                    AND destination_location_id IS NOT NULL""", (int(eid),int(eid))).fetchone()[0])
            resources.update({
                'business_age_days':age_days, 'active_staff':active_staff, 'branch_count':int(resources.get('branch_count') or 0),
                'completed_trade_contracts':completed, 'distinct_trade_locations':markets, 'institutional_form':'merchant_firm',
            })
            depth = active_staff >= 2 or int(resources.get('branch_count') or 0) >= 2 or (completed >= 12 and markets >= 3)
            eligible = float(candidate['significance_score'] or 0) >= 45.0 and age_days >= 3 * 365 and depth
            conn.execute("""UPDATE emergent_institution_candidates
                            SET candidate_kind='merchant firm',resources_json=?,status=?,updated_day=?
                            WHERE id=?""",
                         (json.dumps(resources,sort_keys=True,separators=(',',':')), 'eligible' if eligible else 'forming', now, int(candidate['id'])))

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('orglife01_version','1')")


def _migration_82(conn: sqlite3.Connection) -> None:
    """SEEK-01: inbound demand, discoverable capability and provider-seeking."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS seekable_offerings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        provider_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        provider_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        offer_kind TEXT NOT NULL CHECK(offer_kind IN ('goods','service','instruction','information','employment','patronage','other')),
        domain_key TEXT NOT NULL,
        subject_key TEXT NOT NULL,
        quality REAL NOT NULL DEFAULT 50 CHECK(quality BETWEEN 0 AND 100),
        capacity_per_30 REAL NOT NULL DEFAULT 1 CHECK(capacity_per_30>=0),
        availability REAL NOT NULL DEFAULT 100 CHECK(availability BETWEEN 0 AND 100),
        public_reputation REAL NOT NULL DEFAULT 50 CHECK(public_reputation BETWEEN 0 AND 100),
        visibility REAL NOT NULL DEFAULT 50 CHECK(visibility BETWEEN 0 AND 100),
        scarcity REAL NOT NULL DEFAULT 50 CHECK(scarcity BETWEEN 0 AND 100),
        access_mode TEXT NOT NULL DEFAULT 'open' CHECK(access_mode IN ('open','appointment','visit','referral','rumoured','invitation','closed')),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','closed')),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        next_review_day INTEGER NOT NULL DEFAULT 30,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_seek_offering_match ON seekable_offerings(status,domain_key,subject_key,offer_kind,id);
    CREATE INDEX IF NOT EXISTS idx_seek_offering_provider ON seekable_offerings(provider_actor_id,status,id);

    CREATE TABLE IF NOT EXISTS actor_seek_intents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seeker_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        need_kind TEXT NOT NULL,
        domain_key TEXT NOT NULL,
        subject_key TEXT NOT NULL,
        intensity REAL NOT NULL DEFAULT 50 CHECK(intensity BETWEEN 0 AND 100),
        min_quality REAL NOT NULL DEFAULT 0 CHECK(min_quality BETWEEN 0 AND 100),
        quantity REAL NOT NULL DEFAULT 1 CHECK(quantity>0),
        budget REAL,
        preferred_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        selected_offering_id INTEGER REFERENCES seekable_offerings(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'searching' CHECK(status IN ('searching','traveling','approaching','fulfilled','blocked','abandoned','expired')),
        source_kind TEXT,
        source_id INTEGER,
        created_day INTEGER NOT NULL,
        last_review_day INTEGER NOT NULL,
        next_review_day INTEGER NOT NULL,
        expires_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_seek_intent_due ON actor_seek_intents(status,next_review_day,id);
    CREATE INDEX IF NOT EXISTS idx_seek_intent_actor ON actor_seek_intents(seeker_actor_id,status,id);

    CREATE TABLE IF NOT EXISTS seek_awareness (
        seeker_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        offering_id INTEGER NOT NULL REFERENCES seekable_offerings(id) ON DELETE CASCADE,
        confidence REAL NOT NULL DEFAULT .5 CHECK(confidence BETWEEN 0 AND 1),
        location_certainty REAL NOT NULL DEFAULT .5 CHECK(location_certainty BETWEEN 0 AND 1),
        source_kind TEXT NOT NULL,
        learned_day INTEGER NOT NULL,
        updated_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(seeker_actor_id,offering_id)
    );

    CREATE TABLE IF NOT EXISTS seek_procurement_contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        intent_id INTEGER REFERENCES actor_seek_intents(id) ON DELETE SET NULL,
        offering_id INTEGER REFERENCES seekable_offerings(id) ON DELETE SET NULL,
        buyer_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        buyer_polity_id INTEGER REFERENCES political_polities(id) ON DELETE SET NULL,
        seller_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        seller_enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        good_id INTEGER NOT NULL REFERENCES market_goods(id) ON DELETE RESTRICT,
        quantity REAL NOT NULL CHECK(quantity>0),
        unit_price REAL NOT NULL CHECK(unit_price>0),
        agreed_quality REAL NOT NULL DEFAULT 50 CHECK(agreed_quality BETWEEN 0 AND 100),
        origin_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
        destination_location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
        agreed_day INTEGER NOT NULL,
        due_day INTEGER NOT NULL,
        shipment_id INTEGER REFERENCES commercial_shipments(id) ON DELETE SET NULL,
        fulfilled_day INTEGER,
        status TEXT NOT NULL DEFAULT 'accepted' CHECK(status IN ('accepted','in_transit','fulfilled','breached','cancelled')),
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_seek_procurement_due ON seek_procurement_contracts(status,due_day,id);
    """)
    conn.execute("INSERT OR IGNORE INTO market_goods(good_key,name,category,base_price,unit,perishability,skill_intensity,luxury,notes) VALUES ('horses_remounts','Horses and military remounts','livestock',18,'horse',0.02,0.75,0.25,'Ordinary riding horses, bred remounts and military-quality horses; quality is separately represented by provider/contract state.')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('seek01_version','1')")



def _migration_83(conn: sqlite3.Connection) -> None:
    """ATTENTION-01: strategic relevance and institution-to-person role offers."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS strategic_attention_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observer_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        observer_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
        target_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        domain_key TEXT NOT NULL,
        interest_kind TEXT NOT NULL CHECK(interest_kind IN (
            'procure','commission','recruit','appoint','patronize','partner','invest','affiliate',
            'protect','regulate','investigate','surveil','challenge','coerce','suppress','acquire','imitate','other'
        )),
        salience REAL NOT NULL DEFAULT 50 CHECK(salience BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'observing' CHECK(status IN (
            'observing','planning','approaching','accepted','rejected','fulfilled','blocked','abandoned','expired'
        )),
        source_kind TEXT,
        source_id INTEGER,
        created_day INTEGER NOT NULL,
        last_review_day INTEGER NOT NULL,
        next_review_day INTEGER NOT NULL,
        expires_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(observer_actor_id<>target_actor_id)
    );
    CREATE INDEX IF NOT EXISTS idx_attention_due ON strategic_attention_cases(status,next_review_day,id);
    CREATE INDEX IF NOT EXISTS idx_attention_target ON strategic_attention_cases(target_actor_id,status,interest_kind,id);
    CREATE INDEX IF NOT EXISTS idx_attention_observer ON strategic_attention_cases(observer_actor_id,status,interest_kind,id);

    CREATE TABLE IF NOT EXISTS institutional_appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointing_institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        holder_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        appointment_key TEXT NOT NULL,
        title TEXT NOT NULL,
        domain_key TEXT NOT NULL,
        appointment_kind TEXT NOT NULL DEFAULT 'technical_office',
        career_kind TEXT,
        responsibility_key TEXT,
        source_attention_case_id INTEGER REFERENCES strategic_attention_cases(id) ON DELETE SET NULL,
        source_interaction_id INTEGER REFERENCES interactions(id) ON DELETE SET NULL,
        started_day INTEGER NOT NULL,
        ended_day INTEGER,
        stipend REAL NOT NULL DEFAULT 0 CHECK(stipend>=0),
        exclusivity REAL NOT NULL DEFAULT 0 CHECK(exclusivity BETWEEN 0 AND 1),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended','ended','revoked')),
        obligations_json TEXT NOT NULL DEFAULT '{}',
        privileges_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(appointing_institution_actor_id,holder_actor_id,appointment_key,started_day)
    );
    CREATE INDEX IF NOT EXISTS idx_appointment_holder ON institutional_appointments(holder_actor_id,status,id);
    CREATE INDEX IF NOT EXISTS idx_appointment_institution ON institutional_appointments(appointing_institution_actor_id,status,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('attention01_version','1')")


def _migration_84(conn: sqlite3.Connection) -> None:
    """OPPORTUNITY-01: typed proposals, negotiated terms, asset/control interests and symmetric search."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS opportunity_proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposer_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        proposer_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        target_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        target_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        proposal_kind TEXT NOT NULL CHECK(proposal_kind IN (
            'purchase','sale','commission','supply_contract','first_refusal','exclusive_supply',
            'temporary_service','permanent_service','employment','appointment','retainership',
            'patronage','partnership','investment','acquisition','incorporation','lease','license',
            'affiliation','instruction','protection','access_right','asset_purchase','asset_lease','other'
        )),
        domain_key TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN (
            'draft','pending','countered','accepted','rejected','withdrawn','expired','fulfilled','breached'
        )),
        source_attention_case_id INTEGER REFERENCES strategic_attention_cases(id) ON DELETE SET NULL,
        parent_proposal_id INTEGER REFERENCES opportunity_proposals(id) ON DELETE SET NULL,
        source_kind TEXT,
        source_id INTEGER,
        created_day INTEGER NOT NULL,
        expires_day INTEGER,
        accepted_day INTEGER,
        fulfilled_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(target_actor_id IS NOT NULL OR target_institution_actor_id IS NOT NULL)
    );
    CREATE INDEX IF NOT EXISTS idx_opportunity_proposal_target ON opportunity_proposals(status,target_actor_id,target_institution_actor_id,id);
    CREATE INDEX IF NOT EXISTS idx_opportunity_proposal_source ON opportunity_proposals(source_attention_case_id,status,id);

    CREATE TABLE IF NOT EXISTS opportunity_proposal_terms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL REFERENCES opportunity_proposals(id) ON DELETE CASCADE,
        term_kind TEXT NOT NULL CHECK(term_kind IN (
            'cash_payment','recurring_stipend','enterprise_legal_ownership','enterprise_beneficial_control',
            'enterprise_operation','appointment','membership','first_refusal','exclusivity','supply_commitment',
            'service_commitment','duration','residence','land_grant','asset_transfer','asset_use_right',
            'revenue_share','access_right','termination_right','noncompete','other'
        )),
        subject_kind TEXT CHECK(subject_kind IN ('actor','institution','enterprise','asset','good','location','other')),
        subject_id INTEGER,
        required INTEGER NOT NULL DEFAULT 1 CHECK(required IN (0,1)),
        execution_order INTEGER NOT NULL DEFAULT 100,
        value_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','executed','waived','failed')),
        UNIQUE(proposal_id,term_kind,subject_kind,subject_id,execution_order)
    );
    CREATE INDEX IF NOT EXISTS idx_opportunity_terms_proposal ON opportunity_proposal_terms(proposal_id,execution_order,id);

    CREATE TABLE IF NOT EXISTS opportunity_agreements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL UNIQUE REFERENCES opportunity_proposals(id) ON DELETE RESTRICT,
        agreement_kind TEXT NOT NULL,
        effective_day INTEGER NOT NULL,
        end_day INTEGER,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','fulfilled','ended','breached','revoked')),
        terms_snapshot_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS enterprise_control_interests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enterprise_id INTEGER NOT NULL REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        holder_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
        holder_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
        interest_kind TEXT NOT NULL CHECK(interest_kind IN ('legal_owner','beneficial_controller','operator','revenue_share')),
        share REAL NOT NULL DEFAULT 1 CHECK(share>=0 AND share<=1),
        started_day INTEGER NOT NULL,
        ended_day INTEGER,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','ended','disputed')),
        source_proposal_id INTEGER REFERENCES opportunity_proposals(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK((holder_actor_id IS NOT NULL) <> (holder_institution_actor_id IS NOT NULL))
    );
    CREATE INDEX IF NOT EXISTS idx_enterprise_control_active ON enterprise_control_interests(enterprise_id,status,interest_kind,id);

    CREATE TABLE IF NOT EXISTS strategic_assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_kind TEXT NOT NULL,
        name TEXT NOT NULL,
        owner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        owner_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        quality REAL NOT NULL DEFAULT 50 CHECK(quality BETWEEN 0 AND 100),
        rarity REAL NOT NULL DEFAULT 50 CHECK(rarity BETWEEN 0 AND 100),
        public_visibility REAL NOT NULL DEFAULT 0 CHECK(public_visibility BETWEEN 0 AND 100),
        estimated_value REAL NOT NULL DEFAULT 0 CHECK(estimated_value>=0),
        offered_for_sale INTEGER NOT NULL DEFAULT 0 CHECK(offered_for_sale IN (0,1)),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','lost','destroyed','transferred','historical')),
        created_day INTEGER NOT NULL,
        updated_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(owner_actor_id IS NOT NULL OR owner_institution_actor_id IS NOT NULL)
    );
    CREATE INDEX IF NOT EXISTS idx_strategic_assets_kind ON strategic_assets(asset_kind,status,quality,rarity,id);
    CREATE INDEX IF NOT EXISTS idx_strategic_assets_owner ON strategic_assets(owner_actor_id,owner_institution_actor_id,status,id);

    CREATE TABLE IF NOT EXISTS service_engagements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        client_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        provider_kind TEXT NOT NULL CHECK(provider_kind IN ('actor','institution','enterprise')),
        provider_id INTEGER NOT NULL,
        domain_key TEXT NOT NULL,
        service_kind TEXT NOT NULL,
        scope_json TEXT NOT NULL DEFAULT '{}',
        compensation_json TEXT NOT NULL DEFAULT '{}',
        exclusivity REAL NOT NULL DEFAULT 0 CHECK(exclusivity BETWEEN 0 AND 1),
        started_day INTEGER NOT NULL,
        end_day INTEGER,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','ended','breached','cancelled')),
        source_proposal_id INTEGER REFERENCES opportunity_proposals(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(client_actor_id IS NOT NULL OR client_institution_actor_id IS NOT NULL)
    );
    CREATE INDEX IF NOT EXISTS idx_service_engagement_provider ON service_engagements(provider_kind,provider_id,status,id);
    CREATE INDEX IF NOT EXISTS idx_service_engagement_client ON service_engagements(client_institution_actor_id,client_actor_id,status,id);

    CREATE TABLE IF NOT EXISTS contractual_rights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grantor_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        grantor_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        grantee_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        grantee_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        right_kind TEXT NOT NULL CHECK(right_kind IN ('first_refusal','exclusivity','supply_priority','use_right','access_right','noncompete','other')),
        subject_kind TEXT NOT NULL CHECK(subject_kind IN ('enterprise','asset','good','service','location','other')),
        subject_id INTEGER,
        scope_json TEXT NOT NULL DEFAULT '{}',
        started_day INTEGER NOT NULL,
        ended_day INTEGER,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','ended','revoked','breached')),
        source_proposal_id INTEGER REFERENCES opportunity_proposals(id) ON DELETE SET NULL,
        CHECK((grantor_actor_id IS NOT NULL) OR (grantor_institution_actor_id IS NOT NULL)),
        CHECK((grantee_actor_id IS NOT NULL) OR (grantee_institution_actor_id IS NOT NULL))
    );
    CREATE INDEX IF NOT EXISTS idx_contractual_rights_subject ON contractual_rights(subject_kind,subject_id,status,right_kind,id);

    CREATE TABLE IF NOT EXISTS opportunity_capabilities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_kind TEXT NOT NULL CHECK(subject_kind IN ('actor','institution','enterprise')),
        subject_id INTEGER NOT NULL,
        domain_key TEXT NOT NULL,
        capability_key TEXT NOT NULL,
        quality REAL NOT NULL DEFAULT 50 CHECK(quality BETWEEN 0 AND 100),
        capacity REAL NOT NULL DEFAULT 50 CHECK(capacity BETWEEN 0 AND 100),
        public_visibility REAL NOT NULL DEFAULT 0 CHECK(public_visibility BETWEEN 0 AND 100),
        availability REAL NOT NULL DEFAULT 100 CHECK(availability BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','strained','inactive','ended')),
        source_kind TEXT,
        source_id INTEGER,
        updated_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(subject_kind,subject_id,domain_key,capability_key)
    );
    CREATE INDEX IF NOT EXISTS idx_opportunity_capability_search ON opportunity_capabilities(domain_key,capability_key,status,quality,public_visibility,id);

    CREATE TABLE IF NOT EXISTS opportunity_searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seeker_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        seeker_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        search_kind TEXT NOT NULL CHECK(search_kind IN ('talent','service_provider','asset','enterprise','partner','other')),
        domain_key TEXT NOT NULL,
        role_key TEXT,
        min_quality REAL NOT NULL DEFAULT 0 CHECK(min_quality BETWEEN 0 AND 100),
        intensity REAL NOT NULL DEFAULT 50 CHECK(intensity BETWEEN 0 AND 100),
        preferred_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        willingness_to_poach REAL NOT NULL DEFAULT 0 CHECK(willingness_to_poach BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'searching' CHECK(status IN ('searching','approaching','fulfilled','abandoned','expired')),
        created_day INTEGER NOT NULL,
        next_review_day INTEGER NOT NULL,
        expires_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_opportunity_search_due ON opportunity_searches(status,next_review_day,id);

    CREATE TABLE IF NOT EXISTS opportunity_search_results (
        search_id INTEGER NOT NULL REFERENCES opportunity_searches(id) ON DELETE CASCADE,
        candidate_kind TEXT NOT NULL CHECK(candidate_kind IN ('actor','institution','asset','enterprise')),
        candidate_id INTEGER NOT NULL,
        fit_score REAL NOT NULL,
        confidence REAL NOT NULL DEFAULT 0 CHECK(confidence BETWEEN 0 AND 1),
        availability REAL NOT NULL DEFAULT 0 CHECK(availability BETWEEN 0 AND 1),
        discovered_day INTEGER NOT NULL,
        blockers_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(search_id,candidate_kind,candidate_id)
    );
    """)
    # Seed explicit personal ownership interests from the legacy enterprise owner field.
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]) if _has_table(conn, "world_state") else 0
    conn.execute("""INSERT INTO enterprise_control_interests(enterprise_id,holder_actor_id,interest_kind,share,started_day,status,metadata_json)
                    SELECT e.id,e.owner_actor_id,'legal_owner',1.0,?,'active','{"seeded_from":"civilian_enterprises.owner_actor_id"}'
                    FROM civilian_enterprises e WHERE e.owner_actor_id IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM enterprise_control_interests i WHERE i.enterprise_id=e.id AND i.status='active' AND i.interest_kind='legal_owner')""", (day,))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('opportunity01_version','1')")


def _migration_85(conn: sqlite3.Connection) -> None:
    """ADAPT-01: institution plans, reusable role definitions and exceptional role creation."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS institutional_roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        role_key TEXT NOT NULL,
        title TEXT NOT NULL,
        domain_key TEXT NOT NULL,
        role_kind TEXT NOT NULL DEFAULT 'technical_role' CHECK(role_kind IN (
            'office','command','technical_role','staff_role','advisory_role','service_role','other'
        )),
        capacity_slots INTEGER NOT NULL DEFAULT 1 CHECK(capacity_slots>=1),
        durable INTEGER NOT NULL DEFAULT 1 CHECK(durable IN (0,1)),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','retired')),
        created_day INTEGER NOT NULL,
        ended_day INTEGER,
        source_kind TEXT,
        source_id INTEGER,
        remit_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(institution_actor_id,role_key)
    );
    CREATE INDEX IF NOT EXISTS idx_institutional_roles_open ON institutional_roles(institution_actor_id,status,domain_key,role_key,id);

    CREATE TABLE IF NOT EXISTS institutional_programs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        program_key TEXT NOT NULL,
        title TEXT NOT NULL,
        domain_key TEXT NOT NULL,
        program_kind TEXT NOT NULL DEFAULT 'initiative' CHECK(program_kind IN (
            'standing_program','project','reform','initiative','procurement','training','security','other'
        )),
        horizon TEXT NOT NULL DEFAULT 'durable' CHECK(horizon IN ('one_off','temporary','recurring','durable')),
        priority REAL NOT NULL DEFAULT 50 CHECK(priority BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'planning' CHECK(status IN ('planning','active','paused','completed','abandoned')),
        started_day INTEGER NOT NULL,
        ended_day INTEGER,
        source_kind TEXT,
        source_id INTEGER,
        objective_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(institution_actor_id,program_key)
    );
    CREATE INDEX IF NOT EXISTS idx_institutional_programs_active ON institutional_programs(institution_actor_id,status,domain_key,priority,id);

    CREATE TABLE IF NOT EXISTS institutional_plan_adaptations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        program_id INTEGER REFERENCES institutional_programs(id) ON DELETE SET NULL,
        role_id INTEGER REFERENCES institutional_roles(id) ON DELETE SET NULL,
        adaptation_kind TEXT NOT NULL CHECK(adaptation_kind IN (
            'reuse_role','temporary_contract','standing_service','reshape_program','create_program','create_role','no_structural_change'
        )),
        source_kind TEXT NOT NULL,
        source_id INTEGER,
        candidate_kind TEXT,
        candidate_id INTEGER,
        created_day INTEGER NOT NULL,
        rationale TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_plan_adaptation_inst ON institutional_plan_adaptations(institution_actor_id,created_day,id);
    """)
    cols={r[1] for r in conn.execute("PRAGMA table_info(institutional_appointments)").fetchall()}
    if 'role_id' not in cols:
        conn.execute("ALTER TABLE institutional_appointments ADD COLUMN role_id INTEGER REFERENCES institutional_roles(id) ON DELETE SET NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_appointment_role ON institutional_appointments(role_id,status,id)")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('adapt01_version','1')")


def _migration_86(conn: sqlite3.Connection) -> None:
    """PATRON-01: personal/institutional patronage as an independent relationship, not employment."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS patronage_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patron_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        domain_key TEXT NOT NULL,
        interest_level REAL NOT NULL DEFAULT 50 CHECK(interest_level BETWEEN 0 AND 100),
        taste_json TEXT NOT NULL DEFAULT '{}',
        prestige_motive REAL NOT NULL DEFAULT 0 CHECK(prestige_motive BETWEEN 0 AND 100),
        developmental_motive REAL NOT NULL DEFAULT 0 CHECK(developmental_motive BETWEEN 0 AND 100),
        ideological_motive REAL NOT NULL DEFAULT 0 CHECK(ideological_motive BETWEEN 0 AND 100),
        preferred_support_kind TEXT NOT NULL DEFAULT 'stipend' CHECK(preferred_support_kind IN (
            'stipend','commission_series','residency','workshop_support','scholarship','mixed','other'
        )),
        max_amount_per_cycle REAL NOT NULL DEFAULT 0 CHECK(max_amount_per_cycle>=0),
        recurrence_days INTEGER NOT NULL DEFAULT 30 CHECK(recurrence_days>=1),
        openness_to_emerging REAL NOT NULL DEFAULT 50 CHECK(openness_to_emerging BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','ended')),
        created_day INTEGER NOT NULL,
        updated_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(patron_actor_id,domain_key)
    );
    CREATE INDEX IF NOT EXISTS idx_patronage_preferences ON patronage_preferences(status,domain_key,interest_level,id);

    CREATE TABLE IF NOT EXISTS patronage_relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patron_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        patron_household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
        patron_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        patron_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        beneficiary_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
        beneficiary_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
        domain_key TEXT NOT NULL,
        patronage_kind TEXT NOT NULL DEFAULT 'stipend' CHECK(patronage_kind IN (
            'stipend','commission_series','residency','workshop_support','scholarship','mixed','other'
        )),
        amount_per_cycle REAL NOT NULL DEFAULT 0 CHECK(amount_per_cycle>=0),
        recurrence_days INTEGER NOT NULL DEFAULT 30 CHECK(recurrence_days>=1),
        next_due_day INTEGER NOT NULL,
        started_day INTEGER NOT NULL,
        end_day INTEGER,
        exclusivity REAL NOT NULL DEFAULT 0 CHECK(exclusivity BETWEEN 0 AND 1),
        independence_preserved INTEGER NOT NULL DEFAULT 1 CHECK(independence_preserved IN (0,1)),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','strained','paused','ended','breached')),
        source_proposal_id INTEGER REFERENCES opportunity_proposals(id) ON DELETE SET NULL,
        support_json TEXT NOT NULL DEFAULT '{}',
        expectations_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(beneficiary_actor_id IS NOT NULL OR beneficiary_institution_actor_id IS NOT NULL)
    );
    CREATE INDEX IF NOT EXISTS idx_patronage_relationship_due ON patronage_relationships(status,next_due_day,id);
    CREATE INDEX IF NOT EXISTS idx_patronage_beneficiary ON patronage_relationships(beneficiary_actor_id,beneficiary_institution_actor_id,status,id);
    CREATE INDEX IF NOT EXISTS idx_patronage_patron ON patronage_relationships(patron_actor_id,status,id);

    CREATE TABLE IF NOT EXISTS patronage_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patronage_id INTEGER NOT NULL REFERENCES patronage_relationships(id) ON DELETE CASCADE,
        due_day INTEGER NOT NULL,
        resolved_day INTEGER NOT NULL,
        amount_due REAL NOT NULL CHECK(amount_due>=0),
        amount_paid REAL NOT NULL CHECK(amount_paid>=0),
        source_kind TEXT NOT NULL CHECK(source_kind IN ('household','enterprise','none')),
        source_id INTEGER,
        destination_household_id INTEGER REFERENCES households(id) ON DELETE SET NULL,
        status TEXT NOT NULL CHECK(status IN ('paid','partial','missed')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(patronage_id,due_day)
    );
    CREATE INDEX IF NOT EXISTS idx_patronage_payments ON patronage_payments(patronage_id,due_day,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('patron01_version','1')")


def _migration_87(conn: sqlite3.Connection) -> None:
    """PATRONNET-01: beneficiaries can seek patrons and patron competition is explicit."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS patronage_seek_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        beneficiary_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        domain_key TEXT NOT NULL,
        desire_level REAL NOT NULL DEFAULT 50 CHECK(desire_level BETWEEN 0 AND 100),
        preferred_support_kind TEXT NOT NULL DEFAULT 'stipend' CHECK(preferred_support_kind IN (
            'stipend','commission_series','residency','workshop_support','scholarship','mixed','other'
        )),
        min_amount_per_cycle REAL NOT NULL DEFAULT 0 CHECK(min_amount_per_cycle>=0),
        preferred_duration_days INTEGER,
        max_exclusivity REAL NOT NULL DEFAULT 1 CHECK(max_exclusivity BETWEEN 0 AND 1),
        funding_priority REAL NOT NULL DEFAULT 50 CHECK(funding_priority BETWEEN 0 AND 100),
        prestige_priority REAL NOT NULL DEFAULT 50 CHECK(prestige_priority BETWEEN 0 AND 100),
        independence_priority REAL NOT NULL DEFAULT 50 CHECK(independence_priority BETWEEN 0 AND 100),
        max_simultaneous_requests INTEGER NOT NULL DEFAULT 1 CHECK(max_simultaneous_requests>=1),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','ended')),
        created_day INTEGER NOT NULL,
        updated_day INTEGER NOT NULL,
        next_review_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(beneficiary_actor_id,domain_key)
    );
    CREATE INDEX IF NOT EXISTS idx_patronage_seek_due ON patronage_seek_profiles(status,next_review_day,id);

    CREATE TABLE IF NOT EXISTS patronage_competitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        beneficiary_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        domain_key TEXT NOT NULL,
        started_day INTEGER NOT NULL,
        resolved_day INTEGER,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','resolved','expired')),
        winning_patron_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_patronage_competition_active ON patronage_competitions(beneficiary_actor_id,domain_key,status,id);

    CREATE TABLE IF NOT EXISTS patronage_competition_entries (
        competition_id INTEGER NOT NULL REFERENCES patronage_competitions(id) ON DELETE CASCADE,
        proposal_id INTEGER NOT NULL REFERENCES opportunity_proposals(id) ON DELETE CASCADE,
        patron_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        amount_per_cycle REAL NOT NULL DEFAULT 0 CHECK(amount_per_cycle>=0),
        exclusivity REAL NOT NULL DEFAULT 0 CHECK(exclusivity BETWEEN 0 AND 1),
        entered_day INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','withdrawn','lost','won','expired')),
        PRIMARY KEY(competition_id,proposal_id)
    );
    CREATE INDEX IF NOT EXISTS idx_patronage_comp_entry_patron ON patronage_competition_entries(patron_actor_id,status,competition_id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('patronnet01_version','1')")


def _migration_88(conn: sqlite3.Connection) -> None:
    """PATRONCIRCLE-01: convened patronage circles, introductions and evidence-bound cultural movements."""
    cols={r[1] for r in conn.execute("PRAGMA table_info(patronage_preferences)").fetchall()}
    if 'networking_motive' not in cols:
        conn.execute("ALTER TABLE patronage_preferences ADD COLUMN networking_motive REAL NOT NULL DEFAULT 0 CHECK(networking_motive BETWEEN 0 AND 100)")
    if 'circle_cadence_days' not in cols:
        conn.execute("ALTER TABLE patronage_preferences ADD COLUMN circle_cadence_days INTEGER NOT NULL DEFAULT 60 CHECK(circle_cadence_days>=14)")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS patronage_circles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patron_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        domain_key TEXT NOT NULL,
        started_day INTEGER NOT NULL,
        ended_day INTEGER,
        next_gathering_day INTEGER NOT NULL,
        cadence_days INTEGER NOT NULL DEFAULT 60 CHECK(cadence_days>=14),
        cohesion REAL NOT NULL DEFAULT 50 CHECK(cohesion BETWEEN 0 AND 100),
        public_visibility REAL NOT NULL DEFAULT 50 CHECK(public_visibility BETWEEN 0 AND 100),
        prestige REAL NOT NULL DEFAULT 50 CHECK(prestige BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','dormant','ended')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(patron_actor_id,domain_key)
    );
    CREATE INDEX IF NOT EXISTS idx_patronage_circle_due ON patronage_circles(status,next_gathering_day,id);

    CREATE TABLE IF NOT EXISTS patronage_circle_members (
        circle_id INTEGER NOT NULL REFERENCES patronage_circles(id) ON DELETE CASCADE,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        patronage_id INTEGER REFERENCES patronage_relationships(id) ON DELETE SET NULL,
        joined_day INTEGER NOT NULL,
        left_day INTEGER,
        role_kind TEXT NOT NULL DEFAULT 'beneficiary' CHECK(role_kind IN ('beneficiary','guest','associate')),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','left')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(circle_id,actor_id)
    );
    CREATE INDEX IF NOT EXISTS idx_circle_member_actor ON patronage_circle_members(actor_id,status,circle_id);

    CREATE TABLE IF NOT EXISTS patronage_circle_gatherings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        circle_id INTEGER NOT NULL REFERENCES patronage_circles(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        gathering_kind TEXT NOT NULL DEFAULT 'salon' CHECK(gathering_kind IN ('salon','workshop','supper','court','studio','other')),
        attendance_count INTEGER NOT NULL DEFAULT 0 CHECK(attendance_count>=0),
        introductions_made INTEGER NOT NULL DEFAULT 0 CHECK(introductions_made>=0),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(circle_id,day)
    );

    CREATE TABLE IF NOT EXISTS patronage_circle_introductions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        circle_id INTEGER NOT NULL REFERENCES patronage_circles(id) ON DELETE CASCADE,
        gathering_id INTEGER REFERENCES patronage_circle_gatherings(id) ON DELETE SET NULL,
        actor_a_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        actor_b_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        introduced_day INTEGER NOT NULL,
        introduction_kind TEXT NOT NULL DEFAULT 'patron_circle',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        CHECK(actor_a_id<>actor_b_id),
        UNIQUE(circle_id,actor_a_id,actor_b_id)
    );
    CREATE INDEX IF NOT EXISTS idx_circle_intro_pair ON patronage_circle_introductions(actor_a_id,actor_b_id,introduced_day,id);

    CREATE TABLE IF NOT EXISTS cultural_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        circle_id INTEGER REFERENCES patronage_circles(id) ON DELETE SET NULL,
        domain_key TEXT NOT NULL,
        style_tag TEXT NOT NULL,
        display_name TEXT,
        emerged_day INTEGER NOT NULL,
        recognized_day INTEGER,
        member_count INTEGER NOT NULL DEFAULT 0 CHECK(member_count>=0),
        work_count INTEGER NOT NULL DEFAULT 0 CHECK(work_count>=0),
        mean_quality REAL NOT NULL DEFAULT 0 CHECK(mean_quality BETWEEN 0 AND 100),
        influence REAL NOT NULL DEFAULT 0 CHECK(influence BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'emerging' CHECK(status IN ('emerging','recognized','declining','ended')),
        evidence_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(circle_id,domain_key,style_tag)
    );
    CREATE INDEX IF NOT EXISTS idx_cultural_movement_status ON cultural_movements(status,domain_key,influence DESC,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('patroncircle01_version','1')")


def _migration_89(conn: sqlite3.Connection) -> None:
    """ORGNEED-01: evidence-bound autonomous staffing/capability need projection."""
    cols={r[1] for r in conn.execute("PRAGMA table_info(institutional_roles)").fetchall()}
    if 'minimum_filled_slots' not in cols:
        conn.execute("ALTER TABLE institutional_roles ADD COLUMN minimum_filled_slots INTEGER NOT NULL DEFAULT 0 CHECK(minimum_filled_slots>=0)")
    if 'autonomous_refill' not in cols:
        conn.execute("ALTER TABLE institutional_roles ADD COLUMN autonomous_refill INTEGER NOT NULL DEFAULT 0 CHECK(autonomous_refill IN (0,1))")
    if 'minimum_candidate_quality' not in cols:
        conn.execute("ALTER TABLE institutional_roles ADD COLUMN minimum_candidate_quality REAL NOT NULL DEFAULT 0 CHECK(minimum_candidate_quality BETWEEN 0 AND 100)")
    if 'staffing_priority' not in cols:
        conn.execute("ALTER TABLE institutional_roles ADD COLUMN staffing_priority REAL NOT NULL DEFAULT 50 CHECK(staffing_priority BETWEEN 0 AND 100)")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS organization_capability_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        requirement_key TEXT NOT NULL,
        capability_key TEXT NOT NULL,
        domain_key TEXT NOT NULL,
        minimum_capacity REAL NOT NULL DEFAULT 0 CHECK(minimum_capacity BETWEEN 0 AND 100),
        minimum_readiness REAL NOT NULL DEFAULT 0 CHECK(minimum_readiness BETWEEN 0 AND 100),
        search_kind TEXT NOT NULL DEFAULT 'service_provider' CHECK(search_kind IN ('talent','service_provider')),
        role_key TEXT,
        min_quality REAL NOT NULL DEFAULT 0 CHECK(min_quality BETWEEN 0 AND 100),
        intensity REAL NOT NULL DEFAULT 60 CHECK(intensity BETWEEN 0 AND 100),
        urgency REAL NOT NULL DEFAULT 50 CHECK(urgency BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','ended')),
        source_kind TEXT,
        source_id INTEGER,
        adaptive_plan_json TEXT NOT NULL DEFAULT '{}',
        proposal_json TEXT NOT NULL DEFAULT '{}',
        created_day INTEGER NOT NULL,
        updated_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(institution_actor_id,requirement_key)
    );
    CREATE INDEX IF NOT EXISTS idx_org_capability_requirement_active
        ON organization_capability_requirements(institution_actor_id,status,domain_key,capability_key,id);
    CREATE INDEX IF NOT EXISTS idx_org_pressure_source
        ON organization_pressures(institution_actor_id,source_kind,source_id,status,id);
    """)
    # Migration defines the possibility only. Existing roles default to non-required and no
    # capability requirements are backfilled, so historical vacancies/needs are not fabricated.
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('orgneed01_version','1')")



def _migration_90(conn: sqlite3.Connection) -> None:
    """PERSONECO-01: demand-independent background-person profiles and resolution provenance."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS background_person_profiles (
        partition_id INTEGER NOT NULL REFERENCES background_population_partitions(id) ON DELETE CASCADE,
        local_uid INTEGER NOT NULL,
        source_id INTEGER NOT NULL REFERENCES background_population_sources(id) ON DELETE CASCADE,
        current_location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        given_name TEXT NOT NULL,
        family_name TEXT NOT NULL,
        birth_day INTEGER NOT NULL,
        demographic_sex TEXT NOT NULL CHECK(demographic_sex IN ('female','male')),
        occupation_domain TEXT NOT NULL,
        social_archetype TEXT NOT NULL,
        open_core INTEGER NOT NULL DEFAULT 0 CHECK(open_core IN (0,1)),
        current_stage TEXT,
        command_aptitude REAL NOT NULL DEFAULT 0 CHECK(command_aptitude BETWEEN 0 AND 100),
        economic_aptitude REAL NOT NULL DEFAULT 0 CHECK(economic_aptitude BETWEEN 0 AND 100),
        medical_aptitude REAL NOT NULL DEFAULT 0 CHECK(medical_aptitude BETWEEN 0 AND 100),
        teaching_aptitude REAL NOT NULL DEFAULT 0 CHECK(teaching_aptitude BETWEEN 0 AND 100),
        criminal_familiarity REAL NOT NULL DEFAULT 0 CHECK(criminal_familiarity BETWEEN 0 AND 100),
        status TEXT NOT NULL DEFAULT 'background' CHECK(status IN ('background','resolved','dead')),
        actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        seeded_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(partition_id,local_uid),
        UNIQUE(actor_id)
    );
    CREATE INDEX IF NOT EXISTS idx_background_person_candidate
      ON background_person_profiles(status,current_location_id,occupation_domain,open_core,current_stage,local_uid);
    CREATE INDEX IF NOT EXISTS idx_background_person_source
      ON background_person_profiles(source_id,status,local_uid);

    CREATE TABLE IF NOT EXISTS person_resolution_provenance (
        actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        partition_id INTEGER NOT NULL,
        local_uid INTEGER NOT NULL,
        resolved_day INTEGER NOT NULL,
        resolution_reason TEXT NOT NULL,
        demand_kind TEXT,
        source_kind TEXT NOT NULL DEFAULT 'preexisting_background_identity',
        population_delta INTEGER NOT NULL DEFAULT 0 CHECK(population_delta=0),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(partition_id,local_uid)
    );
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('personeco01_version','1')")


def _migration_91(conn: sqlite3.Connection) -> None:
    """PROFESSION-01 / business ecology: ordinary provider standing and insolvency continuity."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS professional_profiles (
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        domain_key TEXT NOT NULL,
        competence REAL NOT NULL DEFAULT 40 CHECK(competence BETWEEN 0 AND 100),
        reputation REAL NOT NULL DEFAULT 40 CHECK(reputation BETWEEN 0 AND 100),
        capacity REAL NOT NULL DEFAULT 1 CHECK(capacity>=0),
        current_load REAL NOT NULL DEFAULT 0 CHECK(current_load>=0),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','retired','dead')),
        source_kind TEXT NOT NULL DEFAULT 'resolved_background',
        source_id INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(actor_id,domain_key)
    );
    CREATE INDEX IF NOT EXISTS idx_professional_profiles_provider ON professional_profiles(domain_key,status,competence,reputation,actor_id);

    CREATE TABLE IF NOT EXISTS enterprise_ecology_state (
        enterprise_id INTEGER PRIMARY KEY REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        founded_day INTEGER,
        crystallized_day INTEGER,
        structural_origin TEXT NOT NULL DEFAULT 'preexisting',
        profitable_streak_days INTEGER NOT NULL DEFAULT 0,
        insolvent_since_day INTEGER,
        closed_day INTEGER,
        closure_reason TEXT,
        last_review_day INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('profession01_version','1')")


def _migration_92(conn: sqlite3.Connection) -> None:
    """SERVICEFULFILL-01: conserved service demand routed to concrete providers."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS service_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        requester_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        requester_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        domain_key TEXT NOT NULL,
        location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
        need_level REAL NOT NULL DEFAULT 50 CHECK(need_level BETWEEN 0 AND 100),
        requested_day INTEGER NOT NULL,
        due_day INTEGER,
        provider_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        provider_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        provider_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','matched','fulfilled','failed','cancelled')),
        fulfilled_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_service_requests_open ON service_requests(status,domain_key,location_id,requested_day,id);

    CREATE TABLE IF NOT EXISTS service_fulfillments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
        provider_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        provider_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        provider_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        fulfilled_day INTEGER NOT NULL,
        quality REAL NOT NULL DEFAULT 50 CHECK(quality BETWEEN 0 AND 100),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(request_id)
    );
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('servicefulfill01_version','1')")


def _migration_93(conn: sqlite3.Connection) -> None:
    """DEMO-04 / MIGGEO / EXCESSMORT: route-aware migration and excess-death reconciliation."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS population_migration_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_source_id INTEGER NOT NULL REFERENCES background_population_sources(id) ON DELETE CASCADE,
        to_source_id INTEGER NOT NULL REFERENCES background_population_sources(id) ON DELETE CASCADE,
        requested_population REAL NOT NULL CHECK(requested_population>0),
        route_id INTEGER,
        requested_day INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','completed','blocked','cancelled')),
        completed_day INTEGER,
        reason TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_population_migration_pending ON population_migration_requests(status,requested_day,id);

    CREATE TABLE IF NOT EXISTS excess_mortality_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day INTEGER NOT NULL,
        source_kind TEXT NOT NULL,
        source_id INTEGER,
        population_source_id INTEGER REFERENCES background_population_sources(id) ON DELETE SET NULL,
        aggregate_deaths REAL NOT NULL CHECK(aggregate_deaths>=0),
        tracked_deaths INTEGER NOT NULL DEFAULT 0 CHECK(tracked_deaths>=0),
        applied_population_deaths REAL NOT NULL DEFAULT 0 CHECK(applied_population_deaths>=0),
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','applied','unresolved','cancelled')),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(source_kind,source_id)
    );
    CREATE INDEX IF NOT EXISTS idx_excess_mortality_pending ON excess_mortality_ledger(status,day,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('demo04_miggeo_excessmort_version','1')")


def _migration_94(conn: sqlite3.Connection) -> None:
    """CONFLICTGEO-01: explicit military-frontier geometry independent of civilian roads."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS conflict_geometries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_a_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        location_b_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        geometry_kind TEXT NOT NULL CHECK(geometry_kind IN ('civilian_route','military_frontier','maritime','wilderness_corridor')),
        traversable INTEGER NOT NULL DEFAULT 1 CHECK(traversable IN (0,1)),
        military_feasibility REAL NOT NULL DEFAULT 50 CHECK(military_feasibility BETWEEN 0 AND 100),
        civilian_feasibility REAL NOT NULL DEFAULT 50 CHECK(civilian_feasibility BETWEEN 0 AND 100),
        source_kind TEXT NOT NULL,
        source_id INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(location_a_id,location_b_id,geometry_kind)
    );
    CREATE INDEX IF NOT EXISTS idx_conflict_geometries_pair ON conflict_geometries(location_a_id,location_b_id,geometry_kind,traversable);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('conflictgeo01_version','1')")


def _migration_95(conn: sqlite3.Connection) -> None:
    """Structural providers and contractual institutional authority."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS structural_provider_contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        consumer_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
        provider_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE CASCADE,
        provider_enterprise_id INTEGER REFERENCES civilian_enterprises(id) ON DELETE SET NULL,
        domain_key TEXT NOT NULL,
        authority_kind TEXT NOT NULL DEFAULT 'collective_contractual',
        started_day INTEGER,
        ended_day INTEGER,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','ended','breached')),
        terms_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_structural_provider_contract ON structural_provider_contracts(consumer_institution_actor_id,domain_key,status,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('structural_provider_contract_version','1')")


def _migration_96(conn: sqlite3.Connection) -> None:
    """Underworld splinter/provenance: people and crews transfer rather than duplicate."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS organization_transfer_provenance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day INTEGER NOT NULL,
        transfer_kind TEXT NOT NULL,
        source_organization_id INTEGER,
        target_organization_id INTEGER,
        actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        crew_id INTEGER,
        quantity REAL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_org_transfer_target ON organization_transfer_provenance(target_organization_id,day,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('splinter_provenance_version','1')")


def _migration_97(conn: sqlite3.Connection) -> None:
    """Merchant-house taxonomy: institutional house status is not a profitability threshold."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS merchant_house_qualifications (
        enterprise_id INTEGER PRIMARY KEY REFERENCES civilian_enterprises(id) ON DELETE CASCADE,
        institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        durable_depth INTEGER NOT NULL DEFAULT 0 CHECK(durable_depth IN (0,1)),
        dynastic_or_family_continuity INTEGER NOT NULL DEFAULT 0 CHECK(dynastic_or_family_continuity IN (0,1)),
        multi_venture_depth INTEGER NOT NULL DEFAULT 0 CHECK(multi_venture_depth IN (0,1)),
        recognized_house_status INTEGER NOT NULL DEFAULT 0 CHECK(recognized_house_status IN (0,1)),
        reviewed_day INTEGER NOT NULL DEFAULT 0,
        evidence_json TEXT NOT NULL DEFAULT '{}'
    );
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('merchant_taxonomy_version','1')")


def _migration_98(conn: sqlite3.Connection) -> None:
    """Opening-location and institutional-authority provenance."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS actor_location_provenance (
        actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        provenance_kind TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1 CHECK(confidence BETWEEN 0 AND 1),
        resolved_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS institutional_authority_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        institution_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        authority_key TEXT NOT NULL,
        authority_kind TEXT NOT NULL CHECK(authority_kind IN ('named_incumbent','collective','unresolved_incumbent','vacant')),
        incumbent_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        required_stage TEXT,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','vacant','retired')),
        created_day INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(institution_actor_id,authority_key)
    );
    CREATE INDEX IF NOT EXISTS idx_authority_slots ON institutional_authority_slots(institution_actor_id,status,authority_kind,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('location_authority_version','1')")


def _migration_99(conn: sqlite3.Connection) -> None:
    """NONMERCHANT-01 + TEACHECO: spare teaching capacity and informal-circle persistence."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS teaching_capacity_profiles (
        teacher_actor_id INTEGER PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
        domain_key TEXT NOT NULL DEFAULT 'martial_instruction',
        personal_capacity INTEGER NOT NULL DEFAULT 1 CHECK(personal_capacity>=0),
        occupied_places INTEGER NOT NULL DEFAULT 0 CHECK(occupied_places>=0),
        spare_places INTEGER NOT NULL DEFAULT 0 CHECK(spare_places>=0),
        discoverability REAL NOT NULL DEFAULT 50 CHECK(discoverability BETWEEN 0 AND 100),
        last_review_day INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS informal_teaching_circles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        domain_key TEXT NOT NULL DEFAULT 'martial_instruction',
        started_day INTEGER NOT NULL,
        active_students INTEGER NOT NULL DEFAULT 0 CHECK(active_students>=0),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','ended','formalized')),
        formalized_institution_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_informal_teaching_circle ON informal_teaching_circles(teacher_actor_id,status,started_day,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('nonmerchant_teacheco_version','1')")


def _migration_100(conn: sqlite3.Connection) -> None:
    """Named mortality parity audit; no character class receives plot armor."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS mortality_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
        day INTEGER NOT NULL,
        age_years REAL,
        annual_hazard REAL NOT NULL DEFAULT 0,
        elapsed_days INTEGER NOT NULL DEFAULT 0,
        draw REAL,
        died INTEGER NOT NULL DEFAULT 0 CHECK(died IN (0,1)),
        source_kind TEXT NOT NULL DEFAULT 'ordinary_health',
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_mortality_audit_actor ON mortality_audit(actor_id,day,id);
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('mortality_parity_version','1')")


def _migration_101(conn: sqlite3.Connection) -> None:
    """Formation-vs-crystallization provenance and historical-membership non-backfill."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS entity_origin_provenance (
        entity_kind TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        origin_kind TEXT NOT NULL CHECK(origin_kind IN ('preexisting_crystallized','formed_in_simulation','imported','unknown_preexisting')),
        formation_day INTEGER,
        crystallized_day INTEGER,
        source_kind TEXT,
        source_id INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(entity_kind,entity_id)
    );
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('formation_crystallization_version','1')")


def _migration_102(conn: sqlite3.Connection) -> None:
    """Population-casualty reconciliation bridge for war and underworld violence."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS population_casualty_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        casualty_kind TEXT NOT NULL,
        casualty_source_id INTEGER,
        population_source_id INTEGER REFERENCES background_population_sources(id) ON DELETE SET NULL,
        aggregate_deaths REAL NOT NULL DEFAULT 0 CHECK(aggregate_deaths>=0),
        tracked_actor_deaths INTEGER NOT NULL DEFAULT 0 CHECK(tracked_actor_deaths>=0),
        applied INTEGER NOT NULL DEFAULT 0 CHECK(applied IN (0,1)),
        applied_day INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(casualty_kind,casualty_source_id)
    );
    """)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('population_casualty_bridge_version','1')")


def _migration_103(conn: sqlite3.Connection) -> None:
    """Recovered merged-line completeness marker; capability only, no simulated history."""
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('schema103_recovery_complete','1')")


def _migration_104(conn: sqlite3.Connection) -> None:
    """ONEYEAR recovery acceptance epoch: release TENYEAR-02 only for this reconstructed line."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS acceptance_epochs (
        acceptance_key TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','passed','failed')),
        accepted_day INTEGER,
        evidence_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.execute("""INSERT OR IGNORE INTO acceptance_epochs(acceptance_key,schema_version,status,evidence_json)
                    VALUES ('ONEYEAR_RECOVERY_SCHEMA104',104,'pending','{}')""")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('tenyear02_gate_epoch','ONEYEAR_RECOVERY_SCHEMA104')")

_MIGRATIONS: dict[int, Migration] = {
    1: ("baseline", "Original persistent world schema", None),
    2: ("canon_decisions", "Canon retrieval and structured decisions", None),
    3: ("interactions", "Causal actor interactions", None),
    4: ("information", "Character-relative information propagation", None),
    5: ("player_runtime", "Player runtime and scene state", None),
    6: ("model_gateway", "Model gateway and runtime configuration", None),
    7: ("story_time_runtime", "Story-time-only runtime and local model compatibility", _migration_7),
    8: ("continuity_substrate", "Continuity and resolution substrate", _migration_8),
    9: ("crystallization", "Historical crystallization audit layer", None),
    10: ("embodiment", "Persistent character embodiment", _migration_10),
    11: ("competence", "Domain competence and professional readings", _migration_11),
    12: ("time_skip", "Authoritative time-skip resolver", None),
    13: ("combat", "Abstract battle and duel resolver", None),
    14: ("battlefield", "Multi-front battle flow", None),
    15: ("battle_tactics", "Tactical grammar and Vein consequence", None),
    16: ("civilian", "Civilian simulation core", None),
    17: ("civilian_life", "Civilian life depth", None),
    18: ("business", "Differentiated business ecology", _migration_18),
    19: ("household_life", "Household, kinship and demographics", None),
    20: ("health", "Health, aging and mortality", None),
    21: ("religion", "Religion and cultural institutions", _migration_21),
    22: ("ecology", "Ecology, seasons and travel", None),
    23: ("politics", "Politics and macro-history", None),
    24: ("education", "Education and institutional reproduction", None),
    25: ("stress", "Long-run stress testing", None),
    26: ("integration", "v1.0-preRC integration, bootstrap, ownership and save safety", _migration_26),
    27: ("current_canon_bridge", "Current-canon identity bridge, coverage observability and two-way resolution", _migration_27),
    28: ("domain_actions", "Phase 3 NPC domain actions and accepted-interaction callbacks", _migration_28),
    29: ("commercial_logistics", "Conservation-safe commercial stock and shipment lifecycle", _migration_29),
    30: ("economic_substrate", "Current-canon aggregate material, market and production substrate", _migration_30),
    31: ("prose_geography", "Prose-derived geography completion and explicit placement certainty", _migration_31),
    32: ("cultivation_realization", "Causal cultivation, Realization history and Stage progression", _migration_32),
    33: ("elixir_physiology", "Traceable elixir batches, Sediment and cultivation-fuel physiology", _migration_33),
    34: ("family_civilian_consequences", "Causal guardianship, household service/migration and credit initiation", _migration_34),
    35: ("autonomous_combat_tournaments", "Consensual autonomous challenges and recurring tournament lifecycle", _migration_35),
    36: ("spectacle_economy", "Aggregate betting books, structural Closed-Core prizefighting and latent career promotion", _migration_36),
    37: ("underworld_ecology", "Evidence-driven crime organizations, conserved smuggling and local policing", _migration_37),
    38: ("hollow_succession", "Hollow practice, Grand Coven claimant state and mantle succession", _migration_38),
    39: ("addiction_psych", "Causal dependency and psychological consequence state", _migration_39),
    40: ("underworld_medicine", "Discreet medical access and exploitation integrity", _migration_40),
    41: ("war_logistics", "Campaign supply, route pressure and military aftermath", _migration_41),
    42: ("cultivation_demography", "Sparse Realization hazard, plateau persistence and Sixth-stage demographic pressure", _migration_42),
    43: ("generational_continuity", "Contextual family formation and structural institutional training cohorts", _migration_43),
    44: ("autonomous_resolution", "Scheduled two-way actor/institution and latent-identity resolution reviews", _migration_44),
    45: ("decade_integrity_emergence", "Decade relationship/economic integrity and latent commercial emergence", _migration_45),
    46: ("stage_variability", "Probabilistic stage timing, heterogeneous Vessel response and soft summit demographics", _migration_46),
    47: ("groundbinding", "Persistent Groundbound dependency and ecology-linked off-ground failure", _migration_47),
    48: ("stage_attainment_ledger", "Inverse age-Stage calibration and explicit Stage attainment chronology", _migration_48),
    49: ("underworld_organization_forms", "Parallel criminal organization forms with independent scale and structural depth", _migration_49),
    50: ("underworld_membership_flows", "Dynamic gang membership stocks, churn, recruitment and exits", _migration_50),
    51: ("underworld_rebuild_firewall", "Clean underworld rebuild and organization institutional grammar", _migration_51),
    52: ("underworld_territory_crews", "Concrete criminal zones, sovereignty, crews and personnel", _migration_52),
    53: ("underworld_assets_rackets", "Concrete protection, rackets, fronts, finance and leader wealth", _migration_53),
    54: ("underworld_politics_succession", "Inter-organization politics, operations and succession", _migration_54),
    55: ("underworld_heat_enforcement", "Organization heat and concrete enforcement pressure", _migration_55),
    56: ("underworld_zone_geography_anchor", "v0.60 Phase 2A: optional district-scale location anchor on underworld zones", _migration_56),
    57: ("process_registry_tasks", "ARCH-01 ProcessRegistry spike: durable one-off/scheduled task table", _migration_57),
    58: ("underworld_economic_interests", "ECON-01 explicit economic interests, money flows, protection-racket linkage and firewall correction", _migration_58),
    59: ("territorial_event_sourcing_spike", "EVENTS-01 immutable territorial event stream, replay projections, snapshots and branches", _migration_59),
    60: ("directed_relationships", "REL-01 directional social/evaluative relationships with symmetric migration", _migration_60),
    61: ("low_resolution_presence", "PRES-01 shared low-resolution presence with tracked-travel and exact-scene override", _migration_61),
    62: ("belief_evidence_competence_lens", "BELIEF-01 claims/evidence/actor belief revisions and competence-lens foundation", _migration_62),
    63: ("information_bounded_decision_runtime", "DEC-01 actor-accessible candidate providers, weighted selection and decision audit", _migration_63),
    64: ("merchant_vertical_slice", "MERCHANT-01 merchant records, contracts, settlement and input substitution", _migration_64),
    65: ("craft_vertical_slice", "CRAFT-01 tracked recipes, facilities, production orders and conserved stock execution", _migration_65),
    66: ("regional_growth_state_capacity", "GROWTH-01 conserved public finance, public works/security, delayed administration and causal regional response", _migration_66),
    67: ("war_world_integration", "WAR-01 campaign operations, physical supply, persistent casualties/damage/displacement and actor-relative battle reports", _migration_67),
    68: ("health_agriculture_law_integration", "INTEGRATION-01 treatment capacity, agriculture/harvest and law/jurisdiction/procedure", _migration_68),
    69: ("coverage_gate_closure", "COVERAGE-01 opening population policy, process ownership and resolution closure", _migration_69),
    70: ("one_year_unattended_acceptance", "ONEYEAR-01 integrated ordinary unattended-world acceptance and ten-year gate release", _migration_70),
    71: ("scale_authority", "SCALE-01 population, settlement, institution and military scale authority", _migration_71),
    72: ("aggregate_ordinary_trade", "TRADE-01 population-scaled ordinary trade and material-flow telemetry", _migration_72),
    73: ("background_population_partitions", "POPBACK-01 bounded array-backed identity reservoirs beneath latent/named actors", _migration_73),
    74: ("background_population_age_cohorts", "POPLIFE-01 live aggregate life-course over disjoint population sources", _migration_74),
    75: ("information_schedule_indexes", "INFOIDX-01 indexed causal information scheduling and rumour seeding", _migration_75),
    76: ("resolution_owner_cleanup", "RESCLEAN-01 resolution owner/type cleanup and fixed cohort anchors", _migration_76),
    77: ("organization_agency", "ORGAGENCY-01 shared institutional inheritance, regimes, factions, pressures and capabilities", _migration_77),
    78: ("underworld_organization_identity_bridge", "ORGIDENT-01 shared institution identity/capability bridge for criminal organizations", _migration_78),
    79: ("polity_agency", "POLITYAGENCY-01 relationship-specific government agency and structural government actors", _migration_79),
    80: ("conflict_origin", "CONFLICT-01 causal geopolitical pressure, incidents, responses and WAR-01 bridge", _migration_80),
    81: ("organization_lifecycle", "ORGLIFE-01 causal organization and polity life cycles, formation, fission, absorption and dissolution", _migration_81),
    82: ("provider_seeking", "SEEK-01 inbound demand, discoverable capability and provider-seeking", _migration_82),
    83: ("strategic_attention", "ATTENTION-01 strategic relevance, recruitment, appointments and other inbound strategies", _migration_83),
    84: ("opportunity_matching", "OPPORTUNITY-01 symmetric search, typed proposals, negotiated rights and causal transfers", _migration_84),
    85: ("adaptive_institutional_planning", "ADAPT-01 reusable institutional roles, plan adaptation and exceptional structural role creation", _migration_85),
    86: ("social_patronage", "PATRON-01 independent patronage, recurring support and cultural/talent patron discovery", _migration_86),
    87: ("patronage_networks", "PATRONNET-01 beneficiary patron-seeking, competing offers and patronage network state", _migration_87),
    88: ("patronage_circles", "PATRONCIRCLE-01 convened patronage circles, introductions and evidence-bound cultural movements", _migration_88),
    89: ("organization_needs", "ORGNEED-01 evidence-bound autonomous staffing and capability needs", _migration_89),
    90: ("background_person_ecology", "PERSONECO-01 demand-independent background-person profiles and resolution provenance", _migration_90),
    91: ("profession_business_ecology", "PROFESSION-01 professional emergence and ordinary business ecology", _migration_91),
    92: ("service_fulfillment", "SERVICEFULFILL-01 concrete provider fulfillment", _migration_92),
    93: ("demography_migration_excess_mortality", "DEMO-04, MIGGEO and EXCESSMORT reconciliation", _migration_93),
    94: ("conflict_geometry", "CONFLICTGEO-01 explicit military-frontier geometry", _migration_94),
    95: ("structural_provider_contracts", "Structural-provider contracting and collective authority", _migration_95),
    96: ("splinter_provenance", "Real crew/personnel transfer and splinter provenance", _migration_96),
    97: ("merchant_house_taxonomy", "Merchant House status separated from ordinary profitable firms", _migration_97),
    98: ("location_authority_parity", "Opening locations and institutional-head parity", _migration_98),
    99: ("nonmerchant_teacheco", "NONMERCHANT-01 and TEACHECO", _migration_99),
    100: ("mortality_parity", "Named/background ordinary mortality parity audit", _migration_100),
    101: ("formation_crystallization_provenance", "Formation versus crystallization provenance", _migration_101),
    102: ("population_casualty_bridge", "WAR/underworld excess-mortality population reconciliation", _migration_102),
    103: ("merged_recovery_complete", "Recovered schema-101-era merged line plus acceptance fixes", _migration_103),
    104: ("oneyear_recovery_acceptance_epoch", "Current-line ONEYEAR acceptance epoch and TENYEAR-02 gate", _migration_104),
}


def _apply_migrations(conn: sqlite3.Connection, from_version: int) -> None:
    # v0.26 is the first release with a persistent migration ledger. When upgrading an
    # older save, record the already-recognized historical schema levels before applying
    # new migrations. The timestamp is the recognition/import time, not a claim about
    # when an old release was originally installed.
    for version in range(1, min(max(0, from_version), SCHEMA_VERSION) + 1):
        key, description, _ = _MIGRATIONS[version]
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version,migration_key,description) VALUES (?,?,?)",
            (version, key, description + " [recognized from pre-v0.26 save]"),
        )
    for version in range(max(0, from_version) + 1, SCHEMA_VERSION + 1):
        key, description, fn = _MIGRATIONS[version]
        if fn is not None:
            fn(conn)
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations(version,migration_key,description) VALUES (?,?,?)",
            (version, key, description),
        )
        conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('schema_version',?)", (str(version),))


def _ensure_current_vocab_and_meta(conn: sqlite3.Connection) -> None:
    # Safe idempotent compatibility repair is intentionally repeated: old campaigns may
    # acquire source rows after their historical schema migration first ran (for example
    # seed-demo in regression tests or an imported player profile). The resolution and
    # embodiment writers are INSERT OR IGNORE and therefore do not overwrite campaign truth.
    _seed_resolution_from_profiles(conn)
    _ensure_player_embodiment(conn)
    _seed_competence_domains(conn)
    _seed_business_vocab(conn)
    _seed_religion_vocab(conn)
    from .coverage import seed_coverage_registry
    seed_coverage_registry(conn)
    conn.execute("UPDATE runtime_config SET realtime_calendar_progression=0 WHERE id=1")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('engine_version',?)", (ENGINE_VERSION,))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('schema_version',?)", (str(SCHEMA_VERSION),))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_seed_version','1.3')")
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('named_person_chronology_contract','explicit_age_and_birth_day_required')")


def init_db() -> None:
    path = database_path()
    prior_version = _existing_schema_version(path)
    if prior_version and prior_version < SCHEMA_VERSION and not _running_tests():
        _backup_raw(path, f"pre_migration_v{prior_version}_to_v{SCHEMA_VERSION}")
    with connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute("INSERT OR IGNORE INTO world_state(id, world_name, current_day) VALUES (1, 'Caerness', 0)")
        conn.execute("INSERT OR IGNORE INTO campaign_setup_state(id,bootstrap_complete,player_setup_complete) VALUES (1,0,0)")
        # If the database had no version metadata, treat its existing engine version as the baseline.
        stored = conn.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()
        from_version = prior_version
        if stored and prior_version == 0:
            try:
                from_version = int(stored[0])
            except Exception:
                from_version = 0
        _apply_migrations(conn, min(from_version, SCHEMA_VERSION))
        _ensure_current_vocab_and_meta(conn)
        conn.commit()


def reset_db(*, force: bool = False, backup: bool = True) -> None:
    path = database_path()
    exists = any(Path(str(path) + suffix).exists() for suffix in ("", "-wal", "-shm"))
    if exists and not _running_tests() and not force:
        raise RuntimeError(
            "Refusing to reset a non-test Caerness database without force=True. "
            "Use the CLI 'reset --force' command; it creates a safety backup first by default."
        )
    if exists and backup and not _running_tests() and _looks_like_caerness(path):
        _backup_raw(path, "pre_reset")
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()


def backup_db(label: str | None = None, *, keep: int = 20) -> str:
    init_db()
    path = database_path()
    with connect() as src:
        day = int(src.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        turn_count = int(src.execute("SELECT COUNT(*) FROM turns").fetchone()[0])
    tag = f"day{day:06d}_turn{turn_count:06d}" + (f"_{label}" if label else "")
    return _backup_raw(path, tag, keep=keep)


def restore_db(path: str | Path) -> None:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    if not _looks_like_caerness(source):
        raise ValueError("Backup does not contain a Caerness world_state table.")
    target = database_path()
    if target.exists() and not _running_tests():
        _backup_raw(target, "pre_restore")
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(target) + suffix)
        if candidate.exists():
            candidate.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    init_db()


def migration_status(conn: sqlite3.Connection | None = None) -> dict[str, object]:
    own = conn is None
    if conn is None:
        init_db()
        conn = connect()
    try:
        rows = conn.execute("SELECT version,migration_key,description,applied_at FROM schema_migrations ORDER BY version").fetchall()
        return {
            "engine_version": ENGINE_VERSION,
            "schema_version": SCHEMA_VERSION,
            "database_path": str(database_path()),
            "test_mode": _running_tests(),
            "applied": [dict(r) for r in rows],
        }
    finally:
        if own:
            conn.close()
