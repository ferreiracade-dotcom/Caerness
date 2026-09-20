# Caerness Engine v0.56.0 — Vessel/Realization Handoff

## Build identity

- Engine: `0.56.0`
- Schema: `48` (unchanged)
- Working source: durable v0.47 line + inverse Stage-attainment calibration + v0.56 cultivation rewrite
- Setting authority: `Caerness_World_Bible_MASTER_FINAL.docx`

## Purpose of this build

v0.56 corrects the cultivation ladder so the mechanics implement the World Bible's stated progression: early cultivation is primarily Vessel development; genuine Realization becomes increasingly decisive and creates the first major wall at Third→Breach.

## Important invariants

1. Age is never a runtime promotion input.
2. Average age-at-attainment is an inverse distribution, not an expected Stage by current age.
3. Opening/current Stage plausibility can still depend on age + culture + role + training history.
4. First→Temper and Temper→Third are `vessel_maturation` transitions.
5. Third→Breach, Breach→Fifth and Fifth→Sixth are `realization_wall` transitions.
6. The Hearth/outer offset emerges through ecology/training milieu, never a regional hard cap.
7. Realization anchors are Stage-bound by default and cannot be banked across Stage changes.
8. Numeric thresholds/probabilities are campaign calibration, not canon.

## Main code changes

### `engine/cultivation.py`

- Added transition regimes to `REQUIREMENTS`.
- Added deterministic structural maturation path for lower transitions once causal readiness is met.
- Retained irregular opportunity/success logic for mastery transitions.
- Strengthened physical ecology/training effects on lower Vessel development.
- Added nonlinear whole-Vessel ecology factor specifically for Temper→Third.
- Added Stage-bound Realization metadata and old-Stage anchor closure.
- Split early maturation check timing from high-stage Realization opportunity timing.
- Preserved no-age/no-elapsed-time catch-up behavior.

### `engine/db.py`

- Engine semantic version bumped to `0.56.0`.
- Schema remains `48`.

### Tests

- Added `tests/v56_test.py`.
- Updated legacy tests that encoded the superseded assumption that every Stage transition requires a rare Realization event.
- Updated historical semantic-version guards to allow v0.56 while keeping their behavioral assertions.

### Diagnostics

- Added `diagnostics/v56_focus_cultivation.py`.
- Added focus reports for Sella, Tobin and Ansel.

## Current campaign calibration

Transition requirements in v0.56:

| Stage | Vessel | Ordinary Realization / wall | Mode |
|---|---:|---:|---|
| Unstaged→First | 55 | 24 | vessel maturation |
| First→Temper | 72 | 32 | vessel maturation |
| Temper→Third | 90 | 44 | vessel maturation |
| Third→Breach | 84 | 76 (practice cap 65) | realization wall |
| Breach→Fifth | 86 | 86 (practice cap 80) | realization wall |
| Fifth→Sixth | 93 | 95 (practice cap 88) | realization wall |

Do not treat these values as canonical lore numbers.

## Validation snapshot

Three-seed ten-year cohort calibration:

- Hearth Firsts: 74–78% reach Third in another decade.
- Outer Firsts: 89–96% finish Temper; 4–11% reach Third.
- Hearth Tempers: about 91% reach Third.
- Outer Tempers: roughly 35–54% reach Third; the rest largely remain Temper.
- Opening Thirds: only a few percent reach Breach over the sampled decade.

Focus cultivation-only runs:

- Sella Marrin: Temper age 24 → Third age 34; breakthrough Day 1275.
- Tobin Verra: Temper age 23 → Third age 33; breakthrough Day 1090.
- Ansel Rooke: Temper age 31 → Temper age 41; low Vessel aptitude blocks whole-Vessel maturation despite high Realization aptitude.

These are alternate diagnostics, not canon history.

## Regression status

Green: v56, v48 inverse-attainment, v47, v46, v45, v44, v42, v37, v33, v32, v29, v20.

## Known next integration task

The durable v0.56 branch does **not yet contain the full later role/material/ordinary-life/underworld coupling** developed in the transient v0.49–v0.52 work. Port those systems onto v0.56 before rerunning the final six-person decade biography gate.

During that merge, preserve these cultivation invariants exactly; do not restore age bonuses, nominal time-at-Stage bonuses, reusable Realization anchors, or a single universal breakthrough lottery.

## Companion report

See `Caerness_v0_56_VESSEL_REALIZATION_CALIBRATION_REPORT.md` for the World-Bible alignment argument, multi-seed cohort results, focus diagnostics and acceptance reasoning.
