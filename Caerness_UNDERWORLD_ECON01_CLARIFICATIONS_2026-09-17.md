# Caerness Underworld — ECON-01 Clarifications and Canon/Implementation Guardrails
**Date:** 17 September 2026  
**Status:** Current underworld clarification note to accompany ECON-01 and the v0.60 roadmap.

## 1. The narrow Phase 1/2 abstractions are scaffolding, not final ontology

The territorial rebuild is still valid, but `front`, `racket`, `protection`, organization treasury and personal wealth must not remain collapsed into one organization-owned abstraction.

The finished model separates:

- **assets / enterprises** — taverns, warehouses, yards, lenders, workshops, houses, etc.;
- **rackets / criminal operations** — protection, gambling, lending, fencing, smuggling, fraud, theft, vice, etc.;
- **accounts / clients / contracts** — e.g. an individual protected business beneath a protection racket;
- **economic interests** — legal owner, beneficial controller, operator, manager, tenant, revenue share, creditor;
- **territorial rights** — where recurring local criminal activity may occur and under whose authority;
- **organization treasury** — pooled organizational funds;
- **personal estate/wealth** — what an individual actually owns or is owed;
- **money flows / obligations** — tribute, shares, wages, distributions, bribes, support, protection payments and reimbursements.

## 2. Protection is a racket type

Protection is not a peer category alongside “racket.”

A protection racket is the operation. Individual protected businesses are **protection accounts** attached to that operation.

One protection racket may therefore have many client accounts, and an organization may eventually have multiple protection books in the same zone if different crews/operators run them.

Protection is unusual because it often has territorial significance. In settled territory, another organization collecting protection is not merely entering the same market; it can amount to poaching a client and challenging local criminal authority.

## 3. One recognized protector is the normal settled-territory case

The earlier wording suggesting a protected shop might receive “protection from every other gang” is misleading.

The intended concept is:

> A business paying one protector may receive real protection **against** thieves, rival crews and other gangs.

A second rival protector is normally:
- a poaching attempt;
- double extortion;
- a territorial challenge;
- or evidence that local authority is contested/breaking down.

An explicit joint arrangement is possible but exceptional.

### Pending World Bible wording fix

Prefer wording such as:

> “A small shop paying protection may genuinely be protected from thieves, rival crews, and other gangs operating in the ward.”

## 4. A front is a use/status of an enterprise, not an ownership class

A legitimate enterprise can be used criminally without the criminal boss personally owning it.

Examples the engine must support:

- organization legally owns and operates a real business;
- member legally owns it while organization has beneficial control;
- independent proprietor owns it while granting criminal use;
- enterprise is genuinely legitimate but also used for meetings, concealment, fencing, storage or collections;
- protected business remains independent and is not a front at all.

Legal owner, beneficial controller and operator must therefore be separable.

## 5. Individuals and crews may run rackets

Mafia-style organizations in particular are not one firm owning every racket. Individuals/crews can operate earning activities and kick a share upward.

A racket may be:
- independently operated by an individual;
- operated by a crew;
- directly operated by an organization;
- affiliated to an organization without being organization-owned;
- independent of any organization.

`organization_id` on a racket must therefore mean optional affiliation/umbrella authority, not legal ownership.

## 6. Treasury and personal wealth are distinct

Organization treasury may fund:
- security/violence;
- bribes;
- legal/advocacy costs;
- fronts/assets;
- recruitment;
- member/household support;
- reserves;
- explicit distributions/draws.

A boss need not receive a modern salary. Personal wealth may instead increase through explicit tribute, shares, distributions, draws, gifts, or personal enterprises.

The important rule is that money paths are explicit rather than implied.

## 7. ECON-01 scope

ECON-01 intentionally does **not** build the full personal-estate system.

It introduces the minimum generic substrate required for honest underworld economics:

- `economic_interests`;
- `economic_flows`;
- protection-account → protection-racket linkage;
- rackets with optional organizational affiliation and actor/crew operation;
- front-use separable from legal ownership;
- explicit bribe/support flows;
- explicit monthly kick-up/tribute/leader-draw records;
- protection invariants and migration/backfill.

Full later estate work still owns:
- residences;
- land;
- valuable movables;
- personal debt/claims;
- inheritance;
- household property;
- long-run autonomous lifestyle purchasing.

## 8. Candidate-action sequencing

Do not broaden `underworld_candidate_actions()` merely by adding verbs before the relevant objects exist.

Correct direction:

territorial foundation → rackets/assets/economic interests/flows → crews & relations → richer concrete underworld candidates → belief-bounded scoring later.

Future candidate vocabulary can include:
- deliberately poach a protection account;
- grant/revoke permission;
- delegate a racket;
- promote/discipline a subordinate;
- retaliate for a grievance;
- make truce/peace;
- acquire/invest in legitimate property;
- start personal/crew racket;
- alter tribute/share arrangements.

## 9. Anti-grandfathering clarification

“Nothing must be grandfathered in” was aimed primarily at the **old city-assigned criminal-family build**:

- old named crime families surviving merely because already written;
- their inherited assignment to particular cities;
- old preassigned city criminal identities/focuses.

It was **not** a blanket instruction to delete every older underworld-adjacent institution.

Current World Bible material independently retains institutions/ecologies such as:
- Painted Veil;
- The Hush;
- The Reckoning;
- Cormorants;
- Red Board (working rather than settled/active canon in the same sense).

These should not be retired merely because they predate the latest rebuild.

The current clean-rebuild firewall should remain focused on the city-specific durable organizations being deliberately rebuilt rather than on unrelated retained institutions. ECON-01 therefore narrows the automatic quarry set to:
- Tallow Family;
- Greyhook Wharf Company;
- Saltwake Combine.

This is **not** a judgment that those three can never return. It means they do not survive automatically from the old city-specific build. They can be independently reconsidered/re-adopted later if the current World Bible/design warrants it.

The general rule remains:

> Nothing survives solely because it was previously written; nothing is rejected solely because it is old either.
