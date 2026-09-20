# Caerness v0.60.0 — SCALE-01 reconstruction + TRADE-01 aggregate ordinary trade
**Date:** 18 September 2026  
**Schema:** 72  
**Status:** ACCEPTED NATIVE SLICE; TENYEAR-01 remains deliberately deferred.

## Why this exists

The prior SCALE-01/schema-71 working artifact was not present in the recoverable Sept-17 handoff. Its accepted macro denominators and five exact settlement anchors were recoverable, so schema 71 has been reconstructed without pretending the unavailable per-settlement table was recoverable.

Preserved accepted denominators:
- world population: 52,000,000;
- urban: 7,172,000;
- rural/dispersed: 44,828,000;
- 59 named settlement profiles;
- exact recovered anchors: Crownhold 520,000; Saltmere 260,000; Aldergate 210,000; Cairnholt 115,000; Toll’s Reach 110,000;
- settlement/institution/gang scale-band semantics.

Non-anchor named-settlement populations are deterministic campaign calibration preserving the accepted regional/world denominators. They are marked as reconstructed calibration, not setting canon. The independent/frontier urban share (551,000) stays structural rather than inventing unnamed city identities.

## TRADE-01 authority split

Aggregate trade owns ordinary/background material circulation at regional bulk resolution:

`population -> consumption requirement -> production -> local absorption -> surplus/deficit -> exports/imports -> transport loss -> reserve/unmet demand`

MERCHANT-01 continues to own crystallized lots, named enterprises, offers, contracts, shipments and settlement. Tracked contracts are not added on top of aggregate world material totals. A later crystallization bridge may reserve a specific aggregate flow when a background transaction becomes narratively important.

Cultivation resources and elixirs are deliberately excluded from ordinary population-scaled trade.

## New persistent owners

Schema 71:
- `population_scale_buckets`
- `settlement_scale_profiles`
- `institution_scale_profiles`
- `military_scale_profiles`

Schema 72:
- `aggregate_trade_profiles`
- `aggregate_trade_reserves`
- `aggregate_trade_corridors`
- `aggregate_trade_balances`
- `aggregate_trade_flows`

## Geographic resolution rule

Where exact route geography is already crystallized, it outranks macro fallback. Activation found a tracked Underheaven–Windmere corridor via Cairnholt -> Toll’s Reach -> Saltmere. Closing the known Toll’s Reach–Saltmere leg blocks that tracked macro corridor; TRADE-01 may not silently teleport the flow using its unresolved-geography fallback.

Where exact inter-regional geography is genuinely unresolved, flows use `aggregate_macro` resolution and explicitly state that no particular road/river/port is asserted.

## Growth/telemetry correction

`growth.regional_state()` no longer treats a count of fulfilled named merchant contracts as the main measure of settlement trade. It now exposes:
- SCALE-01 settlement population;
- aggregate trade bucket;
- 365-day aggregate dispatched volume;
- volume per 1,000 population;
- latest aggregate demand coverage;
- tracked contract count only as a secondary high-resolution signal.

This fixes the earlier category error where a few crystallized contracts could imply the economic activity of a city of hundreds of thousands.

## Acceptance results

Fresh current-seed activation:
- schema 72;
- 8 population buckets;
- 59 settlement scale profiles;
- 56 region×ordinary-good aggregate profiles;
- 413 ordinary settlement market rows after activation (including pre-existing market rows);
- 1 tracked cross-region aggregate corridor from existing route geography;
- SQLite integrity `ok`; foreign-key check clean.

First monthly cycle:
- consumption requirement: 61,308,000 bulk-equivalent units;
- 22 inter-regional flows;
- dispatched: 475,606.080;
- delivered: 468,794.664;
- explicit transport loss: 6,811.416;
- unmet demand: 51,630.336.

Controlled route-authority test, naval supplies:
- known corridor closed: Underheaven unmet demand 46,200; no Windmere -> Underheaven flow;
- route reopened: tracked route `[Saltmere–Toll’s Reach, Toll’s Reach–Cairnholt]` used; unmet demand fell to 15,131.04.

Full 365-day unattended integration, chunked through the ordinary world clock:
- final day: 365;
- aggregate trade periods: 13;
- balance rows: 728;
- aggregate flow rows: 333;
- total consumption requirement: 797,004,000;
- dispatched: 17,134,111.850;
- delivered: 16,883,150.632;
- transport losses: 250,961.218;
- unmet demand: 980,794.368;
- material-balance violations: 0;
- demand-identity violations: 0;
- SQLite integrity: `ok`;
- foreign-key violations: 0.

Native isolated performance benchmark:
- 120 monthly trade cycles: 1.449 s;
- mean: ~12.075 ms/cycle;
- 6,720 balance rows;
- 3,008 flow rows;
- test DB: ~7.074 MB.

At this state size, replacing TRADE-01 with a dataframe/microsimulation framework has no demonstrated performance justification.

## Regression status

PASS:
- TRADE-01 acceptance;
- MERCHANT-01;
- GROWTH-01;
- CRAFT-01;
- INTEGRATION-01 health/agriculture/law;
- WAR-01;
- COVERAGE-01;
- smoke/dormant simulation;
- DEC-01;
- decision runtime;
- v0.60 Phase 2A;
- underworld rackets/assets;
- EVENTS-01.

The broad historical `tests/run_all.py` still stops at the pre-existing stale `v08_test.py` engine-version allowlist, which does not include 0.60.0. This was not rewritten merely to force a green umbrella runner.

## External-code comparison after the native slice

### TRADE-01 itself
Keep native.

SCML remains useful as design quarry for rich negotiated supply chains and explicit production/trading agents, but that is the *crystallized merchant* problem, not the 56-cell aggregate clearing problem. Its current repository README also reports Python 3.10/3.11 support, while this build environment is Python 3.13. The native cycle is already ~12 ms and directly respects Caerness authority boundaries.

The abcEconomics-style conservation principle has already been adopted: goods move, losses are explicit, and production/consumption are explicit exceptions to transfer conservation. No framework cutover is needed to obtain that invariant.

### Population/life-course backend
This is still worth a real benchmark later. The relevant candidates remain:
- native NumPy/array state;
- Polars;
- neworder;
- Starsim-style arrays;
- current SQL/Python as control.

Current upstream checks on 18 Sep 2026:
- neworder describes itself as a dynamic microsimulation framework with optimized C++, NumPy/Pandas compatibility, reproducible RNG and optional MPI, and currently requires Python 3.12+;
- Starsim 3.6.x has recent performance work around per-timestep overhead and agent-array indexing;
- Python Polars current stable release line is 1.44.x (2.0 RC also exists).

Those are relevant when Caerness benchmarks 10k/100k/1m background people through aging, mortality, union/birth, migration, occupation and household state. They do not improve this aggregate trade owner enough to justify a dependency.

The execution environment could not install optional packages from PyPI because outbound package DNS is unavailable, so no fabricated neworder/Polars runtime numbers are reported here.

## Next engineering boundary

The correct next comparison is **background population/life-course storage and event processing**, not aggregate trade. TRADE-01 is accepted as native unless a later real benchmark demonstrates a material advantage.

TENYEAR-01 remains deferred until that scale/backend comparison is either completed or explicitly judged unnecessary.
