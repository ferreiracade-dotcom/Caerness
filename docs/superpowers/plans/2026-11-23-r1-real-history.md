# R1 Real History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, in this session). Steps use checkbox syntax.

**Goal:** Real history stays real offstage unless the run touches it; real facts carry a source, are looked up or added on demand through the intake, and the engine vetoes only contradictions. A fact the run has knocked off course is tracked with its cause.

**Architecture:** Schema 127 adds `history_entries`, `divergences`, `tech_level` and two columns on `held_things`. `engine/history.py` owns proposing a real fact (class, real date, source, needs), resolving its causes against the run and the divergence ledger (direct touch or a chain of named causes; no random drift), recording it as an entry plus a Fixed `world_facts` row, and applying effects at the run date. `engine/real_figures.py` replaces the gazetteer's offstage refusal with documented real figures (public roles, on-record wrongdoing kinds, source). The package timeline stays data and is read as defaults by `history.run_status`, so `veto.dated_rules` stops being a wall. The intake gets a `history` shape (fields `real_date`, `source`, `class`), so `author` stays the one door.

**Tech Stack:** Python 3.13, SQLite, script tests under `tests/`.

**Spec:** `docs/superpowers/specs/2026-11-22-real-history-and-engine-gaps-design.md` (sections 5.5 to 5.11b, 7.3; owner decisions H1 to H5 in section 11; P3 from the owner).

## Global Constraints

- Python: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe"`. Simulate on copies only; never write `data/*.db`; leave `data/caerness.pre-schema110.db` and `game/campaign_01/backups/` alone.
- No world words in `engine/` (no Saint Jude names, years, firms, ranks). Class words, domain words and figures live in `worlds/saintjude/history.json` or are generic. The no-world-words test must stay green.
- No hard caps, floors, clamps, quotas or cooldowns. Delays are drawn from a cause's weight and reported; never enforced.
- Determinism: draws use `random.Random(f"{design.run_seed(conn)}:history:{key}")`.
- Engine vetoes, never offers menus. Refusals name a contradiction or missing cause. An unclear shape lands on the floor, never a refusal (H5).
- Memory-sourced facts about something major (a law, an election result, a firm's founding or IPO, a technology's arrival, a real person's office or death) are stored `provisional`; systems read them only as defaults until `note(kind="fact")` verifies them with a source (H4).
- Real figures act only in their public roles and only with wrongdoing of kinds on their record; invented men do the dirty work.
- The protagonist is under the same rules: a divergence the protagonist causes is a divergence like any other; no player-only rule.
- Foreknowledge never pays by itself (H2): bets are judged on what the character could know and his advisers' competence.
- Schema: migration **127**. Shared files: `engine/db.py`, `engine/schema.sql`, `engine/veto.py` (J1 session told). Do not edit prison, custody or sentence modules or their tests. Do not edit `connector/server.py`, `connector/campaign.py`, `connector/rulebook_core.md` (uncommitted edits from another session); the connector gets its changes in `connector/views.py`, `connector/store.py` and `worlds/saintjude/rulebook_section.md`.
- Tests clean up temp files (tempfile.TemporaryDirectory). After tests run `git restore game/campaign_01/model_requests/`. Commit with `git add <paths>` only, "R1" in the subject, trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Never push, stash, reset or switch branches.

## Review Focus

1. A fact proposed with no `needs` and no divergence anywhere: passes on time, no reasons invented, no drift.
2. A chain A (run changed) -> B (history entry needing A) -> C (new fact needing B): C is judged changed or later, and the reason names every link.
3. A real figure proposed that the run has already killed or jailed: refused as a contradiction naming the clash; a clean figure asked to do dirty work: refused with "use an invented man".
4. A memory-sourced major fact: stored provisional; a minor one is not; verification promotes it and records the source.
5. A foreseen fact (date ahead): no `knowledge` rows, no effects until its date, re-judged then; a fact judged "not at all" is not re-proposed (second proposal returns the recorded outcome).
6. A package without a timeline or intake data (Caerness): nothing runs, nothing breaks.

---

### Task 1: Schema 127 and the history tables

**Files:** Modify `engine/db.py` (SCHEMA_VERSION 127, `_MIGRATIONS[127]`, migration function), `engine/schema.sql` (append `IF NOT EXISTS` tables); create `tests/history_schema_test.py`.

**Interfaces:** Produces tables:
- `history_entries(id, key UNIQUE, class, what, real_date, precision, run_date, outcome, reasons_json, needs_json, source, verify, provisional INTEGER, effects_json, status, about_json, proposed_day, judged_day, call_id)`; `outcome` in (`on_time`,`earlier`,`later`,`changed`,`never`,`default`); `status` in (`foreseen`,`in_force`,`never`,`superseded`).
- `divergences(id, subject, field_words, day, cause, text, entry_key)`; `subject` is `actor:12`, `org:7`, `history:<key>`, `place:..` or free words.
- `tech_level(id, thing, exists_date, available_date, common_date, price_band, source_key, inventor_actor_id)`.
- `real_figures(id, name, name_norm UNIQUE, actor_id, public_roles_json, record_json, source, verify, provisional, status)`.
- `ALTER held_things ADD COLUMN basis_json TEXT NOT NULL DEFAULT '{}'`.

- [ ] Write `tests/history_schema_test.py`: build a fresh DB via `init_db`, assert `SCHEMA_VERSION == 127`, all five tables exist, `held_things` has `basis_json`; migrate a 126 copy (build a 126 DB by running `_apply_migrations` up to 126 on a fresh DB, or reuse the pattern in `tests/intake_test.py`) and assert row counts of `actors` and `held_things` unchanged.
- [ ] Run it; expect FAIL (version 126).
- [ ] Implement the migration (CREATE TABLE IF NOT EXISTS in both `schema.sql` and the migration; ALTER guarded by a column check). Bump the four older tests that assert the schema version (grep `SCHEMA_VERSION`/`126` in `tests/`).
- [ ] Run the new test and the old version-asserting tests; expect PASS.
- [ ] Commit `R1: schema 127, history tables`.

### Task 2: The history shape on the intake, recording real facts

**Files:** Create `engine/history.py`, `worlds/saintjude/history.json` (+ register data key `history` in the package manifest and `world_package.history_rules(pkg)` in `engine/world_package.py`); modify `engine/intake.py` (register the shape at import, as `intake_business` does); create `tests/history_propose_test.py`.

**Interfaces:**
- `history.propose(conn, me: int, details: dict, call_id: str) -> dict` returns `{"status": "created", "kind": "history", "entry": key, "outcome":..., "run_date":..., "reasons": [...], "provisional": bool, "foreseen": bool}`.
- `history.slug(what: str) -> str`; key is `history:<slug>`.
- `history.is_major(conn, klass: str) -> bool` (classes listed in `history.json` `major_classes`).
- `history.rules(conn) -> dict`.
- Details: `what`, `class` (`technology|firm|firm_event|person_event|law|office|price|culture|event`), `real_date` ISO, `precision` (`day|month|year`, default day), `source` (URL plus quote, or `"memory"`), `needs` (list of strings or `{text, ref}`), `about` (list of refs), `effects` (list of `{kind, ...}`), `people`.

- [ ] Test: proposing a source-backed law with a real date earlier than today writes one `history_entries` row (status `in_force`, outcome `on_time`) and a `world_facts` row `history:<slug>` tag Fixed with `start_date`; a `"memory"`-sourced law is `provisional=1`, `verify='to verify'`; a `"memory"`-sourced street price is not provisional; the same `call_id` replays to one row; a missing `what`/`class`/`real_date` is an `input_gap` refusal naming the missing field.
- [ ] Test: a real date ahead of today stores `status='foreseen'`, no `world_facts` start row applied (row exists with `start_date` NULL until judged), no `knowledge` rows, no effects.
- [ ] Run; expect FAIL.
- [ ] Implement `propose` (calls Task 3's `judge` when present: in this task `judge` returns on_time, so replace the stub in Task 3), the `history` Shape (`fields=("real_date","source","class")`, words from `history.json` `shape_words`, `floor_backed=False`), and the held_things row through `intake.take_in` (backing table `history_entries`). `world_facts` is created via `facts.ensure` and `facts._put`.
- [ ] Run; expect PASS. Run `tests/intake_test.py`; expect PASS.
- [ ] Commit `R1: history shape on the intake`.

### Task 3: The check: do the causes still hold here (H1, P3)

**Files:** Modify `engine/history.py`; create `tests/history_judge_test.py`.

**Interfaces:**
- `history.record_divergence(conn, subject: str, field_words: str, cause: str, text: str, entry_key: str | None = None) -> int`.
- `history.judge(conn, entry: dict, day: int) -> dict` returns `{"outcome", "run_date", "reasons": [str], "links": [str]}`.
- `history.resolve_need(conn, need: dict) -> tuple[str, str]` returns (`holds|bent|broken|unknown`, explanation). `actor:N` holds when alive and free; `org:N` when active; `history:K` when that entry is `in_force`/on a run date at or before this one, broken when `never`; `place:`/`law:` likewise; no ref is `unknown` (treated as holding).
- Weights live in `history.json` (`weights`: central 1.0, supporting 0.4, substitute_exists factor); delay days drawn from weight; report calibration, enforce nothing.

Rules (spec 5.7): all hold or unknown -> `on_time` at the real date. Enabler arrived earlier (a `tech_level`/entry with run date before the real date, named in `needs`) -> `earlier`, not below that date plus lead time (`history.json` `lead_days`, default taken from the source's own gap when given). Non-central bent -> `later`. Central broken with a substitute (`needs[i].substitute` true) -> `changed`. Central broken, no substitute -> `never`. Chains: walk `needs` of accepted entries and `divergences` (a divergence whose subject is an entity in `about`/`needs`, or whose `entry_key` is an entry named in `needs`) to any depth; `links` names each hop. No divergence and no broken need: never anything but `on_time`.

- [ ] Tests (each seeded run in a scratch DB): (a) no needs, no divergences -> `on_time`, `reasons == []`, repeated 50 seeds all `on_time` (no drift); (b) need `actor:<id>` where the actor is dead -> `changed` if `substitute` else `never`, reason names the actor; (c) divergence on the entry's firm entity, non-central -> `later`, `run_date > real_date`; (d) chain: divergence on actor A, entry E1 needing A judged `later`, then proposal E2 with need `history:E1` -> `later` or `changed`, `links` has both hops; (e) an earlier enabler `tech_level` row -> `earlier` and `run_date >= enabler date + lead`; (f) same call twice -> identical outcome and date; (g) a `never` entry proposed again returns the recorded outcome (`replayed`), no second row.
- [ ] Run; expect FAIL.
- [ ] Implement; wire `propose` to use `judge`; a `never` or `changed` result writes a divergence row (subject `history:<key>`, cause the chain) so later facts see it. Fixed `world_facts` change only through `facts.override` with a cause, unchanged.
- [ ] Run; expect PASS.
- [ ] Commit `R1: judge real facts against the run`.

### Task 4: Divergences written by the run itself

**Files:** Modify `engine/history.py` (hooks), `engine/intake.py` (call hook after a held thing is made), `engine/facts.py` (hook in `override` when the key is `history:*` or Fixed), the mortality path that kills an actor (find with `grep -n "status='dead'" engine/*.py`; hook one shared function, not each caller); create `tests/history_divergence_test.py`.

**Interfaces:**
- `history.note_actor_death(conn, actor_id: int, day: int, cause: str) -> None`: writes a divergence when the actor is a real figure (`real_figures.actor_id`) or named in any entry's `about`/`needs`, with `real_date` of a recorded death taken as the default (a death before that date diverges; the default date is not scheduled, mortality decides).
- `history.note_venture(conn, me: int, what: str, trade_words: str, cause: str) -> None`: when a held thing is made, any entry in the same field (word overlap of `what`/trade with entry `what`/`about`, using `history.json` `field_words` synonyms when present) not yet in force gets a divergence row so its later proposal meets the taken niche.
- `history.note_override(conn, fact_key: str, cause: str) -> None`.

- [ ] Tests: killing a real figure (use the existing death path) writes a divergence `actor:<id>`; founding a venture via `author` in a field matching a foreseen entry writes a divergence with the cause call id; overriding a Fixed history fact writes one; an unrelated death, venture or override writes none (no spurious drift); the protagonist founding the venture is handled by the same path (assert on his id).
- [ ] Run; expect FAIL. Implement. Run; expect PASS.
- [ ] Commit `R1: the run writes divergences`.

### Task 5: Real figures replace the offstage refusal

**Files:** Create `engine/real_figures.py`; modify `engine/veto.py` (`real_person`, `canon_figure`), `engine/intake.py` (`_check_facts` calls the figure check), `engine/authoring.py` (person maker accepts a documented real figure); load gazetteer `real_people` as documented figures lazily; modify `tests/saintjude_dated_rules_test.py` (the old refusal assertions at ~line 84 and 114 now expect the new behaviour); create `tests/real_figures_test.py`.

**Interfaces:**
- `real_figures.propose(conn, me, details, call_id) -> dict`; details: `name`, `source`, `public_roles` (list of words), `record` (kinds of wrongdoing on his record, words), `born`/`state_1975` text, `status` (`alive`,`dead`,`jailed`, with `real_date` if not alive in 1975). Reached through the intake as shape `real_figure` (class word "real person"); creates an `actors` person via the existing person path (`person_ecology`, never INSERT directly) and a `real_figures` row; major role from memory is provisional (H4).
- `real_figures.find(conn, name) -> sqlite3.Row | None`.
- `real_figures.check_acts(conn, actor_ids: Iterable[int], legality: str, kind_text: str) -> None` raises `Contradiction`: a real figure with `legality == "illegal"` or wrongdoing words not in his `record` -> "X is a real person whose record shows no {kind}; use an invented man for this".
- `veto.real_person(conn, name)`: no longer refuses a gazetteer name; it refuses only when the name belongs to a real person with no documented figure **and** the proposal is a new invented person claiming it (the name is "taken", message tells the GM to look him up and propose him with a source via `author` with `kind="real person"`); a dead/jailed real figure (per `real_figures.status`/entries) proposed as active is refused naming the clash.

- [ ] Tests: proposing "Brendan Byrne"-style figure through the old path (invented person) is refused with the look-up message; proposing him with a source and public role (use a test gazetteer entry, not world words in `engine/`) succeeds and creates one actor and one figure row; a public-role act (a vote, a speech held thing, legality `legal`) passes; an illegal held thing with him as owner is refused with "use an invented man"; a figure with `record: ["racketeering"]` may be tied to a held thing whose kind words match the record; a figure killed by the run (Task 4) proposed again is refused; `check_acts` applied to the protagonist is a no-op (he is not a real figure) and a test shows the identical check acts on any actor flagged real, so there is no player-only branch.
- [ ] Run; expect FAIL. Implement. Run; expect PASS. Run `tests/veto_test.py`, `tests/saintjude_dated_rules_test.py`, `tests/intake_test.py`.
- [ ] Commit `R1: real figures replace the offstage refusal`.

### Task 6: Dated rules read run dates; the timeline becomes defaults

**Files:** Modify `engine/history.py` (`run_status`), `engine/veto.py` (`dated_rules`), `worlds/saintjude/timeline.json` (add `"class"` to all 63 entries: `law`, `institution`, `technology`, `firm`, `culture` or `event`), `engine/world_package.py` if the timeline loader drops unknown fields; create `tests/history_dated_rules_test.py`.

**Interfaces:**
- `history.run_status(conn, name: str, day_iso: str) -> dict` returns `{"status": "not_yet|exists|available|common|never|unknown", "class": str, "run_exists": iso|None, "reason": str|None}`; reads `history_entries` (run date, `never`) first, then the package timeline default.
- `dated_rules(conn, text)`: for class `law`/`institution` before its run date: refuse as today (with run date); `never` -> refuse with the recorded reasons; class `technology` before its run date: do not refuse, return the mention to the enabler check (Task 7) via `history.pending_enablers`; other classes: not refused (a culture item before its date is a plausible invention; the enabler check handles it if it needs one).

- [ ] Tests: existing `saintjude_dated_rules_test.py` cases for laws still refuse; a technology named before its real date no longer refuses; a law whose entry the run judged `later` refuses until the later date; an entry judged `never` refuses with its reason; a name the timeline lacks passes silently as before.
- [ ] Run; expect FAIL on the new cases. Implement. Run; expect PASS (plus `intake_play_test.py` and `veto_test.py`).
- [ ] Commit `R1: dated rules read run dates`.

### Task 7: Technology and the enabler check (5.10), foreknowledge (H2)

**Files:** Modify `engine/history.py` (tech functions), `engine/intake.py` (checks 6 and the foreknowledge annotation; `basis_json`); create `engine/foreknowledge.py`; create `tests/history_tech_test.py`.

**Interfaces:**
- `history.tech_status(conn, thing: str, day: int) -> str`; `history.add_tech(conn, thing, exists, available, common, price_band, source_key, inventor) -> int`.
- `history.check_enablers(conn, p: Proposal, details: dict) -> None`: for a proposal that is or needs a technology (`details["needs_tech"]` list, or a technology word matched by `pending_enablers`), a missing enabler raises `AuthoringRefused(..., "contradiction")` naming it ("needs cellular networks; none exist on this date here"); distance ahead scales `ready_in_days` and failure odds written to `basis_json`, never a ceiling. A proposal that builds the enabler is accepted as his project.
- `foreknowledge.character_knows(conn, actor_id: int, subject_words: str, day: int) -> dict` returns `{"level": "none|hint|informed", "sources": [...]}` from `actor_competence`, employees with competence in the field (org seats or employment links), trade-press knowledge rows, and rumours he has heard; never from the player's context.
- Intake: when a proposal's `what` names a `foreseen` history entry (a bet on a future firm or event), `basis_json` records `{"foresight": true, "knows": level, "judged_as": "long_shot|informed"}`; the engine does not move any outcome for the player's foreknowledge.

- [ ] Tests: a pocket phone before cellular exists is refused naming the missing enabler; the same with his own funded enabler project accepted; cost grows with distance, no ceiling (a farther thing is still accepted if enablers exist); a foreseen-firm stake by a man with no competence is `long_shot`; the same stake after he hired an employee with competence in that field (set via `actor_competence` and a seat) is `informed`; an NPC owner gets the same judgement.
- [ ] Run; expect FAIL. Implement. Run; expect PASS.
- [ ] Commit `R1: technology enablers and foreknowledge`.

### Task 8: Effects at the run date, foreseen re-judging, the "what was due" prompt

**Files:** Modify `engine/history.py` (`settle_due`, `apply_effects`), `engine/simulation.py` (call next to the held tick; find how `held_things.process_due` is registered and mirror it, with its own process key and cadence 1 day only when a foreseen/in-force-pending entry is due, using `next_due_day`), the advance result builder (search `interrupt` in `connector/acting.py`/`engine/` for where interrupts are returned; add `history_due`), `worlds/saintjude/history.json` (`advance_prompt_classes`); create `tests/history_due_test.py`.

**Interfaces:**
- `history.settle_due(conn, day: int, *, event_logger=None) -> dict` re-judges each `foreseen` entry whose date arrived (Task 3 `judge`), sets status and run date, applies effects, mirrors `world_facts`.
- `history.apply_effects(conn, entry: dict, day: int) -> list[str]` by class: technology -> `tech_level` row; office/person_event -> `world_facts.holder_actor_id` when `effects` names an actor; law -> status `in_force` (read by `dated_rules`); culture/event -> a public rumour via the existing rumour maker; firm/firm_event/price -> recorded with `effects_json` and readable via lookup (business-layer readers plug in later; this leaves a gap row via `intake.bump_gap` with `missing=["a reader for firm/price effects"]`).
- `history.due_prompt(conn, from_day: int, to_day: int) -> list[dict]`: package-timeline defaults and foreseen entries dated within the interval, of classes in `advance_prompt_classes`, not yet entered: `{name, class, real_date, hint}`. The advance result carries them as `history_due`, with the GM told to look them up and propose only those his sphere touches.

- [ ] Tests: a foreseen entry judged when its date arrives gets `in_force`/`on_time`; with a divergence on its firm in between it comes out `later` or `changed`; effects row appears (tech_level for a technology); `advance` across a timeline default's date returns it in `history_due`, and not after it has been entered; no cost when nothing is due (the tick is not scheduled).
- [ ] Run; expect FAIL. Implement. Run; expect PASS.
- [ ] Commit `R1: effects, foreseen re-judging, history_due prompt`.

### Task 9: GM surface: lookup, verification, rulebook

**Files:** Modify `connector/views.py` (`lookup` kinds `"history"` and `"real:<name>"`, `"diverged"`), `connector/store.py` (`note(kind="fact")` on a `history:` key verifies a provisional entry: `cause` carries the source), `worlds/saintjude/rulebook_section.md`; create `tests/history_connector_test.py`.

**Interfaces:** `lookup("history")` lists recorded entries (key, what, real vs run date, outcome, status, provisional) and open provisional ones first; `lookup("real:<name>")` returns the documented figure (roles, record, source) or `found: false` with "propose him with a source via author"; `lookup("diverged")` lists divergences ("how has this world gone differently"). `facts.override` on `history:<slug>` with a source in `cause` sets `provisional=0`, `verify='verified'`, and re-judges if still `foreseen`.

- [ ] Tests (through the connector functions used by `tests/intake_test.py`): the three lookups; verification promotes a provisional entry; a Fixed history fact changed without a cause is refused.
- [ ] Rulebook text (Saint Jude only): look facts up when play reaches a domain; propose with source, honest `needs`, including the ones that would break it here; memory-sourced major facts are provisional; never narrate a fact the engine judged `never`; real people only in public roles; foreknowledge pays through learning and people.
- [ ] Run; expect PASS. Commit `R1: GM lookup, verification, rulebook`.

### Task 10: Play check, no-world-words, measures, report

**Files:** create `tests/history_play_test.py`; update `AGENTS.md` section 2 by one paragraph; write `.superpowers/sdd/2026-11-19-saintjude-org-core/task-R1-report.md`.

- [ ] Play test: from a scratch Saint Jude opening: propose a technology, a firm and a law through `author`; kill a figure; found a venture in a foreseen firm's field; advance across the real dates; assert outcomes, `history_due`, divergences, lookups and that an unrelated fact stayed `on_time`.
- [ ] Run the quick suite alone (`python tools/run_suite.py --out runs/suite`), compare failures with the nine known pre-existing failures in the I1 report; run `tests/no_world_words_test.py`; `git restore game/campaign_01/model_requests/`.
- [ ] Measure a 30-day and a one-year advance on a copy of `data/saintjude.db` (schema 127 migrated on the copy), before and after (stash nothing: use a pre-R1 copy migrated only to 126 for "before"); at most two long runs at once, never alongside the suite.
- [ ] Write the report (commits, tests, rulings, deferred: firm/price effect readers, market payoff for bets, which J1/other sessions' files were not touched). Commit `R1: report and AGENTS note`.
