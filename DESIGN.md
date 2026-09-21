# v0.26.1 pre-RC integration note

The architectural principles below remain authoritative. v0.26.1 adds the product/integration layer needed to carry them into a v1.0 release candidate: a production bootstrap, versioned save migrations, save-safe testing, explicit mirrored-field ownership checks, phone-facing setup/inspection/diagnostics, domain-to-decision adapters, and realistic-scale 20/40/120-year validation. Historical crystallization is explicitly actor-first for v1.0.

---

# Caerness Simulation Design v0.7

## Governing premise

> **The player is the story's camera focus, not the world's protagonist or causal center.**

The purpose of the engine is not to generate a theme park that wakes up around one adventurer. It is to maintain a society with its own chronology, institutions, conflicts, economies, information flows and regional pressures, then let the player experience one path through that society.

A useful test is:

> If the player character were removed from the database for a year, would Caerness still produce a plausible year of history?

v0.7 treats the answer as an engine invariant, not merely a narrative preference.

## 1. Authority layers

### Canon

Slow-changing facts: geography, Vein rules, culture, institutions and historical background. The current World Bible is indexed for retrieval.

### State

What is true now: actor locations, goals, resources, pressures, relationships, agreements, threads, clocks, regional metrics and process accumulators.

### History

What happened: immutable events, actor decisions, interaction actions, player actions and turns.

### Knowledge

What an actor believes or has learned. Truth events, rumours and provenance remain separate.

### Camera

What the player can currently witness or plausibly know. Scene packets are a view onto the world, not the world itself.

## 2. Simulation resolution is not narrative importance

Actors have `ACTIVE`, `STRATEGIC`, and `DORMANT` simulation profiles.

- **ACTIVE** — high-resolution review cadence.
- **STRATEGIC** — slower but regular strategic decisions.
- **DORMANT** — coarse decisions and background development.

These tiers describe computational resolution. They do **not** mean protagonist relevance.

A Dormant clan can start a war while the player is elsewhere. An Active shopkeeper can remain irrelevant to continental politics. A severe incoming event can temporarily promote a Dormant actor because the *world* requires more resolution, not because the player looked at it.

## 3. Dormant never means frozen

A Dormant actor still participates through four independent mechanisms:

1. continuous background processes;
2. exact scheduled clocks;
3. coarse strategic decisions;
4. incoming and outgoing social interactions.

v0.5 added a fifth observer-independent layer: **regional/world processes**.

## 4. Regional processes

`world_processes` belong to locations rather than actors. They allow slow changes such as future examples of:

- trade pressure;
- migration;
- road safety;
- harvest conditions;
- criminal pressure;
- court unrest;
- ecological change;
- cultivation-resource depletion or recovery.

The current engine ships only demo processes. Canon-specific processes should be added as the World Bible develops.

Each process has:

- location;
- cadence;
- direction/rate;
- volatility;
- optional location metric;
- event threshold;
- event severity.

They run at world checkpoints and catch up at the terminal day. No player, faction or named NPC needs to be present for them to change.

## 5. Player-action boundary

A player input passes through three conceptual layers:

```text
raw player text
  -> action interpretation
  -> validation against persisted state
  -> authoritative resolution
```

The model/interpreter is allowed to propose intent. It is not allowed to mutate state directly.

The deterministic v0.6 adapter recognizes observation, waiting, travel, conversation, investigation and explicit responses to pending social interactions. Anything more complicated is recorded as `needs_interpretation` instead of being invented.

This is intentional. It is safer for continuity to say "the resolver needs a richer interpretation" than to silently create a new person, location, possession or outcome.

## 6. Shared time

The player does not own a separate adventure clock.

Travel and waiting advance the same `world_state.current_day` used by every actor, clock, agreement, rumour and world process.

Therefore:

```text
player travels six days
    -> six days pass for everyone
    -> due NPC decisions happen
    -> due interactions resolve
    -> clocks fire
    -> regional processes move
    -> information travels
    -> player arrives
```

The system currently uses whole-day granularity. Finer scene-time can be added later without changing the causal principle.

## 7. Travel

Travel is validated through the persisted undirected `location_links` graph. The engine finds the shortest known route and uses the route's travel-day cost.

A location cannot be reached merely because a narrator says so. Unknown/unconnected travel becomes `needs_interpretation` until geography is supplied or a richer resolver proposes a legal route.

The player's location is changed only after elapsed world time has been simulated.

## 8. Conversation and social interaction

A direct player conversation with a persisted actor who is physically present creates a causal `conversation` interaction and lets the NPC side resolve its response from its own state.

The player controls only their own approach. They do not decide how the other person reacts.

NPC conversations do not automatically create contracts or agreements.

## 9. Explicit responses to NPC offers

Incoming player interactions never auto-answer themselves. The player can explicitly:

- accept;
- reject;
- counter.

The response is persisted as a `player_action` and then applied to the existing interaction. Any resulting agreement or public consequence receives causal provenance.

Situations such as an incoming attack are not treated as an offer the player can simply "reject." They remain for future scene/tactical resolution.

## 10. Information after time passage

The simulation may generate many off-screen events during one player action. Their IDs are retained in the private turn audit for debugging and provenance.

The narrator does **not** receive those hidden event summaries.

After the action resolves, the information system determines which events the player directly knows and which rumours have plausibly reached the new location. Only those enter the post-action scene packet.

This allows the player to discover history rather than receiving omniscient patch notes.

## 11. Scene packets are reads, not activation triggers

Creating a scene packet can update only information exposure that the player plausibly receives at that location. It does not alter simulation tier or create NPC goals.

Hard rule:

> **Camera attention has no causal privilege.**

No actor becomes important because the player entered the room. No distant faction waits motionless until its name appears in narration.

## 12. Anti-protagonist-gravity rule

Future decision providers and narrators must obey these constraints:

1. Do not target the player merely because a player exists.
2. Require a causal bridge: relationship, witnessed event, reputation, possession, shared location, contract, investigation, factional interest, or another persisted reason.
3. Do not reroute unrelated major events toward the player's location for convenience.
4. Do not make every rumour secretly relevant to the player's arc.
5. Let important NPCs have meetings, victories, failures, marriages, debts, promotions, deaths and feuds that the player may never witness.
6. The player may become historically important if their actions earn that importance.

This is the difference between **camera focus** and **chosen-one gravity**.

## 13. Narration envelope

The authoritative play loop creates both a pre-action and post-action scene packet. A narrator receives:

- the player's raw input;
- the resolved player-action result;
- player-safe scene state before and after;
- explicit narration guardrails.

It does not receive unrestricted SQLite state.

A narrator can make prose vivid. It cannot decide that an NPC secretly changed allegiance, a clan lost money, or a new war began unless the engine has already persisted that change.

## 14. Turn/history model

`player_actions` stores interpreted and resolved player intent.

`turns` links:

- raw player input;
- action record;
- day started/ended;
- pre/post scene packets;
- audit IDs for off-screen events generated during elapsed time;
- narrator output.

This gives the campaign a reproducible causal trail.

## 15. Canon safety

Demo actors, channels and world processes are prefixed `[DEMO]` and are not setting canon. The engine never invents permanent Caerness institutions merely because a test needs data.

Canon retrieval provides evidence but does not fill absent facts.

## 16. Existing systems retained from v0.1-v0.4

v0.6 preserves:

- canonical document indexing and retrieval;
- actor goals, pressures, resources and drives;
- simulation tiers and temporary wake-up;
- decisions;
- NPC-to-NPC interactions;
- agreements and conflict threads;
- event provenance;
- public/private/secret information policies;
- rumours and route-based propagation;
- information channels;
- player knowledge boundaries;
- scene anti-omniscience rules.

## 17. Tests that specifically protect the living-world premise

The v0.6 test suite checks that:

- a 90-day player wait advances remote regional state;
- a Dunmoor process creates world events while the player remains in Toll's Reach;
- travel advances global time and then moves the player;
- looking at a scene does not wake a Dormant actor;
- the world continues producing decisions and world events with no configured player at all;
- unknown player actions do not create guessed permanent state;
- explicit player interaction responses are never chosen autonomously.

## 18. Next technical milestone

v0.6 should connect richer model-backed adapters to the existing safe boundaries rather than replacing them. Priority areas:

- schema-validated LLM action interpretation;
- model-backed NPC decision proposals using actor context packets;
- model-backed narration using narration envelopes;
- richer scene-scale social resolution;
- eventually a dedicated tactical/combat resolver;
- finer-than-day time if actual play proves it necessary.

The non-negotiable invariant remains:

> **Caerness lives first. The camera merely follows one person through it.**

---

# v0.6 — Model Gateway Architecture

## 19. Models are replaceable reasoning components, not the engine

v0.6 formalizes a model gateway with three bounded task classes:

1. `action_interpretation` — interpret what the player is trying to do; never resolve success.
2. `npc_decision` — propose one decision for a persisted actor from its private actor context.
3. `narration` — turn an already-resolved player-safe narration envelope into prose.

Every model request is persisted before it leaves the engine. Every response is persisted before it is applied. The resulting history remains auditable.

## 20. Manual ChatGPT / Claude is first-class

The gateway treats ordinary web/app chats as valid model providers through exportable Markdown packets. This avoids requiring an OpenAI or Anthropic API subscription on top of the user's existing chat access.

The provider changes packet presentation only. Both return the same engine contract, so a pending request can be re-exported from ChatGPT to Claude or vice versa without changing world state.

## 21. Manual models never freeze Caerness

Routine world simulation remains rules-based by default. A manual model request is used only where the user deliberately asks for higher-quality reasoning/narration or where freeform player intent cannot be safely interpreted by the deterministic adapter.

Therefore a pending ChatGPT/Claude request cannot stop distant clocks, dormant actors or regional processes unless the unresolved request is specifically the player's current action and world time has not yet advanced. Off-screen simulation itself never depends on a human being present to answer model prompts.

## 22. Action interpretation is pre-state

If deterministic parsing cannot represent a player action, the bridge creates an `action_interpretation` request **before** any player-action state mutation or time advancement. A returned interpretation is converted back into the normal `PlayerActionProposal` and revalidated against persisted actors, locations, routes and interactions.

If the response names something absent or ambiguous, the action remains unapplied.

## 23. Narration is post-state

For a grounded action, the engine completes:

```text
player choice -> validation -> consequences -> elapsed world time -> off-screen simulation -> information propagation -> post-scene
```

before creating a narration request. ChatGPT/Claude cannot use prose to retroactively create a war, move a character, alter an agreement, or reveal hidden events.

## 24. NPC model decisions are exceptional resolution, not global dependency

`model-decide` can elevate one strategically important NPC decision to ChatGPT/Claude. The response must use persisted goals/pressures/targets and an allowed decision type. Applying it passes through the existing `apply_decision` engine.

The default background decision provider remains heuristic/rules-based. This keeps the world alive even when no LLM is connected.

## 25. Spoiler separation

A player-facing narration/action chat should receive only camera-safe packets. An NPC-decision packet can contain private actor goals, pressures and relationships and should therefore be treated as a separate "world mind" channel if the player wants spoiler-blind play.

The architecture deliberately makes it possible to use one ChatGPT/Claude conversation for the camera and another for world simulation.

## 26. Future adapters

Local models and optional paid APIs can be added behind this same request/validation interface later. They should not change the database schema or authority model.


# v0.7 — Mobile, Emergence, Competence, and Agency

## 27. The six player-experience principles

### 27.1 Camera Principle

> **The player is the story's camera focus, not the world's protagonist or causal center.**

Camera attention never activates a faction, makes an enemy easier, delays a distant event, or creates a reason for an unrelated NPC to care about the player.

### 27.2 Emergent Story Principle

> **Caerness does not generate plots. It generates circumstances, consequences, and continuity from which plots can emerge.**

The authored part of the game is the fertile soil: institutions, geography, martial rules, obligations, resources, customs, personalities, information networks, and causal pressures. The engine lets those systems collide. It may recognize that several events have become a coherent developing thread, but recognition grants no authority to force a dramatic next beat.

A recurring rival should recur because shared roads, factions, relationships, offices, contracts, or consequences reconnect the characters—not because a narrative director decides a rival is due for Act III.

### 27.3 Earned Outcome Principle

> **The camera may be lucky about what it gets to see. It is not lucky about what happens next.**

A small main-character feeling may exist primarily through opportunity: the camera can encounter unusually interesting possibilities. Once the player acts, important outcomes are not secretly hedged toward success.

Future combat, health, economic, and social resolution must allow:

- defeat;
- serious injury and long recovery;
- loss of wealth, employment, reputation, status, allies, or opportunities;
- imprisonment or other durable setbacks where the setting supports them;
- being genuinely down on one's luck;
- character death.

The simulation should not treat tragedy as a broken campaign. A dead player character may eventually become one historical person in a world that can continue under a new camera character.

### 27.4 Experienced World Principle

> **The World Bible establishes what is true. Play determines what becomes known.**

The player should experience major worldbuilding through participation before encyclopedia-style explanation whenever practical. A cultural rule is stronger when it changes who bows, who speaks first, or what an insult costs. A financial institution is stronger when its terms constrain later options. A thin-current region is stronger when recovery changes there.

Lore is a reward for investment, not homework required before investment.

The database may know objective truth while characters possess perspectives. The UI should therefore prefer sourced claims and evidence over omniscient conclusions.

### 27.5 Character Competence Principle

> **The player controls decisions. The character handles competence.**

The player should not lose opportunities because they failed to micromanage something their character obviously remembers or physically possesses.

Persisted intentions and obligations can trigger when their conditions become true. Routine fulfillment is automatic. If circumstances changed enough that following the old intention becomes a meaningful new choice, control returns to the player.

Example:

```text
character agreed to deliver letter
+ letter remains in possession
+ intended recipient is now present
+ no meaningful contradictory circumstance
= character hands over letter without player retyping it
```

If the recipient has become an enemy, ownership is disputed, the player explicitly suspended the plan, or another meaningful complication exists, the engine surfaces the decision instead.

Reminders are part of competence, not a separate gamey quest system. Journals and ledgers are reference tools, not substitutes for human memory.

### 27.6 Agency Handoff Principle

> **A scene ends when fiction changes beat. A player turn ends when meaningful agency becomes useful.**

Caerness does not return control merely because an LLM generation, paragraph, or fictional scene ended.

There are three handoff states:

- `none` — established intent can continue without meaningful loss of agency;
- `open` — the situation is rich enough that the player may reasonably want to choose a direction, even though nobody is requesting a decision;
- `hard` — continuing would resolve a meaningful choice on the player's behalf.

A player handoff does not need a question. Normal narration should not end with **“What do you do?”**. The prose ends naturally; the persistent input field is sufficient.

The engine must also support interruption. A player may notice something that the handoff heuristic did not recognize as important. Automatic progression therefore stops at the nearest safe causal boundary when interrupted.

> **The narrator does not ask the player to act. It gives them a world worth acting in.**

## 28. Technical generation boundaries are invisible

One player-facing section may contain multiple fictional scenes and multiple local-model calls.

Example:

```text
departure
  -> ordinary road travel
  -> several days pass while world simulation advances
  -> arrival
  -> open agency handoff
```

On the OnePlus 12, the local narrator may produce this as three bounded generations to keep memory/output load comfortable. Those chunks are joined before presentation. The player never has to type `continue` simply because the local model reached an output limit.

The engine stores `narrative_segments` and `agency_checkpoints` so future UI/runtime code can separate fictional beats from player-turn boundaries.

## 29. Emergence Layer

`actor_memories` records significant consequences in structured form so later NPC behavior does not depend on an LLM remembering old prose.

A memory contains:

- the remembering actor;
- optional subject actor;
- a stable key;
- event/interaction/etc. source;
- summary;
- optional interpretation;
- valence;
- significance;
- creation and reinforcement dates.

Actors can therefore carry forward the fact that somebody defeated, aided, humiliated, betrayed, vouched for, or imposed a cost on them when those events are persisted.

`thread_evidence` lets real events reinforce existing threads. The engine may create a neutral “developing situation” thread when several related consequences recur. Such a thread is an index over history, not a script.

Hard restriction:

> **Emergence recognition has zero authority to alter an outcome merely because another outcome would make a better story.**

## 30. Rhythm without director cheating

Emergent narrative benefits from peaks, aftermath, and ordinary life. Caerness should permit quiet travel, work, study, recovery, conversations, and days where nothing protagonist-shaped happens.

The engine should not, however, weaken a real crisis simply because the player's recent scenes were difficult. Rhythm can arise from:

- actor/resource exhaustion;
- institutional decision cadence;
- travel and communication delay;
- recovery periods;
- seasonal/civic cycles;
- conflict dynamics;
- camera focus choosing to spend time on quieter parts of life.

The world is not obligated to provide a breather if the character deliberately remains inside an escalating war.

## 31. Scene Quality Router

The router separates four questions that AI-agent play often conflates:

1. How difficult is the reasoning?
2. How valuable would stronger prose be?
3. How much context is required?
4. How hard is this request on the current phone profile?

The OnePlus 12 / 12 GB default uses:

```text
comfortable local context: 4096 estimated tokens
heavy local context:       6144 estimated tokens
```

A route assessment can recommend:

- rules;
- local;
- local-heavy;
- external recommended;
- external strongly recommended.

The recommendation is advisory. The player can always force local execution. The UI explains whether the recommendation is primarily about reasoning, prose quality, or phone load.

LLM self-reported confidence is not used as the primary signal. The engine relies on observable task complexity, context size, persisted stakes, and validation failure.

## 32. Local model architecture

v0.7 adds a provider-neutral local HTTP client.

`openai_compatible` is the preferred interface because it can sit in front of llama.cpp and other local runtimes without coupling Caerness to one vendor.

`ollama_native` is an optional adapter.

The authority boundary remains identical across local, ChatGPT, and Claude:

```text
model interprets / proposes / narrates
engine validates
SQLite owns world truth
```

A stronger model is a quality service, not a different ruleset.

## 33. OnePlus 12 / 12 GB profile

The phone is treated as a constrained but capable simulation host.

Design assumptions:

- rules and SQLite handle most background activity;
- a 3B–4B quantized instruct model is the comfortable local baseline;
- larger models are optional rather than required;
- canon is retrieved in small relevant chunks;
- long narration may be split across several model calls;
- external referral exists for rare heavy scenes;
- CPU-compatible local inference is the baseline; GPU acceleration is optimization, not correctness.

## 34. Story time only

v0.7 explicitly sets `realtime_calendar_progression=0`.

Closing the app for ten real days advances zero Caerness days.

If a player action consumes ten in-world days, those ten days are lived by the entire simulation before the camera resumes.

This preserves a living independent world without punishing the player for not opening the game.

## 35. Player-facing information architecture

The engine may know everything. The interface may show only what the character could reasonably know, remember, infer, possess, or access.

The initial mobile UI uses four spaces:

- **Scene** — current narrative camera;
- **Matters** — intentions and obligations;
- **World** — known people, known places, and sourced claims;
- **You** — character/runtime reference.

Player-facing world information should preserve provenance where possible:

```text
claim
source
learned date
confidence
verification / directness
source location
```

The UI must not expose hidden goal scores, secret faction plans, or raw relationship numbers.

People pages should privilege shared history over invisible affinity meters. Place pages should reflect actual knowledge rather than reveal the entire simulation map. An eventual formal in-world Ledger can exist as one source among others rather than functioning as God's stat screen.

## 36. Contextual popups

The player should not be required to repeatedly open a journal merely to remember obligations that their character would naturally be thinking about.

`attention_cues` support:

- approaching obligations;
- overdue obligations;
- automatic competence follow-through;
- meaningful competence forks;
- future knowledge/situational warnings.

In the mobile UI they are transient contextual notices. The underlying obligation/intention remains in `Matters` after the popup has been shown.

This avoids both extremes:

- no reminders, causing artificial player-memory failures;
- a permanent quest HUD that turns every obligation into a videogame objective.

## 37. Mobile runtime

The phone UI is served on localhost by the standard-library HTTP server. v0.7 deliberately has no network authentication and therefore defaults to `127.0.0.1` only.

The mobile composition is:

```text
browser/PWA
  -> localhost Caerness server
  -> SQLite + simulation
  -> local model endpoint
```

The input box remains present instead of narration repeatedly asking for action. A referral modal can copy either a ChatGPT or Claude bridge packet to the clipboard. A returned structured response can be pasted/imported back into the same phone interface.

## 38. Save integrity and versioning

v0.7 introduces engine version `0.7.0`, a migration path for v0.6 model-request provider constraints, WAL mode, and consistent SQLite backups.

Important transitions remain transactional. Narration is disposable presentation; history is permanent state.

Regenerating prose must not reroll the underlying decision/event.

The backup system is designed around rotating local database copies, with an automatic default cadence of every ten committed turns in the mobile runtime.

## 39. Development/admin observability

Spoiler-blind play and simulation debugging are separate modes of access.

Normal UI receives only player-safe information. Developer/admin commands may inspect:

- world pulse;
- events;
- decisions;
- interactions;
- memories;
- emergent threads;
- route assessments;
- raw actor contexts.

This is necessary to answer the development question:

> Is Caerness actually alive off-camera, or is it merely producing prose that sounds alive?

## 40. v0.7 boundary

v0.7 establishes the runtime and interaction philosophy but does not yet contain the finished Caerness campaign population, tactical combat system, detailed injury system, full economic inventory, or final social-resolution engine.

Those future systems must inherit these constraints rather than bypass them.

The next milestone can now safely focus on campaign bootstrap and richer scene-scale resolution because the underlying rules for world independence, player competence, model routing, information, and agency handoff are explicit and tested.


---

# v0.8 — Continuity and Historical Substrate

## 41. Purpose

v0.8 does not replace v0.7. It adds the persistence structures required by the post-v0.7 architecture while retaining the existing authority boundary:

```text
model interprets / proposes / narrates
engine validates
SQLite owns world truth
```

The new governing continuity rule is:

> **The engine may economize on resolution, never on causality or continuity.**

## 42. Continuity cores and anchors

`continuity_cores` store minimum persistent state for people, places, possessions, threads, and cohorts. `historical_anchors` store turning points that later reconstruction must respect. Routine years need not be simulated scene by scene; material consequences do.

> **Persist consequences. Compress routine.**

## 43. Broader resolution metadata

The v0.7 actor scheduler remains `ACTIVE / STRATEGIC / DORMANT`. v0.8 adds a separate conceptual resolution layer for entities:

```text
SCENE
ACTIVE
TRACKED
STRUCTURAL
LATENT
```

This layer describes how much persistent detail an entity currently receives. It does not replace actor simulation cadence and it does not encode narrative importance. Resolution transitions are historical and auditable.

## 44. Cohorts and institutions as compression nodes

Cohorts carry shared generational history. Institutions carry pipelines, culture, capacity, succession, and accumulated reputation. Together they let a fifty-year-old newly encountered character inherit a plausible historical context without requiring fifty years of individual scene simulation.

## 45. Careers are trajectories

`career_tracks`, `career_stages`, and `actor_careers` let professions change with age and experience rather than remaining one static occupation tag. Apprenticeship, practice, leadership, retirement, and career change can all be represented as historical state.

## 46. Objective history vs public history

Existing `events` remain objective world-history facts. v0.8 adds `public_narratives` and `documentary_records` so public belief and surviving records can diverge from objective truth without corrupting it.

## 47. Latent existence

`latent_entities` represent structurally existing but not yet individually instantiated people or other populations.

> **Latent does not mean newly created. It means previously undescribed.**

The next milestone is a historical crystallization service that turns those constraints into individual biographies when causal relevance requires them.

---

# v0.9 — Historical Crystallization

## 41. Latent does not mean newly created

v0.9 operationalizes the post-v0.7 rule:

> **Latent does not mean newly created. It means previously undescribed.**

A latent person pool can now be promoted into an individually persistent actor without pretending that the person began existing when the camera noticed them.

## 42. Freeze constraints before generation

Historical crystallization is two-stage:

```text
latent pool + established world history
    -> persisted crystallization context
    -> biography proposal
    -> validation
    -> authoritative application
```

The context is persisted before the proposal is generated. This prevents a model from quietly broadening the relevant past after seeing what would be convenient in the current scene.

## 43. Identity-facing, not plot-facing

> **Newly crystallized history should primarily explain the entity that already exists, not conveniently solve the protagonist's current problem.**

Strong connections to already-existing actors require explicit persisted historical basis such as a cohort, institution, event, prior anchor, record, or relationship.

## 44. Progressive depth

`shallow`, `developed`, and `deep` crystallization impose different anchor budgets. A first meeting therefore does not require an exhaustive life history. Further detail can be crystallized later as long as it remains consistent with existing anchors.

## 45. Campaign history only

Applied crystallization writes campaign truth. It never silently promotes generated biography into setting canon.

## 46. Auditability

Each run retains:
- frozen context;
- proposal;
- validation result;
- applied entity;
- lineage connecting generated facts to their historical basis.

Once applied, the new actor participates in ordinary v0.7/v0.8 state, history, relationships, careers, information, resolution, and simulation rules.


---

# v0.10 — Character Embodiment

## 47. Persistent protagonist model

v0.10 implements the post-v0.7 rule:

> **The protagonist is still a character when the player is not directly puppeteering every sentence and gesture.**

`character_embodiment` stores persistent voice, temperament, values, habits, social behavior, relationship style, current state, development assumptions, and expression policy. This model is campaign state, not narrator memory.

## 48. Player wording is usually intent

Speech has three input modes:

```text
intent   -> meaning/objective/tone, character chooses expression
guided   -> preserve supplied phrases where practical, character fills the rest
exact    -> preserve the player's words
```

The renderer should not infer that a protagonist is simple, blunt, elegant, awkward, or verbose merely because the player typed that way.

## 49. Expression/commitment boundary

> **Character expression can be autonomous. Major character commitment generally cannot.**

Low-stakes behavior may be inferred when strongly supported by established character state. Examples include a habitual greeting, a glare, a dry aside, or familiar body language.

Major commitments return to player agency. The commitment firewall explicitly protects decisions such as oaths, marriage, betrayal, declarations of war, execution of important prisoners, permanent allegiance, major confessions, and comparable irreversible choices.

The firewall returns one of:

```text
allow  -> strong character support + low stakes
ask    -> plausible but consequential or insufficiently certain
block  -> too uncertain or a major/irreversible commitment
```

## 50. Relationship-sensitive expression

Personality is relational rather than globally uniform. Embodiment packets may include coarse relationship cues for actors presently involved in the scene. The narrator receives qualitative bands rather than hidden raw trust/stance numbers.

A character may therefore be rude to strangers and patient with a child, confident professionally and awkward intimately, or ruthless in war and restrained at home without being treated as inconsistent.

## 51. No caricature rule

Persistent traits create behavioral inertia, not a catchphrase generator.

> **Consistency is not repetition. Personality is not caricature.**

Recent expression history is available so later renderers can avoid repeating the same gesture every scene merely because it is characteristic.

## 52. Narration remains non-authoritative

Embodiment data is added to player-safe scene packets and narration envelopes. It improves how already-resolved scenes are expressed. It cannot create permanent state, relationships, promises, possessions, or outcomes in prose.

The v0.7 authority boundary remains unchanged:

```text
model interprets / proposes / narrates
engine validates
SQLite owns world truth
```

## 53. Next milestone

The next implementation target is **competence interpretation**: domain-specific competence profiles, professional readings of complex situations, advisor separation, and actionable interpretation for players who do not personally possess their character's specialist knowledge.


# v0.11 — Competence Interpretation

## 41. Domain expertise

> **The player supplies intention and judgment; the character supplies professional understanding and execution appropriate to their actual competence.**

Competence is domain-specific. Martial ability does not imply command skill; political office does not imply commercial judgment; wealth does not imply cultural expertise. A character may have multiple competence entries and specialties.

## 42. Professional reading contract

A professional reading is an interpretation of evidence the character can access. It records competence, evidence, stakes, uncertainty, and a bounded confidence ceiling before any prose interpretation is accepted.

The resolver must preserve:

```text
direct observation
!= report
!= character inference
!= advisor judgment
!= player decision
```

Higher expertise allows deeper pattern recognition and better framing of options. It never grants omniscience. Missing evidence remains missing evidence.

## 43. Actionable interpretation

The purpose of competence mediation is not to dump technical detail. It should translate complexity into the kind of decision support the character would naturally possess: likely implications, major risks, important unknowns, and plausible professional approaches.

A deliberate player decision remains authoritative even when the character recognizes it as poor judgment. The engine may warn; it may not silently substitute a better choice.

## 44. Advisor separation

Advisor opinions belong to named actors and may be biased, mistaken, self-interested, or simply different. Only communicated judgments are player-facing. Advisor judgment is not merged into objective world truth or into the protagonist's personal competence.

## 45. Runtime relationship

`professional_context` is now included in scene and narration packets. This extends v0.7's Character Competence Principle while preserving the existing information firewall and post-state narration rule.

The next target is the time-skip resolver: compressed world advancement with protagonist intentions, obligations, delegation, interruption thresholds, and historical anchors.


# v0.12 — Compressed Time With Agency Preservation

## 41. Time skips are simulation, not date arithmetic

A multi-month or multi-year skip advances the same authoritative world clock as ordinary travel and waiting. The protagonist specifies broad focus and may delegate areas of responsibility. Background actors, interactions, clocks, regional processes, information propagation, and existing deterministic systems continue normally.

> **Compression ends where consequential player choice begins.**

## 42. Transactional preview

To avoid advancing thirty days past an event that should have stopped the player on day seven, the resolver previews bounded chunks inside a SQLite savepoint. If a meaningful interruption appears, the preview is rolled back and replayed only to the earliest interruption day. The committed world therefore never skips past an agency boundary merely because compression was requested.

Current interrupt candidates include severe directly relevant events, consequential incoming interactions, important non-routine obligations, and competence forks. Delegated obligations/interaction types may be allowed to continue without returning control.

## 43. Focus is evidence, not free advancement

A time-skip focus records how much of the elapsed period was devoted to a domain or career. This accumulates structured experience evidence. It does not automatically raise competence scores, award promotions, or decide career success. Those outcomes belong to later domain/career resolvers.

## 44. Quiet time is allowed to complete

If no meaningful interruption occurs, a long period may simply complete. The world still advances off-camera. The engine must not manufacture a crisis merely because a player asked to spend a year training, working, building a household, or pursuing ordinary professional life.


# v0.13 — Battle and Duel Resolution

## 45. Battle is a system, not a protagonist duel

A battle is resolved through persistent sides and units with command, morale, cohesion, readiness, fatigue, logistics, information quality, reserves, momentum, objectives, and subordinate agency. Personal importance does not collapse the battlefield into a single hero contest.

> **Major battle outcomes emerge from the whole battlefield. The protagonist can alter local or strategic conditions according to their actual role, but the rest of the army continues to exist and act.**

## 46. Rank-sensitive agency

A player who controls a side receives a strategic intent boundary. A player who commands one unit receives a local intent boundary. A player who merely observes the battle does not receive command authority.

The player does not need to supply technical formations, weapon instructions, or doctrinal minutiae. High-level battle intents are currently:

```text
hold / probe / press / reposition / reinforce / commit_reserve / recover / disengage
```

The resolver translates those intentions through command competence, unit condition, subordinate judgment, and world state.

## 47. Subordinate agency

> **A commander controls through people, not puppetry.**

Subordinate units act automatically within delegated intent. Their commander competence, fatigue, morale, role, and local condition may cause them to hold, support, recover, commit, reposition, or disengage without requiring separate player orders for every unit.

This extends the broader delegation principle: greater responsibility should create higher-level decisions rather than administrative spam.

## 48. Battlefield information

Battle views are actor-relative.

A side controller can see a broad view of their own forces and only such enemy detail as their information quality and command competence support. A unit commander receives a local view centered on their own unit. Hidden enemy values are never exposed merely because the database knows them.

> **Battle resolution may be objective; battlefield perception is not omniscient.**

## 49. Duel intent and embodied expertise

Duels expose high-level intentions rather than asking the player to write technically correct weapon exchanges. Current intents are:

```text
measure / press / defend / conserve / commit / control / disengage
```

The internal exchange considers martial competence, readiness, stamina, composure, reserve, momentum, risk, and commitment.

> **The duel loop is perception → player intent → character execution → changed state → new perception.**

Opponent state is presented as the character's reading rather than exact hidden numbers.

## 50. Combat outcome boundary

The v0.13 resolver determines abstract battle and duel continuation states such as engaged, strained, withdrawing, withdrawn, broken, defeated, victorious, or disengaged. It does not yet model detailed wounds or medical aftermath. Those consequences belong to the future health/injury resolver so combat logic does not invent anatomy ad hoc.

Per-round deterministic seeds ensure that narration regeneration cannot reroll already-resolved combat truth.

## 51. Authority relationship

The v0.7 rule remains unchanged:

```text
player/model proposes intent
engine validates role and state
combat resolver persists the outcome
narrator describes the already-resolved result
```

The next implementation target is **civilian simulation**: careers, households, economy, textiles, culture, architecture, auctions, provenance, and underworld overlap.



# v0.14 — Multi-front Battle Flow

The v0.13 resolver established authoritative abstract combat. v0.14 corrects its main structural weakness: a major battle cannot be represented only by one aggregate contest between whole sides.

## Fronts

Battles may contain persistent `battle_zones`. Units are assigned to a zone, where local pressure and initiative evolve independently. A side can therefore be secure in one area and under severe pressure in another.

## Command hierarchy

`battle_command_links` represent senior/junior command relationships, communication quality, discretion, and trust. `battle_orders` take time to become effective. A subordinate is an agent, not a remote-controlled unit.

## Reports

`battle_reports` separate objective battle state from what high command currently knows. Reports store observation time, availability time, confidence, and source context.

## Turning points

`battle_turning_points` are persisted consequences of state changes. Recognition of a turning point cannot retroactively change the battle.

## Local heroic effects

Individual feats may create bounded local confidence effects through `local_shock`. v0.15 extends this with contextual personal-combat consequences: a duel can become operationally or strategically decisive only when the people, position, command structure, replacement depth, and existing battle state make that causal.

## Generalship

`battle_command_profiles` allow broad differences in planning, adaptation, presence, delegation, and nerve without treating one command score as the whole person.

## Knowledge boundary

The simulation can know all active fronts. The player sees only the information appropriate to their command role and reports that have plausibly arrived.

The v0.14 battle invariant is:

> **A battle is a network of local contests, command relationships, delayed information, and accumulating pressures whose interaction produces the strategic result.**


# v0.15 — Tactical Grammar and Vein Battlefield Logic

## Tactical families

The engine now recognizes pressure, fixing, misdirection, isolation, depth, reserve play, mobility, attrition, disruption, and exploitation as abstract command families. They modify trade-offs and opportunity costs rather than functioning as pre-authored special moves. Commander doctrine supplies preferences; current battle context can pull decisions away from those preferences.

> **Learn tactical grammar, not tactical scripts.**

## Vein assets

Cultivators can be represented as persistent battlefield assets with Stage, reserve, readiness, role, commitment, and zone assignment. Their influence is deliberately separate from command competence. Current-rich or stable ground can improve sustainability without granting higher-stage abilities.

This creates Caerness-specific problems of concentration, distribution, exhaustion, current geography, and reserve timing without turning a powerful cultivator into an army replacement.

## Personal combat consequence

The v0.14 local-only rule is superseded by:

> **Personal combat changes the battlefield through the strategic value of the people, positions, resources, and command structures involved. A duel may be trivial, locally important, operationally decisive, or in exceptional circumstances strategically decisive—but never merely because it was a duel.**

The resolver considers Stage, zone importance, command significance, replacement depth, and current side fragility. A strategic personal loss can trigger an already-precarious side to break; it does not grant automatic victory from duel status alone.

> **Heroic consequence without heroic determinism.**


# v0.16 — Civilian Simulation Core

The civilian layer now shares the authoritative world clock. Households, enterprises, markets, production, careers, projects, cultural objects, provenance, auctions and shadow-market pressures are persisted state rather than narrator inventions.

> **Peaceful life must be simulated as causally as war.**

The initial resolver is deliberately aggregate-first. It provides real causal substrate for merchant, craft, artistic, architectural, household and collecting play without requiring exhaustive bookkeeping. Profession-specific depth can be added behind these same authority boundaries.


# v0.17 — Civilian Life Depth

## 54. Built environment is persistent social infrastructure

Buildings are no longer implied only by project completion. Residences, halls, workshops, shops, warehouses, public buildings, bridges, gardens and other durable works can persist as objects with ownership, location, style, prestige, utility, condition and maintenance burden. A completed architectural project may create such a record.

> **Architecture should outlive the scene that built it.**

Maintenance is intentionally coarse. The engine tracks whether resources exist to keep a building in usable condition and allows neglected structures to become strained or derelict without turning play into facilities management.

## 55. Style spreads socially, not globally

A fashion or artistic style is a historical current with a place of origin and uneven local adoption. Prestige, novelty, accessibility, craft capacity, elite support and local resistance shape diffusion. Styles may become established, decline or revive. A style appearing in Cairnholt does not make every city dress the same way.

> **Culture moves through people, workshops, status and imitation rather than global unlocks.**

## 56. Households have succession history

Households may define a succession method and designated heir, while other members may possess competing claims. The resolver chooses from explicit designation or claim strength and records whether the result is contested. It does not manufacture claims to create drama.

When a household head actually becomes deceased, a settled succession can resolve automatically. Personal cultural property can transfer with an inherited provenance record, preserving the object's historical life.

## 57. Credit creates durable obligations

Commercial credit is represented as a persisted agreement between actors and/or enterprises. Interest accrues through story time, due dates can be missed, and default affects the borrower's enterprise state. Payments reduce both the agreement and enterprise debt.

The model is intentionally accounting-light but causally real.

> **Credit should create future constraints, not merely explain present wealth.**

## 58. Partnership separates ownership from control

Enterprise partners persist ownership share, governance weight, role and capital committed. These values need not be identical: a minority owner can have substantial managerial authority, and a capital-heavy investor can have limited day-to-day control.

## 59. Professional institutions create careers without scripted promotion

Professional memberships link people to institutions independently of their abstract career track. Membership records role, standing, influence and seniority. Long service and strong standing may make someone eligible for review, but eligibility never automatically grants an office.

> **Institutions create pathways and bottlenecks; they do not turn elapsed time into destiny.**

## 60. v0.17 authority boundary

All v0.17 systems are campaign-history mechanisms. They can fill ordinary historical detail inside a campaign, but they do not silently establish universal setting canon. SQLite remains authoritative, and narration may describe only persisted or player-safe derived consequences.


# v0.18 — Business Ecology

The enterprise layer now separates broad legal/economic containers from behavioral archetypes. Business archetypes are engine vocabulary, not declarations that a location canonically contains those businesses. Local commercial context supplies foot traffic, travelers, wealth, trade, elite patronage, cultural activity, credit demand, military/health/craft/construction demand, regulation, security and event activity.

> **Business type must change causal behavior, not merely change a label.**

Configured businesses resolve recurring operating cycles through story time. Those cycles persist utilization, demand, revenue, cost and net income and write to existing enterprise accounts. Archetype weights make different enterprises respond differently to the same city, while later demographic/ecological/political passes can change the city conditions themselves.

---

# v0.19 — Household and Generational Life

v0.19 closes the contradiction identified by the depth audit: the engine could previously resolve inheritance after a household head died but could not reliably produce or track the generations whose inheritance mattered.

The new invariant is:

> **Households persist through changing people; people persist through changing households. Kinship, dependency, residence, and service are related but distinct facts.**

A second agency invariant applies to family life:

> **Major commitments such as marriage or forming a family are never inferred merely from elapsed time. Routine consequences may be simulated only after the relevant commitment already exists as campaign history.**

Named families use persistent life profiles and kinship. Large populations remain aggregate until causality requires crystallization. Health/mortality is intentionally reserved for v0.20 so that demographic and medical causality have one authoritative owner.

---

# v0.20 — Health authority

Health is persistent causal state, not a combat-ready/dead toggle. Aging, illness, injury, Vessel pathology, recovery, disability, treatment, adaptation and mortality are resolved by `engine/health.py`.

Cultivation extends the prime before lifespan. Longevity classes use the World Bible's rough ranges as tonal anchors rather than scheduled death dates. Higher Stage can preserve recovery and function longer, but does not erase injury history or guarantee survival.

Rupture is anatomical Vessel failure. Ordinary care can support the body; specialist Vein treatment is required for strong direct recovery modifiers on serious Channel/Core/Rupture pathology.

The camera receives authoritative capacity through `health_context`; the narrator may describe consequences but cannot invent or erase conditions in prose.

## v0.21 — Religion and Cultural Institutions

Religion is modeled as lived social reality rather than faction alignment. The simulation separates tradition, personal affiliation, organized institution, office, calendar observance, attendance, obligation, sacred place, patronage, and reputation. This permits household rites without centralized priesthood, organized religious institutions where appropriate, overlapping social practice, and exclusive theological claims without collapsing every person into one global alignment field.

The shared civil calendar is settled: day 0 is 1 First Month, 624 SV in a fixed 365-day year. The engine still seeds no universal feast schedule because local religious/civic observances remain regional and partly latent until canon or campaign causality establishes them.

Cultural institutions are persistent actors rather than event vending machines. Their prestige, resources, reach, programs, patrons, and continuity can develop off-camera. Patronage moves actual funds. Public programs create historical instances and can exert bounded influence on an already-existing local style movement.

Religious office seniority is historical evidence, not automatic promotion. Institutional careers remain agent- and institution-dependent.

## v0.22 — Ecology, Seasons, Travel & Environmental Pressure

v0.22 turns environment from descriptive context into authoritative constraints while preserving unresolved geography.

Core rule:

> Established geography constrains movement. Unestablished geography remains latent rather than being filled in for convenience.

Locations may have explicit environmental profiles and recurring seasonal windows, but the engine seeds none. Temporary conditions represent established environmental pressure without requiring a universal weather simulator. Route travel resolves segment by segment through a campaign-defined graph, and recalculates at intermediate nodes so later conditions can matter.

Ambient Current is modeled environmentally through density, stability, replenishment, breadth, concentration, carrying capacity and recoverable load. Heavy use can temporarily exceed local sustainable conditions; recovery is a story-time process rather than a hard reset.

Environment crosses subsystem boundaries only through bounded interfaces: production receives an ecological factor; markets receive environmental transport pressure; travel can generate abstract exposure; health retains ownership of bodily resolution. Scheduled household migration now uses routes whenever route geography exists, preventing a lower-resolution subsystem from bypassing higher-resolution established facts.

# v0.23 — Political state and macro-history

Politics is now authoritative campaign state rather than immutable setting wallpaper.

> **Resolution may change the political map. Continuity must preserve how it changed.**

Polities are institution-backed and can outlive rulers and dynasties. Territory, claims, interstate relations, hierarchy, and succession are distinct facts. A ruler's death does not dissolve a state; a state's dissolution cannot orphan territory; a territorial claim does not equal territorial control.

Political change can occur off-camera through established claims, succession structures and campaign-configured structural processes. The system has no balance-restoration rule: a state may expand, contract, federate, fragment, become subordinate, survive, or disappear if campaign causality supports it.

The political history ledger is append-only so successor states and changed borders remain historically reconstructable.


# v0.24 — Education, Transmission & Institutional Reproduction

Education is persistent causality rather than an explanation added after someone becomes important. Lower-stage and professional competence should have provenance: teachers, institutions, practice, access, and elapsed story time.

> **A manual transmits information. A teacher transmits practiced understanding. Time and embodied work turn either into competence. None of them alone manufactures mastery.**

The engine therefore separates programs, teaching relationships, knowledge assets, custody/access, transmission lines, and competence outcomes. Institutional reproduction is measured through real pipeline health rather than balance restoration: an institution can lose teachers, fail to replace a lineage, preserve an archive without living practice, or remain strong because its instructor depth and recruitment structures actually persist.

Personal master–disciple relationships remain socially heavier than ordinary instruction. Multiple ordinary teachers are normal, and multiple true masters are possible but explicit. Training never silently creates a master bond.

Institutional successor candidates may become eligible through persisted readiness, legitimacy and transmission depth, but eligibility never chooses them. Major succession remains a meaningful institutional act.


# v0.25 — Long-Run Simulation & Stress Testing

The final pre-consolidation domain is not another world system; it is verification across all existing systems. Long-run tests use the same authoritative story clock as ordinary play. Checkpoint snapshots and contradiction scans make failures inspectable rather than merely producing a final pass/fail.

> **Long-run simulation may change resolution and relevance. It may not erase causal continuity.**

Narrative-camera succession is explicit campaign state. A camera character may die without ending the world; a successor is used only when previously designated or explicitly chosen. Family inheritance, political succession and camera succession remain separate concepts.

The stress layer is diagnostic rather than self-balancing. It does not rescue weak institutions, regenerate populations by fiat, preserve borders, or create adversity to make successful campaigns interesting.
