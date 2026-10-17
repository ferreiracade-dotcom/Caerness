# Connector `author` (gap 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the GM make invented people, businesses, organisations and rumours real engine entities, with the engine deciding plausibility and never granting money, troops, ownership or authority.

**Architecture:** New `engine/authoring.py` with one entry point `author(conn, me, kind, details, call_id)` that validates, then materialises through existing engine paths: people come from the settlement's background population (`person_ecology.resolve_background_person`, population-preserving, "always there"); businesses through `civilian.create_enterprise`; underworld outfits through `underworld.create_underworld_organization` + `underworld_rebuild.create_personnel`; civil bodies as institution actors; rumours as `rumours` rows with no truth event. A new MCP tool `author` wraps it with `store.run_once` like `note`/`act`.

**Tech Stack:** Python 3.13, SQLite, existing connector (FastMCP-style `server.py`), plain-script tests in `tests/` (`python tests/<name>.py`).

**Spec:** `docs/superpowers/specs/2026-10-16-claude-connector-design.md` §5 (`author` row; permissions table: "New persistent people, institutions, events, after validation" / never "Troops, money, ownership, victories, legal authority"), §7 (notes promoted through `author`), §11 area 14.

## Global Constraints

- Never write `data/caerness.db`; tests copy it to a temp dir (pattern: `tests/connector_continuity_test.py`).
- Every mutating call idempotent by `call_id` (`store.run_once`). All writes for one call in one SAVEPOINT; any refusal leaves no rows.
- Names follow sex (`person_ecology.FIRST_MALE` / `FIRST_FEMALE`); a given name from the opposite-sex pool is refused.
- No recognised same-sex unions. Protagonist is non-canon (irrelevant here, but authored people are never the protagonist).
- Engine numbers never reach prose: results speak in words (`ledger.scale_word` for means), ids only as ids.
- Authoring never: gives the protagonist or anyone he controls money, people, ownership, office or relationships beyond bare acquaintance; makes anyone his subordinate (that is `act hire`); sets a rumour's truth.
- Match surrounding style: compact code, short comments, plain-script tests with `run()` and asserts.

## Review Focus

1. Pulling an outsider silently: a person request in Toll's Reach must not come back living in another town unless `from_elsewhere` was set; when set, the person's `current_location_id` is the requested place and the result says where they came from.
2. Forged power through ties/owners: an authored business or outfit owned/led by the protagonist or one of his people (personnel, staff, service terms) is refused; `ties` cannot create trust, loyalty or membership in his outfit.
3. Rarity by population: a requested Stage/age/sex/work combination that the settlement's population cannot supply (after reservoir growth) is refused with a reason, not invented.
4. Retry and partial failure: same `call_id` twice creates one entity; a failure after the actor insert (e.g. a bad kin tie) rolls back the actor too.
5. Name collisions and noted names: a GM name already used by a living actor is refused; `from_notes` re-attaches only `general` notes, never notes on another actor.

---

### Task 1: People (`engine/authoring.py`, person kind)

**Files:**
- Create: `engine/authoring.py`
- Modify: `engine/person_ecology.py` (`find_background_candidate`, `resolve_background_person`: new kwarg `allow_elsewhere: bool = True`; when False skip the bucket broadening; also new kwarg `name: str | None = None` on `resolve_background_person` used instead of `_unique_actor_name` and written back to the profile's given/family name)
- Test: `tests/authoring_test.py`

**Interfaces:**
- Produces: `author(conn, me: int, kind: str, details: dict, call_id: str) -> dict` (kinds `person|business|organisation|rumour`; refusals raise `AuthoringRefused(reason)`, a `ValueError` subclass). Person result: `{"status":"created","kind":"person","actor_id","name","sex","age","work","location","from":<origin town or None>}`.

Person `details` (all optional except `sex`):
- `sex`: `male|female` (required).
- `age`: int 13–90 → search `min_age=age-3, max_age=age+3`.
- `work`: one of the occupation domains `artisan artist clerk criminal hospitality labor merchant physician soldier teacher transport`; unknown → refused listing them.
- `stage`: cultivation Stage (`First…Sixth`) → `required_stage`, `require_open_core=True`.
- `location_id`: default the protagonist's current location; must exist.
- `from_elsewhere`: bool, default False. False → `allow_elsewhere=False`; True → local first, then the bucket; an outsider is moved: `current_location_id` = requested place, `home_location_id` kept, result `from` = origin location name.
- `name`: full name "Given Family". Refuse if the given name is in the opposite sex's pool, or a living actor already has that exact name.
- `ties`: up to 4 of `{"actor_id": int, "as": "knows"|"sibling"|"parent"|"child"|"spouse"}`; the actor must be a living character. `knows` → `relationships.ensure_relationship` both ways, familiarity 10, nothing else. Kin via `household_life.add_kinship` (`sibling`/`sibling`, `parent`→ new person is parent: reciprocal `child`); parent must be 15–55 years older than child, else refused. `spouse` via `household_life.create_union` only if both adults, opposite sex, neither in an active union, `prohibited_union_kinship_reason` is None. Sibling/child of a man, or spouse (wife takes husband's family name) with no `name` given → family name copied (a given name still from the identity).
- `wants`: ≤ 200 chars → `goals` row (priority 50, active).
- `from_notes`: note ids; each must be a `gm_notes` row with `subject_kind='general'`; re-pointed to `('actor', new_id)`.
- Life: after resolution, `set_resolution(..., 'TRACKED', ...)` and `resolution_controller._sync_sim_tier(conn, aid, 'TRACKED', day)` so they have their own life; `subtype` = `authored_<work or 'person'>`; `actors.notes` = "Authored in play from a pre-existing identity."
- Never a protagonist relationship value other than familiarity; never membership anywhere.

- [ ] **Step 1: Write the failing tests** `run()` in `tests/authoring_test.py`, temp DB copy, protagonist = first located character (as in `connector_continuity_test.py`), with asserts:
  - a male labourer aged ~30 at the protagonist's place → `status=="created"`, actor sex male in `actor_life_profiles`, given name in `FIRST_MALE`, `current_location_id` == place, `background_person_profiles.status=='resolved'`, population sources unchanged (sum of `population_estimate` before == after), sim tier `STRATEGIC`.
  - `name="Mira Holt"` with `sex="male"` → `AuthoringRefused` mentioning the name; reusing an existing actor's name → refused.
  - an impossible local request (`stage="Sixth"`, `from_elsewhere=False`) → refused, no new actor rows.
  - `ties=[{"actor_id": <a living male>, "as":"sibling"}]` → two kinship rows, family name equals his.
  - `ties` with a parent only 5 years older → refused AND the actor count is unchanged (rollback).
  - `from_notes=[general note id]` re-points it; a note on an actor → refused.
- [ ] **Step 2: Run** `python tests/authoring_test.py` — Expected: FAIL (`ModuleNotFoundError: engine.authoring`).
- [ ] **Step 3: Implement** the person kind and the two `person_ecology` kwargs (existing callers unchanged by defaults).
- [ ] **Step 4: Run** `python tests/authoring_test.py` and `python tests/names_follow_sex_test.py` and `python tests/identity_reservoir_growth_test.py` — Expected: all pass.
- [ ] **Step 5: Commit** `feat: author people from the settlement's own population`.

### Task 2: Businesses, organisations, rumours

**Files:** Modify `engine/authoring.py`; Test: extend `tests/authoring_test.py` (`run_orgs()`).

**Interfaces:** results `{"status":"created","kind":"business","enterprise_id","name","means"}`, `{"status":"created","kind":"organisation","outfit_id"|"institution_actor_id","name"}`, `{"status":"created","kind":"rumour","rumour_id"}`.

Common: `location_id` defaults to the protagonist's place. "His people" = the protagonist, anyone in `underworld_personnel` of an outfit he leads or belongs to, staff of an enterprise he owns, service terms of his household (reuse `player_operations._is_my_person`-style checks or `ledger.can_draw` ownership tests). Settlement population = sum of `background_population_sources.population_estimate` for the location.

- **business** `{name, trade (≤80 chars), enterprise_kind: shop|workshop|service|other, owner_actor_id}`: owner a living character, not one of his people; name unique among active enterprises at the place; cap: active enterprises at the place `< max(3, population // 150)` else refused ("the town has no room for another…"). Means fixed by the engine: `capital=cash= {shop:2, workshop:3, service:2, other:1.5}` × (1.5 if population ≥ 5000 else 1) — scale units as used by `ledger`; owner in `enterprise_staff` as owner via `merchant.add_enterprise_staff(role="owner", authority=100)`. `means` returned as `ledger.scale_word`.
- **organisation** `{name, type, leader_actor_id}`: `type` in `gang|crew` → `underworld.create_underworld_organization(key=f"authored:{call_id}", organization_type=type, primary_location_id, member_count_estimate=4, violence_capacity=10, cohesion=50)` + leader via `underworld_rebuild.create_personnel(org, role_kind="boss", actor_id=leader)`; cap: active outfits at the place `< max(1, population // 2000)`. `type` in `guild|school|temple|club|company` → institution actor (`actor_type='institution'`, `subtype=type`, `current_location_id`) + `institution_memberships` head row for the leader; cap per type at the place `< max(1, population // 1000)`. Any other type (sect, great house, polity, kingdom, mafia_family, syndicate…) → refused "canon-scale bodies cannot be authored". Leader: living character, not one of his people, not already a boss/head elsewhere. No treasury is set.
- **rumour** `{text ≤300, heard_by: [actor ids present]}`: `rumours(created_day, origin_location_id, text, truth_event_id NULL, distortion .3, reach .15, status 'circulating')`, `rumour_locations` prevalence .3 fidelity .7, `information._schedule_from_location(...)` for spread, `information.expose_actor_to_rumour(..., force=True)` per hearer (each must be at the place). Never an event or a hidden truth.
- Every created entity also gets a row in a new connector table (Task 3) — authoring itself returns enough for that.

- [ ] **Step 1: Failing tests** `run_orgs()`: a business owned by a fresh authored person → `civilian_enterprises` row at the place, owner staff row, `means` is a word; owner = protagonist → refused; a gang led by an authored person → `underworld_organizations` row + boss personnel, `treasury` 0/NULL; type `sect` → refused; cap: authoring businesses until refused, then the count equals the cap; a rumour heard by a present actor → `rumours.truth_event_id IS NULL`, exposure row for the hearer; hearer elsewhere → refused.
- [ ] **Step 2: Run** `python tests/authoring_test.py` — Expected: FAIL on `run_orgs`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python tests/authoring_test.py` — Expected: pass.
- [ ] **Step 5: Commit** `feat: author businesses, outfits, local bodies and rumours`.

### Task 3: MCP tool, provenance, rulebook

**Files:** Modify `connector/server.py` (register `author`), `connector/schema.sql` (table `authored_entities(id, call_id, kind, entity_table, entity_id, world_day, created_at)`), `connector/views.py` (`lookup` of an authored actor/enterprise shows `"authored": true` — one key, no numbers), `connector/rulebook.md` + spec Appendix A (kept identical), `connector/session.py` `HOW_TO_PLAY` if it lists tools; Test: `tests/connector_author_test.py`, update `tests/connector_server_test.py` tool list.

**Interfaces:** `author(call_id: str, kind: str, details: dict) -> dict` MCP tool; docstring ≤ 3 lines naming the four kinds and "the engine decides whether it fits; refusals say why". Refusal → `{"status":"refused","kind","reason"}` (stored by `run_once` so a retry returns the same refusal).

Rulebook: replace the line "Propose lasting new people or institutions with `author` once it exists." with:
"- When someone new will matter (anyone the protagonist deals with, employs, threatens or will meet again), make them real with `author` before naming them, and use the name it returns. Describe what the scene needs: sex, rough age, work, from here or from elsewhere; the engine finds who that is. Businesses, outfits, local bodies and rumours go the same way. A refusal means the world has no such thing here: adapt the story. Passers-by stay prose or `note`."

- [ ] **Step 1: Failing test** `tests/connector_author_test.py`: through the connector function (not HTTP), author a person twice with the same `call_id` → one actor; a refusal is returned as `status=="refused"` with a reason and retried identically; `authored_entities` row exists; `lookup` of the new name shows `authored: True`; `scene()` or `act speak` with the new actor passes presence (present at the protagonist's place). Rulebook text equals spec Appendix A text (existing check, if any, still passes).
- [ ] **Step 2: Run** — Expected: FAIL (no `author`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python tests/connector_author_test.py`, `python tests/connector_server_test.py`, `python tests/connector_resume_test.py`, `python tests/connector_views_test.py`, `python tests/authoring_test.py` — Expected: all pass (resume budget ≤ 19000 still holds).
- [ ] **Step 5: Commit** `feat(connector): author tool with provenance and rulebook`.
