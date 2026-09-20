# Caerness Engine v0.59.0 — Accepted Handoff

## Accepted scope
Career, Responsibility, Reach, Underworld Organization-Form, Gang Membership-Flow & Operational-Scale pass.

## Engine/schema
- Engine: `0.59.0`
- Schema: `50`

## Core corrections
- Career standing is coarse and non-mandatory; responsibilities branch independently.
- Success widens reach/opportunities without guaranteeing promotion.
- Open-Core is capability, not profession.
- Independent criminal organizations do not use a universal career ladder.
- Cale starts as boss of a pre-existing **independent Aldergate ward gang**; organizational change affects morphology, reach and staffing, not a personal “crew leader” rank.
- Gang, Mafia-style family, criminal dynasty, syndicate, criminal enterprise, network and crew are parallel forms.
- No automatic gang→Mafia-family conversion.
- Pre-existing organizations crossing significance thresholds are crystallization/tracking events, not retroactive formation events.
- Gang membership is a stock-and-flow model with core, active and peripheral participation plus recruitment and attrition flows.
- No desired final gang size is encoded; the former `member_count < 18` recruitment gate is removed.
- Lazy membership-profile creation does not fabricate a fringe or discard elapsed turnover time.
- **The old eight-person Cale opening is removed.** When headcount is unspecified, opening manpower resolves from concrete operational footprint. Explicit canon/scenario headcounts always override.
- SQLite branch reset removes DB/WAL/SHM before each diagnostic copy.

## Underworld scale calibration
Cale's starting footprint is: cartage-yard front, two recurring rackets, ward-level territorial activity, group enforcement/gang-fight capacity, targeted-killing capacity and two command layers.

Across ten opening-resolution seeds, that exact footprint resolves to **31–64 full members** with **49–85 people in the wider orbit**. These are not target bands for all gangs; they are the result of this particular functional footprint.

Canonical seed 9201 resolves:
- opening: 37 full members + 17 peripheral associates (54-person orbit)
- ending after ten years: 33 full + 4 peripheral (37-person current orbit)
- lifetime entries: 31
- lifetime exits/losses: 48

Final-code alternate seed 9204 resolves:
- opening: 32 full + 17 peripheral
- ending: 26 full + 12 peripheral
- lifetime entries: 44
- lifetime exits/losses: 55

A lighter footprint may still produce a 4–10-person crew/micro-gang; larger gangs can scale far beyond this. Organizational form is not determined by headcount.

See `diagnostics/v59_underworld_operational_scale_calibration.json`.

## Six-character decade gate
The five non-underworld v0.59 branches remain valid because this correction is confined to underworld scale resolution and the Cale diagnostic opening. The underworld branch has been rerun from original seed 9201 on final code to Day 3650.

## Tests
Green after final scale correction: v59, v37, v45, v44, v42, v35, v33, v32, v29, v20.

## Known source-text follow-up
World Bible wording “Street gangs rise and disappear quickly. Durable criminal power looks different.” should be softened/revised. Durable gangs are permitted; organizational form and durability are separate.

## Post-acceptance successful-gang stress test
A conditional success run exposed and corrected a remaining underworld calibration problem: economic/operational success was insufficiently coupled to recruitment, retention and peripheral→active conversion, so prosperous gangs were systematically biased toward manpower contraction. Success coupling now uses cash per full member, work/front/racket support, deterrent reputation, command capacity, cohesion and membership stability; it does not impose a growth target.

Racket expansion was also corrected so an `added another racket` event must add genuinely new criminal business rather than repeat an existing racket under the same or a relabelled evidence kind.

Strong-success seed 9508 (selected conditionally; not canonical) runs Day 0→3650:
- 41 full + 21 peripheral → **68 full + 8 peripheral**
- hard core 8 → **17**
- command depth 2 → **3**
- racket breadth 24.0 → **52.85**
- territory 22.0 → **25.0**
- front depth 28.0 → **30.8**
- cartage-yard cash 10.0 → **268.34**
- 62 lifetime entries / 48 exits-losses
- new rackets: unlicensed betting, cargo diversion/commercial fraud, contraband cartage
- organization type remains **gang**.

See `Caerness_v0_59_SUCCESSFUL_GANG_STRESS_TEST.md` and `diagnostics/v59_cale_successful_decade_*`.
