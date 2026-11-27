# Reply to Gemini's third review (revision 5.4)

Thank you. Every claim checked out, and all of it is applied, with one change of approach.

- **Stamped decisions in Deploy 1:** kept as `actor_decisions`. The weekly tick from Task 14a clears one once it is
  past due: it becomes a `waiting_on_you` matter if it involves him, and otherwise it is `lapsed`. Task 17b fires them
  properly in Deploy 2. This keeps a stamped "he'll call round Friday" visible in `about_to` until it is due.
- **Deploy 2 package keys:** `null` in Task 3. Each Deploy 2 task fills its own.
- **Task 10a files:** `engine/scenes.py`, `engine/information.py`, `connector/money.py` and `engine/civic_tick.py` are
  added.
- **`merchant.py`:** you were right. Saint Jude's `world.json` has `"merchant_houses": false`, so Task 14c hooks only
  `business.py`.
- **Cut:**
  - `gm_scenes.close_json`;
  - `actor_pressures.last_checked_day` and `actor_concerns.last_weighed_day`;
  - `actor_decisions.trigger_kind` and `outcome_text`;
  - `knowledge.topic`;
  - `causal_chains.scope` (also removed from `turning_event`).
- **Kept and wired instead of cut: `actor_concerns.strength`.**
  - It orders the three `on_their_mind` items in the brief.
  - It comes from the `noticing` weight per kind of fact (a threat above an opportunity, above mild interest).
  - `offscreen.weigh` takes the strongest live concern first.

  It changes what the GM sees and what a mover does, so it passes the story-first test.

The revised plan follows.


---

# For review: the "three levels" build plan for a text role-playing game engine (revision 5.4)

## What you are reviewing

This package holds four documents, in this order:
1. **The owner's intent brief:** what the game must do. Judge everything against it.
2. **The design** (revision 3.1, plus revisions 5 to 5.4 at its top and revisions 4 to 4.2 in its section 0, which override the rest).
3. **The schema and tool contract.**
4. **The build plan:** Tasks 1 to 19, in two deployments.

This cover gives the context, and shows how the build fits into the code that is not changing.

## The project in brief

**Narrative Engine** is the owner's personal text role-playing game. It has two parts:
- **The engine:** Python and SQLite, about 87,000 lines in 194 modules under `engine/`. It simulates a whole city
  and its people.
- **The game master (GM):** Claude, connected through an MCP connector (`connector/`). Its tools are:
  - `resume`, `scene`, `lookup`, `lore`, `act`;
  - `advance` (time skips);
  - `note`, `author` (records what the GM invents);
  - `money`, `correct` (undo and corrections).

**The world in play is Saint Jude.** It is a fictional American port city in 1975: Italian families, social clubs,
an organised-crime underworld, local politics, law and ordinary trades. The world is a package of data files under
`worlds/saintjude/`, and engine code holds no world-specific words. The player always plays a new character, never
a canon figure, and can start in any sphere: business, the underworld, politics, or a mix. Dominic Basile, a
24-year-old mechanic, is one playthrough used for examples. He is not the target.

**The division of labour (design section 0).**
- **The engine** holds state, memory, numbers, time, causes and plausibility, and vetoes contradictions.
- **The GM** writes prose and scenes, and invents people, events and hooks. What it invents and the engine accepts
  becomes canon for that save.
- **Near the protagonist, the engine nominates, the GM realizes, and the engine ratifies.**
  - The engine says what has become likely and why.
  - The GM decides who, how and when, and gives a timeframe.
  - The engine checks for contradictions and records it.
  - The engine reminds the GM within the timeframe, and applies the development plainly if it passes.
- **Far from him, the engine applies developments directly,** and they reach him only as news through plausible
  channels.

**Why this build exists.** In two playtests the city was rich but the protagonist's life was thin, with nothing
between the two:
- the mob made a deal, sent one car, then vanished for months;
- almost every customer paid late;
- nights out produced nothing until the player asked, and then the first woman was perfect;
- the GM moralised.

The causes, as we now understand them:
- the engine rolled dice for drama that is the GM's job;
- memory and plausibility work was left to the GM, which forgets;
- the project measured the city simulation, not the story at the protagonist's level.

## How the build fits into the code that is not changing

### Kept as it is (the city layer the build sits on)

| Area | Modules | How the build uses it |
|---|---|---|
| The clock | `engine/simulation.py` `build_default_process_registry` (a due-queue of about 40 process keys) | Adds one weekly key, `levels` (Task 16). Outward spread runs on the existing `information` slot (Task 10a). |
| Outfits and the underworld | `org_lifecycle`, `org_membership`, `org_succession`, `org_coup`, `org_happenings`, `org_money`, `org_choices`, `outfit_choices` (seats, rackets, hits, discipline, succession, coups, money) | Stays the level-2 institutional layer and keeps choosing for outfits. Gains agency guards for the protagonist (Tasks 2b, 14). Movers' own plans come through concerns and decisions (Tasks 16 to 18b). |
| Law and prison | `crime_response`, `prison`, `law` | Kept. High-publicity crime reports become paper and radio news (Task 10b). A plea is never made for the protagonist (Task 14). |
| Politics | `civic_tick`, `politics.json` | Kept. Its news to the player goes through the gate (Task 10b). Offices count as movers (Task 3), with an `office_threat` pressure (Task 16). |
| Money and prices | `money_records`, `ledger`, `price_book` | All money moves through them. Undo reverses money with a reversing record, never a deletion (Task 6). |
| Population and family | `household_life`, `opening_family`, `life_matters`, `civilian_life`, `lived_past`, `opening_ties`, `new_character` | Kept for life at realistic rates. A draw that touches someone near him becomes a nomination; far from him it applies as today (Task 14). `new_character` already builds a real circle for any kind of start. |
| Reputation | `claims` (audiences, impressions, deterrence) | Kept as the per-person and per-group reputation. It is fed by outward spread (Task 10a). |
| Wants and purchases | `temptations` | Kept. The protagonist's chances reach him through the gate (Task 10b). |
| Health and bodies | `health`, the body work (B1.1, B1.2) | Kept. Illness onset can become a nomination near him. His death is handled in Task 18d. |
| Connector tools | `connector/server.py` and its modules | Extended, not replaced: scenes and `close_scene`, stamps, `rationale`, nominations, and the brief (Tasks 4, 5, 8, 11, 14). |

### Switched off in Saint Jude (Task 2b and later), kept for the shelved Caerness world

**Before the build (Task 2b):**
- the old personal-decision loop's built-in choices (`decision_runtime._builtin_candidates`, `decisions.build_actor_context`);
- the write-only belief mirror (`belief.mirror_legacy_knowledge`).

**Inside build tasks:**
- `resolution_controller`'s re-scoring ladder, which `levels` replaces (Task 3);
- `information.py`'s event-to-rumour broadcast, which outward spread replaces (Task 10b);
- in-scene drama generators (Task 11): the happenings dice in `outings`, menus, cutaways, and `texture`'s news push.

Each is a package switch, never a check on the world's name. Deletion waits until the slice is proven, and needs the
owner's yes.

### New modules (detail in the contract)

**Phase B:**
- `levels`: who is simulated at which of the three resolutions;
- `rollback`: the change log and undo;
- `scenes`: the scene ledger and `close_scene`;
- `routines`: where people are.

**Phase C:**
- `answers`: the engine's answers to the GM's proposals;
- `standing`: canon by kind and record standing;
- `news_gate`: one path for news, both inward to him and outward from his deeds.

**Phase D:**
- `nominations` and `conduct`: the nominate, realize and ratify loop, and pressures from his conduct;
- `channels`: shocks along exposure links (debts, suppliers, protection, customers, competitors);
- `pressure` and `offscreen`: from pressure to concern to decision;
- `levels_tick`: the weekly process key.

**Schema:** one migration, from version 133 to 134.

## What we would like from you

1. **Does the plan deliver the brief's seven "game must do" points and its decisions?** For each, name the task that
   covers it, and say whether it is covered, partial or missing.
2. **What would still make play at the protagonist's level feel thin or wrong,** especially where his life meets the
   wider city in either direction?
3. **Is anything on the engine side that should be the GM's,** or the other way round, by the test in design
   section 0?
4. **Do the tasks fit the unchanged code as described?** Look for broken seams: a kept module that a new rule would
   contradict, or two paths left doing one job.
5. **Ordering and risk.** Is anything in Deploy 1 that depends on Deploy 2? Is any task too big or too vague for an
   implementer who sees only that task?

Please keep it short: a list of findings, each with the task, the problem and the fix you would make.

---



---

# Saint Jude: owner intent brief for the personal-level plan

For the code agent. Judge the personal-level plan against this, not against the plan's own goals. Dominic Basile is one illustrative playthrough, not the target. The target is any start in any sphere (business, underworld, politics, or a mix). Do not build Dominic-specific logic.

## The division of labour (do not blur it)

The engine exists because the GM (a Claude agent) was bad at persistent memory, arithmetic, and keeping things plausible instead of giving the player what he asked for. The GM is good at prose, storytelling and inventing hooks.

- **Engine:** state, memory, numbers, time, causes, and the plausibility bounds. It is the authority on what is true.
- **GM:** prose, scenes, voice, and inventing events, people and hooks. It is meant to act as a real game master and take initiative. It must work inside what the engine says is true, and what it invents should be recorded so it persists.

Where this brief says "the game should do X", the agent decides which side does it. Keep the engine's share to what needs memory, arithmetic or enforcement. Do not build tables where a fact plus the GM's judgement is enough. Example: a rough bar is rough because dockworkers drink there. The engine holds who frequents a place and the district's character, and the GM judges what follows. No per-venue fight odds.

## Owner decisions on how the two sides work together

1. **GM inventions become canon.** When the GM invents a person, place, event or fact and the engine accepts it as plausible, it is recorded and is as real as anything the game started with. Canon is per save only and does not carry to other saves. This means the engine needs a way to accept or reject a GM invention and to store what it accepts.
2. **Engine wins, but the owner is told.** If the GM and the engine disagree, the engine's version stands by default. The GM must tell the owner what the disagreement is, and the owner can rule for either side. A ruling for the GM's version is recorded as a correction to the engine.
3. **Every start has a real personal circle.** Whatever the start (family, employees, business associates, close staff, a household), the people around the protagonist are real people in the engine with their own histories and lives, not scenery generated when the player looks.
4. **No veto on plausible events.** If something is plausible and realistic it can happen, however inconvenient, unwelcome or hectic for the protagonist. Stories cannot always go well. The owner chooses how Dominic responds, but does not choose whether a plausible event occurs.

## Owner decisions on how the world behaves (any story)

1. **Real stakes.** The protagonist can be badly hurt, jailed or killed by plausible events (hence the prison work). Tie-break: if both survival and death are plausible, he survives. If death is the only plausible outcome, he dies. After a death, the successor is chosen with the GM afterwards.
2. **Fog and rumour.** The player knows only what someone in his position would learn through channels. Rumours can be wrong or distorted. The true state lives in the engine.
3. **Opponents are active, not only reactive.** Rivals, the mob and the police plan, adapt to his rise and pursue their own aims. Envy, underestimation and human mistakes are part of it.
4. **Reputation is per person and per group,** built from what each actually saw or heard, and it changes how they treat him.
5. **Life goes on.** People, including his parents, brothers and circle, age, marry, have children, fall ill, move away and die at realistic rates.
6. **His influence scales.** If he rises, the city visibly changes around him. While he is small, it carries on without him.
7. **Consequences linger.** Injuries, police attention, debts, grudges and a bad name persist until something actually resolves them. Nothing quietly resets.

## The test every event must pass

Plausible prior history. Invention is welcome. An event with no cause in state (relationships, wants, money, reputation, place, period) is not. The reverse also holds: an absence needs a cause. A mob that notices a useful man and then ignores him for months is as implausible as one that invents a grudge.

## The problem in one paragraph

The city simulation is rich and the protagonist's own life is thin, with nothing in between to carry city events to him. In the first playthrough the mob struck a deal, sent one car, and vanished for months while his business grew. Almost every customer paid late. Nights out with four young men produced nothing until the owner asked about women, and then the first woman was perfect. Nothing was heard of the mob doing anything else. The GM moralised.

## What the finished game must do

1. **The world acts without the player.** Families, gangs, officials and businesses pursue their own aims with reasons: gaining, losing, feuding, killing, making examples, being squeezed. A player could stay on the Hill and never touch the mob, and the mob would still be moving. If he enters later he enters something already in motion. News reaches him only through channels that would plausibly carry it, at plausible delay, or not at all.
2. **Powerful people notice and want things, for reasons.** How the mob learns of a person is itself causal (who saw, who talked). They may know he does good work without knowing his income. Follow-up is the default. Silence needs a cause. Backstory must hold together: a father untouched for thirty years needs a reason, settled at setup.
3. **Business is an ordinary mix.** Customers vary in payment, price, haggling, referrals. Things break. Booms follow good work and reputation, slumps follow neglect or rivals. Capacity matters: a boom in a one-bay shop should push him toward real decisions (premises, hiring, turning work away, marketing). When nothing arrives, there is a discoverable reason.
4. **People around him have their own lives.** Brothers, friends, a girlfriend and parents move without the player. Opening state is plausible: four fit young tradesmen are not all single with nothing going on. People can refuse, leave, lie or compete, with persistent consequences, when plausible.
5. **Ordinary life produces things unprompted.** A night out contains people and incidents without the player asking: most forgettable, some one-offs, some recurring, few marriage material, trouble depending on who he is and where he goes. The first woman, customer or fight is not special by default.
6. **Time skips.** He keeps living in his own competence and routine during a skip, and it is applied. A skip is interrupted for something serious or needing his decision, and not otherwise. Quiet is allowed to be quiet.
7. **No moralising.** Period behaviour is shown plainly (under-age and heavy drinking, speeding, small crimes, bigotry as the characters' own, death as part of the underworld). The protagonist is not steered to the moral high ground and the people around him are not all honest. Characters are gray. This is a GM-side instruction and belongs in the connector or skill.

## How to check

Keep it light. For each of the seven points give: which plan task covers it, whether it is covered, partial or missing, and the test or measured run that shows it. Do not write long prose. Then answer four questions:

- What carries a city event to the protagonist, and what decides it does not?
- What makes the mob follow up with someone it has noticed?
- What stops the first woman, customer or fight from being special?
- Does anything here assume Dominic or a business start, and what happens in a political start?

Flag anything in the plan that serves a different goal (speed, the city sim) and whether it conflicts. Re-read Gemini's review with this brief and say which of its findings bear on these goals.


---

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
    and 2;
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


---

# Three levels: schema and tool contract (step 2, first artifact)

This fixes the names later tasks build on. It implements `2026-11-26-three-levels-design.md`, revision 3.1. Where a
table already exists and fits, it is extended rather than duplicated. The old `pressures` and `decisions` tables belong
to the old decision loop, whose personal choices Task 2b switches off in Saint Jude (the outfit choices still write `decisions`); they are left alone otherwise; the new ones have distinct names. The
addiction tables `dependency_profiles` and `dependency_exposures` are unrelated, so the design's "dependencies" table
is called `exposure_links`.

## Schema 134 (engine/schema.sql + migration in engine/db.py)

**Who is simulated how**
- `actors.sim_resolution TEXT NOT NULL DEFAULT 'materialized_minor' CHECK IN ('materialized_minor','notable','active')`.
  Separate from `entity_resolution.resolution_level`, which stays as the old cadence system (design section 8 keeps
  `tiers.py`). Set by `engine/levels.py` (rules below).
- `actors.closeness_to_me REAL`, NULL by default, refreshed by `levels.refresh`. Power is read from seats directly
  (revision 5.3).

**Scenes and stamps**
- `gm_scenes(id, opened_day, closed_day NULL, location_id NULL, status CHECK IN ('open','closed','abandoned'),
  opened_call_id, closed_call_id NULL)`. At most one row with `status='open'` (partial unique index).
- `scene_participants(scene_id, actor_id, joined_after_beat INT NULL, left_after_beat INT NULL,
  attention CHECK IN ('involved','attentive','overheard','distracted') DEFAULT 'involved', PRIMARY KEY(scene_id, actor_id))`.
- `scene_stamps(id, scene_id, beat INT, kind CHECK IN ('claim','lie','promise','money','goods','injury','enter','leave',
  'walkout','decision','other'), actor_id NULL, target_actor_id NULL, text, holds_true INT NULL CHECK IN (0,1),
  ref_table NULL, ref_id NULL, call_id, status CHECK IN ('stamped','confirmed','amended','struck') DEFAULT 'stamped')`.
  `beat` counts up from 1 within a scene.

**Causes and rollback keys**
- `causal_chains(id, day, origin_kind CHECK IN ('scene','turning_event','decision','world_process','player_act'),
  origin_id INT, summary)`.
- Add `source_scene_id INT NULL` and `causal_chain_id INT NULL` to: `knowledge`, `relationship_history`, `obligations`,
  and every new table below that can be derived. 
- `record_changes(id, day, source_scene_id NULL, causal_chain_id NULL, table_name, row_id, op CHECK IN ('insert',
  'update'), before_json NULL)`. This is one generic log of every write made while a scene or
  chain is current. It covers:
  - status changes to rows that already existed (an obligation fulfilled, a concern resolved);
  - overwrites of `record_standing`;

  Every new module writes through `rollback.log_insert`, `rollback.log_update`. The log also traces chains.

  Rules:
  - **Discrete values** (`record_standing`, statuses) are logged as `update` with `before_json`. Undo restores the
    old value only if no later `record_changes` row touches the same `(table_name, row_id)`. Otherwise it leaves the
    row and names it in `left`.
  - **Inserts** are deleted on undo.
  - **Outside a context** (no `rollback.current`), the log functions do nothing, so the weekly ticks don't fill it.
  - **Ties** (`relationships`) are never logged here. Undo inverts them from
    `relationship_history` only, so nothing is reverted twice.
  - **Keys:** `rollback.py` keeps an explicit table-to-key map, for tables like `actor_routines` that are keyed on
    `actor_id`. A table missing from the map is refused, never guessed.
- Money is never deleted on undo. `undo_scene` walks `scene_stamps(ref_table, ref_id)` and posts a reversing money
  record for each money stamp, so the ledger stays honest. An authored row (`authored_entities`, connector schema,
  gains `reverted_day NULL`) is marked reverted when nothing after the scene refers to it. Otherwise it stays, and
  it is named in the result.

**Ties by context**
- `tie_contexts` is not built here (revision 5.2; steps 6 to 8).

**Record standing** (design 3 and amendment 3)
- `record_standing(id, subject_kind CHECK IN ('actor','location','business','outfit','household'), subject_id,
  attribute TEXT, standing CHECK IN ('confirmed','inferred'), holds INT NULL CHECK IN (0,1), value_text NULL, day,
  source_scene_id NULL, causal_chain_id NULL, UNIQUE(subject_kind, subject_id, attribute))`.
  No row means unknown. `confirmed` with `holds=0` means "checked, and it is not so".

**Knowledge** (extend `knowledge`)
- `basis CHECK IN ('saw','told','read','heard_rumour','inferred','felt') NULL`, `carrier_actor_id NULL`,
  `path_kind CHECK IN ('self','told','paper','radio','mail','work_talk','parish','street') NULL`,
  `holds_true INT NULL` (is the belief actually correct), plus the two rollback keys. Rows without `path_kind` are legacy and
  never reach the news gate.

**Pressure, concern, decision** (amendment 4)
- `actor_pressures(id, actor_id, domain TEXT, since_day, UNIQUE(actor_id, domain))` (revision 5:
  when a condition began to hold, nothing more). `domain` is a package key.
- `actor_concerns(id, actor_id, kind CHECK IN ('owes','owed','wants','resents','fears_for','courts','plans','needs'),
  object_kind NULL CHECK IN ('actor','business','location','outfit','money','work'), object_id NULL,
  origin_kind CHECK IN ('scene','exposure','other_act','chance','buildup','noticed','conduct'), origin_text, strength REAL 0..1,
  status CHECK IN ('live','waiting','resolved','dropped') DEFAULT 'live', opened_day,
  source_scene_id NULL, causal_chain_id NULL)`.
- `actor_decisions(id, actor_id, concern_id NULL, action TEXT, target_kind NULL, target_id NULL, reason TEXT,
  due_day NULL, status CHECK IN ('pending','fired',
  'dropped','failed','lapsed') DEFAULT 'pending', decided_day, fired_day NULL,
  offer_to_actor_id NULL, told_day NULL, expires_day NULL, on_expiry CHECK IN ('lapse','escalate') NULL,
  source_scene_id NULL, causal_chain_id NULL)`. `action` is a key from the package's generic action set, or the
  reserved `stated` for a decision the GM stamped in a scene (the stamp text is the reason). A decision with
  `offer_to_actor_id` is an offer or demand that waits on that person (design 3, "what waits").
- `offscreen_evaluations(id, day, actor_id, concern_id NULL, why, chosen_action, reason)`: every weighing,
  including those that ended in `do_nothing`, so a world that never does something can be explained.

**News waiting with a carrier** (amendment 6)
- `pending_news(id, carrier_actor_id, recipient_actor_id, knowledge_id, urgent INT 0/1, created_day,
  delivered_scene_id NULL, delivered_day NULL, causal_chain_id NULL)`. The carrier's own knowledge row stays where it
  is. The recipient gets a knowledge row only when the news is delivered, either in a scene with the carrier or by a
  call or visit (urgent items in town). Once delivered, it is never offered again.
  - **A scene delivers at `close_scene`, not when a brief is shown.** The brief is read-only. It lists items where
    `delivered_scene_id` is unset, or equals the open scene's id, so `resume` and repeated briefs show the same
    thing.
  - **The delivered row keeps its chain.** It copies `pending_news.causal_chain_id` and is logged through
    `rollback`, so undoing the chain also removes news that was already delivered.
  - **Carriers can be one step removed.** A carrier is the affected person if he is tied to the recipient. Otherwise
    it is a member of the affected person's household, or close kin of his, who is tied to the recipient (Carla, for
    her father's shop). That carrier learns it from home (`basis` told).

**Channels** (amendment 5)
- No subscription table: `engine/channels.py` derives who is attached to a channel from existing links (employer,
  organisation seat, residence, workplace, routine places).
- `exposure_links(id, actor_id, link_kind CHECK IN ('debt','supplier','protection','customer','competitor'), other_kind, other_id,
  since_day, ended_day NULL, source_scene_id NULL, causal_chain_id NULL)`: only the links with no existing structure.
- `channel_shocks(id, day, channel_kind CHECK IN ('business','location','outfit','sector'), channel_id, shock_kind TEXT,
  magnitude REAL, summary, causal_chain_id NOT NULL)`. `shock_kind` is a package key.
- `scheduled_effects(id, due_day, effect_kind TEXT, payload_json, status CHECK IN ('pending','done','cancelled')
  DEFAULT 'pending', causal_chain_id NOT NULL)`: delayed effects on the due-queue.

**Routines** (amendment 8)
- `actor_routines(actor_id PK, home_location_id NULL, work_location_id NULL, haunts_json DEFAULT '[]',
  schedule_key TEXT)`: `schedule_key` names a package schedule (which part of which day is work, home or haunt).
- `routine_exceptions(id, actor_id, kind CHECK IN ('ill','travel','event','prison','away'), from_day, to_day NULL,
  location_id NULL, source_scene_id NULL, causal_chain_id NULL)`.
- Routines are seeded by `routines.seed` when the opening is built, and for anyone newly notable or active on
  `levels.refresh`. Home comes from the household, work from the employer or the business he owns, and the schedule
  from his position.

**Engine answers**
- Revision 5.2: no table. Consequence facts come back in the tool result as `answers`. A refusal carries
  `owner_notice`.

**Nominations (revision 4)**
- `nominations(id, day, kind, actor_ids_json, cause, causal_chain_id NULL, status CHECK IN
  ('new','planned','realized','declined','applied'), plan_text NULL, by_day NULL, reminded_day NULL,
  decline_reason NULL, realized_scene_id NULL, applied_day NULL, payload_json)` (`payload_json`: revision 5.2).
- Revision 4.1:
  - `knowledge` gains `spread_from_day NULL` (outward spread, Task 10a).
  - Nomination kinds include `neglect`, `wronged`, `broken_promise`, `jealousy` and `lie_found_out` (revision 5).
  - `nominations` gains `weight REAL` and `applied_small INTEGER DEFAULT 0` (the budget).
- Revision 5.1: nomination kind `seat_decision` (a decision of a seat he holds, shown in `waiting_on_you`);
  `create_protagonist`'s account gains `displaced` (`actor_id`, `reason`) for a start in a held seat.

## Package data (worlds/saintjude/levels.json; validated on load, carries `"version": 1`)
`mover_roles` (which seats and offices make someone a mover), `close_rule` (tie thresholds for being close),
`lock_quiet_days` (45), `familiarity_step` and `familiarity_decay` (company in a scene), `tie_steps` (what
`small`, `medium` and `large` mean for each tie dimension), `tie_concern_line` (a tie step that opens a concern),
`acute_shock_line` (a felt shock large enough to open a concern straight away, for notable as well as active people),
`urgent_kinds` (news that a close tie phones or calls round about, in town), `pressures` (domains, the existing values each reads, and its line in weeks), `actions` (the generic action set: key, which concerns it serves, what it needs, habit weight, what it
does when fired), `shocks` (shock kinds: what each changes, such as money, takings or demand, and when it opens a concern), `schedules`,
`news_paths` (everyday channels and what they carry), `answers` (the cash share above which money is weighty),
`nominations` (default and longest timeframe in days, reminder lead, weekly budget, weight per kind),
`conduct` (quiet days by closeness, and how long a wrong waits before it surfaces), `news_paths.spread`
(delay per hop, drop-off, chance of a detail changing), `long_sentence_days`, `delegation` (revision 5.1: which decisions of a seat he holds are his), `visible_spend` (revision 5.2), `noticing` (which facts interest which
mover roles). `mover_roles` includes political offices.

## Tool contract (connector/server.py)
- Revision 4: `note(kind="plan", nomination, by_day, text)` sets the GM's timeframe, or with `decline=reason`
  declines; `author` and `close_scene` take `realizes=<nomination id>`. `brief.full` and the skip result list
  `nominations` (new, to remind, overdue, and the small ones applied). `brief.full` has a `you` part. Tool results give facts and numbers in fields, not engine prose.
- **People are a name or an id everywhere** (`close_scene`, stamps, threads). Names are matched against the open
  scene's people first, then the protagonist's known people. An ambiguous name, such as a first name two people share,
  is refused with the candidates. "me" is the protagonist.
- `note(kind="scene", text, present, location=None)`: opens a scene if none is open. `location` is a place name or
  id; without it, it is the protagonist's stored place. A new scene with a location moves him there, through the
  same check as `act travel`. At the open scene's place, the note updates presence. At a different place while a
  scene is open, it is refused with one line: close the current scene first (`close_scene`, or
  `mode="from_stamps"`). Returns `scene_id` and the full brief (connector/brief.py).
- `note(kind="stamp", text, stamp={"kind", "by", "to", "true"})`: a speech-only beat, using a new `stamp` parameter
  so that `field` and `present` keep their meanings. `true: false` marks a lie or a mistake. Arrivals and departures
  mid-scene are stamps of kind `enter` and `leave`. Returns `{"stamp": {beat, kind, text}}`.
- During an open scene, each `act`, `money` and `note` result carries `changed`: only what that call changed. There
  is no cursor for the GM to track.
- `act`, `money`, `author` stamp themselves while a scene is open, add `stamp` to their result. Results carry `answers: [{kind, text}]` when the engine has a note.
- **New tool** `close_scene(call_id, mode="commit", participants=None, amendments=None, exceptions=None, ties=None,
  threads=None)`. `mode`: `review` returns the ledger and commits nothing; `commit` applies the four fields;
  `from_stamps` commits the ledger as stamped. Shapes:
  - `participants`: `[{"who": "Carla", "joined_after_beat": 3, "left_after_beat": 5, "attention": "overheard"}]`
    (only the exceptions). Anyone in the scene's presence list is otherwise involved for the whole scene. Stamped
    `enter` and `leave` beats already set the times.
  - `amendments`: `[{"beat": 4, "status": "struck"}]` or `[{"beat": 4, "text": "...", "true": false}]`. Beats are
    the numbers the ledger and each stamp result show.
  - `exceptions`: `[{"beat": 2, "missed_by": ["Frank"]}, {"beat": 2, "disbelieved_by": ["Ma"]},
    {"secret": "text", "known_to": ["me", "Frank"]}]`.
  - `ties`: `[{"from": "Ma", "to": "me", "change": {"trust": "-small"}, "cause": "one line"}]`.
    Steps are `small`, `medium` or `large`, with a sign, mapped to numbers by `tie_steps`. The GM never sees or sends
    a raw score.
  - `threads`: `[{"kind": "owed", "by": "Frank", "to": "me", "text": "$40 for the parts", "due_in_days": 4}]` or
    `[{"kind": "meeting", "with": ["Tullio"], "text": "the club, Tuesday", "due_in_days": 5}]`. The kinds are
    `owed`, `meeting` and `promise`.
  - A scene with no stamps and no fields closes cleanly as an ordinary one.
  - **All or nothing:** if any reference fails (an ambiguous or unknown name, a beat that doesn't exist, a
    participant who wasn't there), nothing is committed. The scene stays open, and the result lists each failure
    with its candidates, so the GM fixes the call and sends it again.
  - **Thread shapes:** `owed` and `promise` take `by` and `to`, and become one obligation of `by` toward `to`.
    `meeting` takes `with: [...]` and becomes one obligation row per person listed.
  - **Disbelief:** `disbelieved_by` still gets a knowledge row ("heard X say it"), at confidence 0.1. Knowing that a
    claim was made matters even when it isn't believed.
  - **Secrets:** `secret` defaults to `holds_true=1` and reaches only `known_to`, whoever else was present.
- `advance` refuses while a scene is open, naming `close_scene(mode="from_stamps")`. `resume` returns an open scene
  as it stands and never closes it.
- `author(kind="turning_event", details={channels: [{kind, id or name}], shock, summary, magnitude})`.
- `correct(op="undo_scene", details={"scene": id})` and `correct(op="undo_chain", details={"chain": id})`, on the
  player's explicit yes like every `correct` op.

## Engine module surface
- `engine/levels.py`: `refresh(conn, day) -> dict`, `resolution_of(conn, actor_id) -> str`.
- `engine/scenes.py`: `open_scene`, `open_scene_id`, `stamp`, `ledger`, `close(conn, call_id, mode, **fields) -> dict`.
- `engine/rollback.py`: `current(conn, scene_id=None, chain_id=None)` (context manager setting what new writes are
  keyed to), `log_insert(conn, table, row_id)`, `log_update(conn, table, row_id, before: dict)`,
    `undo_scene(conn, scene_id) -> dict`, `undo_chain(conn, chain_id) -> dict`.
- `engine/routines.py` also has `seed(conn, actor_ids=None) -> int`.
- `engine/news_gate.py` also has `hold(conn, carrier, recipient, knowledge_id, urgent, chain_id) -> int` and
  `deliver(conn, pending_ids, scene_id=None) -> int`.
- `engine/answers.py`: `judge(conn, tool, actor_id, change: dict) -> list[dict]`.
- `engine/standing.py`: `confirm`, `standing_of` (`infer` waits for step 8).
- `engine/news_gate.py`: `reaches(conn, me, start_day, end_day) -> list[dict]`, `held_for(conn, me, carrier) -> list[dict]`.
- `engine/conduct.py`: `weekly(conn, day) -> list[int]`, `lies(conn, day) -> list[int]` (revision 4.1).
- `engine/news_gate.py` also has `spread(conn, day) -> int` (revision 4.1).
- `engine/nominations.py`: `near`, `nominate`, `plan`, `decline`, `realize`, `due`, `apply_overdue` (replaces
  `engine/protection.py`, which is not built).
- `engine/routines.py`: `where(conn, actor_id, day, part) -> int | None`.
- `engine/channels.py`: `attached(conn, channel_kind, channel_id) -> list[tuple[int, str]]`, `publish(conn, shock_id) -> list[dict]`.
- `engine/pressure.py`: `build(conn, day, actor_ids) -> list[int]` (ids of new concerns).
- `engine/offscreen.py`: `weigh(conn, actor_id, day, why) -> int | None`, `fire_due(conn, day) -> list[int]`.
- `engine/levels_tick.py`: process key `levels`, weekly, registered in `build_default_process_registry` (Task 14a).


---

# Three levels: build plan (steps 1 to 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> In this repository, tasks run in Sonnet linked sessions, one writer per file set, and the lead reviews every diff.

**Goal:** Build steps 1 to 5 of the three-levels design (revised 2026-11-26 after Gemini's review of this plan): the scoring sheet and GM test bench, the data model, slice 2a
(the GM–engine loop) and slice 2b (a minimal living world), ending in the owner's playtest of a fresh Saint Jude save.

**Architecture:** New engine modules sit beside the city layers and read their existing tables. The connector gains
scene ledgers, one news gate, engine answers and turning events. `life_matters` keeps running only for unprotected
people below level 3. One weekly `levels` process carries pressure build-up, offscreen choice, decisions falling due
and delayed effects. Old news feeds go behind a flag first and are deleted only after the playtest.

**Tech Stack:** Python 3.13, SQLite, the MCP connector (`connector/server.py`), package JSON under
`worlds/saintjude/`, script-style tests run by `tools/run_suite.py`.

**Spec:** `docs/superpowers/specs/2026-11-26-three-levels-design.md` (revision 3.1; section 11 overrides earlier
sections) and its contract `docs/superpowers/specs/2026-11-26-three-levels-contract.md`. Every table, column, tool
argument and module function named below is defined in the contract; read it before your task.

## Global Constraints
- **Story first (revision 5, binding):** every task must make the story more believable, more reactive, more
  interesting to play or more coherent over time, by the simplest mechanism that does it. Where a step below builds
  more machinery than that needs, the simpler reading wins; ask the lead if unsure.
- No hard caps, ladders or ceilings: a threshold marks a real change of state, never a points ladder.
- No world words in `engine/`: every Saint Jude figure, name or list lives in `worlds/saintjude/*.json`.
- The engine vetoes contradictions only and never hands the GM a menu or a closed list.
- The protagonist lives under the same rules as everyone else; the engine never chooses for him.
- Never write `data/*.db` (only an approved `data/saintjude.db` rebuild). Leave `data/caerness.pre-schema110.db` and
  `game/campaign_01/backups/` alone.
- B1's held fight work is saved whole in `docs/superpowers/plans/b1-held-fight.patch` (done 2026-11-26, owner's yes).
  Don't apply it or edit it: it is the input to the contest work in step 6.
- Implementers never push, stash, reset or switch branches; commit only your own files with `git add <paths>`; run
  `git restore game/campaign_01/model_requests/` after tests.
- Tests: `tools/run_suite.py --quick --only <names>` while working and `--quick` before reporting. Never more than two
  long runs at once and never beside the quick suite. Runs are no longer than one simulated year. Tests remove their
  temp files.
- Each tool result stays small: the GM's context per turn is a cost. A new key in a result needs a reason.
- Never show the machinery: concern lists, scores and engine words go to the GM only as plain-language briefs.

## Review Focus
1. A chat ends mid-scene, a new chat calls `resume`, then `advance`: the refusal must name
   `close_scene(mode="from_stamps")` and that call must unlock it (test in Task 5).
2. A name in `present` or `participants` who isn't actually there: listed as not here, learns nothing, gets no tie
   change (test in Task 4).
3. Undo of scene 1 after scene 2 built on it: only scene 1's rows revert, and scene 2's knowledge and ties stay
   (test in Task 6).
4. A live save at schema 128 to 133 (Dominic's VM save) migrating to 134: resolutions assigned, `life_matters` still
   runs for unprotected people, nothing crashes on rows without the new columns (test in Task 3).
5. A skip while the protagonist is away (prison, travel): nothing arrives by a told path; it surfaces when the carrier
   is next in a scene with him (test in Task 10a).

## Left to the plan for steps 6 to 8 (not built here)
- several group memberships, per-domain group rates and competing risks, and calibration across runs;
- contests, built from B1's held fight work;
- the full offscreen choice (others weighing in, decisions before breaks);
- tie resting points, hysteresis and ties by context (`tie_contexts` is not built here: revision 5.2);
- movers' plans through organisations, with imperfect execution (only one mover acts here, directly);
- promotion by demonstrated significance, careful demotion, and obligations through life changes;
- several different starting saves;
- revision 5.1: a look back over his history and the city's big events (a lookup over the scene ledger and
  `causal_chains`).

---

## Delivery and cost (owner-approved 2026-11-26; overrides the task steps where they differ)

**Two deployments.**
- **Deploy 1, after Task 14d:** Tasks 1 to 13, then Tasks 14a to 14d, then a Task 19-style deploy and playtest. Task 14 is
  now nominations, consistency and agency guards (design section 0). Deploy 1 is the GM loop, the news gate with
  every door, and life near him going on through nominations.
- **Deploy 2:** Tasks 15 to 18d (the living world, noticing, business state, his death or long sentence), then
  Task 19.
- **Design section 0 (revision 4, approved 2026-11-27) governs every task.** Engine: state, memory, numbers, causes,
  vetoes. GM: prose and invention. Near him, the engine nominates, the GM realizes and the engine ratifies. Where a
  task below says the engine does something to a person near the protagonist, it nominates instead.

**Deferred to Deploy 2, to save cost:**
- `undo_chain` from Task 6 moves into Task 15, where chains first appear. Task 6 builds `undo_scene` only.

**Tests: targeted per task, the full suite at checkpoints.**
- Wherever a step says "run `--quick`", run instead the task's own test plus the existing tests of the modules it
  modifies (`--only a_test,b_test`). The commit names which ones were run.
- The full `--quick` suite runs only at the checkpoints: after Task 6, at Task 13, and before each deployment.

**GM checks (revision 5.2).** There is no scripted bench. `tools/gm_check.py` (Task 7) runs on the transcripts of
the owner's real playtests and on any session the lead plays, and the lead reads them against the Task 1 checklist.

**Side by side.**
- Tasks that share no files run as parallel sessions: Task 2b with Task 1; Task 7 with Tasks 4 and 5 (Task 7 is now small); Task 16 with
  Task 15.
- Never two writers on the same files.

**Fix rounds go to the session that did the task,** not to a fresh one.

**Revision 5, story first (owner, 2026-11-27).** The design's revision 5 block governs every task. What it changed
here:
- Task 1: a short checklist, not a scoring framework.
- Task 7: the bench is a smoke check for known GM faults; the owner's playtests weigh more.
- Task 8: the engine's answers are consequence facts only, with no character notes.
- Task 14: one rule over remembered facts replaces the four conduct build-ups.
- Task 15: it reuses the existing tables.
- Tasks 16 to 17c: a short pick replaces the scored choice. Pressure is a plain package line, with no lognormal
  thresholds, cooldowns, adaptation or mood.
- Task 18a: three measures.
- Task 18d: firm in Deploy 2 (revision 5.2).

**Revision 5.1, play anyone (owner, 2026-11-27).**
- Task 11: the brief shows what he runs.
- Task 12: a rulebook line against pushing him to rise.
- Task 14: seat decisions are his.
- New Task 14b (now 14d, revision 5.2), in Deploy 1: starts in a held seat (he replaces the holder), and a four-start check.
- Task 18b: the political start becomes part of 14b's check, which runs again before Deploy 2.

**Revision 5.2 (Gemini's review, each point judged by the story-first test).**
- **Task 14 is split into four sessions,** in this order:
  - **14a:** `nominations.py` and `levels_tick.py`, and the hooks in the life modules.
  - **14b:** `conduct.py`, with broken promises and lies found out.
  - **14c:** agency guards and seat decisions, with the second or manager for each seat kind.
  - **14d:** starts at any scale (formerly 14b).
- **Task 17c is built after Task 17b,** since it uses `pressure.py`, `offscreen.py` and the follow-ups.
- **Order of hooks:**
  - Task 10a hooks `news_gate.deliver` into `scenes.close`.
  - Task 15 builds `undo_chain` and teaches turning events in the rulebook.
  - Task 17b registers `offscreen.fire_due` in the tick.
- **Cut:** the scripted bench, `engine_answers` and `rationale`, `tie_contexts`, the daily clock change in
  `tiers.py`, routine changes as nominations, the second mover path for outfits, the separate scorer tool, and drawn
  paying habits.
- **Task 18d is firm in Deploy 2.**

**Revision 5.3 (Gemini's second reply).**
- Every file goes to a named part of Task 14 (see its header).
- Task 15b is now Task 17c, placed after Task 17b.
- Fields that a later task fills are defined empty by the earlier one.
- Six unread schema fields, `standing.infer` and the ties `context` field are cut.
- The business probe measures late payment first.
- `gm_check.py` gains `--db`.

**Revision 5.4 (Gemini's third reply).**
- Stamped decisions past due become his matter or lapse (Task 14a).
- Deploy 2's settings start as `null` (Task 3).
- Task 10a's file list is complete.
- `merchant.py` is out of Task 14c.
- `strength` is wired into the brief and into noticing.
- Seven unread fields are cut.

**What each deployment proves (revision 4.2).** Deploy 1 proves that the GM and engine work together. Deploy 2
proves that the world moves around him. Steps 6 to 8 make the three resolutions complete. Neither deployment
is reported as the finished design.

## Phase A: build step 1

### Task 1: Scoring sheet and playtest situations

**Files:**
- Create: `docs/playtests/2026-11-25-dominic-2.txt` (copy of
  `C:\Users\NozzE\.claude\uploads\63f5ee28-600c-4604-899a-a5ee025d8f85\aad99367-Saint_Jude_roleplay_with_Dominic.txt`;
  owner lines start with the player's turns)
- Create: `docs/superpowers/specs/2026-11-26-scoring-sheet.md`
- Create: `docs/playtests/situations.md`

**Interfaces:**
- Revision 5.2: the situations are a reading checklist for playtests, not bench fixtures.
- Produces: the sheet's check ids (`C1`..`C3` for the engine, matching Task 18a's three measures; `G1`..`G5` and
  `G10` for the GM) used by Task 7's checker and Task 18a's scorer; the situation ids `S1`..`S8` used by Task 7's fixtures.

- [ ] **Step 1: Write the scoring sheet** as a short checklist (revision 5), one line per check: id, what it
  catches, script or reading. Engine checks: C1 events near him have a stored cause; C2 event rates per kind look
  like ordinary life (neither dead nor frantic); C3 package actions that never fired, with the reason. Script-checkable GM lines are G1 menus (a numbered or lettered list of options to the
  player), G2 questions to the player that aren't about his own choice, G3 out-of-character flags, G4 exposed
  machinery (`concern`, `pressure`, `the engine`, `score`, a tool name in prose), G5 moralizing phrases from the
  transcript's faults. Add G10 (read, revision 4.2): his personal life (kin, friends, romance, ordinary evenings)
  stays present whatever his position.
- [ ] **Step 2: Write 8 situations from the transcript**, each with: transcript line range, the state it needs (who is
  present, what each knows and owes), 4 to 6 player turns quoted or condensed, what a good GM does, the sheet checks it
  exercises. Cover: S1 a lie to his mother about money, S2 a walkout from a dinner, S3 a quiet evening that should stay
  ordinary, S4 a moralizing trap (a fence offers stolen parts), S5 an ambiguous detail the record doesn't hold (does
  the supplier have a wife?), S6 a one-off customer (the Gerald Orsini case: no advance news), S7 returning after two
  weeks away, S8 a stranger at a bar who should stay a stranger.
- [ ] **Step 3: Commit**
```bash
git add docs/playtests/2026-11-25-dominic-2.txt docs/superpowers/specs/2026-11-26-scoring-sheet.md docs/playtests/situations.md
git commit -m "Three levels step 1: scoring sheet and eight bench situations from the second Dominic playtest"
```
- [ ] **Step 4: Lead checkpoint.** The lead reads the sheet and the situations before Phase B starts.

---

## Phase B: build step 2 (data model)

### Task 2: Contract sign-off and clearing B1's held edits (lead)
- [ ] The contract (`docs/superpowers/specs/2026-11-26-three-levels-contract.md`) is written with this plan. The lead
  confirms it against the design before Task 3. Any change goes into the contract first, then into the tasks below.
- [x] B1's held fight edits are saved as `docs/superpowers/plans/b1-held-fight.patch` (checked to apply cleanly to
  a clean copy, commit `f7f5a81`), and those files are restored.

### Task 2b: Switch off the competing paths (before any new table)

Approved by the owner on 2026-11-26 from `docs/review/three-levels-adjacent-verdicts.md`. These are small, local
switches, so the build is measured against a world where only the outfit choices still run.

**Files:**
- Modify: `engine/decision_runtime.py` (`_builtin_candidates` adds the built-in personal providers only when the
  package's `systems.personal_choices` is true; registered providers such as `org`, and "hold position", always run)
- Modify: `engine/decisions.py` (`decide_actor` skips `build_actor_context` when only registered providers run)
- Modify: `engine/information.py` (`_upsert_knowledge` calls `belief.mirror_legacy_knowledge` only when
  `systems.belief_mirror` is true)
- Modify: `engine/world_package.py` (`SYSTEM_KEYS` gains `personal_choices`, `belief_mirror`, `entity_resolution`
  and `rumour_broadcast`, used here and in Tasks 3 and 10b; `worlds/caerness/world.json` sets all four true, Saint
  Jude's leaves them out)
- Modify: `engine/org_happenings.py` (the protagonist draws only the happening kinds the package marks
  `"befalls": true`; every other kind is something a man does, and the engine never does it for him)
- Modify: `worlds/saintjude/outfits.json` (mark `busted` and `incident` as `"befalls": true`)
- Modify: `docs/superpowers/specs/2026-11-26-three-levels-contract.md` and the design's section 8 (already done with
  this plan change)
- Test: `tests/competing_paths_off_test.py`

- [ ] **Step 1: Write the failing test:**
```python
# Saint Jude fixture, 120 days
assert decisions_by_type(conn).get("consolidate", 0) == 0 and decisions_by_type(conn).get("initiate_interaction", 0) == 0
assert decisions_by_type(conn).get("org_action", 0) > 0                     # the outfits still choose
assert count(conn, "actor_beliefs") == 0 and count(conn, "knowledge") > 0
# the protagonist seated as an associate for 52 weeks
seat_protagonist_as_associate(conn); run_weeks(conn, 52)
assert happening_kinds_of(conn, me) <= {"busted", "incident"}
# Caerness keeps both switches on (its tests are unchanged)
assert caerness_package().systems["personal_choices"] and caerness_package().systems["belief_mirror"]
```
- [ ] **Step 2: Run it.** Expected: FAIL (209 consolidate decisions in the reference run).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run it**, then `--quick`, and `--only s1_rise_equivalence_test,org_happenings_test,outfit_choices_test`.
  Outfit actions, money and incidents stay inside the S1 ranges; if a range moves, say why in the commit.
- [ ] **Step 5: Commit** the files above.
- [ ] Optional tidying, same task, own commit: a `caerness_economy` switch for the Caerness-only processes
  (agriculture, logistics, merchant, craft, growth, war, ecology, education, patronage, seeking, attention,
  psychology, world). They run on empty tables in Saint Jude, so nothing should change but the run time.
- Not done here: `org_lifecycle._dormant` still puts a former member back on the full review. With the personal
  choices off he can only hold position, so it is harmless; Task 3's `levels` owns his cadence after that.

### Task 3: Schema 134 and resolution levels

**Files:**
- Modify: `engine/schema.sql` (new tables and columns from the contract; append a `-- schema 134` block)
- Modify: `engine/db.py` (`SCHEMA_VERSION = 134`; migration adds columns with `ALTER TABLE ... ADD COLUMN` guarded by
  a column check, as the existing migrations do)
- Create: `engine/levels.py`
- Create: `engine/rollback.py` (only `current`, the two `log_*` functions and the table-to-key map here; Task 6 adds undo)
- Create: `worlds/saintjude/levels.json` (every key in the contract's package section. Deploy 1's keys get first
  figures. Deploy 2's keys (`shocks`, `pressures`, `actions`, `noticing`, `long_sentence_days`) are `null`, which the
  validator accepts, and each Deploy 2 task fills its own. Revision 5.4.)
- Modify: `engine/world_package.py` (load and validate `levels.json`: report missing keys, unknown role references and
  a wrong `version`, telling a missing setting apart from one deliberately left out with `null`)
- Modify: `engine/simulation.py` (`SYSTEM_PROCESSES`: the `resolution` process runs only when the package's
  `systems.entity_resolution` is true; Saint Jude leaves it out)
- Modify: `engine/resolution_controller.py` (`_materialize_latent_person` and `_sync_sim_tier`: when
  `entity_resolution` is off, a new person gets `sim_resolution='materialized_minor'` and a `simulation_profiles`
  row on the quiet routine, never one that feeds the old decision loop)
- Revision 5.2: `engine/tiers.py` is not changed, unless a kept Saint Jude module is found to need level 3 on the
  daily clock. In that case, name the module to the lead before changing it.
- Test: `tests/levels_schema_test.py`

**Interfaces:**
- `levels` owns tiers, cadence and promotion in Saint Jude. `resolution_controller` used to re-score all 5,879 people
  there on its own scale; it no longer runs there. Materializing unnamed people (marriages into the unnamed
  population, a grown child nobody knew about) stays.
- Produces: `levels.refresh(conn, day) -> {"active": int, "notable": int, "changed": int}` and
  `levels.resolution_of(conn, actor_id) -> str`.
- Rules for `refresh`: `active` = the protagonist; anyone whose `closeness_to_me` meets `close_rule` (computed from his
  relationship row with the protagonist: affection, trust, familiarity, and kin or household); anyone in a
  `mover_roles` seat (read from the seat itself; revision 5.3). `notable` = holders of any organisation seat or office and owners
  of an enterprise with staff, not already active. `mover_roles` lists political offices as well as outfit
  seats, so a political start has rivals who plan. Everyone else with a row stays `materialized_minor`. `refresh`
  never lowers anyone below `notable` while he has a live obligation or a live concern (step 8 does careful demotion).

- [ ] **Step 1: Write the failing test** `tests/levels_schema_test.py` with checks:
```python
# fresh opening (tests.sj_fixture.build_saintjude) plus an authored protagonist "Dominic Basile", mechanic, 24
assert schema_version(conn) == 134
assert {"gm_scenes", "scene_stamps", "scene_participants", "causal_chains", "record_standing", "actor_pressures",
        "actor_concerns", "actor_decisions", "exposure_links", "channel_shocks", "scheduled_effects",
        "actor_routines", "routine_exceptions", "nominations", "record_changes",
        "pending_news", "offscreen_evaluations"} <= tables(conn)
with rollback.current(conn, scene_id=1):
    rid = insert_concern(conn); rollback.log_insert(conn, "actor_concerns", rid)
assert logged(conn, "actor_concerns", rid)["source_scene_id"] == 1
assert {"basis", "path_kind", "carrier_actor_id", "holds_true", "source_scene_id", "causal_chain_id"} <= cols(conn, "knowledge")
out = levels.refresh(conn, day)
assert levels.resolution_of(conn, me) == "active"
assert all(levels.resolution_of(conn, k) == "active" for k in kin_of(conn, me))
print(out, active_by_reason(conn))                     # the lead sets the band from this first run
assert 10 <= out["active"] <= 120 and out["notable"] > 0
# a captain-level seat holder from mover_roles is active even with no tie to him
assert levels.resolution_of(conn, a_mover) == "active"
# Review Focus 4, real legacy dirt: LEVELS_LEGACY_DB names a copy of a real pre-134 campaign save (the lead copies
# the VM backup to runs/, never data/). The check is skipped, and says so, when the variable is unset.
if os.environ.get("LEVELS_LEGACY_DB"):
    old = migrate_copy(os.environ["LEVELS_LEGACY_DB"])
    assert schema_version(old) == 134 and levels.resolution_of(old, protagonist_of(old)) == "active"
    assert legacy_knowledge_rows_have_null_path(old)
# package validation: a levels.json missing "pressures" reports it; "pressures": null is accepted as left out
assert "resolution" not in run_process_keys(conn)                            # the old ladder is off in Saint Jude
spouse = materialize_unnamed_spouse(conn, single_adult)
assert levels.resolution_of(conn, spouse) == "materialized_minor" and quiet_routine_of(conn, spouse) == 1
```
- [ ] **Step 2: Run it.** `python tools/run_suite.py --out runs/t3 --quick --only levels_schema_test`. Expected: FAIL
  (schema version 133).
- [ ] **Step 3: Implement** the schema block, the migration, `levels.py`, `levels.json` and its validation.
  `refresh` runs once at the end of the opening build and on protagonist creation.
- [ ] **Step 4: Run it**, then `--quick`. Expected: the new test passes; no test that passed before now fails.
- [ ] **Step 5: Commit** `engine/schema.sql engine/db.py engine/levels.py engine/rollback.py engine/world_package.py
  worlds/saintjude/levels.json tests/levels_schema_test.py`.

### Task 3b: Routines on demand

**Files:**
- Create: `engine/routines.py`
- Modify: `engine/levels.py` (`refresh` calls `routines.seed` for anyone newly notable or active)
- Modify: `tools/build_opening.py` (seed routines at the end of the opening build)
- Modify: `worlds/saintjude/levels.json` (`schedules`)
- Test: `tests/routines_test.py`

**Interfaces:**
- Produces:
  - `seed(conn, actor_ids=None) -> int`: home from the household, work from the employer or the business he owns,
    schedule from his position;
  - `where(conn, actor_id, day, part) -> int | None`, where `part` is one of `morning`, `day`, `evening` or `night`:
    an exception first, then the schedule. `where` writes nothing. Exceptions include what other systems already
    record: active `custody` of kind `held`, an open `inmate_stays` row, a `sentences` row being served, and
    `travel_plans` that are active or stalled (the check `presence._active_travel` makes today).

- [ ] **Step 1: Write the failing test:**
```python
assert routines.seed(conn) > 0 and seeded_share_of_notable_and_active(conn) > 0.9
assert routines.where(conn, frank, weekday, "day") == garage_location
add_exception(conn, frank, "ill", day, day + 5); assert routines.where(conn, frank, day + 1, "day") == frank_home
assert routines.where(conn, unseeded_minor, day, "day") is None              # unknown, not somewhere
hold_in_custody(conn, frank, day); assert routines.where(conn, frank, day, "day") == custody_location(conn, frank)
start_travel(conn, frank, day + 10); assert routines.where(conn, frank, day + 11, "day") != garage_location
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 4: Scene ledger in the engine

**Files:**
- Create: `engine/scenes.py`
- Modify: `engine/relationships.py` (accept `source_scene_id`/`causal_chain_id` in `record_relationship_effect` and
  write them to `relationship_history`)
- Test: `tests/scene_ledger_test.py`

**Interfaces:**
- Consumes:
  - `company.in_earshot`, `company.join` and `veto.settlement_of` (as `connector/store.py _scene_note` uses them);
  - `routines.where` (Task 3b) to judge who can plausibly be present;
  - `rollback.current` and `rollback.log_*` (Task 3) for every write.
- People are given by name or id and resolved as the contract says: the scene's people first, then the
  protagonist's known people. An ambiguous name is refused with the candidates. Tie changes arrive as steps
  (`-small` and so on) and are mapped through `tie_steps`. Thread kinds are `owed`, `meeting` and `promise`, with
  their direction.
- `open_scene(conn, call_id, present, text, location=None)`: compared with the open scene's `location_id`. A different place is refused, naming `close_scene`.
- Produces:
  - `open_scene(conn, call_id, present: list, text: str) -> dict` (returns `{"scene_id", "present", "not_here"}`;
    reuses the open scene if there is one);
  - `open_scene_id(conn) -> int | None`;
  - `stamp(conn, call_id, kind, text, *, actor_id=None, target_actor_id=None, holds_true=None, ref_table=None, ref_id=None) -> dict`
    (returns `{"beat", "kind", "text"}`; refuses when no scene is open);
  - `ledger(conn, scene_id) -> list[dict]`;
  - `close(conn, call_id, mode, participants=None, amendments=None, exceptions=None, ties=None, threads=None) -> dict`
    returning `{"closed": scene_id, "learned": int, "ties": [..], "threads": [..], "refused": [..]}`.
- What `close` writes:
  - **knowledge:** for each stamp of kind claim, lie, promise, money, goods, injury, walkout or decision, a knowledge
    row for every participant present at that beat with attention `involved` or `attentive` (`overheard` at
    confidence 0.5; `distracted` none), unless an exception removes them. Each row gets `basis` saw or told,
    `path_kind` self, `holds_true` from the stamp, and `source_scene_id`.
  - **ties:** every participant pair that includes the protagonist gets a familiarity step through
    `record_relationship_effect`, smaller for each extra scene the pair shared in the last 14 days (the step shrinks to
    half each time; the figure comes from `levels.json`). `ties` entries apply as given, with `cause` as the summary.
  - **threads:** shaped as the contract says.
    - `owed` and `promise` become one obligation of `by` toward `to`: `actor_id` = `by`, `counterparty_actor_id` = `to`.
    - `meeting` becomes one obligation row per person in `with`.
    - Each row has `due_day` = today + `due_in_days`, `source_kind` 'scene' and `source_scene_id`.
  - **exceptions:** `missed_by` gets no row for that beat. `disbelieved_by` gets a row at confidence 0.1 (he heard it
    said). `secret` defaults to `holds_true=1` and gives rows only to `known_to`.
  - **news:** Task 10a adds delivery here (`news_gate.deliver`). This task leaves the hook point only.
  - **deeds (revision 5.2):** each knowledge row a closed scene writes for a witnessed act of his gets
    `spread_from_day` = the close day, so Task 10a's `spread` can carry it outward.
  - **stamps that start something:** a `promise` stamp also becomes an obligation. A `decision` stamp with an
    `actor_id` becomes a pending `actor_decisions` row (the reason is the stamp text). A tie entry that moves
    resentment or affection by at least the `levels.json` concern line opens a `resents` or `wants` concern for the
    `from` person, with `origin_kind='scene'` and the cause as `origin_text`.
  - **casual extras (revision 5.2):** a name in `present` or `participants` that matches nobody in the save becomes a
    new `materialized_minor` person at the scene's place, with no separate `author` call. A name that matches
    someone who is elsewhere is still `not_here` (Review Focus 2).
  - **refusals are all or nothing:** if any reference fails (an ambiguous or unknown name, a beat that doesn't exist,
    a participant who wasn't there), `close` commits nothing and leaves the scene open. It returns `refused`, with
    the candidates for each failure.
  - **close mode:** `from_stamps` does the same with no fields; `review` writes nothing and returns the ledger.

- [ ] **Step 1: Write the failing test** `tests/scene_ledger_test.py`:
```python
sid = scenes.open_scene(conn, "c1", [mother, frank], "kitchen, evening")["scene_id"]
scenes.stamp(conn, "c2", "lie", "Dominic says he has $500 saved", actor_id=me, holds_true=0)
scenes.stamp(conn, "c3", "promise", "Frank will repay by Friday", actor_id=frank, target_actor_id=me)
out = scenes.close(conn, "c4", "commit", participants=[{"who": "Frank", "joined_after_beat": 1}],
                   ties=[{"from": "Ma", "to": "me", "change": {"trust": "+small"}, "cause": "he helped with the rent"}],
                   threads=[{"kind": "owed", "by": "Frank", "to": "me", "text": "repay by Friday", "due_in_days": 4}])
assert knows(conn, mother, sid, beat=1) and not knows(conn, frank, sid, beat=1)   # Frank came in after the lie
assert belief_holds_true(conn, mother, sid, beat=1) == 0                          # she believes a lie
assert obligation(conn, frank, me)["source_scene_id"] == sid
assert familiarity_after_second_scene_gain < familiarity_after_first_scene_gain   # repeated company counts less
assert scenes.open_scene_id(conn) is None
# Review Focus 2: a stranger named in present who is in another town
r = scenes.open_scene(conn, "c5", [stranger_elsewhere], "bar")
assert stranger_elsewhere in r["not_here"]
scenes.close(conn, "c6", "from_stamps")
assert not knows_anything_from(conn, stranger_elsewhere, r["scene_id"])
# a new place while a scene is open is refused, not merged
scenes.open_scene(conn, "c7", ["Frank Moretti"], "garage")
assert "close_scene" in scenes.open_scene(conn, "c8", ["Ma"], "kitchen", location="Basile house")["refused"]
# a quiet scene with no stamps closes cleanly
assert scenes.close(conn, "c9", "commit")["closed"]
# names: a unique first name resolves; a shared one is refused with candidates
bad = scenes.close(conn, ..., ties=[{"from": "Tony", "to": "me", "change": {"trust": "+small"}, "cause": "x"}])
assert bad["refused"][0]["candidates"] and scenes.open_scene_id(conn) is not None and not bad.get("closed")
assert scenes.close(conn, ..., ties=[{"from": "Tony Rizzo", ...}])["closed"]    # the retry goes through
# a meeting with two people writes two obligations; disbelief still records that it was said
assert len(obligations_from_scene(conn, sid_meeting)) == 2
assert knowledge_of(conn, ma, sid, beat=1)["confidence"] == 0.1                 # disbelieved_by=["Ma"]
# two scenes in a row: the second familiarity step is smaller, and the first scene's people aren't in the second
assert step2 < step1 and not participant(conn, scene2, frank)
# owed thread direction: Frank owes me, not the reverse
assert obligation_from(conn, frank, to=me)
```
- [ ] **Step 2: Run it.** Expected: FAIL (no module `engine.scenes`).
- [ ] **Step 3: Implement** `engine/scenes.py` and the `relationships.py` change.
- [ ] **Step 4: Run it, then `--quick`.** Expected: PASS, no new failures.
- [ ] **Step 5: Commit** `engine/scenes.py engine/relationships.py tests/scene_ledger_test.py`.

### Task 5: Scene ledger in the connector

**Files:**
- Modify: `connector/store.py` (`_scene_note` calls `scenes.open_scene` and keeps writing `last_scene`; new
  `kind="stamp"` in `NOTE_TYPES`, read from the new `stamp` parameter)
- Modify: `connector/server.py`:
  - a new `close_scene` tool, registered in `register_tools`;
  - `stamp: dict | None` and `location: str | int | None` parameters on `note`;
  - every writing tool call (`act`, `money`, `author`, `note kind=detail`) runs inside
    `rollback.current(conn, scene_id=...)` while a scene is open (revision 5.2);
  - auto-stamping after a successful `act`, `money` or `author` while a scene is open;
  - `changed` (only what this call changed) on results during an open scene.
- Create: `connector/scene_close.py` (the tool body, run under `store.run_once`)
- Modify: `connector/timeflow.py` (refuse while a scene is open)
- Modify: `connector/session.py` (resume shows the open scene and its ledger)
- Test: `tests/connector_scene_ledger_test.py`

**Interfaces:**
- Consumes: Task 4's `engine/scenes.py`.
- Produces: the `close_scene` tool exactly as in the contract; the stamp mapping: `money` op pay or set_cash goes to
  `money` (with `ref_table` money_records), op owe to `promise`; `act` attack goes to `injury` when harm resulted, pay
  or lend to `money`, other acts to `other`; `author` person goes to `enter`.

- [ ] **Step 1: Write the failing test** (connector functions called directly, as in
  `tests/saintjude_connector_play_test.py`):
```python
server.note("n1", "the garage, morning", kind="scene", present=["Frank Moretti"])
paid = server.money("m1", "pay", {"to": "Frank Moretti", "amount": 40, "what": "parts"})
assert record_changes_for_scene(conn, open_scene_id(conn))                 # mid-scene writes are logged
assert paid["stamp"]["kind"] == "money"
assert server.advance("a1", 7, "work", from_day=day)["status"] == "refused"
assert "close_scene" in server.advance("a1b", 7, "work", from_day=day)["reason"]
# Review Focus 1: a new chat resumes mid-scene
r = server.resume_current()
assert r["open_scene"]["ledger"][0]["kind"] == "money"
assert server.close_scene("cs1", mode="from_stamps")["closed"]
assert server.advance("a2", 7, "work", from_day=day)["day_ended"] > day
# replay: the same call_id returns the same result and closes nothing twice
assert server.close_scene("cs1", mode="from_stamps").get("replayed")
# review mode commits nothing
server.note("n2", "the club", kind="scene", present=["Frank Moretti"])
server.close_scene("cs2", mode="review"); assert scenes.open_scene_id(conn) is not None
st = server.note("st1", "Frank swears the car was fine", kind="stamp", stamp={"kind": "lie", "by": "Frank", "true": False})
assert st["stamp"]["kind"] == "lie" and "changed" in st
```
- [ ] **Step 2: Run it.** Expected: FAIL (no `close_scene`).
- [ ] **Step 3: Implement.** The `close_scene` docstring follows the house style: one paragraph naming the modes and
  the five field shapes.
- [ ] **Step 4: Run it, then `--quick`** (the connector tests must still pass: `connector_*`,
  `saintjude_connector_play_test`).
- [ ] **Step 5: Commit** the five files and the test.

### Task 6: Scene undo

**Files:**
- Modify: `engine/rollback.py` (add `undo_scene`; keep Task 3's `current`, `log_*` and the key map. `undo_chain` is
  built in Task 15)
- Modify: `connector/correct.py` (op `undo_scene`; `preview` shows what it would revert)
- Modify: `engine/commitments.py` (`record` and `complete` log through `rollback.log_insert` and `log_update`)
- Test: `tests/rollback_cascade_test.py`

**Interfaces:**
- Produces `undo_scene(conn, scene_id) -> {"reverted": {table: count}, "left": [...]}`. It replays the
  `record_changes` log backwards:
  - inserts are deleted;
  - updates are restored from `before_json` only where no later change touches the row (otherwise the row is listed
    in `left`);
  - ties are inverted from `relationship_history`;
  - money is reversed with a reversing record, never deleted;
  - authored rows are marked reverted when nothing later refers to them, otherwise listed in `left`;
  - the scene's status becomes `abandoned`.

- [ ] **Step 1: Write the failing test:**
```python
s1 = close a scene where Frank promises repayment and the mother hears a lie
s2 = close a later scene where Frank and Dominic quarrel (trust -10)
rollback.undo_scene(conn, s1)
assert no_rows_with(conn, "source_scene_id", s1)
assert trust(frank, me) == trust_after_s2_minus_s1_effects       # s2's -10 stays
assert knows(conn, frank, s2, beat=1)                              # Review Focus 3
assert server.correct("u1", "undo_scene", "", {"scene": s1})["error"]   # player_said is required
# a scene with several effects comes back whole
s3 = scene where Dominic pays Frank $100, Ma's trust drops, Frank's open debt is marked fulfilled, a commitment is
     recorded, and a raw record_changes update re-sets a business's state
snap = state_of(conn, ["money_records totals", "relationships", "obligations", "commitments", "businesses"])
rollback.undo_scene(conn, s3)
assert state_of(conn, ...) == snap_before_s3 and cash(me) == cash_before_s3     # money reversed by record
assert obligation(conn, frank_debt)["status"] == "active"                        # un-resolved
# out of order: scene 2 re-set the same business row after scene 1; undo scene 1 only
result = rollback.undo_scene(conn, s_first)
assert business_row_in(result["left"])                                           # later overwrite kept, reported
assert not record_changes_rows_for(conn, "relationships")                        # ties never double-logged
assert record_changes_count_after_weekly_tick(conn) == before_tick               # silent outside a context
```
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run it, then `--quick`** (checkpoint).
- [ ] **Step 5: Commit** `engine/rollback.py connector/correct.py engine/commitments.py tests/rollback_cascade_test.py`.

### Task 7: GM fault checker on real transcripts

Revision 5.2: no scripted bench. The owner's real playtests are the test, and this tool reads them.

**Files:**
- Create: `tools/gm_check.py`
- Test: `tests/gm_check_test.py`

**Interfaces:**
- `gm_check.py <transcript.txt | session.jsonl> -> {"G1": [...hits], ..., "G5": [...], "ledger": [...]}`:
  - G1 to G5 by pattern, with the line of each hit;
  - from a session's tool calls, if present: every scene closed, no tool error left unanswered, and every refusal
    with an `owner_notice` followed by prose that tells the player;
  - revision 5.3, `--db <save.db>` (optional): each closed scene's stamps match the session's calls; every person given
    a part exists as a row; a lie stamped `true: false` left a `holds_true=0` belief with its hearers; anyone who
    walked out holds no beat after leaving.

- [ ] **Step 1: Write the failing test** on three canned transcripts: one with a numbered menu (G1 hit), one asking
  the player what the bartender's name is (G2 hit), and one clean (no hits). Add a session where a refusal is
  swallowed silently (a ledger hit), and a small save where a named extra is missing (a `--db` hit).
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run it on `docs/playtests/2026-11-25-dominic-2.txt`.** Expected: hits on the faults the owner named.
- [ ] **Step 5: Commit.**

---

## Phase C: build step 3 (slice 2a, the GM–engine loop)

### Task 8: Consequence facts in tool results

**Files:**
- Create: `engine/answers.py`
- Modify: `connector/acting.py`, `connector/money.py`, `connector/authoring.py` (call `answers.judge` after a
  successful change, and add `answers` to the result. Nothing is stored and there is no `rationale` (revision 5.2))
- Modify: `connector/server.py` (a refusal carries `owner_notice`: one plain line the GM tells the player when the
  engine and the GM's proposal disagree)
- Modify: `worlds/saintjude/levels.json` (`answers`: the cash share only)
- Test: `tests/engine_answers_test.py`

**Interfaces:**
- `judge(conn, tool, actor_id, change) -> list[{"kind": "consequence", "text": str}]`. It states a fact when an act is
  weighty:
  - money above the `answers` share of his cash;
  - violence, or an act that is a crime;
  - an act against an outfit's man or territory;
  - breaking a live obligation, which it names.

  It never judges the act, and it never blocks.

- [ ] **Step 1: Write the failing test:**
```python
out = server.act("x1", "attack", "he beats Sal Ferrante", target_actor_id=sal_an_outfit_man)
assert any("Ferrante" in a["text"] for a in out["answers"]) and out["status"] != "refused"   # a fact, not a veto
quiet = server.money("x3", "pay", {"to": "Frank Moretti", "amount": 5, "what": "coffee"})
assert "answers" not in quiet                                                          # ordinary stays ordinary
r = server.author("x4", "person", {"name": "Tullio Bruni", "role": "owns the Starlite"})  # contradicts the record
assert r["status"] == "refused" and r["owner_notice"]
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus touched modules, commit.

### Task 9: Canon by kind and record standing

**Files:**
- Create: `engine/standing.py`
- Modify: `connector/store.py` (`kind="detail"` with `field` set writes `standing.confirm`; a claim note gives
  knowledge to everyone present in the open scene; both carry the open scene id)
- Modify: `connector/views.py` (`lookup` returns `on_record` as `{attribute: {"standing", "value"}}` and says
  `not on record (unknown)` when asked about an attribute with no row)
- Test: `tests/canon_standing_test.py`

**Interfaces:**
- Produces: `confirm(conn, kind, id, attribute, *, holds: bool, value=None, scene_id=None, chain_id=None)`,
  `standing_of(conn, kind, id, attribute) -> dict | None`. (`infer` waits for step 8: revision 5.3.)

- [ ] **Step 1: Write the failing test:**
```python
server.note("d1", "Palumbo owns the bar on Carlisle", kind="detail", subject_kind="business", subject_id=bar, field="owner")
assert standing.standing_of(conn, "business", bar, "owner")["standing"] == "confirmed"
server.note("d2", "no wife", kind="detail", subject_kind="actor", subject_id=supplier, field="spouse")  # checked: none
assert standing.standing_of(conn, "actor", supplier, "spouse")["holds"] == 0
assert standing.standing_of(conn, "actor", other_supplier, "spouse") is None           # unknown, not "no wife"
assert "unknown" in dump(server.lookup("Other Supplier spouse"))
# a claim made in a scene reaches those present, as the speaker's statement
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 10a: One news gate

**Files:**
- Create: `engine/news_gate.py`
- Modify: `connector/timeflow.py` (when `engine_meta.news_gate='1'`, `news` replaces `noticed`, the hearsay
  `material` keys and texture's news items; `money`, `chances`, `waiting_on_you`, `history_due`, `settled` stay)
- Modify: `engine/texture.py` (`circle` stops counting customers with open deals or work matters as near)
- Modify: `engine/hearsay.py` (knowledge it delivers gets `path_kind='told'` and `carrier_actor_id`)
- Modify: `engine/levels.py` (new saves set `news_gate='1'`)
- Modify: `engine/scenes.py` (`news_gate.deliver` in `close`), `engine/information.py` (the `information` slot runs
  `news_gate.spread` whatever `rumour_broadcast` says), `connector/money.py` (`visible_spend`) and
  `engine/civic_tick.py` (his public civic acts start spread rows). Revision 5.4.
- Modify: `worlds/saintjude/levels.json` (`news_paths`: which everyday channels he has by default and what each carries)
- Test: `tests/news_gate_test.py`

**Interfaces:**
- Produces:
  - `reaches(conn, me, start_day, end_day) -> list[{"text", "path", "via", "firsthand", "why", "floor"}]`;
  - `held_for(conn, me, carrier) -> list[...]` (what a carrier holds for him, shown in the scene brief when the carrier
    is present).
  - `spread(conn, day) -> int` (revision 4.1): a knowledge row with `spread_from_day` set travels outward. That
    covers his deeds from a closed scene, and anything a witness saw. The first hop is to the holders' close ties and
    workmates, chosen by the same path rules. The package sets the delay per hop, the drop-off and the chance of a
    detail changing (`news_paths.spread`). A changed detail is a new row with `holds_true=0`. Every row reached feeds
    `claims` impressions of the person it is about. It runs on the `information` process slot, whatever
    `systems.rumour_broadcast` says (revision 5.2).
  - Revision 5.2:
    - **Visible success travels too.** These start spread rows with him as their subject: a purchase above the
      package's `visible_spend` line (`connector/money.py`) and his public civic acts (`engine/civic_tick.py`).
      Revision 5.3: a sustained rise in his business's work is added in Task 18c, where growth is first measured.
      Test: a big purchase and a council vote each leave a spread row about him.
    - **Hooks:** this task adds `news_gate.deliver` to `scenes.close`.
    - **Skips:** in `connector/timeflow.py`, a skip stops for floor items and `waiting_on_you` matters. Otherwise it
      runs through.
- An item passes only with a **path** (knowledge row with `path_kind`, or a public event of high enough severity on an
  everyday channel he has) **and relevance** (kin, a friend, his money, his business, danger to him or his, or an
  interest on his sheet). Attention only ranks within the read budget. Floor items (danger, an active obligation,
  close kin) are never dropped.
- During a skip (amendment 6), news someone has to tell him goes to `pending_news`. It reaches him three ways:
  - **in town, urgent:** an item of an `urgent_kinds` kind (illness, danger, an urgent demand) from close kin or a
    close tie arrives by phone or visit and is delivered during the skip;
  - **in town, not urgent:** delivered only when the carrier was actually with him, meaning the same household or the
    same place by `routines.where`. Otherwise it waits;
  - **unreachable:** while a `routine_exceptions` row of kind prison, travel or away covers him, only mail and what
    he saw arrive (and paper and radio where he is). Everything else waits.

  What waits comes back through `held_for` when the carrier is in a scene with him. It is then delivered once
  (`delivered_scene_id`) and never offered again. A false item stays false as it travels (`holds_true` is copied).
- Revision 4.2, atmosphere: the paper and radio he has carry a few public items a day whatever their relevance,
  marked `atmosphere`, up to `news_paths.atmosphere_per_day`. They are colour for the GM, never floor items.

- [ ] **Step 1: Write the failing test:**
```python
# Gerald case: a one-off customer's good fortune never reaches him in advance
make_customer_with_open_deal(conn, gerald); give_windfall(conn, gerald)
assert not any("Gerald" in n["text"] for n in advance_news(server, 14))
# stale rumour case: a legacy knowledge row with no path never shows
insert_legacy_knowledge(conn, me, "Mario Basso was seen at the docks")
assert not any("Mario Basso" in n["text"] for n in advance_news(server, 7))
# kin case: his mother's illness reaches him, told by his sister, as floor
assert any(n["why"] == "kin" and n["path"] == "told" for n in news_after_mother_falls_ill(server))
# Review Focus 5: away in prison, the sister's news waits with her
put_away(conn, me, days=20); news = advance_news(server, 14)
assert not any(n["path"] == "told" for n in news)
assert news_gate.held_for(conn, me, sister)
# in town: the sister lives elsewhere, but their mother's illness is urgent and reaches him by phone
assert any(n["why"] == "kin" for n in in_town_skip_news(server))
# in town, not urgent gossip from a friend he never crossed waits with the friend
assert news_gate.held_for(conn, me, friend) and not gossip_in(in_town_skip_news(server))
# delivered once: after a scene with the sister, nothing she held is offered again
scene_with(server, sister); assert not news_gate.held_for(conn, me, sister)
# a false rumour stays false in transit
assert knowledge_of(conn, me, rumour_key)["holds_true"] == 0
# revision 4.1: his deed travels outward, and changes on the way
fight_in_scene(server, me, beats="Sal Ferrante in the Starlite"); run_days(conn, 21)
assert knows(conn, sals_cousin, "fight") and not knows(conn, stranger_across_town, "fight")
assert impression(conn, about=me, audience=sals_crew) != impression_before
assert any(r["holds_true"] == 0 for r in knowledge_rows(conn, "fight"))     # some tellings change
# a skip stops for something serious or needing his decision, and runs through otherwise
assert skip_stopped_by(server, days=30, cause=mother_badly_ill) and not skip_stopped_by(server, days=30, cause=None)
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick` (update `connector_advance_test` expectations only
  where the gate deliberately changes them, and say which in the commit), commit.

### Task 10b: Every side door onto the gate

All doors are in Deploy 1 (revision 4): without crime and civic news on the paper and radio, the city goes quiet
for him.

Approved by the owner on 2026-11-26. After this task, nothing reaches the protagonist's news except through
`news_gate` (a knowledge row with a `path_kind`, or an everyday channel he has).

**Files and the door each closes:**
- Modify: `engine/life_matters.py` (`weekly`'s `hearsay.reach` call writes `pending_news` with a carrier instead)
- Modify: `engine/claims.py` (`deliveries` go to `pending_news`; `from_knowledge` stops reading legacy `rumour:` rows)
- Modify: `engine/civic_tick.py` (`_tell_player`: votes and results go out on the paper and radio channels, and an
  associate's indictment goes to `pending_news` with a carrier; nothing goes to the old delivery ledger)
- Modify: `engine/texture.py` (`ingest` and `deliver` stop when `news_gate='1'`; the room read in `block` stays)
- Modify: `engine/temptations.py` and `connector/timeflow.py` (a new chance for the protagonist reaches him through
  its carrier or the place he passes, as gate news; `chances` in the time-skip result shows only those that reached
  him; the chances themselves are unchanged)
- Modify: `engine/findings.py` (`tell` and `learn` write `path_kind` and `basis`, and log through `rollback` inside
  a scene)
- Modify: `engine/crime_response.py` (a report with high `publicity` in `public_attention` becomes a paper or radio
  item; the threshold goes in `levels.json` `news_paths`)
- Modify: `engine/information.py` (the event-to-rumour broadcast, `seed_rumours_from_events` and the exposures, runs
  only when `systems.rumour_broadcast` is true; Caerness sets it, Saint Jude leaves it out)
- Test: `tests/news_side_doors_test.py`, one case per door

- [ ] **Step 1: Write the failing test:**
```python
for door in ("life_matters", "claims", "civic", "texture", "temptations", "findings"):
    item = trigger_door(conn, door)                           # each makes something he could hear about
    assert item_arrives_only_via_gate(server, item)           # reaches him with a path, or waits with a carrier
assert paper_carries(server, high_publicity_crime(conn)) and not paper_carries(server, low_publicity_crime(conn))
assert count_after_days(conn, "rumour_exposures", 30) == 0    # no broadcast in Saint Jude
put_away(conn, me, days=20); assert not civic_indictment_reaches(server)   # away means it waits
assert claims_moved_for(conn, offscreen_hit_victims_outfit)                  # reputation still moves offscreen (5.2)
```
- [ ] **Step 2 to 5:** run (FAIL), implement door by door, run with `--quick`, commit per door.

### Task 11: Brief and change-based read budget

**Files:**
- Create: `connector/brief.py`
- Modify: `connector/views.py` (`compact_scene` builds on `brief.full`), `connector/store.py` (`note kind=scene`
  returns `brief.full`), `connector/timeflow.py` (after a skip, return `brief.full` in place of the separate blocks),
  `connector/server.py` (results of `act`, `money`, `note` during an open scene carry `brief.changed`)
- Modify: `engine/texture.py` (`block` drops `outside_his_knowledge`) and `engine/claims.py` (`cutaways` is no longer
  shown)
- Modify: `engine/outings.py` (`go_out` returns who is really there (`crowd`, built on `routines.where` and the
  place's population) and the place's character. Revision 5.2: plus one to three facts already true about people
  in the crowd: a regular's live concern, a rival crew's man in the room, an open tie to him, payday. The happenings
  draw, `you_may` and `approach` are deleted, and the GM invents the night)
- Modify: `engine/findings.py` (where the record is silent, `answers` returns `unknown` and the GM may invent)
- Modify: `connector/views.py` and the tool results it shapes (facts and numbers in fields, not engine-written
  sentences; keep the wording the GM needs to know what a fact is, nothing more)
- Test: `tests/brief_budget_test.py`

**Interfaces:**
- Produces:
  - `full(conn) -> dict`, keys in this order: `waiting_on_you`, `you` (revision 4.1: his injuries and health,
    police interest in him, debts both ways, grudges he knows of, open promises and meetings, each with since
    when; revision 5.1: what he runs, such as his businesses, his outfit or his office, with the people under him,
    their state and his rivals' known moves, kept to a few lines and only what changed since his last closed
    scene (revision 5.3: a day window, since the brief keeps no cursor)),
    `present` (per person: name, body, manner,
    temperament in words, tie to him in words, `on_their_mind` (at most three live concerns in plain words, the strongest first by `strength`), `about_to`
    (pending decisions that involve this scene or him), `has_news_for_you` (from `held_for`)), `crossing_your_path`
    (arrivals, visits, matters due within 7 days that involve him), `news`, `money`, `texture`;
  - `changed(conn, call_effects) -> dict`: only what this one call changed. There is no cursor, since MCP calls hold
    no state between them. Bringing someone in or seeing them leave adds or removes their `present` entry.
  - `full` is read-only. `has_news_for_you` lists a carrier's items not yet delivered, or delivered in this open
    scene, so `resume` and a second brief show the same thing. Delivery happens at `close_scene` (Task 4).
- Revision 5.2:
  - In a personal scene (no one under him present), the brief carries only urgent seat matters. The rest go in skip
    results and work scenes.
  - After a skip, `advance` returns `brief.full` plus its skip-only fields: `nominations`, `chances`, `settled`,
    `done_by_his_people` and `history_due`.
  - Revision 5.3: this task defines `nominations`, `done_by_his_people` and the seat-matter filter with empty
    defaults. Tasks 14a and 14c fill them.
- Nothing about people not present, and nothing building elsewhere, appears in either. The owner's rule
  (2026-11-26): the GM sees only what is nearing the protagonist (`crossing_your_path`); the old "outside his
  knowledge" part and the cutaways go.

- [ ] **Step 1: Write the failing test:**
```python
b = server.note("s1", "dinner at the Morettis'", kind="scene", present=["Aurelio Moretti"])["brief"]
assert list(b)[:3] == ["waiting_on_you", "you", "present"]
assert "Aurelio" in dump(b["present"]) and "Tullio" not in dump(b)        # Tullio's plans aren't in the room
assert len(dump(server.money("p1", "pay", {...})["changed"])) < 600        # per-call changes stay small
assert not leak_words(b, ["concern", "pressure", "score", "engine"])       # no machinery
assert "outside_his_knowledge" not in dump(b) and "cutaway" not in dump(b)
injure(conn, me, "broken hand"); owe(conn, me, frank, 200)
b = brief_full(server); assert "broken hand" in dump(b["you"]) and "200" in dump(b["you"])   # it lingers
assert "you_may" not in dump(server.act("p1", "go out", {"place": "the Starlite"}))   # no menu of moves
assert not happenings_in(server.act("p1", "go out", {"place": "the Starlite"}))       # the GM invents the night
assert findings_answer(server, "does the supplier have a wife?")["status"] == "unknown"
assert prose_share(b) < 0.2                      # fields, not sentences (lead sets the bound from the first run)
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 12: Storyteller rulebook

**Files:**
- Modify: `connector/rulebook_core.md` (rewrite as the principles of design section 4, each with one short playtest
  example from `docs/playtests/2026-11-25-dominic-2.txt`, plus how to use scenes, stamps, `close_scene`, canon by kind,
  consequence facts and `owner_notice`. Turning events are taught in Task 15)
- Modify: `worlds/saintjude/rulebook_section.md` (Saint Jude's own examples, if any principle needs one)
- Test: `tests/connector_resume_test.py` (update the rulebook expectations it pins)

- [ ] **Step 1:** Rewrite. The rulebook holds only:
  - the storyteller principles, each with one example;
  - a scene lifecycle of five lines or so: open with `note(kind="scene")`; stamp what can't be undone; close with
    `close_scene` before moving on or skipping; `from_stamps` when there's nothing to add; `resume` returns an open
    scene.

  - the division of labour (design section 0), and four rules from the owner's brief: tell the owner when you
    and the engine disagree, and let him rule; play nominations within the timeframe you set; the first woman,
    customer or fight is not special by default; record what you invent that should last;
  - revision 4.2: look for opportunities in what the world already holds (a rival in trouble, a man out of work)
    without inventing their causes; record only meaningful changes, since an ordinary evening needs only a close;
    use the paper, the radio and gossip for atmosphere, not only for plot;
  - revision 5.1: never push him to rise. A quiet life, holding what he has, and staying ordinary are all valid
    stories; his circumstances set the scale of what happens, from rent and friends to rivals and elections;
  - revision 5.2: an `owner_notice` is always told to the player in plain words. Ordinary people behave
    ordinarily: most customers pay on time, and a late or bad payer is an exception with a reason.

  Parameter shapes and modes go in the tool docstrings (`note`, `close_scene`, `author`), where the GM reads them at
  call time. Principles, not rules per symptom.
- [ ] **Step 2:** `--quick`. Expected: PASS.
- [ ] **Step 3: Commit.**

### Task 13: Slice 2a checkpoint (lead)
- [ ] The lead plays a short session on a fresh save, runs `gm_check.py` on it and reads it against the Task 1
  checklist. Fix rounds go to the owning task's
  files.
- [ ] Review P2.32 to P2.37 (commits up to `dc448e9`) against the design: list each fix as kept, folded in, or to be
  dropped. Dropping code needs the owner's yes.
- [ ] Report to the owner before Phase D.

---

## Phase D: build step 4 (slice 2b, a minimal living world)

### Task 14: Nominations, consistency and agency guards (built as 14a, 14b and 14c)

Revision 5.2 splits this task into three sessions, in this order:
- **14a:** `near`, the nomination functions, `levels_tick.py`, the life-module hooks, and invented people who go on
  living. Files:
  - `engine/nominations.py`, `engine/levels_tick.py` and `engine/simulation.py`;
  - the life modules listed below;
  - `connector/server.py` (`note(kind="plan")`, `realizes` on `author` and `close_scene`, and seeding a person on
    `author` or `realize`);
  - `connector/brief.py` and `connector/timeflow.py` (fill `nominations`);
  - the `nominations` block of `worlds/saintjude/levels.json`.

  Test lines: up to the consistency check, plus the budget lines and Teresa's.
- **14b:** `conduct.py`, broken promises and lies found out. Files: `engine/conduct.py`, `engine/scenes.py`,
  `engine/levels_tick.py` (register its steps) and the `conduct` block of `levels.json`. Test lines: the revision 4.1
  ones.
- **14c:** agency guards and seat decisions. Files:
  - `engine/org_succession.py`, `engine/org_coup.py` and `engine/crime_response.py`;
  - `engine/org_choices.py`, `engine/outfit_choices.py`, `engine/org_money.py` and `engine/org_happenings.py`;
  - `engine/business.py` (`process_due_businesses`). `merchant.py` is not hooked: Saint Jude does not run it
    (`merchant_houses` is off; revision 5.4);
  - `engine/civic_tick.py`;
  - `connector/brief.py` (fill `done_by_his_people` and the seat-matter filter);
  - the `delegation` block of `levels.json`.

  Test lines: the agency-guard line and the revision 5.1 ones.

Task 14d, below, is starts at any scale.

Replaces the protection lock (design section 0, approved 2026-11-27). Life near him goes on at realistic rates. The
engine nominates, the GM realizes and the engine ratifies.

**Files:**
- Create: `engine/nominations.py`
- Create: `engine/levels_tick.py` (revision 5.2, in 14a: process key `levels`, weekly, registered in
  `engine/simulation.py` after `life_matters`. `process_due` runs `levels.refresh`, `nominations.apply_overdue`,
  and from 14b `conduct.weekly`, `conduct.lies` and overdue promises. Later tasks add their steps to it.
  Revision 5.4: it also clears stated decisions from scenes once their due day has passed. One that involves him
  becomes a `waiting_on_you` matter. Any other is marked `lapsed`. Task 17b later fires them instead.)
- Modify: `engine/life_matters.py`, `engine/outings.py` (offscreen flings and scuffles), `engine/opening_family.py`
  (`resolve_unnamed_marriages`), `engine/household_life.py` (planned births), `engine/civilian_life.py` (a grown
  child nobody knew of), `engine/temptations.py` (`_others`), `engine/org_happenings.py`: a draw that touches someone
  `near` him becomes a nomination; a draw on anyone else applies as today
- Modify: `engine/org_succession.py`, `engine/org_coup.py`, `engine/crime_response.py` (agency guards: never vote,
  spend, plot, defect or plead for the protagonist)
- Modify: `connector/server.py` and `connector/brief.py` (`nominations` in `brief.full` and in the skip result;
  `note(kind="plan")`; `realizes` on `author` and `close_scene`)
- Create: `engine/conduct.py` (revision 5: outstanding matters from remembered facts, and lies found out)
- Modify: `engine/scenes.py` (a thread past its date, unmet, becomes a broken promise on the record)
- Modify: `worlds/saintjude/levels.json` (`nominations`: default and longest timeframe, reminder lead, weekly
  budget and weight per kind; `conduct`: quiet days by closeness, and how long a wrong waits before it surfaces)
- Test: `tests/nominations_test.py`

**Interfaces:**
- Produces:
  - `near(conn, day) -> set[int]` (revision 4.2: relevance, not proximity): the active people, his household and
    kin, his ties and recurring connections, anyone who dealt with him in a scene within `lock_quiet_days`
    (named in a stamp or given a part, not merely present), and anyone involved in an event that affects him.
    Someone only at the same place is not near.
  - `nominate(conn, kind, actor_ids, cause: str, payload: dict, chain_id=None) -> int`. `payload` holds what
    `apply_overdue` needs: the partner, the destination, the illness (revision 5.2).
  - `plan(conn, nomination_id, by_day, text) -> None` (the GM's timeframe; refused past the package's longest).
  - `decline(conn, nomination_id, reason) -> dict` (refused without a reason that names something in the record).
  - `realize(conn, nomination_id, change: dict) -> dict` (checked like any authored change; contradictions refused).
  - `due(conn, day) -> {"new": [...], "remind": [...], "overdue": [...]}`.
  - `apply_overdue(conn, day) -> list[int]`: past `by_day` (or the default timeframe if no plan), the engine applies
    the development in a plain form through the same path the draw would have used.
- **Consistency:** nothing the engine applies may contradict what a scene established (`scene_stamps`, recorded
  ties, standing). Where it would, it becomes a nomination instead.
- **Agency guards:** the engine never chooses the protagonist's acts.
- **Seat decisions are his (revision 5.1).**
  - Every code path that chooses for a seat holder checks whether the holder is the protagonist:
    - `org_choices` and `outfit_choices` (rackets, hits, discipline, recruitment);
    - `org_money` spending;
    - `org_happenings`;
    - business decisions (`business.process_due_businesses`);
    - `civic_tick` votes, appointments and deals.
  - Where it is him, a decision the package marks his own (`delegation` in `levels.json`: money above a share of
    the seat's funds, violence, membership, votes and deals) becomes a `waiting_on_you` matter, with a timeframe
    like a nomination.
  - Routine running goes to his second or manager. If he has none, the seat keeps going as it was. Each such act is
    listed in the skip result as done by them.
- Revision 4.1:
  - **`conduct.weekly(conn, day) -> list[int]`** (revision 5: facts and one rule, no build-up maths). For each
    person `near` him it reads facts already on record:
    - the day they last shared a scene, against the package's quiet days for their closeness (`neglect`);
    - a wrong he did them, from a stamp (`wronged`);
    - a promise to them past its date and unmet (`broken_promise`);
    - news they hold of him with another partner (`jealousy`).

    One rule: a fact still outstanding after its package wait opens one nomination naming that fact. At most one open
    nomination per person; a later fact adds to its cause. How it shows, a sharp word or a cold dinner, is the GM's
    to play.
  - **`conduct.lies(conn, day)`:** for a `holds_true=0` belief that he caused, when a holder of the truth shares a
    household, routine place or scene with the believer, it nominates the discovery.
  - **Budget:** one table and one loop, with no scoring beyond the package weight per kind. Each week the GM gets
    nominations by weight up to the package budget. The rest, the small ones, the
    engine applies plainly at once and lists in the skip result as done. Weight comes from what a development
    touches: a tie to him, an obligation, his money, business or safety. Revision 5.2: routine changes (a new
    drinking place, a car bought) never become nominations. They apply as background life.
  - **Invented people live:** `realize` and `author` of a new person seed a routine, run `levels.refresh` for them,
    and give them a purse (as `life_matters.settle_circle` does) and a life profile.

- [ ] **Step 1: Write the failing test:**
```python
anthony = brother_of(conn, me)
force_draw(conn, "romance", anthony); n = nominations.due(conn, day)["new"][0]
assert n["actor_ids"] == [anthony] and n["cause"] and not life_matter_with(conn, anthony, "romance")  # nominated, not applied
nominations.plan(conn, n["id"], day + 30, "he meets her at his cousin's wedding")
assert nominations.due(conn, day + 25)["remind"]                            # reminded inside the window
assert nominations.realize(conn, n["id"], {"partner": "new", "name": "Teresa Lauro", "age": 23})["accepted"]
assert actor_named(conn, "Teresa Lauro") and tie(conn, anthony, "Teresa Lauro")
m = nominations.nominate(conn, "move_away", [cousin], "work in Newark")
run_days(conn, default_timeframe + 1); assert moved(conn, cousin)          # overdue: the engine applies it
assert not nominations.decline(conn, m2, reason="")["ok"]                  # a reason is needed
assert life_matters_still_applies_far(conn)                               # far from him the city runs as before
courting_in_scene(conn, me, carla); force_draw(conn, "union", carla, partner="stranger")
assert not married(conn, carla, "stranger")                               # consistency with the record
assert protagonist_plea(conn) is None and not voted_for_protagonist(conn)  # agency guards
# revision 4.1
no_scene_with(conn, me, girlfriend, weeks=5); conduct.weekly(conn, day + 35)
assert nomination_of(conn, girlfriend)["kind"] == "neglect"
promise_in_scene(server, me, to=brother, by=day + 3); run_days(conn, 5)
assert broken_promise_on_record(conn, me, brother)
lie_in_scene(server, me, to=mother, truth_known_to=[frank]); same_place(conn, frank_wife, mother); conduct.lies(conn, day)
assert nomination_of(conn, mother)["kind"] == "lie_found_out"
flood_near(conn, people=12); week = nominations.due(conn, day)
assert len(week["new"]) <= budget(conn) and applied_small(conn)             # the GM isn't buried
assert nomination_kinds_to_gm(week) >= {"romance"}
d = stated_decision_in_scene(server, frank, "he'll call round Friday", due=day + 4); run_days(conn, 8)
assert decision(conn, d)["status"] == "lapsed" or waiting_on_you_has(server, "call round")   # never stuck pending
force_draw(conn, "new_local_bar", anthony); assert applied_directly(conn, anthony, "new_local_bar") and not nomination_of(conn, anthony, "new_local_bar")
assert stranger_in_same_bar not in nominations.near(conn, day)                 # presence alone isn't relevance
teresa = realized_person(conn, "Teresa Lauro")
assert routines.where(conn, teresa, day, "day") is not None and has_purse(conn, teresa)   # she goes on living
# revision 5.1: his seat's decisions are his
seat_protagonist_as_boss(conn, outfit); run_weeks(conn, 4)
assert not hit_ordered_by(conn, me) and waiting_on_you_has(server, kind="seat_decision")
assert routine_acts_by(conn, his_second(conn, outfit)) and listed_in_skip_result(conn, "done by")
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus the tests of every modified module, commit.

### Task 14d: Starts at any scale (Deploy 1)

**Files:**
- Modify: `engine/new_character.py` (a start in a held seat: `veto.held_by_other` no longer refuses it at the
  opening. The holder is moved aside before day 0 through `real_figures` and the life paths, as retired, dead or not
  present in this save, with the reason recorded. He takes the seat with its people, history and obligations.)
- Modify: `engine/veto.py` (held seats refused during play as now, allowed only for the opening)
- Create: `tools/start_check.py` (the four-start check)
- Test: `tests/start_scale_test.py`

**Interfaces:**
- **Moving a holder aside (revision 5.2):**
  - `retired`: he vacates the seat only, and his household, kin, debts and past stay.
  - `dead`: his death is dated before day 0, his estate passes by the package's inheritance rules, and his kin
    grieve.
  - `absent` (never in this save): allowed only when no kin, obligation or `lived_past` entry refers to him.
- `create_protagonist(conn, proposal, call_id)` accepts a held seat: an office, the head of an existing outfit, or
  the owner of an existing company. It returns the displaced holder and the reason in its account.
- First, probe what a large start gives today: a businessman with several companies and many employees. Report to
  the lead before changing anything for scale.
- `start_check.py --start <mechanic|businessman|politician|boss> --days 30 -> JSON`: a fresh save from
  `tests.sj_fixture` through `new_character`, then 30 days with routine acts. It reports:
  - the circle (kin, friends, colleagues) and holdings;
  - open matters;
  - nominations from his personal life;
  - the city's own events in the same days;
  - for a seat, the seat decisions sent to him;
  - revision 5.2: the three world measures (stored-cause share, events per kind, never-fired actions with the
    reason), in place of a separate scorer.

- [ ] **Step 1: Write the failing test:**
```python
r = create_protagonist(conn, {"concept": "head of the Basile family", "holdings": [{"kind": "outfit", "name": canon_outfit}]}, "s1")
assert r["displaced"]["reason"] and seat_holder(conn, canon_outfit) == me
assert members_of(conn, canon_outfit) == members_before and rivals_of(conn, canon_outfit)   # it keeps its history
assert create_protagonist(conn2, {"concept": "mayor of Saint Jude"}, "s2")["displaced"]
assert veto_refuses_during_play(conn, take_held_seat)                                        # opening only
for start in ("mechanic", "businessman", "politician", "boss"):
    s = start_check(start, days=30)
    assert s["circle"]["kin"] and s["circle"]["friends"]         # a personal life at every scale
    assert s["personal_nominations"] and s["city_events"]         # his life moves, and so does the city
    if start in ("politician", "boss"): assert s["seat_decisions"]
    assert not all_single(s["circle"]["friends"], age_band=(22, 30))  # a plausible opening (5.2)
    assert {"cause_share", "events_per_kind", "never_fired"} <= set(s["measures"])   # never_fired is [] until Task 17a
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus touched modules, commit. The lead reads the
  four reports, and `start_check.py` runs again before Deploy 2.

### Task 15: Channels, shocks, delayed effects and turning events

**Files:**
- Create: `engine/channels.py`
- Modify: `connector/authoring.py` (`kind="turning_event"`)
- Modify: `engine/rollback.py` and `connector/correct.py` (`undo_chain`, moved here from Task 6), and
  `connector/rulebook_core.md` (how to use turning events)
- Modify: `worlds/saintjude/levels.json` (`shocks`)
- Revision 4.1: `exposure_links` gains the kind `competitor` (same trade, same district). When his business takes
  work, demand moves from his competitors as a shock on their channel, with the cause. His own businesses and his
  crew are channels attached to him, so a shock to them reaches him.
- Revision 5, reuse first: `attached` reads the tables that already hold the links (businesses and employment,
  outfit membership and rackets, households, loans and `money_records`), and `exposure_links` holds only what
  none of them records. Effects go through the existing money, ledger and `claims` paths.
- Test: `tests/channels_shocks_test.py` (also: his shop's growth shows up as a demand shock on a rival in the same
  district, and a rival owner with a concern from it is a mover or notable)

**Interfaces:**
- Produces:
  - `attached(conn, channel_kind, channel_id) -> list[(actor_id, link)]`, where `link` is one of `employee`, `owner`,
    `member`, `resident`, `regular`, `debt`, `supplier`, `protection` or `customer`;
  - `publish(conn, shock_id) -> list[{"actor_id", "effect", "felt": bool, "knows_cause": bool}]`. A felt effect changes real
    state (money, takings, demand) through the existing paths (revision 5.2). Knowing the cause takes a path: he is the owner, or someone told
    him. Delayed effects become `scheduled_effects` rows on the same chain.
- **Acute shocks open concerns straight away.** A felt effect at or above `acute_shock_line`, on someone `notable` or
  `active`, opens a concern at once (`origin_kind='exposure'`, on the shock's chain). Slow build-up stays for active
  people only (Task 16). This is how Carla's father, who is notable, has something on his mind after the squeeze.
- **The bridge to the protagonist.** `publish` first writes what each affected person knows of it into his own
  knowledge (`basis` felt or saw). It then picks carriers as the contract says: the affected person, if tied to the
  protagonist (kin, friend, close per `close_rule`, or the object of a live concern of his); otherwise a household
  member or close kin of the affected person who is tied to him. Carla is the carrier for her father's shop: she
  learns it at home (`basis` told), and a `pending_news` row is written with her as carrier and the protagonist as
  recipient, `urgent` set per `urgent_kinds`, on the chain. The gate (Task 10a) delivers it from there. Nobody else's
  news is created.
- `turning_event` checks: every channel resolves; the event doesn't contradict ownership or state (closing a business
  already closed, a fire at a place that doesn't exist); recent shocks on the same channels within 365 days give a
  consequence note. Commit: a `causal_chains` row (`origin_kind='turning_event'`), then `channel_shocks`, then
  `publish`.

- [ ] **Step 1: Write the failing test:**
```python
sid = shock(conn, "business", bakery, "takings_down", 0.4)
effects = channels.publish(conn, sid)
assert {e["actor_id"] for e in effects} == attached_ids(conn, "business", bakery)
assert any(e["felt"] and not e["knows_cause"] for e in effects)            # feels it without knowing why
assert concern_of(conn, notable_owner, origin_kind="exposure")              # acute shock: a concern at once
assert pending_news_for(conn, me, carrier=carla, chain=chain_of_shock(sid))          # two hops: her father's shop
assert knowledge_of(conn, carla, shock_key)["basis"] == "told"                     # she heard it at home
assert not pending_news_for(conn, me, carrier=stranger_employee)            # no tie, no news
assert same_chain_via_record_changes(conn, sid, takings_change(conn, bakery))        # the real state change
out = server.author("t1", "turning_event", {"channels": [{"kind": "business", "name": "Rizzo's Bakery"}],
                                            "shock": "fire", "summary": "a kitchen fire closes Rizzo's for a month"})
assert chain_of(out)["origin_kind"] == "turning_event" and pending_effects(conn, chain_of(out)["id"])
assert server.author("t2", "turning_event", {..., "channels": [{"kind": "business", "name": "No Such Shop"}]})["status"] == "refused"
assert any(a["kind"] == "consequence" for a in server.author("t3", "turning_event", {second fire, same street})["answers"])
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 16: Pressure build-up and concerns

**Files:**
- Create: `engine/pressure.py`
- Modify: `engine/levels_tick.py` (from Task 14a: add `pressure.build` and due `scheduled_effects`)
- Modify: `worlds/saintjude/levels.json` (`pressures`: `cash_strain` from cash against weekly household need;
  `work_restless` from time in the same work at a low wage relative to his trade; `office_threat` for office
  holders, from a challenger's standing and the next election's date)
- Test: `tests/pressure_buildup_test.py`

**Interfaces:**
- Produces:
  - `build(conn, day, actor_ids) -> list[concern_id]` for active people (revision 5: a plain package line, no
    accumulator). Each week it reads the existing values (cash against need, weeks in the same low-paid work, the
    challenger's standing). When a condition has held past the package's line, it opens a concern with
    `origin_kind='buildup'` and an `origin_text` naming the condition and how long it has held ("four months short
    of the rent"). People differ only through what is already recorded about them: savings, kin who can help,
    temperament in `actor_drives`.
  - The concern closes when its condition is gone. No cooldowns, adaptation, resignation or mood.
  - `levels_tick.process_due` (Task 14a) gains `pressure.build` and due `scheduled_effects`. Task 17b adds
    `offscreen.fire_due`.

- [ ] **Step 1: Write the failing test:**
```python
for p in ten_close_people_same_age_and_cash(conn): starve_cash(conn, p)
weeks_to_tip = run_weeks_until_concern(conn, people, max_weeks=40)   # same cash, different savings and kin
assert len(set(weeks_to_tip.values())) > 1                  # what is on record about them makes the difference
c = concern(conn, people[0]); assert c["origin_kind"] == "buildup" and "month" in c["origin_text"]
pay_rent(conn, people[0]); run_weeks(conn, 1); assert concern(conn, people[0])["status"] == 'resolved'
assert not concerns_for(conn, a_materialized_minor)        # only level 3 builds this way
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 17a: Offscreen weighing

**Files:**
- Create: `engine/offscreen.py` (`weigh` only)
- Modify: `worlds/saintjude/levels.json` (`actions`: first contents `seek_income`, `ask_loan`, `call_in_debt`,
  `avoid`, `confront`, `pressure_business`, `make_offer`, `settle`, `do_nothing`)
- Test: `tests/offscreen_weigh_test.py`

**Interfaces:**
- Produces:
  - `weigh(conn, actor_id, day, why) -> decision_id | None`. It is called when a concern opens, a waited-on date
    arrives, or a shock hits him.
  - Revision 5, a short pick: the options are the package actions that serve the concern and whose needs he meets,
    plus `do_nothing`. One is picked by temperament (`actor_drives`) and habit weight, with a little noise. No mood,
    no competing-concern arithmetic, no stored scores.
  - When `do_nothing` is picked, the concern is marked `waiting`.
  - Every weighing writes an `offscreen_evaluations` row with the chosen action and a plain reason only.

- [ ] **Step 1: Write the failing test:**
```python
d = offscreen.weigh(conn, frank, day, "concern opened")     # Frank: needs money, hates his job, mother ill
assert decision(conn, d)["reason"] and evaluation(conn, frank)["reason"]          # every choice stores why
choices = [offscreen.weigh(fork(conn, seed), frank, day, "x") for seed in range(20)]
assert len({decision(c)["action"] if c else "do_nothing" for c in choices}) >= 2   # not always the optimum
assert share(actions_of(choices_of(hothead)), "confront") > share(actions_of(choices_of(meek)), "confront")  # temperament
assert evaluation_when_nothing_won(conn)["chosen_action"] == "do_nothing"
assert offscreen.weigh(conn, me, day, "x") is None and not evaluations_for(conn, me)  # never for the protagonist
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 17b: Decisions falling due, and offers

**Files:**
- Modify: `engine/offscreen.py` (`fire_due`) and `engine/levels_tick.py` (register it)
- Modify: `engine/hearsay.py` (`waiting` includes pending decisions with `offer_to_actor_id` = him and `told_day` set)
- Test: `tests/offscreen_fire_test.py`

**Interfaces:**
- Consumes: Task 17a's decisions; Task 15's `publish` for `pressure_business`.
- Produces:
  - `fire_due(conn, day) -> list[decision_id]` carries out due decisions through existing engine effects (loans and
    payments through money records, obligations, ties, a `channel_shock` for `pressure_business`), all on one causal
    chain under `rollback.current`.
  - A fired decision aimed at an active person opens a concern for him (`origin_kind='other_act'`).
  - A due decision by or aimed at someone `near` him becomes a nomination (Task 14), with the decision as its
    cause. Far from him it fires as an engine act.
  - An offer whose `expires_day` passes lapses or escalates only if `told_day` is set.
  - A `stated` decision from a scene fires on its due day as the stamp says. If no engine effect fits, it becomes a
    `waiting_on_you` matter for the GM to play.

- [ ] **Step 1: Write the failing test:**
```python
d = pending_decision(conn, mover, "pressure_business", target=shop, due=day + 3); run_days(conn, 4)
assert decision(conn, d)["status"] == "fired" and shock_on(conn, shop, chain=decision(conn, d)["causal_chain_id"])
loan = pending_decision(conn, frank, "ask_loan", target=me_friend_active, due=day + 1); run_days(conn, 2)
assert concern_of(conn, me_friend_active, origin_kind="other_act")
offer = make_offer_to_me(conn, frank, expires_in=7, told=False); run_days(conn, 10)
assert decision(conn, offer)["status"] == "pending"         # untold offers don't lapse
offer2 = make_offer_to_me(conn, frank, expires_in=7, told=True); run_days(conn, 10)
assert decision(conn, offer2)["status"] in ("lapsed", "fired")
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run with `--quick`, commit.

### Task 17c: Noticing (Deploy 2; formerly Task 15b)

**Files:**
- Modify: `engine/offscreen.py` and `engine/levels_tick.py` (a knowledge row about a person reaching a mover opens
  a `wants` concern about him when the package's `noticing` rule says the fact is useful to that mover. It runs each
  week over every `active` mover, outfit captains included (revision 5.3).)
- Modify: `worlds/saintjude/levels.json` (`noticing`: which facts interest which mover roles)
- Test: `tests/noticing_test.py`

**Interfaces:**
- Each weighing either follows up or stores why not (`offscreen_evaluations`), so silence is always a stored fact
  with a cause.
- Revision 5.3: the outfit code owns outfit agendas. Noticing him is personal, and it runs for captains too.
- Revision 5.4: the concern's `strength` comes from the package's `noticing` weight for that kind of fact (a
  threat is above an opportunity, which is above mild interest). `weigh` takes the strongest live concern first.
- How a mover learned is itself recorded (`carrier_actor_id`, `path_kind`).
- Revision 4.2: `noticing` maps each kind of fact to interest, opportunity or threat for each mover role, adjusted by
  his circumstances. The follow-up actions are `look_into`, `ask_about`, `send_someone`, `offer_work`, `invite`,
  `test_him` and `leave_be` (deliberate, with its reason). They join the package actions of Task 17a and are
  picked the same short way (revision 5).

- [ ] **Step 1: Write the failing test:**
```python
tell(conn, captain, about=me, fact="does good work on cars", via=a_customer_in_his_crew)
run_weeks(conn, 6)
c = concern_about(conn, captain, me); assert c and c["origin_kind"] == "noticed"
assert followed_up(conn, captain, me) or evaluation_reason(conn, captain, c)   # follow-up, or silence with a cause
assert knowledge_of(conn, captain, "good work")["carrier_actor_id"] == a_customer_in_his_crew
assert strength(concern_about(conn, captain_told_rival_work, me)) > strength(c)  # a threat weighs more than good work
assert len(followup_kinds_over_seeds(conn, captain, me, seeds=20)) >= 2       # not always an offer or pressure
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus touched modules, commit.

### Task 18a: (folded into Task 14d)

Revision 5.2: the three world measures are part of `tools/start_check.py` (Task 14d). There is no separate scorer.

### Task 18b: One mover, the ten-step chain, absence and the routine run

**Files:**
- Revision 5.2: no second mover path for outfits. The kept `outfit_choices` acts for the outfit and emits a
  `channel_shocks` row for a squeeze, and opens the `causal_chains` row it sits on (revision 5.3). `offscreen.py`
  handles personal plans for every mover, and the plans of movers outside outfits.
- Modify: `engine/outfit_choices.py` (a squeeze on a business writes a `channel_shocks` row on the outfit's chain)
- Create: `tests/levels_chain_test.py`, `tests/levels_life_test.py` (slow: add to `tests/slow_tests.txt`)
- Test: both files above

**Interfaces:**
- Consumes: Tasks 10, 11, 14d, 15, 16, 17a and 17b.

- [ ] **Step 1: Write the chain test** (`levels_chain_test.py`), one assertion per step of design section 10.4:
```python
outfit = a captain's outfit; give it an organization_pressures row (collections short)
run_weeks(conn, 8)
c = outfit_choice_on(conn, outfit);                         assert c                                    # 1 the outfit's own aim
d = c;                                                      assert d["action"] == "squeeze"             # 2 decides
shock = shock_of(conn, d);                                  assert shock["channel_id"] == carlas_fathers_shop  # 3
p = concern_of(conn, carlas_father, origin_kind="exposure"); assert p                                 # 4
# 5: shop trouble isn't urgent, and Carla doesn't share his household or routine, so it waits with her
h = pending_news_for(conn, me, carrier=carla, chain=shock["causal_chain_id"]); assert h and not h["delivered_day"]
b = brief_with(server, carla);                              assert "has_news_for_you" in dump(b)        # 6 she has it
server.act(...player responds...); r = server.close_scene(...)                                          # 7
n = knowledge_of(conn, me, shock_key);                      assert n["path_kind"] == "told" and n["carrier_actor_id"] == carla  # 8
b2 = brief_with(server, carlas_father);                     assert "on_their_mind" in dump(b2)          # his worry, later
run_weeks(conn, 4);                                         assert world_moved_on(conn, outfit)         # 9, 10
assert same_chain(conn, c, d, shock, p, n)                  # one chain from origin to news
```
- [ ] **Step 2: Write the life test** (`levels_life_test.py`): a fresh save run 120 days with only routine acts, then
  `start_check.py`'s measures; assert C1 (every level-3 event has a cause), that there's at least one courtship step, one
  business change and one organisation aim pursued, and no doubled consequence. Add the three absence tests:
  1. 60 days away: the city changed for its own reasons;
  2. his return: a carrier holds news for him and nothing is dumped as a summary;
  3. an important day without him: a wedding or vote happens and doesn't reach him without a path.
  Run one year at most.
  Revision 4.2 adds two checks:
  - **A political start** (revision 5.1: run through Task 14d's `start_check.py --start politician`): a fresh save
    with the protagonist as a ward councilman made through `new_character`.
    The same 120 days must give him at least one nomination from his circle, and a rival office holder must pursue
    an aim of his own (`office_threat`).
  - **Report, don't assert:** the lead reads from `causal_chains` whether any chain crosses from one mover's act
    into another's concern.
    Full competing agendas come with steps 6 to 8.
- [ ] **Step 3: Run both.** Expected: FAIL until the mover wiring is in.
- [ ] **Step 4: Implement** the mover wiring. Run both, then `--quick`.
- [ ] **Step 5: Commit.** The lead reads the life run and runs `start_check.py` for all four starts.

---

### Task 18c: Business state (Deploy 2)

**Files:**
- Create: `tools/business_probe.py` (first measure what today's business code does over 120 days: customers, payments,
  demand, capacity)
- Modify: the business modules the probe names (revision 5.2: no drawn paying habits; demand follows reputation, rivals and neglect, with the cause stored; capacity against workload is computed)
- Modify: `worlds/saintjude/business.json` (demand drivers)
- Modify: `connector/brief.py` (his business in `money`: backlog, turned-away work, who owes what)
- Test: `tests/business_mix_test.py`

**Interfaces:**
- The GM invents the haggling, the breakdowns and the customers' faces. The engine holds who pays how, what is
  owed, why demand moved, and when he is over capacity.

- [ ] **Step 1:** run the probe and report to the lead before writing the test. Revision 5.3: it reports the share
  of credit agreements and customer payments that go `late` over 120 days. If the share skews late, tune the
  existing odds in the business code. Add no per-customer model.
- Revision 5.3: also add the spread row for a sustained rise in his business's work (from Task 10a).
- [ ] **Step 2: Write the failing test:**
```python
late_once(conn, customer); assert brief_present_of(server, customer)["owes_or_paid_late"]   # remembered from money records
good_work(conn, me, weeks=8); assert demand_cause(conn, me_shop)["kind"] == "reputation"
overload(conn, me_shop); assert brief_money(server)["turned_away"] > 0
quiet_month(conn, me_shop); assert demand_cause(conn, me_shop)                # nothing arrives, with a reason
# revision 4.2: capacity and slumps become his decisions, with causes in the world
overload(conn, me_shop, weeks=3); assert waiting_on_you_has(server, "turning work away")
undercut(conn, rival, me_shop); assert discoverable(conn, me, cause="undercut", via=a_customer_or_supplier)
```
- [ ] **Step 3 to 5:** implement, run the task's test plus touched modules, commit.

### Task 18d: The protagonist's death or long sentence (Deploy 2)

Revision 5.2 (owner): firm in Deploy 2.

**Files:**
- Modify: the health and law paths that can end his play: the tie-break where survival and death are both
  plausible, his death, and a sentence longer than the package's `long_sentence_days`
- Modify: `connector/server.py` (`resume` on a save whose protagonist is dead offers a successor. It is built with
  the GM through `new_character`, among his kin or circle or a newcomer. The save goes on.)
- Test: `tests/protagonist_end_test.py`

- [ ] **Step 1: Write the failing test:**
```python
assert outcome_when_both_plausible(conn, me, "gunshot") == "survives"
kill(conn, me); run_days(conn, 30)
assert city_moved_on(conn) and kin_grieve(conn, me)                     # the world carries on
r = server.resume(); assert r["protagonist"] == "dead" and "successor" in r
```
- [ ] **Step 2 to 5:** run (FAIL), implement, run the task's test plus touched modules, commit.

## Phase E: build step 5

### Task 19: Deploy and the owner's playtest (lead)

This runs twice: after Task 14d (Deploy 1) and after Task 18d (Deploy 2). See Delivery and cost.
- [ ] Back up the VM saves (`/var/lib/caerness/backups/pre-levels-<date>/`), check integrity, then deploy the branch.
- [ ] Start a fresh Saint Jude save. Dominic's old save is not migrated for play.
- [ ] The owner plays an evening, then a stretch of several game weeks. Nothing is staged to show off features.
  Revision 5.2: Deploy 1's playtest judges the GM–engine loop, nominations, the news gate and the four starts.
  The city's reactions are judged in Deploy 2.
- [ ] The lead runs `gm_check.py` on the playtest transcript.
- [ ] Faults go through the scoring sheet. Each fix goes to the task that owns the code.
- [ ] Once the slice is proven, delete the old feeds behind `news_gate` (owner's yes first). Then write the plan for
  steps 6 to 8.
