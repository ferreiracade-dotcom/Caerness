"""Agenda votes, deals, tenders, approvals and ordinance effects (politics P1).

A body of an office (the council, a board) decides items. Each member votes by a weighed lean (never a rule): what his groups think
of the sponsor, whether the item names what they are angry about, his party's line, favours, money on him, a vote he promised, and his
conscience where the item is corrupt. The body's own data gives its quorum, its tie rule and what passes. A passed item writes the
effects the package allows it, and tells the groups how their own member voted. A promised vote broken runs the business layer's
breach path. All weights are package figures; no world words here.
"""
from __future__ import annotations

import json
import math
import random

from . import civic_patronage, civic_seams, design, electorate, offices, races
from .design import figure
from .world_package import package_for, politics_rules


def _rules(conn) -> dict:
    return politics_rules(package_for(conn))


def _f(conn, name, default: float = 0.0) -> float:
    return float(figure(conn, name, default)) if name else default


def _rng(conn, *key) -> random.Random:
    return random.Random(f"{design.run_seed(conn)}:civic:" + ":".join(str(k) for k in key))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _j(text, default):
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default


def _md(conn) -> dict:
    return _rules(conn).get("member_drivers") or {}


def item(conn, item_id: int):
    return conn.execute("SELECT * FROM civic_items WHERE id=?", (int(item_id),)).fetchone()


def _body(conn, key: str) -> dict:
    return offices._json(offices.office(conn, key)["body_json"], {})


# ---- items --------------------------------------------------------------------------------------------------------

def open_item(conn, body_office_key: str, item_kind: str, subject: dict, *, vote_day: int, day: int) -> int:
    """Put an item before a body. `subject` carries the sponsor (an actor), a title, the grievance words it names, `corrupt` when it
    is, and the effects it writes if it passes ({'effect_key', 'value', 'from_day', 'to_day'})."""
    kinds = _rules(conn).get("item_kinds") or {}
    if item_kind not in kinds:
        raise ValueError(f"unknown item kind {item_kind!r}")
    return int(conn.execute("INSERT INTO civic_items(body_office_key,item_kind,subject_json,opened_day,vote_day) VALUES (?,?,?,?,?)",
                            (body_office_key, item_kind, json.dumps(subject, sort_keys=True, default=str), int(day), int(vote_day))).lastrowid)


def _absent(conn, actor: int) -> str | None:
    st = conn.execute("SELECT status FROM actors WHERE id=?", (int(actor),)).fetchone()
    if st is None or st[0] != "active":
        return "not_living"
    if conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held' AND until_day IS NULL", (int(actor),)).fetchone():
        return "in_custody"
    return None


def _district_groups(conn, member: int, body_key: str) -> list:
    keys = [k for k in offices.offices_of(conn, member) if k != body_key]
    gs: dict[int, object] = {}
    for k in keys:
        for g in electorate._district_groups(conn, k):
            gs[int(g["id"])] = g
    return list(gs.values())


def _line(conn, member: int, sponsor: int | None) -> float:
    """+1 when the sponsor sits in the member's own organisation, -1 when in another that holds stakes, else 0."""
    if sponsor is None:
        return 0.0
    a, b = races.party_of(conn, member), races.party_of(conn, int(sponsor))
    if a is None or b is None:
        return 0.0
    return 1.0 if a == b else -1.0


def _money_on(conn, member: int, sponsor: int | None) -> float:
    if sponsor is None:
        return 0.0
    org = races.party_of(conn, int(sponsor))
    rows = conn.execute("SELECT weekly_usd,payer_kind,payer_id FROM org_arrangements WHERE official_actor_id=? AND status='active'", (int(member),)).fetchall()
    return sum(float(r[0]) for r in rows if (r[1] == "actor" and int(r[2]) == int(sponsor)) or (r[1] == "org" and org is not None and int(r[2]) == org))


def _deal(conn, item_id: int, member: int):
    return conn.execute("SELECT * FROM agreement_terms WHERE ref_kind='vote_deal' AND ref_id=? AND debtor_ref=? AND status='active' ORDER BY id LIMIT 1",
                        (int(item_id), f"person:{int(member)}")).fetchone()


def member_vote(conn, item_id: int, member: int, day: int, *, salt: str = "") -> tuple[str, dict]:
    """(vote, why): the lean's terms are kept in `why`, for the GM and for the test of any member, the protagonist included."""
    it = item(conn, item_id)
    sub = _j(it["subject_json"], {})
    absent = _absent(conn, member)
    if absent:
        return "absent", {"absent": absent}
    d = _md(conn)
    sponsor = sub.get("sponsor")
    groups = _district_groups(conn, int(member), it["body_office_key"])
    names = set(sub.get("grievances") or [])
    n = max(1, len(groups))
    regard = sum(electorate.regard(conn, int(g["id"]), int(sponsor), day) for g in groups) / n if sponsor is not None and groups else 0.0
    fit = sum(len(names & set(json.loads(g["grievances_json"] or "[]"))) for g in groups) / n if names and groups else 0.0
    drives = conn.execute("SELECT loyalty,pragmatism FROM actor_drives WHERE actor_id=?", (int(member),)).fetchone()
    loyalty, pragmatism = (float(drives[0]), float(drives[1])) if drives else (0.5, 0.5)
    favour = -civic_patronage.owed(conn, int(member), int(sponsor)) if sponsor is not None else 0.0  # owing the sponsor leans yes
    money = _money_on(conn, int(member), sponsor)
    deal = _deal(conn, item_id, member)
    terms = {"regard": _f(conn, d.get("regard")) * regard, "fit": _f(conn, d.get("fit")) * fit,
             "line": _f(conn, d.get("line")) * loyalty * _line(conn, int(member), sponsor), "favour": _f(conn, d.get("favour")) * favour,
             "money": _f(conn, d.get("money")) * math.log1p(max(0.0, money)), "deal": _f(conn, d.get("deal")) * (1.0 if deal else 0.0),
             "conscience": -_f(conn, d.get("conscience")) * (1.0 - pragmatism) * (1.0 if sub.get("corrupt") else 0.0),
             "noise": _rng(conn, item_id, member, salt).gauss(0.0, _f(conn, d.get("noise_sd")))}
    z = _f(conn, d.get("base")) + sum(terms.values())
    vote = "yes" if _rng(conn, item_id, member, "draw", salt).random() < _sigmoid(z) else "no"
    return vote, {**terms, "z": z, "deal": bool(deal)}


def pre_vote_deal(conn, item_id: int, member: int, counterparty: int, terms: dict, day: int) -> int:
    """The member promises the counterparty his vote for what he is given: a ledger entry he owes. Voting against it is a breach."""
    t = dict(terms or {})
    both = races.party_of(conn, int(member)) is not None and races.party_of(conn, int(counterparty)) is not None
    t.setdefault("breach_word", "between_orgs" if both else "grudge")
    t["ref_id"] = int(item_id)
    t.setdefault("vote", "yes")
    return civic_seams.ledger_entry(conn, int(member), int(counterparty), kind="vote_deal", terms=t, due_day=int(day), day=int(day))


def _tally(votes: dict[int, str]) -> tuple[int, int, int]:
    yes = sum(1 for v in votes.values() if v == "yes")
    no = sum(1 for v in votes.values() if v == "no")
    return yes, no, sum(1 for v in votes.values() if v == "abstain")


def _count(conn, it, members: list[int], day: int, salt: str = "") -> tuple[dict, dict]:
    votes, whys = {}, {}
    for m in members:
        votes[m], whys[m] = member_vote(conn, int(it["id"]), m, day, salt=salt)
    return votes, whys


def decide(conn, item_id: int, day: int) -> dict:
    """Count a due item: quorum, majority of those present, the body's tie rule. Writes the effects, holds the outcome, tells the groups."""
    it = item(conn, item_id)
    if it["status"] != "open":
        return _j(it["outcome_json"], {})
    body = _body(conn, it["body_office_key"])
    sub = _j(it["subject_json"], {})
    members = sorted({a for _, _, a in offices.members(conn, it["body_office_key"])})
    votes, whys = _count(conn, it, members, day)
    present = sum(1 for v in votes.values() if v != "absent")
    need = math.ceil(_f(conn, body.get("quorum_figure"), 0.5) * len(members))
    out: dict = {"members": len(members), "present": present}
    status, reason = "failed", None
    if present < need or not members:
        reason = "quorum"
    else:
        yes, no, _ = _tally(votes)
        if yes * 2 > present:
            status = "passed"
        elif yes * 2 == present:
            rule = body.get("tie_rule")
            out["tie"] = rule
            if rule == "chair_votes" and body.get("chair"):
                chair = offices.holder(conn, body["chair"])
                if chair is not None and _absent(conn, chair) is None:
                    v, w = member_vote(conn, item_id, chair, day, salt="chair")
                    votes[chair], whys[chair] = v, w
                    status = "passed" if v == "yes" else "failed"
                else:
                    reason = "tie"
            elif rule == "re_vote":
                votes2, whys2 = _count(conn, it, members, day, salt="revote")
                yes2, _, _ = _tally(votes2)
                present2 = sum(1 for v in votes2.values() if v != "absent")
                votes, whys = votes2, whys2
                status = "passed" if yes2 * 2 > present2 else "failed"
                reason = None if status == "passed" else "tie"
            else:
                reason = "tie"
    yes, no, _ = _tally(votes)
    out.update(yes=yes, no=no, reason=reason)
    for m, v in votes.items():
        conn.execute("INSERT OR REPLACE INTO civic_item_votes(item_id,member_actor_id,vote,why_json) VALUES (?,?,?,?)",
                     (int(item_id), int(m), v, json.dumps(whys[m], sort_keys=True, default=str)))
        deal = _deal(conn, item_id, m)
        if deal is not None and v != "absent" and v != str(_j(deal["purpose"], {}).get("vote", "yes")):
            civic_seams.ledger_breach(conn, int(deal["id"]), int(m), int(day), f"voted {v} on item {item_id}")
    conn.execute("UPDATE civic_items SET status=?,outcome_json=? WHERE id=?", (status, json.dumps(out, sort_keys=True), int(item_id)))
    title = sub.get("title") or it["item_kind"]
    if status == "passed":
        for ef in sub.get("effects") or []:
            conn.execute("INSERT INTO civic_effects(source_kind,source_id,effect_key,value_json,from_day,to_day) VALUES ('item',?,?,?,?,?)",
                         (int(item_id), ef["effect_key"], json.dumps(ef.get("value"), sort_keys=True), int(ef.get("from_day", day)), ef.get("to_day")))
    people = [int(sub["sponsor"])] if sub.get("sponsor") is not None else [m for m in members if votes.get(m) == "yes"][:1]
    if people:
        civic_seams.hold_outcome(conn, what=f"{it['body_office_key']} {status}: {title}", people=people, dates={"start_day": int(day)},
                                 consequences=[f"{yes} yes, {no} no" + (f" ({reason})" if reason else "")], day=int(day))
    _tell_groups(conn, it, sub, votes, day)
    return out


def _tell_groups(conn, it, sub: dict, votes: dict[int, str], day: int) -> None:
    names = set(sub.get("grievances") or [])
    if not names:
        return
    for m, v in votes.items():
        if v not in ("yes", "no"):
            continue
        for g in _district_groups(conn, m, it["body_office_key"]):
            if names & set(json.loads(g["grievances_json"] or "[]")):
                civic_seams.tell_group(conn, int(g["id"]), int(m), f"voted {v} on {sub.get('title') or it['item_kind']}", source="record", confidence=0.8,
                                       valence=0.3 if v == "yes" else -0.3, day=int(day))


# ---- tenders ------------------------------------------------------------------------------------------------------

def open_tender(conn, office_key: str, spec: dict, *, close_day: int, day: int) -> int:
    s = dict(spec or {})
    s.setdefault("bids", [])
    return open_item(conn, office_key, "tender", s, vote_day=close_day, day=day)


def add_bid(conn, item_id: int, bidder: int, price: float, *, day: int) -> None:
    it = item(conn, item_id)
    sub = _j(it["subject_json"], {})
    sub.setdefault("bids", []).append({"bidder": int(bidder), "price": float(price), "day": int(day)})
    conn.execute("UPDATE civic_items SET subject_json=? WHERE id=?", (json.dumps(sub, sort_keys=True), int(item_id)))


def award_tender(conn, item_id: int, day: int) -> dict:
    """Each member leans to the bid that is cheaper than the field's, from his own party, owed favours, or paying him; the winner has the
    most members. Nothing guarantees the cheapest, nothing guarantees a kickback."""
    it = item(conn, item_id)
    sub = _j(it["subject_json"], {})
    bids = sub.get("bids") or []
    if not bids:
        conn.execute("UPDATE civic_items SET status='void',outcome_json=? WHERE id=?", (json.dumps({"reason": "no bids"}), int(item_id)))
        return {"winner": None}
    t = (_md(conn).get("tender") or {})
    mean = sum(math.log(max(1.0, b["price"])) for b in bids) / len(bids)
    members = sorted({a for _, _, a in offices.members(conn, it["body_office_key"])})
    tally: dict[int, int] = {int(b["bidder"]): 0 for b in bids}
    for m in members:
        if _absent(conn, m):
            continue
        scores = []
        for b in bids:
            bd = int(b["bidder"])
            kb = _money_on(conn, m, bd)
            same = 1.0 if races.party_of(conn, m) is not None and races.party_of(conn, m) == races.party_of(conn, bd) else 0.0
            z = (_f(conn, t.get("price")) * (mean - math.log(max(1.0, b["price"]))) + _f(conn, t.get("tie")) * same
                 - _f(conn, t.get("favour")) * civic_patronage.owed(conn, m, bd) + _f(conn, t.get("kickback")) * (1.0 if kb > 0 else 0.0)
                 + _rng(conn, item_id, m, bd, "bid").gauss(0.0, _f(conn, _md(conn).get("noise_sd"))))
            scores.append(z)
        top = max(scores)
        w = [math.exp(s - top) for s in scores]
        u = _rng(conn, item_id, m, "pick").random() * sum(w)
        acc = 0.0
        for b, wi in zip(bids, w):
            acc += wi
            if u <= acc:
                tally[int(b["bidder"])] += 1
                break
    best = max(tally.values())
    leaders = sorted(b for b, n in tally.items() if n == best)
    winner = leaders[0] if len(leaders) == 1 else _rng(conn, item_id, "tie").choice(leaders)
    out = {"winner": winner, "votes": {str(k): v for k, v in tally.items()}}
    conn.execute("UPDATE civic_items SET status='passed',outcome_json=? WHERE id=?", (json.dumps(out, sort_keys=True), int(item_id)))
    civic_seams.hold_outcome(conn, what=f"{it['body_office_key']} awarded {sub.get('title') or 'a contract'}", people=[winner], dates={"start_day": int(day)},
                             consequences=[f"to bidder {winner}"], day=int(day))
    return out


# ---- approvals (the business layer asks, the office answers) ---------------------------------------------------------

def decide_approvals(conn, day: int) -> int:
    """Answer every pending approval request: the members of the body that grants that kind weigh the backer as a sponsor."""
    bodies = _rules(conn).get("approval_bodies") or {}
    n = 0
    for req in civic_seams.approval_requests(conn, day):
        key = bodies.get(req["approval_kind"])
        if key is None:
            continue
        backer = int(str(req["backer_ref"]).split(":")[1]) if str(req["backer_ref"]).startswith("person:") else None
        iid = open_item(conn, key, "licence" if "licence" in req["approval_kind"] else "zoning_variance",
                        {"sponsor": backer, "title": f"{req['approval_kind']} for venture {req['project_id']}", "request_id": int(req["id"])},
                        vote_day=int(day), day=int(day))
        out = decide(conn, iid, day)
        by = None
        for r in conn.execute("SELECT member_actor_id FROM civic_item_votes WHERE item_id=? AND vote='yes' ORDER BY member_actor_id LIMIT 1", (iid,)):
            by = int(r[0])
        civic_seams.answer_approval(conn, int(req["id"]), item(conn, iid)["status"] == "passed", key,
                                    {"item_id": iid, "yes": out.get("yes"), "no": out.get("no"), "reason": out.get("reason"), "by_actor_id": by}, int(day))
        n += 1
    return n


def advance(conn, day: int) -> dict:
    """Decide every open item whose vote day has come, and answer the approvals waiting."""
    done = 0
    for r in conn.execute("SELECT id,item_kind FROM civic_items WHERE status='open' AND vote_day<=? ORDER BY vote_day,id", (int(day),)).fetchall():
        if r["item_kind"] == "tender":
            award_tender(conn, int(r["id"]), day)
        else:
            decide(conn, int(r["id"]), day)
        done += 1
    return {"items": done, "approvals": decide_approvals(conn, day)}


# ---- what the rest of the world reads -------------------------------------------------------------------------------

def effects_on(conn, effect_key: str, day: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM civic_effects WHERE effect_key=? AND from_day<=? AND (to_day IS NULL OR to_day>=?) ORDER BY id",
                        (effect_key, int(day), int(day))).fetchall()
    return [{"id": int(r["id"]), "source_kind": r["source_kind"], "source_id": r["source_id"], "value": _j(r["value_json"], None),
             "from_day": int(r["from_day"]), "to_day": r["to_day"]} for r in rows]
