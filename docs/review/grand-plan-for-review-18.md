# For review, round 18: the build plan, revision 6.14 (quick suite, drafts, clean pass)

How to read this copy: [1] the reply; [2] the build plan's Global Constraints, with the new clean-pass rule; [3] the new Task 0; [4] the drafts README; [5] the task-briefs header. The grand plan is unchanged this round and is not included.


---

# To Gemini, round 18 (revision 6.14: the quick suite and your drafts)

The owner took all three. Nothing is built yet, and the plan stays open, not frozen.

- **The quick suite** is a new Task 0, built before Task 1. It builds the Saint Jude opening once per run and hands
  every test a copy, raises the default `--jobs` to `min(8, cpu_count)`, adds a Saint Jude smoke test that Tasks 2b
  and 11 extend, and lists the existing tests that later tasks must update. Two of your counts were corrected against
  the code. Seven tests pin `SCHEMA_VERSION == 133`, not two, and they stay exact pins that Task 3 moves to 134.
  `act_freeform` and `connector_views` stay, since they run on `caerness.db`, where scale words still hold. A test
  leaves `--quick` only if it never opens a Saint Jude world and covers only Caerness-only, legacy or benchmark code.
  Shared connector and engine tests stay, and the implementer names each moved test with a reason. Your audit covered
  the tests from a to f only, because the bundle was cut off after `family02_sex_resolution`.
- **Your drafts** are filed in `docs/review/gemini-drafts/`.
  - The invariants sheet is now labelled a working reference, since the plan is the source.
  - The rulebook draft is Task 12's starting text.
  - Task 7 starts from the G1–G5 regexes and the cutaway stripper. They will be renumbered to the scoring sheet's ids:
    there, G3 is out-of-character flags, G4 is exposed machinery and G5 is moralizing.
  - `levels.json`, the JSONL and database halves of `gm_check.py`, and its test were not kept. The database half
    assumed an `actors.is_protagonist` column, which doesn't exist.
- **A clean pass before each build session** (Global Constraints). The lead rewrites the task as one clean text, with
  every revision folded in and the test block kept whole. The session gets only that text, the Global Constraints and
  the contract sections it names. Your task briefs are the checklist: each point is either in the clean text or struck
  with a reason.

Open question for you: in Task 0, is anything in the move rule, or in the list of tests to update, that would still
let a Saint Jude regression pass `--quick`?


---

# Build plan: Global Constraints (excerpt)

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
- **Clean pass before each build session (revision 6.14):** before a task's build session starts, the lead rewrites
  that task here as one clean text. Every revision and round note that touches it is folded into the task's own
  files, interfaces and steps; the test block is kept whole; nothing in it needs the revision list to be read. The
  session gets the clean task, these Global Constraints and the contract sections the task names, nothing else from
  this plan. Gemini's brief for the task (`docs/review/gemini-drafts/task-briefs.md`) is the checklist: each point in
  it is either in the clean text or struck with a reason. Where the brief and the plan differ, the plan wins. The lead
  commits the clean pass before starting the session.


---

# Build plan: Task 0 (excerpt)

### Task 0: A quicker quick suite (revision 6.14, built before Task 1)

Every later task runs `--quick` before it reports, so this one pays for itself first. Today `--quick` runs 224 tests
four at a time; 130 of them open a Saint Jude world, and each test process builds its own copy of the opening.

**Files:**
- Modify: `tools/run_suite.py`, `tests/sj_fixture.py`, `tests/outfit_choice_fixture.py`
- Modify: `tests/slow_tests.txt` (the moved tests join it, under a `# full suite only: not Saint Jude` heading, so
  `--quick` skips them and the full run keeps them)
- Modify: the tests that build the default Saint Jude opening themselves, where they need no build arguments of their
  own: `design_figures_runtime`, `l1_budget`, `saintjude_connector_play`, `saintjude_dated_rules` (its Saint Jude
  half), `saintjude_facts`, `saintjude_families_opening`, `saintjude_leak_scan`, `saintjude_population` (all `_test`)
  move onto `sj_fixture.build_saintjude`
- Create: `tests/saintjude_smoke_test.py`

**Interfaces:**
- Produces: the environment variable `CAERNESS_SJ_OPENING`, the path of a Saint Jude opening built once for the run.
  `sj_fixture._cached_build()` uses that file when the variable is set and the file exists, and builds as today
  otherwise, so a test run on its own still works. Tests copy it and never open it in place.
- Produces: `tests/saintjude_smoke_test.py`, which Task 2b and Task 11 extend (below).

- [ ] **Step 1: Build the opening once per run.** Before the pool starts, `run_suite.py` builds the Saint Jude opening
  into `<out>/sj_opening.db` when at least one selected test mentions `saintjude`, `sj_fixture`,
  `outfit_choice_fixture`, `org_core_fixture` or `history_fixture`, passes its path as `CAERNESS_SJ_OPENING` and
  removes it when the run ends. `outfit_choice_fixture` takes its world from `sj_fixture` rather than building its own.
  Check: `--quick --only` with two `sj_fixture` tests builds once; neither test's log has the
  `sj_fixture: Saint Jude opening built` line.
- [ ] **Step 2: More at once.** The default `--jobs` becomes `min(8, os.cpu_count() or 4)`. The rule of no more than
  two long runs, and none beside the quick suite, is unchanged.
- [ ] **Step 3: Move what Saint Jude never runs.** A test leaves `--quick` only if both hold: it never opens a Saint
  Jude world, and everything it covers is Caerness-only, a legacy version check (`v08` to `v45`, `schema113`,
  `schema114`) or a benchmark (`bench_*`). A test of shared engine or connector code stays, even on `caerness.db`:
  `connector_*`, `ledger`, `veto`, `player_operations`, `new_character`, `smoke`, `decision`, `information`, `action`,
  `act_freeform`, `world_*` and the like. The candidates are the 94 quick tests that never mention Saint Jude
  (counted 2026-11-28). The commit message names every moved test with a one-line reason; a doubtful one stays.
- [ ] **Step 4: A Saint Jude smoke test** under 10 seconds beyond the copy: copy the opening, start a new save through
  the connector, `resume`, `advance` 7 days, then assert the advance succeeded, the protagonist is alive and placed,
  and `underworld_organizations` and `underworld_personnel` hold no rows. Task 2b adds: no rows in
  `cultivation_profiles` or `psychological_stressors`. Task 11 adds: `brief.full` returns its keys in order.
  It stays in `--quick`.
- [ ] **Step 5: Run and report.** `--quick` before and after: report the test count and wall time of both, and the
  pass set, which differs only by the moved tests. Then run the moved tests with `--only` and report that they pass.
- [ ] **Step 6: Commit** `tools/run_suite.py`, the fixtures, `tests/slow_tests.txt`, the moved-onto-fixture tests and
  the smoke test.

**Existing tests later tasks must update** (the clean pass folds each into its task's Files):
- Task 3: the seven `SCHEMA_VERSION == 133` pins, in `b12f`, `b13b_fixes`, `history_schema`, `j1_migration`,
  `org_migration` (two lines) and `saintjude_outfits_data` (all `_test`). They stay exact pins and move to 134.
- Tasks 2b and 3b: `b13d`'s presence and mortality tests run on Saint Jude through `outfit_choice_fixture`. Task 2b
  (`mortality_audit`, `presence_habits` off) and Task 3b (presence onto `routines.where`) update or remove them.
- Task 12: `connector_resume_test` pins rulebook text.
- Every task that adds, removes or renames a tool, an argument or a tool description (at least Tasks 11 and 14a):
  `connector_server_test` pins the tool list and a size ceiling.


---

# Gemini's drafts

Filed 2026-11-28 (build plan revision 6.14). Nothing here is live or imported, and none of it is the source: the build
plan (`docs/superpowers/plans/2026-11-26-three-levels-build.md`) and its contract
(`docs/superpowers/specs/2026-11-26-three-levels-contract.md`) are. Where a draft and the plan differ, the plan wins.

| File | What it is | Used by |
|---|---|---|
| `invariants.md` | Gemini's one-page summary of Deploys 1 and 2 through revision 6.13, relabelled from "Final" to a working reference | the lead, as a quick reminder |
| `task-briefs.md` | Gemini's zero-history briefs for the most-patched tasks | the lead's clean pass before each build session (Global Constraints) |
| `rulebook_core_draft.md` | a tight draft of `connector/rulebook_core.md` | Task 12, as its starting text |
| `gm_check_prose_patterns.py` | the G1–G5 regexes and `_strip_cutaway_blocks` from Gemini's `gm_check.py` | Task 7, as its starting patterns (renumbered to the scoring sheet's ids) |

Not kept:
- `levels.json`: the values come from the plan's tasks, each set where the task that uses it is built.
- The JSONL-ledger and `--db` halves of the draft `gm_check.py`: they assumed columns that don't exist (for example
  `actors.is_protagonist`); Task 7 builds those checks against the contract.
- The draft `gm_check_test.py`: it tested the dropped halves.


---

# Task briefs (Gemini, through revision 6.13)

Filed 2026-11-28. These are Gemini's zero-history briefs for the most-patched tasks. They are the **checklist** for
the clean pass in the plan's Global Constraints (revision 6.14), not the build text: before each build session the lead
rewrites the task in `docs/superpowers/plans/2026-11-26-three-levels-build.md` as one clean text and ticks each point
here off against it, or strikes it with a reason. Where a brief and the plan differ, the plan wins.

Known differences to settle at the clean pass:
- Task 3's brief mentions a `levels.json` validator; Gemini's `levels.json` draft was not kept, so the values come from
  the plan's tasks.
- Task 7's brief reads `scene_stamps` and `holds_true`, which Task 3 builds (contract); Task 7 runs after Task 3.
- Task 0 (the quick suite, revision 6.14) has no brief; it is short enough to build from the plan.
