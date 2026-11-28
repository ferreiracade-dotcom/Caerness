# Global constraints (binding for every task)

## From the org-core plan

- Every Global Constraint of the mob-minimum plan still holds (Python path, scratch DBs, determinism, Design-proposal figures, sex shares, levels, pull-up only via `person_ecology`, commit per task, no push), except the schema line: this plan adds **migration 117** (`SCHEMA_VERSION = 117`), tables also in `engine/schema.sql` with `IF NOT EXISTS`.
- **No sphere vocabulary in core modules.** `engine/orgs.py`, `engine/org_money.py`, `engine/org_motives.py`, `engine/org_choices.py`, `engine/org_lifecycle.py`, `engine/crime_response.py` and `connector/views.py` contain no rank title (`boss`, `underboss`, `consigliere`, `capo`, `soldier`, `associate`, `made`, `president`, `banker`…), no outfit name and no dollar figure. A test greps for them (Task C2).
- Mob words live only in `worlds/saintjude/*.json`, `engine/outfit_*.py` and `engine/law_opening.py`'s Pad builder (which reads its words from `law.json`).
- Caerness behaves exactly as before: `tests/world_pkg_caerness_regression_test.py` green; Caerness's own organisation tables (`civilian_enterprises`, `organization_*`, `institution_*`) are not touched.
- After every task, every existing Saint Jude test listed under Task C1 Step 5 passes.

## Review focus (org-core plan)

1. **One person, two organisations.** A capo who also owns a trucking firm, an alderman who also runs a union local. Seats are per (person, organisation); his simulation level is the highest of his active seats; when he dies each org's line passes to that org's own stand-in. Test in C2 (`test_two_seats_two_stand_ins`).
2. **A migrated campaign DB.** An existing schema-116 DB (Caerness, and a Saint Jude scratch opening built before this plan) must migrate with every row kept and the same money totals. Test in C1 (`test_116_saintjude_opening_survives_117`).
3. **An org kind with no unit leader** (Brigades, a one-man firm). Stand-in falls straight to the head; a head with no live successor leaves the line unearned without crashing. Test in C2 (`test_kind_without_unit_leader`).
4. **A payer who is a person, not an organisation** (a builder bribing an inspector). The arrangement must draw from his own purse and post a ledger flow. Test in C3 (`test_person_pays_an_official`).
5. **A choice registered by a sphere the package does not enable.** The provider must offer nothing for org kinds the package does not declare. Test in B10 (`test_undeclared_kind_offers_nothing`).

## From the mob-minimum plan (still hold, except schema line: now 117)

- Python: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe"`. Always simulate on a copy: tests build into a temp dir; never write `data/*.db` except in Task 16.
- **No Saint Jude values in `engine/` or `connector/`**: no family, gang, place, rank-title or dollar figure literals. They come from package data. The `step1_diff.md` grep rule applies to every diff.
- New engine behaviour runs only when `system_enabled(conn, "outfits")`; a Caerness campaign must behave exactly as before (`tools/run_suite.py` green; `tests/world_pkg_caerness_regression_test.py` green).
- Schema: one migration, **116**, in `engine/db.py` (`SCHEMA_VERSION = 116`), tables also in `engine/schema.sql` with `IF NOT EXISTS`.
- Determinism: every random draw uses `random.Random(f"{design.run_seed(conn)}:{stream}:{key}")`. Same run seed, same opening and same run.
- Every number not taken from the bible is a figure in `design_figures.json` with `"mark": "Design proposal"` and either a `source` or `"note": "unsourced"`. No silent constants.
- Sex shares (spec §3): made men, Brigades, Horsemen (members, prospects), Russians 100% male; Italian associates and other gang roles 99.5%; numbers bankers, controllers, bolita runners 99%; Pad officers 99%.
- Levels: 4 = daily (`cadence_days` 1), 3 = weekly (`cadence_days` 7). The routine "carry on" choice writes no `decisions`, `decision_evaluations` or `decision_candidate_audit` row.
- Pulling up: a new active person always comes from `background_person_profiles` via `person_ecology`; never `INSERT INTO actors` directly for a person in outfit code.
- Commit after each task. Do not push. Sonnet subagents implement; an Opus reviewer checks each task's diff.

## Owner overrides
- Owner rule: the controller reviews each diff; do NOT dispatch reviewers. Commit on branch feat/world-packages-saintjude only; never push; never switch branches, stash or reset.
- Leave untracked data/caerness.pre-schema110.db and game/campaign_01/backups/ alone. After running tests that touch game/campaign_01/model_requests/, run 'git restore game/campaign_01/model_requests/'.
- Python: "$LOCALAPPDATA/Programs/Python/Python313/python.exe" (bash: /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe).

## No hard caps, anywhere (owner, 2026-11-21)
Hard caps are directly opposed to realism and plausibility. There will always be rare exceptions either way, surprises, unusual years and ordinary average years, and the simulation must allow all of them. A target range is only a reasonable expectation. A result outside it stands if it is plausible for what happened in that run. If it is implausible, fix the driver that made it so. Never use a cap, floor, clamp, quota, cooldown or brake to hit a number. Every brief and every review applies this.

## Long runs (owner, 2026-11-21)
- At most two long simulations at once on this machine, and never alongside the quick suite. Six 5-year runs in parallel crawled for nearly two hours.
- One run gives both the violence and the law figures: never simulate the same seed twice.
- Long runs print progress at least every simulated year, so a stall is visible.

## The protagonist lives under the same rules (owner, 2026-11-22)
Whatever can happen to anyone else can happen to the protagonist, through the same drivers, in every system: law, sweeps, informing, debts, slights, discipline, being poached, deference he owes, reputation, family spill, illness. There is one exception: when his own survival is genuinely uncertain, lean toward his living, with real consequences. Never exempt him otherwise, and never build a player-only rule. Add a test where a system acts on people, showing it can act on him.

## Temp files (owner, 2026-11-22)
Tests must clean up. tools/run_suite.py now gives each test its own temp dir and removes it. When running a test script directly, set TMP/TEMP/TMPDIR to a dir under runs/ and remove it afterwards. New tests use tempfile.TemporaryDirectory or remove what they make.

## Caerness is ignored (owner, 2026-11-22; supersedes "Caerness behaviour-identical")
Caerness will not be played in its current form; it is renovated after the current three games are made. Ignore it entirely: no behaviour-identical requirement, no fingerprint regeneration, no Caerness regression checks, and Caerness-only test failures are not blockers. Keep engine/ free of world words (that rule is about genericity, not Caerness). Do not delete Caerness code or data.

## Run length (owner, 2026-11-23)
No check or cost run longer than one year. Use 30-day and one-year runs; five-year runs are retired.

## Suite (owner, 2026-11-24)
Always `tools/run_suite.py --quick`, never the full suite (the full suite adds the slow tests, e.g. world_pushes_back_test at ~18 min). Run the full suite only when the controller asks for it by name.

## Canon figures are banded targets at the opening only (owner, 2026-11-24)
When the opening is built, a canon figure (an outfit's size, a count the bible fixes) lands somewhere inside a small band from package data, so playthroughs differ. Once play starts there is no band and no pull back toward it: figures move freely through the simulation's own causes. A first-year collapse from opening history alone means that history was seeded too hot, so fix the seeding, not the run.
