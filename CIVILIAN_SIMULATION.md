# Caerness Engine v0.16 — Civilian Simulation Core

v0.16 is the first civilian-world simulation pass built on the audited v0.15.1 baseline.

Its governing rule is:

> **Peaceful life must be simulated as causally as war.**

The civilian layer is not decorative flavour. Households, careers, production, markets, patronage, projects, objects, provenance and auctions now possess authoritative persisted state and advance through the same story-time clock as politics, NPC decisions and battles.

## What is actually implemented

### Households
Persistent household records track location, head, membership, wealth, liquidity, staff capacity, cohesion and hospitality. Household upkeep is time-based and can gradually move a household into decline instead of requiring one dramatic bankruptcy event.

### Enterprises and production
Persistent enterprises track capital, cash, debt, reputation, administrative quality, labour capacity and risk tolerance. Production sites have capacity, material access, skilled labour, efficiency and inventory. Production resolves over elapsed story time, creates real account entries and interacts with local demand and price.

### Markets
Goods have base prices, categories, units, perishability, skill intensity and luxury value. Local markets separately track supply, demand, transport pressure, risk pressure and tax pressure. Prices are derived from those local conditions and re-evaluated on their own cadence.

The player sees the result through the existing information/competence architecture rather than receiving an omniscient economic dashboard in normal play.

### Careers
The existing v0.8 career schema is now used by a live civilian resolver. Careers accumulate time-in-career and time-in-stage. Stages can require elapsed experience and a competence domain. Routine advancement occurs only when a track explicitly marks that step as automatic; otherwise the character becomes eligible and the institutional/person-level decision can be resolved separately.

### Projects
Architecture, artwork, textile, manuscript, craft, public-work, household and business projects now have persistent progress. Progress depends on funding, material access and skilled labour. Completed projects become historical anchors. Appropriate cultural projects create persistent objects automatically.

### Cultural objects and provenance
Important objects can persist with creator, owner, location, quality, condition, attribution confidence, cultural reputation, market value and significance. Provenance is append-only history: creation, commission, sale, inheritance, restoration, disputed attribution, loss and recovery can all be recorded separately.

### Auctions
Auctions are scheduled world events. Lots, reserve prices, estimates and bidder interest are persisted. Resolution uses bidder budget, interest, taste and status motive to produce a deterministic campaign result, then updates ownership and provenance.

### Underworld overlap
Shadow-market links represent abstract illicit/deceptive pressure around actors, objects, enterprises or auctions: disputed provenance, forgery risk, fencing risk, corrupt access and similar pressures. They evolve only as abstract risk/exposure state. The system deliberately does not encode operational crime instructions.

## Shared-clock integration

The civilian subsystem is integrated into `advance_connection()`. Market reviews, scheduled auctions, active production, projects, careers, households, enterprises and shadow-market exposure continue off-camera whenever story time advances.

They are therefore subject to the same foundational rule as the rest of Caerness:

> **Dormant does not mean frozen. Off-camera does not mean nonexistent.**

## Deliberate limits of v0.16

v0.16 is the civilian **core**, not the final complete civilian game.

Still to deepen in later passes:
- profession-specific labour markets and wage negotiation;
- inheritance and succession resolution beyond the general continuity systems;
- richer household relationship effects;
- architecture-specific design/renovation/building persistence;
- fashion propagation and named style movements;
- merchant credit networks and large partnership structures;
- law, contracts and civic institutions at deeper resolution;
- collection curation and institutional museums/libraries;
- health/aging interaction with careers;
- player-facing UI for civilian systems.

The important milestone in v0.16 is that civilian life is no longer merely described. It now has authoritative state, elapsed-time resolution, consequences, and regression tests.
