# CAERNESS CURRENT HANDOFF — 18 SEPTEMBER 2026

**Engine:** v0.60.0  
**Schema:** 76  
**World Bible:** current repaired MASTER FINAL (embedded hash matches external master)  
**Primary acceptance milestone:** TENYEAR-01 COMPLETE

## Accepted stack

SCALE-01 → TRADE-01 → POPBACK-01 → POPLIFE-01 → ARCH-02 → PRESBACK-01 → ROUTE-01 → INFOIDX-01 → RESCLEAN-01, integrated with the existing merchant/craft/growth/war/health/agriculture/law/underworld/belief/decision/cultivation/politics/education systems.

## TENYEAR-01

The canonical diagnostic branch is non-canon world history. It advances day 0 → 3650 without manual causal poking.

Final state:
- population: 57,033,651;
- actors: 873 (862 active);
- enterprises: 278;
- events: 5,324;
- knowledge rows: 91,974;
- latent entities: 207; crystallized: 190;
- Stage attainments: 1,663;
- aggregate trade flows: 3,058;
- natural war operations: 0;
- SQLite integrity: ok;
- foreign-key violations: 0.

Annual checkpoints are summarized in `TENYEAR01_ACCEPTANCE_2026-09-18.md` and `TENYEAR01_annual_audit.json`.

## Critical acceptance evidence

- hard economic/resource invariants: PASS;
- decision canon/hidden-truth basis hits: 0;
- ARCH-02 caller-boundary invariance: PASS;
- Year-10 restart replay from exact Year-9 checkpoint: all 379 persisted tables and SQLite sequences identical;
- naturally quiet WAR domain: separately triggered on a copied day-3650 branch and PASS;
- current schema-76 regression suite: PASS;
- embedded World Bible SHA-256 matches the current master.

## Codebase verdict

Do not replace the engine with a framework. External codebases remain competitors only when profiling demonstrates a bottleneck.

During TENYEAR-01:
- NetworkX was directly compared after route search became expensive; the native Caerness snapshot was faster and was adopted instead;
- information slowdown was solved by SQLite indexing, not another framework;
- background population remains aggregate + bounded array-backed identity reservoirs; whole-world individualization remains rejected.

## Next work

TENYEAR-01 is no longer the gate. Future work should be evidence-driven from the decade:
1. inspect decade biographies/institution histories for qualitative plausibility, not only invariants;
2. investigate why some very large `advance_connection(N)` horizons perform worse than equivalent invariant-safe chunks even though history is identical;
3. deepen only domains whose decade output proves too shallow or implausible;
4. keep direct external-code tournaments targeted to measured bottlenecks.
