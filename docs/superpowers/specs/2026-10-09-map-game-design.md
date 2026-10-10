# The map game: one map, many scales, your knowledge

**Status:** proposed on 2026-10-09 from the owner's direction in conversation; widened on 2026-10-10 by the owner's CK3 / Suzerain / manhwa direction (§8 to §11). Awaiting the owner's review. Nothing here is implemented.
**Related:** story-layer spec (`2026-10-09-story-layer-design.md`: speaker cards, sifting), World Bible coverage (`docs/research/2026-10-09-world-bible-narrator-coverage.md`), the delegation and correspondence system (to be specified; this spec gives it its panels).

## 1. What the owner asked for

- A CK3-style game on the laptop: a map, panels, time controls, rather than a text window alone.
- Playing as an individual, like CK3's landless adventurers and travel: a person and their companions moving across the map, taking work, perhaps winning land.
- The map seen at different levels: a city at ward scale for underworld bosses and business owners; a clan's lands at estate scale; kingdoms and the empire at realm scale.
- Laptop first (Dell G5 15, GTX 1050 Ti, 16 GB), phone later by turning dials, not by separate code.

## 2. Principles

1. **Your character's map, not God's map.** Every level shows what the followed character knows: places they have been or heard of, roads they know, who controls what as far as they have learned, and moving things (armies, caravans, rivals) where they were last *reported*, with the date. Detail is knowledge, not role: an underworld boss knows his city ward by ward because he works it; a wanderer can open the same city and see only the wards they have walked. (DESIGN §27.4; owner rule: plausibility over settings.)
2. **One map, zooming down the place hierarchy.** `locations.parent_location_id` already nests places (realm, region, city, district). Each level is the graph of the children of the place being viewed, so there is one map engine and one data model at every scale.
3. **Management through people and reports.** A king does not watch grain stocks move live; a steward reports, late and sometimes wrong. Levels show the last reports received, and actions at a level are orders to people, delivered by the correspondence system. (Owner direction on agents and letters.)
4. **Narration stays the heart.** The map is the board between scenes. Scenes, conversations and the fire with a captured enemy happen in narration.
5. **No geography invented by the map.** The World Bible deliberately leaves much geography open and text wins over the old continental map. Stages 1–3 below need no coordinates; a painted map waits for the owner to settle geography in the World Bible.
6. **Same code on laptop and phone.** Built into the existing web app the Python engine already serves (`engine/mobile_server.py`, `mobile/`), rendered with SVG or canvas in the browser. The phone gets the same screens with smaller limits.

## 3. What exists (checked 2026-10-09 against the schema-109 packaged world)

| Level | Data that exists | Gaps |
|---|---|---|
| **Realm** | 133 places, 132 routes with canon travel times (`travel_routes`); 122 places with a controlling polity (`territorial_control`); conflict channels and frontier geometry; war system | No coordinates (all 133 places are `OPEN_NOT_REQUIRED`, placed only relative to each other); no recorded claims yet (`territorial_claims` empty) |
| **City** | Aldergate: 12 underworld wards with kind, population scale, commercial intensity, street visibility and policing pressure (`underworld_zones`); rackets, protected businesses and economic interests by ward; a few city districts as places in Cairnholt (4) and Crownhold (4) | No wards for any other city; districts are not linked to underworld zones |
| **Estate / clan lands** | Clan seat districts and cultivation sites as places; agriculture fields; production sites; 5 buildings | No record of who holds which villages, fields or estates. The World Bible asks for land, property and site access as persistent state (Part 24 character record; Part 2 cultivation-site ownership) |
| **The individual** | `travel_plans` moving a person or household route by route, with `exposure_pressure`; presence on the road; seasons and route conditions; rumours at stops | No travelling party (you plus companions as one group); no provisions or upkeep; escort contracting "remains a later extension" (COVERAGE-01 row 31) |
| **Interface** | A small text web app (about 180 lines of JavaScript): narration, Ledger and Matters panels | No map, no people or letters panel, no time controls |

## 4. The screens

**Centre:** narration when in a scene; otherwise the map at the current level.

**Map levels**, each the children of the place being viewed:
- **Realm:** regions, cities and roads; who controls each place as far as you know; reported armies, caravans and notable travellers with dates; your position and journey.
- **Region / estate:** villages, sites, fields, holdings; whose they are; what your steward last reported.
- **City:** wards and districts; whose turf, which rackets and businesses, where the watch is heavy, as far as you know.

**Side panels:** people you know (with the reasons they feel as they do, from shared history, not opinion numbers); letters (arriving with travel time); agents and followers and what they were last doing; matters (obligations, intentions); holdings.

**Time controls:** pause, play, faster. Time runs until the followed character would plausibly stop: a letter that needs a decision, someone at the door, a scene, a choice only the player can make. This replaces the current `interruption_policy` setting (owner rule, 2026-10-09).

**Actions:** common actions are buttons on the map and panels (travel here, send a letter, assign an agent, take this work, muster, pay). They are cheaper and more reliable than asking a 3–4B model to interpret free text. The text box stays for everything else.

## 5. Road life: playing as an individual

- **Travelling party.** You and your companions move as one group on one journey. The party is a camp: people you know, with speaker cards, personalities and mannerisms.
- **Provisions and upkeep.** Food, pay and mounts by the day, so a band of thirty costs something.
- **Work from real needs, never templates.** A job exists only because someone in the world needs it: a merchant house's real shipment needs an escort (MERCHANT-01 shipments); a magistrate's real open case posts a bounty (law cases); a lender's real unpaid debt wants collecting (agreements); a sect's real need wants guards (ORGNEED-01). Work is heard of locally, at inns and waystones, through the rumour system.
- **Dangers from causes.** Whose territory you cross, the season, who else is on the road, who is hunting you; never a random hazard pool.
- **Long Road canon.** Waystones and their local peace, Waymeets, companies, Oath-Kin and circuits (World Bible Part 9) shape what road life looks like.
- **Paths to land.** Granted for service, married into, bought, or taken, each through the systems that already decide who holds what.

## 6. Stages

1. **Realm travel map and panels.** A schematic map from the travel graph laid out by region, travel times on hover, your position and journey, known versus heard-of places; people, letters, matters panels; time controls with plausible stopping. Needs no geography decisions.
2. **Road life.** Travelling party, provisions, work from real needs, dangers from causes.
3. **City level for Aldergate** (the one city with wards): turf, rackets, businesses, watch, as far as you know. Then wards for other cities, from World Bible Parts 20 and 22.
4. **Estate level.** Needs new state: who holds which villages, fields, sites and estates. Settle it with the owner from World Bible Part 24 and Part 2 first.
5. **Painted map with borders,** once the owner settles geography in the World Bible.

Each stage is measured the way the scene brief was: what the map shows must be exactly what the followed character knows (a probe compares the drawn map to the knowledge tables).

## 7. Open questions for the owner (2026-10-09)

1. For stage 1, is a schematic map (places and roads, laid out roughly by region) acceptable until geography is settled, or would you rather settle rough geography first?
2. Should playing at the realm level (a king or emperor) be available from the start, or only once the individual and city levels work?
3. Which city after Aldergate should get wards first?

## 8. Owner direction, 2026-10-10: CK3 to look at, Suzerain to read, manhwa to see

The owner, partly through a discussion with another assistant (summarised as a "design vision" note), widened the request:

- The game should look and feel like CK3, not like a chat window: a map, a court or location view with people in it, outfits and emblems, and event pop-ups in the corner.
- **Event pop-ups carry the narrator's prose** (Suzerain-style), and the player answers by typing, not by picking from four options. Moving on the map, travelling and opening panels are done with the mouse.
- **Narrative first.** Most time is spent in scenes; the map is how you get between them and see where things stand.
- **The wanderer is the default.** Everyone is an individual. A clan martial artist is a wanderer tied to a place; only someone at the top lives in an institutional view, and even a king can walk into a tavern.
- **Scale follows involvement:** ward-level cities for underworld and merchant play, a clan's compound and nearby town, kingdom view for rulers.
- **A base you build** (CK3's domicile): a merchant's house, a gang's headquarters, a clan compound.
- **Visual style:** 2D, manhwa-inspired (the owner names *Absolute Sword Sense*), not 3D. Social staging is a core reason for visuals: bows, guards outside, who stands closest to the boss, colours and emblems, "power should be visible".

## 9. Evaluation against the code (verified on schema 109, 2026-10-10)

Verified facts are marked **[code]**; everything else is recommendation.

| Vision item | What exists | What is missing |
|---|---|---|
| Player attempts, engine decides ("I cut off his arm") | **[code]** A duel engine with intents and exchanges (`combat.py`: `create_duel`, `submit_duel_intent`, `duel_exchanges`); harm with persistent outcomes and lasting impairment (`harm_incidents` to `health_conditions`, `health.py`); player actions as proposals that are begun and finalised with causal links (`actions.py`) | **[code]** Free text never reaches the duel engine. The player-action parser recognises only travel, wait, investigate, talk and observe by keyword; anything else is recorded as "freeform intent requires a richer action interpreter; no permanent state is guessed", so the narrator improvises the outcome. This is the exact failure in the Master Han encounter, and it is the largest gap in the whole vision. |
| Bounded AI co-referee | Model gateway: model proposes, engine validates, SQLite records; resolution on first look (DESIGN §15.1) | An **intent interpreter**: free text to one or more engine actions (attack, threaten, bribe, give an order, promise, buy, train), each validated and resolved by the system that owns it. Genuinely novel undertakings are composed from existing parts (organisation, employees, routes, agreements). A 3–4B local model can classify intent into a closed list reliably; it should not judge outcomes. |
| NPC portraits with persistent identity, injuries and age | **[code]** Age, health conditions, rank (`institution_memberships`), mannerisms and speech (`character_embodiment`) | Appearance: build, face, hair, scars, clothing. Listed already as "visual identity" in the World Bible coverage report (§ missing simulation state). |
| Social staging | World Bible Part 0 (Presence; formality as the response to power) and Part 3 (etiquette, "Same bows. Different room."); culture briefs reach the narrator (SCENE-01) | Data the UI can draw: who escorts whom, guards posted, seating and placement by rank, deference owed between two people, organisation colours and emblems (already on the SPEECH-01 list). |
| Wanderer default, institution views only at the top | Every actor is a character with memberships; presence; travel plans | Travelling party; the base (domicile) as held property, which is the same gap as "who holds what" in §3. |
| Ward-level cities | **[code]** Aldergate's 12 underworld wards with turf, rackets and policing | Wards for other cities; districts linked to wards. |
| Long time advances and interruptions | **[code]** `timeskip.py` with `interruption_policy` (all / meaningful / critical_only) and delegation | Replace the setting with plausibility (owner rule, 2026-10-09). The vision's "wake me if…" conditions fit as orders given to people ("tell me at once if the Ma clan moves"), which is plausible and works the same for NPC bosses. |
| Information shown matches what the character knows | **[code]** Knowledge and belief tables; `player_information_hub` | The map and panels must read only from those (§2 principle 1). |

## 10. Where I disagree or would narrow

1. **CK3's own models and outfits cannot be used.** They are Paradox's proprietary assets, in a proprietary engine format. A CK3 mod is no route either: CK3 scripting cannot host free-text input, a language model or the Python simulation, so the mod would lose what makes Caerness different. CK3 is the design reference; the art must be Caerness's own.
2. **Layered 2D portraits, not generated images per scene.** CK3 itself builds portraits from layers (body, face, hair, clothing, headgear). The same approach in 2D, manhwa style: a modest set of drawn layers (faces, hair, robes and coats by culture and rank, emblems tinted with organisation colours, scars and a missing arm as overlays), assembled from state. The result is consistent forever and costs nothing at run time. Generating new images per scene on a GTX 1050 Ti would be slow and would drift between scenes, which is the inconsistency problem again.
3. **Dynamic scenes (the vision's level B) start as staging, not animation.** Portraits placed on a location background by rank and role (the master seated, elders beside, disciples in lines, guards at the door), with a few pose variants (standing, bowing, kneeling, seated, wounded). That gives most of "power should be visible" without animation work.
4. **Watabou.** Its generated maps may be used freely, but its generator code is GPL-3.0. Run it as a separate tool and import its exported JSON/SVG as data; do not copy the code into the engine. The cities must be generated to fit the simulation's facts (Aldergate's 12 wards), not the other way round.
5. **"The AI may introduce new persistent details"** only in the existing form: the engine resolves a detail on first look, records it, and it never changes. The narrator never decides outcomes or adds commitments the player did not make (SPEAKER_RULE; the commitment check still to be built).

## 11. The play screen (laptop)

- **Centre:** the current location as a scene: background, people present as layered portraits staged by rank and relationship. Click a person for their card (what *you* know of them). In travel or when zoomed out, the map takes the centre.
- **Event pop-up:** the narrator's prose in a framed window over the scene, with a text box to answer. Under it, two or three engine-suggested actions as shortcuts (never the only options). Important scenes can expand to full screen.
- **Bottom right:** letters, reports, rumours and summons waiting, with the date each was sent and arrived. Opening one either informs (a line) or opens a pop-up if a decision is needed.
- **Top bar:** date, time controls (time runs until your character would plausibly stop), your standing.
- **Map button and zoom:** realm, region, city wards, your base; detail is what you know.
- **Side panels on demand:** people, matters, holdings and base, party or crew; institutional panels appear only for someone who actually runs something.

## 11a. Art scope (owner decision, 2026-10-10)

Art is for **people and places**, as in CK3, plus a few **key moments**. Everything dynamic stays in text.

- **People:** a portrait for every character the followed character meets, built from layers. The portrait reflects state: age, rank and dress, organisation colours and emblems, and visible marks. If a text fight leaves a scar or costs an arm, the engine records it, and the portrait shows it from then on.
- **Places:** a background per location kind (clan hall, courtyard, inn, road, market, throne room, field), with known places able to get their own.
- **Key moments:** a staged picture, not a bespoke illustration. People are placed on a background by rank and role: an audience before the emperor, two armies facing each other under their banners and colours, a formal challenge at a gate, a gang boss arriving with his men.
- **Not drawn:** fights, movement and action. These stay in prose, and their results are drawn afterwards through the state they change.

## 12. Revised order

1. **Intent interpreter (new, first).** Free text to engine actions with validation, starting with the murim set: attack or duel, spar, threaten, give an order, ask for or offer a deal, train. Without it, any interface sits on top of improvised outcomes.
2. **Play screen stage 1:** location view with placeholder portraits staged by rank, event pop-up with free text and suggested actions, notifications corner, schematic map (stage 1 of §6), time controls.
3. **Appearance and colours as state:** visual identity per character, visible marks from lasting injuries (from `harm_incidents` and `health_conditions`), organisation colours and emblems, deference rules feeding the staging.
4. **Art pipeline:** a small layered portrait set in a manhwa style for the Hearth and murim cast first, then backgrounds for a handful of location kinds (clan hall, courtyard, inn, road, market), then the key-moment stagings (§11a).
5. Agents, letters and reports (the delegation spec) slot in alongside 2, because the notifications corner needs them.
