# Handoff 2: Saint Jude bible reload, from Task 20 onward

> **Done (2026-10-24):** Tasks 20-23 and the report are finished; read `REPORT.md` in this folder instead.

**Written:** 2026-10-24. **Branch:** `feat/world-packages-saintjude`. Read in this order: `AGENTS.md`, `docs/superpowers/plans/2026-10-23-saint-jude-handoff.md` (§4 rules, §6 code map, §7 runbook), `HANDOFF.md` (this folder: the owner's brief, Steps 1 and 2, the E-check summary, the bible-problems list), then this file. This file supersedes HANDOFF.md §3, §4 and §6 where they differ.

**Commits:** `6a9a1fd` holds Steps 1 and 2 (the reload) and the investigation notes. **Everything below in §1 is uncommitted.** The owner commits when asked. Leave `.claude/`, `data/caerness.pre-schema110.db` and `game/campaign_01/backups/` alone.

**Working method the owner wants:** Sonnet subagents (`model: "sonnet"`) implement, each on a disjoint set of files. The lead reviews every diff. Never call the `caerness` MCP tools. Simulate only on scratch DBs (`CAERNESS_DB_PATH=runs/scratch_*/x.db`).

## 1. Done this session (uncommitted, each reviewed by the lead)

| Item | Files | Evidence |
|---|---|---|
| **E-005/006/008 Design figures**: each `draw` figure is drawn once per run from `world_state.rng_seed`, triangular on its range and peaked at the default. `fixed` figures take their default and `derived` figures are recomputed. Every value is logged with seed, day and cause. `set_figure` needs a cause, clamps to the range unless `exception=True`, and recomputes derived figures. Tables are created lazily, so Caerness gets none. | `engine/design.py` (new); hook at the start of `engine/activation.py` `activate_existing_loops`; `world.json` data `"design": "design_figures.json"` | `tests/design_figures_runtime_test.py` PASS |
| **Blocking population defect fixed**: Saint Jude no longer uses the Caerness 52M buckets. The package `background.scale` block gives the city 1,100,000 at the "Saint Jude" location and an unsplit, unplaced metro remainder of 1,300,000 (Part I 4.1: 2.4M metro − 1.1M city; the county split is Open). There are no military profiles. The city follows `population_decline_pct` each year through a `movement_net`. Birth rate 0.0146, infant mortality 0.016 and the US-1975 age shares are labelled assumptions (the bible is silent on all three). | `engine/scale.py`, `engine/background_population.py`, `worlds/saintjude/world.json` (background) | `tests/saintjude_population_test.py` PASS (5-year advance 20.8 s) |
| **E-009/E-020 dated rules, E-017 real people, E-023 real towns**: `veto.check_world_text` refuses text that names a timeline item not yet existing at the campaign date, or a real town replaced by the city. `canon_figure` refuses a real person's name. The hooks are in `act`, `check_proposal` (protagonist) and `author()` (all kinds). | `engine/veto.py` (`real_person`, `real_town`, `dated_rules`, `check_world_text`), `engine/world_package.py` (`timeline_mentions`, `not_yet_mentions`, `gazetteer`), `connector/acting.py`, `engine/authoring.py` (`author()` ~line 700), `worlds/saintjude/gazetteer.json`, `timeline.json` (9 aliases on the federal preventive-detention entry only) | `tests/saintjude_dated_rules_test.py` PASS (before the authoring hook was added; re-run) |
| **E-001/002/003 facts and Open slots**: the `world_facts` table holds tags, loaded at seed import from claims (now with an explicit `tag`), tagged timeline entries, Example persons and `meta.open_offices`. `author person` takes `holds`, so a second holder is refused with "held by X since <date>". `lookup` answers an office with its holder, or "Open: not yet decided". `note kind=fact` on a Fixed fact needs a `cause`. | `engine/facts.py` (new), `engine/current_seed.py`, `engine/authoring.py`, `connector/views.py`, `connector/store.py`, `connector/server.py`, `tools/saintjude_seed_data.py`, `tools/build_saintjude_seed.py`, `worlds/saintjude/seed.json` (regenerated), `tests/saintjude_snapshot_test.py` | `tests/saintjude_facts_test.py` PASS, `saintjude_snapshot_test` PASS (run by the lead after the rework) |
| **Canon paths, re-index, lore**: `## Part …` / `## Index …` is a level above the section headings, so no path is shared across Parts (99 shared paths remain, all consecutive pieces of one long section). A campaign is re-indexed when the bible's `canon_sources.content_hash` differs; Caerness is never re-indexed. `lore` returns whole paragraphs up to 4,000 chars, with `chunk <id> part N` continuation. | `engine/canon.py`, `connector/campaign.py`, `connector/lore.py` | `tests/saintjude_canon_paths_test.py` PASS; Caerness chunk count still 601 |

Caerness opening fingerprint (`tests/world_pkg_caerness_regression_test.py`) passed after the design, population, veto and canon changes ("445 tables"). **It has not been re-run since the facts rework (seed meta, claim tags, authoring hook): re-run it first.**

### Partly done, needs finishing (Task 21)
`tools/leak_scan.py` (394 lines) and `tests/saintjude_leak_scan_test.py` were written by an agent that was stopped before it reported. Review them against plan Task 21 and `step1_diff.md` §10 before trusting them. The test is expected to fail until the leaks are fixed. Known leaks to expect:
- `seed.json` still says "District Attorney" (meta.removed items ~line 221, 225: these are records of what was removed, probably allowed, decide) and the County Prosecutor notes say "there is no elected District Attorney" (fine as text).
- Place names step1_diff §10.3 lists as old-only but the seed still carries: Eastside Auto Crush, San Lorenzo Provisions Plant, Mercer Avenue Boxing Gym, Pier 4 Diner. Check each against the bible before changing anything; the bible is the authority.

## 2. First steps for the next agent

1. Re-run these on scratch DBs: `world_pkg_caerness_regression_test`, `world_pkg_caerness_connector_test`, `world_connector_test`, `saintjude_dated_rules_test`, `saintjude_facts_test`, `saintjude_population_test`, `saintjude_package_test`, `saintjude_snapshot_test`, `saintjude_canon_paths_test`, `design_figures_runtime_test`, `world_activation_switches_test`. Fix anything the facts rework broke.
2. Review the uncommitted diff (`git diff`, plus the untracked files in §1). Known review points:
   - `engine/facts.py` must hold no Saint Jude data. The office table moved to `seed.json` `meta.open_offices`; confirm nothing else is hard-coded.
   - `dated_rules` refuses any named timeline item before its date, including technology. Check that it does not refuse ordinary speech (the single-word alias rule: capitalised and at least 5 letters).
   - The gazetteer has 41 replaced towns, 37 of them `from_bible: false` (the agent's reading of the Part I 3.1a footprint). Perth Amboy, New Brunswick, Edison and Wall were left out as unclear. It also lists 19 real people. All of this is for the owner to confirm.
3. Ask the owner whether to commit this batch before Task 20.

## 3. Remaining work (plan `docs/superpowers/plans/2026-10-23-world-packages-plan.md`)

- **Task 20.** The opening now creates 64 background identity profiles (32 at Saint Jude, 32 unplaced in the remainder) and **no unnamed actors**. Before the population fix it made 544. Check this against the bible: Open items are invented when needed and then held (Part I 0.1, Part II 10); named men are Examples (Part III 4.6). Where the bible is silent on who exists at the start, say so and invent no rule. Then:
  - Time the run from the 1 Jan 1975 seed to the 1980 default entry (E-024).
  - Record the opening build time, the 30-day advance and the DB size in the plan's Measurements table and in `AGENTS.md`.
  - Write `data/saintjude.db`. `connector/campaign.py` `_packaged_db` expects it; the canon-paths test stubs it because it is missing.
- **Task 21.** Finish and run the leak scan (above). Remove leaks by gating or data fixes; allow-list only engine vocabulary that never reaches Claude.
- **Task 22.** Connector play test (`tests/saintjude_connector_play_test.py`, server module functions only). Plan Step 1, plus the owner's four cases:
  - A 1979 scene asking a federal judge to hold a boss without bail must be refused (veto exists).
  - A scene set in Red Bank must become a Saint Jude place (veto exists).
  - A Pad-paying family committing a public killing must still bring an arrest (Part II 3.4). Not built (E-014): report what happens.
  - Asking twice, a game-month apart, for the name of an Open official must get the same answer (facts store exists).
- **Task 23.** Full suite: `python tools/run_suite.py --out runs/suite`, then `git restore game/campaign_01/model_requests/`.
  - The baseline had 8 FAIL and 2 TIMEOUT, all pre-existing and unrelated (listed in HANDOFF.md §2). Report any others; do not change tests to pass unless they hard-code old bible values.
  - Then update the docs to cite the new bible's sections: AGENTS.md §2, `connector/README.md`, the Saint Jude handoff and the plan.
- **The single report** (HANDOFF.md §5).

## 4. E-item status after this session (update HANDOFF.md §3 / e_checks.md answers in the report)

- **Fixed now:** E-005, E-006, E-008 (design store). E-009, E-020 (named dated rules, engine refusal). E-017, E-023 (real people and towns; jurisdiction routing not built). E-001 (store, tags, lookup, Fixed needs a cause; no free-text contradiction detection, by design). E-002 (Open slots held). E-003 (claims tagged, by role).
- **Population part of E-025 fixed** (city path from the Design figure). Weekly and annual cycles are not built.
- **Still as in e_checks.md:**
  - E-007 (shared sector factor: no sectors yet), E-010, E-011 (pools are data only; `tools/check_saintjude_pools.py`).
  - E-012 to E-015, E-019, E-021, E-022, E-024, E-026 to E-028.
  - E-016 and E-018 are prompt-only. The narration-standards file is still missing (bible problem 23).
  - E-024 needs the Task 20 timing.

## 5. Bible problems to add to HANDOFF.md §6 (quotes verified 2026-10-24)

The lead checked items 1–24 of HANDOFF.md §6 against `worlds/saintjude/bible.md`; the quotes are present. Item 10's "the Pines (west, thirty miles)" is worded "Thirty miles west in Pine County" (Part I 6.4) and "**Pine County** (west)" (Part I 4.1). New:

25. **Part I 4.1** "**Fixed.** The **metropolitan area** has about **2.4 million** people." vs, in the same section, "The metropolitan total is Open; the suburbs take most of those who leave the city." Fix: mark 2.4M as the 1975 Fixed figure and say only its later path is Open. The engine uses 2.4M − 1.1M = 1.3M as the unsplit suburban remainder.
26. **Part I 4.1 / 3.1a silence:** the bible gives no population for the suburban counties (Marsh, Pine, Shore), Oakridge, or any district, and no birth rate, infant mortality or age structure. The engine uses an unplaced 1.3M remainder and recalled US 1975 national rates, labelled as assumptions. Fix: state per-county 1975 populations, or confirm that the unsplit remainder is intended.
27. **Part I 3.1a footprint:** "The real towns there (Long Branch, Asbury Park, Red Bank and their neighbors) do not exist". "Their neighbors" is not listed, so the engine's list of 37 further towns is an inference. Fix: list the replaced municipalities, or define the footprint boundary.
