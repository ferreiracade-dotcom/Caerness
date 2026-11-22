# Task I-1: the intake core — report

Plan: `docs/superpowers/plans/2026-11-22-intake-core.md`. Schema **124** (I1b's 123 was latest). Python 3.13, script tests.

## Commits (all on feat/world-packages-saintjude, none pushed)
1. 5e7494c tables `held_things`, `depth_gaps`, intake package data, `intake_rules` (schema 124; the schema-version asserts in 4 older tests bumped)
2. 8772b6f proposal and shape registry
3. c6b4498 `take_in`, checks, gaps, `adopt_floor`; `authoring.author` goes through it (Caerness fingerprint regenerated: only the two new empty tables and schema rows changed)
4. 68cbd7f `engine/held_things.py` weekly B tick, registered in `simulation.py`
5. b82569b settled commitments become held things (`free_operation`)
6. e5490c2 connector: provenance, `lookup` (thing, "gaps"), author docstring, Saint Jude rulebook line
7. play-check test (`tests/intake_play_test.py`, 26 s, not slow) and this report

## Tests
- `tests/intake_test.py` 25/25; `intake_play_test` passes (printed: 36 money calls, warehouse income 500→450, org heat read).
- Quick suite: 160 pass, 50 fail. 41 of the 50 were disk-full errors (rerun green). The other 9 (`age_birthdate_mortality`, `deploy_files`, `popback01_background_population`, `schema110_underworld`, `seek01_natural_attraction`, `v20`, `v27`, `v30`, `world_activation_switches`) fail identically at I1b's HEAD (8535472) in a clean detached worktree: no new failures.
- Caerness regression, authoring, connector author/views/resume/server, no_world_words, org_migration all green.

## Rulings
- Built-in shape words (club, shop, store...) pick that shape only when the details carry a `name` or that shape's own fields; else "a pigeon club" would hit the organisation maker and fail. Cost if wrong: a GM sending a bare `name` for a thing meant as a floor row gets the built-in maker.
- `_kind_of` left unchanged (it has no connection); `intake.shape_for` owns the logic and delegates to it when the package has no intake data.
- Package words match whole words (so "car" does not match "card"); built-in words keep today's substring match.
- Plan tests pass `members` as a list; the organisation maker needs a number, so tests use `members: 2`.
- Fixture purses start empty; tests that spend fund the person with `ledger.receive` first.
- `take_in` is idempotent on `call_id` itself (returns the existing row, no second gap bump), besides the connector's replay.
- Settled commitments use the description as the kind text, because commitment kinds ("plan", "project") name no shape.
- Customs (`recurrence_days`) act once per occurrence: money (income/upkeep as per-occurrence) and heat; no weekly tick between.
- Rulebook line placed in `worlds/saintjude/rulebook_section.md`, not `connector/rulebook_core.md` (Caerness rulebook is hash-pinned).
- Tests for the connector live in `intake_test.py`, not `connector_author_test.py`.

## Deferred / notes
- `engine/org_lifecycle.py` and `tests/b15_test.py`, `saintjude_mob_fires_test.py`, `slow_tests.txt` carry other sessions' uncommitted edits; not touched.
- Another session's detached worktrees exist in %TEMP%; I removed only my own.
