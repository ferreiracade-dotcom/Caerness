# Caerness v0.60.0 — ORGAGENCY-01 / POLITYAGENCY-01 / CONFLICT-01 Acceptance

**Date:** 19 September 2026  
**Status:** ACCEPTED WORKING CHECKPOINT  
**Schema:** 80  
**Predecessor:** schema-76 TENYEAR-01 accepted diagnostic branch

## Purpose

Schema 80 addresses the central TENYEAR-01 weakness: Caerness was good at simulating activity inside existing structures but weak at producing institutional and political change. This slice gives institutions and governments causal agency without collapsing every domain into one generic behavior tree, and gives WAR-01 an endogenous political origin path.

The shared causal shape is now:

`institutional inheritance + current regime + factions/pressures + issue-specific strategy + concrete capability -> domain candidates -> DEC-01 choice -> domain execution -> consequences`

Institutional culture is inertia, not destiny. Leadership can redirect an institution without retroactively changing its past. Capability remains a hard feasibility boundary.

## Schema 77 — shared organizational agency

New persistent owners:

- `organization_agency_profiles`
- `organization_regimes`
- `organization_factions`
- `organization_pressures`
- `organization_capabilities`
- `organization_strategy_positions`

Every active institution receives the shared substrate, but no generic institution behavior tree is created. Domain providers still own meaningful actions.

A regime change closes the previous active regime and opens a new one. It does not overwrite institutional inheritance. The same leader may begin a materially different regime when the regime kind changes.

## Schema 78 — underworld identity/capability bridge

The v0.60 city gangs already existed as durable underworld organizations, but some lacked institutional actor identity. Schema 78 bridges that boundary:

- each active underworld organization receives a structural institution identity where missing;
- organization type is not changed;
- a gang does not become a mafia family merely because it receives shared agency state;
- no generated identity is promoted into canon;
- resolution is not inflated beyond what the organization warrants.

Underworld operating capability is projected from concrete persisted state rather than a free-floating personality score. Current capability dimensions include territorial authority, enforcement, racket operations, front-business capacity, corruption access, recruitment and organizational continuity, plus the generic institutional-capacity projection where applicable.

## Schema 79 — polity agency

New owners:

- `polity_issue_states`
- `polity_government_actors`

Seven polities now have explicit decision authority. A named ruler acts where one exists. Collective/rulerless governments use a structural government decision body, preventing the absence of a crystallized monarch from freezing state agency.

Politics is relationship- and issue-specific. The engine does not assign a single national aggression score. One government may be hard-line on one frontier, cautious toward a great power and cooperative on another issue at the same time.

Opening geometry seeds six bilateral political relationships and twelve directional issue states from the accepted setting structure.

## Schema 80 — conflict origin

New owners:

- `conflict_channels`
- `conflict_incidents`
- `conflict_responses`

Five opening geopolitical channels represent specific sources of pressure rather than annual war probabilities. Pressure accumulates causally from the channel, current bilateral tension, directional issue pressure and restraint.

When a channel crosses its threshold it can create a concrete incident. The targeted government receives that incident through the normal information-bounded DEC-01 path and may receive concrete candidates such as:

- settle the incident;
- demand redress;
- limited retaliation;
- launch a limited campaign, only when physical feasibility exists.

There is no generic `go_to_war` candidate.

### Campaign feasibility

A limited campaign candidate requires:

- resolved origin and target locations;
- a traversable physical route;
- sufficient military-logistics readiness;
- no already-active campaign between the same attacker and defender.

Acceptance proves that a severe Greywood -> Dunmoor raid does **not** produce a campaign candidate while Stoneford and Westbrook are disconnected. Adding a test-only traversable road makes one limited-campaign candidate appear. Executing it creates a real WAR-01 operation/force and changes only the relevant bilateral political relation to `war`.

## Duplicate-response correction

The interrupted schema-80 working branch allowed repeated `demand_incident_redress` choices for an incident already formally answered.

This is closed at two boundaries:

1. candidate generation excludes incidents with an existing formal response;
2. execution independently rejects a stale/racing duplicate.

`conflict_responses` also has a unique `(incident_id, responding_polity_id)` constraint as a persistence-level backstop.

Acceptance verifies exactly one formal response can be recorded for the tested incident.

## Deterministic 365-day audit

Fresh current-seed activation followed by an unattended 365-day run produced:

- 3 conflict incidents;
- 2 formal government responses;
- 0 military campaigns;
- SQLite integrity `ok`;
- 0 foreign-key violations.

Incidents:

1. day 210 — Underheaven Empire -> Thornward border raid, severity 53.6, answered by formal demand;
2. day 300 — Greywood -> Dunmoor border raid, severity 53.0, answered by formal demand;
3. day 360 — Windmere -> Sunreach Confederacy maritime restriction, severity 48.6, still open at day 365 because it occurred after the target government's latest strategic review.

This is causal calibration, not a quota. Zero great wars remains plausible in the Long Uneasy Peace; a politically inert decade is no longer the only natural result.

## Mature-save migration gate

The accepted schema-76 TENYEAR-01 day-3650 save was copied and upgraded to schema 80.

Before migration:

- day: 3650;
- actors: 873;
- events: 5,324;
- institution profiles: 103;
- political-history rows: 129;
- underworld organizations: 11;
- war campaign operations: 0.

After migration + **narrow post-76 activation only**:

- day remains 3650;
- events remain 5,324;
- political-history rows remain 129;
- war campaign operations remain 0;
- actors: 886;
- institution profiles: 116;
- shared agency profiles / active regimes: 106 / 106;
- government decision actors: 7;
- political relations: 6;
- directional polity issue states: 12;
- conflict channels: 5;
- conflict incidents/responses: 0 / 0;
- all 11 active underworld organizations have institution identity;
- SQLite integrity `ok`;
- 0 foreign-key violations.

The 13 added structural institution actors are the 11 underworld identity bridges plus the two collective government bodies required for rulerless governments. No decade history is backfilled or re-authored.

A resumed copy advanced from day 3650 to day 3710 under schema 80 with zero scheduler errors, integrity `ok` and zero foreign-key violations.

## Regression gate

PASS:

- `orgagency_conflict01_test.py`
- `dec01_information_bounded_decision_runtime_test.py`
- `underworld_rackets_assets_test.py`
- `v60_underworld_rebuild_test.py`
- `econ01_underworld_economic_interests_test.py`
- `events01_territorial_event_sourcing_test.py`
- `war01_campaign_battle_world_consequences_test.py`
- `arch02_scheduler_chunk_invariance_test.py`
- `resclean01_resolution_owner_cleanup_test.py`
- `smoke_test.py`
- Python `compileall` for `engine/`

ARCH-02 remains deterministic at schema 80 across its 90-day chunk-invariance comparison.

### Known stale harness fence

`tests/decision_test.py` still asserts `decision_count > 10`. The untouched accepted schema-76 package deterministically produces exactly 10 and fails the same assertion. This is therefore a pre-existing stale threshold, not a schema-80 regression, and schema-80 behavior has not been distorted merely to satisfy it.

## Authority and migration rule

`activate_post76_agency_conflict()` is the narrow activation entry point for mature campaigns. It seeds only the new schema-77..80 agency/politics/conflict layers and deliberately does not replay older opening activators at the current campaign day.

Normal fresh activation calls the same entry point as part of `activate_existing_loops()`.

## Stop boundary

Schema 80 does **not** claim that organizational life-cycle work is complete.

Not yet implemented by this slice:

- generic institution formation/fission/merger/extinction;
- broad faction emergence and factional coups across every institution type;
- complete domain decision providers for sects, clans, churches, schools, craft organizations and merchant organizations;
- full rebellion/civil-war/succession-crisis origin ecology;
- comprehensive peace negotiation/treaty/war-exhaustion system;
- retroactive historical political incidents for existing saves.

The shared substrate intentionally does not manufacture generic actions where a domain lacks real causal objects.

## Next engineering priority

The next high-value slice is **ORGLIFE-01 / structural organization life cycle**, using the shared agency substrate to let institutions form, split, merge, decline and die. Political conflict can then expand from interstate incidents into internal crises, rebellions, clients/tributaries and succession disputes without returning to random event rolls.
