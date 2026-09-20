# Caerness v0.60.0 — MERCHANT-01 Merchant-House / Market Vertical Slice Acceptance

**Date:** 17 September 2026  
**Status:** ACCEPTED WORKING CHECKPOINT  
**Schema:** 64  
**Predecessor:** DEC-01 / schema 63

## Purpose

MERCHANT-01 is the first post-DEC cross-domain economic vertical slice. It proves that commercial actors can act through real enterprise records and incomplete information, create real contracts, move conserved physical goods over the route graph, settle real cash or credit, and feed material price changes into substitutable production demand.

It is deliberately **not** a separate merchant minigame and does not yet attempt CRAFT-01's full recipe/BOM/workshop scheduling model.

## Accepted causal path

```text
enterprise authority + owned stock + market records
→ actor receives a particular offer/report
→ DEC-01 merchant provider emits concrete feasible candidates
→ actor selects a specific commercial action
→ contract / shipment / stock mutation
→ physical delivery
→ cash settlement or seller-credit receivable
→ market / production-demand response
```

No `merchant_power`, abstract trade score, hidden omniscient market lookup, or direct prosperity modifier is used as the causal carrier.

## Persistent commercial objects

Schema 64 adds:

- `enterprise_staff` — factors/staff with enterprise-specific role and authority;
- `merchant_market_observations` — observed market state with separate observation and receipt days, source and reliability;
- `merchant_trade_offers` — specific seller, stock lot, good, quantity and price;
- `merchant_offer_awareness` — which enterprise/actor actually received a given offer and when;
- `merchant_trade_contracts` — buyer/seller, quantity, price, origin/destination, settlement terms, deadline, shipment and fulfillment state;
- `commercial_cash_transfers` — explicit enterprise-to-enterprise trade settlement;
- `production_input_options` — bounded substitutable input choices for existing production sites.

`commercial_shipments` is extended with:

- `source_stock_id`;
- `recipient_enterprise_id`;
- `trade_contract_id`;
- `carrier_enterprise_id`;
- `freight_cost`.

Existing `civilian_enterprises`, `commercial_stock`, `market_conditions`, `market_goods`, `production_sites`, `credit_agreements`, `enterprise_accounts`, route/travel state and the logistics subsystem remain authoritative for their existing domains.

## Information and competence rule

Merchant decisions are bounded by enterprise-accessible records.

An actor cannot accept an unobserved offer merely because it exists in objective SQL state. Remote market reports are persisted with an observation day and a later receipt day derived from the route path; they are unusable before receipt. Old observations can remain stale even if the objective market has already changed.

Commerce competence now affects interpretation rather than access to hidden truth:

- more capable factors identify stale records sooner;
- they can justify movement on thinner observed price spreads;
- inferred commercial risk is lower where their professional judgment is stronger;
- candidate audit records include the commerce-competence value actually used.

Competence never creates an offer, current price report, route fact or inventory fact that the enterprise has not received or owns.

## DEC-01 integration

`engine.merchant.merchant_decision_candidates()` is registered as a DEC-01 provider.

Current concrete merchant candidates include:

- accept a **specific observed trade offer**;
- move a **specific owned stock lot** toward a **specific observed higher-price market**;
- commission a fresh report for a **specific stale market record**.

Execution is routed through `merchant_action` and remains domain-owned. The decision runtime selects; merchant/logistics/economy code mutates.

## Contracts, conserved cargo and settlement

An accepted offer creates a persisted contract. Dispatch subtracts the exact contracted quantity from the seller's owned `commercial_stock` and creates a route-backed `commercial_shipment`.

Delivery writes the exact physical quantity to the recipient enterprise's stock.

Two settlement paths are accepted:

### Cash on delivery

- buyer cash decreases by the contractual amount;
- seller cash increases by the same amount;
- an explicit `commercial_cash_transfers` row records the transfer;
- buyer and seller receive corresponding enterprise-account entries.

### Seller credit

- delivery creates a real `credit_agreements` receivable/payable relationship;
- the seller is the lender and buyer the borrower;
- buyer debt increases by the contractual amount;
- no magic liquidity is created.

## Steel-vs-copper acceptance experiment

The chosen cross-system experiment is implemented at the MERCHANT-01 boundary:

1. steel and copper are real market goods;
2. a metalware production site has two technically valid input options in the same substitution group;
3. a real steel supply increase raises market supply and lowers its calculated price;
4. the production-input review reweights its material mix using the new relative prices;
5. steel's share rises above copper's;
6. steel demand rises and copper demand falls through those real input shares.

This is **not** a scripted `copper_sector_collapse` event. The outcome is a material demand response to a real price change. Existing civilian/business cycles remain responsible for subsequent output, inventory, revenue/cost, cash/debt and broader economic consequences when time advances.

Full recipe/input consumption, tool dependencies, labor scheduling and detailed workshop order books are intentionally deferred to CRAFT-01 rather than being faked inside MERCHANT-01.

## Scheduler / orchestration integration

MERCHANT-01 has shared due/process functions and is included in the current hand-written scheduler immediately after logistics and before civilian resolution. The ARCH-01 ProcessRegistry parity harness also registers merchant in the equivalent block.

Registry semantic parity passes over the 45-day acceptance window. A 45-day eager-vs-lazy due-query benchmark remains essentially neutral (~1.02× in this environment), so MERCHANT-01 does not alter the prior decision to keep durable SQL scheduling authoritative.

## Migration

Schema 63 → 64:

- creates the merchant tables;
- adds the five shipment linkage fields;
- records `merchant_vertical_slice_version=1`;
- records `merchant_information_rule=enterprise_records_only`.

Migration of the actual packaged schema-63 DEC-01 database was tested directly:

- schema reaches 64;
- all pre-existing table row counts checked are unchanged;
- no enterprise staff, observations, offers or contracts are fabricated retroactively;
- shipment linkage columns are present;
- SQLite integrity check is `ok`;
- foreign-key check is clean.

## Acceptance / regression state

Passed after the final competence integration:

- `merchant01_vertical_slice_test.py` — PASS
- `dec01_information_bounded_decision_runtime_test.py` — PASS
- `belief01_claims_competence_lens_test.py` — PASS
- `pres01_low_resolution_presence_test.py` — PASS
- `rel01_directed_relationships_test.py` — PASS
- `information_test.py` — PASS
- `decision_test.py` — PASS
- `model_gateway_test.py` — PASS
- `interaction_test.py` — PASS
- `events01_territorial_event_sourcing_test.py` — PASS
- `econ01_underworld_economic_interests_test.py` — PASS
- `underworld_rackets_assets_test.py` — PASS
- `v60_phase2a_test.py` — PASS
- `v60_underworld_rebuild_test.py` — PASS
- `action_test.py` — PASS
- `smoke_test.py` — PASS
- `v56_test.py` — PASS
- ARCH-01 registry semantic/parity suite — PASS
- Python `compileall` for `engine/` — PASS
- SQLite integrity / foreign-key checks — clean

The old `v29_test.py` / `v30_test.py` scripts still contain engine-version allowlists ending at `0.59.0`; they reject `0.60.0` before exercising their logistics/economic assertions. This is a historical harness fence, not a MERCHANT-01 behavior failure, and is not mass-edited as part of this slice.

## Stop boundary

MERCHANT-01 establishes the commercial connective layer. It does **not** claim that production itself is now deep enough.

The next implementation slice is **CRAFT-01 — production dependency closure and workshop execution**, using MERCHANT-01 contracts/inventory as procurement inputs rather than inventing a second economic substrate.
