# Caerness Engine Implementation Audit — v0.1 through v0.17

## Audit standard

This audit distinguishes **implemented runtime behavior** from design prose. A feature counts as implemented only when it has persisted schema/state, an executable service/runtime path, and a regression that proves state actually changes through the authoritative engine. A document or callable stub alone does not qualify.

## Cumulative result

The v0.17 release retains the previously audited v0.1–v0.15.1 foundation, the v0.16 civilian core, and adds a tested deeper civilian-life layer. The cumulative test runner executes canon, decisions, dormant simulation, interactions, information, player actions, model gateway, v0.7 through v0.17 version regressions, and the dedicated v0.1–v0.15 implementation audit.

**Result: PASS.**

## Previously audited foundation

The earlier audit established that the following are executable rather than prose-only: SQLite world truth; shared story time; actor tiers and dormant continuation; goals/pressures/relationships; agreements and interactions; information/rumour propagation; player action interpretation and agency handoff; model gateway boundaries; continuity/resolution levels; historical crystallization; persistent embodiment and speech mediation; domain competence and professional readings; transactional time skips; battle/duel resolution; multi-front command, tactical grammar and Vein battlefield assets; and automatic contextual duel-to-battle consequence.

## v0.16 verification

`v16_test.py` proves that civilian systems move under the shared clock: market prices update, production produces account entries, career stages can advance only where track rules explicitly permit it, cultural projects create persistent objects and provenance, auctions transfer ownership, shadow-market exposure evolves abstractly, and households retain persistent economic state.

## v0.17 verification

`v17_test.py` proves the new systems are not merely declared:

- a completed architecture project creates a persistent `buildings` record and that building continues to age/receive maintenance through world-time advancement;
- a local fashion/style adoption value changes through repeated shared-clock reviews rather than a one-off setup call;
- a credit agreement transfers enterprise cash/debt at origination, accrues interest, crosses its due date, defaults, and leaves the borrower economically strained;
- enterprise ownership and governance shares persist separately;
- professional membership seniority advances over hundreds of days and creates review eligibility without changing the member's office automatically;
- a deceased household head triggers the persisted succession plan, creates a succession event, changes the household head, and transfers personal cultural property with an `inherited` provenance record;
- `civilian_summary()` exposes the new layer so it is visible to runtime/UI callers.

## CLI/service exposure

The v0.17 systems are available through Python services and through `run.py` commands for buildings, styles/adoption, succession plans/claims/resolution, credit creation/payment, enterprise partnerships, and professional membership. This closes the class of issue previously found in combat where a subsystem could exist internally without an ordinary runtime access path.

## Deliberate limits, not missing implementation

v0.17 does **not** yet simulate every family birth, marriage negotiation, inheritance law, architectural floorplan, garment cut, committee vote, or banking ledger line. Those would be higher-resolution expansions. The current systems intentionally persist the causally important institutional state while compressing routine.

No v0.17 mechanism establishes new universal World Bible canon. These are campaign-history systems operating under the existing canon/campaign distinction.

## Next roadmap state

The civilian layer is now broad enough to support long-run testing. The next major architectural roadmap item is therefore the long-run simulation suite: 20-year, 40-year, and 100+ year runs; protagonist death/camera succession; political-map divergence; quiet-life and extreme-success campaigns; institutional succession; and historical-crystallization consistency.
