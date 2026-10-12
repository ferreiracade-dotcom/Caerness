# Caerness — Narrative Direction Clarifications (Owner, 2026-10-12)

**Status:** owner-authored design intent clarified in conversation; planning-branch guidance for coding agents, not an implementation claim.  
**Applies to:** first playable narrative loop, player action resolution, story pacing, event exposure/creation, mortality, simulation-cost choices, and future visuals.  
**Companion:** `docs/plans/2026-10-12-player-first-agent-implementation-brief.md`.

## Primary product, priority and authorship

Caerness is **a character-life RPG**, not a simulation research project. The persistent world exists to make personal stories causally credible, varied and consequential. The immediate product is excellent **text-based / potentially voice-assisted play**, with vivid, correct, responsive prose and rich character interaction. A third-person 3D observation client is **explicitly deferred**; optional illustrations can enhance narrative scenes but are not a required interface and should not delay the text game.

Authored content is welcome and already substantial: `canon/world_bible_current.docx` supplies cultures, social customs, countries, institutions, martial metaphysics, geography, religion, etc. Authored locations, local hooks, relationships, distinctive institutions or initial circumstances may enrich play. Avoid the false dichotomy "authored content or emergent game." The rejection is of **forced predetermined plot outcomes**, not of authored worlds, situations or quality writing.

## AI and free-form action resolution

The existing intended architecture is correct: natural-language player intention -> AI interpretation/plan -> constraints and available actors/assets/relationships/resources -> validated executor and transactions -> state-constrained narration. **The design already intended to overcome closed command lists**. The existing v0.6-style enumerated interpreter/action bridge is an incomplete implementation, not the desired upper bound.

The player is free to *attempt* plausible activities; not free to demand that they succeed. Agents should first implement this original architectural intent, reusing and composing domain executors, with persistence and safe failure modes; do not simply add dozens of rigid verbs.

## Controlled protagonist fortune: three distinct levers

The owner revises absolute "camera has no causal privilege" as a blanket gameplay rule, **without abandoning the independently developing world**. The game may modestly favour an interesting *life*, not predetermined success.

1. **Presentation / salience:** where multiple valid observations exist, surface relevant or curious details; allow quiet life, ordinary work, success, romance, stability and positive milestones as well as crisis. Not every detail is portentous.
2. **Plausible opportunity incidence:** when several causally admissible events/encounters could naturally occur in the character's current setting, modestly favour an opportunity, encounter or unfolding situation that might support engaging play. This can affect whether a possible situation actually arises—not just which already-real fact the narrator notices. Its prerequisites must remain grounded: no teleporting famous antagonists, fake wealth, summoned contracts, retroactive biographies, fabricated family, guaranteed tournament or forced personal drama. Opportunities may be positive, neutral or challenging. They do not promise attention, victory, loyalty or success.
3. **Soft survival bias in genuine uncertainty:** if the player character could plausibly live or die in a specific unresolved situation, prefer a credible survival outcome. If causality clearly entails death, death happens. Survival can still entail wounds, capture, grievous losses, permanent disability, humiliation, and expensive recovery. Consequences accumulate, so intentionally reckless repeat attempts must not become risk-free. Avoid precise probabilities until calibrated through experience and tests.

**Outcomes once an event exists:** skill, means, information, risks, opponents' intentions, actions and context still determine whether a project succeeds, a rival wins, a candidate refuses, or a battle is lost. Player-centred fortune must not quietly nerf enemies, guarantee contracts or make all NPCs care about them.

**Independence remains:** distant wars, marriages, businesses, political changes, deaths and careers proceed without requiring the player; important NPCs develop independently; camera attention does not make unrelated people destined for significance. Background causality is unchanged except for the narrow and auditable opportunity/survival allowance above.

**Limits:** Not every ordinary day requires an incident. A genuinely uneventful circumstance may stay quiet. Avoid "adversity debt" (forcing tragedy after success) and "luck quota" (contrived reward patterns). Preserve quiet periods and let the player freely skip them.

## Documentation conflict to reconcile, not conceal

Existing source material differs:
- `DESIGN.md` §27.3: "The camera may be lucky about what it gets to see. It is not lucky about what happens next." This allows salience bias but not the newly clarified opportunity-incidence bias.
- `POST_V07_ARCHITECTURE.md` §4.4: "Soft plot armour may modestly prefer continuation only inside genuinely uncertain outcome space."
- `README.md` development rule 5: "No plot armor."
- Some anti-camera rules appear absolute.

Treat these as an **unresolved historical contradiction now clarified by the owner**: bounded narrative fortune is permitted **only within credible uncertainty**, with a preference toward interesting opportunities and continued life, not guaranteed results or causal exemptions. Future implementation agents should propose a tightly scoped revision of these older documents before introducing code relying on the revised probabilities; do not silently overwrite historical records.

## Simulation economy

Preserve systems that generate independent opportunities, plausible wars/contracts, genuine talent, social reactions, institutions, history, and consequences. Reduce model fidelity/cadence for low-value background work if benchmarks and comparative scenario tests show it can be done without breaking these experiences. The goal is **enough causal resolution to produce excellent character stories**, not exhaustive statistics.

The strongest immediate engineering tests are:
- free-form player intentions can engage real executors;
- long, intelligent, consistent conversations;
- prose paints lived-in scenes and accurate social recognition;
- time skips preserve independently unfolding world consequences without procedural busywork;
- opportunity generation can be selectively weighted without fabricated prerequisites or hidden guaranteed success;
- genuine but nontrivial loss/death risk remains.

## Later visuals

Future standalone third-person observation is a **way of witnessing the protagonist's effect on people and places**, closer to Manor Lords' Visit Mode with optional interactions returning to prose: see a growing town, destroyed building, guards bowing, organisational uniforms and activity. It need not animate every conceivable free-form action or match the narrative engine's open-endedness. **Do not start Unreal production as part of current narrative work.**

## Agent authoring and acceptance requirements

The owner does not code. Agent tasks must specify scope, existing source-of-truth files, causal invariants, reproducible tests, safe database copies, gameplay quality criteria, and exact deliverables. Prompts are essential but **tests, code review and actual human play are additionally necessary**. Never equate a successful unit test with genuinely enjoyable prose, or a plausible narrative with a verified committed world event.

Do not interpret this clarification as permission to modify the engine's live day-0 database, rewrite canon, or retroactively change established events.
