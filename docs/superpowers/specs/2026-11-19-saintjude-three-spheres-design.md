# Saint Jude: one city, three spheres (design)

Date: 2026-11-19. Status: draft for owner approval.

## 1. Intent

Saint Jude must simulate **politics, business and the underworld** well enough that the owner can live in any one of them, or move between them, and all three move each other. There is no win condition, only a good story. Mob play stays as an option. A clean businessman or politician must not get a thinner world than a soldier does.

Why: after task 8 the owner, a Christian, began asking whether they want to play sin as the main thing. The answer is that crime stays available, but the city has to be just as alive for someone who never touches it.

Later, separately: a London/Europe football world (2000s; manager, player, CEO, owner, head of transfers) and a medieval world. Each gets its own design. This document only makes sure Saint Jude's engine work does not block them.

## 2. Goals, non-goals, anti-goals

- **Goals.** One generic engine layer for "people inside an organisation", with each sphere's specifics as package data and thin rule modules on top. Finish mob tasks 10–16 on that layer. Then add business, then politics, as layers on the same core.
- **Non-goals.** No football or medieval work here. No score, win state, or closed menus of actions (engine vetoes, it does not list).
- **Anti-goals.** Mob-only machinery that business and politics would have to copy. Business or politics as abstract numbers (approval %, sector index) with no named people behind them. Breaking Caerness.

## 3. What the audit found (tasks 1–9)

The engine now has **two organisation systems side by side**:

1. **Caerness's general one** (older): `institution_profiles`, `institution_memberships`, `civilian_enterprises` + `enterprise_accounts`/`enterprise_staff`/`business_cycles`, `merchant_trade_contracts`, `organization_regimes`/`organization_factions`/`organization_pressures`/`organization_strategy_positions`. The shapes are mostly world-neutral, and the content is Caerness's. In Saint Jude most of it is switched off (`merchant_houses`, `caerness_trade` false), so **Saint Jude currently has no simulated businesses at all.**
2. **Saint Jude's outfit layer** (tasks 3–9): `outfit_crews`, `outfit_ranks`, `outfit_holdings`, `outfit_lines`, `outfit_money`, `outfit_agenda`, `outfit_incidents`, `pad_envelopes`, plus `outfits.py`, `outfit_opening.py`, `outfit_money.py`, `law_opening.py`.

Task by task:

| Task | Verdict | Mob-only parts |
|---|---|---|
| 1 One connector, both worlds | generic | none |
| 2 VM runbook | generic | none |
| 3 Schema 116 + package data | **needs treatment** | table names `outfit_*`; `outfit_ranks.level CHECK IN (3,4)`; `made_day` as a column; `outfit_money.kind` limited to `take/associate_earning/kickup/executive_share/pad`; `pad_envelopes.payer_outfit_actor_id` (only an outfit can pay an official) |
| 4 Pull up by name group | generic | none |
| 5–6 Families and other gangs at the opening | fine as the **mob layer** | builders live in `outfit_opening.py`; keep, but move shared helpers (pull-up, personality, feelings toward superior) to the core |
| 7 Rackets and monthly flow | **needs treatment** | `capo`/`boss`/`soldier` hard-coded in `outfits.capo_of`, `boss_of`, `outfit_money.line_holder`, `_Roster`, `_post_pad` |
| 8 Law, the Pad, connected people | mostly generic | jurisdictions, agencies and officials are general. The Pad only pays from outfits: it should be one case of "a payer keeps an official sweet" (bribes, retainers, campaign money) |
| 9 Quiet routine and agenda rhythm | **needs treatment** | `has_reason_to_choose` and the daily/weekly review only cover rows in `outfit_ranks`; a foreman or councillor never gets a turn |

Leaving these as they are means business and politics would copy them. **The branch has not shipped (task 16 ships), so generalising now costs one migration and no live saves.**

## 4. Approaches considered

- **A. Generic core, sphere layers on top (chosen).** One layer for org members, units, income lines, money flows, agenda, incidents and arrangements with officials; mob, business and politics as package data plus small rule modules. Costs a refactor of tasks 3, 7, 8 and 9 now. Pays back on every later sphere and on football and medieval.
- **B. Leave outfits mob-shaped; build business on Caerness's `civilian_enterprises`; politics separately.** Least churn now. Three different styles of "an organisation's people" that never share agenda, rhythm or money flow, so cross-sphere stories (the racket and the city contract that are the same story) need glue everywhere.
- **C. One giant merge of both organisation systems now.** Cleanest in theory. Touches Caerness heavily, which risks the main campaign for no Saint Jude gain.

The owner asked for the generic/specific split "only if best for the engine". It is. The refinement over the owner's version is that the core **adopts the outfit layer** (it is the newer, people-first design) and **reuses Caerness's enterprise accounts** for company books instead of writing a third ledger. Caerness's own system is left alone.

## 5. The design

### 5.1 The core (world-agnostic, `engine/orgs*.py`)

Rename and generalise the outfit tables in one migration (schema 117): `outfit_*` → `org_*`, `pad_envelopes` → `org_arrangements`.

- **Organisations** are institution actors with an `org_kind` from package data (`family`, `crew_outfit`, `company`, `union_local`, `ward_organisation`, `party`, `agency`…). No closed list in code.
- **Seats** (`org_seats`, was `outfit_ranks`): actor, org, `role_key`, unit, superior, detail level (no `IN (3,4)` check), standing, personality, status. Rank-specific facts (made day, partner, tenure, elected term) go in `metadata_json` or a sphere table.
- **Role rules from data.** Each package declares per `org_kind`: its roles, which role **leads a unit**, which role **heads the org**, and **who stands in** when a holder dies or is held. `capo_of`/`boss_of`/`line_holder` become `unit_leader_of`, `head_of`, `stand_in_for`, driven by that data.
- **Units** (`org_units`, was crews): crew, department, ward, division.
- **Income** (`org_holdings` + `org_lines`): a source of money and who works it: racket, contract, account, patronage job, ward. A line can be `hidden` (skimming, embezzlement, a no-show job).
- **Money flows** (`org_money`): `kind` is free text validated against the package's declared flows (`kickup`, `salary`, `dividend`, `fee`, `contribution`, `bribe`…). The monthly flow walks the role rules, not rank names.
- **Arrangements with officials** (`org_arrangements`, was the Pad): any payer (an org or a person) keeps an official sweet through a go-between. Kinds come from data: envelope, retainer, campaign money, favour. The mob's Pad becomes one kind.
- **Agenda and rhythm** (`org_agenda`, the task 9 routine): every seated person gets the quiet weekly review and the speed-up. Reason checks are registered per sphere.
- **Incidents** (`org_incidents`): generic, with the kind from data.
- **Motives** (task 10, built here): a person chooses from what his world offers: his lines, his superior, his rivals, his debts, his arrangements. Each sphere registers its choices: a soldier can `start_racket`, an executive can `bid_contract`, an alderman can `trade_vote`. The reading of motives and the single seeded roll point are shared.
- **Law response** (task 13): works on crime kinds from `law.json`, including white-collar ones (bribery, fraud, bid-rigging, election fraud), not just violence.

### 5.2 Sphere layers (Saint Jude package data + small modules)

- **Underworld** (now): `outfits.json` keeps the families and gangs, and declares their roles and flows against the core. `outfit_opening.py` stays as the mob layer's opening builder. Tasks 10–16 finish here.
- **Business** (next, its own plan): companies as orgs with named people (owners, executives, foremen) seated through the core. Their books use the existing `civilian_enterprises` / `enterprise_accounts` with Saint Jude kinds (the `enterprise_kind` check widens to package-declared kinds). Sectors from bible Part I 9 (port, heavy industry, garment, construction, banks) and Part IV (unions, contracts, fronts). Contracts and tenders are what the city, the families and companies compete for.
- **Politics** (after): offices (mayor, council, aldermen, DA, judges where elected), the Machine and wards as orgs, the election calendar from bible Part I 4.6, and votes as agenda items. Patronage jobs are income lines and campaign money is an arrangement.
- **The links** come mostly free: shared people (a capo owns a trucking firm; an alderman's brother is a union president), shared lines (the racket that skims the contract), shared arrangements (the same official on the Pad and on a developer's retainer), and the law response sees all of it.

### 5.3 Order of work

1. **Core refactor (new task 9b):** schema 117 migration, role rules from data, rename and generalise tasks 3/7/8/9 code; all existing Saint Jude tests stay green and Caerness regression passes.
2. **Mob tasks 10–16** on the core, as planned, with generic motive and law-response pieces.
3. **Business layer**: its own spec and plan.
4. **Politics layer**: its own spec and plan.
5. Football and medieval: separate designs that reuse the core.

## 6. Constraints

- Caerness must keep working (its organisation system is untouched; regression tests pass).
- Owner rules hold: engine vetoes, it doesn't list; no ceilings; sex ratios per `power-sex-ratios`; loyalty from bonds, not wages; violence varies by outfit; design figures stay in package data, not engine constants.
- Run sims against a DB copy.

## 7. Left to the builder

- Exact names of the core modules and helpers.
- Whether the rename uses `ALTER TABLE … RENAME` or copy-and-drop (SQLite version dependent).
- How sphere choice functions register (a registry like the task 9 reason checks is the obvious fit).
- Whether the business layer's companies need an `org_seats` row for every clerk or only for level-4 people (follow the task 5 detail ladder).
