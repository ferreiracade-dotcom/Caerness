# Saint Jude Mob Minimum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One connector serves both worlds, and Saint Jude's families, gangs, Pad and police exist as people who earn, choose, fight and get arrested.

**Architecture:** World switching lives in `connector/` (campaign selection on `resume`). Everything else is package-driven engine code switched on by a new package system key `outfits`: opening builders that pull people up from the background population, a money module that splits the bible's pools into holdings, crew slices and soldier lines, a decision provider for outfit members, an incident sweep, and a crime-response process that reads `harm_incidents`. Saint Jude values live only in `worlds/saintjude/outfits.json`, `law.json`, `design_figures.json` and `names.json`.

**Tech Stack:** Python 3.13, SQLite, numpy (already required). Tests are standalone scripts (`tests/*_test.py`) run by `tools/run_suite.py`, each in its own process with its own scratch DB.

**Spec:** `docs/superpowers/specs/2026-10-24-saintjude-mob-minimum-design.md` (read it first; this plan argues from it). Also read `AGENTS.md`.

## Global Constraints

- Python: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe"`. Always simulate on a copy: tests build into a temp dir; never write `data/*.db` except in Task 16.
- **No Saint Jude values in `engine/` or `connector/`**: no family, gang, place, rank-title or dollar figure literals. They come from package data. The `step1_diff.md` grep rule applies to every diff.
- New engine behaviour runs only when `system_enabled(conn, "outfits")`; a Caerness campaign must behave exactly as before (`tools/run_suite.py` green; `tests/world_pkg_caerness_regression_test.py` green).
- Schema: one migration, **116**, in `engine/db.py` (`SCHEMA_VERSION = 116`), tables also in `engine/schema.sql` with `IF NOT EXISTS`.
- Determinism: every random draw uses `random.Random(f"{design.run_seed(conn)}:{stream}:{key}")`. Same run seed, same opening and same run.
- Every number not taken from the bible is a figure in `design_figures.json` with `"mark": "Design proposal"` and either a `source` or `"note": "unsourced"`. No silent constants.
- Sex shares (spec §3): made men, Brigades, Horsemen (members, prospects), Russians 100% male; Italian associates and other gang roles 99.5%; numbers bankers, controllers, bolita runners 99%; Pad officers 99%.
- Levels: 4 = daily (`cadence_days` 1), 3 = weekly (`cadence_days` 7). The routine "carry on" choice writes no `decisions`, `decision_evaluations` or `decision_candidate_audit` row.
- Pulling up: a new active person always comes from `background_person_profiles` via `person_ecology`; never `INSERT INTO actors` directly for a person in outfit code.
- Commit after each task. Do not push. Sonnet subagents implement; an Opus reviewer checks each task's diff.

## Review Focus

1. **A Caerness campaign resumed after a Saint Jude one** must load its own package, bible index and rulebook (no cached `WorldPackage`, connection or bible from the other world). Test in Task 1 (`test_round_trip_keeps_each_world`).
2. **A man pulled up twice** (incident, then arrest) must stay one actor with one background link, not two. Test in Task 4 (`test_pull_up_is_idempotent_per_profile`).
3. **Dead or jailed men in the money flow:** a line whose holder died or is held must not credit a dead man or break the kick-up chain; the line passes to the crew's capo until reassigned. Test in Task 7 (`test_dead_holder_line_goes_to_capo`).
4. **A capo killed while his own capo seat is the only one in a two-capo family:** the minimum-two rule must refill from the crew without leaving soldiers without a superior. Test in Task 11 (`test_capo_killing_refills_seat_and_reparents_crew`).
5. **The player's attack with no offender metadata** (older saves, other code paths) must still produce a crime report with `offender_actor_id` NULL and an open investigation, not a crash. Test in Task 13 (`test_harm_without_offender_opens_investigation`).

---

## File Structure

| File | Responsibility |
|---|---|
| `connector/campaign.py` | Campaign per world, switch, last-played memory |
| `connector/server.py`, `connector/session.py` | `resume(world=None)`; world-neutral instructions |
| `connector/views.py` | A person's place in the life, shown to the GM |
| `connector/backup.py`, `deploy/caerness-backup.service`, `deploy/update.sh` | Back up every campaign; ship the Saint Jude opening |
| `engine/db.py`, `engine/schema.sql` | Migration 116 |
| `engine/world_package.py` | `outfits` system key, `outfit_rules(pkg)`, `law_rules(pkg)` |
| `engine/design.py` | public `run_seed(conn)` |
| `engine/person_ecology.py` | `name_group` filter, batch pull-up |
| `engine/outfits.py` | Shared: ranks, crews, levels and rhythm, agenda |
| `engine/outfit_opening.py` | Families and other gangs at the opening |
| `engine/outfit_money.py` | Holdings, crew slices, lines, monthly posting, Pad payments |
| `engine/law_opening.py` | Jurisdictions, agencies, officials, Pad officers and envelopes |
| `engine/outfit_choices.py` | Decision provider and outfit actions |
| `engine/outfit_incidents.py` | Associate sweep, far-off sparks, books opening |
| `engine/crime_response.py` | Crime reports, cases, arrests, custody |
| `engine/simulation.py`, `engine/decisions.py`, `engine/activation.py` | Wiring |
| `engine/free_operation.py`, `engine/player_operations.py` | Offender and publicness on player attacks |
| `worlds/saintjude/outfits.json`, `law.json` (new); `world.json`, `design_figures.json`, `names.json` | Package data |
| `tests/sj_fixture.py` | Builds one Saint Jude opening per test process |

---

### Task 1: One connector, both worlds

**Files:**
- Modify: `connector/campaign.py`, `connector/server.py`, `connector/session.py`, `connector/run_server.py`, `connector/backup.py`
- Modify: `deploy/caerness-backup.service`, `deploy/update.sh`
- Test: `tests/connector_world_switch_test.py`

**Interfaces:**
- Produces:
  - `campaign.campaign_name_for(world: str) -> str` — `"main"` for `caerness`, else the package id.
  - `campaign.switch_to(world: str) -> Path` — validates the package, `open_campaign(campaign_name_for(world), package=world)`, records it as last played; returns the db path.
  - `campaign.last_played() -> str | None` / `campaign.remember_last(name: str) -> None` — a plain text file `campaign_dir()/last_campaign`.
  - `campaign.list_worlds() -> list[dict]` — `[{"world": id, "display_name": str, "campaign": name, "exists": bool}]` for every package in `list_packages()`.
  - `server.resume(world: str | None = None) -> dict` — adds `"world"` (display name) and `"other_worlds"` (display names) to the session result.
  - `backup.py --all` snapshots and prunes every `*.db` in `campaign_dir()`.

- [ ] **Step 1: Write the failing tests** in `tests/connector_world_switch_test.py` (temp `CAERNESS_CAMPAIGN_DIR`; Saint Jude opening from `tests/sj_fixture.py`, Caerness from `data/caerness.db` copied by `open_campaign`):

```python
def test_switch_creates_and_resumes_each_world():
    out = server.resume(world="saintjude")
    assert out["world"] == "Saint Jude" and "Caerness" in out["other_worlds"]
    assert Path(os.environ["CAERNESS_DB_PATH"]).name == "saintjude.db"

def test_round_trip_keeps_each_world():
    server.resume(world="saintjude"); sj_day = day_of_current()
    server.advance("c1", 3, "pass time")
    server.resume(world="caerness"); assert package_of_current() == "caerness"
    assert "Caerness" in server.lore("Hearth")["source"]          # Caerness bible, not Saint Jude's
    server.resume(world="saintjude"); assert day_of_current() == sj_day + 3

def test_resume_without_world_uses_last_played():
    server.resume(world="saintjude"); campaign.remember_last("saintjude")
    reset_env_path()                    # simulate a restart
    assert server.resume()["world"] == "Saint Jude"

def test_unknown_world_is_an_error_not_a_switch():
    server.resume(world="saintjude")
    out = server.resume(world="atlantis")
    assert "error" in out and package_of_current() == "saintjude"

def test_instructions_name_every_world():
    assert "Saint Jude" in server.make_mcp().instructions and "Caerness" in server.make_mcp().instructions
```

(`lore`'s actual result key for the source may differ: use whatever field `connector/lore.py` returns that names the bible; the assertion is that the text comes from the Caerness bible.)

- [ ] **Step 2: Run** `CAERNESS_DB_PATH=/tmp/x.db PYTHONPATH=. python tests/connector_world_switch_test.py` — Expected: FAIL (`resume() got an unexpected keyword argument 'world'`).

- [ ] **Step 3: Implement.**
  - `campaign.py`: the functions above. `switch_to` resets `engine.world_package._SWITCH_CACHE` is not needed (it keys on manifest path) but any module-level cache keyed only by package id must be cleared; grep `connector/` and `engine/` for module-level dicts keyed by package id and clear them in `switch_to`.
  - `server.resume(world=None)`: inside `_CALL_LOCK`, if `world` is given call `campaign.switch_to(world)` before `_call`; an unknown package returns `{"error": ...}` without changing `CAERNESS_DB_PATH`.
  - Start-up (`server.main`, `run_server.serve_http`): open `campaign.last_played()` if set, else `settings.campaign`.
  - Instructions and tool docstrings: replace the single world name with all display names from `list_worlds()` joined with " or " (e.g. "Caerness or Saint Jude is the user's text role-playing game…"); `resume`'s docstring says `world` is the world's name and is optional.
  - `session.resume`: add `"world": current_package(conn).display_name` and `"other_worlds"`.
  - `backup.py`: `--all` flag; `deploy/caerness-backup.service` uses `--all`. `deploy/update.sh`: also run `tests/connector_world_switch_test.py` as a smoke test.

- [ ] **Step 4: Run** the new test and `tests/world_connector_test.py`, `tests/world_pkg_caerness_connector_test.py`, `tests/connector_http_test.py`. Expected: all PASS.

- [ ] **Step 5: Commit** `feat(connector): one connector serves every world; resume takes a world`.

---

### Task 2: Deploy world switching to the VM (owner runs)

**Files:**
- Create: `docs/superpowers/plans/2026-10-24-vm-world-switch-runbook.md`

This task writes a runbook; the owner runs it on the VM (the agent has no VM access and the token never enters chat or the repo).

- [ ] **Step 1: Write the runbook** with these steps, as commands:
  1. Back up on the VM: `sudo -u caerness /opt/caerness/.venv/bin/python -m connector.backup --campaign main --label pre-world-switch`.
  2. Rehearsal on a copy: copy the newest snapshot to a scratch dir, run `CAERNESS_CAMPAIGN_DIR=<scratch> python -c "from connector import server; print(server.resume(world='caerness')['world']); print(server.scene().get('error'))"` and an `advance` of 1 day; all must succeed.
  3. `git -C /opt/caerness fetch && git -C /opt/caerness checkout feat/world-packages-saintjude`, then `sudo /opt/caerness/deploy/update.sh`.
  4. `sudo systemctl daemon-reload && sudo systemctl restart caerness-backup.timer`.
  5. On the phone: "resume Caerness" (same scene as before), then "resume Saint Jude" (new campaign, asks for a character).
  6. Rollback: `git checkout feat/claude-connector`, stop `caerness`, `python -m connector.import_campaign <snapshot> --campaign main --replace`, start `caerness`.

- [ ] **Step 2: Commit** `docs: VM runbook for world switching`. Tell the owner the runbook is ready; continue with Task 3 without waiting.

---

### Task 3: Schema 116, package data and switches

**Files:**
- Modify: `engine/db.py`, `engine/schema.sql`, `engine/world_package.py`, `engine/design.py`, `engine/simulation.py:513-519`
- Create: `worlds/saintjude/outfits.json`, `worlds/saintjude/law.json`
- Modify: `worlds/saintjude/world.json`, `worlds/saintjude/design_figures.json`, `worlds/saintjude/names.json`
- Create: `tests/sj_fixture.py`
- Test: `tests/saintjude_outfits_data_test.py`

**Interfaces:**
- Produces:
  - Tables (schema 116):
    - `outfit_crews(id PK, outfit_actor_id, leader_actor_id, label, ground_location_id, status DEFAULT 'active', created_day, ended_day)`
    - `outfit_ranks(actor_id PK REFERENCES actors, outfit_actor_id, rank_key TEXT, crew_id NULL, superior_actor_id NULL, level INTEGER CHECK(level IN (3,4)), joined_day, made_day NULL, standing REAL DEFAULT 0, greed REAL DEFAULT 0.5, reliability REAL DEFAULT 0.5, status TEXT DEFAULT 'active' CHECK(status IN ('active','held','retired','dead','out')), left_day NULL, history_due INTEGER DEFAULT 0)`
    - `outfit_holdings(id PK, outfit_actor_id, pool_key, share_pct REAL, yearly_take REAL, status DEFAULT 'active', source TEXT CHECK(source IN ('opening','started','taken','authored')), started_day, ended_day)`
    - `outfit_lines(id PK, holding_id, crew_id, holder_actor_id, description, location_id NULL, weekly_take REAL, hidden INTEGER DEFAULT 0, status DEFAULT 'active', started_day, ended_day)`
    - `outfit_money(id PK, day, kind CHECK(kind IN ('take','associate_earning','kickup','executive_share','pad')), from_actor_id NULL, to_actor_id, line_id NULL, amount REAL)`
    - `outfit_agenda(id PK, actor_id, kind, due_day, subject_kind NULL, subject_id NULL, status DEFAULT 'open', created_day, resolved_day NULL, metadata_json)`
    - `outfit_incidents(id PK, day, kind, offender_actor_id, victim_actor_id NULL, victim_line_id NULL, location_id NULL, matters INTEGER, raised_to_outfit_actor_id NULL, status, metadata_json)`
    - `pad_envelopes(id PK, officer_actor_id, payer_outfit_actor_id, position_key, weekly_usd REAL, bagman_actor_id NULL, status DEFAULT 'active', started_day, ended_day)`
    - `crime_reports(id PK, day, harm_incident_id UNIQUE NULL, crime_kind, location_id NULL, victim_actor_id NULL, offender_actor_id NULL, public INTEGER, jurisdiction_id NULL, agency_profile_id NULL, case_id NULL, status, metadata_json)`
    - `custody(id PK, actor_id, case_id NULL, agency_profile_id NULL, kind CHECK(kind IN ('held','bailed','released')), charge, since_day, until_day NULL)`
    - `simulation_profiles` gains `quiet_routine INTEGER NOT NULL DEFAULT 0` (ALTER in the migration; guard on column existence).
    - Indexes: `outfit_ranks(outfit_actor_id, rank_key)`, `outfit_ranks(superior_actor_id)`, `outfit_lines(holder_actor_id)`, `outfit_agenda(actor_id, status, due_day)`, `crime_reports(status)`.
  - `world_package.SYSTEM_KEYS` gains `"outfits"`; Saint Jude's `world.json` sets it `true` and adds `"outfits": "outfits.json"`, `"law": "law.json"` to `data`.
  - `world_package.outfit_rules(pkg) -> dict` and `world_package.law_rules(pkg) -> dict` — the parsed files (cached on path and mtime like `gazetteer`), `{}` when absent.
  - `design.run_seed(conn) -> int` — the run seed `draw_all` uses (public wrapper over `_seed_day`).
  - `simulation.SYSTEM_PROCESSES["outfits"] = ("outfit_money", "outfit_incidents", "crime_response")` (the processes are registered in later tasks).
  - `tests/sj_fixture.py`: `build_saintjude(tmp: Path) -> Path` (builds once per process with `tools.build_opening.build_opening(db, package="saintjude")`, then copies per call) and `connect(path) -> sqlite3.Connection` (row factory set).

- [ ] **Step 1: Write `outfits.json`.** Shape (values shown are the ones to use; all non-bible values are also figures in `design_figures.json` as Design proposals, and the JSON refers to them by figure key):

```json
{
  "outfits": {
    "sabatini":   {"institution": "Sabatini Family",   "shape": "family", "made_men_figure": "made_men_sabatini",   "associates_figure": "associates_per_man_sabatini",   "name_group": "italian", "ground": ["<location names from bible Part III 4>"]},
    "pellegrino": {"institution": "Pellegrino Family", "shape": "family", "...": "same keys"},
    "ferrante":   {"institution": "Ferrante Family",   "shape": "family", "...": "same keys"},
    "vannucci":   {"institution": "Vannucci Family",   "shape": "family", "...": "same keys"},
    "brigades":   {"institution": "Charlestown Brigades", "shape": "loyalties", "ranks": {"elder": {"figure": "brigades_elders", "level": 4}, "middle": {"figure": "brigades_middle", "level": 3}, "young": {"figure": "brigades_young", "level": 3}}, "name_group": "irish", "upward": {"kind": "gift_to_elder", "figure": "brigades_gift_share"}},
    "combine":    {"institution": "The Eastside Combine", "shape": "banks", "ranks": {"banker": {"figure": "combine_bankers", "level": 4}, "controller": {"figure": "combine_controllers", "level": 3}}, "name_group": "black", "upward": {"kind": "bank_net_to_banker"}},
    "horsemen":   {"institution": "Iron Horsemen MC", "shape": "club", "ranks": {"president": {"count": 1, "level": 4}, "officer": {"figure": "horsemen_officers", "level": 4}, "member": {"figure": "horsemen_members", "level": 3}, "prospect": {"figure": "horsemen_prospects", "level": 3}}, "upward": {"kind": "dues", "figure": "horsemen_dues_share"}},
    "russians":   {"institution": "The Russians of Brighton Point", "shape": "handful", "ranks": {"senior": {"count": 1, "level": 4}, "man": {"figure": "russians_men_minus_senior", "level": 3}}, "name_group": "soviet_jewish_emigre"},
    "bolita":     {"institution": "The Puerto Rican Blocks", "shape": "banks", "ranks": {"banker": {"figure": "bolita_bankers", "level": 4}, "runner": {"figure": "bolita_runners", "level": 3}}, "name_group": "puerto_rican_latino"}
  },
  "family_ranks": ["boss", "underboss", "consigliere", "capo", "soldier", "associate"],
  "executive_ranks": ["boss", "underboss", "consigliere"],
  "seed_role_to_rank": {"Boss": "boss", "Underboss": "underboss", "Consigliere": "consigliere", "Capo": "capo", "Soldier": "soldier", "Associate": "associate"},
  "male_share": {"made": 1.0, "loyalties": 1.0, "club": 1.0, "handful": 1.0, "associate": 0.995, "banks": 0.99, "pad_officer": 0.99},
  "cadence_days": {"4": 1, "3": 7},
  "executive_share_of_boss_receipts": "executive_share",
  "induction": {"father_name_group": "italian", "vouch_required": true},
  "motives": "added in Task 10 and Task 11",
  "line_kinds": {"numbers_it": "a numbers route", "bookmaking": "a book", "cards_dice": "a card game", "loansharking": "a loan book", "protection": "protection on the shops", "...": "one short phrase per non-cost pool"}
}
```

`ground` lists must name rows in the Saint Jude `locations` table (read bible Part III 4 and `gazetteer.json`; pick at least two per family). `Associate` capitalisation in `seed_role_to_rank` matches the start of `institution_memberships.role_text` ("Capo in the …" maps by first word).

- [ ] **Step 2: Add the Design-proposal figures** to `design_figures.json` (each `{"default", "range", "unit", "tag": "Design", "kind": "fixed" or "draw", "mark": "Design proposal", "source" or "note": "unsourced"}`):
  `brigades_elders` 6, `brigades_middle` 14, `brigades_young` 30, `brigades_gift_share` 0.1; `combine_bankers` 6, `combine_controllers` 24; `horsemen_officers` 4, `horsemen_members` 25 (source Part V 6: 20 to 40), `horsemen_prospects` 20, `horsemen_dues_share` 0.1; `russians_men_minus_senior` 6; `bolita_bankers` 3, `bolita_runners` 9; `executive_share` 0.25 (each of underboss and consigliere gets this share of the boss's receipts); `homicide_honest_share` 0.6; `bail_days` 3; `case_review_days` 14; `case_close_days` 90; `pad_captain_weekly_usd`, `pad_sergeant_weekly_usd`, `pad_patrolman_weekly_usd` chosen so the derived mean equals `pad_mean_envelope_usd_year`/52 at `pad_officers` (write the derivation as a `derived` figure `pad_envelope_mean_check` with `tol` 1.0).

- [ ] **Step 3: Write `law.json`**: `jurisdictions` (city, Killbuck County, Marsh County, state, federal) each with `authority_kind`, `priority`; `agencies` (SJPD and its precincts, county prosecutors, State AG, FBI, Strike Force, US Attorney) each `{"institution": name, "jurisdiction": key, "pad_reaches": bool, "capacity", "integrity"}` (state and federal `pad_reaches: false`, source Part II 3.4); `rules` per matter kind (`homicide`, `assault`, `robbery`, `racket`) with `evidence_threshold`; `pad_limits`: `{"public_killing_forces_arrest": true, "killed_officer_all_agencies": true, "new_commander_reopens": true, "honest_homicide_figure": "homicide_honest_share", "source": "Part II 3.4"}`; `level4_offices` (the Open-slot keys: `office:sjpd:police-commissioner`, `office:sjpd:chief-of-department`, `office:county-prosecutor:killbuck-county-prosecutor`, `office:marsh-county-prosecutor:marsh-county-prosecutor`, `office:fbi-field-office:special-agent-in-charge-fbi`, `office:strike-force:strike-force-chief`, `office:us-attorney:u-s-attorney`, `office:state:state-attorney-general`, `office:state:medical-examiner`, `office:city-hall:mayor`, `office:local-402:president-of-local-402`) and `level4_roles` (no slot: chief of detectives, head of the Organized Crime Control Division, one captain per precinct on family ground, aldermen of the mob wards, president of each Part IV 2.7 local, each `{"institution", "role_text", "occupation_domain"}`).

- [ ] **Step 4: Expand `names.json`** groups `italian` (to at least 80 family and 50 male given names), `irish` (40/30) and `black` (40/30), keeping the existing names and weights' group totals; add `"family_source"`/`"male_source"` notes saying "expanded 2026-10-24 from common US surnames of the community, recalled; assumption".

- [ ] **Step 5: Write the failing test** `tests/saintjude_outfits_data_test.py`:

```python
def test_schema_116_tables_exist():
    assert {"outfit_ranks","outfit_crews","outfit_holdings","outfit_lines","outfit_money","outfit_agenda",
            "outfit_incidents","pad_envelopes","crime_reports","custody"} <= tables(conn)
    assert "quiet_routine" in columns(conn, "simulation_profiles")

def test_outfits_switch_on_for_saintjude_only():
    assert system_enabled(sj, "outfits") and not system_enabled(caerness, "outfits")

def test_every_outfit_institution_and_ground_resolves():
    rules = outfit_rules(package_for(sj))
    for key, o in rules["outfits"].items():
        assert actor_named(sj, o["institution"]), key
        for place in o.get("ground", []): assert location_named(sj, place), (key, place)

def test_every_referenced_figure_exists_and_proposals_are_marked():
    for key in referenced_figure_keys(outfit_rules(pkg), law_rules(pkg)):
        f = figures[key]; assert f is not None, key
        if key in NEW_FIGURES: assert f["mark"] == "Design proposal" and (f.get("source") or f.get("note"))

def test_pad_envelope_tiers_average_to_the_derived_mean():
    assert abs(figure(sj, "pad_envelope_mean_check") - figure(sj, "pad_mean_envelope_usd_year") / 52) <= 1.0

def test_italian_names_cover_the_families():
    g = names["groups"]["italian"]; assert len(g["family"]) >= 80 and len(g["male"]) >= 50

def test_no_saintjude_literals_in_engine():
    assert grep_engine(["Sabatini","Pellegrino","Ferrante","Vannucci","Brigades","Combine","Horsemen","Kerrytown"]) == []
```

- [ ] **Step 6: Run** it — Expected: FAIL on the first test.
- [ ] **Step 7: Implement** migration 116, the loaders, `run_seed`, the system key and `sj_fixture.py`.
- [ ] **Step 8: Run** the test, `tests/saintjude_design_figures_test.py`, `tests/world_package_loader_test.py`, `tests/names_same_group_test.py`. Expected: PASS.
- [ ] **Step 9: Commit** `feat: schema 116 and outfit package data for Saint Jude`.

---

### Task 4: Pulling up by name group, in batches

**Files:**
- Modify: `engine/person_ecology.py:429-603`
- Test: `tests/person_pull_up_group_test.py`

**Interfaces:**
- Consumes: `world_package.package_for(conn).name_groups`.
- Produces:
  - `find_background_candidate(..., name_group: str | None = None)` and `resolve_background_person(..., name_group: str | None = None)` — when set, only profiles whose `family_name` is in that group's `family` list qualify.
  - `resolve_background_people(conn, n: int, *, reason: str, demand_kind: str, subtype: str | None, location_id: int | None, min_age: int, max_age: int, demographic_sex: str | None, name_group: str | None, criminal_weight: float = 0.0, pick_seed: str) -> list[int]` — returns up to `n` actor ids, growing the reservoir in batches; returns fewer only on genuine scarcity. One query per growth batch, not per person.

- [ ] **Step 1: Write the failing tests:**

```python
def test_name_group_filter_only_returns_that_group():
    ids = resolve_background_people(conn, 50, reason="t", demand_kind="t", subtype=None, location_id=city,
                                     min_age=18, max_age=60, demographic_sex="male", name_group="italian", pick_seed="t")
    assert len(ids) == 50 and all(surname(i) in ITALIAN_FAMILY for i in ids)

def test_each_pulled_person_has_one_link_and_conserves_the_sample():
    before = unlinked_profiles(conn); ids = resolve_background_people(conn, 30, ...)
    assert unlinked_profiles(conn) == before - 30 + grown_profiles(conn)   # growth adds real sample, pulling removes one each
    assert all(link_count(conn, i) == 1 for i in ids)

def test_pull_up_is_idempotent_per_profile():
    ids = resolve_background_people(conn, 5, ...); again = resolve_background_people(conn, 5, ...)
    assert not set(ids) & set(again)

def test_batch_is_fast():
    t = time.time(); resolve_background_people(conn, 1200, ..., name_group="italian"); assert time.time() - t < 15
```

- [ ] **Step 2: Run** — Expected: FAIL (`unexpected keyword argument 'name_group'`).
- [ ] **Step 3: Implement.** The batch function reuses the existing row-insert code of `resolve_background_person` (extract it as `_link_profile_as_actor(conn, profile, *, reason, demand_kind, subtype, name) -> int`) so single and batch pull-ups write identical rows.
- [ ] **Step 4: Run** the test and `tests/saintjude_population_test.py`, `tests/family02_sex_resolution_test.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(people): pull up by name group and in batches`.

---

### Task 5: Families at the opening

**Files:**
- Create: `engine/outfits.py`, `engine/outfit_opening.py`
- Modify: `engine/activation.py` (call `outfit_opening.build(conn)` at the end of `activate_existing_loops` when `system_enabled(conn, "outfits")`)
- Test: `tests/saintjude_families_opening_test.py`

**Interfaces:**
- Consumes: Task 3 tables and loaders; Task 4 `resolve_background_people`; `facts.fill_open`; `relationships.ensure_relationship`.
- Produces (`engine/outfits.py`):
  - `members(conn, outfit_actor_id: int, rank_key: str | None = None, status: str = "active") -> list[sqlite3.Row]`
  - `superior_of(conn, actor_id: int) -> int | None`; `capo_of(conn, actor_id: int) -> int | None`; `boss_of(conn, outfit_actor_id: int) -> int | None`
  - `set_level(conn, actor_id: int, level: int, day: int) -> None` — writes `outfit_ranks.level` and the actor's `simulation_profiles` row: `tier` `'ACTIVE'` for 4, `'STRATEGIC'` for 3, `cadence_days` from `outfit_rules["cadence_days"]`, `quiet_routine=1`, `next_review_day = day + cadence`.
  - `add_member(conn, actor_id, outfit_actor_id, rank_key, *, crew_id, superior_actor_id, level, day, made_day=None, standing=0.0) -> None` — also writes `institution_memberships` (role text "<Rank> in the <institution name>") and the personality (Step 3).
- Produces (`engine/outfit_opening.py`): `build(conn) -> dict[str, int]` (counts by outfit and rank), `build_families(conn, day) -> dict`.

- [ ] **Step 1: Write the failing tests** (on a fresh `sj_fixture` opening):

```python
def test_made_men_and_associates_match_drawn_figures():
    for fam in FAMILIES:
        made = count(rank in ("boss","underboss","consigliere","capo","soldier"))
        assert made == round(figure(conn, f"made_men_{fam}"))
        assert abs(count("associate") - round(made * figure(conn, f"associates_per_man_{fam}"))) <= 1

def test_capo_rule():
    for fam in FAMILIES:
        assert count("capo") == max(2, ceil(made(fam) / 8))   # capo_one_per_men, capo_minimum_per_family

def test_structure_is_complete():
    assert every soldier and capo has crew_id and a capo superior (a capo's superior is the boss)
    assert every associate has a superior whose rank is soldier or capo in the same family
    assert every crew has exactly one leader of rank capo

def test_seeded_examples_hold_their_seats():
    assert rank_of("Carmine Sabatini") == "boss" and rank_of("Lorenzo DeLuca") == "capo"
    assert rank_of("Johnny Drago") == "associate" and rank_of("Carlo Spatafore") == "soldier"
    assert no family has two bosses, two underbosses or two consiglieres

def test_levels_and_rhythm():
    assert all executives and capos are level 4 with cadence_days 1 and quiet_routine 1
    assert all soldiers and associates are level 3 with cadence_days 7 and quiet_routine 1

def test_all_made_men_are_male_and_italian():
    assert all made men have demographic_sex 'male' and an italian-group family name
    assert share_male(associates) >= 0.99

def test_feelings_toward_superior_exist():
    assert every made man and associate has a relationships row toward his superior

def test_opening_is_deterministic():
    assert fingerprint(build twice with the same run seed, tables outfit_*) is identical
```

- [ ] **Step 2: Run** — Expected: FAIL (no rows in `outfit_ranks`).
- [ ] **Step 3: Implement `build_families`.** Per family: read made-men count `round(figure(made_men_<fam>))` and ratio; place seeded members first by `seed_role_to_rank` (first word of `role_text`); fill missing executive seats by pulling up (age 50-75, level 4); capos `max(capo_minimum_per_family, ceil(made / capo_one_per_men))`, seeded capos count toward it, others pulled up from the family's soldiers-to-be (age 38-65); soldiers pulled up (age 25-65, `criminal_weight=1.0`, name group from the outfit), dealt to crews round-robin by seeded order; associates pulled up (age 17-45, sex by `male_share["associate"]`, name group 80% the outfit's, 20% drawn from the city's groups by weight), each under a seeded soldier or capo of one crew. Each crew gets `ground_location_id` from the family's `ground` (seeded). Personality: `actor_drives` row with ambition, loyalty, aggression (temper), risk_tolerance (1 − caution) each `clamp(gauss(0.5, 0.18))`; `outfit_ranks.greed` and `reliability` the same way; `made_day` = joined minus a seeded 0 to (age − 25) years for made men; `standing` for associates `clamp(gauss(0.3, 0.2))`. Relationship toward superior: `ensure_relationship(man, superior, day, loyalty=…, respect=…, resentment=…)` from `gauss(30, 20)`, `gauss(30, 20)`, `gauss(10, 15)`. Seeded executives whose seats are Open slots in `world_facts` are recorded with `facts.fill_open`.
- [ ] **Step 4: Run** the test, then `tests/saintjude_snapshot_test.py` and `tests/saintjude_leak_scan_test.py`. Expected: PASS. Note the opening time printed by the fixture.
- [ ] **Step 5: Commit** `feat(saintjude): the four families as people at the opening`.

---

### Task 6: The other gangs at the opening

**Files:**
- Modify: `engine/outfit_opening.py` (add `build_other_outfits(conn, day) -> dict`, called from `build`)
- Test: `tests/saintjude_gangs_opening_test.py`

**Interfaces:**
- Consumes: Task 5 `add_member`, `set_level`; `outfit_rules`.
- Produces: outfit members for every `shape` other than `family`; Brigades members have no `superior_actor_id` (loyalties, not a roster) but each young man has a relationship toward one elder or middle man ("got him the job").

- [ ] **Step 1: Write the failing tests:**

```python
def test_counts_per_rank_match_figures():
    for key, o in outfits.items():
        if o["shape"] == "family": continue
        for rank, r in o["ranks"].items():
            want = r.get("count") or round(figure(conn, r["figure"]))
            assert count(o, rank) == want, (key, rank)

def test_seeded_gang_people_keep_their_places():
    assert rank_of("Declan Gallagher") == "elder" and rank_of("Roy Pike") == "president"
    assert rank_of("Walter Pettiford") == "banker"

def test_brigades_have_no_chain_of_command():
    assert all(r["superior_actor_id"] is None for r in members(brigades))
    assert every young man has a relationships row toward an elder or middle man

def test_sex_shares():
    assert all male for brigades, horsemen, russians; share_male(combine + bolita) >= 0.98

def test_no_chinatown_or_cuban_outfit_rows():
    assert no outfit_ranks row for the Docks Chinatown Associations institution
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** with the same pull-up and personality code as Task 5 (shared helper in `outfit_opening.py`, not copied); `banks` shape: controllers and runners get a banker superior; `club`: officers under the president, members and prospects under an officer; `handful`: men under the senior man.
- [ ] **Step 4: Run** the test and the Task 5 test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(saintjude): the other gangs as people at the opening`.

---

### Task 7: Rackets: holdings, crew slices, lines and the monthly flow

**Files:**
- Create: `engine/outfit_money.py`
- Modify: `engine/outfit_opening.py` (`build` calls `outfit_money.build_holdings(conn, day)`), `engine/simulation.py` (register `outfit_money` process in block A after `law`), `engine/ledger.py` (public `receive`)
- Test: `tests/saintjude_outfit_money_test.py`

**Interfaces:**
- Consumes: `design_figures.json` `pools` (skip pools with `"kind": "cost"`), `allocation.family_gross_net_9_3`, ladder figures, `living_associate`, `executive_share`; Task 5 roster helpers.
- Produces:
  - `ledger.receive(conn, dst: Holder, amount: float, *, purpose: str) -> float` — money entering a purse from outside the ledger's holders (a racket's victims); credits and returns the amount.
  - `outfit_money.build_holdings(conn, day) -> dict[str, float]` — family gross by outfit key.
  - `outfit_money.next_due_day(conn, after_day, end_day) -> int | None` and `outfit_money.process_due(conn, day, *, event_logger=None) -> dict` — posts every 28 days from the opening day.
  - `outfit_money.post_period(conn, day, days: int) -> dict[str, float]` — the posting itself (tests call it directly).
  - `outfit_money.line_holder(conn, line_id) -> int` — the live earner (the capo when the holder is dead, held or out).

- [ ] **Step 1: Write the failing tests:**

```python
def test_holdings_sum_to_family_gross():
    for fam in FAMILIES:
        g = sum(h["yearly_take"] for h in holdings(fam))
        assert abs(g / 1e6 - alloc[fam]["gross_m"]) <= alloc_gross_tolerance_m      # 0.1

def test_crew_slices_and_lines_add_up():
    for h in all_holdings(): assert abs(sum(l["weekly_take"] * 52 for l in lines(h)) - h["yearly_take"]) < 1.0
    assert every soldier and capo holds at least one line, with a description and a location

def test_money_is_conserved_in_a_period():
    before = total_cash(all members); out = post_period(conn, day, 28)
    assert abs((total_cash(all members) - before) - out["take"]) < 0.01        # nothing created inside the outfits
    assert sum(kickups into each man) == sum(kickups recorded out of his juniors)

def test_ladder_shares_apply():
    rows = money_for_one_associate_and_his_soldier()
    assert abs(rows.kickup_to_soldier - rows.associate_earning * figure("ladder_associate_to_soldier")) < 0.01

def test_family_net_over_a_year_matches_9_3():
    run 13 periods; for fam: assert abs(take(fam) - pad_paid(fam) - alloc[fam]["net_m"] * 1e6) / 1e6 <= 0.15

def test_dead_holder_line_goes_to_capo():
    kill(a soldier with a line); assert line_holder(conn, line) == his capo; post_period(...)
    assert no outfit_money row credits the dead man after his death day
```

(`pad` rows appear once Task 8 adds envelopes; until then `pad_paid` is 0 and the year test uses gross: write it for net now and mark it expected-to-fail until Task 8 with a comment naming Task 8.)

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Holding per family per non-cost pool with share > 0: `yearly_take = figure(conn, pool["tie"]["figure"], default=pool["default_m"]) * 1e6 * share/100`.
  - Crew slices: each holding is split among the family's crews with seeded weights (`gammavariate(2, 1)`), doubled for the crew whose seeded "main line" is that pool (one main line per crew).
  - Lines: each crew slice split among that crew's capo and soldiers with seeded weights; every made man gets at least one line (if a crew has more men than slices, the largest slice splits further). Description: `line_kinds[pool]` + " in " + the crew's ground location name; `weekly_take = yearly / 52`.
  - Posting a period of `days`: for each active line, `take = weekly_take * days / 7`; `associate_earning` for each associate under the holder: `living_associate / (1 - ladder_associate_to_soldier) * days / 365 * reliability_factor` (factor `0.5 + reliability`), paid out of the line's take to the associate; associate kicks up `ladder_associate_to_soldier` of it to the holder; the holder kicks up `ladder_soldier_to_capo` of his net to his capo (a capo's own lines count as his regime); the capo kicks up `ladder_capo_to_boss` of regime net to the boss; boss pays `executive_share` of receipts to each of underboss and consigliere. Each movement is one `outfit_money` row per man per period and a `ledger.transfer` (or `ledger.receive` for the take). Brigades: men keep their take, gift `brigades_gift_share` to the elder they are tied to; Combine and bolita: controllers and runners pass bank net to the banker; Horsemen: `horsemen_dues_share` to the president as treasury. (Other outfits' holdings come from their pools: `numbers_claims_m`, `brigades_*_m`, `horsemen_*_m`, `bolita_net_m`; one holding per pool, split to men by seeded weights.)
- [ ] **Step 4: Run** the test (the net-per-year test fails until Task 8, as commented) and the Task 5 test. Expected: PASS otherwise.
- [ ] **Step 5: Commit** `feat(saintjude): rackets split to crews and soldiers, monthly flow up the Ladder`.

---

### Task 8: Law, the Pad and connected people at the opening

**Files:**
- Create: `engine/law_opening.py`
- Modify: `engine/outfit_opening.py` (`build` calls `law_opening.build(conn, day)` after families), `engine/outfit_money.py` (Pad payments in `post_period`)
- Test: `tests/saintjude_law_opening_test.py`

**Interfaces:**
- Consumes: `law_rules(pkg)`; `engine/law.py` `create_jurisdiction`, `add_rule`, `create_office`; Task 4 pull-up; `facts.fill_open`.
- Produces:
  - `law_opening.build(conn, day) -> dict[str, int]`
  - `law_opening.agency_for(conn, location_id: int | None, matter_kind: str, *, federal: bool = False) -> int | None` — a `law_enforcement_profiles.id`.
  - Rows: `law_jurisdictions`, `law_rules`, `law_offices`, `law_enforcement_profiles` (one per agency, `metadata_json.pad_reaches`), level-4 officials (`outfit_ranks` is **not** used for them: their level lives in `simulation_profiles` with `quiet_routine=1`, cadence 1), Pad officers (actors pulled up with occupation domain of police, level 3 cadence 7), `pad_envelopes`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_jurisdictions_and_agencies_loaded():
    assert {"city","killbuck_county","marsh_county","state","federal"} <= jurisdiction_keys(conn)
    assert pad_reaches(agency("FBI Saint Jude Field Office")) is False

def test_level4_offices_filled_once():
    for key in law["level4_offices"]: assert holder(conn, key) is not None
    assert captain exists for every precinct that contains a family crew's ground

def test_pad_officers_and_envelopes_balance():
    assert count(pad officers) == round(figure("pad_officers"))
    assert abs(sum(weekly_usd) * 52 / 1e6 - figure("pad_total_m")) <= 0.05
    for fam: assert abs(sum(weekly_usd paid by fam) * 52 / 1e6 - alloc["pad_by_family_m"][fam]) <= 0.02
    assert every precinct captain on family ground has an envelope larger than any patrolman's
    assert share_male(pad officers) >= 0.98

def test_connected_people_are_level_4():
    for c in outfits["connected"]: assert a level-4 profile (cadence 1, quiet_routine 1) exists for its holder
    assert the Docks Chinatown Associations have level-4 leaders and no outfit_ranks rows
    assert law-side and connected level-4 people together number between 50 and 80

def test_pad_is_paid_in_the_flow():
    out = post_period(conn, day, 28)
    assert abs(out["pad"] - sum(weekly_usd) * 4) < 0.5 and every envelope's officer received money
```

Also remove the "expected to fail until Task 8" comment in Task 7's net-per-year test; it must now pass.

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Add `"connected"` to `outfits.json`**: the bankers, contractors and businessmen the bible ties to the families, Chinatown's leaders, and the Jewish financiers and bookmakers (spec §6.2, §6.3), each `{"institution": name or null, "role_text", "occupation_domain", "tied_to": outfit key or null, "count": n}` from the bible (Part III 5.5, Part IV, Part V 7); where the institution already has a seeded head, that person is used.
- [ ] **Step 4: Implement.** Connected people: pulled up (or the seeded head used), level 4 via `simulation_profiles` (cadence 1, `quiet_routine=1`), an `institution_memberships` row with the role text, and a relationships row toward the boss of `tied_to`. Officials: Open slots filled by pulling up (age 40-65, sex per `male_share["pad_officer"]` for police, otherwise the city's default) and `facts.fill_open(conn, key, aid, "the opening needs a holder")`; `level4_roles` pulled up and given an `institution_memberships` row with the role text. Pad: precincts on family ground; per precinct 1 captain (large envelope), 1 to 2 sergeants as bagmen (medium), the rest patrolmen and detectives (small), until `pad_officers` is reached; tiers from the `pad_*_weekly_usd` figures; payer family by `pad_by_family_m` shares; `position_key` `"<precinct institution id>:<tier>:<n>"`. Payment: in `post_period`, each family's capos pay their Pad share pro rata to their regimes' take, through the bagman, to each officer.
- [ ] **Step 5: Run** this test and Task 7's test. Expected: PASS.
- [ ] **Step 6: Commit** `feat(saintjude): jurisdictions, officials, connected people and the Pad at the opening`.

---

### Task 9: Rhythm: daily, weekly, and quiet routine

**Files:**
- Modify: `engine/simulation.py:248-330` (`_review_actor`), `engine/outfits.py`
- Test: `tests/outfit_rhythm_test.py`

**Interfaces:**
- Consumes: `simulation_profiles.quiet_routine`; `outfit_agenda`.
- Produces:
  - `outfits.register_reason_check(fn: Callable[[sqlite3.Connection, int, int], bool]) -> None` and `outfits.has_reason_to_choose(conn, actor_id, day) -> bool` — true when any registered check returns true (Task 10 registers the trait rolls; this task registers "an open agenda item is due").
  - `outfits.add_agenda(conn, actor_id, kind, due_day, *, subject_kind=None, subject_id=None, metadata=None) -> int` — also calls `speed_up(conn, actor_id, until_day=due_day + 7)`.
  - `outfits.speed_up(conn, actor_id, until_day) -> None` — `forced_tier='ACTIVE'`, `forced_until_day=until_day`, `next_review_day=min(next_review_day, today+1)`.
  - `outfits.resolve_agenda(conn, agenda_id, day) -> None`.
  - `_review_actor` change: when `profile["quiet_routine"]` is 1, cadence is `1` while forced ACTIVE (else the profile's `cadence_days`), and if `not has_reason_to_choose(...)` the actor is rescheduled with no `decide_actor` call and no decision rows.

- [ ] **Step 1: Write the failing tests:**

```python
def test_routine_week_writes_no_decision_rows():
    n = decision_rows(conn); advance(conn, 28); assert decision_rows_for(outfit_members) == 0

def test_agenda_item_makes_a_weekly_man_daily_until_it_passes():
    add_agenda(conn, soldier, "collect_debt", due_day=today + 5)
    reviews = review_days(soldier, advance 14 days)
    assert reviews[:6] == consecutive days and the gap after due_day + 7 is 7

def test_non_quiet_profiles_unchanged():
    caerness opening: advance 30 days twice from copies, one before and one after the change → identical events fingerprint
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the test and `tests/world_pkg_caerness_regression_test.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(engine): quiet routine and agenda-driven rhythm for outfit members`.

---

### Task 10: What a man chooses: motives read from the world

The owner's rule (2026-10-24): no choice hangs on one trait roll. Each choice has **several motives, each read from the man's real situation**, and the world around him changes the odds. Motives are open package data (a named reader function plus its weight figure), so new ones can be added without touching the choice code; the lists below are the minimum, not a closed set.

**Files:**
- Create: `engine/outfit_choices.py`, `engine/outfit_motives.py`
- Modify: `engine/decisions.py` (`candidate_to_proposal` and `apply_decision`: `outfit_action`, following the `merchant_action` pattern), `engine/outfits.py`, `engine/simulation.py` (import `outfit_choices` so its provider registers), `worlds/saintjude/outfits.json` (`motives`), `worlds/saintjude/design_figures.json` (weights and base rates, Design proposals)
- Test: `tests/outfit_motives_test.py`, `tests/outfit_choices_test.py`

**Interfaces:**
- Consumes: Task 7 holdings and lines, Task 8 Pad envelopes and precincts, Task 9 agenda and checks, relationships, `actor_drives`, `outfit_ranks`, `harm.record_harm`.
- Produces (`engine/outfit_motives.py`):
  - `Motive = Callable[[sqlite3.Connection, int, int], float]`: reads state for (actor, day) and returns pressure 0..1. `register_motive(choice: str, name: str, fn: Motive) -> None`.
  - `pressure(conn, actor_id, day, choice: str) -> tuple[float, dict[str, float]]`: combines the package's motives for `choice` as `1 - prod(1 - weight_i * m_i)` (several moderate reasons add up; one strong reason is enough) and returns the parts for the decision's rationale.
  - `weekly_chance(conn, actor_id, day, choice) -> float`: `base_rate(choice) * pressure * temperament_factor(choice)`; base rates and temperament factors are figures.
- **Taking out his capo** (`remove_superior`), minimum motives:
  - `grievance`: resentment toward the capo (insults, beatings, a slight in front of others).
  - `squeezed`: what he kicks up to the capo against the ladder figure (a capo who takes more than `ladder_soldier_to_capo`, or takes his line).
  - `passed_over`: a capo seat or the books went to someone with less standing or fewer years.
  - `blocked_ambition`: his ambition and standing against the capo's age and hold on the crew.
  - `fear`: he believes the capo means to kill him or give him up: an open `hit` or `discipline_hunt` naming him that he could know of (knowledge system or his ties), or the capo held on a homicide charge (who talks).
  - `capo_weak`: the capo is held, sick, losing money or losing ground.
  - `outside_push`: another capo, the underboss or a rival family's man tied to him wants the capo gone.
  - `revenge`: the capo harmed his kin or a close friend (`harm_incidents` with the capo as offender).
  - `boss_wants_it`: the boss's resentment of the capo is above his respect; this also lowers the risk.
  - Two paths, chosen by caution and his tie to the boss: `seek_permission` (an agenda item for the boss: grant, refuse, or warn the capo) or `remove_superior` alone. Fear and `boss_wants_it` push toward acting; caution toward asking.
- **Starting a racket** (`start_racket`); opportunity in his world as much as appetite:
  - `thin_ground`: few lines for the people there: active lines on his crew's ground against the location's population and businesses (and the `protection` table's paying share for its trades).
  - `unclaimed_pool`: a pool share held by no family, or held by a family weak on that ground.
  - `vacancy`: a line on his ground whose holder died or was held, or whose business closed, in the last 90 days; a rival outfit pushed off the ground.
  - `demand`: the pool's trend (numbers falling with Pick-3, sports betting rising, new products and businesses from the dated timeline).
  - `low_heat`: the precinct is on his family's Pad and no open case names him; heat raises the cost.
  - `means`: his cash against a start cost, and associates under him to work it.
  - `need`: his earnings against his living standard (`living_soldier`, `living_associate`) and his debts.
  - `appetite`: ambition and greed, less caution.
  - Associates use the same choice with their own base rate; their start is usually a small line under their soldier, not a family holding.
- Produces (`engine/outfit_choices.py`): provider `outfit` (`[]` for non-members); candidates `hold`, `start_racket`, `seek_permission`, `remove_superior`, plus one candidate set per open agenda item through `AGENDA_ACTIONS: dict[str, Callable]` (this task adds `fill_capo_seat`, `grant_or_refuse`, `discipline_hunt`, `hit`; Tasks 11-13 add the rest; `history` has no action). Utilities come from pressures and temperament; there is no fixed order.
  - `execute(conn, actor_id, kind, payload, day) -> dict`:
    - `start_racket`: picks where by the same readers (the place and pool with the most opportunity on or next to his ground; next to a rival's ground is a fight the rival's boss hears of through Task 11's response); a holding (`source='started'`) and a line sized by the opportunity; he pays the start cost; `hidden=1` when greed outweighs loyalty and caution (seeded roll). A hidden line kicks up nothing; Task 12 handles discovery.
    - `remove_superior` / `hit`: `record_harm(..., outcome_override="fatal", metadata={"offender_actor_id": ..., "public": False})`; the boss gets `fill_capo_seat`; an unsanctioned killing gives him `discipline_hunt` unless `boss_wants_it` > 0.5 (then the killer gains standing); `mark_for_history` for both.
    - `fill_capo_seat`: the crew soldier with the best standing, years made and loyalty to the boss; soldiers re-parent; lines stay with the crew.
- Reason checks registered with Task 9: one weekly roll per choice at `weekly_chance`, seeded by actor, day and choice (single roll point `_roll(conn, actor_id, day, stream) -> float`, patched by tests).

- [ ] **Step 1: Add the motives and figures.** `outfits.json` gains `"motives": {"remove_superior": [{"name": "grievance", "weight": "motive_grievance_w"}, ...], "start_racket": [...]}` with every motive above; `design_figures.json` gains each weight (0.5 to 0.9, Design proposal, unsourced) and `remove_superior_base_week` 0.01, `start_racket_base_week` 0.01, `associate_start_base_week` 0.003 (proposals; the pressure does most of the work).
- [ ] **Step 2: Write the failing tests:**

```python
def test_each_motive_reads_its_situation():
    squeeze(capo takes 30% of the soldier's net)      -> parts["squeezed"] > 0.5
    give a seat to a junior man                        -> parts["passed_over"] > 0.5
    open a hit naming the soldier, known to him        -> parts["fear"] > 0.5
    hold the capo on a homicide charge                 -> parts["fear"] > 0 and parts["capo_weak"] > 0
    boss resentment of capo 80, respect 10             -> parts["boss_wants_it"] > 0.5

def test_reasons_add_up():
    assert pressure(grievance only) < pressure(grievance and squeezed) < 1

def test_racket_chance_follows_the_ground():
    same man, same traits: ground with no lines vs ground thick with lines
    assert weekly_chance(thin) > 3 * weekly_chance(thick)
    a vacancy on his ground raises it; an open case naming him lowers it

def test_racket_lands_where_the_opportunity_is():
    with forced_roll("start_racket"): run_review(soldier)
    assert the new line is on the thin or vacant place and its size follows that place

def test_cautious_man_asks_first():
    caution 0.9, strong grievance -> seek_permission; the boss gets grant_or_refuse

def test_unsanctioned_killing_brings_a_hunt_sanctioned_does_not(): ...
def test_capo_killing_refills_seat_and_reparents_crew(): ...
def test_hidden_racket_kicks_up_nothing(): ...
def test_provider_silent_for_non_members(): ...
```

- [ ] **Step 3: Run**. Expected: FAIL.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run** the tests and Tasks 7 and 9 tests. Expected: PASS.
- [ ] **Step 6: Commit** `feat(saintjude): men choose from motives read from the world`.

---

### Task 11: Associates' weeks, far-off sparks and family responses

Associates are not only a source of trouble. Each week an associate may do something good for himself or the crew, something neutral, or something that goes wrong, each weighed by motives read from his world as in Task 10.

**Files:**
- Create: `engine/outfit_incidents.py`
- Modify: `engine/simulation.py` (register `outfit_incidents`, weekly, block A after `outfit_money`), `engine/outfit_choices.py`, `engine/outfit_motives.py`, `worlds/saintjude/outfits.json`, `design_figures.json`
- Test: `tests/outfit_incidents_test.py`

**Interfaces:**
- Consumes: Tasks 4, 9, 10; relationships between bosses.
- Produces `outfit_incidents.next_due_day / process_due(conn, day, *, event_logger=None) -> dict`: every 7 days, for each active associate, at most one **happening**, its kind chosen by motive pressures (package data, open set):
  - **Good:** `score` (a hijacked load, a tip, a good collection: a one-off take kicked up by the ladder; motives ambition, need, the ground's theft and fence pools, low heat); `bring_earner` (a bookmaker, bar owner or loan customer: a new small line under his soldier, the counterpart pulled up); `proves_himself` (does a `job` agenda item cleanly; standing and his superior's trust rise); `recruits` (a young man pulled up under the same soldier while the crew is below its associate ratio); `favour` (for a made man of another crew; a relationship gain).
  - **Neutral:** `drifts` (earns less, standing falls); `goes_straight` (status `out`; motives age, marriage, a job, fear after an arrest); `switches` (to another soldier or outfit offering more; the old soldier's resentment rises).
  - **Goes wrong:** `incident` (robs the wrong game, hits the wrong man, a fight; victim by weight: another family's line on adjoining ground, a made man, a cop, a big earner, a civilian; `matters=1` unless a civilian); `holds_out` (keeps money back; the soldier may notice each period); `busted` (a small arrest: a crime report with `crime_kind='racket'` for Task 13); `informs` (only with an open case naming him, police pressure and low loyalty; gives the agency evidence on his soldier, a taboo the family reacts to if it learns of it).
- Base rate `associate_happening_week` 0.05 (proposal). At average pressure the mix is roughly good 55%, neutral 25%, wrong 20% (proposals); the situation moves it.
- Good happenings raise `standing` (feeds Task 12's books). A civilian incident stays in his record. A mattering one gives the victim's boss `respond_incident`; a cop victim also becomes a `harm_incidents` row (Task 13).
- `respond_incident` (victim boss): `sit_down` (the offender's boss gets `pay_or_refuse`), `kill_offender`, `let_it_go`. `pay_or_refuse`: `pay` (4 to 12 weeks of the line's take) or `refuse`. Each adjusts the boss-to-boss relationship.

- [ ] **Step 1: Add** the happening kinds, their motives and figures (Design proposals).
- [ ] **Step 2: Write the failing tests:**

```python
def test_good_happenings_raise_standing():
    with forced_happening("bring_earner"): process_due(conn, day)
    assert a new line under his soldier, its counterpart pulled up, and his standing rose

def test_mix_is_mostly_not_trouble():
    365 days on a copy: share(good + neutral) > share(wrong); every kind except informs occurs

def test_informing_needs_pressure():
    no open case, loyalty 0.8 -> chance of informs == 0

def test_civilian_incident_stays_quiet(): ...
def test_far_off_spark_reaches_the_other_family(): ...
def test_response_moves_the_relationship(): ...
def test_noise_is_bounded():   # mattering incidents per year between 5 and 300 (tuning range)
```

- [ ] **Step 3: Run**. Expected: FAIL.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run** the test and Task 10's tests. Expected: PASS.
- [ ] **Step 6: Commit** `feat(saintjude): associates' weeks, good, neutral and bad, reach the families`.

---

### Task 12: Being made, discovery and true counts

**Files:**
- Modify: `engine/outfit_incidents.py` (books, discovery, replacement), `engine/outfit_choices.py` (`open_books`, `propose_associate`, `discipline`)
- Test: `tests/outfit_counts_test.py`

**Interfaces:**
- Consumes: health/life deaths (`actor_life_profiles.life_status`), Task 4 pull-up, Task 10 actions.
- Produces:
  - In the weekly process: members who died or are held for over 365 days get `outfit_ranks.status` `'dead'` / `'held'`; their lines pass to the capo (Task 7 `line_holder`); a dead or departed made man opens a vacancy: the boss gets agenda `open_books` when the family's made count is below its figure.
  - `open_books` (boss): asks each capo for one name; `propose_associate` (capo): the associate in his crew with the best `standing` whose family name is in the induction `father_name_group`; the boss makes him (rank `soldier`, `made_day`, superior the capo); his associates re-parent to him.
  - Associates lost (made, dead, out) are replaced, one by one, by pulling up young men (age 17-30) from the crew's ground with the outfit's name-group mix, at most one a week per crew; `standing` rises weekly by `0.01 * (reliability + ambition)` for associates who earned in the period.
  - Hidden lines: each period the capo has a roll `0.05 * (1 - holder caution)` to discover a hidden line; discovery gives the boss agenda `discipline` with the holder as subject; `discipline` candidates: fine (back kick-up), demote (line taken), kill.
  - The Pellegrino rule: a family whose made count would exceed its figure's range top needs a dated cause; the books do not open above `range[1]`.
  - Moving down (spec §5): a level-4 man held for over 30 days, or whose rank is boss/underboss and who has a seeded `retired` or `delegating` agenda, drops to level 3 (`set_level`); he goes back to 4 on release. A man whose status becomes `out` (left the life) keeps his actor row; his `simulation_profiles` row becomes `DORMANT`, cadence 180, `quiet_routine=0`; his `outfit_ranks` row stays with `left_day`. Nobody's actor row is deleted.
  - `outfits.mark_for_history(conn, actor_id, reason: str) -> None` sets `outfit_ranks.history_due=1` and records the reason in an `outfit_agenda` row of kind `history` (no owner action; Task 14 shows it to the GM). Called when a man rises to level 4, kills or is killed, is made, or is arrested.

- [ ] **Step 1: Write the failing tests:**

```python
def test_death_opens_books_and_an_associate_is_made():
    kill(soldier); advance(conn, 60)
    assert made_count(fam) == figure(made_men_fam) and newest_soldier(fam) was an associate with a record before

def test_counts_add_up_over_a_year():
    advance(conn, 365); for fam: assert made_count(fam) <= round(range_top(made_men_fam))
    assert every active associate and soldier has an active superior in the same outfit

def test_hidden_line_can_be_caught():
    with forced_roll("discover"): post_period(...); assert open_agenda(boss, "discipline")

def test_made_men_come_from_the_italian_group():
    assert all soldiers made during the run have an italian-group family name

def test_held_capo_drops_to_weekly_and_returns():
    hold(capo, days=40); advance(conn, 35); assert level(capo) == 3; release(capo); advance(conn, 7); assert level(capo) == 4

def test_leaving_the_life_keeps_the_record():
    make_out(associate); assert actor_exists(associate) and rank_row(associate)["left_day"] is not None
    assert profile(associate)["tier"] == "DORMANT" and profile(associate)["quiet_routine"] == 0
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the test and Tasks 10-11 tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(saintjude): men are made from associates; counts stay true`.

---

### Task 13: The law response

**Files:**
- Create: `engine/crime_response.py`
- Modify: `engine/simulation.py` (register `crime_response`, daily-due, block A after `outfit_incidents`), `engine/player_operations.py:1132-1134`, `engine/free_operation.py` (attack: `d["public"]`)
- Modify: `tests/saintjude_connector_play_test.py` (case C asserted)
- Test: `tests/crime_response_test.py`

**Interfaces:**
- Consumes: `harm_incidents` (new rows since the last run, `intent_class='hostile'`), `law_opening.agency_for`, `law_rules(pkg)`, `pad_envelopes`, Task 9 `add_agenda`.
- Produces:
  - `player_operations` attack passes `metadata={"offender_actor_id": me, "public": bool(d.get("public")), …existing keys}`; `free_operation` sets `d["public"] = True` when the intent matches `r"broad daylight|in public|publicly|in front of|crowded|witness|on the street"`.
  - `crime_response.next_due_day / process_due(conn, day, *, event_logger=None) -> dict`:
    1. Each new hostile harm row becomes a `crime_reports` row: `crime_kind` `homicide` if fatal else `assault`; `public` from metadata; offender from metadata (may be NULL); the victim's being a police officer (an `institution_memberships` row in a police institution) is recorded.
    2. The case goes to `agency_for(location, kind)` (and also the federal agency when the victim is an officer); a `law_enforcement_cases` row (`subject_kind='actor'`, subject the offender or NULL, `allegation_kind` the crime kind, `metadata_json.crime_report_id`).
    3. Evidence: `0.3 + 0.4*public + 0.2*(offender known)`, seeded noise ±0.1.
    4. Response: if `public` and homicide, or the victim is an officer → **arrest** whatever the Pad (`pad_limits`). Else the case officer is a seeded detective of that precinct (pulled up if none is active); if the agency `pad_reaches` and the officer holds an envelope from the offender's outfit and the roll fails `homicide_honest_share` for homicides → `buried` (status `closed`, `metadata.reason='pad'`); else arrest when evidence ≥ the rule's `evidence_threshold`; else stays open, reviewed every `case_review_days`, closed after `case_close_days`.
    5. Arrest: `custody(kind='held')`; the offender's `outfit_ranks.status='held'`, level-3 rhythm; agenda `member_arrested` for his capo and boss; after `bail_days`, non-homicide charges move to `bailed` and the man is `active` again.
    6. A changed precinct captain (holder of the captain role differs from the envelope's officer) voids that envelope (`status='reopened'`).
    7. `member_arrested` action (capo or boss, in `outfit_choices.execute`): `send_lawyer` (the boss spends a seeded fee; bail comes after `max(1, bail_days // 2)` days) or `wait`; either way the boss's `trust` toward the held man drops by a seeded 0 to 10 when the charge is homicide (a worry about who talks). `mark_for_history` for the held man.

- [ ] **Step 1: Write the failing tests:**

```python
def test_public_killing_brings_an_arrest_despite_the_pad():
    offender on a paying family, victim on paid ground, public=True, fatal → process_due
    assert custody_for(offender)["kind"] == "held" and report.status == "arrest"

def test_routine_assault_on_paid_ground_can_be_buried():
    with forced_roll("honest", 0.99): non-public assault by a paying man, case officer on his family's envelope
    assert report.status == "buried"

def test_federal_case_ignores_the_pad():
    victim an officer → assert a case exists at the FBI profile and an arrest follows

def test_harm_without_offender_opens_investigation():
    record_harm(victim, ..., metadata=None); process_due(...)
    assert report.offender_actor_id is None and case.status in ("monitoring", "open")

def test_family_answers_an_arrest():
    arrest a soldier; run his boss's and capo's reviews for 3 days
    assert a decision row of outfit_action member_arrested exists for the capo or boss

def test_mob_killing_reaches_the_law():
    with forced_roll("kill_superior"): run_review(soldier); process_due(conn, day + 1)
    assert a crime_report exists for the capo's death
```

- [ ] **Step 2: Rewrite case C** in `tests/saintjude_connector_play_test.py`: pick a living rival named actor; `server.act(cid(), "operation", "shoot <name> dead in broad daylight on a crowded Kerrytown street", target_actor_id=<id>)`, then `server.advance(cid(), 2, "lie low")`; assert a `custody` row for the protagonist with `kind='held'`. Drop "REPORT-ONLY" from its name.
- [ ] **Step 3: Run** both tests — Expected: FAIL.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run** the tests and `tests/player_operations_test.py`, `tests/act_freeform_test.py`. Expected: PASS.
- [ ] **Step 6: Commit** `feat(saintjude): crimes bring a law response; the Pad bends it within its limits`.

---

### Task 14: What the GM sees

**Files:**
- Modify: `connector/views.py` (person lookup and scene), `engine/outfits.py`
- Test: `tests/outfit_views_test.py`

**Interfaces:**
- Consumes: Tasks 5-13 tables.
- Produces: `outfits.record_view(conn, actor_id) -> dict | None` — `{"outfit", "rank", "crew_capo", "superior", "years_made", "lines": ["a card game on Mercer Avenue, about $X a week", ...], "standing" (associates, in words: "far from being proposed" / "close"), "custody", "history_due": bool, "history_reasons": [...]}`; `None` for non-members. Amounts in words and round dollars, never raw floats. The person lookup and the scene's people include it as `"in_the_life"`; a hidden line is shown only when the protagonist is the holder or the holder's capo or boss and has discovered it.

- [ ] **Step 1: Write the failing tests:**

```python
def test_lookup_shows_the_record():
    out = server.lookup("<a seeded capo>"); r = out["in_the_life"]
    assert r["rank"] == "capo" and r["lines"] and "$" in r["lines"][0]

def test_non_member_has_no_record():
    assert "in_the_life" not in server.lookup("<a seeded newspaper publisher>")

def test_history_due_is_flagged():
    mark_for_history(conn, soldier, "made"); assert server.lookup(name(soldier))["in_the_life"]["history_due"] is True

def test_hidden_line_not_shown_to_others():
    hide a line of soldier S; assert its description is absent from lookup(S) for a protagonist outside S's chain
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** Add one line to `worlds/saintjude/rulebook_section.md`: when `history_due` is true, the GM writes the man's history to fit his record (age, crew, years made) and records it with `note`.
- [ ] **Step 4: Run** the test and `tests/world_connector_test.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(connector): lookup shows a man's place in the life`.

---

### Task 15: It fires, five years, and the measures

**Files:**
- Create: `tests/saintjude_mob_fires_test.py`
- Modify: `tools/run_years.py` only if it cannot take `--package saintjude` (add the flag)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the test** (one 5-year run on a copy, 1 Jan 1975 to 1 Jan 1980; prints timing):

```python
def test_five_years_fire_and_stay_true():
    assert made_during_run >= 1 and started_rackets >= 1 and mattering_incidents >= 1 and arrests >= 1
    assert all four families still have a boss, at least 2 capos, and made counts within their figure ranges
    assert every active member has an active superior (except Brigades and heads)
    assert sum(outfit_money 'take' rows) equals the sum of active lines' weekly_take * days posted, within $1 per period
    assert every kickup, executive_share and pad row has a matching ledger economic_flows row between two existing purses
    assert look-invariance: two copies run 90 days, one with server.lookup on 20 associates and 5 capos during the run, give identical outfit_* and crime_reports fingerprints
    assert leak_scan.find_hits(fresh and 1980 DB) == []
    assert decisions + decision_candidate_audit rows written by outfit members < 30_000 per simulated year
    assert db_size_growth_mb_per_year <= 15
```

- [ ] **Step 2: Run it.** If a system never fires, find the disconnection (join key, reachability, due day) before touching any rate; record what was wrong in the commit message.
- [ ] **Step 3: Measure on the PC** and write the numbers into `AGENTS.md` §2 (Saint Jude line): opening time, 30-day advance, 1975-1980, DB size and growth. Targets: opening < 30 s, 30-day advance < 10 s, 5 years < 10 min on the VM (PC figures are expected to be 2-4x faster); if the PC numbers already miss the VM targets, the first lever is cadence (spec §9), and say so to the owner.
- [ ] **Step 4: Run** `python tools/run_suite.py --out runs/suite` then `git restore game/campaign_01/model_requests/`. Expected: all green.
- [ ] **Step 5: Commit** `test(saintjude): the mob fires over five years; measures recorded`.

---

### Task 16: Ship the opening

**Files:**
- Modify: `data/saintjude.db` (rebuilt), `AGENTS.md`, `docs/superpowers/plans/2026-10-24-vm-world-switch-runbook.md` (add the second update)

- [ ] **Step 1: Rebuild** `python tools/build_opening.py --package saintjude` into `data/saintjude.db`; run `python tools/leak_scan.py data/saintjude.db` (clean) and `tests/saintjude_connector_play_test.py` (all PASS, case C asserted).
- [ ] **Step 2: Update `AGENTS.md`** §2: schema 116, what the Saint Jude opening now holds (counts), the measures, and that the mob minimum is done; point to this plan and the spec.
- [ ] **Step 3: Add to the runbook** the second VM update (pull, `update.sh`, delete or keep the Saint Jude campaign: a Saint Jude campaign created before this update has no families; the owner decides whether to start it again).
- [ ] **Step 4: Commit** `feat(saintjude): ship the opening with the mob minimum`. Ask the owner before pushing.
