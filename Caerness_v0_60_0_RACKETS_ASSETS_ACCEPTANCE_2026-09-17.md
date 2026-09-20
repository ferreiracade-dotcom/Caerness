# Caerness Engine v0.60.0 — Persistent Underworld Rackets/Assets

## Scope
Follow-up to ARCH-01, from the roadmap item "persistent underworld rackets/assets/crews."
Covers rackets and fronts specifically; crews were already reasonably developed
(create_crew, ensure_crew_leadership, ensure_zone_staffing, reconcile_crews_to_membership
all already existed and were not touched here).

## What was wrong, concretely
- `racket_kind` was a label with almost no effect on behavior (one crude substring check
  routed "gambl"/"book" to a "street_gambling" authorization check, everything else,
  including "high-risk debt," to "collections" instead of its own real activity).
- The racket pool used to open a new racket was one flat list, identical in every city
  and every zone.
- A racket's own `secrecy` field existed in the schema and was never read by the raid
  logic, which picked a random active racket uniformly.
- `underworld_business_links.status` already allowed `'seized'`; nothing in the engine
  ever set it. Fronts had no exposure at all.

## What changed
`RACKET_PROFILES`: eleven racket kinds, each with real income/heat multipliers, a
default secrecy and violence baseline, and a correct mapping to an existing
`TERRITORIAL_ACTIVITIES` entry (fixing the substring guess). Split into
`UNIVERSAL_RACKET_KINDS` (plausible in any city: protection, bookmaking, gambling,
high-risk debt, fencing stolen goods, brothel protection, courtesan house leverage) and
`WAREHOUSE_FLAVORED_RACKET_KINDS` (cargo fraud, invoice fraud, warehouse theft, seal
manipulation, weighted up, not exclusive, in warehouse/commercial/caravan zones).

This corrects an overreach in my own earlier read of the World Bible: I initially treated
Aldergate's paperwork/cargo emphasis as if it excluded ordinary gambling and brothels.
It doesn't; that line is relative to Toll's Reach-style port smuggling, not exhaustive,
and the setting explicitly treats gambling and nightlife as ordinary and near-universal.
The zone-kind-based weighting (not city-based) was the correct mechanism the whole time;
it just needed the universal baseline to actually be universal.

`racket_kind_options(conn, zone_id, rng, count)`: the new zone-aware picker, replacing
both flat lists (`_open_new_racket` and `seed_city_underworld`).

`create_racket_site`: now looks up the kind's real activity and applies its income
multiplier and secrecy/violence defaults (still fully overridable by the caller).

`_review_heat`'s racket-raid branch: now weights *against* secrecy (and, symmetrically,
a front's `admin_quality`) instead of picking uniformly, and its candidate pool now
includes fronts, not only rackets.

`seize_front()`: new. Marks the business link `'seized'`, closes the underlying
enterprise, recomputes the org's `front_depth` (pulled into a small `_refresh_front_summary`
helper shared with `create_front`), and emits an `underworld_front_seized` occurrence
through the same event machinery Phase 2A built.

## Proven, not just asserted
New `tests/underworld_rackets_assets_test.py`:
- every racket kind's `activity` is a real `TERRITORIAL_ACTIVITIES` entry;
- universal kinds appear with no zone given at all;
- across 500 samples each, a warehouse zone draws warehouse-flavored kinds at more than
  1.5x the rate a residential zone does, while universal kinds still appear in both;
- the fixed activity mapping has a real behavioral consequence: a guest authorized only
  for `collections` is correctly denied a `high-risk debt` racket, which the old
  substring guess would have wrongly allowed;
- across 300 paired trials, a secrecy-90 racket was suppressed less than half as often
  as a secrecy-10 racket under an identical forced raid;
- a front can be seized directly, the enterprise closes, `front_depth` drops, and a
  second seizure attempt correctly reports failure rather than silently double-firing;
- across 60 forced-raid trials with only a low-`admin_quality` front and no rackets
  available, enforcement actually reached and seized it, proving the new pool, not just
  the weighting formula, works end to end.

All prior suites (`v60_underworld_rebuild_test.py`, `v60_phase2a_test.py`,
`arch01_process_registry_test.py`, `v56_test.py`, smoke test) still pass unchanged.

## What comes next
Per the roadmap: the event-sourcing spike on territorial sovereignty, then directed
relationships, presence, belief/competence-lens, and the decision rewrite.
