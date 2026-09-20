# Caerness Engine v0.59 — Successful Gang Stress Test

## Purpose
This is a conditional success stress test for Cale Brann's independent Aldergate ward gang. It does **not** replace the ordinary seed-9201 branch and is not a target outcome. The purpose is to answer: if the gang has a genuinely successful decade under ordinary engine causality, can success materially change manpower, organizational depth, rackets, territory and economic reach without changing its organizational form into a Mafia family?

The accepted strong-success branch is RNG seed **9508** after correcting two issues exposed by the search:

1. prosperity previously affected cash/rackets far more strongly than recruitment and retention, creating a structural bias toward manpower contraction even in successful branches;
2. racket-expansion events could repeat an already-existing racket and falsely inflate racket breadth.

Success now affects recruitment/retention through causal supports (cash per member, functioning work/fronts, deterrent reputation, command capacity, cohesion and stability). It remains possible for a prosperous gang to stay lean or shrink. Racket expansion must add genuinely new criminal business.

## Opening state — Day 0
- Organization form: **gang**
- Full members: **41**
  - hard core: 8
  - ordinary active: 33
- Peripheral associates: **21**
- Wider current orbit: **62**
- Command depth: **2 layers**
- Territorial presence: 22.0
- Racket breadth: 24.0
- Front depth: 28.0
- Deterrent reputation: 18.0
- Violence capacity: 28.0
- Cohesion: 62.0
- Membership stability: 52.0
- Cartage-yard cash: 10.0
- Cartage-yard reputation: 42.0

## Year 5 — Day 1825
- Full members: **50**
  - hard core: 16
  - ordinary active: 34
- Peripheral associates: 8
- Wider orbit: **58**
- Lifetime entries: 28
- Lifetime exits/losses: 32
- Command depth: 2
- Territorial presence: 23.5
- Racket breadth: 36.13
- Front depth: 28.0
- Deterrent reputation: 22.25
- Cartage-yard cash: 137.83
- Cartage-yard reputation: 44.86

The shrinking fringe alongside a growing full membership is intentional: more of the surviving orbit is being converted into durable members rather than the gang simply accumulating loosely attached people.

## Final state — Day 3650
- Organization form: **gang** (unchanged)
- Full members: **68**
  - hard core: **17**
  - ordinary active: **51**
- Peripheral associates: **8**
- Wider current orbit: **76**
- Lifetime entries to the gang orbit: **62**
- Lifetime exits/losses: **48**
- Command depth: **3 layers**
- Territorial presence: **25.0**
- Racket breadth: **52.85**
- Front depth: **30.8**
- Deterrent reputation: **26.05**
- Violence capacity: 29.0
- Cohesion: 62.0
- Membership stability: 53.85
- Succession/command depth indicator: 9.0
- Cartage-yard cash: **268.34**
- Cartage-yard reputation: **48.15**
- Debt: 2.0 (not silently erased)

Net full-membership growth is **+27**, or about **66%**, while gross turnover is much larger. The gang recruited/attracted 62 people into its orbit and lost 48 through desistance, defection, custody, death/incapacitation or relocation. Eleven active members entered the hard core and 46 peripheral associates became active members during the decade.

### Exit/transition totals
- Recruitment into orbit: 62
- Desistance: 25
- Defection: 8
- Custody: 3
- Death/incapacitation: 7
- Relocation: 5
- Peripheral → active: 46
- Active → hard core: 11

## What success actually looked like
The branch did not succeed because the engine applied a generic success multiplier. Concrete events accumulated:

- repeated profitable protection collections;
- **three genuinely new rackets**:
  - unlicensed betting (Day 912),
  - cargo diversion/commercial fraud (Day 2646),
  - contraband cartage (Day 2737);
- continuing legitimate use of the cartage yard as a front and operational base;
- four significant collection/territory fights:
  - two clear gang victories,
  - two inconclusive fights,
  - no clear territorial defeat;
- sustained recruitment and conversion of associates into full members;
- enough combined manpower and racket breadth for a third command layer to emerge around **Day 2737**.

Notably, this successful branch did **not** require Cale to order or win a spectacular assassination. Its success came mainly from durable economic/criminal activity, territorial wins, diversification, retention and delegation.

## Annual manpower path
| Year | Full | Peripheral | Wider orbit | Core | Command depth |
|---:|---:|---:|---:|---:|---:|
| 0 | 41 | 21 | 62 | 8 | 2 |
| 1 | 43 | 15 | 58 | 9 | 2 |
| 2 | 50 | 6 | 56 | 9 | 2 |
| 3 | 48 | 10 | 58 | 9 | 2 |
| 4 | 49 | 7 | 56 | 15 | 2 |
| 5 | 50 | 8 | 58 | 16 | 2 |
| 6 | 55 | 7 | 62 | 16 | 2 |
| 7 | 58 | 6 | 64 | 16 | 2 |
| 8 | 62 | 11 | 73 | 16 | 3 |
| 9 | 62 | 10 | 72 | 16 | 3 |
| 10 | **68** | **8** | **76** | **17** | **3** |

This is not monotonic. Years 2–5 include contraction/stagnation despite overall decade success. The strong expansion appears later after economic support, rackets and command capacity accumulate.

## Interpretation
This branch demonstrates that a successful ward gang can plausibly become a substantially larger and more layered gang over a decade without becoming a Mafia family or entering a universal criminal promotion ladder.

It does **not** establish 68 members as a target. Other branches under the same engine can stagnate, contract, or grow much less. Seed 9508 was selected because this diagnostic explicitly conditions on a successful outcome.

## Regression status after success coupling
- v0.59 flexible career/reach regression: PASS
- v0.37 underworld ecology regression: PASS
- v0.56 Vessel/Realization regression: PASS

## Artifacts
- `diagnostics/v59_cale_successful_decade_report.json`
- `diagnostics/v59_cale_successful_decade_yearly.json`
- `diagnostics/v59_cale_successful_decade.db`
