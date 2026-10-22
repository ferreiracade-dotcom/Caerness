# Handoff: Claude connector after the first owner playtests (2026-10-16)

Read `AGENTS.md` first, then this. You are picking up from a long session that built the connector (step 1), took it remote, and ran the owner's first real playtests. This file is what that session learned; it is the brief for the next work.

## Where things are

- **Branch:** `feat/claude-connector` (pushed to GitHub, public repo). `master` is untouched.
- **Code:** `connector/` (seven MCP tools: `resume`, `scene`, `lookup`, `lore`, `act`, `advance`, `note`), stdio for local dev and Streamable HTTP + single-owner OAuth for remote. Tests: `tests/connector_*_test.py`, `tests/deploy_files_test.py` (all green at `dbff118`).
- **Live server:** Oracle Cloud Always Free `VM.Standard.E2.1.Micro` (1 GB RAM + 2 GB swap, x86_64, Ubuntu 22.04), public IP `92.4.144.46`, `https://caerness.duckdns.org/mcp`. SSH: `ssh -i ~/.ssh/caerness_oracle ubuntu@92.4.144.46`. Code at `/opt/caerness` (branch `feat/claude-connector`), campaigns `/var/lib/caerness/campaigns`, secrets `/etc/caerness/*.env` (never print them). **Deploy:** commit, `git push`, then `ssh ... 'sudo bash /opt/caerness/deploy/update.sh'` (pulls, runs smoke tests, restarts; `curl` health may fail in the first seconds while the service starts). Owner plays on the phone via a claude.ai custom connector. A 30-day `advance` takes ~2.5 s there.
- **Owner's campaign:** `ansel` on the server (the master copy). Protagonist Ansel Fane (actor 901), non-canon underworld figure in Toll's Reach, Third stage, built by hand on day 0 (script in the old session's scratchpad; records marked `{"source":"owner_protagonist_setup","not_canon":true}`). Holdings: Silkwater House (brothel), The Green Table (gambling), The Tollgate Counting Room (loan house); outfit The Fane Houses (org 12, ~25 members, underboss Vera Keen 905, accountant Iria Ward 906); household with steward Dara Harrow 903 and servant Elin Pell 904. A pre-rework copy is on the laptop (`%LOCALAPPDATA%\Caerness\campaigns\ansel.before-rework.db`).
- **Laptop desktop app** still has a local stdio `caerness` entry (campaign `ansel`, laptop copy). It should be removed so only the remote connector exists; the app rewrites its config on exit, so edit only while it is closed.
- **Plans:** step-1 plan `docs/superpowers/plans/2026-10-16-claude-connector-step1.md` (Tasks 1-7 done; Task 8 is these playtests), remote plan `docs/superpowers/plans/2026-10-16-remote-connector-oracle.md` (Tasks 0-5 done, 6-7 done by hand: deployed and measured). Spec `docs/superpowers/specs/2026-10-16-claude-connector-design.md` (Appendix A is the live rulebook text, kept identical to `connector/rulebook.md` by a test).

## What the playtests taught (binding owner expectations)

These are already in the rulebook unless marked **open**:

- The GM is creative: engine silence means unknown, not nothing; the world has a lived history; invent plausibly, never contradict the engine, record what lasts with `note`.
- Open on an ordinary moment; never invent visitors/urgency; `present` is people around town, not seeking the protagonist.
- No engine figure ever appears in prose or OOC answers; describe money by comparison and consequence (no canon currency yet).
- Introduce people/places/organisations briefly on first mention.
- Direct speech, close third past; no engine talk in the fiction.
- Setting facts come from the World Bible via `lore`.
- **Open:** the GM still stalls by asking the player to choose things it should decide (reasons, subordinate names, organisation shape) and explains itself in terms of "the records". Rule to add: decide plausibly and keep going; ask only for the protagonist's own decisions; OOC answers are brief and in-world, never "the records say".
- **Open:** the GM pulled stale memories of an older Caerness (seven stages, "Stirring", "Ascendant") from the owner's claude.ai memory. Rule to add: only `lore` and the engine are the world; ignore any remembered earlier versions of Caerness.
- No recognised same-sex unions (owner rule). The owner reads names as gendered and finds a female "Elias" or male "Dara"/"Vera" absurd.

## Findings from the transcript (verified in the `ansel` DB)

1. **Engine bug: generated names ignore demographic sex.** Dara Harrow and Elin Pell are recorded `male`, Vera Keen `male`, Elias Keen (583, Iron Rooks crew leader, married to Winston Ives 867) `female`. The connector never shows sex, so the GM guessed from names and contradicted the engine. Investigate the name pools and FAMILY-02 sex resolution (`engine/demographic_sex.py`, `resolution_controller._generated_person_name`, background/opening name generation). Fix at the source (sex-appropriate given names for generated, non-canon people; canon names untouched), decide how to repair the packaged world and existing campaigns deterministically, and test it. Check the scale across the whole world first.
2. **Connector gap: `scene`/`lookup` omit sex and organisation membership.** Add sex (or pronoun) and "role, organisation" (e.g. "crew leader, Iron Rooks") so the GM cannot misplace people. Elias was narrated as a Fane captain; the engine has her in the Iron Rooks.
3. **Character-build defects (Ansel):** underboss Vera placed in Rivermoor; no named crew leaders, so "call my captains" had nobody to call; the owner also judged a woman underboss plus a woman captain implausible for this outfit (raise the general question of sex ratios in underworld/martial leadership with the owner against canon before changing engine rates; canon has female bosses). Repair: co-locate leadership, add a few named crew leaders through the engine's normal person paths, and clean the contradictory GM notes for 583/867/905 (they flip-flop on sex and on spouse vs cousin). Ask the owner whether to repair `ansel` in place or rebuild it after the new-character flow exists.
4. `lore` was missing entirely (fixed in `dbff118`; the packaged world ships with an empty canon index; `open_campaign` now indexes it).

## Gap list (agreed with the owner), in the order to build

1. **Continuity:** recap / live thread, character sheet, standing agreements in `resume`; the spec's `campaign` tool; new-chat hint. A new chat currently restores world state and notes but not the conversation's threads.
2. **Underworld and economic action through `act`:** orders to subordinates, collecting debts, pressure/extortion, spending and paying, hiring, buying/selling, fighting. Today `act` only has observe/speak/investigate/respond/travel, so an underworld boss's real actions have no engine path. Reuse engine domain code (`underworld_rebuild.py` operations, merchant/civilian, Codex `domain_actions.py` as parts bin); parameters stay general (spec section 5).
3. **`author`:** validated creation of new people/businesses/arrangements so inventions become real entities.
4. **World connectivity:** Toll's Reach has no underworld zones, so rivals/heat/expansion never reach the Fane Houses; the Red Board is an institution actor, not an underworld organisation. Also scene time of day/season (no canon calendar yet: decide with the owner).
5. **New-character creation (spec 8a)**, then rebuild Ansel with a lived past (he has 0 knowledge rows and 2 relationships). The owner's real campaign starts after this.
6. Optional canon pass: currency, wages, prices (World Bible lists them as "still to calibrate"). Also: `lookup` for organisations/events; no recorded world events before day 0.

## How to work (owner's preferences)

- Use superpowers skills: writing-plans for each piece, then implement with TDD. Owner wants tokens saved: implementation can go to Sonnet subagents, but you review every diff.
- Each piece ends with a short owner playtest on the phone before the next; tests alone don't sign anything off. Ask "can the GM actually do what a player of this character would ask?" before calling a piece done (the `lore` miss came from not asking that).
- Deploy to the server after each piece (see above). Never print secrets; never write `data/caerness.db` except through a deliberate, tested world repair.
- Commit after each task; pushing to `feat/claude-connector` is needed for deploys and is approved for this work.

Start with findings 1-3 (they corrupt every scene), then gap 1, then gap 2.

## Status 2026-10-17 (deployed)

- Findings 1-3 fixed: names follow sex (schema 109 renamed mismatched people; sex kept), scene/lookup show sex and "role, organisation", rulebook "decide, don't ask" and "ignore remembered older Caerness". Settlement identity reservoirs now grow from their own population (cap 2048); background stages follow canon headcounts; newborns and new businesses get real names.
- `ansel` repaired (backup `/var/lib/caerness/backups/ansel.pre-schema109.db`): Dara/Elin/Vera/Elias are now Marek Harrow, Nolan Pell, Willem Keen (underboss, back in Toll's Reach), Celia Keen (Iron Rooks; husband Winston Ives, unaffiliated); crews Silkwater door crew (Varen Marr), Green Table floor crew (Hale Brann), Counting Room collectors (Varen Dane); contradictory notes replaced.
- Gap 1 done (plan `2026-10-16-connector-continuity.md`): `note` kinds detail/recap/rule/sheet/error; `resume` returns the story; fresh-chat hint.
- Gap 2 done (plan `2026-10-16-connector-actions.md`): `act` pay/hire/lend/demand/attack/trade/order via `engine/ledger.py` and `engine/player_operations.py`; tiered outcomes (own will: just happens; others' will/strength: engine decides). Deferred minors are in that plan's ledger notes (`.superpowers/sdd/2026-10-16-connector-actions/progress.md`, git-ignored) and summarised in the session's final message.
- Not yet run: the full regression suite on the final code (owner stopped it; last full run 139/139 on an earlier state). Next: owner phone playtest, then gap 3 (`author`) and gap 4 (Toll's Reach zones, rivals reacting, unpaid wages vs loyalty).
- Model split (owner): Sonnet subagents implement, Opus reviews.
- Gap 3 done and deployed (plan `2026-10-17-connector-author.md`, commits 2c7579d..fc97514): MCP tool `author` (person / business / organisation / rumour) in `engine/authoring.py` + `connector/authoring.py`. People come from the settlement's own background population (outsiders only with `from_elsewhere`), are reliably present where authored, and get a life of their own; businesses/outfits/local bodies get engine-set modest means and the profiles the simulation needs; canon-scale bodies, empty places, and anything owned or led by the protagonist's people are refused; rumours never carry truth. Backup before deploy: `/var/lib/caerness/backups/ansel.pre-author.db`. Not built: authored outfits have no territory/zones (gap 4).
- Owner request 2026-10-17, after gaps 4a/4b: **culture** — canon covers it extensively (e.g. Hearth household/family culture "You belong to people before you belong only to yourself", reactions by Stage and status, House conduct). Goal: how people react to the protagonist and to each other, and how those in his House treat him, follow canon and engine state (status, Stage, kinship, office, reputation) rather than GM habit. Start by extracting the culture canon the way `docs/superpowers/notes/2026-10-17-underworld-canon.md` did for the underworld.
- Gap 4a and culture done and deployed 2026-10-17 (commits ed37501..63c4b91; schema 110; plans `2026-10-17-underworld-everywhere.md`, `2026-10-17-culture.md`). Every settlement of 15k+ has an underworld sized by canon character, features and population: canon outfits re-adopted (Tallow, Greyhook, Saltwake), canon networks present by place, canon fighting markets (Toll's Reach: Red Yard, prize halls, dockside rings, Red Board warehouse ring), local gangs and specialists. Procedural pre-110 gangs dissolved; open `error_reports` reach the GM as `corrections`. Scenes show date/season, standing in words, regional manners and `you_here`; standing weighs in `_social_response`. Owner rulings: leader sex 92% male (gangs/violent), 85% (specialists), 70% (vice); bearing words separate martial artists (Churned in Churn/Hearth martial houses) from non-martial cultivators (First–Third only). Ansel backup: `/var/lib/caerness/backups/ansel.pre-schema110-20261017-091213.db`. Cost: a 30-day advance ~2.1x slower (4.4 s). Open owner decisions: Seth Carrick's place (Waymeet or none), bearing wording, Crownhold court manners. Known minor: `present.who` can show "resolved criminal" for a dissolved gang's former member.
- Next: background occupation follows Stage (Breach+ always martial, Third mostly martial; redraw unresolved profiles by migration; canon untouched). Then gap 4b, gap 5, culture leftovers (faith, succession customs, fame).

## Status 2026-10-22 (deployed, server at a058502)
- Gap 4b, travel fix, act rework (free `operation`, partial results not refusals) and gap 5 (veto-based `author`, `create_protagonist`, household means/staff, migration 115) are live. Opus review of act rework + gap 5 done; its five Important findings and the minors fixed (de9cdc1, 5893442, a058502).
- Ansel given a fresh lived past on the server (backup `ansel.pre-livedpast-20261022T122628Z.db`; second run adds nothing).
- Not done: tests/new_character_acceptance_test.py; full suite not run. Act leftovers: named ops on absent people, presence mismatch (audit #27), partial trade price; hireling pay vanishes where a place has no households.
- Next: owner phone playtest; then culture leftovers (faith, succession customs, fame) and gap 6 (currency/wages canon).
