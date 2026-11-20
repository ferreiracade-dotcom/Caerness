# Prison as a playable part of the game: design

Date: 2026-11-20. Status: draft for the owner's approval. Follows the Saint Jude mob work (org core, branch `feat/world-packages-saintjude`); the business and politics spheres come after it, and this design is written so all three, and later worlds, use it.

## 1. Intent and why

The owner wants prison never to be the end of the game. Whether the person is a corrupt businessman, a politician or a mobster, and whether it is the protagonist or any other character, going to prison is a new setting where things still happen: power, politics, deals, danger, and a long reach back to the world outside. The owner's words: there are many ways to go to prison, and "that shouldn't necessarily be the end of the game because things should still happen there."

Today the engine cannot do this. See section 2.

## 2. Current state (verified in the code, 2026-11-20)

- `custody` (schema.sql) is one flat row: actor, charge, kind (`held`/`bailed`/`released`), since_day, optional until_day.
- The only writer in the engine is `_do_busted` in `engine/org_happenings.py`: a short arrest with a span of days rolled at the time. Every other writer is a test.
- `law_enforcement_cases` run `monitoring -> open -> actionable -> referred` (`engine/underworld.py`) and `crime_reports` are opened by `informs` and `busted`, but nothing turns an actionable case into a charge, trial, sentence or a facility. `bailed` is never set.
- What exists around custody: `org_membership` takes standing from a man taken into custody; `org_lifecycle._held_decisions` has the superior weigh each week whether to cut a held man's review level or give the seat away (an acting man for a unit leader), and `_return` gives a released man his seat or a returning role back; `worlds/saintjude/law.json` has jurisdictions, agencies, the Pad's reach and routing.
- Task B13 of the org-core plan adds `open_report(...)` for fraud and bribery and sends `member_arrested` to the leader and head in every org the man sits in.
- There is no place, no society, no inside happenings and no GM guidance for a jailed protagonist. For the protagonist "held" is days with nothing in them.

## 3. Goals

1. A jailed person stays alive in the story: acts, is acted on, and the world responds. Same rules for the protagonist and any NPC.
2. The route in is open: any source of a charge (the sphere's own crime, a personal matter, a frame-up, an informant, a sweep). Nothing is scripted.
3. Seat and outfit logic is generic: a capo, a CEO and an indicted alderman go through one mechanism (kept, acting man, or lost), driven by loyalty, time and the quality of the channel out.
4. Prison has its own societies with real people in power, and runs whether or not the player is there (B depth), growing finer around the player when they go in (C depth).
5. Every way out exists and every way is plausible rather than listed: served, parole, appeal, pardon, a deal, escape, death, release as a different man.
6. It works on a phone through the Claude connector: Claude is the GM and plays scenes; the engine holds who is where, the terms, standing, money and consequences.
7. It generalises through package data across the three Saint Jude spheres and later worlds.

## 4. Non-goals and anti-goals

- No closed menus, ladders or ceilings. The engine vetoes named contradictions (an established fact, a canon rule); everything else is a plausibility proposal in data. Rates are data (Design proposals), never code constants.
- No minute-by-minute simulation of every inmate (cells, shifts, yard) as the base layer.
- No world words in `engine/` builders. Saint Jude's jail, Ironhaven and federal penitentiaries live in `worlds/saintjude/` data.
- No invented crimes for real public figures; real people appear in their real roles (standing rule). A real jailed figure appears as in history.
- Not a failure state or a punishment screen. It fails if prison looks like skipped time or a game-over.
- Not forced skipping. Prison is played in detail by default; the player skips when they ask.
- No special treatment for named characters or the protagonist: same rules at every tier.
- The engine never narrates; the GM never decides outcomes the engine has not returned.

## 5. Constraints

- Source canon: bible Part II section 8 (levels of prison, Ironhaven, federal penitentiaries with opening years, Lewisburg's 1976 criticism, parole commission 1976, parole bans on mobsters meeting), Part II section 7 (informants, WITSEC from 1971), Part III and the "silent keeps standing, talks loses it" rule, the envelope for jailed men's families and the "slow rot", bugged visiting rooms, acting boss, street boss and panel. Which mobster does time where, and the federal detention centre's name, are Open: author them.
- Existing standing rules: engine = memory, plausibility and world; Claude = GM; protagonist is a new non-canon character; packages are data only; rare things stay rare; where life and death are both plausible lean toward life and never invent survival (this governs uncertain survival only, never what violent people choose: when someone means to kill and can, a killing that lands kills); conscience follows the character's beliefs; a time-skip keeps the character's routine and is interrupted by real events.
- Another session edits `engine/org_membership.py`, `engine/org_lifecycle.py` and `engine/outfit_opening.py` and Saint Jude data now. This work starts after it lands and extends those layers; it does not fork them.
- Performance: the connector has to answer quickly. B runs on the existing weekly grid; C is local to the player's prison.
- Business and politics are not built yet. The case chain must accept an offender and a crime kind from any sphere (B13's `open_report`).

## 6. Approaches considered

- **A. Prison as a layer on existing machinery (chosen).** The case becomes a chain; facilities are package data; societies inside are outfits on the org core; channels are first class; exits follow the chain; Claude plays every scene. Cost: a real project touching law, lifecycle and happenings.
- **B. Thin.** Keep the `custody` row, add a prison location, let Claude invent the inside with `note`. Cheap, but jailed NPCs only live while Claude writes about them, the world does not move on, and the player's own years would be hollow. Rejected: it breaks "other characters' stories continue".
- **C. Full inmate simulation.** Cells, shifts and yard for every prisoner. Heavy, conflicts with "the engine does not model minute mechanics", slow on a phone. Rejected as a base; rather, the owner's B/C depth rule gives the finer layer only where play goes (below).

The owner picked A, with the C element from the existing depth rule: **B depth always, C depth where the player is** (spheres spec section 5.2a: B is the default living thing with owner, people in seats, money, agenda and drivers; C works out the same drivers in finer detail where the story moves, history carries over, nothing resets, and C is its own design-and-build project).

## 7. Design

### 7.1 The case chain (phase 1)

A report (`open_report`, B13) names an offender and a crime kind from any source. The chain from there is data-driven and every step is a proposal the engine can veto:

charge -> arraignment -> detention or bail (`bailed` is finally used) -> pre-trial (counsel, evidence, witnesses, deals) -> disposition: dismissal, plea (with or without cooperation), trial and verdict -> sentence (term, facility, conditions) -> serving -> exit.

- Evidence, agency reach and the Pad's protection already exist; they set how fast the case moves and whether a tip leaks. Warning before arrest is whatever plausibility gives: a long trial the character expects to lose gives years; a quick bust may give nothing; a tip comes from someone who reaches the right officer; clean agencies (FBI, Strike Force) are out of the Pad's reach.
- Other people are competent: lieutenants know how it goes, call from the jail, visit, and act on their own.
- Co-defendants and sweeps are first class: one action can charge many men, who can flip on each other; `member_arrested` goes to every org each man sits in (B13).
- A conviction has costs beyond the term: forfeited assets, lost licences and office, bars on some work, parole conditions that forbid meeting the old crew. These feed the business and politics spheres.
- The route in is not tied to the sphere: a personal matter (the politician jailed for abuse at home) enters the same chain as a bribery case.

### 7.1b The justice system is people (phase 1)

The people in the case are actors with their own lives, not stages. The case is where much of the story happens.

- **Prosecutor.** Has ambition, which links to the politics sphere (a career, an office sought). That ambition weighs how hard he pushes and what he will trade.
- **Judge.** Bribable or not, as his own character and circumstances make plausible.
- **Jury.** Can be tampered with, can hang.
- **Witnesses.** Can be intimidated, bought or killed, or can go into protection.
- **Defence lawyer.** The mob lawyer especially is also a channel and a messenger (7.3), not only counsel.
- Acting on any of these people goes through the existing choices and agenda path, and the engine vetoes only contradictions. There is no menu of "tamper" or "bribe" actions.

### 7.1c How outcomes are decided: drivers, no caps (phase 1)

Each decision in the chain (charge, bail, plea or trial, verdict, sentence) is weighed from drivers: evidence strength; the defendant's temperament and loyalty; what a deal offers and what he risks by refusing it; the lawyer; money; threats against witnesses; the prosecutor's ambition. These are plausibility inputs, the same as elsewhere in the engine.

**Rates are calibration targets, not rules.** In reality most charges end in a plea or are dropped and few reach trial; mob cases more often went to trial and were sometimes won by tampering. The builder reports what a run produces against such targets and tunes the drivers. Targets are never shares, quotas or clamps. Nothing in code or data says "at most X% go to trial", no outcome has a fixed distribution, and there is no outcome menu. This is stated here on purpose, because target figures have been turned into hard caps before (made-man counts, first-offence kills, timers).

### 7.2 Facilities and societies, at B depth (phase 2)

- A facility is a package-data institution: level (jail, detention centre, state prison, federal penitentiary, camp), security class, who runs it, intake rules (sex, security class, case), and its drivers: crowding, violence, corruption, contraband, guard arrangements.
- Societies inside are outfits on the org core, so a family's men doing time, a prison gang, and a guard arrangement each have seats, standing, loyalty and weekly happenings. Hierarchy follows race and neighbourhood (bible); a made man expects deference; old friends and enemies are often there; mob men live well with money; time inside can cost a man his place outside or make his name.
- Notable inmates and staff (those with real power) are individual actors; the rest is a headcount with a character. Everyone lives by the same rules at every tier.
- A prison runs weekly at B whether or not the player is there, so a boss calling shots from inside is already doing it before the player arrives.
- Standing inside follows existing logic: silence keeps it, talking loses it; the cooperator needs protective custody.
- Women are few and held apart; assignment follows sex, class and case. Cellmates and inmates can be informants (knowledge firewall applies).

### 7.3 Channels and the outside (phase 2)

- Reach from inside runs through channels: visits, the lawyer, a trusted man, a smuggled note, a phone, a bought guard. Each has a quality (slow, watched, interceptable), and the quality is what you can do from inside. Information matters: casual or above-board talk is open; incriminating talk needs codes or a trusted route; visiting rooms are bugged. A weak channel means the outside drifts; a strong one, bought, keeps the grip.
- Seats while a man is held go through B12b's appointment and succession decisions: an acting man, a street boss or a panel are appointments decided by the man with the authority. There is no second mechanism. The channel's quality and the time held feed those decisions as inputs. A business runs without its CEO; an office is filled by the rule its package gives (Part III Open on families).
- The defence lawyer, and especially a mob lawyer, is a channel and messenger in his own right (7.1b).
- Dependents: the envelope for a jailed man's family is a real driver. It shrinks over time and pushes the decision to talk.
- Visiting someone inside while the player is free is a normal play mode: friends, family and rivals get jailed; the player visits, writes, pays for protection or arranges a hit. The visiting room and the lawyer's office are C scenes.
- The world outside moves on: family, business and rivals taking ground through the existing weekly layers.

### 7.4 Ways out (phase 3)

Sentence served, parole (with conditions), appeal, pardon, a deal, transfer, escape, death inside, and release as a different man (name made or ruined, a cooperator under a new name via WITSEC, a record that bars an office, much older). All are proposals; rates and chances are data. Escape and successful appeal stay rare. Life is favoured where life and death are both plausible. Health and ageing apply.

Prison changes a man, which is more than an identity change. A long term moves his temperament and his beliefs, with conscience and cost following the character's own beliefs, not the owner's. Contacts and enemies made inside carry over after release: a friend who runs a block, a rival who got out first, a guard, a cooperator he once shared a cell with.

### 7.5 Depth, C and time (phase 4)

- C is the player's own prison: the blocks and groups around them, the daily routine, the yard and the politics they take part in, resolved in finer detail from the same drivers; history carries over; leaving settles it back to B. C is its own build project (spheres spec rule).
- Play follows the owner's default: major events (arrest, trial, sentence, a deal, the first night) are played in full; skipping inside happens when the player asks. A skip keeps the character's routine (work detail, block, channels), adds the skip's focus, and is interrupted by real events: a visit, a transfer, a hit, a parole hearing.
- The engine notices where play is heading (time inside, choices made) and flags it for C, as the depth rule requires.

### 7.6 What the GM sees and does

- `scene`/`lookup` show custody, the case's stage, the term, the facility, the channels available and the state of the outfits inside, under the knowledge firewall: only what the character would know. The org-core's `record_view` already shows custody; it extends to the case chain.
- `rulebook_core.md` gets a prison section: an arrest and its consequences are major events, play them out; the world moves on outside; inside is a setting with its own politics; skip only on request; the GM proposes freely and the engine vetoes contradictions.

### 7.7 Generalisation

A package supplies facilities, security classes, forms of punishment and the law's agencies and their reach. Saint Jude: county jail, federal detention centre (name Open), Ironhaven, Lewisburg, Atlanta, Leavenworth, Danbury and others. A medieval package could supply a dungeon, ransom, exile or a lord's custody; a football package a ban or a fine. Builders in `engine/` use no world words; `tests/no_world_words_test.py` covers the new modules.

## 8. Phases and order

1. Case chain and custody states (generic law layer; extends B13).
2. Prison B layer: facilities, societies, channels, seat and dependents logic, the weekly rhythm.
3. Ways out and what conviction costs.
4. Prison C depth, the GM views and rulebook, time-skips with interrupts.

Prison starts after the org-core tasks B13 to B16 are done. Phase 1 builds on B13's law response; phases follow in order. Business and politics spheres supply their own report kinds into phase 1 when built.

## 8b. Calls made while writing this up (mine, not the owner's; check these)

- **Baseline.** B13 (`open_report`, `member_arrested`) is a plan task, not landed code. If it is not in place when phase 1 starts, phase 1 builds it first; the case chain takes its signature (offender, crime kind, victim, location, metadata; co-defendants as several offenders on one case).
- **`custody` stays.** It remains the one summary table that `org_membership`, `org_lifecycle`, `outfit_motives` and `record_view` read (`held`/`bailed`/`released`). The case chain is a new layer beside it and is the only writer; `custody` is kept consistent as its derived summary. Readers and tests do not migrate. The schema version moves once for the new tables.
- **The chain is package-defined data.** The engine runs a generic graph of stages and transitions with proposal rates and vetoes; Saint Jude's data supplies the US sequence (charge, arraignment, bail, plea, trial, sentence). A medieval or football package supplies its own stages. The existing veto machinery is reused unchanged.
- **Facilities materialise at world start only in outline.** Each facility is an institution with its outfits and its notable inmates and staff (those with real power) authored in opening data. The rest is a headcount and a character figure, with no individual rows until someone meets them (then they are authored and pinned). Weekly B cost is per facility, not per inmate.
- **Openings may start mid-case.** A character or NPC can begin charged, bailed, serving or paroled, as lived history; the case chain supports any stage at placement.
- **Dates are scheduled, outcomes are proposals.** A sentence end, a parole hearing and a trial date are scheduled events on the engine's clock and interrupt time-skips; the engine's plausibility decides what happens at them (granted, denied, convicted, a delay).
- **A new name is an alias on the same actor.** WITSEC and other identity changes keep the same actor row, add an alias the world knows, and the knowledge firewall hides the link from those who would not know it.

## 8c. Owner's ruling on first release

Phases 1 to 3 may ship with a jailed protagonist at B depth only. The owner will probably not play before it is all complete, and until C exists the GM can improvise inside scenes within B's facts (the engine vetoes contradictions). The GM view and rulebook section (7.6) stay in phase 4.

## 9. Left to the builder

Table and column shapes; which existing modules to extend versus add; the exact weekly rhythm and rate keys; which Saint Jude facilities and notable inmates to author first and their names; the Design-proposal numbers (every rate is a data figure); test fixtures; the exact GM view fields.

## 10. Decisions the owner made in the conversation

- Plea deal and cooperation is a valid, fully playable path (protective custody, WITSEC), not just one way out of a trial.
- Arrest, trial, sentence and first nights are played in detail unless the player asks to skip; inside is more skippy because there is less to do.
- Reach from inside runs through channels (accepted as realistic); secrecy needs depend on what the information is.
- Prisons exist and run at B at all times; C is where the player is (the depth rule).
- Routes in are open and not tied to the sphere; warning depends on the case and on who you know; other characters act competently; a business runs without its CEO.
- Included: dependents and the envelope, visiting someone inside, group cases, costs beyond the sentence, assignment and informants, health and the long term, real people.
