# Three levels of simulation, the GM as storyteller, and the link between them (design, 2026-11-26, revision 2)

Status: for the owner's approval. Nothing has been built.

Background:
- `docs/research/2026-11-26-three-layers-map.md`: what the code does today.
- `docs/research/2026-11-24-outside-engines-study.md`: ideas from outside engines.

Revision 2 takes in an outside review (ChatGPT) and the owner's notes on it.

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
- caps or ladders;
- the world bending toward the protagonist;
- events that exist only to make a story;
- one level's method forced onto another;
- an engine that writes the story;
- a GM that ignores the engine;
- a world that is plausible because nothing happens in it;
- building a large system before anyone has played it.

## 1. The three levels
| Level | Who | How things happen |
|---|---|---|
| 1. Groups | the population held as groups, each with its own rates | rates belonging to the groups a person is in |
| 2. Notable | individuals the city has picked out | their role in the city's systems |
| 3. Close and powerful | (a) the protagonist's closest people; (b) the movers and shakers | concerns and ties; nothing from a yearly chance |

### People are in several groups at once
Membership is not one slot. Each person has:
- **background**: origin, family, faith, neighbourhood (Italian, South Hill, a Catholic family);
- **position**: what he does and has now (owns a garage, earns this much, rents here);
- **memberships**, any number of them: the outfit, the union, the parish, the businessmen's association, the club.

Each of these carries its own rates and pressures. Rates are never averaged together. They show up in a person's
concerns and choices, and that is where they meet. A captain can own a legitimate restaurant. A devout dockworker can
run numbers. Background stays for life. Position and memberships change: a dockworker becomes a businessman and stops
feeling dockworkers' pressures, but he keeps his background. City totals are only what the groups add up to.

### Level 2: why someone is notable
A notable person carries a description of **what he matters through**, not a rank. It is one or more of:
- money (land, a firm, capital);
- an office (police, courts, city hall);
- politics (votes, a ward);
- an organisation (a seat in an outfit, a union or a church);
- social standing (respect in a community: a priest, an old family);
- a criminal role;
- information (a bookmaker, a bartender who hears everything).

This keeps the engine from noticing only the rich. Level-2 and level-3 people are usually exceptional, and they are
judged against their own kind, never pulled toward an average.

### Level 3: close and powerful, one model handled two ways
Both kinds of level-3 people run on the same model (concerns, ties, choices). They are handled differently:
- **Close people** have personal concerns: work, health, family, courtship, money, pride. Their life is personal.
- **Movers and shakers** have mostly systemic concerns: territory, deals, votes, rivals, acquisitions. They act
  through their organisations, and being level 3 doesn't give them a stream of personal drama.

Either kind can be both: a close person may come to wield power, and a boss may become personally close.

**Movers and shakers change the city.** Their plans (take a dock, push a vote, squeeze a rival, back a candidate) work
through their organisation and the level-1 and level-2 people under it. An organisation has its own state: leaders,
staff, money, territory, loyalties and splits. These already exist in the engine. A boss doesn't decide everything,
so a captain can act on his own, misread an order or pursue his own interest. A plan sets level-2 people moving,
shifts the rates of the groups it touches, and reaches the protagonist's people only through real paths (section 5).

## 2. Moving between levels
Everything here happens independently of the protagonist. His presence is one reason among many.
- **Up from 1 to 2: by resulting position, not by event.** Opening a back-street garage isn't notable, but becoming
  an employer of twenty is. A minor theft isn't notable, but becoming the man who runs a crew is. Ordinary life
  events (a marriage, a child, a falling-out) stay as group statistics unless they touch somebody already at level 2
  or 3.
- **Up from 2 to 3.** He becomes truly close to the protagonist (warmth built in play, not repeated dealings), or he
  becomes a mover and shaker.
- **Met in a scene.** Anyone the protagonist meets becomes an individual who can be described and met again. Being
  met once doesn't raise him to level 3.
- **A promoted person's background is reconstructed, never invented.** It is drawn from what his groups and the city
  level already hold (for example, he has run the business for six years, if the record allows it). No new past
  *events* are made up for him: no old rivalry, no failed marriage, no friendship with another notable. It is never
  shown to the GM as something that "has been building".
- **Down.** Being simulated less isn't the same as mattering less. A person who loses a firm can still owe money,
  have enemies and connections, face a court case or be trying to climb back. When he drops a level, his unresolved
  obligations, debts, grudges, deeds and open matters all stay live and keep acting, so he can come back naturally.
  Only how often he is looked at changes.
- **Big life changes** (death, prison, moving away, retirement, disappearance, return) never delete anyone. Debts,
  duties and ties pass on or stay open. The engine already handles much of this; the rule is that none of it is
  lost.

## 3. Level 3: concerns, choices, ties
**Concerns.** A concern is one person's live state toward someone or something, with its origin:
- he owes or is owed;
- he wants something;
- he resents someone, with the reason;
- he fears for someone;
- he courts someone, with the stage reached;
- he plans something.

Short-lived concerns carry their own end date.

Concerns come from five sources, and each records which:
1. scenes and acts in play;
2. city changes that reach him through a real path (section 5);
3. other people's acts;
4. chance happenings that *start* something (an illness, a meeting on a night out, a windfall);
5. **gradual build-up from ordinary life.** Repeated experience slowly becomes a concern, with no single event
   behind it: tired of living at home, restless in a job, wanting to marry as his friends settle down, growing more
   devout, wanting his own money. The engine tracks these slow pressures from his situation (age, home, work, money,
   friends' lives) and turns them into a concern once they build far enough. The origin records the build-up, such as
   "three years on the casual list". Without this, people would only have motives when something happens to them.

Chance can start a situation but never supplies a reason for anyone's behaviour.

**Knowledge comes first.** A person acts only on what *he* knows or believes. The engine keeps these apart:
- objective facts;
- what each person knows;
- what he believes, which may be wrong;
- suspicions;
- rumours.

A boss doesn't know what two mechanics said in private unless word travelled to him by a real path.

**Choosing offscreen.** Between scenes, the engine decides what level-3 people do. People choose like people, not
optimally:
- **Habit first.** He weighs options only when a concern presses.
- **A narrow view.** He considers the few acts that his circumstances bring to mind: his concerns, means, ties, habits
  and where he is. These options are worked out from his situation, not taken from a fixed catalogue.
- **Temperament and mood bend the choice.** A close tie holds a hostile choice back but never forbids it.
- **Others weigh in.** Third parties' concerns add their weight.
- **Noise.** Sometimes a person simply chooses badly.

Every choice stores why it was made, and doing nothing is often the choice. When the protagonist must answer, the
matter waits for him and never lapses. He lives under the same rules as everyone else, but the engine never chooses
for him.

**Ties have several dimensions and follow play.**
- A tie can hold affection, trust, respect, resentment and dependence separately: two brothers can love each other
  and still compete. The engine already keeps trust, resentment and familiarity, and the slice extends these where
  needed.
- Ties move with the end-of-scene record (section 4) and with acts.
- A tie keeps its heaviest dated deeds with plain causes, so the GM can say "since the night at the Tap".
- Untended regard settles at a resting point that fits the pair (kin stays warm), not at zero.
- Kindness repeated within a short window counts for less each time.
- Bonds form when a threshold is crossed and end only once regard falls well back past it (hysteresis).

**Decisions come before acts.** A decision to break (leave the crew, end the courtship, move against a rival) is
stored with its reason and acted on later. The engine and the GM know about it; the player finds out through the
world, or doesn't.

**One contest.** When concerns meet head-on (a quarrel, a bargain, a fight, a courtship), one model decides it from
both sides' states against the stakes. Size counts in a fight but doesn't decide it (the bigger man wins about two
in three), and weapons override size. In a bargain, need counts.

**Scenes as social situations.** A night at the bar, a family dinner or a sale is a situation with roles and its own
natural acts, and several can run in one room. A night out for young men produces brief meetings with women, banter,
sometimes a brawl, and rarely the start of something. The GM can set up any plausible situation without a predefined
type. The engine checks it and records what happened.

**Where people are.** Level-3 people have homes, workplaces, haunts and routines, so who can plausibly be where is
known. Nobody appears across the city because a scene wants him there. The engine already holds locations and
outings; the slice gives level-3 people routines.

## 4. The GM and the engine
The engine is the authority on the world: who exists, where they are, what they own, know, believe and owe, what
happened, and what follows from it. The GM is the authority on how it's told. They work as partners.

**In a scene, the GM plays the people.** It plays them from their concerns, ties, temperament and body, and it moves
the story on. To what the GM proposes, the engine gives one of three answers:

| Answer | Meaning | Effect |
|---|---|---|
| Veto | impossible or contradicts the record | refused |
| Character note | possible, but out of character ("Aurelio is cautious and hardly knows him") | GM weighs it, may keep its choice |
| Consequence note | possible and in character, but it has weight ("insulting him in front of his men will be answered") | GM weighs it, may keep its choice |

**What the GM creates becomes canon, as what it is.**
- **Established fact** (the bar is on Carlisle; it is owned by a man named Palumbo) is real from then on, as real as
  anything the engine started with, and simulated from then on.
- **A claim** (the bartender says the owner is in trouble) is recorded as that person's statement. It is believed
  by those who heard it and true only if the record makes it so.
- **A rumour, or an uncertain sighting**, is recorded as such, with who passed it on.

So a GM-made rumour never becomes history by accident. Big additions get a plausibility note against the city and its
time. The connector's existing `claim` kind is the base for this.

**The GM never rewrites the past.** It never writes "has been building" with nothing on record, and never supplies a
cause for something the engine produced. A missing cause is an engine bug, to be reported. New things start now.

**Every scene is recorded when it ends, lean by design.** The GM records:
- who was there;
- what passed between them;
- anything new;
- **only the knowledge that differs from what everyone saw**: a lie, a secret, something overheard, somebody who
  wasn't listening.

By default, everyone present learns what was said, and anything the protagonist claims becomes the listener's belief,
not a fact. If Dominic tells his mother he has $500 saved, she believes it; his cash doesn't change. Obligations
created in the scene (a promise, a debt, a deal) are recorded as obligations. The engine refuses to skip time or
resume until the last scene is recorded.

**Where big things come from:**
1. the movers and shakers' plans;
2. small things adding up past a threshold, with a decision first;
3. the GM bringing a big thing in directly, if it is plausible.

**The engine shows the GM what's building up.** This is a short list, chosen by how much each item matters to the
protagonist and how close it is to tipping. It is for the GM, not the player. Its sizes are set by the read budget.

**The GM's read has a budget.** Each tool response has a fixed size and order:
1. what demands the protagonist's answer;
2. what's building up;
3. news that reached him;
4. money;
5. texture.

Anything more is available through lookup, never pushed.

**Storyteller principles.** The rulebook becomes a few principles with playtest examples, replacing the growing list
of don'ts:
- Read what the engine gave before writing.
- Decide, don't ask. Questions are only for the player's own choices.
- Put engine material into the scene. **Never show the machinery**: no concern lists, scores, "the engine says" or
  out-of-character flags in the story.
- Respect uncertainty: what the engine doesn't hold, the GM doesn't pretend to know. It decides it and records it, or
  leaves it unknown.
- Other people have their own lives and aren't waiting for the protagonist.
- Don't make things more significant than they are: an ordinary evening can be ordinary.
- Describe people (bodies, dress, manner) and the protagonist's feelings.
- Out-of-character notes only for plausibility or real consequences, in plain words.
- Don't moralize: the law is lived as people of the time lived it.
- No policies in the protagonist's voice that the player didn't set.
- Let conversations finish, and bring people back when the player adds something.
- No dragging things out, and attention arrives at a plausible pace.

## 5. The link between the levels
**Pressure down needs a transmission path.** A city change affects a person only through four things:
1. a real change at its origin;
2. a real link to him: a dependency (his wages come from the docks), a tie, a role, or exposure (his shop is on the
   street being squeezed);
3. a real effect on him (fewer shifts, lower takings, a visit, a threat);
4. for it to become a concern, his knowing or feeling the effect, by a real path.

**"The club noticed Carla" is the example of what this rules out.** It has no effect and no way for anyone to know.
It would matter only if the club did something real: asked about her, leaned on her uncle's shop, or said something
to Dominic. Then the effect and how it was learned are both recorded. A wealthy man with no tie to the docks feels
nothing when the docks slow.

**Results up, with timing.** Level-3 and level-2 outcomes change their groups, households and roles:
- **at once**, such as a beating that changes who is afraid;
- **ongoing**, such as a business that hires;
- **delayed**, such as a new business changing its street over months, or a vote changing the neighbourhood over
  years.

Results are not just counted into a statistic.

**Calibration (tests only, level 1 only).** Over several runs, each group's life, with its promoted members counted
back in, should come out near that group's rates. Nobody is pushed to fit. If a group is off, the population, the
circumstances or the rates are examined.

**What reaches the protagonist: one gate.** An item reaches the GM only with a path and a stake.
- **Path:** who told him or what he saw. News is passed on *as the teller understands it*: it can be wrong, it changes
  as it travels, and it carries its provenance (where it started, who passed it on, firsthand or hearsay). It fades
  at its own rate: a passing rumour within days, something about a close friend for years.
- **Stake:** close kin or friends, his money, his business, or danger to him or his. Salience is how often the subject
  comes up in his own memory and ties.
- **The gate isn't a monitoring system.** Close people keep secrets, have private lives and sometimes deliberately
  hold things back.
- **Feelings and knowledge are separate records**, each with its own fading.
- City changes with no path to him act only through what they change. Gerald Orsini simply comes back to book
  Stage 2.

## 6. Time
The engine already runs on a due-queue: each process says when it is next due, and skips advance through those dates.
The world never depends on how often the player checks in. The design keeps that and states the clocks:

| Clock | What runs on it |
|---|---|
| Scene time | what happens in a played scene, recorded at its end |
| Daily | level-3 routines, concerns, offscreen choices |
| Periodic (weekly or coarser) | level-1 group rates, level-2 upkeep, the economy |
| Event-driven | decisions acted on later, delayed results, thresholds crossed, things falling due |

Event-driven work is preferred wherever possible, for cost. A three-month absence from the garage doesn't freeze
anything.

## 7. What happens to the existing code
- **Kept:**
  - the city layers: economy, outfits and organisations, politics, law, population, money, prices, prison, health,
    history, locations;
  - the due-queue clock;
  - bodies (B1.1, B1.2 and the appearance-reading fix);
  - `crystallization` and `tiers.py`;
  - the knowledge and rumour tables;
  - the connector's correction, undo, money and claim tools.
- **Replaced, not added to:**
  - `life_matters` stops running for level-3 people and stays for levels 1 and 2;
  - the four news feeds in `connector/timeflow.py` become the one gate, starting from `hearsay.py`'s path logic and
    `information.py`'s reliability;
  - the old paths are switched off for level-3 people first, and deleted once the slice is proven.
- **Reworked:** the held B1 fight work becomes the contest; the P2.32 to P2.37 fixes are reviewed, and whatever
  doesn't fit is dropped.
- **Not built separately:** the queued playtest fixes. This design covers them.
- **Group data:** the slice needs per-group rates and multiple memberships per person, as package data. Check what the
  Saint Jude package holds first.

## 8. How "good" is judged
**Two kinds of check:** the faults are gone, *and* life is present. A world that passes every fault check because
nothing happens has failed.

| Check | What it shows |
|---|---|
| Causes | every level-3 event has a stored cause; no news without a path and a stake |
| Social life | friendships, courtships and rivalries develop; people marry, but only after courting |
| Economy | businesses open, grow, struggle and close |
| Organisations | they pursue aims on their own |
| Consequences | events have effects downstream, on time |
| Continuity | people remember and act from their histories; ties match recorded scenes |
| Knowledge | people act only on what they know; wrong beliefs persist until corrected |
| Variety | different runs and different starts give different, plausible histories |
| Restraint | not every event becomes a storyline |
| GM | engine material woven in; no menus; it decides instead of asking; no moralizing; no machinery shown |

**Engine tests:**
- a fresh save run 3 to 6 months with only routine acts, scored against the sheet;
- **the absence test:** months with the protagonist doing nothing. Did the city change for its own reasons?
- several different starting saves, not one;
- group calibration across runs;
- for anything that never fires, why: nobody wanted it, or something blocked it;
- skip time before and after.

**GM test bench:** a few dozen player turns from the transcripts, replayed against the GM with the real connector,
scored against the sheet. Because it costs tokens, it runs on rulebook changes and before playtests. Mechanical
lines (menus, questions, out-of-character flags, exposed machinery) are checked by script; the rest is read by me.

## 9. Build order: a vertical slice first
1. The scoring sheet and the GM test bench.
2. **The slice:**
   - knowledge kept separate (fact, what each person knows, belief, rumour), with provenance, from the start;
   - level-3 concerns, including gradual build-up, and multi-dimension ties for the protagonist's circle;
   - the lean end-of-scene record, and canon by kind (fact, claim, rumour);
   - the news gate, what's building and the read budget;
   - the three engine answers (veto, character note, consequence note);
   - the rewritten storyteller rulebook;
   - a simple offscreen choice (habit plus the most pressing concern, non-optimal) and routines;
   - multiple group memberships per person;
   - **one person outside the circle whose plans touch the neighbourhood** (a local businessman or a club captain),
     acting through a real transmission path, to show that pressure moves down and results move up;
   - the old paths switched off for those people.
3. **The owner plays a fresh save:** an evening first, then a stretch of several game weeks. Fixes follow.
4. The full offscreen choice (others weighing in, decisions before breaks) and the contest.
5. Movers' plans through organisations and the people under them.
6. Promotion by resulting position, careful demotion, group rates across the city.

Each step ends in play, not only in passing tests. The data model for knowledge, ties, concerns and the scene record
is settled before the slice begins, because those are the expensive parts to change later.

## Left to the builder
- the storage shape for concerns, deeds, beliefs and memberships;
- the choice function and contest weights (from package figures, with no world words in `engine/`);
- how gradual pressures accumulate;
- the read-budget sizes;
- how the end-of-scene record is checked;
- the order of work inside each step.
