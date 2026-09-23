# WORLDHIST-01A — Schema 107: review fixes, Windows runtime fixes and FAMILY-02 sex resolution

**Date:** 23 September 2026  
**Engine:** v0.60.0  
**Schema:** 107  
**Parent checkpoint:** `5e9904b` (schema-106 handoff README)

## 1. Code-review fixes to the Stage 1/2 WORLDHIST code

- A blocked re-approach no longer silently returns a stale refusal as if it were a new interaction. Counterproposals are exempt from the block. Opportunity proposals are keyed by proposal id, not title. Blocked opportunity and domain-action callers record `rejected`/`blocked`.
- War: members who already died elsewhere are no longer battle casualties (this previously raised an error and aborted the engagement). An authoritative `killed` result always ends the life.
- FAMILY-02 kinship: disputed/informal links and adoptive parentage bar unions again. Only `former` links do not.
- HARM-01: fatal duel harm passes the event logger through, so `life:death` events are emitted again. The harm RNG seed includes `source_kind`.
- One shared `project_resolved_duel` hook serves both exchange-resolved and referee-decided duels.
- Death-driven succession runs after the death is fully recorded, inside a savepoint.
- `resolve_authority_transition` no longer starts a duplicate regime for polities.
- Duel stakes 0 are respected. `_candidate_rows` no longer re-queries per candidate.

## 2. Windows runtime

- `engine.db.connect()` returns a connection whose `with` block also closes it. Previously sqlite3's statement cache kept unclosed connections, and their file handles, alive until cyclic GC. Windows cannot delete or replace an open database file.
- `tests/underworld_rackets_assets_test.py` closes its own connections before rebuilding the database.

## 3. FAMILY-02 demographic-sex resolution (schema 107)

FAMILY-02 treats missing sex as incomplete state (no union proposal, no biological birth). The v1.4 seed never encoded sex, so 341 of 413 union-eligible named adults could never form a family, and every newborn was `unspecified`.

`engine/demographic_sex.py` resolves every named character once, in evidence order, and records the basis in `actor_life_profiles.metadata_json.demographic_sex_basis`:

1. `canon_text` — a gendered title/kin noun in the seed person's own canon text (Queen, Crown Prince, "younger sister"). Conflicting evidence is ignored.
2. `canon_rule` — the Grand Coven Mantle is male-only (holder and Mantle-eligible heirs).
3. `given_name` — reviewed lists of clearly gendered given names, including invented names with a conventional gendered form.
4. `seeded_roll` — a deterministic 50/50 draw keyed on the seed identity, used only for genuinely ambiguous or invented names.

Newborns receive a seeded 50/50 roll (the background population's convention). Named people created during play (latent crystallization, generated underworld personnel) are resolved at creation. Migration 107 backfills existing databases. The packaged `data/caerness.db` has been migrated and is still day 0.

Opening result (464 seed persons plus 56 already-sexed crystallized persons): canon text 27, canon rule 2, given name 411, seeded roll 24, unresolved 0.

## 4. Evidence

- Full regression, each `tests/*_test.py` run in isolation on Windows with scratch databases: **110/110 completed tests pass**. `v26_candidate_scale_test` (~15 min) was still running at commit time; it passed on the same branch before the schema-107 change. `tenyear02_opening_activation_gate_test` must be pointed at a copy of the packaged database.
- New `tests/family02_sex_resolution_test.py`. Updated `v13` (HARM-01 duel note), `v19_edge`, `v28` and `v43` (fixtures now carry the sex FAMILY-02 requires).
- One-year run on a copy of the migrated opening: population 52,000,000 → 52,117,780 (identical to the schema-104 ONEYEAR). Integrity `ok`, zero FK violations, zero named characters with unresolved sex.
- Day-180 → day-365 replay: 439 substantive tables identical after masking wall-clock timestamps (`coverage_*` bookkeeping excluded).

## 5. Not claimed

This is not a fresh integrated ONEYEAR/TENYEAR acceptance. `ONEYEAR_WORLDHIST01A_SCHEMA107` is pending. Player-character creation still takes no sex, so the player cannot form a union.
