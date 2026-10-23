# Handoff: Saint Jude world packages (plan, then implement)

**Written:** 2026-10-23. **Branch:** `feat/world-packages-bellacorte` (from `feat/claude-connector`; not pushed).
**Design (approved, committed `e7c1eb0`):** `docs/superpowers/specs/2026-10-23-bellacorte-living-city-design.md`. Read it in full first; this handoff only adds context the design doesn't carry.

## 1. What you are taking over

The owner wants the engine to work with any world, and a new world, **Saint Jude**, built as a living 1980s mob city. The design is done and the owner asked for the work to go ahead: write the implementation plan, then implement. The design has three projects in order (§12):

1. **World packages**: engine and connector read the world from a package; Caerness content moves into a Caerness package; build the Saint Jude package and its 1975 starting snapshot. Ends with a Saint Jude opening with no Caerness leaks, playable through the connector with existing generic systems.
2. **The living city**: POP-01 for Saint Jude, rising, ambitions, the new mafia system, everyone acting, money.
3. **Stories**: per-story pre-history run, the summary for Claude, the opening, plausibility checks wired into `author`/`act`.

**Your next step:** use `superpowers:writing-plans` to write the plan for **project 1 only** (`docs/superpowers/plans/2026-10-23-world-packages-plan.md` or similar), get the owner's approval, then execute it (`superpowers:executing-plans` or `superpowers:subagent-driven-development`, test-first per `superpowers:test-driven-development`). Projects 2 and 3 each get their own plan later; project 2 likely needs a short design pass of its own on POP-01 details first.

## 2. Names (settled late; the codex still uses the old ones)

| Codex says | Now |
|---|---|
| Bellacorte (the city) | **Saint Jude** (the city); Bellacorte is an old Italianate **district** |
| Port St. Jude | **Killbuck Point** ("down the Point") |
| Saint Jude's Meadowlands | **the Pines** |
| St. Jude's (Kerrytown) | unchanged; it is the founding church and now the **cathedral** |

The founding story is in design §3.15. The branch and spec filenames still say "bellacorte"; leave them. The package's internal id must not depend on display names.

## 3. Source material

- **The codex:** `D:\Theology\Bellacorte_Living_World_Codex_Flexible_Date_Final.docx` (about 21,000 words). It is Markdown typed into Word paragraphs, so it has **no real Word heading styles**: `engine/canon.py` indexes it as one "Document" section. Extract text with plain `zipfile` + regex over `word/document.xml` (`python-docx` is not installed). Structure: Edition control (flexible date rules); Layer 1 setting bible §1–6; Layer 2 storyteller rules §7–8; Layer 3 starting state §9–11 (families, rival orgs, ~40 named NPCs, three pressures); playbooks §12–13; street dictionary §14; Appendix A (1980 tech/legal timeline), B (1980 price ledger), C (simulation tests), D (sources).
- **The critique:** `D:\Theology\ChatGPT-Review Bellacorte Update-20261023-1016.md` (1,527 lines; earlier review at 723–1021, 1980 rebuild 1026–1331, flexible date 1333–1390, naming 1392–end). Its decisions are folded into design §3 and §10.
- **Known codex defects** to fix while adapting (design §14): garbled figures in §8.1 (sports book and numbers math), §8.2 (rank capital column), §12.2 item 4, §13.2 items 3 and 6, and the §11 Pressure 2 heading. Character ages are written for 1980; the snapshot is 1975 (design §6 lists what back-dating means).

## 4. Owner's rules for this work (binding)

- The codex is **changeable source material**, not canon. Adapt it to the engine; always keep plausibility.
- **Nothing hard-coded**: no fixed pressures or character secrets (Sally Glasses, Vinny Scales, the trial, the container, the clerk are examples at most). Claude invents pressures; the engine checks them.
- **Taboos have consequences**, they are never impossible.
- The engine remembers and vetoes only **named contradictions**; no closed lists or menus to Claude; the engine runs **no language model** (design §10).
- Caerness must keep working: its live campaign plays on the Oracle VM. The regression suite stays green.
- The owner steers framing; give recommendations, not surveys. Commit when the owner asks; branch for feature work; don't push unless asked.
- Repo-wide rules in `AGENTS.md` §3 still apply (e.g. verify with data, don't trust README claims).

## 5. What the throwaway test proved (2026-10-23)

A 15-person Saint Jude slice (Sabatini and Castellano families, FBI, 14th Precinct, Blum's office, 10 places) was loaded into a **scratch** database and run 37 days. The scripts lived in a session scratchpad that is gone; the method is reproducible:

```python
# env: CAERNESS_DB_PATH=<scratch .db>, PYTHONPATH=<repo>, cwd=<repo>
from engine.db import reset_db, init_db, connect
reset_db(force=True, backup=False); init_db(); conn = connect()
from engine.current_seed import import_current_seed      # takes a seed path
import_current_seed(conn, SEED_PATH); conn.commit()       # fails the bible-hash firewall unless forged
from engine.activation import activate_existing_loops; activate_existing_loops(conn); conn.commit()
from engine.simulation import advance_connection; advance_connection(conn, 30)
from engine.canon import index_canon; index_canon(DOCX_PATH, force=True)   # writes into the CAERNESS_DB_PATH db
from engine.player import set_player; from connector import views, lore, store
store.ensure_connector_schema(conn); set_player(conn, actor_id, campaign_name="x"); views.compact_scene(conn); lore.lore(conn, "query")
```

Seed format: see `game/seeds/Caerness_Initial_World_State_Seed_v1_4.json` and `engine/current_seed.py` (places, routes, institutions, persons with `age`/`birth_day`/`birth_date_sv`, relationships, households, cohorts, claims, processes, latent_population_controls). Persons need an SV-calendar `birth_date_sv` from `engine.civil_calendar.format_sv_date` — a coupling to remove.

Results: it loaded and ran without crashing; places, people, kinship, decisions, presence, health and `lore` (after indexing the codex) worked. Every Caerness leak found is listed in design §4 with its file. The quiet result matters too: in 37 days nothing family-, police- or FBI-driven happened; the only crime was by a generated Caerness-style gang. That fails the codex's own C4.6 autonomy test and is project 2's job, not project 1's.

## 6. Code map for project 1

| Concern | Where |
|---|---|
| Seed import, namespace, bible-hash firewall, SV dates, `stage`→longevity | `engine/current_seed.py` |
| DB init, world name "Caerness", default DB path | `engine/db.py` (`init_db`, `DEFAULT_DB_PATH`) |
| Opening activation (Houses, religions, goods, trade buckets, background people, day-0 spouses, underworld seeding) | `engine/activation.py` (`activate_existing_loops`) and what it calls |
| Background population (age/sex/alive only; premodern mortality) | `engine/background_population.py` |
| Calendar | `engine/civil_calendar.py` |
| Bible path and indexing (heading detection from Word styles) | `engine/canon.py` (`DEFAULT_CANON`, `index_canon`, `extract_docx_blocks`) |
| Business archetypes (pre-industrial) | `engine/business.py` `_ARCHETYPES` |
| Market goods, trade buckets | `engine/aggregate_trade.py` and activation |
| Underworld (Caerness model, to be switched off for Saint Jude) | `engine/underworld_*.py` (`underworld_canon.py` holds Caerness data) |
| Cultivation and related (off for Saint Jude) | `engine/cultivation.py`, `elixir.py`, `hollow.py`, `groundbinding.py`; Stage use in `temperament.py`, `person_ecology.py`, `veto.py`, `authoring.py`, `new_character.py` |
| Campaign creation from the packaged DB | `connector/campaign.py` (`PACKAGED_DB`), `connector/setup_campaign.py`, `connector/store.py` |
| GM prompts (world text to split into shared core + per-world section) | `connector/rulebook.md`, `connector/creation.md` |
| Scene view (SV dates, "martial standing" etiquette) | `connector/views.py` |
| Lore tool | `connector/lore.py` |
| Old loader (legacy, Stage tables) | `engine/bootstrap.py`, `canon/core_seed_v3.json` |
| CLI entry points (`current-canon-bootstrap`, `campaign-bootstrap`) | `run.py` |
| Packaged Caerness opening | `data/caerness.db` (schema 115) |

Reusable generic pieces the design keeps: `engine/ledger.py` (money between holders), `payroll.py`, relationships, loyalty, knowledge/rumour/belief, `health.py`, `decision_runtime.py`, `resolution_controller.py`, `crystallization.py` (latent → named; generic despite the name).

## 7. Runbook

- Windows, PowerShell primary; Git Bash also available. Python: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe"` (numpy installed; python-docx not).
- **Always simulate on a copy**: the engine writes to `CAERNESS_DB_PATH`. Never point it at `data/caerness.db` or a live campaign.
- One-line `python -c` with embedded SQL quotes breaks under PowerShell: write a script file and run it. Use `-I` for ad hoc scripts that read untrusted files.
- Full suite: `python tools/run_suite.py --out runs/suite`, then `git restore game/campaign_01/model_requests/`. One test: `CAERNESS_DB_PATH=/tmp/x.db PYTHONPATH=. python tests/<name>.py`.
- The `caerness` MCP tools (`resume`, `scene`, `act`, `author`, `lore`, …) are the owner's live game; do not call them for development.
- Untracked files in the repo root (`.claude/`, `data/caerness.pre-schema110.db`, `game/campaign_01/backups/`) are not yours; leave them.

## 8. Open items the plan must carry

- The 1975 back-dating of the codex (design §6) is an authoring task with judgement calls; the owner reviews the resulting snapshot.
- Project 1 must not break Caerness: a Caerness campaign created after the change must match one created before (same seed → same opening), and the live campaign keeps working.
- Speed targets are unset; measure a Saint Jude opening and a 30-day advance on the server profile and record them.
