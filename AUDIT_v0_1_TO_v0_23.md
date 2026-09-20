# Caerness Engine Implementation Audit — v0.1 through v0.20

**Audit standard:** a feature counts as implemented only when authoritative state exists, runtime code mutates that state, and a regression exercises the behavior. Design prose by itself does not count.

## Current status

The cumulative suite passes from the original simulation substrate through v0.20. The separate v0.15.1 implementation audit and v0.19 adversarial household edge-case regression remain in the suite.

### v0.1–v0.7 — authority/runtime foundation
Implemented: SQLite world truth, shared story time, actors and simulation tiers, clocks, events, goals/pressures, world/regional processes, player camera, interaction resolution, information/rumour separation, action interpretation, agency handoff, model gateway, local/mobile runtime, and scene/narration boundaries.

### v0.8 — continuity substrate
Implemented: continuity cores, anchors, narratives/records, cohorts/careers/institutions, broader resolution levels, latent pools, and resolution transitions.

### v0.9 — historical crystallization
Implemented: constrained context preparation, proposal validation, anti-convenience checks, transactional persistence, lineage audit, and export/import bridge.

### v0.10 — character embodiment
Implemented: persistent protagonist embodiment, speech mediation, autonomous low-stakes expression, and major-commitment firewall.

### v0.11 — competence interpretation
Implemented: domain competence, professional readings, advisor separation, and player-facing professional context.

### v0.12 — time-skip resolution
Implemented: intentions, obligations, delegated follow-through, world advancement, preview/rollback, interruptions, and historical bridge persistence.

### v0.13–v0.15.1 — combat
Implemented: battle/duel authority, fronts/zones, units, command hierarchy, delayed information, subordinate agency, tactical grammar, Vein assets/current geography, and contextual personal-combat consequences. v0.15.1 corrected the audit-discovered gap where some tactical state had been post-processing rather than authoritative input.

### v0.16–v0.18 — civilian economy and business ecology
Implemented: households/enterprises, production, markets, careers/projects, cultural objects/provenance/auctions, architecture/style diffusion, succession/credit/partnerships/professional institutions, and concrete business archetypes with differentiated commercial demand.

### v0.19.1 — household, kinship, and demography
Implemented and adversarially audited: life profiles, unions/family plans, births, guardianship, dependencies, household splitting, service terms, migrations, reciprocal kinship, exact due-day processing, age-band cohort movement, and aggregate population continuity. v0.19.1 fixed several real edge cases found after v0.19.

### v0.20 — health, aging, medicine, disability, mortality
Implemented: cultivation-sensitive longevity classes; growth/prime/late-decline health phases; persistent injuries, illnesses, chronic conditions and Vessel pathology; recovery/progression; ordinary versus Vein-specialist treatment; lasting disability and adaptation; named-character mortality; aggregate-cohort mortality; and player-facing authoritative health context.

Regression coverage verifies that cultivation can extend the prime, specialized Vein treatment outperforms ordinary care for Vessel pathology, disability persists independently of the original condition, catastrophic illness can cause authoritative death, aggregate mortality changes population without named instantiation, and health state reaches the camera packet.

## Still intentionally thin / next depth passes

The depth audit remains correct that several systems are implemented only as substrate or are absent at full long-run depth: religion and lived religious institutions; environment/seasons/travel ecology; political state transformation and successor-state logic; education/mentorship/transmission; and long-run 20/40/100+ year stress tests.

Health also intentionally does not yet generate epidemic/ecological disease or detailed battle wounds by itself. Other systems should create conditions; v0.20 resolves their bodily consequences.

## v0.21.0 — Religion & Cultural Institutions

**Implemented, tested, and adversarially audited.** Religion now persists through distinct tradition, affiliation, institution, office, observance, attendance, obligation, sacred-site, patronage, and reputation state. Cultural institutions persist separately from businesses and produce scheduled programs with real resource and prestige consequences. Religious/cultural due dates participate in authoritative world-time advancement.

The adversarial audit verifies that exact feast days are not silently generated, sign-off-sensitive canon remains flagged, affiliation is not faction alignment, repeated due processing is idempotent, deceased officeholders cannot remain active, patronage cannot mint money, completed obligations cannot farm reputation, and dissolved cultural institutions cannot continue producing events.

See `AUDIT_v0_21_EDGE_CASES.md`.

## v0.22.0 — Ecology, Seasons, Travel & Environmental Pressure

Verified implementation includes persistent environmental profiles, campaign-defined seasonal windows and temporary conditions, Current carrying capacity/load/replenishment, route graphs and route conditions, segment travel, shared-clock processing, civilian production/market integration, health exposure handoff, household-migration route integration, player-facing environment context and CLI exposure.

The adversarial audit found one important cross-version conflict: v0.19 scheduled household migration could bypass established travel geography. This was fixed before packaging v0.22. See `AUDIT_v0_22_EDGE_CASES.md`.

**Status: IMPLEMENTED, WIRED, ADVERSARIALLY AUDITED.**

## v0.23.0 — Politics, State Transformation & Macro-History

Verified implementation includes polity institutions, rulers, dynasties, succession claims, authoritative territorial control, territorial claims, interstate relations, vassal/protectorate/federation/personal-union/tributary links, political structural processes, polity dissolution/successor transfer, shared-clock political review, player-facing political context, CLI exposure, and an append-only political-history ledger.

The adversarial audit verifies non-institution rejection, dead-ruler rejection, hierarchy-cycle prevention, unique territorial control, no orphan territory on dissolution, dead-claimant exclusion, tie-to-crisis succession behavior, threshold-respecting territorial claims, successor-state transfers, and durable history.

See `AUDIT_v0_23_EDGE_CASES.md`.

**Status: IMPLEMENTED, WIRED, ADVERSARIALLY AUDITED.**
