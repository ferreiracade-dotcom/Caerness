# Three levels, nearby code: batch 2 of 5: Private life of named people

Same review as the first file (design revision 3.1 and its contract are already with you; not repeated).
This batch settles suspicion 4. For each module, give the same verdict as before (keep as is, fold into the build, rework, or cut),
with the reason and function names, and when to do it.

Modules in this batch: engine/life_matters.py, engine/household_life.py, engine/civilian_life.py, engine/temptations.py, engine/outings.py, engine/psych.py, engine/texture.py, engine/emergence.py, engine/attention.py, engine/commitments.py, engine/seeking.py.


## engine/life_matters.py

```python
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


def _ids_of(text: str) -> list[int]:
    return [int(x) for x in str(text or "").split(",") if x]


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


def family_of(conn: sqlite3.Connection, a: int) -> set[int]:
    """His kin and the people he shares a house with."""
    return {int(r[0]) for r in conn.execute(
        """SELECT CASE WHEN actor_a_id=? THEN actor_b_id ELSE actor_a_id END FROM kinship_links
           WHERE (actor_a_id=? OR actor_b_id=?) AND ended_day IS NULL
           UNION SELECT h2.actor_id FROM household_members h1 JOIN household_members h2 ON h2.household_id=h1.household_id
           WHERE h1.actor_id=? AND h2.actor_id<>? AND h1.status='active' AND h2.status='active'""", (a, a, a, a, a))}


def has(p: _Pass, a: int, need: str) -> bool:
    """Whether a person has the thing a job turns on: one on record for him or his household, else the same answer every time from
    the share of households that have one (figure `lm_have_<need>`)."""
    conn = p.conn
    home = [int(r[0]) for r in conn.execute(
        "SELECT household_id FROM household_members WHERE actor_id=? AND status='active' ORDER BY household_id LIMIT 1", (a,))]
    folk = [a] + ([int(r[0]) for r in conn.execute(
        "SELECT actor_id FROM household_members WHERE household_id=? AND status='active'", (home[0],))] if home else [])
    marks = ",".join("?" * len(folk))
    if conn.execute(f"""SELECT 1 FROM possessions WHERE holder_actor_id IN ({marks}) AND item_type=? AND status='held'
                        UNION SELECT 1 FROM bearing_marks WHERE actor_id IN ({marks}) AND kind=? AND status='active'""",
                    (*folk, need, *folk, need)).fetchone():
        return True
    whose = f"home:{home[0]}" if home else f"person:{a}"
    return random.Random(f"{p.seed}:have:{need}:{whose}").random() < p.f(f"lm_have_{need}")


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


def _step(p: _Pass, m: dict, stage: str, *, close: bool = False, next_days: float | None = None, said: str | None = None,
          **words) -> None:
    """Record where the matter now stands, in the package's words (or in `said`)."""
    conn = p.conn
    tmpl = (p.words.get("texts") or {}).get(f"{m['kind']}.{stage}") or (p.words.get("texts") or {}).get(stage)
    awaiting = int(bool(m.get("awaiting")))
    text = None
    if tmpl or said:
        fields = {"s": _name(conn, m["subject_actor_id"]), "o": _name(conn, m["other_actor_id"]),
                  "amount": money(p.words, m["amount"]) if m.get("amount") else "", **m.get("data", {}), **words}
        text = said or tmpl.format(**fields)
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


def skip_began(conn: sqlite3.Connection, day: int) -> None:
    """A skip is running from `day`: nothing that turns to him during it runs out before he has been told."""
    if enabled(conn):
        conn.execute("INSERT INTO engine_meta(key,value) VALUES ('lm_skip_from',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (str(int(day)),))


def skip_ended(conn: sqlite3.Connection, me: int, day: int) -> None:
    """The skip is over and he hears what came up: his time to answer runs from today."""
    if not enabled(conn):
        return
    row = conn.execute("SELECT value FROM engine_meta WHERE key='lm_skip_from'").fetchone()
    if row is None:
        return
    conn.execute("""UPDATE life_matters SET next_day=MAX(next_day,?) WHERE status='open' AND awaiting=1 AND kind<>'scuffle'
                    AND (subject_actor_id=? OR other_actor_id=?) AND json_extract(data_json,'$.asked_day')>?""",
                 (day + int(_Pass(conn, day).f("lm_lapse_days")), me, me, int(row[0])))
    conn.execute("DELETE FROM engine_meta WHERE key='lm_skip_from'")


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
        from .physique import blow, standoff
        if o == p.me:
            striker, victim = s, o
        elif s == p.me:
            striker, victim = o, s
        else:  # temper decides who swings, and the bigger of the two is readier to
            ws, wo = drive.get(s, 0.5) * standoff(conn, s, o), drive.get(o, 0.5) * standoff(conn, o, s)
            striker, victim = (s, o) if rng.random() < ws / max(1e-9, ws + wo) else (o, s)
        from .harm import record_harm
        severity = max(1.0, rng.expovariate(1.0 / p.f("lm_blows_severity"))) * blow(conn, striker, victim, "fists")
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
    spec = (p.words.get("jobs") or {}).get(str(trade[1]).lower()) if trade else None
    if not spec:  # not a trade people bring a job of their own to
        return
    amount = round(p.f("lm_work_price_usd") * math.exp(rng.gauss(0.0, 0.8)))
    staff = {int(r[0]) for r in conn.execute("SELECT actor_id FROM enterprise_staff WHERE enterprise_id=? AND status='active'", (trade[0],))}
    own = family_of(conn, s)  # family ask favours; they are not paying customers
    need = spec.get("needs")
    ties = {i: w for i, w in p.ties(s).items()
            if i not in staff and i not in own and i != p.me and p.purse(i) >= amount and (not need or has(p, i, need))}
    o = _pick(rng, ties)
    if o is None:
        return
    job = spec["for"][rng.randrange(len(spec["for"]))]
    m = _open(p, "work", s, o, rng)
    m["amount"] = amount
    m["data"] = {"trade": str(trade[1]).lower(), "enterprise_id": int(trade[0]), "job": job}
    if p.me in (s, o):
        return _wait(p, m, "asked")
    return _step(p, m, "asked", next_days=_span(p, m, "lm_stage_days"))


def _step_work(p: _Pass, m: dict) -> None:
    conn, s, o = p.conn, m["subject_actor_id"], m["other_actor_id"]
    if o is None or not _living(conn, o) or not _living(conn, s):
        return _step(p, m, "fell_through", close=True)
    amount = float(m["amount"] or 0)
    if not m["data"].get("accepted") and m["rng"].random() >= p.f("lm_work_goes_ahead"):  # a job he took on goes ahead
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


# ---- his answers ------------------------------------------------------------------------------------------------------

ANSWERS = ("yes", "no", "settled")


def answer(conn: sqlite3.Connection, me: int, matter_id: int, word: str, day: int, how: str | None = None) -> dict:
    """The protagonist's answer, given in play, to a matter waiting on him. "yes" and "no" move it on as that kind of matter goes;
    "settled" closes it as it was dealt with in the scene (`how` records it), moving nothing. ValueError names what stands in the way."""
    if word not in ANSWERS:
        raise ValueError("the answer must be yes, no or settled")
    r = conn.execute("""SELECT * FROM life_matters WHERE id=? AND status='open' AND awaiting=1
                        AND (subject_actor_id=? OR other_actor_id=?)""", (int(matter_id), me, me)).fetchone()
    if r is None:
        raise ValueError(f"Nothing of number {matter_id} is waiting on your answer; it may be closed already.")
    p = _Pass(conn, day)
    m = _load_matter(p, r)
    s, o = m["subject_actor_id"], m["other_actor_id"]
    other = o if s == me else s
    yes, kind, stage = word == "yes", m["kind"], m["stage"]
    if word == "settled":
        _step(p, m, "settled", close=True, said=" ".join(str(how or "").split())[:300] or None)
    elif kind == "romance" and stage == "interest_in_him":
        if yes:
            _effect(p, m["id"], s, o, "was welcomed", affection_delta=12, familiarity_delta=8)
            conn.execute("""UPDATE social_contact_links SET affinity=MIN(100,affinity+15) WHERE status='active'
                            AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))""", (s, o, o, s))
            m["data"]["since"] = p.day
            _step(p, m, "courting", next_days=_span(p, m, "lm_courting_days"))
        else:
            _effect(p, m["id"], s, o, "was turned down", affection_delta=-8, resentment_delta=4)
            _step(p, m, "turned_down", close=True)
    elif kind == "quarrel":
        if yes:
            _effect(p, m["id"], s, o, "made it up", resentment_delta=-8, trust_delta=3)
        else:
            _effect(p, m["id"], s, o, "held on to it", resentment_delta=6)
        _step(p, m, "made_up" if yes else "grudge", close=True)
    elif kind == "money" and stage == "asks":
        if yes:
            amount = float(m["amount"] or 0)
            have = ledger.balance(conn, ("person", me))
            if have < amount:
                raise ValueError(f"You have {money(p.words, have)}; {_name(conn, other)} asked for {money(p.words, amount)}. "
                                 "Answer no, or settle it another way and say how.")
            p.pay(("person", me), ("person", other), amount, f"personal loan (matter {m['id']})")
            _effect(p, m["id"], other, me, "borrowed money", obligation_delta=10, trust_delta=3)
            _step(p, m, "borrowed", next_days=_span(p, m, "lm_debt_days"))
        else:
            _effect(p, m["id"], other, me, "was turned down for a loan", resentment_delta=5)
            _step(p, m, "refused", close=True)
    elif kind == "money":
        _step(p, m, "settled_self" if yes else "let_ride", close=True)
    elif kind == "work":
        if yes:
            m["data"]["accepted"] = 1
            _effect(p, m["id"], other, me, "has his word on the job", trust_delta=3)
            _step(p, m, "agreed", next_days=_span(p, m, "lm_stage_days"))
        else:
            _step(p, m, "turned_away", close=True)
    elif kind == "fling":
        _effect(p, m["id"], other, me, "was welcomed" if yes else "was turned down", affection_delta=8 if yes else -6)
        _step(p, m, ("taken_up" if stage == "spark_him" else "seen_again") if yes else "faded", close=True)
    elif kind == "scuffle":
        if yes:
            outings._blows(p, m, m["rng"])
        else:
            _step(p, m, "lapsed", close=True)
    else:
        _step(p, m, "settled", close=True, said=" ".join(str(how or "").split())[:300] or None)
    from . import hearsay
    hearsay.reach(conn, me, day)  # he knows what he has just answered: it is not news to him later
    now = conn.execute("SELECT stage,status,summary FROM life_matters WHERE id=?", (m["id"],)).fetchone()
    return {"matter": m["id"], "stage": now["stage"], "closed": now["status"] == "closed", "summary": now["summary"]}


def acted(conn: sqlite3.Connection, me: int, action: str, target: int | None, day: int) -> list[dict]:
    """A deed of his that is itself an answer: coming to blows with somebody who squared up or quarrelled, or handing money to
    somebody who asked to borrow it. The matter is closed as settled; the deed's own effects are already recorded."""
    if target is None or not enabled(conn):
        return []
    kinds = {"attack": ("quarrel", "scuffle"), "lend": ("money",), "pay": ("money",)}.get(action)
    if not kinds:
        return []
    marks = ",".join("?" * len(kinds))
    rows = conn.execute(f"""SELECT id FROM life_matters WHERE status='open' AND awaiting=1 AND kind IN ({marks}) AND stage<>'short_self'
                            AND ((subject_actor_id=? AND other_actor_id=?) OR (subject_actor_id=? AND other_actor_id=?))""",
                        (*kinds, me, int(target), int(target), me)).fetchall()
    text = (data(conn).get("texts") or {}).get("answered_" + ("blows" if action == "attack" else "money"))
    how = text.format(s=_name(conn, me), o=_name(conn, int(target))) if text else None
    return [answer(conn, me, int(r[0]), "settled", day, how) for r in rows]


# ---- the weekly pass -------------------------------------------------------------------------------------------------

def _load_matter(p: _Pass, r: sqlite3.Row) -> dict:
    return {"id": int(r["id"]), "kind": r["kind"], "subject_actor_id": int(r["subject_actor_id"]),
            "other_actor_id": None if r["other_actor_id"] is None else int(r["other_actor_id"]), "stage": r["stage"], "amount": r["amount"],
            "data": json.loads(r["data_json"] or "{}"), "awaiting": False,
            "rng": random.Random(f"{p.seed}:life_step:{r['id']}:{p.day}")}


def _advance_open(p: _Pass) -> int:
    rows = p.conn.execute("SELECT * FROM life_matters WHERE status='open' AND next_day<=? ORDER BY id", (p.day,)).fetchall()
    n = 0
    held = p.conn.execute("SELECT value FROM engine_meta WHERE key='lm_skip_from'").fetchone()
    for r in rows:
        m = _load_matter(p, r)
        if held and r["awaiting"] and m["kind"] != "scuffle" and int(m["data"].get("asked_day", 0)) > int(held[0]):
            _later(p, m, p.f("lm_lapse_days"))  # it came up in the skip now running: he has not been told yet
            continue
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


def settle_circle(p: _Pass) -> int:
    """Give the people near the protagonist something to live with, once for each as he comes near: money on him if nobody has
    counted any, and, among those who live in one district, some who know each other, so that things happen between them and not
    only between each of them and him. Returns how many were taken in."""
    from . import money_records, texture
    from .opening_family import _seed_pair
    conn = p.conn
    row = conn.execute("SELECT value FROM engine_meta WHERE key='lm_circle_settled'").fetchone()
    done = set(_ids_of(row[0] if row else ""))
    close = texture.circle(conn, p.me)
    new = sorted(set(close) - done)
    if not new:
        return 0
    marks = ",".join("?" * len(close))
    grown = {int(r[0]): r[1] for r in conn.execute(
        f"""SELECT a.id,a.current_location_id FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id IN ({marks})
            AND lp.life_status='living' AND lp.birth_day<=?""", [*sorted(close), p.day - int(p.f("lm_adult_age") * YEAR)])}
    chance = figure(conn, "lm_circle_acquainted", 0.0)
    money = money_records.currency(conn)
    for a in new:
        if a not in grown:
            continue
        if money:  # what a grown person has by him: most are a few weeks or months ahead, a few are not
            by = random.Random(f"{p.seed}:circle_purse:{a}").uniform(0.0, figure(conn, "lm_circle_savings_weeks", 0.0))
            money_records.ensure_purse(conn, f"person:{a}", at_least=by * p.f("lm_living_week_usd"))
        for b in sorted(grown):
            if b == a or grown[b] != grown[a] or (b in new and b < a):
                continue
            key = f"circle:{min(a, b)}:{max(a, b)}"
            rng = random.Random(f"{p.seed}:{key}")
            if rng.random() < chance:
                _seed_pair(conn, a, b, "acquaintance", key=key, started_day=p.day - rng.randint(200, 2500))
    done |= set(grown)  # a child is taken in when grown
    conn.execute("INSERT INTO engine_meta(key,value) VALUES ('lm_circle_settled',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (",".join(map(str, sorted(done))),))
    p._cash, p._near = None, {}
    return len(set(new) & set(grown))


def weekly(conn: sqlite3.Connection, day: int) -> dict:
    """One week: open matters move on, and the people due this week may find something new has happened to them."""
    if not enabled(conn):
        return {}
    p = _Pass(conn, day)
    if p.me is not None:
        settle_circle(p)
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
```

## engine/household_life.py

```python
from __future__ import annotations

import json
import random
import sqlite3
from .relationships import adjust_relationship_pair, ensure_reciprocal_relationship
from .presence import actor_is_present_candidate
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _name(conn: sqlite3.Connection, actor_id: int | None) -> str:
    if actor_id is None:
        return "Unknown"
    row = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()
    return str(row[0]) if row else f"Actor {actor_id}"


def _actor_is_living(conn: sqlite3.Connection, actor_id: int) -> bool:
    row = conn.execute("SELECT status FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not row or str(row[0]) == "deceased":
        return False
    prof = conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    return not prof or str(prof[0]) == "living"


def _active_household_member(conn: sqlite3.Connection, household_id: int, actor_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM household_members WHERE household_id=? AND actor_id=? AND status='active'",
        (household_id, actor_id),
    ).fetchone()


def _close_other_household_memberships(conn: sqlite3.Connection, actor_id: int, keep_household_id: int, day: int) -> None:
    conn.execute(
        "UPDATE household_members SET status='former',left_day=? WHERE actor_id=? AND household_id<>? AND status='active'",
        (day, actor_id, keep_household_id),
    )


def _repair_household_head(conn: sqlite3.Connection, household_id: int, day: int) -> None:
    hh = conn.execute("SELECT head_actor_id,status FROM households WHERE id=?", (household_id,)).fetchone()
    if not hh:
        return
    head = hh["head_actor_id"]
    if head is not None and _active_household_member(conn, household_id, int(head)):
        return
    replacement = conn.execute(
        "SELECT actor_id FROM household_members WHERE household_id=? AND status='active' ORDER BY authority DESC,actor_id ASC LIMIT 1",
        (household_id,),
    ).fetchone()
    if replacement:
        aid = int(replacement[0])
        conn.execute("UPDATE households SET head_actor_id=?,updated_day=? WHERE id=?", (aid, day, household_id))
        conn.execute("UPDATE household_members SET role='head',authority=100 WHERE household_id=? AND actor_id=?", (household_id, aid))
    else:
        conn.execute("UPDATE households SET head_actor_id=NULL,status='dissolved',updated_day=? WHERE id=?", (day, household_id))


def _record_life_event(conn: sqlite3.Connection, event_kind: str, summary: str, *, actor_id: int | None = None,
                       related_actor_id: int | None = None, household_id: int | None = None,
                       location_id: int | None = None, day: int | None = None,
                       metadata: dict[str, Any] | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO life_events(day,event_kind,actor_id,related_actor_id,household_id,location_id,summary,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (_day(conn) if day is None else int(day), event_kind, actor_id, related_actor_id, household_id,
         location_id, summary, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _stage_for_age(age_days: int) -> str:
    years = age_days / 365.0
    if years < 2:
        return "infant"
    if years < 13:
        return "child"
    if years < 18:
        return "youth"
    if years < 60:
        return "adult"
    return "elder"


def set_life_profile(conn: sqlite3.Connection, actor_id: int, *, birth_day: int | None = None,
                     demographic_sex: str | None = None, origin_household_id: int | None = None,
                     current_household_id: int | None = None, family_formation_eligible: bool | None = None,
                     metadata: dict[str, Any] | None = None) -> None:
    day = _day(conn)
    stage = _stage_for_age(max(0, day - int(birth_day))) if birth_day is not None else "adult"
    conn.execute(
        """INSERT INTO actor_life_profiles(actor_id,birth_day,demographic_sex,life_stage,origin_household_id,current_household_id,
                                            family_formation_eligible,life_status,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,'living',?,?)
           ON CONFLICT(actor_id) DO UPDATE SET birth_day=COALESCE(excluded.birth_day,actor_life_profiles.birth_day),
             demographic_sex=COALESCE(excluded.demographic_sex,actor_life_profiles.demographic_sex),
             life_stage=CASE WHEN excluded.birth_day IS NOT NULL THEN excluded.life_stage ELSE actor_life_profiles.life_stage END,
             origin_household_id=COALESCE(excluded.origin_household_id,actor_life_profiles.origin_household_id),
             current_household_id=COALESCE(excluded.current_household_id,actor_life_profiles.current_household_id),
             family_formation_eligible=CASE WHEN ? THEN excluded.family_formation_eligible ELSE actor_life_profiles.family_formation_eligible END,
             last_review_day=excluded.last_review_day,
             metadata_json=CASE WHEN ? THEN excluded.metadata_json ELSE actor_life_profiles.metadata_json END""",
        (actor_id, birth_day, demographic_sex, stage, origin_household_id, current_household_id,
         1 if family_formation_eligible else 0, day, json.dumps(metadata or {}, sort_keys=True),
         1 if family_formation_eligible is not None else 0, 1 if metadata is not None else 0),
    )


def add_kinship(conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int, kin_kind: str, *,
                reciprocal_kind: str | None = None, legal_status: str = "recognized",
                metadata: dict[str, Any] | None = None) -> tuple[int, int | None]:
    if actor_a_id == actor_b_id:
        raise ValueError("Kinship cannot relate an actor to themselves")
    day = _day(conn)
    existing = conn.execute(
        "SELECT id FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind=? AND legal_status=? AND ended_day IS NULL ORDER BY id LIMIT 1",
        (actor_a_id, actor_b_id, kin_kind, legal_status),
    ).fetchone()
    if existing:
        rid = None
        if reciprocal_kind:
            reciprocal = conn.execute(
                "SELECT id FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind=? AND legal_status=? AND ended_day IS NULL ORDER BY id LIMIT 1",
                (actor_b_id, actor_a_id, reciprocal_kind, legal_status),
            ).fetchone()
            if reciprocal:
                rid = int(reciprocal[0])
            else:
                cur2 = conn.execute(
                    "INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day,metadata_json) VALUES (?,?,?,?,?,?)",
                    (actor_b_id, actor_a_id, reciprocal_kind, legal_status, day, json.dumps(metadata or {}, sort_keys=True)),
                )
                rid = int(cur2.lastrowid)
        return int(existing[0]), rid
    cur = conn.execute(
        "INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day,metadata_json) VALUES (?,?,?,?,?,?)",
        (actor_a_id, actor_b_id, kin_kind, legal_status, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    rid = None
    if reciprocal_kind:
        reciprocal = conn.execute(
            "SELECT id FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind=? AND legal_status=? AND ended_day IS NULL ORDER BY id LIMIT 1",
            (actor_b_id, actor_a_id, reciprocal_kind, legal_status),
        ).fetchone()
        if reciprocal:
            rid = int(reciprocal[0])
        else:
            cur2 = conn.execute(
                "INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day,metadata_json) VALUES (?,?,?,?,?,?)",
                (actor_b_id, actor_a_id, reciprocal_kind, legal_status, day, json.dumps(metadata or {}, sort_keys=True)),
            )
            rid = int(cur2.lastrowid)
    return int(cur.lastrowid), rid


def create_union(conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int, *, household_id: int | None = None,
                 union_kind: str = "marriage", family_plan: dict[str, Any] | None = None,
                 create_new_household_name: str | None = None) -> int:
    from .civilian import create_household, add_household_member
    day = _day(conn)
    if actor_a_id == actor_b_id:
        raise ValueError("A union requires two distinct actors")
    if not _actor_is_living(conn, actor_a_id) or not _actor_is_living(conn, actor_b_id):
        raise ValueError("A union requires living actors")
    kin_reason = prohibited_union_kinship_reason(conn, actor_a_id, actor_b_id)
    if kin_reason:
        raise ValueError(f"FAMILY-02 prohibits union between close known kin: {kin_reason}")
    existing_union = conn.execute(
        "SELECT id FROM household_unions WHERE status='active' AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)) ORDER BY id LIMIT 1",
        (actor_a_id, actor_b_id, actor_b_id, actor_a_id),
    ).fetchone()
    if existing_union:
        return int(existing_union[0])
    # A person cannot enter two simultaneous active unions merely because two proposals were
    # pending when the first was accepted. Re-check the global invariant at mutation time.
    conflicting = conn.execute(
        "SELECT id,actor_a_id,actor_b_id FROM household_unions WHERE status='active' AND "
        "(actor_a_id IN (?,?) OR actor_b_id IN (?,?)) ORDER BY id LIMIT 1",
        (actor_a_id, actor_b_id, actor_a_id, actor_b_id),
    ).fetchone()
    if conflicting:
        raise ValueError("one or both actors are already in an active union")
    family_plan = dict(family_plan or {})
    if family_plan.get("auto_children"):
        resolved_parent = resolved_biological_birth_parent(conn, actor_a_id, actor_b_id)
        if resolved_parent is None:
            raise ValueError("FAMILY-02 auto-children require a resolved female/male reproductive pair")
        planned_parent = family_plan.get("birth_parent_actor_id")
        if planned_parent is not None and int(planned_parent) != int(resolved_parent):
            raise ValueError("FAMILY-02 family plan names an invalid biological birth parent")
        family_plan["birth_parent_actor_id"] = int(resolved_parent)
        family_plan.pop("birth_parent_unresolved", None)
    if create_new_household_name:
        location = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_a_id,)).fetchone()
        household_id = create_household(
            conn, create_new_household_name, head_actor_id=actor_a_id,
            location_id=int(location[0]) if location and location[0] else None,
            metadata={
                "authority": "ENGINE_DERIVED_HOUSEHOLD_FORMATION",
                "economic_resolution": "STRUCTURAL_ONLY",
                "economic_state": "NOT_SEPARATELY_QUANTIFIED",
                "reason": "Household existence is known; private finances are not inferred from absent source data.",
            },
        )
        add_household_member(conn, household_id, actor_b_id, role="partner", authority=80, dependency=0)
        _record_life_event(conn, "household_formation", f"{create_new_household_name} was formed.", actor_id=actor_a_id,
                           related_actor_id=actor_b_id, household_id=household_id)
    if household_id is not None:
        old_households: set[int] = set()
        for aid in (actor_a_id, actor_b_id):
            for r in conn.execute("SELECT household_id FROM household_members WHERE actor_id=? AND status='active' AND household_id<>?", (aid, household_id)).fetchall():
                old_households.add(int(r[0]))
            _close_other_household_memberships(conn, aid, household_id, day)
        for old_hid in old_households:
            _repair_household_head(conn, old_hid, day)
    cur = conn.execute(
        """INSERT INTO household_unions(actor_a_id,actor_b_id,household_id,union_kind,status,started_day,family_plan_json)
           VALUES (?,?,?,?, 'active', ?,?)""",
        (actor_a_id, actor_b_id, household_id, union_kind, day, json.dumps(family_plan, sort_keys=True)),
    )
    add_kinship(conn, actor_a_id, actor_b_id, "spouse", reciprocal_kind="spouse")
    if household_id is not None:
        for aid, role in ((actor_a_id, "head"), (actor_b_id, "partner")):
            conn.execute(
                """INSERT INTO household_members(household_id,actor_id,role,authority,dependency,joined_day,status)
                   VALUES (?,?,?,?,?,?, 'active')
                   ON CONFLICT(household_id,actor_id) DO UPDATE SET role=CASE WHEN household_members.role='head' THEN 'head' ELSE excluded.role END,
                     status='active',left_day=NULL""",
                (household_id, aid, role, 80 if role == "partner" else 100, 0, day),
            )
            conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (household_id, aid))
    _record_life_event(conn, "union", f"{_name(conn, actor_a_id)} and {_name(conn, actor_b_id)} entered a {union_kind}.",
                       actor_id=actor_a_id, related_actor_id=actor_b_id, household_id=household_id)
    return int(cur.lastrowid)


def end_union(conn: sqlite3.Connection, union_id: int, *, status: str = "dissolved", reason: str | None = None) -> None:
    if status not in {"separated", "dissolved"}:
        raise ValueError("Union end status must be separated or dissolved")
    day = _day(conn)
    row = conn.execute("SELECT * FROM household_unions WHERE id=? AND status='active'", (union_id,)).fetchone()
    if not row:
        raise ValueError("Unknown or inactive household union")
    a, b = int(row["actor_a_id"]), int(row["actor_b_id"])
    conn.execute("UPDATE household_unions SET status=?,ended_day=? WHERE id=?", (status, day, union_id))
    conn.execute(
        "UPDATE kinship_links SET legal_status='former',ended_day=? WHERE kin_kind='spouse' AND ended_day IS NULL AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))",
        (day, a, b, b, a),
    )
    _record_life_event(conn, "separation" if status == "separated" else "dissolution",
                       f"{_name(conn, a)} and {_name(conn, b)} ended their {row['union_kind']}." + (f" {reason}" if reason else ""),
                       actor_id=a, related_actor_id=b, household_id=row["household_id"], day=day)


def update_family_plan(conn: sqlite3.Connection, union_id: int, *, desired_children: int | None = None,
                       auto_children: bool | None = None, birth_parent_actor_id: int | None = None,
                       earliest_next_child_day: int | None = None, spacing_days: int | None = None) -> None:
    row = conn.execute("SELECT family_plan_json FROM household_unions WHERE id=?", (union_id,)).fetchone()
    if not row:
        raise ValueError("Unknown household union")
    urow = conn.execute("SELECT actor_a_id,actor_b_id FROM household_unions WHERE id=?", (union_id,)).fetchone()
    plan = json.loads(row[0] or "{}")
    resolved_parent = resolved_biological_birth_parent(conn, int(urow[0]), int(urow[1])) if urow else None
    if birth_parent_actor_id is not None and (resolved_parent is None or int(birth_parent_actor_id) != int(resolved_parent)):
        raise ValueError("FAMILY-02 family plan names an invalid biological birth parent")
    if auto_children is True and resolved_parent is None:
        raise ValueError("FAMILY-02 auto-children require a resolved female/male reproductive pair")
    if auto_children is True and birth_parent_actor_id is None:
        birth_parent_actor_id = int(resolved_parent)
    for key, val in {
        "desired_children": desired_children, "auto_children": auto_children,
        "birth_parent_actor_id": birth_parent_actor_id, "earliest_next_child_day": earliest_next_child_day,
        "spacing_days": spacing_days,
    }.items():
        if val is not None:
            plan[key] = val
    conn.execute("UPDATE household_unions SET family_plan_json=? WHERE id=?", (json.dumps(plan, sort_keys=True), union_id))


def _existing_children(conn: sqlite3.Connection, actor_a: int, actor_b: int) -> list[int]:
    a = {int(r[0]) for r in conn.execute("SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind='parent' AND legal_status='recognized'", (actor_a,)).fetchall()}
    b = {int(r[0]) for r in conn.execute("SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind='parent' AND legal_status='recognized'", (actor_b,)).fetchall()}
    return sorted(a & b)


def _children_of_either_parent(conn: sqlite3.Connection, actor_a: int, actor_b: int) -> list[int]:
    out: set[int] = set()
    for parent in (actor_a, actor_b):
        out.update(int(r[0]) for r in conn.execute(
            "SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind='parent' AND legal_status='recognized' AND ended_day IS NULL",
            (parent,),
        ).fetchall())
    return sorted(out)


def _family_name(name: str) -> str | None:
    tokens = [t for t in str(name or "").split() if not t.isdigit()]
    return tokens[-1] if len(tokens) >= 2 and not tokens[0].startswith("[") else None


def _newborn_name(conn: sqlite3.Connection, father: int, mother: int, sex: str, key: str) -> str:
    """A newborn's given name of their sex and the father's family name (else the mother's), unique in the world."""
    from .demographic_sex import FEMALE_GIVEN_NAMES, MALE_GIVEN_NAMES
    import hashlib
    names = {int(r[0]): str(r[1]) for r in conn.execute("SELECT id,name FROM actors WHERE id IN (?,?)", (father, mother))}
    family = _family_name(names.get(father, "")) or _family_name(names.get(mother, ""))
    from .demographic_sex import package_given_pool
    pool = package_given_pool(conn, sex, family) or sorted(FEMALE_GIVEN_NAMES if sex == "female" else MALE_GIVEN_NAMES)
    start = int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(pool)
    for given in pool[start:] + pool[:start]:
        name = f"{given} {family}" if family else given
        if not conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
            return name
    from .person_ecology import _free_name  # every given name of the family is taken: tell them apart, never by a number
    return _free_name(conn, pool[start], family or "", sex, int(hashlib.sha256(key.encode()).hexdigest()[:6], 16)).strip()


def register_birth(conn: sqlite3.Connection, union_id: int, *, child_name: str | None = None,
                   demographic_sex: str | None = None, day: int | None = None) -> int:
    row = conn.execute("SELECT * FROM household_unions WHERE id=? AND status='active'", (union_id,)).fetchone()
    if not row:
        raise ValueError("Birth requires an active household union")
    birth_day = _day(conn) if day is None else int(day)
    if birth_day != _day(conn):
        raise ValueError("Birth registration must occur on the current story day; use historical crystallization for retroactive births")
    if birth_day < int(row["started_day"]):
        raise ValueError("Birth cannot predate the union")
    a, b = int(row["actor_a_id"]), int(row["actor_b_id"])
    if not _actor_is_living(conn, a) or not _actor_is_living(conn, b):
        raise ValueError("Birth requires both union actors to be living")
    birth_parent = resolved_biological_birth_parent(conn, a, b)
    if birth_parent is None:
        raise ValueError("FAMILY-02 birth requires a resolved female/male reproductive pair")
    plan = json.loads(row["family_plan_json"] or "{}")
    planned_parent = plan.get("birth_parent_actor_id")
    if planned_parent is not None and int(planned_parent) != int(birth_parent):
        raise ValueError("FAMILY-02 birth parent conflicts with resolved demographic sex")
    hid = row["household_id"]
    existing = _existing_children(conn, a, b)
    siblings = _children_of_either_parent(conn, a, b)
    world_seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    birth_key = f"birth:{world_seed}:{union_id}:{birth_day}:{len(existing)+1}"
    if demographic_sex is None:
        # FAMILY-02: a newborn is never left unresolved; seeded 50/50 like the background population.
        from .demographic_sex import seeded_sex
        demographic_sex = seeded_sex(birth_key)
    if child_name is None:
        child_name = _newborn_name(conn, a if int(birth_parent) == b else b, int(birth_parent), demographic_sex, birth_key)
    loc = conn.execute("SELECT location_id FROM households WHERE id=?", (hid,)).fetchone() if hid else None
    location_id = int(loc[0]) if loc and loc[0] is not None else None
    cur = conn.execute(
        "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,is_demo) VALUES (?,'character','child',?,?, 'active',0)",
        (child_name, location_id, location_id),
    )
    child = int(cur.lastrowid)
    set_life_profile(conn, child, birth_day=birth_day, demographic_sex=demographic_sex,
                     origin_household_id=hid, current_household_id=hid, family_formation_eligible=False,
                     metadata={"generated_by":"v0.19 life-course"})
    if hid:
        from .civilian import add_household_member
        add_household_member(conn, hid, child, role="child", authority=0, dependency=100)
        head = conn.execute("SELECT head_actor_id FROM households WHERE id=?", (hid,)).fetchone()
        sponsor = int(head[0]) if head and head[0] is not None and _actor_is_living(conn, int(head[0])) else a
        conn.execute(
            """INSERT INTO household_dependencies(household_id,dependent_actor_id,sponsor_actor_id,dependency_kind,support_level,status,started_day)
               VALUES (?,?,?,?,100,'active',?)""",
            (hid, child, sponsor, "child", birth_day),
        )
    for parent in (a, b):
        add_kinship(conn, parent, child, "parent", reciprocal_kind="child")
    # A newborn's Core is hereditary; a Veinborn child stays unstaged until someone trains them.
    from .cultivation import assign_birth_core
    assign_birth_core(conn, child, [a, b], location_id)
    for sib in siblings:
        if sib != child:
            add_kinship(conn, child, sib, "sibling", reciprocal_kind="sibling")
    _record_life_event(conn, "birth", f"{child_name} was born into the household.", actor_id=child,
                       related_actor_id=a, household_id=hid, location_id=location_id, day=birth_day)
    return child


def create_guardianship(conn: sqlite3.Connection, guardian_actor_id: int, ward_actor_id: int, *,
                        household_id: int | None = None, authority: float = 70, support_level: float = 70) -> int:
    day = _day(conn)
    if guardian_actor_id == ward_actor_id:
        raise ValueError("Guardian and ward must be distinct actors")
    if not _actor_is_living(conn, guardian_actor_id) or not _actor_is_living(conn, ward_actor_id):
        raise ValueError("Guardianship requires living actors")
    existing = conn.execute(
        "SELECT id FROM guardianships WHERE guardian_actor_id=? AND ward_actor_id=? AND status='active' ORDER BY id LIMIT 1",
        (guardian_actor_id, ward_actor_id),
    ).fetchone()
    if existing:
        return int(existing[0])
    cur = conn.execute(
        """INSERT INTO guardianships(guardian_actor_id,ward_actor_id,household_id,authority,support_level,status,started_day)
           VALUES (?,?,?,?,?,'active',?)""",
        (guardian_actor_id, ward_actor_id, household_id, authority, support_level, day),
    )
    add_kinship(conn, guardian_actor_id, ward_actor_id, "guardian", reciprocal_kind="ward")
    if household_id:
        from .civilian import add_household_member
        old_households = [int(r[0]) for r in conn.execute(
            "SELECT household_id FROM household_members WHERE actor_id=? AND status='active' AND household_id<>?",
            (ward_actor_id, household_id),
        ).fetchall()]
        _close_other_household_memberships(conn, ward_actor_id, household_id, day)
        for old_hid in old_households:
            _repair_household_head(conn, old_hid, day)
        conn.execute(
            "UPDATE household_dependencies SET status='ended',ended_day=? WHERE dependent_actor_id=? AND household_id<>? AND status='active'",
            (day, ward_actor_id, household_id),
        )
        add_household_member(conn, household_id, ward_actor_id, role="ward", authority=0, dependency=90)
        conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (household_id, ward_actor_id))
        conn.execute("""INSERT INTO household_dependencies(household_id,dependent_actor_id,sponsor_actor_id,dependency_kind,support_level,status,started_day)
                        VALUES (?,?,?,?,?,'active',?)""",
                     (household_id, ward_actor_id, guardian_actor_id, "ward", support_level, day))
    _record_life_event(conn, "guardianship", f"{_name(conn, guardian_actor_id)} became guardian of {_name(conn, ward_actor_id)}.",
                       actor_id=guardian_actor_id, related_actor_id=ward_actor_id, household_id=household_id)
    return int(cur.lastrowid)


def end_guardianship(conn: sqlite3.Connection, guardianship_id: int, *, reason: str | None = None) -> None:
    day = _day(conn)
    row = conn.execute("SELECT * FROM guardianships WHERE id=? AND status='active'", (guardianship_id,)).fetchone()
    if not row:
        raise ValueError("Unknown or inactive guardianship")
    g, w = int(row["guardian_actor_id"]), int(row["ward_actor_id"])
    conn.execute("UPDATE guardianships SET status='ended',ended_day=? WHERE id=?", (day, guardianship_id))
    conn.execute(
        "UPDATE kinship_links SET legal_status='former',ended_day=? WHERE ended_day IS NULL AND ((actor_a_id=? AND actor_b_id=? AND kin_kind='guardian') OR (actor_a_id=? AND actor_b_id=? AND kin_kind='ward'))",
        (day, g, w, w, g),
    )
    if row["household_id"] is not None:
        conn.execute(
            "UPDATE household_dependencies SET status='ended',ended_day=? WHERE household_id=? AND dependent_actor_id=? AND sponsor_actor_id=? AND dependency_kind='ward' AND status='active'",
            (day, row["household_id"], w, g),
        )
    _record_life_event(conn, "guardianship", f"Guardianship of {_name(conn, w)} by {_name(conn, g)} ended." + (f" {reason}" if reason else ""),
                       actor_id=g, related_actor_id=w, household_id=row["household_id"], day=day)


def split_household(conn: sqlite3.Connection, source_household_id: int, new_name: str, moving_actor_ids: list[int], *,
                    new_head_actor_id: int, destination_location_id: int | None = None,
                    wealth_share: float = 0.0, liquidity_share: float = 0.0) -> int:
    from .civilian import create_household, add_household_member
    src = conn.execute("SELECT * FROM households WHERE id=?", (source_household_id,)).fetchone()
    if not src:
        raise ValueError("Unknown source household")
    if not 0.0 <= wealth_share <= 1.0 or not 0.0 <= liquidity_share <= 1.0:
        raise ValueError("Household split shares must be between 0 and 1")
    moving = sorted(set(moving_actor_ids + [new_head_actor_id]))
    for aid in moving:
        if not _active_household_member(conn, source_household_id, aid):
            raise ValueError(f"Actor {aid} is not an active member of the source household")
    location_id = destination_location_id if destination_location_id is not None else src["location_id"]
    wealth = float(src["wealth"]) * wealth_share
    liquidity = float(src["liquidity"]) * liquidity_share
    hid = create_household(conn, new_name, head_actor_id=new_head_actor_id, location_id=location_id,
                           wealth=wealth, liquidity=liquidity, cohesion=float(src["cohesion"]), hospitality=float(src["hospitality"]))
    conn.execute("UPDATE households SET wealth=wealth-?,liquidity=liquidity-?,updated_day=? WHERE id=?",
                 (wealth, liquidity, _day(conn), source_household_id))
    for aid in moving:
        old = _active_household_member(conn, source_household_id, aid)
        conn.execute("UPDATE household_members SET status='former',left_day=? WHERE household_id=? AND actor_id=? AND status='active'", (_day(conn), source_household_id, aid))
        if aid != new_head_actor_id:
            add_household_member(conn, hid, aid, role=str(old["role"]) if old else "member",
                                 authority=float(old["authority"]) if old else 20, dependency=float(old["dependency"]) if old else 20)
        conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (hid, aid))
        if location_id is not None:
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (location_id, aid))
        conn.execute("UPDATE household_dependencies SET household_id=? WHERE household_id=? AND dependent_actor_id=? AND status='active'",
                     (hid, source_household_id, aid))
        conn.execute("UPDATE guardianships SET household_id=? WHERE household_id=? AND ward_actor_id=? AND status='active'",
                     (hid, source_household_id, aid))
        conn.execute("UPDATE household_service_terms SET household_id=? WHERE household_id=? AND actor_id=? AND status='active'",
                     (hid, source_household_id, aid))
    # A union belongs to the new household only when both partners moved together. If only one moved,
    # it no longer truthfully belongs to the old shared household.
    for u in conn.execute("SELECT id,actor_a_id,actor_b_id FROM household_unions WHERE household_id=? AND status='active'", (source_household_id,)).fetchall():
        am, bm = int(u["actor_a_id"]) in moving, int(u["actor_b_id"]) in moving
        if am and bm:
            conn.execute("UPDATE household_unions SET household_id=? WHERE id=?", (hid, u["id"]))
        elif am or bm:
            conn.execute("UPDATE household_unions SET household_id=NULL WHERE id=?", (u["id"],))
    if src["head_actor_id"] is not None and int(src["head_actor_id"]) in moving:
        _repair_household_head(conn, source_household_id, _day(conn))
    else:
        remaining = conn.execute("SELECT COUNT(*) FROM household_members WHERE household_id=? AND status='active'", (source_household_id,)).fetchone()[0]
        if int(remaining) == 0:
            _repair_household_head(conn, source_household_id, _day(conn))
    _record_life_event(conn, "household_split", f"{new_name} separated from {src['name']}.", actor_id=new_head_actor_id,
                       household_id=hid, location_id=location_id, metadata={"source_household_id": source_household_id})
    return hid


def add_service_term(conn: sqlite3.Connection, household_id: int, actor_id: int, service_role: str, *,
                     review_in_days: int = 365, loyalty: float = 50, satisfaction: float = 50,
                     renewal_bias: float = 50) -> int:
    from .civilian import add_household_member
    day = _day(conn)
    hh = conn.execute("SELECT status FROM households WHERE id=?", (household_id,)).fetchone()
    if not hh or str(hh[0]) in {"dissolved", "historical"}:
        raise ValueError("Service requires an active household")
    if not _actor_is_living(conn, actor_id):
        raise ValueError("Service requires a living actor")
    existing = conn.execute(
        "SELECT id FROM household_service_terms WHERE household_id=? AND actor_id=? AND service_role=? AND status='active' ORDER BY id LIMIT 1",
        (household_id, actor_id, service_role),
    ).fetchone()
    if existing:
        return int(existing[0])
    cur = conn.execute(
        """INSERT INTO household_service_terms(household_id,actor_id,service_role,start_day,review_day,loyalty,satisfaction,renewal_bias,status)
           VALUES (?,?,?,?,?,?,?,?,'active')""",
        (household_id, actor_id, service_role, day, day + max(1, review_in_days), loyalty, satisfaction, renewal_bias),
    )
    if not _active_household_member(conn, household_id, actor_id):
        add_household_member(conn, household_id, actor_id, role=service_role, authority=15 if service_role not in ('steward','retainer') else 35,
                             dependency=20)
    _record_life_event(conn, "service_change", f"{_name(conn, actor_id)} entered {service_role} service in household #{household_id}.",
                       actor_id=actor_id, household_id=household_id, day=day)
    return int(cur.lastrowid)


def schedule_household_migration(conn: sqlite3.Connection, household_id: int, destination_location_id: int,
                                 planned_day: int, *, reason: str | None = None) -> int:
    day = _day(conn)
    hh = conn.execute("SELECT location_id,status FROM households WHERE id=?", (household_id,)).fetchone()
    if not hh or str(hh["status"]) in {"dissolved", "historical"}:
        raise ValueError("Migration requires an active household")
    if int(planned_day) < day:
        raise ValueError("Migration cannot be scheduled in the past")
    if hh["location_id"] is not None and int(hh["location_id"]) == int(destination_location_id):
        raise ValueError("Migration destination is already the household location")
    if not conn.execute("SELECT 1 FROM locations WHERE id=?", (destination_location_id,)).fetchone():
        raise ValueError("Unknown migration destination")
    # A newly scheduled move supersedes any earlier unresolved plan for the same household.
    if conn.execute("SELECT 1 FROM household_migration_plans WHERE household_id=? AND status='in_transit'", (household_id,)).fetchone():
        raise ValueError("Household already has a migration in transit")
    conn.execute("UPDATE household_migration_plans SET status='cancelled' WHERE household_id=? AND status='planned'", (household_id,))
    cur = conn.execute(
        """INSERT INTO household_migration_plans(household_id,destination_location_id,planned_day,reason,status,created_day)
           VALUES (?,?,?,?,'planned',?)""",
        (household_id, destination_location_id, planned_day, reason, day),
    )
    return int(cur.lastrowid)


def set_demographic_cohort(conn: sqlite3.Connection, location_id: int, cohort_key: str, age_band: str, population: float, *,
                           annual_birth_pressure: float = 0, annual_migration_rate: float = 0,
                           metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    conn.execute(
        """INSERT INTO demographic_cohorts(location_id,cohort_key,age_band,population,annual_birth_pressure,annual_migration_rate,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(location_id,cohort_key,age_band) DO UPDATE SET population=excluded.population,
             annual_birth_pressure=excluded.annual_birth_pressure,annual_migration_rate=excluded.annual_migration_rate,
             last_review_day=excluded.last_review_day,metadata_json=excluded.metadata_json""",
        (location_id, cohort_key, age_band, population, annual_birth_pressure, annual_migration_rate, day,
         json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(conn.execute("SELECT id FROM demographic_cohorts WHERE location_id=? AND cohort_key=? AND age_band=?",
                            (location_id, cohort_key, age_band)).fetchone()[0])


def mark_actor_deceased(conn: sqlite3.Connection, actor_id: int, *, reason: str = "deceased",
                        event_logger: Callable[..., int] | None = None) -> None:
    day = _day(conn)
    prof = conn.execute("SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    hid = int(prof[0]) if prof and prof[0] is not None else None
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    location_id = int(loc[0]) if loc and loc[0] is not None else None
    conn.execute("UPDATE actors SET status='deceased' WHERE id=?", (actor_id,))
    conn.execute("UPDATE actor_life_profiles SET life_status='deceased',last_review_day=? WHERE actor_id=?", (day, actor_id))
    from . import history  # R1: a death that touches real history is a divergence
    history.note_actor_death(conn, actor_id, day, reason)
    # A dead character has no future autonomous review. Historical resolution metadata is
    # retained elsewhere, but the live scheduler row must disappear immediately.
    conn.execute("DELETE FROM simulation_profiles WHERE actor_id=?", (actor_id,))
    conn.execute("UPDATE household_members SET status='deceased',left_day=? WHERE actor_id=? AND status='active'", (day, actor_id))
    unions = conn.execute("SELECT id,actor_a_id,actor_b_id FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?)", (actor_id, actor_id)).fetchall()
    for u in unions:
        other = int(u["actor_b_id"] if int(u["actor_a_id"]) == actor_id else u["actor_a_id"])
        conn.execute("UPDATE household_unions SET status='widowed',ended_day=? WHERE id=?", (day, u["id"]))
        conn.execute("UPDATE kinship_links SET legal_status='former',ended_day=? WHERE kin_kind='spouse' AND actor_a_id IN (?,?) AND actor_b_id IN (?,?) AND legal_status='recognized'",
                     (day, actor_id, other, actor_id, other))
    conn.execute("UPDATE household_service_terms SET status='former',end_day=? WHERE actor_id=? AND status='active'", (day, actor_id))
    guardian_rows = conn.execute("SELECT id,guardian_actor_id,ward_actor_id FROM guardianships WHERE status='active' AND (guardian_actor_id=? OR ward_actor_id=?)", (actor_id, actor_id)).fetchall()
    for g in guardian_rows:
        conn.execute("UPDATE guardianships SET status='ended',ended_day=? WHERE id=?", (day, g["id"]))
        ga, wa = int(g["guardian_actor_id"]), int(g["ward_actor_id"])
        conn.execute("UPDATE kinship_links SET legal_status='former',ended_day=? WHERE ended_day IS NULL AND ((actor_a_id=? AND actor_b_id=? AND kin_kind='guardian') OR (actor_a_id=? AND actor_b_id=? AND kin_kind='ward'))",
                     (day, ga, wa, wa, ga))
        if wa == actor_id:
            conn.execute("UPDATE household_dependencies SET status='ended',ended_day=? WHERE dependent_actor_id=? AND dependency_kind='ward' AND status='active'", (day, wa))
        else:
            conn.execute("UPDATE household_dependencies SET sponsor_actor_id=NULL WHERE dependent_actor_id=? AND sponsor_actor_id=? AND dependency_kind='ward' AND status='active'", (wa, ga))
    conn.execute("UPDATE household_dependencies SET sponsor_actor_id=NULL WHERE sponsor_actor_id=? AND status='active'", (actor_id,))
    conn.execute("UPDATE household_dependencies SET status='ended',ended_day=? WHERE dependent_actor_id=? AND status='active'", (day, actor_id))
    # Health treatment cannot continue after death, regardless of which subsystem recorded the death.
    try:
        conn.execute("UPDATE medical_treatments SET status='stopped',end_day=COALESCE(end_day,?) WHERE actor_id=? AND status='active'", (day, actor_id))
        conn.execute("UPDATE medical_treatments SET status='stopped',end_day=COALESCE(end_day,?) WHERE provider_actor_id=? AND status='active'", (day, actor_id))
        conn.execute("UPDATE actor_health_profiles SET last_review_day=?,next_review_day=? WHERE actor_id=?", (day, day, actor_id))
    except sqlite3.OperationalError:
        pass
    _record_life_event(conn, "death", f"{_name(conn, actor_id)} died: {reason}.", actor_id=actor_id, household_id=hid, location_id=location_id)
    if event_logger:
        event_logger(day=day, event_type="life:death", title=f"Death: {_name(conn, actor_id)}", summary=reason,
                     severity=2, source_actor_id=actor_id, target_actor_ids=(), location_id=location_id)
    # Leadership death must become institutional history. This hook opens real authority
    # vacancies/succession cases but never invents a replacement person. It runs after the
    # death is fully recorded, and a tolerated failure rolls back its partial writes.
    conn.execute("SAVEPOINT actor_death_authority")
    try:
        from .succession import handle_actor_death_authority
        handle_actor_death_authority(conn, actor_id, source_kind='actor_death')
    except (sqlite3.OperationalError, ImportError):
        conn.execute("ROLLBACK TO SAVEPOINT actor_death_authority")
    finally:
        conn.execute("RELEASE SAVEPOINT actor_death_authority")



def _age_years(profile: sqlite3.Row, day: int) -> float | None:
    if profile['birth_day'] is None:
        return None
    return max(0.0,(day-int(profile['birth_day']))/365.0)


def _family_eligible(profile: sqlite3.Row, day: int) -> bool:
    """Social eligibility for courtship/household formation, not a fertility guarantee."""
    if str(profile['life_status'])!='living' or str(profile['life_stage'])!='adult':
        return False
    age=_age_years(profile,day)
    if age is None:
        return bool(profile['family_formation_eligible'])
    return 18.0 <= age <= 70.0


def _known_close_kin(conn: sqlite3.Connection, a: int, b: int) -> bool:
    return conn.execute("""SELECT 1 FROM kinship_links WHERE ended_day IS NULL AND
                           ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))
                           AND kin_kind NOT IN ('spouse') LIMIT 1""",(a,b,b,a)).fetchone() is not None


def _has_active_union(conn: sqlite3.Connection, actor_id: int) -> bool:
    return conn.execute("SELECT 1 FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?) LIMIT 1",(actor_id,actor_id)).fetchone() is not None


def _parents(conn: sqlite3.Connection, actor_id: int) -> set[int]:
    return {int(r[0]) for r in conn.execute(
        # Disputed/informal and adoptive parentage still bar a union; only ended (former) links do not.
        "SELECT actor_a_id FROM kinship_links WHERE actor_b_id=? AND kin_kind IN ('parent','adoptive_parent') AND legal_status<>'former' AND ended_day IS NULL",
        (actor_id,),
    ).fetchall()}


def prohibited_union_kinship_reason(conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int) -> str | None:
    """Return a hard FAMILY-02 kinship prohibition, without guessing culture-specific cousin rules."""
    if actor_a_id == actor_b_id:
        return "same_actor"
    direct = conn.execute(
        """SELECT kin_kind FROM kinship_links WHERE ended_day IS NULL AND legal_status<>'former' AND
           ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)) AND kin_kind<>'spouse'
           ORDER BY id LIMIT 1""",
        (actor_a_id, actor_b_id, actor_b_id, actor_a_id),
    ).fetchone()
    if direct:
        return f"direct_{direct[0]}"
    pa, pb = _parents(conn, actor_a_id), _parents(conn, actor_b_id)
    if pa & pb:
        return "shared_parent"
    # Grandparent/grandchild.
    grandparents_a = {gp for p in pa for gp in _parents(conn, p)}
    grandparents_b = {gp for p in pb for gp in _parents(conn, p)}
    if actor_a_id in grandparents_b or actor_b_id in grandparents_a:
        return "grandparent_descendant"
    # Aunt/uncle with niece/nephew: one actor shares a parent with the other's parent.
    if any(_parents(conn, p) & pa for p in pb) or any(_parents(conn, p) & pb for p in pa):
        return "aunt_uncle_niece_nephew"
    return None


def resolved_biological_birth_parent(conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int) -> int | None:
    """Return the explicit female birth parent only for a resolved female/male reproductive pair."""
    rows = {}
    for aid in (actor_a_id, actor_b_id):
        row = conn.execute("SELECT demographic_sex,life_status FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
        if not row or str(row['life_status']) != 'living':
            return None
        sex = str(row['demographic_sex'] or 'unspecified')
        if sex not in {'female','male'}:
            return None
        rows[aid] = sex
    females = [aid for aid, sex in rows.items() if sex == 'female']
    males = [aid for aid, sex in rows.items() if sex == 'male']
    return females[0] if len(females) == 1 and len(males) == 1 else None


def _contact_rng(conn: sqlite3.Connection, a: int, b: int, context_id: int, salt: int=0) -> random.Random:
    seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed*1000003 + min(a,b)*1709 + max(a,b)*9151 + int(context_id)*271 + salt)


def _resolve_social_contacts(conn: sqlite3.Connection, day: int) -> int:
    """Grow sparse courtship-capable relationships only from sustained shared context.

    This is not matchmaking. Most eligible pairs never become a contact, and contact only creates
    familiarity; the existing interaction/consent system still owns any later union proposal.
    """
    changed=0
    # Existing contact familiarity grows slowly and can also cool if one party is no longer eligible.
    due=conn.execute("SELECT * FROM social_contact_links WHERE status='active' AND next_review_day<=? ORDER BY id",(day,)).fetchall()
    for link in due:
        a,b=int(link['actor_a_id']),int(link['actor_b_id'])
        pa=conn.execute("SELECT * FROM actor_life_profiles WHERE actor_id=?",(a,)).fetchone(); pb=conn.execute("SELECT * FROM actor_life_profiles WHERE actor_id=?",(b,)).fetchone()
        if not pa or not pb or not _family_eligible(pa,day) or not _family_eligible(pb,day) or _has_active_union(conn,a) or _has_active_union(conn,b):
            conn.execute("UPDATE social_contact_links SET status='dormant',last_review_day=?,next_review_day=? WHERE id=?",(day,day+365,int(link['id'])))
            continue
        affinity=float(link['affinity'])
        # Sustained shared context is reciprocal contact, but later reactions can diverge.
        delta=max(-1.5,min(5.0,(affinity-42.0)/18.0))
        adjust_relationship_pair(
            conn, a, b, day,
            symmetric={"trust_delta": delta, "stance_delta": max(-1.0,delta*0.75), "familiarity_delta": 3.0},
        )
        conn.execute("UPDATE social_contact_links SET last_review_day=?,next_review_day=? WHERE id=?",(day,day+180,int(link['id'])))
        changed+=1

    # At most one new institutional contact per single eligible actor per annual review window.
    # S1: looking for new contacts is a weekly pass for everyone (it was daily and the costliest scan in the household layer).
    from . import tiers
    if tiers.batching(conn):
        last = conn.execute("SELECT value FROM runtime_flags WHERE key='social_scan_day'").fetchone()
        if last is not None and day - int(last[0]) < tiers.BATCH_DAYS:
            return changed
        conn.execute("INSERT OR REPLACE INTO runtime_flags(key,value,updated_at) VALUES ('social_scan_day',?,CURRENT_TIMESTAMP)", (str(int(day)),))
    from .world_package import org_rules, package_for
    scan_kinds=[k for k,v in (org_rules(package_for(conn)).get("kinds") or {}).items() if v.get("courtship_scan")]
    candidates=conn.execute("""SELECT lp.actor_id,lp.birth_day,im.institution_actor_id,a.current_location_id
        FROM actor_life_profiles lp JOIN actors a ON a.id=lp.actor_id
        JOIN institution_memberships im ON im.member_actor_id=lp.actor_id AND im.status='active'
        WHERE lp.life_status='living' AND lp.life_stage='adult' AND lp.family_formation_eligible=1
          AND a.status='active' AND a.actor_type='character'
          AND NOT EXISTS (SELECT 1 FROM household_unions u WHERE u.status='active' AND (u.actor_a_id=lp.actor_id OR u.actor_b_id=lp.actor_id))
          -- An organisation's hundreds of members are not a courtship pool: this pairwise scan is quadratic per institution
          -- and ran daily (28 s a day at the Saint Jude opening). Members of a kind whose courtship_scan is false (orgs.json)
          -- meet people through their own lives, not here. (With no scanning kind at all every seat holder is excluded: an empty
          -- `NOT IN (NULL)` list excluded no one, and the scan ran quadratic over every outfit.)
          AND NOT EXISTS (SELECT 1 FROM org_seats o LEFT JOIN org_profiles op ON op.org_actor_id=o.org_actor_id
                          WHERE o.actor_id=lp.actor_id AND (op.org_kind IS NULL OR op.org_kind NOT IN (%s)))
        ORDER BY im.institution_actor_id,lp.actor_id""" % (",".join("?"*len(scan_kinds)) if scan_kinds else "''"),tuple(scan_kinds)).fetchall()
    by_inst={}
    for r in candidates: by_inst.setdefault(int(r['institution_actor_id']),[]).append(r)
    already=set()
    for inst,rows in by_inst.items():
        inst_loc_row=conn.execute("SELECT current_location_id FROM actors WHERE id=?",(inst,)).fetchone()
        inst_loc=int(inst_loc_row[0]) if inst_loc_row and inst_loc_row[0] is not None else None
        if inst_loc is None:
            continue
        for i,r in enumerate(rows):
            a=int(r['actor_id'])
            if a in already: continue
            if conn.execute("SELECT 1 FROM social_contact_links WHERE status='active' AND (actor_a_id=? OR actor_b_id=?) AND started_day>? LIMIT 1",(a,a,day-365)).fetchone(): continue
            agea=(day-int(r['birth_day']))/365.0 if r['birth_day'] is not None else None
            options=[]
            for q in rows[i+1:]:
                b=int(q['actor_id'])
                if b in already or _known_close_kin(conn,a,b): continue
                if conn.execute("SELECT 1 FROM social_contact_links WHERE status='active' AND (actor_a_id=? OR actor_b_id=?) AND started_day>? LIMIT 1",(b,b,day-365)).fetchone(): continue
                lo,hi=sorted((a,b))
                purpose=f"social_contact:{inst}:{lo}:{hi}"
                if not actor_is_present_candidate(conn,a,inst_loc,day=day,purpose=purpose+':a'):
                    continue
                if not actor_is_present_candidate(conn,b,inst_loc,day=day,purpose=purpose+':b'):
                    continue
                ageb=(day-int(q['birth_day']))/365.0 if q['birth_day'] is not None else None
                if agea is not None and ageb is not None and abs(agea-ageb)>20: continue
                lo,hi=sorted((a,b))
                if conn.execute("SELECT 1 FROM social_contact_links WHERE actor_a_id=? AND actor_b_id=? AND status IN ('active','dormant') LIMIT 1",(lo,hi)).fetchone(): continue
                rng=_contact_rng(conn,lo,hi,inst)
                affinity=35.0+rng.random()*55.0
                if affinity<58.0: continue
                options.append((affinity,lo,hi))
            if not options: continue
            affinity,lo,hi=max(options,key=lambda x:(x[0],-x[2]))
            conn.execute("""INSERT INTO social_contact_links(actor_a_id,actor_b_id,context_kind,context_id,affinity,started_day,last_review_day,next_review_day,status,metadata_json)
                          VALUES (?,?,'institution',?,?,?, ?,?,'active','{\"authority\":\"ENGINE_DERIVED_SHARED_CONTEXT\"}')""",
                         (lo,hi,inst,affinity,day,day,day+180))
            ensure_reciprocal_relationship(conn, lo, hi, day, stance=8, trust=8, familiarity=10)
            already.update((lo,hi)); changed+=1
    return changed

def _review_profiles(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    count = 0
    from . import tiers
    if tiers.batching(conn):
        # S1: stage and eligibility follow the calendar, so a quiet person is brought up to date weekly, or on the day he crosses a
        # stage boundary; a rising person daily. (Same boundary constants as next_household_life_due_day.)
        rows = conn.execute(
            f"""SELECT * FROM actor_life_profiles WHERE life_status='living' AND last_review_day<?
                AND (last_review_day<=? OR actor_id IN ({tiers.sql_ids(conn, day)})
                     OR (birth_day IS NOT NULL AND ((life_stage='infant' AND birth_day+?<=?) OR (life_stage='child' AND birth_day+?<=?)
                          OR (life_stage='youth' AND birth_day+?<=?) OR (life_stage='adult' AND birth_day+?<=?))))""",
            (day, day - tiers.BATCH_DAYS, 2 * 365, day, 13 * 365, day, 18 * 365, day, 60 * 365, day)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM actor_life_profiles WHERE life_status='living' AND last_review_day<?", (day,)).fetchall()
    for row in rows:
        old = str(row["life_stage"])
        new = _stage_for_age(max(0, day - int(row["birth_day"]))) if row["birth_day"] is not None else old
        eligible=1 if _family_eligible(row,day) and new=='adult' else 0
        # Re-evaluate using the newly derived life stage; unknown-age profiles retain explicit source state.
        if row['birth_day'] is not None:
            age=max(0.0,(day-int(row['birth_day']))/365.0)
            eligible=1 if new=='adult' and 18.0<=age<=70.0 else 0
        conn.execute("UPDATE actor_life_profiles SET life_stage=?,family_formation_eligible=?,last_review_day=? WHERE actor_id=?", (new,eligible,day,row["actor_id"]))
        if old != new and new in ("youth","adult","elder"):
            summary = f"{_name(conn, int(row['actor_id']))} entered the {new} life stage."
            _record_life_event(conn, "coming_of_age" if new == "adult" else "other", summary, actor_id=int(row["actor_id"]),
                               household_id=row["current_household_id"], day=day)
            if event_logger and new == "adult":
                event_logger(day=day, event_type="life:coming_of_age", title=f"Coming of age: {_name(conn, int(row['actor_id']))}",
                             summary=summary, severity=1, source_actor_id=int(row["actor_id"]), target_actor_ids=(), location_id=None)
        count += 1
    return count


def _resolve_planned_births(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    count = 0
    # Only unions whose plan has come due are read (the same expression next_household_life_due_day schedules on): a daily pass over
    # every union parsed every plan to find none due.
    due_unions = conn.execute(
        """SELECT * FROM household_unions WHERE status='active'
           AND COALESCE(json_extract(family_plan_json,'$.auto_children'),0) NOT IN (0,'',0.0)
           AND COALESCE(json_extract(family_plan_json,'$.earliest_next_child_day'),
                        started_day + COALESCE(json_extract(family_plan_json,'$.spacing_days'), 730)) <= ?""", (day,)).fetchall()
    for u in due_unions:
        plan = json.loads(u["family_plan_json"] or "{}")
        if not plan.get("auto_children"):
            continue
        desired = int(plan.get("desired_children", 0))
        # A family aims for the children it wants *living*; a child who died does not count.
        children = [c for c in _existing_children(conn, int(u["actor_a_id"]), int(u["actor_b_id"])) if _actor_is_living(conn, c)]
        if desired <= len(children):
            continue
        due = int(plan.get("earliest_next_child_day", int(u["started_day"]) + int(plan.get("spacing_days", 730))))
        if day < due:
            continue
        a, b = int(u["actor_a_id"]), int(u["actor_b_id"])
        if not _actor_is_living(conn, a) or not _actor_is_living(conn, b):
            continue
        birth_parent = resolved_biological_birth_parent(conn, a, b)
        if birth_parent is None:
            # Unknown demographic sex or a non-female/male reproductive pairing is unresolved,
            # not permission to fabricate a biological birth.
            continue
        planned_parent = plan.get("birth_parent_actor_id")
        if planned_parent is not None and int(planned_parent) != int(birth_parent):
            continue
        p = conn.execute("SELECT family_formation_eligible,life_status,birth_day FROM actor_life_profiles WHERE actor_id=?", (int(birth_parent),)).fetchone()
        if not p or not bool(p[0]) or str(p[1]) != "living":
            continue
        age = _age_years(p, day)
        if age is None or not 18.0 <= age <= 48.0:
            continue
        if planned_parent is None:
            plan["birth_parent_actor_id"] = int(birth_parent)
            plan.pop("birth_parent_unresolved", None)
        # register_birth requires the current story day, which is exactly the due-processing day.
        child = register_birth(conn, int(u["id"]), day=day)
        plan["earliest_next_child_day"] = day + max(365, int(plan.get("spacing_days", 730)))
        conn.execute("UPDATE household_unions SET family_plan_json=? WHERE id=?", (json.dumps(plan, sort_keys=True), u["id"]))
        if event_logger:
            event_logger(day=day, event_type="life:birth", title=f"Birth: {_name(conn, child)}",
                         summary=f"A child was born into household #{u['household_id']}.", severity=1,
                         source_actor_id=child, target_actor_ids=(a, b), location_id=None)
        count += 1
    return count


def _adult_living_actor(conn: sqlite3.Connection, actor_id: int) -> bool:
    row = conn.execute(
        """SELECT a.status,lp.life_status,lp.life_stage FROM actors a
           JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?""",
        (actor_id,),
    ).fetchone()
    return bool(row and str(row['status']) == 'active' and str(row['life_status']) == 'living'
                and str(row['life_stage']) in {'adult','elder'})


def _resolve_guardianship_needs(conn: sqlite3.Connection, day: int) -> int:
    """Repair real dependent-child support gaps using only already-existing household adults.

    This resolver never creates a relative, moves a child to a guessed household, or assigns a remote
    stranger. It acts only when an active child/ward dependency has actually lost its sponsor and a
    living adult already in the same household can carry the legal/support role.
    """
    rows = conn.execute(
        """SELECT d.*,lp.life_stage,lp.life_status
           FROM household_dependencies d
           JOIN actor_life_profiles lp ON lp.actor_id=d.dependent_actor_id
           LEFT JOIN actors sa ON sa.id=d.sponsor_actor_id
           LEFT JOIN actor_life_profiles slp ON slp.actor_id=d.sponsor_actor_id
           WHERE d.status='active' AND d.dependency_kind IN ('child','ward')
             AND lp.life_status='living' AND lp.life_stage IN ('infant','child','youth')
             AND (d.sponsor_actor_id IS NULL OR sa.status IS NULL OR sa.status<>'active' OR slp.life_status<>'living')
           ORDER BY d.id"""
    ).fetchall()
    resolved = 0
    for dep in rows:
        ward = int(dep['dependent_actor_id'])
        hid = int(dep['household_id']) if dep['household_id'] is not None else None
        if hid is None:
            continue

        # A still-valid legal guardian can simply resume sponsorship without creating another relation.
        existing = conn.execute(
            """SELECT g.guardian_actor_id FROM guardianships g
               JOIN household_members hm ON hm.actor_id=g.guardian_actor_id AND hm.household_id=? AND hm.status='active'
               WHERE g.ward_actor_id=? AND g.status='active' ORDER BY g.id LIMIT 1""",
            (hid, ward),
        ).fetchone()
        if existing and _adult_living_actor(conn, int(existing[0])):
            guardian = int(existing[0])
            conn.execute("UPDATE household_dependencies SET sponsor_actor_id=? WHERE id=?", (guardian, int(dep['id'])))
            resolved += 1
            continue

        candidates: list[int] = []
        # Surviving recognized parents/adoptive parents in the same household take priority.
        for r in conn.execute(
            """SELECT k.actor_a_id FROM kinship_links k
               JOIN household_members hm ON hm.actor_id=k.actor_a_id AND hm.household_id=? AND hm.status='active'
               WHERE k.actor_b_id=? AND k.kin_kind IN ('parent','adoptive_parent')
                 AND k.legal_status='recognized' AND k.ended_day IS NULL ORDER BY k.id""",
            (hid, ward),
        ).fetchall():
            candidates.append(int(r[0]))
        # Then adult siblings already sharing the household.
        for r in conn.execute(
            """SELECT k.actor_a_id FROM kinship_links k
               JOIN household_members hm ON hm.actor_id=k.actor_a_id AND hm.household_id=? AND hm.status='active'
               WHERE k.actor_b_id=? AND k.kin_kind='sibling' AND k.legal_status='recognized' AND k.ended_day IS NULL
               ORDER BY k.id""",
            (hid, ward),
        ).fetchall():
            candidates.append(int(r[0]))
        # Household head, then other high-authority adult members, are conservative fallback custodians.
        head = conn.execute("SELECT head_actor_id FROM households WHERE id=? AND status IN ('active','declining')", (hid,)).fetchone()
        if head and head[0] is not None:
            candidates.append(int(head[0]))
        for r in conn.execute(
            """SELECT actor_id FROM household_members WHERE household_id=? AND status='active' AND actor_id<>?
               ORDER BY authority DESC,actor_id""", (hid, ward)
        ).fetchall():
            candidates.append(int(r[0]))

        seen: set[int] = set()
        guardian = None
        for aid in candidates:
            if aid in seen or aid == ward:
                continue
            seen.add(aid)
            if _adult_living_actor(conn, aid):
                guardian = aid
                break
        if guardian is None:
            continue

        create_guardianship(conn, guardian, ward, household_id=None,
                            authority=70, support_level=float(dep['support_level']))
        conn.execute("UPDATE household_dependencies SET sponsor_actor_id=? WHERE id=?", (guardian, int(dep['id'])))
        resolved += 1
    return resolved


def _resolve_service_terms(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    for s in conn.execute("SELECT * FROM household_service_terms WHERE status='active' AND review_day<=?", (day,)).fetchall():
        h = conn.execute("SELECT cohesion,wealth,status FROM households WHERE id=?", (s["household_id"],)).fetchone()
        if not h:
            continue
        score = float(s["loyalty"]) * .3 + float(s["satisfaction"]) * .3 + float(s["renewal_bias"]) * .2 + float(h["cohesion"]) * .2
        household_closed = str(h["status"]) in ("dissolved","historical")
        if str(h["status"]) == "declining":
            score -= 20
        if not household_closed and score >= 45:
            conn.execute("UPDATE household_service_terms SET review_day=? WHERE id=?", (day + 365, s["id"]))
        else:
            conn.execute("UPDATE household_service_terms SET status='former',end_day=? WHERE id=?", (day, s["id"]))
            conn.execute("UPDATE household_members SET status='former',left_day=? WHERE household_id=? AND actor_id=? AND role=? AND status='active'",
                         (day, s["household_id"], s["actor_id"], s["service_role"]))
            _record_life_event(conn, "service_change", f"{_name(conn, int(s['actor_id']))} left service in household #{s['household_id']}.",
                               actor_id=int(s["actor_id"]), household_id=int(s["household_id"]), day=day)
        count += 1
    return count


def _resolve_migrations(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    count = 0
    for m in conn.execute("SELECT * FROM household_migration_plans WHERE status='planned' AND planned_day<=? ORDER BY planned_day,id", (day,)).fetchall():
        hid, dest = int(m["household_id"]), int(m["destination_location_id"])
        hh = conn.execute("SELECT status,location_id FROM households WHERE id=?", (hid,)).fetchone()
        if not hh or str(hh["status"]) in {"dissolved", "historical"}:
            conn.execute("UPDATE household_migration_plans SET status='cancelled' WHERE id=?", (m["id"],))
            continue
        if hh["location_id"] is not None and int(hh["location_id"]) == dest:
            conn.execute("UPDATE household_migration_plans SET status='completed',completed_day=? WHERE id=?", (day, m["id"]))
            continue
        origin = int(hh["location_id"]) if hh["location_id"] is not None else None
        # v0.22: when campaign route geography exists, household migration must traverse it rather than teleport.
        if origin is not None:
            from .ecology import find_route_path, start_travel
            touching = conn.execute(
                "SELECT COUNT(*) FROM travel_routes WHERE from_location_id IN (?,?) OR to_location_id IN (?,?)",
                (origin, dest, origin, dest),
            ).fetchone()[0]
            if touching:
                path = find_route_path(conn, origin, dest, day=day)
                if not path:
                    conn.execute("UPDATE household_migration_plans SET planned_day=? WHERE id=?", (day + 3, m["id"]))
                    continue
                plan_id = start_travel(conn, "household", hid, dest, metadata={"migration_plan_id": int(m["id"]), "reason": m["reason"]})
                conn.execute("UPDATE household_migration_plans SET status='in_transit',metadata_json=? WHERE id=?",
                             (json.dumps({"travel_plan_id": plan_id}, sort_keys=True), m["id"]))
                count += 1
                continue
        # Structural fallback for locations whose travel geography has not been crystallized yet.
        conn.execute("UPDATE households SET location_id=?,updated_day=? WHERE id=?", (dest, day, hid))
        members = conn.execute("SELECT actor_id FROM household_members WHERE household_id=? AND status='active'", (hid,)).fetchall()
        for r in members:
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (dest, r[0]))
            conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (hid, r[0]))
        conn.execute("UPDATE household_migration_plans SET status='completed',completed_day=? WHERE id=?", (day, m["id"]))
        _record_life_event(conn, "migration", f"Household #{hid} migrated to location #{dest}.", household_id=hid, location_id=dest, day=day,
                           metadata={"reason": m["reason"], "resolution": "structural_unrouted"})
        if event_logger:
            event_logger(day=day, event_type="life:migration", title=f"Household migration #{hid}",
                         summary=f"Household #{hid} moved to location #{dest}.", severity=1, source_actor_id=None,
                         target_actor_ids=tuple(int(r[0]) for r in members), location_id=dest)
        count += 1
    return count


def _resolve_demography(conn: sqlite3.Connection, day: int) -> int:
    rows = conn.execute("SELECT * FROM demographic_cohorts WHERE last_review_day<? ORDER BY location_id,cohort_key,id", (day,)).fetchall()
    due = [r for r in rows if day - int(r["last_review_day"]) >= 365]
    if not due:
        return 0
    widths = {"0_4": 5.0, "5_12": 8.0, "13_17": 5.0, "18_39": 22.0, "40_59": 20.0}
    nxt = {"0_4": "5_12", "5_12": "13_17", "13_17": "18_39", "18_39": "40_59", "40_59": "60_plus"}
    # Snapshot every due cohort before writing, so a person cannot age through multiple bands in one review.
    due_updates: dict[tuple[int,str,str], float] = {}
    inflow: dict[tuple[int,str,str], float] = {}
    inflow_source: dict[tuple[int,str,str], sqlite3.Row] = {}
    for c in due:
        key = (int(c["location_id"]), str(c["cohort_key"]), str(c["age_band"]))
        years = (day - int(c["last_review_day"])) / 365.0
        pop = float(c["population"])
        migration = pop * float(c["annual_migration_rate"]) * years
        births = float(c["annual_birth_pressure"]) * years if str(c["age_band"]) == "0_4" else 0.0
        working = max(0.0, pop + migration + births)
        age_band = str(c["age_band"])
        aged_out = 0.0
        if age_band in widths:
            # Aggregate Leslie-style aging. The bounded fraction prevents an overdue review from
            # moving more people than the source band contains.
            aged_out = working * min(1.0, years / widths[age_band])
            working -= aged_out
            nk = (key[0], key[1], nxt[age_band])
            inflow[nk] = inflow.get(nk, 0.0) + aged_out
            inflow_source[nk] = c
        due_updates[key] = working
    # Add inflow to due destinations in-memory. Non-due destinations receive population only;
    # their last_review_day is deliberately preserved so partial-year migration/aging time is not lost.
    for key, amount in inflow.items():
        if key in due_updates:
            due_updates[key] += amount
            continue
        existing = conn.execute("SELECT * FROM demographic_cohorts WHERE location_id=? AND cohort_key=? AND age_band=?", key).fetchone()
        if existing:
            conn.execute("UPDATE demographic_cohorts SET population=population+? WHERE id=?", (amount, existing["id"]))
        else:
            source = inflow_source.get(key)
            conn.execute(
                """INSERT INTO demographic_cohorts(location_id,cohort_key,age_band,population,annual_birth_pressure,annual_migration_rate,last_review_day,metadata_json)
                   VALUES (?,?,?,?,0,?,?,?)""",
                (key[0], key[1], key[2], amount, float(source["annual_migration_rate"]) if source else 0.0, day,
                 source["metadata_json"] if source else "{}"),
            )
    for key, value in due_updates.items():
        conn.execute("UPDATE demographic_cohorts SET population=?,last_review_day=? WHERE location_id=? AND cohort_key=? AND age_band=?",
                     (max(0.0, value), day, key[0], key[1], key[2]))
    return len(due)


def next_household_life_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals: list[int] = []
    for sql in (
        "SELECT MIN(review_day) FROM household_service_terms WHERE status='active' AND review_day>? AND review_day<=?",
        "SELECT MIN(planned_day) FROM household_migration_plans WHERE status='planned' AND planned_day>? AND planned_day<=?",
    ):
        r = conn.execute(sql, (after_day, end_day)).fetchone()[0]
        if r is not None:
            vals.append(int(r))
    # Exact family-plan due dates are decision-relevant history; do not round them to a monthly tick.
    # Asked in SQL, not row by row in Python: this runs every time the scheduler asks for the next due day, over every union and every living actor.
    r = conn.execute(
        """SELECT MIN(COALESCE(json_extract(family_plan_json,'$.earliest_next_child_day'),
                               started_day + COALESCE(json_extract(family_plan_json,'$.spacing_days'), 730)))
           FROM household_unions WHERE status='active' AND COALESCE(json_extract(family_plan_json,'$.auto_children'),0) NOT IN (0,'',0.0)
             AND COALESCE(json_extract(family_plan_json,'$.earliest_next_child_day'), started_day + COALESCE(json_extract(family_plan_json,'$.spacing_days'), 730)) > ?
             AND COALESCE(json_extract(family_plan_json,'$.earliest_next_child_day'), started_day + COALESCE(json_extract(family_plan_json,'$.spacing_days'), 730)) <= ?""",
        (after_day, end_day)).fetchone()[0]
    if r is not None:
        vals.append(int(r))
    # Life-stage boundaries are also scheduled on their exact threshold day when a birth day is known.
    r = conn.execute(
        """SELECT MIN(d) FROM (SELECT birth_day + CASE life_stage WHEN 'infant' THEN ? WHEN 'child' THEN ? WHEN 'youth' THEN ? WHEN 'adult' THEN ? END AS d
                               FROM actor_life_profiles WHERE life_status='living' AND birth_day IS NOT NULL) WHERE d > ? AND d <= ?""",
        (2 * 365, 13 * 365, 18 * 365, 60 * 365, after_day, end_day)).fetchone()[0]
    if r is not None:
        vals.append(int(r))
    from . import tiers
    if tiers.batching(conn):
        r = conn.execute("SELECT value FROM runtime_flags WHERE key='social_scan_day'").fetchone()
        if r is not None and after_day < int(r[0]) + tiers.BATCH_DAYS <= end_day:
            vals.append(int(r[0]) + tiers.BATCH_DAYS)
    # Profiles without an exact upcoming boundary still receive a bounded periodic review.
    if conn.execute("SELECT 1 FROM actor_life_profiles WHERE life_status='living' LIMIT 1").fetchone():
        d = ((after_day // 30) + 1) * 30
        if d <= end_day:
            vals.append(d)
    # Aggregate cohorts are due one year from their own last review, not on global calendar-year boundaries.
    for r in conn.execute("SELECT last_review_day FROM demographic_cohorts").fetchall():
        d = int(r["last_review_day"]) + 365
        if after_day < d <= end_day:
            vals.append(d)
    # POPLIFE-01 owns the full 52m-scale live age-cohort process. It shares this household/life
    # process owner so births/aging/death remain one life-course phase rather than a rival clock.
    try:
        from .background_population import next_population_life_course_due_day
        d = next_population_life_course_due_day(conn, after_day, end_day)
        if d is not None:
            vals.append(d)
    except sqlite3.OperationalError:
        pass
    return min(vals) if vals else None


def _resolve_cultivation_uptake(conn: sqlite3.Connection, day: int) -> int:
    from .cultivation import resolve_cultivation_uptake
    return resolve_cultivation_uptake(conn, day)


def _resolve_unnamed_marriages(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    from .opening_family import resolve_unnamed_marriages
    return resolve_unnamed_marriages(conn, day, event_logger=event_logger)


def process_due_household_life(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int | float]:
    from .background_population import process_due_population_life_course
    poplife = process_due_population_life_course(conn, day)
    return {
        "life_profiles": _review_profiles(conn, day, event_logger),
        "births": _resolve_planned_births(conn, day, event_logger),
        "unnamed_marriages": _resolve_unnamed_marriages(conn, day, event_logger),
        "cultivation_uptake": _resolve_cultivation_uptake(conn, day),
        "social_contacts": _resolve_social_contacts(conn, day),
        "guardianship_resolutions": _resolve_guardianship_needs(conn, day),
        "service_reviews": _resolve_service_terms(conn, day),
        "migrations": _resolve_migrations(conn, day, event_logger),
        "demographic_cohorts": _resolve_demography(conn, day),
        "population_sources_reviewed": int(poplife.get("sources_reviewed", 0)),
        "population_source_year_periods": int(poplife.get("source_year_periods", 0)),
        "population_births": float(poplife.get("births", 0.0)),
        "population_deaths": float(poplife.get("deaths", 0.0)),
    }


def household_life_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "living_profiles": int(conn.execute("SELECT COUNT(*) FROM actor_life_profiles WHERE life_status='living'").fetchone()[0]),
        "active_unions": int(conn.execute("SELECT COUNT(*) FROM household_unions WHERE status='active'").fetchone()[0]),
        "active_guardianships": int(conn.execute("SELECT COUNT(*) FROM guardianships WHERE status='active'").fetchone()[0]),
        "active_dependencies": int(conn.execute("SELECT COUNT(*) FROM household_dependencies WHERE status='active'").fetchone()[0]),
        "active_service_terms": int(conn.execute("SELECT COUNT(*) FROM household_service_terms WHERE status='active'").fetchone()[0]),
        "planned_migrations": int(conn.execute("SELECT COUNT(*) FROM household_migration_plans WHERE status='planned'").fetchone()[0]),
        "life_events": int(conn.execute("SELECT COUNT(*) FROM life_events").fetchone()[0]),
        "aggregate_population": round(float(__import__('engine.background_population', fromlist=['current_world_population']).current_world_population(conn)), 2),
    }
```

## engine/civilian_life.py

```python
from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def create_building(conn: sqlite3.Connection, name: str, building_kind: str, *, location_id: int | None = None,
                    owner_actor_id: int | None = None, household_id: int | None = None,
                    institution_actor_id: int | None = None, project_id: int | None = None,
                    style_key: str | None = None, capacity: float = 50, condition: float = 100,
                    prestige: float = 50, utility: float = 50, maintenance_burden: float = 10,
                    completed_day: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn) if completed_day is None else int(completed_day)
    cur = conn.execute(
        """INSERT INTO buildings(name,building_kind,location_id,owner_actor_id,household_id,institution_actor_id,project_id,
                                  style_key,capacity,condition,prestige,utility,maintenance_burden,completed_day,status,metadata_json,updated_day)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?,?)""",
        (name, building_kind, location_id, owner_actor_id, household_id, institution_actor_id, project_id,
         style_key, capacity, condition, prestige, utility, maintenance_burden, day,
         json.dumps(metadata or {}, sort_keys=True), day),
    )
    return int(cur.lastrowid)


def ensure_style_movement(conn: sqlite3.Connection, style_key: str, name: str, style_domain: str, *,
                          origin_location_id: int | None = None, origin_actor_id: int | None = None,
                          prestige: float = 50, novelty: float = 50, accessibility: float = 50,
                          durability: float = 50, status: str = "emerging",
                          metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    conn.execute(
        """INSERT OR IGNORE INTO style_movements(style_key,name,style_domain,origin_location_id,origin_actor_id,
                                                  prestige,novelty,accessibility,durability,status,created_day,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (style_key, name, style_domain, origin_location_id, origin_actor_id, prestige, novelty, accessibility,
         durability, status, day, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(conn.execute("SELECT id FROM style_movements WHERE style_key=?", (style_key,)).fetchone()[0])


def set_style_adoption(conn: sqlite3.Connection, style_id: int, location_id: int, *, adoption: float = 0,
                       elite_support: float = 0, craft_capacity: float = 50, resistance: float = 20,
                       metadata: dict[str, Any] | None = None) -> None:
    conn.execute(
        """INSERT INTO style_adoption(style_id,location_id,adoption,elite_support,craft_capacity,resistance,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(style_id,location_id) DO UPDATE SET adoption=excluded.adoption,elite_support=excluded.elite_support,
             craft_capacity=excluded.craft_capacity,resistance=excluded.resistance,last_review_day=excluded.last_review_day,
             metadata_json=excluded.metadata_json""",
        (style_id, location_id, adoption, elite_support, craft_capacity, resistance, _day(conn),
         json.dumps(metadata or {}, sort_keys=True)),
    )


def link_object_style(conn: sqlite3.Connection, object_id: int, style_id: int, *, strength: float = 100,
                      relation_kind: str = "made_in") -> None:
    conn.execute(
        "INSERT OR REPLACE INTO object_style_links(object_id,style_id,strength,relation_kind) VALUES (?,?,?,?)",
        (object_id, style_id, strength, relation_kind),
    )


def set_succession_plan(conn: sqlite3.Connection, household_id: int, *, designated_heir_actor_id: int | None = None,
                        succession_method: str = "designated", certainty: float = 50,
                        dispute_pressure: float = 0, notes: str | None = None) -> None:
    conn.execute(
        """INSERT INTO household_succession_plans(household_id,designated_heir_actor_id,succession_method,certainty,dispute_pressure,status,notes,updated_day)
           VALUES (?,?,?,?,?,'active',?,?)
           ON CONFLICT(household_id) DO UPDATE SET designated_heir_actor_id=excluded.designated_heir_actor_id,
             succession_method=excluded.succession_method,certainty=excluded.certainty,dispute_pressure=excluded.dispute_pressure,
             status='active',notes=excluded.notes,updated_day=excluded.updated_day""",
        (household_id, designated_heir_actor_id, succession_method, certainty, dispute_pressure, notes, _day(conn)),
    )


def set_inheritance_claim(conn: sqlite3.Connection, household_id: int, actor_id: int, *, priority: float = 50,
                          legitimacy: float = 50, support: float = 0, status: str = "potential",
                          notes: str | None = None) -> int:
    conn.execute(
        """INSERT INTO inheritance_claims(household_id,actor_id,priority,legitimacy,support,status,notes)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(household_id,actor_id) DO UPDATE SET priority=excluded.priority,legitimacy=excluded.legitimacy,
             support=excluded.support,status=excluded.status,notes=excluded.notes""",
        (household_id, actor_id, priority, legitimacy, support, status, notes),
    )
    return int(conn.execute("SELECT id FROM inheritance_claims WHERE household_id=? AND actor_id=?",
                            (household_id, actor_id)).fetchone()[0])


def resolve_household_succession(conn: sqlite3.Connection, household_id: int, *, new_head_actor_id: int | None = None,
                                 event_logger: Callable[..., int] | None = None) -> dict[str, Any]:
    h = conn.execute("SELECT * FROM households WHERE id=?", (household_id,)).fetchone()
    if not h:
        raise ValueError("Unknown household")
    former = h["head_actor_id"]
    plan = conn.execute("SELECT * FROM household_succession_plans WHERE household_id=?", (household_id,)).fetchone()
    resolution = "manual" if new_head_actor_id is not None else "vacant"
    disputed = 0
    if new_head_actor_id is None and plan and plan["designated_heir_actor_id"] is not None and float(plan["certainty"]) >= 50:
        new_head_actor_id = int(plan["designated_heir_actor_id"])
        resolution = "designated"
        disputed = 1 if float(plan["dispute_pressure"]) >= 60 else 0
    if new_head_actor_id is None:
        claims = conn.execute(
            """SELECT *, (priority*0.45 + legitimacy*0.35 + support*0.20) AS score
               FROM inheritance_claims WHERE household_id=? AND status IN ('potential','active')
               ORDER BY score DESC,id""", (household_id,)).fetchall()
        if claims:
            new_head_actor_id = int(claims[0]["actor_id"])
            resolution = "claim_strength"
            if len(claims) > 1 and float(claims[0]["score"]) - float(claims[1]["score"]) < 12:
                disputed = 1
    day = _day(conn)
    conn.execute("UPDATE households SET head_actor_id=?,status=?,updated_day=? WHERE id=?",
                 (new_head_actor_id, "active" if new_head_actor_id is not None else "declining", day, household_id))
    if former is not None:
        conn.execute("UPDATE household_members SET role='former_head',status='former',left_day=? WHERE household_id=? AND actor_id=?",
                     (day, household_id, former))
    if new_head_actor_id is not None:
        conn.execute(
            """INSERT INTO household_members(household_id,actor_id,role,authority,dependency,joined_day,status)
               VALUES (?,?,?,?,?,?, 'active')
               ON CONFLICT(household_id,actor_id) DO UPDATE SET role='head',authority=100,status='active',left_day=NULL""",
            (household_id, new_head_actor_id, "head", 100, 0, day),
        )
        # Personal cultural property of the former head passes to the successor as campaign history.
        objects = conn.execute("SELECT id FROM cultural_objects WHERE current_owner_actor_id=? AND status!='destroyed'", (former,)).fetchall() if former else []
        from .civilian import add_provenance
        for obj in objects:
            oid = int(obj[0])
            conn.execute("UPDATE cultural_objects SET current_owner_actor_id=? WHERE id=?", (new_head_actor_id, oid))
            add_provenance(conn, oid, "inherited", "Passed through household succession.",
                           from_actor_id=former, to_actor_id=new_head_actor_id, location_id=h["location_id"], day=day)
        conn.execute("UPDATE inheritance_claims SET status=CASE WHEN actor_id=? THEN 'satisfied' ELSE status END WHERE household_id=?",
                     (new_head_actor_id, household_id))
    summary = f"{h['name']} succession resolved" + (f" under {new_head_actor_id}" if new_head_actor_id else " without a settled head")
    conn.execute("INSERT INTO succession_events(household_id,day,former_head_actor_id,new_head_actor_id,resolution_kind,disputed,summary) VALUES (?,?,?,?,?,?,?)",
                 (household_id, day, former, new_head_actor_id, resolution, disputed, summary))
    if plan:
        conn.execute("UPDATE household_succession_plans SET status=?,updated_day=? WHERE household_id=?",
                     ("contested" if disputed else "resolved", day, household_id))
    if event_logger:
        event_logger(day=day, event_type="civilian:succession", title=f"Succession: {h['name']}", summary=summary,
                     severity=2 if disputed else 1, source_actor_id=former,
                     target_actor_ids=tuple([new_head_actor_id] if new_head_actor_id else []), location_id=h["location_id"])
    return {"household_id": household_id, "former_head_actor_id": former,
            "new_head_actor_id": new_head_actor_id, "resolution_kind": resolution, "disputed": bool(disputed)}


def create_credit_agreement(conn: sqlite3.Connection, *, principal: float,
                            lender_actor_id: int | None = None, lender_enterprise_id: int | None = None,
                            borrower_actor_id: int | None = None, borrower_enterprise_id: int | None = None,
                            interest_rate_per_30: float = 0, due_day: int | None = None,
                            collateral_object_id: int | None = None, risk: float = 20,
                            metadata: dict[str, Any] | None = None) -> int:
    if not (lender_actor_id or lender_enterprise_id) or not (borrower_actor_id or borrower_enterprise_id):
        raise ValueError("Credit needs a lender and a borrower")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO credit_agreements(lender_actor_id,lender_enterprise_id,borrower_actor_id,borrower_enterprise_id,
                                          principal,outstanding,interest_rate_per_30,opened_day,due_day,collateral_object_id,
                                          status,risk,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?, 'current', ?,?,?)""",
        (lender_actor_id, lender_enterprise_id, borrower_actor_id, borrower_enterprise_id, principal, principal,
         interest_rate_per_30, day, due_day, collateral_object_id, risk, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    if borrower_enterprise_id is not None:
        conn.execute("UPDATE civilian_enterprises SET cash=cash+?,debt=debt+?,updated_day=? WHERE id=?",
                     (principal, principal, day, borrower_enterprise_id))
    if lender_enterprise_id is not None:
        conn.execute("UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?", (principal, day, lender_enterprise_id))
    return int(cur.lastrowid)


def make_credit_payment(conn: sqlite3.Connection, agreement_id: int, amount: float) -> float:
    row = conn.execute("SELECT * FROM credit_agreements WHERE id=?", (agreement_id,)).fetchone()
    if not row:
        raise ValueError("Unknown credit agreement")
    if amount <= 0:
        raise ValueError("Payment must be positive")
    amount = min(float(row["outstanding"]), float(amount))
    outstanding = max(0.0, float(row["outstanding"]) - amount)
    status = "repaid" if outstanding <= 1e-9 else "current"
    day = _day(conn)
    conn.execute("UPDATE credit_agreements SET outstanding=?,status=?,last_review_day=? WHERE id=?",
                 (outstanding, status, day, agreement_id))
    if row["borrower_enterprise_id"] is not None:
        conn.execute("UPDATE civilian_enterprises SET cash=cash-?,debt=max(0,debt-?),updated_day=? WHERE id=?",
                     (amount, amount, day, row["borrower_enterprise_id"]))
    if row["lender_enterprise_id"] is not None:
        conn.execute("UPDATE civilian_enterprises SET cash=cash+?,updated_day=? WHERE id=?",
                     (amount, day, row["lender_enterprise_id"]))
    return outstanding


def set_enterprise_partner(conn: sqlite3.Connection, enterprise_id: int, actor_id: int, *, ownership_share: float = 0,
                           governance_weight: float = 0, capital_committed: float = 0,
                           role: str = "partner") -> None:
    conn.execute(
        """INSERT INTO enterprise_partners(enterprise_id,actor_id,ownership_share,governance_weight,capital_committed,role,joined_day,status)
           VALUES (?,?,?,?,?,?,?, 'active')
           ON CONFLICT(enterprise_id,actor_id) DO UPDATE SET ownership_share=excluded.ownership_share,
             governance_weight=excluded.governance_weight,capital_committed=excluded.capital_committed,role=excluded.role,
             status='active',left_day=NULL""",
        (enterprise_id, actor_id, ownership_share, governance_weight, capital_committed, role, _day(conn)),
    )


def create_professional_membership(conn: sqlite3.Connection, actor_id: int, institution_actor_id: int,
                                   profession_domain: str, *, role: str = "member", standing: float = 50,
                                   influence: float = 10, dues_per_30: float = 0,
                                   metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO professional_memberships(actor_id,institution_actor_id,profession_domain,role,standing,seniority_days,
                                                 influence,dues_per_30,eligibility_state,joined_day,last_review_day,status,metadata_json)
           VALUES (?,?,?,?,?,0,?,?,'ordinary',?,?, 'active',?)""",
        (actor_id, institution_actor_id, profession_domain, role, standing, influence, dues_per_30,
         day, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _resolve_buildings(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    try:  # places (the business layer) keep their own upkeep and condition
        rows = conn.execute("SELECT * FROM buildings WHERE status IN ('active','strained','derelict') AND updated_day<? AND id NOT IN (SELECT building_id FROM place_details)", (day,)).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute("SELECT * FROM buildings WHERE status IN ('active','strained','derelict') AND updated_day<?", (day,)).fetchall()
    for b in rows:
        elapsed = day - int(b["updated_day"])
        burden = float(b["maintenance_burden"]) * elapsed / 30.0
        funded = False
        if b["household_id"] is not None:
            hh = conn.execute("SELECT liquidity FROM households WHERE id=?", (b["household_id"],)).fetchone()
            if hh and float(hh[0]) >= burden * 0.02:
                cost = burden * 0.02
                conn.execute("UPDATE households SET liquidity=liquidity-? WHERE id=?", (cost, b["household_id"]))
                funded = True
        elif b["owner_actor_id"] is not None or b["institution_actor_id"] is not None:
            funded = True  # abstracted non-household maintenance budget at this resolution.
        condition = float(b["condition"])
        if funded:
            condition = min(100.0, condition + 0.02 * elapsed)
        else:
            condition = max(0.0, condition - (0.08 + float(b["maintenance_burden"]) / 400.0) * elapsed)
        status = "active" if condition >= 55 else "strained" if condition >= 25 else "derelict"
        conn.execute("UPDATE buildings SET condition=?,status=?,updated_day=? WHERE id=?", (condition, status, day, b["id"]))
        count += 1
    return count


def _resolve_styles(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    for a in conn.execute("""SELECT sa.*,sm.prestige,sm.novelty,sm.accessibility,sm.durability,sm.status AS style_status
                             FROM style_adoption sa JOIN style_movements sm ON sm.id=sa.style_id
                             WHERE sa.last_review_day<?""", (day,)).fetchall():
        elapsed = day - int(a["last_review_day"])
        months = elapsed / 30.0
        pull = (float(a["prestige"]) * 0.35 + float(a["novelty"]) * 0.15 + float(a["accessibility"]) * 0.15 +
                float(a["elite_support"]) * 0.2 + float(a["craft_capacity"]) * 0.15) / 100.0
        resistance = float(a["resistance"]) / 100.0
        adoption = float(a["adoption"])
        growth = max(-2.0, (pull - resistance - adoption / 160.0) * 8.0) * months
        if a["style_status"] in ("declining", "historical"):
            growth -= (2.5 + (100.0 - float(a["durability"])) / 30.0) * months
        adoption = max(0.0, min(100.0, adoption + growth))
        conn.execute("UPDATE style_adoption SET adoption=?,last_review_day=? WHERE style_id=? AND location_id=?",
                     (adoption, day, a["style_id"], a["location_id"]))
        count += 1
    return count


def _resolve_credit(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    for c in conn.execute("SELECT * FROM credit_agreements WHERE status IN ('current','late') AND last_review_day<?", (day,)).fetchall():
        elapsed = day - int(c["last_review_day"])
        interest = float(c["outstanding"]) * float(c["interest_rate_per_30"]) * elapsed / 30.0
        outstanding = float(c["outstanding"]) + interest
        status = str(c["status"])
        if c["due_day"] is not None and day > int(c["due_day"]):
            lateness = day - int(c["due_day"])
            status = "defaulted" if lateness >= 90 or float(c["risk"]) >= 85 else "late"
        conn.execute("UPDATE credit_agreements SET outstanding=?,status=?,last_review_day=? WHERE id=?",
                     (outstanding, status, day, c["id"]))
        if c["borrower_enterprise_id"] is not None:
            conn.execute("UPDATE civilian_enterprises SET debt=debt+?,updated_day=? WHERE id=?",
                         (interest, day, c["borrower_enterprise_id"]))
            if status == "defaulted":
                conn.execute("UPDATE civilian_enterprises SET status='strained' WHERE id=? AND status='active'", (c["borrower_enterprise_id"],))
        count += 1
    return count


def _resolve_professional_memberships(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    for m in conn.execute("SELECT * FROM professional_memberships WHERE status='active' AND last_review_day<?", (day,)).fetchall():
        elapsed = day - int(m["last_review_day"])
        seniority = int(m["seniority_days"]) + elapsed
        standing = float(m["standing"])
        before_elig = str(m["eligibility_state"])
        elig = before_elig
        # Membership can make someone eligible for review, but never auto-promotes role/office.
        if seniority >= 365 and standing >= 65 and before_elig == "ordinary":
            elig = "eligible_for_review"
        conn.execute("UPDATE professional_memberships SET seniority_days=?,eligibility_state=?,last_review_day=? WHERE id=?",
                     (seniority, elig, day, m["id"]))
        if elig != before_elig:
            conn.execute("INSERT INTO professional_reviews(membership_id,day,standing_before,standing_after,eligibility_before,eligibility_after,reason) VALUES (?,?,?,?,?,?,?)",
                         (m["id"], day, standing, standing, before_elig, elig, "Seniority and standing reached review threshold; no office was granted automatically."))
        count += 1
    return count


def _register_family_claims(conn: sqlite3.Connection, household_id: int, former_head: int) -> int:
    """Hearth custom: a household passes within the family.  With no designated heir and no filed claim,
    the surviving spouse and living adult children hold inheritance claims (spouse first, then the
    eldest).  Only when neither exists is a latent adult child of the former head revealed.
    """
    if conn.execute("SELECT 1 FROM inheritance_claims WHERE household_id=? AND status IN ('potential','active')", (household_id,)).fetchone():
        return 0
    day = _day(conn)
    def living_adult(aid: int) -> bool:
        r = conn.execute("""SELECT a.status,lp.life_status,lp.birth_day FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id
                            WHERE a.id=?""", (aid,)).fetchone()
        return bool(r and r[0] == "active" and (r[1] in (None, "living")) and (r[2] is None or day - int(r[2]) >= 18 * 365))
    made = 0
    for u in conn.execute("""SELECT actor_a_id,actor_b_id FROM household_unions WHERE (actor_a_id=? OR actor_b_id=?)
                             AND status IN ('active','widowed') ORDER BY started_day DESC,id DESC""", (former_head, former_head)).fetchall():
        spouse = int(u[1] if int(u[0]) == former_head else u[0])
        if living_adult(spouse):
            set_inheritance_claim(conn, household_id, spouse, priority=75, legitimacy=75, support=65, status="active",
                                  notes="surviving spouse (family inheritance)")
            made += 1
            break
    children = [int(r[0]) for r in conn.execute(
        """SELECT k.actor_b_id FROM kinship_links k JOIN actor_life_profiles lp ON lp.actor_id=k.actor_b_id
           WHERE k.actor_a_id=? AND k.kin_kind IN ('parent','adoptive_parent') AND k.legal_status<>'former'
           ORDER BY lp.birth_day,k.actor_b_id""", (former_head,))]
    adults = [c for c in children if living_adult(c)]
    if not made and not adults:
        from .opening_family import reveal_latent_adult_child
        revealed = reveal_latent_adult_child(conn, former_head, reason="household inheritance")
        if revealed is not None:
            adults = [revealed]
    for rank, child in enumerate(adults):
        set_inheritance_claim(conn, household_id, child, priority=max(30, 60 - 8 * rank), legitimacy=65, support=max(20, 50 - 10 * rank),
                              status="active", notes="adult child (family inheritance)")
        made += 1
    return made


def _resolve_succession_triggers(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None = None) -> int:
    count = 0
    rows = conn.execute("""SELECT h.id AS household_id,h.head_actor_id,a.status AS actor_status
                           FROM households h JOIN actors a ON a.id=h.head_actor_id
                           WHERE h.status IN ('active','declining') AND lower(a.status) IN ('dead','deceased')""").fetchall()
    for r in rows:
        already = conn.execute("SELECT 1 FROM succession_events WHERE household_id=? AND former_head_actor_id=?", (r["household_id"], r["head_actor_id"])).fetchone()
        if not already:
            plan = conn.execute("SELECT designated_heir_actor_id,certainty FROM household_succession_plans WHERE household_id=?",
                                (r["household_id"],)).fetchone()
            if not (plan and plan[0] is not None and float(plan[1]) >= 50):
                _register_family_claims(conn, int(r["household_id"]), int(r["head_actor_id"]))
            resolve_household_succession(conn, int(r["household_id"]), event_logger=event_logger)
            count += 1
    return count


def process_due_civilian_life(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    return {
        "buildings": _resolve_buildings(conn, day),
        "styles": _resolve_styles(conn, day),
        "credit": _resolve_credit(conn, day),
        "professional_memberships": _resolve_professional_memberships(conn, day),
        "successions": _resolve_succession_triggers(conn, day, event_logger),
    }


def civilian_life_summary(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "buildings": int(conn.execute("SELECT COUNT(*) FROM buildings WHERE status!='destroyed'").fetchone()[0]),
        "styles": int(conn.execute("SELECT COUNT(*) FROM style_movements WHERE status!='historical'").fetchone()[0]),
        "style_adoptions": int(conn.execute("SELECT COUNT(*) FROM style_adoption").fetchone()[0]),
        "open_credit": int(conn.execute("SELECT COUNT(*) FROM credit_agreements WHERE status IN ('current','late','defaulted')").fetchone()[0]),
        "enterprise_partners": int(conn.execute("SELECT COUNT(*) FROM enterprise_partners WHERE status='active'").fetchone()[0]),
        "professional_memberships": int(conn.execute("SELECT COUNT(*) FROM professional_memberships WHERE status='active'").fetchone()[0]),
        "succession_plans": int(conn.execute("SELECT COUNT(*) FROM household_succession_plans WHERE status IN ('active','contested')").fetchone()[0]),
    }
```

## engine/temptations.py

```python
"""Temptations: the world puts concrete chances before people, tied to what they want.

A chance has a price and a last day. It names a real place, business and person in the save, and comes from someone they
know or from something they pass. There is no beat to it: each want draws its own chances, the more the stronger it is
and the more its owner is about. The protagonist's chances are laid before him and wait for his say. Everyone else takes
theirs on the same rules, looked at coarsely (a slice of people each week, only for what they want badly), and one he
sits on can go to someone else. It runs on the weekly life cadence; the words and rates come from the package's `wants`
data, and without it nothing runs. The engine only puts the chance there: taking it or leaving it is his."""
from __future__ import annotations

import math
import random
import sqlite3

from . import design, findings, ledger, life_matters, money_records, org_lifecycle, price_book, wants

YEAR = 365.0
SEARCH = 40  # how many people near a contested chance are asked whether they want it


def _player(conn: sqlite3.Connection) -> int | None:
    r = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _today(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _name(conn: sqlite3.Connection, actor_id: int) -> str:
    return str(conn.execute("SELECT name FROM actors WHERE id=?", (int(actor_id),)).fetchone()[0])


def _chain(conn: sqlite3.Connection, place: int | None) -> list[int]:
    """A place, then each wider place it stands in."""
    out: list[int] = []
    while place is not None and place not in out:
        out.append(int(place))
        row = conn.execute("SELECT parent_location_id FROM locations WHERE id=?", (place,)).fetchone()
        place = row[0] if row else None
    return out


_FREE = "NOT EXISTS (SELECT 1 FROM inmate_stays s WHERE s.actor_id=a.id AND s.status='inside')"  # behind walls, nothing is passed


def _inside(conn: sqlite3.Connection, actor_id: int) -> bool:
    return bool(conn.execute("SELECT 1 FROM inmate_stays WHERE actor_id=? AND status='inside'", (actor_id,)).fetchone())


_UNDER = "WITH RECURSIVE under(id) AS (SELECT ? UNION SELECT l.id FROM locations l JOIN under u ON l.parent_location_id=u.id) "


def _near_businesses(conn: sqlite3.Connection, who: int, kinds: list[str], names: list[str] | None) -> list[sqlite3.Row]:
    """Open businesses of these kinds (and names) that are not their own: where they are, else the district around, else the city."""
    here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (who,)).fetchone()[0]
    marks = ",".join("?" * len(kinds))
    for place in _chain(conn, here):
        rows = conn.execute(
            _UNDER + f"""SELECT e.id,e.name,e.location_id,l.name place FROM civilian_enterprises e JOIN locations l ON l.id=e.location_id
                WHERE e.status IN ('active','strained') AND e.enterprise_kind IN ({marks}) AND e.name NOT LIKE '[%'
                AND COALESCE(e.owner_actor_id,-1)<>? AND e.location_id IN (SELECT id FROM under) ORDER BY e.id""",
            (place, *kinds, who)).fetchall()
        if names:
            rows = [r for r in rows if any(n.lower() in r["name"].lower() for n in names)]
        if rows:
            return rows
    return []


def _spot(conn: sqlite3.Connection, actor_id: int, broad: bool = False):
    """Where someone is, when it is a particular place: one with other places inside it is too wide to name, unless `broad`."""
    row = conn.execute("""SELECT l.id,l.name,EXISTS(SELECT 1 FROM locations c WHERE c.parent_location_id=l.id) wide
                          FROM actors a JOIN locations l ON l.id=a.current_location_id WHERE a.id=?""", (actor_id,)).fetchone()
    return row if row is not None and (broad or not row["wide"]) else None


def _carriers(conn: sqlite3.Connection, me: int, day: int, other: int | None) -> dict[int, float]:
    """Grown people in his life who might bring him word, the closer the likelier; never the one the want is about."""
    out = {}
    for a, w in life_matters.contacts(conn, me).items():
        r = conn.execute("""SELECT 1 FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                            WHERE a.id=? AND a.actor_type='character' AND p.birth_day<=?""", (a, day - int(16 * YEAR))).fetchone()
        if r and a != other:
            out[a] = w
    return out


def _about(conn: sqlite3.Connection, who: int, day: int) -> tuple[int, int]:
    """How many people are in their life, and how many places they have been seen in these four weeks."""
    places = conn.execute("""SELECT COUNT(DISTINCT e.location_id) FROM events e WHERE e.day>=? AND e.location_id IS NOT NULL
                             AND (e.source_actor_id=? OR e.id IN (SELECT event_id FROM event_targets WHERE actor_id=?))""",
                          (day - 28, who, who)).fetchone()[0]
    return len(life_matters.contacts(conn, who)), 1 + int(places)


def odds(conn: sqlite3.Connection, who: int, want: dict, rule: dict, about: tuple[int, int] | None = None) -> float:
    """The chance that something turns up for this want in a week: how often such things come, how much it is wanted, and
    how much its owner is about (people who might mention it, places where it might be passed)."""
    known, places = about or _about(conn, who, _today(conn))
    reach = known / (known + 8.0) + places / (places + 2.0)
    pull = float(want["strength"]) * (1.5 if want.get("status") == "matters" else 1.0)
    return min(1.0, float(rule.get("comes", 0.0)) * pull * reach)


def _asking(rng: random.Random, item: dict) -> float:
    """A chance is a fair price or better: between the low end and a little over the usual figure."""
    low, high = float(item["low"]), float(item["high"])
    x = rng.uniform(low, min(high, float(item["price"]) * 1.05))
    step = 5 if x >= 100 else 1 if x >= 20 else 0.25
    return round(min(high, max(low, round(x / step) * step)), 2)


def _compose(conn: sqlite3.Connection, me: int, day: int, want: dict, chance: dict, rng: random.Random, item: dict) -> dict | None:
    """One chance made concrete from the save, or None when the save cannot supply who or where it needs."""
    shop = carrier = None
    if chance.get("business"):
        near = _near_businesses(conn, me, chance["business"], chance.get("names"))
        if not near:
            return None
        shop = rng.choice(near)
    if chance["from"] == "contact":
        carrier = life_matters._pick(rng, _carriers(conn, me, day, want.get("other_actor_id")))
        if carrier is None:
            return None
    if shop is not None:
        place_id, place = shop["location_id"], shop["place"]
    else:
        row = _spot(conn, carrier) if carrier is not None else None
        row = row or _spot(conn, me, broad=True)
        if row is None:
            return None
        place_id, place = row[0], row[1]
    price = _asking(rng, item)
    days = rng.randint(*chance["days"])
    said = money_records.fmt(conn, price) + (f" {item['per']}" if item.get("per") else "")
    who = _name(conn, carrier) if carrier is not None else ""
    text = (chance["text"].replace("{carrier}", who).replace("{business}", shop["name"] if shop else "")
            .replace("{place}", place).replace("{price}", said).replace("{days}", str(days)))
    if place not in text:
        text = f"{text} ({place})"
    return {"text": text, "price": price, "per": item.get("per"), "carrier_actor_id": carrier,
            "business_id": shop["id"] if shop else None, "location_id": place_id, "expires_day": day + days}


def _add(conn: sqlite3.Connection, who: int, day: int, key: str, made: dict, status: str = "open", want_id: int | None = None) -> None:
    conn.execute("""INSERT INTO temptations(actor_id,want_id,want_key,text,price,per,carrier_actor_id,business_id,location_id,
                    opened_day,expires_day,status,updated_day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (who, want_id, key, made["text"], made["price"], made["per"], made["carrier_actor_id"], made["business_id"],
                  made["location_id"], day, made["expires_day"], status, day))


def _show(conn: sqlite3.Connection, who: int, rule: dict, price: float | None, day: int) -> None:
    """What having it shows of them, for those who read a person by what they have."""
    gives = rule.get("gives")
    if gives:
        conn.execute("""INSERT INTO bearing_marks(actor_id,kind,text,amount,source,recorded_day) VALUES (?,?,?,?,'derived',?)
                        ON CONFLICT(actor_id,kind,text) DO UPDATE SET status='active',amount=excluded.amount""",
                     (who, gives["kind"], gives["text"], price, day))


def _can_pay(conn: sqlite3.Connection, who: int, price: float, rng: random.Random, living: float) -> bool:
    """Counted money must cover it with a week's living left over. Someone whose money nobody has counted is likelier to
    have it the smaller the sum is beside a few weeks' living."""
    counted = conn.execute("""SELECT 1 FROM resources WHERE actor_id=? AND resource_type='cash' UNION ALL
                              SELECT 1 FROM underworld_leader_wealth WHERE actor_id=?""", (who, who)).fetchone()
    if counted:
        return ledger.balance(conn, ("person", who)) >= price + living
    return not living or rng.random() < 1.0 / (1.0 + (price / (living * 8.0)) ** 2)


def _take(conn: sqlite3.Connection, who: int, day: int, rule: dict, made: dict, living: float) -> None:
    """Someone other than the protagonist takes a chance: the money goes, and they have the thing."""
    money_records.ensure_purse(conn, f"person:{who}", at_least=made["price"] + living * 2)
    purpose = f"{rule['key'].replace('_', ' ')}: {made['text'][:80]}"
    if made["business_id"] is not None:
        ledger.transfer(conn, ("person", who), ("business", made["business_id"]), made["price"], flow_kind="other",
                        purpose=purpose, allow_partial=True)
    else:
        ledger.spend(conn, ("person", who), made["price"], purpose=purpose)
    _add(conn, who, day, rule["key"], {**made, "carrier_actor_id": None, "expires_day": day}, status="taken")
    _show(conn, who, rule, made["price"], day)


def _people_near(conn: sqlite3.Connection, place: int, day: int, but: int) -> list[int]:
    """Living grown people at this place, widening until there are enough of them to ask."""
    found: list[int] = []
    for at in _chain(conn, place):
        found = [int(r[0]) for r in conn.execute(
            _UNDER + f"""SELECT a.id FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                        WHERE a.actor_type='character' AND p.life_status='living' AND p.birth_day BETWEEN ? AND ? AND a.id<>?
                        AND a.current_location_id IN (SELECT id FROM under) AND {_FREE} ORDER BY a.id""",
            (at, day - int(71 * YEAR), day - int(17 * YEAR), but))]
        if len(found) >= SEARCH:
            break
    return found


def _contest(conn: sqlite3.Connection, me: int, day: int, by_key: dict, all_: dict) -> int:
    """What the protagonist is still sitting on may go to someone near it who wants it and can pay."""
    gone = 0
    rows = conn.execute("SELECT * FROM temptations WHERE actor_id=? AND status='open' AND opened_day<? ORDER BY id", (me, day)).fetchall()
    for row in rows:
        rule = by_key.get(row["want_key"])
        rng = random.Random(f"{all_['seed']}:contest:{row['id']}:{day}")
        if rule is None or rng.random() >= float(rule.get("contest", 0.0)):
            continue
        near = _people_near(conn, row["location_id"], day, me)
        for who in rng.sample(near, min(SEARCH, len(near))):
            if not any(w["key"] == rule["key"] for w in wants.derive(conn, who, all_)):
                continue
            if not _can_pay(conn, who, row["price"], rng, all_["living"]):
                continue
            made = {"text": f"{_name(conn, who)} took it: {row['text']}", "price": row["price"], "per": row["per"],
                    "business_id": row["business_id"], "location_id": row["location_id"]}
            _take(conn, who, day, rule, made, all_["living"])
            conn.execute("UPDATE temptations SET status='gone',taker_actor_id=?,updated_day=? WHERE id=?", (who, day, row["id"]))
            gone += 1
            break
    return gone


def _offer(conn: sqlite3.Connection, me: int, day: int, by_key: dict, book: dict) -> int:
    """What turns up for the protagonist this week: each want on its own odds."""
    if _inside(conn, me) or conn.execute("SELECT 1 FROM temptations WHERE actor_id=? AND opened_day=?", (me, day)).fetchone():
        return 0
    about = _about(conn, me, day)
    known, places = about
    opened = 0
    for want in wants.standing(conn, me):
        rule = by_key.get(want["key"])
        item = book.get(want.get("item"))
        if rule is None or item is None or not rule.get("chances"):
            continue
        rng = random.Random(f"{design.run_seed(conn)}:chance:{me}:{want['key']}:{day}")
        if rng.random() >= odds(conn, me, want, rule, about):
            continue
        # the more people he knows the more it comes by word of mouth; the more he gets about, the more he passes it
        ways = {i: (known if c["from"] == "contact" else places * 3.0) + 1.0 for i, c in enumerate(rule["chances"])}
        while ways:
            i = life_matters._pick(rng, ways)
            made = _compose(conn, me, day, want, rule["chances"][i], rng, item)
            if made is None:
                del ways[i]
                continue
            _add(conn, me, day, want["key"], made, want_id=want.get("id"))
            findings.tell(conn, me, [made["text"]], source=made["carrier_actor_id"], confidence=0.9)
            opened += 1
            break
    return opened


def _others(conn: sqlite3.Connection, me: int | None, day: int, rules: dict, by_key: dict, all_: dict) -> int:
    """This week's slice of everyone else: those who want something badly may come upon it and take it."""
    pace = rules.get("others")
    if not pace:
        return 0
    every, least = int(pace["every_weeks"]), float(pace["threshold"])
    slice_ = conn.execute(f"""SELECT a.id FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                             WHERE a.actor_type='character' AND p.life_status='living' AND p.birth_day BETWEEN ? AND ?
                             AND a.id % ?=? AND a.id<>? AND {_FREE}
                             AND NOT EXISTS (SELECT 1 FROM temptations t WHERE t.actor_id=a.id AND t.opened_day=?) ORDER BY a.id""",
                          (day - int(71 * YEAR), day - int(17 * YEAR), every, (day // 7) % every,
                           me if me is not None else -1, day)).fetchall()
    taken, book = 0, all_["book"]
    for (who,) in slice_:
        found = [w for w in wants.derive(conn, who, all_)
                 if w["strength"] >= least and w["item"] in book and by_key[w["key"]].get("chances")]
        if not found:
            continue
        want = found[0]
        rule = by_key[want["key"]]
        rng = random.Random(f"{all_['seed']}:others:{who}:{day}")
        often = float(rule.get("comes", 0.0)) * want["strength"] * float(pace["reach"]) * every
        if rng.random() >= 1.0 - math.exp(-often):
            continue
        price = _asking(rng, book[want["item"]])
        if not _can_pay(conn, who, price, rng, all_["living"]):
            continue
        kinds = [c for c in rule["chances"] if c.get("business")]
        shops = _near_businesses(conn, who, kinds[0]["business"], kinds[0].get("names")) if kinds else []
        shop = rng.choice(shops) if shops else None
        place = shop["location_id"] if shop else conn.execute("SELECT current_location_id FROM actors WHERE id=?", (who,)).fetchone()[0]
        if place is None:
            continue
        made = {"text": f"{_name(conn, who)} took {want['what']}", "price": price, "per": book[want["item"]].get("per"),
                "business_id": shop["id"] if shop else None, "location_id": place}
        _take(conn, who, day, rule, made, all_["living"])
        taken += 1
    return taken


def weekly(conn: sqlite3.Connection, day: int) -> dict:
    """A week of chances: some he sat on go to others, the old ones lapse, new ones turn up, and others take theirs."""
    rules = wants.data(conn)
    if not rules:
        return {}
    me = _player(conn)
    by_key = {r["key"]: r for r in rules["wants"]}
    all_ = {**wants.shared(conn), "day": day}
    out = {}
    if me is not None:
        out["chances_gone"] = _contest(conn, me, day, by_key, all_)
    out["chances_lapsed"] = conn.execute("UPDATE temptations SET status='lapsed',updated_day=? WHERE status='open' AND expires_day<?",
                                         (day, day)).rowcount
    if me is not None:
        wants.refresh(conn, me)
        out["chances_opened"] = _offer(conn, me, day, by_key, all_["book"])
    out["chances_taken_by_others"] = _others(conn, me, day, rules, by_key, all_)
    return {k: v for k, v in out.items() if v}


def open_for(conn: sqlite3.Connection, actor_id: int, after_id: int = 0, limit: int = 3) -> list[dict]:
    """The chances still standing, the soonest to close first."""
    day = _today(conn)
    rows = conn.execute("""SELECT t.*,w.what want FROM temptations t LEFT JOIN wants w ON w.actor_id=t.actor_id AND w.key=t.want_key
                           WHERE t.actor_id=? AND t.status='open' AND t.expires_day>=? AND t.id>? ORDER BY t.expires_day,t.id LIMIT ?""",
                        (int(actor_id), day, int(after_id), limit)).fetchall()
    return [{"id": r["id"], "chance": r["text"], "price": money_records.fmt(conn, r["price"]) + (f" {r['per']}" if r["per"] else ""),
             "days_left": r["expires_day"] - day, "want": r["want"]} for r in rows]


def gone_for(conn: sqlite3.Connection, actor_id: int, since_day: int, limit: int = 3) -> list[dict]:
    """The chances that went to someone else since a day, the latest first: what it was and who has it."""
    rows = conn.execute("""SELECT t.text,a.name FROM temptations t JOIN actors a ON a.id=t.taker_actor_id
                           WHERE t.actor_id=? AND t.status='gone' AND t.updated_day>=? ORDER BY t.updated_day DESC,t.id DESC LIMIT ?""",
                        (int(actor_id), int(since_day), limit)).fetchall()
    return [{"chance": r[0], "taken_by": r[1]} for r in rows]


def last_id(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COALESCE(MAX(id),0) FROM temptations").fetchone()[0])


_SAYS = ("taken", "refused")


def say(conn: sqlite3.Connection, actor_id: int, field: str, chance_id: int | None) -> dict:
    """What he did with a chance. Money that changes hands is recorded separately."""
    word = str(field or "").strip().lower()
    if word not in _SAYS or chance_id is None:
        raise ValueError(f"kind=chance needs subject_id (the chance's id) and field: one of {', '.join(_SAYS)}")
    row = conn.execute("SELECT * FROM temptations WHERE id=? AND actor_id=?", (int(chance_id), int(actor_id))).fetchone()
    day = _today(conn)
    if row is None or row["status"] != "open" or row["expires_day"] < day:
        raise ValueError(f"chance {chance_id} is not open to him")
    conn.execute("UPDATE temptations SET status=?,updated_day=? WHERE id=?", (word, day, int(chance_id)))
    if word == "taken":
        conn.execute("UPDATE wants SET status='met',updated_day=? WHERE actor_id=? AND key=?", (day, int(actor_id), row["want_key"]))
        rule = next((r for r in wants.data(conn).get("wants", []) if r["key"] == row["want_key"]), None)
        if rule:
            _show(conn, int(actor_id), rule, row["price"], day)
    return {"saved": "chance", "summary": f"{word}: {row['text'][:120]}"}


org_lifecycle.on_week(weekly)
```

## engine/outings.py

```python
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
```

## engine/psych.py

```python
from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

DEPENDENCY_KINDS = {
    'chemical_medication', 'intoxicant', 'stimulant', 'gambling', 'elixir_performance', 'other'
}
PSYCH_FAMILIES = {'trauma','grief','anxiety','depression','nightmares','obsession','severe_mental_illness','other'}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _living(conn: sqlite3.Connection, actor_id: int) -> bool:
    row=conn.execute("SELECT a.status,lp.life_status FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?",(actor_id,)).fetchone()
    return bool(row and str(row['status'])!='deceased' and (row['life_status'] is None or str(row['life_status'])=='living'))


def _meta(raw: str | None) -> dict[str,Any]:
    try: return json.loads(raw) if raw else {}
    except Exception: return {}


def _upsert_pressure(conn: sqlite3.Connection, actor_id: int, kind: str, description: str, intensity: float, threshold: float=10.0) -> None:
    row=conn.execute("SELECT id FROM pressures WHERE actor_id=? AND kind=? ORDER BY id LIMIT 1",(actor_id,kind)).fetchone()
    intensity=max(0.0,float(intensity))
    if row:
        conn.execute("UPDATE pressures SET description=?,intensity=?,threshold=?,updated_day=? WHERE id=?",(description,intensity,threshold,_day(conn),int(row[0])))
    elif intensity>0:
        conn.execute("INSERT INTO pressures(actor_id,kind,description,intensity,threshold,updated_day) VALUES (?,?,?,?,?,?)",(actor_id,kind,description,intensity,threshold,_day(conn)))


def _sync_dependency_pressure(conn: sqlite3.Connection, actor_id: int, dependency_kind: str) -> None:
    row=conn.execute("SELECT * FROM dependency_profiles WHERE actor_id=? AND dependency_kind=?",(actor_id,dependency_kind)).fetchone()
    if not row: return
    status=str(row['status'])
    intensity=0.0 if status in {'resolved','risk'} else max(float(row['functional_impairment']),float(row['urge_load'])*0.45)
    _upsert_pressure(conn,actor_id,f'dependency:{dependency_kind}',f"Dependence on {dependency_kind.replace('_',' ')} is creating practical pressure.",intensity,20.0)


def _sync_psych_pressure(conn: sqlite3.Connection, actor_id: int, family: str) -> None:
    rows=conn.execute("SELECT severity,functional_impairment,status FROM psychological_conditions WHERE actor_id=? AND condition_family=? AND status IN ('active','recovering','chronic')",(actor_id,family)).fetchall()
    intensity=max([max(float(r['functional_impairment']),float(r['severity'])*0.25) for r in rows],default=0.0)
    _upsert_pressure(conn,actor_id,f'psychological:{family}',f"Persistent {family.replace('_',' ')} is affecting ordinary functioning.",intensity,20.0)


def record_dependency_exposure(conn: sqlite3.Connection, actor_id: int, dependency_kind: str, *, source_kind: str,
                               amount: float=1.0, reinforcing_value: float=50.0, adverse_consequence: float=0.0,
                               source_ref_kind: str | None=None, source_ref_id: int | None=None,
                               metadata: dict[str,Any] | None=None) -> int:
    if dependency_kind not in DEPENDENCY_KINDS: raise ValueError('Unknown dependency kind')
    if not _living(conn,actor_id): raise ValueError('Dependency exposure requires living actor')
    if amount<=0: raise ValueError('Exposure amount must be positive')
    day=_day(conn)
    if source_ref_kind and source_ref_id is not None:
        old=conn.execute("SELECT id FROM dependency_exposures WHERE actor_id=? AND source_ref_kind=? AND source_ref_id=? AND dependency_kind=?",(actor_id,source_ref_kind,source_ref_id,dependency_kind)).fetchone()
        if old: return int(old[0])
    cur=conn.execute("""INSERT INTO dependency_exposures(actor_id,dependency_kind,day,source_kind,amount,reinforcing_value,adverse_consequence,source_ref_kind,source_ref_id,metadata_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                     (actor_id,dependency_kind,day,source_kind,float(amount),max(0,min(100,float(reinforcing_value))),max(0,min(100,float(adverse_consequence))),source_ref_kind,source_ref_id,json.dumps(metadata or {},sort_keys=True)))
    pid=conn.execute("SELECT * FROM dependency_profiles WHERE actor_id=? AND dependency_kind=?",(actor_id,dependency_kind)).fetchone()
    load=float(amount)*(0.35+max(0,min(100,float(reinforcing_value)))/100.0)
    adverse=max(0,min(100,float(adverse_consequence)))
    if not pid:
        conn.execute("""INSERT INTO dependency_profiles(actor_id,dependency_kind,status,exposure_count,reinforcement_load,urge_load,tolerance_load,functional_impairment,consequence_load,last_exposure_day,last_review_day,next_review_day,metadata_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (actor_id,dependency_kind,'risk',1,load,min(100,load*3),min(100,load*1.5),min(100,adverse*0.2),adverse,day,day,day+30,json.dumps({},sort_keys=True)))
    else:
        count=int(pid['exposure_count'])+1
        reinforcement=float(pid['reinforcement_load'])+load
        urge=min(100,float(pid['urge_load'])+load*(2.0 if dependency_kind!='gambling' else 2.5))
        tolerance=min(100,float(pid['tolerance_load'])+load*(1.2 if dependency_kind in {'chemical_medication','intoxicant','stimulant'} else 0.45))
        consequences=min(100,float(pid['consequence_load'])+adverse)
        impairment=min(100,max(float(pid['functional_impairment']), consequences*0.35 + urge*0.18))
        status=str(pid['status'])
        # Exposure during recovery is a relapse signal, but one ordinary exposure is not automatically addiction.
        if status=='recovering': status='dependent' if urge>=28 or adverse>=35 else 'risk'
        elif status in {'risk','resolved'} and ((count>=3 and reinforcement>=8 and urge>=18) or adverse>=70): status='dependent'
        conn.execute("""UPDATE dependency_profiles SET status=?,exposure_count=?,reinforcement_load=?,urge_load=?,tolerance_load=?,functional_impairment=?,consequence_load=?,last_exposure_day=?,last_review_day=?,next_review_day=? WHERE id=?""",
                     (status,count,reinforcement,urge,tolerance,impairment,consequences,day,day,day+30,int(pid['id'])))
    _sync_dependency_pressure(conn,actor_id,dependency_kind)
    return int(cur.lastrowid)


def begin_dependency_recovery(conn: sqlite3.Connection, actor_id: int, dependency_kind: str, *, support_quality: float=50.0, metadata: dict[str,Any] | None=None) -> None:
    row=conn.execute("SELECT id,status,metadata_json FROM dependency_profiles WHERE actor_id=? AND dependency_kind=?",(actor_id,dependency_kind)).fetchone()
    if not row or str(row['status']) not in {'dependent','risk','recovering'}: raise ValueError('No active dependency state')
    m=_meta(row['metadata_json']); m['recovery_support_quality']=max(0,min(100,float(support_quality))); m['recovery_started_day']=_day(conn); m.update(metadata or {})
    conn.execute("UPDATE dependency_profiles SET status='recovering',metadata_json=?,next_review_day=? WHERE id=?",(json.dumps(m,sort_keys=True),_day(conn)+30,int(row['id'])))
    _sync_dependency_pressure(conn,actor_id,dependency_kind)


def record_psychological_stressor(conn: sqlite3.Connection, actor_id: int, stress_family: str, *, burden: float,
                                  source_kind: str, source_ref_kind: str | None=None, source_ref_id: int | None=None,
                                  metadata: dict[str,Any] | None=None) -> int:
    if stress_family not in PSYCH_FAMILIES: raise ValueError('Unknown psychological family')
    if not _living(conn,actor_id): raise ValueError('Psychological stressor requires living actor')
    if burden<=0: raise ValueError('Burden must be positive')
    if source_ref_kind and source_ref_id is not None:
        old=conn.execute("SELECT id FROM psychological_stressors WHERE actor_id=? AND stress_family=? AND source_ref_kind=? AND source_ref_id=?",(actor_id,stress_family,source_ref_kind,source_ref_id)).fetchone()
        if old: return int(old[0])
    cur=conn.execute("""INSERT INTO psychological_stressors(actor_id,stress_family,day,burden,source_kind,source_ref_kind,source_ref_id,metadata_json)
                       VALUES (?,?,?,?,?,?,?,?)""",(actor_id,stress_family,_day(conn),max(0,min(100,float(burden))),source_kind,source_ref_kind,source_ref_id,json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def record_psychological_support(conn: sqlite3.Connection, actor_id: int, *, condition_id: int | None=None,
                                 support_kind: str='family', helpfulness: float=50.0, metadata: dict[str,Any] | None=None) -> int:
    if not _living(conn,actor_id): raise ValueError('Support target must be living')
    if condition_id is not None:
        row=conn.execute("SELECT actor_id,status FROM psychological_conditions WHERE id=?",(condition_id,)).fetchone()
        if not row or int(row['actor_id'])!=actor_id or str(row['status']) not in {'active','recovering','chronic'}: raise ValueError('Invalid psychological condition')
    cur=conn.execute("INSERT INTO psychological_support(actor_id,condition_id,day,support_kind,helpfulness,metadata_json) VALUES (?,?,?,?,?,?)",(actor_id,condition_id,_day(conn),support_kind,max(-100,min(100,float(helpfulness))),json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def _ensure_condition_from_burden(conn: sqlite3.Connection, actor_id: int, family: str, day: int) -> bool:
    current=conn.execute("SELECT * FROM psychological_conditions WHERE actor_id=? AND condition_family=? AND status IN ('active','recovering','chronic') ORDER BY id DESC LIMIT 1",(actor_id,family)).fetchone()
    if current: return False
    row=conn.execute("SELECT COUNT(*),COALESCE(SUM(burden),0),MAX(burden) FROM psychological_stressors WHERE actor_id=? AND stress_family=? AND day>=?",(actor_id,family,day-365)).fetchone()
    count,total,maximum=int(row[0]),float(row[1]),float(row[2] or 0)
    # Ordinary distress is not automatically pathologized. Persistent state requires substantial or repeated burden.
    if not (maximum>=80 or (count>=2 and total>=95) or (count>=3 and total>=75)): return False
    severity=min(90,max(20,maximum*0.55+max(0,total-maximum)*0.20))
    impairment=min(80,max(8,severity*0.35))
    conn.execute("""INSERT INTO psychological_conditions(actor_id,condition_family,severity,functional_impairment,status,onset_day,last_review_day,next_review_day,metadata_json)
                    VALUES (?,?,?,?,'active',?,?,?,?)""",(actor_id,family,severity,impairment,day,day,day+30,json.dumps({'source':'accumulated_stressors'},sort_keys=True)))
    _sync_psych_pressure(conn,actor_id,family)
    return True


def _ingest_elixir_exposures(conn: sqlite3.Connection) -> int:
    rows=conn.execute("""SELECT e.* FROM elixir_exposures e
                         LEFT JOIN dependency_exposures d ON d.source_ref_kind='elixir_exposure' AND d.source_ref_id=e.id AND d.dependency_kind='elixir_performance'
                         WHERE d.id IS NULL ORDER BY e.id""").fetchall()
    n=0
    for e in rows:
        # Elixir is explicitly not chemically addictive. Repeated reliance may create performance dependence.
        record_dependency_exposure(conn,int(e['actor_id']),'elixir_performance',source_kind='cultivation_fuel',amount=max(0.25,float(e['units_consumed'])),reinforcing_value=min(90,35+float(e['reserve_gain'])*4),adverse_consequence=min(100,float(e['sediment_gain'])*12),source_ref_kind='elixir_exposure',source_ref_id=int(e['id']),metadata={'chemical_addiction':False})
        n+=1
    return n


def _ingest_severe_health_stressors(conn: sqlite3.Connection) -> int:
    rows=conn.execute("""SELECT h.* FROM health_conditions h
                         LEFT JOIN psychological_stressors p ON p.source_ref_kind='health_condition' AND p.source_ref_id=h.id AND p.stress_family='trauma'
                         WHERE p.id IS NULL AND h.severity>=75 AND h.status IN ('active','recovering','chronic','resolved') ORDER BY h.id""").fetchall()
    n=0
    for h in rows:
        if not _living(conn,int(h['actor_id'])): continue
        burden=min(100,max(10,(float(h['severity'])-60)*1.15 + float(h['pain_impact'])*0.25))
        record_psychological_stressor(conn,int(h['actor_id']),'trauma',burden=burden,source_kind='severe_injury_or_illness',source_ref_kind='health_condition',source_ref_id=int(h['id']),metadata={'label':str(h['label'])})
        n+=1
    return n


def _ingest_bereavement(conn: sqlite3.Connection) -> int:
    rows=conn.execute("""SELECT r.actor_a_id living_id,r.actor_b_id deceased_id,r.trust,r.affection,r.obligation,lp.last_review_day AS death_day
                         FROM relationships r
                         JOIN actor_life_profiles alp ON alp.actor_id=r.actor_a_id
                         JOIN actor_life_profiles lp ON lp.actor_id=r.actor_b_id
                         LEFT JOIN psychological_stressors p ON p.actor_id=r.actor_a_id AND p.source_ref_kind='bereavement_actor' AND p.source_ref_id=r.actor_b_id AND p.stress_family='grief'
                         WHERE alp.life_status='living' AND lp.life_status='deceased' AND lp.last_review_day IS NOT NULL AND p.id IS NULL
                           AND (r.trust>=55 OR r.affection>=55 OR r.obligation>=55)""").fetchall()
    n=0
    for r in rows:
        burden=min(75,max(20,(float(r['trust'])+float(r['affection'])+float(r['obligation']))*0.20))
        record_psychological_stressor(conn,int(r['living_id']),'grief',burden=burden,source_kind='bereavement',source_ref_kind='bereavement_actor',source_ref_id=int(r['deceased_id']),metadata={'death_day':int(r['death_day'])})
        n+=1
    return n

def next_psych_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals=[]
    for table in ('dependency_profiles','psychological_conditions'):
        row=conn.execute(f"SELECT MIN(next_review_day) FROM {table} WHERE status IN ('risk','dependent','recovering','chronic','active') AND next_review_day>? AND next_review_day<=?",(after_day,end_day)).fetchone()
        if row and row[0] is not None: vals.append(int(row[0]))
    # A monthly catch-up lets newly created concrete source events be ingested without creating conditions from nothing.
    month=((after_day//30)+1)*30
    if month<=end_day: vals.append(month)
    return min(vals) if vals else None


def process_due_psychology(conn: sqlite3.Connection, day: int, *, event_logger: Callable[...,int] | None=None) -> dict[str,int]:
    ingested=_ingest_elixir_exposures(conn)+_ingest_severe_health_stressors(conn)+_ingest_bereavement(conn)
    created=0; dep_reviewed=0; psych_reviewed=0; resolved=0
    # Convert only accumulated substantial stress into persistent psychological state.
    pairs=conn.execute("SELECT DISTINCT actor_id,stress_family FROM psychological_stressors WHERE day<=?",(day,)).fetchall()
    for p in pairs:
        if _ensure_condition_from_burden(conn,int(p['actor_id']),str(p['stress_family']),day): created+=1

    deps=conn.execute("SELECT * FROM dependency_profiles WHERE status IN ('risk','dependent','recovering') AND next_review_day<=? ORDER BY id",(day,)).fetchall()
    for d in deps:
        dep_reviewed+=1; status=str(d['status']); urge=float(d['urge_load']); tol=float(d['tolerance_load']); impairment=float(d['functional_impairment']); consequences=float(d['consequence_load'])
        days_since=max(0,day-int(d['last_exposure_day'] or day)); quiet=max(0.0,min(1.0,days_since/90.0))
        m=_meta(d['metadata_json']); support=float(m.get('recovery_support_quality',0.0))
        if status=='recovering':
            reduction=4.0+support*0.08+quiet*5
            urge=max(0,urge-reduction); impairment=max(0,impairment-reduction*0.65); consequences=max(0,consequences-reduction*0.25); tol=max(0,tol-reduction*0.35)
            if urge<8 and impairment<5 and days_since>=90: status='resolved'; resolved+=1
        elif status=='dependent' and days_since>=90:
            # Spontaneous improvement is possible but slow; support accelerates it. No cultivation cure.
            urge=max(0,urge-(1.5+quiet*2)); impairment=max(0,impairment-1.0)
        elif status=='risk' and days_since>=120:
            urge=max(0,urge-4); tol=max(0,tol-2)
            if urge<5: status='resolved'; resolved+=1
        conn.execute("UPDATE dependency_profiles SET status=?,urge_load=?,tolerance_load=?,functional_impairment=?,consequence_load=?,last_review_day=?,next_review_day=? WHERE id=?",(status,urge,tol,impairment,consequences,day,day+30,int(d['id'])))
        _sync_dependency_pressure(conn,int(d['actor_id']),str(d['dependency_kind']))

    conds=conn.execute("SELECT * FROM psychological_conditions WHERE status IN ('active','recovering','chronic') AND next_review_day<=? ORDER BY id",(day,)).fetchall()
    for p in conds:
        psych_reviewed+=1; severity=float(p['severity']); impairment=float(p['functional_impairment']); status=str(p['status'])
        sr=conn.execute("SELECT COALESCE(SUM(helpfulness),0),COUNT(*) FROM psychological_support WHERE actor_id=? AND (condition_id=? OR condition_id IS NULL) AND day>=? AND day<=?",(int(p['actor_id']),int(p['id']),int(p['last_review_day']),day)).fetchone()
        helpful=float(sr[0] or 0); reduction=max(-8,min(12,helpful/35.0))
        if reduction>0: status='recovering'
        severity=max(0,min(100,severity-reduction)); impairment=max(0,min(100,impairment-reduction*0.7))
        if severity<10 and impairment<6: status='resolved'; resolved+=1
        elif severity>=65 and day-int(p['onset_day'])>=365: status='chronic'
        conn.execute("UPDATE psychological_conditions SET severity=?,functional_impairment=?,status=?,last_review_day=?,next_review_day=?,resolved_day=CASE WHEN ?='resolved' THEN ? ELSE resolved_day END WHERE id=?",(severity,impairment,status,day,day+30,status,day,int(p['id'])))
        _sync_psych_pressure(conn,int(p['actor_id']),str(p['condition_family']))
    return {'ingested_sources':ingested,'conditions_created':created,'dependency_reviews':dep_reviewed,'psych_reviews':psych_reviewed,'resolved':resolved}


def psychology_summary(conn: sqlite3.Connection) -> dict[str,int]:
    return {
        'dependency_profiles':int(conn.execute("SELECT COUNT(*) FROM dependency_profiles").fetchone()[0]),
        'active_dependencies':int(conn.execute("SELECT COUNT(*) FROM dependency_profiles WHERE status IN ('dependent','recovering')").fetchone()[0]),
        'dependency_exposures':int(conn.execute("SELECT COUNT(*) FROM dependency_exposures").fetchone()[0]),
        'psychological_stressors':int(conn.execute("SELECT COUNT(*) FROM psychological_stressors").fetchone()[0]),
        'active_psychological_conditions':int(conn.execute("SELECT COUNT(*) FROM psychological_conditions WHERE status IN ('active','recovering','chronic')").fetchone()[0]),
    }
```

## engine/texture.py

```python
"""The push and the delivery ledger (information phase 1a, spec 7.3).

Every scene, advance and resume carries a texture block: bearing, the room read, what he reads in the others there, and the news
that reaches him (about himself and about other people, through his habits and his people). Nothing here waits to be asked.

The ledger keeps what has been delivered. A happening that reaches him is entered once; an item not yet delivered is returned again on
the next call; a delivered one is never repeated. How much one call carries follows the weight of what is waiting
(its significance, growing as it waits): there is no threshold between "full wave" and "nothing", and no tier table. Where the package
sets how long news stays news, what has waited longer (other than what concerns him) is dropped; where people have ordinary-life
matters, news of others comes from someone he knows (or a habit of his), or not at all.
"""
from __future__ import annotations

import sqlite3

from . import bearing as B
from .design import figure, run_seed  # noqa: F401  (run_seed kept for streams)


def enabled(conn: sqlite3.Connection) -> bool:
    return B.enabled(conn)


def _like(text: str) -> str:
    return "%" + text.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def _clip(text, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def circle(conn, me: int) -> dict[int, float]:
    """The people close to him and how close: kin, household, the men above and below him, workmates, friends, people he knows
    and people he has money open with."""
    out: dict[int, float] = {}

    def put(i, w):
        if i is not None and int(i) != me and w > out.get(int(i), 0.0):
            out[int(i)] = w
    for a, b in conn.execute("SELECT actor_a_id,actor_b_id FROM kinship_links WHERE (actor_a_id=? OR actor_b_id=?) AND ended_day IS NULL", (me, me)):
        put(b if int(a) == me else a, 1.0)
    for (i,) in conn.execute("SELECT actor_id FROM household_members WHERE status='active' AND household_id IN "
                             "(SELECT household_id FROM household_members WHERE actor_id=? AND status='active')", (me,)):
        put(i, 0.8)
    for s in B.seats(conn, me):
        put(s["superior_actor_id"], 0.6)
    for (i,) in conn.execute("SELECT actor_id FROM org_seats WHERE superior_actor_id=? AND status='active'", (me,)):
        put(i, 0.6)
    for m in conn.execute("SELECT ref_actor_id FROM bearing_marks WHERE actor_id=? AND kind='retinue' AND status='active'", (me,)):
        put(m[0], 0.6)
    for i, f in conn.execute("SELECT actor_b_id,familiarity FROM relationships WHERE actor_a_id=? AND familiarity>=20", (me,)):
        put(i, 0.5 * float(f) / 100.0)
    from . import life_matters
    if life_matters.enabled(conn):
        for i, w in life_matters.contacts(conn, me).items():
            put(i, min(w, 0.7))
        for (i,) in conn.execute("""SELECT b.actor_id FROM enterprise_staff a JOIN enterprise_staff b ON b.enterprise_id=a.enterprise_id
                                    WHERE a.actor_id=? AND a.status='active' AND b.status='active'
                                    UNION SELECT e.owner_actor_id FROM enterprise_staff a JOIN civilian_enterprises e ON e.id=a.enterprise_id
                                    WHERE a.actor_id=? AND a.status='active'
                                    UNION SELECT s.actor_id FROM civilian_enterprises e JOIN enterprise_staff s ON s.enterprise_id=e.id
                                    WHERE e.owner_actor_id=? AND s.status='active'""", (me, me, me)).fetchall():
            put(i, 0.6)
        mine = f"person:{me}"
        for a, b in conn.execute("SELECT customer_ref,provider_ref FROM deals WHERE status='open' AND (customer_ref=? OR provider_ref=?)", (mine, mine)):
            kind, _, raw = str(b if a == mine else a).partition(":")
            if kind == "person":
                put(int(raw), 0.6)
    return out


def _cursor(conn, me: int):
    r = conn.execute("SELECT * FROM texture_cursor WHERE viewer_actor_id=?", (me,)).fetchone()
    if r is None:
        mk = conn.execute("SELECT COALESCE(MAX(id),0) FROM knowledge").fetchone()[0]
        me_ = conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
        mr = conn.execute("SELECT COALESCE(MAX(id),0) FROM rumours").fetchone()[0]
        conn.execute("INSERT INTO texture_cursor(viewer_actor_id,knowledge_id,event_id,rumour_id) VALUES (?,?,?,?)", (me, mk, me_, mr))
        return None
    return r


def _violent(conn, event_type: str) -> bool:
    return any(w in str(event_type).lower() for w in B.data(conn).get("violent_event_types") or [])


def _significance(conn, me, circ, *, public: bool, severity: int, ids, event_type: str = "", mentions_him: bool = False) -> float:
    close = max((circ.get(i, 0.0) for i in ids), default=0.0)
    him = mentions_him or me in ids
    return (B.fig(conn, "sig_base") + (B.fig(conn, "sig_public") if public else 0.0) + B.fig(conn, "sig_sev") * severity
            + (B.fig(conn, "sig_him") if him else 0.0) + B.fig(conn, "sig_circle") * close
            + (B.fig(conn, "sig_violent") if _violent(conn, event_type) else 0.0))


def _via(conn, kind: str, key: str, habit: str | None) -> str:
    words = (B.data(conn).get("channels") or {}).get(kind) or []
    if kind == "read" and habit:
        return habit
    return words[sum(map(ord, key)) % len(words)] if words else kind


def _bringer(conn, me: int, circ: dict[int, float], ids: set[int], known: dict, place: int | None = None) -> str | None:
    """Who of the people he knows brings him this: one it happened to, one who knows them, or (for talk where he is) one who is
    there. The words saying so, or None when nobody does. `known` is filled once and shared by the items of one call."""
    from . import hearsay, life_matters
    near = {i: circ[i] for i in ids if i in circ}
    if not near and ids:
        if "by" not in known:
            known["by"] = life_matters.known_by(conn, sorted(circ))
        near = {c: circ[c] for i in ids for c in known["by"].get(i, {})}
    if not near and place is not None and circ:
        marks = ",".join("?" * len(circ))
        for (i,) in conn.execute(f"SELECT id FROM actors WHERE current_location_id=? AND id IN ({marks})", (place, *sorted(circ))):
            near[int(i)] = circ[int(i)]
    return hearsay.via(conn, me, max(sorted(near), key=near.get)) if near else None


def _enter(conn, me, key, kind, text, via, sig, day) -> None:
    conn.execute("INSERT OR IGNORE INTO delivery_ledger(viewer_actor_id,item_key,kind,text,via,significance,first_day) VALUES (?,?,?,?,?,?,?)",
                 (me, key, kind, _clip(text, 170), via, float(sig), day))


def ingest(conn, me: int, place: int | None, day: int) -> None:
    """Enter what has reached him since the last call: what he learned, public happenings that reach him through his habits and
    his people, talk running where he is, and what came home. Each is entered once (the ledger key); the cursor only saves the scan."""
    cur = _cursor(conn, me)
    if cur is None:
        return
    circ = circle(conn, me)
    my_name = B.name_of(conn, me)
    habit = conn.execute("SELECT text FROM bearing_marks WHERE actor_id=? AND kind='habit' AND status='active' ORDER BY id DESC LIMIT 1", (me,)).fetchone()
    habit = str(habit[0]) if habit else None
    from . import life_matters
    named = life_matters.enabled(conn)  # here news comes from a person he knows (or a habit of his), or not at all
    known: dict = {}
    # what he learned (about himself and about others)
    for k in conn.execute("SELECT id,fact_key,belief_text,truth_event_id,learned_day FROM knowledge WHERE knower_actor_id=? AND id>? ORDER BY id", (me, cur["knowledge_id"])).fetchall():
        if str(k["fact_key"]).startswith("step:"):  # another's life, brought by someone: the row says who
            from . import hearsay
            step, carrier = hearsay.parse(conn, k["fact_key"])
            if step is None:
                continue
            ids = {int(x) for x in str(step["actors"]).split(",") if x}
            sig = _significance(conn, me, circ, public=False, severity=int(figure(conn, "lm_news_weight")), ids=ids)
            _enter(conn, me, k["fact_key"], "about_him" if me in ids else "news", k["belief_text"], hearsay.via(conn, me, carrier), sig, int(k["learned_day"]))
            continue
        ev = conn.execute("SELECT e.event_type,e.severity,e.source_actor_id,ei.visibility FROM events e LEFT JOIN event_information ei ON ei.event_id=e.id WHERE e.id=?",
                          (int(k["truth_event_id"]),)).fetchone() if k["truth_event_id"] is not None else None
        ids = {int(r[0]) for r in conn.execute("SELECT actor_id FROM event_targets WHERE event_id=?", (int(k["truth_event_id"]),))} if ev else set()
        if ev and ev["source_actor_id"] is not None:
            ids.add(int(ev["source_actor_id"]))
        key = f"event:{k['truth_event_id']}" if ev else f"knowledge:{k['id']}"
        kind = "about_him" if me in ids or my_name in str(k["belief_text"]) else "news"
        sig = _significance(conn, me, circ, public=bool(ev and ev["visibility"] == "public"), severity=int(ev["severity"]) if ev else 1, ids=ids,
                            event_type=str(ev["event_type"]) if ev else "", mentions_him=my_name in str(k["belief_text"]))
        via = _via(conn, "told", key, None)
        if named and kind == "news" and ids and not conn.execute("SELECT 1 FROM event_witnesses WHERE event_id=? AND actor_id=?",
                                                                 (int(k["truth_event_id"]), me)).fetchone():
            via = _bringer(conn, me, circ, ids, known)
            if via is None:
                continue
        _enter(conn, me, key, kind, k["belief_text"], via, sig, int(k["learned_day"]))
    # public happenings that reach him through his habits and his people
    for e in conn.execute("""SELECT e.id,e.day,e.event_type,e.title,e.summary,e.severity,e.source_actor_id FROM events e JOIN event_information ei ON ei.event_id=e.id
                             WHERE e.id>? AND ei.visibility='public' ORDER BY e.id""", (cur["event_id"],)).fetchall():
        ids = {int(r[0]) for r in conn.execute("SELECT actor_id FROM event_targets WHERE event_id=?", (int(e["id"]),))}
        if e["source_actor_id"] is not None:
            ids.add(int(e["source_actor_id"]))
        close = max((circ.get(i, 0.0) for i in ids), default=0.0)
        score = (B.fig(conn, "reach_base") + B.fig(conn, "reach_public") + B.fig(conn, "reach_sev") * int(e["severity"]) + B.fig(conn, "reach_circle") * close
                 + (B.fig(conn, "reach_habit") if habit else 0.0)) + (1.0 if me in ids else 0.0)
        if B._rng(conn, "reach", me, e["id"]).random() >= score:
            continue
        key = f"event:{e['id']}"
        sig = _significance(conn, me, circ, public=True, severity=int(e["severity"]), ids=ids, event_type=str(e["event_type"]))
        via = _via(conn, "read", key, habit)
        if named and not habit and me not in ids:
            via = _bringer(conn, me, circ, ids, known)
            if via is None:
                continue
        _enter(conn, me, key, "about_him" if me in ids else "news", f"{e['title']}: {e['summary']}" if e["summary"] and e["summary"] != e["title"] else e["title"],
               via, sig, int(e["day"]))
    # talk running where he is
    if place is not None:
        for r in conn.execute("""SELECT r.id,r.text,r.truth_event_id,rl.prevalence FROM rumours r JOIN rumour_locations rl ON rl.rumour_id=r.id AND rl.location_id=?
                                 WHERE r.id>? AND r.status='circulating' ORDER BY r.id""", (place, cur["rumour_id"])).fetchall():
            if r["truth_event_id"] is not None and conn.execute("SELECT 1 FROM delivery_ledger WHERE viewer_actor_id=? AND item_key=?", (me, f"event:{r['truth_event_id']}")).fetchone():
                continue
            key = f"rumour:{r['id']}"
            sig = B.fig(conn, "sig_base") + B.fig(conn, "sig_public") * float(r["prevalence"]) + (B.fig(conn, "sig_him") if my_name in str(r["text"]) else 0.0)
            via = _bringer(conn, me, circ, set(), known, place) if named else _via(conn, "talk", key, None)
            if via is not None:
                _enter(conn, me, key, "talk", r["text"], via, sig, day)
    # what came home: his own people hearing of him
    kin = [i for i, w in circ.items() if w >= 0.8]
    if kin:
        for k in conn.execute(f"SELECT id,knower_actor_id,belief_text FROM knowledge WHERE id>? AND knower_actor_id IN ({','.join('?' * len(kin))}) AND belief_text LIKE ? ESCAPE '!'",
                              (cur["knowledge_id"], *kin, _like(my_name))).fetchall():
            key = f"home:{k['id']}"
            _enter(conn, me, key, "home", f"{B.name_of(conn, k['knower_actor_id'])}: {k['belief_text']}", _via(conn, "home", key, None),
                   B.fig(conn, "sig_base") + B.fig(conn, "sig_him") + B.fig(conn, "sig_circle"), day)
    from . import claims
    if claims.enabled(conn):  # his people's days, and what others tell him of himself
        for key, kind, text in claims.deliveries(conn, me, day):
            _enter(conn, me, key, kind, text, _via(conn, "home", key, None), B.fig(conn, "sig_base") + B.fig(conn, "sig_him") + B.fig(conn, "sig_circle"), day)
    mk = conn.execute("SELECT COALESCE(MAX(id),0) FROM knowledge").fetchone()[0]
    me_ = conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
    mr = conn.execute("SELECT COALESCE(MAX(id),0) FROM rumours").fetchone()[0]
    conn.execute("UPDATE texture_cursor SET knowledge_id=?,event_id=?,rumour_id=? WHERE viewer_actor_id=?", (mk, me_, mr, me))


def deliver(conn, me: int, day: int) -> list[dict]:
    """What waits, heaviest first, until the call's attention is used (always at least the heaviest). What is not taken stays
    pending and grows heavier each day it waits; what is taken is marked delivered and never returned."""
    stale = figure(conn, "news_stale_days")
    if stale:  # what has gone round too long without reaching him is no longer news
        conn.execute("DELETE FROM delivery_ledger WHERE viewer_actor_id=? AND delivered_day IS NULL AND kind<>'about_him' AND first_day<?",
                     (me, day - int(stale)))
    rows = conn.execute("SELECT * FROM delivery_ledger WHERE viewer_actor_id=? AND delivered_day IS NULL", (me,)).fetchall()
    gain = B.fig(conn, "push_age_gain")
    weighed = sorted(rows, key=lambda r: -(float(r["significance"]) * (1.0 + gain * max(0, day - int(r["first_day"])))))
    budget, used, out = B.fig(conn, "push_attention"), 0.0, []
    for r in weighed:
        w = float(r["significance"]) * (1.0 + gain * max(0, day - int(r["first_day"])))
        if out and used + w > budget:
            break
        used += w
        conn.execute("UPDATE delivery_ledger SET delivered_day=?,delivered_count=delivered_count+1 WHERE id=?", (day, int(r["id"])))
        ago = day - int(r["first_day"])
        out.append({k: v for k, v in {"what": r["text"], "via": r["via"], "kind": r["kind"], "days_ago": ago if ago > 0 else None}.items() if v is not None})
    return out


def pending_count(conn, me: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM delivery_ledger WHERE viewer_actor_id=? AND delivered_day IS NULL", (me,)).fetchone()[0])


def shown(conn, me: int, limit: int = 12) -> list[dict]:
    """The ledger of what he has been shown (for lookup), newest first."""
    return [{"what": r["text"], "via": r["via"], "when": r["delivered_day"]} for r in conn.execute(
        "SELECT text,via,delivered_day FROM delivery_ledger WHERE viewer_actor_id=? AND delivered_day IS NOT NULL ORDER BY delivered_day DESC,id DESC LIMIT ?", (me, limit))]


def block(conn, me: int, place: int | None, people: list[int], *, news: bool = True) -> dict | None:
    """The texture block for the protagonist's situation. None when the world's package supplies no presence data (nothing is added).
    `people` are the notable people in the scene. Commits nothing."""
    if not enabled(conn):
        return None
    day = B._day(conn)
    mine = B.bearing(conn, me)
    bear = {"retinue": [r["text"] for r in mine["retinue"]] or None, "signals": [s["text"] + (" (beyond his means)" if s.get("beyond_means") else "") for s in mine["signals"]] or None,
            "spending": mine["spending"]}
    forms_used: set[str] = set()
    room = []
    for p in people:
        if int(p) == me:
            continue
        rr = B.room_read(conn, me, int(p))
        shows = []
        if rr.get("placed"):
            due = B.forms_due(conn, me, int(p))
            shows = [f["key"] for f in due if B.form_known(conn, int(p), f)]
        entry = {"id": int(p), "name": B.name_of(conn, p), "toward_him": rr.get("stance"), "from": rr["from"], "sure": rr["sure"], "changed": rr.get("changed"),
                 "holds": rr.get("holds"), "reads_him_as": rr.get("reads_him_as")}
        if shows:
            entry["shows"] = shows
            forms_used.update(shows)
            if any(w in str(rr.get("stance") or "") for w in ("resents", "contemptuous")):
                entry["manner"] = "sullen, thin"
        room.append({k: v for k, v in entry.items() if v is not None})
    reads, hidden = [], []
    for p in people:
        if int(p) == me:
            continue
        r = B.reads_of(conn, me, int(p))
        read = r["read"]
        if len(read) > 3 or read.get("forms_he_knows") or read.get("forms_he_is_unsure_of"):
            reads.append(read)
            forms_used.update(read.get("forms_he_knows") or []); forms_used.update(read.get("forms_he_is_unsure_of") or [])
        if r["hidden"]:
            hidden.append(r["hidden"])
            forms_used.update(r["hidden"]["due"])
    out: dict = {"bearing": {k: v for k, v in bear.items() if v}}
    if room:
        out["room"] = room
    if reads:
        out["he_reads"] = reads
    if forms_used:
        out["form_text"] = B.form_text(conn, forms_used)
    if news:
        ingest(conn, me, place, day)
        items = deliver(conn, me, day)
        if items:
            out["news"] = items
        waiting = pending_count(conn, me)
        if waiting:
            out["more_waiting"] = waiting
    if news:
        from . import claims
        if claims.enabled(conn):
            hidden += claims.cutaways(conn, me, day)
    if hidden:
        out["outside_his_knowledge"] = hidden
    todo = B.unrecorded(conn, me)
    if todo:
        out["to_record"] = todo
    return out
```

## engine/emergence.py

```python
from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class EmergenceSignal:
    kind: str
    source_id: int
    actor_id: int | None
    thread_id: int | None
    significance: float
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tokenize(text: str) -> set[str]:
    stop = {
        "the", "and", "that", "this", "with", "from", "into", "over", "under", "after", "before",
        "their", "they", "them", "while", "where", "when", "about", "through", "because", "between",
        "actor", "event", "day", "caerness", "player", "routine", "during", "against", "toward", "towards",
    }
    return {w for w in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", text.lower()) if w not in stop}


def remember(
    conn: sqlite3.Connection,
    actor_id: int,
    *,
    memory_key: str,
    summary: str,
    source_kind: str,
    source_id: int,
    day: int,
    subject_actor_id: int | None = None,
    interpretation: str | None = None,
    valence: float = 0.0,
    significance: float = 0.5,
) -> int:
    significance = max(0.0, min(1.0, float(significance)))
    valence = max(-1.0, min(1.0, float(valence)))
    existing = conn.execute(
        "SELECT id,significance FROM actor_memories WHERE actor_id=? AND memory_key=?",
        (actor_id, memory_key),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE actor_memories SET summary=?,interpretation=COALESCE(?,interpretation),
                   valence=?,significance=MAX(significance,?),last_reinforced_day=?,status='active'
               WHERE id=?""",
            (summary, interpretation, valence, significance, day, int(existing["id"])),
        )
        return int(existing["id"])
    cur = conn.execute(
        """INSERT INTO actor_memories(
               actor_id,subject_actor_id,memory_key,summary,interpretation,valence,significance,
               source_kind,source_id,created_day,last_reinforced_day,status
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'active')""",
        (
            actor_id, subject_actor_id, memory_key, summary, interpretation, valence, significance,
            source_kind, source_id, day, day,
        ),
    )
    return int(cur.lastrowid)


def ingest_event(conn: sqlite3.Connection, event_id: int) -> list[EmergenceSignal]:
    """Turn consequences into durable actor memory and evidence for existing threads.

    This does not invent plot beats. It recognizes relationships among facts that already
    happened, so later decisions can remember them and the UI can make causal continuity legible.
    """
    event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not event:
        return []
    day = int(event["day"])
    severity = int(event["severity"])
    source_actor_id = int(event["source_actor_id"]) if event["source_actor_id"] is not None else None
    targets = [int(r[0]) for r in conn.execute("SELECT actor_id FROM event_targets WHERE event_id=?", (event_id,)).fetchall()]
    signals: list[EmergenceSignal] = []
    significance = min(1.0, 0.18 + severity * 0.15)

    involved: set[int] = set(targets)
    if source_actor_id is not None:
        involved.add(source_actor_id)
    for actor_id in involved:
        subject = None
        if source_actor_id is not None and actor_id != source_actor_id:
            subject = source_actor_id
        elif targets:
            other = next((a for a in targets if a != actor_id), None)
            subject = other
        key = f"event:{event_id}"
        mid = remember(
            conn, actor_id,
            memory_key=key,
            summary=str(event["summary"]),
            source_kind="event",
            source_id=event_id,
            day=day,
            subject_actor_id=subject,
            significance=significance,
        )
        signals.append(EmergenceSignal("memory", event_id, actor_id, None, significance, f"Actor #{actor_id} retains event #{event_id} as memory #{mid}."))

    # Attach the event to any already-active thread that shares location or participants.
    thread_rows = conn.execute(
        "SELECT id,title,location_id,severity,notes FROM threads WHERE status='active' ORDER BY updated_day DESC,id"
    ).fetchall()
    event_tokens = _tokenize(f"{event['title']} {event['summary']}")
    for thread in thread_rows:
        score = 0.0
        if event["location_id"] is not None and thread["location_id"] == event["location_id"]:
            score += 0.25
        linked_actors = {
            int(r[0]) for r in conn.execute("SELECT actor_id FROM thread_actors WHERE thread_id=?", (thread["id"],)).fetchall()
        }
        if linked_actors & involved:
            score += 0.45
        thread_tokens = _tokenize(f"{thread['title']} {thread['notes'] or ''}")
        if thread_tokens and event_tokens:
            overlap = len(thread_tokens & event_tokens) / max(1, min(len(thread_tokens), len(event_tokens)))
            score += min(0.35, overlap * 0.45)
        if score >= 0.45:
            conn.execute(
                """INSERT OR IGNORE INTO thread_evidence(thread_id,source_kind,source_id,relevance,day,note)
                   VALUES (?,'event',?,?,?,?)""",
                (int(thread["id"]), event_id, min(1.0, score), day, f"Recognized from event: {event['title']}"),
            )
            conn.execute(
                "UPDATE threads SET updated_day=?,progress=MIN(100,progress+?) WHERE id=?",
                (day, max(0.5, score * severity), int(thread["id"])),
            )
            signals.append(EmergenceSignal("thread_evidence", event_id, None, int(thread["id"]), min(1.0, score), f"Event #{event_id} reinforces {thread['title']}."))

    # If several recent, related severe events recur around the same actors/location without an
    # existing thread, create a neutral 'developing situation' thread. This is recognition, not a plot.
    if severity >= 3:
        recent = conn.execute(
            """SELECT e.* FROM events e
               WHERE e.id<>? AND e.day BETWEEN ? AND ? AND e.severity>=2
                 AND (e.location_id IS ? OR e.source_actor_id IS ?)
               ORDER BY e.day DESC,e.id DESC LIMIT 12""",
            (event_id, max(0, day - 45), day, event["location_id"], source_actor_id),
        ).fetchall()
        related = []
        for other in recent:
            otoks = _tokenize(f"{other['title']} {other['summary']}")
            overlap = len(event_tokens & otoks)
            if overlap >= 2 or (event["location_id"] is not None and other["location_id"] == event["location_id"]):
                related.append(other)
        if len(related) >= 2:
            already = False
            for thread in thread_rows:
                if event["location_id"] is not None and thread["location_id"] == event["location_id"]:
                    already = True
                    break
                linked = {int(r[0]) for r in conn.execute("SELECT actor_id FROM thread_actors WHERE thread_id=?", (thread["id"],)).fetchall()}
                if linked & involved:
                    already = True
                    break
            if not already:
                title = f"Developing situation: {event['title']}"
                cur = conn.execute(
                    """INSERT INTO threads(title,scope,status,progress,severity,location_id,created_day,updated_day,notes)
                       VALUES (?,'emergent','active',?,?,?, ?,?,?)""",
                    (title, min(100.0, 10 + severity * 4), min(5, severity), event["location_id"], day, day,
                     "Automatically recognized from recurring consequences; no predetermined resolution."),
                )
                thread_id = int(cur.lastrowid)
                for actor_id in involved:
                    conn.execute("INSERT OR IGNORE INTO thread_actors(thread_id,actor_id,role) VALUES (?,?,?)", (thread_id, actor_id, "involved"))
                ids = [event_id] + [int(r["id"]) for r in related[:4]]
                for eid in ids:
                    eday = int(conn.execute("SELECT day FROM events WHERE id=?", (eid,)).fetchone()[0])
                    conn.execute(
                        "INSERT OR IGNORE INTO thread_evidence(thread_id,source_kind,source_id,relevance,day,note) VALUES (?,'event',?,?,?,?)",
                        (thread_id, eid, 0.65 if eid == event_id else 0.5, eday, "Recurring causal evidence"),
                    )
                signals.append(EmergenceSignal("thread_created", event_id, None, thread_id, significance, title))

    return signals


def important_memories(conn: sqlite3.Connection, actor_id: int, limit: int = 12) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT m.*,s.name subject_name FROM actor_memories m
           LEFT JOIN actors s ON s.id=m.subject_actor_id
           WHERE m.actor_id=? AND m.status='active'
           ORDER BY m.significance DESC,m.last_reinforced_day DESC,m.id DESC LIMIT ?""",
        (actor_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def active_emergent_threads(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT t.*,l.name location_name,
                  (SELECT COUNT(*) FROM thread_evidence te WHERE te.thread_id=t.id) evidence_count
           FROM threads t LEFT JOIN locations l ON l.id=t.location_id
           WHERE t.status='active' ORDER BY t.severity DESC,t.updated_day DESC,t.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
```

## engine/attention.py

```python
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .interactions import create_interaction


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def _government_actor(conn: sqlite3.Connection, polity_id: int) -> int | None:
    row = conn.execute("SELECT decision_actor_id FROM polity_government_actors WHERE polity_id=?", (polity_id,)).fetchone()
    return int(row[0]) if row else None


def _local_polity(conn: sqlite3.Connection, location_id: int | None) -> sqlite3.Row | None:
    if location_id is None:
        return None
    return conn.execute(
        """SELECT p.*,a.name institution_name FROM locations l
           JOIN actors a ON a.name=l.political_owner
           JOIN political_polities p ON p.institution_actor_id=a.id
           WHERE l.id=? AND p.status!='dissolved' LIMIT 1""",
        (int(location_id),),
    ).fetchone()


def create_attention_case(
    conn: sqlite3.Connection,
    observer_actor_id: int,
    target_actor_id: int,
    domain_key: str,
    interest_kind: str,
    *,
    observer_institution_actor_id: int | None = None,
    salience: float = 50,
    source_kind: str | None = None,
    source_id: int | None = None,
    expires_in_days: int | None = 365,
    metadata: dict[str, Any] | None = None,
) -> int:
    day = _day(conn)
    existing = conn.execute(
        """SELECT id FROM strategic_attention_cases
           WHERE observer_actor_id=? AND target_actor_id=? AND domain_key=? AND interest_kind=?
             AND status IN ('observing','planning','approaching')
           ORDER BY id LIMIT 1""",
        (observer_actor_id, target_actor_id, domain_key, interest_kind),
    ).fetchone()
    if existing:
        return int(existing[0])
    cur = conn.execute(
        """INSERT INTO strategic_attention_cases(
               observer_actor_id,observer_institution_actor_id,target_actor_id,domain_key,interest_kind,salience,status,
               source_kind,source_id,created_day,last_review_day,next_review_day,expires_day,metadata_json
           ) VALUES (?,?,?,?,?,?,'observing',?,?,?,?,?,?,?)""",
        (
            observer_actor_id, observer_institution_actor_id, target_actor_id, domain_key, interest_kind,
            max(0.0, min(100.0, float(salience))), source_kind, source_id, day, day, day + 7,
            None if expires_in_days is None else day + int(expires_in_days), _j(metadata or {}),
        ),
    )
    return int(cur.lastrowid)


def ensure_horse_breeder_attention(conn: sqlite3.Connection, day: int | None = None) -> int:
    """Let governments notice strategically important horse breeders, not merely buy from them.

    This is one domain provider for ATTENTION-01.  The shared layer owns relevance/approach state;
    the domain provider decides what horse-breeding excellence can mean to a polity.  It does not
    imply that every successful breeder receives office, and it does not require the breeder to
    publish a SEEK offering first.
    """
    day = _day(conn) if day is None else int(day)
    rows = conn.execute(
        """SELECT e.id enterprise_id,e.owner_actor_id,e.institution_actor_id,e.location_id,e.reputation,
                  bp.quality,bp.service_reliability,
                  COALESCE((SELECT SUM(ps.inventory) FROM production_sites ps
                            JOIN market_goods mg ON mg.id=ps.good_id
                            WHERE ps.enterprise_id=e.id AND ps.active=1 AND mg.good_key='horses_remounts'),0) horse_stock
           FROM civilian_enterprises e
           JOIN enterprise_business_profiles bp ON bp.enterprise_id=e.id
           JOIN business_archetypes ba ON ba.id=bp.archetype_id
           WHERE e.status IN ('active','strained') AND ba.archetype_key='horse_breeder'
             AND e.owner_actor_id IS NOT NULL
           ORDER BY e.id"""
    ).fetchall()
    created = 0
    for r in rows:
        owner = int(r["owner_actor_id"])
        polity = _local_polity(conn, int(r["location_id"]) if r["location_id"] is not None else None)
        if not polity:
            continue
        government = _government_actor(conn, int(polity["id"]))
        if government is None or government == owner:
            continue
        rep = float(r["reputation"] or 0.0)
        quality = float(r["quality"] or 0.0)
        reliability = float(r["service_reliability"] or 0.0)
        stock = float(r["horse_stock"] or 0.0)
        military = float(polity["military_capacity"] or 0.0)
        admin = float(polity["administrative_capacity"] or 0.0)
        # Appointment relevance requires more than being a viable supplier.  The breeder must have
        # durable public standing and quality; stock/reliability make the claim credible, while the
        # state's own military/administrative capacity determines whether it can use such an office.
        salience = (
            rep * 0.31 + quality * 0.30 + reliability * 0.13 + min(100.0, stock * 5.0) * 0.10
            + military * 0.10 + admin * 0.06
        )
        if rep < 62 or quality < 62 or reliability < 50 or salience < 64:
            continue
        if conn.execute(
            """SELECT 1 FROM institutional_appointments
               WHERE appointing_institution_actor_id=? AND holder_actor_id=?
                 AND appointment_key='state_remount_master' AND status='active' LIMIT 1""",
            (int(polity["institution_actor_id"]), owner),
        ).fetchone():
            continue
        if conn.execute(
            """SELECT 1 FROM strategic_attention_cases
               WHERE observer_actor_id=? AND target_actor_id=? AND domain_key='horse_breeding'
                 AND interest_kind='appoint' AND status IN ('observing','planning','approaching','accepted','fulfilled') LIMIT 1""",
            (government, owner),
        ).fetchone():
            continue
        title = f"Remount Master to {polity['institution_name']}"
        create_attention_case(
            conn, government, owner, "horse_breeding", "appoint",
            observer_institution_actor_id=int(polity["institution_actor_id"]), salience=salience,
            source_kind="recognized_enterprise_excellence", source_id=int(r["enterprise_id"]), expires_in_days=300,
            metadata={
                "provider": "horse_breeder_state_appointment",
                "enterprise_id": int(r["enterprise_id"]),
                "polity_id": int(polity["id"]),
                "appointment_key": "state_remount_master",
                "appointment_title": title,
                "proposal_kind": "incorporation",
                "appointment_kind": "technical_office",
                "stipend": round(8.0 + salience * 0.08, 2),
                "exclusivity": 0.85,
                "transfer_enterprise_to_institution": True,
                "retain_breeder_as_operator": True,
                "obligations": {
                    "direct_royal_stud_operations": True,
                    "advise_remount_procurement": True,
                    "inspect_state_breeding_stock": True,
                },
                "privileges": {
                    "court_or_government_access": True,
                    "authority_over_royal_stud_operations": True,
                },
                "evidence": {
                    "enterprise_reputation": rep,
                    "quality": quality,
                    "reliability": reliability,
                    "horse_stock": stock,
                    "salience": round(salience, 3),
                },
            },
        )
        created += 1
    return created


def _pending_case_interaction(conn: sqlite3.Connection, case_id: int) -> sqlite3.Row | None:
    rows = conn.execute("SELECT * FROM interactions WHERE status='pending' ORDER BY id DESC LIMIT 200").fetchall()
    for row in rows:
        terms = _loads(row["terms_json"], {})
        if int(terms.get("attention_case_id") or 0) == int(case_id):
            return row
    return None


def _last_case_interaction(conn: sqlite3.Connection, case_id: int) -> sqlite3.Row | None:
    rows = conn.execute("SELECT * FROM interactions ORDER BY id DESC LIMIT 250").fetchall()
    for row in rows:
        terms = _loads(row["terms_json"], {})
        if int(terms.get("attention_case_id") or 0) == int(case_id):
            return row
    return None


def process_attention_case(conn: sqlite3.Connection, case_id: int, day: int | None = None) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    case = conn.execute("SELECT * FROM strategic_attention_cases WHERE id=?", (case_id,)).fetchone()
    if not case or str(case["status"]) not in {"observing", "planning", "approaching"}:
        return {"case_id": case_id, "action": "none"}
    if case["expires_day"] is not None and day > int(case["expires_day"]):
        conn.execute("UPDATE strategic_attention_cases SET status='expired',last_review_day=?,next_review_day=? WHERE id=?", (day, day, case_id))
        return {"case_id": case_id, "action": "expired"}
    pending = _pending_case_interaction(conn, case_id)
    if pending:
        conn.execute("UPDATE strategic_attention_cases SET status='approaching',last_review_day=?,next_review_day=? WHERE id=?", (day, day + 7, case_id))
        return {"case_id": case_id, "action": "pending_interaction", "interaction_id": int(pending["id"])}
    last = _last_case_interaction(conn, case_id)
    if last and str(last["status"]) in {"rejected", "cancelled", "expired"}:
        conn.execute("UPDATE strategic_attention_cases SET status='rejected',last_review_day=?,next_review_day=? WHERE id=?", (day, day, case_id))
        return {"case_id": case_id, "action": "rejected"}

    meta = _loads(case["metadata_json"], {})
    interest = str(case["interest_kind"])
    observer = int(case["observer_actor_id"])
    target = int(case["target_actor_id"])
    if interest == "patronize":
        from .patronage import propose_patronage
        existing = conn.execute(
            "SELECT id FROM opportunity_proposals WHERE source_attention_case_id=? AND status IN ('draft','pending','countered','accepted') ORDER BY id LIMIT 1",
            (case_id,),
        ).fetchone()
        if existing:
            pid = int(existing[0])
            interaction = None
            prow = conn.execute("SELECT status FROM opportunity_proposals WHERE id=?", (pid,)).fetchone()
            if prow and str(prow[0]) == 'pending':
                from .opportunity import _proposal_interaction
                ir = _proposal_interaction(conn, pid, pending_only=True)
                interaction = int(ir['id']) if ir else None
        else:
            pid, interaction = propose_patronage(
                conn, observer, target, str(case['domain_key']),
                title=str(meta.get('title') or f"Patronage in {case['domain_key']}"),
                amount_per_cycle=float(meta.get('amount_per_cycle') or 0),
                recurrence_days=int(meta.get('recurrence_days') or 30),
                duration_days=meta.get('duration_days'), patronage_kind=meta.get('patronage_kind'),
                funding_source_kind=meta.get('funding_source_kind'), funding_source_id=meta.get('funding_source_id'),
                exclusivity=float(meta.get('exclusivity') or 0), support=meta.get('support') or {}, expectations=meta.get('expectations') or {},
                source_attention_case_id=case_id,
            )
        conn.execute("UPDATE strategic_attention_cases SET status='approaching',last_review_day=?,next_review_day=? WHERE id=?", (day, day + 7, case_id))
        return {"case_id":case_id,"action":"opportunity_offer","proposal_id":pid,"interaction_id":interaction,"target_actor_id":target}

    if interest == "appoint":
        institution_id = int(case["observer_institution_actor_id"]) if case["observer_institution_actor_id"] is not None else None
        if institution_id is None:
            conn.execute("UPDATE strategic_attention_cases SET status='blocked',last_review_day=?,next_review_day=? WHERE id=?", (day, day + 30, case_id))
            return {"case_id": case_id, "action": "blocked_no_institution"}
        # ATTENTION identifies strategic relevance. OPPORTUNITY owns what relationship is actually being offered.
        from .opportunity import create_proposal, add_term, present_proposal
        existing = conn.execute(
            "SELECT id FROM opportunity_proposals WHERE source_attention_case_id=? AND status IN ('draft','pending','countered','accepted','fulfilled') ORDER BY id LIMIT 1",
            (case_id,),
        ).fetchone()
        if existing:
            pid = int(existing[0])
        else:
            pid = create_proposal(
                conn, observer, str(meta.get("proposal_kind") or "appointment"), str(case["domain_key"]),
                str(meta.get("appointment_title") or "Institutional appointment"),
                proposer_institution_actor_id=institution_id, target_actor_id=target,
                source_attention_case_id=case_id, source_kind=str(case["source_kind"] or "strategic_attention"),
                source_id=case["source_id"], metadata={"attention_case_id": case_id, "provider": meta.get("provider")},
            )
            enterprise_id = meta.get("enterprise_id")
            if meta.get("transfer_enterprise_to_institution") and enterprise_id is not None:
                add_term(conn, pid, "enterprise_legal_ownership", subject_kind="enterprise", subject_id=int(enterprise_id), execution_order=20,
                         value={"holder_kind":"institution","holder_id":institution_id,"share":1.0,"replace":True})
                add_term(conn, pid, "enterprise_beneficial_control", subject_kind="enterprise", subject_id=int(enterprise_id), execution_order=30,
                         value={"holder_kind":"institution","holder_id":institution_id,"share":1.0,"replace":True})
                if meta.get("retain_breeder_as_operator"):
                    add_term(conn, pid, "enterprise_operation", subject_kind="enterprise", subject_id=int(enterprise_id), execution_order=40,
                             value={"holder_kind":"actor","holder_id":target,"share":1.0,"replace":True})
            add_term(conn, pid, "appointment", subject_kind="actor", subject_id=target, execution_order=50, value={
                "institution_actor_id": institution_id, "holder_actor_id": target,
                "appointment_key": meta.get("appointment_key"), "title": meta.get("appointment_title"),
                "appointment_kind": meta.get("appointment_kind", "technical_office"),
                "obligations": meta.get("obligations", {}), "privileges": meta.get("privileges", {}),
                "stipend": meta.get("stipend", 0), "exclusivity": meta.get("exclusivity", 0),
            })
        iid = present_proposal(
            conn, pid, day=day,
            rationale="The institution wants a defined relationship with this strategically relevant person. The explicit proposal terms determine whether property, control or independence changes.",
        )
        conn.execute("UPDATE strategic_attention_cases SET status='approaching',last_review_day=?,next_review_day=? WHERE id=?", (day, day + 7, case_id))
        return {"case_id": case_id, "action": "opportunity_offer", "proposal_id": pid, "interaction_id": iid, "target_actor_id": target}

    conn.execute("UPDATE strategic_attention_cases SET status='planning',last_review_day=?,next_review_day=? WHERE id=?", (day, day + 30, case_id))
    return {"case_id": case_id, "action": "unsupported_interest_pending_domain_provider", "interest_kind": interest}


def accept_institutional_appointment(
    conn: sqlite3.Connection,
    attention_case_id: int,
    holder_actor_id: int,
    interaction_id: int,
    day: int | None = None,
) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    case = conn.execute("SELECT * FROM strategic_attention_cases WHERE id=?", (attention_case_id,)).fetchone()
    if not case or str(case["interest_kind"]) != "appoint":
        raise ValueError("attention case is not an appointment")
    if int(case["target_actor_id"]) != int(holder_actor_id):
        raise ValueError("appointment holder does not match attention target")
    institution = int(case["observer_institution_actor_id"]) if case["observer_institution_actor_id"] is not None else None
    if institution is None:
        raise ValueError("appointment has no appointing institution")
    meta = _loads(case["metadata_json"], {})
    key = str(meta.get("appointment_key") or f"appointment_{attention_case_id}")
    title = str(meta.get("appointment_title") or "Institutional Specialist")
    existing = conn.execute(
        """SELECT id FROM institutional_appointments WHERE appointing_institution_actor_id=? AND holder_actor_id=?
           AND appointment_key=? AND status='active' ORDER BY id LIMIT 1""",
        (institution, holder_actor_id, key),
    ).fetchone()
    if existing:
        appointment_id = int(existing[0])
    else:
        cur = conn.execute(
            """INSERT INTO institutional_appointments(
                   appointing_institution_actor_id,holder_actor_id,appointment_key,title,domain_key,appointment_kind,
                   source_attention_case_id,source_interaction_id,started_day,stipend,exclusivity,status,
                   obligations_json,privileges_json,metadata_json
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
            (
                institution, holder_actor_id, key, title, str(case["domain_key"]),
                str(meta.get("appointment_kind") or "technical_office"), attention_case_id, interaction_id, day,
                max(0.0, float(meta.get("stipend") or 0.0)), max(0.0, min(1.0, float(meta.get("exclusivity") or 0.0))),
                _j(meta.get("obligations", {})), _j(meta.get("privileges", {})),
                _j({"authority": "ENGINE_DERIVED", "attention01": True, "source_kind": case["source_kind"], "source_id": case["source_id"]}),
            ),
        )
        appointment_id = int(cur.lastrowid)
    conn.execute(
        """INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json)
           VALUES (?,?,'appointed_office',?,'active',?,?,?)
           ON CONFLICT(institution_actor_id,member_actor_id,membership_kind) DO UPDATE SET
             role_text=excluded.role_text,status='active',left_day=NULL,metadata_json=excluded.metadata_json""",
        (institution, holder_actor_id, title, day, _j(["ATTENTION-01 accepted institutional appointment"]), _j({"institutional_appointment_id": appointment_id})),
    )
    conn.execute("UPDATE strategic_attention_cases SET status='fulfilled',last_review_day=?,next_review_day=? WHERE id=?", (day, day, attention_case_id))
    return {"appointment_id": appointment_id, "institution_actor_id": institution, "holder_actor_id": holder_actor_id, "title": title}


def next_attention_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals: list[int] = []
    r = conn.execute(
        """SELECT MIN(next_review_day) FROM strategic_attention_cases
           WHERE status IN ('observing','planning','approaching') AND next_review_day>? AND next_review_day<=?""",
        (after_day, end_day),
    ).fetchone()
    if r and r[0] is not None:
        vals.append(int(r[0]))
    cycle = ((int(after_day) // 90) + 1) * 90
    if cycle <= int(end_day):
        vals.append(cycle)
    return min(vals) if vals else None


def process_due_attention(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict[str, int]:
    from .patronage import ensure_patronage_attention, ensure_patronage_seeking, refresh_patronage_competitions
    created = ensure_horse_breeder_attention(conn, day) + ensure_patronage_attention(conn, day)
    patronage_requests = ensure_patronage_seeking(conn, day)
    rows = conn.execute(
        """SELECT id FROM strategic_attention_cases
           WHERE status IN ('observing','planning','approaching') AND next_review_day<=?
           ORDER BY next_review_day,id""",
        (day,),
    ).fetchall()
    counts = {"attention_cases_created": created, "attention_cases_reviewed": 0, "attention_approaches": 0,
              "patronage_requests_created": patronage_requests}
    for row in rows:
        result = process_attention_case(conn, int(row[0]), day)
        counts["attention_cases_reviewed"] += 1
        if str(result.get("action", "")).endswith("offer"):
            counts["attention_approaches"] += 1
    counts["patronage_competitions_created"] = refresh_patronage_competitions(conn, day)
    return counts


def summary(conn: sqlite3.Connection) -> dict[str, int]:
    q = lambda sql: int(conn.execute(sql).fetchone()[0])
    return {
        "active_attention_cases": q("SELECT COUNT(*) FROM strategic_attention_cases WHERE status IN ('observing','planning','approaching')"),
        "fulfilled_attention_cases": q("SELECT COUNT(*) FROM strategic_attention_cases WHERE status='fulfilled'"),
        "active_appointments": q("SELECT COUNT(*) FROM institutional_appointments WHERE status='active'"),
    }
```

## engine/commitments.py

```python
"""Commitments: things the protagonist (or someone he commands) has taken on that no engine system models in detail.

A commitment is an `obligations` row (source_kind 'player_commitment') with its costs, people and time kept as JSON in
`notes`, so the simulation's own reminders, overdue cues and time-skip interruptions already see it. Nothing is invented:
the money, the people and the days are debited where they come from, and the GM narrates within that.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

SOURCE = "player_commitment"


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def record(conn: sqlite3.Connection, actor_id: int, description: str, *, kind: str = "project",
           counterparty_actor_id: int | None = None, target_actor_id: int | None = None, target_location_id: int | None = None,
           due_day: int | None = None, importance: int = 2, details: dict[str, Any] | None = None) -> int:
    """Write a commitment. `details` carries: costs (money, people, days), people (actor ids), conditions, terms, outcome."""
    from .competence import add_obligation
    notes = json.dumps({"kind": kind, **(details or {})}, sort_keys=True, default=str)
    return add_obligation(conn, actor_id, description[:300], counterparty_actor_id=counterparty_actor_id, due_day=due_day,
                          target_actor_id=target_actor_id, target_location_id=target_location_id, importance=importance,
                          source_kind=SOURCE, notes=notes)


def details_of(row) -> dict[str, Any]:
    try:
        return json.loads(row["notes"] or "{}")
    except (TypeError, ValueError):
        return {}


def active(conn: sqlite3.Connection, actor_id: int, limit: int = 12, offset: int = 0) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM obligations WHERE actor_id=? AND source_kind=? AND status='active' ORDER BY COALESCE(due_day,999999),id LIMIT ? OFFSET ?",
                          (actor_id, SOURCE, limit, offset)):
        d = details_of(r)
        out.append({"id": int(r["id"]), "what": r["description"], "kind": d.get("kind"), "due_day": r["due_day"], "terms": d.get("terms"),
                    "people": d.get("people_names"), "costs": d.get("cost_words")})
    return out


def complete(conn: sqlite3.Connection, commitment_id: int, status: str = "fulfilled") -> None:
    conn.execute("UPDATE obligations SET status=?,updated_day=? WHERE id=? AND source_kind=?", (status, _day(conn), commitment_id, SOURCE))
```

## engine/seeking.py

```python
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Any

from .ecology import find_route_path, start_travel
from .interactions import create_interaction
from .reputation import martial_instruction_public


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(v: Any) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def _actor_location(conn: sqlite3.Connection, actor_id: int) -> int | None:
    r = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _location_owner(conn: sqlite3.Connection, location_id: int | None) -> str | None:
    if location_id is None:
        return None
    r = conn.execute("SELECT political_owner FROM locations WHERE id=?", (location_id,)).fetchone()
    return str(r[0]) if r and r[0] else None


def register_offering(
    conn: sqlite3.Connection,
    provider_actor_id: int,
    offer_kind: str,
    domain_key: str,
    subject_key: str,
    *,
    provider_enterprise_id: int | None = None,
    provider_institution_actor_id: int | None = None,
    location_id: int | None = None,
    quality: float = 50,
    capacity_per_30: float = 1,
    availability: float = 100,
    public_reputation: float = 50,
    visibility: float = 50,
    scarcity: float = 50,
    access_mode: str = "open",
    metadata: dict[str, Any] | None = None,
) -> int:
    if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (provider_actor_id,)).fetchone():
        raise ValueError("provider actor is not active")
    if provider_enterprise_id is not None:
        e = conn.execute("SELECT owner_actor_id,institution_actor_id,location_id,status FROM civilian_enterprises WHERE id=?", (provider_enterprise_id,)).fetchone()
        if not e or str(e["status"]) not in {"active", "strained"}:
            raise ValueError("provider enterprise is not active")
        if e["owner_actor_id"] is not None and int(e["owner_actor_id"]) != provider_actor_id and (e["institution_actor_id"] is None or int(e["institution_actor_id"]) != provider_actor_id):
            raise ValueError("provider actor does not control enterprise")
        if location_id is None and e["location_id"] is not None:
            location_id = int(e["location_id"])
    if location_id is None:
        location_id = _actor_location(conn, provider_actor_id)
    existing = conn.execute(
        """SELECT id FROM seekable_offerings WHERE provider_actor_id=? AND COALESCE(provider_enterprise_id,0)=COALESCE(?,0)
           AND offer_kind=? AND domain_key=? AND subject_key=? AND status!='closed' ORDER BY id LIMIT 1""",
        (provider_actor_id, provider_enterprise_id, offer_kind, domain_key, subject_key),
    ).fetchone()
    day = _day(conn)
    if existing:
        oid = int(existing[0])
        conn.execute(
            """UPDATE seekable_offerings SET provider_institution_actor_id=?,location_id=?,quality=?,capacity_per_30=?,availability=?,
               public_reputation=?,visibility=?,scarcity=?,access_mode=?,status='active',last_review_day=?,next_review_day=?,metadata_json=? WHERE id=?""",
            (provider_institution_actor_id, location_id, max(0,min(100,float(quality))), max(0,float(capacity_per_30)),
             max(0,min(100,float(availability))), max(0,min(100,float(public_reputation))), max(0,min(100,float(visibility))),
             max(0,min(100,float(scarcity))), access_mode, day, day+30, _j(metadata or {}), oid),
        )
        return oid
    cur = conn.execute(
        """INSERT INTO seekable_offerings(provider_actor_id,provider_enterprise_id,provider_institution_actor_id,location_id,
           offer_kind,domain_key,subject_key,quality,capacity_per_30,availability,public_reputation,visibility,scarcity,access_mode,status,
           last_review_day,next_review_day,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
        (provider_actor_id, provider_enterprise_id, provider_institution_actor_id, location_id, offer_kind, domain_key, subject_key,
         max(0,min(100,float(quality))), max(0,float(capacity_per_30)), max(0,min(100,float(availability))),
         max(0,min(100,float(public_reputation))), max(0,min(100,float(visibility))), max(0,min(100,float(scarcity))), access_mode,
         day, day+30, _j(metadata or {})),
    )
    return int(cur.lastrowid)


def publish_enterprise_offering(
    conn: sqlite3.Connection,
    enterprise_id: int,
    offer_kind: str,
    domain_key: str,
    subject_key: str,
    *,
    good_id: int | None = None,
    access_mode: str = "appointment",
    scarcity: float = 50,
    metadata: dict[str, Any] | None = None,
) -> int:
    e = conn.execute(
        """SELECT e.*,bp.quality,bp.capacity,bp.service_reliability FROM civilian_enterprises e
           LEFT JOIN enterprise_business_profiles bp ON bp.enterprise_id=e.id WHERE e.id=?""",
        (enterprise_id,),
    ).fetchone()
    if not e or str(e["status"]) not in {"active","strained"}:
        raise ValueError("enterprise is not active")
    provider = e["owner_actor_id"] if e["owner_actor_id"] is not None else e["institution_actor_id"]
    if provider is None:
        raise ValueError("enterprise has no actor capable of receiving approaches")
    q = float(e["quality"] if e["quality"] is not None else e["admin_quality"])
    capacity = float(e["capacity"] if e["capacity"] is not None else e["labor_capacity"])
    rep = float(e["reputation"])
    meta = {"enterprise_id": enterprise_id, **(metadata or {})}
    if good_id is not None:
        meta["good_id"] = int(good_id)
    return register_offering(
        conn, int(provider), offer_kind, domain_key, subject_key,
        provider_enterprise_id=enterprise_id, provider_institution_actor_id=int(e["institution_actor_id"]) if e["institution_actor_id"] is not None else None,
        location_id=int(e["location_id"]) if e["location_id"] is not None else None,
        quality=q, capacity_per_30=max(1.0,capacity/5.0), availability=max(10.0,100.0-float(e["debt"])*.1),
        public_reputation=rep, visibility=min(100,35+rep*.65), scarcity=scarcity, access_mode=access_mode, metadata=meta,
    )


def publish_personal_instruction(
    conn: sqlite3.Connection,
    teacher_actor_id: int,
    domain_key: str,
    *,
    subject_key: str | None = None,
    reputation: float | None = None,
    visibility: float | None = None,
    access_mode: str = "visit",
    capacity: int = 3,
    duration_days: int = 360,
    min_entry_score: float = 0,
    completion_gain: float = 8,
    metadata: dict[str, Any] | None = None,
) -> int:
    subject_key = subject_key or domain_key
    score = conn.execute(
        """SELECT MAX(ac.score) FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key=?""", (teacher_actor_id, domain_key)
    ).fetchone()[0]
    quality = float(score if score is not None else 50)
    day = _day(conn)
    rep_mode = "explicit" if reputation is not None else "social_derived"
    public_rep = max(0.0, min(100.0, float(reputation))) if reputation is not None else martial_instruction_public(conn, teacher_actor_id)
    public_visibility = max(0.0, min(100.0, float(visibility))) if visibility is not None else max(12.0, min(95.0, 18.0 + public_rep * .68))
    key = f"personal:{teacher_actor_id}:{domain_key}:{subject_key}"
    prog = conn.execute("SELECT id FROM education_programs WHERE program_key=? AND status='active' ORDER BY id LIMIT 1", (key,)).fetchone()
    if prog:
        program_id = int(prog[0])
    else:
        cur = conn.execute(
            """INSERT INTO education_programs(institution_actor_id,program_key,name,domain_key,program_kind,duration_days,capacity,
               min_entry_score,min_teacher_score,completion_gain,max_score_from_program,status,created_day,review_cadence_days,metadata_json)
               VALUES (NULL,?,?,?,?,?,?,?,?,?,95,'active',?,30,?)""",
            (key, f"Personal instruction under actor #{teacher_actor_id}", domain_key, "advanced_instruction", int(duration_days), int(capacity),
             float(min_entry_score), max(0.0,quality-12.0), float(completion_gain), day,
             _j({"personal_teacher_actor_id":teacher_actor_id,"seek01":True, **(metadata or {})})),
        )
        program_id = int(cur.lastrowid)
    return register_offering(
        conn, teacher_actor_id, "instruction", domain_key, subject_key,
        quality=quality, capacity_per_30=max(1,float(capacity)), public_reputation=public_rep, visibility=public_visibility,
        scarcity=max(20,100-quality), access_mode=access_mode,
        metadata={"program_id":program_id,"personal_instruction":True,"reputation_mode":rep_mode, **(metadata or {})},
    )


def create_seek_intent(
    conn: sqlite3.Connection,
    seeker_actor_id: int,
    need_kind: str,
    domain_key: str,
    subject_key: str,
    *,
    intensity: float = 50,
    min_quality: float = 0,
    quantity: float = 1,
    budget: float | None = None,
    preferred_location_id: int | None = None,
    source_kind: str | None = None,
    source_id: int | None = None,
    expires_in_days: int | None = 365,
    metadata: dict[str, Any] | None = None,
) -> int:
    if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (seeker_actor_id,)).fetchone():
        raise ValueError("seeker actor is not active")
    existing = conn.execute(
        """SELECT id FROM actor_seek_intents WHERE seeker_actor_id=? AND need_kind=? AND domain_key=? AND subject_key=?
           AND status IN ('searching','traveling','approaching') ORDER BY id LIMIT 1""",
        (seeker_actor_id, need_kind, domain_key, subject_key),
    ).fetchone()
    if existing:
        return int(existing[0])
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO actor_seek_intents(seeker_actor_id,need_kind,domain_key,subject_key,intensity,min_quality,quantity,budget,
           preferred_location_id,status,source_kind,source_id,created_day,last_review_day,next_review_day,expires_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,'searching',?,?,?,?,?,?,?)""",
        (seeker_actor_id,need_kind,domain_key,subject_key,max(0,min(100,float(intensity))),max(0,min(100,float(min_quality))),
         max(.01,float(quantity)),budget,preferred_location_id,source_kind,source_id,day,day,day+1,
         None if expires_in_days is None else day+int(expires_in_days),_j(metadata or {})),
    )
    return int(cur.lastrowid)


def _relation_knows(conn: sqlite3.Connection, seeker: int, provider: int) -> bool:
    return conn.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (seeker,provider)).fetchone() is not None


def _discoverable(conn: sqlite3.Connection, seeker: int, offer: sqlite3.Row) -> tuple[bool,float,float,str]:
    provider = int(offer["provider_actor_id"])
    if _relation_knows(conn,seeker,provider):
        return True,.95,1.0,"known_person"
    mode = str(offer["access_mode"])
    if mode in {"closed","invitation"}:
        return False,0,0,"closed"
    sloc = _actor_location(conn,seeker)
    ploc = int(offer["location_id"]) if offer["location_id"] is not None else _actor_location(conn,provider)
    fame = .45*float(offer["public_reputation"]) + .35*float(offer["visibility"]) + .20*float(offer["scarcity"])
    if sloc is not None and ploc is not None and sloc == ploc:
        return fame >= 20, min(.95,.55+fame/220), 1.0, "local_reputation"
    same_owner = _location_owner(conn,sloc) is not None and _location_owner(conn,sloc)==_location_owner(conn,ploc)
    if same_owner and fame >= 43:
        return True,min(.9,.45+fame/200),.9,"regional_reputation"
    if fame >= 76:
        return True,min(.88,.35+fame/180),.78 if mode!="rumoured" else .45,"wide_reputation"
    return False,0,0,"insufficient_reputation_reach"


def _offering_active_load(conn: sqlite3.Connection, offering_id: int) -> float:
    r = conn.execute(
        """SELECT COALESCE(SUM(quantity),0) FROM actor_seek_intents
           WHERE selected_offering_id=? AND status IN ('traveling','approaching')""", (offering_id,)
    ).fetchone()
    load = float(r[0] or 0.0)
    offer = conn.execute("SELECT offer_kind,metadata_json FROM seekable_offerings WHERE id=?", (offering_id,)).fetchone()
    if offer and str(offer["offer_kind"]) == "instruction":
        meta = _loads(offer["metadata_json"], {})
        program_id = meta.get("program_id")
        if program_id is not None:
            active = conn.execute(
                "SELECT COUNT(*) FROM education_enrollments WHERE program_id=? AND status='active'", (int(program_id),)
            ).fetchone()[0]
            load += float(active or 0)
    return load


def _offering_capacity_now(conn: sqlite3.Connection, offer: sqlite3.Row) -> float:
    return max(0.0, float(offer["capacity_per_30"]) * max(0.0, float(offer["availability"])) / 100.0)


def discover_for_intent(conn: sqlite3.Connection, intent_id: int) -> list[dict[str,Any]]:
    intent = conn.execute("SELECT * FROM actor_seek_intents WHERE id=?",(intent_id,)).fetchone()
    if not intent:
        raise ValueError("unknown seek intent")
    rows = conn.execute(
        """SELECT * FROM seekable_offerings WHERE status='active' AND domain_key=? AND subject_key=? AND quality>=? AND availability>0
           ORDER BY quality DESC,public_reputation DESC,id""",
        (str(intent["domain_key"]),str(intent["subject_key"]),float(intent["min_quality"])),
    ).fetchall()
    day=_day(conn); out=[]
    for o in rows:
        if int(o["provider_actor_id"])==int(intent["seeker_actor_id"]):
            continue
        ok,conf,locc,source=_discoverable(conn,int(intent["seeker_actor_id"]),o)
        if not ok:
            continue
        conn.execute(
            """INSERT INTO seek_awareness(seeker_actor_id,offering_id,confidence,location_certainty,source_kind,learned_day,updated_day,metadata_json)
               VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(seeker_actor_id,offering_id) DO UPDATE SET
               confidence=MAX(seek_awareness.confidence,excluded.confidence),location_certainty=MAX(seek_awareness.location_certainty,excluded.location_certainty),
               source_kind=excluded.source_kind,updated_day=excluded.updated_day""",
            (int(intent["seeker_actor_id"]),int(o["id"]),conf,locc,source,day,day,_j({"seek_intent_id":intent_id})),
        )
        sloc=_actor_location(conn,int(intent["seeker_actor_id"])); ploc=int(o["location_id"]) if o["location_id"] is not None else _actor_location(conn,int(o["provider_actor_id"]))
        route_ok = True if sloc==ploc else bool(sloc is not None and ploc is not None and find_route_path(conn,sloc,ploc,day=day))
        capacity_now = _offering_capacity_now(conn, o)
        active_load = _offering_active_load(conn, int(o["id"]))
        # Capacity is a real access constraint, not a reputation penalty.  A provider may be famous
        # enough to be known by many seekers while temporarily unable to accept another named approach.
        if capacity_now <= 0 or active_load + float(intent["quantity"]) > capacity_now + 1e-9:
            continue
        load_ratio = active_load / max(0.01, capacity_now)
        score=(float(o["quality"])-float(intent["min_quality"]))*0.45 + float(o["public_reputation"])*.18 + float(o["scarcity"])*.12 + conf*18 + (8 if route_ok else -25) - load_ratio*9
        out.append({"offering_id":int(o["id"]),"score":score,"confidence":conf,"location_certainty":locc,"route_ok":route_ok,"source_kind":source,
                    "active_load":round(active_load,3),"capacity_now":round(capacity_now,3)})
    return sorted(out,key=lambda x:(-x["score"],x["offering_id"]))


def _pending_seek_interaction(conn: sqlite3.Connection, intent_id: int) -> sqlite3.Row | None:
    rows=conn.execute("SELECT * FROM interactions WHERE status='pending' ORDER BY id DESC LIMIT 100").fetchall()
    for r in rows:
        terms=_loads(r["terms_json"],{})
        if int(terms.get("seek_intent_id") or 0)==int(intent_id):
            return r
    return None


def _approach(conn: sqlite3.Connection, intent: sqlite3.Row, offer: sqlite3.Row, day: int) -> int:
    meta=_loads(offer["metadata_json"],{})
    provider=int(offer["provider_actor_id"]); seeker=int(intent["seeker_actor_id"])
    domain_action: dict[str,Any]
    interaction_type="request"
    if str(offer["offer_kind"])=="instruction":
        pid=meta.get("program_id")
        if pid is None:
            raise ValueError("instruction offering has no program")
        domain_action={"kind":"seek_personal_instruction","initiator_actor_id":seeker,"payload":{"program_id":int(pid),"offering_id":int(offer["id"]),"teacher_actor_id":provider}}
    elif str(offer["offer_kind"])=="goods":
        good_id=meta.get("good_id")
        if good_id is None or offer["provider_enterprise_id"] is None:
            raise ValueError("goods offering lacks good/enterprise")
        interaction_type="contract"
        domain_action={"kind":"seek_direct_procurement","initiator_actor_id":seeker,"payload":{"offering_id":int(offer["id"]),"seller_enterprise_id":int(offer["provider_enterprise_id"]),"good_id":int(good_id),"quantity":float(intent["quantity"])}}
    else:
        domain_action={"kind":"seek_provider_service","initiator_actor_id":seeker,"payload":{"offering_id":int(offer["id"]),"subject_key":str(offer["subject_key"])}}
    terms={"purpose":f"seek {offer['subject_key']}","seek_intent_id":int(intent["id"]),"offering_id":int(offer["id"]),"domain_action":domain_action}
    iid=create_interaction(conn,seeker,provider,interaction_type,day,urgency=3 if float(intent["intensity"])>=70 else 2,stakes=max(1,min(5,int(math.ceil(float(intent["intensity"])/22)))),terms=terms,
                           rationale=f"The proposer sought out a provider because persisted need and public/known capability made this offering attractive.")
    conn.execute("UPDATE actor_seek_intents SET status='approaching',selected_offering_id=?,last_review_day=?,next_review_day=? WHERE id=?",(int(offer["id"]),day,day+7,int(intent["id"])))
    return iid


def process_seek_intent(conn: sqlite3.Connection, intent_id: int, day: int | None=None) -> dict[str,Any]:
    day=_day(conn) if day is None else int(day)
    intent=conn.execute("SELECT * FROM actor_seek_intents WHERE id=?",(intent_id,)).fetchone()
    if not intent or str(intent["status"]) not in {"searching","traveling","approaching"}:
        return {"intent_id":intent_id,"action":"none"}
    if intent["expires_day"] is not None and day>int(intent["expires_day"]):
        conn.execute("UPDATE actor_seek_intents SET status='expired',last_review_day=?,next_review_day=? WHERE id=?",(day,day,intent_id)); return {"intent_id":intent_id,"action":"expired"}
    pending=_pending_seek_interaction(conn,intent_id)
    if pending:
        conn.execute("UPDATE actor_seek_intents SET status='approaching',last_review_day=?,next_review_day=? WHERE id=?",(day,day+7,intent_id)); return {"intent_id":intent_id,"action":"pending_interaction","interaction_id":int(pending["id"])}
    # If a prior interaction resolved, domain callback marks fulfilled on acceptance. Rejection returns search to market.
    if str(intent["status"])=="approaching":
        last=conn.execute("SELECT * FROM interactions WHERE proposer_actor_id=? ORDER BY id DESC LIMIT 20",(int(intent["seeker_actor_id"]),)).fetchall()
        for r in last:
            t=_loads(r["terms_json"],{})
            if int(t.get("seek_intent_id") or 0)==intent_id and str(r["status"]) in {"rejected","cancelled","expired"}:
                conn.execute("UPDATE actor_seek_intents SET status='searching',selected_offering_id=NULL,last_review_day=?,next_review_day=? WHERE id=?",(day,day+14,intent_id)); break
    selected=intent["selected_offering_id"]
    offer=conn.execute("SELECT * FROM seekable_offerings WHERE id=? AND status='active'",(int(selected),)).fetchone() if selected is not None else None
    if offer is None:
        matches=discover_for_intent(conn,intent_id)
        if not matches and str(intent["need_kind"]) == "instruction" and str(intent["domain_key"]) == "martial_instruction":
            # Actual demand may reveal a suitable pre-existing background teacher. It never creates one.
            from .teaching_ecology import ensure_provider_for_seek_intent
            ensure_provider_for_seek_intent(conn,intent_id)
            matches=discover_for_intent(conn,intent_id)
        if not matches:
            conn.execute("UPDATE actor_seek_intents SET status='searching',last_review_day=?,next_review_day=? WHERE id=?",(day,day+30,intent_id)); return {"intent_id":intent_id,"action":"no_provider_known"}
        offer=conn.execute("SELECT * FROM seekable_offerings WHERE id=?",(matches[0]["offering_id"],)).fetchone()
        conn.execute("UPDATE actor_seek_intents SET selected_offering_id=? WHERE id=?",(int(offer["id"]),intent_id))
    seeker=int(intent["seeker_actor_id"]); sloc=_actor_location(conn,seeker); ploc=int(offer["location_id"]) if offer["location_id"] is not None else _actor_location(conn,int(offer["provider_actor_id"]))
    physical = str(offer["offer_kind"])=="instruction" or str(offer["access_mode"]) in {"visit","rumoured"}
    if physical and (sloc is None or ploc is None):
        conn.execute("UPDATE actor_seek_intents SET status='blocked',last_review_day=?,next_review_day=? WHERE id=?",(day,day+30,intent_id))
        return {"intent_id":intent_id,"action":"blocked_unknown_location"}
    if physical and sloc!=ploc:
        active=conn.execute("SELECT * FROM travel_plans WHERE subject_kind='actor' AND subject_id=? AND status IN ('active','stalled') ORDER BY id DESC LIMIT 1",(seeker,)).fetchone()
        if active:
            conn.execute("UPDATE actor_seek_intents SET status='traveling',last_review_day=?,next_review_day=? WHERE id=?",(day,day+3,intent_id)); return {"intent_id":intent_id,"action":"traveling","travel_plan_id":int(active["id"])}
        if not find_route_path(conn,sloc,ploc,day=day):
            conn.execute("UPDATE actor_seek_intents SET status='blocked',last_review_day=?,next_review_day=? WHERE id=?",(day,day+30,intent_id)); return {"intent_id":intent_id,"action":"blocked_no_route"}
        tid=start_travel(conn,"actor",seeker,ploc,metadata={"purpose":"seek_provider","seek_intent_id":intent_id,"offering_id":int(offer["id"]),"provider_actor_id":int(offer["provider_actor_id"])})
        conn.execute("UPDATE actor_seek_intents SET status='traveling',last_review_day=?,next_review_day=? WHERE id=?",(day,day+3,intent_id)); return {"intent_id":intent_id,"action":"started_travel","travel_plan_id":tid}
    iid=_approach(conn,intent,offer,day)
    return {"intent_id":intent_id,"action":"approach","interaction_id":iid,"provider_actor_id":int(offer["provider_actor_id"])}


def refresh_enterprise_offerings(conn: sqlite3.Connection) -> int:
    """Project discoverable capabilities from real enterprise state.

    This is intentionally conservative.  Only domains with a real SEEK consequence bridge should
    auto-publish here; adding an archetype to the business catalogue is not enough by itself.
    """
    horses = conn.execute("SELECT id FROM market_goods WHERE good_key='horses_remounts'").fetchone()
    if not horses:
        return 0
    horse_good = int(horses[0])
    rows = conn.execute(
        """SELECT e.id enterprise_id
           FROM civilian_enterprises e
           JOIN enterprise_business_profiles bp ON bp.enterprise_id=e.id
           JOIN business_archetypes ba ON ba.id=bp.archetype_id
           WHERE e.status IN ('active','strained') AND ba.archetype_key='horse_breeder'
             AND EXISTS (SELECT 1 FROM production_sites ps WHERE ps.enterprise_id=e.id AND ps.good_id=? AND ps.active=1 AND ps.inventory>0)
           ORDER BY e.id""", (horse_good,)
    ).fetchall()
    published = 0
    for r in rows:
        eid = int(r["enterprise_id"])
        publish_enterprise_offering(
            conn, eid, "goods", "military_logistics", "remounts", good_id=horse_good,
            access_mode="appointment", scarcity=68,
            metadata={"auto_projected_from_enterprise": True, "capability_basis": "horse_breeder_with_remount_stock"},
        )
        published += 1
    # If the material capability disappears, pause only auto-projected remount offerings; explicit
    # campaign offerings remain under their owner's chosen state.
    conn.execute(
        """UPDATE seekable_offerings SET status='paused',last_review_day=?
           WHERE domain_key='military_logistics' AND subject_key='remounts' AND status='active'
             AND json_extract(metadata_json,'$.auto_projected_from_enterprise')=1
             AND (provider_enterprise_id IS NULL OR NOT EXISTS (
                 SELECT 1 FROM production_sites ps
                 WHERE ps.enterprise_id=seekable_offerings.provider_enterprise_id AND ps.good_id=? AND ps.active=1 AND ps.inventory>0
             ))""", (_day(conn), horse_good)
    )
    return published


def _stable_propensity(conn: sqlite3.Connection, actor_id: int, cycle: int, salt: str) -> float:
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    raw = f"{seed}:{actor_id}:{cycle}:{salt}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") / float(2**64 - 1)


def ensure_martial_instruction_intents(conn: sqlite3.Connection, day: int | None=None) -> int:
    """Let individual practitioners form a real need to seek outside instruction.

    This is deliberately sparse at named resolution.  Ordinary aspirants remain aggregate social
    attention; a tracked actor becomes a named seeker only when poor teacher access, advancement
    pressure and their own deterministic propensity make the search consequential enough to track.
    The player actor is excluded because the engine must not invent the player's goals.
    """
    day = _day(conn) if day is None else int(day)
    cycle = day // 90
    player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    player_id = int(player[0]) if player and player[0] is not None else None
    rows = conn.execute(
        """SELECT cp.actor_id,cp.current_stage,cp.teacher_support,cp.plateau_days,cp.training_effort,
                  cp.realization_integration,er.resolution_level
           FROM cultivation_profiles cp
           JOIN actors a ON a.id=cp.actor_id AND a.status='active'
           JOIN entity_resolution er ON er.entity_kind='actor' AND er.entity_id=cp.actor_id
           WHERE cp.active=1
             AND cp.current_stage IN ('First','Temper','Third','Breach','Fifth')
             AND er.resolution_level IN ('TRACKED','ACTIVE')
             AND cp.teacher_support < 36
           ORDER BY cp.actor_id"""
    ).fetchall()
    stage_pressure = {"First": 12.0, "Temper": 20.0, "Third": 18.0, "Breach": 14.0, "Fifth": 9.0}
    min_quality = {"First": 50.0, "Temper": 58.0, "Third": 66.0, "Breach": 76.0, "Fifth": 86.0}
    created = 0
    for r in rows:
        aid = int(r["actor_id"])
        if player_id is not None and aid == player_id:
            continue
        if conn.execute("SELECT 1 FROM teaching_relationships WHERE student_actor_id=? AND status='active' LIMIT 1", (aid,)).fetchone():
            continue
        if conn.execute("SELECT 1 FROM education_enrollments WHERE actor_id=? AND status='active' LIMIT 1", (aid,)).fetchone():
            continue
        if conn.execute(
            """SELECT 1 FROM actor_seek_intents WHERE seeker_actor_id=? AND need_kind='instruction'
               AND domain_key='martial_instruction' AND subject_key='martial_instruction'
               AND status IN ('searching','traveling','approaching') LIMIT 1""", (aid,)
        ).fetchone():
            continue
        support_gap = max(0.0, 40.0 - float(r["teacher_support"]))
        plateau = min(30.0, max(0.0, float(r["plateau_days"])) / 45.0)
        effort = max(0.0, float(r["training_effort"]) - 45.0) * 0.45
        integration_gap = max(0.0, 70.0 - float(r["realization_integration"])) * 0.12
        need_score = 22.0 + support_gap * 0.72 + plateau + effort + integration_gap + stage_pressure[str(r["current_stage"])]
        # No quota: each actor independently forms the goal.  The probability rises sharply only
        # when the actor has a genuine access/progression problem, keeping named seekers sparse.
        probability = max(0.0, min(0.22, (need_score - 62.0) / 180.0))
        if probability <= 0 or _stable_propensity(conn, aid, cycle, "martial_instruction") >= probability:
            continue
        intensity = max(45.0, min(92.0, need_score))
        create_seek_intent(
            conn, aid, "instruction", "martial_instruction", "martial_instruction",
            intensity=intensity, min_quality=min_quality[str(r["current_stage"])], quantity=1,
            source_kind="cultivation_instruction_need", source_id=aid, expires_in_days=270,
            metadata={"opening_stage": str(r["current_stage"]), "teacher_support": float(r["teacher_support"]),
                      "plateau_days": int(r["plateau_days"]), "named_need_score": round(need_score, 3)},
        )
        created += 1
    return created


def ensure_military_remount_intents(conn: sqlite3.Connection, day: int | None=None) -> int:
    """Create ordinary remount-procurement needs for polity governments.

    Needs exist independently of whether a famous breeder happens to be available.  The seeking
    layer then decides whether any known provider is worth approaching.
    """
    day=_day(conn) if day is None else int(day)
    created=0
    good=conn.execute("SELECT id FROM market_goods WHERE good_key='horses_remounts'").fetchone()
    if not good:
        return 0
    rows=conn.execute("""SELECT p.id polity_id,p.military_capacity,p.treasury_pressure,pga.decision_actor_id,ml.readiness,ml.transport_capacity,ml.status
                         FROM political_polities p JOIN polity_government_actors pga ON pga.polity_id=p.id
                         LEFT JOIN military_logistics_profiles ml ON ml.polity_id=p.id WHERE p.status!='dissolved'""").fetchall()
    for r in rows:
        aid=int(r["decision_actor_id"])
        if conn.execute("""SELECT 1 FROM actor_seek_intents WHERE seeker_actor_id=? AND domain_key='military_logistics' AND subject_key='remounts'
                           AND status IN ('searching','traveling','approaching')""",(aid,)).fetchone():
            continue
        readiness=float(r["readiness"] if r["readiness"] is not None else 50); transport=float(r["transport_capacity"] if r["transport_capacity"] is not None else 50)
        intensity=max(28,min(90,35+(100-readiness)*.28+float(r["military_capacity"])*.18+(12 if str(r["status"] or '')=='mobilized' else 0)))
        qty=max(2.0,round((float(r["military_capacity"])+transport)/18.0,1))
        create_seek_intent(conn,aid,"procurement","military_logistics","remounts",intensity=intensity,min_quality=45,quantity=qty,
                           source_kind="polity_remount_cycle",source_id=int(r["polity_id"]),expires_in_days=240,
                           metadata={"buyer_polity_id":int(r["polity_id"]),"good_id":int(good[0]),"ordinary_replacement_demand":True})
        created+=1
    return created


def next_seeking_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals=[]
    r=conn.execute("SELECT MIN(next_review_day) FROM actor_seek_intents WHERE status IN ('searching','traveling','approaching') AND next_review_day>? AND next_review_day<=?",(after_day,end_day)).fetchone()
    if r and r[0] is not None: vals.append(int(r[0]))
    # Slow structural demand refresh, independent of whether a provider already exists.
    cyc=((int(after_day)//90)+1)*90
    if cyc<=int(end_day) and conn.execute("SELECT 1 FROM political_polities WHERE status!='dissolved' LIMIT 1").fetchone(): vals.append(cyc)
    return min(vals) if vals else None


def process_due_seeking(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict[str,int]:
    # Real capabilities are projected before needs search, so no actor must manually "register with SEEK".
    refresh_enterprise_offerings(conn)
    for offer in conn.execute("SELECT id,provider_actor_id,metadata_json FROM seekable_offerings WHERE status='active' AND offer_kind='instruction'").fetchall():
        meta = _loads(offer["metadata_json"], {})
        if meta.get("personal_instruction") and meta.get("reputation_mode") == "social_derived":
            rep = martial_instruction_public(conn, int(offer["provider_actor_id"]))
            vis = max(12.0, min(95.0, 18.0 + rep * .68))
            conn.execute("UPDATE seekable_offerings SET public_reputation=?,visibility=?,last_review_day=?,next_review_day=? WHERE id=?", (rep,vis,day,day+30,int(offer["id"])))
    # Demand renewal is intentionally slow; seven polity governments create at most seven standing remount searches.
    ensure_military_remount_intents(conn,day)
    ensure_martial_instruction_intents(conn,day)
    rows=conn.execute("SELECT id FROM actor_seek_intents WHERE status IN ('searching','traveling','approaching') AND next_review_day<=? ORDER BY next_review_day,id",(day,)).fetchall()
    counts={"seek_intents_reviewed":0,"seek_travel_started":0,"seek_approaches":0,"seek_blocked":0}
    for r in rows:
        res=process_seek_intent(conn,int(r[0]),day); counts["seek_intents_reviewed"]+=1
        if res.get("action")=="started_travel": counts["seek_travel_started"]+=1
        elif res.get("action")=="approach": counts["seek_approaches"]+=1
        elif str(res.get("action","")).startswith("blocked"): counts["seek_blocked"]+=1
    return counts


def mark_intent_fulfilled(conn: sqlite3.Connection, intent_id: int, *, detail: dict[str,Any] | None=None) -> None:
    day=_day(conn)
    row=conn.execute("SELECT metadata_json FROM actor_seek_intents WHERE id=?",(intent_id,)).fetchone()
    if not row:
        return
    meta=_loads(row[0],{}); meta.setdefault("fulfillment",{}).update(detail or {}); meta["fulfilled_day"]=day
    conn.execute("UPDATE actor_seek_intents SET status='fulfilled',last_review_day=?,next_review_day=?,metadata_json=? WHERE id=?",(day,day,_j(meta),intent_id))


def summary(conn: sqlite3.Connection) -> dict[str,int]:
    q=lambda sql:int(conn.execute(sql).fetchone()[0])
    return {
        "active_offerings":q("SELECT COUNT(*) FROM seekable_offerings WHERE status='active'"),
        "active_intents":q("SELECT COUNT(*) FROM actor_seek_intents WHERE status IN ('searching','traveling','approaching')"),
        "fulfilled_intents":q("SELECT COUNT(*) FROM actor_seek_intents WHERE status='fulfilled'"),
        "awareness_edges":q("SELECT COUNT(*) FROM seek_awareness"),
        "procurement_contracts":q("SELECT COUNT(*) FROM seek_procurement_contracts"),
    }
```


(End of batch 2 of 5.)
