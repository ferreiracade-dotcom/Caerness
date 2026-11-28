# L1: the 1 January 1975 Saint Jude opening carries lived history everywhere

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every area the C1 opening audit found blank (households and kin, ordinary businesses, debts/grudges/heat/incidents, careers and memories, the 1975 races, neighbourhood ties) starts with a lived past, from package data and existing generic engine code, with the opening build well under a minute.

**Architecture:** One new generic builder module per area under `engine/opening_*.py`, called from `engine/activation.py` after `build_outfits` and gated by the package (`opening_lived` block in `worlds/saintjude/world.json`, so Caerness is untouched). Each builder reuses what exists: `opening_family.resolve_opening_family` (households, kin), `places.make_place` + `civilian.create_enterprise` + `business.configure_enterprise_business` (businesses), `new_character._knowledge/_memories` patterns (made generic in `engine/lived_past.py`), `races.schedule` (races). All draws use `random.Random(f"{design.run_seed(conn)}:{stream}:{key}")`. Rates, densities and mixes are package data with a source or `"note": "unsourced"` and `"mark": "Design proposal"`; no world words in `engine/`.

**Tech Stack:** Python 3.13, SQLite, `tools/build_opening.py --package saintjude`.

**Spec:** the L1 brief (owner-approved, relayed 2026-11-23) and `docs/superpowers/reports/2026-11-19-saintjude-org-core-task-C1-creation-report.md` (the audit this round closes).

## Global Constraints

- No hard caps, floors, quotas or brakes to hit a number; a plausible outlier stands. Fix drivers, not outputs.
- No world words and no figures in `engine/`; they come from `worlds/saintjude/*.json`. `tests/no_world_words_test.py` must stay green.
- Canon wins: where `seed.json`/`bible.md` already names a marriage, child, business, debt or grudge, nothing contradicts it and nothing duplicates it.
- Determinism: same run seed gives the same opening. Insert-only; population totals unchanged (`population_delta` 0): people come from `background_person_profiles` via `person_ecology`, never `INSERT INTO actors` directly.
- Opening build time well under 60 s (11 s on the VM today); report the new time and DB size. Rebuild `data/saintjude.db` with `python tools/build_opening.py --package saintjude`; write no other `data/*.db`.
- Runs in tests: 30 days, or one year for seeds 3, 7 and 11; one long run at a time, never alongside the quick suite. Tests clean up their temp dirs and run `git restore game/campaign_01/model_requests/` after.
- Commit with "L1" in the subject, `git add <paths>` only; never push, stash, reset or switch branches. Do not edit R1's or J1's files. Leave `data/caerness.pre-schema110.db` and `game/campaign_01/backups/` alone.
- Protagonist-same-rules: everything seeded is ordinary world content any system can act on; nothing is player-only.

## Review Focus

- A seeded debt, grudge or payment whose two sides disagree (an `org_debts` row with no matching arrangement or seat; money that does not balance in the ledger) is an inconsistency, not colour. Test: money, seat and canon consistency on a one-year run for seeds 3, 7, 11.
- A person given a spouse who is also a canon figure with a recorded spouse or celibacy (priest, made man's canon wife): no duplicate union. Test in Task 1.
- A business whose owner or staff is an outfit seat holder who then has two employers' worth of time: businesses are held through `org_holdings` where the bible says so, otherwise owned by ordinary people. Test in Task 2.
- The 1975 mayoral race scheduled at day 0 must not already have decided or a winner; candidates filed before the opening only if consistent with `holders_1975`. Test in Task 5.
- Opening size and time blow-up (tens of thousands of knowledge rows). Test in Task 7 (the budget test).

## File Structure

- Create `engine/lived_past.py`: generic memory, knowledge and career seeding for an existing person (shared by `new_character` and the opening).
- Create `engine/opening_households.py`: wires `resolve_opening_family` for Saint Jude (the `marry_adults_on_day0` switch, no hearth), plus kin and neighbours.
- Create `engine/opening_businesses.py` + `worlds/saintjude/neighbourhood.json`: ordinary businesses by district.
- Create `engine/opening_past.py`: debts, grudges, obligations, standing payments, heat, incidents for outfits and people.
- Create `engine/opening_races.py`: the 1975 races and early filers.
- Create `engine/opening_ties.py`: street, parish, workplace ties.
- Modify `engine/activation.py` (one gated call block), `engine/opening_family.py` (replace `location_in_hearth` with a package-driven flag), `worlds/saintjude/world.json` (`opening_lived`).
- Tests: `tests/l1_households_test.py`, `l1_businesses_test.py`, `l1_past_test.py`, `l1_careers_memories_test.py`, `l1_races_test.py`, `l1_ties_test.py`, `l1_consistency_test.py` (one-year runs, seeds 3/7/11), `l1_budget_test.py`.

---

### Task 1: Households and kinship for everyone

**Files:** Modify `engine/opening_family.py:158-428` (hearth parameter), `worlds/saintjude/world.json` (`opening_family.marry_adults_on_day0` true; `opening_lived.households` rates source), `engine/activation.py` (call). Create `engine/opening_households.py`. Test `tests/l1_households_test.py`.

**Interfaces:**
- Consumes: `opening_family.resolve_opening_family(conn) -> dict`, `marriage_curve_for`, `package.name_groups`, `demographic_sex.family_home_groups`.
- Produces: `opening_households.build(conn) -> dict[str, int]` (counts: `households`, `unions`, `children_latent`, `parents_linked`) and every adult character has `marital_status_basis` set.

- [ ] **Step 1: Write the failing test** `test_every_adult_has_a_household_or_is_single_by_draw`: on a fresh Saint Jude opening, assert households >= 0.6 * characters aged 18+ with a seat or relationship; kin links > 1000; no active union between two people with the same `demographic_sex`; no person in two active unions; canon-recorded spouses (`source_identity_map` + `canon_record`) keep exactly their recorded union; married share by age band within a stated tolerance of `marriage_curve_for` (assert the curve's own shares, not hard numbers).
- [ ] **Step 2: Run it** (`PYTHONPATH=. python tests/l1_households_test.py`) and see it fail (1 household).
- [ ] **Step 3: Implement `build(conn)`**: set `opening_family.marry_adults_on_day0` true for the package; make `location_in_hearth` a package hook (`package.opening_family.settlement_groups`, default `False` when the package has no cultivation) so no cultivation import runs; call `resolve_opening_family`; then for each unmarried adult under 30 with living parents' latent group, link parents through `kinship_links` using the existing latent kin-group rows. Marriage rates by name group come from `worlds/saintjude/names.json` groups through `marriage_curve_for` tags; add `opening_lived.marriage_rate_by_group` (Design proposal, 1970 Census figures cited, else `"note": "unsourced"`).
- [ ] **Step 4: Run the test; expect PASS.**
- [ ] **Step 5: Commit** `L1: households and kinship at the opening`.

### Task 2: Ordinary businesses across the neighbourhoods

**Files:** Create `worlds/saintjude/neighbourhood.json`, `engine/opening_businesses.py`; modify `engine/activation.py`; test `tests/l1_businesses_test.py`.

**Interfaces:**
- Consumes: `places.make_place(conn, *, name, place_kind, location_id, owner_ref, day, enterprise_id=None) -> int`, `civilian.create_enterprise`, `business.configure_enterprise_business`, `merchant.add_enterprise_staff`, `authoring._archetype`.
- Produces: `opening_businesses.build(conn) -> dict[str, int]` (`enterprises`, `places`, `staff`); `neighbourhood.json` keys `district_profile` (per district: `households`, `mix` of archetype key -> establishments per 1000 people, `source`, `mark`).

- [ ] **Step 1: Failing test** `test_districts_hold_businesses_by_the_package_mix`: per district, enterprise count per 1000 residents within the package range for each archetype; every enterprise has an owner (a real actor with a household) and `enterprise_staff` rows; every one has a `place_details` row of a matching kind; no owner is an outfit boss/capo seat holder unless `org_holdings` names the enterprise; no enterprise name duplicates; total people unchanged.
- [ ] **Step 2: Run; fail (0 enterprises).**
- [ ] **Step 3: Implement.** Densities: ground in 1975 US city figures (County Business Patterns 1975: about one retail and service establishment per 65 to 80 residents; eating and drinking places about 1 per 400; food stores about 1 per 450; auto repair about 1 per 1,200 to 1,500; mark each `Design proposal`, source or `"note": "unsourced"`). Owners and staff drawn by `person_ecology.resolve_background_person(... allow_elsewhere=False)` in the district; names from the owner's name group; archetype keys from `archetypes.json` (add missing trades such as `grocery`, `tavern` only as package data).
- [ ] **Step 4: Pass. Step 5: Commit** `L1: ordinary businesses at the opening`.

### Task 3: A past for the outfits and people

**Files:** Create `engine/opening_past.py` (+ `opening_lived.past` data in `worlds/saintjude/outfits.json` or `neighbourhood.json`); test `tests/l1_past_test.py`.

**Interfaces:**
- Consumes: `org_debts`, `org_tension`, `org_heat`, `org_incidents`, `org_money`, `org_arrangements` schemas (engine/schema.sql 4982-5180), `orgs.seat_of`, the bible's named feuds (`outfits.json` `grudges`/`history` keys if present).
- Produces: `opening_past.build(conn) -> dict[str, int]` (`debts`, `grudges`, `incidents`, `heat`, `payments`).

- [ ] **Step 1: Failing test** `test_outfits_start_with_a_past_that_balances`: each outfit has heat rows and at least one past incident dated before day 0; every `org_debts` row names a creditor and debtor with seats and `paid <= amount`; every canon feud in the bible data has its `org_tension` and `org_incidents` row; no incident dated after day 0; ledger totals unchanged by seeding (past is history, not a transfer), and `org_money` rows have `day < 0`.
- [ ] **Step 2: Run; fail.** **Step 3: Implement** from package data: per-outfit rates (debts per member, grudge chance per seat pair with resentment above a package threshold already stored in `relationships`), incident kinds from the org core's own kind list; canon pairs first. **Step 4: Pass. Step 5: Commit** `L1: past for outfits and people`.

### Task 4: Careers and memories

**Files:** Create `engine/lived_past.py` (extract `_knowledge`, `_memories`, `_competence` from `engine/new_character.py` as generic functions; `new_character` imports them); modify `engine/new_character.py`; test `tests/l1_careers_memories_test.py`.

**Interfaces:**
- Produces: `lived_past.seed_person(conn, actor_id, *, key, day, depth: int) -> dict` (`memories`, `knowledge`, `careers`) and `lived_past.seed_opening(conn) -> dict[str, int]` (depth by tier: seat holders and officials 12-25 facts, ordinary background-linked people 3-6, with `career_tracks` rows from `occupation_domain` and years since the person's working-age start).

- [ ] **Step 1: Failing test** `test_seat_holders_have_work_history_and_memories`: every active seat holder has an `actor_careers` row whose start precedes day 0 by about his age minus the working-age start, at least 2 `actor_memories`, knowledge facts about his district and his org; `tests/new_character_test`/`c1_stated_family_test` still pass (the extraction changed no behaviour).
- [ ] **Step 2: Run; fail.** **Step 3: Implement** the extraction and the opening seeding; careers use `career_tracks`/`career_stages` rows made from `occupation_domain` (package data maps domain to a track name). **Step 4: Pass. Step 5: Commit** `L1: careers and memories`.

### Task 5: The 1975 races and their candidates

**Files:** Create `engine/opening_races.py`; modify `engine/activation.py`; test `tests/l1_races_test.py`.

**Interfaces:**
- Consumes: `races.schedule(conn, day) -> int`, `races.consider_filing(conn, actor, race_id, day) -> bool`, `races.pool_for`, `offices.next_dates`.
- Produces: `opening_races.build(conn) -> dict[str, int]` (`races`, `filed`).

- [ ] **Step 1: Failing test** `test_1975_races_exist_with_early_filers`: a race exists for every elected office with an election inside the opening window (the mayoral race of 1975 at minimum); stage is `filing`; every filed candidate meets the office's `eligibility`; the incumbent's party is not left without a candidate when the incumbent is eligible; no race is `decided`; one 30-day run does not break the civic tick (`process_due_civic` runs).
- [ ] **Step 2: Run; fail (0 races).** **Step 3: Implement** by calling `races.schedule(conn, 0)` then `consider_filing` for incumbents and pool members whose own driver says yes at day 0 (the run's real driver, not a separate roll). **Step 4: Pass. Step 5: Commit** `L1: the 1975 races`.

### Task 6: Neighbourhood ties

**Files:** Create `engine/opening_ties.py`; test `tests/l1_ties_test.py`.

**Interfaces:**
- Consumes: `social_contact_links` (`context_kind` in `institution`, `household`, `work`, `locality`), `household_members`, `enterprise_staff`, `institution_memberships`.
- Produces: `opening_ties.build(conn) -> dict[str, int]` (`street`, `parish`, `workplace`).

- [ ] **Step 1: Failing test** `test_people_are_tied_to_street_parish_and_workplace`: each household member has a `locality` contact with 3 to 12 neighbours in the district; each staffer a `work` contact with colleagues; each parish member a `institution` contact; no link between a person and himself; `actor_a_id < actor_b_id` held.
- [ ] **Step 2: Run; fail.** **Step 3: Implement** from households, staff and memberships already built in Tasks 1-2 (no new people). **Step 4: Pass. Step 5: Commit** `L1: neighbourhood ties`.

### Task 7: Wire it, rebuild the packaged opening, audit before/after, one-year consistency

**Files:** Modify `engine/activation.py` (gated call order: households, businesses, past, careers/memories, races, ties); create `tests/l1_consistency_test.py`, `tests/l1_budget_test.py`; rebuild `data/saintjude.db`; write `docs/superpowers/reports/2026-11-19-saintjude-org-core-task-L1-report.md`.

- [ ] **Step 1: Failing tests.** `l1_budget_test`: opening build under 60 s and the DB under a stated size; `l1_consistency_test` (env `L1_SEED` in 3/7/11): build the opening, advance 365 days once, and check money (ledger totals reconcile, no negative purse a drawn rate made), seats (every seat holder alive or replaced, no dual head), canon (named canon marriages, offices and feuds unchanged by seeding).
- [ ] **Step 2: Run, fail. Step 3: Wire and fix. Step 4: Run seeds 3, 7, 11 one after another (never in parallel, never with the quick suite); pass.**
- [ ] **Step 5: Rebuild** `python tools/build_opening.py --package saintjude`; re-run the audit counts (script in the report); commit `data/saintjude.db` and the report with `git add -f` only if ignored; commit `L1: wire, rebuild the opening, report`.

## Self-review
Spec coverage: households (T1), businesses (T2), outfit/people past (T3), careers and memories (T4), races (T5), ties (T6), build time/size, rebuild and before/after table (T7), one test per area plus money/seat/canon on seeds 3/7/11 (T7). The Review Focus items each name an owning task. Types: every `build(conn) -> dict[str, int]`; `lived_past.seed_person` and `seed_opening` are the only cross-task names.
