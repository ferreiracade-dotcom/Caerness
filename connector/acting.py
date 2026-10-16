"""act: route structured intents through the engine's player-action pipeline."""
from __future__ import annotations

from connector import store
from engine.actions import PlayerActionProposal, shortest_route
from engine.player import get_player, sync_player_location
from engine.presence import actor_is_present_candidate
from engine.turns import resolve_turn_state

OPERATION_TYPES = ("pay", "hire", "lend", "demand", "attack", "trade", "order")
ACT_TYPES = ("observe", "speak", "investigate", "respond", "travel") + OPERATION_TYPES
RESPONSES = ("accept", "reject", "counter")
MAX_INTENT = 500


class StructuredActionProvider:
    """Builds the proposal from fields the caller already decided; no text parsing."""

    def __init__(self, action_type, *, target_actor_id=None, target_location_id=None, interaction_id=None,
                 response_choice=None, duration_days=0):
        self.action_type = action_type
        self.target_actor_id = target_actor_id
        self.target_location_id = target_location_id
        self.interaction_id = interaction_id
        self.response_choice = response_choice
        self.duration_days = duration_days

    def propose(self, conn, raw_text: str) -> PlayerActionProposal:
        sync_player_location(conn)
        player = get_player(conn)
        if not player:
            raise ValueError("No player is configured.")
        pid = int(player["player_actor_id"])
        here = int(player["current_location_id"]) if player["current_location_id"] is not None else None
        t = self.action_type
        if t == "observe":
            return PlayerActionProposal(raw_text, "observe", 1.0, purpose=raw_text)
        if t == "respond":
            if self.response_choice not in RESPONSES:
                raise ValueError("response_choice must be accept, reject or counter")
            return PlayerActionProposal(raw_text, "respond", 1.0, interaction_id=self.interaction_id,
                                        response_choice=self.response_choice, purpose=raw_text)
        if t == "travel":
            loc = conn.execute("SELECT id,name FROM locations WHERE id=?", (self.target_location_id,)).fetchone()
            base = dict(target_location_id=int(loc["id"]), target_location_name=str(loc["name"]), purpose=raw_text)
            route = shortest_route(conn, here, int(loc["id"])) if here is not None else None
            if route is None:
                return PlayerActionProposal(raw_text, "travel", 1.0, needs_interpretation=True,
                                            note="No known route to that place.", **base)
            days, ids, names = route
            return PlayerActionProposal(raw_text, "travel", 1.0, duration_days=days, route_location_ids=tuple(ids),
                                        route_location_names=tuple(names), **base)
        actor = conn.execute("SELECT id,name,actor_type,current_location_id FROM actors WHERE id=?", (self.target_actor_id,)).fetchone()
        base = dict(target_actor_id=int(actor["id"]), target_actor_name=str(actor["name"]), purpose=raw_text)
        if t == "investigate":
            return PlayerActionProposal(raw_text, "investigate", 1.0, duration_days=max(1, int(self.duration_days or 1)), **base)
        # speak: same presence rule as the engine's heuristic provider
        if here is None:
            ok = False
        elif actor["actor_type"] == "institution":
            ok = actor["current_location_id"] is not None and int(actor["current_location_id"]) == here
        else:
            ok = actor_is_present_candidate(conn, int(actor["id"]), here, purpose=f"player_speak:{pid}:{int(actor['id'])}")
        return PlayerActionProposal(raw_text, "speak", 1.0, needs_interpretation=not ok,
                                    note="" if ok else "Target is not plausibly present for a direct conversation here.", **base)


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _refuse(action_type, summary, call_id) -> dict:
    return {"status": "refused", "action_type": str(action_type), "summary": summary, "operation_id": call_id}


def _validate(conn, action_type, intent, target_actor_id, target_location_id, interaction_id, response_choice) -> str | None:
    if action_type not in ACT_TYPES:
        return f"Unsupported action type; use one of {', '.join(ACT_TYPES)}."
    if not intent or not intent.strip() or len(intent) > MAX_INTENT:
        return f"intent must be 1-{MAX_INTENT} characters."
    player = get_player(conn)
    if not player:
        return "No protagonist is set."
    if action_type in ("speak", "investigate"):
        if target_actor_id is None or not conn.execute(
                "SELECT 1 FROM actors WHERE id=? AND status='active'", (target_actor_id,)).fetchone():
            return "Unknown or inactive target_actor_id."
    if action_type == "travel":
        if target_location_id is None or not conn.execute("SELECT 1 FROM locations WHERE id=?", (target_location_id,)).fetchone():
            return "Unknown target_location_id."
    if action_type == "respond":
        if response_choice not in RESPONSES:
            return "response_choice must be accept, reject or counter."
        if interaction_id is None or not conn.execute(
                "SELECT 1 FROM interactions WHERE id=? AND status='pending' AND recipient_actor_id=?",
                (interaction_id, int(player["player_actor_id"]))).fetchone():
            return "No such pending interaction awaiting the protagonist's answer."
    return None


def act(conn, call_id: str, action_type: str, intent: str, *, target_actor_id: int | None = None,
        target_location_id: int | None = None, interaction_id: int | None = None,
        response_choice: str | None = None, duration_days: int = 0,
        details: dict | None = None) -> dict:
    request = {"action_type": action_type, "intent": intent, "target_actor_id": target_actor_id,
               "target_location_id": target_location_id, "interaction_id": interaction_id,
               "response_choice": response_choice, "duration_days": duration_days, "details": details or {}}

    def go() -> dict:
        problem = _validate(conn, action_type, intent, target_actor_id, target_location_id, interaction_id, response_choice)
        if problem:
            return _refuse(action_type, problem, call_id)
        if action_type in OPERATION_TYPES:
            from engine import player_operations
            me = int(get_player(conn)["player_actor_id"])
            out = player_operations.execute(conn, me, action_type, target_actor_id=target_actor_id,
                                            details=details or {}, intent=intent.strip())
            summary = " ".join(str(out.get("summary", "")).split())
            res = {k: v for k, v in out.items() if v is not None and k != "summary"}
            res.update({"status": out["status"], "action_type": action_type,
                        "summary": summary if len(summary) <= 600 else summary[:599] + "…",
                        "elapsed_days": 0, "day_started": _day(conn), "day_ended": _day(conn), "operation_id": call_id})
            return res
        provider = StructuredActionProvider(
            action_type, target_actor_id=target_actor_id, target_location_id=target_location_id,
            interaction_id=interaction_id, response_choice=response_choice, duration_days=duration_days)
        turn = resolve_turn_state(conn, intent.strip(), action_provider=provider)
        # The turn keeps two full scene packets the connector never reads; drop them to keep the save small.
        pk = conn.execute("SELECT pre_scene_packet_id a,post_scene_packet_id b FROM turns WHERE id=?", (turn["turn_id"],)).fetchone()
        for sid in (pk["a"], pk["b"]):
            if sid is not None:
                conn.execute("DELETE FROM scene_packets WHERE id=?", (sid,))
        res = turn["action_result"]
        summary = " ".join(str(res["summary"]).split())
        return {"status": res["status"], "action_type": res["action_type"],
                "summary": summary if len(summary) <= 600 else summary[:599] + "…",
                "day_started": turn["day_started"], "day_ended": turn["day_ended"],
                "elapsed_days": turn["elapsed_days"], "operation_id": call_id, "turn_id": turn["turn_id"]}

    return store.run_once(conn, call_id, "act", request, go)
