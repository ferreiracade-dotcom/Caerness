# Caerness v0.60.0 — COVERAGE-01 World-Bible Coverage / Resolution Gate Acceptance

**Date:** 17 September 2026  
**Engine:** v0.60.0  
**Schema:** 69  
**Status:** **ACCEPTED — coverage gate passed; one-year unattended run is next.**

## Purpose

COVERAGE-01 is the stop/gate between feature-slice implementation and the integrated ordinary one-year unattended run. It does **not** require every possible rare event to already be happening at opening. It requires every major World Bible domain to have the correct kind of owner, an ordinary opening substrate where one should exist, an autonomous process where autonomy is required, cross-system connections, and a valid resolution story.

The gate now distinguishes:

- opening population/substrate genuinely missing;
- conditional domain currently dormant because no trigger exists;
- populated but no eligible work;
- eligible work;
- production process not wired;
- protected/semantic-open material;
- non-required player boundary in an unattended world.

It no longer treats “no murder today”, “no shipment already in transit”, or “no current lawsuit” as proof that the underlying subsystem is missing.

## Schema 69

Schema 69 adds only coverage metadata:

- `coverage_registry.population_policy`;
- `coverage_registry.process_keys_json`;
- engine metadata for the COVERAGE-01 gate.

Migration from the actual schema-68 INTEGRATION-01 checkpoint creates **no** clinics, fields, courts, cases, criminal organizations, latent people, or historical events. Those are opening-world activation concerns, not save migration.

Verified schema-68 -> 69 migration:

- health care sites: `0 -> 0`;
- agriculture fields: `0 -> 0`;
- law jurisdictions: `0 -> 0`;
- law cases: `0 -> 0`;
- emergent institution candidates: `0`;
- latent entities: `0`;
- `PRAGMA integrity_check = ok`;
- foreign-key violations: `0`.

## Opening-world activation closure

`current_canon_activation_version` advances from **11 to 12**.

The actual current seed plus ordinary activation now creates shallow structural substrate for three mechanisms that INTEGRATION-01 intentionally added without retroactively populating old campaigns:

### Health

Nine commercially active hubs receive structural ordinary-care networks. These represent latent doctors, surgeons, attendants, beds and ordinary treatment capacity. They do **not** create named physicians or claim canon names.

A structural provider pool can actually treat ordinary conditions through the real care queue. Treatment persists with `provider_actor_id = NULL` and explicit provenance that a structural/latent provider pool supplied the care. If that provider later becomes causally important, the normal resolution system can crystallize a person.

### Agriculture

Nine ordinary-grain market locations receive aggregate grain-hinterland enterprises and physical fields. These are anonymous regional farm capacity, not named canon estates.

They use the existing AGRI-01 owner:

`ecology/weather + labor + disruption -> physical harvest -> commercial_stock -> market availability -> food stress / growth response`.

### Law

Seven active opening polities receive structural ordinary jurisdictions, ordinary rule families and ordinary court/docket capacity. These do not invent named judges or settle constitutional details that the World Bible leaves open.

The ordinary law layer is therefore available at opening while local/charter/institution-specific law can still override it where explicitly instantiated.

Activation is idempotent: calling activation a second time creates `0` additional opening health sites, fields, jurisdictions, offices or rules.

## Corrected coverage semantics

Important telemetry corrections include:

- **Merchant/transport:** opening population is the merchant/business substrate, not the transient count of shipments currently moving.
- **Crime organizations:** coverage now reads the concrete v0.60 `underworld_organizations` owner rather than retired legacy aggregate profiles.
- **Smuggling:** a lack of an active smuggling shipment is conditional dormancy, not missing criminal infrastructure.
- **Assassination:** the active Reckoning and Cormorants provide opening targeted-violence substrate without forcing an opening assassination event.
- **Underworld medicine:** coverage reads concrete underworld organizations plus actual health capacity rather than the retired pre-v0.60 profile owner.
- **Undertow compacts:** zero active compact agreements is legal conditional dormancy; the world is not required to start with one already signed.

## Production scheduler ownership

Autonomous coverage rows now declare the production process keys expected to own their progression. The gate validates those keys against the actual scheduler process vocabulary.

Current production scheduler owners include:

`resolution, world, ecology, agriculture, logistics, merchant, craft, civilian, growth, underworld, underworld_medicine, law, war, groundbinding, health, psychology, hollow, religion, politics, education, cultivation, tournament, spectacle`.

The ARCH-01 functional parity/restart/cancellation suite remains green after COVERAGE-01.

## Opening coverage gate result

On a fresh current-canon seed + activation-v12 opening:

- required domains: **50**;
- required failures: **0**;
- gate: **PASS**.

Observed coverage-state distribution:

- eligible: **25**;
- populated / no eligible work: **15**;
- populated active without a separate eligibility query: **9**;
- conditional dormant: **1**;
- non-required missing population: **1** (`player_state`, correct for an unattended opening);
- protected open: **1** (Part Twenty-Five boundary).

No required row is in:

- missing mechanism;
- missing opening population;
- missing autonomous process.

The fact that some domains remain labelled `PARTIAL` is not silently converted into “complete canon simulation”. It means their current ordinary-world owner is sufficient for integrated simulation while richer specialist semantics remain possible later. Protected/open material remains protected rather than being filled with guesses.

## World Bible pass

The coverage matrix still spans Parts Zero through Twenty-Five:

- Part 0 — canon/identity/firewall;
- Parts 1–2 — geography, sovereignty, population, military/current ecology, cultivation;
- Parts 3–10 — Hearth/Churn institutions, transmission, Concord/Undertow/Unsworn/Hollow/Long Road, challenge/tournament;
- Part 11 — material economy, merchant transport, credit, craft/production, appraisal;
- Part 12 — religion;
- Parts 13–19 — polity government/succession/territory/war;
- Part 20 — cities/routes/travel/regional variation;
- Part 21 — households, unions, births, dependency, service/migration, health, material life;
- Part 22 — nightlife, gambling, prizefighting, gangs/crime families, smuggling, policing, privacy, targeted violence, underworld medicine;
- Part 23 — culture, news, reputation/public memory;
- Part 24 — living registry, agency, clock, crystallization/down-resolution/player boundary;
- Part 25 — protected open material.

No World Bible Part is absent from the matrix.

## RESOLUTION-01 closure

COVERAGE-01 closes the main real gap found in the existing two-way resolution controller.

### Latent person -> persistent tracked person

Previously a one-person latent entity could be labelled `TRACKED` in `latent_resolution_profiles` without materializing a persistent actor.

Now, when a one-person latent person crosses the TRACKED significance threshold:

1. a deterministic unique name is generated only if no grounded name exists;
2. a persistent character actor is created;
3. the existing location and latent constraints/history are carried forward;
4. a life profile, health profile, presence profile, ordinary drives and cultivation state are instantiated;
5. relevant professional competence is instantiated from the known archetype rather than omniscient skill;
6. continuity stores the latent source context and significance evidence;
7. resolution becomes TRACKED / simulation tier STRATEGIC;
8. the latent source row is marked crystallized and points to the persistent actor;
9. if the latent person was the owner of a real enterprise, that enterprise is attached to the actor and merchant authority is created.

The acceptance scenario proves an ordinary latent merchant becomes regionally significant and materializes as a persistent named merchant without a fabricated prior biography.

### Emergent organization -> concrete tracked organization

An evidence-backed institution candidate with a grounded/proposed name may now auto-crystallize once it is `eligible`.

For a criminal organization this additionally creates the concrete v0.60 `underworld_organizations` row, so a new gang does not stop at a generic institution record.

Acceptance proof:

`repeated joint extortion + shared treasury evidence -> eligible “Ash Knives” candidate -> persistent institution -> concrete gang owner`.

Unnamed eligible candidates remain eligible. The engine does **not** invent a brand/name merely to satisfy resolution.

### Safe down-resolution

A tracked actor whose objective significance falls and stays low is demoted only after hysteresis.

Acceptance proves:

- TRACKED merchant -> two sustained low-significance reviews -> STRUCTURAL;
- simulation tier becomes DORMANT and cadence lengthens;
- actor identity remains;
- continuity core remains byte-identical;
- directional relationship and obligation remain;
- enterprise ownership/history remains;
- no deletion or narrative amnesia occurs.

Deceased/historical people are now scored as zero-significance for autonomous resolution, allowing them to fall toward cheap structural persistence instead of remaining expensive merely because an old active-tier flag survived death.

## Thirty-day integrated preflight

A fresh opening world was advanced for 30 days through the production scheduler. This is **not** the one-year acceptance run; it is only a COVERAGE-01 preflight.

Results:

- opening coverage gate: PASS;
- current day: `0 -> 30`;
- all production process families logged executions/checkpoints;
- SQLite integrity: `ok`;
- foreign-key violations: `0`;
- coverage gate after preflight: PASS.

No harvest, lawsuit or treatment happened merely because those owners exist. This is correct: opening structural capacity is not a scripted event generator.

## Regression state

Green after COVERAGE-01:

- COVERAGE-01 acceptance;
- INTEGRATION-01;
- WAR-01;
- GROWTH-01;
- CRAFT-01;
- MERCHANT-01;
- DEC-01;
- BELIEF-01;
- PRES-01;
- REL-01;
- EVENTS-01;
- ECON-01;
- v0.60 Phase 2A;
- v0.60 underworld rebuild;
- ARCH-01 functional parity/restart/cancellation;
- information/privacy;
- player/action path;
- decision path;
- interaction path;
- model gateway;
- dormant-simulation smoke;
- v0.56 cultivation regression.

## Gate sequencing correction

`coverage_gate()` and `ten_year_gate()` are now intentionally different.

After COVERAGE-01:

- **coverage gate: PASS**;
- **ten-year gate: FAIL/CLOSED**, because no accepted integrated one-year unattended run has yet been recorded.

The decade gate now requires `one_year_unattended_acceptance` to be explicitly accepted in addition to coverage passing. This prevents the engine or a later agent from skipping the next milestone by mistake.

## Decision

**COVERAGE-01 accepted.**

The engine is now permitted to begin **ONEYEAR-01 — the integrated ordinary one-year unattended run**.

It is **not** yet permitted to begin the ten-year run.
