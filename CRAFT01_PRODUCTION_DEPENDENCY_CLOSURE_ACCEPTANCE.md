# Caerness v0.60.0 — CRAFT-01 Production Dependency Closure Acceptance

**Date:** 17 September 2026  
**Status:** ACCEPTED WORKING CHECKPOINT  
**Schema:** 65  
**Predecessor:** MERCHANT-01 / schema 64

## Purpose

CRAFT-01 replaces tracked-workshop “material access means output happens” with an explicit physical production chain while preserving low-resolution aggregate production for background sites.

The tracked causal path is now:

```text
recipe + technically valid substitutions
+ owned/arrived commercial stock
+ required facility/equipment
+ craft labor / competence
→ production order
→ explicit blocking or input selection
→ conserved input reservation/consumption
→ timed production
→ conserved finished commercial stock
→ MERCHANT-01 sale / shipment / settlement
```

Tracked production never creates material merely from `material_access` or a hidden production-success score.

## Schema 65 production owners

CRAFT-01 adds:

- `craft_recipes` — output good, batch yield, duration and competence domain;
- `craft_recipe_inputs` — required input groups and technically valid substitution options;
- `craft_recipe_facility_requirements` — required equipment/facility classes, capacity and condition;
- `craft_facilities` — real enterprise/location equipment capacity;
- `craft_site_recipes` — recipes actually executable at a production site;
- `craft_site_workers` — tracked worker assignments and capacity shares;
- `craft_production_orders` — queued/blocked/in-progress/completed production work;
- `craft_input_reservations` — exact stock lots and quantities reserved/consumed;
- `craft_output_lots` — order-linked finished output and quality;
- `craft_order_events` — inspectable order history.

`production_sites` gains `production_mode`:

- `aggregate` — existing coarse resolver remains authoritative;
- `tracked` — CRAFT-01 owns production and the legacy aggregate resolver is prohibited from minting parallel output.

`commercial_stock` remains the physical inventory owner. CRAFT-01 deliberately introduces no private “craft inventory.”

## Dependency closure

`validate_recipe_dependency_closure()` checks required input groups for at least one physical source/path at tracked resolution:

- enterprise-owned stock;
- an open stock-backed merchant offer reachable over actual route geography;
- an active production site producing the required input.

Enterprise-specific closure also checks required facilities at the enterprise’s real location.

The acceptance suite proves both:

- a recipe with no `forge` is structurally incomplete for that workshop;
- a required material with no stock, offer, producer, or transport-source path fails as `input_group:<group>:no_source_path`.

The engine does not invent a supplier to repair closure.

## Substitution and price choice

CRAFT-01 promotes MERCHANT-01’s substitution idea from a demand signal into actual batch material choice.

For each substitution group:

1. only recipe-authorized materials are considered;
2. the workshop uses enterprise-accessible received price observations where available;
3. preference weights can break/shape choices where records are incomplete;
4. the selected material must physically exist in sufficient owned stock before production starts.

A key guardrail is intentional: if steel is the workshop’s chosen valid material because its received price record makes it preferable, the order does **not** silently consume expensive copper merely because copper is already on the shelf. It becomes a steel procurement shortage instead.

Price information affects choice; it never makes an invalid substitute valid.

## Staff and competence

Tracked `craft_site_workers` use the existing competence system.

The recipe names a competence domain (normally `craft`, with specialties carried by existing competence rows). Where workers are explicitly assigned, their actual domain competence contributes to execution and quality. Where no worker identities are tracked, the production site’s existing coarse `skilled_labor` value remains the low-resolution fallback.

Competence can improve execution/quality. It cannot conjure missing stock or equipment.

## Order execution

A production order can be:

- `queued`;
- `waiting_input`;
- `waiting_facility`;
- `waiting_labor`;
- `in_progress`;
- `completed`;
- `cancelled`;
- `blocked`.

Blocking state persists an inspectable reason and structured detail.

When an order can start:

- exact required quantities are subtracted from their `commercial_stock` lots;
- the consumed quantities are written to `craft_input_reservations` as the conservation ledger;
- completion time derives from recipe duration, site capacity, efficiency, craft competence and facility condition;
- completion creates exact finished quantity in `commercial_stock` and a `craft_output_lots` row;
- quality is derived from actual tracked execution inputs rather than a free narrative label.

## DEC-01 / MERCHANT-01 procurement integration

A `waiting_input` order can create a CRAFT-01 decision candidate only when:

- the actor has real authority over the enterprise;
- the missing material is the chosen recipe input;
- the enterprise actually received a specific merchant offer;
- that offer is still open;
- the quantity is sufficient;
- enterprise cash can support the purchase under the proposed settlement.

The candidate is tagged `provider_key='craft'`, but its execution kind remains `merchant_action`. CRAFT identifies the production need; MERCHANT owns contracts, dispatch, delivery and settlement.

This preserves domain ownership instead of creating a second procurement system.

## Accepted end-to-end dependency chain

The final CRAFT-01 experiment is deliberately two-stage:

```text
iron ore
+ charcoal
+ furnace
+ tracked smelting labor
→ real steel intermediate stock
→ steel offer backed by that produced stock
→ workshop receives the specific offer
→ steel becomes preferable to copper after the MERCHANT-01 supply/price change
→ workshop order blocks for missing chosen steel
→ DEC-01 exposes a concrete procurement candidate
→ merchant contract
→ physical cargo over a real route
→ buyer stock receives delivered steel
→ exact steel + charcoal consumption
+ forge
+ tracked smithing competence
→ finished tool stock
→ finished-stock merchant offer
→ second physical shipment
→ contractual cash settlement / enterprise revenue
```

The acceptance therefore proves an intermediate good is itself produced from inputs before becoming the input to the next workshop.

## Accounting / conservation

The tool workshop’s steel purchase is recorded by MERCHANT-01 as a real enterprise purchase on delivery.

Finished tools are sold through an ordinary MERCHANT-01 contract; physical output leaves the workshop’s `commercial_stock`, travels as cargo, arrives at the buyer, and contractual cash settlement creates workshop revenue.

The CRAFT slice therefore does not fake “margin” from an abstract production outcome. The purchase and sale sides are both ordinary economic records.

## Aggregate compatibility

Low-resolution sites remain valid.

A dedicated compatibility check proves:

- an `aggregate` production site continues creating coarse inventory through the existing civilian resolver;
- a `tracked` site bound to a CRAFT recipe creates **zero** output through that resolver.

This is the resolution firewall needed to avoid double-counting while retaining background economy performance.

## Scheduler / ProcessRegistry integration

CRAFT-01 adds `next_craft_due_day()` and `process_due_craft()`.

The current execution order is:

```text
logistics
→ merchant
→ craft
→ civilian aggregate production
```

This allows delivered material to become real stock before tracked production resolves, then prevents the later aggregate resolver from duplicating tracked output.

ARCH-01 registry parity was updated with the craft process and passes over the existing parity scenario.

45-day eager-vs-lazy registry benchmark after CRAFT-01:

- eager SQL due requery: ~1.135 s;
- lazy registry cache: ~1.107 s;
- ratio: ~1.03×.

This does not alter the accepted architecture: durable SQL remains scheduling authority.

## Migration

Schema 64 → 65:

- adds the CRAFT tables;
- adds `production_sites.production_mode` defaulting to `aggregate`;
- records `craft_vertical_slice_version=1`;
- records `craft_stock_rule=commercial_stock_conserved`.

Migration of the packaged schema-64 database was tested directly:

- schema reaches 65;
- no recipes, facilities, workers or production orders are fabricated retroactively;
- existing production sites, when present, remain `aggregate` unless explicitly bound to a tracked recipe;
- SQLite integrity check is `ok`;
- foreign-key check is clean.

## Regression state

Passed after final integration:

- `craft01_production_dependency_closure_test.py` — PASS;
- `merchant01_vertical_slice_test.py` — PASS;
- `dec01_information_bounded_decision_runtime_test.py` — PASS;
- `belief01_claims_competence_lens_test.py` — PASS;
- `pres01_low_resolution_presence_test.py` — PASS;
- `rel01_directed_relationships_test.py` — PASS;
- `information_test.py` — PASS;
- `decision_test.py` — PASS;
- `model_gateway_test.py` — PASS;
- `interaction_test.py` — PASS;
- `events01_territorial_event_sourcing_test.py` — PASS;
- `econ01_underworld_economic_interests_test.py` — PASS;
- `underworld_rackets_assets_test.py` — PASS;
- `v60_phase2a_test.py` — PASS;
- `v60_underworld_rebuild_test.py` — PASS;
- `action_test.py` — PASS;
- `smoke_test.py` — PASS;
- `v56_test.py` — PASS;
- ARCH-01 registry semantic/parity test — PASS;
- aggregate-vs-tracked production compatibility check — PASS;
- Python compilation of modified engine modules — PASS;
- SQLite integrity / foreign-key checks — clean.

Several older historical test files still contain literal engine-version allowlists ending at `0.59.0`; as in DEC-01/MERCHANT-01, those stop before exercising behavior when run unchanged under `0.60.0`. They are not mass-edited merely to relax old version fences.

## Stop boundary

CRAFT-01 does **not** attempt to solve every workshop as a job-shop optimization problem.

Ordinary tracked workshops use the lightweight order resolver implemented here. A later large smithy, arsenal, shipyard or similarly capacity-constrained institution may justify a bounded OR-Tools/PyJobShop-style planner, but only when a concrete vertical slice requires it.

The next implementation slice is **GROWTH-01 — backwater-count / regional growth and state-capacity integration**.
