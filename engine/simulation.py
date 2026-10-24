from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass
from typing import Iterable

from .relationships import ensure_reciprocal_relationship
from .db import connect, init_db
from .decisions import decide_actor
from .interactions import process_due_interactions
from .information import register_event_information, process_information, next_information_due_day
from .memory import process_due_memory, next_memory_due_day
from .world import next_world_process_due_day, process_due_world_processes, catch_up_world_processes
from .civilian import next_civilian_due_day, process_due_civilian
from .health import next_health_due_day, process_due_health
from .psych import next_psych_due_day, process_due_psychology
from .religion import next_religion_due_day, process_due_religion
from .ecology import next_ecology_due_day, process_due_ecology
from .agriculture import next_agriculture_due_day, process_due_agriculture
from .politics import next_politics_due_day, process_due_politics
from .conflict import next_conflict_due_day, process_due_conflict
from .organization_lifecycle import next_organization_lifecycle_due_day, process_due_organization_lifecycle
from .seeking import next_seeking_due_day, process_due_seeking
from .attention import next_attention_due_day, process_due_attention
from .patronage import next_patronage_due_day, process_due_patronage
from .education import next_education_due_day, process_due_education
from .logistics import next_logistics_due_day, process_due_logistics
from .merchant import next_merchant_due_day, process_due_merchant
from .craft import next_craft_due_day, process_due_craft
from .growth import next_growth_due_day, process_due_growth
from .law import next_law_due_day, process_due_law
from .cultivation import next_cultivation_due_day, process_due_cultivation
from .groundbinding import next_groundbinding_due_day, process_due_groundbinding
from .tournaments import next_tournament_due_day, process_due_tournaments
from .spectacle import next_spectacle_due_day, process_due_spectacle
from .underworld import next_underworld_due_day, process_due_underworld
from .underworld_medicine import next_underworld_medicine_due_day, process_due_underworld_medicine
from .hollow import next_hollow_due_day, process_due_hollow
from .war import next_war_due_day, process_due_war
from .resolution_controller import next_resolution_due_day, process_due_resolution
from .profession_runtime import next_profession_due_day, process_due_profession
from .service_fulfillment import next_service_due_day, process_due_services
from .role_experience import process_role_experience_review


DEFAULT_CADENCE = {
    "ACTIVE": 2,
    "STRATEGIC": 14,
    "DORMANT": 60,
}


@dataclass
class SimEvent:
    day: int
    event_type: str
    title: str
    summary: str
    severity: int = 1
    source_actor_id: int | None = None
    target_actor_ids: tuple[int, ...] = ()
    location_id: int | None = None
    visibility: str | None = None
    secrecy: float | None = None
    rumorability: float | None = None
    reliability: float | None = None


def current_day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _rng_for(conn: sqlite3.Connection, salt: int) -> random.Random:
    row = conn.execute("SELECT rng_seed, current_day FROM world_state WHERE id=1").fetchone()
    return random.Random(int(row[0]) * 1_000_003 + int(row[1]) * 9_973 + salt)


def log_event(conn: sqlite3.Connection, event: SimEvent) -> int:
    location_id = event.location_id
    if location_id is None and event.source_actor_id is not None:
        row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (event.source_actor_id,)).fetchone()
        if row and row[0] is not None:
            location_id = int(row[0])
    cur = conn.execute(
        """INSERT INTO events(day,event_type,title,summary,severity,location_id,source_actor_id)
           VALUES (?,?,?,?,?,?,?)""",
        (event.day, event.event_type, event.title, event.summary, event.severity, location_id, event.source_actor_id),
    )
    event_id = int(cur.lastrowid)
    for actor_id in event.target_actor_ids:
        conn.execute(
            "INSERT OR IGNORE INTO event_targets(event_id,actor_id,impact) VALUES (?,?,?)",
            (event_id, actor_id, "direct"),
        )
        _wake_actor_if_needed(conn, actor_id, event.severity, event.day)
    register_event_information(
        conn, event_id, day=event.day, visibility=event.visibility, secrecy=event.secrecy,
        rumorability=event.rumorability, reliability=event.reliability
    )
    # v0.7: consequences become durable memories/thread evidence. Import lazily to
    # keep the simulation core free of circular module imports.
    try:
        from .emergence import ingest_event
        ingest_event(conn, event_id)
    except Exception as exc:
        # Emergence recognition must never block authoritative event recording.
        conn.execute(
            "INSERT OR REPLACE INTO runtime_flags(key,value,updated_at) VALUES ('last_emergence_error',?,CURRENT_TIMESTAMP)",
            (str(exc),),
        )
    return event_id


def _effective_tier(row: sqlite3.Row, day: int) -> str:
    forced = row["forced_tier"]
    forced_until = row["forced_until_day"]
    if forced and forced_until is not None and day <= forced_until:
        return str(forced)
    return str(row["tier"])


def _wake_actor_if_needed(conn: sqlite3.Connection, actor_id: int, severity: int, day: int) -> None:
    row = conn.execute(
        "SELECT tier,wake_threshold,forced_tier,forced_until_day FROM simulation_profiles WHERE actor_id=?",
        (actor_id,),
    ).fetchone()
    if not row or severity < int(row["wake_threshold"]):
        return

    tier = str(row["tier"])
    if tier == "DORMANT":
        forced_tier = "STRATEGIC" if severity < 5 else "ACTIVE"
        duration = 45 if forced_tier == "STRATEGIC" else 21
    elif tier == "STRATEGIC" and severity >= 5:
        forced_tier = "ACTIVE"
        duration = 21
    else:
        return

    conn.execute(
        """UPDATE simulation_profiles
           SET forced_tier=?, forced_until_day=?, next_review_day=MIN(next_review_day, ?)
           WHERE actor_id=?""",
        (forced_tier, day + duration, day + 1, actor_id),
    )


def _expire_forced_tiers(conn: sqlite3.Connection, day: int) -> None:
    conn.execute(
        """UPDATE simulation_profiles
           SET forced_tier=NULL, forced_until_day=NULL
           WHERE forced_until_day IS NOT NULL AND forced_until_day < ?""",
        (day,),
    )


def _expire_agreements(conn: sqlite3.Connection, day: int) -> None:
    conn.execute(
        """UPDATE agreements SET status='expired'
           WHERE status='active' AND expiry_day IS NOT NULL AND expiry_day < ?""",
        (day,),
    )


def _process_clock(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> None:
    owner = row["owner_actor_id"]
    title = str(row["title"])
    payload = json.loads(row["payload_json"] or "{}")
    summary = payload.get("summary", f"Clock resolved: {title}")
    event = SimEvent(
        day=day,
        event_type=f"clock:{row['resolution_type']}",
        title=title,
        summary=summary,
        severity=int(row["severity"]),
        source_actor_id=owner,
        target_actor_ids=(owner,) if owner else (),
        location_id=(conn.execute("SELECT current_location_id FROM actors WHERE id=?", (owner,)).fetchone()[0] if owner else None),
    )
    log_event(conn, event)
    conn.execute(
        "UPDATE clocks SET status='resolved', resolved_day=? WHERE id=?",
        (day, row["id"]),
    )


def _resolve_background_process(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> None:
    elapsed = max(0, day - int(row["last_resolved_day"]))
    if elapsed == 0:
        return

    actor_id = int(row["actor_id"])
    rng = _rng_for(conn, int(row["id"]) * 7919 + day)
    base_delta = float(row["rate_per_30_days"]) * elapsed / 30.0
    noise_scale = abs(base_delta) * float(row["volatility"])
    noise = rng.gauss(0.0, noise_scale) if noise_scale > 0 else 0.0
    delta = base_delta + noise
    accumulator = float(row["accumulator"]) + abs(delta)

    metric_key = row["metric_key"]
    if metric_key:
        metric = conn.execute(
            "SELECT id,value,min_value,max_value FROM metrics WHERE actor_id=? AND key=?",
            (actor_id, metric_key),
        ).fetchone()
        if metric:
            value = float(metric["value"]) + delta
            if metric["min_value"] is not None:
                value = max(value, float(metric["min_value"]))
            if metric["max_value"] is not None:
                value = min(value, float(metric["max_value"]))
            conn.execute(
                "UPDATE metrics SET value=?, updated_day=? WHERE id=?",
                (value, day, metric["id"]),
            )

    threshold = float(row["event_threshold"])
    while accumulator >= threshold:
        accumulator -= threshold
        actor_name = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()[0]
        log_event(
            conn,
            SimEvent(
                day=day,
                event_type=f"background:{row['process_type']}",
                title=f"Background change: {actor_name}",
                summary=(
                    f"{actor_name}'s off-screen process '{row['name']}' accumulated enough change "
                    f"to become world-significant. Dormant simulation produced this event without "
                    f"requiring day-by-day scenes."
                ),
                severity=int(row["event_severity"]),
                source_actor_id=actor_id,
                target_actor_ids=(actor_id,),
                location_id=conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()[0],
            ),
        )

    conn.execute(
        "UPDATE background_processes SET accumulator=?, last_resolved_day=? WHERE id=?",
        (accumulator, day, row["id"]),
    )


def _review_actor(conn: sqlite3.Connection, profile: sqlite3.Row, day: int) -> None:
    actor_id = int(profile["actor_id"])
    tier = _effective_tier(profile, day)
    # The profile cadence is authoritative for the actor's normal resolution tier.
    # Only a temporary promotion may shorten it. The old unconditional min() silently
    # forced every DORMANT actor to <=60-day reviews and every STRATEGIC actor to <=14,
    # defeating campaign-specific structural cadences and causing full-world decision floods.
    cadence = int(profile["cadence_days"])
    if tier != str(profile["tier"]):
        cadence = min(cadence, DEFAULT_CADENCE[tier])
    actor = conn.execute("SELECT name,status,actor_type FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not actor:
        return
    # Deceased characters cannot continue producing autonomous choices. v0.26.0 left their
    # simulation profiles alive, so century-scale runs accumulated tens of thousands of
    # posthumous decisions. Retire the scheduler row defensively even when an old save or an
    # external/admin edit marked death without going through household_life.mark_actor_deceased.
    if str(actor["actor_type"]) == "character" and str(actor["status"] or "").lower() in ("dead", "deceased"):
        conn.execute("DELETE FROM simulation_profiles WHERE actor_id=?", (actor_id,))
        return

    # All tiers resolve their own background processes. Resolution granularity differs,
    # but DORMANT never means frozen.
    processes = conn.execute(
        "SELECT * FROM background_processes WHERE actor_id=? AND active=1",
        (actor_id,),
    ).fetchall()
    for process in processes:
        _resolve_background_process(conn, process, day)

    # The configured player is not an autonomous NPC. Passive/background state can still
    # advance with world time, but the engine must never choose the player's intentions.
    player_row = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    if player_row and player_row[0] is not None and int(player_row[0]) == actor_id:
        conn.execute(
            "UPDATE simulation_profiles SET last_review_day=?,next_review_day=? WHERE actor_id=?",
            (day, day + cadence, actor_id),
        )
        return

    # v0.2: every reviewed non-player actor makes a structured decision. Active/Strategic actors
    # get frequent decisions; Dormant actors make coarser decisions at their slower cadence.
    decision_id = decide_actor(conn, actor_id, tier, day)
    decision = conn.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
    if decision:
        # The decisions table is the immutable audit trail for routine choices. The public
        # event stream only receives decisions that become world-significant, avoiding a
        # flood of tiny two-day progress entries from ACTIVE actors.
        outcome = decision["outcome_summary"] or ""
        significant = "Goal completed" in outcome or "additional overreach pressure" in outcome
        if significant:
            log_event(
                conn,
                SimEvent(
                    day=day,
                    event_type="actor_decision",
                    title=f"Decision consequence: {actor['name']}",
                    summary=f"{decision['rationale']} {outcome}".strip(),
                    severity=2,
                    source_actor_id=actor_id,
                    target_actor_ids=(actor_id,),
                    location_id=conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()[0],
                ),
            )

    # v0.58: profession/service/martial experiences are protagonist-agnostic. The same
    # persisted role and circumstances expose an NPC to the same kind of lived opportunities.
    try:
        # Use elapsed simulation time for the hazard exposure.  Under long-horizon compressed
        # resolution a 30-day actor may be reviewed at a later checkpoint; their opportunities
        # must not disappear merely because routine monthly bookkeeping was coalesced.
        elapsed_role_days=max(cadence, day-int(profile['last_review_day'] or 0))
        process_role_experience_review(conn, actor_id, elapsed_role_days, event_logger=_world_event_logger(conn))
    except Exception as exc:
        conn.execute("INSERT OR REPLACE INTO runtime_flags(key,value,updated_at) VALUES ('last_role_experience_error',?,CURRENT_TIMESTAMP)",(str(exc),))

    next_day = day + cadence
    conn.execute(
        """UPDATE simulation_profiles
           SET last_review_day=?, next_review_day=?
           WHERE actor_id=?""",
        (day, next_day, actor_id),
    )

def _world_event_logger(conn: sqlite3.Connection):
    def emit(**kwargs):
        return log_event(conn, SimEvent(**kwargs))
    return emit


def _instrumented_process(conn: sqlite3.Connection, process_key: str, day: int, fn, *args, **kwargs):
    result = fn(*args, **kwargs)
    if isinstance(result, dict):
        executed = sum(int(v) for v in result.values() if isinstance(v, (int, float)) and v > 0)
    elif isinstance(result, (list, tuple)):
        executed = len(result)
    elif result is None:
        executed = 0
    else:
        executed = 1
    try:
        from .coverage import record_process_execution
        row = conn.execute("SELECT id FROM coverage_runs WHERE status='running' ORDER BY id DESC LIMIT 1").fetchone()
        run_id = int(row[0]) if row else None
        record_process_execution(conn, process_key, coverage_run_id=run_id, due_count=executed, eligible_count=executed,
                                 executed_count=executed, changed_count=executed, result=result, day=day)
    except Exception:
        # Observability must never become a second authority that can stop the world clock.
        pass
    return result


def advance_connection_legacy(conn: sqlite3.Connection, days: int) -> list[sqlite3.Row]:
    """Advance authoritative world state on an existing connection.

    This is the core clock used both by admin simulation and player turns. Player presence
    does not define the simulation frontier: actor clocks, NPC interactions, information,
    and location-level world processes all receive their own checkpoints.
    """
    if days < 1:
        raise ValueError("days must be >= 1")
    start_day = current_day(conn)
    cursor_day = start_day
    end = start_day + days
    from .player import process_camera_succession

    while True:
        next_clock = conn.execute(
            "SELECT MIN(due_day) FROM clocks WHERE status='pending' AND due_day<=? AND due_day>?",
            (end, cursor_day),
        ).fetchone()[0]
        next_review = conn.execute(
            "SELECT MIN(next_review_day) FROM simulation_profiles WHERE next_review_day<=? AND next_review_day>?",
            (end, cursor_day),
        ).fetchone()[0]
        next_interaction = conn.execute(
            "SELECT MIN(response_due_day) FROM interactions WHERE status='pending' AND response_due_day<=? AND response_due_day>?",
            (end, cursor_day),
        ).fetchone()[0]
        next_information = next_information_due_day(conn, cursor_day, end)
        next_world = next_world_process_due_day(conn, cursor_day, end)
        next_civilian = next_civilian_due_day(conn, cursor_day, end)
        next_health = next_health_due_day(conn, cursor_day, end)
        next_religion = next_religion_due_day(conn, cursor_day, end)
        next_ecology = next_ecology_due_day(conn, cursor_day, end)
        next_agriculture = next_agriculture_due_day(conn, cursor_day, end)
        next_politics = next_politics_due_day(conn, cursor_day, end)
        next_orglife = next_organization_lifecycle_due_day(conn, cursor_day, end)
        next_education = next_education_due_day(conn, cursor_day, end)
        next_logistics = next_logistics_due_day(conn, cursor_day, end)
        next_merchant = next_merchant_due_day(conn, cursor_day, end)
        next_craft = next_craft_due_day(conn, cursor_day, end)
        next_growth = next_growth_due_day(conn, cursor_day, end)
        next_law = next_law_due_day(conn, cursor_day, end)
        next_cultivation = next_cultivation_due_day(conn, cursor_day, end)
        next_groundbinding = next_groundbinding_due_day(conn, cursor_day, end)
        next_tournament = next_tournament_due_day(conn, cursor_day, end)
        next_spectacle = next_spectacle_due_day(conn, cursor_day, end)
        next_underworld = next_underworld_due_day(conn, cursor_day, end)
        next_hollow = next_hollow_due_day(conn, cursor_day, end)
        next_psych = next_psych_due_day(conn, cursor_day, end)
        next_underworld_medicine = next_underworld_medicine_due_day(conn, cursor_day, end)
        next_war = next_war_due_day(conn, cursor_day, end)
        next_resolution = next_resolution_due_day(conn, cursor_day, end)
        next_patronage = next_patronage_due_day(conn, cursor_day, end)
        candidates = [d for d in (next_clock, next_review, next_interaction, next_information, next_world, next_civilian, next_health, next_religion, next_ecology, next_agriculture, next_politics, next_orglife, next_education, next_logistics, next_merchant, next_craft, next_growth, next_law, next_cultivation, next_groundbinding, next_tournament, next_spectacle, next_underworld, next_hollow, next_psych, next_underworld_medicine, next_war, next_resolution, next_patronage) if d is not None]
        if not candidates:
            break
        checkpoint = min(int(x) for x in candidates)
        conn.execute("UPDATE world_state SET current_day=?, updated_at=CURRENT_TIMESTAMP WHERE id=1", (checkpoint,))
        _expire_forced_tiers(conn, checkpoint)
        _expire_agreements(conn, checkpoint)

        due_clocks = conn.execute(
            "SELECT * FROM clocks WHERE status='pending' AND due_day<=? ORDER BY due_day,id",
            (checkpoint,),
        ).fetchall()
        for clock in due_clocks:
            _process_clock(conn, clock, checkpoint)

        process_due_interactions(conn, checkpoint)

        due_profiles = conn.execute(
            "SELECT * FROM simulation_profiles WHERE next_review_day<=? ORDER BY next_review_day,actor_id",
            (checkpoint,),
        ).fetchall()
        for profile in due_profiles:
            _review_actor(conn, profile, checkpoint)
        _instrumented_process(conn, "resolution", checkpoint, process_due_resolution, conn, checkpoint)

        # Regional processes are independent of named actors and therefore independent of camera location.
        _instrumented_process(conn, "world", checkpoint, process_due_world_processes, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "ecology", checkpoint, process_due_ecology, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "agriculture", checkpoint, process_due_agriculture, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "logistics", checkpoint, process_due_logistics, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "merchant", checkpoint, process_due_merchant, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "craft", checkpoint, process_due_craft, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "civilian", checkpoint, process_due_civilian, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "growth", checkpoint, process_due_growth, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "underworld", checkpoint, process_due_underworld, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "underworld_medicine", checkpoint, process_due_underworld_medicine, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "law", checkpoint, process_due_law, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "war", checkpoint, process_due_war, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "groundbinding", checkpoint, process_due_groundbinding, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "health", checkpoint, process_due_health, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "psychology", checkpoint, process_due_psychology, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "hollow", checkpoint, process_due_hollow, conn, checkpoint, event_logger=_world_event_logger(conn))
        process_camera_succession(conn)
        _instrumented_process(conn, "religion", checkpoint, process_due_religion, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "patronage", checkpoint, process_due_patronage, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "politics", checkpoint, process_due_politics, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "organization_lifecycle", checkpoint, process_due_organization_lifecycle, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "education", checkpoint, process_due_education, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "cultivation", checkpoint, process_due_cultivation, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "tournament", checkpoint, process_due_tournaments, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "spectacle", checkpoint, process_due_spectacle, conn, checkpoint, event_logger=_world_event_logger(conn))
        _instrumented_process(conn, "information", checkpoint, process_information, conn, checkpoint)
        cursor_day = checkpoint

    conn.execute("UPDATE world_state SET current_day=?, updated_at=CURRENT_TIMESTAMP WHERE id=1", (end,))
    _expire_forced_tiers(conn, end)
    _expire_agreements(conn, end)
    process_due_interactions(conn, end)

    # Actor and location processes both catch up at the terminal day even if their normal
    # review cadence did not land exactly on it. This is the 'nothing freezes off-camera' guarantee.
    processes = conn.execute("SELECT * FROM background_processes WHERE active=1").fetchall()
    for process in processes:
        _resolve_background_process(conn, process, end)
    _instrumented_process(conn, "resolution", end, process_due_resolution, conn, end)
    _instrumented_process(conn, "world_catchup", end, catch_up_world_processes, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "ecology", end, process_due_ecology, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "agriculture", end, process_due_agriculture, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "logistics", end, process_due_logistics, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "merchant", end, process_due_merchant, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "craft", end, process_due_craft, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "civilian", end, process_due_civilian, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "growth", end, process_due_growth, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "underworld", end, process_due_underworld, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "underworld_medicine", end, process_due_underworld_medicine, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "law", end, process_due_law, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "war", end, process_due_war, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "groundbinding", end, process_due_groundbinding, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "health", end, process_due_health, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "psychology", end, process_due_psychology, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "hollow", end, process_due_hollow, conn, end, event_logger=_world_event_logger(conn))
    process_camera_succession(conn)
    _instrumented_process(conn, "religion", end, process_due_religion, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "patronage", end, process_due_patronage, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "politics", end, process_due_politics, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "organization_lifecycle", end, process_due_organization_lifecycle, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "education", end, process_due_education, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "cultivation", end, process_due_cultivation, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "tournament", end, process_due_tournaments, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "spectacle", end, process_due_spectacle, conn, end, event_logger=_world_event_logger(conn))
    _instrumented_process(conn, "information", end, process_information, conn, end)

    return conn.execute(
        "SELECT * FROM events WHERE day>? AND day<=? ORDER BY day,id",
        (start_day, end),
    ).fetchall()



# World-package system switch -> simulation processes it owns (a switched-off system is never registered).
SYSTEM_PROCESSES = {
    "caerness_underworld": ("underworld", "underworld_medicine"),
    "cultivation": ("cultivation", "tournament", "spectacle"),
    "groundbinding": ("groundbinding",),
    "hollow": ("hollow",),
    "caerness_religions": ("religion",),
    "outfits": ("outfit_money", "outfit_incidents", "crime_response"),
}


def disabled_process_keys(conn: sqlite3.Connection) -> frozenset[str]:
    """Process keys the campaign's world package switches off (loaded once per advance)."""
    from .world_package import current_package
    systems = current_package(conn).systems
    return frozenset(k for sw, keys in SYSTEM_PROCESSES.items() if not systems.get(sw, False) for k in keys)


def build_default_process_registry(*, eager_requery: bool = True, disabled: frozenset[str] = frozenset()):
    """Build the production domain-process registry.

    SQL due dates remain authoritative.  ``eager_requery=True`` is deliberate: the
    scheduler audit found that domain A can schedule earlier work for domain B after B's
    prior due date was cached.  Re-querying the small process set is cheap and preserves
    causal scheduling; the lazy mode remains only for controlled benchmarks.
    """
    from .process_registry import ProcessRegistry, ProcessSpec
    reg = ProcessRegistry(eager_requery=eager_requery)
    _register = reg.register
    reg.register = lambda spec: None if spec.key in disabled else _register(spec)
    reg.register(ProcessSpec("resolution", next_resolution_due_day, process_due_resolution, needs_event_logger=False))
    reg.register(ProcessSpec("world", next_world_process_due_day, process_due_world_processes,
                             terminal_run=catch_up_world_processes, terminal_key="world_catchup"))
    reg.register(ProcessSpec("ecology", next_ecology_due_day, process_due_ecology))
    reg.register(ProcessSpec("agriculture", next_agriculture_due_day, process_due_agriculture))
    reg.register(ProcessSpec("logistics", next_logistics_due_day, process_due_logistics))
    reg.register(ProcessSpec("merchant", next_merchant_due_day, process_due_merchant))
    reg.register(ProcessSpec("craft", next_craft_due_day, process_due_craft))
    reg.register(ProcessSpec("civilian", next_civilian_due_day, process_due_civilian))
    reg.register(ProcessSpec("profession", next_profession_due_day, process_due_profession))
    reg.register(ProcessSpec("service_fulfillment", next_service_due_day, process_due_services))
    reg.register(ProcessSpec("growth", next_growth_due_day, process_due_growth))
    reg.register(ProcessSpec("underworld", next_underworld_due_day, process_due_underworld))
    reg.register(ProcessSpec("underworld_medicine", next_underworld_medicine_due_day, process_due_underworld_medicine))
    reg.register(ProcessSpec("law", next_law_due_day, process_due_law))
    reg.register(ProcessSpec("war", next_war_due_day, process_due_war))
    reg.register(ProcessSpec("groundbinding", next_groundbinding_due_day, process_due_groundbinding))
    reg.register(ProcessSpec("health", next_health_due_day, process_due_health))
    reg.register(ProcessSpec("psychology", next_psych_due_day, process_due_psychology))
    reg.register(ProcessSpec("hollow", next_hollow_due_day, process_due_hollow))
    reg.register(ProcessSpec("religion", next_religion_due_day, process_due_religion))
    reg.register(ProcessSpec("politics", next_politics_due_day, process_due_politics))
    reg.register(ProcessSpec("conflict", next_conflict_due_day, process_due_conflict))
    reg.register(ProcessSpec("organization_lifecycle", next_organization_lifecycle_due_day, process_due_organization_lifecycle))
    reg.register(ProcessSpec("seeking", next_seeking_due_day, process_due_seeking))
    reg.register(ProcessSpec("attention", next_attention_due_day, process_due_attention))
    reg.register(ProcessSpec("patronage", next_patronage_due_day, process_due_patronage))
    reg.register(ProcessSpec("education", next_education_due_day, process_due_education))
    reg.register(ProcessSpec("cultivation", next_cultivation_due_day, process_due_cultivation))
    reg.register(ProcessSpec("tournament", next_tournament_due_day, process_due_tournaments))
    reg.register(ProcessSpec("spectacle", next_spectacle_due_day, process_due_spectacle))
    reg.register(ProcessSpec("information", next_information_due_day, process_information, needs_event_logger=False))
    # PERF-01: people forget minor rumours nobody repeats (bounded storage; the world keeps its history).
    reg.register(ProcessSpec("memory", next_memory_due_day, process_due_memory, needs_event_logger=False))
    return reg


_REGISTRY_BLOCK_A = (
    "resolution", "world", "ecology", "agriculture", "logistics", "merchant", "craft", "civilian", "profession", "service_fulfillment", "growth",
    "underworld", "underworld_medicine", "law", "war", "groundbinding", "health", "psychology", "hollow",
)
_REGISTRY_BLOCK_B = ("religion", "patronage", "politics", "conflict", "organization_lifecycle", "seeking", "attention", "education", "cultivation", "tournament", "spectacle", "information", "memory")


def _next_scheduler_expiry_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    """Next deadline for state that used to be expired opportunistically at checkpoints.

    API call boundaries must not create simulation checkpoints.  Forced simulation tiers
    and agreements therefore advertise their own exact expiry transition day.  Existing
    semantics expire when ``day > *_until/expiry_day``, hence the +1.
    """
    vals: list[int] = []
    row = conn.execute(
        """SELECT MIN(forced_until_day + 1) FROM simulation_profiles
           WHERE forced_until_day IS NOT NULL AND forced_until_day + 1>? AND forced_until_day + 1<=?""",
        (after_day, end_day),
    ).fetchone()
    if row and row[0] is not None:
        vals.append(int(row[0]))
    row = conn.execute(
        """SELECT MIN(expiry_day + 1) FROM agreements
           WHERE status='active' AND expiry_day IS NOT NULL AND expiry_day + 1>? AND expiry_day + 1<=?""",
        (after_day, end_day),
    ).fetchone()
    if row and row[0] is not None:
        vals.append(int(row[0]))
    return min(vals) if vals else None


def advance_connection_registry(conn: sqlite3.Connection, days: int) -> list[sqlite3.Row]:
    """Advance via the SQL-authoritative ProcessRegistry candidate scheduler.

    This is the production-candidate replacement for the duplicated hand-enumerated
    process blocks in :func:`advance_connection`.  Actor reviews, clocks, interactions,
    camera succession and terminal catch-up retain their existing relative ordering.
    """
    if days < 1:
        raise ValueError("days must be >= 1")
    start_day = current_day(conn)
    cursor_day = start_day
    end = start_day + days
    from .player import process_camera_succession
    disabled = disabled_process_keys(conn)
    registry = build_default_process_registry(eager_requery=True, disabled=disabled)
    block_a = [k for k in _REGISTRY_BLOCK_A if k not in disabled]
    block_b = [k for k in _REGISTRY_BLOCK_B if k not in disabled]
    logger = _world_event_logger(conn)

    def running_coverage_id() -> int | None:
        try:
            row = conn.execute("SELECT id FROM coverage_runs WHERE status='running' ORDER BY id DESC LIMIT 1").fetchone()
            return int(row[0]) if row else None
        except sqlite3.OperationalError:
            return None

    while True:
        next_clock = conn.execute(
            "SELECT MIN(due_day) FROM clocks WHERE status='pending' AND due_day<=? AND due_day>?", (end, cursor_day)
        ).fetchone()[0]
        next_review = conn.execute(
            "SELECT MIN(next_review_day) FROM simulation_profiles WHERE next_review_day<=? AND next_review_day>?", (end, cursor_day)
        ).fetchone()[0]
        next_interaction = conn.execute(
            "SELECT MIN(response_due_day) FROM interactions WHERE status='pending' AND response_due_day<=? AND response_due_day>?", (end, cursor_day)
        ).fetchone()[0]
        registry_next = registry.next_checkpoint(conn, cursor_day, end)
        next_expiry = _next_scheduler_expiry_day(conn, cursor_day, end)
        candidates = [d for d in (next_clock, next_review, next_interaction, registry_next, next_expiry) if d is not None]
        if not candidates:
            break
        checkpoint = min(int(x) for x in candidates)
        if checkpoint <= cursor_day:
            raise RuntimeError(f"scheduler failed to advance: cursor={cursor_day}, checkpoint={checkpoint}")
        conn.execute("UPDATE world_state SET current_day=?, updated_at=CURRENT_TIMESTAMP WHERE id=1", (checkpoint,))
        _expire_forced_tiers(conn, checkpoint)
        _expire_agreements(conn, checkpoint)

        for clock in conn.execute(
            "SELECT * FROM clocks WHERE status='pending' AND due_day<=? ORDER BY due_day,id", (checkpoint,)
        ).fetchall():
            _process_clock(conn, clock, checkpoint)

        process_due_interactions(conn, checkpoint)
        for profile in conn.execute(
            "SELECT * FROM simulation_profiles WHERE next_review_day<=? ORDER BY next_review_day,actor_id", (checkpoint,)
        ).fetchall():
            _review_actor(conn, profile, checkpoint)

        cov = running_coverage_id()
        registry.run_due(conn, checkpoint, event_logger=logger, coverage_run_id=cov,
                         only_keys=block_a, run_one_off=False)
        process_camera_succession(conn)
        registry.run_due(conn, checkpoint, event_logger=logger, coverage_run_id=cov,
                         only_keys=block_b, run_one_off=True)
        cursor_day = checkpoint

    # Reaching the caller-requested end day is *not* itself a causal checkpoint.
    # All scheduled work <= end was already executed by the loop above.  The former
    # terminal catch-up resolved every domain at arbitrary API boundaries, making
    # advance(90) differ from advance(30)+advance(30)+advance(30).  Background actor
    # processes advance on their owning actor's review cadence; world/domain owners
    # advance on their registered due dates; expiries now advertise exact deadlines.
    conn.execute("UPDATE world_state SET current_day=?, updated_at=CURRENT_TIMESTAMP WHERE id=1", (end,))

    return conn.execute(
        "SELECT * FROM events WHERE day>? AND day<=? ORDER BY day,id", (start_day, end)
    ).fetchall()

def advance_connection(conn: sqlite3.Connection, days: int) -> list[sqlite3.Row]:
    """Advance authoritative world state through the production ProcessRegistry scheduler."""
    return advance_connection_registry(conn, days)


def advance(days: int) -> list[sqlite3.Row]:
    init_db()
    with connect() as conn:
        rows = advance_connection(conn, days)
        conn.commit()
        return rows


def seed_demo() -> None:
    init_db()
    with connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM actors WHERE is_demo=1").fetchone()[0]:
            return

        # Geography in the demo uses currently accepted names, but demo institutions are explicitly non-canon.
        for name, kind, owner, canon in [
            ("Underheaven", "empire", "Underheaven Empire", 1),
            ("Crownlands", "region", "Underheaven Empire", 1),
            ("Hearthlands", "region", "Underheaven Empire", 1),
            ("Crownhold", "city", "Underheaven Empire", 1),
            ("Cairnholt", "city", "Underheaven Empire", 1),
            ("Toll's Reach", "free city", None, 1),
            ("Dunmoor", "kingdom", "Dunmoor", 1),
            ("Windmere", "kingdom", "Windmere", 1),
        ]:
            conn.execute(
                "INSERT OR IGNORE INTO locations(name,kind,political_owner,is_canon) VALUES (?,?,?,?)",
                (name, kind, owner, canon),
            )

        hearth_id = conn.execute("SELECT id FROM locations WHERE name='Hearthlands'").fetchone()[0]
        toll_id = conn.execute("SELECT id FROM locations WHERE name=\"Toll's Reach\"").fetchone()[0]
        cairn_id = conn.execute("SELECT id FROM locations WHERE name='Cairnholt'").fetchone()[0]

        demos = [
            ("[DEMO] River Lantern Escort Company", "institution", "escort company", toll_id, "ACTIVE", 2, 0.7, 0.7),
            ("[DEMO] House of Seven Ledgers", "institution", "merchant house", cairn_id, "STRATEGIC", 14, 0.45, 0.65),
            ("[DEMO] Remote Reed Sect", "institution", "martial sect", hearth_id, "DORMANT", 60, 0.35, 0.55),
            ("[DEMO] North Road Brotherhood", "institution", "road organization", hearth_id, "DORMANT", 45, 0.65, 0.5),
        ]
        for name, actor_type, subtype, loc, tier, cadence, volatility, agency in demos:
            cur = conn.execute(
                "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,is_demo) VALUES (?,?,?,?,?,1)",
                (name, actor_type, subtype, loc, loc),
            )
            actor_id = cur.lastrowid
            conn.execute(
                "INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,next_review_day) VALUES (?,?,?,?,?,?)",
                (actor_id, tier, cadence, volatility, agency, cadence),
            )
            conn.execute(
                "INSERT INTO metrics(actor_id,key,value,min_value,updated_day) VALUES (?,?,?,?,0)",
                (actor_id, "institutional_pressure", 0.0, 0.0),
            )

        rows = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM actors WHERE is_demo=1")}

        # v0.2 decision inputs. These are test personalities, not setting canon.
        drives = {
            "[DEMO] River Lantern Escort Company": (0.35, 0.55, 0.55, 0.75, 0.55, 0.8),
            "[DEMO] House of Seven Ledgers": (0.2, 0.35, 0.8, 0.55, 0.8, 0.95),
            "[DEMO] Remote Reed Sect": (0.25, 0.3, 0.85, 0.9, 0.45, 0.5),
            "[DEMO] North Road Brotherhood": (0.65, 0.7, 0.35, 0.55, 0.65, 0.65),
        }
        for name, values in drives.items():
            conn.execute(
                """INSERT INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism)
                   VALUES (?,?,?,?,?,?,?)""",
                (rows[name], *values),
            )

        conn.execute(
            "INSERT INTO resources(actor_id,resource_type,amount,unit,updated_day) VALUES (?,?,?,?,0)",
            (rows["[DEMO] River Lantern Escort Company"], "operating_reserve", 18.0, "abstract reserve"),
        )
        conn.execute(
            "INSERT INTO resources(actor_id,resource_type,amount,unit,updated_day) VALUES (?,?,?,?,0)",
            (rows["[DEMO] House of Seven Ledgers"], "capital", 75.0, "abstract capital"),
        )
        conn.execute(
            "INSERT INTO pressures(actor_id,kind,description,intensity,threshold,updated_day) VALUES (?,?,?,?,?,0)",
            (rows["[DEMO] Remote Reed Sect"], "succession", "An unresolved succession divide among senior members", 4.0, 7.0),
        )
        conn.execute(
            "INSERT INTO pressures(actor_id,kind,description,intensity,threshold,updated_day) VALUES (?,?,?,?,?,0)",
            (rows["[DEMO] North Road Brotherhood"], "road_losses", "Increasing losses and pressure along its usual routes", 3.0, 7.0),
        )

        # Relationship data gives the decision layer a real alternative to solitary action.
        ensure_reciprocal_relationship(
            conn, rows["[DEMO] River Lantern Escort Company"], rows["[DEMO] House of Seven Ledgers"], 0,
            stance=20.0, trust=25.0, obligation=10.0, familiarity=40.0,
        )
        ensure_reciprocal_relationship(
            conn, rows["[DEMO] North Road Brotherhood"], rows["[DEMO] River Lantern Escort Company"], 0,
            stance=-35.0, trust=-20.0, familiarity=35.0,
        )

        # The dormant entities have processes that change even before their formal review date.
        conn.execute(
            """INSERT INTO background_processes
               (actor_id,name,process_type,metric_key,rate_per_30_days,volatility,event_threshold,event_severity)
               VALUES (?,?,?,?,?,?,?,?)""",
            (rows["[DEMO] Remote Reed Sect"], "internal succession pressure", "internal_politics", "institutional_pressure", 1.4, 0.4, 4.5, 3),
        )
        conn.execute(
            """INSERT INTO background_processes
               (actor_id,name,process_type,metric_key,rate_per_30_days,volatility,event_threshold,event_severity)
               VALUES (?,?,?,?,?,?,?,?)""",
            (rows["[DEMO] North Road Brotherhood"], "road pressure", "territorial_pressure", "institutional_pressure", 1.8, 0.65, 5.0, 3),
        )
        conn.execute(
            """INSERT INTO background_processes
               (actor_id,name,process_type,metric_key,rate_per_30_days,volatility,event_threshold,event_severity)
               VALUES (?,?,?,?,?,?,?,?)""",
            (rows["[DEMO] House of Seven Ledgers"], "commercial expansion", "commerce", "institutional_pressure", 0.9, 0.3, 8.0, 2),
        )
        conn.execute(
            "INSERT INTO goals(actor_id,description,priority,progress,created_day) VALUES (?,?,?,?,0)",
            (rows["[DEMO] River Lantern Escort Company"], "Secure a profitable long-road contract", 60, 0.0),
        )
        conn.execute(
            "INSERT INTO goals(actor_id,description,priority,progress,created_day) VALUES (?,?,?,?,0)",
            (rows["[DEMO] House of Seven Ledgers"], "Expand influence among caravan brokers", 55, 0.0),
        )
        conn.execute(
            "INSERT INTO goals(actor_id,description,priority,progress,created_day) VALUES (?,?,?,?,0)",
            (rows["[DEMO] Remote Reed Sect"], "Resolve succession without breaking the sect", 75, 0.0),
        )
        conn.execute(
            "INSERT INTO goals(actor_id,description,priority,progress,created_day) VALUES (?,?,?,?,0)",
            (rows["[DEMO] North Road Brotherhood"], "Keep its road network viable", 68, 0.0),
        )

        conn.execute(
            """INSERT INTO clocks(title,due_day,owner_actor_id,severity,resolution_type,payload_json,created_day)
               VALUES (?,?,?,?,?,?,0)""",
            (
                "[DEMO] Remote sect succession meeting",
                37,
                rows["[DEMO] Remote Reed Sect"],
                4,
                "institutional_decision",
                json.dumps({"summary": "The remote sect's long-scheduled succession meeting occurs despite the player being elsewhere."}),
            ),
        )


        # v0.4 information routes and a non-canon player make the demo sceneable.
        crownhold_id = conn.execute("SELECT id FROM locations WHERE name='Crownhold'").fetchone()[0]
        dunmoor_id = conn.execute("SELECT id FROM locations WHERE name='Dunmoor'").fetchone()[0]
        windmere_id = conn.execute("SELECT id FROM locations WHERE name='Windmere'").fetchone()[0]
        for a,b,kind,days,traffic in [
            (toll_id, cairn_id, 'road-river', 6, 0.85),
            (cairn_id, crownhold_id, 'imperial road', 10, 0.8),
            (crownhold_id, dunmoor_id, 'north road', 7, 0.55),
            (toll_id, windmere_id, 'coastal road', 5, 0.75),
            (cairn_id, hearth_id, 'regional roads', 2, 0.9),
        ]:
            x,y = sorted((int(a),int(b)))
            conn.execute(
                "INSERT OR IGNORE INTO location_links(location_a_id,location_b_id,route_kind,travel_days,traffic) VALUES (?,?,?,?,?)",
                (x,y,kind,days,traffic),
            )

        # v0.5 world processes prove that places themselves can change off-camera,
        # even when no named actor owns the pressure. These are demo-only.
        conn.execute(
            "INSERT OR IGNORE INTO location_metrics(location_id,key,value,min_value,max_value,updated_day) VALUES (?,?,?,?,?,0)",
            (dunmoor_id, 'border_pressure', 0.0, 0.0, 100.0),
        )
        conn.execute(
            """INSERT INTO world_processes(
                   location_id,name,process_type,metric_key,rate_per_30_days,volatility,event_threshold,
                   event_severity,cadence_days,last_resolved_day,next_review_day,notes,is_demo
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            (dunmoor_id, '[DEMO] northern border pressure', 'regional_pressure', 'border_pressure',
             2.4, 0.2, 3.0, 3, 15, 0, 15,
             'Demonstrates observer-independent regional change far from the player.'),
        )

        player_cur = conn.execute(
            "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,is_demo) VALUES (?,?,?,?,?,1)",
            ('[DEMO] Player Wanderer','character','Long Road wanderer',toll_id,toll_id),
        )
        player_id = int(player_cur.lastrowid)
        conn.execute(
            "INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,next_review_day) VALUES (?,?,?,?,?,?)",
            (player_id,'ACTIVE',2,0.35,0.7,2),
        )
        conn.execute(
            "INSERT INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) VALUES (?,?,?,?,?,?,?)",
            (player_id,0.45,0.55,0.55,0.55,0.55,0.65),
        )
        conn.execute(
            "INSERT INTO player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) VALUES (1,?,?,?,0)",
            (player_id,toll_id,'Demo Campaign'),
        )

        chan = conn.execute(
            """INSERT INTO information_channels(name,channel_kind,owner_actor_id,speed_multiplier,fidelity,secrecy,public_access,notes,is_demo)
               VALUES (?,?,?,?,?,?,?,?,1)""",
            ('[DEMO] Caravan Courier Network','courier',rows['[DEMO] House of Seven Ledgers'],0.55,0.9,0.65,0,
             'Non-canon test network used to prove information can outrun ordinary gossip.'),
        )
        channel_id = int(chan.lastrowid)
        for loc in (toll_id,cairn_id,crownhold_id):
            conn.execute("INSERT INTO channel_locations(channel_id,location_id,strength) VALUES (?,?,?)", (channel_id,loc,0.85))
        conn.execute("INSERT INTO channel_memberships(channel_id,actor_id,role,access_level) VALUES (?,?,?,?)",
                     (channel_id,rows['[DEMO] House of Seven Ledgers'],'owner',1.0))

        conn.commit()


def status() -> dict:
    init_db()
    with connect() as conn:
        day = current_day(conn)
        tiers = {
            r["tier"]: r["n"]
            for r in conn.execute("SELECT tier,COUNT(*) n FROM simulation_profiles GROUP BY tier")
        }
        forced = conn.execute(
            "SELECT COUNT(*) FROM simulation_profiles WHERE forced_tier IS NOT NULL AND forced_until_day>=?",
            (day,),
        ).fetchone()[0]
        pending_clocks = conn.execute("SELECT COUNT(*) FROM clocks WHERE status='pending'").fetchone()[0]
        events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        decisions = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        interactions = conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
        pending_interactions = conn.execute("SELECT COUNT(*) FROM interactions WHERE status='pending'").fetchone()[0]
        agreements = conn.execute("SELECT COUNT(*) FROM agreements WHERE status='active'").fetchone()[0]
        canon_chunks = conn.execute("SELECT COUNT(*) FROM canon_chunks").fetchone()[0]
        rumours = conn.execute("SELECT COUNT(*) FROM rumours WHERE status='circulating'").fetchone()[0]
        pending_info = conn.execute("SELECT COUNT(*) FROM rumour_transmissions WHERE status='pending'").fetchone()[0]
        world_processes = conn.execute("SELECT COUNT(*) FROM world_processes WHERE active=1").fetchone()[0]
        player_actions = conn.execute("SELECT COUNT(*) FROM player_actions").fetchone()[0]
        turns = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
        return {
            "day": day,
            "tiers": tiers,
            "temporarily_promoted": forced,
            "pending_clocks": pending_clocks,
            "events": events,
            "decisions": decisions,
            "interactions": interactions,
            "pending_interactions": pending_interactions,
            "active_agreements": agreements,
            "canon_chunks": canon_chunks,
            "circulating_rumours": rumours,
            "pending_information_transmissions": pending_info,
            "active_world_processes": world_processes,
            "player_actions": player_actions,
            "turns": turns,
            "player_configured": bool(player and player[0]),
            "camera_principle": "Player attention does not define world activity.",
        }


def recent_events(limit: int = 20) -> list[dict]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id,day,event_type,title,summary,severity FROM events ORDER BY day DESC,id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
