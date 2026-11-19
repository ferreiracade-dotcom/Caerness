"""Rackets as money in the outfits (Saint Jude mob minimum, task 7): holdings, crew slices, lines and the monthly flow.

Opening: every outfit pool in design_figures.json becomes a holding (family share of the pool, or the outfit's own
pool); a family's holdings are split over its crews, and each crew's slices over its capo and soldiers as lines.
Every line has a holder, a description and a place. Other outfits hold one line per working man.

The periodic posting (take in from outside, then up the Ladder) lives in `org_money.post_period`, driven by the
package's orgs.json; this module keeps the opening builders, the design figures and the Pad flow (`post_pad`, named
in orgs.json `flow_handlers`).
"""
from __future__ import annotations

import json
import random
import sqlite3
from collections import defaultdict

from . import ledger
from .design import figure, run_seed
from .org_money import MIN_ROW
from .outfit_opening import outfit_actor
from .world_package import outfit_rules, package_for, system_enabled

# ---- data ----

def design_pools(conn: sqlite3.Connection) -> dict:
    path = package_for(conn).data.get("design")
    return dict(json.loads(path.read_text(encoding="utf-8")).get("pools") or {}) if path else {}


def design_allocation(conn: sqlite3.Connection) -> dict:
    path = package_for(conn).data.get("design")
    return dict(json.loads(path.read_text(encoding="utf-8")).get("allocation") or {}) if path else {}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


# ---- holdings, crews, lines (opening) ----

def _gross_by_family(conn: sqlite3.Connection, day: int) -> dict[str, float]:
    return {r[0]: float(r[1]) for r in conn.execute(
        """SELECT a.name,SUM(h.yearly_take) FROM org_holdings h JOIN actors a ON a.id=h.org_actor_id
           WHERE h.source='opening' GROUP BY a.name""")}


def _location(conn: sqlite3.Connection, loc_id: int | None) -> str | None:
    if loc_id is None:
        return None
    r = conn.execute("SELECT name FROM locations WHERE id=?", (loc_id,)).fetchone()
    return str(r[0]) if r else None


def _describe(kind: str, place: str | None) -> str:
    return f"{kind} in {place}" if place else kind


def _build_family(conn: sqlite3.Connection, key: str, spec: dict, rules: dict, pools: dict, day: int, seed: int) -> float:
    oid = outfit_actor(conn, spec["institution"])
    kinds = rules["line_kinds"]
    split_low = float(figure(conn, "line_split_low", default=0.3))
    held: list[tuple[str, float, int]] = []  # (pool, yearly, holding id)
    gross = 0.0
    for pool, p in pools.items():
        share = float((p.get("shares") or {}).get(key, 0) or 0)
        if p.get("kind") == "cost" or share <= 0:
            continue
        if p.get("tie"):
            yearly = float(figure(conn, p["tie"]["figure"], default=p["default_m"])) * 1e6 * share / 100.0
        else:  # a pool computed elsewhere (drugs, by dial and ground): the allocation's expected take for the family
            expected = (design_allocation(conn).get("drugs_1975", {}).get("expected_take_m") or {}).get(key)
            yearly = float(expected if expected is not None else p["default_m"] * share / 100.0) * 1e6
        hid = int(conn.execute(
            "INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,status,source,started_day) VALUES (?,?,?,?, 'active','opening',?)",
            (oid, pool, share, yearly, day)).lastrowid)
        held.append((pool, yearly, hid))
        gross += yearly
    crews = conn.execute("SELECT id,ground_location_id FROM org_units WHERE org_actor_id=? ORDER BY id", (oid,)).fetchall()
    if not crews or not held:
        return gross
    rng = random.Random(f"{seed}:outfit_money:{key}:crews")
    # Each crew's main line: one pool, drawn in proportion to the pool's size; its slice weight is doubled.
    weights: dict[int, dict[str, float]] = {}
    for c in crews:
        main = rng.choices([h[0] for h in held], weights=[max(h[1], 1.0) for h in held])[0]
        weights[int(c["id"])] = {pool: rng.gammavariate(2, 1) * (2.0 if pool == main else 1.0) for pool, _, _ in held}
    totals = {pool: sum(weights[int(c["id"])][pool] for c in crews) for pool, _, _ in held}
    men_by_crew: dict[int, list[int]] = defaultdict(list)
    for r in conn.execute("SELECT actor_id,unit_id,role_key FROM org_seats WHERE org_actor_id=? AND status='active' "
                          "AND role_key IN ('capo','soldier') AND unit_id IS NOT NULL ORDER BY actor_id", (oid,)):
        men_by_crew[int(r["unit_id"])].append(int(r["actor_id"]))
    rows: list[tuple] = []
    for c in crews:
        cid = int(c["id"])
        men = list(men_by_crew.get(cid, []))
        if not men:
            continue
        place = _location(conn, c["ground_location_id"])
        slices = sorted(((yearly * weights[cid][pool] / totals[pool], pool, hid) for pool, yearly, hid in held), reverse=True)
        rng.shuffle(men)
        lines: list[list] = []  # [yearly, pool, holding, holder]
        for i, (amount, pool, hid) in enumerate(slices):
            holder = men[i] if i < len(men) else rng.choices(men, weights=[rng.gammavariate(2, 1) for _ in men])[0]
            lines.append([amount, pool, hid, holder])
        for extra in men[len(slices):]:  # more men than slices: the largest line splits further
            big = max(lines, key=lambda ln: ln[0])
            part = big[0] * rng.uniform(split_low, 1.0 - split_low)
            big[0] -= part
            lines.append([part, big[1], big[2], extra])
        for amount, pool, hid, holder in lines:
            rows.append((hid, cid, holder, _describe(kinds[pool], place), c["ground_location_id"], amount / 52.0, day))
    conn.executemany(
        "INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,location_id,weekly_take,hidden,status,started_day) VALUES (?,?,?,?,?,?,0,'active',?)",
        rows)
    return gross


def _build_other(conn: sqlite3.Connection, key: str, spec: dict, day: int, seed: int) -> float:
    oid = outfit_actor(conn, spec["institution"])
    money = spec.get("money")
    if not money:
        return 0.0
    rng = random.Random(f"{seed}:outfit_money:{key}:lines")
    yearly: dict[str, float] = {}
    phrase = {p["key"]: p["line_kind"] for p in money["pools"]}
    for p in money["pools"]:
        v = float(figure(conn, p["figure"], default=0.0)) * 1e6
        if p.get("less_figure"):  # a tax another outfit takes comes off this pool's net
            v -= float(figure(conn, p["less_figure"], default=0.0)) * 1e6
        if v > 0:
            yearly[p["key"]] = v
    if not yearly:
        return 0.0
    hid = {pool: int(conn.execute(
        "INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,status,source,started_day) VALUES (?,?,100,?, 'active','opening',?)",
        (oid, pool, v, day)).lastrowid) for pool, v in yearly.items()}
    ranks = money["holder_ranks"]
    weight_of = money.get("rank_weight", {})
    men = [int(r[0]) for r in conn.execute(
        f"SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND role_key IN ({','.join('?' * len(ranks))}) ORDER BY actor_id",
        (oid, *ranks))]
    if not men:
        return sum(yearly.values())
    rank_of = {int(r[0]): r[1] for r in conn.execute("SELECT actor_id,role_key FROM org_seats WHERE org_actor_id=?", (oid,))}
    pool_keys = list(yearly)
    rng.shuffle(men)
    assign: dict[int, str] = {}
    for i, m in enumerate(men):  # every pool gets a man first, the rest by pool size
        assign[m] = pool_keys[i] if i < len(pool_keys) else rng.choices(pool_keys, weights=[yearly[p] for p in pool_keys])[0]
    ground = [int(r[0]) for name in spec.get("ground", []) for r in conn.execute("SELECT id FROM locations WHERE name=? ORDER BY id LIMIT 1", (name,))]
    rows = []
    for pool in pool_keys:
        team = [m for m in men if assign[m] == pool]
        w = {m: rng.gammavariate(2, 1) * weight_of.get(rank_of[m], 1.0) for m in team}
        total = sum(w.values())
        for m in team:
            loc = rng.choice(ground) if ground else None
            rows.append((hid[pool], None, m, _describe(phrase[pool], _location(conn, loc)), loc,
                         yearly[pool] * w[m] / total / 52.0, day))
    conn.executemany(
        "INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,location_id,weekly_take,hidden,status,started_day) VALUES (?,?,?,?,?,?,0,'active',?)",
        rows)
    return sum(yearly.values())


def build_holdings(conn: sqlite3.Connection, day: int | None = None) -> dict[str, float]:
    """Holdings, crew slices and lines for every outfit; returns the yearly gross by outfit key."""
    if not system_enabled(conn, "outfits"):
        return {}
    if conn.execute("SELECT 1 FROM org_holdings WHERE source='opening' LIMIT 1").fetchone():
        return {}
    day = _day(conn) if day is None else int(day)
    rules = outfit_rules(package_for(conn))
    pools = design_pools(conn)
    seed = run_seed(conn)
    out: dict[str, float] = {}
    for key, spec in rules.get("outfits", {}).items():
        if spec["shape"] == "family":
            out[key] = _build_family(conn, key, spec, rules, pools, day, seed)
    for key, spec in rules.get("outfits", {}).items():
        if spec["shape"] != "family":
            out[key] = _build_other(conn, key, spec, day, seed)
    return out


def post_pad(conn: sqlite3.Connection, day: int, days: int, ctx: dict) -> float:
    """The Pad: every active envelope is paid out of the paying family's capos' purses through a bagman.

    Each family's capos pay what the family owes in proportion to their regimes' take (the take posted this period by
    their men and themselves); a bagman collects the envelopes of his group, keeps his own and hands the rest to the
    officers. One row per payer, payee and kind: capo to bagman, bagman to officer. The amount returned is what the
    families paid out (the envelopes' total), not the bagmen's onward hand-offs."""
    rows = conn.execute(
        """SELECT e.* FROM org_arrangements e WHERE e.status='active' AND e.started_day<=? AND (e.ended_day IS NULL OR e.ended_day>?)
           ORDER BY e.id""", (int(day), int(day))).fetchall()
    if not rows:
        return 0.0
    ros = ctx["roster"]
    alive = {int(r[0]) for r in conn.execute(
        """SELECT a.id FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id
           WHERE a.id IN (%s) AND lower(COALESCE(a.status,'active')) NOT IN ('dead','deceased','historical')
             AND COALESCE(lp.life_status,'living')='living'""" % ",".join(str(int(e["official_actor_id"])) for e in rows))}
    # who collects each officer's envelope: his bagman when the bagman lives, else the officer himself
    owed: dict[tuple[int, int], float] = defaultdict(float)  # (paying family, collector) -> amount for the period
    onward: dict[tuple[int, int], float] = defaultdict(float)  # (collector, officer) -> amount handed on
    onward_org: dict[tuple[int, int], int] = {}  # (collector, officer) -> the paying outfit whose books carry the hand-off
    for e in rows:
        officer, bag = int(e["official_actor_id"]), e["go_between_actor_id"]
        if officer not in alive:
            continue  # the Pad pays the position, but there is no one to hand the envelope to until a man sits in it
        amount = float(e["weekly_usd"]) * days / 7.0
        collector = int(bag) if bag is not None and int(bag) in alive else officer
        owed[(int(e["payer_id"]), collector)] += amount
        if collector != officer:
            onward[(collector, officer)] += amount
            onward_org.setdefault((collector, officer), int(e["payer_id"]))
    # regime weights: the take each capo's regime brought in this period
    regime: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for _, earner, amount, _line, oid in ctx["entries"]["take"]:
        capo = ros.unit_leader(int(earner), oid)
        if capo is None or not ros.alive(capo, oid):
            capo = ros.head(oid)
        if capo is not None:
            regime[oid][int(capo)] += float(amount)
    paid_out = 0.0
    pay_rows: list[tuple] = []
    for (family, collector), amount in sorted(owed.items()):
        weights = regime.get(family) or ({ros.head(family): 1.0} if ros.head(family) is not None else {})
        if not weights:
            continue
        total = sum(weights.values())
        for capo, w in sorted(weights.items()):
            part = amount * w / total
            if part < MIN_ROW or capo == collector:
                continue
            got = ledger.transfer(conn, ("person", capo), ("person", collector), part, flow_kind="bribe", purpose="the Pad", allow_partial=True)
            if got > 0:
                paid_out += got
                pay_rows.append((int(day), "pad", capo, collector, None, got, family))
    for (collector, officer), amount in sorted(onward.items()):
        got = ledger.transfer(conn, ("person", collector), ("person", officer), amount, flow_kind="bribe", purpose="the Pad", allow_partial=True)
        if got > 0:
            pay_rows.append((int(day), "pad", collector, officer, None, got, onward_org.get((collector, officer))))
    conn.executemany("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,line_id,amount,org_actor_id) VALUES (?,?,?,?,?,?,?)", pay_rows)
    return paid_out
