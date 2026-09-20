"""ProcessRegistry — ARCH-01 spike.

Replaces the manually enumerated due-day/execution blocks in engine/simulation.py's
advance_connection with a single registration point per domain process, following the
external-code research master's Vivarium-shaped contract (owner/reads/writes/dependencies/
cadence/events emitted) over a Caerness-owned, SQL-authoritative registry.

Scope of this spike, deliberately: the ~18 recurring "next_X_due_day / process_due_X"
domain process pairs simulation.py already enumerates by hand. Clocks, actor reviews
(simulation_profiles), interactions, and camera succession keep their existing direct call
sites unchanged; they are a different scheduling shape (per-row due dates, not a single
"next due day for this whole domain" function) and folding them in is not needed to prove
this spike's five properties. New capability added here: durable one-off/scheduled tasks
(schedule_once/cancel), which had no existing home anywhere in the engine.

Mesa's mesa.time (EventList/Event/Priority) was inspected as a candidate backend for the
in-memory "what's due next" cache. Its EventList is a heapq-backed priority queue with
weakref callables — appropriate for a live in-process agent scheduler, but the weakref
storage cannot survive a process restart, and Caerness's persistence/restart requirement
is satisfied entirely by SQL, not by whatever sits in front of it. At the current process
count (~18-30, not thousands), a plain dict-and-min() cache is exactly as fast as a heap
and needs no dependency. So this registry does NOT depend on Mesa; see
tests/arch01_process_registry_test.py for the measured comparison this conclusion rests on.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ProcessSpec:
    """One domain process's registration, in the Vivarium-shaped contract.

    next_due_day(conn, after_day, end_day) -> int | None : same signature every existing
        next_X_due_day function already has; reused unchanged.
    run(conn, day, *, event_logger=...) : same signature every existing process_due_X
        function already has; reused unchanged. Called with event_logger only if
        needs_event_logger is True, matching which functions actually accept it today.
    terminal_run : only "world" differs (catch_up_world_processes instead of
        process_due_world_processes) for the terminal catch-up pass; defaults to run.
    """
    key: str
    next_due_day: Callable[[sqlite3.Connection, int, int], int | None]
    run: Callable[..., Any]
    needs_event_logger: bool = True
    terminal_run: Callable[..., Any] | None = None
    terminal_key: str | None = None
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    cadence_hint: str = "checkpoint"


class ProcessRegistry:
    """SQL-authoritative registry. Registration order is execution order (deterministic,
    matching the existing hand-written call order in simulation.py so behavior does not
    shift on cutover). Only re-queries a process's next due day when that process actually
    ran; every other process's cached due day is reused until it fires, instead of the
    current advance_connection re-querying all ~18 processes' next_due_day every checkpoint.
    """

    def __init__(self, *, eager_requery: bool = True) -> None:
        self._specs: dict[str, ProcessSpec] = {}
        self._order: list[str] = []
        self._due_cache: dict[str, int | None] = {}
        self._cache_from_day: int | None = None
        self._one_off_handlers: dict[str, Callable[..., Any]] = {}
        # Cross-domain processes can schedule work for one another.  A lazy due-day cache
        # is therefore not authoritative: a shipment, tournament, event, or travel action
        # can create an earlier due date after another process was cached.  SQL re-query is
        # deliberately the production-safe default.  ``eager_requery=False`` remains only
        # as a benchmark/research mode.
        self._eager_requery = eager_requery

    def register(self, spec: ProcessSpec) -> None:
        if spec.key in self._specs:
            raise ValueError(f"process already registered: {spec.key}")
        self._specs[spec.key] = spec
        self._order.append(spec.key)
        self._due_cache[spec.key] = None

    def registered_keys(self) -> list[str]:
        return list(self._order)

    def _refresh(self, conn: sqlite3.Connection, key: str, after_day: int, end_day: int) -> None:
        spec = self._specs[key]
        self._due_cache[key] = spec.next_due_day(conn, after_day, end_day)

    def _next_one_off_day(self, conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
        row = conn.execute(
            "SELECT MIN(run_day) FROM process_registry_tasks WHERE status='pending' AND run_day>? AND run_day<=?",
            (after_day, end_day),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def next_checkpoint(self, conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
        if self._eager_requery or self._cache_from_day != after_day:
            for key in self._order:
                self._refresh(conn, key, after_day, end_day)
            self._cache_from_day = after_day
        candidates = [d for d in self._due_cache.values() if d is not None]
        one_off = self._next_one_off_day(conn, after_day, end_day)
        if one_off is not None:
            candidates.append(one_off)
        return min(candidates) if candidates else None

    def _invoke(self, conn: sqlite3.Connection, spec: ProcessSpec, day: int, *, event_logger, coverage_run_id: int | None,
                terminal: bool) -> Any:
        fn = (spec.terminal_run or spec.run) if terminal else spec.run
        coverage_key = (spec.terminal_key or spec.key) if terminal else spec.key
        if spec.needs_event_logger:
            result = fn(conn, day, event_logger=event_logger)
        else:
            result = fn(conn, day)
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
            record_process_execution(conn, coverage_key, coverage_run_id=coverage_run_id, due_count=executed,
                                      eligible_count=executed, executed_count=executed, changed_count=executed,
                                      result=result, day=day)
        except Exception:
            pass
        return result

    def run_due(self, conn: sqlite3.Connection, day: int, *, event_logger=None, coverage_run_id: int | None = None,
                terminal: bool = False, only_keys: list[str] | None = None, run_one_off: bool = True) -> dict[str, Any]:
        results: dict[str, Any] = {}
        keys = only_keys if only_keys is not None else self._order
        for key in keys:
            spec = self._specs[key]
            if not terminal and self._eager_requery:
                # Re-evaluate at the checkpoint immediately before this owner runs.  This
                # is load-bearing: an earlier owner in the same checkpoint may have
                # created same-day work for this owner after next_checkpoint() was chosen.
                self._due_cache[key] = spec.next_due_day(conn, day - 1, day)
            due = self._due_cache.get(key)
            if not terminal and (due is None or due > day):
                continue
            results[key] = self._invoke(conn, spec, day, event_logger=event_logger, coverage_run_id=coverage_run_id, terminal=terminal)
            if not terminal:
                # Refresh this owner's future due date after mutation.  In authoritative
                # eager mode every owner will also be refreshed before its next execution.
                self._refresh(conn, key, day, day + 10_000_000)
        if run_one_off:
            results["_one_off"] = self._run_due_one_off(conn, day, event_logger=event_logger)
        return results

    # --- one-off / scheduled tasks -----------------------------------------------------
    def schedule_once(self, conn: sqlite3.Connection, *, process_key: str, run_day: int, task_kind: str,
                       payload: dict[str, Any] | None = None, created_day: int | None = None) -> int:
        if created_day is None:
            created_day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        cur = conn.execute(
            """INSERT INTO process_registry_tasks(process_key,run_day,task_kind,payload_json,status,created_day)
               VALUES (?,?,?,?, 'pending',?)""",
            (process_key, run_day, task_kind, json.dumps(payload or {}, sort_keys=True), created_day),
        )
        return int(cur.lastrowid)

    def cancel(self, conn: sqlite3.Connection, task_id: int) -> bool:
        cur = conn.execute("UPDATE process_registry_tasks SET status='cancelled' WHERE id=? AND status='pending'", (task_id,))
        return cur.rowcount > 0

    def _run_due_one_off(self, conn: sqlite3.Connection, day: int, *, event_logger=None) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM process_registry_tasks WHERE status='pending' AND run_day<=? ORDER BY run_day,id", (day,)
        ).fetchall()
        fired: list[dict[str, Any]] = []
        for row in rows:
            handler = self._one_off_handlers.get(str(row["task_kind"]))
            payload = json.loads(row["payload_json"] or "{}")
            outcome = handler(conn, day, payload, event_logger=event_logger) if handler else None
            conn.execute("UPDATE process_registry_tasks SET status='done' WHERE id=?", (int(row["id"]),))
            fired.append({"id": int(row["id"]), "task_kind": row["task_kind"], "outcome": outcome})
        return fired

    def register_one_off_handler(self, task_kind: str, handler: Callable[..., Any]) -> None:
        self._one_off_handlers[task_kind] = handler
