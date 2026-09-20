# Caerness Engine v0.60.0 — BELIEF-01 Claims, Evidence & Competence Lens Acceptance

**Date:** 17 September 2026  
**Engine:** 0.60.0  
**Schema:** 62  
**Base:** REL-01 + PRES-01

## Accepted scope

BELIEF-01 separates objective world state from what a particular actor has evidence to believe.

The foundation is:

```text
objective world state / event
        ↓ may generate
claim
        ↓ supported / contradicted / contextualized by
evidence with provenance
        ↓ only if an actor actually receives/accesses it
actor evidence envelope
        ↓
actor stance + confidence + correction history
```

The Competence Lens then operates only on that actor-accessible evidence:

```text
accessible evidence
→ profession/domain-specific attention
→ noticed cues
→ professional reading depth + bounded confidence
```

Competence improves interpretation. It does not grant omniscience.

## New persistence

BELIEF-01 adds:

- `information_claims`
- `claim_evidence`
- `actor_evidence_access`
- `actor_beliefs`
- `belief_revisions`

Claims can retain an internal `authoritative_event_id` for engine provenance. Actor-facing belief envelopes deliberately omit that hidden truth link.

## Actor-relative belief

Two actors may hold different stances toward the same proposition because they possess different evidence.

Supported stances are:

- `unaware`
- `uncertain`
- `accepts`
- `rejects`

Confidence is derived from evidence available to that actor, not from hidden truth.

Contradictory later evidence can change a stance. The prior state is not silently erased: `belief_revisions` records the correction path and `correction_count` persists meaningful stance reversals.

## Legacy knowledge compatibility

The existing `knowledge` table is retained for compatibility during the transition.

New legacy-knowledge writes are mirrored into claims/evidence/beliefs, including provenance. Migration 62 also imports pre-existing knowledge rows.

A schema-60 save containing legacy knowledge was upgraded successfully: the prior fact remained available at its original learned day and became an actor-relative `accepts` belief with evidence provenance.

This is deliberately a bridge, not a claim that every old knowledge consumer has already been rewritten. The next DEC-01 decision rewrite is where strategic choice should consume the belief/evidence envelope rather than hidden truth-oriented shortcuts.

## Competence Lens

`build_competence_lens(...)`:

- sees only evidence present in `actor_evidence_access` for that actor;
- never reads hidden evidence into the actor packet;
- applies domain competence to attention/noticing;
- passes noticed evidence to the existing professional-reading layer;
- preserves observation/inference separation and uncertainty guardrails;
- never exposes `authoritative_event_id` through the actor-safe belief packet.

High competence therefore means a character is more likely to notice material cues and interpret them deeply, not that they magically learn facts they never received.

## Player-facing integration

Scene packets now include an actor-safe `beliefs` envelope alongside known events and rumours. Narrator rules explicitly treat the envelope as actor-relative and prohibit equating confidence with objective truth.

## Migration: schema 61 → 62

Migration 62:

1. creates the claim/evidence/access/belief/revision owners;
2. imports existing legacy knowledge without changing the historical learned day;
3. records `belief_model_version=1`;
4. records `competence_lens_version=1`.

No hidden event truth is copied into actor-visible packets merely because a claim has an internal truth/provenance link.

## Acceptance tests

New:

- `tests/belief01_claims_competence_lens_test.py`

It proves:

1. actors can reach different beliefs about one claim from different evidence access;
2. contradictory evidence can cause a recorded correction rather than silent overwrite;
3. actor-safe belief envelopes expose acquired evidence but not hidden truth links;
4. inaccessible evidence cannot enter the Competence Lens;
5. raising competence over the same accessible evidence increases noticed evidence/interpretive depth without changing access;
6. legacy knowledge writes mirror into the new model;
7. database integrity and foreign keys remain clean.

## Result

BELIEF-01 + Competence Lens is accepted as the epistemic foundation.

The three foundational architecture items are now complete in the cumulative branch:

1. REL-01 — directed relationships;
2. PRES-01 — low-resolution presence;
3. BELIEF-01 — claims/evidence/belief + Competence Lens.

The next bounded implementation task is **DEC-01 — information-bounded decision rewrite**.
