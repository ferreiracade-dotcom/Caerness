# WORLDHIST-01A Stage 1 — FAMILY-02 + HARM-01 acceptance

**Date:** 22 September 2026  
**Base:** TENYEAR-02 accepted development baseline `6f42fda5e0beeaea743227680c86ba5ce10a1458`  
**Schema:** 105  
**Status:** focused acceptance PASS; full WORLDHIST-01A tranche not yet complete.

## FAMILY-02

- Union mutation now rejects direct known kin, shared-parent siblings/half-siblings, grandparent-descendant pairs, and aunt/uncle-to-niece/nephew pairs.
- Culture-specific cousin policy remains deliberately unspecified rather than universalized.
- Autonomous union proposals require resolved demographic sex rather than treating missing sex as permission to invent a trajectory.
- Biological birth requires a resolved female/male reproductive pair and a female birth parent consistent with the union's family plan.
- Unknown-sex or same-sex unions cannot fabricate biological births through `register_birth` or `auto_children`.
- `create_union` and `update_family_plan` enforce these constraints at mutation time.

## HARM-01

- New `harm_incidents` authority table records provenance from a concrete source event into transient harm, persistent injury, or death.
- Harm resolution distinguishes controlled, accidental, hostile, and lethal intent.
- Replaying the same source against the same actor is idempotent.
- Resolved duels now project final anatomical consequences through HARM-01.
- Controlled tournament/challenge contexts can injure but cannot become immediately fatal through HARM-01.
- Lethal challenge terms no longer mean guaranteed death; lethal intent is resolved through HARM-01.
- WAR-01 named killed/wounded consequences now use the same HARM-01 path rather than a separate direct health/death writer.
- Persistent harm produces real `health_conditions` with provenance, feeding existing health, disability and cultivation-injury mechanics.

## Gate behavior

Schema 105 creates a fresh pending ONEYEAR acceptance epoch:
`ONEYEAR_WORLDHIST01A_SCHEMA105`.

The schema-104 TENYEAR-02 acceptance remains historical evidence and cannot unlock a schema-105 decade.

## Focused regression evidence

PASS:
- `family02_feasibility_firewall_test.py`
- `harm01_shared_consequence_test.py`
- `v34_test.py`
- `v35_test.py`
- `integration01_health_agriculture_law_test.py`
- `war01_campaign_battle_world_consequences_test.py`
- `schema104_reconstructed_parity_test.py` as retained-capability parity under current schema.

## Fresh opening

Fresh current seed + activation under schema 105:
- story day: 0
- population: 52,000,000
- background-person profiles: 2,272
- professional profiles: 100
- activation version: 20
- harm incidents: 0
- SQLite integrity: `ok`
- FK violations: 0
- schema-105 ONEYEAR epoch: pending

## Not yet claimed

Stage 1 does **not** yet implement the remaining WORLDHIST-01A pieces:
- INTERACT/REL-02;
- ORGPRESS-01;
- SUCCESSION-02;
- EMERGENCE-02;
- full post-tranche 108-file regression/ONEYEAR acceptance.
