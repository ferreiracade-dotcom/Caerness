# Caerness v0.60.0 — PATRON-01 Social Patronage Acceptance
**Date:** 19 September 2026  
**Schema:** 86  
**Predecessor:** schema 85 / ADAPT-01  
**Status:** ACCEPTED WORKING CHECKPOINT

## Purpose

PATRON-01 extends OPPORTUNITY/ATTENTION beyond employment, purchase and office. A patron may materially support an independent person or institution without acquiring that person, their unrelated property, or all future output.

Core distinction:

`patronage != employment != commission != acquisition`

Patronage may coexist with later commissions, first-refusal rights, residence, exclusivity or other negotiated terms, but those consequences must be explicit.

## New persistent owners

Schema 86 adds:

- `patronage_preferences` — explicit patron tastes/motives/budgets rather than wealth automatically implying patronage;
- `patronage_relationships` — patron, beneficiary, funding source, cadence, independence, exclusivity and expectations;
- `patronage_payments` — actual recurring material transfers with shortfall/strain state.

Patronage is domain-generic. The acceptance case uses art/culture, but the relationship can support scholarship, architecture, craft, medicine, martial talent, religion, invention or other domains.

## Attention and opportunity integration

A patron with an explicit preference can notice a discoverable capable person through ATTENTION-01. PATRON-01 evaluates real capability, public visibility and domain reputation; it does not know hidden talent by omniscience.

The resulting relationship is proposed through OPPORTUNITY-01 as a `patronage` proposal with explicit terms. Incoming offers to the player remain player-controlled under the existing interaction boundary.

## Funding

The first accepted funding owners are:

- a patron's household liquidity;
- a patron-owned active enterprise cash balance.

Recurring support is conserved: the source balance falls and the beneficiary household (or fallback personal cash resource) rises. Missed/partial support strains the relationship rather than creating free money.

## Merchant + noble + artist acceptance scenario

A merchant collector and a noble collector each had explicit art/culture patronage preferences. One funded patronage from a merchant enterprise; the other from household liquidity. Both independently noticed the same high-quality, publicly visible painter.

The painter accepted both non-exclusive relationships.

Acceptance proved:

- two simultaneous patrons are legal where exclusivity was not negotiated;
- the painter received no institutional appointment or membership;
- recurring payments moved real money from both patrons to the painter's household;
- patronage itself transferred no enterprise or cultural object ownership.

The painter then completed an independent high-quality work during the patronage. The work did **not** become either patron's property. By contrast, a separately created explicit commissioned portrait was owned by its commissioning patron. This proves patronage and commission remain different relationships.

## Reputation feedback

Successful cultural output can raise the creator's cultural reputation. Active patrons receive a smaller cultural-reputation benefit when association with a beneficiary produces respected work. Merely paying support does not automatically grant prestige; output quality drives the feedback.

## Negative ecology

Fresh unattended 365-day run with no explicit patronage preferences:

- patronage preferences: 0;
- patronage relationships: 0;
- patronage payments: 0;
- `patronize` attention cases: 0;
- patronage proposals: 0.

Wealth alone therefore does not cause every merchant or noble to become a patron.

## Mature-save migration

The real schema-85 day-3710 campaign migrated to schema 86 with:

- day unchanged: 3710;
- historical events unchanged: 5,439;
- interactions unchanged: 2,686;
- patronage preferences: 0;
- patronage relationships: 0;
- patronage payments: 0;
- SQLite integrity: `ok`;
- foreign-key violations: 0.

The migrated save then advanced another 60 days to day 3770 cleanly, still without invented patronage because no historical patronage preferences were retroactively fabricated.

## Regression status

Green focused regressions include:

- `patron01_social_patronage_test.py`;
- ADAPT-01 reuse-before-role-creation;
- OPPORTUNITY symmetric relationships/ownership/search;
- OPPORTUNITY negotiation/rejection/counter;
- ATTENTION strategic relevance;
- all four SEEK acceptance tests;
- DEC-01 information-bounded decisions;
- ARCH-02 90-day scheduler chunk invariance;
- v0.60 underworld rebuild;
- ECON-01 underworld economic interests;
- EVENTS-01 territorial event sourcing;
- smoke/dormant simulation;
- Python compileall for `engine/`.

## Boundaries

PATRON-01 does not assume that every artist seeks a patron or every rich person wants one. Patron preferences are explicit state and can later be seeded/formed from collecting history, court culture, ideology, relationships, artistic taste or domain-specific events.

Institutional patronage from heterogeneous treasuries remains partly owned by older domain systems; schema 86's accepted fully conserved funders are households and enterprises. Future slices can bridge polity/sect/clan treasuries into the same patronage relationship without changing its semantics.

PATRON-01 also does not claim that support owns unrelated work. Ownership, first refusal, commissions, exclusivity, residence and access remain separate negotiated rights/terms.
