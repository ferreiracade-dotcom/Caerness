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
