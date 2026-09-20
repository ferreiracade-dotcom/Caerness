# Caerness Engine v0.60.0 — REL-01 Directed Relationships Acceptance

**Date:** 17 September 2026  
**Engine:** 0.60.0  
**Schema:** 60  
**Base:** `Caerness_Engine_v0_60_0_EVENTS01_WORKING.zip`

## Accepted scope

REL-01 implements the post-EVENTS-01 roadmap item **directed relationships** only.

The old `relationships` table looked directional but behaved largely as an unordered/shared pair because callers frequently:
- sorted actor IDs before writing;
- searched either orientation;
- averaged both orientations;
- or updated both directions together.

REL-01 gives the existing table one explicit meaning:

```text
actor_a_id = source / observer
actor_b_id = target
```

An A→B evaluation is no longer B→A by definition.

Structural relationships remain separate owners and were not collapsed into this table:
- kinship;
- household unions / spouses;
- teaching relationships;
- institution membership;
- offices;
- contracts and agreements.

## Directional dimensions

The relationship owner now supports:

```text
source_actor
target_actor
stance                 # retained transitional general-valence field
familiarity
trust
affection
respect
fear
loyalty
resentment
obligation
professional_confidence
```

`stance` is retained because existing systems still consume it. It is now explicitly directional and can be retired or derived only when later consumers are migrated to richer dimensions.

New dimensions begin neutral unless a causal system actually writes them; REL-01 does not fabricate historical affection, fear, loyalty, etc. from the old generic `stance` value.

## Migration: schema 59 → 60

Migration 60:
1. adds the new dimensions;
2. snapshots pre-migration relationship rows;
3. for each row with no reverse row, inserts a reverse row with the same pre-REL-01 values;
4. if both directions already existed, preserves both independently rather than overwriting either;
5. adds source/target indexes;
6. records `directed_relationship_model_version=1`.

This gives old campaigns behavior-preserving initial symmetry without imposing permanent symmetry afterward.

A real untouched schema-59 EVENTS-01 database was upgraded successfully to schema 60:
- original one-way test relationship was mirrored exactly;
- deliberately pre-existing B→C / C→B differences were preserved;
- SQLite integrity: `ok`;
- foreign-key violations: `0`.

Historical chronology is not invented. The migration creates the minimum state needed to preserve old shared meaning.

## New relationship API

New `engine/relationships.py` owns:
- `relationship_view(source, target)`;
- `ensure_relationship(source, target)`;
- `ensure_reciprocal_relationship(a, b)` for genuinely mutual initial contexts;
- `adjust_relationship(source, target)`;
- `adjust_relationship_pair(...)` when one event causally affects both perspectives;
- `relationship_exists(source, target)`.

A directional adjustment mutates one row only.

## Consumers corrected

### Decisions
Actor decision context now reads only the actor's own outgoing relationship views. It no longer rewrites an incoming row as if it were the actor's belief or averages both sides.

### Domain actions
Partner selection, distressed-enterprise buyer selection and martial-challenge selection now use **the acting person's view of the target**, rather than an unordered pair.

### Social contact / household life
Sustained shared contact can still create or grow two initially similar views because both people are actually in the shared context. After creation, those views remain independent.

### Interactions
Generic accepted/rejected proposals still change the proposer's view of the recipient where that was the causal meaning.

REL-01 also fixes two cases that the symmetric model made impossible to express correctly:
- if an investigation is detected, the **target's** view of the investigator worsens;
- open attack changes both directions, but not identically: the target can gain more resentment/fear than the aggressor.

### Psychology
Bereavement now reads the living actor's relationship toward the deceased, rather than UNION-ing both orientations and risking duplicate grief processing after migration.

### Discovery / embodiment / player context / competence
These now read the observing actor's outgoing view when actor-relative relationship state is required.

### Crystallization
A crystallized actor can acquire a one-sided historical evaluation of an existing person without inventing that existing person's reciprocal opinion.

## One-sided relationships are allowed

REL-01 deliberately permits:

```text
A knows / evaluates B
B has no persisted evaluative relationship to A
```

This is useful for:
- reputation-derived familiarity;
- one-sided admiration or fear;
- surveillance;
- distant professional confidence;
- asymmetric patron/client awareness.

A reverse row is created only when a causal process warrants it.

## What REL-01 does NOT do

REL-01 does not yet implement:
- a belief/evidence model;
- low-resolution presence;
- automatic underworld loyalty/faction integration;
- political faction scoring;
- a full affection/romance system;
- derived `stance` replacement;
- event sourcing of every relationship tick.

Per the EVENTS-01 conclusion, ordinary relationship changes remain normal mutable domain state. They are **not** mass-event-sourced.

## Acceptance tests

New:
- `tests/rel01_directed_relationships_test.py`

It proves:
- A→B may differ from B→A;
- one-sided relationships are valid;
- all target dimensions exist;
- actor decision context reads the correct directional view;
- structural relationship tables remain separate;
- arbitrary NPC pairs use the same API (no protagonist privilege);
- DB integrity and foreign keys remain clean.

Green on final source:
- `tests.rel01_directed_relationships_test`
- `tests.events01_territorial_event_sourcing_test`
- `tests.econ01_underworld_economic_interests_test`
- `tests.v60_phase2a_test`
- `tests.v60_underworld_rebuild_test`
- `tests.underworld_rackets_assets_test`
- `tests.arch01_process_registry_test`
- `tests.v56_test`
- `tests.smoke_test`

Relationship-sensitive historical suites were also executed with their stale `ENGINE_VERSION` allowlist bypassed only in the test process; their substantive assertions passed:
- v0.28 domain actions;
- v0.34 family/civilian consequences;
- v0.43 generational continuity;
- v0.45 decade integrity;
- v0.19 household/life behavior;
- v0.39 psychology;
- v0.09 crystallization.

The old allowlists were not rewritten merely to manufacture a green historical-version check.

## Result

REL-01 is accepted as the new current v0.60 working branch.

The next bounded roadmap item is **low-resolution presence**.
