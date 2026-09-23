# Caerness Engine v0.60.0 — Schema 80 ORGAGENCY / POLITYAGENCY / CONFLICT-01 Accepted Checkpoint

**Current schema: 80.** The accepted schema-76 TENYEAR-01 run remains the historical diagnostic baseline; schema 80 adds the next causal layer rather than replacing that history.

Schema 80 gives institutions a shared agency substrate (inheritance, regimes, factions/pressures, issue-specific strategy and concrete capability), bridges durable underworld organizations into that substrate without changing their type, gives all seven polities explicit decision authority, and adds endogenous conflict-origin channels that feed concrete incidents into DEC-01 and WAR-01.

Politics is relation- and issue-specific rather than a single national personality score. Leadership can change direction without rewriting institutional inheritance, and desired strategy cannot bypass physical capability. Limited campaign candidates require real route and logistics feasibility. A persistence-level response uniqueness rule plus candidate/execution guards prevents repeated formal responses to the same incident.

A deterministic fresh 365-day audit produces three limited political incidents, two government responses and zero campaigns. The accepted schema-76 day-3650 save migrates to schema 80 without changing its day, event history, political-history count or campaign history, then resumes normally.

See `ORGAGENCY_CONFLICT01_SCHEMA80_ACCEPTANCE_2026-09-19.md` for the complete schema, migration, calibration and regression record.

## Historical v0.26.1 integration notes

## v0.26.1 — pre-RC closure

v0.26.1 closes the blockers found by the final v1.0 candidate review without adding another major simulation domain. It makes the existing engine safer to install, easier to start, more visible on the phone-first interface, and viable under a realistic century-scale seed.

Key additions and hardening:

- versioned production Caerness bootstrap derived from the current World Bible, with 48 established places, 36 institutions/polities, 388 named working-registry characters, six Hearth demographic cohorts, and six latent cultivation pools;
- bootstrap and player creation remain separate, so campaign setup does not silently invent the player character;
- test databases are isolated from the packaged/live campaign database, destructive reset is guarded, and normal resets/migrations create safety backups;
- ordered schema migration ledger through schema version 26, including pre-migration backup and compatibility repair;
- explicit ownership checks for life/death mirrors, territorial ownership, player location, and household migration/travel state;
- domain-state adapters that expose health, household, business, religion, travel, education, and politics pressures to the generic decision layer without duplicating domain truth;
- phone-first setup, Ledger inspection, and diagnostics for campaign state, health, household, education, religion, travel/environment, derived pressures, version/schema state, and contradiction status;
- scheduler cadence hardening, deceased-actor scheduler retirement, stable-late-decline health review optimization, and canon-context reuse;
- authoritative established travel routes for information propagation once route geography is crystallized;
- production-scale 20/40/120-year validation, alternate deterministic runs, dense scheduler load, large route/information graph validation, and differentiated-business scale validation.

The realistic 120-year production-seed run reaches day 43,800 with zero detected contradictions. In the packaging environment its sequential 20/40/120 checkpoints took roughly 5.58 s, 5.51 s, and 19.67 s, with the database growing to about 31.2 MB. These are regression measurements, not hardware guarantees.

The full ordinary cumulative suite also passes through v0.26.1. See `AUDIT_v0_26_INTEGRATION_AND_SCALE.md`, `V1_RC1_READINESS.md`, and `V1_CANDIDATE_CHECKLIST.md`.

## v0.25 — Long-Run Simulation & Stress Testing

v0.25 is the consolidation pass. It adds persisted 20/40/100+ year stress runs, cross-system contradiction scanning, checkpoint snapshots, explicit narrative-camera succession after protagonist death, and long-horizon regression coverage using the same authoritative story clock as ordinary play.

The cumulative fixture now runs through 120 years while exercising civilian economy, demographics, health/mortality, culture, politics, education/institutional reproduction, and camera continuity. No adversity debt is created merely because the quiet-life enterprise succeeds.

See `LONG_RUN_STRESS_TESTING.md`, `AUDIT_v0_25_EDGE_CASES.md`, and `AUDIT_v0_1_TO_v0_25.md`.

## v0.24 — Education, Transmission & Institutional Reproduction

v0.24 makes learning and institutional continuity causal. Programs, teachers, apprenticeships, manuals/archives/oral inheritances, knowledge access, transmission lines, certifications, and institutional reproduction now persist and advance through story time. Manuals are explicitly media of transmission rather than mastery objects; teacher death or loss of required knowledge can interrupt training; oral or embodied knowledge can become endangered and, under configured campaign rules, genuinely lost.

Institutional pipeline health is descriptive structural state, not automatic destiny. The engine does not manufacture replacement teachers, recruits, or successors merely to preserve an institution. Successor candidates can become eligible but are never auto-appointed.

See `EDUCATION_AND_TRANSMISSION.md` and `AUDIT_v0_24_EDGE_CASES.md`.

## v0.22 — ecology, seasons, travel and environmental pressure

v0.22 adds authoritative environmental state and route-based movement. Locations can carry campaign-defined climate/terrain profiles, seasonal and temporary pressures, and local Current carrying capacity. Travel now follows established route geography one segment at a time, recalculating at intermediate nodes when conditions change. Civilian production and markets respond to environmental pressure, and severe travel exposure hands consequences to the existing health system.

No named seasons, weather events, routes or climate zones are seeded automatically. The current World Bible leaves detailed travel geography open, so v0.22 supplies the machinery without silently deciding unresolved canon. The included adversarial audit also found and fixed a cross-version issue where scheduled household migration could bypass established routes.

Caerness is a persistent world simulation with a narrative camera inside it. The central rule is:

> **Caerness is a world simulation with a camera in it, not a game world waiting for its player.**

The player character matters because the story follows them. The wider world does not scale itself around them, wait for them, or protect their success.

v0.7 is the first phone-first runtime. It is designed specifically around a **OnePlus 12 with 12 GB RAM** and can run without a PC or paid API. The recommended stack is:

```text
OnePlus 12
  -> Caerness mobile UI (localhost)
  -> Python + SQLite simulation
  -> rules for routine world activity
  -> local OpenAI-compatible model server for normal interpretation/narration
  -> ChatGPT / Claude manual bridge only when desired or recommended
```

Real-world absence does **not** advance the campaign. Story time moves only when in-world actions consume time.


## v0.20.1 — health edge-case hardening

An adversarial audit of v0.20 found several places where the health system existed but did not yet preserve its own rules under awkward timing and ownership cases. v0.20.1 hardens aging continuity, treatment ownership, Vein-Mending qualification, treatment duration, disability adaptation, and death cleanup.

Key corrections:

- a late cultivation breakthrough can slow future decline but cannot erase decline already accrued;
- ordinary recovery now respects the actor's actual recovery capacity, so late decline matters to healing speed;
- medical and Vein-Mending treatments that require expertise must have a living qualified provider;
- expired or stopped treatment contributes only for the portion of the review interval in which it was actually active;
- Vein-specific care no longer acts as a generic cure for ordinary illness or injury;
- disability adaptation advances by elapsed story years rather than by how often the profile happens to be recalculated;
- resolved source conditions do not erase lasting disability, while explicit successful repair can close the disability;
- death stops patient and provider-owned treatment, and health conditions on deceased actors no longer keep evolving.

See `AUDIT_v0_20_EDGE_CASES.md`.




## v0.18 — differentiated business ecology

The civilian economy now distinguishes concrete business archetypes rather than relying only on broad `shop` / `workshop` / `service` containers. Local commercial context and business-specific demand weights cause inns, theatres, lenders, smithies, tailors, warehouses, regulated entertainment venues and other enterprises to behave differently through shared story time. See `BUSINESS_ECOLOGY.md` and `DEPTH_AUDIT_v0_1_TO_v0_17.md`.

## v0.16 — civilian simulation core

v0.16 makes peaceful and professional life authoritative simulation rather than narration-only flavour. Households, enterprises, production, local markets, careers, projects, cultural objects, provenance, auctions, and abstract shadow-market pressure now persist in SQLite and advance through the same story-time clock as the rest of Caerness.

Markets are local and causal; production has labour/material bottlenecks; careers accumulate experience and advance only according to explicit track rules; cultural projects can create persistent objects; auctions transfer ownership and provenance; household and enterprise finances can improve or deteriorate gradually.

See `CIVILIAN_SIMULATION.md`.

## v0.15.1 — audit hardening

A full v0.1–v0.15 implementation audit found that the v0.14/v0.15 multi-front/tactical layers existed but were being applied too late in the round loop to fully shape the same authoritative round. v0.15.1 corrects that ordering, makes persistent front pressure causally affect assigned units, and links battle-embedded duels directly to contextual battlefield consequence. It also exposes the v0.14 command/front APIs through the CLI and fixes stale release labels.

See `AUDIT_v0_1_TO_v0_15.md` for the version-by-version findings and corrections.

## v0.15 — Tactical grammar and Vein-aware battle consequence

v0.15 extends v0.14 rather than replacing its multi-front model. Commanders now have persistent abstract doctrine preferences across pressure, fixing, misdirection, isolation, depth, reserve play, mobility, attrition, disruption, and exploitation. These are reasoning families with opportunity costs, not scripted winning moves or real-world tactical instructions.

Battle zones can now carry current density, stability, and replenishment. Persisted Vein assets carry Stage, readiness, reserve, commitment, role, and location, allowing cultivators to matter as finite strategic resources rather than generic bonuses. Rich current improves sustainability; it never grants capabilities the cultivator does not possess.

Personal combat is no longer forced to remain merely local. A defeat can be minor, local, operational, or strategic depending on Stage, front importance, command significance, replacement depth, and the side's existing fragility. A duel can therefore contribute to or even trigger a battle-deciding cascade in exceptional circumstances without becoming an automatic victory switch.

> **Heroic consequence without heroic determinism.**

See `VEIN_BATTLE_TACTICS.md`.

## v0.14 — Multi-front battle flow

v0.14 revises the first combat skeleton after a dedicated structural study of large-scale war storytelling. It adds persistent battle zones, command links, delayed orders, partial reports, commander profiles, local turning points, bounded local morale shocks, and emergent battle phases. The goal is not to reproduce any copyrighted battle or real-world technique; it is to make Caerness battles readable at several scales while preserving protagonist-agnostic causality.

The key correction is that a battle is no longer treated only as one whole-army contest. Local fronts can improve or deteriorate independently, and senior commanders must act through incomplete reports and subordinate agency. See `KINGDOM_BATTLE_STUDY.md`.

## v0.13 — Battle and duel resolver

v0.13 adds the first dedicated combat resolver while preserving the existing authority boundary. Combat state is persisted before narration, player decisions remain high-level, and technical execution belongs to character competence plus subordinate agency rather than requiring the player to supply real-world tactical or weapon detail.

Battles operate through sides, units, morale, cohesion, readiness, fatigue, logistics, reserves, information quality, momentum, command competence, and abstract intents. A player commanding a whole side receives a strategic decision boundary; a player commanding one unit receives a local decision boundary. Other units continue acting through subordinate judgment instead of waiting for the player to micromanage them.

Duels use the same philosophy at personal scale. The player chooses abstract intent such as measuring, pressing, defending, conserving, committing, controlling, or disengaging. The resolver handles the technical exchange internally using martial competence, readiness, stamina, composure, reserve, and momentum. Specific injury and medical consequences are deliberately deferred to the later health resolver.

Rank-sensitive views expose only what the character's role and competence plausibly support. Enemy hidden state is not exposed as raw numbers.

Useful commands:

```text
python run.py battle-create "Border Clash" --player "Player Name"
python run.py battle-side-add 1 "North" --controller "Player Name"
python run.py battle-unit-add 1 "Main Body" --commander "Captain Name"
python run.py battle-intent 1 "Player Name" probe --risk balanced
python run.py battle-resolve 1
python run.py battle-view 1 "Player Name"

python run.py duel-create "Formal Duel" "Player Name" "Rival Name" --player "Player Name"
python run.py duel-intent 2 "Player Name" measure
python run.py duel-resolve 2
python run.py duel-view 2 "Player Name"
```

> **Combat intent is player-facing; technical execution remains character-facing.**


## v0.12 — Time-skip resolver

Long waits are now compressed simulation rather than simply adding days. A prepared time skip records the protagonist's focus and delegated authority, advances the same shared world clock used by every NPC and regional process, accumulates grounded career/competence exposure without granting free skill increases, and stops at meaningful agency interruptions.

The resolver previews bounded chunks transactionally. If a severe direct event, consequential incoming interaction, important non-routine obligation, or competence fork appears inside the chunk, the preview is rolled back and the world is advanced again only to the exact interruption day. This preserves the rule that **compression ends where consequential player choice begins**.

Useful commands:

```text
python run.py timeskip-prepare "Player Name" 180 --focus commerce --focus family
python run.py timeskip-resolve 1
python run.py timeskip-show 1
```

Focus time is evidence of experience, not automatic advancement. Later career/training resolvers decide whether accumulated exposure produces promotion or competence growth.

## What v0.8 adds

v0.8 is the first implementation pass after the post-v0.7 Narrative Engine architecture. It keeps v0.7's mobile/runtime and authority boundaries intact while adding the persistence substrate required for deeper long-form lives and history.

New schema and helpers cover:

- compact **continuity cores** for persistent entities;
- append-only **historical anchors** for biographical and institutional turning points;
- **public narratives** and **documentary records** separate from objective event truth;
- historical **cohorts** and explicit memberships;
- **career tracks, stages, and actor careers**;
- **institution profiles** as compression nodes for culture, pipelines, capacity, succession, and trajectory;
- broader **entity resolution** (`SCENE / ACTIVE / TRACKED / STRUCTURAL / LATENT`) layered above, not substituted for, the v0.7 actor scheduler;
- a transition history for resolution promotion/demotion;
- constrained **latent entity pools** representing people or other entities that exist structurally before individual crystallization.

The implementation lives primarily in `engine/schema.sql` and `engine/continuity.py`. Existing `ACTIVE / STRATEGIC / DORMANT` actor profiles still drive the v0.7 background scheduler; v0.8 seeds the broader resolution layer from those profiles for backward compatibility.

> **v0.8 does not yet implement historical crystallization itself.** It implements the database and helper layer that the crystallization service will use next.

See `POST_V07_ARCHITECTURE.md` for the complete design target.


## What v0.9 adds

### Historical crystallization

Latent people can now become persistent individuals with a constrained pre-existing history. The engine first freezes a context drawn from location, institution, cohort, career rules, latent constraints, and existing historical events. A model or human may propose a biography, but the engine validates it before any campaign history changes.

The central rule is:

> **Historical crystallization explains an existing life; it does not invent a convenient past for the current plot.**

Typical workflow:

```bash
python run.py crystallize-prepare LATENT_ID --depth developed
python run.py crystallize-export RUN_ID
# create/edit a JSON proposal from the packet
python run.py crystallize-validate RUN_ID proposal.json
python run.py crystallize-apply RUN_ID
python run.py crystallize-show RUN_ID
```

Unsupported retroactive connections to existing actors are rejected. Applied details become campaign history and do not become setting canon.


## What v0.11 adds

### Domain-specific competence

Characters now carry explicit professional competence by domain rather than relying on one generic intelligence or on the player's real-world expertise. Domains include martial practice, command, politics, administration, commerce, medicine, Vein-Mending, craft, architecture, scholarship, social judgment, law, art/culture, and regional knowledge. Competence bands run from untrained through master and may include specialties, training history, and experience.

### Professional readings

The engine can prepare an auditable professional-reading packet from player-accessible evidence. The packet limits interpretation depth according to the character's competence and evidence quality. Expertise may deepen inference; it may not reveal hidden state, manufacture certainty, or override a deliberate player choice. Resolved readings preserve observations, inferences, warnings, unknowns, options, and bounded confidence.

### Advisor separation

Advisor judgments are persisted separately from the protagonist's own professional reading. A named advisor may disagree with the character or with another advisor. The engine therefore preserves the distinction between character knowledge, reports, advisor judgment, and player decision.

### Scene integration

Scene and narration packets now carry `professional_context`. Request-sensitive domain detection can surface the protagonist's relevant expertise to the narrator while maintaining v0.7's information firewall.

Useful commands:

```text
python run.py competence-set "Actor" commerce 70 --specialty "long-distance trade"
python run.py competence-show "Actor"
python run.py professional-read "Actor" commerce "A shipment is late and premiums are rising."
python run.py professional-show 1
python run.py advisor-judgment "Actor" "Advisor" commerce wool-delay-1 "I would hold the route."
python run.py decision-context "Actor" commerce wool-delay-1 --reading-id 1
```

## What v0.10 adds

### Character embodiment

v0.10 gives the protagonist a persistent character model that survives between direct commands. It extends the existing v0.7 competence boundary without giving the narrator authority over major player decisions.

The governing rule is:

> **The protagonist is still a character when the player is not directly puppeteering every sentence and gesture. Character expression can be autonomous; major commitment generally cannot.**

New systems include:

- persistent voice, temperament, values, habits, social style, relationship style, current state, and development data;
- speech mediation across `intent`, `guided`, and `exact` input modes;
- a commitment firewall that permits strongly supported low-stakes expression but blocks autonomous oaths, marriage choices, betrayals, declarations of war, executions, permanent allegiances, and comparable irreversible commitments;
- coarse relationship-aware rendering cues without exposing raw relationship meters to the narrator;
- an audit trail for autonomous expression and speech-mediation packets;
- embodiment data inside player-safe scene and narration envelopes.

Useful commands:

```bash
python run.py embodiment-show "Actor Name"
python run.py embodiment-set "Actor Name" profile_patch.json
python run.py speech-mediate "Actor Name" "Tell him we support him if he keeps his word." --mode intent
python run.py autonomy-check "Actor Name" gesture --confidence 0.9 --stakes 1
python run.py expression-record "Actor Name" "Gives a familiar brief nod." --kind greeting
python run.py speech-history "Actor Name"
```

The narrator may use the protagonist model to choose small, consistent gestures, phrasing, timing, and habitual expression. It may not use that model as permission to decide irreversible commitments or invent hidden self-knowledge.

## What v0.7 adds

### Phone-local runtime

`python run.py serve` starts a mobile-first browser interface at `http://127.0.0.1:8765`.

The interface is deliberately not an RPG spreadsheet. The main screen is the prose scene. The input field remains available without the narrator repeatedly asking *What do you do?*. Supporting screens expose only what the character could reasonably know:

- **Scene** — the actual narrative camera;
- **Matters** — current commitments and intentions;
- **World** — known people, places, and sourced knowledge;
- **You** — character/runtime information.

The UI is installable as a home-screen web app and is served entirely from the phone.

See `ANDROID_ONEPLUS12.md`.

### Local-model gateway

v0.7 supports two local HTTP backends:

- `openai_compatible` — intended for `llama.cpp` server and other compatible runtimes;
- `ollama_native` — optional native `/api/chat` compatibility.

No paid OpenAI or Anthropic API is required. ChatGPT and Claude remain available through the existing manual bridge packets.

Useful commands:

```bash
python run.py runtime-status
python run.py local-health
python run.py runtime-config --backend openai_compatible \
  --endpoint http://127.0.0.1:8080/v1/chat/completions \
  --model local-model --context 4096 --heavy-context 6144
```

### Scene Quality Router

Before an expensive model task, the engine independently scores:

- reasoning complexity;
- narrative importance;
- estimated context size;
- phone/hardware burden.

The result is one of:

```text
rules
local
local_heavy
external_recommended
external_strongly_recommended
```

An external recommendation is never mandatory. The player may always **run locally anyway**.

The UI explains *why* it recommends ChatGPT/Claude: better reasoning, better prose, hardware relief, or a combination.

### Character Competence Layer

> **The player controls decisions. The character handles competence.**

Established intentions and obligations persist in the database. The player is not expected to remember obvious physical follow-through that the character would naturally remember.

Example: if the character has agreed to deliver a sealed letter to someone, still possesses it, and later meets the recipient under ordinary circumstances, the competence layer can deliver it automatically. If circumstances have changed enough to make delivery a meaningful choice, the engine stops and surfaces that choice instead.

The layer also generates contextual reminders for approaching obligations. Journals are reference tools, not substitutes for ordinary character memory.

Developer/admin commands:

```bash
python run.py matters
python run.py attention
python run.py possession-add "Player Wanderer" "sealed letter" --type letter
python run.py intention-add "Player Wanderer" "deliver the letter" \
  --target-actor "River Lantern" --possession-id 1 \
  --kind deliver_possession --trigger actor_present --policy ask_if_changed
```

### Agency Handoffs

A fictional scene boundary is **not** automatically a player-turn boundary.

The engine distinguishes:

- **hard handoff** — continuing would decide a meaningful unresolved choice for the player;
- **open handoff** — the situation is rich enough that the player may reasonably want to act, even though nobody explicitly asked them anything;
- **no handoff** — the established course can continue without meaningful loss of agency.

The narrator must not end normal output with generic prompts such as *What do you do?*.

> **The narrator does not ask the player to act. It gives them a world worth acting in.**

One player-facing passage may cover multiple scenes, transitions, or days. On a local phone model these may be generated in several technical chunks and joined into one continuous section, so the player is never forced to type `continue` merely because a model reached a generation boundary.

### Emergence Layer

Events now create durable actor memories and can reinforce existing causal threads. Repeated related consequences can be recognized as a developing thread without scripting a predetermined plot.

This layer has **no authority to change outcomes for dramatic convenience**. It recognizes continuity; it does not author destiny.

NPC decision packets can include significant memories, allowing earlier humiliation, aid, betrayal, debts, defeats, or other consequences to affect later behavior without relying on the LLM to remember old prose.

```bash
python run.py memories "Actor Name"
python run.py emergent-threads
```

### Player-facing discovery state

The World interface is epistemic rather than omniscient. It derives information from persisted knowledge and provenance:

- what the character believes;
- when they learned it;
- how reliable it seems;
- whether it came from direct experience, rumour, another actor, or an information network;
- which people and places have actually entered the character's experience.

Hidden relationship numbers, secret actor goals, and omniscient state are not shown.

### Save integrity and backups

SQLite uses WAL mode and authoritative turn resolution remains transactional. Backups are taken only after committed state.

```bash
python run.py backup --label before_convergence
python run.py restore game/campaign_01/backups/caerness_day000123_turn000045_before_convergence.db
```

The mobile runtime defaults to an automatic rotating backup every 10 turns.

## Foundational play principles

### Camera Principle

The player is the focus of the narrative, not the causal center of the world.

### Emergent Story Principle

Caerness generates circumstances, consequences, and continuity rather than predetermined plots.

### Earned Outcome Principle

The simulation should not hedge important outcomes to preserve the player's success. A future combat/tactical resolver must permit genuine defeat, serious injury, loss, and death. Any slight “main-character” bias belongs primarily in **opportunity**, not outcome protection.

### Experienced World Principle

The World Bible is for the engine. The player should learn Caerness mainly through participation, consequences, conversation, observation, rumours, objects, customs, travel, research, and institutional friction rather than compulsory exposition.

### Character Competence Principle

The player chooses meaningful intent; the character performs obvious routine follow-through unless circumstances create a new meaningful decision.

### Agency Handoff Principle

The game pauses at agency-rich moments, not model/scene boundaries. It may pause even when nobody needs anything from the player. It should also be interruptible whenever the player notices something they want to pursue.

## Existing living-world guarantees retained

v0.7 preserves the systems built in v0.1–v0.6:

- stable canon retrieval from the current World Bible;
- live SQLite world state;
- Active / Strategic / Dormant simulation tiers;
- **Dormant means coarse simulation, never frozen simulation**;
- exact-date clocks;
- actor background processes;
- actor goals, pressures, resources, drives, constraints, relationships, and decisions;
- NPC-to-NPC offers, negotiations, contracts, alliances, threats, investigations, and conflicts;
- persistent agreements and causal links;
- actor-independent regional/world processes;
- public / limited / private / secret event policies;
- route-based rumour propagation and information channels;
- player-safe scene packets;
- no autonomous simulation of player decisions;
- manual ChatGPT and Claude bridge packets.

## Quick start on desktop/testing

```bash
python run.py reset
python run.py init
python run.py seed-demo
python run.py serve
```

Then open:

```text
http://127.0.0.1:8765
```

The demo content is explicitly non-canon and exists only to exercise the engine.

## Local vs ChatGPT / Claude

A typical intended workload is:

```text
routine world simulation       -> deterministic rules
routine NPC choices            -> deterministic rules
ordinary player interpretation -> local model only when rules cannot ground it
ordinary narration             -> local model
heavy council/political scene  -> router may recommend ChatGPT/Claude
major ambiguous NPC decision   -> router may recommend ChatGPT/Claude
```

Manual bridge workflow remains:

```bash
python run.py bridge-play "..." --provider chatgpt
python run.py bridge-play "..." --provider claude
python run.py model-import REQUEST_ID response.txt
python run.py model-apply REQUEST_ID
```

On the mobile UI, a referral card can copy the complete ChatGPT or Claude packet to the clipboard and later import the returned JSON from the clipboard.

## Project layout

```text
Caerness_Engine_v0_26_1/
├── canon/
│   └── world_bible_current.docx
├── data/
│   └── caerness.db
├── engine/
│   ├── actions.py
│   ├── agency.py
│   ├── canon.py
│   ├── combat.py
│   ├── battle_tactics.py
│   ├── battlefield.py
│   ├── competence.py
│   ├── db.py
│   ├── decisions.py
│   ├── discovery.py
│   ├── emergence.py
│   ├── information.py
│   ├── interactions.py
│   ├── local_model.py
│   ├── mobile_runtime.py
│   ├── mobile_server.py
│   ├── model_gateway.py
│   ├── player.py
│   ├── router.py
│   ├── schema.sql
│   ├── simulation.py
│   ├── turns.py
│   └── world.py
├── mobile/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── manifest.json
│   └── sw.js
├── game/campaign_01/
├── tests/
├── ANDROID_ONEPLUS12.md
├── CHATGPT_BRIDGE.md
├── CLAUDE_BRIDGE.md
├── DESIGN.md
├── LOCAL_MODEL.md
└── run.py
```

## Tests

```bash
python tests/run_all.py
```

The suite includes all v0.1–v0.14 guarantees plus v0.15 regression tests for doctrine-driven tactical variation, tactical opportunity costs, Vein assets, current ecology, contextual personal-combat consequences, and exceptional-but-causal battle cascades.

## Current boundary

v0.15 now includes the first mature abstract battle stack, but it is **not yet the final campaign game**. Detailed injury/health consequences, full civilian economic simulation, finished campaign population, and deeper campaign-scale military logistics remain future work. The included actors remain demo data.


## v0.17 — civilian life depth

v0.17 deepens the v0.16 civilian substrate instead of opening another unrelated system. The built environment, fashions and styles, household succession, commercial credit/partnerships, and profession-specific institutional membership now persist and advance through shared story time.

Key additions:

- architecture/public-work projects can crystallize into persistent buildings with condition, prestige, utility and maintenance burden;
- dress, textile, architecture and decorative styles spread unevenly by locality through prestige, elite support, craft capacity, accessibility and resistance;
- household succession can be designated, claim-driven, contested or vacant, and personal cultural property receives inherited provenance when it passes to a successor;
- enterprise credit tracks principal, accrued interest, lateness/default and borrower balance-sheet consequences;
- enterprise partners have explicit ownership, governance weight and committed capital;
- professional memberships accumulate seniority and may become eligible for review, but the engine never silently grants an office or promotion;
- all of the above are exposed through CLI/service functions and covered by `v17_test.py`.

The governing principle is: **civilian institutions should accumulate history the same way military and political systems do.**
## v0.19 household and generational life

v0.19 adds persistent life profiles, kinship, household unions/family plans, births, guardianships, dependants, household splitting, staff/service turnover, household migration, aggregate demographic cohorts, and explicit death transitions. See `HOUSEHOLD_LIFE.md` and `AUDIT_v0_1_TO_v0_19.md`.

The engine does not automatically create marriages or partnerships. Births generated by routine simulation require an already-established union with an explicit family plan. Ordinary mortality, health, disease, disability, cultivation-specific aging, and medical treatment remain v0.20 responsibilities.


## v0.19.1 — household-life edge-case audit

v0.19.1 is a hardening release completed before starting the health/aging pass. It adds no new simulation domain; it makes the v0.19 household/demographic systems behave coherently at awkward boundaries.

Key corrections include exact family-plan due dates, conservative automatic-birth validation, half-sibling linking, idempotent kinship, guardianship ending/cleanup, household-head repair when members move, split-record transfer for dependencies/service/guardianship, migration-plan supersession, service-term idempotency, death cleanup, age-band progression for aggregate cohorts, and cohort-specific annual review scheduling.

See `AUDIT_v0_19_EDGE_CASES.md` and `tests/v19_edge_test.py`.

---

## v0.20 — Health and aging

v0.20 makes health authoritative campaign state. Characters now possess longevity/aging profiles, recoverable or chronic conditions, treatment histories, disabilities and adaptive capacity. Cultivation extends the prime before old age; it does not provide immortality or rewind age.

Vessel pathology is distinguished from ordinary illness and injury. Ordinary medicine may support recovery, but Channel/Core damage and Rupture can require Vein-Mending or related specialist care. Scene packets include a bounded `health_context` so physical condition can shape narration and competence without taking decisions away from the player.

See `HEALTH_AND_AGING.md` and `AUDIT_v0_1_TO_v0_20.md`.

## v0.23 — Politics, State Transformation & Macro-History

v0.23 adds persistent polities, rulers, dynasties, succession claims, authoritative territorial control, territorial claims, interstate relations, political hierarchy, state dissolution/successor transfers, structural political processes, and append-only macro-history.

Political state now participates in shared story time and can genuinely diverge over long campaigns without protagonist protection or automatic balance restoration.

See `POLITICS_AND_MACRO_HISTORY.md` and `AUDIT_v0_23_EDGE_CASES.md`.
