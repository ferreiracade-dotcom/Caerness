# v0.26.1 Closure Note

The review below was written against v0.25.0 and is preserved as the finding record. Its blocking recommendations have now been implemented in v0.26.1. See `AUDIT_v0_26_INTEGRATION_AND_SCALE.md`, `V1_RC1_READINESS.md`, and the closed `V1_CANDIDATE_CHECKLIST.md`. The current recommendation is **READY TO CUT v1.0-RC1 FROM v0.26.1**.

---

# Caerness Engine — Final Whole-Engine Review Toward v1.0

Review baseline: **v0.25.0**  
Scope: architecture, implementation depth, cross-system ownership, player-facing usability, upgrade safety, testing, and the 120-year stress harness.

## Executive verdict

**The simulation architecture is mature enough for a v1.0 candidate, but v0.25.0 should not itself be relabeled v1.0-RC without a short pre-RC hardening pass.**

The remaining work is no longer another world-simulation domain. The core systems are present and the cumulative suite passes. The remaining blockers are mostly productization, campaign bootstrap, persistence safety, and ownership cleanup.

Recommended next release: **v0.26 / v1.0-preRC — Integration & Usability Hardening**. After those blockers are closed, cut **v1.0-RC1** and run the same cumulative/adversarial/long-run suite against a realistic seeded Caerness campaign.

## Verification performed in this review

- Full cumulative test suite: **PASS** (`python tests/run_all.py`).
- Python compile check: **PASS** (`python -m compileall`).
- CLI parser/help construction: **PASS**.
- Current engine size: about **20.8k lines** across engine Python, schema, and CLI entry point.
- Schema size: **199 tables**.
- CLI surface: **187 subcommands**.
- Mobile HTTP surface: roughly **11 route handlers**, centered on play/runtime/model/backup rather than world administration.
- Canon index after clean reset: **160 chunks**.
- Clean package restored after review: day 0, no actors, no campaign events.

## v1.0 blockers

### B1 — There is no production Caerness campaign bootstrap

A clean database intentionally contains no actors, polities, routes, households, institutions, demographic population, or player character. `seed-demo` creates explicitly non-canon demonstration entities rather than a playable canonical starting world.

That is correct for engine development, but it conflicts with the engine's own central premise that **the world is already alive before the player enters it**. A normal player should not need to use dozens of CLI commands to instantiate the setting manually.

**Required before RC:** add a versioned campaign-bootstrap/seed pipeline that converts accepted World Bible material plus explicit campaign-start choices into authoritative campaign state. It should be idempotent, provenance-aware, and distinguish canon seeds from campaign inventions. The seed does not need to instantiate every person in the Bible; it should create the high-value places, institutions, shallow named registry, aggregate populations, and latent pools needed for an inhabited starting world.

### B2 — The phone-first UI is far behind the engine

The mobile runtime can play scenes, show Matters/World/You, handle model referral, runtime settings, interrupt, and backups. But most of the v0.16–v0.25 simulation cannot be inspected or configured through it.

The mismatch is now extreme: **187 CLI subcommands versus about 11 mobile HTTP route handlers**. Important domains such as households, health, business, religion, ecology, politics, education, succession, and stress diagnostics are not meaningfully exposed in the phone UI.

There are also stale runtime labels in `engine/mobile_server.py`: `CaernessMobile/0.8` and console text identifying the mobile UI as `v0.15.1`.

**Required before RC:** do not reproduce all 187 commands in the UI. Add a coherent administration/reference layer: campaign setup, character sheet, household, health, affiliations/institutions, travel/map state, important political state, education/transmission, save/restore, and diagnostics. Fix version labels and expose engine version dynamically.

### B3 — The test suite uses the live package database path and is destructive

`engine/db.py` has a single fixed `DB_PATH`, and many tests call `reset_db()`. Running the cumulative suite against an installed campaign can therefore wipe or replace the user's active database.

This is acceptable in a disposable packaging directory but is not safe for a v1.0 tool a user may run locally.

**Required before RC:** support database-path injection (environment variable, connection factory, or test fixture), and move all automated tests to temporary databases. Add a guard that refuses destructive test/reset operations against a non-test campaign unless explicitly confirmed/backed up.

### B4 — Upgrade/migration safety is not yet a first-class system

`init_db()` runs the latest `CREATE TABLE IF NOT EXISTS` schema and one broadly named `_migrate_v13()` routine. The only explicit table-rebuild migration currently visible is the old `model_requests` provider constraint migration. There is no ordered schema-version migration registry and no regression matrix proving that a saved campaign from major historical baselines upgrades safely to v0.25.

Because `CREATE TABLE IF NOT EXISTS` does not alter existing tables, future changes to columns/check constraints/index semantics are a real save-compatibility risk.

**Required before RC:** introduce an ordered schema migration system keyed by stored schema version, backup automatically before migration, and test upgrades from representative old snapshots (at least v0.15.1, v0.19.1, v0.20.1, v0.24, current).

## High-priority pre-RC hardening

### H1 — Formalize mirrored ownership fields and invariants

Several values exist in both authoritative and compatibility/convenience forms:

- `actors.status` and `actor_life_profiles.life_status`;
- `territorial_control` and `locations.political_owner`;
- `actors.current_location_id` and `player_state.current_location_id` for the camera actor;
- `household_migration_plans` and the generalized `travel_plans` while a migration is in transit.

These mirrors are mostly handled coherently today: death is centralized through `mark_actor_deceased`, politics writes the location mirror, scene/model paths resynchronize player location, and v0.22 links migration to travel. But v1.0 should document one owner for each pair and make contradiction checks explicit so later code cannot write the mirror directly.

**Recommendation:** authoritative owner + read-only mirror rule in `DESIGN.md`, helper functions for writes, and scanner assertions for divergence.

### H2 — The 120-year stress test is structurally good but too small to certify production scale

The stress fixture is valuable because it uses the real shared clock. It proves temporal and cross-system consistency. But its seeded world is intentionally miniature: a handful of characters/institutions, one enterprise, two locations, one polity, one program, one cultural institution, and aggregate town cohorts.

Therefore its sub-second/low-second timings do **not** establish performance for the actual intended world, nor do they establish emergent richness under many simultaneous processes.

**Required before RC1 sign-off:** run the harness on a realistic seed with hundreds of named/light actors, many institutions/enterprises/routes, multiple polities and claims, broad demographic cohorts, education pipelines, health state, and information networks. Run more than one deterministic seed/configuration. Record database growth and checkpoint latency.

### H3 — Historical crystallization is still primarily person-shaped

The continuity architecture says latent detail can later crystallize, but `engine/crystallization.py` currently prepares/applies `target_kind='actor'` and emits an actor biography shape. Later versions added persistent buildings, cultural objects, enterprises, institutions, political entities, and transmission assets, but the crystallizer did not become equivalently general.

This is not a simulation correctness blocker, because those entities can already exist persistently. It is a **historical reconstruction thin spot**: a long campaign can reconstruct a previously latent person more cleanly than a previously latent workshop, shrine, building, manuscript, institution, or local office.

**Recommendation:** either generalize crystallization to a small set of target families (`actor`, `institution`, `place/building`, `object/work`) or explicitly scope v1.0 crystallization to people and document the rest as post-1.0.

### H4 — The generic social/decision substrate remains thinner than the specialized domains

The old depth audit correctly identified generic goals, pressures, and relationships as thin. Later releases made the world much deeper by adding specialized state, but the base relationship table is still centered on broad stance/trust/obligation and generic goal/pressure vocabulary.

This may become the next narrative-quality bottleneck: the world can know a great deal about an actor's household, business, faith, health, politics, and education while the generic decision layer may not automatically derive enough domain-specific motives from those facts.

**Recommendation:** before RC, add a lightweight adapter layer that derives candidate goals/pressures from authoritative domain state rather than expanding another giant generic ontology. Domain systems should remain truth owners; the decision layer should consume their consequences.

### H5 — Test the scheduler under dense simultaneous due dates

The shared clock is one of the strongest parts of the engine. However, the long-run fixture primarily proves correctness under a modest number of due processes. A fully seeded world may have large numbers of monthly/quarterly/annual reviews landing on the same story day.

**Recommendation:** add one performance/adversarial fixture with thousands of due rows across several systems on the same day and verify deterministic ordering, no starvation, reasonable checkpoint time, and bounded transactions.

## Duplicated system ownership review

### Death / mortality — **mostly resolved**

Health is allowed to decide that a health condition becomes fatal, but it delegates the actual cross-system death transition to `household_life.mark_actor_deceased()`. That function updates actor/life/household state and cleans guardianship, service, dependencies, unions, and medical treatment. This is the correct pattern.

Remaining risk is the existence of two status fields. Make direct writes outside the death transition invalid by convention/test.

### Territory — **intentional mirror, needs hard invariant**

`territorial_control` is the proper political authority; `locations.political_owner` is a human-readable compatibility mirror still used by discovery/scene views. This is acceptable if only politics can write the mirror. Add divergence detection and preferably derive the display owner dynamically over time.

### Travel and household migration — **good post-v0.22 ownership split**

Household life owns the social decision to migrate. Ecology owns physical traversal once route geography is crystallized. The migration row links to travel state. This is a good division and should be retained.

### Careers, professional membership, certifications, education — **distinct but adjacent**

These are not direct duplicates: careers model long-run occupational position; memberships model standing within a profession; certifications record explicit credentials; education records training/transmission. The distinction is defensible. What is missing is a single player-facing view showing how they relate.

### Cultural institutions, ordinary institutions, enterprises, and religious institutions — **conceptually sound, UX-confusing**

All are represented through actor/institution identity plus specialized profiles. This avoids wholly separate entity universes, which is good. The player/admin UI should present one institution page with domain panels rather than expose these as unrelated database systems.

### Event/history ownership — **acceptable layered ledgers**

Domain histories (`political_history`, `education_history`, life events, cultural program instances, accounting history) preserve detailed provenance, while the global simulation event stream contains salient world-facing events. Do not collapse them into one table. The rule should be: domain ledger = authoritative detailed history; global event = attention/information-facing projection.

## Player-facing usability review

### Strong today

- Freeform play pipeline exists.
- Character-relative information and scene packets are mature.
- Matters/attention model avoids quest-HUD design.
- Local/external model routing is operational.
- Backup/restore exists.
- Story time is clearly separated from real-world absence.
- Camera succession now prevents protagonist death from ending the world.

### Missing before a comfortable v1.0

1. **New Campaign flow.** Choose/create player, starting place, initial social situation, and campaign seed without CLI archaeology.
2. **World initialization.** Seed the accepted Caerness state rather than the non-canon demo.
3. **Character sheet.** Health, relationships, household, competence, affiliations, education/transmission, possessions, current obligations.
4. **Institution page.** One combined view for a House/sect/company/religious/cultural/political institution.
5. **Travel view.** Current route, destination, estimated story-time arrival, stalls/closures, relevant known route information.
6. **Save management.** Named campaign slots, visible backup list, restore confirmation, export/import.
7. **Diagnostics page.** Engine version, canon status, DB/schema version, contradiction scan, pending model requests, last backup.
8. **Admin/setup separation.** The player should not see 187 low-level commands as the normal way to use the engine.

## 120-year stress-pass interpretation

### What the pass genuinely proves

- The real shared clock can run for century-scale story time.
- The tested demographic cohorts age and experience mortality without going negative.
- Businesses/culture/politics/education can keep resolving off-camera.
- Camera death can hand off without world reset.
- Political territory can diverge through configured causality.
- Historical actor crystallization remains traceable after decades.
- The tested cross-system invariants stay clean.
- The miniature database does not explode in size.

### What it does not yet prove

- Performance with the intended named population and institutional density.
- Narrative richness across 120 years rather than structural correctness.
- Multi-polity wars, repeated dynastic crises, large trade networks, or high route traffic under century-scale load.
- Dense information propagation across a large graph.
- Many concurrent health, education, household, and business processes.
- Randomized/multi-seed stability.
- Crash/restart behavior in the middle of a large advance transaction.
- Save migration across engine versions.

The correct conclusion is therefore **“long-horizon architecture validated”**, not “production-scale century simulation fully certified.”

## Lower-priority thin spots acceptable for v1.0 if documented

- Economy is intentionally constraint-oriented rather than a complete commodity/wage/macroeconomic simulator.
- Health does not need a pathological encyclopedia; the current condition/treatment framework is sufficient if content remains abstract and extensible.
- Politics can transform state structure without becoming a grand-strategy simulator.
- Religion correctly avoids inventing an exhaustive feast calendar.
- Education/transmission correctly models pipelines without simulating every lesson.
- Battles remain abstract tactical grammar rather than procedural real-world tactics.
- Crystallization can remain actor-first if the limitation is explicit.

These are design boundaries, not defects.

## Recommended pre-RC sequence

1. **Safe database/test isolation + schema migrations.** Protect user saves first.
2. **Canonical/campaign bootstrap.** Make a real starting Caerness.
3. **Mobile/admin integration pass.** Expose the systems players actually need to see.
4. **Ownership-invariant hardening.** Add mirror divergence checks and write helpers.
5. **Realistic-scale stress seed.** Re-run 20/40/120-year tests on an inhabited world, plus dense-due-date and multi-seed runs.
6. **Final docs/version cleanup.** Remove stale v0.15.1/0.8 runtime labels and document v1 scope boundaries.
7. Cut **v1.0-RC1**, then run the entire cumulative suite and candidate-scale stress suite unchanged.

## Candidate gate

I would call the engine **simulation-complete but not yet product-complete**.

The v1.0-RC gate should be:

- no destructive tests against a user campaign;
- versioned save migration with rollback backup;
- playable non-demo campaign bootstrap;
- phone UI capable of setup, play, inspection, saves, and diagnostics;
- mirror/ownership contradiction checks pass;
- full cumulative test suite passes;
- realistic seeded 20/40/120-year stress run passes with zero critical contradictions and acceptable DB growth/latency.

Once those conditions are met, there is no architectural reason to keep adding major simulation sections before v1.0.
