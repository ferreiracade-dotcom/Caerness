"""What the GM is shown of the organisations a man or an organisation belongs to: seats, tension, heat, law cases, what is in the air.

Read-only. Everything is said in words (a band from the package's view_words.json, never a number) and under the firewall: only what
the protagonist would plausibly know, through his own place, his own people, the street and the papers. A fact known only to the
engine (a hidden line, investigative heat, a man's standing in a family not his own) is left out. No world words here: the roles,
labels and bands come from the package's data.
"""
from __future__ import annotations

import json
import sqlite3

_WORDS: dict = {}


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def words(conn) -> dict:
    """The package's view_words.json ({} when it has none), cached on path and mtime."""
    from engine.world_package import package_for
    path = package_for(conn).root / "view_words.json"
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    if key not in _WORDS:
        try:
            _WORDS[key] = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            _WORDS[key] = {}
    return _WORDS[key]


def band(table, value: float) -> str:
    for upper, text in table or []:
        if value < float(upper):
            return str(text or "")
    return str(table[-1][1] or "") if table else ""  # nothing tops the last band: past it is still that band


def _name(conn, actor_id) -> str | None:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone() if actor_id is not None else None
    return str(r[0]) if r else None


def _me(conn) -> int | None:
    from engine.player import get_player
    p = get_player(conn)
    return int(p["player_actor_id"]) if p else None


def _my_orgs(conn, me) -> set[int]:
    if me is None:
        return set()
    return {int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (me,))}


def _like(text: str) -> str:
    return "%" + str(text).replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def _has_heard(conn, me, name: str) -> bool:
    return me is not None and conn.execute("SELECT 1 FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE ? ESCAPE '!' LIMIT 1", (me, _like(name))).fetchone() is not None


def _in_his_chain(conn, me, subject: int, org: int) -> bool:
    """He is the man's superior up the chain, or the head of the organisation, or the man himself."""
    if me is None:
        return False
    if me == subject:
        return True
    from engine import orgs
    cur, seen = orgs.superior_of(conn, subject, org), set()
    while cur is not None and cur not in seen:
        if cur == me:
            return True
        seen.add(cur)
        cur = orgs.superior_of(conn, cur, org)
    return False


def _knows_him(conn, me, subject: int, org: int | None = None) -> bool:
    """He is the man, shares an organisation with him, or has heard of him by name."""
    if me is None:
        return False
    if me == subject:
        return True
    mine = _my_orgs(conn, me)
    if mine and conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND status='active' AND org_actor_id IN (%s) LIMIT 1" % ",".join("?" * len(mine)),
                             (subject, *sorted(mine))).fetchone():
        return True
    return _has_heard(conn, me, _name(conn, subject) or "\0")


def _ago(conn, days: int) -> str:
    return band([[u, t] for u, t in (words(conn).get("when") or [])], float(days))


# ---- a man: temperament, custody, his place in the life ----

def temperament_words(conn, actor_id: int, me: int | None) -> str | None:
    """His temper in words; read off a man he has dealt with or works beside (the engine's drives are never shown to a stranger)."""
    w = words(conn).get("temperament")
    if not w or not _knows_him(conn, me, actor_id):
        return None
    r = conn.execute("SELECT aggression,risk_tolerance FROM actor_drives WHERE actor_id=?", (int(actor_id),)).fetchone()
    if r is None:
        return None
    bits = [band(w.get("aggression"), float(r[0])), band(w.get("risk"), float(r[1]))]
    return ", ".join(b for b in bits if b) or None


def _span(conn, days: int) -> str:
    units = (words(conn).get("custody") or {}).get("term_units") or {"year": 365, "month": 30}
    y, m = float(units.get("year", 365)), float(units.get("month", 30))
    if days >= 1.5 * y:
        return f"about {round(days / y)} years"
    if days >= 0.75 * y:
        return "about a year"
    if days >= 2 * m:
        return f"about {round(days / m)} months"
    return "a few weeks"


def custody_view(conn, actor_id: int, me: int | None) -> dict | None:
    """His custody, case status, charge and sentence, as the protagonist could know them: a public crime is in the papers; otherwise only
    a man who knows him (his own organisation, or one who has heard) has it. None when there is nothing to tell or nothing he could know."""
    cw = words(conn).get("custody")
    if not cw:
        return None
    day = _day(conn)
    try:
        row = conn.execute("SELECT * FROM custody WHERE actor_id=? ORDER BY id DESC LIMIT 1", (int(actor_id),)).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    rep = conn.execute("SELECT public FROM crime_reports WHERE case_id=? LIMIT 1", (row["case_id"],)).fetchone() if row["case_id"] is not None else None
    if not ((rep is not None and rep[0]) or _knows_him(conn, me, int(actor_id))):
        return None
    out: dict = {}
    sen = None
    try:
        sen = conn.execute("SELECT * FROM sentences WHERE actor_id=? ORDER BY id DESC LIMIT 1", (int(actor_id),)).fetchone()
    except sqlite3.OperationalError:
        pass
    disp = None
    if sen is None:
        try:
            disp = conn.execute("SELECT kind,day FROM case_dispositions WHERE actor_id=? ORDER BY id DESC LIMIT 1", (int(actor_id),)).fetchone()
        except sqlite3.OperationalError:
            pass
    charge = str(row["charge"] or "").replace("_", " ")
    if sen is not None and sen["status"] == "serving":
        out["state"] = cw["serving"].format(term=_span(conn, int(sen["term_days"])), facility=sen["facility"] or "prison",
                                            out=_span(conn, max(0, int(sen["earliest_release_day"]) - day)))
    elif sen is not None and sen["status"] == "released":
        out["state"] = cw["home"].format(term=_span(conn, int(sen["term_days"])), facility=sen["facility"] or "prison",
                                         when=_ago(conn, day - int(sen["released_day"] or day)))
    elif row["kind"] == "bailed":
        out["state"] = cw["bailed"]
    elif row["kind"] == "held":
        out["state"] = cw["held"]
    elif disp is not None and disp["kind"] == "dismissed":
        out["state"] = cw["walked"]
    elif disp is not None and disp["kind"] == "verdict_not_guilty":
        out["state"] = cw["acquitted"]
    else:
        return None
    if charge:
        out["charge"] = cw["charge"].format(charge=charge)
    return out


def _lines(conn, actor_id: int, me: int | None) -> list[str]:
    """His lines of business. A line he keeps hidden is never shown to anyone but him; once found it is an ordinary line."""
    from connector.views import _clip
    out = []
    for r in conn.execute("SELECT description,weekly_take,hidden FROM org_lines WHERE holder_actor_id=? AND status='active' ORDER BY id", (int(actor_id),)):
        if r["hidden"] and me != actor_id:
            continue
        take = int(round(float(r["weekly_take"] or 0) / 50.0) * 50)
        out.append(_clip(f"{r['description']}, about ${take} a week" if take else str(r["description"]), 140))
    return out


def _years(conn, day: int, since) -> int | None:
    return None if since is None else max(0, int((day - int(since)) // 365))


def record_view(conn, actor_id: int, me: int | None = None) -> list[dict]:
    """One entry per active seat: where he stands in each organisation he belongs to, as the protagonist could know it."""
    from engine import orgs
    from engine.world_package import org_rules, package_for
    day = _day(conn)
    me = _me(conn) if me is None else me
    out = []
    for s in orgs.seats_of(conn, int(actor_id)):
        if s["status"] != "active":
            continue
        org = int(s["org_actor_id"])
        mine = org in _my_orgs(conn, me) or me == actor_id
        if not (mine or _knows_him(conn, me, int(actor_id), org)):
            continue  # a man he has no way to place in the life is just a man
        rules = orgs.kind_rules(conn, org)
        prof = conn.execute("SELECT sphere FROM org_profiles WHERE org_actor_id=?", (org,)).fetchone()
        labels = rules.get("labels") or {}
        chain = _in_his_chain(conn, me, int(actor_id), org)
        entry = {"org": _name(conn, org), "sphere": prof[0] if prof else None, "role": labels.get(s["role_key"], str(s["role_key"]).replace("_", " "))}
        if mine:
            ul = orgs.unit_leader_of(conn, int(actor_id), org)
            sup = s["superior_actor_id"]
            entry["unit_leader"] = _name(conn, ul) if ul is not None and ul != actor_id else None
            entry["superior"] = _name(conn, sup) if sup is not None else None
            if s["inducted_day"] is not None:
                entry["years_inducted"] = _years(conn, day, s["inducted_day"])
                entry["inducted_label"] = rules.get("inducted_label")
            entry["lines"] = _lines(conn, int(actor_id), me)
            if chain and me != actor_id:
                entry["standing_words"] = band(words(conn).get("standing"), float(s["standing"] or 0)) or None
        c = custody_view(conn, int(actor_id), me)
        entry["custody"] = c
        due = bool(s["history_due"])
        entry["history_due"] = due
        entry["history_reasons"] = [json.loads(r[0] or "{}").get("reason") for r in conn.execute(
            "SELECT metadata_json FROM org_agenda WHERE actor_id=? AND kind='history' ORDER BY id DESC LIMIT 3", (int(actor_id),))] if due else []
        out.append({k: v for k, v in entry.items() if v not in (None, [], "")} | {"history_due": due})
    return out


# ---- an organisation: how it stands with the others, its heat, its head, what it has lost ----

def _pair_phrase(conn, a: int, b: int, day: int) -> str | None:
    tw = words(conn).get("tension") or {}
    acts = tw.get("street_acts") or {}
    if not acts:
        return None
    r = conn.execute(
        f"""SELECT kind FROM org_tension_acts WHERE ((from_org=? AND to_org=?) OR (from_org=? AND to_org=?)) AND day>=? AND delta>0
            AND kind IN ({','.join('?' * len(acts))}) ORDER BY day DESC,id DESC LIMIT 1""",
        (a, b, b, a, day - int(tw.get("back_days") or 400), *sorted(acts))).fetchone()
    return acts[r[0]] if r else None


def org_view(conn, org_id: int, me: int | None = None) -> dict | None:
    """How the organisation stands with those it deals with, said as the street says it; its heat; who leads it; what it has lost lately.
    None for an actor that is not an organisation."""
    from engine import orgs, org_heat, org_tension
    if conn.execute("SELECT 1 FROM org_profiles WHERE org_actor_id=?", (int(org_id),)).fetchone() is None:
        return None
    w = words(conn)
    day = _day(conn)
    me = _me(conn) if me is None else me
    out: dict = {}
    head = orgs.head_of(conn, int(org_id))
    if head is not None:
        out["led_by"] = _name(conn, head)
    rel = []
    if org_tension.enabled(conn):
        tw = w.get("tension") or {}
        others = sorted({b if a == org_id else a for a, b in org_tension.pairs(conn, day) if org_id in (a, b)})
        for o in others:
            h = max(org_tension.heat(conn, int(org_id), o, day), org_tension.heat(conn, o, int(org_id), day))
            b = band(tw.get("bands"), h)
            if not b:
                continue
            ph = _pair_phrase(conn, int(org_id), o, day)
            rel.append(f"{b} {_name(conn, o)}" + (f" ({ph})" if ph else ""))
    if rel:
        out["with_others"] = rel
    if org_heat.enabled(conn):
        full = max(1e-9, org_heat._v(conn, org_heat._data(conn).get("city_full"), 1.0))
        pub = org_heat.read(conn, int(org_id), day)["public_heat"] / full
        hw = band((w.get("heat") or {}).get("public"), pub)
        if hw:
            out["heat"] = hw
    lw = w.get("losses") or {}
    if lw:
        since = day - int(lw.get("recent_days") or 0)
        labels = orgs.kind_rules(conn, int(org_id)).get("labels") or {}
        lost = []
        for r in conn.execute(
                """SELECT a.name,s.role_key,c.day FROM crime_reports c JOIN org_seats s ON s.actor_id=c.victim_actor_id AND s.org_actor_id=?
                   JOIN actors a ON a.id=c.victim_actor_id WHERE c.public=1 AND c.day>=? AND s.status IN ('dead','out','retired') ORDER BY c.day DESC LIMIT 4""",
                (int(org_id), since)):
            lost.append(str(lw["title"]).format(name=r[0], role=str(labels.get(r[1], r[1])).lower(), when=_ago(conn, day - int(r[2]))))
        if lost:
            out["lately_lost"] = lost
    return out


# ---- the scene: what is in the air ----

def in_the_air(conn, me: int | None = None) -> list[str]:
    """What anyone in the city would say is going on: trouble between the families, police busy, a big trial, a public killing. Short."""
    from engine import org_heat, org_tension
    aw = (words(conn).get("air") or {})
    if not aw:
        return []
    day = _day(conn)
    out: list[str] = []
    if org_tension.enabled(conn):
        top = max((max(org_tension.heat(conn, a, b, day), org_tension.heat(conn, b, a, day)) for a, b in org_tension.pairs(conn, day)), default=0.0)
        t = band(aw.get("war"), top)
        if t:
            out.append(t)
    if org_heat.enabled(conn):
        t = band(aw.get("police"), org_heat.city_factor(conn, day))
        if t:
            out.append(t)
    try:
        since = day - int(aw.get("recent_days") or 0)
        pub = float(aw.get("trial_publicity") or 0)
        trial = conn.execute(
            """SELECT 1 FROM crime_reports c JOIN public_attention p ON p.report_id=c.id JOIN law_enforcement_cases l ON l.id=c.case_id
               WHERE c.public=1 AND l.status<>'closed' AND p.loudness>=? LIMIT 1""", (pub,)).fetchone()
        if trial and aw.get("trial"):
            out.append(aw["trial"])
        kinds = sorted(aw.get("killing_kinds") or [])
        kill = conn.execute(
            f"""SELECT c.day FROM crime_reports c WHERE c.public=1 AND c.day>=? AND c.crime_kind IN ({','.join('?' * len(kinds))})
               ORDER BY c.day DESC LIMIT 1""", (since, *kinds)).fetchone() if kinds else None
        if kill and aw.get("killing"):
            out.append(aw["killing"].format(when=_ago(conn, day - int(kill[0]))))
    except sqlite3.OperationalError:
        pass  # a campaign without the law tables has nothing of the kind in the air
    return out
