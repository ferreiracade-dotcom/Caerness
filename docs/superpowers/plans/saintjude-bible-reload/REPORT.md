# Saint Jude bible reload: the report

**Date:** 2026-10-24. **Branch:** `feat/world-packages-saintjude`. The authority is the new bible (Index + Parts I–VI), joined verbatim in `worlds/saintjude/bible.md`. Detail lives in this folder: `step1_diff.md` (every change), `e_checks.md` (the first investigation of E-001 to E-028), `HANDOFF.md` and `HANDOFF_2.md` (state between sessions).

## 1. What changed from the old bible (Step 1, grouped by area)

Full list with file and line: `step1_diff.md`. In short:

- **Families and names.** Castellano becomes **Pellegrino** and Moretti becomes **Ferrante** (Part III 0: both were real mobsters' names). Every named man is an **Example** (Part III 0 and 4.6, Part V 0.2, Part IV 0.2): replaceable, not canon. Officials are Open (Part II 10). The Mercer Street Kings and a headed Vorovskoy do not exist in 1975 (Part V); the Eastside has a headless combine. The Strike Force is a Justice Department program, not an FBI unit (Part II 5.2).
- **Geography.** The city sits on northern Monmouth County's shore (Part I 3.1a); no real town exists in that footprint. Oakridge is outside the city line in Marsh County (W/NW). Eight districts plus Kerrytown, Gannet Terminal, Docks Chinatown and others (Part I 3.2, 5, 6); 24 police precincts (Part II 2.4).
- **History and dates.** The seed date is 1 Jan 1975; the default player entry is 1980 (Part I 0.4). Several items were corrected or added:
  - 1929–31 harbor wars added; the 1946 war is no longer three months long.
  - The Ferrante Schism's instigator and the Concrete Purge's outcome are Open; the "caisson pour" fate is gone.
  - Dock Strike Massacre 1973; Dolan Commission 1970–72; Gannet Terminal 1968.
  - Pick-3 (first called Pick-it) begins 22 May 1975.
  - Dated law: pen register June 1979; Bail Reform Act 1984; union-office bar 5→13 years on 12 Oct 1984; SCI created 1968, working 1969.
- **Money.** Rebuilt from Part VI: wage and price ladder, racket arithmetic, the 9.3A allocation table, the Pad. The old 1980-ledger prices scaled back to 1975 by CPI are gone. Data files:
  - `prices_1975.json`;
  - `design_figures.json`: 264 figures and 26 pools;
  - `tools/check_saintjude_pools.py` checks that the shares balance.
- **Counts.**
  - **Made men:** Sabatini 50–60; Pellegrino 40–50, default 45, and 51–55 only with a dated cause; Ferrante 40–50; Vannucci 30–40.
  - **Associates:** 5–8 per made man.
  - **Population:** the city has 1.1M people in 1975 and falls 0.8% a year; the metro has 2.4M.
  - **Police:** about 4,800 sworn officers in the SJPD.
  - **Ethnic shares:** Part I 7.1.
- **Rules and tags.** The new tag system is Fixed, Open, Weather, Anchor, Tendency, Design and Example, alongside the five tiers of truth. Taboos are prices, not walls: 15 in Part III 9 and 8 in Part V 10.4. "Women are never made" carries no price. The content limits of Index 2 and the Period Mind (Part II 0) are in the rulebook.
- **Names.** 11 naming groups (Part I 14.1) with weights from 7.1.

## 2. E-001 to E-028

**YES** means the engine does it, **PARTIAL** means part of it, **NO** means not at all. "Fixed now" means it was changed in this reload, with the test that shows it.

| Item | Answer | Evidence and what was done |
|---|---|---|
| E-001 Fixed facts locked | **YES (store), by design no free-text contradiction detection** | Fixed now. The `world_facts` table (`engine/facts.py`) holds tags, loaded from seed claims, tagged timeline entries, Example persons and `meta.open_offices`. Changing a Fixed fact with `note kind=fact` needs a `cause`. Test: `tests/saintjude_facts_test.py`. |
| E-002 Open items filled once, then held | **YES** | Fixed now. `author person … holds=<office>` fills an Open office once, and a second holder is refused with "held by X since <date>". `lookup` gives the holder, or "Open: not yet decided". Tests: `saintjude_facts_test`; play test check D (same name a game-month apart). |
| E-003 Example men replaceable | **YES** | Fixed now. Seed persons carry `canon_tag: "Example"`, and claims name roles, not men. |
| E-004 Belief apart from truth | **YES** for beliefs, **PARTIAL** for conventions | Unchanged (`e_checks.md`). |
| E-005 Design figures drawn once per run, held, logged | **YES** | Fixed now. `engine/design.py` draws each figure once from `world_state.rng_seed` (triangular, peaked at the default) and logs seed, day and cause. Test: `design_figures_runtime_test`. |
| E-006 Derived figures recomputed | **YES** | Fixed now (`engine/design.py`). |
| E-007 Sector draws share a factor | **NO** | No sectors exist yet. The fix is a shared per-year shock in `design.py` once sectors exist (about 30 lines). |
| E-008 Range bounds enforced | **YES** | Fixed now. `set_figure` clamps to the range unless `exception=True`, and needs a cause. |
| E-009 No rule before its date | **YES** for named rules | Fixed now. `veto.check_world_text` (`dated_rules`) refuses a named timeline item before its date in `act`, protagonist proposals and `author`. Test: `saintjude_dated_rules_test`; play test case A (1979 "no bail" refused, citing 12 October 1984). |
| E-010 Verified events fire; pressures can be deflected | **PARTIAL** | Clocks fire and log, but nothing distinguishes verified events from pressures and no handlers exist. About 150 lines (`e_checks.md`). |
| E-011 Pools balance | **PARTIAL** | `ledger.transfer` balances. Pools are data only, checked by `tools/check_saintjude_pools.py`; the engine has no pool model (project 2 money work, about 250 lines). |
| E-012 Kick-ups on net, weekly, up the Ladder | **NO** | Only the Caerness outfit model exists, and it is off for Saint Jude. Project 2 (about 300 lines). |
| E-013 Nominal sums decay with the deflator | **NO** | About 80 lines (`e_checks.md`). |
| E-014 The Pad is a cost, with limits | **NO** | Play test case C: a Pad-paying family's public killing was accepted as a plan and brought no arrest or police response. Part II 3.4 requires an arrest. Needs a protection-arrangement table plus a law-process hook that ignores the Pad for excluded cases (200–300 lines). Saint Jude has no law jurisdictions yet. |
| E-015 Headcount follows revenue slowly | **NO** | Project 2 (family record with revenue and count range). |
| E-016 Generated text keeps the four limits | **PARTIAL (prompt-only, the ceiling)** | The engine reads no narration. The Index 2 limits are quoted verbatim in `worlds/saintjude/rulebook_section.md` (line 8). The engine side is the real-person and real-town vetoes (E-017, E-023). |
| E-017 Real people never act on stage | **YES** for named people | Fixed now. `veto.real_person` refuses the 19 real people in `worlds/saintjude/gazetteer.json` (for you to confirm). |
| E-018 Narration standards loaded | **PARTIAL** | The Period Mind is in the rulebook. The companion file "Saint Jude Rulebook Narration Standards" was not supplied (bible problem 23). |
| E-019 Offices with rules and terms | **PARTIAL / mostly NO** | Holders are kept (E-002), but terms, elections and turnover dates are not built (250–350 lines). |
| E-020 Procedure follows the law of the date | **YES** for named rules, **NO** for case procedure | Same veto as E-009. Numeric enforcement per case needs a Saint Jude law process (`law_jurisdictions` is empty). |
| E-021 Narcotics dial per family and drug | **NO** | Project 2. |
| E-022 Taboos are prices, not walls | **PARTIAL** | Nothing refuses a taboo act, which is correct. Nothing reads `taboos.json`, so no reactions are drawn (150–250 lines). |
| E-023 Real towns blocked; jurisdictions follow the map | **YES** for towns, **NO** for jurisdictions | Fixed now. `veto.real_town` refuses replaced towns. Play test case B: "Red Bank does not exist in this world: the city stands on that ground (Part I 3.1a)…" in `act`, `author person` and `author business`. The gazetteer has 41 towns, 37 of them inferred (bible problem 27). Jurisdiction routing is project 2. |
| E-024 Run 1975 to the entry date and keep the record | **PARTIAL** | Measured: 1 Jan 1975 to Tuesday 1 Jan 1980 takes 18.9 s on the PC. The `events` table is the record. The world is nearly inert, so the record holds births, deaths and unions and nothing about elections, Pick-3 or dials (project 2). |
| E-025 Recurring cycles; population series | **PARTIAL** | The population part is fixed now: the city follows the Design decline path, 1.1M less about 0.8% a year (`saintjude_population_test`). Weekly, annual and fiscal cycles are not built (80–120 lines). |
| E-026 Validation suite on the bible | **PARTIAL** | Pool balance and ranges: `check_saintjude_pools.py`. Old-codex and Caerness leaks: `tools/leak_scan.py` (new). Cross-references, Weather and one-value checks are not built. |
| E-027 The dial binds the family, not each man | **NO** | Project 2, after E-021. |
| E-028 Rackets have holders | **PARTIAL** | The `economic_interests` table exists, but Saint Jude has no rackets or enterprises yet. Project 2. |

## 3. Problems in the bible itself

All quotes were checked against `worlds/saintjude/bible.md` on 2026-10-24.

1. **Part VI 9.3A** mixes units. The fronts row "2.5 (1.0 to 4.0) | 0.5 | 0.8 | 1.2", the drugs row "0.14 | 0.03 | 0.19 | 0.18" and the Pad row are dollars, but they sit in columns that are percentages in every other row, under "the shares of a row add to 100 percent". **Fix:** print shares (fronts 50/10/16/24; drugs 26/6/35/33; Pad 26/19/33/22) or add a $M column.
2. **Part VI 9.5** "the carting line (80 percent of $4.5M to Vannucci) and the Strip line (70 percent of $3.6M)" does not match 9.3A, which has 89% of $4.05M and 78% of $3.24M: the same dollars on different bases. **Fix:** restate 9.5 on the 9.3A basis.
3. **Part VI 8.1** says "plus the Brigades' half of the cross-river items, $0.15M". No pool holds this, and the Pellegrino half appears nowhere. **Fix:** add a cross-river row to 4.3 and 9.3A, or fold it into the $0.75M.
4. **Part VI 7.5** says "The annual total is a separate Design figure and is not the sum of the weekly table." It can only run as a free draw. **Fix:** state the default officer count and mean envelope.
5. **Part VI 2.2** gives the Italian numbers share as "$0.45 million (range $0.1M to $1.2M at the default handle)", but 20–50% of $1.28M is $0.26M–$0.64M. **Fix:** either change the range or drop "at the default handle".
6. **Part VI 2.2** chain: "Pad, bad debt, cheating, variance | 0.145 default, 0.07 to 0.195" against a net range of "0.03 to 0.15". The top of the net range follows from the bottom of the Pad range: 0.225 − 0.07 = 0.155. **Fix:** make the net top 0.155, or the Pad low 0.075.
7. **Part VI 8.2 and 8.5** print rounded figures that differ from their own derivations:
   - combine numbers net: printed 0.8, derived 0.83;
   - bookmaking: printed 0.3, derived 0.32;
   - Chinatown: printed 0.5, derived 0.46.

   **Fix:** print the derived values.
8. **Part VI 3.4 vs 4.5:** "profit on Sabatini-owned construction firms $1.0M" against $2.5M of "legitimate fronts" may count the same money twice. **Fix:** say whether the fronts include the construction firms.
9. **Part III 3.2 / Part VI** give no default made-man count for Sabatini, Ferrante or Vannucci; the midpoints are used. **Fix:** state defaults.
10. **Pine County** is in two directions:
   - Part I 3.1a: "Pine County is the Pine Barrens inland to the south-west";
   - Part I 4.1: "**Pine County** (west)";
   - Part I 6.4: "Thirty miles west in Pine County".

   **Fix:** pick one direction.
11. **Pick-it vs Pick-3:** Part III 7.2 and Part VI 2.3 say "first called Pick-it and renamed Pick-3 in 1987", but Part I 9.8, 13 and Index 3 call the 1975 game "Pick-3". **Fix:** write "Pick-it (later Pick-3)" in 1975 contexts.
12. **Money-laundering law date:** Part VI 10.1 has "1984 to 1985 | Forfeiture and money-laundering laws", while Part IV 7 has "(an act of 1986)". **Fix:** one date.
13. **Part III 7.2** "the runner who takes the bets kept 10 percent of the play, and the runner's share is 10 percent of the play" says the same thing twice. **Fix:** delete the second clause.
14. **Part I 15.2** gives "the State Commission of Investigation (1969)", but 3.1a and Part II 1.1 say "created in 1968, working from 1 January 1969". **Fix:** "(created 1968, working 1969)".
15. **Part I 6.1** "Monsignor Boyle's rectory" names a pastor, while 15.1 and Index 7 leave pastors' names Open. **Fix:** "the cathedral rectory".
16. **Part I 5.8** is titled "The Heights and Oakridge", but Oakridge is outside the city in Marsh County. **Fix:** retitle it, with Oakridge as a note on what lies beyond the line.
17. **Federal detention center:** Part I 5.2 names the Metropolitan Correctional Center, while Part II 8 says "(name **Open**)". **Fix:** keep one.
18. **Part I 7.1** gives no share for the Soviet Jewish émigrés, although 14.1 lists them as a naming group (the engine weights them 0). **Fix:** add a share.
19. **Part III 8.7** "the Armorer" is defined nowhere and reads as a named figure. **Fix:** define it as an Open role, or drop it.
20. **Old-codex text inside the bible:**
   - Part I 2.5: "The old codex timeline's '1982 Barber Shop Hit,' later '1977,' is no longer history";
   - Part III 0: "A note on scale (a decision for Cade)".

   **Fix:** move both to a change log.
21. **Part I 5.5** refers to "the Economy of Face in Part III", which does not exist. **Fix:** remove the reference or add the section.
22. **Unplaced places:** Fenwick, the Docks Chinatown bank, Greenwood's line, the Master Layoff bank and the car-crushing yard (Part III 4.3) have no location. **Fix:** place them in Part I 3.2/6.4. Meanwhile the seed calls the yard "Eastside Auto Crush", an Example name.
23. **Index 7** "Nothing has been loaded into the engine." is now stale. Index 1 and Part II 0.4 also require the companion "Saint Jude Rulebook Narration Standards", which was not supplied. **Fix:** supply the file.
24. **Headings:** every Part opens with the same H1, and its Part title and its sections sit at the same `##` level. **Fix (bible side):** make the Part title the H1. The engine now handles it in `engine/canon.py`.
25. **Part I 4.1** contradicts itself: "**Fixed.** The **metropolitan area** has about **2.4 million** people." against "The metropolitan total is Open". **Fix:** make 2.4M the Fixed 1975 figure and say that only its later path is Open.
26. **Part I 4.1 / 3.1a are silent** on the populations of Marsh, Pine, Shore, Oakridge and the districts, and on the birth rate, infant mortality and age structure. Until the bible decides, the engine uses:
   - an unplaced suburban remainder of 1.3M;
   - the 1975 US rates, labelled as assumptions.

   **Fix:** state 1975 populations per county, or confirm that the unsplit remainder is intended.
27. **Part I 3.1a** "The real towns there (Long Branch, Asbury Park, Red Bank and their neighbors) do not exist" does not list "their neighbors". The engine's 37 further towns are an inference. **Fix:** list the municipalities, or define the boundary.

Engine Implications §10 "Unrunnable as written": A-002, A-003, A-004 and A-019 are resolved by this bible. A-014 (problem 4) and A-035 (problem 23) remain.

## 4. Tasks 20–23

### Task 20: the opening

- **Who exists at the start.** The opening holds the 51 seeded Example persons and 83 institutions as actors (134 in all), 70 places and 64 background identity profiles (32 in the city, 32 in the unplaced suburban remainder). It holds **no unnamed people**; the old Caerness behaviour made 544. This follows the bible:
  - Open items are "invented when needed" (Part I 0.1), and officials are created "when needed" (Part II 10).
  - Named men are Examples (Part III 4.6).
  - The bible gives made-man and associate counts as Design figures (Part III 3.2). It does not say that those men exist as individuals at the start, so the engine invents no rule there: the counts sit in `design_figures.json`.
- **Timing on the PC** (also in the plan's Measurements table and `AGENTS.md` §2):

  | Run | Time |
  |---|---|
  | Opening build | 2.6 s |
  | 30-day advance | 0.1 s |
  | 1 Jan 1975 to 1 Jan 1980 (E-024) | 18.9 s; 3.1 to 4.4 s per year; ends "Tuesday 1 January 1980" |

  DB size: 5.8 MB at the opening, 8.0 MB after 30 days with the bible indexed, 9.2 MB in 1980. The Oracle VM was not measured: it has no Saint Jude campaign.
- **`data/saintjude.db`** is built (`python tools/build_opening.py --package saintjude`), with world name "Saint Jude" and the package stamped. A new connector campaign now takes `CAERNESS_WORLD_PACKAGE` (`connector/campaign.py`); before this, the server could only create Caerness campaigns. `connector/README.md` explains how to run Saint Jude on the VM.

### Task 21: leak scan

`tools/leak_scan.py` scans every text column of a database for:
- Caerness names, taken from `data/caerness.db`, plus fixed words;
- old-codex strings from `step1_diff.md` §10.

It skips any string the new bible or the seed itself contains. `tests/saintjude_leak_scan_test.py` builds an opening, advances 30 days, indexes the bible, checks two planted leaks are caught, and expects 0 leaks. **PASS.**

- **Removed by gating on package switches** (Caerness unchanged; the opening fingerprint test passes):
  - the 10 Caerness religions (`caerness_religions`);
  - the "Horses and military remounts" good and the four Caerness news channels (`caerness_trade`);
  - the `cultivated_light` route key, the "competence is not derived from Stage" note and the "Martial practice" skill (`cultivation`).
- **A real bug found here:** the connector re-runs `init_db` every time it opens a campaign, with no package in the environment, so a reopened Saint Jude campaign got Caerness religions seeded back. The switch now reads the package recorded in the database. Checked by reopening `data/saintjude.db` through `open_campaign`: 0 religions, 0 leaks.
- **Allowed as engine bookkeeping** that the connector never reads: `schema_migrations`, `engine_meta`, `coverage_registry`, `process_execution_log`.
- **Allowed by rule:** five old-codex names made only of pool names (Salvatore Conti, Arkady Volkov, Raymond Doyle, Hector Rivera, Danny Lombardo), because the name generator can draw them legitimately; it drew "Hector Rivera" during the play test. Their nicknames stay on the list.
- **The old cast kept as Examples (confirmed by the owner, 2026-10-24).** About 40 old-codex people and businesses stay in the seed as Examples, for example Arthur Blum, the Gallaghers, Teamsters Local 814 and Saint Jude Ready-Mix. The previous session chose this on the basis of Part III 0: "may be changed, dropped, reversed, or invented again". The scanner treats them as legitimate.
- **The four place names queried in the handoff** are kept as Example names:
  - Eastside Auto Crush: the bible's "car-crushing yard", unplaced (problem 22);
  - Mercer Avenue Boxing Gym: the Strip has "boxing gyms";
  - Pier 4 Diner: an invented diner at Pier 4;
  - San Lorenzo Provisions Plant: the bible calls it "San Lorenzo Provisions". It could be renamed if you prefer.

### Task 22: playing through the connector

`tests/saintjude_connector_play_test.py` (server module functions, temp campaign) has 13 checks, **all PASS**, with one report-only case:

- **Plan flow:**
  - `resume` asks for a character, with the Saint Jude rulebook and no leaks.
  - The protagonist (a 28-year-old Kerrytown bartender) is accepted.
  - The scene reads "Wednesday 1 January 1975", with Saint Jude names and no leaks.
  - `lore("St. Jude's")` returns Part I 2.3, "The Chapel Becomes the Cathedral".
  - A free-text `act` resolves.
  - A 30-day advance reaches "Friday 31 January 1975".
  - The pizzeria is accepted, scaled to "small".
  - The leak scan of the campaign finds 0.
- **Case A:** in 1979, asking a federal judge to hold a boss without bail is **refused**: "federal preventive detention does not exist yet: it arrives 12 October 1984 …".
- **Case B:** Red Bank is **refused** in `act`, `author person` and `author business`, and the GM is pointed to a Saint Jude place or a neighbourhood that borrows the name.
- **Case C:** a Pad-paying family's public killing is **report-only**. It was accepted as a plan, settled in 3 days, with **no arrest** (E-014 not built).
- **Case D:** the Police Commissioner is Open. Authored once as Harold Brennan, the office gives the same name a game-month later, and a second holder is refused.

Engine defects this test found, all fixed (each in a generic, package-aware way):
- **Kin and spouse names from Caerness lists** (for example "Della Birch"). Spouses, latent children and newborns are now named from the package's name groups (`engine/opening_family.py`, `household_life.py`, `new_character.py`, `demographic_sex.py`).
- **Sex from name used only Caerness given names**, so "Harold" was rolled female. The package pools are now checked first (`demographic_sex._given_name_sex`, `veto.name_sex`).
- **"Police Commissioner" became occupation "labor".** Generic police and civic words were added to `veto.categorise`. One gap remains: `holds` still does not set the occupation by itself.
- **`build_opening(package=…)` named the world from the environment**, so a build without the variable was called "Caerness". Fixed in `tools/build_opening.py`.

### Task 23: full suite

`python tools/run_suite.py --out runs/suite_h2` on 2026-10-24 gave **174 PASS, 9 FAIL, 0 TIMEOUT out of 183**. The model-request files were restored afterwards.

- **8 failures are the pre-existing Caerness failures** from the baseline, unchanged and outside this brief: `age_birthdate_mortality_test`, `popback01_background_population_test`, `schema110_underworld_test`, `seek01_natural_attraction_test`, `underworld_rackets_assets_test`, `v20_test`, `v27_test`, `v30_test`.
- **The two baseline timeouts passed this time:** `v26_candidate_scale_test` and `world_pushes_back_test`.
- **1 new failure, fixed after the run:** `connector_server_test`. The connector's tool descriptions were 6,035 characters against the test's 6,000 budget, after the facts commit `e03fbf8` added the `holds` and `fact` wording. I shortened the wording; the test now passes at 5,975.
- **Every Saint Jude and world-package test passes,** including the new leak-scan and play tests.

## 5. Not finished, and decisions for you

- **Nothing is committed yet.**
- **Lists to confirm:**
  - the gazetteer: 41 replaced towns, 37 inferred; Perth Amboy, New Brunswick, Edison and Wall were left out as unclear;
  - the 19 real people it lists.
- **Bible fixes:** problems 1–27 above are yours to resolve in the bible.
- **Project 2 work**, not built here: the Pad (E-014), the Ladder (E-012), pools in the engine (E-011), the dial (E-021 and E-027), rackets (E-028), offices with terms (E-019), cycles (E-025), taboo reactions (E-022) and jurisdictions (E-023 routing).
- **Before playing Saint Jude on the VM:** run `update.sh`, ship `data/saintjude.db`, and set `CAERNESS_WORLD_PACKAGE=saintjude` with a new `CAERNESS_CAMPAIGN` name. Existing Caerness campaigns need nothing.
