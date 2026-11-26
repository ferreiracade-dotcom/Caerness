# For review: the build plan for a three-level simulation design (AI-run text role-playing game)

## Context for the reviewer
You reviewed the design (revision 3, and your amendments became revision 3.1, section 11). The owner approved
revision 3.1. This file holds what came next:
1. **The schema and tool contract**: the one-page specification your amendment 15 asked for, which fixes the table,
   column, tool and function names.
2. **The build plan for steps 1 to 5**: 19 tasks, each with files, interfaces and the test that proves it, ending in
   the owner's playtest of a fresh save.

Reminders about the project:
- **Engine:** Python/SQLite, about 87,000 lines, schema version 133 today.
- **GM:** Claude, through an MCP connector with the tools `resume`, `scene`, `lookup`, `lore`, `act`, `advance`,
  `note`, `author`, `money` and `correct`.
- **World:** Saint Jude, 1975.
- **Who builds it:** each task is built by a separate implementer session, and the lead reviews every diff.
- **Fixed constraints:**
  - no hard caps;
  - no world words in engine code;
  - the engine vetoes and never offers a menu;
  - the protagonist lives under the same rules;
  - token cost matters.

Some existing tables are reused rather than duplicated: `knowledge`, `relationships`, `relationship_history`,
`obligations`. The old `pressures` and `decisions` tables belong to a shelved world's engine and are left alone.

Calls the lead made that you may want to test:
- During a time skip, news told by someone reaches the protagonist only if that person was actually with him in that
  window. Otherwise it waits with them until they next meet.
- Illness stays exempt from the protection lock, as a chance origin.
- Several group memberships, contests, others weighing in, movers acting through organisations, and promotion and
  demotion are left to a later plan (steps 6 to 8).

**What would help most:**
- Does the contract hold up?
  - Are tables missing, misplaced, or likely to need changing soon?
  - Are the rollback keys complete?
  - Are the `close_scene` field shapes workable for an LLM GM?
- Is the task order right, and is any task too big or hiding a dependency?
- Do the tests prove what each task claims? Where would a task pass its test and still be wrong in play?
- What will go wrong first when the owner plays?
- Concrete suggestions are more useful than general praise.

---

**What changed after your first review of the plan:**
- **Undo:** a generic change log, `record_changes`, covers pressure rises, standing overwrites and status changes.
  Money is reversed with a reversing record, never deleted. `tie_contexts` is inverted through
  `relationship_history.context`. Authored rows are marked reverted or listed as left in place.
- **New tables:**
  - `pending_news`, holding what a carrier has to tell him and marked delivered once;
  - `offscreen_evaluations`, recording every weighing, including those that ended in doing nothing;
  - `stated`, a reserved decision action for decisions stamped in a scene.
- **`close_scene` and `note`:**
  - names or ids everywhere, with ambiguous names refused along with the candidates;
  - tie changes as signed small, medium or large steps, never raw scores;
  - directional thread kinds (`owed`, `meeting`, `promise`);
  - a `stamp` parameter of its own;
  - a scene at a new place refused while one is open;
  - per-call `changed` in place of a `since_beat` cursor.
- **Your call 1:** in town, urgent news from close kin or ties arrives by phone or visit; other told news waits.
  Prison, travel and away get no told news.
- **Your call 2:** illness audited. It opens only a health condition, and death can come only later through the
  health system's own reviews.
- **Order:**
  - routines moved to Task 3b and seeded at the opening and on refresh;
  - acute shocks open concerns at once for notable people;
  - `publish` writes `pending_news` to the protagonist through tied carriers (the chain's missing bridge);
  - Task 17 split into 17a and 17b, and the scorer split out as 18a.
- **Tests:**
  - migration against a real pre-134 save;
  - an active-count band;
  - scene edge cases;
  - a multi-effect undo;
  - record post-conditions on the bench fixtures;
  - news delivered once, and false rumours staying false;
  - the illness exemption tested both ways.
- **Rulebook:** the rulebook holds principles plus a short scene lifecycle; parameter shapes live in the tool
  docstrings.

**For this round:** is anything still missing or wrong, especially in the generic undo log, the news bridge and
the `close_scene` shapes? Short answers are fine.

---
# Three levels: schema and tool contract (step 2, first artifact)

This fixes the names later tasks build on. It implements `2026-11-26-three-levels-design.md`, revision 3.1. Where a
table already exists and fits, it is extended rather than duplicated. The old `pressures` and `decisions` tables belong
to the shelved Caerness decision loop (empty in Saint Jude) and are left alone; the new ones have distinct names. The
addiction tables `dependency_profiles` and `dependency_exposures` are unrelated, so the design's "dependencies" table
is called `exposure_links`.

## Schema 134 (engine/schema.sql + migration in engine/db.py)

**Who is simulated how**
- `actors.sim_resolution TEXT NOT NULL DEFAULT 'materialized_minor' CHECK IN ('materialized_minor','notable','active')`.
  Separate from `entity_resolution.resolution_level`, which stays as the old cadence system (design section 8 keeps
  `tiers.py`). Set by `engine/levels.py` (rules below).
- `actors.closeness_to_me REAL` and `actors.systemic_power REAL`, both NULL by default: the two independent values of
  design 1.4, refreshed by `levels.refresh`.

**Scenes and stamps**
- `gm_scenes(id, opened_day, closed_day NULL, location_id NULL, status CHECK IN ('open','closed','abandoned'),
  opened_call_id, closed_call_id NULL, close_json NULL)`. At most one row with `status='open'` (partial unique index).
- `scene_participants(scene_id, actor_id, joined_after_beat INT NULL, left_after_beat INT NULL,
  attention CHECK IN ('involved','attentive','overheard','distracted') DEFAULT 'involved', PRIMARY KEY(scene_id, actor_id))`.
- `scene_stamps(id, scene_id, beat INT, kind CHECK IN ('claim','lie','promise','money','goods','injury','enter','leave',
  'walkout','decision','other'), actor_id NULL, target_actor_id NULL, text, holds_true INT NULL CHECK IN (0,1),
  ref_table NULL, ref_id NULL, call_id, status CHECK IN ('stamped','confirmed','amended','struck') DEFAULT 'stamped')`.
  `beat` counts up from 1 within a scene.

**Causes and rollback keys**
- `causal_chains(id, day, origin_kind CHECK IN ('scene','turning_event','decision','world_process','player_act'),
  origin_id INT, scope CHECK IN ('personal','local','ward','city') DEFAULT 'personal', summary,
  touches_open_thread INT NOT NULL DEFAULT 0)`.
- Add `source_scene_id INT NULL` and `causal_chain_id INT NULL` to: `knowledge`, `relationship_history`, `obligations`,
  and every new table below that can be derived. `relationship_history` also gets `context TEXT NULL`, so undo can
  invert `tie_contexts` as well as `relationships`.
- `record_changes(id, day, source_scene_id NULL, causal_chain_id NULL, table_name, row_id, op CHECK IN ('insert',
  'update'), before_json NULL)`: one generic log of every insert and update made while a scene or chain is current.
  It covers status changes to pre-existing rows (an obligation fulfilled, a concern resolved), overwrites of
  `record_standing` and pressure rises. Undo replays it backwards: an insert is deleted, an update gets `before_json`
  back. Every new module writes through `rollback.log_insert` and `rollback.log_update`. It also traces chains: a
  pressure rise is found on its chain through this log, so no separate pressure log is needed.
- Money is never deleted on undo. `undo_scene` walks `scene_stamps(ref_table, ref_id)` and posts a reversing money
  record for each money stamp, so the ledger stays honest. An authored row (`authored_entities`, connector schema,
  gains `reverted_day NULL`) is marked reverted when nothing after the scene refers to it. Otherwise it stays, and
  it is named in the result.

**Ties by context** (design 3, "ties")
- `tie_contexts(actor_a_id, actor_b_id, context CHECK IN ('work','personal','business','family'), trust, respect,
  affection, resentment, updated_day, PRIMARY KEY(actor_a_id, actor_b_id, context))`. These hold the per-context
  differences; the overall values stay in `relationships`. A `close_scene` tie entry may carry `"context"`.

**Record standing** (design 3 and amendment 3)
- `record_standing(id, subject_kind CHECK IN ('actor','location','business','outfit','household'), subject_id,
  attribute TEXT, standing CHECK IN ('confirmed','inferred'), holds INT NULL CHECK IN (0,1), value_text NULL, day,
  source_scene_id NULL, causal_chain_id NULL, UNIQUE(subject_kind, subject_id, attribute))`.
  No row means unknown. `confirmed` with `holds=0` means "checked, and it is not so".

**Knowledge** (extend `knowledge`)
- `basis CHECK IN ('saw','told','read','heard_rumour','inferred','felt') NULL`, `carrier_actor_id NULL`,
  `path_kind CHECK IN ('self','told','paper','radio','mail','work_talk','parish','street') NULL`,
  `holds_true INT NULL` (is the belief actually correct), `topic CHECK IN ('money','obligation','tie','membership',
  'incident','whereabouts','plan','other') NULL`, plus the two rollback keys. Rows without `path_kind` are legacy and
  never reach the news gate.

**Pressure, concern, decision** (amendment 4)
- `actor_pressures(id, actor_id, domain TEXT, level REAL >= 0, threshold REAL > 0, adapted INT 0/1 DEFAULT 0,
  last_built_day, cooldown_until_day NULL, built_since_day, UNIQUE(actor_id, domain))`. `domain` is a package key.
- `actor_concerns(id, actor_id, kind CHECK IN ('owes','owed','wants','resents','fears_for','courts','plans','needs'),
  object_kind NULL CHECK IN ('actor','business','location','outfit','money','work'), object_id NULL,
  origin_kind CHECK IN ('scene','exposure','other_act','chance','buildup'), origin_text, strength REAL 0..1,
  status CHECK IN ('live','waiting','resolved','resigned','dropped') DEFAULT 'live', opened_day, ends_day NULL,
  last_weighed_day NULL, source_scene_id NULL, causal_chain_id NULL)`.
- `actor_decisions(id, actor_id, concern_id NULL, action TEXT, target_kind NULL, target_id NULL, reason TEXT,
  due_day NULL, trigger_kind CHECK IN ('date','event','opportunity') DEFAULT 'date', status CHECK IN ('pending','fired',
  'dropped','failed','lapsed') DEFAULT 'pending', decided_day, fired_day NULL, outcome_text NULL,
  offer_to_actor_id NULL, told_day NULL, expires_day NULL, on_expiry CHECK IN ('lapse','escalate') NULL,
  source_scene_id NULL, causal_chain_id NULL)`. `action` is a key from the package's generic action set, or the
  reserved `stated` for a decision the GM stamped in a scene (the stamp text is the reason). A decision with
  `offer_to_actor_id` is an offer or demand that waits on that person (design 3, "what waits").
- `offscreen_evaluations(id, day, actor_id, concern_id NULL, why, chosen_action, reason, rejected_json)`: every weighing,
  including those that ended in `do_nothing`, so a world that never does something can be explained.

**News waiting with a carrier** (amendment 6)
- `pending_news(id, carrier_actor_id, recipient_actor_id, knowledge_id, urgent INT 0/1, created_day,
  delivered_scene_id NULL, delivered_day NULL, causal_chain_id NULL)`. The carrier's own knowledge row stays where it
  is. The recipient gets a knowledge row only when the news is delivered, either in a scene with the carrier or by a
  call or visit (urgent items in town). Once delivered, it is never offered again.

**Channels** (amendment 5)
- No subscription table: `engine/channels.py` derives who is attached to a channel from existing links (employer,
  organisation seat, residence, workplace, routine places).
- `exposure_links(id, actor_id, link_kind CHECK IN ('debt','supplier','protection','customer'), other_kind, other_id,
  since_day, ended_day NULL, source_scene_id NULL, causal_chain_id NULL)`: only the links with no existing structure.
- `channel_shocks(id, day, channel_kind CHECK IN ('business','location','outfit','sector'), channel_id, shock_kind TEXT,
  magnitude REAL, summary, causal_chain_id NOT NULL)`. `shock_kind` is a package key.
- `scheduled_effects(id, due_day, effect_kind TEXT, payload_json, status CHECK IN ('pending','done','cancelled')
  DEFAULT 'pending', causal_chain_id NOT NULL)`: delayed effects on the due-queue.

**Routines** (amendment 8)
- `actor_routines(actor_id PK, home_location_id NULL, work_location_id NULL, haunts_json DEFAULT '[]',
  schedule_key TEXT)`: `schedule_key` names a package schedule (which part of which day is work, home or haunt).
- `routine_exceptions(id, actor_id, kind CHECK IN ('ill','travel','event','prison','away'), from_day, to_day NULL,
  location_id NULL, source_scene_id NULL, causal_chain_id NULL)`.
- Routines are seeded by `routines.seed` when the opening is built, and for anyone newly notable or active on
  `levels.refresh`. Home comes from the household, work from the employer or the business he owns, and the schedule
  from his position.

**Engine answers**
- `engine_answers(id, day, call_id, tool, kind CHECK IN ('character','consequence'), actor_id NULL, text,
  rationale NULL, scene_id NULL)`. Vetoes stay as today's refusals and are not stored here.

## Package data (worlds/saintjude/levels.json; validated on load, carries `"version": 1`)
`mover_roles` (which seats and offices make someone a mover), `close_rule` (tie thresholds for being close),
`lock_quiet_days` (45), `familiarity_step` and `familiarity_decay` (company in a scene), `tie_steps` (what
`small`, `medium` and `large` mean for each tie dimension), `tie_concern_line` (a tie step that opens a concern),
`acute_shock_line` (a felt shock large enough to open a concern straight away, for notable as well as active people),
`urgent_kinds` (news that a close tie phones or calls round about, in town), `pressures` (domains, how each builds from existing values, threshold spread, cooldown,
adaptation), `actions` (the generic action set: key, which concerns it serves, what it needs, habit weight, what it
does when fired), `shocks` (shock kinds: which pressure domain each feeds, and by how much), `schedules`,
`news_paths` (everyday channels and what they carry), `answers` (when an act is out of character or weighty).

## Tool contract (connector/server.py)
- **People are a name or an id everywhere** (`close_scene`, stamps, threads). Names are matched against the open
  scene's people first, then the protagonist's known people. An ambiguous name, such as a first name two people share,
  is refused with the candidates. "me" is the protagonist.
- `note(kind="scene", text, present)`: opens a scene if none is open. At the open scene's place, it updates presence.
  At a different place while a scene is open, it is refused with one line: close the current scene first
  (`close_scene`, or `mode="from_stamps"`). Returns `scene_id` and the full brief (connector/brief.py).
- `note(kind="stamp", text, stamp={"kind", "by", "to", "true"})`: a speech-only beat, using a new `stamp` parameter
  so that `field` and `present` keep their meanings. `true: false` marks a lie or a mistake. Arrivals and departures
  mid-scene are stamps of kind `enter` and `leave`. Returns `{"stamp": {beat, kind, text}}`.
- During an open scene, each `act`, `money` and `note` result carries `changed`: only what that call changed. There
  is no cursor for the GM to track.
- `act`, `money`, `author` stamp themselves while a scene is open, add `stamp` to their result, and take
  `rationale: str | None`. Results carry `answers: [{kind, text}]` when the engine has a note.
- **New tool** `close_scene(call_id, mode="commit", participants=None, amendments=None, exceptions=None, ties=None,
  threads=None)`. `mode`: `review` returns the ledger and commits nothing; `commit` applies the four fields;
  `from_stamps` commits the ledger as stamped. Shapes:
  - `participants`: `[{"who": "Carla", "joined_after_beat": 3, "left_after_beat": 5, "attention": "overheard"}]`
    (only the exceptions). Anyone in the scene's presence list is otherwise involved for the whole scene. Stamped
    `enter` and `leave` beats already set the times.
  - `amendments`: `[{"beat": 4, "status": "struck"}]` or `[{"beat": 4, "text": "...", "true": false}]`. Beats are
    the numbers the ledger and each stamp result show.
  - `exceptions`: `[{"beat": 2, "missed_by": ["Frank"]}, {"beat": 2, "disbelieved_by": ["Ma"]},
    {"secret": "text", "known_to": ["me", "Frank"]}]`.
  - `ties`: `[{"from": "Ma", "to": "me", "change": {"trust": "-small"}, "context": "family", "cause": "one line"}]`.
    Steps are `small`, `medium` or `large`, with a sign, mapped to numbers by `tie_steps`. The GM never sees or sends
    a raw score.
  - `threads`: `[{"kind": "owed", "by": "Frank", "to": "me", "text": "$40 for the parts", "due_in_days": 4}]` or
    `[{"kind": "meeting", "with": ["Tullio"], "text": "the club, Tuesday", "due_in_days": 5}]`. The kinds are
    `owed`, `meeting` and `promise`.
  - A scene with no stamps and no fields closes cleanly as an ordinary one.
- `advance` refuses while a scene is open, naming `close_scene(mode="from_stamps")`. `resume` returns an open scene
  as it stands and never closes it.
- `author(kind="turning_event", details={scope, channels: [{kind, id or name}], shock, summary, magnitude})`.
- `correct(op="undo_scene", details={"scene": id})` and `correct(op="undo_chain", details={"chain": id})`, on the
  player's explicit yes like every `correct` op.

## Engine module surface
- `engine/levels.py`: `refresh(conn, day) -> dict`, `resolution_of(conn, actor_id) -> str`.
- `engine/scenes.py`: `open_scene`, `open_scene_id`, `stamp`, `ledger`, `close(conn, call_id, mode, **fields) -> dict`.
- `engine/rollback.py`: `current(conn, scene_id=None, chain_id=None)` (context manager setting what new writes are
  keyed to), `log_insert(conn, table, row_id)`, `log_update(conn, table, row_id, before: dict)`,
  `undo_scene(conn, scene_id) -> dict`, `undo_chain(conn, chain_id) -> dict`.
- `engine/routines.py` also has `seed(conn, actor_ids=None) -> int`.
- `engine/news_gate.py` also has `hold(conn, carrier, recipient, knowledge_id, urgent, chain_id) -> int` and
  `deliver(conn, pending_ids, scene_id=None) -> int`.
- `engine/answers.py`: `judge(conn, tool, actor_id, change: dict, rationale) -> list[dict]`.
- `engine/standing.py`: `confirm`, `infer`, `standing_of`.
- `engine/news_gate.py`: `reaches(conn, me, start_day, end_day) -> list[dict]`, `held_for(conn, me, carrier) -> list[dict]`.
- `engine/protection.py`: `protected_ids(conn, day) -> set[int]`.
- `engine/routines.py`: `where(conn, actor_id, day, part) -> int | None`.
- `engine/channels.py`: `attached(conn, channel_kind, channel_id) -> list[tuple[int, str]]`, `publish(conn, shock_id) -> list[dict]`.
- `engine/pressure.py`: `build(conn, day, actor_ids) -> list[int]` (ids of new concerns).
- `engine/offscreen.py`: `weigh(conn, actor_id, day, why) -> int | None`, `fire_due(conn, day) -> list[int]`.
- `engine/levels_tick.py`: process key `levels`, weekly, registered in `build_default_process_registry`.

---

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
   is next in a scene with him (test in Task 10).

## Left to the plan for steps 6 to 8 (not built here)
- several group memberships, per-domain group rates and competing risks, and calibration across runs;
- contests, built from B1's held fight work;
- the full offscreen choice (others weighing in, decisions before breaks);
- tie resting points and hysteresis (the `tie_contexts` table is created here; only scene tie entries write to it);
- movers' plans through organisations, with imperfect execution (only one mover acts here, directly);
- promotion by demonstrated significance, careful demotion, and obligations through life changes;
- several different starting saves.

---

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

### Task 3: Schema 134 and resolution levels

**Files:**
- Modify: `engine/schema.sql` (new tables and columns from the contract; append a `-- schema 134` block)
- Modify: `engine/db.py` (`SCHEMA_VERSION = 134`; migration adds columns with `ALTER TABLE ... ADD COLUMN` guarded by
  a column check, as the existing migrations do)
- Create: `engine/levels.py`
- Create: `engine/rollback.py` (only `current`, `log_insert` and `log_update` here; Task 6 adds undo)
- Create: `worlds/saintjude/levels.json` (every key in the contract's package section, with first figures)
- Modify: `engine/world_package.py` (load and validate `levels.json`: report missing keys, unknown role references and
  a wrong `version`, telling a missing setting apart from one deliberately left out with `null`)
- Test: `tests/levels_schema_test.py`

**Interfaces:**
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
    an exception first, then the schedule. `where` writes nothing.

- [ ] **Step 1: Write the failing test:**
```python
assert routines.seed(conn) > 0 and seeded_share_of_notable_and_active(conn) > 0.9
assert routines.where(conn, frank, weekday, "day") == garage_location
add_exception(conn, frank, "ill", day, day + 5); assert routines.where(conn, frank, day + 1, "day") == frank_home
assert routines.where(conn, unseeded_minor, day, "day") is None              # unknown, not somewhere
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
- `open_scene` at a different place from the open scene is refused, naming `close_scene`.
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
  - **threads:** each becomes an `obligations` row (`counterparty_actor_id` = `with`, `due_day` = today +
    `due_in_days`, `source_kind` 'scene', `source_scene_id`).
  - **stamps that start something:** a `promise` stamp also becomes an obligation. A `decision` stamp with an
    `actor_id` becomes a pending `actor_decisions` row (the reason is the stamp text). A tie entry that moves
    resentment or affection by at least the `levels.json` concern line opens a `resents` or `wants` concern for the
    `from` person, with `origin_kind='scene'` and the cause as `origin_text`.
  - **contexts:** a tie entry with `"context"` (work, personal, business or family) writes `tie_contexts` as well as
    the overall row.
  - **refusals:** references to beats or people that don't exist, and participants who weren't there. These are
    returned in `refused` and change nothing else.
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
scenes.open_scene(conn, "c7", ["Frank Moretti"], "garage"); move_protagonist(conn, kitchen)
assert "close_scene" in scenes.open_scene(conn, "c8", ["Ma"], "kitchen")["refused"]
# a quiet scene with no stamps closes cleanly
assert scenes.close(conn, "c9", "commit")["closed"]
# names: a unique first name resolves; a shared one is refused with candidates
assert scenes.close(conn, ..., ties=[{"from": "Tony", "to": "me", "change": {"trust": "+small"}, "cause": "x"}])["refused"][0]["candidates"]
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
  - a `stamp: dict | None` parameter on `note`;
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
- Create: `engine/rollback.py`
- Modify: `connector/correct.py` (ops `undo_scene` and `undo_chain`; `preview` shows what each would revert)
- Test: `tests/rollback_cascade_test.py`

**Interfaces:**
- Produces:
  - `undo_scene(conn, scene_id) -> {"reverted": {table: count}, "left": [...]}` and `undo_chain(conn, chain_id) -> {...}`;
  - the `record_changes` log, replayed backwards: inserts deleted, updates restored from `before_json`. This covers
    pressures, overwritten standing, and obligations or concerns a scene resolved;
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

### Task 10: One news gate

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

### Task 11: Brief and change-based read budget

**Files:**
- Create: `connector/brief.py`
- Modify: `connector/views.py` (`compact_scene` builds on `brief.full`), `connector/store.py` (`note kind=scene`
  returns `brief.full`), `connector/timeflow.py` (after a skip, return `brief.full` in place of the separate blocks),
  `connector/server.py` (results of `act`, `money`, `note` during an open scene carry `brief.changed`)
- Test: `tests/brief_budget_test.py`

**Interfaces:**
- Produces:
  - `full(conn) -> dict`, keys in this order: `waiting_on_you`, `present` (per person: name, body, manner,
    temperament in words, tie to him in words, `on_their_mind` (at most three live concerns in plain words), `about_to`
    (pending decisions that involve this scene or him), `has_news_for_you` (from `held_for`)), `crossing_your_path`
    (arrivals, visits, matters due within 7 days that involve him), `news`, `money`, `texture`;
  - `changed(conn, call_effects) -> dict`: only what this one call changed. There is no cursor, since MCP calls hold
    no state between them. Bringing someone in or seeing them leave adds or removes their `present` entry.
  - Each time `full` shows a carrier's `has_news_for_you`, it calls `news_gate.deliver`.
- Nothing about people not present, and nothing building elsewhere, appears in either.

- [ ] **Step 1: Write the failing test:**
```python
b = server.note("s1", "dinner at the Morettis'", kind="scene", present=["Aurelio Moretti"])["brief"]
assert list(b)[:3] == ["waiting_on_you", "present", "crossing_your_path"]
assert "Aurelio" in dump(b["present"]) and "Tullio" not in dump(b)        # Tullio's plans aren't in the room
assert len(dump(server.money("p1", "pay", {...})["changed"])) < 600        # per-call changes stay small
assert not leak_words(b, ["concern", "pressure", "score", "engine"])       # no machinery
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
- **The bridge to the protagonist.** For each affected person with a tie to the protagonist (kin, friend, close per
  `close_rule`, or Carla-style through a live concern of his), `publish` writes what that person knows of it into
  his own knowledge (`basis` felt or saw). It also writes a `pending_news` row with him as carrier and the
  protagonist as recipient, `urgent` set per `urgent_kinds`, on the chain. The gate (Task 10) delivers it from there.
  Nobody else's news is created.
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
assert pending_news_for(conn, me, carrier=carlas_father, chain=chain_of_shock(sid))   # the bridge to him
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
n = gate_item_about(conn, me, shock);                       assert n["path"] == "told" and n["via"]     # 5
b = brief_with(server, carlas_father);                      assert "on_their_mind" in dump(b)           # 6
server.act(...player responds...); r = close_scene(...)                                                 # 7
assert recorded(conn, r)                                                                                # 8
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
- [ ] Back up the VM saves (`/var/lib/caerness/backups/pre-levels-<date>/`), check integrity, then deploy the branch.
- [ ] Start a fresh Saint Jude save. Dominic's old save is not migrated for play.
- [ ] The owner plays an evening, then a stretch of several game weeks. Nothing is staged to show off features.
- [ ] Faults go through the scoring sheet. Each fix goes to the task that owns the code.
- [ ] Once the slice is proven, delete the old feeds behind `news_gate` (owner's yes first). Then write the plan for
  steps 6 to 8.
