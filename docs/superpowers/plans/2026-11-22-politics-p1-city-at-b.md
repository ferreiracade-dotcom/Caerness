# Politics P1, the city at B depth: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Saint Jude's politics runs at B depth, always:
- city and ward offices with real calendars;
- the field's actors, each acting for itself (the Machine is one of them);
- voter groups with grievances and turnout;
- mayoral and council races;
- council and board votes on zoning, licences and tenders;
- appointments through sponsors;
- patronage and favours;
- fraud and corruption, answered by the law.

The protagonist is under the same rules throughout.

**Architecture:** Everything is generic engine code on the org core (`org_seats`, `org_lines`, `org_arrangements`, `org_tension`, `split_org`), with all world words in a new package file, `worlds/saintjude/politics.json`, plus new org kinds in `orgs.json`. Offices are new rows keyed on the existing `world_facts` office keys, so `law_opening`, `lookup` and the Fixed rule keep working. Races are ventures, favours and deals are ledger entries, and lasting outcomes pass through the one intake. All three come from prerequisites and are reached through one adapter module, so that a name change there touches one file.

**Tech Stack:** Python 3.13, SQLite (`engine/schema.sql` plus a migration in `engine/db.py`), and the plain-script tests in `tests/` (run with `PYTHONPATH=. python tests/<name>.py`).

**Spec:** `docs/superpowers/specs/2026-11-22-politics-sphere-design.md` (APPROVED 2026-11-22). Also read §5.1–5.4 and §9 of `2026-11-22-real-history-and-engine-gaps-design.md`, and §5 and §10 of `2026-11-22-saintjude-business-design.md`.

## Prerequisites (must have landed before Task 1)

| From | What P1 uses | Where P1 touches it |
|---|---|---|
| History intake core (history spec §9 step 1) | `held_things`, `depth_gaps`, and the intake entry (`author` widened; `settle_due` routed through it) | election results, appointments and passed ordinances are recorded as held things (dated-fact shape) |
| History step 3 (real facts), **only if landed** | `divergences` | P1 writes no divergences (it has no real offices); P2 does. If step 3 has landed, P1 records a divergence when a **fictional** default named in `timeline.json` is changed (for example, the 1975 mayoral race being Open means there is no default, so nothing is written). |
| Business BZ1 | ventures (widened `civilian_projects`, stages as package data), the agreements-ledger `terms` and breach path, shared drivers including **required approvals**, and widened `buildings` | a race is a venture; favours, deals and sponsorship debts are ledger entries; licence and zoning approvals are requested by business and decided here |
| Information I1a (landed, schema 122) | the push and delivery ledger | election nights, indictments and votes that touch the protagonist are pushed |
| Information I1b (landed, 8535472, schema 123) | `engine/claims.py`: `audiences` rows keyed `(key, ref_id)` with rules from `presence.json` `audiences`; `claims.record` (holder `audience`); `claims.impression(conn, aud, subject, day)` giving regard, force and mass, with decay, bad-weighs-more, costly-over-talk and spill; `audiences_of`, `is_member`, `members`; the weekly pass on `org_lifecycle.on_week` | **voter groups are I1b audiences.** Every impression a voter group holds of a candidate, an office-holder or an org is a set of I1b claims, and P1 keeps no impression store of its own |

**Voter groups and I1b (supervisor's correction, 2026-11-22).** P1 owns what makes a voter group an electorate: its district, identity words, size, grievances, **turnout** and the **delivery** organised actors can get from it. I1b owns its impressions. Each voter group is one I1b audience row (`key` = the package's electorate audience key, `ref_id` = `voter_groups.id`). Every political act that should move opinion is recorded as an audience claim through I1b, and read back through `claims.impression`.

## Global Constraints

- Packages are data. There are no world words in `engine/`, and `tests/no_world_words_test.py` must pass. "Machine", "Democrat", "ward" and every office, org, group and place name live in `worlds/saintjude/*.json`. Generic words ("office", "race", "vote", "voter group", "district") may appear in code.
- **No caps, floors, quotas or fixed shares.** Every number is a `design_figures.json` entry with a one-line reason. Calibration targets are reported by the measuring test, never enforced.
- **The engine vetoes; it never offers menus.** Refusals name a contradiction or input gap (`reason_kind`). Eligibility (age, residence, citizenship, conviction bars from law data) is a veto, not a cap.
- **No special case for any actor or outcome.** No code branch tests for a particular org, party or "the Machine". Successor shapes come only from the drivers.
- **The protagonist is under the same rules.** Every behaviour test that acts on an NPC has a paired assertion acting on the protagonist (`engine.player.set_player`). The only exception in the whole engine is the existing lean toward life over death when both are possible.
- **Real people** act within their record. P1 seeds no real office-holder; Saint Jude's officials are fictional.
- **Caerness stays behaviour-identical.** `tests/fixtures/caerness_opening_fingerprint.json` must be unchanged, and with no `politics.json`, every P1 tick is a no-op.
- **Schema:** one migration to the next free version at build time (I1b is 123; expected 126, after the history intake core and BZ1). Bump `SCHEMA_VERSION` in `engine/db.py`.
- **Cost:** with P1 on, the 30-day advance stays under 10 s and five years stays under 10 min on the PC (AGENTS.md targets). Measured in Task 11.
- **Never write `data/*.db`.** Sims run against a copy, and long runs follow constraints.md (at most two at once).
- After tests, run `git restore game/campaign_01/model_requests/`. Commit only the files a task names. Never push, stash, reset or switch branches.

## Review Focus

1. **An office falls vacant mid-term** (death, resignation, conviction, custody). The office's `vacancy` rule (special election, appointment by a named office, or the council choosing) fills it, and politics keeps running. Pinned in Task 1 and Task 9.
2. **A candidate becomes ineligible mid-race** (convicted, or moves out of the district): the race drops him with a named reason, and the drop is logged. Pinned in Task 5.
3. **An org dissolves or is absorbed while holding patronage lines, ledger favours or field holdings.** Each is carried to the successor, or ends with its holders told. Nothing is left pointing at a dead org. Pinned in Task 10.
4. **The protagonist holds an office through a time-skip.** His agenda items and his own re-election interrupt the skip (§5.2b interrupts). Pinned in Task 11.
5. **A vote ties or loses its quorum** (dead or held members). The office data's tie rule decides (the chair's vote, a re-vote or failure), never a silent default. Pinned in Task 6.

---

## File map

| File | Responsibility |
|---|---|
| `engine/civic_seams.py` (new) | the only file that calls prerequisite APIs: venture, ledger entry, intake, approvals, push, I1b claims and impressions |
| `engine/offices.py` (new) | offices, terms, holders, eligibility, vacancy; mirrors to `world_facts.holder_actor_id` |
| `engine/civic_field.py` (new) | field holdings (what each actor holds), transfer, the org-level reading of strength |
| `engine/electorate.py` (new) | voter groups as I1b audiences (the `voter_group` audience rule), turnout and delivery |
| `engine/claims.py` | one generic hook only: `register_audience_rule`, so a package rule I1b does not know can be supplied by another module (no politics words) |
| `engine/civic_patronage.py` (new; `engine/patronage.py` is Caerness and is not touched) | public jobs as lines, favours |
| `engine/races.py` (new) | filing, primary, general, the vote, fraud, the result |
| `engine/civic_votes.py` (new) | agenda items, member weighing, deals, tenders, approvals, ordinances with effects |
| `engine/appointments.py` (new) | sponsor chains and appointed offices |
| `engine/civic_tick.py` (new) | the dated-events tick, wired into `advance`; GM views; cost counters |
| `engine/schema.sql`, `engine/db.py` | the tables below and the migration |
| `engine/world_package.py` | `politics_rules(package)`, a loader like `org_rules` |
| `worlds/saintjude/politics.json` (new) | offices, calendar, powers, eligibility, vacancy rules, voter groups, 1975 holdings, race and vote stages |
| `worlds/saintjude/orgs.json` | new kinds: `party`, `political_club`, `interest` (lifecycle and appointment blocks as for existing kinds) |
| `worlds/saintjude/outfits.json` (or a new `polity_orgs` list in `politics.json`) | the 1975 political orgs to seed **[my call: in `politics.json`, so outfits.json stays the underworld's]** |
| `worlds/saintjude/design_figures.json` | every P1 figure, with reasons |
| `tests/p1_*_test.py` (new) | one test file per task |

## Tables (one migration)

```
offices(id, office_key UNIQUE -> world_facts.key, jurisdiction_kind, jurisdiction_ref, filled_by
        CHECK(filled_by IN ('elected','appointed','org')), appointer_office_key, consent_office_key,
        term_years, cycle_json, powers_json, eligibility_json, vacancy_json, seats INTEGER DEFAULT 1)
office_terms(id, office_id, actor_id, seat_no, start_day, end_day, how
        CHECK(how IN ('opening','elected','appointed','succeeded','special')), ended_how, source_id)
field_holdings(id, holder_kind CHECK(holder_kind IN ('org','actor')), holder_id, stake_kind, stake_ref,
        strength REAL, since_day, ended_day, cause_kind, cause_id)
voter_groups(id, group_key UNIQUE, district_ref, location_id, words_json, size, turnout_base,
        grievances_json, audience_id REFERENCES audiences(id))   -- impressions live in I1b's claims/impressions
races(id, office_id, seat_no, stage, primary_day, election_day, venture_id, result_json, status)
race_candidates(race_id, actor_id, party_org_id, filed_day, dropped_day, drop_reason, primary_share, general_share)
civic_items(id, body_office_key, item_kind, subject_json, opened_day, vote_day, status, outcome_json, venture_id)
civic_item_votes(item_id, member_actor_id, vote CHECK(vote IN ('yes','no','abstain','absent')), why_json)
civic_effects(id, source_kind, source_id, effect_key, value_json, from_day, to_day)
sponsorships(id, appointee_actor_id, office_id, sponsor_actor_id, ledger_ref, day)
```

Nothing has a CHECK list of world words. Kinds such as `stake_kind`, `item_kind` and `effect_key` are validated in code against `politics.json`.

---

### Task 0: The seam adapter

**Files:**
- Create: `engine/civic_seams.py`
- Test: `tests/p1_seams_test.py`

**Interfaces:**
- Consumes: the history intake entry, the BZ1 venture and ledger APIs, and the I1a push. Read their landed modules first, and record the real names in the module docstring.
- Produces:
  - `open_venture(conn, kind: str, backer: int, *, stages_key: str, due_day: int, meta: dict) -> int`
  - `advance_venture(conn, venture_id: int, stage: str, day: int, outcome: dict | None = None) -> None`
  - `ledger_entry(conn, a: int, b: int, *, kind: str, terms: dict, due_day: int | None, day: int) -> int`
  - `ledger_breach(conn, entry_id: int, by: int, day: int, why: str) -> None` (runs BZ1's breach path)
  - `ledger_open(conn, actor: int, *, kind: str | None = None) -> list[sqlite3.Row]`
  - `hold_outcome(conn, *, what: str, people: list[int], dates: dict, consequences: list[str], day: int) -> int` (returns the `held_things.id`)
  - `approval_requests(conn, day: int) -> list[dict]` and `answer_approval(conn, request_id: int, granted: bool, by_office_key: str, why: dict, day: int) -> None`
  - `push(conn, actor: int, kind: str, text: str, day: int, ref: dict) -> None`
  - `group_audience(conn, group_id: int) -> dict`, the I1b audience dict (`{id,key,ref,label}`), made through I1b's own audience helper
  - `tell_group(conn, group_id: int, subject: int, text: str, *, source: str, confidence: float, valence: float, force: float = 0.0, costly: bool = False, day: int) -> int`, which calls `claims.record(holder_kind='audience', …)` and returns the claim id
  - `group_regard(conn, group_id: int, subject: int, day: int) -> float`, the `regard` from `claims.impression`

- [ ] **Step 1: Write the failing test.**
  - `test_each_seam_reaches_its_prerequisite`, on a `build_saintjude` copy. `open_venture` makes a row the BZ1 venture reader sees. `ledger_entry`, then `ledger_breach`, leaves the entry broken and runs the breach path (BZ1's breach marker present). `hold_outcome` writes one `held_things` row with `depth='B'`. `push` writes one I1a delivery row for the actor. `tell_group`, then `group_regard`, moves regard in the claim's direction, and the claim row has `holder_kind='audience'`.
  - `test_missing_prerequisite_names_itself`: monkeypatch the intake import away; `hold_outcome` raises `RuntimeError` whose message contains "history intake core".
- [ ] **Step 2: Run** `PYTHONPATH=. python tests/p1_seams_test.py`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** each function as a thin call to the landed API, with no logic of its own beyond argument mapping.
- [ ] **Step 4: Run the test.** Expected: PASS.
- [ ] **Step 5: Commit** `engine/civic_seams.py tests/p1_seams_test.py`, with the message "feat(politics): P1 seam adapter to the intake, ventures, ledger and push".

### Task 1: Offices, terms, the calendar and eligibility

**Files:**
- Create: `engine/offices.py`, `worlds/saintjude/politics.json` (its `offices` and `calendar` parts)
- Modify: `engine/schema.sql`, `engine/db.py` (migration: all tables above), `engine/world_package.py` (`politics_rules`)
- Test: `tests/p1_offices_test.py`

**Interfaces:**
- Produces:
  - `load_offices(conn) -> int` (idempotent; the number of offices)
  - `holder(conn, office_key: str, seat_no: int = 1) -> int | None`
  - `holders(conn, office_key: str) -> list[int]`
  - `seat_holder(conn, office_key, actor_id, *, how: str, day: int, seat_no: int = 1, source_id: int | None = None) -> int`, which ends the previous term and mirrors `world_facts.holder_actor_id` for single-seat offices
  - `end_term(conn, term_id, how: str, day: int) -> None`, which queues the vacancy
  - `eligible(conn, actor_id, office_key, day) -> tuple[bool, str | None]` (reason words on refusal)
  - `next_dates(conn, office_key, after_day) -> dict` (`primary_day`, `election_day`)
  - `vacancy_rule(conn, office_key) -> dict`

**Package data.** `politics.json`, under `offices`, gives each office key:
- `jurisdiction`;
- `filled_by`;
- `term_years`;
- `cycle`, either `{"every_years": 4, "first_year": 1975}` or `{"real": true}` for P2;
- `primary_month`;
- `election_rule: "first_tuesday_after_first_monday_november"`;
- `powers` (the list from spec §5.4);
- `eligibility` (`min_age`, `residence`, `citizenship`, and `conviction_bar` as a list of crime kinds from `law.json`);
- `vacancy` (`{"how":"special_election"|"appointed_by"|"body_chooses", "by": office_key}`);
- `seats`.

The P1 offices:
- the mayor;
- 15 council seats, one office key per ward with `seats: 1`, plus the council as a body key, `office:council:body`, whose members are those seats' holders;
- the Board of Public Works (3: 2 appointed by the mayor, 1 elected citywide);
- the Zoning Board and the Licensing Board (appointed by the mayor);
- the police commissioner (appointed by the mayor; already in `level4_offices`);
- the county prosecutor (appointed by the Governor with State Senate consent; the Governor and senators are P2 offices with `filled_by:"elected"` and seeded holders, at B only through `appointments`);
- the party offices (county chairman, ward leaders) with `filled_by:"org"`.

**The calendar:** mayor 1975 and every 4 years; council 1977 and every 4 years (owner-approved); a September primary. The bible makes the 1975 mayoral race **Open**: the opening has an incumbent whose term ends 31 December 1975, and the 1975 race runs from the opening. **[my call: an incumbent exists in 1975 and the race is open, so no result is preset.]**

- [ ] **Step 1: Write the failing tests:**
  - `test_offices_load_from_package_only`: Saint Jude has more than 20 offices after `load_offices`, and a Caerness opening has 0 rows and no error.
  - `test_holder_mirrors_world_fact`: `seat_holder` on `office:city-hall:mayor` makes `world_facts.holder_actor_id` equal the actor, and the previous term has `end_day` set.
  - `test_eligibility_vetoes_with_reason`: a 24-year-old gives `(False, 'min_age')` for the mayor (Design figure `office_min_age_mayor`, reason: NJ law, verify). A man with a conviction of a listed kind gives `(False, 'conviction_bar')`. The protagonist, given the same age, gets the same answer.
  - `test_calendar_dates`: `next_dates('office:city-hall:mayor', day_of(1975,1,1))` gives an election day of 4 November 1975 and a primary in September 1975. The council's next election is 8 November 1977.
  - `test_vacancy_queues_rule` (Review Focus 1): `end_term(..., 'died')` on a council seat leaves a pending vacancy whose rule comes from `politics.json`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the migration, the loader and `offices.py`. Seat the 1975 holders from `politics.json` `holders_1975`. Existing world-fact holders are kept, and the rest are pulled up the way `law_opening._fill_officials` does, with sex from the existing `male_share_*` figures and `law.json` `no_woman_seats` as it stands today.
- [ ] **Step 4: Run** this test, then `tests/no_world_words_test.py`. Expected: PASS.
- [ ] **Step 5: Commit** the files listed, with the message "feat(politics): offices, terms, calendar and eligibility (schema N)".

### Task 2: The field's actors and their holdings

**Files:**
- Create: `engine/civic_field.py`
- Modify: `worlds/saintjude/orgs.json` (kinds `party`, `political_club`, `interest`), `worlds/saintjude/politics.json` (`polity_orgs`, `holdings_1975`), `engine/outfit_opening.py` (only to call the generic `build_org` for `polity_orgs`; there is no new logic there)
- Test: `tests/p1_field_test.py`

**Interfaces:**
- Consumes: `outfit_opening.build_org`, `orgs.seat`, `offices.holder`.
- Produces:
  - `seed_field(conn, day) -> dict`
  - `holdings_of(conn, holder_kind, holder_id) -> list[sqlite3.Row]`
  - `holder_of(conn, stake_kind, stake_ref) -> tuple[str, int] | None`
  - `transfer(conn, stake_id, to_kind, to_id, *, day, cause_kind, cause_id) -> int` (the new row)
  - `weaken(conn, stake_id, delta, *, day, cause_kind, cause_id) -> None` (strength floors at 0, then the stake ends)
  - `strength(conn, holder_kind, holder_id) -> float` (sum of active stakes, normalised by `field_strength_scale`)

**What can be held** (the `stake_kind` values in `politics.json`): `party_office` (the chairmanship, a ward leadership), `patronage` (an office's hiring), `sponsor` (a seat in an appointment chain), `delivery` (a voter group), `ledger` (a bundle of favours).

**Seeded in 1975 from data:**
- the county party org (the Machine) with factions as `org_units` (old guard, Italians, Black ward leaders);
- the Republicans;
- reform clubs;
- a civil-rights org.

Existing orgs (unions, the families, the *Chronicle*, the Archdiocese where it exists as an institution) get their `delivery` stakes from `holdings_1975` and no new kind. Builders and banks get theirs when BZ2 and BZ4 create them, through the same `transfer` call.

- [ ] **Step 1: Write the failing tests:**
  - `test_machine_is_only_data`: grep `engine/` for every org name in `politics.json`; none is found. The Machine org's stakes equal `holdings_1975`.
  - `test_any_stake_can_move`: `transfer` of a ward leadership from the party org to a reform club ends the old row, starts the new one with the cause recorded, and `holder_of` returns the club.
  - `test_politics_runs_with_an_org_holding_nothing`: remove every stake of the party org; `civic_tick.process_due` for 400 days raises nothing, and the 1975 race still resolves (this test is completed in Task 5, so assert only `seed_field` and `strength`==0 here).
  - `test_protagonist_can_hold_stakes`: `transfer` to `('actor', player)` works the same as for an NPC.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** this test plus the Caerness fingerprint test. Expected: PASS, with the fingerprint unchanged.
- [ ] **Step 5: Commit** "feat(politics): the field's actors and holdings; the Machine is package data".

### Task 3: Voter groups as I1b audiences; turnout and delivery

**Files:**
- Create: `engine/electorate.py`
- Modify:
  - `engine/claims.py`: add `register_audience_rule(rule: str, *, of_subject, is_member, members)` and have `audiences_of`, `is_member` and `members` fall through to a registered rule after their built-in `org`, `circle` and `home_place`. The hook carries no politics words, and the existing three rules are unchanged.
  - `worlds/saintjude/presence.json` `audiences`: add `"electorate": {"rule": "voter_group", "label": "the voters"}`.
  - `politics.json` `voter_groups` per ward: `words` (descent, class, parish, union, age), `size`, `turnout_base`, and `grievances` (words mapped to drivers: "jobs", "schools", "police", "taxes", "housing").
  - `design_figures.json`.
- Test: `tests/p1_electorate_test.py`

**Interfaces:**
- Consumes: `civic_seams.group_audience`, `tell_group` and `group_regard`; `claims.register_audience_rule`.
- Produces:
  - `seed_groups(conn) -> int`: makes the `voter_groups` rows and one I1b audience each, and stores its `audience_id`.
  - The `voter_group` rule, registered at import:
    - **of_subject(subject):** the groups in whose district the subject is a candidate or holds an office, plus the groups in which the subject (an actor or an org actor) holds a `delivery` stake;
    - **is_member(actor, aud):** his home is in the group's district and his descent, parish, union or age words match the group's;
    - **members(aud):** `[]`, because a crowd is held as an impression only, as I1b does for `home_place`.

    So I1b's own pass (told by a member, then reaching the audience; spill to the subject's people; decay) works for voters unchanged.
  - `regard(conn, group_id, subject, day) -> float`: delegates to `civic_seams.group_regard`. P1 code never reads I1b tables directly.
  - `turnout(conn, group_id, race_id, day) -> float`: from `turnout_base`, the grievance stakes in the race, weather (`calendar`), and organised drive (the sum of `delivery` stakes' effort).
  - `delivery(conn, holder_kind, holder_id, group_id, candidate_id, day) -> float`: from the stake's strength, what the holder can give (its patronage lines, Task 4) and its effort for this candidate.

**Political acts tell the groups.** Later tasks record opinion moves as audience claims with `civic_seams.tell_group`, with words a GM can read back. Each move gets a valence, a force and `costly`, from that task's figures.
- **A race result (Task 5):** "won the mayoralty", "lost in ward 7".
- **Fraud exposed (Task 5):** costly and bad.
- **A vote on an item a group's grievance names (Task 6).**
- **Jobs given or cut (Task 4).**
- **An indictment (Task 8).**

There is no separate decay or half-life in P1: decay is I1b's `claim_half_life_days`.

- [ ] **Step 1: Write the failing tests:**
  - `test_groups_from_data`: every ward has at least one group; the sizes sum to the city's voting-age population figure within rounding; each group has an `audiences` row with key `electorate`.
  - `test_group_is_an_i1b_audience`: `claims.audiences_of(candidate)` includes the groups of his district once he files (after Task 5; before then, seat him in the ward's council office). `tell_group(…, valence=-0.6, confidence=0.8)` makes `regard` < 0. A read `claim_half_life_days` later is closer to 0. A resident member who hears a claim about the candidate reaches the group through I1b's `_reach_audiences` without P1 code.
  - `test_no_impression_store_in_p1`: the schema has no P1 impression table, and grep finds no `INSERT INTO impressions` or `INSERT INTO claims` outside `engine/claims.py`.
  - `test_existing_audience_rules_unchanged`: rerun `tests/i1b_test.py`; it passes.
  - `test_delivery_falls_with_jobs`: halving a holder's patronage lines lowers its `delivery`. This test is completed after Task 4; here, stub the lines with an `org_lines` insert.
  - `test_turnout_rises_with_grievance_at_stake`: a race whose candidates' agendas name a group's grievance has higher `turnout` than one that does not.
  - `test_protagonist_held_alike`: the same claim told to a group about the protagonist and about an NPC candidate gives the same regard.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the hook in `claims.py` first, then `electorate.py`.
- [ ] **Step 4: Run** this test, `tests/i1b_test.py` and `tests/no_world_words_test.py`. Expected: PASS.
- [ ] **Step 5: Commit** `engine/electorate.py engine/claims.py worlds/saintjude/presence.json worlds/saintjude/politics.json worlds/saintjude/design_figures.json tests/p1_electorate_test.py`, with the message "feat(politics): voter groups as I1b audiences; turnout and delivery".

### Task 4: Patronage and favours

**Files:**
- Create: `engine/civic_patronage.py`
- Modify: `orgs.json` (flow `patronage` added to `flows`), `politics.json` (`patronage` per office: jobs and weekly payroll from the city budget), `design_figures.json`
- Test: `tests/p1_patronage_test.py`

**Interfaces:**
- Consumes: `org_lines`, `ledger_entry`, `field.transfer`.
- Produces:
  - `seed_patronage(conn, day) -> int` (lines held by the office-holder's chosen holder of the `patronage` stake)
  - `hand_out(conn, office_key, to_actor, *, day, why) -> int` (a line; writes a ledger favour owed by `to_actor` to the giver)
  - `cut(conn, office_key, share, *, day, cause) -> int` (lines ended, used by the budget and the money crisis)
  - `favour(conn, giver, receiver, what: str, *, day) -> int` (a ledger entry of kind `favour`)
  - `owed(conn, a, b) -> float` (the net favours)

- [ ] **Step 1: Write the failing tests:**
  - `test_jobs_follow_the_office_not_the_org`: when the mayor's office changes holder, its patronage stake moves with the new holder's choice. The old holder's org loses lines, and its `delivery` (Task 3) drops.
  - `test_favour_is_a_ledger_entry`: `hand_out` makes a ledger entry the receiver owes. Breaking it (a vote against the giver, Task 6) runs `ledger_breach`.
  - `test_cut_weakens_holds`: `cut(0.3)` ends about 30% of lines. Seeded, it is exact for the seed.
  - `test_protagonist_gives_and_owes_alike`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** "feat(politics): patronage lines and favours on the ledger".

### Task 5: Races and fraud

**Files:**
- Create: `engine/races.py`
- Modify: `politics.json` (`race_stages` for the venture: filing, primary, campaign, general, result; `vote_drivers` with figure names), `design_figures.json`
- Test: `tests/p1_races_test.py`

**Interfaces:**
- Consumes: `offices.*`, `electorate.*`, `civic_field.*`, `civic_seams.open_venture`/`advance_venture`/`hold_outcome`/`push`, `crime_response.open_report`.
- Produces:
  - `schedule(conn, day) -> int` (opens a race per office whose next dates fall in the scheduling window)
  - `consider_filing(conn, actor, race_id, day) -> bool` (a weighed choice from ambition, standing, money, backing and the odds he can read; the protagonist files only by his own act, `file(conn, actor, race_id, day)`, which goes through `eligible`)
  - `drop(conn, race_id, actor, reason, day) -> None`
  - `run_primary(conn, race_id, day) -> dict`
  - `run_general(conn, race_id, day) -> dict`
  - `vote_shares(conn, race_id, stage, day) -> dict[int, float]`, per group, summed
  - `commit_fraud(conn, actor, race_id, group_id, kind, size, day) -> dict` (gain and exposure)
  - `result_why(conn, race_id) -> dict` (driver contributions per candidate)

**The vote.** Per group, a candidate's score is
`w_inc*incumbent + Σ_org delivery + w_imp*regard (electorate.regard, I1b) + w_tie*ties + w_econ*economy_fit + w_scandal*scandal + w_money*log1p(spend) + w_end*endorsements + noise`.
Each group's turnout times its share-softmax gives the votes, and the votes are summed. The weights are figures. `noise` is from `_rng(conn, 'race', race_id, group_id)`. `ties` come from shared descent, parish and union words between the candidate and the group. **Fraud** adds votes in one group and draws an exposure chance from the figures (poll watchers, which come from rivals' delivery stakes in that group; press; `heat`). Exposure opens a crime report through `open_report(crime_kind='election_fraud', ...)` and tells every group in the district a costly bad claim about the beneficiary (`tell_group`). Each result is also told to the district's groups as a claim about the winner and the losers.

- [ ] **Step 1: Write the failing tests:**
  - `test_1975_mayoral_race_resolves`: from the opening, advance to 5 November 1975. The race has a winner. The mayor office's holder from 1 January 1976 is that winner. A `held_things` row exists, and `result_why` lists each driver.
  - `test_no_fixed_result`: across seeds 3, 7 and 11, a race built to be close (equal drivers) gives more than one winner.
  - `test_incumbency_matters`: the same race with and without an incumbent shifts the incumbent's share up by more than 0.
  - `test_ineligible_mid_race_is_dropped` (Review Focus 2): convict a candidate between the primary and the general; he is dropped with the reason `conviction_bar`.
  - `test_fraud_gains_and_can_be_exposed`: with fraud, the beneficiary's share in that group is higher. Over 50 seeded trials the exposure rate is above 0 and below 1, and each exposure has a crime report.
  - `test_politics_after_the_machine`: the Task 2 scenario completed. With the party org holding nothing, the 1975 race still resolves and the winner's backers are other actors.
  - `test_protagonist_files_and_loses_alike`: the protagonist files and the same drivers decide; he can lose.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** "feat(politics): races as ventures, the vote from drivers, and fraud".

### Task 6: Agenda votes, deals, tenders, approvals and ordinances

**Files:**
- Create: `engine/civic_votes.py`
- Modify: `politics.json` (`item_kinds`: zoning variance, licence, tender, budget, ordinance; each with its body office, quorum, tie rule and the effects it may carry), `design_figures.json`
- Test: `tests/p1_votes_test.py`

**Interfaces:**
- Consumes: `offices.holders`, `electorate.impression`, `civic_patronage.owed`, `civic_seams.ledger_*` and `approval_requests`/`answer_approval`, `org_arrangements` (money on an official).
- Produces:
  - `open_item(conn, body_office_key, item_kind, subject: dict, *, vote_day, day) -> int`
  - `member_vote(conn, item_id, member, day) -> tuple[str, dict]`, weighing his district groups' `electorate.regard` of the subject's sponsor and of himself, his patron's or faction's line, the interests pressing him, favours owed, money on him, his own agenda and conscience (temperament), and press exposure
  - `pre_vote_deal(conn, item_id, member, counterparty, terms, day) -> int` (a ledger entry; voting against it calls `ledger_breach`)
  - `decide(conn, item_id, day) -> dict` (count, quorum, tie rule; writes `civic_effects` for a passed ordinance and `hold_outcome`; tells each group whose grievance the item names how its own member voted, through `tell_group`)
  - **Tender**, replacing BZ3's stub with the same interface the stub exposes:
    - `open_tender(conn, office_key, spec: dict, *, close_day, day) -> int`
    - `award_tender(conn, item_id, day) -> dict` (bids come from business; the members weigh price, ties, favours and kickbacks)
  - `decide_approvals(conn, day) -> int`: each request from `approval_requests` is weighed by its office-holder and answered with `answer_approval`
  - `effects_on(conn, effect_key, day) -> list[dict]` (what business drivers read)

- [ ] **Step 1: Write the failing tests:**
  - `test_vote_counts_members`: a zoning item before the council gives 15 votes or absences, and the outcome follows the count.
  - `test_deal_breach_runs_ledger`: a member with a deal who votes against it triggers `ledger_breach` and raises tension between the parties' orgs.
  - `test_tie_and_quorum_follow_data` (Review Focus 5): with 8 members held in custody, quorum fails with the reason `quorum`. A built tie resolves by the body's `tie_rule` from data.
  - `test_tender_replaces_stub`: BZ3's stub test file still passes against `civic_votes.open_tender`/`award_tender`. The award goes to a bidder with a kickback arrangement more often than to an equal bidder without one, over seeded trials, and not always.
  - `test_approvals_answered`: an approval request from a BZ1 venture is answered with a reason dict.
  - `test_ordinance_effect_readable`: a passed ordinance writes a `civic_effects` row, and `effects_on` returns it from its `from_day`.
  - `test_protagonist_as_member_and_as_petitioner`: the same weighing applies when he sits on the council and when he lobbies it.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** this test and the BZ3 tender stub test. Expected: PASS.
- [ ] **Step 5: Commit** "feat(politics): agenda votes, deals, tenders, approvals and ordinance effects".

### Task 7: Appointments by sponsorship

**Files:**
- Create: `engine/appointments.py`
- Modify: `politics.json` (each appointed office: `appointer`, `consent`, `sponsors` as office keys or stake kinds, `courtesy_block: true` for a home-county senator)
- Test: `tests/p1_appointments_test.py`

**Interfaces:**
- Consumes: `offices.*`, `civic_field.holder_of('sponsor', …)`, `civic_seams.ledger_entry`.
- Produces:
  - `fill(conn, office_key, day) -> int | None`: put forward (each sponsor weighs loyalty and debts), the appointer weighs fit, politics and the press, then consent (courtesy can block). The appointee is seated, with a `sponsorships` row and a ledger debt to the sponsor.
  - `review_on_change(conn, appointer_office_key, day) -> int` (a new appointer may replace an at-pleasure appointee)
  - `sponsor_of(conn, actor_id, office_key) -> int | None`

- [ ] **Step 1: Write the failing tests:**
  - `test_commissioner_appointed_by_mayor`: when the mayor's office changes holder, `review_on_change` may replace the commissioner. Over seeded trials it sometimes does and sometimes doesn't. Each new commissioner has a sponsor and a debt.
  - `test_courtesy_blocks`: a sponsor-chain senator hostile to the nominee blocks him, with the reason `courtesy`.
  - `test_sponsor_is_whoever_holds_the_seat`: move the `sponsor` stake from the party org to a reform chairman, and the next prosecutor's sponsor is the reform chairman.
  - `test_protagonist_can_sponsor_or_be_appointed`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** "feat(politics): appointments through sponsor chains".

### Task 8: Corruption and the law's answer

**Files:**
- Modify: `engine/civic_votes.py` (money on an official as an `org_arrangements` row of kind `retainer`, from `law.json` `arrangements`), `engine/crime_response.py` (only to register crime kinds `bribery`, `kickback`, `no_show_job` and `election_fraud` from package data; no political logic there), `worlds/saintjude/law.json` (those kinds, and the agencies that take them: the county prosecutor, the U.S. Attorney, the SCI, the state AG)
- Create: (none)
- Test: `tests/p1_corruption_test.py`

**Interfaces:**
- Consumes: `crime_response.open_report`, B13's disposition and sentence chain, `offices.end_term`, `appointments.sponsor_of`.
- Produces:
  - `put_on(conn, payer_kind, payer_id, official, weekly, *, go_between, day) -> int` (reuses the Pad path, with the same reach, integrity and exposure rules)
  - `exposure_check(conn, day) -> int` (weekly: each active political arrangement draws exposure from heat, the press, informers and the agencies' **ambition**)
  - `ambition(conn, agency_actor, target_actor) -> float` (a prosecutor's career gain from the target's office rank; a figure-scaled driver, not a cap)

- [ ] **Step 1: Write the failing tests:**
  - `test_bribed_member_votes_the_payers_way_more_often`.
  - `test_exposure_opens_a_case_and_conviction_vacates` (Review Focus 1): an exposed councilman leads to a report, a case and a conviction. `end_term('convicted')` runs, and the vacancy rule fills the seat.
  - `test_deal_pressure_applies_to_politicians`: a charged official may inform on his go-between (B12g informer path), with the same chance function as a mob man.
  - `test_ambition_scales_with_rank`: a mayor target gives higher ambition than a clerk target.
  - `test_protagonist_bribes_and_is_exposed_alike`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** this test and `tests/b13b_fixes_test.py`. Expected: PASS.
- [ ] **Step 5: Commit** "feat(politics): political arrangements and the law's answer".

### Task 9: Vacancies and succession across offices

**Files:**
- Modify: `engine/offices.py`, `engine/races.py` (special elections)
- Test: `tests/p1_vacancy_test.py`

**Interfaces:**
- Produces: `process_vacancies(conn, day) -> int`, which runs each pending vacancy's rule: `special_election` gives `races.schedule` a dated race; `appointed_by` gives `appointments.fill`; `body_chooses` gives `civic_votes.open_item(item_kind='choose_member')`.

- [ ] **Step 1: Write the failing tests:**
  - `test_each_vacancy_rule_fills`: one office per rule, each emptied by death; each is filled by its rule within the rule's figure days, and the term's `how` is set.
  - `test_held_in_custody_is_not_vacant_until_rule_says`: custody alone leaves the seat held, with the member absent from votes. The data's `custody_vacates_after_days`, if present, then vacates it.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** "feat(politics): vacancies filled by each office's rule".

### Task 10: The field shifts: weakening, splits, absorption, after an organisation

**Files:**
- Modify: `engine/civic_field.py`
- Test: `tests/p1_field_shift_test.py`

**Interfaces:**
- Consumes: `org_coup.split_org`, the B12g absorption path (`org_dealings`), `org_tension`, `civic_patronage`, `civic_seams.ledger_open`.
- Produces:
  - `weekly_shift(conn, day) -> dict`. For each holder, it weighs each stake against its drivers:
    - lost lines;
    - defeats (a race lost by its backed candidate);
    - indictments of its seat-holders;
    - a head's death (org-core succession already runs);
    - a voter group's impression of it;
    - a rival's offer (a better patron).

    Stakes weaken or transfer to whoever the drivers favour, with no named recipient in code.
  - `factional_walkout(conn, org, unit_id, day) -> int | None`: a faction leader whose grievance passes the figure takes his unit's members and stakes through `split_org`.
  - `carry_on_end(conn, org, day, successor: int | None) -> dict` (Review Focus 3): when an org ends or is absorbed, its stakes, patronage lines and ledger entries go to the successor or end, and their counterparties are told through `push`.

- [ ] **Step 1: Write the failing tests:**
  - `test_defeat_weakens_backer`: the org whose candidate lost a race has a lower `strength` afterwards than before.
  - `test_walkout_makes_a_new_org_with_its_stakes`: a forced grievance creates a new org through `split_org`, holding the unit's ward leaderships.
  - `test_end_carries_or_closes_everything` (Review Focus 3): after `carry_on_end`, no active `field_holdings`, `org_lines` or open ledger entry points at the ended org.
  - `test_successor_shapes_vary_by_seed`: from a built state where the party org has collapsed (stakes zeroed by indictments), a 4-year run over seeds 3, 7 and 11 leaves the city's mayoralty and most ward leaderships held by different kinds of holder (a single dominant org, several, or the reform club) on at least two seeds. **The test asserts variety, not any particular outcome.**
  - `test_no_actor_named_in_shift_code`: grep `engine/civic_field.py` for the org keys in `politics.json`; there are none.
  - `test_protagonist_can_lead_a_walkout`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** "feat(politics): the field shifts; any holder can weaken, split or end".

### Task 11: The tick, the GM views, the push and the cost

**Files:**
- Create: `engine/civic_tick.py`
- Modify: `engine/simulation.py` (register next to `process_due_politics`; do not touch that function), the B14 view module that serves `lookup`/`scene` (add a `politics` view), `engine/timeskip.py` (interrupts)
- Test: `tests/p1_tick_test.py`, `tests/p1_measures_test.py` (slow; add to `tests/slow_tests.txt`)

**Interfaces:**
- Produces:
  - `process_due(conn, day, *, event_logger) -> dict`, which runs, in order: `races.schedule`; race stages due; `civic_votes` items due; `decide_approvals`; `process_vacancies`; and weekly, `exposure_check` and `weekly_shift`
  - `next_due_day(conn, after_day, through_day) -> int | None`, for the skip planner
  - `view(conn, observer, day) -> dict` (behind the firewall): seats near him, who owes him and whom he owes, the calendar ahead, and, for his standing with voters, I1b's existing `held_of_him` filtered to `electorate` audiences (no new reader)
  - Pushes: election night, a vote on an item he sponsored, an indictment of someone he deals with, a law that touches his business

- [ ] **Step 1: Write the failing tests:**
  - `test_tick_is_noop_without_package`: Caerness `advance` 30 days leaves the fingerprint unchanged.
  - `test_skip_interrupts_for_protagonist_office` (Review Focus 4): the protagonist holds a council seat, and a 90-day skip spanning a vote on his item and his own primary stops at both.
  - `test_view_respects_firewall`: the view does not list a bribe arrangement he cannot know.
  - `test_push_on_election_night`: one delivery row for him on election day when he is a candidate or a backer.
  - `p1_measures_test` (slow), a five-year run on seeds 3, 7 and 11 from the opening. It reports, without asserting a range:
    - incumbents' re-election rate;
    - the reform win rate;
    - turnout per race;
    - fraud and exposure counts;
    - indictments of officials;
    - prosecutor turnover;
    - women office-holders;
    - stakes per holder over time;
    - time per 30 days and the five-year time.

    It asserts only that the five-year time is under 10 min and the 30-day step is under 10 s on the PC.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement**, with the elections as dated events and lazy impressions (spec §6 cost budget).
- [ ] **Step 4: Run** the quick tests, then the full suite (`python tools/run_suite.py --out runs/suite`), then `git restore game/campaign_01/model_requests/`. Then run `p1_measures_test` in the background on a DB copy (constraints.md). Expected: PASS, with the measures reported in `runs/p1_measures/`.
- [ ] **Step 5: Commit** "feat(politics): P1 tick, GM view, push and measures"; add to AGENTS.md status a P1 line with the measured times.

---

## Self-review against the spec

| Spec section | Covered by |
|---|---|
| §5.1 offices, generic across levels, calendar, seeding, firewall | Task 1. P2 adds real offices; the same model with `cycle.real` |
| §5.2 field actors, money and patronage, the Machine as one org, after it | Tasks 2, 4 and 10 |
| §5.3 the electorate, races, drivers, fraud | Tasks 3 (voter groups as I1b audiences) and 5. State and national at B is P2 |
| §5.4 powers, votes, laws (city ordinances in full) | Tasks 1 (powers as data) and 6. State and national laws are P2 |
| §5.5 appointments | Task 7 |
| §5.6 the families as an interest | Tasks 2 (delivery stakes) and 8 (the Pad upward) |
| §5.7 corruption, ambition, deals | Task 8 |
| §5.8 real people above the city | P2. P1 only reads the seeded Governor and senators as the appointment chain |
| §5.9 C depth | P3 |
| §5.10 the protagonist under the same rules | the paired test in every task |
| §5.11 GM view and push | Task 11 |
| §6 constraints and cost | Global Constraints; Task 11 measures |
| §8 calibration | Task 11 report (never asserted) |
| §9 business seams | Task 0 (approvals, ledger, ventures), Task 6 (tenders replace the BZ3 stub; effects for drivers), Task 4 (public jobs as an employer: the lines are visible to BZ's labour market through `org_lines`) |

Left to the builder: the exact figure values (each with a reason in `design_figures.json`), the softmax temperature, and the exact window for opening a race before its primary.
