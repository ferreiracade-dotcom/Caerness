# Caerness v0.60.0 — PATRONNET-01 Patron Seeking, Competition & Networks
**Date:** 19 September 2026  
**Status:** ACCEPTED WORKING CHECKPOINT  
**Schema:** 87  
**Predecessor:** schema 86 / PATRON-01

## Purpose

PATRON-01 proved that a merchant, noble, ruler or other capable person can independently patronize talent without employing or owning that person. PATRONNET-01 closes the opposite and network directions:

1. a talented person may actively seek a patron when that person has an explicit patronage-seeking intent;
2. more than one patron may compete for the same rising talent;
3. non-exclusive patronage may form a real multi-patron network;
4. exclusive patronage resolves incompatible competing offers explicitly rather than leaving ghost proposals.

The core distinction remains:

`talent / poverty / fame != automatic desire for patronage`

A beneficiary must actually have an actor-owned patronage-seeking intent. The engine does not infer that every artist, scholar, master or poor professional wants a patron.

## Schema 87

New persistent owners:

- `patronage_seek_profiles`
- `patronage_competitions`
- `patronage_competition_entries`

A seek profile records domain, desire intensity, desired support kind, minimum useful support, duration, tolerated exclusivity, funding/prestige/independence priorities, bounded simultaneous requests and next review.

Competition records preserve which concrete proposals competed, their patrons, financial support and exclusivity, and the eventual winner/loser state.

## Beneficiary-side discovery

A seeker does not search a generic list of rich people. A potential patron must already have:

- an active patronage preference in the relevant domain;
- enough interest for the beneficiary to fit that patron's own taste/motives;
- a real household or enterprise capable of funding the proposed support;
- enough current patronage capacity to make another relationship plausible.

The beneficiary then evaluates patrons using funding, patron prestige, compatibility and current capacity according to the beneficiary's own seeking priorities.

This makes the match bilateral: the artist may want the noble, but the noble also has to be the sort of person who could plausibly want that artist.

## Reverse proposals

A beneficiary can initiate a real `patronage` proposal toward a discovered patron.

The recurring-stipend term now explicitly identifies:

- patron actor;
- beneficiary actor;
- funding source;
- cadence and duration;
- support kind;
- explicit exclusivity.

Therefore proposal direction no longer determines relationship ontology. A patron may offer support to an artist, or an artist may ask a patron for support; both can materialize the same correct patron -> beneficiary relationship if accepted.

## Player agency

PATRONNET-01 does not invent outgoing player decisions. If the player is the beneficiary, autonomous review will not send patronage requests merely because a seek profile exists.

NPC beneficiaries can, however, discover a player who is a plausible patron and send that player a proposal. The ordinary interaction/player-response boundary still governs acceptance, rejection or counteroffer.

## Competition

Two or more pending patronage proposals for the same beneficiary/domain can create an explicit competition.

Non-exclusive patronage is allowed to coexist. This supports historical/social patterns in which an artist, scholar or master has multiple supporters.

If an accepted relationship is explicitly exclusive (current hard-conflict threshold >= 0.75), incompatible rival proposals are closed and the competition records the winning patron and losing proposals.

Exclusivity is never inferred merely from prestige, payment size or patron status; it must be an explicit negotiated term.

## Network read model

`patronage_network()` exposes current relationship counts, distinct patrons and beneficiaries, multi-patron beneficiaries, and active competitions. The authoritative relationships remain `patronage_relationships`; the read model does not create a second social truth.

## Acceptance scenario

The dedicated `patronnet01_patron_seeking_competition_test.py` proves:

1. a talented independent painter has an explicit desire to seek patronage;
2. two real patrons have compatible tastes/preferences and real funding sources;
3. the painter independently sends two bounded requests;
4. both patrons can accept non-exclusive support;
5. the painter remains one beneficiary in a genuine two-patron network;
6. two patrons then independently make exclusive offers to a second rising artist;
7. an explicit competition records both offers;
8. accepting one exclusive offer resolves the competition, records the winner/loser state and withdraws the incompatible rival proposal;
9. SQLite integrity and foreign keys remain clean.

## Negative ecology

A fresh unattended 365-day world with no patronage-seeking profiles produced:

- 0 patronage-seeking profiles;
- 0 beneficiary-originated patronage requests;
- 0 patronage competitions;
- 0 patronage relationships.

The system therefore adds possibility rather than automatically making every talented or poor person seek sponsorship.

## Mature-save migration

The real schema-86 day-3770 campaign migrated to schema 87 with:

- day unchanged: 3770;
- events unchanged: 5,555;
- interactions unchanged: 2,688;
- existing patronage unchanged: 0;
- newly backdated seek profiles: 0;
- newly backdated competitions: 0;
- newly backdated competition entries: 0;
- SQLite integrity: `ok`;
- foreign-key violations: 0.

It then advanced a further 60 days to day 3830 without spontaneous patronage-seeking state, because that campaign currently contains no explicit beneficiary patronage intent.

## Regression status

PASS:

- `patronnet01_patron_seeking_competition_test.py`
- `patron01_social_patronage_test.py`
- `opportunity01_negotiation_test.py`
- `opportunity01_symmetric_relationships_test.py`
- `attention01_strategic_relevance_test.py`
- all four SEEK-01 tests
- `adapt01_reuse_before_create_test.py`
- `dec01_information_bounded_decision_runtime_test.py`
- `arch02_scheduler_chunk_invariance_test.py`
- `smoke_test.py`
- Python compileall

## Boundary

PATRONNET-01 does not yet invent beneficiary patronage desire from generic poverty, profession or fame. Domain systems may create or update the explicit seek profile when a real causal reason exists: e.g. a stalled project, desire for court access, need for a workshop, scholarly expedition, martial school formation or deliberate social ambition.

It also does not treat every rivalry between patrons as hostility. Competition is presently a factual relationship around overlapping proposals; relationship consequences should arise from the actual people and events rather than from a generic jealousy rule.
