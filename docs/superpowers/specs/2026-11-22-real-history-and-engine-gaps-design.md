# Real history on demand, and what the engine cannot hold (DRAFT design)

Status: DRAFT, written without the owner, for the supervisor to take to him. Calls marked **[my call]** are open to correction.

## 1. Intent

The owner's words: "there's only so much real life stuff we can put in the database. There needs to be a way for the agent to look something up and for it to be able to be added into the engine ... some things might not happen when they did, or they might not happen at all." Also: "all of those things are possible with the agent but then the engine won't be able to reflect them."

There are two problems here, and they share one root: the GM can tell more than the engine can hold.

- **A. Real history.** Sixty years of technology, firms, IPOs, politicians, laws and prices can't be preloaded. The GM looks a fact up when play needs it and proposes it with a source and date. The engine checks it against this run's alternate history and records the outcome as dated canon that other systems read.
- **B. Narrated, then forgotten.** Some things a player or NPC plausibly does in Saint Jude have nowhere to live in the engine. They are narrated once and then lost. Section 6 is the audit, ranked. Section 7 is the generic fix.

## 2. Goals, non-goals, anti-goals

**Goals**
- The GM can bring any real fact into play when it is needed, with a source.
- The engine decides whether that fact still happens in this run: on time, earlier, later, differently, or not at all. It decides from named causes and gives its reasons.
- Accepted facts persist as dated canon that business, politics, the law and technology checks all read.
- Nothing about the future sits in the database before play needs it.
- An invention is checked against what the year's technology, money, skill and law can support. There is no date wall.
- Every plausible lasting act ends up as an engine thing that at least one system reads.

**Non-goals**
- A preloaded history of 1975 to 2026.
- The engine reading the web. The GM looks things up and the engine judges.
- Butterfly-effect simulation of world history. Distant history holds unless a named cause in the run breaks it.

**Anti-goals (a failure even if it works)**
- A menu of "historical events available this year".
- A date wall, where the protagonist is refused a cellular phone in 1981 because the real one came in 1983, whatever he paid or built.
- Random drift, where Apple doesn't exist for no stated reason.
- Real people doing things off their record.
- A GM "lookup" that simply writes whatever it found into canon.

## 3. What exists (from reading the code)

- **`worlds/saintjude/timeline.json`** is 63 hand-written entries with real dates, each with `exists`, `available` and `common`. They cover laws (RICO, the 1984 detention act), agencies, lottery games, the casino referendum, port terminals, and devices (pager, fax, VCR, ATM, personal computer, CD).
- **`engine/veto.py` `dated_rules`** refuses any free text that names a timeline entry before its real `exists` date. This is the date wall, and it has two faults:
  - It is hard. Nobody in the run can bring an entry earlier, and the run cannot make it later or cancel it.
  - It is blind to everything not on the list. A Walkman in 1977, a Sony in 1975 or Uber in 1990 passes silently, and nothing is recorded.
- **`engine/facts.py` `world_facts`** is created lazily for tagged packages. It holds tags (Fixed, Open, Weather, Anchor, Tendency, Design, Example), `start_date` and `end_date`, `source` and `holder_actor_id` for offices. `world_fact_overrides` keeps changes, and a Fixed fact changes only with a `cause`.
  - `note(kind="fact")` changes an existing fact. Nothing adds a new dated fact.
- **`historical_anchors`** (Caerness era) is a generic dated record. Its `canon_scope` is setting, campaign or provisional, and it carries `certainty` and `source_kind`.
- **Spec §5.2c** (three spheres) already sets the stance:
  - real people and organisations start from their 1 January 1975 state;
  - "Real dated events ... are calibration and defaults, and the run can plausibly change them";
  - an invention is "checked against what enables it";
  - taking a niche first "can mean the real firm never appears, or appears smaller";
  - things not seeded up front are "seeded when the story reaches it: the GM proposes ... the engine records it and vetoes contradictions. Facts from memory are marked to verify."

  The stance exists. The mechanism doesn't.
- **The politics draft §5.4** says real dated laws are defaults that can be moved, defeated or added. That needs this mechanism for every law beyond the package list.

## 4. Approaches considered

1. **Grow the package timeline** with research sessions writing more entries. This fails the owner's point: it is a database waiting for its time, it never covers 60 years, and dates stay hard.
2. **The GM writes facts through `note`.** This is cheap, but nothing checks causes, nothing dates it in the run, and no system reads it. It is the "narrated and forgotten" problem in another form.
3. **A history ledger (recommended).** The GM proposes a real fact with a source, its real date and what it depends on. The engine resolves each dependency against the run, weighs the outcome, and records the result as a dated entry with effects as data. The package timeline becomes the seed of that ledger, as defaults, and stops being a wall.

## 5. The design (Part A)

### 5.1 The proposal: `author(kind="history")`

This rides the existing `author` tool, whose docstring already says "make something new real" **[my call]**. A new tool would cost the connector a tool slot and the GM one more thing to remember.

`details`:
- `what`: the fact in words ("Microsoft is founded in Albuquerque by Bill Gates and Paul Allen").
- `class`: one of technology, firm, firm_event (IPO, merger, failure), person_event (election, appointment, death, conviction), law, office, price, culture, event. A free word maps to the nearest, as `_kind_of` does now.
- `real_date`: ISO, as precise as known, with a `precision` of day, month or year.
- `source`: a URL and a short quote, or `"memory"`. A `"memory"` fact is marked **to verify**, like the research files.
- `needs`: the preconditions, each a short phrase plus, where possible, a reference (`actor:12`, `org:7`, `history:intel-4004`, `place:…`, `law:…`). These are the causes that had to hold in real history. Examples:
  - Gates and Allen alive and free;
  - the MITS Altair announced (January 1975);
  - no rival BASIC dominant on the Altair.
- `about`: the engine entities it touches, if any.
- `effects` (optional, the GM's proposal): what the fact changes, in the words of section 5.5.

The GM is told in the rulebook to propose the causes honestly, including the ones that would break it in this run. The engine doesn't trust the list blindly. It adds the causes it can see itself (5.3).

### 5.2 When the GM looks something up (lazy introduction)

Nothing is preloaded. A fact enters at one of four moments:

1. **Play reaches a domain.** A scene turns to computers, a council vote or a stock. The GM looks up what was real then and nearby, and proposes only what the scene uses.
2. **A time-skip crosses dates.** `advance` returns, as it already returns interrupts, a short "what was due in the real world" prompt for the domains the protagonist touches (his trades, his offices, his city's politics, the law against him). The GM looks those up and proposes them. This means elections, laws and major firm events in his sphere are never missed, without a list waiting in the database **[my call]**.
3. **A character's plan needs it.** An invention, an investment in a real firm, a run for office. The plan's check asks for its enablers (5.6), and the GM proposes the missing ones.
4. **An NPC with documented history acts.** A real person's next real move (Byrne's 1977 campaign) is looked up when his B-depth turn comes and the engine asks for it.

A fact proposed **for a date still ahead** of the game date (the GM foresees Apple's 1980 IPO while in 1979) is stored as **foreseen**:
- it holds the real date as a default and nothing else;
- no character knows it (no `knowledge` rows);
- it is re-judged when its date arrives, because the run may have changed by then;
- it has no effects until then.

This is the only "waiting" row, and it exists only because play reached for it.

### 5.3 The engine's check: do the causes still hold here?

The engine resolves each `needs` item against the run:
- **Holds:** the referenced actor is alive, free and in the stated role; the org exists; the law is in force; the history entry was accepted on or before the date.
- **Broken:** the actor is dead, jailed or elsewhere; the org is gone or absorbed; the niche is held by someone else; the law was defeated.
- **Unknown:** there is no entity to check, so it is treated as holding, because history holds by default.

The engine also adds causes of its own, from the **divergence ledger** (5.4), when the fact's subject or field shares an entity with a recorded divergence. For example, the protagonist's firm already sells a BASIC for the Altair, or the real founder was killed in the run. This is how the run's own acts reach facts the GM didn't think to link.

The outcome is weighed, not listed. Each broken or bent cause carries a weight: how central it was (the founder himself versus a supplier) and whether a substitute plausibly exists (another investor, another chip). Then:
- **all hold:** **on time**, at the real date;
- **an enabler arrived earlier in the run** (the protagonist funded the chip): **earlier**, allowed only down to the date that enabler appeared plus a plausible lead time from the GM's source;
- **a non-central cause is bent:** **later**, by a delay drawn from the weight;
- **a central cause is broken but substitutes exist:** **changed**. Different people, a smaller firm, another city, a different law text. The GM narrates the changed form within the reason the engine gives;
- **a central cause is broken and no substitute exists:** **not at all**. The fact's "not at all" is recorded too, so it isn't re-proposed every session.

The draw is seeded per campaign and per fact, so it is repeatable, and the reasons always name the causes. The GM may answer with a better-argued proposal: a substitute it has a source for. The engine re-weighs. It never refuses for "not on a list". It refuses only a named contradiction, such as a dead man founding a firm or a law in force before the legislature that passes it exists.

**Distance rule [my call, owner question 1]:** a fact with no shared entity and no divergence near its field passes on time. National and global history holds unless the run touched it. This keeps "Apple exists" from depending on a coin flip, and puts the change where the run actually acted.

### 5.4 The divergence ledger

A new `divergences` table. A row is written whenever the run departs from a known real default:
- a real person dies, is jailed, wins or loses off his real date or outcome;
- a real firm is bought, beaten to its niche or never founded;
- an office goes to someone else;
- a history entry comes out earlier, later, changed or not at all;
- the protagonist founds a firm or venture in a field a real firm later enters (written when that history fact is first proposed, by matching field words).

Each row records the subject entity, the field words, the day, the cause (an event or act id) and a short text. It is cheap and read only by the check in 5.3 and by the GM's `lookup` ("how has this world gone differently?").

### 5.5 Recording: dated canon with effects as data

The accepted outcome becomes:
- a `history_entries` row: class, what, real date, run date (or null for not at all), outcome, reasons, `needs` with their resolution, source, verify mark, effects, status (foreseen, in_force, never, superseded);
- a `world_facts` row with `key = 'history:<slug>'`, tag **Fixed**, and `start_date` as the run date. `lookup` and the Fixed-needs-a-cause rule then work unchanged, and a later change needs a stated cause in the run.

Effects are applied at the run date by class, into systems that already exist or are being designed:

| class | effect (data) | read by |
|---|---|---|
| technology | `tech_level` entry: thing, exists, available, common (run dates), price band | invention check (5.6), business drivers, the law (wiretap, DNA), `dated_rules` |
| law | an in-force law with effects (politics draft §5.4: tax rate, sector cost, crime-policy shift) | law, crime_response, business drivers, `dated_rules` |
| office / person_event | office holder in `world_facts` (`holder_actor_id`); a real person seeded or moved | politics, standing, the law |
| firm | a generic org at B depth (org core) with real founders as real people, a sector, size and money | business sphere |
| firm_event | IPO, merger or failure as an org-core change (ownership, money, holdings) | business sphere, investment |
| price | a price-index point per good or sector | business, wages, `prices_1975.json` successor |
| culture / event | a dated public fact the city can talk about (rumour or public attention seed) | information, standing |

The **package timeline** is loaded as **defaults** into `history_entries` (outcome "default", status per date), not as a wall. `dated_rules` changes from "named before its real date → refuse" to the following:
- for a **law or institution:** before its run date, refuse; it isn't in force here;
- for a **technology:** before its run date, don't refuse. Send it to the invention check (5.6), and refuse only if that check finds a missing enabler;
- an entry whose run outcome is "not at all" is refused with the reason ("the casino referendum failed here in 1976 because …").

### 5.6 Invention plausibility

An act or authored business that builds something (a device, a process, a product, a service) goes through the check:

1. **Enablers.** The GM names what it needs, and the engine looks each up in `tech_level` and `history_entries`. A missing enabler is proposed by the GM right away (5.2, moment 3) and judged. An enabler that doesn't exist yet in the run is a **named contradiction**: "a pocket cellular phone needs cellular networks; none exist in 1977 here". A character can, however, set out to create the enabler. Then it becomes his project, judged the same way.
2. **Distance ahead of the run's technology.** How far the thing is ahead of when its enablers became available scales its cost, time and failure chance. There is no ceiling. A PC company in 1976 is cheap and plausible. A GPS navigator in 1980 needs a satellite constellation nobody can build, so it fails at step 1.
3. **Means.** Competence in the field (`actor_competence`, expertise), money (the ledger), people with the skill (they are hired, and the labour market has them only if the field exists), and time (a commitment with a due day).
4. **Law and demand.** Required approvals (FCC, FDA, as law data) and a market. Demand is read from the business sphere's drivers. Until those exist it is a seeded judgement with reasons **[my call]**.
5. **Result.** A venture in the business sphere, a `tech_level` entry with the run's own date and the inventor as its source, and divergence rows for the real firms in that field. Their later history proposals meet a taken niche and come out changed, later or not at all.

### 5.7 Real people through the same door

A real person who first appears in play (a congressman, a founder, a CEO) is proposed with a source for their 1 January 1975 state. They are checked like any fact: alive, there, in that role, given the run. Then they are seeded under the real-people rule:
- lawful public life in full;
- wrongdoing only of the kinds on their record;
- a clean figure stays clean, and invented men do the dirty work;
- documented later events are history entries for that person, defaults that the run can change.

Their death is decided by the engine's mortality, with the real date as calibration. It isn't a scheduled event **[my call; the mortality model already takes canon anchors]**.

### 5.8 Ties to the business and politics designs

- **Business ("business-design").** Firms founded after 1975, IPOs, mergers and failures arrive as `firm` and `firm_event` entries. The firm population beyond the seeded large firms grows only through this door. Sector drivers read `tech_level` (what products exist and their cost) and price points. The invention check (5.6) produces ventures in business's shape. A real firm's answer to an offer (Microsoft taking no outside money until 1981) is the real person's documented stance, looked up when the offer is made. The business spec should own: what a firm org's money and holdings fields are, how an IPO changes them, and how a demand judgement is made.
- **Politics ("politics-design").** Offices and the election calendar beyond what the package seeds, the results of real elections outside Saint Jude, and every law beyond the package list come through this door. Real results are the defaults, and the politics simulation decides where the run touched them: the protagonist's money, his candidates, scandals he caused. Laws carry their effects as politics §5.4 data. The politics spec should own: which offices are simulated, as opposed to taken as history defaults, and at what distance from Saint Jude (owner question 3).
- **The law.** Every new statute, ruling or agency (the 1984 Act, Smith v. Maryland, CALEA, the PATRIOT Act) is a law entry. Its run date gates what the law layer can do.

## 6. Part B: the audit (narrated, then forgotten)

**Method.** I read the act, author and note paths in the connector and `engine/free_operation.py`, `player_operations.py`, `authoring.py`, `facts.py`, `veto.py`, the org-core tables and the Saint Jude seed.
- **Confirmed** means I traced the code path.
- **Likely** means the tables exist but I found no GM path that fills or reads them in Saint Jude. These are flagged for a builder to verify before fixing.

**The root finding (confirmed).** The engine's catch-all is good on the way in and empty on the way out. `free_operation` accepts any intent nothing models as an `obligations` row, with costs taken and a due day. When the day comes, `settle_due` writes "It was carried out as planned" to a log and marks the row done. Nothing is created, no system reads it again, and no one in the world knows of it beyond the log. So everything below that falls to the catch-all is held for its duration and then forgotten. This is the gap behind most of the list.

Ranked by likelihood in Saint Jude play × how much it matters:

| # | What a player or NPC plausibly does | Held today? | Does B-depth org catch it? | What's missing |
|---|---|---|---|---|
| 1 | **Expand outside Saint Jude**: a crew in Philadelphia, a numbers bank in Newark, a piece of Atlantic City, a contact in Miami or Sicily, a family taking over another | **No, confirmed.** `authoring._place` refuses "there is no place called …" for anything outside the seed's 70 places, and no author kind makes a place | Partly: an org can be authored, but its seats, holdings and lines need a `location_id` | **Lazy places:** a place or jurisdiction made on demand at coarse depth (population, its offices and law agencies as data, which outfits are there). The politics draft §9 asks for this |
| 2 | **A lasting venture by free operation**: start a loan-sharking book in a new district, open a chop shop, set up a bookmaking wire, rig a bid, start a newspaper, buy a pier | Only until due day, **confirmed** (above) | The depth rule says it should become a B org; the code doesn't do it | **Settle into a thing**: the commitment's result becomes a holding, a line or an org at B depth, with money lines and legality (section 7) |
| 3 | **Buy or own property and assets**: a building, land, a house, a car, a truck fleet, a boat, a plane | **Likely no.** `trade` only matches "business / shop / stall / inn …", so the rest falls to the catch-all. A `possessions` table exists, but I found no Saint Jude path into it | No: assets aren't orgs | An **asset** shape: owner, legal owner (a front), place, value, upkeep, income, who knows, and whether it was bought with dirty money |
| 4 | **Deals and promises between people**: "10% of the take", a partnership, a supply contract, a loan to a councilman, a silent stake in a club | Partly: `lend` and `agreements` exist, and org arrangements cover payoffs to officials | Payoffs, yes (`org_arrangements`); other deals, no | An **arrangement** shape that covers any two-party terms (who owes what, when, and what breach costs), read by tension, loyalty and standing |
| 5 | **Real-world dated facts**: a new device, a firm, a law, an election result, prices | Only the 63 timeline items, and those as a wall | n/a | Part A |
| 6 | **Invest or speculate**: buy shares of a real firm, gold, real estate, back a start-up | **No** (no shares or market table found) | No | Business sphere plus Part A firm events. Until then, an asset with a value that the GM can't move by narration |
| 7 | **Marriage, affairs, children, family break-ups for the protagonist** | Partly: authoring a person with ties marries or makes kin (`_marry`, kinship). Marrying an existing NPC in play, a mistress or a divorce: **likely no** path | No | An **arrangement or relation** shape for unions (`household_unions` exists, but I found no Saint Jude path); divorce as a civil matter (row 10) |
| 8 | **Inventions and new products** | No | No | Part A 5.6 |
| 9 | **Politics by the protagonist**: run a candidate, donate, deliver a ward, sit on a board | Offices can be held (`holds`); donations and elections, no | Politics as B orgs per the politics draft | The politics draft covers it; it needs Part A for anything beyond the city |
| 10 | **Civil law**: sue, be sued, injunctions, liens, divorce, bankruptcy, a business license revoked | **No.** The law layer is criminal | No | The law layer's civil side: a case of the same shape with money and an order as outcomes (a prison or law spec follow-up) |
| 11 | **Taxes and the books**: income tax on legit income, IRS audits, laundering through a business, a false-return case | **Likely no** (Bank Secrecy Act is in the timeline; I found no tax liability) | Partly: org money exists | Tax as law data read by the ledger. An audit is a law case started by gaps between visible spending and declared income (the "Capone" path) |
| 12 | **False identities and documents**: an alias, a fake passport, a no-show job as cover, a front owner | **No** (there is a front owner in `possessions.legal_owner`, but no path) | No | An identity or cover record on the actor, read by the law (who they think owns what) and by the information layer |
| 13 | **Media**: plant a story, buy a reporter, own a paper or a radio station, a TV exposé about him | Partly: rumours and public attention | A paper is an org at B | Press as an org that turns knowledge into public attention, which the information design already points at |
| 14 | **Money hidden abroad**: a Bahamas or Swiss account, a courier run | No (no place, no bank) | No | Lazy places (row 1) plus the asset shape (row 3) |
| 15 | **Faith acts**: tithe, take a vow, sponsor a parish, a priest's counsel | **Likely partly.** Religious tables exist (Caerness); Saint Jude reachability unverified | Church as an org, yes | Verify the Saint Jude path. The "conviction pivot" makes this likelier than it was |
| 16 | **Sport**: own a boxer or a team stake, fix a fight, build a stadium | Partly: prizefight and betting tables exist; Saint Jude reachability unverified | A club is an org | Verify. It belongs to the sports-campaign design |
| 17 | **Union work**: take a local, run a pension fund, a strike | Likely caught: unions are orgs with seats; ERISA is in the timeline | Yes | Check that a pension fund is an org-money pool the law can read (ERISA) |
| 18 | **Health, injury, addiction, habits** | Caught: harm, health and dependency exist | n/a | — |
| 19 | **Learning a skill, a degree, a licence (bar, broker, pilot)** | Training is caught; credentials **likely no** in Saint Jude | No | Credentials as data per field, read by law (who may practise) and business |
| 20 | **Small lasting details**: his habits, his apartment's look, a scar | Held as `note` detail text | n/a | Fine as text; nothing reads it, and nothing needs to |

## 7. The generic fix: five shapes, each with a reader

The depth rule says no silent bucket: anything with no mechanism becomes a generic living org at B depth. Rows 1 to 4, 6, 7 and 12 show that an org isn't the only shape a lasting thing takes. The fix generalises the rule to **five B-depth shapes**. Every narrated lasting thing becomes one of them, and each shape has at least one system that reads it:

| shape | made from | holds | read by |
|---|---|---|---|
| **Org** (exists) | a group with a purpose | seats, money, agenda, reactions | the org core, tension, the law |
| **Place** (new, lazy) | a named place outside the seed | coarse population, jurisdiction, offices and law agencies as data, outfits present, routes | travel, authoring, org seats and lines, politics, the law |
| **Holding** (extend `org_holdings` and `org_lines`, or `possessions`) | an asset, venture or property | owner, front owner, place, value, upkeep and income, legality, who knows | ledger and org money, the law (seizure, tax, RICO forfeiture), heat, information |
| **Arrangement** (extend `agreements` and `org_arrangements`) | any two-party terms | parties, terms, due, breach cost, witnesses | tension, loyalty, standing, the law (a co-conspirator) |
| **Dated fact** (Part A) | a real or run-made fact | class, run date, effects | business, politics, the law, the invention check |

The three changes that close whole classes:

1. **The catch-all settles into a shape [the biggest single fix].** `settle_due` stops ending at "carried out as planned". A settled commitment becomes a Holding, an Arrangement or an Org, judged from its words and costs the way `author` chooses its kind now. It keeps its money lines and its legality, and it registers who knows. The protagonist's chop shop then earns, draws heat, can be raided and can be inherited. If the shape can't be judged, it asks the GM through `reason_kind: input_gap` and never drops it.
2. **Lazy places.** `author(kind="place")` and the travel path make an unknown real place at coarse depth from a GM proposal: its 1975 state with a source. It is checked against the gazetteer (a real town Saint Jude replaces is still refused). Jurisdiction data comes in as history entries (its offices, law agencies and outfits). This opens expansion, travel, accounts abroad and the outer ring as places rather than names.
3. **A coverage tripwire.** The silent-disconnection audit lesson ("check reachability before tuning") becomes a standing test and a play-time check:
   - **Test:** for each shape, a fixture builds one through the GM tools and asserts a reader changes because of it (the venture's income reaches org money; the arrangement's breach raises tension; the place's office appears in politics).
   - **Play:** `note(kind="recap")` already carries threads. The connector compares the recap's lasting things against what the turn created. When a thread names something with no entity behind it, the next tool result carries an "unheld: …" line, so the GM authors it or lets it go knowingly. **[my call: a warning, never a refusal]**
   - **C-depth flag:** repeated settlements of one class (three civil disputes, four foreign ventures) raise the depth rule's "play is heading here" flag. That's the signal to build C depth for that domain.

## 8. Constraints

- Packages are data. Class words, effect fields and the timeline defaults live in the package or are generic. There are no world words in `engine/`.
- Engine vetoes, not menus. The engine never offers what history has in store. It answers proposals.
- No hard caps. Dates and limits are defaults and costs. Refusals name a missing cause or a contradiction.
- The protagonist is under the same rules, and real people stay within their record.
- Caerness is untouched: no timeline and no history ledger means none of this runs.
- Schema migration, and sims against a DB copy.

## 9. Order of work [my call]

1. The catch-all settles into a shape (7.1). It is the largest gap, and every sphere needs it.
2. The history ledger core: `author(kind="history")`, `history_entries`, divergences, `world_facts` mirroring, and the timeline loaded as defaults with the `dated_rules` change (5.1 to 5.5).
3. Lazy places (7.2).
4. The invention check (5.6), with `tech_level`.
5. The coverage tripwire (7.3) and the `advance` "what was due" prompt (5.2, moment 2).
6. The business and politics specs plug firm, firm_event, law and office effects in as they are built.

## 10. Left to the builder

- Whether `history_entries` and `historical_anchors` merge (anchors have a good shape: certainty, scope, source kind).
- The exact weights and delay distributions in 5.3 and the lead-time floor for "earlier". Report calibration, never enforce it.
- How the field words for divergence matching are kept (a small package word list versus the GM supplying them with each proposal).
- Whether the Holding shape extends `org_holdings` and `org_lines` or `possessions`. My lean is the org tables, because they already carry legality and money.

## 11. Open questions for the owner, most important first

1. **How far does the run bend distant history?** My call is that real history holds unless something in the run touches it through a named cause, so Apple and the Berlin Wall happen on time unless he or his world changed their causes. The alternative is a little general drift (chance alone moves dates a bit), which feels more alive and is less predictable.
2. **Can the protagonist get ahead of history from foreknowledge?** He is an invented man in 1975 with no knowledge of the future, but the GM and the player know it. Does the engine refuse a plan whose only basis is knowing the future (buying Apple stock in 1977 "because"), unless there is an in-world reason? Or is that the player's skill and allowed? My lean: allowed, but his NPC advisers and his own competence judge the bet without foreknowledge, so it is a costly gamble to them.
3. **How wide is history simulated rather than taken as given?** My call: Saint Jude, New Jersey and the outer ring are simulated. National politics is simulated only where the run touched it (his donations, his candidates). The rest of the world is history defaults.
4. **Sources.** When the GM can't look something up (no web search on the phone), is "from memory, to verify" good enough to make it canon, or should those stay provisional until verified?
5. **The catch-all settling (7.1).** Is it fine for the engine to judge the shape of a settled commitment from its words, and ask the GM only when it can't tell?
