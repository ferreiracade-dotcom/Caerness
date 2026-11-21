"""The understanding between the families: tension between organisations, and the people who raise and ease it (task B12e). Generic; the package's words and
figures are outfits data `tension` (each figure a Design proposal with its reasoning in design_figures.json).

State. `org_tension(from_org, to_org, level)` is directional: how much `from` is aggrieved at, or pressed by, `to`. It decays by a
half-life and has no upper bound; readers turn it into a 0..1 heat with level/(level + scale). Every change is a row in
`org_tension_acts`, so a pair's history can be read back. Nothing raises it on a timer: small acts do (a line opened on another's
ground, a man changing sides, a beating, a slight, a killing, a refused sit-down) and small acts ease it (a message, a meeting, a
sit-down with a mediator, redress paid, a funeral attended).

People. Each week every pair of organisations in contact is weighed from each side: the chance that someone on that side does
something about the other rises with the pair's heat. When the roll passes, one of the side's voices is drawn (by his place and his own
temper) and weighs the acts open to him with his own drives, the pair's state and what it would cost (men lost, city heat, allies,
a broker). The acts run from a message to a killing; steps can be skipped. A voice who is not his head's own asks leave or acts alone;
an unsanctioned killing puts the matter on his head's list (`answer_for_man`). A strike widens along two ladders weighed the same way:
who (the guilty man, whoever ordered it, his crew, his earners and kin, anyone of the family who can be found) and how (a quiet hit, a
hit wherever he is found, a team hitting a gathering where everyone present is at risk). No ceiling on a rung, a count or a rate.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3

from . import org_heat, org_motives, outfit_motives as om
from .design import run_seed
from .org_choices import register_agenda_action, register_executor
from .org_motives import _fig as figure
from .orgs import add_agenda, clamp01, head_of, imposed, is_living, resolve_agenda, seat_of
from .relationships import adjust_relationship

_DAY: dict = {"key": None, "orgs": None, "places": {}, "maxheat": None}


# ---- data ----

def data(conn: sqlite3.Connection) -> dict:
    return org_motives._sphere_data(conn).get("tension") or {}


def enabled(conn: sqlite3.Connection) -> bool:
    return bool(data(conn))


def _v(conn, spec, default: float = 0.0) -> float:
    return org_motives._value(conn, spec, default)


def _name(conn: sqlite3.Connection, actor_id: int | None) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone() if actor_id is not None else None
    return str(r[0]) if r else "someone"


def _rng(conn: sqlite3.Connection, stream: str, *keys) -> random.Random:
    return random.Random(f"{run_seed(conn)}:tension:{stream}:" + ":".join(str(int(k)) for k in keys))


def _today(conn: sqlite3.Connection, day: int) -> dict:
    key = (org_motives.db_key(conn), int(day))
    if _DAY["key"] != key:
        _DAY.update(key=key, orgs=None, places={}, maxheat=None, press={})
    return _DAY


# ---- the state ----

def _half(conn) -> float:
    return _v(conn, data(conn).get("half_life_days"), 0.0)


def level(conn: sqlite3.Connection, a: int, b: int, day: int) -> float:
    r = conn.execute("SELECT level,updated_day FROM org_tension WHERE from_org=? AND to_org=?", (int(a), int(b))).fetchone()
    if r is None:
        return 0.0
    half = _half(conn)
    return float(r[0]) if half <= 0 or day <= r[1] else float(r[0]) * 0.5 ** ((int(day) - int(r[1])) / half)


def heat(conn: sqlite3.Connection, a: int, b: int, day: int) -> float:
    """0..1: how hot `a` runs toward `b`, level/(level + scale); a very hot pair keeps rising and is read with diminishing weight."""
    lv = level(conn, a, b, day)
    return lv / (lv + max(1e-9, _v(conn, data(conn).get("scale"), 1.0)))


def add(conn: sqlite3.Connection, a: int, b: int, kind: str, delta: float, day: int, *, actor: int | None = None, victim: int | None = None,
        note: str | None = None) -> float:
    """Move the tension of `a` toward `b` by `delta` (negative eases it), write the act, and return the new level. The level cannot go
    below nothing; it has no top."""
    if not enabled(conn) or int(a) == int(b) or delta == 0:
        return 0.0
    new = max(0.0, level(conn, a, b, day) + float(delta))
    conn.execute("""INSERT INTO org_tension(from_org,to_org,level,updated_day,peak) VALUES (?,?,?,?,?)
                    ON CONFLICT(from_org,to_org) DO UPDATE SET level=excluded.level,updated_day=excluded.updated_day,peak=MAX(peak,excluded.level)""",
                 (int(a), int(b), new, int(day), new))
    conn.execute("INSERT INTO org_tension_acts(day,from_org,to_org,kind,delta,actor_id,victim_id,note) VALUES (?,?,?,?,?,?,?,?)",
                 (int(day), int(a), int(b), kind, float(delta), actor, victim, note))
    _today(conn, day)["maxheat"] = None
    return new


def _raise(conn, name: str) -> float:
    return _v(conn, (data(conn).get("raise") or {}).get(name), 0.0)


def _rank(conn: sqlite3.Connection, role: str | None) -> float:
    from .org_happenings import _killing
    return _v(conn, (_killing(conn).get("role_rank") or {}).get(role), 0.5)


# ---- hooks the rest of the layer calls (each a small act that moves a pair) ----

def on_line_opened(conn: sqlite3.Connection, org: int, loc: int | None, actor: int, day: int) -> None:
    """A line or book opened on the ground of another organisation: it is aggrieved at the one that opened it."""
    if loc is None or not enabled(conn):
        return
    d = _raise(conn, "line_opened")
    if d <= 0:
        return
    for (other,) in conn.execute("SELECT DISTINCT org_actor_id FROM org_units WHERE ground_location_id=? AND status='active' AND org_actor_id<>?", (int(loc), int(org))).fetchall():
        add(conn, int(other), int(org), "line_opened", d, day, actor=actor, note="a line opened on its ground")


def on_incident(conn: sqlite3.Connection, victim_org: int | None, offender_org: int, offender: int, victim: int, kind: str, day: int, went_too_far: bool = False) -> None:
    """A man of one organisation hurt a man of another: the one that was hurt is aggrieved at the one that did it."""
    d = _raise(conn, "incident")
    if d > 0 and enabled(conn) and victim_org is not None and int(victim_org) != int(offender_org):
        add(conn, int(victim_org), int(offender_org), "incident", d, day, actor=offender, victim=victim, note=kind)


def on_killing(conn: sqlite3.Connection, killer: int, victim: int, victim_org: int, killer_orgs, role: str | None, sanctioned: bool, day: int) -> None:
    d = _raise(conn, "killing")
    if d <= 0 or not enabled(conn):
        return
    rank = _rank(conn, role)
    d *= _v(conn, (data(conn).get("rank_scale") or {}).get("base"), 1.0) + _v(conn, (data(conn).get("rank_scale") or {}).get("rank"), 0.0) * rank
    if not sanctioned:
        d *= 1.0 + _raise(conn, "unsanctioned")
    for k in sorted(int(x) for x in killer_orgs):
        add(conn, int(victim_org), k, "killing", d, day, actor=killer, victim=victim, note=str(role or ""))


def on_answer(conn: sqlite3.Connection, a: int, b: int, name: str, day: int, *, actor: int | None = None, victim: int | None = None) -> None:
    """A named raise or ease from the package's `raise` table (refused redress, refused peace, settled, paid...); negative eases."""
    d = _raise(conn, name)
    if d and enabled(conn):
        add(conn, int(a), int(b), name, d, day, actor=actor, victim=victim)


def seed_initial(conn: sqlite3.Connection, day: int) -> int:
    """The quarrels the setting starts with (data `initial`: from and to by organisation key, a level, the reason)."""
    by_key = {str(r[1]): int(r[0]) for r in conn.execute("SELECT org_actor_id,package_key FROM org_profiles")}
    n = 0
    for item in data(conn).get("initial") or []:
        a, b = by_key.get(item["from"]), by_key.get(item["to"])
        if a is not None and b is not None:
            add(conn, a, b, "history", _v(conn, item["level"]), int(day), note=str(item.get("why") or ""))
            n += 1
    return n


def seed_relations(conn: sqlite3.Connection, day: int) -> int:
    """How the heads of the organisations stand toward one another at the opening (data `relations`): respect, trust and familiarity drawn
    around the package's means, resentment from the old quarrel between their organisations. Without these no third head is one both sides
    hear out, and no head thinks well of another."""
    from .relationships import ensure_relationship
    rd = data(conn).get("relations")
    if not rd:
        return 0
    orgs = [int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_profiles WHERE sphere='underworld' ORDER BY org_actor_id")]
    heads = {o: head_of(conn, o) for o in orgs}
    n = 0

    def draw(rng, spec):
        return max(-100.0, min(100.0, rng.gauss(_v(conn, spec["mean"]), _v(conn, spec["sd"]))))
    res = rd["resentment"]
    for a in orgs:
        for b in orgs:
            if a == b or heads[a] is None or heads[b] is None:
                continue
            rng = random.Random(f"{run_seed(conn)}:tension:relation:{a}:{b}")
            hot = _v(conn, res["per_tension"]) * level(conn, a, b, day)
            ensure_relationship(conn, int(heads[a]), int(heads[b]), int(day), respect=draw(rng, rd["respect"]), trust=draw(rng, rd["trust"]),
                                familiarity=max(0.0, draw(rng, rd["familiarity"])),
                                resentment=max(0.0, min(100.0, rng.gauss(_v(conn, res["base"]) + hot, _v(conn, res["sd"])))))
            n += 1
    return n


# ---- who is in contact ----

def _underworld_orgs(conn: sqlite3.Connection, day: int) -> list[int]:
    t = _today(conn, day)
    if t["orgs"] is None:
        t["orgs"] = [int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_profiles WHERE sphere='underworld' ORDER BY org_actor_id") if head_of(conn, int(r[0])) is not None]
    return t["orgs"]


def _places(conn: sqlite3.Connection, org: int, day: int) -> frozenset:
    t = _today(conn, day)
    if org not in t["places"]:
        s = {int(r[0]) for r in conn.execute("SELECT ground_location_id FROM org_units WHERE org_actor_id=? AND status='active' AND ground_location_id IS NOT NULL", (int(org),))}
        s |= {int(r[0]) for r in conn.execute(
            "SELECT DISTINCT l.location_id FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active' AND l.location_id IS NOT NULL", (int(org),))}
        t["places"][org] = frozenset(s)
    return t["places"][org]


def _declared_contacts(conn: sqlite3.Connection) -> set[tuple[int, int]]:
    out: set = set()
    by_key = {str(r[1]): int(r[0]) for r in conn.execute("SELECT org_actor_id,package_key FROM org_profiles")}
    for a, b in data(conn).get("contacts") or []:
        if a in by_key and b in by_key:
            out.add((by_key[a], by_key[b]))
            out.add((by_key[b], by_key[a]))
    return out


def pairs(conn: sqlite3.Connection, day: int) -> list[tuple[int, int]]:
    """Directional pairs in contact: ground or lines in the same places, a declared tie, or tension already between them."""
    orgs = _underworld_orgs(conn, day)
    declared = _declared_contacts(conn)
    live = {(int(r[0]), int(r[1])) for r in conn.execute("SELECT from_org,to_org FROM org_tension WHERE level>0")}
    out = []
    for a in orgs:
        pa = _places(conn, a, day)
        for b in orgs:
            if a != b and ((a, b) in declared or (a, b) in live or pa & _places(conn, b, day)):
                out.append((a, b))
    return out


def _max_other_heat(conn: sqlite3.Connection, a: int, b: int, day: int) -> float:
    """The hottest other pair involving either organisation: a war nearby frays the understanding."""
    t = _today(conn, day)
    if t["maxheat"] is None:
        m: dict = {}
        for r in conn.execute("SELECT from_org,to_org,level FROM org_tension WHERE level>0").fetchall():
            h = heat(conn, int(r[0]), int(r[1]), day)
            for o in (int(r[0]), int(r[1])):
                m.setdefault(o, []).append((h, int(r[0]), int(r[1])))
        t["maxheat"] = m
    best = 0.0
    for o in (a, b):
        for h, x, y in t["maxheat"].get(o, ()):
            if {x, y} != {a, b}:
                best = max(best, h)
    return best


# ---- the people ----

def _free(conn: sqlite3.Connection, actor: int) -> bool:
    return is_living(conn, int(actor)) and conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held'", (int(actor),)).fetchone() is None


def _voices(conn: sqlite3.Connection, org: int, day: int) -> list[tuple[int, float]]:
    """(man, weight): the men of the organisation in a role the package lets speak, by the role's weight and his own aggression."""
    vd = data(conn).get("voice") or {}
    rw = {r: _v(conn, w) for r, w in (vd.get("role_weight") or {}).items()}
    if not rw:
        return []
    floor = _v(conn, vd.get("aggression_floor"), 0.2)
    q = ",".join("?" * len(rw))
    out = []
    for r in conn.execute(
            f"""SELECT s.actor_id,s.role_key,COALESCE(d.aggression,0.5) FROM org_seats s LEFT JOIN actor_drives d ON d.actor_id=s.actor_id
                WHERE s.org_actor_id=? AND s.status='active' AND s.role_key IN ({q}) ORDER BY s.actor_id""", (int(org), *sorted(rw))).fetchall():
        if _free(conn, int(r[0])):
            out.append((int(r[0]), rw[r[1]] * (floor + float(r[2]))))
    return out


def _head_weak(conn: sqlite3.Connection, head: int | None, day: int) -> float:
    """0..1: a head who is held, sick or old (data `weak`: where age begins to count and how fast, the sickness severity read as 0..1)."""
    if head is None:
        return 0.0
    w = data(conn).get("weak") or {}
    held = 1.0 if conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held'", (int(head),)).fetchone() else 0.0
    sick = conn.execute("SELECT MAX(severity) FROM health_conditions WHERE actor_id=? AND status='active'", (int(head),)).fetchone()[0]
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (int(head),)).fetchone()
    age = max(0.0, (int(day) - int(r[0])) / 365.0) if r and r[0] is not None else 0.0
    aged = clamp01((age - _v(conn, w.get("age_from"), 70.0)) / max(1e-9, _v(conn, w.get("age_span"), 20.0)))
    rest = 1.0
    for p in (held, clamp01(float(sick or 0.0) / 100.0), aged):
        rest *= 1.0 - p
    return 1.0 - rest


def protection(conn: sqlite3.Connection, man: int | None) -> tuple[float, float]:
    """What stands between a man and anyone who means to kill him, each 0..1: `guarded` (the men who answer to him, directly or through
    those under him, against the data's `guard.half`: the number at which a man is half covered) and `loved` (how loyal those who answer to
    him directly are: the men who would avenge him, or would not). A man nobody answers to has neither. No rank is named: a head's ring is
    large because the whole outfit is under him, a unit leader's is his crew, an ordinary man's is nothing."""
    if man is None:
        return 0.0, 0.0
    g = data(conn).get("guard") or {}
    half = max(1e-9, _v(conn, g.get("half"), 20.0))
    n = int(conn.execute(
        """WITH RECURSIVE under(a) AS (SELECT actor_id FROM org_seats WHERE superior_actor_id=? AND status='active' AND actor_id<>?
             UNION SELECT s.actor_id FROM org_seats s JOIN under u ON s.superior_actor_id=u.a WHERE s.status='active' AND s.actor_id<>?)
           SELECT COUNT(*) FROM under""", (int(man), int(man), int(man))).fetchone()[0])
    direct = [int(r[0]) for r in conn.execute("SELECT DISTINCT actor_id FROM org_seats WHERE superior_actor_id=? AND status='active' AND actor_id<>?", (int(man), int(man)))]
    loyal = []
    for d in direct:
        r = om._rel(conn, d, int(man))
        loyal.append(clamp01(float(r["loyalty"]) / 100.0) if r is not None else 0.0)
    return n / (n + half), (sum(loyal) / len(loyal) if loyal else 0.0)


def factors(conn: sqlite3.Connection, voice: int, F: int, T: int, day: int) -> dict[str, float]:
    """Everything a voice of F weighs about T today, each 0..1 (the package's terms name them)."""
    from .org_happenings import _cost_factors, _sees, _size
    f = _cost_factors(conn, int(voice), int(F), int(T), int(day), 1)
    own_head, their_head = head_of(conn, F), head_of(conn, T)
    mine, theirs = _size(conn, F), _size(conn, T)
    h, hb = heat(conn, F, T, day), heat(conn, T, F, day)
    rel = om._rel(conn, voice, their_head)
    pa, pb = _places(conn, F, day), _places(conn, T, day)
    own_weak = _head_weak(conn, own_head, day) if own_head != voice else 0.0
    guarded, loved = protection(conn, their_head)
    f.update({"their_head_guarded": guarded, "their_head_loved": loved,
              "unbacked": 0.0 if own_head == voice else 1.0,  # a voice who is not his own head's has not yet his leave
              "heat": h, "heat_back": hb, "calm": 1.0 - h, "always": 1.0,
              "aggression": om._drive(conn, voice, "aggression"), "ambition": om._drive(conn, voice, "ambition"),
              "caution": 1.0 - om._drive(conn, voice, "risk_tolerance"), "patience": om._drive(conn, voice, "patience"),
              "pragmatism": om._drive(conn, voice, "pragmatism"),
              "friendly": _sees(conn, voice, their_head),
              "grievance": 0.0 if rel is None else clamp01(float(rel["resentment"]) / 100.0),
              "stronger": clamp01(1.0 - theirs / mine) if mine and theirs < mine else 0.0,
              "their_head_weak": _head_weak(conn, their_head, day), "own_head_weak": own_weak,
              "ambition_open": om._drive(conn, voice, "ambition") * own_weak,
              "war_near": _max_other_heat(conn, F, T, day),
              "shared_ground": clamp01(len(pa & pb) / max(1, len(pa | pb)))})
    return f


def _blend(conn, terms, f: dict[str, float]) -> float:
    from .org_happenings import _blend as blend
    return blend(conn, terms, f)


def _against(conn, terms, f: dict[str, float]) -> float:
    from .org_happenings import _against as against
    return against(conn, terms, f)


def _softmax_pick(conn, scored: list[tuple[str, float]], rng: random.Random) -> str | None:
    if not scored:
        return None
    beta = _v(conn, data(conn).get("beta"), 6.0)
    top = max(s for _, s in scored)
    w = [(k, math.exp(beta * (s - top))) for k, s in scored]
    pick = rng.random() * sum(x for _, x in w)
    for k, x in w:
        pick -= x
        if pick < 0:
            return k
    return w[-1][0]


# ---- the weekly weighing ----

def next_chance(conn: sqlite3.Connection, F: int, T: int, day: int) -> float:
    """The week's chance that someone on F's side does something about T: a base plus a share of F's heat toward T and of T's toward F."""
    p = data(conn).get("pair") or {}
    return clamp01(_v(conn, p.get("base"), 0.0) + _v(conn, p.get("per_heat"), 0.0) * heat(conn, F, T, day) + _v(conn, p.get("per_heat_back"), 0.0) * heat(conn, T, F, day))


def process_due(conn: sqlite3.Connection, day: int) -> dict:
    if not enabled(conn):
        return {}
    out: dict = {}
    for F, T in pairs(conn, day):
        if _rng(conn, "pair", F, T, day).random() >= next_chance(conn, F, T, day):
            continue
        res = weigh_pair(conn, F, T, day)
        if res:
            out[res["act"]] = out.get(res["act"], 0) + 1
    return out


def draw_voice(conn: sqlite3.Connection, F: int, T: int, day: int) -> int | None:
    vs = _voices(conn, F, day)
    total = sum(w for _, w in vs)
    if total <= 0:
        return None
    pick = _rng(conn, "voice", F, T, day).random() * total
    for a, w in vs:
        pick -= w
        if pick < 0:
            return a
    return vs[-1][0]


def weigh_pair(conn: sqlite3.Connection, F: int, T: int, day: int, *, voice: int | None = None, only: str | None = None) -> dict | None:
    """One voice of F weighs what to do about T and does it. `voice` and `only` let a test force the man or the act."""
    voice = draw_voice(conn, F, T, day) if voice is None else int(voice)
    if voice is None:
        return None
    f = factors(conn, voice, F, T, day)
    acts = data(conn).get("acts") or {}
    scored = []
    for name, spec in sorted(acts.items()):
        if only is not None and name != only:
            continue
        scored.append((name, _blend(conn, spec.get("terms") or [], f)))
    rng = _rng(conn, "act", F, T, day)
    pick = None
    while scored:  # an act he cannot do here (no one to carry a message to, no ground to press) is dropped and the rest weighed again: feasibility is only asked of what is drawn
        pick = _softmax_pick(conn, scored, rng)
        if _feasible(conn, acts[pick], voice, F, T, day):
            break
        scored = [x for x in scored if x[0] != pick]
        pick = None
    if pick is None or acts[pick].get("do") == "none":
        return None
    spec = acts[pick]
    res = _DO[spec["do"]](conn, voice, F, T, day, pick, spec, f) or {}
    imposed(conn, voice)
    res.update(act=pick, voice=voice, kind=spec["do"])
    return res


def _feasible(conn, spec: dict, voice: int, F: int, T: int, day: int) -> bool:
    do = spec.get("do")
    if do == "none":
        return True
    if do in ("ease", "slight"):
        return head_of(conn, T) is not None
    if do == "sit_down":
        return head_of(conn, T) is not None and _mediator(conn, voice, F, T, day) is not None
    if do == "press_ground":
        return _press_choice(conn, voice, F, T, day) is not None
    if do == "squeeze":
        return bool(_victims(conn, "earners_kin", voice, F, T, day))
    if do == "levy":
        from .org_happenings import _size
        return head_of(conn, T) is not None and _size(conn, T) < _size(conn, F) and _weekly_take(conn, T) > 0
    if do == "strike":
        return bool(_victims(conn, "anyone", voice, F, T, day))
    return False


# ---- acts ----

def _do_ease(conn, voice, F, T, day, name, spec, f):
    """A message, a meeting, a courtesy: it eases both sides a little and the two men think better of each other."""
    d, other = _v(conn, spec["delta"]), head_of(conn, T)
    pts = _v(conn, spec.get("relation"), 0.0)
    add(conn, F, T, name, -d, day, actor=voice)
    add(conn, T, F, name, -d * _v(conn, spec.get("reciprocal"), 1.0), day, actor=voice)
    if other is not None and pts:
        adjust_relationship(conn, voice, other, int(day), respect_delta=pts, trust_delta=pts / 2.0, resentment_delta=-pts)
        adjust_relationship(conn, other, voice, int(day), respect_delta=pts, trust_delta=pts / 2.0, resentment_delta=-pts)
        imposed(conn, other)
    return {"summary": f"{_name(conn, voice)} sent word to {_name(conn, other)}."}


def _mediator(conn, voice: int, F: int, T: int, day: int) -> int | None:
    """The third head both sides hear out best (respect and trust of both, weighted by his weight in the city); None where no one is heard by both."""
    from .org_happenings import _sees, _size
    hF, hT = head_of(conn, F), head_of(conn, T)
    best, who = 0.0, None
    biggest = max([_size(conn, o) for o in _underworld_orgs(conn, day)] or [1])
    for o in _underworld_orgs(conn, day):
        if o in (F, T):
            continue
        m = head_of(conn, o)
        if m is None or not _free(conn, m):
            continue
        w = min(_sees(conn, hF, m), _sees(conn, hT, m)) * math.sqrt(_size(conn, o) / max(1, biggest))
        if w > best:
            best, who = w, int(m)
    return who


def _do_sit_down(conn, voice, F, T, day, name, spec, f):
    """A sit-down through a mediator. The other head weighs whether to come with his own costs; peace eases both ways, a refusal sours."""
    from .org_happenings import _sees
    hT = head_of(conn, T)
    med = _mediator(conn, voice, F, T, day)
    fT = factors(conn, hT, T, F, day)
    fT["mediator"] = min(_sees(conn, voice, med), _sees(conn, hT, med))
    p = _blend(conn, spec["accept"], fT)
    d = _v(conn, spec["delta"])
    pts = _v(conn, spec.get("relation"), 0.0)
    imposed(conn, hT)
    if _rng(conn, "sit", F, T, day).random() < p:
        w = 1.0 + _v(conn, spec.get("mediator_weight"), 0.0) * fT["mediator"]
        add(conn, F, T, name, -d * w, day, actor=voice)
        add(conn, T, F, name, -d * w, day, actor=voice)
        for a, b in ((voice, hT), (hT, voice), (voice, med), (hT, med)):
            adjust_relationship(conn, a, b, int(day), respect_delta=pts, trust_delta=pts / 2.0, resentment_delta=-pts)
        return {"summary": f"{_name(conn, voice)} and {_name(conn, hT)} sat down with {_name(conn, med)} and settled it.", "settled": True}
    add(conn, F, T, name + "_refused", _v(conn, spec.get("refused_delta"), 0.0), day, actor=voice)
    adjust_relationship(conn, voice, hT, int(day), resentment_delta=pts, respect_delta=-pts / 2.0)
    return {"summary": f"{_name(conn, hT)} would not sit down with {_name(conn, voice)}.", "settled": False}


def _do_slight(conn, voice, F, T, day, name, spec, f):
    """An insult: the other side is aggrieved at F, and F's own man is a little more sure of his case."""
    d = _v(conn, spec["delta"])
    add(conn, T, F, name, d, day, actor=voice)
    add(conn, F, T, name + "_own", d * _v(conn, spec.get("own_share"), 0.0), day, actor=voice)
    other = head_of(conn, T)
    if other is not None:
        adjust_relationship(conn, other, voice, int(day), resentment_delta=_v(conn, spec.get("relation"), 0.0), respect_delta=-_v(conn, spec.get("relation"), 0.0) / 2.0)
        imposed(conn, other)
    return {"summary": f"{_name(conn, voice)} slighted {_name(conn, other)}."}


def _press_choice(conn, voice: int, F: int, T: int, day: int):
    """(location, pool, opportunity): a place on T's ground where `voice` could open a line he has the money for; None where he cannot."""
    memo = _today(conn, day).setdefault("press", {})
    k = (int(voice), int(F), int(T))
    if k not in memo:
        memo[k] = _press_best(conn, voice, F, T, day)
    return memo[k]


def _press_best(conn, voice: int, F: int, T: int, day: int):
    seat = seat_of(conn, voice, F)
    if seat is None:
        return None
    cost = om.start_cost(conn, seat["role_key"])
    from . import ledger
    if ledger.balance(conn, ("person", int(voice))) < cost:
        return None
    best = None
    for loc in sorted(_places(conn, T, day)):
        for pool in om._pools(conn):
            o = om.opportunity(conn, voice, day, loc, pool)
            if o > 0 and (best is None or o > best[2]):
                best = (loc, pool, o)
    return best


def _do_press_ground(conn, voice, F, T, day, name, spec, f):
    from . import outfit_choices
    loc, pool, opp = _press_choice(conn, voice, F, T, day)
    cost = om.start_cost(conn, seat_of(conn, voice, F)["role_key"])
    res = outfit_choices.execute_start_racket(conn, voice, "start_racket", {"org": F, "location_id": loc, "pool": pool, "opportunity": opp, "cost": cost}, day)
    return {"summary": res.get("summary", "")}


def _victims(conn, rung: str, voice: int, F: int, T: int, day: int) -> list[int]:
    """The men of T on a rung of the ladder who can be found: guilty (the man who last wronged F), orderer (T's head), crew (his unit
    mates), earners_kin (line holders and kin of the guilty or the head who are in the life), anyone (any seated man of T)."""
    free = lambda ids: [i for i in ids if _free(conn, i) and seat_of(conn, i, T) is not None]  # noqa: E731
    g = conn.execute("SELECT actor_id FROM org_tension_acts WHERE from_org=? AND to_org=? AND actor_id IS NOT NULL AND delta>0 ORDER BY id DESC LIMIT 1", (int(F), int(T))).fetchone()
    guilty = [int(g[0])] if g is not None else []
    if rung == "guilty":
        return free(guilty)
    if rung == "orderer":
        h = head_of(conn, T)
        return free([h] if h is not None else [])
    if rung == "crew":
        units = {int(r[0]) for i in guilty for r in conn.execute("SELECT unit_id FROM org_seats WHERE actor_id=? AND org_actor_id=? AND unit_id IS NOT NULL", (i, T))}
        mates = [int(r[0]) for u in sorted(units) for r in conn.execute("SELECT actor_id FROM org_seats WHERE unit_id=? AND status='active' ORDER BY actor_id", (u,))]
        return free(mates)
    if rung == "earners_kin":
        earners = [int(r[0]) for r in conn.execute(
            "SELECT DISTINCT l.holder_actor_id FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active' AND l.holder_actor_id IS NOT NULL ORDER BY 1", (int(T),))]
        key = [i for i in (guilty + [head_of(conn, T)]) if i is not None]
        kin = []
        for k in key:
            kin += [int(r[0]) for r in conn.execute(
                """SELECT CASE WHEN actor_a_id=? THEN actor_b_id ELSE actor_a_id END FROM kinship_links WHERE (actor_a_id=? OR actor_b_id=?)
                   AND legal_status='recognized' AND ended_day IS NULL AND kin_kind IN ('parent','child','sibling','spouse')""", (k, k, k))]
        return free(sorted(set(earners + kin)))
    return free([int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY actor_id", (int(T),))])


def _pick_victim(conn, vs: list[int], rng: random.Random, T: int, F: int, voice: int, day: int) -> int:
    """One of the men on the rung. T's head is harder to get at than any of the others: his guards, the men who would avenge him and the
    voice's own want of backing take a share off his weight (data `guard.cover`, the same blend as every other counter-term)."""
    head = head_of(conn, T)
    if head is None or head not in vs or len(vs) == 1:
        return vs[rng.randrange(len(vs))]
    f = factors(conn, voice, F, T, day)
    reach = 1.0 - _against(conn, (data(conn).get("guard") or {}).get("cover") or [], f)
    w = [reach if x == head else 1.0 for x in vs]
    return rng.choices(vs, weights=w, k=1)[0]


def _do_squeeze(conn, voice, F, T, day, name, spec, f):
    """A beating of one of T's earners or men: the weekly incident, aimed."""
    from .org_happenings import run_incident
    vs = _victims(conn, "earners_kin", voice, F, T, day)
    rng = _rng(conn, "squeeze", F, T, day)
    v = vs[rng.randrange(len(vs))]
    res = run_incident(conn, voice, F, day, rng, v, T)
    return {"summary": res.get("summary", "")}


def _weekly_take(conn, org: int) -> float:
    return float(conn.execute("SELECT COALESCE(SUM(l.weekly_take),0) FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active'", (int(org),)).fetchone()[0])


def _do_levy(conn, voice, F, T, day, name, spec, f):
    """Protection: the stronger side asks a weaker organisation's head to pay against trouble. He weighs paying with his own costs; paying
    buys a little quiet, refusing is remembered."""
    from . import ledger
    payer = head_of(conn, T)
    amount = round(_weekly_take(conn, T) * _v(conn, spec["weeks"]) * _v(conn, spec["share"]), 2)
    fp = factors(conn, payer, T, F, day)
    p = _blend(conn, spec["pay"], fp)
    imposed(conn, payer)
    if _rng(conn, "levy", F, T, day).random() < p:
        paid = ledger.transfer(conn, ("person", int(payer)), ("person", int(voice)), amount, flow_kind="tribute", purpose="protection", allow_partial=True) if amount > 0 else 0.0
        if paid > 0:
            add(conn, T, F, "levy_paid", -_v(conn, spec["ease"]), day, actor=voice)
            return {"summary": f"{_name(conn, payer)} paid {_name(conn, voice)} ${paid:,.0f} for protection."}
    add(conn, T, F, "levy_refused", _v(conn, spec["refuse"]), day, actor=voice)
    adjust_relationship(conn, payer, voice, int(day), resentment_delta=_v(conn, spec["refuse"]))
    return {"summary": f"{_name(conn, payer)} would not pay {_name(conn, voice)}."}


def _hirable(conn, F: int, day: int) -> int | None:
    """A free man a head can hire: a seated man of an organisation the package lists as working for hire (data `hire.orgs`), not one of F's own."""
    keys = list((data(conn).get("hire") or {}).get("orgs") or [])
    if not keys:
        return None
    q = ",".join("?" * len(keys))
    for (a,) in conn.execute(
            f"""SELECT s.actor_id FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id WHERE p.package_key IN ({q}) AND s.status='active'
                AND p.org_actor_id<>? ORDER BY s.actor_id""", (*keys, int(F))).fetchall():
        if _free(conn, int(a)):
            return int(a)
    return None


# ---- strike: who, and how ----

def _team(conn, F: int, voice: int, size: int, exclude=()) -> list[int]:
    roles = list(data(conn).get("team_roles") or [])
    q = ",".join("?" * len(roles)) if roles else ""
    rows = conn.execute(f"SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' {('AND role_key IN (' + q + ')') if roles else ''} ORDER BY actor_id",
                        (int(F), *roles)).fetchall()
    ranked = []
    for (a,) in rows:
        a = int(a)
        if a in exclude or a == voice or not _free(conn, a):
            continue
        rel = om._rel(conn, a, voice)
        ranked.append((float(rel["loyalty"]) if rel is not None else 0.0, -a, a))
    team = [a for _l, _n, a in sorted(ranked, reverse=True)[:max(0, int(size))]]
    return team or ([int(voice)] if _free(conn, voice) else [])


def _venue(conn, T: int) -> tuple[int, list[int]] | None:
    """The place where most of T's men are together now (data `gathering.min_present` or more), and everyone there."""
    need = int(_v(conn, (data(conn).get("gathering") or {}).get("min_present"), 2))
    r = conn.execute(
        """SELECT a.current_location_id,COUNT(*) c FROM org_seats s JOIN actors a ON a.id=s.actor_id WHERE s.org_actor_id=? AND s.status='active'
           AND a.current_location_id IS NOT NULL AND a.status='active' GROUP BY 1 HAVING c>=? ORDER BY c DESC,1 LIMIT 1""", (int(T), need)).fetchone()
    if r is None:
        return None
    people = [int(x[0]) for x in conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' AND current_location_id=? ORDER BY id", (int(r[0]),)) if is_living(conn, int(x[0]))]
    return int(r[0]), people


def _rung_scores(conn, ladder: str, voice, F, T, day, f) -> list[tuple[str, float]]:
    out = []
    for rung in (data(conn).get("ladders") or {}).get(ladder) or []:
        if ladder == "targets" and not _victims(conn, rung["name"], voice, F, T, day):
            continue
        if ladder == "methods" and rung["name"] == "gathering" and _venue(conn, T) is None:
            continue
        if ladder == "methods" and rung["name"] == "hired" and _hirable(conn, F, day) is None:
            continue
        out.append((rung["name"], _blend(conn, rung.get("terms") or [], f)))
    return out


def plan_strike(conn, voice: int, F: int, T: int, day: int, f: dict | None = None, rng: random.Random | None = None) -> dict | None:
    f = f if f is not None else factors(conn, voice, F, T, day)
    rng = rng or _rng(conn, "plan", F, T, day)
    rung = _softmax_pick(conn, _rung_scores(conn, "targets", voice, F, T, day, f), rng)
    method = _softmax_pick(conn, _rung_scores(conn, "methods", voice, F, T, day, f), rng)
    return None if rung is None or method is None else {"from": F, "to": T, "voice": voice, "rung": rung, "method": method}


def _do_strike(conn, voice, F, T, day, name, spec, f):
    plan = plan_strike(conn, voice, F, T, day, f)
    if plan is None:
        return {"summary": "He found no one to hit."}
    head = head_of(conn, F)
    sd = data(conn).get("sanction") or {}
    if head is not None and head != voice:
        tie = om._rel(conn, voice, head)
        tie_v = clamp01(float(tie["trust"]) / 100.0) if tie is not None else 0.0
        ask = clamp01((1.0 - (1.0 - f["caution"]) * (1.0 - tie_v)) * (1.0 - _v(conn, sd.get("fear_share"), 0.0) * f["aggression"]))
        if _rng(conn, "ask", F, T, day).random() < ask:
            add_agenda(conn, head, "sanction_strike", int(day) + int(_v(conn, sd.get("delay_days"), 1)), subject_kind="actor", subject_id=int(voice), metadata=plan)
            imposed(conn, head)
            return {"summary": f"{_name(conn, voice)} asked {_name(conn, head)} for leave to strike {_name(conn, head_of(conn, T))}'s people.", "asked": True}
    return execute_strike(conn, plan, day, sanctioned=head == voice)


def _drift(conn, actor, cause, day):
    from . import org_temperament
    org_temperament.drift(conn, int(actor), cause, int(day))


def execute_strike(conn, plan: dict, day: int, *, sanctioned: bool) -> dict:
    """Carry out a planned strike: pick the man on the rung, then the method's way of reaching him. Everything is lethal through the
    existing hit machinery, so it can miss, wound, maim or kill; a gathering reaches everyone present."""
    from .outfit_choices import kill
    F, T, voice, rung, method = int(plan["from"]), int(plan["to"]), int(plan["voice"]), plan["rung"], plan["method"]
    rng = _rng(conn, "strike", F, T, day)
    md = (data(conn).get("methods") or {}).get(method) or {}
    team_n = int(round(_v(conn, md.get("team"), 1.0)))
    land = _v(conn, md.get("land"), 0.5)
    style = md.get("style", "assault")
    head = head_of(conn, F)
    dead: list[int] = []
    summary = ""
    if method == "gathering":
        ven = _venue(conn, T)
        if ven is None:
            return {"summary": "There was no one gathered to hit."}
        loc, people = ven
        team = _team(conn, F, voice, team_n)
        gd = data(conn).get("gathering") or {}
        wt, wo = _v(conn, gd.get("w_target"), 1.0), _v(conn, gd.get("w_other"), 1.0)
        mine = {int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active'", (T,))}
        pool = [p for p in people if p not in team]
        for p in pool:
            imposed(conn, p)
        for shooter in team:
            for _ in range(int(round(_v(conn, gd.get("shots"), 3.0)))):
                alive = [p for p in pool if is_living(conn, p)]
                if not alive:
                    break
                v = rng.choices(alive, weights=[wt if p in mine else wo for p in alive], k=1)[0]
                kill(conn, shooter, v, day, sanctioned=sanctioned, land=land, style=style)
                if not is_living(conn, v):
                    dead.append(v)
        summary = f"A team from {_name(conn, head)}'s side hit {_name(conn, head_of(conn, T))}'s men at a gathering: {len(dead)} dead of {len(pool)} present."
    else:
        vs = _victims(conn, rung, voice, F, T, day)
        if not vs:
            return {"summary": "He found no one to hit."}
        victim = _pick_victim(conn, vs, rng, T, F, voice, day)
        team = _team(conn, F, voice, team_n)
        if method == "found":
            for shooter in team:
                if not is_living(conn, victim):
                    break
                kill(conn, shooter, victim, day, sanctioned=sanctioned, land=land, style=style)
            if not is_living(conn, victim):
                dead.append(victim)
            summary = f"{_name(conn, voice)}'s men went after {_name(conn, victim)}" + (" and killed him." if dead else " and failed.")
        elif method == "hired":  # a man who works for hire is paid and given the job: the dead man's head will hunt whoever hired it
            from . import ledger
            man = _hirable(conn, F, day)
            if man is None:
                return {"summary": "He could find no one to hire."}
            ledger.transfer(conn, ("person", int(voice)), ("person", int(man)), _v(conn, md.get("fee"), 0.0), flow_kind="wage", purpose="a job", allow_partial=True)
            add_agenda(conn, man, "hit", int(day) + int(_v(conn, md.get("delay_days"), 1)), subject_kind="actor", subject_id=int(victim),
                       metadata={"sanctioned": sanctioned, "ordered_by": voice, "org": F, "tension": True, "hired": True})
            team = [man]
            summary = f"{_name(conn, voice)} hired {_name(conn, man)} for {_name(conn, victim)}."
        else:  # quiet: the men are given the job and carry it out when they can
            for a in team:
                add_agenda(conn, a, "hit", int(day) + int(_v(conn, md.get("delay_days"), 1)), subject_kind="actor", subject_id=int(victim),
                           metadata={"sanctioned": sanctioned, "ordered_by": voice, "org": F, "tension": True})
            summary = f"{_name(conn, voice)} put {len(team)} men on {_name(conn, victim)}."
    conn.execute("INSERT INTO org_tension_acts(day,from_org,to_org,kind,delta,actor_id,victim_id,note) VALUES (?,?,?,?,?,?,?,?)",
                 (int(day), F, T, "strike", 0.0, voice, dead[0] if dead else None, f"{rung}/{method}/dead={len(dead)}"))
    if method != "quiet" and not dead:
        add(conn, T, F, "attempt", _raise(conn, "attempt"), day, actor=voice)
    for a in {voice, *team}:
        imposed(conn, a)
        _drift(conn, a, "strike", day)
    if not sanctioned and head is not None and head != voice:
        add_agenda(conn, head, "answer_for_man", int(day) + int(_v(conn, (data(conn).get("sanction") or {}).get("delay_days"), 1)), subject_kind="actor", subject_id=voice,
                   metadata={"from": F, "to": T, "man": voice, "dead": dead[:1] or None})
        imposed(conn, head)
    return {"summary": summary, "dead": dead}


# ---- the head's lists: sanction_strike, answer_for_man ----

def sanction_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    from .org_happenings import _utility
    plan = json.loads(item["metadata_json"] or "{}")
    F, T = int(plan["from"]), int(plan["to"])
    f = factors(conn, int(actor_id), F, T, day)
    f["own_voice"] = om._rel(conn, actor_id, plan["voice"]) is not None and clamp01(float(om._rel(conn, actor_id, plan["voice"])["trust"]) / 100.0) or 0.0
    spec = (data(conn).get("acts") or {}).get("strike") or {}
    sd = data(conn).get("sanction") or {}
    yes = _blend(conn, sd.get("approve") or spec.get("terms") or [], f)
    return [{"kind": "approve_strike", "utility": _utility(conn, yes), "rationale": f"Lets {_name(conn, plan['voice'])} strike.", "payload": plan},
            {"kind": "refuse_strike", "utility": _utility(conn, 1.0 - yes), "rationale": f"Tells {_name(conn, plan['voice'])} no.", "payload": plan}]


def execute_approve(conn, actor_id, kind, payload, day):
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))
    plan = {k: payload[k] for k in ("from", "to", "voice", "rung", "method")}
    if not is_living(conn, int(plan["voice"])):
        return {"summary": "The man who asked is dead."}
    res = execute_strike(conn, plan, int(day), sanctioned=True)
    return {"summary": f"{_name(conn, actor_id)} gave leave. " + res.get("summary", "")}


def execute_refuse(conn, actor_id, kind, payload, day):
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))
    pts = _v(conn, (data(conn).get("sanction") or {}).get("refuse_resentment"), 0.0)
    adjust_relationship(conn, int(payload["voice"]), int(actor_id), int(day), resentment_delta=pts)
    return {"summary": f"{_name(conn, actor_id)} refused {_name(conn, payload['voice'])}."}


def answer_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    """His man struck without leave. The head backs him, makes good to the other side, or gives him up: weighed with his own ties to the
    man, the other head's strength and what a war would cost."""
    from .org_happenings import _utility
    meta = json.loads(item["metadata_json"] or "{}")
    F, T, man = int(meta["from"]), int(meta["to"]), int(meta["man"])
    f = factors(conn, int(actor_id), F, T, day)
    r = om._rel(conn, actor_id, man)
    f["fond"] = 0.0 if r is None else clamp01((float(r["loyalty"]) + float(r["respect"])) / 200.0)
    f["standing"] = clamp01(float((seat_of(conn, man, F) or {"standing": 0.0})["standing"]))
    ad = data(conn).get("answer") or {}
    payload = dict(meta)
    why = {"back_him": f"Stands behind {_name(conn, man)}.", "make_good": f"Makes it good with {_name(conn, head_of(conn, T))} for {_name(conn, man)}.",
           "give_him_up": f"Gives up {_name(conn, man)}."}
    return [{"kind": k, "utility": _utility(conn, _blend(conn, ad[k], f)), "rationale": why[k], "payload": payload} for k in ("back_him", "make_good", "give_him_up") if ad.get(k)]


def _finish(conn, payload, day):
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))


def execute_back_him(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    adjust_relationship(conn, int(payload["man"]), int(actor_id), int(day), respect_delta=_v(conn, (data(conn).get("answer") or {}).get("back_points"), 0.0), loyalty_delta=_v(conn, (data(conn).get("answer") or {}).get("back_points"), 0.0))
    return {"summary": f"{_name(conn, actor_id)} stood behind {_name(conn, payload['man'])}."}


def execute_make_good(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    F, T = int(payload["from"]), int(payload["to"])
    d = _v(conn, (data(conn).get("answer") or {}).get("make_good_delta"), 0.0)
    add(conn, T, F, "made_good", -d, day, actor=actor_id)
    other = head_of(conn, T)
    if other is not None:
        pts = _v(conn, (data(conn).get("answer") or {}).get("relation"), 0.0)
        adjust_relationship(conn, other, actor_id, int(day), respect_delta=pts, resentment_delta=-pts)
        imposed(conn, other)
    return {"summary": f"{_name(conn, actor_id)} made it good with {_name(conn, other)}."}


def execute_give_up(conn, actor_id, kind, payload, day):
    from .outfit_choices import execute_order_hunt
    _finish(conn, payload, day)
    F, T = int(payload["from"]), int(payload["to"])
    d = _v(conn, (data(conn).get("answer") or {}).get("give_up_delta"), 0.0)
    add(conn, T, F, "gave_him_up", -d, day, actor=actor_id)
    res = execute_order_hunt(conn, int(actor_id), "order_hunt", {"org": F, "killer": int(payload["man"]), "team": int(_v(conn, (data(conn).get("answer") or {}).get("team"), 1.0))}, int(day))
    return {"summary": f"{_name(conn, actor_id)} gave up {_name(conn, payload['man'])}. " + res.get("summary", "")}


# ---- funerals and courtesy calls ----

def on_death(conn: sqlite3.Connection, victim: int, org: int, role: str | None, day: int, *, killed_by_org: int | None = None) -> None:
    """A seated man died (of any cause): the heads of the other organisations in contact weigh whether to go to the wake or send word. Going
    eases the host's feeling toward the guest; a friend's staying away is a slight (bible 6.1: the understanding is kept by small acts)."""
    fd = data(conn).get("funeral") or {}
    if not fd or not enabled(conn):
        return
    from .org_happenings import _sees
    if conn.execute("SELECT 1 FROM org_tension_acts WHERE kind='wake' AND victim_id=? AND from_org=?", (int(victim), int(org))).fetchone():
        return  # his wake has been weighed already
    conn.execute("INSERT INTO org_tension_acts(day,from_org,to_org,kind,delta,actor_id,victim_id,note) VALUES (?,?,?,?,0,NULL,?,?)", (int(day), int(org), int(org), "wake", int(victim), role))
    rank = _rank(conn, role)
    declared = _declared_contacts(conn)
    for O in _underworld_orgs(conn, day):
        if O == org or O == killed_by_org:
            continue
        if not (level(conn, org, O, day) > 0 or level(conn, O, org, day) > 0 or _places(conn, org, day) & _places(conn, O, day) or (org, O) in declared):
            continue
        guest = head_of(conn, O)
        if guest is None or not _free(conn, guest):
            continue
        f = factors(conn, guest, O, org, day)
        f["rank"] = rank
        f["friend_rank"] = f["friendly"] * rank
        p = _blend(conn, fd.get("attend") or [], f)
        if _rng(conn, "funeral", victim, O, day).random() < p:
            add(conn, org, O, "funeral_attended", -_v(conn, fd.get("delta"), 0.0) * (0.5 + rank), day, actor=guest, victim=victim)
            host = head_of(conn, org)
            if host is not None:
                pts = _v(conn, fd.get("relation"), 0.0)
                adjust_relationship(conn, host, guest, int(day), respect_delta=pts, trust_delta=pts / 2.0)
        elif f["friendly"] > 0:
            add(conn, org, O, "funeral_missed", _v(conn, fd.get("missed_delta"), 0.0) * f["friendly"] * rank, day, actor=guest, victim=victim)


_DO = {"levy": _do_levy, "ease": _do_ease, "sit_down": _do_sit_down, "slight": _do_slight, "press_ground": _do_press_ground, "squeeze": _do_squeeze, "strike": _do_strike}

for _kind, _fn in (("approve_strike", execute_approve), ("refuse_strike", execute_refuse), ("back_him", execute_back_him),
                   ("make_good", execute_make_good), ("give_him_up", execute_give_up)):
    register_executor(_kind, _fn)
register_agenda_action("sanction_strike", sanction_offers)
register_agenda_action("answer_for_man", answer_offers)
