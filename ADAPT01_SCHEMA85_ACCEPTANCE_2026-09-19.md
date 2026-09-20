# Caerness v0.60.0 — ADAPT-01 Reuse-Before-Role-Creation Acceptance
**Date:** 19 September 2026  
**Schema:** 85  
**Predecessor:** schema 84 OPPORTUNITY-01 accepted checkpoint  
**Status:** ACCEPTED WORKING CHECKPOINT

## Purpose

ADAPT-01 corrects an over-broad implication in the first opportunity-driven institutional-planning design: discovering unusually useful talent must not imply that an institution creates a new office for that person.

The accepted rule is:

`existing compatible role -> bounded contract -> standing retainer/service -> adjust existing remit -> new role only for a durable uncovered structural need`

Institutional plan adaptation and institutional role creation are separate things.

## New owners

Schema 85 adds:

- `institutional_roles`: durable role definitions independent of current holders;
- `institutional_programs`: projects, reforms, standing programs and initiatives;
- `institutional_plan_adaptations`: auditable records of how a discovered person changed an institution's plan;
- optional `institutional_appointments.role_id`: links an accepted appointment to a real pre-existing or newly-created role.

No historical roles/programs are fabricated during migration.

## Reuse-before-creation resolution

When a real talent search finds a candidate under an adaptive plan, the engine resolves the relationship in this order:

1. Reuse a compatible existing active role with an open slot.
2. If the need is one-off/temporary, use a service contract.
3. If durable access is useful but internal authority is unnecessary, use a standing service/retainer relationship.
4. Create a new role only if all are true:
   - no compatible existing role is available;
   - the need is recurring/durable;
   - internal authority is genuinely required;
   - the source domain explicitly allows role creation;
   - structural-need intensity meets the configured threshold.

A second search for the same structural role reuses the existing role definition rather than creating a duplicate.

## Acceptance scenarios

### Existing Master of Works

The Crown already has a `master_of_works` role and a Royal Works program. Discovering an exceptional master builder:

- raises/reshapes the existing program priority;
- produces a proposal to fill the existing role;
- creates zero new role definitions;
- accepted appointment links to the pre-existing role.

### Temporary bridge engineer

A 120-day bridge-repair need discovers a suitable engineer. Despite high importance, the bounded horizon resolves as a temporary service contract and creates no office.

### Standing metallurgy adviser

A durable arsenal-quality need does not require internal authority. The institution proposes standing service/retainership and creates no office.

### Genuine Master of Waterworks gap

A durable internal waterworks program has no compatible role and has very high structural need. The institution may create `master_waterworks` once. A later search for another hydraulic master reuses that same role rather than creating another one.

## Migration safety

The accepted day-3710 schema-84 save migrated to schema 85 with:

- day unchanged: 3710;
- events unchanged: 5,439;
- interactions unchanged: 2,686;
- appointments unchanged: 0;
- new historical institutional roles: 0;
- new historical institutional programs: 0;
- new historical plan adaptations: 0;
- SQLite integrity: `ok`;
- foreign-key violations: 0.

## Natural-year ecology

Fresh activated world advanced 365 days:

- institutional roles: 0;
- institutional programs: 0;
- plan adaptations: 0;
- OPPORTUNITY proposals: 0;
- OPPORTUNITY searches: 0;
- surviving countries: 7;
- SQLite integrity: `ok`;
- foreign-key violations: 0.

This proves the capability does not create background bureaucratic churn merely because the tables exist.

## Focused regression

PASS:

- ADAPT-01 reuse-before-role-creation acceptance;
- OPPORTUNITY-01 symmetric relationships/ownership/search;
- OPPORTUNITY-01 negotiation/counteroffer/rejection;
- ATTENTION-01 strategic relevance;
- all SEEK-01 acceptance tests;
- ORGLIFE-01 country lifecycle;
- ARCH-02 90-day scheduler chunk invariance;
- DEC-01 information-bounded decision runtime;
- smoke/dormant simulation.

## Design boundary

ADAPT-01 does not mean that every institutional plan is represented by a new program row or that every useful person must enter the institution.

A discovered person can change institutional behavior while remaining:

- an external contractor;
- a retained adviser;
- a supplier;
- an allied institution member;
- an independent operator;
- or simply someone whose existence changes the institution's policy.

New roles are exceptional structural consequences, not routine rewards for fame.
