"""act: the protagonist does something with consequences. Free-form operations and the named shortcuts share one door."""
from __future__ import annotations

import re

from connector import store
from engine.actions import PlayerActionProposal, explain_no_route, nearest_on, shortest_route
from engine.player import get_player, sync_player_location
from engine import company
from engine.turns import resolve_turn_state

OPERATION_TYPES = ("pay", "hire", "lend", "demand", "attack", "trade", "order")
ACT_TYPES = ("observe", "speak", "investigate", "respond", "travel") + OPERATION_TYPES
RESPONSES = ("accept", "reject", "counter")
MAX_INTENT = 1000
_FORMAT = re.compile(r"must be|Say |Name |not understood|give a number|holder must|unknown (business|crew|outfit|household|person|institution|polity|actor)|"
                     r"count must|men must|Give the rate|nothing is known by|more than one thing fits|Unknown or inactive|Unknown target|No such pending|no living person named", re.I)


class StructuredActionProvider:
    """Builds the proposal from fields the caller already decided; no text parsing."""

    def __init__(self, action_type, *, target_actor_id=None, target_location_id=None, interaction_id=None,
                 response_choice=None, duration_days=0, changes=None):
        self.action_type = action_type
        self.target_actor_id = target_actor_id
        self.target_location_id = target_location_id
        self.interaction_id = interaction_id
        self.response_choice = response_choice
        self.duration_days = duration_days
        self.changes = changes
        self.arrival_note = ""

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
        if t == "wait":
            return PlayerActionProposal(raw_text, "wait", 1.0, duration_days=max(1, int(self.duration_days or 1)), purpose=raw_text)
        if t == "respond":
            if self.response_choice not in RESPONSES:
                raise ValueError("response_choice must be accept, reject or counter")
            return PlayerActionProposal(raw_text, "respond", 1.0, interaction_id=self.interaction_id,
                                        response_choice=self.response_choice, purpose=raw_text, changes=self.changes)
        if t == "travel":
            loc = conn.execute("SELECT id,name FROM locations WHERE id=?", (self.target_location_id,)).fetchone()
            aim = int(loc["id"])
            near = nearest_on(conn, here, aim) if here is not None else None
            if near is not None:  # a region, sea or river: go to the nearest settlement, pass or port on it
                self.arrival_note = near[1]
                aim = near[0]
                loc = conn.execute("SELECT id,name FROM locations WHERE id=?", (aim,)).fetchone()
            base = dict(target_location_id=int(loc["id"]), target_location_name=str(loc["name"]), purpose=raw_text)
            route = shortest_route(conn, here, int(loc["id"])) if here is not None else None
            if route is None:
                return PlayerActionProposal(raw_text, "travel", 1.0, needs_interpretation=True,
                                            note=explain_no_route(conn, here, int(loc["id"])), **base)
            days, ids, names = route
            return PlayerActionProposal(raw_text, "travel", 1.0, duration_days=days, route_location_ids=tuple(ids),
                                        route_location_names=tuple(names), **base)
        actor = conn.execute("SELECT id,name,actor_type,current_location_id FROM actors WHERE id=?", (self.target_actor_id,)).fetchone()
        base = dict(target_actor_id=int(actor["id"]), target_actor_name=str(actor["name"]), purpose=raw_text)
        if t == "investigate":
            return PlayerActionProposal(raw_text, "investigate", 1.0, duration_days=max(1, int(self.duration_days or 1)), **base)
        # speak: whoever the scene shows, or who is with them, can be spoken to
        if here is None:
            ok = False
        elif actor["actor_type"] == "institution":
            ok = actor["current_location_id"] is not None and int(actor["current_location_id"]) == here
        else:
            ok = company.in_earshot(conn, pid, int(actor["id"]))
        return PlayerActionProposal(raw_text, "speak", 1.0, needs_interpretation=not ok,
                                    note="" if ok else "Target is not plausibly present for a direct conversation here.", **base)


def _destination(conn, actor, location, details) -> tuple[int | None, tuple[int, ...]]:
    """Where a journey goes and who is met there: a place, else the business named, else where a person is."""
    if location is not None:
        return int(location), ()
    raw = str((details or {}).get("business") or "").strip()
    if raw:
        ref = raw.partition(":")[2] if raw.startswith("business:") else raw
        row = conn.execute("""SELECT id,location_id,owner_actor_id FROM civilian_enterprises
                              WHERE (CAST(id AS TEXT)=? OR lower(name)=lower(?)) AND status IN ('active','strained','insolvent')
                              ORDER BY id LIMIT 1""", (ref, ref)).fetchone()
        if row is None or row["location_id"] is None:
            return None, ()
        there = [r[0] for r in conn.execute("SELECT actor_id FROM enterprise_staff WHERE enterprise_id=? AND status='active'", (row["id"],))]
        return int(row["location_id"]), tuple(int(x) for x in (row["owner_actor_id"], *there) if x is not None)
    if actor is not None:
        row = conn.execute("SELECT current_location_id,home_location_id FROM actors WHERE id=? AND status='active'", (actor,)).fetchone()
        if row:
            at = row[0] if row[0] is not None else row[1]
            return (int(at) if at is not None else None), (int(actor),)
    return None, ()


def _companions(details) -> list[int | None]:
    got = (details or {}).get("with") or []
    got = got if isinstance(got, list) else [got]
    out: list[int | None] = []
    for x in got:
        raw = str(x).partition(":")[2] if str(x).startswith("actor:") else str(x)
        out.append(int(raw) if raw.isdigit() else None)
    return out


def _travel(conn, me: int, call_id: str, intent: str, dest, met, details) -> dict:
    """The journey; those travelling together arrive together, and whoever it was made to see is there."""
    with_them = [x for x in _companions(details) if x is not None and x != me]
    res = _named(conn, me, call_id, "travel", intent, None, dest, None, None, 0, details)
    if res.get("status") != "applied":
        return res
    company.leave_all(conn)
    arrived = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
    for other in with_them:
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (arrived, other))
    waiting = [x for x in met if conn.execute("SELECT 1 FROM actors WHERE id=? AND current_location_id=?", (x, arrived)).fetchone()
               or (details or {}).get("business")]
    company.join(conn, [*with_them, *waiting])
    return res


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _refuse(action_type, summary, call_id, reason_kind="input_gap") -> dict:
    return {"status": "refused", "action_type": str(action_type), "summary": summary, "reason_kind": reason_kind, "operation_id": call_id}


def _validate(conn, action_type, intent, target_actor_id, target_location_id, interaction_id, response_choice, details) -> str | None:
    if not intent or not intent.strip() or len(intent) > MAX_INTENT:
        return f"intent must be 1-{MAX_INTENT} characters."
    player = get_player(conn)
    if not player:
        return "No protagonist is set."
    if action_type == "speak":
        if target_actor_id is None or not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (target_actor_id,)).fetchone():
            return "Unknown or inactive target_actor_id."
    if action_type == "investigate":
        d = details or {}
        has_subject = any(d.get(k) for k in ("subject", "business", "outfit", "location"))
        if target_actor_id is not None and not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (target_actor_id,)).fetchone():
            return "Unknown or inactive target_actor_id."
        if target_actor_id is None and target_location_id is None and not has_subject:
            return "Say what is looked into: target_actor_id, target_location_id, or details.subject (a question, business or outfit)."
    if action_type == "travel":
        dest, _ = _destination(conn, target_actor_id, target_location_id, details)
        if dest is None or not conn.execute("SELECT 1 FROM locations WHERE id=?", (dest,)).fetchone():
            return "Unknown destination: give target_location_id, or target_actor_id or details.business to go to them."
        me = int(player["player_actor_id"])
        for other in _companions(details):
            if other is None or not company.in_earshot(conn, me, other):
                return "details.with must be a list of actor ids of people who are here now."
    if action_type == "respond":
        if response_choice not in RESPONSES:
            return "response_choice must be accept, reject or counter."
        if interaction_id is None or not conn.execute(
                "SELECT 1 FROM interactions WHERE id=? AND status='pending' AND recipient_actor_id=?",
                (interaction_id, int(player["player_actor_id"]))).fetchone():
            return "No such pending interaction awaiting the protagonist's answer."
    return None


def _clip(text, n=600) -> str:
    summary = " ".join(str(text or "").split())
    return summary if len(summary) <= n else summary[: n - 1] + "…"


def _classify(res: dict) -> dict:
    """A refusal says what kind it is: a contradiction the world holds (stage it), or an input gap (put it differently and retry)."""
    if res.get("status") == "refused" and "reason_kind" not in res:
        res["reason_kind"] = "input_gap" if _FORMAT.search(str(res.get("summary", ""))) else "contradiction"
    return res


def _settled(conn, me: int) -> list[dict]:
    from engine import free_operation
    return free_operation.settle_due(conn, me)


def act(conn, call_id: str, action_type: str, intent: str, *, target_actor_id: int | None = None,
        target_location_id: int | None = None, interaction_id: int | None = None,
        response_choice: str | None = None, duration_days: int = 0,
        details: dict | None = None) -> dict:
    request = {"action_type": action_type, "intent": intent, "target_actor_id": target_actor_id,
               "target_location_id": target_location_id, "interaction_id": interaction_id,
               "response_choice": response_choice, "duration_days": duration_days, "details": details or {}}

    def go() -> dict:
        problem = _validate(conn, action_type, intent, target_actor_id, target_location_id, interaction_id, response_choice, details)
        if problem:
            return _refuse(action_type, problem, call_id)
        me = int(get_player(conn)["player_actor_id"])
        dest, met = target_location_id, ()
        if action_type == "travel":
            dest, met = _destination(conn, target_actor_id, target_location_id, details)
        try:  # the world package's text vetoes: a real town that does not exist here, a dated rule not yet in force
            from engine import veto
            veto.check_world_text(conn, intent, details or {})
        except veto.Contradiction as e:
            return _refuse(action_type, str(e), call_id, "contradiction")
        if action_type in OPERATION_TYPES:
            from engine import player_operations
            out = player_operations.execute(conn, me, action_type, target_actor_id=target_actor_id,
                                            details={**(details or {}), "_call_id": call_id}, intent=intent.strip())
            res = {k: v for k, v in out.items() if v is not None and k != "summary"}
            res.update({"status": out["status"], "action_type": action_type, "summary": _clip(out.get("summary")),
                        "elapsed_days": 0, "day_started": _day(conn), "day_ended": _day(conn), "operation_id": call_id})
            if out["status"] != "refused" and target_actor_id is not None and company.in_earshot(conn, me, target_actor_id):
                company.join(conn, [target_actor_id])
            return _classify(res)
        if action_type not in ACT_TYPES:
            return _free(conn, me, call_id, action_type, intent, target_actor_id, target_location_id, details)
        if action_type == "travel":
            return _travel(conn, me, call_id, intent, dest, met, details)
        return _named(conn, me, call_id, action_type, intent, target_actor_id, target_location_id, interaction_id,
                      response_choice, duration_days, details)

    return store.run_once(conn, call_id, "act", request, go)


def _free(conn, me, call_id, action_type, intent, target_actor_id, target_location_id, details) -> dict:
    """Any intent: the engine maps it, judges it at scale, and returns what happened, including partial results."""
    from engine import free_operation
    f = dict(details or {})
    if target_actor_id is not None and not f.get("target") and not f.get("targets"):
        f["target"] = f"actor:{target_actor_id}"
    if target_location_id is not None:
        f["targets"] = [*(f.get("targets") or []), f"location:{target_location_id}"]
    hint = f.get("kind") or (action_type if action_type not in ("operation", "do", "act") else None)
    out = free_operation.run(conn, me, intent.strip(), f, call_id, hint)
    if out.get("status") == "delegate" and out.get("delegate") == "travel":
        met = (out["target_actor_id"],) if out.get("target_actor_id") else ()
        return _travel(conn, me, call_id, intent, out["target_location_id"], met, details)
    res = {k: v for k, v in out.items() if v is not None and k != "summary"}
    res.update({"action_type": "operation", "summary": _clip(out.get("summary")), "elapsed_days": 0, "day_started": _day(conn),
                "day_ended": _day(conn), "operation_id": call_id})
    return _classify(res)


def _named(conn, me, call_id, action_type, intent, target_actor_id, target_location_id, interaction_id, response_choice, duration_days, details) -> dict:
    d = details or {}
    kind = action_type
    subject_only = action_type == "investigate" and target_actor_id is None
    if subject_only:
        kind = "wait"
    provider = StructuredActionProvider(
        kind, target_actor_id=target_actor_id, target_location_id=target_location_id,
        interaction_id=interaction_id, response_choice=response_choice, duration_days=duration_days,
        changes=d.get("changes") if action_type == "respond" else None)
    turn = resolve_turn_state(conn, intent.strip(), action_provider=provider)
    # The turn keeps two full scene packets the connector never reads; drop them to keep the save small.
    pk = conn.execute("SELECT pre_scene_packet_id a,post_scene_packet_id b FROM turns WHERE id=?", (turn["turn_id"],)).fetchone()
    for sid in (pk["a"], pk["b"]):
        if sid is not None:
            conn.execute("DELETE FROM scene_packets WHERE id=?", (sid,))
    res = turn["action_result"]
    out = {"status": res["status"], "action_type": action_type if subject_only else res["action_type"], "summary": _clip(res["summary"]),
           "day_started": turn["day_started"], "day_ended": turn["day_ended"], "elapsed_days": turn["elapsed_days"],
           "operation_id": call_id, "turn_id": turn["turn_id"]}
    if provider.arrival_note:
        out["destination_note"] = provider.arrival_note
    if action_type == "speak" and res["status"] == "applied":
        company.join(conn, [target_actor_id])
        out["them"] = _them(conn, me, target_actor_id)  # before the talk adds to what they know
        out.update(_spoken(conn, me, target_actor_id, d, call_id))
    if action_type == "investigate" and res["status"] == "applied":
        out.update(_investigated(conn, me, target_actor_id, target_location_id, d, max(1, int(duration_days or 1)), call_id))
    if out["status"] == "applied" and action_type == "respond":
        done = _settled(conn, me)
        if done:
            out["settled"] = done
    return _classify(out)


def _spoken(conn, me, target, d, call_id) -> dict:
    """What he said becomes known to the other; what he asked is answered from what the other knows."""
    from engine import findings
    out: dict = {}
    tells = d.get("tells")
    if tells:
        tells = [tells] if isinstance(tells, str) else [str(t) for t in tells]
        findings.tell(conn, target, tells, source=me)
        out["told"] = len(tells)
    asks = d.get("asks")
    if asks:
        ans = findings.answers(conn, target, asks)
        if ans:
            findings.learn(conn, me, ans, key=f"asked:{call_id}", confidence=0.6)
            out["answers"] = ans
        else:
            out["answers"] = []
            out["note"] = "He has nothing to say on that; anything he says beyond it is the GM's to invent and note."
    return out


def _feeling(conn, who, me) -> str:
    """How one person stands toward another, in plain words."""
    from engine.relationships import relationship_view
    r = relationship_view(conn, who, me)
    said = [word for hit, word in (
        (r["stance"] >= 30, "warm to you"), (10 <= r["stance"] < 30, "friendly"), (-30 < r["stance"] <= -10, "cool toward you"),
        (r["stance"] <= -30, "hostile"), (r["trust"] >= 30, "trusts you"), (r["trust"] <= -20, "does not trust you"),
        (r["respect"] >= 30, "respects you"), (r["resentment"] >= 30, "resents you"), (r["fear"] >= 30, "is afraid of you"),
        (r["obligation"] >= 20, "feels in your debt")) if hit]
    if r["familiarity"] < 15:
        said.insert(0, "hardly knows you")
    return ", ".join(said) or "knows you, with no strong feeling either way"


def _them(conn, me, target) -> dict:
    """What the other person brings to the talk: their feeling toward the protagonist, what they want, what they have heard
    of the protagonist, and what stands open between the two."""
    mine = conn.execute("SELECT name FROM actors WHERE id=?", (me,)).fetchone()[0]
    wants = [str(r[0]) for r in conn.execute(
        "SELECT description FROM goals WHERE actor_id=? AND status='active' ORDER BY priority DESC,id LIMIT 3", (target,))]
    heard = [_clip(r[0], 200) for r in conn.execute(
        """SELECT belief_text FROM knowledge WHERE knower_actor_id=? AND instr(belief_text,?)>0 AND learned_day>=?
           AND belief_text NOT LIKE '%approach.' ORDER BY learned_day DESC,id DESC LIMIT 3""",
        (target, str(mine).split()[0], _day(conn) - 180))]
    pair = (me, target, target, me)
    owed = (f"person:{me}", f"person:{target}", f"person:{target}", f"person:{me}")
    open_between = [f"awaiting an answer: {_clip(r[0], 160)}" for r in conn.execute(
        """SELECT i.interaction_type||' from '||a.name FROM interactions i JOIN actors a ON a.id=i.proposer_actor_id
           WHERE i.status='pending' AND ((i.proposer_actor_id=? AND i.recipient_actor_id=?) OR (i.proposer_actor_id=? AND i.recipient_actor_id=?))""", pair)]
    open_between += [_clip(r[0], 160) for r in conn.execute(
        """SELECT summary FROM life_matters WHERE status='open' AND summary<>'' AND
           ((subject_actor_id=? AND other_actor_id=?) OR (subject_actor_id=? AND other_actor_id=?)) LIMIT 3""", pair)]
    from engine.money_records import fmt
    open_between += [f"{r[0]}: {fmt(conn, r[1])}, not settled" for r in conn.execute(
        """SELECT job,quote FROM deals WHERE status IN ('quoted','open') AND
           ((customer_ref=? AND provider_ref=?) OR (customer_ref=? AND provider_ref=?)) LIMIT 3""", owed)]
    open_between += [str(r[0]) for r in conn.execute(
        """SELECT description FROM obligations WHERE status='active' AND
           ((actor_id=? AND counterparty_actor_id=?) OR (actor_id=? AND counterparty_actor_id=?)) LIMIT 3""", pair)]
    return {"toward_you": _feeling(conn, target, me), **({"wants": wants} if wants else {}),
            **({"has_heard": heard} if heard else {}), **({"open_between": open_between} if open_between else {})}


def _investigated(conn, me, actor, location, d, days, call_id) -> dict:
    from engine import findings

    def ref(key, prefix):
        raw = str(d.get(key) or "").partition(":")[2] or str(d.get(key) or "")
        return int(raw) if raw.isdigit() else None
    if actor is None and location is None and not any(d.get(k) for k in ("business", "outfit", "location")):
        got = findings.investigate(conn, me, text=str(d.get("subject") or ""), days=days, seed_key=call_id)
    else:
        got = findings.investigate(conn, me, actor=actor, location=location if actor is None else None,
                                   business=ref("business", "business:"), outfit=ref("outfit", "outfit:"), text=str(d.get("subject") or ""),
                                   days=days, seed_key=call_id)
    found = got["found"][:8]
    if found:
        findings.learn(conn, me, found, key=f"found:{call_id}", confidence=0.65)
        if actor is not None:  # the engine's placeholder note ("Investigation concerning X: <your purpose>") becomes what was actually found
            conn.execute("UPDATE knowledge SET belief_text=? WHERE knower_actor_id=? AND fact_key LIKE 'investigation:%' AND learned_day=? AND belief_text LIKE 'Investigation concerning%'",
                         (f"Looked into {got['subject']}: " + " ".join(found[:3])[:260], me, _day(conn)))
    return {"found": found, "subject": got["subject"], **({} if found else {"nothing_found": True})}
