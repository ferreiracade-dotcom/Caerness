"""The readers behind a made man's choices (Saint Jude): what in his world pushes him to take out his leader or start a racket.

Each reader is `fn(conn, actor_id, day) -> 0..1` over real state and is registered with `org_motives.register_motive`;
the motive lists, weights and rates are package data (worlds/saintjude/outfits.json `motives`, `rates`, design figures).
The list is open: a new reader plus a data line adds a reason without touching `outfit_choices`.

Where the world has no record yet, the closest real state is read instead (so a reader returns 0 rather than invent):
  * a hit or hunt "he could know of" is an open agenda item naming him that he is listed in (`known_to`) or that a man
    he trusts holds; there is no knowledge-system query yet.
  * a line the leader took is an incident naming the leader as offender and the man as victim with a line (Task 11 raises them).
  * "the people there" and "the businesses there": no place has a population of its own (every background person sits at the
    city root), so thin ground is measured against the other places that are worked, by lines per working place.
  * "passed over": the day a seat was filled is the day of the `history` note `fill_unit_leader` leaves for the new leader; capos of
    the opening have no such note, so no one starts out passed over.
  * "business closed" and "a rival pushed off the ground" have no record; a line ended or its holder lost stands for them.
  * "new products and businesses" from the dated timeline are not read; demand follows the package's yearly tables.
  * debts are not modelled; need compares earnings with the living standard.
  * "heat" is the open cases naming him.
"""
from __future__ import annotations

import datetime
import functools
import json
from pathlib import Path
import sqlite3

from . import ledger, org_motives
from .law_opening import precinct_for_location
from .org_lifecycle import RISE_REASON
from .orgs import clamp01, head_of, kind_rules, seat_of, seats_of, unit_leader_of
from .world_package import org_rules, package_for

REMOVE = "remove_superior"
START = "start_racket"
_KIN = ("spouse", "parent_of", "grandparent_of", "sibling_of", "child_of")
_YEAR = 365.0


# ---- small readings ----

def _rel(conn: sqlite3.Connection, a: int | None, b: int | None):
    if a is None or b is None:
        return None
    return conn.execute("SELECT * FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(a), int(b))).fetchone()


def _recent(conn: sqlite3.Connection) -> int:
    return int(org_motives._fig(conn, "motive_recent_days", default=90))


def _period(conn: sqlite3.Connection) -> int:
    return int(org_rules(package_for(conn)).get("period_days") or 28)


def _drive(conn: sqlite3.Connection, actor_id: int, trait: str) -> float:
    r = conn.execute(f"SELECT {trait} FROM actor_drives WHERE actor_id=?", (int(actor_id),)).fetchone()
    return float(r[0]) if r is not None else 0.5


def _roles(conn: sqlite3.Connection, choice: str) -> list[str]:
    return list((org_motives._sphere_data(conn).get("choice_roles") or {}).get(choice) or [])


def _live(conn: sqlite3.Connection, actor_id: int | None) -> bool:
    if actor_id is None:
        return False
    from .orgs import is_living
    return is_living(conn, int(actor_id))


def context(conn: sqlite3.Connection, actor_id: int, choice: str = REMOVE):
    """(org id, his seat, his unit leader, the head) for a man who may weigh `choice`, in the first of his active seats
    whose role the package lists for it; None when he has none or the organisation has no unit leaders."""
    roles = _roles(conn, choice)
    for s in seats_of(conn, actor_id):
        if s["status"] != "active" or s["role_key"] not in roles:
            continue
        org = int(s["org_actor_id"])
        leader = unit_leader_of(conn, int(actor_id), org)
        if choice == REMOVE and (leader is None or leader == int(actor_id) or not _live(conn, leader)):
            continue
        return org, s, leader, head_of(conn, org)
    return None


def _money(conn: sqlite3.Connection, day: int, flows, *, to: int | None = None, frm: int | None = None, back: int = 0) -> float:
    """Sum of org_money rows in a flow set over the period that ended `back` periods before `day`."""
    per = _period(conn)
    hi, lo = int(day) - back * per, int(day) - (back + 1) * per
    q = "SELECT COALESCE(SUM(amount),0) FROM org_money WHERE day>? AND day<=? AND kind IN (%s)" % ",".join("?" * len(flows))
    args: list = [lo, hi, *flows]
    if to is not None:
        q += " AND to_actor_id=?"
        args.append(int(to))
    if frm is not None:
        q += " AND from_actor_id=?"
        args.append(int(frm))
    return float(conn.execute(q, args).fetchone()[0])


def _ladder_share(conn: sqlite3.Connection, org: int, role: str) -> float:
    for r in kind_rules(conn, org).get("rules") or []:
        if r.get("type") == "to_superior" and role in (r.get("roles") or []):
            spec = r["share"]
            return float(org_motives._fig(conn, spec["figure"], default=spec.get("default")))
    return 0.0


def _years(seat, day: int) -> float | None:
    return None if seat is None or seat["inducted_day"] is None else (int(day) - int(seat["inducted_day"])) / _YEAR


def _age(conn: sqlite3.Connection, actor_id: int, day: int) -> float | None:
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (int(actor_id),)).fetchone()
    return None if r is None or r[0] is None else (int(day) - int(r[0])) / _YEAR


def _held(conn: sqlite3.Connection, actor_id: int, day: int) -> list:
    return conn.execute("SELECT * FROM custody WHERE actor_id=? AND kind='held' AND since_day<=? AND (until_day IS NULL OR until_day>=?)",
                        (int(actor_id), int(day), int(day))).fetchall()


# ---- taking out his leader ----

def grievance(conn, actor_id, day):
    """His resentment of the leader, squared: mild resentment is not a reason to kill, a murderous one is."""
    ctx = context(conn, actor_id)
    r = _rel(conn, actor_id, ctx[2]) if ctx else None
    return 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0) ** 2


def squeezed(conn, actor_id, day):
    """What he kicked up to the leader last period against the ladder share; or his line taken (incidents, as offender the leader)."""
    ctx = context(conn, actor_id)
    if ctx is None:
        return 0.0
    org, seat, leader, _ = ctx
    out = 0.0
    earned = _money(conn, day, org_motives.inflow_flows(conn), to=actor_id)
    ladder = _ladder_share(conn, org, seat["role_key"])
    if earned > 0 and ladder > 0:
        out = clamp01((_money(conn, day, org_motives.upward_flows(conn), frm=actor_id) / earned - ladder) / ladder)
    n = conn.execute("SELECT COUNT(*) FROM org_incidents WHERE offender_actor_id=? AND victim_actor_id=? AND victim_line_id IS NOT NULL",
                     (int(leader), int(actor_id))).fetchone()[0]
    return max(out, 1.0 - 0.5 ** n)


def passed_over(conn, actor_id, day):
    """The man who now leads his unit took the seat lately (the `history` note `fill_unit_leader` leaves) and is junior to
    him in years inducted or standing."""
    ctx = context(conn, actor_id)
    if ctx is None:
        return 0.0
    org, seat, leader, _ = ctx
    rose = conn.execute("SELECT created_day FROM org_agenda WHERE actor_id=? AND kind='history' AND json_extract(metadata_json,'$.reason')=? "
                        "ORDER BY id DESC LIMIT 1", (int(leader), RISE_REASON)).fetchone()
    if rose is None or int(day) - int(rose[0]) > int(org_motives._fig(conn, "motive_seat_memory_days", default=365)):
        return 0.0
    cs = seat_of(conn, leader, org)
    ys, yc = _years(seat, day), _years(cs, day)
    by_years = 0.0 if ys is None or yc is None else clamp01((ys - yc) / float(org_motives._fig(conn, "motive_years_full", default=10)))
    return max(by_years, clamp01(float(seat["standing"]) - float(cs["standing"])))


def blocked_ambition(conn, actor_id, day):
    """His ambition, as far as the leader is older than he and holds the unit's lines."""
    ctx = context(conn, actor_id)
    if ctx is None or not ctx[1]["unit_id"]:
        return 0.0
    leader = ctx[2]
    ac, am = _age(conn, leader, day), _age(conn, actor_id, day)
    if ac is None or am is None or ac <= 0:
        return 0.0
    rows = conn.execute("SELECT holder_actor_id,weekly_take FROM org_lines WHERE unit_id=? AND status='active'", (int(ctx[1]["unit_id"]),)).fetchall()
    total = sum(float(r["weekly_take"]) for r in rows)
    hold = sum(float(r["weekly_take"]) for r in rows if r["holder_actor_id"] == leader) / total if total > 0 else 0.0
    return clamp01(_drive(conn, actor_id, "ambition") * hold * clamp01((ac - am) / ac))


def fear(conn, actor_id, day):
    """An open hit or hunt naming him that he could know of; or the leader held on a homicide charge (who talks)."""
    ctx = context(conn, actor_id)
    if ctx is None:
        return 0.0
    leader = ctx[2]
    out = 0.0
    for it in conn.execute("SELECT * FROM org_agenda WHERE kind IN ('hit','discipline_hunt') AND status='open' AND subject_kind='actor' AND subject_id=?",
                           (int(actor_id),)).fetchall():
        meta = json.loads(it["metadata_json"] or "{}")
        if int(actor_id) in [int(x) for x in meta.get("known_to") or []]:
            out = 1.0
            continue
        r = _rel(conn, actor_id, it["actor_id"])
        if r is not None and float(r["trust"]) > 0:
            out = max(out, clamp01(float(r["trust"]) / 100.0))
    if any("homicide" in str(h["charge"]).lower() for h in _held(conn, leader, day)):
        floor = float(org_motives._fig(conn, "motive_homicide_talk_floor", default=0.3))
        cs = seat_of(conn, leader, ctx[0])
        out = max(out, floor + (1.0 - float(cs["reliability"])) * (1.0 - floor))
    return out


def leader_weak(conn, actor_id, day):
    """The leader is held, sick, losing money (what the men below him kicked up fell) or losing ground (lines ended lately)."""
    ctx = context(conn, actor_id)
    if ctx is None:
        return 0.0
    org, seat, leader, _ = ctx
    parts = []
    cs = seat_of(conn, leader, org)
    parts.append(1.0 if _held(conn, leader, day) or cs["status"] == "held" else 0.0)
    sick = conn.execute("SELECT MAX(severity) FROM health_conditions WHERE actor_id=? AND status='active'", (int(leader),)).fetchone()[0]
    parts.append(clamp01(float(sick or 0.0) / 100.0))
    now, before = _money(conn, day, org_motives.upward_flows(conn), to=leader), _money(conn, day, org_motives.upward_flows(conn), to=leader, back=1)
    parts.append(clamp01(1.0 - now / before) if before > 0 else 0.0)
    if seat["unit_id"]:
        lo = int(day) - _recent(conn)
        ended = conn.execute("SELECT COUNT(*) FROM org_lines WHERE unit_id=? AND status<>'active' AND ended_day>=?", (int(seat["unit_id"]), lo)).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM org_lines WHERE unit_id=?", (int(seat["unit_id"]),)).fetchone()[0]
        parts.append(ended / total if total else 0.0)
    rest = 1.0
    for p in parts:
        rest *= 1.0 - clamp01(p)
    return 1.0 - rest


def outside_push(conn, actor_id, day):
    """A man who reports to the head, tied to him, wants the leader gone (resentment above respect)."""
    ctx = context(conn, actor_id)
    if ctx is None or ctx[3] is None:
        return 0.0
    org, _, leader, head = ctx
    out = 0.0
    for x in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND superior_actor_id=? AND status='active' AND actor_id NOT IN (?,?)",
                          (org, int(head), int(actor_id), int(leader))).fetchall():
        tie, wants = _rel(conn, actor_id, x[0]), _rel(conn, x[0], leader)
        if tie is None or wants is None or float(tie["trust"]) <= 0:
            continue
        out = max(out, clamp01((float(wants["resentment"]) - float(wants["respect"])) / 100.0) * clamp01(float(tie["trust"]) / 100.0))
    return out


def revenge(conn, actor_id, day):
    """The leader harmed him, his kin or a close friend (harm incidents with the leader as offender)."""
    ctx = context(conn, actor_id)
    if ctx is None:
        return 0.0
    out = 0.0
    for h in conn.execute("SELECT actor_id FROM harm_incidents WHERE json_extract(metadata_json,'$.offender_actor_id')=?", (int(ctx[2]),)).fetchall():
        v = int(h[0])
        if v == int(actor_id) or conn.execute(
                "SELECT 1 FROM typed_relationship_facts WHERE status='active' AND relation_type IN (%s) AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))"
                % ",".join("?" * len(_KIN)), (*_KIN, int(actor_id), v, v, int(actor_id))).fetchone():
            return 1.0
        r = _rel(conn, actor_id, v)
        if r is not None:
            out = max(out, clamp01(float(r["affection"]) / 100.0))
    return out


def head_wants(conn: sqlite3.Connection, head: int | None, leader: int | None) -> float:
    """The head's resentment of the leader above his respect, 0..1."""
    r = _rel(conn, head, leader)
    return 0.0 if r is None else clamp01((float(r["resentment"]) - float(r["respect"])) / 100.0)


def head_wants_it(conn, actor_id, day):
    ctx = context(conn, actor_id)
    return 0.0 if ctx is None else head_wants(conn, ctx[3], ctx[2])


# ---- starting a racket ----

def _subtree(conn: sqlite3.Connection, loc: int) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        "WITH RECURSIVE sub(id) AS (SELECT ? UNION ALL SELECT l.id FROM locations l JOIN sub ON l.parent_location_id=sub.id) SELECT id FROM sub", (int(loc),))]


def thin_ground(conn: sqlite3.Connection, loc: int) -> float:
    """1 where nothing works the place, falling to 0 at twice the lines per working place of the city's grounds.
    (No place has a population of its own yet, so the comparison is with the other places that are worked.)"""
    ids = set(_subtree(conn, loc))
    rows = conn.execute("SELECT location_id,COUNT(*) FROM org_lines WHERE status='active' AND location_id IS NOT NULL GROUP BY location_id").fetchall()
    worked = {int(r[0]) for r in rows} | {int(r[0]) for r in conn.execute(
        "SELECT ground_location_id FROM org_units WHERE status='active' AND ground_location_id IS NOT NULL")}
    total = sum(int(r[1]) for r in rows)
    if not total or not worked:
        return 1.0
    here = sum(int(r[1]) for r in rows if int(r[0]) in ids)
    places_here = max(1, len(worked & ids))
    return clamp01(1.0 - (here / places_here) / (total / len(worked)) / 2.0)


def unclaimed_pool(conn: sqlite3.Connection, pool: str) -> float:
    """The part of a pool no organisation holds."""
    held = conn.execute("SELECT COALESCE(SUM(share_pct),0) FROM org_holdings WHERE pool_key=? AND status='active'", (pool,)).fetchone()[0]
    return clamp01(1.0 - float(held) / 100.0)


def vacancy(conn: sqlite3.Connection, loc: int, day: int, pool: str | None = None) -> float:
    """Lines at this place that ended, or whose holder died, was held or left, lately: 1 - 0.5 ** how many."""
    lo = int(day) - _recent(conn)
    q = ("SELECT COUNT(*) FROM org_lines l LEFT JOIN org_holdings h ON h.id=l.holding_id WHERE l.location_id=? "
         "AND ((l.status<>'active' AND l.ended_day>=?) OR (l.status='active' AND EXISTS (SELECT 1 FROM org_seats s WHERE s.actor_id=l.holder_actor_id "
         "AND s.status IN ('dead','held','out') AND (s.left_day IS NULL OR s.left_day>=?))))")
    args: list = [int(loc), lo, lo]
    if pool is not None:
        q += " AND h.pool_key=?"
        args.append(pool)
    n = conn.execute(q, args).fetchone()[0]
    return 1.0 - 0.5 ** n


def _interp(rows: list, col: int, y: float) -> float | None:
    pts = sorted((float(r[0]), float(r[col])) for r in rows)
    if not pts:
        return None
    if y <= pts[0][0]:
        return pts[0][1]
    for (x0, v0), (x1, v1) in zip(pts, pts[1:]):
        if y <= x1:
            return v0 + (v1 - v0) * (y - x0) / (x1 - x0)
    return pts[-1][1]


@functools.lru_cache(maxsize=4)
def _tables(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")).get("tables") or {}


def demand(conn: sqlite3.Connection, pool: str, day: int) -> float:
    """The pool's rise over the coming year in the package's table for it (0 when it falls or has no table)."""
    src = (org_motives._sphere_data(conn).get("demand_sources") or {}).get(pool)
    pkg = package_for(conn)
    path = pkg.data.get("design")
    cal = pkg.calendar
    if not src or path is None or cal.get("kind") != "gregorian":
        return 0.0
    table = _tables(str(path)).get(src["table"])
    if not table:
        return 0.0
    col = table["columns"].index(src["column"])
    d = datetime.date.fromisoformat(str(cal["start"])) + datetime.timedelta(days=int(day))
    y = d.year + (d.timetuple().tm_yday - 1) / _YEAR
    now, nxt = _interp(table["rows"], col, y), _interp(table["rows"], col, y + 1.0)
    return 0.0 if not now or nxt is None else clamp01((nxt - now) / now)


def _places(conn: sqlite3.Connection, seat) -> list[int]:
    """His unit's ground first, then the places inside it and the places beside it (the same parent, when that parent is
    not the city itself: the districts of a city are not next to one another by being in it)."""
    if not seat["unit_id"]:
        return []
    r = conn.execute("SELECT ground_location_id FROM org_units WHERE id=?", (int(seat["unit_id"]),)).fetchone()
    if r is None or r[0] is None:
        return []
    ground = int(r[0])
    inside = [i for i in _subtree(conn, ground) if i != ground]
    p = conn.execute("SELECT parent_location_id FROM locations WHERE id=?", (ground,)).fetchone()
    beside: list[int] = []
    if p is not None and p[0] is not None:
        gp = conn.execute("SELECT parent_location_id FROM locations WHERE id=?", (int(p[0]),)).fetchone()
        if gp is not None and gp[0] is not None:
            beside = [int(x[0]) for x in conn.execute("SELECT id FROM locations WHERE parent_location_id=? AND id<>? ORDER BY id", (int(p[0]), ground))]
    return [ground, *sorted(inside), *beside]


def _pools(conn: sqlite3.Connection) -> list[str]:
    return list(org_motives._sphere_data(conn).get("racket_pools") or [])


def opportunity(conn: sqlite3.Connection, actor_id: int, day: int, loc: int, pool: str, memo: dict | None = None) -> float:
    """How good this place and pool are for him: the place and pool motives combined at the package's weights.
    `memo` keeps the readings and weights across calls for one man on one day."""
    memo = {} if memo is None else memo

    def got(key, fn):
        if key not in memo:
            memo[key] = fn()
        return memo[key]

    rest = 1.0
    for name, v in (("thin_ground", got(("thin", loc), lambda: thin_ground(conn, loc))),
                    ("unclaimed_pool", got(("unc", pool), lambda: unclaimed_pool(conn, pool))),
                    ("vacancy", got(("vac", loc, pool), lambda: vacancy(conn, loc, day, pool))),
                    ("demand", got(("dem", pool), lambda: demand(conn, pool, day)))):
        rest *= 1.0 - got(("w", name), lambda: org_motives.weight_of(conn, actor_id, START, name)) * v
    return 1.0 - rest


def _best(conn: sqlite3.Connection, actor_id: int, day: int, seat) -> tuple[int, str, float] | None:
    best, memo = None, {}
    for loc in _places(conn, seat):
        for pool in _pools(conn):
            o = opportunity(conn, actor_id, day, loc, pool, memo)
            if best is None or o > best[2] + 1e-12:
                best = (loc, pool, o)
    return best


def _start_seat(conn: sqlite3.Connection, actor_id: int):
    ctx = context(conn, actor_id, START)
    return None if ctx is None else ctx[1]


def _read_place(fn):
    """A motive over his own ground (where he looks for a place to start is `_best`: his ground and the places beside it)."""
    def reader(conn, actor_id, day):
        seat = _start_seat(conn, actor_id)
        places = _places(conn, seat) if seat is not None else []
        return fn(conn, actor_id, day, places[0]) if places else 0.0
    return reader


def _thin(conn, actor_id, day, loc):
    return thin_ground(conn, loc)


def _vacant(conn, actor_id, day, loc):
    return vacancy(conn, loc, day)


def _read_pool(fn):
    def reader(conn, actor_id, day):
        return max((fn(conn, p, day) for p in _pools(conn)), default=0.0) if _start_seat(conn, actor_id) else 0.0
    return reader


def low_heat(conn, actor_id, day):
    """His precinct is on his organisation's Pad and no open case names him."""
    seat = _start_seat(conn, actor_id)
    places = _places(conn, seat) if seat is not None else []
    if not places:
        return 0.0
    precinct = precinct_for_location(conn, places[0])
    if precinct is None:
        return 0.0
    paid = conn.execute("SELECT 1 FROM org_arrangements WHERE payer_kind='org' AND payer_id=? AND status='active' AND position_key LIKE ? LIMIT 1",
                        (int(seat["org_actor_id"]), f"{precinct}:%")).fetchone()
    case = conn.execute("SELECT 1 FROM crime_reports WHERE offender_actor_id=? AND status='open' LIMIT 1", (int(actor_id),)).fetchone()
    return 1.0 if paid and not case else 0.0


def _by_role(conn: sqlite3.Connection, spec: dict, role: str) -> str:
    return (spec.get("by_role") or {}).get(role, spec["default"])


def start_cost(conn: sqlite3.Connection, role: str) -> float:
    return float(org_motives._fig(conn, _by_role(conn, org_motives._sphere_data(conn)["start_racket"]["cost"], role)))


def line_weekly(conn: sqlite3.Connection, role: str) -> float:
    return float(org_motives._fig(conn, _by_role(conn, org_motives._sphere_data(conn)["start_racket"]["line_weekly"], role)))


def means(conn, actor_id, day):
    seat = _start_seat(conn, actor_id)
    if seat is None:
        return 0.0
    cash = ledger.balance(conn, ("person", int(actor_id)))
    men = conn.execute("SELECT COUNT(*) FROM org_seats WHERE superior_actor_id=? AND status='active'", (int(actor_id),)).fetchone()[0]
    needed = float(org_motives._fig(conn, "motive_workers_needed", default=2))
    return clamp01(cash / start_cost(conn, seat["role_key"])) * (0.5 + 0.5 * clamp01(men / needed))  # no cash, no means; men to work it complete it


def need(conn, actor_id, day):
    """The shortfall of his earnings (last period, grossed up to a year; the lines he holds before any is posted) against his living standard."""
    seat = _start_seat(conn, actor_id)
    living = (org_motives._sphere_data(conn).get("living") or {}).get(seat["role_key"] if seat is not None else "")
    if seat is None or not living:
        return 0.0
    standard = float(org_motives._fig(conn, living))
    per = _period(conn)
    flow = _money(conn, day, org_motives.inflow_flows(conn), to=actor_id)
    if flow > 0 or _money(conn, day, org_motives.upward_flows(conn), frm=actor_id) > 0:
        yearly = (flow - _money(conn, day, org_motives.upward_flows(conn), frm=actor_id)) * _YEAR / per
    else:
        take = conn.execute("SELECT COALESCE(SUM(weekly_take),0) FROM org_lines WHERE holder_actor_id=? AND status='active'", (int(actor_id),)).fetchone()[0]
        if not take:
            return 0.0
        yearly = float(take) * 52.0 * (1.0 - _ladder_share(conn, int(seat["org_actor_id"]), seat["role_key"]))
    return clamp01(1.0 - yearly / standard)


def appetite(conn, actor_id, day):
    seat = _start_seat(conn, actor_id)
    if seat is None:
        return 0.0
    return clamp01((_drive(conn, actor_id, "ambition") + float(seat["greed"])) / 2.0 * _drive(conn, actor_id, "risk_tolerance"))


for _name, _fn in (("grievance", grievance), ("squeezed", squeezed), ("passed_over", passed_over), ("blocked_ambition", blocked_ambition),
                   ("fear", fear), ("leader_weak", leader_weak), ("outside_push", outside_push), ("revenge", revenge),
                   ("head_wants_it", head_wants_it)):
    org_motives.register_motive(REMOVE, _name, _fn)
for _name, _fn in (("thin_ground", _read_place(_thin)), ("unclaimed_pool", _read_pool(lambda c, p, d: unclaimed_pool(c, p))),
                   ("vacancy", _read_place(_vacant)), ("demand", _read_pool(demand)), ("low_heat", low_heat),
                   ("means", means), ("need", need), ("appetite", appetite)):
    org_motives.register_motive(START, _name, _fn)
