# PERF-01: Long-Run Speed and Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep Caerness fast and small over a long campaign, so it can live on the phone. The user will not install it until this is fixed.

**Status (2026-10-09):** Tasks 1–4 done plus extras (news fading, audit retention, slim context snapshot,
set-based fading, report-table indexes, exposure prefetch, implied rumour provenance note). Year-3 season ~33–37 s,
3-year save ~96–101 MB (~20 MB/yr and falling). Remaining: batch rumour exposure; drop per-hearer rumour text in
legacy `knowledge`; re-measure; phone benchmark. See AGENTS.md §2.

**Evidence (2026-09-26, PC).**
- At the opening a season takes 13 s. From a day-2,790 save it took 453 s, and the save was 716 MB (about 95 MB per year).
- About 390 MB of the ~455 MB of data is the rumour/knowledge/belief system: one person hearing one rumour writes about nine rows, and nothing is ever forgotten.
- The time went on the same system: belief recomputation (68%) and decision belief envelopes (21%), both from an actor-first query plan. Presence snapshots came third (15%).

**Architecture.**
- Fix query plans where cost grows with history.
- Compute presence once per place and day, from indexed lookups.
- Stop writing duplicate and write-only rows.
- Add a memory-fading process: people forget low-importance, unreinforced rumours. The world's objective history, public narratives and records never fade. This was the user's decision on 2026-09-26: "a".

**Tech stack:** Python 3.12+, sqlite3, the repo's script-style tests, and `tools/bench_sim.py` from POP-01 Phase 0.

## Global Constraints

- **Targets:**

| Measure | Target (PC) |
|---|---|
| Late-run season from the day-2,790 save | ≤ 20 s (leaves room for a phone at about 3× slower to reach about 1 minute) |
| Storage growth | ≤ 15 MB per simulated year at today's population |
| Lookups | Must not slow down as history accumulates |

- Behaviour-preserving changes (query plans, presence) must give identical results. Verify by comparing old and new outputs on the late save.
- The player character never forgets. Personal and important knowledge never fades.
- The late save is `scratchpad/late2790.db` (a consistent copy of the interrupted routed decade). Always benchmark a fresh copy.
- The full regression suite must stay green (`scratchpad/suite/run_suite.py`; tenyear02 runs on a copy of the packaged opening).
- Commit on the `pop01-phase0` branch at each task (the user asked for everything to be committed).

---

### Task 1: Belief lookups from the claim side — DONE

- `engine/belief.py`: `ACTOR_CLAIM_EVIDENCE_SQL` and `ACTOR_CLAIM_EVIDENCE_DETAIL_SQL` use `CROSS JOIN` to pin claim-first order.
- Test: `tests/perf01_belief_query_plan_test.py` (the plan must search `claim_evidence` by claim, then `actor_evidence_access` by actor and evidence).
- Result: late 30 days 86.6 s → 31.5 s; late season 453 s → 103 s; identical belief results on 400 random pairs.

### Task 2: Presence snapshots from indexed lookups, once per place and day

**Files:** `engine/presence.py` (`presence_probability_snapshot`), a new test `tests/perf01_presence_equivalence_test.py`.

- Replace the OR-over-left-joins candidate query with a `UNION` of indexed lookups:
  - habits at this place effective on the day;
  - profiles based here;
  - characters currently here;
  - active or stalled travel plans currently here.

  Then filter to active characters.
- Move the "any character missing a presence profile" check out of the per-call path: run it once per `process_due_transmissions` pass.
- Add any missing indexes: `actor_presence_profiles(base_location_id)`, `actors(current_location_id)` and `travel_plans(subject_kind, status, current_location_id)`, with `CREATE INDEX IF NOT EXISTS` in `schema.sql` and the migration.
- **Test:** on a fresh copy of the late save, the snapshot for every location on the save's current day is identical before and after. Store the old implementation's output as the reference inside the test run by keeping the old function as `_presence_probability_snapshot_reference` in the test file.
- **Acceptance:** presence is under 2 s of the late 30-day profile.

### Task 3: Stop duplicate and write-only rows

**Files:** `engine/belief.py`, `engine/information.py`, a new test `tests/perf01_storage_rows_test.py`.

- **Shared evidence.**
  - `mirror_legacy_knowledge` reuses an existing `claim_evidence` row when claim, evidence kind, source id, location, polarity and reliability are identical. Everyone who hears the same rumour at the same place gets the same evidence, and each hearer's access stays in `actor_evidence_access`.
  - `add_claim_evidence` stays as is for explicit evidence. Add a `find_or_add_claim_evidence` helper.
- **Belief revisions only on real change.** `recompute_actor_belief` writes `belief_revisions` only when a prior belief row existed and its stance or confidence changed. The first acquisition is already recorded by `actor_beliefs.first_received_day`.
- **No write-only links.** `_upsert_knowledge` stops writing the `learned_as` `information_links` row, since `knowledge_provenance` records the same source and nothing reads the link. The `became_rumour` event→rumour links stay, because `tests/information_test.py` reads them.
- **Test:**
  - Twenty actors hear one rumour at one place → exactly one `claim_evidence` row, twenty access rows, twenty beliefs and zero revisions.
  - A later contradicting report → revisions only for actors whose stance changed.
  - `tests/belief01_claims_competence_lens_test.py` still passes.

### Task 4: Memory fading

**Files:** create `engine/memory.py`; modify `engine/simulation.py` (register `ProcessSpec("memory", next_memory_due_day, process_due_memory, needs_event_logger=False)` after `information`) and `engine/db.py` (migration 109: indexes plus the `memory_fading_version` meta key; `SCHEMA_VERSION = 109`). New test: `tests/perf01_memory_fading_test.py`.

**Rule** (on the 30-day grid, deterministic):
- A person's belief in a rumour-sourced claim fades when all of these hold:
  - it is not personal: the person is not the event's source or target, and has no kinship or household link to them;
  - the event's severity is 3 or less;
  - the person is not the player character;
  - it has not been reinforced (`actor_beliefs.updated_day`) for the retention time.
- **Retention time:**
  - severity 1: about 365 days;
  - severity 2: about 540 days;
  - severity 3: about 1,095 days;

  each varied ±30% per person by a stable hash.
- Severity 4–5 events (wars, deaths of the great, a new Sixth) are never forgotten.
- **Fading removes that person's:**
  - `knowledge` row (and its provenance, by cascade);
  - `rumour_exposures` row (so they can hear it again);
  - `actor_evidence_access`, `actor_beliefs` and `belief_revisions` rows for the claim.
- `claim_evidence` rows that no one can access any more are deleted. `information_claims` rows, rumours, events, public narratives and records are never deleted.

**Test:**
- A severity-1 rumour heard by a bystander fades after the retention period and can be heard again.
- The same rumour is kept by the event's target and by the player character.
- A severity-5 event is kept by everyone.
- Evidence rows are garbage-collected only when unreferenced.
- Running the same days in one chunk or many gives identical results (chunk invariance).

### Task 5: Measure, re-profile, suite

- Late benchmark: `python tools/bench_sim.py --db scratchpad/late2790.db --label pc_late2790_perf01`. The target season is ≤ 20 s. If it's missed, re-profile (`scratchpad/prof30.py`) and fix the top hotspot with the same equivalence-test discipline.
- Storage growth: run three years from the packaged opening (`scratchpad/sim/oneyear.py ... 1095`) and report MB per year of the resulting DB after `VACUUM`. The target is ≤ 15 MB per year.
- Full regression suite plus tenyear02 on a copy of the packaged opening.
- Update `benchmarks/results/`, the WORLDHIST evidence note, and the README schema line (109).
- Rebuild the packaged opening through migration 109.
