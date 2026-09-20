# Caerness — Post-ONEYEAR-01 Implementation Roadmap

**Date:** 17 September 2026  
**Current engine:** v0.60.0 / schema 70  
**Status:** ONEYEAR-01 accepted with mandatory conditional-domain trigger audit.

## Immediate next milestone — TENYEAR-01

Run a **fresh** current-canon opening world for ten unattended years. Do not continue the ONEYEAR diagnostic save and do not use any manufactured trigger branch as the canonical decade input.

TENYEAR-01 is not another feature-development slice. Its purpose is to expose failures that only emerge through compounding, recovery, turnover and resolution changes.

### Required yearly checkpoints

At minimum retain year-0 opening plus years 1–10 fingerprints covering:

- population/households/deaths/births/unions/migration;
- latent/tracked/crystallized/down-resolved population;
- enterprises, merchant contracts, stock and shipments;
- craft facilities/orders/output;
- agriculture/food prices/food stress;
- public treasuries, debt, projects and regional state;
- institutions/offices/succession and teaching pipelines;
- cultivation Stage ecology and institutional reproduction;
- underworld organization formation/decline, rackets, protection and territorial state;
- health conditions/capacity and any disease activity;
- law cases/judgments/enforcement;
- warfare/campaign consequences if naturally triggered;
- information/belief propagation and decision counts;
- process coverage and invariant results.

### Long-run questions

TENYEAR-01 must test whether the world can:

1. compound without numeric explosion or silent resource minting;
2. recover from bad years rather than only accumulate damage;
3. lose and replace important people/institutional roles;
4. sustain multi-generational household and lineage continuity;
5. allow regions, firms and organizations to diverge causally;
6. promote latent/background entities when consequences make them important;
7. down-resolve formerly important entities without losing continuity/property/relationship history;
8. allow organizations to form, decline, merge, fracture or disappear through real causes;
9. keep information actor-relative over long periods;
10. remain deterministic across persisted restart checkpoints.

### Conditional-domain rule carried forward

ONEYEAR-01 established a stronger acceptance rule:

> Natural quiet is allowed; untested quiet is not.

For TENYEAR-01, if a critical conditional domain remains entirely inactive for the decade, do **not** manufacture activity inside the canonical decade simply to make a counter move. Instead create a separate branch from an appropriate checkpoint and manufacture a bounded causal trigger, exactly as ONEYEAR-01 did for HEALTH, LAW and WAR.

Any such branch is evidence only and must not contaminate the canonical decade save.

### Performance/scale trigger

Do not pre-emptively migrate the background population backend. Measure the decade first. If background population or graph processing becomes a demonstrated bottleneck, activate the deferred external-code benchmarks:

- neworder vs direct Polars vs Starsim-style arrays vs current SQL/Python;
- NetworkX vs rustworkx/NetworKit where graph workload warrants it.

Adopt only if measured gains justify migration complexity.

### TENYEAR-01 failure conditions

Fail and fix before acceptance if any of the following occurs:

- a required process silently stops running;
- persistent overdue work accumulates because due-day semantics are wrong;
- route movement or another in-progress process can be restarted indefinitely by a higher-level review;
- resource conservation fails;
- actor decisions read hidden/canon truth;
- the world requires manual poking merely to keep ordinary causal loops alive;
- entity promotion/down-resolution invents or loses historical identity;
- institutions become immortal because vacancies/replacement never resolve;
- quiet conditional mechanisms cannot activate when separately triggered;
- database integrity or foreign keys fail;
- restart replay materially diverges under identical state/seed.

## After TENYEAR-01

If the decade passes, the next work should be driven by evidence from the decade rather than by the old checklist. Likely categories are performance/scale migration, deeper domain-specific vertical slices revealed by actual bottlenecks, and narrative/explainability consumption of the now-stable causal world.
