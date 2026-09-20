# Caerness v0.60.0 — PATRONCIRCLE-01 Patronage Circles, Introductions & Evidence-Bound Movements
**Date:** 19 September 2026  
**Status:** ACCEPTED WORKING CHECKPOINT  
**Schema:** 88  
**Predecessor:** schema 87 / PATRONNET-01

## Purpose

PATRONNET-01 made patronage bidirectional and competitive. PATRONCIRCLE-01 makes repeated patronage relationships socially consequential without assuming that every patron with several beneficiaries runs a salon, academy or school.

The accepted distinction is:

`multiple beneficiaries != circle != artistic school/institution`

A circle requires an explicit patron-side convening/networking motive. A cultural movement requires a second, stronger evidence threshold: actual connected creators must produce multiple high-quality works sharing a persisted style marker. A movement does not automatically become a formal institution.

## Schema 88

Migration 88 adds patron-side convening controls to `patronage_preferences`:

- `networking_motive` (default 0);
- `circle_cadence_days`.

New persistent owners:

- `patronage_circles`;
- `patronage_circle_members`;
- `patronage_circle_gatherings`;
- `patronage_circle_introductions`;
- `cultural_movements`.

Existing schema-87 preferences migrate with `networking_motive=0`, so migration itself cannot reinterpret old support relationships as historical salons.

## Private patronage vs convened circle

A patron may support several people privately. That fact alone does not create a circle.

`refresh_patronage_circles()` requires:

1. an active patronage preference in the domain;
2. explicit `networking_motive >= 45`;
3. at least two distinct active actor-beneficiaries in that same patron/domain relationship.

If the required social structure later disappears, the circle becomes dormant rather than being erased.

## Gatherings and introductions

An active circle has a real gathering cadence. Gatherings create explicit records and may introduce previously unacquainted beneficiaries.

Introduction is not a metadata-only edge. It updates the ordinary directed relationship owner with bounded familiarity, respect and professional-confidence changes. At most three genuinely new pairs are introduced in one gathering, avoiding an instant complete graph for large circles.

Repeated shared patronage without a gathering does not itself fabricate acquaintance.

## Reputation / prestige feedback

Successful cultural work continues to benefit the creator most strongly and may benefit the patron through existing PATRON-01 association logic.

For a publicly visible active circle, acclaimed work may also:

- increase circle prestige modestly;
- create a much smaller association spillover to other circle members.

This spillover is intentionally capped. Knowing or sharing a patron with a great creator cannot substitute for creating respected work oneself.

## Cultural movement emergence

A salon/circle is not a school or style.

`evaluate_cultural_movements()` currently requires, within an active cultural circle:

- at least 3 active creator-members;
- at least 3 qualifying works created after circle formation;
- each qualifying work quality >= 75;
- a shared explicit `style_tag`/`style_tags` marker across works;
- at least 3 distinct creators represented for the shared marker.

This can create an `emerging` movement under a structural unresolved identity. `display_name` remains nullable: existence does not require the simulation to invent a socially accepted name.

A movement becomes `recognized` only with stronger output evidence (currently >=5 qualifying works, mean quality >=84, and sufficient combined output/circle influence).

The movement remains cultural/social state. It does **not** create an academy, sect, guild or other institution automatically.

## Acceptance scenario

`patroncircle01_social_circle_movement_test.py` proves:

1. a private patron supports two artists with `networking_motive=0` and creates no circle;
2. a second merchant patron supports three artists and explicitly has a high convening motive;
3. exactly one active cultural circle forms around the convening patron;
4. shared patronage before gathering creates no introductions and no movement;
5. one real gathering introduces the three previously unconnected creator pairs and writes ordinary relationship changes;
6. two high-quality works with a shared style marker are insufficient to create a movement;
7. a third high-quality work by a third connected creator creates one `emerging` structural movement;
8. two additional excellent works raise the same movement to `recognized`;
9. no formal institution is created by that recognition;
10. SQLite integrity and foreign keys remain clean.

## Negative ecology

A fresh unattended 365-day opening world produced:

- networking patronage preferences: 0;
- patronage circles: 0;
- circle gatherings: 0;
- circle introductions: 0;
- cultural movements: 0;
- patronage relationships: 0;
- SQLite integrity: `ok`;
- foreign-key violations: 0.

The new layer therefore creates no salons or artistic schools merely because the machinery exists.

## Mature-save migration

The prior archive was named `TENYEAR01_day3830_SCHEMA87_RESUMED.zip`, but inspection found its authoritative database was actually at **day 3770**. The internal database state, not the filename, was treated as source of truth.

That real schema-87 day-3770 database migrated to schema 88 with:

- day unchanged: 3770;
- events unchanged: 5,555;
- interactions unchanged: 2,688;
- patronage relationships unchanged: 0;
- networking preferences backdated: 0;
- circles backdated: 0;
- gatherings backdated: 0;
- introductions backdated: 0;
- movements backdated: 0;
- SQLite integrity: `ok`;
- foreign-key violations: 0.

It then advanced 60 days under schema 88 to an actual **day 3830**:

- events: 5,713;
- interactions: 2,752;
- circles: 0;
- gatherings: 0;
- movements: 0;
- SQLite integrity: `ok`;
- foreign-key violations: 0.

This package corrects the previous filename/state mismatch.

## Regression status

PASS:

- `patroncircle01_social_circle_movement_test.py`;
- `patronnet01_patron_seeking_competition_test.py`;
- `patron01_social_patronage_test.py`;
- `opportunity01_negotiation_test.py`;
- `opportunity01_symmetric_relationships_test.py`;
- `attention01_strategic_relevance_test.py`;
- `adapt01_reuse_before_create_test.py`;
- `dec01_information_bounded_decision_runtime_test.py`;
- `arch02_scheduler_chunk_invariance_test.py` (schema 88 / 90 days);
- `smoke_test.py`;
- Python compileall for `engine/` and `tests/`.

## Boundary

PATRONCIRCLE-01 does not automatically create collaboration projects, institutions, ideologies or personal friendship from a circle. It establishes real social opportunity: people can meet, become professionally familiar, gain limited association effects, and—if their actual output converges—develop a recognizable movement.

Formal academies, schools or institutions must still arise through ORGLIFE/OPPORTUNITY/ADAPT when the social group develops durable organization, property, offices, membership rules or other institutional substance.
