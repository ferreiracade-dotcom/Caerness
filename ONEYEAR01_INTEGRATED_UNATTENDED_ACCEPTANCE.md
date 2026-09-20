# Caerness v0.60.0 — ONEYEAR-01 Integrated Unattended World Acceptance

**Date:** 17 September 2026  
**Engine:** v0.60.0  
**Schema:** 70  
**Status:** **ACCEPTED — strengthened conditional-domain trigger gate passed; TENYEAR-01 may begin.**

## Purpose

ONEYEAR-01 is the integration gate between World-Bible/system coverage and the first real ten-year unattended run. It must prove more than that the scheduler reaches day 365. It must show that ordinary world systems actually operate together, that physical and informational authority boundaries survive a long run, that persisted restart is deterministic, and that systems which happen to remain quiet are truly dormant rather than silently broken.

## Ordinary 365-day run

The first attempted year correctly exposed an opening-world integration defect: MERCHANT, CRAFT and GROWTH mechanisms existed but ordinary starting-world activation left them effectively ceremonial. The gate was not weakened. Opening activation was corrected so existing merchant principals receive bounded commercial authority/records, the Dovell productive footprint receives a tracked workshop with conserved inputs/order, and all seven active polities receive public-finance owners.

The corrected fresh unattended world then reached day **365** with:

- **425** merchant market observations;
- **62** trade offers;
- **25** merchant contracts, **24 fulfilled**;
- **11** physical shipments;
- **1** tracked craft recipe and **1 completed tracked order/output lot**;
- **7** live public treasuries;
- **383** fiscal ledger entries;
- **1,464** regional growth snapshots;
- **9** physical harvests;
- **1,123** resolution transitions;
- all required production process families scheduled;
- **0** canon/hidden-truth hits in decision information bases;
- no negative tracked stock, invalid shipment quantities, project overconsumption, negative public debt, or negative harvest quantities;
- `PRAGMA integrity_check = ok`;
- **0** foreign-key violations.

The year was naturally peaceful: no WAR operation, lawsuit or active health condition happened spontaneously. This is acceptable only after the trigger audit below.

## Persisted restart determinism

The exact day-180 database was copied and independently replayed to day 365. The main branch and replay branch matched hash-for-hash across every substantive state group compared, including:

- actors;
- enterprises;
- commercial stock;
- merchant offers/contracts/shipments;
- craft orders/output;
- public treasuries/fiscal ledger/regional state;
- harvests;
- underworld organizations;
- post-day-180 events;
- post-day-180 resolution transitions;
- post-day-180 decision evaluations.

**Result: zero substantive differences.**

## Conditional-domain manufactured-trigger audit

A quiet year cannot prove that a conditional system is healthy. Three independent copies of the accepted day-365 save were therefore created. Each copy received exactly one bounded causal trigger and then used the real production owners. None of these branches is part of the clean checkpoint.

### HEALTH — PASS

A real active Saltmere merchant principal, **Amory Selwick**, received a serious injury.

The production scheduler:

1. detected the severe condition;
2. created care demand automatically;
3. selected the real opening Saltmere structural care network;
4. used its aggregate medicine provider pool rather than inventing a named doctor;
5. treated the request on day **367**.

The health branch retained clean invariants/integrity. HEALTH was therefore genuinely dormant in the peaceful year, not broken.

### LAW — PASS

A real commercial dispute was manufactured between the existing Saltmere merchant enterprises **House Selwick** and **House Morrick**.

The real Windmere ordinary jurisdiction/court:

1. accepted the contract matter;
2. processed evidence through procedural delays;
3. reached a claimant judgment;
4. awarded **2.0**;
5. enforced **2.0** through real enterprise cash;
6. closed the case with an enforcement step.

The law branch retained clean invariants/integrity. LAW was therefore genuinely dormant in the peaceful year, not broken.

### WAR — PASS after two integration fixes

The manufactured WAR branch deliberately used the actual opening world:

- attacker: **Windmere**;
- defender: **Underheaven Empire**;
- origin: **Saltmere**;
- target: **Toll's Reach**;
- route: the real Saltmere–Toll's Reach route;
- supply source: real House Dovell physical grain stock.

This test exposed two defects that the isolated WAR-01 fixture had not revealed.

#### Fix 1 — newly created same-day WAR work

A campaign created at the current world day had `next_review_day = current_day`, while the simulation cursor asks process owners for due work strictly after the cursor day. Without a bridge, a newly created campaign could wait until terminal catch-up of a multi-day advance before entering movement.

`next_war_due_day()` now treats already-due newly created WAR work as due on the **next simulated day**. Direct same-day `process_due_war()` remains valid.

#### Fix 2 — strategic review restarted active movement

WAR strategic reviews occur more frequently than some route legs. `_review_force_movement()` previously called `_begin_force_segment()` on any force with status `marching`, even when that force was already traversing a live segment. Each strategic review could therefore reset the same route leg and push its arrival day forward indefinitely.

An active route segment is now authoritative until its `segment_due_day`. Strategic reviews may inspect the force and supply state, but they cannot restart an in-progress leg.

#### Retest result

After both fixes:

- the Windmere force reached Toll's Reach and became deployed;
- House Dovell grain stock fell from **12.49248** to **7.29248** through mobilization/consumption/resupply;
- the engagement resolved;
- Windmere aggregate losses: **5 killed, 17 wounded**;
- Underheaven aggregate losses: **12 killed, 20 wounded**;
- **2** battle reports were created;
- **4** war-damage events were projected;
- the real Toll's Reach warehouse condition fell from roughly **53.5** to **33.0**;
- integrity and foreign keys remained clean.

The original WAR-01 acceptance suite still passes after these fixes.

## Regression after trigger fixes

Green after the WAR scheduler/movement corrections:

- WAR-01;
- INTEGRATION-01;
- COVERAGE-01;
- GROWTH-01;
- CRAFT-01;
- MERCHANT-01;
- DEC-01;
- BELIEF-01;
- PRES-01;
- REL-01.

## Schema 70 clean-checkpoint rule

Schema 70 records engine capability acceptance only:

- `one_year_unattended_acceptance = passed`;
- `one_year_unattended_acceptance_version = 2`;
- `conditional_domain_trigger_audit = health_law_war_passed`;
- `ten_year_gate_rule = coverage_plus_accepted_one_year`.

The clean packaged database remains at **day 0** and contains **zero** diagnostic-year or manufactured-trigger WAR operations, battle aftermath, health conditions/care requests, law cases/judgments, merchant contracts, public treasury history, craft orders, or harvest history.

## Decision

**ONEYEAR-01 accepted.**

A quiet conditional domain is no longer accepted merely because its process is scheduled. If an ordinary run does not naturally exercise an important conditional owner, an acceptance branch must manufacture a bounded causal trigger and prove that the real owner wakes, executes, and persists its consequences.

`ten_year_gate()` now passes on an appropriately activated accepted world. The next milestone is **TENYEAR-01**.
