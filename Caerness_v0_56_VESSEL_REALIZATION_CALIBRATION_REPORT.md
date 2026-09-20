# Caerness v0.56 — Vessel/Realization Cultivation Calibration Report

## Status

**Engine version:** 0.56.0  
**Schema:** 48 (unchanged)  
**Authority:** Caerness World Bible remains setting canon. Numeric probabilities and thresholds below are campaign calibration, not new setting canon.

## World-Bible constraints implemented

The World Bible gives a clear causal progression:

- Cultivation begins as a **Vessel problem** and increasingly becomes a **Realization problem**.
- Vessel cultivation develops Core capacity, Channel throughput, bodily adaptation, efficiency, recovery, and control.
- Congenital Vessel quality changes the speed of physically dominated early development, but is not a rigid destiny ceiling.
- Realization is accumulated martial understanding and the solution of problems that instruction alone cannot solve.
- Temper is the first major maturation and the professional backbone of serious Churn martial power.
- Third is the point at which whole-Vessel circulation becomes normal and is the apex of purely internal-current development.
- Breach is where coherent Aura extends beyond the Vessel and is the first unmistakable Master threshold.
- Lower-stage instruction is standardized, scalable, teachable, and benchmarked; cultivation becomes progressively more individualized at higher Stage.
- The Hearth advantage is environmental and social — richer current, teachers, manuals, peers, medicine, elixirs, infrastructure, and accumulated transmission — not an anatomical law.
- The World Bible explicitly gives an outer-world social offset: mature strong Churn professionals commonly occupy Third, while Temper often fills the analogous role outside the Hearth.

The engine now treats those statements as design constraints rather than flavor text.

## Transition regimes

| Current Stage | Next Stage | v0.56 regime | Primary bottleneck |
|---|---|---|---|
| Unstaged/Open Core | First | Vessel maturation | Establishing deliberate cultivation |
| First | Temper | Vessel maturation | Major physical/Core/Channel maturation |
| Temper | Third | Vessel maturation | Whole-Vessel circulation; demanding especially in poorer current ecology |
| Third | Breach | Realization wall | Genuine insight required to externalize coherent Aura |
| Breach | Fifth | Realization wall | Deep integrated martial understanding |
| Fifth | Sixth | Realization wall | Pinnacle integration; geography again matters strongly |

### Lower ladder

First→Temper and Temper→Third no longer use the same rare-Realization lottery as mastery. Once actual structural readiness is achieved, maturation can occur without a special enlightenment event. Uncertainty lives in Vessel aptitude, current ecology, teaching, resources, injury, effort, and the time required to reach physical readiness.

Ordinary Realization still matters at the lower Stages: a practitioner must know how to use what their Vessel can sustain. It is simply not modeled as the rare, individualized insight wall that defines mastery.

### Mastery ladder

Third→Breach and above retain broad irregular opportunity timing plus Stage-specific Realization requirements. A practitioner can have a fully capable body for years and never solve the next martial problem. This is where permanent plateaus become normal rather than exceptional.

## Regional implementation

There is no `if outside_churn: cannot_reach_third` rule.

The same anatomy and Stage thresholds apply everywhere. The regional difference emerges through causal inputs:

- current ecology,
- institutional/training milieu,
- teachers and peers,
- medicine and resources,
- and other cultivation infrastructure.

Temper→Third receives a nonlinear whole-Vessel ecology factor because Third requires normal whole-body circulation. This reproduces the World Bible's outer-world Third bottleneck while still allowing rich outer schools, exceptional sites, prodigies, or unusually well-supported practitioners to reach Third quickly.

Current campaign-calibration expression:

`whole_vessel_current_factor = clamp((ecology / 55)^4, 0.25, 1.12)`

This is an engine parameter, not a canonical metaphysical equation.

## No age destiny

v0.56 preserves the inverse age-at-attainment rule:

- Age never supplies breakthrough progress.
- Current age never creates catch-up pressure.
- Historical time-at-Stage is not fabricated from age.
- Stage-attainment chronology is recorded independently from current age/current Stage.
- Opening/current Stage plausibility may still be assessed from age + culture + role + training history. That is a seeding/biography question, not a runtime promotion mechanic.

Thus a mature Churn professional being Third can be common while a particular older Temper remains Temper indefinitely. A young Breach is possible, but should emerge from exceptional causes rather than an age rule.

## Multi-seed ten-year validation

Three independent ten-year cohort seeds were run against the named opening cultivation population. These are calibration diagnostics, **not canonical population probabilities**.

### Opening Firsts after ten years

| Context | Seed 1 | Seed 3 | Seed 5 |
|---|---|---|---|
| Hearth/Churn First (n=50) | 38 Third / 12 Temper | 39 Third / 11 Temper | 37 Third / 12 Temper / 1 Breach |
| Outer First (n=27) | 26 Temper / 1 Third | 25 Temper / 2 Third | 24 Temper / 3 Third |

### Opening Tempers after ten years

| Context | Seed 1 | Seed 3 | Seed 5 |
|---|---|---|---|
| Hearth/Churn Temper (n=53) | 48 Third / 3 Temper / 2 Breach | 48 Third / 3 Temper / 2 Breach | 48 Third / 4 Temper / 1 Breach |
| Outer Temper (n=26) | 13 Third / 13 Temper | 9 Third / 16 Temper / 1 Breach | 14 Third / 12 Temper |

### Opening Thirds after ten years

| Context | Seed 1 | Seed 3 | Seed 5 |
|---|---|---|---|
| Hearth/Churn Third (n=57) | 55 Third / 2 Breach | 55 Third / 2 Breach | 54 Third / 3 Breach |
| Outer Third (n=36) | 35 Third / 1 Breach | 35 Third / 1 Breach | 35 Third / 1 Breach |

### Reading the cohort results

Across these seeds:

- roughly three quarters of opening Hearth Firsts progress to Third within another decade;
- nearly all opening outer Firsts mature to Temper but only a small minority reach Third;
- established Hearth Tempers very commonly reach Third;
- established outer Tempers split between remaining Temper and reaching Third;
- Third→Breach remains only a few percent over the sampled decade rather than becoming the next routine career step.

That is the intended qualitative ecology: lower-stage professionals cluster closer to their regional norm because Vessel development is comparatively trainable, while the Master threshold creates a much steeper, more individual funnel.

## Focus-character cultivation diagnostic

These are cultivation-only alternate histories, not accepted canon biographies.

| Character | Context | Start | Vessel aptitude | Realization aptitude | Result after 10 years |
|---|---|---|---:|---:|---|
| Sella Marrin | Churn / independent Long Road | Temper, 24 | 0.834 | 0.844 | Third, 34 |
| Tobin Verra | Churn / Wrenfield | Temper, 23 | 1.196 | 1.121 | Third, 33 |
| Ansel Rooke | Dunmoor retainer | Temper, 31 | 0.547 | 1.356 | Temper, 41 |

### Sella

Sella reaches Third on Day 1275 (approximately age 27.5). The transition is recorded as `vessel_maturation`: no rare Realization opportunity is required. By Year 10 her Third-stage Vessel is strong, but ordinary practice has reached the Third-stage Realization cap, so she does not drift into Breach.

### Tobin

Tobin reaches Third on Day 1090 (approximately age 26.0), also through `vessel_maturation`. Wrenfield's continuing institutional milieu improves his lower-stage development, but after reaching Third he likewise hits the ordinary-practice Realization ceiling rather than being guaranteed mastery.

### Ansel

Ansel remains Temper through age 41. His result is especially useful diagnostically: his Realization aptitude is the highest of the three, but his Vessel aptitude is by far the lowest, and ordinary Dunmoor current conditions make the whole-Vessel Third transition physically harder. High understanding cannot give him a capability his Vessel cannot yet sustain. This directly expresses the World Bible's rule rather than an arbitrary regional cap.

## Stage-bound Realization

Realization anchors are now Stage-bound by default. Experience acquired while solving a First-stage problem cannot be banked indefinitely and later spent on Breach. On successful advancement, unresolved Stage-bound anchors from the old Stage are closed.

This prevents two prior failure modes:

1. failed insight anchors being rerolled every review until success;
2. lower-Stage occupational experience silently accumulating into guaranteed later mastery.

## Summit check

The stronger Realization wall does not freeze high cultivation. A five-seed decade sweep produced new Sixth-stage attainments of:

`0, 0, 0, 1, 3`

for final Sixth counts of `40, 40, 40, 41, 43` respectively.

The point is not that these are canonical rates. The point is that the summit remains permeable through actual causal state while old Fifths receive no age-based upward pull.

## Regression status

Passing after the v0.56 changes:

- `v56_test.py` — Vessel-led lower ladder / Realization-wall mastery
- `v48_attainment_inverse_test.py` — inverse age/attainment chronology
- `v47_test.py` — Groundbinding dependency
- `v46_test.py` — probabilistic Stage timing / summit variability
- `v45_test.py` — decade integrity / latent commercial emergence
- `v44_test.py` — autonomous two-way resolution
- `v42_test.py` — long-run cultivation demography
- `v37_test.py` — underworld ecology
- `v33_test.py` — elixir/Sediment/Rupture conservation
- `v32_test.py` — causal cultivation/Realization
- `v29_test.py` — commercial logistics conservation
- `v20_test.py` — health/aging

## Remaining boundary

This v0.56 branch is the corrected **cultivation core**, rebuilt from the last durable v0.47 engine plus the inverse-attainment work. The richer later role/life/underworld coupling developed in the intervening v0.49–v0.52 work is not yet fully merged into this durable branch.

Therefore the focus-character runs above validate cultivation mechanics only. They should not be treated as the final six-person ten-year biography acceptance run.

## Acceptance conclusion

v0.56 is accepted as the current cultivation calibration baseline because it now satisfies all of the following simultaneously:

- early progression is substantially Vessel-dominated;
- mature Churn professionals can commonly reach Third;
- Temper remains a common mature-professional outer-world level;
- outer Third is harder but never forbidden;
- Third→Breach is the first major Realization wall;
- later advancement becomes increasingly individual and uncertain;
- age never creates advancement pressure;
- exceptional early mastery remains possible through causal history;
- indefinite lower- or mid-Stage plateau remains possible.
