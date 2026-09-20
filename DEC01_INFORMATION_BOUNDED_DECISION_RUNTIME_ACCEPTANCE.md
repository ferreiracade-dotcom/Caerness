# Caerness v0.60.0 — DEC-01 Information-Bounded Decision Runtime Acceptance

**Date:** 17 September 2026  
**Status:** ACCEPTED WORKING CHECKPOINT  
**Schema:** 63  
**Predecessor:** BELIEF-01 / schema 62

## Purpose

DEC-01 replaces the default centralized generic NPC decision path with an information-bounded candidate runtime:

```text
actor-accessible information / belief envelope
→ domain behavior providers
→ concrete candidate actions
→ feasibility
→ utility / proclivity
→ deterministic weighted selection
→ domain-owned execution
```

The player remains outside autonomous NPC strategic selection.

## Accepted architecture

### Actor-safe decision envelope

`engine.decisions.build_actor_context()` now builds decision context from the actor's own persisted state:

- goals and pressures;
- resources and constraints;
- directed relationships;
- memories;
- actor-relative beliefs/evidence;
- relevant presence summary;
- derived drives/motives.

The World Bible/canon retrieval channel is not personal knowledge. `canon=[]` is deliberate in autonomous decision envelopes. External claims must enter through evidence/belief pathways before they can affect decisions.

### Candidate runtime

New `engine/decision_runtime.py` owns candidate generation and selection, not domain mutation.

A candidate records:

- provider;
- concrete action kind;
- concrete target where applicable;
- information basis;
- claim/evidence IDs where applicable;
- payload;
- utility;
- cost/risk metadata;
- execution owner/type.

The runtime always supplies a legal `hold_position` option. It de-duplicates overlapping providers and chooses among plausible actions with tier-specific softmax-like weighting. RNG remains deterministic by world seed, actor and day.

### Decision audit

Schema 63 adds:

- `decision_evaluations`;
- `decision_candidate_audit`.

Each evaluation records the complete candidate set, utilities, plausible band, selection probabilities, random draw, selected candidate and a summary of the actor information envelope. This makes the answer to “why did this actor do that?” inspectable without exposing hidden truth to the actor.

### Model/manual gateway

The model gateway no longer accepts arbitrary generic NPC action names. It receives the concrete engine-generated candidate list and may select only one currently feasible candidate. The selection is written through the same decision audit layer.

This preserves model-assisted expression/choice without letting a model invent authority, hidden facts or mutations.

## Initial domain vertical slice — underworld

New `engine/underworld_decisions.py` provides concrete strategic options from persisted underworld objects, including:

- warn, negotiate with, or retaliate against the organization responsible for a specific protection-account poach;
- seek a truce with a specific hostile organization;
- discipline a specific weak crew;
- promote a specific member where an organizational vacancy exists;
- delegate a specific racket to a specific crew;
- expand protection to a specific eligible enterprise in controlled territory;
- invest explicit treasury funds in a specific racket;
- investigate a specific uncertain underworld claim already present in the actor's evidence envelope.

Execution remains under the underworld domain owner.

## Underworld strategic cutover

`autonomous_organization_turn()` no longer contains a second hard-coded strategic chooser (`attack/racket/front/recruit/patrol/hold`). It now performs maintenance/accounting work only:

- leadership/staffing upkeep;
- income;
- membership turnover/reconciliation;
- leader lifestyle;
- enforcement/heat maintenance.

Strategic action belongs to the organization's leader through DEC-01. Active underworld leaders are kept on STRATEGIC review cadence (maximum 30 days) so removing the old monthly option bag does not freeze organizational agency.

## Social interaction correction found during regression

The first relationship provider was too narrow: a familiar counterpart with adverse stance/distrust and a real pressure could produce no social candidate unless explicit resentment was already high.

DEC-01 now treats persisted negative stance/trust as sufficient actor-known grounds for a specific negotiation/demand where a real goal or pressure exists. Familiar non-hostile ties can produce specific request/negotiation options. This restores dormant off-screen causal interactions without resurrecting the generic `work_relationship` action.

Arrangeable requests/negotiations do not falsely assert exact co-presence; PRES-01 still governs genuinely direct/spontaneous encounter.

## Removed from the default decision vocabulary

The DEC-01 default runtime does not generate:

- `advance_goal`;
- `force_goal`;
- `address_pressure`;
- `work_relationship`.

Legacy application branches may remain temporarily for compatibility with old persisted/request data, but they are not default autonomous candidates.

## Migration

Schema 62 → 63:

- creates the two decision-audit tables;
- records `decision_runtime_version=1`;
- records `decision_information_rule=actor_accessible_only`;
- promotes active underworld bosses with decision authority to STRATEGIC cadence where needed.

Migration does **not** fabricate historical candidate evaluations or retroactive decisions.

## Acceptance tests

Clean-package pass:

- `dec01_information_bounded_decision_runtime_test.py` — PASS
- `decision_test.py` — PASS
- `model_gateway_test.py` — PASS
- `interaction_test.py` — PASS
- `rel01_directed_relationships_test.py` — PASS
- `pres01_low_resolution_presence_test.py` — PASS
- `belief01_claims_competence_lens_test.py` — PASS
- `information_test.py` — PASS
- `events01_territorial_event_sourcing_test.py` — PASS
- `econ01_underworld_economic_interests_test.py` — PASS
- `underworld_rackets_assets_test.py` — PASS
- `v60_phase2a_test.py` — PASS
- `v60_underworld_rebuild_test.py` — PASS
- `action_test.py` — PASS
- `smoke_test.py` — PASS
- `v56_test.py` — PASS
- Python compileall for `engine/` — PASS
- SQLite integrity check — `ok`
- SQLite foreign-key check — clean

`arch01_process_registry_test.py` also passes separately after the DEC-01 rewrite.

Older historical regression scripts still contain hard-coded engine-version allowlists ending at `0.59.0`; those scripts can reject `0.60.0` before exercising behavior. This is a stale harness fence, not a DEC-01 behavior failure, and was not mass-edited as part of this slice.

## Stop boundary

DEC-01 does **not** attempt to model every profession or strategic domain deeply. The runtime/provider architecture is accepted; the underworld proves the rich-provider pattern. Subsequent vertical slices should add domain providers only as their real economic/material objects are implemented.

The next implementation slice is the **merchant-house / market vertical slice**.
