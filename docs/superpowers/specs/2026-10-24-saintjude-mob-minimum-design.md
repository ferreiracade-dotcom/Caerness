# Saint Jude: the mob minimum

**Status:** design, agreed in conversation on 2026-10-24 (handoff `docs/superpowers/plans/2026-10-24-saintjude-mob-minimum-handoff.md`); awaiting the owner's review of this written spec.
**Branch:** `feat/world-packages-saintjude`.
**Parent design:** `docs/superpowers/specs/2026-10-23-saint-jude-living-city-design.md` (project 2, "the living city"). This spec is the first, smallest slice of project 2 that makes Saint Jude playable as a mob game. Where the two differ, this one is later and governs for the slice it covers.

## 1. Why

Saint Jude cannot be played yet, for two reasons.

1. **Reach.** The Oracle VM runs the older `feat/claude-connector` code, and a connector serves one campaign whose world was fixed when it was created (`connector/campaign.py`: `CAERNESS_CAMPAIGN` picks the file at start-up, `CAERNESS_WORLD_PACKAGE` its world). The owner wants one connector that holds both worlds: "resume Saint Jude", "resume Caerness".
2. **The mob is names only.** `data/saintjude.db` (checked 2026-10-24) has the four families, the Brigades, the Combine, the Horsemen, the Russians and the Puerto Rican blocks as `institution` actors with 63 memberships between all 83 institutions; 0 crews, 0 rackets (`economic_interests`, `underworld_racket_sites`), 0 law jurisdictions, 0 goals. The seed names about 30 mob and gang men. A public killing brings no response (connector play test case C). Five simulated years record only births, deaths and unions.

**Not in this slice** (later, each its own piece): the narcotics dial (E-021, E-027), offices with terms (E-019), weekly and annual cycles (E-025), taboo reactions beyond the law response (E-022), the deflator (E-013), the Narration Standards file, long Federal cases (wiretaps, flips, grand juries), business growth and decline (§10 of the parent design), and POP-01's background-group property and debt.

## 2. Goals and anti-goals

**Goals**
- The owner can resume either world from the same connector, on the phone.
- At the opening every family is its people: ranks, crews, every made man and associate, with earnings that sum to the bible's figures.
- Men below the top make choices that matter: start rackets, get made, fight, kill a capo. Far-off incidents reach the families and get a response.
- A recorded crime brings a law response; the Pad bends routine responses and does not bend what the bible says it cannot buy.
- It fits the speed budget on the VM (§9).

**Anti-goals (failure even if it technically works)**
- A family as one block with a score (the Caerness underworld's shape; parent design §5).
- 1,200 associates producing a flood of noise incidents that drown what matters.
- Money that does not reconcile: earnings that do not sum to the family gross, kick-ups that create or lose money.
- Saint Jude values in engine or connector code (`step1_diff.md` grep rule).
- People created from nothing during a run when a group already holds someone who fits; counts that stop adding up.

## 3. Owner rules that bind this work

Read them in memory and `AGENTS.md`; listed here so the plan checks against them.

- **Engine veto, not menu.** The GM proposes freely; the engine refuses only named contradictions. No closed lists handed to Claude.
- **Violence is per outfit,** from temperament and cost, never a world cap.
- **Loyalty beyond wages.** Bonds and grievances drive loyalty; pay mostly matters for hirelings.
- **Power sex ratios.** Women in the Saint Jude underworld are super rare exceptions, more skewed than the Caerness defaults (owner, 2026-10-24). Package figures, not engine constants:
  - Made men, Brigades men, Horsemen members and prospects, the Russians: all men (induction, colours and custom bar women).
  - Italian associates and other gang roles: 99.5% male. Women in the Life sit in the connected roles around it (a girlfriend who carries, a bookkeeper, a bar owner who looks away), not on a crew.
  - Numbers bankers, controllers and bolita runners: 99% male. The numbers game is the one place with a real precedent for women (Harlem's policy queens of the 1930s), so the rare exception is likeliest there.
  - Pad officers: 99% male (women had only just begun patrol duty in 1975, and few were in positions the Pad paid).
- **Opening vs run-time invention.** The opening gets lived records once; histories are written when a man becomes important and must fit his record.
- **Silent disconnection.** After building, show that every new system fires (join keys, reachability) before tuning any rate.
- **Package-aware, not Saint Jude-coded.** Ranks, ladder shares, pools, gang structures and jurisdictions are package data under `worlds/saintjude/`. The Caerness underworld (`engine/underworld*.py`, switch `caerness_underworld`, off for Saint Jude) is a parts bin, not a base.
- Run sims on a copy of the database. Sonnet subagents implement, Opus reviews, every diff is checked.

## 4. One connector, both worlds

- `resume` takes an optional world (or campaign) name. With none it resumes the campaign last played. With one, it switches to that world's campaign, creating it from the packaged opening the first time (the existing `open_campaign(name, package)` already does creation).
- One campaign per world by default: the live Caerness campaign keeps its name (`main`); Saint Jude's is named after its package. Naming more than one campaign per world is not built now.
- The switch happens between tool calls, never during one. The connector is single-owner, so a process-wide switch of the database path is acceptable; the plan must show that no open connection or cached package survives the switch.
- `resume` names the world it resumed and the other worlds available, so Claude can tell the owner.
- **VM update:** the VM moves from `feat/claude-connector` to this branch. Before deploying: back up the live Caerness campaign (`connector/backup.py`), and confirm on a copy of it that migrations to the current schema keep it playable (resume, scene, advance). The rollback is the old branch plus the backup.

This is small and comes first, so everything after it can be play-tested on the phone.

## 5. One ladder of detail

Every person in the city sits on one ladder. The rules are the same at every level; the level only decides how much is stored and how often the person chooses something new.

| Level | What is stored | How often he chooses | Engine today |
|---|---|---|---|
| 1. In a group | A count (neighbourhood population by trade) | Never individually | `background_population_sources`, age cohorts |
| 2. Light record | Age, sex, a few traits, job, place; no history | Never, until pulled up | `background_person_profiles` |
| 3. Active, weekly | Level 2 plus rank and crew, earnings, standing, feelings toward his superiors | Weekly | actor + `simulation_profiles` |
| 4. Active, daily | Full person | Daily | actor + `simulation_profiles` |

**Pulling up.** When the simulation needs someone, it takes him from the level below, never from nothing: a new associate from the neighbourhood's young men, a detective from the department, a bar owner from that neighbourhood's bar owners, a new made man from the family's associates. He keeps everything he had and only gains detail; the group's count drops by one. Extend the existing pattern (`engine/person_ecology.py`, `resolution_controller._materialize_latent_person`, `background_population_identity_links`); do not replace it.

**Moving down.** A man who goes quiet drops from daily to weekly; one who leaves the life becomes a light record. Nobody pulled in ever becomes a bare count again: his name and deeds stay on record.

**Rhythm.** Importance sets the usual rhythm. Activity speeds a man up for a while: an important job this week (a hit, a big collection, a delivery), a deadline (a debt due, an order, a meeting), danger (hunted, watched by the police), a live conflict, or nearness to the protagonist. He chooses daily until it is over, then drops back. It works both ways: a boss in prison, retired or delegating can drop to weekly. Anything that happens *to* a man (shot, arrested) is handled at once whatever his rhythm. The engine already has this shape (`simulation_profiles.tier`, `cadence_days`, `forced_tier`, `forced_until_day`, `_wake_actor_if_needed`); the plan maps levels 3 and 4 onto it with package-set cadences (7 and 1 days) rather than adding a second scheduler.

**Weekly is not frozen.** Routine business runs on its own every week (collections, kick-ups); the rhythm only sets how often a man considers something new.

## 6. What exists at the start of a run

The opening builds these once, deterministically from the run seed, after `engine/design.py` has drawn the figures.

### 6.1 The four families

- **Full people (level 4):** each family's boss, underboss, consigliere and capos. The seeded Examples fill their seats (for example Carmine Sabatini, Ettore Conti, Lorenzo DeLuca); Open seats are filled here through the existing Open-office fill (`facts.fill_open`, E-002), then held for the run.
- **Capos:** one per 8 made men, at least 2 per family (`capo_one_per_men`, `capo_minimum_per_family`). At the drawn defaults that is 7 Sabatini, 6 Pellegrino, 6 Ferrante, 5 Vannucci (the plan computes from the drawn counts, not these numbers).
- **Made men (level 3):** every one, in a capo's crew, the drawn counts (defaults 57, 45, 44, 36). Record: rank, crew and capo, age, years made, personality (ambition, greed, loyalty, temper, caution), earnings and racket line, his feeling toward his capo, and a name (from the package name pools; drawn now because it is free and keeps him stable).
- **Associates (level 3):** every one, the drawn ratio per made man (defaults 6.7, 6.7, 7.0, 6.2; about 1,200 in all). Record: crew and the soldier he answers to, age, two or three traits (ambition, temper, reliability), earnings, standing (how near he is to being proposed). No history.
- **Sabatini's seeded soldiers and Vannucci's seeded associates** take their places in this structure rather than being added on top.
- Wives, children and side contacts are created when they come up. Histories are written when a man becomes important (§7.4) and must fit his record.

### 6.2 The other gangs (Part III 5, Part V)

Same ladder of detail, each with its own insides. **The bible gives upward shares and headcounts only for the Italians; every figure below not cited to the bible is a Design proposal for the owner to approve**, and goes into `design_figures.json` marked as such.

| Group | Inside shape | Opening people (proposal) | Bible anchor |
|---|---|---|---|
| Charlestown Brigades | Not a roster; nobody is inducted. Older counsel; middle-aged men holding a crane crew or a union post; young men who do the work. Loyalty runs through parish, pub, firehouse and family more than money upward. | About 50: 6 elders (level 4), 14 middle men, 30 young men (level 3). Money belongs to men: each man draws his own income; no Brigade treasury. | Part V 3.1; income $1.5M (Part VI 8.1), whose counterargument says to draw each man's income, not the group's |
| Eastside Combine | No single head. Bankers, their controllers and writers, a loose council of older bankers. | 6 bankers (level 4), 24 controllers (level 3); writers and runners stay a counted group, pulled up when needed. The 1980s Kings grow later from its young men. | Part V 4; own lines $1.15M (Part VI 8.2) |
| Iron Horsemen MC | President, officers, full-patch members, prospects, hangarounds. | President and 4 officers (level 4), 25 full members and 20 prospects (level 3). | Part V 6: "twenty to forty full members in 1975, with prospects and hangarounds adding as many again" |
| The Russians | A handful in 1975, with no group income yet. | 7 men (level 3; the senior man level 4), so the 1980s outfit grows from real men. | Part V 5.3; income $0 in January 1975 (Part VI 8.3) |
| Puerto Rican blocks | Bolita bankers on their blocks. | 3 bankers (level 4), 9 runners (level 3); they hold the `bolita_tax` pool. | Part V 8.2 |

**Not gangs:** Jewish financiers and bookmakers cannot be made and belong to no family; they are connected businessmen, one by one, at level 3 or 4. Chinatown: its leaders only (level 4), the rest group numbers until drawn in. Cuban exiles: offstage, left out.

**Upward money for the others (proposal):** Brigades men keep what they earn, with a customary gift to the elder who got them the job; Combine controllers pass the bank's net to their banker, who pays the Italian slice the bible already counts (Part V 4.3); Horsemen pay club dues to the treasury. Rates are Design proposals in the figures file.

### 6.3 Law, the Pad and connected people

- **Jurisdictions:** city, county (Killbuck and Marsh), state and federal, loaded from package data into the existing tables (`law_jurisdictions`, `law_offices`, `law_rules`, `law_enforcement_profiles`); empty today.
- **Level 4 from the start** is whoever holds a seat the underworld must deal with, not a set number per institution and not every named office. Roughly: the police commissioner, chief of detectives, head of the Organized Crime Control Division and the captains of the precincts the families work; the district attorneys, the US Attorney, the FBI special agent in charge; the mayor and the aldermen of the mob wards; the president of each local in Part IV 2.7; the bankers, contractors and businessmen the bible ties to the families. About 50 to 80 people, filled through the Open-office fill where Open.
- **Pad officers (level 3):** `pad_officers` (300), each with an envelope. Envelopes are uneven: precinct captains take large ones, sergeants carry the money (bagmen), many patrolmen take small amounts; the mean is the derived `pad_mean_envelope_usd_year` (about $5,300, about $100 a week) and the total is `pad_total_m` ($1.6M), split by family as `allocation.pad_by_family_m`. Who gets what decides who can be squeezed and who might talk. Part II 3.2 shapes it: most money moves through intermediaries, and the Pad pays the position, not the man (a new captain reopens the arrangement, Part II 3.4).
- Everyone else in those institutions stays level 2 or 1, pulled up when involved.

### 6.4 Expected size

Level 4: about 40 Italians, about 20 from the other gangs, 50 to 80 law and business: roughly 110 to 140. Level 3: about 180 made men, 1,200 associates, 300 Pad officers, about 120 gang men, and some connected businessmen: roughly 1,850 to 1,950. About 2,000 active people. Not measured; measure (§9).

## 7. What the families do

### 7.1 Rackets: from pools to men

1. **Family holdings:** one per family per pool (`pools.*.shares`), with its share and yearly take, summing to the family's gross (`allocation.family_gross_net_9_3`: for example Vannucci $11.6M gross, $0.53M Pad, $11.1M net, within `gross_tolerance_m`).
2. **Crew slices:** each crew holds slices of the family's holdings by its ground and line (Lorenzo DeLuca's crews hold construction; Jackie Pellegrino's the North Pier).
3. **Soldier lines:** every made man has at least one earning line ("a card game on Mercer Avenue, about $X a week"). Totals match the bible, and every soldier earns.
4. **Weekly flow** up the Ladder: associate to soldier `ladder_associate_to_soldier` (22.5% of net), soldier to capo `ladder_soldier_to_capo` (18.3%), capo to boss `ladder_capo_to_boss` (11.7% of regime net); the Pad paid as a cost. Shares are each family's own figures and the boss can change them.
5. **Made when needed:** the bar paying protection, the debtor, the runner, the game's address. Until then they are counts and amounts on a holding. When one is needed, he is pulled up from the matching group (§5).

The generic tables hold this where their columns fit (`economic_interests` has holder actor, crew or organisation and a share; `underworld_crews`; the ledger). Whether to extend them or add Saint Jude-neutral tables is the plan's call; Caerness-only columns (patrol strength, Stage estimates) are left unused, not repurposed.

### 7.2 What a man chooses

Each active man's choice runs through the existing decision loop (`engine/decision_runtime.py` providers), with a new package-driven provider. The candidates come from his position, means and record; this is the NPCs' choice, not a menu for Claude, and Claude can still propose anything through `author`/`act`.

- **Keep doing what he does** (collect, run the game, drive, kick up). For most men in most weeks this wins. It is cheap: when nothing in his record or situation has changed, no decision row is written (see storage, §9).
- **What changes it:** traits, a situation (a debt, a slight, an opportunity, police pressure) or an order from above.
- **Start a racket:** a small weekly chance for each made man (rarely an associate), raised by ambition and greed, lowered by caution. He needs money, men and ground. The new racket is a new holding: an unclaimed part of a pool, a new pool, or someone else's share (a fight). He must kick up; hiding it and being caught is a serious offence. The GM or the player starts one through the same holding.
- **Kill his capo:** his record already holds the reason (a capo who takes too much, being passed over, an insult). Personality decides whether he acts, since an unsanctioned killing of a made man is a death sentence. If it happens: the capo dies; the boss picks a new capo from the crew; the rackets stay with the crew; the killer is rewarded (if sanctioned) or hunted; the police get a homicide (§8). Both men get full histories then.
- No fixed escalation order: a violent capo can go straight to a hit; a cautious one swallows an insult (parent design §3.8).

### 7.3 Associates and noise

- Incident chances stay low. An incident rises to the families only when it touches someone who matters: another family's ground, a made man, a cop, a big earner. Everything else stays in the man's own record. The rates are tuning, once built and once shown to fire.
- **Far-off sparks:** an associate across the city robs the wrong game or hits the wrong man. He is pulled up to a full person at that moment; the incident lands on his soldier, capo and family; the other family responds through the family-to-family relationship (a sit-down, a payment, a killing). The protagonist may only hear of it, through the existing knowledge and rumour systems.

### 7.4 Being made, rising, dying

- **Being made:** when a family's books open (a death, a vacancy, the boss's choice), the candidates are the associates with the best standing; the family picks a real man with a record. Induction rules (an Italian father, an open slot, someone to vouch) are package data.
- **Becoming a capo:** from the crew, by the boss, when a seat falls vacant.
- **Counts stay true:** deaths and prison lower the made-man count; new made men come from associates; new associates come from the neighbourhood's young men. The Pellegrino count above 50 needs a dated cause (Part III 3.2).
- **Histories:** written when a man rises to level 4 or is involved in something with consequences, from his record (age, crew, years made), never contradicting it.

## 8. The law response and the Pad

- **Every crime the engine records gets a law response:** an investigation, an arrest, or nothing, decided by the facts of the case (who saw it, where, how public, the evidence) and the jurisdiction (`engine/law.py` `resolve_jurisdiction`). The minimum covers the crimes the engine already records with a victim and a place: killings and assaults (`harm_incidents`), and racket busts. Long Federal investigations are not in this slice: a Federal jurisdiction opens a case and gathers evidence on the same rule, nothing more.
- **The Pad changes the response within its limits** (Part II 3.3): warning of a raid, soft treatment, lost paper, information, a blind eye. It works through the officers on the case and their envelopes, so a case handled by a clean officer is not bought.
- **What it cannot buy** (Part II 3.4, Fixed): a public killing (a body in front of witnesses, a bystander hit, a front-page story) forces an arrest regardless of the Pad; it does not reach the FBI, the Strike Force or the State Attorney General; it does not control Homicide's honest men, the Medical Examiner or IAD; it does not cover a killed officer; it does not bind a new commander. These are package data with the bible reference, not engine constants.
- An arrest is a fact the families learn of and respond to (a lawyer, bail, a worry about who talks), through the same decision loop.
- **Play test case C must now bring an arrest.**

## 9. Speed and storage

Measure on the PC and on the VM, after each build step (handoff §5 step 6):

| Measure | Today (PC) | Target (proposal) |
|---|---|---|
| Opening build | 2.6 s | under 30 s on the VM |
| 30-day advance | 0.1 s | under 10 s on the VM (a typical time skip while playing) |
| 1 Jan 1975 to 1 Jan 1980 | 18.9 s | under 10 minutes on the VM (the pre-history run) |
| Database growth | 5.8 MB, 9.2 MB in 1980 | at most 15 MB per simulated year |

- About 2,000 active people at weekly or daily rhythm is about 400 choices a day at most. The routine choice must not write a decision and candidate audit row every week for every associate (that alone is over 100,000 rows a year); record what changes, not every "carried on".
- Weekly money flows are posted to the ledger in a form that keeps every holder's balance exact without a ledger row per man per week (for example a monthly posting with weekly accrual). The plan picks the form; the reconciliation test (§10) decides whether it is right.
- If the targets fail, the first lever is cadence (more men at a slower rhythm), not dropping people from the record.

## 10. Tests

| Test | Passes when |
|---|---|
| World switch | One connector resumes Caerness, then Saint Jude, then Caerness, each with its own state, without restart; the live Caerness campaign plays the same before and after (resume, scene, advance). |
| Opening counts | Each family's made men, capos and associates equal its drawn figures; capo rule holds; every made man has a capo and every associate a soldier; the seeded Examples hold their seats. |
| Money reconciles at the opening | Each family's holdings sum to its gross within `gross_tolerance_m`; crew slices sum to holdings; every soldier has at least one line. |
| Money reconciles over time | After a simulated year, every holder's balance equals the sum of his ledger; kick-ups neither create nor lose money; the Pad total matches `pad_total_m` within tolerance. |
| Sex ratios | Every made man, Brigades man, Horsemen member and Russian is a man; associates, numbers men and Pad officers meet the shares in §3. |
| It fires | In a 5-year run: at least one man is made from the associates, at least one racket is started, at least one incident rises from an associate to a family, at least one arrest follows a recorded crime. (Silent-disconnection rule: shown before any rate is tuned.) |
| Pulling up conserves | Every pulled-up person came from a group whose count dropped by one; no active person was created from nothing while a fitting group existed. |
| Look-invariance | Pulling a man up to look at him does not change what he would have done. |
| Pad limits | A public killing brings an arrest whatever the Pad; a routine bust on a paid precinct can be warned or softened; a case in Federal jurisdiction is not affected by the Pad. |
| Case C | The connector play test's public killing brings an arrest. |
| No Saint Jude code | The `step1_diff.md` grep finds no Saint Jude values in `engine/` or `connector/`. |
| No leaks | `tools/leak_scan.py` passes on a fresh Saint Jude opening and on a 5-year run. |
| Caerness still works | `tools/run_suite.py` stays green. |
| Speed | The targets of §9 on the PC and the VM. |

## 11. Build order

1. World switching in `resume`, and the VM update (§4).
2. Families, crews and the Ladder as data at the opening (§6.1), from `design_figures.json` and the seed's Examples; the other gangs (§6.2) once the owner approves their figures.
3. Racket holdings split to crews and soldiers, with the weekly flow (§7.1).
4. The rhythm and the decision loop for levels 3 and 4 (§5, §7.2 to §7.4).
5. Law response and the Pad (§6.3, §8).
6. Measure (§9) and re-run the connector play test.

Each step is its own plan section with its tests; step 1 can ship to the VM on its own.

## 12. Left to the builder

- Exact schema: which generic tables are extended and which new, package-neutral ones are added.
- How levels map onto `simulation_profiles` tiers and cadences, within §5.
- The ledger posting form for weekly flows, within §9 and the reconciliation test.
- Trait scales and the exact weekly chances, recorded as Design figures with a source or marked unsourced.
- How crimes are scored into evidence, within §8.

## 13. Calls I made (for the owner to check)

- Headcounts and inside shapes for the Brigades, Combine, Horsemen, Russians and Puerto Rican blocks (§6.2), and their upward money; all Design proposals.
- The exact sex-ratio shares inside the owner's "super rare exceptions" rule (§3): all men where membership bars women; 99.5% for associates; 99% for numbers men and Pad officers.
- One campaign per world, with Caerness keeping `main` (§4).
- Federal cases in this slice only open and gather evidence; no wiretaps, flips or trials yet (§8).
- The speed and storage targets (§9).
- Routine weekly choices write nothing when nothing changed (§7.2, §9).
