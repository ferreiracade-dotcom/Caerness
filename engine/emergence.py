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
