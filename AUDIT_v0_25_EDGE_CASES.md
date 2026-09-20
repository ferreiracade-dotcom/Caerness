# v0.25 Adversarial Long-Run Audit

## Scope

This audit targets the failure modes that only become visible after decades of authoritative story time: cross-system contradictions, camera/protagonist death, institutional continuity, demographic turnover, political divergence, crystallization persistence, database growth, and repeated shared-clock catch-up.

## Findings and hardening

### 1. Camera death previously had no authoritative continuation mechanism

Earlier versions correctly treated the player as camera rather than causal center, but `player_state` still pointed at one actor. If that actor died, there was no persisted handoff mechanism.

**Fix:** v0.25 adds explicit camera-successor designations and append-only transfer history. Handoff occurs only to a designated living actor.

### 2. Camera succession must not become hidden heir generation

A naïve fix would choose a child, spouse, household heir, or nearby NPC automatically. That would silently turn family/political succession into narrative-camera destiny.

**Fix:** the engine refuses to invent a successor. Dead or revoked candidates become unavailable. No valid designation means no automatic handoff.

### 3. Long-run validity must be cross-system, not subsystem-local

A valid education row can become invalid when the teacher dies. A valid medical row can become invalid when its provider dies. A polity can become contradictory if it is dissolved but still owns crystallized territory.

**Fix:** `contradiction_scan()` checks cross-domain invariants at every long-run checkpoint.

### 4. Historical crystallization must survive decades after application

Crystallization is only useful if its historical basis remains reconstructable later.

**Fix/test:** an adversarial fixture crystallizes a latent actor, advances another 25 years, and verifies that the applied run still points to the produced actor and retains lineage records.

### 5. Long-run tests must use the real clock

A separate coarse century resolver could hide defects in ordinary subsystems.

**Fix:** `run_horizon()` uses `advance_connection()` itself in multi-year chunks, then audits the authoritative database.

### 6. Institutional succession remains a choice, not an elapsed-time side effect

The 40-year fixture deliberately allows a successor candidate to become eligible, then performs an explicit choice. The engine does not promote the candidate merely because decades passed.

### 7. Extreme success must not create adversity debt

The quiet-life fixture gives an enterprise strong commercial conditions and allows prosperity to persist for twenty years.

**Test:** success produces ordinary accounts and state change but does not create unrelated player pressure merely to rebalance the story.

## Adversarial assertions

The v0.25 regression/audit suite verifies:

- 20-year quiet/extreme-success simulation;
- 40-year generational continuation;
- 120-year total macro-history horizon;
- aggregate population remains non-negative and continues to age/migrate/die through existing systems;
- political territory can diverge through configured claims;
- institutional successor eligibility does not auto-appoint;
- explicit institutional succession can be recorded;
- camera succession occurs after protagonist death when designated;
- dead designated camera candidates are not used;
- no convenient replacement camera is invented;
- crystallization history remains traceable after decades;
- SQLite integrity and foreign keys remain clean;
- no tested cross-system contradictions are present at checkpoints;
- database growth remains bounded in the deterministic miniature fixture.

## Result

**PASS.**

v0.25 is the first release whose cumulative regression suite includes 20-, 40-, and 100+-year authoritative simulation horizons rather than only short functional tests.
