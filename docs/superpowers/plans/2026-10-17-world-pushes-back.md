# Gap 4b: the World Pushes Back — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Outfits earn, hold ground, pay their people and fight each other; rivals notice and answer what the protagonist does; unpaid or mistreated members, staff and servants grow disloyal and leave, defect or inform.

**Architecture:** Mostly reconnection. The audit (`docs/superpowers/notes/2026-10-17-gap4b-audit.md`, binding for line references and hook points) found the outfit tick skips orgs without a heat row, the attack/turf code has no callers, player operations write no org-level traces, there is no payroll, and loyalty never moves. Reuse existing functions (`collect_monthly_income`, `_territorial_attack`, `_targeted_hit`, `_take_vacant_turf`, `add_zone_challenger`, `change_relation`, `protect_business`, `ledger.transfer`, `_resolve_service_terms`) and DEC-01 candidates in `engine/underworld_decisions.py`. One migration (113) repairs existing worlds.

**Tech Stack:** Python 3.13, SQLite, plain-script tests (`PYTHONPATH=<repo>;<repo>/tests`).

**Spec / sources:** audit note above; connector spec §5 (no engine figures in prose); underworld canon notes `2026-10-17-underworld-canon.md` (ecosystem not pyramid [1618]; violence is costly and mostly contingent; Closed-Core/Churn rules); owner rulings in memory (power sex ratios; occupation follows Stage).

## Global Constraints

- Universal: every rule applies to every outfit, business and household, the protagonist's included; nothing special-cased by name.
- Violence is per outfit, not a world cap (owner ruling 2026-10-17: the world's culture is one of power and violence; canon's "controlled violence" lines are about particular outfits: Tallow [1739], Greyhook [1742], access brokers [1746]). General canon: street gangs rise and disappear quickly; durable power owns property, keeps fronts, pays people and manages succession [1734]; no thieves' court, disputes settled by family, intermediaries, control of the asset [1774]; reputation substitutes for law, violence is a backstop [1775]; a city tolerates a family until rising violence or a crossed line [1771]; a cultivated fighter outclasses ordinary guards [1680].
  - Each outfit gets a violence temperament (propensity 0–1 and a preferred style) from its type and canon character, its leader's drives (aggression, patience), the Stage of its fighters, and its place: street gangs volatile and quick to violence; durable families and syndicates controlled, using selective examples; specialists (fences, brokers, lenders) rarely violent themselves, buying it (enforcers, Cormorants) when needed; coercive vice and debt collection violent toward the weak. Canon outfits take canon character (Tallow controlled with younger branches hotter; Greyhook contingency).
  - Styles: intimidation and threats, beatings, smashed or burned premises, seizing goods, abduction, a duel or challenge between cultivated enforcers, a hired killing (Cormorants/freelances; Reckoning only for the rich and rarely), a public example. Pick by temperament, target and what the outfit can field.
  - Costs make it plausible, not caps: heat and the city's tolerance (rising violence brings the watch, cultivated officers, a magistrate's crackdown [1771]), losses in men and Stage-weighted strength, retaliation, damage to the outfit's own income. Deals and intermediaries [1774] are a common answer between durable outfits; street gangs fight more and die more.
  - Street gang churn [1734]: weak or beaten street gangs collapse and new ones rise in cities with room, over months and years (reuse the seeding helpers; names and leader sex as for schema 110).
  - Calibration is a plausibility check, not a target: report a 365-day run by outfit type and city (moves, styles, deaths, collapses, new gangs) and make sure violent cities and outfits differ visibly from quiet ones.
- Money stays in engine units; no new currency. Payroll is calibrated so the median outfit, business and household with ordinary income stays net positive; insolvency only from real causes.
- No numbers reach the GM's prose: connector shows words ("two months behind on the crews' pay", "the Stone Boars are angry").
- 30-day advance on the packaged world may grow at most 15% over the schema 112 figure (measure before and after with the same script).
- Never write `data/caerness.db` except the final regeneration; tests on temp copies. `git add` specific files only.

## Review Focus

1. The protagonist's org is now a real participant: the player himself is skipped by decision loops (`simulation.py:280`), so his underboss may act for the outfit; that must never spend his treasury or start a war he did not order beyond routine (delegate, invest small). Hostile initiatives for the player's outfit need an order through `act`.
2. Rivals' answers to the player land on him for real (a racket suppressed, a crew hurt, a business pressured, a challenge on his zone), each with an incident and news the scene shows.
3. Payroll arrears never go negative or double-charge across a missed month; paying arrears through `act` pay restores loyalty gradually, not instantly.
4. Defection moves real people (personnel rows) and only to an outfit in the same city; desertion returns people to ordinary life (occupation per Stage rule, no 'criminal' label).
5. Migration 113 is idempotent and leaves live saves that already earned money untouched (treasury seed only where treasury = 0 and no finance rows).

---

### Task 1: Every outfit ticks and earns; businesses pay their owner

- `create_underworld_organization` (`engine/underworld.py:202`) calls `ensure_heat_profile`; fix `tests/fixtures_protagonist.py:17` the same way.
- Factor `monthly_net_estimate(conn, org_id) -> float` out of `collect_monthly_income`.
- Owner's draw: monthly, each active business pays its owner a share of cash above a working floor (keep ≥ 2 months of operating cost; draw ≤ 50% of the excess) into the owner's household liquidity (or purse if no household), via `ledger.transfer`, in the existing business monthly step.
- Migration 113: heat rows for active orgs lacking one; `treasury = round(3*monthly_net_estimate, 2)` where treasury = 0 and the org has no finance rows; report in `engine_meta schema113_report`.
- [ ] Test `tests/world_pushes_back_test.py::money`: a fixture outfit without heat row now earns over 30 days; Fane-like fixture treasury > 0 after migration; business owner's household liquidity rises over 90 days while business cash stays ≥ floor. Commit.

### Task 2: Ground and relations

- Protection conflict: an outfit's own controlled front is never protected by another outfit. Migration 113 ends opening protection accounts held by a rival on a business that is a `controlled_front` of another org or owned by that org's leader, and files a `protection_dispute` incident and a rival relation (hostility ~50) between the two (the rival lost income; it will remember).
- An outfit with fronts or rackets in a city and no zone claims the zone where its fronts sit if vacant, else becomes challenger on it (`add_zone_challenger`); reuse `authoring._claim_ground` logic.
- Seed baseline `underworld_relations` between outfits sharing a city (neutral/rival by overlap of activities and zones; hostility 10–40).
- [ ] Test `::ground`: after migration the Fane-like outfit holds or contests a Toll's Reach zone, no rival protection account remains on its fronts, and a rival relation exists with each former protector. Commit.

### Task 3: Rivals act

- Add DEC-01 candidates in `underworld_decision_candidates`: `occupy_vacant_turf` (`_take_vacant_turf`), `challenge_zone` (`_territorial_attack` or `add_zone_challenger`), `poach_protection` (protected business in a zone the actor controls or contests, protector weaker locally), `targeted_hit` (`_targeted_hit`, only with relation hostility ≥ 58). Utilities from drives (aggression, ambition, patience), relative strength and hostility; each records an operation, an incident against the target org where there is one, heat, and an event.
- Extend the incident query (`underworld_decisions.py:48-50`) to `protection_poach, protection_dispute, attack_on_client, attack_on_member, extortion_attempt, territorial_challenge`.
- `retaliate` gets a real effect against the source org: suppress one racket for 30–60 days, or `record_harm` on a member, or a challenge on its zone (pick by what the source has).
- Temperament, styles, costs and street gang churn per Global Constraints; violence outcomes weigh the Stage of the fighters on each side.
- Add a `negotiate_settlement` candidate (intermediary, split, payment) whose utility is higher for durable outfits.
- [ ] Test `::rivals`: over 365 days on the packaged world copy, street gangs make more hostile moves per outfit than durable families/syndicates and specialists the fewest; at least one street gang collapses and one rises somewhere; heat from violence brings a law response in at least one city; a fixture rival with hostility ≥ 58 toward the Fane-like outfit acts against it within 180 days, by a style that fits its temperament. Commit.

### Task 4: The protagonist's acts leave traces

- In `engine/player_operations.py` `_attack` and `_demand` (and any extort/take-over path): find the victim's outfit (personnel org, else protection account protector, else business-link owner, else zone controller per audit line 57) and write an `underworld_incidents` row (`attack_on_member`, `attack_on_client`, `extortion_attempt`) plus `change_relation(hostility +15..+30)` and heat on both.
- [ ] Test `::player_traces`: attack on a business protected by a rival → incident + relation; within 90 days the rival answers (warn/retaliate/negotiate operation recorded). Commit.

### Task 5: Pay

- Monthly payroll, through `ledger.transfer`, with an arrears counter (months unpaid, in metadata or a small table):
  - outfit: each active personnel member is paid from the treasury by role weight (boss draw already exists; underboss 3, lieutenant/crew leader 2, specialist 1.5, member 1, peripheral 0.5 units of a base wage set so payroll ≈ 35–45% of median gross);
  - business: staff pay folded out of operating cost into an explicit payroll line paid from business cash (headcount from existing employment rows or capacity), no double-counting with the existing cost;
  - household: servants and stewards paid from household liquidity, falling back to the head's purse (replaces the implicit 0.08/member charge).
- `act` `pay` can pay arrears for an outfit, a business's staff or the household (check how `pay` targets today; extend with a `wages` target).
- [ ] Test `::pay`: normal outfit/business/household net positive over 180 days; a zero-treasury outfit accumulates arrears, never negative balance; paying arrears via act clears the counter. Commit.

### Task 6: Loyalty and its consequences

- Monthly drift: crew loyalty/cohesion, personnel loyalty (add a column or metadata if absent), `relationships.loyalty` toward the head, and service-term loyalty/satisfaction fall with arrears (−4 to −8 per month unpaid), with recorded harm/threats by the head (reuse the culture treatment memory), and rise slowly (+1 to +2 per month, toward 60) when paid and untroubled.
- Consequences, each rare, thresholded and recorded with an event and news:
  - desertion: personnel with loyalty < 25 for 2 months may leave; ordinary life per Stage rule;
  - defection: a crew or member with loyalty < 20 and a rival in the city may go over (personnel rows move; incident `defection`; relation hostility up);
  - informing: low-loyalty member may raise the outfit's heat and seed a rumour;
  - theft: a low-loyalty accountant/treasurer may skim the treasury;
  - servants: a service term with satisfaction < 25 or 2+ months unpaid may end mid-term (`_resolve_service_terms` gains a monthly check);
  - business staff: 2+ months unpaid lowers business capacity/condition.
- Connector: holdings/scene show words for morale and arrears ("the crews are grumbling", "Nolan Pell has not been paid in two months") and these events in news; rulebook gains one bullet under the House line (unpaid and mistreated people leave or turn; the engine decides). Resume budget holds.
- [ ] Test `::loyalty`: with pay withheld 4 months a fixture outfit loses members (desertion or defection, recorded), a servant leaves, and morale words appear; paid outfits over 365 days lose no one to these paths beyond background turnover. Commit.

### Task 7: Migration, regeneration, timing

- Migration 113 per Tasks 1–2 (and any columns from 5–6), idempotent; `tests/schema113_test.py` (from schema 112 packaged copy: heat rows complete, treasuries seeded, protection conflicts ended, relations seeded, report present).
- Regenerate `data/caerness.db` from the committed schema 112 file through the normal open path; integrity_check; no -wal/-shm.
- Measure 30-day advance before/after (≤ +15%).

**Final test list:** world_pushes_back_test, schema113_test, schema112_test, player_operations_test, interactions_standing_test, standing_test, underworld_ecology_test, schema110_underworld_test, v60_underworld_rebuild_test, v60_phase2a_test, connector_views_test, connector_resume_test, connector_act_test, connector_server_test, connector_author_test, authoring_test, tenyear02_underworld_person_reservoir_defer_test, any `*household*`/`*service*`/`*business*` tests.

**Not in this plan:** new-character flow and servants seeded into wealthy opening households (gap 5); currency/wage canon (gap 6).
