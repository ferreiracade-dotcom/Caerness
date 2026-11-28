# Deploy 1 and 2 invariants (working reference: the plan is the source)

Gemini's one-page summary through revision 6.13, filed 2026-11-28. Where it and `docs/superpowers/plans/2026-11-26-three-levels-build.md` differ, the plan wins.

## Core Split
- Engine = facts, memory, numbers, causes, named vetoes. Never decides for the protagonist.
- GM = prose, scenes, inventions. Never refuses an ambition for lack of a model.
- No psychology simulation, no hard caps, no scale-word-only money hiding.

## Switches (`engine/world_package.py` `SYSTEM_KEYS`)
- Add: `personal_choices`, `belief_mirror`, `entity_resolution`, `rumour_broadcast`, `psychology`, `mortality_audit`, `presence_habits`.
- `worlds/caerness/world.json`: all 7 `true`. `worlds/saintjude/world.json`: all 7 omitted/false.
- Guard `cultivation.assign_birth_core` on `system_enabled(conn, "cultivation")`; migration deletes SJ `cultivation_profiles`.

## Placement (`engine/routines.py`)
- `where(conn, actor_id, day, part)` (`morning|day|evening|night`) is the single source of truth; `company`, `household_life`, `authoring` use it alone (no presence fallback).
- Order: exceptions (custody/prison/serving/active travel) -> institution meeting (1 deterministic evening/week per club/diner/parish) -> stored routine -> on-the-spot household+work -> `None`.
- `note(kind="scene")` and `gm_scenes` accept optional `part` (never moves backward within a day).

## Levels, `near`, and Nominations
- `near(conn, day)` = active via `close_rule` + household + kin + ties + recurring + scene dealings within `lock_quiet_days` + event-affecting-him. Distant movers are `active`, NOT `near`.
- Life draws run for everyone (including `active`). `near` -> nomination; else apply directly with stored cause.
- `nominations.status` CHECK: `('new','planned','realized','declined','applied','lapsed')`.
- `apply_overdue` NEVER executes `seat_decision`: marks `lapsed`, notifies path (council vote = `absent`).
- `conduct.weekly` / `conduct.lies`: store source keys (`stamp:<id>`, `obligation:<id>`, `knowledge:<id>`, `quiet:<person>:<day>`) in payload; skip any key already in a nomination of any status. Ordinary `advance` skips count as shared time with routine co-located people.

## `waiting_on_you` & `act(answer)`
- Prefixes in `hearsay.waiting`: `life:<id>`, `seat:<nomination_id>`, `decision:<decision_id>` (bare int = `life:`).
- `seat:` -> `nominations.realize(id, {"choice": how or answer})` (free text, no yes/no check).
- `decision:` -> Deploy 1 handles protagonist's due `stated` decisions (`yes`/`settled` = done with `how`; `no` = dropped); Task 17b adds `offer_to_actor_id` accept/refuse.
- `free_operation` unmatched intent -> `status: "unmodelled"` (no `owner_notice`, no `gm_check` hit), naming record path.
- `act` results return dollar numbers in `amount`/`short_of`. `act(outing)` with target -> ordinary scene (no `outings.approach`).

## Cutaways & `brief`
- `cutaways` appear ONLY on `advance` and `close_scene` results, never in `brief.full`/`brief.changed`.
- Sources: `circle_reactions` + `spread`/`publish_media` above `cutaways.floor`. Reactions only, never pending decisions/plans. Marked shown once (`cutaway_day`). Ignored by `gm_check --db` actor-row check.
- `brief.full["you"]` includes open BZ1 ventures and `standing_here`.

## Outfits on Org Core (Task 14d0)
- Under `systems.outfits`, `outfit:<id>` and `institution:<id>` alias to `org_money.purse_ref` (living head's purse): shown once in money/means, self-transfer refused, `can_draw` head-only, headless refuses.
- `_org_behind` business: owner's seat -> top weekly racket take at location (`org_lines`) -> `None`.
- SQL watch test fails on any query touching `underworld_organizations|personnel|crews`.

## Global Agency Constraint (Task 14c)
- 120-day hands-off test across councilman, soldier, owner, inmate: zero autonomous protagonist writes except `befell`, `upkeep`, `payroll`, `delegated`.