# Saint Jude: one city, three spheres (design)

Date: 2026-11-19. Status: draft for owner approval.

## 1. Intent

Saint Jude must simulate **politics, business and the underworld** well enough that the owner can live in any one of them, or move between them, and all three move each other. There is no win condition, only a good story. Mob play stays as an option. A clean businessman or politician must not get a thinner world than a soldier does.

Why: after task 8 the owner, a Christian, began asking whether they want to play sin as the main thing. The answer is that crime stays available, but the city has to be just as alive for someone who never touches it.

Later, separately: a London/Europe football world (2000s; manager, player, CEO, owner, head of transfers) and a medieval world. Each gets its own design. This document only makes sure Saint Jude's engine work does not block them.

## 2. Goals, non-goals, anti-goals

- **Goals.** One generic engine layer for "people inside an organisation", with each sphere's specifics as package data and thin rule modules on top. Finish mob tasks 10–16 on that layer. Then add business, then politics, as layers on the same core.
- **Non-goals.** No football or medieval work here. No score, win state, or closed menus of actions (engine vetoes, it does not list).
- **Anti-goals.** Mob-only machinery that business and politics would have to copy. Business or politics as abstract numbers (approval %, sector index) with no named people behind them. Breaking Caerness.

## 3. What the audit found (tasks 1–9)

The engine now has **two organisation systems side by side**:

1. **Caerness's general one** (older): `institution_profiles`, `institution_memberships`, `civilian_enterprises` + `enterprise_accounts`/`enterprise_staff`/`business_cycles`, `merchant_trade_contracts`, `organization_regimes`/`organization_factions`/`organization_pressures`/`organization_strategy_positions`. The shapes are mostly world-neutral, and the content is Caerness's. In Saint Jude most of it is switched off (`merchant_houses`, `caerness_trade` false), so **Saint Jude currently has no simulated businesses at all.**
2. **Saint Jude's outfit layer** (tasks 3–9): `outfit_crews`, `outfit_ranks`, `outfit_holdings`, `outfit_lines`, `outfit_money`, `outfit_agenda`, `outfit_incidents`, `pad_envelopes`, plus `outfits.py`, `outfit_opening.py`, `outfit_money.py`, `law_opening.py`.

Task by task:

| Task | Verdict | Mob-only parts |
|---|---|---|
| 1 One connector, both worlds | generic | none |
| 2 VM runbook | generic | none |
| 3 Schema 116 + package data | **needs treatment** | table names `outfit_*`; `outfit_ranks.level CHECK IN (3,4)`; `made_day` as a column; `outfit_money.kind` limited to `take/associate_earning/kickup/executive_share/pad`; `pad_envelopes.payer_outfit_actor_id` (only an outfit can pay an official) |
| 4 Pull up by name group | generic | none |
| 5–6 Families and other gangs at the opening | fine as the **mob layer** | builders live in `outfit_opening.py`; keep, but move shared helpers (pull-up, personality, feelings toward superior) to the core |
| 7 Rackets and monthly flow | **needs treatment** | `capo`/`boss`/`soldier` hard-coded in `outfits.capo_of`, `boss_of`, `outfit_money.line_holder`, `_Roster`, `_post_pad` |
| 8 Law, the Pad, connected people | mostly generic | jurisdictions, agencies and officials are general. The Pad only pays from outfits: it should be one case of "a payer keeps an official sweet" (bribes, retainers, campaign money) |
| 9 Quiet routine and agenda rhythm | **needs treatment** | `has_reason_to_choose` and the daily/weekly review only cover rows in `outfit_ranks`; a foreman or councillor never gets a turn |

Leaving these as they are means business and politics would copy them. **The branch has not shipped (task 16 ships), so generalising now costs one migration and no live saves.**

## 4. Approaches considered

- **A. Generic core, sphere layers on top (chosen).** One layer for org members, units, income lines, money flows, agenda, incidents and arrangements with officials; mob, business and politics as package data plus small rule modules. Costs a refactor of tasks 3, 7, 8 and 9 now. Pays back on every later sphere and on football and medieval.
- **B. Leave outfits mob-shaped; build business on Caerness's `civilian_enterprises`; politics separately.** Least churn now. Three different styles of "an organisation's people" that never share agenda, rhythm or money flow, so cross-sphere stories (the racket and the city contract that are the same story) need glue everywhere.
- **C. One giant merge of both organisation systems now.** Cleanest in theory. Touches Caerness heavily, which risks the main campaign for no Saint Jude gain.

The owner asked for the generic/specific split "only if best for the engine". It is. The refinement over the owner's version is that the core **adopts the outfit layer** (it is the newer, people-first design) and **reuses Caerness's enterprise accounts** for company books instead of writing a third ledger. Caerness's own system is left alone.

## 5. The design

### 5.0 Engine, layers, packages (agreed 2026-11-19)

Almost everything in this document is engine work, not Saint Jude work. The three spheres are reusable layers that Saint Jude is simply the first to use. Three tiers:

1. **Core (every world):** people in organisations (§5.1); B/C depth and the flag for where play is heading; shared drivers, ventures, property and places (§5.2a); deals ledger, orders, time-skips with routine and interrupts, goals within competence, recording what is named, the knowledge firewall, time budget, conscience per character (§5.2b); widening circles and the dated timeline; the real-figures and hindsight rules wherever a world uses real history.
2. **Layers (reusable, switched on per world in the manifest's `systems`):** business (companies, contracts, markets); politics as **offices and how they are filled** (election, appointment, inheritance, purchase, seizure come from data, so a 1975 alderman and a medieval duke sit on one layer); underworld (rackets, payoffs, protection, so a thieves' guild or a football agent's bungs use it too); later sport (season, matches, transfers) and war.
3. **Package (one world):** bible, the actual organisations and people, real figures for its era, prices, sex ratios, manners, which layers are on, and its circles as data (Saint Jude: city, New Jersey, US, world; football: club, league, country, Europe; medieval: manor, duchy, kingdom).

Checked: football is core + business + sport, with light politics and underworld; medieval is core + politics + business + war + underworld.

**Packages are data and prose; the engine never names a world** (revised the same day after review). A package holds its bible, rulebook and creation sections, and JSON (organisations, roles, flows, law, timeline, real people, prices, circles). It holds no code. Builders are generic and read the package's data:
- `outfit_opening.py` becomes a generic "organisation with units" builder: a head, executives, unit leaders on grounds, members dealt to units, hangers-on spread over members, with every role word, count figure and age band from data. The same builder makes a family, a company (CEO, vice-presidents, department heads, staff, contractors) or a duchy (duke, council, knights with manors, men-at-arms, retainers).
- `law_opening.py` is already almost entirely generic (jurisdictions, agencies, precincts, officials, connected people from `law.json`) and stays in the engine as the "authorities" builder. Its Pad step becomes opening arrangements from data (§5.1 arrangements).
- The officials it seats (judges, DA, police chiefs) are **offices**. The politics layer grows from that same office concept rather than adding a second one.
- **Escape hatch:** if something truly cannot be said in data, a package may carry a small rule module listed in its manifest. Each use is a signal that the engine lacks a general piece, so that question is asked first.
- Test of the rule: no Saint Jude word (family names, `capo`, `soldier`, `boss`, the Pad) appears in `engine/`.

This is done with the org-core refactor (role rules from data), while the branch is unshipped. **Caerness is shelved for now** and is the known exception: its world-only code (cultivation, elixir, Hollow, groundbinding) stays in `engine/` until Caerness work resumes. Caerness is the eventual final package where the layers built for the other worlds come together.

### 5.1 The core (world-agnostic, `engine/orgs*.py`)

Rename and generalise the outfit tables in one migration (schema 117): `outfit_*` → `org_*`, `pad_envelopes` → `org_arrangements`.

- **Organisations** are institution actors with an `org_kind` from package data (`family`, `crew_outfit`, `company`, `union_local`, `ward_organisation`, `party`, `agency`…). No closed list in code.
- **Seats** (`org_seats`, was `outfit_ranks`): actor, org, `role_key`, unit, superior, detail level (no `IN (3,4)` check), standing, personality, status. Rank-specific facts (made day, partner, tenure, elected term) go in `metadata_json` or a sphere table.
- **Role rules from data.** Each package declares per `org_kind`: its roles, which role **leads a unit**, which role **heads the org**, and **who stands in** when a holder dies or is held. `capo_of`/`boss_of`/`line_holder` become `unit_leader_of`, `head_of`, `stand_in_for`, driven by that data.
- **Units** (`org_units`, was crews): crew, department, ward, division.
- **Income** (`org_holdings` + `org_lines`): a source of money and who works it: racket, contract, account, patronage job, ward. A line can be `hidden` (skimming, embezzlement, a no-show job).
- **Money flows** (`org_money`): `kind` is free text validated against the package's declared flows (`kickup`, `salary`, `dividend`, `fee`, `contribution`, `bribe`…). The monthly flow walks the role rules, not rank names.
- **Arrangements with officials** (`org_arrangements`, was the Pad): any payer (an org or a person) keeps an official sweet through a go-between. Kinds come from data: envelope, retainer, campaign money, favour. The mob's Pad becomes one kind.
- **Agenda and rhythm** (`org_agenda`, the task 9 routine): every seated person gets the quiet weekly review and the speed-up. Reason checks are registered per sphere.
- **Incidents** (`org_incidents`): generic, with the kind from data.
- **Motives** (task 10, built here): a person chooses from what his world offers: his lines, his superior, his rivals, his debts, his arrangements. Each sphere registers its choices: a soldier can `start_racket`, an executive can `bid_contract`, an alderman can `trade_vote`. The reading of motives and the single seeded roll point are shared.
- **Law response** (task 13): works on crime kinds from `law.json`, including white-collar ones (bribery, fraud, bid-rigging, election fraud), not just violence.

### 5.2 Sphere layers (Saint Jude package data + small modules)

- **Underworld** (now): `outfits.json` keeps the families and gangs, and declares their roles and flows against the core. `outfit_opening.py` stays as the mob layer's opening builder. Tasks 10–16 finish here.
- **Business** (next, its own plan): companies as orgs with named people (owners, executives, foremen) seated through the core. Their books use the existing `civilian_enterprises` / `enterprise_accounts` with Saint Jude kinds (the `enterprise_kind` check widens to package-declared kinds). Sectors from bible Part I 9 (port, heavy industry, garment, construction, banks) and Part IV (unions, contracts, fronts). Contracts and tenders are what the city, the families and companies compete for.
- **Politics** (after): offices (mayor, council, aldermen, DA, judges where elected), the Machine and wards as orgs, the election calendar from bible Part I 4.6, and votes as agenda items. Patronage jobs are income lines and campaign money is an arrangement.
- **The links** come mostly free: shared people (a capo owns a trucking firm; an alderman's brother is a union president), shared lines (the racket that skims the contract), shared arrangements (the same official on the Pad and on a developer's retainer), and the law response sees all of it.

### 5.2a No silent buckets: how deep anything is simulated (agreed 2026-11-19)

The engine's job: make requests plausible (friction, never refusal unless it contradicts something), simulate the world (people with their own wants, consequences off-screen), keep memory and continuity, and keep honest numbers. The GM interprets requests and tells the story. Nothing is refused for lacking a mechanism, and nothing is accepted and then forgotten.

- **B, the default for anything made in play:** a living thing through the core. It has an owner, people in seats, money in and out, an agenda, **and its drivers**: what really moves it, written down when it is made and run by shared mechanisms. So a club in B still has a rough form and results, and those set its crowd, income, press and the owner's worries.
- **C, when the story moves toward it:** domain depth (squads and matches, tour routing, ward-by-ward canvassing). C works out **the same drivers in finer detail**. History carries over and nothing resets. C's outcomes still feed B things and the other spheres through the same links. A C is its own design-and-build project. The engine should notice where play is heading (time spent, choices made) and flag it; B and the GM carry the thing until then.
- **The mob is the first C.** Families, rackets, the Pad and the law are the "real movers" for a B thing sitting beside them.

**Shared drivers (core, built with the business layer):** a season or calendar; form or quality (drifts and swings); demand (follows reputation, results and price); capacity (seats, floor space, staff); rivals in the same market; required approvals (permit, licence, lease, vote, all handled by politics); dated outside shocks (the timeline: the 1975 recession, Pick-3, the casino referendum); seeded outcome rolls. A thing's driver list is data written when it is made. The mechanisms are generic code.

**Ventures (new core object):** one-off undertakings beside ongoing income lines. Each has a backer, money committed, counterparties, a date or schedule, an outcome from its drivers, and a payoff or loss. Examples: a concert or tour stop, a fight card, a building project, a renovation, an election campaign, a takeover bid.

**Property and places (new core layer, reusing Caerness's `buildings` and `civilian_projects`, with package-declared kinds instead of the fixed `building_kind` list):** anything owned that is not itself a business. It has condition, capacity, prestige, upkeep, location, and who uses it.
- Buying a high-rise for headquarters: the company's seats get a **workplace**, so staff work there, are found there and commute there. Floor space is a capacity limit (outgrow it and you move, rent more floors or build). Renovation is a venture (cost, contractors, unions, time, mob concrete, permits) that changes condition and prestige. The building sits on someone's ground and in a precinct, so protection, the Pad and the ward alderman come with it. Spare floors can be let, which is an income line.
- Other things that work the same way: the family home or an estate (household, servants, upkeep, standing in the Heights); a racehorse at Bayview Downs (form, races, the track's bookmakers); a yacht or car fleet; an art collection (value drifts with taste); a private club membership; a charity or foundation (an org with patronage instead of profit); a pew and gifts at the cathedral (standing with the Archdiocese); a newspaper bought for influence rather than money; a private security detail (seats, wages, loyalty).

**Checked against other campaigns:** event organiser for big artists (ventures; drivers are artist demand, venues, season and rival promoters; links to stagehands and Teamsters, scalping and concessions, the arena lease and the press); property developer (ventures, zoning votes, building unions, mob concrete); running for alderman then mayor (election as a dated outcome from people); newspaper owner (circulation, advertisers, pressmen's union); the casino (bible Open: a referendum and licence fight before it is a business); shipping or trucking (freight volume, unions, theft); boxing promoter (small ventures, fixed fights). All of them fit: org core plus drivers plus ventures plus property.

### 5.2b Where the GM's story and the engine can drift apart (agreed 2026-11-19)

Core work, in priority order:
1. **Agreements and obligations ledger.** Promises, debts, favours and deals narrated in play are recorded with parties, terms and due dates. People act on them, and breaking one has consequences.
2. **Orders and standing policies.** The player's instructions to people become their agenda items or lasting policies. How well they are carried out follows the person's skill, loyalty and interests.
3. **Time-skips.** (a) The protagonist keeps his routine, drawn from what he was doing before (work, family, people he sees, habits), and the skip's focus is added on top. (b) The player's focus becomes ventures and orders that the engine carries out. (c) The world keeps moving, and a real event that touches him (arrest, a death in the family, a rival's move, a deal souring, an opportunity) **interrupts** the skip and hands the moment back.
4. **Vague goals within competence.** "Make it leaner" or "win over the Irish" are translated into drivers moved and costs paid, bounded by the character's skills, experience, people and temperament (or the people he hires). They are never ignored.
5. **The engine resolves, then the GM narrates.** For persuasion, fights and heists, the GM supplies the substance (the offer, the plan) and the engine weighs it against the people involved. The narration follows the outcome.
6. **Record what is named.** Every person, place or business named in narration is recorded (`author`/`note`). The engine may detect names that weren't recorded.
7. **Knowledge firewall.** The GM's views show what the protagonist knows. The engine's hidden truth (hidden lines, informants, plans) is reached through investigations it settles.
8. **Time budget.** Each new layer carries a cost budget per simulated day, and long skips stay fast.

**Real people.** Real public figures (artists, athletes, national and state politicians, celebrities) appear as fully as possible in their real public roles, and push on events. The run is an **alternate timeline**: each real figure starts from who they really were in that year (career, standing, character), then the run may diverge (an added tour date, a different political fight) when the world gives them reason to. Dated real events happen by default unless the run plausibly changes them. One limit: no invented crimes, scandals or private wrongdoing for a real person; shady acts belong to fictional characters only. Saint Jude's own local officials are fictional, as the city is.

**Beyond the city: widening circles.** Saint Jude is simulated in full. The state, the nation and the world run at B depth, with the real timeline as the default track (politics, markets, real companies, events). Detail grows to C where the protagonist goes (running for the Senate makes the state race and Trenton a C; national politics makes Washington one). The circles feed each other: national shocks reach the city, and his moves outside come home (the Machine, the families, federal pressure). Real companies follow their real histories by default and may diverge from the protagonist's stakes and moves.

**Hindsight within competence.** The protagonist may invest in or act on anything real that exists in that year, but only what he or the people around him (advisers, partners, his circle, the press he reads) would plausibly come across, and his judgement and nerve shape the bet. The player's knowledge of the future is never a free win.

**Conscience follows the character, not the owner.** The engine models the protagonist's own beliefs and temperament. Inner costs (guilt, confession, a strained marriage, hardening over time) follow who he is, and they can change over a life.

### 5.2c Beyond the city: real people and organisations, B and C above Saint Jude (agreed 2026-11-21)

- **Real people and organisations start from their real 1 January 1975 state** (seat, age, health, ties, size, money) and are simulated like anyone else. After that, the run decides. Real dated events (deaths, elections, laws) are calibration and defaults, and the run can plausibly change them. Conduct follows the bible's Content limits: real people act within who they documentably were. The men around them who aren't documented are invented.
- **The outer ring of mob families** (Elizabeth, the Genovese and Lucchese New Jersey crews, Philadelphia, the Gambino presence) is seeded with its real 1975 heads and invented men below them. It is simulated at B depth where it touches Saint Jude: allies, mediators, trade, incursions, loaned or poached men, and nearby wars. It goes to C if the story moves there.
- **Politics at B depth, always running.** Offices and elections follow the real calendar: president, Congress, governor, state legislature, mayor and council. Results are simulated from incumbency, the economy, scandal, money, endorsements and turnout. Office-holders have agendas, allies, donors and favours to give. Laws and policies are events with effects (tax, regulation, federal money, crime policy, gambling and casinos). Election seasons change the city, and favours owed after a win are real.
- **Business at B depth, always running.** A population of real large firms as they stood in 1975, plus firms that could grow to join them, real and invented. Each has an agenda (expand, enter Saint Jude, cut, merge, relocate). They are moved by the economy, and the protagonist can invest in, sell to or compete with them.
- **C depth widens the world around the protagonist as well as his own detail.** In business, more firms in his sector and region get full depth: rivals, suppliers, buyers, start-ups. In politics, the people around him do: rival candidates, his party's machine, donors, the press.
- **Limits are plausibility, never ceilings.** He can reach the top of the Fortune 500 or the presidency. It is rare and takes decades, the engine weighs capital, market, timing, rivals, party and luck, and his past (a mob record) is a cost he must hide, buy off or survive. A real firm's answer to an offer comes from its real people and situation (Microsoft took no outside investor until 1981; Apple took Markkula's money in 1977). An invention is checked against what enables it: the technology of the year, the law, capital and demand. Taking a niche first can mean the real firm never appears, or appears smaller.
- **Seeding scope.** Seed up front what touches Saint Jude or is needed for B: state and national offices, the outer ring, the big unions, regional employers and banks, and the large national firms. Everything else is seeded when the story reaches it: the GM proposes its 1975 state from what is known, and the engine records it and vetoes contradictions. Facts from memory are marked to verify.

### 5.3 Order of work

1. **Core refactor (new task 9b):** schema 117 migration, role rules from data, rename and generalise tasks 3/7/8/9 code; all existing Saint Jude tests stay green and Caerness regression passes.
2. **Mob tasks 10–16** on the core, as planned, with generic motive and law-response pieces.
3. **Business layer**: its own spec and plan. It starts with the shared drivers, ventures and property (§5.2a), because every later sphere and every C uses them.
4. **Politics layer**: its own spec and plan.
5. Football and medieval: separate designs that reuse the core.

## 6. Constraints

- Caerness must keep working (its organisation system is untouched; regression tests pass).
- Owner rules hold: engine vetoes, it doesn't list; no ceilings; sex ratios per `power-sex-ratios`; loyalty from bonds, not wages; violence varies by outfit; design figures stay in package data, not engine constants.
- Run sims against a DB copy.

## 7. Left to the builder

- Exact names of the core modules and helpers.
- Whether the rename uses `ALTER TABLE … RENAME` or copy-and-drop (SQLite version dependent).
- How sphere choice functions register (a registry like the task 9 reason checks is the obvious fit).
- Whether the business layer's companies need an `org_seats` row for every clerk or only for level-4 people (follow the task 5 detail ladder).
