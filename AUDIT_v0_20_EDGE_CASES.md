# Caerness Engine v0.20 Health Edge-Case Audit

**Audited baseline:** v0.20.0  
**Hardened release:** v0.20.1  
**Scope:** aging, mortality, disability persistence, recovery, treatment ownership, and Vein-Mending.

## Result

The v0.20 health layer was genuinely implemented, but the adversarial audit found several edge cases where its behaviour did not yet match the design claims under long-running or awkward timing conditions. These were corrected rather than merely documented.

## Findings and corrections

### 1. Late breakthroughs could rewind old age

**Finding:** changing an elderly actor from an ordinary longevity class to a high cultivation class could move them from `late_decline` back to `prime`, erase the accumulated age penalty, and sharply lower mortality pressure. This conflicted with the World Bible rule that breakthrough improves preservation but does not rewind age.

**Correction:** a cultivation-class upgrade now preserves accrued age penalty and mortality-pressure floors. Future decline follows the new class, but already-accrued decline is not erased.

### 2. Recovery capacity existed but did not affect condition recovery

**Finding:** aging reduced the stored `recovery_capacity`, but `_resolve_condition` used only the condition's nominal recovery rate. A ninety-year-old ordinary actor therefore healed the same injury at the same speed as a healthy young adult if the condition rows were identical.

**Correction:** condition recovery is now multiplied by the actor's authoritative recovery capacity, with a bounded floor so recovery can be very poor without becoming mathematically impossible by default.

### 3. Vein-Mending was keyed by treatment label, not provider qualification

**Finding:** a treatment called `vein_mending` could be created with no provider, or with any actor as provider. Specialist requirements therefore distinguished treatment *names* but not actual specialist ownership.

**Correction:** treatments that require professional skill now use the existing competence system. Medicine, surgery, Vein-Mending, guided circulation, and elixir stabilization require a living provider with the appropriate minimum Medicine or Vein-Mending competence. `legendary_vein_mender` cases require master-level Vein-Mending competence. Provider competence also modestly affects treatment strength after qualification.

### 4. Expired treatment could affect the wrong amount of time

**Finding:** treatment effects were applied to an entire condition-review interval if the treatment happened to be active when the review occurred. Conversely, completing the treatment before the later review could cause its earlier valid contribution to disappear.

**Correction:** treatment effects are now calculated from the actual overlap between the treatment's active interval and the condition's review interval. Expired and stopped courses retain their historical contribution for the days they were actually active but contribute nothing afterward. Treatment end days are also health scheduler checkpoints.

### 5. Vein-specific treatment could behave like universal medicine

**Finding:** a Vein-Mending or guided-circulation treatment could provide the same generic recovery bonus to ordinary illness because compatibility logic was too permissive.

**Correction:** ordinary and Vein-specific treatment families now have distinct compatibility. Ordinary care can support a body suffering Vessel pathology at reduced strength, but it cannot substitute for specialist repair. Vein-specific care does not automatically accelerate ordinary fever or unrelated bodily injury.

### 6. Disability adaptation depended on recalculation frequency

**Finding:** after the first year, adaptation increased whenever the health profile happened to be recalculated. Repeated same-day recalculations could therefore accelerate adaptation, while a quiet actor might fail to adapt simply because no review landed on the anniversary.

**Correction:** adaptation is now based on elapsed story years using a persisted adaptation checkpoint. Disability anniversaries are scheduler checkpoints. Recalculating a profile repeatedly on the same day cannot accelerate adaptation.

### 7. Persistent disability had no explicit repair path

**Finding:** disability correctly survived source-condition recovery, but the schema's `resolved` disability state had no authoritative API.

**Correction:** `resolve_disability` now records genuine repair explicitly. Source-condition resolution still does not erase disability automatically.

### 8. Disability source ownership was not validated

**Finding:** a disability belonging to actor A could reference a source condition belonging to actor B.

**Correction:** source-condition ownership is validated when the disability is created.

### 9. Death did not fully close treatment ownership

**Finding:** death from a non-health subsystem could leave medical treatment active. A provider could also die while their treatment remained active. Unresolved conditions on dead actors could remain scheduled for later evolution.

**Correction:** death now stops treatments where the deceased is either patient or provider. Due-condition processing excludes deceased actors, so their unresolved health state is frozen as history rather than continuing after death. Global active-health counts likewise exclude deceased actors.

## Adversarial regression coverage

`tests/v20_edge_test.py` now verifies:

- late breakthrough does not restore an already-declining elder to prime;
- accrued mortality pressure is not erased by the breakthrough;
- unowned and underqualified Vein-Mending is rejected;
- finite treatment courses are time-weighted;
- Vein-specific care does not improve an ordinary fever merely because it exists;
- late-decline actors recover more slowly from otherwise identical injuries;
- repeated same-day profile recalculation cannot farm disability adaptation;
- adaptation advances by elapsed years;
- source-condition recovery does not erase disability;
- explicit disability repair works;
- cross-actor source-condition links are rejected;
- provider death stops provider-owned treatment;
- patient death stops treatment and freezes condition progression.

## Boundary retained for future work

This audit does **not** add epidemics, detailed disease ecology, childbirth physiology, combat wound generation, fertility physiology, or automatic specialist discovery. Those remain separate future systems. It also does not turn the World Bible's lifespan ranges into deterministic death dates.

## Final status

**v0.20.1 is the corrected health baseline.** The cumulative v0.1-v0.20.1 regression suite, v0.15.1 implementation audit, v0.19 household edge audit, and v0.20 health edge audit all pass.
