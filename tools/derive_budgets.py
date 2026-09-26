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
