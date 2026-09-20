# CAERNESS — INFOIDX-01 INFORMATION SCHEDULING INDEX ACCEPTANCE
**Date:** 18 September 2026  
**Engine:** v0.60.0 / schema 75+  
**Status:** ACCEPTED

TENYEAR-01 Year 6 profiling showed information scheduling/rumour seeding—not graph traversal—had become the dominant long-run cost. The expensive operation was repeatedly asking whether any rumourable event remained unseeded.

Two authority-preserving indexes were added:
- `rumours(truth_event_id)`;
- `event_information(visibility, rumorability, event_id)`.

On identical schema/backfilled Year-5 state, the same 30 simulated days measured:
- without indexes: 14.5813 s;
- with indexes: 2.6114 s;
- speedup: ~5.58×.

All 30 authoritative comparison tables hashed identically. The fix changes query access only; information, rumour, belief and provenance semantics are unchanged.

**Verdict:** native SQLite indexing solved the demonstrated bottleneck. No external information framework or graph backend is justified for this problem.
