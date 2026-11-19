# Saint Jude Organisation Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the mob-shaped outfit layer (tasks 3–9 of the mob minimum) into a world-agnostic organisation core, then finish mob tasks 10–16 on that core, so business and politics later arrive as data and thin modules.

**Architecture:** One migration (117) renames `outfit_*` to `org_*`, lets a person hold seats in several organisations, and removes the mob-only checks. A new `engine/orgs.py` reads **role rules per organisation kind** from a new package file `orgs.json` (who heads, who leads a unit, who stands in, who holds the purse) and replaces every `capo`/`boss` literal. The Pad becomes one kind of **arrangement** (any payer to any official). Choice, motive, lifecycle and law-response machinery from tasks 10–13 are built generic (`org_*` modules) with the mob's choices registered on top (`outfit_*` modules).

**Tech Stack:** Python 3.13, SQLite, standalone test scripts run by `tools/run_suite.py`.

**Spec:** `docs/superpowers/specs/2026-11-19-saintjude-three-spheres-design.md`. Also read `docs/superpowers/plans/2026-10-24-saintjude-mob-minimum.md` (the original plan; tasks 10–16 there are **amended** by section B below and keep everything this plan does not change) and `AGENTS.md`.

## Global Constraints

- Every Global Constraint of the mob-minimum plan still holds (Python path, scratch DBs, determinism, Design-proposal figures, sex shares, levels, pull-up only via `person_ecology`, commit per task, no push), except the schema line: this plan adds **migration 117** (`SCHEMA_VERSION = 117`), tables also in `engine/schema.sql` with `IF NOT EXISTS`.
- **No sphere vocabulary in core modules.** `engine/orgs.py`, `engine/org_money.py`, `engine/org_motives.py`, `engine/org_choices.py`, `engine/org_lifecycle.py`, `engine/crime_response.py` and `connector/views.py` contain no rank title (`boss`, `underboss`, `consigliere`, `capo`, `soldier`, `associate`, `made`, `president`, `banker`…), no outfit name and no dollar figure. A test greps for them (Task C2).
- Mob words live only in `worlds/saintjude/*.json`, `engine/outfit_*.py` and `engine/law_opening.py`'s Pad builder (which reads its words from `law.json`).
- Caerness behaves exactly as before: `tests/world_pkg_caerness_regression_test.py` green; Caerness's own organisation tables (`civilian_enterprises`, `organization_*`, `institution_*`) are not touched.
- After every task, every existing Saint Jude test listed under Task C1 Step 5 passes.

## Review Focus

1. **One person, two organisations.** A capo who also owns a trucking firm, an alderman who also runs a union local. Seats are per (person, organisation); his simulation level is the highest of his active seats; when he dies each org's line passes to that org's own stand-in. Test in C2 (`test_two_seats_two_stand_ins`).
2. **A migrated campaign DB.** An existing schema-116 DB (Caerness, and a Saint Jude scratch opening built before this plan) must migrate with every row kept and the same money totals. Test in C1 (`test_116_saintjude_opening_survives_117`).
3. **An org kind with no unit leader** (Brigades, a one-man firm). Stand-in falls straight to the head; a head with no live successor leaves the line unearned without crashing. Test in C2 (`test_kind_without_unit_leader`).
4. **A payer who is a person, not an organisation** (a builder bribing an inspector). The arrangement must draw from his own purse and post a ledger flow. Test in C3 (`test_person_pays_an_official`).
5. **A choice registered by a sphere the package does not enable.** The provider must offer nothing for org kinds the package does not declare. Test in B10 (`test_undeclared_kind_offers_nothing`).

---

## File Structure

| File | Responsibility |
|---|---|
| `engine/db.py`, `engine/schema.sql` | Migration 117 |
| `engine/world_package.py` | `org_rules(pkg)` (data key `orgs`) |
| `engine/orgs.py` (new; absorbs the generic half of `outfits.py`) | Seats, units, kind rules, head / unit leader / stand-in, levels, rhythm, agenda, `record_view` |
| `engine/outfits.py` | Mob-only helpers left after the move (kept thin; may end up empty and be deleted) |
| `engine/org_money.py` (new; the generic half of `outfit_money.py`) | Roster and earners, monthly posting walk, arrangements |
| `engine/outfit_money.py` | Mob holdings builder (pools to crews to lines); calls `org_money` to post |
| `engine/outfit_opening.py`, `engine/law_opening.py` | Mob opening; Pad written as arrangements |
| `engine/org_motives.py`, `engine/org_choices.py`, `engine/org_lifecycle.py` (new, section B) | Generic motive, choice and lifecycle machinery |
| `engine/outfit_choices.py`, `engine/outfit_incidents.py` (section B) | Mob choices, motives and happenings, registered on the core |
| `engine/crime_response.py` (section B) | Law response over any crime kind |
| `worlds/saintjude/orgs.json` (new) | Org kinds and their role rules; money flows; arrangement kinds |
| `tests/org_core_fixture.py` (new) | A tiny non-Saint-Jude package with one toy kind (`firm`) for core tests |

---

## Section A: the core refactor

### Task C1: Migration 117, rename and generalise the tables

**Files:**
- Modify: `engine/db.py` (`SCHEMA_VERSION = 117`, `_migration_117`), `engine/schema.sql`, every file that names an old table: `engine/outfits.py`, `engine/outfit_money.py`, `engine/outfit_opening.py`, `engine/law_opening.py`, `engine/household_life.py:743`, `engine/role_experience.py:101`, `engine/simulation.py:540`, and the tests below
- Modify: `tests/fixtures/caerness_opening_fingerprint.json` (regenerate the keys for the renamed, still-empty tables)
- Modify: `docs/superpowers/plans/2026-10-24-saintjude-mob-minimum.md` (one line under the Task 10 heading: "Amended by `2026-11-19-saintjude-org-core.md` section B; read that first.")
- Test: `tests/org_migration_test.py`

**Interfaces:**
- Produces, the table mapping (data is copied; old tables are dropped):

| Old | New | Changes |
|---|---|---|
| — | `org_profiles(org_actor_id PK → actors, org_kind TEXT NOT NULL, sphere TEXT NOT NULL, package_key TEXT, metadata_json)` | new: what kind of organisation an institution actor is |
| `outfit_crews` | `org_units` | `outfit_actor_id` → `org_actor_id` |
| `outfit_ranks` | `org_seats` | `id INTEGER PRIMARY KEY`; `UNIQUE(actor_id, org_actor_id)`; `outfit_actor_id` → `org_actor_id`; `rank_key` → `role_key`; `crew_id` → `unit_id`; `made_day` → `inducted_day`; `level CHECK (level BETWEEN 1 AND 4)` |
| `outfit_holdings` | `org_holdings` | `outfit_actor_id` → `org_actor_id` |
| `outfit_lines` | `org_lines` | `crew_id` → `unit_id` |
| `outfit_money` | `org_money` | `kind` loses its CHECK (validated against `orgs.json` `flows` in code); new `org_actor_id INTEGER` (the org whose books this row is in) |
| `outfit_agenda` | `org_agenda` | none |
| `outfit_incidents` | `org_incidents` | `raised_to_outfit_actor_id` → `raised_to_org_actor_id` |
| `pad_envelopes` | `org_arrangements` | `payer_outfit_actor_id` → `payer_kind TEXT CHECK IN ('org','actor')` + `payer_id INTEGER`; `officer_actor_id` → `official_actor_id`; `bagman_actor_id` → `go_between_actor_id`; new `kind TEXT NOT NULL` (existing rows: `'envelope'`) |

- `crime_reports` and custody tables are unchanged.
- `_migration_117` copies `org_actor_id` into `org_money` from the payer or payee's seat and writes one `org_profiles` row per outfit institution (`org_kind` = the outfit's `shape` from `outfits.json`, `sphere='underworld'`, `package_key` = its outfits key). The migration reads package data, so for a Caerness DB (no outfits) it writes no profiles.
- Constraint changes need table rebuilds (create new, `INSERT … SELECT`, drop old, recreate indexes); a plain `ALTER TABLE RENAME` is enough only where nothing else changes.
- Code in this task is a **mechanical rename only**: the same behaviour, new names. Mob logic moves in C2.

- [ ] **Step 1: Write the failing tests** in `tests/org_migration_test.py`:

```python
def test_fresh_db_has_org_tables():
    conn = fresh_db()                      # SCHEMA_VERSION 117
    for t in ("org_profiles","org_units","org_seats","org_holdings","org_lines","org_money","org_agenda","org_incidents","org_arrangements"):
        assert table_exists(conn, t)
    for t in ("outfit_ranks","outfit_crews","pad_envelopes"):
        assert not table_exists(conn, t)

def test_one_person_two_seats_allowed():
    insert two org_seats rows for one actor in two orgs -> no error; a second row for the same (actor, org) -> IntegrityError

def test_116_saintjude_opening_survives_117():
    a scratch DB on the Saint Jude package, migrated only up to 116 (_apply_migrations stops at 116; _migration_116 still holds the old DDL)
    insert a small hand-made outfit world: 2 outfits (one family, one club), crews, 8 ranks incl. made_day, holdings, lines, outfit_money rows of every kind, 3 pad_envelopes
    record counts and SUM(amount) by kind; migrate to 117
    -> the same numbers from org_money (org_actor_id filled), org_arrangements (kind='envelope', payer_kind='org'), org_seats by role_key with inducted_day = made_day,
       and one org_profiles row per outfit with sphere='underworld' and org_kind = its shape
```

- [ ] **Step 0 (before any change): record the baseline.** Build a Saint Jude opening on a scratch DB with the current code and post one 28-day period. Write the one-period sum of `outfit_money` kind `pad` and the sums of `take`/`kickup` into `tests/fixtures/org_refactor_baseline.json`. C2 and C3 assert against it.

- [ ] **Step 2: Run** `"$LOCALAPPDATA/Programs/Python/Python313/python.exe" tests/org_migration_test.py`. Expected: FAIL.
- [ ] **Step 3: Implement** the migration, the `schema.sql` tables and the rename across the files listed.
- [ ] **Step 4: Regenerate** the Caerness fingerprint fixture with the project's existing regeneration path (see the header of `tests/world_pkg_caerness_regression_test.py`); the diff should show only the renamed table keys.
- [ ] **Step 5: Run** this test plus `outfit_rhythm_test.py`, `saintjude_families_opening_test.py`, `saintjude_gangs_opening_test.py`, `saintjude_law_opening_test.py`, `saintjude_outfits_data_test.py`, `saintjude_outfit_money_test.py`, `saintjude_connector_play_test.py`, `world_pkg_caerness_regression_test.py`. Expected: PASS.
- [ ] **Step 6: Commit** `refactor(engine): schema 117, outfit tables become organisation tables`.

---

### Task C2: Role rules from data; the generic seat and roster

**Files:**
- Create: `engine/orgs.py`, `engine/org_money.py`, `worlds/saintjude/orgs.json`, `tests/org_core_fixture.py`
- Modify: `engine/world_package.py` (`org_rules`), `worlds/saintjude/world.json` (`data.orgs`), `engine/outfits.py`, `engine/outfit_money.py`, `engine/outfit_opening.py`, `engine/law_opening.py` (callers), `engine/simulation.py:300` (import from `orgs`), `engine/household_life.py`, `engine/role_experience.py`
- Test: `tests/org_core_test.py`

**Interfaces:**
- `orgs.json` shape (open data; the Saint Jude values come from the current code's behaviour):

```json
{
  "kinds": {
    "family":  {"sphere": "underworld", "head": "boss", "unit_leader": "capo",
                "purse_roles": ["capo"], "labels": {"capo": "Capo", "...": "..."},
                "inducted_label": "made", "courtship_scan": false},
    "club":    {"sphere": "underworld", "head": "president", "unit_leader": null, "...": "..."},
    "banks":   {"...": "..."}, "handful": {"...": "..."}, "loyalties": {"...": "..."}
  },
  "flows": ["take", "associate_earning", "kickup", "executive_share", "pad"],
  "arrangement_kinds": {"envelope": {"flow": "pad"}}
}
```

  One entry per `shape` used in `outfits.json`. For non-family shapes, `head` is the first key of the outfit's `ranks` (today's `_top_rank`) and `unit_leader` is whatever role the current opening makes crew leader (null when none).
- `world_package.org_rules(pkg) -> dict` (data key `orgs`; `{}` when absent).
- `engine/orgs.py` (moved from `outfits.py` and renamed; the sphere-free half):
  - `kind_rules(conn, org_actor_id) -> dict`: that org's `kinds` entry via `org_profiles.org_kind`; `{}` when none.
  - `seat(conn, actor_id, org_actor_id, role_key, *, unit_id, superior_actor_id, level, day, inducted_day=None, standing=0.0, provenance="opening") -> int`: was `outfits.add_member`. Returns the seat id. The membership `role_text` comes from `labels[role_key]` and the org name, not `capitalize()`. The person's level is `max(level of his active seats)`.
  - `seat_of(conn, actor_id, org_actor_id) -> Row | None`, `seats_of(conn, actor_id) -> list[Row]`, `members(conn, org_actor_id, role_key=None, status="active")`, `superior_of(conn, actor_id, org_actor_id)`.
  - `head_of(conn, org_actor_id) -> int | None`, `unit_leader_of(conn, actor_id, org_actor_id) -> int | None` (replaces `capo_of`: first holder of the kind's `unit_leader` role up the chain), `stand_in_for(conn, actor_id, org_actor_id) -> int | None` (unit leader if alive, else head if alive, else None).
  - `set_level`, `give_personality`, `register_reason_check`, `has_reason_to_choose`, `speed_up`, `add_agenda`, `resolve_agenda`: moved unchanged apart from table names.
- `engine/org_money.py`: `Roster` (was `_Roster`; earner via the kind rules), `line_holder(conn, line_id) -> int` (the earner in the line's holding's org), `post_period(conn, day, days) -> dict[str, float]`, `next_due_day`, `process_due` (moved; posts the flows `outfit_money` declares). `outfit_money` keeps `build_holdings`, `design_pools`, `design_allocation` and the family builders, and re-exports nothing.
- `outfit_opening` writes the `org_profiles` row when it creates each outfit's institution.
- `household_life` courtship exclusion: seats in kinds whose `courtship_scan` is false. `role_experience`: any active seat means no retainer career (generic).
- `law_opening.head_of(conn, outfit_key, spec)` is renamed `outfit_head(…)` so it doesn't collide with `orgs.head_of`.

- [ ] **Step 1: Write `tests/org_core_fixture.py`**: builds a scratch DB on a minimal test package (no Saint Jude data) whose `orgs.json` declares one kind `firm` (`head: "chair"`, `unit_leader: "manager"`, flows `["take","salary"]`) and seats a chair, two managers and four clerks in one firm with one holding and two lines.
- [ ] **Step 2: Write the failing tests** in `tests/org_core_test.py`:

```python
def test_roles_come_from_data():
    assert head_of(conn, firm) == chair and unit_leader_of(conn, clerk1, firm) == manager1

def test_line_passes_to_stand_in():
    kill(clerk1); assert line_holder(conn, clerk1_line) == manager1
    kill(manager1); assert line_holder(conn, clerk1_line) == chair

def test_kind_without_unit_leader():
    kind with unit_leader null: kill(member) -> line_holder == head; kill(head) too -> RuntimeError("no live earner"), and post_period skips the line without raising

def test_two_seats_two_stand_ins():
    seat clerk1 also as a member of a second firm (level 4 there, 3 in the first) -> his simulation tier is ACTIVE
    kill(clerk1) -> each firm's line goes to that firm's stand-in

def test_non_outfit_seat_gets_the_quiet_routine():
    a clerk has quiet_routine=1; add_agenda(clerk) -> forced ACTIVE until due+7; has_reason_to_choose True on due day

def test_core_has_no_sphere_words():
    for f in CORE_FILES: assert no match of r"\b(boss|underboss|consigliere|capo|soldier|associate|made|president|banker|pad)\b" outside comments and docstrings
```

- [ ] **Step 3: Run**. Expected: FAIL.
- [ ] **Step 4: Implement**: move the code, add the kind rules, replace every rank literal in `outfit_money`/`outfits` with `kind_rules` lookups, write `orgs.json`.
- [ ] **Step 5: Run** this test and the C1 Step 5 list. Expected: PASS, and one period's `take` and `kickup` sums match `org_refactor_baseline.json` within $1.
- [ ] **Step 6: Commit** `refactor(engine): organisation roles come from package data`.

---

### Task C3: Arrangements with officials (the Pad, generalised)

**Files:**
- Modify: `engine/org_money.py` (`post_arrangements`), `engine/outfit_money.py` (drop `_post_pad`), `engine/law_opening.py` (`_build_pad` writes `org_arrangements`), `worlds/saintjude/law.json` (`pad.arrangement_kind: "envelope"`)
- Test: `tests/org_arrangements_test.py`

**Interfaces:**
- `org_money.add_arrangement(conn, *, kind, payer_kind, payer_id, official_actor_id, weekly_usd, day, go_between_actor_id=None, position_key="") -> int`.
- `org_money.post_arrangements(conn, day, days, roster) -> float`: each active arrangement pays `weekly_usd * days / 7`, using the money kind given by `arrangement_kinds[kind].flow`. An org payer pays from its `purse_roles` holders, weighted by the take their units posted this period (today's capo weighting). A person payer pays from his own purse. Each payment goes through the go-between when there is one (payer to go-between to official, two rows, as now). The return value is the total paid to officials.
- `post_period` calls it in place of `_post_pad`; the year-net test from task 7 is unchanged.

- [ ] **Step 1: Write the failing tests:**

```python
def test_pad_totals_unchanged():                    # Saint Jude opening
    one period's sum of org_money kind 'pad' to officials == org_refactor_baseline.json "pad" (within $1)

def test_person_pays_an_official():                  # org_core_fixture
    add_arrangement(kind="envelope", payer_kind="actor", payer_id=chair, official_actor_id=inspector, weekly_usd=50)
    post_period(28 days) -> one org_money row chair -> inspector of 200 and a matching ledger economic_flows row

def test_arrangement_needs_a_live_payer():
    kill(chair) -> the arrangement posts nothing and is marked status 'lapsed'
```

- [ ] **Step 2: Run**. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** this test, `saintjude_law_opening_test.py`, `saintjude_outfit_money_test.py`. Expected: PASS.
- [ ] **Step 5: Commit** `refactor(engine): the Pad is one kind of arrangement with an official`.

---

## Section B: mob tasks 10–16, amended

Each task keeps its original content in the mob-minimum plan. The changes below are binding. Throughout, read `outfit_ranks` as `org_seats`, `rank_key` as `role_key`, `crew` as `unit`, `made_day` as `inducted_day`, `pad_envelopes` as `org_arrangements`, `capo_of`/`boss_of` as `unit_leader_of`/`head_of`, and `outfits.add_agenda` etc. as `orgs.*`.

### Task B10 (was 10): choices and motives, core plus mob

- Split the files. Generic: `engine/org_motives.py` holds `register_motive`, `pressure`, `weekly_chance`, `_roll`, with motive lists read from `orgs.json` `kinds[k].motives` or the sphere file (`outfits.json` `motives`, as planned). Generic: `engine/org_choices.py` holds provider `org`, `register_choice(org_kind: str, choice: str, candidate_fn, execute_fn) -> None`, `AGENDA_ACTIONS` with `register_agenda_action(kind, fn)`, and `execute`. Mob: `engine/outfit_choices.py` registers `start_racket`, `seek_permission`, `remove_superior` and the agenda actions for the underworld kinds, and holds the mob motive readers.
- Decision kind is `org_action` (not `outfit_action`) in `engine/decisions.py`.
- `fill_capo_seat` becomes generic `fill_unit_leader` in `org_lifecycle` (see B12), and the mob calls it.
- Added tests:

```python
def test_undeclared_kind_offers_nothing():      # org_core_fixture: a choice registered for "family" is never offered to a firm clerk
def test_toy_kind_choice_round_trip():          # register a "firm" choice with one motive; forced roll -> an org_action decision executes it
```

### Task B11 (was 11): associates' weeks

- Unchanged in substance; it stays mob (`outfit_incidents.py`). It writes `org_incidents` and registers its agenda actions (`respond_incident`, `pay_or_refuse`) through `register_agenda_action`.

### Task B12 (was 12): lifecycle core, being made on top

- New `engine/org_lifecycle.py` (generic, weekly process `org_lifecycle`). It sets `org_seats.status` to dead or held, passes lines through `stand_in_for`, and handles the vacancy hook `on_vacancy(org_kind, fn)`, `fill_unit_leader(conn, unit_id, day)`, the level drop when held over 30 days and the return on release, leaving the life (DORMANT, cadence 180, `quiet_routine=0`, `left_day`), and `mark_for_history`.
- Mob, in `outfit_incidents.py`: `open_books`, `propose_associate`, `induction.father_name_group`, the Pellegrino range rule, associate replacement and standing growth, hidden-line discovery and `discipline`.
- Added test: `test_firm_vacancy_uses_the_generic_path` (org_core_fixture: a dead manager's unit gets a new manager through `fill_unit_leader`; no mob code runs).

### Task B13 (was 13): law response over any crime kind

- `crime_response` also exposes `open_report(conn, *, crime_kind, day, offender_actor_id=None, victim_actor_id=None, location_id=None, public=False, metadata=None) -> int`, so later spheres can file fraud, bribery and bid-rigging without a `harm_incidents` row. Harm-derived reports go through it.
- `law.json` gains matter kinds `bribery` and `fraud` with their agencies per bible Part II 4.5 and 5 (State Commission of Investigation; FBI / Strike Force), evidence thresholds and review days (Design proposals).
- The Pad's protection (`pad_reaches`) is read from `org_arrangements` where the offender is the payer or sits in the paying org.
- `member_arrested` goes to the offender's unit leader and head **in each org where he holds a seat**, via `orgs`.
- Added tests:

```python
def test_bribery_report_reaches_the_right_agency():
    open_report(crime_kind="bribery", offender_actor_id=chair, victim_actor_id=None, ...) -> a case at agency_for(loc, "bribery")
def test_arrest_reaches_every_org_he_sits_in():   # two seats -> agenda member_arrested for both orgs' leaders
```

### Task B14 (was 14): what the GM sees

- `orgs.record_view(conn, actor_id) -> list[dict]`, one entry per active seat: `{"org", "sphere", "role" (label), "unit_leader", "superior", "years_inducted", "inducted_label", "lines", "standing_words", "custody", "history_due", "history_reasons"}`. The lookup shows it as `"organisations"`; the scene's people include it the same way. Tests as planned, reading `out["organisations"][0]`; add `test_two_seats_both_shown`.
- The rulebook line refers to `organisations[].history_due`.

### Task B15 (was 15): five years

- Rename the table names in the assertions to `org_*`; "every active member has an active superior" becomes "every active seat that is not its kind's head has an active superior in the same org (kinds with no hierarchy excepted by `orgs.json` `flat: true`, e.g. Brigades)".
- Add: `org_lifecycle` and `crime_response` fired at least once each; no `org_money.kind` outside `orgs.json` `flows`.

### Task B16 (was 16): ship

- `AGENTS.md` says schema 117 and points to this plan and the three-spheres spec as the current stream. The Saint Jude line names the next work: the **business layer** (its own spec, then plan).

---

## Self-review notes

- Spec §5.1 core items map to: tables C1; kinds, seats, units, roles C2; income lines C1/C2; flows C2; arrangements C3; agenda and rhythm C2; incidents C1/B11; motives B10; law response B13. §5.3 order: Section A, then B. Business and politics are out of scope by design (spec §5.2, own plans later).
- `inducted_day` replaces the spec's "metadata_json" suggestion for made day. It is one generic column (made, partner, sworn in), so it keeps the queries simple. This is my call.
- Seats are keyed per (person, org), not per person. The spec implied it (shared people across spheres) but did not say it. This is my call, and Review Focus 1 pins it.
