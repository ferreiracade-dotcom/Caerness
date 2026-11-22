# Business BZ1: the shared layer (drivers, ventures, places, agreement terms) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the generic business layer that every sphere stands on. A business's numbers say where they came from. Ventures have a backer, money, parties, stages and a named outcome. Places have condition, owners, rent and upkeep. Agreements carry terms that fall due and a breach path. Caerness's business vocabulary moves out of the engine into package data, and Caerness's behaviour does not change.

**Architecture:**
- **No widened CHECKs.** New engine modules sit beside `engine/business.py` and keep their state in side tables keyed on the existing `civilian_projects`, `buildings` and `agreements`/`org_arrangements` rows. The CHECK constraints on those tables are not widened. **[my call]** This keeps Caerness's row hashes untouched and avoids table rebuilds; package words live in the side tables.
- **Package data only.** World words live in a new `business` data file per package. The engine names no world.
- **Holders and the intake.** Money moves only through `engine/ledger.py` holders. Every thing BZ1 makes is reported to the history design's intake (`held_things`) once that exists (Task 8).

**Tech Stack:** Python 3.13 and SQLite, through the repo's own test scripts (`PYTHONPATH=. python tests/<name>_test.py`, or `tools/run_suite.py`).

**Specs:**
- `docs/superpowers/specs/2026-11-22-saintjude-business-design.md`, §5 (approved). This plan implements §5.1 to §5.4 and the Caerness move from §6.2.
- `docs/superpowers/specs/2026-11-22-real-history-and-engine-gaps-design.md`, §5.1 to §5.4 (approved), the intake BZ1 plugs into.
- The parent spec, `2026-11-19-saintjude-three-spheres-design.md` §5.2a and §5.2b.

## Global Constraints

- **Branch.** Work on `feat/world-packages-saintjude` at current HEAD. The B line (B15b, then B16) is landing on the same branch.
  - Rebase nothing.
  - Never stash, reset, switch branches or push.
  - Commit only the files your task names (`git add <paths>`).
- **Python path.** Use `/c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe`. Bare `python3` hangs.
- **Databases.**
  - Never write `data/*.db`. Tests use the scratch DB that `engine.db.database_path()` picks under tests.
  - Leave `data/caerness.pre-schema110.db` and `game/campaign_01/backups/` alone.
  - Tests rewrite `game/campaign_01/model_requests/*.md`. Restore them with `git restore game/campaign_01/model_requests/` before committing.
- **Schema number.** Take the next free number on HEAD when Task 2 starts. It is 122 today, but B15b, B16 or the intake core may take 123 or later. Re-read `SCHEMA_VERSION` in `engine/db.py` right before committing Task 2 and renumber if someone landed first.
- **No hard caps.** No `min(..., ceiling)` on growth, counts or money. Score clamps that already exist in the 0–100 columns stay. New quantities (dollars, days, counts) have no top.
- **Engine vetoes, never menus.** No function returns a list of options for the GM to pick from.
- **No world words in `engine/`.** Every new module is added to `tests/no_world_words_test.py`'s scanned files. Package words (trade names, venture kinds, place kinds, breach words) come only from the package's `business` data.
- **Caerness stays behaviour-identical.** `tests/world_pkg_caerness_regression_test.py` must pass.
  - The fixture `tests/fixtures/caerness_opening_fingerprint.json` may be regenerated only in Task 2, and only for the new empty tables and the migration rows. Task 2 says how to prove that.
  - Caerness gets no `business` data file, so every new tick is a no-op there.
- **The protagonist under the same rules.** Nothing in BZ1 checks "is this the player". Places, ventures and terms behave the same whoever owns them.
- **Long runs.** At most two five-year runs at once on this PC. Run them in the background.
- **Cost.** A five-year Saint Jude run sits at about 9 of its 10-minute budget, and its DB grows about 24–25 MB a year against a 15 MB target. BZ1 must add no per-day work when it has nothing to do, and no per-tick history rows: driver readings keep the latest reading per subject only.

## Review Focus

1. **A backer who runs out of money mid-venture.**
   - Expect: the stage stalls and is late with the reason "backer short of money"; the venture fails only when the stall runs past the kind's `stall_days`.
   - Never: money below zero, or a crash. Test in Task 6.
2. **An owner or party who dies, or an org that dissolves, while a term or a place is live.**
   - Expect: the term's debtor or creditor is resolved through the existing inheritance path, or the term ends as `orphaned` with that reason. A place keeps its condition and passes to its legal owner if one is set.
   - Never: an exception from `_check_exists`. Test in Tasks 4 and 5.
3. **A long time-skip (365+ days) over many due terms.**
   - Expect: each due date between the two days is settled in order, so missed counts and breaches match a day-by-day run.
   - Never: one lump settlement. Test in Task 5: a run in 30-day steps and a single 360-day step give the same `missed_count` and the same breach rows.
4. **A package `business` file with an unknown key or word.** For example, a venture kind whose stage names an approval kind the file does not declare.
   - Expect: a load-time error naming the file, the key and the word.
   - Never: a silent default. Test in Task 2.
5. **Seeded reproducibility.** Two runs from the same seed give identical driver readings, venture outcomes and breach rows. Test in Task 6: two scratch DBs, same seed, compare rows.

---

## File structure

| File | Responsibility |
|---|---|
| `worlds/caerness/archetypes.json` (new) | Caerness's business archetypes, copied byte-for-byte in meaning from `engine/business.py::_ARCHETYPES` |
| `engine/business.py` (modify) | `_ARCHETYPES` removed; `archetypes(conn)` reads the package's file, with Caerness's file as the default |
| `engine/authoring.py` (modify, ~line 405–420) | `_archetype()` reads `business.archetypes(conn)`, not the Caerness constant |
| `engine/schema.sql`, `engine/db.py` (modify) | BZ1's side tables and one migration entry |
| `engine/business_data.py` (new) | Loads and validates the package's `business` data file |
| `worlds/saintjude/business.json` (new), `worlds/saintjude/world.json` (modify) | Saint Jude's drivers, shocks, venture kinds, place kinds and breach words |
| `engine/business_drivers.py` (new) | The shared drivers, each with its value and source |
| `engine/places.py` (new) | Places: owner, legal owner, landlord, rent, upkeep, condition and the monthly tick |
| `engine/agreement_terms.py` (new) | Terms that fall due, payment through the ledger, missed payments and breach paths |
| `engine/ventures.py` (new) | Ventures: stages, spending, parties, approvals, the weighed outcome and the payoff |
| `engine/civilian.py` (modify, ~lines 565–615) | Calls the new ticks and their due days, and keeps the Caerness project resolver off venture rows |
| `engine/intake_business.py` (new, Task 8) | Registers BZ1's things with the intake |
| `tests/bz1_*_test.py` (new) | One test file per task |

---

### Task 1: Caerness archetypes become package data

**Files:**
- Create: `worlds/caerness/archetypes.json`
- Modify: `worlds/caerness/world.json` (`"data": {"archetypes": "archetypes.json"}`), `engine/business.py:11-100,136-171`, `engine/authoring.py` (`_archetype`, around line 405–420)
- Test: `tests/bz1_archetypes_test.py`

**Interfaces:**
- Produces:
  - `business.archetypes(conn) -> dict[str, dict]`. It always reads a file: the campaign package's `archetypes`, or `worlds/caerness/archetypes.json` when there is no package or no file.
  - `business.CAERNESS_ARCHETYPES_PATH: Path`.
  - The `catalog is not _ARCHETYPES` test in `seed_business_archetypes` becomes `package_has_own_archetypes(conn) -> bool`.

- [ ] **Step 0: Baseline.** Record the HEAD hash, `SCHEMA_VERSION`, and `tools/run_suite.py --quick --out runs/bz1_base` TOTAL in the task report. Start one five-year seed in the background (`python tests/saintjude_mob_fires_test.py` with `B15_SEED=3`) and record its wall time. That is the BZ1 cost baseline.
- [ ] **Step 1: Write the failing tests.**
  - `test_caerness_archetypes_file_matches_old_constant`: load `worlds/caerness/archetypes.json` and compare it with a frozen copy of the old `_ARCHETYPES`. Before editing, dump the constant to `tests/fixtures/bz1_caerness_archetypes_frozen.json` with `json.dumps(..., sort_keys=True)`. Assert equal dicts.
  - `test_no_archetype_constant_in_engine`: `not hasattr(engine.business, "_ARCHETYPES")`.
  - `test_saintjude_author_bar_uses_package_archetype`: on a Saint Jude scratch campaign, `author(kind="business", details={"name": "Test Bar", "trade": "bar", "amount": "modest", ...})` makes an enterprise whose `enterprise_business_profiles` row points at the `bar` archetype. Today `authoring._archetype` indexes the Caerness constant.
- [ ] **Step 2: Run them and see them fail.** Run `PYTHONPATH=. python tests/bz1_archetypes_test.py`. Expect the first test to fail with a missing file, the second to fail because `_ARCHETYPES` is still present, and the third to fail with a KeyError or the wrong archetype.
- [ ] **Step 3: Implement.**
  - Write the JSON file from the frozen dump.
  - Delete `_ARCHETYPES`.
  - Route `archetypes(conn)` and `_archetype(...)` through the package file.
- [ ] **Step 4: Run the tests.**
  - Run `bz1_archetypes_test` and expect PASS.
  - Run `world_pkg_caerness_regression_test` and expect PASS with an **unchanged** fixture.
  - Run `business_ecology_reconstructed_test`, `seek01_enterprise_projection_test` and `no_world_words_test` and expect PASS.
- [ ] **Step 5: Commit.** Add `worlds/caerness/archetypes.json`, `worlds/caerness/world.json`, `engine/business.py`, `engine/authoring.py`, `tests/bz1_archetypes_test.py` and `tests/fixtures/bz1_caerness_archetypes_frozen.json`. Message: `feat(business): BZ1.1 Caerness archetypes move to package data`.

### Task 2: Side tables, the migration and the package `business` file

**Files:**
- Modify: `engine/schema.sql` (append), `engine/db.py` (`SCHEMA_VERSION`, `_MIGRATIONS` entry with `None` function, like 118–122), `worlds/saintjude/world.json` (`"business": "business.json"`)
- Create: `engine/business_data.py`, `worlds/saintjude/business.json`
- Test: `tests/bz1_schema_data_test.py`

**Tables** (append to `schema.sql`; all `CREATE TABLE IF NOT EXISTS`). Holder refs are ledger strings: `person:<id>`, `business:<id>`, `institution:<id>` and so on.

```sql
driver_readings(subject_kind TEXT NOT NULL, subject_id INTEGER NOT NULL, day INTEGER NOT NULL,
                factors_json TEXT NOT NULL, total REAL NOT NULL, PRIMARY KEY(subject_kind, subject_id))
venture_details(project_id INTEGER PRIMARY KEY REFERENCES civilian_projects(id) ON DELETE CASCADE,
                venture_kind TEXT NOT NULL, backer_ref TEXT NOT NULL, budget_usd REAL NOT NULL DEFAULT 0,
                spent_usd REAL NOT NULL DEFAULT 0, stage_key TEXT NOT NULL, stage_started_day INTEGER NOT NULL,
                stage_due_day INTEGER NOT NULL, stalled_days INTEGER NOT NULL DEFAULT 0,
                outcome TEXT, outcome_reason TEXT, payoff_json TEXT NOT NULL DEFAULT '{}', next_due_day INTEGER NOT NULL)
venture_parties(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL REFERENCES civilian_projects(id) ON DELETE CASCADE,
                role TEXT NOT NULL, party_ref TEXT NOT NULL, term_id INTEGER)
venture_approvals(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL REFERENCES civilian_projects(id) ON DELETE CASCADE,
                approval_kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','granted','refused','not_needed')), decided_day INTEGER, decided_by_actor_id INTEGER, reason TEXT)
place_details(building_id INTEGER PRIMARY KEY REFERENCES buildings(id) ON DELETE CASCADE,
                place_kind TEXT NOT NULL, owner_ref TEXT NOT NULL, legal_owner_ref TEXT, landlord_ref TEXT,
                rent_usd_30 REAL NOT NULL DEFAULT 0, upkeep_usd_30 REAL NOT NULL DEFAULT 0, enterprise_id INTEGER,
                rent_term_id INTEGER, next_due_day INTEGER NOT NULL)
agreement_terms(id INTEGER PRIMARY KEY AUTOINCREMENT, ref_kind TEXT NOT NULL, ref_id INTEGER,
                debtor_ref TEXT NOT NULL, creditor_ref TEXT NOT NULL, amount_usd REAL NOT NULL CHECK (amount_usd >= 0),
                every_days INTEGER, next_due_day INTEGER NOT NULL, grace_days INTEGER NOT NULL DEFAULT 0,
                breach_word TEXT NOT NULL, purpose TEXT NOT NULL, missed_count INTEGER NOT NULL DEFAULT 0,
                owed_usd REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','ended','breached','orphaned')), created_day INTEGER NOT NULL)
agreement_breaches(id INTEGER PRIMARY KEY AUTOINCREMENT, term_id INTEGER NOT NULL REFERENCES agreement_terms(id),
                day INTEGER NOT NULL, path TEXT NOT NULL, owed_usd REAL NOT NULL, effect_json TEXT NOT NULL DEFAULT '{}')
```

Add an index on `next_due_day` for `agreement_terms`, `place_details` and `venture_details`.

**`business.json` shape** (Saint Jude values; Caerness has none). Each block carries a `basis` and an `assumption` flag, as `archetypes.json` does.
- `seasonality`: `{sector: [12 monthly multipliers]}`. Fill `hospitality`, `retail`, `construction` and `logistics` from bible Part IV §3.8. Anything else defaults to 1.0. The default is recorded in the reading's source as "no seasonality given".
- `shocks`: a list of `{name, from: ISO, to: ISO|null, sectors: {sector: multiplier}, source}`. Include the 1975 recession tail, the 1979–82 rate squeeze, and Regulation Q's end for banks (`from` 1980-03-31, *verify*). Dates are read with `world_calendar.day_for_date`.
- `approval_kinds`: a list of words, for example `liquor_licence`, `building_permit`, `zoning_variance` and `occupancy`. These are what politics will decide later.
- `venture_kinds`: `{kind: {stages: [{key, days, cost_share, approvals: [kind…], driver_sector}], stall_days, payoff: {"kind": "money"|"place"|"terms"|"none", ...}}}`. Saint Jude gets `open_business`, `build_or_refit` and `bid_contract`.
  - `bid_contract` has a single `bid` stage and payoff `none`. BZ3 and politics P1 make it real; for now it only proves stages and approvals.
- `place_kinds`: `{kind: {building_kind, upkeep_usd_30, decay_per_30_unpaid, base_capacity}}`. `building_kind` must be one of the existing CHECK words. Saint Jude gets `storefront`, `bar_room`, `warehouse`, `tenement`, `office_floor`, `garage` and `lot`.
- `breach_words`: `{word: path}`, with paths from the fixed engine set `tension | debt | grudge | claim`. Saint Jude: `sue → claim`, `street → debt`, `grudge → grudge`, `walk_out → grudge`, `between_orgs → tension`.

**Interfaces:**
- Produces:
  - `business_data.load(conn) -> dict | None`: `None` when the package has no `business` file. It is memoised through `world_package.pass_memo`.
  - `business_data.BusinessDataError(ValueError)`.
  - `business_data.venture_kind(conn, kind: str) -> dict`, which raises `BusinessDataError` naming the kind.
  - `business_data.place_kind(conn, kind: str) -> dict`.
  - `business_data.breach_path(conn, word: str) -> str`.

- [ ] **Step 1: Write the failing tests.**
  - `test_tables_exist_fresh_and_migrated`: a fresh `init_db()` has all seven tables. A DB built at the previous schema and then migrated has them too. Use the pattern in `tests/org_migration_test.py`.
  - `test_saintjude_business_file_loads`: `load(conn)["venture_kinds"]["open_business"]["stages"][0]["key"]` exists, and `breach_path(conn, "street") == "debt"`.
  - `test_unknown_word_is_named` (Review Focus 4): write a temp package copy whose stage names `approvals: ["no_such"]`. Assert that `BusinessDataError` is raised and that its message contains `business.json`, `open_business` and `no_such`. The same holds for a place kind whose `building_kind` is not a CHECK word, and for a breach path outside the four.
  - `test_caerness_has_no_business_data`: `load(caerness_conn) is None`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** the tables, the migration entry, `business_data.py` and `business.json`.
- [ ] **Step 4: Run the tests and the Caerness fixture.**
  - Run `bz1_schema_data_test` and expect PASS.
  - Run `world_pkg_caerness_regression_test`. It will FAIL on the fingerprint.
  - Regenerate with `python tools/build_opening.py --write-fixture`, then `git diff tests/fixtures/caerness_opening_fingerprint.json`. The **only** changed entries may be the seven new tables, `schema_migrations` and `engine_meta`. Paste that list into the task report. Any other changed table is a bug: stop and fix it.
  - Run `org_migration_test` and `no_world_words_test` and expect PASS.
- [ ] **Step 5: Commit.** Add `engine/schema.sql`, `engine/db.py`, `engine/business_data.py`, `worlds/saintjude/business.json`, `worlds/saintjude/world.json`, `tests/bz1_schema_data_test.py`, `tests/fixtures/caerness_opening_fingerprint.json` and `tests/no_world_words_test.py` (with `business_data.py` added to the scan). Message: `feat(business): BZ1.2 side tables and business package data (schema N)`.

### Task 3: The shared drivers

**Files:**
- Create: `engine/business_drivers.py`
- Test: `tests/bz1_drivers_test.py`

**Interfaces:**
- Consumes: `business_data.load`, `business._demand_score`, `business.commercial_context`, `world_calendar._date`.
- Produces:
  - `@dataclass Factor(value: float, source: str)`.
  - `reading(conn, subject_kind: str, subject_id: int, day: int, *, sector: str, location_id: int | None, quality: float = 50.0, condition: float = 100.0, capacity_used: float | None = None, demand_weights: dict[str, float] | None = None) -> dict[str, Factor]`. Keys, always present: `calendar`, `shock`, `demand`, `form`, `condition`, `capacity`, `rivals`, `roll`.
  - `total(factors: dict[str, Factor]) -> float`: the product of the multipliers. There is no clamp.
  - `record(conn, subject_kind, subject_id, day, factors) -> None`: UPSERT into `driver_readings`, one row per subject.
  - `why(conn, subject_kind, subject_id) -> list[str]`: lines in the form `"<factor>: <value> (<source>)"`.

**The factors** (each a multiplier around 1.0, and each `source` names its origin in words):
- **calendar**: `seasonality[sector][month-1]` for the day's date.
- **shock**: the product over shocks active on the date that list the sector. Its source lists the shock names.
- **demand**: `_demand_score(weights, commercial_context(conn, location_id)) / 50`.
- **form**: `0.5 + quality/100`.
- **condition**: `0.6 + 0.4*condition/100`.
- **capacity**: `1.0` unless `capacity_used` is given. Then it is `min(1.0, 1/capacity_used)` when over capacity, because demand beyond capacity is not served. That `min` is the physical limit of seats, not a cap on the world.
- **rivals**: `1/(1 + 0.15*n)`, where `n` counts active enterprises with the same archetype sector at the same `location_id`, excluding the subject. Its source names up to three of them.
- **roll**: `0.9 + 0.2*u`, where `u` is drawn from `random.Random(f"{seed}:{subject_kind}:{subject_id}:{day}")`. `seed` is the campaign's seed, as `org_tension._rng` reads it.

- [ ] **Step 1: Write the failing tests.**
  - `test_every_factor_has_a_source`: on a Saint Jude scratch campaign, read a bar at a seeded place. All eight keys are present, each `source` is non-empty, and `total == product`.
  - `test_shock_dates_bite`: a `construction` reading on 1975-03-01 differs from one on 1977-03-01 by the shock multiplier, and its source names the shock.
  - `test_rivals_named`: two more bars at the same place make `rivals.value == 1/1.3`, and the source contains both names.
  - `test_record_keeps_latest_only`: `record` called on days 10 and 40 leaves one row, at day 40.
  - `test_roll_is_seeded`: the same inputs on two scratch DBs with the same seed give an identical `roll.value`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `bz1_drivers_test` and `no_world_words_test` (add the module to the scan). Expect PASS.
- [ ] **Step 5: Commit** the module, the test and the scan edit. Message: `feat(business): BZ1.3 shared drivers with their sources`.

### Task 4: Places

**Files:**
- Create: `engine/places.py`
- Test: `tests/bz1_places_test.py`

**Interfaces:**
- Consumes:
  - `business_data.place_kind`.
  - `ledger.parse_holder`, `ledger.spend`, `ledger.balance`.
  - `agreement_terms.add_term` (Task 5), only when `landlord_ref` is set. **Build Task 5 first if you prefer. Tasks 4 and 5 may be swapped; neither needs the other's tick.**
- Produces:
  - `make_place(conn, *, name: str, place_kind: str, location_id: int, owner_ref: str, day: int, legal_owner_ref: str | None = None, landlord_ref: str | None = None, rent_usd_30: float = 0.0, condition: float = 100.0, prestige: float = 50.0, enterprise_id: int | None = None) -> int`. It returns the `buildings.id`, writes the `buildings` row with the kind's `building_kind` and the `place_details` row, and makes a rent term when there is a landlord.
  - `place(conn, building_id) -> dict`: the joined view, including `who_pays_upkeep` and `legal_owner_ref or owner_ref`.
  - `damage_place(conn, building_id: int, amount: float, cause: str, day: int) -> float`: lowers condition and returns the new value. At 0 the `buildings.status` becomes `'destroyed'`.
  - `transfer_place(conn, building_id: int, new_owner_ref: str, day: int, *, legal: bool = True) -> None`.
  - `next_places_due_day(conn, after_day: int, end_day: int) -> int | None`.
  - `process_due_places(conn, day: int) -> dict`. For each place due: the upkeep for the elapsed whole periods is spent from the owner (`ledger.spend`, `allow_partial=True`). Any shortfall lowers condition by `decay_per_30_unpaid` × the unpaid share. Status follows condition: `strained` below 40, `derelict` below 15. These are labels, not limits. `next_due_day` moves on by 30.
  - When the owner holder no longer exists (Review Focus 2), the payer becomes `legal_owner_ref`, else the place keeps decaying unpaid with the reason "no owner".

- [ ] **Step 1: Write the failing tests.**
  - `test_make_place_writes_both_rows`.
  - `test_upkeep_paid_from_owner`: an owner with $1,000 and upkeep of $200 has $800 after one due tick, and condition is unchanged.
  - `test_unpaid_upkeep_decays_and_labels`: with an owner at $0, condition falls each period, and status passes through `strained` to `derelict`.
  - `test_straw_owner_pays_when_owner_gone`: delete the owner actor's purse holder. The legal owner pays and no exception is raised.
  - `test_damage_to_destroyed`.
  - `test_long_skip_settles_each_period`: a 360-day step and twelve 30-day steps leave equal condition and equal owner balance.
  - `test_no_business_data_noop`: on Caerness, `process_due_places` returns an empty dict and writes nothing.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `bz1_places_test` and `no_world_words_test` (with the scan edit). Expect PASS.
- [ ] **Step 5: Commit.** Message: `feat(business): BZ1.4 places with owners, straws, landlords, upkeep and condition`.

### Task 5: Agreement terms and breach paths

**Files:**
- Create: `engine/agreement_terms.py`
- Test: `tests/bz1_terms_test.py`

**Interfaces:**
- Consumes:
  - `ledger.parse_holder`, `ledger.transfer` (`flow_kind="agreement_term"`, `allow_partial=True`) and `ledger.balance`;
  - `business_data.breach_path`;
  - `org_tension.add(conn, a, b, kind, delta, day, note=...)`;
  - `org_dealings.owe(conn, creditor, debtor, amount, origin, day)`;
  - `relationships.adjust_relationship(conn, src, tgt, day, resentment_delta=..., trust_delta=...)`.
- Produces:
  - `add_term(conn, *, ref_kind: str, ref_id: int | None, debtor_ref: str, creditor_ref: str, amount_usd: float, first_due_day: int, every_days: int | None, grace_days: int, breach_word: str, purpose: str, day: int) -> int`. `every_days=None` is a one-time payment.
  - `end_term(conn, term_id: int, day: int, reason: str) -> None`.
  - `next_terms_due_day(conn, after_day, end_day) -> int | None`.
  - `process_due_terms(conn, day: int) -> dict`. For each due date up to `day`, **in date order**:
    - transfer `amount_usd` plus any `owed_usd`;
    - a shortfall adds to `owed_usd` and increments `missed_count`;
    - when the oldest unpaid date is more than `grace_days` old, call `breach(...)` once and set the status to `breached`.
  - `breach(conn, term_id: int, day: int) -> int`, which returns the `agreement_breaches.id`. The path comes from `breach_path(word)`:
    - `tension`: both refs map to orgs (a person ref maps to the org whose purse role they hold, through `org_money`'s convention). Call `org_tension.add(creditor_org, debtor_org, "breach", delta=owed/1000, ...)`. The scale is **[my call]**; record it in `effect_json`.
    - `debt`: `org_dealings.owe(...)` when both are orgs. Otherwise `adjust_relationship(creditor→debtor, resentment_delta=+15, trust_delta=-15)` plus an `effect_json` that says "street debt between persons: no org" **[my call]**.
    - `grudge`: `adjust_relationship` as in `debt`, both ways at half strength for the debtor.
    - `claim`: no reader exists yet, because civil law is not built (history design §6 row 10). Write the breach row with `effect_json={"unread": "civil claim"}` and, once the intake exists, bump `depth_gaps` (Task 8).
  - A term whose holder no longer exists becomes `orphaned`, with that reason (Review Focus 2).

- [ ] **Step 1: Write the failing tests.**
  - `test_recurring_term_pays`: weekly $50 from A to B for four weeks moves $200.
  - `test_shortfall_accrues_then_breaches`: with A at $0 and `grace_days=14`, the term is breached on the first tick past day 14, with exactly one breach row, and `owed_usd` equals the missed sum.
  - `test_breach_paths`: one case per path. The tension level rises, an `org_debts` row appears, the relationship's resentment rises, and the claim row has `"unread"`.
  - `test_skip_equals_steps` (Review Focus 3): twelve 30-day steps and one 360-day step give identical `missed_count`, `owed_usd` and breach rows.
  - `test_orphaned_when_party_gone`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `bz1_terms_test` and `no_world_words_test`. Expect PASS.
- [ ] **Step 5: Commit.** Message: `feat(business): BZ1.5 agreement terms that fall due, and breach paths`.

### Task 6: Ventures

**Files:**
- Create: `engine/ventures.py`
- Modify: `engine/civilian.py` (the `projects = ...` query around line 600): add `AND id NOT IN (SELECT project_id FROM venture_details)`, so the Caerness resolver never touches a venture.
- Test: `tests/bz1_ventures_test.py`

**Interfaces:**
- Consumes: `business_data.venture_kind`, `business_drivers.reading/total/record`, `ledger.spend`, `places.make_place`, `agreement_terms.add_term`, and `civilian_projects` (`project_kind='business'`).
- Produces:
  - `start_venture(conn, *, kind: str, title: str, backer_ref: str, location_id: int | None, budget_usd: float, day: int, parties: list[dict] | None = None, payoff: dict | None = None) -> int`.
    - It writes `civilian_projects` (`project_kind='business'`, status `'active'`) plus `venture_details` at the first stage, `venture_parties`, and one `venture_approvals` row per approval the stage names, with status `'pending'`.
    - A `parties` entry is `{"role": str, "ref": str, "term": {add_term kwargs}|None}`.
    - The return value is the project id.
  - `decide_approval(conn, approval_id: int, status: str, day: int, *, by_actor_id: int | None, reason: str) -> None`. This is the hook politics will call. Until politics P1, nothing calls it, and **pending approvals do not block** **[my call]**. A stage with pending approvals proceeds, and the venture's `why` says "approval X pending: politics not built". A `refused` approval fails the venture with that reason.
  - `next_ventures_due_day(conn, after_day, end_day) -> int | None`.
  - `process_due_ventures(conn, day) -> dict`. For each due venture:
    - spend this period's share of the stage cost from the backer;
    - a shortfall adds a stall day and pushes the due date, and the reason is "backer short of money";
    - when the stage time is done, weigh it: `t = total(reading(...))` for the stage's `driver_sector`;
    - `t >= 0.85` completes the stage, `0.6 <= t < 0.85` makes it late by `round(days*(1-t))` with the weakest factor named, and `t < 0.6` fails it on a seeded roll against `t/0.6`, naming the weakest factor. These thresholds are **[my call]**; they are reported, never tuned to hit a target;
    - `stalled_days > stall_days` fails the venture with "backer short of money";
    - after the last stage, apply the payoff and set `outcome='completed'`.
  - **Payoffs:**
    - `money` calls `ledger.receive` to the backer;
    - `place` calls `places.make_place(**payoff["place"])`;
    - `terms` calls `add_term` for each entry;
    - `none` does nothing.
  - `venture(conn, project_id) -> dict`: stage, spent, parties, approvals, outcome, and `why` taken from `business_drivers.why`.

- [ ] **Step 1: Write the failing tests.**
  - `test_open_business_completes_with_place`: a backer with enough money, good drivers and enough ticks ends with outcome `completed`, a `place_details` row, and spending equal to the budget, within $1.
  - `test_backer_runs_dry_stalls_then_fails` (Review Focus 1): no money is ever negative, `stalled_days` grows, and the outcome is `failed` with the reason "backer short of money".
  - `test_bad_drivers_fail_with_named_factor`: force `commercial_context` demand to 0. The outcome reason names `demand`.
  - `test_pending_approval_does_not_block_but_is_said`.
  - `test_refused_approval_fails`.
  - `test_caerness_resolver_skips_ventures`: a venture row is never touched by `_resolve_project`. Its `progress` stays 0 and its `last_resolved_day` stays unchanged.
  - `test_seed_reproducible` (Review Focus 5): two scratch DBs with the same seed and the same calls give identical `venture_details` rows and `agreement_breaches` rows.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `bz1_ventures_test`, `no_world_words_test` and `world_pkg_caerness_regression_test`. Expect PASS.
- [ ] **Step 5: Commit.** Message: `feat(business): BZ1.6 ventures with stages, backers, parties, approvals and weighed outcomes`.

### Task 7: Run on the clock; drivers on existing businesses; the GM can ask why

**Files:**
- Modify:
  - `engine/civilian.py` `next_civilian_due_day` (around line 568): add the three `next_*_due_day` functions.
  - the `engine/civilian.py` function that calls `process_due_businesses` (around line 610): call `process_due_terms`, then `process_due_places`, then `process_due_ventures`. Terms go first, so rent paid this day is seen by the place.
  - `engine/business.py` `resolve_business_cycle`: when `business_data.load(conn)` is not `None`, multiply the computed revenue by `total(reading(...))`, call `record(...)`, and put `why` into the cycle result. When it is `None`, Caerness code runs unchanged.
  - `engine/business.py` `business_profile`: add `"why": business_drivers.why(conn, "enterprise", id)`.
- Test: `tests/bz1_clock_test.py`

**Interfaces:**
- Consumes: Tasks 3–6 as named there.

- [ ] **Step 1: Write the failing tests.**
  - `test_advance_runs_terms_places_ventures`: on a Saint Jude scratch campaign, through the normal advance, make one place with a landlord, one venture and one weekly term. Advance 90 days and assert that rent moved, upkeep was taken and the venture moved through its stages.
  - `test_idle_layer_adds_no_wakeups`: with no BZ1 rows, `next_civilian_due_day` returns the same value as on a DB without the BZ1 tables queried. Patch the three `next_*` functions to return `None`, then compare.
  - `test_existing_bar_has_why`: an authored Saint Jude bar, after one business cycle, has a `business_profile(...)["why"]` with eight lines.
  - `test_caerness_cycle_untouched`: `world_pkg_caerness_regression_test`'s opening, advanced 60 days, gives the same `enterprise_accounts` totals before and after this task. Record that number in Step 1 before changing any code, then compare against it.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `bz1_clock_test`, the quick suite (`tools/run_suite.py --quick --out runs/bz1_t7`) and `world_pkg_caerness_regression_test`. Expect PASS, with the quick suite's TOTAL equal to the Task 1 baseline (no new failures).
- [ ] **Step 5: Commit.** Message: `feat(business): BZ1.7 the shared layer runs on the clock and explains itself`.

### Task 8: Plug into the intake (gated)

**Gate:** start only when the history design's intake core (that spec's §9 step 1: `held_things`, `depth_gaps`, the shape choice and `author` routed through it) is on HEAD. If it is not, mark this task blocked in the report and stop. Tasks 1–7 stand on their own.

**Files:**
- Create: `engine/intake_business.py`
- Modify: wherever the intake keeps its shape table (as named on HEAD), to register three backings
- Test: `tests/bz1_intake_test.py`

**What it registers.** The history design's five shapes in play are Org, Place, Holding, Arrangement and Thing.
- **Holding** backed by `place_details`: a building, a storefront, a lot. The intake fields map as follows: `place → location_id`, `money.upkeep → upkeep_usd_30`, `people.owners → owner_ref`, a straw → `legal_owner_ref`.
- **Arrangement** backed by `agreement_terms`: any two-party terms with money. `money` maps to the amount and `every_days`, `dates.due` to `first_due_day`, and the breach word comes from the proposal's `consequences`, mapped through `breach_words`. An unmapped word is a `depth_gaps` bump, not a refusal (history design H5).
- **A built thing goes through check 7** (means and competence, which becomes a commitment with a due day) as a **venture**: `start_venture`. The intake row's id is stored in `payoff_json` as `held_thing_id`. When the venture completes, the held thing goes live.
- **Claim breaches** (Task 5) bump `depth_gaps` with class `civil claim`.

**Interfaces:**
- Consumes: the intake's row writer and its shape-registration hook, with the names they have on HEAD.
- Produces: `register(conn) -> None`, called wherever the intake registers its shapes.
- The contract: one `held_things` row per place, term or venture made through `author`, with `backing_table` and `backing_id` set.

- [ ] **Step 1: Write the failing tests.**
  - `test_author_building_is_held_place`: `author(kind="a garage on Front Street", details={...owner, upkeep...})` makes a `held_things` row with shape Holding and backing `place_details`, and the place's upkeep is paid at the next due tick.
  - `test_author_deal_is_held_term`: "10% of the take, weekly" between two people becomes an `agreement_terms` row that pays.
  - `test_author_build_goes_through_venture`.
  - `test_claim_breach_bumps_gap`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `bz1_intake_test` and the intake's own tests. Expect PASS.
- [ ] **Step 5: Commit.** Message: `feat(business): BZ1.8 places, terms and ventures behind the intake`.

### Task 9: The five-year measure and the runbook line

**Files:**
- Modify: `AGENTS.md` (one status line under the current-state section: what BZ1 added and the measured cost)
- Test: none new. This task measures.

- [ ] **Step 1:** Run one five-year seed in the background with `B15_SEED=3` (`python tests/saintjude_mob_fires_test.py`). Run at most two long runs at once.
- [ ] **Step 2:** Compare against the Task 1 baseline.
  - Report: wall time, DB size at 1980, and the row counts of the seven BZ1 tables.
  - Flag it if the time grew more than 5% or the DB more than 2 MB. **Do not tune to hit a number.** Find the driver (the query, the cadence or the row growth) and report it.
- [ ] **Step 3:** Run the full suite (`tools/run_suite.py --out runs/bz1_full`) once, in the background. The TOTAL must have no new failures against the baseline.
- [ ] **Step 4: Commit.** Add `AGENTS.md`. Message: `docs: BZ1 shared business layer landed; five-year cost measured`.

---

## Left to the implementer

- The spec's workplace roster (§5.3) needs no new table in BZ1. It is read from the existing employment of the place's `enterprise_id`. BZ2 adds a table if that proves thin **[my call]**.

- Exact SQL indexes beyond the three `next_due_day` ones.
- Row-to-dict helpers and the private function layout inside each module.
- The wording of `source` strings, which must name the origin (for example "seasonality: hospitality, March (bible IV §3.8)").
- **How an org is addressed.** It is the `org_money` purse-role holder. If no helper exists, add `org_money.purse_ref(conn, org_id) -> str | None` in Task 5 and note it in the report.
