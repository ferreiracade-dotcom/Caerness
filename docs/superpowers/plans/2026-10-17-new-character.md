# Gap 5: New Character (veto model), Household Means and Staff, Open `author` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (a) The GM and player design the whole protagonist; the engine only vetoes contradictions, then materialises the proposal and fills what was left open with a plausible lived past. (b) Every household has quantified means and pays staff through 4b's payroll; wealthy ones have stewards, servants and retainers. (c) `author` moves to the same veto model.

**Architecture:** The engine is a veto, not a menu. New `engine/veto.py` holds the checks, each returning a named `Contradiction` (what clashes, with what) so the GM can adjust and resubmit. `engine/new_character.py` materialises a proposal through the existing paths (`authoring.materialise_person`, `opening_family`, `_tie_values`, `health._family_means`, `reputation.adjust`, `education._set_competence_floor`, `underworld_ecology` helpers). `engine/household_staff.py` quantifies households and staffs them. Creation is `author(kind="protagonist")` (no ninth tool): `accept=false` previews in a rolled-back SAVEPOINT, `accept=true` re-runs the same deterministic fill and commits. Ansel Fane keeps his outfit, businesses and household and gets a fresh lived past (Task 5b); nothing from earlier playtests is carried over.

**Tech Stack:** Python 3.13, SQLite, plain-script tests (`PYTHONPATH=<repo>;<repo>/tests`).

**Spec / sources:** connector spec §8a, §2 line 35, §11 item 2; culture canon notes §2.1-2.4 ([1436]-[1439], [1488]-[1491]); gap 4b plan; owner rulings.

**Depends on:** gap 4b (see "Assumed from 4b"). Migration number **114**.

## Global Constraints

- Veto, not menu: accept anything that contradicts nothing. No station ladder, no ceilings table, no closed list of works, roles, affiliations, means or body kinds. Free text in; the engine maps it internally to its nearest simulation category (fallback the commonest, `labor`) and never refuses because a word is unknown. The GM may pass an optional `category` hint.
- Refusals only for: (a) **canon rules** — protagonist never a canon figure (name or likeness matches `source_identity_map` or a canon actor); no same-sex unions; names follow sex; Stage plausibility (non-martial above Temper unheard of, Third rarely, unless a retired master of 45+; age vs Stage by the same canon caps `reveal_latent_adult_child` uses: under 25 at most Third, under 35 at most Breach); (b) **established facts** — a business, seat, office, headship or outfit leadership already held by someone else, a dead or nonexistent person named as kin, a nonexistent place or organisation where one is claimed to exist; (c) **world scale** — the population cannot supply the people (reservoir after `grow_identity_reservoir`), or holdings out of proportion to the place, measured from world data (Task 2), never fixed tables. Every refusal says which fact it contradicts.
- Joining an existing house, sect, company or outfit as an ordinary or cadet member is fine; claiming a canon seat or title someone holds is not.
- Sex: when the GM leaves it open for a power role, draw with P(male) 0.92 violent outfit, 0.85 trade/specialist, 0.70 vice, 0.85 unit leader (seeded); when specified, accept if the pool can supply it. Elsewhere sex follows the population.
- The engine fills the unspecified (family, origin kin, ties, knowledge, competence, memories, standing) plausibly for age and background; age is plausibility, not rules (a 12-year-old has parents, no spouse). Canon null means unknown: drawn once at creation, deterministic from (world seed, `draw`), basis in `actor_life_profiles.metadata_json`.
- Safety kept: the engine never grants money, troops, ownership or authority over existing entities; authoring never creates the protagonist's subordinates (that is `act hire`) or anything owned/led by him or his people. A protagonist may own what he proposes only if it is new and in proportion (Task 2).
- Same rules as every named person; population never inflates (background identities or latent kin revealed the opening way, `population_delta` 0); no duplicate kin; no existing person's rows rewritten. No engine numbers reach the GM (words, `ledger.scale_word`). Records carry `{"source":"new_character","not_canon":true}`.
- Revealed people are low-attention (`STRUCTURAL`/`DORMANT`, 365-day cadence). 30-day advance on the packaged world grows at most 5% from this plan (4b has its own 15%). Never write `data/caerness.db` except the final regeneration; tests on temp copies; `git add` specific files. Migration 114 idempotent. Resume budget 20500: creation text lives in `connector/creation.md`, returned only when no protagonist exists.

## Review Focus

1. Nothing is refused for being unlisted: odd works ("lamp-lighter"), roles ("cadet of House X"), affiliations, big-but-proportionate holdings all pass; each refusal cites a concrete clash and a resubmit succeeds once adjusted.
2. Preview and accept give the identical person for the same `draw`; a preview leaves no row (actors, reservoir growth, engine_meta, latent_entities).
3. World-scale checks use live data (a tiny village refuses a 25-man outfit and a large fortune; Toll's Reach accepts them) and cannot be bypassed by splitting holdings across calls.
4. Households: quantifying all of them does not dissolve any in a 365-day run except from real causes (head dies, income lost); canon households are not all poor or all rich (spread follows `_family_means`).
5. `author` conversion keeps every safety rule and every existing `authoring_test`/`connector_author_test` assertion that was about safety; only closed-list assertions change.
6. Refactors are behaviour-preserving, proven by a fingerprint recorded on HEAD first.

---

### Task 1: Extract shared parts (no behaviour change)

**Files:** `engine/authoring.py`, `engine/person_ecology.py`, `engine/opening_family.py`, `engine/manners_canon.py`, `tests/new_character_test.py::parity`.
- `authoring.materialise_person(conn, *, loc, sex, age, work_domain, stage, elsewhere, name, pick_seed, call_id) -> int` = the pick/resolve/relocate/TRACKED/presence block of `_person`.
- `find_background_candidate/resolve_background_person(..., pick_seed=None)`: with a seed choose seeded-weighted among the top 12 by score, else unchanged.
- `opening_family.resolve_family_for(conn, aid, *, key, day, constraints=None, force=False)` = loop body of `resolve_opening_family`; `constraints` (`marital`, `children_min/max`) by rejection sampling of the pure `draw_family_history` (<= 40 tries, else `Contradiction` "the world's marriage and mortality rates make this improbable").
- `manners_canon.culture_key(conn, place_id)`.
- [ ] Step 0 on HEAD: record a SHA of `household_unions`, `kinship_links`, `latent_entities`, marital metadata after `resolve_opening_family` on a packaged copy with markers cleared; commit the constant; refactor; reproduce. `authoring_test`, `opening_family_test`, `connector_author_test`, `manners_canon_test` green. Commit `refactor: shared person, family and culture helpers`.

### Task 2: The veto (`engine/veto.py`)

**Interfaces:** `class Contradiction(ValueError)` (message names the clash); `check_proposal(conn, proposal) -> None | raises`; `categorise(text, hint=None) -> str` (work text to the nearest `occupation_domain`; fallback `labor`; never raises); `place_scale(conn, location_id) -> dict` (live data: population, sum of enterprise capital+cash there, sum of household wealth there, total outfit member estimates, institution count).
- Checks (each its own function, each tested): `canon_figure` (name/likeness vs `source_identity_map` + existing actor names); `name_sex`; `same_sex_union`; `stage_plausible` (via `occupation_with_past` and the age caps above; retired master allowed at 45+); `held_by_other` (business owner, `institution_memberships` head, outfit leader, political office, zone controller); `kin_alive` (named kin must exist and be living, ages 15-55 apart parent/child, no prohibited kinship union); `place_exists`; `pool_can_supply` (via `find_background_candidate` dry run incl. growth); `holdings_in_proportion`.
- **Proportion checks from world data** (parameters in one dict, e.g. `PROPORTION = {"wealth_share": 0.05, "outfit_share": 0.15, "business_share": 0.10}`): total proposed wealth+capital <= 5% of the place's enterprise capital + household wealth (floor: what an ordinary modest household holds, so tiny places still allow a living); an outfit's members <= 15% of the place's existing underworld membership and the place must have a settlement-scale underworld (`seed_settlement_underworld` zone/population logic, no new table); businesses <= 10% of the place's enterprise count (floor 1); canon-scale seats (any `institution` actor with canon source, polity offices, Great House headship) are `held_by_other` by definition. Totals count the protagonist's earlier submissions.
- [ ] Tests `tests/veto_test.py`: each check passes a plausible case and refuses a clashing one with a message naming the clash; a lamp-lighter and a "cadet of House X" pass; a 25-man outfit refused in a village, accepted in Toll's Reach; a fortune larger than the town refused, a comfortable one accepted; unknown work text maps without error. Commit.

### Task 3: The lived past of one person (`engine/new_character.py` part 1)

**Interfaces:** `fill_lived_past(conn, aid, *, key, proposal) -> dict` (counts and a words digest). Each layer fills only what the proposal left open, insert-only, idempotent:
1. **Family:** `resolve_family_for` (spouse = latent person revealed as in the opening, children a latent group) unless the proposal names them. Up to 3 children named (youngest at home, eldest adult) via `reveal_latent_adult_child(min_age=0)`; minors get no Stage under 14, at most First under 18 (adult behaviour unchanged). Under 16: no union.
2. **Origin family:** pure `opening_family.draw_origin_family(key, *, age, sex, hearth, childhood_multiplier)` from the existing models (`natural_annual_hazard`, `_DESIRED_CHILDREN`, `_birth_interval_days`); living parents/siblings revealed (latent route, family name from father, names follow sex) at the home place with P 0.7, else kept as unnamed `origin_family` counts. A 12-year-old therefore has living parents with high probability.
3. **Ties:** 4-6 neighbours/acquaintances (background identities, age +-15, `_tie_values` branch `acquaintance`), colleagues from the affiliation (`colleague`), a mentor if staged/skilled (`teaching_relationships`, may be dead), subordinate/superior ties for an outfit he founded with its members (loyalty 35-65).
4. **Competence:** `education._set_competence_floor` for the categorised work, `min(85, round(25 + 1.6*min(years,25) + 0.3*(aptitude-50)))`, years = age minus start age (14 manual/hospitality, 16 clerical/trade, 18 martial/criminal).
5. **Knowledge:** 12-25 `knowledge` rows (`fact_key='lived:<kind>:<id>'`, `truth_event_id` NULL, negative `learned_day`, confidence 0.6-0.9) templated from rows he would know (districts and who holds them, outfits and bosses if criminal, businesses of his trade, institutions, kin and neighbours, the manners line) plus 3-5 `actor_memories` (`source_kind='admin'`) from real past facts.
6. **Standing:** `reputation.adjust` domains for the home place scaled by years there and what he holds.
- [ ] Tests `::lived_past`: spouse opposite sex, union before first child; no duplicate kin; every tie both ways; `started_day` within [max(births), 0]; names follow sex; `population_delta` 0 and totals unchanged; second call adds nothing; a 12-year-old has parents, no spouse; `marital: widowed` at 25 refused, at 55 succeeds; proposal-named kin are used, not duplicated. Commit.

### Task 4: Proposal to protagonist (`create_protagonist`)

**Interfaces:** `create_protagonist(conn, proposal: dict, call_id: str) -> dict`. `proposal` (all optional but `age`, `place`): `name, sex, age, place, work` (free text) `category?, stage?, family? {spouse?, children?, parents?, siblings? (each free description or named person)}, affiliation? {name or text, role text}, holdings? [{kind text, name, amount word or number}], ties? [{who, as}], from_elsewhere?, concept (verbatim), draw, accept`. Refused when a player exists. Result: `{status: "draft"|"created"|"refused", reason?, draw, summary{who, family, work, holdings, standing, people, past}, actor_id?}` in words.
- Flow: `check_proposal` -> `materialise_person(pick_seed)` -> household headed by him (money from `holdings`/default modest for his age and work via `_family_means` conventions, never above `place_scale` shares) -> affiliation: match an existing org/institution by name (join as ordinary member; a role that is a held seat is vetoed) or create a new small body through `author`'s organisation/business paths (4b outfit setup incl. heat, temperament, ground, relations) with him as owner/leader only when the proposal says so and it is new -> `fill_lived_past` -> `household_staff.ensure_household_staff` -> `set_player` -> seed `character_sheet` `history` and `standing`.
- Outfit sizing when the GM gives none: from the place's underworld scale and his age (drawn, not tabled); named underboss/crew leaders drawn through `underworld_ecology._person` with the power-sex skews.
- [ ] Tests `::proposal`: same `draw` gives the same person for preview and accept; preview leaves row counts/`engine_meta` unchanged; redraw differs; a Fane-like proposal (45, male, Third, Toll's Reach, boss of a new outfit, brothel + gambling + lending) is accepted and the outfit earns after 30 days (4b); sexless outfit-boss draws over 300 seeds: male share 0.88-0.96 / 0.80-0.90 / 0.64-0.76 by class, and an explicit female is accepted when the pool supplies one; refusals each cite their clash and a corrected resubmit passes (canon name, Third merchant at 25, headship held by another, dead father named alive, absurd fortune, same-sex spouse); weird free text passes; second create refused. Commit.

### Task 5: Households quantified, paid, staffed (`engine/household_staff.py`, migration 114)

**Interfaces:** `household_means(conn, hid) -> (means, tags)` (`health._family_means` over active members + head); `quantify_household(conn, hid)`; `household_income(conn, hid)`; `staff_plan`, `ensure_household_staff(conn, hid, *, key)`; `seed_all(conn)`.
- **Quantify** every household (replaces `NOT_SEPARATELY_QUANTIFIED`/`STRUCTURAL_ONLY`; metadata keeps `economic_basis: "family_means"` and the tags): `wealth = round(4 * (means/50)**3, 1)` x1.5 for lineage `great house`, x4 for `royal house`/`imperial dynasty`; `liquidity = max(1, round(0.4 * wealth, 1))`; `staff_capacity` follows Task staff total. Ansel-like 70 gives about 11.
- **Income** (so `_resolve_households` can run for all without dissolving them): monthly household income = earnings of working adult members, credited to liquidity as a wage-income flow, `earn = upkeep_per_member * (1.15 + (means-50)/100)` per working member plus owner draws from businesses (4b). Calibrate so a median household of each means band is net positive after upkeep and staff pay; insolvency only from real causes (no earner, head dead, business lost). 
- **Staff total** = `floor(0.3 * monthly_income / wage_base)` (4b's base), x culture factor (`culture_key`: dunmoor 1.3 retainers/grooms, thornward 1.2 guards, windmere +1 named clerk, hearth/churn prefer retainer families of the same institution), +-20% seeded; none when the total is below 1 (poor households do their own labour [1490]; `dependent_house_family` people are the retainers of their house and are used first). Named = `min(total, 3 + total // 6)`, the rest counted. Roles by total: steward (clerical/trade, 35+, 65% male [1489]), clerk, servants, nurse if children under 8, counted guards/grooms. Named staff are background identities of the household's place (`allow_elsewhere=False`), each with `add_service_term` (loyalty 45-70, satisfaction 45-65, renewal 40-70, review staggered), a `service` tie, `STRUCTURAL` tier. A missing pool is reported `unstaffed`, never invented.
- All staff are paid by 4b's household payroll; no wage exemption anywhere. A household that cannot afford its plan gets a smaller plan (never extra money).
- `_migration_114` (after 113): `seed_all`, report `schema114_report`, deterministic from the world seed, skips nothing but location-less households (reported). Regenerate `data/caerness.db` through the normal open path from the committed 113 file; `integrity_check`; no `-wal/-shm`.
- [ ] Tests `tests/household_staff_test.py`, `tests/schema114_test.py`: all 263 households quantified, wealth rises with means band, median net positive; 365-day run: no household dissolves without a real cause, no staff leaves for wage reasons, payroll rows exist; tier spread (great houses larger than house families, ordinary households none); named staff have terms, members rows, two-way ties, name-sex match; second run adds nothing; `population_delta` 0; 30-day advance <= +5%. Commit.

### Task 5b: Ansel gets a fresh lived past (repair)

**Files:** `tools/give_lived_past.py`, `tests/new_character_test.py::ansel`.
- Owner ruling: keep playing Ansel Fane with his outfit, businesses, household and staff; nothing established in earlier playtests (wife, children, parents, notes, recaps) has to carry over. Run Task 3's `give_lived_past` on the existing protagonist: it fills family, origin kin, ties (neighbours, colleagues, his outfit's people, his businesses' managers), knowledge, competence, memories and standing plausibly for a 45-year-old Third-stage underworld boss in Toll's Reach. Existing rows stay (insert-only); no constraints file, no owner review of playtest facts.
- Usage: `python tools/give_lived_past.py --campaign ansel [--apply]`; dry run on a copy prints a short digest; `--apply` takes a sqlite backup `<backups>/ansel.pre-livedpast-<ts>.db` + `integrity_check` first and refuses without it. On the server, run after deploying migration 114.
- [ ] Test `::ansel` (temp Fane-like fixture): after apply he has kin (parents dead or alive by age), >= 12 knowledge rows, ties to his underboss/accountant/steward with both directions, standing in Toll's Reach; his outfit, businesses, household and pre-existing rows unchanged (hash); second run adds nothing. Commit.

### Task 6: `author` becomes a veto (`engine/authoring.py`, `connector/authoring.py`)

Closed lists and caps removed, with their replacement:

| Removed in `engine/authoring.py` | Replaced by |
|---|---|
| `WORK` (11 domains) and `work must be one of` | free `work` text -> `veto.categorise`; unknown text never refuses |
| `STAGES` check | free text mapped to a Stage name or none; `veto.stage_plausible` (canon caps) |
| `TIES` (knows/sibling/parent/child/spouse) and `<= 4` ties | free relation text -> nearest kin/knows kind; checks stay data-driven (ages, union rules, living); no count cap beyond the 25-named-per-call guard |
| age `13..90` | any age the pool can supply and mortality allows (`pool_can_supply`) |
| `BUSINESS_KINDS` and fixed means (`2.0/3.0/2.0/1.5`, x1.5 over 5000) | free `trade`/kind text -> archetype (the `_BY_KIND`/`_BY_WORD` map becomes a scored keyword map with `labor`-style fallback `wholesaler`); capital/cash from the proposal's amount word, default modest for the owner's means, bounded by `holdings_in_proportion` |
| business cap `max(3, pop // 150)` | `holdings_in_proportion` against the place's enterprise count and demand |
| `OUTFIT_TYPES`, `BODY_TYPES` and `canon-scale bodies cannot be authored` | free `type` text -> nearest outfit/institution kind; a canon-scale body is vetoed as `held_by_other`/scale, not by a list |
| outfit cap `pop // 2000`, institution cap `pop // 1000` | `holdings_in_proportion` against the place's existing underworld/institution counts |
| `heard_by <= 12`, text lengths | kept as input hygiene only (not world rules) |

Kept unchanged: never grant money, troops, ownership or authority over existing entities; nothing owned or led by the protagonist or his people (`_not_his`); leaders must live there and not already lead; names unique; rumours carry no truth; savepoint all-or-nothing; `call_id` idempotency; people only from the settlement's own population unless `from_elsewhere`. Refusals return the clash. Connector tool description lists free-text fields.
- [ ] Tests: update `authoring_test` and `connector_author_test`: closed-list assertions replaced by "free text accepted and mapped" and "scale/contradiction refused with reason"; every safety assertion unchanged and green. Commit.

### Task 7: Connector and rulebook

**Files:** `connector/authoring.py` (route `kind="protagonist"` before the player check), `connector/server.py` (author docstring), `connector/session.py` (no player: `{"needs_character": true, "creation": <creation.md>, "rulebook": ...}` replaces `needs_setup`), `connector/creation.md` (new, <= 1800 chars), `connector/rulebook.md` + spec Appendix A (one bullet: propose whole people to `author`; refusals name a clash, adjust and resubmit), README, `tests/connector_character_test.py`, `tests/connector_resume_test.py`.
- `creation.md`: design the person with the owner (age, background, family, work, holdings, who they know) and propose all of it; the engine only vetoes contradictions and fills the gaps; preview with `accept=false`, retell in prose with no figures and no canon figures, "another" bumps `draw`, adjust and preview again, `accept=true` only on the owner's yes; then `note kind=sheet` for voice, temperament, appearance, habits, ambitions; open on an ordinary moment.
- [ ] Tests: no-player resume returns `needs_character`; preview/accept replay by `call_id`; refusal carries its reason; after accept, resume is normal shape <= 20500; scene shows "your steward". Commit.

### Task 8: Acceptance and playtest

- [ ] `tests/new_character_acceptance_test.py` (§8a): 10 varied proposals on separate copies (labourer, clerk, free-text trade owner, outfit boss, retired master, Temper cultivator, woman physician, soldier, cadet of an existing house, 12-year-old heir-to-nothing) -> population counts unchanged, no duplicate kin, pre-existing rows unchanged, past consistent from the other side, 365-day run on 3 without error and with ties/staff persisting, no same-sex unions, names follow sex.
- [ ] Timing (`tools/bench_sim.py`), full suite (`tools/run_suite.py`, then `git restore game/campaign_01/model_requests/`), status lines in README/AGENTS/handoff. Deploy; owner phone playtest on a new campaign: design a character with the GM, accept, play a scene at home with family and staff.

**Final test list:** veto_test, new_character_test, household_staff_test, schema114_test, connector_character_test, new_character_acceptance_test, authoring_test, connector_author_test, opening_family_test, family02_sex_resolution_test, names_follow_sex_test, occupation_follows_stage_test, standing_test, manners_canon_test, connector_resume_test, connector_views_test, connector_server_test, world_pushes_back_test, schema113_test, interactions_standing_test, any `*household*`/`*service*` tests.

**Assumed from 4b (check once it lands):**
1. `create_underworld_organization` makes the heat row and `monthly_net_estimate` exists (landed); `world_pressure.claim_ground_for_outfits` / `seed_baseline_relations` are global and idempotent; `temperament.ensure_temperament(conn, oid)` is what a new outfit needs, plus any other outfit-setup function 4b adds, which I call after `create_personnel`.
2. Household payroll pays every active `household_service_terms` row from household liquidity (head's purse fallback) via `ledger.transfer(flow_kind="wage")`, keeps arrears on the term, and does not skip quantified households; it exports a wage base and role weights (steward, servant, clerk, nurse, groom, guard). If it needs household income to be net positive it relies on Task 5's income step; if 4b adds its own household income, Task 5 uses that instead of duplicating it.
3. Its owner draw from businesses credits household liquidity (or purse); loyalty drift reads `relationships.loyalty` toward the head and service-term loyalty/satisfaction as seeded here (non-hostile values).
4. Migration 113 is final; 114 runs after it and touches none of its columns.

**Not in this plan:** per-person faith; household succession customs; currency/wage canon (gap 6); staffing households that become rich mid-run (only migration and creation paths; add a 30-day hook if play shows the need).

## Owner decisions

None.
