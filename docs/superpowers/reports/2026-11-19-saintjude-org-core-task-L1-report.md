# L1 report: the lived 1 January 1975 opening

## Before / after (data/saintjude.db, `python tools/build_opening.py --package saintjude`)
| | before (C1 audit) | after |
|---|---|---|
| characters | 2,223 | 5,607 |
| households / unions | 1 | 1,645 / 1,645 |
| kinship links | 8 | 3,912 |
| ordinary businesses (enterprises, buildings) | 0 | 544 (+1,740 staff rows) |
| org debts (canon) | 0 | 3 |
| obligations | 0 | 118 |
| past incidents / heat rows | 0 | 500 (+3 canon events) / 11 |
| knowledge facts / memories / careers | 0 | 10,502 / 5,816 / 3,480 |
| races open at day 0 / declared candidates | 0 | 2 / 5 |
| neighbourhood contact links (household/work/institution/locality) | 0 | 21,004 |
| characters with no relationship | 407 | 101 |
| build time | 11 s | about 21-25 s unprofiled (63 s before one `package_pass` around the opening steps) |
| file size | 18.6 MB | 42.7 MB |

## What was built (commits "L1: ...")
households (`opening_households`), businesses (`opening_businesses`, `neighbourhood.json`), outfit past (`outfit_past`, `op_*` figures), careers/memories (`lived_past`), races (`opening_races`), ties (`opening_ties`), middle-initial fallback for crowded names (`new_character`, `opening_family._spouse_name`), `package_pass` around the opening steps. All figures are package data marked Design proposal; no world words in engine/.

## Tests
New: l1_households, l1_businesses, l1_past, l1_careers_memories, l1_races, l1_ties, l1_budget (build 23.8 s, 40.7 MB), l1_consistency (one year, seeds 3, 7, 11, run one at a time: seats all have superiors, no family with two heads, money reconciles with the ledger, ties ordered). Seed 11 reports a J1 inmate_society seat with no superior (not L1; reported, not asserted).

## Costs to look at (open)
- **A simulated year costs about 3x as much**: 202-215 s against 65 s, and the file grows about 90 MB in a year against 20 MB (rumour exposures of the extra people, enterprise accounts, relationships). `saintjude_mob_fires_test`, `p1_measures_test`, `p1b_five_years_test` and `saintjude_connector_play_test` hit the suite's 1,500 s timeout. The cause is the population (2,223 -> 5,607 characters), not a bug; the owner should decide whether to thin the sample (`named_share`, `residents`) or speed the daily loop.
- `outfit_counts_test.test_counts_move_around_the_figure_over_a_year`: decavalcante ends a year at 15 made men against a figure of 20 (all other families within 2). Resentments from the past incidents are the likely cause; not tuned.
- Canon-named businesses (pubs, funeral homes) are not yet made enterprises; shop rents/standing payments skipped (money risk).

## Existing tests changed because the opening is no longer empty
b12f (canon org debts exist at the opening), org_tension_b12e (a little faded heat), p1_races (the synthetic equal-driver race clears claims/relationships of its two candidates), i1b (clears the subject's household/kin first), bz1_ventures (sets the clock before jumping days). One engine guard: `org_happenings.respond_offers` offers no `kill_offender` when the offender is the responder himself (crashed saintjude_population_test).

## Suite (tools/run_suite.py, once): 243 pass, 20 fail, 4 timeout, before the fixes above. Failing before and unrelated (also fail on the pre-L1 tree): age_birthdate_mortality, deploy_files, new_character, schema110_underworld, v20, v27, v30, world_activation_switches, world_pkg_caerness_connector, world_pkg_caerness_regression, popback01, seek01. Not re-run after fixes: underworld_rackets_assets, saintjude_population (the guard), outfit_counts.
