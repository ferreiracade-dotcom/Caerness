# Caerness Engine v0.60.0 — EVENTS-01 Territorial Event-Sourcing Spike Acceptance

**Date:** 17 September 2026  
**Engine:** 0.60.0  
**Schema:** 59  
**Base:** `Caerness_Engine_v0_60_0_ECON01_WORKING.zip`  
**Status:** ACCEPTED SPIKE — sidecar only; no authority cutover.

## Purpose

Prove, on one bounded real Caerness domain owner, that event sourcing can provide:

1. immutable append;
2. deterministic projection;
3. persistence/restart;
4. full replay/rebuild;
5. snapshot + tail recovery;
6. counterfactual branching;
7. event-version evolution/upcasting.

The bounded owner is **underworld territorial sovereignty only**.

Current SQL remains authoritative during the spike.

## Deliberate scope

EVENTS-01 event-sources only the state necessary to reconstruct:

- active territorial controller claims;
- active challenger claims / contested state;
- active operating permissions.

It does **not** event-source:

- rackets;
- protection accounts;
- economic interests/flows;
- crews;
- violence/casualties;
- organization politics;
- relationships;
- households;
- the rest of the world.

Those remain under their existing owners.

## Schema 59

New tables:

- `territorial_event_branches`
- `territorial_domain_events`
- `territorial_projection_zones`
- `territorial_projection_challengers`
- `territorial_projection_permissions`
- `territorial_event_snapshots`

`territorial_domain_events` carries:

- branch;
- stream key;
- branch-local stream sequence;
- day;
- event type;
- explicit event version;
- machine payload;
- optional causal source kind/id.

Database triggers reject `UPDATE` and `DELETE` against territorial domain events. The event history is append-only.

## Domain events in the spike

- `territory.zone_control_set` — current version 2
- `territory.challenger_added` — version 1
- `territory.permission_granted` — version 1
- `territory.permission_revoked` — version 1

The current runtime writes these from the real territorial mutation paths in `underworld_rebuild.py`.

## Projection parity

`authoritative_territorial_state()` renders the existing SQL owner into the same semantic shape as the event-sourced projection.

Acceptance proves:

```text
event replay == event projection == current authoritative SQL
```

on a fresh current world and after additional controller/challenger/permission mutations.

## Restart

The acceptance test closes the database connection, opens a fresh connection, replays from persisted SQL events, and still reproduces current territorial truth exactly.

Nothing required for replay lives only in Python memory.

## Full replay / rebuild

The test deliberately deletes the event-sourced **projection tables only** while leaving immutable events intact.

`rebuild_territorial_projection()` reconstructs the projections from zero and again matches the current SQL owner exactly.

This proves the projection is disposable derived state rather than hidden authority.

## Snapshot + tail

`create_snapshot()` persists a full projection at an exact event boundary.

The test then performs a later territorial mutation, and:

```text
snapshot state + events after snapshot
== full replay
== current authoritative SQL
```

Snapshots therefore work as an optimization/read checkpoint rather than a new source of truth.

## Branching

`create_branch()` forks from a parent branch at an exact parent event id and materializes inherited state.

A hypothetical territorial control event can then be appended to the branch without changing:

- the base branch;
- current authoritative SQL;
- ordinary campaign state.

The acceptance test proves the branch diverges while the base remains byte/semantic-state equivalent to its pre-branch state.

This is suitable for future counterfactual debugging/testing. It is **not yet a second playable timeline system**.

## Event version evolution

`territory.zone_control_set` current event version is 2.

A historical v1 shape used:

```text
organization_id
```

and omitted explicit claim dimensions.

The replay layer contains a v1 → v2 upcaster which:

- renames the semantic controller field;
- supplies the historical defaults for strength/local support/fear;
- preserves the persisted v1 event unchanged.

Acceptance appends a real v1 event to a branch and proves current code can replay it correctly.

The event is **not rewritten in storage**.

## Migration from ECON-01 / schema 58

Tested against an untouched real schema-58 ECON-01 database.

Result:

- schema becomes 59;
- migration 59 ledger row exists;
- territorial base branch persists;
- 11 current-state baseline events were generated for that database;
- replay equals existing authoritative SQL;
- hot projection equals existing authoritative SQL;
- `PRAGMA integrity_check` = `ok`;
- `PRAGMA foreign_key_check` = 0 violations.

### Important migration honesty rule

A schema-58 save did not possess a complete immutable territorial event history.

Migration 59 therefore creates explicit **baseline-import events for current active territorial state**. It does not fabricate chronology that the old schema never recorded.

All post-migration mutations append normally.

## Existing regression results on final source

Green:

- `tests/events01_territorial_event_sourcing_test.py`
- `tests/econ01_underworld_economic_interests_test.py`
- `tests/v60_underworld_rebuild_test.py`
- `tests/v60_phase2a_test.py`
- `tests/underworld_rackets_assets_test.py`
- `tests/arch01_process_registry_test.py`
- `tests/v56_test.py`
- `tests/smoke_test.py`

ARCH-01 parity remains green after schema 59.

Final scheduler benchmark in that run:

- eager SQL due-day requery: ~2.510 s
- lazy registry cache: ~2.395 s
- ~1.05× difference

This does not alter the earlier conclusion: no Mesa dependency is justified by current scheduling costs.

## Why this is native rather than a broad framework cutover

The spike deliberately uses a small SQLite-native store around Caerness's existing persistence model.

The point of EVENTS-01 is to answer whether the **semantics and operational workflow** are valuable in this engine before introducing a framework dependency or rewriting multiple owners.

The external Python Eventsourcing project remains architectural quarry; this spike does not adopt it as a dependency.

## What EVENTS-01 proves

Event sourcing is technically compatible with Caerness where it is applied to a bounded strategic owner:

```text
command/mutation
→ append immutable domain event
→ rebuildable projection
→ ordinary consumers read projection
```

It also gives Caerness useful debugging infrastructure:

- causal audit trail;
- replay;
- disposable read models;
- counterfactual branches;
- explicit event schema evolution.

## What EVENTS-01 does NOT prove

It does not prove that every Caerness table should become event-sourced.

It does not justify event-sourcing:

- every latent actor;
- every population microdelta;
- every relationship tick;
- every commodity quantity;
- every background process.

The likely fit remains selective: strategic/named domain owners with meaningful commands, histories and derived projections.

## Recommendation after the spike

**Accept the event-first pattern for new strategic owners where it provides clear replay/audit value, but do not perform a mass migration now.**

Continue the planned foundational work:

1. directed relationships;
2. low-resolution presence;
3. belief/evidence + Competence Lens;
4. decision rewrite / broader concrete underworld candidate actions;
5. cross-domain merchant/craft/count/war vertical slices.

When a new persistent strategic owner is introduced, prefer an event-first design where practical. Existing owners can migrate progressively only when touched for substantive work.

## Stop boundary

This package does **not** cut `underworld_zone_claims` / `underworld_operating_permissions` over to event-source authority.

That decision is deliberately deferred.
