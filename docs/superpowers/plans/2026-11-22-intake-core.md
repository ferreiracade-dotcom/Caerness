# The intake core (I-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every lasting thing the GM narrates goes through one door (`author`) and becomes a held, simulated thing at B depth. It has owners, money, an agenda, a place, dates and consequences, and a gap flag when nothing deeper exists for it. Free-operation commitments that settle go through the same door.

**Architecture:**
- `engine/intake.py` is the door. It turns a proposal into a `Proposal`, picks a shape from a registry, runs the veto-only checks, calls the shape's maker if it has one, and always writes one `held_things` row. For floor-backed shapes and unread consequences it writes a `depth_gaps` row.
- `engine/held_things.py` is the weekly B tick, registered like the org core's processes.
- `engine/authoring.author` and `engine/free_operation.settle_due` both go through `intake.take_in`.
- All figures and shape words live in package data (`worlds/saintjude/intake.json`). A package without that file (Caerness) behaves exactly as today.

**Tech Stack:** Python 3.13, SQLite, the repo's script-style tests (`tests/*_test.py`, run directly).

**Spec:** `docs/superpowers/specs/2026-11-22-real-history-and-engine-gaps-design.md`. Approved 2026-11-22; this plan is §9 step 1: §5.1, §5.2 checks 1 to 4 and 7, §5.3 without lazy places, §5.4, §7.1 and §7.4, and owner decision H5.

**Shared with the business sphere (BZ1 depends on this plan; it does not rebuild it):**
- the `author` kinds and the free-text door;
- `Proposal`;
- the shape registry (`Shape`, `register_shape`);
- `held_things`, `depth_gaps` and `adopt_floor`.

BZ1 registers its venture, property and agreement makers on the `holding` and `arrangement` shapes that Task 2 declares floor-backed. BZ1 then calls `adopt_floor` to move rows already held into its tables.

## Global Constraints

- No world words in `engine/` or `connector/` code (`tests/no_world_words_test.py` stays green). New shapes' words, reader words and every figure live in `worlds/saintjude/intake.json`.
- Figures are read with `engine.org_succession.v(conn, spec)`, which raises KeyError on a missing figure. No hidden defaults and no fallback numbers in code.
- A package whose `world.json` `data` has no `"intake"` key keeps today's behaviour exactly: an unclear `kind` is still refused with `input_gap`, there is no tick, and no `depth_gaps` rows are written. The Caerness regression and `tests/fixtures/caerness_opening_fingerprint.json` are unchanged.
- The engine vetoes and never lists. A refusal names the clash, an oversized ask is scaled down with its reason, and an unclear shape lands on the `thing` floor with a gap flag. That is never a refusal (owner decision H5).
- No hard caps: arrears, growth and failure are weighed or counted, never clamped to a ceiling.
- Never write `data/*.db`. Tests copy fixtures into temp dirs.
- The schema version is the next free one at implementation time. It is 123 if HEAD's `SCHEMA_VERSION = 122` is still the latest; check `engine/db.py` first. The migration function is `None` (tables come from `schema.sql`), like versions 118 to 122.
- **Work in a worktree from HEAD.** The shared checkout has other sessions' uncommitted edits in `engine/db.py`, `engine/schema.sql` and `worlds/saintjude/world.json`. Never commit their hunks.
- Commit only the files the task names.
- Run tests with `PYTHONPATH=. /c/Users/NozzE/AppData/Local/Programs/Python/Python313/python.exe tests/<file>.py`. Expected success output: `N/N passed`.

## Review Focus

1. **The same `call_id` sent twice** (the connector replays): exactly one `held_things` row and one `depth_gaps` bump. Pinned in Task 6.
2. **An owner who dies, or a purse that can't pay upkeep**: the thing passes to the next living person in `people`, then to the owner's org head, or ends with a reason. It never ticks forever on a dead man's purse. Pinned in Task 4.
3. **Money given in words** ("a few thousand", "half his money", "$200 a week", "1,000 a month"): it parses to a start cost and weekly figures, and a month figure becomes a week figure. Pinned in Task 2.
4. **The same thing proposed twice under different call_ids** (same normalised name, same owner, still active): refused as a contradiction that names the held thing's id. Pinned in Task 3.
5. **Caerness** (no intake data): an unclear kind is still `input_gap`, the tick doesn't register work, and the opening fingerprint is identical. Pinned in Task 1 and Task 3.

---

### Task 1: Tables, package data and the rules accessor

**Files:**
- Modify: `engine/schema.sql`: append the two tables below.
- Modify: `engine/db.py`: `SCHEMA_VERSION`, plus a `_MIGRATIONS` entry `(<next>: ("intake_core", "One intake: held things at B depth and the depth gaps they flag (held_things, depth_gaps)", None))`.
- Modify: `engine/world_package.py`: add `intake_rules(pkg) -> dict` beside `org_rules`.
- Create: `worlds/saintjude/intake.json`.
- Modify: `worlds/saintjude/world.json`: add `"intake": "intake.json"` to `data` (a targeted text edit; don't re-dump the file).
- Test: `tests/intake_test.py` (created here; later tasks add to it).

**Interfaces:**
- Produces: tables `held_things` and `depth_gaps`; `world_package.intake_rules(pkg) -> dict` (empty when the package has no `"intake"`).

The tables:

```sql
CREATE TABLE IF NOT EXISTS held_things (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind_text TEXT NOT NULL DEFAULT '',
    shape TEXT NOT NULL,
    backing_table TEXT,
    backing_id INTEGER,
    owner_actor_id INTEGER REFERENCES actors(id) ON DELETE SET NULL,
    people_json TEXT NOT NULL DEFAULT '[]',
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    place_text TEXT,
    from_ref TEXT,
    start_cost REAL NOT NULL DEFAULT 0,
    income_weekly REAL NOT NULL DEFAULT 0,
    upkeep_weekly REAL NOT NULL DEFAULT 0,
    arrears_weeks INTEGER NOT NULL DEFAULT 0,
    agenda TEXT NOT NULL DEFAULT '',
    start_day INTEGER NOT NULL,
    end_day INTEGER,
    recurrence_days INTEGER,
    legality TEXT NOT NULL DEFAULT 'unknown' CHECK (legality IN ('legal','grey','illegal','unknown')),
    knows_json TEXT NOT NULL DEFAULT '[]',
    consequences_json TEXT NOT NULL DEFAULT '[]',
    readers_json TEXT NOT NULL DEFAULT '[]',
    unmapped_json TEXT NOT NULL DEFAULT '[]',
    source TEXT,
    real_date TEXT,
    verify INTEGER NOT NULL DEFAULT 0 CHECK (verify IN (0,1)),
    depth TEXT NOT NULL DEFAULT 'B',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('building','active','failing','ended')),
    ended_reason TEXT,
    gap_key TEXT,
    call_id TEXT,
    created_day INTEGER NOT NULL,
    updated_day INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_held_things_status ON held_things(status);
CREATE TABLE IF NOT EXISTS depth_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_key TEXT NOT NULL UNIQUE,
    shape TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    first_day INTEGER NOT NULL,
    last_day INTEGER NOT NULL,
    examples_json TEXT NOT NULL DEFAULT '[]',
    missing_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','built'))
);
```

`worlds/saintjude/intake.json` holds starting calibrations, reported and never enforced:

```json
{
  "shape_words": {
    "holding": ["building", "property", "land", "house", "apartment", "car", "truck", "fleet", "boat", "plane", "pier", "lot", "stake", "share", "account", "warehouse"],
    "arrangement": ["deal", "contract", "agreement", "partnership", "arrangement", "understanding", "promise", "lease", "marriage", "engagement", "pact"],
    "custom": ["custom", "tradition", "truce", "feast", "standing rule", "ritual", "every year", "every sunday"]
  },
  "readers": {
    "money": ["earns", "income", "pays", "costs", "upkeep", "takes in", "profit"],
    "heat": ["illegal", "police", "cops", "heat", "raid", "law"],
    "knowledge": ["known", "talk", "word", "rumour", "everyone knows"],
    "succession": ["inherit", "heir", "passes to", "will"]
  },
  "tick": {
    "happening_week_rate": 0.05,
    "arrears_weeks_to_fail": 4,
    "grow_share": 0.10,
    "shrink_share": 0.10,
    "illegal_weekly_investigative_heat": 0.05
  }
}
```

- [ ] **Step 1: Write the failing tests** in `tests/intake_test.py` (script style, like `tests/b12g_test.py`: `tests = [...]`, `_run_all()`, `sys.exit`):

```python
def test_tables_exist_and_saintjude_has_intake_rules():
    from engine.world_package import intake_rules, package_for
    w = _open_world()                      # from tests.outfit_choice_fixture import open_world as _open_world, DAY
    c = w.conn
    for t in ("held_things", "depth_gaps"):
        assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone(), t
    r = intake_rules(package_for(c))
    assert set(r) >= {"shape_words", "readers", "tick"}
    assert r["tick"]["arrears_weeks_to_fail"] == 4

def test_caerness_has_no_intake_rules():
    # copy data/caerness.db to a temp dir as tests/connector_author_test.py does; set CAERNESS_DB_PATH; init_db(); connect()
    from engine.world_package import intake_rules, package_for
    assert intake_rules(package_for(conn)) == {}
```

- [ ] **Step 2: Run them to see them fail.** Expected: FAIL (no table, no `intake_rules`).
- [ ] **Step 3: Implement** the tables, migration entry, `intake_rules` (`return _data_json(pkg, "intake")`), the JSON file and the `world.json` key.
- [ ] **Step 4: Run** `tests/intake_test.py`, `tests/org_migration_test.py` and `tests/no_world_words_test.py`. Expected: all pass.
- [ ] **Step 5: Commit** `engine/schema.sql engine/db.py engine/world_package.py worlds/saintjude/intake.json worlds/saintjude/world.json tests/intake_test.py` with the message `feat(intake): held_things and depth_gaps tables, intake package data (schema <next>)`.

---

### Task 2: The proposal and the shape registry

**Files:**
- Create: `engine/intake.py`.
- Test: `tests/intake_test.py`.

**Interfaces:**
- Produces:
  - A frozen `@dataclass class Proposal` with these fields:
    - `what: str`, `kind_text: str`, `people: tuple[int, ...]`, `owner: int`;
    - `location_id: int | None`, `place_text: str | None`, `from_ref: str`;
    - `start_cost: float`, `income_weekly: float`, `upkeep_weekly: float`;
    - `agenda: str`, `start_day: int`, `end_day: int | None`, `recurrence_days: int | None`;
    - `legality: str`, `knows: tuple[int, ...]`, `consequences: tuple[str, ...]`;
    - `source: str | None`, `real_date: str | None`, `ready_in_days: int | None`;
    - `details: dict` (the raw details, for makers that read more).
  - `normalise(conn, me: int, kind: str, details: dict) -> Proposal`:
    - `owner` defaults to `me`, or the first of `people`;
    - `from_ref` defaults to `"me"`;
    - an unknown place name sets `place_text` and leaves `location_id` None. It is never refused here; lazy places are a later plan;
    - money comes from `details["money"]`, which is a dict `{start, income, upkeep, from}` or a bare start amount. Each value is a number or words. Words go through `ledger.amount_of(word, base)`, where `base` is the `from` holder's balance for the start cost. Income and upkeep text containing "month" is divided by 30/7, "year" by 52, and "week" is kept.
  - A frozen `@dataclass class Shape` with fields `name: str`, `words: tuple[str, ...]`, `fields: tuple[str, ...]`, `make: Callable[[sqlite3.Connection, int, Proposal, str], dict] | None`, and `floor_backed: bool`.
  - `register_shape(shape: Shape) -> None`: the latest registration for a name wins. This is how BZ1 replaces `holding` and `arrangement`.
  - `shapes(conn) -> list[Shape]`: the built-ins, then the package's `shape_words` shapes (`holding`, `arrangement`, `custom`, each `make=None, floor_backed=True` unless something is registered), then `thing` (the floor).
  - `shape_for(conn, kind: str, details: dict) -> Shape`: the same order as `authoring._kind_of`. An exact name, then words in `kind`, then the fields present. With intake rules and no match it returns `thing`. Without intake rules it raises `AuthoringRefused(..., "input_gap")` with today's message.
- The built-in shapes wrap the existing makers: `person`, `business`, `organisation` and `rumour` call `authoring._person/_business/_organisation/_rumour(conn, me, proposal.details, call_id)`. Their `fields` are today's `_kind_of` field keys.

- [ ] **Step 1: Write the failing tests:**

```python
def test_words_and_fields_pick_the_shape():
    from engine import intake
    w = _open_world(); c = w.conn
    assert intake.shape_for(c, "a numbers bank", {"members": [w.soldier]}).name == "organisation"
    assert intake.shape_for(c, "the warehouse on Ferry Street", {}).name == "holding"
    assert intake.shape_for(c, "a ten percent deal", {}).name == "arrangement"
    assert intake.shape_for(c, "the Saint Rocco truce", {}).name == "custom"
    s = intake.shape_for(c, "something nobody has a word for", {})
    assert s.name == "thing" and s.floor_backed

def test_registering_a_maker_replaces_the_floor_shape():
    from engine import intake
    w = _open_world(); c = w.conn
    made = []
    intake.register_shape(intake.Shape("holding", (), (), lambda conn, me, p, cid: made.append(p.what) or {"backing_table": "x", "backing_id": 1}, False))
    try:
        assert intake.shape_for(c, "a pier", {}).floor_backed is False
    finally:
        intake._reset_registry_for_tests()

def test_money_words_parse_to_start_and_weekly():
    from engine import intake
    w = _open_world(); c = w.conn
    p = intake.normalise(c, w.capo, "a bookmaking wire", {"what": "a wire", "money": {"start": 500, "income": "1,000 a month", "upkeep": "$200 a week"}})
    assert p.start_cost == 500 and abs(p.income_weekly - 1000 * 7 / 30) < 0.01 and p.upkeep_weekly == 200
    q = intake.normalise(c, w.capo, "x", {"what": "x", "money": {"start": "half", "from": "me"}})
    assert q.start_cost > 0
```

- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Implement** `engine/intake.py` with the interfaces above, plus `_reset_registry_for_tests()`, which drops registered overrides. The words come only from package data for the new shapes. The built-in words stay in `authoring._KIND_WORDS`, and `shape_for` reuses them.
- [ ] **Step 4: Run** `tests/intake_test.py`. Expected: pass.
- [ ] **Step 5: Commit** `engine/intake.py tests/intake_test.py` with the message `feat(intake): proposal and shape registry`.

---

### Task 3: `take_in`: checks, the held row, gaps; authoring goes through it

**Files:**
- Modify: `engine/intake.py`.
- Modify: `engine/authoring.py`: `author()` calls `intake.take_in` inside its existing savepoint. `_kind_of` becomes a thin call to `intake.shape_for(...).name` for packages with intake rules, and is unchanged otherwise.
- Test: `tests/intake_test.py`, `tests/authoring_test.py` (must stay green).

**Interfaces:**
- Consumes: Task 2's `normalise`, `shape_for` and `Shape`.
- Produces:
  - `take_in(conn, me: int, kind: str, details: dict, call_id: str) -> dict`. It returns the maker's result (if any), merged with:
    - `"status": "created"` (or `"scaled_down"` with a `"scaled"` reason);
    - `"kind": shape.name`, `"held_thing_id": int`, `"name": str`;
    - `"gap": gap_key` when one was written.

    It raises `AuthoringRefused` for a refusal.
  - `bump_gap(conn, gap_key: str, shape: str, held_id: int, missing: list[str]) -> None`.
  - `adopt_floor(conn, shape_name: str) -> int`: re-runs the now-registered maker for every active floor row of that shape, sets `backing_table`, `backing_id` and `gap_key = NULL`, marks the gap `built` when no open rows are left, and returns the count. This is for BZ1.

The checks, in this order:
1. **World text:** `veto.check_world_text(conn, details)`. This stays as today, in `authoring.author`, before the savepoint.
2. **Established facts:**
   - every actor in `people`, `owner` and `knows` must be living (`player_operations._living`); a dead one is refused as "<name> is dead";
   - an active `held_things` row with the same normalised `name` and the same `owner` is refused as "that is already held (held thing <id>)";
   - a given `location_id` must exist.
3. **Real people:** unchanged. It stays inside the person maker (`veto.real_person` and `name_taken`).
4. **World scale:**
   - `start_cost` is taken with `ledger.spend(conn, ledger.parse_holder(from_ref, me, conn), start_cost, purpose=what, allow_partial=True)` after `ledger.can_draw`; refuse "He has no right to draw on that purse" if he can't draw;
   - when less was spent than asked, `income_weekly` and `upkeep_weekly` scale by the same share, and the result says `scaled_down` with the reason "the money on hand covered only part of it".
5. **Means:** `ready_in_days` set means `status='building'` and a commitment through `commitments.record(conn, me, what, kind="intake", due_day=today+ready_in_days, details={"held_thing_id": id})`. Task 5 makes it go live when that settles.

Name is `details["name"]` or `what` truncated to 80 characters.

Readers: each consequence phrase and the `agenda` are matched against `intake_rules["readers"]` words. The matched reader keys go to `readers_json`, and phrases with no match go to `unmapped_json`. Legality `illegal` always adds `heat`.

`gap_key` is `shape.name + ":" + <the first three content words of kind_text, lowercased>`. It is written when the shape is floor-backed, or when `unmapped_json` is non-empty, with `missing` holding the unmapped phrases. Each knower in `knows` is told once with `findings.tell(conn, k, [what], source=owner)`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_a_floor_thing_is_held_with_people_money_place_and_a_gap():
    from engine import authoring, ledger
    w = _open_world(); c = w.conn
    before = ledger.balance(c, ("person", w.capo))
    out = authoring.author(c, w.capo, "a pigeon racing club for the bosses", {"what": "the Ferry Street pigeon club", "people": [w.capo, w.soldier],
                           "place": w.ground, "money": {"start": 100, "upkeep": "20 a week"}, "agenda": "win the Shore race", "legality": "legal"}, "t3-1")
    row = c.execute("SELECT * FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()
    assert out["kind"] == "thing" and row["status"] == "active" and row["upkeep_weekly"] == 20 and row["location_id"] == w.ground
    assert ledger.balance(c, ("person", w.capo)) == before - 100
    g = c.execute("SELECT * FROM depth_gaps WHERE gap_key=?", (out["gap"],)).fetchone()
    assert g["count"] == 1 and g["status"] == "open"

def test_an_existing_shape_still_makes_its_entity_and_also_a_held_row():
    from engine import authoring
    w = _open_world(); c = w.conn
    out = authoring.author(c, w.capo, "organisation", {"name": "The Ferry Street Social Club", "members": [w.soldier]}, "t3-2")
    row = c.execute("SELECT * FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()
    assert row["shape"] == "organisation" and row["backing_table"] and row["backing_id"] and row["gap_key"] is None

def test_a_dead_owner_and_a_duplicate_are_refused_by_name():
    from engine import authoring
    w = _open_world(); c = w.conn
    authoring.author(c, w.capo, "a card game", {"what": "the Tuesday card game", "people": [w.capo]}, "t3-3")
    try: authoring.author(c, w.capo, "a card game", {"what": "the Tuesday card game", "people": [w.capo]}, "t3-4"); assert False
    except authoring.AuthoringRefused as e: assert "already held" in str(e)
    c.execute("UPDATE actors SET status='deceased' WHERE id=?", (w.soldier,))
    try: authoring.author(c, w.capo, "a card game", {"what": "another game", "people": [w.soldier]}, "t3-5"); assert False
    except authoring.AuthoringRefused as e: assert "dead" in str(e)

def test_an_oversized_start_is_scaled_down_with_its_reason():
    from engine import authoring
    w = _open_world(); c = w.conn
    out = authoring.author(c, w.soldier, "a stake in a trucking fleet", {"what": "a stake in the Route 9 fleet", "money": {"start": 10_000_000, "income": "500 a week"}}, "t3-6")
    assert out["status"] == "scaled_down" and "part" in out["scaled"]
    assert c.execute("SELECT income_weekly FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()[0] < 500

def test_caerness_unclear_kind_is_still_an_input_gap():
    # Caerness copy as in Task 1; a protagonist set with engine.player.set_player
    from engine import authoring
    try: authoring.author(conn, me, "something nobody has a word for", {}, "t3-7"); assert False
    except authoring.AuthoringRefused as e: assert getattr(e, "reason_kind", "") == "input_gap"
    assert conn.execute("SELECT COUNT(*) FROM depth_gaps").fetchone()[0] == 0
```

- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Implement** `take_in`, `bump_gap` and `adopt_floor`, and route `authoring.author` through `take_in` when `intake_rules` is non-empty. Otherwise the old `_KINDS[target](...)` path stays byte-for-byte.
- [ ] **Step 4: Run** `tests/intake_test.py`, `tests/authoring_test.py`, `tests/connector_author_test.py` and `tests/no_world_words_test.py`. Expected: all pass.
- [ ] **Step 5: Commit** `engine/intake.py engine/authoring.py tests/intake_test.py` with the message `feat(intake): take_in with veto-only checks; authoring goes through it`.

---

### Task 4: The B tick for held things

**Files:**
- Create: `engine/held_things.py`.
- Modify: `engine/simulation.py`: import, and `reg.register(ProcessSpec("held_things", next_held_things_due_day, process_due_held_things))` next to `outfit_incidents`.
- Test: `tests/intake_test.py`.

**Interfaces:**
- Consumes: the `held_things` rows from Task 3, `org_succession.v`, `ledger`, `org_heat.add` and `findings.tell`.
- Produces:
  - `next_due_day(conn, after_day: int, end_day: int) -> int | None`: weekly, on the same grid as `org_happenings.next_due_day`. It returns None when the package has no intake rules or no active or failing rows exist.
  - `process_due(conn, day: int, *, event_logger=None) -> dict` with counts `{paid, failing, ended, passed_on, happenings}`.

Per active or failing row, each tick:
1. **Owner.** If the owner isn't living, pass the row to the next living actor in `people`. Failing that, pass it to the head of the owner's org (`org_seats` active row, then `orgs.head_of`). Failing that, end it with the reason "its owner died and no one took it up". Count `passed_on` or `ended`.
2. **Money.** Receive `income_weekly` into the owner's holder (`ledger.receive`, with purpose "<name>: takings"). Spend `upkeep_weekly` from it (`allow_partial=True`). A shortfall adds 1 to `arrears_weeks` and sets `failing`, and full payment resets it to 0. When `arrears_weeks >= v(tick.arrears_weeks_to_fail)`, end the row with "it could not pay its way", and the owner is told.
3. **Heat.** `legality == 'illegal'` with an owner who holds an org seat adds `org_heat.add(conn, org, day, investigative=v(tick.illegal_weekly_investigative_heat))`.
4. **Happenings.** With a seeded draw (`random.Random(f"held:{row_id}:{day}")`) and chance `v(tick.happening_week_rate)`, one of three things happens, weighted equally:
   - **grow:** income times (1 + grow_share);
   - **shrink:** income times (1 − shrink_share);
   - **notice:** the owner is told the thing drew notice, and an illegal row adds the same heat again.

   It is logged with `event_logger` when given, otherwise through `player_operations._record` for the protagonist's own rows only.
5. **Dates.** `end_day` reached ends the row with "its time ran out". `recurrence_days` rows (customs) only touch `updated_day` on their day, and their readers act then.

- [ ] **Step 1: Write the failing tests:**

```python
def test_a_held_thing_earns_and_pays_each_week():
    from engine import authoring, held_things, ledger
    w = _open_world(); c = w.conn
    out = authoring.author(c, w.capo, "a jukebox route", {"what": "the Ward 3 jukebox route", "money": {"income": "300 a week", "upkeep": "100 a week"}}, "t4-1")
    b = ledger.balance(c, ("person", w.capo))
    held_things.process_due(c, DAY + 7)
    assert abs(ledger.balance(c, ("person", w.capo)) - (b + 200)) < 0.01

def test_a_thing_that_cannot_pay_fails_then_ends_and_its_owner_is_told():
    from engine import authoring, held_things, ledger
    w = _open_world(); c = w.conn
    out = authoring.author(c, w.soldier, "a racing pigeon loft", {"what": "the loft", "money": {"upkeep": "1,000,000 a week"}}, "t4-2")
    for k in range(1, 6):
        held_things.process_due(c, DAY + 7 * k)
    row = c.execute("SELECT status,ended_reason FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()
    assert row["status"] == "ended" and "pay its way" in row["ended_reason"]

def test_a_dead_owners_thing_passes_to_the_next_of_its_people():
    from engine import authoring, held_things
    w = _open_world(); c = w.conn
    out = authoring.author(c, w.capo, "a social club", {"what": "the Vesuvio room", "people": [w.capo, w.soldier]}, "t4-3")
    c.execute("UPDATE actors SET status='deceased' WHERE id=?", (w.capo,))
    held_things.process_due(c, DAY + 7)
    assert c.execute("SELECT owner_actor_id FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()[0] == w.soldier

def test_an_illegal_thing_draws_heat_on_its_owners_organisation():
    from engine import authoring, held_things, org_heat
    w = _open_world(); c = w.conn
    authoring.author(c, w.capo, "a chop shop", {"what": "the Route 1 chop shop", "legality": "illegal", "money": {"income": "400 a week"}}, "t4-4")
    h0 = org_heat.read(c, w.org, DAY + 7)["investigative_heat"]
    held_things.process_due(c, DAY + 7)
    assert org_heat.read(c, w.org, DAY + 7)["investigative_heat"] > h0
```

- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Implement** `engine/held_things.py` and register it in `engine/simulation.py`.
- [ ] **Step 4: Run** `tests/intake_test.py`, `tests/org_happenings_test.py` and `tests/b12g_test.py`. Expected: all pass.
- [ ] **Step 5: Commit** `engine/held_things.py engine/simulation.py tests/intake_test.py` with the message `feat(intake): held things live at B depth (money, owner, heat, happenings)`.

---

### Task 5: Settled commitments become held things

**Files:**
- Modify: `engine/free_operation.py`: in `settle_due`'s generic branch (today the `else:` that writes "It was carried out as planned").
- Test: `tests/intake_test.py`, `tests/act_freeform_test.py` (must stay green).

**Interfaces:**
- Consumes: `intake.take_in` (Task 3).
- Produces: the settled entry gains `"held_thing_id"`, and its `result` reads `"<old result> It now stands as <name>."`. A `kind="intake"` commitment (a building thing, Task 3) sets its held row `status='active'` instead of calling `take_in` again.

The proposal built from the commitment:
- `what` is `r["description"]`;
- `kind` is the commitment's `kind` or the description;
- `people` is `details["people"]`, with `owner = me`;
- `place` is `r["target_location_id"]`;
- `money` is `{"start": 0}`, because the costs were already taken at `_commit`;
- the description's words feed the readers as consequences.

`funded < 1` scales nothing further: `_commit` already scaled it. A `take_in` refusal (for example a dead target) keeps the old result text and adds `" Nothing of it lasts: <reason>."`. Packages without intake rules keep today's branch exactly.

- [ ] **Step 1: Write the failing tests:**

```python
def test_a_free_operation_that_settles_leaves_a_held_thing():
    from engine import free_operation, held_things
    w = _open_world(); c = w.conn
    from engine.player import set_player
    set_player(c, w.capo)
    out = free_operation.run(c, w.capo, "set up a bookmaking wire in the back of the Ferry Street candy store", {"time": "a week"}, "t5-1")
    assert out.get("commitment_id"), out  # nothing models it, so it is a commitment
    c.execute("UPDATE world_state SET current_day=current_day+8 WHERE id=1")
    done = free_operation.settle_due(c, w.capo)
    hid = done[0]["held_thing_id"]
    assert c.execute("SELECT status FROM held_things WHERE id=?", (hid,)).fetchone()[0] == "active"
    assert "now stands as" in done[0]["result"]
```

- [ ] **Step 2: Run it to see it fail.**
- [ ] **Step 3: Implement** the branch change.
- [ ] **Step 4: Run** `tests/intake_test.py` and `tests/act_freeform_test.py`. Expected: all pass.
- [ ] **Step 5: Commit** `engine/free_operation.py tests/intake_test.py` with the message `feat(intake): settled commitments become held things`.

---

### Task 6: The connector: provenance, lookup and the GM's words

**Files:**
- Modify: `connector/authoring.py`: add `("held_thing_id", "held_things")` as the **last** `_ENTITY` entry, so a backed shape still records its own table first.
- Modify: `connector/views.py`:
  - `lookup` adds `("thing", [r for r in _find(conn, "held_things", q) if r["status"] != "ended"])` to `kinds`, with basics `{shape, owner name, place (location name or place_text), status, weekly income, weekly upkeep, legality, agenda, depth}`;
  - the exact query `"gaps"` returns `{"found": True, "kind": "gaps", "gaps": [{gap_key, shape, count, last_day, missing}]}` for open gaps, by count descending, top 10.
- Modify: `connector/server.py`: the `author` docstring's second sentence becomes "kind is free text: anything lasting the world has no mechanism for is still held (owners, money {start, income, upkeep, from}, agenda, place, dates, legality, knows, consequences) and flagged for deeper build; person, business, organisation, rumour and protagonist keep their fields". Keep it under the current docstring's length plus 40%.
- Modify: `connector/rulebook_core.md`: one line in the authoring rules: "Anything lasting that act and note cannot hold: author it with its people, money, place and agenda; the engine keeps it alive and flags it."
- Test: `tests/connector_author_test.py` (extend it), `tests/intake_test.py`.

**Interfaces:**
- Consumes: Tasks 3 and 4.
- Produces: nothing new for engine code. The GM sees held things and gaps through `lookup`.

- [ ] **Step 1: Write the failing tests** in `tests/intake_test.py`, through the connector, with a Saint Jude fixture and `set_player(conn, w.capo)` plus `store.ensure_connector_schema(conn)`:

```python
def test_the_same_call_twice_holds_one_thing_and_one_gap_bump():
    from connector.authoring import author
    r1 = author(c, "t6-1", "a pigeon club", {"what": "the Ferry Street pigeon club"})
    r2 = author(c, "t6-1", "a pigeon club", {"what": "the Ferry Street pigeon club"})
    assert r2.get("replayed") and r2["held_thing_id"] == r1["held_thing_id"]
    assert c.execute("SELECT COUNT(*) FROM held_things WHERE call_id='t6-1'").fetchone()[0] == 1
    assert c.execute("SELECT count FROM depth_gaps WHERE gap_key=?", (r1["gap"],)).fetchone()[0] == 1
    assert c.execute("SELECT entity_table FROM authored_entities WHERE call_id='t6-1'").fetchone()[0] == "held_things"

def test_lookup_finds_a_held_thing_and_lists_gaps():
    from connector.views import lookup
    hit = lookup(c, "the Ferry Street pigeon club")
    assert hit["found"] and hit["kind"] == "thing" and hit["basics"]["depth"] == "B"
    gaps = lookup(c, "gaps")
    assert gaps["kind"] == "gaps" and gaps["gaps"][0]["count"] >= 1
```

- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Implement** the four changes.
- [ ] **Step 4: Run** `tests/intake_test.py`, `tests/connector_author_test.py`, `tests/connector_org_views_test.py` and `tests/no_world_words_test.py`. Expected: all pass.
- [ ] **Step 5: Commit** `connector/authoring.py connector/views.py connector/server.py connector/rulebook_core.md tests/intake_test.py tests/connector_author_test.py` with the message `feat(intake): connector records, looks up and explains held things`.

---

### Task 7: Play-check and a 90-day run

**Files:**
- Create: `tests/intake_play_test.py`.

**Interfaces:**
- Consumes: everything above.

The test, through the connector only, on a Saint Jude fixture with a protagonist:
1. Author three things:
   - a legal floor thing with income and upkeep;
   - an illegal holding-shaped thing ("the warehouse on Ferry Street, for hijacked loads");
   - a custom ("the Feast of Saint Rocco truce, every year on 16 August").
2. Act one free operation that settles into a fourth.
3. `advance` 30 days, three times.
4. Assert structural truths only:
   - all four rows exist with status in `active`, `failing` or `ended`, and none vanished;
   - every `ended` row has an `ended_reason`;
   - `lookup("gaps")` lists the floor, holding and custom gaps;
   - the money balances: the sum of the owner's receipts minus spends equals the change in his balance, within 0.01;
   - no exception in `advance`.
5. Print, never assert: how many happenings fired, which rows grew or shrank, and the heat on his org.

- [ ] **Step 1: Write the test.**
- [ ] **Step 2: Run** `PYTHONPATH=. <python> tests/intake_play_test.py`. Expected: PASS, with printed findings. If it takes more than 60 s, add `intake_play_test` to `tests/slow_tests.txt` with its time.
- [ ] **Step 3: Run** the quick suite with `PYTHONPATH=. <python> tools/run_suite.py --quick`. Expected: no new failures against HEAD's list.
- [ ] **Step 4: Commit** `tests/intake_play_test.py` (and `tests/slow_tests.txt` if changed) with the message `test(intake): play-check, held things survive three advances`.

---

## Out of scope (later plans in the spec's §9)

- Lazy places (step 2): an unknown place stays `place_text` here.
- Real facts with check 5 and the `dated_rules` change (step 3).
- `tech_level` and check 6 (step 4).
- The coverage tripwire and the "what was due" prompt (step 5).
- BZ1's makers for `holding` and `arrangement`, and its call to `adopt_floor`.
