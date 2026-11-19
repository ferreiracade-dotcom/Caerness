"""Organisation money: who earns a line, and the periodic posting of what lines bring in and pass up.

Sphere-free: roles, flows and the rules that move money between roles come from the package's orgs.json (see its
"_doc"). Every `period_days` from the opening, `post_period` brings each line's take in from outside (`ledger.receive`,
the only money organisations ever gain) and then moves it between existing purses with `ledger.transfer`, stage by
stage so every man holds what he passes on before he passes it. Each movement is one `org_money` row. Nothing is created
or lost inside the organisations. A flow with its own function (`flow_handlers` in orgs.json) is posted by that function.
"""
from __future__ import annotations

import hashlib
import importlib
import sqlite3
from collections import defaultdict

from . import ledger
from .design import figure, run_seed
from .orgs import kind_rules
from .world_package import org_rules, package_for

PERIOD_DAYS = 28  # used when the package's orgs.json gives no period_days
MIN_ROW = 0.005  # amounts below half a cent are not posted

_DEAD = ("dead", "deceased", "historical")


def _rules(conn: sqlite3.Connection) -> dict:
    return org_rules(package_for(conn))


def _period(conn: sqlite3.Connection) -> int:
    return int(_rules(conn).get("period_days") or PERIOD_DAYS)


def _inflow(conn: sqlite3.Connection) -> str | None:
    flows = _rules(conn).get("flows") or []
    return str(flows[0]) if flows else None


def _rendezvous(seed: int, tag: str, actor_id: int, candidates: list[int]) -> int | None:
    """Pick one of `candidates` for a man by a stable hash, so a tie holds until the man he is tied to goes."""
    if not candidates:
        return None
    return max(candidates, key=lambda c: hashlib.sha256(f"{seed}:{tag}:{actor_id}:{c}".encode()).digest())


def _share(conn: sqlite3.Connection, spec: dict) -> float:
    return float(figure(conn, spec["figure"], default=spec.get("default")))


# ---- who is alive to earn ----

def _is_alive(r: sqlite3.Row | None) -> bool:
    """A seat is alive when it is active and its person is living and not dead, held or out."""
    return r is not None and r["status"] == "active" and r["life_status"] == "living" and r["actor_status"] not in _DEAD


class Roster:
    """Live seats of every organisation, and who stands in for a man who cannot earn (his unit leader, then the head)."""

    def __init__(self, conn: sqlite3.Connection):
        self.seats: dict[tuple[int, int], sqlite3.Row] = {}  # (actor, org) -> seat row with life columns
        self.by_org: dict[int, list[tuple[int, sqlite3.Row]]] = defaultdict(list)
        for r in conn.execute(
            """SELECT r.*, COALESCE(lp.life_status,'living') AS life_status, lower(COALESCE(a.status,'active')) AS actor_status
               FROM org_seats r JOIN actors a ON a.id=r.actor_id LEFT JOIN actor_life_profiles lp ON lp.actor_id=r.actor_id"""):
            self.seats[(int(r["actor_id"]), int(r["org_actor_id"]))] = r
            self.by_org[int(r["org_actor_id"])].append((int(r["actor_id"]), r))
        self.kinds = {org: kind_rules(conn, org) for org in self.by_org}
        self.top: dict[int, list[int]] = defaultdict(list)  # org -> live holders of the head role, by actor id
        for org, rows in self.by_org.items():
            head = self.kinds[org].get("head")
            for a, r in rows:
                if head and r["role_key"] == head and _is_alive(r):
                    self.top[org].append(a)
        for v in self.top.values():
            v.sort()

    def seat(self, actor_id: int | None, org: int) -> sqlite3.Row | None:
        return None if actor_id is None else self.seats.get((int(actor_id), int(org)))

    def alive(self, actor_id: int | None, org: int) -> bool:
        return _is_alive(self.seat(actor_id, org))

    def head(self, org: int) -> int | None:
        top = self.top.get(int(org))
        return top[0] if top else None

    def unit_leader(self, actor_id: int, org: int) -> int | None:
        """Himself when he holds the kind's unit-leader role, else the first holder of it up his chain of superiors."""
        role = self.kinds.get(int(org), {}).get("unit_leader")
        if not role:
            return None
        seen: set[int] = set()
        cur: int | None = int(actor_id)
        while cur is not None and cur not in seen:
            seen.add(cur)
            r = self.seats.get((cur, int(org)))
            if r is None:
                return None
            if r["role_key"] == role:
                return cur
            cur = int(r["superior_actor_id"]) if r["superior_actor_id"] is not None else None
        return None

    def earner(self, actor_id: int | None, org: int) -> int | None:
        """The man who earns on this man's behalf: himself, else his unit leader, else the head; None if no one."""
        r = self.seat(actor_id, org)
        if r is None:
            return None
        if _is_alive(r):
            return int(actor_id)
        leader = self.unit_leader(int(actor_id), org)
        if leader is not None and leader != int(actor_id) and self.alive(leader, org):
            return leader
        return self.head(org)


def line_holder(conn: sqlite3.Connection, line_id: int) -> int:
    """The live earner of a line: its holder, or when he is dead, held or out, his stand-in in the line's organisation."""
    row = conn.execute(
        """SELECT l.holder_actor_id, COALESCE(h.org_actor_id,u.org_actor_id) AS org FROM org_lines l
           LEFT JOIN org_holdings h ON h.id=l.holding_id LEFT JOIN org_units u ON u.id=l.unit_id WHERE l.id=?""",
        (int(line_id),)).fetchone()
    if row is None:
        raise ValueError(f"no line {line_id}")
    earner = Roster(conn).earner(row[0], row[1]) if row[1] is not None else None
    if earner is None:
        raise RuntimeError(f"line {line_id} has no live earner")
    return earner


# ---- the posting ----

def _last_posted(conn: sqlite3.Connection) -> int | None:
    inflow = _inflow(conn)
    if inflow is None:
        return None
    r = conn.execute("SELECT MAX(day) FROM org_money WHERE kind=?", (inflow,)).fetchone()
    if r and r[0] is not None:
        return int(r[0])
    r = conn.execute("SELECT MIN(started_day) FROM org_holdings WHERE source='opening'").fetchone()
    return int(r[0]) if r and r[0] is not None else None


def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    last = _last_posted(conn)
    if last is None:
        return None
    due = max(last + _period(conn), int(after_day) + 1)
    return due if due <= end_day else None


def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict:
    last = _last_posted(conn)
    period = _period(conn)
    out: dict = {"periods": 0}
    while last is not None and last + period <= day:
        last += period
        res = post_period(conn, last, period)
        out["periods"] += 1
        for k, v in res.items():
            out[k] = out.get(k, 0) + v
    return out


class _State:
    """What one posting has worked out so far, keyed by (organisation, person)."""

    def __init__(self, conn: sqlite3.Connection, ros: Roster, day: int, days: int, seed: int):
        self.conn, self.ros, self.day, self.days, self.seed = conn, ros, day, days, seed
        self.take: dict[tuple[int, int], float] = defaultdict(float)
        self.hidden: dict[tuple[int, int], float] = defaultdict(float)
        self.take_line: dict[tuple[int, int], tuple[float, int]] = {}
        self.take_order: dict[int, list[int]] = defaultdict(list)
        self.net: dict[tuple[int, int], float] = {}
        self.kick_in: dict[tuple[int, int], float] = defaultdict(float)  # received from a man's own earners
        self.head_in: dict[tuple[int, int], float] = defaultdict(float)  # received by the head from regimes
        self.stages: dict[int, list[tuple]] = defaultdict(list)  # stage -> (flow, src, dst, amount, line_id, org)

    def add(self, stage: int, flow: str, src: int | None, dst: int, amount: float, line_id: int | None, org: int) -> None:
        self.stages[int(stage)].append((flow, src, dst, amount, line_id, org))

    def base_net(self, org: int, a: int) -> float:
        return max(0.0, self.net[(org, a)] - self.hidden.get((org, a), 0.0))


def _rule_paid_by_patron(rule: dict, org: int, st: _State) -> None:
    roles = set(rule["roles"])
    ret = _share(st.conn, rule["return_share"])
    base = _share(st.conn, rule["living"]) / (1.0 - ret) * st.days / 365.0
    cap = _share(st.conn, rule["cap"])
    by_patron: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for a, r in st.ros.by_org[org]:
        if r["role_key"] not in roles or not _is_alive(r):
            continue
        patron = st.ros.earner(r["superior_actor_id"], org)
        if patron is None or st.take.get((org, patron), 0.0) <= 0 or patron == a:
            continue
        by_patron[patron].append((a, base * (0.5 + float(r["reliability"]))))
    for patron, paid in by_patron.items():
        want = sum(e for _, e in paid)
        f = min(1.0, cap * st.take[(org, patron)] / want)
        for a, e in paid:
            e *= f
            if e < MIN_ROW:
                continue
            st.add(rule["stage"], rule["flow"], patron, a, e, None, org)
            st.add(rule["return_stage"], rule["return_flow"], a, patron, e * ret, None, org)
            st.net[(org, patron)] -= e * (1.0 - ret)


def _rule_to_superior(rule: dict, org: int, st: _State) -> None:
    roles, share = set(rule["roles"]), _share(st.conn, rule["share"])
    for a in st.take_order[org]:
        r = st.ros.seats[(a, org)]
        if r["role_key"] not in roles:
            continue
        sup = st.ros.earner(r["superior_actor_id"], org)
        if sup is None or sup == a:
            continue
        amount = share * st.base_net(org, a)
        if amount >= MIN_ROW:
            st.add(rule["stage"], rule["flow"], a, sup, amount, None, org)
            st.kick_in[(org, sup)] += amount


def _rule_regime_to_head(rule: dict, org: int, st: _State) -> None:
    roles, share = set(rule["roles"]), _share(st.conn, rule["share"])
    head = st.ros.head(org)
    for a, r in st.ros.by_org[org]:
        if r["role_key"] not in roles or not _is_alive(r):
            continue
        regime = st.base_net(org, a) if (org, a) in st.net else 0.0
        regime += st.kick_in.get((org, a), 0.0)
        if regime > 0 and head is not None:
            amount = share * regime
            if amount >= MIN_ROW:
                st.add(rule["stage"], rule["flow"], a, head, amount, None, org)
                st.head_in[(org, head)] += amount


def _rule_head_share(rule: dict, org: int, st: _State) -> None:
    roles, share = set(rule["roles"]), _share(st.conn, rule["share"])
    head_role = st.ros.kinds[org].get("head")
    receipts: dict[int, float] = defaultdict(float)
    for (o, h), v in st.head_in.items():
        if o == org:
            receipts[h] += v
    for (o, h), v in st.kick_in.items():  # a man's earners who sent straight to the head count as receipts too
        if o == org and st.ros.seats[(h, org)]["role_key"] == head_role:
            receipts[h] += v
    for h, got in receipts.items():
        for b, r in st.ros.by_org[org]:
            if r["role_key"] in roles and _is_alive(r):
                amount = share * got
                if amount >= MIN_ROW:
                    st.add(rule["stage"], rule["flow"], h, b, amount, None, org)


def _upward(rule: dict, org: int, st: _State, pick) -> None:
    """Every earner outside the head role passes a share up; `pick(a, r)` gives (destination, amount) or None."""
    head_role = st.ros.kinds[org].get("head")
    for a in st.take_order[org]:
        r = st.ros.seats[(a, org)]
        got = pick(a, r, head_role)
        if got is None:
            continue
        dst, amount = got
        if dst is not None and dst != a and amount >= MIN_ROW:
            st.add(rule["stage"], rule["flow"], a, dst, amount, None, org)


def _rule_to_head_pick(rule: dict, org: int, st: _State) -> None:
    share = _share(st.conn, rule["share"])

    def pick(a, r, head_role):
        if r["role_key"] == head_role:
            return None
        heads = [x for x in st.ros.top.get(org, []) if x != a]
        return _rendezvous(st.seed, rule["tag"], a, heads), share * st.base_net(org, a)
    _upward(rule, org, st, pick)


def _rule_to_head_via_superior(rule: dict, org: int, st: _State) -> None:
    keep = _share(st.conn, rule["keep"])

    def pick(a, r, head_role):
        sup = st.ros.earner(r["superior_actor_id"], org)
        if sup is not None and sup != a and st.ros.seats[(sup, org)]["role_key"] == head_role:
            dst = sup
        else:
            dst = _rendezvous(st.seed, rule["tag"], a, list(st.ros.top.get(org, [])))
        return dst, st.base_net(org, a) * (1.0 - keep)
    _upward(rule, org, st, pick)


def _rule_to_first_head(rule: dict, org: int, st: _State) -> None:
    share = _share(st.conn, rule["share"])

    def pick(a, r, head_role):
        if r["role_key"] == head_role:
            return None
        return st.ros.head(org), share * st.base_net(org, a)
    _upward(rule, org, st, pick)


_RULES = {
    "paid_by_patron": _rule_paid_by_patron,
    "to_superior": _rule_to_superior,
    "regime_to_head": _rule_regime_to_head,
    "head_share": _rule_head_share,
    "to_head_pick": _rule_to_head_pick,
    "to_head_via_superior": _rule_to_head_via_superior,
    "to_first_head": _rule_to_first_head,
}


def _handler(name: str):
    """A flow's own posting function from orgs.json flow_handlers ("module:function" under the engine package)."""
    module, _, fn = name.partition(":")
    return getattr(importlib.import_module(f".{module}", __package__), fn)


def post_period(conn: sqlite3.Connection, day: int, days: int) -> dict[str, float]:
    """Post one period: bring the take in, move it up by the kinds' rules. Returns the amount by flow (plus "rows"
    and "unearned_lines", the lines left out because nobody alive could earn on them)."""
    rules = _rules(conn)
    flows = [str(f) for f in rules.get("flows") or []]
    out: dict[str, float] = {f: 0.0 for f in flows}
    out["rows"] = 0.0
    out["unearned_lines"] = 0.0
    if not flows:
        return out
    inflow = flows[0]
    st = _State(conn, Roster(conn), int(day), int(days), run_seed(conn))
    ros = st.ros

    for r in conn.execute(
        """SELECT l.id,l.holder_actor_id,l.weekly_take,l.hidden,h.org_actor_id AS org FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id
           WHERE l.status='active' AND h.status='active' AND l.started_day<=? ORDER BY l.id""", (int(day),)):
        org = int(r["org"])
        earner = ros.earner(r["holder_actor_id"], org)
        if earner is None:
            out["unearned_lines"] += 1.0
            continue
        amount = float(r["weekly_take"]) * days / 7.0
        key = (org, earner)
        if key not in st.take:
            st.take_order[org].append(earner)
        st.take[key] += amount
        if r["hidden"]:
            st.hidden[key] += amount
        if key not in st.take_line or amount > st.take_line[key][0]:
            st.take_line[key] = (amount, int(r["id"]))
    for (org, a), amount in st.take.items():
        st.add(0, inflow, None, a, amount, st.take_line[(org, a)][1], org)
    st.net = dict(st.take)  # what each earner keeps of his line take

    by_org = {org: list(k.get("rules") or []) for org, k in ros.kinds.items()}
    for pos in range(max((len(v) for v in by_org.values()), default=0)):
        for org, rl in by_org.items():
            if pos < len(rl):
                _RULES[rl[pos]["type"]](rl[pos], org, st)

    kinds = rules.get("ledger_kinds") or {}
    purpose = str(rules.get("ledger_purpose") or "{flow}")
    rows: list[tuple] = []
    entries_by_flow: dict[str, list[tuple]] = defaultdict(list)
    for stage in sorted(st.stages):
        for flow, src, dst, amount, line_id, org in st.stages[stage]:
            if flow not in out:
                raise ValueError(f"flow {flow!r} is not declared in the package's orgs.json flows")
            if flow == inflow:
                ledger.receive(conn, ("person", dst), amount, purpose=purpose.format(flow=flow))
            else:
                ledger.transfer(conn, ("person", src), ("person", dst), amount, flow_kind=kinds[flow], purpose=purpose.format(flow=flow))
            out[flow] += amount
            rows.append((int(day), flow, src, dst, line_id, amount, org))
            entries_by_flow[flow].append((src, dst, amount, line_id, org))
    conn.executemany("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,line_id,amount,org_actor_id) VALUES (?,?,?,?,?,?,?)", rows)
    out["rows"] = float(len(rows))
    ctx = {"roster": ros, "entries": entries_by_flow}
    for flow, name in (rules.get("flow_handlers") or {}).items():
        out[flow] = float(_handler(name)(conn, day, days, ctx))
    return out
