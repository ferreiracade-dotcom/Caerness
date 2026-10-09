# World Bible to narrator: coverage pass

**Date:** 2026-10-09
**Checkpoint read:** `master` at `b118590` plus the docs on `claude/epic-clarke-npsvru`
**Question:** COVERAGE-01 (2026-09-17) checked that every World Bible domain has a *simulation* owner. Nobody checked the other direction: when a scene needs a World Bible rule about how things look, sound and behave, does the narrator get it? The owner kept having to remind the old Narrative Engine games about deference, dress and stature. This pass asks whether Caerness would do the same.
**Tool:** `tools/canon_delivery_probe.py` (repeatable; run on a database copy).
**Nothing here changes engine code.**

## 1. What the World Bible itself says the engine should do

The design intent is already written down, and it is right:

- **Part 25 §XII, "Narrative Engine integration":** "The engine should not convert every cultural statement into a numerical variable. Formality, religion, local custom, class display, beauty, shame, prestige, artistic taste, fear, grief and the meaning of institutions often belong in the interpretive narrative layer. Deterministic state is for continuity; prose canon is for understanding what that state means."
- **Part 0, "How to read the world: two lenses":** *Presence and visual identity* ("Recognition precedes introduction, and the world reacts to the announcement") and *Formality as the response to power* ("a breach of that grammar is itself a legible and consequential act"). These are "the lenses for reading almost any scene."
- **Part 3, "Recognition and social presence":** "The greater a person's standing, the less they ordinarily need to announce it themselves. Other people do the announcing… Reaction should vary."

So the World Bible splits the work three ways: **state** remembers, **simulation** moves the world, and **prose canon delivered to the narrator** makes the state mean something. Caerness has built the first two. The third is where the remembering fails.

## 2. Measured: what the narrator actually receives

The narrator gets World Bible text only through `search_canon`, six passages per scene, chosen by full-text match on a query built from the place name and kind, the protagonist's name and role, the player's request, up to four present people's names and recent event titles (`engine/player.py:171-182, 228-229`). The World Bible indexes into 601 passages under 434 section headings.

`tools/canon_delivery_probe.py` ran 400 plausible scenes against the packaged opening world (2,400 slots), using real places, real people present there, and fifteen ordinary requests ("I walk into the inn…", "I greet the clan head", "I buy new clothes", "I sit by the fire and talk with the prisoner", "I collect the protection money"…):

| Finding | Number |
|---|---|
| Slots spent on **Part 24, the simulation registry** (headcounts, name lists, anchors: engine data, not scene material) | **866 of 2,400 (36%)** |
| Slots spent on **Part 25, Open Questions** (undecided canon, delivered as if settled) | **75 (3%)** |
| Sections ever delivered | 205 of 434 |
| Part 0 (including the two lenses) | 0 |
| "Formality, familiarity, and etiquette"; "Fear, respect, and the same bow"; "Power, authority, and etiquette" | 0 each |
| "Dress and visible status"; "Clothing, repair, and visible class" | 0 each |
| "Regional variation"; "Outsiders and acculturation"; "Regional social expressions" | 0 each |
| "Death in a martial civilization"; "Ancestors, mourning, and the dead" | 0 each |
| "Underworld justice and dispute resolution"; "Gossip, intelligence, and information laundering" | 0 each |
| "Presence" (Part 2); "Naming grammar for martial arts" | 0 each |
| "Recognition and social presence" | 4 |
| "Challenge culture" (two sections) | 17 |

**Why:** the query is dominated by proper names, and the passages densest in proper names are the registry lists. A rule about bowing contains no names, so it never wins.

Caveats: day-0 world, so no event titles in the queries; requests are a fixed sample; random seed 7. The pattern does not depend on these: rules without names lose to lists with names.

## 3. Every Part, sorted by how it should reach the narrator

Keyword search is the right channel for only one of these six kinds of material.

| Class | What it is | Parts and examples | How it should be delivered | Today |
|---|---|---|---|---|
| **A. Lenses** | Rules for reading any scene | Part 0 two lenses; Part 3 Power/authority/etiquette, Recognition and social presence, Formality/familiarity, Fear/respect/same bow, Culture is not alignment; Part 2 Presence | **Every scene**, as a short fixed brief | Never (0–4 of 400) |
| **B. Culture of a place and its people** | How people dress, eat, greet, mourn, worship and behave in this region and class | Part 3 Dress, Regional variation, Outsiders, Family, Marriage, Ancestors, Death, Popular martial culture; Part 9 Long Road way of life; Part 12 each religion; Parts 13–19 "Character and economy", religion; Part 21 Clothing, Food, Housing, Privacy, Regional social expressions; Part 22 regional underworlds; Part 23 regional cultural traditions, Fashion | **By the scene's place and the cultures of the people present**, as a culture brief per culture | Almost never |
| **C. Situation rules** | Rules that apply when a kind of thing happens | Challenge culture by Current (Part 3), Part 10 challenges and tournaments, masters and disciples, mourning, courtship, trade and escorts (Part 11), underworld justice, gambling, nightlife, assassination conventions (Part 22), medicine, injury, addiction (Part 21), news, gossip, reputation (Part 23), Presence, naming of arts (Part 4) | **By what is happening in the scene** (a challenge, a funeral, a negotiation, a wound) | Sometimes, by luck |
| **D. Entity lore** | Facts about a specific institution, city, ruler or house | Parts 5–8 institutions; Parts 13–19 governments and cast; Part 11 named houses; Part 20 cities and routes; Part 22 named families and syndicates | **By link** from the people present (their institutions) and the place (its owner, its city entry), not by keyword | Partly; links do not exist |
| **E. Engine-only** | Calibration, headcounts, registry, design rules | Part 0 canon levels and naming rules; Part 1 calibration; Part 2 stage distribution; Part 24 registry and anchors | **Not to the narrator.** The engine already holds this as state. A present person's own registry entry may be included as a fact card | 36% of all slots |
| **F. Open** | Undecided canon | Part 25 | **Never to the narrator**, except Part 25 §XIII "no longer open" if it settles something | 3% of slots |

## 4. Simulation-facing rules in the World Bible that the engine does not yet hold

The World Bible's own "simulation-facing" lists (end of Parts 21, 22, 23; Part 25 §XII state table) ask for state that persists. Checked against `engine/`:

| World Bible asks for | Engine today |
|---|---|
| "Public reputation **by region or network**" (Part 23) | One global value per subject and domain (`social_reputation`, `engine/reputation.py:12-32`). A captain famous in one valley is equally known three kingdoms away. |
| "Major epithets" (Part 23) | Not found. |
| "Active scandals" (Part 23) | Not found. |
| "Known versus hidden identities"; "mistaken identity" (Parts 23, 25 §XII) | Not found. |
| "Rumours mutate… what version survives" (Part 23) | Rumours never change content; see the story-layer audit, RUMOUR-02. |
| "Presence and visual identity": the consequential are recognisable by "silhouette, dress, bearing… a single distinctive object" (Part 0) | No per-person or per-institution visual marks (no colours, emblems, signature objects) in the schema. |
| Actual skill, reputation, fame, respectability, authority and wealth are separate (Part 23) | Several exist separately (competence, reputation domains, offices, resources). Fame and respectability are not distinguished. |

## 5. Proposal: assemble the scene brief instead of searching for it (SCENE-01)

Replace the single keyword search with a brief assembled from what the scene is, in this order, each with a size budget:

1. **Lenses** (class A): one fixed brief, condensed from the World Bible sections above, always included.
2. **Culture briefs** (class B): one per culture involved: the place's culture, plus the culture of each present person whose culture differs. Written once from the World Bible, stored with references back to the World Bible sections they condense, so a World Bible edit marks them stale.
3. **Situation rules** (class C): each section tagged with the situations it governs. The turn's resolved action and segment kind supply the situation.
4. **Entity cards** (class D): from links (person → institution → its World Bible section; place → city or region section).
5. **Visible standing** of the protagonist and of anyone notable present, as each observer would read it (see the story-layer spec).
6. **Search** only for what remains, with Parts 0 (except the lenses), 24 and 25 excluded.

Laptop-first gives a larger narrator context, but the budget still matters: the brief should fit the phone version with lower limits, not a different design.

**Acceptance:** rerun `tools/canon_delivery_probe.py` adapted to the new assembler. Every class A section is in 100% of scenes; a Hearth inn scene always carries the Hearth culture brief; Parts 24 and 25 take 0 slots except present people's own fact cards.

## 6. This is one instance of a general rule

The owner's question was whether the whole effort amounts to a framework so the narrator does not forget. Close: the narrator needs three things, and each has its own failure mode.

| Job | Owner in Caerness | Failure seen in the old games | Failure still present in Caerness |
|---|---|---|---|
| **Remember** what is true | SQLite state | Lost from the chat window | Small: the database keeps it |
| **Move** the world without the player | Simulation | Nothing happened between turns | Partly: no delegation or reports (story-layer spec) |
| **Bring** the right things to the narrator each scene | Scene packet | Had to be reminded | **Large: this report.** Present people are name-only; culture and lenses never arrive; registry noise fills the slots |

The third job is where most remaining "the narrator forgot" problems will come from. Etiquette is one instance. The general fix is the same each time: decide what a scene of this kind must always carry, and assemble it deliberately rather than hoping a search finds it.

## 7. Next

1. Owner review of SCENE-01 (above) alongside the story-layer spec.
2. Write the class A lenses brief and the first culture brief (Hearth) as data, and measure with the probe.
3. Tag class C situations for Parts 3, 10, 21 and 22 first; they cover the play styles the owner named (cultivator, underworld boss, soldier, merchant, noble).

## 8. Step 1 implemented (2026-10-09)

- `canon/scene_briefs.json`: the reading-lenses brief (Part 0 two lenses; Part 3 recognition, formality, the same bow, the axes of standing, culture is not alignment; Part 2 Presence), a full Hearth culture brief (Part 3 culture sections; Part 12 Hearth Rites and the Vigil), and minimal briefs for Underheaven beyond the Hearth and the six kingdoms (their rows of Part 21 "Regional social expressions", plus each society's formality key from the Part 0 lens). Each brief records the digest of its sources.
- `engine/scene_brief.py`: place culture (the existing Hearth membership rule, else the nearest political owner), visitors' cultures from their home place, brief assembly, and `brief_staleness()` / `stamp_digests()`.
- `engine/player.py`: every scene packet carries `scene_brief`; narrator canon search excludes Part Zero, Part 24, Part 25 and the title chunk. Narrator rules in the scene packet and the narration envelope tell the narrator to apply it.
- `tests/scene01_scene_brief_test.py`: culture mapping, visitors, exclusion (proved non-vacuous), staleness, and the full packet.

Measured with `tools/canon_delivery_probe.py` (same 400 scenes, seed 7):

| | Before | After |
|---|---|---|
| Scenes with the reading lenses | 0 | **400** |
| Scenes with a culture brief for the place | 0 | **400** (Hearth 243, Underheaven 57, Windmere 31, Dunmoor 25, Stormhollow 20, Sunreach 11, Thornward 8, Greywood 5) |
| Search slots on Part 24 registry / Part 25 open questions / Part Zero | 866 / 75 / 0 | **0 / 0 / 0** |

Size: lenses 458 words, Hearth brief 630 words, kingdom briefs about 30–40 words each; a Hearth scene gains about 1,450 tokens, comparable to the six search passages. Fine on the laptop; the phone will want a compact variant.

Still open, in the order of section 5: full-depth briefs for Underheaven and each kingdom (Parts 13–19, 21–23); situation rules (class C); entity cards by link (class D); the protagonist's visible standing; and the World Bible state the engine lacks (section 4). Note also that the docx misfiles the text of "Power, authority, and etiquette" under the next heading, "The Churn and ordinary authority"; the lenses brief cites it there.
