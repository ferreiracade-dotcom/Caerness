# Task BZ1 report: the shared business layer

Implemented `docs/superpowers/plans/2026-11-22-business-bz1-shared-layer.md` (Tasks 1-8 committed 614dbbf..bb63cbe; Task 9 measure and this report in the final commit). Schema **125** (migration `business_layer`: driver_readings, venture_details, venture_parties, venture_approvals, place_details, agreement_terms, agreement_breaches + three next_due_day indexes).

## What exists
- engine/business_data.py (+ worlds/saintjude/business.json): validated package data; Caerness has none, so every tick is a no-op there.
- business_drivers (eight sourced factors, latest reading kept), agreement_terms (settled per due date; breach paths tension/debt/grudge/claim), places, ventures (stages, backers, parties, approvals that do not block), all on the civilian clock; resolve_business_cycle multiplies the drivers in and business_profile explains why.
- intake_business: holding -> place (or venture when ready_in_days), arrangement -> term; unreadable ones stay on the floor with a gap; claim breach bumps the "civil claim" gap.
- Caerness archetypes moved to worlds/caerness/archetypes.json (frozen-fixture test).

## Fixture diffs
tests/fixtures/caerness_opening_fingerprint.json regenerated twice (Task 2: the seven tables + schema_migrations/engine_meta; Task 5: agreement_terms.unpaid_since_day only). None since; controller has since said Caerness is ignored.

## Five-year measure (B15_SEED=3, saintjude_mob_fires_test, post-B15d code)
Layer ON: simulate 623 s, total 936 s, db 138.3 MB (23.92 MB/yr). Layer OFF (business_data.load patched to None): 596 s, 879 s, 138.3 MB. Cost +27 s (+4.5%, under the 5% flag, within run noise), size identical; every structural finding identical. The seven tables' row counts were not captured (temp DB not kept); identical size says they are negligible in a mob run that authors no places/ventures. Not tuned. (The ON run started before fix bb63cbe; that fix does not touch the clock.)

## Failures investigated
- saintjude_connector_play_test "federal judge 1979" and "public killing on Pad-paid ground": fail identically on baseline d546067 (pre-BZ1). Not BZ1; cause not investigated.
- intake_play_test (quick suite): **my bug in BZ1.8**: I registered the holding/arrangement makers with floor_backed=False, so a holding the maker could not read lost its depth gap. Fixed (floor_backed=True) in bb63cbe; also a place's takings still come through the held tick (only upkeep is the place's). Tests: intake_play_test, bz1_intake_test (6, two new).
- 9 quick-suite failures pre-existing on baseline (listed in ledger).

## Final review
Self-review (no fresh reviewer run): see ledger. No hard caps: breach scale, venture thresholds, place labels are business.json calibration.

## Rulings I made
See .superpowers/sdd/bz1/progress.md (Ruling: lines) and the final message.
