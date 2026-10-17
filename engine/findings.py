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


def _events_about(conn: sqlite3.Connection, actor: int, limit: int = 4) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT e.day,e.title FROM events e LEFT JOIN event_targets t ON t.event_id=e.id
           WHERE (e.source_actor_id=? OR t.actor_id=?) AND e.severity<=4 ORDER BY e.day DESC,e.id DESC LIMIT ?""", (actor, actor, limit)).fetchall()
    return [f"On day {r[0]}: {r[1]}" for r in rows]


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
            plain.append(f"On day {r[0]}: {r[1]}")
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
                plain.append(f"On day {r[0]}: {r[1]}")
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
