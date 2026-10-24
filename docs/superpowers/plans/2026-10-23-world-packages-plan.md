# World Packages Implementation Plan (project 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The engine and connector read the world from a package; Caerness becomes the first package with identical behaviour; a Saint Jude package and 1975 starting snapshot produce an opening with no Caerness leaks, playable through the connector.

**Architecture:** A package is a directory `worlds/<id>/` with `world.json` (manifest + switches + small data tables) and files it points to (bible, seed, rulebook section, timeline, prices, archetypes). A new module `engine/world_package.py` loads it. A campaign records its package id in `engine_meta` (`world_package_id`; absent means `caerness`, so existing saves and the live campaign keep working). Every Caerness-specific engine behaviour is either read from the package or gated by a package switch; Caerness's package reproduces today's values exactly. Existing Caerness files (`canon/`, `game/seeds/`, `connector/rulebook.md`) stay where they are; the Caerness manifest points at them.

**Tech Stack:** Python 3.13, SQLite, stdlib only (no python-docx). Tests are plain scripts `tests/<name>_test.py` with a `run()`/asserts, discovered by `tools/run_suite.py` (every `tests/*_test.py`, own process, own scratch DB via `CAERNESS_DB_PATH`, `CAERNESS_TEST_MODE=1`).

**Spec:** `docs/superpowers/specs/2026-10-23-saint-jude-living-city-design.md` (esp. §3.15, §4 leak list, §6, §10, §11, §12, §14). Context and binding rules: `docs/superpowers/plans/2026-10-23-saint-jude-handoff.md`.

## Global Constraints

- Caerness must not change: a Caerness opening built after the change equals one built before (Task 1 fingerprint); `python tools/run_suite.py --out runs/suite` stays green (then `git restore game/campaign_01/model_requests/`).
- Package id is independent of display names: Saint Jude's id is `saintjude`; the city is "Saint Jude", Bellacorte is a district, "Port St. Jude" becomes "Killbuck Point", "Saint Jude's Meadowlands" becomes "the Pines", St. Jude's church (Kerrytown) is the cathedral.
- Nothing hard-coded: no fixed pressures or character secrets in the Saint Jude snapshot (Sally Glasses, Vinny Scales, the RICO trial, the container, the clerk are excluded). Taboos are data with consequences, never impossibilities.
- The engine runs no language model; it vetoes only named contradictions; no closed menus to Claude.
- Always simulate on a copy: `CAERNESS_DB_PATH=<scratch>`; never `data/caerness.db` or a live campaign. Never call the `caerness` MCP tools. Do not touch `.claude/`, `data/caerness.pre-schema110.db`, `game/campaign_01/backups/`.
- Python: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe"`; ad hoc scripts use `-I`; write script files, not one-line `python -c` with SQL quotes.
- Commit only when the owner asks. Commit steps below are written for when they do; executors skip them otherwise.
- Out of scope: POP-01, rising, ambitions, mafia system, pre-history run, run summary, plausibility wiring (projects 2 and 3).

## Review Focus

- A package id that does not exist, or a manifest with a missing file: clear error naming the package and file, not a traceback deep in the engine (Task 3).
- An existing Caerness save with no `world_package_id` row: loads as `caerness`, including after `init_db` migration (Task 3).
- A Saint Jude campaign opened on the Caerness rulebook or lore index by mistake: `resume` and `lore` must follow the campaign's package (Tasks 14, 15).
- A Gregorian date for day 0..N including leap years and weekday: no off-by-one at month/year ends (Task 5).
- A seed person whose `birth_date` is absent or malformed for the package's calendar: rejected with the person's name (Task 6).
- A Saint Jude opening that silently inherits a Caerness default (a name pool, a good, a region) because one activation step was missed: caught by the leak scan, not by eye (Task 19).

## File structure

- Create `engine/world_package.py`: manifest loader, `WorldPackage` dataclass, `current_package(conn)`, `set_campaign_package(conn, pkg_id)`.
- Create `engine/world_calendar.py`: calendar kinds (`sv`, `gregorian`) behind `format_date(pkg, day)`, `season(pkg, day)`, `birth_date_for(pkg, day)`, `weekday(pkg, day)`; `engine/civil_calendar.py` stays as the SV implementation.
- Create `worlds/caerness/world.json`, `worlds/saintjude/{world.json,bible.md,seed.json,rulebook_section.md,creation_section.md,timeline.json,prices_1975.json,archetypes.json,taboos.json,names.json}`.
- Modify: `engine/db.py` (init_db world name), `engine/current_seed.py`, `engine/activation.py`, `engine/background_population.py`, `engine/person_ecology.py`, `engine/business.py`, `engine/canon.py`, `engine/authoring.py`, `engine/new_character.py`, `engine/manners_canon.py`, `connector/campaign.py`, `connector/session.py`, `connector/views.py`, `connector/lore.py`, `connector/rulebook.md` (split), `run.py`.
- Tools: `tools/build_opening.py` (create; builds a package's opening DB), `tools/leak_scan.py` (create).
- Tests (all new, `tests/`): `world_pkg_caerness_regression_test.py`, `world_package_loader_test.py`, `world_calendar_test.py`, `world_seed_import_test.py`, `world_activation_switches_test.py`, `world_canon_md_test.py`, `world_connector_test.py`, `saintjude_package_test.py`, `saintjude_snapshot_test.py`, `saintjude_leak_scan_test.py`, `saintjude_connector_play_test.py`.

Task kinds: **M** = mechanical (cheap model fine); **J** = judgement-heavy (strong model, owner review where stated).

---

### Task 1 (M): Lock Caerness behaviour with a fingerprint

**Files:** Create `tools/build_opening.py`, `tests/world_pkg_caerness_regression_test.py`, `tests/fixtures/caerness_opening_fingerprint.json`.

**Interfaces:** Produces `build_opening(db_path: Path, seed_path: Path | None = None, package: str = "caerness") -> None` (init_db, `import_current_seed`, `activate_existing_loops`, commit; mirrors `run.py` `current-canon-bootstrap` minus coverage) and `fingerprint(db_path: Path) -> dict[str, str]` (table name -> sha256 of rows sorted by all columns, for every table except those listed in `VOLATILE` such as `scene_packets`, `connector_*`, timestamp columns named `*_at`; excluded columns documented in the test).

- [ ] **Step 1:** Write `tests/world_pkg_caerness_regression_test.py`: builds an opening in a scratch DB from `game/seeds/Caerness_Initial_World_State_Seed_v1_4.json`, builds it a second time, asserts the two fingerprints are equal (proves determinism), then asserts equality with `tests/fixtures/caerness_opening_fingerprint.json`.
- [ ] **Step 2:** Run with the fixture missing; expect FAIL (fixture absent). If the two fresh builds differ, find the nondeterministic columns (timestamps, rowids drawn from wall clock) and add them to `VOLATILE`/excluded columns until two builds match; record the exclusions in the test docstring.
- [ ] **Step 3:** Implement `tools/build_opening.py`; add `--write-fixture` that writes the JSON. Generate the fixture **on the unchanged code** (first commit of this branch's work).
- [ ] **Step 4:** Run `CAERNESS_DB_PATH=/tmp/x.db PYTHONPATH=. python tests/world_pkg_caerness_regression_test.py`; expect PASS. Record build time in the test output.
- [ ] **Step 5:** Commit `test: lock Caerness opening fingerprint`.

Every later task ends by re-running this test.

### Task 2 (M): Lock the Caerness connector surface

**Files:** Create `tests/world_pkg_caerness_connector_test.py`, `tests/fixtures/caerness_connector_surface.json`.

- [ ] **Step 1:** Test: copy the packaged `data/caerness.db` as a campaign (pattern from `tests/connector_campaign_test.py`: `CAERNESS_CAMPAIGN_DIR` temp dir, `open_campaign`), then assert the exact bytes of `connector.session.load_rulebook()` and `load_creation()` hash, `compact_scene(conn)["date"]` format string for day 0 (`1 First Month, 624 SV` style), and `lore(conn, "Cairnholt")` returns at least one passage. Hashes stored in the fixture.
- [ ] **Step 2:** Run to generate the fixture on unchanged code (flag `--write-fixture`), then run to PASS.
- [ ] **Step 3:** Commit.

### Task 3 (J): Package loader and campaign binding

**Files:** Create `engine/world_package.py`, `worlds/caerness/world.json`, `tests/world_package_loader_test.py`. Modify `engine/db.py` (`init_db` insert at line ~4751).

**Interfaces:** Produces
- `@dataclass(frozen=True) WorldPackage`: `id: str`, `display_name: str`, `root: Path`, `calendar: dict` (`{"kind": "sv"|"gregorian", ...}`), `bible_path: Path`, `bible_sha256: str | None` (None disables the firewall; Caerness keeps its check), `seed_path: Path`, `seed_namespace: str`, `rulebook_section: Path | None`, `creation_section: Path | None`, `systems: dict[str, bool]` (keys: `cultivation`, `elixir`, `hollow`, `groundbinding`, `caerness_underworld`, `caerness_religions`, `caerness_trade`, `merchant_houses`), `data: dict[str, Path]` (optional json tables), `name_pools: dict`.
- `load_package(pkg_id: str) -> WorldPackage` (raises `WorldPackageError("package 'x': file 'y' missing")`), `list_packages() -> list[str]`, `current_package(conn) -> WorldPackage` (reads `engine_meta.world_package_id`, default `"caerness"`), `set_campaign_package(conn, pkg_id) -> None`.
- `init_db()` inserts `world_state.world_name` from the package given by env `CAERNESS_WORLD_PACKAGE` (default `caerness` -> `'Caerness'`).

- [ ] **Step 1:** Tests: (a) `load_package("caerness")` has `calendar.kind == "sv"`, `bible_path == canon/world_bible_current.docx`, all `systems` true, `seed_namespace == "caerness_seed_v1_1"`; (b) unknown id and a manifest naming a missing file each raise `WorldPackageError` naming package and file; (c) a fresh DB has `current_package(conn).id == "caerness"`; after `set_campaign_package(conn, "saintjude")` (use a temp package dir from `tmp`, via `CAERNESS_WORLDS_DIR`) it returns that id; (d) DB with `world_state` but no meta row loads as caerness.
- [ ] **Step 2:** Run; expect FAIL (module missing).
- [ ] **Step 3:** Implement. Packages root: `worlds/` beside `engine/`, overridable by env `CAERNESS_WORLDS_DIR` for tests. Write `worlds/caerness/world.json` pointing at the existing files.
- [ ] **Step 4:** Run the new test and Task 1 test; PASS.
- [ ] **Step 5:** Commit.

### Task 4 (M): Package-aware campaign creation

**Files:** Modify `connector/campaign.py`, `connector/setup_campaign.py`; test `tests/world_connector_test.py` (first part).

**Interfaces:** `open_campaign(name: str, package: str | None = None) -> Path`. New campaigns copy `PACKAGED_DB` for caerness or `data/<package>.db` (Saint Jude's packaged opening, built in Task 20) and call `set_campaign_package`; an existing campaign file ignores `package`. `--package` option in `setup_campaign.py`. Canon indexing fallback in `open_campaign` uses `current_package(conn).bible_path`.

- [ ] **Step 1:** Test: opening a campaign with no package gives `current_package == caerness`; with `package="nope"` raises `WorldPackageError` and leaves no file; existing campaigns are never re-copied (extend the `marker` check in `connector_campaign_test.py` style).
- [ ] **Step 2-4:** Run FAIL, implement, run PASS plus `tests/connector_campaign_test.py` and Task 2.
- [ ] **Step 5:** Commit.

### Task 5 (M): Calendar behind the package

**Files:** Create `engine/world_calendar.py`, `tests/world_calendar_test.py`. Modify `connector/views.py:260,312` to call `world_calendar` with `current_package(conn)`.

**Interfaces:** `format_date(pkg, day) -> str` (sv: `civil_calendar.format_sv_date`; gregorian: `"Tuesday 14 October 1980"` from `calendar.start` = ISO date of day 0), `season(pkg, day) -> str` (northern-hemisphere meteorological for gregorian), `birth_date_for(pkg, birth_day) -> str` (same text as `format_date`), `day_for_date(pkg, text) -> int`.

- [ ] **Step 1:** Tests: sv outputs equal `format_sv_date`/`season_for_day` for days 0, 364, 365, -3650; gregorian with start `1975-01-01`: day 0 is `Wednesday 1 January 1975`, day 59 is `Saturday 1 March 1975`, day 1825 is `Monday 1 January 1980` (leap days 1976 and 1980 counted), `season` of day 0 is Winter; negative days work; `day_for_date` round-trips.
- [ ] **Step 2-4:** FAIL, implement (stdlib `datetime`), PASS; Task 2 test still PASS (Caerness date text unchanged).
- [ ] **Step 5:** Commit.

### Task 6 (J): Seed import reads the package

**Files:** Modify `engine/current_seed.py`; test `tests/world_seed_import_test.py`.

**Interfaces:** `import_current_seed(conn, seed_path=None, package: WorldPackage | None = None)`; package defaults to `current_package(conn)`. Uses `package.seed_namespace` (replace `SOURCE_NAMESPACE` use sites; keep the module constant as the Caerness default for callers/tests that import it), `package.bible_sha256` for the firewall (skip when None), `world_calendar.birth_date_for` for `_validate_person_chronology` (field name `birth_date` accepted alongside legacy `birth_date_sv`), and a seed-level `longevity_field`: when `package.systems["cultivation"]` is false, longevity is `ordinary` and `stage` is ignored.

- [ ] **Step 1:** Tests using a tiny Gregorian package built in a temp worlds dir and a 3-person seed: imports under its own namespace and the Caerness namespace is untouched; a person with a wrong `birth_date` raises naming the person; a bible-hash mismatch raises only when the package has a hash; `stage: "Sixth"` in a non-cultivation package yields `longevity_class == "ordinary"` in the health profile.
- [ ] **Step 2-4:** FAIL, implement, PASS; Task 1 test PASS.
- [ ] **Step 5:** Commit.

### Task 7 (J): Gate Caerness-only activation steps by package switches

**Files:** Modify `engine/activation.py` (`activate_existing_loops`, lines 1075-1151), `engine/db.py` as needed; test `tests/world_activation_switches_test.py`.

**Interfaces:** `activate_existing_loops(conn, package: WorldPackage | None = None)`; a module table `STEP_SWITCH: dict[str, str]` maps each step (by function name) to the `systems` key that must be true, e.g. `seed_cultivation_from_current_source`, `activate_elixir_substrate`, `seed_current_groundbinding`, `activate_hollow_substrate`, `activate_tournament_substrate`, `activate_spectacle_substrate` -> their switch; `activate_underworld_substrate`, `seed_all_settlements` -> `caerness_underworld`; `activate_religion_and_culture` -> `caerness_religions`; `activate_aggregate_trade`, `activate_economic_substrate` (Caerness goods/regions) -> `caerness_trade`; merchant-noble House creation inside `activate_economic_substrate` -> `merchant_houses`. Steps whose Caerness parts are inline (religions, paintings, Vein-Root goods, Houses) are split so the world-specific part is a separate function gated by the table. `out` records `skipped_steps` listing disabled ones. Caerness (all true) runs the identical sequence.

- [ ] **Step 1:** Test: (a) with a package whose `systems` are all false except what the seed needs, an opening from a 5-person non-Caerness seed creates zero rows in `cultivation_profiles`, `elixir_*`, `hollow_*`, `religions`-type tables (list the tables by `sqlite_master` name pattern in the test), and none of the Caerness constants appear (`SELECT` on goods/religion names for 'Vein-Root', 'Salt Road'); (b) for Caerness the returned `out` keys equal a snapshot stored in the test (key set only).
- [ ] **Step 2:** Run; FAIL. Expect the first runs to reveal further inline Caerness seeding; each discovery is added to `STEP_SWITCH` or split out, and listed in the test's table-name list.
- [ ] **Step 3-4:** Implement, PASS, Task 1 PASS.
- [ ] **Step 5:** Commit.

### Task 8 (J): Background population, names and day-0 marriages from the package

**Files:** Modify `engine/person_ecology.py` (`activate_background_people`), `engine/background_population.py` (`_AGE_BANDS`, `_mortality_probability`, `activate_population_sources`), `engine/opening_family.py` (day-0 spouses); test additions in `tests/world_activation_switches_test.py`.

**Interfaces:** package `name_pools` (`{"male": [...], "female": [...], "family": [...]}` weighted by `names.json` ethnicity mix) replaces Caerness pools when present; `mortality` table in `world.json` (`{"model": "gompertz_premodern"|"table", "table": {...}}`) with Caerness = current function; `background.stage_distribution: false` stops cultivation Stage assignment; `opening_family.marry_adults_on_day0: false` skips the invented day-0 spouse for named adults of the seed (Saint Jude: a widower stays a widower; seed relationships are authoritative).

- [ ] **Step 1:** Tests: with a package providing 10 names and `marry_adults_on_day0=false`, all background people's names come from the pools, no `cultivation_profiles` rows exist, a seeded widower has zero `unions`; the 1980-US `table` mortality returns a smaller annual probability at age 30 than the Caerness model and is monotone by age (assert specific bounds: 30-year-old male annual death between 0.001 and 0.004; 80-year-old between 0.05 and 0.12).
- [ ] **Step 2-4:** FAIL, implement, PASS, Task 1 PASS.
- [ ] **Step 5:** Commit.

### Task 9 (M): Business archetypes from the package

**Files:** Modify `engine/business.py` (`_ARCHETYPES`, `seed_business_archetypes`), `engine/authoring.py:367`, `engine/world_pressure.py:222`; test addition `tests/world_activation_switches_test.py`.

**Interfaces:** `archetypes(conn=None) -> dict[str, dict]` returns the package's `archetypes.json` if the package defines one, else the module `_ARCHETYPES` (Caerness). The three readers call `archetypes(conn)`. JSON entries have the same keys as `_ARCHETYPES` values (`name, sector, enterprise_kind, base_revenue, cost_ratio, weights, regulation, skill_sensitive, capital_sensitive`).

- [ ] **Step 1:** Test: a package with one `pizzeria` archetype seeds only that row into `business_archetypes`; `authoring`'s archetype guess for text "a pizzeria on Ocean Ave" returns it; Caerness still returns `inn`.
- [ ] **Step 2-4:** FAIL, implement, PASS, Task 1 PASS.
- [ ] **Step 5:** Commit.

### Task 10 (M): Bible indexing from a package (Markdown with real headings)

**Files:** Modify `engine/canon.py` (`index_canon`, `search_canon` fallback at line 282, add `extract_markdown_blocks`); test `tests/world_canon_md_test.py`.

**Interfaces:** `extract_markdown_blocks(path: Path) -> list[tuple[str, str]]` returns `("Heading N", text)` for `#`-prefixed lines and `("Normal", text)` for other non-empty lines, so `_chunk_blocks` is unchanged; `index_canon(path)` dispatches on suffix (`.md` vs `.docx`); `DEFAULT_CANON` stays as the Caerness default; `search_canon` fallback and `connector/lore.py` index the current package's `bible_path`. `bible_path` for Saint Jude is `worlds/saintjude/bible.md` (Task 15 authors it; no python-docx or Word needed).

- [ ] **Step 1:** Test: a 3-heading md file yields chunks whose `heading_path` is `"A > B"` for a `##` under `#`; `index_canon` of `canon/world_bible_current.docx` output identical chunk count to before (read the count from the Task 2 fixture).
- [ ] **Step 2-4:** FAIL, implement, PASS, Task 1/2 PASS.
- [ ] **Step 5:** Commit.

### Task 11 (M): Etiquette text and "martial standing"

**Files:** Modify `engine/manners_canon.py` (line ~36 and any Stage wording), `connector/views.py`; test addition `tests/world_connector_test.py`.

**Interfaces:** `manners_for(conn, location_id)` reads manner phrases from `current_package(conn).data["manners"]` when present (JSON list of generic phrases keyed by place kind), else the existing Caerness text. Saint Jude supplies its own phrases in Task 15. Stage-based words in `temperament.py`, `person_ecology.py`, `veto.py`, `authoring.py`, `new_character.py` are guarded by `systems["cultivation"]`: when off, `stage` is ignored in proposals and never mentioned in veto reasons.

- [ ] **Step 1:** Test with a no-cultivation package: `author kind=person` with `stage="Sixth"` neither raises nor stores a cultivation profile; `compact_scene` contains no substring "martial", "Stage" or "cultivat".
- [ ] **Step 2-4:** FAIL, implement, PASS, Task 1/2 PASS.
- [ ] **Step 5:** Commit.

### Task 12 (J): Underworld off for non-Caerness packages

**Files:** Modify `engine/underworld*.py` entry points called from `engine/simulation.py` (find with `grep -n underworld engine/simulation.py engine/scheduler*.py`); test addition `tests/world_activation_switches_test.py`.

- [ ] **Step 1:** Test: a 30-day `advance_connection` on a package with `caerness_underworld=false` produces zero rows in `underworld_*` tables and no actor named by `underworld_canon` patterns; Caerness unchanged (Task 1 PASS, and `tests/underworld_*` suite tests PASS).
- [ ] **Step 2-4:** FAIL, gate the scheduler registrations by switch (not by deleting code), PASS.
- [ ] **Step 5:** Commit.

### Task 13 (M): Gate remaining simulation-time Caerness systems

**Files:** scheduler registrations for cultivation, elixir, hollow, groundbinding, tournaments, spectacle, religion, aggregate trade (same grep method as Task 12).

- [ ] **Step 1:** Test: 30-day advance on the no-switch test package from Task 7 produces zero rows in the tables for those systems and does not raise.
- [ ] **Step 2-4:** FAIL, gate, PASS; run the full suite once (`python tools/run_suite.py --out runs/suite`), expect all green; `git restore game/campaign_01/model_requests/`.
- [ ] **Step 5:** Commit.

### Task 14 (M): Rulebook split into core plus world section

**Files:** Create `connector/rulebook_core.md`, `worlds/caerness/rulebook_section.md`, `worlds/caerness/creation_section.md`; modify `connector/session.py` (`load_rulebook`, `load_creation`, `RULEBOOK_PATH`), `connector/server.py` INSTRUCTIONS/tool docstrings (use the package display name); test `tests/world_connector_test.py`.

**Interfaces:** `load_rulebook(conn=None) -> str` = core + "\n\n" + package section (campaign's package). Split `connector/rulebook.md` so the Caerness text is moved verbatim: the shared core holds the GM/engine split, voice, reading the player, pacing, protagonist, mistakes, continuity; the Caerness section holds the Caerness-specific lines ("You are the game master for Caerness", Stage/House/standing/"old Caerness" lines, money-currency line). The concatenation for Caerness must hash identical to the old file (Task 2 fixture), so split by exact line moves and reassemble in original order using markers, not by rewriting.

- [ ] **Step 1:** Test: Caerness `load_rulebook()` hash equals Task 2 fixture; a Saint Jude campaign's rulebook contains none of "Caerness", "Stage", "cultivat", "House", "SV", "Hollow".
- [ ] **Step 2-4:** FAIL, implement (the section for Saint Jude is a stub until Task 16), PASS.
- [ ] **Step 5:** Commit.

### Task 15 (J): Lore and resume follow the campaign's package

**Files:** Modify `connector/lore.py`, `connector/session.py`, `connector/views.py`; test `tests/world_connector_test.py`.

- [ ] **Step 1:** Test: a campaign built from a temp package indexes that package's bible on open and `lore(conn, query)` returns its text, not Caerness's; `resume` returns the matching rulebook and a date in the package's calendar format.
- [ ] **Step 2-4:** FAIL, implement, PASS; Task 2 PASS; run `connector_*` tests.
- [ ] **Step 5:** Commit.

*Checkpoint:* engine and connector are package-driven and Caerness is provably unchanged. Everything below is Saint Jude content.

---

### Task 16 (J): Adapt the codex into the Saint Jude bible (`bible.md`)

**Files:** Create `worlds/saintjude/bible.md`, `tests/saintjude_package_test.py` (bible part).

Extract the codex text with `zipfile` + regex over `word/document.xml` (script in the session scratchpad, not committed; the codex already uses `#`/`##`/`###` lines, so keep them as Markdown headings). Authoring rules:
- Keep Layer 1 (setting bible §1-6) and the street dictionary §14, Appendix A (dated tech/legal), Appendix B (prices, as the 1980 reference). Drop Layer 3 §10 NPC profiles and §11 pressures from the bible (they feed the snapshot, Task 19, and pressures are not stored at all). Layer 2 §7-8 becomes the Saint Jude rulebook section (Task 17), not the bible.
- Apply the renames (handoff §2): Bellacorte -> district in the geography section; Port St. Jude -> Killbuck Point; Saint Jude's Meadowlands -> the Pines; St. Jude's (Kerrytown) -> the founding church and cathedral. Add the founding story of design §3.15 as a section "Founding and history" with the historical caveat.
- Fix codex defects (design §14): garbled figures in §8.1 (sports book and numbers math), §8.2 (rank capital column), §12.2 item 4, §13.2 items 3 and 6, §11 Pressure 2 heading (drop §11 outright). Where a figure cannot be recovered from context, recompute from Appendix B and state the assumption inline as "Assumption:". List every fix in a `## Adaptation notes` section.
- Remove the hard-coded secrets and trial/container/clerk/Sally Glasses/Vinny Scales text from bible passages (examples may remain only as clearly labelled "Examples of the kind of pressure Claude might invent").
- Taboos (§3.2 of the codex and design §7) are written as "taboo with consequences, never impossible; who cares and how they react".

- [ ] **Step 1:** Test: `bible.md` indexes via Task 10 into >= 60 chunks, every chunk has a non-"Document" heading path; none of the strings `Bellacorte` appear as a city name pattern `"city of Bellacorte"|"Bellacorte, "` (district use allowed: assert that the string `Port St. Jude` and `Meadowlands` are absent); the strings `Sally Glasses`, `Vinny Scales` appear only under the heading containing `Examples`; `lore("Killbuck Point")` returns a passage.
- [ ] **Step 2-4:** FAIL, author, PASS.
- [ ] **Step 5:** Commit. **Owner-review checkpoint (light):** show the Adaptation notes list.

### Task 17 (J): Saint Jude rulebook and creation sections

**Files:** Create `worlds/saintjude/rulebook_section.md`, `worlds/saintjude/creation_section.md`, `worlds/saintjude/manners.json`.

Rulebook section from codex Layer 2 §7-8, adapted: plain-English intent rule with the review's clarified player-agency wording (Claude may render routine actions that follow stated intent, never consequential decisions, loyalties, commitments or betrayals), the 5-step continuity protocol, information boundaries, knowledge/rumour timings (hours street, a day barbers and bondsmen, two days papers) as tendencies, "tendencies not absolutes" for police/Feds, dated-technology rule, money/accounting vocabulary with no engine figures in prose, taboo wording, no fixed pressures: Claude invents pressures and the engine vetoes contradictions. Creation section: the protagonist is always a new person (no codex figures), 1980s setting vocabulary (work, family, ties, neighbourhood), no Stage. `manners.json`: generic phrases for bar, club, church, precinct, office, street keyed by place kind.

- [ ] **Step 1:** Test in `saintjude_package_test.py`: the three files exist; sections contain none of the Caerness forbidden words (list shared with Task 19 via `tools/leak_scan.py::FORBIDDEN`); `rulebook_section` mentions "veto" and not "menu of"; `manners.json` has a phrase for each place kind used in the snapshot (Task 19).
- [ ] **Step 2-4:** FAIL, author, PASS; Task 14 test PASS with real section.
- [ ] **Step 5:** Commit.

### Task 18 (J): Saint Jude package data: manifest, calendar, timeline, prices, archetypes, taboos, names, mortality

**Files:** Create `worlds/saintjude/world.json`, `timeline.json`, `prices_1975.json`, `archetypes.json`, `taboos.json`, `names.json`; extend `tests/saintjude_package_test.py`.

- `world.json`: `id: "saintjude"`, display name "Saint Jude", `calendar: {kind: gregorian, start: "1975-01-01"}` (snapshot day 0 = 1 January 1975, the owner's date), all Caerness `systems` false, `bible_sha256: null`, `seed_namespace: "saintjude_seed_v1"`, mortality `{model: table}` from published 1975-80 US life table values (record the source and year as an assumption in the file), `name_pools` pointer, `background.stage_distribution=false`, `opening_family.marry_adults_on_day0=false`.
- `timeline.json`: list of `{name, exists, available, common}` ISO dates from codex Appendix A (pagers, cellular phone, fax, VCR, answering machine, Title III wiretap rules, RICO 1970 and its use dates, Witness Security, money-laundering statutes, etc.). Each date sourced in a `source` field. Structured so a later project can query by name and date; this project only provides a loader `timeline_status(pkg, name, date) -> "unknown"|"not_yet"|"exists"|"available"|"common"` in `engine/world_package.py`.
- `prices_1975.json`: codex Appendix B values restated at 1975 from the same historical sources (CPI ratio 1975/1980 with the table of national benchmarks kept apart from Saint Jude estimates); every figure carries `basis` and `assumption: true`.
- `archetypes.json`: bar, diner, pizzeria, social club, nightclub, trucking firm, warehouse, car dealership, construction firm, laundromat, vending route, numbers bank, sports book, bakery, butcher, funeral home, union local office; keys as `_ARCHETYPES`, dollars from `prices_1975.json`, demand weights using the existing commercial-context keys read from `engine/business.py` `commercial_context`.
- `taboos.json`: killing a cop; killing a reporter; killing or striking a made man without sanction; holding out; informing; narcotics where forbidden; a made man's wife; violence in the Oakridge sanctuary; disrespecting a boss in public. Fields `who_cares`, `typical_reactions` (ranges), `can_be_permitted_by`. Never a "forbidden" flag.
- `names.json`: weighted ethnic mix (Italian, Irish, Black, Jewish, Russian, Puerto Rican, old-money WASP) with male, female, family pools of >= 40 names per group.

- [ ] **Step 1:** Tests: `load_package("saintjude")` succeeds; `timeline_status(pkg, "cellular phone", "1975-06-01") == "not_yet"` and `"pager"` is `"available"` in 1980; every price row has `basis`; every archetype validates the same required keys as `_ARCHETYPES`; every taboo has `who_cares` and no key named `forbidden|impossible|never`; names pools sizes.
- [ ] **Step 2-4:** FAIL, author/implement, PASS.
- [ ] **Step 5:** Commit.

### Task 19 (J): The 1975 starting snapshot `seed.json` (back-dating) **[OWNER-REVIEW CHECKPOINT]**

**Files:** Create `worlds/saintjude/seed.json`, `tools/leak_scan.py` (built in Task 21, not here), `tests/saintjude_snapshot_test.py`; helper `tools/build_saintjude_seed.py` (authoring script producing deterministic JSON from a hand-written Python data module `tools/saintjude_seed_data.py`; ids stable, sorted).

Seed format = `game/seeds/Caerness_Initial_World_State_Seed_v1_4.json` (places with `parent_ref`, routes, institutions, persons with `age/birth_day/birth_date`, relationships, households, cohorts, claims, processes, `latent_population_controls`). Authoring rules (design §6):
- **Day 0 = 1 January 1975.** Everyone is five years younger than the codex's 1980 age; `birth_day = -(age*365 + offset)` consistent with Gregorian `birth_date` (validated by Task 6).
- **Posts at 1975:** each 1980 post is re-assigned to what the man plausibly held then (Mikey Saints 24 and not a capo; some 1980 capos are soldiers; some 1980 bosses are underbosses/capos under men the codex never names; add those unnamed men with ids prefixed `sj:person:`). Record every re-assignment in `seed.json` `meta.backdating_notes` (person, 1980 post, 1975 post, reason).
- **Remove post-1975 history** from the snapshot: the 1977 Barber Shop hit on Don Giuseppe Vannucci (he is alive in 1975 with the post he held), recent buttons, businesses founded after 1975 (*The Starlight* as a disco), anything the timeline places after 1975-01-01. Keep 1946 Harbor War, 1958 Moretti schism, 1967 Vannucci split, 1973 dock strike massacre, 1974 Concrete Purge as `claims`.
- **Places:** city Saint Jude; districts incl. Bellacorte (Italianate), Kerrytown (St. Jude's cathedral), Killbuck Point, the Pines, Oakridge, Brighton Point, the Hill (St. Rocco's); the 10 places of the throwaway test plus every codex §2 location; routes between districts with travel days.
- **Institutions:** four families, Charlestown Brigades, Vorovskoy, Mercer Street Kings, Iron Horsemen, BCPD, 14th Precinct, FBI Strike Force, City Hall, DA/Blum's office, unions, papers, Archdiocese, major businesses and fronts (as 1975 businesses with owners).
- **Persons:** codex §10 cast with ages/posts back-dated; **no** pressure text, secrets, or the trial/container/clerk. `public_identity_text` only; the `current` field (private vector) holds motives as ordinary traits, not plot hooks.
- **Defect fixes** apply to any numbers copied from the codex (design §14).
- Money: seed `economic_state` values from `prices_1975.json`.

- [ ] **Step 1:** Tests (`tests/saintjude_snapshot_test.py`): seed validates (every `*_ref` resolves; every person passes Gregorian chronology; no duplicate ids); counts at least: 4 families, 5 outside/law institutions, 40 persons, 30 places; no person has age equal to the 1980 age recorded in `meta.codex_1980_ages` (all exactly 5 younger); Matthew/Matty-type trial text, `Sally Glasses` secret, `container`, `clerk` strings absent from every `notes/current/public_identity_text`; no person born after day 0; Don Vannucci is `living`; no institution `founded` after 1975; `meta.backdating_notes` non-empty and covers every person whose post changed.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Author data module and build script; generate `seed.json`.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit. **STOP for owner review:** present `meta.backdating_notes` as a table (person, 1980 post, 1975 post, reason) plus the added unnamed men and removed post-1975 history. Proceed to Task 20 only after the owner accepts or amends (amendments edit the data module and regenerate).

### Task 20 (J): Build the Saint Jude opening; measure; package it

**Files:** Modify `tools/build_opening.py`, `run.py` (`current-canon-bootstrap --package`); create `data/saintjude.db` (built artifact, committed like `data/caerness.db`), `docs/superpowers/plans/2026-10-23-world-packages-measurements.md` is NOT created; measurements go in the plan's final section (below) and in `AGENTS.md` §2.

- [ ] **Step 1:** Run `build_opening(Path(scratch), package="saintjude")` with `CAERNESS_WORLD_PACKAGE=saintjude`; expected first failure is unresolved Caerness assumptions in activation steps not yet gated. Fix each by extending `STEP_SWITCH` or the package data (Tasks 7-9), never by special-casing Saint Jude in the engine.
- [ ] **Step 2:** Time the build (`time` around `build_opening`) and a 30-day `advance_connection(conn, 30)` on a copy, on the PC; repeat on the Oracle VM profile if the owner has deployed (otherwise record PC only and say so). Record: opening seconds, 30-day seconds, DB size, actor/location counts.
- [ ] **Step 3:** Write `data/saintjude.db`; set `init_db` meta `world_package_id=saintjude` inside it; `open_campaign(name, package="saintjude")` copies it.
- [ ] **Step 4:** Test: `tests/saintjude_package_test.py` builds from seed in a temp DB, `current_package(conn).id == "saintjude"`, `world_state.world_name == "Saint Jude"`, a 30-day advance completes without exception and `current_day == 30`.
- [ ] **Step 5:** Commit.

### Task 21 (M): Automated leak scan

**Files:** Create `tools/leak_scan.py`, `tests/saintjude_leak_scan_test.py`.

**Interfaces:** `FORBIDDEN: tuple[str, ...]` (Caerness names/places/goods/religions drawn from the Caerness DB at scan time: all `locations.name`, `religions`/culture names, `goods.name`, `actors.name` of `data/caerness.db` that are not also in the Saint Jude seed; plus fixed words `cultivat`, `Stage`, `Vein-Root`, `SV`, `Hollow`, `Veinborn`, `martial`, `Salt Road`, `Aldergate`); `scan(db_path: Path) -> list[Leak]` (table, column, row id, matched string) over every TEXT column of every table (`sqlite_master` loop), excluding `canon_chunks` of other packages and engine vocabulary tables listed in `ALLOW_TABLES` with a reason each.

- [ ] **Step 1:** Test: builds a Saint Jude opening, runs a 30-day advance, indexes the bible, then `scan()` returns an empty list; also a negative control (insert a row containing "Vein-Root"; scan finds it).
- [ ] **Step 2:** FAIL initially (expect real leaks: engine vocabulary rows, default strings). For each leak decide: remove by gating (preferred), or add to `ALLOW_TABLES` only if it is engine vocabulary that never reaches Claude (justify in the file).
- [ ] **Step 3-4:** Fix until PASS; Task 1/2 PASS.
- [ ] **Step 5:** Commit.

### Task 22 (J): Playable through the connector

**Files:** Create `tests/saintjude_connector_play_test.py`.

- [ ] **Step 1:** Test using temp `CAERNESS_CAMPAIGN_DIR` and the server module functions (not the MCP tools): `open_campaign("sj", package="saintjude")`; `resume` (needs_character, rulebook has Saint Jude section, no leak words); `author kind=protagonist` with an invented 28-year-old tavern worker in Kerrytown (accept=true) succeeds; `set_player`; `compact_scene` shows a Gregorian date `Wednesday 1 January 1975`, people present with Saint Jude names, no leak words in the JSON dump; `lore("St. Jude's")` returns the cathedral passage; `act` with a free-text intent resolves; `advance` 30 days returns without error and the new date is `Friday 31 January 1975`; `author kind=business` "pizzeria" accepted; re-run `leak_scan` on the campaign DB: empty.
- [ ] **Step 2-4:** FAIL, fix generic gaps found (never Saint Jude special cases), PASS.
- [ ] **Step 5:** Commit.

### Task 23 (M): Full regression, docs and handoff

**Files:** Modify `AGENTS.md` §2 (stream state, package layout, how to build a package opening, measured numbers), `connector/README.md` (package selection), `docs/superpowers/plans/2026-10-23-saint-jude-handoff.md` (mark project 1 done, point at projects 2 and 3).

- [ ] **Step 1:** `python tools/run_suite.py --out runs/suite`; expect every test PASS, including all new ones; then `git restore game/campaign_01/model_requests/`.
- [ ] **Step 2:** Re-run Task 1 and Task 2 tests; confirm the fixtures were never regenerated since Tasks 1-2 (`git log -- tests/fixtures`).
- [ ] **Step 3:** Update docs with measurements: opening seconds, 30-day advance seconds, db size (PC and, if available, VM).
- [ ] **Step 4:** Commit; tell the owner the VM needs `update.sh` plus `data/saintjude.db` shipped for a Saint Jude campaign, and that existing Caerness campaigns need nothing.

## Self-review notes

- Spec coverage: §4 leak list: current_seed namespace/firewall/SV dates/stage (6), init_db name (3), activation Houses/religions/paintings/elixir/trade/background/day-0 spouses/underworld (7, 8, 12, 13), underworld names (12), business archetypes (9), canon path and headings (10), views etiquette and dates (5, 11), per-person cultivation profile (7, 11); package selection (3, 4, 15); rulebook split (14, 17); calendar, money, timeline, taboos, names, mortality, switches (18); snapshot, back-dating, renames, defect fixes (16, 19); no-leak test (21); playable (22); speed (20); Caerness unchanged (1, 2, 23).
- Not built here by design: price ledger moving year by year, plausibility checks using the timeline (`timeline_status` only exposes data), POP-01, mafia, pre-history.
- Types: `WorldPackage` fields, `current_package`, `set_campaign_package`, `load_package`, `archetypes(conn)`, `format_date(pkg, day)` are used with the same names throughout.

## Measurements (filled by Task 20)

Measured 2026-10-24 on the PC (`runs/h2/build_sj.py`, `runs/h2/five_years.py`). The Oracle VM has no Saint Jude campaign yet, so there is no server column.

| Measure | PC | Server profile |
|---|---|---|
| Saint Jude opening build (`python tools/build_opening.py --package saintjude`) | 2.6 s | not measured |
| 30-day advance | 0.1 s | not measured |
| 1 Jan 1975 to 1 Jan 1980 (E-024 default entry) | 18.9 s (3.1 to 4.4 s a year) | not measured |
| DB size | 5.8 MB opening (`data/saintjude.db`); 8.0 MB after 30 days with the bible indexed; 9.2 MB at 1 Jan 1980 | |
| Opening contents | 134 actors (51 seeded Example persons plus the seeded institutions' actors), 70 locations, 83 institutions, 64 background identity profiles, no unnamed people | |
