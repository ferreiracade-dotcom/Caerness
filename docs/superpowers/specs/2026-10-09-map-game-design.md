# The map game: one map, many scales, your knowledge

**Status:** proposed on 2026-10-09 from the owner's direction in conversation; awaiting the owner's review. Nothing here is implemented.
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

## 7. Open questions for the owner

1. For stage 1, is a schematic map (places and roads, laid out roughly by region) acceptable until geography is settled, or would you rather settle rough geography first?
2. Should playing at the realm level (a king or emperor) be available from the start, or only once the individual and city levels work?
3. Which city after Aldergate should get wards first?
