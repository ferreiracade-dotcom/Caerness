# Caerness — External Code Adoption Ledger
**Date:** 17 September 2026  
**Checkpoint:** v0.60.0 COVERAGE-01 / schema 69  
**Purpose:** Close ambiguity about what was borrowed, benchmarked, rejected, or intentionally deferred from the completed external-code research pass.

## Status vocabulary
- **PATTERN INCORPORATED** — the external source materially changed Caerness architecture/semantics, implemented natively unless otherwise noted.
- **SPIKED / SELECTIVELY INCORPORATED** — a bounded experiment was run and the useful conclusion/pattern retained without wholesale adoption.
- **CONDITIONAL / DEFERRED** — valuable only if a concrete later problem or measured bottleneck appears.
- **REFERENCE / CALIBRATION ONLY** — useful research quarry; not intended as a production dependency.
- **REJECTED / NOT NEEDED** — reviewed but not appropriate for Caerness authority/runtime.
- **FUTURE ESCAPE HATCH** — intentionally not current architecture.

## Core architecture and agency
| Source | Status | Caerness result |
|---|---|---|
| Neighborly | PATTERN INCORPORATED | Directed relationships, broad/frequented-location presence, owner/employee separation, concrete consequence thinking, multi-generation continuity. No ECS wholesale or random universal life-event pool. |
| Minerva | PATTERN INCORPORATED | DEC-01 provider architecture: actor information envelope → concrete candidates → feasibility → local utility/proclivity → weighted choice → domain-owned execution. |
| PsychSim | PATTERN INCORPORATED | BELIEF/DEC use subjective information envelopes and shallow models of important others; no universal recursive theory-of-mind engine. |
| Little Lives | PATTERN INCORPORATED | Event/evidence/memory/relationship provenance principles; no prose-secret strings as authority. |
| Talk of the Town | PATTERN INCORPORATED | Negative/positive lessons around consequence propagation, inheritance/continuity and business ≠ building; monolithic routine simulation rejected. |
| Brunnfeld | PATTERN INCORPORATED | Competence Lens boundary: accessible evidence → professional attention → noticed cues → uncertain inference/affordance. |
| Victoria-Like | PATTERN INCORPORATED | Explainability/factor-tree concept informs causal audit and derived-state explanations; not adopted as an engine. |
| GTPyhop | CONDITIONAL / DEFERRED | Rare multi-step strategic planning only if utility/provider decisions prove inadequate in a concrete case. No current need to add it before ONEYEAR-01. |
| py_trees | CONDITIONAL / DEFERRED | Possible bounded tactical/routine controller; explicitly not primary world AI. |

## Persistence, orchestration and state machines
| Source | Status | Caerness result |
|---|---|---|
| Python Eventsourcing | SPIKED / SELECTIVELY INCORPORATED | EVENTS-01 proved immutable event stream, replay, projections, snapshots, branching and upcasting for bounded strategic owners. No mass event-sourcing rewrite. |
| Vivarium Core | PATTERN INCORPORATED | Explicit process contracts/ownership/read-write/dependency discipline and coverage observability informed ProcessRegistry. |
| Mesa 3.5 | SPIKED / SELECTIVELY INCORPORATED | Scheduler semantics benchmarked; Caerness retained its native SQL-backed ProcessRegistry/time authority instead of adopting Mesa wholesale. |
| transitions | PATTERN INCORPORATED | Declarative lifecycle/state-machine discipline used conceptually; Caerness-native persisted domain state remains authority. |
| SimPy | CONDITIONAL / DEFERRED | Local finite-capacity queues only (ports, healers, court dockets, workshops) if complexity warrants it; not world scheduler. |
| Simulus | REFERENCE / CALIBRATION ONLY | Discrete-event comparison only; no reason to replace current world clock. |
| Salabim | REFERENCE / CALIBRATION ONLY | Same as Simulus: local DES quarry, not current architecture. |

## Demography, resolution and scale
| Source | Status | Caerness result |
|---|---|---|
| SOCSIM / rsocsim | PATTERN INCORPORATED CONCEPTUALLY | Competing-risk/eligibility life-course thinking informs native background family/demographic processes; direct GPL code not copied. |
| neworder | CONDITIONAL / BENCHMARK DEFERRED | Strong candidate for high-volume longitudinal background simulation. Benchmark only if ONEYEAR/TENYEAR profiling shows the current substrate is a bottleneck. |
| Polars | CONDITIONAL / BENCHMARK DEFERRED | Candidate columnar backend for latent/dormant population; not yet justified by measured need. |
| Starsim arrays | CONDITIONAL / BENCHMARK DEFERRED | Population-array architecture is a scale reference; disease/network concepts are separately incorporated. |
| Mesa-Frames | REJECTED AS PRIMARY | The useful idea is vectorized/columnar state, not Mesa AgentSet lifecycle semantics. |
| PopulationSim | CONDITIONAL / INITIALIZATION ONLY | Potential household/population synthesis tool if future seed fidelity requires it; runtime quotas prohibited. |
| SynthPops | CONDITIONAL / INITIALIZATION ONLY | Same role as PopulationSim; not needed for current opening seed. |
| Repast4Py | FUTURE ESCAPE HATCH | CPU active-agent scale option only if measured scale requires a different substrate. |
| FLAME GPU 2 | FUTURE ESCAPE HATCH | GPU-scale escape hatch only; not current architecture. |

## Economy, commerce, production and logistics
| Source | Status | Caerness result |
|---|---|---|
| Manifest | PATTERN INCORPORATED | Emergent market/stock-flow causal thinking informed MERCHANT/GROWTH; Caerness retains native market authority. |
| abcEconomics | PATTERN INCORPORATED | Hard conservation semantics for physical transfers/inventory underpin MERCHANT/CRAFT/WAR supply. |
| NegMAS | PATTERN INCORPORATED AS DESIGN | Persistent negotiation/offer/issue/deadline concepts inform native contracts/negotiation; AGPL package not casually adopted. |
| SCML | PATTERN INCORPORATED AS DESIGN | Supply-chain/contract interaction concepts; GPL-family implementation not copied into production. |
| Pacioli | PATTERN INCORPORATED | Ledger/accounting invariants inform ECON/GROWTH/public finance; no mandatory dependency. |
| PyLuca | PATTERN INCORPORATED | Accounting pattern quarry alongside Pacioli; native ledgers retained. |
| FutureMUD | PATTERN INCORPORATED | CRAFT-01 recipes, inputs, facilities, labor, blocked reasons and concrete execution reflect craft-runtime lessons. |
| PyJobShop | CONDITIONAL / DEFERRED | Only for genuinely complex large-workshop scheduling. CRAFT-01 did not require it. |
| JobShopLib | CONDITIONAL / DEFERRED | Same as PyJobShop. |
| Selo Empire | PATTERN INCORPORATED | Physical settlement/logistics/infrastructure coupling informed merchant/growth/war vertical slices. |
| OR-Tools | CONDITIONAL / DEFERRED | Bounded planner for competent institutions if a real allocation/routing optimization problem appears; global world optimizer prohibited. |
| Port Simulation | CONDITIONAL / DEFERRED | Local port congestion/berth simulation if ports become a detailed bottleneck domain. |

## Geography, graphs, property and infrastructure
| Source | Status | Caerness result |
|---|---|---|
| NetworkX | PATTERN INCORPORATED / CURRENT GRAPH QUARRY | Derived graph/reachability patterns used while SQL remains authoritative. |
| rustworkx | CONDITIONAL / BENCHMARK DEFERRED | Benchmark against NetworkX only when graph workload becomes material. |
| NetworKit | CONDITIONAL / BENCHMARK DEFERRED | Large-network analysis candidate; not needed at current scale. |
| python-igraph | REJECTED / LICENSE-SENSITIVE | No need to accept GPL when permissive graph options exist. |
| UrbanSim | PATTERN INCORPORATED | Capacity/location-choice concepts inform property/business/household placement and GROWTH logic. |
| ChoiceModels | PATTERN INCORPORATED | Choice-with-constraints pattern quarry; native causal owners retained. |
| WNTR | PATTERN INCORPORATED | Infrastructure degradation/service/disruption/repair pattern informs GROWTH/WAR consequences. |

## Health, agriculture and law
| Source | Status | Caerness result |
|---|---|---|
| Synthea | PATTERN INCORPORATED | Individual condition-course/state-machine separation from care availability informed INTEGRATION-01 health. |
| Starsim | PATTERN INCORPORATED / CONDITIONAL SCALE | Network/contagion and separate population-disease owner principles retained; modern calibration not imported. |
| PCSE | PATTERN INCORPORATED | Crop/harvest causal structure informs simplified native regional agriculture. |
| WOFOST | PATTERN INCORPORATED AS REFERENCE | Crop physiology/harvest architecture quarry; no field-by-field scientific crop engine or EUPL source import. |
| OpenFisca | PATTERN INCORPORATED AS DESIGN | Dated jurisdiction/rules-as-data discipline informs native law owner; AGPL implementation not copied. |
| SpiffWorkflow | PATTERN INCORPORATED AS DESIGN | Procedure/workflow/capacity concepts inform native court/administrative case progression. |

## Warfare and reputation
| Source | Status | Caerness result |
|---|---|---|
| Standard of Iron | PATTERN INCORPORATED | Battle/session/consequence architecture quarry used in WAR-01 around the existing battle resolver. |
| Late Eastern Han Dynasty | PATTERN INCORPORATED | Multi-resolution warfare, campaign→battle→world-consequence architecture informed WAR-01. |
| OpenSkill | CONDITIONAL / DEFERRED | Useful for observer-specific public martial ratings/reputation; not objective power and not required before ONEYEAR-01. |

## Culture, diffusion and calibration
| Source | Status | Caerness result |
|---|---|---|
| SOIL | REFERENCE / CALIBRATION ONLY | Cultural/social diffusion experiment bench; Caerness belief/information network remains authority. |
| NDlib | REFERENCE / CALIBRATION ONLY | Topology/cascade diagnostics only; rumor is not disease infection. |
| cultural ABMs / opinion-dynamics models | REFERENCE / CALIBRATION ONLY | Used to test plausibility of clustering/diffusion, not as religion/culture authority. |
| skillmodels | REJECTED AS OPERATIONAL ENGINE | Not a suitable universal skill/career engine for Caerness. |

## Final adoption decision before ONEYEAR-01
The architectural research program is **closed enough for integrated simulation**. No unincorporated source above is a prerequisite for ONEYEAR-01.

The remaining items are conditional by design:
1. **background-population backend benchmark** — neworder vs direct Polars vs Starsim-style arrays vs current SQL/Python, triggered by measured performance/scaling need;
2. **graph backend benchmark** — NetworkX vs rustworkx vs NetworKit, triggered by graph workload;
3. **GTPyhop** — one strategic planning spike only if a concrete multi-step decision problem defeats the DEC-01 utility/provider model;
4. **OR-Tools / PyJobShop / local DES** — bounded institutional/workshop/queue optimization only when a real capacity problem warrants them;
5. **OpenSkill** — observer-specific public rating/reputation only when that richer reputation slice is implemented;
6. **Repast4Py / FLAME GPU 2** — future scale escape hatches.

Do **not** delay ONEYEAR-01 merely to install or import these libraries. ONEYEAR-01 should instead measure whether any of the conditional benchmarks becomes necessary.
