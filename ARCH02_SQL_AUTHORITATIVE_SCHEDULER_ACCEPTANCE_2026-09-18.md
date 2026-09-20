# CAERNESS — ARCH-02 SQL-AUTHORITATIVE PROCESS REGISTRY ACCEPTANCE
**Date:** 18 September 2026  
**Engine:** v0.60.0  
**Schema:** 74  
**Status:** ACCEPTED FOR PRODUCTION `advance_connection()`

## Problem

The legacy world clock hand-enumerated every domain owner at every checkpoint. It was semantically forgiving but expensive: unrelated checkpoints repeatedly executed domains that had no due work.

ARCH-01 had already proved a registry abstraction, but its lazy due-date cache was unsafe because one domain can schedule earlier work for another after that other's cached due date was computed.

A second defect emerged during production cutover: caller API boundaries were being treated as simulation checkpoints through terminal catch-up. Therefore:

`advance(90)` could differ from `advance(30)+advance(30)+advance(30)`.

A due-date lookahead in the resolution controller also mutated latent review state using the caller's requested horizon.

## Accepted scheduler law

The public call boundary is **not** a world event.

```text
advance(N) == advance(a) + advance(b) + ...
when a+b+... = N
```

Subject only to volatile wall-clock metadata being ignored.

## Accepted design

- `ProcessRegistry` owns process registration and execution ordering.
- SQL due state remains authoritative.
- production uses **eager re-query**, not a lazy due-date cache.
- due-date query functions must be observational/pure.
- exact agreement / forced-tier expiry days advertise themselves as scheduler deadlines.
- newly scheduled cross-domain work is rediscovered through authoritative re-query.
- ordinary domain owners execute only when genuinely due.
- `advance_connection()` does not run arbitrary terminal catch-up merely because the caller stopped on that day.
- legacy scheduler remains available explicitly as `advance_connection_legacy()` for diagnostics/comparison, not production authority.

## Full-year chunk-invariance proof

Fresh schema-74 worlds were advanced as:

1. one call: `advance_connection(..., 365)`;
2. segmented: `30 × 12 + 5` days.

Thirty substantive tables were hashed after excluding volatile timestamp columns.

**Result: all 30 tables match exactly.**

Important matched state includes:

- 228 events;
- 3,735 knowledge rows and provenance;
- 4,171 actor beliefs;
- 203 rumours;
- 2,128 rumour transmissions;
- 3,651 rumour exposures;
- 333 aggregate trade flows;
- 728 aggregate trade balances;
- 619 actors;
- 131 civilian enterprises;
- all background population sources/cohorts;
- simulation profiles and presence profiles;
- relationships and information links;
- travel plans;
- tournament state;
- agreements;
- underworld organizations;
- latent entities, resolution profiles and 2,132 resolution reviews.

Both databases:

- SQLite integrity: `ok`;
- foreign-key violations: `0`;
- final story day: `365`.

Machine-readable evidence: `diagnostics/ARCH02_full_year_chunk_invariance_2026-09-18.json`.

## Performance comparison

Same corrected opening seed, 365 days:

| Scheduler | Runtime | Events | Enterprise account rows |
| --- | ---: | ---: | ---: |
| Production ARCH-02 registry | **15.824 s** | 228 | 1,123 |
| Legacy hand-enumerated loop | **24.574 s** | 228 | 3,307 |

These are development-environment measurements rather than device guarantees.

The legacy loop's extra 2,184 enterprise-account rows are chiefly repeated bookkeeping caused by running civilian owners at unrelated checkpoints, not additional narrative history.

## Bugs found and repaired during cutover

1. **Lazy registry cache:** could miss newly scheduled cross-domain work. Rejected for production.
2. **Terminal catch-up:** caller boundaries changed world history. Removed as ordinary-domain authority.
3. **Resolution lookahead mutation:** `next_resolution_due_day()` could create review dates based on the caller's horizon. Due lookup is now pure.
4. **Presence reseeding duplicates:** four migration-derived habit paths were not actually using the intended open-habit deduplication. Corrected.
5. **Imported life-stage inconsistency:** opening people whose stored life stage conflicted with exact age could generate false transition events; repaired through chronology-consistent state handling rather than preserving scheduler artifacts.

## Permanent regression

`tests/arch02_scheduler_chunk_invariance_test.py` protects:

- pure resolution lookahead;
- 90-day row-level caller-boundary invariance over 30 substantive tables;
- DB integrity / FK safety.

A separate full-year audit is retained in diagnostics because making every normal test pay the full 365-day hashing cost is unnecessary.

## Verdict

**ARCH-02 is accepted.**

The registry architecture wins because it improves both semantics and performance. A lazy cache or an external scheduler dependency is not justified by current evidence.
