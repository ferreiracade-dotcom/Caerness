# Caerness v1.0-RC1 Readiness

Status: **READY TO CUT RC1 FROM v0.26.1**

The pre-RC gate established after v0.25 is now satisfied:

- tests cannot silently wipe the packaged/live campaign database;
- destructive reset requires explicit force outside test mode;
- schema migrations are ordered, versioned, backed up, and validated against representative older releases;
- production Caerness has a versioned World-Bible-derived bootstrap rather than relying on `seed-demo`;
- player creation is explicit and separate from world bootstrap;
- phone-facing setup/Ledger/diagnostics expose the core player/admin state needed for normal use;
- ownership mirrors have contradiction checks;
- specialized domain state feeds the generic decision layer without duplicating truth ownership;
- the full cumulative/adversarial suite passes;
- realistic 20/40/120-year production-seed stress passes with zero critical contradictions;
- alternate deterministic runs, dense same-day scheduling, route/information scale, and business scale pass;
- release version strings are aligned on v0.26.1;
- actor-first historical crystallization is explicitly documented as the v1 boundary.

## What RC1 should do

RC1 should be a **release-candidate freeze**, not another feature version. Recommended work after this package is limited to:

1. install/startup verification on the target Android/OnePlus environment;
2. save/backup/restore smoke tests from the phone UI;
3. one real play-session usability pass;
4. bug fixes only unless a blocker is discovered;
5. rerun the unchanged cumulative and candidate-scale suites before final v1.0.

## What should not block RC1

The following are intentional scope boundaries rather than missing v1 features:

- economy is constraint-oriented, not a full macroeconomic simulator;
- combat remains abstract rather than procedural real-world tactics;
- religion does not pre-invent an exhaustive feast calendar;
- education simulates transmission pipelines rather than every lesson;
- politics supports causal state transformation without becoming a grand-strategy game;
- historical crystallization is actor-first rather than generalized to every entity family;
- the engine does not manufacture replacement named adults merely to keep the registry numerically full after a century.
