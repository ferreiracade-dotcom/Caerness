# Caerness Engine v0.19 — Household, Kinship, Demographic, and Life-Course Simulation

v0.19 deepens the household substrate established in v0.16-v0.17 into a generational system suitable for long-running campaigns.

## Governing principle

> **A household is not merely an inventory container or an inheritance target. It is a changing social institution whose membership, dependencies, kinship, residence, service relationships, and generations continue through story time.**

The engine distinguishes explicit major commitments from routine consequences. It does **not** automatically create marriages or partnerships merely because compatible actors coexist. A union must already exist as campaign fact before family-plan resolution can act on it. Once a family plan is explicitly established, births can occur as ordinary life-course consequences through shared story time.

## Implemented systems

### Actor life profiles

Named actors can now carry persistent birth day, demographic sex, life stage, household origin/current household, family-formation eligibility, and living/deceased status. Life stages update during ordinary world advancement and can emit coming-of-age history.

This is not yet the health/aging system. v0.19 tracks social life-course state; v0.20 will own disease, injury recovery, disability, physiological aging, fertility constraints, and ordinary mortality.

### Kinship

`kinship_links` persists parent/child, sibling, spouse, guardian/ward, adoptive, and other recognized kin relationships separately from generic stance/trust relationships. Kinship is therefore historical structure rather than an inferred label.

### Household unions and family plans

Marriage and recognized partnerships are persistent household facts. Family plans can explicitly record desired children, whether routine child generation is enabled, a birth-parent actor, spacing, and earliest next child day.

Automatic child generation is intentionally conservative: it occurs only for an already-established active union with an explicit `auto_children` family plan. The engine never decides that a player character marries or starts a family simply because time passes.

### Births and generational replacement

A birth creates a persistent actor, life profile, household membership, household dependency, parent/child kinship, sibling relationships, and a life event. Automatically generated children use a latent descriptive name until later crystallization or naming resolves fuller identity.

This finally allows households that possess inheritance systems to produce the generations that may later inherit them.

### Guardianship and dependants

Guardianships and household dependencies are first-class persistent records. Wards can enter a guardian's household without being treated as ordinary employees or generic relationship edges.

### Household formation and splitting

Established adults can form or split households while carrying bounded wealth/liquidity, membership, residence, and historical continuity. Splitting moves people rather than cloning the old household.

### Household service

Servants, retainers, guards, stewards, tutors, apprentices, clerks, and other household workers can have persisted service terms. Review dates, loyalty, satisfaction, household cohesion, and household condition can lead to continued service or departure over time.

This is deliberately a household-service layer, not yet the full employment/labor market promised by later career/economic passes.

### Household migration

A household can plan a migration for a future story day. When it resolves, the household and its active members relocate together and the move becomes campaign history.

### Aggregate demographic cohorts

Locations can hold aggregate age-banded cohorts for population-scale simulation. v0.19 supports migration and explicit birth pressure at aggregate resolution without creating thousands of named actors.

Ordinary mortality is deliberately **not** synthesized here. The health/aging pass will supply mortality and physiological constraints so demographic decline does not get invented twice by two unrelated systems.

### Explicit death transition

`mark_actor_deceased` exists as an authoritative life-cycle transition for combat, health, politics, accidents, or scripted campaign facts. It updates actor/life status, household membership, spouse union state, and life history. v0.19 itself does not randomly kill actors from old age or disease.

## Resolution policy

Named people use detailed persistent life state. Large populations use aggregate cohorts. The engine does not create a named person merely because an aggregate population number increased.

> **Generational continuity should be explicit where identity matters and aggregate where only population structure matters.**

## Deliberate boundaries

v0.19 does not yet provide:

- disease, injury, disability, recovery, or treatment;
- cultivation-specific aging or lifespan curves;
- ordinary mortality probabilities;
- physiological fertility modeling;
- full employment markets;
- automatic marriage matchmaking;
- education/transmission systems beyond household service roles;
- state-scale migration policy or refugee systems.

Those remain later passes rather than being silently approximated here.


## v0.19.1 edge-case hardening

The pre-v0.20 audit found several cases where the v0.19 substrate existed but could drift into contradictory state. v0.19.1 hardens those paths without taking ownership away from the future health/aging pass.

- family-plan births are scheduled on exact due days and require a valid living birth parent for automatic resolution;
- manual birth registration cannot silently backdate campaign history;
- sibling links include half-siblings through either recognized parent;
- kinship insertion is idempotent and reciprocal links are repaired when missing;
- guardianships can be explicitly ended, and moving a ward closes stale household/dependency state;
- household splits move attached service/dependency/guardianship records and repair the source head when needed;
- migration plans supersede older unresolved plans instead of allowing two future moves to fire;
- service terms do not overwrite an already-existing household/family role;
- death ends or detaches stale service/guardianship/dependency state;
- aggregate age cohorts now age forward between bands and review on their own annual cadence.

Ordinary mortality, fertility physiology, disease, disability, and treatment remain intentionally deferred to v0.20.
