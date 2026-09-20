# Caerness v0.60.0 — WAR-01 Campaign → Battle → World Consequences Acceptance

**Date:** 17 September 2026  
**Engine:** v0.60.0  
**Schema:** 67  
**Status:** ACCEPTED WORKING CHECKPOINT

## Scope

WAR-01 closes the gap between Caerness's existing battle resolver and the persistent world around it. War is no longer only a battle record plus abstract readiness/logistics. A strategic campaign can now move the same people and goods that exist in peacetime over the same geography, fight through the existing battle owner, and project consequences back into health, households, politics, property, routes, markets and BELIEF/DEC.

The accepted chain is:

```text
political campaign objective
→ mobilized persistent force
→ real route movement
→ physical carried supply + routed resupply
→ existing battle resolver
→ aggregate force losses + named tracked consequences
→ health / death / capture / political vacancy
→ building / route / stock / market damage
→ household displacement through real migration
→ incompatible delayed battle reports
→ BELIEF-01 evidence
→ information-bounded WAR DEC candidates
→ persistent aftermath / demobilization
```

WAR-01 deliberately does **not** replace the aggregate battle engine. It surrounds it with persistent campaign/world ownership so low-relevance armies can remain compressed while already-crystallized people and important consequences remain real.

## New authoritative owners

### `war_campaign_operations`

Owns a bounded strategic operation: attacker/defender polities, commander where known, origin, target, objective, operation status, start/end and review cadence.

### `war_campaign_forces`

Owns the operation's persistent force state: polity, role, initial/available personnel, current location, route leg in progress, status, aggregate killed/wounded/captured/deserted totals and optional battle-side linkage.

A force moves through `travel_routes`; it does not teleport to the campaign target.

### `war_force_members`

Tracks only named/crystallized people who are already important enough to persist individually inside an otherwise aggregate force. This is the bridge between compressed force casualties and the existing actor/health/household/politics owners.

### `war_force_supplies` / `war_supply_ledger`

Own carried physical supplies and their flow. Mobilization/resupply withdraws actual `commercial_stock`; elapsed campaign time consumes carried supply; replenishment requires a currently traversable route back to the configured source.

The earlier 0–100 military logistics capacities remain as low-resolution/legacy compatibility state. Where WAR-01 physical supply rows exist, those rows become the material owner rather than allowing abstract capacity to mint goods.

### `war_operation_engagements`

Links an operation to one or more real battle engagements without making the operation itself the combat resolver.

### `war_battle_aftermath`

Idempotence/provenance record for projecting one resolved battle into the world exactly once.

### `war_damage_events`

Audit/provenance records for actual changes already owned elsewhere: building condition, route condition and commercial stock loss.

### `war_displacement_events`

Records households materially displaced by a battle and the existing household-migration plan used where a traversable destination exists. WAR does not maintain a parallel refugee-location system.

### `war_battle_reports`

Actor-relative official and eyewitness versions with source, reliability, issued/received/delivered days and eventual BELIEF claim/evidence IDs.

## Physical campaign / route acceptance

The acceptance fixture creates a four-location geography with a supply city, pass, contested town and refuge route.

An attacking force begins at the supply city. Its route traversal occurs in explicit legs:

```text
source city → pass → contested town
```

Force movement due-times are authoritative even when the parent operation has a slower strategic review cadence. A route leg therefore cannot be delayed merely because no high-level operation review was due that day.

A defender already at the objective can remain deployed there without requiring artificial travel.

## Physical supply acceptance

The attacking force mobilizes grain/equipment from an actual enterprise's `commercial_stock`. Mobilization immediately decreases source stock.

While the route is open, force reviews can consume carried stock and replenish from the source through the route graph. The acceptance test then closes the pass route. After closure:

- carried grain continues to be consumed;
- source stock no longer decreases from attempted resupply;
- the force's on-hand stock falls;
- shortage pressure appears in both the physical WAR layer and the compatible battle-logistics projection.

This proves that a cut supply road creates a material shortage instead of merely applying a decorative route penalty while supplies teleport through it.

A double-consumption guard ensures a physical force is not charged once by the operation review and a second time by the legacy battle-logistics review on the same day.

## Battle-resolution boundary

Combat itself remains owned by the existing `combat.py` / battlefield stack. WAR-01 links campaign forces to battle sides and consumes the battle's resolved outcome/status; it does not create a second battle resolver.

This preserves the resolution ladder:

- a distant force can remain aggregate;
- its battle can be resolved at formation/unit resolution;
- only named people already tracked in `war_force_members` require individual consequence projection;
- the engine does not materialize hundreds of anonymous soldiers merely because an aggregate casualty count exists.

## Casualty / health / political acceptance

After a resolved battle, each linked force receives persistent aggregate killed, wounded, captured and deserted counts. `personnel_available` falls and the losses remain on the force after combat.

Named force members are selected from the already-tracked subset by exposure and deterministic engagement-specific ordering. Consequences use existing owners:

- **killed** → `household_life.mark_actor_deceased`;
- **wounded** → an ordinary persistent `health_conditions.condition_kind='injury'` row carrying battle/force provenance;
- **captured** → persistent force-member capture state.

WAR-01 does not invent a parallel `battle_wound` health ontology.

The acceptance fixture places a polity ruler in the defending tracked subset. His battle death is therefore a real actor death, immediately creates political review pressure, and the existing succession machinery installs the previously established heir. The succession result is not scripted by WAR.

## Civilian / economic consequence acceptance

A sufficiently consequential battle mutates real local owners:

- an actual building loses condition and can become strained/derelict/destroyed;
- an actual route receives a `war_damage` route condition with access/delay/hazard consequences;
- an actual local `commercial_stock` row loses physical quantity;
- existing market risk and transport pressure rise.

`war_damage_events` record provenance for those mutations; they are not the authority replacing the building/route/stock owners.

This means later trade, travel, public works and household behavior see the changed world through their ordinary systems.

## Displacement acceptance

Where battle damage is high enough, existing households at the battle location may be selected for displacement. WAR identifies a traversable adjacent destination, then calls the existing household migration owner.

The acceptance fixture proves a displaced crystallized household receives a real migration plan and then moves using the ordinary ecology/travel process. WAR does not directly rewrite `households.location_id` as a teleport.

If no usable destination exists, the displacement can remain explicitly stranded rather than inventing a safe location.

## Information / BELIEF acceptance

WAR-01 produces at least two materially different versions of a battle where recipients exist:

- an **official dispatch** with its own casualty estimate/reliability;
- a **local eyewitness account** with a different estimate/framing/reliability.

Reports are queued at battle conclusion but are not knowledge merely because the report row exists. Receipt delay is derived from route travel where possible; unreachable recipients receive a conservative communication lag.

Only on delivery does a report create:

```text
claim
+ evidence/source/provenance
+ actor_evidence_access
+ actor-relative belief observation
```

The acceptance fixture verifies that the ruler who receives the official dispatch does **not** automatically receive the eyewitness evidence, and the eyewitness does not automatically receive the official dispatch.

## DEC-01 integration

The WAR behavior provider generates concrete candidates only from the actor's own campaign/force records plus delivered reports actually accessible to that actor.

Current bounded candidates include:

- attempt to resupply a specifically identified force whose own records show shortage;
- withdraw a specifically identified force whose own records show heavy loss or stalled movement.

Candidate information basis deliberately contains own-force state and received report provenance, not hidden enemy personnel/supply truth. Execution remains WAR-owned. An attempted resupply while the supply route is still cut cannot magically replenish the force.

## Aftermath acceptance

Resolved battle consequences are projected exactly once via `war_battle_aftermath`. Reprocessing the same resolved engagement does not re-kill actors, re-damage property or create duplicate displacement.

The operation enters an explicit aftermath period before closing/demobilizing surviving forces. The earlier `military_campaigns` aftermath layer remains for readiness/recovery compatibility.

World consequences remain after demobilization: dead/injured actors, damaged buildings/routes, lost stock, displaced households and delivered beliefs are not reset when the campaign row closes.

## Scheduler / architecture integration

WAR retains its existing scheduler position rather than adding a second world process. `next_war_due_day()` now also considers:

- operation reviews;
- force route/supply reviews;
- battle report receipt dates.

The operation review runs when either the operation itself **or one of its forces** is due, preventing slow strategic cadence from blocking real route-leg completion.

ARCH-01 functional parity/order/one-off/cancellation/restart acceptance passes with WAR-01 in place. The historical ARCH script's 250-day benchmark tail remains intentionally expensive and can exceed the execution harness limit; no new scheduler architecture was introduced by WAR-01.

## Migration acceptance

The actual clean schema-66 GROWTH checkpoint database was copied and migrated to schema 67.

Verified after migration:

- schema reports 67;
- every new WAR-01 operation/force/supply/aftermath/damage/displacement/report table contains **zero** rows;
- `PRAGMA integrity_check = ok`;
- zero foreign-key violations.

Old campaigns therefore gain WAR-01 machinery without fabricated wars, forces, casualties, property damage, refugees or battle reports.

## Regression status

Green after WAR-01:

- WAR-01 campaign/battle/world-consequence acceptance;
- GROWTH-01;
- CRAFT-01;
- MERCHANT-01;
- DEC-01;
- BELIEF-01;
- PRES-01;
- REL-01;
- information/privacy;
- interactions;
- model gateway;
- EVENTS-01;
- ECON-01;
- rackets/assets;
- v0.60 Phase 2A;
- v0.60 underworld rebuild;
- ordinary action test;
- smoke/dormant-world test;
- v0.56 cultivation regression;
- ARCH-01 functional parity/order/one-off/cancellation/restart suite.

Historical `v41_test.py` still hard-codes an engine-version whitelist ending at `0.59.0`, so it exits on the version assertion before exercising its old logistics behavior. This is the same stale historical-test fence seen in later slices and is not treated as a WAR-01 behavioral regression.

## Deliberate boundary

WAR-01 proves one bounded **field battle** campaign/world-consequence vertical slice. It does not yet attempt a complete siege engine, naval warfare model, raid-specific resolver, or tactical command rewrite.

Agricultural field/crop destruction is also not yet a first-class owner because the dedicated agriculture/weather subsystem is the next integration work. WAR currently damages existing property, routes, stock and market conditions; future agriculture integration should let armies burn/requisition actual harvest/stores through that domain rather than adding a WAR-only farm meter.

Likewise, battlefield injury uses the existing health-condition owner; the next health integration pass can deepen condition courses, treatment capacity, rehabilitation and disability without moving health authority into WAR.

## Stop boundary

WAR-01 is accepted and banked. War now concentrates the same people, goods, roads, institutions, households, health and information that exist before and after battle.

The next slice is **INTEGRATION-01 — health + agriculture/weather + law/procedure integration**, followed by the cross-system coverage gate and integrated one-year unattended world run.
