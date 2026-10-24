# Saint Jude: world packages and a living mob city

**Status:** design, agreed in conversation on 2026-10-23; awaiting the owner's review of this written spec.
**Branch:** `feat/world-packages-saintjude` (from `feat/claude-connector`).
**Source material:** `D:\Theology\Bellacorte_Living_World_Codex_Flexible_Date_Final.docx` (the codex) and `D:\Theology\ChatGPT-Review Bellacorte Update-20261023-1016.md` (its critique).

## 1. Intent

The owner plays through Claude (the connector). Claude is the game master: it understands intent, invents, and writes prose. The engine is memory, persistence, simulation, world lore and plausibility: it checks Claude's inventions and vetoes only contradictions it can name.

Two goals follow from that split:

1. **The engine works with any world.** A world is a package that is loaded into the engine; Caerness is one package, Saint Jude is the next. Caerness (a continent of nations, religions and cultivation) proved too large to simulate well; a single city is a smaller world.
2. **Saint Jude is a living city.** It is a 1980s East Coast port city of 2.4 million with four Italian-American crime families, rival gangs, police, Feds, politicians, unions and ordinary businesses. It is modelled on the real New York Mafia, romanticised and more violent.

**Why the owner wants this:** they will play many stories in this one world. If every story opens on the same hard-coded pressures (Matty's trial, the missing heroin container, Sally Glasses' secret), it feels unnatural and boring, and little changes. The world has to run on its own, so that things happen away from the owner's character, and people, places and businesses grow, decline and change. Without a population that keeps producing new characters, the world eventually runs out of them.

## 2. Goals, non-goals, anti-goals

**Goals**
- No pressure, plot or character secret is hard-coded. The codex's pressures (the RICO trial, the missing container, the missing clerk, Sally Glasses, Vinny Scales) are at most examples Claude may draw on.
- Each new story starts from a city with its own simulated history, so the powers, characters and storylines differ from story to story.
- Taboo acts (killing a cop, a reporter, or a made man without sanction) can happen, and bring retaliation.
- The city is simulated at the opening at a depth that suits each group; details are invented when the owner's character needs them.
- Neighbourhoods, businesses, fronts and rackets change; background people rise.
- Money is tracked properly and businesses grow or decline for reasons the simulation can show.

**Non-goals**
- Modelling minute mechanics (how a lock is picked, the wording of a sit-down). Claude supplies that; the engine keeps what has consequences.
- Rewriting Caerness. Caerness keeps working as its own package; its content is moved out of the engine, not changed.
- Phone-local play. Play runs on the connector server (Oracle VM); speed matters for how long a time skip takes.

**Anti-goals (failure even if it technically works)**
- The same opening pressures, the same bosses or the same storylines every story.
- A city that waits for the player: nothing moves unless the owner's character acts.
- Families as single blocks fighting over abstract zones (the existing underworld's shape, see §5).
- Claude dictating outcomes: a failing business making money, or a person knowing what they couldn't know, because the story wanted it.
- A frozen cast: the same named people forever, with nobody new rising.
- Fixed rules that cannot be broken (a family that physically cannot kill a cop).
- A rigid escalation ladder (insult, then sit-down, then beating, in order).
- Closed lists or menus handed to Claude (existing project rule).

## 3. Decisions the owner made

These are the owner's, as they said them in conversation:

1. **The codex is changeable source material, not absolute fact.** Its laws, levers, numbers and cast can be adapted to fit the engine. Always respect plausibility.
2. **Pressures are invented by Claude**, not pulled from a fixed pool. A starter pool is optional. The engine checks each invention against what is possible in the period and what the world already holds.
3. **Mafia rules are taboos with consequences, not fixed conventions.** Someone can kill a reporter or a cop, or a made man without sanction; retaliation attaches to the act.
4. **Each story inherits a city with its own simulated history.** The engine runs the city forward from a starting snapshot before the story opens, with different results each time. Major change to the codex cast is welcome (it keeps characters fresh).
5. **Diplomacy** rests mostly on the threat of mutual destruction and of Federal heat, not on written agreements. Agreements exist (two families splitting a business), but they are tense. Always plausible.
6. **Territory** has rough, shifting lines. Families try to hold their own ground and keep encroaching on each other's; they are also fighting the outside gangs. Some places are shared, tensely.
7. **Wars**: the bloodiest are often internal, but wars between families happen too, usually held short of all-out war by mutual destruction. Proxies are used: families keep **off-record associates** for deniable work.
8. **Escalation is not mechanical.** A violent capo may jump straight to a hit; a cautious one may swallow an insult.
9. **Everyone acts on their own motives**: bosses, capos, made men, associates, police, Feds, politicians, businessmen, the outside gangs and civilians. How deep each group is simulated is an engineering choice set by measurement, not a fixed rule.
10. **People rise three ways**: by their own trajectory (a businessman who prospers over a few years becomes an individual, forms ambitions such as a seaside development, and gets involved with the mob); by being needed by anyone in the simulation (a landlord a capo wants to buy from); and by contact with the owner's character. This applies to civilians, lawyers, businessmen, politicians and police alike.
11. **Finances must be tracked properly.** Businesses grow or decline. Claude may want a financial outcome for the story, but it is checked against the simulation: a weak business in the wrong area makes good money only with a plausible reason.
12. **How the owner will judge it:** different characters, arcs, "acts" and storylines across and within stories (turned into tests in §11).
13. **The starting snapshot is the codex back-dated to about 1975**, so stories can open in 1980.
14. **The city is Saint Jude** (after the patron saint of lost causes, already the patron of its docks). **Bellacorte becomes a district**, an old Italianate quarter inside the city. Renames that follow: Port St. Jude becomes **Killbuck Point** (the headland where the Killbuck River meets the Atlantic; "down the Point"); Saint Jude's Meadowlands becomes "the Pines" (already its nickname); St. Jude's church in Kerrytown keeps its name. The world package is called Saint Jude; its internal id must not depend on display names.
15. **Saint Jude was founded as a Roman Catholic settlement around its first church, St. Jude's**, which the city grew out from. Which Catholic settlers founded it is open; the owner named Italian, Spanish, Portuguese and Irish as candidates, or a mix. **Agreed founding story (proposed by me, accepted by the owner):** a small colonial-era Catholic refuge, as Maryland was for English Catholics, beside a Dutch trading post on the Killbuck (which explains the river's Dutch name). It took its saint after surviving something hopeless, which suits the patron of lost causes. Portuguese fishermen followed in the 1800s, the Irish after the Famine, and the Italians from the 1880s, each adding parishes. St. Jude's stands on the original site near the river mouth, by Kerrytown and Killbuck Point, and is now the cathedral of the Archdiocese. The Irish inherited the old parish, while the Italians built St. Rocco's on the Hill, a quiet rivalry the families inherit. Historical caveat: mass devotion to St. Jude in America is largely 20th-century, so an early dedication is a deliberate setting choice, explained by the founding story.

**Already settled by the ChatGPT review and carried into this design:** a flexible opening date (the story chooses; 1980 by default, never fixed to 1 January); a dated technology timeline (exists, available, common); a sourced price and wage ledger that moves with the years, with national benchmarks kept apart from Saint Jude estimates; one accounting sequence for every business and racket (§10); the material split into bible, simulation rules, starting state, economic reference and live campaign state, with the live state outranking the starting state (§4); and the city's geography as the codex has it, a large Atlantic port at the mouth of the Killbuck River with industry, wealthy suburbs and a major downtown.

## 4. World packages

The engine becomes world-agnostic. A world package holds everything world-specific:

| Part | Saint Jude | Caerness |
|---|---|---|
| Bible (searched by `lore`) | The adapted codex, Layer 1 | `canon/world_bible_current.docx` |
| Game-master rules for this world | Codex Layer 2 adapted (plain-English intent, player agency, 5-step continuity check, information boundaries), as Saint Jude's own section of the rulebook | Current Caerness wording, unchanged |
| Starting snapshot (seed) | Built from codex Layer 3 and Section 2, adapted (§6) | `game/seeds/Caerness_Initial_World_State_Seed_v1_4.json` |
| Calendar | Gregorian, with weekdays; opening season and year chosen per story (early 1980s default) | SV calendar |
| Money | US dollars; a price and wage ledger by year (codex Appendix B as the 1980 base) | Current abstract price index |
| Dated timeline | Technology, laws, products and business models, each with when it exists, becomes available and becomes common (codex Appendix A) | None needed |
| Business and racket types | 1980 city businesses (bar, diner, pizzeria, social club, nightclub, trucking, warehouse, car dealership, construction, laundromat, vending route, numbers bank, sports book…) | Current archetypes in `engine/business.py` |
| Taboos | The list in §7, with who cares about each | None or its own |
| People | Name pools and the city's ethnic mix (Italian, Irish, Black, Jewish, Russian, Puerto Rican, old-money WASP); 1980 US death rates | Current |
| Systems switched on | Cultivation, elixir, Hollow and groundbinding off | All on |

The test run on 2026-10-23 (a throwaway Saint Jude slice loaded into a scratch database) found these Caerness ties in the engine. Each moves into the Caerness package or becomes package-driven:

- `engine/current_seed.py`: hard-coded namespace `caerness_seed_v1_1`; refuses any seed whose bible fingerprint isn't the Caerness World Bible; requires SV-calendar date strings; maps `stage` to longevity.
- `engine/db.py` `init_db`: inserts world name "Caerness".
- `engine/activation.py` (opening): adds four merchant-noble Houses and the Salt Road Consortium, ten Caerness religions, Caerness paintings, Vein-Root elixir goods, and trade flows between Caerness regions; seeds 544 background people with Caerness names, some at cultivation Stages; marries every named adult to an invented spouse on day 0 (it married Carmine Sabatini, a widower in the codex).
- `engine/underworld_ecology.py` and `engine/underworld_canon.py`: generate Caerness-style outfits ("Sten Carrying Company", "Rooke Pawn House") and medieval zones ("Market Quarter", "Road Gate").
- `engine/business.py`: pre-industrial archetypes (inn, stable, horse breeder).
- `engine/canon.py`: `DEFAULT_CANON` is a hard-coded path; it indexes headings only from real Word styles (the codex is Markdown typed into Word, so it indexed as one "Document" section).
- `connector/views.py`: etiquette text mentions "martial standing"; dates print in SV.
- Every person gets a cultivation profile.

What worked unchanged: places, institutions, people, memberships, kinship, households, claims, the decision loop, presence, health, and `lore` once the Saint Jude bible was indexed.

**Selecting a package:** a campaign records which package it was created from; the connector and engine read the package from the campaign. Caerness campaigns keep working.

**The rulebook splits** into a shared core (the GM/engine split, prose rules, tool use) and a section per package. Caerness's wording moves into its section unchanged, so the live Caerness campaign plays as before (my call).

**Stories and campaigns (my call).** Each new story is a new campaign: a copy of the package's starting snapshot, then its own pre-history run (§6). The owner's character is created after that run, with Claude, from the city that resulted: any existing person of a fitting position, or a new one. Nobody is protected during the run. Starting a later story from the city a finished campaign left behind is not built now, but nothing in this design prevents it (a finished campaign's state can serve as a snapshot).

## 5. The existing underworld is replaced, not reused

`engine/underworld_*.py` (about 4,600 lines) models an outfit as a single firm competing for generic zones: aggregate scores (manpower, violence, cohesion, heat), a monthly choice among occupy turf, challenge, patrol, open racket, buy front, recruit or hold, a flat kick-up on gross, a code of conduct rolled at random per outfit, and fighting strength weighted by cultivation Stage. A ten-year Caerness run produced 606 operations and zero territory changes (POP-01 spec §11).

Saint Jude's drama lives between named men inside and across families, under conventions that are shared, not random. Bending the existing model is likely slower than building the mafia directly and would pull stories toward abstract turf fights. **Decision (the owner raised that the existing underworld may be a trap, and accepted replacing it in conversation): build the mafia as its own system; keep the generic pieces** (money ledger `engine/ledger.py`, payroll, relationships, loyalty, knowledge and rumour, health and death, the decision runtime). The old underworld stays for Caerness until Caerness gets its own review; it is switched off for Saint Jude.

## 6. How a story begins

1. **Starting snapshot.** The adapted codex gives the city's shape: districts and corridors, the four families, the outside organisations (Charlestown Brigades, Vorovskoy, Mercer Street Kings, Iron Horsemen), BCPD and the 14th Precinct, the FBI Strike Force, City Hall, the unions, the papers, the Archdiocese, major businesses and fronts, and the named cast with their positions, motives and relationships. **Not** in the snapshot: the codex's pressures and character secrets (§3.1).

   **The snapshot is dated about 1975 (the owner's decision), and the codex describes 1980, so it must be back-dated.** This is an authoring task in project 1:
   - Everyone is five years younger. Men hold the posts they plausibly held in 1975 (Mikey Saints, 29 in 1980, is 24 and not yet a capo; some 1980 capos are soldiers; some of today's bosses may still be underbosses under men the codex never names, who are added).
   - Codex history after 1975 is removed from the snapshot and becomes something that may or may not happen in the run: the 1977 Barber Shop hit on Don Giuseppe Vannucci, recent buttons, businesses founded late in the decade (for example *The Starlight* as a disco), and anything the dated timeline puts after 1975.
   - History up to 1975 stays (the 1946 Harbor War, the 1958 Moretti schism, the 1967 Vannucci split, the 1973 dock strike massacre, the 1974 Concrete Purge).
   - Prices and wages use 1975 values from the same historical sources as codex Appendix B, recorded as assumptions; the ledger then moves year by year.

   There is one snapshot. A story opening in 1980 runs about five years of pre-history; a later opening runs longer. The opening is normally 1980 (the codex's default) but stays the story's choice.
2. **The pre-history run.** The engine plays the city forward from the snapshot to the opening date, with a different random seed for each story. Everyone acts on their own motives (§8). Every change is recorded as history: deaths, imprisonments, promotions, people made, businesses opened, failed, bought, busted out or burned, territory gained and lost, debts, grudges, investigations.
3. **The opening.** Claude reads the resulting city (who is rising, who is in debt, which truce is fraying, which investigation is closing in), sets up the owner's character in it with the owner, and invents the opening pressures and particulars that fit. The engine checks each invention (§10) and stores it.
4. **During play.** The same simulation continues; the city moves while the owner's character is elsewhere. Claude invents details when the story needs them; the engine holds Claude to what is already true.

The engine's job at the opening is to make the run's results readable to Claude: a summary of current tensions, debts, grudges, ambitions, open investigations and recent history. **Left to the builder:** its form, as long as it is information, not a menu of plots.

## 7. Families, turf, taboos, agreements and war

**A family is its people.** Its made men; its associates on record and off record; who answers to whom; the money that flows up. Its real strength comes from relationships and money: who the shooters are loyal to, whose envelope the boss can't afford to lose, who controls what the boss hears, who slow-walks orders, who is loyal to the family and who to a man. Rank is the formal picture, and practical power can drift away from it (the codex's six levers, emerging from state rather than stored as scores). Induction requires an Italian father, an open slot when the books open, and someone to vouch; all three are changeable package rules.

**Money comes up from below.** Soldiers and capos open and run their own rackets and kick up a share of their net take; each family's rates are set by its boss and can change. The boss runs the family's big interests but does not plan every book or hijack.

**Turf has three layers, with rough, shifting lines.**
- Street spots: blocks, bars, numbers routes, protected shops; held by a soldier or capo; neighbours encroach.
- Industries and unions: the port, concrete, trucking, garment, waste, sanitation; held through union locals and cartels; sometimes split between families by a tense agreement.
- People: who is on record with whom.
Families try to hold their own ground, contest it with each other and with the outside gangs, and share some places tensely.

History check (2026-10-23): street rackets were neighbourhood-based, while control of industries ran citywide through unions and cartels (garment district, Fulton Fish Market, JFK cargo, construction, Javits Center, waste hauling: Jacobs & Friel, *Gotham Unbound*); New York was unusual in families legitimately sharing territory. The owner's correction applies: Saint Jude is more violent, so sharing is tenser and lines are defended.

**Taboos with consequences.** Package data, each with who cares and the plausible range of reactions: killing a cop; killing a reporter; killing or striking a made man without sanction; holding out; informing; dealing narcotics where the family forbids it; a made man's wife; violence in the Oakridge sanctuary; disrespecting a boss in public. Any can happen. The reaction comes from the people who learn of it, scaled by how sure they are and how much they care: a cop killing brings the whole precinct and the Feds; an unsanctioned hit brings a sit-down or a body. A boss can quietly permit what his family officially forbids. Who learns what follows the engine's existing knowledge and rumour systems (the codex's 48-hour rumour mill: hours for the street, a day for the barbers and bondsmen, two days for the papers).

**Agreements.** Deals between families and with outsiders have recorded terms (who gets what share of which business, for how long). Breaking one is an offence that others can learn of and react to.

**Conflict and war.** Responses come from the person: temper, means, stakes, and what they believe happened. There is no fixed ladder. Fear of mutual ruin and of Federal heat pushes towards settling, not always successfully. Deniable work goes through off-record associates, outside gangs (the bikers, an Irish crew, the Kings) and freelancers (an arsonist, a forger), until the rumour mill pins it on someone; how certain each side is decides the response. Internal wars (succession, coups, purges) and wars between families both happen.

## 8. Everyone acts

The same decision loop drives all individuals, each from their position, means and temperament:
- Bosses and capos: expansion, succession, alliances, discipline, business deals, settling scores.
- Made men and associates: earning (books, loans, hijacks, fronts), getting made, getting ahead, surviving.
- BCPD: the Pad as a warning and evidence-sabotage service with limits; crackdowns when public pressure forces them; clean captains and Internal Affairs.
- FBI and Strike Force: cases built over months (surveillance, Title III wiretaps under the law of the period, informants, people who flip, grand juries, trials).
- Politicians: contracts, zoning, elections, favours, scandals.
- Businessmen and civilians: borrowing, building, failing, selling, paying protection, witnessing, informing.
- The outside organisations: their own aims (the codex's §9.2 objectives are starting examples, not scripts).

## 9. People, depth and rising

Built on POP-01 (`docs/superpowers/specs/2026-09-26-population-tiers-design.md`, designed, not built). **Scope (my call): POP-01 is built for Saint Jude only.** Caerness keeps its current population model; the shared population code is written so a package chooses its model, and Caerness can adopt POP-01 later in its own project (with cultivation as its domain step). POP-01's phone targets are replaced by the speed test in §11. POP-01's principles hold: one set of rules for everyone; tier decides only how much is stored and how often it is computed; nobody is created or deleted by moving between tiers; looking at someone never changes their fate.

**Levels** (adapted from POP-01): background (simulated in groups monthly), individuals without names, and full characters. **Starting guess (my call, to be tuned by measurement on the server):**

| Group | Starting level |
|---|---|
| Bosses, their top men, capos | Full characters |
| Made men (~270 across the four families) | Individuals with rackets, money, crew and motives |
| Associates (~1,200, on and off record) | Individuals or small groups attached to their made man |
| Lieutenants, detectives, Federal agents, prosecutors | Individuals |
| Patrolmen, clerks | Groups |
| Mayor, council, DA, judges, union officials | Individuals |
| Businessmen tied to the mob or to individuals | Individuals |
| The rest of the city's commerce and civilians | Groups |
| Outside gangs | Same pattern by rank |

**Background groups hold real things.** Not just headcounts: who owns which buildings and shops, who works where, who owes money, who saw what. The Saint Jude background must carry, at minimum: age, sex, ethnicity, neighbourhood, household, occupation and rank, wealth and income, property, debts, criminal involvement and affiliation (on record, off record, none), and reputation.

**Rising, three ways.**
1. **Own trajectory**: standing out from peers or gaining power. A shop owner prospers and lends to neighbours; a patrolman makes good arrests; a ward heeler wins a seat; a lawyer picks up mob clients; a corner kid earns for a soldier. The mob path: hang around a club, get put on record, get made when the books open, become a capo through money, muscle or a vacancy.
2. **Being needed** by any individual in the simulation: being bought from, lent to, leaned on, robbed, hired; owning what someone wants; witnessing; holding information; being drawn into an investigation, lawsuit or election. The engine picks a specific fitting person from the group (an actual owner of that kind of building on that street) and splits them out with their state.
3. **Contact with the owner's character.**

**Ambitions grow from position.** Once someone is an individual, they form goals that fit their position, means and temperament (the developer with money eyes the seaside, which needs permits, unions, concrete and protection, which brings the mob). This is how new plots arise without being scripted.

**Their past is theirs.** A risen person's history is their group's recorded path. Claude invents name, looks, family and manner when the story needs them, consistent with that record; the engine checks and stores. Nothing is re-rolled once the owner has seen it. People who are no longer needed are simulated more lightly but keep what happened to them; anyone the owner's character has met stays an individual.

**The city refills itself.** Births, children growing up, arrivals (a crew from Miami, new immigrants in Brighton Point), new organisations (a new gang, a new company, a breakaway crew), and the established cast ageing, dying, going to prison or retiring.

**Places change the same way.** A building or shop sits inside the city's general commerce until someone wants it; then it becomes a specific property with an owner, rent, debts and history. Neighbourhoods drift in wealth and character within the period's limits.

## 10. Money and plausibility checks

**Money is the engine's.** Every holder (person, household, business, family, institution) has cash, assets and liabilities. Business ledgers follow codex Appendix B7: revenue, cost of goods, wages, rent, utilities, insurance, licences and taxes, debt service, owner draws, protection and kick-ups recorded separately from legitimate costs, cash, inventory, receivables and payables. Loans record principal, rate, schedule and terms; principal is never profit; weekly street rates are never mixed with annual rates. Dirty and clean money are tracked apart, with laundering limited by the capacity of real fronts.

**Businesses grow or decline for reasons.** Location and its traffic, demand, competition, the owner's competence, debt, protection costs, police and press attention, season, and the city's economy (1980: high inflation and interest rates, industrial decline) set results. `engine/business.py` already resolves business cycles from location demand and owner skill; it is reused with Saint Jude's types and dollars.

**Claude cannot set outcomes.** When Claude wants a financial result for the story (the owner's bar doing well), it proposes a cause: a new client, a celebrity visit, a contract, a rival closing. The engine checks the cause against the state; if plausible, it changes the numbers. A weak business in the wrong area does well only with a plausible reason. The owner's businesses run on the same rules as everyone's.

**What the engine checks when Claude invents:**
- **Date**: nothing appears before its time (no handheld phone in 1980), from the package's dated timeline.
- **State**: the dead stay dead; owners own what they own; money spent is gone; events recorded stay recorded.
- **Knowledge**: nobody acts on what they could not know.
- **Means**: nobody spends money, men or influence they don't have.
As now, the engine vetoes only a specific contradiction it can name, never offers a menu.

**Intentions are not facts** (from the ChatGPT review). A faction planning to seize a warehouse does not control it; a later summary never silently overwrites an established event. Plans, rumours and possibilities are recorded apart from what has happened.

**Tendencies, not absolutes** (from the ChatGPT review and codex A4). Corrupt local police and hard-to-reach Feds are tendencies: individual officers and agents can be honest, ambitious, incompetent or compromised; a bribe or a friendly judge changes the odds, never guarantees the outcome.

**Player agency** (codex Rule 9, as the review clarified it). Claude may render routine actions and ordinary speech that follow from the owner's stated intent, but never chooses the character's consequential decisions, loyalties, commitments or betrayals.

**How the checks work (my call, following the project's existing split).** The engine runs no language model. Judging whether free-text prose is plausible is Claude's job (it reads `lore` and the state). The engine checks the *structured claims* Claude records through `author`/`act`: the people, places, businesses, amounts, dates and items an invention names. So Claude ties a cause to records: a financial cause is recorded as a fact the simulation can use (a named client or contract with an amount and a counterparty, a rival enterprise that closed, an event), and the business model then uses that fact like any other; the engine checks that the counterparty exists, has the means, and that nothing predates the timeline. This is not a closed list of cause types: any cause that can be stated as people, things, money and dates can be recorded. The dated timeline and price ledger are therefore stored as structured data the engine can query by name and date.

## 11. Tests (how "natural and varied" is judged)

From the owner's criterion (different characters, arcs, acts and storylines), plus the codex's own Appendix C4:

| Test | Passes when |
|---|---|
| Variety across stories | Several pre-history runs from the same snapshot differ in who holds power (bosses, capos, which family is up), in most of the important characters, and in the main storylines (feuds, deals, investigations, fortunes). |
| Acts within a story | With the owner's character idle, the world produces its own turning points (a death, war, arrest, coup or big deal) every few weeks to months of game time; at least two factions move in any simulated month. |
| The cast refills | Over several simulated years, the share of individuals who rose from the background keeps growing, across the mob, police, politics and business. |
| Taboo consequences | A taboo act happens in simulation and draws a reaction proportional to who learned of it. |
| Money reconciles | Every holder's cash and liabilities reconcile; no business distributes money it doesn't have; loan principal never counts as profit. |
| Plausible finance | A proposed financial outcome for a weak business is vetoed without a plausible cause and accepted with one. |
| Date | No active technology, law or product predates its timeline entry. |
| Knowledge | No individual acts on information they haven't obtained. |
| No Caerness leaks | A fresh Saint Jude opening contains no Caerness names, places, goods, religions, calendar or cultivation. |
| Starting roles | Short openings as a street associate, a capo, a boss, a businessman and a police investigator each find an active city that doesn't revolve around the character (from the ChatGPT review). |
| Caerness still works | The existing regression suite (`tools/run_suite.py`) stays green. |
| POP-01 invariants | Tier invariance, conservation, look-invariance, chunk invariance (POP-01 §10). |
| Speed | A pre-history run and a typical time skip finish within targets set after the first measurement. |

## 12. Build order

Three projects, in this order; each gets its own implementation plan:

1. **World packages.** Make the engine and connector read the world from a package; move Caerness content into the Caerness package; build the Saint Jude package (adapted bible with real headings, rules, calendar, money and price ledger from 1975, dated timeline, business types, taboos, name pools, death rates, switches) and the 1975 starting snapshot back-dated from the codex (§6). Ends with a Saint Jude opening that has no Caerness leaks, playable through the connector with the generic systems that already exist.
2. **The living city.** POP-01 with Saint Jude as its first full domain set (life, means, work, crime, standing): background groups that hold property and debts, the three ways of rising, ambitions, and the mafia system of §7 with police, Feds, politicians, businessmen and outside gangs acting (§8). Money and business per §10.
3. **Stories.** The pre-history run per story, the readable summary for Claude, the opening, and the plausibility checks of §10 wired into `author`/`act`.

## 13. Left to the builder

- Package format and where packages live on disk.
- Exact schema changes, and whether the mafia system extends existing tables or adds new ones.
- How the pre-history run is made fast enough (cadences, batching), within the speed test.
- The level each group starts at (§9 table is a starting guess).
- The form of the run summary given to Claude.
- Calibration numbers (kick-up rates, business margins, crime rates), anchored to codex Appendix B and history, recorded as assumptions.

## 14. Calls I made (for the owner to check)

- Replace the existing underworld for Saint Jude rather than reuse it (§5).
- How the codex is back-dated to 1975: who holds which post, which unnamed men are added above them, which businesses don't exist yet (§6). Done in project 1 and reviewed by the owner as part of the snapshot.
- Starting depth per group (§9 table).
- Fix the codex's garbled figures (8.1 sports book and numbers math, 8.2 rank capital, 12.2 item 4, 13.2 items 3 and 6) while adapting it, rather than ask the owner for each.
- The codex's induction rules, taboos and kick-up ranges become changeable package data, not code.
- The rulebook splits into a shared core plus a section per world; Caerness's wording is unchanged (§4).
- Each story is a new campaign; the owner's character is created after the pre-history run; nobody is protected during it (§4).
- POP-01 is built for Saint Jude only; Caerness keeps its population model for now (§9).
- The engine runs no language model; it checks the structured claims Claude records (§10).
