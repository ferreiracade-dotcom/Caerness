from __future__ import annotations

"""POPBACK comparison harness.

This is deliberately split into two kinds of evidence:
1. Executable local backends (NumPy, pandas, SQLite, Starsim-inspired active UID arrays).
2. Optional direct-framework hooks, detected but not required, for Polars/neworder/Starsim/mesa-frames.

The executable backends share one Caerness-shaped workload: stable identity, aging, mortality,
migration eligibility, occupation transition, Core assessment, one-person lookup/promotion,
and checkpoint/restart. Randomness for the array backends is stateless and deterministic by
(uid, step, stream), so restart does not depend on a hidden RNG cursor.
"""

import importlib.util
import json
import math
import os
import sqlite3
import tempfile
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SEED = np.uint64(0x9E3779B97F4A7C15)
SIZES = (10_000, 100_000, 1_000_000)
STEPS = 12


def splitmix64(x: np.ndarray) -> np.ndarray:
    """Vectorised SplitMix64 finalizer; used only for deterministic benchmark draws."""
    z = x.astype(np.uint64, copy=False) + np.uint64(0x9E3779B97F4A7C15)
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return z ^ (z >> np.uint64(31))


def draws(uid: np.ndarray, step: int, stream: int) -> np.ndarray:
    # Use high 53 bits, matching double mantissa precision.
    x = uid.astype(np.uint64, copy=False) ^ SEED ^ np.uint64((step * 0xD1B54A32D192ED03) & 0xFFFFFFFFFFFFFFFF) ^ np.uint64((stream * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF)
    z = splitmix64(x)
    return ((z >> np.uint64(11)).astype(np.float64)) * (1.0 / (1 << 53))


def mortality_probability(age_days: np.ndarray) -> np.ndarray:
    age = age_days / 365.2425
    annual = np.where(
        age < 1, 0.018,
        np.where(age < 15, 0.0004,
        np.where(age < 50, 0.0018,
        np.where(age < 65, 0.009,
        np.where(age < 75, 0.03, 0.085))))
    )
    return annual / 12.0


def seed_state(n: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(812197 + n)
    return {
        "uid": np.arange(1, n + 1, dtype=np.int64),
        "age_days": rng.integers(0, 80 * 365, size=n, dtype=np.int32),
        "alive": np.ones(n, dtype=np.bool_),
        "region": rng.integers(0, 8, size=n, dtype=np.uint8),
        "occupation": rng.integers(0, 24, size=n, dtype=np.uint8),
        "household": rng.integers(0, max(1, n // 4), size=n, dtype=np.int32),
        "core_assessed": (rng.random(n) < 0.12),
        "mobility_pressure": rng.random(n).astype(np.float32),
    }


@dataclass
class Result:
    backend: str
    people: int
    init_seconds: float
    step_seconds: float
    state_bytes: int
    checkpoint_bytes: int
    checkpoint_seconds: float
    restore_seconds: float
    lookup_microseconds: float
    alive: int
    migration_eligible_last_step: int
    occupation_changes: int
    core_assessments: int
    deterministic_restart: bool
    stable_identity_lookup: bool
    notes: str = ""


def _state_bytes(d: dict[str, np.ndarray]) -> int:
    return int(sum(v.nbytes for v in d.values()))


def _step_arrays(d: dict[str, np.ndarray], step: int, selector: np.ndarray | None = None) -> tuple[int, int, int]:
    uid = d["uid"] if selector is None else d["uid"][selector]
    ages = d["age_days"] if selector is None else d["age_days"][selector]
    alive = d["alive"] if selector is None else d["alive"][selector]
    mobility = d["mobility_pressure"] if selector is None else d["mobility_pressure"][selector]

    # For a Starsim-style active selector, all selected rows are active by construction.
    active = alive.copy()
    ages[active] += 30
    p = mortality_probability(ages)
    death = active & (draws(uid, step, 1) < p)
    alive[death] = False

    adult = ages >= 18 * 365
    migration = alive & adult & (mobility > 0.82)
    occ_change = migration & (draws(uid, step, 2) < 0.08)
    new_core = alive & adult & ~((d["core_assessed"] if selector is None else d["core_assessed"][selector])) & (draws(uid, step, 3) < 0.002)

    if selector is None:
        d["occupation"][occ_change] = (d["occupation"][occ_change] + 1) % 24
        d["core_assessed"][new_core] = True
    else:
        slots = selector
        d["age_days"][slots] = ages
        d["alive"][slots] = alive
        oslots = slots[occ_change]
        cslots = slots[new_core]
        d["occupation"][oslots] = (d["occupation"][oslots] + 1) % 24
        d["core_assessed"][cslots] = True

    return int(migration.sum()), int(occ_change.sum()), int(new_core.sum())


def _checkpoint_npz(d: dict[str, np.ndarray], path: Path) -> tuple[int, float]:
    t = time.perf_counter()
    np.savez(path, **d)
    elapsed = time.perf_counter() - t
    return path.stat().st_size, elapsed


def _restore_npz(path: Path) -> tuple[dict[str, np.ndarray], float]:
    t = time.perf_counter()
    with np.load(path, allow_pickle=False) as z:
        d = {k: z[k] for k in z.files}
    return d, time.perf_counter() - t


def run_numpy(n: int) -> Result:
    t = time.perf_counter(); d = seed_state(n); init = time.perf_counter() - t
    changes = assessments = migration = 0
    t = time.perf_counter()
    for step in range(STEPS):
        migration, c, a = _step_arrays(d, step)
        changes += c; assessments += a
    step_seconds = time.perf_counter() - t

    probe_uid = n // 2 + 1
    t = time.perf_counter(); slot = probe_uid - 1; person = {k: v[slot].item() for k, v in d.items()}; lookup = (time.perf_counter()-t)*1e6
    stable = int(person["uid"]) == probe_uid

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "state.npz"
        cbytes, csec = _checkpoint_npz(d, path)
        restored, rsec = _restore_npz(path)
        deterministic = all(np.array_equal(d[k], restored[k]) for k in d)

    return Result("numpy_dense", n, init, step_seconds, _state_bytes(d), cbytes, csec, rsec, lookup,
                  int(d["alive"].sum()), migration, changes, assessments, deterministic, stable,
                  "Direct dense arrays; every operation scans full slots, masked by alive state.")


def run_starsim_pattern(n: int) -> Result:
    t = time.perf_counter(); d = seed_state(n); active_uids = np.arange(n, dtype=np.int64); init = time.perf_counter() - t
    changes = assessments = migration = 0
    t = time.perf_counter()
    for step in range(STEPS):
        migration, c, a = _step_arrays(d, step, active_uids)
        changes += c; assessments += a
        # Delayed removal preserves stable raw slots while active operations shrink to living people.
        active_uids = active_uids[d["alive"][active_uids]]
    step_seconds = time.perf_counter() - t

    probe_uid = n // 2 + 1
    t = time.perf_counter(); slot = probe_uid - 1; person = {k: v[slot].item() for k, v in d.items()}; lookup = (time.perf_counter()-t)*1e6
    stable = int(person["uid"]) == probe_uid

    save = dict(d); save["active_uids"] = active_uids
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "state.npz"
        cbytes, csec = _checkpoint_npz(save, path)
        restored, rsec = _restore_npz(path)
        deterministic = all(np.array_equal(save[k], restored[k]) for k in save)

    return Result("starsim_active_uid_pattern", n, init, step_seconds, _state_bytes(d)+active_uids.nbytes,
                  cbytes, csec, rsec, lookup, int(d["alive"].sum()), migration, changes, assessments,
                  deterministic, stable,
                  "Caerness prototype of Starsim's raw-slot + active-UID semantics; not a Starsim runtime benchmark.")


def run_pandas(n: int) -> Result:
    t = time.perf_counter(); base = seed_state(n); df = pd.DataFrame(base); init = time.perf_counter() - t
    changes = assessments = migration = 0
    t = time.perf_counter()
    # Use arrays without copy; this is the closest installed analogue to dataframe-backed agent stores.
    for step in range(STEPS):
        d = {k: df[k].to_numpy(copy=False) for k in base}
        migration, c, a = _step_arrays(d, step)
        changes += c; assessments += a
    step_seconds = time.perf_counter() - t

    probe_uid = n // 2 + 1
    t = time.perf_counter(); row = df.iloc[probe_uid-1]; lookup = (time.perf_counter()-t)*1e6
    stable = int(row["uid"]) == probe_uid

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "state.pkl"
        t = time.perf_counter(); df.to_pickle(path); csec = time.perf_counter()-t; cbytes = path.stat().st_size
        t = time.perf_counter(); restored = pd.read_pickle(path); rsec = time.perf_counter()-t
        deterministic = df.equals(restored)
    mem = int(df.memory_usage(index=True, deep=True).sum())
    return Result("pandas_columnar", n, init, step_seconds, mem, cbytes, csec, rsec, lookup,
                  int(df["alive"].sum()), migration, changes, assessments, deterministic, stable,
                  "Installed dataframe control; architectural proxy only for dataframe frameworks, not Polars/mesa-frames runtime.")


def run_sqlite(n: int) -> Result:
    base = seed_state(n)
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=OFF"); conn.execute("PRAGMA synchronous=OFF")
    conn.execute("CREATE TABLE people(uid INTEGER PRIMARY KEY,age_days INTEGER,alive INTEGER,region INTEGER,occupation INTEGER,household INTEGER,core_assessed INTEGER,mobility REAL)")
    t = time.perf_counter()
    conn.executemany("INSERT INTO people VALUES (?,?,?,?,?,?,?,?)", zip(
        base["uid"].tolist(), base["age_days"].tolist(), base["alive"].astype(np.uint8).tolist(),
        base["region"].tolist(), base["occupation"].tolist(), base["household"].tolist(),
        base["core_assessed"].astype(np.uint8).tolist(), base["mobility_pressure"].tolist()))
    conn.commit(); init = time.perf_counter()-t

    changes = assessments = migration = 0
    # SQL control uses deterministic modular sampling. It is a persistence/control benchmark, not outcome-parity benchmark.
    t = time.perf_counter()
    for step in range(STEPS):
        conn.execute("UPDATE people SET age_days=age_days+30 WHERE alive=1")
        conn.execute("""UPDATE people SET alive=0 WHERE alive=1 AND
          ((age_days<365 AND ((uid*1103515245+?*12345)&2147483647)%1000000 < 1500)
           OR (age_days>=27375 AND ((uid*1664525+?*1013904223)&2147483647)%1000000 < 7000))""", (step,step))
        migration = int(conn.execute("SELECT COUNT(*) FROM people WHERE alive=1 AND age_days>=6570 AND mobility>.82").fetchone()[0])
        before = conn.total_changes
        conn.execute("""UPDATE people SET occupation=(occupation+1)%24 WHERE alive=1 AND age_days>=6570 AND mobility>.82
                        AND ((uid*22695477+?)&2147483647)%10000 < 800""", (step,))
        changes += conn.total_changes-before
        before = conn.total_changes
        conn.execute("""UPDATE people SET core_assessed=1 WHERE alive=1 AND age_days>=6570 AND core_assessed=0
                        AND ((uid*214013+?*2531011)&2147483647)%100000 < 200""", (step,))
        assessments += conn.total_changes-before
    conn.commit(); step_seconds = time.perf_counter()-t

    probe_uid = n // 2 + 1
    t = time.perf_counter(); row = conn.execute("SELECT * FROM people WHERE uid=?", (probe_uid,)).fetchone(); lookup=(time.perf_counter()-t)*1e6
    stable = bool(row and int(row[0]) == probe_uid)
    pages = conn.execute("PRAGMA page_count").fetchone()[0]; page_size=conn.execute("PRAGMA page_size").fetchone()[0]
    state_bytes = pages*page_size

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "state.sqlite"
        t=time.perf_counter(); out=sqlite3.connect(path); conn.backup(out); out.close(); csec=time.perf_counter()-t; cbytes=path.stat().st_size
        t=time.perf_counter(); restored=sqlite3.connect(path); alive2=int(restored.execute("SELECT COUNT(*) FROM people WHERE alive=1").fetchone()[0]); restored.close(); rsec=time.perf_counter()-t
        alive=int(conn.execute("SELECT COUNT(*) FROM people WHERE alive=1").fetchone()[0]); deterministic=alive2==alive
    conn.close()
    return Result("sqlite_set_based", n, init, step_seconds, state_bytes, cbytes, csec, rsec, lookup,
                  alive, migration, changes, assessments, deterministic, stable,
                  "Authoritative SQL control; sampling predicate differs, so compare systems cost, persistence, and lookup rather than exact counts.")


def optional_backends() -> dict[str, bool]:
    return {m: bool(importlib.util.find_spec(m)) for m in ("polars", "neworder", "starsim", "mesa_frames")}


def projection(result: Result, target: int = 52_000_000) -> dict[str, float]:
    per_person = result.state_bytes / result.people
    return {
        "backend": result.backend,
        "bytes_per_person_observed": round(per_person, 3),
        "projected_52m_state_gib": round(per_person * target / (1024**3), 3),
        "projected_1m_state_mib": round(per_person * 1_000_000 / (1024**2), 2),
    }


def main() -> None:
    rows: list[Result] = []
    for n in SIZES:
        for fn in (run_numpy, run_starsim_pattern, run_pandas, run_sqlite):
            r = fn(n); rows.append(r); print(json.dumps(asdict(r), sort_keys=True), flush=True)
    max_rows = [r for r in rows if r.people == max(SIZES)]
    payload = {
        "steps": STEPS,
        "sizes": SIZES,
        "optional_backend_availability": optional_backends(),
        "framework_runtime_note": "Polars/neworder/Starsim/mesa-frames are direct-runtime optional hooks; unavailable packages are not impersonated as measured framework runs.",
        "52m_memory_projection_from_1m": [projection(r) for r in max_rows],
    }
    print(json.dumps(payload, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
