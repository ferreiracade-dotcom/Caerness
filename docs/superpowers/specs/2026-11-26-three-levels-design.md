# Three simulation resolutions, the GM as storyteller, and the link between them (design, 2026-11-26, revision 3.1)

Status: approved by the owner on 2026-11-26 (revision 3.1). Section 0 (revision 4) approved by the owner on 2026-11-27. Revision 5 (story first, below) is binding and
overrides every section. Build plan: `docs/superpowers/plans/2026-11-26-three-levels-build.md`.

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

## Revision 5: story first (binding, owner 2026-11-27; overrides every section below)

> **The objective is not to build the most sophisticated simulation of a fictional city. It is to create the best
> possible environment in which to play a believable character-led story.** (owner, 2026-11-27)

**The test for every feature, now and later:** does it make the story more believable, more reactive, more
interesting to play, or more coherent over time? If a simpler mechanism gets the same result, use the simpler one.
No feature is justified because it makes the simulation more complete.

**Priorities, in order:**
1. the playing experience;
2. a world that reacts;
3. persistence and continuity;
4. the machinery underneath, which serves 1 to 3 and never dictates them.

**What this changes in the sections below:**
- **The three levels are a practical tool,** not a project in themselves. Where a level rule adds work without
  changing what the player meets, it goes.
- **No psychology simulation.** The engine remembers facts about people (when they last saw him, what he did to
  them, what he promised, what he lied about, what they are short of) and applies one plain rule to them. It does
  not model inner states. Out:
  - pressure accumulators with per-person lognormal thresholds;
  - cooldowns, adaptation and resignation;
  - mood from recent deeds;
  - scored lists of rejected options;
  - separate build-up formulas for neglect, grievance and jealousy.
- **Offscreen choice is a short pick:** among the package actions that serve the concern, chosen by temperament and
  habit with a little noise. The engine stores the action and its reason only.
- **The engine's answers are facts:** what an act costs, whether it is legal, what obligation it breaks, whose man
  or ground it touches. Whether an act fits the man is the GM's judgement. The engine is not a narrative critic.
- **Reuse the city systems that exist** (`claims`, `temptations`, `life_matters`, `money_records`, `org_*`,
  `crime_response`, `civic_tick`, households, businesses) before adding a table or a module.
- **Recording stays light.** A scene closes with its participants. Anything more is recorded only when it matters
  later.
- **The GM has room to tell the story.** The engine says what is true and what has become likely; the GM chooses how
  it plays.
- **The player always has a life.** Kin, friends, romance and ordinary evenings stay present whatever his position,
  from mechanic to boss to councilman.
- **This is not a licence to delete working code.** Existing systems are switched off or kept, never removed without
  the owner's yes.

## Revision 5.1: play anyone (owner, 2026-11-27; binding with revision 5)

The owner's central principle: *"I want to be able to play anyone, in a living Saint Jude, and experience what
happens."* The owner's brief lists nine priorities, in order:
1. the freedom to play different characters from different starts;
2. a convincing personal life suited to the character;
3. natural conversations and meaningful interactions;
4. believable people with their own aims;
5. a world that goes on without him;
6. real consequences when he acts;
7. businesses, organisations and institutions that behave plausibly;
8. continuity, memory, history and time;
9. a storyteller who makes it engaging.

**What it adds:**
- **Every start is equally valid:** an ordinary person, a wealthy businessman, a politician (up to the mayor), a crime
  boss, a member of an established family. These are different ways into the same city, not advanced scenarios. A
  powerful start has not finished its story.
- **Starting in a seat someone holds (owner's ruling): he replaces the holder.** The opening gives him the seat
  before day 0, with a recorded reason. The previous holder is moved aside plausibly: retired, dead, or never
  present in this save. He inherits the office, outfit or company with its history, people, rivals and obligations,
  which are not replaced by his arrival.
- **The decisions of a seat he holds are his.** Where the outfit, business or civic code would choose for a seat
  holder, it asks him instead: it gives the GM a matter for him to decide. Routine running is done by his people
  (his second, his manager, his staff), and the GM is told what they did. The engine never decides for his seat in
  silence.
- **His importance follows his position.** A boss or a magnate is known where his position reaches. The brief shows
  him what he runs, and nominations come from his whole circle, within the budget.
- **No push to rise.** Staying ordinary, holding what he has, or living a quiet life are all valid. Neither the
  engine nor the GM steers him towards more money, power or conflict.
- **Judged by playing four starts:** a mechanic, a wealthy businessman, a politician and a crime boss, all in the
  same city.

## Revision 5.2: Gemini's review, judged by the story-first test (2026-11-27)

The owner asked that every point, Gemini's and the plan's own, pass the test of revision 5 before it is kept.
- **Kept, because the story fails without them:**
  - the weekly tick runs nominations from Deploy 1;
  - a nomination stores its details;
  - his deeds and his visible success (a booming shop, big spending, public votes) travel as news;
  - undo catches every write in a scene;
  - a refusal carries a notice that the GM tells the owner.
- **Kept, because they make play better at little cost:**
  - nights out return facts already true about the people there (a regular's worry, a rival crew's man in the room,
    an open tie), never drawn events;
  - seat business stays out of personal scenes unless it is urgent or one of his people is there;
  - the GM can bring a casual extra into a scene on the spot;
  - holders moved aside at the opening follow plain rules.
- **Cut, because nothing in play reads them or a simpler way exists:**
  - the `engine_answers` table and `rationale`: consequence facts come back in the tool's result;
  - `tie_contexts`, until steps 6 to 8;
  - routine changes as nominations: they are applied quietly as background life;
  - the separate mover path for outfits: the kept outfit code acts for outfits, and new code handles personal plans
    and non-outfit movers only;
  - the scripted GM bench: the fault checker runs on the owner's real playtest transcripts instead;
  - level 3 on the daily clock;
  - the world scorer as its own tool: its three measures join the start check;
  - drawn paying habits for customers: most people pay on time by the rulebook, and the money record remembers who
    did not.
- **Changed by the owner:** his death or a long sentence (Task 18d) is firm in Deploy 2.

**Revision 5.3 (Gemini's second reply, 2026-11-27).**
- **Late payers:** the existing business code has a `late` status on credit agreements, so the engine may cause them
  as well as the GM. The business probe measures the late rate first. If it skews late, its existing odds are tuned;
  no new model is added.
- **Outfit captains still notice him.** The outfit code owns outfit agendas (collections, rackets, squeezes, hits).
  Noticing and personal concerns run for every mover, captains included.
- **GM inventions becoming canon is checked by script:** `gm_check.py --db` compares a save with the session.
- **Cut, since nothing reads them:**
  - `record_changes.delta_json`;
  - `actor_concerns.waiting_on`, `waiting_since` and `ends_day`;
  - `causal_chains.touches_open_thread`;
  - `actors.systemic_power` (seats are read directly);
  - `standing.infer` (until step 8);
  - the `context` field on scene ties.

**Revision 5.4 (Gemini's third reply, 2026-11-27).**
- **Decisions stamped in a scene** do not wait forever in Deploy 1. When one passes its due day with nothing to
  carry it out, the weekly tick makes it a matter for him if it involves him, and otherwise lets it lapse.
- **Deploy 2's package settings start empty,** and each Deploy 2 task writes its own.
- **The strength of a worry is used:** it picks the three worries the brief shows about a person, and it is what
  makes a threat weigh more than good work when a mover notices him.
- **Cut, since nothing reads them:**
  - `gm_scenes.close_json`;
  - `actor_pressures.last_checked_day` and `actor_concerns.last_weighed_day`;
  - `actor_decisions.trigger_kind` and `outcome_text`;
  - `knowledge.topic`;
  - `causal_chains.scope`.
- **Saint Jude does not run `merchant.py`** (`merchant_houses` is off), so seat decisions hook only into
  `business.py`.

**Revision 5.5 (Gemini's fourth reply, 2026-11-27): four wiring gaps.**
- Decision and promise stamps carry a due date.
- The weekly tick weighs live concerns, so they become decisions.
- His shop taking work from rivals moves to Task 18c, where demand is built, and Task 15 runs due delayed effects.
- A worry's strength defaults to 0.5.

**Revision 5.6:** a stamp stores its `due_in_days`, and a stated decision keeps the stamp's target.

**Revision 5.7 (cross-sphere play, 2026-11-27).**
- Schemes the player invents are settled by the GM with the existing tools. An ordered act puts his men on record
  and him as the one who ordered it, with the truth held only by those in on it.
- An organisation he founds counts like any other.
- The brief says how a place sees him (`standing_here`).
- His public deeds reach him through his own paper, radio or television.
- In an outfit, his crew carries the insider version of outfit events.
- Business ripples are the GM's to play from his business state.

**Revision 5.8 (an ambitious city, 2026-11-27).**
- The city's big business owners are movers, not only notables.
- An opportunity opens a worry as strain does: money to spare, or a struggling rival in the same trade.
- Movers can expand, buy out a struggling business, or propose an alliance. A buy-out changes owners the same way
  his own purchase through `trade` already does.
- The canon paper, radio and television outlets are real businesses with owners.
- The visible steps of someone's plan travel as news; the intent stays with those in on it.
- Deploy 2 proves at least one ambition pursued outside the outfits.

**Revision 5.9 (Gemini's reply to 5.8, 2026-11-27).**
- How news reached someone is recorded as a generic kind (saw it, told, talk, media, mail) plus the package's name
  for the channel. Television, magazines or a parish bulletin are package data, and the engine names no channel.
- One function writes every paper, radio and television item.
- An opportunity is acted on once, when it appears. A new one needs a new chance; there is no waiting period.
- Away from him, an owner accepts a buy-out the way a price is already weighed against value, and an alliance by tie
  and temperament.

## 0. The split between engine and GM (revision 4, approved 2026-11-27; overrides the sections below where they differ)

Source: the owner's intent brief (`docs/review/saint-jude-intent-brief.md`) and his answers on 2026-11-27.

**The rule.**
- **The engine** holds state, memory, numbers, time, causes and the bounds of plausibility. It is the authority on
  what is true.
- **The GM** writes prose and scenes, and invents people, events and hooks inside what is true. What it invents and
  the engine accepts becomes canon for that save.
- **The test for which side owns a thing:** if the GM forgot it by next session, would the story break or turn
  implausible? If so, it is the engine's. If it is a judgement about what is interesting, it is the GM's, and the
  engine records it.
- **No tables where a fact plus the GM's judgement is enough.** Example: the engine holds that dockworkers drink at a
  bar; the GM decides the night is rough. There are no per-venue fight odds.

**Nominate, realize, ratify.** For developments near the protagonist:
1. **The engine nominates** what has become likely, with the cause. Example: "Anthony has likely started seeing
   someone (24, out most weekends, his crowd's courting rate)."
2. **The GM realizes it.** It decides who, how and when, and gives a timeframe for playing it. The engine may list a
   few real, free people who fit; the GM may pick one or invent someone new.
3. **The engine ratifies.** It checks the GM's version for contradictions only, then records it and holds the GM's
   plan.
4. **Reminders and fallback.** Within the timeframe, the engine reminds the GM. If the timeframe passes, the engine
   applies the development itself, in a plain form, and the GM can colour it later.

The owner's four answers:
- **Scope.** Anything touching his circle, or that he could plausibly come across, is nominated to the GM.
  Far-off city events (a killing across town, a business failing) the engine applies directly, and they reach him
  as news through the gate.
- **The GM's latitude.** Who, how and when (within the timeframe), never whether. A plausible event happens: the
  owner's "no veto" rule. Declining needs a reason in the record, such as something established in play that makes
  it implausible.
- **Who the people are.** The GM picks a real person or invents one, and the engine checks and records them.
- **Forgetting.** The GM sets the timeframe; the engine reminds within it, then applies.

**What changes in the design below.**
- **Section 3 (pressure to act):** an offscreen decision by someone near him becomes a nomination, not an engine act.
  Far-off people's decisions still fire as engine acts.
- **The protection lock becomes consistency.**
  - The engine keeps everyone's life going at realistic rates. Near him, its draws go out as nominations.
  - Nothing the engine applies may contradict what scenes established.
  - Guards on his agency stay: the engine never pleads, votes, plots or chooses for the protagonist.
- **Outings and other in-scene drama.** The engine supplies who is really there and the place's character. The GM
  invents what happens. The happenings dice, menus, cutaways and texture pushes go.
- **Tool results are facts and numbers, not prose.** That saves tokens and keeps engine wording out of the GM's
  voice.
- **Unknown stays unknown.** Where the record is silent, the engine says so, and the GM invents (`findings`
  included). The engine records the invention unless it contradicts something.
- **Recording an invention is cheap.** A stamp, or closing the scene from its stamps. The bench checks that a person
  invented in a scene exists afterwards.

**Engine work the brief needs, kept engine-side:**
- **Noticing.** Who learned what about him, through whom and when. Each mover has a "waiting on" record, so follow-up
  is the default and silence is a stored fact with a cause.
- **Business state.** Each customer's paying habit (drawn once from a realistic spread), what is owed, demand and its
  causes, and capacity against workload. The GM invents the haggling and what breaks.
- **Crime and civic events reach the paper and radio.** This is in Deploy 1.
- **Offices plan.** Political seats count as movers, and politics gets a pressure of its own. That covers a political
  start.
- **Skips stop only for something serious.** This is tested.

**Revision 4.1 (owner, 2026-11-27): the personal level and the wider world, both ways.**
1. **What he does travels outward.**
   - The gate carries news to anyone, not only to him.
   - His deeds go from the witnesses through their ties, with delay and some distortion.
   - They build his standing with people and groups (`claims` impressions) and reach movers, which is what noticing
     runs on.
2. **His conduct builds pressure.**
   - Neglect, grievance, broken promises and jealousy build in the people near him from what the record shows he
     did.
   - Past their line they become nominations, and the GM plays how it comes to a head.
   - A promise broken from a closed scene is a recorded fact with a consequence.
3. **Lies get found out.** When someone who holds the truth meets someone holding his lie, the engine nominates the
   discovery.
4. **Rising has machinery.**
   - Competitors are an exposure link, so his growth is pressure on rivals.
   - His businesses and crew are his channels.
   - A nomination budget: the GM gets the ones that matter, and the engine applies the small ones plainly.
5. **The brief has a "you" part:** his injuries, police interest, debts, grudges he knows of, and open promises.
   Consequences linger because the GM is shown them until they resolve.
6. **People the GM invents go on living.** Ratifying one seeds a routine, a level, a purse and a life, like anyone
   in the save.
7. **The protagonist's death or long sentence.**
   - If both survival and death are plausible, he survives.
   - If he dies, the city carries on, and the successor is chosen with the GM afterwards.

**Revision 4.2 (from ChatGPT's review, 2026-11-27).**
1. **Relevance, not proximity.** Sharing a room does not make someone part of his story. A person is near him
   (nominations, conduct) when they:
   - have dealt with him;
   - are involved in an event that affects him;
   - have a tie or a recurring connection with him;
   - or are kin or household.

   Strangers in the same bar stay strangers.
2. **Attention goes to what can become story.** A nomination's weight comes from what it touches: a tie to him,
   an obligation, his money, business or safety. Routine changes (a new drinking place, a car bought) are recorded
   and applied quietly.
3. **Noticing depends on what was learned and who learned it.**
   - The kind of fact sets how interested the mover is:
     - good work means mild interest;
     - unexpected money means an opportunity;
     - work for a rival means a threat.
   - The follow-up can be any of several moves: look into him quietly, ask someone who knows him, send someone round,
     offer legitimate work, invite him somewhere, test him, or leave him alone on purpose because he is more useful
     that way.
4. **Business produces decisions.** Being over capacity or losing work comes to him as a matter needing his
   decision, with its cause discoverable in the world (a rival undercutting him, a job talked about badly), not
   only as a number.
5. **The world has atmosphere.** The paper and radio carry a few public items a day whether or not they concern him,
   as colour. These are marked as atmosphere and limited in number.
6. **The record stays light.** At `close_scene` only the participants are needed. Ties are recorded only when
   something meaningful changed. An ordinary evening needs nothing more than a close.
7. **The GM finds opportunities in what exists.** For example, a rival in trouble can become an offer, a man looking
   for work, or a desperate competitor. The GM looks for these without inventing their causes. This is a rulebook
   principle.
8. **Validation beyond one mover and one start.**
   - The life test also runs a political start.
   - The scorer counts chains that cross from one mover's act into another's pressure.
   - The scoring sheet checks that his personal life stays alive whatever his position.

   Deploy 1 proves that the GM and engine work together. Deploy 2 proves that the world moves. Steps 6 to 8 make the
   three resolutions complete. None of them is mistaken for the finished design.

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
  - materializing unnamed people (`_materialize_latent_person`) and `tiers.py`;
  - the knowledge and rumour tables;
  - the connector's correction, undo, money and claim tools.
- **Replaced, not added to:**
  - `life_matters` stops running for level-3 people and for protected people, and stays for the rest of levels 1
    and 2 (replaced by revision 6.3 of the build plan: life draws run for everyone, and one touching someone near
    him becomes a nomination);
  - the four news feeds in `connector/timeflow.py` become the one gate, built from `hearsay.py`'s path logic and
    `information.py`'s reliability;
  - old paths are switched off first and deleted once the slice is proven.
  - Added 2026-11-26 from the review of the nearby code (`docs/review/three-levels-adjacent-verdicts.md`):
    - the old loop's personal choices, the belief mirror and `resolution_controller`'s ladder are switched off
      in Saint Jude;
    - every side door into the protagonist's news goes through the gate;
    - the protection lock covers every background roll on a named person, not only `life_matters`;
    - the brief shows the GM only what is nearing the protagonist;
    - `temptations` and `settle_circle` stay.
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

## 11. Amendments (revision 3.1, from Gemini's second review; these override the sections above where they differ)
1. **Resolution is stored on each person.** A `resolution` value takes one of three forms:
   - `materialized_minor` (a full row with no systemic role: most of the roughly 5,600 today);
   - `notable` (true level 2);
   - `active` (level 3).

   `life_matters` runs on unprotected `materialized_minor` and `notable` people. Organisation and systemic logic
   targets `notable` and `active`. Counting against the aggregate is simple subtraction (full rows are about 0.5% of
   1.1 million); the real double-counting risk is causal, and section 5 already handles that.
2. **The protection lock works both ways and expires.**
   - It blocks `life_matters` events where a protected person is either the actor *or* the target.
   - A lock from a scene alone is released after a quiet window (about 30 to 60 game days) with no concern and no
     obligation, so the bartender who poured one beer isn't frozen for ever.
3. **Record standing uses three states, not five.**
   - `confirmed` carries a true or false value: "checked the safe and it is empty" is not ignorance.
   - `inferred` covers background filled in on promotion.
   - A missing row means `unknown`.
4. **Three stages from pressure to act, not five:**
   - **pressure**: a numeric accumulator per area of life, invisible until it crosses that person's varied threshold,
     or until it settles into adaptation;
   - **concern**: a named motive with an origin and strength, which shapes choices and appears in scene briefs. A
     concern whose latest weighing came out as "do nothing" is simply waiting;
   - **decision**: a committed plan with an action, a target, a reason and a trigger or due date. It can be dropped
     if circumstances change, and becomes an **act** when it fires.
5. **Exposure channels are derived from existing links**, such as employer, organisation, residence, workplace and
   routine places, as indexed queries rather than a parallel subscription table. A small explicit `dependencies`
   table holds only links with no existing structure: debts, suppliers, protection.
6. **After an absence, news stays with whoever heard it.** During a skip, only what reached the protagonist himself
   goes into his news: the newspaper, the radio, mail, what he saw. What his family, friends or crew learned while he
   was away stays in *their* knowledge, and he hears it when he talks to them. This resolves the clash with the
   absence-return test.
7. **The gate has two tests: path and relevance.** Attention is not a third test. It only ranks lower-priority items
   inside the read budget, with a floor that is never dropped: direct danger, active obligations, close kin.
8. **Routines are worked out when needed, not run every day.** Each level-3 person has a baseline schedule plus
   active exceptions (illness, travel, special events). The question "where is he now?" is resolved only when a scene
   opens, a lookup runs, or a shock hits a place-based channel. The "Daily" row in section 6 becomes "on demand".
9. **The scene close works from a ledger of stamps.** Stamps ride on calls the GM already makes, plus a cheap
   `note(kind="stamp")` for speech-only beats (a lie, a walkout, a promise). At `close_scene`, the engine echoes the
   scene's stamps back, and the GM sends four short fields:
   1. **participants**, with simple `joined_late` or `left_early` markers relative to stamped beats;
   2. **stamp amendments**, which confirm or patch the ledger instead of restating it;
   3. **knowledge exceptions**: lies, secrets, who missed what;
   4. **tie nudges and open threads**: each with a one-line cause, plus promises or decisions not already stamped.

   This replaces the twelve-part table in section 4. That table now describes what the engine holds, not what the GM
   writes.
10. **Sessions can end mid-scene.** `resume` returns to an open scene without closing it. `close_scene(mode="from_stamps")`
    commits whatever was stamped if a scene is abandoned. A new chat never has to make up a scene record to unlock
    `advance`.
11. **GM turning events have their own path.**
    - **One call:** they go through `author(kind="turning_event")` with a scope (local, ward or city), the affected
      channels and a summary. They never go only into prose or a plain fact.
    - **Checks on entry:** the engine checks against territory, ownership and recent shocks on those channels. A
      contradiction is vetoed; a strained rhythm gets a consequence note.
    - **The engine owns what follows:** once committed, it publishes the shock to the channels, and all downstream
      effects are the engine's. The GM supplies the spark.
    - **Two measures on the scoring sheet:** how often GM turning events happen compared with engine-originated ones;
      and **protagonist-convenience bias**, meaning how often a GM turning event happens to resolve or force an
      active thread right in front of him.
12. **A reason can come with the change.** Record-changing calls (`act`, `money`, `author`) take an optional
    `rationale`, so the GM states up front why someone is acting against type, without a second call.
13. **Undo and correction cascade.** Every record derived during a scene or a turning event carries a
    `source_scene_id` or `causal_chain_id`: beliefs, deeds, obligations, shocks, scheduled effects. Undo and
    correction then revert everything that came from it, with no ghost rumours or orphaned delayed effects. This
    goes into the data model in step 2.
14. **Build-order changes.**
    - Step 1 writes the scoring sheet and gathers test prompts. The test-bench *harness* is coded once step 2 has
      fixed the tool and scene-record contracts.
    - The bench runs on **6 to 10 small fixed test saves**, each 4 to 6 turns, built from situations in the
      transcripts: lies, walkouts, quiet evenings, moralizing traps, ambiguous details. It doesn't replay old
      transcripts end to end, because those depend on old state.
    - Slice 2b starts gradual build-up with **one or two simple pressures** taken from existing values, such as cash
      strain and restlessness in a job. The rest comes with step 6.
15. **The first artifact of step 2** is a one-page specification of the schema and tool signatures. It covers:
    - `resolution`;
    - the pressure, concern and decision tables;
    - the rollback keys;
    - standing;
    - the stamp payload;
    - `close_scene`;
    - `author(kind="turning_event")`;
    - the `rationale` parameter.

## Left to the builder
- the table shapes, within the data model settled in step 2;
- the generic action set's first contents;
- contest weights and gradual-pressure figures from package data;
- read-budget sizes;
- the order of work inside each step.
