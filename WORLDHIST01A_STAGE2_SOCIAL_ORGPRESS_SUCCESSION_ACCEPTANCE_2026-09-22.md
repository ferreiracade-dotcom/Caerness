# WORLDHIST-01A Stage 2 — REL-02 / ORGPRESS-01 / SUCCESSION-02 Acceptance

**Date:** 22 September 2026  
**Engine:** v0.60.0  
**Schema:** 106  
**Parent checkpoint:** `c3b5027736cbf3a549a814b5d1a53639cf814681` (schema-105 FAMILY-02/HARM-01)

## Purpose

Stage 2 makes consequential events persist as social and institutional history instead of ending as isolated event rows.

## Implemented

### REL-02 social memory
- Added `relationship_history` with exact causal source provenance.
- Successful, refused, coerced and countered NPC interactions now write asymmetric familiarity/trust/respect/fear/resentment/obligation/professional-confidence effects.
- Three materially identical refusals within the recent window suppress another unchanged approach for 180 days instead of generating pathological repeat requests.
- A materially different proposal remains possible; this is memory/cooldown, not loss of agency.

### ORGPRESS-01 event projection
- Added reusable event-driven organization pressure accumulation on the existing `organization_pressures` owner.
- Added causal faction creation on the existing `organization_factions` owner.
- A resolved internal duel now writes social memory for both combatants.
- If an incumbent institutional head is publicly defeated by a member, the institution receives leadership-legitimacy pressure.
- Defeat never directly removes the incumbent; subsequent organizational politics own the response.

### SUCCESSION-02 authority transitions
- Added `leadership_transition_cases`.
- Death of a named incumbent vacates the authority slot and creates leadership pressure with provenance.
- Generic institutions can resolve a clear successor only from living, already-existing active members satisfying the authority requirement.
- Close qualified contests remain unresolved and create actual candidate factions instead of selecting randomly.
- Political succession remains authoritative in the existing polity claim/dynasty system; the generic authority bridge synchronizes to its result.
- Underworld leadership remains authoritative in the existing underworld succession owner; the generic transition ledger synchronizes to that result.
- No replacement adult is invented to fill a vacancy.

## Acceptance tests

PASS:
- `tests/rel02_interaction_memory_test.py`
- `tests/orgpress_succession02_test.py`
- `tests/interaction_test.py`
- `tests/rel01_directed_relationships_test.py`
- `tests/orgagency_conflict01_test.py`
- `tests/orglife01_country_lifecycle_test.py`
- `tests/family02_feasibility_firewall_test.py`
- `tests/harm01_shared_consequence_test.py`
- `tests/war01_campaign_battle_world_consequences_test.py`

The WAR-01 regression specifically caught and fixed an ownership conflict: ruler death must remain visible to the established political succession resolver rather than being prematurely consumed by the generic authority bridge.

## Packaged opening state

- schema: 106
- story day: 0
- `relationship_history`: 0 (history starts from play, not manufactured opening events)
- `leadership_transition_cases`: 0
- fresh acceptance epoch: `ONEYEAR_WORLDHIST01A_SCHEMA106` = pending
- SQLite integrity: `ok`
- foreign-key violations: 0

## Not yet claimed

Stage 2 does not yet implement broad EMERGENCE-02, full sect/clan feud strategy, war-origin recalibration, city/place history, religion/culture, or underworld-world consequences. Those remain subsequent WORLDHIST tranches.
