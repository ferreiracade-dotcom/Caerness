"""author: make an invented person, business, organisation or rumour real, or say why the world has no such thing."""
from __future__ import annotations

from connector import store
from engine.authoring import AuthoringRefused, author as engine_author
from engine.player import get_player

# result key -> table the new entity lives in
_ENTITY = (("actor_id", "actors"), ("enterprise_id", "civilian_enterprises"), ("outfit_id", "underworld_organizations"),
           ("institution_actor_id", "actors"), ("rumour_id", "rumours"))


def author(conn, call_id: str, kind: str, details: dict | None = None) -> dict:
    request = {"kind": kind, "details": details or {}}

    def go() -> dict:
        player = get_player(conn)
        if not player:
            return {"status": "refused", "kind": str(kind), "reason": "No protagonist is set."}
        try:
            out = engine_author(conn, int(player["player_actor_id"]), kind, details or {}, call_id)
        except AuthoringRefused as e:
            return {"status": "refused", "kind": str(kind), "reason": str(e), "reason_kind": getattr(e, "reason_kind", "contradiction")}
        for key, table in _ENTITY:
            if key in out:
                conn.execute("INSERT INTO authored_entities(call_id,kind,entity_table,entity_id,world_day) VALUES (?,?,?,?,?)",
                             (call_id, out["kind"], table, int(out[key]), store._day(conn)))
                break
        return out

    return store.run_once(conn, call_id, "author", request, go)
