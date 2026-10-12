# Caerness — Agent Implementation Brief: Player-First Vertical Slice

**Date:** 2026-10-12  
**Status:** implementation brief only; no engine implementation authorised by this planning branch  
**Parent audit:** `docs/reviews/2026-10-12-player-first-simulation-audit.md`  
**Primary repo:** `ferreiracade-dotcom/Caerness`

## Product objective

Create an enjoyable, persistent, free-form character-life RPG. The **player is the camera, not the cause of everything**, and may attempt any plausible action. The world determines outcomes. The player's words convey decisions, not engineering instructions: competent character and NPC delegates execute ordinary details. The experience should support long rich conversations, meaningful social recognition, discovering and elevating talent, personal martial excellence, institutions, projects, war and mercenary careers, and seamless time compression. The narrative/voice interface must be fully playable on mobile. An optional **standalone** PC third-person observation client is a later complementary mode, visually oriented toward grounded modded Skyrim/Kingdom Come/Manor Lords. Prefer licensable Unreal technology and reusable packages to building an engine; never depend on proprietary decompiled game code.

**Owner requirement:** all coding, builds, tests, scene assembly, editor automation and debugging must be performed by development agents. The owner only sets direction, supplies installation/licence authorisations where unavoidable, and playtests.

## Non-negotiable game design

1. World state, law of consequences, knowledge and chronology are authoritative. Narration cannot quietly create entities, relationships, holdings, contracts, wealth or victories. Do not grant player advantage merely because the camera follows them.
2. NPC agency is real; relationships contain mixed feelings; loyalty and refusal are possible; significance and attention alter simulation resolution, not eligibility for success.
3. Free-form intent is unrestricted but may be infeasible. Never silently convert an unsupported proposal into mere observation or claim it happened. Explain blockers in-world and allow alternatives, revisions or longer processes.
4. Conversations may continue for many turns within the same scene, including sensitive, quiet, ordinary or emotionally important exchanges. Scene progression is not forced by the agent's need for plot.
5. Player can advance hours, days, months and years without performing repetitive work. Meaningful decisions and causal interruptions can stop a skip; delegations proceed without micromanagement.
6. Individual ability and institutional/social/material standing are distinct. A great spearman need not be a ruler; a successful patron need not be an extraordinary fighter.
7. Information is situated and may be incomplete or wrong. NPCs recognise the protagonist only if their actual information and social situation warrant it. Fame is not universal.
8. All UI choices are optional prompts, not a closed action menu. No fake victory loops, arbitrary success or mandatory administrative spreadsheets.

## Work sequencing (agent executes, user reviews)

### Track A — baseline and evidence

- Check out a new implementation branch from latest `master` after design approval. Never use the live day-0 DB for tests.
- Run `tools/run_suite.py` and fresh snapshot/benchmark; record host specs, revisions, failures and reproducible commands.
- Verify whether Schema 108 wars, contracts and background progression actually activate. Compare claimed handoff to running evidence, not blindly to earlier reports.
- Add scenario-specific end-to-end test harness for narrative turns and world causality before feature work.
- Produce a concise owner-facing report with pass/fail, not code excerpts as the primary deliverable.

### Track B — narrative action bridge (first priority)

- Preserve `engine/actions.py` / `engine/model_gateway.py` separation: LLM proposes *intent*, validator checks world state and capabilities, deterministic domain executors mutate via transactions, narrator reports only committed outcome.
- Inventory existing domain executors and map them to typed intents with parameter validation, identity resolution, location/authority/resource constraints, refusal states, costs and time.
- Support an extensible compound-action workflow that can hold unresolved substeps and delegate routine subactions, without arbitrarily adding a dozen bespoke player actions.
- Initially cover: character approach/conversation, hiring and elevating an NPC, assigning organisational responsibility, project commissioning and delegation, investigating a lead, searching for a mercenary contract, and voluntarily ending/interruption of scenes.
- Unsupported actions remain pending for a defined implementation/clarification path; never claim that nothing is possible merely because one intent vocabulary omitted it.

### Track C — multi-turn conversation scenes

- Establish a persisted conversation session linked to actual actors, time, location, relationships and knowledge access.
- Each turn can express dialogue, actions, questions and changes of tone, without each utterance triggering `accept/refuse` relationship bookkeeping.
- Relevant facts, promises, threats, discoveries and concluded agreements are written as consequential anchors after validation; insignificant exchanges may remain narrative memory with sensible bounds.
- NPCs may disagree, initiate topics, interrupt for causal reasons, stay silent or end conversation. A participant can have admiration and resentment simultaneously.
- Separate temporary emotions and local perceptions from durable commitments and trait development.
- Human playtest a 15–20 turn reunion and 10–15 turn defeated-commandant negotiation. Check continuity, personality, pacing and genuine disagreement.

### Track D — narrator and mobile game UX

- Design scene packet to prioritise salient independent activity: places have routines, construction, small changes, inhabitants, sounds, ongoing work and local social protocols. Do not generate random decorative anomalies without causal support.
- Responsive narrative density: brief for familiar routine movement, rich for new/changed surroundings or player attention, deliberately slow for chosen conversations; no automatic time leap.
- Character-competence layer handles routine tasks and speech mediation; no technical combat writing or manual procurement.
- Ensure phone text is readable, can be spoken and navigated with minimal interaction; explore voice/input integration if available, but no mandatory remote cloud or fragile manual copy/paste as the only reliable mode.
- Preserve Scene / Matters / World / Ledger / You or improve them only with tested user benefit.
- Keep hidden information hidden, even in optional reports/news and recognition events.

### Track E — world plausibility and calibrated background development

- Validate political-economic-war-contract causal chain, project funding/material/work-time limits, NPC recruitment and promotion, personal cultivation progress.
- Complete only the minimal background-to-notable emergence necessary to make independent discoveries demonstrable, maintaining identity continuity and stable history under changing resolution.
- Do not force a war or celebrity to appear for the player. Use seeded alternative scenarios with plausible causes to prove that the pathway works.
- PERF-01 before full POP-01 or further large-scale system expansion. Any simplification proposal must prove conserved player-facing behaviour across seeded comparative runs.
- Maintain source-of-truth provenance for visual scene needs: recurring buildings, uniforms, people, activity slots, construction status, social responses.

### Track F — third-person observation technical spike (after narrative slice)

- Research Unreal starter projects, open/legally reusable code, NPC animation and medieval scene packages, licence restrictions, dependencies, version compatibility, editor automation, build reproducibility and agent control. Do not buy assets without owner authorisation.
- Define data boundary: `GET scene snapshot` returns player-observable current place, people, appearances, positions/roles, construction stage, activities and knowledge-limited contextual cues; `POST intent` sends player attempt to the same authoritative engine; Unreal never writes canonical world state itself.
- Prove a standalone UE prototype: one small courtyard; third-person locomotion; guards and independent civilian activity; warranted salutes/bows; approach NPC -> free-form conversation; text time skip -> visibly changed scene.
- Mark visual omissions truthfully: distant cohorts/LOD and simplified animations are fine; contradictory identities, architectures, injuries or project states are not.
- Third-person view is optional; narrator remains capable of conveying the whole experience. Do not require gamepad or PC for game decisions.

## Acceptance stories (must be playable, persistent, verified)

**Scenario A — The patron.** Player meets a long-serving merchant/officer, has a personal conversation, establishes a new division and appoints the individual. Authority, money, housing, personnel and nominee preference are evaluated; a feasible implementation persists roles/resources; conflicting officer resentment may develop, not automatically. Revisit in 6 months: division activities, career evolution and memories persist.

**Scenario B — The fighting-school discoverer.** An exceptional but originally unknown fighter emerged through simulated circumstances before the player noticed. Player discovers him, makes an offer, builds trust over time, appoints a trainer and returns years later. Fame may follow or fail due to ability, setbacks and rival opportunity. Discovery does not retroactively create talent.

**Scenario C — The ordinary conversation.** Reunion with a sibling unseen for 18 years; family already exists with intervening history; both parties possess grounded beliefs. Spend at least 20 player turns talking without forced exit, automatic affection or invented kinship. Recognition/resentment/curiosity arise independently.

**Scenario D — The mercenary market.** Political and economic pressure can independently produce plausible disputes and war, military need and contract requests. A company may discover opportunities through location/network/information. Competition and refusal possible. Searching does not cause wars to be generated on demand.

**Scenario E — The project and monastery.** Player commissions a church or martial compound via architect/steward; costs/time/labour bind; delegate execution; skip 12 months; revisit and see plausible physical/social changes and new unrelated activity, without managing individual stones or meals.

**Scenario F — The formidable wanderer.** A personally remarkable spearman or martial practitioner receives responses grounded in feats and local information without an organisation; higher rank/riches do not automatically grant superior personal combat. Combat consequences, injury and possible defeat matter.

**Scenario G — The observation client** (future gate). First-person world is not required. In standalone third-person, player enters the same headquarters seen in text, encounters consistent character identities/attire and simulated activity, interacts through narrative, and sees construction changes across a time skip.

## Quality gates

- **No fabrication:** 0 permanent facts authored by narrator outside validated state mutation. Detect contradiction and unsupported claims; audit text against known anchors.
- **Freedom:** each acceptance scenario is initiated by ordinary natural language, not secret CLI invocations or fixed button choices; sensible variants either resolve correctly or yield a clear in-world blocker.
- **Persistence:** save/reload/resume remains coherent; no forgotten family, magically replenished resources or replaced NPC identity.
- **Autonomy:** alternative seeded runs show refusals, independent successes and failures, mixed reaction, and independent events; no fixed quota of drama.
- **Time:** day/month/year skips execute reproducibly, preserving causality, interruptions and delegation; benchmark performance on current saved states.
- **Presentation:** story-quality human evaluation focused on scene density, surprise, empathy, hierarchy, recognition, narration pacing and mobile usability. Model response latency reported separately from world simulation cost.
- **No regression:** previously accepted deterministic and transactional invariants remain green on scratch DB copies.
- **Delivery:** agent supplies playable package/demo, reproducible build, test evidence, short change log and readable instructions; no code-writing task is assigned to the owner.

## Explicit stop conditions

Pause implementation and report a blocker rather than silently choosing a different architecture if: the world canon must be rewritten; a required external tool cannot be automated with available permissions; licensing is unclear; a change would create incompatible saves; a simplification changes causal results without review; or simulation/LLM time becomes impractical. Proposed trade-offs should include cost, benefits, impact on gameplay, and reversible migration steps.

## Definition of Phase 2 readiness

A **complete narrative vertical slice** reaches Scenario A + C + E at high quality on a fresh, safe campaign copy; war/contract and martial discovery paths have demonstrable independent causal tests; performance and current suite are measured; everything is operable through the existing phone-oriented interface; a future UE bridge contract is specified but 3D production is not a blocker.

**Do not treat this document as authority to claim that these features are already implemented.**
