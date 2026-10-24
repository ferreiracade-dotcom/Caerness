"""Validate worlds/saintjude/design_figures.json (stdlib only).

Checks the Part VI allocation table (9.3A), the draw ranges, the derived figures
(recomputed from their inputs), the 1975 drug take by dial and ground, the family
gross and net of 9.3, the Pick-3 and protection tables and the population path.

    python tools/check_saintjude_pools.py          # exit 0 on success, 1 with messages
"""
from __future__ import annotations

import ast
import json
import math
import operator
import sys
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "worlds" / "saintjude" / "design_figures.json"
FAMILIES = ("sabatini", "pellegrino", "vannucci", "ferrante")
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow}
_FUNCS = {"min": min, "max": max, "abs": abs, "sum": sum, "round": round}


def _eval(expr: str, env: dict):
    """Evaluate an arithmetic expression over figure names; nothing else is allowed."""
    def go(n):
        if isinstance(n, ast.Expression):
            return go(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in env:
                raise KeyError(n.id)
            return env[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            return _BINOPS[type(n.op)](go(n.left), go(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -go(n.operand) if isinstance(n.op, ast.USub) else go(n.operand)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[go(a) for a in n.args])
        raise ValueError(f"disallowed expression element {type(n).__name__}")
    return go(ast.parse(expr, mode="eval"))


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def check(data: dict) -> list[str]:
    errs: list[str] = []
    figs = data["figures"]
    pools = data["pools"]
    alloc = data["allocation"]
    tables = data.get("tables", {})
    env = {k: v["default"] for k, v in figs.items() if _num(v.get("default"))}

    # 1. figure structure, draw ranges, derived recomputation
    for key, f in figs.items():
        kind = f.get("kind")
        for need in ("default", "unit", "tag", "source", "kind"):
            if need not in f:
                errs.append(f"figure {key}: missing {need}")
        if kind not in ("draw", "derived", "fixed"):
            errs.append(f"figure {key}: bad kind {kind!r}")
            continue
        if kind == "draw":
            r, d = f.get("range"), f.get("default")
            if not (isinstance(r, list) and len(r) == 2 and _num(d) and all(_num(x) for x in r)):
                errs.append(f"draw figure {key}: needs numeric default and [lo, hi] range")
            elif not r[0] <= d <= r[1]:
                errs.append(f"draw figure {key}: default {d} outside range {r}")
        elif kind == "derived":
            expr = f.get("formula")
            if not expr:
                errs.append(f"derived figure {key}: no formula")
                continue
            if expr == "table:protection":
                got = sum(row[3] * row[4] * 52 for row in tables["protection"]["rows"]) / 1e6
            else:
                try:
                    got = _eval(expr, env)
                except Exception as e:  # noqa: BLE001
                    errs.append(f"derived figure {key}: cannot evaluate {expr!r}: {e!r}")
                    continue
            tol = f.get("tol", 0.01)
            if abs(got - f["default"]) > tol:
                errs.append(f"derived figure {key}: formula gives {got:.5g}, default {f['default']} (tol {tol})")

    # 2. pools: shares, dollars, ranges, ties
    for key, p in pools.items():
        sh = p.get("shares", {})
        if set(sh) != set(FAMILIES):
            errs.append(f"pool {key}: shares must name the four families")
            continue
        if abs(sum(sh.values()) - 100) > 0.5:
            errs.append(f"pool {key}: family shares sum to {sum(sh.values()):.2f}, not 100")
        lo, hi = p["range_m"]
        if not lo <= p["default_m"] <= hi:
            errs.append(f"pool {key}: default {p['default_m']} outside range {p['range_m']}")
        if p.get("unit_basis") == "dollars":
            tot = sum(p["family_m"].values())
            if abs(tot - p["default_m"]) > 0.005:
                errs.append(f"pool {key}: family dollars sum to {tot:.4f}, default is {p['default_m']}")
            for f_, (flo, fhi) in p.get("family_range_m", {}).items():
                if not flo <= p["family_m"][f_] <= fhi:
                    errs.append(f"pool {key}: {f_} dollars outside its range")
        t = p.get("tie")
        if t:
            fig = figs.get(t["figure"])
            if fig is None:
                errs.append(f"pool {key}: ties to unknown figure {t['figure']}")
            elif abs(fig["default"] - p["default_m"]) > t["tol"]:
                errs.append(f"pool {key}: default {p['default_m']} differs from figure {t['figure']} = {fig['default']}")

    # 3. numbers: chain, Italian share, claims
    g = lambda k: figs[k]["default"]  # noqa: E731
    if abs(g("numbers_bank_net_m") - g("numbers_handle_m") * g("numbers_net_margin")) > 0.005:
        errs.append("numbers bank net is not handle x margin")
    it = g("numbers_handle_eastside_m") * g("numbers_net_margin") * g("italian_numbers_share_pct") / 100
    if abs(it - 0.45) > 0.01:
        errs.append(f"Italian numbers share is {it:.3f}, expected 0.45")
    claims = alloc["numbers_claims_m"]
    computed = {"italian": g("numbers_italian_net_m"), "combine": g("numbers_combine_net_m"), "puerto_rican": g("numbers_pr_net_m"),
                "irish": g("numbers_irish_net_m"), "chinatown": g("numbers_chinatown_net_m")}
    for k, v in computed.items():
        if abs(v - claims[k]) > 0.01:
            errs.append(f"numbers claim {k}: figures give {v:.3f}, allocation says {claims[k]}")
    if abs(sum(computed.values()) - 2.0) > 0.01 or abs(claims["total"] - 2.0) > 1e-9:
        errs.append(f"claims on the numbers bank net sum to {sum(computed.values()):.3f}, not 2.0")

    # 4. drug take by dial and ground, 1975
    d = alloc["drugs_1975"]
    market = {"heroin": g("drug_market_heroin_m"), "cocaine": g("drug_market_cocaine_m"), "marijuana": g("drug_market_marijuana_m"),
              "pills": g("drug_market_pills_m"), "crank": g("drug_market_crank_m")}
    ground = {k: g(f"drug_ground_italian_{k}_pct") / 100 for k in market}
    step_rate = {0: 0.0, 1: g("dial_step1_take_per_10m") / 1e7, 2: g("dial_step2_take_per_10m") / 1e7, 3: g("dial_step3_take_per_10m") / 1e7}
    if abs(sum(d["ground_family_pct"].values()) - 100) > 0.5:
        errs.append("drug ground shares by family do not sum to 100")
    take = {}
    for fam in FAMILIES:
        share = d["ground_family_pct"][fam] / 100
        take[fam] = sum(market[k] * ground[k] * share * step_rate[d["dial_defaults"][fam][k]] for k in market)
        if abs(take[fam] - d["expected_take_m"][fam]) > d["tolerance_m"]:
            errs.append(f"drug take {fam}: model gives {take[fam]:.4f}, bible {d['expected_take_m'][fam]}")
    tot = sum(take.values())
    if abs(tot - d["expected_take_m"]["four"]) > 0.01:
        errs.append(f"drug take, four families: model gives {tot:.4f}, bible {d['expected_take_m']['four']}")
    drug_pool = pools["drugs_by_dial_and_ground"]["family_m"]
    for fam in FAMILIES:
        if abs(drug_pool[fam] - d["expected_take_m"][fam]) > 1e-9:
            errs.append(f"pool drugs_by_dial_and_ground disagrees with allocation.drugs_1975 for {fam}")

    # 5. family gross, Pad and net (9.3 reproduced from 9.3A)
    tol = alloc["gross_tolerance_m"]
    gross = {f: 0.0 for f in FAMILIES}
    for key, p in pools.items():
        if p.get("kind") == "cost":
            continue
        for fam in FAMILIES:
            gross[fam] += p["family_m"][fam] if p.get("unit_basis") == "dollars" else p["default_m"] * p["shares"][fam] / 100
    pad = pools["pad"]["family_m"]
    if abs(sum(pad.values()) - g("pad_total_m")) > 0.005:
        errs.append("Pad by family does not sum to the Pad total")
    for fam in FAMILIES:
        exp = alloc["family_gross_net_9_3"][fam]
        if abs(gross[fam] - exp["gross_m"]) > tol:
            errs.append(f"gross {fam}: 9.3A gives {gross[fam]:.3f}, 9.3 prints {exp['gross_m']}")
        net = gross[fam] - pad[fam]
        if abs(net - exp["net_m"]) > tol:
            errs.append(f"net {fam}: gross - Pad = {net:.3f}, 9.3 prints {exp['net_m']}")
        if abs(pad[fam] - exp["pad_m"]) > 1e-9:
            errs.append(f"Pad {fam}: pool {pad[fam]}, 9.3 prints {exp['pad_m']}")
        men = g(f"made_men_{fam}_mid")  # 9.3 prints per-man figures at the range midpoints
        if abs(exp["net_m"] * 1e6 / men - exp["per_man_usd"]) > 1500:
            errs.append(f"per made man {fam}: {exp['net_m'] * 1e6 / men:.0f} against {exp['per_man_usd']}")
    four = alloc["family_gross_net_9_3"]["four"]
    if abs(sum(gross.values()) - four["gross_m"]) > tol:
        errs.append(f"gross, four: {sum(gross.values()):.3f} against {four['gross_m']}")
    net4 = sum(gross.values()) - sum(pad.values())
    if abs(net4 - 35.9) > tol:
        errs.append(f"net after the Pad is {net4:.3f}, expected 35.9")
    if abs(four["net_m"] - 35.9) > 1e-9:
        errs.append("allocation four-family net is not 35.9")
    if abs(four["net_m"] * 1e6 / g("made_men_total_mid") - four["per_man_usd"]) > 1500:
        errs.append("per made man across the four does not match 200,000")

    # 6. population path
    pop = {y: g("population_city_1975_m") * (1 - g("population_decline_pct") / 100) ** (y - 1975) for y in (1980, 1985, 1990)}
    for y, want in ((1980, 1.06), (1985, 1.02), (1990, 0.98)):
        if abs(pop[y] - want) > 0.01:
            errs.append(f"population {y}: path gives {pop[y]:.4f}M, bible {want}M")
    pe = figs["made_men_pellegrino"]
    if pe.get("ceiling") != 55 or pe.get("extended_range") != [51, 55]:
        errs.append("Pellegrino must keep 51-55 as an extended range with ceiling 55")

    # 7. tables
    var = g("pick3_variable_net_per_dollar")
    fixed_cost = g("pick3_fixed_cost_m")
    for year, lost, handle, net, ital, net_lost in tables["pick3"]["rows"]:
        h = g("numbers_handle_m") * (1 - lost / 100)
        if abs(h - handle) > 0.011:
            errs.append(f"Pick-3 {year}: handle {h:.2f} against {handle}")
        n = h * var - fixed_cost
        if abs(n - net) > 0.02:
            errs.append(f"Pick-3 {year}: net {n:.3f} against {net}")
        if abs(net * g("numbers_share_eastside_pct") / 100 * g("italian_numbers_share_pct") / 100 - ital) > 0.011:
            errs.append(f"Pick-3 {year}: Italian share does not follow from the net")
        if abs((1 - net / 2.0) * 100 - net_lost) > 1.0:
            errs.append(f"Pick-3 {year}: net lost {(1 - net / 2.0) * 100:.1f} against {net_lost}")
    bounds = tables["pick3"]["bounds_1980_bank_net_m"]
    loss = 1 - 1.52 / 2.0
    if abs(2.0 * (1 - loss / 2) - bounds["supplier"]) > 0.02 or abs(2.0 * (1 - loss * 1.5) - bounds["rival"]) > 0.02:
        errs.append("Pick-3 1980 supplier/rival bounds do not follow from the loss")
    for name, biz, pct, payers, wk, lo, hi, annual in tables["protection"]["rows"]:
        if abs(biz * pct / 100 - payers) > 0.5:
            errs.append(f"protection {name}: payers {payers} is not {biz} x {pct}%")
        if abs(payers * wk * 52 / 1000 - annual) > 1.5:
            errs.append(f"protection {name}: annual {payers * wk * 52 / 1000:.1f}K against {annual}K")
        if not lo <= wk <= hi:
            errs.append(f"protection {name}: weekly default outside its range")
    c = tables["concrete_3_4A"]
    if abs(sum(r[1] for r in c["rows"]) - c["totals"]["volume_m"]) > 0.01:
        errs.append("concrete 3.4A volumes do not sum to 330")
    for r in c["rows"]:
        if abs(r[1] * r[2] / 100 - r[3]) > 0.06:
            errs.append(f"concrete 3.4A {r[0]}: covered {r[1] * r[2] / 100:.2f} against {r[3]}")
    if abs(sum(r[3] for r in c["rows"]) - c["totals"]["covered_m"]) > 0.06 or abs(sum(r[4] for r in c["rows"]) - c["totals"]["take_m"]) > 0.015:
        errs.append("concrete 3.4A covered or take totals do not add")
    m = tables["drug_market_by_year"]["rows"]
    for row in m:
        if abs(sum(row[1:6]) - row[6]) > 0.1:
            errs.append(f"drug market {row[0]}: parts do not add to the total")
    return errs


def run(path: Path | str = DEFAULT_PATH) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return check(data)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_PATH
    errs = run(path)
    if errs:
        for e in errs:
            print("FAIL:", e)
        print(f"{len(errs)} problem(s) in {path}")
        return 1
    print(f"OK: {path.name} checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
