"""The weeks of the men who depend on a patron: something good, neutral or bad now and then (underworld layer, role-free).

Every `week_days` (7) each active man in a dependent role (orgs.json `kinds[k].opening.dependent_role`) rolls once against
the package's `happenings.week_rate`; when it passes, one happening is drawn from the package's open set
(`outfits.json` `happenings.kinds`): each kind has a group (good / neutral / wrong), a base weight, a floor and motives. The
motives are readers registered with `org_motives.register_motive` under the choice name `hap_<kind>`; their weights are
package data, so a new kind is a data entry (and a reader if it needs one). A kind's weight is
`base * (floor + pressure)`; `requires` readers that read 0 shut a kind out (no open case, no informing).

  good     score  bring_earner  proves_himself  recruits  favour
  neutral  drifts  goes_straight  switches
  wrong    incident  holds_out  busted  informs

Each happening writes an `org_incidents` row (offender = the man; `matters` 1 when it raises something to another
organisation's head). A mattering `incident` puts `respond_incident` on the victim organisation's head (sit_down, kill_offender,
let_it_go); sitting down puts `pay_or_refuse` on the offender's head. Everything imposed on a man calls `orgs.imposed`
(reviewed tomorrow and daily for a few days): an incident's victim and offender, a held man, a man whose seat is taken over,
an informer's named superior when it is discovered, the recipient of a demand to pay. Names of roles come from the package
data; this module names none. Every rate and figure is a design figure.
"""
from __future__ import annotations

import json
import random
import sqlite3

from . import ledger, org_heat, org_motives, outfit_motives as om
from .design import run_seed
from .org_choices import register_agenda_action, register_executor
from .law_opening import agency_for
from .org_lifecycle import leave_life, mark_for_history
from .org_motives import _fig as figure
from .orgs import add_agenda, clamp01, head_of, imposed, is_living, kind_rules, resolve_agenda, seat_of
from .relationships import adjust_relationship
from .world_package import org_rules, package_for

WEEK = 7
_CACHE: dict = {"key": None, "data": None, "roles": None}


# ---- the package's data ----

def _data(conn: sqlite3.Connection) -> dict:
    """outfits.json `happenings` (read once per database); {} when the package has none."""
    key = org_motives.db_key(conn)
    if _CACHE["key"] != key:
        _CACHE.update(key=key, data=org_motives._sphere_data(conn).get("happenings") or {}, roles=None)
    return _CACHE["data"]


def _dependent_roles(conn: sqlite3.Connection) -> dict[str, str]:
    """org kind -> its dependent role (orgs.json kinds[k].opening.dependent_role)."""
    _data(conn)
    if _CACHE["roles"] is None:
        kinds = org_rules(package_for(conn)).get("kinds") or {}
        _CACHE["roles"] = {k: v["opening"]["dependent_role"] for k, v in kinds.items() if (v.get("opening") or {}).get("dependent_role")}
    return _CACHE["roles"]


def _v(conn, spec, default: float = 0.0) -> float:
    return org_motives._value(conn, spec, default)


def _kinds(conn: sqlite3.Connection) -> dict:
    return _data(conn).get("kinds") or {}


def group_of(conn: sqlite3.Connection) -> dict[str, str]:
    return {k: str(s["group"]) for k, s in _kinds(conn).items()}


def _name(conn: sqlite3.Connection, actor_id: int | None) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone() if actor_id is not None else None
    return str(r[0]) if r else "someone"


def _rng(conn: sqlite3.Connection, stream: str, actor: int, day: int) -> random.Random:
    return random.Random(f"{run_seed(conn)}:happening:{stream}:{int(actor)}:{int(day)}")


# ---- the man's place in his organisation ----

def _ctx(conn: sqlite3.Connection, actor_id: int):
    """(seat, org) for the first active seat in a dependent role of its organisation's kind; None otherwise."""
    roles = _dependent_roles(conn)
    for s in conn.execute("SELECT s.*,p.org_kind FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id WHERE s.actor_id=? AND s.status='active' "
                          "ORDER BY s.org_actor_id", (int(actor_id),)).fetchall():
        if roles.get(s["org_kind"]) == s["role_key"]:
            return s, int(s["org_actor_id"])
    return None


def _opening(conn: sqlite3.Connection, org: int) -> dict:
    return kind_rules(conn, org).get("opening") or {}


def _ratio(conn: sqlite3.Connection, org: int) -> float:
    key = conn.execute("SELECT package_key FROM org_profiles WHERE org_actor_id=?", (org,)).fetchone()[0]
    spec = ((org_motives._sphere_data(conn).get("outfits") or {}).get(key) or {})
    return float(figure(conn, spec["dependents_figure"])) if spec.get("dependents_figure") else 0.0


def _gain(conn: sqlite3.Connection, seat, delta: float) -> None:
    conn.execute("UPDATE org_seats SET standing=? WHERE id=?", (clamp01(float(seat["standing"]) + delta), int(seat["id"])))


def _refresh(conn: sqlite3.Connection, a: int, org: int):
    return seat_of(conn, a, org)


# ---- readers (registered under `hap_<kind>`) ----

def _drive(conn, a, trait):
    return om._drive(conn, a, trait)


def _r_ctx(fn):
    def reader(conn, actor, day):
        c = _ctx(conn, actor)
        return 0.0 if c is None else clamp01(fn(conn, actor, day, c[0], c[1]))
    return reader


def _unit_men(conn, seat, org):
    """(inducted members, dependants) in his unit."""
    if not seat["unit_id"]:
        return 0, 0
    rows = conn.execute("SELECT role_key,inducted_day FROM org_seats WHERE unit_id=? AND status='active'", (int(seat["unit_id"]),)).fetchall()
    return sum(1 for r in rows if r["inducted_day"] is not None), sum(1 for r in rows if r["role_key"] == seat["role_key"])


def _unit_short(conn, a, day, seat, org):
    men, deps = _unit_men(conn, seat, org)
    want = men * _ratio(conn, org)
    return 0.0 if want <= 0 else 1.0 - deps / want


def _other_members(conn, seat, org, day: int | None = None) -> list[int]:
    st = _day_state(conn, day)["readings"] if day is not None else {}
    k = ("others", org, seat["unit_id"])
    if k not in st:
        st[k] = [int(r[0]) for r in conn.execute(
            "SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND inducted_day IS NOT NULL AND COALESCE(unit_id,0)<>COALESCE(?,0) ORDER BY actor_id",
            (org, seat["unit_id"])) if is_living(conn, int(r[0]))]
    return st[k]


def _take_per_man(conn, patron: int, org: int, day: int | None = None) -> float:
    st = _day_state(conn, day)["readings"] if day is not None else {}
    k = ("take", int(patron), org)
    if k not in st:
        take = conn.execute("SELECT COALESCE(SUM(weekly_take),0) FROM org_lines WHERE holder_actor_id=? AND status='active'", (int(patron),)).fetchone()[0]
        deps = conn.execute("SELECT COUNT(*) FROM org_seats WHERE superior_actor_id=? AND org_actor_id=? AND status='active'", (int(patron), org)).fetchone()[0]
        st[k] = float(take) / (deps + 1)
    return st[k]


def _better_patron(conn, a, seat, org, day: int | None = None) -> tuple[int | None, float]:
    """The man of his patron's own role who offers more per man, and how much more (0..1)."""
    cur = seat["superior_actor_id"]
    if cur is None:
        return None, 0.0
    cur_seat = seat_of(conn, int(cur), org)
    if cur_seat is None:  # his patron is dead or gone and no one has taken the place yet: there is no patron to compare
        return None, 0.0
    role = cur_seat["role_key"]
    own = _take_per_man(conn, int(cur), org, day)
    best, gap = None, 0.0
    for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active' AND actor_id<>? ORDER BY actor_id", (org, role, int(cur))).fetchall():
        t = _take_per_man(conn, int(r[0]), org, day)
        g = (t - own) / t if t > 0 else 0.0
        if g > gap + 1e-12 and is_living(conn, int(r[0])):
            best, gap = int(r[0]), g
    return best, clamp01(gap)


def _arrested(conn, a, day) -> float:
    n = conn.execute("SELECT COUNT(*) FROM custody WHERE actor_id=? AND since_day>=?", (int(a), int(day) - int(org_motives._fig(conn, "motive_recent_days", default=90)))).fetchone()[0]
    return 1.0 if n else 0.0


def _open_case(conn, a, day) -> float:
    return 1.0 if conn.execute("SELECT 1 FROM crime_reports WHERE offender_actor_id=? AND status='open' LIMIT 1", (int(a),)).fetchone() else 0.0


def _kin_tie(conn, a, day) -> float:
    return 1.0 if conn.execute("SELECT 1 FROM typed_relationship_facts WHERE status='active' AND relation_type='spouse' AND (actor_a_id=? OR actor_b_id=?) LIMIT 1",
                               (int(a), int(a))).fetchone() else 0.0


def _age_late(conn, a, day) -> float:
    age = om._age(conn, a, day)
    return 0.0 if age is None else clamp01((age - float(figure(conn, "hap_age_from", default=35))) / float(figure(conn, "hap_age_span", default=25)))


def _resentment(conn, a, day, seat, org) -> float:
    r = om._rel(conn, a, seat["superior_actor_id"])
    return 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0)


_DAY: dict = {"key": None, "memo": {}, "readings": {}}


def forget_readings() -> None:
    """Drop the day's shared readings (for tests that change a man's situation between readings on one day)."""
    _DAY.update(key=None, memo={}, readings={})


def _day_state(conn: sqlite3.Connection, day: int) -> dict:
    """What every man's reading shares on one day: the places' and pools' opportunity memo and each man's readings."""
    key = (org_motives.db_key(conn), int(day))
    if _DAY["key"] != key:
        _DAY.update(key=key, memo={}, readings={})
    return _DAY


def _ground(kind: str):
    def reader(conn, actor, day):
        c = _ctx(conn, actor)
        if c is None:
            return 0.0
        st = _day_state(conn, day)
        k = ("ground", kind, c[0]["unit_id"], c[1])  # the same for every man of a unit: the places, pools and weights are his unit's
        if k not in st["readings"]:
            pools = (_kinds(conn).get(kind) or {}).get("pools") or []
            st["readings"][k] = max((om.opportunity(conn, actor, day, loc, p, st["memo"]) for loc in om._places(conn, c[0]) for p in pools), default=0.0)
        return st["readings"][k]
    return reader


def _low_heat(conn, a, day, seat, org) -> float:
    """`outfit_motives.low_heat` (his precinct is paid and no open case names him), the precinct part worked out once per unit."""
    st = _day_state(conn, day)
    k = ("paid", org, seat["unit_id"])
    if k not in st["readings"]:
        places = om._places(conn, seat)
        precinct = om.precinct_for_location(conn, places[0]) if places else None
        st["readings"][k] = precinct is not None and conn.execute(
            "SELECT 1 FROM org_arrangements WHERE payer_kind='org' AND payer_id=? AND status='active' AND position_key LIKE ? LIMIT 1", (org, f"{precinct}:%")).fetchone() is not None
    return 1.0 if st["readings"][k] and not _open_case(conn, a, day) else 0.0


def _simple(fn):
    return lambda conn, actor, day: clamp01(fn(conn, actor, day))


_READER_FACTORIES = {
    "ambition": lambda k: _simple(lambda c, a, d: _drive(c, a, "ambition")),
    "boldness": lambda k: _simple(lambda c, a, d: _drive(c, a, "risk_tolerance")),
    "temper": lambda k: _simple(lambda c, a, d: _drive(c, a, "aggression")),
    "loyal": lambda k: _simple(lambda c, a, d: _drive(c, a, "loyalty")),
    "disloyal": lambda k: _simple(lambda c, a, d: 1.0 - _drive(c, a, "loyalty")),
    "lazy": lambda k: _simple(lambda c, a, d: 1.0 - _drive(c, a, "ambition")),
    "greed": lambda k: _r_ctx(lambda c, a, d, s, o: float(s["greed"])),
    "reliable": lambda k: _r_ctx(lambda c, a, d, s, o: float(s["reliability"])),
    "need": lambda k: om.need,
    "appetite": lambda k: om.appetite,
    "low_heat": lambda k: _r_ctx(lambda c, a, d, s, o: _low_heat(c, a, d, s, o)),
    "no_cover": lambda k: _r_ctx(lambda c, a, d, s, o: 1.0 - _low_heat(c, a, d, s, o)),
    "ground": _ground,
    "age_late": lambda k: _simple(_age_late),
    "kin_tie": lambda k: _simple(_kin_tie),
    "arrested": lambda k: _simple(_arrested),
    "open_case": lambda k: _simple(_open_case),
    "resentful": lambda k: _r_ctx(_resentment),
    "unit_short": lambda k: _r_ctx(_unit_short),
    "other_member": lambda k: _r_ctx(lambda c, a, d, s, o: 1.0 if _other_members(c, s, o, d) else 0.0),
    "better_offer": lambda k: _r_ctx(lambda c, a, d, s, o: _better_patron(c, a, s, o, d)[1]),
}
_REGISTERED: set = set()


def _cached(name: str, fn):
    """A reading of a man on a day is worked out once however many kinds use it."""
    def reader(conn, actor, day):
        r = _day_state(conn, day)["readings"]
        k = (int(actor), name)
        if k not in r:
            r[k] = fn(conn, actor, day)
        return r[k]
    return reader


def _ensure_readers(conn: sqlite3.Connection) -> None:
    for kind, spec in _kinds(conn).items():
        names = [m["name"] for m in (org_motives._sphere_data(conn).get("motives") or {}).get(f"hap_{kind}", [])] + list(spec.get("requires") or [])
        for n in names:
            if (kind, n) not in _REGISTERED and n in _READER_FACTORIES:
                org_motives.register_motive(f"hap_{kind}", n, _cached(n if n != "ground" else f"ground:{kind}", _READER_FACTORIES[n](kind)))
                _REGISTERED.add((kind, n))


def kind_weights(conn: sqlite3.Connection, actor_id: int, day: int) -> dict[str, float]:
    """Each kind's weight for this man today: base * (floor + pressure), 0 when a required reader reads 0."""
    _ensure_readers(conn)
    out: dict[str, float] = {}
    for kind, spec in _kinds(conn).items():
        if any((org_motives._READERS.get((f"hap_{kind}", r)) or (lambda *_: 0.0))(conn, int(actor_id), int(day)) <= 0.0 for r in spec.get("requires") or []):
            out[kind] = 0.0
            continue
        p, _ = org_motives.pressure(conn, int(actor_id), int(day), f"hap_{kind}")
        out[kind] = _v(conn, spec["weight"]) * (float(spec.get("floor", 0.5)) + p)
    return out


def draw_kind(conn: sqlite3.Connection, actor_id: int, day: int) -> str | None:
    w = kind_weights(conn, actor_id, day)
    total = sum(w.values())
    if total <= 0:
        return None
    pick = _rng(conn, "kind", actor_id, day).random() * total
    for k in sorted(w):
        pick -= w[k]
        if pick < 0:
            return k
    return sorted(w)[-1]


# ---- records ----

def _record(conn, day, kind, offender, *, victim=None, line=None, loc=None, matters=0, raised=None, status="done", **meta) -> int:
    return int(conn.execute(
        """INSERT INTO org_incidents(day,kind,offender_actor_id,victim_actor_id,victim_line_id,location_id,matters,raised_to_org_actor_id,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (int(day), kind, int(offender), victim, line, loc, int(matters), raised, status, json.dumps(meta, sort_keys=True, default=str))).lastrowid)


def _ground_of(conn, seat):
    r = conn.execute("SELECT ground_location_id FROM org_units WHERE id=?", (seat["unit_id"],)).fetchone() if seat["unit_id"] else None
    return None if r is None else r[0]


def _pass_up(conn, a, org, seat, amount: float, day: int, purpose: str) -> float:
    sup = seat["superior_actor_id"]
    flows = org_motives.upward_flows(conn)
    if sup is None or amount <= 0:
        return 0.0
    paid = ledger.transfer(conn, ("person", int(a)), ("person", int(sup)), amount, flow_kind="tribute", purpose=purpose, allow_partial=True)
    if paid > 0 and flows:
        conn.execute("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,amount,org_actor_id) VALUES (?,?,?,?,?,?)", (int(day), flows[0], int(a), int(sup), paid, org))
    return paid


def _span(conn, lo_key: str, hi_key: str, rng: random.Random) -> float:
    lo, hi = float(figure(conn, lo_key)), float(figure(conn, hi_key))
    return lo + (hi - lo) * rng.random()


# ---- good ----

def _do_score(conn, a, seat, org, day, rng, spec, **o):
    amt = round(_span(conn, spec["take"][0], spec["take"][1], rng), 2)
    ledger.receive(conn, ("person", a), amt, purpose="a score")
    up = _pass_up(conn, a, org, seat, amt * float(figure(conn, spec["up_share"])), day, "a score kicked up")
    _gain(conn, seat, float(figure(conn, spec["standing"])))
    return {"take": amt, "kicked_up": up, "summary": f"{_name(conn, a)} made a score of ${amt:,.0f}."}


def _small_line(conn, a, seat, org, day, pool, weekly, counterpart, loc) -> int:
    from . import outfit_money
    total = float((outfit_money.design_pools(conn).get(pool) or {}).get("default_m") or 0.0) * 1_000_000.0
    holding = conn.execute("INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,source,started_day) VALUES (?,?,?,?,'started',?)",
                           (org, pool, round(100.0 * weekly * 52.0 / total, 4) if total > 0 else 0.0, weekly * 52.0, int(day))).lastrowid
    under = org_motives._sphere_data(conn).get("under_patron") or []
    holder = int(seat["superior_actor_id"]) if seat["role_key"] in under and seat["superior_actor_id"] else int(a)
    label = (org_motives._sphere_data(conn).get("line_kinds") or {}).get(pool, pool)
    place = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()[0] if loc else "the ground"
    who = f" through {_name(conn, counterpart)}" if counterpart else ""
    line = int(conn.execute(
        "INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,location_id,weekly_take,hidden,started_day) VALUES (?,?,?,?,?,?,0,?)",
        (holding, seat["unit_id"], holder, f"{label} in {place}{who}", loc, weekly, int(day))).lastrowid)
    from . import org_tension
    org_tension.on_line_opened(conn, org, loc, a, int(day))
    return line


def _do_bring_earner(conn, a, seat, org, day, rng, spec, **o):
    pool = rng.choice(list(spec["pools"]))
    got, new_person = _taken(conn, a, "bring_earner", seat, org, day, spec, o)
    cp = got[0] if got else None
    weekly = float(figure(conn, spec["weekly"])) * (0.5 + rng.random())
    line = _small_line(conn, a, seat, org, day, pool, weekly, cp, _ground_of(conn, seat))
    if cp is not None and seat["superior_actor_id"] is not None:
        adjust_relationship(conn, int(seat["superior_actor_id"]), cp, int(day), familiarity_delta=10.0, trust_delta=5.0)
    _gain(conn, seat, float(figure(conn, spec["standing"])))
    return {"counterpart": cp, "line_id": line, "pool": pool, "weekly": weekly, "meta": {"counterpart": cp, "new_person": bool(new_person and cp is not None)},
            "summary": f"{_name(conn, a)} brought a new line ({pool}) under {_name(conn, seat['superior_actor_id'])}."}


def _do_proves_himself(conn, a, seat, org, day, rng, spec, **o):
    _gain(conn, seat, float(figure(conn, spec["standing"])))
    if seat["superior_actor_id"] is not None:
        adjust_relationship(conn, int(seat["superior_actor_id"]), a, int(day), trust_delta=float(figure(conn, spec["trust"])),
                            respect_delta=float(figure(conn, spec["trust"])) / 2.0)
    return {"summary": f"{_name(conn, a)} did a job cleanly."}


def _recruit_request(conn, a, seat, org, day, spec) -> tuple:
    """(name group, sex, ages, subtype, criminal weight) of the man he would bring in, from the run seed."""
    from .outfit_opening import seat_subtype
    rng = _rng(conn, "recruit_params", a, day)
    op = _opening(conn, org)
    spec_o = (op.get("roles") or {}).get(seat["role_key"]) or {}
    male = float((org_motives._sphere_data(conn).get("male_share") or {}).get(spec_o.get("male_share_key"), 1.0))
    key = conn.execute("SELECT package_key FROM org_profiles WHERE org_actor_id=?", (org,)).fetchone()[0]
    ospec = (org_motives._sphere_data(conn).get("outfits") or {}).get(key) or {}
    inst = conn.execute("SELECT name FROM actors WHERE id=?", (org,)).fetchone()[0]
    group = ospec.get("name_group") if rng.random() < float(op.get("own_group_share", 1.0)) else None
    return (group, "male" if rng.random() < male else "female", tuple(int(x) for x in spec["ages"]),
            seat_subtype(seat["role_key"], inst, op.get("in_roles") or ()), float(spec_o.get("criminal_weight", 1.0)))


def _bring_request(conn, a, seat, org, day, spec) -> tuple:
    return (None, None, tuple(int(x) for x in spec["counterpart_ages"]), spec.get("counterpart_subtype"), 0.0)


_REQUESTS = {"recruits": _recruit_request, "bring_earner": _bring_request}


def _pull(conn, req: tuple, n: int, stream: str) -> list[int]:
    from .outfit_opening import pull_up
    group, sex, ages, subtype, cw = req
    return pull_up(conn, n, stream=stream, name_group=group, sex=sex, ages=ages, subtype=subtype, criminal_weight=cw)


def _counterparts_used(conn: sqlite3.Connection) -> set[int]:
    return {int(r[0]) for r in conn.execute("SELECT json_extract(metadata_json,'$.counterpart') FROM org_incidents WHERE kind='bring_earner'") if r[0] is not None}


def _nearby(conn, a, seat, day, spec, rng, used: set[int]) -> int | None:
    """An existing person who fits the counterpart (living, in the age band, not seated anywhere, not already a line's
    counterpart) in his unit's places or the city itself, or None."""
    from .outfit_opening import city_location
    places = list(dict.fromkeys([*om._places(conn, seat), city_location(conn)]))
    lo, hi = (int(x) for x in spec["counterpart_ages"])
    rows = conn.execute(
        "SELECT a.id,lp.birth_day FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.actor_type='character' AND a.status='active' "
        "AND COALESCE(lp.life_status,'living')='living' AND a.current_location_id IN (%s) AND lp.birth_day BETWEEN ? AND ? "
        "AND a.id NOT IN (SELECT actor_id FROM org_seats) ORDER BY a.id" % ",".join("?" * len(places)),
        (*places, int(day) - hi * 365, int(day) - lo * 365)).fetchall()
    fit = [int(r[0]) for r in rows if int(r[0]) not in used and not conn.execute(
        "SELECT 1 FROM typed_relationship_facts WHERE status='active' AND relation_type IN ('spouse','parent_of','child_of','sibling_of') AND (actor_a_id=? OR actor_b_id=?) "
        "AND (actor_a_id=? OR actor_b_id=?) LIMIT 1", (int(r[0]), int(r[0]), int(a), int(a))).fetchone()]
    return fit[rng.randrange(len(fit))] if fit else None


def _taken(conn, a, kind, seat, org, day, spec, o) -> tuple[list[int], bool]:
    """(who was brought for this man, whether he is a new person): from the weekly batch when there is one, otherwise
    an existing counterpart where one fits (bring_earner), otherwise one pulled up on its own."""
    batch = o.get("pulled")
    if batch is not None and a in batch:
        return batch[a]
    if kind == "bring_earner":
        near = _nearby(conn, a, seat, day, spec, _rng(conn, "nearby", a, day), _counterparts_used(conn))
        if near is not None:
            return [near], False
    return _pull(conn, _REQUESTS[kind](conn, a, seat, org, day, spec), 1, f"happening:{kind}:{a}:{day}"), True


def _do_recruits(conn, a, seat, org, day, rng, spec, **o):
    from .orgs import seat as seat_up
    from .outfit_opening import feelings_toward
    op = _opening(conn, org)
    spec_o = (op.get("roles") or {}).get(seat["role_key"]) or {}
    got, _new = _taken(conn, a, "recruits", seat, org, day, spec, o)
    if not got:
        return {"summary": "There was no one to pull up.", "skipped": True}
    new = got[0]
    st = spec_o.get("standing") or {"mean": 0.3, "sd": 0.2}
    seat_up(conn, new, org, seat["role_key"], unit_id=seat["unit_id"], superior_actor_id=seat["superior_actor_id"], level=int(seat["level"]), day=int(day),
            standing=clamp01(rng.gauss(float(st["mean"]), float(st["sd"]))), provenance="happening")
    if seat["superior_actor_id"] is not None:
        feelings_toward(conn, new, int(seat["superior_actor_id"]), int(day), rng)
    adjust_relationship(conn, new, a, int(day), familiarity_delta=10.0, trust_delta=8.0)
    _gain(conn, seat, float(figure(conn, spec["standing"])))
    return {"recruit": new, "meta": {"recruit": new, "new_person": True}, "summary": f"{_name(conn, a)} brought in {_name(conn, new)}."}


def _do_favour(conn, a, seat, org, day, rng, spec, **o):
    others = _other_members(conn, seat, org)
    if not others:
        return {"summary": "There was no one to do a favour for.", "skipped": True}
    other = others[rng.randrange(len(others))]
    adjust_relationship(conn, other, a, int(day), trust_delta=float(figure(conn, spec["trust"])), obligation_delta=float(figure(conn, spec["trust"])))
    adjust_relationship(conn, a, other, int(day), respect_delta=float(figure(conn, spec["trust"])) / 2.0)
    _gain(conn, seat, float(figure(conn, spec["standing"])))
    return {"for_actor": other, "summary": f"{_name(conn, a)} did {_name(conn, other)} a favour."}


# ---- neutral ----

def _do_drifts(conn, a, seat, org, day, rng, spec, **o):
    _gain(conn, seat, -float(figure(conn, spec["standing"])))
    return {"summary": f"{_name(conn, a)} drifted: earning less."}


def _do_goes_straight(conn, a, seat, org, day, rng, spec, **o):
    leave_life(conn, a, org, int(day))  # the seat goes `out` with the day, his profile DORMANT; the weekly lifecycle notes the history
    return {"summary": f"{_name(conn, a)} went straight."}


def _do_switches(conn, a, seat, org, day, rng, spec, **o):
    old = seat["superior_actor_id"]
    new = o.get("to")
    if new is None:
        new, _ = _better_patron(conn, a, seat, org)
    if new is None or old is None:
        return {"summary": "There was no one to switch to.", "skipped": True}
    ns = seat_of(conn, int(new), org)
    conn.execute("UPDATE org_seats SET superior_actor_id=?, unit_id=? WHERE id=?", (int(new), ns["unit_id"], int(seat["id"])))
    adjust_relationship(conn, int(old), a, int(day), resentment_delta=float(figure(conn, spec["resentment"])))
    return {"to": int(new), "summary": f"{_name(conn, a)} went to {_name(conn, new)}, leaving {_name(conn, old)}."}


# ---- wrong ----

def _victim_other_line(conn, a, seat, org, day, rng, spec):
    places = om._places(conn, seat)
    if not places:
        return None
    rows = conn.execute(
        "SELECT l.id,l.holder_actor_id,l.location_id,h.org_actor_id FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id "
        "WHERE h.org_actor_id<>? AND l.status='active' AND l.holder_actor_id IS NOT NULL AND l.location_id IN (%s) ORDER BY l.id" % ",".join("?" * len(places)),
        (org, *places)).fetchall()
    rows = [r for r in rows if is_living(conn, int(r[1]))]
    if not rows:
        return None
    r = rows[rng.randrange(len(rows))]
    return {"victim": int(r[1]), "line": int(r[0]), "loc": r[2], "org": int(r[3])}


def _seat_org(conn, actor, exclude):
    r = conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active' AND org_actor_id<>? ORDER BY org_actor_id LIMIT 1", (int(actor), exclude)).fetchone()
    return None if r is None else int(r[0])


def _victim_member(conn, a, seat, org, day, rng, spec):
    rows = [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id<>? AND status='active' AND inducted_day IS NOT NULL ORDER BY actor_id", (org,)) if is_living(conn, int(r[0]))]
    if not rows:
        return None
    v = rows[rng.randrange(len(rows))]
    return {"victim": v, "line": None, "loc": conn.execute("SELECT current_location_id FROM actors WHERE id=?", (v,)).fetchone()[0], "org": _seat_org(conn, v, org)}


def _victim_big_earner(conn, a, seat, org, day, rng, spec):
    big = float(figure(conn, spec["big_weekly"]))
    rows = conn.execute("SELECT l.id,l.holder_actor_id,l.location_id,h.org_actor_id FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id "
                        "WHERE h.org_actor_id<>? AND l.status='active' AND l.holder_actor_id IS NOT NULL AND l.weekly_take>=? ORDER BY l.id", (org, big)).fetchall()
    rows = [r for r in rows if is_living(conn, int(r[1]))]
    if not rows:
        return None
    r = rows[rng.randrange(len(rows))]
    return {"victim": int(r[1]), "line": None, "loc": r[2], "org": int(r[3])}


def _victim_officer(conn, a, seat, org, day, rng, spec):
    rows = [int(r[0]) for r in conn.execute("SELECT DISTINCT official_actor_id FROM org_arrangements WHERE status='active' ORDER BY official_actor_id") if is_living(conn, int(r[0]))]
    if not rows:
        return None
    v = rows[rng.randrange(len(rows))]
    return {"victim": v, "line": None, "loc": conn.execute("SELECT current_location_id FROM actors WHERE id=?", (v,)).fetchone()[0], "org": None}


def _victim_civilian(conn, a, seat, org, day, rng, spec):
    n = conn.execute("SELECT COUNT(*) FROM actors WHERE actor_type='character' AND status='active' AND id NOT IN (SELECT actor_id FROM org_seats)").fetchone()[0]
    if not n:
        return None
    r = conn.execute("SELECT id,current_location_id FROM actors WHERE actor_type='character' AND status='active' AND id NOT IN (SELECT actor_id FROM org_seats) "
                     "ORDER BY id LIMIT 1 OFFSET ?", (rng.randrange(n),)).fetchone()
    return {"victim": int(r[0]), "line": None, "loc": r[1], "org": None} if is_living(conn, int(r[0])) else None


_VICTIMS = {"other_line": _victim_other_line, "member": _victim_member, "big_earner": _victim_big_earner,
            "officer": _victim_officer, "civilian": _victim_civilian}


def _do_incident(conn, a, seat, org, day, rng, spec, victim_kind=None, **o):
    weights = {k: _v(conn, w) for k, w in (spec.get("victims") or {}).items()}
    if victim_kind is not None:
        weights = {victim_kind: 1.0}
    found: dict[str, dict] = {}
    for k in sorted(weights):
        if weights[k] > 0 and k in _VICTIMS:
            hit = _VICTIMS[k](conn, a, seat, org, day, rng, spec)
            if hit is not None:
                found[k] = hit
    if not found:
        return {"summary": "There was no one to hit.", "skipped": True}
    tot = sum(weights[k] for k in found)
    pick, chosen = rng.random() * tot, sorted(found)[-1]
    for k in sorted(found):
        pick -= weights[k]
        if pick < 0:
            chosen = k
            break
    return _apply_incident(conn, a, org, day, rng, spec, found[chosen], chosen)


def run_incident(conn, a: int, org: int, day: int, rng, victim: int, victim_org: int | None, kind: str = "squeeze") -> dict:
    """An incident aimed by the tension model: man `a` of `org` hurts `victim` (of `victim_org`); the same harm, record and answer as the weekly one."""
    spec = _kinds(conn).get("incident") or {}
    line = conn.execute("SELECT l.id,l.location_id FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE l.holder_actor_id=? AND l.status='active' "
                        "AND (? IS NULL OR h.org_actor_id=?) ORDER BY l.weekly_take DESC,l.id LIMIT 1", (int(victim), victim_org, victim_org)).fetchone()
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(victim),)).fetchone()
    hit = {"victim": int(victim), "line": line[0] if line else None, "loc": (loc[0] if loc and loc[0] is not None else (line[1] if line else None)), "org": victim_org}
    return _apply_incident(conn, int(a), int(org), int(day), rng, spec, hit, kind)


def _apply_incident(conn, a, org, day, rng, spec, hit, chosen) -> dict:
    v = hit["victim"]
    matters = 0 if chosen == "civilian" else 1
    raised = hit["org"] if matters and hit["org"] is not None else None
    iid = _record(conn, day, "incident", a, victim=v, line=hit["line"], loc=hit["loc"], matters=matters, raised=raised,
                  status="open" if raised is not None else "done", victim_kind=chosen, offender_org=org)
    from . import lethality, org_tension
    from .harm import record_harm
    vseats = conn.execute("SELECT org_actor_id,role_key,unit_id,superior_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (v,)).fetchall()
    key = conn.execute("SELECT package_key FROM org_profiles WHERE org_actor_id=?", (org,)).fetchone()
    key = key[0] if key else None
    sev, method, too_far = lethality.incident_roll(conn, key, _span(conn, spec["harm"][0], spec["harm"][1], rng), rng)
    harm = record_harm(conn, v, source_kind="org_incident", source_ref_id=iid, severity=round(sev, 2), intent_class="hostile", method=method,
                       location_id=hit["loc"], metadata={"offender_actor_id": a, "public": chosen == "officer", "went_too_far": too_far})
    if matters:
        org_tension.on_incident(conn, raised, org, a, v, chosen, int(day), too_far)
    by_sev = lethality.bystander_hurt(conn, key, method, rng) if too_far else None
    bystander = None
    if by_sev is not None:
        near = [int(r[0]) for r in conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' AND current_location_id IS ? AND id NOT IN (?,?) ORDER BY id",
                                                 (hit["loc"], a, v)) if is_living(conn, int(r[0]))]
        if near:
            bystander = near[rng.randrange(len(near))]
            record_harm(conn, bystander, source_kind="org_incident_bystander", source_ref_id=iid, severity=round(by_sev, 2), intent_class="accidental",
                        method=method, location_id=hit["loc"], metadata={"offender_actor_id": a, "public": True})
            imposed(conn, bystander)
    imposed(conn, a)
    if harm["outcome"] != "fatal":
        imposed(conn, v)
    if harm["outcome"] == "fatal" and matters:
        # a beating that went too far is a killing: the dead man's head answers a killing, not an incident
        conn.execute("UPDATE org_incidents SET status='done' WHERE id=?", (iid,))
        killed_across(conn, a, v, vseats, int(day))
    elif raised is not None:
        head = head_of(conn, raised)
        if head is not None and head != a:
            add_agenda(conn, head, "respond_incident", int(day) + int(figure(conn, spec["respond_delay"])), subject_kind="incident", subject_id=iid,
                       metadata={"incident": iid, "offender": a, "offender_org": org, "victim": v, "org": raised, "kind": "incident"})
    return {"incident_id": iid, "victim": v, "victim_kind": chosen, "matters": matters, "harm": harm["outcome"], "bystander": bystander,
            "summary": f"{_name(conn, a)} hit {_name(conn, v)} ({chosen}){' and killed him' if harm['outcome'] == 'fatal' else ''}."}


def _do_holds_out(conn, a, seat, org, day, rng, spec, **o):
    amt = round(_span(conn, spec["take"][0], spec["take"][1], rng), 2)
    ledger.receive(conn, ("person", a), amt, purpose="a collection kept back")
    return {"amount": amt, "meta": {"amount": amt}, "status": "open", "victim": seat["superior_actor_id"],
            "summary": f"{_name(conn, a)} kept ${amt:,.0f} back."}


def _do_busted(conn, a, seat, org, day, rng, spec, **o):
    days = int(round(_span(conn, spec["days"][0], spec["days"][1], rng)))
    conn.execute("INSERT INTO custody(actor_id,kind,charge,since_day,until_day) VALUES (?,'held',?,?,?)", (a, spec["charge"], int(day), int(day) + days))
    loc = _ground_of(conn, seat)
    conn.execute("INSERT INTO crime_reports(day,crime_kind,location_id,offender_actor_id,public,agency_profile_id,status,metadata_json) VALUES (?,?,?,?,0,?,'open',?)",
                 (int(day), spec["crime_kind"], loc, a, agency_for(conn, loc, spec["crime_kind"]), json.dumps({"source": "org_happening", "close_day": int(day) + days})))
    imposed(conn, a)
    mark_for_history(conn, a, "was arrested", int(day))
    return {"status": "done", "loc": loc, "summary": f"{_name(conn, a)} was picked up."}


def _do_informs(conn, a, seat, org, day, rng, spec, **o):
    sup = seat["superior_actor_id"]
    if sup is None:
        return {"summary": "He had no one to inform on.", "skipped": True}
    loc = _ground_of(conn, seat)
    from .crime_response import open_report  # an informant names the man: the law has a case it can work, and the evidence builds like any other
    open_report(conn, crime_kind=spec["crime_kind"], day=int(day), offender_actor_id=int(sup), location_id=loc,
                metadata={"source": "org_happening", "informant": a, "discovered": 0, "identified": True,
                          "close_day": int(day) + int(figure(conn, spec["report_days"]))})
    return {"status": "open", "victim": int(sup), "loc": loc, "summary": f"{_name(conn, a)} gave the police evidence on {_name(conn, sup)}."}


_DO = {"score": _do_score, "bring_earner": _do_bring_earner, "proves_himself": _do_proves_himself, "recruits": _do_recruits, "favour": _do_favour,
       "drifts": _do_drifts, "goes_straight": _do_goes_straight, "switches": _do_switches, "incident": _do_incident, "holds_out": _do_holds_out,
       "busted": _do_busted, "informs": _do_informs}


def happen(conn: sqlite3.Connection, actor_id: int, kind: str, day: int, **opts) -> dict | None:
    """Carry out one happening for a man (the weekly draw, or a test forcing a kind). Returns {kind, group, summary, incident_id, ...}."""
    spec = _kinds(conn).get(kind)
    c = _ctx(conn, int(actor_id))
    if spec is None or c is None or kind not in _DO:
        return None
    seat, org = c
    rng = _rng(conn, f"do:{kind}", actor_id, day)
    if "pulled" in opts:
        opts = {**opts, "pulled": (opts["pulled"] or {}).get(kind)}
    res = _DO[kind](conn, int(actor_id), seat, org, int(day), rng, spec, **opts) or {}
    res.update(kind=kind, group=spec["group"])
    if "incident_id" not in res and not res.get("skipped"):
        res["incident_id"] = _record(conn, day, kind, actor_id, victim=res.get("victim"), loc=res.get("loc"), status=res.get("status", "done"),
                                     group=spec["group"], summary=res.get("summary"), **{k: v for k, v in (res.get("meta") or {}).items()})
    return res


# ---- the weekly check-ups (a man kept money back; a report names his patron; a short arrest ends) ----

def _roll(conn, stream: str, key: int, day: int) -> float:
    return random.Random(f"{run_seed(conn)}:happening:{stream}:{int(key)}:{int(day)}").random()


def notice_holdouts(conn: sqlite3.Connection, day: int) -> int:
    spec = _kinds(conn).get("holds_out") or {}
    n = 0
    for r in conn.execute("SELECT * FROM org_incidents WHERE kind='holds_out' AND status='open' ORDER BY id").fetchall():
        a, sup = int(r["offender_actor_id"]), r["victim_actor_id"]
        if not is_living(conn, a):
            conn.execute("UPDATE org_incidents SET status='lapsed' WHERE id=?", (r["id"],))
            continue
        if _roll(conn, "notice", r["id"], day) >= float(figure(conn, spec["notice_week"])):
            continue
        amt = float(json.loads(r["metadata_json"]).get("amount") or 0.0)
        back = ledger.transfer(conn, ("person", a), ("person", int(sup)), min(amt, ledger.balance(conn, ("person", a))), flow_kind="tribute",
                               purpose="what he kept back", allow_partial=True) if sup is not None and amt > 0 and ledger.balance(conn, ("person", a)) > 0 else 0.0
        c = _ctx(conn, a)
        if c is not None:
            _gain(conn, c[0], -float(figure(conn, spec["standing"])))
        if sup is not None:
            adjust_relationship(conn, int(sup), a, int(day), resentment_delta=float(figure(conn, spec["resentment"])), trust_delta=-float(figure(conn, spec["resentment"])))
        conn.execute("UPDATE org_incidents SET status='noticed' WHERE id=?", (r["id"],))
        imposed(conn, a)  # his patron has found out: he is looked at tomorrow
        if c is not None:  # and the man who decides about him (his patron) gets `discipline` about him
            from .org_membership import discipline_for_holdout
            discipline_for_holdout(conn, a, int(c[0]["org_actor_id"]), amt, int(r["day"]), int(r["id"]), int(day))
        n += 1
    return n


def discover_informers(conn: sqlite3.Connection, day: int, force: bool = False) -> int:
    spec = _kinds(conn).get("informs") or {}
    n = 0
    for r in conn.execute("SELECT id,offender_actor_id,metadata_json FROM crime_reports WHERE status IN ('open','buried','arrest') AND json_extract(metadata_json,'$.informant') IS NOT NULL "
                          "AND COALESCE(json_extract(metadata_json,'$.discovered'),0)=0 ORDER BY id").fetchall():
        if not force and _roll(conn, "discover", r["id"], day) >= float(figure(conn, spec["discover_week"])):
            continue
        meta = json.loads(r["metadata_json"])
        meta["discovered"] = 1
        conn.execute("UPDATE crime_reports SET metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), r["id"]))
        inf, sup = int(meta["informant"]), int(r["offender_actor_id"])
        c = _ctx(conn, inf)
        org = c[1] if c else _seat_org(conn, inf, -1)
        imposed(conn, sup)  # the superior the evidence names
        imposed(conn, inf)
        inc = conn.execute("SELECT id FROM org_incidents WHERE kind='informs' AND offender_actor_id=? AND status='open' ORDER BY id DESC LIMIT 1", (inf,)).fetchone()
        if inc is not None and org is not None:
            conn.execute("UPDATE org_incidents SET matters=1, raised_to_org_actor_id=? WHERE id=?", (org, inc[0]))
            head = head_of(conn, org)
            if head is not None:
                add_agenda(conn, head, "respond_incident", int(day) + int(figure(conn, spec["respond_delay"])), subject_kind="incident", subject_id=int(inc[0]),
                           metadata={"incident": int(inc[0]), "offender": inf, "offender_org": org, "victim": sup, "org": org, "kind": "informs"})
        n += 1
    return n


def close_old(conn: sqlite3.Connection, day: int) -> None:
    """A short arrest ends; a report this layer opened closes when its time is up."""
    from . import org_temperament
    for (a,) in conn.execute("SELECT actor_id FROM custody WHERE kind='held' AND until_day IS NOT NULL AND until_day<=? AND case_id IS NULL AND agency_profile_id IS NULL ORDER BY actor_id", (int(day),)).fetchall():
        org_temperament.drift(conn, int(a), "prison", int(day))
    conn.execute("UPDATE custody SET kind='released' WHERE kind='held' AND until_day IS NOT NULL AND until_day<=? AND case_id IS NULL AND agency_profile_id IS NULL", (int(day),))
    conn.execute("UPDATE crime_reports SET status='closed' WHERE status='open' AND json_extract(metadata_json,'$.source')='org_happening' "
                 "AND json_extract(metadata_json,'$.close_day')<=?", (int(day),))


# ---- the weekly process ----

def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    if not _kinds(conn):
        return None
    due = (int(after_day) // WEEK + 1) * WEEK
    return due if due <= int(end_day) else None


def _roster(conn: sqlite3.Connection) -> list[int]:
    roles = _dependent_roles(conn)
    if not roles:
        return []
    out: list[int] = []
    for kind, role in sorted(roles.items()):
        for r in conn.execute(
                """SELECT s.actor_id FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id JOIN actors a ON a.id=s.actor_id
                   LEFT JOIN actor_life_profiles lp ON lp.actor_id=s.actor_id
                   WHERE p.org_kind=? AND s.role_key=? AND s.status='active' AND COALESCE(lp.life_status,'living')='living'
                     AND lower(COALESCE(a.status,'active')) NOT IN ('dead','deceased','historical')
                     AND NOT EXISTS (SELECT 1 FROM custody c WHERE c.actor_id=s.actor_id AND c.kind='held')
                   ORDER BY s.actor_id""", (kind, role)):
            out.append(int(r[0]))
    return sorted(set(out))


def _pull_batches(conn: sqlite3.Connection, plan: list[tuple[int, str]], day: int) -> dict[str, dict[int, tuple[list[int], bool]]]:
    """The people this week's happenings pull up, one batch per kind of request (each pull-up scans the city's
    candidates once however many it is asked for): {kind: {man: [pulled ids]}}."""
    out: dict = {}
    for kind, fn in _REQUESTS.items():
        spec = _kinds(conn).get(kind)
        groups: dict[tuple, list[int]] = {}
        used = _counterparts_used(conn) if kind == "bring_earner" else set()
        for a, k in plan:
            c = _ctx(conn, a) if k == kind else None
            if c is None:
                continue
            if kind == "bring_earner":  # an existing person where one fits; a new one only when none does
                near = _nearby(conn, a, c[0], day, spec, _rng(conn, "nearby", a, day), used)
                if near is not None:
                    used.add(near)
                    out.setdefault(kind, {})[a] = ([near], False)
                    continue
            groups.setdefault(fn(conn, a, c[0], c[1], day, spec), []).append(a)
        for i, (req, men) in enumerate(sorted(groups.items(), key=lambda kv: repr(kv[0]))):
            ids = _pull(conn, req, len(men), f"happening:{kind}:{day}:{i}")
            for j, m in enumerate(men):
                out.setdefault(kind, {})[m] = ([ids[j]] if j < len(ids) else [], True)
    return out


def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None, only_checks: bool = False) -> dict:
    data = _data(conn)
    if not data.get("kinds"):
        return {}
    out: dict = {}
    close_old(conn, day)
    out["noticed"] = notice_holdouts(conn, day)
    out["discovered"] = discover_informers(conn, day)
    if only_checks:
        return out
    rate = _v(conn, data["week_rate"])
    plan: list[tuple[int, str]] = []
    for a in _roster(conn):
        if org_motives._roll(conn, a, int(day), "happening") >= rate:  # the one point where a man's seeded draw is made (tests patch it)
            continue
        kind = draw_kind(conn, a, int(day))
        if kind is not None:
            plan.append((a, kind))
    pulled = _pull_batches(conn, plan, int(day))
    for a, kind in plan:
        res = happen(conn, a, kind, int(day), pulled=pulled)
        if res and not res.get("skipped"):
            out[kind] = out.get(kind, 0) + 1
    from . import org_temperament, org_tension
    for act, n in org_tension.process_due(conn, int(day)).items():
        out[f"tension:{act}"] = n
    from . import org_council, org_dealings, org_informing
    for mod in (org_council, org_dealings, org_informing):
        out.update(mod.process_due(conn, int(day)))
    if int(day) // WEEK % 52 == 0:
        org_temperament.age_year(conn, int(day))
    return out


# ---- the heads' agenda: respond_incident, pay_or_refuse ----

def _utility(conn: sqlite3.Connection, x: float) -> float:
    return float(figure(conn, "org_choice_utility_base", default=8.0)) + float(figure(conn, "org_choice_utility_span", default=10.0)) * clamp01(x)


def _carry(payload: dict) -> dict:
    """What a new agenda item takes over from the one just answered: not its agenda id (the provider sets the new item's own)."""
    return {k: v for k, v in payload.items() if k != "agenda_id"}


def _finish(conn, payload, day, status: str | None = None) -> None:
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))
    if status and payload.get("incident_id") is not None:
        conn.execute("UPDATE org_incidents SET status=? WHERE id=?", (status, int(payload["incident_id"])))


def respond_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = json.loads(item["metadata_json"] or "{}")
    spec = _kinds(conn).get(meta.get("kind") or "incident") or {}
    allowed = spec.get("responses") or ["sit_down", "kill_offender", "let_it_go"]
    off = int(meta["offender"])
    if not is_living(conn, off):
        return [{"kind": "let_it_go", "utility": _utility(conn, 1.0), "rationale": "The man is already dead.", "payload": {**meta, "incident_id": meta["incident"]}}]
    aggr = om._drive(conn, actor_id, "aggression")
    ohead = head_of(conn, int(meta["offender_org"])) if meta.get("offender_org") else None
    xs = {"sit_down": float(figure(conn, "hap_resp_sit")) if ohead not in (None, actor_id) else 0.0,
          "kill_offender": float(figure(conn, "hap_resp_kill")) * (0.25 + aggr),
          "let_it_go": float(figure(conn, "hap_resp_let")) * (1.25 - aggr)}
    payload = {**meta, "incident_id": int(meta["incident"])}
    why = {"sit_down": f"Asks {_name(conn, ohead)} to sit down over {_name(conn, off)}.", "kill_offender": f"Has {_name(conn, off)} dealt with.",
           "let_it_go": f"Lets what {_name(conn, off)} did go."}
    return [{"kind": k, "utility": _utility(conn, xs[k]), "rationale": why[k], "payload": payload, **({"target_actor_id": off} if k == "kill_offender" else {})}
            for k in allowed if xs.get(k, 0.0) > 0.0]


def execute_sit_down(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day, "sat_down")
    ohead = head_of(conn, int(payload["offender_org"]))
    if ohead is None or ohead == int(actor_id):
        return {"summary": "There was no one to sit down with.", "blocked": True}
    spec = _kinds(conn).get("incident") or {}
    weeks = int(round(_span(conn, "hap_pay_weeks_lo", "hap_pay_weeks_hi", _rng(conn, "weeks", payload["incident_id"], day))))
    add_agenda(conn, ohead, "pay_or_refuse", int(day) + int(figure(conn, spec.get("respond_delay", "hap_respond_delay"))), subject_kind="incident",
               subject_id=int(payload["incident_id"]), metadata={**_carry(payload), "from": int(actor_id), "weeks": weeks})
    imposed(conn, ohead)  # the demand lands on him
    adjust_relationship(conn, int(actor_id), ohead, int(day), familiarity_delta=5.0, respect_delta=float(figure(conn, "hap_resp_sit_respect")))
    return {"summary": f"{_name(conn, actor_id)} asked {_name(conn, ohead)} to sit down."}


def execute_kill_offender(conn, actor_id, kind, payload, day):
    from .outfit_choices import kill
    off = int(payload["offender"])
    if not is_living(conn, off):
        _finish(conn, payload, day, "let_go")
        return {"summary": "The man was already dead.", "blocked": True}
    _finish(conn, payload, day, "killed")
    ohead = head_of(conn, int(payload["offender_org"])) if payload.get("offender_org") else None
    if ohead is not None and ohead != int(actor_id):
        adjust_relationship(conn, ohead, int(actor_id), int(day), resentment_delta=float(figure(conn, "hap_resp_kill_resentment")),
                            fear_delta=float(figure(conn, "hap_resp_kill_resentment")) / 2.0)
    return {"summary": kill(conn, int(actor_id), off, int(day), sanctioned=True, fallible=True)}


def execute_let_go(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day, "let_go")
    ohead = head_of(conn, int(payload["offender_org"])) if payload.get("offender_org") else None
    if ohead is not None and ohead != int(actor_id):
        adjust_relationship(conn, ohead, int(actor_id), int(day), respect_delta=-float(figure(conn, "hap_resp_let_respect")))
    return {"summary": f"{_name(conn, actor_id)} let it go."}


def pay_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = json.loads(item["metadata_json"] or "{}")
    aggr = om._drive(conn, actor_id, "aggression")
    payload = {**meta, "incident_id": int(meta["incident"])}
    return [{"kind": "pay", "utility": _utility(conn, float(figure(conn, "hap_pay_w")) * (1.25 - aggr)), "rationale": "Pays what is asked.", "payload": payload},
            {"kind": "refuse", "utility": _utility(conn, float(figure(conn, "hap_refuse_w")) * (0.25 + aggr)), "rationale": "Refuses.", "payload": payload}]


def execute_pay(conn, actor_id, kind, payload, day):
    vh = int(payload["from"])
    line = conn.execute("SELECT weekly_take FROM org_lines WHERE id=(SELECT victim_line_id FROM org_incidents WHERE id=?)", (int(payload["incident_id"]),)).fetchone()
    weekly = float(line[0]) if line and line[0] else float(figure(conn, "hap_pay_default_weekly"))
    amount = weekly * int(payload["weeks"])
    paid = ledger.transfer(conn, ("person", int(actor_id)), ("person", vh), amount, flow_kind="tribute", purpose="making good an incident", allow_partial=True)
    if paid <= 0:
        return execute_refuse(conn, actor_id, "refuse", payload, day)
    _finish(conn, payload, day, "paid")
    if paid < amount and payload.get("offender_org") is not None and payload.get("org") is not None:
        from . import org_dealings
        org_dealings.owe(conn, int(payload["org"]), int(payload["offender_org"]), amount - paid, "redress he could only part pay", int(day))
    adjust_relationship(conn, vh, int(actor_id), int(day), respect_delta=float(figure(conn, "hap_resp_sit_respect")), resentment_delta=-float(figure(conn, "hap_resp_sit_respect")))
    if payload.get("offender_org") is not None and payload.get("org") is not None:
        from . import org_tension
        org_tension.on_answer(conn, int(payload["org"]), int(payload["offender_org"]), "paid", int(day), actor=int(actor_id))
        org_tension.on_answer(conn, int(payload["offender_org"]), int(payload["org"]), "paid", int(day), actor=int(actor_id))
    return {"summary": f"{_name(conn, actor_id)} paid {_name(conn, vh)} ${paid:,.0f}."}


def execute_refuse(conn, actor_id, kind, payload, day):
    vh = int(payload["from"])
    _finish(conn, payload, day, "refused")
    adjust_relationship(conn, vh, int(actor_id), int(day), resentment_delta=float(figure(conn, "hap_resp_kill_resentment")),
                        respect_delta=-float(figure(conn, "hap_resp_let_respect")))
    imposed(conn, vh)  # the refusal lands on the man who asked
    if payload.get("offender_org") is not None and payload.get("org") is not None:
        from . import org_tension
        org_tension.on_answer(conn, int(payload["org"]), int(payload["offender_org"]), "refused_redress", int(day), actor=int(actor_id))
    if payload.get("killer_org") is not None and payload.get("victim") is not None:
        _again(conn, vh, payload, day, redress_refused=True, peace_refused=bool(payload.get("peace_refused")))  # redress for a killing was refused: it is his to answer again
    return {"summary": f"{_name(conn, actor_id)} refused {_name(conn, vh)}."}


# ---- a killing across organisations: the dead man's head answers ----

def _killing(conn: sqlite3.Connection) -> dict:
    return _data(conn).get("killing") or {}


def killed_across(conn: sqlite3.Connection, killer: int, victim: int, seats, day: int, sanctioned: bool = True, ordered_by: int | None = None) -> None:
    """A man was killed. The world notices: heat is written on the organisations involved, the pairs' tension moves, the dead man's unit and
    kin are changed by it, other heads weigh the wake. For each organisation the killer (or the man who sent him) holds no seat in, the
    dead man's head (when it has one) gets a `respond_killing` item, a `killing` incident is recorded, and the head and the dead man's
    superior are imposed on. A killing by a man with no seat and no one who sent him is the dead man's head's to hunt (`discipline_hunt`)."""
    data = _killing(conn)
    if not data:
        return
    from . import org_heat, org_temperament, org_tension
    mine = {int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (int(killer),))}
    if ordered_by is not None and int(ordered_by) != int(killer):
        sent = {int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (int(ordered_by),))}
        if sent and not (mine & sent):  # a man hired from outside: the dead man's head answers whoever hired him
            mine, killer = sent, int(ordered_by)
        elif not mine:
            mine = sent
    victim_orgs = sorted({int(s["org_actor_id"]) for s in seats})
    foreign = [o for o in victim_orgs if o not in mine]
    role = seats[0]["role_key"] if seats else None
    if org_heat.enabled(conn):
        org_heat.on_killing(conn, mine, victim_orgs, org_tension._rank(conn, role), int(day), public=bool(foreign), civilian=not seats)
    for s in seats:
        org = int(s["org_actor_id"])
        org_tension.on_death(conn, int(victim), org, s["role_key"], int(day), killed_by_org=min(mine) if mine and org not in mine else None)
        if s["unit_id"]:
            for (mate,) in conn.execute("SELECT actor_id FROM org_seats WHERE unit_id=? AND status='active' AND actor_id<>? ORDER BY actor_id", (int(s["unit_id"]), int(victim))).fetchall():
                org_temperament.drift(conn, int(mate), "unit_loss", int(day))
    for kin, kind in conn.execute(
            """SELECT CASE WHEN actor_a_id=? THEN actor_b_id ELSE actor_a_id END,kin_kind FROM kinship_links WHERE (actor_a_id=? OR actor_b_id=?)
               AND legal_status='recognized' AND ended_day IS NULL AND kin_kind IN ('parent','child','sibling','spouse')""", (int(victim), int(victim), int(victim))).fetchall():
        if is_living(conn, int(kin)):
            close = _v(conn, (((org_temperament.data(conn).get("drift") or {}).get("kin_killed")) or {}).get("close_scale"), 1.0) if kind in ("parent", "child") else 1.0
            org_temperament.drift(conn, int(kin), "kin_killed", int(day), close)
    if not mine:
        for org in victim_orgs:
            head = head_of(conn, org)
            if head is not None and head != int(victim):
                add_agenda(conn, head, "discipline_hunt", int(day) + int(figure(conn, data["delay"])), subject_kind="actor", subject_id=int(killer),
                           metadata={"victim": int(victim), "org": org, "head_wants": 0.0, "outsider": True})
                imposed(conn, head)
        return
    for s in seats:
        org = int(s["org_actor_id"])
        if org in mine:
            continue
        org_tension.on_killing(conn, int(killer), int(victim), org, mine, s["role_key"], bool(sanctioned), int(day))
        head = head_of(conn, org)
        sup = s["superior_actor_id"]
        if sup is not None:
            imposed(conn, int(sup))
        if head is None or head == int(killer):
            continue
        iid = _record(conn, day, "killing", killer, victim=int(victim), matters=1, raised=org, status="open",
                      killer_org=min(mine), role=s["role_key"])
        imposed(conn, head)
        add_agenda(conn, head, "respond_killing", int(day) + int(figure(conn, data["delay"])), subject_kind="actor", subject_id=int(victim),
                   metadata={"incident": iid, "killer": int(killer), "killer_org": min(mine), "org": org, "victim": int(victim), "role": s["role_key"],
                             "sanctioned": bool(sanctioned)})


def _size(conn, org: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND status='active'", (org,)).fetchone()[0])


def _had_sit_down(conn, victim: int) -> bool:
    return conn.execute("SELECT 1 FROM org_incidents WHERE offender_actor_id=? AND status IN ('sat_down','paid','refused') LIMIT 1", (int(victim),)).fetchone() is not None


def _kin_wanting(conn, victim: int) -> float:
    """Living close kin of the dead man (parents, children, siblings, spouse), 0..1 with two or more counting full."""
    kin = {int(r[0]) for r in conn.execute(
        """SELECT CASE WHEN actor_a_id=? THEN actor_b_id ELSE actor_a_id END FROM kinship_links
           WHERE (actor_a_id=? OR actor_b_id=?) AND legal_status='recognized' AND ended_day IS NULL AND kin_kind IN ('parent','child','sibling','spouse')""",
        (victim, victim, victim))}
    return clamp01(sum(1 for k in kin if is_living(conn, k)) / 2.0)


def _on_own_ground(conn, victim: int, org: int) -> float:
    """1 when the man was killed on the ground of his own unit: an insult as well as a loss."""
    r = conn.execute("""SELECT 1 FROM org_seats s JOIN org_units u ON u.id=s.unit_id JOIN actors a ON a.id=s.actor_id
                        WHERE s.actor_id=? AND s.org_actor_id=? AND a.current_location_id IS NOT NULL AND u.ground_location_id=a.current_location_id LIMIT 1""", (victim, org)).fetchone()
    return 1.0 if r else 0.0


def _cost(conn: sqlite3.Connection) -> dict:
    """The package's cost figures for answering a killing (outfits data `happenings.killing.cost`); every key is required."""
    return _killing(conn)["cost"]


def _need(conn, key: str) -> float:
    return _v(conn, _cost(conn)[key])


def _recent_killings(conn, day: int, *, org: int | None = None, killer_org: int | None = None, either: int | None = None) -> list:
    """The killings across outfits recorded within the lookback (data `cost.lookback_days`): a weight over memory, not a gate. `org` is the
    outfit that lost the man, `killer_org` the one that did it, `either` an outfit on either side."""
    since = int(day) - int(_need(conn, "lookback_days"))
    sql = "SELECT day,raised_to_org_actor_id,json_extract(metadata_json,'$.killer_org'),victim_actor_id FROM org_incidents WHERE kind='killing' AND day>=?"
    args: list = [since]
    if org is not None:
        sql += " AND raised_to_org_actor_id=?"
        args.append(int(org))
    if killer_org is not None:
        sql += " AND json_extract(metadata_json,'$.killer_org')=?"
        args.append(int(killer_org))
    if either is not None:
        sql += " AND (raised_to_org_actor_id=? OR json_extract(metadata_json,'$.killer_org')=?)"
        args += [int(either), int(either)]
    return conn.execute(sql, args).fetchall()


def _sees(conn, a: int | None, b: int | None) -> float:
    """How well one head thinks of another, 0..1 (respect and trust)."""
    r = om._rel(conn, a, b)
    return 0.0 if r is None else clamp01((float(r["respect"]) + float(r["trust"])) / 200.0)


def _third_heads(conn, org: int, other: int) -> list[tuple[int, int]]:
    """(head, size) of every other outfit of the same kind, from the data."""
    out = []
    for (o,) in conn.execute("SELECT org_actor_id FROM org_profiles WHERE org_actor_id NOT IN (?,?) AND org_kind=(SELECT org_kind FROM org_profiles WHERE org_actor_id=?) ORDER BY org_actor_id",
                             (int(org), int(other), int(org))).fetchall():
        h = head_of(conn, int(o))
        if h is not None:
            out.append((int(h), _size(conn, int(o))))
    return out


def _cost_factors(conn, head: int, org: int, other: int, day: int, team: int) -> dict[str, float]:
    """What carrying on a feud would cost the head of `org` against `other`: men and earnings lost to them, both sides' losses, being the
    weaker side by men and by allies, law heat after recent killings, a thin purse (what has come to him within the lookback against what a team costs), his caution, his standing, and a third head both
    would hear out. Each is 0..1 against a data figure (`cost.*_full`); none is a ceiling on anything."""
    mine, theirs = _size(conn, org), _size(conn, other)
    taken_rows = _recent_killings(conn, day, org=org, killer_org=other)
    lost = len(taken_rows)
    their_lost = len(_recent_killings(conn, day, org=other, killer_org=org))
    ohead = head_of(conn, other)
    taken = [int(r[3]) for r in taken_rows if r[3] is not None]
    earn = 0.0
    if taken:
        q = ",".join("?" * len(taken))
        earn = float(conn.execute(f"SELECT COALESCE(SUM(weekly_take),0) FROM org_lines WHERE holder_actor_id IN ({q})", taken).fetchone()[0])
    total = float(conn.execute("SELECT COALESCE(SUM(l.weekly_take),0) FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active'", (org,)).fetchone()[0])
    allies_theirs = 0.0
    broker = 0.0
    for t, tsize in _third_heads(conn, org, other):
        clout = clamp01(tsize / max(1, mine, theirs))
        allies_theirs += max(0.0, _sees(conn, t, ohead) - _sees(conn, t, head)) * clout
        broker = max(broker, min(_sees(conn, head, t), _sees(conn, ohead, t)) * clout)
    seat = conn.execute("SELECT standing FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (int(head), int(org))).fetchone()
    price = _need(conn, "price_per_man") * max(1, int(team))
    since = int(day) - int(_need(conn, "lookback_days"))
    settled = conn.execute(
        """SELECT 1 FROM org_incidents WHERE kind='killing' AND day>=? AND status IN ('settled','paid')
           AND ((raised_to_org_actor_id=? AND json_extract(metadata_json,'$.killer_org')=?) OR (raised_to_org_actor_id=? AND json_extract(metadata_json,'$.killer_org')=?)) LIMIT 1""",
        (since, int(org), int(other), int(other), int(org))).fetchone()
    return {"lost": clamp01(lost / max(1, mine) / _need(conn, "lost_share_full")),
            "both_lost": clamp01((lost + their_lost) / max(1, mine + theirs) / _need(conn, "both_share_full")),
            "lost_earnings": clamp01(earn / total / _need(conn, "earn_full")) if total > 0 else 0.0,
            "weaker": clamp01(1.0 - mine / theirs) if theirs and mine < theirs else 0.0,
            "allies_theirs": clamp01(allies_theirs / _need(conn, "allies_full")),
            "heat_own": org_heat.own_factor(conn, org, day),
            "heat_city": org_heat.city_factor(conn, day),
            "cash_thin": clamp01(1.0 - float(conn.execute("SELECT COALESCE(SUM(amount),0) FROM org_money WHERE to_actor_id=? AND day>=?", (int(head), since)).fetchone()[0]) / price) if price > 0 else 0.0,
            "cautious": 1.0 - om._drive(conn, head, "aggression"),
            "secure": clamp01(float(seat["standing"]) / _need(conn, "standing_full")) if seat is not None else 0.0,
            "broker": broker,
            "broken_peace": 1.0 if settled else 0.0}


def _killing_factors(conn, head: int, meta: dict, day: int) -> dict[str, float]:
    victim, killer = int(meta["victim"]), int(meta["killer"])
    org, korg = int(meta["org"]), int(meta["killer_org"])
    rank = _v(conn, (_killing(conn).get("role_rank") or {}).get(meta.get("role")), 0.5)
    wrong = conn.execute("SELECT status FROM org_incidents WHERE offender_actor_id=? AND kind<>'killing' AND matters=1 AND status<>'done'", (victim,)).fetchall()
    khead = head_of(conn, korg)
    r = om._rel(conn, head, khead)
    mine, theirs = _size(conn, org), _size(conn, korg)
    f = {"always": 1.0, "victim_wrong": 1.0 if wrong else 0.0, "low_role": 1.0 - rank, "high_role": rank,
         "unsanctioned": 0.0 if meta.get("sanctioned", True) else 1.0, "kin": _kin_wanting(conn, victim),
         "humiliation": _on_own_ground(conn, victim, org),
         "refused_sit": 1.0 if any(w[0] == "refused" for w in wrong) else 0.0,
         "no_sit_down": 0.0 if _had_sit_down(conn, victim) else 1.0,
         "stronger": clamp01(1.0 - theirs / mine) if mine and theirs < mine else 0.0,
         "friendly": 0.0 if r is None else clamp01((float(r["respect"]) + float(r["trust"])) / 200.0),
         "resentful": 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0),
         "temper": om._drive(conn, head, "aggression"),
         "redress_refused": 1.0 if meta.get("redress_refused") else 0.0, "peace_refused": 1.0 if meta.get("peace_refused") else 0.0}
    f.update(_cost_factors(conn, head, org, korg, day, _team_size(conn, meta)))
    return f


def _blend(conn, items, factors: dict[str, float]) -> float:
    """1 - prod(1 - weight x factor) over an answer's terms, scaled by (1 - the same blend over the terms marked `against`): a weighed
    counter-term takes a share off the answer, never down to a fixed ceiling and never to a fixed count."""
    rest = against = 1.0
    for m in items:
        t = clamp01(_v(conn, m["weight"])) * clamp01(factors.get(m["name"], 0.0))
        if m.get("against"):
            against *= 1.0 - t
        else:
            rest *= 1.0 - t
    return (1.0 - rest) * against


def _against(conn, items, factors: dict[str, float]) -> float:
    """The share the counter-terms take off an answer on their own: 1 - prod(1 - weight x factor) over `items`."""
    rest = 1.0
    for m in items:
        rest *= 1.0 - clamp01(_v(conn, m["weight"])) * clamp01(factors.get(m["name"], 0.0))
    return 1.0 - rest


def killing_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = json.loads(item["metadata_json"] or "{}")
    f = _killing_factors(conn, actor_id, meta, int(day))
    why = {"accept_killing": f"Lets the killing of {_name(conn, meta['victim'])} stand.",
           "demand_redress": f"Demands redress from {_name(conn, head_of(conn, int(meta['killer_org'])))} for {_name(conn, meta['victim'])}.",
           "sit_down_peace": f"Asks for a sit-down with {_name(conn, head_of(conn, int(meta['killer_org'])))} to end it over {_name(conn, meta['victim'])}.",
           "retaliate": f"Has {_name(conn, meta['killer'])} answered for {_name(conn, meta['victim'])}."}
    return [{"kind": k, "utility": _utility(conn, _blend(conn, _killing(conn)[k], f)), "rationale": why[k], "payload": {**meta, "incident_id": int(meta["incident"])}}
            for k in ("accept_killing", "demand_redress", "sit_down_peace", "retaliate") if _killing(conn).get(k)]


def _heads(conn, actor_id, payload):
    return int(actor_id), head_of(conn, int(payload["killer_org"]))


def execute_accept_killing(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day, "accepted")
    me, other = _heads(conn, actor_id, payload)
    pts = float(figure(conn, _killing(conn)["relation_points"]))
    if other is not None:
        adjust_relationship(conn, other, me, int(day), respect_delta=-pts)  # he let it go: he is thought weaker
        adjust_relationship(conn, me, other, int(day), resentment_delta=pts / 2.0)
    from . import org_tension
    org_tension.on_answer(conn, int(payload["org"]), int(payload["killer_org"]), "accepted", int(day), actor=me)
    return {"summary": f"{_name(conn, me)} let the killing of {_name(conn, payload['victim'])} stand."}


def execute_demand_redress(conn, actor_id, kind, payload, day):
    me, other = _heads(conn, actor_id, payload)
    _finish(conn, payload, day, "redress_asked")
    if other is None:
        return {"summary": "There was no one to ask.", "blocked": True}
    weeks = int(round(_span(conn, "hap_pay_weeks_lo", "hap_pay_weeks_hi", _rng(conn, "weeks", payload["incident_id"], day))))
    add_agenda(conn, other, "pay_or_refuse", int(day) + int(figure(conn, _killing(conn)["delay"])), subject_kind="incident", subject_id=int(payload["incident_id"]),
               metadata={**_carry(payload), "incident": int(payload["incident_id"]), "from": me, "weeks": weeks, "offender": int(payload["killer"]), "offender_org": int(payload["killer_org"])})
    imposed(conn, other)
    adjust_relationship(conn, me, other, int(day), resentment_delta=float(figure(conn, _killing(conn)["relation_points"])))
    return {"summary": f"{_name(conn, me)} asked {_name(conn, other)} to make good the killing of {_name(conn, payload['victim'])}."}


_KILLING_KEYS = ("incident", "killer", "killer_org", "org", "victim", "role", "sanctioned")


def _again(conn, head: int, payload: dict, day: int, **flag) -> None:
    """Put the killing back on the dead man's head's list after the other side said no, with what was refused marked in it."""
    meta = {k: payload[k] for k in _KILLING_KEYS if k in payload}
    meta.update(flag)
    add_agenda(conn, int(head), "respond_killing", int(day) + int(figure(conn, _killing(conn)["delay"])), subject_kind="actor", subject_id=int(payload["victim"]), metadata=meta)
    imposed(conn, int(head))


def execute_sit_down_peace(conn, actor_id, kind, payload, day):
    """The head asks the other head to sit down over the killing (through a third head both hear out where there is one). The other
    head weighs it with his own costs (data `killing.settle_accept`) against a draw from the run's seed; peace settles the matter
    and eases both, a refusal puts the matter back on the first head's list marked as refused."""
    me, other = _heads(conn, actor_id, payload)
    if other is None:
        _finish(conn, payload, day, "sat_down")
        return {"summary": "There was no one to sit down with.", "blocked": True}
    org, korg = int(payload["org"]), int(payload["killer_org"])
    f = _cost_factors(conn, other, korg, org, int(day), 1)
    f.update({"always": 1.0, "temper": om._drive(conn, other, "aggression")})
    p = _blend(conn, _killing(conn)["settle_accept"], f)
    pts = float(figure(conn, _killing(conn)["relation_points"]))
    imposed(conn, other)
    if _rng(conn, "peace", int(payload["incident_id"]), day).random() < p:
        _finish(conn, payload, day, "settled")
        adjust_relationship(conn, me, other, int(day), respect_delta=pts, resentment_delta=-pts, trust_delta=pts / 2.0)
        adjust_relationship(conn, other, me, int(day), respect_delta=pts, resentment_delta=-pts, trust_delta=pts / 2.0)
        from . import org_tension
        org_tension.on_answer(conn, org, korg, "settled", int(day), actor=me)
        org_tension.on_answer(conn, korg, org, "settled", int(day), actor=other)
        return {"summary": f"{_name(conn, me)} and {_name(conn, other)} sat down and settled the killing of {_name(conn, payload['victim'])}."}
    _finish(conn, payload, day, "peace_refused")
    adjust_relationship(conn, me, other, int(day), resentment_delta=pts, respect_delta=-pts / 2.0)
    from . import org_tension
    org_tension.on_answer(conn, org, korg, "refused_peace", int(day), actor=other)
    _again(conn, me, payload, day, redress_refused=bool(payload.get("redress_refused")), peace_refused=True)
    return {"summary": f"{_name(conn, other)} would not sit down with {_name(conn, me)} over {_name(conn, payload['victim'])}."}


def _team_size(conn, payload: dict) -> int:
    """How many men go after the killer: a base and more for the victim's rank (data `killing.team`). No cap on how often."""
    t = _killing(conn).get("team") or {}
    rank = _v(conn, (_killing(conn).get("role_rank") or {}).get(payload.get("role")), 0.5)
    return max(1, int(round(_v(conn, t.get("base"), 1.0) + _v(conn, t.get("rank"), 0.0) * rank)))


def execute_retaliate(conn, actor_id, kind, payload, day):
    from .outfit_choices import execute_order_hunt
    me, other = _heads(conn, actor_id, payload)
    _finish(conn, payload, day, "retaliated")
    team = _team_size(conn, payload)
    if other is not None:
        pts = float(figure(conn, _killing(conn)["retaliate_points"]))
        adjust_relationship(conn, me, other, int(day), resentment_delta=pts)
        adjust_relationship(conn, other, me, int(day), fear_delta=pts / 2.0, resentment_delta=pts / 2.0)
    res = execute_order_hunt(conn, me, "order_hunt", {"org": int(payload["org"]), "killer": int(payload["killer"]), "team": team, "retaliation": True}, int(day))
    return {"summary": f"{_name(conn, me)} had the killing of {_name(conn, payload['victim'])} answered: {res.get('summary', '')}"}


for _kind, _fn in (("sit_down", execute_sit_down), ("kill_offender", execute_kill_offender), ("let_it_go", execute_let_go),
                   ("pay", execute_pay), ("refuse", execute_refuse), ("accept_killing", execute_accept_killing),
                   ("demand_redress", execute_demand_redress), ("sit_down_peace", execute_sit_down_peace), ("retaliate", execute_retaliate)):
    register_executor(_kind, _fn)
register_agenda_action("respond_killing", killing_offers)
register_agenda_action("respond_incident", respond_offers)
register_agenda_action("pay_or_refuse", pay_offers)

from . import org_tension  # noqa: E402,F401  (registers the tension model's executors and agenda actions)
