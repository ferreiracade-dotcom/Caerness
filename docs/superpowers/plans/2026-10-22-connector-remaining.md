# Caerness connector: what still needs doing (2026-10-22)

State: branch `feat/claude-connector`, pushed; server runs a058502 (schema 115). Live: gaps 1–5, 4a/4b, culture, travel fix, act rework, veto-based `author`, `create_protagonist`, households staffed and paid. Ansel has a fresh lived past (backup `/var/lib/caerness/backups/ansel.pre-livedpast-20261022T122628Z.db`). Runbook, rules and earlier history: `2026-10-16-connector-handoff.md` and `AGENTS.md`.

Owner principles that govern every item below: the engine is a veto, not a menu (named contradictions only, no closed lists, ladders or caps); oversized requests get partial results with the reason; the engine exists for persistence, memory, plausibility and numbers; the GM has creative freedom.

## 1. Owner, next
- [ ] Phone playtest as Ansel: businesses, outfit, his new family and past, an operation, an `advance` of a month, an attack on him (pending → `act respond`).
- [ ] Playtest new-character creation once (a fresh campaign starts with the creation conversation).
- [ ] Pick the GM model (Sonnet medium for value, Opus low for quality).

## 2. Verification debt (do before or alongside the playtest)
- [ ] Full regression suite never run on the final code (last full run 139/139 was before gap 3). Run it once in a clean worktree; fix only real failures.
- [ ] `tests/new_character_acceptance_test.py` (gap 5 plan, Task 8) not written.
- [ ] Review-fix tests (a058502, 5893442) were not watched failing first. The outfit-loan repayment test only checks the treasury when the demand is accepted, so it can pass without exercising repayment; make it deterministic.
- [ ] Re-run `tools/uw_calibration.py` once (365 days) after gap 5: households now have staff and service terms, so servants quitting should no longer read 0; check violence per outfit and 30-day timing (about 5.5 s now).

## 3. `act` leftovers (hard-coded limits audit, `notes/2026-10-17-hardcoded-limits-audit.md`)
- [ ] #10 / D4 Remote contact: speak, hire, order or demand someone in another town. It should become a letter, messenger or summons that lands after real travel time; an attack at a distance becomes pursuit or ambush.
- [ ] #27 Presence judged two ways: `speak` uses a random presence test, operations use same location. One rule.
- [ ] Partial trade price: a sale or purchase the buyer can only part-fund should settle in part, not refuse.
- [ ] Hireling pay in `free_operation._commit` vanishes where the place has no households; pay a real recipient (the nearest settlement's households, or the hirelings' own households).
- [ ] D3 Poaching: a man serving another outfit should open a negotiation with a price (or an approach through his superior), not a refusal.
- [ ] D6 Lending rate not in the list: take the nearest rate and say so.
- [ ] D9 An order a man won't carry out: give him a counter (part of it, more pay, more time).
- [ ] Closed enums still in `player_operations.py:784` (`demand` kinds) and `:1023` (`attack.intent_kind`): confirm unknown kinds route to the free operation instead of "must be one of".
- [ ] #25 `lore` cuts passages at 1800 characters with no marker of the cut.
- [ ] #20 `scene.present` is now capped at 5 (resume budget). Check that a big holding (many staff, many businesses) still shows what matters; `lookup` covers the rest.

## 4. World content still to build
- [ ] Culture leftovers: faith and religious practice, succession customs, fame and reputation spreading.
- [ ] Gap 6, canon pass on currency, wages and prices (the World Bible lists them as "still to calibrate").
- [ ] `lookup` for events; there are no recorded world events before day 0.
- [ ] Time of day in scenes (no canon calendar yet: owner decision).

## 5. Housekeeping
- [ ] Merge `feat/claude-connector` into `master` once the playtest signs it off (ask the owner first).
- [ ] The ChatGPT guide lives on branch `chatgpt-guide` only; keep it out of the connector deploy.
- [ ] The local `mcp__caerness__*` tools read a stale local server; verify on the live server (or restart the local one) when checking play behaviour.

## 6. Later, owner idea
- [ ] A second world on the same connector: each campaign records its world; worlds bring their own packaged DB, rulebook part, lore and profile; Caerness-specific systems (Stages, Mantle, underworld canon, regional cultures, name pools, sex ratios) move behind that profile. First step: an audit of where the engine assumes Caerness. Start after the Caerness playtest.

## How to work
Sonnet subagents implement, one Opus review per batch, check every diff; relevant tests only unless a full run is the task; deploy = push, back up `ansel.db`, `sudo bash /opt/caerness/deploy/update.sh`, then `curl 127.0.0.1:8765/health` (the script's own check races the start). Never write `data/caerness.db` outside a tested migration; never print secrets.
