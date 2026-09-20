# v0.26.1 Integration, Save-Safety, and Candidate-Scale Audit

## Scope

v0.26.1 is the v1.0-preRC hardening pass. It does not add a new simulation domain. It closes the integration and product-readiness gaps identified by the final v0.25 whole-engine review: campaign initialization, save safety, schema migration, ownership mirrors, phone-facing inspection, domain-to-decision integration, and realistic-scale long-run validation.

## Release verdict

**PASS for v1.0-RC1 entry.**

The ordinary cumulative regression suite passes through v0.26.1, the adversarial ownership/cadence audit passes, representative legacy databases migrate to schema 26 with preserved state and safety backups, and the realistic production seed survives the 20/40/120-year candidate-scale run with zero detected contradictions.

## 1. Campaign bootstrap and canon boundaries

The production bootstrap creates an inhabited starting world instead of the old non-canon demo seed:

- 48 established places;
- 36 institutions/polities;
- 388 named working-registry characters;
- 6 Hearth demographic cohorts;
- 6 latent cultivation-stage pools;
- approximately 3.5 million aggregate starting population.

Bootstrap is idempotent and is separate from player creation. No player character is silently generated.

Open World-Bible questions remain open. The bootstrap intentionally creates **zero detailed travel routes** and **zero religious observances**, because those details are not locked universally by the current canon.

## 2. Save safety and migration

Tests now select temporary databases rather than the packaged/live campaign database. A normal non-test `reset` refuses to delete a campaign without explicit `--force`, and reset/migration operations create safety backups by default.

Schema version 26 introduces a persistent ordered migration ledger. A final migration audit copied representative databases from v0.15.1, v0.19.1, v0.20.1, v0.24.0, and v0.25.0 and upgraded them using the current engine.

| Source | Result | Schema | Integrity | Critical contradictions | State preservation |
| --- | --- | ---: | --- | ---: | --- |
| v0.15.1 | PASS | 26 | `ok` | 0 | clean day-0 state preserved |
| v0.19.1 | PASS | 26 | `ok` | 0 | clean day-0 state preserved |
| v0.20.1 | PASS | 26 | `ok` | 0 | clean day-0 state preserved |
| v0.24.0 | PASS | 26 | `ok` | 0 | clean day-0 state preserved |
| v0.25.0 | PASS | 26 | `ok` | 0 | day 180 + actor + event preserved |

Every representative migration created a pre-migration safety backup and recorded all 26 migration-ledger entries.

## 3. Ownership and duplicate-state hardening

The final review identified several deliberate mirrors that needed explicit ownership rules. v0.26.1 now scans for divergence rather than relying on convention alone:

- `actor_life_profiles.life_status` / actor death state;
- authoritative `territorial_control` / `locations.political_owner` compatibility mirror;
- actor physical location / `player_state.current_location_id`;
- household migration intent / route-owned physical travel state.

Death now retires a named character's autonomous simulation profile immediately. This fixed a real century-scale issue where deceased characters could remain scheduled and generate posthumous decisions. The scanner now detects both scheduled deceased actors and decisions dated after death.

## 4. Domain-to-decision integration

The generic goals/pressures layer remains an interpretation layer rather than a second truth store. v0.26.1 derives candidate pressure/motivation context from authoritative health, household, business, religion, travel, education, and political state. Domain systems remain the owners of their facts.

## 5. Scheduler and long-horizon performance hardening

The audit found that ordinary DORMANT/STRATEGIC cadence could be silently shortened by old scheduler caps. Normal configured cadence is now authoritative; temporary promotion can still shorten review intervals when causally justified.

Additional long-run hardening includes:

- deceased-actor scheduler retirement;
- quarterly review for stable late-decline health rather than unnecessary monthly wakeups;
- reuse of unchanged canon-context selection;
- indexes for scheduler/goal/pressure lookups;
- bounded stress checkpoints and appropriately scoped integrity scans;
- established v0.22 route geography becoming authoritative for information propagation once crystallized.

## 6. Production 20/40/120-year run

The realistic production seed was advanced through the same authoritative story clock used in play.

| Checkpoint | Story day | Segment time | Approx DB size | Decisions | Living named characters | Deceased named characters | Aggregate population | Contradictions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Year 20 | 7,300 | 5.58 s | 9.58 MB | 23,106 | 388 | 0 | 4,024,199.81 | 0 |
| Year 40 | 14,600 | 5.51 s | 15.95 MB | 46,113 | 388 | 0 | 4,262,632.57 | 0 |
| Year 120 | 43,800 | 19.67 s | 31.23 MB | 99,207 | 1 | 387 | 4,278,091.86 | 0 |

Total measured simulation time was approximately **30.76 seconds** in the packaging environment. These figures are regression measurements, not device guarantees.

The near-complete turnover of the original named registry by year 120 is **not repaired by spawning replacement adults**. Aggregate population persists and latent population machinery remains available; named people should be promoted/crystallized when causally relevant.

## 7. Alternate and load tests

Additional candidate-scale checks passed:

- 40 years with RNG seed `271828`: ~10.84 s, zero critical contradictions;
- 40 years with RNG seed `314159`: ~10.80 s, zero critical contradictions;
- 1,500 actors due on the same story day: all 1,500 resolved in ~0.22 s;
- 64 locations, 112 authoritative routes, 192 actors: one public-information item traversed the full crystallized graph in ~0.011 s with zero critical contradictions;
- 200 differentiated businesses across 10 locations for five years: 12,000 authoritative business cycles in ~0.94 s, all 200 enterprises updated, aggregate cash changed from 73,610.00 to 158,111.98, zero critical contradictions.

## 8. Phone/player-facing integration

The mobile runtime no longer carries stale v0.8/v0.15.1 labels. Its setup/Ledger layer exposes the core state a player or administrator needs without exposing omniscient NPC truth as normal play UI:

- production campaign initialization;
- explicit player creation;
- personal health and household state;
- education/transmission and religious life;
- travel/environment state;
- derived pressures;
- engine/schema version and contradiction status.

Low-level simulation APIs remain available through the CLI, but they are not the intended everyday player interface.

## 9. Explicit v1.0 boundary: historical crystallization

Historical crystallization remains **actor-first in v1.0**. It can reconstruct a previously latent person against established history and preserve the lineage trail. Buildings, workshops, shrines, manuscripts, offices, and institutions already persist once established, but v1.0 does not claim a single generalized retroactive crystallizer for every entity family.

This is a documented scope boundary, not an untracked defect. General multi-entity historical crystallization can be considered after v1.0 if actual campaigns show that it is needed.

## 10. Final test status

The ordinary cumulative suite passes:

> **All Caerness Engine v0.26.1 tests passed.**

This includes every earlier subsystem regression and adversarial audit through v0.25 plus the v0.26.1 bootstrap/save-safety and ownership/cadence/seeded-scale regressions.

## Candidate conclusion

v0.26.1 closes the blockers identified in the v0.25 whole-engine review. The remaining limitations are now documented design boundaries or ordinary post-1.0 polish rather than architectural blockers.

**Recommendation: package v0.26.1 as the v1.0-preRC baseline and cut v1.0-RC1 from this code line without adding another major simulation subsystem.**
