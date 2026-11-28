# Task R1 report: real history (branch feat/world-packages-saintjude)

Plan: `docs/superpowers/plans/2026-11-23-r1-real-history.md`. Spec: `docs/superpowers/specs/2026-11-22-real-history-and-engine-gaps-design.md`. All commits carry "R1" and the Sonnet 5.5 trailer. Nothing pushed.

## What was built
- Schema 127: `held_things.basis_json`; tables `history_entries`, `divergences`, `tech_level`, `real_figures`. J1 was told to take 128.
- `engine/history.py`: propose/judge/resolve_need (holds/bent/broken/unknown, chain followed with visited set), divergence ledger, foreseen entries re-judged on their date (`settle_due`, run inside the weekly `held_things.process_due`, so `simulation.py` was not edited), `due_prompt` (`history_due` in `advance`), technology enablers, `screen` (distance-ahead scaling, foresight long_shot/informed).
- `engine/foreknowledge.py`: `character_knows` from competence (own and his people's) and knowledge rows.
- `engine/real_figures.py`: documented real figures, gazetteer actors adopted, illegal acts need a matching record word; `veto.real_person` now refuses an invented person wearing a real name and points to the lookup path.
- Intake shapes `history` and `real_figure`; `dated_rules` reads the run's own dates; `facts.override` and the death hook feed the ledger; memory-sourced entries are provisional ("to verify") until a source arrives via `note(kind="fact")`.
- GM surface: `lookup` history / real history / diverged / divergences / `real:<name>`; one rulebook line.
- `worlds/saintjude/history.json` and `timeline.json` classes (all figures marked Design proposal).

## Tests (all pass)
history_schema, history_propose, history_judge, history_divergence, real_figures, history_dated_rules, history_tech, history_due, history_connector, history_play (uncommitted, see below); intake_test, intake_play_test, veto_test, saintjude_dated_rules_test still pass.

## Cost
One-year run on a DB copy (`tools/run_years.py --days 365 --every 30`, busy machine, other sessions running): day-30 checkpoint 43.9 s (includes startup and contention; B15 baseline 3.5 s for 30 days on a quiet machine), later 30-day chunks 7.6-224 s, db 39.7 MB at day 365. With no foreseen entries the history tick is not scheduled; the death hook adds two small queries per death. Contention makes the numbers noisy; no per-day overhead was isolated.

## Suite (quick, partial: first run cut off at "m", second `--quick` run: 170 pass, 6 fail, 1 timeout)
- Known pre-existing: age_birthdate_mortality, deploy_files, v20, world_activation_switches.
- Seen failing, NOT investigated: `new_character_test` (not on the known list; may be J1's uncommitted `engine/new_character.py`, unverified); `saintjude_population_test` timed out at 1500 s.
- Failed in the suite but pass alone: `no_world_words_test`, `named_mortality_calibration_test` (load-related flake suspected).
- `saintjude_leak_scan_test` not run. `reg9` (saintjude_package_test etc.) result not rechecked.

## Rulings and deferred
- No market payoff for foresight: a `long_shot` bet has income zeroed, `informed` keeps stated income; no market engine exists.
- No reader yet for firm/price effects: a gap row is left.
- `failure_odds` stored in `basis_json` only.
- History effects and settling run weekly: up to six days late.
- `note_actor_death` flags only real figures and named causes.
- P3 and H3 are handled by the generic divergence/chain mechanism, no special cases.
- NPC foresight bets go through the same `screen`.
- Real figures seeded as opening actors have no documented record, so the off-record act check applies only to figures the GM documents.
- J1 files untouched; `engine/simulation.py` not edited.

## Unfinished
- Commit `tests/history_play_test.py`, `AGENTS.md` R1 paragraph and this report.
- Investigate `new_character_test` and `saintjude_population_test`; run `saintjude_leak_scan_test`; `git restore game/campaign_01/model_requests/`.
