# AGENTS.md — start here

Read this first if you are an agent (or human) picking up Caerness. It says what the project is, where work stands, the rules the owner has set, how to run things, and what comes next. It is kept current; `README.md` is the long engine handoff and the many `*_ACCEPTANCE*.md`, `AUDIT_*`, `HANDOFF_*` and `POST_*_ROADMAP` files in the root are **historical evidence**: they do not override this file or README.

## 1. What Caerness is

A persistent low-fantasy world simulation (a murim-style martial world plus Western-style kingdoms) with a narrative camera inside it. **The world exists and changes without the player; the player is the camera, not the centre of causality.** The owner wants to be able to play as a cultivator, a noble rebuilding a county, a soldier or general, a merchant/collector, or an underworld boss. All of those must work on one simulated world.

- Engine: Python + SQLite (`engine/`), schema migrations in `engine/db.py` (`SCHEMA_VERSION`), schema in `engine/schema.sql` (re-applied idempotently by `init_db`, so new `IF NOT EXISTS` indexes reach old saves).
- Canon: `canon/world_bible_current.docx` (the World Bible) and seeds in `canon/` and `game/seeds/`.
- Packaged opening world: `data/caerness.db` (schema 115, story day 0, 132 travel routes; households quantified and staffed, gap 5).
- Design: `DESIGN.md`. Specs and plans for current work: `docs/superpowers/specs/`, `docs/superpowers/plans/`.

## 2. Where work stands

### Current direction (2026-10-16): play through Claude

The owner now plays **only through the Claude apps (desktop and phone, Claude Pro) via a custom connector hosted on an Oracle Cloud Always Free VM; stdio on the PC remains for development**. Claude is the game master and prose; the engine is memory, plausibility and the living world. Requirements: `D:\Theology\Caerness_Agreed_Narrative_Design_Baseline_2026-10-16.md` (16 agreed areas) and `D:\Theology\Caerness_Repository_Audit_2026-10-16.md`.

- **Active branch:** `feat/claude-connector` (from `master`).
- **Design (approved):** `docs/superpowers/specs/2026-10-16-claude-connector-design.md`.
- **Next work:** `docs/superpowers/plans/2026-10-16-claude-connector-step1.md` (connector + first playable scene), then `docs/superpowers/plans/2026-10-16-remote-connector-oracle.md` (remote hosting on Oracle Cloud Always Free, OAuth login, backups).
- The Codex `feat/*` branches and `master`'s old player/narration layer are a **parts bin**, not a base. The engine does not model minute mechanics: Claude supplies understanding, the engine remembers and enforces what has consequences. No bespoke per-activity verbs.
- PERF-01 and POP-01 below continue but are no longer the priority; phone numbers matter only for how long time skips take.

**Latest (2026-10-16, end of day):** step 1 and the remote connector are live; owner playtests found gaps. Next agent: read `docs/superpowers/plans/2026-10-16-connector-handoff.md` first.

**New stream (2026-10-23): world packages and Saint Jude.** Branch `feat/world-packages-bellacorte`. The engine becomes world-agnostic and gains a second world, Saint Jude, a 1980s mob city. Design approved: `docs/superpowers/specs/2026-10-23-bellacorte-living-city-design.md`. Next agent: read `docs/superpowers/plans/2026-10-23-saint-jude-handoff.md` first, then plan project 1.

**Saint Jude bible reload (2026-10-24):** the package follows the new bible (Index + Parts I-VI, `worlds/saintjude/bible.md`); state, E-item answers and bible problems are in `docs/superpowers/plans/saintjude-bible-reload/` (`HANDOFF_2.md`, then the report). Packaged opening: `data/saintjude.db` (build with `python tools/build_opening.py --package saintjude`; a new connector campaign takes `CAERNESS_WORLD_PACKAGE`). Measured on the PC: opening 2.6 s, 30-day advance 0.1 s, 1 Jan 1975 to 1 Jan 1980 18.9 s, DB 5.8 MB (9.2 MB in 1980). The opening holds the 51 seeded Example persons and 83 institutions and no unnamed people (the bible invents Open people when needed: Part I 0.1, Part II 10). `tools/leak_scan.py DB` checks a Saint Jude database for Caerness and old-codex vocabulary.

### Earlier streams (2026-10-09)

Branches: **`master` is current.** `worldhist01a-stage1` and `pop01-phase0` are the feature branches it was fast-forwarded from (kept for history).

| Stream | State | Where |
|---|---|---|
| Schema 108: opening family history, named/child mortality, Veinborn & training realism, ROUTES-01 travel graph, conflict fixes | Done, 125/125 suite | `WORLDHIST01A_SCHEMA108_OPENING_HISTORY_MORTALITY_CULTIVATION_2026-09-23.md`, README §Schema 108 |
| **PERF-01**: long-run speed and save size so the game can live on a phone | **In progress** (below) | `docs/superpowers/plans/2026-09-26-perf01-speed-and-storage.md` |
| **POP-01** Phase 0: phone runtime + benchmark tooling | Tooling done; **phone run not done** (owner will not install until PERF-01 targets are met) | `docs/superpowers/plans/2026-09-26-pop01-phase0-phone-benchmark.md`, `ANDROID_ONEPLUS12.md` |
| **POP-01** population tiers (background → notable → named, weighted simulants, promotion by distinction/significance/relevance, summit renewal ladder, Sixth depth bands) | Designed and approved; not started | `docs/superpowers/specs/2026-09-26-population-tiers-design.md` |

### PERF-01 numbers (PC, `tools/bench_sim.py` / `tools/run_years.py`)

| Measure | Before | Now | Target |
|---|---|---|---|
| A 90-day season from a year-3 save | ~45 s (453 s from a year-7.6 save) | ~33–37 s | ≤ 20 s on PC (phone assumed 2–4× slower; target ~1 min there) |
| Save growth | ~95 MB/year | ~20 MB in year 3, falling | ≤ 15 MB/year |

Done (each test-covered; behaviour-preserving changes verified identical): belief lookups claim-first; presence snapshots via indexed lookups; shared rumour evidence; revisions only on change; write-only link tables no longer written; **memory fading** (people forget minor unrepeated rumours; player, the people an event touched and their kin, and severity 4–5 events are never forgotten; the world's history is never deleted); **news fading** (rumours that stopped moving stop circulating); audit trails keep one year; slim decision-context snapshot.

Next for PERF-01:
1. Batch rumour exposure per place/day (rumour spreading is ~40% of run time). Verify with the 60-day fingerprint method (hash of exposures/knowledge/beliefs/rumour_locations before vs after must be identical).
2. Stop storing each hearer's copy of rumour text in the legacy `knowledge.belief_text` (7 MB, only ~800 distinct texts); touches 7 modules.
3. Re-measure 3 years (`tools/run_years.py`), run the suite, then ask the owner to run the phone benchmark (`ANDROID_ONEPLUS12.md` §1, §2, §11).

Then POP-01 plans 2–4 (background store + life rules; cultivation + renewal ladder + Sixth depth; tiers + migration) — write each plan from the spec after phone numbers exist.

## 3. Owner's rules (binding)

- **World Bible plausibility beats real-world realism.** The World Bible is the current truth, not immutable: change a canon figure only when it is clearly the cause of a problem, and record it.
- **Text wins over the continental map** in every case; the embedded map is very old and only places things the text leaves open (`working_placement`).
- **Opening resolution is not run-time invention** (DESIGN §15.1). Canon null means unknown: the opening world gets lived history once, deterministically. During a run, nothing is invented on demand; latent means previously undescribed.
- Model circumstances by **actual means and access**, never by a group label (not all underworld or remote people are poor).
- No recognized same-sex household unions (judged too common/unaccepted); Veinborn ≠ cultivator; aptitudes are bell-shaped; groups marry at different, canon-grounded rates.
- **Named characters get no special treatment**: same rules at every tier (POP-01).
- **Interface (2026-10-16): the Claude apps (desktop and phone, Claude Pro) via a custom connector hosted on an Oracle Cloud Always Free VM; stdio on the PC remains for development** (the earlier phone-only/local-model target is superseded). No 20–30 minute waits. Never end narration on a bare "continue" when nothing needs the player.
- Don't trust README/acceptance claims: verify with data. Systems that "never happen" are usually silently disconnected (check graph reachability, join keys, endpoints) before tuning rates.
- Commit and push when the owner asks; use branches for feature work.

## 4. How to run things

PC interpreter used so far: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe"` (Python 3.13; numpy required). Always simulate on a **copy**: the engine writes to `CAERNESS_DB_PATH`.

| Task | Command |
|---|---|
| Full isolated regression suite | `python tools/run_suite.py --out runs/suite` then `git restore game/campaign_01/model_requests/` (tests rewrite those files) |
| One test | `CAERNESS_DB_PATH=/tmp/x.db PYTHONPATH=. python tests/<name>.py` |
| Multi-year run with speed and size per checkpoint | `python tools/run_years.py --days 1095 --out runs/<name>` |
| Engine benchmark (1/7/90-day segments on copies) | `python tools/bench_sim.py --label pc [--db SAVE]` |
| Profile N days | `python tools/profile_days.py SAVE.db 30` |
| Which tables grew | `python tools/table_growth.py LATE.db data/caerness.db` |
| Update the remote connector (on the VM) | `sudo /opt/caerness/deploy/update.sh` (runbook: `connector/README.md` "Remote hosting") |
| Restore a connector backup (on the VM) | stop `caerness`; `python -m connector.import_campaign <snapshot> --campaign NAME --replace`; start `caerness` |
| Export a campaign for the VM (laptop) | `python tools/export_campaign.py --campaign NAME --out FILE.db` |
| Phone zip | `python tools/package_phone.py` (→ `dist/caerness_phone.zip`; also attached to the GitHub release) |

`runs/`, `dist/`, `__pycache__/`, `*.db-wal/-shm` are git-ignored. Benchmark JSON results are committed in `benchmarks/results/`.

## 5. Canon facts that drive calibration

- Global staged headcounts: First ~1.65M, Temper ~350k, Third ~45k, Breach ~4k, Fifth ~350, Sixth ~40. **Hearth**: ~330k / 122.5k / 24.75k / 2.8k / 300 / 38. Outside the Hearth the social offset applies (outer professional backbone = First; mature backbone = Temper; local master = Third).
- Canon's 40 Sixths: median age ~88, oldest 119; typical attainment early-to-mid 60s; Blake Merrin (34) is the prodigy outlier. A stable 40 needs ~7–9 new Sixths a decade; POP-01 makes rarity live in the *depth* of Sixth (Peak Sixths ~3–6 alive) and lets the summit have eras.
- Murim genre references the owner uses: Absolute Regression, Absolute Sword Sense, Chronicles of the Demon Faction, Heavenly Demon Cultivation Simulation, Murim Psychopath, Nano Machine, Reborn as the Heavenly Demon, Reincarnation of the Fist King, Return of the Mount Hua Sect, Surviving as a Genius on Borrowed Time, Myst Might Mayhem. Caerness deliberately rejects genre reverse-ageing in looks; the planned ladder renews the Vessel instead (Breach stasis, Fifth partial, Sixth full renewal; fertility unaffected).

**Gap 5 (2026-10-18):** new protagonists are proposed whole to `author` kind=protagonist and only vetoed (`engine/veto.py`, `engine/new_character.py`, `worlds/caerness/creation_section.md`); `author` is free text with scaling instead of caps; schema 115 quantifies and staffs every household (`engine/household_staff.py`); `tools/give_lived_past.py` repairs an existing protagonist (run on the server after deploying 115, `--apply` backs up first). Not done: `tests/new_character_acceptance_test.py`.
