# Three levels, nearby code: batch 1 of 5: Knowledge and resolution

Same review as the first file (design revision 3.1 and its contract are already with you; not repeated).
This batch settles suspicions 2 and 5. For each module, give the same verdict as before (keep as is, fold into the build, rework, or cut),
with the reason and function names, and when to do it.

Facts from the same test (Saint Jude, day 120, from the opening):
- events: life:coming_of_age 101, life:birth 56, life:union 34, civilian:succession 5, life:death 4. That is all 200
  events, and each became a rumour (rumours 200; rumour_exposures 9,665; rumour_locations 1,400).
- decisions 591 by action_type: org_action 238, consolidate 209, initiate_interaction 144. The interactions table
  holds exactly 144 offers (138 accepted), so the personal path of decide_actor produces them.
- life_matters 2,678; life_matter_steps 4,666; life_events 3,575; temptations 1,337; psychological_stressors 9.
- org_incidents 941; org_money 13,268; org_agenda 476; org_tension_acts 357; org_seats 1,904; public_attention 131.
- The Caerness economy processes (agriculture, logistics, merchant, craft, growth, war, patronage, education) have
  no rows in Saint Jude apart from enterprise_ecology_state 544 and conflict_geometries 31. They run, but on empty
  tables.

Two corrections to your first answer:
- advance_connection_legacy is not dead. tests/arch01_process_registry_test.py uses it as the reference for the
  equivalence test of the process registry.
- "Thousands of offers" was our earlier estimate, not this run's: here it is 144 in 120 days.

Modules in this batch: engine/hearsay.py, engine/claims.py, engine/findings.py, engine/memory.py, engine/continuity.py, engine/resolution_controller.py, engine/activation.py, engine/tiers.py, engine/crystallization.py, engine/decision_runtime.py.


## engine/hearsay.py

```python
"""What reaches the protagonist of other people's lives, and by whom.

What happened (a step of a life matter) and what he knows are separate records. A step reaches him only by a real path: it happened
to him, or a living person close to him carries it: the one it happened to, or someone who knows both. His knowledge row keeps the
day and who carried it (`fact_key` "step:<step>:<carrier, 0 for himself>"); why it reaches him is the tie between them. His circle
decides what is delivered and where a skip stops, never what happens.
"""
from __future__ import annotations

import random
import sqlite3

from . import life_matters, texture, world_calendar
from .design import figure, run_seed
from .world_package import current_package

PREFIX = "step:"
_KIN_WORDS = {"parent": ("father", "mother", "parent"), "child": ("son", "daughter", "child"), "sibling": ("brother", "sister", "sibling"),
              "spouse": ("husband", "wife", "spouse")}


def _name(conn, a: int) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (int(a),)).fetchone()
    return str(r[0]) if r else "someone"


def _ids(text) -> list[int]:
    return [int(x) for x in str(text or "").split(",") if x]


def relation(conn: sqlite3.Connection, me: int, other: int) -> str:
    """What `other` is to him, in a word or two."""
    r = conn.execute("SELECT kin_kind FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND ended_day IS NULL LIMIT 1", (other, me)).fetchone()
    if r:
        words = _KIN_WORDS.get(str(r[0]))
        if not words:
            return "family"
        s = conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (other,)).fetchone()
        return words[{"male": 0, "female": 1}.get(str(s[0]) if s else "", 2)]
    if conn.execute("""SELECT 1 FROM household_members a JOIN household_members b ON b.household_id=a.household_id
                       WHERE a.actor_id=? AND b.actor_id=? AND a.status='active' AND b.status='active'""", (me, other)).fetchone():
        return "shares a home"
    for sql, word in (
        ("SELECT 1 FROM enterprise_staff s JOIN civilian_enterprises e ON e.id=s.enterprise_id WHERE s.actor_id=? AND e.owner_actor_id=? AND s.status='active'", "boss"),
        ("SELECT 1 FROM civilian_enterprises e JOIN enterprise_staff s ON s.enterprise_id=e.id WHERE e.owner_actor_id=? AND s.actor_id=? AND s.status='active'", "works for you"),
        ("SELECT 1 FROM enterprise_staff a JOIN enterprise_staff b ON b.enterprise_id=a.enterprise_id WHERE a.actor_id=? AND b.actor_id=? AND a.status='active' AND b.status='active'", "workmate"),
    ):
        if conn.execute(sql, (me, other)).fetchone():
            return word
    if conn.execute("SELECT 1 FROM deals WHERE status='open' AND ((customer_ref=? AND provider_ref=?) OR (customer_ref=? AND provider_ref=?))",
                    (f"person:{me}", f"person:{other}", f"person:{other}", f"person:{me}")).fetchone():
        return "money between you"
    v = conn.execute("SELECT affection,resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (me, other)).fetchone()
    if v and float(v[0] or 0) >= float(figure(conn, "lm_friend_affection", 30.0)):
        return "friend"
    if v and float(v[1] or 0) >= float(figure(conn, "lm_friend_affection", 30.0)):
        return "bad blood"
    return "acquaintance"


def _path(conn, me: int, close: dict[int, float], known: dict[int, dict[int, float]], actors: list[int], rng: random.Random,
          sure: set[int] = frozenset()) -> int | None:
    """Who brings it to him: 0 when it happened to him, a carrier's id, or None when it does not reach him. People in `sure` always
    tell this themselves."""
    if me in actors:
        return 0
    own = {a: close[a] for a in actors if a in close}
    always = sorted(a for a in own if a in sure)
    if always:
        return max(always, key=own.get)
    if own:
        who = max(sorted(own), key=own.get)
        if rng.random() < float(figure(conn, "lm_news_own")) * own[who]:
            return who
    second: dict[int, float] = {}
    for a in actors:
        for c, w in known.get(a, {}).items():
            if c not in actors:
                second[c] = max(second.get(c, 0.0), close[c] * w)
    if second:
        who = max(sorted(second), key=second.get)
        if rng.random() < float(figure(conn, "lm_news_secondhand")) * second[who]:
            return who
    return None


def reach(conn: sqlite3.Connection, me: int, day: int) -> int:
    """Enter what reaches him of the steps taken since the last pass. Returns how many."""
    row = conn.execute("SELECT value FROM engine_meta WHERE key='hearsay_step'").fetchone()
    last = int(row[0]) if row else 0
    steps = conn.execute("SELECT id,day,text,actors FROM life_matter_steps WHERE id>? ORDER BY id", (last,)).fetchall()
    if not steps:
        return 0
    close = texture.circle(conn, me)
    told = life_matters.told(conn, me, close)
    known = life_matters.known_by(conn, sorted(close))  # once a pass: who has someone of his circle in their life
    seed = run_seed(conn)
    stale = figure(conn, "news_stale_days")
    n = 0
    for s in steps:
        if stale and int(s["day"]) < int(day) - int(stale):  # written down as past (a courtship already under way): history, not news
            continue
        carrier = _path(conn, me, close, known, _ids(s["actors"]), random.Random(f"{seed}:hearsay:{me}:{s['id']}"), told)
        if carrier is None:
            continue
        conn.execute("INSERT OR IGNORE INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day) VALUES (?,?,?,?,?)",
                     (me, f"{PREFIX}{s['id']}:{carrier}", s["text"], 1.0 if not carrier else float(figure(conn, "lm_news_confidence")), int(day)))
        n += 1
    conn.execute("INSERT INTO engine_meta(key,value) VALUES ('hearsay_step',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (str(int(steps[-1]["id"])),))
    return n


def parse(conn: sqlite3.Connection, fact_key: str) -> tuple[sqlite3.Row | None, int]:
    """(the step with its matter, the carrier) behind a knowledge row's key."""
    _, step, carrier = str(fact_key).split(":")
    row = conn.execute("""SELECT s.id step_id,s.day,s.stage,s.text,s.actors,s.matter_id,m.kind,m.status,m.awaiting,m.amount,m.subject_actor_id,
                                 m.other_actor_id,m.location_id
                          FROM life_matter_steps s JOIN life_matters m ON m.id=s.matter_id WHERE s.id=?""", (int(step),)).fetchone()
    return row, int(carrier)


def via(conn: sqlite3.Connection, me: int, carrier: int) -> str:
    return "it happened to you" if not carrier else f"from {_name(conn, carrier)} ({relation(conn, me, carrier)})"


def _known(conn, me: int, start: int, end: int) -> list:
    return conn.execute("""SELECT fact_key,belief_text,learned_day FROM knowledge WHERE knower_actor_id=? AND fact_key LIKE 'step:%'
                           AND learned_day>? AND learned_day<=? ORDER BY learned_day,id""", (me, start, end)).fetchall()


def _item(conn, me: int, k) -> dict | None:
    s, carrier = parse(conn, k["fact_key"])
    if s is None:
        return None
    pkg = current_package(conn)
    people = [{"id": a, "name": _name(conn, a), "relation": relation(conn, me, a)} for a in _ids(s["actors"]) if a != me]
    out = {"date": world_calendar.format_date(pkg, int(k["learned_day"])), "what": k["belief_text"], "about": s["kind"], "people": people,
           "involves_you": me in _ids(s["actors"])}
    if carrier:
        out["told_by"] = {"id": carrier, "name": _name(conn, carrier), "relation": relation(conn, me, carrier)}
    place = conn.execute("SELECT name FROM locations WHERE id=?", (s["location_id"],)).fetchone() if s["location_id"] is not None else None
    if place:
        out["where"] = str(place[0])
    if s["amount"]:
        out["stakes"] = life_matters.money(life_matters.data(conn), float(s["amount"]))
    if s["status"] == "open":
        mine = bool(s["awaiting"]) and me in _ids(s["actors"])
        out["open"] = "waits on your answer" if mine else "not settled"
        if mine:
            out["matter"] = int(s["matter_id"])  # the number his answer is given under
    # the thread so far: earlier steps of this matter, and of earlier matters of the same kind between the same two
    before = conn.execute("""SELECT s.day,s.text FROM life_matter_steps s JOIN life_matters m ON m.id=s.matter_id
                             WHERE s.id<? AND m.kind=? AND (s.matter_id=? OR (m.subject_actor_id=? AND m.other_actor_id=?)
                                   OR (m.subject_actor_id=? AND m.other_actor_id=?))
                               AND EXISTS(SELECT 1 FROM knowledge k WHERE k.knower_actor_id=? AND k.fact_key LIKE 'step:' || s.id || ':%')
                             ORDER BY s.id DESC LIMIT 3""",
                          (s["step_id"], s["kind"], s["matter_id"], s["subject_actor_id"], s["other_actor_id"], s["other_actor_id"],
                           s["subject_actor_id"], me)).fetchall()
    if before:
        out["before"] = [f"{world_calendar.format_date(pkg, int(b['day']))}: {b['text']}" for b in reversed(before)]
    return out


def material(conn: sqlite3.Connection, me: int, start: int, end: int) -> dict:
    """What the GM can play from the days `start`..`end`: what reached him (his own first, then his closest), and what he does not
    know about his closest people (for cutaways only)."""
    if not life_matters.enabled(conn):
        return {}
    close = texture.circle(conn, me)
    rows = _known(conn, me, start, end)

    def weight(k):
        s, _ = parse(conn, k["fact_key"])
        ids = _ids(s["actors"]) if s is not None else []
        return (me in ids, max((close.get(a, 0.0) for a in ids), default=0.0), k["learned_day"])
    ranked = sorted(rows, key=weight, reverse=True)
    budget = int(figure(conn, "lm_material_items"))
    out: dict = {}
    items = [x for x in (_item(conn, me, k) for k in ranked[:budget]) if x]
    if items:
        out["material"] = items
    if len(ranked) > budget:
        out["material_more"] = len(ranked) - budget
    near = float(figure(conn, "lm_stop_closeness"))
    known = {str(k["fact_key"]).split(":")[1] for k in rows}
    unseen = []
    for s in conn.execute("SELECT id,text,actors FROM life_matter_steps WHERE day>? AND day<=? ORDER BY id DESC", (start, end)):
        ids = _ids(s["actors"])
        if str(s["id"]) not in known and me not in ids and any(close.get(a, 0.0) >= near for a in ids):
            unseen.append(str(s["text"]))
            if len(unseen) >= 3:
                break
    if unseen:
        out["outside_your_knowledge"] = unseen
    return out


def waiting(conn: sqlite3.Connection, me: int) -> list[dict]:
    """The matters whose next move is his, in their latest words, each with the number his answer is given under."""
    if not life_matters.enabled(conn):
        return []
    return [{"matter": int(r["id"]), "about": r["kind"], "what": str(r["summary"])} for r in conn.execute(
        """SELECT id,kind,summary FROM life_matters WHERE status='open' AND awaiting=1
           AND (subject_actor_id=? OR other_actor_id=?) AND summary IS NOT NULL ORDER BY opened_day,id""", (me, me))]


def asks(conn: sqlite3.Connection, me: int, start: int, end: int, *, every: bool = False) -> list[dict]:
    """What an ordinary skip stops for in `start`..`end`: a matter that turned to him and turns on him personally (the package
    names the kinds, and those that only count when the money is big), and word of the family events it names. With `every`, any
    matter that turned to him stops; otherwise the rest waits, open, and is told when the skip ends."""
    if not life_matters.enabled(conn):
        return []
    rules = life_matters.data(conn).get("stops") or {}
    kinds, big = set(rules.get("waiting") or ()), set(rules.get("waiting_big") or ())
    floor = float(figure(conn, "lm_big_money_usd", 0.0))
    rows = conn.execute("""SELECT MAX(s.id) step_id,s.day,s.text,m.kind,m.amount FROM life_matters m JOIN life_matter_steps s
                             ON s.matter_id=m.id AND s.day=json_extract(m.data_json,'$.asked_day')
                           WHERE (m.subject_actor_id=? OR m.other_actor_id=?) AND s.day>? AND s.day<=? GROUP BY m.id""", (me, me, start, end))
    found = [{"day": int(r["day"]), "source_kind": "system", "source_id": int(r["step_id"]), "severity": 4, "reason": str(r["text"]),
              "metadata": {"what": "matter", "kind": r["kind"]}} for r in rows
             if every or not rules or r["kind"] in kinds or (r["kind"] in big and float(r["amount"] or 0) >= floor)]
    events = set(rules.get("family") or ())
    if events:
        family = life_matters.family_of(conn, me)
        for k in _known(conn, me, start, end):
            s, _ = parse(conn, k["fact_key"])
            if s is None or f"{s['kind']}.{s['stage']}" not in events or not family & (set(_ids(s["actors"])) - {me}):
                continue
            found.append({"day": int(k["learned_day"]), "source_kind": "system", "source_id": int(s["step_id"]), "severity": 4,
                          "reason": str(k["belief_text"]), "metadata": {"what": "matter", "kind": s["kind"]}})
    return found


def stops(conn: sqlite3.Connection, me: int, start: int, end: int) -> list[dict]:
    """The days in `start`..`end` that hold something worth stopping a skip for: a matter of his own or of someone close that
    reached him, or money of his that moved or fell due."""
    found: list[dict] = []
    if life_matters.enabled(conn):
        close = texture.circle(conn, me)
        near = float(figure(conn, "lm_stop_closeness"))
        told = life_matters.told(conn, me)
        for k in _known(conn, me, start, end):
            s, _ = parse(conn, k["fact_key"])
            if s is None:
                continue
            ids = _ids(s["actors"])
            if me in ids or any(close.get(a, 0.0) >= near or (s["kind"] == "romance" and a in told) for a in ids):
                found.append({"day": int(k["learned_day"]), "source_kind": "system", "source_id": int(s["step_id"]), "severity": 4 if me in ids else 3,
                              "reason": str(k["belief_text"]), "metadata": {"what": "matter", "kind": s["kind"]}})
    # a deal paid or due, or pay that did not come; ordinary paydays go by
    for r in conn.execute("""SELECT id,day,text FROM money_news WHERE day>? AND day<=?
                             AND (deal_id IS NOT NULL OR text LIKE '%still owed%' OR text LIKE '%did not pay%') ORDER BY id""", (start, end)):
        found.append({"day": int(r["day"]), "source_kind": "system", "source_id": int(r["id"]), "severity": 3, "reason": str(r["text"]),
                      "metadata": {"what": "money"}})
    return found
```

## engine/claims.py

```python
"""Claims and audiences (information phase 1b, spec 7.1 and 7.5).

A claim is a free-text statement about a subject held by a person or by an audience, with a source (saw, told, read, inferred), a
confidence, a day, and a link to the truth when there is one. Claims about the same subject stand alone. There is no list of traits.

An audience is anything the package's `presence.json` `audiences` defines (an outfit, a man's people, the place he lives in): the
engine knows only the three membership rules (org, circle, home_place), never a name. A named person holds individual claims and what
he holds reaches the audiences he belongs to; an audience holds an impression, the aggregate of what has reached it. The two can
disagree and each draws on the other.

The drivers of 7.1 are weighed in `weigh` and the telling rules, none of them a cap: a costly act outweighs talk; second-hand is
discounted per hop; bad news sticks and trust is slow; closeness resists bad news and a rival spreads it; weight decays with time unless
reinforced (and slowly for a costly bad claim: stigma); a claim spills onto the people connected to the subject; and standing and access
follow the name. Nothing here knows the protagonist: observer and subject are any two people (`tests/i1b_test.py` greps for that).
"""
from __future__ import annotations

import json
import math
import sqlite3

from . import bearing as B

SOURCES = ("saw", "told", "read", "inferred")
WEEK = 7


def enabled(conn: sqlite3.Connection) -> bool:
    return B.enabled(conn) and bool(B.data(conn).get("audiences"))


def _d(conn) -> dict:
    return B.data(conn).get("claims") or {}


def _clip(text, n: int = 200) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _home(conn, aid: int):
    r = conn.execute("SELECT COALESCE(home_location_id,current_location_id) FROM actors WHERE id=?", (int(aid),)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _here(conn, aid: int):
    r = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(aid),)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def kin(conn, subject: int) -> dict[int, float]:
    """The people connected to him by blood, marriage or household (1.0 kin, 0.8 household)."""
    out: dict[int, float] = {}
    for a, b in conn.execute("SELECT actor_a_id,actor_b_id FROM kinship_links WHERE (actor_a_id=? OR actor_b_id=?) AND ended_day IS NULL", (subject, subject)):
        i = int(b) if int(a) == subject else int(a)
        out[i] = 1.0
    for (i,) in conn.execute("SELECT actor_id FROM household_members WHERE status='active' AND household_id IN "
                             "(SELECT household_id FROM household_members WHERE actor_id=? AND status='active')", (subject,)):
        if int(i) != subject:
            out.setdefault(int(i), 0.8)
    return out


# ---- audiences ----------------------------------------------------------------------------------------------

_RULES: dict[str, dict] = {}  # rules a package audience may name besides org, circle and home_place, supplied by another layer


def register_audience_rule(rule: str, *, of_subject, is_member, members) -> None:
    """Supply a membership rule the package's `audiences` may name. of_subject(conn, subject, key, df) -> [audience dicts];
    is_member(conn, actor, aud) -> bool; members(conn, aud) -> [actor ids] (a crowd with no enumerable members gives [])."""
    _RULES[rule] = {"of_subject": of_subject, "is_member": is_member, "members": members}


def _aud(conn, key: str, ref: int, label: str) -> dict:
    r = conn.execute("SELECT id,label FROM audiences WHERE key=? AND ref_id=?", (key, int(ref))).fetchone()
    if r is None:
        aid = int(conn.execute("INSERT INTO audiences(key,ref_id,label) VALUES (?,?,?)", (key, int(ref), label)).lastrowid)
        return {"id": aid, "key": key, "ref": int(ref), "label": label}
    return {"id": int(r["id"]), "key": key, "ref": int(ref), "label": str(r["label"])}


def audiences_of(conn, subject: int) -> list[dict]:
    """The audiences that hold an impression of this subject, by the package's rules."""
    out = []
    for key, df in (B.data(conn).get("audiences") or {}).items():
        rule = df.get("rule")
        if rule == "org":
            for s in B.seats(conn, subject):
                out.append(_aud(conn, key, int(s["org_actor_id"]), f"{df.get('label', key)}: {B.name_of(conn, s['org_actor_id'])}"))
        elif rule == "circle":
            out.append(_aud(conn, key, subject, df.get("label", key)))
        elif rule == "home_place":
            loc = _home(conn, subject)
            if loc is not None:
                nm = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()
                out.append(_aud(conn, key, loc, f"{df.get('label', key)}: {nm[0] if nm else loc}"))
        elif rule in _RULES:
            out.extend(_RULES[rule]["of_subject"](conn, subject, key, df))
    return out


def _rule(conn, aud: dict) -> str | None:
    return ((B.data(conn).get("audiences") or {}).get(aud["key"]) or {}).get("rule")


def is_member(conn, actor: int, aud: dict) -> bool:
    rule = _rule(conn, aud)
    if rule == "org":
        return conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (int(actor), aud["ref"])).fetchone() is not None
    if rule == "circle":
        return int(actor) in kin(conn, aud["ref"])
    if rule == "home_place":
        return _home(conn, actor) == aud["ref"]
    if rule in _RULES:
        return bool(_RULES[rule]["is_member"](conn, int(actor), aud))
    return False


def members(conn, aud: dict) -> list[int]:
    """The named members (a crowd with no enumerable members is held as an impression only)."""
    rule = _rule(conn, aud)
    if rule == "org":
        return [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active'", (aud["ref"],))]
    if rule == "circle":
        return list(kin(conn, aud["ref"]))
    if rule in _RULES:
        return list(_RULES[rule]["members"](conn, aud))
    return []


# ---- weighing -----------------------------------------------------------------------------------------------

def _eff(conn, c, day: int) -> float:
    """What a claim still counts for: its confidence, decayed with age unless reinforced (a costly bad claim decays slowly)."""
    age = max(0, int(day) - int(c["day"]))
    hl = B.fig(conn, "claim_half_life_days") * (B.fig(conn, "stigma_mult") if int(c["costly"]) and float(c["valence"]) < 0 else 1.0)
    return float(c["confidence"]) * 0.5 ** (age / hl)


def weigh(conn, c, day: int) -> float:
    """A claim's weight: decayed confidence, bad news heavier, a costly act heavier than talk."""
    return (_eff(conn, c, day) * (B.fig(conn, "bad_weight") if float(c["valence"]) < 0 else B.fig(conn, "good_weight"))
            * (B.fig(conn, "costly_mult") if int(c["costly"]) else 1.0))


def _aggregate(conn, rows, day: int) -> tuple[float, float, float]:
    """(regard, force, mass) from claims: each -1..1, shrunk toward neutral by the prior so a few claims move little."""
    num = fnum = den = 0.0
    for c in rows:
        w = weigh(conn, c, day)
        num += float(c["valence"]) * w
        fnum += float(c["force"]) * w
        den += w
    prior = B.fig(conn, "prior_mass")
    return num / (den + prior), fnum / (den + prior), den


def impression(conn, aud: dict, subject: int, day: int | None = None) -> dict:
    day = B._day(conn) if day is None else int(day)
    rows = conn.execute("SELECT * FROM claims WHERE holder_kind='audience' AND holder_id=? AND subject_actor_id=?", (aud["id"], int(subject))).fetchall()
    regard, force, mass = _aggregate(conn, rows, day)
    return {"audience": aud["key"], "label": aud["label"], "regard": regard, "force": force, "mass": mass}


def own_regard(conn, actor: int, subject: int, day: int | None = None) -> tuple[float, float, float]:
    day = B._day(conn) if day is None else int(day)
    rows = conn.execute("SELECT * FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=?", (int(actor), int(subject))).fetchall()
    return _aggregate(conn, rows, day)


def regard_of(conn, actor: int, subject: int, day: int | None = None) -> tuple[float, float, float]:
    """(regard, force, mass): what he makes of the subject, his own claims drawing on the impression of the audiences he belongs to."""
    day = B._day(conn) if day is None else int(day)
    r, f, m = own_regard(conn, actor, subject, day)
    imps = [impression(conn, a, subject, day) for a in audiences_of(conn, subject) if is_member(conn, actor, a)]
    imps = [i for i in imps if i["mass"] > 0]
    if imps:
        pull = B.fig(conn, "audience_pull")
        ar = sum(i["regard"] for i in imps) / len(imps)
        af = sum(i["force"] for i in imps) / len(imps)
        return (1 - pull) * r + pull * ar, (1 - pull) * f + pull * af, m + sum(i["mass"] for i in imps)
    return r, f, m


# ---- recording ----------------------------------------------------------------------------------------------

def _effect(conn, event_type: str):
    for e in _d(conn).get("event_effects") or []:
        if any(w in str(event_type).lower() for w in e.get("match") or []):
            return e
    return None


def _per(table: dict | None, keys) -> float:
    table = table or {}
    for k in keys:
        if k in table:
            return float(table[k])
    return float(table.get("default", 0.0))


def _veto(conn, subject, holder_kind, holder_id, source, confidence, truth_event_id) -> None:
    if source not in SOURCES:
        raise ValueError(f"a claim's source is one of {SOURCES}")
    if not 0.0 <= float(confidence) <= 1.0:
        raise ValueError("confidence runs from 0 to 1")
    if conn.execute("SELECT 1 FROM actors WHERE id=?", (int(subject),)).fetchone() is None:
        raise ValueError("there is no such subject")
    if holder_kind == "actor":
        if conn.execute("SELECT 1 FROM actors WHERE id=?", (int(holder_id),)).fetchone() is None:
            raise ValueError("there is no such holder")
        if not B._alive(conn, int(holder_id)):
            raise ValueError("the dead hold no claims")
    elif conn.execute("SELECT 1 FROM audiences WHERE id=?", (int(holder_id),)).fetchone() is None:
        raise ValueError("there is no such audience")
    if truth_event_id is not None:
        ev = conn.execute("SELECT source_actor_id FROM events WHERE id=?", (int(truth_event_id),)).fetchone()
        if ev is None:
            raise ValueError("that happening is not in the record")
        about = {int(r[0]) for r in conn.execute("SELECT actor_id FROM event_targets WHERE event_id=?", (int(truth_event_id),))}
        if ev[0] is not None:
            about.add(int(ev[0]))
        if about and int(subject) not in about:
            raise ValueError("that happening is not about this subject")
        if source == "saw" and holder_kind == "actor":
            saw = {int(r[0]) for r in conn.execute("SELECT actor_id FROM event_witnesses WHERE event_id=?", (int(truth_event_id),))} | about
            if int(holder_id) not in saw:
                raise ValueError("he was not there: a claim that he saw it contradicts the record")


def record(conn, subject: int, holder_kind: str, holder_id: int, text: str, source: str, confidence: float, valence: float = 0.0,
           force: float = 0.0, costly: bool = False, *, source_ref: int | None = None, hops: int = 0, truth_event_id: int | None = None,
           knowledge_id: int | None = None, day: int | None = None, spilled: bool = False, check: bool = True) -> int:
    """Hold a claim (or reinforce the same one). Reaching a named holder also reaches the audiences he belongs to; an audience's claim
    spills onto the subject's own people. Vetoes only contradictions with established fact (`check`)."""
    day = B._day(conn) if day is None else int(day)
    text = _clip(text)
    if not text:
        raise ValueError("a claim needs its text")
    if check:
        _veto(conn, subject, holder_kind, holder_id, source, confidence, truth_event_id)
    old = conn.execute("SELECT * FROM claims WHERE subject_actor_id=? AND holder_kind=? AND holder_id=? AND text=?",
                       (int(subject), holder_kind, int(holder_id), text)).fetchone()
    if old is not None:
        conf = 1.0 - (1.0 - float(old["confidence"])) * (1.0 - float(confidence))
        conn.execute("UPDATE claims SET confidence=?,day=?,hops=MIN(hops,?),costly=MAX(costly,?),source=CASE WHEN ?='saw' THEN 'saw' ELSE source END,"
                     "truth_event_id=COALESCE(truth_event_id,?),knowledge_id=COALESCE(knowledge_id,?) WHERE id=?",
                     (conf, day, int(hops), int(bool(costly)), source, truth_event_id, knowledge_id, int(old["id"])))
        cid, fresh = int(old["id"]), False
    else:
        cid = int(conn.execute(
            """INSERT INTO claims(subject_actor_id,holder_kind,holder_id,text,source,source_ref,hops,confidence,valence,force,costly,truth_event_id,knowledge_id,
                                  spilled,first_day,day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (int(subject), holder_kind, int(holder_id), text, source, source_ref, int(hops), float(confidence), float(valence), float(force), int(bool(costly)),
             truth_event_id, knowledge_id, int(spilled), day, day)).lastrowid)
        fresh = True
    c = conn.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    if not spilled:
        if holder_kind == "actor" and int(holder_id) != int(subject):
            _reach_audiences(conn, c, day)
        elif holder_kind == "audience":
            _spill(conn, c, day)
    return cid


def _reach_audiences(conn, c, day: int) -> None:
    share = B.fig(conn, "audience_share")
    for a in audiences_of(conn, int(c["subject_actor_id"])):
        if is_member(conn, int(c["holder_id"]), a):
            record(conn, int(c["subject_actor_id"]), "audience", a["id"], c["text"], "told", float(c["confidence"]) * share, float(c["valence"]), float(c["force"]),
                   bool(c["costly"]), source_ref=int(c["holder_id"]), hops=int(c["hops"]) + 1, truth_event_id=c["truth_event_id"], day=day, check=False)


def _spill(conn, c, day: int) -> None:
    """What an audience holds of a man reaches the people connected to him (his kin and household) and the outfit he belongs to."""
    if abs(float(c["valence"])) <= 0.0:
        return
    share = B.fig(conn, "spill_share")
    s = int(c["subject_actor_id"])
    name = B.name_of(conn, s)
    targets = {i: 1.0 for i in kin(conn, s)}
    for seat in B.seats(conn, s):
        targets.setdefault(int(seat["org_actor_id"]), 0.7)
    for t, w in targets.items():
        record(conn, t, "audience", int(c["holder_id"]), f"{name}'s own: {c['text']}", "inferred", float(c["confidence"]) * share * w, float(c["valence"]) * share,
               float(c["force"]) * share, bool(c["costly"]), source_ref=s, hops=int(c["hops"]) + 1, truth_event_id=c["truth_event_id"], day=day, spilled=True, check=False)


def propose(conn, text: str, subject: int, *, holder: str | int | None = None, source: str = "inferred", confidence: float = 0.6, valence: float = 0.0,
            force: float = 0.0, costly: bool = False, truth_event_id: int | None = None, day: int | None = None) -> dict:
    """The GM proposes a claim. `holder` is an audience key (of the subject), a person's name or id, or None (the street: the
    subject's home-place audience). The engine vetoes only a contradiction with established fact."""
    subject = int(subject)
    aud = audiences_of(conn, subject)
    hk, hid, hname = "audience", None, None
    if holder is None:
        pick = [a for a in aud if _rule(conn, a) == "home_place"] or aud
        if not pick:
            raise ValueError("this subject has no audience that could hold it")
        hid, hname = pick[0]["id"], pick[0]["label"]
    elif isinstance(holder, str) and not holder.lstrip("-").isdigit() and any(a["key"] == holder for a in aud):
        a = next(a for a in aud if a["key"] == holder)
        hid, hname = a["id"], a["label"]
    else:
        hk = "actor"
        if isinstance(holder, int) or str(holder).isdigit():
            hid = int(holder)
        else:
            r = conn.execute("SELECT id FROM actors WHERE name=? COLLATE NOCASE", (str(holder),)).fetchone()
            if r is None:
                raise ValueError(f"no audience or person is called {holder}")
            hid = int(r[0])
        hname = B.name_of(conn, hid)
    cid = record(conn, subject, hk, int(hid), text, source, confidence, valence, force, costly, truth_event_id=truth_event_id, day=day)
    return {"saved": "claim", "summary": f"{hname} holds of {B.name_of(conn, subject)}: {_clip(text, 80)}", "claim_id": cid}


# ---- hearing and telling ------------------------------------------------------------------------------------

def _rel(conn, a: int, b: int):
    return conn.execute("SELECT * FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(a), int(b))).fetchone()


def hear(conn, holder: int, subject: int, text: str, confidence: float, valence: float, force: float, costly: bool, source: str, *, teller: int | None = None,
         hops: int = 1, truth_event_id: int | None = None, knowledge_id: int | None = None, day: int | None = None) -> int | None:
    """A named person takes in a claim he did not see for himself: discounted by the teller's credibility (his trust in him), closeness to the
    subject resisting bad news, resentment of the subject discounting good news."""
    if int(holder) == int(subject) and teller is None:
        return None
    conf = float(confidence)
    if teller is not None:
        r = _rel(conn, holder, teller)
        trust = float(r["trust"]) if r else 0.0
        conf *= max(B.fig(conn, "cred_floor"), min(1.0, 0.5 + trust / 200.0))
    rs = _rel(conn, holder, subject)
    if rs is not None and int(holder) != int(subject):
        close = max(0.0, (float(rs["affection"]) + float(rs["trust"])) / 200.0)
        resent = max(0.0, float(rs["resentment"]) / 100.0)
        if valence < 0:
            conf *= 1.0 - B.fig(conn, "resist") * close
        elif valence > 0:
            conf *= 1.0 - B.fig(conn, "rival_discount") * resent
    cid = record(conn, int(subject), "actor", int(holder), text, source, max(0.0, min(1.0, conf)), valence, force, costly, source_ref=teller, hops=hops,
                 truth_event_id=truth_event_id, knowledge_id=knowledge_id, day=day, check=False)
    if int(holder) == int(subject) and valence < 0:  # he hears of himself what damages him: it goes on his list
        from . import news_choices
        news_choices.hears_of_himself(conn, cid, B._day(conn) if day is None else int(day))
    return cid


def _state(conn, key: str) -> int:
    r = conn.execute("SELECT value FROM claims_state WHERE key=?", (key,)).fetchone()
    return int(r[0]) if r else -1


def _set_state(conn, key: str, v: int) -> None:
    conn.execute("INSERT INTO claims_state(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, int(v)))


def _event_subject(conn, e) -> int | None:
    if e["source_actor_id"] is not None:
        return int(e["source_actor_id"])
    r = conn.execute("SELECT actor_id FROM event_targets WHERE event_id=? ORDER BY actor_id LIMIT 1", (int(e["id"]),)).fetchone()
    return int(r[0]) if r else None


def _keys_for(conn, actor: int, subject: int) -> list[str]:
    return [a["key"] for a in audiences_of(conn, subject) if is_member(conn, actor, a)]


def from_events(conn, day: int) -> int:
    """Happenings the package says colour a name become claims: held first-hand by those who were there, and (when public) by the
    audiences the subject belongs to, in proportion to how far a public act reaches."""
    n = 0
    cur = _state(conn, "event_cursor")
    if cur < 0:  # first pass: what is older than a week is history, not news
        cur = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM events WHERE day<=?", (int(day) - WEEK,)).fetchone()[0])
    for e in conn.execute("SELECT id,day,event_type,title,summary,severity,source_actor_id FROM events WHERE id>? ORDER BY id", (cur,)).fetchall():
        eff = _effect(conn, e["event_type"])
        subject = _event_subject(conn, e) if eff else None
        if eff is None or subject is None:
            continue
        text = e["summary"] if e["summary"] and e["summary"] != e["title"] else e["title"]
        costly = bool(eff.get("costly"))
        for w in conn.execute("SELECT actor_id,witness_type,confidence FROM event_witnesses WHERE event_id=?", (int(e["id"]),)).fetchall():
            h = int(w["actor_id"])
            if h == subject or not B._alive(conn, h):
                continue
            keys = _keys_for(conn, h, subject)
            record(conn, subject, "actor", h, text, "saw" if w["witness_type"] in ("participant", "observer", "target", "source") else "told",
                   float(w["confidence"]), _per(eff.get("valence"), keys), _per(eff.get("force"), keys), costly, truth_event_id=int(e["id"]), day=int(e["day"]), check=False)
            n += 1
        vis = conn.execute("SELECT visibility FROM event_information WHERE event_id=?", (int(e["id"]),)).fetchone()
        if vis and vis[0] == "public":
            reach = B.fig(conn, "public_reach_base") + B.fig(conn, "public_reach_sev") * int(e["severity"])
            for a in audiences_of(conn, subject):
                record(conn, subject, "audience", a["id"], text, "told", min(1.0, reach), _per(eff.get("valence"), [a["key"]]), _per(eff.get("force"), [a["key"]]),
                       costly, hops=1, truth_event_id=int(e["id"]), day=int(e["day"]), check=False)
                n += 1
        cur = int(e["id"])
    _set_state(conn, "event_cursor", cur)
    return n


def from_incidents(conn, day: int) -> int:
    """The organisations' own happenings (an informing, an arrest, a killing) are claims too: held first-hand by the man it was done to and the
    head it was raised to, and by the subject's audiences when the package says such a thing is public."""
    cur = _state(conn, "incident_cursor")
    if cur < 0:
        cur = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM org_incidents WHERE day<=?", (int(day) - WEEK,)).fetchone()[0])
    n = 0
    for i in conn.execute("SELECT * FROM org_incidents WHERE id>? ORDER BY id", (cur,)).fetchall():
        cur = int(i["id"])
        eff = _effect(conn, i["kind"])
        s = i["offender_actor_id"]
        if eff is None or s is None:
            continue
        s = int(s)
        try:
            meta = json.loads(i["metadata_json"] or "{}")
        except ValueError:
            meta = {}
        text = meta.get("summary") or (f"{B.name_of(conn, s)} {i['kind']}" + (f": {B.name_of(conn, i['victim_actor_id'])}" if i["victim_actor_id"] is not None else ""))
        holders = {int(i["victim_actor_id"])} if i["victim_actor_id"] is not None else set()
        if i["raised_to_org_actor_id"] is not None:
            from .orgs import head_of
            h = head_of(conn, int(i["raised_to_org_actor_id"]))
            if h is not None:
                holders.add(int(h))
        for h in holders:
            if h != s and B._alive(conn, h):
                keys = _keys_for(conn, h, s)
                record(conn, s, "actor", h, text, "saw" if h == i["victim_actor_id"] else "told", 0.9, _per(eff.get("valence"), keys), _per(eff.get("force"), keys),
                       bool(eff.get("costly")), day=int(i["day"]), check=False)
                n += 1
        if eff.get("public"):
            reach = B.fig(conn, "public_reach_base") + B.fig(conn, "public_reach_sev") * (1 + 2 * int(i["matters"]))
            for a in audiences_of(conn, s):
                record(conn, s, "audience", a["id"], text, "told", min(1.0, reach), _per(eff.get("valence"), [a["key"]]), _per(eff.get("force"), [a["key"]]),
                       bool(eff.get("costly")), hops=1, day=int(i["day"]), check=False)
                n += 1
    _set_state(conn, "incident_cursor", cur)
    return n


def from_knowledge(conn, day: int) -> int:
    """What people come to know of those happenings (word of mouth, the existing rumour layer) becomes second-hand claims."""
    cur = _state(conn, "knowledge_cursor")
    if cur < 0:
        cur = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM knowledge WHERE learned_day<=?", (int(day) - WEEK,)).fetchone()[0])
    n = 0
    for k in conn.execute("SELECT id,knower_actor_id,belief_text,confidence,truth_event_id,learned_day FROM knowledge WHERE id>? AND truth_event_id IS NOT NULL ORDER BY id", (cur,)).fetchall():
        cur = int(k["id"])
        e = conn.execute("SELECT id,day,event_type,title,summary,source_actor_id FROM events WHERE id=?", (int(k["truth_event_id"]),)).fetchone()
        eff = _effect(conn, e["event_type"]) if e else None
        subject = _event_subject(conn, e) if eff else None
        if subject is None:
            continue
        text = e["summary"] if e["summary"] and e["summary"] != e["title"] else e["title"]
        prov = conn.execute("SELECT source_kind FROM knowledge_provenance WHERE knowledge_id=? ORDER BY id LIMIT 1", (int(k["id"]),)).fetchone()
        src = "read" if prov and prov[0] == "channel" else "told"
        keys = _keys_for(conn, int(k["knower_actor_id"]), subject)
        if hear(conn, int(k["knower_actor_id"]), subject, text, float(k["confidence"]) * B.fig(conn, "hop_factor"), _per(eff.get("valence"), keys),
                _per(eff.get("force"), keys), bool(eff.get("costly")), src, teller=None, hops=1, truth_event_id=int(e["id"]), knowledge_id=int(k["id"]), day=int(k["learned_day"])) is not None:
            n += 1
    _set_state(conn, "knowledge_cursor", cur)
    return n


def spread(conn, day: int) -> int:
    """Fresh claims are told on, person to person: to those he knows, more readily when it is bad news, more readily by a rival, each
    hop discounted. A subject can hear what is said of him this way."""
    n = 0
    window, hop = int(B.fig(conn, "tell_window")), B.fig(conn, "hop_factor")
    fam_min = B.fig(conn, "tell_fam_min")
    fresh = conn.execute("SELECT * FROM claims WHERE holder_kind='actor' AND day>=? AND day<=? AND holder_id<>subject_actor_id ORDER BY id", (int(day) - window, int(day))).fetchall()
    for c in fresh:
        h, s = int(c["holder_id"]), int(c["subject_actor_id"])
        if not B._alive(conn, h):
            continue
        rs = _rel(conn, h, s)
        rival = 1.0 + (B.fig(conn, "rival_boost") if rs is not None and float(rs["resentment"]) >= 30 and float(c["valence"]) < 0 else 0.0)
        eff = _eff(conn, c, day)
        base = B.fig(conn, "tell_rate") * (0.3 + abs(float(c["valence"]))) * (1.0 + (B.fig(conn, "tell_bad_bonus") if float(c["valence"]) < 0 else 0.0)) * rival
        draw = B._rng(conn, "tell", c["id"], day)  # one generator per claim per week, a draw for each neighbour in id order (a generator per pair was 700k a year)
        for r in conn.execute("SELECT actor_b_id,familiarity FROM relationships WHERE actor_a_id=? AND familiarity>=? ORDER BY actor_b_id", (h, fam_min)).fetchall():
            t = int(r["actor_b_id"])
            if draw.random() >= base * (0.5 + float(r["familiarity"]) / 100.0):
                continue
            if not B._alive(conn, t):
                continue
            if hear(conn, t, s, c["text"], eff * hop, float(c["valence"]), float(c["force"]), bool(c["costly"]), "told", teller=h, hops=int(c["hops"]) + 1,
                    truth_event_id=c["truth_event_id"], day=day) is not None:
                n += 1
    return n


def prune(conn, day: int) -> int:
    """A claim faded below the forgetting weight is forgotten (storage only: whatever is still weighed is kept)."""
    gone = []
    floor = B.fig(conn, "forget_below")
    for c in conn.execute("SELECT * FROM claims WHERE day<?", (int(day) - int(B.fig(conn, "claim_half_life_days")),)).fetchall():
        if _eff(conn, c, day) < floor:
            gone.append(int(c["id"]))
    for i in range(0, len(gone), 500):
        conn.execute(f"DELETE FROM claims WHERE id IN ({','.join('?' * len(gone[i:i + 500]))})", gone[i:i + 500])
    return len(gone)


# ---- what the claims feed ---------------------------------------------------------------------------------

def read_for(conn, observer: int, subject: int) -> dict | None:
    """What the observer holds of the subject, for the room read: where it comes from (saw, heard, read, inferred), how sure, the strongest
    thing he holds, and his regard. None when he holds nothing."""
    day = B._day(conn)
    rows = conn.execute("SELECT * FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=?", (int(observer), int(subject))).fetchall()
    reg, force, mass = regard_of(conn, observer, subject, day)
    if not rows:
        if mass <= 0:
            return None
        return {"source": "heard", "sure": min(1.0, mass), "holds": None, "regard": reg, "force": force}
    top = max(rows, key=lambda c: weigh(conn, c, day))
    word = {"saw": "saw", "told": "heard", "read": "read", "inferred": "inferred"}[top["source"]]
    return {"source": word, "sure": _eff(conn, top, day), "holds": top["text"], "regard": reg, "force": force}


def claims_about(conn, subject: int, holder: int | None = None, limit: int = 8) -> list[dict]:
    """Claims held of a subject: by one person, else by the audiences (for lookup)."""
    day = B._day(conn)
    if holder is not None:
        rows = conn.execute("SELECT * FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=?", (int(holder), int(subject))).fetchall()
        who = lambda c: B.name_of(conn, holder)
    else:
        rows = conn.execute("SELECT * FROM claims WHERE holder_kind='audience' AND subject_actor_id=?", (int(subject),)).fetchall()
        labels = {int(r["id"]): r["label"] for r in conn.execute("SELECT id,label FROM audiences")}
        who = lambda c: labels.get(int(c["holder_id"]), "?")
    rows = sorted(rows, key=lambda c: -weigh(conn, c, day))[:limit]
    return [{"holder": who(c), "claim": c["text"], "source": c["source"], "sure": round(_eff(conn, c, day), 2), "day": int(c["day"])} for c in rows]


def deterrence(conn, subject: int, audience: dict | None = None) -> float:
    """How formidable an audience holds him to be, -1 (a man who lets slights pass) to 1. Answering a slight is partly weighed against
    looking weak, so a man held weak has more reason to answer."""
    auds = [audience] if audience else audiences_of(conn, subject)
    imps = [impression(conn, a, subject) for a in auds]
    imps = [i for i in imps if i["mass"] > 0]
    return sum(i["force"] for i in imps) / len(imps) if imps else 0.0


# ---- the weekly pass ----------------------------------------------------------------------------------------

def _pull_standing(conn, subject: int, day: int) -> int:
    """Seat standing follows the outfit's own impression of the man: it moves a share of the way to where the men of the outfit hold him."""
    n = 0
    pull, prior = B.fig(conn, "standing_pull"), B.fig(conn, "standing_prior")
    for a in audiences_of(conn, subject):
        if _rule(conn, a) != "org":
            continue
        imp = impression(conn, a, subject, day)
        if imp["mass"] <= 0:
            continue
        share = imp["mass"] / (imp["mass"] + prior)
        seat = conn.execute("SELECT id,standing FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (subject, a["ref"])).fetchone()
        if seat is None:
            continue
        st = float(seat["standing"])
        tgt = (imp["regard"] + 1.0) / 2.0
        conn.execute("UPDATE org_seats SET standing=? WHERE id=?", (max(0.0, min(1.0, st + pull * share * (tgt - st))), int(seat["id"])))
        n += 1
    return n


def _access(conn, subject: int, day: int) -> int:
    """Reputation is access: a name held in regard draws approaches (an offer, a tip, a favour asked), as a happening that reaches him."""
    best = None
    for a in audiences_of(conn, subject):
        imp = impression(conn, a, subject, day)
        if imp["regard"] >= B.fig(conn, "access_regard") and (best is None or imp["regard"] > best["regard"]):
            best = imp
    if best is None:
        return 0
    p = B.fig(conn, "access_rate") * best["regard"] * best["mass"] / (best["mass"] + 1.0)
    if B._rng(conn, "access", subject, day).random() >= p:
        return 0
    B._event(conn, day, "reputation_access", f"{B.name_of(conn, subject)} is sought out",
             f"His name has weight with {best['label']}: someone comes to him with an approach, a favour asked or a tip.", subject)
    return 1


def _react(conn, subject: int, day: int) -> int:
    """The people connected to him meet what is held of him in their own days (the school gate, the shops, the parish): who was there, how
    they treated the connected person, what comes home. Same machinery for anyone's family."""
    fresh = conn.execute("SELECT * FROM claims WHERE holder_kind='audience' AND subject_actor_id=? AND day>=? AND spilled=0 AND ABS(valence)>0 ORDER BY id", (subject, int(day) - WEEK)).fetchall()
    if not fresh:
        return 0
    salience = sum(float(c["confidence"]) * abs(float(c["valence"])) for c in fresh)
    top = max(fresh, key=lambda c: weigh(conn, c, day))
    n = 0
    rate = B.fig(conn, "react_rate")
    for person in sorted(kin(conn, subject)):
        if not B._alive(conn, person):
            continue
        if B._rng(conn, "react", subject, person, day).random() >= 1.0 - math.exp(-rate * salience):
            continue
        loc = _here(conn, person)
        around = [int(r[0]) for r in conn.execute("SELECT id FROM actors WHERE current_location_id=? AND id NOT IN (?,?) AND status<>'dead' ORDER BY id", (loc, subject, person))] if loc is not None else []
        rng = B._rng(conn, "react_present", subject, person, day)
        rng.shuffle(around)
        holders = [p for p in around if conn.execute("SELECT 1 FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=?", (p, subject)).fetchone()]
        present = (holders + [p for p in around if p not in holders])[: int(B.fig(conn, "present_n"))]
        if present:
            regs = [regard_of(conn, p, subject, day)[0] for p in present]
            reg = sum(regs) / len(regs)
            fears = [float(r["fear"]) for p in present for r in [_rel(conn, p, subject)] if r is not None]
            fear = sum(fears) / len(fears) if fears else 0.0
        else:
            reg, fear = float(top["valence"]), 0.0
        t = B.fig(conn, "react_regard_t")
        band = "afraid" if fear >= B.fig(conn, "react_fear_t") else "cold" if reg <= -t else "warm" if reg >= t else "mixed"
        phrase = (_d(conn).get("circle_phrases") or {}).get(band, "watch")
        place = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone() if loc is not None else None
        who = ", ".join(B.name_of(conn, p) for p in present) or "people there"
        text = (f"{B.name_of(conn, person)} at {place[0] if place else 'the day'}: {who} {phrase} them over what is said of {B.name_of(conn, subject)}"
                f" ({_clip(top['text'], 90)})")
        routing = "first_hand" if _here(conn, subject) == loc and loc is not None else "cutaway"
        conn.execute("INSERT INTO circle_reactions(day,person_actor_id,subject_actor_id,location_id,claim_id,regard,fear,present_json,text,routing) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (day, person, subject, loc, int(top["id"]), reg, fear, "[" + ",".join(map(str, present)) + "]", text, routing))
        for p in present:  # the spill driver: how they hold him moves how they treat his people
            from .relationships import adjust_relationship
            adjust_relationship(conn, p, person, day, stance_delta=B.fig(conn, "spill_stance") * reg, fear_delta=max(0.0, fear / 100.0 * 2.0))
        if reg <= -t:
            from .relationships import adjust_relationship
            adjust_relationship(conn, person, subject, day, resentment_delta=B.fig(conn, "react_resent") * min(1.0, -reg))
        n += 1
    return n


def _come_home(conn, day: int) -> int:
    """A reaction nobody told him of reaches him when he and the person meet again (a wife tells him what was said). He then holds it
    himself: a named man hears what is said of him."""
    n = 0
    for r in conn.execute("SELECT * FROM circle_reactions WHERE told_day IS NULL AND routing='cutaway'").fetchall():
        if _here(conn, int(r["person_actor_id"])) is not None and _here(conn, int(r["person_actor_id"])) == _here(conn, int(r["subject_actor_id"])) and B._alive(conn, int(r["subject_actor_id"])):
            conn.execute("UPDATE circle_reactions SET told_day=? WHERE id=?", (day, int(r["id"])))
            c = conn.execute("SELECT * FROM claims WHERE id=?", (r["claim_id"],)).fetchone() if r["claim_id"] is not None else None
            if c is not None:
                hear(conn, int(r["subject_actor_id"]), int(r["subject_actor_id"]), SAID + c["text"], float(c["confidence"]), float(c["valence"]), float(c["force"]),
                     bool(c["costly"]), "told", teller=int(r["person_actor_id"]), hops=1, truth_event_id=c["truth_event_id"], day=day)
            n += 1
    return n


SAID = "it is said of him: "


def deliveries(conn, me: int, day: int) -> list[tuple[str, str, str]]:
    """(key, kind, text) for what reaches him through the people around him: a reaction he was there for, what came home, and what
    people told him of himself. Each is entered once by its key in the ledger; here the state is only marked."""
    out = []
    for r in conn.execute("SELECT * FROM circle_reactions WHERE subject_actor_id=? AND entered_day IS NULL AND (routing='first_hand' OR told_day IS NOT NULL) ORDER BY id", (int(me),)).fetchall():
        conn.execute("UPDATE circle_reactions SET entered_day=? WHERE id=?", (day, int(r["id"])))
        out.append((f"reaction:{r['id']}", "first_hand" if r["routing"] == "first_hand" else "home", r["text"]))
    for c in conn.execute("SELECT id,text,source_ref FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=? AND source_ref IS NOT NULL AND text NOT LIKE ? ESCAPE '!' ORDER BY id",
                          (int(me), int(me), SAID.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%")).fetchall():
        out.append((f"claim:{c['id']}", "about_him", f"{B.name_of(conn, c['source_ref'])} lets him know what is said of him: {c['text']}"))
    return out


def cutaways(conn, me: int, day: int) -> list[dict]:
    """What his people met that he was not there for and has not been told: for the GM to write a cutaway, marked as outside his
    knowledge (he learns it only if it comes home to him)."""
    out = []
    for r in conn.execute("SELECT * FROM circle_reactions WHERE subject_actor_id=? AND routing='cutaway' AND told_day IS NULL AND cutaway_day IS NULL ORDER BY id", (int(me),)).fetchall():
        conn.execute("UPDATE circle_reactions SET cutaway_day=? WHERE id=?", (day, int(r["id"])))
        out.append({"cutaway": r["text"], "note": "outside his knowledge: he hears of it only if it is told or comes home"})
    return out


def weekly(conn, day: int) -> dict:
    """The week's pass, run with the organisation lifecycle's: happenings and word of mouth become claims, claims are told on, the old
    forgotten; for everyone whose name moved, impressions settle, seat standing follows, the people around them meet it, approaches come."""
    if not enabled(conn):
        return {}
    out = {"claims_from_events": from_events(conn, day)}
    out["claims_from_incidents"] = from_incidents(conn, day)
    out["claims_from_knowledge"] = from_knowledge(conn, day)
    out["claims_told"] = spread(conn, day)
    out["claims_forgotten"] = prune(conn, day)
    subjects = [int(r[0]) for r in conn.execute("SELECT DISTINCT subject_actor_id FROM claims WHERE day>=? ORDER BY subject_actor_id", (int(day) - WEEK,))]
    st = rx = ac = 0
    for s in subjects:
        if not B._alive(conn, s):
            continue
        for a in audiences_of(conn, s):
            imp = impression(conn, a, s, day)
            conn.execute("INSERT INTO impressions(audience_id,subject_actor_id,regard,force,mass,day) VALUES (?,?,?,?,?,?) ON CONFLICT(audience_id,subject_actor_id) DO UPDATE SET "
                         "regard=excluded.regard,force=excluded.force,mass=excluded.mass,day=excluded.day", (a["id"], s, imp["regard"], imp["force"], imp["mass"], int(day)))
        st += _pull_standing(conn, s, day)
        rx += _react(conn, s, day)
        ac += _access(conn, s, day)
    out["claims_standing_moved"], out["claims_reactions"], out["claims_access"] = st, rx, ac
    out["claims_came_home"] = _come_home(conn, day)
    return out


def _register() -> None:
    from . import org_lifecycle
    org_lifecycle.on_week(weekly)


_register()
```

## engine/findings.py

```python
"""What asking and looking into things turns up: findings come from what the world holds, never from the GM's invention.

`answers` reads what one person knows; `investigate` gathers what a person, a place, a business, an outfit or a bare question
leaves traces of (public events, standing arrangements, talk, and, with time and luck, what is kept quiet).
Whatever is found is written to the protagonist's knowledge, so it stays found. Nothing found is said as nothing found.
"""
from __future__ import annotations

import hashlib
import random
import re
import sqlite3

_STOP = {"the", "and", "for", "that", "with", "what", "who", "whom", "how", "about", "into", "from", "his", "her", "their", "this",
         "have", "has", "any", "ask", "tell", "know", "where", "when", "why", "was", "were", "are", "you", "your", "him", "them"}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _terms(text: str) -> list[str]:
    return [w for w in dict.fromkeys(re.findall(r"[a-z']{3,}", str(text or "").lower())) if w not in _STOP][:6]


def _like(w: str) -> str:
    return "%" + w.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def tell(conn: sqlite3.Connection, listener: int, texts: list[str], *, source: int | None = None, confidence: float = 0.8) -> int:
    """The listener now knows these things (told by `source`). Returns how many were written."""
    day = _day(conn)
    n = 0
    for t in texts:
        t = " ".join(str(t or "").split())[:300]
        if not t:
            continue
        key = "told:" + hashlib.sha1(t.lower().encode()).hexdigest()[:12]
        conn.execute("""INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day) VALUES (?,?,?,?,?)
                        ON CONFLICT(knower_actor_id,fact_key) DO UPDATE SET confidence=MAX(knowledge.confidence,excluded.confidence),learned_day=excluded.learned_day""",
                     (listener, key, t, confidence, day))
        n += 1
    return n


def answers(conn: sqlite3.Connection, holder: int, topics, limit: int = 5) -> list[str]:
    """What `holder` knows that bears on the topics (a string or a list of strings), most confident first."""
    words = _terms(" ".join(topics) if isinstance(topics, (list, tuple)) else topics)
    if not words:
        return []
    clause = " OR ".join("belief_text LIKE ? ESCAPE '!'" for _ in words)
    rows = conn.execute(f"SELECT belief_text FROM knowledge WHERE knower_actor_id=? AND ({clause}) ORDER BY confidence DESC,learned_day DESC,id DESC LIMIT ?",
                        (holder, *[_like(w) for w in words], limit)).fetchall()
    return [str(r[0]) for r in rows]


def learn(conn: sqlite3.Connection, learner: int, texts: list[str], *, key: str, confidence: float = 0.7) -> int:
    day = _day(conn)
    n = 0
    for i, t in enumerate(texts):
        conn.execute("""INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day) VALUES (?,?,?,?,?)
                        ON CONFLICT(knower_actor_id,fact_key) DO UPDATE SET belief_text=excluded.belief_text,confidence=excluded.confidence,learned_day=excluded.learned_day""",
                     (learner, f"{key}:{i}", " ".join(t.split())[:300], confidence, day))
        n += 1
    return n


def _talk(conn: sqlite3.Connection, name: str, place: int | None, limit: int = 3) -> list[str]:
    """What people in the same place are saying: distinct beliefs of locals that name the subject."""
    if not name:
        return []
    rows = conn.execute(
        """SELECT DISTINCT k.belief_text FROM knowledge k JOIN actors a ON a.id=k.knower_actor_id
           WHERE k.belief_text LIKE ? ESCAPE '!' AND k.belief_text NOT LIKE 'Investigation concerning%'
             AND (a.current_location_id=? OR ? IS NULL) ORDER BY k.confidence DESC,k.id DESC LIMIT ?""",
        (_like(name), place, place, limit)).fetchall()
    return ["People say: " + str(r[0]) for r in rows]


def _ago(conn: sqlite3.Connection, day: int) -> str:
    n = _day(conn) - int(day)
    return "Recently" if n <= 10 else "Some weeks ago" if n <= 60 else "Some months ago" if n <= 400 else "Years ago"


def _events_about(conn: sqlite3.Connection, actor: int, limit: int = 4) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT e.day,e.title FROM events e LEFT JOIN event_targets t ON t.event_id=e.id
           WHERE (e.source_actor_id=? OR t.actor_id=?) AND e.severity<=4 ORDER BY e.day DESC,e.id DESC LIMIT ?""", (actor, actor, limit)).fetchall()
    return [f"{_ago(conn, r[0])}: {r[1]}" for r in rows]


def _actor_pool(conn: sqlite3.Connection, a: sqlite3.Row) -> tuple[list[str], list[str]]:
    """(plain findings, kept-quiet findings) for a person."""
    aid, name = int(a["id"]), str(a["name"])
    plain: list[str] = []
    quiet: list[str] = []
    for r in conn.execute("""SELECT b.name FROM household_unions u JOIN actors b ON b.id=CASE WHEN u.actor_a_id=? THEN u.actor_b_id ELSE u.actor_a_id END
                             WHERE ? IN (u.actor_a_id,u.actor_b_id) AND u.status='active'""", (aid, aid)):
        plain.append(f"{name} is married to or partnered with {r[0]}.")
    for r in conn.execute("SELECT name,status FROM civilian_enterprises WHERE owner_actor_id=? AND status NOT IN ('closed','dissolved') LIMIT 3", (aid,)):
        plain.append(f"{name} owns {r[0]}.")
    for r in conn.execute("""SELECT e.name,s.role FROM enterprise_staff s JOIN civilian_enterprises e ON e.id=s.enterprise_id
                             WHERE s.actor_id=? AND s.status='active' AND COALESCE(e.owner_actor_id,-1)<>? LIMIT 3""", (aid, aid)):
        plain.append(f"{name} works at {r[0]} as {r[1]}.")
    for r in conn.execute("""SELECT i.name,m.role_text FROM institution_memberships m JOIN actors i ON i.id=m.institution_actor_id
                             WHERE m.member_actor_id=? AND m.status='active' LIMIT 3""", (aid,)):
        plain.append(f"{name} belongs to {r[0]}" + (f" as {r[1]}." if r[1] else "."))
    plain += _events_about(conn, aid)
    for r in conn.execute("""SELECT o.name,p.role_kind FROM underworld_personnel p JOIN underworld_organizations o ON o.id=p.organization_id
                             WHERE p.actor_id=? AND p.status='active'""", (aid,)):
        quiet.append(f"{name} answers to {r[0]} as {str(r[1]).replace('_', ' ')}.")
    for r in conn.execute("""SELECT COALESCE(l.name,e.name,'someone') FROM credit_agreements c LEFT JOIN actors l ON l.id=c.lender_actor_id
                             LEFT JOIN civilian_enterprises e ON e.id=c.lender_enterprise_id
                             WHERE c.borrower_actor_id=? AND c.outstanding>0 LIMIT 2""", (aid,)):
        quiet.append(f"{name} is in debt to {r[0]}.")
    return plain, quiet


def investigate(conn: sqlite3.Connection, me: int, *, actor: int | None = None, location: int | None = None, business: int | None = None,
                outfit: int | None = None, text: str = "", days: int = 1, seed_key: str = "") -> dict:
    """Findings for an investigation lasting `days`. More days reach further into what is kept quiet."""
    days = max(1, int(days))
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    rng = random.Random(f"investigate:{seed}:{seed_key}:{me}:{actor}:{location}:{business}:{outfit}:{text}:{_day(conn)}")
    here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
    plain: list[str] = []
    quiet: list[str] = []
    subject = text
    if actor is not None:
        a = conn.execute("SELECT * FROM actors WHERE id=?", (actor,)).fetchone()
        subject = str(a["name"])
        plain, quiet = _actor_pool(conn, a)
        plain += _talk(conn, subject, a["current_location_id"] or here)
    elif business is not None:
        b = conn.execute("SELECT * FROM civilian_enterprises WHERE id=?", (business,)).fetchone()
        subject = str(b["name"])
        if b["owner_actor_id"] is not None:
            plain.append(f"{subject} is owned by {conn.execute('SELECT name FROM actors WHERE id=?', (b['owner_actor_id'],)).fetchone()[0]}.")
        for r in conn.execute("SELECT a.name,s.role FROM enterprise_staff s JOIN actors a ON a.id=s.actor_id WHERE s.enterprise_id=? AND s.status='active' LIMIT 5", (business,)):
            plain.append(f"{r[0]} works at {subject} as {r[1]}.")
        if float(b["debt"] or 0) > float(b["cash"] or 0):
            plain.append(f"{subject} owes more than it holds.")
        for r in conn.execute("""SELECT o.name FROM underworld_protection_accounts p JOIN underworld_organizations o ON o.id=p.protector_organization_id
                                 WHERE p.enterprise_id=? AND p.status='active'""", (business,)):
            quiet.append(f"{subject} pays {r[0]} for protection.")
        plain += _talk(conn, subject, b["location_id"] or here)
    elif outfit is not None:
        o = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()
        subject = str(o["name"])
        if o["current_leader_actor_id"] is not None:
            quiet.append(f"{subject} is led by {conn.execute('SELECT name FROM actors WHERE id=?', (o['current_leader_actor_id'],)).fetchone()[0]}.")
        for r in conn.execute("SELECT a.name,p.role_kind FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id WHERE p.organization_id=? AND p.status='active' ORDER BY p.authority DESC LIMIT 4", (outfit,)):
            quiet.append(f"{r[0]} is {str(r[1]).replace('_', ' ')} of {subject}.")
        plain += _talk(conn, subject, here)
    elif location is not None:
        l = conn.execute("SELECT * FROM locations WHERE id=?", (location,)).fetchone()
        subject = str(l["name"])
        for r in conn.execute("SELECT day,title FROM events WHERE location_id=? AND severity<=4 ORDER BY day DESC,id DESC LIMIT 4", (location,)):
            plain.append(f"{_ago(conn, r[0])}: {r[1]}")
        for r in conn.execute("SELECT name FROM civilian_enterprises WHERE location_id=? AND status IN ('active','strained') ORDER BY capital DESC LIMIT 4", (location,)):
            plain.append(f"{r[0]} trades here.")
        for r in conn.execute("""SELECT o.name FROM underworld_zone_claims c JOIN underworld_zones z ON z.id=c.zone_id JOIN underworld_organizations o ON o.id=c.organization_id
                                 WHERE z.city_location_id=? AND c.claim_kind='controller' AND c.status='active' ORDER BY c.strength DESC LIMIT 2""", (location,)):
            quiet.append(f"{r[0]} holds ground here.")
        plain += _talk(conn, subject, location)
    else:
        words = _terms(text)
        for w in words[:3]:
            for r in conn.execute("SELECT day,title FROM events WHERE title LIKE ? ESCAPE '!' AND severity<=4 ORDER BY day DESC LIMIT 2", (_like(w),)):
                plain.append(f"{_ago(conn, r[0])}: {r[1]}")
        for w in words[:3]:
            plain += [f"People say: {t}" for t in _topic_talk(conn, w, here)]
    # time and luck reach what is kept quiet: each quiet fact surfaces with a chance that grows with the days spent
    chance = min(0.9, 0.2 + 0.1 * days)
    got = list(dict.fromkeys(plain))[: 2 + days] + [q for q in quiet if rng.random() < chance]
    return {"subject": subject, "found": got, "more_unknown": bool(quiet) and len(got) < len(plain) + len(quiet)}


def _topic_talk(conn: sqlite3.Connection, word: str, place: int | None) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT k.belief_text FROM knowledge k JOIN actors a ON a.id=k.knower_actor_id
           WHERE k.belief_text LIKE ? ESCAPE '!' AND k.belief_text NOT LIKE 'Investigation concerning%' AND a.current_location_id=? LIMIT 2""",
        (_like(word), place)).fetchall()
    return [str(r[0]) for r in rows]
```

## engine/memory.py

```python
"""PERF-01 memory fading: people forget low-importance rumours nobody repeats; the world does not.

A person's memory of a rumour fades when the underlying event was minor (severity 1-3), did not touch them
(they were not its source or target, nor kin or household of one who was), they are not the player, and they
have not heard anything about that event for the retention time (severity 1 ~1 year, 2 ~1.5 years, 3 ~3 years,
varied +/-30% per person).  Wars, the deaths of the great and a new Sixth (severity 4-5) are never forgotten.

Fading removes only that person's knowledge, rumour exposure (so they can hear it again), evidence access,
belief and belief revisions.  Shared rumour evidence is removed once nobody holds it.  Claims, rumours,
events, public narratives and records are never removed: the world keeps its history.

The rule depends only on the day, so the 30-day cadence is chunk-invariant.
"""
from __future__ import annotations

import hashlib
import sqlite3

MEMORY_GRID_DAYS = 30
RETENTION_DAYS = {1: 365, 2: 540, 3: 1095}
MIN_RETENTION_DAYS = int(min(RETENTION_DAYS.values()) * 0.7)
# News goes stale: a rumour that has reached nowhere new for this long stops circulating (great events longer).
NEWS_STALE_DAYS = {1: 180, 2: 180, 3: 365, 4: 730, 5: 730}
DELIVERED_TRANSMISSION_KEEP_DAYS = 90


def _stable_fraction(*parts: object) -> float:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def retention_days(actor_id: int, event_key: str, severity: int) -> float:
    return RETENTION_DAYS[max(1, min(3, int(severity)))] * (0.7 + 0.6 * _stable_fraction("memory", actor_id, event_key))


def next_memory_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    day = (int(after_day) // MEMORY_GRID_DAYS + 1) * MEMORY_GRID_DAYS
    return day if day <= int(end_day) else None


def _personal_pairs(conn: sqlite3.Connection, event_ids: set[int]) -> set[tuple[int, int]]:
    """(actor, event) pairs where the event touched the actor: source/target, their kin, their household."""
    if not event_ids:
        return set()
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _memory_events(event_id INTEGER PRIMARY KEY)")
    conn.execute("DELETE FROM _memory_events")
    conn.executemany("INSERT INTO _memory_events(event_id) VALUES (?)", [(e,) for e in sorted(event_ids)])
    involved: dict[int, set[int]] = {}
    for eid, aid in conn.execute(
        """SELECT e.id,e.source_actor_id FROM events e JOIN _memory_events m ON m.event_id=e.id WHERE e.source_actor_id IS NOT NULL
           UNION SELECT t.event_id,t.actor_id FROM event_targets t JOIN _memory_events m ON m.event_id=t.event_id"""
    ):
        involved.setdefault(int(eid), set()).add(int(aid))
    people = {a for s in involved.values() for a in s}
    close: dict[int, set[int]] = {a: {a} for a in people}
    if people:
        marks = ",".join("?" * len(people))
        for a, b in conn.execute(
            f"SELECT actor_a_id,actor_b_id FROM kinship_links WHERE actor_a_id IN ({marks}) OR actor_b_id IN ({marks})",
            (*people, *people),
        ):
            if int(a) in close: close[int(a)].add(int(b))
            if int(b) in close: close[int(b)].add(int(a))
        for a1, a2 in conn.execute(
            f"""SELECT m1.actor_id,m2.actor_id FROM household_members m1 JOIN household_members m2 ON m2.household_id=m1.household_id
                WHERE m1.actor_id IN ({marks}) AND m1.status='active' AND m2.status='active'""",
            tuple(people),
        ):
            close[int(a1)].add(int(a2))
    return {(member, eid) for eid, actors in involved.items() for a in actors for member in close.get(a, {a})}


def _forget_all(conn: sqlite3.Connection, forget: list[tuple[int, int, str, int]]) -> tuple[int, int]:
    """Set-based removal of (knowledge_id, actor, fact_key, rumour_id) memories; returns (faded, evidence collected)."""
    claims_by_key: dict[str, list[int]] = {}
    for cid, key in conn.execute("SELECT id,claim_key FROM information_claims WHERE claim_key LIKE 'rumour:%'"):
        claims_by_key.setdefault(str(key).split("#", 1)[0], []).append(int(cid))
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _memory_forget(knowledge_id INTEGER, actor_id INTEGER, rumour_id INTEGER)")
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _memory_forget_claims(actor_id INTEGER, claim_id INTEGER, PRIMARY KEY(actor_id,claim_id))")
    conn.execute("DELETE FROM _memory_forget"); conn.execute("DELETE FROM _memory_forget_claims")
    conn.executemany("INSERT INTO _memory_forget VALUES (?,?,?)", [(k, a, r) for k, a, _, r in forget])
    conn.executemany("INSERT OR IGNORE INTO _memory_forget_claims VALUES (?,?)",
                     [(a, cid) for _, a, key, _ in forget for cid in claims_by_key.get(key, ())])
    conn.execute("""DELETE FROM actor_evidence_access WHERE (actor_id,evidence_id) IN
                    (SELECT f.actor_id,ce.id FROM _memory_forget_claims f JOIN claim_evidence ce ON ce.claim_id=f.claim_id)""")
    conn.execute("DELETE FROM actor_beliefs WHERE (actor_id,claim_id) IN (SELECT actor_id,claim_id FROM _memory_forget_claims)")
    conn.execute("DELETE FROM belief_revisions WHERE (actor_id,claim_id) IN (SELECT actor_id,claim_id FROM _memory_forget_claims)")
    conn.execute("DELETE FROM knowledge_provenance WHERE knowledge_id IN (SELECT knowledge_id FROM _memory_forget)")
    conn.execute("DELETE FROM knowledge WHERE id IN (SELECT knowledge_id FROM _memory_forget)")
    conn.execute("DELETE FROM rumour_exposures WHERE (rumour_id,actor_id) IN (SELECT rumour_id,actor_id FROM _memory_forget)")
    collected = conn.execute(
        """DELETE FROM claim_evidence WHERE claim_id IN (SELECT DISTINCT claim_id FROM _memory_forget_claims)
           AND evidence_kind='rumour' AND NOT EXISTS (SELECT 1 FROM actor_evidence_access a WHERE a.evidence_id=claim_evidence.id)"""
    ).rowcount
    return len(forget), int(collected)


def fade_stale_news(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    """Rumours that stopped moving stop circulating; their per-place spread rows and transmissions go.
    The rumour row and its event stay (history); memories of it follow memory fading."""
    stale = []
    for rid, sev, last in conn.execute(
        """SELECT r.id,COALESCE(e.severity,1),MAX(r.created_day,COALESCE(MAX(rl.last_updated_day),r.created_day))
           FROM rumours r LEFT JOIN events e ON e.id=r.truth_event_id
           LEFT JOIN rumour_locations rl ON rl.rumour_id=r.id
           WHERE r.status='circulating' GROUP BY r.id"""
    ):
        if int(last) + NEWS_STALE_DAYS[max(1, min(5, int(sev)))] <= day:
            stale.append((int(rid),))
    if stale:
        conn.executemany("UPDATE rumours SET status='faded' WHERE id=?", stale)
        conn.executemany("DELETE FROM rumour_locations WHERE rumour_id=?", stale)
        conn.executemany("DELETE FROM rumour_transmissions WHERE rumour_id=?", stale)
    pruned = conn.execute("DELETE FROM rumour_transmissions WHERE status='delivered' AND due_day<?",
                          (day - DELIVERED_TRANSMISSION_KEEP_DAYS,)).rowcount
    return {"news_faded": len(stale), "transmissions_pruned": int(pruned)}


AUDIT_KEEP_DAYS = 365


def prune_audit_logs(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    """Diagnostic trails keep about a year; history (events, decisions, breakthroughs, relationships) is kept.
    Every reader of these trails looks at the same day or an entity's latest row, which is always kept."""
    cutoff = int(day) - AUDIT_KEEP_DAYS
    n = 0
    n += conn.execute("DELETE FROM decision_evaluations WHERE day<?", (cutoff,)).rowcount  # candidate audits cascade
    n += conn.execute("DELETE FROM mortality_audit WHERE day<?", (cutoff,)).rowcount
    n += conn.execute("DELETE FROM regional_growth_snapshots WHERE day<?", (cutoff,)).rowcount
    n += conn.execute("DELETE FROM cultivation_history WHERE history_kind='practice_review' AND day<?", (cutoff,)).rowcount
    n += conn.execute(
        """DELETE FROM resolution_reviews WHERE day<? AND id NOT IN
           (SELECT MAX(id) FROM resolution_reviews GROUP BY entity_kind,entity_id)""", (cutoff,)).rowcount
    return {"audit_rows_pruned": int(n)}


def process_due_memory(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    day = int(day)
    news = fade_stale_news(conn, day)
    result = forget_minor_rumours(conn, day)
    audit = prune_audit_logs(conn, day)
    return {**news, **result, **audit}


def forget_minor_rumours(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    day = int(day)
    player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    player_id = int(player[0]) if player and player[0] is not None else -1
    rows = conn.execute(
        """SELECT k.id,k.knower_actor_id,k.fact_key,k.learned_day,r.id,r.truth_event_id,COALESCE(e.severity,1)
           FROM knowledge k
           JOIN rumours r ON r.id=CAST(substr(k.fact_key,8) AS INTEGER)
           LEFT JOIN events e ON e.id=r.truth_event_id
           WHERE k.fact_key LIKE 'rumour:%' AND k.knower_actor_id<>? AND COALESCE(e.severity,1)<=3
             AND k.learned_day<=?
           ORDER BY k.id""",
        (player_id, day - MIN_RETENTION_DAYS),
    ).fetchall()
    if not rows:
        return {"memories_faded": 0, "evidence_collected": 0}
    event_ids = {int(r[5]) for r in rows if r[5] is not None}
    personal = _personal_pairs(conn, event_ids)
    # Hearing anything about the same event refreshes the memory of it.
    last_touch: dict[tuple[int, str], int] = {}
    for kid, actor, fact_key, learned, rid, eid, sev in rows:
        key = (int(actor), f"e{eid}" if eid is not None else f"r{rid}")
        last_touch[key] = max(last_touch.get(key, 0), int(learned))
    if event_ids:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _memory_events(event_id INTEGER PRIMARY KEY)")
        conn.execute("DELETE FROM _memory_events")
        conn.executemany("INSERT INTO _memory_events(event_id) VALUES (?)", [(e,) for e in sorted(event_ids)])
        for actor, eid, latest in conn.execute(
            """SELECT k.knower_actor_id,r.truth_event_id,MAX(k.learned_day) FROM knowledge k
               JOIN rumours r ON r.id=CAST(substr(k.fact_key,8) AS INTEGER)
               JOIN _memory_events m ON m.event_id=r.truth_event_id
               WHERE k.fact_key LIKE 'rumour:%' GROUP BY 1,2"""
        ):
            key = (int(actor), f"e{eid}")
            last_touch[key] = max(last_touch.get(key, 0), int(latest))
    forget: list[tuple[int, int, str, int]] = []
    for kid, actor, fact_key, learned, rid, eid, sev in rows:
        actor = int(actor)
        if eid is not None and (actor, int(eid)) in personal:
            continue
        event_key = f"e{eid}" if eid is not None else f"r{rid}"
        if last_touch[(actor, event_key)] + retention_days(actor, event_key, int(sev)) > day:
            continue
        forget.append((int(kid), actor, str(fact_key), int(rid)))
    if not forget:
        return {"memories_faded": 0, "evidence_collected": 0}
    faded, collected = _forget_all(conn, forget)
    return {"memories_faded": faded, "evidence_collected": int(collected)}
```

## engine/continuity.py

```python
from __future__ import annotations

import json
import sqlite3
from typing import Any


RESOLUTION_LEVELS = ("LATENT", "STRUCTURAL", "TRACKED", "ACTIVE", "SCENE")
_RESOLUTION_RANK = {name: i for i, name in enumerate(RESOLUTION_LEVELS)}


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _entity_exists(conn: sqlite3.Connection, entity_kind: str, entity_id: int) -> bool:
    tables = {
        "actor": "actors",
        "institution": "actors",
        "location": "locations",
        "possession": "possessions",
        "thread": "threads",
        "cohort": "cohorts",
    }
    table = tables.get(entity_kind)
    if not table:
        return False
    row = conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (entity_id,)).fetchone()
    if not row:
        return False
    if entity_kind == "institution":
        actor = conn.execute("SELECT actor_type FROM actors WHERE id=?", (entity_id,)).fetchone()
        return bool(actor and actor[0] == "institution")
    return True


def upsert_continuity_core(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: int,
    core: dict[str, Any],
    *,
    core_type: str = "general",
    historical_depth: str = "present",
    day: int | None = None,
    crystallized_day: int | None = None,
    source_kind: str = "engine",
    notes: str | None = None,
) -> int:
    if not _entity_exists(conn, entity_kind, entity_id):
        raise ValueError(f"Unknown {entity_kind} #{entity_id}")
    if historical_depth not in {"present", "shallow", "developed", "deep"}:
        raise ValueError("Invalid historical_depth")
    if day is None:
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    conn.execute(
        """
        INSERT INTO continuity_cores(
            entity_kind,entity_id,core_type,core_json,historical_depth,last_crystallized_day,last_updated_day,source_kind,notes
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(entity_kind,entity_id,core_type) DO UPDATE SET
            core_json=excluded.core_json,
            historical_depth=excluded.historical_depth,
            last_crystallized_day=COALESCE(excluded.last_crystallized_day,continuity_cores.last_crystallized_day),
            last_updated_day=excluded.last_updated_day,
            source_kind=excluded.source_kind,
            notes=COALESCE(excluded.notes,continuity_cores.notes)
        """,
        (entity_kind, entity_id, core_type, _dumps(core), historical_depth, crystallized_day, day, source_kind, notes),
    )
    row = conn.execute(
        "SELECT id FROM continuity_cores WHERE entity_kind=? AND entity_id=? AND core_type=?",
        (entity_kind, entity_id, core_type),
    ).fetchone()
    return int(row[0])


def continuity_core(conn: sqlite3.Connection, entity_kind: str, entity_id: int, *, core_type: str = "general") -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM continuity_cores WHERE entity_kind=? AND entity_id=? AND core_type=?",
        (entity_kind, entity_id, core_type),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["core"] = _loads(result.pop("core_json"), {})
    return result


def add_historical_anchor(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: int,
    anchor_type: str,
    summary: str,
    *,
    start_day: int | None = None,
    end_day: int | None = None,
    detail: dict[str, Any] | None = None,
    source_kind: str = "crystallization",
    source_id: int | None = None,
    certainty: float = 1.0,
    canon_scope: str = "campaign",
    immutable: bool = True,
    created_day: int | None = None,
) -> int:
    if not _entity_exists(conn, entity_kind, entity_id):
        raise ValueError(f"Unknown {entity_kind} #{entity_id}")
    if not 0 <= certainty <= 1:
        raise ValueError("certainty must be between 0 and 1")
    if created_day is None:
        created_day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    cur = conn.execute(
        """
        INSERT INTO historical_anchors(
            entity_kind,entity_id,anchor_type,start_day,end_day,summary,detail_json,source_kind,source_id,
            certainty,canon_scope,immutable,created_day
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            entity_kind, entity_id, anchor_type, start_day, end_day, summary, _dumps(detail), source_kind,
            source_id, certainty, canon_scope, 1 if immutable else 0, created_day,
        ),
    )
    return int(cur.lastrowid)


def historical_anchors(conn: sqlite3.Connection, entity_kind: str, entity_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT * FROM historical_anchors
           WHERE entity_kind=? AND entity_id=?
           ORDER BY COALESCE(start_day,created_day),id""",
        (entity_kind, entity_id),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["detail"] = _loads(item.pop("detail_json"), {})
        result.append(item)
    return result


def create_cohort(
    conn: sqlite3.Connection,
    name: str,
    cohort_type: str,
    *,
    institution_actor_id: int | None = None,
    location_id: int | None = None,
    start_day: int | None = None,
    end_day: int | None = None,
    population_estimate: int | None = None,
    shared_context: dict[str, Any] | None = None,
    historical_summary: str | None = None,
    status: str = "historical",
    is_canon: bool = False,
) -> int:
    if institution_actor_id is not None and not _entity_exists(conn, "institution", institution_actor_id):
        raise ValueError("institution_actor_id must reference an institution actor")
    if location_id is not None and not _entity_exists(conn, "location", location_id):
        raise ValueError("Unknown location")
    cur = conn.execute(
        """
        INSERT INTO cohorts(
            name,cohort_type,institution_actor_id,location_id,start_day,end_day,population_estimate,
            shared_context_json,historical_summary,status,is_canon
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (name, cohort_type, institution_actor_id, location_id, start_day, end_day, population_estimate,
         _dumps(shared_context), historical_summary, status, 1 if is_canon else 0),
    )
    return int(cur.lastrowid)


def add_cohort_member(
    conn: sqlite3.Connection,
    cohort_id: int,
    actor_id: int,
    *,
    role: str | None = None,
    joined_day: int | None = None,
    left_day: int | None = None,
    membership_status: str = "member",
    significance: float = 0.5,
    notes: str | None = None,
) -> None:
    if not _entity_exists(conn, "cohort", cohort_id):
        raise ValueError("Unknown cohort")
    if not _entity_exists(conn, "actor", actor_id):
        raise ValueError("Unknown actor")
    conn.execute(
        """
        INSERT INTO cohort_memberships(cohort_id,actor_id,role,joined_day,left_day,membership_status,significance,notes)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(cohort_id,actor_id) DO UPDATE SET
            role=excluded.role,joined_day=excluded.joined_day,left_day=excluded.left_day,
            membership_status=excluded.membership_status,significance=excluded.significance,notes=excluded.notes
        """,
        (cohort_id, actor_id, role, joined_day, left_day, membership_status, significance, notes),
    )


def create_career_track(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    domain: str,
    *,
    description: str | None = None,
    typical_entry_age: int | None = None,
    institution_kind: str | None = None,
    stage_model: dict[str, Any] | None = None,
    is_canon: bool = False,
) -> int:
    conn.execute(
        """
        INSERT INTO career_tracks(key,name,domain,description,typical_entry_age,institution_kind,stage_model_json,is_canon)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(key) DO UPDATE SET
            name=excluded.name,domain=excluded.domain,description=excluded.description,
            typical_entry_age=excluded.typical_entry_age,institution_kind=excluded.institution_kind,
            stage_model_json=excluded.stage_model_json,is_canon=excluded.is_canon
        """,
        (key, name, domain, description, typical_entry_age, institution_kind, _dumps(stage_model), 1 if is_canon else 0),
    )
    return int(conn.execute("SELECT id FROM career_tracks WHERE key=?", (key,)).fetchone()[0])


def add_career_stage(
    conn: sqlite3.Connection,
    track_id: int,
    stage_key: str,
    stage_name: str,
    sequence_index: int,
    *,
    description: str | None = None,
    entry_requirements: dict[str, Any] | None = None,
    responsibilities: dict[str, Any] | None = None,
    exit_paths: list[Any] | None = None,
) -> int:
    conn.execute(
        """
        INSERT INTO career_stages(
            track_id,stage_key,stage_name,sequence_index,description,entry_requirements_json,responsibilities_json,exit_paths_json
        ) VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(track_id,stage_key) DO UPDATE SET
            stage_name=excluded.stage_name,sequence_index=excluded.sequence_index,description=excluded.description,
            entry_requirements_json=excluded.entry_requirements_json,responsibilities_json=excluded.responsibilities_json,
            exit_paths_json=excluded.exit_paths_json
        """,
        (track_id, stage_key, stage_name, sequence_index, description, _dumps(entry_requirements),
         _dumps(responsibilities), json.dumps(exit_paths or [], ensure_ascii=False)),
    )
    return int(conn.execute(
        "SELECT id FROM career_stages WHERE track_id=? AND stage_key=?", (track_id, stage_key)
    ).fetchone()[0])


def start_career(
    conn: sqlite3.Connection,
    actor_id: int,
    track_id: int,
    *,
    stage_id: int | None = None,
    institution_actor_id: int | None = None,
    mentor_actor_id: int | None = None,
    started_day: int | None = None,
    notes: str | None = None,
) -> int:
    if not _entity_exists(conn, "actor", actor_id):
        raise ValueError("Unknown actor")
    if started_day is None:
        started_day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    cur = conn.execute(
        """
        INSERT INTO actor_careers(
            actor_id,track_id,current_stage_id,institution_actor_id,mentor_actor_id,started_day,stage_started_day,notes
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (actor_id, track_id, stage_id, institution_actor_id, mentor_actor_id, started_day, started_day, notes),
    )
    return int(cur.lastrowid)


def advance_career_stage(conn: sqlite3.Connection, career_id: int, stage_id: int, *, day: int | None = None) -> None:
    if day is None:
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    career = conn.execute("SELECT * FROM actor_careers WHERE id=?", (career_id,)).fetchone()
    if not career:
        raise ValueError("Unknown career")
    stage = conn.execute("SELECT * FROM career_stages WHERE id=? AND track_id=?", (stage_id, career["track_id"])).fetchone()
    if not stage:
        raise ValueError("Stage does not belong to career track")
    conn.execute(
        "UPDATE actor_careers SET current_stage_id=?,stage_started_day=? WHERE id=?",
        (stage_id, day, career_id),
    )


def set_institution_profile(
    conn: sqlite3.Connection,
    actor_id: int,
    institution_kind: str,
    *,
    founded_day: int | None = None,
    parent_institution_actor_id: int | None = None,
    primary_location_id: int | None = None,
    governance: dict[str, Any] | None = None,
    culture: dict[str, Any] | None = None,
    pipeline: dict[str, Any] | None = None,
    capacity: dict[str, Any] | None = None,
    economic: dict[str, Any] | None = None,
    reputation: dict[str, Any] | None = None,
    succession: dict[str, Any] | None = None,
    trajectory: str = "stable",
    last_review_day: int | None = None,
    notes: str | None = None,
) -> None:
    if not _entity_exists(conn, "institution", actor_id):
        raise ValueError("institution profile requires actor_type='institution'")
    if last_review_day is None:
        last_review_day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    conn.execute(
        """
        INSERT INTO institution_profiles(
            actor_id,institution_kind,founded_day,parent_institution_actor_id,primary_location_id,
            governance_json,culture_json,pipeline_json,capacity_json,economic_json,reputation_json,
            succession_json,trajectory,last_review_day,notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(actor_id) DO UPDATE SET
            institution_kind=excluded.institution_kind,founded_day=excluded.founded_day,
            parent_institution_actor_id=excluded.parent_institution_actor_id,primary_location_id=excluded.primary_location_id,
            governance_json=excluded.governance_json,culture_json=excluded.culture_json,pipeline_json=excluded.pipeline_json,
            capacity_json=excluded.capacity_json,economic_json=excluded.economic_json,reputation_json=excluded.reputation_json,
            succession_json=excluded.succession_json,trajectory=excluded.trajectory,last_review_day=excluded.last_review_day,
            notes=excluded.notes
        """,
        (actor_id, institution_kind, founded_day, parent_institution_actor_id, primary_location_id,
         _dumps(governance), _dumps(culture), _dumps(pipeline), _dumps(capacity), _dumps(economic),
         _dumps(reputation), _dumps(succession), trajectory, last_review_day, notes),
    )


def set_resolution(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: int,
    level: str,
    *,
    day: int | None = None,
    reason: str | None = None,
    source_kind: str = "engine",
    source_id: int | None = None,
    review_cadence_days: int | None = None,
    next_review_day: int | None = None,
    locked_min_level: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if level not in _RESOLUTION_RANK:
        raise ValueError("Invalid resolution level")
    if locked_min_level is not None and locked_min_level not in _RESOLUTION_RANK:
        raise ValueError("Invalid locked_min_level")
    if not _entity_exists(conn, entity_kind, entity_id):
        raise ValueError(f"Unknown {entity_kind} #{entity_id}")
    if day is None:
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    old = conn.execute(
        "SELECT * FROM entity_resolution WHERE entity_kind=? AND entity_id=?", (entity_kind, entity_id)
    ).fetchone()
    old_level = str(old["resolution_level"]) if old else None
    effective_lock = locked_min_level if locked_min_level is not None else (old["locked_min_level"] if old else None)
    if effective_lock and _RESOLUTION_RANK[level] < _RESOLUTION_RANK[str(effective_lock)]:
        raise ValueError(f"Cannot demote below locked minimum {effective_lock}")
    conn.execute(
        """
        INSERT INTO entity_resolution(
            entity_kind,entity_id,resolution_level,previous_level,reason,promoted_by_kind,promoted_by_id,
            review_cadence_days,next_review_day,last_changed_day,locked_min_level,metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(entity_kind,entity_id) DO UPDATE SET
            previous_level=entity_resolution.resolution_level,
            resolution_level=excluded.resolution_level,
            reason=excluded.reason,
            promoted_by_kind=excluded.promoted_by_kind,
            promoted_by_id=excluded.promoted_by_id,
            review_cadence_days=COALESCE(excluded.review_cadence_days,entity_resolution.review_cadence_days),
            next_review_day=COALESCE(excluded.next_review_day,entity_resolution.next_review_day),
            last_changed_day=excluded.last_changed_day,
            locked_min_level=COALESCE(excluded.locked_min_level,entity_resolution.locked_min_level),
            metadata_json=excluded.metadata_json
        """,
        (entity_kind, entity_id, level, old_level, reason, source_kind, source_id, review_cadence_days,
         next_review_day, day, locked_min_level, _dumps(metadata)),
    )
    if old_level != level:
        conn.execute(
            """INSERT INTO resolution_transitions(
                   day,entity_kind,entity_id,from_level,to_level,reason,source_kind,source_id
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (day, entity_kind, entity_id, old_level, level, reason, source_kind, source_id),
        )


def resolution_state(conn: sqlite3.Connection, entity_kind: str, entity_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM entity_resolution WHERE entity_kind=? AND entity_id=?", (entity_kind, entity_id)
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["metadata"] = _loads(result.pop("metadata_json"), {})
    return result


def create_latent_entity(
    conn: sqlite3.Connection,
    latent_kind: str,
    archetype: str,
    *,
    location_id: int | None = None,
    institution_actor_id: int | None = None,
    cohort_id: int | None = None,
    count_estimate: int = 1,
    constraints: dict[str, Any] | None = None,
    historical_context: dict[str, Any] | None = None,
    day: int | None = None,
    notes: str | None = None,
) -> int:
    if day is None:
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    cur = conn.execute(
        """INSERT INTO latent_entities(
               latent_kind,archetype,location_id,institution_actor_id,cohort_id,count_estimate,
               constraints_json,historical_context_json,created_day,updated_day,notes
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (latent_kind, archetype, location_id, institution_actor_id, cohort_id, count_estimate,
         _dumps(constraints), _dumps(historical_context), day, day, notes),
    )
    return int(cur.lastrowid)


def add_public_narrative(
    conn: sqlite3.Connection,
    narrative_key: str,
    subject_kind: str,
    subject_id: int,
    claim_text: str,
    *,
    day: int,
    scope_kind: str = "world",
    scope_id: int | None = None,
    confidence: float = 0.5,
    prevalence: float = 0.5,
    valence: float = 0.0,
    origin_kind: str | None = None,
    origin_id: int | None = None,
) -> int:
    conn.execute(
        """INSERT INTO public_narratives(
               narrative_key,scope_kind,scope_id,subject_kind,subject_id,claim_text,confidence,prevalence,valence,
               first_day,last_reinforced_day,origin_kind,origin_id
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (narrative_key, scope_kind, scope_id, subject_kind, subject_id, claim_text, confidence, prevalence,
         valence, day, day, origin_kind, origin_id),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
```

## engine/resolution_controller.py

```python
from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any

from .continuity import RESOLUTION_LEVELS, resolution_state, set_institution_profile, set_resolution, upsert_continuity_core

RANK = {name: i for i, name in enumerate(RESOLUTION_LEVELS)}


def _j(v: Any) -> str:
    return json.dumps(v if v is not None else {}, ensure_ascii=False, sort_keys=True)


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _entity_row(conn: sqlite3.Connection, entity_kind: str, entity_id: int) -> sqlite3.Row:
    if entity_kind not in {"actor", "institution"}:
        raise ValueError("Resolution controller currently supports actor and institution")
    row = conn.execute("SELECT * FROM actors WHERE id=?", (entity_id,)).fetchone()
    if not row or (entity_kind == "institution" and row["actor_type"] != "institution") or (entity_kind == "actor" and row["actor_type"] != "character"):
        raise ValueError(f"Unknown {entity_kind} #{entity_id}")
    return row


def significance_score(conn: sqlite3.Connection, entity_kind: str, entity_id: int, *, signals: dict[str, float] | None = None) -> tuple[float, dict[str, float]]:
    """Objective consequence score. Camera/player attention is intentionally not a signal."""
    row = _entity_row(conn, entity_kind, entity_id)
    parts: dict[str, float] = {}
    if entity_kind == "actor":
        lp=conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?",(entity_id,)).fetchone()
        if str(row["status"]) in {"deceased","historical"} or (lp and str(lp[0])=="deceased"):
            return 0.0, {"life_state": -100.0}
    sim = conn.execute("SELECT tier FROM simulation_profiles WHERE actor_id=?", (entity_id,)).fetchone()
    if sim:
        parts["simulation_tier"] = {"ACTIVE": 35.0, "STRATEGIC": 30.0, "DORMANT": 6.0}.get(str(sim[0]), 0.0)

    if entity_kind == "actor":
        enterprises = conn.execute(
            "SELECT capital,cash,reputation,status FROM civilian_enterprises WHERE owner_actor_id=? AND status IN ('active','strained','insolvent')",
            (entity_id,),
        ).fetchall()
        if enterprises:
            scale = sum(max(0.0, float(r["capital"])) + max(0.0, float(r["cash"])) for r in enterprises)
            rep = max(float(r["reputation"]) for r in enterprises)
            parts["enterprise_reach"] = min(35.0, 8.0 + 5.0 * math.log10(1.0 + scale) + max(0.0, rep - 50.0) * 0.15)
        staff = conn.execute(
            """SELECT s.authority,e.capital,e.cash,e.reputation FROM enterprise_staff s
               JOIN civilian_enterprises e ON e.id=s.enterprise_id
               WHERE s.actor_id=? AND s.status='active' AND s.authority>=40 AND e.status IN ('active','strained','insolvent')""",
            (entity_id,),
        ).fetchall() if _table(conn,'enterprise_staff') else []
        if staff:
            max_auth=max(float(r['authority']) for r in staff)
            scale=sum(max(0.0,float(r['capital']))+max(0.0,float(r['cash'])) for r in staff)
            parts['enterprise_authority']=min(26.0,10.0+max_auth*.12+3.0*math.log10(1.0+scale))
        memberships = conn.execute(
            "SELECT role_text FROM institution_memberships WHERE member_actor_id=? AND status='active'", (entity_id,)
        ).fetchall()
        if _table(conn,"cultivation_profiles"):
            cp=conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=? AND core_state='Open-Core'",(entity_id,)).fetchone()
            if cp and cp[0] is not None:
                parts["martial_standing"]={"First":2.0,"Temper":4.0,"Third":7.0,"Breach":11.0,"Fifth":20.0,"Sixth":35.0}.get(str(cp[0]),0.0)
        leadership_words = ("head", "king", "queen", "emperor", "empress", "prince", "minister", "prefect", "bishop", "master", "heir", "patriarch", "matriarch", "chief", "captain")
        if any(any(w in str(r[0] or "").lower() for w in leadership_words) for r in memberships):
            parts["office_or_leadership"] = 20.0
        active_threads = conn.execute(
            "SELECT COUNT(*) FROM thread_participants tp JOIN threads t ON t.id=tp.thread_id WHERE tp.actor_id=? AND t.status='active'",
            (entity_id,),
        ).fetchone() if _table(conn, "thread_participants") else None
        if active_threads and int(active_threads[0]):
            parts["active_threads"] = min(15.0, 4.0 * int(active_threads[0]))
    else:
        members = int(conn.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=? AND status='active'", (entity_id,)).fetchone()[0])
        if members:
            parts["persistent_membership"] = min(22.0, 4.0 + 4.0 * math.log2(1 + members))
        ip = conn.execute("SELECT trajectory,economic_json,succession_json FROM institution_profiles WHERE actor_id=?", (entity_id,)).fetchone()
        if ip:
            parts["trajectory"] = {"rising":15.0,"crisis":18.0,"transforming":12.0,"stable":4.0,"declining":2.0,"dormant":0.0}.get(str(ip["trajectory"]), 0.0)
        ents = int(conn.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE institution_actor_id=? AND status IN ('active','strained','insolvent')", (entity_id,)).fetchone()[0])
        if ents: parts["enterprise_footprint"] = min(20.0, 6.0 + 4.0 * ents)
        proc = int(conn.execute("SELECT COUNT(*) FROM canon_process_anchors WHERE entity_actor_id=? AND status NOT IN ('closed','resolved')", (entity_id,)).fetchone()[0]) if _table(conn,"canon_process_anchors") else 0
        if proc: parts["open_institutional_process"] = min(18.0, 8.0 * proc)

    # External domain systems may contribute objective signals such as regional market share,
    # case exposure, follower count, military command, or cross-border contract load.
    for key, value in (signals or {}).items():
        if key.lower() in {"camera", "player_attention", "narrative_interest"}:
            continue
        parts[f"signal:{key}"] = max(-40.0, min(40.0, float(value)))
    return max(0.0, min(100.0, sum(parts.values()))), parts


def _table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def proposed_level(score: float) -> str:
    # Automatic world simulation never promotes an entity to SCENE; scene is a camera state.
    if score >= 75.0: return "ACTIVE"
    if score >= 32.0: return "TRACKED"
    return "STRUCTURAL"


def _sync_sim_tier(conn: sqlite3.Connection, entity_id: int, level: str, day: int) -> None:
    tier, cadence = ({"ACTIVE":("ACTIVE",30), "TRACKED":("STRATEGIC",90)}.get(level, ("DORMANT",180)))
    conn.execute(
        """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold)
           VALUES (?,?,?,?,?,?,?,3)
           ON CONFLICT(actor_id) DO UPDATE SET tier=excluded.tier,cadence_days=excluded.cadence_days,last_review_day=excluded.last_review_day,next_review_day=excluded.next_review_day""",
        (entity_id,tier,cadence,0.25,0.5,day,day+cadence),
    )


def review_entity(conn: sqlite3.Connection, entity_kind: str, entity_id: int, *, signals: dict[str,float] | None = None, day: int | None = None, demotion_reviews: int = 2) -> dict[str, Any]:
    _entity_row(conn, entity_kind, entity_id)
    day = _day(conn) if day is None else int(day)
    state = resolution_state(conn, entity_kind, entity_id)
    current = str(state["resolution_level"]) if state else "STRUCTURAL"
    score, parts = significance_score(conn, entity_kind, entity_id, signals=signals)
    target = proposed_level(score)
    lock=str(state.get("locked_min_level")) if state and state.get("locked_min_level") else None
    life=conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?",(entity_id,)).fetchone() if entity_kind=="actor" else None
    deceased = entity_kind=="actor" and (str(_entity_row(conn,entity_kind,entity_id)["status"]) in {"deceased","historical"} or (life and str(life[0])=="deceased"))
    if deceased:
        target="STRUCTURAL"
    elif lock in RANK and RANK[target] < RANK[lock]:
        target=lock
    # Respect a manually/camera elevated SCENE state; autonomous reviews do not overwrite it.
    if current == "SCENE":
        action, applied, reason = "defer", current, "SCENE is camera-controlled; autonomous controller did not alter it"
    elif RANK[target] > RANK[current]:
        action, applied, reason = "promote", target, "objective consequence threshold crossed"
        set_resolution(conn, entity_kind, entity_id, target, day=day, reason=reason, source_kind="engine", review_cadence_days=30 if target=="ACTIVE" else 90, next_review_day=day+(30 if target=="ACTIVE" else 90), metadata={"significance_score":score,"score_parts":parts})
        _sync_sim_tier(conn, entity_id, target, day)
    elif RANK[target] < RANK[current]:
        prior = conn.execute(
            """SELECT proposed_level FROM resolution_reviews WHERE entity_kind=? AND entity_id=? AND day<? ORDER BY day DESC,id DESC LIMIT ?""",
            (entity_kind,entity_id,day,max(1,demotion_reviews-1)),
        ).fetchall()
        sustained = len(prior) >= max(1,demotion_reviews-1) and all(str(r[0]) == target for r in prior)
        if sustained:
            action, applied, reason = "demote", target, "lower consequence state sustained across reviews; persistence retained"
            set_resolution(conn, entity_kind, entity_id, target, day=day, reason=reason, source_kind="engine", review_cadence_days=180 if target=="STRUCTURAL" else 90, next_review_day=day+(180 if target=="STRUCTURAL" else 90), metadata={"significance_score":score,"score_parts":parts,"history_retained":True})
            _sync_sim_tier(conn, entity_id, target, day)
        else:
            action, applied, reason = "defer", current, "demotion hysteresis: lower significance must persist across reviews"
    else:
        action, applied, reason = "none", current, "resolution level remains appropriate"

    conn.execute(
        """INSERT INTO resolution_reviews(day,entity_kind,entity_id,prior_level,proposed_level,applied_level,significance_score,trigger_json,reason,action)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (day,entity_kind,entity_id,current,target,applied,score,_j(parts),reason,action),
    )
    return {"entity_kind":entity_kind,"entity_id":entity_id,"prior_level":current,"proposed_level":target,"applied_level":applied,"significance_score":score,"score_parts":parts,"action":action,"reason":reason}



def _latent_significance(conn: sqlite3.Connection, latent: sqlite3.Row, day: int) -> tuple[float,dict[str,float]]:
    parts:dict[str,float]={}
    count=max(1,int(latent['count_estimate']))
    if count==1: parts['individualized_identity']=18.0
    elif count<=5: parts['small_specific_group']=8.0
    archetype=str(latent['archetype'] or '').lower()
    if 'champion' in archetype: parts['recognized_champion_role']=16.0
    if latent['institution_actor_id'] is not None: parts['institutional_context']=8.0
    age=max(0,int(day)-int(latent['created_day']))
    parts['persistence']=min(12.0,age/365.0*3.0)
    try: hist=json.loads(latent['historical_context_json'] or '{}')
    except Exception: hist={}
    streak=float(hist.get('champion_streak') or 0)
    if streak: parts['durable_record']=min(28.0,streak*5.0)
    consequences=float(hist.get('consequence_score') or hist.get('regional_significance') or 0)
    if consequences: parts['recorded_consequence']=min(30.0,max(0.0,consequences))
    return max(0.0,min(100.0,sum(parts.values()))),parts


def _latent_level(score: float) -> str:
    if score>=40.0:return 'TRACKED'
    if score>=18.0:return 'STRUCTURAL'
    return 'LATENT'



_FIRST_NAMES=("Adrian","Bram","Celia","Darin","Elena","Ferran","Galen","Hessa","Ilan","Jora","Kellen","Lysa","Marek","Nessa","Orin","Pella","Rian","Sera","Tomas","Vera")
_SURNAMES=("Alder","Bennet","Cairn","Dale","Evers","Fenn","Grey","Hale","Ives","Kerr","Lorne","Merrin","North","Pike","Quill","Rook","Senn","Tarn","Vale","Wren")

def _generated_person_name(conn: sqlite3.Connection, latent_id: int, day: int) -> str:
    seedrow=conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone(); seed=int(seedrow[0] if seedrow else 1)
    rng=random.Random(seed*1000003+latent_id*9176+day*37)
    for i in range(200):
        name=f"{rng.choice(_FIRST_NAMES)} {rng.choice(_SURNAMES)}" if i<80 else f"{rng.choice(_FIRST_NAMES)} {rng.choice(_SURNAMES)} {i}"
        if not conn.execute("SELECT 1 FROM actors WHERE name=?",(name,)).fetchone(): return name
    raise RuntimeError('could not produce unique crystallized latent-person name')

def _materialize_latent_person(conn: sqlite3.Connection, latent: sqlite3.Row, day: int, score: float, parts: dict[str,float]) -> int | None:
    if str(latent['latent_kind'])!='person' or int(latent['count_estimate'])!=1: return None
    if latent['crystallized_entity_kind']=='actor' and latent['crystallized_entity_id'] is not None:
        return int(latent['crystallized_entity_id'])
    try: constraints=json.loads(latent['constraints_json'] or '{}')
    except Exception: constraints={}
    try: hist=json.loads(latent['historical_context_json'] or '{}')
    except Exception: hist={}
    name=str(constraints.get('name') or hist.get('proposed_name') or '').strip() or _generated_person_name(conn,int(latent['id']),day)
    birth_raw=constraints.get('birth_day') if constraints.get('birth_day') is not None else hist.get('birth_day')
    age_raw=constraints.get('age') if constraints.get('age') is not None else hist.get('age')
    if birth_raw is not None:
        # Exact chronology already exists upstream (for example POPBACK-01); preserve it.
        birth=int(birth_raw)
        age=max(0,min(110,int(max(0,day-birth)/365.2425)))
    else:
        if age_raw is None:
            ar=constraints.get('age_range')
            if isinstance(ar,(list,tuple)) and len(ar)>=2: age_raw=(float(ar[0])+float(ar[1]))/2.0
        age=max(0,min(110,int(age_raw if age_raw is not None else 28+(int(latent['id'])%23))))
        birth=day-int(age*365.2425)
    subtype=str(latent['archetype'] or 'ordinary person').replace('_',' ')
    lid=int(latent['location_id']) if latent['location_id'] is not None else None
    cur=conn.execute("INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) VALUES (?,'character',?,?,?,'active',?,0)",
                     (name,subtype,lid,lid,f"Crystallized from latent person #{int(latent['id'])}; no retroactive biography invented."))
    aid=int(cur.lastrowid); stage='elder' if age>=60 else ('child' if age<13 else ('youth' if age<20 else 'adult'))
    family_eligible=1 if age>=16 else 0
    upstream_sex=constraints.get('demographic_sex') or hist.get('demographic_sex')
    conn.execute("""INSERT INTO actor_life_profiles(actor_id,birth_day,demographic_sex,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json)
                    VALUES (?,?,?,?,?, 'living',?,?)""",(aid,birth,upstream_sex if upstream_sex in ('female','male') else None,stage,family_eligible,day,_j({'latent_entity_id':int(latent['id']),'source_age':age,'source_birth_day':birth,'generated_from_existing_population':True})))
    # FAMILY-02: no unresolved sex for a new named person (given name, else seeded roll).
    from .demographic_sex import resolve_missing_demographic_sex
    resolve_missing_demographic_sex(conn,actor_id=aid)
    from .world_package import system_enabled
    if system_enabled(conn,'cultivation'):
        # Ordinary crystallization starts Closed-Core unless the latent evidence explicitly says otherwise.
        open_core=bool(constraints.get('open_core') or hist.get('open_core'))
        stage_name=(constraints.get('stage') or hist.get('stage')) if open_core else None
        conn.execute("""INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,
                        training_effort,resource_access,teacher_support,injury_constraint,realization_aptitude,vessel_aptitude,
                        next_realization_check_day,last_review_day,next_review_day,status,metadata_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (aid,'Open-Core' if open_core else 'Closed-Core',stage_name,1 if open_core and stage_name else 0,
                      30 if open_core else 0,20 if open_core else 0,45 if open_core else 0,45,0,0,1.0,1.0,day+365,day,day+30,
                      'active' if open_core and stage_name else 'paused',_j({'latent_entity_id':int(latent['id']),'not_canon':True})))
        # A Stage held before crystallization sits somewhere inside that Stage, like any canon person's.
        from .cultivation import calibrate_revealed_profile
        calibrate_revealed_profile(conn,aid)
    conn.execute("INSERT INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) VALUES (?,?,?,?,?,?,?)",
                 (aid,.35+(aid%17)/100,.45+(aid%13)/100,.55+(aid%11)/100,.55,.62,.68))
    from .health import ensure_health_profile
    ensure_health_profile(conn,aid,metadata={'latent_entity_id':int(latent['id']),'generated_from_existing_population':True})
    from .presence import ensure_presence_profile
    ensure_presence_profile(conn,aid,base_location_id=lid,confidence=.65,source_kind='latent_crystallization',effective_from_day=day,notes='Crystallized from latent population')
    if 'merchant' in subtype.lower() or 'trade' in subtype.lower():
        from .education import _set_competence_floor
        _set_competence_floor(conn,aid,'commerce',55,source_kind='crystallization')
    if latent['institution_actor_id'] is not None:
        conn.execute("INSERT OR IGNORE INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,status,joined_day,provenance_json,metadata_json) VALUES (?,?,'ordinary_member','active',?,?,?)",
                     (int(latent['institution_actor_id']),aid,day,_j(['latent crystallization']),_j({'latent_entity_id':int(latent['id'])})))
    enterprise_id=hist.get('enterprise_id') or constraints.get('enterprise_id')
    if enterprise_id and conn.execute("SELECT 1 FROM civilian_enterprises WHERE id=?",(int(enterprise_id),)).fetchone():
        conn.execute("UPDATE civilian_enterprises SET owner_actor_id=COALESCE(owner_actor_id,?) WHERE id=?",(aid,int(enterprise_id)))
        from .merchant import add_enterprise_staff
        add_enterprise_staff(conn,int(enterprise_id),aid,role='owner-factor',authority=90,specialty='trade',metadata={'latent_entity_id':int(latent['id'])})
    upsert_continuity_core(conn,'actor',aid,{'latent_entity_id':int(latent['id']),'latent_constraints':constraints,'latent_history':hist,'significance_at_crystallization':score,'score_parts':parts},source_kind='engine',crystallized_day=day,notes='Identity materialized from pre-existing latent population; prior context preserved, missing biography not invented.')
    set_resolution(conn,'actor',aid,'TRACKED',day=day,reason='latent person crossed persistent causal significance threshold',source_kind='engine',locked_min_level='STRUCTURAL',review_cadence_days=90,next_review_day=day+90,metadata={'latent_entity_id':int(latent['id'])})
    _sync_sim_tier(conn,aid,'TRACKED',day)
    conn.execute("UPDATE latent_entities SET status='crystallized',crystallized_entity_kind='actor',crystallized_entity_id=?,updated_day=? WHERE id=?",(aid,day,int(latent['id'])))
    # POPBACK-01 continuity: if this latent person originated as a sampled ordinary identity,
    # carry the same identity link through to the named actor instead of spawning a replacement.
    if _table(conn,'background_population_identity_links'):
        conn.execute("""UPDATE background_population_identity_links
                        SET status='crystallized',actor_id=?,last_update_day=?
                        WHERE latent_entity_id=?""",(aid,day,int(latent['id'])))
    return aid

def _review_latent(conn: sqlite3.Connection, latent_id: int, day: int) -> dict[str,Any]:
    latent=conn.execute("SELECT * FROM latent_entities WHERE id=?",(latent_id,)).fetchone()
    if not latent: raise ValueError('Unknown latent entity')
    prof=conn.execute("SELECT * FROM latent_resolution_profiles WHERE latent_entity_id=?",(latent_id,)).fetchone()
    current=str(prof['resolution_level']) if prof else 'LATENT'
    score,parts=_latent_significance(conn,latent,day); target=_latent_level(score)
    applied=target; action='none' if target==current else ('promote' if {'LATENT':0,'STRUCTURAL':1,'TRACKED':2}[target]>{'LATENT':0,'STRUCTURAL':1,'TRACKED':2}[current] else 'demote')
    cadence={'TRACKED':90,'STRUCTURAL':180,'LATENT':365}[target]
    conn.execute("""INSERT INTO latent_resolution_profiles(latent_entity_id,resolution_level,significance_score,previous_level,last_review_day,next_review_day,last_changed_day,metadata_json)
                  VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(latent_entity_id) DO UPDATE SET previous_level=latent_resolution_profiles.resolution_level,
                  resolution_level=excluded.resolution_level,significance_score=excluded.significance_score,last_review_day=excluded.last_review_day,
                  next_review_day=excluded.next_review_day,last_changed_day=CASE WHEN latent_resolution_profiles.resolution_level<>excluded.resolution_level THEN excluded.last_changed_day ELSE latent_resolution_profiles.last_changed_day END,
                  metadata_json=excluded.metadata_json""",
                 (latent_id,target,score,current,day,day+cadence,day,_j({'score_parts':parts})))
    materialized_actor_id=None
    if target=='TRACKED' and str(latent['latent_kind'])=='person' and int(latent['count_estimate'])==1:
        materialized_actor_id=_materialize_latent_person(conn,latent,day,score,parts)
    ek='latent_person' if str(latent['latent_kind'])=='person' else 'latent_institution'
    conn.execute("""INSERT INTO resolution_reviews(day,entity_kind,entity_id,prior_level,proposed_level,applied_level,significance_score,trigger_json,reason,action)
                  VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 (day,ek,latent_id,current,target,applied,score,_j(parts),'autonomous latent consequence review',action if action in {'none','promote','demote'} else 'none'))
    return {'latent_entity_id':latent_id,'prior_level':current,'applied_level':target,'significance_score':score,'action':action,'materialized_actor_id':materialized_actor_id}


def next_resolution_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    """Pure due-date query for resolution work.

    Scheduler lookahead must never mutate world state and must never depend on the caller's
    requested horizon.  The previous implementation inserted missing latent profiles here
    with ``MIN(created_day + 180, end_day)``; consequently advance(30) could crystallize a
    person months earlier than advance(365).  Missing profiles now advertise their natural
    first review date directly and are materialized only when the resolution owner runs.
    """
    vals=[]
    r=conn.execute("""SELECT MIN(next_review_day) FROM entity_resolution
                      WHERE entity_kind IN ('actor','institution') AND next_review_day>? AND next_review_day<=?""",(after_day,end_day)).fetchone()
    if r and r[0] is not None: vals.append(int(r[0]))
    if _table(conn,'latent_entities'):
        lr=conn.execute("""SELECT MIN(lr.next_review_day)
                           FROM latent_resolution_profiles lr
                           JOIN latent_entities le ON le.id=lr.latent_entity_id
                           WHERE le.status IN ('latent','partially_crystallized')
                             AND lr.next_review_day>? AND lr.next_review_day<=?""",(after_day,end_day)).fetchone()
        if lr and lr[0] is not None: vals.append(int(lr[0]))
        missing=conn.execute("""SELECT MIN(le.created_day + 180)
                                FROM latent_entities le
                                LEFT JOIN latent_resolution_profiles lr ON lr.latent_entity_id=le.id
                                WHERE le.status IN ('latent','partially_crystallized')
                                  AND lr.latent_entity_id IS NULL
                                  AND le.created_day + 180>? AND le.created_day + 180<=?""",(after_day,end_day)).fetchone()
        if missing and missing[0] is not None: vals.append(int(missing[0]))
    if _table(conn,'emergent_institution_candidates'):
        org=conn.execute("""SELECT MIN(updated_day + 1) FROM emergent_institution_candidates
                            WHERE status='eligible' AND updated_day + 1>? AND updated_day + 1<=?""",(after_day,end_day)).fetchone()
        if org and org[0] is not None: vals.append(int(org[0]))
    return min(vals) if vals else None


def process_due_resolution(conn: sqlite3.Connection, day: int) -> dict[str,int]:
    reviewed=promoted=demoted=latent_reviewed=latent_promoted=latent_materialized=institution_crystallized=0
    rows=conn.execute("""SELECT er.entity_kind,er.entity_id,er.resolution_level,er.review_cadence_days
                         FROM entity_resolution er JOIN actors a ON a.id=er.entity_id
                         WHERE er.entity_kind IN ('actor','institution') AND er.next_review_day<=?
                           AND ((er.entity_kind='actor' AND a.actor_type='character') OR (er.entity_kind='institution' AND a.actor_type='institution'))
                         ORDER BY er.next_review_day,er.entity_kind,er.entity_id""",(day,)).fetchall()
    for row in rows:
        out=review_entity(conn,str(row['entity_kind']),int(row['entity_id']),day=day)
        reviewed+=1
        if out['action']=='promote': promoted+=1
        if out['action']=='demote': demoted+=1
        # None/defer reviews must still advance their own clock; a due row must never become permanently stale.
        state=conn.execute("SELECT resolution_level,review_cadence_days,next_review_day FROM entity_resolution WHERE entity_kind=? AND entity_id=?",(row['entity_kind'],row['entity_id'])).fetchone()
        if state and int(state['next_review_day'] or 0)<=day:
            cadence=int(state['review_cadence_days'] or ({'ACTIVE':30,'TRACKED':90}.get(str(state['resolution_level']),180)))
            conn.execute("UPDATE entity_resolution SET next_review_day=? WHERE entity_kind=? AND entity_id=?",(day+cadence,row['entity_kind'],row['entity_id']))
    # Seed/review latent resolution identities.
    conn.execute("""INSERT OR IGNORE INTO latent_resolution_profiles(latent_entity_id,resolution_level,significance_score,last_review_day,next_review_day,last_changed_day,metadata_json)
                  SELECT id,'LATENT',0,created_day,created_day+180,created_day,'{}' FROM latent_entities
                  WHERE status IN ('latent','partially_crystallized')""")
    for row in conn.execute("SELECT lr.latent_entity_id,lr.resolution_level FROM latent_resolution_profiles lr JOIN latent_entities le ON le.id=lr.latent_entity_id WHERE le.status IN ('latent','partially_crystallized') AND lr.next_review_day<=? ORDER BY lr.next_review_day,lr.latent_entity_id",(day,)).fetchall():
        out=_review_latent(conn,int(row['latent_entity_id']),day);latent_reviewed+=1
        if out['action']=='promote':latent_promoted+=1
        if out.get('materialized_actor_id'): latent_materialized+=1
    # Eligible organizations cross into persistent structural identity whether or not their
    # ordinary/social name is yet known.  Naming is a social fact, not an ontology gate.
    if _table(conn,'emergent_institution_candidates'):
        candidates=conn.execute("SELECT id FROM emergent_institution_candidates WHERE status='eligible' ORDER BY id").fetchall()
        for cand in candidates:
            crystallize_institution_candidate(conn,int(cand[0]),day=day); institution_crystallized+=1
    return {'entities_reviewed':reviewed,'promotions':promoted,'demotions':demoted,'latent_reviewed':latent_reviewed,'latent_promotions':latent_promoted,'latent_materialized':latent_materialized,'institution_crystallized':institution_crystallized}

def create_institution_candidate(conn: sqlite3.Connection, candidate_kind: str, *, location_id: int | None = None, enterprise_id: int | None = None, founder_actor_id: int | None = None, proposed_name: str | None = None, significance_score: float = 0.0, resources: dict[str,Any] | None = None, participants: list[int] | None = None, evidence: list[dict[str,Any]] | None = None, day: int | None = None) -> int:
    """Records causal formation. This does not itself invent/crystallize an organization."""
    day = _day(conn) if day is None else int(day)
    if not evidence:
        raise ValueError("Emergent institution candidates require causal evidence")
    cur = conn.execute(
        """INSERT INTO emergent_institution_candidates(candidate_kind,location_id,enterprise_id,founder_actor_id,proposed_name,significance_score,resources_json,participants_json,evidence_json,status,created_day,updated_day)
           VALUES (?,?,?,?,?,?,?,?,?,'forming',?,?)""",
        (candidate_kind,location_id,enterprise_id,founder_actor_id,proposed_name,float(significance_score),_j(resources),_j(participants or []),_j(evidence),day,day),
    )
    return int(cur.lastrowid)


def _institution_candidate_eligible(candidate_kind: str, score: float, evidence: list[dict[str,Any]], resources: dict[str,Any]) -> bool:
    """Domain-aware persistence threshold. A successful enterprise is not automatically an institution.

    In particular, the old commercial slice used ``merchant_house`` as a business archetype for
    ordinary wholesalers.  ORGLIFE must not interpret that implementation label as evidence that
    a durable merchant institution exists.  A merchant firm needs organizational depth beyond one
    operator: staff/branches, or a sustained multi-market contracting footprint.
    """
    if not evidence:
        return False
    kind = str(candidate_kind or "").strip().lower().replace('_',' ')
    if kind in {"merchant firm", "merchant house"}:
        age_days = int(resources.get("business_age_days") or 0)
        active_staff = int(resources.get("active_staff") or 0)
        branch_count = int(resources.get("branch_count") or 0)
        completed = int(resources.get("completed_trade_contracts") or 0)
        markets = int(resources.get("distinct_trade_locations") or 0)
        organizational_depth = active_staff >= 2 or branch_count >= 2 or (completed >= 12 and markets >= 3)
        return score >= 45.0 and age_days >= 3 * 365 and organizational_depth
    return score >= 32.0


def update_institution_candidate(conn: sqlite3.Connection, candidate_id: int, *, significance_score: float | None = None, resources: dict[str,Any] | None = None, participants: list[int] | None = None, evidence_append: dict[str,Any] | None = None, day: int | None = None) -> dict[str,Any]:
    day = _day(conn) if day is None else int(day)
    row = conn.execute("SELECT * FROM emergent_institution_candidates WHERE id=?", (candidate_id,)).fetchone()
    if not row: raise ValueError("Unknown emergent institution candidate")
    evidence = json.loads(row["evidence_json"] or "[]")
    if evidence_append: evidence.append(evidence_append)
    score = float(row["significance_score"] if significance_score is None else significance_score)
    next_resources = resources if resources is not None else json.loads(row["resources_json"] or "{}")
    # Eligibility is recomputed rather than made sticky. If later evidence reveals that an old
    # generic candidate never possessed institutional depth, it remains a forming enterprise
    # instead of being grandfathered into a durable organization. Crystallized rows are immutable.
    prior_status = str(row["status"])
    if prior_status == "crystallized":
        status = prior_status
    else:
        status = "eligible" if _institution_candidate_eligible(str(row["candidate_kind"]), score, evidence, next_resources) else "forming"
    conn.execute(
        "UPDATE emergent_institution_candidates SET significance_score=?,resources_json=?,participants_json=?,evidence_json=?,status=?,updated_day=? WHERE id=?",
        (score,_j(next_resources),_j(participants if participants is not None else json.loads(row["participants_json"] or "[]")),_j(evidence),status,day,candidate_id),
    )
    return dict(conn.execute("SELECT * FROM emergent_institution_candidates WHERE id=?", (candidate_id,)).fetchone())


def crystallize_institution_candidate(conn: sqlite3.Connection, candidate_id: int, *, name: str | None = None, day: int | None = None) -> int:
    """Turns a causally formed organization into a persistent institution. History comes from evidence; none is retro-invented."""
    day = _day(conn) if day is None else int(day)
    row = conn.execute("SELECT * FROM emergent_institution_candidates WHERE id=?", (candidate_id,)).fetchone()
    if not row: raise ValueError("Unknown emergent institution candidate")
    if row["status"] != "eligible": raise ValueError("Candidate is not yet eligible for crystallization")
    grounded_name = name or row["proposed_name"]
    unresolved_name = not bool(grounded_name and str(grounded_name).strip())
    final_name = str(grounded_name).strip() if not unresolved_name else f"[STRUCTURAL] {row['candidate_kind']} candidate #{candidate_id}"
    if conn.execute("SELECT 1 FROM actors WHERE name=?", (final_name,)).fetchone():
        final_name = f"{final_name} / day {day}"
    participants = json.loads(row["participants_json"] or "[]")
    evidence = json.loads(row["evidence_json"] or "[]")
    resources = json.loads(row["resources_json"] or "{}")
    preexisting = bool(resources.get("preexisting_organization"))
    note = "Crystallized from pre-existing organization evidence" if preexisting else "Crystallized from causal formation evidence"
    if unresolved_name:
        note += "; structural identity only, ordinary/social name unresolved"
    cur = conn.execute(
        "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) VALUES (?,'institution',?,?,?,?,?,0)",
        (final_name,row["candidate_kind"],row["location_id"],row["location_id"],"active",note),
    )
    aid = int(cur.lastrowid)
    set_institution_profile(conn, aid, str(row["candidate_kind"]), primary_location_id=row["location_id"], capacity={"participant_count":len(participants)}, trajectory="rising", notes="Emergent institution; no retroactive perfect history invented.")
    upsert_continuity_core(conn,"institution",aid,{"formation_candidate_id":candidate_id,"participants":participants,"evidence":evidence,"resources":resources,"preexisting_before_crystallization":preexisting,"unresolved_name":unresolved_name},source_kind="engine",crystallized_day=day,notes="Pre-existing history preserved through crystallization." if preexisting else "Formation history preserved from causal candidate.")
    for pid in participants:
        if conn.execute("SELECT 1 FROM actors WHERE id=? AND actor_type='character'", (int(pid),)).fetchone():
            membership_kind = 'existing_member' if preexisting else 'founding_member'
            conn.execute("INSERT OR IGNORE INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,status,joined_day,provenance_json,metadata_json) VALUES (?,?,?,'active',?,?,?)", (aid,int(pid),membership_kind,day,_j(["pre-existing organization crystallization" if preexisting else "emergent institution candidate"]),_j({"candidate_id":candidate_id,"preexisting":preexisting})))
    set_resolution(conn,"institution",aid,"TRACKED",day=day,reason="causally formed organization crossed persistence threshold",source_kind="engine",locked_min_level="STRUCTURAL",review_cadence_days=90,next_review_day=day+90,metadata={"candidate_id":candidate_id})
    _sync_sim_tier(conn,aid,"TRACKED",day)
    if "criminal" in str(row["candidate_kind"]).lower() and _table(conn,"underworld_organizations"):
        org_type=str(resources.get("organization_type") or "gang")
        leader=row["founder_actor_id"] or (participants[0] if participants else None)
        conn.execute("""INSERT OR IGNORE INTO underworld_organizations(organization_key,organization_type,name,founder_actor_id,institution_actor_id,
                          primary_location_id,member_count_estimate,command_depth,territorial_presence,racket_breadth,front_depth,corrupt_access,
                          reputation_deterrence,violence_capacity,cohesion,membership_stability,succession_depth,status,created_day,updated_day,metadata_json,current_leader_actor_id,treasury)
                          VALUES (?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,'active',?,?,?, ?,?)""",
                     (f"emergent:candidate:{candidate_id}",org_type,final_name,row["founder_actor_id"],aid,row["location_id"],
                      max(1.0,float(resources.get("member_count_estimate") or len(participants) or 1)),
                      float(resources.get("territorial_presence") or 10),float(resources.get("racket_breadth") or 0),
                      float(resources.get("front_depth") or 0),float(resources.get("corrupt_access") or 0),
                      float(resources.get("reputation_deterrence") or 10),float(resources.get("violence_capacity") or 10),
                      float(resources.get("cohesion") or 50),float(resources.get("membership_stability") or 50),
                      float(resources.get("succession_depth") or 0),day,day,_j({"candidate_id":candidate_id,"crystallized_by":"resolution_controller"}),
                      int(leader) if leader is not None else None,float(resources.get("treasury") or 0)))
    conn.execute("UPDATE emergent_institution_candidates SET status='crystallized',crystallized_institution_actor_id=?,updated_day=? WHERE id=?", (aid,day,candidate_id))
    try:
        from .organization_lifecycle import record_formation
        record_formation(conn, aid, candidate_id=candidate_id, unresolved_name=unresolved_name,
                         detail={"candidate_kind": str(row["candidate_kind"]), "preexisting": preexisting})
    except sqlite3.OperationalError:
        # Compatibility for deliberately pre-ORGLIFE schemas opened in isolation.
        pass
    conn.execute("INSERT INTO resolution_reviews(day,entity_kind,entity_id,prior_level,proposed_level,applied_level,significance_score,trigger_json,reason,action) VALUES (?,?,?,?,?,?,?,?,?,?)", (day,"institution",aid,"LATENT","TRACKED","TRACKED",float(row["significance_score"]),_j({"candidate_id":candidate_id}),"causal organization formation reached persistent relevance","crystallize_institution"))
    return aid
```

## engine/activation.py

```python
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .business import configure_enterprise_business, set_commercial_context
from .civilian import (
    add_production_site,
    create_auction,
    create_cultural_object,
    create_enterprise,
    ensure_good,
    set_market_condition,
)
from .civilian_life import create_building
from .education import (
    _set_competence_floor, add_knowledge_custody, configure_reproduction, create_knowledge_asset,
    create_program, create_teaching_relationship, enroll, ensure_structural_training_cohorts,
)
from .ecology import configure_environment
from .cultivation import seed_cultivation_from_current_source
from .elixir import configure_elixir_supply, initialize_cultivation_physiology
from .politics import configure_polity, set_territorial_control
from .religion import configure_cultural_institution, configure_religious_institution

MARTIAL_INSTITUTION_KINDS={
    'sect','sect/school','martial school','military school','military academy','military college','order','clan/house','coven',
    'state martial establishment','martial/religious order','martial religious order','martial institution','noble martial house','military tradition'
}

# Opening-world activation is versioned separately from the SQL schema. A database can be
# schema-current yet still be missing newer opening projections. Long-horizon release gates
# verify this value before accepting the opening world.
CURRENT_CANON_ACTIVATION_VERSION = 20


def _load(raw: str | None, default):
    try: return json.loads(raw) if raw else default
    except Exception: return default


def _common_institution(conn: sqlite3.Connection, a: int, b: int) -> int | None:
    row=conn.execute('''SELECT x.institution_actor_id FROM institution_memberships x
                        JOIN institution_memberships y ON y.institution_actor_id=x.institution_actor_id
                        WHERE x.member_actor_id=? AND y.member_actor_id=? AND x.status='active' AND y.status='active'
                        ORDER BY x.institution_actor_id LIMIT 1''',(a,b)).fetchone()
    return int(row[0]) if row else None


def activate_explicit_teaching(conn: sqlite3.Connection) -> dict[str,int]:
    created_rel=0; competence=0
    rows=conn.execute("SELECT * FROM typed_relationship_facts WHERE status='active' AND relation_type IN ('direct_transmission','teacher_of') ORDER BY id").fetchall()
    for r in rows:
        teacher,student=int(r['actor_a_id']),int(r['actor_b_id'])
        if not conn.execute("SELECT 1 FROM actor_life_profiles WHERE actor_id=? AND life_status='living'",(teacher,)).fetchone(): continue
        if not conn.execute("SELECT 1 FROM actor_life_profiles WHERE actor_id=? AND life_status='living'",(student,)).fetchone(): continue
        # The explicit fact that A teaches B establishes teaching competence. No combat competence or Stage is inferred.
        _set_competence_floor(conn,teacher,'martial_instruction',60,source_kind='canon'); competence+=1
        kind='personal_master' if r['relation_type']=='direct_transmission' else 'instructor'
        existing=conn.execute("SELECT id FROM teaching_relationships WHERE teacher_actor_id=? AND student_actor_id=? AND relation_kind=? AND domain_key='martial_instruction' AND status='active'",(teacher,student,kind)).fetchone()
        if not existing:
            create_teaching_relationship(conn,teacher,student,kind,'martial_instruction',institution_actor_id=_common_institution(conn,teacher,student),responsibility=60,notes='Activated from explicit current-seed teaching/transmission fact; does not infer Stage progression.')
            created_rel+=1
    return {'explicit_teaching_relationships_created':created_rel,'teaching_competence_anchors':competence}


def activate_institution_training_contexts(conn: sqlite3.Connection) -> dict[str,int]:
    programs=0; enrollments=0; reproduction=0
    insts=conn.execute("SELECT ip.actor_id,ip.institution_kind FROM institution_profiles ip JOIN actors a ON a.id=ip.actor_id WHERE a.status='active'").fetchall()
    for inst in insts:
        kind=str(inst['institution_kind'] or '').lower()
        if kind not in MARTIAL_INSTITUTION_KINDS: continue
        iid=int(inst['actor_id'])
        configure_reproduction(conn,iid,recruitment_capacity=50,training_capacity=50,instructor_depth=50,archival_resilience=50,review_cadence_days=90,
                               metadata={'authority':'CAMPAIGN_CALIBRATION','meaning':'neutral initial capacities; not canon headcounts or quality rankings'})
        reproduction+=1
        key='aggregate-foundation-context'
        row=conn.execute("SELECT id FROM education_programs WHERE institution_actor_id=? AND program_key=?",(iid,key)).fetchone()
        if row: pid=int(row[0])
        else:
            pid=create_program(conn,key,'Aggregate foundation training context','martial_foundation','martial_foundation',institution_actor_id=iid,
                               duration_days=730,capacity=max(8,int(conn.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=? AND status='active'",(iid,)).fetchone()[0])*2),
                               min_entry_score=0,min_teacher_score=0,completion_gain=3,max_score_from_program=40,review_cadence_days=30,
                               metadata={'authority':'CAMPAIGN_ASSUMPTION','basis':'martial institution + active named trainee state','does_not_mean':'uniform curriculum, exclusive instruction, or Stage progression'})
            programs+=1
        # Named low-stage members already marked as actively training are safe participants in an aggregate context.
        candidates=conn.execute('''SELECT m.member_actor_id,s.source_payload_json FROM institution_memberships m
            JOIN source_identity_map s ON s.entity_kind='actor' AND s.entity_id=m.member_actor_id AND s.source_namespace='caerness_seed_v1_1'
            WHERE m.institution_actor_id=? AND m.status='active' ''',(iid,)).fetchall()
        for c in candidates:
            payload=_load(c['source_payload_json'],{})
            rt=payload.get('runtime_v1_1') or {}; tr=rt.get('training_state') or {}
            if not tr.get('active') or payload.get('stage') not in {'First','Temper'}: continue
            aid=int(c['member_actor_id'])
            if conn.execute("SELECT 1 FROM education_enrollments WHERE actor_id=? AND program_id=? AND status IN ('active','paused','completed')",(aid,pid)).fetchone(): continue
            enroll(conn,aid,pid,practice_quality=1.0,metadata={'authority':'CAMPAIGN_ASSUMPTION','basis':'explicit active training state + institution membership','stage_progression':False})
            enrollments+=1
    return {'training_programs_created':programs,'training_enrollments_created':enrollments,'reproduction_profiles_configured':reproduction}


def _archetype_for(name: str, kind: str) -> str | None:
    k=kind.lower(); n=name.lower()
    if k=='financial institution': return 'loan_house'
    if k=='merchant-noble house': return 'warehouse'
    if k=='company ecosystem': return 'warehouse'
    if k=='smuggling power': return 'warehouse'
    if k=='gambling/fight syndicate': return 'gambling_house'
    if k=='criminal dynasty': return 'warehouse'
    if 'brass lantern' in n: return 'appraiser'
    if 'still hand' in n: return 'refiner'
    return None


def activate_commercial_anchors(conn: sqlite3.Connection) -> dict[str,int]:
    created=0; profiled=0
    rows=conn.execute('''SELECT a.id,a.name,a.current_location_id,ip.institution_kind,ip.economic_json
                         FROM actors a JOIN institution_profiles ip ON ip.actor_id=a.id
                         WHERE a.actor_type='institution' AND a.status='active' ORDER BY a.id''').fetchall()
    for r in rows:
        archetype=_archetype_for(str(r['name']),str(r['institution_kind'] or ''))
        if not archetype: continue
        iid=int(r['id'])
        existing=conn.execute("SELECT id FROM civilian_enterprises WHERE institution_actor_id=? AND json_extract(metadata_json,'$.activation_key')='current-canon-aggregate-arm' LIMIT 1",(iid,)).fetchone()
        if existing: eid=int(existing[0])
        else:
            econ=_load(r['economic_json'],{})
            eid=create_enterprise(conn,f"{r['name']} — aggregate commercial arm",'other',institution_actor_id=iid,location_id=r['current_location_id'],
                                  capital=50,cash=25,debt=0,reputation=50,admin_quality=50,labor_capacity=50,risk_tolerance=50,
                                  metadata={'activation_key':'current-canon-aggregate-arm','authority':'CAMPAIGN_CALIBRATION','source_economic_state':econ,
                                            'meaning':'one aggregate operating footprint, not a claim that the institution owns exactly one business'})
            created+=1
        configure_enterprise_business(conn,eid,archetype,quality=50,price_position=50,capacity=50,clientele_fit=50,service_reliability=50,regulatory_pressure=20 if archetype in {'gambling_house'} else 5,
                                      cadence_days=30,metadata={'authority':'CAMPAIGN_CALIBRATION','institution_actor_id':iid})
        profiled+=1
    return {'aggregate_enterprises_created':created,'business_profiles_configured':profiled}


def _location(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def _institution(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def _aggregate_enterprise(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    location_id: int,
    archetype: str,
    *,
    institution_actor_id: int | None = None,
    enterprise_kind: str = 'other',
    capital: float = 50,
    cash: float = 25,
    quality: float = 50,
    capacity: float = 50,
    notes: str,
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM civilian_enterprises WHERE json_extract(metadata_json,'$.activation_key')=? LIMIT 1",
        (key,),
    ).fetchone()
    created = False
    if row:
        eid = int(row[0])
        conn.execute(
            "UPDATE civilian_enterprises SET location_id=COALESCE(location_id,?),institution_actor_id=COALESCE(institution_actor_id,?) WHERE id=?",
            (location_id, institution_actor_id, eid),
        )
    else:
        eid = create_enterprise(
            conn, name, enterprise_kind, institution_actor_id=institution_actor_id, location_id=location_id,
            capital=capital, cash=cash, debt=0, reputation=50, admin_quality=50, labor_capacity=50,
            risk_tolerance=45,
            metadata={
                'activation_key': key,
                'authority': 'CAMPAIGN_CALIBRATION',
                'basis': notes,
                'resolution': 'AGGREGATE_SECTOR',
                'does_not_mean': 'one literal firm, universal prices, or a complete local economy',
            },
        )
        created = True
    configure_enterprise_business(
        conn, eid, archetype, quality=quality, price_position=50, capacity=capacity,
        clientele_fit=55, service_reliability=55, regulatory_pressure=5, cadence_days=30,
        metadata={'authority':'CAMPAIGN_CALIBRATION','activation_key':key,'basis':notes},
    )
    return eid, created


def _ensure_production(
    conn: sqlite3.Connection,
    enterprise_id: int,
    good_id: int,
    *,
    capacity: float,
    inventory: float,
    efficiency: float = 55,
    material_access: float = 60,
    skilled_labor: float = 55,
    notes: str,
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM production_sites WHERE enterprise_id=? AND good_id=?",
        (enterprise_id, good_id),
    ).fetchone()
    if row:
        return int(row[0]), False
    pid = add_production_site(
        conn, enterprise_id, good_id, capacity_per_30=capacity, efficiency=efficiency,
        material_access=material_access, skilled_labor=skilled_labor, inventory=inventory,
        notes=notes,
    )
    return pid, True


def _ensure_aggregate_building(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    building_kind: str,
    location_id: int,
    *,
    institution_actor_id: int | None = None,
    basis: str,
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM buildings WHERE json_extract(metadata_json,'$.activation_key')=? LIMIT 1",
        (key,),
    ).fetchone()
    if row:
        return int(row[0]), False
    bid = create_building(
        conn, name, building_kind, location_id=location_id, institution_actor_id=institution_actor_id,
        capacity=60, condition=90, prestige=50, utility=75, maintenance_burden=8,
        metadata={
            'activation_key': key,
            'authority': 'CAMPAIGN_CALIBRATION',
            'basis': basis,
            'resolution': 'AGGREGATE_INFRASTRUCTURE',
            'does_not_mean': 'one literal building or a complete district census',
        },
    )
    return bid, True


def activate_economic_substrate(conn: sqlite3.Connection) -> dict[str, int]:
    """Seed a sparse, explicitly aggregate current-canon economy.

    The World Bible gives commercial *roles* and hubs but intentionally does not provide a
    continent-wide price/capacity table.  Therefore all numerical values below are campaign
    calibration in abstract economic units.  We seed market presence broadly, but production
    only where the Bible explicitly supports making/refining/assembling the relevant goods.
    Specific loans, debts, counterparties and ownership shares are not invented here.
    """
    # Abstract price indices, not an in-world currency declaration.
    goods = {
        'ordinary-grain': ('Grain and staple food', 'food', 1.0, 'bulk unit', 0.20, 0.10, 0.00),
        'ordinary-cloth': ('Cloth and ordinary textiles', 'textile', 2.0, 'bolt', 0.02, 0.45, 0.15),
        'ordinary-timber': ('Timber and building material', 'material', 1.4, 'load', 0.02, 0.20, 0.00),
        'ordinary-medicine': ('Ordinary medicines and medical supplies', 'medicine', 4.0, 'lot', 0.08, 0.65, 0.20),
        'vein-root': ('Vein-Root', 'cultivation_resource', 8.0, 'lot', 0.08, 0.70, 0.45),
        'metalwork': ('Tools, arms and metalwork', 'craft', 5.0, 'lot', 0.00, 0.75, 0.30),
        'travel-supplies': ('Travel and caravan supplies', 'material', 2.5, 'load', 0.05, 0.35, 0.05),
        'naval-supplies': ('Shipbuilding and naval supplies', 'material', 4.5, 'load', 0.00, 0.60, 0.20),
    }
    good_ids: dict[str, int] = {}
    for key, spec in goods.items():
        good_ids[key] = ensure_good(
            conn, key, spec[0], spec[1], spec[2], unit=spec[3], perishability=spec[4],
            skill_intensity=spec[5], luxury=spec[6],
            notes='v0.30 campaign-calibration price index; category/existence is setting-supported, number is not canon currency.',
        )

    # Current Bible commercial geography. Values are relative pressures only.
    hub_context = {
        'Toll’s Reach': dict(foot_traffic=80, traveler_flow=82, trade_flow=92, credit_demand=70, craft_demand=65, security=55, event_activity=65),
        'Aldergate': dict(foot_traffic=78, traveler_flow=72, trade_flow=95, credit_demand=88, craft_demand=70, security=68, construction_demand=65),
        'Cairnholt': dict(foot_traffic=78, traveler_flow=72, trade_flow=72, elite_patronage=88, cultural_activity=78, event_activity=82, health_demand=68),
        'Waymeet': dict(foot_traffic=75, traveler_flow=94, trade_flow=76, credit_demand=62, event_activity=70, security=62),
        'Lysmere': dict(foot_traffic=62, traveler_flow=68, trade_flow=62, health_demand=96, craft_demand=70, elite_patronage=65, security=82),
        'Aldenmoor': dict(foot_traffic=58, traveler_flow=55, trade_flow=58, elite_patronage=72, cultural_activity=92, craft_demand=70, reputation_climate=85),
        'Saltmere': dict(foot_traffic=86, traveler_flow=88, trade_flow=98, credit_demand=82, craft_demand=82, construction_demand=80, security=62, cultural_activity=72),
        'Stonecross': dict(foot_traffic=58, traveler_flow=62, trade_flow=68, craft_demand=90, military_demand=72, construction_demand=68, security=66),
        'Redford': dict(foot_traffic=55, traveler_flow=58, trade_flow=70, craft_demand=58, health_demand=55, security=62),
    }
    contexts = 0
    for name, values in hub_context.items():
        lid = _location(conn, name)
        if lid is not None:
            set_commercial_context(conn, lid, **values)
            contexts += 1

    # Markets describe circulation/demand, not local manufacture. Supply/demand are relative
    # starting pressures chosen to make hubs behave differently without claiming exact prices.
    market_plan = {
        'Toll’s Reach': {
            'ordinary-grain': (70,72), 'ordinary-cloth':(72,74), 'ordinary-timber':(68,72),
            'ordinary-medicine':(62,72), 'vein-root':(52,68), 'metalwork':(62,75),
            # Toll is a provisioning/export hub. Local consumption is deliberately below
            # aggregate provisioning output so exportable stock can exist for the logistics
            # subsystem instead of every unit being silently sold at origin.
            'travel-supplies':(82,34), 'naval-supplies':(70,78),
        },
        'Aldergate': {
            'ordinary-grain':(88,76), 'ordinary-cloth':(82,76), 'ordinary-timber':(78,74),
            'ordinary-medicine':(65,70), 'vein-root':(58,64), 'metalwork':(72,76), 'travel-supplies':(78,80),
        },
        'Cairnholt': {
            'ordinary-grain':(60,82), 'ordinary-cloth':(58,84), 'ordinary-timber':(55,68),
            'ordinary-medicine':(55,82), 'vein-root':(45,84), 'metalwork':(55,80), 'travel-supplies':(58,75),
        },
        'Waymeet': {
            'ordinary-grain':(62,80), 'ordinary-cloth':(60,72), 'ordinary-medicine':(52,75),
            'metalwork':(58,70), 'travel-supplies':(50,92),
        },
        'Lysmere': {
            'ordinary-grain':(62,74), 'ordinary-medicine':(85,92), 'vein-root':(60,82), 'travel-supplies':(62,68),
        },
        'Aldenmoor': {
            'ordinary-grain':(65,70), 'ordinary-cloth':(62,74), 'ordinary-medicine':(55,64), 'metalwork':(54,60),
        },
        'Saltmere': {
            'ordinary-grain':(76,78), 'ordinary-cloth':(82,78), 'ordinary-timber':(82,86),
            'ordinary-medicine':(78,76), 'vein-root':(75,72), 'metalwork':(75,82),
            # Dovell's explicit shipbuilding/naval-supply base is export-facing.
            'travel-supplies':(82,78), 'naval-supplies':(90,28),
        },
        'Stonecross': {'ordinary-grain':(58,70), 'metalwork':(88,62), 'travel-supplies':(62,68)},
        'Redford': {'ordinary-grain':(68,72), 'vein-root':(72,62), 'travel-supplies':(58,66)},
    }
    market_rows = 0
    for loc_name, plan in market_plan.items():
        lid = _location(conn, loc_name)
        if lid is None:
            continue
        for good_key, (supply, demand) in plan.items():
            set_market_condition(
                conn, lid, good_ids[good_key], supply=supply, demand=demand,
                transport_pressure=8 if loc_name in {'Waymeet','Redford','Stonecross'} else 4,
                risk_pressure=6 if loc_name in {'Toll’s Reach','Waymeet'} else 3,
                tax_pressure=5, cadence_days=30,
                metadata={
                    'authority':'CAMPAIGN_CALIBRATION',
                    'basis':'World Bible commercial geography and ordinary material economy',
                    'cadence_days':30,
                    'numeric_status':'relative simulation index, not canon price/volume',
                },
            )
            market_rows += 1

    # Correct the location of three explicit institutions whose v1.1 structured seed omitted
    # place_ref but whose MASTER FINAL Bible states their principal seat/headquarters.
    explicit_seats = {
        'Counting House': 'Aldergate',
        'Still Hand': 'Toll’s Reach',
        'Brass Lantern House': 'Toll’s Reach',
    }
    explicit_location_updates = 0
    for inst_name, loc_name in explicit_seats.items():
        iid, lid = _institution(conn, inst_name), _location(conn, loc_name)
        if iid is not None and lid is not None:
            # Canon-explicit present seats outrank any earlier non-canon opening working placement.
            # This is current-state correction, not invented travel/history.
            conn.execute("UPDATE actors SET home_location_id=?,current_location_id=? WHERE id=?", (lid,lid,iid))
            conn.execute("UPDATE institution_profiles SET primary_location_id=? WHERE actor_id=?", (lid,iid))
            conn.execute("UPDATE civilian_enterprises SET location_id=? WHERE institution_actor_id=?", (lid,iid))
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            conn.execute(
                """INSERT INTO actor_location_provenance(actor_id,location_id,provenance_kind,confidence,resolved_day,metadata_json)
                   VALUES (?,?, 'explicit_canon_seat',1.0,?,?)
                   ON CONFLICT(actor_id) DO UPDATE SET location_id=excluded.location_id,
                     provenance_kind=excluded.provenance_kind,confidence=excluded.confidence,
                     resolved_day=excluded.resolved_day,metadata_json=excluded.metadata_json""",
                (iid,lid,day,json.dumps({'opening_state':True,'history_invented':False,'authority':'MASTER_FINAL_EXPLICIT_SEAT'},sort_keys=True)),
            )
            explicit_location_updates += 1

    enterprises_created = 0
    production_created = 0

    # Explicitly supported making/assembling nodes only.
    # Still Hand: provision/procurement guild assembling mixed travel supplies at Toll's Reach.
    still = _institution(conn, 'Still Hand'); toll = _location(conn, 'Toll’s Reach')
    if still is not None and toll is not None:
        row = conn.execute("SELECT id FROM civilian_enterprises WHERE institution_actor_id=? ORDER BY id LIMIT 1", (still,)).fetchone()
        if row:
            eid = int(row[0]); conn.execute("UPDATE civilian_enterprises SET location_id=? WHERE id=?", (toll,eid))
        else:
            eid, made = _aggregate_enterprise(conn,'econ:still-hand-provisioning','Still Hand — aggregate provisioning arm',toll,'wholesaler',institution_actor_id=still,notes='MASTER FINAL: Still Hand headquarters in Toll’s Reach assembles mixed orders and travel supplies.')
            enterprises_created += int(made)
        _, made = _ensure_production(conn,eid,good_ids['travel-supplies'],capacity=18,inventory=8,notes='Aggregate provisioning/assembly, not raw-goods manufacture; campaign calibration grounded in Still Hand mixed-order role.')
        production_created += int(made)

    # House Dovell: explicit shipbuilding and naval supply at Saltmere.
    dovell = _institution(conn, 'House Dovell'); saltmere = _location(conn, 'Saltmere')
    if dovell is not None and saltmere is not None:
        row = conn.execute("SELECT id FROM civilian_enterprises WHERE institution_actor_id=? ORDER BY id LIMIT 1", (dovell,)).fetchone()
        if row:
            eid = int(row[0]); conn.execute("UPDATE civilian_enterprises SET location_id=? WHERE id=?", (saltmere,eid))
            configure_enterprise_business(conn,eid,'shipping_house',quality=55,capacity=65,clientele_fit=60,service_reliability=60,regulatory_pressure=8,cadence_days=30,metadata={'authority':'CAMPAIGN_CALIBRATION','basis':'MASTER FINAL: House Dovell shipbuilding and naval supply.'})
        else:
            eid, made = _aggregate_enterprise(conn,'econ:house-dovell-supply','House Dovell — aggregate naval supply arm',saltmere,'shipping_house',institution_actor_id=dovell,notes='MASTER FINAL: House Dovell dominates a large part of Windmere shipbuilding and naval supply.')
            enterprises_created += int(made)
        _, made = _ensure_production(conn,eid,good_ids['naval-supplies'],capacity=22,inventory=10,efficiency=60,material_access=65,skilled_labor=65,notes='Campaign-calibrated aggregate output grounded in explicit Dovell shipbuilding/naval-supply role.')
        production_created += int(made)

    # Lysmere explicitly contains refiners and medical manufacturing/services. This anonymous
    # aggregate avoids inventing a named school or proprietor.
    lys = _location(conn, 'Lysmere')
    if lys is not None:
        eid, made = _aggregate_enterprise(conn,'econ:lysmere-medical-sector','Lysmere — aggregate medical supply sector',lys,'medicine_shop',notes='MASTER FINAL: Lysmere contains rival medical schools, refiners, prosthetic makers and rehabilitation establishments.')
        enterprises_created += int(made)
        _, made2 = _ensure_production(conn,eid,good_ids['ordinary-medicine'],capacity=14,inventory=5,efficiency=60,material_access=60,skilled_labor=70,notes='Aggregate medicine/refining output; no named firm or monopoly implied.')
        production_created += int(made2)

    # Stonecross explicitly has smiths and Ore trade; model aggregate ordinary metalwork, not a
    # claim of Veinsteel volume or a named workshop.
    stone = _location(conn, 'Stonecross')
    if stone is not None:
        eid, made = _aggregate_enterprise(conn,'econ:stonecross-metal-sector','Stonecross — aggregate metalworking sector',stone,'smithy',notes='MASTER FINAL: Stonecross is a junction of smiths, Ore, guides and appraisers.')
        enterprises_created += int(made)
        _, made2 = _ensure_production(conn,eid,good_ids['metalwork'],capacity=16,inventory=6,efficiency=58,material_access=65,skilled_labor=62,notes='Ordinary tools/arms/metalwork aggregate; does not quantify Vein Ore or Veinsteel output.')
        production_created += int(made2)

    # Redroot Vale is the strongest explicit commercial Root-production geography, but the current
    # route graph has no direct Vale node connection. Keep production local; do not teleport freight.
    redroot = _location(conn, 'Redroot Vale')
    if redroot is not None:
        eid, made = _aggregate_enterprise(conn,'econ:redroot-production','Redroot Vale — aggregate Root production sector',redroot,'refiner',notes='MASTER FINAL: Redroot Vale is reliable enough for organized Vein-Root production.')
        enterprises_created += int(made)
        _, made2 = _ensure_production(conn,eid,good_ids['vein-root'],capacity=6,inventory=3,efficiency=52,material_access=75,skilled_labor=55,notes='Aggregate sustainable Root production calibration; does not fix acreage, owners, or harvest law.')
        production_created += int(made2)

    # Material infrastructure is represented as aggregate footprints, not exact building counts.
    building_specs = [
        ('econ:bld:toll-warehouses','Toll’s Reach — aggregate warehouse footprint','warehouse','Toll’s Reach','MASTER FINAL: dense warehouse districts at the River and Sea Quays.'),
        ('econ:bld:aldergate-warehouses','Aldergate — aggregate warehouse and caravan footprint','warehouse','Aldergate','MASTER FINAL: Exchange Quarter, warehouses and caravan wards.'),
        ('econ:bld:waymeet-caravan','Waymeet — aggregate caravan-court footprint','other','Waymeet','MASTER FINAL: inn yards, caravan courts and Contract Row.'),
        ('econ:bld:lysmere-medical','Lysmere — aggregate medical-establishment footprint','public_building','Lysmere','MASTER FINAL: rival medical schools, rehabilitation establishments, refiners and prosthetic makers.'),
        ('econ:bld:saltmere-port','Saltmere — aggregate port and warehouse footprint','warehouse','Saltmere','MASTER FINAL: principal international port with long-distance trade and overseas warehouse networks.'),
    ]
    buildings_created = 0
    for key,name,kind,loc_name,basis in building_specs:
        lid = _location(conn,loc_name)
        if lid is not None:
            _, made = _ensure_aggregate_building(conn,key,name,kind,lid,basis=basis)
            buildings_created += int(made)

    # The Brass Lantern explicitly runs four Grand Sales. The shared SV civil calendar is fixed,
    # but canon does not assign these sales exact dates, so these remain campaign-relative quarterly
    # placements until an in-world schedule is causally established. No lots are invented.
    auctions_created = 0
    brass = _institution(conn,'Brass Lantern House'); toll = _location(conn,'Toll’s Reach')
    if brass is not None and toll is not None:
        for idx, due in enumerate((90,180,270,360),1):
            key=f'econ:brass-grand-sale:{idx}'
            if conn.execute("SELECT 1 FROM auctions WHERE json_extract(metadata_json,'$.activation_key')=?",(key,)).fetchone():
                continue
            create_auction(conn,f'Brass Lantern Grand Sale — cycle {idx}',due,location_id=toll,institution_actor_id=brass,prestige=80,
                           metadata={'activation_key':key,'authority':'CAMPAIGN_CALIBRATION','basis':'MASTER FINAL states four major Grand Sales per year','calendar_status':'shared SV calendar fixed; exact Grand Sale dates not canonically assigned','no_lots_invented':True})
            auctions_created += 1

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('economic_substrate_activation_version','1')")
    return {
        'market_goods_configured': len(good_ids),
        'commercial_contexts_configured': contexts,
        'market_conditions_configured': market_rows,
        'explicit_institution_locations_applied': explicit_location_updates,
        'economic_aggregate_enterprises_created': enterprises_created,
        'production_sites_created': production_created,
        'aggregate_buildings_created': buildings_created,
        'brass_lantern_grand_sales_created': auctions_created,
    }


def activate_missing_merchant_anchors(conn: sqlite3.Connection) -> dict[str,int]:
    """Complete explicitly named Part Eleven institution identities omitted from the first structured seed.

    Identity is canonical/working from MASTER FINAL; headquarters remain unset unless the Bible actually fixes them.
    """
    specs = {
        'House Fenwick': ('merchant-noble house','MASTER FINAL Part 11: large inland merchant dynasty tied to caravans, grain, warehousing, road commerce and the Aldergate exchange.'),
        'House Merevale': ('merchant-noble house','MASTER FINAL Part 11: maritime and foreign-trade dynasty with ships and port factors.'),
        'House Serrick': ('merchant-noble house','MASTER FINAL Part 11: finance, urban property, wholesale credit and ordinary relationship lending.'),
        'House Orlan': ('merchant-noble house','MASTER FINAL Part 11: medicinal goods, refiners and cultivation-resource commerce.'),
        'Salt Road Consortium': ('company ecosystem','MASTER FINAL Part 11: association coordinating major coastal and cross-sea interests rather than one family.'),
    }
    created=0
    for name,(kind,basis) in specs.items():
        row=conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?",(name,)).fetchone()
        if row:
            iid=int(row[0])
        else:
            cur=conn.execute("INSERT INTO actors(name,actor_type,subtype,status,notes,is_demo) VALUES (?,'institution',?,'active',?,0)",(name,kind,basis))
            iid=int(cur.lastrowid); created += 1
        conn.execute("""INSERT OR IGNORE INTO institution_profiles(actor_id,institution_kind,governance_json,culture_json,pipeline_json,capacity_json,economic_json,reputation_json,succession_json,trajectory,last_review_day,notes)
                        VALUES (?,?, '{}','{}','{}','{}','{}','{}','{}','stable',0,?)""",(iid,kind,basis))
        conn.execute("""INSERT OR IGNORE INTO source_identity_map(source_namespace,source_key,entity_kind,entity_id,canon_status,provenance_json,source_payload_json,created_day,updated_day)
                        VALUES ('caerness_world_bible_master_final',?,'institution',?,'working',?,'{}',0,0)""",
                     ('institution:'+name.lower().replace(' ','-'),iid,json.dumps([basis])))
        conn.execute("""INSERT OR IGNORE INTO entity_resolution(entity_kind,entity_id,resolution_level,reason,review_cadence_days,next_review_day,last_changed_day,metadata_json)
                        VALUES ('institution',?,'STRUCTURAL','Named persistent World Bible institution anchor',90,90,0,?)""",
                     (iid,json.dumps({'authority':'WORLD_BIBLE','precise_headquarters':'UNSET_UNLESS_EXPLICIT'},sort_keys=True)))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('merchant_anchor_completion_version','1')")
    return {'named_merchant_institution_anchors_created':created}


def activate_elixir_substrate(conn: sqlite3.Connection) -> dict[str,int]:
    """Activate the source-supported elixir market/refining substrate without inventing batches or consumers."""
    refined=ensure_good(conn,'refined-elixir','Ordinary refined Vein-Root elixir','cultivation_resource',18.0,unit='batch unit',perishability=0.03,skill_intensity=0.90,luxury=0.65,
                        notes='v0.33 abstract price index; MASTER FINAL supports ordinary refined elixir as routine legitimate martial/medical commodity.')
    high=ensure_good(conn,'high-grade-elixir','High-grade Vein-Root elixir','cultivation_resource',48.0,unit='batch unit',perishability=0.02,skill_intensity=0.98,luxury=0.92,
                     notes='v0.33 abstract price index; MASTER FINAL supports scarce contracted/reserved high-grade elixir. Price is campaign calibration.')
    plans={
        'Toll’s Reach': ((62,74),(32,58)), 'Aldergate':((68,72),(36,62)), 'Cairnholt':((52,82),(24,72)),
        'Lysmere':((78,90),(38,74)), 'Saltmere':((70,76),(34,66)), 'Redford':((58,62),(18,42)),
    }
    markets=0
    for name,(ordinary,elite) in plans.items():
        lid=_location(conn,name)
        if lid is None: continue
        for gid,(sup,dem),grade in [(refined,ordinary,'refined'),(high,elite,'high_grade')]:
            set_market_condition(conn,lid,gid,supply=sup,demand=dem,transport_pressure=6,risk_pressure=5,tax_pressure=5,cadence_days=30,
                metadata={'authority':'CAMPAIGN_CALIBRATION','basis':'MASTER FINAL elixir economy and commercial geography','grade':grade,'numeric_status':'relative simulation index'})
            markets += 1

    suppliers=0
    # Lysmere explicitly contains refiners. This is an anonymous aggregate sector, not a named monopoly.
    lys=_location(conn,'Lysmere')
    if lys is not None:
        row=conn.execute("SELECT id FROM civilian_enterprises WHERE name='Lysmere — aggregate medical supply sector' ORDER BY id LIMIT 1").fetchone()
        if row:
            configure_elixir_supply(conn,int(row[0]),'refined',refinement_quality=72,sediment_risk=4,provenance_standard=70,
                source_basis='MASTER FINAL: Lysmere contains refiners and is the great concentration of cultivation medicine.',
                metadata={'authority':'SOURCE_ROLE_PLUS_CAMPAIGN_CALIBRATION','high_grade_not_assumed':True})
            suppliers += 1

    # House Orlan is explicitly a refiner/cultivation-resource merchant and explicitly deeply established in Aldergate.
    orlan=_institution(conn,'House Orlan'); ald=_location(conn,'Aldergate')
    if orlan is not None and ald is not None:
        row=conn.execute("SELECT id FROM civilian_enterprises WHERE institution_actor_id=? AND location_id=? ORDER BY id LIMIT 1",(orlan,ald)).fetchone()
        if row: eid=int(row[0])
        else:
            eid,_=_aggregate_enterprise(conn,'econ:orlan-aldergate','House Orlan — Aldergate aggregate refining/commercial footprint',ald,'refiner',institution_actor_id=orlan,
                 notes='MASTER FINAL: House Orlan handles medicinal goods, refiners and cultivation resources; Orlan is deeply established in Aldergate. This is an aggregate local footprint, not a claimed headquarters.')
        configure_elixir_supply(conn,eid,'refined',refinement_quality=76,sediment_risk=3,provenance_standard=78,
            source_basis='MASTER FINAL: House Orlan medicinal goods/refiners/cultivation-resource commerce; deep Aldergate establishment.',
            metadata={'authority':'SOURCE_ROLE_PLUS_CAMPAIGN_CALIBRATION','principal_seat':'UNRESOLVED','high_grade_not_assumed':True})
        suppliers += 1
    out=initialize_cultivation_physiology(conn)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('elixir_substrate_activation_version','1')")
    return {'elixir_market_conditions_configured':markets,'elixir_supply_profiles_configured':suppliers,**out}



def _person(conn: sqlite3.Connection, name: str) -> int | None:
    row = conn.execute("SELECT id FROM actors WHERE actor_type='character' AND name=?", (name,)).fetchone()
    return int(row[0]) if row else None


def activate_current_ecology(conn: sqlite3.Connection) -> dict[str, int]:
    """Activate only qualitatively established current ecology.

    Numeric values are coarse campaign calibration bands required by the legacy resolver; they are
    not canonical measurements and do not create seasonal timers the World Bible leaves qualitative.
    """
    specs = {
        'Hearthlands': (50,55,50,70,40,120,'broad Hearth baseline'),
        'Central Hearth': (55,60,55,80,40,150,'richer and broader central Hearth baseline'),
        'Eastern Hearth': (35,45,40,60,35,90,'thinner and patchier on average east of Ember Range'),
        'Fellmarch': (45,45,45,60,45,90,'mixed Fellmarch baseline'),
        'Ashgrave': (25,30,30,40,25,60,'damaged ecological/infrastructural region; not magical corruption'),
        'The Spine': (35,55,40,45,65,70,'concentrated and variable mountain current'),
        'White Laurel Heights': (80,75,55,35,85,50,'rich mountain ground with limited best-capacity portions'),
        'Stillwater': (60,90,65,45,55,60,'old stable ancestral ground'),
        'Bell Hollow': (65,70,65,90,55,140,'broad moderate-to-rich basin supporting many disciples'),
        'Stonepool': (75,65,55,30,85,35,'small dense ancestral ground with restricted high-value access'),
        'Brackwater Springs': (60,60,60,55,65,60,'several useful concentrations across the district'),
        'Deepwell Basin': (65,70,65,80,55,100,'broad reliable chartered/semi-neutral cultivation ground'),
        'Clearwell': (45,65,60,60,40,70,'weaker but dependable commercial cultivation ground'),
        'Stonewake Caverns': (65,45,45,30,80,35,'rich scattered chambers with variable recharge'),
        'Redroot Vale': (60,65,70,80,60,120,'major Root environment with mixed economic control'),
        'Ashgrave Wells': (30,30,35,50,35,50,'surviving and damaged remnants with fragmented claims'),
        'Silent Peak': (30,95,60,35,45,35,'thin but exceptionally coherent and stable current'),
    }
    configured = 0
    for name, (density, stability, replenishment, breadth, concentration, capacity, basis) in specs.items():
        lid = _location(conn, name)
        if lid is None:
            continue
        configure_environment(
            conn, lid,
            current_density=density, current_stability=stability, current_replenishment=replenishment,
            current_breadth=breadth, current_concentration=concentration, current_carrying_capacity=capacity,
            metadata={
                'activation_key': f'current-ecology:{name}', 'authority': 'CAMPAIGN_CALIBRATION',
                'basis': basis, 'source': 'Caerness World Bible MASTER FINAL',
                'no_hidden_cycle': True, 'numeric_values_are_inworld': False,
            },
        )
        configured += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_ecology_activation_version','1')")
    return {'current_ecology_profiles_configured': configured}


def activate_knowledge_assets(conn: sqlite3.Connection) -> dict[str, int]:
    # These aggregate records represent known institutional transmission corpora, not one invented
    # physical book. Named arts remain arts unless the Bible actually establishes a manual/text.
    institutions = [
        'House Halloway','House Corr','White Laurel Sect','Grey Bell Sect','Amberlight Sect',
        'Wrenfield Sect','Ragged Order','Grand Coven','House Renlow','Red Cedar Sect',
    ]
    created = custody = 0
    for name in institutions:
        iid = _institution(conn, name)
        if iid is None:
            continue
        key = f'knowledge:aggregate-canon:{name}'
        row = conn.execute("SELECT id FROM knowledge_assets WHERE json_extract(metadata_json,'$.activation_key')=?", (key,)).fetchone()
        if row:
            aid = int(row[0])
        else:
            aid = create_knowledge_asset(
                conn, f'{name} institutional transmission corpus (aggregate)', 'other', 'martial_instruction',
                institution_actor_id=iid, access_tier='member', completeness=1.0, teachability=0.65,
                preservation_mode='mixed', metadata={
                    'activation_key': key, 'authority': 'STRUCTURAL_AGGREGATE',
                    'basis': 'MASTER FINAL establishes a continuing martial inheritance/transmission canon',
                    'not_a_claim_of': 'one physical manual, universal member access, complete mastery, or a newly named text',
                },
            )
            created += 1
        if not conn.execute("SELECT 1 FROM knowledge_custody WHERE asset_id=? AND institution_actor_id=? AND status='active'", (aid, iid)).fetchone():
            add_knowledge_custody(conn, aid, 'archive', institution_actor_id=iid, notes='Aggregate institutional custody; exact copy/keeper distribution remains unresolved.')
            custody += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('knowledge_activation_version','1')")
    return {'knowledge_assets_created': created, 'knowledge_custody_created': custody}


def activate_polities(conn: sqlite3.Connection) -> dict[str, int]:
    specs = [
        ('Underheaven Empire','Underheaven','imperial state','Emperor Osric Varen','designated'),
        ('Dunmoor','Dunmoor','landed warrior monarchy','King Nicholas Ternwell','hereditary'),
        ('Windmere','Windmere','charter monarchy','Queen Maren Norwyn','hereditary'),
        ('Greywood','Greywood','institutional monarchy',None,'hereditary'),
        ('Sunreach Confederacy','Sunreach','confederated league',None,'custom'),
        ('Thornward','Thornward','elective ward-kingdom','King Corwin Hartfell','elective'),
        ('Stormhollow','Stormhollow','hereditary highland monarchy','King Roric Dunross','hereditary'),
    ]
    configured = controls = 0
    for inst_name, state_name, kind, ruler_name, method in specs:
        iid = _institution(conn, inst_name)
        if iid is None:
            continue
        ruler = _person(conn, ruler_name) if ruler_name else None
        # Capture current state-tagged places before set_territorial_control rewrites political_owner
        # to the polity actor's display name (notably Underheaven -> Underheaven Empire).
        locs = [int(r[0]) for r in conn.execute("SELECT id FROM locations WHERE political_owner=?", (state_name,)).fetchall()]
        pid = configure_polity(
            conn, iid, polity_kind=kind, ruler_actor_id=ruler, succession_method=method,
            legitimacy=50, stability=50, administrative_capacity=50, military_capacity=50, treasury_pressure=0,
            metadata={
                'authority':'WORLD_BIBLE_STRUCTURE_PLUS_CAMPAIGN_CALIBRATION',
                'basis':f'MASTER FINAL political form for {state_name}',
                'neutral_numeric_start':True,
                'ruler_omission_is_authoritative_open': inst_name in {'Greywood','Sunreach Confederacy'},
            },
        )
        configured += 1
        for lid in locs:
            set_territorial_control(
                conn, pid, lid, control_kind='direct', legitimacy=50, integration=50,
                notes='Imported from current seed state/polity containment; neutral numeric calibration.',
                reason='Current-canon territorial containment activated.',
            )
            controls += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('polity_activation_version','1')")
    return {'polities_configured': configured, 'territorial_controls_configured': controls}


def activate_religion_and_culture(conn: sqlite3.Connection) -> dict[str, int]:
    religious = 0
    for inst_name, tradition, authority, capacity in [
        ('Grand Coven','hollow_faith',85,75),
        ('Order of Marek','dunmoor_pantheon',60,55),
        ('Order of the Pilgrim Shield','witness',55,45),
        ('Underheaven Empire','imperial_observance',80,70),
    ]:
        iid = _institution(conn, inst_name)
        if iid is None:
            continue
        configure_religious_institution(
            conn, iid, tradition, authority=authority, ritual_capacity=capacity, treasury=0,
            metadata={
                'authority':'WORLD_BIBLE_STRUCTURE_PLUS_CAMPAIGN_CALIBRATION',
                'basis':'MASTER FINAL establishes religious/institutional role',
                'no_calendar_inferred':True,
                'treasury_zero_means':'unquantified religious treasury; no patronage spending is seeded',
            },
        )
        religious += 1

    cultural_profiles = 0
    brass = _institution(conn, 'Brass Lantern House')
    if brass is not None:
        configure_cultural_institution(
            conn, brass, 'auction_provenance_and_collecting', prestige=75, resources=50, public_reach=70, continuity=70,
            metadata={
                'authority':'WORLD_BIBLE_STRUCTURE_PLUS_CAMPAIGN_CALIBRATION',
                'basis':'MASTER FINAL establishes Brass Lantern as premier auction/cultural-market institution',
                'no_program_calendar_inferred':True,
            },
        )
        cultural_profiles += 1

    objects_created = 0
    for title, kind, creator_name, significance in [
        ('Arrival at Amber Court','painting','Liora Kelso','valuable'),
        ('Mercy at Caelshore','painting','Aurelia Morn','historical'),
        ('Glass Map of Saltmere','sculpture','Corvin Latch','historical'),
    ]:
        key=f'culture:object:{title}'
        if conn.execute("SELECT 1 FROM cultural_objects WHERE json_extract(metadata_json,'$.activation_key')=?",(key,)).fetchone():
            continue
        creator=_person(conn,creator_name)
        create_cultural_object(
            conn,title,kind,creator_actor_id=creator,quality=50,market_value=0,significance=significance,
            metadata={
                'activation_key':key,'authority':'WORLD_BIBLE',
                'basis':'MASTER FINAL named cultural exemplar',
                'current_owner_location_value_unresolved':True,
                'quality_value_is_neutral_runtime_placeholder':True,
            },
        )
        objects_created += 1

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('religion_culture_activation_version','1')")
    return {'religious_institutions_configured': religious, 'cultural_profiles_configured': cultural_profiles, 'cultural_objects_created': objects_created}


def activate_information_channels(conn: sqlite3.Connection) -> dict[str, int]:
    # Aggregate channel classes established by Part Twenty-Three; these are not invented newspaper titles.
    specs = [
        ('Hearth commercial-sheet circulation (aggregate)','commercial_sheet',0.8,0.78,0.15,1,
         ['Toll’s Reach','Aldergate','Cairnholt','Waymeet','Saltmere']),
        ('Long Road oral circulation (aggregate)','oral_network',1.0,0.55,0.20,1,
         ['Waymeet','Toll’s Reach','Cairnholt','Stonecross','Redford','Blackfen']),
        ('Concord correspondence network (aggregate)','institutional_correspondence',0.75,0.88,0.55,0,
         ['Cairnholt','Highford','Stonecross','Rivermoor']),
        ('Port and maritime correspondence (aggregate)','merchant_correspondence',0.7,0.82,0.35,0,
         ['Toll’s Reach','Saltmere','Stormwatch','Silvercove']),
    ]
    channels = links = 0
    for name, kind, speed, fidelity, secrecy, public, locations in specs:
        row=conn.execute("SELECT id FROM information_channels WHERE name=?",(name,)).fetchone()
        if row:
            cid=int(row[0])
        else:
            cur=conn.execute(
                """INSERT INTO information_channels(name,channel_kind,speed_multiplier,fidelity,secrecy,public_access,notes,is_demo)
                   VALUES (?,?,?,?,?,?,?,0)""",
                (name,kind,speed,fidelity,secrecy,public,
                 'STRUCTURAL_AGGREGATE from MASTER FINAL Part 23; channel class/network, not a uniquely named publication.'),
            )
            cid=int(cur.lastrowid); channels += 1
        for loc_name in locations:
            lid=_location(conn,loc_name)
            if lid is None: continue
            before=conn.total_changes
            conn.execute("INSERT OR IGNORE INTO channel_locations(channel_id,location_id,strength) VALUES (?,?,?)",(cid,lid,0.75))
            if conn.total_changes>before: links += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('information_channel_activation_version','1')")
    return {'information_channels_created':channels,'information_channel_location_links_created':links}


def activate_military_logistics(conn: sqlite3.Connection) -> dict[str,int]:
    from .war import configure_military_logistics_profile
    day=int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    source_names={'Underheaven Empire':'Crownhold','Dunmoor':None,'Windmere':None,'Greywood':None,'Sunreach Confederacy':None,'Thornward':None,'Stormhollow':None}
    count=0
    for row in conn.execute("SELECT p.id,a.name,p.military_capacity,p.administrative_capacity FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id WHERE p.status!='dissolved'").fetchall():
        name=str(row['name']); source=_location(conn,source_names.get(name)) if source_names.get(name) else None
        mil=float(row['military_capacity']); admin=float(row['administrative_capacity'])
        configure_military_logistics_profile(conn,int(row['id']),source_location_id=source,food_fodder_capacity=(mil+admin)/2,medical_capacity=45+mil*0.1,equipment_capacity=45+mil*0.1,elixir_reserve_capacity=25,transport_capacity=(mil+admin)/2,readiness=mil,metadata={'authority':'WORLD_BIBLE_STRUCTURE_PLUS_CAMPAIGN_CALIBRATION','basis':'MASTER FINAL establishes every polity military; numerical capacities are neutral campaign calibration','quiet_opening_does_not_imply_mobilization':True})
        count+=1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('military_logistics_activation_version','1')")
    return {'military_logistics_profiles_configured':count}


def activate_integration_opening_substrate(conn: sqlite3.Connection) -> dict[str,int]:
    """Populate shallow ordinary-world health/agriculture/law capacity without inventing named people.

    These rows are structural campaign substrate. Named physicians, farmers, judges and clerks remain
    latent until they become causally important and crystallize through the resolution layer.
    """
    from .health import create_care_site
    from .agriculture import create_field
    from .law import create_jurisdiction, add_rule, create_office

    day=int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    out={'opening_health_sites_created':0,'opening_agriculture_fields_created':0,
         'opening_law_jurisdictions_created':0,'opening_law_offices_created':0,'opening_law_rules_created':0}

    # Health: one structural ordinary-care network per economically active hub with health demand.
    # Capacity represents latent ordinary providers, not invented named doctors.
    health_rows=conn.execute("""SELECT c.location_id,l.name,c.health_demand
                                FROM location_commercial_context c JOIN locations l ON l.id=c.location_id
                                WHERE c.health_demand>0 ORDER BY c.health_demand DESC,c.location_id""").fetchall()
    for r in health_rows:
        lid=int(r['location_id']); key=f"opening:care:{lid}"
        if conn.execute("SELECT 1 FROM health_care_sites WHERE site_key=?",(key,)).fetchone():
            continue
        demand=float(r['health_demand']); quality=max(42.0,min(72.0,42.0+demand*.22)); capacity=max(1.0,min(5.0,1.0+demand/35.0))
        enterprise=conn.execute("""SELECT e.id FROM civilian_enterprises e
                                   WHERE e.location_id=? AND e.status IN ('active','strained')
                                   ORDER BY CASE WHEN lower(e.enterprise_kind) LIKE '%medicine%' THEN 0 ELSE 1 END,e.id LIMIT 1""",(lid,)).fetchone()
        create_care_site(conn,key,f"[STRUCTURAL] {r['name']} ordinary care network",location_id=lid,
                         enterprise_id=int(enterprise[0]) if enterprise else None,quality=quality,capacity_per_day=capacity,
                         beds=max(1,int(round(capacity*2))),metadata={
                             'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                             'not_named_canon_provider':True,
                             'aggregate_provider_domains':{
                                 'medicine':{'competence':max(48.0,min(68.0,quality)),'capacity_per_day':capacity},
                                 'surgery':{'competence':max(44.0,min(62.0,quality-4)),'capacity_per_day':max(.5,capacity*.35)},
                             },
                             'basis':'ordinary medical capacity implied by populated commercial hubs; named providers remain latent',
                         })
        out['opening_health_sites_created']+=1

    # Agriculture: food markets need a physical local/regional harvest substrate. The anonymous
    # enterprise/field is aggregate hinterland capacity, not a claim about a named farm or owner.
    grain=conn.execute("SELECT id FROM market_goods WHERE good_key='ordinary-grain'").fetchone()
    if grain:
        gid=int(grain[0])
        food_locs=conn.execute("""SELECT DISTINCT mc.location_id,l.name
                                  FROM market_conditions mc JOIN locations l ON l.id=mc.location_id
                                  WHERE mc.good_id=? ORDER BY mc.location_id""",(gid,)).fetchall()
        for r in food_locs:
            lid=int(r['location_id']); fkey=f"opening:grain:{lid}"
            if conn.execute("SELECT 1 FROM agriculture_fields WHERE field_key=?",(fkey,)).fetchone():
                continue
            erow=conn.execute("""SELECT id FROM civilian_enterprises WHERE location_id=?
                                AND json_extract(metadata_json,'$.activation_key')=? LIMIT 1""",(lid,f"opening-grain-hinterland:{lid}")).fetchone()
            if erow: eid=int(erow[0])
            else:
                eid=create_enterprise(conn,f"[STRUCTURAL] {r['name']} grain hinterland",'other',location_id=lid,
                                      capital=35,cash=12,debt=0,reputation=45,admin_quality=45,labor_capacity=65,risk_tolerance=35,
                                      metadata={'activation_key':f'opening-grain-hinterland:{lid}','authority':'CAMPAIGN_CALIBRATION',
                                                'opening_structural_substrate':True,'not_named_canon_enterprise':True,
                                                'meaning':'aggregate farms supplying the local/regional grain market'})
            create_field(conn,fkey,f"[STRUCTURAL] {r['name']} grain fields",enterprise_id=eid,location_id=lid,crop_good_id=gid,
                         hectares=24,base_yield_per_hectare=2.2,soil_quality=65,labor_capacity=68,
                         harvest_day_of_year=270,metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                                          'not_named_canon_farm':True,'aggregate_hinterland':True})
            out['opening_agriculture_fields_created']+=1

    # Law: every active polity receives a structural ordinary jurisdiction and docket. This does
    # not invent a named judge, specific statute book or disputed constitutional detail.
    polities=conn.execute("""SELECT p.*,a.name AS polity_name,a.current_location_id AS actor_location
                             FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id
                             WHERE p.status IN ('active','regency','succession_crisis','fragmenting') ORDER BY p.id""").fetchall()
    for pty in polities:
        pid=int(pty['id']); jkey=f"opening:polity-law:{pid}"
        jr=conn.execute("SELECT id FROM law_jurisdictions WHERE jurisdiction_key=?",(jkey,)).fetchone()
        if jr: jid=int(jr[0])
        else:
            jid=create_jurisdiction(conn,jkey,f"[STRUCTURAL] {pty['polity_name']} ordinary jurisdiction",'other',polity_id=pid,
                                    priority=45,metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                                          'not_named_canon_court':True,'constitutional_detail_protected':True})
            out['opening_law_jurisdictions_created']+=1
        for matter,threshold,remedy in (('contract',55,'damages'),('property',58,'order'),('commercial',52,'restitution'),('criminal',62,'fine')):
            rkey=f"opening:{pid}:{matter}"
            if not conn.execute("SELECT 1 FROM law_rules WHERE jurisdiction_id=? AND rule_key=?",(jid,rkey)).fetchone():
                add_rule(conn,jid,rkey,f"[STRUCTURAL] ordinary {matter} rule",matter,evidence_threshold=threshold,default_remedy=remedy,
                         metadata={'authority':'CAMPAIGN_CALIBRATION','ordinary_rule_family':True,'not_verbatim_canon_statute':True})
                out['opening_law_rules_created']+=1
        okey=f"opening:ordinary-court:{pid}"
        if not conn.execute("SELECT 1 FROM law_offices WHERE office_key=?",(okey,)).fetchone():
            loc=int(pty['actor_location']) if pty['actor_location'] is not None else None
            create_office(conn,okey,f"[STRUCTURAL] {pty['polity_name']} ordinary court",jid,location_id=loc,
                          institution_actor_id=int(pty['institution_actor_id']),capacity=max(35,float(pty['administrative_capacity'])),
                          integrity=65,corruption_pressure=15,metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                                                       'presiding_person_remains_latent':True})
            out['opening_law_offices_created']+=1
    return out


def activate_ordinary_economic_state_substrate(conn: sqlite3.Connection) -> dict[str, int]:
    """Seed the minimum ordinary MERCHANT/CRAFT/GROWTH substrate required by an unattended world.

    This deliberately uses existing named house principals only where the current seed already supplies
    them. Workshop labor remains structural through the production site's aggregate skilled-labor value;
    no named craftsperson is invented. Physical opening stock is transferred or materialized from an
    aggregate market with corresponding market-supply/cash conservation.
    """
    from .merchant import add_enterprise_staff, record_market_observation, apply_supply_shock
    from .craft import create_recipe, add_recipe_input, add_recipe_facility_requirement, add_facility, bind_recipe_to_site, create_production_order
    from .growth import configure_public_treasury

    day=int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    out={
        'opening_merchant_staff_configured':0,'opening_merchant_observations_created':0,
        'opening_physical_stock_bridges_created':0,'opening_craft_recipes_created':0,
        'opening_craft_facilities_created':0,'opening_craft_orders_created':0,
        'opening_public_treasuries_created':0,
    }

    # Merchant houses with explicit current-seed members receive authority through those existing people.
    for house in ('House Selwick','House Morrick','House Dovell'):
        inst=conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?",(house,)).fetchone()
        if not inst: continue
        ent=conn.execute("""SELECT id,location_id FROM civilian_enterprises WHERE institution_actor_id=?
                            AND json_extract(metadata_json,'$.activation_key')='current-canon-aggregate-arm' ORDER BY id LIMIT 1""",(int(inst[0]),)).fetchone()
        member=conn.execute("""SELECT member_actor_id FROM institution_memberships WHERE institution_actor_id=? AND status='active'
                               ORDER BY member_actor_id LIMIT 1""",(int(inst[0]),)).fetchone()
        if not ent or not member: continue
        add_enterprise_staff(conn,int(ent['id']),int(member[0]),role='house_principal',authority=72,specialty='commerce',
                             metadata={'authority':'WORLD_BIBLE_ROLE_PLUS_CAMPAIGN_CALIBRATION',
                                       'basis':'existing named active member authorizes the house aggregate commercial arm',
                                       'not_claim':'exclusive factor or exact historical office'})
        # Material commercial authority is a real reason for strategic review cadence; this is not camera privilege.
        conn.execute("""UPDATE simulation_profiles SET tier='STRATEGIC',cadence_days=MIN(cadence_days,30),
                      next_review_day=MIN(next_review_day,?) WHERE actor_id=?""",(day+30,int(member[0])))
        out['opening_merchant_staff_configured']+=1
        if ent['location_id'] is not None:
            lid=int(ent['location_id'])
            for mr in conn.execute("SELECT good_id FROM market_conditions WHERE location_id=? ORDER BY good_id",(lid,)).fetchall():
                gid=int(mr[0])
                if conn.execute("""SELECT 1 FROM merchant_market_observations WHERE enterprise_id=? AND observer_actor_id=?
                                  AND location_id=? AND good_id=? AND source_kind='opening_local_market_book' LIMIT 1""",
                                (int(ent['id']),int(member[0]),lid,gid)).fetchone():
                    continue
                record_market_observation(conn,int(ent['id']),lid,gid,observer_actor_id=int(member[0]),observed_day=day,received_day=day,
                                          source_kind='opening_local_market_book',reliability=.9,
                                          metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                                    'basis':'principal is physically based at the enterprise local market'})
                out['opening_merchant_observations_created']+=1

    # Move already-existing aggregate opening inventories into the physical-stock owner where a
    # merchant-facing lot is useful. This is a transfer, not duplication: legacy inventory is zeroed.
    for site_name in ('Still Hand — aggregate commercial arm','House Dovell — aggregate commercial arm'):
        row=conn.execute("""SELECT ps.id AS site_id,ps.inventory,ps.good_id,e.id AS enterprise_id,e.location_id
                            FROM production_sites ps JOIN civilian_enterprises e ON e.id=ps.enterprise_id
                            WHERE e.name=? AND ps.active=1 ORDER BY ps.id LIMIT 1""",(site_name,)).fetchone()
        if not row or row['location_id'] is None or float(row['inventory'])<=1e-9: continue
        marker=f"opening_stock_bridge_site_{int(row['site_id'])}"
        if conn.execute("SELECT 1 FROM engine_meta WHERE key=?",(marker,)).fetchone(): continue
        qty=float(row['inventory'])
        conn.execute("""INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json)
                        VALUES (?,?,?,?,?,?) ON CONFLICT(enterprise_id,location_id,good_id) DO UPDATE SET
                        quantity=commercial_stock.quantity+excluded.quantity,updated_day=excluded.updated_day""",
                     (int(row['enterprise_id']),int(row['location_id']),int(row['good_id']),qty,day,
                      json.dumps({'authority':'MIGRATED_OPENING_STATE','source':'legacy_production_site_inventory',
                                  'opening_resolution_bridge':True,'production_site_id':int(row['site_id'])},sort_keys=True)))
        conn.execute("UPDATE production_sites SET inventory=0 WHERE id=?",(int(row['site_id']),))
        conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?)",(marker,'1'))
        out['opening_physical_stock_bridges_created']+=1

    # One explicit ordinary tracked workshop: Dovell's already-established naval-supply activity.
    # It uses structural labor (production_sites.skilled_labor) until a worker becomes important enough to crystallize.
    site=conn.execute("""SELECT ps.*,e.location_id,e.cash,e.id AS eid FROM production_sites ps
                         JOIN civilian_enterprises e ON e.id=ps.enterprise_id
                         WHERE e.name='House Dovell — aggregate commercial arm' AND ps.active=1 ORDER BY ps.id LIMIT 1""").fetchone()
    if site and site['location_id'] is not None:
        naval=conn.execute("SELECT id FROM market_goods WHERE good_key='naval-supplies'").fetchone()
        timber=conn.execute("SELECT id FROM market_goods WHERE good_key='ordinary-timber'").fetchone()
        metal=conn.execute("SELECT id FROM market_goods WHERE good_key='metalwork'").fetchone()
        cloth=conn.execute("SELECT id FROM market_goods WHERE good_key='ordinary-cloth'").fetchone()
        if naval and timber and metal and cloth:
            existed=conn.execute("SELECT id FROM craft_recipes WHERE recipe_key='opening:dovell-naval-supplies'").fetchone()
            rid=create_recipe(conn,'opening:dovell-naval-supplies','Dovell ordinary naval-supply batch',int(naval[0]),
                              output_quantity=1,base_duration_days=2,skill_domain='craft',min_skill=45,
                              metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                        'basis':'Dovell shipbuilding/naval-supply role; ratios are coarse runtime calibration'})
            if not existed: out['opening_craft_recipes_created']+=1
            add_recipe_input(conn,rid,int(timber[0]),group_key='timber',units_per_batch=1.0)
            add_recipe_input(conn,rid,int(metal[0]),group_key='metal fittings',units_per_batch=.25)
            add_recipe_input(conn,rid,int(cloth[0]),group_key='cloth/rigging',units_per_batch=.25)
            add_recipe_facility_requirement(conn,rid,'shipyard_workshop',minimum_capacity=1,minimum_condition=40)
            fac=conn.execute("""SELECT id FROM craft_facilities WHERE enterprise_id=? AND location_id=? AND facility_kind='shipyard_workshop'
                                AND json_extract(metadata_json,'$.activation_key')='opening:dovell-shipyard' LIMIT 1""",
                             (int(site['eid']),int(site['location_id']))).fetchone()
            if not fac:
                add_facility(conn,int(site['eid']),int(site['location_id']),'shipyard_workshop','[STRUCTURAL] Dovell shipyard workshop',
                             capacity=1.5,condition=72,metadata={'activation_key':'opening:dovell-shipyard','authority':'CAMPAIGN_CALIBRATION',
                                                               'opening_structural_substrate':True,'named_workers_remain_latent':True})
                out['opening_craft_facilities_created']+=1
            bind_recipe_to_site(conn,int(site['id']),rid,is_default=True)

            # Materialize a small opening working lot from the already-existing aggregate Saltmere market.
            # The tracked enterprise pays cash and aggregate market supply falls by the same physical quantity.
            marker='opening_dovell_craft_inputs_seeded'
            if not conn.execute("SELECT 1 FROM engine_meta WHERE key=?",(marker,)).fetchone():
                needs=((int(timber[0]),3.0),(int(metal[0]),.75),(int(cloth[0]),.75))
                priced=[]; total=0.0
                for gid,qty in needs:
                    mc=conn.execute("SELECT current_price,supply FROM market_conditions WHERE location_id=? AND good_id=?",
                                    (int(site['location_id']),gid)).fetchone()
                    if not mc or float(mc['supply'])+1e-9<qty:
                        priced=[]; break
                    cost=qty*float(mc['current_price']); priced.append((gid,qty,cost)); total+=cost
                cash=float(conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?",(int(site['eid']),)).fetchone()[0])
                if priced and cash+1e-9>=total:
                    for gid,qty,cost in priced:
                        apply_supply_shock(conn,int(site['location_id']),gid,-qty,source='opening_tracked_working_inventory_bridge')
                        conn.execute("""INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json)
                                        VALUES (?,?,?,?,?,?) ON CONFLICT(enterprise_id,location_id,good_id) DO UPDATE SET
                                        quantity=commercial_stock.quantity+excluded.quantity,updated_day=excluded.updated_day""",
                                     (int(site['eid']),int(site['location_id']),gid,qty,day,
                                      json.dumps({'authority':'CAMPAIGN_CALIBRATION','source':'aggregate_market_resolution_bridge',
                                                  'opening_working_inventory':True},sort_keys=True)))
                    conn.execute("UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?",(total,day,int(site['eid'])))
                    conn.execute("""INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,source_kind)
                                    VALUES (?,?,?,?,?,'opening_resolution_bridge')""",
                                 (int(site['eid']),day,'purchase',total,'Opening tracked working inventory purchased from aggregate Saltmere market'))
                    conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?)",(marker,'1'))
            if not conn.execute("""SELECT 1 FROM craft_production_orders WHERE production_site_id=?
                                  AND json_extract(metadata_json,'$.activation_key')='opening:dovell-order' LIMIT 1""",(int(site['id']),)).fetchone():
                create_production_order(conn,int(site['id']),3.0,recipe_id=rid,priority=55,due_day=day+45,
                                        metadata={'activation_key':'opening:dovell-order','authority':'CAMPAIGN_CALIBRATION',
                                                  'opening_structural_substrate':True})
                out['opening_craft_orders_created']+=1

    # Every active polity needs a public-finance owner even if it takes no discretionary action this year.
    for pty in conn.execute("SELECT id,administrative_capacity FROM political_polities WHERE status IN ('active','regency','succession_crisis','fragmenting') ORDER BY id").fetchall():
        pid=int(pty['id'])
        if conn.execute("SELECT 1 FROM regional_public_treasuries WHERE polity_id=?",(pid,)).fetchone(): continue
        admin=float(pty['administrative_capacity'])
        configure_public_treasury(conn,pid,cash=max(60.0,admin*1.5),debt=0,tax_rate=.04,toll_rate=.005,
                                  review_cadence_days=30,metadata={'authority':'CAMPAIGN_CALIBRATION','opening_structural_substrate':True,
                                                                  'cash_is_simulation_liquidity_not_canon_treasury_amount':True,
                                                                  'basis':'active polity requires a fiscal owner for ordinary unattended state capacity'})
        out['opening_public_treasuries_created']+=1

    if not conn.execute("SELECT 1 FROM engine_meta WHERE key='merchant_next_market_cycle_day'").fetchone():
        conn.execute("INSERT INTO engine_meta(key,value) VALUES ('merchant_next_market_cycle_day',?)",(str(day+1),))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('ordinary_economic_substrate_activation_version','1')")
    return out

def activate_post76_agency_conflict(conn: sqlite3.Connection) -> dict[str,Any]:
    """Activate only the schema-77..80 agency/conflict layers on an existing campaign.

    This is deliberately narrow so upgrading a mature save does not re-run older opening
    activators and fabricate present-day copies of historical setup events.
    """
    out={}
    from .organization_agency import activate_shared_organization_agency
    out.update(activate_shared_organization_agency(conn))
    from .polity_agency import activate_polity_agency
    out.update(activate_polity_agency(conn))
    from .conflict import activate_conflict_channels
    out.update(activate_conflict_channels(conn))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('orgagency_conflict_activation_version','1')")
    return out

def activate_post80_organization_lifecycle(conn: sqlite3.Connection) -> dict[str,Any]:
    """Activate only ORGLIFE-01 on an already-running schema-80 campaign.

    This intentionally projects current organization/polity state into the new lifecycle
    owner without backdating formation, split, merger, or dissolution events.
    """
    from .organization_lifecycle import activate_organization_lifecycle
    out = activate_organization_lifecycle(conn)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('orglife01_narrow_activation_version','1')")
    return out


# Steps whose content is Caerness-specific, keyed by step name -> the world-package `systems` switch that must be on.
# A step not listed here runs for every world.
STEP_SWITCH: dict[str, str] = {
    'activate_missing_merchant_anchors': 'merchant_houses',
    'activate_economic_substrate': 'caerness_trade',
    'activate_aggregate_trade': 'caerness_trade',
    'activate_elixir_substrate': 'elixir',
    'activate_religion_and_culture': 'caerness_religions',
    'seed_cultivation_from_current_source': 'cultivation',
    'seed_current_groundbinding': 'groundbinding',
    'activate_tournament_substrate': 'cultivation',
    'activate_spectacle_substrate': 'cultivation',
    'activate_underworld_substrate': 'caerness_underworld',
    'seed_all_settlements': 'caerness_underworld',
    'activate_hollow_substrate': 'hollow',
    'activate_information_channels': 'caerness_trade',
}


def activate_existing_loops(conn: sqlite3.Connection, package=None) -> dict[str,Any]:
    from .world_package import current_package
    package = package if package is not None else current_package(conn)
    out={}
    skipped: list[str] = []

    def step(name: str, fn):
        """Run a package-gated step; a disabled one is recorded in skipped_steps instead."""
        if not package.systems.get(STEP_SWITCH[name], False):
            skipped.append(name)
            return
        out.update(fn())

    from .opening_world_state import resolve_opening_institution_locations, resolve_opening_character_locations
    # Design figures (packages that carry them) are drawn once, before anything reads them.
    from .design import draw_all
    out.update(draw_all(conn))
    # The canon travel graph must exist before anything that routes people, goods, news or armies.
    from .route_network import ensure_canon_route_network
    out.update({k:v for k,v in ensure_canon_route_network(conn).items() if k!='routes01_missing_places'})
    out['opening_institution_locations_resolved']=resolve_opening_institution_locations(conn)
    out.update({f'opening_character_locations_{k}':v for k,v in resolve_opening_character_locations(conn).items()})
    step('activate_missing_merchant_anchors', lambda: activate_missing_merchant_anchors(conn))
    out['opening_institution_locations_post_anchors']=resolve_opening_institution_locations(conn)
    out.update(activate_explicit_teaching(conn))
    out.update({f'opening_character_locations_post_teaching_{k}':v for k,v in resolve_opening_character_locations(conn).items()})
    from .teaching_ecology import refresh_teacher_market
    out.update(refresh_teacher_market(conn))
    out.update(activate_institution_training_contexts(conn))
    out['structural_training_cohorts_created']=ensure_structural_training_cohorts(conn,0)
    out.update(activate_commercial_anchors(conn))
    step('activate_economic_substrate', lambda: activate_economic_substrate(conn))
    from .scale import activate_scale_authority
    out.update(activate_scale_authority(conn))
    from .background_population import activate_population_sources, activate_population_life_course
    out.update(activate_population_sources(conn))
    out.update(activate_population_life_course(conn))
    from .person_ecology import activate_background_people
    out.update(activate_background_people(conn))
    from .profession_runtime import activate_profession_runtime
    out.update(activate_profession_runtime(conn))
    from .opening_world_state import activate_institutional_authority
    out.update(activate_institutional_authority(conn))
    from .aggregate_trade import activate_aggregate_trade
    step('activate_aggregate_trade', lambda: activate_aggregate_trade(conn))
    step('activate_elixir_substrate', lambda: activate_elixir_substrate(conn))
    out.update(activate_current_ecology(conn))
    from .conflict_geometry import activate_conflict_geometry
    out.update(activate_conflict_geometry(conn))
    out.update(activate_knowledge_assets(conn))
    out.update(activate_polities(conn))
    out.update(activate_military_logistics(conn))
    out.update(activate_ordinary_economic_state_substrate(conn))
    step('activate_religion_and_culture', lambda: activate_religion_and_culture(conn))
    step('activate_information_channels', lambda: activate_information_channels(conn))
    step('seed_cultivation_from_current_source', lambda: seed_cultivation_from_current_source(conn))
    from .groundbinding import seed_current_groundbinding
    step('seed_current_groundbinding', lambda: seed_current_groundbinding(conn))
    from .tournaments import activate_tournament_substrate
    step('activate_tournament_substrate', lambda: activate_tournament_substrate(conn))
    from .spectacle import activate_spectacle_substrate
    step('activate_spectacle_substrate', lambda: activate_spectacle_substrate(conn))
    from .underworld_rebuild import enforce_rebuild_firewall
    out['v060_legacy_underworld_retired'] = enforce_rebuild_firewall(conn)
    from .underworld import activate_underworld_substrate
    # v0.60 keeps the old module only for generic law/evidence compatibility. Legacy named
    # underworld institutions are retired by the schema firewall and therefore do not reactivate.
    step('activate_underworld_substrate', lambda: activate_underworld_substrate(conn))
    from .underworld_ecology import seed_all_settlements
    # Canon-shaped underworld in every settlement (gap 4a); replaces the Aldergate-only procedural city.
    step('seed_all_settlements', lambda: seed_all_settlements(conn))
    out.update(activate_post76_agency_conflict(conn))
    out.update(activate_post80_organization_lifecycle(conn))
    from .hollow import activate_hollow_substrate
    step('activate_hollow_substrate', lambda: activate_hollow_substrate(conn))
    out.update(activate_integration_opening_substrate(conn))
    from .merchant_taxonomy import activate_merchant_taxonomy
    out.update(activate_merchant_taxonomy(conn))
    from .service_fulfillment import activate_structural_provider_contracts
    out.update(activate_structural_provider_contracts(conn))
    # Last, so the Hollow Mantle rule can see the heirs registered above.
    from .demographic_sex import resolve_missing_demographic_sex
    out.update({f'family02_sex_{k}': v for k, v in resolve_missing_demographic_sex(conn).items()})
    # Opening family life and relationships need resolved sex, locations, teaching and memberships.
    from .opening_family import resolve_opening_history
    out.update(resolve_opening_history(conn))
    # The outfits as people (Saint Jude): needs the seeded members, the background population and opening relationships.
    from .world_package import system_enabled
    from .world_package import package_pass
    with package_pass():  # the package's files do not change while the opening is built
        if system_enabled(conn, "outfits"):
            from .outfit_opening import build as build_outfits
            out.update({f'outfit_opening_{k}': v for k, v in build_outfits(conn).items()})
            from .opening_households import build as build_households
            out.update({f'opening_households_{k}': v for k, v in build_households(conn).items()})
            from .opening_businesses import build as build_businesses
            out.update({f'opening_businesses_{k}': v for k, v in build_businesses(conn).items()})
            from .outfit_past import build as build_past
            out.update({f'outfit_past_{k}': v for k, v in build_past(conn).items()})
            from .lived_past import build as build_lived
            out.update({f'lived_past_{k}': v for k, v in build_lived(conn).items()})
            from .opening_races import build as build_races
            out.update({f'opening_races_{k}': v for k, v in build_races(conn).items()})
            from .opening_ties import build as build_ties
            out.update({f'opening_ties_{k}': v for k, v in build_ties(conn).items()})
        from .opening_family import seed_lived_courtships
        out.update(seed_lived_courtships(conn))  # who is courting or engaged when play begins
        from .physique import seed_all
        out['physical_records'] = seed_all(conn)  # everybody alive has a body (none in a world without body norms)
    conn.execute(
        "INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('current_canon_activation_version',?)",
        (str(CURRENT_CANON_ACTIVATION_VERSION),),
    )
    if skipped:
        out['skipped_steps'] = skipped
    return out
```

## engine/tiers.py

```python
"""S1: who is rising, and the coarse clock for everyone who is not.

Background upkeep that only integrates elapsed time (careers, household stage and money, enterprise accounts, planned births,
courtship contacts) does not need to run for every person every day. A *quiet* person's rows are brought up to date every
BATCH_DAYS on the row's own stamp (the load spreads, and every scan already integrates `elapsed`, so no time is lost). A *rising*
person's rows stay on the daily clock.

Who is rising is read from live state, never from where anyone is or how far he is from the player: a daily-reviewed seat in an organisation, a
party to a venture, the owner of an enterprise, a candidate in an open race, an office holder, a person who owes or is owed on a
standing agreement, a person harmed in the last month, a person forced to a faster tier. Because it is derived at the moment a scan
runs, a man who gains any of these is on the daily clock the next time the scan runs: nobody has to call anything to promote him.

`CAERNESS_TIERS=off` makes everyone rising (the all-full-tier baseline used by the equivalence tests).
"""
from __future__ import annotations

import os
import sqlite3

BATCH_DAYS = 7
RECENT_HARM_DAYS = 30


def enabled(conn: sqlite3.Connection | None = None) -> bool:
    return os.environ.get("CAERNESS_TIERS", "on").strip().lower() not in ("off", "0", "false")


def _ids(conn: sqlite3.Connection, sql: str, *args) -> set[int]:
    try:
        return {int(r[0]) for r in conn.execute(sql, args).fetchall() if r[0] is not None}
    except sqlite3.OperationalError:  # a database made before the layer that owns the table
        return set()


def _compute(conn: sqlite3.Connection, day: int) -> frozenset[int]:
    out: set[int] = set()
    # An organisation seat alone is not a reason: its holder's own advancement (induction, promotion, a line, a challenge) runs on the
    # organisation's clocks, which S1 does not touch. What puts him here is the engine's own daily tier (a man whose level is reviewed daily)
    # and the held seats that are in play (a seat with nobody above it, or a vacancy-bound one).
    out |= _ids(conn, "SELECT actor_id FROM simulation_profiles WHERE cadence_days<=1")
    out |= _ids(conn, "SELECT actor_id FROM org_seats WHERE status='held'")
    out |= _ids(conn, "SELECT CAST(substr(party_ref,8) AS INTEGER) FROM venture_parties vp JOIN civilian_projects p ON p.id=vp.project_id "
                      "WHERE vp.party_ref LIKE 'person:%' AND p.status='active'")
    out |= _ids(conn, "SELECT owner_actor_id FROM civilian_enterprises WHERE status IN ('active','strained','insolvent') AND owner_actor_id IS NOT NULL")
    out |= _ids(conn, "SELECT actor_id FROM race_candidates rc JOIN races r ON r.id=rc.race_id WHERE r.status='open' AND rc.dropped_day IS NULL")
    out |= _ids(conn, "SELECT actor_id FROM office_terms WHERE end_day IS NULL")
    out |= _ids(conn, "SELECT CAST(substr(debtor_ref,8) AS INTEGER) FROM agreement_terms WHERE status IN ('active','breached') AND debtor_ref LIKE 'person:%' AND (missed_count>0 OR owed_usd>0)")
    out |= _ids(conn, "SELECT actor_id FROM harm_incidents WHERE day>=?", day - RECENT_HARM_DAYS)
    out |= _ids(conn, "SELECT actor_id FROM simulation_profiles WHERE forced_tier IS NOT NULL AND COALESCE(forced_until_day,0)>=?", day)
    return frozenset(out)


def rising_actor_ids(conn: sqlite3.Connection, day: int) -> frozenset[int]:
    """The people on the daily clock today. Computed once per simulated day inside a time skip."""
    from .world_package import pass_memo
    return pass_memo(conn, f"rising:{int(day)}", lambda: _compute(conn, int(day)))


def is_rising(conn: sqlite3.Connection, actor_id: int, day: int) -> bool:
    return (not enabled(conn)) or int(actor_id) in rising_actor_ids(conn, day)


def sql_ids(conn: sqlite3.Connection, day: int) -> str:
    """The rising ids as a SQL list literal, for `... OR actor_id IN (<list>)`. With tiers off the caller must not filter at all
    (see `batching(conn)`)."""
    ids = sorted(rising_actor_ids(conn, day))
    return ",".join(str(i) for i in ids) if ids else "NULL"


def batching(conn: sqlite3.Connection) -> bool:
    """True when quiet people's rows may wait for their batch day."""
    return enabled(conn)
```

## engine/crystallization.py

```python
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from .relationships import ensure_relationship
from .continuity import (
    add_cohort_member,
    add_historical_anchor,
    set_resolution,
    start_career,
    upsert_continuity_core,
)

DAY_PER_YEAR = 365
_ALLOWED_DEPTHS = {"shallow", "developed", "deep"}
_ALLOWED_BASIS = {"cohort", "institution", "event", "anchor", "record", "relationship", "canon", "latent_constraint"}


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _world_day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _rowdict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


def _latent(conn: sqlite3.Connection, latent_entity_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM latent_entities WHERE id=?", (latent_entity_id,)).fetchone()
    if not row:
        raise ValueError(f"Unknown latent entity #{latent_entity_id}")
    if row["status"] == "retired":
        raise ValueError("Latent entity pool is retired")
    return row


def _career_candidates(conn: sqlite3.Connection, constraints: dict[str, Any]) -> list[dict[str, Any]]:
    domain = constraints.get("career_domain") or constraints.get("domain")
    if domain:
        rows = conn.execute("SELECT * FROM career_tracks WHERE domain=? ORDER BY is_canon DESC,name", (domain,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM career_tracks ORDER BY is_canon DESC,name LIMIT 40").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["stage_model"] = _loads(item.pop("stage_model_json"), {})
        item["stages"] = [dict(x) for x in conn.execute(
            "SELECT id,stage_key,stage_name,sequence_index,description FROM career_stages WHERE track_id=? ORDER BY sequence_index,id",
            (row["id"],),
        ).fetchall()]
        result.append(item)
    return result


def _event_context(conn: sqlite3.Connection, location_id: int | None, earliest_day: int, latest_day: int) -> list[dict[str, Any]]:
    if location_id is None:
        return []
    rows = conn.execute(
        """SELECT id,day,event_type,title,summary,severity,location_id,source_actor_id
           FROM events WHERE location_id=? AND day BETWEEN ? AND ?
           ORDER BY day,id LIMIT 120""",
        (location_id, earliest_day, latest_day),
    ).fetchall()
    return [dict(r) for r in rows]


def _institution_context(conn: sqlite3.Connection, latent: sqlite3.Row) -> dict[str, Any] | None:
    iid = latent["institution_actor_id"]
    if iid is None:
        return None
    actor = conn.execute("SELECT id,name,subtype,home_location_id,current_location_id,status FROM actors WHERE id=?", (iid,)).fetchone()
    if not actor:
        return None
    result = dict(actor)
    profile = conn.execute("SELECT * FROM institution_profiles WHERE actor_id=?", (iid,)).fetchone()
    if profile:
        p = dict(profile)
        for key in ("governance_json", "culture_json", "pipeline_json", "capacity_json", "economic_json", "reputation_json", "succession_json"):
            p[key.removesuffix("_json")] = _loads(p.pop(key), {})
        result["profile"] = p
    else:
        result["profile"] = None
    return result


def _cohort_context(conn: sqlite3.Connection, cohort_id: int | None) -> dict[str, Any] | None:
    if cohort_id is None:
        return None
    row = conn.execute("SELECT * FROM cohorts WHERE id=?", (cohort_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["shared_context"] = _loads(result.pop("shared_context_json"), {})
    return result


def prepare_crystallization_context(
    conn: sqlite3.Connection,
    latent_entity_id: int,
    *,
    requested_depth: str = "shallow",
    trigger_kind: str = "engine",
    trigger_id: int | None = None,
) -> dict[str, Any]:
    """Build and persist a bounded historical context for one latent pool.

    This does not create a person. It freezes the constraints a proposal must obey,
    so later generation cannot opportunistically broaden the past to fit a scene.
    """
    if requested_depth not in _ALLOWED_DEPTHS:
        raise ValueError("Invalid crystallization depth")
    latent = _latent(conn, latent_entity_id)
    constraints = _loads(latent["constraints_json"], {})
    historical = _loads(latent["historical_context_json"], {})
    current_day = _world_day(conn)

    age_range = constraints.get("age_range") or [18, 85]
    try:
        min_age, max_age = int(age_range[0]), int(age_range[1])
    except Exception:
        min_age, max_age = 18, 85
    min_age = max(0, min_age)
    max_age = max(min_age, max_age)
    earliest_birth = current_day - max_age * DAY_PER_YEAR
    latest_birth = current_day - min_age * DAY_PER_YEAR

    location = None
    if latent["location_id"] is not None:
        location = _rowdict(conn.execute("SELECT * FROM locations WHERE id=?", (latent["location_id"],)).fetchone())

    context = {
        "context_version": 1,
        "prepared_day": current_day,
        "requested_depth": requested_depth,
        "latent": {
            "id": int(latent["id"]),
            "latent_kind": latent["latent_kind"],
            "archetype": latent["archetype"],
            "count_estimate": int(latent["count_estimate"]),
            "constraints": constraints,
            "historical_context": historical,
            "status": latent["status"],
        },
        "birth_window": {"earliest_day": earliest_birth, "latest_day": latest_birth, "age_range": [min_age, max_age]},
        "location": location,
        "institution": _institution_context(conn, latent),
        "cohort": _cohort_context(conn, latent["cohort_id"]),
        "career_tracks": _career_candidates(conn, constraints),
        "local_events": _event_context(conn, latent["location_id"], earliest_birth, current_day),
        "guardrails": {
            "identity_facing_history": True,
            "no_convenient_connections": True,
            "existing_references_require_basis": True,
            "campaign_scope_only": True,
            "max_anchor_counts": {"shallow": 4, "developed": 8, "deep": 14},
        },
    }
    cur = conn.execute(
        """INSERT INTO crystallization_runs(
               latent_entity_id,target_kind,requested_depth,trigger_kind,trigger_id,status,context_json,created_day
           ) VALUES (?,?,?,?,?,'prepared',?,?)""",
        (latent_entity_id, "actor", requested_depth, trigger_kind, trigger_id, _dumps(context), current_day),
    )
    context["run_id"] = int(cur.lastrowid)
    return context


def _ref_exists(conn: sqlite3.Connection, basis_kind: str, ref_id: int) -> bool:
    table = {
        "cohort": "cohorts",
        "institution": "actors",
        "event": "events",
        "anchor": "historical_anchors",
        "record": "documentary_records",
        "relationship": "relationships",
    }.get(basis_kind)
    if not table:
        return basis_kind in {"canon", "latent_constraint"}
    row = conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (ref_id,)).fetchone()
    if not row:
        return False
    if basis_kind == "institution":
        actor = conn.execute("SELECT actor_type FROM actors WHERE id=?", (ref_id,)).fetchone()
        return bool(actor and actor[0] == "institution")
    return True


def validate_crystallization_proposal(
    conn: sqlite3.Connection,
    run_id: int,
    proposal: dict[str, Any],
    *,
    strict: bool = True,
) -> dict[str, Any]:
    run = conn.execute("SELECT * FROM crystallization_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise ValueError(f"Unknown crystallization run #{run_id}")
    if run["status"] in {"applied", "cancelled"}:
        raise ValueError(f"Crystallization run is already {run['status']}")
    context = _loads(run["context_json"], {})
    errors: list[str] = []
    warnings: list[str] = []

    name = str(proposal.get("name") or "").strip()
    if not name:
        errors.append("proposal.name is required")
    elif conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
        errors.append(f"actor name already exists: {name}")

    if proposal.get("actor_type", "character") != "character":
        errors.append("historical person crystallization currently supports actor_type='character' only")

    birth_day = proposal.get("birth_day")
    window = context.get("birth_window", {})
    if birth_day is None:
        errors.append("proposal.birth_day is required")
    else:
        birth_day = int(birth_day)
        if not int(window.get("earliest_day", birth_day)) <= birth_day <= int(window.get("latest_day", birth_day)):
            errors.append("birth_day falls outside the latent pool age constraints")

    latent = context.get("latent", {})
    constraints = latent.get("constraints", {})
    expected_location = (context.get("location") or {}).get("id")
    home_location_id = proposal.get("home_location_id", expected_location)
    current_location_id = proposal.get("current_location_id", expected_location)
    if strict and expected_location is not None and home_location_id not in {None, expected_location}:
        warnings.append("home_location differs from latent pool location; requires explicit historical basis")
    for key, value in (("home_location_id", home_location_id), ("current_location_id", current_location_id)):
        if value is not None and not conn.execute("SELECT 1 FROM locations WHERE id=?", (int(value),)).fetchone():
            errors.append(f"{key} references unknown location #{value}")

    max_anchors = int(context.get("guardrails", {}).get("max_anchor_counts", {}).get(run["requested_depth"], 4))
    anchors = proposal.get("anchors") or []
    if len(anchors) > max_anchors:
        errors.append(f"too many anchors for {run['requested_depth']} crystallization: {len(anchors)} > {max_anchors}")

    previous_start: int | None = None
    for i, anchor in enumerate(anchors):
        if not str(anchor.get("anchor_type") or "").strip():
            errors.append(f"anchors[{i}].anchor_type is required")
        if not str(anchor.get("summary") or "").strip():
            errors.append(f"anchors[{i}].summary is required")
        start = anchor.get("start_day")
        if start is not None:
            start = int(start)
            if birth_day is not None and start < int(birth_day):
                errors.append(f"anchors[{i}] predates birth_day")
            if start > int(context.get("prepared_day", _world_day(conn))):
                errors.append(f"anchors[{i}] lies in the future")
            if previous_start is not None and start < previous_start:
                warnings.append("anchors are not chronological")
            previous_start = start
        end = anchor.get("end_day")
        if end is not None and start is not None and int(end) < int(start):
            errors.append(f"anchors[{i}].end_day precedes start_day")
        basis = anchor.get("basis") or []
        for j, item in enumerate(basis):
            kind = str(item.get("kind") or "")
            ref_id = item.get("id")
            if kind not in _ALLOWED_BASIS:
                errors.append(f"anchors[{i}].basis[{j}] has invalid kind {kind!r}")
                continue
            if kind not in {"canon", "latent_constraint"}:
                if ref_id is None or not _ref_exists(conn, kind, int(ref_id)):
                    errors.append(f"anchors[{i}].basis[{j}] references missing {kind} #{ref_id}")

    # Anti-convenience: strong existing-actor connections need explicit historical basis.
    connections = proposal.get("connections") or []
    for i, connection in enumerate(connections):
        actor_id = connection.get("actor_id")
        if actor_id is None or not conn.execute("SELECT 1 FROM actors WHERE id=?", (int(actor_id),)).fetchone():
            errors.append(f"connections[{i}] references unknown actor")
            continue
        basis = connection.get("basis") or []
        if not basis:
            errors.append(f"connections[{i}] has no historical basis; convenient retroactive connections are forbidden")
            continue
        valid_basis = False
        for item in basis:
            kind = str(item.get("kind") or "")
            ref_id = item.get("id")
            if kind in _ALLOWED_BASIS and (kind in {"canon", "latent_constraint"} or (ref_id is not None and _ref_exists(conn, kind, int(ref_id)))):
                valid_basis = True
        if not valid_basis:
            errors.append(f"connections[{i}] has no valid basis")

    career = proposal.get("career")
    if career:
        track_id = int(career.get("track_id", 0))
        track = conn.execute("SELECT * FROM career_tracks WHERE id=?", (track_id,)).fetchone()
        if not track:
            errors.append("career.track_id is unknown")
        else:
            expected_domain = constraints.get("career_domain") or constraints.get("domain")
            if strict and expected_domain and track["domain"] != expected_domain:
                errors.append(f"career domain {track['domain']} violates latent constraint {expected_domain}")
            stage_id = career.get("stage_id")
            if stage_id is not None and not conn.execute("SELECT 1 FROM career_stages WHERE id=? AND track_id=?", (int(stage_id), track_id)).fetchone():
                errors.append("career.stage_id does not belong to career.track_id")
            institution_actor_id = career.get("institution_actor_id")
            if institution_actor_id is not None:
                inst = conn.execute("SELECT actor_type FROM actors WHERE id=?", (int(institution_actor_id),)).fetchone()
                if not inst or inst[0] != "institution":
                    errors.append("career.institution_actor_id must reference an institution")

    continuity = proposal.get("continuity") or {}
    if not isinstance(continuity, dict):
        errors.append("proposal.continuity must be an object")

    result = {"valid": not errors, "errors": errors, "warnings": warnings, "checked_day": _world_day(conn), "strict": strict}
    conn.execute(
        "UPDATE crystallization_runs SET proposal_json=?,validation_json=?,status=? WHERE id=?",
        (_dumps(proposal), _dumps(result), "validated" if not errors else "rejected", run_id),
    )
    return result


def _add_lineage(conn: sqlite3.Connection, run_id: int, fact_kind: str, produced_kind: str, produced_id: int, *, ref_kind: str | None = None, ref_id: int | None = None, summary: str | None = None, day: int) -> None:
    conn.execute(
        """INSERT INTO crystallization_lineage(run_id,fact_kind,fact_ref_kind,fact_ref_id,produced_kind,produced_id,summary,created_day)
           VALUES (?,?,?,?,?,?,?,?)""",
        (run_id, fact_kind, ref_kind, ref_id, produced_kind, produced_id, summary, day),
    )


def apply_crystallization_proposal(conn: sqlite3.Connection, run_id: int) -> int:
    """Commit a previously validated person proposal as campaign history.

    Application is transactional under the caller's transaction. It never mutates setting canon.
    """
    run = conn.execute("SELECT * FROM crystallization_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise ValueError(f"Unknown crystallization run #{run_id}")
    if run["status"] != "validated":
        raise ValueError("Crystallization must validate successfully before application")
    proposal = _loads(run["proposal_json"], {})
    validation = _loads(run["validation_json"], {})
    if not validation.get("valid"):
        raise ValueError("Stored crystallization validation is not valid")
    latent = _latent(conn, int(run["latent_entity_id"]))
    day = _world_day(conn)

    location_id = proposal.get("current_location_id")
    if location_id is None:
        location_id = latent["location_id"]
    home_location_id = proposal.get("home_location_id")
    if home_location_id is None:
        home_location_id = latent["location_id"]

    cur = conn.execute(
        """INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo)
           VALUES (?,'character',?,?,?,?,?,0)""",
        (proposal["name"], proposal.get("subtype"), home_location_id, location_id, proposal.get("status", "active"), proposal.get("notes")),
    )
    actor_id = int(cur.lastrowid)

    core = dict(proposal.get("continuity") or {})
    core.setdefault("identity", {})
    core["identity"].setdefault("birth_day", int(proposal["birth_day"]))
    core["identity"].setdefault("crystallized_from_latent_id", int(latent["id"]))
    upsert_continuity_core(
        conn, "actor", actor_id, core,
        historical_depth=str(run["requested_depth"]), crystallized_day=day, source_kind="campaign",
        notes="Created by historical crystallization v0.9",
    )
    _add_lineage(conn, run_id, "latent_pool", "continuity_core", actor_id, ref_kind="latent_entity", ref_id=int(latent["id"]), summary="Identity crystallized from latent pool", day=day)

    birth_anchor = add_historical_anchor(
        conn, "actor", actor_id, "birth", f"Born: {proposal['name']}", start_day=int(proposal["birth_day"]),
        detail={"home_location_id": home_location_id}, source_kind="crystallization", canon_scope="campaign",
    )
    _add_lineage(conn, run_id, "birth", "historical_anchor", birth_anchor, summary="Birth anchor", day=day)

    for anchor in proposal.get("anchors") or []:
        detail = dict(anchor.get("detail") or {})
        detail["basis"] = anchor.get("basis") or []
        anchor_id = add_historical_anchor(
            conn, "actor", actor_id, str(anchor["anchor_type"]), str(anchor["summary"]),
            start_day=anchor.get("start_day"), end_day=anchor.get("end_day"), detail=detail,
            source_kind="crystallization", certainty=float(anchor.get("certainty", 1.0)), canon_scope="campaign",
        )
        for basis in anchor.get("basis") or []:
            _add_lineage(conn, run_id, "anchor_basis", "historical_anchor", anchor_id, ref_kind=basis.get("kind"), ref_id=basis.get("id"), summary=str(anchor["summary"]), day=day)

    cohort_id = latent["cohort_id"]
    if cohort_id is not None:
        add_cohort_member(conn, int(cohort_id), actor_id, role=proposal.get("cohort_role"), membership_status="former")
        _add_lineage(conn, run_id, "cohort", "actor", actor_id, ref_kind="cohort", ref_id=int(cohort_id), summary="Inherited latent cohort membership", day=day)

    career = proposal.get("career")
    if career:
        career_id = start_career(
            conn, actor_id, int(career["track_id"]), stage_id=career.get("stage_id"),
            institution_actor_id=career.get("institution_actor_id") or latent["institution_actor_id"],
            mentor_actor_id=career.get("mentor_actor_id"), started_day=career.get("started_day"), notes=career.get("notes"),
        )
        conn.execute(
            "UPDATE actor_careers SET status=?,experience_json=?,reputation_json=? WHERE id=?",
            (career.get("status", "active"), _dumps(career.get("experience")), _dumps(career.get("reputation")), career_id),
        )
        _add_lineage(conn, run_id, "career", "actor_career", career_id, ref_kind="career_track", ref_id=int(career["track_id"]), summary="Crystallized career", day=day)

    for connection in proposal.get("connections") or []:
        other = int(connection["actor_id"])
        stance = float(connection.get("stance", 0))
        trust = float(connection.get("trust", 0))
        obligation = float(connection.get("obligation", 0))
        rid = ensure_relationship(conn, actor_id, other, day)
        conn.execute(
            "UPDATE relationships SET stance=?,trust=?,obligation=?,updated_day=? WHERE id=?",
            (stance, trust, obligation, day, rid),
        )
        for basis in connection.get("basis") or []:
            _add_lineage(conn, run_id, "connection_basis", "relationship", int(conn.execute("SELECT id FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (actor_id, other)).fetchone()[0]), ref_kind=basis.get("kind"), ref_id=basis.get("id"), summary=connection.get("summary"), day=day)

    set_resolution(conn, "actor", actor_id, proposal.get("resolution_level", "TRACKED"), day=day, reason="historical crystallization", source_kind="crystallization", source_id=run_id)

    remaining = int(latent["count_estimate"]) - 1
    if remaining <= 0:
        conn.execute(
            """UPDATE latent_entities SET status='crystallized',crystallized_entity_kind='actor',crystallized_entity_id=?,updated_day=? WHERE id=?""",
            (actor_id, day, latent["id"]),
        )
    else:
        conn.execute(
            """UPDATE latent_entities SET count_estimate=?,status='partially_crystallized',crystallized_entity_kind='actor',crystallized_entity_id=?,updated_day=? WHERE id=?""",
            (remaining, actor_id, day, latent["id"]),
        )

    conn.execute(
        """UPDATE crystallization_runs SET status='applied',crystallized_entity_kind='actor',crystallized_entity_id=?,applied_day=?,applied_at=CURRENT_TIMESTAMP WHERE id=?""",
        (actor_id, day, run_id),
    )
    return actor_id


def crystallization_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM crystallization_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["context"] = _loads(result.pop("context_json"), {})
    result["proposal"] = _loads(result.pop("proposal_json"), None)
    result["validation"] = _loads(result.pop("validation_json"), {})
    result["lineage"] = [dict(x) for x in conn.execute("SELECT * FROM crystallization_lineage WHERE run_id=? ORDER BY id", (run_id,)).fetchall()]
    return result


def export_crystallization_packet(conn: sqlite3.Connection, run_id: int, path: str | None = None) -> str:
    run = crystallization_run(conn, run_id)
    if not run:
        raise ValueError(f"Unknown crystallization run #{run_id}")
    if run["status"] not in {"prepared", "rejected", "validated"}:
        raise ValueError(f"Cannot export run in status {run['status']}")
    packet = f"""# Caerness Historical Crystallization Request #{run_id}\n\nYou are proposing historical detail for an entity that already existed latently in the world.\nDo not change world truth. Do not create convenient connections to solve the current scene.\nUse only the supplied context as historical constraint. Return JSON only.\n\n## Context\n```json\n{json.dumps(run['context'], ensure_ascii=False, indent=2, sort_keys=True)}\n```\n\n## Required JSON shape\n```json\n{{\n  \"name\": \"Unique Name\",\n  \"actor_type\": \"character\",\n  \"subtype\": \"profession or social subtype\",\n  \"birth_day\": -19000,\n  \"home_location_id\": null,\n  \"current_location_id\": null,\n  \"continuity\": {{\n    \"identity\": {{}},\n    \"temperament\": {{}},\n    \"values\": [],\n    \"goals\": [],\n    \"relationships_summary\": []\n  }},\n  \"anchors\": [\n    {{\n      \"anchor_type\": \"apprenticeship\",\n      \"start_day\": -14000,\n      \"end_day\": -13000,\n      \"summary\": \"...\",\n      \"detail\": {{}},\n      \"certainty\": 1.0,\n      \"basis\": [{{\"kind\": \"cohort\", \"id\": 1}}]\n    }}\n  ],\n  \"career\": null,\n  \"connections\": [],\n  \"resolution_level\": \"TRACKED\"\n}}\n```\n\nRules:\n- History is identity-facing, not plot-facing.\n- Never invent an existing-actor connection without explicit basis.\n- Do not exceed the anchor limit in context.guardrails.\n- Do not contradict age, location, cohort, institution, career, or event constraints.\n- This creates campaign history only, never setting canon.\n"""
    if path is None:
        path = f"game/campaign_01/crystallization_{run_id}.md"
    from pathlib import Path
    out = Path(path)
    if not out.is_absolute():
        out = Path(__file__).resolve().parent.parent / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(packet, encoding="utf-8")
    return str(out)


def parse_crystallization_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        first = text.find("\n")
        last = text.rfind("```")
        if first >= 0 and last > first:
            text = text[first + 1:last].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Crystallization response must be one JSON object: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Crystallization response must be a JSON object")
    return data
```

## engine/decision_runtime.py

```python
from __future__ import annotations

import json
import math
import os
import random
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable

from .domain_actions import domain_action_options


@dataclass(frozen=True)
class DecisionCandidate:
    key: str
    provider_key: str
    action_kind: str
    utility: float
    rationale: str
    execution_kind: str  # domain_action | interaction | underworld_action | merchant_action | org_action | growth_action | war_action | political_action | hold
    target_actor_id: int | None = None
    interaction_type: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    information_basis: dict[str, Any] = field(default_factory=dict)
    claim_ids: tuple[int, ...] = ()
    evidence_ids: tuple[int, ...] = ()
    tags: tuple[str, ...] = ()
    estimated_cost: float = 0.0
    risk: float = 0.0


Provider = Callable[[sqlite3.Connection, int, str, int, dict[str, Any]], list[DecisionCandidate]]
_PROVIDERS: list[tuple[str, Provider]] = []


def register_provider(key: str, provider: Provider) -> None:
    global _PROVIDERS
    _PROVIDERS = [(k, p) for k, p in _PROVIDERS if k != key]
    _PROVIDERS.append((key, provider))


def clear_providers() -> None:
    _PROVIDERS.clear()


def _rng(conn: sqlite3.Connection, actor_id: int, day: int) -> random.Random:
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed * 1_000_003 + actor_id * 9_973 + day * 37_219 + 63 * 65_537)


def _ordinary_domain_provider(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    drives = envelope.get("drives") or {}
    out: list[DecisionCandidate] = []
    for opt in domain_action_options(conn, actor_id, tier, day, context=envelope, drives=drives):
        out.append(DecisionCandidate(
            key=f"ordinary:{opt.kind}:{opt.target_actor_id or 0}:{json.dumps(opt.payload or {}, sort_keys=True, default=str)}",
            provider_key="ordinary_domain",
            action_kind=opt.kind,
            utility=float(opt.score),
            rationale=opt.rationale,
            execution_kind="domain_action",
            target_actor_id=opt.target_actor_id,
            interaction_type=opt.interaction_type,
            payload={"mode": opt.mode, "payload": opt.payload or {}},
            information_basis={"kind": "owned_or_observed_domain_state"},
            tags=("domain_owned",),
        ))
    return out


def _relationship_provider(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    """Concrete social options from the actor's own relationship/goals, never a generic relationship tick."""
    rels = list(envelope.get("relationships") or [])
    goals = list(envelope.get("goals") or [])
    pressures = list(envelope.get("pressures") or [])
    drives = envelope.get("drives") or {}
    out: list[DecisionCandidate] = []
    for rel in rels[:3]:
        target = int(rel["actor_b_id"])
        if conn.execute("SELECT 1 FROM interactions WHERE status='pending' AND proposer_actor_id=? AND recipient_actor_id=?", (actor_id, target)).fetchone():
            continue
        stance = float(rel.get("stance") or 0)
        familiarity = float(rel.get("familiarity") or 0)
        trust = float(rel.get("trust") or 0)
        resentment = float(rel.get("resentment") or 0)
        obligation = float(rel.get("obligation") or 0)
        target_name = str(rel.get("actor_b_name") or f"actor #{target}")
        purpose = str(goals[0]["description"]) if goals else (str(pressures[0]["description"]) if pressures else "maintain the relationship")
        adverse = max(resentment / 35.0, max(0.0, -trust) / 30.0, max(0.0, -stance) / 40.0)
        if (resentment > 35 or trust < -15 or stance < -25) and (goals or pressures):
            interaction_type = "demand" if float(drives.get("aggression", .5)) >= .55 and (resentment > 20 or stance < -25) else "negotiation"
            utility = 4.0 + adverse + float(drives.get("pragmatism", .5))
        elif obligation > 25 or trust > 20:
            interaction_type = "request" if pressures else "offer"
            utility = 3.2 + max(0.0, trust) / 45.0 + max(0.0, obligation) / 45.0 + float(drives.get("loyalty", .5))
        elif familiarity >= 25 and (goals or pressures):
            # A persisted, familiar counterpart is enough to make a bounded approach plausible.
            # This represents an arrangeable request/negotiation, not proof of exact co-presence.
            interaction_type = "request" if pressures else "negotiation"
            utility = 3.0 + familiarity / 100.0 + float(drives.get("pragmatism", .5))
        else:
            continue
        out.append(DecisionCandidate(
            key=f"social:{interaction_type}:{target}", provider_key="relationship", action_kind=f"social_{interaction_type}",
            utility=utility, rationale=f"Open a concrete {interaction_type} with {target_name} concerning {purpose}.",
            execution_kind="interaction", target_actor_id=target, interaction_type=interaction_type,
            payload={"purpose": purpose, "burden": 0.15, "incentive": 0.15},
            information_basis={"relationship_edge_id": int(rel["id"]), "own_goal_or_pressure": bool(goals or pressures)},
            tags=("social", "specific_counterpart"),
        ))
    return out


def _belief_investigation_provider(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    """Investigate uncertain claims only through a source actor the decision-maker actually knows supplied evidence."""
    out: list[DecisionCandidate] = []
    for belief in envelope.get("beliefs") or []:
        if str(belief.get("stance")) != "uncertain" and float(belief.get("confidence") or 0) >= .45:
            continue
        source = None
        evidence_ids: list[int] = []
        for ev in belief.get("evidence") or []:
            evidence_ids.append(int(ev["id"]))
            if ev.get("source_actor_id") is not None:
                source = int(ev["source_actor_id"])
                break
        if source is None or source == actor_id:
            continue
        if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (source,)).fetchone():
            continue
        if conn.execute("SELECT 1 FROM interactions WHERE status='pending' AND proposer_actor_id=? AND recipient_actor_id=? AND interaction_type='investigation'", (actor_id, source)).fetchone():
            continue
        cid = int(belief["claim_id"])
        out.append(DecisionCandidate(
            key=f"belief:investigate:{cid}:{source}", provider_key="belief_investigation", action_kind="investigate_claim",
            utility=4.0 + (1.0 - float(belief.get("confidence") or 0)) * 2.0,
            rationale=f"Seek clarification of an uncertain claim from a source already represented in the actor's evidence trail.",
            execution_kind="interaction", target_actor_id=source, interaction_type="investigation",
            payload={"claim_id": cid, "purpose": str(belief.get("proposition_text") or "clarify uncertain information")},
            information_basis={"claim_id": cid, "source_actor_id": source}, claim_ids=(cid,), evidence_ids=tuple(evidence_ids),
            tags=("belief_bounded", "investigation"),
        ))
        if len(out) >= 2:
            break
    return out


def _builtin_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    out: list[DecisionCandidate] = []
    out.extend(_ordinary_domain_provider(conn, actor_id, tier, day, envelope))
    out.extend(_relationship_provider(conn, actor_id, tier, day, envelope))
    out.extend(_belief_investigation_provider(conn, actor_id, tier, day, envelope))
    try:
        from .underworld_decisions import underworld_decision_candidates
        out.extend(underworld_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .merchant import merchant_decision_candidates
        out.extend(merchant_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .craft import craft_decision_candidates
        out.extend(craft_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .growth import growth_decision_candidates
        out.extend(growth_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .war import war_decision_candidates
        out.extend(war_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .conflict import polity_conflict_decision_candidates
        out.extend(polity_conflict_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .opportunity import opportunity_decision_candidates
        out.extend(opportunity_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    for _, provider in _PROVIDERS:
        out.extend(provider(conn, actor_id, tier, day, envelope))
    return out


def generate_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    candidates = _builtin_candidates(conn, actor_id, tier, day, envelope)
    # One concrete no-new-commitment candidate is always legal; it is not a hidden goal-progress action.
    candidates.append(DecisionCandidate(
        key="hold:current_commitments", provider_key="baseline", action_kind="hold_position", utility=2.6,
        rationale="Make no new strategic commitment this review and continue existing obligations.", execution_kind="hold",
        information_basis={"kind": "self_state"}, tags=("baseline",),
    ))
    # Deterministic de-duplication protects against provider overlap.
    dedup: dict[str, DecisionCandidate] = {}
    for c in candidates:
        prior = dedup.get(c.key)
        if prior is None or c.utility > prior.utility:
            dedup[c.key] = c
    return [dedup[k] for k in sorted(dedup)]


def audit_candidates() -> bool:
    """Candidate-by-candidate audit rows (decision_candidate_audit) are written only when CAERNESS_DECISION_AUDIT=1: nothing in the engine, connector or tools reads them, and they were
    the second-largest table by year 5. Read at each call so a test or a debugging session can switch it on."""
    return os.environ.get("CAERNESS_DECISION_AUDIT", "") not in ("", "0")


def choose_candidate(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> tuple[DecisionCandidate, int]:
    candidates = generate_candidates(conn, actor_id, tier, day, envelope)
    if not candidates:
        raise RuntimeError("decision runtime produced no candidates")
    max_u = max(c.utility for c in candidates)
    plausible = [c for c in candidates if c.utility >= max_u - 4.0]
    temperature = {"ACTIVE": .85, "STRATEGIC": .95, "DORMANT": 1.10}.get(tier, .95)
    raw_weights = [math.exp((c.utility - max_u) / max(.15, temperature)) for c in plausible]
    total = sum(raw_weights) or 1.0
    probabilities = [w / total for w in raw_weights]
    rng = _rng(conn, actor_id, day)
    draw = rng.random()
    cumulative = 0.0
    chosen = plausible[-1]
    for c, p in zip(plausible, probabilities):
        cumulative += p
        if draw <= cumulative:
            chosen = c
            break

    summary = {
        "belief_count": len(envelope.get("beliefs") or []),
        "relationship_count": len(envelope.get("relationships") or []),
        "goal_count": len(envelope.get("goals") or []),
        "pressure_count": len(envelope.get("pressures") or []),
        "canon_chunk_count": len(envelope.get("canon") or []),
        "information_rule": "actor_accessible_only",
    }
    cur = conn.execute(
        """INSERT INTO decision_evaluations(day,actor_id,tier,temperature,random_draw,selected_candidate_key,envelope_summary_json)
           VALUES (?,?,?,?,?,?,?)""",
        (day, actor_id, tier, temperature, draw, chosen.key, json.dumps(summary, sort_keys=True)),
    )
    evaluation_id = int(cur.lastrowid)
    prob_by_key = {c.key: p for c, p in zip(plausible, probabilities)}
    for c in (candidates if audit_candidates() else ()):
        conn.execute(
            """INSERT INTO decision_candidate_audit(evaluation_id,candidate_key,provider_key,action_kind,utility,selection_probability,
                   plausible,selected,target_actor_id,interaction_type,information_basis_json,payload_json,tags_json,estimated_cost,risk)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (evaluation_id, c.key, c.provider_key, c.action_kind, c.utility, prob_by_key.get(c.key, 0.0),
             1 if c in plausible else 0, 1 if c.key == chosen.key else 0, c.target_actor_id, c.interaction_type,
             json.dumps(c.information_basis, sort_keys=True, default=str), json.dumps(c.payload, sort_keys=True, default=str),
             json.dumps(list(c.tags)), float(c.estimated_cost), float(c.risk)),
        )
    return chosen, evaluation_id


def record_external_selection(
    conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any],
    candidates: list[DecisionCandidate], selected_key: str,
) -> int:
    """Audit a bounded external/manual selector that chooses from engine-generated candidates."""
    selected = next((c for c in candidates if c.key == selected_key), None)
    if selected is None:
        raise ValueError("selected candidate is not currently feasible")
    summary = {
        "belief_count": len(envelope.get("beliefs") or []), "relationship_count": len(envelope.get("relationships") or []),
        "goal_count": len(envelope.get("goals") or []), "pressure_count": len(envelope.get("pressures") or []),
        "canon_chunk_count": len(envelope.get("canon") or []), "information_rule":"actor_accessible_only",
        "selector":"external_bounded_candidate_choice",
    }
    cur=conn.execute(
        """INSERT INTO decision_evaluations(day,actor_id,tier,temperature,random_draw,selected_candidate_key,envelope_summary_json)
           VALUES (?,?,?,?,?,?,?)""", (day,actor_id,tier,1.0,0.0,selected_key,json.dumps(summary,sort_keys=True))
    )
    eid=int(cur.lastrowid)
    for c in (candidates if audit_candidates() else ()):
        conn.execute(
            """INSERT INTO decision_candidate_audit(evaluation_id,candidate_key,provider_key,action_kind,utility,selection_probability,
                   plausible,selected,target_actor_id,interaction_type,information_basis_json,payload_json,tags_json,estimated_cost,risk)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid,c.key,c.provider_key,c.action_kind,c.utility,1.0 if c.key==selected_key else 0.0,1,1 if c.key==selected_key else 0,
             c.target_actor_id,c.interaction_type,json.dumps(c.information_basis,sort_keys=True,default=str),json.dumps(c.payload,sort_keys=True,default=str),
             json.dumps(list(c.tags)),float(c.estimated_cost),float(c.risk)),
        )
    return eid
```


(End of batch 1 of 5.)
