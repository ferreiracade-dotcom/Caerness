# Caerness — Player-First Phase 1 Audit

**Date:** 2026-10-12  
**Audit type:** static repository/code/design audit, not a completed runtime regression or playtest  
**Reviewed revision:** `b1185903d6a23cbe1ba49bb5755d1a42a762582a` (`master` at inspection)  
**Decision requested:** reposition near-term work toward a complete character-life game loop while protecting already useful simulation foundations.

## Executive verdict

**The simulation is not conceptually excessive, but development investment is misallocated relative to the desired game.** The player wants a compelling, open-ended, text/voice-playable life in a persistent world, with an optional independent third-person Unreal observation client later. The simulation is *supporting infrastructure*, not the product to maximise.

A deep economy, politics, warfare, institutions, families, culture and population model can be justified **when it produces causal opportunities, constraints, autonomy, continuity and consequences that the player experiences**. More detailed mechanics are not automatically an improvement. The strongest immediate bottleneck is the player-action/conversation/presentation path—not the absence of another simulation domain.

**Do not delete or simplify existing simulation code as a speculative cleanup.** Establish user-facing functionality, measure performance and system contributions, then simplify only where tests demonstrate retained causality and continuity.

## Scope and evidence

Reviewed: `README.md`; `AGENTS.md`; `DESIGN.md`; `POST_V07_ARCHITECTURE.md`; `engine/actions.py`; `engine/turns.py`; `engine/model_gateway.py`; `engine/mobile_runtime.py`; `engine/mobile_server.py`; `engine/player.py`; `engine/interactions.py`; `engine/competence.py`; `engine/timeskip.py`; `engine/continuity.py`; `engine/crystallization.py`; `engine/resolution_controller.py`; `engine/conflict.py`; `engine/war.py`; `engine/domain_actions.py`; `engine/opportunity.py`; `engine/organization_needs.py`; `engine/civilian.py`; `CIVILIAN_SIMULATION.md`; `mobile/index.html`; `tests/model_gateway_test.py`; `tests/v07_test.py`; `tests/interaction_test.py`; the POP-01 and PERF-01 specs; and published benchmark/decade acceptance artifacts.

Evidence limitations: the GitHub connector allows source inspection but does not execute this project's Python code. No fresh regression, benchmark, gameplay session, model-quality test, or direct mobile-device test was run in this audit. Treat acceptance reports and benchmark files as *reported prior results*. The implementing agent must validate them independently on copies of the current opening database.

### Reported baseline

- Runtime: Python/SQLite engine v0.60.0, packaged opening Schema 108 at story day 0; the `AGENTS.md` handoff dated 2026-10-09 reports 125/125 suite pass, not independently reproduced here.
- Code surface: approximately 100 Python engine modules; `engine/schema.sql` around 272 KB; source tree has extensive domain systems.
- `benchmarks/results/pc_engine.json` reports an opening 90-day skip of 13.037 s; `pc_year3_engine.json` reports a year-3 90-day skip of 33.535 s; `AGENTS.md` reports current late-year work around 33–37 s per season and around 20 MB/year database growth (target <=20 s and <=15 MB/year on PC). `pc_late2790_perf1_engine.json` is an *older* intermediate performance snapshot (102.854 s/90 days) and must not be mistaken for latest.
- `acceptance_artifacts/TENYEAR02_CORRECTED_ACCEPTANCE_2026-09-21.md` is a **Schema 104, non-canon** unattended decade: broad world activity and restart determinism passed, but natural war=0, law=0, patronage=0, and opportunity searches=0; many merchant firm candidates never crystallized. Later Schema 108 addressed routes and conflict pressure; its fresh integrated one-/ten-year gate is still unverified according to the handoff.
- `AGENTS.md` says POP-01 population tiers are designed but **not implemented**; current background profile progression is materially shallower than the intended living populace.

## Findings, ranked

### P0 — free-form player agency is not yet a general gameplay capability

`engine/model_gateway.py`'s action interpretation contract permits `observe|wait|travel|speak|investigate|respond|attempt`. In `engine/actions.py`, `attempt` ends as `needs_interpretation` and does not mutate authoritative state. The model gateway test explicitly demonstrates converting a complicated bargain to an *observation* when it cannot be encoded. The rich domain functions exist elsewhere but are not generally available to free-form player intentions.

**Player consequence:** commissioning a project, elevating a trusted merchant, founding a division, hiring fighters or proposing an unconventional contract cannot reliably proceed from ordinary dialogue, even when the underlying domain model can represent it.

**Action:** build an *authoritative player-intent/action bridge* that maps unconstrained natural-language intent to existing validated domain operations, supports multi-step plans and genuine inability/refusal, and can add an extensible action where appropriate. Never permit an LLM to write directly to SQLite or assert success in prose.

### P0 — conversation is currently too transactional for the desired game

`engine/actions.py` creates a `conversation` interaction and immediately calls `resolve_interaction`. In `engine/interactions.py` the general social resolver scores acceptance/counter/refusal, and a successful conversation can be summarised as the recipient having engaged with the approach. This is useful for causal social bookkeeping, **not evidence of persistent, open-ended, multi-turn character dialogue**. Current narration is constrained to already resolved packets, and the rules fallback in `engine/turns.py` openly identifies itself as an offline testing narrator, not literary gameplay.

**Player consequence:** the nuanced, extended family reunion or bonfire negotiation is not yet demonstrated by the running experience, however rich the character schema.

**Action:** persistent conversation scene/session; identity, beliefs, relationship and memory context; reciprocal NPC initiative; controlled emotional expression; natural pacing; a ledger of consequential statements, commitments and information; a reliable mechanism for ending/resuming dialogue. Routine descriptive dialogue need not create a high-stakes database mutation on every utterance.

### P0 — enjoyable prose and selective perception have not been playtested

The prompt rules in `engine/turns.py` and `engine/player.py` are promising: attention should be centred on player perception without giving camera privilege; no forced `What do you do?`; no narrator-owned world changes; scene spans can be long; player wording is intent unless marked exact. But these rules are not proof of the desired lived-in, reactive prose. The phone interface already has Scene/Matters/World/Ledger/You views and a model referral path, but its *quality as a game* is unevaluated.

**Action:** playtest human-quality narrative scenes using a capable model, with specific tests for recurring places, social recognition, autonomous ordinary life, extended dialogue, long skips and actual refusals. Keep phone text/voice as a complete play route. Do not make the quality of all gameplay contingent on a local 3–4B model's ability to do high-complexity scenes.

### P1 — cross-domain world causality is valuable; activation is uneven

Politics/war, institutions, economy, logistics, cultivation, health, family, information and underworld systems are genuine assets because they produce wars, contracts, risks, careers, relationships, scarcity and historical change that the player did not request. But the historical quiet-domain reports show that *having the systems* is not enough: unconnected routes, issue-key mismatches and unmet institutional capacity previously prevented plausible activity.

**Action:** scenario-specific causality tests: does political/economic pressure generate feasible conflict; does conflict lead to believable mercenary demand; can a suitable company discover/negotiate a contract; can settlement work advance via materials/labour/delegation; can background talent become known and rise? Measure the chains, not the count of domain modules or events. A quiet decade is not automatically a bug; a systematically disconnected causal pathway is.

### P1 — current simulation speed may undermine time-compression gameplay

A 90-day skip measured around 33–37 s on PC from a year-3 save cannot be assumed satisfactory on a phone, especially with a language model resident. PERF-01 identifies information/rumour duplication and propagation as a significant historical cost; the performance work is incomplete. Caerness's particular advantage is skipping months/years while retaining the lived experience.

**Action:** finish narrow, evidence-backed PERF-01 optimisations, independently benchmark days/weeks/seasons/years and scene turns on a current database, then revisit budget based on actual phone usage. Never introduce additional large background fidelity before measuring impact.

### P1 — background agency needs follow-through, not maximum resolution

`docs/superpowers/specs/2026-09-26-population-tiers-design.md` makes an important distinction: distinction, significance and player relevance determine how much detail is held, not whose outcomes count. Weighted background people continue advancing, with individuals promoted without changing their fate. This directly serves the user's talent-discovery/loyalty/rising-NPC stories, but it remains an unimplemented design.

**Action:** protect this principle. After the narrative slice, prioritise the smallest verified POP-01 tranche necessary to show an unknown fighter, merchant or officer becoming exceptional without being invented for the player. Do not blindly implement every currently proposed population domain before gameplay testing.

### P2 — some simulation precision is not presently justified

Potential candidates for *lower fidelity or slower cadence after measurement*, not immediate removal:
- high-frequency propagation and storage of minor rumours in remote regions;
- very fine-grained trade/production detail with no effect on price, scarcity, hiring, conflict or a live project;
- exhaustive per-person routines where a place/occupation/cohort model would preserve the same visible outcomes;
- background activity that generates large records without altering opportunities, chronology or player-relevant consequences;
- specialised simulation passes whose costs are high but whose outcome feeds no functioning player or NPC decision loop.

These are hypotheses. Each proposed simplification must name its downstream consumers, run seed-paired comparative scenarios, measure time/save size and prove continued causality and continuity before code is changed.

## Preserve / simplify / defer decision

| System | Recommendation | Reason |
|---|---|---|
| World state, event/provenance ledger, continuity, canon constraints, time, movement | **Preserve** | Directly prevents invented/fogotten history and impossible actions |
| Family, relationships, information/reputation, knowledge boundaries | **Preserve; improve presentation** | Enables reunions, recognition, reputational differences and genuine responses |
| Politics, war origins, institutional agency, economy, logistics | **Preserve; test connectivity** | Creates contracts, campaigns, scarcity, employment and believable obstacles |
| Character progression, cultivation, ability/competence, teaching | **Preserve; make playable** | Personal martial excellence and discovering/raising talent |
| Projects, settlements, commerce, delegation | **Preserve; remove micromanagement in UI** | Visible change and command without procurement busywork |
| Background-to-notable emergence | **Prioritise a targeted slice after gameplay core** | Prevents the world being a fixed named cast |
| Fine-grained low-salience information/production and repeated historical records | **Profile and possibly coarsen** | Runtime/storage risk; benefit must be justified by downstream decisions |
| Remaining broad WORLDHIST and full POP-01 expansion | **Stage, do not implement all first** | Gameplay cannot wait for complete civilisation simulation |
| Standalone Unreal observation client | **Specify interface now; prototype after narrative loop** | Strong visual direction, but not prerequisite for phone play |

## Constraints and project changes to reconcile

1. `AGENTS.md` currently says **phone-only target**. The owner's updated direction is **phone-first narrative plus optional PC third-person observation**, ideally using independent Unreal technology and licensed reusable assets, developed by coding agents. Do not silently leave the older requirement authoritative; propose the explicit update and obtain owner acceptance.
2. The user writes **no code**. Development agents must own source, tests, build scripts, Unreal editor automation, debugging, documentation and playable packaging. Human assistance may still be required for credentials, licences or installing local tooling.
3. Player has broad freedom of *intent*, not guaranteed outcomes. NPC autonomy, failure, scarcity, time and information limits are non-negotiable.
4. No proprietary decompiled game code or redistributed assets without rights. Evaluate legitimate starter projects and asset licences.
5. Preserve existing day-0 canonical state; perform all runs on copies; use a branch, review, acceptance tests and rollback plan.

## Uncertainties and go/no-go tests

The static audit cannot establish current runtime speed, actual model performance, visual feasibility, or whether natural Schema 108 wars/mercenary contracts emerge at acceptable rates. An implementing agent must produce reproducible evidence.

**Go/no-go for a playable narrative slice:** a player can enter an established scene, talk for many turns without forced time advancement, promote or hire a person, delegate construction, seek and respond to a contract opportunity, skip time, return and discover consistent changes; NPCs may disagree/refuse; scarce resources matter; no facts are inserted to satisfy the narrative. Full suite passes on copies.

**Go/no-go for simulation simplification:** a proposed reduction demonstrates measurable performance/storage improvement while maintaining invariant histories, continuity, core opportunity paths and distributional realism over several seeded runs.

## Recommended next sequence

1. Preflight: reproduce current test suite and fresh baseline without touching opening DB.
2. Build a high-quality player-facing vertical slice by exposing existing mechanics through natural-language action interpretation and persistent dialogue scenes.
3. Add story-quality acceptance tests, with human evaluation, not just code unit tests.
4. Finish narrow PERF-01 and benchmark time skips on phone-class targets.
5. Implement targeted background-emergence needs; decide broader POP-01 based on evidence.
6. Define a read-only scene-state contract and event-command boundary for independent Unreal visual client; prototype one location only after narrative core works.

**Decision:** simulation stays as causal support; narrative experience is the product. No feature is justified solely by a more detailed simulation statistic.