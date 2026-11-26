# For review: a three-level simulation design for an AI-run text role-playing game

## Context for the reviewer
This is a design for **Narrative Engine**, a personal text role-playing game. It has two parts:
- **The engine:** a Python/SQLite simulation (about 87,000 lines) of a whole city and its people. It keeps memory,
  money, relationships, organisations, politics, law and history. It is the single source of truth.
- **The game master (GM):** Claude, connected to the engine through an MCP connector (tools such as `scene`,
  `act`, `advance`, `lookup`, `note`, `author` and `money`). The GM narrates, plays the other characters, and calls
  the engine for facts and to record what happens.

The current world is **Saint Jude**: a fictional American port city in 1975, with Italian families, a garage,
social clubs and an organised-crime world. The player plays a new, non-canon protagonist. In the latest playtest that
was Dominic, a young mechanic building a car-tuning sideline.

**Why this design exists.** Two long playtests found many plausibility faults:
- quarrels with no cause;
- people marrying out of nowhere;
- his mother offering him a paid job;
- news about people he'd have no way of hearing about, who didn't matter to him;
- relationships in the record not matching the story as played.

There were also GM faults: moralizing, offering menus, inventing plot hooks and explaining them afterwards, and
asking the player things the GM should have decided. Fixes had been made one symptom at a time. Looking at the code
showed the root cause: the engine used city-wide random rates directly on the named people closest to the
protagonist, and its four separate news feeds had different rules for what reaches him. The design below is the
replacement, agreed with the owner in a long discussion.

**Fixed constraints:**
- no hard caps or ladders anywhere;
- the world doesn't bend toward the protagonist;
- the engine vetoes contradictions but never offers the GM a menu;
- world packages are data only, with no world-specific words in engine code;
- the protagonist lives under the same rules as everyone else;
- token cost matters, both the GM's context per turn and test runs.

**This is revision 3.** It takes in two rounds of outside review (ChatGPT twice, Gemini once) and the owner's decisions. Earlier rounds added: people in several groups at once (a mobster can be a legitimate businessman), pressure only through real transmission paths, knowledge kept apart from truth, gradual concerns, three kinds of engine answer, and tests for life as well as for faults.

**What I'd like from the review:**
- Is the three-level structure sound?
- Is the link between the levels (pressure down, results up, one news gate) well defined?
- Does the split of roles between the engine and an LLM game master hold up?
- What's missing or risky?
- Is the build order (scoring sheet and test bench, then a thin vertical slice, then a playtest) right?
- Concrete suggestions are more useful than general praise.

Two internal notes are mentioned but not included:
- a map of the current code (it found the "roll first, explain after" pattern and the four separate news feeds);
- a study of outside engines (Versu, Talk of the Town, Ensemble, Freeciv and others).

---

# Three simulation resolutions, the GM as storyteller, and the link between them (design, 2026-11-26, revision 3)

Status: for the owner's approval. Nothing has been built.

Background:
- `docs/research/2026-11-26-three-layers-map.md`: what the code does today.
- `docs/research/2026-11-24-outside-engines-study.md`: ideas from outside engines.

Revision history:
- Revision 2 took in one outside review (ChatGPT) and the owner's notes.
- Revision 3 takes in second reviews from ChatGPT and Gemini and the owner's decisions on them.

## Why
In the two Dominic playtests, most faults came from one confusion: the engine used the dice that suit the city as a
whole on named people close to the protagonist. That produced quarrels with no cause, marriages out of nowhere, a
mother offering a paid job, news about nobodies, and relationships that never followed play. The other faults were
GM behaviour: moralizing, menus, invented hooks, and asking the player what it should have decided.

The old approach asked: *what events happen in this city, and who do they happen to?* The new one asks: *what are
these people doing, given who they are, what they want, what they know, and where they stand?*

**Goal:** the city lives on its own; everything near the protagonist happens for a reason; and the GM tells the story
on top of an engine that keeps every fact, sum and relationship in order.

**Anti-goals:**
- caps or ladders (a threshold marks a real change of state, never a points ladder);
- the world bending toward the protagonist;
- one level's method forced onto another;
- an engine that writes the story;
- a GM that ignores the engine;
- **a world that is plausible because nothing happens in it**;
- building a large system before anyone has played it.

The three levels are **resolutions of simulation, not a ranking of people**. Level 1 isn't less important; it is
held at less detail.

## 1. The three resolutions
| Level | Who | How things happen |
|---|---|---|
| 1. Groups | the population held as groups, each with its own rates | group rates, by domain (1.2) |
| 2. Notable | individuals the city has picked out | their role in the city's systems |
| 3. Close and powerful | (a) the protagonist's closest people; (b) the movers and shakers | concerns, knowledge and ties; nothing from a yearly chance |

### 1.1 Background, position, memberships
Each person has three things:
- **background** (origin, family, faith, neighbourhood), which stays for life;
- **position** (what he does and has now), which changes;
- **memberships**, any number of them (outfit, union, parish, association, club), which change too.

A captain can own a legitimate restaurant, and a devout dockworker can run numbers. A man who becomes a businessman
stops feeling dockworkers' pressures but keeps his background.

### 1.2 Group rates without double counting
- **Rates are split by area of life.** Marriage and children come from background and faith. Work, wages and
  layoffs come from position. Arrests and violence come from criminal and ward memberships. Overlapping memberships
  therefore govern different hazards. Where two memberships truly meet in one area of life, a stated competing-risks
  rule settles it. Rates are never averaged.
- **Counts are kept apart:** population counts, membership counts, group rates, and individual exposures and their
  effects. A person is counted once in the population, however many groups he is in.
- **Group rates describe collective tendencies and never become an individual's odds.** At level 3, they show up
  only as pressures in his concerns.

### 1.3 Level 2: what someone matters through
A notable person carries a description, not a rank, of how he matters: money, an office, politics, an organisation,
social standing, a criminal role, or information. Several can apply. That keeps the engine from noticing only the
rich. Notable people are judged against their own kind, never pulled toward an average.

### 1.4 Level 3: one model, closeness and power held separately
Closeness to the protagonist and systemic power are **independent values** in the data. A person can have either,
both or neither. Both kinds of level-3 people run on the same model (concerns, knowledge, ties, choices).
- **Close people** have mostly personal concerns.
- **Movers and shakers** have mostly systemic concerns. They act through their organisations, and being level 3
  doesn't give them a stream of personal drama.

### 1.5 Organisations carry plans out imperfectly
An organisation has its own state: leaders, staff, money, territory, procedures, memory, loyalties and splits. The
engine already holds most of this. A mover's plan is an aim. Whether it happens depends on the organisation's real
ability and on the people under it:
- captains resist, misread an order or pursue their own interest;
- local men are unreliable;
- the target is stronger than expected;
- a deal falls through.

A plan is never an order with a predetermined result.

## 2. Moving between resolutions
Everything here happens independently of the protagonist. His presence is one reason among many.

**Up from 1 to 2: by demonstrated significance in context.** A person is promoted when his position has real
consequences for others or for the city's systems:
- people depend on him for work, money, protection or information;
- he controls a resource others need;
- his acts now matter to more than one system.

There is no points threshold. Opening a back-street garage isn't notable; becoming an employer of twenty is.
Ordinary life events stay as group statistics unless they touch someone already at level 2 or 3.

**Up from 2 to 3:** by real closeness to the protagonist (warmth built in play, not repeated dealings), or by becoming
a mover and shaker.

**Met in a scene, and the protection lock.** Anyone the protagonist meets becomes an individual who can be described
and met again, without being raised to level 3. Any level-1 or level-2 individual who is the object of a level-3
concern, has an open obligation with a level-3 person, or appeared in a recent scene is **protected**:
- `life_matters` can't make changes that conflict with an open thread, such as marrying off the woman Dominic is
  courting or starting a random quarrel with his supplier;
- he changes only through direct interaction, his own role in the city's systems, or explicit promotion.

**Promotion fills in background, never drama.** Ordinary background consistent with his age, groups and position is
filled in as *inferred*: a spouse and children, years in the neighbourhood, staff. **Dramatic history** is never
filled in: no pre-existing grudges, secrets, or hidden links to existing level-2 or level-3 people. None of it is
shown to the GM as something that "has been building".

**Down.** Being simulated less isn't mattering less. Unresolved obligations, debts, grudges, deeds and open matters
stay live and keep acting, so the person can come back naturally. Only how often he is looked at changes.

**Big life changes never delete anyone:** death, incapacity, prison, moving away, retirement, estrangement,
disappearance, return. The original obligation is kept, and what happens to it is recorded explicitly, never
assumed:
- a debt stands against the estate;
- an outfit takes it over;
- a relative chooses to take it on;
- a contract survives;
- a grudge stays with the living party.

## 3. Resolution 3: from pressure to act
**Stages are kept separate:**
1. **pressure**: slow, from his situation;
2. **concern**: he is aware of it, and it shapes his choices;
3. **intention**: he means to do something;
4. **decision**: he has settled on it;
5. **act**.

Wanting to leave a job is not deciding to leave; deciding is not resigning.

**Concerns** come with an origin: owes or is owed, wants, resents (because...), fears for, courts (stage), plans.
Short-lived ones carry an end date. Concerns come from five sources, each recorded:
1. scenes and acts in play;
2. city changes that reach him through a real exposure (section 5);
3. other people's acts;
4. chance happenings that *start* something (an illness, a meeting on a night out, a windfall);
5. **gradual build-up from ordinary life.** Pressures come from his situation (age, home, work, money, his friends'
   lives) and turn into a concern only after they build far enough. The origin records the build-up ("three years on
   the casual list"). Each person's threshold varies, so people of the same age and position don't tip in step. After
   a failed attempt there is a pause. An unmet want can settle into **resignation or adaptation** instead of firing
   for ever.

Chance can start a situation but never supplies a reason for anyone's behaviour.

**Knowledge comes first.** A person acts only on what he knows or believes. The engine keeps apart:
- objective facts;
- what each person knows;
- what he believes (which may be wrong);
- suspicions;
- rumours.

Every record also has a standing:
- *known to exist*;
- *known not to exist*;
- *unknown*;
- *inferred* (from groups or records);
- *not yet looked into*.

An empty record means unknown, never "doesn't exist".

**Belief records cover what matters.** These are money and assets, obligations and debts, tie changes, memberships and
roles, crimes and incidents, and locations and plans. Everyday dialogue stays in the scene log.

**Choosing offscreen.** Between scenes, the engine decides what level-3 people do. It works event by event: a person
with no pressing concern keeps his routine; a person is looked at again when his circumstances change, when a date
he waits on arrives, or when an opportunity bears on an open decision. When he does choose, he chooses like a person:
- **Habit first.** Routines set expectations, not rigid schedules: illness, an emergency or a day off can break them.
- **A narrow view.** He considers a few options that come from a **set of generic actions defined in the package**
  (seek income, call in a debt, court, avoid, escalate, pressure, defect, settle, ...), filtered by his concerns,
  means, ties, place and habits. This list is for the engine offscreen only. In scenes, the GM is free.
- **Competing concerns weigh against each other.** He stays in a job he hates because he needs the money; he keeps
  quiet about a grudge because his mother is ill.
- **Temperament and mood bend the choice.** A close tie holds a hostile choice back but never forbids it.
- **Others weigh in.** Third parties' concerns add their weight.
- **Noise.** Sometimes he simply chooses badly.

Doing nothing is a real choice in its own right, not a fallback. Every choice stores why it was made. The engine
never chooses for the protagonist.

**What waits on the protagonist.** A question in a scene waits for his reply. An offer or demand made to him in the
world has an **expiry or escalation date on the engine's clock**. If time passes, it lapses or escalates, but only if
he was actually told about it. Nothing freezes the world because he is away.

**Ties: several dimensions, depending on context, following play.**
- Affection, trust, respect, resentment, fear and dependence can each be held separately, and per context where
  needed (respects him at work, dislikes him personally). This extends the existing trust, resentment and
  familiarity values.
- Ties move with the scene record and with acts.
- Ties keep their heaviest dated deeds with plain causes.
- Untended regard settles at a resting point that fits the pair, not at zero.
- Kindness repeated in a short window counts for less each time.
- Bonds form and end with hysteresis.

**Decisions come before acts.** The engine knows the decision. The GM learns of it only when that person is in the
scene or about to cross the protagonist's path (section 4). The player finds out through the world, or doesn't.

**Contests: one framework, factors by situation, outcomes beyond win and lose.**

| Contest | What counts |
|---|---|
| Fight | size, strength, skill, weapons, surprise, numbers, ground, drink |
| Bargain | need, alternatives, leverage, information, means |
| Courtship | mutual interest, trust, attraction, circumstances, social constraints |
| Intimidation | reputation, perceived danger, power, temperament, protection |

Outcomes can be a compromise, a retreat, or nothing settled. The figures (for instance, size counts strongly in a
fight but is not decisive) come from package data and are not universal formulas.

**Scenes as social situations.** A night at the bar, a family dinner or a sale is a situation with roles and its own
natural acts, and several can run in one room. A night out for young men produces brief meetings with women, banter,
sometimes a brawl, and rarely the start of something. The GM can set up any plausible situation without a predefined
type.

**Where people are.** Level-3 people have homes, workplaces, haunts and routines, so who can plausibly be where is
known. The engine already holds locations and outings.

## 4. The GM and the engine
The engine is the authority on what is true: who exists, where they are, what they own, know, believe and owe, what
happened, and what follows from it. The GM is the authority on how it is experienced. They work as partners.

**In a scene, the GM plays the people.** At the start of the scene it is given the concerns, ties, temperament and
body of the people present, and it plays them from those. Routine dialogue isn't checked. **The engine checks only
what changes the record**: money, violence and injury, new facts, deals and obligations, and who is where.

| Answer | Meaning | Effect |
|---|---|---|
| Veto | impossible or contradicts the record | refused |
| Character note | possible but out of character, as a neutral reminder of who he is | recorded with the change; the GM continues |
| Consequence note | possible and in character, but weighty | recorded with the change; the GM continues |

Notes never block, and they are framed as facts about the world, never as criticism, so the GM doesn't treat them as
hidden vetoes. When the GM deliberately has someone act strongly out of character, it states why ("desperate",
"misread the situation"), and the reason is recorded.

**What the GM creates becomes canon, as what it is:**
- an **established fact** (the bar is on Carlisle; Palumbo owns it) is real from then on, and simulated;
- a **claim** (the bartender says the owner is in trouble) is that person's statement, believed by those who heard it;
- a **rumour or uncertain sighting** is recorded with who passed it on.

The GM sets down only what's needed. Everything else about a new person or place stays *unknown* until it matters;
the GM doesn't flesh out a biography to fill a gap.

**The GM never rewrites the past.** It never writes "has been building" without a record behind it, and never
supplies a cause for something the engine produced. A missing cause is an engine bug, to be reported. New things
start now.

**Where big things come from:**
1. movers' plans;
2. small things adding up past a threshold, with a decision first;
3. what the player does;
4. **the GM, as storyteller.** Keeping the story alive is part of its job, so it may bring in a big turning event (a
   fire, a new outfit in town, a factory closing). Three conditions apply:
   - it must be plausible for the city and its time, and the engine adds a consequence note if it's unusual ("the
     third dock fire this year");
   - it starts now and is recorded with its origin, and from then on the engine owns its consequences;
   - it is **measured, not banned**: the scoring sheet tracks GM-introduced big events against world-produced ones.
     If the GM keeps reaching for them, that signals the world is too quiet, and the fix is in the engine (more life
     from movers, thresholds and build-up), not a ban on the GM.

**The scene record: a defined format, with stamps during the scene.** When something can't be undone, the GM makes a
short stamp at the moment it happens:
- a claim or a lie;
- a promise or obligation;
- money or goods changing hands;
- an injury;
- someone entering or leaving.

At the end of the scene, one record reconciles everything:

| Part | Example |
|---|---|
| Presence, with times | Frank arrived, Carla left before the talk about money |
| Attention | involved / attentive / overheard / distracted |
| Statements | Dominic says he has $500 saved |
| Beliefs created | his mother believes him (his cash is unchanged) |
| Objective changes | $100 handed over |
| Obligations | Frank promises to repay by Friday |
| Physical changes | Vincent's hand is cut |
| Tie changes | trust between X and Y falls |
| Knowledge changes | Anthony overheard the price |
| Decisions | Frank decides to take the trial |
| Open matters | the meeting next Tuesday |
| New canon | Palumbo's bar, Carlisle Street (fact) |

The default is that everyone present and attentive learns what was said. Only exceptions are written. The engine
checks the record against the stamps and the state, and it refuses to skip time or resume until the last scene is
recorded and checked.

**What the GM sees as building up** is limited to two things. Anything else building in the world stays out of the
GM's context, so it can't leak into hints or an ominous tone.
- **People in the current scene:** their pressing concerns and pending decisions, so they can be played truly.
- **What is about to cross the protagonist's path:** an arrival, a visit, a matter falling due.

**The read budget works on changes.** The full summary, in a fixed order, comes at scene start and after a skip:
1. what waits on the protagonist;
2. the people present and what's building with them;
3. news that reached him;
4. money;
5. texture.

Tool calls during a scene send only what changed. Anything else is available through lookup.

**Storyteller principles.** The rulebook becomes a few principles with playtest examples:
- Read what the engine gave before writing.
- Decide; don't ask. Questions are for the player's own choices only.
- Put engine material into the scene. **Never show the machinery**: no concern lists, scores, "the engine says" or
  out-of-character flags in the story.
- Respect uncertainty: what the record doesn't hold is unknown; decide it and record it, or leave it unknown.
- Other people have their own lives and aren't waiting for the protagonist.
- Keep the story alive. When it's quiet, use what the world offers first; bring in something new when it doesn't.
- Don't make things more significant than they are: an ordinary evening can be ordinary.
- Describe people (bodies, dress, manner) and the protagonist's feelings.
- Out-of-character notes only for plausibility or real consequences, in plain words.
- Don't moralize: the law is lived as people of the time lived it.
- No policies in the protagonist's voice that the player didn't set.
- Let conversations finish, and bring people back when the player adds something.
- No dragging things out. Attention arrives at a plausible pace.

## 5. The link between the resolutions
**Exposure channels carry pressure down.** Places, firms, sectors, streets, piers and organisations are **channels**.
People are attached to channels through their position, memberships, routines and dependencies ("wages from Pier 4",
"shop on Bedford Street", "member of the parish"). A city change is published to a channel as a typed shock. Only
the people attached to it feel the effect.

A pressure therefore needs:
1. a real change at its origin;
2. a real link, which is a channel attachment or a tie;
3. a real effect on the person (fewer shifts, lower takings, a visit, a threat);
4. for it to become a concern, his feeling or knowing the effect.

He can feel an effect without knowing its cause: takings fall, and he doesn't know the club is squeezing the street.

**"The club noticed Carla" is the example of what this rules out.** It has no effect, and nobody could know it. It
would matter only if the club did something real, and then both the effect and how it was learned are recorded.

**Results come up as one causal chain, with timing.** An outcome is recorded once at its origin, and its downstream
effects hang off that one chain. Those effects are immediate (a beating), ongoing (a business hiring) or delayed (a
new business changing its street over months). Delayed effects are **scheduled entries on the due-queue**, so they
can be inspected and audited. Group rates never generate the same consequence a second time: if the factory
closed, the layoffs come from the closure, not from a separate layoff roll.

**Calibration (tests only, level 1 only).** Over several runs, each group's life, counted together with its promoted
members, should come out near that group's rates. Nobody is pushed to fit. A group that is off gets its population,
circumstances or rates examined.

**What reaches the protagonist: one gate, three tests.**
- **Path:** what he saw himself, who told him, or an everyday channel (the newspaper, the radio, talk at work, the
  parish). News passes on as the teller understands it. It can be wrong and can change as it travels. It carries
  its provenance (where it started, who passed it on, firsthand or hearsay) and fades at its own rate.
- **Relevance:** why it matters to him. That means his kin and friends, his money, his business, danger to him or his,
  and his interests (he follows the races, the parish, local politics). Salience is how often the subject comes up in
  his own memory and ties.
- **Attention:** how likely he is to notice it, keep it in mind, or follow it up.

**Big public events** (a strike, a scandal, a murder, a disaster) reach him through everyday channels, so his world
isn't artificially small. **The gate isn't a monitoring system:** close people keep secrets and have private lives.
Feelings and knowledge are separate records.

## 6. Time
The engine already runs on a due-queue, so the world never depends on how often the player checks in.

| Clock | What runs on it |
|---|---|
| Scene time | a played scene, stamped as it goes and recorded at its end |
| Daily | level-3 routines and their exceptions |
| Periodic (weekly or coarser) | level-1 group rates, level-2 upkeep, the economy |
| Event-driven | reconsidering people, decisions acted on later, delayed results, thresholds, expiries and things falling due |

Event-driven work is preferred everywhere, for cost. A three-month absence from the garage doesn't freeze anything.

## 7. Packages
Packages remain data only, with no world words in `engine/`. They supply:
- the groups and their rates by domain;
- the membership kinds;
- the generic action set;
- the contest factors;
- the channel kinds;
- the figures.

Each package **is validated and carries a version**. On load, the engine reports:
- missing group definitions;
- membership references that don't resolve;
- missing rates;
- an incompatible version;
- references to people or organisations that don't exist.

It also tells a missing setting apart from a feature the package deliberately leaves out.

## 8. What happens to the existing code
- **Kept:**
  - the city layers (economy, outfits and organisations, politics, law, population, money, prices, prison, health,
    history, locations);
  - the due-queue clock;
  - bodies (B1.1, B1.2, and the appearance-reading fix);
  - `crystallization` and `tiers.py`;
  - the knowledge and rumour tables;
  - the connector's correction, undo, money and claim tools.
- **Replaced, not added to:**
  - `life_matters` stops running for level-3 people and for protected people, and stays for the rest of levels 1
    and 2;
  - the four news feeds in `connector/timeflow.py` become the one gate, built from `hearsay.py`'s path logic and
    `information.py`'s reliability;
  - old paths are switched off first and deleted once the slice is proven.
- **Reworked:** the held B1 fight work becomes the contest. The P2.32 to P2.37 fixes are reviewed, and whatever
  doesn't fit is dropped.
- **Not built separately:** the queued playtest fixes. This design covers them.

## 9. How "good" is judged
**Two kinds of check:** the faults are gone, *and* life is present. Frequencies are watched to catch a dead or a
frantic world. They are never targets that events are forced to meet.

| Check | What it shows |
|---|---|
| Causes | every level-3 event has a stored cause; no news without path, relevance and attention |
| Social life | friendships, courtships and rivalries develop; people marry, but only after courting |
| Economy | businesses open, grow, struggle, close |
| Organisations | they pursue aims and sometimes fail at them |
| Consequences | effects downstream, on time, never doubled |
| Continuity | people act from their histories; ties match recorded scenes |
| Knowledge | no unexplained omniscience; wrong beliefs persist until corrected; unknown is not treated as nonexistent |
| Variety | different runs and starts give different, plausible histories |
| Restraint | ordinary events stay ordinary |
| GM | engine material woven in; no menus; it decides instead of asking; no moralizing; no machinery shown; clean scene records; how often it brings in big events |

**Engine tests:**
- a fresh save run 3 to 6 months with only routine acts, scored against the sheet;
- **three absence tests:**
  1. months with the protagonist away: did the city change for its own reasons?
  2. his return: does the world feel moved on, and does he find things out naturally rather than from a full
     summary?
  3. important days that have nothing to do with him: a wedding he doesn't attend, a territory fight he never hears
     about, a vote that changes hundreds of lives;
- several different starting saves;
- group calibration across runs;
- for anything that never fires, the reason (nobody wanted it, or something blocked it);
- skip time before and after.

**GM test bench:** a few dozen player turns from the transcripts, replayed against the GM with the real connector,
scored against the sheet. Because it costs tokens, it runs on rulebook changes and before playtests. Mechanical lines
(menus, questions, out-of-character flags, exposed machinery) are checked by script; the rest is read by me.

## 10. Build order
1. **The scoring sheet and the GM test bench.**
2. **Settle the data model before any slice code.** This covers:
   - knowledge, beliefs and record standing;
   - the belief record types;
   - ties with dimensions and contexts;
   - the stages from pressure to act;
   - the scene-record format, stamps, and how a record is checked.

   These are the expensive parts to change later, so they come first.
3. **Slice 2a, the GM–engine loop:**
   - the scene record with stamps;
   - canon by kind;
   - the three engine answers on record-changing proposals;
   - the one news gate (path, relevance, attention) with everyday channels;
   - what's building, limited to the scene and to what crosses his path;
   - the change-based read budget;
   - the rewritten storyteller rulebook;
   - the old news feeds switched off.

   Then **run the GM test bench** on the old transcripts.
4. **Slice 2b, a minimal living world:**
   - routines;
   - a simple offscreen choice (habit, competing concerns, non-optimal), from the generic action set;
   - a simple gradual build-up with varied thresholds and resignation;
   - offers with expiry;
   - the protection lock against `life_matters`;
   - **one mover outside the circle** acting through an exposure channel.

   The test is a ten-step chain: a businessman has a concern → decides → it affects a local business → that affects
   someone close to the protagonist → he hears by a plausible path → the GM presents it → the player responds → the
   engine records it → the world carries on.
5. **The owner plays a fresh save:** an evening first, then a stretch of several game weeks. The playtest isn't
   staged to show off features. Fixes follow.
6. Several group memberships and per-domain group rates; the full offscreen choice (others weighing in, decisions
   before breaks); contests.
7. Movers' plans through organisations, with imperfect execution.
8. Promotion by demonstrated significance; careful demotion; obligations through life changes.

Each step ends in play or a test bench run, not only in passing tests.

## Left to the builder
- the table shapes, within the data model settled in step 2;
- the generic action set's first contents;
- contest weights and gradual-pressure figures from package data;
- read-budget sizes;
- the order of work inside each step.
