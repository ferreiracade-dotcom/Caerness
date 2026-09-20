# Caerness Engine Implementation and Depth Audit — v0.1 through v0.18

## Two audit questions

The engine is now evaluated against two separate standards:

1. **Implementation audit:** does the subsystem have persisted state, an executable runtime path and a regression proving authoritative state change?
2. **Depth audit:** is that implemented subsystem differentiated enough to support decades of simulation without generic placeholder behavior?

The earlier v0.15.1 audit remains the implementation baseline. `DEPTH_AUDIT_v0_1_TO_v0_17.md` is the first systematic depth review.

## Cumulative implementation result

The complete v0.1-v0.18 suite passes, including the dedicated v0.15.1 implementation-hardening regression.

**Result: PASS.**

## v0.18 verification

`v18_test.py` proves that differentiated businesses are not merely labels:

- the engine archetype catalog contains hospitality, entertainment, finance, craft, retail, professional, logistics and security businesses, including inns, theatres, gambling houses, pleasure/courtesan houses, loan houses, smithies, tailors, physicians and warehouses;
- four enterprises configured in the same city resolve recurring cycles through the shared world clock;
- a high-cultural-activity / high-event district favors a theatre over a smithy when craft and military demand are weak;
- high regulation suppresses a regulation-sensitive gambling-house profile more strongly than an ordinary theatre profile;
- high credit demand and real outstanding credit produce operating income for a loan house;
- changing the same city's commercial context toward military/craft demand increases the smithy's demand while reducing the theatre's demand;
- relaxing regulation materially changes the regulated venue's utilization;
- business cycles write authoritative revenue and expense entries and update enterprise cash/status;
- the civilian summary exposes business ecology rather than hiding it behind internal-only services.

## Depth status after v0.18

v0.18 closes the most immediate civilian gap identified by the depth audit: `shop`, `service`, and `workshop` are no longer the only meaningful business distinctions.

It does **not** close the remaining long-run gaps. The highest-priority thin/absent domains remain:

1. household, kinship, demography and life-course change;
2. health, aging, recovery, disability and medicine;
3. religion, ritual, patronage and cultural institutions;
4. seasons, ecology, travel friction and harvest/environmental cycles;
5. explicit polity/state transformation and institutional succession;
6. education, apprenticeship, mentorship and intergenerational transmission;
7. final 20/40/100+ year validation.

## Release conclusion

v0.18 is a stronger base for long-run civilization simulation than v0.17, but the engine should still **not** claim final 40-year validation until the remaining high-priority domain passes are implemented.
