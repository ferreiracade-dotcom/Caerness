# Caerness Engine v0.60.0 — ECON-01 Acceptance

**Date:** 17 September 2026  
**Base:** `Caerness_Engine_v0_60_0_RacketsAssets_WORKING.zip`  
**Engine:** `0.60.0`  
**Schema:** `58`

## Accepted scope

ECON-01 is the bounded underworld economic-relationship correction inserted after the Rackets/Assets milestone and before the territorial event-sourcing spike.

It does **not** implement the full personal-estate system or the later Minerva/PsychSim decision rewrite.

## What changed

### 1. Generic economic interests

New `economic_interests` persistence separates relationships that were previously collapsed together:

- legal owner;
- beneficial controller;
- operator;
- manager;
- tenant;
- revenue share;
- creditor.

Interests can be held by actors, crews, organizations or households and can target an enterprise or racket.

Creation/backfill paths populate these relationships rather than leaving the new table decorative.

### 2. Protection is structurally a racket

`underworld_protection_accounts` now has `racket_id`.

An active protection account must point to an active protection-type racket for the same organization and zone. Schema triggers enforce the invariant on insert/update.

`protect_business()` can reuse/create a protection racket or attach a new client to an explicitly selected valid protection racket. The schema deliberately does **not** impose one protection racket per organization per zone; multiple crew/operator books remain possible.

Territorial conquest/absorption paths were updated so protection does not become an impossible hybrid where the account names one protector but points to another organization's racket.

### 3. Racket affiliation is not ownership

`underworld_racket_sites.organization_id` is nullable and now represents optional organizational affiliation/umbrella authority rather than legal ownership.

A racket can be:

- actor-operated;
- crew-operated;
- organization-operated;
- affiliated with an organization while controlled by an actor/crew;
- independent where territorial rules permit.

Default beneficial control follows the actual operator rather than automatically assigning every affiliated racket to the organization.

### 4. Front is use/control, not ownership class

Existing front creation now records economic interests explicitly.

New `attach_front_use()` can attach criminal/front use to an already-existing ordinary enterprise without changing its legal owner.

A legitimate enterprise may therefore have:

- one legal owner;
- another beneficial controller;
- another operator;
- an underworld business-use relationship.

Seizing the criminal use/control of a front no longer necessarily destroys an independently owned legitimate enterprise. Organization-owned fronts can still be closed/seized as appropriate.

### 5. Explicit economic flows

New `economic_flows` records money movements/obligations including:

- racket kick-up;
- protection payments;
- tribute;
- leader draws/distributions;
- bribes;
- member/household support;
- other share/reimbursement-style flows.

Existing monthly underworld income paths are preserved but are now queryable as explicit flows rather than existing only as treasury arithmetic.

Treasury-funded bribe and support-payment paths are implemented as real expenditures.

### 6. Anti-grandfathering firewall correction

The v0.60 rebuild firewall had over-applied the instruction that the old underworld should not be grandfathered in.

The current World Bible independently retains/recognizes the Painted Veil, Hush, Reckoning and Cormorants, while the Red Board remains a working institution/network.

ECON-01 therefore narrows the automatic clean-rebuild quarry set to the city-specific durable organizations that were the actual target of the anti-grandfathering concern:

- Tallow Family;
- Greyhook Wharf Company;
- Saltwake Combine.

This does not permanently reject those three. It means they are not preserved merely because an older city-specific underworld build already assigned them there.

Migration repair only reverses retirement/quarry status when the v0.60 rebuild firewall itself caused it; it does not arbitrarily reactivate unrelated retired material.

## Migration proof

A real untouched schema-57 Claude database was upgraded to schema 58.

Verified after migration:

- `PRAGMA integrity_check` clean;
- foreign-key check clean;
- all 16 existing active protection accounts backfilled to valid active protection rackets;
- no dangling active protection accounts;
- existing fronts/rackets received inferable economic-interest rows;
- racket `organization_id` is nullable under schema 58;
- preserved institutions were restored only from firewall-caused retirement/quarry state;
- Red Board returns to its prior `working` status rather than being falsely promoted to active;
- Tallow/Greyhook/Saltwake remain quarantined by the rebuild firewall.

## Regression policy correction

Claude's original Rackets/Assets acceptance test rebuilt the **entire Caerness world 300 times** to test one secrecy-weighting relationship.

That is unnecessarily expensive for an ordinary regression suite. It was reduced to **20 full-world paired secrecy trials**, with deterministic seeds, while retaining the same qualitative assertion (`low-secrecy` suppression rate > 2× `high-secrecy`). The exposed-front forced-raid loop was reduced from 60 attempts to 12 because it operates in one already-built world.

The resulting Rackets/Assets suite runs in roughly 15 seconds on this environment instead of several minutes and still tests the intended behavior. Long Monte Carlo/stress sampling belongs in diagnostics/calibration, not the default acceptance suite.

## Final test status

Green on the final ECON-01 source:

- `tests.econ01_underworld_economic_interests_test` — PASS
- `tests.underworld_rackets_assets_test` — PASS (downsized regression)
- `tests.v60_underworld_rebuild_test` — PASS
- `tests.v60_phase2a_test` — PASS
- `tests.v56_test` — PASS
- `tests.smoke_test` — PASS
- `tests.arch01_process_registry_test` — PASS, including parity/persistence and benchmark

ARCH-01 final benchmark in this run:

- eager SQL re-query: ~2.62 s
- lazy cache: ~2.51 s
- no meaningful reason to adopt Mesa; SQL remains authoritative.

## What ECON-01 does not do

Still deferred:

- full generic personal estates;
- inheritance/land/residences/personal valuables;
- complete accounting for every enterprise/household coin movement;
- broad underworld candidate-action expansion;
- PsychSim-style belief-bounded strategic scoring;
- directed-relationship rewrite;
- presence/belief/Competence Lens work;
- ProcessRegistry production cutover;
- whole-engine event sourcing.

## Immediate next task

Proceed to the **bounded territorial event-sourcing spike**.

Use territorial sovereignty as the test owner and prove:

1. typed append-only events;
2. current-state projection;
3. close/reopen persistence;
4. replay to identical state;
5. snapshot + tail;
6. branch/replay experiment;
7. versioned event evolution.

Do not migrate the whole engine at once.
