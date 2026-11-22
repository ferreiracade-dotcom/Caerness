"""A table of heads that can emerge between the organisations, and can fail (task B12f). Generic; the package's words and figures are
outfits data `tension.council`, each figure a Design proposal with its reasoning in design_figures.json.

Nothing creates a council. A head who is tired of war, who sees a respected third head, who feels the city's heat or an outside
family's pressure, who knows the others well, or who is so large that a table would suit him weighs proposing one each week; the heads
he asks weigh coming with their own costs and fears (a table he runs is a table that runs them). A council with enough heads seated
(a definition of a table, not a cap on anything) exists; it has a standing that rises when its rulings are kept and falls when they are
defied or when the families kill each other in spite of it, and it fades unless it is used. Heads weigh staying each week and weigh
leaving; others are asked in. It fails when too few remain.

What it does. It settles disputes between its members (a ruling both heads weigh accepting; redress for killings is paid, and what is
not paid becomes a debt). It sanctions killings: a strike by one member on another is put to the table (the table weighs the
provocation); a refused voice weighs defying it, and a defied ruling binds only in honour: the breaker loses the others' regard, the
table loses standing. And its standing is one more term in every member's weighing of a slight, a squeeze, a strike or a sit-down.
"""
from __future__ import annotations

import math
import sqlite3

from . import org_heat, outfit_motives as om
from . import org_tension as ot
from .orgs import clamp01, head_of, imposed
from .relationships import adjust_relationship


def cd(conn: sqlite3.Connection) -> dict:
    return ot.data(conn).get("council") or {}


def enabled(conn: sqlite3.Connection) -> bool:
    return bool(cd(conn))


def _v(conn, spec, default: float = 0.0) -> float:
    return ot._v(conn, spec, default)


def _rng(conn, stream: str, *keys):
    return ot._rng(conn, "council:" + stream, *keys)


def _raise(conn, name: str) -> float:
    return _v(conn, (ot.data(conn).get("raise") or {}).get(name), 0.0)


# ---- the state ----

def standing(conn: sqlite3.Connection, cid: int, day: int) -> float:
    r = conn.execute("SELECT standing,updated_day FROM org_councils WHERE id=?", (int(cid),)).fetchone()
    if r is None:
        return 0.0
    half = _v(conn, cd(conn).get("half_life_days"), 0.0)
    return float(r[0]) if half <= 0 or day <= r[1] else float(r[0]) * 0.5 ** ((int(day) - int(r[1])) / half)


def norm(conn: sqlite3.Connection, cid: int, day: int) -> float:
    """0..1: a council's standing against the data's `scale`; a council that is used and kept keeps rising, read with diminishing weight."""
    s = standing(conn, cid, day)
    return s / (s + max(1e-9, _v(conn, cd(conn).get("scale"), 1.0)))


def _move(conn, cid: int, delta: float, day: int, kind: str, a: int | None = None, b: int | None = None, actor: int | None = None, note: str | None = None) -> None:
    new = max(0.0, standing(conn, cid, day) + float(delta))
    conn.execute("UPDATE org_councils SET standing=?, updated_day=? WHERE id=?", (new, int(day), int(cid)))
    conn.execute("INSERT INTO org_council_acts(council_id,day,kind,org_a,org_b,actor_id,standing_delta,note) VALUES (?,?,?,?,?,?,?,?)",
                 (int(cid), int(day), kind, a, b, actor, float(delta), note))


def active(conn: sqlite3.Connection) -> list[int]:
    return [int(r[0]) for r in conn.execute("SELECT id FROM org_councils WHERE ended_day IS NULL ORDER BY id")]


def members(conn: sqlite3.Connection, cid: int) -> list[int]:
    return [int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_council_seats WHERE council_id=? AND left_day IS NULL ORDER BY org_actor_id", (int(cid),))]


def binding(conn: sqlite3.Connection, a: int, b: int, day: int) -> tuple[int, float] | None:
    """(council, standing 0..1) of the strongest active council in which both organisations hold a seat; None when there is none."""
    if not enabled(conn):
        return None
    best = None
    for (cid,) in conn.execute(
            """SELECT s.council_id FROM org_council_seats s JOIN org_councils c ON c.id=s.council_id WHERE c.ended_day IS NULL AND s.left_day IS NULL AND s.org_actor_id=?
               AND s.council_id IN (SELECT council_id FROM org_council_seats WHERE org_actor_id=? AND left_day IS NULL) ORDER BY s.council_id""", (int(a), int(b))).fetchall():
        n = norm(conn, int(cid), day)
        if best is None or n > best[1]:
            best = (int(cid), n)
    return best


def bound_standing(conn: sqlite3.Connection, a: int, b: int, day: int) -> float:
    r = binding(conn, a, b, day)
    return 0.0 if r is None else r[1]


def seated(conn: sqlite3.Connection, org: int) -> int | None:
    r = conn.execute("SELECT s.council_id FROM org_council_seats s JOIN org_councils c ON c.id=s.council_id WHERE c.ended_day IS NULL AND s.left_day IS NULL AND s.org_actor_id=? ORDER BY s.council_id LIMIT 1", (int(org),)).fetchone()
    return None if r is None else int(r[0])


# ---- what a head weighs about the table ----

def _contacts(conn, F: int, day: int) -> list[int]:
    t = ot._today(conn, day)
    c = t.get("cp")
    if c is None or c[0] != int(day):
        by: dict = {}
        for a, b in ot.pairs(conn, day):
            by.setdefault(a, set()).add(b)
        t["cp"] = c = (int(day), by)
    return sorted(c[1].get(int(F), ()))


def _outside(conn) -> set[int]:
    keys = list(cd(conn).get("outside") or [])
    if not keys:
        return set()
    q = ",".join("?" * len(keys))
    return {int(r[0]) for r in conn.execute(f"SELECT org_actor_id FROM org_profiles WHERE package_key IN ({q})", keys)}


def _sizes(conn, day: int) -> dict[int, int]:
    from .org_happenings import _size
    t = ot._today(conn, day)
    c = t.get("sz")
    if c is None or c[0] != int(day):
        t["sz"] = c = (int(day), {o: _size(conn, o) for o in ot._underworld_orgs(conn, day)})
    return c[1]


def org_factors(conn: sqlite3.Connection, F: int, day: int) -> dict[str, float]:
    """Each 0..1: how tired F is of its quarrels (`weary`) and of its dead (`lost`), the pressure from outside (`outside`: the city's heat, its
    own, an outside family's), how well its head knows the heads it deals with (`ties`), a respected third head (`mediator`), how large it
    is among them (`dominance`), its grudges (`grievance`), and its head's own temper."""
    from .org_happenings import _sees
    orgs = ot._underworld_orgs(conn, day)
    hF = head_of(conn, F)
    cs = _contacts(conn, F, day)
    sizes = _sizes(conn, day)
    total = max(1, sum(sizes.values()))
    biggest = max(sizes.values() or [1])
    weary = max([max(ot.heat(conn, F, x, day), ot.heat(conn, x, F, day)) for x in cs] or [0.0])
    d = cd(conn)
    since = int(day) - int(_v(conn, d.get("lookback_days"), 365.0))
    dead = conn.execute("SELECT COUNT(*) FROM org_tension_acts WHERE kind='killing' AND from_org=? AND day>=?", (int(F), since)).fetchone()[0]
    lost = clamp01(dead / max(1.0, sizes.get(F, 1) * _v(conn, d.get("lost_full"), 0.05)))
    outer = max([max(ot.heat(conn, F, o, day), ot.heat(conn, o, F, day)) for o in _outside(conn) if o != F] or [0.0])
    city, own = org_heat.city_factor(conn, day), org_heat.own_factor(conn, F, day)
    ties = [_sees(conn, hF, head_of(conn, x)) for x in cs if head_of(conn, x) is not None]
    med = max([_sees(conn, hF, head_of(conn, m)) * math.sqrt(sizes.get(m, 1) / biggest) for m in orgs if m != F and head_of(conn, m) is not None] or [0.0])
    grievance = 0.0
    for x in cs:
        r = om._rel(conn, hF, head_of(conn, x))
        if r is not None:
            grievance = max(grievance, clamp01(float(r["resentment"]) / 100.0))
    drive = (lambda k: om._drive(conn, hF, k)) if hF is not None else (lambda k: 0.5)
    return {"weary": weary, "lost": lost, "outside": 1.0 - (1.0 - city) * (1.0 - own) * (1.0 - outer), "ties": sum(ties) / len(ties) if ties else 0.0,
            "mediator": med, "dominance": clamp01(sizes.get(F, 0) / total), "grievance": grievance, "always": 1.0,
            "aggression": drive("aggression"), "calm": 1.0 - drive("aggression"), "ambition": drive("ambition"),
            "patience": drive("patience"), "pragmatism": drive("pragmatism")}


def _blend(conn, terms, f):
    return ot._blend(conn, terms, f)


# ---- the weekly life ----

def process_due(conn: sqlite3.Connection, day: int) -> dict:
    if not enabled(conn):
        return {}
    out: dict = {}
    for name, fn in (("proposed", _propose), ("joined", _recruit), ("left", _leave), ("ruled", _rule)):
        n = fn(conn, int(day))
        if n:
            out[f"council:{name}"] = n
    return out


def _form(conn, convener: int, orgs_: list[int], day: int) -> int:
    cid = int(conn.execute("INSERT INTO org_councils(formed_day,standing,updated_day,convener_org) VALUES (?,?,?,?)", (int(day), _v(conn, cd(conn).get("start"), 0.0), int(day), int(convener))).lastrowid)
    for o in [convener, *orgs_]:
        conn.execute("INSERT INTO org_council_seats(council_id,org_actor_id,joined_day) VALUES (?,?,?)", (cid, int(o), int(day)))
        h = head_of(conn, o)
        if h is not None:
            imposed(conn, h)
    conn.execute("INSERT INTO org_council_acts(council_id,day,kind,org_a,standing_delta,note) VALUES (?,?,?,?,0,?)", (cid, int(day), "formed", int(convener), f"{len(orgs_) + 1} seats"))
    return cid


def _asked(conn, F: int, I: int, day: int, cid: int | None) -> bool:
    """Whether the head of I comes when F's head asks: his own weariness, fears and ties, and how large and how hated the asker is."""
    from .org_happenings import _sees
    f = org_factors(conn, I, day)
    hI, hF = head_of(conn, I), head_of(conn, F)
    r = om._rel(conn, hI, hF)
    sizes = _sizes(conn, day)
    f.update({"asker_ties": _sees(conn, hI, hF), "asker_big": clamp01(sizes.get(F, 0) / max(1, sum(sizes.values()))), "heat_to_asker": ot.heat(conn, I, F, day),
              "asker_grievance": 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0),
              "council": 0.0 if cid is None else norm(conn, cid, day)})
    return _rng(conn, "accept", F, I, day).random() < _blend(conn, cd(conn)["accept"], f)


def _propose(conn, day: int) -> int:
    d = cd(conn)
    n = 0
    taken: set[int] = set()
    for F in ot._underworld_orgs(conn, day):
        if seated(conn, F) is not None or F in taken:
            continue
        f = org_factors(conn, F, day)
        if _rng(conn, "propose", F, day).random() >= _blend(conn, d["propose"], f) * _v(conn, d.get("propose_rate"), 0.0):
            continue
        ask = [x for x in _contacts(conn, F, day) if head_of(conn, x) is not None and x not in taken]
        yes = [x for x in ask if _asked(conn, F, x, day, None)]
        ok = len(yes) + 1 >= int(_v(conn, d.get("min_seats"), 3))
        conn.execute("INSERT INTO org_tension_acts(day,from_org,to_org,kind,delta,actor_id,victim_id,note) VALUES (?,?,?,?,0,?,NULL,?)",
                     (int(day), F, F, "council_proposed", head_of(conn, F), f"asked {len(ask)}, came {len(yes)}, {'formed' if ok else 'failed'}"))
        if ok:
            _form(conn, F, yes, day)
            taken |= set(yes) | {F}
            n += 1
    return n


def _recruit(conn, day: int) -> int:
    d = cd(conn)
    n = 0
    for cid in active(conn):
        ms = members(conn, cid)
        for X in ot._underworld_orgs(conn, day):
            if X in ms or seated(conn, X) is not None:
                continue
            near = [m for m in ms if X in _contacts(conn, m, day)]
            if not near or _rng(conn, "recruit", cid, X, day).random() >= _v(conn, d.get("join_rate"), 0.0):
                continue
            if _asked(conn, max(near), X, day, cid):
                conn.execute("INSERT INTO org_council_seats(council_id,org_actor_id,joined_day) VALUES (?,?,?)", (cid, int(X), int(day)))
                conn.execute("INSERT INTO org_council_acts(council_id,day,kind,org_a,standing_delta) VALUES (?,?,?,?,0)", (cid, int(day), "joined", int(X)))
                imposed(conn, head_of(conn, X))
                n += 1
    return n


def _end(conn, cid: int, day: int, reason: str) -> None:
    conn.execute("UPDATE org_councils SET ended_day=?, end_reason=? WHERE id=?", (int(day), reason, int(cid)))
    conn.execute("UPDATE org_council_seats SET left_day=?, left_reason=? WHERE council_id=? AND left_day IS NULL", (int(day), reason, int(cid)))
    conn.execute("INSERT INTO org_council_acts(council_id,day,kind,standing_delta,note) VALUES (?,?,?,0,?)", (int(cid), int(day), "ended", reason))


def _leave(conn, day: int) -> int:
    d = cd(conn)
    n = 0
    for cid in active(conn):
        nrm = norm(conn, cid, day)
        for org in members(conn, cid):
            reason = None
            if conn.execute("SELECT 1 FROM org_council_seats WHERE council_id=? AND org_actor_id=? AND left_day IS NULL AND joined_day>=?", (cid, int(org), int(day))).fetchone():
                continue  # he sat down today; the table is not weighed the day it is made
            if head_of(conn, org) is None:
                reason = "headless"
            else:
                f = org_factors(conn, org, day)
                f.update({"ignored": 1.0 - nrm, "council": nrm})
                if _rng(conn, "leave", cid, org, day).random() < _blend(conn, d["leave"], f) * _v(conn, d.get("leave_rate"), 0.0):
                    reason = "withdrew"
            if reason is None:
                continue
            conn.execute("UPDATE org_council_seats SET left_day=?, left_reason=? WHERE council_id=? AND org_actor_id=? AND left_day IS NULL", (int(day), reason, cid, int(org)))
            _move(conn, cid, -_v(conn, d.get("walkout_cost"), 0.0), day, "left", org, None, head_of(conn, org), reason)
            if reason == "withdrew":
                for m in members(conn, cid):
                    ot.add(conn, m, org, "council_walkout", _raise(conn, "council_walkout"), day, actor=head_of(conn, org))
            n += 1
        if len(members(conn, cid)) < int(_v(conn, d.get("min_seats"), 3)):
            _end(conn, cid, day, "too few")
    return n


def _recent_kills(conn, victim_org: int, killer_org: int, day: int) -> int:
    since = int(day) - int(_v(conn, cd(conn).get("lookback_days"), 365.0))
    return int(conn.execute("SELECT COUNT(*) FROM org_tension_acts WHERE kind='killing' AND from_org=? AND to_org=? AND day>=?", (int(victim_org), int(killer_org), since)).fetchone()[0])


def _rule(conn, day: int) -> int:
    d = cd(conn)
    rd = d.get("rule") or {}
    n = 0
    for cid in active(conn):
        ms = members(conn, cid)
        nrm = norm(conn, cid, day)
        for i, a in enumerate(ms):
            for b in ms[i + 1:]:
                h = max(ot.heat(conn, a, b, day), ot.heat(conn, b, a, day))
                if h <= 0 or _rng(conn, "rule", cid, a, b, day).random() >= _v(conn, rd.get("rate"), 0.0) * h:
                    continue
                ha, hb = head_of(conn, a), head_of(conn, b)
                if ha is None or hb is None:
                    continue
                said = {}
                for me, other, hm in ((a, b, ha), (b, a, hb)):
                    f = ot.factors(conn, hm, me, other, day)
                    f["council"] = nrm
                    f["owes"] = clamp01((_recent_kills(conn, other, me, day) - _recent_kills(conn, me, other, day)) / max(1.0, _v(conn, rd.get("owes_full"), 1.0)))
                    said[me] = _rng(conn, "ruling", cid, me, other, day).random() < _blend(conn, rd["accept"], f)
                    imposed(conn, hm)
                if said[a] and said[b]:
                    delta = _v(conn, rd.get("delta")) * (0.5 + nrm)
                    ot.add(conn, a, b, "council_ruling", -delta, day, actor=ha)
                    ot.add(conn, b, a, "council_ruling", -delta, day, actor=hb)
                    pts = _v(conn, rd.get("relation"), 0.0)
                    for x, y in ((ha, hb), (hb, ha)):
                        adjust_relationship(conn, x, y, int(day), respect_delta=pts, trust_delta=pts / 2.0, resentment_delta=-pts)
                    owed_a, owed_b = _recent_kills(conn, a, b, day), _recent_kills(conn, b, a, day)  # a lost owed_a men to b
                    payer, payee, count = (b, a, owed_a - owed_b) if owed_a > owed_b else (a, b, owed_b - owed_a)
                    if count > 0:
                        from . import org_dealings
                        org_dealings.settle_up(conn, payer, payee, count * _v(conn, rd.get("redress_per_death"), 0.0), "council ruling", day)
                    _move(conn, cid, _v(conn, rd.get("standing_up"), 0.0), day, "ruled", a, b, None, "kept")
                else:
                    for me, other in ((a, b), (b, a)):
                        if not said[me]:
                            ot.add(conn, other, me, "council_defied", _raise(conn, "council_defied"), day, actor=head_of(conn, me))
                            for w in ms:
                                if w not in (a, b):
                                    ot.add(conn, w, me, "council_witness", _raise(conn, "council_witness"), day, actor=head_of(conn, me))
                    _move(conn, cid, -_v(conn, rd.get("standing_down"), 0.0) * (1 if said[a] != said[b] else 2), day, "ruled", a, b, None, "defied")
                n += 1
    return n


# ---- the table and a strike ----

def strike_verdict(conn: sqlite3.Connection, plan: dict, day: int, sanctioned: bool) -> str | None:
    """A strike by one member of a table on another is put to the table. Returns None where no table binds the pair, `approved` when the table
    weighs the provocation enough to let it stand, `defied` when it refused and the voice weighed breaking its ruling anyway (it binds in
    honour and is broken at a price), `barred` when it refused and he did not."""
    F, T, voice = int(plan["from"]), int(plan["to"]), int(plan["voice"])
    b = binding(conn, F, T, day)
    if b is None:
        return None
    cid, nrm = b
    d = cd(conn).get("strike") or {}
    f = ot.factors(conn, voice, F, T, day)
    full = max(1.0, _v(conn, d.get("struck_full"), 1.0))
    f.update({"council": nrm, "provoked": f["heat"], "struck_first": clamp01(_recent_kills(conn, F, T, day) / full), "they_struck": clamp01(_recent_kills(conn, T, F, day) / full)})
    verdict = "approved" if _rng(conn, "verdict", cid, F, T, day).random() < _blend(conn, d["approve"], f) else None
    if verdict is None:
        verdict = "defied" if _rng(conn, "defy", cid, F, T, day).random() < _blend(conn, d["defy"], f) else "barred"
    hF = head_of(conn, F)
    if verdict == "approved":
        _move(conn, cid, _v(conn, d.get("approved_standing"), 0.0), day, "sanctioned", F, T, voice, f"{plan.get('rung')}/{plan.get('method')}")
    elif verdict == "barred":
        _move(conn, cid, _v(conn, d.get("barred_standing"), 0.0), day, "barred", F, T, voice, None)
    else:
        _move(conn, cid, -_v(conn, d.get("breach_cost"), 0.0), day, "broken", F, T, voice, f"{plan.get('rung')}/{plan.get('method')}")
        for w in members(conn, cid):
            if w != F:
                ot.add(conn, w, F, "council_breach", _raise(conn, "council_breach"), day, actor=voice)
                if hF is not None and head_of(conn, w) is not None:
                    pts = _v(conn, d.get("breach_relation"), 0.0)
                    adjust_relationship(conn, head_of(conn, w), hF, int(day), respect_delta=-pts, trust_delta=-pts)
    return verdict


def on_killing(conn: sqlite3.Connection, victim_org: int, killer_org: int, sanctioned: bool, day: int) -> None:
    """Members killing each other in spite of the table, with no leave from it, costs the table its standing."""
    b = binding(conn, victim_org, killer_org, day)
    if b is not None and not sanctioned:
        _move(conn, b[0], -_v(conn, cd(conn).get("killing_cost"), 0.0), day, "killing", victim_org, killer_org)


def census(conn: sqlite3.Connection) -> dict:
    """For reports: councils formed, how they ended, their acts."""
    return {"formed": int(conn.execute("SELECT COUNT(*) FROM org_councils").fetchone()[0]),
            "ended": {str(r[0]): int(r[1]) for r in conn.execute("SELECT COALESCE(end_reason,'active'),COUNT(*) FROM org_councils GROUP BY 1")},
            "acts": {str(r[0]): int(r[1]) for r in conn.execute("SELECT kind,COUNT(*) FROM org_council_acts GROUP BY 1")}}
