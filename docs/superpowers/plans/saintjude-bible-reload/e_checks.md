# Saint Jude Engine Implications: E-001 to E-028 against the code

Repo D:\Code\Caerness, branch feat/world-packages-saintjude, HEAD c3e58b2. Read-only. All tests ran on scratch copies under this scratchpad (sj.db etc.), never the live DBs, never the caerness MCP tools.

Caveat on the bible: worlds/saintjude/bible.md in the repo is the older codex adaptation (no Fixed/Open/Design/Weather tags, no ranges). The new "Saint Jude Bible Part I..VI" files in Downloads are not loaded by anything. Several NOs below are partly "the engine has not seen the new bible's structure yet".

## Package facts

- world.json (worlds/saintjude/world.json): calendar gregorian start 1975-01-01; seed_namespace saintjude_seed_v1; all 8 system switches false (cultivation, elixir, hollow, groundbinding, caerness_underworld, caerness_religions, caerness_trade, merchant_houses); mortality model "table" (US 1975-80 life tables); background.stage_distribution false; opening_family.marry_adults_on_day0 false; data files archetypes, manners, timeline, prices, taboos, names.
- Consumers of those data files in the engine: archetypes (engine/business.py:140), manners (engine/manners_canon.py:95), names (world_package.load_package name_groups). NOT consumed by any engine code: timeline.json (timeline_status is called only from tests/saintjude_package_test.py), prices_1975.json, taboos.json.
- Systems actually running for saintjude: simulation.disabled_process_keys gives {cultivation, groundbinding, hollow, religion, spectacle, tournament, underworld, underworld_medicine} (engine/simulation.py:513-527). Still registered and running: resolution, world, ecology, agriculture, logistics, merchant (aggregate trade is off via caerness_trade), craft, civilian, profession, service_fulfillment, growth, law, war, health, psychology, politics, conflict, organization_lifecycle, seeking, attention, patronage, education, information, memory. Process log after 30 days shows only civilian, memory, merchant, psychology doing anything.
- Opening built with tools/build_opening.py build_opening(db, package='saintjude') in 2.3 s. Contents: 130 actors (69 characters, 61 institutions), 54 locations, 90 institution_memberships, 1 household, 5 world_claims; 0 underworld_organizations, 0 enterprises, 0 polities, 0 law_jurisdictions, 0 rumours, 0 possessions/resources.
- advance_connection(conn, 30) on that opening: 1.23 s. 5 years (5 x 365 days): 3.1, 2.8, 3.7, 3.1, 3.5 s per year (about 16 s total), 17 events in total (6 deaths, 4 role_retainer_duty, 3 offers, 2 unions, 1 birth, 1 coming_of_age). These times are for a nearly inert world; they are not representative of a populated Saint Jude.
- Determinism: built the saintjude opening twice and advanced each 90 days; tools.build_opening.fingerprint of every table identical (rng_seed 812197 both). A single world_state.rng_seed drives hash/seeded draws (engine/simulation.py:76 _rng_for, and about 25 other call sites).

## Leaks found while testing (important for project 1)

1. Population is Caerness. background_population_sources in the saintjude opening holds 52,000,000 people in Caerness buckets (underheaven, dunmoor, greywood, stormhollow, sunreach, thornward, windmere, independent_frontier) plus "settlement:34" = Oakridge, 82,000. After 5 years the total is 56.57M (+8.8%, Caerness growth), Oakridge 89,204. Saint Jude (location 41) and every other place has no population source.
2. Because of (1), `author` cannot make people, businesses or organisations anywhere except Oakridge. Tested: author person at "Saint Jude" / "City Hall" with from_elsewhere true -> refused "the settlement's population cannot supply that person"; author business at a diner in the Pier 4 location -> "nobody lives there"; organisation -> "the leader must live there". At Oakridge a person is created but "County Prosecutor" becomes occupation "labor" (veto.categorise maps work text to the Caerness trade categories; with from_elsewhere it degraded to "hospitality" with a scaled_down note). Protagonist creation (engine/new_character.py) goes through the same pool_can_supply, so it is likely to have the same limit; I did not call it.
3. `lookup("prosecutor")` and role lookups only search actors.subtype, institution_memberships.role_text, enterprise_staff.role, underworld_personnel.role_kind (connector/views.py _role_hits). An authored person has no office, so role lookup returns nothing.

## Item table

Legend: YES / PARTIAL / NO. "Small" = small and clearly within the engine.

### 1. Truth tiers

**E-001 Fixed facts locked: NO** (Critical).
- Evidence: no tag field anywhere. Closest: source_identity_map.canon_status (values: None 61, CANONICAL_HISTORY 5, KNOWN_PARTIAL 1, "working" 148 in the saintjude opening; engine/current_seed.py:66 _map), world_claims.canon_status + claim_text (schema.sql:3311; seeded at current_seed.py:463, never read by act/author/veto: grep shows no reader), historical_anchors.immutable and canon_scope (schema.sql:815; written by continuity.py:113/crystallization/civilian/timeskip, never enforced anywhere). veto.py checks only named contradictions about people, places, kin, offices-by-name (veto.held_by_other), not claims.
- Test: act "Tell the room the Gannet Terminal opened in 1972" -> status applied, mapped_to plan, a commitment row (connector.acting._free -> free_operation). Nothing compares speech with world_claims. The act tool takes free text and cannot "change a Fixed fact" because it has no fact store, so the failure here is "no protection and no fact store", not a drifting write.
- Fix: (a) a `facts` table (key, text, tier Fixed/Open/Design/Example, start/end date, source) loaded from the package, plus (b) a veto in author/note/act that matches asserted subjects against Fixed facts and requires a cause_event_id/reason to retcon, plus (c) a lore-side lookup so the GM can see the tag. 3 files minimum (schema/db.py migration, a new engine/facts.py, hook in veto.py and connector/store.add_note), about 300-500 lines plus a bible-side tag parser. Free-text matching is the hard part: only subject-key matching is "small"; semantic detection of a contradicting assertion is not.
- Small and clearly within the engine: the store, the tag and a "retcon needs a cause" call are small. Detecting contradictions in free text is not engine work (that is the GM's job with lore); a reasonable cut is a `fact` tool/field the GM must use when it changes something.

**E-002 Open items filled once then held: PARTIAL** (High).
- Stored and returned: author person creates a real actor row (engine/authoring.py:_person), provenance row in connector authored_entities (connector/authoring.py), found by name via lookup (tested: lookup("Harold Weiss3") -> found, authored true). `note` kind=detail stores free text per subject (gm_notes) and is returned in scene/lookup (views.py:304, 504). `note` kind=rule/sheet/recap persist across chats (store.py:123).
- Missing: no key for "the County Prosecutor of Marsh County" as an Open slot; a second author with the same job text would create a second person (the veto only blocks duplicate names and leadership of existing bodies, veto.held_by_other). Role lookup finds nobody (leak 3). In Saint Jude author is also blocked by leak 2.
- Fix: office/slot table (see E-019) keyed by role+jurisdiction; author person gains `holds: slot_key`; veto refuses a second holder; lookup and lore return it. Plus the population fix for Saint Jude. Medium: about 200 lines plus schema, and the leak-2 fix (give Saint Jude real population sources; likely 1-2 files, partly package data).
- Small: the slot store is small and within the engine; the population fix is package + activation work, already project 1 territory.

**E-003 Example men replaceable: PARTIAL** (High).
- Seed people are actors with source_identity_map rows (source_key, canon_status "working"); engine/veto.canon_figure stops a protagonist taking a seed name. Nothing says "Example". Fixed facts do not exist (E-001), so nothing refers to Carmine Sabatini by name in a Fixed record except the 5 world_claims (claim_text names him: "In 1974 Carmine Sabatini quietly had his own brother-in-law..."), which are plain text and would still name him if the seed dropped him.
- Fix: author world_claims with actor-id subjects and render names at read time (world_claim_subjects exists, schema.sql:3324) or keep claims role-based. Mostly an authoring/data task; small in code.
- Small: yes, mostly seed data discipline.

**E-004 Belief apart from truth: YES for beliefs, PARTIAL for conventions** (High).
- Per-character belief store exists: information_claims, claim_evidence, actor_evidence_access, actor_beliefs, belief_revisions (schema.sql:4062-4133; engine/belief.py ensure_claim/recompute_actor_belief/actor_belief_envelope), plus rumours/rumour_locations/rumour_exposures/knowledge. author rumour (engine/authoring.py:_rumour) writes only rumours, rumour_locations and exposures. Test: authored "The PBA is owned by the Castellanos" -> rumour_id 1 created, no actor/institution rows changed.
- Conventions: taboos.json is data only; nothing consumes it; act never refuses a taboo act (test: "Kill Carlo Spatafore without sanction" was refused only because "he is not here"; the engine has no taboo check). So conventions are not walls, but the reactions come only from generic loyalty/grievance/harm machinery, not from the taboo table.
- Fix for the convention half: a small consumer of taboos.json in resolution of player operations (see E-022).

### 2. Design ranges

**E-005 Design draws once per run, held, logged: NO for Design figures, YES for run determinism** (Critical).
- There is no Design-figure concept (prices_1975.json and world.json hold no ranges and are not read by the engine). Determinism: single rng_seed in world_state; hash-derived draws; Caerness regression test tests/world_pkg_caerness_regression_test.py:38 proves two fresh builds are identical; I verified the same for saintjude (opening + 90 days, all tables identical). No existing test named restart_determinism; tests/arch02_scheduler_chunk_invariance_test.py covers chunked-vs-whole advance.
- Draws are not logged (no draw table). decisions/events/interactions are logged but not as "figure X drawn value V seed S".
- Fix: `design_figures` table (key, lo, default, hi, value, drawn_by, seed, day, cause) + `engine/design.py: figure(conn, key)` that draws once with hash(seed,key) and logs; then loaders read the package's `figures.json`. About 150 lines plus package data. Small, and within the engine.

**E-006 Derived figures recomputed: NO** (High). No figure model at all (no bank net = handle x margin anywhere). Fix: part of the same design.py (a `derived` expression evaluator or plain Python functions per package). Small if kept to a handful of named formulas; a general expression engine is not small.

**E-007 Sector draws share a factor: NO** (Medium). No sector revenue sampling. Fix: one shared per-year shock seeded from rng_seed, about 30 lines inside design.py once sectors exist. Small.

**E-008 Range bounds enforced: NO** (Medium). Only SQL CHECK constraints (e.g. 0-100 scales). Fix: clamp in design.set_figure, with a logged cause for exceptions; small, same file.

### 3. Weather

**E-009 No rule before its date: PARTIAL, mechanism exists but nobody calls it** (Critical).
- engine/world_package.py:178 timeline_status(pkg, name, date) returns not_yet/exists/available/common/unknown from worlds/saintjude/timeline.json (case/alias insensitive, tested in tests/saintjude_package_test.py:155-164). The only callers are tests. act (connector/acting.py), author (engine/authoring.py), veto.py, free_operation.py, lore.py never call it. Test: act "Ask a federal judge to hold a boss without bail as dangerous" in 1975 -> applied (a plan commitment, no refusal).
- Also timeline.json covers technologies and a handful of laws (25+ entries), not "procedural rules with numeric limits" (bail before 1984, Title III 30 days, 18-month contempt).
- Fix: (a) a dated-rules table/JSON ("rules.json": key, start, end, text, scope) generalising timeline.json; (b) call sites: a `period` check in veto.check_proposal/authoring (businesses, items) and in free_operation (text matching to technology/product names), plus a `lookup`/`lore` response that reports "not yet" so the GM can read it. A pure text-match on names is inexact; the sound cut is to make it a GM-facing tool/field (`lore` already exists; add timeline answers to `lookup`) and a veto only for named matches (the engine's own veto-not-menu rule). About 150-250 lines. Small and clearly within the engine for named-thing vetoes; keyword matching free text is borderline.

**E-010 Verified events fire, pressures can be deflected: PARTIAL** (High).
- `clocks` table (schema.sql:108): due_day, resolution_type, payload_json, status pending/resolved; simulation.py:_process_clock logs a dated event and marks resolved. Test: inserted clock 'Resorts International opens' (resolution_type verified_event) due day 100; advance 120 -> events row day 100 'clock:verified_event'. So scheduled dated events fire and are logged.
- Missing: no verified-vs-pressure typing, no strength or default-response, no way for a run to weaken one; the clock only logs an event, it changes nothing (no handler per resolution_type). The `pressures` table (schema.sql:74) is per actor intensity/threshold, not per scheme.
- Fix: loader for a package `events.json` creating clocks; `type: verified|pressure`; for pressures a small process that rolls strength with the run seed and logs the outcome; handlers for effects live in the bible (Claude narrates). About 150 lines. Small.

### 4. Money

**E-011 Pools balance: PARTIAL** (Critical).
- engine/ledger.py: transfer(src,dst,amount) checks the source balance, debits and credits equally (ledger.py:111-130) and records an economic flow (_record_economic_flow, underworld_rebuild.py:897); holders: person, business, outfit, household, institution, polity. So no account is credited without a debit, and transfers cannot overdraw (unless allow_partial). spend() destroys money by design (purpose goods/upkeep). _debit clamps at zero (MAX(0,...)).
- Missing: no pool concept, no "shares of a pool sum to at most 100%", no load-time check (E-026). Test requested ("sum every claim on numbers bank net; expect 2.0M not 2.42M") cannot run: there is no allocation table.
- Fix: `pools` (key, amount per period) and `pool_allocations` (pool, holder, share) with a validator and a monthly/weekly distributor that uses ledger.transfer; about 250 lines. Small; it is the bible's allocation table that is missing (the doc itself lists it as unrunnable, A-002).

**E-012 Kick-ups on net, weekly, up the Ladder: NO for Saint Jude** (High).
- A kick-up exists only inside the Caerness underworld model (switched off for saintjude): engine/underworld_rebuild.py:1723 kick_rate (one rate per outfit, from culture and boss greed), engine/payroll.py:50 crew_earnings = keep (1 - kick_rate) x racket gross_income_per_30, run per 30 days. So: gross not net, monthly not weekly, one flat rate not a tiered ladder, outfit-level not soldier -> capo -> underboss.
- No weekday scheduling anywhere (see E-025).
- Fix: a Saint Jude-specific `ladder` module: earners (actors) with costs, weekly job on Fridays from a package rate table, using ledger.transfer. About 300 lines plus data, and it needs the holder model of E-028 and a way to give earners income lines. Medium, not "small", but within the engine.

**E-013 Nominal sums decay with deflator: NO** (Medium). No inflation/deflator code (grep empty). prices_1975.json is data with year 1975, CPI ratios, not consumed. Standing payments (agreements, credit_agreements, obligations, household_service_terms) store no year. Fix: price-year column on standing payments and a `real_value(amount, from_year, to_year)` helper reading prices json; raises as clocks. About 80 lines. Small.

**E-014 The Pad is a cost, with limits: NO** (High). No Pad concept. Closest: law_offices.corruption_pressure/integrity (engine/law.py:33-62), underworld_enforcement_actions (Caerness, off). Nothing checks agency or case type (public killing, FBI, Strike Force). Fix: a protection arrangement table (payer, officer/precinct, commander_id, cost per week) and a veto/decision hook in the law process that ignores the arrangement when case type or agency is excluded; new commander resets it. 200-300 lines; depends on law data for Saint Jude (0 jurisdictions today). Medium; within the engine.

**E-015 Headcount follows revenue slowly: NO** (High). underworld_organizations.member_count_estimate and underworld_membership_profiles/flows exist (schema in db.py:1198, 1237) but are the Caerness model (off), no revenue coupling, and the Saint Jude families are 61 plain institution actors with membership rows (no headcounts). Fix: a Saint Jude "family" record with revenue and count range plus yearly attrition rule; needs E-005/E-011. 150-250 lines. Medium; within the engine.

### 5. Period Mind and content limits

**E-016 Generated text keeps the four limits: PARTIAL, prompt-only, partial** (Critical).
- The engine runs no language model and no output filter exists, so enforcement can only be prompt rules in the GM rulebook. Present in worlds/saintjude/rulebook_section.md: "no real person is in it" (line 5), "Engine measures never appear in prose", "Do not script the city. No pressure, secret ... fixed in advance" (so "no scripted plot and no named secret" is roughly there), Close third person (rulebook_core.md:11). Absent: any rule on drug/weapon/explosive methods (grep for drug/method/weapon/explosive in connector/*.md and worlds/saintjude/*.md finds only the taboo sentence and a taboos.json entry).
- Fix: add 3-4 lines to worlds/saintjude/rulebook_section.md (market-level narration only; no method). One file, a few lines. Small; this is the only possible kind of "check" since the engine does not read narration. Test still needs a human/Claude play-check.

**E-017 Real people never act on stage: PARTIAL** (High).
- The rulebook says no real person is in the city. No data flag "real" exists (grep in seed.json and engine: none). veto.canon_figure only stops a protagonist taking a seed name. author person accepted nothing real-specific (my attempt with "Anthony Provenzano" was refused for the population reason, not because he is real).
- Fix: a `real_persons.json` list in the package; veto.name check in author person and protagonist creation ("the name is a real person; use a stand-in"); about 40 lines. Small, within the engine (it is a named contradiction).

**E-018 Narration standards loaded: PARTIAL** (High). worlds/saintjude/rulebook_section.md and connector/rulebook_core.md are loaded into resume (connector/session.py:35 load_rulebook). There is no "Saint Jude Rulebook Narration Standards" file and no rule that the narrator does not moralize or judge by present standards (grep for judg/moral/anachron: none). Fix: add the narration-standards text to rulebook_section.md. One file, small.

### 6. Institutions with rules

**E-019 Offices with rules and terms: PARTIAL / mostly NO** (High).
- Data model pieces: institutional_roles (institution, role_key, capacity_slots, durable; db.py:3628), institutional_appointments (appointing_institution_actor_id, holder, started_day, ended_day, status; db.py:3396), law_offices (presiding_actor_id; db.py:2667), institution_memberships.role_text (what the seed uses). No term length, no election/appointment rule, no next-turnover date.
- Scheduling: nothing runs elections or reappointments (grep "election" finds none in engine/*.py). The only appointment writer is an attention-case path for a "state_remount_master" (engine/attention.py:127-150), Caerness-specific. Succession for polity heads exists for deaths (succession.py, organization_lifecycle), not terms. No fiscal-year events (grep fiscal finds only regional treasury entries).
- Fix: extend institutional_roles with appointing_authority, term_years, tenure_to_age, election_rule, next_turnover_day (migration + loader from package `offices.json`) and a process that on due day clears or reappoints the holder (leave "who" to the GM or a seeded draw), using clocks for the dated trigger. About 250-350 lines. Medium; clearly within the engine.

**E-020 Procedure follows law of the date: NO** (High). No procedural rules encoded anywhere (bail, Title III 30 days, contempt 18 months, union-office bar). Same fix as E-009: dated rules with numeric parameters, surfaced through lore/lookup and a veto for named violations. Small-to-medium; the numeric enforcement per case needs a law process for Saint Jude (law_jurisdictions is empty).

**E-021 Narcotics dial per family/drug: NO** (High). No "dial" in the code (grep). Fix: a 4x5 `dials` table with a cause log and a review trigger on succession (hook on leadership-transition events, there is leadership_transition_cases at db schema 4873). 100-150 lines plus data. Small once Saint Jude has families as records (see E-028).

**E-022 Taboos are prices, not walls: PARTIAL** (High). Not walls: no refusal exists (the act test above). But there is also no reaction draw: taboos.json is not read by any module. Reactions come only from generic mechanisms (loyalty/grievance, harm_incidents, rumours, conflict). Fix: a small module that when a player operation or sim event matches a taboo key logs the act and draws per-witness reactions (witnesses from event_witnesses table) inside the ranges in taboos.json. Needs a taboo-detection step: from `act` kind or GM-declared `taboo` field. 150-250 lines. Small to medium.

### 7. Geography

**E-023 Real towns blocked, jurisdictions follow the map: NO** (High).
- No blocklist (grep "blocklist/real town/Red Bank" in code: none), no jurisdiction map: law_jurisdictions is empty (activation only creates one per active polity; Saint Jude has 0 polities). Oakridge is a "city district" under Saint Jude (location 34), with nothing about being outside the SJPD. find_location returns None for a town the world lacks ("there is no place called 'Red Bank'" refusal came from author business), so author does refuse unknown places, but a blocklist is about narration and nothing reads narration.
- Fix: `gazetteer`/`blocklist` data in the package surfaced by lore/lookup (answer: "no such place; use X") and a veto in author place names; jurisdictions: loader creating law_jurisdictions with location_id and a `police_force`/`prosecutor` per place from the seed, plus the law/crime response routing (engine/law.py:process_due_law only handles civil-style cases between claimants; crime response routing is new). 100-200 lines for the data/veto; routing is project 2 work. Small for blocklist; medium for jurisdiction routing.

### 8. Time

**E-024 Run 1975 to entry date and keep the record: PARTIAL** (Critical).
- Run-forward exists: advance_connection(conn, days) (engine/simulation.py), tested 5 years in about 16 s (see package facts). History log: the `events` table (dated, typed, severities; e.g. life:death, life:union, role_retainer_duty), plus life_events, historical_anchors, political_history, process_execution_log. connector `advance` tool wraps it with a digest (connector/server.py:123).
- Missing: Weather application (E-009), Open outcomes drawn into a readable "history log" for Claude (events are generic; the 5-year saintjude run produced 17 events, nothing about elections, Pick-3, dials, police or families). Only the time-flow exists. The designed "per-story pre-history run + summary for Claude" is project 3 in the handoff.
- Also note leak 1 (Caerness growth of 52M background population during the run).
- Fix: after E-005, E-009, E-010, E-019, E-021: a `history_log` view/tool summarising events by year for the entry date. Medium; the sim content that creates something to log is project 2.

**E-025 Recurring cycles on the calendar, population series: PARTIAL / mostly NO** (Medium).
- Calendar: engine/world_calendar.py gives weekday/date for gregorian packages (tested: day 2 = Friday 3 January 1975; day 1826 = Tuesday 1 January 1980, leap-year correct). Nothing fires on weekday or date: no code uses weekday for scheduling (the weekday name appears only in formatting); processes use cadence_days (world_processes.cadence_days, schema.sql:520), monthly (30-day) payroll/finance, 90-day seasons. No feast calendar (religion.py explicitly says no universal feast calendar; caerness_religions is off), no fiscal year.
- Population: background_population_sources are Caerness numbers (leak 1); growth is Caerness-like (+8.8% over 5 years); engine/background_population.py mortality is a table in world.json (works for Saint Jude), but no time series with a fall rate, ranges, or cap on growth. Drug users as headcounts: not modelled.
- Fix: (a) weekly/annual/fiscal cycles: register cycles in package `cycles.json` (weekday or month-day) and a process that computes next_due_day from the calendar; small (80-120 lines). (b) population: package-level bucket definition for Saint Jude (population of the city, 1.04M or whatever the new bible says), per-year rate with range from the figure model (E-005), replacing the Caerness buckets in activation for this package; medium (leak 1 is the real blocker and is activation/package work).

### 9. Validation

**E-026 Validation suite on the bible: PARTIAL / mostly NO** (High).
- tests/saintjude_package_test.py (bible, sections, data) checks that the repo bible indexes (>= 60 chunks), has needed headings and certain strings, that timeline entries have sources and ordered ISO dates, that prices ratios agree. It is a test of the package, not a validator of the new bible format. engine/coverage.py validates opening coverage, not documents. The bible-hash firewall in current_seed.py checks the Caerness bible hash only.
- The five required checks do not exist (cross-refs, Design has range+default, Weather has no numeric outcome, one value per named figure, pools balance). They also need the bible to carry those tags in a parseable form (see E-001) which the repo bible does not.
- Fix: tools/validate_bible.py plus a tagged-figure parser; 200-400 lines; mostly a document-side tool (the doc's own author could host it). It is within the engine repo but is more build tooling than engine.

### 10. Added after Gemini review

**E-027 Dial binds family, not each man: NO** (High). No dial (E-021) and no per-person drug involvement. Generic decision runtime exists (engine/decision_runtime.py, temperament.py, motives.py) so a soldier deciding to deal could be a decision kind; today the decision kinds are Caerness-generic. Fix: new decision kind + boss response event; depends on E-021, E-028. Medium (project 2).

**E-028 Rackets have holders: PARTIAL** (High).
- Data model exists: economic_interests(holder_actor_id | holder_crew_id | holder_organization_id | holder_household_id, target_racket_id | target_enterprise_id, interest_kind legal_owner/beneficial_controller/operator/manager/tenant/revenue_share/creditor, share_fraction, started_day/ended_day, status) (db.py:1565). Interests end when a racket is suppressed/seized (underworld_rebuild.py:943-954) and are rewritten on organisation merges (underworld_rebuild.py:2431). payroll.crew_earnings uses the operator crew. underworld_racket_sites (db.py:1434) belongs to an organisation, with an optional enterprise.
- Missing for Saint Jude: the whole underworld model is switched off (caerness_underworld false), the saintjude opening has zero organizations, rackets or enterprises, and no code moves a title on a boss change.
- Fix: enable a Saint Jude flavour of the underworld model or build a lighter "family" record with rackets whose holder is an actor via economic_interests; change of boss does not move titles automatically (right per the bible: separate event). The table is reusable; the content and a handover event are new. 200-300 lines plus the family model. Medium; within the engine.

## What would unblock the most (my reading)

1. Fix the population/leak 1-2 problem first: Saint Jude opening has no population sources for its own places, so author (person/business/organisation) and probably protagonist creation fail in the city, and the 5-year run grows a 52M Caerness population. Without this, E-002, E-015, E-025 and E-027 cannot even be exercised.
2. Wire timeline_status and a generalised dated-rules file to lore/lookup and to named vetoes (E-009, E-020). The mechanism exists and is tested; nobody calls it.
3. Add a design-figure store (E-005/6/7/8) and a facts/tag store (E-001/2/3). These are small and shared by many items.
4. Use clocks for verified events and cycles (E-010, E-019, E-025): the dated scheduler exists.
5. Add the content-limit lines to the rulebook (E-016/17/18): prompt-only and cheap; the engine cannot enforce more.
6. Items needing a Saint Jude family/ladder/rackets/dial model (E-012, E-014, E-015, E-021, E-027, E-028) are project 2.
