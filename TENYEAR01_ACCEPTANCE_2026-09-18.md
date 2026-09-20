# CAERNESS — TENYEAR-01 ANNUAL AUDIT

**Branch:** non-canon unattended diagnostic  
**Final engine:** v0.60.0 / schema 76  
**Canonical span:** day 0 → day 3650

## Annual trajectory

| Yr | Pop. | Births | Deaths | Actors | Enterprises | Crystallized latent | Events | Knowledge | Trade unmet | War ops | DB MB |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 52,523,380 | 832,000 | 308,620 | 619 | 131 | 1 | 228 | 3,735 | 980,794 | 0 | 24.5 |
| 2 | 53,042,694 | 840,374 | 321,060 | 623 | 168 | 5 | 532 | 8,057 | 938,673 | 0 | 39.9 |
| 3 | 53,557,725 | 848,683 | 333,651 | 652 | 192 | 34 | 894 | 12,769 | 947,951 | 0 | 55.7 |
| 4 | 54,068,312 | 856,924 | 346,337 | 694 | 212 | 75 | 1,291 | 17,690 | 957,153 | 0 | 71.5 |
| 5 | 54,574,333 | 865,093 | 359,072 | 721 | 229 | 102 | 1,856 | 25,732 | 966,275 | 0 | 92.8 |
| 6 | 55,075,699 | 873,189 | 371,823 | 756 | 245 | 126 | 2,413 | 34,237 | 975,315 | 0 | 115.8 |
| 7 | 55,572,347 | 881,211 | 384,563 | 793 | 254 | 145 | 3,047 | 45,365 | 1,066,283 | 0 | 141.4 |
| 8 | 56,064,237 | 889,158 | 397,268 | 822 | 265 | 164 | 3,756 | 58,658 | 993,146 | 0 | 170.1 |
| 9 | 56,551,342 | 897,028 | 409,923 | 847 | 274 | 176 | 4,524 | 74,576 | 1,001,933 | 0 | 202.5 |
| 10 | 57,033,651 | 904,821 | 422,512 | 873 | 278 | 190 | 5,324 | 91,974 | 1,010,636 | 0 | 237.2 |

## Decade-level observations

- Population changed from **52,000,000** to **57,033,651** (+5,033,651) through live births/deaths/movement rather than quota rebalance.
- Named/tracked actors grew to **873**; **190** latent entities had crystallized by Year 10.
- Tracked enterprises grew to **278**.
- The event ledger reached **5,324** events and actor knowledge **91,974** rows.
- Natural war operations during the canonical decade: **0**. WAR-01 is therefore tested separately in a bounded trigger branch.
- Every annual checkpoint reports SQLite integrity `ok` and zero foreign-key violations.

## Performance/codebase outcomes discovered during the decade

- ROUTE-01: repeated SQL pathfinding became a demonstrated merchant bottleneck. A native read-only route snapshot reproduced authoritative paths/lags and beat NetworkX on this graph; the native snapshot was adopted, not the dependency.
- INFOIDX-01: information scheduling slowdown was caused by missing causal lookup indexes, not a framework limitation. Two indexes produced a ~5.6× 30-day improvement with state equivalence.
- ARCH-02 remains SQL-authoritative and caller-boundary invariant. Long-horizon API calls can still exhibit performance spikes, so diagnostic decade advancement used proven-equivalent bounded chunks.
- RESCLEAN-01/schema 76 removes false overdue resolution scheduling without changing domain history or future surrogate-ID determinism.

## Acceptance evidence

- Canonical day-3650 hard invariants: PASS.
- Canon/hidden-truth basis hits in decision audit: 0.
- Year-10 restart replay from exact Year-9 checkpoint: all persisted tables and SQLite sequences identical after wall-clock fields are excluded.
- Separate WAR trigger branch: PASS.
- Current schema-76 regression suite: PASS.
