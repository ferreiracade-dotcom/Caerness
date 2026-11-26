"""Bodies: every person has a height, a build, a strength, looks and marks.

A record is drawn once (at the opening, at birth, or the first time somebody is looked at) from the package's norms by
sex, age and heritage, a child taking after both parents. A life moves it: manual work builds muscle over years, idleness,
drink and illness wear it down, and injuries leave marks. The review is coarse (the weekly lifecycle pass, each person every
few months on their own stamp). What the player or the narrator has stated about somebody's appearance is taken as given;
only what they left unsaid is filled.

In a fight, a shove or a standoff a body is a weight on the odds, never a gate. Without package data (`data: physique`),
or for somebody with no known age or sex, every factor is 1 and nothing is said.

Reads never write: somebody without a record is shown the very draw that will later be saved.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import sqlite3
from pathlib import Path

from .design import run_seed
from .world_package import package_for

YEAR = 365.25
CM = 2.54
BMI = 703.0  # pounds and inches to body-mass index
_PEOPLE = ("female", "male")
_DATA: dict = {}
_Z = ("height_z", "frame", "vigour", "flesh", "looks")


# ---- package data ----------------------------------------------------------------------------------------------------

def data(conn: sqlite3.Connection) -> dict:
    path = package_for(conn).data.get("physique")
    if path is None:
        return {}
    path = Path(path)
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    if key not in _DATA:
        _DATA[key] = json.loads(path.read_text(encoding="utf-8"))
    return _DATA[key]


def enabled(conn: sqlite3.Connection) -> bool:
    return os.environ.get("CAERNESS_PHYSIQUE") != "off" and bool(data(conn))


def _interp(points: list, x: float) -> float:
    if x <= points[0][0]:
        return float(points[0][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return float(points[-1][1])


def _choose(rng: random.Random, weighted: list):
    return rng.choices([w[0] for w in weighted], weights=[w[1] for w in weighted])[0]


def _day(conn: sqlite3.Connection) -> int:
    r = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()
    return int(r[0]) if r else 0


def _chunks(ids: list, size: int = 500):
    for i in range(0, len(ids), size):
        part = ids[i:i + size]
        yield part, ",".join("?" * len(part))


def _rows(conn: sqlite3.Connection, sql: str, ids: list) -> list:
    """`sql` holds `{}` where the id list goes. A table an older save does not have yet gives no rows."""
    out: list = []
    for part, marks in _chunks(ids):
        try:
            out += conn.execute(sql.format(marks), part).fetchall()
        except sqlite3.OperationalError:
            return out
    return out


# ---- facts about a person --------------------------------------------------------------------------------------------

def _who(conn: sqlite3.Connection, actor_id: int):
    r = conn.execute("""SELECT a.name, l.demographic_sex, l.birth_day FROM actors a JOIN actor_life_profiles l ON l.actor_id=a.id
                        WHERE a.id=? AND a.actor_type='character'""", (int(actor_id),)).fetchone()
    if r is None or r[1] not in _PEOPLE or r[2] is None:
        return None
    return {"id": int(actor_id), "name": str(r[0]), "sex": str(r[1]), "birth_day": int(r[2])}


def _parents(conn: sqlite3.Connection, actor_id: int) -> list[int]:
    return sorted({int(r[0]) for r in conn.execute(
        "SELECT actor_a_id FROM kinship_links WHERE actor_b_id=? AND kin_kind='parent'", (int(actor_id),)).fetchall()})


def _heritage_by_name(conn: sqlite3.Connection, name: str, rng: random.Random, cache: dict) -> str | None:
    groups = package_for(conn).name_groups or {}
    words = [w for w in name.replace(",", " ").split() if w.rstrip(".").lower() not in ("jr", "sr", "ii", "iii", "iv")]
    if not groups or len(words) < 2:
        return None
    family = words[-1]
    held = cache.setdefault("families", {})
    if family not in held:
        from .demographic_sex import family_home_groups
        found = family_home_groups(conn, groups, family)
        held[family] = sorted(k for k, g in groups.items() if any(g is f for f in found))
    return rng.choice(held[family]) if held[family] else None


def _work(conn: sqlite3.Connection, d: dict, ids: list[int]) -> dict[int, dict]:
    """What each person's work asks of the body: the role the record words, else the trade of the business they work in,
    else the kind of occupation."""
    w = d.get("work") or {}
    roles = [(re.compile(r"\b(?:%s)(?:s|es|man|men|er|ers)?\b" % "|".join(re.escape(m) for m in r["match"]), re.I), r)
             for r in w.get("roles") or []]
    out: dict[int, dict] = {}
    for r in _rows(conn, "SELECT id, COALESCE(subtype,''), COALESCE(notes,'') FROM actors WHERE id IN ({})", ids):
        text = f"{r[1]} {r[2]}"
        for pattern, rule in roles:
            if pattern.search(text):
                out[int(r[0])] = rule
                break
    sexes = {int(r[0]): r[1] for r in _rows(conn, "SELECT actor_id, demographic_sex FROM actor_life_profiles WHERE actor_id IN ({})", ids)}

    def at(rule: dict, actor: int, source: str) -> dict:
        # a business or a kind of occupation does not say who does the heavy end of it; the package's shares by sex do
        share = float((w.get(f"{source}_share") or {}).get(sexes.get(actor), 1.0))
        return rule if share == 1.0 else {**rule, "load": float(rule.get("load", 0.0)) * share}

    trades = w.get("trades") or {}
    for r in _rows(conn, """SELECT s.actor_id, e.metadata_json FROM enterprise_staff s JOIN civilian_enterprises e ON e.id=s.enterprise_id
                            WHERE s.status='active' AND s.actor_id IN ({}) ORDER BY s.actor_id, s.authority, s.enterprise_id""", ids):
        rule = trades.get((json.loads(r[1] or "{}")).get("trade"))
        if rule is not None and int(r[0]) not in out:
            out[int(r[0])] = at(rule, int(r[0]), "trade")
    domains = w.get("domains") or {}
    for r in _rows(conn, "SELECT actor_id, occupation_domain FROM background_person_profiles WHERE actor_id IN ({}) ORDER BY id", ids):
        if r[1] in domains and int(r[0]) not in out:
            out[int(r[0])] = at(domains[r[1]], int(r[0]), "domain")
    return out


def _health(conn: sqlite3.Connection, ids: list[int]) -> dict[int, tuple[float, float]]:
    """(illness, everything) a person is held back by, as the worst current capacity impact out of 100."""
    out: dict[int, tuple[float, float]] = {}
    for r in _rows(conn, """SELECT actor_id, condition_kind, capacity_impact FROM health_conditions
                            WHERE status IN ('active','recovering','chronic') AND actor_id IN ({})""", ids):
        ill, every = out.get(int(r[0]), (0.0, 0.0))
        hit = float(r[2] or 0)
        out[int(r[0])] = (max(ill, hit) if r[1] in ("illness", "chronic") else ill, max(every, hit))
    for r in _rows(conn, """SELECT actor_id, capacity_impact, adaptation FROM disabilities
                            WHERE status IN ('active','adapted') AND actor_id IN ({})""", ids):
        ill, every = out.get(int(r[0]), (0.0, 0.0))
        out[int(r[0])] = (ill, max(every, float(r[1] or 0) * (1 - float(r[2] or 0) / 100)))
    return out


def _wear(conn: sqlite3.Connection, d: dict, ids: list[int]) -> dict[int, float]:
    life = d["life"]
    kinds = life.get("dependency") or {}
    out: dict[int, float] = {}
    for r in _rows(conn, """SELECT actor_id, dependency_kind, status, functional_impairment FROM dependency_profiles
                            WHERE status IN ('dependent','recovering') AND actor_id IN ({})""", ids):
        share = 1.0 if r[2] == "dependent" else float(life["recovering_share"])
        hit = float(kinds.get(r[1], 0.0)) * share * (0.5 + float(r[3] or 0) / 100)
        out[int(r[0])] = out.get(int(r[0]), 0.0) + hit
    return out


def _bulk(conn: sqlite3.Connection, d: dict, ids: list[int]) -> dict:
    return {"work": _work(conn, d, ids), "health": _health(conn, ids), "wear": _wear(conn, d, ids)}


# ---- norms -----------------------------------------------------------------------------------------------------------

def _norm_height(d: dict, sex: str, age: float) -> float:
    n = d["norms"][sex]
    adult = float(d["adult_age"])
    if age >= adult:
        return _interp(n["height_in"], age)
    return _interp(n["height_in"], adult) * _interp(n["child_height_cm"], age) / _interp(n["child_height_cm"], adult)


def _norm_bmi(d: dict, sex: str, age: float) -> float:
    n = d["norms"][sex]
    if age >= float(d["adult_age"]):
        return _interp(n["weight_lb"], age) / _interp(n["height_in"], age) ** 2 * BMI
    return _interp(n["child_bmi"], age)


def _shrink(d: dict, age: float) -> float:
    b = d["body"]
    return float(b["shrink_in_per_decade"]) * max(0.0, age - float(b["shrink_from_age"])) / 10


def _grown(d: dict, sex: str, age: float) -> float:
    """The share of adult height reached at this age."""
    adult = float(d["adult_age"])
    if age >= adult:
        return 1.0
    n = d["norms"][sex]
    return _interp(n["child_height_cm"], age) / _interp(n["child_height_cm"], adult)


def _offset(d: dict, heritage: str | None, sex: str) -> float:
    v = ((d.get("heritage") or {}).get(heritage) or {}).get("height_in", 0.0)
    return float(v.get(sex, 0.0) if isinstance(v, dict) else v)


def _peak_height(d: dict, sex: str, age: float, heritage: str | None, z: float) -> float:
    at = max(age, float(d["adult_age"]))
    return _norm_height(d, sex, at) + _shrink(d, at) + _offset(d, heritage, sex) + z * float(d["norms"][sex]["height_sd_in"])


# ---- the draw --------------------------------------------------------------------------------------------------------

def _stored(conn: sqlite3.Connection, actor_id: int) -> dict | None:
    try:
        cur = conn.execute("SELECT * FROM physical_records WHERE actor_id=?", (int(actor_id),))
    except sqlite3.OperationalError:
        return None
    r = cur.fetchone()
    return None if r is None else dict(zip([c[0] for c in cur.description], r))


def _target(d: dict, work: dict | None, response: float, age: float, wear: float, illness: float) -> float:
    """The muscle a life asks for now: work builds it, drink, drugs and illness take it away."""
    life = d["life"]
    load = float((work or {}).get("load", 0.0)) if float(life["work_from_age"]) <= age < float(life["work_to_age"]) else 0.0
    return load * float(life["muscle_gain"]) * response - wear - float(life["illness_muscle"]) * illness / 100


def _built_so_far(d: dict, work: dict | None, response: float, age: float) -> float:
    """Muscle from the working years already behind somebody when they are first drawn."""
    life = d["life"]
    start, stop = float(life["work_from_age"]), float(life["work_to_age"])
    years = max(0.0, min(age, stop) - start)
    built = float((work or {}).get("load", 0.0)) * float(life["muscle_gain"]) * response
    built *= 1 - math.exp(-years / float(life["build_years"]))
    return built * math.exp(-max(0.0, age - stop) / float(life["loss_years"]))


def _draw(conn: sqlite3.Connection, d: dict, actor_id: int, day: int, cache: dict) -> dict | None:
    drawn = cache.setdefault("records", {})
    if actor_id in drawn:
        return drawn[actor_id]
    who = _who(conn, actor_id)
    if who is None:
        return None
    visiting = cache.setdefault("visiting", set())
    visiting.add(actor_id)
    parents = []
    for p in _parents(conn, actor_id):
        if p in visiting:
            continue
        rec = drawn.get(p) or _stored(conn, p) or _draw(conn, d, p, day, cache)
        if rec:
            parents.append(rec)
    visiting.discard(actor_id)
    if actor_id not in cache.get("work", {}) and actor_id not in cache.get("ready", ()):
        one = _bulk(conn, d, [actor_id])
        for key, value in one.items():
            cache.setdefault(key, {}).update(value)

    sex, age = who["sex"], max(0.0, (day - who["birth_day"]) / YEAR)
    rng = random.Random(f"{run_seed(conn)}:physique:{actor_id}")
    known = sorted(p["heritage"] for p in parents if p["heritage"])
    heritage = rng.choice(known) if known else _heritage_by_name(conn, who["name"], rng, cache)
    inherit = d["body"]["inherit"]
    rec = {"actor_id": actor_id, "heritage": heritage}
    for key in _Z:
        own = rng.gauss(0.0, 1.0)
        if parents:
            share = float(inherit["looks_share" if key == "looks" else "share"])
            if len(parents) == 1:
                share /= 2
            mid = sum(float(p[key]) for p in parents) / len(parents)
            own = share * mid + math.sqrt(max(0.0, 1 - share * share / len(parents))) * own
        rec[key] = round(own, 4)
    rec["height_cm"] = round(_peak_height(d, sex, age, heritage, rec["height_z"]) * CM, 2)

    response = rng.uniform(*[float(x) for x in d["life"]["response"]])
    looks_of = (d.get("heritage") or {}).get(heritage) or (d.get("heritage") or {}).get("default") or {}
    features = {k: _choose(rng, looks_of[k]) for k in ("hair", "eyes", "complexion") if looks_of.get(k)}
    f = d.get("features") or {}
    grey = (f.get("greying") or {}).get(sex)
    if grey:
        features["grey_at"] = round(rng.gauss(float(grey["mean"]), float(grey["sd"])), 1)
    bald = (f.get("balding") or {}).get(sex)
    if bald and rng.random() < float(bald["chance"]):
        features["bald_at"] = round(rng.gauss(float(bald["mean"]), float(bald["sd"])), 1)
    features["marks"] = []
    for m in f.get("marks") or []:
        roll = rng.random()
        if (m.get("sex") in (None, sex)) and roll < float(m["chance"]):
            features["marks"].append({"mark": m["mark"], "from_age": m.get("from_age", 0)})
    features["response"] = round(response, 3)

    work = cache.get("work", {}).get(actor_id)
    illness = cache.get("health", {}).get(actor_id, (0.0, 0.0))[0]
    wear = cache.get("wear", {}).get(actor_id, 0.0)
    life = d["life"]
    rec["muscle"] = round(_built_so_far(d, work, response, age) - wear - float(life["illness_muscle"]) * illness / 100, 4)
    rec["muscle_base"] = 0.0
    rec["flesh_shift"] = round(-float(life["illness_flesh"]) * illness / 100, 4)
    rec["features_json"] = json.dumps(features, sort_keys=True)
    rec["stated_json"] = "{}"
    rec["work_json"] = json.dumps(work if work and work.get("load") else {}, sort_keys=True)
    rec["last_day"] = day
    drawn[actor_id] = rec
    return rec


_COLUMNS = ("actor_id", "heritage", "height_cm", "height_z", "frame", "vigour", "flesh", "looks", "muscle", "muscle_base",
            "flesh_shift", "features_json", "stated_json", "work_json", "last_day")


def _insert(conn: sqlite3.Connection, rec: dict) -> None:
    conn.execute(f"INSERT OR IGNORE INTO physical_records({','.join(_COLUMNS)}) VALUES ({','.join('?' * len(_COLUMNS))})",
                 [rec[c] for c in _COLUMNS])


def _record(conn: sqlite3.Connection, d: dict, actor_id: int) -> dict | None:
    return _stored(conn, actor_id) or _draw(conn, d, int(actor_id), _day(conn), {})


def ensure(conn: sqlite3.Connection, actor_id: int) -> dict | None:
    """The person's record, saved if it was not yet."""
    if not enabled(conn):
        return None
    rec = _record(conn, data(conn), int(actor_id))
    if rec is not None:
        _insert(conn, rec)
    return rec


def _missing(conn: sqlite3.Connection) -> list[int]:
    """Living people with an age who have no record, parents before their children."""
    return [int(r[0]) for r in conn.execute(
        """SELECT l.actor_id FROM actor_life_profiles l JOIN actors a ON a.id=l.actor_id AND a.actor_type='character'
           LEFT JOIN physical_records p ON p.actor_id=l.actor_id
           WHERE p.actor_id IS NULL AND l.life_status='living' AND l.birth_day IS NOT NULL AND l.demographic_sex IN ('female','male')
           ORDER BY l.birth_day, l.actor_id""").fetchall()]


def _add(conn: sqlite3.Connection, d: dict, ids: list[int], day: int, *, stagger: int = 0) -> int:
    if not ids:
        return 0
    cache = _bulk(conn, d, ids)
    cache["ready"] = set(ids)
    n = 0
    for actor in ids:
        rec = _draw(conn, d, actor, day, cache)
        if rec is None:
            continue
        if stagger:  # spread the first reviews over the whole interval
            rec["last_day"] = day - actor % stagger
        _insert(conn, rec)
        n += 1
    return n


def seed_all(conn: sqlite3.Connection, day: int | None = None) -> int:
    """Give every living person without a record one (the opening, and a save made before there were records)."""
    if not enabled(conn):
        return 0
    ids = _missing(conn)
    if not ids:
        return 0
    d = data(conn)
    return _add(conn, d, ids, _day(conn) if day is None else int(day), stagger=int(d["life"]["review_days"]))


# ---- a life moves it -------------------------------------------------------------------------------------------------

def weekly(conn: sqlite3.Connection, day: int) -> dict:
    """The newly born and newly known get a record; each record is looked at again when its own interval is up."""
    if not enabled(conn):
        return {}
    d = data(conn)
    life = d["life"]
    added = _add(conn, d, _missing(conn), int(day))
    due = conn.execute(
        """SELECT p.actor_id, p.muscle, p.muscle_base, p.flesh_shift, p.features_json, p.work_json, p.last_day, l.birth_day
           FROM physical_records p JOIN actor_life_profiles l ON l.actor_id=p.actor_id
           WHERE l.life_status='living' AND p.last_day<=? ORDER BY p.actor_id""", (int(day) - int(life["review_days"]),)).fetchall()
    if due:
        ctx = _bulk(conn, d, [int(r[0]) for r in due])
        changed = []
        for r in due:
            actor, muscle, base, shift = int(r[0]), float(r[1]), float(r[2]), float(r[3])
            age = (int(day) - int(r[7])) / YEAR
            years = max(0.0, (int(day) - int(r[6])) / YEAR)
            work = ctx["work"].get(actor)
            illness = ctx["health"].get(actor, (0.0, 0.0))[0]
            response = float(json.loads(r[4]).get("response", 1.0))
            want = base + _target(d, work, response, age, ctx["wear"].get(actor, 0.0), illness)
            muscle += (want - muscle) * (1 - math.exp(-years / float(life["build_years" if want > muscle else "loss_years"])))
            lost = -float(life["illness_flesh"]) * illness / 100
            shift += (lost - shift) * (1 - math.exp(-years / float(life["loss_years"])))
            kept = json.dumps(work, sort_keys=True) if work and work.get("load") else r[5]
            changed.append((round(muscle, 4), round(shift, 4), kept, int(day), actor))
        conn.executemany("UPDATE physical_records SET muscle=?, flesh_shift=?, work_json=?, last_day=? WHERE actor_id=?", changed)
    return {"bodies_added": added, "bodies_reviewed": len(due)}


# ---- the body as it is today -----------------------------------------------------------------------------------------

def _body(conn: sqlite3.Connection, actor_id: int | None) -> dict | None:
    if actor_id is None or not enabled(conn):
        return None
    who = _who(conn, actor_id)
    if who is None:
        return None
    d = data(conn)
    rec = _record(conn, d, int(actor_id))
    if rec is None:
        return None
    day = _day(conn)
    sex, age = who["sex"], max(0.0, (day - who["birth_day"]) / YEAR)
    b = d["body"]
    height = float(rec["height_cm"]) / CM * _grown(d, sex, age) - _shrink(d, age)
    flesh = float(rec["flesh"]) + float(rec["flesh_shift"])
    weights = b["bmi_weights"]
    ratio = math.exp(float(b["bmi_spread"]) * (weights["flesh"] * flesh + weights["frame"] * float(rec["frame"])
                                               + weights["muscle"] * float(rec["muscle"])))
    weight = _norm_bmi(d, sex, age) * ratio * height ** 2 / BMI
    g = b["grip_weights"]
    grip = _interp(d["norms"][sex]["grip_lb"], age) * math.exp(float(b["grip_spread"]) * (
        g["vigour"] * float(rec["vigour"]) + g["muscle"] * float(rec["muscle"]) + g["frame"] * float(rec["frame"])))
    grip *= (height / _norm_height(d, sex, age)) ** float(b["height_strength_power"])
    held_back = _health(conn, [int(actor_id)]).get(int(actor_id), (0.0, 0.0))[1]
    strength = grip / float(b["reference_grip_lb"]) * math.exp(-held_back / float(b["illness_strength_scale"]))
    force = strength * (weight / float(b["reference_weight_lb"])) ** float(d["contest"]["weight_power"])
    return {"id": int(actor_id), "sex": sex, "age": age, "day": day, "height": height, "weight": weight, "ratio": ratio,
            "strength": strength, "force": force, "rec": rec}


# ---- how much a body counts ------------------------------------------------------------------------------------------

def _pair(conn: sqlite3.Connection, a: int | None, b: int | None):
    x, y = _body(conn, a), _body(conn, b)
    return (x["force"], y["force"]) if x and y and x["force"] > 0 and y["force"] > 0 else None


def force(conn: sqlite3.Connection, actor_id: int) -> float:
    """Strength and weight together, 1 being the package's reference adult; 1 when nothing is known."""
    body = _body(conn, actor_id)
    return body["force"] if body else 1.0


def odds(conn: sqlite3.Connection, a: int | None, b: int | None) -> float:
    """The chance that `a` gets the better of `b` bare-handed: even when either body is unknown."""
    pair = _pair(conn, a, b)
    if pair is None:
        return 0.5
    k = float(data(conn)["contest"]["exponent"])
    x, y = pair[0] ** k, pair[1] ** k
    return x / (x + y)


def blow(conn: sqlite3.Connection, hitter: int | None, victim: int | None, method: str | None) -> float:
    """What the two bodies do to the harm of a blow: by how much the weapon leaves to the body."""
    pair = _pair(conn, hitter, victim)
    if pair is None:
        return 1.0
    c = data(conn)["contest"]
    share = float(c["methods"].get(method or "", c["methods"].get("default", 0.0)))
    return (pair[0] / pair[1]) ** (float(c["blow_power"]) * share)


def standoff(conn: sqlite3.Connection, a: int | None, b: int | None) -> float:
    """A weight on `a` squaring up to `b`: below 1 against somebody bigger, above 1 against somebody smaller."""
    pair = _pair(conn, a, b)
    return 1.0 if pair is None else (pair[0] / pair[1]) ** float(data(conn)["contest"]["standoff_power"])


def capacity_factor(conn: sqlite3.Connection, actor_id: int) -> float:
    """The body's mild share of what somebody can bring to bear on another in person."""
    body = _body(conn, actor_id)
    return 1.0 if body is None else body["force"] ** float(data(conn)["contest"]["capacity_power"])


# ---- stated appearance -----------------------------------------------------------------------------------------------

_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven")
_FEET = re.compile(r"(?<![\d.])([3-7])\s*(?:'|ft\.?(?![a-z])|foot\b|feet\b)(?![a-z])\s*(?:(1[01]|\d)(?!\d))?")
_FEET_WORDS = re.compile(r"\b(four|five|six|seven)[ -](?:foot|feet)\b(?:[ -](eleven|ten|one|two|three|four|five|six|seven|eight|nine)\b)?")
_CM = re.compile(r"(?<![\d.])(\d{2,3})\s*cm\b")
_POUNDS = re.compile(r"(?<![\d.])(\d{2,3})\s*(?:lb|lbs|pound|pounds)\b")


def _lexicon(text: str, entries: list, negations: list) -> list[dict]:
    """The entries whose phrases the text uses, longest phrase first so a longer one claims its words; a phrase after a
    negation, or followed by a word that turns it elsewhere, does not count."""
    phrases = sorted(((w, i) for i, e in enumerate(entries) for w in e["words"]), key=lambda p: -len(p[0]))
    found: list[dict] = []
    left = text
    for phrase, i in phrases:
        for m in list(re.finditer(r"(?<![a-z0-9])%s(?![a-z0-9-])" % re.escape(phrase), left)):
            before = re.findall(r"[a-z']+", re.split(r"[.,;:!?]", left[:m.start()])[-1])[-3:]
            after = re.match(r"[\s-]*([a-z']+)", left[m.end():])
            left = left[:m.start()] + "#" * len(m.group()) + left[m.end():]
            if any(n in before for n in negations) or (after and after.group(1) in entries[i].get("unless_next", ())):
                continue
            if entries[i] not in found:
                found.append(entries[i])
    return found


def parse_stated(d: dict, text: str, label: str | None = None) -> dict:
    """What a few words say about a body, as far as the package's lexicon reads them."""
    s = d["stated"]
    low = text.lower().replace("’", "'").replace("”", '"').replace("“", '"')
    out: dict = {"set": {}, "fields": set()}
    feet = _FEET.search(low)
    spoken = _FEET_WORDS.search(low)
    metric = _CM.search(low)
    if feet:
        out["height_in"] = int(feet.group(1)) * 12 + int(feet.group(2) or 0)
    elif spoken:
        out["height_in"] = _NUMBER_WORDS.index(spoken.group(1)) * 12 + _NUMBER_WORDS.index(spoken.group(2) or "zero")
    elif metric:
        out["height_in"] = int(metric.group(1)) / CM
    negations = s.get("negations") or []
    tall = _lexicon(low, s.get("height_words") or [], negations)
    if tall and "height_in" not in out:
        out["height_z"] = float(tall[0]["z"])
    if "height_in" in out or tall:
        out["fields"].add("height")
    pounds = _POUNDS.search(low)
    if pounds:
        out["weight_lb"] = int(pounds.group(1))
        out["fields"].add("weight")
    for entry in _lexicon(low, s.get("build_words") or [], negations):
        out["fields"].add("build")
        for key, value in entry["set"].items():
            if key not in out["set"] or abs(value) > abs(out["set"][key]):
                out["set"][key] = float(value)
    for key, field in (("strength_words", "strength"), ("looks_words", "looks")):
        hits = _lexicon(low, s.get(key) or [], negations)
        if hits:
            out[f"{field}_z"] = sum(float(h["z"]) for h in hits) / len(hits)
            out["fields"].add(field)
    rating = s.get("rating") or {}
    scored = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:/|out of)\s*(?:%d|ten)\b" % int(rating.get("scale", 10)), low)
    if not scored and label in (rating.get("labels") or ()):
        scored = re.match(r"\W*(\d+(?:\.\d+)?)(?![\d.'])\W*$", low)
    if scored:
        out["looks_z"] = (float(scored.group(1)) - float(rating["middle"])) / float(rating["per_sd"])
    for field in ("marks", "hair", "eyes", "complexion"):
        if _lexicon(low, [{"words": s.get(f"{field}_words") or []}], negations):
            out["fields"].add(field)
    return out


def _shown(d: dict, item: dict) -> str:
    """The stated words as the narrator may repeat them: a score out of ten is a measure, not a description."""
    scale = int(((d.get("stated") or {}).get("rating") or {}).get("scale", 10))
    text = re.sub(r"\(?(?<![\d.])\d+(?:\.\d+)?\s*(?:/|out of)\s*(?:%d|ten)\b\)?" % scale, "", item["text"], flags=re.I)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,;:.-—–")
    return "" if re.fullmatch(r"[\d.\s]*", text) else text


def set_stated(conn: sqlite3.Connection, actor_id: int, stated, *, label: str | None = None) -> bool:
    """Take what was said about somebody's appearance as given: the words are kept, and the figures follow them.
    `stated` is a text, or {height, build, strength, looks, marks, ...: text}. A later saying under the same label
    replaces the earlier one."""
    if not stated:
        return False
    rec = ensure(conn, actor_id)
    if rec is None:
        return False
    d = data(conn)
    who = _who(conn, actor_id)
    rec = dict(rec)
    sex, day = who["sex"], _day(conn)
    age = max(0.0, (day - who["birth_day"]) / YEAR)
    pairs = [(str(k).lower(), ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v))
             for k, v in stated.items() if v not in (None, "", [])] if isinstance(stated, dict) else [((label or "appearance").lower(), str(stated))]
    kept = json.loads(rec["stated_json"] or "{}").get("items") or []
    b, body = d["body"], {}
    for key, text in pairs:
        text = text.strip()
        if not text:
            continue
        kept = [i for i in kept if i["label"] != key] + [{"label": key, "text": text, "day": day}]
        said = parse_stated(d, text, key)
        sd = float(d["norms"][sex]["height_sd_in"])
        if "height_in" in said:
            peak = (said["height_in"] + _shrink(d, age)) / _grown(d, sex, age)
            rec["height_z"] = (peak - _peak_height(d, sex, age, rec["heritage"], 0.0)) / sd
            rec["height_cm"] = peak * CM
        elif "height_z" in said:
            z = said["height_z"]
            rec["height_z"] = max(float(rec["height_z"]), z) if z > 0 else min(float(rec["height_z"]), z)
            rec["height_cm"] = _peak_height(d, sex, age, rec["heritage"], rec["height_z"]) * CM
        for column, value in said["set"].items():
            rec[column] = value
            if column == "flesh":
                rec["flesh_shift"] = 0.0
            if column == "muscle":
                work = _work(conn, d, [int(actor_id)]).get(int(actor_id))
                rec["muscle_base"] = value - _target(d, work, float(json.loads(rec["features_json"]).get("response", 1.0)), age,
                                                     _wear(conn, d, [int(actor_id)]).get(int(actor_id), 0.0), 0.0)
        for k in ("weight_lb", "strength_z"):
            if k in said:
                body[k] = said[k]
        if "looks_z" in said:
            rec["looks"] = said["looks_z"]
    if "weight_lb" in body:
        w = b["bmi_weights"]
        height = float(rec["height_cm"]) / CM * _grown(d, sex, age) - _shrink(d, age)
        ratio = body["weight_lb"] / (_norm_bmi(d, sex, age) * height ** 2 / BMI)
        rec["flesh"] = (math.log(ratio) / float(b["bmi_spread"]) - w["frame"] * float(rec["frame"])
                        - w["muscle"] * float(rec["muscle"])) / w["flesh"]
        rec["flesh_shift"] = 0.0
    if "strength_z" in body:
        g = b["grip_weights"]
        rec["vigour"] = (body["strength_z"] - g["muscle"] * float(rec["muscle"]) - g["frame"] * float(rec["frame"])) / g["vigour"]
    rec["stated_json"] = json.dumps({"items": kept}, ensure_ascii=False)
    columns = [c for c in _COLUMNS if c != "actor_id"]
    conn.execute(f"UPDATE physical_records SET {','.join(c + '=?' for c in columns)} WHERE actor_id=?",
                 [rec[c] for c in columns] + [int(actor_id)])
    return True


def _labelled(d: dict, text: str):
    s = d.get("stated") or {}
    head = r"^.{0,40}?\b(%s)\b\s*(?:\([^)]*\))?\s*"
    for labels, mark in ((s.get("labels"), r"[:\-–—]"), (s.get("colon_labels"), ":")):
        if labels:
            m = re.match(head % "|".join(map(re.escape, labels)) + mark, text, re.I)
            if m:
                return m.group(1).lower(), text[m.end():]
    return None


def apply_note(conn: sqlite3.Connection, subject_kind: str, subject_id: int | None, text: str, field: str | None = None) -> bool:
    """A narrator's note about one person that describes how they look sets it: the field says so, or the text opens with
    a label ("Appearance: ...")."""
    if subject_kind != "actor" or subject_id is None or not enabled(conn):
        return False
    d = data(conn)
    found = _labelled(d, text.strip())
    s = d.get("stated") or {}
    if found is None:
        name = (field or "").strip().lower()
        if name not in (s.get("labels") or []) + (s.get("colon_labels") or []):
            return False
        found = (name, text)
    return set_stated(conn, int(subject_id), found[1].strip(), label=found[0])


def apply_old_notes(conn: sqlite3.Connection) -> int:
    """Notes and the character sheet written before there were records: what they say about appearance now counts."""
    if not enabled(conn):
        return 0
    s = data(conn).get("stated") or {}
    capital = re.compile(r"\b(%s)\b" % "|".join(w.capitalize() for w in s.get("labels") or ["appearance"]))
    n = 0
    try:
        notes = conn.execute("SELECT subject_id, text FROM gm_notes WHERE subject_kind='actor' ORDER BY id").fetchall()
    except sqlite3.OperationalError:
        notes = []
    for actor, text in notes:
        if apply_note(conn, "actor", actor, text):
            n += 1
        else:
            m = capital.search(text)
            if m and set_stated(conn, int(actor), text, label=m.group(1).lower()):
                n += 1
    try:
        sheet = conn.execute("""SELECT p.player_actor_id, c.text FROM character_sheet c, player_state p
                                WHERE p.id=1 AND c.field='appearance'""").fetchone()
    except sqlite3.OperationalError:
        sheet = None
    if sheet and sheet[0] is not None and set_stated(conn, int(sheet[0]), sheet[1], label="appearance"):
        n += 1
    return n


def on_authored(conn: sqlite3.Connection, actor_id: int, stated=None) -> dict | None:
    """A person just made: their record, with whatever the author said about how they look."""
    if not enabled(conn):
        return None
    ensure(conn, actor_id)
    set_stated(conn, actor_id, stated)
    return appearance(conn, actor_id)


# ---- words -----------------------------------------------------------------------------------------------------------

def _word(entry, sex: str) -> str:
    return entry[sex] if isinstance(entry, dict) else entry


def _band(table: list, value: float, sex: str) -> tuple[str, bool]:
    for row in table:
        if value >= float(row.get("min", -math.inf)):
            return _word(row["word"], sex), bool(row.get("quiet"))
    return _word(table[-1]["word"], sex), bool(table[-1].get("quiet"))


def _parts(conn: sqlite3.Connection, body: dict) -> dict:
    """Every phrase the record gives about this body today."""
    d = data(conn)
    w, rec, sex, age = d["words"], body["rec"], body["sex"], body["age"]
    features = json.loads(rec["features_json"] or "{}")
    work = json.loads(rec["work_json"] or "{}")
    muscle = float(rec["muscle"])
    total = int(round(body["height"]))
    out: dict = {"height": w["height"].format(feet=total // 12, inches=total % 12),
                 "weight": w["weight"].format(pounds=int(round(body["weight"] / 5.0) * 5))}
    spread = float(d["norms"][sex]["height_sd_in"])
    z = (body["height"] - _norm_height(d, sex, age)) / spread
    out["stature"] = w["tall"] if z >= float(w["tall_z"]) else w["short"] if z <= float(w["short_z"]) else None
    for rule in w["build"]:
        if (muscle >= float(rule.get("muscle_min", -math.inf)) and body["ratio"] >= float(rule.get("fat_min", 0.0))
                and body["ratio"] <= float(rule.get("fat_max", math.inf))):
            phrase = _word(rule["word"], sex)
            if rule.get("from_work") and work.get("from"):
                phrase = f"{phrase} {work['from']}"
            out["build"] = phrase
            break
    if age >= float(d["child_age"]):
        own = body["strength"] * float(d["body"]["reference_grip_lb"]) / float(d["norms"][sex]["prime_grip_lb"])
        out["strength"], out["strength_quiet"] = _band(w["strength"], own, sex)
    if age >= float(w["looks_from_age"]):
        out["looks"], out["looks_quiet"] = _band(w["looks"], float(rec["looks"]), sex)
    f = d.get("features") or {}
    hair = features.get("hair")
    if hair:
        grey, bald = f.get("greying") or {}, f.get("balding") or {}
        grey_at, bald_at = features.get("grey_at"), features.get("bald_at")
        if bald_at is not None and age >= bald_at + float(bald["bald_after_years"]):
            out["hair"] = bald["bald_word"]
        else:
            if grey_at is not None and age >= grey_at + float(grey["grey_after_years"]):
                phrase, colour = grey["grey_word"], "grey"
            elif grey_at is not None and age >= grey_at:
                phrase, colour = grey["greying_word"].format(hair=hair), f"greying {hair}"
            else:
                phrase, colour = grey.get("hair_word", "{hair}").format(hair=hair), hair
            out["hair"] = bald["thinning_word"].format(hair=colour) if bald_at is not None and age >= bald_at else phrase
    if features.get("eyes"):
        out["eyes"] = f"{features['eyes']} eyes"
    out["complexion"] = features.get("complexion")

    recent, old = [], []
    since = body["day"] - int(d["life"]["recent_harm_days"])
    for r in _rows(conn, """SELECT day, outcome, metadata_json FROM harm_incidents
                            WHERE actor_id IN ({}) ORDER BY day DESC, id DESC""", [body["id"]]):
        method = json.loads(r[2] or "{}").get("method")
        for words, into, wanted in ((f.get("recent_marks"), recent, int(r[0]) >= since),
                                    (f.get("injury_marks"), old, r[1] == "persistent")):
            if words and wanted:
                phrase = words.get(method or "", words.get("default"))
                if phrase and phrase not in into:
                    into.append(phrase)
    drawn = [m["mark"] for m in features.get("marks") or [] if age >= float(m.get("from_age", 0))]
    if work.get("hands") and muscle >= 0.5 and age >= float(d["life"]["work_from_age"]):
        drawn.append(work["hands"])
    out["recent"], out["marks"] = recent, old + drawn
    return out


def _stated_of(d: dict, rec: dict) -> tuple[list[str], set]:
    words, fields = [], set()
    for item in json.loads(rec.get("stated_json") or "{}").get("items") or []:
        shown = _shown(d, item)
        if shown:
            words.append(shown)
            fields |= parse_stated(d, item["text"], item["label"])["fields"]
    return words, fields


def _line(d: dict, p: dict, words: list[str], fields: set) -> str:
    filled = []
    if "height" not in fields:
        filled.append(f"{p['stature']}, {p['height']}" if p.get("stature") else p["height"])
    if "build" not in fields:
        filled.append(p.get("build"))
    for key in ("strength", "looks"):
        if key not in fields and not p.get(f"{key}_quiet"):
            filled.append(p.get(key))
    if "hair" not in fields:
        filled.append(p.get("hair"))
    filled += p["recent"][:1]
    if "marks" not in fields:
        filled += p["marks"][:int(d["words"]["line_marks"])]
    return "; ".join(x for x in words + [", ".join(x for x in filled if x)] if x)


def describe(conn: sqlite3.Connection, actor_id: int) -> str | None:
    """One line on how somebody looks, the stated words first."""
    body = _body(conn, actor_id)
    if body is None:
        return None
    d = data(conn)
    return _line(d, _parts(conn, body), *_stated_of(d, body["rec"])) or None


def appearance(conn: sqlite3.Connection, actor_id: int, viewer: int | None = None) -> dict | None:
    """Everything that shows, and how it compares with the person looking."""
    body = _body(conn, actor_id)
    if body is None:
        return None
    d = data(conn)
    p = _parts(conn, body)
    words, fields = _stated_of(d, body["rec"])
    out = {"line": _line(d, p, words, fields), "as_stated": words or None, "height": p["height"], "weight": p["weight"]}
    for key in ("build", "strength", "looks", "hair", "eyes", "complexion"):
        if key not in fields:
            out[key] = p.get(key)
    out["marks"] = (p["recent"] + ([] if "marks" in fields else p["marks"])) or None
    other = None if viewer in (None, actor_id) else _body(conn, viewer)
    if other:
        a = d["words"]["against"]
        gap = body["height"] - other["height"]
        said = [a["taller"] if gap >= a["height_in"] else a["shorter"] if gap <= -a["height_in"] else a["level"]]
        heft = body["weight"] / other["weight"]
        if heft >= a["weight_ratio"] or heft <= 1 / a["weight_ratio"]:
            said.append(a["heavier"] if heft > 1 else a["lighter"])
        power = body["force"] / other["force"]
        said.append(a["stronger"] if power >= a["force_ratio"] else a["weaker"] if power <= 1 / a["force_ratio"] else a["even"])
        out["against_you"] = a["join"].join(said)
    return {k: v for k, v in out.items() if v}
