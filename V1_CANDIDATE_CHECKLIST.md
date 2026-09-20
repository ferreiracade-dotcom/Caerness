# v1.0 Candidate Checklist — closed by v0.26.1

## Blockers
- [x] Isolate tests from live campaign DB; guard destructive reset.
- [x] Add ordered schema migrations + pre-migration backup + representative upgrade validation.
- [x] Add real Caerness campaign bootstrap/seed with provenance.
- [x] Bring phone-first UI to setup/inspection/diagnostic parity for core player needs.
- [x] Remove stale mobile runtime version strings.

## Integration hardening
- [x] Declare authoritative owner for mirrored fields.
- [x] Add contradiction checks for actor/life status, territorial owner mirror, player location mirror, migration/travel linkage.
- [x] Add domain-state -> generic goal/pressure adapters.
- [x] Document v1 crystallization as actor-first; broader entity crystallization is post-1.0 unless campaigns prove it necessary.

## Scale validation
- [x] Realistic inhabited seed, not miniature fixture.
- [x] 20/40/120-year run on realistic seed.
- [x] Multiple deterministic seeds/configurations.
- [x] Dense same-day scheduler load test.
- [x] Large route/information graph test.
- [x] Differentiated business-scale test.
- [x] Record DB growth and checkpoint latency.

## RC cut
- [x] Full cumulative suite PASS.
- [x] All adversarial audits PASS.
- [x] Candidate-scale stress PASS with zero critical contradictions.
- [x] Clean DB/package state.
- [x] Documentation/version strings consistent.

**Gate result: READY FOR v1.0-RC1.**
