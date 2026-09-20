# CAERNESS — ROUTE-01 NATIVE ROUTE SNAPSHOT ACCEPTANCE
**Date:** 18 September 2026  
**Engine:** v0.60.0  
**Status:** ACCEPTED

TENYEAR-01 exposed a real late-run merchant bottleneck: repeated SQL route searches dominated ordinary market cycles after merchant observations accumulated.

At the exact Year-4 checkpoint (day 1460), the route tournament compared authoritative SQL pathfinding, SQL-per-cycle memoization, a native read-only route snapshot, and NetworkX. Across all 132 connected origin/destination pairs, both the native snapshot and NetworkX reproduced the authoritative path and information-lag semantics with zero mismatches.

Measured repeated workload (2,376 calls):
- current repeated SQL: 0.17365 s;
- SQL memo: 0.13471 s (~1.29×);
- NetworkX snapshot: 0.00925 s (~18.8×);
- native Caerness route snapshot: 0.00282 s (~61.5×).

The native snapshot was ~3.3× faster than NetworkX on this small operational graph, required no dependency, and preserved SQL as authority. The full merchant-cycle comparison was stronger: 0.5142 s → 0.0386 s (~13.33×), with identical hashes for merchant offers, awareness, observations, commercial stock, enterprises and engine metadata, plus clean integrity/FKs.

**Verdict:** adopt the graph access pattern, not NetworkX. Build one read-only route snapshot per merchant market cycle from authoritative `travel_routes`; route mutations remain SQL-owned and invalidate naturally on the next cycle.
