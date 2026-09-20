# v0.18 Business Ecology

## Purpose

v0.16-v0.17 established enterprises, markets, production, credit, partnerships and professional membership. v0.18 adds the missing layer between **"this is an enterprise"** and **"this is a particular kind of business whose economics differ from its neighbors."**

The governing rule is:

> **Business type must change causal behavior, not merely change a label.**

A theatre, smithy, inn, lender, warehouse and gambling house can occupy the same city and experience the same month differently because they depend on different mixtures of travelers, trade, disposable income, elite patronage, cultural activity, credit demand, military demand, skilled labor, security, regulation and local events.

## Business archetypes

The engine now ships a stable vocabulary of business archetypes. The vocabulary does **not** assert that every settlement contains every business. Campaign history determines which enterprises actually exist.

Current archetypes include:

- hospitality and travel: inn, tavern, bathhouse, stable;
- entertainment and social venues: theatre, music hall, gambling house, pleasure/courtesan house, private salon;
- finance: moneylender, loan house, pawnbroker;
- craft: smithy, armorer, tailor, weaver, jeweler, carpenter, instrument maker, refiner;
- retail: food shop, cloth shop, book/manuscript shop, medicine shop, luxury-goods shop;
- professional services: physician practice, Vein-Mender practice, appraiser/authenticator, architectural practice;
- trade/logistics: warehouse, wholesaler, caravan firm, shipping house, courier service, cartage firm;
- security: escort office, bodyguard firm;
- culture/market institutions: auction house.

The pleasure/courtesan-house archetype is deliberately represented only as a non-explicit economic and social institution: clientele, staffing capacity, reputation, regulation, revenue and information exposure. The engine contains no sexual-content subsystem.

## Commercial context

Each location may carry a commercial context with independent values for:

- foot traffic;
- traveler flow;
- disposable income;
- trade flow;
- elite patronage;
- cultural activity;
- credit demand;
- military demand;
- health demand;
- craft demand;
- construction demand;
- regulation;
- security;
- event activity;
- reputation climate.

These values are campaign state, not universal canon. Later ecology, politics and demographic systems can alter them.

## Enterprise business profiles

An ordinary `civilian_enterprises` row remains the broad legal/economic entity. A differentiated business profile adds:

- archetype;
- quality;
- price position;
- operating capacity;
- utilization;
- clientele fit;
- service reliability;
- regulatory pressure;
- recurring review cadence.

This lets two businesses of the same broad enterprise kind behave differently.

## Recurring business cycles

Every configured business resolves through shared story time. A cycle records:

- elapsed days;
- local demand index;
- utilization;
- gross revenue;
- operating cost;
- net income;
- the commercial context used for the calculation.

Revenue and expense are written into the existing authoritative enterprise accounts, and enterprise cash/status changes accordingly.

Craft businesses with production sites receive reduced front-of-house/service revenue so the new system does not simply duplicate the existing production-sale layer. Finance businesses can derive bounded additional income from an actual outstanding loan book.

## Regulation and security

Regulated businesses respond more strongly to local regulation than ordinary workshops or shops. Security also matters, but there is no universal "crime = profit" rule. Security businesses can experience greater demand when ordinary security is poor; hospitality and trade usually suffer when the wider environment becomes unsafe.

## What v0.18 does not attempt

v0.18 is not a full city-economy or accounting simulator. It does not yet model individual customers, every wage, every table, every performance, every wager, or procedural criminal activity.

It supplies enough differentiated behavior that the engine can say more than "shop A and shop B both earn generic shop income."

## Long-run significance

This pass is necessary before demographic and city growth simulation. Once households, population, seasons and politics begin changing local conditions, business archetypes give those changes somewhere causally distinct to land.
