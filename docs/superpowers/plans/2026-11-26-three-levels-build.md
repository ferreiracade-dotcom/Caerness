# Three levels: build plan (steps 1 to 5)

**Revision 6.0 (2026-11-27).** This is the build text for the grand plan's Deploys 1 and 2
(`docs/superpowers/plans/2026-11-27-saint-jude-grand-plan.md`). Every change from the grand plan's review rounds
is already in the task text below; the round blocks after the revision list say which task each one touched.
Where a task's text and an older revision note differ, the task's text wins.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> In this repository, tasks run in Sonnet linked sessions, one writer per file set, and the lead reviews every diff.

**Goal:** Build steps 1 to 5 of the three-levels design (revised 2026-11-26 after Gemini's review of this plan): the scoring sheet and GM test bench, the data model, slice 2a
(the GM–engine loop) and slice 2b (a minimal living world), ending in the owner's playtest of a fresh Saint Jude save.

**Architecture:** New engine modules sit beside the city layers and read their existing tables. The connector gains
scene ledgers, one news gate, engine answers and turning events. Life draws (`life_matters` and the other
life modules) keep running for everyone; one that touches someone `near` him becomes a nomination (Task 14a;
revision 6.3 replaces the earlier "only below level 3"). One weekly `levels` process carries pressure build-up, offscreen choice, decisions falling due
and delayed effects. Old news feeds go behind a flag first and are deleted only after the playtest.

**Tech Stack:** Python 3.13, SQLite, the MCP connector (`connector/server.py`), package JSON under
`worlds/saintjude/`, script-style tests run by `tools/run_suite.py`.

**Spec:** `docs/superpowers/specs/2026-11-26-three-levels-design.md` (revision 3.1; section 11 overrides earlier
sections) and its contract `docs/superpowers/specs/2026-11-26-three-levels-contract.md`. Every table, column, tool
argument and module function named below is defined in the contract; read it before your task.

## Global Constraints
- **Story first (revision 5, binding):** every task must make the story more believable, more reactive, more
  interesting to play or more coherent over time, by the simplest mechanism that does it. Where a step below builds
  more machinery than that needs, the simpler reading wins; ask the lead if unsure.
- No hard caps, ladders or ceilings: a threshold marks a real change of state, never a points ladder.
- No world words in `engine/`: every Saint Jude figure, name or list lives in `worlds/saintjude/*.json`.
- The engine vetoes contradictions only and never hands the GM a menu or a closed list.
- The protagonist lives under the same rules as everyone else; the engine never chooses for him. Grand plan round 6:
  no background tick writes a choice for him. Only three things may: what befalls him, routine upkeep and payroll,
  and an act by his second or manager, recorded as theirs. Task 14c's hands-off test enforces it.
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
- tie resting points, hysteresis and ties by context (`tie_contexts` is not built here: revision 5.2);
- movers' plans through organisations, with imperfect execution (only one mover acts here, directly);
- promotion by demonstrated significance, careful demotion, and obligations through life changes;
- several different starting saves;
- revision 5.1: a look back over his history and the city's big events (a lookup over the scene ledger and
  `causal_chains`).

---

## Delivery and cost (owner-approved 2026-11-26; overrides the task steps where they differ)

**Two deployments.**
- **Deploy 1, after Task 14d:** Tasks 1 to 13, then Tasks 14a to 14d, then a Task 19-style deploy and playtest. Task 14 is
  now nominations, consistency and agency guards (design section 0). Deploy 1 is the GM loop, the news gate with
  every door, and life near him going on through nominations.
- **Deploy 2:** Tasks 15 to 18d (the living world, noticing, business state, his death or long sentence), then
  Task 19.
- **Design section 0 (revision 4, approved 2026-11-27) governs every task.** Engine: state, memory, numbers, causes,
  vetoes. GM: prose and invention. Near him, the engine nominates, the GM realizes and the engine ratifies. Where a
  task below says the engine does something to a person near the protagonist, it nominates instead.

**Deferred to Deploy 2, to save cost:**
- `undo_chain` from Task 6 moves into Task 15, where chains first appear. Task 6 builds `undo_scene` only.

**Tests: targeted per task, the full suite at checkpoints.**
- Wherever a step says "run `--quick`", run instead the task's own test plus the existing tests of the modules it
  modifies (`--only a_test,b_test`). The commit names which ones were run.
- The full `--quick` suite runs only at the checkpoints: after Task 6, at Task 13, and before each deployment.

**GM checks (revision 5.2).** There is no scripted bench. `tools/gm_check.py` (Task 7) runs on the transcripts of
the owner's real playtests and on any session the lead plays, and the lead reads them against the Task 1 checklist.

**Side by side.**
- Tasks that share no files run as parallel sessions: Task 2b with Task 1; Task 7 with Tasks 4 and 5 (Task 7 is now small); Task 16 with
  Task 15.
- Never two writers on the same files.

**Fix rounds go to the session that did the task,** not to a fresh one.

**Revision 5, story first (owner, 2026-11-27).** The design's revision 5 block governs every task. What it changed
here:
- Task 1: a short checklist, not a scoring framework.
- Task 7: the bench is a smoke check for known GM faults; the owner's playtests weigh more.
- Task 8: the engine's answers are consequence facts only, with no character notes.
- Task 14: one rule over remembered facts replaces the four conduct build-ups.
- Task 15: it reuses the existing tables.
- Tasks 16 to 17c: a short pick replaces the scored choice. Pressure is a plain package line, with no lognormal
  thresholds, cooldowns, adaptation or mood.
- Task 18a: three measures.
- Task 18d: firm in Deploy 2 (revision 5.2).

**Revision 5.1, play anyone (owner, 2026-11-27).**
- Task 11: the brief shows what he runs.
- Task 12: a rulebook line against pushing him to rise.
- Task 14: seat decisions are his.
- New Task 14b (now 14d, revision 5.2), in Deploy 1: starts in a held seat (he replaces the holder), and a four-start check.
- Task 18b: the political start becomes part of 14b's check, which runs again before Deploy 2.

**Revision 5.2 (Gemini's review, each point judged by the story-first test).**
- **Task 14 is split into four sessions,** in this order:
  - **14a:** `nominations.py` and `levels_tick.py`, and the hooks in the life modules.
  - **14b:** `conduct.py`, with broken promises and lies found out.
  - **14c:** agency guards and seat decisions, with the second or manager for each seat kind.
  - **14d:** starts at any scale (formerly 14b).
- **Task 17c is built after Task 17b,** since it uses `pressure.py`, `offscreen.py` and the follow-ups.
- **Order of hooks:**
  - Task 10a hooks `news_gate.deliver` into `scenes.close`.
  - Task 15 builds `undo_chain` and teaches turning events in the rulebook.
  - Task 17b registers `offscreen.fire_due` in the tick.
- **Cut:** the scripted bench, `engine_answers` and `rationale`, `tie_contexts`, the daily clock change in
  `tiers.py`, routine changes as nominations, the second mover path for outfits, the separate scorer tool, and drawn
  paying habits.
- **Task 18d is firm in Deploy 2.**

**Revision 5.3 (Gemini's second reply).**
- Every file goes to a named part of Task 14 (see its header).
- Task 15b is now Task 17c, placed after Task 17b.
- Fields that a later task fills are defined empty by the earlier one.
- Six unread schema fields, `standing.infer` and the ties `context` field are cut.
- The business probe measures late payment first.
- `gm_check.py` gains `--db`.

**Revision 5.4 (Gemini's third reply).**
- Stamped decisions past due become his matter or lapse (Task 14a).
- Deploy 2's settings start as `null` (Task 3).
- Task 10a's file list is complete.
- `merchant.py` is out of Task 14c.
- `strength` is wired into the brief and into noticing.
- Seven unread fields are cut.

**Revision 5.5 (Gemini's fourth reply).**
- Stamps take `due_in_days` (Tasks 4 and 5).
- `levels_tick` weighs live concerns before `fire_due` (Task 17b).
- The competitor shock moves to Task 18c, and `channels.run_due_effects` is added (Task 15).
- `strength` defaults to 0.5 (Task 3).

**Revision 5.6 (Gemini's fifth reply).** `scene_stamps.due_in_days` and `scenes.stamp(due_in_days=None)` are added,
and a stated decision takes its target from the stamp (Task 4).

**Revision 5.7 (cross-sphere play, from Gemini's reading of the owner's later ChatGPT messages).** All in Deploy 1:
- Task 3: an organisation he founds counts like any other.
- Task 10a: he sees himself in the news, and television is a channel.
- Task 10b: an ordered act puts his men on record and him as the one who ordered it.
- Task 11: a `standing_here` line.
- Task 12: two rulebook lines.
- Task 14c: insider news through his crew.

**Revision 5.8 (an ambitious city, from Gemini's ambitious-movers note).**
- Deploy 1, Task 3: owners of the city's big businesses are movers, above a package line. The canon paper, radio and
  television outlets become business rows.
- Deploy 2:
  - Task 16: an opportunity opens a concern, as strain does.
  - Task 17a: three ambition actions; a buy-out reuses the ownership change of `act`'s `trade`.
  - Task 17b: the visible steps of a plan travel as news.
  - Task 18b: the life run proves one ambition pursued by someone outside the outfits.

**Revision 5.9 (Gemini's reply to 5.8).**
- How news reached someone is a small generic kind plus the package's channel name, so a new channel (a magazine,
  a parish bulletin, television) is package data (Tasks 3 and 10a).
- One helper writes paper, radio and television items (Task 10a).
- An ordered act writes its true knowledge rows directly (Task 10b).
- An opportunity is acted on once, when it appears (Task 16).
- The ambition actions are carried out in Task 17b, with an acceptance rule.
- The outlets: four already exist in the seed, and three are added (Task 3).
- `standing_here` sits inside `you` (Task 11).

**Revision 6.8 (the code audit's third pass).**
- Task 14d: in a package that runs the org core, his outfit tools (its purse, hiring, promoting and dismissing, truces,
  heat, "his outfit") use the org core instead of the old Caerness tables, which are empty in Saint Jude. The boss
  start's test proves it.

**Revision 6.7 (the code audit's second pass, the paths that run during play).**
- Task 14c and the contract: his answer to a seat matter goes through the existing `act(action_type="answer")`, which
  already answers `waiting_on_you`. Revision 6.5's `note(kind="answer")` is dropped: it duplicated that tool.
- Task 11: `act`'s results give sums in dollars, and `act(outing)` no longer leads to the deleted `outings.approach`.
- Task 12: an intent `act` can't map comes back `unmodelled` with the way to record it, never refused.

**Revision 6.6 (owner's code audit, 2026-11-27; `docs/review/saint-jude-code-audit.md`).**
- Task 2b: the psychology process is off in Saint Jude (required, no longer optional tidying); babies get no
  cultivation Core where the package has no cultivation; the death check stops logging every person every month.
- Task 3: the schema 134 migration removes the Core rows wrongly given to Saint Jude babies.
- Task 3b: the callers of `presence.py` that place named people move onto `routines.where`, so one system answers
  where a person is.

**Revision 6.5 (Gemini round 11).**
- Task 14b: each nomination from `conduct` names the fact behind it, and a fact that has already produced one, of
  any status, never produces another, so a played-out confrontation isn't nominated again every week.
- Task 14c and the contract: `note(kind="answer", nomination, choice)` is the connector's way to pass his answer to
  a seat matter (replaced by revision 6.7: the existing `act(action_type="answer")` does it).

**Revision 6.4 (Gemini round 10: slips in this plan's own text).**
- Contract and Task 3: `nominations.status` allows `lapsed`.
- Task 16: an opportunity is tied to its `actor_pressures` episode, so a fired one isn't reopened while cash stays
  high; Task 17b marks it `resolved`.
- Task 7: the cutaway check covers the wider cutaways too.
- Tasks 14c and 17b: missing files added; Task 17b replaces Task 14a's stated-decision cleanup.
- Task 11: the test's second `advance` uses its own call id; `levels.json` is in its files; a media item is marked
  shown on its own row.

**Revision 6.3 (Gemini, owner's yes 2026-11-27).**
- Architecture and Task 14a: life draws keep running for everyone; one touching someone `near` him becomes a
  nomination, any other applies under the consistency check and records its cause.
- Task 14a: `apply_overdue` never acts on a `seat_decision`.
- Task 16: `work_restless` only for wage earners; `cash_strain` reads the money a man can draw on.
- Tasks 7 and 11: wider cutaways are marked shown once, have a significance floor, and are not checked as scene people.

**Revision 6.2 (Gemini, owner's yes 2026-11-27).**
- Task 14: `near` no longer includes a mover with no tie to him, so distant movers act on their own.
- Task 14c: his answer to a seat matter goes back to the code that asked; unanswered, nothing is decided for him.
- Task 14b: a skipped day counts as time with whoever his routine puts him with, so a skip doesn't breed neglect.
- Task 4: a casual extra is recorded like an authored person, so `undo_scene` reverts it cleanly.
- Task 14d: personal nominations are asserted over 120 days, and only reported at 30.

**Revision 6.0 (Gemini, owner's yes 2026-11-27).**
- Task 4: a scene has a part of the day, so `routines.where` judges presence for a morning garage scene and an evening
  bar scene on the same day correctly.
- Task 11: a cutaway is a reaction to what he did or how he is seen, never a plan aimed at him. Revision 6.1
  (owner): it covers anyone reacting to what is public or visible about him, not only his circle.
- The grand plan's changes to Deploys 1 and 2, by task: Task 3 (the `refresh` guard is all of careful demotion), Task
  4 (part of the day), Task 7 (cutaways used as his knowledge; unheld recap threads), Task 11 (cutaways on skip and
  close results; his ventures in `you`), Task 12 (cutaways; never refuse an unmodelled ambition), Task 14c (his
  council vote, his prison filings, his inside group, the hands-off test), Task 14d (an outside counterpart), Task 15
  (`demand_up`), Tasks 17a and 17b (officials who seek payments and rig counts), Task 18c (`trades.json` as default
  costs). Each is marked in its task as "grand plan round n".

**Grand plan round 6 (2026-11-27).**
- Task 14c gains the hands-off test (90 to 120 days with no calls from him, in every role) and a third guard:
  `prison.assign_group` no longer places him; the group that would take him makes an approach, as a nomination.

**Grand plan round 5 (2026-11-27).**
- Task 14c names the two places that act for him today: `civic_votes.member_vote` casts his council vote from his
  lean, and `prison_review.weekly` files appeals and pardons for him by chance.

**Grand plan round 3 (2026-11-27).**
- Task 7's `gm_check` reports a recap thread with nothing held behind it (former F-6).
- Office holders seek payments and rig counts as their own decisions (former F-4): two actions in Task 17a, carried
  out in Task 17b through P1's existing graft and fraud code.

**Grand plan round 2 (2026-11-27).**
- Cutaways are built in Deploy 1: Task 11 keeps them as their own field on skip and close results, Task 7 reports one
  used as his knowledge, and Task 12 teaches them.
- Task 3's `refresh` guard is the whole of careful demotion; a test pins it.

**What each deployment proves (revision 4.2).** Deploy 1 proves that the GM and engine work together. Deploy 2
proves that the world moves around him. Steps 6 to 8 make the three resolutions complete. Neither deployment
is reported as the finished design.

## Phase A: build step 1

### Task 1: Scoring sheet and playtest situations

**Files:**
- Create: `docs/playtests/2026-11-25-dominic-2.txt` (copy of
  `C:\Users\NozzE\.claude\uploads\63f5ee28-600c-4604-899a-a5ee025d8f85\aad99367-Saint_Jude_roleplay_with_Dominic.txt`;
  owner lines start with the player's turns)
- Create: `docs/superpowers/specs/2026-11-26-scoring-sheet.md`
- Create: `docs/playtests/situations.md`

**Interfaces:**
- Revision 5.2: the situations are a reading checklist for playtests, not bench fixtures.
- Produces: the sheet's check ids (`C1`..`C3` for the engine, matching Task 18a's three measures; `G1`..`G5` and
  `G10` for the GM) used by Task 7's checker and Task 18a's scorer; the situation ids `S1`..`S8` used by Task 7's fixtures.

- [ ] **Step 1: Write the scoring sheet** as a short checklist (revision 5), one line per check: id, what it
  catches, script or reading. Engine checks: C1 events near him have a stored cause; C2 event rates per kind look
  like ordinary life (neither dead nor frantic); C3 package actions that never fired, with the reason. Script-checkable GM lines are G1 menus (a numbered or lettered list of options to the
  player), G2 questions to the player that aren't about his own choice, G3 out-of-character flags, G4 exposed
  machinery (`concern`, `pressure`, `the engine`, `score`, a tool name in prose), G5 moralizing phrases from the
  transcript's faults. Add G10 (read, revision 4.2): his personal life (kin, friends, romance, ordinary evenings)
  stays present whatever his position.
- [ ] **Step 2: Write 8 situations from the transcript**, each with: transcript line range, the state it needs (who is
  present, what each knows and owes), 4 to 6 player turns quoted or condensed, what a good GM does, the sheet checks it
  exercises. Cover: S1 a lie to his mother about money, S2 a walkout from a dinner, S3 a quiet evening that should stay
  ordinary, S4 a moralizing trap (a fence offers stolen parts), S5 an ambiguous detail the record doesn't hold (does
  the supplier have a wife?), S6 a one-off customer (the Gerald Orsini case: no advance news), S7 returning after two
  weeks away, S8 a stranger at a bar who should stay a stranger.
- [ ] **Step 3: Commit**
```bash
git add docs/playtests/2026-11-25-dominic-2.txt docs/superpowers/specs/2026-11-26-scoring-sheet.md docs/playtests/situations.md
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
- Revision 6.6 (code audit):
  - Modify: `engine/simulation.py` (`SYSTEM_PROCESSES` gains `"psychology": ("psychology",)`, so a package without
    the switch doesn't run it) and `worlds/caerness/world.json` (`psychology` true). In Saint Jude it wrote grief
    and trauma scores (`psychological_stressors`) that nothing reads but a coverage count, and revision 5 rules out
    psychology simulation.
  - Modify: `engine/household_life.py` (the birth path calls `cultivation.assign_birth_core` only when
    `system_enabled(conn, "cultivation")`, as `person_ecology` and `resolution_controller` already do; all 56
    babies of a 120-day Saint Jude run got a `Closed-Core` row) and `tools/leak_scan.py` (flags any
    `cultivation_profiles` row in a package with cultivation off).
  - Modify: `engine/health.py` (`mortality_audit` gets a row only for a death, unless the package's
    `systems.mortality_audit` is true; Caerness sets it true, so its tests are unchanged. Saint Jude wrote about
    8,500 rows a year that nothing reads.)
  - Not changed here, but checked by the test: `information_links`, `resolution_transitions` and
    `actor_context_cache` (no readers) stop growing in Saint Jude as a result of the rumour-broadcast switch
    (Task 10b), the resolution switch (Task 3) and the skipped actor context (this task). If one still grows after
    those tasks, the task that owns its writer stops it.
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
# revision 6.6 (code audit), same 120-day Saint Jude run
assert count(conn, "psychological_stressors") == 0                       # no psychology simulation
assert births_in_run(conn) > 0 and count(conn, "cultivation_profiles") == 0  # no Caerness Core on a Saint Jude baby
assert count(conn, "mortality_audit") == deaths_in_run(conn)              # a row only for a death
assert caerness_package().systems["psychology"] and caerness_package().systems["mortality_audit"]
```
- [ ] **Step 2: Run it.** Expected: FAIL (209 consolidate decisions in the reference run).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run it**, then `--quick`, and `--only s1_rise_equivalence_test,org_happenings_test,outfit_choices_test`.
  Outfit actions, money and incidents stay inside the S1 ranges; if a range moves, say why in the commit.
- [ ] **Step 5: Commit** the files above.
- [ ] Optional tidying, same task, own commit: a `caerness_economy` switch for the Caerness-only processes
  (agriculture, logistics, merchant, craft, growth, war, ecology, education, patronage, seeking, attention,
  world). They run on empty tables in Saint Jude, so nothing should change but the run time. Revision 6.6:
  `psychology` left this list; it wrote rows in Saint Jude and is switched off in the required part above.
- Not done here: `org_lifecycle._dormant` still puts a former member back on the full review. With the personal
  choices off he can only hold position, so it is harmless; Task 3's `levels` owns his cadence after that.

### Task 3: Schema 134 and resolution levels

**Files:**
- Modify: `engine/schema.sql` (new tables and columns from the contract; append a `-- schema 134` block)
- Modify: `engine/db.py` (`SCHEMA_VERSION = 134`; migration adds columns with `ALTER TABLE ... ADD COLUMN` guarded by
  a column check, as the existing migrations do. Revision 6.6: on a save whose package has cultivation off, the
  migration deletes its `cultivation_profiles` rows. They were made in error by the birth path, and nothing in such
  a package reads them. Test: a Saint Jude save with such rows has none after migrating; a Caerness save keeps
  all of its rows)
- Create: `engine/levels.py`
- Create: `engine/rollback.py` (only `current`, the two `log_*` functions and the table-to-key map here; Task 6 adds undo)
- Create: `worlds/saintjude/levels.json` (every key in the contract's package section. Deploy 1's keys get first
  figures. Deploy 2's keys (`shocks`, `pressures`, `actions`, `noticing`, `long_sentence_days`, `opportunities`) are `null`, which the
  validator accepts, and each Deploy 2 task fills its own. Revision 5.4.)
- Modify: `engine/world_package.py` (load and validate `levels.json`: report missing keys, unknown role references and
  a wrong `version`, telling a missing setting apart from one deliberately left out with `null`)
- Modify: `engine/simulation.py` (`SYSTEM_PROCESSES`: the `resolution` process runs only when the package's
  `systems.entity_resolution` is true; Saint Jude leaves it out)
- Modify: `engine/resolution_controller.py` (`_materialize_latent_person` and `_sync_sim_tier`: when
  `entity_resolution` is off, a new person gets `sim_resolution='materialized_minor'` and a `simulation_profiles`
  row on the quiet routine, never one that feeds the old decision loop)
- Revision 5.2: `engine/tiers.py` is not changed, unless a kept Saint Jude module is found to need level 3 on the
  daily clock. In that case, name the module to the lead before changing it.
- Modify: `worlds/saintjude/seed.json` (revision 5.8, corrected in 5.9: the *Daily Mirror*, the *Chronicle*, the
  *Courier* and Channel 4 already exist as seed institutions with empty `owner_refs`. Give each the
  `economic_state` the seed's businesses use, so it gets a business row. Add Channels 7 and 10 and WSJD radio
  (bible, the media paragraph) in the same shape. Owners: the *Mirror* and the *Chronicle* go to their canon
  publisher offices (`open_offices`). The other four have no owner in canon, which means unknown, and the opening
  fills them as it fills any other blank. If the opening fills neither, tell the lead before choosing owners.)
- Test: `tests/levels_schema_test.py`

**Interfaces:**
- `levels` owns tiers, cadence and promotion in Saint Jude. `resolution_controller` used to re-score all 5,879 people
  there on its own scale; it no longer runs there. Materializing unnamed people (marriages into the unnamed
  population, a grown child nobody knew about) stays.
- Produces: `levels.refresh(conn, day) -> {"active": int, "notable": int, "changed": int}` and
  `levels.resolution_of(conn, actor_id) -> str`.
- Rules for `refresh`: `active` = the protagonist; anyone whose `closeness_to_me` meets `close_rule` (computed from his
  relationship row with the protagonist: affection, trust, familiarity, and kin or household); anyone in a
  `mover_roles` seat (read from the seat itself; revision 5.3). `notable` = holders of any organisation seat or office and owners
  of an enterprise with staff, not already active. `mover_roles` lists political offices as well as outfit
  seats, so a political start has rivals who plan. Revision 5.7: an organisation made through `author`
  (`kind=organisation`) counts like any other. Its leader's seat makes him a mover when its kind is in
  `mover_roles`, and a notable otherwise, and its members are attached to it for `channels`. Revision 5.8: the
  owner of a business at or above `mover_roles.business_line` (staff or capital; the package sets it so only
  the city's big businesses and property holdings qualify) is a mover too. Everyone else with a row stays `materialized_minor`. `refresh`
  never lowers anyone below `notable` while he has a live obligation or a live concern. Grand plan round 2: this
  guard is all of careful demotion; nothing later adds to it.

- [ ] **Step 1: Write the failing test** `tests/levels_schema_test.py` with checks:
```python
# fresh opening (tests.sj_fixture.build_saintjude) plus an authored protagonist "Dominic Basile", mechanic, 24
assert schema_version(conn) == 134
assert {"gm_scenes", "scene_stamps", "scene_participants", "causal_chains", "record_standing", "actor_pressures",
        "actor_concerns", "actor_decisions", "exposure_links", "channel_shocks", "scheduled_effects",
        "actor_routines", "routine_exceptions", "nominations", "record_changes",
        "pending_news", "offscreen_evaluations"} <= tables(conn)
with rollback.current(conn, scene_id=1):
    rid = insert_concern(conn); rollback.log_insert(conn, "actor_concerns", rid)
assert logged(conn, "actor_concerns", rid)["source_scene_id"] == 1
assert {"basis", "path_kind", "channel", "carrier_actor_id", "holds_true", "source_scene_id", "causal_chain_id", "cutaway_day"} <= cols(conn, "knowledge")
assert "lapsed" in check_values(conn, "nominations", "status")                                   # revision 6.4
# revision 5.9: a channel not in news_paths is refused on load; an authored organisation has real rows
assert knowledge_insert_fails(conn, path_kind="television")          # a channel name is not a kind
org = server.author("p1", "organisation", {"name": "Harbor Haulers", "members": 4})
assert head_membership(conn, org) and member_count(conn, org) >= 4
out = levels.refresh(conn, day)
assert levels.resolution_of(conn, me) == "active"
assert all(levels.resolution_of(conn, k) == "active" for k in kin_of(conn, me))
print(out, active_by_reason(conn))                     # the lead sets the band from this first run
assert 10 <= out["active"] <= 120 and out["notable"] > 0
# a captain-level seat holder from mover_roles is active even with no tie to him
assert levels.resolution_of(conn, a_mover) == "active"
# grand plan round 2: a mover who loses his seat but still holds a live concern stays notable
vacate_seat(conn, a_mover); open_live_concern(conn, a_mover); levels.refresh(conn, day)
assert levels.resolution_of(conn, a_mover) == "notable"
# revision 5.8: a big-business owner is a mover; a corner-shop owner is notable; the Chronicle is a business row
assert levels.resolution_of(conn, big_business_owner) == "active"
assert levels.resolution_of(conn, corner_shop_owner) == "notable"
assert business_named(conn, "Chronicle") and business_named(conn, "WSJD")
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
```
- [ ] **Step 2: Run it.** `python tools/run_suite.py --out runs/t3 --quick --only levels_schema_test`. Expected: FAIL
  (schema version 133).
- [ ] **Step 3: Implement** the schema block, the migration, `levels.py`, `levels.json` and its validation.
  `refresh` runs once at the end of the opening build and on protagonist creation.
- [ ] **Step 4: Run it**, then `--quick`. Expected: the new test passes; no test that passed before now fails.
- [ ] **Step 5: Commit** `engine/schema.sql engine/db.py engine/levels.py engine/rollback.py engine/world_package.py
  worlds/saintjude/levels.json worlds/saintjude/seed.json tests/levels_schema_test.py`.

### Task 3b: Routines on demand

**Files:**
- Create: `engine/routines.py`
- Modify: `engine/levels.py` (`refresh` calls `routines.seed` for anyone newly notable or active)
- Modify: `tools/build_opening.py` (seed routines at the end of the opening build)
- Modify: `worlds/saintjude/levels.json` (`schedules`)
- Revision 6.6 (code audit), one answer to "where is he": `presence.py` keeps probabilistic presence habits for
  everyone (12,469 new rows in 120 days of Saint Jude, about 11% of the engine's own time). Without this step its
  callers and `routines.where` would answer the same question differently. The callers that place named people
  move onto `routines.where`, and keep their old presence check only where `where` returns `None` (someone with
  no routine):
  - Modify: `engine/company.py` (`in_earshot`: whether someone at his place can overhear him);
  - Modify: `engine/household_life.py` (where a courting pair can meet, in its courtship scan);
  - Modify: `engine/authoring.py` (who is at home, line ~722);
  - `information.py`'s presence snapshot for rumour exposure goes with the rumour-broadcast switch (Task 10b);
    `player.py`, `turns.py`, `decisions.py` and `model_gateway.py` are the old player layer and are left alone.
  - Modify: `engine/presence.py` (with a package switch `systems.presence_habits`, false in Saint Jude and true in
    Caerness, it answers its remaining callers without storing new habit or profile rows).
  - The nearby-code review said `outings.crowd` was presence's last caller; that was wrong, and this step is
    the correction.
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
# revision 6.6: one answer to "where is he"
put_me_at(conn, garage_location, weekday, "day"); assert company.in_earshot(conn, me, frank)   # routine says the garage, so does the scene
put_me_at(conn, bar_location, weekday, "day"); assert not company.in_earshot(conn, me, frank)
rows = count(conn, "actor_presence_habits") + count(conn, "actor_presence_profiles"); run_days(conn, 120)
assert count(conn, "actor_presence_habits") + count(conn, "actor_presence_profiles") == rows  # Saint Jude stores no new habits
# and the S1 ranges (outfit actions, money, incidents) and the courtship rate stay inside the reference run's ranges
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
- `open_scene(conn, call_id, present, text, location=None, part=None)`: compared with the open scene's `location_id`. A different place is refused, naming `close_scene`.
- Revision 6.0, part of the day: `part` is `morning`, `day`, `evening` or `night`, stored on `gm_scenes.part` and
  passed to `routines.where` when judging who is `not_here`. With none given, the scene takes the part of the last
  scene opened that day, or `day`. A later scene the same day may name a later part; an earlier one is refused,
  since time doesn't run back.
- Produces:
  - `open_scene(conn, call_id, present: list, text: str, location=None, part=None) -> dict` (returns `{"scene_id", "present", "not_here"}`;
    reuses the open scene if there is one);
  - `open_scene_id(conn) -> int | None`;
  - `stamp(conn, call_id, kind, text, *, actor_id=None, target_actor_id=None, holds_true=None, ref_table=None, ref_id=None, due_in_days=None) -> dict`
    (returns `{"beat", "kind", "text"}`; refuses when no scene is open);
  - `ledger(conn, scene_id) -> list[dict]`;
  - `close(conn, call_id, mode, participants=None, amendments=None, exceptions=None, ties=None, threads=None) -> dict`
    returning `{"closed": scene_id, "learned": int, "ties": [..], "threads": [..], "refused": [..]}`.
- What `close` writes:
  - **knowledge:** for each stamp of kind claim, lie, promise, money, goods, injury, walkout or decision, a knowledge
    row for every participant present at that beat with attention `involved` or `attentive` (`overheard` at
    confidence 0.5; `distracted` none), unless an exception removes them. Each row gets `basis` saw or told,
    `path_kind` self, `holds_true` from the stamp, and `source_scene_id`.
  - **ties:** every participant pair that includes the protagonist gets a familiarity step through
    `record_relationship_effect`, smaller for each extra scene the pair shared in the last 14 days (the step shrinks to
    half each time; the figure comes from `levels.json`). `ties` entries apply as given, with `cause` as the summary.
  - **threads:** shaped as the contract says.
    - `owed` and `promise` become one obligation of `by` toward `to`: `actor_id` = `by`, `counterparty_actor_id` = `to`.
    - `meeting` becomes one obligation row per person in `with`.
    - Each row has `due_day` = today + `due_in_days`, `source_kind` 'scene' and `source_scene_id`.
  - **exceptions:** `missed_by` gets no row for that beat. `disbelieved_by` gets a row at confidence 0.1 (he heard it
    said). `secret` defaults to `holds_true=1` and gives rows only to `known_to`.
  - **news:** Task 10a adds delivery here (`news_gate.deliver`). This task leaves the hook point only.
  - **deeds (revision 5.2):** each knowledge row a closed scene writes for a witnessed act of his gets
    `spread_from_day` = the close day, so Task 10a's `spread` can carry it outward.
  - **stamps that start something:** a `promise` stamp also becomes an obligation. A `decision` stamp with an
    `actor_id` becomes a pending `actor_decisions` row (the reason is the stamp text). Revision 5.5: both take
    `due_in_days` from the stamp. A decision stamped without one is due in the package's `stated_due_days` (14). Revision 5.6: the stamp's
    `target_actor_id`, when set, becomes `target_kind='actor'` and `target_id` on the decision, so the past-due
    clean-up and `about_to` can tell whether it involves him. A tie entry that moves
    resentment or affection by at least the `levels.json` concern line opens a `resents` or `wants` concern for the
    `from` person, with `origin_kind='scene'` and the cause as `origin_text`.
  - **casual extras (revision 5.2):** a name in `present` or `participants` that matches nobody in the save becomes a
    new `materialized_minor` person at the scene's place, with no separate `author` call. Revision 6.2: it is
    recorded through the same path as `author(kind="person")`, an `authored_entities` row with the scene's
    `source_scene_id`, so `undo_scene` marks it reverted (with its routine and profile) instead of deleting a raw
    `actors` row. A name that matches someone who is elsewhere is still `not_here` (Review Focus 2).
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
# revision 6.0: part of the day
frank_at_garage_mornings_bar_evenings(conn)
assert "Frank Moretti" not in scenes.open_scene(conn, "p1", ["Frank Moretti"], "the bar", part="morning")["present"]
scenes.close(conn, "p1c", "commit")
assert "Frank Moretti" in scenes.open_scene(conn, "p2", ["Frank Moretti"], "the bar", part="evening")["present"]
scenes.close(conn, "p2c", "commit")
assert scenes.open_scene(conn, "p3", [], "the garage", part="morning").get("refused")   # time doesn't run back
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
  - every writing tool call (`act`, `money`, `author`, `note kind=detail`) runs inside
    `rollback.current(conn, scene_id=...)` while a scene is open (revision 5.2);
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
paid = server.money("m1", "pay", {"to": "Frank Moretti", "amount": 40, "what": "parts"})
assert record_changes_for_scene(conn, open_scene_id(conn))                 # mid-scene writes are logged
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

### Task 6: Scene undo

**Files:**
- Modify: `engine/rollback.py` (add `undo_scene`; keep Task 3's `current`, `log_*` and the key map. `undo_chain` is
  built in Task 15)
- Modify: `connector/correct.py` (op `undo_scene`; `preview` shows what it would revert)
- Modify: `engine/commitments.py` (`record` and `complete` log through `rollback.log_insert` and `log_update`)
- Test: `tests/rollback_cascade_test.py`

**Interfaces:**
- Produces `undo_scene(conn, scene_id) -> {"reverted": {table: count}, "left": [...]}`. It replays the
  `record_changes` log backwards:
  - inserts are deleted;
  - updates are restored from `before_json` only where no later change touches the row (otherwise the row is listed
    in `left`);
  - ties are inverted from `relationship_history`;
  - money is reversed with a reversing record, never deleted;
  - authored rows are marked reverted when nothing later refers to them, otherwise listed in `left`;
  - the scene's status becomes `abandoned`.

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
s3 = scene where Dominic pays Frank $100, Ma's trust drops, Frank's open debt is marked fulfilled, a commitment is
     recorded, and a raw record_changes update re-sets a business's state
snap = state_of(conn, ["money_records totals", "relationships", "obligations", "commitments", "businesses"])
rollback.undo_scene(conn, s3)
assert state_of(conn, ...) == snap_before_s3 and cash(me) == cash_before_s3     # money reversed by record
assert obligation(conn, frank_debt)["status"] == "active"                        # un-resolved
# out of order: scene 2 re-set the same business row after scene 1; undo scene 1 only
result = rollback.undo_scene(conn, s_first)
assert business_row_in(result["left"])                                           # later overwrite kept, reported
assert not record_changes_rows_for(conn, "relationships")                        # ties never double-logged
assert record_changes_count_after_weekly_tick(conn) == before_tick               # silent outside a context
```
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run it, then `--quick`** (checkpoint).
- [ ] **Step 5: Commit** `engine/rollback.py connector/correct.py engine/commitments.py tests/rollback_cascade_test.py`.

### Task 7: GM fault checker on real transcripts

Revision 5.2: no scripted bench. The owner's real playtests are the test, and this tool reads them.

**Files:**
- Create: `tools/gm_check.py`
- Test: `tests/gm_check_test.py`

**Interfaces:**
- `gm_check.py <transcript.txt | session.jsonl> -> {"G1": [...hits], ..., "G5": [...], "ledger": [...]}`:
  - G1 to G5 by pattern, with the line of each hit;
  - from a session's tool calls, if present: every scene closed, no tool error left unanswered, and every refusal
    with an `owner_notice` followed by prose that tells the player;
  - revision 5.3, `--db <save.db>` (optional): each closed scene's stamps match the session's calls; every person given
    a part exists as a row; a lie stamped `true: false` left a `holds_true=0` belief with its hearers; anyone who
    walked out holds no beat after leaving. Revision 6.3: people named inside a `cutaways` block are prose, not
    scene people, and are not checked for rows. Grand plan round 2: a stamp by him that acts on a cutaway he has not
    been told (a `circle_reactions` row with `cutaway_day` set and `told_day` empty, and no `knowledge` row for him
    about it) is a hit. Revision 6.4: the same for the wider cutaways: a `knowledge` row or media item with
    `cutaway_day` set, about which he holds no `knowledge` row of his own, acted on in his stamp, is a hit.
  - grand plan round 3 (former F-6, the intake design's tripwire, §7.5): with `--db`, each open thread the GM's
    recap names (a debt, a promise, a meeting, a plan under way) must have something held behind it: an obligation,
    a concern, a venture, a scheduled effect, a pending decision or a stamp. One with nothing is a hit.

- [ ] **Step 1: Write the failing test** on three canned transcripts: one with a numbered menu (G1 hit), one asking
  the player what the bartender's name is (G2 hit), and one clean (no hits). Add a session where a refusal is
  swallowed silently (a ledger hit), and a small save where a named extra is missing (a `--db` hit). Add a small
  save where he confronts a man about something he saw only in a cutaway (a `--db` hit), and a recap that
  promises "Frank's money is due Friday" with no obligation behind it (a `--db` hit).
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run it on `docs/playtests/2026-11-25-dominic-2.txt`.** Expected: hits on the faults the owner named.
- [ ] **Step 5: Commit.**

---

## Phase C: build step 3 (slice 2a, the GM–engine loop)

### Task 8: Consequence facts in tool results

**Files:**
- Create: `engine/answers.py`
- Modify: `connector/acting.py`, `connector/money.py`, `connector/authoring.py` (call `answers.judge` after a
  successful change, and add `answers` to the result. Nothing is stored and there is no `rationale` (revision 5.2))
- Modify: `connector/server.py` (a refusal carries `owner_notice`: one plain line the GM tells the player when the
  engine and the GM's proposal disagree)
- Modify: `worlds/saintjude/levels.json` (`answers`: the cash share only)
- Test: `tests/engine_answers_test.py`

**Interfaces:**
- `judge(conn, tool, actor_id, change) -> list[{"kind": "consequence", "text": str}]`. It states a fact when an act is
  weighty:
  - money above the `answers` share of his cash;
  - violence, or an act that is a crime;
  - an act against an outfit's man or territory;
  - breaking a live obligation, which it names.

  It never judges the act, and it never blocks.

- [ ] **Step 1: Write the failing test:**
```python
out = server.act("x1", "attack", "he beats Sal Ferrante", target_actor_id=sal_an_outfit_man)
assert any("Ferrante" in a["text"] for a in out["answers"]) and out["status"] != "refused"   # a fact, not a veto
quiet = server.money("x3", "pay", {"to": "Frank Moretti", "amount": 5, "what": "coffee"})
assert "answers" not in quiet                                                          # ordinary stays ordinary
r = server.author("x4", "person", {"name": "Tullio Bruni", "role": "owns the Starlite"})  # contradicts the record
assert r["status"] == "refused" and r["owner_notice"]
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus touched modules, commit.

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
  `standing_of(conn, kind, id, attribute) -> dict | None`. (`infer` waits for step 8: revision 5.3.)

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
- Modify: `engine/scenes.py` (`news_gate.deliver` in `close`), `engine/information.py` (the `information` slot runs
  `news_gate.spread` whatever `rumour_broadcast` says), `connector/money.py` (`visible_spend`) and
  `engine/civic_tick.py` (his public civic acts start spread rows). Revision 5.4.
- Modify: `worlds/saintjude/levels.json` (`news_paths`: which everyday channels he has by default and what each carries.
  Revision 5.9: each channel also has a `kind`, `media` or `talk`. Saint Jude's first channels: `paper`, `radio`,
  `television` and `magazine` as `media`; `work`, `parish`, `street`, `bar` and `union` as `talk`.
  The validator refuses a `knowledge.channel` that is not a `news_paths` key.)
- Test: `tests/news_gate_test.py`

**Interfaces:**
- Produces:
  - `reaches(conn, me, start_day, end_day) -> list[{"text", "path", "via", "firsthand", "why", "floor"}]`;
  - `held_for(conn, me, carrier) -> list[...]` (what a carrier holds for him, shown in the scene brief when the carrier
    is present).
  - `spread(conn, day) -> int` (revision 4.1): a knowledge row with `spread_from_day` set travels outward. That
    covers his deeds from a closed scene, and anything a witness saw. The first hop is to the holders' close ties and
    workmates, chosen by the same path rules. The package sets the delay per hop, the drop-off and the chance of a
    detail changing (`news_paths.spread`). A changed detail is a new row with `holds_true=0`. Every row reached feeds
    `claims` impressions of the person it is about. It runs on the `information` process slot, whatever
    `systems.rumour_broadcast` says (revision 5.2).
  - Revision 5.2:
    - **Visible success travels too.** These start spread rows with him as their subject: a purchase above the
      package's `visible_spend` line (`connector/money.py`) and his public civic acts (`engine/civic_tick.py`).
      Revision 5.3: a sustained rise in his business's work is added in Task 18c, where growth is first measured.
      Test: a big purchase and a council vote each leave a spread row about him.
    - **He sees himself in the news (revision 5.7).** A deed of his at or above the public line (a civic act, a
      major purchase or acquisition, a scandal) also becomes an item on the paper, radio or television he has, so
      it reaches him like any city news. `news_paths` gains `television`. Test: his council vote is on his evening
      news.
    - **One writer for public media (revision 5.9).** `publish_media(conn, day, channel, text, *,
      subject_actor_id=None, chain_id=None) -> int` writes a public item on a `media` channel, and `reaches` delivers
      it. Every caller that puts something in the paper, on radio or on television (`connector/money.py`,
      `engine/civic_tick.py`, the ordered-act and crime path in Task 10b, `engine/offscreen.py` in Task 17b) uses it.
      Test: a big purchase and a fired buy-out offer both arrive as items on his paper through `publish_media`.
    - **Hooks:** this task adds `news_gate.deliver` to `scenes.close`.
    - **Skips:** in `connector/timeflow.py`, a skip stops for floor items and `waiting_on_you` matters. Otherwise it
      runs through.
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
- Revision 4.2, atmosphere: the paper and radio he has carry a few public items a day whatever their relevance,
  marked `atmosphere`, up to `news_paths.atmosphere_per_day`. They are colour for the GM, never floor items.

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
# revision 4.1: his deed travels outward, and changes on the way
fight_in_scene(server, me, beats="Sal Ferrante in the Starlite"); run_days(conn, 21)
assert knows(conn, sals_cousin, "fight") and not knows(conn, stranger_across_town, "fight")
assert impression(conn, about=me, audience=sals_crew) != impression_before
assert any(r["holds_true"] == 0 for r in knowledge_rows(conn, "fight"))     # some tellings change
# a skip stops for something serious or needing his decision, and runs through otherwise
assert skip_stopped_by(server, days=30, cause=mother_badly_ill) and not skip_stopped_by(server, days=30, cause=None)
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick` (update `connector_advance_test` expectations only
  where the gate deliberately changes them, and say which in the commit), commit.

### Task 10b: Every side door onto the gate

All doors are in Deploy 1 (revision 4): without crime and civic news on the paper and radio, the city goes quiet
for him.

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
- Modify: `engine/player_operations.py` (revision 5.7: an act he orders (`order`) is a crime on record with his
  men as the offenders and him as the one who ordered it. The truth is held only by those in on it. Revision 5.9:
  an order can happen outside a scene, so `player_operations` writes those `knowledge` rows itself (`holds_true=1`,
  `path_kind='self'`) for him and the men he ordered, and nobody else, with no stamp. `crime_response`,
  `conduct.lies` and `spread` work from those rows. Test: an ordered attack opens a `crime_response` case naming
  his men, and only the conspirators hold that he ordered it.)
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
assert claims_moved_for(conn, offscreen_hit_victims_outfit)                  # reputation still moves offscreen (5.2)
```
- [ ] **Step 2 to 5:** run (FAIL), implement door by door, run with `--quick`, commit per door.

### Task 11: Brief and change-based read budget

**Files:**
- Create: `connector/brief.py`
- Modify: `connector/views.py` (`compact_scene` builds on `brief.full`), `connector/store.py` (`note kind=scene`
  returns `brief.full`), `connector/timeflow.py` (after a skip, return `brief.full` in place of the separate blocks),
  `connector/server.py` (results of `act`, `money`, `note` during an open scene carry `brief.changed`)
- Modify: `worlds/saintjude/levels.json` (revision 6.4: `cutaways.floor`)
- Modify: `engine/texture.py` (`block` no longer puts `claims.cutaways` inside `outside_his_knowledge` in the brief)
  and `connector/timeflow.py`, `connector/server.py` (grand plan round 2: `advance` and `close_scene` results carry
  a `cutaways` field from `claims.cutaways`)
- Modify: `engine/outings.py` (`go_out` returns who is really there (`crowd`, built on `routines.where` and the
  place's population) and the place's character. Revision 5.2: plus one to three facts already true about people
  in the crowd: a regular's live concern, a rival crew's man in the room, an open tie to him, payday. The happenings
  draw, `you_may` and `approach` are deleted, and the GM invents the night)
- Modify: `engine/findings.py` (where the record is silent, `answers` returns `unknown` and the GM may invent)
- Modify: `connector/views.py` and the tool results it shapes (facts and numbers in fields, not engine-written
  sentences; keep the wording the GM needs to know what a fact is, nothing more)
- Modify: `engine/player_operations.py` and `connector/acting.py` (revision 6.7: `act` results give every sum as a
  dollar number in `amount` and `short_of`, with the scale word allowed beside it; the summary becomes plain
  facts, who paid whom what. The module header's "amounts leave this module only as scale words" goes. Today
  `act(pay)` returns `"amount": "modest"`, so the GM has to invent the figure the rulebook says must agree with
  the engine)
- Modify: `connector/acting.py` and the `act` description in `connector/server.py` (revision 6.7: with
  `outings.approach` deleted, `act(outing)` with a target puts that person in his company for an ordinary scene;
  the description loses `details.move talk|dance|number|leave together`)
- Test: `tests/brief_budget_test.py`

**Interfaces:**
- Produces:
  - `full(conn) -> dict`, keys in this order: `waiting_on_you`, `you` (revision 4.1: his injuries and health,
    police interest in him, debts both ways, grudges he knows of, open promises and meetings, each with since
    when; revision 5.1: what he runs, such as his businesses, his outfit or his office, with the people under him,
    their state and his rivals' known moves, kept to a few lines and only what changed since his last closed
    scene (revision 5.3: a day window, since the brief keeps no cursor)),
    `present` (per person: name, body, manner,
    temperament in words, tie to him in words, `on_their_mind` (at most three live concerns in plain words, the strongest first by `strength`), `about_to`
    (pending decisions that involve this scene or him), `has_news_for_you` (from `held_for`)), `crossing_your_path`
    (arrivals, visits, matters due within 7 days that involve him), `news`, `money`, `texture`;
  - `changed(conn, call_effects) -> dict`: only what this one call changed. There is no cursor, since MCP calls hold
    no state between them. Bringing someone in or seeing them leave adds or removes their `present` entry.
  - `full` is read-only. `has_news_for_you` lists a carrier's items not yet delivered, or delivered in this open
    scene, so `resume` and a second brief show the same thing. Delivery happens at `close_scene` (Task 4).
- Revision 5.2:
  - In a personal scene (no one under him present), the brief carries only urgent seat matters. The rest go in skip
    results and work scenes.
  - After a skip, `advance` returns `brief.full` plus its skip-only fields: `nominations`, `chances`, `settled`,
    `done_by_his_people` and `history_due`.
  - Revision 5.3: this task defines `nominations`, `done_by_his_people` and the seat-matter filter with empty
    defaults. Tasks 14a and 14c fill them.
  - Grand plan round 2b: `you` also lists his open ventures (stage, what is pending, who is in it, the next due
    day), so a long project is visible while it is unfinished. Test: a venture in its approval stage shows in `you`.
  - Revision 5.7: the brief (inside `you`, revision 5.9, so the first three keys stay put) and `outings.go_out`
    carry `standing_here`, one short line on how this place and its
    people see him. It is taken from `claims` impressions for the district or crowd, his public office or seat,
    and spending above `visible_spend` within 30 days. Test: after a big public purchase, the restaurant's
    `standing_here` names it.
- Nothing about people not present, and nothing building elsewhere, appears in either. The owner's rule
  (2026-11-26): the GM sees only what is nearing the protagonist (`crossing_your_path`); the old "outside his
  knowledge" part goes. Owner, 2026-11-27: cutaways come back (grand plan F-10, built here since round 2). They
  are their own field, `cutaways`, on `advance` and `close_scene` results only, never in `brief.full` or
  `brief.changed` during an open scene. Each is I1a's existing item: what his people met about a significant
  happening that touches him, which he was not there for and has not been told, with its "outside his knowledge"
  note. `claims.cutaways` already marks each one shown, so it appears once. Revision 6.0: a cutaway is a
  reaction to what he did or how he is seen (today `circle_reactions`, which is exactly that), never a pending
  decision, plan or nomination aimed at him. Test: a rival's pending decision against him never shows in
  `cutaways`. Revision 6.1 (owner): cutaways are wider than his circle. They also draw on how anyone meets what is
  public or visible about him: the `spread` rows and `publish_media` items about him (Task 10a) as people take them
  in, such as strangers seeing him pull up in a sports car with security, a bar watching him on the news, men talking
  about his sentence or what he is worth. Each `advance` or close result carries the few most significant (by the
  item's loudness and how near the people are to him), each once. Still reactions only. Test: after a big public
  purchase and a skip, `cutaways` holds a stranger's reaction to it. Revision 6.3: shown once is held on the
  `knowledge` row of the person who took the item in (`cutaway_day`, a schema 134 column, Task 3), and for a media
  item on the row `publish_media` writes (revision 6.4), since a broadcast has no single taker; a package
  floor (`levels.json` `cutaways.floor`, by loudness) means an ordinary week returns none. Test: a quiet week's
  skip returns no `cutaways`; a second skip doesn't repeat the purchase.

- [ ] **Step 1: Write the failing test:**
```python
b = server.note("s1", "dinner at the Morettis'", kind="scene", present=["Aurelio Moretti"])["brief"]
assert list(b)[:3] == ["waiting_on_you", "you", "present"]
assert "Aurelio" in dump(b["present"]) and "Tullio" not in dump(b)        # Tullio's plans aren't in the room
assert len(dump(server.money("p1", "pay", {...})["changed"])) < 600        # per-call changes stay small
assert not leak_words(b, ["concern", "pressure", "score", "engine"])       # no machinery
assert "outside_his_knowledge" not in dump(b) and "cutaway" not in dump(b)       # not in a mid-scene brief
circle_reaction_away_from_him(conn, me)                     # grand plan round 2: his wife hears of it at church
r = server.advance("p1", days=1)
assert r["cutaways"] and "outside his knowledge" in dump(r["cutaways"])
assert not server.advance("p2", days=1).get("cutaways")     # shown once (its own call id, so no replay)
# revision 6.7: sums in dollars; no outing approach roll
r = server.act("q1", "pay", "he pays Frank for the parts", target_actor_id=frank, details={"amount": 120})
assert r["amount"] == 120 and "modest" not in r["summary"]
r = server.act("q2", "outing", "he goes over to talk to her", target_actor_id=carla)
assert r["status"] == "applied" and "outcome" not in r and company.is_with(conn, me, carla)
injure(conn, me, "broken hand"); owe(conn, me, frank, 200)
b = brief_full(server); assert "broken hand" in dump(b["you"]) and "200" in dump(b["you"])   # it lingers
assert "you_may" not in dump(server.act("p1", "go out", {"place": "the Starlite"}))   # no menu of moves
assert not happenings_in(server.act("p1", "go out", {"place": "the Starlite"}))       # the GM invents the night
assert findings_answer(server, "does the supplier have a wife?")["status"] == "unknown"
assert prose_share(b) < 0.2                      # fields, not sentences (lead sets the bound from the first run)
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 12: Storyteller rulebook

**Files:**
- Modify: `connector/rulebook_core.md` (rewrite as the principles of design section 4, each with one short playtest
  example from `docs/playtests/2026-11-25-dominic-2.txt`, plus how to use scenes, stamps, `close_scene`, canon by kind,
  consequence facts and `owner_notice`. Turning events are taught in Task 15)
- Modify: `worlds/saintjude/rulebook_section.md` (Saint Jude's own examples, if any principle needs one)
- Modify: `engine/free_operation.py` and `connector/acting.py` (revision 6.7, the engine side of "never refuse an
  ambition because nothing models it": `free_operation` sorts an intent into one of 15 kinds by keyword, and
  today anything that matches none is refused as "not something the engine can carry out yet", with a reason
  that tells the GM to rephrase. A con, a forged document, a smear in the paper or a rigged fight is then forced
  into a wrong kind or played unrecorded. It now returns `status: "unmodelled"`, nothing applied, naming the
  record path: a scene stamp with `known_to` for what was done and who knows, `money` for any sum, `author` for
  anyone new. The keyword list stays, and the GM's `kind` hint still overrides it. Test: `act("operation", "he
  has a forger make up a new title deed")` returns `unmodelled` with the record path, not `refused`; the rulebook
  line under the round 2b rule says to follow it)
- Test: `tests/connector_resume_test.py` (update the rulebook expectations it pins)

- [ ] **Step 1:** Rewrite. The rulebook holds only:
  - the storyteller principles, each with one example;
  - a scene lifecycle of five lines or so: open with `note(kind="scene")`; stamp what can't be undone; close with
    `close_scene` before moving on or skipping; `from_stamps` when there's nothing to add; `resume` returns an open
    scene.

  - the division of labour (design section 0), and four rules from the owner's brief: tell the owner when you
    and the engine disagree, and let him rule; play nominations within the timeframe you set; the first woman,
    customer or fight is not special by default; record what you invent that should last;
  - revision 4.2: look for opportunities in what the world already holds (a rival in trouble, a man out of work)
    without inventing their causes; record only meaningful changes, since an ordinary evening needs only a close;
    use the paper, the radio and gossip for atmosphere, not only for plot;
  - revision 5.1: never push him to rise. A quiet life, holding what he has, and staying ordinary are all valid
    stories; his circumstances set the scale of what happens, from rent and friends to rivals and elections;
  - revision 5.2: an `owner_notice` is always told to the player in plain words. Ordinary people behave
    ordinarily: most customers pay on time, and a late or bad payer is an exception with a reason;
  - grand plan round 2b: never refuse an ambition because nothing models it, and never make it cheap. Ground the
    obstacles in the era (the market, the money, rival cities, the league's politics), record the real actors,
    commitments and money, and let the world push back over time;
  - grand plan round 2: a cutaway is written as a cutaway, marked as away from him, and he acts only on what
    reaches him through the world;
  - revision 5.7: settle any scheme the player tries with the existing tools (`act`, stamps with `known_to`,
    `author`) without waiting for a special mechanic. Play business ripples (staff poached, suppliers' terms,
    struggling rivals) out of his business state in the brief.

  Parameter shapes and modes go in the tool docstrings (`note`, `close_scene`, `author`), where the GM reads them at
  call time. Principles, not rules per symptom.
- [ ] **Step 2:** `--quick`. Expected: PASS.
- [ ] **Step 3: Commit.**

### Task 13: Slice 2a checkpoint (lead)
- [ ] The lead plays a short session on a fresh save, runs `gm_check.py` on it and reads it against the Task 1
  checklist. Fix rounds go to the owning task's
  files.
- [ ] Review P2.32 to P2.37 (commits up to `dc448e9`) against the design: list each fix as kept, folded in, or to be
  dropped. Dropping code needs the owner's yes.
- [ ] Report to the owner before Phase D.

---

## Phase D: build step 4 (slice 2b, a minimal living world)

### Task 14: Nominations, consistency and agency guards (built as 14a, 14b and 14c)

Revision 5.2 splits this task into three sessions, in this order:
- **14a:** `near`, the nomination functions, `levels_tick.py`, the life-module hooks, and invented people who go on
  living. Files:
  - `engine/nominations.py`, `engine/levels_tick.py` and `engine/simulation.py`;
  - the life modules listed below;
  - `connector/server.py` (`note(kind="plan")`, `realizes` on `author` and `close_scene`, and seeding a person on
    `author` or `realize`; revision 6.7: 14c routes `seat_decision` matters through the existing `act` answer);
  - `connector/brief.py` and `connector/timeflow.py` (fill `nominations`);
  - the `nominations` block of `worlds/saintjude/levels.json`.

  Test lines: up to the consistency check, plus the budget lines and Teresa's.
- **14b:** `conduct.py`, broken promises and lies found out. Files: `engine/conduct.py`, `engine/scenes.py`,
  `engine/levels_tick.py` (register its steps) and the `conduct` block of `levels.json`. Test lines: the revision 4.1
  ones.
- **14c:** agency guards and seat decisions. Files:
  - `connector/acting.py` and `connector/server.py` (revision 6.7: `_answer` sends a `seat_decision` matter to
    `nominations.realize`; the `act` description says so);
  - `engine/nominations.py` (revision 6.4: `realize` hands a `seat_decision` answer to its path; `apply_overdue`
    lapses one);
  - `engine/org_succession.py`, `engine/org_coup.py` and `engine/crime_response.py`;
  - `engine/org_choices.py`, `engine/outfit_choices.py`, `engine/org_money.py` and `engine/org_happenings.py`;
  - `engine/business.py` (`process_due_businesses`). `merchant.py` is not hooked: Saint Jude does not run it
    (`merchant_houses` is off; revision 5.4);
  - `engine/civic_tick.py` and `engine/civic_votes.py` (grand plan round 5: `member_vote` and `_count` cast a
    seated protagonist's vote from his lean today. His vote is a `waiting_on_you` matter before `vote_day`, and
    with none given he is counted `absent`);
  - `engine/prison_review.py` (grand plan round 5: `weekly` files appeals and pardons by chance for every serving
    man; it skips the protagonist, who files by his own act, grand plan F-14);
  - `engine/prison.py` (grand plan round 6: `admit` calls `assign_group` for every inmate. For him it doesn't
    place him; the group it would have picked becomes a nomination, an approach the GM plays, and he joins only by
    his own act, grand plan F-14);
  - `connector/brief.py` (fill `done_by_his_people` and the seat-matter filter);
  - the `delegation` block of `levels.json`.

  Test lines: the agency-guard line and the revision 5.1 ones.
  - Revision 5.7: when he belongs to an outfit, an event from `org_happenings` or `outfit_choices` that the
    public hears of also gives a crewmate tied to him the insider version (who, which family, why) as
    `pending_news`. Test: a hit by a rival family reaches a boss start with the families named, and a mechanic
    start gets only the paper's line.

Task 14d, below, is starts at any scale.

Replaces the protection lock (design section 0, approved 2026-11-27). Life near him goes on at realistic rates. The
engine nominates, the GM realizes and the engine ratifies.

**Files:**
- Create: `engine/nominations.py`
- Create: `engine/levels_tick.py` (revision 5.2, in 14a: process key `levels`, weekly, registered in
  `engine/simulation.py` after `life_matters`. `process_due` runs `levels.refresh`, `nominations.apply_overdue`,
  and from 14b `conduct.weekly`, `conduct.lies` and overdue promises. Later tasks add their steps to it.
  Revision 5.4: it also clears stated decisions from scenes once their due day has passed. One that involves him
  becomes a `waiting_on_you` matter. Any other is marked `lapsed`. Task 17b later fires them instead.)
- Modify: `engine/life_matters.py`, `engine/outings.py` (offscreen flings and scuffles), `engine/opening_family.py`
  (`resolve_unnamed_marriages`), `engine/household_life.py` (planned births), `engine/civilian_life.py` (a grown
  child nobody knew of), `engine/temptations.py` (`_others`), `engine/org_happenings.py`: a draw that touches someone
  `near` him becomes a nomination; a draw on anyone else applies as today. Revision 6.3: this holds for the active
  too, close kin and distant movers alike; nothing skips a person for being active. A draw applied directly
  records its cause (the draw's kind and rate), so C1's "every level-3 event has a cause" holds for them
- Modify: `engine/org_succession.py`, `engine/org_coup.py`, `engine/crime_response.py` (agency guards: never vote,
  spend, plot, defect or plead for the protagonist)
- Modify: `connector/server.py` and `connector/brief.py` (`nominations` in `brief.full` and in the skip result;
  `note(kind="plan")`; `realizes` on `author` and `close_scene`)
- Create: `engine/conduct.py` (revision 5: outstanding matters from remembered facts, and lies found out)
- Modify: `engine/scenes.py` (a thread past its date, unmet, becomes a broken promise on the record)
- Modify: `worlds/saintjude/levels.json` (`nominations`: default and longest timeframe, reminder lead, weekly
  budget and weight per kind; `conduct`: quiet days by closeness, and how long a wrong waits before it surfaces)
- Test: `tests/nominations_test.py`

**Interfaces:**
- Produces:
  - `near(conn, day) -> set[int]` (revision 4.2: relevance, not proximity): the people active because they are close
    to him (`close_rule`; revision 6.2: a mover active only by his seat, with no tie to him, is not near and acts on
    his own), his household and kin, his ties and recurring connections, anyone who dealt with him in a scene within `lock_quiet_days`
    (named in a stamp or given a part, not merely present), and anyone involved in an event that affects him.
    Someone only at the same place is not near.
  - `nominate(conn, kind, actor_ids, cause: str, payload: dict, chain_id=None) -> int`. `payload` holds what
    `apply_overdue` needs: the partner, the destination, the illness (revision 5.2).
  - `plan(conn, nomination_id, by_day, text) -> None` (the GM's timeframe; refused past the package's longest).
  - `decline(conn, nomination_id, reason) -> dict` (refused without a reason that names something in the record).
  - `realize(conn, nomination_id, change: dict) -> dict` (checked like any authored change; contradictions refused).
  - `due(conn, day) -> {"new": [...], "remind": [...], "overdue": [...]}`.
  - `apply_overdue(conn, day) -> list[int]`: past `by_day` (or the default timeframe if no plan), the engine applies
    the development in a plain form through the same path the draw would have used. Revision 6.3: never for
    `kind == 'seat_decision'`. Past its date that matter is marked lapsed and its path told he gave no answer (a
    vote counts him absent); nothing is done in his name. Test: an overdue seat matter on an outfit hit leaves no
    hit and the nomination `lapsed`.
- **Consistency:** nothing the engine applies may contradict what a scene established (`scene_stamps`, recorded
  ties, standing). Where it would, it becomes a nomination instead.
- **Agency guards:** the engine never chooses the protagonist's acts.
- **Seat decisions are his (revision 5.1).**
  - Every code path that chooses for a seat holder checks whether the holder is the protagonist:
    - `org_choices` and `outfit_choices` (rackets, hits, discipline, recruitment);
    - `org_money` spending;
    - `org_happenings`;
    - business decisions (`business.process_due_businesses`);
    - `civic_tick` votes, appointments and deals.
  - Where it is him, a decision the package marks his own (`delegation` in `levels.json`: money above a share of
    the seat's funds, violence, membership, votes and deals) becomes a `waiting_on_you` matter, with a timeframe
    like a nomination.
  - Revision 6.2, answering it: the `seat_decision` nomination's payload names the code path that asked and what
    it needs (the item for a vote, the choice for an outfit or business decision). `realize(nomination_id,
    {"choice": ...})` hands his answer back to that path: a vote is recorded through `civic_votes`, an outfit or
    business choice runs through the existing `execute_*` handler or `business` path. The GM sees the matter in
    plain words and passes what the player said, never a menu. An answer that fits nothing the path holds becomes
    his `stated` decision (Task 17b). Unanswered by its date, `apply_overdue` decides nothing for him: a vote
    counts him absent, and the seat goes on as it was. Test: a seated councilman answers "no" through
    `realize` and the item's count holds his no; an outfit choice he answers runs the matching handler.
  - Revision 6.7, the connector path (replacing 6.5's `note(kind="answer")`): the existing
    `act(action_type="answer", details={"matter": id, "answer": ..., "how": ...})` already answers any
    `waiting_on_you` matter through `life_matters.answer`. In `connector/acting.py` `_answer`, a matter that is a
    `seat_decision` nomination goes instead to `nominations.realize` with `{"choice": how or answer}`, so the GM
    can answer straight after a skip or mid-scene, in the player's words. Test:
    `server.act("a1", "answer", "he votes no", details={"matter": n, "answer": "no"})` and the item's count
    holds his no; a life matter answered the same way still goes to `life_matters.answer`.
  - Routine running goes to his second or manager. If he has none, the seat keeps going as it was. Each such act is
    listed in the skip result as done by them.
- Revision 4.1:
  - **`conduct.weekly(conn, day) -> list[int]`** (revision 5: facts and one rule, no build-up maths). For each
    person `near` him it reads facts already on record:
    - the day they last shared a scene, against the package's quiet days for their closeness (`neglect`).
      Revision 6.2: a day skipped with `advance` counts as shared time with whoever his routine puts him with that
      day (`routines.where` for both at the same place: his household at home, the regulars at his bar), unless an
      exception keeps him away (travel, custody, a stated long absence). Neglect comes from real absence, or from
      played scenes that leave someone out. Test: a five-week ordinary skip opens no `neglect` for his mother;
      five weeks away on a job opens one;
    - a wrong he did them, from a stamp (`wronged`);
    - a promise to them past its date and unmet (`broken_promise`);
    - news they hold of him with another partner (`jealousy`).

    One rule: a fact still outstanding after its package wait opens one nomination naming that fact. At most one open
    nomination per person; a later fact adds to its cause. How it shows, a sharp word or a cold dinner, is the GM's
    to play.
    Revision 6.5, each fact surfaces once: the nomination's `payload` lists the source keys of the facts in it
    (`stamp:<id>` for `wronged`, `obligation:<id>` for `broken_promise`, `knowledge:<id>` for `jealousy` and for
    `conduct.lies`, and `quiet:<person>:<day of the last shared scene>` for `neglect`). `conduct.weekly` and
    `conduct.lies` skip any fact whose key is in a nomination of any status, `realized`, `declined`, `applied`
    and `lapsed` included. A new absence after a shared scene has a new key, so neglect can come back; an old
    wrong can't.
  - **`conduct.lies(conn, day)`:** for a `holds_true=0` belief that he caused, when a holder of the truth shares a
    household, routine place or scene with the believer, it nominates the discovery.
  - **Budget:** one table and one loop, with no scoring beyond the package weight per kind. Each week the GM gets
    nominations by weight up to the package budget. The rest, the small ones, the
    engine applies plainly at once and lists in the skip result as done. Weight comes from what a development
    touches: a tie to him, an obligation, his money, business or safety. Revision 5.2: routine changes (a new
    drinking place, a car bought) never become nominations. They apply as background life.
  - **Invented people live:** `realize` and `author` of a new person seed a routine, run `levels.refresh` for them,
    and give them a purse (as `life_matters.settle_circle` does) and a life profile.

- [ ] **Step 1: Write the failing test:**
```python
anthony = brother_of(conn, me)
force_draw(conn, "romance", anthony); n = nominations.due(conn, day)["new"][0]
assert n["actor_ids"] == [anthony] and n["cause"] and not life_matter_with(conn, anthony, "romance")  # nominated, not applied
nominations.plan(conn, n["id"], day + 30, "he meets her at his cousin's wedding")
assert nominations.due(conn, day + 25)["remind"]                            # reminded inside the window
assert nominations.realize(conn, n["id"], {"partner": "new", "name": "Teresa Lauro", "age": 23})["accepted"]
assert actor_named(conn, "Teresa Lauro") and tie(conn, anthony, "Teresa Lauro")
m = nominations.nominate(conn, "move_away", [cousin], "work in Newark")
run_days(conn, default_timeframe + 1); assert moved(conn, cousin)          # overdue: the engine applies it
assert not nominations.decline(conn, m2, reason="")["ok"]                  # a reason is needed
assert life_matters_still_applies_far(conn)                               # far from him the city runs as before
courting_in_scene(conn, me, carla); force_draw(conn, "union", carla, partner="stranger")
assert not married(conn, carla, "stranger")                               # consistency with the record
assert protagonist_plea(conn) is None and not voted_for_protagonist(conn)  # agency guards
seat_him_on_council(conn, me); item = open_item_due(conn, days=3); run_days(conn, 4)   # grand plan round 5
assert vote_of(conn, item, me) == "absent" and waiting_on_you_had(server, kind="seat_decision")
sentence_him(conn, me, years=10); run_weeks(conn, 20); assert not reviews_filed_for(conn, me)
assert inside_group_of(conn, me) is None and nomination_of_kind(conn, me, "inside_approach")   # round 6
# grand plan round 6, the hands-off test: one save per role (council seat, outfit soldier, business owner,
# serving inmate), 90 to 120 days with no call from him. Every row written with him as the actor is something
# that befell him, routine upkeep or payroll, or an act recorded as his second's or manager's
for role in ("councilman", "soldier", "owner", "inmate"):
    conn = start_as(role); before = his_rows(conn, me); run_days(conn, 120)
    assert all(r.kind in ("befell", "upkeep", "payroll", "delegated") for r in his_rows(conn, me) - before), role
# revision 4.1
no_scene_with(conn, me, girlfriend, weeks=5); conduct.weekly(conn, day + 35)
assert nomination_of(conn, girlfriend)["kind"] == "neglect"
promise_in_scene(server, me, to=brother, by=day + 3); run_days(conn, 5)
assert broken_promise_on_record(conn, me, brother)
lie_in_scene(server, me, to=mother, truth_known_to=[frank]); same_place(conn, frank_wife, mother); conduct.lies(conn, day)
assert nomination_of(conn, mother)["kind"] == "lie_found_out"
# revision 6.5: a fact surfaces once
n = nomination_of(conn, mother); nominations.realize(conn, n["id"], {"scene": "she confronts him"})
run_weeks(conn, 3); assert not nomination_of(conn, mother, status="new")   # the played-out lie isn't renominated
flood_near(conn, people=12); week = nominations.due(conn, day)
assert len(week["new"]) <= budget(conn) and applied_small(conn)             # the GM isn't buried
assert nomination_kinds_to_gm(week) >= {"romance"}
d = stated_decision_in_scene(server, frank, "he'll call round Friday", due=day + 4); run_days(conn, 8)
assert decision(conn, d)["status"] == "lapsed" or waiting_on_you_has(server, "call round")   # never stuck pending
force_draw(conn, "new_local_bar", anthony); assert applied_directly(conn, anthony, "new_local_bar") and not nomination_of(conn, anthony, "new_local_bar")
assert stranger_in_same_bar not in nominations.near(conn, day)                 # presence alone isn't relevance
teresa = realized_person(conn, "Teresa Lauro")
assert routines.where(conn, teresa, day, "day") is not None and has_purse(conn, teresa)   # she goes on living
# revision 5.1: his seat's decisions are his
seat_protagonist_as_boss(conn, outfit); run_weeks(conn, 4)
assert not hit_ordered_by(conn, me) and waiting_on_you_has(server, kind="seat_decision")
assert routine_acts_by(conn, his_second(conn, outfit)) and listed_in_skip_result(conn, "done by")
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus the tests of every modified module, commit.

### Task 14d: Starts at any scale (Deploy 1)

**Files:**
- Modify: `engine/new_character.py` (a start in a held seat: `veto.held_by_other` no longer refuses it at the
  opening. The holder is moved aside before day 0 through `real_figures` and the life paths, as retired, dead or not
  present in this save, with the reason recorded. He takes the seat with its people, history and obligations.)
- Modify: `engine/veto.py` (held seats refused during play as now, allowed only for the opening)
- Create: `tools/start_check.py` (the four-start check)
- Revision 6.8 (code audit finding 11), his outfit through the org core. Saint Jude's outfits run on the org core
  (`org_profiles`, `org_seats`, `org_units`, `org_money`); the old layer (`underworld_organizations`,
  `underworld_personnel`) is empty there. Yet every outfit path in his tools reads the old layer: checked on a
  Saint Jude save, `outfit:20` (the Eastside Combine) is refused as "unknown outfit 20". When the package runs the
  org core (`systems.outfits`), these paths use it; the old layer stays for Caerness:
  - Modify: `engine/ledger.py` (an `outfit:<id>` holder is an `org_profiles` organisation. Its purse is the one the
    org core already pays from, `org_money.purse_ref`: the living head's purse. `_check_exists`, `balance`,
    `_debit` and `can_draw` follow it, so a boss pays out of the outfit's money as the org core does);
  - Modify: `engine/player_operations.py`:
    - hiring into an outfit seats the man through `orgs.seat` at the role named, under the boss or the unit
      leader named;
    - promoting, retiring and expelling change his `org_seats` row the way the org core's own vacancies do;
    - `_my_outfit` reads his seat (`orgs.seats_of`);
    - a truce or alliance lowers the pair's `org_tension` and is recorded with the org core's deal records;
    - heat goes to `org_heat.add`;
    - the men behind an attack are his outfit's seated men;
  - Modify: `connector/store.py`, `connector/authoring.py` and `connector/views.py` (an outfit id is an `org_profiles`
    organisation; "who is in the life" reads `org_seats`);
  - the money-flow recorder `underworld_rebuild._record_economic_flow` stays where it is (O-9 moves it later).
- Test: `tests/start_scale_test.py`

**Interfaces:**
- **Moving a holder aside (revision 5.2):**
  - `retired`: he vacates the seat only, and his household, kin, debts and past stay.
  - `dead`: his death is dated before day 0, his estate passes by the package's inheritance rules, and his kin
    grieve.
  - `absent` (never in this save): allowed only when no kin, obligation or `lived_past` entry refers to him.
- `create_protagonist(conn, proposal, call_id)` accepts a held seat: an office, the head of an existing outfit, or
  the owner of an existing company. It returns the displaced holder and the reason in its account.
- First, probe what a large start gives today: a businessman with several companies and many employees. Report to
  the lead before changing anything for scale.
- `start_check.py --start <mechanic|businessman|politician|boss> --days 30 -> JSON`: a fresh save from
  `tests.sj_fixture` through `new_character`, then 30 days with routine acts. It reports:
  - the circle (kin, friends, colleagues) and holdings;
  - open matters;
  - nominations from his personal life;
  - the city's own events in the same days;
  - for a seat, the seat decisions sent to him;
  - revision 5.2: the three world measures (stored-cause share, events per kind, never-fired actions with the
    reason), in place of a separate scorer.

- [ ] **Step 1: Write the failing test:**
```python
r = create_protagonist(conn, {"concept": "head of the Basile family", "holdings": [{"kind": "outfit", "name": canon_outfit}]}, "s1")
assert r["displaced"]["reason"] and seat_holder(conn, canon_outfit) == me
assert members_of(conn, canon_outfit) == members_before and rivals_of(conn, canon_outfit)   # it keeps its history
assert create_protagonist(conn2, {"concept": "mayor of Saint Jude"}, "s2")["displaced"]
assert veto_refuses_during_play(conn, take_held_seat)                                        # opening only
for start in ("mechanic", "businessman", "politician", "boss"):
    s = start_check(start, days=30)
    assert s["circle"]["kin"] and s["circle"]["friends"]         # a personal life at every scale
    print(start, len(s["personal_nominations"]))                # revision 6.2: reported at 30 days, a quiet month is normal
    assert s["city_events"]                                      # the city moves
    assert start_check(start, days=120)["personal_nominations"]  # his life moves, over the hands-off window
    if start in ("politician", "boss"): assert s["seat_decisions"]
    assert not all_single(s["circle"]["friends"], age_band=(22, 30))  # a plausible opening (5.2)
    assert {"cause_share", "events_per_kind", "never_fired"} <= set(s["measures"])   # never_fired is [] until Task 17a
# grand plan round 2b: a counterpart outside the city survives refresh, routines and a skip
league = server.author("p1", "organisation", {"name": "a national league office", "place": "New York"})
rep = league_representative(conn, league); open_negotiation(server, me, rep, due_in_days=20); run_days(conn, 25)
assert waiting_on_you_has(server, "league") and levels.resolution_of(conn, rep) != "gone"
# revision 6.8: the boss runs his outfit through the org core
boss = start_as("boss"); outfit = his_outfit_id(boss)
before = org_money_rows(boss); r = server.act("b1", "pay", "he pays Sal for the job", target_actor_id=sal,
                                           details={"amount": 500, "from": f"outfit:{outfit}"})
assert r["status"] == "applied" and r["amount"] == 500                     # not "unknown outfit"
server.act("b2", "hire", "he takes Nicky on as a soldier", target_actor_id=nicky, details={"into": f"outfit:{outfit}", "role": "soldier"})
assert seat_role(boss, nicky, outfit) == "soldier"                            # an org_seats row, not underworld_personnel
t0 = tension(boss, outfit, rival); server.act("b3", "demand", "he offers the Greco crew a truce", target_actor_id=greco_head)
assert tension(boss, outfit, rival) < t0 or waiting_on_you_has(server, "truce")   # agreed, or their answer is pending
assert count(boss, "underworld_personnel") == 0 and count(boss, "underworld_organizations") == 0
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus touched modules, commit. The lead reads the
  four reports, and `start_check.py` runs again before Deploy 2.

### Task 15: Channels, shocks, delayed effects and turning events

**Files:**
- Create: `engine/channels.py`
- Modify: `connector/authoring.py` (`kind="turning_event"`)
- Modify: `engine/rollback.py` and `connector/correct.py` (`undo_chain`, moved here from Task 6), and
  `connector/rulebook_core.md` (how to use turning events)
- Modify: `worlds/saintjude/levels.json` (`shocks`; grand plan round 2b adds `demand_up`, a good-news shock: a big
  opening lifts demand at nearby businesses through `exposure_links`, which can open `opportunity` concerns for their
  owners in Task 16. Test: an opened venture with a large budget lifts a neighbouring bar's demand)
- Revision 4.1: `exposure_links` gains the kind `competitor` (same trade, same district). His own businesses and his
  crew are channels attached to him, so a shock to them reaches him. Revision 5.5: the shock that moves demand from
  his competitors when his business takes work is built in Task 18c, where demand is built.
- Revision 5.5: `channels.run_due_effects(conn, day) -> int` carries out due `scheduled_effects` rows through the
  same paths as `publish`, on their chains. Task 16 calls it from `levels_tick`.
- Revision 5, reuse first: `attached` reads the tables that already hold the links (businesses and employment,
  outfit membership and rackets, households, loans and `money_records`), and `exposure_links` holds only what
  none of them records. Effects go through the existing money, ledger and `claims` paths.
- Test: `tests/channels_shocks_test.py` (also: a delayed effect on the bakery's chain runs on its due day through
  `run_due_effects`)

**Interfaces:**
- Produces:
  - `attached(conn, channel_kind, channel_id) -> list[(actor_id, link)]`, where `link` is one of `employee`, `owner`,
    `member`, `resident`, `regular`, `debt`, `supplier`, `protection` or `customer`;
  - `publish(conn, shock_id) -> list[{"actor_id", "effect", "felt": bool, "knows_cause": bool}]`. A felt effect changes real
    state (money, takings, demand) through the existing paths (revision 5.2). Knowing the cause takes a path: he is the owner, or someone told
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
  consequence note. Commit: a `causal_chains` row (`origin_kind='turning_event'`), then `channel_shocks`, then
  `publish`.

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
assert same_chain_via_record_changes(conn, sid, takings_change(conn, bakery))        # the real state change
out = server.author("t1", "turning_event", {"channels": [{"kind": "business", "name": "Rizzo's Bakery"}],
                                            "shock": "fire", "summary": "a kitchen fire closes Rizzo's for a month"})
assert chain_of(out)["origin_kind"] == "turning_event" and pending_effects(conn, chain_of(out)["id"])
assert server.author("t2", "turning_event", {..., "channels": [{"kind": "business", "name": "No Such Shop"}]})["status"] == "refused"
assert any(a["kind"] == "consequence" for a in server.author("t3", "turning_event", {second fire, same street})["answers"])
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 16: Pressure build-up and concerns

**Files:**
- Create: `engine/pressure.py`
- Modify: `engine/levels_tick.py` (from Task 14a: add `pressure.build` and `channels.run_due_effects`)
- Modify: `worlds/saintjude/levels.json` (`pressures`: `cash_strain` from cash against weekly household need
  (revision 6.3: the cash he can draw on, `ledger.can_draw` over his purse and the businesses or holdings he owns,
  so an owner with a healthy business isn't strained); `work_restless` from time in the same work at a low wage
  relative to his trade (revision 6.3: only for a man on a wage, never a seat holder or an owner living on profit
  or tribute); `office_threat` for office
  holders, from a challenger's standing and the next election's date. Revision 5.8: `opportunities`: the cash
  line, as weeks of the business's costs, and the struggling line for a rival)
- Test: `tests/pressure_buildup_test.py`

**Interfaces:**
- Produces:
  - `build(conn, day, actor_ids) -> list[concern_id]` for active people (revision 5: a plain package line, no
    accumulator). Each week it reads the existing values (cash against need, weeks in the same low-paid work, the
    challenger's standing). When a condition has held past the package's line, it opens a concern with
    `origin_kind='buildup'` and an `origin_text` naming the condition and how long it has held ("four months short
    of the rent"). People differ only through what is already recorded about them: savings, kin who can help,
    temperament in `actor_drives`.
  - The concern closes when its condition is gone. No cooldowns, adaptation, resignation or mood.
  - Revision 5.8, opportunity: for an active owner of a business, `build` also opens a concern with
    `origin_kind='opportunity'` when the business's cash stands above the `opportunities` cash line, or a business
    in the same trade and district is below the struggling line. The `origin_text` names it ("money to spare,
    and Rizzo's is struggling"). It closes when the condition is gone, like any other.
  - Revision 5.9, acted on once: each opportunity concern names its chance (the struggling business, or the cash
    itself), and there is at most one live or waiting concern per chance. Once a decision on it fires, the concern
    is `resolved`. A new one opens only for a new chance: another struggling business, or cash that fell below the
    line and rose above it again. No waiting period.
  - Revision 6.4, how the chance is held: the cash episode is the `actor_pressures` row for the opportunity domain,
    whose `since_day` is when cash rose above the line; the row is deleted when cash falls below it. No new
    opportunity concern opens while a concern for that chance, of any status, `resolved` included, has
    `opened_day >= since_day`. A struggling business is its own chance, keyed by the business.
  - `levels_tick.process_due` (Task 14a) gains `pressure.build` and due `scheduled_effects`. Task 17b adds
    `offscreen.fire_due`.

- [ ] **Step 1: Write the failing test:**
```python
for p in ten_close_people_same_age_and_cash(conn): starve_cash(conn, p)
weeks_to_tip = run_weeks_until_concern(conn, people, max_weeks=40)   # same cash, different savings and kin
assert len(set(weeks_to_tip.values())) > 1                  # what is on record about them makes the difference
c = concern(conn, people[0]); assert c["origin_kind"] == "buildup" and "month" in c["origin_text"]
pay_rent(conn, people[0]); run_weeks(conn, 1); assert concern(conn, people[0])["status"] == 'resolved'
assert not concerns_for(conn, a_materialized_minor)        # only level 3 builds this way
fill_cash(conn, big_business_owner); run_weeks(conn, 2)    # revision 5.8
assert concern(conn, big_business_owner)["origin_kind"] == "opportunity"
fire_decision_on(conn, big_business_owner); run_weeks(conn, 8)          # revision 5.9: still rich, nothing new
assert count_opportunity_concerns(conn, big_business_owner) == 1
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 17a: Offscreen weighing

**Files:**
- Create: `engine/offscreen.py` (`weigh` only)
- Modify: `worlds/saintjude/levels.json` (`actions`: first contents `seek_income`, `ask_loan`, `call_in_debt`,
  `avoid`, `confront`, `pressure_business`, `make_offer`, `settle`, `do_nothing`; revision 5.8 adds `expand`,
  `buy_out` and `propose_alliance`, which serve `opportunity` concerns. Revision 5.9: `buy_out` needs a struggling
  business in the concern; `expand` needs the cash. Grand plan round 3 (former F-4): `seek_payment`, for an office
  holder under `cash_strain`, needs an item before his body or an office decision that a business or outfit wants;
  `rig_count`, for an office holder under `office_threat`, needs his own open race)
- Test: `tests/offscreen_weigh_test.py`

**Interfaces:**
- Produces:
  - `weigh(conn, actor_id, day, why) -> decision_id | None`. It is called when a concern opens, a waited-on date
    arrives, or a shock hits him.
  - Revision 5, a short pick: the options are the package actions that serve the concern and whose needs he meets,
    plus `do_nothing`. One is picked by temperament (`actor_drives`) and habit weight, with a little noise. No mood,
    no competing-concern arithmetic, no stored scores.
  - When `do_nothing` is picked, the concern is marked `waiting`.
  - Every weighing writes an `offscreen_evaluations` row with the chosen action and a plain reason only.
  - Revision 5.9: what the ambition actions do when fired is in Task 17b.

- [ ] **Step 1: Write the failing test:**
```python
d = offscreen.weigh(conn, frank, day, "concern opened")     # Frank: needs money, hates his job, mother ill
assert decision(conn, d)["reason"] and evaluation(conn, frank)["reason"]          # every choice stores why
choices = [offscreen.weigh(fork(conn, seed), frank, day, "x") for seed in range(20)]
assert len({decision(c)["action"] if c else "do_nothing" for c in choices}) >= 2   # not always the optimum
assert share(actions_of(choices_of(hothead)), "confront") > share(actions_of(choices_of(meek)), "confront")  # temperament
assert evaluation_when_nothing_won(conn)["chosen_action"] == "do_nothing"
assert offscreen.weigh(conn, me, day, "x") is None and not evaluations_for(conn, me)  # never for the protagonist
d2 = offscreen.weigh(conn, big_business_owner, day, "concern opened")   # revision 5.8: an opportunity concern
assert decision(conn, d2)["action"] in ("expand", "buy_out", "propose_alliance", "do_nothing")
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 17b: Decisions falling due, and offers

**Files:**
- Modify: `engine/offscreen.py` (`fire_due`) and `engine/levels_tick.py` (register it. Revision 5.5: before
  `fire_due`, a weigh pass calls `offscreen.weigh` for every active person other than him who has a `live` concern
  and no pending decision on it. Revision 6.4: `fire_due` replaces Task 14a's clean-up of past-due stated
  decisions; remove that step from `levels_tick.py`, keeping its rule that one involving him becomes a
  `waiting_on_you` matter)
- Modify: `engine/civic_graft.py` (revision 6.4: `fraud_pass` skips a candidate who is a mover; grand plan F-4)
  and `engine/civic_corruption.py` (`put_on` for an accepted `seek_payment`)
- Revision 5.8, plans in motion: when a fired decision has a visible step (a buy-out offer, an expansion, a loan
  sought, staff taken on, an alliance agreed), it starts a spread row about the mover from those who saw it (the
  owner offered, the new staff, the lender). It then travels by `news_gate.spread` to people in that trade or
  district. An offer for one of the named businesses, or one above `visible_spend`, is also an item on the paper.
  The intent itself stays with the mover and those in on it.
- Modify: `engine/hearsay.py` (`waiting` includes pending decisions with `offer_to_actor_id` = him and `told_day` set)
- Modify: `engine/business.py` (`expand`) and `engine/player_operations.py` (revision 5.9: the payment and
  ownership change of an accepted `trade` move into one shared function that `buy_out` also calls; no second copy)
- Test: `tests/offscreen_fire_test.py`

**Interfaces:**
- Consumes: Task 17a's decisions; Task 15's `publish` for `pressure_business`.
- Produces:
  - `fire_due(conn, day) -> list[decision_id]` carries out due decisions through existing engine effects (loans and
    payments through money records, obligations, ties, a `channel_shock` for `pressure_business`), all on one causal
    chain under `rollback.current`.
  - A fired decision aimed at an active person opens a concern for him (`origin_kind='other_act'`).
  - A due decision by or aimed at someone `near` him becomes a nomination (Task 14), with the decision as its
    cause. Far from him it fires as an engine act.
  - An offer whose `expires_day` passes lapses or escalates only if `told_day` is set.
  - A `stated` decision from a scene fires on its due day as the stamp says. If no engine effect fits, it becomes a
    `waiting_on_you` matter for the GM to play.
  - Revision 5.9, the ambition actions (moved here from Task 17a):
    - `expand` puts the business's cash into capital or staff through `business.py`'s existing paths;
    - `buy_out` offers the owner of the struggling business a price from its value (capital plus cash minus
      debt, as `trade` reckons it). Accepted, it pays and changes owners through the shared function;
    - `propose_alliance` makes an offer to another owner or seat holder, which becomes an obligation if
      accepted.
    - Revision 6.4: once one of these fires, `fire_due` sets the `opportunity` concern it served to `resolved`.
    - **Who accepts.** Far from him, an owner weighs a buy-out the way the `trade` offer already weighs a price
      against value, more willing the deeper his business is below the struggling line. An alliance is settled
      by the tie between the two and their temperament (`actor_drives`). An offer to him, or by or to someone
      `near` him, goes the existing way: a nomination, or his `waiting_on_you` matter.
  - Grand plan round 3 (former F-4), officials acting on their own:
    - `seek_payment` asks the business or outfit for money. The payer answers through `civic_graft.weigh`, and an
      accepted payment is put on through `civic_corruption.put_on`, so the existing exposure checks and
      convictions reach it;
    - `rig_count` adds votes through `races.commit_fraud`. The weekly `civic_graft.fraud_pass` skips a candidate
      who is a mover, so there is one path per person and no doubled fraud.
    - Test: an office holder under `cash_strain` with a licence before his body ends the run with an arrangement
      he started; a mover in a close race rigs through his decision, and `fraud_pass` doesn't touch him.

- [ ] **Step 1: Write the failing test:**
```python
d = pending_decision(conn, mover, "pressure_business", target=shop, due=day + 3); run_days(conn, 4)
assert decision(conn, d)["status"] == "fired" and shock_on(conn, shop, chain=decision(conn, d)["causal_chain_id"])
loan = pending_decision(conn, frank, "ask_loan", target=me_friend_active, due=day + 1); run_days(conn, 2)
assert concern_of(conn, me_friend_active, origin_kind="other_act")
offer = make_offer_to_me(conn, frank, expires_in=7, told=False); run_days(conn, 10)
assert decision(conn, offer)["status"] == "pending"         # untold offers don't lapse
offer2 = make_offer_to_me(conn, frank, expires_in=7, told=True); run_days(conn, 10)
open_concern(conn, rival_officeholder, 'office_threat'); run_weeks(conn, 2); assert pending_or_fired_decision(conn, rival_officeholder)  # 5.5
bid = fire_buy_out(conn, big_business_owner, rizzos); assert spread_row_about(conn, big_business_owner, from_=rizzo)  # 5.8
assert not knows_intent(conn, a_stranger_in_another_trade, big_business_owner)
assert decision(conn, offer2)["status"] in ("lapsed", "fired")
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 17c: Noticing (Deploy 2; formerly Task 15b)

**Files:**
- Modify: `engine/offscreen.py` and `engine/levels_tick.py` (a knowledge row about a person reaching a mover opens
  a `wants` concern about him when the package's `noticing` rule says the fact is useful to that mover. It runs each
  week over every `active` mover, outfit captains included (revision 5.3).)
- Modify: `worlds/saintjude/levels.json` (`noticing`: which facts interest which mover roles)
- Test: `tests/noticing_test.py`

**Interfaces:**
- Each weighing either follows up or stores why not (`offscreen_evaluations`), so silence is always a stored fact
  with a cause.
- Revision 5.3: the outfit code owns outfit agendas. Noticing him is personal, and it runs for captains too.
- Revision 5.4: the concern's `strength` comes from the package's `noticing` weight for that kind of fact (a
  threat is above an opportunity, which is above mild interest). `weigh` takes the strongest live concern first.
- How a mover learned is itself recorded (`carrier_actor_id`, `path_kind`).
- Revision 4.2: `noticing` maps each kind of fact to interest, opportunity or threat for each mover role, adjusted by
  his circumstances. The follow-up actions are `look_into`, `ask_about`, `send_someone`, `offer_work`, `invite`,
  `test_him` and `leave_be` (deliberate, with its reason). They join the package actions of Task 17a and are
  picked the same short way (revision 5).

- [ ] **Step 1: Write the failing test:**
```python
tell(conn, captain, about=me, fact="does good work on cars", via=a_customer_in_his_crew)
run_weeks(conn, 6)
c = concern_about(conn, captain, me); assert c and c["origin_kind"] == "noticed"
assert followed_up(conn, captain, me) or evaluation_reason(conn, captain, c)   # follow-up, or silence with a cause
assert knowledge_of(conn, captain, "good work")["carrier_actor_id"] == a_customer_in_his_crew
assert strength(concern_about(conn, captain_told_rival_work, me)) > strength(c)  # a threat weighs more than good work
assert len(followup_kinds_over_seeds(conn, captain, me, seeds=20)) >= 2       # not always an offer or pressure
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus touched modules, commit.

### Task 18a: (folded into Task 14d)

Revision 5.2: the three world measures are part of `tools/start_check.py` (Task 14d). There is no separate scorer.

### Task 18b: One mover, the ten-step chain, absence and the routine run

**Files:**
- Revision 5.2: no second mover path for outfits. The kept `outfit_choices` acts for the outfit and emits a
  `channel_shocks` row for a squeeze, and opens the `causal_chains` row it sits on (revision 5.3). `offscreen.py`
  handles personal plans for every mover, and the plans of movers outside outfits.
- Modify: `engine/outfit_choices.py` (a squeeze on a business writes a `channel_shocks` row on the outfit's chain)
- Create: `tests/levels_chain_test.py`, `tests/levels_life_test.py` (slow: add to `tests/slow_tests.txt`)
- Test: both files above

**Interfaces:**
- Consumes: Tasks 10, 11, 14d, 15, 16, 17a and 17b.

- [ ] **Step 1: Write the chain test** (`levels_chain_test.py`), one assertion per step of design section 10.4:
```python
outfit = a captain's outfit; give it an organization_pressures row (collections short)
run_weeks(conn, 8)
c = outfit_choice_on(conn, outfit);                         assert c                                    # 1 the outfit's own aim
d = c;                                                      assert d["action"] == "squeeze"             # 2 decides
shock = shock_of(conn, d);                                  assert shock["channel_id"] == carlas_fathers_shop  # 3
p = concern_of(conn, carlas_father, origin_kind="exposure"); assert p                                 # 4
# 5: shop trouble isn't urgent, and Carla doesn't share his household or routine, so it waits with her
h = pending_news_for(conn, me, carrier=carla, chain=shock["causal_chain_id"]); assert h and not h["delivered_day"]
b = brief_with(server, carla);                              assert "has_news_for_you" in dump(b)        # 6 she has it
server.act(...player responds...); r = server.close_scene(...)                                          # 7
n = knowledge_of(conn, me, shock_key);                      assert n["path_kind"] == "told" and n["carrier_actor_id"] == carla  # 8
b2 = brief_with(server, carlas_father);                     assert "on_their_mind" in dump(b2)          # his worry, later
run_weeks(conn, 4);                                         assert world_moved_on(conn, outfit)         # 9, 10
assert same_chain(conn, c, d, shock, p, n)                  # one chain from origin to news
```
- [ ] **Step 2: Write the life test** (`levels_life_test.py`): a fresh save run 120 days with only routine acts, then
  `start_check.py`'s measures; assert C1 (every level-3 event has a cause), that there's at least one courtship step, one
  business change and one organisation aim pursued, and no doubled consequence. Revision 5.8: also at least one
  ambition pursued by a mover outside the outfits: an `opportunity` concern that fired as `expand`, `buy_out` or
  `propose_alliance`. Add the three absence tests:
  1. 60 days away: the city changed for its own reasons;
  2. his return: a carrier holds news for him and nothing is dumped as a summary;
  3. an important day without him: a wedding or vote happens and doesn't reach him without a path.
  Run one year at most.
  Revision 4.2 adds two checks:
  - **A political start** (revision 5.1: run through Task 14d's `start_check.py --start politician`): a fresh save
    with the protagonist as a ward councilman made through `new_character`.
    The same 120 days must give him at least one nomination from his circle, and a rival office holder must pursue
    an aim of his own (`office_threat`).
  - **Report, don't assert:** the lead reads from `causal_chains` whether any chain crosses from one mover's act
    into another's concern.
    Full competing agendas come with steps 6 to 8.
- [ ] **Step 3: Run both.** Expected: FAIL until the mover wiring is in.
- [ ] **Step 4: Implement** the mover wiring. Run both, then `--quick`.
- [ ] **Step 5: Commit.** The lead reads the life run and runs `start_check.py` for all four starts.

---

### Task 18c: Business state (Deploy 2)

**Files:**
- Create: `tools/business_probe.py` (first measure what today's business code does over 120 days: customers, payments,
  demand, capacity)
- Modify: the business modules the probe names (revision 5.2: no drawn paying habits; demand follows reputation, rivals and neglect, with the cause stored; capacity against workload is computed)
- Modify: `worlds/saintjude/business.json` (demand drivers)
- Create: `worlds/saintjude/trades.json` (grand plan round 1: the bible's cost structures per trade, so a bar leaves its
  owner 10 to 20% and a garment shop 3 to 8%; the business state reads it. Test: a bar's month leaves its owner a
  share inside the bible's range. Grand plan round 2b: it gives default costs, never a closed list. A trade that
  matches none of it (a sports team, a stadium, a hotel group) takes the capital and running costs the GM sets on the
  record through `author`, instead of defaulting to a wholesaler (`authoring._archetype`). Test: an authored
  "basketball franchise" keeps the GM's figures and is not costed as a wholesaler)
- Revision 5.5: when his business takes work, demand moves from a same-district competitor as a `competitor`
  shock through `channels.publish` (moved here from Task 15). Test: his shop's growth shows up as a demand shock on
  a rival in the same district, and the rival owner has a concern from it.
- Modify: `connector/brief.py` (his business in `money`: backlog, turned-away work, who owes what)
- Test: `tests/business_mix_test.py`

**Interfaces:**
- The GM invents the haggling, the breakdowns and the customers' faces. The engine holds who pays how, what is
  owed, why demand moved, and when he is over capacity.

- [ ] **Step 1:** run the probe and report to the lead before writing the test. Revision 5.3: it reports the share
  of credit agreements and customer payments that go `late` over 120 days. If the share skews late, tune the
  existing odds in the business code. Add no per-customer model.
- Revision 5.3: also add the spread row for a sustained rise in his business's work (from Task 10a).
- [ ] **Step 2: Write the failing test:**
```python
late_once(conn, customer); assert brief_present_of(server, customer)["owes_or_paid_late"]   # remembered from money records
good_work(conn, me, weeks=8); assert demand_cause(conn, me_shop)["kind"] == "reputation"
overload(conn, me_shop); assert brief_money(server)["turned_away"] > 0
quiet_month(conn, me_shop); assert demand_cause(conn, me_shop)                # nothing arrives, with a reason
# revision 4.2: capacity and slumps become his decisions, with causes in the world
overload(conn, me_shop, weeks=3); assert waiting_on_you_has(server, "turning work away")
undercut(conn, rival, me_shop); assert discoverable(conn, me, cause="undercut", via=a_customer_or_supplier)
```
- [ ] **Step 3 to 5:** implement, run the task's test plus touched modules, commit.

### Task 18d: The protagonist's death or long sentence (Deploy 2)

Revision 5.2 (owner): firm in Deploy 2.

**Files:**
- Modify: the health and law paths that can end his play: the tie-break where survival and death are both
  plausible, his death, and a sentence longer than the package's `long_sentence_days`
- Modify: `connector/server.py` (`resume` on a save whose protagonist is dead offers a successor. It is built with
  the GM through `new_character`, among his kin or circle or a newcomer. The save goes on.)
- Test: `tests/protagonist_end_test.py`

- [ ] **Step 1: Write the failing test:**
```python
assert outcome_when_both_plausible(conn, me, "gunshot") == "survives"
kill(conn, me); run_days(conn, 30)
assert city_moved_on(conn) and kin_grieve(conn, me)                     # the world carries on
r = server.resume(); assert r["protagonist"] == "dead" and "successor" in r
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus touched modules, commit.

## Phase E: build step 5

### Task 19: Deploy and the owner's playtest (lead)

This runs twice: after Task 14d (Deploy 1) and after Task 18d (Deploy 2). See Delivery and cost.
- [ ] Back up the VM saves (`/var/lib/caerness/backups/pre-levels-<date>/`), check integrity, then deploy the branch.
- [ ] Start a fresh Saint Jude save. Dominic's old save is not migrated for play.
- [ ] The owner plays an evening, then a stretch of several game weeks. Nothing is staged to show off features.
  Revision 5.2: Deploy 1's playtest judges the GM–engine loop, nominations, the news gate and the four starts.
  The city's reactions are judged in Deploy 2.
- [ ] The lead runs `gm_check.py` on the playtest transcript.
- [ ] Faults go through the scoring sheet. Each fix goes to the task that owns the code.
- [ ] Once the slice is proven, delete the old feeds behind `news_gate` (owner's yes first). Then write the plan for
  steps 6 to 8.
