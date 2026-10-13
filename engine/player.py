from __future__ import annotations

import json
import sqlite3
from typing import Any

from .canon import search_canon
from .information import hear_local_rumours, learn_public_events_at_location, process_information
from .competence import active_matters, pending_attention, process_competence
from .expertise import build_scene_competence_packet
from .embodiment import build_embodiment_packet, ensure_embodiment_profile
from .health import build_health_packet
from .religion import religion_context, cultural_context
from .politics import politics_summary
from .ecology import ecology_context
from .education import education_context
from .presence import actors_plausibly_present
from .belief import actor_belief_envelope


def set_player(conn: sqlite3.Connection, actor_id: int, campaign_name: str = "Campaign 01") -> None:
    actor = conn.execute("SELECT id,current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not actor:
        raise ValueError(f"unknown actor_id {actor_id}")
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    ensure_embodiment_profile(conn, actor_id)
    conn.execute(
        """INSERT INTO player_state(id,player_actor_id,current_location_id,campaign_name,updated_day)
           VALUES (1,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             player_actor_id=excluded.player_actor_id,
             current_location_id=excluded.current_location_id,
             campaign_name=excluded.campaign_name,
             updated_day=excluded.updated_day""",
        (actor_id, actor["current_location_id"], campaign_name, day),
    )


def get_player(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT ps.*,a.name actor_name,a.actor_type,a.subtype,a.status actor_status,
                  l.name location_name,l.kind location_kind,l.political_owner,l.notes location_notes
           FROM player_state ps
           JOIN actors a ON a.id=ps.player_actor_id
           LEFT JOIN locations l ON l.id=COALESCE(ps.current_location_id,a.current_location_id)
           WHERE ps.id=1"""
    ).fetchone()


def sync_player_location(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        """SELECT ps.player_actor_id,a.current_location_id
           FROM player_state ps JOIN actors a ON a.id=ps.player_actor_id WHERE ps.id=1"""
    ).fetchone()
    if not row:
        return None
    conn.execute(
        "UPDATE player_state SET current_location_id=?,updated_day=(SELECT current_day FROM world_state WHERE id=1) WHERE id=1",
        (row["current_location_id"],),
    )
    return int(row["current_location_id"]) if row["current_location_id"] is not None else None


def _known_event_ids(conn: sqlite3.Connection, actor_id: int) -> set[int]:
    return {
        int(r[0])
        for r in conn.execute(
            "SELECT truth_event_id FROM knowledge WHERE knower_actor_id=? AND truth_event_id IS NOT NULL",
            (actor_id,),
        ).fetchall()
    }


def _known_events(conn: sqlite3.Connection, actor_id: int, limit: int = 12) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT DISTINCT e.id,e.day,e.event_type,e.title,e.summary,e.severity,e.location_id,
                  k.confidence,k.learned_day,l.name location_name,ei.visibility
           FROM knowledge k
           JOIN events e ON e.id=k.truth_event_id
           LEFT JOIN event_information ei ON ei.event_id=e.id
           LEFT JOIN locations l ON l.id=e.location_id
           WHERE k.knower_actor_id=? AND k.fact_key LIKE 'event:%'
           ORDER BY e.day DESC,e.id DESC LIMIT ?""",
        (actor_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def _known_rumours(conn: sqlite3.Connection, actor_id: int, limit: int = 12) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT DISTINCT r.id,r.created_day,r.text,r.distortion,r.reach,r.status,
                  k.confidence,k.learned_day,l.name origin_name
           FROM knowledge k
           JOIN knowledge_provenance kp ON kp.knowledge_id=k.id AND kp.source_kind='rumour'
           JOIN rumours r ON r.id=kp.source_id
           LEFT JOIN locations l ON l.id=r.origin_location_id
           WHERE k.knower_actor_id=?
           ORDER BY k.learned_day DESC,k.id DESC LIMIT ?""",
        (actor_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def _player_state_detail(conn: sqlite3.Connection, actor_id: int) -> dict[str, Any]:
    goals = [dict(r) for r in conn.execute(
        "SELECT id,description,priority,progress,status,target_day FROM goals WHERE actor_id=? ORDER BY priority DESC,id",
        (actor_id,),
    ).fetchall()]
    pressures = [dict(r) for r in conn.execute(
        "SELECT id,kind,description,intensity,threshold,updated_day FROM pressures WHERE actor_id=? ORDER BY intensity DESC,id",
        (actor_id,),
    ).fetchall()]
    resources = [dict(r) for r in conn.execute(
        "SELECT resource_type,amount,unit,updated_day FROM resources WHERE actor_id=? ORDER BY resource_type",
        (actor_id,),
    ).fetchall()]
    relationships = [dict(r) for r in conn.execute(
        """SELECT r.id,a.name actor_a,b.name actor_b,r.stance,r.familiarity,r.trust,r.affection,r.respect,r.fear,r.loyalty,r.resentment,r.obligation,r.professional_confidence,r.updated_day
           FROM relationships r JOIN actors a ON a.id=r.actor_a_id JOIN actors b ON b.id=r.actor_b_id
           WHERE r.actor_a_id=? ORDER BY r.updated_day DESC,r.id""",
        (actor_id,),
    ).fetchall()]
    return {"goals": goals, "pressures": pressures, "resources": resources, "relationships": relationships}


def _present_actors(conn: sqlite3.Connection, player_actor_id: int, location_id: int | None) -> list[dict[str, Any]]:
    if location_id is None:
        return []
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    ids = [aid for aid in actors_plausibly_present(conn, location_id, day=day, purpose=f"scene:{player_actor_id}") if aid != player_actor_id]
    rows = []
    if ids:
        marks = ",".join("?" for _ in ids)
        rows.extend(conn.execute(
            f"SELECT id,name,actor_type,subtype,status FROM actors WHERE id IN ({marks}) AND status='active'",
            tuple(ids),
        ).fetchall())
    # Presence profiles model people. Institutions remain scene context when their explicit
    # institutional location is this place; they are not probabilistically 'walking around'.
    rows.extend(conn.execute(
        """SELECT id,name,actor_type,subtype,status FROM actors
           WHERE actor_type='institution' AND status='active' AND current_location_id=?""",
        (location_id,),
    ).fetchall())
    # Deliberately no goals, drives, pressures, resources or hidden relationships here.
    unique = {int(r['id']): dict(r) for r in rows}
    return sorted(unique.values(), key=lambda r: (str(r['actor_type']), str(r['name'])))


def _pending_player_interactions(conn: sqlite3.Connection, actor_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT i.id,i.created_day,i.interaction_type,i.status,i.urgency,i.stakes,i.terms_json,
                  i.response_due_day,p.name proposer_name,r.name recipient_name
           FROM interactions i
           JOIN actors p ON p.id=i.proposer_actor_id JOIN actors r ON r.id=i.recipient_actor_id
           WHERE i.status='pending' AND (i.proposer_actor_id=? OR i.recipient_actor_id=?)
           ORDER BY i.response_due_day,i.id""",
        (actor_id, actor_id),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["terms"] = json.loads(item.pop("terms_json") or "{}")
            # Social utility inputs belong to the resolver, never NPC dialogue.
            item["terms"].pop("burden", None)
            item["terms"].pop("incentive", None)
        except Exception:
            item["terms"] = {}
        out.append(item)
    return out


def _canon_query(player: sqlite3.Row, request_text: str, present: list[dict[str, Any]], known_events: list[dict[str, Any]]) -> str:
    terms = [
        "Caerness",
        str(player["location_name"] or ""),
        str(player["location_kind"] or ""),
        str(player["actor_name"] or ""),
        str(player["subtype"] or ""),
        request_text or "",
    ]
    terms.extend(str(a["name"]) for a in present[:4])
    terms.extend(str(e["title"]) for e in known_events[-3:])
    return " ".join(t for t in terms if t)


def build_scene_packet(
    conn: sqlite3.Connection,
    request_text: str = "",
    *,
    canon_limit: int = 6,
    event_limit: int = 12,
    rumour_limit: int = 12,
) -> dict[str, Any]:
    sync_player_location(conn)
    player = get_player(conn)
    if not player:
        raise ValueError("No player is configured. Use player-set first.")

    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    player_actor_id = int(player["player_actor_id"])
    location_id = int(player["current_location_id"]) if player["current_location_id"] is not None else None

    process_information(conn, day)
    if location_id is not None:
        learn_public_events_at_location(conn, player_actor_id, location_id, day)
        hear_local_rumours(conn, player_actor_id, location_id, day)

    present = _present_actors(conn, player_actor_id, location_id)
    embodiment = build_embodiment_packet(
        conn, player_actor_id, present_actor_ids=[int(a["id"]) for a in present], request_text=request_text
    )
    competence_outcomes = process_competence(
        conn, player_actor_id, current_location_id=location_id,
        present_actor_ids={int(a["id"]) for a in present},
    )
    # Routine competence may itself have created a private event known directly to the player.
    process_information(conn, day)
    known_events = _known_events(conn, player_actor_id, event_limit)
    known_rumours = _known_rumours(conn, player_actor_id, rumour_limit)
    attention = pending_attention(conn, player_actor_id, mark_shown=False, limit=12)
    matters = active_matters(conn, player_actor_id)
    from .player_appointments import known_appointments
    matters["appointments"] = known_appointments(conn, player_actor_id)
    professional_context = build_scene_competence_packet(conn, player_actor_id, request_text or "")
    health_context = build_health_packet(conn, player_actor_id)
    religious_context = religion_context(conn, player_actor_id, location_id)
    culture_context = cultural_context(conn, location_id)
    environment_context = ecology_context(conn, location_id)
    political_context = politics_summary(conn)
    education_state = education_context(conn, player_actor_id)
    query = _canon_query(player, request_text, present, known_events)
    chunks = search_canon(query, limit=canon_limit, conn=conn)

    packet: dict[str, Any] = {
        "world": {
            "name": "Caerness",
            "day": day,
            "campaign": player["campaign_name"],
        },
        "player": {
            "actor_id": player_actor_id,
            "name": player["actor_name"],
            "actor_type": player["actor_type"],
            "subtype": player["subtype"],
            **_player_state_detail(conn, player_actor_id),
        },
        "location": {
            "id": location_id,
            "name": player["location_name"],
            "kind": player["location_kind"],
            "political_owner": player["political_owner"],
            "notes": player["location_notes"],
        },
        "present_actors": present,
        "known_events": known_events,
        "known_rumours": known_rumours,
        "beliefs": actor_belief_envelope(conn, player_actor_id, limit=50),
        "pending_player_interactions": _pending_player_interactions(conn, player_actor_id),
        "embodiment": embodiment,
        "attention_cues": attention,
        "competence_outcomes": [o.as_dict() for o in competence_outcomes],
        "professional_context": professional_context,
        "health_context": health_context,
        "religious_context": religious_context,
        "cultural_context": culture_context,
        "environment_context": environment_context,
        "political_context": political_context,
        "education_context": education_state,
        "matters": matters,
        "canon": [
            {"chunk_id": c.id, "heading": c.heading_path, "text": c.text, "source": c.source}
            for c in chunks
        ],
        "request": request_text,
        "camera_principle": "The player is the story's camera focus, not the world's protagonist or causal center.",
        "narrator_rules": [
            "The player is the camera focus, not the world's causal center.",
            "Use accessible knowledge and canon as constraints, not an exhaustive inventory. Compatible creative additions are permitted; durable objective additions use campaign authorship before future reliance.",
            "Treat rumours as beliefs, not verified truth, unless the same fact is separately known.",
            "Use the beliefs envelope as actor-relative claims grounded in accessible evidence; confidence is not objective truth, and hidden authoritative truth links are not exposed here.",
            "Do not reveal other actors' hidden goals, pressures, drives, resources, or private relationships.",
            "Do not invent permanent state changes in prose; resolve them through the simulation/state layer first.",
            "The wider world continues moving off-screen at the resolution appropriate to each actor's tier.",
            "Do not make unrelated actors or events converge on the player simply because the player is present.",
            "Local people should visibly have agendas, work, relationships and routines that do not exist for the player's benefit.",
            "The Character Competence Layer handles obvious follow-through. Do not make the player restate routine actions already resolved by competence_outcomes.",
            "Use professional_context to mediate expertise: interpret accessible evidence at the character's domain level, distinguish observation from inference, and never reveal hidden world state.",
            "Character professional reading, reports, advisor judgment, and player choice are separate layers; do not merge an advisor's opinion into objective truth or the protagonist's own expertise.",
            "Use health_context as authoritative capacity state. Injury, illness, aging and disability constrain what the character can sustain without dictating their choices or personality.",
            "Use religious_context as lived social context. Do not infer private belief from faction or public observance. Compatible local customs may be developed through campaign authorship; preserve established doctrine and distinguish beliefs from objective truth.",
            "Use cultural_context for local institutions and scheduled public cultural life. Cultural institutions exist for their own continuity, patrons and audiences rather than to generate content for the player.",
            "Use environment_context for route, season, production and exposure constraints. Incidental atmosphere and compatible customs may be improvised; consequential route closures or disasters need validation and persistence, not prose that silently changes travel outcomes.",
            "Use political_context as authoritative macro-state. Do not preserve states, borders, rulers, or alliances merely because they were important at campaign start, and do not invent political transformations that have not been resolved by the simulation.",
            "Use education_context as authoritative training and transmission state. Access to a manual is not mastery; teachers, time, competence gates, and living transmission matter. Do not invent completed training, certifications, or master-disciple bonds that the engine has not resolved.",
            "Do not end with generic game prompts such as 'What do you do?' or 'What happens next?'. End naturally at the agency handoff.",
            "A narration response may span multiple scenes, transitions, or days if no meaningful player intervention was required in between.",
            "Use the embodiment packet to keep the protagonist consistent between direct commands.",
            "Player wording is intent/content/tone unless explicitly marked as exact dialogue.",
            "Small low-stakes expression may be inferred when strongly supported; major commitments always return to player agency.",
            "Do not turn persistent personality into caricature or invent major hidden self-knowledge for the player character.",
        ],
    }
    cur = conn.execute(
        """INSERT INTO scene_packets(day,player_actor_id,location_id,request_text,canon_chunk_ids_json,payload_json)
           VALUES (?,?,?,?,?,?)""",
        (day, player_actor_id, location_id, request_text, json.dumps([c.id for c in chunks]), json.dumps(packet)),
    )
    packet_id = int(cur.lastrowid)
    packet["scene_packet_id"] = packet_id
    return packet


def render_scene_brief(packet: dict[str, Any]) -> str:
    location = packet["location"]
    player = packet["player"]
    lines = [
        f"CAERNESS SCENE PACKET #{packet['scene_packet_id']} — Day {packet['world']['day']}",
        f"Player: {player['name']} ({player.get('subtype') or player.get('actor_type')})",
        f"Location: {location.get('name') or 'Unknown'} ({location.get('kind') or 'unknown'})",
    ]
    if packet.get("request"):
        lines.append(f"Player request: {packet['request']}")

    present = packet.get("present_actors") or []
    lines.append("\nVisible/present actors:")
    if present:
        lines.extend(f"- {a['name']} — {a.get('subtype') or a['actor_type']}" for a in present)
    else:
        lines.append("- none persisted at this exact location")

    events = packet.get("known_events") or []
    lines.append("\nKnown events:")
    if events:
        lines.extend(f"- Day {e['day']}: {e['title']} — {e['summary']}" for e in events[-8:])
    else:
        lines.append("- none")

    rumours = packet.get("known_rumours") or []
    lines.append("\nRumours heard (unverified unless separately known):")
    if rumours:
        lines.extend(f"- {r['text']} [confidence {r['confidence']:.2f}]" for r in rumours[-8:])
    else:
        lines.append("- none")

    cues = packet.get("attention_cues") or []
    lines.append("\nCharacter-salient reminders / competence:")
    if cues:
        lines.extend(f"- [{c['cue_type']}] {c['text']}" for c in cues[-8:])
    else:
        lines.append("- none")

    interactions = packet.get("pending_player_interactions") or []
    lines.append("\nPending interactions involving player:")
    if interactions:
        lines.extend(
            f"- #{i['id']} {i['interaction_type']}: {i['proposer_name']} -> {i['recipient_name']} (due day {i['response_due_day']})"
            for i in interactions
        )
    else:
        lines.append("- none")

    lines.append("\nRelevant canon:")
    for c in packet.get("canon") or []:
        text = str(c["text"]).replace("\n", " ")
        if len(text) > 360:
            text = text[:357] + "..."
        lines.append(f"- [{c['chunk_id']}] {c['heading']}: {text}")

    lines.append("\nNarrator guardrails:")
    lines.extend(f"- {r}" for r in packet.get("narrator_rules") or [])
    return "\n".join(lines)

# v0.25 camera succession -----------------------------------------------------

def designate_camera_successor(conn: sqlite3.Connection, from_actor_id: int, successor_actor_id: int, *,
                               priority: int = 50, notes: str | None = None) -> int:
    if int(from_actor_id) == int(successor_actor_id):
        raise ValueError('Camera successor must be a different actor')
    src = conn.execute("SELECT id FROM actors WHERE id=?", (from_actor_id,)).fetchone()
    dst = conn.execute("SELECT id,status FROM actors WHERE id=?", (successor_actor_id,)).fetchone()
    if not src or not dst:
        raise ValueError('Unknown actor')
    if str(dst['status']).lower() in ('dead','deceased'):
        raise ValueError('Camera successor must be living when designated')
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    conn.execute(
        """INSERT INTO player_camera_successors(from_actor_id,successor_actor_id,priority,status,designated_day,notes)
           VALUES (?,?,?,'designated',?,?)
           ON CONFLICT(from_actor_id,successor_actor_id) DO UPDATE SET priority=excluded.priority,
             status='designated',designated_day=excluded.designated_day,resolved_day=NULL,notes=excluded.notes""",
        (from_actor_id, successor_actor_id, int(priority), day, notes),
    )
    return int(conn.execute(
        "SELECT id FROM player_camera_successors WHERE from_actor_id=? AND successor_actor_id=?",
        (from_actor_id, successor_actor_id),
    ).fetchone()[0])


def revoke_camera_successor(conn: sqlite3.Connection, designation_id: int) -> None:
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    row = conn.execute("SELECT status FROM player_camera_successors WHERE id=?", (designation_id,)).fetchone()
    if not row:
        raise ValueError('Unknown camera successor designation')
    if str(row['status']) == 'used':
        raise ValueError('A used camera succession cannot be revoked')
    conn.execute("UPDATE player_camera_successors SET status='revoked',resolved_day=? WHERE id=?", (day, designation_id))


def transfer_camera(conn: sqlite3.Connection, actor_id: int, *, reason: str = 'explicit camera transfer') -> None:
    target = conn.execute("SELECT id,status,current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not target:
        raise ValueError(f'unknown actor_id {actor_id}')
    if str(target['status']).lower() in ('dead','deceased'):
        raise ValueError('Cannot move the narrative camera to a deceased actor')
    old = conn.execute("SELECT player_actor_id,campaign_name FROM player_state WHERE id=1").fetchone()
    old_id = int(old['player_actor_id']) if old and old['player_actor_id'] is not None else None
    campaign = str(old['campaign_name']) if old and old['campaign_name'] else 'Campaign 01'
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    set_player(conn, actor_id, campaign)
    conn.execute(
        "INSERT INTO player_camera_history(day,from_actor_id,to_actor_id,reason,campaign_name) VALUES (?,?,?,?,?)",
        (day, old_id, actor_id, reason, campaign),
    )


def process_camera_succession(conn: sqlite3.Connection) -> int | None:
    """Move the camera only when the current focus is dead and an explicit living successor exists.

    This is deliberately not an heir-selection or protagonist-resurrection system. If no valid
    designation exists, the player_state remains pointed at the deceased character until the user
    explicitly chooses another camera actor.
    """
    row = conn.execute(
        """SELECT ps.player_actor_id,a.status FROM player_state ps
           LEFT JOIN actors a ON a.id=ps.player_actor_id WHERE ps.id=1"""
    ).fetchone()
    if not row or row['player_actor_id'] is None:
        return None
    current = int(row['player_actor_id'])
    if str(row['status'] or '').lower() not in ('dead','deceased'):
        return None
    candidates = conn.execute(
        """SELECT pcs.*,a.status actor_status FROM player_camera_successors pcs
           JOIN actors a ON a.id=pcs.successor_actor_id
           WHERE pcs.from_actor_id=? AND pcs.status='designated'
           ORDER BY pcs.priority DESC,pcs.designated_day,pcs.id""",
        (current,),
    ).fetchall()
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    chosen = None
    for c in candidates:
        if str(c['actor_status']).lower() in ('dead','deceased'):
            conn.execute("UPDATE player_camera_successors SET status='unavailable',resolved_day=? WHERE id=?", (day, c['id']))
            continue
        chosen = c
        break
    if not chosen:
        return None
    successor = int(chosen['successor_actor_id'])
    transfer_camera(conn, successor, reason=f"camera succession after actor #{current} death")
    conn.execute("UPDATE player_camera_successors SET status='used',resolved_day=? WHERE id=?", (day, chosen['id']))
    return successor


def camera_history(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM player_camera_history ORDER BY day,id").fetchall()]
