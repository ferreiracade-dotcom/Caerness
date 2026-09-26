# POP-01: Population tiers — a simulated world beneath the named layer

**Status:** design, agreed in conversation on 2026-09-26; awaiting the user's review of this written spec.
**Scope of this spec:** the tier framework plus domain step 1 (life and cultivation). Domains 2–6 each get their own spec on this framework.

## 1. Problem

The engine simulates a closed opening cohort of about 780 named people in detail. Everyone else is either an aggregate count (births and deaths only) or one of 2,272 frozen "background person profiles", whose stage, wealth and standing never change and which are only drawn on when something asks for a person.

Consequences seen in a schema-108 decade:
- The named upper stages drain and are never replenished from the wider world. Canon has about 300 Hearth Fifths, but only the 70 named ones can ever become Sixths. The Sixth census went from 40 to 31.
- Named Hearth Thirds pile up (116 → 314). Canon's named cross-section is shaped partly by eminence: people are named because they reached Breach. The engine has no way for newly eminent people to enter the named layer.
- Nobody rises from the wider world by achievement in any domain: cultivation, commerce, the military, the underworld or the arts.

The player may play as a noble reviving a county, a soldier rising to general, a merchant building a fortune and a collection, an underworld boss, or a cultivator. The world has to be a proper simulation for all of them, without the protagonist.

## 2. Principles

1. **One trajectory for everyone.** Every person, in every tier, lives by the same rules. Tier decides only how much is stored and how often it is computed.
2. **Nobody is frozen.** The background is simulated continuously, in bulk.
3. **Tier never changes outcomes.** The same person with the same circumstances and the same random draws gets the same result in any tier.
4. **Conservation.** Splitting, merging and promotion never create or delete people. Population totals always equal the opening population plus births, minus deaths, plus net migration.
5. **Rising is not invention** (DESIGN §15.1). A person split out of the background had a real past, which is their simulant's recorded path. Only personal details are drawn, from their own fixed random stream.
6. **Canon anchors are the current truth, not immutable.** Calibrate to them first. Change a canon figure only when it is clearly the cause of an implausibility, and record the change.

## 3. Tiers

| Tier | Holds | Storage | Simulated |
|---|---|---|---|
| **Background** | Everyone not singled out | Weighted simulants in numpy arrays per regional partition | Every 30-day step, in bulk |
| **Known** (a background state, not a separate tier) | Background people the player has asked about or met in passing | A weight-1 simulant plus a pinned identity (name, brief history, place) | In bulk, like any simulant |
| **Notable** | People who stand out locally, or whom the player deals with repeatedly | A light individual record: identity, history, relationships, standing | Individually, cheaply, on the 30-day grid |
| **Named** | People significant at kingdom or continent scale, locally top-ranked, or central to the player's life | A full engine actor | The full engine, at the existing camera cadence |

The camera cadence (`ACTIVE`/`STRATEGIC`/`DORMANT`, `SCENE`) is unchanged and orthogonal: it decides how often a named person is computed, never who exists or who advances. During long skips, distant, quiet named people drop to coarser cadence (DESIGN §3: dormant never means frozen).

## 4. Simulants

A simulant carries a whole person across every domain, so overlaps (a general who is a Third, a rich underworld boss, a Veinborn merchant) are natural.

| Domain | Attributes |
|---|---|
| Life | Age, sex, place, household state (married, children), social estate (commoner, gentry, noble line, clergy) |
| Means | Wealth, income, property |
| Work and career | Occupation (farming, craft, trade, soldiering, service, clergy, office, underworld), career rank, skill |
| Cultivation | Core, stage, Vessel adaptation, realization integration, training state, teacher and institution access |
| Military | Serving or not, rank, experience, force (crown army, house retinue, mercenary company) |
| Underworld | Involvement, rank, affiliation, notoriety |
| Standing | Reputation per domain; memberships (sect, house, guild, company, gang) |
| Aptitudes | Vessel, realization, command, commerce, medicine, teaching, craft/art, criminal familiarity |

Step 1 fills in life, means and cultivation. The other columns exist from the start but are populated by their domain steps.

### 4.1 Weight is resolution, not importance

- A **niche** is people in the same place and domain at a similar rank. Examples: underworld captains in Cairnholt; Hearth Thirds in the Churn; militia sergeants in rural Dunmoor.
- Every niche keeps at least `k` distinct simulants (starting value 10–20, set from phone benchmarks).
- A simulant's weight is the niche size divided by `k`. A niche smaller than `k` is simulated one to one.
- Rarity is therefore local and follows the world as it changes. Examples:
  - Cairnholt's three underworld bosses are individuals, while its roughly 60 captains are about 12 simulants of 5.
  - A small outer town's Thirds, who are local masters there, are individuals, while a big Churn city's Thirds are grouped in small numbers.
  - Breach, Fifth and Sixth are individual everywhere.

### 4.2 Splitting and merging

- Each step, the rules decide how many of the people a simulant stands for experience each event. They use binomial draws from the simulant's identity stream.
- The people affected split off into new simulants carrying the new state. Weights always sum to the original.
- Simulants in the same niche whose states have become indistinguishable merge back, within a tolerance, so storage does not creep upward.
- Individuals (weight-1 simulants with an identity, and every notable or named person) never merge.

## 5. Moving between tiers

Three scores, each recomputed on the 30-day grid:

1. **Distinction:** how far ahead of local peers someone runs. Examples: a breakthrough years younger than their niche, a business outgrowing its rivals, decoration in battle, territory seized, work that starts selling.
2. **Significance:** rank within a domain at city, kingdom or continent scale. It comes either from power (office, command, land, a large firm, gang territory) or from excellence alone (the best fighters, richest merchants, most famous performers, finest craftsmen, most notable collections).
3. **Relevance:** how often the player deals with someone and how much they matter to the player's life. It accumulates with contact and decays without it.

| Move | Trigger |
|---|---|
| Background → known | The player asks someone's name or meets them in passing. Identity is fixed on the first look and never re-drawn. |
| Background/known → notable | Distinction or significance at city scale, or relevance built up from repeated contact |
| Notable → named | Significance at kingdom or continent scale, top local rank, or strong relevance |
| Moving down | All three scores stay below threshold for about a year (hysteresis). Named drops to notable, and notable to known. Individuals are never merged back. |

- Significance is rank-based (starting values: top few dozen per domain per kingdom, top handful per city). Relevance is limited by how many people the player actually deals with. Together these bound the named layer without quotas.
- Canon-authored people start at whatever tier their opening scores give them, and being authored confers nothing afterwards.
- A known background person is caught up on demand. When the player next looks, their life since the last look is computed by the same rules from their own draws. That result is identical to having simulated them continuously as a weight-1 simulant, which is how they are stored.

## 6. Shared rules

- Each rule is one function over a batch of attribute arrays: mortality, marriage and fertility, training uptake, Vessel growth, the realization walls, career promotion, wealth change. The background calls it on thousands of simulants, and individuals call it on a batch of one.
- Randomness comes from `(world seed, identity, day, rule stream)`. For a weighted simulant, the same draws determine the binomial count affected. Looking at someone never changes their fate.
- The background and notables advance on the 30-day grid, which keeps chunk invariance.
- Rules read world state: ground quality and ecology, teacher and institution capacity, prices and wages, war levies, crime pressure, famine. Results feed back into existing systems: aggregate trade supply and demand, recruits and levies, tax base, gang manpower, disciples.
- The existing full-engine systems for firms, gangs, armies, households and polities stay. POP-01 supplies the population beneath them.

## 7. Domain step 1: life and cultivation

- **Life:** mortality (the Gompertz-Makeham model and the DEMO-04 childhood model, with socio-economic circumstance multipliers), marriage and remarriage hazards with group differences, births with Core heredity, and means drift.
- **Cultivation:**
  - Veinborn shares by sphere (35% in the Hearth, 8% outside), staging and sex-weighted uptake, and bell-shaped aptitudes.
  - Vessel growth: unchanged, since the named Hearth lower-stage pace matches canon's Hearth cross-section.
  - The realization walls (Third→Breach, Breach→Fifth, Fifth→Sixth): average rates are held to canon's steady state, but opportunity and success respond to circumstances (teacher, institution, ecology, aptitude). This makes elite-track people break through more often and poorly supported ones less, instead of using near-constant chances.
- **Opening draw.** Canon anchors (not quotas) seed the background:
  - Population: continent about 52M, with the per-polity figures in Part One.
  - Staged cultivators by stage, sphere-split as follows.

| Stage | Global | Hearth |
|---|---|---|
| First | ~1.65M | ~330k |
| Temper | ~350k | ~122.5k |
| Third | ~45k | ~24.75k |
| Breach | ~4,000 | ~2,800 |
| Fifth | ~350 | ~300 |
| Sixth | ~40 | ~38 |

- **Offset.** The canon social offset outside the Hearth (outer professional backbone First; mature backbone Temper; local master Third) is respected by the ecology and resource terms, not by caps.

### 7.1 Ageing at the summit, and where rarity lives (provisional, calibrated in step 1)

**Evidence (2026-09-26).**
- Canon's ages put typical Sixth attainment in the early-to-mid 60s: Hearth Fifth median 63; the youngest Sixths apart from Blake Merrin (34) are 69, 71 and 74.
- Murim manhwa agree on attainment ages. Summit masters are in their 60s–80s (Return of the Mount Hua Sect, Chronicles of the Demon Faction); the tier below is 40s–60s; a 30-something near the summit is a prodigy.
- The genre keeps its summit tiny through reverse ageing (반로환동): masters stay in their prime for a century. Caerness canon deliberately rejects the youthful look ("does not become thirty again").
- A joint Third-to-Sixth model fitted to canon's Hearth ratios (`scratchpad/ladder_model.py`) shows that lifespan changes barely reduce turnover. Holding about 38 Hearth Sixths needs about 7–9 new ones a decade under any plausible ladder. Longer lives mainly make Sixths older.

**Rule: looks keep calendar age; breakthroughs change the Vessel.**

| Stage | Effect of the breakthrough on ageing | Starting value |
|---|---|---|
| First–Third | Slower decline (existing longevity classes) | — |
| Breach | Stasis: the body holds where it is | about 5 years |
| Fifth | Partial renewal: accrued decline cleared back to a renewed prime | about 10 years of prime |
| Sixth | Full renewal: a second career even if reached at 70 | about 25 years of prime |

- Renewal resets the decline clock for mortality **and** capability (functional capacity, recovery, resilience, stamina, mobility). This reverses the 2026-09-23 "accrued decline floors" rule for Breach and above.
- Renewal never restores fertility; reproductive ageing continues (canon).
- The starting values are fitted in step 1's full runs, which include violent death. At about 5/10/25 the toy model gives about 7.5 new Hearth Sixths a decade, attainment around 75 and a living median around 100, with a handful over 110.

**Rarity lives in the depth of Sixth, not in entry.**
- Entering Sixth is rare but regular: about 7–8 a decade in the Hearth.
- Sixth has depth bands (Entry, Established, Peak), earned through decades at the stage, realizations, teaching and developing one's own art. The engine's post-Sixth realization and Vessel growth supplies the depth.
- **Peak Sixths** are the genre-rare summit: about 3–6 alive, with a new one about once a decade. Canon's "several in one decade would be unusual" is re-read as applying to them.
- The summit has eras: counts at each band rise and fall with generations, wars and lost inheritances, and the engine records unusual ages as history. There is no census target; calibration checks bands across decades.

**Canon changes to record:**
- Moderately re-age the Sixth census: a handful over 110 and a couple of ancient figures.
- Add the renewal ladder and Sixth depth bands to the cultivation Part.
- Re-read "several in a decade" as referring to Peak Sixths.
- Canon's named ages are a named-layer sanity check, not a population target: canon names working masters, so old Breaches who never reached Fifth go unnamed.

## 8. Phone

The game runs entirely on the phone (OnePlus 12, 12 GB, CPU, with a local 3–4B model loaded alongside).

- **Phase 0, before sizes are fixed:** get the engine running on the phone (likely Termux with Python, SQLite and numpy), then benchmark a day, a week and a season at several simulant counts with the model loaded.
- **Targets:**

| World time | Target wait |
|---|---|
| A scene turn | under 1 s |
| A day | 1–2 s |
| A week | about 10 s |
| A season | about 1 minute |
| A year | about 4 minutes, in season-sized segments |

- The next segment computes while the player reads.
- Skips stop early only at genuine decision points produced by the simulation. Skip pacing belongs to the narration design, not this spec.
- `k` and the significance ranks are set from these measurements. The expected scale is about 300k simulants, notables in the low tens of thousands and named people in the low thousands, all to be confirmed by measurement.

## 9. Migration from the current engine

- The frozen `background_person_profiles` are retired. People already resolved from them stay individuals.
- The 68 population partitions become the simulant background, re-drawn at the opening from canon anchors.
- Existing named actors keep their identities and histories and take the tier their scores give them.
- Named-person rules are refactored into shared rule functions, one domain at a time, with the regression suite green at each step.
- A schema migration rebuilds the packaged opening, as in schema 108.

## 10. Tests

| Test | Proves |
|---|---|
| Tier invariance | Same person, same draws, same outcome in any tier |
| Conservation | No person is created or lost by splitting, merging or promotion; totals reconcile with births, deaths and migration |
| Look-invariance | Asking a name or catching someone up never changes anyone's fate |
| Chunk invariance | A year as one skip equals a year in small steps |
| Canon calibration | Several decades hold stage counts per sphere, Veinborn shares and population within bands; new Sixths and Peak Sixths within the §7.1 ranges |
| Renewal consistency | A renewed Breach, Fifth or Sixth has decline reset in both mortality and capability; fertility is unaffected |
| Distinction flow | Standouts rise from the background at plausible rates, and the named layer stays within budget |
| Phone budget | A season meets its target on the benchmark profile |

## 11. Out of scope

- Domains 2–6, each with its own spec on this framework: military; commerce; underworld (a primary play style, which must also make territory move; the old decade saw 606 operations and zero territory changes); nobility, land and offices; arts, crafts and fame.
- Narration and skip pacing ("never a bare continue").
- The PC version.
