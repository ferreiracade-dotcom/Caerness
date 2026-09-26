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
