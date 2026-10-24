"""Saint Jude design_figures.json: the validator passes and a few Part VI numbers hold."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import check_saintjude_pools as chk  # noqa: E402

FIG = ROOT / "worlds" / "saintjude" / "design_figures.json"
PRICES = ROOT / "worlds" / "saintjude" / "prices_1975.json"


def run():
    errs = chk.run(FIG)
    assert not errs, errs

    data = json.loads(FIG.read_text(encoding="utf-8"))
    figs, pools, alloc = data["figures"], data["pools"], data["allocation"]

    # Spot asserts straight from the bible.
    assert figs["population_city_1975_m"]["default"] == 1.1 and figs["population_decline_pct"]["range"] == [0.4, 1.5]
    assert figs["sjpd_sworn"]["default"] == 4800 and figs["sjpd_sworn"]["range"] == [4200, 5400]
    assert figs["made_men_pellegrino"]["default"] == 45 and figs["made_men_pellegrino"]["ceiling"] == 55
    assert abs(figs["associates_total"]["default"] - 1202) < 1
    assert figs["numbers_handle_m"]["default"] == 25.0 and figs["numbers_handle_m"]["range"] == [15, 40]
    assert abs(figs["numbers_bank_net_m"]["default"] - 2.0) < 1e-9
    assert figs["italian_numbers_share_pct"]["range"] == [20, 50]
    assert figs["pad_total_m"]["default"] == 1.6 and figs["pad_total_m"]["range"] == [0.9, 2.7]
    assert figs["payday"]["default"] == "Friday"
    assert len(pools) >= 26 and all(abs(sum(p["shares"].values()) - 100) <= 0.5 for p in pools.values())
    assert abs(sum(alloc["pad_by_family_m"].values()) - 1.6) < 1e-9
    assert alloc["family_gross_net_9_3"]["four"]["net_m"] == 35.9

    # The validator must actually fail on a broken file.
    bad = copy.deepcopy(data)
    bad["pools"]["cards_dice"]["shares"]["sabatini"] += 10
    bad["figures"]["population_decline_pct"]["range"] = [1.0, 1.5]
    bad["allocation"]["drugs_1975"]["dial_defaults"]["vannucci"]["heroin"] = 0
    msgs = chk.check(bad)
    assert any("cards_dice" in m for m in msgs) and any("population_decline_pct" in m for m in msgs) and any("drug take vannucci" in m for m in msgs), msgs

    # prices_1975.json: every row carries the fields the engine reads.
    prices = json.loads(PRICES.read_text(encoding="utf-8"))
    assert prices["year"] == 1975 and prices["currency"] == "USD"
    keys = [r["key"] for r in prices["rows"]]
    assert len(keys) == len(set(keys)) and len(keys) >= 200
    for r in prices["rows"]:
        for need in ("key", "label", "default", "range", "unit", "year_basis", "mark", "tag", "source"):
            assert need in r, (r.get("key"), need)
        assert r["year_basis"] in ("1975 dollars", "nominal"), r["key"]
        if r["range"] is not None and r["default"] is not None:
            assert r["range"][0] <= r["default"] <= r["range"][1], r["key"]
    by = {r["key"]: r for r in prices["rows"]}
    assert by["cpi_multiplier_1980"]["default"] == 1.532 and by["federal_min_wage_1975"]["default"] == 2.10
    assert by["wage_longshoreman_ila"]["default"] == 6.80 and by["pay_mayor"]["range"] == [25000, 45000]
    print("saintjude_design_figures_test passed")


if __name__ == "__main__":
    run()
