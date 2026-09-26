# POP-01 Phase 0: Phone Runtime and Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get Caerness running on the user's OnePlus 12 and measure how fast it simulates, so POP-01's tier budgets (`k`, simulant count, significance ranks) are set from real phone numbers instead of guesses.

**Architecture:** There are four standalone tools under `tools/`:
- `bench_sim.py` times the full engine advancing a fresh copy of the packaged opening by a day, a week and a season. Each segment runs in its own subprocess.
- `bench_simulants.py` times a numpy prototype of the POP-01 weighted-simulant step (deaths, breakthrough splits, merges, conservation) at several simulant counts.
- `derive_budgets.py` turns both results into a simulant budget against the spec's season target.
- `package_phone.py` builds a single zip to copy to the phone.

The user runs the tools on the phone under Termux and brings the result JSON files back.

**Tech Stack:** Python 3.12+ standard library, numpy and sqlite3 only (what Termux provides as `python` and `python-numpy`). Tests are plain scripts in `tests/`, the repo convention.

**Spec:** `docs/superpowers/specs/2026-09-26-population-tiers-design.md`, §8 (Phone).

## Global Constraints

- Target device: OnePlus 12, 12 GB, running the simulation on CPU with a local 3–4B model loaded alongside. The game is phone-only.
- Spec §8 targets:

| World time | Target wait |
|---|---|
| A scene turn | under 1 s |
| A day | 1–2 s |
| A week | about 10 s |
| A season (90 days) | about 1 minute |
| A year | about 4 minutes, in season-sized segments |

- No new dependencies beyond the standard library, numpy and sqlite3.
- Never open `data/caerness.db` in place for a simulation. Always work on a copy, because `run.py` and the engine write to the configured DB.
- Point the engine at a DB with the environment variables `CAERNESS_DB_PATH` and `CAERNESS_BACKUP_DIR`. The engine reads them at call time (`engine/db.py:34` `database_path()`).
- The PC interpreter is `"$LOCALAPPDATA/Programs/Python/Python313/python.exe"`. Run tests with `PYTHONPATH=D:/Code/Caerness`.
- Tests follow the repo convention: a script with `run()` and `if __name__ == '__main__': run()`, printing `... PASS` and raising `AssertionError` on failure.
- **Commits:** the user commits only when they ask. Each task ends with a checkpoint that stages the files. Commit only if the user has approved commits for this work.
- Benchmark results live in `benchmarks/results/`, one JSON per device and label.

---

### Task 1: Full-engine benchmark (`tools/bench_sim.py`)

**Files:**
- Create: `tools/bench_sim.py`
- Test: `tests/bench_sim_smoke_test.py`
- Output (PC baseline): `benchmarks/results/pc_engine.json`

**Interfaces:**
- Consumes: `engine.db.init_db`, `engine.db.connect`, `engine.simulation.advance_connection(conn, days)`, `engine.simulation.current_day(conn)`.
- Produces: the CLI `python tools/bench_sim.py [--db PATH] [--out PATH] [--label STR] [--segments 1,7,90]`, which writes JSON shaped as `{"label": str, "device": {...}, "segments": [{"days": int, "wall_secs": float, "secs_per_day": float, "day_reached": int, "peak_rss_mb": float|None}]}`. Task 3 reads `segments[].days` and `segments[].wall_secs`.

- [ ] **Step 1: Write the failing test**

```python
"""bench_sim: the full-engine phone benchmark runs a segment on a copy and reports timings."""
from __future__ import annotations
import json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent


def run():
    out = Path(tempfile.gettempdir()) / f"bench_sim_smoke_{os.getpid()}.json"
    out.unlink(missing_ok=True)
    before = (ROOT / "data" / "caerness.db").stat().st_mtime
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "bench_sim.py"), "--segments", "1",
                        "--out", str(out), "--label", "smoke"], cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stderr[-2000:]
    data = json.loads(out.read_text())
    assert data["label"] == "smoke"
    for key in ("platform", "python", "numpy", "sqlite", "cpu_count"):
        assert key in data["device"], key
    seg = data["segments"][0]
    assert seg["days"] == 1 and seg["day_reached"] == 1, seg
    assert seg["wall_secs"] > 0 and abs(seg["secs_per_day"] - seg["wall_secs"]) < 1e-9, seg
    # The packaged opening is never touched.
    assert (ROOT / "data" / "caerness.db").stat().st_mtime == before
    out.unlink(missing_ok=True)
    print("bench_sim smoke PASS", seg)


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PYTHONPATH=D:/Code/Caerness "$LOCALAPPDATA/Programs/Python/Python313/python.exe" tests/bench_sim_smoke_test.py`
Expected: FAIL with `AssertionError`, because `tools/bench_sim.py` does not exist and the subprocess returns non-zero.

- [ ] **Step 3: Write the implementation**

```python
"""Full-engine phone benchmark: how long Caerness takes to advance the packaged opening.

Usage:
  python tools/bench_sim.py [--db data/caerness.db] [--out benchmarks/results/<label>_engine.json]
                            [--label pc] [--segments 1,7,90]

Each segment runs in its own subprocess on a fresh copy of the opening, so segments are independent and
peak memory is per segment.  The source DB is only ever copied, never opened.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def peak_rss_mb() -> float | None:
    try:
        import resource
    except ImportError:  # Windows
        return None
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(v / (1048576 if sys.platform == "darwin" else 1024), 1)


def device_info() -> dict:
    import numpy
    return {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
            "numpy": numpy.__version__, "sqlite": sqlite3.sqlite_version, "cpu_count": os.cpu_count()}


def child(db: Path, days: int) -> None:
    os.environ["CAERNESS_DB_PATH"] = str(db)
    os.environ["CAERNESS_BACKUP_DIR"] = str(db.parent / "backups")
    sys.path.insert(0, str(ROOT))
    from engine.db import connect, init_db
    from engine.simulation import advance_connection, current_day
    init_db()
    conn = connect()
    start = current_day(conn)
    t0 = time.perf_counter()
    advance_connection(conn, days)
    conn.commit()
    wall = time.perf_counter() - t0
    reached = current_day(conn)
    conn.close()
    print(json.dumps({"days": days, "wall_secs": round(wall, 3), "secs_per_day": round(wall / days, 3),
                      "day_reached": reached - start, "peak_rss_mb": peak_rss_mb()}))


def run_segment(src: Path, days: int, work: Path) -> dict:
    db = work / f"bench_{days}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    shutil.copy2(src, db)
    r = subprocess.run([sys.executable, __file__, "--child", str(db), str(days)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"segment {days} failed:\n{r.stderr[-3000:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        child(Path(sys.argv[2]), int(sys.argv[3]))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "caerness.db"))
    ap.add_argument("--label", default="device")
    ap.add_argument("--out", default=None)
    ap.add_argument("--segments", default="1,7,90")
    a = ap.parse_args()
    out = Path(a.out) if a.out else ROOT / "benchmarks" / "results" / f"{a.label}_engine.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = {"label": a.label, "device": device_info(), "segments": []}
    with tempfile.TemporaryDirectory(prefix="caerness_bench_") as tmp:
        for days in [int(x) for x in a.segments.split(",") if x.strip()]:
            seg = run_segment(Path(a.db), days, Path(tmp))
            result["segments"].append(seg)
            print(json.dumps(seg), flush=True)
    out.write_text(json.dumps(result, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `PYTHONPATH=D:/Code/Caerness "$LOCALAPPDATA/Programs/Python/Python313/python.exe" tests/bench_sim_smoke_test.py`
Expected: `bench_sim smoke PASS {'days': 1, ...}`

- [ ] **Step 5: Record the PC baseline**

Run (it takes a few minutes, since 90 days on PC is about 90 s): `"$LOCALAPPDATA/Programs/Python/Python313/python.exe" tools/bench_sim.py --label pc`
Expected: three JSON lines for 1, 7 and 90 days, then `wrote ...benchmarks/results/pc_engine.json`.

- [ ] **Step 6: Checkpoint**

```bash
git add tools/bench_sim.py tests/bench_sim_smoke_test.py benchmarks/results/pc_engine.json
```

Commit only if the user has approved commits: `git commit -m "pop01: full-engine phone benchmark"`.

---

### Task 2: Weighted-simulant step prototype benchmark (`tools/bench_simulants.py`)

This is a numpy prototype of the POP-01 background step. It measures the cost per simulant of the spec's operations and exercises conservation and the never-merge-individuals rule early. It is **not** the production store: plan 2 builds that. The prototype only has to be representative in cost.

**Files:**
- Create: `tools/bench_simulants.py`
- Test: `tests/bench_simulants_test.py`
- Output (PC baseline): `benchmarks/results/pc_simulants.json`

**Interfaces:**
- Produces:
  - `make_population(k: int, seed: int) -> dict[str, np.ndarray]`
  - `step(pop: dict, rng: np.random.Generator) -> dict` (mutates `pop`; returns `{"deaths": int, "splits": int, "merged": int}`)
  - `total(pop) -> int`
  - The CLI `python tools/bench_simulants.py [--sizes 50000,150000,300000,600000] [--steps 12] [--label pc] [--out PATH]`, which writes `{"label": str, "device": {...}, "runs": [{"k": int, "rows_end": int, "secs_per_step": float, "mb": float}]}`. Task 3 reads `runs[].k` and `runs[].secs_per_step`.

- [ ] **Step 1: Write the failing test**

```python
"""bench_simulants: the prototype step conserves people and never merges individuals."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import numpy as np
from bench_simulants import make_population, step, total


def run():
    pop = make_population(2000, seed=7)
    rng = np.random.default_rng(7)
    individuals_before = set(pop["uid"][pop["individual"] == 1].tolist())
    people = total(pop)
    deaths = splits = 0
    for _ in range(24):
        r = step(pop, rng)
        deaths += r["deaths"]; splits += r["splits"]
    # Conservation: nobody is created or lost except by death.
    assert total(pop) == people - deaths, (total(pop), people, deaths)
    # Splits happened, and weights stay positive.
    assert splits > 0 and (pop["weight"] > 0).all()
    # Individuals are never merged away: each surviving individual uid is still present exactly once.
    uids = pop["uid"][pop["individual"] == 1].tolist()
    assert len(uids) == len(set(uids))
    assert (pop["weight"][pop["individual"] == 1] == 1).all()
    # Opening individuals that survive keep their identity (none was absorbed into a group row).
    grouped_uids = set(pop["uid"][pop["individual"] == 0].tolist())
    assert not (individuals_before & grouped_uids)
    print("bench_simulants conservation PASS", {"people": people, "deaths": deaths, "splits": splits, "rows": len(pop["weight"])})


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PYTHONPATH=D:/Code/Caerness "$LOCALAPPDATA/Programs/Python/Python313/python.exe" tests/bench_simulants_test.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench_simulants'`

- [ ] **Step 3: Write the implementation**

```python
"""POP-01 weighted-simulant step prototype: cost per simulant of one 30-day background step.

Representative of the spec's background operations: age, deaths (binomial on weight), breakthrough
splits (binomial on weight -> new rows), Vessel growth, and merging indistinguishable grouped rows.
Individuals (weight 1, individual=1) never merge.  Not the production store.

Usage: python tools/bench_simulants.py [--sizes 50000,150000,300000,600000] [--steps 12] [--label pc] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
STAGES = 7            # 0 unstaged/closed, 1 First .. 6 Sixth
# Rough monthly death probability by stage (index) and age in years (0..199): ordinary Gompertz shape,
# pushed later for higher stages.  Only the cost matters here, not the calibration.
_AGES = np.arange(200)
_SHIFT = np.array([0, 3, 6, 9, 14, 22, 34])
MONTHLY_DEATH = np.stack([np.clip(0.0018 + 0.03 * 2.0 ** ((_AGES - 70 - s) / 7.3), 0, 1) / 12 for s in _SHIFT])
MONTHLY_UP = np.array([0.0, 0.012, 0.006, 0.0004, 0.0004, 0.0003, 0.0])
FIELDS = {"uid": np.int64, "weight": np.int64, "individual": np.int8, "age_days": np.int32, "sex": np.int8,
          "place": np.int16, "stage": np.int8, "occupation": np.int8, "rank": np.int8, "vessel": np.float32,
          "realization": np.float32, "apt_v": np.float32, "apt_r": np.float32, "wealth": np.float32}


def make_population(k: int, seed: int = 1) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    stage = rng.choice(STAGES, size=k, p=[0.60, 0.20, 0.12, 0.06, 0.015, 0.004, 0.001]).astype(np.int8)
    individual = (stage >= 3).astype(np.int8)
    weight = np.where(individual == 1, 1, rng.integers(5, 300, size=k))
    pop = {
        "uid": np.arange(k, dtype=np.int64), "weight": weight.astype(np.int64), "individual": individual,
        "age_days": (rng.uniform(0, 80, k) * 365).astype(np.int32), "sex": rng.integers(0, 2, k).astype(np.int8),
        "place": rng.integers(0, 68, k).astype(np.int16), "stage": stage,
        "occupation": rng.integers(0, 8, k).astype(np.int8), "rank": rng.integers(0, 5, k).astype(np.int8),
        "vessel": rng.uniform(20, 90, k).astype(np.float32), "realization": rng.uniform(10, 80, k).astype(np.float32),
        "apt_v": np.exp(rng.normal(-0.05, 0.34, k)).astype(np.float32), "apt_r": np.exp(rng.normal(0, 0.215, k)).astype(np.float32),
        "wealth": rng.lognormal(3, 1, k).astype(np.float32),
    }
    pop["_next_uid"] = np.array([k], dtype=np.int64)
    return pop


def total(pop: dict) -> int:
    return int(pop["weight"].sum())


def _keep(pop: dict, mask: np.ndarray) -> None:
    for f in FIELDS:
        pop[f] = pop[f][mask]


def step(pop: dict, rng: np.random.Generator) -> dict:
    pop["age_days"] += 30
    years = np.minimum(pop["age_days"] // 365, 199)
    # Deaths: binomial on each row's weight.
    deaths = rng.binomial(pop["weight"], MONTHLY_DEATH[pop["stage"], years])
    pop["weight"] -= deaths
    # Vessel growth for staged rows.
    staged = pop["stage"] > 0
    pop["vessel"][staged] = np.minimum(100, pop["vessel"][staged] + 0.9 * pop["apt_v"][staged])
    # Breakthroughs split off new rows carrying the next stage.
    p_up = MONTHLY_UP[pop["stage"]] * np.clip(pop["apt_r"], 0.5, 1.8)
    ups = rng.binomial(pop["weight"], p_up)
    src = np.flatnonzero(ups > 0)
    splits = int(src.size)
    if splits:
        pop["weight"][src] -= ups[src]
        new = {f: pop[f][src].copy() for f in FIELDS}
        new["weight"] = ups[src].astype(np.int64)
        new["stage"] = np.minimum(new["stage"] + 1, STAGES - 1).astype(np.int8)
        new["vessel"] = np.full(src.size, 30.0, dtype=np.float32)
        new["individual"] = ((new["stage"] >= 3) | (new["weight"] == 1)).astype(np.int8)
        n0 = int(pop["_next_uid"][0])
        new["uid"] = np.arange(n0, n0 + src.size, dtype=np.int64)
        pop["_next_uid"][0] = n0 + src.size
        # An individual who stood out becomes one row per person (weight 1).
        multi = (new["individual"] == 1) & (new["weight"] > 1)
        if multi.any():
            reps = np.where(multi, new["weight"], 1)
            for f in FIELDS:
                new[f] = np.repeat(new[f], reps)
            new["weight"] = np.where(np.repeat(multi, reps), 1, new["weight"]).astype(np.int64)
            n0 = int(pop["_next_uid"][0])
            new["uid"] = np.arange(n0, n0 + new["uid"].size, dtype=np.int64)
            pop["_next_uid"][0] = n0 + new["uid"].size
        for f in FIELDS:
            pop[f] = np.concatenate([pop[f], new[f]])
    _keep(pop, pop["weight"] > 0)
    # Merge grouped (non-individual) rows that have become indistinguishable.
    grouped = np.flatnonzero(pop["individual"] == 0)
    merged = 0
    if grouped.size:
        key = np.stack([pop["place"][grouped].astype(np.int64), pop["stage"][grouped], pop["occupation"][grouped],
                        pop["rank"][grouped], (pop["age_days"][grouped] // 1825).astype(np.int64),
                        (pop["vessel"][grouped] // 10).astype(np.int64), pop["sex"][grouped]], axis=1)
        _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        inv = inv.ravel()
        sums = np.bincount(inv, weights=pop["weight"][grouped]).astype(np.int64)
        merged = int(grouped.size - first.size)
        if merged:
            keep_rows = grouped[first]
            pop["weight"][grouped] = 0
            pop["weight"][keep_rows] = sums
            _keep(pop, pop["weight"] > 0)
    return {"deaths": int(deaths.sum()), "splits": splits, "merged": merged}


def device_info() -> dict:
    return {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
            "numpy": np.__version__, "sqlite": sqlite3.sqlite_version, "cpu_count": os.cpu_count()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="50000,150000,300000,600000")
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--label", default="device")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out) if a.out else ROOT / "benchmarks" / "results" / f"{a.label}_simulants.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = {"label": a.label, "device": device_info(), "runs": []}
    for k in [int(x) for x in a.sizes.split(",") if x.strip()]:
        pop = make_population(k, seed=1)
        rng = np.random.default_rng(1)
        people = total(pop); deaths = 0
        t0 = time.perf_counter()
        for _ in range(a.steps):
            deaths += step(pop, rng)["deaths"]
        secs = (time.perf_counter() - t0) / a.steps
        assert total(pop) == people - deaths
        mb = sum(pop[f].nbytes for f in FIELDS) / 1048576
        run = {"k": k, "rows_end": int(pop["weight"].size), "secs_per_step": round(secs, 4), "mb": round(mb, 1)}
        result["runs"].append(run)
        print(json.dumps(run), flush=True)
    out.write_text(json.dumps(result, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `PYTHONPATH=D:/Code/Caerness "$LOCALAPPDATA/Programs/Python/Python313/python.exe" tests/bench_simulants_test.py`
Expected: `bench_simulants conservation PASS {...}`

- [ ] **Step 5: Record the PC baseline**

Run: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe" tools/bench_simulants.py --label pc`
Expected: four JSON lines, one per size, with `secs_per_step` growing roughly linearly with `k`, then `wrote ...pc_simulants.json`.

- [ ] **Step 6: Checkpoint**

```bash
git add tools/bench_simulants.py tests/bench_simulants_test.py benchmarks/results/pc_simulants.json
```

Commit only if the user has approved commits: `git commit -m "pop01: weighted-simulant step prototype benchmark"`.

---

### Task 3: Budget derivation (`tools/derive_budgets.py`)

**Files:**
- Create: `tools/derive_budgets.py`
- Test: `tests/derive_budgets_test.py`

**Interfaces:**
- Consumes: the JSON outputs of Tasks 1 and 2.
- Produces: `derive(engine: dict, simulants: dict, *, season_target_secs: float = 60.0, steps_per_season: int = 3) -> dict`, returning `{"named_season_secs", "secs_per_simulant_step", "background_budget_secs", "max_simulants", "named_speedup_needed"}`. Also the CLI `python tools/derive_budgets.py ENGINE_JSON SIMULANTS_JSON [--season-secs 60]`.

- [ ] **Step 1: Write the failing test**

```python
"""derive_budgets: phone numbers -> simulant budget against the spec's season target."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from derive_budgets import derive


def run():
    engine = {"segments": [{"days": 1, "wall_secs": 1.0}, {"days": 90, "wall_secs": 30.0}]}
    sims = {"runs": [{"k": 100000, "secs_per_step": 1.0}, {"k": 200000, "secs_per_step": 2.0}]}
    d = derive(engine, sims, season_target_secs=60.0)
    # 60 s target - 30 s named = 30 s for 3 background steps at 1e-5 s per simulant-step -> 1,000,000.
    assert abs(d["secs_per_simulant_step"] - 1e-5) < 1e-12, d
    assert d["named_season_secs"] == 30.0 and d["background_budget_secs"] == 30.0
    assert d["max_simulants"] == 1_000_000 and d["named_speedup_needed"] == 1.0, d
    # When the named engine alone blows the target, the budget is zero and the needed speed-up is reported.
    slow = {"segments": [{"days": 90, "wall_secs": 300.0}]}
    d2 = derive(slow, sims, season_target_secs=60.0)
    assert d2["max_simulants"] == 0 and abs(d2["named_speedup_needed"] - 5.0) < 1e-9, d2
    print("derive_budgets PASS", d)


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PYTHONPATH=D:/Code/Caerness "$LOCALAPPDATA/Programs/Python/Python313/python.exe" tests/derive_budgets_test.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'derive_budgets'`

- [ ] **Step 3: Write the implementation**

```python
"""Turn phone benchmark results into a POP-01 background budget.

season wait = named-engine season + steps_per_season x (secs per simulant-step x simulants).
The named engine's measured 90-day segment is the named cost; whatever remains of the season target is
the background's.  Usage: python tools/derive_budgets.py ENGINE_JSON SIMULANTS_JSON [--season-secs 60]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _slope_through_origin(runs: list[dict]) -> float:
    num = sum(float(r["k"]) * float(r["secs_per_step"]) for r in runs)
    den = sum(float(r["k"]) ** 2 for r in runs)
    return num / den


def derive(engine: dict, simulants: dict, *, season_target_secs: float = 60.0, steps_per_season: int = 3) -> dict:
    seasons = [s for s in engine["segments"] if int(s["days"]) >= 90]
    seg = seasons[0] if seasons else max(engine["segments"], key=lambda s: int(s["days"]))
    named = float(seg["wall_secs"]) * (90.0 / int(seg["days"]))
    per = _slope_through_origin(simulants["runs"])
    budget = max(0.0, season_target_secs - named)
    return {
        "named_season_secs": round(named, 3),
        "secs_per_simulant_step": per,
        "background_budget_secs": round(budget, 3),
        "max_simulants": int(budget / (steps_per_season * per) + 1e-6) if per > 0 else 0,
        "named_speedup_needed": round(max(1.0, named / season_target_secs), 6),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("engine_json")
    ap.add_argument("simulants_json")
    ap.add_argument("--season-secs", type=float, default=60.0)
    a = ap.parse_args()
    d = derive(json.loads(Path(a.engine_json).read_text()), json.loads(Path(a.simulants_json).read_text()),
               season_target_secs=a.season_secs)
    print(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `PYTHONPATH=D:/Code/Caerness "$LOCALAPPDATA/Programs/Python/Python313/python.exe" tests/derive_budgets_test.py`
Expected: `derive_budgets PASS {...}`

- [ ] **Step 5: Derive the PC budget as a reference**

Run: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe" tools/derive_budgets.py benchmarks/results/pc_engine.json benchmarks/results/pc_simulants.json`
Expected: a JSON block. The PC is expected to show `named_speedup_needed` above 1, since the named engine is about 1 s a day, so a season is about 90 s. Report the numbers to the user.

- [ ] **Step 6: Checkpoint**

```bash
git add tools/derive_budgets.py tests/derive_budgets_test.py
```

Commit only if the user has approved commits: `git commit -m "pop01: derive phone simulation budgets"`.

---

### Task 4: Phone package and setup guide

**Files:**
- Create: `tools/package_phone.py`
- Test: `tests/package_phone_test.py`
- Modify: `ANDROID_ONEPLUS12.md` (replace sections 1–2; add section 11)

**Interfaces:**
- Produces: `build(out: Path) -> dict` returning `{"path": str, "files": int, "bytes": int}`, and the CLI `python tools/package_phone.py [--out dist/caerness_phone.zip]`. The zip holds `run.py`, `engine/`, `mobile/`, `canon/`, `tools/`, `DESIGN.md`, `ANDROID_ONEPLUS12.md` and a consistent single-file copy of `data/caerness.db` made with the SQLite backup API. It has no `__pycache__`, `*.pyc`, `-wal` or `-shm` files.

- [ ] **Step 1: Write the failing test**

```python
"""package_phone: one zip with everything the phone needs, a consistent DB, and no build litter."""
from __future__ import annotations
import os, sqlite3, sys, tempfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from package_phone import build


def run():
    tmp = Path(tempfile.mkdtemp(prefix="caerness_pkg_"))
    info = build(tmp / "caerness_phone.zip")
    assert info["files"] > 50 and info["bytes"] > 1_000_000, info
    z = zipfile.ZipFile(info["path"])
    names = set(z.namelist())
    for required in ("run.py", "engine/db.py", "engine/simulation.py", "mobile/index.html", "data/caerness.db",
                     "tools/bench_sim.py", "tools/bench_simulants.py", "tools/derive_budgets.py", "ANDROID_ONEPLUS12.md"):
        assert required in names, required
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc") or n.endswith("-wal") or n.endswith("-shm")]
    assert not [n for n in names if n.startswith("tests/")]
    z.extract("data/caerness.db", tmp)
    c = sqlite3.connect(tmp / "data" / "caerness.db")
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]) == 0
    c.close()
    print("package_phone PASS", info)


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PYTHONPATH=D:/Code/Caerness "$LOCALAPPDATA/Programs/Python/Python313/python.exe" tests/package_phone_test.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'package_phone'`

- [ ] **Step 3: Write the implementation**

```python
"""Build the single zip to copy onto the phone (Termux home) for running and benchmarking Caerness.

Usage: python tools/package_phone.py [--out dist/caerness_phone.zip]
The packaged opening is copied with the SQLite backup API so pending WAL content is included and the
zip holds one consistent file.  The source DB is opened read-only.
"""
from __future__ import annotations

import argparse
import sqlite3
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["run.py", "DESIGN.md", "ANDROID_ONEPLUS12.md"]
DIRS = ["engine", "mobile", "canon", "tools"]


def _wanted(p: Path) -> bool:
    return "__pycache__" not in p.parts and p.suffix != ".pyc" and p.is_file()


def build(out: Path) -> dict:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with tempfile.TemporaryDirectory(prefix="caerness_pkgdb_") as tmp:
        db_copy = Path(tmp) / "caerness.db"
        src = sqlite3.connect(f"file:{ROOT / 'data' / 'caerness.db'}?mode=ro", uri=True)
        dst = sqlite3.connect(db_copy)
        src.backup(dst)
        dst.close(); src.close()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in FILES:
                z.write(ROOT / f, f); count += 1
            for d in DIRS:
                for p in sorted((ROOT / d).rglob("*")):
                    if _wanted(p):
                        z.write(p, p.relative_to(ROOT).as_posix()); count += 1
            z.write(db_copy, "data/caerness.db"); count += 1
    return {"path": str(out), "files": count, "bytes": out.stat().st_size}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist" / "caerness_phone.zip"))
    info = build(Path(ap.parse_args().out))
    print(info)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `PYTHONPATH=D:/Code/Caerness "$LOCALAPPDATA/Programs/Python/Python313/python.exe" tests/package_phone_test.py`
Expected: `package_phone PASS {...}`

- [ ] **Step 5: Update the phone guide**

In `ANDROID_ONEPLUS12.md`, replace everything from `## 1. Install a current Termux build` up to, but not including, `## 3. Build a local llama.cpp server` with:

````markdown
## 1. Install Termux

Install Termux from F-Droid or the Termux GitHub releases (the Play Store build is outdated). Open it and run:

```bash
pkg update && pkg upgrade
pkg install python python-numpy unzip
termux-setup-storage
```

`termux-setup-storage` gives Termux access to Android's Downloads folder (`~/storage/downloads`).

## 2. Copy Caerness onto the phone

On the PC, build the package:

```bash
python tools/package_phone.py
```

Copy `dist/caerness_phone.zip` to the phone's Downloads folder (USB, Google Drive or similar). Then in Termux:

```bash
mkdir -p ~/caerness && cd ~/caerness
unzip -o ~/storage/downloads/caerness_phone.zip
python -c "import numpy, sqlite3; print('numpy', numpy.__version__, 'sqlite', sqlite3.sqlite_version)"
```

Keep Caerness and its database in the Termux home folder, not in shared storage: SQLite is more reliable there.
````

Append at the end of the file:

````markdown
## 11. Phase 0 benchmark (POP-01)

Run from `~/caerness` with the phone plugged in and the screen on (Android throttles background apps).

1. Engine alone:

   ```bash
   python tools/bench_sim.py --label phone
   ```

2. Background prototype:

   ```bash
   python tools/bench_simulants.py --label phone
   ```

3. Optional, with the local model loaded (in a second Termux session, start `llama-server` as in section 5 and leave it idle):

   ```bash
   python tools/bench_sim.py --label phone_with_model
   ```

4. Copy the results back to the PC:

   ```bash
   cp ~/caerness/benchmarks/results/*.json ~/storage/downloads/
   ```

Put the JSON files in `benchmarks/results/` on the PC.
````

- [ ] **Step 6: Build the real package**

Run: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe" tools/package_phone.py`
Expected: `{'path': '...dist\\caerness_phone.zip', 'files': N, 'bytes': M}`, with M roughly 10–20 MB.

- [ ] **Step 7: Checkpoint**

```bash
git add tools/package_phone.py tests/package_phone_test.py ANDROID_ONEPLUS12.md
```

`dist/` is a build output; do not add it. Commit only if the user has approved commits: `git commit -m "pop01: phone package and setup guide"`.

---

### Task 5: Run on the phone and record the budgets (user and agent together)

**Files:**
- Add: `benchmarks/results/phone_engine.json`, `benchmarks/results/phone_simulants.json`, and optionally `benchmarks/results/phone_with_model_engine.json` (from the user)
- Create: `POP01_PHASE0_PHONE_BENCHMARK_<date>.md`
- Modify: `docs/superpowers/specs/2026-09-26-population-tiers-design.md` §8 (replace the "expected scale" sentence with the measured values)

- [ ] **Step 1: The user sets up the phone.** They follow `ANDROID_ONEPLUS12.md` sections 1, 2 and 11 and send back the JSON files. If any command fails, capture the exact error text: Termux Python and numpy versions differ from the PC.

- [ ] **Step 2: Derive the phone budgets**

Run: `"$LOCALAPPDATA/Programs/Python/Python313/python.exe" tools/derive_budgets.py benchmarks/results/phone_engine.json benchmarks/results/phone_simulants.json`

If `phone_with_model_engine.json` exists, run it again with that file as the engine input. Use the with-model result as the binding one.

- [ ] **Step 3: Write `POP01_PHASE0_PHONE_BENCHMARK_<date>.md`** with:
  - the device block from each JSON;
  - a table of 1-, 7- and 90-day wall times for PC, phone, and phone with model;
  - the phone ÷ PC ratio;
  - the simulant `secs_per_step` by `k`, and memory in MB;
  - the `derive_budgets` output.

  Include a verdict against the spec §8 targets:
  - Does a day meet 1–2 s?
  - Does a week meet about 10 s?
  - Does a season meet about 1 minute?
  - How much named-engine speed-up (`named_speedup_needed`) is required before any background is added?

- [ ] **Step 4: Update the spec §8 sentence.** Replace `The expected scale is about 300k simulants, notables in the low tens of thousands and named people in the low thousands, all to be confirmed by measurement.` with the measured `max_simulants`, the named-engine speed-up needed, and the date of the measurement.

- [ ] **Step 5: Report to the user.** Say whether the phone meets the targets. If `named_speedup_needed` is above 1, say that the next plan must start with named-engine cadence and performance work (spec §3: coarser cadence for distant, quiet named people during skips) before adding the background.

- [ ] **Step 6: Checkpoint**

```bash
git add benchmarks/results/phone_*.json POP01_PHASE0_PHONE_BENCHMARK_*.md docs/superpowers/specs/2026-09-26-population-tiers-design.md
```

Commit only if the user has approved commits: `git commit -m "pop01: phase 0 phone benchmark results"`.

---

## Follow-on plans (written after Phase 0 results)

1. **POP-01 background store and life rules:** the production simulant store (partitioned numpy arrays persisted in SQLite blobs, extending `engine/background_population.py`), niche weighting, split and merge, shared life rules (mortality, marriage, births with Core heredity, means), and the conservation, chunk-invariance and tier-invariance tests.
2. **POP-01 cultivation:**
   - shared cultivation rule functions;
   - circumstance-driven walls;
   - the renewal ladder with capability reset and no fertility effect;
   - Sixth depth bands;
   - the multi-decade calibration.
3. **POP-01 tiers and migration:**
   - the known, notable and named tiers;
   - distinction, significance and relevance scores with hysteresis;
   - canon-authored placement;
   - retiring the frozen profiles;
   - the schema migration.
