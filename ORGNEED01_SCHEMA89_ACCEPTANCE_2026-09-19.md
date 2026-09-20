# Caerness v0.60.0 — ORGNEED-01 Evidence-Bound Autonomous Organization Needs
**Date:** 19 September 2026  
**Status:** ACCEPTED WORKING CHECKPOINT  
**Schema:** 89  
**Predecessor:** schema 88 / PATRONCIRCLE-01

## Purpose

OPPORTUNITY-01 already allowed rulers, houses, clans, sects, companies and other institutions to search the existing world for real people and providers, but it deliberately refused to invent *why* an institution needed one. Until this slice, the autonomous bridge depended on a hand-created `organization_pressures.metadata_json.opportunity_need` object.

ORGNEED-01 moves that causal boundary down one layer:

> a persisted institutional requirement can become unmet because world state changes; the engine may detect that unmet requirement and create a bounded organization pressure/search motive without hand-authoring an `opportunity_need`.

It does **not** infer professions from generic success/failure. A declining sect is not assumed to need a smith; a rich crown is not assumed to need an artist; an enterprise with no named staff is not assumed to have no workers.

## Schema 89

`institutional_roles` gains explicit staffing policy:

- `minimum_filled_slots` — how many slots are genuinely required rather than merely available;
- `autonomous_refill` — whether the institution should act when required staffing falls below that minimum;
- `minimum_candidate_quality` — evidence-bound search floor;
- `staffing_priority` — importance of restoring the required role.

Existing roles migrate with `minimum_filled_slots=0` and `autonomous_refill=0`. Migration therefore does not reinterpret every historical/open role as a vacancy.

New persistent owner:

- `organization_capability_requirements` — a domain-owned statement that a real program, obligation, office, asset or policy requires a specified organization capability at a minimum capacity/readiness, together with the permitted search relationship if the requirement is unmet.

Migration creates no capability requirements automatically.

## Role vacancy detection

A role creates an autonomous need only if all of the following are true:

1. the role is active;
2. `autonomous_refill=1`;
3. `minimum_filled_slots > 0`;
4. active appointments linked to that exact `role_id` fall below the required minimum.

The generated pressure is source-bound to the role and contains a typed OPPORTUNITY need. Its adaptive plan explicitly forbids creating another office: the existing role must be reused.

When active appointments again satisfy the required minimum, the source pressure resolves. Any still-open search generated from that need becomes fulfilled. Already-presented voluntary offers remain real social facts and are not silently revoked.

## Durable roles created by ADAPT

When ADAPT-01 creates a new role because all of its strict structural criteria are met — no reusable office, durable recurring need, internal authority required, explicit permission to create a role, and structural threshold passed — that new role is now marked as requiring one filled slot and is eligible for autonomous refill.

This means the institution does not forget *why the office exists* once its first holder later dies, leaves or is dismissed.

This rule applies only to roles actually created through the proven structural-gap branch. Ordinary existing roles are not changed by migration.

## Capability-gap detection

A domain may persist an `organization_capability_requirement` only when it owns a real cause for the requirement. ORGNEED-01 compares that requirement with the institution's authoritative `organization_capabilities` row.

If capacity/readiness is below the explicit target, an organization pressure is projected with a typed talent or service-provider search. If the capability later reaches the target, the pressure resolves.

Crucially, a search, contract or appointment does **not** automatically increase the capability. The relevant domain must actually change the authoritative capability state when the provider begins delivering useful capacity. This prevents “signed contract = magically solved problem.”

## Opening-world / pre-start rule

`activate_organization_lifecycle()` now refreshes explicit schema-89 requirements at activation. Therefore a seed may contain an already-existing required office or capability gap on day 0 and the corresponding need exists immediately; such needs do not have to wait to be “invented” after the campaign starts.

At the same time, migration does not fabricate requirements merely because a newer subsystem now exists.

A mature-state audit found several examples that **must not** be misread as vacancies:

- structural/aggregate law courts with `presiding_actor_id=NULL`;
- structural ordinary-care networks with no named `health_provider_assignments`;
- owner-operated/aggregate enterprises with no named `enterprise_staff`.

Those objects already represent functional aggregate capacity. “No named person attached” is not evidence that no one performs the work, so ORGNEED-01 deliberately does not turn them into recruitment needs.

## Acceptance scenario

`orgneed01_autonomous_need_generation_test.py` proves:

1. an ordinary active role with spare capacity but no explicit staffing minimum creates no need;
2. the same ontology, when explicitly marked as a required one-slot role, autonomously creates exactly one role-sourced organization pressure;
3. DEC-01/OPPORTUNITY sees that pressure without a manually inserted `opportunity_need`;
4. the institution opens a real talent search and discovers a pre-existing competent specialist;
5. ADAPT-01 reuses the required role and creates no duplicate office;
6. accepting the appointment fills the real role;
7. the next need review resolves the role pressure and fulfills the linked search;
8. an explicit capability requirement below target creates a service-provider need and can discover a real persisted institutional provider;
9. merely finding/contracting a provider does not mutate the capability target by fiat;
10. once the authoritative organization capability actually meets the target, the capability pressure resolves;
11. forcing an unrelated institution's lifecycle state to `declining` creates no profession-specific need by itself;
12. SQLite integrity and foreign keys remain clean.

## Fresh ecological audit

A fresh opening world advanced unattended for 365 days under schema 89 produced:

- required/autonomous-refill institutional roles: `0`;
- active organization capability requirements: `0`;
- ORGNEED-generated organization pressures: `0`;
- OPPORTUNITY searches sourced from ORGNEED: `0`;
- SQLite integrity: `ok`;
- foreign-key violations: `0`.

This is intentional. The current opening seed has no explicit schema-89 requirements, and ORGNEED does not manufacture them from organization type, wealth or lifecycle status.

## Mature-save migration

The accepted schema-88 campaign at real **day 3830** migrated to schema 89 with:

- day: `3830 -> 3830`;
- events: `5713 -> 5713`;
- interactions: `2752 -> 2752`;
- organization pressures: `0 -> 0`;
- migrated required/autonomous roles: `0`;
- backfilled capability requirements: `0`;
- backfilled ORGNEED pressures: `0`.

The migrated campaign then advanced another 60 days to **day 3890**:

- events: `5849`;
- interactions: `2836`;
- ORGNEED pressures: `0`;
- ORGNEED searches: `0`;
- SQLite integrity: `ok`;
- foreign-key violations: `0`.

The quiet result is evidence that schema 89 adds a causal route without rewriting old history.

## Regression status

PASS:

- `orgneed01_autonomous_need_generation_test.py`;
- `adapt01_reuse_before_create_test.py`;
- `opportunity01_symmetric_relationships_test.py`;
- `opportunity01_negotiation_test.py`;
- `orglife01_country_lifecycle_test.py`;
- `dec01_information_bounded_decision_runtime_test.py`;
- `patron01_social_patronage_test.py`;
- `patronnet01_patron_seeking_competition_test.py`;
- `patroncircle01_social_circle_movement_test.py`;
- `arch02_scheduler_chunk_invariance_test.py` at schema 89 / 90 days;
- `smoke_test.py`;
- Python `compileall` for `engine/` and `tests/`.

## Boundary

ORGNEED-01 solves **need detection from explicit structural state**, not every domain's future requirement vocabulary.

Domains still need to declare their own real requirements when causal facts justify them. For example, a future naval owner can say a fleet-expansion program requires shipwright capacity; a medical owner can say a new hospital requires a particular specialist mix; an archive crisis can say a transmission program requires a keeper. ORGNEED then detects whether that requirement is actually unmet and gives the institution agency to respond.

It remains wrong to convert every null named office-holder, low lifecycle score, low generic capability, or successful institution into a recruitment prompt.

## Result and next boundary

The earlier hand-seeded bridge is no longer the only route to institutional opportunity behaviour:

`real structural requirement -> actual gap -> organization pressure -> DEC choice -> real-world search -> proposal/negotiation -> role/service relationship -> domain fulfillment`

The next major pre-TENYEAR slice is **non-merchant endogenous organization formation**: ordinary people/groups must be able to become new clans, sects, gangs, companies, schools, associations and other institutions for concrete reasons, while reusing existing organizations where appropriate and preserving pre-start historical depth.
