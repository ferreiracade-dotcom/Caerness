"""Prison J1.4: how a man inside stays in touch with the outside, and what it is worth.

A channel is a way a man inside reaches people outside: a visit from kin or a friend, a letter, a lawyer, a trusted man of his outfit,
a smuggled note, a phone, a guard who has been bought. Each has a quality (how well it carries a message) and a watched share (how
likely the staff are to read or hear it). Visits and letters happen by a weighed pull (kin tie, how close the two are, how far the
place is, what it costs), never on a schedule. Orders sent from inside by a man who holds a seat outside can be overheard, and that is
a report like any other to the law. `channel_grip` reads how well he still reaches the outside, and the outside weighs that (J1.5).

Every number is package data (`prison.json`, `channels`); the module has no player branch: a visitor or an inmate is any actor.
"""
from __future__ import annotations

import math
import sqlite3

from .prison import _event, _figure, _living, _name, _rng, rules


def _cfg(conn: sqlite3.Connection) -> dict:
    return rules(conn).get("channels") or {}


def _kin(conn: sqlite3.Connection, actor_id: int) -> dict[int, float]:
    """Living relatives and a spouse of the man, each with the pull of the tie (data `kin_pull` by kind of kin)."""
    pull = {k: _figure(v) for k, v in (_cfg(conn).get("kin_pull") or {}).items() if isinstance(v, dict)}
    out: dict[int, float] = {}
    for r in conn.execute("""SELECT actor_a_id,actor_b_id,kin_kind FROM kinship_links WHERE ended_day IS NULL AND legal_status<>'former'
                             AND (actor_a_id=? OR actor_b_id=?)""", (int(actor_id), int(actor_id))).fetchall():
        other = int(r["actor_b_id"]) if int(r["actor_a_id"]) == int(actor_id) else int(r["actor_a_id"])
        out[other] = max(out.get(other, 0.0), pull.get(r["kin_kind"], pull.get("other", 0.0)))
    for r in conn.execute("""SELECT actor_a_id,actor_b_id FROM typed_relationship_facts WHERE status='active' AND relation_type='spouse'
                             AND (actor_a_id=? OR actor_b_id=?)""", (int(actor_id), int(actor_id))).fetchall():
        other = int(r["actor_b_id"]) if int(r["actor_a_id"]) == int(actor_id) else int(r["actor_a_id"])
        out[other] = max(out.get(other, 0.0), pull.get("spouse", 0.0))
    return out


def _friends(conn: sqlite3.Connection, actor_id: int, n: int) -> dict[int, float]:
    """The few people outside who feel most for him (their own affection and trust of him), as a pull."""
    scale = _figure(_cfg(conn).get("friend_pull"), 0.0)
    out: dict[int, float] = {}
    for r in conn.execute("""SELECT actor_a_id,MAX(affection,trust) AS feel FROM relationships WHERE actor_b_id=? AND MAX(affection,trust)>0
                             ORDER BY feel DESC, actor_a_id LIMIT ?""", (int(actor_id), int(n))).fetchall():
        out[int(r["actor_a_id"])] = scale * float(r["feel"]) / 100.0
    return out


def _far(conn: sqlite3.Connection, facility_id: int) -> bool:
    """The facility is off the map (far from the city), so visits are rarer and dearer."""
    r = conn.execute("SELECT json_extract(metadata_json,'$.off_map') FROM facilities WHERE id=?", (int(facility_id),)).fetchone()
    return bool(r and r[0])


def _outside(conn: sqlite3.Connection, actor_id: int) -> bool:
    return _living(conn, actor_id) and conn.execute("SELECT 1 FROM inmate_stays WHERE actor_id=? AND status='inside'", (int(actor_id),)).fetchone() is None


def _stay(conn: sqlite3.Connection, stay_id: int):
    return conn.execute("SELECT * FROM inmate_stays WHERE id=?", (int(stay_id),)).fetchone()


def open_channel(conn: sqlite3.Connection, stay_id: int, kind: str, outside_actor_id: int | None, day: int) -> int:
    """Open (or find the open) channel of this kind between the man and this outside person. Its quality, watch and cost are the data's."""
    spec = (_cfg(conn).get("kinds") or {}).get(kind)
    if spec is None:
        raise KeyError(f"no channel kind {kind!r} in the package's prison data")
    old = conn.execute("SELECT id FROM prison_channels WHERE stay_id=? AND kind=? AND status='open' AND COALESCE(outside_actor_id,0)=COALESCE(?,0)",
                       (int(stay_id), kind, outside_actor_id)).fetchone()
    if old is not None:
        return int(old[0])
    return int(conn.execute("INSERT INTO prison_channels(stay_id,kind,outside_actor_id,quality,watched,cost_weekly,since_day) VALUES (?,?,?,?,?,?,?)",
                            (int(stay_id), kind, outside_actor_id, _figure(spec["quality"]), _figure(spec["watched"]), _figure(spec.get("cost_weekly"), 0.0), int(day))).lastrowid)


def _carries_orders(conn: sqlite3.Connection, actor_id: int) -> bool:
    """He holds a seat outside the prison that has men under it: what he sends out is an order."""
    return conn.execute("""SELECT 1 FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id
                           WHERE s.actor_id=? AND s.status IN ('active','held') AND p.sphere<>'prison'
                             AND EXISTS (SELECT 1 FROM org_seats u WHERE u.org_actor_id=s.org_actor_id AND u.superior_actor_id=s.actor_id AND u.status='active') LIMIT 1""",
                        (int(actor_id),)).fetchone() is not None


def contact(conn: sqlite3.Connection, channel_id: int, day: int, *, orders: bool | None = None, from_inside: bool = True) -> dict:
    """One contact on a channel. It moves the relationship between the two; a contact that carries a seat-holder's orders on a watched
    channel can be overheard, and that is a case. `orders` None means: carried when he holds a seat with men under it, by the data's share."""
    from .crime_response import open_report
    from .relationships import adjust_relationship_pair
    ch = conn.execute("SELECT * FROM prison_channels WHERE id=? AND status='open'", (int(channel_id),)).fetchone()
    if ch is None:
        return {"ok": False, "reason": "channel closed"}
    st = _stay(conn, ch["stay_id"])
    if st is None or st["status"] != "inside":
        return {"ok": False, "reason": "not inside"}
    cfg = _cfg(conn)
    man, other = int(st["actor_id"]), ch["outside_actor_id"]
    rng = _rng(conn, "contact", f"{day}:{channel_id}")
    if orders is None:
        orders = _carries_orders(conn, man) and rng.random() < _figure(cfg.get("orders_share"), 0.0)
    over = False
    if orders and rng.random() < _figure(cfg.get("intercept_rate"), 0.0) * float(ch["watched"]):
        over = True
    kind = "orders" if orders else str(ch["kind"])
    who = _name(conn, other) if other is not None else "his lawyer"
    cid = int(conn.execute("INSERT INTO prison_contacts(day,stay_id,channel_id,kind,from_actor_id,to_actor_id,summary,intercepted) VALUES (?,?,?,?,?,?,?,?)",
                           (int(day), int(st["id"]), int(channel_id), kind, man if from_inside else other, other if from_inside else man,
                            f"{_name(conn, man)} and {who}: {ch['kind']}" + (", overheard" if over else ""), 1 if over else 0)).lastrowid)
    if other is not None and not conn.execute("SELECT 1 FROM actors WHERE id=?", (int(other),)).fetchone() is None:
        bump = {k: _figure(v) for k, v in (cfg.get("contact_gain") or {}).items() if isinstance(v, dict)}
        adjust_relationship_pair(conn, int(other), man, int(day), symmetric={f"{k}_delta": v * float(ch["quality"]) for k, v in bump.items()})
    if over:
        fac = conn.execute("SELECT location_id,id FROM facilities WHERE id=?", (int(st["facility_id"]),)).fetchone()
        _event(conn, day, int(fac["id"]), "overheard", man, other, 0.0, f"{_name(conn, man)}'s orders were overheard")
        open_report(conn, crime_kind=str(cfg.get("overheard_kind") or "racket"), day=int(day), offender_actor_id=man, location_id=fac["location_id"], public=False)
    return {"ok": True, "contact_id": cid, "intercepted": over, "orders": bool(orders), "kind": kind}


def visit(conn: sqlite3.Connection, visitor: int, inmate: int, day: int) -> dict:
    """Someone visits a man inside. The same call whoever the visitor is and whoever is inside; it costs the visitor, opens (or finds) the
    visit channel between them, and is one contact on it."""
    from . import ledger
    st = conn.execute("SELECT * FROM inmate_stays WHERE actor_id=? AND status='inside'", (int(inmate),)).fetchone()
    if st is None:
        return {"ok": False, "reason": "he is not inside"}
    if int(visitor) == int(inmate) or not _outside(conn, int(visitor)):
        return {"ok": False, "reason": "the visitor is not free to come"}
    cost = _figure((_cfg(conn).get("visit") or {}).get("cost"), 0.0) * (1.0 + (_figure((_cfg(conn).get("visit") or {}).get("far_cost"), 0.0) if _far(conn, st["facility_id"]) else 0.0))
    if cost > 0:
        ledger.spend(conn, ("person", int(visitor)), cost, purpose="a prison visit", allow_partial=True)
    ch = open_channel(conn, int(st["id"]), "visit", int(visitor), int(day))
    return contact(conn, ch, int(day), from_inside=False)


def _pull_of(conn: sqlite3.Connection, other: int, kin: dict, friends: dict) -> float:
    return max(kin.get(other, 0.0), friends.get(other, 0.0))


def _routes(conn: sqlite3.Connection, st, day: int) -> int:
    """Open the man's other channels as the week allows: a lawyer when his case has one paid, a trusted man of his outfit, and, where
    the place is corrupt, a phone, a smuggled note and a guard (each with its own weekly chance and its cost)."""
    from . import ledger
    cfg = _cfg(conn)
    kinds = cfg.get("kinds") or {}
    a = int(st["actor_id"])
    opened = 0
    fac = conn.execute("SELECT * FROM facilities WHERE id=?", (int(st["facility_id"]),)).fetchone()
    import json as _json
    state = _json.loads(fac["character_json"] or "{}")
    if st["case_id"] is not None:
        cs = conn.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (int(st["case_id"]),)).fetchone()
        if cs is not None and float((_json.loads(cs[0] or "{}")).get("lawyer_fee") or 0.0) > 0:
            had = conn.execute("SELECT 1 FROM prison_channels WHERE stay_id=? AND kind='lawyer'", (int(st["id"]),)).fetchone()
            open_channel(conn, int(st["id"]), "lawyer", None, int(day))
            opened += 0 if had else 1
    for kind in ("trusted_man", "phone", "smuggled_note", "bought_guard"):
        spec = kinds.get(kind) or {}
        if not spec or conn.execute("SELECT 1 FROM prison_channels WHERE stay_id=? AND kind=? AND status='open'", (int(st["id"]), kind)).fetchone():
            continue
        p = 1.0 - math.exp(-_figure(spec["open_rate"]) * (state.get(spec.get("by") or "corruption", 1.0) if spec.get("by") else 1.0))
        if _rng(conn, "route", f"{day}:{a}:{kind}").random() >= p:
            continue
        outside = None
        if kind == "trusted_man":
            r = conn.execute("""SELECT s.superior_actor_id FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id
                                WHERE s.actor_id=? AND s.status IN ('active','held') AND p.sphere<>'prison' AND s.superior_actor_id IS NOT NULL ORDER BY s.standing DESC LIMIT 1""", (a,)).fetchone()
            if r is None or not _outside(conn, int(r[0])):
                continue
            outside = int(r[0])
        cost = _figure(spec.get("cost_weekly"), 0.0)
        if cost > 0 and ledger.balance(conn, ("person", a)) < cost:
            continue
        open_channel(conn, int(st["id"]), kind, outside, int(day))
        opened += 1
    return opened


def _upkeep(conn: sqlite3.Connection, day: int) -> int:
    """A channel that costs money is paid from the man's purse each week; one he cannot pay for closes."""
    from . import ledger
    n = 0
    for ch in conn.execute("""SELECT c.*,s.actor_id AS man FROM prison_channels c JOIN inmate_stays s ON s.id=c.stay_id
                              WHERE c.status='open' AND c.cost_weekly>0 AND s.status='inside' ORDER BY c.id""").fetchall():
        paid = ledger.spend(conn, ("person", int(ch["man"])), float(ch["cost_weekly"]), purpose="a channel out of prison", allow_partial=True)
        if paid < float(ch["cost_weekly"]) - 1e-6:
            conn.execute("UPDATE prison_channels SET status='closed' WHERE id=?", (int(ch["id"]),))
            n += 1
    return n


def weekly(conn: sqlite3.Connection, day: int) -> dict:
    """The week's contact for every man inside: each person who would come comes or writes by the weighed pull (kin tie or how he is felt
    for, the distance of the place, the data's rate); his other channels open and are paid for; those carrying orders may be overheard."""
    cfg = _cfg(conn)
    if not cfg:
        return {"visits": 0, "letters": 0, "routes": 0, "closed": 0}
    vis, let, routes = 0, 0, 0
    vcfg = cfg.get("visit") or {}
    for st in conn.execute("SELECT * FROM inmate_stays WHERE status='inside' ORDER BY id").fetchall():
        a = int(st["actor_id"])
        dist = _figure(vcfg.get("far_factor"), 1.0) if _far(conn, st["facility_id"]) else 1.0
        kin = _kin(conn, a)
        friends = _friends(conn, a, int(_figure(cfg.get("friends_considered"), 0)))
        for other in sorted(set(kin) | set(friends)):
            if not _outside(conn, other):
                continue
            pull = _pull_of(conn, other, kin, friends)
            rng = _rng(conn, "pull", f"{day}:{a}:{other}")
            if rng.random() < 1.0 - math.exp(-_figure(vcfg["rate"]) * pull * dist):
                if visit(conn, other, a, int(day)).get("ok"):
                    vis += 1
            elif rng.random() < 1.0 - math.exp(-_figure((cfg.get("letter") or {}).get("rate"), 0.0) * pull):
                ch = open_channel(conn, int(st["id"]), "letter", other, int(day))
                if contact(conn, ch, int(day), from_inside=bool(rng.random() < 0.5)).get("ok"):
                    let += 1
        routes += _routes(conn, st, int(day))
    closed = _upkeep(conn, int(day))
    # the standing channels (trusted man, phone, note, guard, lawyer) are used each week by their own chance
    for ch in conn.execute("""SELECT c.* FROM prison_channels c JOIN inmate_stays s ON s.id=c.stay_id
                              WHERE c.status='open' AND c.kind NOT IN ('visit','letter') AND s.status='inside' ORDER BY c.id""").fetchall():
        if _rng(conn, "use", f"{day}:{ch['id']}").random() < _figure(cfg.get("use_rate"), 0.0):
            contact(conn, int(ch["id"]), int(day))
    return {"visits": vis, "letters": let, "routes": routes, "closed": closed}


def channel_grip(conn: sqlite3.Connection, actor_id: int) -> float:
    """How well a man inside still reaches the outside, 0..1: the best open channel's quality, less what is watched, faded by how long
    since it was used. A reading the outside weighs (J1.5), not a threshold. Nothing inside, no channel: 0."""
    g = _cfg(conn).get("grip") or {}
    st = conn.execute("SELECT id FROM inmate_stays WHERE actor_id=? AND status='inside' ORDER BY id DESC LIMIT 1", (int(actor_id),)).fetchone()
    if st is None or not g:
        return 0.0
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    half, ww = _figure(g["recency_days"]), _figure(g["watched_weight"])
    best = 0.0
    for ch in conn.execute("SELECT * FROM prison_channels WHERE stay_id=? AND status='open'", (int(st["id"]),)).fetchall():
        last = conn.execute("SELECT MAX(day) FROM prison_contacts WHERE channel_id=?", (int(ch["id"]),)).fetchone()[0]
        age = max(0, day - int(last if last is not None else ch["since_day"]))
        best = max(best, float(ch["quality"]) * (1.0 - ww * float(ch["watched"])) * math.exp(-math.log(2.0) * age / half))
    return best
