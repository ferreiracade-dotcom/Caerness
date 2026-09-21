# Caerness v0.60 — TENYEAR-02 Corrected Decade Acceptance

**Source commit:** `665b6af874e3b1a4c2f0e527617770f8ac56c47c`  
**Schema:** 104  
**Span:** day 0 → day 3650  
**Classification:** non-canon unattended acceptance / development evidence

## Verdict

**PASS.** The corrected decade completed with clean invariants and exact persisted restart replay. The run is suitable as the accepted TENYEAR-02 development benchmark. Known PARTIAL coverage remains explicitly partial and is not relabeled as complete.

## Annual trajectory

| Year | Population | Births | Deaths | Actors | Enterprises | Professionals | Events | Decisions | Stage attainments | DB MB |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 52,117,780 | 1,404,000 | 1,286,220 | 654 | 117 | 116 | 234 | 1690 | 12 | 29.2 |
| 2 | 52,246,327 | 1,407,180 | 1,278,633 | 679 | 135 | 136 | 564 | 3466 | 63 | 52.7 |
| 3 | 52,383,517 | 1,410,651 | 1,273,460 | 697 | 149 | 151 | 971 | 5287 | 50 | 74.9 |
| 4 | 52,527,613 | 1,414,355 | 1,270,259 | 723 | 163 | 172 | 1274 | 7215 | 29 | 94.3 |
| 5 | 52,677,175 | 1,418,246 | 1,268,684 | 745 | 175 | 188 | 1760 | 9651 | 32 | 121.4 |
| 6 | 52,830,996 | 1,422,284 | 1,268,463 | 777 | 184 | 203 | 2131 | 11888 | 29 | 145.5 |
| 7 | 52,988,054 | 1,426,437 | 1,269,378 | 820 | 190 | 216 | 2473 | 13986 | 24 | 168.9 |
| 8 | 53,147,478 | 1,430,677 | 1,271,253 | 854 | 199 | 230 | 2818 | 16066 | 30 | 192.3 |
| 9 | 53,308,518 | 1,434,982 | 1,273,942 | 886 | 206 | 242 | 3140 | 18164 | 18 | 217.5 |
| 10 | 53,470,527 | 1,439,330 | 1,277,322 | 916 | 209 | 247 | 3426 | 20350 | 14 | 241.1 |

## Load-bearing acceptance checks

- **population — PASS:** 52,000,000 -> 53,470,527 (+2.83%); aggregate births 14,208,141, deaths 12,737,615, net movement 0.
- **determinism — PASS:** Year-9 -> Year-10 replay: 438 substantive tables, 0 differences, 0 SQLite-sequence differences.
- **integrity — PASS:** Final integrity=ok; FK violations=0; contradiction errors=0 across annual audits.
- **information_firewall — PASS:** 20,350 decisions; 0 decisions carry canon-chunk basis.
- **business_profession — PASS:** Enterprises 104->209, professional profiles 100->247, merchant contracts 0->307.
- **latent_crystallization — PASS:** Latent entities 3->34; 30 are crystallized by final state. Earlier audit field based on crystallization_runs was not the authoritative count.
- **households — PASS:** Life events: {'birth': 89, 'coming_of_age': 15, 'household_formation': 81, 'other': 66, 'union': 84}; household migration plans final=6 ({'completed': 6}).
- **underworld — PASS:** Crews 38->40, personnel 49->51, operations=1441, membership flows=1446; no forced violence was required.
- **conditional_domains — PASS_WITH_EXTERNAL_EVIDENCE:** Natural WAR=0, LAW=0, patronage=0, OPPORTUNITY searches=0. Quiet is allowed; HEALTH/LAW/WAR capability branches are retained from schema-104 ONEYEAR acceptance, while patronage/OPPORTUNITY contracts explicitly require real persisted motives/needs.
- **tracked_mortality — PASS_CALIBRATION_NOTE:** No new tracked character death occurred; actual mortality audits imply ~0.88 expected tracked deaths over the decade, so zero is statistically plausible rather than evidence of a disabled owner. Aggregate deaths total 12,737,615.
- **organization_formation — KNOWN_PARTIAL_NOT_BLOCKING:** Emergent institution candidates=86 ({'merchant firm': {'forming': 86, 'eligible': 0, 'crystallized': 0}}). Merchant-firm candidates remain forming because autonomous enterprise expansion/staffing is explicitly still PARTIAL in coverage; successful ordinary firms are intentionally not auto-promoted to merchant Houses. This is a next-development target, not a TENYEAR integrity failure.

## Important interpretation

- The opening population of 52,000,000 is retained. The corrected demographic calibration grows it to 53,470,527 over ten years (+2.83%), so the earlier excessive jump was a stale-calibration problem rather than an opening-population problem.
- Natural quiet was not converted into fake activity. No canonical war or law case was manufactured simply to exercise counters.
- The authoritative latent-person crystallization count is the `latent_entities.status=crystallized` state: 30 by Year 10. `crystallization_runs` is not the authoritative counter for this current path.
- Merchant-firm institutionalization remains a real development target: 86 mature ordinary firms reached evidence-backed `forming` candidacy, but none crossed the organizational-depth threshold because autonomous enterprise staffing/expansion remains explicitly PARTIAL. The decade therefore exposes the next useful development task without invalidating deterministic/integrity acceptance.

## Restart determinism

The exact Year-9 checkpoint (day 3285) was independently advanced to day 3650. Comparison covered **438 substantive tables** and found **0 differences** and **0 SQLite-sequence differences**. Both copies pass SQLite integrity and foreign-key checks.

## Regression status

Post-decade standard/focused suite: **105/105 passed**. The dedicated 120-year candidate-scale harness is retained as prior stress evidence and was not rerun as part of this post-decade standard sweep.

## Development consequence

TENYEAR-02 should now be preserved as the accepted decade benchmark. The next development work should build on the clean day-0 development tree, not on the Year-10 world as campaign canon. The Year-10 database and annual checkpoints remain acceptance evidence for regression and future comparisons.
