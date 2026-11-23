"""The field shifts (politics P1).

Every holder in the field weighs its own pressure each week: lost patronage lines, races lost by the men it backed, its seat-holders
indicted, the public's regard of its head. A holder that slips has one stake weakened, and the stake may pass to whichever other
holder the drivers favour; a stake that is gone is taken up afresh by the rival that looks best. A unit leader may walk out with his
men and the stakes in his districts through the org core's split. When an organisation ends, what it held is carried on by a
successor or closed, and those on the other side are told. Nothing here names a holder or a post: who rises is whoever the numbers say.
"""
from __future__ import annotations

import json
import math
import random
import re
import sqlite3

from . import civic_field, civic_seams, design, electorate, orgs, races
from .design import figure
from .world_package import package_for, politics_rules


def _sd(conn) -> dict:
    return politics_rules(package_for(conn)).get("field_shift") or {}


def _f(conn, name, default: float = 0.0) -> float:
    return float(figure(conn, name, default)) if name else default


def _rng(conn, *key) -> random.Random:
    return random.Random(f"{design.run_seed(conn)}:shift:" + ":".join(str(k) for k in key))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


_SEEN: dict = {}  # (connection, holder, day) -> regard, read once a day however many drivers ask (the impressions are lazy)


def _impression(conn, holder_kind: str, holder_id: int, day: int) -> float:
    """The electorate's regard of the holder's face (its head, or the person himself), averaged over the groups."""
    who = int(holder_id) if holder_kind == "actor" else orgs.head_of(conn, int(holder_id))
    if who is None:
        return 0.0
    key = (id(conn), int(who), int(day))
    if key not in _SEEN:
        if len(_SEEN) > 4000:
            _SEEN.clear()
        gs = electorate.groups(conn)
        _SEEN[key] = sum(electorate.regard(conn, int(g["id"]), int(who), day) for g in gs) / max(1, len(gs))
    return _SEEN[key]


def pressure(conn, holder_kind: str, holder_id: int, day: int) -> dict[str, float]:
    """The drivers of a holder losing ground, each read from the world."""
    d = _sd(conn)
    since = int(day) - int(_f(conn, d.get("window_days"), 180))
    lost = conn.execute("SELECT COUNT(*) FROM field_holdings WHERE holder_kind=? AND holder_id=? AND stake_kind='patronage' AND ended_day IS NOT NULL AND ended_day>=?",
                        (holder_kind, int(holder_id), since)).fetchone()[0]
    defeats = 0
    indicted = 0
    if holder_kind == "org":
        for r in conn.execute("""SELECT r.result_json,c.actor_id FROM race_candidates c JOIN races r ON r.id=c.race_id
                                 WHERE c.party_org_id=? AND r.status='decided' AND r.election_day>=?""", (int(holder_id), since)).fetchall():
            try:
                win = json.loads(r[0]).get("winner")
            except (TypeError, ValueError):
                win = None
            defeats += 1 if win is not None and int(win) != int(r[1]) else 0
        men = [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active'", (int(holder_id),))]
        if men:
            q = ",".join("?" * len(men))
            indicted = int(conn.execute(f"SELECT COUNT(*) FROM (SELECT offender_actor_id AS x FROM crime_reports WHERE offender_actor_id IN ({q}) AND day>=? "
                                        f"UNION SELECT actor_id FROM sentences WHERE actor_id IN ({q}) AND start_day>=?)", (*men, since, *men, since)).fetchone()[0])
    return {"lost": float(lost), "defeat": float(defeats), "indicted": math.log1p(indicted), "impression": -_impression(conn, holder_kind, holder_id, day)}


def _score(conn, rival: int, day: int, rng: random.Random) -> float:
    rd = _sd(conn).get("rival") or {}
    return (_f(conn, rd.get("strength")) * civic_field.strength(conn, "org", rival) + _f(conn, rd.get("regard")) * _impression(conn, "org", rival, day)
            + rng.gauss(0.0, _f(conn, rd.get("noise_sd"))))


def _rivals(conn, exclude: tuple[str, int] | None) -> list[int]:
    """Every living organisation that has ever held a stake in the field (one that lost them all may come back)."""
    return [int(r[0]) for r in conn.execute("SELECT DISTINCT holder_id FROM field_holdings WHERE holder_kind='org' ORDER BY holder_id")
            if ("org", int(r[0])) != exclude and orgs.is_living(conn, int(r[0]))]


def _pick(conn, scores: dict[int, float], rng: random.Random) -> int:
    """One rival, weighted by how good each looks (a softmax), so a vacuum does not always fall the same way."""
    temp = max(1e-6, _f(conn, (_sd(conn).get("vacuum") or {}).get("pick_temp"), 1.0))
    keys = sorted(scores)
    top = max(scores.values())
    w = [math.exp((scores[k] - top) / temp) for k in keys]
    u = rng.random() * sum(w)
    acc = 0.0
    for k, wi in zip(keys, w):
        acc += wi
        if u <= acc:
            return k
    return keys[-1]


def _vacant(conn) -> list[tuple[str, str]]:
    """Stakes that have been held and now have no holder."""
    return [(str(r[0]), str(r[1])) for r in conn.execute(
        """SELECT DISTINCT stake_kind,stake_ref FROM field_holdings f WHERE stake_kind IN ('party_office','delivery','sponsor')
           AND NOT EXISTS (SELECT 1 FROM field_holdings g WHERE g.stake_kind=f.stake_kind AND g.stake_ref=f.stake_ref AND g.ended_day IS NULL) ORDER BY 1,2""")]


def weekly_shift(conn, day: int) -> dict:
    """One draw per holder; see the module text. Returns what moved."""
    d = _sd(conn)
    out = {"weakened": 0, "transferred": 0, "taken_up": 0, "walkouts": 0}
    if not d:
        return out
    _SEEN.clear()
    holders = [(str(r[0]), int(r[1])) for r in conn.execute("SELECT DISTINCT holder_kind,holder_id FROM field_holdings WHERE ended_day IS NULL ORDER BY 1,2")]
    rd = d.get("rival") or {}
    for hk, hid in holders:
        p = pressure(conn, hk, hid, day)
        z = _f(conn, d.get("base")) + sum(_f(conn, d.get(k)) * v for k, v in p.items())
        rng = _rng(conn, hk, hid, day)
        if rng.random() < _sigmoid(z):
            rows = civic_field.holdings_of(conn, hk, hid)
            if rows:
                stake = rows[rng.randrange(len(rows))]
                sid, kind, ref = int(stake["id"]), stake["stake_kind"], stake["stake_ref"]
                civic_field.weaken(conn, sid, _f(conn, d.get("delta")), day=int(day), cause_kind="pressure")
                out["weakened"] += 1
                rivals = _rivals(conn, (hk, hid))
                if rivals:
                    scores = {r: _score(conn, r, int(day), rng) for r in rivals}
                    best = _pick(conn, scores, rng)
                    gone = conn.execute("SELECT ended_day FROM field_holdings WHERE id=?", (sid,)).fetchone()[0] is not None
                    if gone:
                        civic_field._open(conn, "org", best, kind, ref, _f(conn, rd.get("start"), 0.3), int(day), "pressure", sid)
                        out["taken_up"] += 1
                    else:
                        mine = civic_field.strength(conn, hk, hid) + _f(conn, rd.get("regard")) * _impression(conn, hk, hid, day)
                        if rng.random() < _sigmoid(_f(conn, rd.get("take")) * (scores[best] - mine)):
                            civic_field.transfer(conn, sid, "org", best, day=int(day), cause_kind="rival", cause_id=hid)
                            out["transferred"] += 1
        if hk == "org":
            out["walkouts"] += _walk_draws(conn, hid, p, int(day))
    vac = d.get("vacuum") or {}
    rivals = _rivals(conn, None)
    for kind, ref in _vacant(conn):
        rng = _rng(conn, "vacuum", kind, ref, day)
        if rivals and rng.random() < _sigmoid(_f(conn, vac.get("base"), -3.0)):
            best = _pick(conn, {r: _score(conn, r, int(day), rng) for r in rivals}, rng)
            civic_field._open(conn, "org", best, kind, ref, _f(conn, rd.get("start"), 0.3), int(day), "vacuum")
            out["taken_up"] += 1
    return out


def _unit_leaders(conn, org: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT id,leader_actor_id FROM org_units WHERE org_actor_id=? AND leader_actor_id IS NOT NULL ORDER BY id", (int(org),)).fetchall()


def _walk_draws(conn, org: int, p: dict, day: int) -> int:
    w = _sd(conn).get("walkout") or {}
    if not w:
        return 0
    head = orgs.head_of(conn, int(org))
    n = 0
    for u in _unit_leaders(conn, org):
        lead = int(u["leader_actor_id"])
        if lead == head or races._is_player(conn, lead):
            continue  # the engine never walks the player out
        r = conn.execute("SELECT ambition,loyalty FROM actor_drives WHERE actor_id=?", (lead,)).fetchone()
        amb, loy = (float(r[0]), float(r[1])) if r else (0.5, 0.5)
        z = (_f(conn, w.get("base")) + _f(conn, w.get("ambition")) * amb + _f(conn, w.get("disloyal")) * (1.0 - loy)
             + _f(conn, w.get("pressure")) * (p["lost"] + p["defeat"] + p["indicted"]))
        if _rng(conn, "walk", org, lead, day).random() < _sigmoid(z) and factional_walkout(conn, org, int(u["id"]), day) is not None:
            n += 1
    return n


def _unit_stakes(conn, org: int, leader: int) -> list[sqlite3.Row]:
    """The org's stakes in the districts whose organisation this man leads (the n-th district is the n-th unit's)."""
    leaders = [int(r["leader_actor_id"]) for r in _unit_leaders(conn, org)]
    out = []
    for s in civic_field.holdings_of(conn, "org", int(org)):
        ref = str(s["stake_ref"])
        if s["stake_kind"] == "delivery":
            n = civic_field._district_no(ref)
        elif s["stake_kind"] == "party_office":
            m = re.search(r"-(\d+)$", ref)
            n = int(m.group(1)) if m else None
        else:
            n = None
        if n is not None and leaders and leaders[(n - 1) % len(leaders)] == int(leader):
            out.append(s)
    return out


def factional_walkout(conn, org: int, unit_id: int, day: int) -> int | None:
    """A unit leader takes his unit's men and the stakes in his districts out through the org core's split; returns the new organisation
    (None when the split cannot be made). The same for any leader, the protagonist included."""
    from . import org_coup
    u = conn.execute("SELECT * FROM org_units WHERE id=? AND org_actor_id=?", (int(unit_id), int(org))).fetchone()
    if u is None or u["leader_actor_id"] is None:
        return None
    leader = int(u["leader_actor_id"])
    stakes = _unit_stakes(conn, int(org), leader)
    men = [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND unit_id=?", (int(org), int(unit_id)))]
    new = org_coup.split_org(conn, int(org), men, leader, int(day), {})
    if new is None:
        return None
    for s in stakes:
        civic_field.transfer(conn, int(s["id"]), "org", int(new), day=int(day), cause_kind="walkout", cause_id=int(org))
    return int(new)


def carry_on_end(conn, org: int, day: int, successor: int | None) -> dict:
    """An organisation ends or is absorbed: each stake, patronage line and open ledger entry of it goes to the successor, or ends; whoever
    stood on the other side is told through the delivery ledger."""
    out = {"stakes": 0, "lines": 0, "ledger": 0, "told": 0}
    for s in civic_field.holdings_of(conn, "org", int(org)):
        if successor is not None:
            civic_field.transfer(conn, int(s["id"]), "org", int(successor), day=int(day), cause_kind="carried_on", cause_id=int(org))
        else:
            conn.execute("UPDATE field_holdings SET ended_day=?,cause_kind='ended',cause_id=? WHERE id=?", (int(day), int(org), int(s["id"])))
        out["stakes"] += 1
    for h in conn.execute("SELECT id FROM org_holdings WHERE org_actor_id=?", (int(org),)).fetchall():
        out["lines"] += int(conn.execute("SELECT COUNT(*) FROM org_lines WHERE holding_id=? AND status='active'", (int(h[0]),)).fetchone()[0])
        if successor is not None:
            conn.execute("UPDATE org_holdings SET org_actor_id=? WHERE id=?", (int(successor), int(h[0])))
        else:
            conn.execute("UPDATE org_lines SET status='ended',ended_day=? WHERE holding_id=? AND status='active'", (int(day), int(h[0])))
    ref = f"org:{int(org)}"
    told: set[int] = set()
    for t in conn.execute("SELECT * FROM agreement_terms WHERE status='active' AND (debtor_ref=? OR creditor_ref=?) ORDER BY id", (ref, ref)).fetchall():
        other = t["creditor_ref"] if t["debtor_ref"] == ref else t["debtor_ref"]
        if successor is not None:
            col = "debtor_ref" if t["debtor_ref"] == ref else "creditor_ref"
            conn.execute(f"UPDATE agreement_terms SET {col}=? WHERE id=?", (f"org:{int(successor)}", int(t["id"])))
        else:
            conn.execute("UPDATE agreement_terms SET status='orphaned' WHERE id=?", (int(t["id"]),))
        out["ledger"] += 1
        if str(other).startswith("person:"):
            told.add(int(str(other).split(":")[1]))
    head = orgs.head_of(conn, int(org))
    if head is not None:
        told.add(int(head))
    name = conn.execute("SELECT name FROM actors WHERE id=?", (int(org),)).fetchone()[0]
    for a in sorted(told):
        civic_seams.push(conn, a, "org_ended", f"{name} is no more" + (" and what it held has gone to its successor" if successor is not None else ""), int(day), {"org": int(org)})
        out["told"] += 1
    return out
