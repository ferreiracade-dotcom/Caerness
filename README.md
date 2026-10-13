# Caerness — a life in a living world

A free-form AI narrative RPG for desktop/laptop browsers, with mobile-browser compatibility. The AI supplies conversation, reasoning and prose; the Python/SQLite simulation supplies authoritative continuity and consequences.

**Play free on Windows:** [download the complete local-AI branch ZIP](https://github.com/ferreiracade-dotcom/Caerness/archive/refs/heads/feat/free-local-ai.zip), extract it and double-click **Play Caerness.cmd**. [Windows instructions](WINDOWS_PLAY.md) explain hardware detection, permission before downloads, Ollama startup and the actual inference check. No paid account or API key is required. **Play with LM Studio.cmd** supports model comparison; **Change Local Model.cmd** preserves the campaign. Local model quality remains subject to genuine gameplay acceptance, not server reachability.

**Current direction (13 October 2026):** enjoyable desktop play using genuinely free local AI; one responsive web client. 3D/Unreal is postponed indefinitely. This branch starts from the latest PR #6 desktop corrections and retains #5/#4/#3. [Local runtime/model assessment](docs/local-ai.md), [test evidence](docs/local-ai-evidence.md), [desktop work](docs/plans/2026-10-13-desktop-narrative.md).

## Simulation handoff (historical milestones below)

**Package state:** Schema 108 / WORLDHIST-01A Stage 2 + opening history, mortality and cultivation realism
**Engine version:** 0.60.0
**Canonical opening database (never play/test in place):** `data/caerness.db`
**Live story day:** 0
**Historical simulation checkpoint:** `58ee22291d34bb1da59db951ca14dae233e71e8d`
**Current World Bible:** `canon/world_bible_current.docx`
**Current opening-world seed:** `game/seeds/Caerness_Initial_World_State_Seed_v1_4.json`
**Status:** focused WORLDHIST-01A Stage 2 acceptance passed; Schema 107 adds review fixes and FAMILY-02 sex resolution; Schema 108 adds opening family life and relationships, canon-anchored named mortality, and Veinborn/training realism (see `WORLDHIST01A_SCHEMA108_OPENING_HISTORY_MORTALITY_CULTIVATION_2026-09-23.md`); fresh Schema-108 integrated ONEYEAR acceptance is still pending.

> **Agents: read `AGENTS.md` first** — current product priority, feature-stack dependencies, owner rules and runbook.

This README is the authoritative engine handoff for anyone resuming development from this package. Older handoffs, acceptance reports and roadmaps remain in the repository as historical evidence, but **their schema numbers and “current” labels must not override this file**.

---

## 1. What Caerness is

Caerness is a persistent low-fantasy world simulation with a narrative camera inside it. Its governing design principle is:

> **The world exists and changes independently of the player. The player is the camera, not the centre of causality.**

The engine is intended to support long-running lives and world history across cultivation/martial practice, families, institutions, kingdoms, war, religion, commerce, underworld organizations, arts and patronage, travel, health, education, social relationships, succession and emergent historical change.

The simulation should not preserve institutions, characters or outcomes merely because they were prewritten or convenient. Named opening characters are not a privileged main cast. Background/professional people may become important and be promoted to higher resolution when causality demands it; important people may die, fail, decline or disappear. The same principle applies to organizations, settlements, businesses, sects, gangs, dynasties and other world entities.

---

## 2. Where development is RIGHT NOW

The live code in this package is **Schema 108**, built on the corrected Schema-104 TENYEAR-02 development baseline.

### Schema 104 baseline already accepted

Schema 104 produced the corrected unattended TENYEAR-02 benchmark from day 0 to day 3,650. That decade is **non-canon development evidence**, not the live campaign history. It proved broad multi-system operation and restart determinism at that checkpoint. The live development database was deliberately returned to a clean day-0 opening state after acceptance.

Important Schema-104 evidence is under `acceptance_artifacts/`, especially:

- `TENYEAR02_CORRECTED_ACCEPTANCE_2026-09-21.md`
- `TENYEAR02_CORRECTED_FINAL_SYSTEM_AUDIT_2026-09-21.json`
- `TENYEAR02_CORRECTED_ANNUAL_AUDIT_2026-09-21.json`
- `TENYEAR02_CORRECTED_YEAR9_YEAR10_REPLAY_2026-09-21.json`
- `TENYEAR02_POST_DECADE_STANDARD_REGRESSION_105_OF_105.json`

Do **not** replace `data/caerness.db` with a TENYEAR-02 output database. The decade run is evidence, not opening canon.

### WORLDHIST-01A Stage 1 — Schema 105: implemented

Stage 1 added the first shared world-history consequence layer:

**FAMILY-02**
- family/union mutation rejects prohibited known close-kin relationships;
- biological birth requires resolved demographic sex and a valid reproductive pairing;
- missing demographic information is not treated as permission to invent biology;
- family planning and birth mutation enforce these constraints at write time.

**HARM-01**
- introduced `harm_incidents` as the shared provenance-bearing harm authority;
- combat, duels, tournaments and war can project through one harm path;
- harm distinguishes controlled/accidental/hostile/lethal intent;
- persistent injuries create real health conditions rather than narration-only consequences;
- duplicate resolution of the same source is idempotent.

See `WORLDHIST01A_STAGE1_FAMILY_HARM_ACCEPTANCE_2026-09-22.md`.

### WORLDHIST-01A Stage 2 — Schema 106: implemented and focused-accepted

Stage 2 makes consequential events persist as **social and institutional history** rather than ending as isolated event rows.

**REL-02 — social memory**
- `relationship_history` stores causal relationship changes;
- interactions can alter familiarity, trust, respect, fear, resentment, obligation and professional confidence;
- repeated materially identical refusals can suppress pathological immediate re-approach without eliminating agency;
- materially different proposals remain possible.

**ORGPRESS-01 — institutional pressure projection**
- concrete events can accumulate organization pressure;
- causal factions can form on the existing organization-agency substrate;
- a public defeat of an institutional head by a member can create leadership-legitimacy pressure;
- the duel itself does not automatically depose the incumbent.

**SUCCESSION-02 — authority transitions**
- `leadership_transition_cases` records succession/authority-transition history;
- death of a named incumbent vacates the authority slot and creates pressure with provenance;
- generic institutions may select only from living, already-existing qualified members;
- close contests remain unresolved and can form candidate factions rather than selecting randomly;
- political succession remains owned by the polity/dynasty system;
- underworld succession remains owned by the underworld system;
- the generic bridge synchronizes with those domain-specific owners rather than stealing authority from them;
- no replacement adult is invented merely to fill a vacancy.

See `WORLDHIST01A_STAGE2_SOCIAL_ORGPRESS_SUCCESSION_ACCEPTANCE_2026-09-22.md`.

### Schema 107 — review fixes and FAMILY-02 sex resolution

- correctness fixes to the Stage 1/2 code (re-approach blocking, war casualties, kinship prohibitions, duel harm events, succession savepoints);
- `connect()` closes on leaving its `with` block (Windows could not delete or replace open databases);
- every named character has a resolved demographic sex, in the order canon text → canon rule (male-only Mantle) → given name → seeded roll; newborns and characters created during play are resolved at creation (`engine/demographic_sex.py`, migration 107).

See `WORLDHIST01A_SCHEMA107_REVIEW_FIXES_AND_SEX_RESOLUTION_2026-09-23.md`.

### Schema 108 — opening history, mortality and cultivation realism

- **Opening resolution is not run-time invention** (DESIGN §15.1). Canon's nulls mean *unknown*: the opening world now has lived family history and relationships, resolved once and deterministically, never over canon, with each fact's basis recorded (`engine/opening_family.py`).
- Named adults have marriages, widowhood, remarriage and latent children, with canon-grounded group differences. Living spouses are revealed as low-attention persons. Opening relationships come from kin, teaching lines and shared institutions, backdated. Relationships have a real `started_day`.
- During a run, single named adults can marry into the unnamed population at the same rates. Heirs come from family: a surviving spouse and adult children claim households, lineage houses weigh kinship, and latent adult children are revealed only when needed.
- Named mortality follows a canon-fitted Gompertz-Makeham curve (Sixth median ~111, matching the Sixth census). Childhood mortality is premodern and shared by every population model, scaled by a family's actual means and access to care.
- Veinborn (Open-Core) is not the same as martial artist. Staging follows canon anchors and is sex-weighted. Newborns inherit a Core. Any Veinborn may take up training at plausible rates. Aptitudes are bell-shaped, and revealed people get the same within-Stage calibration as canon people.
- **ROUTES-01** (`engine/route_network.py`): the travel graph held only 11 routes, and 121 of 133 places, including every outer kingdom, were unreachable. This silently blocked trade, travel, news and war. There are now 132 routes at canon caravan times, each with its basis and certainty. The very old continental map is used only where the text is silent.
- Conflict channels now see their frontier's issue pressure. An issue-kind naming mismatch had kept it at 0. The Empire–Thornward channel has its Thornward endpoint, and canon's Thornward–Stormhollow southern ridges frontier exists.

See `WORLDHIST01A_SCHEMA108_OPENING_HISTORY_MORTALITY_CULTIVATION_2026-09-23.md`.

### Current gate status

The packaged database is a clean opening state:

- schema: **108**
- story day: **0**
- engine version: **0.60.0**
- background person profiles: **2,272**
- professional profiles: **100**
- `relationship_history`: **0** at opening by design (history arises from play)
- opening relationships: **3,288** (canon kin, teaching lines and shared institutions, backdated; schema 108)
- travel routes: **132**, every place reachable (ROUTES-01); conflict channels: **6**
- opening unions: **267** active; revealed opening spouses: **264**; latent (undescribed) children alive: **585**
- `leadership_transition_cases`: **0** at opening by design
- SQLite integrity: verified in the parent checkpoint
- foreign-key violations: 0 in the parent checkpoint
- acceptance epoch: `ONEYEAR_WORLDHIST01A_SCHEMA108` = **pending**
- named characters with unresolved demographic sex: **0**

The zero history rows at day 0 are intentional: world history should arise from simulation, not be fabricated to satisfy coverage counters.

---

## 3. What is NOT finished yet

Do not interpret Schema 106 as a completed WORLDHIST pass or as a new accepted decade baseline.

The current Stage-2 acceptance explicitly does **not** yet claim:

- broad **EMERGENCE-02** world-historical emergence;
- full clan/sect feud strategy and historical propagation;
- war-origin recalibration across the new history layer;
- city/place development and decline history;
- religion/cultural change as a world-history system;
- broader underworld-to-city/world consequences;
- the remaining cross-domain historical consequences needed for a genuinely full world chronicle;
- final full-schema regression and a fresh integrated Schema-106 ONEYEAR acceptance;
- a fresh Schema-106 TENYEAR acceptance.

The next work should therefore continue **WORLDHIST-01A from the Schema-106 branch**, then run the full regression/ONEYEAR gate once the intended tranche is complete. Only after that gate passes should another ten-year acceptance be treated as current.

Do not “make counters nonzero” by inventing events. A quiet domain is acceptable when the world state provides no causal trigger. The test is whether a system can act when causality requires it, not whether every system fires every year.

---

## 4. Canon, runtime truth and evidence — keep these separate

Caerness has three different kinds of authoritative material. Mixing them is a major source of errors.

### A. Setting canon

`canon/world_bible_current.docx`

This is the current prose World Bible: cultures, polities, institutions, cultivation metaphysics, geography, religion, social structures and other setting rules. Treat it as the primary human-readable setting source.

`canon/core_seed_v1.json`, `core_seed_v2.json`, `core_seed_v3.json`

These are historical/bootstrap canon seed layers. They are retained because the project evolved through them. Do not assume the oldest seed is the current complete opening state.

### B. Current opening simulation state

`game/seeds/Caerness_Initial_World_State_Seed_v1_4.json`

This is the current versioned opening-world seed used by the present development baseline.

`data/caerness.db`

This is the runnable SQLite opening database for the packaged checkpoint. It is at day 0. Treat this as the current persisted simulation state supplied with the package.

`engine/schema.sql`

This is the current database schema definition. The runtime reports Schema 108.

### C. Development evidence

`acceptance_artifacts/`, `diagnostics/`, and the many root-level `*_ACCEPTANCE*.md`, audit and handoff files contain test evidence and historical development records.

These files can prove that a past branch or schema behaved in a particular way. They **do not automatically become current canon or current runtime state**.

In particular, the Schema-104 TENYEAR-02 result is non-canon development evidence. It should be used to find regressions and calibrate plausibility, not imported as the day-0 world.

---

## 5. Repository map — what everything is for

### `.git/`

The actual Git repository is included. Use it to inspect history, diffs and parent checkpoints. The engine code checkpoint packaged here is `58ee22291d34bb1da59db951ca14dae233e71e8d` before this handoff-documentation refresh.

### `README.md`

This file. It should always describe the **actual current packaged checkpoint**. If future engine work changes schema, current gates or the continuation point, update this README before packaging.

### `run.py`

Main command-line entry point. It exposes campaign/bootstrap controls, simulation advancement, inspection, health, households, religion, ecology, politics, education, combat, information, model bridges, coverage and many other engine functions.

Useful first checks:

```bash
python run.py status
python run.py migration-status
python run.py coverage-status
python run.py campaign-status
```

Use `python run.py -h` to inspect the full command surface.

### `engine/`

The authoritative Python simulation engine and database schema.

Major areas include:

- `simulation.py`, `world.py`, `turns.py`, `timeskip.py` — world clock, scheduling and time advancement;
- `db.py`, `schema.sql`, `process_registry.py`, `resolution_controller.py` — persistence, schema, process ownership and resolution control;
- `opening_world_state.py`, `current_seed.py`, `bootstrap.py`, `activation.py` — opening-state import and activation;
- `background_population.py`, `person_ecology.py`, `population_reconciliation.py`, `scale.py`, `presence.py` — population scale, background persons and low-resolution presence;
- `cultivation.py`, `elixir.py`, `teaching_ecology.py` — cultivation progression, physiology/resources and teaching ecology;
- `combat.py`, `battle_tactics.py`, `battlefield.py`, `harm.py` — duels, battles, tactics and shared physical consequences;
- `war.py`, `logistics.py`, `conflict.py`, `conflict_geometry.py`, `territorial_events.py` — war/campaign generation, logistics and conflict causality;
- `politics.py`, `polity_agency.py`, `organization_agency.py`, `organization_lifecycle.py`, `organization_needs.py`, `succession.py` — state/institution agency, lifecycle, pressures and succession;
- `relationships.py`, `interactions.py`, `reputation.py`, `motives.py`, `adaptive_planning.py` — person-to-person social state and decision drivers;
- `household_life.py`, `civilian.py`, `civilian_life.py`, `health.py`, `psych.py` — family, ordinary life, health, disability and psychological consequence systems;
- `business.py`, `merchant.py`, `merchant_taxonomy.py`, `aggregate_trade.py`, `growth.py`, `craft.py`, `agriculture.py`, `patronage.py`, `spectacle.py` — economy, trade, production, merchant institutions, regional growth, patronage and culture-facing activity;
- `underworld.py`, `underworld_decisions.py`, `underworld_rebuild.py`, `underworld_medicine.py` — gangs/mafia-family ecology, rackets, decisions and underworld consequences;
- `hollow.py` — Hollow/Grand Coven-specific systems;
- `religion.py`, `belief.py` — religious institutions, affiliation, observance and belief/evidence handling;
- `education.py`, `competence.py`, `expertise.py`, `profession_runtime.py`, `career_reach.py`, `role_experience.py` — training, professions, skill and career development;
- `ecology.py`, `civil_calendar.py`, `groundbinding.py` — environment, travel, calendar/geographic constraints;
- `information.py`, `discovery.py`, `decision_runtime.py`, `decisions.py`, `agency.py`, `opportunity.py`, `seeking.py`, `service_fulfillment.py` — information-bounded agency and autonomous action;
- `emergence.py`, `crystallization.py`, `attention.py`, `continuity.py` — resolution-tier movement, emergent importance, naming/crystallization and continuity;
- `player.py`, `model_gateway.py`, `local_model.py`, `router.py`, `embodiment.py` — player camera, narration/model integration and interface mediation;
- `mobile_runtime.py`, `mobile_server.py` — the shared desktop/mobile browser runtime (module names retained for compatibility).

Do not create a second authority for a concept if an existing module already owns it. Several regressions in prior work came from two systems both trying to resolve the same death, succession, movement or consequence.

### `tests/`

Regression and acceptance tests for current and historical subsystems. This folder is part of the runnable development tree, not optional documentation.

For the current Stage-2 work, the most relevant focused tests are:

```text
tests/rel02_interaction_memory_test.py
tests/orgpress_succession02_test.py
tests/interaction_test.py
tests/rel01_directed_relationships_test.py
tests/orgagency_conflict01_test.py
tests/orglife01_country_lifecycle_test.py
tests/family02_feasibility_firewall_test.py
tests/harm01_shared_consequence_test.py
tests/war01_campaign_battle_world_consequences_test.py
```

A focused pass is not equivalent to the final full regression gate.

### `data/`

Contains the packaged runnable SQLite database:

`data/caerness.db`

Before destructive work, preserve or copy it. Normal project practice is to keep the live opening baseline recoverable and to use separate temporary databases for simulations/tests where possible.

### `game/`

Game-facing state and versioned world seeds.

`game/seeds/` contains the evolving current-world seed files. v1.4 is current for this checkpoint.

`game/campaign_01/` contains campaign-specific material rather than universal setting canon.

### `canon/`

World Bible and core canonical seed material. This is where the setting source lives; it is not a diagnostics folder.

### `diagnostics/`

Diagnostic runners, calibration scripts and captured results from prior runs. Use these for targeted simulation probes, performance checks, follow-character biographies, one-year runs and subsystem audits.

Diagnostic outputs are evidence. They are not automatically the live world state.

### `acceptance_artifacts/`

Load-bearing acceptance evidence for major gates. `acceptance_artifacts/README_CURRENT.md` summarizes what is current and what is historical.

### `mobile/`

Shared responsive desktop/mobile browser assets (directory name retained for compatibility): HTML, JavaScript, styles, manifest and service worker.

### `docs/`

Supporting documentation. `docs/history/README_LEGACY_THROUGH_SCHEMA80.md` preserves the previous root README so historical notes were not lost when this current handoff README replaced it.

### `benchmarks/`

Performance/benchmark material. Use it for comparative runtime evidence rather than setting truth.

### Root-level Markdown/JSON/TXT reports

The repository intentionally retains many milestone handoffs, audit reports, roadmaps and acceptance files from earlier versions. Their names usually identify the schema/version/tranche they belonged to.

They are useful historical evidence, but **the newest schema number is not determined by whichever old file happens to say “CURRENT” in its title**. Start with this README, the live DB/schema and the newest matching acceptance document.

---

## 6. The current world-simulation architecture in plain terms

Caerness uses multiple simulation resolutions rather than individually simulating every human every day.

Broadly:

1. **Aggregate/background state** represents populations and pressures that do not need individual identity yet.
2. **Professional/background persons** allow causal individual activity without immediately crystallizing everyone into a fully tracked named character.
3. **Named/lightweight or crystallized actors** appear when the world needs durable identity, relationships, biography or player-facing significance.
4. Entities can move upward in resolution when their actions matter. Importance is causal, not predetermined.
5. High-resolution people are not protected from death or decline; lower-resolution people are not forbidden from becoming historically important.

The World Bible’s population and cultivation distributions are ecological anchors, not hard runtime quotas. War, recruitment, institutional collapse, prosperity and migration may push the world away from the opening proportions. If similar conditions later return, ordinary causal dynamics should tend back toward similar ranges rather than being forcibly reset.

Early cultivation progression is more Vessel-dominated; later progression becomes increasingly Realization-dominated. The engine should preserve that distinction rather than treating all stage advancement as the same generic XP process.

---

## 7. Development rules that must not regress

These are recurring project constraints that have caused errors when lost between sessions:

1. **Persist the actual runnable tree.** After substantial engine work, checkpoint the source, tests, schema/migrations, current DB/seed assets and relevant evidence — not only a prose handoff.
2. **Verify the package independently after zipping.** Extract it fresh and check ZIP integrity, Git state, schema, SQLite integrity/FKs and appropriate tests before calling it safe.
3. **Do not privilege the opening named cast.** Generated/promoted people and pre-named people follow the same causal rules.
4. **Missing ordinary biography is usually incomplete state, not mysterious canon.** Resolve missing age/birth information when the simulation requires it unless genuine uncertainty is part of the setting.
5. **No plot armor.** The rule applies to everyone, from low-resolution people through rulers and apex martial figures.
6. **No forced institutional preservation.** Successors, recruits, teachers, businesses, gangs, towns and sects should emerge or fail causally.
7. **Do not invent a new role/institution/entity every time a need appears.** Reuse existing structures when they plausibly satisfy the need; create new ones only when causal conditions support formation.
8. **Keep ownership boundaries clear.** Political succession, underworld succession, generic institutional succession, health/death, movement and other domains must not double-resolve the same event.
9. **World history must include ordinary consequences.** Wars and apex duels matter, but so do merchant expansion, patronage, city improvement/decline, gang predation, religious change, art movement, family succession, institutional fracture and local development.
10. **Silence is allowed.** A domain need not manufacture an event merely to demonstrate that its code exists.

---

## 8. How to resume work safely

From a fresh extraction:

```bash
python run.py status
python run.py migration-status
```

Confirm that the reported engine version is 0.60.0, schema is 108 and story day is 0 before treating the package as the current baseline.

Inspect Git history:

```bash
git log --oneline --decorate -12
git status
```

The current Stage-2 code commit is:

```text
58ee22291d34bb1da59db951ca14dae233e71e8d
```

Its parent stages are:

```text
58ee222  WORLDHIST-01A Stage 2: social memory / org pressure / succession
c3b5027  WORLDHIST-01A Stage 1: FAMILY-02 / HARM-01
6f42fda  corrected Schema-104 TENYEAR-02 accepted baseline
```

Read these before changing the Stage-2 systems:

```text
WORLDHIST01A_STAGE1_FAMILY_HARM_ACCEPTANCE_2026-09-22.md
WORLDHIST01A_STAGE2_SOCIAL_ORGPRESS_SUCCESSION_ACCEPTANCE_2026-09-22.md
acceptance_artifacts/README_CURRENT.md
```

Then continue WORLDHIST-01A rather than branching from an older schema-104 acceptance package.

---

## 9. Acceptance hierarchy

Use these labels carefully:

- **Focused acceptance:** targeted tests for the newly changed subsystem pass.
- **Regression acceptance:** wider existing tests pass against the new code.
- **ONEYEAR acceptance:** a fresh integrated year demonstrates that the full current schema runs coherently and satisfies its coverage/consistency gate.
- **TENYEAR acceptance:** a fresh integrated decade demonstrates long-horizon plausibility, persistence and restart behavior for the current schema.

Schema 106 currently has **focused Stage-2 acceptance**, not a completed new ONEYEAR/TENYEAR gate.

Do not say “the ten-year test passes on Schema 106” merely because the package contains accepted Schema-104 decade evidence.

---

## 10. Packaging rule for the next checkpoint

When the next major tranche is complete:

1. ensure the live source tree contains the actual changes;
2. ensure tests, schema, DB and seed files are synchronized;
3. update this README’s schema/stage/current-status sections;
4. preserve acceptance/diagnostic evidence;
5. commit the working tree;
6. create the ZIP from the real repository root, including `.git`;
7. extract the ZIP into a new directory;
8. verify archive integrity, Git cleanliness, compile/import health, schema, DB day, SQLite integrity and foreign keys;
9. run the required focused/full acceptance tests from the extracted copy;
10. record the ZIP SHA-256 and verification result.

A prose state-capture or handoff document is **not** a substitute for the runnable tree.

---

## 11. Immediate continuation point

**Continue from Schema 106 / WORLDHIST-01A Stage 2.**

The core question for the next tranche is no longer “can an event occur?” but increasingly:

> **Does the event leave the right durable history in people, institutions, places and the wider world, and can that history causally change what happens next?**

Stage 1 established family feasibility and shared harm. Stage 2 established social memory, organization pressure and authority-transition history. The remaining WORLDHIST work should extend that same provenance-driven causal principle across the other major world-history domains before a new integrated ONEYEAR/TENYEAR gate is claimed.
