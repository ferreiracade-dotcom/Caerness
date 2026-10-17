# Underworld Everywhere (gap 4a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Aldergate-only procedural underworld with a canon-shaped underworld in every settlement, re-adopt the canon outfits at their canon places, give Toll's Reach its fighting rings, show the civil date and season in scenes, and migrate existing campaigns (Ansel's) onto it.

**Architecture:** A data module `engine/underworld_canon.py` holds what the World Bible says (outfits, per-settlement character, named districts, fighting). A new `engine/underworld_ecology.py` seeds each settlement deterministically from (1) canon character, (2) the place's own features (`location_commercial_context`, ports/quays, routes), (3) population, using the existing `underworld_rebuild` helpers (`create_zone`, `create_underworld_organization`, `create_personnel`, `create_crew`, `set_zone_controller`, `create_racket_site`, `create_front`) and `spectacle` markets. Opening activation calls it for every settlement instead of `seed_city_underworld` for Aldergate. Migration 110 applies the same to existing campaigns. Gap 4b (rivals reacting, pay and loyalty) is a separate later plan.

**Tech Stack:** Python 3.13, SQLite, plain-script tests (`PYTHONPATH=. python tests/<name>.py`).

**Spec / sources:** `docs/superpowers/notes/2026-10-17-underworld-canon.md` (canon extract with paragraph locators — the binding source for every canon fact here); `canon/world_bible_current.docx` Part Twenty-Two; owner rulings 2026-10-17 (below); `Caerness_UNDERWORLD_ECON01_CLARIFICATIONS_2026-09-17.md` §9 (nothing survives only because it was written; nothing is rejected only because it is old).

## Owner rulings (2026-10-17)

- Re-adopt Tallow Family (Aldergate), Greyhook Wharf Company (Toll's Reach), Saltwake Combine (Saltmere) as live outfits.
- Every settlement gets an underworld sized by canon character first, then the place's features, then population.
- Aldergate's ten invented gangs do not survive as such; Ansel's campaign is rebuilt onto the same canon version.
- Networks are not "parked" at Waymeet: place them as canon says, check each.
- Toll's Reach must have its fighting: the Red Yard, dockside rings, the Red Board warehouse ring.

## Global Constraints

- Never write `data/caerness.db` except by running the migration deliberately in the final task, after all tests pass on a temp copy; back it up first (`data/caerness.pre-schema110.db`).
- Deterministic: all draws seeded from `world_state.rng_seed` + location id (as `seed_city_underworld` does). Re-running seeding is idempotent (no duplicates).
- Population-preserving: named leaders/members only through `person_ecology.resolve_background_person` (location-scoped, `allow_elsewhere=False`), never invented adults; unnamed membership stays estimates.
- Canon leadership of Tallow, Greyhook, Red Board, Saltwake, Mallow, Reckoning is open: never name a canon leader in data; a leader may be resolved from the local population only when an outfit needs one (existing `ensure_organization_leader`).
- Canon structure (notes §1): no pyramid, no crime lord, no thieves' guild; durable outfits hold fronts and bottlenecks, not districts; street gangs are small, territorial, short-lived; violence controlled. Territory (zone claims) only for street gangs and protection.
- Every generated item carries `metadata.source` = `world_bible` (with the notes locator) or `procedural` (with the inputs that sized it). Nothing procedural is labelled canon.
- Names: outfit names unique world-wide; generated person names follow sex.
- Performance: 30-day `advance` on the migrated packaged DB ≤ 2× its time before the change (measure both on the dev machine; record in the ledger).
- Match surrounding style; short comments; plain-script tests.

## Review Focus

1. A settlement the canon says nothing about must still get a plausible small underworld (or none for tiny places), never a copy of Aldergate's 12 wards.
2. The migration on a campaign must not touch the protagonist's outfit, authored outfits, or any person's life; people who belonged to a dissolved procedural gang stay alive and in place, just unaffiliated.
3. A canon network spread across many places (Hush, Painted Veil, Red Board partners) must not become one territorial gang, and must not sit only at Waymeet.
4. The underworld daily/monthly process must run for every settlement's outfits without a performance cliff.
5. GM notes, recaps and standing rules in an existing campaign that name a dissolved gang are reported (listed by the migration result), not silently left contradicting the world.

---

### Task 1: Date and season in scenes

**Files:** Modify `connector/views.py` (compact scene), `connector/session.py` (resume scene) if separate; Test: `tests/connector_views_test.py`.

- Scene gains `"date": "14 Eighth Month, 624 SV"` and `"season": "Summer"` from `engine/civil_calendar.py` (`sv_date_from_day`; seasons: Spring months 1–3, Summer 4–6, Autumn 7–9, Winter 10–12 — canon "The calendar and dating convention"). Add `season_for_day(day)->str` and `format_sv_date(day)->str` to `civil_calendar.py` if absent.
- Rulebook (and spec Appendix A identically): one line — "The scene gives the date and season; you keep the time of day within the day and say it in the prose."
- [ ] Test first (day 0 → "1 First Month, 624 SV", "Spring"; day 100 → correct month/season), see it fail, implement, pass. Resume size test still ≤ 19000.
- [ ] Commit `feat(connector): scenes give the civil date and season`.

### Task 2: Canon data module

**Files:** Create `engine/underworld_canon.py`; Test: `tests/underworld_canon_test.py`.

Contents (plain dicts/tuples, each entry with `locator` = notes paragraph refs):
- `CANON_OUTFITS`: Tallow Family (Aldergate; `criminal_dynasty`; fronts warehousing, cheap lodging, wagon repair, animal yards, freight handling, small lending; activities cargo substitution, stolen goods, protection, high-risk debt, illegal gambling, warehouse-record manipulation; violence controlled), Greyhook Wharf Company (Toll's Reach; `criminal_enterprise`; fronts dock work, salvage, small boats, warehousing; smuggling through paperwork/port relations; not a pirate fleet), Saltwake Combine (Saltmere; `syndicate`, several principals; false manifests, customs evasion, insurance fraud, elixir redistribution). Each maps to the existing institution actor by name.
- `CANON_NETWORKS` (not territorial outfits; presence by place with a strength word): Painted Veil (Hearth cities; strongest Cairnholt Lantern District), The Hush (everywhere with docks/households: every settlement ≥ 20,000), Red Board (local partners: Cairnholt respectable hall, Toll's Reach warehouse ring, plus Waymeet and Aldergate books as already in `spectacle`), Cormorants (Toll's Reach, Saltmere, southern/maritime ports), The Reckoning (no known base: no presence rows; stays unplaced — canon says relationships obscured), Mallow Coven (secret cells: leave unplaced; out of scope).
- `SETTLEMENT_CHARACTER`: for every settlement in notes §3 — a multiplier on underworld density (`density`), street-gang weight (`street`), specialist kinds weighted (`fencing, smuggling, lending, gaming, prizefighting, vice, brokerage, labour_debt, horse_theft, fraud`), and named canon districts usable as zones. Values are working calibration (label `procedural_calibration_from_canon_character`); canon only fixes the character. Required anchors: Toll's Reach (high density, broad specialists, quays/warehouse districts/Red Yard, prizefighting high), Aldergate (density moderate, street low, fraud/lending/warehouse, caravan quarter + Exchange Quarter), Saltmere (highest density in canon: "largest and most international underworld outside the Hearth" is Windmere — Saltmere its hub), Cairnholt (street very low, brokerage/gaming high, Lantern District), Crownhold (brokerage/fraud), Waymeet (transient: gaming, vice, prizefighting; no durable outfit), Lysmere, Aldenmoor (fencing of manuscripts), Ravenfield (prizefighting high, horse theft), Stormhollow (labour debt, debt pits), Brackenfell. Regions (Dunmoor, Greywood, Sunreach, Thornward, North Coast, Spineward, Crownlands) give defaults for their settlements via `locations` ownership/parent chain.
- `FIGHTING`: Toll's Reach — Red Yard (legal permanent challenge ground, location exists), dockside rings (tolerated, rough), Red Board warehouse ring (illegal pit, coercive contracts possible); Ravenfield strong Closed-Core fighting; Saltmere prestige prizefighting; Waymeet open professional prizefighting; Aldergate high-stakes private clubs; Stormhollow debt pits; Thornward seasonal promoters.
- [ ] Test: every name in `CANON_OUTFITS`/`CANON_NETWORKS` exists as an institution actor in the packaged DB; every settlement key exists in `locations`; every entry has a locator. Fail, implement, pass. Commit `feat: World Bible underworld canon as data`.

### Task 3: Universal seeding

**Files:** Create `engine/underworld_ecology.py`; Modify `engine/underworld_rebuild.py` (`LEGACY_UNDERWORLD_QUARRY_NAMES` → empty; firewall keeps working for any future names), `engine/activation.py` (call `seed_all_settlements(conn)` instead of the Aldergate-only `seed_city_underworld`), `engine/spectacle.py` (prize markets/books from `FIGHTING` for every listed place, keeping existing keys); Test: `tests/underworld_ecology_test.py`.

**Interfaces:** `seed_settlement_underworld(conn, location_id) -> dict` and `seed_all_settlements(conn) -> dict` (idempotent; skip locations with population 0).

Sizing (per settlement, population P, character C, context X from `location_commercial_context` defaults if absent):
- `density = C.density * (1 + 0.004*(X.trade_flow-50) + 0.003*(X.traveler_flow-50) + 0.002*(X.event_activity-50))`, clamped 0.3–2.5; uncharacterised settlements use their region default, else 1.0.
- Zones: P < 15,000 → none (underworld exists only as specialists); else `clamp(round(P/20000), 2, 12)` zones, named from canon districts first (e.g. "River Quays", "Sea Quays", "Lantern District", "Caravan Quarter"), then generic kinds chosen by features (quay/warehouse only for ports or warehouse character; market, craft, residential, road gate, yards). Ring + a few cross adjacencies as today.
- Street gangs (territorial, `gang`, 8–30 members): `round(density * C.street * P / 60000)`, at most zones−1; each controls one zone, some zones stay open.
- Specialists (non-territorial `criminal_enterprise`/`network`, 3–15 members): `round(density * P / 30000)`, kinds drawn by `C` weights; each gets 1–2 racket sites of fitting kinds and maybe a front.
- Canon outfits: re-activated (`actors.status='active'`, location set), `underworld_organizations` row linked via `institution_actor_id`, fronts from canon via `create_front`, rackets from canon activities, membership estimate durable (30–80) — no zone control for durable outfits (Global Constraints).
- Networks: new table `underworld_network_presence(institution_actor_id, location_id, strength TEXT, source TEXT, PRIMARY KEY(institution_actor_id,location_id))`; institution actors of networks get `current_location_id=NULL` (no single seat) except where canon gives a seat. Move Seth Carrick only if canon gives his place; otherwise leave and record a ruling.
- Fighting: from `FIGHTING` → `prizefight_markets` (legality licensed/tolerated/illegal; `coercion_profile` 'voluntary' or 'coercive' for the Red Board warehouse ring and debt pits) + racket site `unlicensed bookmaking`/`illegal gaming` for the illegal ones; Red Yard as a legal `prize_hall`-kind market at The Red Yard location (or Toll's Reach with metadata `venue: The Red Yard` if markets need a settlement id).
- Leaders: each outfit's boss via `resolve_background_person(location_id=place, allow_elsewhere=False, occupation_domains=('criminal',), ...)`; if the place cannot supply one, the outfit is not created (log it in the result) — except canon outfits, whose leader stays open (no boss personnel; `named_leadership: open`).
- [ ] Tests (temp copy, run activation path on a fresh campaign build the way existing activation tests do, or call `seed_all_settlements` after retiring the old procedural orgs):
  - Toll's Reach: Greyhook active outfit with fronts; Cormorants presence; Red Board partner; prize markets include the Red Yard (legal), a dockside ring (tolerated), a warehouse ring (illegal, coercive); zones include River Quays and Sea Quays; ≥ 2 street gangs; ≥ 4 specialists.
  - Aldergate: Tallow active, no zone control by Tallow; street gangs ≤ 3; fraud/lending/warehouse rackets present.
  - Saltmere: Saltwake active. Cairnholt: 0–1 street gangs, Painted Veil presence "strong", Lantern District zone.
  - A settlement absent from canon with P ≈ 80,000 gets 3–5 zones and a few outfits; a settlement with P < 15,000 gets no zones.
  - No network institution actor has `current_location_id` = Waymeet unless canon says so.
  - Population sources sum unchanged; outfit names unique; running `seed_all_settlements` twice adds nothing.
  - 60-day advance raises nothing and at least one outfit outside Aldergate records an underworld operation/finance row.
- [ ] Commit `feat: canon-shaped underworld in every settlement`.

### Task 4: Every outfit can hold ground

**Files:** Modify `engine/authoring.py` (authored `gang`/`crew`: claim one vacant zone in its settlement if any, else become a challenger in the weakest-held zone via `add_zone_challenger`), `engine/underworld_rebuild.py` process path if it is city-restricted (check `process_due_rebuild_underworld` and helpers for Aldergate/city filters; remove them); Test: extend `tests/authoring_test.py`, `tests/underworld_ecology_test.py`.
- [ ] Tests: an authored gang in Toll's Reach holds or challenges a zone; the monthly underworld process touches outfits in at least three different settlements over 60 days. Commit `feat: outfits anywhere hold and contest ground`.

### Task 5: Migration 110 and campaign rebuild

**Files:** Modify `engine/db.py` (`_migration_110`, `SCHEMA_VERSION = 110`); Test: `tests/schema110_underworld_test.py`.

`_migration_110`:
1. Procedural orgs (`metadata_json` has `not_world_bible_canon` and `v060_clean_rebuild`): status `destroyed`, metadata `superseded_by: schema110_canon_underworld`; their crews/claims/rackets/protection accounts/fronts' links ended (status values the tables allow); personnel ended (`status` not active) — the people stay alive, in place, with `actors.subtype` reset from `underworld_*` to `resolved_criminal` (or their previous non-underworld subtype if recorded).
2. Their zones in Aldergate are retired; `seed_all_settlements` then builds the canon version everywhere.
3. Leaves untouched: any org whose leader/boss/founder is the protagonist or in `player_state`, any org with `metadata.authored`, any org not procedural.
4. Returns/records (engine_meta key `schema110_report`) the dissolved org names, so the connector can surface notes that mention them: if the connector tables exist (`gm_notes`, `campaign_recaps`, `standing_rules`), insert one `error_reports` row per note/recap/rule whose text contains a dissolved name: "World rebuilt (schema 110): <name> no longer exists; revise this note."
- [ ] Tests: on a temp copy with a fake protagonist-led outfit and an authored gang, after migration: procedural orgs destroyed, their former personnel alive and located, protagonist/authored outfits unchanged, canon outfits active, error_reports created for a planted note mentioning "Iron Rooks"; idempotent on second run; `init_db()` on a fresh copy reaches schema 110.
- [ ] Run the full named list below; then back up and migrate `data/caerness.db` (`python -c "from engine.db import init_db; init_db()"` with the default path), confirm schema 110.
- [ ] Commit `feat: schema 110 rebuilds the underworld from canon everywhere` (include the migrated `data/caerness.db` only if the repo tracks it — check `git ls-files data/caerness.db`).

**Final test list:** underworld_canon_test, underworld_ecology_test, schema110_underworld_test, authoring_test, connector_author_test, connector_views_test, connector_resume_test, connector_server_test, player_operations_test, names_follow_sex_test, identity_reservoir_growth_test, plus every existing test whose name contains `underworld`, `spectacle` or `v060` (`ls tests | grep -E 'underworld|spectacle|v060'`).
