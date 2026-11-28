# J1 report: prison for Saint Jude

Commits (branch feat/world-packages-saintjude): a0b95c5 plan; bcfd3b0 J1.1; e74b4f2 J1.2; 0e34c6b J1.3; b2f44d7 J1.4; 9c8dc08 J1.5; e01f8e7 + 60783c5 J1.6; b289668 J1.7; 259bf86 J1.8; 5312b1a J1.9 (schema 128); then the "J1 done:" commit.

## What it is
Prison as a place with its own groups, economy, channels to the outside, hearings and release, beside the B13 case chain. engine/prison.py (facilities, inside groups as org-core organisations, stays, the weekly inside life, carry-on outside), engine/prison_channels.py, engine/prison_review.py (parole, appeal, pardon, good time, conditions). All figures and words are package data (worlds/saintjude/prison.json, law.json, view_words.json). The protagonist is under the same rules; each protagonist test is paired with an NPC one. Schema 128 holds the eight tables.

## Checks
- One-year runs on the lived opening, seeds 3/7/11: 190/222/220 stays, 33/48/52 inside at the end; no man in two stays, every inside stay has a serving sentence or a hold, no inside seats for men not inside, integrity ok, no FK violations. Parole heard 10/3/11 (granted 2/1/1), appeals pending 1/4/4.
- Cost (seed 7, 30 days): prison on 23.5 s, off 22.1 s. One year: on 234 s, off 257 s (noise exceeds the difference). Old opening (3331f28) 30 days: 6.7 s, so the rise to about 23 s is the lived opening (L1), not prison.
- Final quick suite: 188 pass, 0 fail, 0 timeout.

## Found and fixed on the way
- The lived opening holds a man with no case row (a sentence begun before the game) and organisations' arrests carry no case: a hold with no case is now a term by its length (Ironhaven for a long one, the county jail for days). Without this they were never placed and, with release handed to the prison layer, never freed.
- Stale tests (opening is lived, creation changed): world_activation_switches (Caerness gates only the organisation layer's processes), deploy_files (backup uses --all), new_character (a stated age/work fixes who he can be; the draw varies the unstated), age_birthdate_mortality and v20 (first health reviews spread over 30-180 days; advance 181), connector size budgets (rulebook additions), bz1 ventures text. saintjude_population_test (a 5-year advance) moved to the slow set, unchanged. j1_chain_test is slow too.
- Three small fixes asked for: `entry` in the author docstring, creation note in rulebook_core.md (and the spec appendix it must match), stale "politics not built" removed.

## Gaps, named
- A sentence of a man who died before admission stays 'serving' (case chain's to close).
- The opening's held man has no sentence row, so no J1 hearings for him.
- Inside groups in one-year runs are almost all 'connected' (the sim's convicts are mob men); street and neighbourhood groups barely appear.
- Witness protection and aliases (no alias table); judge and jury actors; neighbourhood groups by a stable per-man draw; transfers by security reclass; claims.record on visits; visit stigma; the board's arrangements reach; overheard orders reuse the racket crime kind.
- The quick suite never ran saintjude_population_test (5 years); not run by me under the one-year rule.
