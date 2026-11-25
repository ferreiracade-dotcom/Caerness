"""Ordinary life happens to everyone: money runs short, people take to each other, quarrel, fall ill, undercut a rival, bring
each other work, draw the police.

Every living adult is a subject, drawn from his own state (cash, ties, resentment, age, health, trade, company he keeps). Nobody is
chosen because of the protagonist: who he is near matters only to what reaches him, never to what happens. Each matter is a thread
with stages and real effects (money moves, ties shift, a condition begins, someone is hurt and the law may follow).

Cadence follows the tiers (`engine/tiers.py`): rising and active people are looked at every week, quiet people every
`lm_quiet_weeks`, with the chance integrated over the time since they were last looked at, so the rate per year is the same.

The protagonist is a subject like anyone else; things happen to him. But the engine never acts for him: where the next move would be
his (to lend, to answer, to take a job, to strike back), the matter waits, and lapses if nothing is done.

Words and figures come from the package (`data: matters` and `design_figures.json`); without them nothing runs.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
from pathlib import Path

from . import ledger, relationships as rel, tiers
from .design import figure, run_seed
from .world_package import package_for

WEEK = 7
YEAR = 365.0
SOURCE = "life_matter"

_DATA: dict = {}


# ---- package data ----------------------------------------------------------------------------------------------------

def data(conn: sqlite3.Connection) -> dict:
    path = package_for(conn).data.get("matters")
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
    return bool(data(conn))


def _player(conn: sqlite3.Connection) -> int | None:
    try:
        r = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    except sqlite3.OperationalError:
        return None
    return int(r[0]) if r and r[0] is not None else None


class _Pass:
    """What one weekly pass reads once: figures, and the state that says who is open to what."""

    def __init__(self, conn: sqlite3.Connection, day: int):
        self.told: set[int] | None = None
        self.conn, self.day = conn, int(day)
        self.me = _player(conn)
        self.words = data(conn)
        self.seed = run_seed(conn)
        self._figs: dict[str, float] = {}
        self._cash: dict[int, float] | None = None
        self._near: dict[int, dict[int, float]] = {}

    def cash(self) -> dict[int, float]:
        """Every purse, read once a week and kept up to date by the pass's own payments."""
        if self._cash is None:
            self._cash = {int(r[0]): float(r[1]) for r in self.conn.execute("SELECT actor_id,amount FROM resources WHERE resource_type='cash'")}
            for a, v in self.conn.execute("SELECT actor_id,liquid_wealth FROM underworld_leader_wealth"):
                self._cash[int(a)] = float(v)
        return self._cash

    def purse(self, a: int) -> float:
        return self.cash().get(int(a), 0.0)

    def ties(self, a: int) -> dict[int, float]:
        if a not in self._near:
            self._near[a] = contacts(self.conn, a)
        return dict(self._near[a])

    def pay(self, src: tuple[str, int], dst: tuple[str, int], amount: float, why: str) -> None:
        ledger.transfer(self.conn, src, dst, amount, flow_kind="other", purpose=why)
        for h in (src, dst):
            if h[0] == "person":
                self.cash()[h[1]] = ledger.balance(self.conn, h)

    def f(self, key: str) -> float:
        if key not in self._figs:
            v = figure(self.conn, key)
            if v is None:
                raise KeyError(f"package figure {key} is missing")
            self._figs[key] = float(v)
        return self._figs[key]


# ---- helpers ----------------------------------------------------------------------------------------------------------

def _name(conn: sqlite3.Connection, a: int | None) -> str:
    if a is None:
        return "someone"
    r = conn.execute("SELECT name FROM actors WHERE id=?", (int(a),)).fetchone()
    return str(r[0]) if r else "someone"


def _living(conn: sqlite3.Connection, a: int) -> bool:
    r = conn.execute("""SELECT a.status, lp.life_status FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?""", (int(a),)).fetchone()
    return bool(r) and str(r[0] or "active").lower() not in ("dead", "deceased") and str(r[1] or "living") == "living"


def money(words: dict, x: float) -> str:
    return f"{words.get('currency_symbol', '')}{int(round(x)):,}"


def contacts(conn: sqlite3.Connection, a: int) -> dict[int, float]:
    """The living people in a person's life and how close each is (kin, household, people he knows, the company he keeps)."""
    out: dict[int, float] = {}

    def put(i, w):
        if i is not None and int(i) != a and w > out.get(int(i), 0.0):
            out[int(i)] = w
    for x, y in conn.execute("SELECT actor_a_id,actor_b_id FROM kinship_links WHERE (actor_a_id=? OR actor_b_id=?) AND ended_day IS NULL", (a, a)):
        put(y if int(x) == a else x, 1.0)
    for (i,) in conn.execute("""SELECT h2.actor_id FROM household_members h1 JOIN household_members h2 ON h2.household_id=h1.household_id
                                WHERE h1.actor_id=? AND h1.status='active' AND h2.status='active'""", (a,)):
        put(i, 0.9)
    for i, fam in conn.execute("SELECT actor_b_id,familiarity FROM relationships WHERE actor_a_id=?", (a,)):
        put(i, min(0.8, float(fam or 0) / 100.0))
    for x, y, aff in conn.execute("""SELECT actor_a_id,actor_b_id,affinity FROM social_contact_links
                                     WHERE (actor_a_id=? OR actor_b_id=?) AND +status='active'""", (a, a)):  # + : by the two ends
        put(y if int(x) == a else x, min(0.7, float(aff or 0) / 100.0))
    if out:
        marks = ",".join("?" * len(out))
        alive = {int(r[0]) for r in conn.execute(
            f"""SELECT a.id FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id IN ({marks})
                AND lp.life_status='living' AND lower(COALESCE(a.status,'active')) NOT IN ('dead','deceased')""", list(out))}
        out = {k: v for k, v in out.items() if k in alive}
    return out


def known_by(conn: sqlite3.Connection, those: list[int]) -> dict[int, dict[int, float]]:
    """`contacts` the other way round, for a few people at once: for each person who has any of `those` in their life, who and how close."""
    out: dict[int, dict[int, float]] = {}
    if not those:
        return out
    marks, ids = ",".join("?" * len(those)), [int(i) for i in those]
    alive = {int(r[0]) for r in conn.execute(
        f"""SELECT a.id FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id IN ({marks})
            AND lp.life_status='living' AND lower(COALESCE(a.status,'active')) NOT IN ('dead','deceased')""", ids)}

    def put(a, c, w):
        a, c = int(a), int(c)
        if a != c and w > 0 and c in alive:  # as in `contacts`: no tie without weight
            d = out.setdefault(a, {})
            d[c] = max(d.get(c, 0.0), w)
    for x, y in conn.execute(f"""SELECT actor_a_id,actor_b_id FROM kinship_links WHERE ended_day IS NULL
                                 AND (actor_a_id IN ({marks}) OR actor_b_id IN ({marks}))""", ids + ids):
        put(x, y, 1.0)
        put(y, x, 1.0)
    for a, c in conn.execute(f"""SELECT h1.actor_id,h2.actor_id FROM household_members h2 JOIN household_members h1
                                 ON h1.household_id=h2.household_id WHERE h2.actor_id IN ({marks}) AND h1.status='active' AND h2.status='active'""", ids):
        put(a, c, 0.9)
    for a, c, fam in conn.execute(f"SELECT actor_a_id,actor_b_id,familiarity FROM relationships WHERE actor_b_id IN ({marks})", ids):
        put(a, c, min(0.8, float(fam or 0) / 100.0))
    for x, y, aff in conn.execute(f"""SELECT actor_a_id,actor_b_id,affinity FROM social_contact_links WHERE +status='active'
                                      AND (actor_a_id IN ({marks}) OR actor_b_id IN ({marks}))""", ids + ids):
        put(x, y, min(0.7, float(aff or 0) / 100.0))
        put(y, x, min(0.7, float(aff or 0) / 100.0))
    return out


def _pick(rng: random.Random, weighted: dict[int, float]) -> int | None:
    items = sorted((k, v) for k, v in weighted.items() if v > 0)
    if not items:
        return None
    total = sum(v for _, v in items)
    x = rng.random() * total
    for k, v in items:
        x -= v
        if x <= 0:
            return k
    return items[-1][0]


def _effect(p: _Pass, matter: int, a: int, b: int, summary: str, **deltas) -> None:
    """What `a` now feels about `b`. The protagonist's feelings are the player's own: nothing is written on his side."""
    if a == p.me:
        return
    rel.record_relationship_effect(p.conn, a, b, p.day, source_kind=SOURCE, source_id=matter, summary=summary, **deltas)


def _step(p: _Pass, m: dict, stage: str, *, close: bool = False, next_days: float | None = None, **words) -> None:
    """Record where the matter now stands, in the package's words."""
    conn = p.conn
    tmpl = (p.words.get("texts") or {}).get(f"{m['kind']}.{stage}")
    awaiting = int(bool(m.get("awaiting")))
    text = None
    if tmpl:
        fields = {"s": _name(conn, m["subject_actor_id"]), "o": _name(conn, m["other_actor_id"]),
                  "amount": money(p.words, m["amount"]) if m.get("amount") else "", **m.get("data", {}), **words}
        text = tmpl.format(**fields)
        actors = [x for x in (m["subject_actor_id"], m["other_actor_id"]) if x is not None]
        conn.execute("INSERT INTO life_matter_steps(matter_id,day,stage,text,actors) VALUES (?,?,?,?,?)",
                     (m["id"], p.day, stage, text, ",".join(str(int(x)) for x in actors)))
    next_day = None if close else p.day + max(1, int(round(next_days if next_days is not None else p.f("lm_stage_days"))))
    conn.execute("""UPDATE life_matters SET stage=?,status=?,next_day=?,stage_day=?,awaiting=?,summary=COALESCE(?,summary),other_actor_id=?,
                    amount=?,data_json=? WHERE id=?""",
                 (stage, "closed" if close else "open", next_day, p.day, 0 if close else awaiting, text, m["other_actor_id"], m.get("amount"),
                  json.dumps(m.get("data", {}), sort_keys=True), m["id"]))


def _open(p: _Pass, kind: str, subject: int, other: int | None, rng: random.Random) -> dict:
    loc = p.conn.execute("SELECT current_location_id FROM actors WHERE id=?", (subject,)).fetchone()
    mid = int(p.conn.execute("""INSERT INTO life_matters(kind,subject_actor_id,other_actor_id,location_id,stage,status,opened_day,stage_day,data_json)
                                VALUES (?,?,?,?,'new','open',?,?,'{}')""",
                             (kind, subject, other, loc[0] if loc else None, p.day, p.day)).lastrowid)
    return {"id": mid, "kind": kind, "subject_actor_id": subject, "other_actor_id": other, "amount": None, "data": {}, "awaiting": False, "rng": rng}


def _wait(p: _Pass, m: dict, stage: str, **words) -> None:
    """The next move is the protagonist's: the matter waits for it."""
    m["awaiting"] = True
    m.setdefault("data", {})["asked_day"] = p.day  # the day it turned to him: an ordinary skip stops there
    _step(p, m, stage, next_days=p.f("lm_lapse_days"), **words)


def _span(p: _Pass, m: dict, key: str) -> float:
    return p.f(key) * (0.5 + m["rng"].random())


# ---- money ------------------------------------------------------------------------------------------------------------

def _open_money(p: _Pass, s: int, rng) -> None:
    conn = p.conn
    living = p.f("lm_living_week_usd")
    short = max(p.f("lm_short_weeks") * living - p.purse(s), living)
    amount = round(short * (0.4 + rng.random()))
    ties = p.ties(s)
    lenders = {i: w * w for i, w in ties.items() if p.purse(i) >= amount * 2}
    lender = _pick(rng, lenders)
    m = _open(p, "money", s, lender, rng)
    m["amount"] = amount
    if s == p.me:
        m["other_actor_id"] = None
        return _wait(p, m, "short_self")
    if lender is None:
        return _step(p, m, "behind", next_days=_span(p, m, "lm_debt_days"))
    if lender == p.me:
        return _wait(p, m, "asks")
    view = rel.relationship_view(conn, lender, s)
    willing = ties[lender] * 0.6 + (view["trust"] + view["affection"] - view["resentment"]) / 200.0 + p.f("lm_lend_base")
    if rng.random() < willing:
        p.pay(("person", lender), ("person", s), amount, f"personal loan (matter {m['id']})")
        _effect(p, m["id"], s, lender, "borrowed money", obligation_delta=10, trust_delta=3)
        return _step(p, m, "borrowed", next_days=_span(p, m, "lm_debt_days"))
    _effect(p, m["id"], s, lender, "was turned down for a loan", resentment_delta=5)
    return _step(p, m, "refused", close=True)


def _step_money(p: _Pass, m: dict) -> None:
    conn, s, o = p.conn, m["subject_actor_id"], m["other_actor_id"]
    living, amount = p.f("lm_living_week_usd"), float(m["amount"] or 0)
    if m["stage"] == "borrowed" or m["stage"] == "asked_time":
        if o is None or not _living(conn, o):
            return _step(p, m, "written_off", close=True)
        if p.purse(s) >= amount + living and s != p.me:
            p.pay(("person", s), ("person", o), amount, f"loan repayment (matter {m['id']})")
            _effect(p, m["id"], o, s, "was repaid", trust_delta=6)
            return _step(p, m, "repaid", close=True)
        if m["stage"] == "borrowed":
            _effect(p, m["id"], o, s, "was asked for more time", trust_delta=-3)
            return _step(p, m, "asked_time", next_days=_span(p, m, "lm_debt_days"))
        _effect(p, m["id"], o, s, "was not repaid", trust_delta=-10, resentment_delta=15)
        return _step(p, m, "soured", close=True)
    if p.purse(s) >= amount:
        return _step(p, m, "caught_up", close=True)
    return _step(p, m, "worse", close=True)


# ---- romance ------------------------------------------------------------------------------------------------------------

def _single_candidates(p: _Pass, s: int) -> dict[int, float]:
    conn = p.conn
    me_row = conn.execute("SELECT birth_day,demographic_sex FROM actor_life_profiles WHERE actor_id=?", (s,)).fetchone()
    if not me_row:
        return {}
    ties = p.ties(s)
    out: dict[int, float] = {}
    for i, w in ties.items():
        r = conn.execute("""SELECT birth_day,demographic_sex,family_formation_eligible FROM actor_life_profiles WHERE actor_id=?""", (i,)).fetchone()
        if not r or str(r[1]) == str(me_row[1]) or not r[2]:
            continue
        age = (p.day - int(r[0])) / YEAR
        gap = abs(int(r[0]) - int(me_row[0])) / YEAR
        if age < p.f("lm_romance_age_min") or gap > p.f("lm_romance_gap_years"):
            continue
        if conn.execute("SELECT 1 FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?)", (i, i)).fetchone():
            continue
        if conn.execute("SELECT 1 FROM life_matters WHERE kind='romance' AND status='open' AND (subject_actor_id=? OR other_actor_id=?)",
                        (i, i)).fetchone():
            continue
        if conn.execute("SELECT 1 FROM kinship_links WHERE ended_day IS NULL AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))", (s, i, i, s)).fetchone():
            continue
        out[i] = max(0.05, w) * max(0.1, 1.0 - gap / (p.f("lm_romance_gap_years") + 1))
    return out


def _open_romance(p: _Pass, s: int, rng) -> None:
    o = _pick(rng, _single_candidates(p, s))
    if o is None:
        return
    if s == p.me:  # the engine does not decide whom he wants: the other takes the interest
        s, o = o, s
    m = _open(p, "romance", s, o, rng)
    _effect(p, m["id"], s, o, "took an interest", affection_delta=12, familiarity_delta=8)
    if o == p.me:
        return _wait(p, m, "interest_in_him")
    return _step(p, m, "interest", next_days=_span(p, m, "lm_stage_days"))


def _later(p: _Pass, m: dict, days: float) -> None:
    """Nothing new to tell yet: look again later."""
    p.conn.execute("UPDATE life_matters SET next_day=? WHERE id=?", (p.day + max(1, int(round(days))), m["id"]))


def _step_romance(p: _Pass, m: dict) -> None:
    conn, s, o = p.conn, m["subject_actor_id"], m["other_actor_id"]
    if o is None or not _living(conn, o):
        return _step(p, m, "ended", close=True)
    if m["stage"] == "engaged":
        return _step_engaged(p, m)
    if p.me in (s, o) and m["stage"] != "interest":
        return _later(p, m, p.f("lm_stage_days"))  # his own courtship moves only by what he does
    view = rel.relationship_view(conn, o, s)
    if m["stage"] == "interest":
        if m["rng"].random() < p.f("lm_romance_return") + (view["affection"] - view["resentment"]) / 200.0:
            _effect(p, m["id"], o, s, "returned the interest", affection_delta=12, familiarity_delta=8)
            conn.execute("""UPDATE social_contact_links SET affinity=MIN(100,affinity+15) WHERE status='active'
                            AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))""", (s, o, o, s))
            m["data"]["since"] = p.day
            return _step(p, m, "courting", next_days=_span(p, m, "lm_courting_days"))
        _effect(p, m["id"], s, o, "was turned down", affection_delta=-8, resentment_delta=4)
        return _step(p, m, "turned_down", close=True)
    if m["data"].get("match"):  # a courtship that is heading to marriage: it lasts its time, then an engagement, unless it ends
        due = int(m["data"].get("since", p.day)) + int(m["data"]["wait"])
        if p.day < due:
            return _later(p, m, due - p.day)
        if m["rng"].random() >= p.f("lm_match_breaks"):
            return _engage(p, m)
        return _break_off(p, m, "broke_off")
    if m["stage"] == "courting":
        if m["rng"].random() >= p.f("lm_romance_keeps"):
            return _break_off(p, m, "broke_off")
        rel.adjust_relationship_pair(conn, s, o, p.day, symmetric={"affection_delta": 15.0, "trust_delta": 8.0})
        _effect(p, m["id"], s, o, "grew serious", affection_delta=5)
        conn.execute("""UPDATE social_contact_links SET affinity=MIN(100,affinity+20) WHERE status='active'
                        AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))""", (s, o, o, s))
        return _step(p, m, "serious", next_days=_span(p, m, "lm_serious_days"))
    if m["rng"].random() < p.f("lm_serious_breaks"):
        return _break_off(p, m, "broke_off")
    return _later(p, m, _span(p, m, "lm_serious_days"))


def _break_off(p: _Pass, m: dict, stage: str) -> None:
    s, o = m["subject_actor_id"], m["other_actor_id"]
    _effect(p, m["id"], s, o, "broke it off", affection_delta=-20, resentment_delta=8)
    _effect(p, m["id"], o, s, "broke it off", affection_delta=-20, resentment_delta=8)
    _step(p, m, stage, close=True)


def told(conn: sqlite3.Connection, me: int, close: dict[int, float] | None = None) -> set[int]:
    """Family, friends and workmates: what happens to them they tell him themselves."""
    from . import texture
    near = float(figure(conn, "lm_told_closeness", 0.55))
    return {i for i, w in (texture.circle(conn, me) if close is None else close).items() if w >= near}


def _engage(p: _Pass, m: dict, wait: int | None = None) -> None:
    from . import world_calendar
    s, o = m["subject_actor_id"], m["other_actor_id"]
    wait = int(round(_span(p, m, "lm_engaged_days"))) if wait is None else wait
    date = world_calendar.format_date(package_for(p.conn), p.day + wait)
    m["data"]["wed_day"] = p.day + wait
    _effect(p, m["id"], s, o, "got engaged", affection_delta=10, trust_delta=8)
    _effect(p, m["id"], o, s, "got engaged", affection_delta=10, trust_delta=8)
    _step(p, m, "engaged", next_days=wait, date=date)
    if p.me is None or p.me in (s, o):
        return
    if p.told is None:
        p.told = told(p.conn, p.me)
    if s in p.told or o in p.told:
        text = (p.words.get("texts") or {}).get("romance.invited")
        if text:
            p.conn.execute("INSERT INTO life_matter_steps(matter_id,day,stage,text,actors) VALUES (?,?,'invited',?,?)",
                           (m["id"], p.day, text.format(s=_name(p.conn, s), o=_name(p.conn, o), date=date), f"{s},{o},{p.me}"))


def _step_engaged(p: _Pass, m: dict) -> None:
    conn, s, o = p.conn, m["subject_actor_id"], m["other_actor_id"]
    if p.day < int(m["data"].get("wed_day", p.day)):
        return _later(p, m, int(m["data"]["wed_day"]) - p.day)
    if conn.execute("SELECT 1 FROM household_unions WHERE status='active' AND (actor_a_id IN (?,?) OR actor_b_id IN (?,?))",
                    (s, o, s, o)).fetchone():
        return _break_off(p, m, "engagement_off")
    if p.me not in (s, o) and m["rng"].random() < p.f("lm_match_breaks"):  # his own engagement is his to break
        return _break_off(p, m, "engagement_off")
    from .opening_family import wed_courtship
    first, second = (o, s) if o == p.me else (s, o)  # whoever moves in joins the first one's home; he is never moved by it
    try:
        wed_courtship(conn, p.day, first, second)
    except ValueError:
        return _break_off(p, m, "engagement_off")
    return _step(p, m, "wed", close=True)


def courtship(conn: sqlite3.Connection, a: int, b: int) -> sqlite3.Row | None:
    """The open courtship between two people, if there is one."""
    return conn.execute("""SELECT * FROM life_matters WHERE kind='romance' AND status='open' AND
                           ((subject_actor_id=? AND other_actor_id=?) OR (subject_actor_id=? AND other_actor_id=?)) ORDER BY id DESC LIMIT 1""",
                        (a, b, b, a)).fetchone()


def open_courtships(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    """Everyone now in an open courtship, with it."""
    out: dict[int, sqlite3.Row] = {}
    for r in conn.execute("SELECT * FROM life_matters WHERE kind='romance' AND status='open' ORDER BY id"):
        for a in (r["subject_actor_id"], r["other_actor_id"]):
            if a is not None:
                out[int(a)] = r
    return out


def begin_courtship(conn: sqlite3.Connection, day: int, subject: int, other: int, *, match: bool = False, since: int | None = None,
                    wait: int | None = None) -> int:
    """Two people start going together. `match` marks a courtship that is heading to marriage."""
    p = _Pass(conn, day)
    m = _open(p, "romance", subject, other, random.Random(f"{p.seed}:courtship:{subject}:{other}:{day}"))
    m["data"]["since"] = int(day if since is None else since)
    if match:
        m["data"].update(match=1, wait=int(round(_span(p, m, "lm_match_courting_days"))) if wait is None else wait)
    _effect(p, m["id"], subject, other, "started courting", affection_delta=25, familiarity_delta=30)
    _effect(p, m["id"], other, subject, "started courting", affection_delta=25, familiarity_delta=30)
    _step(p, m, "courting", next_days=m["data"]["wait"] if match else _span(p, m, "lm_courting_days"))
    return m["id"]


def seed_match(conn: sqlite3.Connection, subject: int, other: int, *, since: int, wait: int, engaged: int | None = None) -> int:
    """A courtship heading to marriage that was already under way when it is written down, at the stage it had reached: courting
    since `since` for `wait` days, then (when `engaged` is given) engaged for that many days up to the wedding."""
    mid = begin_courtship(conn, since, subject, other, match=True, wait=wait)
    if engaged is not None:
        p = _Pass(conn, since + wait)
        _engage(p, _load_matter(p, conn.execute("SELECT * FROM life_matters WHERE id=?", (mid,)).fetchone()), wait=engaged)
    return mid


def make_match(conn: sqlite3.Connection, day: int, row: sqlite3.Row) -> None:
    """An existing courtship is now heading to marriage: after its time it leads to an engagement."""
    data_ = json.loads(row["data_json"] or "{}")
    if data_.get("match"):
        return
    p = _Pass(conn, day)
    m = _load_matter(p, row)
    m["data"].setdefault("since", int(row["stage_day"] or day))
    m["data"].update(match=1, wait=int(round(_span(p, m, "lm_match_courting_days"))))
    conn.execute("UPDATE life_matters SET data_json=?,next_day=? WHERE id=?",
                 (json.dumps(m["data"], sort_keys=True), max(day + WEEK, m["data"]["since"] + m["data"]["wait"]), m["id"]))


def engage_pair(conn: sqlite3.Connection, day: int, a: int, b: int) -> int:
    """An accepted proposal: they are engaged, and the wedding follows on its date."""
    if conn.execute("SELECT 1 FROM household_unions WHERE status='active' AND (actor_a_id IN (?,?) OR actor_b_id IN (?,?))",
                    (a, b, a, b)).fetchone():
        raise ValueError("one or both actors are already in an active union")
    row = courtship(conn, a, b)
    mid = int(row["id"]) if row is not None else begin_courtship(conn, day, a, b)
    row = conn.execute("SELECT * FROM life_matters WHERE id=?", (mid,)).fetchone()
    if row["stage"] != "engaged":
        p = _Pass(conn, day)
        _engage(p, _load_matter(p, row))
    return mid


# ---- quarrels -----------------------------------------------------------------------------------------------------------

def footing(conn: sqlite3.Connection, a: int, b: int) -> str:
    """What two people mainly are to each other: the key under which the package keeps what such a pair falls out over."""
    kinds = {str(r[0]) for r in conn.execute("""SELECT kin_kind FROM kinship_links WHERE ended_day IS NULL
                 AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))""", (a, b, b, a))}
    if kinds & {"parent", "child"}:
        return "parent_child"
    if "sibling" in kinds:
        return "siblings"
    if "spouse" in kinds or courtship(conn, a, b) or conn.execute(
            """SELECT 1 FROM household_unions WHERE status='active' AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))""",
            (a, b, b, a)).fetchone():
        return "couple"
    if kinds:
        return "family"
    if conn.execute("""SELECT 1 FROM household_members x JOIN household_members y ON y.household_id=x.household_id
                       WHERE x.actor_id=? AND y.actor_id=? AND x.status='active' AND y.status='active'""", (a, b)).fetchone():
        return "home"
    if conn.execute("""SELECT 1 FROM enterprise_staff x JOIN enterprise_staff y ON y.enterprise_id=x.enterprise_id
                       WHERE x.actor_id=? AND y.actor_id=? AND x.status='active' AND y.status='active'""", (a, b)).fetchone():
        return "work"
    v = rel.relationship_view(conn, a, b)
    return "friends" if v["affection"] >= float(figure(conn, "lm_friend_affection", 30.0)) else "others"


def _meets(p: _Pass, need: str, a: int, b: int) -> bool:
    if need == "of_age":  # something only grown people who go out could fall out over
        oldest = p.day - int(p.f("out_age_min") * YEAR)
        return p.conn.execute("SELECT COUNT(*) FROM actor_life_profiles WHERE actor_id IN (?,?) AND birth_day<=?", (a, b, oldest)).fetchone()[0] == 2
    if need == "debt":
        return bool(p.conn.execute("""SELECT 1 FROM life_matters WHERE kind='money' AND status='open'
                      AND ((subject_actor_id=? AND other_actor_id=?) OR (subject_actor_id=? AND other_actor_id=?))""", (a, b, b, a)).fetchone())
    return False


def _topic(p: _Pass, a: int, b: int, rng) -> str:
    book = p.words.get("quarrel_topics") or {}
    if isinstance(book, dict):
        book = book.get(footing(p.conn, a, b)) or book.get("others") or []
    fit = [t if isinstance(t, str) else t["text"] for t in book if isinstance(t, str) or _meets(p, str(t.get("needs")), a, b)]
    return fit[rng.randrange(len(fit))] if fit else "something"

def _open_quarrel(p: _Pass, s: int, rng) -> None:
    ties = p.ties(s)
    weights = {}
    for i, w in ties.items():
        v = rel.relationship_view(p.conn, s, i)
        weights[i] = 0.1 + w * 0.3 + max(0.0, v["resentment"]) / 20.0
    o = _pick(rng, weights)
    if o is None:
        return
    if s == p.me:  # someone picks it with him
        s, o = o, s
    m = _open(p, "quarrel", s, o, rng)
    m["data"] = {"topic": _topic(p, s, o, rng)}
    _effect(p, m["id"], s, o, "quarrelled", resentment_delta=8, trust_delta=-4)
    _effect(p, m["id"], o, s, "quarrelled", resentment_delta=6, trust_delta=-3)
    if o == p.me:  # how it ends is partly his to settle
        return _wait(p, m, "words")
    return _step(p, m, "words", next_days=_span(p, m, "lm_quarrel_days"))


def _step_quarrel(p: _Pass, m: dict) -> None:
    conn, s, o, rng = p.conn, m["subject_actor_id"], m["other_actor_id"], m["rng"]
    if o is None or not _living(conn, o):
        return _step(p, m, "ended", close=True)
    drive = {int(r[0]): float(r[1]) for r in conn.execute("SELECT actor_id,aggression FROM actor_drives WHERE actor_id IN (?,?)", (s, o))}
    heat = (drive.get(s, 0.5) + (drive.get(o, 0.5) if o != p.me else 0.0)) / (2 if o != p.me else 1)
    if rng.random() < p.f("lm_blows_chance") * 2 * heat:
        if o == p.me:
            striker, victim = s, o
        elif s == p.me:
            striker, victim = o, s
        else:
            striker, victim = (s, o) if rng.random() < drive.get(s, 0.5) / max(1e-9, drive.get(s, 0.5) + drive.get(o, 0.5)) else (o, s)
        from .harm import record_harm
        severity = max(1.0, rng.expovariate(1.0 / p.f("lm_blows_severity")))
        override = None
        if victim == p.me:  # his survival leans to living; the hurt itself is real
            override = "persistent" if severity >= p.f("lm_blows_lasting") else "transient"
        place = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (victim,)).fetchone()
        res = record_harm(conn, victim, source_kind=SOURCE, source_ref_id=m["id"], severity=min(100.0, severity), intent_class="hostile",
                          location_id=place[0] if place else None, metadata={"offender_actor_id": striker}, outcome_override=override)
        _effect(p, m["id"], victim, striker, "was struck", resentment_delta=25, fear_delta=10, trust_delta=-15)
        return _step(p, m, "killed" if res.get("outcome") == "fatal" else "blows", close=True,
                     hitter=_name(conn, striker), hurt=_name(conn, victim))
    if o == p.me:  # he has not answered: it is not made up for him
        _effect(p, m["id"], s, o, "heard nothing back", resentment_delta=6)
        return _step(p, m, "let_stand", close=True)
    if rng.random() < p.f("lm_quarrel_makes_up"):
        _effect(p, m["id"], s, o, "made it up", resentment_delta=-8, trust_delta=3)
        if o != p.me:
            _effect(p, m["id"], o, s, "made it up", resentment_delta=-6, trust_delta=2)
        return _step(p, m, "made_up", close=True)
    _effect(p, m["id"], s, o, "held on to it", resentment_delta=6)
    return _step(p, m, "grudge", close=True)


# ---- illness ------------------------------------------------------------------------------------------------------------

def _open_illness(p: _Pass, s: int, rng) -> None:
    from .health import add_condition
    birth = p.conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (s,)).fetchone()
    age = (p.day - int(birth[0])) / YEAR if birth else 30.0
    kinds = [k for k in p.words.get("illnesses") or [] if age >= float(k.get("from_age", 0))]
    if not kinds:
        return
    k = kinds[_pick(rng, {i: float(x.get("weight", 1.0)) for i, x in enumerate(kinds)})]
    severity = float(k["severity"][0]) + rng.random() * (float(k["severity"][1]) - float(k["severity"][0]))
    frail = max(0.0, age - p.f("lm_frail_age")) / 30.0
    cid = add_condition(p.conn, s, "illness", str(k["label"]), severity=severity, body_system=k.get("body_system"),
                        capacity_impact=severity * 0.6, pain_impact=severity * 0.4,
                        recovery_rate_per_30=float(k["recovery"]), progression_rate_per_30=severity * frail * 0.05,
                        fatality_pressure=severity * frail * float(k.get("deadliness", 0.2)), next_review_days=14,
                        metadata={"life_matter": True})
    m = _open(p, "illness", s, None, rng)
    m["data"] = {"label": str(k["label"]), "condition_id": cid}
    return _step(p, m, "ill" if severity < p.f("lm_illness_serious") else "badly_ill", next_days=p.f("lm_illness_check_days"))


def _step_illness(p: _Pass, m: dict) -> None:
    conn = p.conn
    if not _living(conn, m["subject_actor_id"]):
        return _step(p, m, "died", close=True)
    r = conn.execute("""SELECT status,severity,recovery_rate_per_30,progression_rate_per_30,last_review_day
                        FROM health_conditions WHERE id=?""", (m["data"].get("condition_id"),)).fetchone()
    # the health system reviews at its own long intervals: between them, its own pace says where the illness stands
    left = float(r[1]) - (float(r[2]) - float(r[3])) * (p.day - int(r[4])) / 30.0 if r else 0.0
    if not r or str(r[0]) not in ("active", "recovering") or left <= 0.5:
        return _step(p, m, "recovered", close=True)
    conn.execute("UPDATE life_matters SET next_day=? WHERE id=?", (p.day + int(p.f("lm_illness_check_days")), m["id"]))


# ---- rivalry ------------------------------------------------------------------------------------------------------------

def _open_rivalry(p: _Pass, s: int, rng) -> None:
    conn = p.conn
    mine = conn.execute("""SELECT e.id,e.location_id,bp.archetype_id,e.name FROM civilian_enterprises e
                           JOIN enterprise_business_profiles bp ON bp.enterprise_id=e.id WHERE e.owner_actor_id=? AND e.status IN ('active','strained')
                           ORDER BY e.id LIMIT 1""", (s,)).fetchone()
    if not mine:
        return
    others = {int(r[0]): 1.0 for r in conn.execute(
        """SELECT e.owner_actor_id FROM civilian_enterprises e JOIN enterprise_business_profiles bp ON bp.enterprise_id=e.id
           WHERE bp.archetype_id=? AND e.location_id=? AND e.id<>? AND e.status IN ('active','strained') AND e.owner_actor_id IS NOT NULL""",
        (mine[2], mine[1], mine[0]))}
    others.pop(s, None)
    o = _pick(rng, {i: w for i, w in others.items() if _living(conn, i)})
    if o is None:
        return
    if s == p.me:
        s, o = o, s
    theirs = conn.execute("SELECT name FROM civilian_enterprises WHERE owner_actor_id=? ORDER BY id LIMIT 1", (o,)).fetchone()
    m = _open(p, "rivalry", s, o, rng)
    m["data"] = {"business": str(theirs[0]) if theirs else "the business"}
    _effect(p, m["id"], o, s, "is being undercut", resentment_delta=10, professional_confidence_delta=-3)
    return _step(p, m, "undercutting", next_days=_span(p, m, "lm_courting_days"))


def _step_rivalry(p: _Pass, m: dict) -> None:
    conn, s, o, rng = p.conn, m["subject_actor_id"], m["other_actor_id"], m["rng"]
    if o is None or not _living(conn, o) or not _living(conn, s):
        return _step(p, m, "ended", close=True)
    roll = rng.random()
    if roll < p.f("lm_rivalry_gains"):
        for owner, delta in ((s, 1.0), (o, -1.0)):
            conn.execute("UPDATE civilian_enterprises SET reputation=MAX(0,MIN(100,reputation+?)) WHERE owner_actor_id=?",
                         (delta * p.f("lm_rivalry_reputation"), owner))
        _effect(p, m["id"], o, s, "lost custom to them", resentment_delta=10)
        return _step(p, m, "gains", close=True)
    if roll < p.f("lm_rivalry_gains") + p.f("lm_quarrel_makes_up"):
        return _step(p, m, "fizzled", close=True)
    _effect(p, m["id"], o, s, "bad blood", resentment_delta=15, trust_delta=-10)
    return _step(p, m, "bad_blood", close=True)


# ---- work ----------------------------------------------------------------------------------------------------------------

def _open_work(p: _Pass, s: int, rng) -> None:
    conn = p.conn
    trade = conn.execute("""SELECT es.enterprise_id, ba.name FROM enterprise_staff es
                            JOIN enterprise_business_profiles bp ON bp.enterprise_id=es.enterprise_id JOIN business_archetypes ba ON ba.id=bp.archetype_id
                            WHERE es.actor_id=? AND es.status='active' ORDER BY es.enterprise_id LIMIT 1""", (s,)).fetchone()
    if not trade:
        return
    amount = round(p.f("lm_work_price_usd") * math.exp(rng.gauss(0.0, 0.8)))
    staff = {int(r[0]) for r in conn.execute("SELECT actor_id FROM enterprise_staff WHERE enterprise_id=? AND status='active'", (trade[0],))}
    ties = {i: w for i, w in p.ties(s).items() if i not in staff and i != p.me and p.purse(i) >= amount}
    o = _pick(rng, ties)
    if o is None:
        return
    m = _open(p, "work", s, o, rng)
    m["amount"] = amount
    m["data"] = {"trade": str(trade[1]).lower(), "enterprise_id": int(trade[0])}
    if p.me in (s, o):
        return _wait(p, m, "asked")
    return _step(p, m, "asked", next_days=_span(p, m, "lm_stage_days"))


def _step_work(p: _Pass, m: dict) -> None:
    conn, s, o = p.conn, m["subject_actor_id"], m["other_actor_id"]
    if o is None or not _living(conn, o) or not _living(conn, s):
        return _step(p, m, "fell_through", close=True)
    amount = float(m["amount"] or 0)
    if m["rng"].random() >= p.f("lm_work_goes_ahead"):
        return _step(p, m, "fell_through", close=True)
    if p.purse(o) < amount:
        _effect(p, m["id"], s, o, "could not pay for the work", trust_delta=-5)
        return _step(p, m, "could_not_pay", close=True)
    p.pay(("person", o), ("business", int(m["data"]["enterprise_id"])), amount, f"work payment (matter {m['id']})")
    _effect(p, m["id"], o, s, "got the work done", professional_confidence_delta=6, familiarity_delta=5)
    return _step(p, m, "done", close=True)


# ---- police --------------------------------------------------------------------------------------------------------------

def _open_police(p: _Pass, s: int, rng) -> None:
    m = _open(p, "police", s, None, rng)
    matters = p.words.get("police_matters") or ["something"]
    m["data"] = {"matter": matters[rng.randrange(len(matters))]}
    for (org,) in p.conn.execute("SELECT DISTINCT org_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (s,)).fetchall():
        p.conn.execute("UPDATE org_heat SET investigative_heat=investigative_heat+? WHERE org_actor_id=?", (p.f("lm_police_heat"), org))
    return _step(p, m, "stopped", next_days=_span(p, m, "lm_courting_days"))


def _step_police(p: _Pass, m: dict) -> None:
    return _step(p, m, "watched" if m["rng"].random() < p.f("lm_police_watches") else "dropped", close=True)


OPENERS = {"money": _open_money, "romance": _open_romance, "quarrel": _open_quarrel, "illness": _open_illness,
           "rivalry": _open_rivalry, "work": _open_work, "police": _open_police}
STEPS = {"money": _step_money, "romance": _step_romance, "quarrel": _step_quarrel, "illness": _step_illness,
         "rivalry": _step_rivalry, "work": _step_work, "police": _step_police}


# ---- the weekly pass -------------------------------------------------------------------------------------------------

def _load_matter(p: _Pass, r: sqlite3.Row) -> dict:
    return {"id": int(r["id"]), "kind": r["kind"], "subject_actor_id": int(r["subject_actor_id"]),
            "other_actor_id": None if r["other_actor_id"] is None else int(r["other_actor_id"]), "stage": r["stage"], "amount": r["amount"],
            "data": json.loads(r["data_json"] or "{}"), "awaiting": False,
            "rng": random.Random(f"{p.seed}:life_step:{r['id']}:{p.day}")}


def _advance_open(p: _Pass) -> int:
    rows = p.conn.execute("SELECT * FROM life_matters WHERE status='open' AND next_day<=? ORDER BY id", (p.day,)).fetchall()
    n = 0
    for r in rows:
        m = _load_matter(p, r)
        if r["awaiting"] and m["kind"] not in ("scuffle", "quarrel"):  # nothing was done about it (a challenge or quarrel moves on)
            if m["other_actor_id"] is not None and m["other_actor_id"] != p.me and p.me is not None:
                _effect(p, m["id"], m["other_actor_id"], p.me, "heard nothing back", resentment_delta=3)
            ending = "let_ride" if m["stage"] == "short_self" else "faded" if m["kind"] == "fling" else "lapsed"
            _step(p, m, ending, close=True)
        elif not _living(p.conn, m["subject_actor_id"]):
            _step(p, m, "died" if m["kind"] == "illness" else "ended", close=True)
        else:
            STEPS[m["kind"]](p, m)
        n += 1
    return n


def _due_people(p: _Pass) -> list[tuple[int, float]]:
    """Who is looked at this week, with the days since he was last looked at."""
    conn, day = p.conn, p.day
    quiet = max(1, int(p.f("lm_quiet_weeks")))
    often = set(tiers.rising_actor_ids(conn, day))
    often |= {int(r[0]) for r in conn.execute("SELECT actor_id FROM simulation_profiles WHERE tier='ACTIVE'")}
    batching = tiers.batching(conn)
    row = conn.execute("SELECT value FROM engine_meta WHERE key='life_matters_start'").fetchone()
    if row is None:
        start = day - WEEK
        conn.execute("INSERT INTO engine_meta(key,value) VALUES ('life_matters_start',?)", (str(start),))
    else:
        start = int(row[0])
    clock = {int(r[0]): int(r[1]) for r in conn.execute("SELECT actor_id,day FROM life_matter_clock")}
    week = day // WEEK
    out = []
    for (aid,) in conn.execute("""SELECT a.id FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
                                  WHERE lp.life_status='living' AND lower(COALESCE(a.status,'active')) NOT IN ('dead','deceased','historical')
                                    AND lp.birth_day<=? ORDER BY a.id""", (day - int(p.f("lm_adult_age") * YEAR),)):
        aid = int(aid)
        if batching and aid not in often and (aid + week) % quiet:
            continue
        since = day - max(clock.get(aid, start), start)
        if since > 0:
            out.append((aid, float(since)))
    conn.executemany("INSERT INTO life_matter_clock(actor_id,day) VALUES (?,?) ON CONFLICT(actor_id) DO UPDATE SET day=excluded.day",
                     [(a, day) for a, _ in out])
    return out


def _rates(p: _Pass):
    """The yearly chance of each kind for one person, from the state read once this week."""
    conn, day = p.conn, p.day
    cash = p.cash()
    short_below = p.f("lm_short_weeks") * p.f("lm_living_week_usd")
    taken = {int(x) for r in conn.execute("SELECT actor_a_id,actor_b_id FROM household_unions WHERE status='active'") for x in r}
    taken |= set(open_courtships(conn))
    profile = {int(r[0]): ((day - int(r[1])) / YEAR, int(r[2] or 0), r[3]) for r in conn.execute(
        "SELECT actor_id,birth_day,family_formation_eligible,demographic_sex FROM actor_life_profiles WHERE life_status='living'")}
    resent = {int(r[0]): float(r[1]) for r in conn.execute("SELECT actor_a_id,MAX(resentment) FROM relationships GROUP BY actor_a_id")}
    temper = {int(r[0]): float(r[1]) for r in conn.execute("SELECT actor_id,aggression FROM actor_drives")}
    traders = {int(r[0]) for r in conn.execute("SELECT actor_id FROM enterprise_staff WHERE status='active'")}
    owners = {int(r[0]) for r in conn.execute(
        "SELECT owner_actor_id FROM civilian_enterprises WHERE status IN ('active','strained') AND owner_actor_id IS NOT NULL")}
    crime = {int(r[0]) for r in conn.execute(
        "SELECT actor_id FROM background_person_profiles WHERE actor_id IS NOT NULL AND criminal_familiarity>=?", (p.f("lm_police_familiarity"),))}
    crime |= {int(r[0]) for r in conn.execute(
        "SELECT s.actor_id FROM org_seats s JOIN org_profiles o ON o.org_actor_id=s.org_actor_id WHERE s.status='active' AND o.sphere=?",
        (str(p.words.get("police_sphere") or ""),))}
    inside = {int(r[0]) for r in conn.execute("SELECT actor_id FROM inmate_stays WHERE until_day IS NULL OR until_day>?", (day,))}

    g = {k: p.f(f"lm_{k}") for k in ("frail_age", "illness_year", "illness_year_per_age", "money_year_short", "money_year_base", "romance_age_min",
                                       "romance_year", "romance_age_span", "quarrel_year", "resent_scale", "rivalry_year", "work_year", "police_year",
                                       "fling_year", "scuffle_year")}
    out_min, out_max = p.f("out_age_min"), p.f("out_age_max")

    def rates(a: int) -> list[tuple[str, float]]:
        age, eligible, sex = profile.get(a, (30.0, 0, None))
        frail = max(0.0, age - g["frail_age"])
        out = [("illness", g["illness_year"] + frail * g["illness_year_per_age"])]
        if a in inside:
            return out
        if a in cash:
            out.append(("money", g["money_year_short"] if cash[a] < short_below else g["money_year_base"]))
        if eligible and a not in taken and age >= g["romance_age_min"]:
            young = max(0.0, 1.0 - max(0.0, age - g["romance_age_min"]) / g["romance_age_span"])
            out.append(("romance", g["romance_year"] * young))
        out.append(("quarrel", g["quarrel_year"] * (0.5 + temper.get(a, 0.5)) * (1.0 + max(0.0, resent.get(a, 0.0)) / g["resent_scale"])))
        if a in owners:
            out.append(("rivalry", g["rivalry_year"]))
        if a in traders:
            out.append(("work", g["work_year"]))
        if a in crime:
            out.append(("police", g["police_year"]))
        if out_min <= age <= out_max:  # who goes out, and so who flirts and scuffles, thins with age
            nights = max(0.0, 1.0 - (age - out_min) / (out_max - out_min))
            if eligible and a not in taken:
                out.append(("fling", g["fling_year"] * nights))
            if sex == "male":
                out.append(("scuffle", g["scuffle_year"] * nights * (0.5 + temper.get(a, 0.5))))
        return out
    return rates


def weekly(conn: sqlite3.Connection, day: int) -> dict:
    """One week: open matters move on, and the people due this week may find something new has happened to them."""
    if not enabled(conn):
        return {}
    p = _Pass(conn, day)
    moved = _advance_open(p)
    rates = _rates(p)
    open_now = {(r[0], int(r[1])) for r in conn.execute("SELECT kind,subject_actor_id FROM life_matters WHERE status='open'")}
    opened = 0
    rng = random.Random(f"{p.seed}:life:{day}")  # one stream a week, drawn in person order
    for aid, since in _due_people(p):
        for kind, per_year in rates(aid):
            if rng.random() >= 1.0 - math.exp(-per_year * since / YEAR):
                continue
            if (kind, aid) in open_now:  # the thing already hanging over him is the same thing
                continue
            if not _living(conn, aid):
                break
            before = conn.total_changes
            OPENERS[kind](p, aid, random.Random(f"{p.seed}:life_open:{kind}:{day}:{aid}"))
            opened += 1 if conn.total_changes > before else 0
    if p.me is not None:  # delivery only: what of this week reaches him
        from . import hearsay
        hearsay.reach(conn, p.me, day)
    return {"life_matters_opened": opened, "life_matters_moved": moved}


from . import outings  # noqa: E402,F401  (nights out: the fling and scuffle matters)
