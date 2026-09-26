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
