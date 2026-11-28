# Task briefs (Gemini, through revision 6.13)

Filed 2026-11-28. These are Gemini's zero-history briefs for the most-patched tasks. They are the **checklist** for
the clean pass in the plan's Global Constraints (revision 6.14), not the build text: before each build session the lead
rewrites the task in `docs/superpowers/plans/2026-11-26-three-levels-build.md` as one clean text and ticks each point
here off against it, or strikes it with a reason. Where a brief and the plan differ, the plan wins.

Known differences to settle at the clean pass:
- Task 3's brief mentions a `levels.json` validator; Gemini's `levels.json` draft was not kept, so the values come from
  the plan's tasks.
- Task 7's brief reads `scene_stamps` and `holds_true`, which Task 3 builds (contract); Task 7 runs after Task 3.
- Task 0 (the quick suite, revision 6.14) has no brief; it is short enough to build from the plan.

---

## Task 2b: Switch off competing paths

* Files:
   * Modify: `engine/world_package.py` (`SYSTEM_KEYS` adds `personal_choices`, `belief_mirror`, `entity_resolution`, `rumour_broadcast`, `psychology`, `mortality_audit`, `presence_habits`; `worlds/caerness/world.json` sets all 7 `true`; Saint Jude omits them).
   * Modify: `engine/decision_runtime.py` (`_builtin_candidates` adds built-in personal providers only when `systems.personal_choices` is true; registered providers like `org` and "hold position" always run).
   * Modify: `engine/decisions.py` (`decide_actor` skips `build_actor_context` when only registered providers run).
   * Modify: `engine/information.py` (`_upsert_knowledge` calls `belief.mirror_legacy_knowledge` only when `systems.belief_mirror` is true).
   * Modify: `engine/org_happenings.py` (protagonist draws only happening kinds marked `"befalls": true`) and `worlds/saintjude/outfits.json` (mark `busted`, `incident` as `"befalls": true`).
   * Modify: `engine/simulation.py` (`SYSTEM_PROCESSES` adds `"psychology": ("psychology",)`).
   * Modify: `engine/household_life.py` (guard `cultivation.assign_birth_core` on `system_enabled(conn, "cultivation")`) and `tools/leak_scan.py` (flag any `cultivation_profiles` row when cultivation is off).
   * Modify: `engine/health.py` (`mortality_audit` writes a row only on death unless `systems.mortality_audit` is true).
   * Create: `tests/competing_paths_off_test.py`.
* Verify: 120-day Saint Jude run has 0 `consolidate`/`initiate_interaction` decisions, >0 `org_action`, 0 `actor_beliefs`, >0 `knowledge`, 0 `psychological_stressors`, >0 births with 0 `cultivation_profiles`, and `mortality_audit` count == deaths. 52-week associate protagonist draws only `busted`/`incident`. Caerness keeps all 7 switches `true`. Run `--quick` plus `s1_rise_equivalence_test`, `org_happenings_test`, `outfit_choices_test`. No `caerness_economy` switch.

## Task 3 (Key Amendments): Schema 134 & resolution levels

* Additions to keep in mind when building Task 3:
   * `nominations.status` CHECK constraint includes `'lapsed'`.
   * `knowledge` gets `cutaway_day` column (and `publish_media`'s table gets a shown-once marker).
   * Schema 134 migration deletes `cultivation_profiles` rows on saves where cultivation is off (Caerness saves keep theirs).
   * `SYSTEM_PROCESSES` gates `resolution` on `systems.entity_resolution`; `resolution_controller.py` assigns `sim_resolution='materialized_minor'` on quiet routine when off.
   * `worlds/saintjude/seed.json` gives Daily Mirror, Chronicle, Courier, Channel 4, Channels 7 & 10, and WSJD radio business `economic_state` rows (Mirror and Chronicle owned by their canon publisher offices; others left for opening fill).
   * `worlds/saintjude/levels.json` validator accepts `null` for Deploy 2 keys (`shocks`, `pressures`, `actions`, `noticing`, `long_sentence_days`, `opportunities`).

## Task 3b: Routines on demand

* Files:
   * Create: `engine/routines.py`, `tests/routines_test.py`.
   * Modify: `engine/levels.py` (`refresh` calls `routines.seed` for newly notable/active), `tools/build_opening.py` (seed routines at end of build), `worlds/saintjude/levels.json` (`schedules`).
   * Modify: `engine/company.py` (`in_earshot`), `engine/household_life.py` (courtship scan), `engine/authoring.py` (who is at home) — all three move onto `routines.where` alone (no presence fallback).
   * Modify: `engine/presence.py` (under `systems.presence_habits` false, answer remaining callers without writing new habit/profile rows).
* Requirements:
   * `seed(conn, actor_ids=None) -> int`: home from household, work from employer or owned business, schedule from position.
   * `where(conn, actor_id, day, part) -> int | None` (`morning|day|evening|night`, read-only):
      1. Exceptions first (active `custody` held, open `inmate_stays`, serving `sentences`, active/stalled `travel_plans`, explicit exceptions).
      2. Institution meeting evening: each club, supper club, diner, or parish meets one deterministic evening/week (derived from its id); members are placed there on that evening (older membership wins ties), with or without a stored routine.
      3. Stored routine schedule; if unseeded, compute on the spot (read-only) from household + employer/business on default schedule. Return `None` only if neither home nor work exists.
   * `household_life` courtship scan asks `routines.where` for both members on their institution's meeting evening.
* Verify: >90% notable/active seeded; exceptions/custody/travel override schedule; unseeded minor placed at home at night and at club on meeting evening; `company.in_earshot` matches `where`; 120-day Saint Jude run writes 0 new `actor_presence_habits`/`profiles` rows; S1 ranges and courtship rate stay in reference range.

## Task 7: GM fault checker

* Files: Create `tools/gm_check.py`, `tests/gm_check_test.py`.
* Requirements:
   * `gm_check.py <transcript.txt | session.jsonl> [--db <save.db>] -> {"G1": [...], ..., "G5": [...], "ledger": [...]}`.
   * Pattern hits G1–G5 with line numbers (numbered menus, asking player to invent names/facts, machinery leaks, moralising, meta-prompts).
   * Session ledger checks: every scene closed; no unanswered tool error; every `status: "refused"` with `owner_notice` followed by prose telling the player (`status: "unmodelled"` is not a refusal).
   * With `--db`: closed scene stamps match session calls; every person given a part exists as an actor row (people named inside `cutaways` blocks are ignored); a lie stamped `true: false` left a `holds_true=0` belief with its hearers; walk-outs hold no later beat; acting in a stamp on an unseen cutaway (`circle_reactions` with `cutaway_day` set and `told_day` empty, or a `knowledge`/media row with `cutaway_day` set where he holds no own `knowledge` row) is a hit; each open thread in a recap (debt, promise, meeting, plan) must have a backing row (obligation, concern, venture, scheduled effect, pending decision, or stamp).
* Verify: Canned transcript + DB unit tests; run on `docs/playtests/2026-11-25-dominic-2.txt` and confirm hits on the known faults.

## Task 11: Brief and change-based read budget

* Files:
   * Create: `connector/brief.py`, `tests/brief_budget_test.py`.
   * Modify: `connector/views.py` (`compact_scene` builds on `brief.full`; fields/numbers, not engine sentences), `connector/store.py` (`note kind=scene` returns `brief.full`), `connector/timeflow.py` (`advance` returns `brief.full` + skip-only fields + `cutaways`), `connector/server.py` (in-scene `act`/`money`/`note` carry `brief.changed`; `close_scene` carries `cutaways`; drop `details.move` from `act` description).
   * Modify: `engine/texture.py` (remove `claims.cutaways` from `outside_his_knowledge` in brief), `engine/outings.py` (`go_out` returns `crowd` via `routines.where`, place character, `standing_here`, and 1–3 true crowd facts; delete happenings draw, `you_may`, `approach`), `engine/findings.py` (silent record returns `unknown`).
   * Modify: `engine/player_operations.py` and `connector/acting.py` (`act` returns dollar numbers in `amount`/`short_of` with plain-fact summary, removing scale-word-only rule; `act(outing)` with target puts person in company for an ordinary scene).
   * Modify: `worlds/saintjude/levels.json` (`cutaways.floor`).
* Requirements:
   * `brief.full(conn)` (read-only) keys in order: `waiting_on_you`, `you` (lingering injuries/health, police interest, debts, known grudges, open promises/meetings with since-when, what he runs + changes since last closed scene, open BZ1 ventures, `standing_here`), `present` (name, body, manner, temperament/tie in words, top 3 `on_their_mind`, `about_to`, `has_news_for_you`), `crossing_your_path` (within 7 days), `news`, `money`, `texture`.
   * Personal scenes (no subordinates present) carry only urgent seat matters.
   * `cutaways` appear only on `advance` and `close_scene` results (never in `brief.full`/`changed`). Sources: `circle_reactions` + `spread`/`publish_media` items about him above `cutaways.floor`. Reactions only—never pending decisions, plans, or nominations. Marked shown once (`cutaway_day` on `knowledge` row or `publish_media` row). Quiet weeks return none.
* Verify: Key order, no off-scene plans, `changed` < 600 chars, no machinery words, no cutaways in mid-scene brief, cutaways show once across two distinct `advance` call IDs (`p1`/`p2`), quiet week returns no cutaways, `act(pay)` returns numeric `amount` without `"modest"`, `act(outing)` puts target in company without `outcome`, `prose_share < 0.2`.

## Task 12: Storyteller rulebook & `unmodelled` free actions

* Files:
   * Modify: `connector/rulebook_core.md`, `worlds/saintjude/rulebook_section.md`, `tests/connector_resume_test.py`.
   * Modify: `engine/free_operation.py`, `connector/acting.py`, `tools/gm_check.py` (if its refusal check reads anything other than `status: "refused"`).
* Requirements:
   * Rewrite `rulebook_core.md` as tight storyteller principles (scene lifecycle, division of labour, `owner_notice` rule, never refuse an ambition, never push to rise, no menus/meta-prompts, ordinary is ordinary, no moralising, play from world state, nominations, cutaways). Parameter shapes belong in tool docstrings, not the rulebook.
   * `free_operation`: unmatched intents return `status: "unmodelled"` (nothing applied, no `owner_notice`, no `gm_check` hit) naming the record path (scene stamp with `known_to`, `money`, `author`). Keyword list and `kind` hint stay.
* Verify: `act("operation", "he has a forger make up a new title deed")` returns `unmodelled` with record path and no `owner_notice`; `gm_check` reports no ledger hit; `--quick` passes.

## Task 14: Nominations, conduct, and agency guards (built as 14a, 14b, 14c)

* Task 14a (`near`, nominations, life hooks):
   * Files: Create `engine/nominations.py`, `engine/levels_tick.py`, `tests/nominations_test.py`. Modify `engine/simulation.py` (register weekly `levels` after `life_matters`), `engine/life_matters.py`, `engine/outings.py`, `engine/opening_family.py`, `engine/household_life.py`, `engine/civilian_life.py`, `engine/temptations.py`, `engine/org_happenings.py`, `connector/server.py` (`note(kind="plan")`, `realizes` on `author`/`close_scene`), `connector/brief.py`, `connector/timeflow.py`, `worlds/saintjude/levels.json`.
   * Requirements: `near(conn, day)` = active via `close_rule` + household + kin + ties + recurring + scene dealings within `lock_quiet_days` + event-affecting-him (distant movers active only by seat are NOT `near`). Life draws run for everyone (active included): `near` -> nomination; else apply directly with stored cause. Routine changes never nominate. `apply_overdue` applies plain form past `by_day`, NEVER for `seat_decision` (marks `lapsed`, notifies path). Past-due `stated` decisions involving him become `waiting_on_you` under `decision:<id>`; others lapse. Invented/realized people get routine, `levels.refresh`, purse, and life profile.
* Task 14b (`conduct`):
   * Files: Create `engine/conduct.py`. Modify `engine/scenes.py` (unmet past-due thread -> broken promise), `engine/levels_tick.py`, `worlds/saintjude/levels.json`.
   * Requirements: `conduct.weekly` checks `neglect` (ordinary `advance` skips count as shared time with co-located routine people unless an exception keeps him away), `wronged`, `broken_promise`, `jealousy`; `conduct.lies` checks `holds_true=0` beliefs when truth-holder shares household/routine/scene with believer. Max 1 open nomination per person. Store source keys (`stamp:<id>`, `obligation:<id>`, `knowledge:<id>`, `quiet:<person>:<day>`) in payload; skip any key already present in a nomination of any status.
* Task 14c (agency guards & seat decisions):
   * Files: Modify `connector/acting.py`, `connector/server.py`, `engine/nominations.py`, `engine/hearsay.py`, `connector/brief.py`, `worlds/saintjude/levels.json`, `engine/org_succession.py`, `engine/org_coup.py`, `engine/crime_response.py`, `engine/org_choices.py`, `engine/outfit_choices.py`, `engine/org_money.py`, `engine/org_happenings.py`, `engine/business.py`, `engine/civic_tick.py`, `engine/civic_votes.py`, `engine/prison_review.py`, `engine/prison.py`.
   * Requirements: Engine never chooses for protagonist (`civic_votes` prompts before `vote_day` or counts `absent`; `prison_review.weekly` skips him; `prison.admit` turns group assignment into an `inside_approach` nomination). `hearsay.waiting` prefixes every item: `life:<id>`, `seat:<nomination_id>`, `decision:<decision_id>` (bare int = `life:`). `_answer` routes `life:` -> `life_matters.answer`, `seat:` -> `nominations.realize(id, {"choice": how or answer})` (free text, no yes/no check; unmatched answer -> `stated` decision), `decision:` -> protagonist's due `stated` decisions (`yes`/`settled` = done with `how`, `no` = dropped). Routine seat running goes to second/manager and lists in `done_by_his_people`. Outfit insider news reaches tied crewmates as `pending_news`.
* Verify: All nomination/conduct/seat tests (including ID-collision prefix test, once-per-fact conduct test, overdue `seat_decision` lapse test) + 120-day hands-off test across councilman, soldier, owner, inmate asserting zero autonomous protagonist writes except `befell`, `upkeep`, `payroll`, `delegated`.

## Task 14d0: His outfit through the org core (built before Task 14d)

* Files: Modify `engine/ledger.py`, `engine/player_operations.py`, `engine/veto.py`, `engine/new_character.py`, `engine/free_operation.py`, `engine/authoring.py`, `engine/intake.py`, `connector/store.py`, `connector/authoring.py`, `connector/views.py`. Create `tests/outfit_org_core_test.py`.
* Requirements (when `systems.outfits` is on; Caerness keeps old layer):
   * `ledger.py`: `outfit:<id>` and `institution:<id>` of an org-core org both alias to `org_money.purse_ref` (living head's purse). Refuse self-transfer ("that is already his money"), refuse headless outfit ("the outfit has no living head to pay from"), `can_draw` head-only. `views.py` / `brief.full` / `cash_strain` count aliased purse once.
   * `player_operations.py`: move all ~20 outfit helpers to org core (`org_seats`, `org_units`, `org_tension`, `org_heat`, `orgs.seats_of`). `_org_behind` business order: owner's outfit seat -> outfit with highest weekly `org_lines` take at its location -> `None`.
   * `veto.py`: `held_by_other` reads `orgs.head_of`; world measures count org-core outfits/seats.
   * `new_character.py`: outfit start colleagues come from `org_seats`.
   * `free_operation.py`, `authoring.py`, `intake.py`: resolve, attack, and found outfits in org core (`org_profiles`, `org_units`, `org_seats`).
* Verify: Seat protagonist directly (no Task 14d `start_as`); run pay, hire, promote, retire, expel, order, truce, lean on business, attack (outfit and protected man), author org, and lookup under `conn.set_trace_callback` failing on any SQL naming `underworld_organizations|personnel|crews`. Test single-purse deduplication, headless refusal, `veto.held_by_other`, and `_org_behind` priority order.

## Task 14d: Starts at any scale

* Files: Modify `engine/new_character.py`, `engine/veto.py`. Create `tools/start_check.py`, `tests/start_scale_test.py`.
* Requirements:
   * Opening accepts a held seat (office, outfit head, company owner), moving the existing holder aside before day 0 as `retired`, `dead`, or `absent` (only if no kin/obligation/`lived_past` refs) with reason recorded. During play, `veto.held_by_other` still refuses.
   * `start_check.py --start <mechanic|businessman|politician|boss> --days 30 -> JSON` reports circle, holdings, open matters, personal nominations, city events, seat decisions, and world measures (`cause_share`, `events_per_kind`, `never_fired`).
* Verify: Boss and mayor starts displace holders while keeping history; all 4 starts have kin/friends, city events, non-all-single 22–30 friends, and non-empty `personal_nominations` over 120 days (reported at 30); outside-city counterpart (New York league office) survives refresh, routines, and a 25-day skip.

## Task 16 (Deploy 2): Pressure build-up and concerns

* Files: Create `engine/pressure.py`, `tests/pressure_buildup_test.py`. Modify `engine/levels_tick.py` (add `pressure.build` and `channels.run_due_effects`), `worlds/saintjude/levels.json` (`pressures`, `opportunities`).
* Requirements:
   * `build(conn, day, actor_ids) -> list[concern_id]` runs weekly for active people with plain package thresholds (no accumulators, cooldowns, or resignation):
      * `cash_strain`: `ledger.can_draw` over purse + owned businesses/holdings against weekly household need (deduplicating aliased outfit purses).
      * `work_restless`: wage earners only (skip seat holders and owners living on profit/tribute).
      * `office_threat`: office holders vs challenger standing and election date.
      * `opportunity`: for active business owners when business cash > cash line, or same-trade/district rival < struggling line.
   * Opportunity episode tracking: record cash-surplus episode in `actor_pressures` (`since_day` when cash rose above line; delete row when cash falls below). Do not open a new opportunity concern while any concern for that chance (any status, including `resolved`) has `opened_day >= since_day`. Struggling rivals are keyed per business.
   * Concerns resolve when their condition clears.
* Verify: Identical cash with different savings/kin tips at different weeks; clearing condition resolves concern; `materialized_minor` gets none; rich owner opens one opportunity concern and stays at 1 across 8 weeks after its decision fires.

## Task 17b (Deploy 2): Decisions falling due, and offers

* Files: Modify `engine/offscreen.py` (`fire_due`), `engine/levels_tick.py` (register weigh pass for active NPCs with live concern + `fire_due`; remove Task 14a's temporary past-due stated-decision cleanup), `engine/civic_graft.py` (`fraud_pass` skips movers), `engine/civic_corruption.py` (`put_on` for accepted `seek_payment`), `engine/hearsay.py` (`waiting` includes pending offers with `offer_to_actor_id = me` and `told_day` set under `decision:<id>`), `engine/business.py` (`expand`), `engine/player_operations.py` (shared payment/ownership transfer used by both `trade` and `buy_out`), `connector/acting.py` (add offer accept/refuse branch to `_answer`'s `decision:` handler). Create `tests/offscreen_fire_test.py`.
* Requirements:
   * `fire_due(conn, day)` executes due decisions on one causal chain under `rollback.current`. Due decisions by or aimed at someone `near` him become nominations; distant ones fire directly. Fired decisions aimed at an active person open an `other_act` concern.
   * Visible fired steps (`buy_out`, `expand`, loan, hiring, alliance) start a `spread` row from witnesses (and a paper item if named business or above `visible_spend`); intent itself stays private.
   * Ambition actions: `expand`, `buy_out` (uses shared transfer), `propose_alliance`. Once an opportunity decision fires, set its `opportunity` concern to `'resolved'`.
   * Officials: `seek_payment` (via `civic_graft.weigh` + `civic_corruption.put_on`) and `rig_count` (via `races.commit_fraud`; `fraud_pass` skips movers).
   * Untold offers never lapse; `stated` decisions with no engine effect enter `waiting_on_you` under `decision:<id>`.
* Verify: `pressure_business` shock chain, `other_act` concern, untold vs told offer lapsing, `office_threat` decision firing, `buy_out` spread without leaking intent, `seek_payment`/`rig_count` without `fraud_pass` double-rigging, and answering an offer via `decision:<id>`.
