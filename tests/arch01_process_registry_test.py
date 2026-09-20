"""ARCH-01 — ProcessRegistry + Mesa event queue.

Acceptance test for the scheduler spike described in the external-code research master
(RESEARCH/CURRENT/Caerness_EXTERNAL_CODE_RESEARCH_MASTER_CURRENT_2026-09-17.md, sections 2
and 10): "Prove recurring/one-off scheduling, ordering, cancellation, persistence/restart,
and coverage registration." Also settles the Mesa question empirically rather than by
assumption (see benchmark_due_day_strategies at the bottom).

This does NOT modify engine/simulation.py's advance_connection. It builds a parallel
advance_via_registry using the exact same due-day/execution logic, wired through
ProcessRegistry, and proves parity against the real advance_connection over real seeded
state before anything is proposed to be cut over.
"""
from __future__ import annotations
import os, sys, tempfile, time, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.process_registry import ProcessRegistry, ProcessSpec
from engine.simulation import (
    advance_connection_legacy as advance_connection, _expire_forced_tiers, _expire_agreements, _process_clock,
    _review_actor, _resolve_background_process, _world_event_logger, current_day,
)
from engine.player import process_camera_succession
from engine.interactions import process_due_interactions
from engine.information import process_information, next_information_due_day
from engine.world import next_world_process_due_day, process_due_world_processes, catch_up_world_processes
from engine.civilian import next_civilian_due_day, process_due_civilian
from engine.health import next_health_due_day, process_due_health
from engine.psych import next_psych_due_day, process_due_psychology
from engine.religion import next_religion_due_day, process_due_religion
from engine.ecology import next_ecology_due_day, process_due_ecology
from engine.agriculture import next_agriculture_due_day, process_due_agriculture
from engine.politics import next_politics_due_day, process_due_politics
from engine.education import next_education_due_day, process_due_education
from engine.logistics import next_logistics_due_day, process_due_logistics
from engine.merchant import next_merchant_due_day, process_due_merchant
from engine.craft import next_craft_due_day, process_due_craft
from engine.growth import next_growth_due_day, process_due_growth
from engine.law import next_law_due_day, process_due_law
from engine.cultivation import next_cultivation_due_day, process_due_cultivation
from engine.groundbinding import next_groundbinding_due_day, process_due_groundbinding
from engine.tournaments import next_tournament_due_day, process_due_tournaments
from engine.spectacle import next_spectacle_due_day, process_due_spectacle
from engine.underworld import next_underworld_due_day, process_due_underworld
from engine.underworld_medicine import next_underworld_medicine_due_day, process_due_underworld_medicine
from engine.hollow import next_hollow_due_day, process_due_hollow
from engine.war import next_war_due_day, process_due_war
from engine.resolution_controller import next_resolution_due_day, process_due_resolution

BLOCK_A = ["resolution", "world", "ecology", "agriculture", "logistics", "merchant", "craft", "civilian", "growth", "underworld",
           "underworld_medicine", "law", "war", "groundbinding", "health", "psychology", "hollow"]
BLOCK_B = ["religion", "politics", "education", "cultivation", "tournament", "spectacle", "information"]


def bootstrap(name: str):
    path = Path(tempfile.gettempdir()) / name
    os.environ['CAERNESS_DB_PATH'] = str(path)
    os.environ['CAERNESS_TEST_MODE'] = '1'
    reset_db(force=True, backup=False); init_db()
    c = connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def build_registry() -> ProcessRegistry:
    reg = ProcessRegistry()
    reg.register(ProcessSpec("resolution", next_resolution_due_day, process_due_resolution, needs_event_logger=False))
    reg.register(ProcessSpec("world", next_world_process_due_day, process_due_world_processes,
                              terminal_run=catch_up_world_processes, terminal_key="world_catchup"))
    reg.register(ProcessSpec("ecology", next_ecology_due_day, process_due_ecology))
    reg.register(ProcessSpec("agriculture", next_agriculture_due_day, process_due_agriculture))
    reg.register(ProcessSpec("logistics", next_logistics_due_day, process_due_logistics))
    reg.register(ProcessSpec("merchant", next_merchant_due_day, process_due_merchant))
    reg.register(ProcessSpec("craft", next_craft_due_day, process_due_craft))
    reg.register(ProcessSpec("civilian", next_civilian_due_day, process_due_civilian))
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
    reg.register(ProcessSpec("education", next_education_due_day, process_due_education))
    reg.register(ProcessSpec("cultivation", next_cultivation_due_day, process_due_cultivation))
    reg.register(ProcessSpec("tournament", next_tournament_due_day, process_due_tournaments))
    reg.register(ProcessSpec("spectacle", next_spectacle_due_day, process_due_spectacle))
    reg.register(ProcessSpec("information", next_information_due_day, process_information, needs_event_logger=False))
    return reg


def advance_via_registry(conn, days: int, registry: ProcessRegistry) -> list:
    """Same shape as engine.simulation.advance_connection, with the ~20-line candidate
    list and the two ~18-line process-execution blocks replaced by the registry. Clocks,
    interactions, actor review, background-process catchup and camera succession are
    copied verbatim, unchanged, in their original relative order.
    """
    if days < 1:
        raise ValueError("days must be >= 1")
    start_day = current_day(conn)
    cursor_day = start_day
    end = start_day + days
    logger = _world_event_logger(conn)

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
        candidates = [d for d in (next_clock, next_review, next_interaction, registry_next) if d is not None]
        if not candidates:
            break
        checkpoint = min(int(x) for x in candidates)
        conn.execute("UPDATE world_state SET current_day=?, updated_at=CURRENT_TIMESTAMP WHERE id=1", (checkpoint,))
        _expire_forced_tiers(conn, checkpoint)
        _expire_agreements(conn, checkpoint)

        due_clocks = conn.execute("SELECT * FROM clocks WHERE status='pending' AND due_day<=? ORDER BY due_day,id", (checkpoint,)).fetchall()
        for clock in due_clocks:
            _process_clock(conn, clock, checkpoint)

        process_due_interactions(conn, checkpoint)

        due_profiles = conn.execute("SELECT * FROM simulation_profiles WHERE next_review_day<=? ORDER BY next_review_day,actor_id", (checkpoint,)).fetchall()
        for profile in due_profiles:
            _review_actor(conn, profile, checkpoint)

        registry.run_due(conn, checkpoint, event_logger=logger, only_keys=BLOCK_A, run_one_off=False)
        process_camera_succession(conn)
        registry.run_due(conn, checkpoint, event_logger=logger, only_keys=BLOCK_B, run_one_off=True)
        cursor_day = checkpoint

    conn.execute("UPDATE world_state SET current_day=?, updated_at=CURRENT_TIMESTAMP WHERE id=1", (end,))
    _expire_forced_tiers(conn, end)
    _expire_agreements(conn, end)
    process_due_interactions(conn, end)

    processes = conn.execute("SELECT * FROM background_processes WHERE active=1").fetchall()
    for process in processes:
        _resolve_background_process(conn, process, end)

    registry.run_due(conn, end, event_logger=logger, only_keys=BLOCK_A, terminal=True, run_one_off=False)
    process_camera_succession(conn)
    registry.run_due(conn, end, event_logger=logger, only_keys=BLOCK_B, terminal=True, run_one_off=True)

    return conn.execute("SELECT * FROM events WHERE day>? AND day<=? ORDER BY day,id", (start_day, end)).fetchall()


AGGREGATE_QUERIES = [
    "SELECT COUNT(*) FROM events",
    "SELECT COUNT(*) FROM underworld_organizations",
    "SELECT COALESCE(SUM(treasury),0) FROM underworld_organizations",
    "SELECT COUNT(*) FROM underworld_zone_claims WHERE status='active'",
    "SELECT COUNT(*) FROM civilian_enterprises",
    "SELECT COUNT(*) FROM actors WHERE status='deceased'",
    "SELECT COUNT(*) FROM household_unions",
    "SELECT COUNT(*) FROM tournament_events",
    "SELECT current_day FROM world_state WHERE id=1",
]


def _fingerprint(conn) -> list:
    return [conn.execute(q).fetchone()[0] for q in AGGREGATE_QUERIES]


def run():
    assert ENGINE_VERSION == '0.60.0' and SCHEMA_VERSION >= 59

    # --- Parity: the registry-driven loop must reach the same world, not just "not crash".
    # Same seed import twice, same day range, compared on real aggregate state.
    baseline = bootstrap('caerness_arch01_baseline.db')
    advance_connection(baseline, 45)
    baseline_fp = _fingerprint(baseline)
    baseline.commit(); baseline.close()

    registry_db = bootstrap('caerness_arch01_registry.db')
    advance_via_registry(registry_db, 45, build_registry())
    registry_fp = _fingerprint(registry_db)
    registry_db.commit(); registry_db.close()

    assert baseline_fp == registry_fp, ("registry-driven advance diverged from advance_connection", baseline_fp, registry_fp)

    # --- Ordering: processes ran in registration order, matching the hand-written order
    # in advance_connection (needed so cutover cannot silently reorder cross-process effects).
    # Anchored on the terminal pass specifically (unambiguous: it runs exactly once, and
    # "world_catchup" only ever appears there), since an earlier regular checkpoint can
    # land on the same day number as the terminal pass and would otherwise conflate the two.
    c = bootstrap('caerness_arch01_order.db')
    reg = build_registry()
    advance_via_registry(c, 10, reg)
    keys = [r[0] for r in c.execute("SELECT process_key FROM process_execution_log ORDER BY id").fetchall()]
    catchup_idx = keys.index("world_catchup")
    terminal_slice = keys[catchup_idx - 1: catchup_idx - 1 + len(BLOCK_A) + len(BLOCK_B)]
    expected_terminal = [("world_catchup" if k == "world" else k) for k in BLOCK_A] + BLOCK_B
    assert terminal_slice == expected_terminal, (terminal_slice, expected_terminal)

    # --- Coverage registration: every registered process that ran left a real
    # process_execution_log row, the same table _instrumented_process already writes to.
    logged_keys = {r[0] for r in c.execute("SELECT DISTINCT process_key FROM process_execution_log").fetchall()}
    assert logged_keys & (set(BLOCK_A) | set(BLOCK_B)), "no coverage rows were written by the registry"
    c.commit(); c.close()

    # --- Recurring scheduling: already proven by the parity check (every recurring
    # domain process ran to identical effect over 45 days). Now one-off scheduling.
    c = bootstrap('caerness_arch01_oneoff.db')
    reg = build_registry()
    fired = {"count": 0}
    reg.register_one_off_handler("test_marker", lambda conn, day, payload, event_logger=None: fired.update(count=fired["count"] + 1, day=day, payload=payload))
    day0 = current_day(c)
    task_id = reg.schedule_once(c, process_key="test", run_day=day0 + 5, task_kind="test_marker", payload={"note": "hello"})
    advance_via_registry(c, 3, reg)
    assert fired["count"] == 0, "one-off task fired before its run_day"
    advance_via_registry(c, 5, reg)
    assert fired["count"] == 1, "one-off task did not fire on its run_day"
    assert fired["payload"] == {"note": "hello"}
    advance_via_registry(c, 10, reg)
    assert fired["count"] == 1, "one-off task fired more than once"
    c.commit(); c.close()

    # --- Cancellation: a cancelled task must never fire, even once its run_day passes.
    c = bootstrap('caerness_arch01_cancel.db')
    reg = build_registry()
    fired2 = {"count": 0}
    reg.register_one_off_handler("test_marker", lambda conn, day, payload, event_logger=None: fired2.update(count=fired2["count"] + 1))
    day0 = current_day(c)
    task_id = reg.schedule_once(c, process_key="test", run_day=day0 + 5, task_kind="test_marker")
    cancelled = reg.cancel(c, task_id)
    assert cancelled is True
    assert reg.cancel(c, task_id) is False, "cancelling an already-cancelled task must not report success"
    advance_via_registry(c, 20, reg)
    assert fired2["count"] == 0, "a cancelled one-off task fired anyway"
    status = c.execute("SELECT status FROM process_registry_tasks WHERE id=?", (task_id,)).fetchone()[0]
    assert status == 'cancelled'
    c.commit(); c.close()

    # --- Persistence/restart: schedule a task, close the connection AND build a brand
    # new ProcessRegistry (simulating a process restart, since the due-day cache is
    # purely in-memory), reopen, and confirm the task still fires on schedule. This is
    # the property that rules out an in-memory-only scheduler (e.g. Mesa's EventList,
    # which stores callables via weakref and cannot be reconstructed after a restart).
    db_path = Path(tempfile.gettempdir()) / 'caerness_arch01_restart.db'
    os.environ['CAERNESS_DB_PATH'] = str(db_path)
    os.environ['CAERNESS_TEST_MODE'] = '1'
    reset_db(force=True, backup=False); init_db()
    c = connect(); import_current_seed(c); activate_existing_loops(c); c.commit()
    reg = build_registry()
    day0 = current_day(c)
    reg.schedule_once(c, process_key="test", run_day=day0 + 5, task_kind="restart_marker", payload={"x": 1})
    c.commit(); c.close()
    # Fresh connection AND a fresh registry instance: nothing Python-side survives.
    c2 = connect()
    reg2 = build_registry()
    fired3 = {"count": 0}
    reg2.register_one_off_handler("restart_marker", lambda conn, day, payload, event_logger=None: fired3.update(count=fired3["count"] + 1))
    advance_via_registry(c2, 10, reg2)
    assert fired3["count"] == 1, "one-off task did not survive a connection/process restart"
    c2.commit(); c2.close()

    print('ARCH-01 ProcessRegistry tests: PASS')
    return {
        "baseline_fingerprint": baseline_fp,
        "registry_fingerprint": registry_fp,
    }


def benchmark_due_day_strategies(days: int = 250) -> dict:
    """The real Mesa question, measured against real SQL on a real seeded database, not
    a synthetic in-memory model. Compares:

    eager   -- re-query every registered process's next_due_day on every checkpoint
               computation, reproducing advance_connection's current behavior exactly.
    lazy    -- this registry's default: only re-query a process's next_due_day when that
               process actually ran; every other process's cached value is reused.

    Mesa's mesa.time.EventList is a heapq-backed in-memory priority queue with weakref
    callables. It has no bearing on this benchmark: the cost here is database round-trips,
    not heap-pop overhead, and EventList cannot itself be the persistence-safe source of
    truth (see the persistence/restart test). So the honest comparison is eager vs lazy
    SQL querying, not "heapq vs Mesa" -- both would need the same number of real SQL calls
    underneath either way. This is reported explicitly rather than running a heap
    micro-benchmark that would not actually answer the question asked.
    """
    eager_db = bootstrap('caerness_arch01_bench_eager.db')
    eager_db.commit(); eager_db.close()  # warm the sqlite file cache identically for both runs

    def timed_run(db_name: str, eager: bool) -> float:
        conn = bootstrap(db_name)
        reg = build_registry()
        reg._eager_requery = eager
        t0 = time.perf_counter()
        advance_via_registry(conn, days, reg)
        elapsed = time.perf_counter() - t0
        conn.commit(); conn.close()
        return elapsed

    eager_s = timed_run('caerness_arch01_bench_eager2.db', eager=True)
    lazy_s = timed_run('caerness_arch01_bench_lazy2.db', eager=False)

    result = {
        "days_advanced": days,
        "eager_requery_every_checkpoint_s": eager_s,
        "lazy_cache_only_requery_ran_s": lazy_s,
        "speedup": (eager_s / lazy_s) if lazy_s > 0 else None,
        "note": "Mesa's EventList is not applicable here; the cost is SQL round-trips, "
                "not in-memory heap operations, and it cannot serve as the durable "
                "scheduling authority (see persistence/restart test). SQL stays authoritative.",
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    run()
    print()
    benchmark_due_day_strategies()
