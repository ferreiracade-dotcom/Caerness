# Bible fixes, 2026-10-24

Applies REPORT.md section 3 (problems 1 to 27). The corrected sources are in `bible_v2/` (the seven files), edited by `apply_bible_fixes.py` and joined by `tools/build_saintjude_bible.py bible_v2`, so `bible.md` still equals its source files byte for byte. The originals in Downloads were not touched. Replace them with `bible_v2/`, or build from `bible_v2/` from now on.

Items marked **proposal** are my inventions to close a gap, not the bible's earlier word. Overrule any of them.

| # | What was done |
|---|---|
| 1 | Part VI 9.3A: fronts, drugs and Pad rows now print shares (fronts 50/10/16/24, drugs 26/6/35/33, Pad 26/19/33/22). The dollars by family moved to the last column. |
| 2 | Part VI 9.5 restated on the 9.3A basis: carting 89 percent of the $4.05M pool, Strip 78 percent of the $3.24M pool. |
| 3 | Part VI 8.1: the Brigades' half of the cross-river items sits inside the 25 percent docks share. Docks line $0.9M to $0.75M, Brigades total $1.7M to $1.5M, outside own lines $9.4M to $9.2M (8.8). |
| 4 | Part VI 7.5: default about 300 officers on the Pad at a mean envelope of about $5,300 a year (about $100 a week). **Proposal**, derived from the $1.6M. |
| 5 | Part VI 2.2: the Italian numbers range stays $0.1M to $1.2M, now said to combine the handle, net and share ranges. |
| 6 | Part VI 2.2: Pad low raised from 0.07 to 0.075 so the net range top stays 0.15. This differs from the net-top-0.155 fix I first named: it changes one number and none of the dollar ranges that follow from 0.15. |
| 7 | Part VI 8.2 and 8.5 print the derived values: numbers 0.83, bookmaking 0.32, combine lines 1.15, Chinatown 0.46. |
| 8 | Part VI 4.5: the $2.5M Sabatini fronts exclude the construction firms, which are counted under the Concrete Club line. |
| 9 | Part III 3.2 defaults: Sabatini 57, Pellegrino 45 (as printed), Ferrante 44, Vannucci 36, summing to 182. Part VI 9 keeps using the range midpoints (55, 45, 45, 35). These replace the 56, 43, 34 I first named, which summed to 178, below the stated 180 to 190. |
| 10 | Pine County is south-west everywhere (Part I 4.1 and 6.4). |
| 11 | Part I 9.8 and 13: "Pick-it (renamed Pick-3 in 1987)" for the 1975 game. |
| 12 | Part VI 10: forfeiture law 1984, money-laundering law 1986. |
| 13 | Part III 7.2: duplicate clause removed. |
| 14 | Part I 15.2: SCI "created 1968, working from 1 January 1969". |
| 15 | Part I 6.1: "the cathedral rectory". The seed note about Monsignor Boyle is gone. |
| 16 | Part I 5.8 retitled "The Heights (the Gold Coast)", with a line saying Oakridge lies outside the city line. |
| 17 | Part I 5.2: "federal detention center (name Open)", also in the 1974 timeline row and the seed. |
| 18 | Part I 7.1: Soviet Jewish emigres 0.2 percent, "Mixed, other" 7.8 percent. **Proposal.** `names.json` weights and `world.json` name pools were recomputed, and the package test no longer expects weight 0. |
| 19 | Part III 8.7: "the armorer" is an Open role. |
| 20 | The old-codex sentence in Part I 2.5 is removed, and "(a decision for Cade)" is removed from Part III 0. Recorded here: the codex timeline's "1982 Barber Shop Hit", later "1977", is not history. |
| 21 | Part I 5.5 now points to Part III 2, Courtesy and Ceremony. |
| 22 | Placed (**proposals**): Fenwick on the north bank west of Crown Harbor between Bellacorte and Greenwood; Docks Chinatown on the north bank behind the North Piers; the Master Layoff bank kept in Crown Harbor; the car-crushing yard in the Eastside rail yards. Greenwood's line is unchanged ("half in Marsh County"). The seed text matches. |
| 23 | Index 7: "Nothing has been loaded into the engine" removed. **Not done:** the companion file "Saint Jude Rulebook Narration Standards" still does not exist. |
| 24 | Not changed. The engine already handles the repeated H1s. |
| 25 | Part I 4.1: the 1975 metro total of 2.4 million is Fixed; only its later path is Open. |
| 26 | Part I 4.1: the outside-city 1.3 million is one suburban remainder, with 1975 US rates until a revision sets them. |
| 27 | Part I 3.1a now lists all 41 replaced municipalities (the gazetteer's list) and says Perth Amboy, New Brunswick, Edison and Wall exist. **Proposal** for those four. `gazetteer.json` now marks all 41 as from the bible. |

## Data files changed

`bible.md`, `bible_sources.json`, `design_figures.json` (made-man defaults, new midpoint figures, Brigades, combine, Chinatown, own-lines total, Pad low, Pad officers and envelope), `tools/check_saintjude_pools.py` (per-man figures use the midpoints), `names.json`, `world.json` (name pools), `gazetteer.json`, `seed.json` (rebuilt from `tools/saintjude_seed_data.py`), `data/saintjude.db` (rebuilt), `tests/saintjude_package_test.py` (Soviet weight).

## Checks run here

Pass: `check_saintjude_pools.py`, `build_saintjude_bible.py --check`, `build_saintjude_seed.py --check`, leak scan of the new DB (0 hits), and these tests: saintjude_package, design_figures, canon_paths, design_figures_runtime, dated_rules, facts, population, snapshot, names_same_group, world_canon_md, world_package_loader, world_connector, world_activation_switches, world_seed_import.

Not run here: `saintjude_connector_play_test` (needs the `mcp` package, not installable in this workspace) and `saintjude_leak_scan_test` (did not finish in time). Run both on the PC, then the full suite with `tools/run_suite.py`.
