# Caerness Engine v0.20 — Health, Aging, Recovery, Disability, and Mortality

## Governing rule

> **Health changes capacity and life trajectory rather than simply toggling characters between combat-ready and dead. Recovery, adaptation, aging, disability, and continued usefulness all matter.**

v0.20 gives health one authoritative owner. Household/life-course simulation owns family and demographic continuity; the health layer owns bodily aging, conditions, recovery, disability, treatment, and mortality.

## Aging

Health profiles distinguish the World Bible's cultivation-linked longevity classes: ordinary, First, Temper, Third, Breach, Fifth, and Sixth. The engine does not treat these as guaranteed death ages. They are tonal longevity anchors.

Cultivation extends the prime before it extends old age. A character can therefore be chronologically elderly while still in the health model's prime phase. Late decline first reduces recovery and injury resilience, then sustained capacity, stamina, and mobility. A breakthrough or higher Stage can preserve the prime but does not rewind age.

## Conditions

Conditions are persistent records rather than narration-only flags. Supported families are ordinary injury, illness, chronic disease, fatigue, Channel injury, Core injury, Rupture, and other campaign-specific pathology.

Each condition can carry severity, capacity and pain burden, recovery and progression rates, fatality pressure, review cadence, and a specialist requirement. Conditions improve, worsen, become chronic, resolve, leave disability, or become fatal through authoritative state resolution.

Rupture remains anatomical Vessel damage. It is not magical corruption and does not produce supernatural fallout.

## Treatment

Treatments persist separately from conditions. Ordinary medicine, surgery, rehabilitation, rest, Vein-Mending, guided circulation, and elixir stabilization can all be represented.

Ordinary medicine can support a person with Vessel damage, but it cannot substitute for specialized repair. Vein-Mending and related cultivation medicine therefore produce a substantially stronger recovery modifier for Channel/Core/Rupture pathology. Current may be guided or given; cultivation itself is not simply transferred.

## Disability and adaptation

A resolved condition is not required to return a character to their previous baseline. Lasting impairment is stored as disability with mobility, stamina, and general-capacity effects. Adaptation can improve practical function over years without pretending the underlying impairment never existed.

This supports characters who continue meaningful careers after injury rather than treating disability as equivalent to removal from the simulation.

## Mortality

Named-character mortality is conservative and causal. Severe pathology can kill. Natural mortality pressure rises around the tonal lifespan range for the character's longevity class, but no lifespan value is a scheduled death date.

Aggregate cohorts use a separate mortality state so population-scale deaths do not require thousands of named actors. Cohort mortality is explicit and configurable by age band, allowing later ecology, war, famine, medicine, wealth, or regional systems to modify it without rewriting household logic.

## Camera integration

The player-facing scene packet now contains `health_context`: functional capacity, recovery, stamina, mobility, pain burden, current conditions, and disabilities. This is authoritative capacity state, not hidden-dice narration. Health can constrain what a character can sustain without choosing their intentions, personality, or commitments for them.

## Deliberate boundaries

v0.20 does not yet generate epidemics, famine disease, seasonal exposure, hospital networks, or battlefield wound anatomy automatically. Those systems can create health conditions later; v0.20 owns what happens after a health condition exists.

Combat still resolves combat. Health resolves bodily aftermath.


## v0.20.1 audit hardening

The edge-case audit established several invariants that are now enforced in code:

1. **Aging is path-dependent.** A later breakthrough may improve future preservation, but it does not reset already-accrued late decline or old-age mortality pressure.
2. **Recovery belongs to the body that is recovering.** A condition's nominal recovery rate is modulated by the actor's current recovery capacity.
3. **Treatment has ownership and duration.** Qualified care requires a living provider where the treatment logically requires one, and a treatment contributes only during the story-time interval in which it was active.
4. **Vein-Mending is not generic medicine.** It acts strongly on Channel/Core/Rupture pathology; ordinary medicine may support the body around such pathology but does not substitute for Vessel repair. Conversely, Vein-specific treatment does not become a universal cure for ordinary illness.
5. **Disability is persistent state.** Recovery of the source condition does not erase a disability. Adaptation changes functional impact over elapsed years, and genuine repair requires an explicit disability-resolution event.
6. **Death closes active care.** Treatments owned by the patient or by a deceased provider stop, and unresolved conditions on deceased actors become frozen historical state rather than continuing to improve or worsen.
