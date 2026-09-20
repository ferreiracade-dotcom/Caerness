# Caerness Engine Depth Audit — v0.1 through v0.17

## Purpose

The earlier implementation audit asked whether a subsystem existed as executable, persisted runtime behavior. This audit asks a harder question:

> **Is the subsystem deep enough to support a decades-long Caerness campaign without repeatedly falling back to generic placeholders, bespoke scripting, or narrator invention?**

The rating scale is:

- **Deep enough for current target** — causally useful, persistent, varied enough to support long play now.
- **Implemented but thin** — real runtime behavior exists, but the state vocabulary or evolution rules are too generic for the intended 40-year living-world simulation.
- **Substrate only** — important foundations exist, but the domain itself is not yet simulated at the intended level.
- **Absent** — no dedicated authoritative simulation layer yet.
- **Deliberately deferred** — intentionally outside the current engine target.

This audit is based on the actual schema, executable services, CLI/runtime exposure, and cumulative tests in v0.17. Design prose alone is not credited as implementation.

---

## Executive result

The engine's **authority architecture is strong**. SQLite truth, shared story time, player-safe information boundaries, model validation, continuity, crystallization, embodiment, professional interpretation, time skipping, and the revised battle stack are not the problem.

The main depth gap is that **social and civilian life is still much less differentiated than combat and character authority**. v0.16-v0.17 established a genuine civilian substrate, but enterprises, households, culture, institutions, and world-scale change still need several domain passes before a 40- or 100-year simulation would feel like a civilization rather than a durable event database.

The most important finding is therefore:

> **Do not begin the final long-run validation yet. First deepen the thin domains that long-run tests would otherwise merely expose.**

Recommended order:

1. v0.18 — Business ecology and differentiated urban commerce.
2. v0.19 — Household, kinship, demographic and life-course simulation.
3. v0.20 — Health, aging, disability, recovery and medicine.
4. v0.21 — Religion, ritual, patronage and cultural institutions.
5. v0.22 — Seasons, ecology, travel friction, harvest and environmental cycles.
6. v0.23 — Political/state transformation and institutional succession at polity scale.
7. v0.24 — Education, apprenticeship, mentorship and intergenerational transmission.
8. v0.25 — Long-run simulation validation and hardening.

The numbering is a working roadmap, not a canon commitment.

---

# Audit matrix

| System | Rating | What is genuinely implemented | Why the rating is not higher / next requirement |
|---|---|---|---|
| SQLite authority, transactions, backup/restore | **Deep enough for current target** | Persistent world truth, WAL SQLite, migrations, backups, restore validation, deterministic state ownership. | Long-run stress may expose performance/indexing issues, but conceptually complete. |
| Shared story time | **Deep enough for current target** | All major systems advance from the same campaign day; real-world absence does not advance the world. | Needs long-run performance validation only. |
| Canon retrieval and canon/campaign separation | **Deep enough for current target** | DOCX indexing, chunk retrieval, canon status, camera-safe use, campaign history kept separate. | Later canon revisions may need stronger conflict tooling, but core authority is correct. |
| Actor resolution scheduler | **Deep enough for current target** | ACTIVE/STRATEGIC/DORMANT cadence plus continuity resolution metadata; dormant actors continue off-camera. | Could later gain load-adaptive scheduling, but no major conceptual gap. |
| NPC goals, pressures and decisions | **Implemented but thin** | Persistent goals, pressures, drives, decisions, resources and actor context; NPCs act independently. | Decision vocabulary remains comparatively generic. Decades of life will need richer domain-specific goal generation from careers, households, politics, religion, health and institutions. |
| Relationships | **Implemented but thin** | Persistent stance/trust/obligation and interaction effects. | Too few relationship dimensions for kinship, mentorship, patronage, rivalry, dependency, affection, hierarchy and institutional duty over decades. Household/kinship pass should deepen rather than replace this layer. |
| Interactions, agreements and conflict | **Deep enough for current target** | Offers, requests, contracts, alliances, negotiations, demands, threats, investigations, attacks, mediation, agreements, counters and wake-up behavior. | Domain-specific contracts can be added by later systems; general interaction machinery is strong. |
| Information, rumours and knowledge provenance | **Deep enough for current target** | Event visibility, secrecy, rumourability, route/channel propagation, exposures, provenance, actor knowledge and player-safe packets. | Institutional secrecy and archival/document ecosystems can deepen later, but the information architecture is already sufficient. |
| Player action interpretation and agency handoff | **Deep enough for current target** | Actions interpreted before mutation, handoff rules, meaningful choice pauses, competence execution and narration after resolution. | Long-run testing only. |
| Model gateway / local model / manual ChatGPT-Claude bridge | **Deep enough for current target** | Bounded action/NPC/narration tasks, stored requests/responses, routing, local endpoint, manual packets. | Provider/runtime changes are maintenance rather than world-simulation depth. |
| Mobile runtime | **Deep enough for current target** | Phone-first server/UI, local runtime configuration, scene/matter/world access and backup path. | UX polish is separate from simulation depth. |
| Continuity cores / historical anchors / cohorts / resolution | **Deep enough for current target** | Persisted identity core, anchors, cohorts, careers, institution profiles, latent entities and resolution transitions. | More entity kinds need to make fuller use of the substrate, especially places, institutions and cultural works. |
| Historical crystallization | **Implemented but thin** | Constrained person crystallization, anti-convenience firewall, proposal validation, lineage audit and campaign-history commitment. | v0.9 is still person-centered. Latent institutions, local places, works, lineages and historical businesses need equivalent crystallization pathways. |
| Character embodiment | **Deep enough for current target** | Persistent voice/temperament/values/habits/social style, speech mediation, autonomous-expression checks, commitment firewall. | Character development over decades should eventually use life events and relationships as evidence, but the embodiment authority model itself is sound. |
| Competence interpretation | **Implemented but thin** | Domain scores, specialties/experience, professional readings, uncertainty and advisor separation. | Learning, decay, teaching, certification, apprenticeship, cross-domain transfer and mastery formation are not yet a full developmental system. v0.24 should deepen this. |
| Time-skip resolver | **Deep enough structurally; thin in supplied life systems** | Transactional preview/rollback, focus, obligations, interruption thresholds, world advancement, historical bridges. | It can only evolve what downstream systems know how to evolve. Once family, health, religion, politics and ecology deepen, time-skip should integrate them automatically. |
| Battle resolution | **Deep enough for current target** | Persistent engagements, sides, units, command roles, unit autonomy, morale/cohesion/readiness/logistics, information restriction and deterministic rounds. | Leave stable until long-run/actual-play feedback. |
| Multi-front command and tactical grammar | **Deep enough for current target** | Zones, command links, delayed orders/reports, doctrines, tactical families, local pressure, Vein assets and contextual personal-combat consequence. | This already received the second-pass hardening that other civilian systems now need. |
| Duel resolution | **Deep enough for current target** | Abstract intent/risk/resource posture, character competence, hidden technical state, linked battle consequences. | Detailed medical aftermath correctly belongs to health system rather than duel mechanics. |
| Generic market and production layer | **Implemented but thin** | Goods, local supply/demand/friction prices, production capacity, enterprise accounts and status. | Goods do not yet form rich production chains; labor classes, wages, inventories, trade flows and demand sources are compressed. Business ecology should begin differentiating enterprise behavior now. |
| Enterprise/business layer | **Implemented but thin** | Persistent enterprises, capital/cash/debt/reputation/admin/labor/risk; partnerships and credit. | Enterprise kinds are only broad containers (`shop`, `workshop`, `service`, etc.). Inns, theatres, gambling houses, pleasure houses, lenders, smithies, tailors, healers, warehouses and similar businesses do not yet behave differently. **Immediate priority.** |
| Credit and partnerships | **Implemented but thin** | Loans accrue, default, affect borrowers; ownership and governance are distinct. | No lender portfolio, collateral enforcement pipeline, interest market, partnership disputes or business-type-specific finance behavior yet. Expand as business/politics systems mature. |
| Households | **Implemented but thin** | Membership, headship, wealth/liquidity/cohesion/staff/hospitality, succession plans, claims and inheritance event. | No general life-course: marriage, household formation/splitting, births, adoption/guardianship, widowhood, dependants, servants/retainers turnover, kin obligations or demographic replacement. **Major pre-long-run gap.** |
| Demography / migration | **Substrate only** | Actors have locations and cohorts; travel exists; some latent population concepts exist. | No authoritative births, deaths from ordinary causes, fertility, migration cohorts, urbanization, age structure or population replacement. |
| Careers and professions | **Implemented but thin** | Career tracks/stages, elapsed experience, explicit entry requirements, professional memberships, standing/seniority/review eligibility. | Career systems do not yet generate job competition, vacancies, retirement, apprenticeship chains, institutional staffing pressure or profession-specific work rhythms. |
| Education / mentorship / transmission | **Substrate only** | Careers have optional mentor IDs; continuity/history can record apprenticeship; institutions have pipelines in metadata. | No persistent teaching relationship, curriculum/manual access, skill transmission, student progression, master succession or educational capacity system. |
| Buildings / architecture | **Implemented but thin** | Buildings persist with type/style/capacity/condition/prestige/utility/maintenance and age under time. | Buildings do not yet house businesses/households/institutions operationally, constrain urban capacity, generate rents, or form neighborhoods. Good foundation, not a complete built-environment simulation. |
| Styles / fashion | **Implemented but thin** | Style movements, location adoption, elite support, craft capacity, resistance, object links and diffusion. | No consumer groups, garment lifecycle, workshop response, seasonal fashion, court/urban subcultures, critics or explicit demand feedback into textile businesses yet. |
| Cultural objects / provenance / auctions | **Deep enough as an object-history substrate** | Creation, ownership, condition, reputation/value, provenance, auctions, inheritance, shadow-market links. | The surrounding cultural ecosystem is thin: creators, performers, patrons, schools, venues, critics, commissions and audience formation need richer simulation. |
| Culture / performing arts | **Substrate only** | Projects, objects, style and some institutions can represent cultural activity. | Theatre companies, performers, repertoires, venues, audiences, patronage networks, artistic schools and careers are not dedicated systems yet. Business ecology can add venues; v0.21 should add institutions/patronage. |
| Underworld / shadow economy | **Implemented but intentionally abstract** | Shadow links carry pressure/exposure/status; information and provenance can represent grey markets. | This is intentionally not a procedural crime simulator. Later work should deepen social/economic consequences without operational wrongdoing mechanics. |
| Religion | **Absent as a dedicated simulation layer** | Can currently be represented only through generic actors, institutions, buildings, events and metadata. | Needs calendars/ritual, clergy/lay roles, patronage, sacred sites, vows/obligations, institutional property and lived-practice effects. **Major gap.** |
| Health, medicine and aging | **Absent as a dedicated simulation layer** | Combat avoids inventing medical consequences; competence includes medicine; world bible canon exists. | No health states, disease/injury recovery, disability, aging curves, fertility implications, care capacity, Vein-Mending treatment or mortality process. **Major gap.** |
| Seasons, ecology and environment | **Substrate only** | Generic world/location processes can change metrics; routes have travel days; current geography exists in canon and combat zones. | No season calendar, weather/road/pass/river state, harvest cycle, shipping season, ecological production effects or regional current cycles integrated into ordinary world time. **Major gap.** |
| Travel and logistics | **Implemented but thin** | Location graph, travel days, player travel and information routes. | Seasonal travel, convoy capacity, lodging, freight, route closures, shipping schedules, migration and logistics costs are not yet deeply modeled. |
| Politics / states / territorial change | **Substrate only** | Institutions/actors, agreements, conflict, clocks, world processes and locations can represent politics. | No explicit polity/territory/dynasty/vassal/succession/annexation/federation/secession model. The starting map therefore cannot yet robustly diverge under generic rules. **Major gap.** |
| Institutional succession | **Implemented but thin** | Household succession exists; generic actor/institution pressure can create succession events; career/professional systems persist roles. | There is no general office/charter/governance succession model for sects, merchant houses, states, temples, guilds or civic institutions. |
| Economy at state/regional scale | **Substrate only** | Local markets, enterprises, credit, world metrics and merchant actors exist. | Taxes, treasuries, public debt, large trade balances, infrastructure spending, harvest revenues and war finance are not an integrated macro layer. |
| Long-run validation | **Absent** | Unit/regression tests cover individual systems and short advances. | No 20/40/100-year scenario suite yet. It should come only after the major thin domains above are deepened. |

---

# Findings by priority

## Priority A — deepen before any 40-year claim

### Business ecology

The enterprise schema is real but too generic. A theatre, smithy, inn, moneylender, gambling house, pleasure/courtesan house, warehouse and healer can all be stored, yet the engine does not currently understand that they have different demand drivers, cost structures, clientele, regulation exposure, capacity use, seasonality or reputation dynamics.

**Action:** v0.18.

### Household and demographic life

The engine can inherit a household after its head dies, but it does not yet naturally create the next generation whose inheritance matters. This is the clearest long-run contradiction.

**Action:** v0.19.

### Health and aging

The world bible gives aging and medical logic substantial causal importance, while the runtime currently has no authoritative health state. Combat deliberately postpones injury detail to a future system, which is correct, but that future system must now exist.

**Action:** v0.20.

### Religion and cultural institutions

Religion is part of daily social reality in the architecture but currently has no dedicated runtime. Culture has objects and styles without enough institutions and people producing/performing/curating them.

**Action:** v0.21.

### Environment and seasons

Generic world-process metrics are useful infrastructure, but a world with roads, rivers, passes, farming, ports, campaigns and current geography requires recurring environmental cycles rather than only arbitrary scalar drift.

**Action:** v0.22.

### State transformation

The current actor/institution machinery can represent political events but does not yet make the political map structurally mutable through ordinary engine rules.

**Action:** v0.23.

### Education and transmission

A multi-generational world needs skills, institutions and martial/professional traditions to reproduce themselves through actual teaching pipelines.

**Action:** v0.24.

---

# Systems that should not be reopened now

The audit does **not** recommend another conceptual rewrite of:

- authority boundaries;
- story-time ownership;
- model gateway rules;
- information/player-knowledge separation;
- agency handoff;
- historical continuity principles;
- battle tactical architecture;
- duel abstraction;
- commitment firewall.

Those should be tested and extended only where later domain systems require integration.

---

# Release decision

The depth audit therefore rejects the v0.17 audit's statement that the civilian layer is already broad enough for final long-run testing.

A more accurate statement is:

> **v0.17 is broad enough to begin the final domain-deepening sequence, but not yet broad enough for a meaningful 40-year validation of Caerness as a living civilization.**

The immediate implementation target is **v0.18 Business Ecology**.
