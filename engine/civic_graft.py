"""Corruption and fraud that start on their own (politics P1b).

Nobody is told to pay or to cheat. Each time a need arises (a permit or a variance before a board, a case against a man's outfit, a
race that is close) the one with the need weighs it: his temperament (pragmatism, risk tolerance, loyalty), the size of the need, the
price the official would ask (his rank and his ambition), and the risk of being found out (the same exposure chance the law draws
each week, over a horizon, softened by a bold man's tolerance). An official who is offered weighs it too: a pragmatic, ambitious one
accepts. A man in a close race weighs the same way whether to add votes where his side is strongest. There is no cap, no quota and
no fixed rate: every weight is a design figure with a note, and the package says which items, bodies, offices and organisation kinds
are in play (`graft` in the politics file). The engine never decides for the protagonist: `weigh` is the same rule for him, he is told
of an offer made to him, and what he does is his act; an official who is the protagonist is offered, and the offer is put in his
ledger rather than taken for him. Nothing here names a city, a party or an office.
"""
from __future__ import annotations

import json
import math
import random

from . import civic_corruption, civic_seams, design, electorate, offices, org_money, races
from .design import figure
from .world_package import package_for, politics_rules


def _g(conn) -> dict:
    return politics_rules(package_for(conn)).get("graft") or {}


def enabled(conn) -> bool:
    return bool(_g(conn))


def _f(conn, name, default: float = 0.0) -> float:
    return float(figure(conn, name, default)) if name else default


def _rng(conn, *key) -> random.Random:
    return random.Random(f"{design.run_seed(conn)}:graft:" + ":".join(str(k) for k in key))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _is_player(conn, actor: int) -> bool:
    from . import player
    p = player.get_player(conn)
    return p is not None and int(p["player_actor_id"]) == int(actor)


def _drive(conn, actor: int, col: str) -> float:
    r = conn.execute(f"SELECT {col} FROM actor_drives WHERE actor_id=?", (int(actor),)).fetchone()
    return float(r[0]) if r and r[0] is not None else 0.5


def temper(conn, actor: int) -> float:
    """How readily a man takes the crooked way: pragmatic, bold and not tied by loyalty. Centred on zero."""
    return (_drive(conn, actor, "pragmatism") + _drive(conn, actor, "risk_tolerance") + (1.0 - _drive(conn, actor, "loyalty"))) / 3.0 - 0.5


def price(conn, official: int) -> float:
    """What the official asks each week: with the rank of his office and with his own ambition."""
    g = _g(conn)
    return _f(conn, g.get("price_per_rank"), 120.0) * max(1.0, civic_corruption.rank(conn, int(official))) * (
        1.0 + _f(conn, g.get("price_ambition"), 1.0) * _drive(conn, int(official), "ambition"))


def risk(conn, payer_actor: int, official: int, weekly: float, day: int) -> float:
    """The chance, over the horizon, that a payment is found out; a bold man counts it down."""
    g = _g(conn)
    p, _ = civic_corruption.exposure_chance(conn, {"official_actor_id": int(official), "weekly_usd": float(weekly)}, day)
    over = 1.0 - (1.0 - p) ** max(1.0, _f(conn, g.get("horizon_weeks"), 26.0))
    return over * (1.0 - _drive(conn, int(payer_actor), "risk_tolerance") * _f(conn, g.get("tolerance_cut"), 0.7))


def weigh(conn, payer_actor: int, need: float, official: int, day: int) -> dict:
    """The one rule: the chance this person takes the crooked way for this need, with this official. The same for anyone."""
    g = _g(conn)
    weekly = price(conn, official)
    terms = {"base": _f(conn, g.get("base"), -5.0),
             "temper": _f(conn, g.get("w_temper"), 2.0) * temper(conn, payer_actor),
             "need": _f(conn, g.get("w_need"), 1.5) * float(need),
             "price": -_f(conn, g.get("w_price"), 0.6) * math.log1p(weekly / 10.0),
             "risk": -_f(conn, g.get("w_risk"), 4.0) * risk(conn, payer_actor, official, weekly, day)}
    return {"p": _sigmoid(sum(terms.values())), "terms": terms, "weekly": weekly}


def accepts(conn, official: int, day: int, key) -> bool:
    """He takes it more readily the more pragmatic and the more ambitious he is."""
    g = _g(conn)
    z = _f(conn, g.get("accept_base"), -1.0) + _f(conn, g.get("accept_pragmatism"), 2.5) * (_drive(conn, official, "pragmatism") - 0.5) \
        + _f(conn, g.get("accept_ambition"), 1.0) * (_drive(conn, official, "ambition") - 0.5)
    return _rng(conn, "accept", official, key, day).random() < _sigmoid(z)


def _already(conn, payer_kind: str, payer_id: int, official: int) -> bool:
    return bool(conn.execute("SELECT 1 FROM org_arrangements WHERE status='active' AND payer_kind=? AND payer_id=? AND official_actor_id=? AND position_key LIKE 'political:%'",
                             (payer_kind, int(payer_id), int(official))).fetchone())


def _try(conn, payer_kind: str, payer_id: int, payer_actor: int, need: float, officials: list[int], day: int, key, kind: str) -> int | None:
    """One weighed attempt: pick the official (the more likely to take it, the likelier), draw the payer's choice, draw his consent.
    Returns the arrangement id, or None."""
    officials = [o for o in officials if offices.offices_of(conn, o) and int(o) != int(payer_actor) and not _already(conn, payer_kind, payer_id, o)]
    if not officials or _is_player(conn, payer_actor):
        return None  # he is never made to pay; the same rule is there for him in `weigh`
    rng = _rng(conn, key, payer_kind, payer_id, day)
    pick = rng.choices(officials, weights=[max(1e-6, 1.0 - _drive(conn, o, "loyalty") * 0.5) for o in officials])[0]
    w = weigh(conn, payer_actor, need, pick, day)
    if rng.random() >= w["p"]:
        return None
    if _is_player(conn, pick):
        civic_seams.push(conn, int(pick), "offer", f"An offer of about {int(w['weekly'])} dollars a week for a favour is put to you.", day, {"payer": int(payer_actor)})
        return None
    if not accepts(conn, pick, day, key):
        return None
    return civic_corruption.put_on(conn, payer_kind, payer_id, pick, w["weekly"], go_between=None, day=day, kind=kind)


# ---- a need before a board -------------------------------------------------------------------------------------------

def consider_item(conn, item_id: int, day: int) -> int | None:
    """The sponsor of an item before a body he does not sit in weighs paying a member for it."""
    from . import civic_votes
    g = _g(conn)
    it = civic_votes.item(conn, item_id)
    sub = json.loads(it["subject_json"] or "{}")
    sponsor = sub.get("sponsor")
    needs = g.get("need") or {}
    if sponsor is None or it["item_kind"] not in needs or sub.get("graft_drawn"):
        return None
    sponsor = int(sponsor)
    members = [a for _, _, a in offices.members(conn, it["body_office_key"])]
    if sponsor in members:
        return None
    sub["graft_drawn"] = True
    conn.execute("UPDATE civic_items SET subject_json=? WHERE id=?", (json.dumps(sub, sort_keys=True, default=str), int(item_id)))
    return _try(conn, "actor", sponsor, sponsor, _f(conn, needs[it["item_kind"]]), members, int(day), f"item:{item_id}", g.get("kind") or "kickback")


# ---- protection: a case against an outfit's men ---------------------------------------------------------------------

def protection_pass(conn, day: int) -> int:
    g = _g(conn)
    p = g.get("protection") or {}
    kinds = p.get("org_kinds") or []
    offs = p.get("offices") or []
    if not kinds or not offs:
        return 0
    window = int(_f(conn, p.get("window_days"), 90.0))
    officials = [h for h in (offices.holder(conn, k) for k in offs) if h is not None]
    q = ",".join("?" * len(kinds))
    n = 0
    for o in conn.execute(f"SELECT org_actor_id FROM org_profiles WHERE org_kind IN ({q}) ORDER BY org_actor_id", tuple(kinds)).fetchall():
        org = int(o[0])
        cases = conn.execute("""SELECT COUNT(*) FROM crime_reports r JOIN org_seats s ON s.actor_id=r.offender_actor_id AND s.org_actor_id=? AND s.status='active'
                                WHERE r.day>? AND r.day<=?""", (org, int(day) - window, int(day))).fetchone()[0]
        head = None
        from . import orgs
        head = orgs.head_of(conn, org)
        if head is None or not cases:
            continue
        if _try(conn, "org", org, int(head), math.log1p(cases) * _f(conn, g.get("w_protect_scale"), 1.0), officials, int(day), "protect", p.get("kind") or "retainer") is not None:
            n += 1
    return n


# ---- a close race --------------------------------------------------------------------------------------------------

def fraud_pass(conn, day: int) -> int:
    """A candidate in a general election that is close, inside the window before the count, weighs adding votes where his side is strongest."""
    g = _g(conn)
    f = g.get("fraud") or {}
    if not f:
        return 0
    window = int(_f(conn, f.get("window_days"), 28.0))
    n = 0
    for r in conn.execute("SELECT * FROM races WHERE status='open' ORDER BY election_day,id").fetchall():
        rid = int(r["id"])
        if not (int(day) <= int(r["election_day"]) <= int(day) + window) or (r["primary_day"] is not None and int(r["primary_day"]) > int(day)):
            continue
        cs = races.candidates(conn, rid)
        if len(cs) < 2:
            continue
        shares = races.vote_shares(conn, rid, "general", int(day), cs)
        total = sum(shares.values()) or 1.0
        done = {int(x["actor"]) for x in (races._result(conn, rid).get("fraud") or [])}
        for c in cs:
            if c in done or _is_player(conn, c):
                continue
            mine = shares[c] / total
            rival = max(shares[a] / total for a in cs if a != c)
            need = math.exp(-abs(mine - rival) / max(1e-6, _f(conn, f.get("closeness"), 0.06)))
            party = races.party_of(conn, c)
            gs = electorate._district_groups(conn, races.office_key(conn, rid))
            if not gs:
                continue
            gs = sorted(gs, key=lambda x: (-(float(x["size"]) * (1.0 + (electorate.delivery(conn, int(x["id"]), "org", int(party)) if party is not None else 0.0))), int(x["id"])))
            grp = gs[0]
            size = max(1, int(_f(conn, f.get("share"), 0.03) * float(grp["size"])))
            terms = {"base": _f(conn, f.get("base"), -6.0), "temper": _f(conn, f.get("w_temper"), 2.5) * temper(conn, c),
                     "need": _f(conn, f.get("w_need"), 3.0) * need}
            p_caught = races.fraud_chance(conn, c, rid, int(grp["id"]), size)
            terms["risk"] = -_f(conn, f.get("w_risk"), 3.0) * p_caught * (1.0 - _drive(conn, c, "risk_tolerance") * _f(conn, g.get("tolerance_cut"), 0.7))
            if _rng(conn, "fraud", rid, c, day).random() < _sigmoid(sum(terms.values())):
                races.commit_fraud(conn, c, rid, int(grp["id"]), str(f.get("kind") or "stuffing"), size, int(day))
                n += 1
    return n


# ---- the weekly step -------------------------------------------------------------------------------------------------

def weekly(conn, day: int) -> dict:
    if not enabled(conn):
        return {}
    n_items = 0
    for r in conn.execute("SELECT id FROM civic_items WHERE status='open' ORDER BY id").fetchall():
        if consider_item(conn, int(r[0]), int(day)) is not None:
            n_items += 1
    return {"graft_items": n_items, "graft_protection": protection_pass(conn, day), "graft_fraud": fraud_pass(conn, day)}
