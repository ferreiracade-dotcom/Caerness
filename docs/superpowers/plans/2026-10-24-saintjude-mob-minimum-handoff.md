# Handoff: the Saint Jude mob minimum

**Written:** 2026-10-24. **Branch:** `feat/world-packages-saintjude` (HEAD `07be394`, not pushed). Read `AGENTS.md` first, then this file. The design below was agreed with the owner in conversation; it is not yet a spec or a plan. Next agent: write the spec from this, have it approved, then plan.

## 1. Why this is next

Saint Jude cannot be played yet. Two things stop it:

1. **Reach.** The Oracle VM runs the older `feat/claude-connector` code, and a connector serves one campaign whose world is fixed at creation (`connector/campaign.py`, `CAERNESS_WORLD_PACKAGE`). The owner wants one connector holding both worlds: "resume Saint Jude" / "resume Caerness". This is small and can be done before or alongside the mob work.
2. **The mob is names only.** In `data/saintjude.db` the four families (Sabatini, Vannucci, Ferrante, Pellegrino) are `institution` actors with 63 office memberships. There are 0 underworld organisations, 0 crews, 0 rackets (`economic_interests`), 0 law jurisdictions, and no goals. A public killing brings no response (play test case C). Over five game years the record holds only births, deaths and unions. For a mob game this is game-breaking.

The mob minimum below is what the owner wants built before playing. Not needed yet: the narcotics dial (E-021, E-027), offices with terms (E-019), weekly/annual cycles (E-025), taboo reactions (E-022), the deflator (E-013), the Narration Standards file.

## 2. Numbers (from `worlds/saintjude/design_figures.json`)

| | Sabatini | Pellegrino | Ferrante | Vannucci |
|---|---|---|---|---|
| Made men, default (range) | 57 (50-60) | 45 (40-50) | 44 (40-50) | 36 (30-40) |
| Associates per made man | 6.7 | 6.7 | 7.0 | 6.2 |

- Total about 180 made men and 1,200 associates. Capos: one per 8 men, at least 2 per family.
- The Ladder: associate to soldier 22.5% of net, soldier to capo 18.3%, capo to boss 11.7% of regime net (all Tendency draws).
- Rackets are citywide pools with family shares (`pools.*.shares`), for example Vannucci has 89% of carting and 78% of the Strip. Vannucci gross about $11.6M a year, Pad $0.53M, net $11.1M, about $317,000 per made man (`allocation.family_gross_net_9_3`).
- Figures are drawn once per run by `engine/design.py` and held.

## 3. The agreed design

### 3.1 One ladder of detail for everyone

Every person in the city sits on the same ladder. Mob, other gangs, police, businessmen and civilians all follow it.

1. **In a group:** a count only (neighbourhood population by trade). Ordinary residents.
2. **Light record:** age, a few traits, job, place; no history. The rest of the police force, honest businessmen, union rank and file: people who could be drawn in by a bribe, a debt or a shakedown.
3. **Active, deciding weekly:** associates, soldiers, ordinary gang members, Pad cops, smaller connected businessmen.
4. **Active, deciding daily:** bosses, underbosses, consiglieres, capos and the other gangs' equivalents; the top police (commissioner, chiefs, key detectives); the businessmen and officials who really matter; plus anyone temporarily busy (3.3).

**Pulling up.** When the simulation needs someone it takes him from the level below, never from nothing: a new associate from the neighbourhood's young men, a detective from the department, a bar owner from that neighbourhood's bar owners, a new made man from the family's associates. He keeps everything he had and only gains detail, and the group's count drops by one so the numbers always add up. This is the engine's existing pattern (background identity profiles resolved into actors: `engine/person_ecology.py`, `resolution_controller._materialize_latent_person`); extend it, do not replace it.

**Moving down.** A man who goes quiet drops from daily to weekly; one who leaves the life becomes a light record. Anyone who has been pulled in never becomes a bare count again: his name and deeds stay on record.

### 3.2 What exists at the start of a run

- **Full people:** boss, underboss, consigliere and capos of each family, and the other gangs' leaders. Seeded Examples are used where the seed has them; Open roles are invented here.
- **Made men (level 3):** every one, in a capo's crew. Record: rank, crew and capo, age, years made, personality (ambition, greed, loyalty, temper, caution), earnings and racket line, feeling toward his capo, and a name (drawn now because it is free and keeps him stable, not because it drives behaviour).
- **Associates (level 3):** every one, about 1,200. Record: crew and the soldier he answers to, age, two or three traits (ambition, temper, reliability), earnings, standing (how close he is to being proposed). No history.
- **Histories are written later**, when a man becomes important, and must fit his record (age, crew, years made). Wives, children and side contacts are created when they come up. This follows "opening vs run-time invention": the opening gets lived records, not invented biographies.

### 3.3 Daily versus weekly

- Importance sets the usual rhythm (3.1 levels 3 and 4).
- **Activity speeds a man up for a while:** an important job this week (a hit, a big collection, a delivery), a deadline (a debt due, an order, a meeting), danger (hunted, watched by police), a live conflict, or being near or involved with the protagonist. He decides daily until it is over, then drops back.
- It works both ways: a boss in prison, retired or delegating can drop to weekly. Anything that happens *to* a man (shot, arrested) is handled at once whatever his rhythm.
- **Weekly does not mean frozen.** Routine business runs automatically (collections, kick-ups up the Ladder); weekly only sets how often he chooses something new.
- Expected load: about 2,500 active people, of whom perhaps 100-200 decide on a given day. Not measured; measure on the PC and the VM.

### 3.4 Associates in particular

- Their weekly choice is mostly "keep doing what I do" (collect, run the game, drive, kick up). Only traits, a situation (debt, a slight, an opportunity, police pressure) or an order change it.
- **The real risk is noise.** Keep incident chances low, and raise an incident to the families only when it touches someone who matters: another family's ground, a made man, a cop, a big earner. That is tuning once built.
- **Being made:** when the books open, candidates are the associates with the best standing, so the family picks a real man with a record.
- **Far-off sparks:** an associate across the city can rob the wrong game or hit the wrong man. He is resolved to a full person at that moment, the incident lands on his soldier, capo and family, and the other family responds through the family-to-family relationship (sit-down, payment, killing). The protagonist may only hear of it.

### 3.5 Rackets

1. **Family holdings:** one per family per pool, with its share and yearly take, summing to the family's gross.
2. **Crew slices:** each crew holds slices of the family's holdings by its ground.
3. **Soldier lines:** every made man has at least one earning line ("a card game on Mercer Avenue, about $X a week"). This is the minimum: totals match the bible and every soldier earns.
4. **Weekly flow** up the Ladder (section 2 shares), the Pad paid as a cost.
5. **Made when needed:** the individual bar paying protection, the debtor, the runner, the game's address. Until then they are counts and amounts on a holding.

### 3.6 What lower ranks can do (the reason they are simulated)

- **Start a racket:** each made man (and associate, rarely) has a small weekly chance to act on ambition and greed, lowered by caution. He needs money, men and ground. The new racket is a new holding: an unclaimed part of a pool, a new pool, or someone else's share (a fight). He must kick up; hiding it and being caught is a serious offence. The GM or the player can start one through the same holding.
- **Kill his capo:** his record already holds the reason (a capo who takes too much, being passed over, an insult); personality decides whether he acts, since an unsanctioned killing of a made man is a death sentence. If it happens: the capo dies, the boss picks a new capo from the crew, the rackets stay with the crew, the killer is rewarded (sanctioned) or hunted, and the police get a homicide. Both men get full histories then.
- Counts stay true: deaths lower the made-man count; new made men come from associates.

### 3.7 Police and the Pad (minimum)

- A crime the engine records gets a law response: investigation, arrest or nothing, by the facts of the case. Saint Jude needs its jurisdictions (city, county, state, federal) loaded; `law_jurisdictions` is empty today.
- The Pad changes the response within its limits: it buys quiet on routine matters, but cases Part II 3.4 excludes (a public killing, among others) still bring an arrest (E-014).
- Pad cops are level 3 people with their envelope; the top police are level 4.

## 4. Owner rules that bind this work

From memory and `AGENTS.md`; read them, do not re-derive them:

- **Engine veto, not menu:** the GM proposes freely; the engine refuses only named contradictions. No closed lists of actions.
- **Violence is per outfit,** set by temperament and cost, never a world cap.
- **Loyalty beyond wages:** bonds and grievances drive loyalty; pay mostly matters for hirelings.
- **Power sex ratios:** made men are men; associates and connected roles are overwhelmingly male, never egalitarian.
- **Silent disconnection:** after building, check every new system actually fires (join keys, reachability) before tuning.
- **Package-aware, not Saint Jude-coded:** engine and connector hold no hard-coded Saint Jude values (`step1_diff.md` grep rule). Saint Jude data lives in `worlds/saintjude/`. The Caerness underworld (`engine/underworld*.py`, switch `caerness_underworld`, off for Saint Jude) is a parts bin, not a base.
- Run sims on a copy of the DB. Sonnet subagents implement, Opus reviews, and every diff is checked.

## 5. Suggested order

1. World switching in `resume` and the VM update (small; makes everything else play-testable on the phone).
2. Families, crews and the Ladder as data at the opening (3.2), from `design_figures.json` and the seed's Examples.
3. Racket holdings split to crews and soldiers (3.5), with the weekly flow.
4. Daily/weekly rhythm and the decision loop for levels 3 and 4 (3.3, 3.4, 3.6).
5. Law response and the Pad (3.7).
6. Measure: opening time, 30-day advance, five years, on the PC and the VM. Re-run the connector play test; case C must now bring an arrest.

## 6. Proposals for the open questions (agreed in principle by the owner, 2026-10-24)

These are proposals, not bible text; put them in the spec as such.

### 6.1 The other gangs (Part III 5, Part V)

- **In the minimum, with simulated members:** the Charlestown Brigades (Irish; the 50/50 with the Pellegrinos, union locals, arms to Ireland), the Eastside Combine (the policy game, retail heroin, the working arrangement with the Italians; the 1980s Kings grow from its young men), and the Iron Horsemen MC (muscle and crank, resentful of being used).
- **In small:** the Russians, "a handful" in 1975 (5 to 10 men), so the 1980s outfit grows from real men; the Puerto Rican bolita men, who hold the `bolita_tax` pool.
- **Not as gangs:** Jewish financiers and bookmakers cannot be made and are no family, so they are connected businessmen, one by one, at levels 3 and 4. Chinatown: its leaders only, the rest as group numbers until drawn in. Cuban exiles: offstage, left out.
- **Same ladder of detail (3.1), own insides.** The Italians use the ranks and the Ladder. The Brigades are "more a set of loyalties than a roster" and nobody is inducted (Part V 3.1): older counsel, middle-aged men holding crane crews or union posts, young men who do the work, loyalty through parish and family more than money upward. The Combine: leaders, lieutenants, street. The bikers: officers, full members, prospects (their associates).
- The bible gives upward shares only for the Italians. For the others, propose figures as labelled Design proposals for the owner to approve; do not invent them silently.

### 6.2 Level 4 police and businessmen at the start

- **Rule:** level 4 from the start is whoever holds a seat the underworld must deal with, not a set number per institution and not every named office.
- Roughly: the police commissioner, chief of detectives, head of organized crime and the captains of the precincts the families work; the district attorney, US Attorney and FBI special agent in charge; the mayor and the aldermen of the mob wards; the president of each local in Part IV 2.7; the bankers, contractors and businessmen the bible ties to the families. Perhaps 50 to 80 people.
- Everyone else in those institutions is level 3 or 2, pulled up when involved.
- Many of these offices are Open ("invented when needed"). The simulation needing a holder to decide counts as needed: these offices are filled at the start through the existing Open-office fill (E-002), then held for the run.

### 6.3 The Pad

- Confirm the figures already in `design_figures.json`: `pad_total_m` 1.6, `pad_officers` 300, `pad_mean_envelope_usd_year` 5,300 (about $100 a week), derived from the total so the money always balances.
- **Uneven envelopes:** precinct captains take large envelopes, sergeants carry the money (bagmen), many patrolmen take small amounts; the mean stays at the derived figure. Who gets what decides who can be squeezed and who might talk.
