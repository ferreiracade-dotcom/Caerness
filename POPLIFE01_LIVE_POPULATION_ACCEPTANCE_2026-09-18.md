# CAERNESS — POPLIFE-01 LIVE POPULATION / LIFE-COURSE ACCEPTANCE
**Date:** 18 September 2026  
**Engine:** v0.60.0  
**Schema:** 74  
**Status:** ACCEPTED

## Purpose

POPBACK-01 solved bounded ordinary-person identity continuity. POPLIFE-01 makes the 52,000,000-person opening population causally live without creating 52 million full NPC records.

SCALE-01 remains the opening ecological/calibration authority. Runtime population thereafter belongs to POPLIFE-01 and may diverge causally; it is never rebalanced back to the opening target.

## Accepted population structure

- 68 disjoint `background_population_sources` cover the entire opening population exactly.
- 408 live age cohorts provide six age bands per source.
- `baseline_population_estimate` preserves the opening source calibration.
- live `population_estimate` changes through births, deaths and explicit transfers.
- bounded POPBACK identity partitions overlap the aggregate count and therefore never add a second population total.

Opening source sum: **52,000,000**.

## Year-one acceptance

Using the campaign's existing demographic calibration, one full annual population pass produces:

- births: **832,000**;
- deaths: **308,620**;
- net change: **+523,380**;
- end-of-year population: **52,523,380**.

No quota or target-share rebalance occurs.

## Movement acceptance

A controlled 10,000-person source-to-source displacement:

- conserves world population exactly;
- transfers age structure proportionally;
- records an explicit movement row;
- changes subsequent regional population reads.

This provides the population mutation primitive required by war displacement, migration, colonization, economic flight and disaster without inventing a parallel population counter.

## Cross-domain integration

TRADE-01 now reads **live POPLIFE population** rather than the frozen opening SCALE-01 denominator when determining aggregate consumption pressure.

Regional/growth reporting also prefers live population where available.

Thus demographic change can propagate into economic demand and state-capacity conditions rather than remaining diagnostic-only telemetry.

## Backend relationship

POPLIFE and POPBACK deliberately solve different problems:

```text
POPLIFE aggregate cohorts
    own headcount, birth, death, aging and movement

POPBACK identity partitions
    preserve bounded ordinary-person continuity and causal exposure

latent / named actors
    own rich individual state once promoted
```

A sampled identity's death or promotion is not independently added to/subtracted from the aggregate population total unless the population owner records the corresponding aggregate event.

## Acceptance tests

`tests/poplife01_population_life_course_test.py` — PASS.

Current broader regression after schema 74:

- POPBACK-01 — PASS
- TRADE-01 — PASS
- MERCHANT-01 — PASS
- GROWTH-01 — PASS
- CRAFT-01 — PASS
- INTEGRATION-01 health/agriculture/law — PASS
- WAR-01 — PASS
- COVERAGE-01 — PASS
- DEC-01 — PASS
- EVENTS-01 — PASS
- PRES-01 — PASS
- information/belief/relationship/interaction/smoke — PASS
- Python `compileall engine/` — PASS

## Stop boundary

POPLIFE-01 is intentionally aggregate. It does not attempt to create universal individual genealogy, household identity or occupation history for all 52 million people. Those details materialize only when causal resolution requires them.
