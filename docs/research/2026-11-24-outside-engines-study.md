# Outside engines study (2026-11-24)

Read-only study. Nothing here was run; clones sit in a scratch folder outside the repo. Nothing is committed.

**Position stays as decided:** adopt no outside library, because each would add a second model of state. This note mines the code for *ideas*. Our rules stand: no hard caps, no world words in `engine/`, packages are data only, engine vetoes and never offers a menu.

Two corrections to the ChatGPT review that prompted this:

1. It says business/venture/place processes are not on the production clock. They are: `process_due_civilian` (`engine/civilian.py` ~600-633) calls `agreement_terms.process_due_terms`, `places.process_due_places`, `ventures.process_due_ventures` and `process_due_businesses`.
2. Mesa's `EventList` was already examined and rejected (`engine/process_registry.py` docstring).

**Where our real cost sits (matters for S1).** We do not scan every actor per tick. Cost is *checkpoint count × registry requery* (`ProcessRegistry.next_checkpoint` re-queries every process eagerly) plus per-actor review in `simulation_profiles`. `_review_phase` (`engine/bootstrap.py`) already coarsens review stagger into 30-day buckets so as not to mint hundreds of checkpoints. Most outside engines optimise a different shape (per-entity modulo scans), so their tricks help less than they look.

Legend: **S1** = skip-speed tiering; **V1** = "does the city live" audit.

## Licence table

| Project | Licence | Use |
|---|---|---|
| Mesa | Apache-2.0 | ideas / may copy small patterns with notice |
| NetworkX | BSD-3 | audit-only dependency possible |
| SimPy | MIT | ideas |
| pyeventsourcing | BSD-3 | ideas |
| transitions | MIT | dev/test tool possible |
| OSMnx | MIT (OSM data ODbL) | not relevant |
| ESL | Apache-2.0 | ideas |
| Metternich_old | MIT | structure only |
| Moltke Engine | MPL-2.0 | ideas only; file-level copyleft |
| EcoSim | MIT | ideas / small patterns |
| abm-econ-sim | no licence file | do not copy |
| computational-economy | GPL | do not copy |
| narrativeengine-p | MIT | ideas |
| narrative-state-engine | AGPL | study only |
| Talk of the Town | MIT | ideas / patterns |
| Neighborly | MIT (archived Apr 2026) | ideas |
| Ensemble | BSD-4-clause (advertising clause) | ideas only |
| OpenVic-Simulation | MIT | ideas |
| Open Football (ZOXEXIVO) | Apache-2.0 | ideas |
| Open Football database | none detected | do not copy |
| football.json / footballcsv | CC0 | data for a future football world |
| Veloren (rtsim) | GPL-3 | ideas only |
| OpenTTD | GPL-2 | ideas only |
| Unciv | MPL-2.0 | ideas only |
| Archon Engine | MIT | ideas |
| Freeciv | GPL-2.0 (`COPYING`) | ideas only |
| Game of Crowns | MIT (`LICENSE`, "The Game of Crowns authors") for its own code; it *runs* Freeciv 3.2 (GPL-2.0) as a separate process, `sim/freeciv` is only a submodule pointer; art is third-party (CC BY / CC0, not in git); its ruleset and `baseline/` data files look Freeciv-derived, so treat the `bridge/data` rulesets as GPL-tainted | ideas only; the JS `bridge/` logic is MIT and could be read freely, but we copy nothing |
| Google OR-Tools | Apache-2.0 | not relevant to core |
| Fantasy-Map-Generator | NOASSERTION | not relevant |

GPL/AGPL/MPL projects: read for ideas, copy nothing.

## Ranked shortlist (read this first)

| # | Idea | Source | Fits | Flag | Better than ours? | Cost |
|---|---|---|---|---|---|---|
| 1 | Post-run **story recognizer**: mine the finished run for patterns (unrequited bond, triangle, rivalry, rival owners, loner, one-way friendship) | Talk of the Town `drama.py` | new `tools/` script over relationship/org/office/business tables | V1 | We have nothing equivalent; coverage counts executions, not stories | medium, tool only |
| 2 | **Gate block reason**: per entity per gate, store the last reason it did not act; scan separates "nobody wants it" / "a gate blocks it" / "it keeps failing" | Open Football `FreeAgentBlockReason` + auditor; EcoSim "inactive control" registry | `engine/coverage.py` (`record_process_execution`, specs) | V1 | Ours counts due/eligible/executed; no *why not* | low-medium |
| 3 | **Schedule threshold crossings** instead of polling a rate-driven value: solve the day it reaches the threshold, schedule that day, re-solve when the rate changes | Mesa `ContinuousState` + `Threshold` | `_resolve_background_process` (accumulator vs `event_threshold`), `_resolve_shadow_links` (exposure to 85), business cash running out; via `next_due_day` or `ProcessRegistry.schedule_once` | S1 | Yes: removes polling and removes checkpoints that do nothing | low-medium |
| 4 | **Tier by graph distance** from the protagonist's circle (multi-source BFS over relationship/org edges, recomputed monthly); tier is a *cadence*, never an outcome | Archon `AIDistanceCalculator`; POP-01 "tier never changes outcomes" | `_effective_tier`, `_wake_actor_if_needed` in `engine/simulation.py`; `simulation_profiles.forced_tier/wake_threshold` | S1 | Complements our tiers (we have explicit tiers and wake rules; distance would feed them) | medium |
| 5 | **Rescale progress when a cadence changes** (half-done stays half-done) instead of resetting the due day | OpenTTD `grow_counter` rescale | `next_review_day` updates when a tier changes in `_wake_actor_if_needed` / `_review_actor` | S1 | Avoids a burst or a stall at tier changes | low |
| 6 | **Conservation test net of recorded injections**, with strict-xfail leak reproductions so known leaks stay visible | EcoSim `tests_contracts/test_conservation_leaks.py` | new test beside `tests/ledger_test.py`, `tests/saintjude_outfit_money_test.py` | V1 | We test pieces; a whole-world money invariant is not seen (grep found none) | low |
| 7 | **Pro-rata funded pool** across named claims (stable, bounded) for insolvency/creditors | EcoSim `payments.py proportional` | `engine/ventures.py`, business closure paths | - | No pro-rata logic found in our engine | low |
| 8 | **Package validator** with severities, typo suggestions, suppressions | Unciv `RulesetValidator`, `TextSimilarity` | world package loader (check `engine/world_package.py` or equivalent) | - | Unverified whether we have one | medium |
| 9 | **Per-subsystem world digest** per day, so a determinism mismatch says which subsystem differs; plus an **ablation switch** per feature | Open Football `fingerprint.rs`, `OF_CAREER_ANCHORS_OFF` | extend `tools/build_opening.py` row-hash fingerprint to a run-time digest | V1 | We fingerprint the opening, not the run | low |
| 10 | **Cohort career census**: follow a cohort through the whole run and ask conditional questions ("do men of equal standing in equal outfits get judged by what they did?") | Open Football `.dev/careers`, `judgement.rs` | new audit tool | V1 | New capability | medium |
| 11 | **Source-attributed modifiers with expiry**; Ensemble schema `duration` statuses | Moltke `modifiers.rs`; Ensemble `schema.json` | standing/relationship data in package schema | - | Probably, if we hold ad hoc timers | medium |
| 12 | **Neglect-weighted attention** so starved goals/actors can rise | narrativeengine-p `allocateTicks` | review ordering for minor actors | S1 | Supports "minor actors can still rise" | low |
| 13 | **Third-party considerations on a shared event type, zero = veto** | Neighborly `EventConsiderations` | package extension point for event likelihood | - | Matches "engine veto, not menu" | low |
| 14 | **Slow decay of regard toward a per-pair resting point**, not toward zero; plus kindness weighing less each time it is repeated within a window | Freeciv `love_coeff` (4% edge toward zero per turn); Game of Crowns `restingFavour`/`LEAN`, `temper` | our relationship/standing drift (check where regard decays; `_resolve_shadow_links` for exposure) | V1 | Likely: avoids the "everyone ends neutral" flattening a plain decay causes | low |
| 15 | **A warning phase before a break**: a countdown from decision to act (Freeciv `adip->countdown`, -10/-20 turns by reason) and a stated ultimatum before a rising (Game of Crowns), so a break is traceable in `causal_links` and the player/GM can see it coming | Freeciv `dai_go_to_war`; GoC `risings.js` `odds`/`rise` | any process that ends a bond (feud, rebellion, betrayal): record decision day and reason, act later | V1 | New for us if breaks fire on the same day as the decision | low |
| 16 | **Deed ledger with plain-language cause**: a bond keeps its heaviest named deeds with date and reason, repeats add to one entry, and the story can quote the worst one | Game of Crowns `favourbook.js` `recordDeed`, `causeOf`, `DEED_WORDS` | our grievance/standing records and the GM-facing text | V1 | We already keep grievances (canon grudges, J1 prison); check they carry *date + reason*; the keep-eight-heaviest cap is NOT borrowable (no hard caps) | low |

## Per codebase

### Mesa (Apache-2.0)
- **Does well:** `mesa/time/events.py` is a heap `EventList` with weakref callbacks, cancel with adaptive compaction, and `EventGenerator`. `experimental/states/state.py` has `ContinuousState` + `Threshold`: a value with a rate gets its exact crossing time solved (linear or quadratic) and scheduled as one event, re-solved on rate change. `experimental/data_collection` declares datasets with an interval and Memory/JSON/Parquet/SQL recorders. `experimental/actions` has timed interruptible actions with `on_interrupt(progress)`.
- **Borrow:** crossing-time scheduling (#3). Declared-dataset collection is a fit for `coverage.py` specs but we already have specs. Interruptible actions with progress map to travel/long tasks; check how `agreement_terms`/travel handle interruption before any change.
- **Not worth it:** the dependency (already rejected), weakref storage (cannot survive restart; SQL does that).

### Talk of the Town (MIT)
- **Does well:** per-person pass thinned by `chance_of_a_timestep_being_simulated` with rates rescaled by 1/chance; `missing_timesteps_to_account_for` catch-up multiplier in `progress_relationship`; relationship charge/spark thresholds that create Friendship/Enmity; `StoryRecognizer` in `drama.py`; event numbers for ordering; pre-play events retconned with random dates.
- **Borrow:** the story recognizer (#1). The catch-up multiplier idea fits S1 (a skipped actor gets accumulated change on wake; check `_review_actor` already does this).
- **Not worth it:** business advent/demise tables with min population per type are a hard cap per type. Do not borrow.

### Neighborly (MIT, archived)
- **Does well:** `LifeEvent.get_probability` (base plus considerations; zero vetoes, rest averaged); `EventConsiderations` lets third parties add considerations to an existing event; preconditions and effects as data; global and personal event histories; `data_collection.py` modelled on Mesa.
- **Borrow:** considerations with zero as veto (#13).
- **Not worth it:** `LifeEventSystem` evaluates every event for every character each step, O(characters × events). Our due-queue is better.

### Ensemble / CiF (BSD-4)
- **Does well:** `schema.json` categories with direction type, min/max, default and `duration` (auto-expiring statuses); a time-indexed `socialRecord` so queries can ask what was true at time t; volition rules give weighted per-pair desires; trigger rules vs volition rules.
- **Borrow:** statuses with a duration as package data (#11); "what was true at t" is already natural with our dated rows.
- **Not worth it:** the advertising clause; a per-pair volition table is O(n²) and conflicts with tiering unless limited to the live circle.

### NetworkX (BSD-3)
- Has `structural_holes` (brokers), Louvain communities, pagerank, betweenness (with k sampling), DAG ancestors/descendants/topological generations, d-separation.
- **Borrow:** audit-only. Build a read-only graph from SQL (`causal_links`, patronage/ownership edges) to measure chain depth and chains crossing business/politics/crime, and brokers. A recursive CTE may be enough for chains alone. Never a second source of truth. **V1**, cost low.
- **Not worth it:** anything inside the run loop.

### Open Football (Apache-2.0, Rust)
- **Does well:** a fixed ordered daily phase pipeline with an observer (`simulator/mod.rs`); career census (`.dev/careers`); `judgement.rs` conditional checks with an ablation toggle; `fingerprint.rs` per-subsystem daily digest; `FreeAgentMarketAuditor` with a durable last block reason; dormant records decay monthly; result types kept apart from behaviour; has AGENTS.md and `openspec/`.
- **Borrow:** #2, #9, #10. These are the best V1 ideas in the whole study: they test *behaviour*, not just execution.
- **Not worth it:** Rust, so only ever a service boundary. The football database repo has no detected licence; football.json and footballcsv are CC0 and only matter if a football world is built.

### OpenVic-Simulation (MIT, C++)
- **Does well:** `tick()` mutates the world, `update_gamestate()` refreshes derived caches behind a dirty flag; queued actions run at a defined point; fixed-point arithmetic; pops as aggregated groups with per-province attributes; batched market order clearing.
- **Borrow:** the split between mutation and derived caches matters if S1 adds cached tier or distance data: refresh it at one defined point, never mid-checkpoint. Pop aggregates are the closest analogue to POP-01; nothing to add beyond what the design already says.
- **Not worth it:** fixed-point (we use SQLite integers/floats; determinism comes from seeded draws).

### Veloren rtsim (GPL-3)
- **Does well:** simulates the whole world including unloaded areas with throttled rates; relational data with logic on top rather than ECS; `rule/cleanup.rs` uses a seed-staggered modulo `(actor.seed + tick) % SKIP == 0` with decay scaled by `dt * SKIP`; `data/sentiment.rs` (feelings that decay slower when stronger) is kept apart from `data/report.rs` (information, each with its own remember-for time).
- **Borrow:** the sentiment-versus-report split (a feeling is not a piece of knowledge) is a clean model for grudges versus what someone knows. Check how our grudge and knowledge records split before deciding. Decay scaled by elapsed time is the same catch-up rule as in Talk of the Town.
- **Not worth it:** its caps on sentiments per entity (128 NPC, 1024 faction) break our no-cap rule; `rule/architect.rs` respawns population, which breaks conservation and no-invention; `world/src/civ` is layout generation, not lived history.

### OpenTTD (GPL-2)
- LFSR tile sweep with a cursor as minimal state; `(counter + index) % N` staggering; growth counter rescale on rate change (#5); a `regression/` set for deterministic output diffs.
- **Not worth it:** modulo staggering, for the reason in the opening section.

### Archon Engine (MIT, Unity)
- **Does well:** tier-based AI intervals; tier from multi-source BFS distance to human players, recomputed rarely (#4); "wall-clock never changes what the AI decides"; slow-goal diagnostics; command pattern; opt-in TSV session recorder of commands, decision notes and declared tables.
- **Not worth it:** its scheduler scans every AI state each hour, worse than our due-queue.

### Moltke Engine (MPL-2.0, Rust)
- Fixed integer ticks; canonical state checksums; versioned command replays; seeded SplitMix64; source-attributed modifiers with expiry and cached derived values; bounded trigger expressions; layered package VFS with override diagnostics; content fingerprint (like our `_source_key`); economy changes planned before commit so errors leave no partial state; Lua sandbox with instruction budgets.
- **Borrow:** modifiers (#11); bounded trigger expressions as a way to keep package conditions data-only; plan-then-commit for multi-row money moves (check `ventures`/ledger paths for partial-state risk).
- **Not worth it:** the Lua sandbox (our packages are data only).

### Unciv (MPL-2.0)
- **Does well:** data-driven "uniques" effect/condition language; `RulesetValidator` with severities, typo suggestions, suppression; auto-update of deprecated entries.
- **Borrow:** the validator (#8). Verify first whether `engine/world_package.py` (or the loader) already validates.
- **Not worth it:** its turn flow hard-codes major civs versus city-states.

### EcoSim (MIT)
- **Does well:** `proportional(due, available)` pro-rata allocation (#7); `PaymentBook`; conservation leak tests (#6); `run_evidence.py` records which controls are wired and marks the rest "inactive" (the silent-disconnection audit, #2); matched-seed comparisons in `docs/MODEL_SCOPE.md`.
- **Borrow:** #2, #6, #7.

### SimPy (MIT)
- A heap of `(time, priority, eid, event)`, the same shape as ours. `PriorityResource`/`PreemptiveResource` model capacity and queues (cells, office seats) and may inform J1's prison capacity, but only as a model to read; capacity must be a pressure, never a cap.
- **Not worth it:** the dependency; `rt.py`.

### pyeventsourcing (BSD-3)
- Aggregates emitting events, optimistic version check, snapshots, projections.
- **Borrow:** a replay test that rebuilds derived rows from event rows, and optimistic row versions only where two processes write the same row. Cost low.
- **Not worth it:** converting to event sourcing; we already hold SQL as the authority.

### transitions (MIT)
- State machines with queued triggers and diagram export. Use only as a dev tool to document and test lifecycles (business, prisoner, office-holder).
- **Caution:** an allowed-transition list is a menu. Keep it as a *test* of what must never happen, not as the rule set.

### narrativeengine-p (MIT, TypeScript)
- `allocateTicks` gives ticks to the goals with the highest "neglect" score (time since last advanced): #12.
- **Not worth it:** `TIMESKIP_CAP` (a hard cap) and the karma pity bonus.

### narrative-state-engine (AGPL)
- Schema-first extraction of entities, relationships and events from narrative text with provenance. Study only; no code.

### Metternich_old (MIT)
- Engine and content in separate repos; confirms the packages-as-data split. Nothing to add.

### ESL (Apache-2.0)
- Walrasian price solving, balance sheet and cash flow statement. Alpha, C++. Ideas only; our prices are not market-clearing.

### OSMnx, OR-Tools, Fantasy-Map-Generator
- Not relevant: Saint Jude is fictional; OR-Tools adds a solver we would not let own causality; the map generator was mentioned only in an image caption.

### abm-econ-sim, computational-economy
- Small generic economy models. computational-economy is GPL. Not worth borrowing.

### Freeciv (GPL-2.0, C)
Fetched with `git clone --depth 1 --filter=blob:none --sparse`, then sparse-checkout of `ai/`, `server/*.c`, `server/advisors/`, `common/*.h`. Read: `ai/default/daidiplomacy.c`, `daidata.c/.h`, `daimilitary.c`, `ai/difficulty.c`, `ai/handicaps.h`, `server/srv_main.c`.
- **Diplomacy memory is one number per ordered pair**: `pplayer->ai_common.love[other]`, range ±`MAX_AI_LOVE`. Each turn (`dai_diplomacy_begin_new_phase`) it moves by named causes: up for shared enemies, up for gifts (`love_incr`, capped), down for war with its ally, "Provoked!" for incidents (and a good reputation is only half-protected: `amount -= love/2` when positive), down for units in its territory, down for "excess" above 80% (high trust is reserved for allies), then **edges toward zero by `love_coeff` (4%) each turn**. Thresholds gate behaviour: `req_love_for_peace` = 1/8, `req_love_for_alliance` = 1/4. `greed(missing_love)` turns lack of love into a price in treaty talks.
- **Wars have a countdown**: `dai_go_to_war` sets `adip->countdown` to -10 or -20 by reason (space, behaviour, hatred, excuse) and tells the target why; peace agreed in the meantime cancels it. Per-pair flags stop nagging: `asked_about_peace/alliance/ceasefire`, `spam` timer, `ally_patience`, `warned_about_space`.
- **War target choice** is a want per candidate (`dai_war_desire`), reduced by love (`want -= want*love/(2*MAX_AI_LOVE)`), so affection is a brake, not a veto.
- **Danger is cached and bounded by the player's skill, not by a cap on the world**: `assess_danger` computes, per city, danger, urgency and "grave danger" from enemy units within `assess_turns` (2 under `H_ASSESS_DANGER_LIMITED`, else 3, 6 for some cases), skipping units beyond a distance limit. `dai_assess_danger_player` pre-fills it for all cities once per turn before the AI decides.
- **Difficulty is handicaps plus fuzz, not different rules**: bit flags (`H_DIPLOMACY`, `H_DANGER`, `H_MAP`, `H_FOG`, `H_ASSESS_DANGER_LIMITED`, ...) and a `fuzzy` number (400 novice down to 0) that makes a decision randomly wrong. Same engine, a weaker mind.
- **Turn order**: `srv_main.c` runs phases; in each phase every AI gets `first_activities`, humans move, then `last_activities`; the order of players is shuffled in concurrent mode so no one always acts first.
- **Borrow:** #14 (decay toward a resting point instead of zero; caps on trust; gift gain capped), #15 (decision-to-act delay with a reason), and the *handicap/fuzz* model as an S1 idea: tier means "sees less and looks less often", never "different outcomes". Our tiers already say this; Freeciv shows the cheap way to state it (a visibility/horizon limit plus noise per actor). Cost low.
- **Not worth it:** a single scalar `love` loses *why*; our grievances need reasons. Fixed per-turn recomputation of everything per player; ours is due-driven.

### Game of Crowns (MIT; Godot + Node, drives Freeciv 3.2)
Fetched by sparse blobless clone after a plain shallow clone failed (`fatal: fetch-pack: invalid index-pack output`, probably the large art history). Read: `GAME_DESIGN.md`, `WORLD.md`, `CLAUDE.md`, `README.md`, `bridge/favourbook.js`, `bridge/risings.js`, `bridge/contagion.js`. Architecture: Freeciv server runs the world; a Node **bridge** adds named characters, a court, favour and story arcs; Godot only draws.
- **Favour with reasons** (`favourbook.js`): per great house a favour value (default 60), a list of the last six *causes* (same cause adds up), and a ledger of **deeds** the house will not forget, each with turn, size and plain wording ("broke the oath we swore to the crown"). The same deed again adds to the old entry; `causeOf` returns "the winter of 352, when the King took a town that was theirs" for the chronicle. A ruling at court is owed back to the lord who asked, due after a number of seasons (`recordRuling`).
- **Diminishing kindness** (`temper`): the same house warmed again within four turns gets 1x, 0.5x, 0.2x of the gift's effect, and rival houses at war with it cool by 40% of the gain. A good reason to make repeated generosity weigh less without a cap.
- **Resting regard** (`LEAN`, `restingFavour`): where favour settles when left alone is a per-house offset on a reign-wide trust option, not zero.
- **A rising has a warning**: stories decide when and who; `risings.js` asks Freeciv for the odds and *tells them* ("the captains put the chance at N in a hundred") before the split, and the realm settles itself after a number of seasons. The design rule: "a house always gives an ultimatum two seasons before it rises; no single random event ends a reign".
- **Contagion** (`contagion.js`): a plague moving along trade routes season by season, with immunity after, closed roads, a wave record counting what it cost. A small SIR spread over our own route graph is the pattern; it fits the route/trade processes if we want illness onset (see the named-mortality note: illness onset is still missing).
- **Fun-bar tests** (`GAME_DESIGN.md`): "Measure, don't guess: count from a real reign's chronicle before and after a change". Same spirit as V1.
- **Licence check:** `LICENSE` is MIT, but the game depends on Freeciv (GPL-2.0) at run time and ships ruleset/baseline data derived from Freeciv; art is third-party and not in git. So the *JS bridge logic* is MIT and readable, while its data files should be treated as GPL-tainted. We copy nothing in any case.
- **Not worth it:** the keep-eight-heaviest cap on deeds and the 6-cause list are hard caps; the whole design is built for a 15-minute game (seasons as turns, seven houses), not a city of thousands.

### Not found
- **No open legends generator found.** Dwarf Fortress is closed source and a GitHub topic search returned only noise. Talk of the Town and Neighborly are the lived-history references; our opening-history work (schema 108) already goes further on canon-grounded rates.

## Notes by theme

- **Scheduling and clock:** our registry is already a due-queue. The gains are not scanning less but (a) scheduling crossings (#3) and (b) not re-querying all processes at every checkpoint. The eager requery is load-bearing for cross-domain same-day work (see the registry comment), so any cache must keep that safety.
- **Tiering:** keep tier as cadence only. Distance from the protagonist (#4), neglect weighting (#12) and rescaling on change (#5) let minor actors rise without a cap.
- **Reporting:** the strongest ideas are behaviour checks (#1, #2, #10), not more counters.
- **Replay and determinism:** per-subsystem digest (#9) and a rebuild-from-events test; everything else is already covered by seeded draws.
- **Social model:** keep feeling and knowledge apart (Veloren); statuses with expiry (Ensemble, Moltke).
- **Cause and effect across spheres:** `causal_links` plus NetworkX at audit time (#1 and the NetworkX entry); chains crossing business, politics and crime are the V1 evidence that the city is one system.

## Surprises
- The biggest finds came from the football and economy hobby projects, not the city-builders: their *audit* habits (block reasons, ablation toggles, conservation leaks kept as strict-xfail) are better than any of their simulation tricks.
- Several "tier" systems scan everything each tick and only skip work after the scan. Ours does not, so S1 should not copy them.
