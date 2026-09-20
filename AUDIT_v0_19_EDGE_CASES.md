# Caerness Engine v0.19 Edge-Case Audit

**Audit target:** v0.19.0 household, kinship, demographic, and life-course systems.  
**Resulting hardened baseline:** v0.19.1.  
**Scope:** births, guardianship, household splitting, migration, service terms, kinship links, and aggregate demographic cohorts.

## Executive result

The v0.19 systems were real and connected to shared story time, but the edge-case audit found several state-integrity gaps that would have become serious over a multi-decade simulation. The problems were not missing tables; they were boundary conditions where persisted records could disagree with one another. Those issues are corrected in v0.19.1.

## Births

**Found:** family-plan births were only guaranteed to be checked at the periodic household-life tick, so a persisted due day could resolve late. Manual birth registration also accepted arbitrary historical days, which could create a child actor whose membership history began after its claimed birth. Sibling generation only linked children shared by both union partners, omitting half-sibling relations.

**Fixed:** exact family-plan due days participate in the scheduler. Automatic births require an active union, living union actors, an explicit birth parent who belongs to that union, and an eligible living birth-parent profile. Manual birth registration is current-story-day only; retroactive births belong to historical crystallization. Sibling linking uses either recognized parent, while desired-child counting remains union-specific.

## Guardianship

**Found:** a ward could be moved into a guardian household while remaining an active member/dependant of the previous household. Duplicate active guardianships were possible across different days, there was no explicit end operation, and a moved ward who had been the old household head could leave that household pointing at a non-member head.

**Fixed:** duplicate active guardian/ward pairs are idempotent; moving a ward closes stale household membership and dependency records; vacated household heads are repaired or the empty household dissolves; explicit `end_guardianship` closes guardianship, guardian/ward kinship, and the matching dependency. Death also ends relevant guardianships.

## Household splitting

**Found:** arbitrary actors who were not source members could be pulled into a split; resource-share values above 1 were silently clamped; moving dependants, wards, and household staff left their dependency/guardianship/service records attached to the old household; moving the source head could leave the old household headed by a former member; union household affiliation could become false after one or both partners moved.

**Fixed:** all movers must be active source members; shares must be within 0..1; active dependency, guardianship, and service records follow the relevant mover; a union moves with both partners or loses the old shared-household attachment when only one leaves; the source head is repaired deterministically from remaining active members or the source household dissolves when empty.

## Migration

**Found:** multiple planned migrations for the same household could coexist and later fire in sequence; past-day and no-op same-location plans were accepted. Aggregate cohort review scheduling also used global calendar-year boundaries rather than each cohort's own last-review day.

**Fixed:** a new unresolved migration supersedes the prior plan; past and same-location plans are rejected; closed households cannot migrate; cohort annual due dates derive from each cohort's own `last_review_day`.

## Service terms

**Found:** adding a service term used household membership insertion in a way that could overwrite an existing family/household role. Duplicate active service terms could accumulate. A dissolved household could theoretically renew a very strong service relationship. Actor death did not close service terms.

**Fixed:** existing household roles are preserved; duplicate active household/actor/role service terms are idempotent; dissolved/historical households cannot renew service; death closes active service records. Service still does not automatically imply that the household is the actor's sole residence, preserving room for non-resident retainers and guards.

## Kinship links

**Found:** repeated recognized relationships could accumulate across days, and if only one direction of a reciprocal pair existed, re-adding the relation did not repair the missing inverse. Union/guardianship end operations were absent.

**Fixed:** active recognized kinship is idempotent, missing reciprocals are repaired, half-sibling links are produced from either recognized parent, and explicit union/guardianship end APIs move spouse or guardian/ward links to former status.

## Aggregate demographic cohorts

**Found:** the original v0.19 implementation applied birth pressure and net migration but never aged population from `0_4` into `5_12`, etc. A 40-year run would therefore leave cohorts permanently trapped in the band where they were seeded. This was the most serious demographic gap.

**Fixed:** annual aggregate reviews now perform bounded Leslie-style aging across `0_4 -> 5_12 -> 13_17 -> 18_39 -> 40_59 -> 60_plus`. Transfers use a snapshot so incoming population cannot cascade through several age bands on the same tick. Missing destination bands are created automatically. Existing non-due destination cohorts receive inflow without losing their own partial-year review clock. Population is conserved except for explicit birth pressure and net migration. Mortality remains deferred to v0.20 by design.

## Regression coverage

`tests/v19_edge_test.py` now verifies:

- exact-day birth resolution and retroactive-birth rejection;
- half-sibling linkage and idempotent kinship;
- stale-residence cleanup and explicit guardianship ending;
- split membership validation, attached-record transfer, source-head repair, and share bounds;
- preservation of pre-existing household role when adding service;
- migration-plan supersession and invalid-date/location rejection;
- death cleanup for service/guardianship/dependency state;
- annual cohort aging, population conservation, and no same-tick cascade aging.

## Remaining deliberate boundaries for v0.20

This audit does **not** add physiological fertility, pregnancy simulation, disease, injury, disability, recovery, cultivation-specific aging, or mortality. Those remain one coherent health/aging domain for v0.20.
