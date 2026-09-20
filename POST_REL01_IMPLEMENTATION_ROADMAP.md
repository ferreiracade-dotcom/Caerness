# Caerness — Post-REL-01 Implementation Roadmap
**Date:** 17 September 2026  
**Status:** Current continuation sequence after REL-01 directed relationships.

## Completed current-chain milestones

1. Phase 2A — territorial/shared-geography foundations.
2. ARCH-01 — ProcessRegistry spike; pattern accepted, no Mesa dependency/cutover.
3. Rackets/Assets — behavioral rackets and front enforcement.
4. ECON-01 — economic interests/flows, protection-as-racket, front ownership correction.
5. EVENTS-01 — bounded territorial event-sourcing spike; selective event-first conclusion.
6. REL-01 — directional social/evaluative relationships; structural ties remain separate.

## Immediate next task — PRES-01 low-resolution presence

Create one shared presence substrate instead of every subsystem inventing its own answer to “where can this person plausibly be encountered?”

Resolution ladder:

```text
aggregate
→ habitual / dormant presence profile
→ tracked travel
→ exact scene presence
```

Rules:
- exact tracked travel overrides habitual presence;
- habitual presence is probabilistic/access-oriented, not teleportation;
- actor presence must respect travel geography, occupation, household and institutional obligations;
- player/focus actors receive no presence privilege;
- no subsystem may treat `current_location_id` alone as proof of exact co-presence at city scale.

Shared consumers should eventually include:
- social contact;
- rumor/information exposure;
- recruitment;
- market encounters;
- surveillance;
- witness generation;
- ordinary meetings;
- crime opportunity;
- teaching/institutional contact.

### Minimal PRES-01 persistence

Prefer a reusable owner such as:

```text
actor_presence_profiles
    actor_id
    home/base anchors
    habitual locations / location classes
    cadence / probability / time-window metadata
    occupation/institution basis
    confidence/source
    effective dates

tracked_movements / existing travel owner
    remains authoritative when explicit

scene/exact presence
    highest-resolution runtime fact
```

Do not duplicate existing route/travel truth.

### Acceptance

Prove at least:
1. two people assigned to the same large city are not automatically co-present;
2. a habitual workplace materially raises encounter probability there;
3. tracked travel overrides a stale habitual profile;
4. exact scene presence overrides both;
5. social contact/rumor can consume the same presence API;
6. dormant NPCs use the same rules as followed actors;
7. old saves migrate without inventing exact historical movements.

Stop/test/package before beliefs.

## Then — BELIEF-01 + Competence Lens

Move actor knowledge away from direct hidden truth.

```text
claim
actor stance/belief
confidence
evidence/source
received time
supports / contradicts
correction history
```

Then:

```text
accessible evidence
→ profession-specific attention
→ noticed cues
→ uncertain inference
→ warnings / affordances
→ actor/narrative packet
```

Competence must improve interpretation, not grant omniscience.

## Then — DEC-01 decision rewrite

Use:

```text
actor information/belief envelope
→ domain behavior providers
→ concrete candidate actions
→ feasibility
→ utility/proclivity
→ weighted selection
→ domain-owned execution
```

At this point expand the underworld candidate vocabulary using ECON-01 objects and REL-01 directed loyalty/resentment/fear/trust:
- protection-account poaching;
- permission/franchise decisions;
- retaliation for specific grievances;
- truce/peace;
- discipline;
- promotion/delegation;
- personal/crew rackets;
- legitimate investment;
- differentiated tribute/share terms.

PsychSim-style opponent models remain shallow and strategic.

## Later semantic/domain work

- full generic personal estates;
- merchant/market vertical slice;
- craft/production;
- backwater count/state capacity;
- warfare;
- agriculture/health/law;
- culture/religion/publishing through shared primitives;
- background population benchmark.

## Integrated-run gate

Before the next ten-year run:
- every major World Bible domain has an active owner/process or explicit no-change reason;
- one-year unattended simulation shows cross-domain movement;
- player-facing controls remain human-scale rather than exposing simulation coefficients.

## Persistent rule

> Caerness is one causal world. Rich simulation is engine-facing; the player acts as a person inside it.
