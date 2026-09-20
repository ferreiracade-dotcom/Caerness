# Caerness — Post-DEC-01 Implementation Roadmap

**Date:** 17 September 2026  
**Status:** Current continuation sequence after REL-01, PRES-01, BELIEF-01 and DEC-01.

## Completed current-chain milestones

1. Phase 2A — territorial/shared-geography foundations.
2. ARCH-01 — ProcessRegistry spike; Caerness-native durable scheduling retained.
3. Rackets/Assets — concrete criminal operations/assets substrate.
4. ECON-01 — economic interests/flows; protection/front semantic correction.
5. EVENTS-01 — bounded territorial event-sourcing spike; selective event-first design accepted.
6. REL-01 — directed evaluative relationships; structural ties separate.
7. PRES-01 — low-resolution presence with exact scene/travel/habitual precedence.
8. BELIEF-01 — claims/evidence/actor-relative belief + Competence Lens.
9. DEC-01 — information-bounded concrete candidate runtime + weighted selection + domain-owned execution.

## Immediate next slice — MERCHANT-01 merchant-house / market vertical slice

The purpose is not to build a detached merchant minigame. It is to prove that the unified world can carry a material economic chain through real objects while DEC-01 actors act on incomplete information.

Target causal chain:

```text
physical stock / production capacity / contracts / credit
→ observed market information (possibly stale)
→ merchant-house beliefs and records
→ concrete purchase / sale / shipment / investment candidates
→ transport and inventory mutation
→ prices / margins / employment / credit / tax consequences
→ information emitted back into the world
```

### Required persistent objects / corrections

Implement or strengthen enough shared ownership for:

- enterprise inventories by commodity/location;
- physical cargo / shipment lots;
- purchase and sale orders or contracts;
- counterparties;
- delivery obligations and deadlines;
- transport capacity / route selection hooks;
- receivables, payables and credit exposure;
- enterprise cash and explicit transfers;
- market observations with observation day/source;
- merchant-house staff/factors and authority;
- enterprise assets/property links;
- production demand signals where relevant.

Do not create magic `merchant_power`, `trade_score`, or direct prosperity modifiers when concrete goods/money/contracts can carry the causality.

### Information rule

Merchants and institutions must plan from their own records/observations/beliefs. A market actor must be able to be wrong because:

- the price report is stale;
- cargo has not arrived;
- a route disruption is not yet known;
- an inventory record is inaccurate;
- a counterparty concealed information.

Competence should improve what records/cues are interpreted and which plans are feasible, not expose hidden world truth.

### DEC-01 integration

Add merchant behavior providers that emit concrete candidates such as:

- buy a specified quantity of a specified commodity from a specified market/counterparty;
- sell from a specified inventory lot;
- contract a specified carrier/route;
- move stock between specified warehouses/markets;
- extend/refuse/renegotiate credit with a specified counterparty;
- hire/assign a factor;
- invest in a specified warehouse/cartage/production asset;
- investigate a stale or conflicting price/supply report;
- hold liquidity rather than commit capital.

Execution belongs to economy/business/logistics owners, not the decision runtime.

## MERCHANT-01 acceptance experiment

Use the previously selected steel-vs-copper supply-shock experiment.

Inject a real increase in steel supply and observe whether ordinary causal responses can include, where technically valid:

```text
steel stock rises / price pressure
→ workshops substitute toward steel
→ copper demand changes
→ inventories and margins react
→ employment / orders / credit react
→ household income and tax exposure react
```

No scripted `copper_sector_collapse` event or direct global modifier.

The exact outcome need not be collapse. The acceptance criterion is that the engine can explain the result through real stocks, flows, contracts and actor decisions.

## Then

1. **CRAFT-01** — production dependency closure and large-workshop scheduling where justified.
2. **GROWTH-01** — backwater-count / regional growth and state-capacity vertical slice.
3. **WAR-01** — campaign logistics → battle → persistent people/property/refugee/information consequences.
4. Health + agriculture/weather + law/procedure integration.
5. Cross-system coverage/regression pass against the full World Bible.
6. Integrated ordinary one-year unattended run with all major systems active.
7. Ten-year run only after the coverage gate passes.

## Representation rule remains

Named/crystallized actors, dormant profiles and aggregate populations remain one ladder. Individuals/organizations may move up or down resolution when causal importance changes; focus characters receive no special ontology.

## Persistent architecture rule

> Caerness is one causal world. Domain owners hold truth; actors act on bounded information; concrete objects and flows carry cross-system consequences; narration describes rather than creates truth.
