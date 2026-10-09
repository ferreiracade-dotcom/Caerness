# AGENTS.md — start here

Read this first if you are an agent (or human) picking up Caerness. It says what the project is, where work stands, the rules the owner has set, how to run things, and what comes next. It is kept current; `README.md` is the long engine handoff and the many `*_ACCEPTANCE*.md`, `AUDIT_*`, `HANDOFF_*` and `POST_*_ROADMAP` files in the root are **historical evidence**: they do not override this file or README.

## 1. What Caerness is

A persistent low-fantasy world simulation (a murim-style martial world plus Western-style kingdoms) with a narrative camera inside it. **The world exists and changes without the player; the player is the camera, not the centre of causality.** The owner wants to be able to play as a cultivator, a noble rebuilding a county, a soldier or general, a merchant/collector, or an underworld boss. All of those must work on one simulated world.

- Engine: Python + SQLite (`engine/`), schema migrations in `engine/db.py` (`SCHEMA_VERSION`), schema in `engine/schema.sql` (re-applied idempotently by `init_db`, so new `IF NOT EXISTS` indexes reach old saves).
- Canon: `canon/world_bible_current.docx` (the World Bible) and seeds in `canon/` and `game/seeds/`.
- Packaged opening world: `data/caerness.db` (schema 108, story day 0, 132 travel routes).
- Design: `DESIGN.md`. Specs and plans for current work: `docs/superpowers/specs/`, `docs/superpowers/plans/`.

## 2. Where work stands (2026-10-09)

Branches: **`master` is current.** `worldhist01a-stage1` and `pop01-phase0` are the feature branches it was fast-forwarded from (kept for history).

| Stream | State | Where |
|---|---|---|
| Schema 108: opening family history, named/child mortality, Veinborn & training realism, ROUTES-01 travel graph, conflict fixes | Done, 125/125 suite | `WORLDHIST01A_SCHEMA108_OPENING_HISTORY_MORTALITY_CULTIVATION_2026-09-23.md`, README §Schema 108 |
| **PERF-01**: long-run speed and save size so the game can live on a phone | **In progress** (below) | `docs/superpowers/plans/2026-09-26-perf01-speed-and-storage.md` |
| **POP-01** Phase 0: phone runtime + benchmark tooling | Tooling done; **phone run not done** (owner will not install until PERF-01 targets are met) | `docs/superpowers/plans/2026-09-26-pop01-phase0-phone-benchmark.md`, `ANDROID_ONEPLUS12.md` |
| **POP-01** population tiers (background → notable → named, weighted simulants, promotion by distinction/significance/relevance, summit renewal ladder, Sixth depth bands) | Designed and approved; not started | `docs/superpowers/specs/2026-09-26-population-tiers-design.md` |
| **Story layer** (SPEECH-01 intent-grounded NPC speech, SIFT-01 story sifting, RUMOUR-02 false/garbled rumours, DEAL-01 goal-valued bargaining) and an audit of earlier external-code adoptions | Proposed; awaiting owner review; not started | `docs/superpowers/specs/2026-10-09-story-layer-design.md`, `docs/research/2026-10-09-story-layer-sources-and-adoption-audit.md` |

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

> Since 2026-10-09 the target is laptop first. PERF-01 still matters there (late-game slowdown grows with save age, not just device speed), but its targets and the "after phone numbers exist" gate above should be re-set against laptop numbers. That decision is the owner's.

## 3. Owner's rules (binding)

- **World Bible plausibility beats real-world realism.** The World Bible is the current truth, not immutable: change a canon figure only when it is clearly the cause of a problem, and record it.
- **Text wins over the continental map** in every case; the embedded map is very old and only places things the text leaves open (`working_placement`).
- **Opening resolution is not run-time invention** (DESIGN §15.1). Canon null means unknown: the opening world gets lived history once, deterministically. During a run, no person, tie or event is conjured because a scene or system wants one; latent means previously undescribed. Undescribed *details* are different: resolve them when play first needs them, plausibly and consistent with canon and state, then record them and never contradict them (DESIGN §15.1, "Resolution on first look").
- Model circumstances by **actual means and access**, never by a group label (not all underworld or remote people are poor).
- No recognized same-sex household unions (judged too common/unaccepted); Veinborn ≠ cultivator; aptitudes are bell-shaped; groups marry at different, canon-grounded rates.
- **Named characters get no special treatment**: same rules at every tier (POP-01).
- **Laptop first, phone later** (owner decision 2026-10-09, replacing "phone-only"): build the best version for the owner's laptop, then scale it down for the phone (OnePlus 12, 12 GB, CPU, local 3–4B model). Scaling down should mean turning dials (how many people are simulated individually, model size, context size), not separate code, so keep phone limits in mind when designing. Quality over speed, but no 20–30 minute waits on either. Never end a narration node on a bare "continue" when nothing needs the player.
- **Prefer what a person in the world would plausibly do over a player setting** (owner, 2026-10-09). Example: a character reads a letter when it reaches them and answers it as they plausibly would; time stops for the player only when a real decision is needed, not because of an interruption preference.
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
| Phone zip | `python tools/package_phone.py` (→ `dist/caerness_phone.zip`; also attached to the GitHub release) |

`runs/`, `dist/`, `__pycache__/`, `*.db-wal/-shm` are git-ignored. Benchmark JSON results are committed in `benchmarks/results/`.

## 5. Canon facts that drive calibration

- Global staged headcounts: First ~1.65M, Temper ~350k, Third ~45k, Breach ~4k, Fifth ~350, Sixth ~40. **Hearth**: ~330k / 122.5k / 24.75k / 2.8k / 300 / 38. Outside the Hearth the social offset applies (outer professional backbone = First; mature backbone = Temper; local master = Third).
- Canon's 40 Sixths: median age ~88, oldest 119; typical attainment early-to-mid 60s; Blake Merrin (34) is the prodigy outlier. A stable 40 needs ~7–9 new Sixths a decade; POP-01 makes rarity live in the *depth* of Sixth (Peak Sixths ~3–6 alive) and lets the summit have eras.
- Murim genre references the owner uses: Absolute Regression, Absolute Sword Sense, Chronicles of the Demon Faction, Heavenly Demon Cultivation Simulation, Murim Psychopath, Nano Machine, Reborn as the Heavenly Demon, Reincarnation of the Fist King, Return of the Mount Hua Sect, Surviving as a Genius on Borrowed Time, Myst Might Mayhem. Caerness deliberately rejects genre reverse-ageing in looks; the planned ladder renews the Vessel instead (Breach stasis, Fifth partial, Sixth full renewal; fertility unaffected).
