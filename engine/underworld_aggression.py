"""Gap 4b: outfits push on each other, each in its own temperament.

DEC-01 candidates (occupy vacant turf, challenge a zone, poach protection, hit, negotiate a settlement) built from rows that
exist, with utilities from the outfit's current temperament toward that rival, relative strength (Stage-weighted), hostility,
grudges and the heat the outfit already carries. Every move is one of several styles, chosen by temperament and means.
There is no cap on violence: costs make it plausible (heat, the city's tolerance, losses, retaliation, caution).
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any

from . import temperament as tp
from .decision_runtime import DecisionCandidate

HOSTILE_KINDS = {"occupy_vacant_turf", "challenge_zone", "poach_protection", "targeted_hit", "squeeze_specialist"}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _player_actor(conn: sqlite3.Connection) -> int | None:
    r = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    return int(r[0]) if r and r[0] is not None else None


def leader_is_player(conn: sqlite3.Connection, oid: int) -> bool:
    r = conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    p = _player_actor(conn)
    return bool(r and r[0] is not None and p is not None and int(r[0]) == p)


def _name(conn: sqlite3.Connection, oid: int) -> str:
    r = conn.execute("SELECT name FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    return str(r[0]) if r else f"outfit #{oid}"


def city_tension(conn: sqlite3.Connection, loc: int | None, day: int | None = None) -> float:
    """How much violence a city has seen lately: summed severity (0-1 each) of violent incidents and hits in the last 90 days."""
    if loc is None:
        return 0.0
    day = _day(conn) if day is None else int(day)
    r = conn.execute("""SELECT COALESCE(SUM(i.severity),0)/100.0 FROM underworld_incidents i JOIN underworld_organizations o ON o.id=i.target_organization_id
                        WHERE o.primary_location_id=? AND i.day>? AND i.incident_kind IN ('attack_on_member','attack_on_client')""", (loc, day - 90)).fetchone()
    return float(r[0])


def city_violence(conn: sqlite3.Connection, loc: int | None) -> float:
    return city_tension(conn, loc) * 25.0


def _own_zones(conn: sqlite3.Connection, oid: int) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        "SELECT zone_id FROM underworld_zone_claims WHERE organization_id=? AND status='active' ORDER BY claim_kind,zone_id", (oid,))]


def _city_zones(conn: sqlite3.Connection, loc: int | None) -> list[int]:
    if loc is None:
        return []
    return [int(r[0]) for r in conn.execute("SELECT id FROM underworld_zones WHERE city_location_id=? AND status='active' ORDER BY id", (loc,))]


def _controller(conn: sqlite3.Connection, zid: int) -> int | None:
    r = conn.execute("SELECT organization_id FROM underworld_zone_claims WHERE zone_id=? AND claim_kind='controller' AND status='active' LIMIT 1", (zid,)).fetchone()
    return int(r[0]) if r else None


def _neighbours(conn: sqlite3.Connection, zones: list[int]) -> list[int]:
    from .underworld_rebuild import UnderworldZoneGraph
    g = UnderworldZoneGraph(conn)
    seen: list[int] = []
    for z in zones:
        for n in g.neighbors(z):
            if n not in seen and n not in zones:
                seen.append(n)
    return seen


def _hostility(conn: sqlite3.Connection, a: int, b: int) -> tuple[float, str]:
    x, y = (a, b) if a < b else (b, a)
    r = conn.execute("SELECT hostility,relation_kind FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (x, y)).fetchone()
    return (float(r[0]), str(r[1])) if r else (20.0, "neutral")


def _log_ratio(conn: sqlite3.Connection, a: int, b: int) -> float:
    return math.log((tp.fighting_strength(conn, a) + 4.0) / (tp.fighting_strength(conn, b) + 4.0))


def aggression_candidates(conn: sqlite3.Connection, actor_id: int, oid: int, drives: dict[str, float], day: int,
                          investigative_heat: float, violence_heat: float, treasury: float) -> list[DecisionCandidate]:
    if leader_is_player(conn, oid):
        return []  # hostile initiatives for the player's outfit come only from an order through `act`
    org = conn.execute("SELECT primary_location_id,organization_type FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    loc = int(org[0]) if org[0] is not None else None
    cls = tp.outfit_class(conn, oid)
    aggression = float(drives.get("aggression", .5)); patience = float(drives.get("patience", .5))
    ambition = float(drives.get("ambition", .5))
    p0 = tp.propensity(conn, oid)
    hp = violence_heat / 60.0 + investigative_heat / 90.0
    tol = city_violence(conn, loc) / 100.0
    own = _own_zones(conn, oid)
    out: list[DecisionCandidate] = []
    pool = [(int(r[0]), float(r[1]), str(r[2])) for r in conn.execute(
        """SELECT CASE WHEN organization_a_id=? THEN organization_b_id ELSE organization_a_id END other,hostility,relation_kind
           FROM underworld_relations r JOIN underworld_organizations o ON o.id=CASE WHEN r.organization_a_id=? THEN r.organization_b_id ELSE r.organization_a_id END
           WHERE (organization_a_id=? OR organization_b_id=?) AND o.status IN ('active','strained','fragmented') AND o.primary_location_id IS ?
           ORDER BY hostility DESC LIMIT 6""", (oid, oid, oid, oid, loc))]

    def cand(key: str, kind: str, util: float, why: str, payload: dict[str, Any], tags: tuple[str, ...], risk: float, cost: float = 0.0) -> None:
        out.append(DecisionCandidate(
            key=f"underworld:{key}", provider_key="underworld", action_kind=kind, utility=util, rationale=why, execution_kind="underworld_action",
            payload=payload, information_basis={"access": "local_operational_opportunity", **{k: v for k, v in payload.items() if isinstance(v, (int, str))}},
            tags=tags, risk=risk, estimated_cost=cost))

    # Ground: a vacant zone next to one's own (or, with none, anywhere in town) -- expansion, not yet violence.
    if cls != "specialist" and loc is not None:
        free = [z for z in (_neighbours(conn, own) if own else _city_zones(conn, loc)) if _controller(conn, z) is None]
        if free:
            from .underworld_rebuild import _required_zone_manpower, organization_manpower_balance
            zid = free[0]
            if organization_manpower_balance(conn, oid)["slack"] >= _required_zone_manpower(conn, zid) * .65:
                cand(f"occupy:{zid}", "occupy_vacant_turf", 3.4 + 1.8 * ambition + 1.4 * p0 - tol, "Take the vacant ground next to what the outfit already holds.",
                     {"zone_id": zid}, ("territory", "expansion"), .15)

    # Challenge a zone held by another outfit, or poach one of its protected clients.
    if cls != "specialist" and loc is not None:
        reach = (_neighbours(conn, own) + own) if own else _city_zones(conn, loc)
        seen_t: set[int] = set()
        for zid in reach:
            t = _controller(conn, zid)
            if t is None or t == oid or t in seen_t:
                continue
            seen_t.add(t)
            h, _kind = _hostility(conn, oid, t)
            pt = tp.propensity(conn, oid, toward=t)
            # Durable families hold property and fronts and settle things by other means [1734, 1774]; street gangs fight over corners.
            u = 0.6 + 9.0 * pt + h / 40.0 + 1.4 * _log_ratio(conn, oid, t) - (1.6 - 1.0 * pt) * hp - 1.5 * tol + {"street": .5, "durable": -1.4}.get(cls, 0.0)
            cand(f"challenge:{zid}:{t}", "challenge_zone", u, f"Press {_name(conn, t)} for its ground.", {"zone_id": zid, "target_organization_id": t},
                 ("territory", "hostile"), .6)
            acct = conn.execute(
                """SELECT p.enterprise_id,p.protector_organization_id FROM underworld_protection_accounts p
                   WHERE p.zone_id=? AND p.status='active' AND p.protector_organization_id=? ORDER BY p.id LIMIT 1""", (zid, t)).fetchone()
            if acct and _log_ratio(conn, oid, t) > -.1 and zid in own + [z for z in reach if z in own]:
                up = 1.8 + 4.0 * pt + 1.3 * ambition + h / 60.0 - 1.0 * hp + {"street": .3, "durable": -.8}.get(cls, 0.0)
                cand(f"poach:{acct['enterprise_id']}:{zid}", "poach_protection", up, f"Take a protected client from {_name(conn, t)}.",
                     {"zone_id": zid, "enterprise_id": int(acct["enterprise_id"]), "target_organization_id": t}, ("protection", "hostile"), .4)
            if len(seen_t) >= 3:
                break

    # Gangs and families prey on the specialists of their city (fences, lenders, brokers): they hold stock and cash and no ground to defend it.
    if cls != "specialist" and loc is not None:
        prey = conn.execute(
            """SELECT o.id,o.treasury FROM underworld_organizations o WHERE o.primary_location_id=? AND o.id<>? AND o.status='active'
               AND json_extract(o.metadata_json,'$.role')='specialist' ORDER BY o.treasury DESC,o.id LIMIT 2""", (loc, oid)).fetchall()
        own_tr = max(0.0, treasury)
        for pr in prey:
            t = int(pr["id"])
            pt = tp.propensity(conn, oid, toward=t)
            richness = math.log1p(float(pr["treasury"])) - math.log1p(own_tr)
            u = .3 + 5.5 * pt + 1.1 * ambition + .5 * richness + 1.2 * _log_ratio(conn, oid, t) - (1.6 - pt) * hp - 1.2 * tol + {"street": .4, "durable": -1.0}.get(cls, 0.0)
            cand(f"squeeze:{t}", "squeeze_specialist", u, f"Squeeze {_name(conn, t)}: it holds stock and cash and no ground to defend them.",
                 {"target_organization_id": t}, ("hostile", "predation"), .5)

    # A hit on a hated rival, and the settlements durable outfits prefer.
    for other, h, kind in pool:
        pt = tp.propensity(conn, oid, toward=other)
        g = tp.grudge_level(conn, oid, other, day)
        if (h >= 58 and kind in ("rival", "war")) or (kind == "hostile_peace" and h >= 58 and g >= 35):
            u = .4 + 6.5 * pt + (h - 58) / 12.0 + g / 22.0 + 1.0 * _log_ratio(conn, oid, other) - (2.0 - 1.2 * pt) * hp - tol
            cand(f"hit:{other}", "targeted_hit", u, f"Strike {_name(conn, other)} where it hurts.", {"target_organization_id": other}, ("hostile", "violence"), .8)
        if h >= 35 and kind in ("rival", "war", "hostile_peace"):
            u = 2.4 + 2.6 * (1 - pt) + 1.3 * patience + (.9 if cls == "durable" else 0.0) + h / 55.0 + .8 * hp + tol - g / 35.0
            cand(f"settle:{other}", "negotiate_settlement", u, f"Settle with {_name(conn, other)} through an intermediary, with a payment.",
                 {"target_organization_id": other}, ("diplomacy", "truce_path"), .12, cost=.5)
    return out


# -- styles --------------------------------------------------------------------------------------------------

def _members_of(conn: sqlite3.Connection, oid: int, *, least: bool = False) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT p.actor_id,p.role_kind FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id
           WHERE p.organization_id=? AND p.status='active' AND a.status='active'
           ORDER BY p.authority {} ,p.actor_id""".format("ASC" if least else "DESC"), (oid,)).fetchall()


def _client(conn: sqlite3.Connection, t: int, zid: int | None) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT e.id,e.name,e.cash FROM underworld_protection_accounts p JOIN civilian_enterprises e ON e.id=p.enterprise_id
           WHERE p.protector_organization_id=? AND p.status='active' AND e.status IN ('active','strained')
           ORDER BY (p.zone_id=?) DESC,e.cash DESC,e.id LIMIT 1""", (t, zid if zid is not None else -1)).fetchone()


def hit_band(p: float, rng: random.Random, lethal: bool) -> str:
    """Outcome of a blow whose odds of landing are p: failed / wounded / maimed / killed. It leans toward survival: death needs
    a killing intent and odds that are close to overwhelming; most blows that land wound or maim."""
    if rng.random() >= max(0.0, min(1.0, p)):
        return "failed"
    pk = (max(0.0, p - 0.3) / 0.7) ** 1.3 * (1.0 if lethal else 0.15)
    if rng.random() < pk:
        return "killed"
    return "maimed" if rng.random() < 0.35 + 0.3 * p else "wounded"


_BAND_OUTCOME = {"wounded": "transient", "maimed": "persistent", "killed": "fatal"}


def _phrase_for(style: str, org: str) -> str:
    if style == "beating":
        return f"men of {org} mean to beat you"
    if style == "abduction":
        return f"men of {org} mean to take you"
    if style == "duel":
        return f"{org} has sent its best fighter to settle it with you"
    return f"{org} has made an attempt on your life"


def pending_attempt(conn: sqlite3.Connection, player: int, src_org: int, p: float, *, style: str, lethal: bool, day: int) -> int | None:
    """An attempt on the protagonist is never resolved off-screen: it becomes a pending incident for the GM to play (and it
    interrupts a time skip). The odds are kept for the scene's resolution."""
    from .interactions import create_interaction
    from .simulation import SimEvent, log_event
    head = conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (src_org,)).fetchone()
    proposer = int(head[0]) if head and head[0] is not None and int(head[0]) != player else None
    if proposer is None:
        r = conn.execute("""SELECT p.actor_id FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id WHERE p.organization_id=? AND p.status='active'
                            AND a.status='active' AND p.actor_id<>? ORDER BY p.authority DESC,p.actor_id LIMIT 1""", (src_org, player)).fetchone()
        proposer = int(r[0]) if r else None
    if proposer is None:
        return None
    org = _name(conn, src_org)
    phrase = _phrase_for(style, org)
    iid = create_interaction(conn, proposer, player, "attack", day, urgency=5, stakes=4,
                             terms={"purpose": phrase, "underworld_attempt": True, "source_organization_id": src_org, "style": style,
                                    "odds": round(float(p), 4), "lethal": bool(lethal)},
                             rationale=f"{org} moves against the protagonist.")
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (player,)).fetchone()
    log_event(conn, SimEvent(day=day, event_type="underworld_attempt", title=f"{org} moves against you", summary=phrase[0].upper() + phrase[1:] + ".",
                             severity=4, source_actor_id=proposer, target_actor_ids=(player,), location_id=int(loc[0]) if loc and loc[0] is not None else None))
    return iid


def _apply_band(conn: sqlite3.Connection, victim: int, src_org: int, band: str, rng: random.Random, *, style: str, severity: float, lethal: bool,
                ref: int | None = None) -> dict[str, Any] | None:
    from .harm import record_harm
    outcome = _BAND_OUTCOME.get(band)
    if outcome is None:
        return None
    return record_harm(conn, victim, source_kind=f"underworld_{style}", source_ref_id=ref if ref is not None else rng.randrange(1, 10**9), severity=severity,
                       intent_class="lethal" if lethal else "hostile", metadata={"source_organization_id": src_org, "style": style, "band": band},
                       outcome_override=outcome)


def attempt_on(conn: sqlite3.Connection, victim: int, src_org: int, p: float, rng: random.Random, *, style: str, lethal: bool, severity: float) -> dict[str, Any]:
    """A blow aimed at one person, whoever he is. The protagonist's becomes a pending incident; anyone else's resolves in bands."""
    if victim == _player_actor(conn):
        return {"band": "pending", "interaction_id": pending_attempt(conn, victim, src_org, p, style=style, lethal=lethal, day=_day(conn))}
    band = hit_band(p, rng, lethal)
    _apply_band(conn, victim, src_org, band, rng, style=style, severity=severity, lethal=lethal)
    return {"band": band}


def resolve_attempt(conn: sqlite3.Connection, interaction: sqlite3.Row, choice: str, day: int):
    """The GM has played the attempt on the protagonist: he stands (reject), yields (accept) or runs (counter). Same bands, same odds."""
    from . import ledger
    from .interactions import InteractionResult
    from .simulation import SimEvent, log_event
    terms = json.loads(interaction["terms_json"] or "{}")
    me, src = int(interaction["recipient_actor_id"]), int(terms["source_organization_id"])
    p, lethal, style = float(terms.get("odds", .5)), bool(terms.get("lethal")), str(terms.get("style", "assault"))
    rng = random.Random(int(interaction["id"]) * 7919 + day)
    org = _name(conn, src)
    if choice == "accept":
        bal = ledger.balance(conn, ("person", me))
        if bal > 0.01:
            ledger.transfer(conn, ("person", me), ("outfit", src), round(bal * (0.1 + 0.4 * p), 4), flow_kind="other", purpose="paid off", allow_partial=True)
        summary = f"He yields to {org}, pays them off and walks away whole."
    else:
        pe = p if choice == "reject" else p * 0.45  # running cuts the odds of being caught
        band = hit_band(pe, rng, lethal)
        _apply_band(conn, me, src, band, rng, style=style, severity=70 if lethal else 40, lethal=lethal, ref=int(interaction["id"]))
        verb = "stands" if choice == "reject" else "runs"
        tail = {"failed": f"and {org}'s attempt comes to nothing.", "wounded": f"and {org}'s men leave him hurt.",
                "maimed": f"and {org}'s men leave him badly hurt, for good.", "killed": f"and {org}'s men kill him."}[band]
        summary = f"He {verb} {tail}"
        if band == "failed":
            _anonymous_loss(conn, src, 1.0, "lost a man in a failed attempt on", 30, (0.0, 0.0, 0.0))
    conn.execute("UPDATE interactions SET status='resolved',resolved_day=?,resolution_summary=? WHERE id=?", (day, summary, int(interaction["id"])))
    log_event(conn, SimEvent(day=day, event_type="underworld_attempt_resolved", title=f"{org}'s attempt on him", summary=summary, severity=4,
                             source_actor_id=int(interaction["proposer_actor_id"]), target_actor_ids=(me,)))
    return InteractionResult(int(interaction["id"]), "resolved", choice, summary)


def expire_attempts(conn: sqlite3.Connection, day: int, ttl: int = 60) -> int:
    """An attempt nobody plays out lapses (the moment passes); it never turns into harm unseen."""
    n = 0
    for r in conn.execute("SELECT id FROM interactions WHERE status='pending' AND interaction_type='attack' AND json_extract(terms_json,'$.underworld_attempt')=1 AND created_day<=?", (day - ttl,)).fetchall():
        conn.execute("UPDATE interactions SET status='expired',resolved_day=?,resolution_summary='The moment passed.' WHERE id=?", (day, int(r[0])))
        n += 1
    return n


def _edge(conn: sqlite3.Connection, a: int, t: int) -> float:
    """Chance that outfit a gets the better of outfit t in a blow: from the Stage-weighted strength of the two."""
    return max(0.06, min(0.94, 1.0 / (1.0 + math.exp(-1.6 * _log_ratio(conn, a, t)))))


def _harm(conn: sqlite3.Connection, victim: int, source_org: int, rng: random.Random, *, severity: float, intent: str, kind: str,
          lethal: bool = False, odds: float = 0.6) -> str:
    """Harm to one person. The protagonist's is a pending incident. A killing resolves in bands; a beating by the ordinary model."""
    from .harm import record_harm
    if victim == _player_actor(conn):
        pending_attempt(conn, victim, source_org, odds, style=kind, lethal=lethal, day=_day(conn))
        return "pending"
    if lethal:
        band = hit_band(max(odds, 0.05), rng, True)
        _apply_band(conn, victim, source_org, band, rng, style=kind, severity=severity, lethal=True)
        return {"failed": "transient", "wounded": "transient", "maimed": "persistent", "killed": "fatal"}[band]
    r = record_harm(conn, victim, source_kind=f"underworld_{kind}", source_ref_id=rng.randrange(1, 10**9), severity=severity, intent_class=intent,
                    metadata={"source_organization_id": source_org, "style": kind})
    return str(r["outcome"])


def _anonymous_loss(conn, t, count, text, severity, heat):
    """Most of an outfit's men are not named people: the blow lands on the membership stock (killed or put out of action)."""
    from .underworld import record_underworld_membership_flow
    prof = conn.execute("SELECT COALESCE(active_members,0) FROM underworld_membership_profiles WHERE organization_id=?", (t,)).fetchone()
    n = min(float(prof[0]) if prof else 0.0, count)
    if n > 0.05:
        record_underworld_membership_flow(conn, t, "death_or_incapacitation", n, from_tier="active", metadata={"hostile_move": True})
    return {"win": True, "incident": "attack_on_member", "severity": severity, "heat": heat, "text": text}


def _styled(name):
    def deco(fn):
        def run(conn, a, t, zid, rng):
            res = fn(conn, a, t, zid, rng)
            res.setdefault("style", name)
            return res
        return run
    return deco


@_styled("intimidation")
def _s_intimidation(conn, a, t, zid, rng):
    conn.execute("UPDATE underworld_zone_claims SET fear=MIN(100,fear+2),strength=MAX(0,strength-2.5) WHERE zone_id=? AND organization_id=? AND status='active'", (zid, t))
    win = rng.random() < .55 + .1 * math.tanh(_log_ratio(conn, a, t))
    return {"win": win, "incident": "extortion_attempt", "severity": 30, "heat": (1.0, 0.5, 1.0), "text": "leaned on"}


def _failed(conn, a, t, text, severity=22):
    """The blow did not land. The target still knows it was tried, and the attacker pays for it in men."""
    _anonymous_loss(conn, a, .5 + .9 * (1.0 - _edge(conn, a, t)), "lost men", severity, (0.0, 0.0, 0.0))
    return {"win": False, "incident": "extortion_attempt", "severity": severity, "heat": (1.0, .5, 1.0), "text": text}


def _fee(conn, a):
    """What a hired hand costs: a share of the buyer's treasury, so a rich outfit pays more and a poor one can still buy something small."""
    tr = float(conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (a,)).fetchone()[0])
    return round(max(.2, .12 * tr), 3), tr


@_styled("beating")
def _s_beating(conn, a, t, zid, rng):
    ms = [m for m in _members_of(conn, t, least=True) if m["role_kind"] in ("member", "associate", "collector", "enforcer", "crew_leader")]
    p = _edge(conn, a, t)
    if rng.random() >= p:
        return _failed(conn, a, t, "failed in a beating of men of")
    if not ms:
        return _anonymous_loss(conn, t, .6, "beat men of", 42, (1.5, 1.0, 2.5))
    v = ms[rng.randrange(min(3, len(ms)))]
    out = _harm(conn, int(v["actor_id"]), a, rng, severity=38, intent="hostile", kind="beating", odds=p)
    return {"win": True, "incident": "attack_on_member", "severity": 42, "heat": (1.5, 1.0, 2.5), "text": "beat a man of", "victim": int(v["actor_id"]), "harm": out}


@_styled("hired_beating")
def _s_hired_beating(conn, a, t, zid, rng):
    """A specialist or a careful family buys a beating from freelances instead of sending its own."""
    from .underworld_rebuild import _finance
    fee, tr = _fee(conn, a)
    if tr < fee * .5:
        return _s_intimidation(conn, a, t, zid, rng)
    pay = round(fee * .5, 3)
    conn.execute("UPDATE underworld_organizations SET treasury=treasury-? WHERE id=?", (pay, a))
    _finance(conn, a, "hired_hands_fee", -pay, counterparty_organization_id=None)
    ms = [m for m in _members_of(conn, t, least=True) if m["role_kind"] in ("member", "associate", "collector", "enforcer", "crew_leader")]
    p = max(.3, min(.8, .55 + .1 * math.tanh(-_log_ratio(conn, t, a))))  # the hired hands' skill does not depend on the buyer's own fighters
    if rng.random() >= p:
        return {"win": False, "incident": "extortion_attempt", "severity": 22, "heat": (.5, .5, .5), "text": "sent hired hands against"}
    if not ms:
        return _anonymous_loss(conn, t, .5, "had men of", 38, (1.0, 1.0, 1.5))
    v = ms[rng.randrange(min(3, len(ms)))]
    out = _harm(conn, int(v["actor_id"]), a, rng, severity=38, intent="hostile", kind="hired_beating", odds=p)
    return {"win": True, "incident": "attack_on_member", "severity": 40, "heat": (1.0, 1.5, 1.5), "text": "had a man of", "victim": int(v["actor_id"]), "harm": out}


@_styled("smashed_premises")
def _s_smashed_premises(conn, a, t, zid, rng):
    c = _client(conn, t, zid)
    if c is None:
        return _s_beating(conn, a, t, zid, rng)
    if rng.random() >= _edge(conn, a, t):
        return _failed(conn, a, t, "failed to wreck a business under the protection of")
    conn.execute("UPDATE civilian_enterprises SET cash=cash*.6,status=CASE WHEN status='active' AND ?<.4 THEN 'strained' ELSE status END WHERE id=?", (rng.random(), int(c["id"])))
    return {"win": True, "incident": "attack_on_client", "severity": 48, "heat": (2.5, 1.5, 3.0), "text": "wrecked a business under the protection of", "enterprise_id": int(c["id"])}


@_styled("seized_goods")
def _s_seized_goods(conn, a, t, zid, rng):
    from . import ledger
    c = _client(conn, t, zid)
    p = _edge(conn, a, t)
    if c is not None and float(c["cash"]) >= 1.0:
        if rng.random() >= p:
            return _failed(conn, a, t, "failed to seize goods from a client of")
        amt = round(float(c["cash"]) * .35, 3)
        if amt >= .05:
            ledger.transfer(conn, ("business", int(c["id"])), ("outfit", a), amt, flow_kind="other", purpose="goods seized")
        return {"win": True, "incident": "attack_on_client", "severity": 40, "heat": (1.5, 1.5, 1.0), "text": "seized goods from a client of", "enterprise_id": int(c["id"])}
    # an outfit with no clients (a fence, a broker, a lender) is robbed of its own stock
    tr = float(conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (t,)).fetchone()[0])
    if tr < .5:
        return _s_intimidation(conn, a, t, zid, rng)
    if rng.random() >= p:
        return _failed(conn, a, t, "failed to rob")
    amt = round(tr * .2, 3)
    ledger.transfer(conn, ("outfit", t), ("outfit", a), amt, flow_kind="other", purpose="goods seized")
    return {"win": True, "incident": "attack_on_member", "severity": 38, "heat": (1.5, 1.5, 1.0), "text": "robbed the stock of"}


@_styled("abduction")
def _s_abduction(conn, a, t, zid, rng):
    from . import ledger
    ms = [m for m in _members_of(conn, t, least=False) if m["role_kind"] in ("crew_leader", "collector", "enforcer", "lieutenant", "member")]
    if not ms:
        return _s_beating(conn, a, t, zid, rng)
    p = _edge(conn, a, t)
    if rng.random() >= p:
        return _failed(conn, a, t, "failed to snatch a man of", 26)
    v = ms[-1]
    out = _harm(conn, int(v["actor_id"]), a, rng, severity=22, intent="hostile", kind="abduction", odds=p)
    ransom = round(float(conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (t,)).fetchone()[0]) * .25, 3)
    if ransom >= .05:
        ledger.transfer(conn, ("outfit", t), ("outfit", a), ransom, flow_kind="other", purpose="ransom")
    return {"win": True, "incident": "attack_on_member", "severity": 55, "heat": (2.5, 3.0, 3.0), "text": "snatched a man of", "victim": int(v["actor_id"]), "harm": out}


@_styled("duel")
def _s_duel(conn, a, t, zid, rng):
    fa = [m for m in _members_of(conn, a)][:6]
    ft = [m for m in _members_of(conn, t)][:6]
    if not fa or not ft:
        return _s_beating(conn, a, t, zid, rng)
    ca = max(fa, key=lambda m: (tp.stage_weight(conn, int(m["actor_id"])), -int(m["actor_id"])))
    ct = max(ft, key=lambda m: (tp.stage_weight(conn, int(m["actor_id"])), -int(m["actor_id"])))
    wa, wt = tp.stage_weight(conn, int(ca["actor_id"])), tp.stage_weight(conn, int(ct["actor_id"]))
    p = 1.0 / (1.0 + (wt / wa) ** 1.6)
    win = rng.random() < p
    loser, winner = (ct, ca) if win else (ca, ct)
    src = a if win else t
    out = _harm(conn, int(loser["actor_id"]), src, rng, severity=78, intent="hostile", kind="duel", odds=p if win else 1.0 - p)
    return {"win": win, "incident": "attack_on_member", "severity": 60, "heat": (3.0, 2.0, 4.0), "text": "sent its best fighter against the best of",
            "victim": int(loser["actor_id"]), "harm": out}


@_styled("public_example")
def _s_public_example(conn, a, t, zid, rng):
    ms = [m for m in _members_of(conn, t, least=True) if m["role_kind"] in ("member", "associate", "collector", "enforcer")]
    p = min(.95, _edge(conn, a, t) + .15)  # the example is made of someone who cannot fight back well
    if rng.random() >= p:
        return _failed(conn, a, t, "failed to make an example of a man of", 30)
    if not ms:
        return _anonymous_loss(conn, t, 1.0, "made a public example of a man of", 72, (6.0, 3.0, 9.0))
    v = ms[0]
    out = _harm(conn, int(v["actor_id"]), a, rng, severity=100, intent="lethal", kind="public_example", lethal=True, odds=p)
    return {"win": True, "incident": "attack_on_member", "severity": 72, "heat": (6.0, 3.0, 9.0), "text": "made a public example of a man of", "victim": int(v["actor_id"]), "harm": out}


@_styled("hired_killing")
def _s_hired_killing(conn, a, t, zid, rng):
    from .underworld_rebuild import _finance, _targeted_hit
    fee, tr = _fee(conn, a)
    if tr < fee:
        return _s_beating(conn, a, t, zid, rng)
    conn.execute("UPDATE underworld_organizations SET treasury=treasury-? WHERE id=?", (fee, a))
    _finance(conn, a, "hired_killer_fee", -fee, counterparty_organization_id=None)
    ok = _targeted_hit(conn, a, rng, target=t, hired=True)
    return {"win": bool(ok), "incident": "attack_on_member", "severity": 80, "heat": (1.0, 4.0, 3.0), "text": "paid for a killing in", "hit": True}


@_styled("assault")
def _s_assault(conn, a, t, zid, rng):
    from .underworld_rebuild import _resolve_territorial_attack, organization_manpower_balance
    if zid is None or organization_manpower_balance(conn, a)["slack"] < 2:
        return _s_beating(conn, a, t, zid, rng)
    before = _controller(conn, zid)
    _resolve_territorial_attack(conn, a, zid, t, rng)
    won = _controller(conn, zid) == a and before != a
    return {"win": won, "incident": None, "severity": 70, "heat": (0.0, 0.0, 0.0), "text": "stormed the ground of", "assault": True}


STYLE_FUNCS = {"intimidation": _s_intimidation, "beating": _s_beating, "hired_beating": _s_hired_beating, "smashed_premises": _s_smashed_premises,
               "seized_goods": _s_seized_goods, "abduction": _s_abduction, "duel": _s_duel, "public_example": _s_public_example,
               "hired_killing": _s_hired_killing, "assault": _s_assault}


def pick_style(conn: sqlite3.Connection, a: int, t: int, rng: random.Random) -> str:
    w = tp.style_weights(conn, a)
    h, _ = _hostility(conn, a, t)
    p = tp.propensity(conn, a, toward=t)
    fee, tr = _fee(conn, a)
    keys, weights = [], []
    for k, v in sorted(w.items()):
        if k in ("hired_killing", "hired_beating") and tr < fee:
            continue
        if k == "public_example":
            v *= p * p * 2.0 if h >= 40 else 0.0
        if k in ("hired_killing", "duel", "abduction"):
            v *= .3 + p
        if k == "hired_beating":
            v *= 1.4 - p  # the less hot-blooded the buyer, the more it prefers to pay for it
        if v > 0:
            keys.append(k); weights.append(v)
    return rng.choices(keys, weights=weights, k=1)[0] if keys else "intimidation"


def hostile_move(conn: sqlite3.Connection, a: int, t: int, zid: int | None, rng: random.Random, *, style: str | None = None,
                 file_contest: bool = True) -> dict[str, Any]:
    """One hostile move of outfit a against outfit t, in a style. Records the operation, the incident (answered by the target's
    own decision loop), heat on both, the relation and the event, and moves both outfits' temperaments."""
    from .underworld_rebuild import _operation, _record_territorial_occurrence, add_heat, add_zone_challenger, change_relation
    from .simulation import _world_event_logger
    style = style or pick_style(conn, a, t, rng)
    res = STYLE_FUNCS[style](conn, a, t, zid, rng)
    style = res.get("style", style)  # a style that could not be carried out falls back to a lesser one; record what happened
    win = bool(res.get("win"))
    meta = {"style": style, "won": win, "zone_id": zid, **{k: res[k] for k in ("victim", "harm", "enterprise_id") if k in res}}
    incident_id = None
    if res.get("incident"):
        incident_id = int(conn.execute(
            """INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
               VALUES (?,?,?,?,?,?,'open',?)""", (_day(conn), zid, a, t, res["incident"], res["severity"], json.dumps(meta, sort_keys=True))).lastrowid)
    if file_contest and zid is not None and style != "assault" and not res.get("hit"):
        add_zone_challenger(conn, zid, a, strength=22 + (6 if win else 0), severity=28, metadata={"style": style})
    if res["heat"] != (0.0, 0.0, 0.0):
        add_heat(conn, a, public=res["heat"][0], investigative=res["heat"][1], violence=res["heat"][2])
        add_heat(conn, t, public=res["heat"][0] * .4, investigative=res["heat"][1] * .3, violence=res["heat"][2] * .4)
    h, _ = _hostility(conn, a, t)
    change_relation(conn, a, t, kind="war" if h + 9 >= 75 else "rival", hostility_delta=9 if win else 6, respect_delta=1 if win else 0, metadata={"style": style})
    tp.adjust(conn, a, .04 if win else -.10)
    tp.adjust(conn, t, -.04 if win else .03)
    op = _operation(conn, a, "hostile_move", zone_id=zid, target_organization_id=t, result="won" if win else "failed", success=1.0 if win else 0.0, metadata=meta)
    if res.get("victim") is not None and res.get("harm") in ("fatal", "persistent"):
        pass  # grudges come from record_harm itself
    zname = conn.execute("SELECT name FROM underworld_zones WHERE id=?", (zid,)).fetchone() if zid is not None else None
    _record_territorial_occurrence(
        conn, event_logger=_world_event_logger(conn), event_type="underworld_hostile_move",
        title=f"Trouble between outfits: {_name(conn, a)} and {_name(conn, t)}",
        summary=f"{_name(conn, a)} {res['text']} {_name(conn, t)}" + (f" in {zname[0]}." if zname else "."),
        severity_0_100=res["severity"], zone_id=zid, source_organization_id=a, target_organization_id=t, operation_id=op, incident_id=incident_id,
        tags=["violence", style], metadata=meta)
    return {"operation_id": op, "style": style, "won": win, "incident_id": incident_id}


# -- execution ------------------------------------------------------------------------------------------------

def _rng(conn: sqlite3.Connection, oid: int, salt: int) -> random.Random:
    from .underworld_rebuild import _seed
    return random.Random(_seed(conn, oid * 7919 + salt))


def execute_aggression(conn: sqlite3.Connection, actor_id: int, oid: int, action_kind: str, payload: dict[str, Any], day: int) -> dict[str, Any]:
    from . import underworld_rebuild as uw
    if leader_is_player(conn, oid) and (action_kind in HOSTILE_KINDS or action_kind == "negotiate_settlement"):
        return {"summary": "Hostile initiative withheld: it needs the boss's own order.", "blocked": True}
    t = int(payload["target_organization_id"]) if payload.get("target_organization_id") is not None else None
    rng = _rng(conn, oid, (t or 0) * 31 + int(payload.get("zone_id") or 0))
    if action_kind == "occupy_vacant_turf":
        zid = int(payload["zone_id"])
        if _controller(conn, zid) is not None:
            raise ValueError("zone no longer vacant")
        uw.set_zone_controller(conn, zid, oid, strength=rng.uniform(35, 52), local_support=rng.uniform(25, 48), fear=rng.uniform(34, 58),
                               metadata={"dec01_occupation": True})
        uw.add_heat(conn, oid, public=.7)
        op = uw._operation(conn, oid, "occupy_vacant_turf", zone_id=zid, result="completed", success=1, metadata={"dec01_actor_id": actor_id})
        return {"summary": f"Occupied vacant ground (zone #{zid}).", "operation_id": op}
    if action_kind == "challenge_zone":
        zid = int(payload["zone_id"])
        if _controller(conn, zid) != t:
            raise ValueError("zone changed hands")
        r = hostile_move(conn, oid, t, zid, rng)
        return {"summary": f"Pressed {_name(conn, t)} over zone #{zid} by {r['style']}.", "operation_id": r["operation_id"]}
    if action_kind == "poach_protection":
        eid, zid = int(payload["enterprise_id"]), int(payload["zone_id"])
        res = uw.protect_business(conn, oid, eid, zid, payment_per_30=1.0, service_strength=50, fear_component=50, metadata={"dec01_actor_id": actor_id})
        uw.add_heat(conn, oid, public=1.0, violence=1.0)
        uw.change_relation(conn, oid, t, kind="rival", hostility_delta=6)
        op = uw._operation(conn, oid, "poach_protection", zone_id=zid, target_organization_id=t, enterprise_id=eid, result="attempted",
                           success=.5, metadata={"style": "intimidation", **res})
        return {"summary": f"Tried to take protected client #{eid} from {_name(conn, t)}.", "operation_id": op}
    if action_kind == "targeted_hit":
        fee, trs = _fee(conn, oid)
        style = "hired_killing" if tp.outfit_class(conn, oid) != "street" and trs >= fee else "assault"
        if style == "assault":
            ok = uw._targeted_hit(conn, oid, rng, target=t)
            op = None
        else:
            r = hostile_move(conn, oid, t, None, rng, style="hired_killing", file_contest=False)
            return {"summary": f"Paid for a killing in {_name(conn, t)}.", "operation_id": r["operation_id"]}
        uw.add_heat(conn, oid, violence=2)
        return {"summary": f"Struck at {_name(conn, t)}: {'done' if ok else 'nothing came of it'}."}
    if action_kind == "squeeze_specialist":
        w = {k: v for k, v in tp.style_weights(conn, oid).items() if k in ("seized_goods", "intimidation", "beating")}
        style = rng.choices(sorted(w), weights=[w[k] for k in sorted(w)], k=1)[0] if w else "intimidation"
        r = hostile_move(conn, oid, t, None, rng, style=style, file_contest=False)
        return {"summary": f"Squeezed {_name(conn, t)} by {r['style']}.", "operation_id": r["operation_id"]}
    if action_kind == "negotiate_settlement":
        return negotiate(conn, oid, t, rng, day)
    raise ValueError(f"unsupported aggression action {action_kind}")


def negotiate(conn: sqlite3.Connection, a: int, t: int, rng: random.Random, day: int) -> dict[str, Any]:
    from . import ledger
    from . import underworld_rebuild as uw
    pt = tp.propensity(conn, t, toward=a, day=day)
    g = tp.grudge_level(conn, t, a, day)
    accept = max(.05, min(.92, .85 - .55 * pt - g / 160.0))
    mid = conn.execute(
        """SELECT o.id FROM underworld_organizations o WHERE o.primary_location_id=(SELECT primary_location_id FROM underworld_organizations WHERE id=?)
           AND o.status='active' AND o.id NOT IN (?,?) ORDER BY o.cohesion DESC,o.id LIMIT 1""", (a, a, t)).fetchone()
    pay = round(float(conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (a,)).fetchone()[0]) * .15, 3)
    ok = rng.random() < accept
    if ok:
        if pay >= .05:
            ledger.transfer(conn, ("outfit", a), ("outfit", t), pay, flow_kind="other", purpose="settlement")
        uw.make_truce(conn, a, t, metadata={"settlement": True, "intermediary_organization_id": int(mid[0]) if mid else None})
        conn.execute("UPDATE underworld_grudges SET intensity=MAX(0,intensity-12) WHERE (organization_id=? AND rival_organization_id=?) OR (organization_id=? AND rival_organization_id=?)", (a, t, t, a))
        conn.execute("UPDATE underworld_incidents SET status='settled' WHERE status='open' AND ((source_organization_id=? AND target_organization_id=?) OR (source_organization_id=? AND target_organization_id=?))", (a, t, t, a))
    else:
        uw.change_relation(conn, a, t, hostility_delta=3)
    op = uw._operation(conn, a, "negotiate_settlement", target_organization_id=t, result="completed" if ok else "refused", success=1.0 if ok else 0.0,
                       metadata={"payment": pay if ok else 0, "intermediary_organization_id": int(mid[0]) if mid else None})
    return {"summary": f"{'Settled' if ok else 'Failed to settle'} with {_name(conn, t)}.", "operation_id": op}


_IN_KIND = {"beating": "beating", "hired_beating": "hired_beating", "smashed_premises": "smashed_premises", "seized_goods": "seized_goods",
            "intimidation": "intimidation", "abduction": "abduction", "duel": "duel",
            # a killing is answered in proportion: the same only when the dead man's side can afford a hired hand, else by a beating
            "public_example": "beating", "hired_killing": "hired_beating", "assault": "beating"}


def retaliate(conn: sqlite3.Connection, oid: int, source: int, incident_id: int, rng: random.Random) -> dict[str, Any]:
    """A real answer to a specific incident, proportionate and in kind: the same sort of blow the source dealt (a killing is answered
    by a beating unless a man was in fact killed), else a racket of the source's suppressed for a while, else its ground contested."""
    from . import underworld_rebuild as uw
    day = _day(conn)
    inc = conn.execute("SELECT metadata_json,incident_kind FROM underworld_incidents WHERE id=?", (incident_id,)).fetchone()
    try:
        meta = json.loads(inc["metadata_json"] or "{}") if inc else {}
    except Exception:
        meta = {}
    style = _IN_KIND.get(str(meta.get("style")))
    dead = meta.get("harm") == "fatal"
    if style is not None and meta.get("style") in ("public_example", "hired_killing") and dead:
        style = "hired_killing" if _fee(conn, oid)[1] >= _fee(conn, oid)[0] else "beating"
    if style in ("beating", "abduction", "duel", "assault") and tp.outfit_class(conn, oid) == "specialist":
        style = "hired_beating"  # a fence or a lender does not send its own men; it pays freelances
    zones = _own_zones(conn, source)
    if style is not None and (style != "smashed_premises" or _client(conn, source, zones[0] if zones else None) is not None):
        r = hostile_move(conn, oid, source, zones[0] if zones else None, rng, style=style, file_contest=False)
        return {"effect": "in_kind", "style": r["style"], "operation_id": r["operation_id"]}
    rk = conn.execute("""SELECT id,racket_kind,zone_id FROM underworld_racket_sites WHERE organization_id=? AND status='active'
                         AND racket_kind<>'protection collections' ORDER BY gross_income_per_30 DESC,id LIMIT 1""", (source,)).fetchone()
    if rk is not None and rng.random() < .55:
        uw.set_racket_status(conn, int(rk["id"]), "suppressed")
        conn.execute("UPDATE underworld_racket_sites SET metadata_json=json_set(COALESCE(metadata_json,'{}'),'$.restore_day',?) WHERE id=?", (day + rng.randint(30, 60), int(rk["id"])))
        return {"effect": "racket_suppressed", "racket_id": int(rk["id"])}
    if rng.random() < .5 or not zones:
        r = hostile_move(conn, oid, source, zones[0] if zones else None, rng, style="hired_beating" if tp.outfit_class(conn, oid) == "specialist" else "beating", file_contest=False)
        return {"effect": "member_beaten", "style": r["style"], "operation_id": r["operation_id"]}
    uw.add_zone_challenger(conn, zones[0], oid, strength=26, severity=30, metadata={"retaliation_for": incident_id})
    return {"effect": "zone_contested", "zone_id": zones[0]}


# -- coercion of clients and debtors ---------------------------------------------------------------------------

_COERCION = {"high-risk debt": ("a debtor", ("labor", "merchant", "artisan", "transport"), "was beaten over what he owed"),
             "brothel protection": ("a house worker", ("hospitality", "artisan"), "was roughed up for the house's protection money"),
             "protection collections": ("a shopkeeper", ("merchant", "artisan", "hospitality"), "was leaned on for his protection money")}


def coercion_turn(conn: sqlite3.Connection, oid: int, rng: random.Random, day: int) -> int:
    """Outfits that live on coercive rackets (debt, brothel and shop protection) hurt the people they squeeze, at a rate set by their
    temperament and the heat they carry. The victim is a person of the city who already existed; the blow is a real harm."""
    if leader_is_player(conn, oid):
        return 0  # nothing hostile happens in his name without his order
    org = conn.execute("SELECT primary_location_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    loc = int(org[0]) if org and org[0] is not None else None
    rackets = [r for r in conn.execute("SELECT racket_kind FROM underworld_racket_sites WHERE organization_id=? AND status='active'", (oid,)) if r[0] in _COERCION]
    if not rackets:
        return 0
    heat = conn.execute("SELECT investigative_heat,violence_heat FROM underworld_heat WHERE organization_id=?", (oid,)).fetchone()
    hp = (float(heat[1]) / 60.0 + float(heat[0]) / 90.0) if heat else 0.0
    p = tp.propensity(conn, oid)
    tol = city_violence(conn, loc) / 100.0
    h = 0.10 * p * math.exp(-hp) * (1.0 - 0.5 * min(1.0, tol))
    n = 0
    for r in rackets:
        if rng.random() >= h:
            continue
        who, domains, what = _COERCION[r[0]]
        victim = None
        if loc is not None:
            from .person_ecology import resolve_background_person
            victim = resolve_background_person(conn, reason="An outfit squeezed its clients", demand_kind="underworld_coercion", location_id=loc,
                                               occupation_domains=domains, min_age=20, max_age=60, allow_elsewhere=False)
        if victim is not None:
            _harm(conn, int(victim), oid, rng, severity=34, intent="hostile", kind="coercion")
            name = str(conn.execute("SELECT name FROM actors WHERE id=?", (int(victim),)).fetchone()[0])
            who_text = f"{name}, {who},"
        else:
            who_text = who
        from .underworld_rebuild import add_heat
        from .simulation import SimEvent, log_event
        add_heat(conn, oid, public=1.0, investigative=.5, violence=1.5)
        log_event(conn, SimEvent(day=day, event_type="underworld_coercion", title=f"Trouble from {_name(conn, oid)}",
                                 summary=f"{who_text[0].upper() + who_text[1:]} {what}.", severity=2, location_id=loc, rumorability=.25))
        n += 1
    return n


# -- the city's own response, and the churn of street gangs ---------------------------------------------------

def restore_suppressed_rackets(conn: sqlite3.Connection, day: int) -> int:
    n = 0
    for r in conn.execute("SELECT id FROM underworld_racket_sites WHERE status='suppressed' AND json_extract(metadata_json,'$.restore_day') IS NOT NULL AND json_extract(metadata_json,'$.restore_day')<=?", (day,)).fetchall():
        conn.execute("UPDATE underworld_racket_sites SET status='active',metadata_json=json_remove(metadata_json,'$.restore_day') WHERE id=?", (int(r[0]),))
        n += 1
    return n


def city_crackdowns(conn: sqlite3.Connection, day: int) -> int:
    """Rising violence in a city brings the watch, cultivated officers and a magistrate's crackdown; the outfits that fed it turn cautious.
    How much violence a city tolerates grows with the number of outfits it holds; the chance of a crackdown rises smoothly with the
    tension above that, and falls just after the last one (the watch has been through). Outfits are hit in proportion to the
    violence heat they carry."""
    from . import underworld_rebuild as uw
    done = 0
    for r in conn.execute("""SELECT DISTINCT o.primary_location_id loc FROM underworld_incidents i JOIN underworld_organizations o ON o.id=i.target_organization_id
                             WHERE o.primary_location_id IS NOT NULL AND i.day>? AND i.incident_kind IN ('attack_on_member','attack_on_client')""", (day - 90,)).fetchall():
        loc = int(r["loc"])
        tension = city_tension(conn, loc, day)
        n_out = int(conn.execute("SELECT COUNT(*) FROM underworld_organizations WHERE primary_location_id=? AND status IN ('active','strained','fragmented')", (loc,)).fetchone()[0])
        tolerance = 0.45 * math.sqrt(max(1, n_out))
        key = f"uw_crackdown:{loc}"
        last = conn.execute("SELECT value FROM engine_meta WHERE key=?", (key,)).fetchone()
        rest = 1.0 - math.exp(-(day - int(last[0])) / 60.0) if last else 1.0
        rng = _rng(conn, loc, day)
        p = rest / (1.0 + math.exp(-(tension - tolerance) / max(0.2, 0.25 * tolerance)))
        if rng.random() >= p:
            continue
        conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES (?,?)", (key, str(day)))
        heats = conn.execute("""SELECT o.id,h.violence_heat vh FROM underworld_heat h JOIN underworld_organizations o ON o.id=h.organization_id
                                WHERE o.primary_location_id=? AND o.status IN ('active','strained','fragmented') ORDER BY h.violence_heat DESC,o.id""", (loc,)).fetchall()
        top_heat = float(heats[0]["vh"]) if heats else 0.0
        for t in heats:
            oid = int(t["id"])
            if t is not heats[0] and float(t["vh"]) < 0.5 * top_heat:
                continue
            conn.execute("INSERT INTO underworld_enforcement_actions(organization_id,day,action_kind,severity,result,metadata_json) VALUES (?,?,?,?,?,?)",
                         (oid, day, "city_crackdown", 60, "applied", json.dumps({"city_tension": round(tension, 2)})))
            rk = conn.execute("SELECT id FROM underworld_racket_sites WHERE organization_id=? AND status='active' ORDER BY gross_income_per_30 DESC,id LIMIT 1", (oid,)).fetchone()
            if rk:
                uw.set_racket_status(conn, int(rk[0]), "suppressed")
                conn.execute("UPDATE underworld_racket_sites SET metadata_json=json_set(COALESCE(metadata_json,'{}'),'$.restore_day',?) WHERE id=?", (day + rng.randint(40, 70), int(rk[0])))
            conn.execute("UPDATE underworld_heat SET violence_heat=MAX(0,violence_heat-25),public_heat=MAX(0,public_heat-10) WHERE organization_id=?", (oid,))
            tp.adjust(conn, oid, -.15)
        name = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()[0]
        from .simulation import SimEvent, log_event
        log_event(conn, SimEvent(day=day, event_type="underworld_city_crackdown", title=f"Crackdown in {name}",
                                 summary=f"After the fighting, the watch and the magistrate moved against the outfits of {name}.", severity=3, location_id=loc))
        done += 1
    return done


def _weakness(conn: sqlite3.Connection, oid: int) -> float:
    prof = conn.execute("SELECT COALESCE(core_members,0)+COALESCE(active_members,0) FROM underworld_membership_profiles WHERE organization_id=?", (oid,)).fetchone()
    full = float(prof[0]) if prof and prof[0] is not None else 10.0
    org = conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    w = 0.0
    if full < 7:
        w += (7 - full) / 7 * .6
    if not conn.execute("SELECT 1 FROM underworld_zone_claims WHERE organization_id=? AND claim_kind='controller' AND status='active'", (oid,)).fetchone():
        w += .3
    if float(org[0]) < .5:
        w += .2
    row = tp.ensure_temperament(conn, oid)
    if tp.effective_current(conn, oid) < float(row["base"]) - .08:
        w += .1
    lost = conn.execute("SELECT COUNT(*) FROM underworld_operations WHERE organization_id=? AND day>=? AND result IN ('repulsed','failed','lost')", (oid, _day(conn) - 180)).fetchone()[0]
    w += min(.3, .1 * int(lost))
    return w


def dissolve_street_gang(conn: sqlite3.Connection, oid: int, day: int, reason: str) -> None:
    from . import underworld_rebuild as uw
    from .person_ecology import make_former_member_ordinary
    from .simulation import SimEvent, log_event
    name = _name(conn, oid)
    loc = conn.execute("SELECT primary_location_id FROM underworld_organizations WHERE id=?", (oid,)).fetchone()[0]
    conn.execute("UPDATE underworld_organizations SET status='destroyed',updated_day=? WHERE id=?", (day, oid))
    conn.execute("UPDATE underworld_zone_claims SET status='lost' WHERE organization_id=? AND status='active'", (oid,))
    uw._refresh_territory_summary(conn, oid)
    conn.execute("UPDATE underworld_crews SET status='destroyed' WHERE organization_id=?", (oid,))
    conn.execute("UPDATE underworld_protection_accounts SET status='ended' WHERE protector_organization_id=? AND status='active'", (oid,))
    conn.execute("UPDATE underworld_business_links SET status='ended' WHERE organization_id=? AND status='active'", (oid,))
    for rk in conn.execute("SELECT id FROM underworld_racket_sites WHERE organization_id=? AND status IN ('active','suppressed')", (oid,)).fetchall():
        uw.set_racket_status(conn, int(rk[0]), "abandoned")
    me = _player_actor(conn)
    for p in conn.execute("SELECT actor_id FROM underworld_personnel WHERE organization_id=? AND status='active'", (oid,)).fetchall():
        conn.execute("UPDATE underworld_personnel SET status='retired' WHERE actor_id=?", (int(p[0]),))
        if me is None or int(p[0]) != me:  # the protagonist is not rewritten by his gang's fall
            make_former_member_ordinary(conn, int(p[0]))
    log_event(conn, SimEvent(day=day, event_type="underworld_outfit_collapsed", title=f"{name} has broken up",
                             summary=f"{name} came apart ({reason}); its men drifted back to ordinary life or to other crews.", severity=2, location_id=loc))


def found_street_gang(conn: sqlite3.Connection, lid: int, zid: int, rng: random.Random, day: int, serial: int) -> int | None:
    from . import underworld_ecology as ue
    from .simulation import SimEvent, log_event
    from .underworld_rebuild import create_crew, create_personnel, racket_kind_options, set_zone_controller
    conn.execute("SAVEPOINT uw_new_gang")
    try:
        place = conn.execute("SELECT name FROM locations WHERE id=?", (lid,)).fetchone()[0]
        name = ue._unique_name(conn, lambda k: f"{rng.choice(ue._GANG_PREFIX)} {rng.choice(ue._GANG_WORDS)}" + ("" if k < 40 else f" of {place}"))
        members = rng.randint(7, 16)
        oid = ue._new_org(conn, f"uw-churn:{lid}:{day}:{serial}", "gang", name, lid, members,
                          {"source": "procedural", "role": "street_gang", "founded_day": day, "calibration": "gap4b_churn"}, violence=(25, 55), rng=rng)
        boss = create_personnel(conn, oid, role_kind="boss", rng=rng, actor_id=ue._person(
            conn, lid, "boss", strict=True, oid=oid, rng=rng, sex=ue._wanted_sex(conn, "violent", ue.P_MALE_VIOLENT, rng)))
        ue._note_sex(conn, "violent", boss)
        conn.execute("UPDATE underworld_organizations SET founder_actor_id=?,current_leader_actor_id=? WHERE id=?", (boss, boss, oid))
        set_zone_controller(conn, zid, oid, strength=rng.uniform(40, 58), local_support=rng.uniform(28, 55), fear=rng.uniform(40, 66), metadata={"founded_gang": True})
        lead = create_personnel(conn, oid, role_kind="crew_leader", membership_status="member", rng=rng,
                                actor_id=ue._person(conn, lid, "crew_leader", strict=False, oid=oid, rng=rng, sex=ue._wanted_sex(conn, "violent", ue.P_MALE_VIOLENT, rng)))
        ue._note_sex(conn, "violent", lead)
        create_crew(conn, oid, f"{name} Crew", leader_actor_id=lead, home_zone_id=zid, size_estimate=members, rng=rng)
        ue._rackets(conn, oid, racket_kind_options(conn, zid, rng, count=rng.randint(1, 2)), rng, zid)
        conn.execute("RELEASE SAVEPOINT uw_new_gang")
    except ue._NoPerson:
        conn.execute("ROLLBACK TO SAVEPOINT uw_new_gang"); conn.execute("RELEASE SAVEPOINT uw_new_gang")
        return None
    from .world_pressure import seed_baseline_relations, seed_named_personnel
    seed_named_personnel(conn, oid, rng)
    seed_baseline_relations(conn, only_org=oid)
    log_event(conn, SimEvent(day=day, event_type="underworld_new_gang", title=f"A new gang in {place}: {name}",
                             summary=f"A crew calling itself {name} has begun to hold a corner of {place}.", severity=2, location_id=lid))
    return oid


def next_pressure_day(conn: sqlite3.Connection) -> int:
    """The next day the world-level monthly work (restoring suppressed rackets, city crackdowns, gang churn) falls due."""
    last = conn.execute("SELECT value FROM engine_meta WHERE key='uw_churn_day'").fetchone()
    return (int(last[0]) if last else 0) + 30


def monthly_world_pressure(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    """Runs on its own schedule (never on whichever day another outfit happens to be due), so every clock driver agrees."""
    if day < next_pressure_day(conn):
        return {"collapsed": 0, "founded": 0, "crackdowns": 0}
    restore_suppressed_rackets(conn, day)
    expire_attempts(conn, day)
    crackdowns = city_crackdowns(conn, day)
    churn = street_gang_churn(conn, day)
    return {**churn, "crackdowns": crackdowns}


def street_gang_churn(conn: sqlite3.Connection, day: int) -> dict[str, int]:
    """Weak or beaten street gangs collapse and new ones rise where there is room (canon [1734]: they rise and disappear quickly)."""
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('uw_churn_day',?)", (str(day),))
    rng = random.Random(int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0]) * 7 + day * 131)
    collapsed = founded = 0
    for r in conn.execute("""SELECT id FROM underworld_organizations WHERE status IN ('active','strained','fragmented')
                             AND json_extract(metadata_json,'$.role')='street_gang' ORDER BY id""").fetchall():
        oid = int(r[0])
        w = _weakness(conn, oid)
        if (w >= .3 and rng.random() < .30) or rng.random() < .006:  # the weak go quickly; any street gang can fold on a bad month
            dissolve_street_gang(conn, oid, day, "beaten and spent" if w >= .8 else "worn thin")
            collapsed += 1
    cities = conn.execute("""SELECT DISTINCT z.city_location_id FROM underworld_zones z WHERE z.status='active' ORDER BY 1""").fetchall()
    from .underworld_ecology import _character
    for c in cities:
        lid = int(c[0])
        free = [z for z in _city_zones(conn, lid) if _controller(conn, z) is None]
        if not free:
            continue
        try:
            street = float(_character(conn, lid)[0]["street"])
        except Exception:
            street = .3
        p = .014 * min(1.5, street * 1.6) * min(1.0, len(free) / 2.0)
        if rng.random() < p:
            if found_street_gang(conn, lid, free[rng.randrange(len(free))], rng, day, founded) is not None:
                founded += 1
    return {"collapsed": collapsed, "founded": founded}
