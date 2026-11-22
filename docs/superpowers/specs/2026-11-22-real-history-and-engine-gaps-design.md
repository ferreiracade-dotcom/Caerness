# One intake: anything narrated sticks, real history included (DRAFT design)

Status: APPROVED by the owner 2026-11-22 (v2, one intake; his answers to the open questions are folded in and recorded in section 11). Calls still marked **[my call]** were accepted with the design.

## 1. Intent

The owner's words: "there's only so much real life stuff we can put in the database. There needs to be a way for the agent to look something up and for it to be able to be added into the engine ... some things might not happen when they did, or they might not happen at all." Also: "all of those things are possible with the agent but then the engine won't be able to reflect them."

The root of both is the same: the GM can tell more than the engine can hold.

**Owner's clarification (binding, 2026-11-22, via the supervisor):**
- The audit closes the gaps found now, but some will always be missed. So the core deliverable is a generic **catch-all**: whenever the GM plausibly narrates something the engine has no mechanism for (expansion outside the city, a new kind of venture, an institution, a custom), there must be a way to make it stick. It is recorded as a persisting, simulated thing with owners or people, money, an agenda, a place, dates and consequences, so it can't be forgotten and doesn't ruin the run.
- It is flagged as a gap for a later deep build.
- It extends the depth rule (B: a generic living org through the org core) to anything, not only orgs: facts, standing arrangements, customs, territories, technologies.
- Real history feeds it. A looked-up real fact enters through the same path, checked against the alternate history.
- There is **one intake with veto-only checks**, not two systems.

So the design is one door, **the intake** (section 5). Its parts:
- the generic thing it records (5.1);
- the checks it runs (5.2);
- how a thing lives at B depth (5.3);
- how it is flagged for C (5.4).

Real history (5.5 to 5.10) is the intake with a source and a real date, which add one extra check: do the causes still hold in this run? Section 6 is the audit, which says what the intake must cover first. Section 7 says what the intake replaces.

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

1. **Grow the package timeline and add mechanisms one by one.** This fails the owner's point: it is a database waiting for its time, it never covers 60 years, and every missed case is forgotten until someone builds for it.
2. **Two systems: a history ledger plus a separate catch-all.** This is what the first draft did. The owner ruled it out: two doors means two sets of checks and a GM who must choose between them.
3. **One intake (chosen by the owner).** Every lasting thing the GM narrates, invented or real, goes through `author`.
   - The engine picks the nearest shape it has, runs veto-only checks, and records it as a living B-depth thing with owners, money, agenda, place, dates and consequences.
   - A thing that has a source and a real date also gets the history-causes check.
   - Anything without deep machinery is flagged as a gap for a C build.
   - The package timeline becomes intake defaults and stops being a wall.

## 5. The design

### 5.1 The intake and the generic thing

**The door.** `author(kind, details)` is already "make something new real", and its `kind` is already free text. The intake widens it. No new tool **[my call]**. Free-operation commitments that settle (`settle_due`) and lasting outcomes of `act` also pass through it internally, so nothing lasting bypasses the door.

**The common fields** every thing may carry, whatever its kind. All are optional except `what`, and the engine fills or asks for the rest:
- `what`: the thing in words ("the Ferrante crew's numbers bank in South Philadelphia", "the families' truce for the Feast of Saint Rocco", "the pocket pager", "Microsoft").
- `people`: owners, members and leaders, as refs or new persons (made by the person path).
- `place`: a ref, or a place name. An unknown real place is made lazily at coarse depth (5.3), and a gazetteer-replaced town is still refused.
- `money`: what it costs to start (from whom, taken by the ledger), and its yearly or weekly income and upkeep (and from where).
- `agenda`: what it wants or does, in words ("grow into Camden", "hold the truce", "sell to hospitals").
- `dates`: start, end or recurrence (a custom's yearly day), and due dates.
- `legality`: legal, grey or illegal, under which law where known.
- `knows`: who knows it (the information layer).
- `consequences`: what it changes, in words, which the engine maps to readers (5.3).
- **Real facts only:** `source` (a URL and a quote, or `"memory"`, marked to verify), `real_date` with `precision`, and `needs` (the causes it depended on in real history).

**Shapes.** The engine chooses the nearest shape it can deepen, as `_kind_of` does now. It reads the words first, then the fields present:

| shape | backed by | examples |
|---|---|---|
| Person | actors (exists) | a new man, a real congressman |
| Org | the org core (exists) | a crew in Philadelphia, a newspaper, a PAC, a start-up firm |
| Place / territory | locations plus a coarse jurisdiction, and territorial control | Newark, Atlantic City, a Bahamas bank's island, "the docks south of Pier 9" |
| Holding | `org_holdings` and `org_lines`, or `possessions` | a building, a fleet, a chop shop, a share stake |
| Arrangement | `agreements` and `org_arrangements` | 10% of the take, a supply contract, a marriage |
| Custom / standing rule | a recurring dated fact with participants | a truce week, a tribute day, a tithe, the Sunday dinner where disputes are heard |
| Technology | `tech_level` (new) | the pager, the microcomputer, an invention of his |
| Dated fact | `history_entries` plus `world_facts` (new and existing) | a law, an IPO, an election result, a price |
| **Thing** (the floor) | `held_things` alone | anything that fits none of the above |

**One row for every intake, whatever its shape.** Every intake writes a `held_things` row:
- the shape, plus the backing table and id if any;
- people, place, money lines, agenda, dates, legality and knows;
- consequences and the readers they were mapped to, with any unmapped words kept;
- source and verify mark;
- a `depth` field, `B` until C is built;
- a gap flag.

If no shape fits, the row itself is the thing, and the generic tick (5.3) keeps it alive. **This is the guarantee: nothing accepted is ever only a log line.**

### 5.2 The checks (veto only)

The checks run in order. Each either refuses with a named reason (`reason_kind`: contradiction or input_gap), scales the thing down with its reason, or passes. None offers options.

1. **World text.** The gazetteer and the timeline: a replaced real town is refused. A dated *law* not in force in the run is refused. A dated *technology* goes to check 6 instead of being refused.
2. **Established facts and entities.** A dead owner, a jailed founder, a place already held by someone, a Fixed fact without a cause, or an office already filled is refused, with the clash named.
3. **Real-people rule.** A real person acting off their record (a clean figure doing dirty work, wrongdoing of a kind not on their record) is refused, and the GM is told to use an invented man.
4. **World scale.** Money comes from a named holder and is taken by the ledger. Men come from where men are. An oversized ask gets what exists (`scaled_down`), as authoring does now.
5. **History causes**, only when `source` or `real_date` is given (5.7): the outcome is on time, earlier, later, changed or not at all.
6. **Enablers**, only when the thing is or needs a technology (5.10). A missing enabler is a named contradiction. Distance ahead of the run's technology is cost and time, never a ceiling.
7. **Means and competence**, for a thing someone builds: skill, people and time become a commitment with a due day, and the thing goes live when it settles.

### 5.3 Living at B depth

Every held thing is simulated, so it can't go stale:
- **Money lines** run through the ledger every tick (income and upkeep, to and from its people or org). A thing that can't pay its upkeep weakens and then ends, and its people are told.
- **Its agenda** gives it happenings, on the pattern of `org_happenings`. Each tick it may grow, shrink, draw attention, clash with whoever shares its place or field (org tension), or ask its owner for something (an interaction). The chance is drawn from its size, money, agenda and legality.
- **Consequences** are mapped to readers that exist:
  - illegal means heat and a possible law case where it sits;
  - known by people means knowledge and rumours;
  - a place means that jurisdiction's law and officials;
  - an arrangement's breach means tension and loyalty;
  - a custom's day means its participants' behaviour (a truce lowers violence between the named outfits that week, through org tension);
  - a technology means what business and the law can do;
  - the owner's death means succession and inheritance.

  Words that map to no reader are kept on the row, and they mark the gap (5.4).
- **Lazy places** are made at coarse depth: population band, its jurisdiction's offices and law agencies (their real 1975 state from the GM, through this same intake), outfits present, and routes to Saint Jude. That is enough for org seats, lines and travel to point at.
- **Ending.** It ends when its dates run out, its money fails, it is destroyed (an attack or a raid), or it is folded into a deeper build. Its row stays as history.

### 5.4 The gap flag and the path to C

- Every intake that lands on the **Thing** floor, or carries consequence words no reader takes, writes or bumps a `depth_gaps` row. The row holds the class of thing (normalised words), the count, the first and last day, example held_things ids, and the missing readers.
- `lookup` shows open gaps, and the supervisor or owner sees them as a build queue: the most frequent and most consequential gaps first.
- The depth rule's "play is heading here" flag fires when one class recurs (three foreign ventures, four civil disputes).
- When a C build lands for a class, a migration moves its held things into the new tables and clears the gap. Nothing narrated in the meantime is lost.

### 5.5 Real facts: the same intake with a source

A real fact is proposed through the same door. Example: `author(kind="firm", details={what, real_date, source, needs, people, place, ...})`, or `kind="law"`, `kind="technology"`. The real-fact fields:
- `class`: one of technology, firm, firm_event (IPO, merger, failure), person_event (election, appointment, death, conviction), law, office, price, culture, event. It feeds the shape choice in 5.1.
- `real_date`: ISO, as precise as known, with a `precision` of day, month or year.
- `source`: a URL and a short quote, or `"memory"`. A `"memory"` fact is marked **to verify**. **Owner decision (H4):** a memory-sourced fact about something **major** (a law, an election result, a firm's founding or IPO, a technology's arrival, a real person's office or death) is recorded **provisional**: it may be narrated, but systems read it only as a default until a source verifies it. A **minor** detail (a street price, a model name, a date within the month) is fine from memory. The GM verifies provisional facts when it can search, and verification promotes them with `note(kind="fact")` and the source.
- `needs`: the preconditions, each a short phrase plus, where possible, a reference (`actor:12`, `org:7`, `history:intel-4004`, `place:…`, `law:…`). These are the causes that had to hold in real history. Examples:
  - Gates and Allen alive and free;
  - the MITS Altair announced (January 1975);
  - no rival BASIC dominant on the Altair.
- `about`: the engine entities it touches, if any.
- `effects` (optional, the GM's proposal): what the fact changes, in the words of section 5.9.

The GM is told in the rulebook to propose the causes honestly, including the ones that would break it in this run. The engine doesn't trust the list blindly. It adds the causes it can see itself (5.7).

### 5.6 When the GM looks something up (lazy introduction)

Nothing is preloaded. A fact enters at one of four moments:

1. **Play reaches a domain.** A scene turns to computers, a council vote or a stock. The GM looks up what was real then and nearby, and proposes only what the scene uses.
2. **A time-skip crosses dates.** `advance` returns, as it already returns interrupts, a short "what was due in the real world" prompt for the domains the protagonist touches (his trades, his offices, his city's politics, the law against him). The GM looks those up and proposes them. This means elections, laws and major firm events in his sphere are never missed, without a list waiting in the database **[my call]**.
3. **A character's plan needs it.** An invention, an investment in a real firm, a run for office. The plan's check asks for its enablers (5.10), and the GM proposes the missing ones.
4. **An NPC with documented history acts.** A real person's next real move (Byrne's 1977 campaign) is looked up when his B-depth turn comes and the engine asks for it.

A fact proposed **for a date still ahead** of the game date (the GM foresees Apple's 1980 IPO while in 1979) is stored as **foreseen**:
- it holds the real date as a default and nothing else;
- no character knows it (no `knowledge` rows);
- it is re-judged when its date arrives, because the run may have changed by then;
- it has no effects until then.

This is the only "waiting" row, and it exists only because play reached for it.

### 5.7 The engine's check: do the causes still hold here?

The engine resolves each `needs` item against the run:
- **Holds:** the referenced actor is alive, free and in the stated role; the org exists; the law is in force; the history entry was accepted on or before the date.
- **Broken:** the actor is dead, jailed or elsewhere; the org is gone or absorbed; the niche is held by someone else; the law was defeated.
- **Unknown:** there is no entity to check, so it is treated as holding, because history holds by default.

The engine also adds causes of its own, from the **divergence ledger** (5.8), when the fact's subject or field shares an entity with a recorded divergence. For example, the protagonist's firm already sells a BASIC for the Altair, or the real founder was killed in the run. This is how the run's own acts reach facts the GM didn't think to link.

The outcome is weighed, not listed. Each broken or bent cause carries a weight: how central it was (the founder himself versus a supplier) and whether a substitute plausibly exists (another investor, another chip). Then:
- **all hold:** **on time**, at the real date;
- **an enabler arrived earlier in the run** (the protagonist funded the chip): **earlier**, allowed only down to the date that enabler appeared plus a plausible lead time from the GM's source;
- **a non-central cause is bent:** **later**, by a delay drawn from the weight;
- **a central cause is broken but substitutes exist:** **changed**. Different people, a smaller firm, another city, a different law text. The GM narrates the changed form within the reason the engine gives;
- **a central cause is broken and no substitute exists:** **not at all**. The fact's "not at all" is recorded too, so it isn't re-proposed every session.

The draw is seeded per campaign and per fact, so it is repeatable, and the reasons always name the causes. The GM may answer with a better-argued proposal: a substitute it has a source for. The engine re-weighs. It never refuses for "not on a list". It refuses only a named contradiction, such as a dead man founding a firm or a law in force before the legislature that passes it exists.

**Distance rule (owner decision H1):** real history holds as real **unless the run touches it, directly or indirectly**. Directly means a run divergence shares an entity with the fact (its founder, its firm, its office, its law). Indirectly means a **chain of named causes** links them: the run changed A, A was a named cause of B, and B is a named cause of this fact (the protagonist bankrupted a supplier, the supplier would have financed the founder). The engine walks the `needs` of accepted history entries and the divergence ledger to find such chains, and the reason names every link. There is **no general drift**: chance never moves a fact on its own. With no direct or indirect touch, the fact passes on time.

### 5.8 The divergence ledger

A new `divergences` table. A row is written whenever the run departs from a known real default:
- a real person dies, is jailed, wins or loses off his real date or outcome;
- a real firm is bought, beaten to its niche or never founded;
- an office goes to someone else;
- a history entry comes out earlier, later, changed or not at all;
- the protagonist founds a firm or venture in a field a real firm later enters (written when that history fact is first proposed, by matching field words).

Each row records the subject entity, the field words, the day, the cause (an event or act id) and a short text. It is cheap and read only by the check in 5.7 and by the GM's `lookup` ("how has this world gone differently?").

### 5.9 Recording: dated canon with effects as data

The accepted outcome becomes:
- a `history_entries` row: class, what, real date, run date (or null for not at all), outcome, reasons, `needs` with their resolution, source, verify mark, effects, status (foreseen, in_force, never, superseded);
- a `world_facts` row with `key = 'history:<slug>'`, tag **Fixed**, and `start_date` as the run date. `lookup` and the Fixed-needs-a-cause rule then work unchanged, and a later change needs a stated cause in the run.

Effects are applied at the run date by class, into systems that already exist or are being designed:

| class | effect (data) | read by |
|---|---|---|
| technology | `tech_level` entry: thing, exists, available, common (run dates), price band | invention check (5.10), business drivers, the law (wiretap, DNA), `dated_rules` |
| law | an in-force law with effects (politics draft §5.4: tax rate, sector cost, crime-policy shift) | law, crime_response, business drivers, `dated_rules` |
| office / person_event | office holder in `world_facts` (`holder_actor_id`); a real person seeded or moved | politics, standing, the law |
| firm | a generic org at B depth (org core) with real founders as real people, a sector, size and money | business sphere |
| firm_event | IPO, merger or failure as an org-core change (ownership, money, holdings) | business sphere, investment |
| price | a price-index point per good or sector | business, wages, `prices_1975.json` successor |
| culture / event | a dated public fact the city can talk about (rumour or public attention seed) | information, standing |

The **package timeline** is loaded as **defaults** into `history_entries` (outcome "default", status per date), not as a wall. `dated_rules` changes from "named before its real date → refuse" to the following:
- for a **law or institution:** before its run date, refuse; it isn't in force here;
- for a **technology:** before its run date, don't refuse. Send it to the invention check (5.10), and refuse only if that check finds a missing enabler;
- an entry whose run outcome is "not at all" is refused with the reason ("the casino referendum failed here in 1976 because …").

### 5.10 Invention plausibility

An act or authored business that builds something (a device, a process, a product, a service) goes through the check:

1. **Enablers.** The GM names what it needs, and the engine looks each up in `tech_level` and `history_entries`. A missing enabler is proposed by the GM right away (5.6, moment 3) and judged. An enabler that doesn't exist yet in the run is a **named contradiction**: "a pocket cellular phone needs cellular networks; none exist in 1977 here". A character can, however, set out to create the enabler. Then it becomes his project, judged the same way.
2. **Distance ahead of the run's technology.** How far the thing is ahead of when its enablers became available scales its cost, time and failure chance. There is no ceiling. A PC company in 1976 is cheap and plausible. A GPS navigator in 1980 needs a satellite constellation nobody can build, so it fails at step 1.
3. **Means.** Competence in the field (`actor_competence`, expertise), money (the ledger), people with the skill (they are hired, and the labour market has them only if the field exists), and time (a commitment with a due day).
4. **Law and demand.** Required approvals (FCC, FDA, as law data) and a market. Demand is read from the business sphere's drivers. Until those exist it is a seeded judgement with reasons **[my call]**.
5. **Result.** A venture in the business sphere, a `tech_level` entry with the run's own date and the inventor as its source, and divergence rows for the real firms in that field. Their later history proposals meet a taken niche and come out changed, later or not at all.

### 5.11 Real people through the same door

A real person who first appears in play (a congressman, a founder, a CEO) is proposed with a source for their 1 January 1975 state. They are checked like any fact: alive, there, in that role, given the run. Then they are seeded under the real-people rule:
- lawful public life in full;
- wrongdoing only of the kinds on their record;
- a clean figure stays clean, and invented men do the dirty work;
- documented later events are history entries for that person, defaults that the run can change.

Their death is decided by the engine's mortality, with the real date as calibration. It isn't a scheduled event **[my call; the mortality model already takes canon anchors]**.

### 5.11b Foreknowledge (owner decision H2)

The player and the GM know the future; the protagonist does not. Foreknowledge never pays by itself.

- A bet, investment, purchase or plan whose only basis is knowing the future is judged as the **character** would see it. That means what he could plausibly know on that day and his advisers' competence in the field, never the player's knowledge. Buying Apple in 1977 "because" is judged like any small bet on an unknown garage firm in an unknown field: a long shot his accountant would argue against.
- The player profits from foresight only by **positioning the character** so he plausibly comes across the information. He learns the field (training, competence), hires people who know it (an engineer, a broker, a man in Sunnyvale), reads the trade press, or puts money and men where the news is made. The engine then judges the bet on what those people and his learning could plausibly have told him then, through the information layer and `actor_competence`.
- So the same move can be a reckless guess in one run and a sound bet in another. The difference is the people and learning the character built, not what the player knows.
- This is the protagonist-under-the-same-rules principle: NPCs get the same judgement, and their bets come from their own knowledge and competence.

### 5.12 Ties to the business and politics designs

- **Business ("business-design").** Firms founded after 1975, IPOs, mergers and failures arrive as `firm` and `firm_event` entries. The firm population beyond the seeded large firms grows only through this door. Sector drivers read `tech_level` (what products exist and their cost) and price points. The invention check (5.10) produces ventures in business's shape. A real firm's answer to an offer (Microsoft taking no outside money until 1981) is the real person's documented stance, looked up when the offer is made. The business spec should own: what a firm org's money and holdings fields are, how an IPO changes them, and how a demand judgement is made.
- **Politics ("politics-design").** Offices and the election calendar beyond what the package seeds, the results of real elections outside Saint Jude, and every law beyond the package list come through this door. Real results are the defaults, and the politics simulation decides where the run touched them: the protagonist's money, his candidates, scandals he caused. Laws carry their effects as politics §5.4 data. The politics spec should own: which offices are simulated, as opposed to taken as history defaults, and at what distance from Saint Jude (owner question 3).
- **How wide the simulation runs (owner decision H3).** Saint Jude, New Jersey and the outer ring are simulated. National politics is simulated only where the run touched it (his donations, his candidates, his scandals), directly or through a chain of causes as in 5.7. The rest of the world is history defaults through the intake.
- **The law.** Every new statute, ruling or agency (the 1984 Act, Smith v. Maryland, CALEA, the PATRIOT Act) is a law entry. Its run date gates what the law layer can do.

## 6. Part B: the audit (narrated, then forgotten)

**Method.** I read the act, author and note paths in the connector and `engine/free_operation.py`, `player_operations.py`, `authoring.py`, `facts.py`, `veto.py`, the org-core tables and the Saint Jude seed.
- **Confirmed** means I traced the code path.
- **Likely** means the tables exist but I found no GM path that fills or reads them in Saint Jude. These are flagged for a builder to verify before fixing.

**The root finding (confirmed).** The engine's catch-all is good on the way in and empty on the way out. `free_operation` accepts any intent nothing models as an `obligations` row, with costs taken and a due day. When the day comes, `settle_due` writes "It was carried out as planned" to a log and marks the row done. Nothing is created, no system reads it again, and no one in the world knows of it beyond the log. So everything below that falls to the catch-all is held for its duration and then forgotten. This is the gap behind most of the list.

Ranked by likelihood in Saint Jude play × how much it matters:

| # | What a player or NPC plausibly does | Held today? | Does B-depth org catch it? | Deep (C) build it needs; the intake holds it at B meanwhile |
|---|---|---|---|---|
| 1 | **Expand outside Saint Jude**: a crew in Philadelphia, a numbers bank in Newark, a piece of Atlantic City, a contact in Miami or Sicily, a family taking over another | **No, confirmed.** `authoring._place` refuses "there is no place called …" for anything outside the seed's 70 places, and no author kind makes a place | Partly: an org can be authored, but its seats, holdings and lines need a `location_id` | **Lazy places:** a place or jurisdiction made on demand at coarse depth (population, its offices and law agencies as data, which outfits are there). The politics draft §9 asks for this |
| 2 | **A lasting venture by free operation**: start a loan-sharking book in a new district, open a chop shop, set up a bookmaking wire, rig a bid, start a newspaper, buy a pier | Only until due day, **confirmed** (above) | The depth rule says it should become a B org; the code doesn't do it | **Settle into a thing**: the commitment's result becomes a holding, a line or an org at B depth, with money lines and legality (section 7) |
| 3 | **Buy or own property and assets**: a building, land, a house, a car, a truck fleet, a boat, a plane | **Likely no.** `trade` only matches "business / shop / stall / inn …", so the rest falls to the catch-all. A `possessions` table exists, but I found no Saint Jude path into it | No: assets aren't orgs | An **asset** shape: owner, legal owner (a front), place, value, upkeep, income, who knows, and whether it was bought with dirty money |
| 4 | **Deals and promises between people**: "10% of the take", a partnership, a supply contract, a loan to a councilman, a silent stake in a club | Partly: `lend` and `agreements` exist, and org arrangements cover payoffs to officials | Payoffs, yes (`org_arrangements`); other deals, no | An **arrangement** shape that covers any two-party terms (who owes what, when, and what breach costs), read by tension, loyalty and standing |
| 5 | **Real-world dated facts**: a new device, a firm, a law, an election result, prices | Only the 63 timeline items, and those as a wall | n/a | Real facts on the intake (5.5 to 5.10) |
| 6 | **Invest or speculate**: buy shares of a real firm, gold, real estate, back a start-up | **No** (no shares or market table found) | No | Business sphere plus firm events on the intake. Until then, an asset with a value that the GM can't move by narration |
| 7 | **Marriage, affairs, children, family break-ups for the protagonist** | Partly: authoring a person with ties marries or makes kin (`_marry`, kinship). Marrying an existing NPC in play, a mistress or a divorce: **likely no** path | No | An **arrangement or relation** shape for unions (`household_unions` exists, but I found no Saint Jude path); divorce as a civil matter (row 10) |
| 8 | **Inventions and new products** | No | No | Technology on the intake (5.10) |
| 9 | **Politics by the protagonist**: run a candidate, donate, deliver a ward, sit on a board | Offices can be held (`holds`); donations and elections, no | Politics as B orgs per the politics draft | The politics draft covers it; it needs real facts on the intake for anything beyond the city |
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

## 7. What the intake changes in the code today

With the intake in place, every row of section 6 is held from its first narration:
- rows 1 to 4, 6, 7 and 12 to 14 land on an existing or lazily made shape (Place, Holding, Arrangement, Org);
- rows 5 and 8 are real facts and technologies (5.5 to 5.10);
- row 10 (civil law) and row 11 (tax) land on the **Thing** floor with a gap flag until their C builds.

Section 6's last column is then the deep-build queue, and the `depth_gaps` counts order it from real play.

The concrete changes:

1. **`settle_due` passes through the intake.** A settled free-operation commitment no longer ends at "carried out as planned". Its words, people, costs and target become an intake proposal, and the result is a held thing: the chop shop earns, draws heat, can be raided and can be inherited. Partly funded becomes smaller, never dropped. If the shape can't be judged, the thing lands on the Thing floor with a gap flag, not a refusal **[my call]**.
2. **`authoring._place` stops refusing unknown real places.** It makes them lazily at coarse depth (5.3). A gazetteer-replaced town is still refused.
3. **`dated_rules` reads run dates.** Laws stay refused until in force here, a technology goes to the enabler check, and a "not at all" entry is refused with its reason. The package timeline is loaded as intake defaults.
4. **A generic B tick for held things** (5.3), run in `advance` next to the org core's tick.
5. **The coverage tripwire.** The silent-disconnection lesson becomes a standing test and a play-time check:
   - **Test:** for each shape, a fixture builds one through the GM tools and asserts a reader changes because of it (the venture's income reaches org money; the arrangement's breach raises tension; the place's office appears in politics; a custom's day lowers violence between its outfits; a Thing-floor row pays its upkeep).
   - **Play:** `note(kind="recap")` already carries threads. When a thread names something with no held thing behind it, the next tool result carries an "unheld: …" line, so the GM sends it through the intake or lets it go knowingly. **[my call: a warning, never a refusal]**

## 8. Constraints

- Packages are data. Class words, effect fields and the timeline defaults live in the package or are generic. There are no world words in `engine/`.
- Engine vetoes, not menus. One intake, veto-only checks: the engine never offers what history or the world has in store, it answers proposals.
- No hard caps. Dates and limits are defaults and costs. Refusals name a missing cause or a contradiction.
- The protagonist is under the same rules, and real people stay within their record.
- Caerness is untouched: no timeline and no history ledger means none of this runs.
- Schema migration, and sims against a DB copy.

## 9. Order of work [my call]

1. The intake core: `held_things`, `depth_gaps`, the shape choice, checks 1 to 4 and 7, the generic B tick, and `settle_due` routed through it (7.1, 7.4). Every sphere needs it, and it closes the root gap.
2. Lazy places (7.2).
3. Real facts on the same intake: `history_entries`, divergences, `world_facts` mirroring, check 5, the timeline as defaults with the `dated_rules` change (5.5 to 5.9, 7.3).
4. Technology: `tech_level` and check 6 (5.10).
5. The coverage tripwire (7.5) and the `advance` "what was due" prompt (5.6, moment 2).
6. The business and politics specs plug their deeper shapes in as C builds. Each migration moves held things out of the floor and clears its gap.

## 10. Left to the builder

- Whether `history_entries` and `historical_anchors` merge (anchors have a good shape: certainty, scope, source kind).
- The exact weights and delay distributions in 5.7 and the lead-time floor for "earlier". Report calibration, never enforce it.
- How the field words for divergence matching are kept (a small package word list versus the GM supplying them with each proposal).
- Whether `held_things` holds the floor's own money lines or always goes through a ledger holder (my lean: a ledger holder kind `thing:<id>`).
- Whether the Holding shape extends `org_holdings` and `org_lines` or `possessions`. My lean is the org tables, because they already carry legality and money.

## 11. The owner's decisions (2026-11-22)

1. **H1, distant history:** history stays as real unless the run touches it, directly or indirectly, through a chain of named causes. There is no general drift (5.7).
2. **H2, foreknowledge:** profit only through competence and plausibility. The player positions the character through his learning and his employees so he might plausibly come across the information. The bet is judged on what the character could plausibly know and his advisers' competence, never on the player's foreknowledge (5.11b).
3. **H3, width:** accepted. Saint Jude, New Jersey and the outer ring are simulated, national politics where touched, and the rest is defaults (5.12).
4. **H4, sources:** accepted. Memory-sourced facts are provisional for anything major until verified, and fine for minor detail (5.5).
5. **H5, unclear shape:** accepted. It lands on the Thing floor with a gap flag, never a refusal (7.1).
