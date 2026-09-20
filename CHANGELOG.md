# v0.60.0 working — schema 71–74 scale/trade/population + ARCH-02/PRESBACK-01

- Added SCALE-01 operational population/settlement scale authority and TRADE-01 causal aggregate production/consumption/reserve/inter-regional flow beneath named MERCHANT-01 commerce.
- Added POPBACK-01 bounded NumPy stable-identity reservoirs over 68 disjoint population sources; aggregate headcount remains authoritative and sampled identities are not double-counted.
- Added POPLIFE-01 schema 74 live age cohorts, annual births/deaths/aging and explicit conserved source-to-source population movement; TRADE now consumes live population.
- Cut production `advance_connection()` over to ARCH-02 SQL-authoritative eager ProcessRegistry scheduling; lazy due caches and caller-boundary terminal catch-up are rejected.
- Added permanent scheduler chunk-invariance regression and full-year 30-table hash audit: `advance(365)` is row-identical to `30×12+5` after volatile timestamps are excluded.
- Adapted Neighborly-style reverse location presence lookup and reusable location/day probability snapshots without adopting an ECS/framework authority.
- Repaired repeated presence seeding, institution-triggered reseeding, side-effecting resolution lookahead and chronology/life-stage transition inconsistencies exposed by the scheduler cutover.
- Current schema is 74; current engine remains v0.60.0.
- Next task: fresh TENYEAR-01 from day 0 with annual state/performance checkpoints; revisit external frameworks only when the decade demonstrates a real bottleneck.

# v0.60.0 working — INTEGRATION-01 health/agriculture/law integration

- Advanced schema to 68 with finite health-care sites/providers/requests, physical fields/harvests/disruptions, and general jurisdiction/rule/office/case/judgment/enforcement owners.
- Kept health condition progression independent from care availability; severe conditions can seek real local care, but treatment begins only when a qualified provider and site capacity actually exist.
- Added bounded care queues where delayed/unavailable treatment materially changes condition course.
- Added agriculture fields that consume existing ecology/weather and produce actual `commercial_stock`; harvest deviation changes existing market supply/price and therefore GROWTH food stress.
- WAR now damages real tracked fields through agriculture disruptions rather than a WAR-only farm meter.
- Added general jurisdiction resolution (local/charter > polity > default), evidence thresholds, capacity/corruption-sensitive procedure, judgments and real cash/debt enforcement.
- Judgment information enters BELIEF only for actors who actually receive legal notice.
- Integrated agriculture and law into ordinary scheduler/ARCH parity.
- Migration from schema 67 creates no fabricated medical, agricultural or legal history.
- Next task: COVERAGE-01 World Bible → engine coverage gate and promotion/down-resolution proof before the integrated one-year run.

# v0.60.0 working — WAR-01 campaign/battle/world-consequence vertical slice

- Added schema 67 persistent campaign operations, routed campaign forces, tracked named force members, physical force supplies and supply ledgers.
- Force movement now uses the ordinary route graph and force due-times; a slower operation review cannot stall a completed route leg.
- Physical military supply withdraws real `commercial_stock`, consumes over elapsed campaign time and can only resupply through a currently traversable route.
- Preserved the earlier aggregate military-logistics layer for compatibility while preventing double consumption when a WAR-01 physical force is reviewed on the same day.
- Linked campaign operations to the existing battle resolver instead of creating a parallel combat engine.
- Added persistent aggregate killed/wounded/captured/deserted force losses while keeping named consequences limited to already-crystallized force members.
- Named battle wounds use the existing health `injury` ontology with battle provenance; named deaths use ordinary actor/household death and trigger existing political succession review.
- Added battle-to-world projection for real building condition, route damage, commercial stock loss, market pressure and household displacement through the existing migration/travel owner.
- Added idempotent battle aftermath so repeated processing cannot re-kill actors or re-damage the world.
- Added delayed official and eyewitness battle reports that become recipient-specific BELIEF claims/evidence only on actual receipt.
- Added information-bounded WAR DEC candidates for specific force resupply/withdrawal using own force records and delivered reports, never hidden enemy state.
- Expanded coverage reporting for the campaign/world consequence layer.
- Migration from schema 66 creates no fabricated war history.
- Next slice: INTEGRATION-01 health + agriculture/weather + law/procedure integration.

# v0.60.0 working — CRAFT-01 production dependency closure

- Advanced schema to 65 with tracked recipes, substitution groups, facility requirements, enterprise facilities, site workers, production orders, input-consumption ledger, output lots and order events.
- Bound tracked production to MERCHANT-01 `commercial_stock`; no parallel craft inventory was introduced.
- Tracked sites are firewalled from the legacy aggregate `material_access` output resolver, while ordinary aggregate sites continue to work unchanged.
- Added explicit closure checks for missing material source/path and missing required facilities.
- Production chooses only technically permitted substitutions and uses enterprise-accessible price observations; a chosen-but-missing material becomes a real procurement shortage rather than a silent fallback.
- Added craft DEC-01 procurement candidates tied to a specific blocked order and a specific observed offer; execution remains merchant-domain-owned.
- Added actual worker/craft competence where tracked, with coarse site labor retained as the fallback at aggregate resolution.
- Accepted end-to-end chain: ore + charcoal + furnace -> steel intermediate -> contract/shipment -> steel + charcoal + forge -> finished tools -> contract/shipment -> revenue.
- Integrated craft cadence into the shared scheduler and ARCH-01 parity harness.
- Next slice: GROWTH-01 regional growth/state-capacity vertical slice.

# v0.60.0 working — MERCHANT-01 commercial vertical slice

- Added schema 64 commercial connective layer: enterprise factors/authority, received market observations, explicitly observed trade offers, buyer/seller contracts, cash transfers, and production input substitution options.
- Extended commercial shipments so owned stock can move physically between seller and buyer enterprises with contract/carrier linkage.
- Cash-on-delivery settlement conserves enterprise cash; seller-credit settlement creates a real credit agreement and borrower debt.
- Added merchant DEC-01 provider using only enterprise-accessible offers/reports; hidden offers do not become candidates.
- Commerce competence improves interpretation and action thresholds without revealing hidden market truth.
- Added steel-supply/copper-demand acceptance experiment through real market price and technically valid input substitution.
- Integrated merchant cadence into the production scheduler and ARCH-01 parity registry.
- Next slice: CRAFT-01 production dependency closure and workshop execution.

# v0.60.0 working — DEC-01 information-bounded decisions

- Replaced the default generic NPC decision vocabulary with actor-information envelopes, domain behavior providers, concrete candidates, feasibility/utility evaluation, deterministic weighted selection, and domain-owned execution.
- Added candidate/evaluation audit persistence and bounded model/manual selection.
- Cut underworld strategy over to the shared DEC-01 architecture.

# v0.60.0 working — REL-01 + PRES-01 + BELIEF-01 foundations

- REL-01: relationship evaluations are directional A→B edges; structural kinship/union/teaching/office/contract relations remain separate.
- PRES-01: added shared low-resolution presence profiles/habits with exact-scene > tracked-travel > habitual/aggregate precedence. Broad settlement assignment is no longer proof of exact co-presence for migrated scene, rumour, social-contact, arrival-competence and direct-conversation paths.
- BELIEF-01: added claims, provenance-bearing evidence, actor evidence access, actor-relative stance/confidence, and correction history while retaining the legacy knowledge table as a compatibility projection.
- Competence Lens now filters interpretation through evidence the actor actually possesses; skill improves attention and reading depth but never grants hidden facts.
- Schema advances to 62 with safe migrations from REL-01 schema 60. Presence migration derives only present-day anchors; it does not invent historical movement. Legacy knowledge is imported into claims/evidence/beliefs.
- Added PRES-01 and BELIEF-01 acceptance suites and re-ran information/privacy, REL-01, event sourcing, ECON-01, v0.60 underworld, ProcessRegistry, action/model/interaction/decision, and key household/domain-action regressions.

# v0.59.0 — Career, Responsibility, Reach & Underworld Scale

- Split professional development into durable standing, branching responsibilities/appointments, and reach/opportunity scale; promotion is no longer a universal ladder.
- Added role-sensitive career/reach coupling for martial institutions, retainers, Long Road work, Witness service and merchants without making advancement automatic.
- Removed independent-underworld personal promotion ladders; Cale begins as the boss of his already-existing gang.
- Added parallel underworld organization forms (`gang`, `mafia_family`, `criminal_dynasty`, `syndicate`, `criminal_enterprise`, `network`, `crew`, `other`) with no gang→Mafia-family power ladder.
- Added stock-and-flow gang membership with core, active and peripheral participation plus recruitment, desistance, defection, custody, death/incapacitation, relocation and internal movement.
- Removed hidden gang-size anchors: no synthetic fringe, no `member_count < 18` growth gate, and no eight-person Cale opening.
- Added operational-footprint opening scale resolution. Cale's ward-level front/rackets/enforcement footprint resolves into manpower in the tens with seed variation; explicit canon headcounts still override.
- Re-ran Cale's ten-year branch and added operational-scale calibration diagnostics; final v0.59/v37/v45/v44/v42/v35/v33/v32/v29/v20 regressions pass.
- Engine version is 0.59.0; schema is 50.

# v0.58.0 — Protagonist-Agnostic Experience / Biography Acceptance

- Removed runtime Stage-census feedback entirely; World Bible Stage counts are ecological baselines rather than quotas.
- Retained causal summit permeability and updated the old v0.46 summit regression so a quiet decade is legal while fully ready Fifths with genuine summit problems can still attain Sixth.
- Generalized martial experience into the shared NPC path: tournament bouts and accepted challenges create Stage-bound, single-use Realization anchors for both participants.
- Lethal accepted challenges now mark the loser deceased when the duel resolves.
- Added protagonist-agnostic role experiences for Long Road work, martial institutions, retainers, Witness service, merchants and underworld operators.
- DORMANT routine remains causally simulated but compressed; STRATEGIC/TRACKED promotion increases event resolution detail rather than probability.
- Underworld collection fights now record concrete outcomes; ordered hits persist and later resolve as success, failed survival, or exposed failure.
- Institutional and retainer duties now resolve into specific patrol/watch/training/escort/horse-work beats rather than generic assignment labels.
- Expanded six-person decade diagnostics to persist tournament bouts and combat engagements.
- Re-ran all six 10-year biography branches and completed the protagonist-privilege population audit.
- Added `Caerness_v0_58_FINAL_DECADE_BIOGRAPHY_ACCEPTANCE.md` and `Caerness_v0_58_0_ACCEPTED_HANDOFF.md`.
- Engine version is now 0.58.0; schema remains 48.

# v0.56.0 — Vessel-Dominant Lower Ladder / Realization-Wall Mastery

- Reworked cultivation transitions to implement the World Bible's explicit Vessel→Realization progression.
- First→Temper and Temper→Third are now Vessel-maturation transitions rather than rare-Realization lotteries.
- Third→Breach is the first major Realization wall; Breach→Fifth and Fifth→Sixth remain increasingly selective Realization transitions.
- Added Stage-bound Realization anchors so lower-Stage insights cannot be banked indefinitely into later mastery.
- Added a nonlinear whole-Vessel current-ecology factor to Temper→Third, reproducing the Hearth/outer social offset through conditions rather than regional Stage caps.
- Preserved inverse age-at-attainment semantics: age and elapsed time never create catch-up advancement.
- Recalibrated opening focus priors: mature Churn professionals commonly sit around Third; mature outer professionals commonly around Temper, with outliers requiring biography rather than hard prohibition.
- Added v0.56 regression and focus-cultivation diagnostics; multi-seed validation preserves common Churn Thirds, durable outer Tempers, rare Breach progression and variable summit turnover.
- Engine version is now 0.56.0; schema remains 48.

# v0.54.0 — Inverse Stage-Attainment Calibration (working calibration branch)

- Added persistent `cultivation_stage_attainments`: Stage attainment chronology is distinct from current age/current Stage.
- Opening imports backfill attained-Stage facts with unknown chronology rather than inventing breakthrough dates from current age.
- Runtime breakthroughs record exact attained day and age-at-attainment when birth chronology is known.
- Removed current-age influence from opening within-Stage depth.
- Removed synthetic opening `observed_stage_days` and nominal-duration breakthrough bonus. Elapsed time alone no longer creates catch-up pressure.
- Continuing membership in a martial institution retains a modest institutional teaching milieu after finite foundation enrollment ends.
- Diagnostic harness now creates biological life state for crystallized focus actors, writes unknown opening attainment chronology, and uses exact 365-day years.
- Calibration result: a 77-person opening First cohort remained strongly mixed after ten years; adult Firsts persist naturally.

# Changelog

## v0.26.1 — v1.0-preRC Integration & Usability Hardening

- Added versioned production Caerness bootstrap with 48 places, 36 institutions/polities, 388 named working-registry characters, six Hearth demographic cohorts, and six latent cultivation pools.
- Kept bootstrap separate from explicit player creation and preserved open canon boundaries for detailed routes and feast days.
- Isolated test databases from live campaign saves; guarded destructive reset and added default safety backups.
- Added ordered schema migration ledger through schema 26 with automatic pre-migration backup and compatibility repair.
- Validated representative migrations from v0.15.1, v0.19.1, v0.20.1, v0.24.0, and v0.25.0; preserved day/actor/event state in a populated v0.25 sample.
- Added ownership-mirror contradiction checks for death/life status, territorial ownership, player location, and household migration/travel state.
- Added read-only domain-state adapters from health, household, business, religion, travel, education, and politics into generic decision pressures.
- Expanded phone-first setup/Ledger/diagnostics and removed stale runtime labels.
- Hardened scheduler cadence, retired deceased actors from autonomous scheduling, optimized stable late-decline health reviews, and reused unchanged canon-context selection.
- Made crystallized v0.22 route geography authoritative for information propagation.
- Added realistic production 20/40/120-year validation, alternate deterministic runs, 1,500-actor same-day scheduler load, 64-location route/information load, and 200-business scale validation.
- Realistic 120-year production run completes with zero critical contradictions and approximately 31.2 MB database size in the packaging regression.
- Documented actor-first historical crystallization as the v1.0 scope boundary.
- Full cumulative v0.1-v0.26.1 suite passes.

## v0.25.0 — Long-Run Simulation & Stress Testing

- Added persistent stress-run/checkpoint/issue tables and `engine/stress.py`.
- Added reusable authoritative 20/40/100+ year horizon runner using the ordinary shared simulation clock.
- Added cross-system contradiction scanning for integrity, demographic, household, political, education, treatment, religious-office, chronology, camera and crystallization invariants.
- Added explicit narrative-camera successor designations and append-only camera transfer history.
- Added automatic camera handoff only when the current camera actor is dead and a designated living successor exists; no convenient successor is invented.
- Added CLI commands `camera-successor-set`, `camera-history`, `stress-run`, `stress-status`, and `stress-scan`.
- Added 20-year quiet/extreme-success, 40-year generational, and 120-year macro-history regression horizons.
- Added long-run crystallization-continuity and camera-succession adversarial tests.
- Full cumulative v0.1–v0.25 regression and adversarial suite passes.

## v0.24.0 — Education, Transmission & Institutional Reproduction

- Added persistent training programs, apprenticeships/enrollments, teacher relationships, knowledge assets, custody/access, transmission lines, certifications, and institutional reproduction profiles.
- Added shared-clock progression and interruption for teacher death, program closure, and required knowledge becoming unavailable.
- Enforced the rule that manuals/access do not directly grant competence.
- Added teacher qualification requirements and a completion cap preventing one teacher from training a student beyond that teacher's established competence through a single configured course.
- Added program capacity, duplicate/current enrollment protection, and completion anti-farming.
- Added explicit knowledge-preservation modes; oral/embodied/site-bound knowledge can become endangered and only becomes lost after a configured threshold.
- Added transmission-line vitality and dormancy without fabricated replacement masters.
- Added institutional pipeline health and successor-candidate eligibility without automatic appointment.
- Added `education_context` to scene packets and CLI exposure for the major v0.24 systems.
- Added `v24_test.py` and adversarial `v24_edge_test.py`; full cumulative suite passes.

## v0.22.0 — Ecology, Seasons, Travel & Environmental Pressure

- Added persistent per-location environmental profiles without seeding a canonical climate map or calendar.
- Added campaign-defined seasonal windows and temporary environmental conditions.
- Added Current ecology state for density, stability, replenishment, breadth, concentration, carrying capacity and recoverable local load.
- Added route graphs, route conditions, directionality, shortest-path planning, segment travel, stalling/recalculation and authoritative arrival.
- Integrated environmental factors into civilian production and market transport pressure.
- Added abstract travel exposure handoff into the existing health resolver.
- Added `environment_context` to scene packets with anti-invention guardrails.
- Hardened v0.19 scheduled household migration so crystallized route geography is obeyed rather than bypassed by instant relocation.
- Added CLI commands for environment setup, seasonal windows, routes, route conditions, travel, current use and ecology status.
- Added `v22_test.py` and adversarial `v22_edge_test.py`; complete cumulative v0.1–v0.22 suite passes.

## v0.21.0 — Religion & Cultural Institutions

- Added persistent religious traditions, affiliations, institutions, offices, campaign-defined observances, attendance, obligations, sacred sites, patronage, and domain-specific religious reputation.
- Seeded only the religious vocabulary explicitly present in the current World Bible; exact calendars and local practice remain campaign state.
- Preserved the Small True Faith as `signoff_pending` rather than silently locking unfinished canon.
- Added cultural institution profiles and recurring cultural programs distinct from businesses.
- Cultural programs create historical instances and can exert bounded influence on existing style adoption.
- Patronage transfers actual household/enterprise funds and cannot create money through overdraft.
- Integrated religious/cultural due dates into authoritative story-time advancement.
- Added religious and cultural player-facing context with anti-faction and anti-invention guardrails.
- Added `v21_test.py` and adversarial `v21_edge_test.py`. Full cumulative v0.1–v0.21 suite passes.

# v0.19.1 — Household-Life Edge-Case Audit and Hardening

- Audited births, guardianship, household splitting, migration, service terms, kinship, death cleanup, and aggregate demographic cohorts before beginning v0.20.
- Birth plans now resolve on their exact persisted due day instead of waiting for a monthly review tick.
- Automatic births require an explicit birth parent belonging to the active union and a living/eligible birth-parent profile; manual births cannot silently backdate campaign history.
- Half-siblings are linked through shared parentage; recognized kinship insertion is idempotent and repairs missing reciprocal links.
- Added explicit union and guardianship termination APIs and CLI commands.
- Guardianship moves close stale ward residence/dependency state and repair a vacated household head.
- Household splitting now validates source membership, validates resource-share bounds, transfers dependent/service/ward records with movers, updates union household affiliation, and repairs/dissolves the source household when its head leaves.
- Service terms no longer overwrite an existing family role and duplicate active service terms are idempotent. Closed households cannot renew service.
- Migration scheduling rejects past/same-location moves and supersedes earlier unresolved plans for the same household.
- Death cleanup now ends active service and guardianship records and removes dead sponsors/dependants from active dependency state.
- Aggregate demographic cohorts now age between age bands, preserve total population apart from explicit birth/migration pressure, avoid same-tick cascade aging, and schedule annual review from each cohort's own last-review day.
- Added `v19_edge_test.py` and `AUDIT_v0_19_EDGE_CASES.md`; full cumulative suite passes.

# v0.18.0 — Differentiated Business Ecology

- Added a depth audit for v0.1-v0.17 that distinguishes implemented-but-thin systems from domains already deep enough for long-run play.
- Added persisted business archetypes and location commercial context.
- Added enterprise business profiles with quality, price position, capacity, utilization, clientele fit, reliability and regulatory pressure.
- Added recurring business cycles that write revenue/expense to authoritative enterprise accounts and change enterprise cash/status through shared story time.
- Added differentiated demand/cost behavior for hospitality, entertainment, finance, craft, retail, professional services, logistics, security and cultural-market businesses.
- Added archetypes including inns, taverns, theatres, gambling houses, pleasure/courtesan houses, loan houses, moneylenders, smithies, armorers, tailors, weavers, warehouses, physicians, Vein-Menders, escort offices and others.
- Finance businesses can respond to actual outstanding credit; craft profiles coexist with production sites without simply duplicating wholesale production revenue.
- Added CLI/service exposure and v0.18 regression coverage proving business type materially changes outcomes under the same city conditions and that changing city conditions changes different archetypes differently.

# v0.17.0 — Civilian Life Depth

- Added persistent buildings and built-environment maintenance.
- Architecture and public-work projects can crystallize into buildings.
- Added local style/fashion movements and adoption dynamics.
- Added household succession plans, claims, automatic death-triggered succession, succession events, and inherited provenance.
- Added enterprise credit agreements with interest, lateness/default, payments, and borrower balance-sheet effects.
- Added enterprise ownership/governance partnerships.
- Added profession-specific institutional memberships, seniority, standing, and review eligibility without automatic office promotion.
- Added CLI coverage for all major v0.17 systems.
- Added `CIVILIAN_LIFE_DEPTH.md` and `v17_test.py`.
- Full cumulative v0.1–v0.17 regression suite passes.

---

# v0.16.0 — Civilian Simulation Core

- Added authoritative households and household membership with time-based upkeep and gradual decline.
- Added civilian enterprises with capital, cash, debt, administration, labour capacity and persistent accounts.
- Added local market goods/conditions with supply, demand, transport, risk, tax and derived local prices.
- Added production sites with elapsed-time output, labour/material bottlenecks, inventory, sales and expenses.
- Activated the existing career schema with elapsed experience, competence-gated eligibility and explicitly opt-in automatic advancement.
- Added persistent civilian projects for architecture, culture, textiles, manuscripts, craft, public works, household and business activity.
- Added persistent cultural objects and append-only provenance history.
- Added scheduled auctions, lots, bidder interest, deterministic resolution, ownership transfer and provenance updates.
- Added abstract shadow-market pressure/exposure without operational crime instructions.
- Integrated civilian resolution into the shared authoritative story-time clock.
- Added CLI commands for core civilian setup and auction flow.
- Added `CIVILIAN_SIMULATION.md` and v0.16 regression tests.
- Full cumulative v0.1–v0.16 suite passes.

# v0.15.1 — v0.1–v0.15 Implementation Audit and Combat Causality Hardening

- Audited cumulative v0.1–v0.15 code, schema, CLI, runtime paths and tests against release claims.
- Fixed v0.14/v0.15 ordering flaw: tactics and active front pressure now feed the authoritative same-round resolver instead of being only post-round processing.
- Added bounded unit leverage from persistent front pressure.
- Added explicit duel-to-battle links and automatic contextual battlefield consequence when a linked duel resolves.
- Added CLI exposure for v0.14 battlefield zones, unit-zone assignment, command links, delayed orders and command profiles.
- Fixed stale v0.13 labels in CLI/mobile startup text.
- Added `AUDIT_v0_1_TO_v0_15.md` and `audit_v01_v15_test.py`.
- Full cumulative regression suite plus audit regression passes.

# v0.15.0 — Tactical Grammar and Vein-Aware Battlefield Consequence

- Added persistent commander doctrine across ten abstract tactical families.
- Added per-round tactical choices and persisted tactical effects.
- Added opportunity-cost logic so tactics reshape reserves, information, cohesion, momentum, and local pressure instead of acting as flat bonuses.
- Added battle-zone current ecology: density, stability, and replenishment.
- Added persisted Vein battlefield assets with Stage, role, readiness, reserve, commitment, and zone assignment.
- Added Stage-sensitive but bounded Vein influence whose sustainability depends partly on local current conditions.
- Added contextual personal-combat consequence resolution with minor/local/operational/strategic scales.
- Strategic cascades now require context: important person + important place/role + low replacement + existing fragility.
- Replaced the too-strict v0.14 local-only heroic rule with **heroic consequence without heroic determinism**.
- Added `VEIN_BATTLE_TACTICS.md`.
- Added CLI hooks for doctrine, tactical family selection, zone current, and Vein assets.
- Added v0.15 regression tests; full v0.1–v0.15 suite passes.

# v0.14.0 — Multi-front Battle Flow and Command Uncertainty

- Added persistent battle zones/fronts with independent pressure and initiative.
- Added unit-to-zone assignments so local fronts can diverge inside the same engagement.
- Added command links with communication quality, discretion, and trust.
- Added delayed battle orders with issued/effective rounds.
- Added bounded subordinate adaptation when local conditions materially change.
- Added delayed, confidence-weighted battle reports for strategic views.
- Added command profiles separating planning, adaptation, presence, delegation, and nerve.
- Added persisted local turning points and bounded local morale-shock hooks.
- Battle phase can now emerge from front state rather than only elapsed round count.
- Strategic views use delivered reports and remain non-omniscient.
- Added `KINGDOM_BATTLE_STUDY.md` documenting the structural study and transfer rules.
- Added v0.14 regression tests for multi-front flow, command hierarchy, delayed reports, orders, and bounded local effects.

# v0.13.0 — Battle and Duel Resolution

- Added `engine/combat.py` with authoritative abstract battle and duel resolution.
- Added persisted combat engagements, battle sides, units, intents, subordinate unit actions, battle rounds, duel combatants, duel intents, and duel exchanges.
- Added strategic vs local player command boundaries: whole-side commanders choose strategic intent; unit commanders choose local intent.
- Added subordinate agency so non-player units act within side intent and commander judgment without player micromanagement.
- Added command-competence and martial-competence integration.
- Added morale, cohesion, readiness, fatigue, logistics, reserve, information-quality, momentum, stamina, composure, and abstract reserve state.
- Added rank-sensitive battle views that withhold hidden enemy state and expose only role-appropriate information.
- Added character-relative duel views where opponent condition is interpreted rather than revealed omnisciently.
- Added deterministic per-round seeds so rereading or regenerating narration cannot reroll combat truth.
- Duel resolution intentionally stops at abstract defeat/disengagement; detailed injury and medical consequences are deferred to the later health resolver.
- Added CLI commands for creating, viewing, issuing intents to, resolving, and auditing battles and duels.
- Added v0.13 regression tests; all v0.1-v0.13 tests pass.

### Authority rule
> **The player chooses intent. Character competence and subordinate agency perform the technical execution. Combat truth is persisted before narration.**

### Boundary
- v0.13 is an abstract narrative/simulation combat layer, not a granular real-world tactics simulator.
- Campaign logistics, detailed injuries, rehabilitation, equipment-specific technical exchanges, and civilian simulation remain later targets.

# v0.12.0

- Added interruption-safe compressed time skips.
- Added persisted time-skip runs, focus accumulation, delegation metadata, and interruption audit rows.
- Added transactional preview/rollback so long skips stop on the exact day a meaningful player decision emerges.
- Integrated routine character competence into compression: routine obligations can resolve automatically while meaningful forks interrupt.
- Focus accumulates experience evidence without silently increasing competence scores.
- Completed/interrupted periods become campaign historical anchors.
- Added CLI commands `timeskip-prepare`, `timeskip-resolve`, and `timeskip-show`.
- Added v0.12 regression tests for ordinary completion, obligation interruption, routine follow-through, and mid-chunk severe-event rollback.

# Changelog

## v0.11.0 — Competence Interpretation

- Added explicit domain-specific competence profiles with specialties, training, and experience.
- Added competence bands from untrained through master.
- Added professional-reading packets that constrain interpretation to accessible evidence and domain competence.
- Professional-reading confidence is bounded by character competence, evidence quality, and unresolved uncertainty.
- Added persisted observations, inferences, warnings, unknowns, options, and provider attribution for resolved readings.
- Added named advisor judgments as a separate layer from protagonist expertise and objective truth.
- Added decision-context packets preserving the distinction between character reading, advisor opinion, and player choice.
- Added request-sensitive `professional_context` to scene and narration packets.
- Added CLI tools for competence profiles, professional readings, advisor judgments, and decision contexts.
- Preserved the v0.7 authority boundary: expertise interprets; it does not mutate hidden world truth or steal player agency.
- Added v0.11 regression coverage; all v0.1-v0.11 tests pass.

### Boundary

- v0.11 implements the competence-interpretation target. It does not yet implement the time-skip resolver, battle/duel resolver, or full civilian economic simulation.

## v0.10.0 — Character Embodiment

### Added
- `engine/embodiment.py` with persistent protagonist voice, temperament, values, habits, social style, relationship style, current state, and development state.
- `character_embodiment` persistence table.
- `embodiment_expressions` audit history for inferred low-stakes protagonist expression.
- `speech_mediations` for intent/guided/exact dialogue mediation.
- relationship-aware embodiment packets using qualitative bands rather than exposing raw player-facing affinity numbers.
- commitment firewall with `allow / ask / block` outcomes.
- major-commitment protection for oaths, marriage, betrayal, war declarations, executions, permanent allegiance, major confessions, life-changing secrets, and irreversible contracts.
- player-safe embodiment data in scene packets and narration envelopes.
- CLI commands: `embodiment-show`, `embodiment-set`, `speech-mediate`, `speech-history`, `autonomy-check`, and `expression-record`.
- `v10_test.py` regression coverage.

### Authority rule
> Character expression may be autonomous when strongly supported and low-stakes. Major character commitment remains under player control.

### Boundary
- v0.10 mediates expression and speech; it does not yet implement the broader competence-domain interpretation layer, time-skip resolver, battle/duel resolver, or civilian economic simulation.
- Narration remains disposable presentation. Embodiment never grants prose authority to mutate world state.

## v0.9.0 — Historical Crystallization

### Added
- `engine/crystallization.py` for progressive historical crystallization of latent people.
- persisted `crystallization_runs` so historical context is frozen before biography proposals are generated.
- `crystallization_lineage` audit links from generated anchors/relationships/careers back to their historical basis.
- constrained context construction from latent-pool rules, location, institution, cohort, career tracks, and existing local events.
- validation of age windows, career domains, locations, anchor chronology, reference existence, and anchor-depth limits.
- an explicit anti-convenience firewall: retroactive connections to existing actors require persisted historical basis.
- transactional application of validated proposals into actors, continuity cores, immutable campaign anchors, cohort memberships, careers, relationships, resolution state, and latent-pool counts.
- manual/model proposal packets plus JSON response parsing; the model proposes history but never commits it.
- CLI commands: `crystallize-prepare`, `crystallize-export`, `crystallize-validate`, `crystallize-apply`, and `crystallize-show`.
- `v09_test.py` regression coverage including rejection of convenient unsupported connections.

### Authority rule
> Historical crystallization is retroactive detail generation constrained by pre-existing history. Once validated and applied, the detail becomes immutable campaign history.

### Boundary
- v0.9 crystallizes people. Latent cultural works, places, and more automatic institution/career inference remain future extensions.
- The service does not silently generate setting canon. It writes campaign history only.

## v0.8.0 — Continuity Substrate

### Added
- `continuity_cores` for compact persistent person/place/object/cohort state.
- `historical_anchors` for immutable campaign-history turning points.
- `public_narratives` and `documentary_records`, separating social/history claims from objective world events.
- cohort definitions and memberships for generation-level historical compression.
- career tracks, stages, and actor career records.
- institution profiles for pipeline, culture, capacity, economy, succession, reputation, and trajectory compression.
- entity-resolution metadata and transition history across `SCENE / ACTIVE / TRACKED / STRUCTURAL / LATENT`.
- latent entity pools so undescribed populations can pre-exist individual instantiation.
- `engine/continuity.py` helper API for the new persistence layer.
- `POST_V07_ARCHITECTURE.md` containing the consolidated post-v0.7 design target.
- `v08_test.py` regression coverage.

### Migration
- Engine metadata now reports `0.8.0`.
- Existing v0.7 `simulation_profiles` seed the new entity-resolution table (`ACTIVE → ACTIVE`, `STRATEGIC → TRACKED`, `DORMANT → STRUCTURAL`).
- The v0.7 scheduler remains authoritative for actor background cadence. The broader resolution layer is additive.

### Boundary
- Historical crystallization logic is intentionally **not** implemented yet. v0.8 provides its storage and validation substrate.
- Combat, detailed health, full economy, and finished campaign population remain future work.

## v0.7.0

### Phone-first runtime
- Added a standard-library localhost web server and responsive mobile UI.
- Added PWA/home-screen manifest and static caching for the UI shell.
- Added Scene / Matters / World / You surfaces designed around player knowledge rather than omniscient state.
- The text input is persistent; normal narration is explicitly forbidden from ending in generic “What do you do?” prompts.
- Story time remains completely separate from real-world absence.

### OnePlus 12 / 12 GB local profile
- Added `runtime_config` with a 4096-token comfortable local context and 6144-token heavy ceiling.
- Added local output, timeout, referral-sensitivity, and auto-backup settings.
- Added `ANDROID_ONEPLUS12.md` and `LOCAL_MODEL.md`.

### Local model gateway
- Added OpenAI-compatible local HTTP chat support suitable for llama.cpp-style servers.
- Added optional Ollama-native `/api/chat` support.
- Added local health/configuration commands.
- Added `local` as a first-class model request provider while preserving ChatGPT/Claude manual packets.
- Added migration logic so a v0.6 request database can accept local-provider requests without losing history.

### Scene Quality Router
- Added separate reasoning, narrative, context, and hardware scores.
- Added `rules`, `local`, `local_heavy`, `external_recommended`, and `external_strongly_recommended` routes.
- External recommendations state whether the principal reason is quality, reasoning, or hardware load.
- The player can force local execution at any time.

### Character Competence Layer
- Added persisted possessions, intentions, obligations, and contextual attention cues.
- Routine established intentions can auto-resolve when their trigger becomes true.
- Added automatic delivery behavior for persisted possessions such as letters.
- `ask_if_changed` intentions stop and create a player decision cue when recognized circumstances have materially changed.
- Approaching obligations create contextual reminders rather than relying on journal micromanagement.

### Agency handoffs / long-form sections
- Added `open`, `hard`, and `none` agency handoff assessments.
- Added narrative segment outlines and agency checkpoints.
- Travel, downtime, and conversations can be represented as several fictional beats inside one player-facing section.
- Local narration can be generated through several technical model calls and joined into one continuous passage; no `continue` input is required at model boundaries.
- Added an interrupt flag/endpoint for future safe-boundary interruption during longer automatic sequences.

### Emergence Layer
- Added persistent actor memories derived from real events.
- Actor decision contexts can now include important memories.
- Added thread evidence and conservative recognition of recurring developing situations.
- Emergence recognition is explicitly prohibited from changing outcomes for dramatic convenience.

### Discovery / epistemic UI preparation
- Added player-facing sourced claims, known people, known places, and Matters projections.
- Hidden relationship numbers and secret actor state remain outside the normal UI.
- Attention popups are transient while the underlying Matter remains inspectable.

### Save integrity
- Enabled SQLite WAL mode.
- Added consistent database backup/restore commands and rotating mobile auto-backups.
- Engine metadata now reports version `0.7.0`.

### Tests
- Added tests for phone runtime defaults, story-time-only behavior, local model compatibility, competence auto-fulfillment, competence agency forks, multi-scene handoffs, external referral routing, event memory, emergent thread recognition, and localhost mobile-state serving.
- Full v0.1–v0.7 regression suite passes.

## v0.6.0

- Provider-neutral model gateway.
- Manual ChatGPT and Claude bridge packets with no API requirement.
- Two-stage safe action interpretation and post-state narration.
- Optional major-NPC model decisions with persisted validation.

## v0.5.0

- Persistent player-action/turn loop.
- Shared world time and route-based travel.
- Observer-independent location/world processes.
- Camera-focus / anti-protagonist-gravity architecture.
- Player-safe narration envelope and campaign journal.

## v0.19.0 — Household, Kinship, Demographic, and Life-Course Simulation

- Added persistent actor life profiles with birth day, social life stage, household origin/current household, family-formation eligibility, and living/deceased state.
- Added persistent kinship links separate from generic stance/trust relationships.
- Added explicit household unions and conservative family plans; the engine does not auto-create marriages/partnerships.
- Added authoritative births from already-established family plans, including child actors, parent/child and sibling kinship, household dependency, and life history.
- Added guardianships and household dependencies.
- Added household splitting/formation support with bounded resource transfer and member relocation.
- Added persisted service terms for servants, retainers, guards, stewards, tutors, apprentices, clerks, and other household staff.
- Added scheduled household migration that moves active household members through the shared world clock.
- Added aggregate demographic cohorts for population-scale birth pressure and migration without forcing every person into named simulation.
- Added explicit death lifecycle transition for later health/combat/political systems without prematurely inventing ordinary mortality.
- Integrated life-course reviews into normal civilian/world advancement and civilian summaries.
- Added CLI commands for life profiles, unions/family plans, births, guardianship, household migration/service, demographic cohorts, and life status.
- Added `HOUSEHOLD_LIFE.md` and cumulative `AUDIT_v0_1_TO_v0_19.md`.
- Added v0.19 regression and reran the entire cumulative v0.1-v0.19 suite plus the v0.15.1 implementation audit.


## v0.20.1 — Health Edge-Case Hardening

- Preserved accrued late-life decline across later cultivation-class upgrades; breakthrough can slow future decline without rewinding age.
- Made condition recovery respect the actor's current recovery capacity.
- Added provider qualification checks using the existing Medicine and Vein-Mending competence domains.
- Required living qualified providers for medicine, surgery, Vein-Mending, guided circulation, and elixir stabilization where appropriate.
- Time-weighted treatment effects by actual overlap with the condition review interval.
- Prevented expired treatments from applying beyond their end day.
- Prevented Vein-specific treatments from acting as generic ordinary medicine.
- Made disability adaptation elapsed-time based and immune to repeated same-day recalculation.
- Added explicit disability resolution for genuine repair while preserving disability after source-condition recovery.
- Added source-condition ownership validation for disabilities.
- Stopped patient- and provider-owned treatments on death and froze health progression for deceased actors.
- Added `v20_edge_test.py` and `AUDIT_v0_20_EDGE_CASES.md`; full cumulative v0.1-v0.20.1 suite passes.

## v0.20.0 — Health, Aging, Medicine, Disability, and Mortality

- Added authoritative actor health profiles with cultivation-sensitive longevity classes and Growth / Prime / Late Decline phases.
- Added persistent injuries, illness, chronic disease, fatigue, Channel/Core pathology, and Rupture conditions.
- Added treatment records for ordinary medicine, surgery, rehabilitation, rest, Vein-Mending, guided circulation, and elixir stabilization.
- Added persistent disability with gradual adaptation rather than automatic restoration to baseline.
- Added causal named-character mortality and aggregate demographic mortality.
- Added health state to player-facing scene packets.
- Kept combat resolution and bodily aftermath as separate authority layers.
- Added v0.20 regression and retained the v0.15.1 implementation audit plus v0.19 edge-case regression.

## v0.23.0 — Politics, State Transformation & Macro-History

- Added persistent political polities backed by institution actors.
- Added rulers, dynasties, dynasty membership and succession claims.
- Added authoritative one-controller-per-location territorial state with control kind, legitimacy and integration.
- Added territorial claims with story-time pressure and campaign-configured resolution policies.
- Added interstate relations and political hierarchy links: vassalage, protectorate, federation, personal union and tributary status.
- Added hierarchy-cycle prevention and no-orphan-territory dissolution safeguards.
- Added polity dissolution with successor-state territory transfer.
- Added political structural processes for integration, separatism, legitimacy, stability, treasury and diplomacy pressure.
- Added append-only `political_history` for map and regime continuity.
- Added political due dates to shared story-time advancement and political context to scene packets.
- Added CLI exposure for core polity, territory, claim, succession and hierarchy operations.
- Added `v23_test.py`, `v23_edge_test.py`, `POLITICS_AND_MACRO_HISTORY.md`, and `AUDIT_v0_23_EDGE_CASES.md`.
- Full cumulative v0.1–v0.23 suite passes.
