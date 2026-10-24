"""Rackets as money in the outfits (Saint Jude mob minimum, task 7): holdings, crew slices, lines and the monthly flow.

Opening: every outfit pool in design_figures.json becomes a holding (family share of the pool, or the outfit's own
pool); a family's holdings are split over its crews, and each crew's slices over its capo and soldiers as lines.
Every line has a holder, a description and a place. Other outfits hold one line per working man.

Every 28 days from the opening, `post_period` brings each line's take in from outside (`ledger.receive`, the only
money the outfits ever gain) and then moves it up the Ladder with `ledger.transfer` between existing purses:
associates are paid out of the line's take and kick back a share, soldiers kick up to their capo, capos to the
boss, the boss pays the underboss and consigliere. Each movement is one `outfit_money` row per man per kind per
period. Nothing is created or lost inside the outfits.
"""
from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from collections import defaultdict

from . import ledger
from .design import figure, run_seed
from .outfit_opening import outfit_actor
from .world_package import outfit_rules, package_for, system_enabled

PERIOD_DAYS = 28
MIN_ROW = 0.005  # amounts below half a cent are not posted

_DEAD = ("dead", "deceased", "historical")


# ---- data ----

def design_pools(conn: sqlite3.Connection) -> dict:
    path = package_for(conn).data.get("design")
    return dict(json.loads(path.read_text(encoding="utf-8")).get("pools") or {}) if path else {}


def design_allocation(conn: sqlite3.Connection) -> dict:
    path = package_for(conn).data.get("design")
    return dict(json.loads(path.read_text(encoding="utf-8")).get("allocation") or {}) if path else {}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _meta(conn: sqlite3.Connection) -> dict[int, dict]:
    """outfit actor id -> {key, shape, spec}."""
    out: dict[int, dict] = {}
    for key, spec in outfit_rules(package_for(conn)).get("outfits", {}).items():
        try:
            oid = outfit_actor(conn, spec["institution"])
        except RuntimeError:
            continue
        out[oid] = {"key": key, "shape": spec["shape"], "spec": spec}
    return out


def _top_rank(meta: dict) -> str:
    return "boss" if meta["shape"] == "family" else next(iter(meta["spec"]["ranks"]))


def _rendezvous(seed: int, tag: str, actor_id: int, candidates: list[int]) -> int | None:
    """Pick one of `candidates` for a man by a stable hash, so a tie holds until the man he is tied to goes."""
    if not candidates:
        return None
    return max(candidates, key=lambda c: hashlib.sha256(f"{seed}:{tag}:{actor_id}:{c}".encode()).digest())


# ---- holdings, crews, lines (opening) ----

def _gross_by_family(conn: sqlite3.Connection, day: int) -> dict[str, float]:
    return {r[0]: float(r[1]) for r in conn.execute(
        """SELECT a.name,SUM(h.yearly_take) FROM outfit_holdings h JOIN actors a ON a.id=h.outfit_actor_id
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
            "INSERT INTO outfit_holdings(outfit_actor_id,pool_key,share_pct,yearly_take,status,source,started_day) VALUES (?,?,?,?, 'active','opening',?)",
            (oid, pool, share, yearly, day)).lastrowid)
        held.append((pool, yearly, hid))
        gross += yearly
    crews = conn.execute("SELECT id,ground_location_id FROM outfit_crews WHERE outfit_actor_id=? ORDER BY id", (oid,)).fetchall()
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
    for r in conn.execute("SELECT actor_id,crew_id,rank_key FROM outfit_ranks WHERE outfit_actor_id=? AND status='active' "
                          "AND rank_key IN ('capo','soldier') AND crew_id IS NOT NULL ORDER BY actor_id", (oid,)):
        men_by_crew[int(r["crew_id"])].append(int(r["actor_id"]))
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
        "INSERT INTO outfit_lines(holding_id,crew_id,holder_actor_id,description,location_id,weekly_take,hidden,status,started_day) VALUES (?,?,?,?,?,?,0,'active',?)",
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
        "INSERT INTO outfit_holdings(outfit_actor_id,pool_key,share_pct,yearly_take,status,source,started_day) VALUES (?,?,100,?, 'active','opening',?)",
        (oid, pool, v, day)).lastrowid) for pool, v in yearly.items()}
    ranks = money["holder_ranks"]
    weight_of = money.get("rank_weight", {})
    men = [int(r[0]) for r in conn.execute(
        f"SELECT actor_id FROM outfit_ranks WHERE outfit_actor_id=? AND status='active' AND rank_key IN ({','.join('?' * len(ranks))}) ORDER BY actor_id",
        (oid, *ranks))]
    if not men:
        return sum(yearly.values())
    rank_of = {int(r[0]): r[1] for r in conn.execute("SELECT actor_id,rank_key FROM outfit_ranks WHERE outfit_actor_id=?", (oid,))}
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
        "INSERT INTO outfit_lines(holding_id,crew_id,holder_actor_id,description,location_id,weekly_take,hidden,status,started_day) VALUES (?,?,?,?,?,?,0,'active',?)",
        rows)
    return sum(yearly.values())


def build_holdings(conn: sqlite3.Connection, day: int | None = None) -> dict[str, float]:
    """Holdings, crew slices and lines for every outfit; returns the yearly gross by outfit key."""
    if not system_enabled(conn, "outfits"):
        return {}
    if conn.execute("SELECT 1 FROM outfit_holdings WHERE source='opening' LIMIT 1").fetchone():
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


# ---- who is alive to earn ----

def _alive_ranks(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    """Every outfit man with his rank row; `alive` is False when the rank row or the actor says dead, held or out."""
    rows = {}
    for r in conn.execute(
        """SELECT r.*, COALESCE(lp.life_status,'living') AS life_status, lower(COALESCE(a.status,'active')) AS actor_status
           FROM outfit_ranks r JOIN actors a ON a.id=r.actor_id LEFT JOIN actor_life_profiles lp ON lp.actor_id=r.actor_id"""):
        rows[int(r["actor_id"])] = r
    return rows


def _is_alive(r: sqlite3.Row | None) -> bool:
    return r is not None and r["status"] == "active" and r["life_status"] == "living" and r["actor_status"] not in _DEAD


class _Roster:
    """Live men of every outfit, and who stands in for a man who cannot earn (his capo, then the top of the outfit)."""

    def __init__(self, conn: sqlite3.Connection):
        self.ranks = _alive_ranks(conn)
        self.meta = _meta(conn)
        self.crew_leader = {int(r[0]): int(r[1]) for r in conn.execute("SELECT id,leader_actor_id FROM outfit_crews")}
        self.top: dict[int, list[int]] = defaultdict(list)
        for a, r in self.ranks.items():
            m = self.meta.get(int(r["outfit_actor_id"]))
            if m and r["rank_key"] == _top_rank(m) and _is_alive(r):
                self.top[int(r["outfit_actor_id"])].append(a)
        for v in self.top.values():
            v.sort()

    def alive(self, actor_id: int | None) -> bool:
        return actor_id is not None and _is_alive(self.ranks.get(int(actor_id)))

    def earner(self, actor_id: int | None) -> int | None:
        """The man who earns on this man's behalf: himself, else his crew's capo, else the top of his outfit; None if no one."""
        if actor_id is None:
            return None
        r = self.ranks.get(int(actor_id))
        if r is None:
            return None
        if _is_alive(r):
            return int(actor_id)
        capo = self.crew_leader.get(int(r["crew_id"])) if r["crew_id"] is not None else None
        if capo is not None and self.alive(capo):
            return capo
        top = self.top.get(int(r["outfit_actor_id"]))
        return top[0] if top else None


def line_holder(conn: sqlite3.Connection, line_id: int) -> int:
    """The live earner of a line: its holder, or when he is dead, held or out, his capo, or when the capo is too, the boss."""
    row = conn.execute("SELECT holder_actor_id FROM outfit_lines WHERE id=?", (int(line_id),)).fetchone()
    if row is None:
        raise ValueError(f"no line {line_id}")
    earner = _Roster(conn).earner(row[0])
    if earner is None:
        raise RuntimeError(f"line {line_id} has no live earner")
    return earner


# ---- the posting ----

def _last_posted(conn: sqlite3.Connection) -> int | None:
    r = conn.execute("SELECT MAX(day) FROM outfit_money WHERE kind='take'").fetchone()
    if r and r[0] is not None:
        return int(r[0])
    r = conn.execute("SELECT MIN(started_day) FROM outfit_holdings WHERE source='opening'").fetchone()
    return int(r[0]) if r and r[0] is not None else None


def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    last = _last_posted(conn)
    if last is None:
        return None
    due = max(last + PERIOD_DAYS, int(after_day) + 1)
    return due if due <= end_day else None


def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict:
    last = _last_posted(conn)
    out: dict = {"periods": 0}
    while last is not None and last + PERIOD_DAYS <= day:
        last += PERIOD_DAYS
        res = post_period(conn, last, PERIOD_DAYS)
        out["periods"] += 1
        for k, v in res.items():
            out[k] = out.get(k, 0) + v
    return out


def _post_pad(conn: sqlite3.Connection, day: int, days: int, ctx: dict) -> float:
    """Hook for the Pad (task 8): pays the officers' envelopes out of the families' purses and returns the amount paid."""
    return 0.0


def post_period(conn: sqlite3.Connection, day: int, days: int) -> dict[str, float]:
    """Post one period: bring the take in, move it up the Ladder. Returns the amount by kind (plus "rows")."""
    seed = run_seed(conn)
    ros = _Roster(conn)
    a2s = float(figure(conn, "ladder_associate_to_soldier", default=0.225))
    s2c = float(figure(conn, "ladder_soldier_to_capo", default=0.183))
    c2b = float(figure(conn, "ladder_capo_to_boss", default=0.117))
    living = float(figure(conn, "living_associate", default=7500.0))
    exec_share = float(figure(conn, "executive_share", default=0.25))
    gift = float(figure(conn, "brigades_gift_share", default=0.1))
    dues = float(figure(conn, "horsemen_dues_share", default=0.1))
    keep = float(figure(conn, "bank_keep_share", default=0.15))
    pay_cap = float(figure(conn, "associate_pay_cap", default=0.5))

    take: dict[int, float] = defaultdict(float)
    hidden: dict[int, float] = defaultdict(float)
    take_line: dict[int, tuple[float, int]] = {}
    for r in conn.execute(
        """SELECT l.id,l.holder_actor_id,l.weekly_take,l.hidden FROM outfit_lines l JOIN outfit_holdings h ON h.id=l.holding_id
           WHERE l.status='active' AND h.status='active' AND l.started_day<=? ORDER BY l.id""", (int(day),)):
        earner = ros.earner(r["holder_actor_id"])
        if earner is None:
            continue
        amount = float(r["weekly_take"]) * days / 7.0
        take[earner] += amount
        if r["hidden"]:
            hidden[earner] += amount
        if earner not in take_line or amount > take_line[earner][0]:
            take_line[earner] = (amount, int(r["id"]))

    entries: dict[str, list[tuple[int | None, int, float, int | None]]] = {k: [] for k in
        ("take", "associate_earning", "assoc_kickup", "kickup", "executive_share")}
    for a, amount in take.items():
        entries["take"].append((None, a, amount, take_line[a][1]))

    net: dict[int, float] = dict(take)  # what each earner keeps of his line take
    # Associates are paid out of the take of the man they work under (his stand-in when he cannot earn).
    by_patron: dict[int, list[tuple[int, float]]] = defaultdict(list)
    base = living / (1.0 - a2s) * days / 365.0
    for a, r in ros.ranks.items():
        if r["rank_key"] != "associate" or not _is_alive(r):
            continue
        patron = ros.earner(r["superior_actor_id"])
        if patron is None or take.get(patron, 0.0) <= 0 or patron == a:
            continue
        by_patron[patron].append((a, base * (0.5 + float(r["reliability"]))))
    for patron, assoc in by_patron.items():
        want = sum(e for _, e in assoc)
        f = min(1.0, pay_cap * take[patron] / want)
        for a, e in assoc:
            e *= f
            if e < MIN_ROW:
                continue
            entries["associate_earning"].append((patron, a, e, None))
            entries["assoc_kickup"].append((a, patron, e * a2s, None))
            net[patron] -= e * (1.0 - a2s)

    kick_in: dict[int, float] = defaultdict(float)  # kickups received by capos and bosses (their regime / receipts)
    boss_in: dict[int, float] = defaultdict(float)
    for a in list(take):
        r = ros.ranks[a]
        m = ros.meta.get(int(r["outfit_actor_id"]))
        if m is None:
            continue
        shape, spec = m["shape"], m["spec"]
        base_net = max(0.0, net[a] - hidden.get(a, 0.0))
        if shape == "family":
            if r["rank_key"] == "capo" or r["rank_key"] == "soldier":
                superior = ros.earner(r["superior_actor_id"]) if r["rank_key"] == "soldier" else None
                if r["rank_key"] == "soldier" and superior is not None and superior != a:
                    amount = s2c * base_net
                    if amount >= MIN_ROW:
                        entries["kickup"].append((a, superior, amount, None))
                        kick_in[superior] += amount
    # Capos kick up a share of their regime (own net plus what their soldiers sent) to the boss.
    for a, r in ros.ranks.items():
        if r["rank_key"] != "capo" or not _is_alive(r):
            continue
        regime = max(0.0, net.get(a, 0.0) - hidden.get(a, 0.0)) + kick_in.get(a, 0.0)
        top = ros.top.get(int(r["outfit_actor_id"]))
        if regime > 0 and top:
            amount = c2b * regime
            if amount >= MIN_ROW:
                entries["kickup"].append((a, top[0], amount, None))
                boss_in[top[0]] += amount
    # Soldiers whose capo could not be replaced by a capo sent their kickup straight to the boss: count it as receipts.
    for dst, amount in kick_in.items():
        if ros.ranks[dst]["rank_key"] == "boss":
            boss_in[dst] += amount
    for boss, receipts in boss_in.items():
        oid = int(ros.ranks[boss]["outfit_actor_id"])
        for r in ros.ranks.values():
            if int(r["outfit_actor_id"]) == oid and r["rank_key"] in ("underboss", "consigliere") and _is_alive(r):
                amount = exec_share * receipts
                if amount >= MIN_ROW:
                    entries["executive_share"].append((boss, int(r["actor_id"]), amount, None))

    # Other outfits: money passes up to the elder, banker or president.
    for a in list(take):
        r = ros.ranks[a]
        m = ros.meta.get(int(r["outfit_actor_id"]))
        if m is None or m["shape"] == "family":
            continue
        oid, key = int(r["outfit_actor_id"]), m["key"]
        kind = (m["spec"].get("upward") or {}).get("kind")
        amount = max(0.0, take[a] - hidden.get(a, 0.0))
        if kind == "gift_to_elder" and r["rank_key"] != "elder":
            elders = [x for x in ros.top.get(oid, []) if x != a]
            dst, amount = _rendezvous(seed, "gift", a, elders), gift * amount
        elif kind == "bank_net_to_banker":
            sup = ros.earner(r["superior_actor_id"])
            bankers = [x for x in ros.top.get(oid, [])]
            dst = sup if sup is not None and sup != a and ros.ranks[sup]["rank_key"] == "banker" else _rendezvous(seed, "bank", a, bankers)
            amount *= 1.0 - keep
        elif kind == "dues" and r["rank_key"] != "president":
            dst, amount = (ros.top.get(oid) or [None])[0], dues * amount
        else:
            continue
        if dst is not None and dst != a and amount >= MIN_ROW:
            entries["kickup"].append((a, dst, amount, None))

    # Apply, bottom-up, so every man holds what he passes on before he passes it.
    flow = {"associate_earning": "wage", "assoc_kickup": "tribute", "kickup": "tribute", "executive_share": "share"}
    out: dict[str, float] = {"take": 0.0, "associate_earning": 0.0, "kickup": 0.0, "executive_share": 0.0, "pad": 0.0}
    rows: list[tuple] = []
    agg: dict[tuple[str, int, int], tuple[float, int | None]] = {}
    for phase in ("take", "associate_earning", "assoc_kickup", "kickup", "executive_share"):
        kind = "kickup" if phase == "assoc_kickup" else phase
        for src, dst, amount, line_id in entries[phase]:
            if phase == "take":
                ledger.receive(conn, ("person", dst), amount, purpose="outfit take")
            else:
                ledger.transfer(conn, ("person", src), ("person", dst), amount, flow_kind=flow[phase], purpose=f"outfit {kind}")
            out[kind] += amount
            rows.append((int(day), kind, src, dst, line_id, amount))
    ctx = {"roster": ros, "entries": entries}
    out["pad"] = float(_post_pad(conn, day, days, ctx))
    conn.executemany("INSERT INTO outfit_money(day,kind,from_actor_id,to_actor_id,line_id,amount) VALUES (?,?,?,?,?,?)", rows)
    out["rows"] = float(len(rows))
    return out
