# v0.25 — Long-Run Simulation & Stress Testing

v0.25 is the consolidation/stress pass for the systems built through v0.24. It does not introduce a new world domain. Instead it adds a reusable long-horizon harness, contradiction scanning, checkpoint snapshots, explicit narrative-camera succession, and adversarial tests that run the existing systems through decades of story time.

## Core principle

> **Long-run simulation is allowed to change the world. It is not allowed to lose the causal trail that explains how the world changed.**

The stress harness advances the same authoritative `advance_connection()` clock used by ordinary play. It does not use a separate simplified century simulator.

## Added runtime systems

### Stress runs

`engine/stress.py` provides:

- `world_snapshot()` — compact structural state at a story day;
- `contradiction_scan()` — cross-system invariant checks;
- `start_stress_run()` — persists a run definition;
- `run_horizon()` — advances real story time in bounded checkpoints and audits every checkpoint;
- `stress_report()` — returns run/checkpoint/issue history.

Persistent tables:

- `stress_runs`
- `stress_checkpoints`
- `stress_issues`

The harness records start/end state, elapsed wall-clock time, checkpoint state, database-size approximation, and every contradiction detected.

### Explicit camera succession

A protagonist/camera death must not imply world death. v0.25 adds:

- `player_camera_successors`
- `player_camera_history`
- `designate_camera_successor()`
- `transfer_camera()`
- `process_camera_succession()`

A handoff occurs only when the current camera actor is dead and a previously designated living successor exists. The engine does **not** invent an heir, resurrect the protagonist, or pick whichever nearby NPC is convenient. If there is no valid designation, the campaign remains without a living camera focus until the user explicitly chooses one.

## Contradiction scanner

The scanner currently checks, among other things:

- SQLite integrity and foreign keys;
- negative aggregate population;
- live households whose recorded head is no longer an active member;
- dissolved polities still controlling territory;
- active education under a dead teacher;
- active medical treatment under a dead provider;
- active religious office held by a dead actor;
- events or knowledge dated in the future;
- a dead camera focus with an available designated successor that failed to hand off;
- applied historical crystallization whose produced actor or lineage trail has disappeared.

This is deliberately cross-system. A subsystem can be internally valid while still violating another subsystem's authoritative state.

## Cumulative long-run scenarios

`tests/v25_test.py` exercises one persistent miniature campaign through three horizons:

1. **20-year quiet prosperity / extreme-success run**
   - household and successful inn remain causal;
   - business accounts continue off-camera;
   - aggregate demography advances;
   - culture recurs through story time;
   - a configured political claim may change control;
   - success does not automatically create an adversity/pressure debt.

2. **40-year generational continuation**
   - the first camera actor is explicitly killed after year 20;
   - the camera hands off to a pre-designated successor;
   - education has enough time to complete or be interrupted by actual causality;
   - an eligible institutional successor is explicitly chosen rather than auto-appointed;
   - recurring cultural programs build historical instances.

3. **120-year macro-history horizon**
   - aggregate age cohorts turn over for more than a century;
   - mortality operates without requiring named instantiation of the whole population;
   - political-control history remains coherent;
   - institutions and enterprises continue using the same shared clock;
   - the database remains structurally consistent at every decade checkpoint.

In the current deterministic test fixture, all three horizons complete with zero contradiction findings. The measured wall-clock figures on the packaging environment were roughly 0.28 s, 0.36 s, and 1.34 s for the three sequential segments. Those numbers are **regression-fixture measurements, not hardware guarantees or a benchmark for a fully populated campaign**.

## Adversarial v0.25 audit

`tests/v25_edge_test.py` specifically checks:

- a camera cannot succeed to itself;
- a dead actor cannot be designated as a new successor;
- if the designated successor dies before handoff, the engine marks that designation unavailable rather than inventing a replacement;
- a later explicit valid designation can still continue the campaign;
- camera history remains append-only;
- an applied crystallization remains connected to its produced actor and lineage records after another 25 years of simulation;
- long-run audits remain clean after the handoff and crystallization history are both present.

## What v0.25 proves — and what it does not

v0.25 proves that the implemented systems can be advanced together for long periods without the tested contradiction classes, that story time remains the authoritative clock, and that the world can outlive its original camera character.

It does **not** claim that one tiny test fixture proves every possible Caerness campaign will be narratively rich for 120 years. The harness is now part of the engine precisely so larger seeded campaigns can be stress-tested as the World Bible and campaign population grow.

## v0.26.1 production-scale extension

The original v0.25 fixture remains useful as a fast structural regression, but v0.26.1 adds candidate-scale validation against the production bootstrap rather than treating the miniature fixture as proof of full-world scale.

The production seed contains 388 named working-registry characters, 48 established places, 36 institutions/polities, six aggregate Hearth demographic cohorts and latent cultivation pools. The 20/40/120-year production run completed with zero contradiction findings at every checkpoint. The year-120 database was approximately 31.2 MB and the measured total simulation time in the packaging environment was about 30.8 seconds.

The same validation pass also checks two alternate deterministic 40-year runs, 1,500 simultaneously due actors, a 64-location/112-route information graph, and 200 differentiated businesses resolving 12,000 business cycles over five years.

A century-scale bug found during this work is now permanently guarded: deceased named characters are removed from autonomous simulation scheduling, and the contradiction scanner detects posthumous decisions.
