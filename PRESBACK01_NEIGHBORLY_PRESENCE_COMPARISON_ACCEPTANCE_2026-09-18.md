# CAERNESS — PRESBACK-01 NEIGHBORLY-STYLE PRESENCE ACCESS ACCEPTANCE
**Date:** 18 September 2026  
**Engine:** v0.60.0 / schema 74  
**Status:** ACCEPTED PATTERN; no Neighborly framework dependency

## Question

After profiling the integrated year, information propagation and low-resolution presence were spending substantial time repeatedly discovering the same location/day candidate population.

Should Caerness keep a broad active-character scan, adopt Neighborly wholesale, or adapt Neighborly's reverse location access pattern while retaining Caerness authority and semantics?

## External pattern tested

Neighborly's useful idea for this problem is not ECS itself. It is the bidirectional low-resolution presence model:

```text
character -> frequented locations
location  -> frequenting characters
```

This lets a location query start from actors who have a reason to be there instead of scanning every active character.

Caerness keeps its own precedence:

```text
exact scene
> tracked travel
> habitual / aggregate presence
```

and keeps SQLite as authority.

## Production implementation

`engine/presence.py` now provides `presence_probability_snapshot(location, day)`.

The snapshot:

- starts from reverse location eligibility (habits, base, current broad anchor, active travel);
- loads candidate travel/profile/habit state in batches;
- computes actor -> presence probability once for a location/day;
- leaves rumour/purpose-specific deterministic selection downstream.

`engine/information.py` caches that probability snapshot by location/day while processing transmissions, so several rumours reaching the same place on the same day do not rebuild the same physical-presence state.

## Direct parity benchmark

A fresh 180-day world generated 887 real/supplemental location-day queries.

Comparison:

| Access path | Runtime | Result mismatches |
| --- | ---: | ---: |
| prior batched all-active-character scan | 2.026 s | — |
| reverse location index | **1.525 s** | **0** |

Observed speedup: **1.33×** on this run.

Machine-readable result: `diagnostics/PRESBACK01_presence_backend_comparison_2026-09-18.json`.

The exact speedup varies with cache/host conditions; zero semantic mismatch is the acceptance requirement.

## Additional correctness repairs

- Migration-derived home/current/work/institution habits now check for an existing open habit before seeding, preventing repeated lazy reseeding from duplicating presence state.
- Assessing an institution no longer triggers the global character presence seeder merely because institutions intentionally lack character presence profiles.
- probability snapshots are independent of a particular rumour ID; only the deterministic exposure draw is rumour/purpose-specific.

## Full-year compatibility

After PRESBACK-01, ARCH-02's full-year one-shot/chunked comparison remains row-identical across the substantive 30-table acceptance set, including all rumour transmissions/exposures and actor presence profiles.

## Framework verdict

**ADOPT the Neighborly access pattern, not the framework.**

Caerness does not need to move authoritative world state to Neighborly/ECS. The proven gain comes from reverse locality and reusable low-resolution presence snapshots, both of which integrate cleanly with the existing SQL/event/information model.
