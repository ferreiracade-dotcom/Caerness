# Information, press and reputation: design

Date: 2026-11-20. Status: draft for the owner's approval. Cross-cutting design, written so the mob, business and politics spheres of Saint Jude (`2026-11-19-saintjude-three-spheres-design.md`), the prison design (`2026-11-20-prison-design.md`) and later worlds all use it. Companion to the population tiers (`2026-09-26-population-tiers-design.md`): background, notable and named tiers and the B/C depth rule apply here unchanged.

## 1. Intent and why

The owner's own words, kept as the test of whether this works:

- Reputation, standing and **people reacting to what the character does** is the favourite part of the game. The owner wants it developed, and wants it to be what **builds the character**.
- The model case: a capo or family head is charged, it goes on the news, and a **wave** follows. The GM writes reactions from people who are not in the scene, what the newspaper says, what the anchor says. These are cutaways; the character cannot know them and the GM marks them so.
- The same applies to **presence**: a family head has men outside his house and a driver; people stand when he walks in; someone kisses the ring. A politician has security. People read how he dresses, his car and his men. A shop attendant who thinks little of a man in a plain coat treats him differently after he spends freely. **It is dynamic, within a scene and across years.**
- The biggest complaint about play before the engine: the owner had to **ask** for reactions, news, deference, the crew's formation, the dress and the car. That made them feel manufactured instead of authentic even when plausible. **Nothing in this design may require the player to ask.**
- **NPCs live under the same rules.** An NPC gets news about himself, reacts to it, turns up with a pose, security and a nice car, and goes on a shopping spree when he is flush. No special treatment for the player or for named characters.

The press is a set of institutions and people, not a background carrier. The owner wants it at **B depth always and C depth where the player goes**. The owner is unlikely to play a reporter or anchor, but may play the **owner of a paper or TV station**; politicians and mobsters connect to the press in their own ways (an interview, a rat planted in the newsroom, a bribe). The reporter's role stays possible and must not need a rewrite.

## 2. Current state (verified in the code, 2026-11-20)

- **Information spread** (`engine/information.py`, tables `events`, `event_witnesses`, `knowledge`, `rumours`, `rumour_locations`, `rumour_transmissions`, `rumour_exposures`): events get a visibility (public, limited, private, secret), secrecy, rumourability and reliability; they become rumours that travel place to place with distortion and reach; actors learn them as `knowledge` rows (belief text, confidence, link to the truth event); minor unrepeated rumours fade (PERF-01). This is word of mouth and is a sound base.
- **Reputation** (`engine/reputation.py`, table `social_reputation`): one 0 to 100 value per subject and domain. The only real reader is `martial_instruction_public`; `standing.py` uses a fame threshold. Nothing in the org core, law or business reads it. It has no audience, no source, no decay.
- **Standing** (`engine/standing.py`): per-observer words from kin, rank, relationship axes (stance, trust, fear, resentment, respect) and fame. Public roles only; secret roles are never read off a person. This is the right voice and is extended, not replaced.
- **Law and mob**: `informs` and `busted` happenings (`engine/org_happenings.py`) open `crime_reports` and cases; `record_view` shows custody under the firewall. The prison design adds prosecutors with ambition, juries and witnesses as people.
- **Media**: none in the engine. Saint Jude bible §11 lists the *Daily Mirror*, the *Chronicle*, the *Courier*, two ethnic weeklies, the student paper, three TV affiliates, a public station, a UHF independent and radio, as Fixed text only. Part III §2 (Courtesy and Ceremony) has the deference customs for the mob.
- **Presence and display**: nothing makes a scene show rank. A few mentions of escorts and honorifics exist (`career_reach`, `role_experience`); none produces a retinue, a way of dressing or a way of being greeted.
- **Delivery to the GM**: no record of what the player has been shown, so nothing stops a wave being dropped or repeated.

## 3. Goals

1. A **wave** follows every significant public happening: the engine decides who hears what, when, through which channel, how it is twisted and how each audience reacts. The GM writes it, including cutaways.
2. **Reputation is claims held by people and by audiences**, with source, confidence and decay, not a score.
3. **Standing is visible**: retinue, forms of deference, dress, car, company, spending. Strangers read these signals; the reading updates live as the scene goes on.
4. **Pushed, never asked for.** Every `scene`, `advance` and `resume` carries what the character's situation naturally shows, including **news about other people that reaches him**; a delivery ledger tracks what has been shown.
5. **Press as institutions** with owner, editor, reporters, politics, debts, reach and cadence; a story pipeline with gatekeeping; printed stories stay on record.
6. **The player can fight, steer or stay neutral**, depending on where the news comes from, who the character is and when he hears it: all plausibility. Press owner is a playable seat; the reporter role is possible later.
7. **NPCs run the same machinery**: they get news about themselves, manage an image, display wealth and react.
8. **It feeds the other systems**: law, politics, business and the mob (section 7.6).
9. **It generalises**: packages supply media, audiences, customs and signals as data (section 7.8).

## 4. Non-goals and anti-goals

- **No closed lists, ladders or ceilings.** No fixed list of reputation traits, audiences or press actions. The GM proposes; the engine vetoes named contradictions (an established fact, a canon rule) and nothing else.
- **Rates are calibration targets, not rules.** Real-world rates (stories killed, time for a story to cross a city, how often an editor holds an indictment, how much a wave moves belief) are targets the builder *reports after a run* and reaches by tuning weighed drivers. They are **never shares, quotas, clamps or caps**. Nothing in code or data says "at most X% of stories are killed", no outcome has a fixed distribution, and there is no outcome menu. This is written down on purpose because earlier work kept turning targets into hard caps.
- **No single reputation number** driving behaviour, and no number shown to the player. Words and behaviour only.
- **No world words in `engine/`.** Saint Jude's papers, customs and signals live in `worlds/saintjude/` data; builders are generic.
- **The engine never writes prose.** The GM never decides outcomes the engine has not returned.
- **No manufactured reactions.** The failure to avoid: the player asking for reactions the world should have produced. Needing to ask is counted as a defect.
- **Not a reporter simulator** in its first form; the data supports it later.
- **No special treatment** for the protagonist or named characters. The protagonist is always a new non-canon character; real figures appear only in their public roles.
- **No minute-by-minute simulation of every reader** or every conversation as the base layer.

## 5. Constraints

- Standing rules: engine = memory, plausibility and world; Claude = the GM; play happens through the claude.ai connector, often on a phone, so answers must be fast. Packages are data only. B depth everywhere, C depth where the player goes. Rare things stay rare; where life and death are both plausible lean to life; conscience follows the character's own beliefs; a time-skip keeps routine and is interrupted by real events.
- Source canon: Saint Jude bible §11 (media), Part III §2 (Courtesy and Ceremony; deference, the street as a stage), the "silent keeps standing, talks loses it" rule, "a man's family is his reputation", Part II (informants, WITSEC), and the prison design. The *Mirror*'s union press schedule is Fixed.
- Another session edits `engine/org_*.py`, `engine/outfit_*.py` and `worlds/saintjude/` data now. This work extends the org core and does not fork it. Business and politics do not exist yet: the press and its owner hooks must work from the org core alone and gain more when those spheres land.
- Performance: B on the existing weekly grid, one pass per institution not per reader; crowds are aggregates; C is local to the scene.
- **Cost target (measured and reported, as the other tasks do).** The texture block rides on every `scene`, `advance` and `resume`, and play happens on a phone. A scene call's added time on the VM stays under a figure the builder measures and reports, and any weekly B pass costs at most 1.15x the current week. Crowds stay aggregate and the room read is computed only for the people in the scene. Like every rate here, the figure is a reported target and a tuning goal, never a clamp that cuts content.
- Real facts about 1975 (libel standard for public figures, shield-law position, FOIA) are **[verify]** items for the builder; this document does not assert them.

## 6. Approaches considered

- **1. A stored score per audience.** Add an audience column to `social_reputation`. Cheap and fast, but detached from who actually knows what: it cannot give a room read, say *why* someone behaves as they do, or tell a believed claim from a true one, and it drifts into a tuned number. Rejected.
- **2. Derived only from individual beliefs.** No stored score; reputation is what each person knows. Faithful, but too heavy for a paper's 400,000 readers or a rally of civilians, who are mostly unnamed. Rejected as the only layer.
- **3. Hybrid (chosen by the owner).** Named and notable people hold real, individual beliefs with a source and confidence; crowds hold an aggregate impression per audience; each can shape the other. Matches the approved tier model and the B/C depth rule. Cost: the largest build of the three.

## 7. Design

### 7.1 Claims and audiences (phase 1)

- A **claim** is a free-text statement about a subject ("will not talk", "pays on time", "snaps when slighted", "takes envelopes"), held by a person or an audience, with: source (saw it, was told by X, read it in Y, inferred from a signal), confidence, the day, and a link to the truth when there is one. Claims about the same subject stand alone; a known killer can be known as honest. The GM proposes claims; the engine vetoes only contradictions with established fact. There is no list of traits.
- **Named and notable people** hold individual claims about the subject (extends `knowledge`). They update from what they witness, what they are told (discounted by the teller's credibility, motive and relationship), what they read, and what they infer from signals.
- **Crowds** hold an **impression per audience**: the aggregate of a story's reach and framing into a group. An **audience** is anything the package data defines: a neighbourhood, an outfit, a trade, a parish, an ethnic community, a paper's readership, an electorate. No closed list.
- A crowd's impression and a named person's belief can disagree (a hostile paper meets a loyal street). Each can shape the other: a named man's belief draws on his audience's impression, and a famous man's act moves the audience.
- **Realism drivers** (all weighed, none caps): a costly act is believed more than talk; second-hand claims are discounted; bad news sticks harder and trust is built slowly and lost fast; people close to the subject resist bad news and rivals spread it; reputation decays with social distance and with time unless reinforced; deterrence is a reputation function (answering a slight partly to avoid looking weak); a claim spills onto family and outfit; stigma persists after the facts fade; reputation is access (offers, recruits, tips, favours come to a name).
- **Two kinds of standing, one connection.** B12 gave every org seat a `standing` value (`org_seats.standing`); discipline, the books, nominations and B12b's succession weighing all read it. Here standing comes from claims. They connect like this: **seat standing becomes the outfit's own audience impression of the man**, built from the claims its members hold about him and kept as the derived value the org layers read (the same way `social_reputation` stays a derived summary). The org layers do not change what they read; what feeds the value changes. Without this the head could trust a man the street knows is skimming.
- **The personal circle is an audience of its own**: wife and children (the kids at school), parents, neighbours, the parish priest and the congregation. These are the reactions closest to home, and where a man's name costs him most. The owner is weighing faith and conviction in the mob storyline, so the parish and the family carry real weight in the claims and in how a wave lands.
- **The principle: a man's reputation reaches everyone connected to him, through any channel plausible for the era and place.** Wife and children are the clearest case, but it holds for any relative, friend or associate. Each of those people is **reacted to in their own life**, and the reactions are driven by the same claims and drivers, with **no list of situations**. The school and the shopping below are illustrations only.
  - *Illustrations.* The children's classmates see the father on the news, or hear it from their own parents, and say something to the kids at school. The wife is recognised and reacted to on her own: at the shops, at church, by other wives. That can mean fear, deference, a cold shoulder, a free cut of meat, or whispering.
  - These happen in the connected people's **own off-screen days, at B depth, and they come home**: a child comes back upset or proud, a wife tells him what was said, a teacher calls.
  - **The player does not see this only second-hand.** It can be **first-hand** when he is there (at the school gate, shopping with his wife, at a christening, when another father pulls his child away), **a cutaway marked outside his knowledge**, or **reported to him at home**. Which it is follows where the player is and what play reaches. The engine supplies the happening and who was present; the GM plays it.
  - They arrive as pushed texture through the same ledger, never asked for. The reactions follow from the claims each audience holds (the parents at the school, the parish, the shopkeepers) and **spill onto the connected person through the existing family-spill driver**.
  - The same machinery runs for **NPCs and NPC families**: a rival's son is taunted at school too.
- `social_reputation` is not migrated away: it remains the summary the existing martial reader uses and is kept consistent as a derived value. Existing readers do not move.

### 7.2 Presence, bearing and the room read (phase 1)

- The engine returns a **bearing** for the player and for any notable person in the scene: **retinue** (who attends: guards, driver, secretary, aides, walking order), **forms of deference** the package's customs and the observers' beliefs make apt, **signals** worn or arriving with (dress, car, jewellery, company, table, house), and **spending**.
- The engine returns a **room read** on scene entry: each notable person's stance toward the subject, where it comes from (saw it, heard it, read it, inferred it from a signal), and how sure; crowds as an audience impression. The GM plays the behaviour (people stand, make way, address him by title, come to kiss the ring, avoid his eye). The character perceives behaviour; the GM may show the cause only where the character could plausibly infer it.
- **Strangers read signals.** A man nobody knows is read from his car, clothes and men. A real boss in a cardigan may be unrecognised; a pretender who dresses and arrives like one may be believed until tested.
- **Dynamic, within the scene and over time.** First impressions are guesses from signals and update on evidence: the attendant who sniffed at the plain coat treats him differently after he spends freely; a deed confirms or breaks the signal; a rumour makes people reconsider. Display follows belief, so a head whose men have lost faith still gets the forms, but sullen or thinner, and display can **lag the truth** until the first man does not stand. This makes deference something that can be lost in public and tested by rivals.
- **Display comes from real things.** Dress, car, house and retinue come from what the character actually owns and pays for: assets, the money ledger and his men. It is not a free description. Where nothing is recorded, the GM proposes it and **the engine records it so it persists** (no silent bucket; the car he arrived in is the car he has next week). A display **beyond his means is plausible but costs him**: it draws debt, envy and attention, and it can be noticed and read as a front.
- Fame has costs: loss of anonymity, being recognised on the street, being unable to go somewhere unnoticed.
- Reputation is also a **constraint**: a man known never to forgive pays a cost for letting something go. His name makes some actions plausible and others expensive.
- Extends `standing()`; keeps its rule that secret roles are never read off a person.

### 7.3 Pushed, never asked for (phase 1, binding requirement)

- Every `scene`, `advance` and `resume` carries a **texture block** for the player's situation, as facts: bearing, room read, running waves, and recent public happenings that touch him. The GM weaves it into the prose and never announces it as a feature.
- A **delivery ledger** records what has been shown to the player. An unshown wave persists and is returned again at the next call; a shown one is not repeated. This is how a wave survives a skipped beat.
- **Significance is weighed, never a threshold.** It comes from who is involved (their rank and fame), how public it is, who it touches, novelty and violence, and what else is in the news that day. There is **no fixed cut-off between "full wave" and "nothing" and no tier table**. A capo's indictment lands big and an ordinary day carries only the texture a scene naturally has, but both fall out of the weighing. Detail follows significance (the owner's pacing rule), so it does not become a list.
- **The character sees news about other people, not only himself.** The paper on his table, the six o'clock anchor, the radio in the car and the talk at the club carry stories about rivals, other families, politicians, friends and anyone he is watching. What reaches him depends on his habits and means (which paper he reads, whether he watches TV, who tells him things), his interests and relationships, and the story's significance. This is both texture and a **source of information** he can act on (a rival's indictment is an opening; a politician's scandal changes who he calls), and it can **mislead** him: it is a printed claim with a source and a truth link he cannot see. The same ledger tracks it, and it is pushed, never asked for.
- **Cutaways are allowed.** The engine returns off-screen reactions (the editor's meeting, the anchor's script, the club talk) marked as outside the character's knowledge. The character may act only on what reaches him: a paper he reads, a call, a man who stops greeting him.
- `rulebook_core.md` gets a section: weave, never announce, never wait to be asked; being asked is a miss; minor ripples stay on request through `lookup`.
- **Test of success**: play a stretch with no prompting and check that crew, dress, deference and news all appear unasked, and that no wave is dropped or repeated. Also check that **the family's lives visibly carry the man's reputation without the player asking**: the children's school days, the wife at the shops and at church, and the reactions that come home. An honest limit: the engine supplies and tracks; it cannot write the GM's prose, and the ledger and rulebook are how a miss is made hard.

### 7.4 Media institutions at B depth (phase 2)

- A paper, TV station or radio station is an **institution on the org core**: owner, editor, reporters, anchors, politics, debts, advertisers, unions (the *Mirror*'s pressmen), a **cadence** (morning, evening, weekly, six and eleven), a **reach** per audience, and its **own reputation**: trusted by some audiences and discounted by others (the *Courier* on the Eastside, the *Chronicle* downtown).
- **Story pipeline**: tip or source, assignment, reporting, editing (run, hold, kill, soften, move), print or broadcast, reaction. Gatekeeping runs on deadlines, limited space, competition for scoops, libel exposure, sourcing, owner and advertiser pressure, and access dependence (a reporter goes soft on a source he needs). Each step is a plausibility proposal the engine can veto.
- **Sources of stories**: courts and public records, police and prosecutors' press conferences, leaks (used as pressure), informants, reporters' own digging, rivals planting stories.
- **Attention is limited**: a bigger story buries yours, and a release can be timed to a slow day on purpose. Follow-ups, denials, retractions and lawsuits are news in their own right.
- **Records**: every printed or broadcast story stays on file (the morgue). The long memory: an old story or court record can be dug up years later in an election year. Photos and film count for more than text.
- **Falsehood**: a planted story or forged proof is stored with no truth link; what people believe is separate from what happened; the player's own paper can mislead the character.
- **NPC reporters and editors have ambitions** (a prize, a seat, a job at a bigger paper, a score to settle) and act on them through the existing choices path.
- **Owner as a playable seat**: levers are the editorial line, hiring and firing the editor, holding or killing stories, advertisers, union relations, buying and selling, licences and endorsements. No fixed motive; what he wants depends on the story and the character.
- **Press and word of mouth run side by side**: a neighbourhood hears it on the street before the paper prints it, and the street may not believe the paper.

### 7.5 NPCs under the same rules (phase 1 and 2)

- An NPC **hears news about himself** through the same channels, weighs it by the same drivers, and responds: ignores it, answers it, buys the editor, leaks a counter-story, leans on the reporter, goes quiet, or retaliates.
- An NPC **manages an image**: a prosecutor builds a career through press conferences, a politician defends his name, a rival head cultivates fear or respect.
- An NPC **arrives with a pose**: retinue, dress and car follow his means, role and temperament. **Display follows means**: a man who has just been paid goes on a spending spree and his display rises; a man under indictment may go quiet. Strangers read it.
- **Peers read each other**: a head's standing among other heads is the same machinery.
- **Institutions have reputations too** (a family, a paper, the police department, a city), and public trust in them affects tips, juries and cooperation.
- **Legacy**: an heir inherits part of a reputation and a family name carries it, through B12b's succession layer.
- **Nicknames and epithets** emerge as claims the press or the street gives a man; they stick, and they connect to aliases (WITSEC).
- All NPC behaviour runs at the tier the population design gives it: background crowds as aggregates, notable and named people individually, no special treatment.

### 7.6 How it feeds the other systems (phase 3)

- **Law**: a story is a tip and a source of public pressure on prosecutors; prosecutors' ambition (prison design 7.1b) links to coverage; pretrial publicity bears on juries, gag orders and venue; the case chain's `member_arrested` is also a public happening that starts a wave.
- **Politics**: scandals and elections run on reputation per electorate; an old story resurfaces in a campaign; endorsement is a lever; the press's own politics matter.
- **Business**: confidence (a story about a firm moves lenders, customers and suppliers); owning a paper or station is a business seat; advertisers are a pressure.
- **The mob**: the cost of attention. Heat makes police hungrier, politicians cooler and the commission unhappy; silence keeps standing and talking loses it (bible rule); a family's name is a man's reputation.
- **The player's own reach**: any plausible route to the press, such as an interview, a favour, a rat inside the paper, a bribe, a lawyer's leak, a statement on the courthouse steps. There is no menu of press actions; the player says what he does and the engine vetoes only contradictions.
- **Public set-pieces** (wakes, funerals, trials, rallies, press conferences) are stages where reputation is made and tested; the engine marks them as high-exposure happenings.
- **Legal limits on the press**: libel exposure is in phase 2; subpoenas, shield laws and gag orders are later work (section 8). All are data the package supplies, with 1975 specifics flagged **[verify]**.

### 7.7 What the GM sees under the knowledge firewall

- `scene`, `advance` and `resume` return the texture block (7.3). `lookup` returns the claims the character holds about a subject, the room read, a story's text and the ledger of what he has seen.
- The firewall keeps two things apart: what the **character** knows (what reaches him), and what the **GM** is shown to write a cutaway, marked as outside the character's knowledge. The GM may not use a cutaway as the character's knowledge.
- Truth links stay with the engine: the GM sees that a claim is false only where the character could know it.

### 7.8 Generalisation

- A package supplies: media (channels with speed, reach, cost and cadence), audiences, customs of deference, signals and display forms, the law's limits on the press, and the era's technology. Saint Jude 1975 supplies print, TV at six and eleven, radio and no internet. A medieval package supplies heralds, criers, banners, titles, letters and pamphlets. A football package supplies tabloids, fans, club statements and bans. A later Saint Jude era supplies cable and the internet on the same engine.
- Caerness's existing martial reputation (stage, sect fame, `martial_instruction_public`) becomes one audience's claims in this model and is not rewritten.
- `tests/no_world_words_test.py` covers the new modules.

### 7.9 Calibration (reported, never enforced)

After a run the builder reports, among others: time for a story to cross the city, the share of tips killed or held by editors, the gap between belief and truth for false stories, how far a wave moves a named man's belief against his audience's impression, time to decay of an unreinforced claim. These are targets compared against real-world figures and tuned through the drivers. They are never caps.

## 8. Phases and order

**Where it sits in the build order.** Phase 1 comes straight after org-core tasks B13 to B16 and **before prison**, which uses it (the arrest wave, standing inside).

1. **Phase 1, split so value arrives sooner.**
   - **1a. Bearing, room read, the push and the ledger**, built on what already exists (`standing.py`, `knowledge`, rumours, seats, money, assets). Display comes from real things (7.2). 1a should already end the "having to ask" problem.
   - **1b. The full claims and audience model** (7.1): claims with source and confidence, crowd impressions, decay, seat standing as the outfit's audience impression, the personal circle, NPC image and display rules.
2. **Media institutions at B depth**: papers, TV, radio, the story pipeline, waves, records, falsehood, nicknames, owner seats.
3. **Hooks**: law (pressure, pretrial publicity), politics (scandal, elections), business (confidence, ownership), the mob (heat and the cost of attention), the player's reach into the press.
4. **C depth and the GM's views**: the interview, the courthouse steps, the rulebook section.

**Later work, kept possible but not built first** so phase 1 stays small: the **reporter role**, the **newsroom at C depth**, and **legal limits on the press beyond libel** (subpoenas, shield laws, gag orders). Nothing in phases 1 to 3 may need a rewrite to add them.

Business and politics are not built; phase 3 grows as they land. The delivery ledger and the push (7.3) ship with phase 1a, because every later phase depends on them.

## 8b. Calls made while writing this up (mine, not the owner's; check these)

- **"C" was read as the third approach, the hybrid.** The owner answered "C probably" to a numbered list; I took it as option 3.
- **Phase order** was mine; the owner has since approved placing phase 1 after org-core tasks B13 to B16 and before prison, splitting it into 1a and 1b, and the later-work list (section 8).
- **Folded in at the owner's approval** (relayed by the session that started this work): seat standing as the outfit's audience impression; significance weighed with no threshold; the cost target; display from real things; the personal circle as an audience; and the family as subjects of the wave in their own off-screen days (the owner: "all of these life reactions are cool to me").
- **`social_reputation` stays** as the derived summary for the existing martial reader; the new layer sits beside it.
- **Claims are free text.** This follows the no-closed-lists rule; the builder may add a light index for lookup but not a vocabulary.
- **Crowd impressions at B, individuals at notable and named tiers**, following the population-tier design.
- **The owner of a paper as a playable seat** is in scope for phase 2; the reporter role is only kept possible.
- **Nothing here asserts real 1975 legal facts.** They are flagged **[verify]**.
- **The texture block is a new field set in existing connector responses** and does not add a connector tool; the exact shape is the builder's.

## 9. Left to the builder

Table and column shapes; which existing modules to extend and which to add; the weekly rhythm and rate keys; the Saint Jude data (audiences, media staff and owners, customs, signals); test fixtures; the exact texture-block and ledger fields; the shape of the claim index; which Design proposals to author first.

## 10. Decisions the owner made in the conversation

- Reputation, standing and reactions are the core; the press carries them. It should build the character.
- A wave after a major public happening, with the GM writing reactions from people who are not there; **cutaways are allowed**, marked as outside the character's knowledge.
- The player can fight, steer or stay neutral, all decided by plausibility from where the news came from, who the character is and when he hears it.
- The press is built at **B and C depth, not a background carrier**. The owner probably will not play a reporter or anchor but may own a paper or TV station; connection comes through any plausible route (an interview, a plant inside).
- No fixed motive for owning a paper; it depends on the story and the character.
- The player sees news about NPCs as well as himself, as part of the world reaching him, and it can inform or mislead him.
- Waves are pushed to the player without being asked, with the engine and the rulebook arranged so asking is never needed.
- Presence and display are in: retinue, deference, dress, car, spending, read by strangers, and dynamic within a scene and over time.
- NPCs run the same machinery: they get news on themselves, show a pose, security and a nice car, and go on shopping sprees; all plausible and realistic.
- The hybrid approach was chosen.
- All the extra items proposed were accepted: nicknames and epithets, false stories, the long memory, reputation as a constraint, the cost of fame, public set-pieces, institutions' reputations, NPC image management, legacy, and legal limits.
