"""The shared business layer's makers for the intake's `holding` and `arrangement` shapes.

A holding that names one of the package's place kinds becomes a place (an owner, upkeep, a condition that moves); one that is
still being built goes through a venture and takes its place when the venture completes. An arrangement between two people
with money in it becomes an agreement term with its breach path. Anything these cannot read stays on the floor and bumps a gap,
as before. The place's own upkeep and a term's own payments are the layer's, so the weekly held-thing tick leaves them alone.
No world words here: the kinds, words and defaults all come from the package's business data.
"""
from __future__ import annotations

import json
import re

from . import agreement_terms, business_data, intake, places, ventures
from .intake import Proposal, Shape


def _place_kind(conn, p: Proposal) -> str | None:
    data = business_data.load(conn)
    if data is None:
        return None
    text = f"{p.kind_text} {p.what}".lower()
    for word in sorted(data.get("place_kinds") or {}, key=len, reverse=True):
        if re.search(r"(?<![a-z])" + re.escape(word.replace("_", " ")) + r"(?:s|es)?(?![a-z])", text.replace("_", " ")):
            return word
    return None


def _upkeep_30(p: Proposal) -> float | None:
    return round(p.upkeep_weekly * 30.0 / 7.0, 2) if p.upkeep_weekly > 0 else None


def make_holding(conn, me: int, p: Proposal, call_id: str) -> dict:
    kind = _place_kind(conn, p)
    if kind is None or p.location_id is None:
        return {}  # nothing here says what it is or where: it stays on the floor, with its gap
    owner_ref = f"person:{int(p.owner)}"
    straw = p.details.get("legal_owner_actor_id")
    straw_ref = f"person:{int(straw)}" if isinstance(straw, int) and not isinstance(straw, bool) else None
    day = int(p.start_day)
    if p.ready_in_days:
        vk = business_data.default(conn, "build_venture_kind")
        if vk is not None:
            pay = {"kind": "place", "place": {"name": p.what[:80], "place_kind": kind, "location_id": int(p.location_id),
                                              "owner_ref": owner_ref, "legal_owner_ref": straw_ref}}
            pid = ventures.start_venture(conn, kind=vk, title=p.what[:80], backer_ref=owner_ref, location_id=int(p.location_id),
                                         budget_usd=float(p.start_cost), day=day, payoff=pay)
            st = json.loads(conn.execute("SELECT payoff_json FROM venture_details WHERE project_id=?", (pid,)).fetchone()[0])
            st["prepaid"] = True  # take_in already drew the money
            st["held_call_id"] = str(call_id)
            conn.execute("UPDATE venture_details SET payoff_json=? WHERE project_id=?", (json.dumps(st, sort_keys=True), pid))
            return {"backing_table": "venture_details", "backing_id": pid}
    bid = places.make_place(conn, name=p.what[:80], place_kind=kind, location_id=int(p.location_id), owner_ref=owner_ref, day=day,
                            legal_owner_ref=straw_ref)
    up = _upkeep_30(p)
    if up is not None:
        conn.execute("UPDATE place_details SET upkeep_usd_30=? WHERE building_id=?", (up, bid))
    return {"backing_table": "place_details", "backing_id": bid}


def make_arrangement(conn, me: int, p: Proposal, call_id: str) -> dict:
    if business_data.load(conn) is None or not p.people or (p.income_weekly <= 0 and p.upkeep_weekly <= 0):
        return {}
    other = f"person:{int(p.people[0])}"
    mine = f"person:{int(p.owner)}"
    if other == mine:
        return {}
    if p.income_weekly > 0:
        debtor, creditor, amount = other, mine, p.income_weekly
    else:
        debtor, creditor, amount = mine, other, p.upkeep_weekly
    word = business_data.default(conn, "breach_word")
    for c in p.consequences:  # a package breach word named in what the GM said the breach does
        for w in (business_data.load(conn).get("breach_words") or {}):
            if w.replace("_", " ") in c.lower():
                word = w
    if word is None:
        return {}
    grace = int(business_data.default(conn, "grace_days") or 0)
    day = int(p.start_day)
    tid = agreement_terms.add_term(conn, ref_kind="intake", ref_id=None, debtor_ref=debtor, creditor_ref=creditor, amount_usd=float(amount),
                                   first_due_day=day + 7, every_days=7, grace_days=grace, breach_word=word, purpose=p.what[:120], day=day)
    return {"backing_table": "agreement_terms", "backing_id": tid}


def _on_venture_finish(conn, pid: int, outcome: str, reason: str | None, day: int) -> None:
    held = conn.execute("SELECT id FROM held_things WHERE backing_table='venture_details' AND backing_id=?", (int(pid),)).fetchone()
    if held is None:
        return
    if outcome == "completed":
        name = conn.execute("SELECT title FROM civilian_projects WHERE id=?", (int(pid),)).fetchone()[0]
        b = conn.execute("SELECT MAX(building_id) FROM place_details d JOIN buildings b ON b.id=d.building_id WHERE b.name=?", (name,)).fetchone()[0]
        if b is not None:
            conn.execute("UPDATE held_things SET backing_table='place_details',backing_id=?,status='active',updated_day=? WHERE id=?",
                         (int(b), int(day), int(held[0])))
            return
    conn.execute("UPDATE held_things SET status='ended',ended_reason=?,updated_day=? WHERE id=?",
                 (reason or "the build did not finish", int(day), int(held[0])))


def register() -> None:
    intake.register_shape(Shape("holding", (), (), make_holding, True))
    intake.register_shape(Shape("arrangement", (), (), make_arrangement, True))
    intake.OWN_MONEY_TABLES.update({"place_details": "upkeep", "agreement_terms": "all", "venture_details": "all"})
    if _on_venture_finish not in ventures.ON_FINISH:
        ventures.ON_FINISH.append(_on_venture_finish)
