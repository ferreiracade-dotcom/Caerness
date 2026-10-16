"""advance: pass time through the engine's time-skip runner, capped per call."""
from __future__ import annotations

from connector import store
from engine.player import get_player
from engine.timeskip import prepare_time_skip, resolve_time_skip

MAX_ADVANCE_DAYS = 30


def _clip(text, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def advance(conn, call_id: str, days: int, purpose: str) -> dict:
    if not isinstance(days, int) or days < 1:
        raise ValueError("days must be an integer >= 1")

    def go() -> dict:
        player = get_player(conn)
        if not player:
            raise ValueError("No protagonist is set.")
        me = int(player["player_actor_id"])
        run_days = min(days, MAX_ADVANCE_DAYS)
        run_id = prepare_time_skip(conn, me, run_days, interruption_policy="meaningful")
        run = resolve_time_skip(conn, run_id)
        start, end = int(run["start_day"]), int(run["actual_end_day"])
        interrupted = run["status"] == "interrupted"
        noticed = [_clip(r[0], 140) for r in conn.execute(
            """SELECT belief_text FROM knowledge WHERE knower_actor_id=? AND learned_day>? AND learned_day<=?
               ORDER BY learned_day DESC,id DESC LIMIT 8""", (me, start, end))]
        out = {"summary": _clip((run.get("summary") or {}).get("player_summary", ""), 300),
               "day_started": start, "day_ended": end, "elapsed_days": end - start,
               "interrupted": interrupted, "noticed": noticed, "operation_id": call_id}
        if interrupted and run["interruptions"]:
            out["interruption"] = _clip(run["interruptions"][0]["reason"], 300)
        if days > end - start:  # an interruption also leaves the rest of the request undone
            out["remaining_days"] = days - (end - start)
        return out

    return store.run_once(conn, call_id, "advance", {"days": days, "purpose": purpose}, go)
