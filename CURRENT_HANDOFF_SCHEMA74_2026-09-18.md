# Caerness Engine Current Handoff — schema 74 / 18 September 2026

**Engine:** v0.60.0  
**Schema:** 74  
**Current World Bible:** `canon/world_bible_current.docx` (18 September repaired master)  
**Current seed line:** v1.3  
**Production scheduler:** ARCH-02 SQL-authoritative ProcessRegistry

## Newly accepted in this working line

- SCALE-01 opening population/settlement scale authority;
- TRADE-01 aggregate ordinary trade below explicit MERCHANT-01 commerce;
- POPBACK-01 bounded background identity reservoirs;
- POPLIFE-01 live aggregate population and explicit source-to-source movement;
- ARCH-02 scheduler cutover with caller-boundary invariance;
- PRESBACK-01 Neighborly-style reverse/cached presence access.

## Strongest acceptance result

A fresh 365-day world advanced once and the same world advanced as `30×12+5` produce identical nonvolatile row hashes across the 30-table authoritative acceptance set.

The current focused regression suite for these systems is green and SQLite integrity/FK checks pass.

## Next task

Run TENYEAR-01 fresh from day 0 using this schema-74 engine. Do not reuse a pre-schema-74 decade branch.

Follow `CAERNESS_POST_ARCH02_TENYEAR_ROADMAP_2026-09-18.md`.

External frameworks should only be revisited if TENYEAR-01 profiling demonstrates the corresponding bottleneck. See `CODEBASE_COMPARISON_VERDICT_2026-09-18.md`.
