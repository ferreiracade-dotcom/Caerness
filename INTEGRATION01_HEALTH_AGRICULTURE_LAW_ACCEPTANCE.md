# Caerness v0.60.0 — INTEGRATION-01 Health + Agriculture + Law Acceptance

**Date:** 17 September 2026  
**Engine:** v0.60.0  
**Schema:** 68  
**Status:** ACCEPTED WORKING CHECKPOINT

## Scope

INTEGRATION-01 closes the three large domain-owner gaps deliberately left after WAR-01:

1. persistent health condition course **plus separate treatment access/capacity**;
2. agriculture/weather/harvest as a physical food-production owner;
3. general law/jurisdiction/procedure beyond underworld-specific policing.

The point is not to create three detached minigames. Each owner reuses existing world truth:

```text
HEALTH
condition truth
→ care request
→ real local care site/provider capacity
→ treatment only if capacity exists
→ condition progression/recovery/disability/death

AGRICULTURE
ecological/weather truth + field + labor
→ harvest quantity
→ physical commercial_stock
→ local market supply/price
→ GROWTH food stress / downstream behavior

LAW
location/polity
→ applicable jurisdiction + rule
→ office/capacity/corruption
→ complaint/evidence/hearing
→ judgment/remedy/enforcement
→ real enterprise cash/debt + BELIEF notice
```

## HEALTH-01 — condition course and treatment capacity

The existing `health_conditions` owner remains authoritative for pathology. INTEGRATION-01 adds care-access owners rather than moving condition truth into a hospital table.

### New persistent owners

- `health_care_sites`: real treatment locations with local quality and finite daily capacity;
- `health_provider_assignments`: which living actors actually provide a competence domain at a site and how much daily capacity they have;
- `health_care_requests`: patient/condition/treatment demand, selected site/provider, delay, and eventual treatment day.

### Guardrail

A condition does **not** ask whether a doctor exists when it progresses. It follows its own recovery/progression/fatality course. Care capacity is resolved separately and creates an ordinary `medical_treatments` row only when a real site and sufficiently competent provider are available.

This preserves the intended split:

```text
condition progression ≠ healthcare availability
```

### Autonomous care demand

Severe unresolved conditions can autonomously create a care request only where a real local active/strained care site exists. No site means no magically invented doctor or treatment.

Treatment kind is bounded by the existing health ontology:

- ordinary injury/illness → ordinary medicine;
- very severe injury → surgery;
- Vein/Core/Rupture conditions or explicit Vein-specialist requirements → vein mending.

The provider must satisfy the existing competence threshold. Daily site and provider capacity are both consumed by treated requests.

### Acceptance scenario

Two actors begin with comparable serious fractures. One can reach an active high-quality site with a qualified physician; the second explicitly seeks a closed ward.

Across the same story-time reviews:

- the first receives real treatment;
- the second remains waiting and accumulates actual calendar delay;
- the untreated fracture becomes materially more severe than the treated one;
- reopening the ward later allows treatment to begin at that later day rather than retroactively healing the missed period.

This proves delayed/unavailable care can change health outcomes without the condition owner knowing provider availability.

## AGRI-01 — fields, weather and physical harvests

Agriculture now has a first-class owner rather than being only a generic production factor.

### New persistent owners

- `agriculture_fields`: enterprise-owned field, crop good, location, area, normal yield, soil/labor, harvest calendar and current condition;
- `agriculture_disruptions`: war/fire/flood/drought/pest/requisition/other yield disruptions with explicit time windows and provenance;
- `agriculture_harvests`: expected vs actual physical output, ecology/labor/disruption factors, and the resulting stock row.

### Shared ecology

AGRI-01 does not create a second weather system. It consumes the existing `ecology.environment_effects()` / `production_factor()` owner, including seasonal windows and temporary environmental conditions.

### Physical conservation

A harvest creates or increments the enterprise's ordinary `commercial_stock` for the crop good. There is no separate agriculture inventory.

The market receives an availability shock derived from the harvest's deviation from expected output. Market supply/price therefore changes through the existing market owner while the actual grain quantity remains physical stock.

### Growth coupling

GROWTH's existing food-stress calculation reads the same market condition. A poor harvest can therefore raise food stress without an `famine += 1` script.

### War coupling

WAR-01 now damages agriculture through the agriculture owner. A sufficiently consequential battle at a location containing a tracked field creates a timed `agriculture_disruptions(disruption_kind='war')` row and a WAR provenance event. WAR does not own a parallel farm-damage meter.

### Acceptance scenario

A tracked grain field experiences a real ecological drought (`production_factor=.25`). At harvest:

- actual physical grain is below 30% of expected output;
- the harvested quantity appears in `commercial_stock`;
- local market supply falls;
- local grain price rises;
- the same location's derived GROWTH food-stress state rises.

This is a causal chain from ecology → field → physical food → market → regional condition.

## LAW-01 — jurisdiction, rules, procedure and enforcement

The prior engine already had local underworld policing/case rows. Those remain an investigative/enforcement source for crime. INTEGRATION-01 adds a general law owner for ordinary commercial/property/criminal/administrative/family matters.

### New persistent owners

- `law_jurisdictions`: imperial/kingdom/charter/local/Churn/institutional scopes with location/polity and priority;
- `law_rules`: matter-specific rule, evidence threshold and default remedy;
- `law_offices`: office location, presiding actor/institution, capacity, integrity and corruption pressure;
- `law_cases`: parties, subject, claim, applicable jurisdiction/rule/office, evidence score and procedural stage;
- `law_case_evidence`: concrete submitted records/evidence;
- `law_judgments`: finding/remedy/award/enforcement state;
- `law_enforcement_steps`: actual attempts to realize the remedy.

### Jurisdiction resolution

`resolve_jurisdiction()` chooses among applicable active rules using scope specificity and explicit priority:

```text
exact location/charter
> controlling polity/kingdom
> global/default jurisdiction
```

This prevents every economic/criminal subsystem from embedding its own legal `if` statements.

### Capacity and corruption

Procedure is not instant. Cases progress through due-dated stages. Office capacity determines delay; insufficient capacity can stall a case. Integrity and corruption alter the effective evidentiary evaluation at hearing, and an explicit favored-side office bias can further distort it.

### Enforcement

A damages judgment between enterprises transfers actual enterprise cash through `commercial_cash_transfers`. If the payer lacks enough cash, the unpaid amount becomes real debt and the judgment remains only partially enforced.

The law owner therefore cannot simply write "damages paid" when there is no money.

### BELIEF boundary

An entered judgment creates a law claim/evidence record and grants legal notice to the actual party actors/enterprise owners. The judgment is not injected into all actors as global truth.

### Acceptance scenario

A town lies inside a kingdom but also has its own charter jurisdiction. Both have contract rules. The charter has the more specific scope and is correctly selected.

A merchant claim then passes through:

```text
complaint
→ evidence
→ hearing
→ decided
→ enforcement
→ closed
```

with separate review days rather than one instantaneous call. Strong written evidence produces a claimant judgment; the awarded 40 units are transferred from the respondent enterprise's real cash to the claimant's real cash, and both owner actors receive the judgment evidence.

The same office is then degraded to capacity 5. A second well-evidenced case stalls rather than bypassing the collapsed docket.

## Scheduler integration

Ordinary process order now includes:

```text
world
→ ecology
→ agriculture
→ logistics
→ merchant
→ craft
→ civilian
→ growth
→ underworld
→ underworld medicine
→ law
→ war
→ groundbinding
→ health
→ ...
```

Important ordering consequences:

- ecology/weather is current before harvest resolution;
- harvest stock/market effects exist before later civilian/GROWTH reviews;
- merchant breaches and underworld evidence can exist before the law process;
- WAR can create health injuries and agriculture disruptions through their authoritative owners;
- health then resolves treatment/condition consequences.

The ARCH-01 functional parity, one-off, cancellation and restart suite passes with agriculture and law registered in the corresponding registry order.

## Migration acceptance

The actual schema-67 WAR checkpoint database was migrated to schema 68.

Verified:

- previous actor/enterprise/health/WAR counts unchanged;
- zero fabricated care sites/requests;
- zero fabricated fields/harvests;
- zero fabricated jurisdictions/cases/judgments;
- `PRAGMA integrity_check = ok`;
- zero foreign-key violations.

Existing campaigns therefore gain the new machinery without invented medical, agricultural or legal history.

## Regression status

Green after INTEGRATION-01:

- INTEGRATION-01 health/agriculture/law acceptance;
- WAR-01;
- GROWTH-01;
- CRAFT-01;
- MERCHANT-01;
- DEC-01;
- BELIEF-01;
- PRES-01;
- REL-01;
- information/privacy;
- EVENTS-01;
- ECON-01;
- rackets/assets;
- v0.60 underworld rebuild;
- v0.60 Phase 2A;
- ARCH-01 functional registry parity/order/restart/cancellation.

## Deliberate boundaries

This slice does not claim every disease, crop, statute, court or legal remedy is exhaustively modeled.

- Epidemic/population transmission remains a separate aggregate problem from individual condition course.
- Agriculture currently proves field/harvest/weather/war coupling; livestock, irrigation networks, tenancy and detailed crop rotations can be added when a concrete scenario requires them.
- Law currently proves general jurisdiction/procedure/enforcement; detailed canon-specific legal codes remain data content, not hard-coded universal rules.
- Underworld policing remains separate from general adjudication rather than being rewritten into LAW-01.

## Stop boundary

INTEGRATION-01 is accepted and banked.

The next step is **COVERAGE-01 — fresh World Bible → engine coverage gate**, including proof that domains are not merely implemented but populated/running where appropriate, and proof of causal promotion/down-resolution for people and institutions.

Only after that gate passes should the integrated ordinary one-year unattended run begin.
