# Story layer: grounded speech, story sifting, honest rumour, real bargaining

**Status:** proposed on 2026-10-09; awaiting the owner's review. Nothing here is implemented.
**Evidence and sources:** `docs/research/2026-10-09-story-layer-sources-and-adoption-audit.md`.
**Scope:** four workstreams (SPEECH-01, SIFT-01, RUMOUR-02, DEAL-01). Each gets its own plan in `docs/superpowers/plans/` when it is scheduled. None should start before PERF-01's current targets are met, except SPEECH-01, which adds narration-time work only.

## 1. Problem

Caerness was built so the stories would live inside a world that exists without the player, because the Narrative Engine games had to invent everything on the spot: inconsistencies, a small world, characters and threads that moved only when asked. The simulation now does that work for the world. It does not yet do it for the two layers the player actually touches:

- **What NPCs say.** The narrator receives present actors as name, type, subtype and status only (`engine/player.py:126-147`). Every line of NPC speech, every demeanour, every hint of what someone wants is therefore invented at narration time and may contradict the state. A promise the narrator puts in an NPC's mouth exists nowhere in the world.
- **Which of the world's changes reach the player as stories.** Threads are recognised by word overlap, place and participants (`engine/emergence.py:107-131`), and only as generic "Developing situation" threads. A betrayal, a feud passing to the next generation, a protégé surpassing the master: the simulation can produce them all, but nothing recognises them as such.

Two further gaps make the world feel smaller than it is:

- **Every rumour is true.** Distortion only lowers confidence (`engine/information.py:370-442`); nothing ever produces a false or garbled claim, and the belief system's `contradicts` path is never reached in play.
- **Bargains are not about the bargainers.** A recipient accepts or refuses by a scalar against a fixed threshold, and a counter is a fixed adjustment (`engine/interactions.py` about 370-410 and 508-512). Nobody asks whether the terms serve the recipient's own goals.

## 2. Principles

1. **The engine decides; the model voices.** Following CICERO: an NPC's speech is conditioned on what the engine has decided that NPC intends, and generated speech is checked against that intent before the player sees it. (DESIGN §23: narration is post-state.)
2. **Revealing is a decision, not a leak.** The narrator still never receives hidden goals, pressures or resources (DESIGN §13). What it receives is the *speech act* the engine chose for the NPC, which may be to conceal or to mislead. Concealment is then the NPC's choice, not the narrator's ignorance.
3. **Recognition has zero authority** (DESIGN §29). Sifting may change what the camera is shown and what the journal indexes. It may never change an outcome, an actor's decision, or how far a rumour travels.
4. **No events conjured on demand; details resolved on first look and remembered** (DESIGN §15.1). A false rumour must come from a real process (a mistaken witness, a motivated liar, a garbled retelling) with its origin recorded. It is never conjured because a scene needs one.
5. **Same rules at every tier** (owner rule). A background NPC with no DEC-01 review still has a speech card, built from role and routine.
6. **Phone budget.** Everything per-day must be incremental and measured with `tools/bench_sim.py`. Narration-time work must fit the local 3-4B model's context.

## 3. SPEECH-01: intent-grounded NPC speech

### 3.1 Speaker cards

`build_scene_packet` adds `speakers`: at most three present actors likely to speak (those with a pending interaction with the player, a goal or pressure that targets the player, a relationship with the player, or a role that makes them address strangers, such as innkeeper, guard or clerk). Each card:

| Field | Source | Notes |
|---|---|---|
| `role`, `doing_now` | actor subtype, presence purpose | What they are visibly busy with. |
| `shared_history` | `relationship_history` and `actor_memories` entries whose subject is the player, filtered to what the player also knows | Lets an NPC say "after what you did at the ford" truthfully. |
| `demeanour` | coarse band of the directed relationship (warm, civil, wary, cold, hostile), unless the speech act is `conceal` or `mislead` | Visible behaviour, not hidden numbers. |
| `speech_act` | engine-chosen, from §3.2 | The intent the line must serve. |
| `may_mention` | up to five claims from the NPC's own belief envelope, chosen by the speech act | This is how rumour reaches the player through talk, grounded in what that NPC actually believes. |
| `open_commitments` | active agreements and pending interactions between this NPC and the player | The narrator may refer to these, and only these. |

### 3.2 Speech acts

A small vocabulary chosen by a cheap rules provider, using the DEC-01 candidate the NPC already holds where one exists: `ambient` (their own business), `greet`, `ask_about(topic)`, `share(claim)`, `conceal(topic)`, `mislead(claim)`, `request(terms)`, `offer(terms)`, `warn`, `refuse`, `threaten`. `mislead` requires an NPC-held motive and a claim the NPC believes to be false or is fabricating; it writes a real claim with that NPC as origin (feeds RUMOUR-02).

### 3.3 Commitment check

After generation, before the player sees the text:

1. The narration response adds a structured `npc_lines` list: speaker, speech act served, any commitment voiced.
2. A rules check flags any voiced commitment (promise, agreement, threat, offer) with no matching `speech_act` or `open_commitments` entry, plus quoted lines that match a small promise-pattern list ("I'll", "you have my word", "agreed", "deal").
3. On a flag, regenerate that segment once with the violation named. If it still fails, drop the offending sentence and log it. Never persist a commitment because prose said it: that would let the narrator create obligations.

Small models misreport their own output, which is why step 2 has a text backstop. Both are logged so the failure rate can be measured on the phone.

### 3.4 Acceptance

- A scene with a merchant holding a pending offer to the player: narration names the offer's real terms, and no other commitment.
- A scene where the NPC's speech act is `conceal`: the hidden goal does not appear in the packet or the prose.
- The injected violation test: a forced narrator response containing an unbacked promise is caught and regenerated.
- Packet size for three speakers stays within the local model's context budget (measure on `pc` first, then phone).

### 3.5 Status: step 1 implemented (2026-10-09)

`engine/speaker_cards.py`, wired into `build_scene_packet` as `speakers`, with `player.visible_standing`; test `tests/speech01_speaker_cards_test.py`.

- **Done:** up to three likely speakers (being named in the request outranks everything; then open dealings, history and familiarity; then people whose work is to address strangers). Each card carries public role and visible standing, familiarity and demeanour toward the followed character, the last three shared-history entries, open dealings (the only commitments they may voice), temperament as portrayal cues, mannerisms and a speech habit. About 425 tokens for three cards.
- **Personality and mannerisms (owner, 2026-10-09):** temperament comes from `actor_drives` where it exists. Mannerisms and speech are resolved on first look from role- and age-fitting pools, recorded in `character_embodiment` (`development_json.revealed`), and identical in every later scene and in any fresh run with the same world seed.
- **Found and fixed:** seed role texts mix public positions with the seed's private judgements ("Generational anomaly", "Strong mature Third", "Good fundamentals"); about 312 characters carry one as their `subtype`, which the narrator received for every present person. `public_role()` keeps positions and professions and drops judgements and Stage labels, for speaker cards and for `present_actors`.
- **Found and fixed (owner approved 2026-10-09), DRIVES-01, schema 109:** 464 of 784 named characters had no `actor_drives` row and decided as exactly average, and 264 of the other 320 came from a near-constant crystallization formula (loyalty .55, ambition .62, pragmatism .68 for everyone). `engine/drives.py` gives every character a stable, bell-shaped seeded draw (basis `seeded_draw`): migration 109 fills the missing and, at day 0 only, redraws the copied rows; the scheduler fills newcomers at every checkpoint and at the end of each advance; latent crystallization uses the same draw. Speaker cards now show the same values decisions use, with cues for drives that stand out from the population (8% of the cast read as even-tempered). Test: `tests/drives01_seeded_drives_test.py`.
- **Not yet:** engine-chosen speech acts (3.2), the commitment check on narration (3.3), organisation colours and emblems for visible standing, and recording texture the narrator itself establishes.

## 4. SIFT-01: story sifting

### 4.1 Patterns

Replace word-overlap recognition with a native pattern library in the style of Winnow: each pattern is an ordered set of typed facts over `events`, `interactions`, `agreements`, `relationship_history`, `harm_incidents`, `leadership_transition_cases` and memberships, with join variables, time windows and `unless` clauses. Partial matches are stored as open threads with the stages matched so far. First set:

| Pattern | Stages |
|---|---|
| Broken word | agreement made → agreement `broken` by one party → the other party remembers it |
| Violation of hospitality | X received or aided by Y → Y harms X |
| Rivalry | three or more adverse interactions or harms between the same pair within a window |
| Feud passes on | harm A→B → kin of B acts against A or A's kin |
| Rise | a person gains office, stage or standing two or more times within a window |
| Fall | loss of office, wealth or standing, then a further loss |
| Pupil surpasses master | teaching line exists → pupil defeats master or overtakes their stage |
| Contested succession | vacancy → two or more candidates or factions → resolution |
| Debt spiral | debt agreement → missed obligation → new debt or forfeiture |

### 4.2 What a thread may do

- Feed the journal and people pages: "what is going on with this person", built only from stages the player has evidence of.
- Tell the narrator which already-known facts belong together, so it can say "the second time the same crew has been seen on that road" instead of two unrelated mentions.
- Nothing else. A thread never raises an event's visibility, never makes a rumour travel further, never biases any decision.

### 4.3 Cost

Incremental: each simulated day, only new rows are tested, and only against patterns whose first stage they could satisfy or open threads they could extend. Bench the day cost with `tools/bench_sim.py` before and after; target under 3% of a 90-day season.

## 5. RUMOUR-02: honest uncertainty, real falsehood

Talk of the Town's central idea, which the earlier adoption missed: knowledge mutates as it travels, and people lie.

- **Garbling.** On retelling, with probability rising with `distortion`, one slot of the claim changes to a plausible neighbour (the wrong place on the same road, the wrong one of two brothers, an inflated number). The result is a new claim with `authoritative_event_id` set and a recorded mutation origin.
- **Lies.** Only from `mislead` speech acts or DEC-01 candidates with a motive. The liar is recorded as origin.
- **Contradiction.** When an actor later gains better evidence, `contradicts` evidence is written. This reconnects the path that is currently unreachable.
- **Fingerprint rule.** PERF-01's 60-day fingerprint method must be extended, not broken: garbling uses its own seeded stream so existing exposure results are unchanged when garbling is disabled.

## 6. DEAL-01: bargains valued by the bargainers

From NegMAS, the half the earlier adoption left out:

- The recipient values the proposed terms by scoring "accept these terms" as a DEC-01 candidate against its own goals, pressures and resources, and compares the result with a **walk-away value**: its best alternative candidate that review.
- Accept if the terms beat the walk-away value; refuse if far below; otherwise counter by changing the single term that most improves its own value, not by a fixed adjustment.
- Relationship and personality still matter, as they already do, but as inputs to value, not the whole decision.
- First slice: merchant contracts or underworld protection, whichever PERF-01 leaves cheaper to touch.

## 7. Also proposed (small)

- **DEC-01 typical-person anchor** (from CICERO's piKL): blend each actor's softmax with a per-role prior of what such a person ordinarily does, so a few utility-maximising outliers do not dominate. Cheap, behaviour-changing, so it needs its own regression evidence.
- **Ledger corrections:** the Vivarium contract fields are empty and unchecked, and the `transitions` claim is enforced by `CHECK` lists only. Either fill and test them, or correct the ledger.

## 8. Open questions for the owner

1. Should a `mislead` speech act ever target the player directly in the first release, or should lies circulate only between NPCs at first?
2. For SPEECH-01, is three speakers per scene the right cap on the phone, or should crowded scenes have one named speaker plus "voices in the crowd"?
3. Which SIFT-01 patterns matter most for the five play styles (cultivator, noble, soldier, merchant, underworld boss)? The list in §4.1 is a starting set, not a decision.
