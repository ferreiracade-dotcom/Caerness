# AGENTS.md — start here

Read this first if you are an agent (or human) picking up Caerness. It says what the project is, where work stands, the rules the owner has set, how to run things, and what comes next. It is kept current; `README.md` is the long engine handoff and the many `*_ACCEPTANCE*.md`, `AUDIT_*`, `HANDOFF_*` and `POST_*_ROADMAP` files in the root are **historical evidence**: they do not override this file or README.

## 1. What Caerness is

A persistent low-fantasy world simulation (a murim-style martial world plus Western-style kingdoms) with a narrative camera inside it. **The world exists and changes without the player; the player is the camera, not the centre of causality.** The owner wants to be able to play as a cultivator, a noble rebuilding a county, a soldier or general, a merchant/collector, or an underworld boss. All of those must work on one simulated world.

- Engine: Python + SQLite (`engine/`), schema migrations in `engine/db.py` (`SCHEMA_VERSION`), schema in `engine/schema.sql` (re-applied idempotently by `init_db`, so new `IF NOT EXISTS` indexes reach old saves).
- Canon: `canon/world_bible_current.docx` (the World Bible) and seeds in `canon/` and `game/seeds/`.
- Packaged opening world: `data/caerness.db` (schema 108, story day 0, 132 travel routes).
- Design: `DESIGN.md`. Specs and plans for current work: `docs/superpowers/specs/`, `docs/superpowers/plans/`.

## 2. Where work stands (2026-10-13)

**Current product direction:** a rich AI narrative RPG, primarily in a desktop/laptop browser, with the same responsive client usable on mobile. Capable model reasoning, prose and characters take priority over running inference on a particular device. 3D observation/Unreal is postponed indefinitely until text play is genuinely enjoyable.

**Feature stack:** PR #3 → #4 → #5 (`feat/narrative-runtime`) → desktop narrative work. Preserve the latest dependency fixes; do not start this work from master or merge/retarget automatically. The simulation remains Python/SQLite. PR #5 connects an OpenAI-compatible model, saves conversations and supports validated general planning; actual real-model gameplay remains an acceptance gate, not an established success. Current desktop specification: `docs/plans/2026-10-13-desktop-narrative.md`.

The simulation milestones below are historical status/performance evidence, not the immediate development sequence.

| Stream | State | Where |
|---|---|---|
| Schema 108: opening family history, named/child mortality, Veinborn & training realism, ROUTES-01 travel graph, conflict fixes | Done, 125/125 suite | `WORLDHIST01A_SCHEMA108_OPENING_HISTORY_MORTALITY_CULTIVATION_2026-09-23.md`, README §Schema 108 |
| **PERF-01**: long-run speed and save size for practical play | **In progress** (below) | `docs/superpowers/plans/2026-09-26-perf01-speed-and-storage.md` |
| **POP-01** Phase 0: phone runtime + benchmark tooling | Legacy tooling done; physical-phone performance unverified (not a desktop acceptance gate) | `docs/superpowers/plans/2026-09-26-pop01-phase0-phone-benchmark.md`, `ANDROID_ONEPLUS12.md` |
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
3. Re-measure on the actual desktop deployment and run the suite. A physical-phone benchmark is optional compatibility evidence, not a gate for desktop play.

These PERF/POP next steps are deferred behind the playable narrative milestone. Phone benchmarks and population work are not prerequisites for desktop play. Do not expand or refactor simulation in the desktop task.

## 3. Owner's rules (binding)

- **World Bible plausibility beats real-world realism.** The World Bible is the current truth, not immutable: change a canon figure only when it is clearly the cause of a problem, and record it.
- **Text wins over the continental map** in every case; the embedded map is very old and only places things the text leaves open (`working_placement`).
- **Campaign authoring freedom (owner clarification, PR #7, 13 October 2026):** the World Bible/opening seed are foundations, not exhaustive inventories. Absence is not contradiction. Compatible previously undescribed biographies, relationships, important people, institutions and circumstances may be invented and progressively crystallized into campaign truth. Ordinary expression/recollections need no approval ceremony; significant objective additions need consistency review and persistence before future reliance. Preserve hard canon, established history, independent development and domain validation of actions. No prior named/latent seed entry is universally required. Deterministic opening resolution remains a separate bootstrap process, not a ban on campaign creativity. See `docs/narrative-authoring.md`.
- Model circumstances by **actual means and access**, never by a group label (not all underworld or remote people are poor).
- No recognized same-sex household unions (judged too common/unaccepted); Veinborn ≠ cultivator; aptitudes are bell-shaped; groups marry at different, canon-grounded rates.
- **Named characters get no special treatment**: same rules at every tier (POP-01).
- **Desktop-first, mobile-compatible, free local narrative play**: one browser client and authoritative Python/SQLite engine. Default to Ollama through the existing OpenAI-compatible gateway; support LM Studio for comparison. No mandatory cloud inference, subscription, API key or token charges. Detect RAM/GPU/dedicated VRAM, explain model sizes and obtain explicit permission before downloads. Recommend hardware-sized candidates, never claim a model is best without genuine gameplay evidence. No OnePlus, CPU-only or 3–4B requirement. Measure model latency separately from simulation time. Keep settings and diagnostics out of the main story.
- **Institutional presence matters:** portray organisations, developed followers, captains and subordinate contingents, colours, fortresses and assemblies through established or compatibly authored campaign truth. Ownership and independent development can matter without a battle/reward. Narrative authorship may introduce significant institutions and history, but cannot grant player loyalty, troops, equipment, command or completed undertakings without appropriate domain validation. Do not add request-specific handlers. See `docs/narrative-authoring.md` and `docs/plans/2026-10-13-loyal-forces-narrative-acceptance.md`.
- Don't trust README/acceptance claims: verify with data. Systems that "never happen" are usually silently disconnected (check graph reachability, join keys, endpoints) before tuning rates.
- Commit and push when the owner asks; use branches for feature work.

## 4. How to run things

PC interpreter used so far: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe"` (Python 3.13; numpy required). Always simulate on a **copy**: the engine writes to `CAERNESS_DB_PATH`.

| Task | Command |
|---|---|
| Windows play | Double-click `Play Caerness.cmd`; see `WINDOWS_PLAY.md` |
| Browser play | `python tools/narrative_play.py --local --open-browser` (separate campaign save; consent before downloads) |
| Full isolated regression suite | `python tools/run_suite.py --out runs/suite` then `git restore game/campaign_01/model_requests/` (tests rewrite those files) |
| One test | `CAERNESS_DB_PATH=/tmp/x.db PYTHONPATH=. python tests/<name>.py` |
| Multi-year run with speed and size per checkpoint | `python tools/run_years.py --days 1095 --out runs/<name>` |
| Engine benchmark (1/7/90-day segments on copies) | `python tools/bench_sim.py --label pc [--db SAVE]` |
| Profile N days | `python tools/profile_days.py SAVE.db 30` |
| Which tables grew | `python tools/table_growth.py LATE.db data/caerness.db` |
| Phone zip | `python tools/package_phone.py` (→ `dist/caerness_phone.zip`; also attached to the GitHub release) |

`runs/`, `dist/`, `__pycache__/`, `*.db-wal/-shm` are git-ignored. Benchmark JSON results are committed in `benchmarks/results/`.

## 5. Canon facts that drive calibration

- Global staged headcounts: First ~1.65M, Temper ~350k, Third ~45k, Breach ~4k, Fifth ~350, Sixth ~40. **Hearth**: ~330k / 122.5k / 24.75k / 2.8k / 300 / 38. Outside the Hearth the social offset applies (outer professional backbone = First; mature backbone = Temper; local master = Third).
- Canon's 40 Sixths: median age ~88, oldest 119; typical attainment early-to-mid 60s; Blake Merrin (34) is the prodigy outlier. A stable 40 needs ~7–9 new Sixths a decade; POP-01 makes rarity live in the *depth* of Sixth (Peak Sixths ~3–6 alive) and lets the summit have eras.
- Murim genre references the owner uses: Absolute Regression, Absolute Sword Sense, Chronicles of the Demon Faction, Heavenly Demon Cultivation Simulation, Murim Psychopath, Nano Machine, Reborn as the Heavenly Demon, Reincarnation of the Fist King, Return of the Mount Hua Sect, Surviving as a Genius on Borrowed Time, Myst Might Mayhem. Caerness deliberately rejects genre reverse-ageing in looks; the planned ladder renews the Vessel instead (Breach stasis, Fifth partial, Sixth full renewal; fertility unaffected).
