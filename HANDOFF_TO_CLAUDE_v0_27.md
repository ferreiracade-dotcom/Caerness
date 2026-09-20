# Caerness Engine v0.27 — Named Population Continuity
## Handoff from ChatGPT to Claude

### Important state-of-source note

The full persisted source tree available for handoff is the **verified v0.26.1 baseline**. During the attempted v0.27 session, design work, exploratory long-run runs, and proposed implementation details were discussed, but the actual v0.27 Python/schema/test source delta was **not preserved in the current runtime filesystem**. The `/mnt/data/Caerness_Engine_v0_27` directory that survived contains only copied documentation, not the modified `engine/`, `tests/`, `run.py`, database, or canon tree.

Therefore this handoff deliberately gives you:

1. the complete, verified v0.26.1 source as the code baseline;
2. the v0.27 architecture decisions that were settled with the user and Claude;
3. code-level facts re-verified directly against v0.26.1;
4. exploratory numbers from the attempted v0.27 session, clearly marked as **not certified until rerun**;
5. the exact work still required before v0.27 can be called complete.

Do **not** assume any v0.27 code described below already exists. Implement it from this baseline and rerun every criterion.

---

# 1. Problem v0.27 must solve

A fresh production bootstrap contains ~388 named characters plus millions of people in aggregate demographic cohorts. Across a century, the aggregate population remains healthy but the named register dies off because:

- `household_life.create_union()` exists but has no autonomous simulation caller;
- production bootstrap seeds zero `household_unions` and zero family plans;
- births work only for an already-established union carrying an `auto_children` family plan;
- `prepare_crystallization_context()` / validate / apply are driven only through CLI/admin/tests;
- there is no routine in-engine crystallization trigger.

The named layer therefore has no autonomous replenishment mechanism.

The design goal is **not** to make the world breed to preserve a quota. It is to keep the named/resolved layer healthy while preserving Caerness's existing causality rules.

---

# 2. Settled architecture

## Primary mechanism: demand-driven crystallization

Autonomous crystallization is the primary mechanism for sustaining **named resolution**.

A continuity controller may detect structural resolution deficits such as:

- `institution_generation`
- `regional_representation`
- `professional_pipeline`
- `lineage_context`
- `succession_pool`
- `general_resolution` only if implemented as a broad resolution-health trigger, never as a plot convenience

A vacancy does **not** mean "crystallize the new officeholder". It means the system may need to resolve people who plausibly already exist around that institution or lineage.

Newly crystallized people become participants/candidates. Existing succession/politics rules remain authoritative.

> Eligible does not mean appointed.

Where latent structure supports it, a succession vacancy should sometimes resolve **multiple plausible people**, not exactly one suspiciously perfect replacement.

## Secondary mechanism: autonomous NPC family continuity

Autonomous reproduction is secondary and exists to preserve organic continuity in known families/households.

Do **not** build a large courtship subsystem for v0.27. Minimum viable behavior is enough:

- living adult NPCs;
- explicit `family_formation_eligible`;
- no active union;
- sustained causal contact/shared location/context;
- no prohibited close kin;
- no player actor;
- politically significant House/lineage marriages require stronger pre-existing evidence such as positive relationship or established institutional/family connection;
- named-population shortage must never be part of the match score.

When a grounded NPC union is formed, assign a bounded family plan and let the **existing birth resolver** remain authoritative.

The revised philosophy should be:

> The engine never creates marriages to satisfy demographic or narrative quotas. Non-player actors may form unions through ordinary simulated life when persistent circumstances support them.

---

# 3. Cohort semantics — verified directly against v0.26.1 code

This gate has now been re-checked against the actual baseline source.

In `engine/bootstrap.py`:

- the complete Hearth midpoint population is seeded into `demographic_cohorts` by age-band shares;
- the original named registry is **not subtracted** from those demographic cohorts;
- separate stage-specific `latent_entities` **do subtract** already named stage members:

```python
remainder = max(1, int(count) - int(stage_named_counts.get(stage, 0)))
```

Therefore the correct semantics are:

> **`demographic_cohorts` are total population. Named actors are a resolution overlay.**

Consequences:

- autonomous crystallization must **not decrement demographic cohort population**;
- crystallization of staged Hearth cultivators should continue to consume the relevant stage-specific latent pool (`latent_entities.count_estimate`), as the existing crystallizer already does;
- do not introduce mixed semantics where only post-v0.27 names are subtracted from cohorts.

Add explicit metadata/migration documentation such as:

`population_layer_semantics = total_population_overlay`

Recommended hard checks:

- named living count must never exceed total aggregate population;
- a crystallized actor's recorded age-band provenance must match their birth age at crystallization;
- if demographic sex provenance is recorded, it must match the actor life profile;
- source geography must be plausible relative to the available cohort/location hierarchy;
- source Stage must match the latent pool consumed;
- latent source pool must have positive capacity before promotion.

These checks must be **enforceable**, not informational warnings only.

---

# 4. Mandatory crystallization provenance

Every autonomous crystallization must have a mandatory, queryable `coverage_reason`.

Do not leave this as optional JSON trivia. Prefer a real schema field or a reliably indexed/queryable authoritative record.

Recommended values:

- `institution_generation`
- `regional_representation`
- `professional_pipeline`
- `lineage_context`
- `succession_pool`
- `general_resolution`

Also record enough frozen provenance to audit distributional plausibility, for example:

- source demographic location / hierarchy;
- source age band;
- source demographic sex where applicable;
- source latent entity id and Stage;
- trigger institution/lineage/location ids;
- candidate-group id for multi-candidate succession-pool crystallizations;
- `coverage_reason` independently of the generated biography.

The reason explains **why this person was resolved now**. It must not become **why their past conveniently makes them perfect for the current plot**.

---

# 5. Continuity controller ownership

Implement a thin observer/trigger layer, e.g. `engine/named_continuity.py`.

It should own no duplicated world facts. It may:

- measure living named coverage;
- persist annual continuity snapshots;
- detect structural deficits;
- request autonomous crystallization;
- request evaluation of ordinary NPC family formation;
- expose next due day / process due functions to the shared clock.

It must **not** directly own:

- marriage truth;
- birth truth;
- office/succession truth;
- demographic truth;
- institution truth;
- health/death truth.

Those stay in their existing authoritative subsystems.

Recommended annual snapshot fields:

- story day/year;
- living/dead named totals;
- age-band and Stage distributions;
- births, deaths, unions since prior review;
- autonomous crystallizations by `coverage_reason`;
- institutional/lineage/regional coverage indicators;
- minimum living named count observed;
- floor breach duration for audit purposes;
- configured annual crystallization cap;
- any structural deficits detected.

The **audit floor judges the controller**. The floor must not become the controller's fiction.

Do not implement logic of the form "named count < X, therefore manufacture Y actors" as the primary causal trigger.

---

# 6. Shared-clock integration

`engine/simulation.py` currently composes authoritative due-day systems through `next_*_due_day` and `process_due_*` functions. Household life is already routed through `civilian.py`.

Add named continuity to the shared clock in the same pattern. Annual review is appropriate unless the implementation finds a better bounded cadence.

Keep deterministic behavior under the existing seeded RNG.

---

# 7. Full wiring required for every autonomous crystallization

The existing `apply_crystallization_proposal()` creates an actor, continuity core, historical anchors, optional cohort/career/relationships, resolution state, and decrements the latent pool.

For v0.27 autonomous promotion, every actor must additionally be guaranteed to have the normal post-v0.20/v0.26 runtime wiring expected of a live named character:

- `actors` row;
- `actor_life_profiles`;
- `actor_health_profiles`;
- `simulation_profiles`;
- valid current/home location;
- affiliation/cohort/institution context where claimed;
- `entity_resolution`/resolution tier;
- continuity core;
- immutable historical anchor(s);
- applied crystallization run + lineage;
- no dangling references.

If the existing crystallization apply path does not create all of those, extend the authoritative path rather than patching them in tests.

---

# 8. Distributional invariant must have teeth

This was explicitly requested by Claude and the user.

A contradiction scan should fail for at least:

- crystallized age does not fit recorded source age band;
- recorded sex provenance conflicts with life profile;
- source cohort/location is not plausibly related to actor location and no explicit migration/history basis exists;
- requested Stage conflicts with latent Stage consumed;
- latent pool had no positive count at promotion;
- missing `coverage_reason`;
- missing frozen anchor/provenance;
- missing life/health/simulation/resolution wiring;
- autonomous crystallization directly created an office/rulership/succession claim without the normal politics path.

Write adversarial tests that deliberately corrupt at least age-band provenance and Stage provenance and prove `stress_scan` catches them.

---

# 9. Succession firewall

Crystallization must never auto-fill office.

For `succession_pool` coverage:

- resolve surrounding plausible people;
- if latent structure supports it, sometimes resolve 2–3 candidates under one candidate-group id;
- do **not** create `succession_claims`, rulers, office assignments, or guaranteed eligibility merely because they were crystallized;
- normal politics/education/institution rules evaluate them afterward.

Add a test proving that a vacancy can trigger several resolved people while producing **zero automatic office assignment**.

---

# 10. Minimal autonomous union formation

Use existing `household_unions.metadata_json` for provenance if no new table is needed.

Suggested stored metadata:

```json
{
  "source": "named_continuity",
  "autonomous": true,
  "basis": ["shared_location", "positive_relationship", "same_institution"],
  "kin_distance_at_creation": 5
}
```

Important: if auditing close kin, measure kin distance **at union creation**. Later spouses may become graph-distance two through shared children; auditing the later graph can create false positives.

Do not auto-marry the player.

Do not infer politically consequential matches merely from both people belonging to Houses. Require stronger existing causal grounding.

Family plans should be conservative and grounded. Existing `_resolve_planned_births()` remains the birth authority.

---

# 11. No-replenishment calibration run

Before finalizing promotion caps, run the real production bootstrap with continuity replenishment disabled to at least 200 years and record:

- deaths per story year;
- worst rolling 1-year, 3-year, and 5-year death windows;
- named living curve every 5 years;
- Stage distribution of deaths.

Exploratory numbers reported during the attempted v0.27 session were:

- year 20: 388 living
- year 40: 388
- year 60: 382
- year 80: 172
- year 100: 10
- year 120: 1
- year 140 onward: 0
- worst 1-year deaths: 21
- worst 3-year deaths: 57
- worst 5-year deaths: 88

**These values are not certified in this handoff because the v0.27 source delta/test artifacts were not persisted. Rerun and treat the new run as authoritative.**

Use the measured mortality wave to set a bounded annual crystallization capacity. The cap must be high enough to recover from real clustered mortality, but a hard cap must still prevent instant mass biography generation.

---

# 12. 200-year acceptance test

Retain all shorter 20/40/120-year tests. Add a decisive **200-year production-bootstrap continuity test** because high-stage cultivators live long enough that 120 years does not fully test generational replacement.

The acceptance criteria are all mandatory:

1. Full legacy suite v0.7–v0.26.1 remains green.
2. Production bootstrap runs to 200 years without systemic failure.
3. Named living population never spends a sustained period below the audit floor.
4. Do not tune world behavior to the floor. The floor is an external test criterion.
5. Start with a provisional floor around 70% of the 388-person bootstrap (~272) unless the measured runs justify another documented threshold.
6. No runaway named-population explosion.
7. Every autonomous crystallization has mandatory `coverage_reason` and frozen provenance.
8. Every crystallized actor is fully wired: life, health, simulation, location, affiliation/context, resolution, continuity, lineage.
9. No demographic cohort subtraction on crystallization under the verified total-population-overlay semantics.
10. Latent stage pool accounting remains coherent.
11. No automatic officeholder/succession appointment merely because someone was crystallized.
12. Some appropriate succession vacancies resolve multiple candidates where latent structure supports it.
13. No invalid close-kin autonomous unions.
14. No auto-made player marriage/family commitment.
15. Same RNG seed produces identical autonomous unions, births, crystallizations, coverage reasons, and continuity-history hash.
16. Different RNG seed remains healthy but should not produce an identical social history.
17. Extended contradiction scan reports zero errors throughout/checkpoints.

Run at least:

- seed A, 200 years;
- seed A again, 200 years;
- seed B, 200 years.

Compare persisted continuity histories/hashes, not just final counts.

---

# 13. Exploratory attempted-v0.27 observations

The prior attempted session reported the following exploratory result before persistence of the source delta was lost:

- 200-year run endpoint: ~350 living named;
- ~816 historical/deceased named;
- ~695 autonomous crystallizations;
- ~92 grounded NPC unions;
- ~83 named births;
- minimum observed living named: ~321;
- provisional floor: 272;
- floor breaches: 0;
- annual continuity reviews: 200;
- final contradiction scan: 0 errors.

It also reported performance fixes around shared-clock dispatch, information event high-water marks, and periodic SQLite `ANALYZE` during very long stress runs.

**Treat all of this only as useful expected behavior, not as verified code or certified test output. None of the corresponding v0.27 source files survive in the current runtime. Reimplement/rerun.**

---

# 14. Files/functions to inspect first

- `engine/bootstrap.py`
  - production population and latent-stage-pool semantics
- `engine/household_life.py`
  - `create_union()`
  - `update_family_plan()`
  - `register_birth()`
  - `_resolve_planned_births()`
  - `next_household_life_due_day()`
  - `process_due_household_life()`
- `engine/crystallization.py`
  - `prepare_crystallization_context()`
  - `validate_crystallization_proposal()`
  - `apply_crystallization_proposal()`
- `engine/stress.py`
  - contradiction scanner / long-run reports
- `engine/simulation.py`
  - authoritative shared-clock due-day dispatch
- `engine/civilian.py`
  - household-life clock integration
- `engine/db.py`
  - bump schema/version to 27 and add migration 27
- `engine/schema.sql`
  - continuity review/provenance fields/tables
- `tests/v26_candidate_scale_test.py`
  - production-scale pattern to extend
- `tests/v25_test.py`, `tests/v25_edge_test.py`
  - long-horizon and crystallization continuity patterns
- `tests/v19_edge_test.py`
  - family/kinship edge cases
- `tests/run_all.py`
  - register new v0.27 tests

Current direct code verification also confirms:

- `create_union()` is referenced by CLI/tests, not the autonomous review loop;
- `prepare_crystallization_context()` is referenced by CLI/tests, not routine autonomous simulation;
- production bootstrap contains no household-union/family-plan seed path.

---

# 15. Suggested new files

- `engine/named_continuity.py`
- `tests/v27_test.py`
- `tests/v27_edge_test.py`
- `tests/v27_200y_test.py` (or fold into candidate-scale suite if runtime is manageable)
- `AUDIT_v0_27_NAMED_CONTINUITY.md`
- update `LONG_RUN_STRESS_TESTING.md`
- update `README.md`, `DESIGN.md`, `CHANGELOG.md`

If performance requires a separate checkpointed determinism runner, add it rather than weakening the 200-year acceptance criteria.

---

# 16. What still needs to be done before v0.27 can ship

This is the actual remaining task list:

1. Implement schema migration 27 and engine version 0.27.x.
2. Add authoritative continuity-review/provenance storage.
3. Implement `engine/named_continuity.py` observer/trigger layer.
4. Wire it into the shared story clock.
5. Implement deterministic demand-driven autonomous crystallization.
6. Make `coverage_reason` mandatory/queryable.
7. Add enforceable age/sex/region/Stage/provenance distribution checks.
8. Ensure autonomous crystallization fully wires life/health/simulation/location/affiliation/resolution/continuity state.
9. Implement multi-candidate succession-pool resolution without auto-appointment.
10. Implement minimal grounded autonomous NPC union/family-plan formation.
11. Keep player major commitments excluded.
12. Extend contradiction scanner with all v0.27 invariants.
13. Run and record fresh 200-year no-replenishment mortality calibration.
14. Set/document a measured promotion cap.
15. Add v0.27 regression + adversarial tests.
16. Run same-seed 200-year test twice and compare complete continuity-history hashes.
17. Run alternate-seed 200-year test and verify healthy but non-identical history.
18. Run the entire existing suite through v0.27.
19. Produce `AUDIT_v0_27_NAMED_CONTINUITY.md` with actual measured results.
20. Reset distributable DB to clean day 0, remove caches/test artifacts, package ZIP only after every criterion passes.

Do not label v0.27 complete before items 1–20 are done.

---

# 17. Governing design principles to preserve

- SQLite remains authoritative.
- Story time only.
- Causality remains protagonist-agnostic.
- Named actors are resolution, not a privileged population caste.
- Latent means undescribed, not nonexistent.
- Crystallization explains an existing life; it does not invent a convenient past for the current plot.
- Successor eligibility is not appointment.
- Autonomous marriage must arise from ordinary social causality, never named-population quotas.
- Simulate broadly. Resolve selectively. Present personally. Preserve continuity everywhere.

