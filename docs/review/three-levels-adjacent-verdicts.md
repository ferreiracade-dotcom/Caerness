# Three levels: what to do with the nearby code (Gemini's review, checked)

**Sources:**
- Gemini reviewed 48 engine modules next to the three-levels build, in the files
  `three-levels-adjacent-code*.md`.
- I checked its main claims against the code, and against a 120-day test of Saint Jude run from the
  opening.

**Status:** approved by the owner on 2026-11-26, as recommended on all four questions. Folded into the plan as Task 2b, Task 10a/10b, and additions to Tasks 3, 3b, 6, 11 and 14.

## The short version

**The main findings:**
- **Gemini is right on the main point.** Five side doors bypass what the design wants to be single
  paths. They are listed below.
- **Gemini is wrong in four places.** It would cut `temptations` and `settle_circle`, both of which are
  real features. It also called `advance_connection_legacy` dead code and overstated the noise.
- **The outfit machinery stays.** The `org_*` modules are the working level-2 layer. They are not
  competing with the personal path.

**The side doors:**
1. **The old decision loop still chooses for people.** The choice-builder in `decision_runtime.py`
   still offers ordinary people personal choices.
2. **A second "who is simulated how closely" ladder.** `resolution_controller` re-scores 5,879
   people on its own scale.
3. **News reaches the protagonist by other routes.** At least five push into the news feeds, around
   the gate.
4. **Every event becomes a rumour.** Each one is also mirrored into a belief table that nothing reads.
5. **Background rolls that ignore protection.** Several modules roll on people outside `life_matters`.
   One of them can choose for the protagonist himself.

## What I checked, and what it showed

**Decisions:**
- At day 120 there were 591 decisions: 238 outfit actions, 209 "consolidate" and 144 "start an
  interaction".
- The personal ones came from only 13 people.
- They come from `decision_runtime._builtin_candidates`. It always adds the relationship, ordinary and
  belief-investigation choices next to the `org` provider.
- The contract's claim that the old `decisions` table is "empty in Saint Jude" is wrong.

**Rumours and beliefs:**
- All 200 events of the 120 days (births, unions, coming of age, deaths, successions) became rumours.
  They produced 9,665 exposures.
- `actor_beliefs` (10,016 rows) has exactly as many rows as `knowledge_provenance` (10,016), and there
  are 0 belief revisions.
- So it is a mirror that nothing reads, apart from the old decision context.

**`resolution_controller`:**
- It runs in Saint Jude. Every due cycle it reviews `entity_resolution` (5,879 rows), promotes and
  demotes people, and syncs `simulation_profiles` tiers.
- That is a second level system next to `actors.sim_resolution`.
- Its code also holds world words: "king", "emperor", "bishop" and a list of fantasy first names.

**`crystallization.py`:**
- Nothing imports it at run time.
- When the design says it "keeps crystallization", what is really used is the materialization of
  unnamed people: `resolution_controller._materialize_latent_person`, called from `opening_family` and
  `household_life`.

**`org_happenings._roster`:**
- It rolls weekly happenings on every seated associate, with no check for the protagonist.
- Those happenings include **informs, goes straight, switches and holds out**. These are choices.
- If the protagonist ever holds an associate seat, the engine would choose for him. That breaks the
  rule that the engine never chooses the player's intentions.

**`opening_family.resolve_unnamed_marriages`:**
- It runs every 30 days through `household_life`. It skips only the protagonist.
- Task 14's lock list does not name it, nor the other background rolls Gemini found.

**`temptations`:**
- 1,337 rows, all of the kind "Frank Pugliese took sharp clothes for going out" or "Ray Fontana took a
  car".
- It is a designed feature: wants, chances with a price and a deadline, and contests for a chance the
  protagonist sits on. The scene's market view and the time-skip read it.

**`settle_circle`:**
- `ensure_purse` creates a purse only for someone who has none. It never tops one up.
- So it fills in a fact nobody had counted yet. It is not minting money.

**`advance_connection_legacy`:**
- It is the reference for `tests/arch01_process_registry_test.py`, so it is not dead code.

**`emergence`:**
- It made 0 threads in Saint Jude, and `actor_memories` grew by 283.
- That is minor, but its consumers need checking before it is cut.

**The Caerness economy processes:**
- They run in Saint Jude, but on empty tables. Switching them off is tidying, not a fix.

## Proposal

### A. A new Task 2b, before Task 3: switch off the competing paths

These changes are small, local and verified. Without them, the build's numbers (the life test, the
scoring sheet) would be measured against a world where the old loop is still choosing.

1. **Personal choices off in Saint Jude.**
   - `decision_runtime._builtin_candidates` offers only the registered providers (`org`) and "hold
     position" when the world package says so. This is a package switch, not a check on the world's
     name.
   - `decisions.build_actor_context` is skipped when only `org` runs.
   - Expected result: the 209 "consolidate" and 144 "start an interaction" decisions go to 0, and the
     outfit actions are unchanged.
   - Equivalence check: outfit actions, money and incidents should stay within the ranges of the
     existing S1 test.
2. **The belief mirror off.** `information._upsert_knowledge` stops calling
   `belief.mirror_legacy_knowledge` in Saint Jude.
3. **The protagonist taken out of the choice-type happenings.**
   - In `org_happenings`, he no longer gets informs, goes straight, switches, holds out or drifts.
   - Things that happen to him (busted, incident, a favour asked) stay, because he lives under the same
     rules.
   - A test seats him as an associate and runs 52 weeks.
4. **The contract and design corrected.**
   - The "empty in Saint Jude" line comes out.
   - Section 8's "crystallization" is renamed "materializing unnamed people
     (`_materialize_latent_person`)".
5. **Optional tidying:** a package switch for the Caerness-only processes (agriculture, logistics,
   merchant, craft, growth, war, ecology, education, patronage, seeking, attention, psychology, world),
   so Saint Jude does not run them.

### B. Into the build's existing tasks

**Task 3 (levels):**
- `levels` takes over what `resolution_controller` does in Saint Jude: tiers, cadence and promotion.
- The `resolution` process is switched off there.
- `_materialize_latent_person` stays, but it sets `sim_resolution` and stops creating profiles that
  feed the old loop.
- `tiers.py` keeps people at the `active` level on the daily clock.

**Task 3b (routines):**
- `routines.where` also reads custody (held), prison stays, sentences being served, and travel that is
  under way.
- Without that, an arrested man still "is at work" when a scene opens.
- After this, `presence.py` loses its last callers (`outings.crowd`).

**Task 6 (undo):**
- `commitments.record` and `complete` go through the undo log.

**Task 10 (the news gate) grows: every route into the player's news goes through the gate.**
- These come in by side doors today:
  - `hearsay.reach` and its path logic (the gate is built from it);
  - `life_matters.weekly`'s hearsay call;
  - `claims.deliveries`;
  - `civic_tick._tell_player`;
  - `texture` delivery;
  - the protagonist's new chances from `temptations`;
  - `findings.tell` and `learn`, which also need `path_kind` and `basis`.
- `information.py`'s event-to-rumour broadcast is switched off in Saint Jude.
- Crime reports with high publicity (`public_attention`) become the paper and radio channel.
- **This roughly doubles Task 10, so I'd split it:**
  - **10a,** the gate and the channels;
  - **10b,** moving each side door onto the gate, one test per door.

**Task 11 (the brief):**
- `outings.go_out` stops returning `you_may` (a fixed list of moves: talk, dance, ask for her number,
  leave together). That is the kind of menu the rules forbid.
- Pre-rolled happenings and `approach` go to scenes.

**Task 14 (protection) names every background roll that can touch a protected person:**
- `life_matters` (already planned);
- `outings` (flings and scuffles);
- `opening_family.resolve_unnamed_marriages`;
- `household_life` planned births;
- `civilian_life`'s revealing of a grown child nobody knew about;
- `claims._react`;
- `org_happenings`: the roster, the victims, the bystanders and the nearby earner;
- `temptations` for other people;
- `org_succession` and `org_coup`, which may not vote, spend or plot for the protagonist;
- `crime_response`, which may not plead for the protagonist.

The test protects one person of each kind and runs a year.

### C. After the slice (step 7 and later; noted, not planned now)

- **Big underworld and civic moves carry a causal chain and publish channel shocks:** killings across
  outfits, coups, civil wars, installing a new head, sweeps, elections.
- **Movers' own plans go through concern and decision, and land on the outfits' agenda.** Their duties
  stay with the outfit procedures.
- **Deleted once the slice is proven:**
  - the old delivery ledger;
  - `hearsay.material`;
  - `information.py`'s rumour spread;
  - `presence.py`;
  - the personal half of `decisions.py`;
  - `motives.py`;
  - `domain_actions` for Saint Jude.
- **Step 6 contests replace two resolvers in `interactions.py`:** its attack and social resolvers.

## Where I depart from Gemini

| Gemini | My view | Why |
|---|---|---|
| Cut `temptations` | **Keep it**: lock the other people's draws, and send the protagonist's chances through the gate | It is the only thing that turns wants into spending. The design has nothing to replace it. |
| Cut `settle_circle` (it "mints cash") | **Keep it**, and later move it into level promotion | It only fills in a purse nobody had counted. Unknown is not zero. |
| Strip `_materialize_latent_person` from `opening_family` | **Keep it, re-pointed at `sim_resolution`** | Marrying into the unnamed population is what keeps the city's families real. |
| Disable 17 processes before the build | **Optional tidying** | They run on empty tables and change nothing. |
| `advance_connection_legacy` is dead | **Keep it** | The registry equivalence test uses it. |
| Hide what the protagonist doesn't know from the GM (`outside_his_knowledge`, cutaways) | **Owner's call** (below) | It decides what kind of game master the brief makes. |

## For the owner

1. **Approve Task 2b** (section A) as a step before the build?
2. **Split Task 10** into the gate (10a) and moving the side doors onto it (10b)?
3. **Keep `temptations` and `settle_circle`** against Gemini's advice?
4. **What should the brief show the GM about the world the protagonist can't see?** Today the brief has
   an "outside his knowledge" part and "cutaways". Gemini would remove both.
   - With them, the GM can foreshadow and play people who know more than he does.
   - Without them, the GM can't leak what the protagonist couldn't know.
   - I lean to keeping a short part for things that are building and cross his path, which is what the
     design already allows, and dropping the rest.

## The owner's answers (2026-11-26)

1. Task 2b: yes.
2. Task 10: split into 10a and 10b.
3. `temptations` and `settle_circle`: keep both.
4. The brief: only what is nearing him; the "outside his knowledge" part and the cutaways go.
