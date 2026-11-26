# Three levels: build plan (steps 1 to 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> In this repository, tasks run in Sonnet linked sessions, one writer per file set, and the lead reviews every diff.

**Goal:** Build steps 1 to 5 of the three-levels design (revised 2026-11-26 after Gemini's review of this plan): the scoring sheet and GM test bench, the data model, slice 2a
(the GM–engine loop) and slice 2b (a minimal living world), ending in the owner's playtest of a fresh Saint Jude save.

**Architecture:** New engine modules sit beside the city layers and read their existing tables. The connector gains
scene ledgers, one news gate, engine answers and turning events. `life_matters` keeps running only for unprotected
people below level 3. One weekly `levels` process carries pressure build-up, offscreen choice, decisions falling due
and delayed effects. Old news feeds go behind a flag first and are deleted only after the playtest.

**Tech Stack:** Python 3.13, SQLite, the MCP connector (`connector/server.py`), package JSON under
`worlds/saintjude/`, script-style tests run by `tools/run_suite.py`.

**Spec:** `docs/superpowers/specs/2026-11-26-three-levels-design.md` (revision 3.1; section 11 overrides earlier
sections) and its contract `docs/superpowers/specs/2026-11-26-three-levels-contract.md`. Every table, column, tool
argument and module function named below is defined in the contract; read it before your task.

## Global Constraints
- No hard caps, ladders or ceilings: a threshold marks a real change of state, never a points ladder.
- No world words in `engine/`: every Saint Jude figure, name or list lives in `worlds/saintjude/*.json`.
- The engine vetoes contradictions only and never hands the GM a menu or a closed list.
- The protagonist lives under the same rules as everyone else; the engine never chooses for him.
- Never write `data/*.db` (only an approved `data/saintjude.db` rebuild). Leave `data/caerness.pre-schema110.db` and
  `game/campaign_01/backups/` alone.
- B1's held fight work is saved whole in `docs/superpowers/plans/b1-held-fight.patch` (done 2026-11-26, owner's yes).
  Don't apply it or edit it: it is the input to the contest work in step 6.
- Implementers never push, stash, reset or switch branches; commit only your own files with `git add <paths>`; run
  `git restore game/campaign_01/model_requests/` after tests.
- Tests: `tools/run_suite.py --quick --only <names>` while working and `--quick` before reporting. Never more than two
  long runs at once and never beside the quick suite. Runs are no longer than one simulated year. Tests remove their
  temp files.
- Each tool result stays small: the GM's context per turn is a cost. A new key in a result needs a reason.
- Never show the machinery: concern lists, scores and engine words go to the GM only as plain-language briefs.

## Review Focus
1. A chat ends mid-scene, a new chat calls `resume`, then `advance`: the refusal must name
   `close_scene(mode="from_stamps")` and that call must unlock it (test in Task 5).
2. A name in `present` or `participants` who isn't actually there: listed as not here, learns nothing, gets no tie
   change (test in Task 4).
3. Undo of scene 1 after scene 2 built on it: only scene 1's rows revert, and scene 2's knowledge and ties stay
   (test in Task 6).
4. A live save at schema 128 to 133 (Dominic's VM save) migrating to 134: resolutions assigned, `life_matters` still
   runs for unprotected people, nothing crashes on rows without the new columns (test in Task 3).
5. A skip while the protagonist is away (prison, travel): nothing arrives by a told path; it surfaces when the carrier
   is next in a scene with him (test in Task 10a).

## Left to the plan for steps 6 to 8 (not built here)
- several group memberships, per-domain group rates and competing risks, and calibration across runs;
- contests, built from B1's held fight work;
- the full offscreen choice (others weighing in, decisions before breaks);
- tie resting points and hysteresis (the `tie_contexts` table is created here; only scene tie entries write to it);
- movers' plans through organisations, with imperfect execution (only one mover acts here, directly);
- promotion by demonstrated significance, careful demotion, and obligations through life changes;
- several different starting saves.

---

## Delivery and cost (owner-approved 2026-11-26; overrides the task steps where they differ)

**Two deployments.**
- **Deploy 1, after Task 14:** Tasks 1 to 13, then Task 14 (the protection lock), then a Task 19-style deploy
  and playtest. This is the GM loop, the news gate and the lock.
- **Deploy 2:** Tasks 15 to 18b (the living world), then Task 19.

**Deferred to Deploy 2, to save cost:**
- `undo_chain` from Task 6 moves into Task 15, where chains first appear. Task 6 builds `undo_scene` only.
- The Task 10b doors for civic news (`civic_tick._tell_player`), crime to paper (`public_attention`) and the
  `information.py` broadcast switch move into Task 15.

**Tests: targeted per task, the full suite at checkpoints.**
- Wherever a step says "run `--quick`", run instead the task's own test plus the existing tests of the modules it
  modifies (`--only a_test,b_test`). The commit names which ones were run.
- The full `--quick` suite runs only at the checkpoints: after Task 6, at Task 13, and before each deployment.

**The GM bench is the costliest test, so it runs small.**
- Each fix round runs S1, S2, S4 and S5, the four situations the playtest failed.
- All eight run only at Task 13 and before each deployment.

**Side by side.**
- Tasks that share no files run as parallel sessions: Task 2b with Task 1; Task 7 with Tasks 4 and 5; Task 16 with
  Task 15.
- Never two writers on the same files.

**Fix rounds go to the session that did the task,** not to a fresh one.

## Phase A: build step 1

### Task 1: Scoring sheet and bench situations

**Files:**
- Create: `docs/playtests/2026-11-25-dominic-2.txt` (copy of
  `C:\Users\NozzE\.claude\uploads\63f5ee28-600c-4604-899a-a5ee025d8f85\aad99367-Saint_Jude_roleplay_with_Dominic.txt`;
  owner lines start with the player's turns)
- Create: `docs/superpowers/specs/2026-11-26-scoring-sheet.md`
- Create: `tests/gm_bench/situations.md`

**Interfaces:**
- Produces: the sheet's check ids (`C1`..`C10` for engine, `G1`..`G9` for GM) used by Task 7's checker and Task 18a's
  scorer; the situation ids `S1`..`S8` used by Task 7's fixtures.

- [ ] **Step 1: Write the scoring sheet.** One row per check in design section 9, plus the two turning-event
  measures from amendment 11. Each row: id, what is measured, how (script or reading), and a "dead world" and
  "frantic world" sign. Script-checkable GM lines are G1 menus (a numbered or lettered list of options to the
  player), G2 questions to the player that aren't about his own choice, G3 out-of-character flags, G4 exposed
  machinery (`concern`, `pressure`, `the engine`, `score`, a tool name in prose), G5 moralizing phrases from the
  transcript's faults.
- [ ] **Step 2: Write 8 situations from the transcript**, each with: transcript line range, the state it needs (who is
  present, what each knows and owes), 4 to 6 player turns quoted or condensed, what a good GM does, the sheet checks it
  exercises. Cover: S1 a lie to his mother about money, S2 a walkout from a dinner, S3 a quiet evening that should stay
  ordinary, S4 a moralizing trap (a fence offers stolen parts), S5 an ambiguous detail the record doesn't hold (does
  the supplier have a wife?), S6 a one-off customer (the Gerald Orsini case: no advance news), S7 returning after two
  weeks away, S8 a stranger at a bar who should stay a stranger.
- [ ] **Step 3: Commit**
```bash
git add docs/playtests/2026-11-25-dominic-2.txt docs/superpowers/specs/2026-11-26-scoring-sheet.md tests/gm_bench/situations.md
git commit -m "Three levels step 1: scoring sheet and eight bench situations from the second Dominic playtest"
```
- [ ] **Step 4: Lead checkpoint.** The lead reads the sheet and the situations before Phase B starts.

---

## Phase B: build step 2 (data model)

### Task 2: Contract sign-off and clearing B1's held edits (lead)
- [ ] The contract (`docs/superpowers/specs/2026-11-26-three-levels-contract.md`) is written with this plan. The lead
  confirms it against the design before Task 3. Any change goes into the contract first, then into the tasks below.
- [x] B1's held fight edits are saved as `docs/superpowers/plans/b1-held-fight.patch` (checked to apply cleanly to
  a clean copy, commit `f7f5a81`), and those files are restored.

### Task 2b: Switch off the competing paths (before any new table)

Approved by the owner on 2026-11-26 from `docs/review/three-levels-adjacent-verdicts.md`. These are small, local
switches, so the build is measured against a world where only the outfit choices still run.

**Files:**
- Modify: `engine/decision_runtime.py` (`_builtin_candidates` adds the built-in personal providers only when the
  package's `systems.personal_choices` is true; registered providers such as `org`, and "hold position", always run)
- Modify: `engine/decisions.py` (`decide_actor` skips `build_actor_context` when only registered providers run)
- Modify: `engine/information.py` (`_upsert_knowledge` calls `belief.mirror_legacy_knowledge` only when
  `systems.belief_mirror` is true)
- Modify: `engine/world_package.py` (`SYSTEM_KEYS` gains `personal_choices`, `belief_mirror`, `entity_resolution`
  and `rumour_broadcast`, used here and in Tasks 3 and 10b; `worlds/caerness/world.json` sets all four true, Saint
  Jude's leaves them out)
- Modify: `engine/org_happenings.py` (the protagonist draws only the happening kinds the package marks
  `"befalls": true`; every other kind is something a man does, and the engine never does it for him)
- Modify: `worlds/saintjude/outfits.json` (mark `busted` and `incident` as `"befalls": true`)
- Modify: `docs/superpowers/specs/2026-11-26-three-levels-contract.md` and the design's section 8 (already done with
  this plan change)
- Test: `tests/competing_paths_off_test.py`

- [ ] **Step 1: Write the failing test:**
```python
# Saint Jude fixture, 120 days
assert decisions_by_type(conn).get("consolidate", 0) == 0 and decisions_by_type(conn).get("initiate_interaction", 0) == 0
assert decisions_by_type(conn).get("org_action", 0) > 0                     # the outfits still choose
assert count(conn, "actor_beliefs") == 0 and count(conn, "knowledge") > 0
# the protagonist seated as an associate for 52 weeks
seat_protagonist_as_associate(conn); run_weeks(conn, 52)
assert happening_kinds_of(conn, me) <= {"busted", "incident"}
# Caerness keeps both switches on (its tests are unchanged)
assert caerness_package().systems["personal_choices"] and caerness_package().systems["belief_mirror"]
```
- [ ] **Step 2: Run it.** Expected: FAIL (209 consolidate decisions in the reference run).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run it**, then `--quick`, and `--only s1_rise_equivalence_test,org_happenings_test,outfit_choices_test`.
  Outfit actions, money and incidents stay inside the S1 ranges; if a range moves, say why in the commit.
- [ ] **Step 5: Commit** the files above.
- [ ] Optional tidying, same task, own commit: a `caerness_economy` switch for the Caerness-only processes
  (agriculture, logistics, merchant, craft, growth, war, ecology, education, patronage, seeking, attention,
  psychology, world). They run on empty tables in Saint Jude, so nothing should change but the run time.
- Not done here: `org_lifecycle._dormant` still puts a former member back on the full review. With the personal
  choices off he can only hold position, so it is harmless; Task 3's `levels` owns his cadence after that.

### Task 3: Schema 134 and resolution levels

**Files:**
- Modify: `engine/schema.sql` (new tables and columns from the contract; append a `-- schema 134` block)
- Modify: `engine/db.py` (`SCHEMA_VERSION = 134`; migration adds columns with `ALTER TABLE ... ADD COLUMN` guarded by
  a column check, as the existing migrations do)
- Create: `engine/levels.py`
- Create: `engine/rollback.py` (only `current`, the three `log_*` functions and the table-to-key map here; Task 6 adds undo)
- Create: `worlds/saintjude/levels.json` (every key in the contract's package section, with first figures)
- Modify: `engine/world_package.py` (load and validate `levels.json`: report missing keys, unknown role references and
  a wrong `version`, telling a missing setting apart from one deliberately left out with `null`)
- Modify: `engine/simulation.py` (`SYSTEM_PROCESSES`: the `resolution` process runs only when the package's
  `systems.entity_resolution` is true; Saint Jude leaves it out)
- Modify: `engine/resolution_controller.py` (`_materialize_latent_person` and `_sync_sim_tier`: when
  `entity_resolution` is off, a new person gets `sim_resolution='materialized_minor'` and a `simulation_profiles`
  row on the quiet routine, never one that feeds the old decision loop)
- Modify: `engine/tiers.py` (`_compute` keeps everyone at `sim_resolution='active'` on the daily clock)
- Test: `tests/levels_schema_test.py`

**Interfaces:**
- `levels` owns tiers, cadence and promotion in Saint Jude. `resolution_controller` used to re-score all 5,879 people
  there on its own scale; it no longer runs there. Materializing unnamed people (marriages into the unnamed
  population, a grown child nobody knew about) stays.
- Produces: `levels.refresh(conn, day) -> {"active": int, "notable": int, "changed": int}` and
  `levels.resolution_of(conn, actor_id) -> str`.
- Rules for `refresh`: `active` = the protagonist; anyone whose `closeness_to_me` meets `close_rule` (computed from his
  relationship row with the protagonist: affection, trust, familiarity, and kin or household); anyone in a
  `mover_roles` seat (`systemic_power` from the seat). `notable` = holders of any organisation seat or office and owners
  of an enterprise with staff, not already active. Everyone else with a row stays `materialized_minor`. `refresh`
  never lowers anyone below `notable` while he has a live obligation or a live concern (step 8 does careful demotion).

- [ ] **Step 1: Write the failing test** `tests/levels_schema_test.py` with checks:
```python
# fresh opening (tests.sj_fixture.build_saintjude) plus an authored protagonist "Dominic Basile", mechanic, 24
assert schema_version(conn) == 134
assert {"gm_scenes", "scene_stamps", "scene_participants", "causal_chains", "record_standing", "actor_pressures",
        "actor_concerns", "actor_decisions", "exposure_links", "channel_shocks", "scheduled_effects",
        "actor_routines", "routine_exceptions", "engine_answers", "tie_contexts", "record_changes",
        "pending_news", "offscreen_evaluations"} <= tables(conn)
with rollback.current(conn, scene_id=1):
    rid = insert_concern(conn); rollback.log_insert(conn, "actor_concerns", rid)
assert logged(conn, "actor_concerns", rid)["source_scene_id"] == 1
assert {"basis", "path_kind", "carrier_actor_id", "holds_true", "topic", "source_scene_id", "causal_chain_id"} <= cols(conn, "knowledge")
out = levels.refresh(conn, day)
assert levels.resolution_of(conn, me) == "active"
assert all(levels.resolution_of(conn, k) == "active" for k in kin_of(conn, me))
print(out, active_by_reason(conn))                     # the lead sets the band from this first run
assert 10 <= out["active"] <= 120 and out["notable"] > 0
# a captain-level seat holder from mover_roles is active even with no tie to him
assert levels.resolution_of(conn, a_mover) == "active"
# Review Focus 4, real legacy dirt: LEVELS_LEGACY_DB names a copy of a real pre-134 campaign save (the lead copies
# the VM backup to runs/, never data/). The check is skipped, and says so, when the variable is unset.
if os.environ.get("LEVELS_LEGACY_DB"):
    old = migrate_copy(os.environ["LEVELS_LEGACY_DB"])
    assert schema_version(old) == 134 and levels.resolution_of(old, protagonist_of(old)) == "active"
    assert legacy_knowledge_rows_have_null_path(old)
# package validation: a levels.json missing "pressures" reports it; "pressures": null is accepted as left out
assert "resolution" not in run_process_keys(conn)                            # the old ladder is off in Saint Jude
spouse = materialize_unnamed_spouse(conn, single_adult)
assert levels.resolution_of(conn, spouse) == "materialized_minor" and quiet_routine_of(conn, spouse) == 1
assert active_on_daily_clock(conn)                                         # tiers.py keeps level 3 daily
```
- [ ] **Step 2: Run it.** `python tools/run_suite.py --out runs/t3 --quick --only levels_schema_test`. Expected: FAIL
  (schema version 133).
- [ ] **Step 3: Implement** the schema block, the migration, `levels.py`, `levels.json` and its validation.
  `refresh` runs once at the end of the opening build and on protagonist creation.
- [ ] **Step 4: Run it**, then `--quick`. Expected: the new test passes; no test that passed before now fails.
- [ ] **Step 5: Commit** `engine/schema.sql engine/db.py engine/levels.py engine/rollback.py engine/world_package.py
  worlds/saintjude/levels.json tests/levels_schema_test.py`.

### Task 3b: Routines on demand

**Files:**
- Create: `engine/routines.py`
- Modify: `engine/levels.py` (`refresh` calls `routines.seed` for anyone newly notable or active)
- Modify: `tools/build_opening.py` (seed routines at the end of the opening build)
- Modify: `worlds/saintjude/levels.json` (`schedules`)
- Test: `tests/routines_test.py`

**Interfaces:**
- Produces:
  - `seed(conn, actor_ids=None) -> int`: home from the household, work from the employer or the business he owns,
    schedule from his position;
  - `where(conn, actor_id, day, part) -> int | None`, where `part` is one of `morning`, `day`, `evening` or `night`:
    an exception first, then the schedule. `where` writes nothing. Exceptions include what other systems already
    record: active `custody` of kind `held`, an open `inmate_stays` row, a `sentences` row being served, and
    `travel_plans` that are active or stalled (the check `presence._active_travel` makes today).

- [ ] **Step 1: Write the failing test:**
```python
assert routines.seed(conn) > 0 and seeded_share_of_notable_and_active(conn) > 0.9
assert routines.where(conn, frank, weekday, "day") == garage_location
add_exception(conn, frank, "ill", day, day + 5); assert routines.where(conn, frank, day + 1, "day") == frank_home
assert routines.where(conn, unseeded_minor, day, "day") is None              # unknown, not somewhere
hold_in_custody(conn, frank, day); assert routines.where(conn, frank, day, "day") == custody_location(conn, frank)
start_travel(conn, frank, day + 10); assert routines.where(conn, frank, day + 11, "day") != garage_location
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 4: Scene ledger in the engine

**Files:**
- Create: `engine/scenes.py`
- Modify: `engine/relationships.py` (accept `source_scene_id`/`causal_chain_id` in `record_relationship_effect` and
  write them to `relationship_history`)
- Test: `tests/scene_ledger_test.py`

**Interfaces:**
- Consumes:
  - `company.in_earshot`, `company.join` and `veto.settlement_of` (as `connector/store.py _scene_note` uses them);
  - `routines.where` (Task 3b) to judge who can plausibly be present;
  - `rollback.current` and `rollback.log_*` (Task 3) for every write.
- People are given by name or id and resolved as the contract says: the scene's people first, then the
  protagonist's known people. An ambiguous name is refused with the candidates. Tie changes arrive as steps
  (`-small` and so on) and are mapped through `tie_steps`. Thread kinds are `owed`, `meeting` and `promise`, with
  their direction.
- `open_scene(conn, call_id, present, text, location=None)`: compared with the open scene's `location_id`. A different place is refused, naming `close_scene`.
- Produces:
  - `open_scene(conn, call_id, present: list, text: str) -> dict` (returns `{"scene_id", "present", "not_here"}`;
    reuses the open scene if there is one);
  - `open_scene_id(conn) -> int | None`;
  - `stamp(conn, call_id, kind, text, *, actor_id=None, target_actor_id=None, holds_true=None, ref_table=None, ref_id=None) -> dict`
    (returns `{"beat", "kind", "text"}`; refuses when no scene is open);
  - `ledger(conn, scene_id) -> list[dict]`;
  - `close(conn, call_id, mode, participants=None, amendments=None, exceptions=None, ties=None, threads=None) -> dict`
    returning `{"closed": scene_id, "learned": int, "ties": [..], "threads": [..], "refused": [..]}`.
- What `close` writes:
  - **knowledge:** for each stamp of kind claim, lie, promise, money, goods, injury, walkout or decision, a knowledge
    row for every participant present at that beat with attention `involved` or `attentive` (`overheard` at
    confidence 0.5; `distracted` none), unless an exception removes them. Each row gets `basis` saw or told,
    `path_kind` self, `holds_true` from the stamp, `topic` from the stamp kind, and `source_scene_id`.
  - **ties:** every participant pair that includes the protagonist gets a familiarity step through
    `record_relationship_effect`, smaller for each extra scene the pair shared in the last 14 days (the step shrinks to
    half each time; the figure comes from `levels.json`). `ties` entries apply as given, with `cause` as the summary.
  - **threads:** shaped as the contract says.
    - `owed` and `promise` become one obligation of `by` toward `to`: `actor_id` = `by`, `counterparty_actor_id` = `to`.
    - `meeting` becomes one obligation row per person in `with`.
    - Each row has `due_day` = today + `due_in_days`, `source_kind` 'scene' and `source_scene_id`.
  - **exceptions:** `missed_by` gets no row for that beat. `disbelieved_by` gets a row at confidence 0.1 (he heard it
    said). `secret` defaults to `holds_true=1` and gives rows only to `known_to`.
  - **news:** any `pending_news` whose carrier was a participant is delivered here (`news_gate.deliver`, which copies
    the chain id onto his knowledge row).
  - **stamps that start something:** a `promise` stamp also becomes an obligation. A `decision` stamp with an
    `actor_id` becomes a pending `actor_decisions` row (the reason is the stamp text). A tie entry that moves
    resentment or affection by at least the `levels.json` concern line opens a `resents` or `wants` concern for the
    `from` person, with `origin_kind='scene'` and the cause as `origin_text`.
  - **contexts:** a tie entry with `"context"` (work, personal, business or family) writes `tie_contexts` as well as
    the overall row.
  - **refusals are all or nothing:** if any reference fails (an ambiguous or unknown name, a beat that doesn't exist,
    a participant who wasn't there), `close` commits nothing and leaves the scene open. It returns `refused`, with
    the candidates for each failure.
  - **close mode:** `from_stamps` does the same with no fields; `review` writes nothing and returns the ledger.

- [ ] **Step 1: Write the failing test** `tests/scene_ledger_test.py`:
```python
sid = scenes.open_scene(conn, "c1", [mother, frank], "kitchen, evening")["scene_id"]
scenes.stamp(conn, "c2", "lie", "Dominic says he has $500 saved", actor_id=me, holds_true=0)
scenes.stamp(conn, "c3", "promise", "Frank will repay by Friday", actor_id=frank, target_actor_id=me)
out = scenes.close(conn, "c4", "commit", participants=[{"who": "Frank", "joined_after_beat": 1}],
                   ties=[{"from": "Ma", "to": "me", "change": {"trust": "+small"}, "cause": "he helped with the rent"}],
                   threads=[{"kind": "owed", "by": "Frank", "to": "me", "text": "repay by Friday", "due_in_days": 4}])
assert knows(conn, mother, sid, beat=1) and not knows(conn, frank, sid, beat=1)   # Frank came in after the lie
assert belief_holds_true(conn, mother, sid, beat=1) == 0                          # she believes a lie
assert obligation(conn, frank, me)["source_scene_id"] == sid
assert familiarity_after_second_scene_gain < familiarity_after_first_scene_gain   # repeated company counts less
assert scenes.open_scene_id(conn) is None
# Review Focus 2: a stranger named in present who is in another town
r = scenes.open_scene(conn, "c5", [stranger_elsewhere], "bar")
assert stranger_elsewhere in r["not_here"]
scenes.close(conn, "c6", "from_stamps")
assert not knows_anything_from(conn, stranger_elsewhere, r["scene_id"])
# a new place while a scene is open is refused, not merged
scenes.open_scene(conn, "c7", ["Frank Moretti"], "garage")
assert "close_scene" in scenes.open_scene(conn, "c8", ["Ma"], "kitchen", location="Basile house")["refused"]
# a quiet scene with no stamps closes cleanly
assert scenes.close(conn, "c9", "commit")["closed"]
# names: a unique first name resolves; a shared one is refused with candidates
bad = scenes.close(conn, ..., ties=[{"from": "Tony", "to": "me", "change": {"trust": "+small"}, "cause": "x"}])
assert bad["refused"][0]["candidates"] and scenes.open_scene_id(conn) is not None and not bad.get("closed")
assert scenes.close(conn, ..., ties=[{"from": "Tony Rizzo", ...}])["closed"]    # the retry goes through
# a meeting with two people writes two obligations; disbelief still records that it was said
assert len(obligations_from_scene(conn, sid_meeting)) == 2
assert knowledge_of(conn, ma, sid, beat=1)["confidence"] == 0.1                 # disbelieved_by=["Ma"]
# two scenes in a row: the second familiarity step is smaller, and the first scene's people aren't in the second
assert step2 < step1 and not participant(conn, scene2, frank)
# owed thread direction: Frank owes me, not the reverse
assert obligation_from(conn, frank, to=me)
```
- [ ] **Step 2: Run it.** Expected: FAIL (no module `engine.scenes`).
- [ ] **Step 3: Implement** `engine/scenes.py` and the `relationships.py` change.
- [ ] **Step 4: Run it, then `--quick`.** Expected: PASS, no new failures.
- [ ] **Step 5: Commit** `engine/scenes.py engine/relationships.py tests/scene_ledger_test.py`.

### Task 5: Scene ledger in the connector

**Files:**
- Modify: `connector/store.py` (`_scene_note` calls `scenes.open_scene` and keeps writing `last_scene`; new
  `kind="stamp"` in `NOTE_TYPES`, read from the new `stamp` parameter)
- Modify: `connector/server.py`:
  - a new `close_scene` tool, registered in `register_tools`;
  - `stamp: dict | None` and `location: str | int | None` parameters on `note`;
  - `rationale` on `act`, `money` and `author`;
  - auto-stamping after a successful `act`, `money` or `author` while a scene is open;
  - `changed` (only what this call changed) on results during an open scene.
- Create: `connector/scene_close.py` (the tool body, run under `store.run_once`)
- Modify: `connector/timeflow.py` (refuse while a scene is open)
- Modify: `connector/session.py` (resume shows the open scene and its ledger)
- Test: `tests/connector_scene_ledger_test.py`

**Interfaces:**
- Consumes: Task 4's `engine/scenes.py`.
- Produces: the `close_scene` tool exactly as in the contract; the stamp mapping: `money` op pay or set_cash goes to
  `money` (with `ref_table` money_records), op owe to `promise`; `act` attack goes to `injury` when harm resulted, pay
  or lend to `money`, other acts to `other`; `author` person goes to `enter`.

- [ ] **Step 1: Write the failing test** (connector functions called directly, as in
  `tests/saintjude_connector_play_test.py`):
```python
server.note("n1", "the garage, morning", kind="scene", present=["Frank Moretti"])
paid = server.money("m1", "pay", {"to": "Frank Moretti", "amount": 40, "what": "parts"}, rationale=None)
assert paid["stamp"]["kind"] == "money"
assert server.advance("a1", 7, "work", from_day=day)["status"] == "refused"
assert "close_scene" in server.advance("a1b", 7, "work", from_day=day)["reason"]
# Review Focus 1: a new chat resumes mid-scene
r = server.resume_current()
assert r["open_scene"]["ledger"][0]["kind"] == "money"
assert server.close_scene("cs1", mode="from_stamps")["closed"]
assert server.advance("a2", 7, "work", from_day=day)["day_ended"] > day
# replay: the same call_id returns the same result and closes nothing twice
assert server.close_scene("cs1", mode="from_stamps").get("replayed")
# review mode commits nothing
server.note("n2", "the club", kind="scene", present=["Frank Moretti"])
server.close_scene("cs2", mode="review"); assert scenes.open_scene_id(conn) is not None
st = server.note("st1", "Frank swears the car was fine", kind="stamp", stamp={"kind": "lie", "by": "Frank", "true": False})
assert st["stamp"]["kind"] == "lie" and "changed" in st
```
- [ ] **Step 2: Run it.** Expected: FAIL (no `close_scene`).
- [ ] **Step 3: Implement.** The `close_scene` docstring follows the house style: one paragraph naming the modes and
  the five field shapes.
- [ ] **Step 4: Run it, then `--quick`** (the connector tests must still pass: `connector_*`,
  `saintjude_connector_play_test`).
- [ ] **Step 5: Commit** the five files and the test.

### Task 6: Cascading undo

**Files:**
- Modify: `engine/rollback.py` (add `undo_scene`; keep Task 3's `current`, `log_*` and the key map. `undo_chain`
  is deferred to Task 15; see Delivery and cost)
- Modify: `connector/correct.py` (ops `undo_scene` and `undo_chain`; `preview` shows what each would revert)
- Modify: `engine/commitments.py` (`record` and `complete` log through `rollback.log_insert` and `log_update`)
- Test: `tests/rollback_cascade_test.py` (also: a commitment recorded in a scene is gone after `undo_scene`)

**Interfaces:**
- Produces:
  - `undo_scene(conn, scene_id) -> {"reverted": {table: count}, "left": [...]}` and `undo_chain(conn, chain_id) -> {...}`;
  - the `record_changes` log, replayed backwards: inserts deleted, `add` deltas subtracted, and updates restored
    from `before_json` only where no later change touches the row (otherwise the row is listed in `left`). This
    covers pressures, overwritten standing, and obligations or concerns a scene resolved;
  - ties: the inverse of each `relationship_history.effect_json` keyed by the id, on `relationships`, and on
    `tie_contexts` where `context` is set;
  - money: a reversing record for each money stamp's `ref_id`, never a deletion;
  - authored rows: marked reverted when nothing later refers to them, otherwise listed in `left`;
  - pending scheduled effects cancelled; the scene's status becomes `abandoned`; chains started inside the scene are
    undone too.

- [ ] **Step 1: Write the failing test:**
```python
s1 = close a scene where Frank promises repayment and the mother hears a lie
s2 = close a later scene where Frank and Dominic quarrel (trust -10)
rollback.undo_scene(conn, s1)
assert no_rows_with(conn, "source_scene_id", s1)
assert trust(frank, me) == trust_after_s2_minus_s1_effects       # s2's -10 stays
assert knows(conn, frank, s2, beat=1)                              # Review Focus 3
assert server.correct("u1", "undo_scene", "", {"scene": s1})["error"]   # player_said is required
# a scene with several effects comes back whole
s3 = scene where Dominic pays Frank $100, Ma's family trust drops ("-medium", context family), the bar owner is
     confirmed as Palumbo (overwriting an earlier confirmed value), Frank's open debt is marked fulfilled, and a GM
     turning event closes the bakery
snap = state_of(conn, ["money_records totals", "relationships", "tie_contexts", "record_standing", "obligations",
                       "actor_pressures", "routine_exceptions", "channel_shocks", "scheduled_effects"])
rollback.undo_scene(conn, s3)
assert state_of(conn, ...) == snap_before_s3 and cash(me) == cash_before_s3     # money reversed by record
assert standing_of(conn, "business", bar, "owner")["value"] == earlier_value      # restored, not unknown
assert obligation(conn, frank_debt)["status"] == "active"                        # un-resolved
# out of order: scene 1 raised a pressure by 2, scene 2 by 3 and then re-set the bar owner; undo scene 1 only
result = rollback.undo_scene(conn, s_first)
assert pressure_level(conn, x) == base + 3                                       # the later rise survives
assert owner_row_in(result["left"])                                              # later overwrite kept, reported
assert not record_changes_rows_for(conn, "relationships")                        # ties never double-logged
assert record_changes_count_after_weekly_tick(conn) == before_tick               # silent outside a context
```
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run it, then `--quick`.**
- [ ] **Step 5: Commit** `engine/rollback.py connector/correct.py tests/rollback_cascade_test.py`.

### Task 7: GM test bench harness

**Files:**
- Create: `tools/gm_bench/run.py`, `tools/gm_bench/check.py`, `tools/gm_bench/fixtures/S1.json` .. `S8.json`
- Test: `tests/gm_bench_check_test.py` (the checker only; the bench itself is never part of the suite)

**Interfaces:**
- Consumes: Task 1's situations and sheet ids; Task 5's tools.
- Produces:
  - `run.py --situation S1 [--model sonnet] --out runs/gm_bench/<date>`: builds the fixture save in a temp campaign
    dir (opening from `tests.sj_fixture`, then `author` and `money` and `note` calls from the fixture's `setup`
    list). It then plays the fixture's player turns through Claude Code headless
    (`claude -p --mcp-config <temp config pointing at the stdio connector> --output-format stream-json`, continuing
    with `--resume <session id>` for each later turn) and saves the prose and tool calls per turn as JSONL.
  - `check.py <run dir> -> {"S1": {"G1": [...hits], ...}}`: G1 to G5 by pattern, plus ledger checks (every scene
    closed, no tool error left unanswered).
  - Fixture shape: `{"id", "setup": [{"tool", "args"}], "turns": ["player text", ...], "expect": ["G2", ...],
    "post": [{"sql": "...", "equals": ...}]}`. `post` holds record checks run on the save afterwards, so the bench
    sees whether the GM recorded the right world. For example:
    - S1: his mother holds a `holds_true=0` belief about the $500, and his cash is unchanged;
    - S2: the person who walked out knows no beat after the walkout;
    - S5: the supplier's spouse is either unknown or confirmed by a record, never asserted in prose with no record.

- [ ] **Step 1: Write the failing test** for `check.py` on three canned transcripts in the test file: one with a
  numbered menu (G1 hit), one asking the player what the bartender's name is (G2 hit), one clean (no hits).
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement** `check.py`, then `run.py` and the eight fixtures.
- [ ] Cost: fix rounds run S1, S2, S4 and S5 only (see Delivery and cost).
- [ ] **Step 4: Run the test, then run the bench once on S3** to confirm it works end to end:
  `python tools/gm_bench/run.py --situation S3 --out runs/gm_bench/smoke`. Expected: a JSONL with one entry per turn.
- [ ] **Step 5: Commit** the harness, fixtures and test. The lead reads the S3 run.

---

## Phase C: build step 3 (slice 2a, the GM–engine loop)

### Task 8: The three engine answers and `rationale`

**Files:**
- Create: `engine/answers.py`
- Modify: `connector/acting.py`, `connector/money.py`, `connector/authoring.py` (call `answers.judge` after a
  successful change; add `answers` to the result; store each in `engine_answers`)
- Modify: `worlds/saintjude/levels.json` (`answers` block)
- Test: `tests/engine_answers_test.py`

**Interfaces:**
- Produces: `judge(conn, tool, actor_id, change, rationale) -> list[{"kind": "character"|"consequence", "text": str}]`.
- A character note fires when the act runs against his temperament (`actor_drives`: an aggressive act by a man with
  low aggression and no grievance; generosity against his means) or against a close tie (a hostile act toward someone
  he holds in high affection). It is phrased as a fact about him ("Frank has never raised a hand to his brother").
- A consequence note fires when the act is weighty: money above the `answers` share of his cash, violence, an act
  against an outfit's man or territory, or breaking a live obligation.
- With a `rationale`, the note is still recorded but the text acknowledges the stated reason, and no second call is
  needed. Notes never block.

- [ ] **Step 1: Write the failing test:**
```python
out = server.act("x1", "attack", "Frank hits his brother", target_actor_id=brother, details={"actor": frank})
assert out["answers"][0]["kind"] == "character" and "never" not in out.get("reason", "")   # not a refusal
assert stored_answers(conn, "x1")
out2 = server.money("x2", "pay", {"to": "Tullio Bruni", "amount": cash_of(me) * 0.8, "what": "a debt"})
assert any(a["kind"] == "consequence" for a in out2["answers"])
quiet = server.money("x3", "pay", {"to": "Frank Moretti", "amount": 5, "what": "coffee"})
assert "answers" not in quiet                                                          # ordinary stays ordinary
```
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run it, then `--quick`.**
- [ ] **Step 5: Commit.**

### Task 9: Canon by kind and record standing

**Files:**
- Create: `engine/standing.py`
- Modify: `connector/store.py` (`kind="detail"` with `field` set writes `standing.confirm`; a claim note gives
  knowledge to everyone present in the open scene; both carry the open scene id)
- Modify: `connector/views.py` (`lookup` returns `on_record` as `{attribute: {"standing", "value"}}` and says
  `not on record (unknown)` when asked about an attribute with no row)
- Test: `tests/canon_standing_test.py`

**Interfaces:**
- Produces: `confirm(conn, kind, id, attribute, *, holds: bool, value=None, scene_id=None, chain_id=None)`,
  `infer(conn, kind, id, attribute, value)`, `standing_of(conn, kind, id, attribute) -> dict | None`.

- [ ] **Step 1: Write the failing test:**
```python
server.note("d1", "Palumbo owns the bar on Carlisle", kind="detail", subject_kind="business", subject_id=bar, field="owner")
assert standing.standing_of(conn, "business", bar, "owner")["standing"] == "confirmed"
server.note("d2", "no wife", kind="detail", subject_kind="actor", subject_id=supplier, field="spouse")  # checked: none
assert standing.standing_of(conn, "actor", supplier, "spouse")["holds"] == 0
assert standing.standing_of(conn, "actor", other_supplier, "spouse") is None           # unknown, not "no wife"
assert "unknown" in dump(server.lookup("Other Supplier spouse"))
# a claim made in a scene reaches those present, as the speaker's statement
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 10a: One news gate

**Files:**
- Create: `engine/news_gate.py`
- Modify: `connector/timeflow.py` (when `engine_meta.news_gate='1'`, `news` replaces `noticed`, the hearsay
  `material` keys and texture's news items; `money`, `chances`, `waiting_on_you`, `history_due`, `settled` stay)
- Modify: `engine/texture.py` (`circle` stops counting customers with open deals or work matters as near)
- Modify: `engine/hearsay.py` (knowledge it delivers gets `path_kind='told'` and `carrier_actor_id`)
- Modify: `engine/levels.py` (new saves set `news_gate='1'`)
- Modify: `worlds/saintjude/levels.json` (`news_paths`: which everyday channels he has by default and what each carries)
- Test: `tests/news_gate_test.py`

**Interfaces:**
- Produces:
  - `reaches(conn, me, start_day, end_day) -> list[{"text", "path", "via", "firsthand", "why", "floor"}]`;
  - `held_for(conn, me, carrier) -> list[...]` (what a carrier holds for him, shown in the scene brief when the carrier
    is present).
- An item passes only with a **path** (knowledge row with `path_kind`, or a public event of high enough severity on an
  everyday channel he has) **and relevance** (kin, a friend, his money, his business, danger to him or his, or an
  interest on his sheet). Attention only ranks within the read budget. Floor items (danger, an active obligation,
  close kin) are never dropped.
- During a skip (amendment 6), news someone has to tell him goes to `pending_news`. It reaches him three ways:
  - **in town, urgent:** an item of an `urgent_kinds` kind (illness, danger, an urgent demand) from close kin or a
    close tie arrives by phone or visit and is delivered during the skip;
  - **in town, not urgent:** delivered only when the carrier was actually with him, meaning the same household or the
    same place by `routines.where`. Otherwise it waits;
  - **unreachable:** while a `routine_exceptions` row of kind prison, travel or away covers him, only mail and what
    he saw arrive (and paper and radio where he is). Everything else waits.

  What waits comes back through `held_for` when the carrier is in a scene with him. It is then delivered once
  (`delivered_scene_id`) and never offered again. A false item stays false as it travels (`holds_true` is copied).

- [ ] **Step 1: Write the failing test:**
```python
# Gerald case: a one-off customer's good fortune never reaches him in advance
make_customer_with_open_deal(conn, gerald); give_windfall(conn, gerald)
assert not any("Gerald" in n["text"] for n in advance_news(server, 14))
# stale rumour case: a legacy knowledge row with no path never shows
insert_legacy_knowledge(conn, me, "Mario Basso was seen at the docks")
assert not any("Mario Basso" in n["text"] for n in advance_news(server, 7))
# kin case: his mother's illness reaches him, told by his sister, as floor
assert any(n["why"] == "kin" and n["path"] == "told" for n in news_after_mother_falls_ill(server))
# Review Focus 5: away in prison, the sister's news waits with her
put_away(conn, me, days=20); news = advance_news(server, 14)
assert not any(n["path"] == "told" for n in news)
assert news_gate.held_for(conn, me, sister)
# in town: the sister lives elsewhere, but their mother's illness is urgent and reaches him by phone
assert any(n["why"] == "kin" for n in in_town_skip_news(server))
# in town, not urgent gossip from a friend he never crossed waits with the friend
assert news_gate.held_for(conn, me, friend) and not gossip_in(in_town_skip_news(server))
# delivered once: after a scene with the sister, nothing she held is offered again
scene_with(server, sister); assert not news_gate.held_for(conn, me, sister)
# a false rumour stays false in transit
assert knowledge_of(conn, me, rumour_key)["holds_true"] == 0
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick` (update `connector_advance_test` expectations only
  where the gate deliberately changes them, and say which in the commit), commit.

### Task 10b: Every side door onto the gate

For Deploy 1, this task closes the life_matters, claims, texture, temptations and findings doors. The
`civic_tick`, `crime_response` and `information.py` items below move to Task 15.

Approved by the owner on 2026-11-26. After this task, nothing reaches the protagonist's news except through
`news_gate` (a knowledge row with a `path_kind`, or an everyday channel he has).

**Files and the door each closes:**
- Modify: `engine/life_matters.py` (`weekly`'s `hearsay.reach` call writes `pending_news` with a carrier instead)
- Modify: `engine/claims.py` (`deliveries` go to `pending_news`; `from_knowledge` stops reading legacy `rumour:` rows)
- Modify: `engine/civic_tick.py` (`_tell_player`: votes and results go out on the paper and radio channels, and an
  associate's indictment goes to `pending_news` with a carrier; nothing goes to the old delivery ledger)
- Modify: `engine/texture.py` (`ingest` and `deliver` stop when `news_gate='1'`; the room read in `block` stays)
- Modify: `engine/temptations.py` and `connector/timeflow.py` (a new chance for the protagonist reaches him through
  its carrier or the place he passes, as gate news; `chances` in the time-skip result shows only those that reached
  him; the chances themselves are unchanged)
- Modify: `engine/findings.py` (`tell` and `learn` write `path_kind` and `basis`, and log through `rollback` inside
  a scene)
- Modify: `engine/crime_response.py` (a report with high `publicity` in `public_attention` becomes a paper or radio
  item; the threshold goes in `levels.json` `news_paths`)
- Modify: `engine/information.py` (the event-to-rumour broadcast, `seed_rumours_from_events` and the exposures, runs
  only when `systems.rumour_broadcast` is true; Caerness sets it, Saint Jude leaves it out)
- Test: `tests/news_side_doors_test.py`, one case per door

- [ ] **Step 1: Write the failing test:**
```python
for door in ("life_matters", "claims", "civic", "texture", "temptations", "findings"):
    item = trigger_door(conn, door)                           # each makes something he could hear about
    assert item_arrives_only_via_gate(server, item)           # reaches him with a path, or waits with a carrier
assert paper_carries(server, high_publicity_crime(conn)) and not paper_carries(server, low_publicity_crime(conn))
assert count_after_days(conn, "rumour_exposures", 30) == 0    # no broadcast in Saint Jude
put_away(conn, me, days=20); assert not civic_indictment_reaches(server)   # away means it waits
```
- [ ] **Step 2 to 5:** run (FAIL), implement door by door, run with `--quick`, commit per door.

### Task 11: Brief and change-based read budget

**Files:**
- Create: `connector/brief.py`
- Modify: `connector/views.py` (`compact_scene` builds on `brief.full`), `connector/store.py` (`note kind=scene`
  returns `brief.full`), `connector/timeflow.py` (after a skip, return `brief.full` in place of the separate blocks),
  `connector/server.py` (results of `act`, `money`, `note` during an open scene carry `brief.changed`)
- Modify: `engine/texture.py` (`block` drops `outside_his_knowledge`) and `engine/claims.py` (`cutaways` is no longer
  shown)
- Modify: `engine/outings.py` (`go_out` stops returning `you_may` and pre-rolled happenings; `approach` gives way to
  scenes; `crowd` stays as the venue read, built on `routines.where`)
- Test: `tests/brief_budget_test.py`

**Interfaces:**
- Produces:
  - `full(conn) -> dict`, keys in this order: `waiting_on_you`, `present` (per person: name, body, manner,
    temperament in words, tie to him in words, `on_their_mind` (at most three live concerns in plain words), `about_to`
    (pending decisions that involve this scene or him), `has_news_for_you` (from `held_for`)), `crossing_your_path`
    (arrivals, visits, matters due within 7 days that involve him), `news`, `money`, `texture`;
  - `changed(conn, call_effects) -> dict`: only what this one call changed. There is no cursor, since MCP calls hold
    no state between them. Bringing someone in or seeing them leave adds or removes their `present` entry.
  - `full` is read-only. `has_news_for_you` lists a carrier's items not yet delivered, or delivered in this open
    scene, so `resume` and a second brief show the same thing. Delivery happens at `close_scene` (Task 4).
- Nothing about people not present, and nothing building elsewhere, appears in either. The owner's rule
  (2026-11-26): the GM sees only what is nearing the protagonist (`crossing_your_path`); the old "outside his
  knowledge" part and the cutaways go.

- [ ] **Step 1: Write the failing test:**
```python
b = server.note("s1", "dinner at the Morettis'", kind="scene", present=["Aurelio Moretti"])["brief"]
assert list(b)[:3] == ["waiting_on_you", "present", "crossing_your_path"]
assert "Aurelio" in dump(b["present"]) and "Tullio" not in dump(b)        # Tullio's plans aren't in the room
assert len(dump(server.money("p1", "pay", {...})["changed"])) < 600        # per-call changes stay small
assert not leak_words(b, ["concern", "pressure", "score", "engine"])       # no machinery
assert "outside_his_knowledge" not in dump(b) and "cutaway" not in dump(b)
assert "you_may" not in dump(server.act("p1", "go out", {"place": "the Starlite"}))   # no menu of moves
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 12: Storyteller rulebook

**Files:**
- Modify: `connector/rulebook_core.md` (rewrite as the principles of design section 4, each with one short playtest
  example from `docs/playtests/2026-11-25-dominic-2.txt`, plus how to use scenes, stamps, `close_scene`, canon by kind,
  `rationale`, engine answers and turning events)
- Modify: `worlds/saintjude/rulebook_section.md` (Saint Jude's own examples, if any principle needs one)
- Test: `tests/connector_resume_test.py` (update the rulebook expectations it pins)

- [ ] **Step 1:** Rewrite. The rulebook holds only:
  - the storyteller principles, each with one example;
  - a scene lifecycle of five lines or so: open with `note(kind="scene")`; stamp what can't be undone; close with
    `close_scene` before moving on or skipping; `from_stamps` when there's nothing to add; `resume` returns an open
    scene.

  Parameter shapes and modes go in the tool docstrings (`note`, `close_scene`, `author`), where the GM reads them at
  call time. Principles, not rules per symptom.
- [ ] **Step 2:** `--quick`. Expected: PASS.
- [ ] **Step 3: Commit.**

### Task 13: Slice 2a checkpoint (lead)
- [ ] Run the bench on all eight situations; score with `check.py` and by reading. Fix rounds go to the owning task's
  files.
- [ ] Review P2.32 to P2.37 (commits up to `dc448e9`) against the design: list each fix as kept, folded in, or to be
  dropped. Dropping code needs the owner's yes.
- [ ] Report to the owner with the bench scores before Phase D.

---

## Phase D: build step 4 (slice 2b, a minimal living world)

### Task 14: The protection lock

**Files:**
- Create: `engine/protection.py`
- Modify: `engine/life_matters.py` (`_Pass` loads `protected_ids` once a week; `_due_people` skips them; every partner
  draw skips them)
- Modify, the same rule for every other background roll on a named person (owner-approved 2026-11-26):
  - `engine/outings.py` (flings and scuffles: neither person drawn may be protected);
  - `engine/opening_family.py` (`resolve_unnamed_marriages`: no protected single, and no protected partner of a
    courtship);
  - `engine/household_life.py` (planned births never on a union with a protected partner; `_resolve_social_contacts`
    no longer changes a protected person's ties);
  - `engine/civilian_life.py` (`_register_family_claims` reveals no unknown grown child into a protected household);
  - `engine/claims.py` (`_react` changes no protected person's ties);
  - `engine/org_happenings.py` (the roster, the victims, the bystanders and the nearby earner skip protected people,
    except kinds marked `"befalls": true`, which still happen to anyone);
  - `engine/temptations.py` (`_others` and `_contest` draw no protected person);
  - `engine/org_succession.py` and `engine/org_coup.py` (never vote, spend, plot or defect for the protagonist);
  - `engine/crime_response.py` (`_dispose_one` never pleads for the protagonist; his plea waits for play).
- Not locked: police work, arrests and the law's response to harm done by or to a protected person. Those are
  consequences, not rolls.
- Test: `tests/protection_lock_test.py`

**Interfaces:**
- Produces:
  - `protected_ids(conn, day) -> set[int]`: everyone `active`, the object of a live concern of an active person,
    anyone with an active obligation with an active person, and anyone in a scene within `lock_quiet_days` who has
    none of those.
- Chance still starts things for protected people (design 3, source 4). The `illness` kind is exempt from the lock.
  When it opens for a protected person, it also opens a `fears_for` concern for each of his close kin who is active,
  with `origin_kind='chance'`. Every other kind is blocked.
- Audited by the lead: `_open_illness` only opens a health condition. Any death comes later, through the health
  system's own reviews (the first is 14 days on), never in the same tick. Keep it that way.

- [ ] **Step 1: Write the failing test:**
```python
court(conn, me, carla)   # Dominic's live concern "courts" Carla
run_life_matters_weeks(conn, 52)
assert no_life_matter_with(conn, carla, except_kinds={"illness"})          # neither subject nor partner
assert no_life_matter_with(conn, supplier_with_obligation, except_kinds={"illness"})
force_illness_roll(conn, carla); m = life_matter_of(conn, carla, "illness")
assert m and m["stage"] in ("ill", "badly_ill")              # illness still fires, as onset, not death
assert concern_of(conn, me, "fears_for", carla_or_kin)        # only when the sick person is his active close kin
bartender = met_once_in_scene(conn, day0)
run_life_matters_weeks(conn, 10)                            # past the quiet window
assert bartender not in protection.protected_ids(conn, day0 + 70)
assert life_matters_still_opens_for_unprotected(conn)       # the city keeps living
# every other roll: protect one person of each kind, run a year, and none of the rolls touched them
for roll in ("outings", "unnamed_marriage", "planned_birth", "latent_child", "claims_react", "org_roster",
             "org_victim", "temptations_other"):
    assert not touched_by(conn, roll, protected_sample(conn))
assert still_fires_for_unprotected(conn, roll="unnamed_marriage")   # the city still marries
assert protagonist_plea(conn) is None and not voted_for_protagonist(conn)
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick` plus
  `--only life_matters_test,outings_test` (or whichever tests cover `life_matters`), commit.

### Task 15: Channels, shocks, delayed effects and turning events

**Files:**
- Create: `engine/channels.py`
- Modify: `connector/authoring.py` (`kind="turning_event"`)
- Modify: `worlds/saintjude/levels.json` (`shocks`)
- Test: `tests/channels_shocks_test.py`

**Interfaces:**
- Produces:
  - `attached(conn, channel_kind, channel_id) -> list[(actor_id, link)]`, where `link` is one of `employee`, `owner`,
    `member`, `resident`, `regular`, `debt`, `supplier`, `protection` or `customer`;
  - `publish(conn, shock_id) -> list[{"actor_id", "effect", "felt": bool, "knows_cause": bool}]`. A felt effect raises
    the package pressure domain for that shock kind. Knowing the cause takes a path: he is the owner, or someone told
    him. Delayed effects become `scheduled_effects` rows on the same chain.
- **Acute shocks open concerns straight away.** A felt effect at or above `acute_shock_line`, on someone `notable` or
  `active`, opens a concern at once (`origin_kind='exposure'`, on the shock's chain). Slow build-up stays for active
  people only (Task 16). This is how Carla's father, who is notable, has something on his mind after the squeeze.
- **The bridge to the protagonist.** `publish` first writes what each affected person knows of it into his own
  knowledge (`basis` felt or saw). It then picks carriers as the contract says: the affected person, if tied to the
  protagonist (kin, friend, close per `close_rule`, or the object of a live concern of his); otherwise a household
  member or close kin of the affected person who is tied to him. Carla is the carrier for her father's shop: she
  learns it at home (`basis` told), and a `pending_news` row is written with her as carrier and the protagonist as
  recipient, `urgent` set per `urgent_kinds`, on the chain. The gate (Task 10a) delivers it from there. Nobody else's
  news is created.
- `turning_event` checks: every channel resolves; the event doesn't contradict ownership or state (closing a business
  already closed, a fire at a place that doesn't exist); recent shocks on the same channels within 365 days give a
  consequence note. Commit: a `causal_chains` row (`origin_kind='turning_event'`, `touches_open_thread` set when a
  channel's attached people include anyone with an open obligation or a live concern involving the protagonist), then
  `channel_shocks`, then `publish`.

- [ ] **Step 1: Write the failing test:**
```python
sid = shock(conn, "business", bakery, "takings_down", 0.4)
effects = channels.publish(conn, sid)
assert {e["actor_id"] for e in effects} == attached_ids(conn, "business", bakery)
assert any(e["felt"] and not e["knows_cause"] for e in effects)            # feels it without knowing why
assert concern_of(conn, notable_owner, origin_kind="exposure")              # acute shock: a concern at once
assert pending_news_for(conn, me, carrier=carla, chain=chain_of_shock(sid))          # two hops: her father's shop
assert knowledge_of(conn, carla, shock_key)["basis"] == "told"                     # she heard it at home
assert not pending_news_for(conn, me, carrier=stranger_employee)            # no tie, no news
assert same_chain_via_record_changes(conn, sid, pressure_row(conn, carlas_father, "cash_strain"))
out = server.author("t1", "turning_event", {"scope": "local", "channels": [{"kind": "business", "name": "Rizzo's Bakery"}],
                                            "shock": "fire", "summary": "a kitchen fire closes Rizzo's for a month"})
assert chain_of(out)["origin_kind"] == "turning_event" and pending_effects(conn, chain_of(out)["id"])
assert server.author("t2", "turning_event", {..., "channels": [{"kind": "business", "name": "No Such Shop"}]})["status"] == "refused"
assert any(a["kind"] == "consequence" for a in server.author("t3", "turning_event", {second fire, same street})["answers"])
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 16: Pressure build-up and concerns

**Files:**
- Create: `engine/pressure.py`, `engine/levels_tick.py`
- Modify: `engine/simulation.py` (register process key `levels`, weekly, after `life_matters`)
- Modify: `worlds/saintjude/levels.json` (`pressures`: `cash_strain` from cash against weekly household need;
  `work_restless` from time in the same work at a low wage relative to his trade)
- Test: `tests/pressure_buildup_test.py`

**Interfaces:**
- Produces:
  - `build(conn, day, actor_ids) -> list[concern_id]` for active close people. Each person's threshold is the package
    base times a per-person factor drawn once from a lognormal spread seeded by actor id.
  - Crossing the threshold opens a concern with `origin_kind='buildup'` and an `origin_text` that names the build-up
    and its length ("four months short of the rent").
  - A failed attempt sets `cooldown_until_day`. Past the package's adaptation time with no attempt, `adapted=1` and
    the concern becomes `resigned`.
  - `levels_tick.process_due(conn, day)` runs `levels.refresh`, `pressure.build`, `offscreen.fire_due` (Task 17b) and
    due `scheduled_effects`; `next_due_day(conn)` follows the house pattern.

- [ ] **Step 1: Write the failing test:**
```python
for p in ten_close_people_same_age_and_cash(conn): starve_cash(conn, p)
weeks_to_tip = run_weeks_until_concern(conn, people, max_weeks=40)
assert len(set(weeks_to_tip.values())) > 3                  # they don't tip in step
c = concern(conn, people[0]); assert c["origin_kind"] == "buildup" and "month" in c["origin_text"]
fail_attempt(conn, c); assert no_new_concern_within(conn, people[0], days=cooldown)
assert resigned_after_long_unmet(conn, people[1])
assert not concerns_for(conn, a_materialized_minor)        # only level 3 builds this way
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 17a: Offscreen weighing

**Files:**
- Create: `engine/offscreen.py` (`weigh` only)
- Modify: `worlds/saintjude/levels.json` (`actions`: first contents `seek_income`, `ask_loan`, `call_in_debt`,
  `avoid`, `confront`, `pressure_business`, `make_offer`, `settle`, `do_nothing`)
- Test: `tests/offscreen_weigh_test.py`

**Interfaces:**
- Produces:
  - `weigh(conn, actor_id, day, why) -> decision_id | None`. It is called when a concern opens, a waited-on date
    arrives, or a shock hits him.
  - Options are the package actions that serve a live concern and whose needs he meets. Each is scored from concern
    strength × fit, plus habit weight, plus temperament bias, plus mood from recent deeds, plus noise (normal, package
    sd). Competing concerns subtract where an action harms another concern.
  - `do_nothing` is always scored, from inertia. When it wins, the concern is marked `waiting`.
  - Every weighing writes an `offscreen_evaluations` row: the chosen action (or `do_nothing`), the reason, and the
    rejected options with their scores.

- [ ] **Step 1: Write the failing test:**
```python
d = offscreen.weigh(conn, frank, day, "concern opened")     # Frank: needs money, hates his job, mother ill
assert decision(conn, d)["reason"] and evaluation(conn, frank)["rejected_json"]   # every choice stores why
choices = [offscreen.weigh(fork(conn, seed), frank, day, "x") for seed in range(20)]
assert len({decision(c)["action"] if c else "do_nothing" for c in choices}) >= 2   # not always the optimum
assert "confront" not in actions_of(choices_when_mother_ill)                        # competing concern holds him back
assert evaluation_when_nothing_won(conn)["chosen_action"] == "do_nothing"
assert offscreen.weigh(conn, me, day, "x") is None and not evaluations_for(conn, me)  # never for the protagonist
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 17b: Decisions falling due, and offers

**Files:**
- Modify: `engine/offscreen.py` (`fire_due`)
- Modify: `engine/hearsay.py` (`waiting` includes pending decisions with `offer_to_actor_id` = him and `told_day` set)
- Test: `tests/offscreen_fire_test.py`

**Interfaces:**
- Consumes: Task 17a's decisions; Task 15's `publish` for `pressure_business`.
- Produces:
  - `fire_due(conn, day) -> list[decision_id]` carries out due decisions through existing engine effects (loans and
    payments through money records, obligations, ties, a `channel_shock` for `pressure_business`), all on one causal
    chain under `rollback.current`.
  - A fired decision aimed at an active person opens a concern for him (`origin_kind='other_act'`).
  - An offer whose `expires_day` passes lapses or escalates only if `told_day` is set.
  - A `stated` decision from a scene fires on its due day as the stamp says. If no engine effect fits, it becomes a
    `waiting_on_you` matter for the GM to play.

- [ ] **Step 1: Write the failing test:**
```python
d = pending_decision(conn, mover, "pressure_business", target=shop, due=day + 3); run_days(conn, 4)
assert decision(conn, d)["status"] == "fired" and shock_on(conn, shop, chain=decision(conn, d)["causal_chain_id"])
loan = pending_decision(conn, frank, "ask_loan", target=me_friend_active, due=day + 1); run_days(conn, 2)
assert concern_of(conn, me_friend_active, origin_kind="other_act")
offer = make_offer_to_me(conn, frank, expires_in=7, told=False); run_days(conn, 10)
assert decision(conn, offer)["status"] == "pending"         # untold offers don't lapse
offer2 = make_offer_to_me(conn, frank, expires_in=7, told=True); run_days(conn, 10)
assert decision(conn, offer2)["status"] in ("lapsed", "fired")
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 18a: The world scorer

**Files:**
- Create: `tools/score_world.py`
- Test: `tests/score_world_test.py` (on a small hand-built save with known counts)

**Interfaces:**
- Produces: `score_world.py <db> --from-day N --to-day M -> JSON` with C1 to C10 and the two turning-event measures:
  - the share of level-3 events with a stored cause;
  - events per kind per 100 people per year;
  - GM turning events against engine-originated chains, and the convenience-bias share;
  - for each action in the package set that never fired, why: no concern it serves, needs never met, or `do_nothing`
    always outscored it (from `offscreen_evaluations`).

- [ ] **Step 1 to 5:** test with known counts (FAIL), implement, run with `--quick`, commit.

### Task 18b: One mover, the ten-step chain, absence and the routine run

**Files:**
- Modify: `engine/offscreen.py` (movers: concerns seeded from their organisation's `organization_pressures` rows as
  `wants` with `origin_kind='exposure'`)
- Create: `tests/levels_chain_test.py`, `tests/levels_life_test.py` (slow: add to `tests/slow_tests.txt`)
- Test: both files above

**Interfaces:**
- Consumes: Tasks 10, 11, 15, 16, 17a, 17b and 18a.

- [ ] **Step 1: Write the chain test** (`levels_chain_test.py`), one assertion per step of design section 10.4:
```python
mover = a captain from mover_roles; give his outfit an organization_pressures row (collections short)
run_weeks(conn, 8)
c = concern(conn, mover);                                  assert c                                    # 1 concern
d = decision_of(conn, c);                                   assert d["action"] == "pressure_business"   # 2 decides
shock = shock_of(conn, d);                                  assert shock["channel_id"] == carlas_fathers_shop  # 3
p = pressure(conn, carlas_father, "cash_strain");           assert p["level"] > 0                       # 4
# 5: shop trouble isn't urgent, and Carla doesn't share his household or routine, so it waits with her
h = pending_news_for(conn, me, carrier=carla, chain=shock["causal_chain_id"]); assert h and not h["delivered_day"]
b = brief_with(server, carla);                              assert "has_news_for_you" in dump(b)        # 6 she has it
server.act(...player responds...); r = server.close_scene(...)                                          # 7
n = knowledge_of(conn, me, shock_key);                      assert n["path_kind"] == "told" and n["carrier_actor_id"] == carla  # 8
b2 = brief_with(server, carlas_father);                     assert "on_their_mind" in dump(b2)          # his worry, later
run_weeks(conn, 4);                                         assert world_moved_on(conn, mover)          # 9, 10
assert same_chain(conn, c, d, shock, p, n)                  # one chain from origin to news
```
- [ ] **Step 2: Write the life test** (`levels_life_test.py`): a fresh save run 120 days with only routine acts, then
  `score_world.py`; assert C1 (every level-3 event has a cause), that there's at least one courtship step, one
  business change and one organisation aim pursued, and no doubled consequence. Add the three absence tests:
  1. 60 days away: the city changed for its own reasons;
  2. his return: a carrier holds news for him and nothing is dumped as a summary;
  3. an important day without him: a wedding or vote happens and doesn't reach him without a path.
  Run one year at most.
- [ ] **Step 3: Run both.** Expected: FAIL until the mover wiring is in.
- [ ] **Step 4: Implement** the mover wiring. Run both, then `--quick`.
- [ ] **Step 5: Commit.** The lead runs the bench again (all eight situations) and reads the life run's scores.

---

## Phase E: build step 5

### Task 19: Deploy and the owner's playtest (lead)

This runs twice: after Task 14 (Deploy 1) and after Task 18b (Deploy 2). See Delivery and cost.
- [ ] Back up the VM saves (`/var/lib/caerness/backups/pre-levels-<date>/`), check integrity, then deploy the branch.
- [ ] Start a fresh Saint Jude save. Dominic's old save is not migrated for play.
- [ ] The owner plays an evening, then a stretch of several game weeks. Nothing is staged to show off features.
- [ ] Faults go through the scoring sheet. Each fix goes to the task that owns the code.
- [ ] Once the slice is proven, delete the old feeds behind `news_gate` (owner's yes first). Then write the plan for
  steps 6 to 8.
