# Caerness v0.59 — Career, Responsibility, Reach & Underworld-Form Acceptance

## Status

**ACCEPTED for the six-character decade career/reach gate, including the revised underworld organization-form, membership-flow, and operational-scale calibration.** One World-Bible wording correction still remains to fold into the prose master.

Engine `0.59.0`, schema `50`.

v0.59 preserves v0.58 biography/cultivation behavior while correcting four structural problems: career development was too ladder-shaped; independent underworld growth was incorrectly being modeled as personal promotion; gang manpower was initially treated too much like a net-growth counter; and Cale's diagnostic opening was arbitrarily forced into an eight-person gang despite a much larger functional footprint.

## Governing model

- **Standing** is a coarse description of durable professional/social place. It may change, but it is not the universal mechanism for giving someone new work.
- **Responsibilities/appointments** branch sideways and can overlap. An actor may lead patrols, teach, coordinate volunteers, manage factors, specialize in horses, or take high-value contracts without first climbing every standing band.
- **Reach** changes the opportunity pool. Stage, wealth, reputation, service, trust, business scale and prior success can open larger work without forcing a title change.
- **Underworld organizational form is not a rank.** A gang, Mafia-style family, criminal dynasty, syndicate, criminal enterprise, network or crew can each be small or large, weak or powerful, durable or unstable. Scale alone never converts one form into another.
- **Gang manpower is stock-and-flow.** Current core members, active members and peripheral associates are stocks; recruitment, desistance, defection, custody, death/incapacitation, relocation and movement between tiers are flows. There is no target final size.
- **Unspecified opening manpower is resolved from operational footprint, not a label such as “small gang.”** Explicit canon/scenario headcounts override this resolver. Otherwise rackets, territorial work, fronts, enforcement capacity, command depth and other concrete obligations determine the plausible staffing demand, with stochastic variation around it.

## Six-decade results

| Character | Year 0 | Year 10 | What actually changed |
|---|---|---|---|
| **Cale Brann** | Boss of an independent Aldergate ward gang; canonical seed resolves 37 full members + 17 peripheral associates | Boss of the same **gang**; 33 full members + 4 peripheral associates in seed 9201 | The gang experiences substantial turnover (31 entrants, 48 exits/losses), multiple gang fights, delegated collections, a functioning cartage-yard front, targeted violence, racket diversification and modest territorial/front growth. No underworld career promotion and no gang→Mafia conversion. |
| **Sella Marrin** | Temper; Working Escort Hand | Breach; still Working Escort Hand | Formal standing stayed put, but her actual opportunity set widened: she received higher-value Road commissions above her durable standing because Stage/reputation qualified her. |
| **Tobin Verra** | Temper; Junior Disciple | Third; Senior Disciple | Standing changed, but appointments branched independently: External Representative, Disciple Examiner and Patrol Lead became possible/actual through capability and service rather than a compulsory ladder. |
| **Ansel Rooke** | Temper; Retainer | Temper; Senior Retainer | Advanced professionally despite no cultivation breakthrough; gained Remount / Horse Readiness Specialist responsibility. |
| **Mara Elwick** | Parish Worker | Trusted Parish Worker | Local trust/service changed durable standing; gained Volunteer Coordinator; no forced elite ecclesiastical office. |
| **Elian Torve** | Local-Scale Operator | Still Local-Scale Operator | Business grew materially; larger commercial reach opened without title inflation; gained Factor / Carrier Coordinator. |

## Cale / underworld scale correction

Cale is not a collector who eventually “earns” Crew Leader. His opening facts already make him the boss of an **independent Aldergate ward gang**, so he has no underworld career ladder. The engine tracks the gang itself.

The former eight-member opening has been removed. It was not justified by the scenario's actual functions.

### What the opening actually says

Before the camera begins, Cale's operation already has:

- a legitimate cartage-yard front;
- two recurring criminal income streams (protection/collections and stolen-goods handling);
- enough people to conduct group enforcement and gang fights;
- enough organizational reach to commission targeted killing;
- delegated work beneath Cale rather than every action being personally performed by him;
- a recognizable ward-level criminal presence.

Those facts are now the input. Headcount is a **resolved consequence**, not an independent premise.

### Operational-footprint opening resolver

For Cale's current footprint (`racket_breadth=24`, `territorial_presence=22`, `front_depth=28`, `violence_capacity=28`, command depth 2, two recurring rackets, operating front, group-violence capacity, targeted-killing capacity), ten opening-resolution seeds produce:

| Seed | Full members | Peripheral associates | Wider orbit |
|---:|---:|---:|---:|
| 9201 | 37 | 17 | 54 |
| 9202 | 45 | 20 | 65 |
| 9203 | 51 | 28 | 79 |
| 9204 | 32 | 17 | 49 |
| 9205 | 54 | 31 | 85 |
| 9206 | 35 | 14 | 49 |
| 9207 | 64 | 17 | 81 |
| 9208 | 31 | 18 | 49 |
| 9209 | 34 | 18 | 52 |
| 9210 | 55 | 19 | 74 |

This is **not** a new “correct gang size” table. It is a calibration test showing that this particular operating footprint resolves into a gang in the tens rather than a micro-crew, and that it does not collapse to one hard-coded number.

A lighter criminal footprint can still resolve to a 4–10-person crew/micro-gang. A much larger territorial or federated gang can be far larger. Organizational type remains independent of scale.

### Canonical decade seed (9201)

Opening:

- form: **gang**
- hard core: 8
- ordinary active members: 29
- full membership: **37**
- peripheral associates: **17**
- wider orbit: **54**
- command depth: 2
- racket breadth: 24
- territorial presence: 22
- front depth: 28
- violence capacity: 28

After ten years:

- form: **gang** (unchanged)
- hard core: 12
- ordinary active members: 21
- full membership: **33**
- peripheral associates: **4**
- wider current orbit: **37**
- lifetime entrants to the gang orbit: **31**
- lifetime exits/losses: **48**
- command depth: 2
- racket breadth: 30.18
- territorial presence: 25.0
- front depth: 30.8
- violence capacity: 30.1

This is a contracting/stabilizing personnel history despite improving criminal/economic reach. The gang did not have to grow numerically simply because its front and rackets became more effective.

An alternate final-code decade (seed 9204) opens at **32 full + 17 peripheral** and ends at **26 full + 12 peripheral**, after **44 entrants and 55 exits/losses**. This confirms that neither the opening nor the ending is being pulled toward the canonical 9201 numbers.

### Research guardrail

Modern evidence is used only to keep the scale model from making obviously narrow assumptions, not as literal Caernessian demographics:

- The National Gang Center's 2012 estimates were roughly 30,700 gangs and 850,000 gang members nationally; simple division gives about 28 members per gang as a crude aggregate, not a typical-size target.
- U.S. DOJ gang-structure material notes gang sizes ranging from four or five members to thousands and distinguishes core, regular/associate, peripheral/fringe and recruit participation.
- FBI/DOJ descriptions emphasize that gangs vary greatly in size and structure; large sophisticated gangs remain gangs rather than “advancing” into Mafia organizations.

See `diagnostics/v59_underworld_operational_scale_calibration.json` for the exact research notes, opening samples and decade checks.

## Parallel underworld forms

The engine supports `gang`, `mafia_family`, `criminal_dynasty`, `syndicate`, `criminal_enterprise`, `network`, `crew`, and `other` as parallel organizational forms. The database forbids automatic gang→Mafia-family promotion metadata, and the v0.59 regression explicitly grows a gang beyond a smaller Mafia-style family while asserting both retain their distinct forms.

Current canon is preserved rather than flattened: Tallow remains represented as a **criminal dynasty** and Greyhook as a **criminal enterprise/logistics organization**. A future Mafia-style family is only typed as such when its actual institutional structure warrants it.

## Protagonist-agnostic check

The career/reach system is not focus-only. Across the six worlds, ordinary non-focus actors also receive standing changes and branching responsibilities. Counts are retained in `diagnostics/v59_career_reach_organization_audit.json`.

## Regression status

PASS after the operational-scale correction:

- v59 flexible career/reach and underworld-scale regression
- v37 underworld ecology
- v45 decade integrity / latent commercial emergence
- v44 autonomous two-way resolution
- v42 long-run cultivation demography
- v35 autonomous combat/tournaments
- v33 elixir/Sediment/Rupture conservation
- v32 causal cultivation/Realization
- v29 commercial logistics conservation
- v20 health/aging

## Remaining prose-source correction

The current World Bible sentence stating that street gangs “rise and disappear quickly” is too categorical for the revised/researched model. The engine now permits both ephemeral and durable gangs. That sentence should later be revised so durability and organizational form remain separate concepts. This handoff does **not** silently relabel Tallow as a Mafia family.

## Diagnostics

- `diagnostics/v59_career_reach_organization_audit.json`
- `diagnostics/v59_underworld_operational_scale_calibration.json`
- `diagnostics/follow_underworld_latent_report.json`
