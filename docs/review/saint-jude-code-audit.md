# Saint Jude code audit against story first (2026-11-27)

**The question (owner):** what in the Saint Jude or engine code it touches doesn't fit the new philosophy, and what is
more complicated than it needs to be to deliver the story?

**The rules used:** AGENTS.md §0 (story first; the simplest mechanism wins) and revision 5 of the three-levels design:
- no psychology simulation;
- recording stays light;
- the engine never chooses for him;
- packages are data only;
- no caps.

**Method:**
- I ran 120 days of Saint Jude from the packaged opening, on a copy, under a profiler.
- I recorded which engine modules ran, what each table gained, and whether anything reads what was written.
- I left out what the grand plan, the three-levels plan or the nearby-code review (`three-levels-adjacent-verdicts.md`)
  already deals with.

**The run:** 121 engine modules ran, 109 tables grew, and the run made 211 events, all births, unions, comings of age,
deaths and successions.

## Already dealt with by the plans (not repeated here)

- The old personal choices and the belief mirror. The mirror is the four 13,143-row tables `knowledge`,
  `knowledge_provenance`, `actor_evidence_access` and `actor_beliefs`. Both go in Task 2b.
- `resolution_controller`'s second level ladder (Task 3).
- Event-to-rumour broadcast and the side doors into his news (Task 10).
- `outings`' `you_may` list of moves (Task 11).
- Background rolls that ignore protection (Task 14).
- `org_happenings` choosing for him (Task 2b).
- The agency leaks in civic, prison and business code (Task 14c).

## New findings

### 1. Two systems answer "where is this person?" (the biggest)

- `presence.py` keeps probabilistic presence habits for everyone:
  - 12,469 new rows in 120 days;
  - the single costliest module, about 11% of the engine's own time.
- Task 3b adds `routines.where` as the answer, but nothing moves `presence.py`'s callers onto it. They are:
  - `company.py` (who is with him in a scene);
  - `household_life` (courtship meetings);
  - `authoring` (housemates);
  - `information` (rumour exposure; that part goes off with Task 10);
  - plus `player`, `turns`, `decisions` and `model_gateway`.
- The nearby-code review said `outings.crowd` was presence's last caller. That is wrong.
- **Risk:** after Deploy 1, the scene's company and the presence check could disagree about where a man is.
- **Proposal:**
  - Task 3b moves `company.py`, `household_life` and `authoring` onto `routines.where`.
  - Saint Jude stops writing presence habits.
  - The module stays for Caerness.

### 2. Saint Jude babies get a Caerness cultivation "Core" (a bug)

- `household_life` calls `cultivation.assign_birth_core` for every birth with no check of the package.
- All 56 babies born in the run got a `Closed-Core` row with Caerness metadata (`HEREDITARY_BIRTH_CORE`).
- The other two paths that write cultivation profiles already check `system_enabled(conn, "cultivation")`.
- `tools/leak_scan.py` doesn't look at this table.
- **Proposal:**
  - Guard the call: one line.
  - Delete the rows on existing Saint Jude saves in a migration.
  - Add the table to the leak scan.

### 3. The psychology process runs in Saint Jude

- It writes grief and trauma scores (for example "grief 60, intensity 29.4" after a death).
- Nothing reads them except a coverage count used in tests.
- Revision 5 says plainly: no psychology simulation.
- Task 2b lists `psychology` among the Caerness processes to switch off, but as optional tidying and "on empty tables".
  It isn't empty.
- **Proposal:** make that switch required, not optional.

### 4. Records nobody reads

| Table | Rows in 120 days | Read by |
|---|---|---|
| `mortality_audit` (one row per person per monthly death check, about 8,500 a year) | 2,824 | nothing |
| `information_links` | 580 | nothing |
| `resolution_transitions` | 84 | nothing |
| `actor_context_cache` | 111 | nothing |

- Recording should stay light.
- **Proposal:** Saint Jude stops writing these:
  - `mortality_audit` keeps a row only for a death, or only under a debug switch;
  - the other three go off with the systems that write them.

### 5. Saint Jude words and closed lists inside `engine/` (small)

- `underworld.py`:
  - a closed set of organisation types;
  - a hard-coded rule refusing "gang-to-Mafia-family" promotion.
- `temperament.py` branches on `organization_type == "mafia_family"`.
- `veto.py` holds a list of public-office words (mayor, alderman, councilman and so on).
- `civic_field` and `civic_patronage` read package keys named `holdings_1975` and `patronage_1975`.
- Each is small, but all are world facts living in the engine, not in the package.
- **Proposal:** move them to package data when that code is next touched. No dedicated task.

### 6. Looked at, no change proposed

- **Relationships:**
  - Each bond holds ten numbers: affection, trust, resentment, fear, respect, loyalty and others.
  - Every change also writes a history row: 4,718 in 120 days.
  - That is closer to modelling inner states than revision 5 likes.
  - But `life_matters`, the outfit choices and the brief all read those numbers, and the player meets the result only
    as how people treat him.
  - Replacing them would be a large change for little that he would notice. Keep.
- **Outfit motives:**
  - `org_motives` and `outfit_motives` score motives from real state: 1.5 million calls in 120 days.
  - This is the working level-2 layer the design keeps, and it already follows temperament and cost. Keep.
- **`temptations` and `settle_circle`:** kept by the earlier review, and still right.
- **No hard caps found** in the code that runs for Saint Jude. The package's prison capacities and term limits are real
  facts about the buildings and the law.

## Second pass: the code that runs during play (2026-11-27)

The first pass profiled the city's own clock, with no protagonist and no scenes, so the tools the GM calls never ran.
This pass read those paths: `act`, its dispatch (`connector/acting.py`), `free_operation`, `player_operations` and
`outings`, checked against story first and the engine/GM split. Four findings.

### 7. His answer to a matter already has a tool, and revision 6.5 added a second one

- `act(action_type="answer", details={"matter", "answer", "how"})` already exists. It answers anything in
  `waiting_on_you` through `life_matters.answer`: "yes", "no", or "settled" with a free-text `how`.
- Task 14c makes a seat decision a `waiting_on_you` matter.
- Revision 6.5 then added `note(kind="answer")` as a separate path for those matters, without knowing this tool
  existed.
- **Proposal:**
  - Drop `note(kind="answer")`.
  - `act(answer)` hands a `seat_decision` matter to `nominations.realize` with `{"choice": how or answer}`.
  - Every other matter goes to `life_matters.answer` as now.
  - That leaves one tool, with the player's own words in `how`.

### 8. `act` hides sums behind scale words

- `player_operations` returns money only as scale words. Its header says "Amounts leave this module only as scale
  words".
- So `act(pay)` returns `"amount": "modest"`, and its summary says "hands over a modest sum".
- Yet the Saint Jude rulebook says every sum the GM states must agree with `scene` or `lookup`. The contract says tool
  results give facts and numbers in fields, not engine prose. The `money` tool does give dollars.
- The GM is left to invent the figure, which is exactly how sums drift.
- Task 11 fixes this for `views.py` only.
- **Proposal:**
  - Task 11 also covers `act`'s results: the dollar figure as a number in `amount` (and in `short_of`).
  - The scale word may stay beside it. The summary sentence becomes plain facts.

### 9. Free actions are matched against a fixed keyword list, and anything else is refused

- `free_operation` sorts an intent into one of 15 kinds by English keyword: travel, duel, battle, message, treat,
  train, craft, project, attack, trade, demand, lend, hire, pay, order.
- Many of the keywords are Caerness words: siege, smith, granary, sect, tithe, guild, "sail to", "march to".
- An intent that matches none is refused with "That is not something the engine can carry out yet". Its reason kind
  tells the GM to rephrase and retry.
- So a con, a forged document, a newspaper smear or a rigged fight gets pushed into the wrong kind (a "pay", an
  "order"), or played with nothing recorded.
- That cuts against Task 12's rule: never refuse an ambition because nothing models it.
- **Proposal:**
  - An unmatched intent comes back as `status: "unmodelled"`, not a refusal.
  - The result names the record path the rulebook already gives (a scene stamp with `known_to`, `money` for any sum,
    `author` for anyone new), so it is played and recorded, never turned away.
  - The keyword list stays; the GM's `kind` hint already overrides it.
  - Its Caerness words join O-9.

### 10. Task 11 deletes `outings.approach`, but `act` still calls it

- Task 11 deletes the happenings draw, `you_may` and `approach` from `outings`. That is right: approach is a fixed
  four-move romance roll with points for each move.
- But `act(outing)` with a target, and the `act` tool's own description ("details.move talk|dance|number|leave
  together"), still lead there.
- **Proposal:** Task 11's files add `connector/acting.py` (an outing with a target becomes an ordinary scene with
  that person) and the `act` description in `connector/server.py`.

### Smaller, joining O-9

- `ledger._LEADER`, the pattern that decides who may draw on a holder's purse, matches Caerness titles (lord, abbot,
  abbess, prior, patriarch, steward, warden).
- It belongs in package data with the other world words.

## Third pass: systems that do the same job twice (2026-11-27)

This pass looked for places where two systems hold the same fact or do the same job.

### 11. Saint Jude outfits live in one organisation layer, and his tools use the other

- The engine has two organisation layers:
  - the old Caerness one: `underworld_organizations`, `underworld_personnel` and about 40 `underworld_*` tables,
    worked by `underworld.py` and `underworld_rebuild.py`;
  - the org core (`org_profiles`, `org_seats`, `org_units`, `org_money` and the `org_*` modules), which runs Saint
    Jude's outfits.
- In Saint Jude the old tables are empty after 120 days (0 organisations, 0 personnel).
- But every outfit path in the tools he uses still reads and writes the old layer:
  - `ledger`'s `outfit:<id>` purse reads `underworld_organizations.treasury`. Checked on a Saint Jude save,
    `outfit:20` (the Eastside Combine) is refused as "unknown outfit 20".
  - In `player_operations`:
    - hiring into an outfit (`create_personnel`);
    - promoting, retiring and expelling;
    - "his outfit" (`_my_outfit`);
    - truces and alliances (`change_relation`);
    - heat (`add_heat`);
    - the men behind an attack.
  - In the connector:
    - `store`'s and `authoring`'s outfit ids;
    - `views`' list of who is in the life.
- **What it means in play:** a Saint Jude boss can't pay out of his outfit's treasury through `money` or `act`. He
  can't hire a man into it, promote one, or make a truce through `act`. Each comes back refused, or does nothing.
  That is a silent disconnection.
- It is also complexity: two layers for one thing.
- **Deploy 1 is affected.** Task 14d proves "play anyone, including a boss", but these paths are not in its test.
- **Proposal:**
  - Point those paths at the org core when the package runs it (`systems.outfits`):
    - an outfit purse is the org core's treasury;
    - hiring, promoting and dismissing go through `org_seats`;
    - truces and alliances go through `org_tension`;
    - heat goes through `org_heat`.
  - The old layer stays for Caerness.
  - Task 14d's boss start gets a test: he pays a man from the treasury, takes one on, and agrees a truce, each landing
    in the org core.
- This overlaps grand plan F-14 (his reach into the outfit, Deploy 3a). F-14 assumed these paths worked and only
  checked the non-boss side.

### Overlaps that are deliberate, no change proposed

- **How closely someone is simulated.** After Deploy 1, two settings remain:
  - `actors.sim_resolution`, from `levels`: how much he matters to the story;
  - `simulation_profiles`, used by `tiers.py`: how often his upkeep runs.
  - The contract keeps them apart on purpose; 14 modules read the second.
  - The old `entity_resolution` (5,934 rows) stays frozen in Saint Jude once its process is off. That is harmless.
- **What people think of him.** Three records each answer a different question:
  - the ten numbers on each relationship: how one person feels about another;
  - `claims` and `impressions`: what is said of him, and how a crowd sees him;
  - `standing`: words worked out from those two.
  - Merging them would be a large change before anyone has played.
- **Marriages:** these come from two places, but for different people. `household_life`'s courtship pairs named
  people; `opening_family` marries a named person into the unnamed population. Not a duplicate.
- **The money-flow recorder** lives in `underworld_rebuild` (`_record_economic_flow`), though every Saint Jude
  payment uses it. Misplaced, but harmless. It can move to `ledger` when either file is next touched (O-9's list).

### Still not covered by any pass

- **The opening builder** (`tools/build_opening.py`, `opening_family`): it runs once. "Canon null means unknown"
  already governs it.
- **Caerness's own code:** left alone until Caerness is renovated, by the owner's rule.
- **Whether the engine still acts for him during a run:** the first pass had no protagonist. Task 14c's hands-off test
  is the check for that.

## What it would cost

- **Findings 1 to 4:** small changes that fit the Deploy 1 tasks that already touch these files (Tasks 2b and 3b).
- **Finding 5:** later, when that code is next touched.
- **Finding 6:** nothing.
- Nothing is deleted; each change is a Saint Jude switch or a guard, as revision 5 requires.
