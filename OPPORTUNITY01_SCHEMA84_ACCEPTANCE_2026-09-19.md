# Caerness v0.60.0 — OPPORTUNITY-01 Symmetric Opportunity / Relationship Formation Acceptance
**Date:** 19 September 2026  
**Status:** ACCEPTED WORKING CHECKPOINT  
**Schema:** 84  
**Predecessor:** schema 83 ATTENTION-01 working branch; schema 80 remains the prior packaged baseline.

## Purpose

Schema 84 generalizes the SEEK/ATTENTION work into a symmetric opportunity layer.

The governing rule is:

> A person, institution, enterprise or strategically important asset can become relevant to somebody else's plans even when it is not actively advertising itself; either side can then search, approach, negotiate, reject, counter, or form a persistent relationship whose terms have real consequences.

This is not a player-only system. The same machinery is available to rulers, noble houses, clans, sects, merchant institutions, criminal organizations, companies and individuals.

## Architecture

SEEK-01 remains the bounded answer to “I know what I need; find a provider.”  
ATTENTION-01 remains the bounded answer to “I learned that this person matters to my plans.”  
OPPORTUNITY-01 owns the next layer:

`need/salience -> discovery -> candidate -> typed proposal -> explicit terms -> negotiation -> agreement/refusal -> causal transfers/rights/engagements`

The opportunity layer does **not** invent why an institution needs a smith, assassin, escort company, breeder or adviser. Domain systems persist that need as ordinary state/pressure; OPPORTUNITY handles matching and relationship formation.

## New persistent owners

Schema 84 adds:

- `opportunity_proposals`
- `opportunity_proposal_terms`
- `opportunity_agreements`
- `enterprise_control_interests`
- `strategic_assets`
- `service_engagements`
- `contractual_rights`
- `opportunity_capabilities`
- `opportunity_searches`
- `opportunity_search_results`

## Typed proposal consequences

Acceptance no longer means “add an appointment badge.” Proposal terms can independently express:

- enterprise legal ownership;
- beneficial control;
- operating authority;
- appointment / membership;
- first-refusal rights;
- exclusivity / non-compete / access / use rights;
- service or supply commitments;
- asset transfer;
- duration, residence, stipend, revenue-share, termination and other terms.

Required executable terms run transactionally. A failed required transfer rolls back acceptance rather than creating a half-applied deal.

### Crown horse-breeder acceptance

The ATTENTION horse-breeder provider now offers an **incorporation**, not a harmless side office.

Accepted “Remount Master” terms currently mean:

1. the Crown institution receives 100% legal ownership of the stud;
2. the Crown receives beneficial control;
3. the breeder remains the operating master;
4. the breeder receives the institutional appointment.

The stud remains an operating enterprise, but it is no longer the breeder's privately owned business.

A separate first-refusal proposal proves the opposite semantics: the breeder keeps full ownership and grants the Crown only the specified commercial right.

## Enterprise control is no longer one field

`civilian_enterprises.owner_actor_id` remains a compatibility field, but schema 84 introduces explicit control interests:

- `legal_owner`
- `beneficial_controller`
- `operator`
- `revenue_share`

Migration seeds present-day legal ownership from the legacy owner field without inventing past ownership history.

## Kingdom / institution talent search

`opportunity_searches` can search the **existing world** for actual talent.

A talent search evaluates:

- real competence;
- discoverability / public reputation;
- existing appointments;
- enterprise roles;
- institution memberships;
- resulting availability;
- the seeker's willingness to poach already-committed talent.

It does not create a specialist because the seeker wants one.

Acceptance proves a kingdom search can find both:

- an independent master smith;
- a more skilled but already-embedded Great-House smith.

The embedded smith is visible but materially less available.

## Non-state institutional agency

Noble houses, clans, sects and other institutions are not second-class seekers.

A domain can persist an `organization_pressures` row whose metadata carries a concrete `opportunity_need`. DEC-01 then exposes bounded choices to:

1. open a real-world search;
2. later approach a discovered candidate.

Acceptance proves a sect with a real forge-capacity pressure autonomously opens a smith search and receives a concrete approach candidate on the next review.

OPPORTUNITY does not invent the forge shortage; the institution/domain owns that cause.

## Service-provider generalization

`opportunity_capabilities` lets actors, institutions and enterprises expose discoverable service capability without a bespoke quest hook.

Acceptance covers:

- a mercenary company as an institutional service provider;
- an independent fixer as an individual service provider;
- an assassin order as an institutional covert-service provider.

The same pattern is intended for escort companies, advisers, physicians, craftsmen, spies, engineers, caravan specialists and other services.

Accepted service proposals create a real `service_engagements` row containing:

- client;
- provider kind/id;
- domain/service kind;
- scope;
- compensation metadata;
- exclusivity;
- start/end dates;
- source proposal.

Signing the engagement does not fabricate fulfillment. Domain systems still own escort movement, battle service, assassination, investigation, construction, etc.

## Unsolicited asset interest

`strategic_assets` separates ownership from market listing.

A visible/renowned asset can be discovered even when `offered_for_sale=0`.

Acceptance proves a merchant collector's exceptional horse can be found by another actor and receive an unsolicited purchase proposal while remaining explicitly unlisted. The owner can reject, counter or accept.

This model can later cover rare manuals, ships, mines, weapons, artworks, breeding animals, relics and other strategically important possessions.

## Negotiation

OPPORTUNITY-linked interactions now synchronize rejection/countering with proposal state.

- rejection -> linked proposal becomes `rejected`; no terms execute;
- counter -> original becomes `countered`; a new child proposal carries the amended terms;
- acceptance -> only the accepted proposal's terms execute.

Acceptance test:

- Crown proposes first refusal on horses above quality 80;
- breeder counters at quality 92;
- original proposal remains unexecuted;
- Crown accepts the child proposal;
- only the quality-92 right becomes active;
- breeder keeps ownership of the stud.

## Player agency

Incoming offers to the player remain pending until explicit player response.

Other actors may decide to notice, seek, investigate, compete with, regulate or approach the player without permission. But voluntary relationship terms—employment, incorporation, patronage, partnership, contract, asset sale, etc.—do not auto-accept on the player's behalf.

## Mature-save migration

The accepted day-3650 schema-80 save migrated to schema 84 with:

- day: `3650 -> 3650`;
- events: `5,324 -> 5,324`;
- interactions: `2,606 -> 2,606`;
- active institutions: `108 -> 108`;
- new historical OPPORTUNITY proposals: `0`;
- new historical searches: `0`;
- new historical strategic assets: `0`;
- new historical service engagements: `0`;
- new historical ATTENTION cases: `0`;
- new historical SEEK intents: `0`;
- present-day enterprise legal-owner interests seeded: `160`.

The migrated save then advanced 60 further days successfully to day 3710 with all seven countries intact, clean integrity and zero foreign-key violations.

## Fresh ecological audit

A fresh 365-day unattended run with no specially seeded opportunity providers produced:

- OPPORTUNITY proposals: `0`;
- OPPORTUNITY searches: `0`;
- service engagements: `0`;
- strategic assets: `0`;
- ATTENTION cases: `0`;
- ordinary SEEK intents: `18`;
- active countries: `7`;
- active institutions: `108`;
- SQLite integrity: `ok`;
- foreign-key violations: `0`.

So the new architecture adds possible relationships without creating generic recruitment/contract spam.

## Regression status

Green focused sweep:

- OPPORTUNITY symmetric relationships/ownership/search;
- OPPORTUNITY rejection/counter negotiation;
- ATTENTION strategic relevance;
- SEEK inbound demand;
- SEEK natural attraction/capacity;
- SEEK reputation feedback;
- SEEK enterprise projection;
- DEC-01 information-bounded decisions;
- ARCH-02 scheduler chunk invariance;
- ORGLIFE country lifecycle;
- MERCHANT-01;
- WAR-01;
- ECON-01 underworld economic interests;
- EVENTS-01;
- v0.60 underworld rebuild;
- smoke.

See `SCHEMA84_REGRESSION_SWEEP.txt`.

## Explicit current boundaries

Schema 84 does **not** claim every domain already publishes every possible provider/asset/capability.

Current generic machinery is accepted; domain projection remains incremental. In particular:

- ordinary untracked goods do not automatically become `strategic_assets`;
- service engagements do not execute their underlying domain task by themselves;
- national cash/land transfers are not fabricated where no authoritative treasury/land owner exists;
- autonomous institution searches require a real domain-created `opportunity_need` pressure;
- OPPORTUNITY does not decide that a sect needs a smith, a kingdom needs an assassin, or a company needs an escort merely because such providers exist.

Those boundaries preserve the engine rule: **capability and matching do not manufacture motive.**

## Result

Schema 84 establishes the broader player/NPC consequence principle:

> Success, ownership and unusual capability change what relationships other actors imagine with you. The world can seek you, recruit you, contract you, try to acquire what you control, or reorganize around your relevance—and you can search the same world in reverse for real people, institutions and assets.
