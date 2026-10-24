# Handoff: Saint Jude bible reload, Steps 3–4 and the report

**Written:** 2026-10-24. **Branch:** `feat/world-packages-bellacorte`. **Nothing is committed** (the owner commits when asked). Read `AGENTS.md`, then `docs/superpowers/plans/2026-10-23-saint-jude-handoff.md` (§4 rules, §6 code map, §7 runbook), then this file.

## 0. The owner's brief (binding, summarised)

The owner supplied a new Saint Jude bible (Index + Parts I–VI, in `C:\Users\NozzE\Downloads\Saint_Jude_Bible_*.md`) and `C:\Users\NozzE\Downloads\Saint Jude Engine Implications.md` (E-001 to E-028). Rules:

- The seven bible files are the **only authority** on the world. Where they disagree with seed data, fixtures, prompts, tests or docs, the files win.
- **Never edit the bible files.** If something in them is wrong, unclear or cannot run, list it with file, section, exact quote and a proposed fix. Do not guess around it. Where the bible is silent, say so; do not invent a rule.
- Every Engine Implications item is a **question**, answered yes/no from the code with evidence (file and function, or a test you ran). Critical + small + clearly within the engine: fix now. Otherwise list it with what the fix would take. **Start with the ten checks at the end of that document, in that order** (E-005, E-011, E-001, E-009, E-024, E-016, E-010, E-015, E-023, E-026).
- Each Design figure keeps its default and range; each item keeps its tag (Fixed, Open, Weather, Anchor, Tendency, Design, Example).
- Tests: fix only those that fail because they hard-code old bible values; list any other failure and do not change it to pass.
- **Save tokens:** the owner wants implementation done by Sonnet subagents (`model: "sonnet"`), with the lead reviewing diffs. Give each agent disjoint files.

Steps 1 and 2 are done (below). **Your job: Step 3, Step 4 (Tasks 20–23), then the single report** (section 5).

## 1. Step 1 (done): the diff

`step1_diff.md` (this folder) lists every old-bible figure, rule, name and tag in the package against the new bible, grouped by area. Its section 10, "OLD-ONLY STRINGS", is the scan list for Task 21. Main changes: Castellano→Pellegrino and Moretti→Ferrante; Part III 4.6 seats as Examples; Oakridge in Marsh County (W/NW), outside the city; officials Open; the Mercer Street Kings and a headed Vorovskoy do not exist in 1975; Concrete Purge outcome and Ferrante Schism instigator Open; money rebuilt from Part VI; Pellegrino 40–50 (default 45, 51–55 only with a dated cause); 11 naming groups; taboos 15 + 8 plus "women never made" (no price); timeline corrected (pen register June 1979, Parness Oct 1973, bail 1984, union bar 5→13 years on 12 Oct 1984, SCI 1968/1969, Elizabeth 15 Aug 1962).

## 2. Step 2 (done): the reload

| File | State |
|---|---|
| `worlds/saintjude/bible.md` | The seven files joined verbatim by a blank line. `tools/build_saintjude_bible.py [--check]`; hashes in `worlds/saintjude/bible_sources.json`. `world.json` `bible_sha256` is still null (set it if you want the seed firewall on). |
| `worlds/saintjude/prices_1975.json` | Rebuilt from Part VI §1–7 as `rows` (key, label, default, range, unit, year_basis, mark, tag, source, group). The 66 old `saint_jude_estimates` rows (CPI-scaled from the 1980 codex ledger) are gone. |
| `worlds/saintjude/design_figures.json` (new) | 264 figures (draw / derived / fixed, each with default, range, tag, source), the 26 pools of the 9.3A allocation table, the dial defaults, population path, counts, associates per made man, the Pad. `tools/check_saintjude_pools.py` validates it (shares sum to 100; ranges hold; numbers claims = $2.0M; drug take 0.14/0.03/0.19/0.18 = $0.54M; family gross 10.9/7.2/11.6/7.7; net $35.9M; population 1.06/1.02/0.98M). **No engine code reads it yet**: it is the data for E-005 to E-008, E-011. |
| `worlds/saintjude/seed.json` (from `tools/saintjude_seed_data.py` via `tools/build_saintjude_seed.py`) | 51 persons (5 women), 70 places, 83 institutions, 10 claims, 31 routes. Every person `canon_tag: "Example"`; claims name roles, not people; Open offices have no holder. Review: `docs/superpowers/plans/2026-10-23-saintjude-backdating-review.md`. Trade institutions carry `economic_state.trade_profile_1975` from Part VI 4.4; no property valuations (bible silent). |
| `worlds/saintjude/taboos.json` | 23 priced taboos (Part III 9 ×15, Part V 10.4 ×8) + `fixed_rules`: women never made, `carries_no_price`. **No engine code reads it.** |
| `worlds/saintjude/names.json` + `world.json` `name_pools` | 11 groups of Part I 14.1, weights from 7.1 (mapping in file). Women's names from the bible only for Italian and Black; other female lists are labelled fallbacks. Émigré group weight 0 (7.1 gives no share). |
| `worlds/saintjude/timeline.json` | 63 entries with `mark`, `tag`, `from_bible`, bible citations; month/year-only dates use the last day so nothing fires early. 17 technology entries kept as "Not from the bible" assumptions. **Only a test calls `timeline_status`.** |
| `worlds/saintjude/rulebook_section.md`, `creation_section.md` | Period Mind, Index 2 content limits verbatim, tags, real people offstage, no real town in the footprint, Examples, taboos as prices, women never made, dated law (bail before 1984 etc.), narration companion file noted as outside the load set. |
| `worlds/saintjude/archetypes.json` | `price_refs` repointed to Part VI 4.4 `trade_*` rows; six archetypes have no Part VI row and are marked "bible silent". |
| Tests | `saintjude_package_test`, `saintjude_snapshot_test`, `names_same_group_test` updated to new values only; new `saintjude_design_figures_test`. |

**Full suite after the reload (2026-10-24, `runs/suite_reload.log`):** 166 PASS, 8 FAIL, 2 TIMEOUT out of 176. All Saint Jude and world-package tests pass. The 10 non-passing tests failed or timed out identically in the baseline taken before the reload (`runs/suite_baseline.log`), none touches Saint Jude, and none was changed: `age_birthdate_mortality_test`, `popback01_background_population_test`, `schema110_underworld_test`, `seek01_natural_attraction_test`, `underworld_rackets_assets_test`, `v20_test`, `v27_test`, `v30_test` (FAIL); `v26_candidate_scale_test`, `world_pushes_back_test` (TIMEOUT at 1,500 s). They are pre-existing Caerness failures, outside this brief; report them as such. Logs per test are in `runs/suite_reload/`.

## 3. Step 3: E-001 to E-028 (investigated, not yet fixed)

`e_checks.md` (this folder) answers all 28 with file:function evidence, fix sizes and whether each is small. Summary: 1 YES (E-004 belief store), 12 PARTIAL (E-002, 003, 009, 010, 011, 016, 017, 018, 019, 022, 024, 025, 028), 15 NO (E-001, 005, 006, 007, 008, 012, 013, 014, 015, 020, 021, 023, 026, 027; E-026 mostly). Note `e_checks.md` predates the reload: re-verify any answer touching data (E-016/017/018 now have rulebook lines; E-026 now has `tools/check_saintjude_pools.py` for pool balance and ranges, but not the other four checks; E-003 seed now tags Examples and claims name roles).

Critical items and what the investigation suggests is small:
- **E-005** run determinism exists (`world_state.rng_seed`; same seed → identical 90 days) but there is no Design-figure store and no logged draws. Small: at opening, draw each `design_figures.json` "draw" figure from its range (or default) with the run seed into a table, log seed and value; recompute "derived" ones (also E-006).
- **E-011** `ledger.transfer` balances, but nothing models pools. The validator covers the data; engine pools are project-2 money work.
- **E-001** no Fixed/Open tag store; `act` accepted "Gannet Terminal opened in 1972". Small-to-medium: a facts table with tags, loaded from seed claims and timeline, and a veto on contradicting a Fixed fact without a cause event (`engine/veto.py`).
- **E-009** `timeline_status` exists (`engine/world_package.py:178`) but `act`/`author` never call it; `act` accepted "hold a boss without bail" in 1975. Small: veto on a named timeline item whose date has not arrived; surface dated rules in `lore`/`lookup`.
- **E-024** `advance_connection` runs forward (5 years ≈ 16 s on the current inert world) and `events` is the log, but nothing about elections, Pick-3 or dials is in it. Verified-date clocks fire (`clocks.due_day`) but only log.
- **E-016** prompt-only (rulebook lines now present); no output filter. The engine runs no language model, so a prompt rule plus a veto on named real people/towns is the realistic ceiling.

## 4. Step 4: Tasks 20–23 (plan: `docs/superpowers/plans/2026-10-23-world-packages-plan.md`)

- **Blocking defect found in Step 3 investigation:** the Saint Jude opening carries **52M people in Caerness population buckets** (underheaven, dunmoor, …); only Oakridge (82,000) maps to a Saint Jude place. It grows 8.8% in five years (E-025 wants about −0.8%/yr). `author` person/business/organisation fails outside Oakridge ("population cannot supply that person", "nobody lives there"); "County Prosecutor" became occupation "labor". Fix this first: Saint Jude needs its own population sources tied to its districts (1.1M, Part I 4.1 and 7.1), never Caerness buckets.
- **Task 20.** The opening creates 544 unnamed background people (Caerness behaviour). Bible: Open items are invented when needed and then held (Part I 0.1, Part II 10); named men are Examples (Part III 4.6). Make the opening follow that; where the bible is silent on who exists at start, say so and invent no rule. Time the run from the 1 Jan 1975 seed to the 1980 default entry (E-024) and record it in the plan's Measurements table and `AGENTS.md`.
- **Task 21.** Build `tools/leak_scan.py` (plan text) and scan for Caerness leaks **and** old-bible leaks using `step1_diff.md` §10. Known false positives: "Holloway" (Part I 14.1 name pool), "Sparks Steak House", "Customs House" trip Hollow/House words.
- **Task 22.** Connector play test (server module functions, never the live `caerness` MCP tools), including: a 1979 scene asking a federal judge to hold a boss without bail (must be refused before 1984); a scene set in a real town inside the footprint, e.g. Red Bank (must become a Saint Jude place); a Pad-paying family committing a public killing (must still bring an arrest, Part II 3.4); asking twice, a game-month apart, for the name of an Open official (same answer both times).
- **Task 23.** Full suite, then docs citing the new bible's sections (AGENTS.md §2, connector/README.md, the Saint Jude handoff, the plan).

Other known engine gaps from Step 2:
- `engine/canon.py` builds heading paths H1 > H2 > H3, and every Part file starts `# Saint Jude: The Setting Bible` / `## Part X` with sections also at `##`, so 102 of 483 chunk paths are shared across Parts (e.g. "0. How to Read This Part"). The bible may not be edited: fix in `canon.py` (carry the `## Part …` line as a level above the section `##` lines) or index each Part file separately.
- `connector/campaign.py` indexes the bible only when `canon_chunks` is empty, so an existing Saint Jude campaign keeps the old index.
- `lore` truncates passages at 1,800 chars; Part III 7.2's long paragraph is cut.

## 5. The report the owner wants (one report at the end)

1. The Step 1 diff, grouped by area (from `step1_diff.md`).
2. E-001 to E-028: yes or no, evidence, and what was fixed.
3. Problems in the bible itself: location, exact quote, proposed fix (collected so far in section 6 below; add any you find).
4. Results of Tasks 20–23, including the opening's timing and anything not finished.

## 6. Bible problems collected so far (verify the quotes before reporting)

1. **Part VI 9.3A** mixes units: the legitimate-fronts row ("2.5 (1.0 to 4.0) | 0.5 | 0.8 | 1.2"), the drugs row ("0.14 | 0.03 | 0.19 | 0.18") and the Pad row are dollars in columns that are percentages for every other row, under "the shares of a row add to 100 percent". Fix: print shares (fronts 50/10/16/24; drugs 26/6/35/33; Pad 26/19/33/22) or add a $M column.
2. **Part VI 9.5** "the carting line (80 percent of $4.5M to Vannucci) and the Strip line (70 percent of $3.6M)" vs 9.3A 89% of $4.05M and 78% of $3.24M (same dollars, different bases). Fix: restate on the 9.3A basis.
3. **Part VI 8.1** Brigades docks: "plus the Brigades' half of the cross-river items, $0.15M" — no pool in 4.3 or 9.3A holds it, and the Pellegrino half is nowhere (breaks 0.2, every flow is a share of a named pool). Fix: add a cross-river row to 4.3 and 9.3A, or fold it into the $0.75M.
4. **Part VI 7.5** "The annual total is a separate Design figure and is not the sum of the weekly table." Runnable only as a free draw ($0.9M–$2.7M); no rule ties envelopes to officers to dollars beyond "$1.6M buys about 300". Fix: state the default officer count and mean envelope.
5. **Part VI 2.2** Italian numbers share "$0.45 million (range $0.1M to $1.2M at the default handle)"; 20–50% of $1.28M gives $0.26M–$0.64M. Fix: $0.26M–$0.64M, or drop "at the default handle".
6. **Part VI 2.2** chain: "Pad, bad debt, cheating, variance | 0.145 default, 0.07 to 0.195" against "Net to the bank … range 0.03 to 0.15": 0.225 − 0.07 = 0.155. Fix: net top 0.155, or Pad low 0.075.
7. **Part VI 8.2** prints combine numbers net 0.8 and bookmaking 0.3; the derivations give 0.83 and 0.32 (own lines 1.15 vs printed 1.1). 8.5 Chinatown 0.30 + 0.16 = 0.46 vs printed 0.5. Fix: print the derived values.
8. **Part VI 3.4 vs 4.5:** "profit on Sabatini-owned construction firms $1.0M" under concrete_club and $2.5M "legitimate fronts" — possible double count if the fronts include the construction firms. Fix: say whether they do.
9. **Part III 3.2 / Part VI:** no stated default made-man count for Sabatini, Ferrante, Vannucci (midpoints used). Fix: state defaults.
10. **Pine County direction:** Part I 3.1a "Pine County is the Pine Barrens inland to the south-west" vs Part I 4.1 "Pine County (west)" and 3.2/6.4 "the Pines (west, thirty miles)". Fix: one direction.
11. **Pick-3 vs Pick-it:** Part III 7.2 / Part VI 2.3 "first called Pick-it and renamed Pick-3 in 1987", but Part I 9.8, 13 and Index 3 call the 1975 game "Pick-3". Fix: "Pick-it (later Pick-3)" in 1975 contexts.
12. **Money-laundering date:** Part VI 10.1 "1984 to 1985 | Forfeiture and money-laundering laws" vs Part IV 7 "(an act of 1986)". Fix: one date.
13. **Part III 7.2** "the runner who takes the bets kept 10 percent of the play, and the runner's share is 10 percent of the play" — the clause repeats itself. Fix: delete the second clause.
14. **Part I 15.2** anchor "the State Commission of Investigation (1969)" vs 3.1a and Part II 1.1 "created in 1968, working from 1 January 1969". Fix: "(created 1968, working 1969)".
15. **Part I 6.1** "Monsignor Boyle's rectory" names a pastor, while Part I 15.1 and Index 7 leave pastors' names Open. Fix: "the cathedral rectory".
16. **Part I 5.8** titles District Eight "The Heights and Oakridge", but Oakridge is outside the city line in Marsh County; the city then has seven districts in the line. Fix: retitle, with Oakridge as a beyond-the-line note.
17. **Federal detention center:** Part I 5.2 names the Metropolitan Correctional Center (opened 1974) but Part II 8 says "The federal detention center downtown … (name **Open**)". Fix: one or the other.
18. **Part I 7.1** gives no share for the Soviet Jewish émigrés, whom 14.1 names as a naming group. Fix: add a share.
19. **Part III 8.7** "Guns come from the bikers, the gun shows and the Armorer." — "the Armorer" is defined nowhere and reads like a named figure. Fix: define as an Open role or drop.
20. **Old-codex text inside the bible:** Part I 2.5 "The old codex timeline's '1982 Barber Shop Hit,' later '1977,' is no longer history" and Part III 0 "A note on scale (a decision for Cade)". Fix: move to a change log.
21. **Part I 5.5** points to "the Economy of Face in Part III", which does not exist. Fix: remove or add the section.
22. **Part I 3.2 / 6.4 placements missing:** Fenwick, Docks Chinatown's bank, Greenwood's line, the Master Layoff bank, the car-crushing yard (Part III 4.3) have no location. Fix: place them in Part I 3.2/6.4.
23. **Index 7** "Nothing has been loaded into the engine." — now stale. **Index 1/Part II 0.4:** the companion "Saint Jude Rulebook Narration Standards" is required but not supplied, so E-018 cannot be met in full. Fix: supply the file.
24. **Chunking:** each Part opens with an H1 shared by all seven files and puts its Part title and its sections at the same `##` level, so section paths collide across Parts. Fix (bible side): make the Part title the H1; or handle in `canon.py` (section 4).

Engine Implications §10 "Unrunnable as written": with this bible, A-002 (9.3A now exists), A-003 (6.5 now says "on the family's own ground") and A-019 (3.2 now requires a dated cause for 51–55) and A-004 (Part VI 10 now says "[verified] or [verified in outline] fires") are resolved; A-014 (item 4 above) and A-035 (item 23) remain.

## 7. Runbook reminders

- Python: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe"`; simulate only on scratch copies (`CAERNESS_DB_PATH`); never the `caerness` MCP tools; ad hoc scripts with `-I`.
- Full suite: `python tools/run_suite.py --out runs/suite` then `git restore game/campaign_01/model_requests/` (about 20–25 min on the PC).
- Regenerate: `python tools/build_saintjude_bible.py`, `python tools/build_saintjude_seed.py`, `python tools/check_saintjude_pools.py`.
- Leave `.claude/`, `data/caerness.pre-schema110.db`, `game/campaign_01/backups/` alone.
