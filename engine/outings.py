"""Nights out, and what happens on them.

An outing is settled the same evening: the venue is a real business of the place, its crowd is drawn from the people who are
plausibly about (age, sex and ties), and it offers what may be taken up: someone to approach, trouble brewing, a familiar face.
The engine proposes and never moves for the protagonist; his moves are resolved when he makes them. The same nights happen to
everyone else as flings and scuffles (life matters). Which businesses are venues, the words and the figures come from the package.
"""
from __future__ import annotations

import random
import sqlite3

from . import company, life_matters as lm, relationships as rel
from .design import figure, run_seed

YEAR = lm.YEAR
MOVES = ("talk", "dance", "ask for her number", "leave together")
_NUMBER = ("ask for her number", "ask for his number", "number", "ask for a number")
_NIGHT = ("leave together", "go home together", "night")


def _f(conn, key: str) -> float:
    v = figure(conn, key)
    if v is None:
        raise KeyError(f"package figure {key} is missing")
    return float(v)


def venues(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """The open businesses people go out to."""
    trades = [str(t) for t in lm.data(conn).get("venues") or {}]
    if not trades:
        return []
    marks = ",".join("?" * len(trades))
    return conn.execute(f"""SELECT id,name,location_id,owner_actor_id,json_extract(metadata_json,'$.trade') trade FROM civilian_enterprises
                            WHERE status IN ('active','strained','insolvent') AND json_extract(metadata_json,'$.trade') IN ({marks})
                            ORDER BY id""", trades).fetchall()


def within_reach(conn: sqlite3.Connection, location_id: int) -> list[sqlite3.Row]:
    """Where an evening out can take someone: the venues of the place, else of the smallest area around it that has any."""
    every, here = venues(conn), int(location_id)
    while here is not None:
        area = {int(r[0]) for r in conn.execute(
            """WITH RECURSIVE t(id) AS (SELECT ? UNION SELECT l.id FROM locations l JOIN t ON l.parent_location_id=t.id)
               SELECT id FROM t""", (here,))}
        found = [v for v in every if v["location_id"] is not None and int(v["location_id"]) in area]
        if found:
            return found
        row = conn.execute("SELECT parent_location_id FROM locations WHERE id=?", (here,)).fetchone()
        here = None if row is None or row[0] is None else int(row[0])
    return []


def _people(conn: sqlite3.Connection, day: int, location_id: int | None = None) -> dict[int, dict]:
    """The living adults (of a place, or everywhere), with what a night out turns on."""
    sql = """SELECT a.id,a.name,a.current_location_id loc,lp.birth_day,lp.demographic_sex,lp.family_formation_eligible,
                    COALESCE(d.aggression,0.5) aggression
             FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id LEFT JOIN actor_drives d ON d.actor_id=a.id
             WHERE a.actor_type='character' AND a.status='active' AND lp.life_status='living' AND lp.birth_day IS NOT NULL
               AND lp.birth_day<=?"""
    args: list = [day - int(_f(conn, "out_age_min") * YEAR)]
    if location_id is not None:
        sql += " AND a.current_location_id=?"
        args.append(int(location_id))
    out = {int(r["id"]): {"id": int(r["id"]), "name": r["name"], "loc": r["loc"], "age": int((day - r["birth_day"]) / YEAR),
                          "sex": r["demographic_sex"], "eligible": bool(r["family_formation_eligible"]),
                          "aggression": float(r["aggression"])} for r in conn.execute(sql + " ORDER BY a.id", args)}
    inside = {int(r[0]) for r in conn.execute("SELECT actor_id FROM inmate_stays WHERE until_day IS NULL OR until_day>?", (day,))}
    return {k: v for k, v in out.items() if k not in inside}


def _taken(conn: sqlite3.Connection, actor: int) -> bool:
    return bool(conn.execute("""SELECT 1 FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?)
                                UNION SELECT 1 FROM life_matters WHERE kind='romance' AND status='open' AND stage<>'interest'
                                  AND (subject_actor_id=? OR other_actor_id=?)""", (actor, actor, actor, actor)).fetchone())


def _kin(conn: sqlite3.Connection, a: int, b: int) -> bool:
    return bool(conn.execute("""SELECT 1 FROM kinship_links WHERE ended_day IS NULL AND ((actor_a_id=? AND actor_b_id=?)
                                OR (actor_a_id=? AND actor_b_id=?))""", (a, b, b, a)).fetchone())


def crowd(conn: sqlite3.Connection, venue: sqlite3.Row, me: int, day: int) -> list[dict]:
    """Who is there this evening: whoever runs the place, and a draw from the people about, weighted by habit, age, sex and ties."""
    from .presence import presence_probability_snapshot
    here = int(venue["location_id"])
    about = presence_probability_snapshot(conn, here, day=day)
    people = _people(conn, day)
    close = lm.contacts(conn, me)
    young, old, women = _f(conn, "out_age_peak"), _f(conn, "out_age_max"), _f(conn, "out_women_weight")
    weights: dict[int, float] = {}
    for a, p in about.items():
        x = people.get(a)
        if a == me or x is None or p <= 0 or x["age"] > old:
            continue
        age = 1.0 if x["age"] <= young else max(0.15, 1.0 - (x["age"] - young) / max(1.0, old - young))
        weights[a] = p * age * (women if x["sex"] == "female" else 1.0) * (1.0 + _f(conn, "out_friend_pull") * close.get(a, 0.0))
    rng = random.Random(f"{run_seed(conn)}:crowd:{venue['id']}:{day}")
    low, high = int(_f(conn, "out_crowd_min")), int(_f(conn, "out_crowd_max"))
    keyed = sorted(((rng.random() ** (1.0 / w), a) for a, w in sorted(weights.items()) if w > 0), reverse=True)
    ids = [a for _, a in keyed[:rng.randint(low, high)]]
    staff = [int(r[0]) for r in conn.execute("SELECT actor_id FROM enterprise_staff WHERE enterprise_id=? AND status='active' ORDER BY actor_id",
                                              (venue["id"],))]
    if venue["owner_actor_id"] is not None:
        staff.insert(0, int(venue["owner_actor_id"]))
    runs = [a for a in dict.fromkeys(staff) if a in people and a != me][:2]
    mine = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
    along = [a for a, w in sorted(close.items(), key=lambda kv: (-kv[1], kv[0]))  # his own people from home or from there come along
             if a in people and a != me and w >= _f(conn, "lm_told_closeness") and people[a]["loc"] in (mine, here)
             and rng.random() < _f(conn, "out_friend_along") * w][:int(_f(conn, "out_friends_most"))]
    out = []
    for a in dict.fromkeys(runs + along + ids):
        x = dict(people[a])
        if a in runs:
            x["runs_the_place"] = True
        out.append(x)
    return out


def regard(conn: sqlite3.Connection, other: dict, me: dict, day: int) -> float:
    """How open one of them is to the protagonist tonight, 0 to 1: her own, the same all evening."""
    v = rel.relationship_view(conn, other["id"], me["id"])
    rng = random.Random(f"{run_seed(conn)}:regard:{other['id']}:{me['id']}:{day}")
    gap = abs(other["age"] - me["age"])
    score = (_f(conn, "out_regard_base") + v["affection"] / 200.0 + v["familiarity"] / 400.0 - v["resentment"] / 100.0
             - gap * _f(conn, "out_regard_gap") + (rng.random() - 0.5) * _f(conn, "out_regard_spread"))
    return max(0.0, min(1.0, score))


def _person(conn, me: int, x: dict) -> dict:
    from .hearsay import relation
    out = {"id": x["id"], "name": x["name"], "age": x["age"], "sex": x["sex"], "to_you": relation(conn, me, x["id"])}
    if x.get("runs_the_place"):
        out["runs_the_place"] = True
    from .physique import describe
    looks = describe(conn, x["id"])
    if looks:
        out["looks"] = looks
    return out


def go_out(conn: sqlite3.Connection, me: int, day: int, venue_id: int | None = None) -> dict:
    """An evening at a venue where he is: who is there and what offers itself. Raises ValueError when there is nowhere to go."""
    mine = _people(conn, day).get(me)
    if mine is None:
        raise ValueError("A night out of this kind is not open to someone under age or held inside.")
    here = mine["loc"]
    found = [] if here is None else within_reach(conn, here)
    if venue_id is not None:
        found = [v for v in found if int(v["id"]) == int(venue_id)]
    if not found:
        raise ValueError("There is nowhere of that kind to go to from here.")
    rng = random.Random(f"{run_seed(conn)}:outing:{me}:{day}")
    likes = lm.data(conn)["venues"]
    habit = {int(v["id"]): random.Random(f"{run_seed(conn)}:local:{me}:{v['id']}").random() ** 3 + 0.02 for v in found}
    venue = rng.choices(found, weights=[float(likes[v["trade"]]) * habit[int(v["id"])] * (3.0 if v["location_id"] == here else 1.0)
                                        for v in found])[0]  # he has his locals
    folk = crowd(conn, venue, me, day)
    company.join(conn, [x["id"] for x in folk])
    words = lm.data(conn).get("outing") or {}
    close = lm.contacts(conn, me)
    happenings: list[dict] = []
    for x in folk:
        if x["id"] in close:  # his own people, and whoever else he knows and runs into
            kind = "familiar" if close[x["id"]] >= _f(conn, "lm_told_closeness") else "chance"
            happenings.append({"kind": kind, "id": x["id"], "what": words[kind].format(who=x["name"])})
    wanted = "female" if mine["sex"] == "male" else "male"
    singles = [x for x in folk if x["sex"] == wanted and not x.get("runs_the_place") and not _kin(conn, me, x["id"])
               and abs(x["age"] - mine["age"]) <= _f(conn, "lm_romance_gap_years")]
    scored = sorted(((regard(conn, x, mine, day), x) for x in singles), key=lambda s: (-s[0], s[1]["id"]))
    for score, x in scored[:int(_f(conn, "out_offers"))]:
        mood = "taken" if _taken(conn, x["id"]) else "keen" if score >= _f(conn, "out_keen") else \
            "open" if score >= _f(conn, "out_open") else "cool"
        happenings.append({"kind": "woman" if wanted == "female" else "man", "id": x["id"], "mood": mood,
                           "what": words[mood].format(who=x["name"]), "you_may": [m for m in MOVES]})
    rough = sorted((x for x in folk if x["sex"] == "male" and not x.get("runs_the_place")), key=lambda x: -x["aggression"])
    if rough and rng.random() < _f(conn, "out_trouble") * (0.5 + rough[0]["aggression"]):
        sore = {x["id"]: rel.relationship_view(conn, x["id"], me)["resentment"] for x in rough}
        who = max(rough, key=lambda x: (sore[x["id"]], x["aggression"], -x["id"]))
        others = [x for x in folk if x["id"] != who["id"]]
        at_him = sore[who["id"]] > 0 or not others or rng.random() < _f(conn, "out_trouble_at_him")
        target = None if at_him else others[rng.randrange(len(others))]
        key = "trouble_you_sore" if at_him and sore[who["id"]] > 0 else "trouble_you" if at_him else "trouble_other"
        happenings.append({"kind": "trouble", "id": who["id"], "at_you": at_him,
                           "what": words[key].format(who=who["name"], other=target["name"] if target else "")})
    return {"venue": str(venue["name"]), "venue_id": int(venue["id"]), "there": [_person(conn, me, x) for x in folk],
            "happenings": happenings}


def approach(conn: sqlite3.Connection, me: int, other: int, move: str, day: int, venue_name: str | None = None) -> dict:
    """His move toward someone who is there tonight, and what she or he does about it."""
    if not company.is_with(conn, me, other):
        raise ValueError("They are not here this evening; go out first, or go to where they are.")
    people = _people(conn, day)
    mine, x = people.get(me), people.get(other)
    if mine is None or x is None:
        raise ValueError("Not someone who can be approached this way.")
    kind = "number" if move in _NUMBER else "night" if move in _NIGHT else "dance" if move == "dance" else "talk"
    words = lm.data(conn).get("outing") or {}
    score = regard(conn, x, mine, day) - (_f(conn, "out_taken_cost") if kind != "talk" and _taken(conn, other) else 0.0)
    danced = conn.execute("SELECT 1 FROM relationship_history WHERE source_actor_id=? AND target_actor_id=? AND day=? AND source_kind='outing_dance'",
                          (other, me, day)).fetchone()
    rng = random.Random(f"{run_seed(conn)}:approach:{me}:{other}:{day}:{kind}")
    if kind in ("number", "night") and _kin(conn, me, other):
        outcome = "turned_down"
    elif kind == "talk":
        outcome = "talked" if score >= _f(conn, "out_talk") else "turned_down"
    elif kind == "dance":
        outcome = "danced" if rng.random() < score + _f(conn, "out_dance_ease") else "turned_down"
    elif kind == "number":
        outcome = "number" if rng.random() < score else "turned_down"
    else:
        warm = _f(conn, "out_dance_warms") if danced else 0.0
        outcome = "night" if rng.random() < score - _f(conn, "out_night_reserve") + warm else "turned_down"
    warmth = {"talked": 3.0, "danced": 8.0, "number": 10.0, "night": 18.0, "turned_down": -2.0}[outcome]
    rel.record_relationship_effect(conn, other, me, day, source_kind="outing_dance" if outcome == "danced" else "outing",
                                   source_id=day, summary=f"a night out: {outcome}", affection_delta=warmth, familiarity_delta=6.0)
    out = {"outcome": outcome, "with": x["name"], "what": words[outcome].format(who=x["name"])}
    if outcome in ("number", "night"):
        p = lm._Pass(conn, day)
        row = conn.execute("""SELECT * FROM life_matters WHERE kind='fling' AND status='open' AND subject_actor_id=? AND other_actor_id=?""",
                           (other, me)).fetchone()
        m = lm._load_matter(p, row) if row is not None else lm._open(p, "fling", other, me, rng)
        m["data"]["venue"] = str(venue_name or m["data"].get("venue") or words["the_place"])
        lm._wait(p, m, outcome)  # the next move is his: unanswered, it fades
        out["follow_up"] = "It waits on you: see them again, call, or let it fade."
    return out


# ---- the same nights, for everyone ----------------------------------------------------------------------------------------

def _locals(p) -> dict[int, list[dict]]:
    if getattr(p, "_places", None) is None:
        places: dict[int, list[dict]] = {}
        for x in _people(p.conn, p.day).values():
            if x["loc"] is not None:
                places.setdefault(int(x["loc"]), []).append(x)
        p._places, p._venues = places, {}
    return p._places


def _where(p, s: int, rng) -> tuple[dict, list[dict], str] | None:
    row = p.conn.execute("SELECT current_location_id FROM actors WHERE id=?", (s,)).fetchone()
    if row is None or row[0] is None:
        return None
    folk = _locals(p).get(int(row[0])) or []
    mine = next((x for x in folk if x["id"] == s), None)
    if mine is None:
        return None
    here = int(row[0])
    if here not in p._venues:
        p._venues[here] = [str(v["name"]) for v in within_reach(p.conn, here)]
    names = p._venues[here]
    return (mine, folk, names[rng.randrange(len(names))]) if names else None


def _open_fling(p, s: int, rng) -> None:
    found = _where(p, s, rng)
    if found is None:
        return
    mine, folk, venue = found
    gap = p.f("lm_romance_gap_years")
    near = [x for x in folk if x["id"] != s and x["eligible"] and x["sex"] != mine["sex"] and x["age"] >= p.f("lm_romance_age_min")
            and abs(x["age"] - mine["age"]) <= gap]
    rng.shuffle(near)
    other = next((x["id"] for x in near[:12] if not _taken(p.conn, x["id"]) and not _kin(p.conn, s, x["id"])), None)
    if other is None:
        return
    if s == p.me:  # someone takes to him; what he does about it is his
        s, other = other, s
    m = lm._open(p, "fling", s, other, rng)
    m["data"] = {"venue": venue}
    lm._effect(p, m["id"], s, other, "took to someone on a night out", affection_delta=8, familiarity_delta=6)
    if other == p.me:
        return lm._wait(p, m, "spark_him")
    return lm._step(p, m, "spark", next_days=lm._span(p, m, "lm_fling_days"))


def _step_fling(p, m: dict) -> None:
    s, o, rng = m["subject_actor_id"], m["other_actor_id"], m["rng"]
    if o is None or not lm._living(p.conn, o):
        return lm._step(p, m, "faded", close=True)
    if p.me in (s, o):
        return lm._step(p, m, "faded", close=True)
    if m["stage"] == "spark":
        if rng.random() < p.f("lm_fling_night"):
            lm._effect(p, m["id"], s, o, "spent the night", affection_delta=12, familiarity_delta=12)
            lm._effect(p, m["id"], o, s, "spent the night", affection_delta=12, familiarity_delta=12)
            return lm._step(p, m, "night", next_days=lm._span(p, m, "lm_fling_days"))
        return lm._step(p, m, "faded", close=True)
    if rng.random() < p.f("lm_fling_courts") and not _taken(p.conn, s) and not _taken(p.conn, o):
        lm._step(p, m, "carried_on", close=True)
        lm.begin_courtship(p.conn, p.day, s, o)
        return
    return lm._step(p, m, "faded", close=True)


def _open_scuffle(p, s: int, rng) -> None:
    found = _where(p, s, rng)
    if found is None:
        return
    mine, folk, venue = found
    others = {x["id"]: 0.1 + x["aggression"] + max(0.0, rel.relationship_view(p.conn, s, x["id"])["resentment"]) / 20.0
              for x in rng.sample(folk, min(12, len(folk))) if x["id"] != s and x["sex"] == "male"
              and abs(x["age"] - mine["age"]) <= p.f("lm_romance_gap_years") * 2 and not _kin(p.conn, s, x["id"])}
    o = lm._pick(rng, others)
    if o is None:
        return
    if s == p.me:  # someone picks it with him
        s, o = o, s
    m = lm._open(p, "scuffle", s, o, rng)
    m["data"] = {"venue": venue}
    lm._effect(p, m["id"], s, o, "squared up", resentment_delta=6)
    lm._effect(p, m["id"], o, s, "squared up", resentment_delta=6)
    if o == p.me:  # his to answer this week; the other man does not wait longer than that
        lm._wait(p, m, "at_him")
        p.conn.execute("UPDATE life_matters SET next_day=? WHERE id=?", (p.day + 1, m["id"]))
        return
    lm._step(p, m, "words", next_days=1)
    roll = rng.random()
    if roll < p.f("lm_scuffle_fight") * (0.5 + mine["aggression"]):
        return _blows(p, m, rng)
    if roll > 1.0 - p.f("lm_scuffle_police"):
        return lm._step(p, m, "police", close=True)
    return lm._step(p, m, "thrown_out", close=True)


def _blows(p, m: dict, rng) -> None:
    from .harm import record_harm
    s, o = m["subject_actor_id"], m["other_actor_id"]
    winner, loser = (s, o) if rng.random() < 0.5 else (o, s)
    severity = max(1.0, rng.expovariate(1.0 / p.f("lm_blows_severity")))
    place = p.conn.execute("SELECT current_location_id FROM actors WHERE id=?", (loser,)).fetchone()
    override = ("persistent" if severity >= p.f("lm_blows_lasting") else "transient") if loser == p.me else None
    res = record_harm(p.conn, loser, source_kind=lm.SOURCE, source_ref_id=m["id"], severity=min(100.0, severity), intent_class="hostile",
                      location_id=place[0] if place else None, metadata={"offender_actor_id": winner}, outcome_override=override)
    lm._effect(p, m["id"], loser, winner, "was beaten", resentment_delta=15, fear_delta=6)
    return lm._step(p, m, "killed" if res.get("outcome") == "fatal" else "fight", close=True,
                    hitter=lm._name(p.conn, winner), hurt=lm._name(p.conn, loser))


def _step_scuffle(p, m: dict) -> None:
    """A challenge he left standing: the other man may swing anyway, or let it go."""
    s, o, rng = m["subject_actor_id"], m["other_actor_id"], m["rng"]
    if o != p.me:
        return lm._step(p, m, "thrown_out", close=True)
    r = p.conn.execute("SELECT aggression FROM actor_drives WHERE actor_id=?", (s,)).fetchone()
    if lm._living(p.conn, s) and rng.random() < p.f("lm_scuffle_fight") * (0.5 + (float(r[0]) if r else 0.5)):
        return _blows(p, m, rng)
    return lm._step(p, m, "lapsed", close=True)


lm.OPENERS.update(fling=_open_fling, scuffle=_open_scuffle)
lm.STEPS.update(fling=_step_fling, scuffle=_step_scuffle)
