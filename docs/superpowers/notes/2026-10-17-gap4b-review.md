# Gap 4b review (Opus, 2026-10-17): findings to fix

Commits reviewed: e6ce565, 9b29a0b, 31f2c5c, 871b651, fa4e7e8, bff7fff. Probe scripts are in the session scratchpad, `review4b/`.

Calibration over 365 days, reproduced: 54 hostile moves; 1 hit, which failed; 3 territorial attacks; 0 named deaths. Defections, desertions, informants, thefts and servants quitting are all 0. 8 gangs collapsed and 6 were founded. Timing for the year is +15%, right at the ceiling; the 30-day advance is +4–12%.

## Critical

**C1. The player is immune, which breaks the rulebook ("never invent survival") and the rule that nothing is special-cased.**

Where the exclusions are:
- `underworld_rebuild.py:2019`: hits exclude `player_actor_id`.
- `underworld_aggression.py:174`: `_members_of` excludes him from beatings, duels, abductions and public examples.
- `underworld_aggression.py:95` and `:384`: the player's outfit gets no candidates at all.
- `underworld_decisions.py:315`: the player's outfit never retaliates.
- `underworld_decisions.py:612`: his gang can never collapse.

The plausible rule:
- He is a valid target, chosen the same way as anyone else.
- Attempts on anyone resolve through `record_harm` in outcome bands (failed / wounded / maimed / killed). They are not a binary `mark_actor_deceased`. The odds are weighted by Stage, guards and where the target is.
- When both outcomes are plausible, the result leans toward survival with real consequences: injury, a man lost, a front lost, flight. Death only when the odds are overwhelming.
- An attempt on the protagonist surfaces to the GM as a pending incident to play. It does not resolve off-screen during `advance`.

What his outfit may do on its own:
- It defends itself: passive defence, plus proportionate in-kind retaliation to incidents aimed at it.
- It does not occupy turf, negotiate, challenge, poach or make targeted hits without an `act` order.

Smallest fix:
- drop the two `player_actor_id` exclusions;
- route lethal outcomes through harm bands;
- make `leader_is_player` filter only HOSTILE_KINDS, not retaliation.

**C2. Loyalty consequences fire only in fixtures, never in the real world.** (`payroll.py:12-13`)

Why:
- Payroll is 3.6% of kick-up income; the plan said 35–45% of gross.
- Named personnel are only bosses (251) and crew leaders (41).
- Treasuries pile up and nobody is in arrears.
- Crew loyalty stays at exactly 60 everywhere after a year.
- The thresholds (<20 or <25 for 60 days, starting from 55) mean everyone crosses together after about six months.

Fix:
- set wages to the plan's share of gross, with rank and file paid too, or make the boss's take the residual;
- use a smooth hazard that rises as loyalty falls, instead of thresholds;
- seed per-person loyalty dispersion;
- add drivers beyond pay: lost fights, dead comrades, succession, a richer or stronger rival in town pulling people away, heat or crackdowns making informants.

## Important

**I1. Why the world is tame.**

What the report found:
- 223 of 254 outfits are specialists, 28 are street gangs and 3 are durable. Specialists get no turf, challenge or poach candidates (`underworld_aggression.py:120,130`), and their tradition value is 0.10–0.14.
- Only 6 cities have two or more ground-holding outfits, and 28 of 315 zones are controlled.
- Violence happens only between outfits. There is none toward debtors, brothel workers or extorted shops, although 28 high-risk-debt and 23 brothel-protection rackets exist.
- Specialists never buy violence.
- Hits need hostility ≥58 and a `rival` or `war` relation. Negotiation relabels the relation `hostile_peace` while hostility stays at 96, which removes it from the hit pool (`:158`).
- There are no named people to hit, so public examples fall on anonymous losses. One gang beat the same man six times.

Fix, with no world caps:
- coercive rackets cause harm to clients and debtors, at a rate set by temperament and heat;
- specialists who are wronged hire Cormorants or freelances;
- gangs prey on specialists (extortion, robbing fences);
- hits are allowed under `hostile_peace` when a grudge is high;
- outfits get named personnel (lieutenants, enforcers, members) seeded from the background reservoir, so there are people to hurt, promote and lose. Leader picks follow the 92/85/70% male rule and occupation follows Stage.

**I2. Style outcomes ignore the target's strength.** (`underworld_aggression.py:219-289`)
- `_s_beating`, `_s_smashed_premises`, `_s_seized_goods`, `_s_abduction` and `_s_public_example` always return win=True.
- Fix: roll the win against `_log_ratio` plus the Stage edge, as `_s_intimidation` already does. A lost roll becomes a failed move with losses.

**I3. The grudge hook practically never fires.** (`temperament.py:921,927`)
- It needs the victim or the victim's kin to be a boss, underboss or lieutenant, and the world has no lieutenants. 0 grudges were created in a year.
- A killing of an ordinary member creates no grudge.
- Fix: include crew leaders (smaller amount), and add a small grudge for any fatal blow on a member.

**I4. Business wages are charged twice.** (`payroll.py:116-134` with `business.py:375-379`)
- The deficit is already capitalised into `debt`, and the unpaid labour is also recorded as arrears. The catch-up then debits cash without reducing debt; `pay_arrears(kind='business')` does the same.
- Fix: on catch-up or payment, set `debt=MAX(0,debt-paid)`, or keep unpaid labour out of the debt.

**I5. Household arrears are forgiven between book closings.** (`payroll.py:163-182`)
- `total_due = due*scale` with `scale = 1+owed/month_due` drops prior debt when books close every 5–25 days, and doubles it when they close after more than 30.
- As a result, "unpaid 2+ months" can never be reached.
- Fix: `total_due = due + prior owed`. The pay test must assert `months_behind >= 2` after 90 unpaid days.

**I6. A rival's beating counts as mistreatment by the victim's own head.** (`loyalty.py:45-50`, `:215`)
- Fix: also require the harm's source organisation to be this outfit (or, for servants, the head of the household), or the victim's head to be the player.

**I7. A defector still leads his old crew.** (`loyalty.py:148-150`)
- Fix: clear `underworld_crews.leader_actor_id` for his old outfit's crews.

**I8. The `general_store` archetype doesn't exist, so seeded fronts never run as businesses.** (This predates 4b.)
- Scope: 0 of 54 seeded fronts and 120 of 152 enterprises have no business profile. `create_front` defaults to it (`underworld_rebuild.py:1154`; callers at 1460 and 1514; both `underworld_ecology` front calls). The error is swallowed at 1175-1179.
- Consequence: the owner's draw fired 0 times in a year. The 32 profiled opening businesses have no person owner.
- Fix:
  - map the front kind to a real archetype;
  - stop swallowing the error;
  - backfill profiles in a migration;
  - give unowned profiled opening businesses an owner where one plausibly exists (a person from the place's reservoir), or let their profit go somewhere real.

## Minor (fix these too: they break owner rules)

**M1. Digits reach the GM.** `payroll.arrears_words` ("3 months behind") feeds `connector/views.py:158,203`. Reuse `_nword`.

**M2. Fixed absolute caps.** These break the owner's veto principle:
- ransom ≤3, seized goods ≤4, skim ≤3, settlement ≤2.5 and a flat killer fee of 3 (`underworld_aggression.py:244,258,296,435`; `loyalty.py:197`);
- one defection per month (`loyalty.py:103`);
- crackdowns: a 90-day per-city cooldown, a tension threshold of ≥2.4 and a top-3 limit (`:488-493`).

Make each one proportional to treasury, cash, tension or hazard.

**M3. Gaps in the loyalty paths.**
- `desert()` records no membership flow.
- The `defection` incident is missing from the DEC-01 incident query.
- `_rival_in_city` may pick an ally or the player's outfit. It should pick a plausible rival, and never the player's outfit without his order.

**M4. Wrong words for the wider incidents.** Responses to `attack_on_member` and other incidents still use `*_protection_poach` kinds and the "poaching attempt" rationale (`underworld_decisions.py:61-75`).

**M5. `schema113_test` does not test a real 112 save.** It fakes 112 instead of starting from the real committed schema-112 DB (`git show 39b35da:data/caerness.db`). Re-running `_migration_113` also overwrites `schema113_report` with zeros.

## Fine as is

- Outfit payroll and arrears never go negative.
- Migration 113 is idempotent and seeds treasury only where it is zero.
- Deserters follow the Stage rule.
- Gang churn follows the sex rule and produces no digit names.
- Succession re-derives temperament.
- The owner's draw is recorded with the `distribution` kind.
- The `dec01` test change is legitimate.
- The player's underboss cannot start hostile moves.
