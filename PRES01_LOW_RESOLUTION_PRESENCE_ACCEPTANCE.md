# Caerness Engine v0.60.0 — PRES-01 Low-Resolution Presence Acceptance

**Date:** 17 September 2026  
**Engine:** 0.60.0  
**Schema component:** 61 (current cumulative schema: 62)  
**Base:** REL-01 directed-relationships working branch

## Accepted scope

PRES-01 adds one shared answer to the question:

> Where can this person plausibly be encountered right now, at the resolution the simulation actually possesses?

It does **not** replace travel geography and does not pretend that a city-level actor location is a room-level fact.

Resolution precedence is:

```text
exact scene state
> tracked travel state
> habitual/frequented-location profile
> aggregate / coarse location fallback
```

The highest available resolution wins.

## Persistence

New owners:

- `actor_presence_profiles`
- `actor_presence_habits`

Profiles preserve a base anchor and provenance. Habits can encode home, workplace, institution and other frequented-location bases with weights, cadence, confidence and effective dates.

Existing `travel_plans` remains the authority for explicit travel. PRES-01 does not duplicate route or movement truth.

## Core semantics

### Broad location is not exact co-presence

`actors.current_location_id` remains useful as coarse geography, a base for arrangeable services, and an endpoint for real movement. It is **not**, by itself, proof that two people in the same city are standing together.

Large-settlement legacy anchors are deliberately weak.

### Explicit travel overrides habits

If an actor is on a tracked route, they cannot simultaneously be encountered at a stale habitual workplace merely because that habit remains persisted.

### Exact scene state overrides travel/habits

When a scene explicitly establishes who is present, that is the highest-resolution fact for that scene.

### Presence is not protagonist-relative

Dormant, strategic and followed characters all use the same API. Resolution tier affects how richly a person is simulated elsewhere; it does not grant the player special encounter gravity.

## Shared consumers migrated

PRES-01 now supplies the presence decision for:

- player scene `present_actors` for characters;
- local rumour exposure;
- information-channel local exposure;
- spontaneous institutional social-contact formation;
- direct player-conversation grounding;
- post-travel arrival competence triggers.

Institution actors are not treated as walking people. A located institution may still appear as scene context through its explicit institutional location.

Arrangeable interactions remain distinct from spontaneous co-presence. For example, a physician known to operate in a city can be sought out without requiring a random encounter roll. PRES-01 therefore does not turn broad geographic availability into a universal probabilistic gate.

## Migration: schema 60 → 61

Migration 61:

1. creates the profile/habit tables and indexes;
2. derives **present-day** profiles from already persisted facts;
3. gives explicit home/work/institution facts provenance-bearing habits;
4. imports a legacy current-location value only as a weak present-day anchor where appropriate;
5. records `presence_model_version=1`.

It does not fabricate past journeys or backdate derived movement history.

A real schema-60 REL-01 database containing 562 actors migrated successfully to the cumulative schema 62. All 462 active characters received a present-day presence profile; SQLite integrity remained `ok` with zero foreign-key violations.

## Acceptance tests

New:

- `tests/pres01_low_resolution_presence_test.py`

It proves:

1. same large city != automatic exact co-presence;
2. a workplace habit materially raises plausible presence there;
3. tracked travel overrides a stale habit;
4. exact scene presence overrides both;
5. rumour exposure consumes the same API;
6. a DORMANT NPC uses the same rules as any other character;
7. late/migrated profiles start on the actual derivation day rather than inventing history;
8. database integrity and foreign keys remain clean.

Relevant regressions also pass, including information/privacy, player actions/model gateway, household/social-contact continuity, interactions and directed relationships.

## Result

PRES-01 is accepted as the low-resolution presence foundation.

The next completed layer in the cumulative branch is BELIEF-01 + Competence Lens.
