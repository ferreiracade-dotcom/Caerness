"""A named man answers a damaging claim about himself (information phase 1b, spec 7.5), through the organisation choice provider.

He hears what is said of him (the claims layer lets a subject hear it: from his people, or told by others) and a damaging claim puts an
item on his list. He weighs it by the same drivers as anyone: how much it damages him, how formidable he is held to be (a man held weak has
more reason to answer), his temper. The baseline "carry on" stands for ignoring it; he may answer it (lean on the man he had it from) or go
quiet (withdraw his display). Nothing here knows the protagonist: the item is offered to any seated man; the GM decides for the one he plays.
"""
from __future__ import annotations

import json
import sqlite3

from . import bearing as B
from . import claims
from .org_choices import register_agenda_action, register_executor
from .org_motives import _fig as figure
from .orgs import add_agenda, clamp01, is_living, resolve_agenda
from .relationships import adjust_relationship

KIND = "answer_name"


def _utility(conn, x: float) -> float:
    return float(figure(conn, "org_choice_utility_base", default=8.0)) + float(figure(conn, "org_choice_utility_span", default=10.0)) * clamp01(x)


def _drive(conn, actor: int, trait: str) -> float:
    r = conn.execute(f"SELECT {trait} FROM actor_drives WHERE actor_id=?", (int(actor),)).fetchone()
    return float(r[0]) if r is not None else 0.5


def hears_of_himself(conn, claim_id: int, day: int) -> None:
    """A damaging claim about a man reached him: it goes on his list once (if he has a place in an organisation, where the choice is offered)."""
    if not B.enabled(conn):
        return
    c = conn.execute("SELECT * FROM claims WHERE id=?", (int(claim_id),)).fetchone()
    if c is None or float(c["valence"]) >= 0 or int(c["holder_id"]) != int(c["subject_actor_id"]) or not B.seats(conn, int(c["holder_id"])):
        return
    if conn.execute("SELECT 1 FROM org_agenda WHERE actor_id=? AND kind=? AND status='open' AND json_extract(metadata_json,'$.claim')=?", (int(c["holder_id"]), KIND, int(claim_id))).fetchone():
        return
    add_agenda(conn, int(c["holder_id"]), KIND, int(day), subject_kind="actor", subject_id=c["source_ref"], metadata={"claim": int(claim_id)})


def offers(conn, actor: int, item, day: int) -> list[dict]:
    meta = json.loads(item["metadata_json"] or "{}")
    c = conn.execute("SELECT * FROM claims WHERE id=?", (int(meta.get("claim", 0)),)).fetchone()
    if c is None:  # it has faded from what is held
        resolve_agenda(conn, int(item["id"]), int(day))
        return []
    damage = clamp01(abs(float(c["valence"])) * claims._eff(conn, c, int(day)) * B.fig(conn, "bad_weight"))
    weak = (1.0 - claims.deterrence(conn, int(actor))) / 2.0  # a man held weak has more reason to answer
    base = B.fig(conn, "answer_base")
    teller = c["source_ref"]
    out = []
    payload = {"claim": int(c["id"]), "agenda_id": int(item["id"])}
    if teller is not None and int(teller) != int(actor) and is_living(conn, int(teller)):
        out.append({"kind": "answer_claim", "utility": _utility(conn, base * damage * (0.5 + _drive(conn, actor, "aggression")) * (0.5 + weak)),
                    "rationale": f"Weighs answering what {B.name_of(conn, teller)} let out: {c['text'][:80]}", "payload": {**payload, "teller": int(teller)},
                    "target_actor_id": int(teller), "risk": 0.4})
    out.append({"kind": "go_quiet", "utility": _utility(conn, base * damage * (1.0 - _drive(conn, actor, "risk_tolerance"))),
                "rationale": f"Weighs keeping his head down over: {c['text'][:80]}", "payload": payload})
    return out


def execute_answer(conn, actor: int, kind: str, payload: dict, day: int) -> dict:
    teller = int(payload["teller"])
    if not is_living(conn, teller):
        return {"summary": "The man was already gone.", "blocked": True}
    adjust_relationship(conn, teller, actor, int(day), fear_delta=B.fig(conn, "answer_fear"), resentment_delta=B.fig(conn, "answer_resent"), trust_delta=-B.fig(conn, "answer_trust"))
    eid = B._event(conn, int(day), "answered_talk", f"{B.name_of(conn, actor)} leans on {B.name_of(conn, teller)} over talk",
                   f"{B.name_of(conn, actor)} answered what {B.name_of(conn, teller)} had been saying of him.", actor)
    conn.execute("INSERT OR IGNORE INTO event_targets(event_id,actor_id,impact) VALUES (?,?,?)", (eid, teller, "answered"))
    conn.execute("INSERT OR IGNORE INTO event_witnesses(event_id,actor_id,witness_type,confidence,learned_day) VALUES (?,?,?,?,?)", (eid, teller, "target", 1.0, int(day)))
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))
    return {"summary": f"{B.name_of(conn, actor)} answered {B.name_of(conn, teller)}."}


def execute_quiet(conn, actor: int, kind: str, payload: dict, day: int) -> dict:
    internal = tuple(B._INTERNAL)
    conn.execute("UPDATE bearing_marks SET status='quiet' WHERE actor_id=? AND status='active' AND kind NOT IN (%s)" % ",".join("?" * len(internal)), (int(actor), *internal))
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))
    return {"summary": f"{B.name_of(conn, actor)} went quiet."}


register_agenda_action(KIND, offers)
register_executor("answer_claim", execute_answer)
register_executor("go_quiet", execute_quiet)
