# Caerness Engine v0.60.0 — Phase 2A Acceptance (plus Phase 2B foundation)

## Accepted scope
v0.60 Phase 2A (foundation adjustment) per `CURRENT_WORK/V0_60_PHASE2_REVISED_IMPLEMENTATION_PLAN_2026-09-17.md`
sections 3.1-3.6, implemented against direct inspection of the v0.60.0/schema-55 working
source, not the plan's prose summary alone. Phase 2B's substrate (section 4) was found to
already exist from Phase 1's `seed_city_underworld`; what Phase 2A/B still needed there
(geography anchoring, an honest World Bible theme cross-check) is included below.

## Engine/schema
- Engine: `0.60.0` (unchanged; still the current v0.60 working branch, per the plan)
- Schema: `56` (migration 56: `underworld_zone_geography_anchor`)

## What changed, by plan section

**3.1 — Zone graph interface.** `UnderworldZoneGraph` (`engine/underworld_rebuild.py`):
`neighbors`, `are_adjacent`, `permeability`, `reachable_from`. SQL remains authoritative;
no graph library dependency added. `_adjacent_targets` and `_vacant_adjacent_zones` now
use it instead of ad hoc adjacency SQL; their return values are unchanged.

**3.2/3.3 — Event-shaped mutation, separated from projection mutation.** New
`_record_territorial_occurrence()` helper wires the engine's existing
`events`/`event_targets`/`causal_links` tables into territorial code that, on direct
inspection, almost never touched them before this pass (only `underworld_operations`/
`underworld_incidents` rows existed). All nine required occurrence kinds are now emitted:
`underworld_zone_claim_established`, `underworld_zone_control_changed`,
`underworld_encroachment_attempted`, `underworld_operating_permission_granted`,
`underworld_operating_permission_revoked` (new explicit `revoke_operating_permission`,
plus the implicit supersede-on-regrant path), `underworld_protection_poach_attempted`,
`underworld_zone_became_contested` (fires only on the no-challenger -> challenger
transition, not on every re-challenge), `underworld_territorial_attack`, and
`underworld_territorial_attack_resolved`. Each links to its causing
`underworld_operations`/`underworld_incidents` row via `causal_links`
(`source_kind='world_process'`, since no existing causal_links source kind fits an
autonomous background action better). `event_logger` is optional everywhere it was added:
callers with none still get the authoritative SQL row, just no event.

**3.4 — Concrete candidate-action boundary.** `UnderworldCandidateAction` (frozen
dataclass) and `underworld_candidate_actions()`: real zone/organization targets only,
verified non-mutating (test asserts zone_claims/relations row counts are unchanged across
a call). `autonomous_organization_turn`'s option-list construction now sources its
existence checks from this function instead of duplicating adjacency/treasury SQL; the
weighting formula itself (2x vacant-turf, aggression-scaled attack, etc.) is byte-for-byte
the same as before, so this is a refactor, not a behavior change.

**3.5 — Shared-geography anchoring.** New nullable `underworld_zones.anchor_location_id`
(migration 56, guarded/idempotent `ALTER TABLE`). `ensure_zone_anchor_locations()`
backfills a district-scale `locations` child row (`is_canon=0`, `parent_location_id` =
the city) for any zone that lacks one; idempotent, additive, does not touch
`city_location_id`'s existing meaning.

**3.6 — Cross-system tags.** Encroachment/poach occurrences carry `enterprise_affected`
and activity-kind tags; attack occurrences carry `violence`/`territorial_change` or
`territorial_defense`.

## Phase 2B substrate: already existed, now anchored and cross-checked
Direct inspection of `seed_city_underworld` shows Phase 1 already seeded 12 zones, 7-10
territorial organizations, initial claims, and vacant-zone assignment, each zone
explicitly flagged `"not_world_bible_canon": True`. That satisfied the letter of the
anti-invention rule (6.8) by construction. Two things were still missing and are now
done:

- **Geography anchors.** `ensure_zone_anchor_locations` run against Aldergate's existing
  12 zones; all now resolve `zone -> anchor_location_id -> parent_location_id -> city`
  without parsing `zone_key` strings.
- **World Bible theme cross-check.** The Bible's Aldergate entry names an "Exchange
  Quarter, warehouses, caravan wards and finance houses" as the city's defining
  commercial features, and gives no ward names, count, or boundaries. New
  `apply_world_bible_zone_theme_citations()` annotates exactly the 5 of 12 zones whose
  *theme* matches (`exchange`, `warehouse_east`, `warehouse_west`, `caravan_north`,
  `caravan_south`) with a citation, while leaving `not_world_bible_canon` on all zones
  unchanged — the theme is grounded; the specific zone as a fixed place is still working.
  The other 7 zones (Market/Craft/Old Quarter/River Gate/East Road/South Yards/North
  Residential) have no Aldergate-specific canon support found and are untouched.
- **Not modeled, flagged for awareness only:** the World Bible gives Aldergate a named
  legitimate power structure (the Counting House's principal seat; House Fenwick as
  strongest merchant dynasty, with Serrick/Orlan/Merevale; Stonebridge Escorts) distinct
  from the criminal-zone layer this slice covers. Integrating that is a MerchantHouse-
  system-shaped task the plan explicitly defers (section 5); it was not touched.
- The World Bible's own named Aldergate criminal dynasty ("Tallow Family") is confirmed
  still correctly retired to quarry by the existing v0.60 rebuild firewall
  (`enforce_rebuild_firewall`, migration 51) and was not revived.

## Off-camera parity (6.7)
Structural check: no branch in `engine/underworld_rebuild.py` keys behavior off
player/followed/protagonist identity (grepped for `is_player`, `is_focus_org`,
`followed_organization`, `protagonist_org`, `player_organization_id`; none present).
Functional check: `autonomous_organization_turn` runs to completion for a non-followed
rival organization through the same code path.

## Tests
New: `tests/v60_phase2a_test.py` — sections 6.2-6.8 (6.1 already covered by
`v60_underworld_rebuild_test.py`). Green.

Green, unaffected: `v60_underworld_rebuild_test.py`, `v56_test.py`, `smoke_test.py`
(run as `python -m tests.smoke_test`; direct execution needs that module form,
unrelated to this pass).

**Pre-existing, confirmed unrelated to this pass** (checked against the untouched
v0.60.0/schema-55 zip before any Phase 2A edit): `v37_test.py` and `v59_test.py` fail on
stale `ENGINE_VERSION` allowlists that were never updated when the engine moved to
0.60.0; `v48_attainment_inverse_test.py` fails the same way; `v26_candidate_scale_test.py`
fails an unrelated enterprise-count assertion (212 vs 200). None of these were altered to
force a pass, per the plan's own instruction.

Backups of every file this pass touched are kept alongside the originals with a
`.pre_phase2a` suffix, matching this codebase's existing backup convention
(`.pre_flexible`, `.pre_org_forms`, etc.).

## What comes next
Per the plan's own sequencing (section 9): ProcessRegistry/scheduler rewrite, then
concrete underworld rackets/assets/crews, then the event-sourcing spike. This package
stops here, as instructed ("do not immediately proceed into rackets/assets in the same
unreviewed patch").
