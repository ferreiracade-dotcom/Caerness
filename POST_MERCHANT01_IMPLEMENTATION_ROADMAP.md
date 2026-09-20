# Caerness — Post-MERCHANT-01 Implementation Roadmap

**Date:** 17 September 2026  
**Status:** Current continuation sequence after the foundational architecture and first economic vertical slice.

## Completed current-chain milestones

1. Phase 2A — territorial/shared-geography foundations.
2. ARCH-01 — ProcessRegistry spike; durable SQL scheduling retained.
3. Rackets/Assets — concrete criminal operations/assets.
4. ECON-01 — economic interests/flows; protection/front corrections.
5. EVENTS-01 — selective event-first strategic ownership accepted.
6. REL-01 — directed evaluative relationships.
7. PRES-01 — low-resolution presence.
8. BELIEF-01 — claims/evidence + Competence Lens.
9. DEC-01 — information-bounded concrete candidate runtime.
10. MERCHANT-01 — enterprise records, observed offers, market reports, contracts, conserved stock/cargo, settlement/credit, commerce competence and steel/copper substitution signal.

## Immediate next slice — CRAFT-01 production dependency closure

MERCHANT-01 deliberately stops at the edge of production. `production_input_options` currently expresses **which technically valid material can satisfy a substitution role and how demand responds to price**; it is not a full bill-of-materials or physical-consumption system.

CRAFT-01 should make actual production causal.

### Authoritative production objects

Add or strengthen shared owners for:

```text
recipe / process definition
→ required input goods and quantities
→ optional substitution groups
→ intermediate goods
→ required tools / equipment / facilities
→ labor skill/capacity
→ production order / batch
→ reserved inputs
→ consumed inputs
→ output lots
→ waste/by-products where material
```

A workshop must not produce an item merely because `material_access=70` if the chosen resolution tier requires real stock.

### Dependency closure

Build at least one end-to-end dependency graph such as:

```text
ore / scrap
+ charcoal / fuel
+ furnace / forge capacity
+ skilled labor
→ iron/steel intermediate
→ tool/weapon/metalware output
```

Validation must fail when a required material, tool or intermediate has no available source/path at the selected simulation resolution.

Do not require every distant village to resolve every nail individually. Preserve aggregate/latent/tracked resolution layers, but make the conversion between them explicit and conservation-safe.

### Procurement integration

CRAFT-01 must consume the MERCHANT-01 substrate rather than duplicating it:

- input stock comes from enterprise inventory;
- shortages can generate concrete purchase/contract candidates;
- shipments must actually arrive before stock is usable;
- seller credit may finance procurement;
- late cargo can delay a real production order;
- excess finished stock can generate merchant sale/movement candidates.

### Price substitution

Retain MERCHANT-01's steel/copper substitution mechanism, but promote it from a demand signal into actual recipe selection where technically valid.

The production owner should decide which permitted material mix a batch uses and reserve/consume the corresponding quantities. Relative price may influence the mix; it must not permit physically invalid substitution.

### Capacity and scheduling

Ordinary small workshops should use a lightweight production-order resolver.

Use a heavier queue/scheduling model only where the institution warrants it, e.g.:

- large smithy;
- shipyard;
- arsenal;
- major textile works;
- scarce furnace/equipment bottleneck.

Player-facing control remains ordinary-language priority/delegation, not machine scheduling.

### Staff and competence

Distinguish:

- enterprise authority/management;
- craft competence;
- specialist roles;
- labor capacity;
- actual worker availability where tracked.

Professional competence should improve feasible process choice, quality control and diagnosis of bottlenecks; it must not conjure missing material or equipment.

## CRAFT-01 acceptance experiment

Use a bounded metalworking chain that crosses MERCHANT-01:

1. workshop has a real order for metalware/tools;
2. available local copper is expensive;
3. steel becomes cheaper after the MERCHANT-01 supply shock;
4. the workshop chooses steel only because the recipe permits it;
5. the workshop lacks enough steel on hand;
6. a concrete procurement candidate/contract is created from an actually known offer;
7. physical cargo travels and arrives;
8. the production batch reserves and consumes the delivered stock;
9. finished inventory is created;
10. enterprise accounts/margins reflect real material purchase and output sale;
11. a missing required input or facility blocks production with an inspectable reason.

No direct `production_success +1` or synthetic material-access success may bypass the chain.

## After CRAFT-01

1. **GROWTH-01** — backwater-count / regional growth and state-capacity vertical slice.
2. **WAR-01** — campaign logistics → battle → persistent people/property/refugee/information consequences.
3. Health + agriculture/weather + law/procedure integration.
4. Cross-system World-Bible coverage/regression gate.
5. Integrated ordinary one-year unattended run with every major domain active and crystallization/down-resolution functioning.
6. Ten-year run only after the coverage gate and one-year integrated run pass.

## Architecture rule

> Reuse shared owners. Goods are goods, money is money, people are people, routes are routes, evidence is evidence. A new vertical slice should connect those objects more deeply rather than inventing a parallel abstraction for its own convenience.
