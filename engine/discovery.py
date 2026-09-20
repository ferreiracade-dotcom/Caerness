from __future__ import annotations

import sqlite3
from typing import Any

from .competence import active_matters, pending_attention
from .emergence import important_memories
from .player import get_player


def _source_label(row: sqlite3.Row) -> str:
    kind = str(row["source_kind"])
    if kind == "event":
        return "direct event / witness record"
    if kind == "rumour":
        return "rumour"
    if kind == "actor":
        return "another person"
    if kind == "channel":
        return "information network"
    if kind == "scene":
        return "personal observation"
    return kind


def known_claims(conn: sqlite3.Connection, actor_id: int, limit: int = 120) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT k.id,k.fact_key,k.belief_text,k.confidence,k.learned_day,k.truth_event_id,
                  kp.source_kind,kp.source_id,kp.location_id,kp.acquired_day,kp.notes,
                  l.name source_location_name
           FROM knowledge k
           LEFT JOIN knowledge_provenance kp ON kp.id=(
               SELECT kp2.id FROM knowledge_provenance kp2 WHERE kp2.knowledge_id=k.id ORDER BY kp2.id DESC LIMIT 1
           )
           LEFT JOIN locations l ON l.id=kp.location_id
           WHERE k.knower_actor_id=?
           ORDER BY k.learned_day DESC,k.id DESC LIMIT ?""",
        (actor_id, limit),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["source_label"] = _source_label(row) if row["source_kind"] else "unknown source"
        item["certainty"] = (
            "personally/directly known" if float(row["confidence"]) >= 0.9
            else "fairly reliable" if float(row["confidence"]) >= 0.7
            else "uncertain"
        )
        out.append(item)
    return out


def known_people(conn: sqlite3.Connection, actor_id: int) -> list[dict[str, Any]]:
    # People are visible because the character has an actual persisted relationship or shared event memory.
    ids: set[int] = set()
    for row in conn.execute(
        "SELECT actor_a_id,actor_b_id FROM relationships WHERE actor_a_id=?",
        (actor_id,),
    ).fetchall():
        ids.add(int(row["actor_b_id"]))
    for row in conn.execute(
        "SELECT subject_actor_id FROM actor_memories WHERE actor_id=? AND subject_actor_id IS NOT NULL AND status='active'",
        (actor_id,),
    ).fetchall():
        ids.add(int(row[0]))
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""SELECT id,name,actor_type,subtype,status FROM actors WHERE id IN ({placeholders}) ORDER BY name""",
        tuple(sorted(ids)),
    ).fetchall()
    memories = important_memories(conn, actor_id, limit=40)
    by_subject: dict[int, list[dict[str, Any]]] = {}
    for m in memories:
        if m.get("subject_actor_id") is not None:
            by_subject.setdefault(int(m["subject_actor_id"]), []).append(m)
    out = []
    for row in rows:
        rel = conn.execute(
            """SELECT stance,trust,obligation,updated_day FROM relationships
               WHERE actor_a_id=? AND actor_b_id=? LIMIT 1""",
            (actor_id, row["id"]),
        ).fetchone()
        # Numeric relationship internals are intentionally NOT exposed; only shared-history evidence is.
        out.append({
            "id": int(row["id"]),
            "name": str(row["name"]),
            "type": str(row["subtype"] or row["actor_type"]),
            "status": str(row["status"]),
            "shared_history": [m["summary"] for m in by_subject.get(int(row["id"]), [])[:6]],
            "relationship_last_changed_day": int(rel["updated_day"]) if rel else None,
        })
    return out


def known_places(conn: sqlite3.Connection, actor_id: int) -> list[dict[str, Any]]:
    ids: set[int] = set()
    player = get_player(conn)
    if player and int(player["player_actor_id"]) == actor_id and player["current_location_id"] is not None:
        ids.add(int(player["current_location_id"]))
    home = conn.execute("SELECT home_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    if home and home[0] is not None:
        ids.add(int(home[0]))
    for row in conn.execute(
        """SELECT DISTINCT e.location_id FROM knowledge k JOIN events e ON e.id=k.truth_event_id
           WHERE k.knower_actor_id=? AND e.location_id IS NOT NULL""",
        (actor_id,),
    ).fetchall():
        ids.add(int(row[0]))
    for row in conn.execute(
        """SELECT DISTINCT kp.location_id FROM knowledge k JOIN knowledge_provenance kp ON kp.knowledge_id=k.id
           WHERE k.knower_actor_id=? AND kp.location_id IS NOT NULL""",
        (actor_id,),
    ).fetchall():
        ids.add(int(row[0]))
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id,name,kind,political_owner FROM locations WHERE id IN ({placeholders}) ORDER BY name",
        tuple(sorted(ids)),
    ).fetchall()
    out = []
    for row in rows:
        last = conn.execute(
            """SELECT MAX(k.learned_day) FROM knowledge k JOIN knowledge_provenance kp ON kp.knowledge_id=k.id
               WHERE k.knower_actor_id=? AND kp.location_id=?""",
            (actor_id, row["id"]),
        ).fetchone()[0]
        out.append({
            "id": int(row["id"]), "name": row["name"], "kind": row["kind"],
            "political_owner": row["political_owner"], "last_information_day": int(last) if last is not None else None,
        })
    return out


def player_information_hub(conn: sqlite3.Connection) -> dict[str, Any]:
    player = get_player(conn)
    if not player:
        return {"player": None, "attention": [], "matters": {}, "people": [], "places": [], "claims": []}
    actor_id = int(player["player_actor_id"])
    return {
        "player": {
            "id": actor_id,
            "name": player["actor_name"],
            "location": player["location_name"],
            "campaign": player["campaign_name"],
        },
        "attention": pending_attention(conn, actor_id, limit=12),
        "matters": active_matters(conn, actor_id),
        "people": known_people(conn, actor_id),
        "places": known_places(conn, actor_id),
        "claims": known_claims(conn, actor_id, limit=80),
    }
