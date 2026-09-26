# WORLDHIST-01A — Schema 108: opening history, mortality and cultivation realism

**Date:** 23 September 2026  
**Engine:** v0.60.0  
**Schema:** 108  
**Parent checkpoint:** `ed5eeef` (schema 107)

Every change here answers the same question: *would the World Bible's world plausibly look like this?* Canon outranks inherited constants. Where canon gives a number (the Sixth census, the Veinborn and staged populations, the martial sex ratio), the model is fitted to it.

## 1. Opening resolution is not run-time invention (DESIGN §15.1)

The seed leaves "household membership, marriages, children … and full social networks" null where canon does not establish them. The engine had read that null as *none*, producing a world of lifelong-single adults who knew nobody. The run-time no-invention rules ("never invents a replacement person", "roster shortage never causes a match") were being applied to the opening.

The distinction is now written down:
- **Opening resolution** fills canon's unknowns once, at the start of a run. It is deterministic from the world seed and each person's seed identity, never overrides canon, and records a basis for every fact.
- **Run-time change** comes only from simulated processes at world rates. Revealing someone who already existed ("latent does not mean newly created, it means previously undescribed") is not invention.

## 2. Opening family life and relationships (`engine/opening_family.py`)

- **Life-course draw.** Each named adult canon is silent about gets a reproducible life history: first marriage at canon-cultural rates, spouse survival on the engine's own mortality curve, widowhood, remarriage, and children. Families aim for the number of *living* children they want (the Rites' stake in continuing the line).
- **Canon kept.** The three royal couples keep their canon marriages. Niall Redcairn and Lewis Grant have canon descendants but no named spouse, so they are left to canon (`canon_partial`).
- **Group rates, each grounded in canon.**
  - Lineage houses marry more ("reproduced through kinship, inheritance, marriage").
  - Serious martial careers (Third and above) marry later and less often.
  - The Long Road, and canon "recluse"/"wanderer" text, lower marriage.
  - Greywood's Witness adds marriage pressure.
  - Same-sex relationships and long-term lovers exist in canon but are not broadly recognized households, so they are not modelled as unions.
- **Living spouses** are revealed as low-attention persistent people. **Children** born before the opening stay latent; they age, and may die, from the opening on.
- **Opening relationships** come from canon kin, teaching lines and shared institutions, backdated by the length of the tie. Relationships now have a `started_day`, which fixes a bug where every change reset the acquaintance clock.
- **Opening result:**
  - 3,288 relationships;
  - 267 active unions, with 264 spouses revealed;
  - 585 living latent children;
  - of the canon persons: 223 married, 44 widowed, 178 never married, 2 left to canon.

## 3. During a run

- **Marriage.** Single named adults marry into the unnamed population at the same rates the opening uses, on a fixed 30-day grid so results do not depend on how a run is stepped. Named-to-named courtship is unchanged.
- **Births.** Birth spacing follows each couple's own history, averaging about 3.3 years.
- **Heirs.**
  - When a household head dies without a designated heir, the surviving spouse and living adult children hold inheritance claims. Previously the household went headless.
  - Lineage-house succession weighs kinship (child +20, sibling +12, spouse +6, against 12 per Stage rank). Ability still decides: "no simple eldest-child succession".
  - An eldest latent adult child is revealed only when an inheritance or a lineage succession needs them.

## 4. Mortality

- **Named adults.** Named natural mortality is a Gompertz-Makeham curve. Cultivators' prime and old age are stretched separately ("cultivation extends the prime before it extends old age"). Stage anchors are fitted to canon: the Sixth census (median 88, oldest 118) gives a Sixth decline at 87 and a median death age of 111. Median death ages, ordinary through Sixth, are 77, 80, 83, 86, 91, 99 and 111. Named deaths had been effectively switched off: zero in the accepted schema-104 decade.
- **Childhood.** Childhood mortality is premodern (DEMO-04: 10% in the first year, then 4.5%/0.8%/0.5% a year) and shared by the named, sampled-background and aggregate models. It is scaled by a family's actual means (standing within a house, underworld earnings and lifestyle, enterprise, household wealth) and access to care (a care network, an institutional infirmary; remoteness costs in proportion to poverty). It is never scaled by a group label alone.
- **Bug fixed.** A late breakthrough could reverse an elder's accrued decline.

## 5. Veinborn, staging and training

Canon anchors: 4.79M Open-Core ("Veinborn": 35% of the Hearth, about 8% elsewhere) and 2.05M staged cultivators. Serious martial society is "roughly 70–75% male" from unequal training investment, "not a hard female Stage ceiling".

- **Staging.** About 60% of Hearth Veinborn and 37% elsewhere became staged, weighted about two-thirds male. Revealed spouses and children and sampled background people follow this. Most Veinborn wives of cultivators are not practising martial artists. Background Veinborn were previously all staged, two to three times canon's share.
- **Newborns** inherit a Core ("primarily hereditary"). Veinborn babies are unstaged.
- **Training uptake.** Any Veinborn person not training may take it up. The chance depends on age, sex, a martial connection, family means, the Hearth and visible early talent. This applies equally to canon, revealed, background and underworld people and to children born in the run.
- **Aptitude.** Realization aptitude is bell-shaped (median 1.0, spread about 0.2); it was uniform. Every revealed person, whether latent, background, underworld, spouse or child, gets the same within-Stage calibration and aptitude as canon people, instead of a generic entry-level profile. That profile had let 126 revealed spouses produce 235 of a decade's 381 breakthroughs.

## 6. Other corrections

- **World Bible pronouns** now count as canon text for sex: Voss Rannick and Nall Reed are male ("… is **his** principal active family recipient"; "the huge order produces **him**"). Both had been rolled female.
- **Newborn placeholder names** include the union, because several couples can share a royal household.

## 6a. Routes and frontiers (ROUTES-01, `engine/route_network.py`)

Canon calls the geography "intentionally connective rather than zoned", but the travel graph held only the seed's 11 timed routes. 121 of 133 places were unreachable, including Crownhold and every outer kingdom. That silently blocked trade, travel, news, tournaments, smuggling and war. A schema-107 decade produced no war, no change to political, religious or settlement history, and 86 merchant firms stuck in "forming".

- **Network.** There are now 132 routes, and every place is reachable. Each route records its basis and a certainty: `canon_route`, `canon_corridor` or `working_placement`. Shortest paths honour the Part 20 caravan-day table: Aldergate–Cairnholt 4–6, Cairnholt–Lysmere 5–7, Cairnholt–Toll's Reach 12–16, the Grand Coven 10–14. Crownhold–Cairnholt runs through the Aldergate corridor (7–9 days), not a Highford shortcut.
- **Map.** Where the text is silent, the very old provisional continental map places things: Stonegate Pass crosses to Oakspire in Greywood; Kingsway Pass sits beside Toll's Reach; Talonkeep, Oakridge and Verenwood lie east, Britterwatch north. These are all `working_placement`. Text wins in every conflict.
- **Armed corridors are not roads.** The Underheaven–Thornward corridor (Eastwatch–Westgate) is military frontier geometry, not a civilian road; campaigns use the geometry.
- **Issue pressure was always 0.** Conflict channels named issue kinds such as `territorial_frontier` and `armed_corridor`, which never matched the polity issue kinds `territorial` and `frontier`. Incidents were therefore scored without grievance and could not reach campaign severity. `conflict._CHANNEL_ISSUE_KIND` maps them.
- **Missing frontier.** The Empire–Thornward channel had no Thornward endpoint; it is now Eastwatch–Westgate. Canon's "Thornward–Stormhollow: broken southern ridges … raids, forts, cattle, disputed valleys" had no channel and no opening issue; it now has both, Dunbriar–Highcairn. The migration adds only missing opening geometry and never resets relations a run has moved.

## 7. Evidence

- **Regression.** Isolated full regression on Windows with scratch databases: **115/115 PASS** (`tenyear02_opening_activation_gate_test` is run against the packaged opening). New tests: `named_mortality_calibration_test`, `opening_family_test`, `veinborn_training_test`, `routes01_canon_network_test`. Updated for the connected world: `orgagency_conflict01` (six channels; campaign feasibility tested by closing the frontier roads), `trade01` (a blocked corridor is tested by cutting Saltmere off, since one closed leg now reroutes). Updated: `v20` (a 70-year-old Fifth, not 90), `v27`/`v43` (opening families exist; no union forms from contact links), `v56` (practitioners only), `family02` (World Bible pronouns).
- **Packaged opening.** `data/caerness.db` is migrated to schema 108 at day 0: integrity `ok`, zero foreign-key violations, zero unresolved sex.

## 8. Not claimed

- **Decades.** A ten-year run on the pre-routes opening completed (integrity `ok`): 363 births, 107 named deaths, 125 unions, 390 breakthroughs, no war (maximum incident severity 65.3). It exposed the stalled summit (Thirds 116 to 314, Sixths 40 to 31), which is addressed by the POP-01 design (`docs/superpowers/specs/2026-09-26-population-tiers-design.md`). The routed ten-year run was interrupted at day 2,790 when the session ended. By day 1,050 it had already shown incident severity 68.9 (a campaign needs 70) and 32 trade flows over tracked routes. It must be rerun.

This is not a fresh integrated ONEYEAR/TENYEAR acceptance. `ONEYEAR_WORLDHIST01A_SCHEMA108` is pending.

Still open:
- Adult mortality differs between the aggregate cohort model and the per-person/named models.
- Nobody quits training yet.
- The canon/background adult means signal is coarse: household wealth is unquantified at the opening.
