# The politics sphere (design)

Date: 2026-11-22. Status: **DRAFT**, written without the owner on the supervisor's instruction, from what was already agreed. The owner answered the open questions on 2026-11-22 and then reframed politics as a general field, not as the Machine (binding; §10). Question 3 still awaits the owner's confirmation. Calls the owner has not ruled on stay marked **[my call]**.

Builds on:
- `2026-11-19-saintjude-three-spheres-design.md`: §5.1 the org core; §5.2 the politics layer; §5.2a B/C depth, the shared drivers, ventures and property; §5.2b the agreements ledger, real people and widening circles; §5.2c politics at B depth and limits that are plausibility, not ceilings.
- `2026-11-20-information-reputation-design.md`: claims, audiences, the press and the push.
- `2026-11-20-prison-design.md`: the case chain and the prosecutor's ambition.
- The sibling design for the business sphere (session "business-design"). §9 names every seam between the two.

## 1. Intent

Politics is a **general field**, not a machine story (owner, 2026-11-22, binding). It is made up of:
- offices at every level, from ward to state and beyond;
- voter groups by neighbourhood and identity, each with its own grievances and turnout;
- parties and factions;
- organised interests: unions, builders, banks, the Church, police and fire unions, landlords, the press, civil-rights groups;
- money and patronage;
- the press and scandal;
- prosecutors and courts;
- higher levels of government;
- individuals.

Each acts for itself on the generic org core. Saint Jude in 1975 is where the field starts, not a fixed shape:
- an old Irish Democratic machine is dominant, holding parts of the field and under pressure from the Italians, the Black wards and the reformers;
- prosecutors and judges are appointed, each with a sponsor;
- the city is broke and needs builders;
- Trenton and Washington sit above it on their real calendars, sending down laws, money and pressure.

The Machine is one organisation in the package data. It can lose any part it holds, and politics carries on without it.

Politics must always run, so that a mob or business campaign feels it: the alderman who stops taking calls in an election year, the new prosecutor who wants headlines, the casino vote. It must also be playable all the way up. The protagonist can work with or against any actor at any level: buy an alderman, become one, build a coalition, serve or fight the Machine or whatever replaces it, or run for governor or president, if his life can plausibly carry him there.

## 2. Goals, non-goals, anti-goals

**Goals**
- The calendar of every office that matters to the city and the protagonist, seeded with the real 1975 holders.
- Elections whose results come from people and drivers.
- Office-holders with powers, agendas and favours.
- Votes and laws with effects.
- Appointments made through sponsors.
- A field of actors acting for themselves: voter groups, parties and factions, organised interests, the press, prosecutors and courts, higher government and individuals. Any organisation, including the Machine, can rise, hold, lose or yield any part of it.
- Corruption and the law's answer.
- C depth where the protagonist goes.

**Non-goals for now** (kept possible)
- A full legislative simulator for Congress.
- Foreign policy beyond dated shocks.
- Polling as a product.
- Courts' case law.

**Anti-goals** (what would make it a failure even if it works)
- **A ladder or a menu.** For example "alderman, then mayor, then governor" as fixed steps, or a list of allowed bribes. The engine vetoes only contradictions: a 30-year-old cannot be president, and a convicted felon could not hold some offices.
- **Caps on outcomes,** such as "reformers win at most 1 in 3". The bible's "about one in three" is a calibration target.
- **A player exemption.** He can be indicted, beaten at the polls, betrayed by a ward leader, or used by a governor the same as anyone.
- **A special case for any actor or outcome.** There is no Machine-only code path and no scripted aftermath. A successor machine, a reform government, candidate-centred coalitions, kingmaker interests and rule from above all come out of the same drivers.
- **Real politicians given invented crimes.**
- **A silent bucket:** a seat bought in narration that the engine then forgets.

## 3. What exists

- **The bible.** It gives the city government: a strong mayor; a 15-ward council (zoning, paving, licences); the Board of Public Works (contracts); the Zoning Board; Buildings and Inspections; the Licensing Board; State ABC; the Racing Commission; the Port Authority. It also gives the Machine (§4.4), the money crisis (§4.5) and the election rules (§4.6: mayor in odd years, a September primary, the 1975 race Open). County Prosecutors and Superior Court judges are appointed by the Governor with the State Senate's consent, through the county's senators and the county chairman. It also covers the casino question (§9.9), women's rarity in office (§16) and the timeline (Pick-it 1975, the casino vote 1976, RICO 1978).
- **The research file.** `worlds/saintjude/research/real_1975_seed_facts.md` has the real holders on 1 January 1975: federal officials, Governor Byrne, the AG, legislative leaders, the SCI, Congress members for the footprint, and the U.S. Attorney.
- **The engine.**
  - `law.json` `level4_offices` gives office slots for the Mayor, the prosecutors and others, and world_facts holds offices that can be Open.
  - The org core has seats, money flows, arrangements (the Pad), tension, councils, debts and informers.
  - B13–B12g built law cases and dispositions.
  - B14 provides the GM's views of all of this.
  - **There are no elections, wards, electorates, votes or laws yet.**

## 4. Approaches considered

1. **Offices as world_facts only, with the GM narrating elections.** Cheap, but it is a silent bucket. Results are not plausibility-checked, and favours are forgotten. Rejected.
2. **A separate political simulator:** its own tables for parties, votes and polls, beside the org core. It has full detail, but it forks the core. Business, the mob and the press could not share people, money and arrangements with it. Rejected.
3. **Politics on the org core, with an electorate model built on the information design's audiences. [chosen; my call, following §5.2's direction]**
   - Every actor in the field is an org with seats, or an individual: parties and factions, the Machine, reform clubs, organised interests, the press, campaign committees.
   - Offices are seats in institutions.
   - Elections are ventures (§5.2a) with a dated outcome.
   - Voters are audiences with blocs and impressions.
   - Favours go on the agreements ledger (§5.2b).
   - The links to business, the mob and the press come free through shared people, money and arrangements.

## 5. The design

### 5.1 Offices and the calendar (package data, generic engine)

- **Offices and races are generic across levels (owner, 2026-11-22).** The same office model, race venture and drivers serve a precinct captaincy, a ward, the city, the county, a State Senate district, the state and the nation, with no role that exists only in the city. The levels differ only in data: the jurisdiction, the electorate's coarseness, the powers, and the calendar.
- An **office** is a seat in an institution, with:
  - its **jurisdiction** (city, ward, county, state, district, nation);
  - how it is **filled**: elected (with its cycle), appointed (by whom, with whose consent), or chosen within an org (a ward leader by the county committee);
  - its **term**;
  - its **powers** (§5.4);
  - its **eligibility**: age, residence, citizenship, and bars from conviction where the law says so. These are real legal rules, and so are vetoes, not caps.
- **The calendar is data.** For each elected office it records the cycle, the primary month and election day ("first Tuesday after the first Monday in November"). Real 1975–1990 dates are the default track:
  - president 1976, 1980, 1984, 1988;
  - the House every two years;
  - the U.S. Senate seats on their real classes;
  - NJ Governor 1977, 1981, 1985 and 1989;
  - the NJ Assembly in odd years;
  - the NJ Senate in 1977, 1981, 1983, 1987 [memory, to verify];
  - the Saint Jude mayor in 1975, 1979 and on;
  - the council on its own cycle: elected two years after the mayor (1977, 1981), so that every party and interest fights two campaigns. Bible §4.6 leaves the cycle unstated. **[Accepted by the owner, 2026-11-22: the council follows this calendar.]**
- **Seeding.** Real holders come from the research file, at their real age and health. Saint Jude's own officials are fictional, as the city is: the mayor, the 15 councilmen, the ward leaders, the boards, the county chairman, and the city's state senators (Design: about six) and assemblymen. They are generated at the opening with lived histories, following the bible's character text for the Machine, the reformers and the Black wards.
- **The firewall on real figures:** each acts within who they documentably were (the content limits). Byrne, for example, governs, signs and vetoes as himself, with no invented wrongdoing.

### 5.2 The field's actors on the org core

**Every actor acts for itself (owner, 2026-11-22, binding).** Each actor below is an org kind or a person on the generic org core. Each has its own goals, purse, seats, standing with voter groups, ledger entries and temperament, and weighs its own acts. None has a special code path. Package data says which actors exist in 1975 and what each holds.

- **Parties and factions:** the county Democratic organisation, with a chairman, a county committee, ward leaders and precinct captains as seats; factions within it (the Irish old guard, the rising Italians, the Black ward leaders); the Republicans, small in the city and stronger in the suburbs and state; reform clubs.
- **Organised interests:**
  - unions: the building trades, the Teamsters, public-employee unions, and the police and fire unions;
  - builders and contractors;
  - banks;
  - the Church: the Archdiocese and the parishes;
  - landlords and real estate;
  - the press, whose own politics comes from the information design;
  - civil-rights and Black political organisations;
  - ethnic and civic societies;
  - the families, whose reach is the Pad extended upward (§5.6).
- **Voter groups** (§5.3): electorates, not orgs, but with their own grievances and turnout.
- **Prosecutors and courts** (§5.5, §5.7), and **higher levels of government** (§5.8), as office-holders with their own drivers.
- **Individuals:** a rich donor, a fixer, a priest with a following, a columnist, a candidate with no organisation behind him.

**How actors act.** They endorse and deliver votes, give money (legal or not), put workers on the streets on election day, apply pressure (a strike before a budget vote, a sermon, an editorial, a lawsuit), trade favours on the agreements ledger, and bargain for what they want back: contracts, jobs, zoning, licences, laws, appointments, protection.

**Money and patronage are generic.** Public jobs are **patronage lines** held by whichever office-holder controls the hiring and passed down to whoever he chooses. **Favours** go on the agreements ledger: a pothole filled, a licence fast-tracked, a nephew hired, a judge's ear. **Kickbacks** on contracts and **campaign money** are arrangements with flows. An organisation's delivery of votes follows from what it can give, its people's loyalty and its standing. When it has less to give (the money crisis), its hold weakens.

**The Machine is one organisation (owner, 2026-11-22).** In 1975 it holds large parts of the field: the party's chairmanship, most ward leaderships, the patronage lines from City Hall, the sponsor chain for appointments, and ledger entries with interests across the city. That is starting data, not a role. Drivers that already exist can take any part of it away:
- lost jobs and money;
- defeats at the polls;
- indictments;
- a boss's death or fall;
- ward leaders defecting;
- a voter group turning;
- an interest finding a better partner.

It can weaken, split through the org core's split path, be taken over from inside, or dissolve, through the same weighed acts as mob families: absorption, splits, succession.

**After the Machine, politics continues.** What fills the field is decided by the run's drivers, with no special case for any outcome. The possibilities include:
- a successor machine (a rival boss's, the rising Italians', the Black ward leaders');
- reform government;
- fragmented, candidate-centred coalitions;
- kingmaker interests (the unions, the builders, the press);
- rule from above (state takeover, federal pressure, a receiver over a broke city).

Whoever wins the old patronage lines, seats and ledger entries takes them on, and the old debts and grudges carry into the new arrangements.

### 5.3 The electorate and elections (B depth always)

- **Voters are audiences** (information design §7.1). Each ward has voter groups by neighbourhood and identity (descent, class, parish, union, age), each with its own grievances and turnout, with shares from the package data and drifting with the population layer. Each bloc holds an **impression** of each candidate and party, built from claims, the press, the candidate's deeds, the economy and endorsements.
- **A race** is a venture.
  1. **Filing.** Candidates decide to run as weighed choices, from ambition, standing, money, the party's backing and the odds they can read.
  2. **The primary,** then the general election.
  3. **Spending** and the campaign's acts.
  4. **Result day.**
- **The vote is computed per ward and bloc from drivers:**
  - incumbency;
  - organised delivery: each party, faction or interest's strength in that group times its effort for this candidate;
  - the bloc's impression;
  - ethnic and personal ties;
  - the economy (unemployment, the city's cuts);
  - scandal (claims in that audience);
  - money spent and on what;
  - endorsements (unions, the *Chronicle*, the Church, civil-rights groups, the families' quiet word);
  - turnout per group, from its grievances, the stakes, the weather and whoever is driving its voters to the polls;
  - a seeded noise term.

  No result is fixed. The bible's "reformers win about one in three" and incumbents' advantage are calibration targets, reported across seeds.
- **Fraud** is a weighed act by people: padded rolls, ballot stuffing, paid "walking-around money", a crooked count in a ward. It has a gain, a risk of exposure (poll watchers, the press, the U.S. Attorney, the SCI) and consequences through the case chain. It is in from P1 (owner, 2026-11-22).
- **State and national races run at B** from the same drivers on coarser audiences: counties for the state, states for the nation. The real result is the default track. The run may diverge only when its own drivers give cause, for example a scandal the run created or an economy that went differently. **[PENDING the owner's confirmation, proposed 2026-11-22: real national results hold unless a named cause from the run changes them. That cause can come from the protagonist or from the simulation itself, directly or indirectly, consistent with the history design's H1: history stays unless it is touched directly or indirectly. A divergence must name its cause.]**

### 5.4 Powers, votes and laws

- **Powers are data per office.** They are what the seat can do as weighed choices:
  - appoint (from a pool, weighing sponsors, loyalty and competence);
  - vote on agenda items;
  - award (contracts, licences, zoning variances, permits);
  - veto;
  - set the budget (cuts, hires, layoffs);
  - direct (a police commissioner's priorities, a prosecutor's targets);
  - pardon or commute (the Governor; the President).
- **Votes.** A council or board vote is an agenda item. Each member weighs it:
  - his ward's impression;
  - his patron's or faction's line;
  - the interests pressing him;
  - favours owed;
  - money (legal or not);
  - his own agenda and conscience;
  - what the press would make of it.

  The outcome is the count. A deal before the vote is a ledger entry, and breaking it has consequences.
- **Laws** are events with **effects as data:**
  - a tax rate;
  - a new regulation's cost to a sector;
  - federal or state money to the city;
  - a crime-policy shift (sentencing, RICO's reach, wiretap rules);
  - gambling (the lottery games, the casino referendum and any later widening to the Shore).

  Real dated laws are defaults, for example the NJ casino referendum on 2 November 1976 and RICO's first use against the mob around 1978. A law can be moved, defeated or added when the run's people plausibly do it. State and national laws stay coarse at B; city ordinances are fully simulated.

### 5.5 Appointments by sponsorship

Prosecutors and judges are appointed by the Governor with the Senate's consent, on the recommendation of the county's senators and chairman (bible §4.3). Whoever holds those seats at the time is the sponsor chain, whether that is the Machine, a successor or a reform chairman. Each appointment is a chain of weighed choices:
1. who is put forward (sponsors' loyalties and debts);
2. the Governor's counsel weighing fit, politics and the press;
3. Senate courtesy, under which a home-county senator can block a nominee.

Every appointee has a **sponsor**, and owes him. A change of Governor (1977, 1981) can change the County Prosecutor. The same machinery covers the Police Commissioner (appointed by the mayor), the board members and the patronage posts.

### 5.6 The families as political actors

The families are organised interests like the others (§5.2). Their political reach is the Pad extended upward. An alderman or a judge can be "on" an arrangement, with the same reach, integrity and exposure rules as the police Pad, and the same law response.

### 5.7 Corruption and the law's answer

- Bribes, kickbacks, no-show jobs, extortion of contractors and fixed tenders are **arrangements and crimes**, run through B13's report, case, disposition and sentence chain.
- Federal and state investigators act with their own drivers: the U.S. Attorney (the Stern-era record against Newark and Hudson), the Strike Force, the SCI's hearings and subpoenas, and the State AG.
- A **prosecutor's ambition** (prison design §7.1b) is a real driver. Indicting a mayor builds a career and can mean a run for governor.
- **Pressure to cut a deal** (talking, a plea) applies to politicians as to mob men: a councilman facing ten years may give up his bagman.

### 5.8 Real people above the city (B depth)

- **Seeding.** State and national office-holders are seeded with their real 1 January 1975 state. They act within their documented record. Their real dated events (elections, appointments, deaths) are the defaults and calibration, and the run may plausibly change them.
- **What they want comes from their real situation.** Byrne's re-election in 1977 runs on the income tax fight; a congressman wants his district's money.
- **What they do touches Saint Jude** through laws, money, appointments and investigations. They take the protagonist's calls only when he has standing, money or votes they need.
- **The undocumented men around them are invented,** and they may do the dirty work a clean figure would not (agreed rule).

### 5.9 C depth: where the protagonist goes

C is a later build per level (§5.2a), using the same drivers in finer detail. When the protagonist runs or works a race, more of the world comes into focus:

- **City (the first C to be built; owner, 2026-11-22). Building it first does not exclude the levels above: the protagonist can be at any level from the start, played at B until that level's C lands.**
  - the field around him in full: the actors he works with or against (party officers, ward leaders and precinct captains, interest leaders, editors, the prosecutor's office) as named people; jobs handed out, favours called in, factions manoeuvring, and the fights when an organisation's hold breaks;
  - his ward or the citywide race in full: precinct-level blocs, door-knocking, rallies, the precinct captains as named people;
  - rival candidates with campaigns;
  - his party's factions;
  - the press beat (information phase 2);
  - fundraising and spending decisions;
  - election day operations, including the polling-place fights.
- **State:** the Trenton legislature as named people with committees, leadership races and votes; the Governor's office; county chairmen.
- **National:** the House and Senate as named people, the national party, and federal agencies.

### 5.10 The protagonist under the same rules; reaching the top

- **He can hold any seat he can plausibly win or be given, at any level (owner, 2026-11-22):** ward, city, county, State Senate, state and beyond, with or against any actor at any level. Eligibility is law (age, residence, citizenship; bars for some convictions). Everything else is weighed: money, the backing of parties, factions and interests, standing in the audiences, his record, his age, his temperament and competence, rivals and luck.
- **There are no fixed rungs.** A rich outsider can run for governor without having been an alderman. It is plausible but hard, and the drivers say how hard.
- **His past is a cost.** A mob record, an arrest, or a known associate is a claim that can surface (the press's morgue, a rival's opposition research, an informer, the SCI). He hides it, buys it off, outlives it or loses to it.
- **The presidency is reachable and very rare.** It needs decades of standing, a national base, money, the party's nomination, a moment and luck. Nothing caps it; the drivers make it what it was.
- **The same systems act on him as on anyone:** indictment, betrayal by a ward leader, a primary challenger, a bloc turning on him, a sponsor calling in a debt, the press.

### 5.11 What the GM sees and the push

- What the protagonist would plausibly know reaches the GM behind the firewall (B14): who holds the seats near him, which ones owe him or whom he owes, what's coming on the calendar, and how his name stands with each audience he deals with.
- Election nights, scandals, indictments and laws that touch him are **pushed** through the information design's ledger.

## 6. Constraints

- Packages are data. Offices, org kinds, the calendar, blocs, powers and law effects are all in package files. The engine has no world words (`no_world_words_test`).
- No caps, floors, quotas or fixed shares. Every figure is a Design figure with its reasoning. Calibration targets are reported, never enforced.
- Real people act within their documented record.
- Caerness stays behaviour-identical. Its own politics, the Courts and Houses, may later reuse this core.
- **A cost budget per simulated day.** Elections are dated events. Between them the electorate updates lazily, when a claim lands or a vote is cast. City votes are agenda items, not a daily scan. State and national levels are coarse.
- Long runs follow constraints.md.

## 7. The order of work [my call]

1. **P1, the city at B.**
   - Offices and the calendar.
   - The field's actors as orgs, with the 1975 holdings in package data: parties and factions (the Machine among them), the organised interests, and the wards.
   - Patronage lines and favours on the ledger.
   - Electorate blocs per ward.
   - Mayoral and council elections as ventures.
   - Council and board votes on zoning, contracts and licences (these are the business seams).
   - Appointments by sponsorship for the prosecutor and the commissioner.
   - Election fraud as a weighed act (owner, 2026-11-22).
   - Political arrangements and the law's answer.

   Builds after (owner, 2026-11-22) the business layer's shared drivers, ventures and the agreements ledger (§5.2a, §5.2b), and information phase 1b's audiences.
2. **P2, the state and the nation at B.** Real holders and the calendar, coarse elections with the real default, laws with effects, and federal and state investigators driven by ambition.
3. **P3, the city at C:** the actors around the protagonist as named people, and campaigns run ward by ward.
4. **P4 and later:** the state at C (Trenton), then the nation at C.

## 8. Calibration targets (reported, never enforced; from memory, approximate)

- Incumbent mayors and councilmen are usually re-elected. While the Machine holds the party, its candidates win most primaries; reformers win about one race in three (bible). These are targets for 1975 conditions only, and the drivers move them when the field changes.
- Turnout in city elections runs at roughly 40–60%, higher in presidential years.
- Some indictments of local officials per decade in a NJ city of this kind (Newark 1970, Hudson 1971–72).
- Prosecutors turn over on a change of Governor about as often as the bible's text implies.
- Women in office stay as rare as bible §16 says. Women in elected office rise slowly through the 1980s, by drivers, not a quota.

## 9. Seams with the business sphere (for "business-design")

- **Donations:**
  - who gives: firms, unions, families and individuals;
  - the forms: legal contributions, cash, in-kind (trucks, halls, printing), and walking-around money;
  - how they flow: money from a firm's purse to a campaign committee's purse, as arrangements on the org core. Legality is per law data, including the 1974 FECA federal limits [verified in outline] and NJ rules [to verify].
  - **The interface:** business owns the giver's decision (what it wants back, and whether it can afford to give). Politics owns how the gift moves the candidate and the ledger entry it creates.
- **Contracts and tenders:**
  - the Board of Public Works and city departments put out tenders, which are **agenda items with bids**;
  - firms bid (business weighs the bid price and capacity);
  - board members weigh price, ties, favours and kickbacks (politics);
  - the award is a contract, which is an income line and a venture for the firm.
  - Rigging (the Concrete Club) is an arrangement between bidders, which business owns, plus one with the board members, which politics owns.
  - Until P1 lands, business's BZ3 uses a stub tender agenda item (agreed with business-design). P1 replaces the stub with the real item, keeping the same interface, and the board members' weighing takes over from the stub.
- **Licences and permits:**
  - the Licensing Board, State ABC, the Racing Commission, the Zoning Board, Buildings and Inspections, the Port Authority, and later a Casino Control Commission;
  - each grant is a weighed decision by an office-holder;
  - business declares which approvals a venture or line needs (§5.2a "required approvals"), and politics decides them;
  - an inspector closing a site is a power used, and can be bought.
- **Regulation and laws:** law effects are data that business drivers read: a tax on a sector, a new rule's cost, wage law, rent control, a casino's legality. Business firms and unions lobby through the vote weighing in §5.4.
- **Patronage jobs and public employers:** city jobs are politics' currency, and the business layer's labour market should see public employment as an employer with its own wage and security.
- **A family expanding into other jurisdictions:**
  - every jurisdiction (another city, county or state) has its own offices, law agencies and arrangements reach, as data, keyed on the region ids in `worlds/saintjude/regions.json` (business's file for geography, markets and mob holders; agreed with business-design);
  - moving a racket, firm or casino interest there means reaching its officials: new arrangements with new people, and new law agencies with their own integrity and capacity;
  - the outer ring's families already hold some of those arrangements (the Genovese NJ crew in Hudson; Philadelphia in Atlantic City), so expansion runs into them through org tension;
  - business owns the firm's entry; politics owns the officials; the mob layer owns the rival family's answer.

## 10. The owner's answers (2026-11-22)

**Reframe (binding, supersedes the earlier Machine-first framing):** politics is a general field of actors that each act for themselves on the generic org core. The Machine is one organisation in Saint Jude's package data: dominant in 1975, holding parts of the field, and able to lose any part. When it is gone, politics continues, and what follows (a successor machine, reform government, fragmented candidate-centred coalitions, kingmaker interests, rule from above) is decided by the run's drivers, with no special case for any of them. The protagonist can work with or against any actor at any level (§1, §5.2).

1. **Role:** with or against any actor. The role can be anything at any level: ward, city, county, State Senate, state and beyond. Offices and races are modelled generically across levels, not as city-only roles (§5.1, §5.9, §5.10).
2. **Council cycle:** accepted. The council is elected two years after the mayor (1977, 1981).
3. **National races: PENDING the owner's confirmation.** Proposed: real national results hold unless a named cause from the run changes them, whether that cause comes from the protagonist or from the simulation itself, directly or indirectly (history design H1) (§5.3).
4. **First C:** accepted, the city first as the build order. Answer 1 means the levels above are not excluded.
5. **Election fraud:** accepted, from P1.
6. **Build order:** accepted. The business sphere's shared layer comes first, then politics P1.

**To verify before P2 seeds them:** the NJ Senate election years and New Jersey's campaign-finance rules, both written from memory.
