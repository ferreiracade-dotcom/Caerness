# Caerness Engine v0.1–v0.15 Implementation Audit
## Audit-hardening release: v0.15.1

This audit was performed against the actual cumulative v0.15 codebase, schema, CLI, mobile runtime, and regression tests. The purpose was specifically to distinguish **implemented behavior** from features that had only been described in design prose.

## Audit standard

A feature counts as implemented only when at least one of the following is true:

1. it has authoritative runtime code and persistent state;
2. it has a callable service/API with validation and persistence where appropriate;
3. it has a player/runtime integration path where the version claim said it did;
4. it has regression coverage that exercises behavior rather than only checking that a symbol exists.

Documentation alone does not count.

The audit also distinguishes **intentional substrate/service boundaries** from missing implementation. For example, v0.8 explicitly claimed to provide a persistence substrate rather than automatic historical crystallization, so the absence of v0.9 behavior in v0.8 is not a defect.

---

# Version-by-version result

## v0.1 — Persistent living-world substrate

**Status: VERIFIED IMPLEMENTED.**

Actual runtime/persistence includes:
- shared world clock;
- locations and actors;
- Active / Strategic / Dormant simulation profiles;
- actor metrics, goals, pressures, threads, clocks, background processes;
- events, event targets, relationships, resources, knowledge, and rumours;
- world advancement in `engine/simulation.py`.

Regression evidence:
- `smoke_test.py` verifies dormant actors still produce background events and resolve clocks while off-screen.

This is executable simulation state, not prose-only design.

## v0.2 — Canon retrieval and actor decisions

**Status: VERIFIED IMPLEMENTED.**

Actual implementation includes:
- indexed canon sources/chunks;
- retrieval against the World Bible;
- actor drives and constraints;
- persisted structured decisions;
- cached decision contexts;
- canon evidence attached to decisions.

Regression evidence:
- `canon_test.py` indexes and retrieves real World Bible chunks;
- `decision_test.py` verifies persisted decisions, canon evidence, dormant decisions, wake-up behavior, and interaction creation.

## v0.3 — Inter-actor causal interaction layer

**Status: VERIFIED IMPLEMENTED.**

Actual implementation includes:
- NPC-to-NPC interactions;
- offers, contracts, negotiations, threats and conflict paths;
- counterproposals;
- agreements;
- causal links/provenance;
- severe incoming interactions waking coarse actors to higher resolution.

Regression evidence:
- `interaction_test.py` verifies acceptance, agreements, counters, conflict events, pressure effects, causal links, and dormant-origin interactions.

## v0.4 — Information ecology and anti-omniscience

**Status: VERIFIED IMPLEMENTED.**

Actual implementation includes:
- event visibility policies;
- witnesses;
- route graph;
- information channels;
- rumour propagation and distortion;
- knowledge provenance;
- player-safe scene packets;
- hidden NPC goals/drives kept out of player view.

Regression evidence:
- `information_test.py` verifies private-information non-leakage, rumour propagation, provenance, direct knowledge, hidden-state filtering, and player-agency protection.

## v0.5 — Player action loop and observer-independent world processes

**Status: VERIFIED IMPLEMENTED.**

Actual implementation includes:
- persisted player actions and turns;
- shared world time for player travel/waiting and NPC simulation;
- route-validated travel;
- actor-independent regional/world processes;
- camera attention that does not activate or alter actors;
- player-safe post-state narration envelopes.

Regression evidence:
- `action_test.py` verifies 90-day off-camera development, global-time travel, camera non-causality, explicit player interaction responses, and refusal to mutate state for ungrounded actions.

## v0.6 — Model gateway and authority separation

**Status: VERIFIED IMPLEMENTED.**

Actual implementation includes:
- persisted model requests;
- action interpretation before state mutation;
- narration after authoritative state resolution;
- ChatGPT/Claude manual bridge packets;
- major-NPC model-decision requests passing back through engine validation;
- provider swapping without changing the authority model.

Regression evidence:
- `model_gateway_test.py` verifies pending interpretation before time/state advance, narration requests after resolution, cross-provider packet export, and validated NPC decisions.

## v0.7 — Phone runtime, local model, competence follow-through, emergence, agency handoff

**Status: VERIFIED IMPLEMENTED.**

Actual implementation includes:
- localhost mobile server and PWA shell;
- Scene / Matters / World / You surfaces;
- phone runtime configuration;
- OpenAI-compatible and Ollama-native local model clients;
- model router with rules/local/local-heavy/external recommendation paths;
- persisted possessions, intentions, obligations, attention cues;
- routine competence auto-follow-through and decision forks;
- actor memories and emergent-thread evidence;
- none/open/hard agency handoffs;
- segmented local narration generation joined into one player-facing passage;
- interrupt flag;
- WAL mode and rotating backups.

Regression evidence:
- `v07_test.py` verifies story-time-only behavior, runtime defaults, automatic competence, competence forks, handoff behavior, router recommendations, memory/thread emergence, and UI serving.
- segmented local narration exists in `engine/model_gateway.py` and is called for multi-beat narration envelopes.

## v0.8 — Continuity substrate

**Status: VERIFIED IMPLEMENTED AS THE SUBSTRATE IT CLAIMED TO BE.**

Actual persistence/API includes:
- continuity cores;
- append-only historical anchors;
- public narratives and documentary records separate from objective events;
- cohorts and memberships;
- career tracks/stages/careers;
- institution profiles;
- SCENE / ACTIVE / TRACKED / STRUCTURAL / LATENT resolution metadata and transition history;
- latent entity pools.

Regression evidence:
- `v08_test.py` verifies creation, migration and persistence of these structures.

This version intentionally did **not** claim to automate historical crystallization yet.

## v0.9 — Historical crystallization

**Status: VERIFIED IMPLEMENTED.**

Actual implementation includes:
- frozen crystallization runs;
- context from latent pools, cohorts, institutions, careers, locations and prior events;
- proposal validation;
- age/chronology/reference checks;
- anti-convenience rejection of unsupported retroactive connections;
- transactional application into actor state, anchors, careers, relationships, cohort membership and resolution state;
- crystallization lineage/audit.

Regression evidence:
- `v09_test.py` verifies contextual reconstruction, anti-convenience rejection, successful application, lineage, latent-count reduction, career/cohort integration, and TRACKED promotion.

The model/human proposes biography; the engine validates and commits it. That split is intentional.

## v0.10 — Character embodiment and commitment firewall

**Status: VERIFIED IMPLEMENTED AS A SERVICE + NARRATION INTEGRATION.**

Actual implementation includes:
- persistent voice, temperament, values, habits, social and relationship style, current state and development state;
- qualitative relationship context;
- autonomous-expression assessment;
- allow/ask/block commitment firewall;
- intent/guided/exact speech mediation;
- expression and speech audit history;
- embodiment data in scene/narration packets;
- narration guardrails against autonomous major commitments.

Regression evidence:
- `v10_test.py` verifies persistence, autonomy decisions, exact-word preservation, oath blocking, history, and scene/narration integration.

Important boundary: the speech-mediation service is not a forced rewrite of every raw `speak` action before resolution. Instead the player action establishes conversational intent and the narrator receives embodiment/speech rules. This matches the service architecture but remains a possible later UX integration improvement.

## v0.11 — Domain competence and professional interpretation

**Status: VERIFIED IMPLEMENTED.**

Actual implementation includes:
- domain-specific competence profiles;
- specialties/training/experience;
- competence bands;
- professional-reading packets bounded by evidence and uncertainty;
- persisted observations, inferences, warnings, unknowns and options;
- separate named advisor judgments;
- decision-context packets;
- request-sensitive `professional_context` in scene/narration packets.

Regression evidence:
- `v11_test.py` verifies domain separation, bounded confidence, no hidden-state authority, advisor separation, and scene/narration integration.

## v0.12 — Interruption-safe time skips

**Status: VERIFIED IMPLEMENTED.**

Actual implementation includes:
- prepared time-skip runs;
- focus and delegated-authority metadata;
- bounded chunk preview;
- transaction rollback when an interruption is found inside a larger chunk;
- exact-day re-advance;
- competence auto-follow-through during compression;
- focus accumulation as experience evidence rather than free skill increases;
- time-skip historical anchors.

Regression evidence:
- `v12_test.py` verifies ordinary completion, exact-day obligation interruption, automatic routine fulfillment, no free competence-score gain, and rollback to a severe event inside a larger preview.

## v0.13 — Battle and duel resolver

**Status: VERIFIED IMPLEMENTED.**

Actual implementation includes:
- authoritative persisted battle/duel engagements;
- sides, units, battle intents, unit actions and battle rounds;
- duel combatants, intents and exchanges;
- command and martial competence integration;
- player decision boundaries by role;
- subordinate agency;
- deterministic round seeds;
- rank-sensitive battle views;
- character-relative duel views;
- hidden technical exchange;
- abstract defeat/disengagement without inventing medical detail.

Regression evidence:
- `v13_test.py` verifies side-controller and unit-commander agency boundaries, subordinate action, hidden enemy state, character-relative duel perception, and autonomous NPC duels.

## v0.14 — Multi-front battle and command uncertainty

**Initial audit result: IMPLEMENTED, BUT NOT FULLY CAUSAL IN THE AUTHORITATIVE ROUND LOOP.**

The code genuinely contained:
- battle zones;
- unit-zone assignment;
- command links;
- delayed orders;
- command profiles;
- delayed reports;
- local turning points;
- local shock;
- emergent front/phase calculations.

`v14_test.py` verified those structures operated.

However, the audit found a real architectural defect: **the v0.14 battlefield-flow pass ran after the v0.13 whole-side resolver had already calculated that round's authoritative side/unit outcome.** This meant fronts were persistent and evolving, but their current pressure did not sufficiently feed back into the same-round base result. In other words, part of the multi-front layer was more post-processing than the design language implied.

### v0.15.1 correction

- tactical/front state is now established before authoritative unit/side power is resolved;
- assigned units receive bounded leverage/pressure from their active front;
- the post-round front pass then updates the next local state, turning points, reports and phase;
- the audit regression explicitly verifies different tactical choices causally alter same-round authoritative resolution.

The audit also found that v0.14's zone/order/command functions existed only as engine APIs/tests and lacked CLI access. v0.15.1 adds CLI commands for zone creation, unit-zone assignment, command links, delayed orders and command profiles.

## v0.15 — Tactical grammar and Vein battlefield consequence

**Initial audit result: SUBSTANTIVE IMPLEMENTATION PRESENT, TWO INTEGRATION GAPS FOUND.**

The code genuinely contained:
- ten persistent doctrine weights;
- doctrine-driven tactical family selection;
- persisted player/NPC tactical choices;
- opportunity-cost changes to reserve, logistics, information, momentum, morale and cohesion;
- zone current density/stability/replenishment;
- persisted Vein assets with Stage/readiness/reserve/commitment/role/location;
- current-sensitive Vein exertion and reserve/readiness expenditure;
- minor/local/operational/strategic personal-combat consequence scaling;
- contextual strategic cascades based on Stage, front importance, command significance, replacement depth and existing fragility.

`v15_test.py` verified these mechanisms.

### Gap 1: tactical ordering

As above, the tactical layer was originally applied **after** base round resolution. Some side-state effects therefore mattered only from the following round, and zone-focused leverage could not shape the just-resolved round.

**Fixed in v0.15.1:** tactical choices and Vein leverage now enter the authoritative round before base side/unit resolution, and active front pressure contributes to unit power.

### Gap 2: duel-to-battle consequence was manual

The contextual consequence resolver existed, but a separately resolved duel did not automatically invoke it. A caller had to resolve the duel and then manually call the battlefield consequence function.

That did not fully satisfy the intended principle that a battle-embedded duel should matter through causal battlefield context.

**Fixed in v0.15.1:**
- new `duel_battle_links` persistence;
- explicit duel ↔ battle-zone ↔ Vein-asset linkage;
- linked duel outcomes automatically invoke the contextual battle consequence resolver once;
- result is persisted back to the duel link and returned in the duel exchange summary.

This preserves the rule that a duel has no strategic meaning unless it was actually linked to strategically relevant battlefield people and positions.

---

# Other audit findings and corrections

## Stale release labels

Found:
- `run.py` still described itself as v0.13;
- `mobile_server.py` still printed v0.13 in its startup text.

These did not change simulation behavior but were genuine release-integrity defects.

**Fixed in v0.15.1.**

## v0.14 CLI exposure

The multi-front API existed and tests called it directly, but player/developer CLI commands did not expose several core functions.

**Fixed in v0.15.1:**
- `battle-zone-add`;
- `battle-unit-zone`;
- `battle-command-link`;
- `battle-order`;
- `battle-command-profile`.

The commands were manually smoke-tested after addition.

---

# What remains intentionally unfinished

The audit does **not** reclassify future roadmap items as defects. The current engine still does not claim completion of:
- detailed health/injury/rehabilitation;
- full civilian economic simulation;
- households/family life as a complete runtime subsystem;
- textiles/fashion/arts/architecture/auction/provenance simulation;
- finished campaign population/bootstrap;
- deep campaign-scale military logistics;
- equipment-specific technical combat exchanges.

Those remain future layers and are accurately described as such in the current README/design documents.

---

# Verification performed for v0.15.1

The audit-hardening release was checked by:

- full cumulative regression suite from v0.1 through v0.15;
- new `audit_v01_v15_test.py`;
- schema-table existence audit across all claimed persistence layers;
- same-round tactical-causality regression;
- automatic linked-duel-to-battle consequence regression;
- CLI parser/startup smoke test;
- manual CLI smoke test for v0.14 zone/order/command commands;
- Python `compileall` across engine, CLI, and tests;
- stale release-label check.

Final result:

> **All v0.1–v0.15 claimed implemented systems are now backed by code at the scope they actually claimed. The audit found real gaps in the v0.14/v0.15 combat integration, and those gaps were corrected rather than merely documented.**

The next roadmap stage should use **v0.15.1**, not the original v0.15 package.
