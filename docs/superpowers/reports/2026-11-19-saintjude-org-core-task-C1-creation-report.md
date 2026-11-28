# Task C1 (character creation) report: what the player states is canon

(Named `task-C1-creation-report.md` because `task-C1-report.md` already holds the earlier org-core C1.)

## What changed
- `engine/stated_family.py` (new, pure): reads `family.parents` (alive/dead/age/name, from text or a list), `family.siblings` (each with sex, age, alive, name, half; or counted), and the family business (`family_business`, or an `affiliation` with an `owner`). It checks plausibility and raises a `Contradiction` that names the clash and its reason: a father under 15 years older than a child, a mother outside 14 to 52 at a birth, a living parent over 105, full siblings spanning more than a mother can bear, a dead father who owns the garage, a child under 12 employed.
- `engine/new_character.py`:
  - `_origin` takes each stated parent (alive or dead as said) and each stated sibling (exact sex and age) as a real person tied by kinship. The old `draw_origin_family` roll is used only for what was left unsaid. The drawn sibling set is no longer applied when the player gave siblings.
  - Age is exact: the pool is searched at his exact age first (the community he named, then anyone of that age renamed from that community, widening 1 then 3 years only if nobody is there); a person found off by a year or two has his birth date set to the stated age and the response says so. No more ±1 per submission.
  - `family_business` creates the garage as a business owned by the father (`civilian_enterprises` + `place_details` kind `garage` on the BZ1 place layer, held by the father), with the father as owner staff and the sons as employees (`enterprise_staff`, role `mechanic`, authority 25). He owns and leads nothing; the old "founder" path cannot fire, and the district-population scaling of followers no longer applies to what the player did not ask to lead. A stated business is not scaled to the town; only its money (unsaid) is filled.
  - The response now has `as_stated`, `filled` and `scaled`, each entry `{field, status, value, reason}`; `scaled_down` is kept for the old holdings scaling.
  - Caerness logic is off the path: hearth, veinborn, `open_core`, `calibrate_revealed_profile`, the Caerness surname list and `_STAGE_CLASS` are gone or gated behind `system_enabled(conn, "cultivation")`. A stated Stage is ignored and tested.
- `engine/authoring.py` (NPC equivalent): an `author` person with a stated age now has exactly that age (birth date set), and returns `as_stated`.
- `worlds/saintjude/archetypes.json`: new `auto_repair` archetype (assumption, marked) so a garage is not priced as a wholesaler. Needs the opening rebuild at deploy (`tools/build_opening.py --package saintjude`) because archetypes are seeded into the packaged DB; I did not touch `data/*.db`.
- Entry date: `engine/entry.py` and `author(kind="entry")` in `connector/authoring.py`. Default = the opening day (1 January 1975). A later date is described first (`accept=false`: "simulates the years in between", years, note on time), then run one year per call (`accept=true`) until `reached`, with the measured seconds of each chunk and an estimate of what is left; refused once a protagonist exists.
- Text: `connector/creation_core.md` and `worlds/saintjude/creation_section.md` rewritten (stated is canon, the three lists, report only the response's reasons, default entry 1975 and the later-entry option). **Not edited:** `connector/rulebook_core.md` and `worlds/saintjude/rulebook_section.md` (other sessions have uncommitted edits in them). Line 50 of `rulebook_core.md` still says "scales down what the place cannot supply", which stays true for NPCs; add one sentence there pointing at the creation text when that file is free.

## Tests (`tests/c1_stated_family_test.py`, 8 tests, all green)
Transcript case (23-year-old, both parents alive, brothers 21 and 18 with the stated sex and kin ties, father owns the garage as `place_kind=garage`, three sons staff, protagonist owns and leads nothing, every field has a reason); resubmission and a redraw give the same stated facts, and the identical proposal twice the identical people; implausible claims refused with reasons (father of 31, dead father owning the garage, siblings 62 apart) and nothing left behind; unsaid fields filled and said so; NPC age exact; no cultivation rows or Stage words; entry described not run, then a 20-day entry in chunks, and refused after the story began. No run longer than 20 days.

## Opening richness audit (fresh Saint Jude opening, same as `data/saintjude.db`: 2223 characters, 107 institutions)
Rich: org seats 1811, org lines 717, arrangements 300, holdings 72, relationships 2338 (about one per person), offices 43 and terms 47, institution memberships 2225, tensions between organisations 8, law offices 21, rules 30.
**Blank at the opening (nothing lived behind them):**
- Families and households: 1 household, 8 kin links for 2223 people; 407 characters have no relationship at all.
- Businesses: `civilian_enterprises` 0, `enterprise_staff` 0, `place_details` 0, `buildings` 0, `venture_details` 0, `agreement_terms` 0, `org_money` 0. There are no shops, garages, bars or firms as businesses before play; only org holdings.
- Debts, grudges, obligations: `org_debts` 0, `underworld_grudges` 0, `obligations` 0, `org_heat` 0, `org_incidents` 0.
- Personal history: `actor_memories` 0, `knowledge` 0, `actor_careers` 0, `life_events` 1, `history_entries`/`political_history` 0.
- Politics: `races` 0, `race_candidates` 0 (offices and terms exist), no `org_councils`.
- Neighbourhoods: districts exist as locations and the 26,947-person background pool is generated lazily; no household, shop or parish content ties anyone to a street.
This does not match "the opening already carries lived history" for Saint Jude (that is true of the Caerness opening, schema 108). Filling it is a separate round. A protagonist created now gets his own lived past (kin, neighbours, knowledge, memories) from `fill_lived_past`, but the city around him starts bare. In the transcript case the Hill has no other garage or household for the family business to sit among.

## Not done / caveats
- The owner said "place, venture, holdings": the garage is a place plus a business; no venture is made because nothing is being built.
- A stated community whose adult men are all already revealed in the opening (the Italian group on the Hill) takes its name from the community (a drawn identity renamed), since no unlinked Italian man of 23 remains; said in the `background` reason of the response.
- The protagonist still gets his own household at 16+ (not moved into his father's house): not stated, filled as before.
- The `entry` tool is described in `creation_section.md` only; the `author` docstring in `connector/server.py` (another session's file) does not list it yet.
