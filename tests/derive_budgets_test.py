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
