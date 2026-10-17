"""Compact read-only views over the engine for the Claude connector."""
from __future__ import annotations

import json

from connector import store

_LIMITS = {"present": 5, "news": 5, "competence": 6, "notes": 6, "underworld": 2}


def _clip(text, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _age(conn, actor_id: int, day: int):
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    return int((day - r[0]) // 365) if r and r[0] is not None else None


_TRADE_WORDS = {"labor": "labourer", "transport": "carter", "hospitality": "innkeeper", "criminal": "local"}


def _plain_role(subtype) -> str:
    """A subtype as a plain trade word: no 'resolved_'/'authored_' prefixes, and 'criminal' only for an active underworld role."""
    sub = str(subtype or "")
    for pre in ("resolved_", "authored_"):
        if sub.startswith(pre):
            dom = sub[len(pre):]
            return _TRADE_WORDS.get(dom, dom.replace("_", " "))
    return sub.replace("_", " ")


def _who(conn, a) -> str:
    """One line on who someone is; kin and partners say whose, so nobody is mistaken for the protagonist's."""
    role = _plain_role(a["subtype"] or a["actor_type"])
    partner = conn.execute(
        """SELECT b.name,b.subtype FROM household_unions u JOIN actors b ON b.id=CASE WHEN u.actor_a_id=? THEN u.actor_b_id ELSE u.actor_a_id END
           WHERE ? IN (u.actor_a_id,u.actor_b_id) AND u.status='active' ORDER BY u.started_day DESC LIMIT 1""",
        (a["id"], a["id"])).fetchone()
    if partner and role in ("spouse", "partner", "widow", "widower", ""):
        return _clip(f"{role or 'spouse'} of {partner[0]} ({_plain_role(partner[1]) or 'local'})", 100)
    return _clip(role, 80)


def _sex(conn, actor_id: int, day: int):
    r = conn.execute("SELECT demographic_sex,birth_day FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    if not r or r[0] not in ("female", "male"):
        return None
    young = r[1] is not None and (day - r[1]) < 16 * 365
    return {"female": "girl" if young else "woman", "male": "boy" if young else "man"}[r[0]]


def _member_of(conn, actor_id: int) -> list[str]:
    """Organisations someone belongs to, as "role, organisation", so nobody is placed in the wrong outfit."""
    out = []
    for role, org, crew in conn.execute(
            """SELECT p.role_kind,o.name,c.name FROM underworld_personnel p JOIN underworld_organizations o ON o.id=p.organization_id
               LEFT JOIN underworld_crews c ON c.id=p.crew_id WHERE p.actor_id=? AND p.status='active'""", (actor_id,)):
        out.append(f"{str(role).replace('_', ' ')}, {org}" + (f" ({crew})" if crew else ""))
    for role, kind, inst in conn.execute(
            """SELECT m.role_text,m.membership_kind,i.name FROM institution_memberships m JOIN actors i ON i.id=m.institution_actor_id
               WHERE m.member_actor_id=? AND m.status='active' ORDER BY m.id LIMIT 3""", (actor_id,)):
        out.append(_clip(f"{role or str(kind).replace('_', ' ')}, {inst}", 80))
    return out[:4]


def _town_sample(conn, people: list, me: int, limit: int) -> list:
    """A settlement-wide scene is the town. Underworld figures are few among a town's people, so beyond a couple
    (unless they know the protagonist or are his own people) they stay out of the list."""
    crim = {r[0] for r in conn.execute("SELECT actor_id FROM underworld_personnel WHERE status='active'")}
    mine = {r[0] for r in conn.execute(
        """SELECT p.actor_id FROM underworld_personnel p WHERE p.status='active' AND p.organization_id IN
           (SELECT organization_id FROM underworld_personnel WHERE actor_id=? AND status='active')""", (me,))}
    known = {r[0] for r in conn.execute(
        "SELECT actor_b_id FROM relationships WHERE actor_a_id=? UNION SELECT actor_a_id FROM relationships WHERE actor_b_id=?", (me, me))}
    house = {r[0] for r in conn.execute(
        """SELECT m.actor_id FROM household_members m WHERE m.status='active' AND m.household_id IN
           (SELECT household_id FROM household_members WHERE actor_id=? AND status='active')""", (me,))}
    close = mine | known | house
    people = sorted(people, key=lambda a: a["id"] not in close)  # his own people, kin and acquaintances come first (stable otherwise)
    if not crim.intersection(a["id"] for a in people):
        return people[:limit]
    out, strangers = [], 0
    for a in people:
        if a["id"] in crim and a["id"] not in mine and a["id"] not in known:
            strangers += 1
            if strangers > _LIMITS["underworld"]:
                continue
        out.append(a)
        if len(out) >= limit:
            break
    return out


def _network_places(conn, actor_id: int) -> list[str] | None:
    """Where a network (no seat, no territory) is present, strongest first."""
    rows = [f"{n} ({st})" for n, st in conn.execute(
        """SELECT l.name,p.strength FROM underworld_network_presence p JOIN locations l ON l.id=p.location_id WHERE p.institution_actor_id=?
           ORDER BY CASE p.strength WHEN 'strong' THEN 0 WHEN 'present' THEN 1 ELSE 2 END,l.name LIMIT 8""", (actor_id,))]
    return rows or None


def _words(conn, observer: int | None, subject: int, place, shown: str = "") -> dict:
    """Standing in words for a scene entry: what repeats the entry's own text, or is only the default, is left out."""
    from engine.standing import standing

    w = standing(conn, observer, subject, place)
    if w.get("station") and w["station"].lower() in shown.lower():
        w.pop("station")
    if w.get("knows") == "does not know you":
        w.pop("knows")  # absent means a stranger to the protagonist
    if w.get("knows") == "knows you" and (w.get("kin") or w.get("house")):
        w.pop("knows")  # kin and household know him
    if w.get("age") == "adult":
        w.pop("age")  # absent means an ordinary adult
    return w


def _pending(item: dict) -> dict:
    terms = item.get("terms") or {}
    about = terms.get("purpose") or terms.get("subject") or item.get("recipient_name")
    return {"interaction_id": item["id"], "kind": item["interaction_type"], "from": item["proposer_name"],
            "about": _clip(about, 100)}


def _competence(prof: dict) -> list[str]:
    rows = prof.get("relevant_domains") or []
    lines = [f"{r['domain']}: {r['label']}" for r in rows]
    if not lines:
        best = sorted(prof.get("all_domains") or [], key=lambda d: -float(d.get("score") or 0))
        lines = [f"{d['domain_name']}: {d['band']['label']}. {_clip(d['band']['description'], 90)}" for d in best]
    return lines[: _LIMITS["competence"]]


def _condition(h: dict) -> str:
    bits = [str(h.get("aging_phase") or "unknown phase"), f"capacity {round(float(h.get('functional_capacity') or 0))}%"]
    for key in ("conditions", "disabilities"):
        for c in (h.get(key) or [])[:2]:
            bits.append(_clip(c.get("name") or c.get("label") or c.get("kind") or c if isinstance(c, dict) else c, 40))
    return _clip(", ".join(bits), 160)


def _num(v):
    return None if v is None else round(float(v), 1)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _arrears_word(conn, kind: str, hid: int):
    from engine.payroll import arrears_words, get_arrears
    return arrears_words(get_arrears(conn, kind, hid)["months"]) or None


def _business(conn, e, me: int | None = None) -> dict:
    """One business as the engine records it: kind, money, staff, rackets run through it."""
    kind = conn.execute(
        """SELECT a.name FROM enterprise_business_profiles p JOIN business_archetypes a ON a.id=p.archetype_id
           WHERE p.enterprise_id=?""", (e["id"],)).fetchone()
    staff = [{"name": r[0], "role": r[1]} for r in conn.execute(
        """SELECT a.name,s.role FROM enterprise_staff s JOIN actors a ON a.id=s.actor_id
           WHERE s.enterprise_id=? AND s.status='active' AND s.actor_id<>? ORDER BY s.authority DESC LIMIT 4""",
        (e["id"], me or 0))]
    rackets = [f"{r[0].replace('_', ' ')}: {_num(r[1])}/30 days" for r in conn.execute(
        "SELECT racket_kind,gross_income_per_30 FROM underworld_racket_sites WHERE enterprise_id=? AND status='active'", (e["id"],))]
    rank, total = conn.execute(
        """SELECT (SELECT COUNT(*) FROM civilian_enterprises WHERE status='active' AND capital>?)+1,
                  (SELECT COUNT(*) FROM civilian_enterprises WHERE status='active')""", (e["capital"] or 0,)).fetchone()
    standing = f"capital {_ordinal(rank)} of {total} businesses in the world"
    return _drop_none({"id": e["id"], "name": e["name"], "kind": kind[0] if kind else e["enterprise_kind"], "standing": standing,
                       "capital": _num(e["capital"]), "cash": _num(e["cash"]), "debt": _num(e["debt"]) or None,
                       "staff": staff or None, "rackets": rackets or None,
                       "wages": _arrears_word(conn, "business", int(e["id"]))})


def _unpaid_people(conn, hid: int) -> list[str]:
    from engine.payroll import get_arrears
    months = get_arrears(conn, "household", hid)["months"]
    if months < 1:
        return []
    how = "has not been paid this month" if months == 1 else f"has not been paid in {({2: 'two', 3: 'three', 4: 'four', 5: 'five'}).get(months, 'many')} months"
    return [f"{r[0]} {how}" for r in conn.execute(
        """SELECT a.name FROM household_service_terms t JOIN actors a ON a.id=t.actor_id WHERE t.household_id=? AND t.status='active' ORDER BY t.id LIMIT 4""", (hid,))]


def _outfit_mood(conn, oid: int) -> str:
    from engine.loyalty import outfit_mood
    return outfit_mood(conn, oid)


def _holdings(conn, me: int) -> dict:
    """What the protagonist owns and runs: businesses, organisations led, household, personal means."""
    biz_rows = conn.execute(
        """SELECT * FROM civilian_enterprises WHERE status='active' AND (owner_actor_id=? OR id IN
             (SELECT enterprise_id FROM enterprise_partners WHERE actor_id=? AND status='active')) ORDER BY capital DESC""",
        (me, me)).fetchall()
    businesses = [_business(conn, e, me) for e in biz_rows[:6]]
    biz_more = len(biz_rows) - len(businesses)
    orgs = []
    for o in conn.execute("SELECT * FROM underworld_organizations WHERE current_leader_actor_id=? AND status='active'", (me,)):
        people = [f"{r[0]} ({r[1]})" for r in conn.execute(
            """SELECT a.name,p.role_kind FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id
               WHERE p.organization_id=? AND p.actor_id<>? AND p.status='active' ORDER BY p.authority DESC LIMIT 5""", (o["id"], me))]
        incomes = [r[0] or 0 for r in conn.execute(
            """SELECT (SELECT SUM(gross_income_per_30) FROM underworld_racket_sites s WHERE s.organization_id=o.id AND s.status='active')
               FROM underworld_organizations o WHERE o.status='active'""")]
        mine = conn.execute("SELECT COALESCE(SUM(gross_income_per_30),0) FROM underworld_racket_sites WHERE organization_id=? AND status='active'",
                            (o["id"],)).fetchone()[0]
        sizes = [r[0] or 0 for r in conn.execute("SELECT member_count_estimate FROM underworld_organizations WHERE status='active'")]
        standing = (f"racket income {_ordinal(sum(1 for x in incomes if x > mine) + 1)} of {len(incomes)} outfits; "
                    f"size {_ordinal(sum(1 for x in sizes if x > (o['member_count_estimate'] or 0)) + 1)} of {len(sizes)}")
        orgs.append(_drop_none({"name": o["name"], "type": o["organization_type"], "standing": standing,
                                "members": int(o["member_count_estimate"] or 0),
                                "treasury": _num(o["treasury"]), "violence_capacity": _num(o["violence_capacity"]),
                                "mood": _outfit_mood(conn, int(o["id"])) or None,
                                "key_people": people or None}))
    hh = conn.execute(
        """SELECT h.* FROM household_members m JOIN households h ON h.id=m.household_id
           WHERE m.actor_id=? AND m.status='active' ORDER BY m.authority DESC LIMIT 1""", (me,)).fetchone()
    household = None
    if hh:
        members = [f"{r[0]} ({r[1]})" for r in conn.execute(
            """SELECT a.name,m.role FROM household_members m JOIN actors a ON a.id=m.actor_id
               WHERE m.household_id=? AND m.actor_id<>? AND m.status='active' LIMIT 6""", (hh["id"], me))]
        from engine.payroll import arrears_words, get_arrears
        household = _drop_none({"name": hh["name"], "wealth": _num(hh["wealth"]), "liquidity": _num(hh["liquidity"]),
                                "wages": arrears_words(get_arrears(conn, "household", int(hh["id"]))["months"]) or None,
                                "unpaid": _unpaid_people(conn, int(hh["id"])) or None,
                                "members": members or None})
    w = conn.execute("SELECT liquid_wealth,property_value,lifestyle_level FROM underworld_leader_wealth WHERE actor_id=?", (me,)).fetchone()
    means = _drop_none({"liquid": _num(w[0]), "property": _num(w[1]), "lifestyle": _num(w[2])}) if w else None
    scale = None
    if businesses:
        lo, mid, hi = conn.execute(
            "SELECT MIN(capital),AVG(capital),MAX(capital) FROM civilian_enterprises WHERE status='active'").fetchone()
        scale = f"engine money units; businesses in this world hold {lo:.0f}-{hi:.0f} capital, average {mid:.0f}"
    from engine.ledger import balance, scale_word
    boss = conn.execute(
        "SELECT organization_id FROM underworld_personnel WHERE actor_id=? AND status='active' AND role_kind IN ('boss','underboss') LIMIT 1",
        (me,)).fetchone()
    spend = {"purse": scale_word(balance(conn, ("person", me)))}
    if boss:
        spend["outfit_treasury"] = scale_word(balance(conn, ("outfit", int(boss[0]))))
    if businesses:
        spend["business_cash"] = {b["name"]: scale_word(float(b.get("cash") or 0)) for b in businesses}
    hh_more = int(conn.execute("SELECT COUNT(*) FROM households WHERE head_actor_id=? AND status='active'", (me,)).fetchone()[0]) - (1 if household else 0)
    return _drop_none({"money_scale": scale, "means": spend, "businesses": businesses or None,
                       "businesses_more": biz_more or None, "organisations": orgs or None,
                       "household": household, "households_more": hh_more if hh_more > 0 else None, "personal_means": means})


def compact_scene(conn) -> dict:
    """Commits (it drops its own audit packet), so never call it inside a run_once callback."""
    from engine.civil_calendar import format_sv_date, season_for_day
    from engine.player import build_scene_packet

    p = build_scene_packet(conn)
    # The packet row is an audit copy the connector does not need; keep the save small.
    conn.execute("DELETE FROM scene_packets WHERE id=?", (p["scene_packet_id"],))
    conn.commit()
    day = int(p["world"]["day"])
    me, loc = p["player"], p["location"]
    people = [a for a in p["present_actors"] if a.get("actor_type") == "character"]
    here = loc["id"]
    present = []
    sampled = _town_sample(conn, people, int(me["actor_id"]), _LIMITS["present"])
    for a in sampled:
        who, member = _who(conn, a), "; ".join(_member_of(conn, a["id"])) or None
        present.append(_drop_none({"id": a["id"], "name": a["name"], "sex": _sex(conn, a["id"], day), "who": who,
                                   "member_of": member, **_words(conn, int(me["actor_id"]), a["id"], here, f"{who} {member or ''}")}))
    from engine.manners_canon import manners_for
    you_here = _words(conn, None, int(me["actor_id"]), here)
    you_here.pop("age", None)
    if you_here.get("station") and you_here["station"].lower() in str(me.get("subtype") or "").lower():
        you_here.pop("station")  # already in protagonist.role
    institutions = [{"id": a["id"], "name": a["name"], "what": _who(conn, a)}
                    for a in p["present_actors"] if a.get("actor_type") != "character"]
    seen = {i["id"] for i in institutions}
    local_n = len(institutions)
    for nid, nname, strength in conn.execute(
            """SELECT a.id,a.name,n.strength FROM underworld_network_presence n JOIN actors a ON a.id=n.institution_actor_id
               WHERE n.location_id=? AND a.status NOT IN ('dead','destroyed','dissolved','defunct','historical') ORDER BY CASE n.strength WHEN 'strong' THEN 0 WHEN 'present' THEN 1 ELSE 2 END,a.name""", (here,)):
        if nid not in seen:
            institutions.append({"id": nid, "name": nname, "what": f"network, {strength} here"})
    local, nets = institutions[:local_n], institutions[local_n:]
    local = local[:8 - min(3, len(nets))]  # networks are not crowded out by a town's many seats
    inst_total = len(institutions)
    institutions = local + nets[:8 - len(local)]
    events = [f"day {e['day']}: {_clip(e['title'], 100)}" for e in p["known_events"][-_LIMITS["news"]:]]
    rumours = ["rumour: " + _clip(r["text"], 110) for r in p["known_rumours"][-_LIMITS["news"]:]]
    more_news = max(0, len(p["known_events"]) - len(events)) + max(0, len(p["known_rumours"]) - len(rumours))
    notes, notes_more = [], 0
    for kind, sid, name in [("location", loc["id"], loc["name"])] + [("actor", a["id"], a["name"]) for a in present]:
        if sid is None:
            continue
        notes += [{"about": name, "text": _clip(t, 160)} for t in store.notes_for(conn, kind, int(sid), 2)]
        notes_more += max(0, store.notes_count(conn, kind, int(sid)) - 2)
    notes_more += max(0, len(notes) - _LIMITS["notes"])
    desc = "; ".join(x for x in (loc.get("kind"), loc.get("notes"), loc.get("political_owner")) if x)
    from engine import commitments
    pending_work = commitments.active(conn, int(me["actor_id"]), 5)
    return _drop_none({
        "commitments": [{"what": _clip(c["what"], 100), "kind": c["kind"], "due_in_days": max(0, int(c["due_day"]) - day) if c["due_day"] is not None else None}
                        for c in pending_work] or None,
        "day": day,
        "date": format_sv_date(day),
        "season": season_for_day(day),
        "location": {"id": loc["id"], "name": loc["name"], "description": _clip(desc, 140)},
        "protagonist": _drop_none({"id": me["actor_id"], "name": me["name"], "age": _age(conn, me["actor_id"], day),
                                   "role": _clip(me.get("subtype") or me.get("actor_type"), 100)}),
        "present": present,
        "manners": manners_for(conn, here),
        "you_here": you_here or None,
        "institutions_here": institutions,
        "pending": [_pending(i) for i in p["pending_player_interactions"][:5]],
        "news": _drop_none({"events": events, "rumours": rumours, "more": more_news or None}),
        "present_more": (len(people) - len(sampled)) or None,
        "institutions_more": (inst_total - len(institutions)) or None,
        "competence": _competence(p["professional_context"]),
        "condition": _condition(p["health_context"]),
        "holdings": _holdings(conn, int(me["actor_id"])),
        "notes": notes[: _LIMITS["notes"]],
        "notes_more": notes_more or None,
        "recent_operations": store.recent_operations(conn),
    })


def _like(text: str) -> str:
    return "%" + text.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def _find(conn, table: str, q: str):
    if q.isdigit():
        return conn.execute(f"SELECT * FROM {table} WHERE id=?", (int(q),)).fetchall()
    rows = conn.execute(f"SELECT * FROM {table} WHERE name=? COLLATE NOCASE", (q,)).fetchall()
    # Engine stand-ins ("[STRUCTURAL] ... grain hinterland") are aggregates, not people or places to meet.
    return rows or conn.execute(f"SELECT * FROM {table} WHERE name LIKE ? ESCAPE '!' AND name NOT LIKE '[%' ORDER BY id LIMIT 5",
                                (_like(q),)).fetchall()


_PAGE = 8


def _role_hits(conn, q: str) -> list[tuple]:
    """People known by a role word ("magistrate", "steward", "boss"): (actor row, role text)."""
    like = _like(q)
    seen, out = set(), []
    queries = (
        "SELECT a.*,a.subtype role FROM actors a WHERE a.actor_type='character' AND a.status='active' AND a.subtype LIKE ? ESCAPE '!' AND a.subtype NOT LIKE 'resolved_%' ORDER BY a.id LIMIT 6",
        "SELECT a.*,m.role_text role FROM institution_memberships m JOIN actors a ON a.id=m.member_actor_id WHERE m.status='active' AND m.role_text LIKE ? ESCAPE '!' ORDER BY a.id LIMIT 6",
        "SELECT a.*,s.role role FROM enterprise_staff s JOIN actors a ON a.id=s.actor_id WHERE s.status='active' AND s.role LIKE ? ESCAPE '!' ORDER BY a.id LIMIT 6",
        "SELECT a.*,REPLACE(p.role_kind,'_',' ') role FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id WHERE p.status='active' AND REPLACE(p.role_kind,'_',' ') LIKE ? ESCAPE '!' ORDER BY a.id LIMIT 6",
    )
    for sql in queries:
        for r in conn.execute(sql, (like,)):
            if r["id"] not in seen:
                seen.add(r["id"])
                out.append((r, str(r["role"])))
    return out[:8]


def _knows_of(conn, me: int | None, kind: str, row) -> bool:
    """Lookup finds what he could know exists: his own outfit, house or crew, what he has heard named, what stands in the place he is."""
    if me is None:
        return False
    here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()
    here = here[0] if here else None
    if kind == "outfit":
        if conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'", (me, row["id"])).fetchone():
            return True
        if conn.execute("""SELECT 1 FROM underworld_zone_claims c JOIN underworld_zones z ON z.id=c.zone_id
                           WHERE c.organization_id=? AND c.claim_kind='controller' AND c.status='active' AND z.city_location_id=? LIMIT 1""", (row["id"], here)).fetchone():
            return True
    elif kind == "crew":
        if conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'", (me, row["organization_id"])).fetchone():
            return True
    elif kind == "household":
        if conn.execute("SELECT 1 FROM household_members WHERE household_id=? AND actor_id=? AND status='active'", (row["id"], me)).fetchone():
            return True
        if here is not None and "location_id" in row.keys() and row["location_id"] == here:
            return True
    return conn.execute("SELECT 1 FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE ? ESCAPE '!' LIMIT 1", (me, _like(row["name"]))).fetchone() is not None


def _outfit_view(conn, o, me: int | None) -> dict:
    mine = me is not None and conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'", (me, o["id"])).fetchone()
    out = {"type": o["organization_type"], "status": o["status"]}
    if mine:
        people = [f"{r[0]} ({str(r[1]).replace('_', ' ')})" for r in conn.execute(
            "SELECT a.name,p.role_kind FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id WHERE p.organization_id=? AND p.status='active' ORDER BY p.authority DESC LIMIT ?", (o["id"], _PAGE))]
        crews = [{"id": c["id"], "name": c["name"]} for c in conn.execute("SELECT id,name FROM underworld_crews WHERE organization_id=? AND status='active' ORDER BY id LIMIT ?", (o["id"], _PAGE))]
        out.update({"members": int(o["member_count_estimate"] or 0), "key_people": people or None, "crews": crews or None,
                    "mood": _outfit_mood(conn, int(o["id"])) or None})
    else:
        out["seen"] = "what he knows of it is below"  # a rival's inner workings are not his to read off
    return _drop_none(out)


def _household_view(conn, h, me: int | None) -> dict:
    head = conn.execute("SELECT name FROM actors WHERE id=?", (h["head_actor_id"],)).fetchone()
    members = [f"{r[0]} ({r[1]})" for r in conn.execute(
        "SELECT a.name,m.role FROM household_members m JOIN actors a ON a.id=m.actor_id WHERE m.household_id=? AND m.status='active' ORDER BY m.authority DESC LIMIT ?", (h["id"], _PAGE))]
    where = conn.execute("SELECT name FROM locations WHERE id=?", (h["location_id"],)).fetchone() if "location_id" in h.keys() else None
    return _drop_none({"head": head[0] if head else None, "members": members or None, "place": where[0] if where else None, "status": h["status"]})


def _crew_view(conn, c, me: int | None) -> dict:
    org = conn.execute("SELECT name FROM underworld_organizations WHERE id=?", (c["organization_id"],)).fetchone()
    leader = conn.execute("SELECT name FROM actors WHERE id=?", (c["leader_actor_id"],)).fetchone() if c["leader_actor_id"] is not None else None
    mine = me is not None and conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'", (me, c["organization_id"])).fetchone()
    return _drop_none({"outfit": org[0] if org else None, "leader": leader[0] if leader else None, "status": c["status"],
                       "men": int(c["size_estimate"]) if mine else None, "works": c["purpose_kind"] if mine else None})


def lookup(conn, query: str, offset: int = 0) -> dict:
    """Find what the protagonist knows of a person, place, business, outfit, household, crew, institution or role.
    `offset` pages the older known facts and notes (the newest come first); the reply says how many more there are."""
    from engine.player import get_player

    q = str(query or "").strip()
    offset = max(0, int(offset or 0))
    if not q:
        return {"found": False, "candidates": []}
    pl0 = get_player(conn)
    me0 = int(pl0["player_actor_id"]) if pl0 else None
    kinds = [("actor", _find(conn, "actors", q)), ("location", _find(conn, "locations", q)), ("business", _find(conn, "civilian_enterprises", q)),
             ("outfit", [o for o in _find(conn, "underworld_organizations", q) if _knows_of(conn, me0, "outfit", o)]),
             ("household", [h for h in _find(conn, "households", q) if _knows_of(conn, me0, "household", h)]),
             ("crew", [c for c in _find(conn, "underworld_crews", q) if _knows_of(conn, me0, "crew", c)])]
    hits = [(k, r) for k, rows in kinds for r in rows]
    roles = []
    if len(hits) != 1:
        exact = [h for h in hits if str(h[1]["name"]).lower() == q.lower()]
        if len(exact) == 1:
            hits = exact
    if not hits:
        roles = _role_hits(conn, q)
        if len(roles) == 1:
            hits = [("actor", roles[0][0])]
    if len(hits) != 1:
        if roles:
            return {"found": False, "candidates": [f"{r['name']} ({role})" for r, role in roles[:5]], "by_role": True,
                    **({"more_candidates": len(roles) - 5} if len(roles) > 5 else {})}
        return {"found": False, "candidates": [h[1]["name"] for h in hits[:5]], **({"more_candidates": len(hits) - 5} if len(hits) > 5 else {})}
    kind, r = hits[0]
    out = {"found": True, "kind": kind, "id": int(r["id"]), "name": r["name"]}
    pl = get_player(conn)
    me = int(pl["player_actor_id"]) if pl else None
    if kind == "actor":
        where = conn.execute("SELECT name FROM locations WHERE id=?", (r["current_location_id"],)).fetchone()
        day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
        out["basics"] = _drop_none({"type": r["actor_type"], "sex": _sex(conn, int(r["id"]), day), "role": _who(conn, r),
                                    "member_of": _member_of(conn, int(r["id"])) or None, "status": r["status"],
                                    "last_known_place": where[0] if where else None,
                                    "present_in": _network_places(conn, int(r["id"]))})
    elif kind == "business":
        owner = conn.execute("SELECT name FROM actors WHERE id=COALESCE(?,?)", (r["owner_actor_id"], r["institution_actor_id"])).fetchone()
        where = conn.execute("SELECT name FROM locations WHERE id=?", (r["location_id"],)).fetchone()
        b = _business(conn, r)
        b.pop("id"); b.pop("name")
        out["basics"] = _drop_none({**b, "owner": owner[0] if owner else None, "place": where[0] if where else None})
    elif kind == "outfit":
        out["basics"] = _outfit_view(conn, r, me)
    elif kind == "household":
        out["basics"] = _household_view(conn, r, me)
    elif kind == "crew":
        out["basics"] = _crew_view(conn, r, me)
    else:
        out["basics"] = _drop_none({"kind": r["kind"], "owner": r["political_owner"], "notes": _clip(r["notes"], 160)})
    table = {"actor": "actors", "business": "civilian_enterprises", "outfit": "underworld_organizations", "household": "households", "crew": "underworld_crews"}.get(kind)
    if table and conn.execute("SELECT 1 FROM authored_entities WHERE entity_table=? AND entity_id=? LIMIT 1", (table, out["id"])).fetchone():
        out["authored"] = True
    if pl:
        like = _like(r["name"])
        total = conn.execute("SELECT COUNT(*) FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE ? ESCAPE '!'", (me, like)).fetchone()[0]
        known = conn.execute(
            """SELECT belief_text,confidence,learned_day FROM knowledge
               WHERE knower_actor_id=? AND belief_text LIKE ? ESCAPE '!' ORDER BY learned_day DESC,id DESC LIMIT ? OFFSET ?""",
            (me, like, _PAGE, offset)).fetchall()
        if known:
            out["known"] = [{"text": _clip(k[0], 160), "confidence": round(float(k[1]), 2), "learned_day": k[2]} for k in known]
        if total > offset + len(known):
            out["known_more"] = total - offset - len(known)  # ask again with a larger offset for the older ones
        if kind == "actor" and me != out["id"]:
            # Bands in words replace the rounded meters (the rulebook forbade showing those anyway).
            from engine.standing import standing
            here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()
            words = standing(conn, me, out["id"], here[0] if here else None)
            if words:
                out["standing"] = words
        if kind == "actor" and me == out["id"]:
            from engine import commitments
            cm = commitments.active(conn, me, _PAGE, offset)
            if cm:
                out["commitments"] = [{"what": _clip(c["what"], 140), "kind": c["kind"], "due_day": c["due_day"]} for c in cm]
    notes = store.notes_for(conn, kind, out["id"], _PAGE, offset)
    if notes:
        out["notes"] = [_clip(n, 160) for n in notes]
    ncount = store.notes_count(conn, kind, out["id"])
    if ncount > offset + len(notes):
        out["notes_more"] = ncount - offset - len(notes)
    return out
