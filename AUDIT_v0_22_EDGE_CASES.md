# v0.22 Adversarial Edge-Case Audit

**Audited release:** v0.22.0  
**Scope:** environment profiles, seasons, temporary conditions, current carrying capacity, routes, travel, household migration, health handoff, civilian integration.

The audit was run before treating v0.22 as the next baseline. It tests actual runtime behavior, not merely the existence of schema or APIs.

## Findings and hardening

### 1. No invented environmental canon

A clean campaign contains zero environment profiles, seasonal windows and travel routes. The engine does not seed a four-season calendar, climate labels, roads or weather events. Invalid seasonal windows outside the campaign-defined year are rejected. Wrap-around windows are supported without inventing calendar names.

**Result:** PASS.

### 2. Route directionality and closures

One-way routes are one-way. A route condition with zero accessibility makes the route unavailable. If an onward route closes after a journey has already started, the traveller reaches the current segment endpoint and then stalls instead of teleporting through the closure. After the closure expires, the route is recalculated and travel can resume.

**Result:** PASS.

### 3. Temporary environmental pressure does not become permanent climate

Temporary conditions affect only their active date interval. Once their end date passes, their travel/production/health/current modifiers no longer apply and the record is marked ended during environmental processing.

**Result:** PASS.

### 4. Current carrying capacity never becomes negative

Heavy current use may exceed nominal carrying capacity. Available capacity floors at zero; load itself remains explicit rather than being silently clipped. Replenishment reduces load over story time but cannot drive it negative.

**Result:** PASS.

### 5. Household travel consistency

Household travel updates the household location and all active household members together. Active household membership remains authoritative; former members are not moved automatically.

**Result:** PASS.

### 6. Scheduled migration previously bypassed geography

The initial v0.22 pass exposed a cross-version contradiction: v0.19 scheduled household migration still teleported households on the planned day, bypassing newly established route geography.

This was fixed during the audit. Migration now enters `in_transit` and uses a real travel plan whenever relevant route geography has been crystallized. An unavailable route delays migration instead of bypassing the blockage. Structural instant relocation remains only when the route layer for those locations has not been crystallized.

**Result:** FIXED / PASS.

### 7. Duplicate travel commitments

An actor or household cannot have two simultaneous active/stalled travel plans. A second travel start is rejected. Scheduled household migration also rejects replacement while the household is already in transit.

**Result:** PASS.

### 8. Environmental health ownership

High route hazard can create an abstract travel-exposure fatigue condition. Ecology does not attempt to heal it, assign specialist treatment or resolve disability. Those remain owned by v0.20 health.

**Result:** PASS.

### 9. Death during travel

A dead actor's active travel plan is cancelled when next processed; the actor cannot later arrive because an old travel timer fires.

**Result:** PASS.

### 10. Civilian economy wiring

Environmental production factors feed the existing production resolver. Environmental travel friction feeds ordinary market transport pressure. The regression test proves the resulting production and market state changes through shared story-time advancement.

**Result:** PASS.

## Resolution boundary retained

A route condition that begins while a traveller is already physically inside a segment does not retroactively rewrite distance already traversed. The condition is reconsidered at the next route node. This is deliberate resolution granularity rather than an omniscient continuous-position simulator.

## Audit result

`v22_test.py` and `v22_edge_test.py` pass, followed by the complete cumulative regression suite from v0.1 through v0.22.

**Result: PASS.** v0.22.0 is suitable as the baseline for v0.23.
