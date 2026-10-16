# Caerness through Claude: connector design

**Date:** 2026-10-16
**Status:** draft for owner review. No code until approved.
**Requirements:** `D:\Theology\Caerness_Agreed_Narrative_Design_Baseline_2026-10-16.md` (all 16 agreed areas) and `D:\Theology\Caerness_Repository_Audit_2026-10-16.md` (gap audit, 12 acceptance episodes). The design conversation itself is `D:\Theology\Reassess_Caerness_Design.txt`.

## 1. Why this exists

The owner played long campaigns (Ramon, the Order of Two Hearts) directly with Claude. Claude understood anything he asked. What broke was everything around that:

- **Facts and numbers drifted.** Troop counts, money, who was where, titles, promises.
- **Contradictions.** Earlier events were forgotten or rewritten. Claude covered its own arithmetic errors by making a character (Tonic, the finance manager) apologise for them.
- **A yes-man world.** Rewards, land and power arrived because he wanted them; wars were scarce; battles resolved in two paragraphs with no input from him.
- **New chats felt like a different book.** Tone changed, direct speech turned into italic reported speech, "continue" and "do it" were read differently. So he kept one chat for weeks, which made forgetting worse and burned usage.

Caerness fixes the world, not the storytelling. **Claude supplies the imagination; the engine supplies the reality.** "Generous with possibilities, impartial about outcomes."

Success: the owner plays a scene in the Claude desktop app and the facts are right, the world moves on its own, outcomes aren't handed to him, and a new chat continues the same book.

## 2. Decisions already made by the owner

- **One interface for now:** a local connector (MCP) used from a normal chat in the **Claude desktop app on Windows**, with Claude Pro. PC only. No paid hosting. (Phone through a free tunnel may come later; out of scope.)
  - **Superseded 2026-10-16 (owner decision):** the connector is hosted remotely on an Oracle Cloud Always Free VM and used from any Claude app including mobile, via a custom connector; implementation plan `docs/superpowers/plans/2026-10-16-remote-connector-oracle.md`. "PC only", "no paid hosting" and "phone later" no longer apply (hosting stays free). stdio remains supported for local development.
- **Tokens as low as reasonably possible** without hurting the play.
- **Parts bin, not a base.** Neither the Codex `feat/*` stack nor `master`'s player/narration layer is the foundation. The connector is new and built on the engine (simulation, database, promotion ladder). Useful pieces are taken from either on merit. This overrides the audit's "Gate 0: build on the stacked branch". Source-control fact (checked 2026-10-16): `feat/free-cloud-ai` is `master` plus 27 commits; the simulation engine is identical on both, and the branches differ only in the narrative/AI layer (20 engine files such as `narrative_runtime.py`, `world_capabilities.py`, `narrative_authoring.py`) plus small edits to `actions.py`, `opportunity.py` and `player.py`. So the connector builds on `master`. A part taken from the Codex branch is brought over with its dependencies, schema and tests, and the source commit is recorded. No casual single-file cherry-picks.
- **The engine does not model minute mechanics.** That is the AI's job. Three layers (agreed in the design conversation, ~lines 3880–3940 and 9825–9902):
  1. *Intelligence (Claude):* understands intent, improvises, portrays people, knows what a gambling house or a martial sect is.
  2. *Persistent world (engine):* remembers people, places, organisations, resources, commitments, events, and can record new kinds of things nobody anticipated.
  3. *Authority (engine):* enforces what must stay consistent: ownership, resources, time, valid changes, consequences that can't be narrated away.
  **Depth of simulation follows the significance of the consequence.** A customer walking in needs nothing; spending half the treasury needs validation. Specialised mechanics (war, trade, combat) are used where they already exist and add value; new ones only when a real test shows they are missing.
- **No bespoke verbs.** Claude combines a small set of general operations. No per-activity commands, no regex recognisers.
- **Preserve the population promotion ladder** (people rise from groups to individuals).
- **The World Bible is a foundation, not a closed list.** New people and institutions may be invented during play if they fit and pass validation.
- **Continuity across chats:** a stored GM rulebook, standing agreements and a live-thread recap, loaded when a new chat says `resume`. The GM **asks before saving a new standing rule**. The GM **suggests a new chat** when one is getting long or at a time skip or the end of an arc. The GM **saves short recap notes** after meaningful moments.
- **The protagonist is a new character, never a blank one** (§8a): placed into the world with the biography, family, knowledge and job a real person of that age and background would have.
- **Default voice:** close third person, past tense, changeable per campaign on request.
- **Old Claude rule documents are not adopted verbatim.** The agreed 16 areas are the source.

## 3. Goals, non-goals, anti-goals

**Goals (this design):**
1. Claude can enter the existing campaign, see the scene, look things up, and change the world only through validated engine operations.
2. Improvised details stay consistent without being simulated.
3. A fresh chat continues the same campaign in the same voice with no pasting.
4. Every agreed principle has a home: GM rule, engine, connector, or backlog.

**Non-goals (now):** a 3D/visual client; a new simulation subsystem; merging the Codex stack; replacing the browser notebook; PERF-01/POP-01 work (they continue separately).

**Anti-goals (failure even if it "works"):**
- Claude narrates a consequential success the engine never recorded, and the story carries on as if it happened.
- The engine grows a hand-coded command for every activity.
- An AI or engine mistake becomes a character's fault.
- The world bends toward the player (rewards, convenient rarities, protagonist-first discoveries).
- A new chat changes the voice or forgets agreements.
- Turns cost so many tokens that the owner hits Pro limits in a short session.

## 4. Shape of the system

```
Claude desktop app (normal chat)
   │  MCP over stdio (launched by the app); the transport can also be Streamable HTTP (remote hosting, 2026-10-16)
   ▼
caerness-mcp  (new, thin: tool definitions, turn ledger, continuity store)
   │  Python calls, one SQLite connection
   ▼
engine/  (existing simulation, people, knowledge, promotion, war, economy…)
   ▼
campaign database (a copy of data/caerness.db, never the packaged opening file)
```

- The connector is a Python process using the official MCP Python SDK (`mcp` package, not yet installed), registered in Claude desktop's config with the interpreter path and the campaign DB path. It holds the database while the app is open.
- No raw SQL tool, no Python-exec tool, ever.
- The campaign file lives outside the repo's packaged `data/caerness.db` (for example `%LOCALAPPDATA%\Caerness\campaigns\<name>.db`), created from the opening world on first run.

## 5. The tools Claude gets

Small on purpose: every tool definition is sent with every message, so each one costs tokens all session. Target **8 tools or fewer**, short descriptions.

| Tool | What it does | Notes |
|---|---|---|
| `resume` | Start or continue a campaign in this chat. Returns the GM rulebook, standing agreements, character sheet summary, live-thread recap and current scene. | Called once per chat. ~2–3k tokens. |
| `scene` | The current situation from the player character's point of view: place, time, who is present (with what the character knows of them), what's pending, recent news, relevant competence. | Built on `player.build_scene_packet`, re-shaped compact. The existing brief is ~1.1k tokens; aim ≤ 1k. Includes `professional_context` (fixes the audit's top defect). |
| `lookup` | Targeted retrieval: a person, place, organisation, event, relationship history, what the character knows/believes about X, journal entries, earlier notes. | The answer to "Claude checks instead of remembering". Respects character knowledge; GM-only facts are marked as hidden. |
| `act` | Submit a consequential intention as one or more general operations (see §6). The engine checks feasibility, resolves what it owns, advances the time the activity takes, commits, and returns what actually happened (attempted, agreed, refused, in progress, failed) with an operation id. | The only way the world changes, apart from `note` and `author`. |
| `note` | Record a lightweight improvised detail so it stays consistent: a name, a description, a minor fact about a place, something someone said. No simulation, minimal validation (no resources, no authority, no outcomes). | See §7, tier 2. |
| `author` | Propose a consequential new thing: a person, school, organisation, rumour, background fact. The engine validates against canon and the world and either materialises it with native ids and an independent life, or rejects it with a reason. | Reuse the Codex `narrative_authoring.py` approach if it holds up. |
| `advance` | Pass time: wait, travel days, a deliberate time skip. Runs the world and stops early at genuine interruptions (existing `timeskip.py`). Returns what the character noticed plus a short "while you were away" digest. | Time skips stay player-directed. |
| `campaign` | Continuity housekeeping: save recap note, propose or save a standing rule (after the owner says yes), report an AI or engine error for correction, mark arc boundaries. | Kept to one tool to save definition tokens. |

The exact parameter schemas are left to the plan, with one rule: **parameters are general** (who, what, with what, toward whom, under what terms, for how long), never activity names. General at the surface does not mean generic underneath: every call routes to **typed, validated engine operations**. There is no tool that edits arbitrary world data.

**What may change the world, and how:**

| Tool | May change | Never |
|---|---|---|
| `act` | Consequential actions, resolved by engine domain rules | Narrated outcomes without resolution |
| `advance` | Game time, and everything the simulation does in that time | Skip time the player didn't direct (except time an activity itself takes) |
| `note` | Lightweight details, recorded as GM-improvised | Resources, authority, outcomes, objective truth of claims |
| `author` | New persistent people, institutions, events, after validation | Troops, money, ownership, victories, legal authority |
| `campaign` | Recap, standing rules (after owner approval), error reports, and later error repair (§8b) | World state outside the repair workflow |
| `resume`, `scene`, `lookup` | Nothing (read only) | — |

**Every mutating call is safe to retry.** Each carries a call id; repeating it returns the stored result. This applies to `act`, `advance`, `author`, `note` and `campaign` alike: no duplicate people, double spending, double casualties, or time advanced twice.

## 6. One turn of play

Agreed protocol (Area 16-H): **interpret → inspect/validate → commit → narrate.**

1. The owner writes. It may be speech, intention, a mix, a parenthetical question, "continue", "redo".
2. Claude decides what kind of turn it is, using the GM rulebook:
   - **Pure portrayal** (looking around, small talk, a gesture, atmosphere): no tool call, or a `lookup` if a fact is needed. Most turns.
   - **Out-of-character question** (parentheses, or plainly a player question): `lookup`, answer in parentheses, no time passes, no in-fiction amnesia.
   - **Consequential intention** (give an order, spend, recruit, negotiate terms, attack, travel, promise): `act` first, narrate after.
   - **Something new and lasting** enters the story: `author` (consequential) or `note` (detail).
3. The engine returns facts and outcomes. Claude narrates **from those results**. If the engine refused or the result is partial, the narration shows that.
4. After a meaningful moment, Claude saves a recap note with `campaign` (a few lines).

**When Claude forgets to call a tool** (it will happen; nothing can force a tool call):
- The engine never changes from prose. An uncommitted "success" simply didn't happen in the world.
- Every `scene` and `resume` response includes the last few committed operations, so drift shows up on the next read and Claude corrects it outside the fiction (Area 4: no in-world excuses).
- The rulebook states plainly: consequential outcomes are only narrated after `act` returns.

**Retries:** see §5, every mutating call is idempotent. This is acceptance episode 12.

## 7. What gets stored, by significance

This is how "the engine doesn't model minute mechanics" works in practice.

| Tier | Examples | Stored? | Validated? |
|---|---|---|---|
| 1. Pure prose | Weather, a passer-by's cough, the smell of the stables, a bartender's joke | No | No |
| 2. Noted details | The innkeeper's name and limp, the colour of a banner, a scar, what the captain said about the north road, a minor rumour Claude introduced | Yes, as **notes** attached to a person, place or organisation, with provenance "GM improvised" | Only that it doesn't contradict recorded facts |
| 3. Consequential | Money, troops, property, office, agreements, injuries, deaths, new significant people, relationships changing meaningfully, time | Yes, as engine state | Yes, by the engine's existing domain rules |

Notes come back in `lookup` and in `scene` for people who are present, so improvised details stay put across scenes and chats. A noted person who becomes important can be promoted through `author` without contradicting what was noted.

Provenance is kept on everything. A finance manager's report is a statement; the treasury is the ledger (the Tonic rule).

**Recording a claim never makes it true.** If Claude introduces a rumour that a noble secretly funds bandits, the record is "this rumour exists and these people heard it", not "the noble funds bandits". The engine keeps these apart (it already has beliefs, evidence and rumours in `belief.py` and `information.py`):

- established world fact
- something a character said
- a report from an identifiable source
- a rumour or belief, possibly false
- an unresolved possibility (nothing decided yet)
- a hidden truth that is settled but undiscovered by the protagonist

Once a hidden truth is settled it stays settled (Area 14: mysteries need stable truths). Claude may see hidden truths to stay consistent, but never reveals them without a legitimate way of finding out.

**Weight decides the tier, not the type.** A minor rumour is a note. A rumour that sets an investigation going or changes what a faction does is a consequential event and goes through `author` or `act`.

**Recaps and notes are guides, never sources of truth.** If a recap says an offer was accepted but the engine records a refusal, the engine wins and the recap is corrected.

## 8. Continuity across chats

Stored in the campaign database, not in Claude:

- **GM rulebook.** The agreed play rules, written as direct instructions to the GM (initial content in Appendix A). Same for every campaign unless changed.
- **Standing agreements.** Rules added during play ("don't do X", "I like Y"). The GM proposes; the owner confirms; then `campaign` saves it. Each has a date and the scene it came from.
- **Character sheet summary.** Who the protagonist is, voice, temperament, ambitions and priorities (Area 15), established habits. Changes when play changes them, not when Claude speculates.
- **Live thread.** The rolling recap: the last few meaningful moments, open threads, where the scene stands, the protagonist's immediate intent. Old recap notes fold into the journal over time so the recap stays short.

**Starting a new chat:** the owner types `resume` (or uses a saved Claude Project instruction that says "call `resume` first"). Claude calls `resume`, gets everything above plus the scene, and continues mid-scene without a "previously" unless asked.

**Suggesting a new chat:** the connector counts turns and tool output since `resume`. Past a threshold (my guess: ~40 exchanges or ~60k tokens of tool output; tune in play), and at natural breaks (after an `advance` skip, or an arc boundary), the response carries a hint and Claude says one line out of character: a good moment to start a fresh chat. It never interrupts a scene mid-flow.

**Journal page (later layer):** a local browser page served by the connector, reading the same database: journal, recap, rulebook and agreements (editable), people, organisations. Costs no Claude tokens. The browser notebook in the Codex branch is the first candidate part.

## 8a. Starting a campaign: a new character with a lived past

Owner's decision: the protagonist is **new, but never blank**. Taking over someone at 25 means they already have a biography, family, knowledge, skills, a job, relationships and a place in the world, exactly as an existing person of that age and background would.

The flow:

1. **The owner describes a concept** in chat, as loosely or as precisely as they like: "a 25-year-old caravan guard from the southern marches", "a minor noble's third son who failed at the sect entrance trials", "a cultivator in her forties who runs a small debt-collection crew".
2. **The engine finds that person in the world.** The protagonist comes from the matching background population group, through the existing promotion ladder (`background_population.promote_identity_to_latent` keeps the sampled identity), so the world's headcount doesn't change and the protagonist was always "there". Where no group fits, the engine creates the person through the same validation as `author`.
3. **The engine gives them a lived past by the world's own rules**, the same machinery the opening world used: family and marriage history (`opening_family.draw_family_history` and related), relatives as real people where warranted, competence by age and occupation (bell-shaped aptitudes, actual training), means and access, employer or organisation, people they know, what they know (local knowledge, profession, culture), and Veinborn/cultivation status only where plausible. **No special treatment** (owner rule): the protagonist gets the same rules as any named person.
4. **The owner sees a summary** (who they are, family, work, skills, standing, a few people who matter, a little past) written by Claude from engine records. They can accept, ask for another draw, or adjust details. Adjustments must stay plausible. A request like "make me a secret heir" is checked like any other claim and may be refused or toned down.
5. **The character sheet** (§8) is seeded from this, along with the protagonist's voice and temperament, which come from the owner's concept and are then confirmed in play.

What the owner chose stays fixed. Everything else is drawn by the world's rules. *(My call: the owner may ask for a fresh draw a few times; there's no hard limit, but each draw is a real plausible person, not a wish list.)*

**This workflow is new work.** The engine has the parts (promotion of a sampled identity, opening family history, competence, relationships) but not a character-creation flow that joins them. It is to be built and tested. It is also separate from **automatic promotion during ordinary simulation** (people rising on their own while the world runs), which exists as a mechanism but whose production triggers are unproven (audit, Gate 4). One is a player-facing flow; the other is a world behaviour with its own test (§11, step 5).

Acceptance for creation: the world's population count doesn't inflate; no family members are duplicated; no existing person's recorded history is silently rewritten; the protagonist's past is consistent with what other people remember of them.

## 8b. Repairing real errors

Reporting an error is not repairing it. Agreed standard (Area 4): when a wrong record has already affected later events, the affected state and everything that depends on it gets corrected. Workflow, through `campaign`:

1. Identify the incorrect record or event.
2. Inspect what depends on it (the engine's causal links and provenance).
3. Propose the correction and its knock-on effects to the owner.
4. Apply it as one validated engine transaction.
5. Keep an audit trail of the correction.

Never an unrestricted editing tool. This comes after the first playable slices, but it is **required before the game is treated as safe for long campaigns** (§11, step 5).

## 9. Token budget (targets, to be measured)

| Item | Target |
|---|---|
| Tool definitions (sent every message) | ≤ 1.5k tokens total |
| `resume` | ≤ 3k |
| `scene` | ≤ 1k |
| `lookup` | ≤ 500 typical |
| `act` / `advance` result | ≤ 600 typical; longer only for big skips |
| Ordinary portrayal turn | no tool call |

Measured: today's full scene packet is ~16k characters (~4k tokens) and builds in 0.1 s; the rendered brief is ~4.4k characters (~1.1k tokens). The packet's biggest parts are the player record, narrator rules and embodiment; narrator rules move into the rulebook (sent once per chat instead of every scene).

## 10. Where every agreed area lives

GM = rule in the rulebook. Engine = the engine already owns it (may need tests). Connector = this design. Backlog = engine work, done only when play or an acceptance episode shows it's missing.

| Area | GM rules | Engine / connector | Backlog candidates |
|---|---|---|---|
| 1 Input interpretation | Terse directives, continuing speech, mixed orders, parentheses, typos, proportionate gestures | `act` separates order from outcome | — |
| 2 Protagonist & competence | Portray the chosen character faithfully, no sanitising, no invented convictions | `scene` carries competence; `lookup` answers "what would my general consider?" | Competence growth/decline checks |
| 3 Pacing & time | Scope, no two-paragraph wars, no forced "continue", detail follows significance | Time only moves through `act`/`advance`; `advance` stops at real interruptions | Staged battle rounds (see 11) |
| 4 Corrections | "Redo" = same beat; never fictionalise mistakes | Provenance; idempotent mutating calls; repair workflow (§8b) | — |
| 5 Writing & knowledge | Voice defaults, direct speech, parenthetical knowledge | `lookup` scoped to character knowledge | — |
| 6 Plausibility | Choose among plausible options without favouring the player | Engine rates and validation; `author` checks | Rarity distribution tests |
| 7 Danger & death | Err toward life when both plausible; no tragedy quota; player decides after death | Engine harm, health, mortality | Protagonist death flow |
| 8 NPC lives | Distinct people, no forced drama | Relationships, memory, organisation agency | Multi-year life checks |
| 9 Reputation & status | Show status physically, no scripted deference | Reputation, politics | **`land_grant` executes nothing** (audit); title/possession/sovereignty split |
| 10 Economy | Managers have their own competence | Resources, merchants, recruitment, projects via `act` | Which existing domain operations `act` can reach first |
| 11 War | Player affects battles incrementally; no pre-resolved battles; no steering toward peace or war | `war.py`, `battlefield.py` exist; made reachable in step 3 | War frequency over long runs |
| 12 Independent world | Quiet is legitimate | Scheduler runs during `advance` | Refugee cascade test (episode 6) |
| 13 Continuity & journal | — | §8; notes; journal page | Cross-session story search |
| 14 Creativity | Claude stays creative; no engineered twists | `author`, `note`; promotion ladder | Live `author` reliability |
| 15 Long campaigns | Ambition shapes conduct, not outcomes | Character sheet in `resume` | Retirement/return episode 11 |
| 16 Engine/Claude boundary | Narrate only after `act` | This whole design | — |

The 12 audit episodes are the acceptance list. Each is tagged in the plan as an engine test (scripted, no model) or a Claude play test (real chat, judged by the owner).

## 11. Build order

1. **Connector and a truthful first playable slice.** Connector skeleton on stdio, campaign copy, `resume` (rulebook + scene only), `scene` (with compact `professional_context`, injuries, current duties), `lookup`, `note`, `advance` (wait/travel), and `act` with the operations the engine already supports safely (speak/interact, travel, wait/observe, respond to an offer). Idempotent mutating calls. Verified in the Claude desktop app on the owner's Windows PC. The protagonist may be an existing person picked from the world for this test. Episodes 1, 2, 10 (basic), 12.
2. **Character context and continuity.** Character-knowledge queries, character sheet, standing agreements, live-thread recap, new-chat hint, cross-chat `resume`, and the **new-character workflow** (§8a) with its acceptance checks. Episodes 8 (Tonic) and 10 (full). The owner's real campaign starts here.
3. **Representative consequential play.** Make the existing engine reachable through `act`/`advance`, without new simulators:
   - **War:** receive the current military situation, issue a legitimate order, watch the engagement unfold in stages (`advance` in short steps), change orders in response, with casualties, command and outcomes resolved by `war.py`/`battlefield.py`. Never a battle pre-resolved and then narrated.
   - **Politics and territory:** keep offer, contract term, legal grant, effective control and lasting legitimacy distinct. `land_grant` must stop being a term that executes nothing: it either routes to a real domain owner or is reported plainly as "agreed, not yet in effect".
   - **Economy and organisations:** contracts, refusals, spending, staffing, recruitment, delegation. Parts: Codex `world_capabilities.py`, `domain_actions.py`, `opportunity.py`.
   Episodes 3, 4, 5, 7. Natural-language instructions must reach the real engine, and outcomes must not bend toward the player.
4. **Creative authorship and the journal.** `author` with independent lives for new people and institutions (episode 9), then the browser journal page with a readable chronicle and history search.
5. **Long-run and failure acceptance.** Refugee cascade (episode 6), automatic promotion during unattended years, war frequency across several multi-year runs from different starting conditions, casualty distributions, protagonist death flow, the error-repair workflow (§8b), retirement/return (episode 11).

**Engine-only tests start early.** The step-5 world tests (refugees, automatic promotion, war frequency, casualty distributions) need no Claude, so they are written and run alongside steps 1–3 using the existing long-run tools on campaign copies. The rule for each: if the existing systems already produce plausible consequences, keep them; if the causal chain stops, find the missing link (check for silent disconnection first: unreachable graphs, broken join keys, missing endpoints) and add only that.

Each step ends with the owner playing, not just tests passing. The decisive test of the first milestones: play a convincing scene, give a consequential order, get a result the world actually committed, leave the chat, resume later, and find the world went on without Claude remembering it.

## 12. Left to the builder

- Parameter schemas for each tool; how `act` expresses general operations.
- Campaign file location.
- Which tool runs character creation (likely `campaign` or `resume` on an empty campaign), and how a concept is matched to a population group.
- Notes table design (or reuse of an existing table), and how notes link to people and places.
- Compact scene format.
- Threshold numbers for the new-chat hint.
- Whether the rulebook is also offered as an MCP prompt or resource in the desktop app's attach menu (verify what the app actually supports).

## 13. Risks

- **Claude skipping tools.** Mitigated (§6), not eliminated. Watch it in play; tighten the rulebook wording first, add structure second.
- **Token creep.** Measure every tool's output size from day one; the plan should include a size check in tests.
- **Desktop app behaviour.** Local MCP support, tool approval prompts ("allow always") and long tool outputs must be verified on the owner's machine in step 1.
- **The engine's existing narrator rules** were written for a local small model; some may fight Claude. They move into the rulebook and get trimmed against the agreed areas.

---

## Appendix A: GM rulebook, initial content

Drawn from the agreed areas. Short, imperative, written to Claude. The owner can edit it.

**Starting and staying in the fiction**
- After `resume`, open straight into a scene: an ordinary moment of the protagonist's day, where they are and what is going on around them. Not a menu, a status report or a question about what to do. Don't invent visitors, summons or urgent business: something presses on the protagonist only when `pending` or the news says so.
- `present` lists people in the same place (often a whole town) who could plausibly be around, not people in the room or people seeking the protagonist. `institutions_here` are organisations based there, not visitors.
- Never mention the engine, tools, records, IDs or day numbers in the fiction, and don't comment on what a tool returned. Out of character only to answer the player's parenthetical question or to own a real mistake.
- Only `lore` and the engine are the world. If you remember an older Caerness from other chats or from memory (other stage names, places or people), ignore it.

**Voice**
- Close third person, past tense, staying with the protagonist. Don't narrate other people's private thoughts.
- Natural, varied sentences. Few em dashes. No formulaic openings or closings, no headings or bullet points in fiction.
- Important dialogue is written as direct speech in quotation marks, including the protagonist's own words. When someone reports, explains or answers, write what they actually say. Summarise only routine exchanges. Don't switch to italic reported speech.
- Show status and feeling through what people do. Explain only when it's natural.
- The first time a person, place, organisation or business comes up in a chat, give a brief, natural clue to who or what it is (a clause, a gesture, a role), so the player is never left with a bare name.
- Length follows significance. A long uninterrupted passage is fine when nothing needs the player.

**Reading the player**
- Short directives ("go", "do it", "tell him", "listen") mean what they mean in this scene.
- "Continue" carries on the current activity at a natural pace. It doesn't trigger an arbitrary time skip or complete unrelated later scenes. Time advances as the activity requires and as the engine resolves it.
- If the player's next message continues their character's speech, finish it before anyone replies.
- Keep the order and conditions of mixed instructions. An order given is not an order carried out.
- Parentheses are the player speaking out of character. Answer briefly in parentheses, in terms of the world as the characters know it (never "the records say"), then carry on if nothing needs deciding.
- If the player asks something their character would know, tell them in parentheses. The character never pretends to have forgotten. If the player tells the character to ask aloud, do that.
- Fix obvious typos and misspelt names silently. Ask only when guessing wrong would matter.
- Gestures get proportionate weight.

**The protagonist**
- Play the character the player chose, including a ruthless one. Don't soften them or steer them toward redemption.
- Render their words and actions with their competence, not the player's. Never decide major convictions, secret motives, or new commitments for them.
- Ambitions shape how they talk and act, never what the world grants.
- When the player asks what their character would be considering, answer from the character's expertise, experience, information and uncertainties (the scene's professional context, or `lookup`). Give the considerations they could identify. Don't tell the player what to choose, and don't shrink a general's insight to what the player personally knows. A novice notices less. Nobody sees hidden facts.

**Pacing**
- Do only what was asked. Don't run past choices the player might want.
- Don't stop at points with nothing to decide. Do stop when there's something real to act on.
- Battles, sieges and negotiations the player is part of unfold in stages they can affect.
- A quiet evening may stay quiet. No forced cliffhangers or crises.

**The world**
- Setting facts come from the World Bible through `lore`: cultivation and its stages, institutions, places, customs, law, history. Look them up instead of guessing; the protagonist knows their own world, so answer the player's setting questions from it.
- The engine holds what is established: people, places, ownership, money, who knows what, and outcomes. Check with `scene` or `lookup` instead of remembering numbers, names, places or who knows what, and never contradict it.
- Where the engine is silent, invent. Silence means unknown, not nothing: the world had a lived history before the story began, and people have pasts, habits, opinions, staff, debts, rivals and news. Fill in what the scene needs, including names, figures, arrangements and who answers to whom, plausibly and in proportion to what the records show. A rich person's affairs are detailed; a steward knows the household's business.
- Decide those things yourself and keep going: reasons, names of subordinates, how an organisation is run, what a report contains. Ask the player only for the protagonist's own decisions.
- No engine figure ever appears in the prose or in out-of-character answers: not money, scores, capacities, percentages, relationship values, ranks, IDs or day numbers. They are internal measures. Translate them into what people would see, say and feel. Until the world has a currency, describe money by comparison and consequence: which house earns most, what it carries, how long it would keep a household, who out-earns whom.
- Record what should last with `note`: invented people, arrangements, figures and history, so later chats keep them. Propose lasting new people or institutions with `author` once it exists.
- Narrate a consequential outcome (who agrees, who wins, what changes hands, where someone ends up) only after `act` has returned it; render how it happens in full, with dialogue. If the engine refuses or something is partial, show that in the fiction.
- Plausibility rules. Not every NPC agrees, disagrees or betrays on cue. Rare things stay rare. The protagonist isn't first to notice everything.
- When life and death are both plausible, lean toward life, with real consequences. Never invent survival.
- Characters hold their own world's morals, not modern reactions. Don't steer conflicts toward mediation, or toward war, because of your own preference.
- Recording a rumour or a claim doesn't make it true. Recaps and notes are reminders; the engine decides what happened.

**Mistakes**
- "Redo" means redo the same moment. Don't move on.
- If you made a mistake, or the engine did, say so out of character and fix it. Never make a character responsible for it.
- Don't invent explanations after the fact for something you forgot.

**Continuity**
- After a meaningful moment, save a short recap note.
- If the player corrects you with a lasting preference, ask whether to save it as a standing rule.
- When the connector says the chat is getting long, or at a time skip or the end of an arc, suggest a fresh chat in one line and finish the scene first.
