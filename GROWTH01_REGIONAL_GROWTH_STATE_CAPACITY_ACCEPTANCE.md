# Caerness v0.60.0 — GROWTH-01 Regional Growth / State Capacity Acceptance

**Date:** 17 September 2026  
**Engine:** v0.60.0  
**Schema:** 66  
**Status:** ACCEPTED WORKING CHECKPOINT

## Scope

GROWTH-01 implements the bounded regional/state-capacity vertical slice planned after
CRAFT-01. Its purpose is not to create a city-builder or a universal prosperity meter. It
connects existing world objects so a county can improve, stall, overextend or regress for
causal reasons.

The implemented chain is:

```text
real economic activity
→ conserved tax/toll revenue
→ public treasury / debt
→ specific public project or security commitment
→ real commercial material + household labor + time + cash
→ route/building/administrative consequence only on completion
→ changed market-access/security experience
→ business/household response and routed migration
```

Administrative decisions are information-bounded:

```text
objective regional state
→ delayed administrative report
→ BELIEF-01 claim/evidence
→ DEC-01 concrete candidate
→ ruler decision
→ GROWTH-owned execution
```

## New authoritative owners

### `regional_public_treasuries`
Owns public cash, debt, tax/toll rates, debt carrying cost, cadence and fiscal condition.
Cash cannot go negative. Debt is explicit rather than a generic treasury-pressure modifier.

### `regional_fiscal_entries`
Append-style public ledger for business tax, trade toll, borrowing, debt service, project
material, public-work wages and security payroll. The acceptance test checks opening cash +
ledger inflows − ledger outflows against treasury cash.

### `regional_public_projects`
Owns a specific public project and its required cash, material, labor, location/route,
progress, blocking reason and completion effects. Current bounded kinds are road repair,
security post, market warehouse and administrative office.

### `regional_project_materials` / `regional_project_labor`
Projects purchase actual `commercial_stock` from actual enterprises and pay actual households.
Material stock falls; supplier enterprise cash/revenue rises; household liquidity rises; public
cash falls. Intent alone cannot satisfy a requirement.

### `regional_security_assignments`
A recurring public commitment with a real monthly cost. When funded it can gradually reduce
specific crime/banditry/insecurity route conditions. When the treasury cannot pay it becomes
`unfunded` and produces no free security effect.

### `regional_administrative_reports`
Observed regional state is delayed before reaching a ruler. Delivery creates BELIEF-01
claim/evidence records. The GROWTH decision provider only reasons from delivered reports or
owned treasury/project state, not hidden route truth.

### `regional_growth_snapshots`
Rebuildable diagnostic projections of population estimate, households, businesses, route
access/hazard, trade, food stress, public cash/debt and fiscal flow. They are observational
history, not an authoritative growth score.

### `regional_migration_responses`
Records why a materially pressured household was scheduled to move. Actual movement remains
owned by the existing household-migration + ecology travel machinery.

## No prosperity meter

There is no `prosperity`, `development_score`, or equivalent authoritative field in the
GROWTH-01 state. `regional_state()` derives current condition from shared domain objects.
`location_commercial_context` is updated only as a low-resolution, rebuildable projection for
existing business ecology; it is not the source of regional truth.

## Fiscal conservation acceptance

The funded test begins with a configured public treasury and realized enterprise revenue.
Business tax transfers cash out of the enterprise and into the treasury. Public materials,
wages and security costs transfer cash back out through explicit ledger entries.

The acceptance invariant is:

```text
opening public cash
+ fiscal inflows
- fiscal outflows
= current public cash
```

for the no-borrowing funded fixture.

A duplicate-toll guard also prevents one fulfilled contract from being charged twice merely
because both endpoints lie in the same polity.

## Infrastructure acceptance

The ruler receives a delayed report describing a genuinely bad route. Before report delivery,
no GROWTH candidate appears. After delivery, DEC-01 exposes concrete actions tied to the report's
claim/evidence IDs, including repairing that exact route and funding security on it.

Authorizing road repair does **not** immediately improve the route. The project must:

1. buy actual local construction material from `commercial_stock`;
2. pay assigned local household labor;
3. meet its non-material cash requirement over successive reviews;
4. reach full tracked requirements.

Only then does completion raise the actual `travel_routes.reliability`, reduce base travel time,
and resolve physical disrepair/washout/bridge/road-damage conditions. Physical repair does not
erase banditry; that is owned by funded security.

## Security acceptance

A recurring route-security assignment reduces only specific criminal/insecurity route
conditions while the public treasury actually pays its monthly cost. A separate constrained
case proves that an unaffordable deployment becomes `unfunded` and leaves banditry active.

## Household/migration acceptance

Public-works wages raise real household liquidity. After regional accessibility/security
improves, a deliberately pressured neighboring household can receive a migration plan because
its experienced destination appeal is materially better. That plan then uses the existing
household migration owner and real route travel; the household is not teleported by GROWTH-01.

## Long-horizon bounded experiment

The acceptance test runs two ten-year bounded regional cases. This is **not** the final
integrated ten-year world simulation.

### Funded/active case

Recurring realized commercial revenue supplies an actual tax base. The previously repaired
route remains improved, the treasury remains solvent without debt, and monthly/quarterly state
snapshots remain explainable through source objects.

Observed acceptance values in the final run:

- initial route accessibility: **55.0**;
- later route accessibility: **100.0**;
- ending public cash: **389.1**;
- public debt: **0**.

These are fixture results, not global balancing targets.

### Constrained/debt case

The second county begins with minimal cash, substantial debt, a project requiring a material
with no supplier/stock path, and a security commitment it cannot afford. Across ten bounded
years:

- the project remains explicitly blocked for missing material/cash;
- security becomes unfunded;
- the route's reliability does not improve;
- banditry remains active;
- unpaid debt carrying cost compounds public debt above its opening level.

Observed ending debt in the final fixture was about **1098.05**, again a causal fixture result,
not a desired balance value.

This proves the required property: **growth is not guaranteed**. Finance, supply, labor,
security and shocks can halt or reverse state-capacity improvement.

## Scheduler / architecture integration

GROWTH is inserted into the ordinary process order after civilian and before underworld:

```text
logistics → merchant → craft → civilian → growth → underworld ...
```

This lets settled commercial/civilian activity become taxable/input state before the public
review, while later domains see any completed infrastructure/security consequences.

ARCH-01 parity/order/cancellation/restart tests pass with the new process. A 60-day scheduler
benchmark after integration measured approximately:

- eager SQL due-day requery: **1.567 s**;
- lazy registry cache: **1.530 s**;
- ratio: **~1.02×**.

The full historical ARCH script's 250-day benchmark tail can exceed the execution harness
limit; the functional ARCH suite itself passes and the shorter real benchmark shows no material
regression.

## Migration acceptance

The actual packaged schema-65 CRAFT database was migrated to schema 66.

Verified:

- existing actor/economy/merchant/craft row counts unchanged;
- zero fabricated GROWTH treasuries, fiscal entries, projects, security assignments, reports or
  snapshots;
- `PRAGMA integrity_check = ok`;
- zero foreign-key violations.

Old campaigns therefore receive GROWTH machinery without invented fiscal or administrative
history.

## Regression status

Green after GROWTH-01:

- GROWTH-01 regional/state-capacity acceptance;
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
- ARCH-01 functional parity/order/cancellation/restart suite.

## Deliberate boundary

GROWTH-01 does not yet implement the full agriculture/weather owner, general legal procedure,
or WAR-01 consequence projection. Food stress currently reads the real local grain market at
the resolution needed for this slice. Agriculture/weather and law remain scheduled later
integration work.

It also does not guarantee every canon polity begins with a public treasury. Migration adds
machinery only; it does not fabricate historical tax systems or opening cash for old saves.

## Stop boundary

GROWTH-01 is accepted and banked. Do not expand it into a detached kingdom-management game.
The next implementation slice is **WAR-01**.
