"""Compact read-only views over the engine for the Claude connector."""
from __future__ import annotations

import json

from connector import store

_LIMITS = {"present": 12, "news": 5, "competence": 6, "notes": 6}


def _clip(text, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _age(conn, actor_id: int, day: int):
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    return int((day - r[0]) // 365) if r and r[0] is not None else None


def _pending(item: dict) -> dict:
    terms = item.get("terms") or {}
    about = terms.get("purpose") or terms.get("subject") or item.get("recipient_name")
    return {"interaction_id": item["id"], "kind": item["interaction_type"], "from": item["proposer_name"],
            "about": _clip(about, 100)}


def _competence(prof: dict) -> list[str]:
    rows = prof.get("relevant_domains") or []
    lines = [f"{r['domain']}: {r['label']}" for r in rows]
    if not lines:
        best = sorted(prof.get("all_domains") or [], key=lambda d: -float(d.get("score") or 0))
        lines = [f"{d['domain_name']}: {d['band']['label']}. {_clip(d['band']['description'], 90)}" for d in best]
    return lines[: _LIMITS["competence"]]


def _condition(h: dict) -> str:
    bits = [str(h.get("aging_phase") or "unknown phase"), f"capacity {round(float(h.get('functional_capacity') or 0))}%"]
    for key in ("conditions", "disabilities"):
        for c in (h.get(key) or [])[:2]:
            bits.append(_clip(c.get("name") or c.get("label") or c.get("kind") or c if isinstance(c, dict) else c, 40))
    return _clip(", ".join(bits), 160)


def compact_scene(conn) -> dict:
    """Commits (it drops its own audit packet), so never call it inside a run_once callback."""
    from engine.player import build_scene_packet

    p = build_scene_packet(conn)
    # The packet row is an audit copy the connector does not need; keep the save small.
    conn.execute("DELETE FROM scene_packets WHERE id=?", (p["scene_packet_id"],))
    conn.commit()
    day = int(p["world"]["day"])
    me, loc = p["player"], p["location"]
    present = [{"id": a["id"], "name": a["name"], "who": _clip(a.get("subtype") or a.get("actor_type"), 80)}
               for a in p["present_actors"][: _LIMITS["present"]]]
    events = [f"day {e['day']}: {_clip(e['title'], 100)}" for e in p["known_events"][-_LIMITS["news"]:]]
    rumours = ["rumour: " + _clip(r["text"], 110) for r in p["known_rumours"][-_LIMITS["news"]:]]
    notes = []
    for kind, sid, name in [("location", loc["id"], loc["name"])] + [("actor", a["id"], a["name"]) for a in present]:
        if sid is None:
            continue
        notes += [{"about": name, "text": _clip(t, 160)} for t in store.notes_for(conn, kind, int(sid), 2)]
    desc = "; ".join(x for x in (loc.get("kind"), loc.get("notes"), loc.get("political_owner")) if x)
    return _drop_none({
        "day": day,
        "location": {"id": loc["id"], "name": loc["name"], "description": _clip(desc, 140)},
        "protagonist": _drop_none({"id": me["actor_id"], "name": me["name"], "age": _age(conn, me["actor_id"], day),
                                   "role": _clip(me.get("subtype") or me.get("actor_type"), 100)}),
        "present": present,
        "pending": [_pending(i) for i in p["pending_player_interactions"][:5]],
        "news": {"events": events, "rumours": rumours},
        "competence": _competence(p["professional_context"]),
        "condition": _condition(p["health_context"]),
        "notes": notes[: _LIMITS["notes"]],
        "recent_operations": store.recent_operations(conn),
    })


def _like(text: str) -> str:
    return "%" + text.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def _find(conn, table: str, q: str):
    if q.isdigit():
        return conn.execute(f"SELECT * FROM {table} WHERE id=?", (int(q),)).fetchall()
    rows = conn.execute(f"SELECT * FROM {table} WHERE name=? COLLATE NOCASE", (q,)).fetchall()
    return rows or conn.execute(f"SELECT * FROM {table} WHERE name LIKE ? ESCAPE '!' ORDER BY id LIMIT 5", (_like(q),)).fetchall()


def lookup(conn, query: str) -> dict:
    from engine.player import get_player
    from engine.relationships import relationship_exists, relationship_view

    q = str(query or "").strip()
    if not q:
        return {"found": False, "candidates": []}
    actors, locs = _find(conn, "actors", q), _find(conn, "locations", q)
    hits = [("actor", r) for r in actors] + [("location", r) for r in locs]
    if len(hits) != 1:
        exact = [h for h in hits if h[1]["name"].lower() == q.lower()]
        if len(exact) == 1:
            hits = exact
    if len(hits) != 1:
        return {"found": False, "candidates": [h[1]["name"] for h in hits[:5]]}
    kind, r = hits[0]
    out = {"found": True, "kind": kind, "id": int(r["id"]), "name": r["name"]}
    if kind == "actor":
        where = conn.execute("SELECT name FROM locations WHERE id=?", (r["current_location_id"],)).fetchone()
        out["basics"] = _drop_none({"type": r["actor_type"], "role": _clip(r["subtype"], 100), "status": r["status"],
                                    "last_known_place": where[0] if where else None})
    else:
        out["basics"] = _drop_none({"kind": r["kind"], "owner": r["political_owner"], "notes": _clip(r["notes"], 160)})
    pl = get_player(conn)
    if pl:
        me = int(pl["player_actor_id"])
        like = _like(r["name"])
        known = conn.execute(
            """SELECT belief_text,confidence,learned_day FROM knowledge
               WHERE knower_actor_id=? AND belief_text LIKE ? ESCAPE '!' ORDER BY learned_day DESC,id DESC LIMIT 8""",
            (me, like)).fetchall()
        if known:
            out["known"] = [{"text": _clip(k[0], 160), "confidence": round(float(k[1]), 2), "learned_day": k[2]} for k in known]
        if kind == "actor" and me != out["id"] and relationship_exists(conn, me, out["id"]):
            rel = relationship_view(conn, me, out["id"])
            out["relationship"] = {k: round(v) for k, v in rel.items() if abs(v) >= 0.5}
    notes = store.notes_for(conn, kind, out["id"])
    if notes:
        out["notes"] = [_clip(n, 160) for n in notes]
    return out
