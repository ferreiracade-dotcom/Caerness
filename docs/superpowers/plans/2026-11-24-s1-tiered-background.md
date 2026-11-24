# S1: Tiered Background Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (this session implements inline). Steps use checkbox syntax.

**Goal:** One-month skips comfortable on the VM with the lived 1975 opening, by running quiet background people's elapsed-based upkeep on a coarser clock, without ever making "noteworthy" depend on distance to the protagonist.

**Architecture:** A new generic module `engine/tiers.py` derives, from live state only (never from distance), which people are *rising* (seat in an organisation, venture party or enterprise owner, race candidate or office holder, person-held debt, recent harm, forced tier). Rising people stay on the daily clock. Everyone else is *quiet*: the daily scans that only integrate elapsed time (careers, household stage and eligibility, planned births, courtship contacts, household money, enterprise status) run for them on a 7-day clock per row (each row's own last-run stamp, so the load spreads). Every such scan already integrates `elapsed` days, so a quiet person loses no outcome, only timing resolution. Anything significant calls `tiers.promote`, which makes the person's rows due the next day.

**Tech Stack:** Python 3.13, SQLite (engine/), pytest-style test scripts under `tests/`.

**Spec:** the task brief (owner decision 2026-11-24: keep everyone, simulate quiet background people more cheaply; noteworthiness never depends on closeness to the protagonist). Measurements: `.superpowers/sdd/2026-11-19-saintjude-org-core/task-S1-report.md`.

## Global Constraints

- No hard caps, floors, clamps, quotas, cooldowns or brakes to hit a number. No world words in `engine/` (no rank titles, outfit names, dollar figures).
- Outcomes keep the baseline distributions. A switch `CAERNESS_TIERS=off` (read in `engine/tiers.py`) restores the all-full-tier baseline for comparison tests.
- Tests clean up their temp files. Use `tools/run_suite.py --quick` only; runs of at most one year, one at a time, never beside the suite. `git restore game/campaign_01/model_requests/` after tests.
- Never write `data/*.db`; leave `data/caerness.pre-schema110.db` and `game/campaign_01/backups/` alone. Commit with `git add <paths>`, "S1" in the subject, never push.

## Review Focus

1. A man far from the protagonist who is made, wins a seat, builds a business or collects support rises at the baseline rate: Task 6 test over seeds 3/7/11, split by distance.
2. A quiet person who suddenly gets a seat, venture, debt, harm or candidacy is on the daily clock the next day: Task 1 test (`test_promote_makes_rows_due_tomorrow`, `test_signals_ignore_distance`).
3. A career whose stage gate opens on an exact day is reviewed that day, not up to a week late: Task 2 test.
4. Weekly batches integrate the same elapsed time as daily ones (days in stage, household money) : Tasks 2 and 4 tests compare daily vs batched totals.
5. The protagonist's own rows follow the same rules (no player-only branch): Task 1 test that the protagonist qualifies by signals only.

---

### Task 1: `engine/tiers.py`

**Files:** Create `engine/tiers.py`, `tests/s1_tiers_test.py`.

**Interfaces:**
- Produces: `enabled(conn) -> bool` (False when env `CAERNESS_TIERS=off`), `BATCH_DAYS = 7`, `rising_actor_ids(conn, day) -> frozenset[int]` (memoised per (db, day) with `world_package.pass_memo`), `is_rising(conn, actor_id, day) -> bool`, `promote(conn, actor_id, day) -> None` (career rows due `day+1`; household and enterprise rows owned by him get `updated_day` untouched but his id is added to a per-day override set so scans treat him as rising).

- [ ] Step 1: test `test_signals_ignore_distance` (a seat holder, a venture party, an enterprise owner, a debtor, a race candidate, a harmed person are rising; a plain employee is not; moving everyone to another location changes nothing) and `test_promote_makes_rows_due_tomorrow`.
- [ ] Step 2: implement the signals as one SQL union over `org_seats(status='active')`, `venture_parties`, `civilian_enterprises(owner_actor_id)`, `race_candidates(dropped_day IS NULL)` joined to open races, `office_terms(end_day IS NULL)`, `agreement_terms` with a person debtor, `simulation_profiles.forced_tier`. Run test, commit "S1.1".

### Task 2: careers on the batch clock

**Files:** Modify `engine/civilian.py` (`review_careers`, `next_civilian_due_day`); Test `tests/s1_careers_test.py`.

**Interfaces:** Consumes `tiers.rising_actor_ids`, `tiers.BATCH_DAYS`. A career's `experience_json` gains `next_review_day`.

- [ ] Step 1: tests `test_batched_totals_equal_daily` (30 days daily vs 7-day batches: identical `days_in_stage`, `days_in_career`), `test_gate_day_reviewed_exactly` (min_days_in_stage gate: promotion on the gate day), `test_rising_career_daily`.
- [ ] Step 2: `review_careers` selects only rows with `COALESCE(json_extract(experience_json,'$.next_review_day'),0)<=day`; after review sets `next_review_day = day + (1 if rising else 7)`, or the exact day the next stage's `min_days_in_stage` is reached when sooner. `next_civilian_due_day` includes `MIN(next_review_day)` of active careers. Run tests, commit "S1.2".

### Task 3: household life scans

**Files:** Modify `engine/household_life.py` (`_review_profiles`, `_resolve_planned_births`, `_resolve_social_contacts`, `next_household_life_due_day`); Test `tests/s1_household_test.py`.

- [ ] Step 1: tests `test_stage_change_on_boundary_day`, `test_births_same_as_baseline_dates` (planned birth happens on its due day), `test_new_contact_scan_weekly`.
- [ ] Step 2: `_review_profiles` selects rows with `last_review_day <= day - 7` or a life-stage boundary crossed (2, 13, 18, 60 years, same constants as the due-day function) or rising actor; `_resolve_planned_births` selects only unions whose plan due day (same SQL expression as `next_household_life_due_day`) is `<= day`; the new-contact scan runs when `day - last scan >= 7` (stamp in `runtime_flags`, exposed to `next_household_life_due_day`). Run tests, commit "S1.3".

### Task 4: household money and enterprise status

**Files:** Modify `engine/civilian.py` (`_resolve_households`, `_resolve_enterprise_status`); Test `tests/s1_money_test.py`.

- [ ] Step 1: tests `test_household_money_batched_equals_daily_within_rounding`, `test_owner_with_signal_stays_daily`.
- [ ] Step 2: both scans filter rows with `updated_day <= day - 7`, or the head/owner is in `tiers.rising_actor_ids`. Commit "S1.4".

### Task 5: measurement tool and numbers

**Files:** `tools/s1_skip_times.py` (exists), `runs/s1/`.

- [ ] 1/7/30/365 day times and growth, before (done: 2.1, 6.7, 19.8, 238 s, +91 MB) and after, seed 3; profile a late month; write report.

### Task 6: rise equivalence over a year

**Files:** Create `tools/s1_rise_counts.py`, `tests/s1_rise_equivalence_test.py` (slow: marked in the slow set).

- [ ] Step 1: `rise_counts(db_start, db_end, protagonist_loc) -> dict` counting: new inductions (seats with `inducted_day` in the year), promotions (seat level up), new enterprises and enterprises whose capital grew by a tenth, new ventures, race filings, office terms started, each split by *near/far* (route hops from the protagonist's location; far = more than one hop or not in his district).
- [ ] Step 2: test runs seeds 3, 7, 11 for one year with `CAERNESS_TIERS=off` then on, one at a time, and asserts each count within `max(3*sqrt(n), 0.25*n)` of baseline and that far-from-protagonist risers are non-zero in both modes. Commit "S1.6".

### Task 7: report

- [ ] Write `task-S1-report.md` with times, growth, thinning verdict; quick suite once at the end; `git restore game/campaign_01/model_requests/`.
