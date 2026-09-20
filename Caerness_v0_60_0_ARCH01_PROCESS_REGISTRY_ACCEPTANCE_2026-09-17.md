# Caerness Engine v0.60.0 — ARCH-01 Acceptance (ProcessRegistry spike)

## Accepted scope
ARCH-01 per `RESEARCH/CURRENT/Caerness_EXTERNAL_CODE_RESEARCH_MASTER_CURRENT_2026-09-17.md`
sections 2 and 10: "Prove recurring/one-off scheduling, ordering, cancellation,
persistence/restart, and coverage registration." This is a spike, not a cutover:
`engine/simulation.py`'s `advance_connection` is untouched. `engine/process_registry.py`
is new, and `tests/arch01_process_registry_test.py` proves it against a parallel
`advance_via_registry` built from the same due-day/execution logic.

## Engine/schema
- Engine: `0.60.0` (unchanged)
- Schema: `57` (migration 57: `process_registry_tasks`, a durable table for the new
  one-off/scheduled-task capability; recurring domain processes keep their existing
  tables, nothing about them changed)

## What was built
`ProcessSpec` (Vivarium-shaped: key/next_due_day/run/reads/writes/emits/cadence) and
`ProcessRegistry`, registering the real 19 existing `next_X_due_day`/`process_due_X`
pairs `advance_connection` already calls, unchanged. Scope, deliberately: this covers the
19 recurring domain processes that were hand-enumerated twice (main loop + terminal
catch-up) in `simulation.py`. Clocks, actor reviews, interactions, and camera succession
are a different scheduling shape (per-row due dates, not "next due day for this whole
domain") and were left as direct calls in the parallel harness, unchanged, in their
original relative position — including `process_camera_succession`'s original position
between "hollow" and "religion," which the harness preserves exactly rather than folding
into one contiguous registry block.

New capability with no prior home in the engine: durable one-off scheduling
(`schedule_once`/`cancel`), backed by `process_registry_tasks` so a scheduled task
survives a connection close/reopen.

## Results, against the five required properties

**Parity (the load-bearing check).** `advance_via_registry` run against a real
seeded database for 45 days produces byte-identical aggregate state to the real
`advance_connection` run on an identically-seeded database: event count, organization
count and treasury sum, active zone-claim count, enterprise count, deceased-actor count,
household-union count, tournament-event count, and final `current_day` all match exactly.
This is what "the registry is safe to build toward" actually rests on, not just "the
code runs."

**Recurring scheduling.** Proven by the parity result: every one of the 19 recurring
processes ran to identical effect over the full 45-day range.

**One-off scheduling.** A task scheduled 5 days out did not fire at +3 days, fired exactly
once at +5, and did not fire again over 10 further days.

**Cancellation.** A cancelled task never fires even after its `run_day` passes;
cancelling twice correctly reports failure the second time; the row's status persists as
`'cancelled'`, not deleted.

**Ordering.** The terminal catch-up pass (the one unambiguous, single-occurrence anchor,
since `world_catchup` only ever appears there) reproduces the exact hand-written call
order from `simulation.py`, including the block split around `process_camera_succession`.

**Persistence/restart.** A task was scheduled, the connection closed, and a *new* Python
process state simulated (fresh `connect()`, fresh `ProcessRegistry()` instance — nothing
Python-side survives). The task still fired on schedule, because the due-day cache is
explicitly not the authority; SQL is.

**Coverage registration.** Every process the registry ran wrote a real
`process_execution_log` row through the same `record_process_execution` call
`_instrumented_process` already used, not a parallel observability system.

## The Mesa question, answered rather than assumed
Two things were tested, not asserted:

1. **Does an in-memory due-day cache actually help?** Measured against real SQL on a
   real seeded database over 250 simulated days: re-querying all 19 processes' next due
   day on every checkpoint ("eager," matching `advance_connection`'s current behavior)
   and only re-querying the process that just ran ("lazy," this registry's default) came
   out statistically even (lazy was not faster; run-to-run noise exceeded the difference).
   At Caerness's actual process count, 19 SQLite `MIN()` queries per checkpoint are cheap
   enough that the caching layer buys nothing measurable yet. This may change as more
   domain processes are added, but it is not true today, and it did not go untested.
2. **Does Mesa's `mesa.time.EventList` help beyond that?** No, and not because it is
   slow: it is an in-memory, heapq-backed queue with weakref-stored callables, built for
   a live in-process agent scheduler. It cannot be the persistence-safe authority (the
   restart test above specifically rules out anything living only in Python memory), and
   the measured bottleneck here is database round-trips, not heap-pop overhead — a
   domain Mesa's EventList does not touch either way.

**Conclusion: adopt the ProcessRegistry pattern; do not add Mesa as a dependency.**
Its value is the one the plan actually named — a single registration point instead of a
doubled hand-written list, explicit per-process contracts, and a real place for a future
domain owner to declare "notify me when X emits a violence-tagged event" — not raw speed.

## Tests
New: `tests/arch01_process_registry_test.py`. Green, including the parity check against
the real `advance_connection`.

Unaffected (rerun after the schema bump to 57): `v60_underworld_rebuild_test.py`,
`v60_phase2a_test.py`, `v56_test.py`, `smoke_test.py`. All green.

## What this does NOT do
`advance_connection` was not modified and is not proposed to be replaced by this package.
Cutting it over to `ProcessRegistry` internally is a follow-up decision, not bundled into
this spike — the same separation Phase 2A kept between "prove it" and "ship it." Clocks,
actor review, interactions, and camera succession were not brought into the registry;
whether they should be is open, and nothing here forecloses it.

## What comes next
Per the plan's own sequencing: persistent underworld rackets/assets/crews, then the
event-sourcing spike on territorial sovereignty.
