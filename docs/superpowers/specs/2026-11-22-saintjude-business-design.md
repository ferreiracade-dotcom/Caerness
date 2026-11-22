# The business sphere (design) — DRAFT

Status: **DRAFT, written without the owner.** The supervisor told the brainstorm to design from what was already agreed and to mark every call made here. Where a line says **[my call]**, the owner has not decided it yet. Corrections come back through the supervisor. (An earlier commit wrongly marked this approved; the answers it recorded were not the owner's.)

Sources:
- the parent spec, `2026-11-19-saintjude-three-spheres-design.md`, §5.1, §5.2, §5.2a–c and §5.3;
- `worlds/saintjude/research/real_1975_seed_facts.md` (§4 business);
- `worlds/saintjude/bible.md` Part I §9 (economy) and Part IV §2 (unions) and §3 (legitimate business);
- the sibling politics draft, `2026-11-22-politics-sphere-design.md`, whose §9 lists the seams. This doc agrees with that split (§10 below).

## 1. Intent

Saint Jude has a mob and a law, and nothing around them earns a living. A bar pays protection, but the bar has no books. A contractor joins the Concrete Club, but no contract is ever let. A business campaign has nothing to stand on.

The business sphere makes the economy a set of actors with agendas, not a backdrop:
- **Businesses are orgs.** Each has named people, a purse and books. It wants things: to grow, survive, merge, move, sell out or rob its partners.
- **Every business is three things together:** a trade with a real cost structure, a place with a condition, and a ledger of agreements with others.
- **The mob, politics and the protagonist reach the economy through those same objects.** Protection is an arrangement on a business's books. A front is a business whose lines carry dirty money. A tender is an agenda item that firms bid on.

It must serve three kinds of play:
- a mob campaign that feels the economy (a bar's takings fall, so the envelope gets thin);
- a business campaign from a corner shop to a conglomerate;
- a mix of the two: a legitimate man the mob reaches for, or a made man going straight.

The protagonist lives under the same rules. His business is audited, struck, undercut, bought out, busted out and burned, exactly as anyone's would be.

## 2. Goals, non-goals, anti-goals

**Goals**
- A business population at **B depth that always runs**: the real large firms that touch Saint Jude, the city's own businesses, and emerging firms, each with an agenda.
- **C depth** that widens the world around the player's sector and region: rivals, suppliers, buyers, staff and start-ups, made named and simulated.
- Books that follow the bible's cost structures, so a bar leaves its owner 10–20% and a garment shop 3–8%.
- The six relations to the Life (bible Part IV §3.4) as real arrangements, never flavour.
- **A family can expand outside the city:** Atlantic City, nearby counties, Newark/Elizabeth, Philadelphia's edge, and other cities. That means new rackets, unions, fronts and businesses there, and friction with whoever already holds the ground (§9).
- Inventions and new firms judged against the year's technology, law, capital and demand.

**Non-goals**
- A national input-output model. Outside the city and the player's chain, the economy stays coarse.
- Stock-market simulation beyond what a named firm's price and the market's dated weather need.
- Building Caerness business anew. Caerness must stay behaviour-identical.

**Anti-goals** (failure even if it technically works)
- **Hard caps.** For example "a firm may not grow past X", "the protagonist cannot found a computer company", or "at most N businesses per block". Targets are expectations judged for plausibility, and an implausible result is fixed at its driver.
- **A menu.** The engine never offers "choose: expand / cut / sell". The GM proposes what a person would do, and the engine records it or vetoes a named contradiction.
- **A silent bucket.** An economy that moves money without named payers, so nobody can be asked who lost. (This is the depth rule: everything made in play is at least B. Anything coarse names its abstraction and can be widened.)
- **Real people doing undocumented wrongdoing.** Real executives act within their record. Invented men do the dirty work around them.
- **Hindsight beyond competence.** The protagonist does not "know" Microsoft will win unless his character could know.

## 3. What exists

**Org core (built, schemas up to 121).**
- Tables: `org_profiles`, `org_units`, `org_seats`, `org_holdings`, `org_lines`, `org_money`, `org_agenda`, `org_incidents`, `org_arrangements`, `org_tension` (+acts), `org_heat`, `org_councils` (+seats, acts), `org_debts`, `org_informers`, `org_absorptions` and `org_deals`.
- Modules: choices, council, coup, dealings, happenings, heat, informing, lifecycle, membership, money, motives, succession, temperament and tension.
- `orgs.json` declares kinds (family, loyalties, banks, club, handful, independent), each with sphere, head, unit leader, purse roles, courtship scan, choices, lifecycle, labels, rules and opening.
- Money layer: `org_money` purses, flows, ledger kinds and purposes, and arrangement kinds.

**Older Caerness tables** (reused per parent spec §5.1–5.2a):
- `civilian_enterprises`;
- `enterprise_accounts`;
- `civilian_projects`;
- `buildings`.

**`engine/business.py`** is Caerness-only. Its `_ARCHETYPES` (inn, tavern, bathhouse, stable, theatre, gambling house…) are hard-coded in the engine, each with base revenue, cost ratio, demand weights and regulation.

**Not built (parent spec §5.2a):**
- shared drivers;
- ventures;
- property and places;
- the §5.2b agreements ledger.

**Data that exists:**
- `real_1975_seed_facts.md` §4:
  - the Fortune 500, with ranks 1–25 verified and 26–100 being filled by the facts-gaps session;
  - NJ employers and banks;
  - young firms (Microsoft, Apple, Intel, FedEx, Nike, Southwest, Wal-Mart, Genentech, Atari and Turner).
- The bible's cost table, sectors and their weather from 1975 to 1984, family touchpoints, fronts and skims, Concrete Club rigging, and banks.
- The price book (Part VI).
- `gazetteer.json` has no regions (only `about`, `real_towns_replaced` and `real_people`). **Expansion needs new geography data.**

## 4. Approaches considered

1. **A separate economy simulator** with its own firm and market tables beside the org core. Detailed, but it forks the core: the mob, politics and the press could not share people, purses and arrangements with it. **Rejected.**
2. **Business as flavour on the mob layer:** a business is a holding with an income number. Cheap, but it is a silent bucket. There is no campaign in it and no named loser. **Rejected.**
3. **Businesses as an org kind on the core, with the §5.2a shared layer (drivers, ventures, property) and package data for trades and markets.** People, purses, arrangements, tension, absorption and deals come free. Caerness's archetypes move to package data. **Chosen [my call, but it is also what parent spec §5.2 and §5.3 already say].**

## 5. The shared layer (phase 1; parent spec §5.2a)

Everything here is generic engine code. Its world words live in package data.

### 5.1 Shared drivers

Every venture, line and business reads the same set:
- **calendar**: seasons, holidays and dated events from `timeline.json`;
- **form and quality**: the operator's skill, staff quality and the place's condition;
- **demand**: per market (§6);
- **capacity**: seats, bays, trucks, beds or men;
- **rivals**: who else serves this market, by name;
- **required approvals**: decided by politics (§10);
- **dated shocks**: the oil shock tail, the 1975 recession, the 1979–82 squeeze, Regulation Q, the casino vote;
- **seeded rolls**, so a run replays.

A driver says where its number came from, so the GM and audits can ask why a business is failing.

### 5.2 Ventures

A venture is anything with a backer, money, counterparties, a schedule, an outcome and a payoff: opening a bar, a tender bid, a fight card, a development, a takeover, a bust-out. It reuses `civilian_projects`, widened, **[my call]** rather than a new table.
- Stages are package data per venture kind.
- An outcome is weighed, not scripted. It can be late, over cost or failed, and anything that fails has a named reason.

### 5.3 Property and places

A business has a place, through `buildings`, widened. The place has:
- condition and upkeep;
- capacity;
- prestige;
- ownership (owned, leased from a named landlord, or held through a straw);
- a workplace roster.

Arson, decay, redlining and a landlord selling all act on the place, not on an abstract score.

### 5.4 The agreements ledger (parent spec §5.2b)

Contracts, leases, supply deals, loans, protection, favours and orders sit on one ledger.

Each entry has:
- parties;
- terms;
- a schedule;
- remedies.

`org_arrangements` already carries flows. The ledger adds two fields:
- **terms**: what each side owes, when, and what happens on default;
- **a breach path**: a lawsuit, a strike, the street, or a quiet grudge, depending on who the parties are.

Time-skips run the ledger: rent falls due, a loan is called, a contract ends.

## 6. Businesses on the org core

### 6.1 The company kind

A new kind in `orgs.json`, `company`, with sphere business **[my call: one kind with sub-shapes, rather than kinds per size]**.

**Shapes** are data:
- sole trader;
- family firm;
- partnership;
- closely held corporation;
- public corporation;
- cooperative and credit union.

**Seats** are data per shape:
- owner or chairman;
- CEO and president;
- officers;
- department heads;
- plant managers;
- foremen;
- the bookkeeper (who matters to fronts and to informing).

**Units** are plants, branches, stores and terminals.

The rest comes from the core:
- **succession and coups:** heirs, a boardroom fight, a proxy war;
- **absorption:** mergers and acquisitions;
- **deals:** joint ventures;
- **tension:** price wars, poaching, litigation;
- **heat:** regulators, the IRS, the press.

### 6.2 Books

- `enterprise_accounts` is the business's books. `org_money` is its purse.
- `civilian_enterprises.enterprise_kind` is widened to the package's trade kinds, as parent spec §5.2 says.
- Lines are revenue and cost streams with the bible's cost structures as package data: bar, laundromat, garment shop, trucking, construction, restaurant, vending, carting, bakery, funeral home, newsstand, car lot and so on (`worlds/saintjude/trades.json`, new).
- **Caerness's `_ARCHETYPES` move to `worlds/caerness/trades.json` unchanged.** A fingerprint test proves Caerness stays behaviour-identical.

Two sets of books are allowed. A front or a skim has a declared set and a real set, and the difference is the laundering or theft. An audit, a bookkeeper informing or a partner's suspicion reads the gap.

### 6.3 Agendas and choices

`org_agenda` and `org_choices` carry business intentions, drawn from the firm's situation and its people's temperament, never from a list of allowed moves:
- expand;
- cut;
- move to the suburbs;
- merge;
- sell out;
- enter Saint Jude;
- leave Saint Jude;
- automate;
- fight a union;
- settle;
- borrow;
- bribe;
- bust out a partner;
- go to the street for money.

A choice that contradicts named facts is vetoed, for example "lists on the NYSE" for a two-man shop with no audit.

### 6.4 Markets

Markets are per **sector and region**, as package data. Each holds:
- demand;
- price level, from the price book;
- growth and decline by year (bible §3.3 and §3.8 weather);
- seasonality;
- the named firms serving it.

Two rules:
- **Coarse is allowed for the national market, but it names its abstraction.** For example, "rest of US auto demand" is one number with a source.
- **Saint Jude's markets are always per neighbourhood** where the trade is local (bars, groceries), and citywide where it is not (trucking, construction).

### 6.5 Labour and unions

Unions are orgs (`union` kind), with:
- locals as units;
- business agents and stewards as seats;
- dues as the purse;
- contracts as ledger entries with firms.

Strikes, slowdowns, sweetheart contracts, Teamster chokepoints on concrete and freight, and pension-fund loans (the Central States pattern, where documented) are all weighed acts.

Two seams:
- unions are also political actors (politics §5.6);
- the mob reaches them through `org_arrangements` (bible Part IV §2).

Workers are people. A firm's staff are drawn from the population layer at B as counts with named key men, and become named when C reaches them.

### 6.6 Credit and banks

Banks already exist as an org kind (`banks`). Business adds:
- **loans** as ledger entries with terms;
- **loan officers** as seats whose judgment weighs collateral, ties and redlining;
- **Regulation Q and the rate weather** from 1975 to 1984 as dated data.

**The shylock is a real competitor for a business turned down by the bank.** That is how a legitimate man ends up owned (bible §3.4, "borrows from the street").

### 6.7 Contracts and tenders

Public tenders are politics' agenda items (politics §9). Business owns:
- the bid;
- the firm's capacity;
- the price;
- the surety bond (sureties are firms that can refuse);
- the rigging arrangement between bidders.

The Concrete Club (bible §3.6) is an arrangement with:
- a rotation;
- about a 2% tax;
- the Teamster chokepoint;
- the "lowest responsible bidder" fig leaf.

Its victims are real: an outside firm that bids low gets its trucks stopped, its bond refused or its site burned.

**The rigging is tied to whichever machine holds the city.** Politics models the Machine and the organisations that may succeed it. Public contracts and the Concrete Club's arrangement with the board reference the political org that currently holds the awarding offices, never a fixed name. If the Machine falls, a reformer wins, or a successor takes over, the Club's arrangement is renegotiated, broken or carried over through the same tension, deal and absorption machinery. The Club's rotation and tax can then change, stop or move to the new holder.

Private contracts work the same way without the board.

## 7. The relations to the Life (bible Part IV §3.4)

Each of the six relations is an arrangement kind (most already exist in `orgs.json`'s `arrangement_kinds`, **to check**) with flows on the business's books:
1. **None.** Most firms. They still feel the Life through prices (carting, linen, concrete).
2. **Protection.** A weekly envelope, a cost line. It goes up when takings go up.
3. **Borrows from the street.** A debt in `org_debts` at street terms. Default walks toward partner or bust-out.
4. **Partner.** The family holds a share: a holding plus a seat or a silent stake.
5. **Front or skim.** Dirty money in or clean money out through the two sets of books.
6. **Customer or supplier.** Mob-owned carting, linen, vending or jukeboxes sold to the business, at a price the business cannot refuse.

Movement between them is weighed, never scheduled. A failing bar borrows, misses, takes a partner and gets busted out. The same machine runs on the protagonist's own business.

## 8. Population: B always, C where the story goes

### 8.1 B depth, always running

Seeded at the opening on 1 January 1975, from the research files, each with its real state on that date:
- **The giants that touch Saint Jude:**
  - Fortune 500 firms with plants, offices or contracts in the footprint or its trade (Exxon's Bayway, the auto plants, the chemical firms, AT&T and Bell Labs Holmdel);
  - the NJ employers in seed-facts §4.2 (Prudential, J&J, Merck, Campbell, PSE&G, Allied, Hartz Mountain);
  - the military employers (Fort Monmouth, Earle).
- **The city's own economy:** the bible's named firms, the family touchpoints (Vannucci mills and the Strip, Ferrante trucking, Pellegrino piers and the fish market, Sabatini and the Concrete Club, the Brigades' south piers), the banks, the *Chronicle*, and the main employers per neighbourhood.
- **Emerging firms with real 1975 states:** Microsoft (founded April 1975, no outside investor until 1981), Apple (not founded until April 1976), Intel, FedEx, Nike, Southwest, Wal-Mart, Genentech (1976), Atari (sold to Warner in 1976) and Turner. Their dated real paths are **defaults, not scripts.** They diverge when the run gives a driver a reason, for example the protagonist investing, competing, or hiring their people away.

**B fidelity [my call]:**
- **Giants run monthly.** Each has an agenda, its head (a real person, within the record), its main lines and its relation to Saint Jude: a plant to keep or close, a contract to let, an office to move.
- **City firms run on the org cadence.**
- **Everything else outside is the named market abstraction.**

**Real people.** Real executives act on their documented public record. Wrongdoing is of documented kinds only (established history for the dead, convictions for the recently alive). Invented people do the dirty work around clean figures.

The real people's answers to offers are plausible to the person:
- Gates in 1975 does not sell Microsoft to a stranger for cash, because of his documented attitude.
- Jobs and Wozniak in 1976 might take a seed investor, as they took Markkula.

### 8.2 C depth, widening around the player

When the protagonist enters a sector or a region, C makes it fully named:
- the rivals for his customers;
- his suppliers and buyers;
- the union local;
- the bank officer;
- the landlord;
- the inspector (from politics);
- the start-ups that might appear.

C stays where the story is and falls back to B when the story leaves. The named people stay named.

**Seeding scope (parent spec §5.2c):**
- everything that touches Saint Jude is seeded up front;
- everything else is made when reached, with the GM proposing and the engine recording or vetoing.

### 8.3 Invention and new firms

A new product or firm, whether the protagonist's or an NPC's, is a venture whose plausibility is weighed against:
- **technology of the year:** a dated table of what exists, what is in labs and what is impossible. Examples: the Altair in January 1975, the floppy disk, VisiCalc in 1979, the IBM PC in 1981, fibre optics in labs, no mobile networks;
- **law:** licences, patents, the FCC, the FDA;
- **capital:** who would lend, and on what;
- **demand:** the market that exists or could plausibly be made;
- **the inventor's competence**, including the protagonist's.

There are no "forbidden inventions". There is a veto when a named fact contradicts the claim, and otherwise a weighed outcome that can fail.

## 9. Families expanding outside Saint Jude (from the owner)

Today only the outside families act on Saint Jude. The owner wants it to run both ways: a Saint Jude family can move into new ground.

### 9.1 Ground as data

A new package file, `worlds/saintjude/regions.json` **[my call]**. Each region has:
- **geography:**
  - its name;
  - its distance from Saint Jude (Atlantic City about 65 miles south, Newark/Elizabeth 35–40 miles north, the Shore and Pine counties inside the footprint, Philadelphia, New York);
  - whether it is real or fictional.
- **economy:** its markets (as §6.4), its dated weather and its big employers.
- **holders:** who holds which rackets, unions and arrangements there, as org ids:
  - outer-ring families (subtype "outer ring family" in `outfits.json`);
  - the Philadelphia family in Atlantic City;
  - the Genovese NJ crew in Hudson;
  - local gangs;
  - unions.
- **politics:** its offices and law agencies, owned by the politics package data (politics §9 "jurisdictions").
- **dated events:**
  - the casino referendum (2 November 1976);
  - Resorts International opening (26 May 1978);
  - the Shore casino question, which the bible leaves **Open**.

The gazetteer has no regions today, so this file is new research. **Real places use the real holders of 1975, within the record. Fictional places use the bible.**

### 9.2 How a family moves in

Expansion is a choice on a family's agenda, weighed from:
- its temperament;
- its money;
- its men;
- its heat;
- the ground's lure: casino money, a new port, a union local without a master, a weak holder.

There is no scheduled expansion and no forbidden region.

Entry goes through machinery that already exists:
1. **A foothold.** Pick one or more:
   - a business there (a venture, §5.2): a bar, a vending route, a construction firm, a hotel supplier to the casinos;
   - a union local's officer brought over through an arrangement;
   - a relative or a made man who moves there (membership);
   - a deal with a local holder (`org_deals`: tribute, a share, an alliance).
2. **Rackets on the foothold.** New lines (gambling, loans, protection, labour) are `org_lines` in the new region's units. They need customers from the region's markets and officials reached through politics arrangements.
3. **Friction with the holder.** `org_tension` between the newcomer and whoever holds the ground. It is weighed like any tension, and can lead to:
   - a sit-down;
   - tribute;
   - a split of ground;
   - absorption of a weak holder;
   - a war.
   
   The outside world's councils matter: the Commission, or the Philadelphia family's own answer, through the councils core.
4. **Law in a new jurisdiction.** Its own agencies have their own integrity and capacity (the NJ State Police, the Division of Gaming Enforcement after 1977, other county prosecutors). Heat earned there is that agency's heat.

### 9.3 Depth

- **B (always) [my call]:**
  - each region outside the city keeps its holders as orgs at B, with their lines as counts with named heads;
  - a Saint Jude family's foothold there is a unit with named men and B lines;
  - friction runs on the normal tension cadence.
- **C, when play moves there:** the region widens like a sector does (§8.2), with its bars, its locals, its officials and its street.

**Atlantic City after 1978 is the likeliest C, so it gets seeded research first [my call].**

### 9.4 Symmetry

The same machinery already runs inward. Outside families courting Saint Jude ground become this same entry path seen from the other side, so there is one code path, not two.

The protagonist can take it too: open a business in Atlantic City, bring a crew, or be the foothold a family uses.

## 10. Seams

### With politics (agreed with the politics draft §9)

- **Donations.**
  - Business owns the giver's decision: what it wants back and whether it can afford it.
  - Politics owns the effect on the candidate and the ledger entry.
- **Tenders.**
  - Politics owns the agenda item and the board's weighing, through whichever machine or successor holds the awarding offices (§6.7).
  - Business owns the bid, capacity, bond and bidder rigging.
  - The award becomes a contract on the business ledger.
- **Licences and permits.**
  - Business declares the approvals a venture or line needs (§5.1).
  - Politics decides them by an office-holder's weighing.
  - An inspector's closure is politics' power. Its cost to the business is business's.
- **Laws as data that business drivers read:** taxes, wage law, rent control, casino legality, usury.
- **Patronage jobs:** public employment is an employer in the labour market.
- **Expansion:**
  - business owns the firm's entry;
  - politics owns the region's officials;
  - the mob layer owns the holder's answer.

### With the mob layer (org core)

Protection, fronts, skims, street loans and bust-outs are arrangements and debts already in the core. Business adds the books they act on.

### With information and the press

A business's reputation is an audience impression (information design). The *Chronicle* is a company and a press actor at once.

## 11. The protagonist under the same rules

Everything above hits his business as it hits anyone's:
- audits;
- strikes;
- price wars;
- a partner's skim;
- a bust-out;
- arson;
- a takeover bid;
- a bank calling a loan;
- a family deciding he is a target or a partner.

He can do everything an NPC can: found, borrow, bribe, rig, invent and expand, all weighed by the same drivers.

The only exception is the existing lean toward life over death when both are possible. It has no business-specific exception.

## 12. Cost budget per simulated day [my call]

- **Giants:** monthly, a few dozen orgs.
- **City firms:** a few hundred at B, run on the org cadence. Their lines are computed per period, not per day.
- **C sectors and regions:** daily for the named people in the story, and weekly for their firms.
- **Target:** a five-year run with business on should stay within about 1.5× today's run time. This is reported, not enforced. If it is too slow, fix the cadence, not the population.

## 13. Order of work [my call]

1. **BZ1 — Shared layer.**
   - Shared drivers, ventures (widened `civilian_projects`), property (widened `buildings`) and the agreements ledger terms and breach path.
   - Caerness archetypes move to package data, and the Caerness fingerprint stays identical.
   - **Politics P1 can start after this.**
2. **BZ2 — The company kind and books.**
   - `trades.json` for Saint Jude with the bible's cost structures, two sets of books, and markets per sector and neighbourhood.
   - The city's own firms seeded.
3. **BZ3 — The relations to the Life.**
   - Protection, street loans, partner, front and skim, and customer and supplier on real books.
   - The bust-out path.
   - Concrete Club rigging on tenders, which needs politics P1's tender item, or a stub.
4. **BZ4 — Unions and banks**, as business actors: contracts, strikes, loans and redlining.
5. **BZ5 — The B national population.**
   - Giants and emerging firms with real 1 January 1975 states, agendas and defaults.
   - The technology-of-the-year table.
6. **BZ6 — Regions and expansion.**
   - `regions.json` (Atlantic City first), holders, footholds, entry and friction, and new-jurisdiction law.
   - The inward path refactored onto the same code.
7. **BZ7 — C widening** for sectors and regions, plus play-checks of the parent spec's campaign checks: event organiser, developer, newspaper, casino, trucking, boxing.

Each step ends with a five-year run that reports its measures (Long-runs rule: at most two at once).

## 14. Calibration targets (reported, never enforced; approximate)

- Small-business failure: roughly half of new small firms gone within five years.
- Owner's take per trade within the bible's table ranges.
- Protection on a share of bars and shops in mob neighbourhoods, per the bible's sense of it, **to fix with the owner**.
- The families' legitimate holdings grow through the decade, as the bible's §3.3 touchpoints imply.
- Manufacturing jobs in the city fall and services rise (bible §3.3), driven by firms' agendas, not set.
- Atlantic City draws Saint Jude men after 1978 if the Shore stays closed (bible line 853).

## 15. Open questions for the owner, most important first

1. **What does a business campaign's day look like for you?** Running one shop by hand, or deals and boardrooms over years? This decides whether BZ7's C widening or BZ5's national population matters first. I assumed both, with the city first.
2. **Expansion targets and the Shore casinos.** Is Atlantic City the first region to research? And does the Shore stay casino-free by default (bible Open) unless the run's politics changes it? I assumed yes to both.
3. **Real executives' answers.** May a real founder (Gates, Jobs) plausibly sell, partner or be outcompeted when the run gives a reason, or should the big tech names keep their real path unless the protagonist acts directly on them? I assumed the first, weighed on their documented attitudes.
4. **How many city firms at B.** A few hundred named firms, or fewer with named market abstractions per neighbourhood? This is a cost and depth trade.
5. **Protection's reach.** How much of the city's small business pays, by neighbourhood? I need a number to calibrate against, not to enforce.
6. **Order against politics.** BZ1 first, then politics P1 alongside BZ2 to BZ3? This is what both drafts assume.
