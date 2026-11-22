"""Claims and audiences (information phase 1b, spec 7.1 and 7.5).

A claim is a free-text statement about a subject held by a person or by an audience, with a source (saw, told, read, inferred), a
confidence, a day, and a link to the truth when there is one. Claims about the same subject stand alone. There is no list of traits.

An audience is anything the package's `presence.json` `audiences` defines (an outfit, a man's people, the place he lives in): the
engine knows only the three membership rules (org, circle, home_place), never a name. A named person holds individual claims and what
he holds reaches the audiences he belongs to; an audience holds an impression, the aggregate of what has reached it. The two can
disagree and each draws on the other.

The drivers of 7.1 are weighed in `weigh` and the telling rules, none of them a cap: a costly act outweighs talk; second-hand is
discounted per hop; bad news sticks and trust is slow; closeness resists bad news and a rival spreads it; weight decays with time unless
reinforced (and slowly for a costly bad claim: stigma); a claim spills onto the people connected to the subject; and standing and access
follow the name. Nothing here knows the protagonist: observer and subject are any two people (`tests/i1b_test.py` greps for that).
"""
from __future__ import annotations

import json
import math
import sqlite3

from . import bearing as B

SOURCES = ("saw", "told", "read", "inferred")
WEEK = 7


def enabled(conn: sqlite3.Connection) -> bool:
    return B.enabled(conn) and bool(B.data(conn).get("audiences"))


def _d(conn) -> dict:
    return B.data(conn).get("claims") or {}


def _clip(text, n: int = 200) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _home(conn, aid: int):
    r = conn.execute("SELECT COALESCE(home_location_id,current_location_id) FROM actors WHERE id=?", (int(aid),)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _here(conn, aid: int):
    r = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(aid),)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def kin(conn, subject: int) -> dict[int, float]:
    """The people connected to him by blood, marriage or household (1.0 kin, 0.8 household)."""
    out: dict[int, float] = {}
    for a, b in conn.execute("SELECT actor_a_id,actor_b_id FROM kinship_links WHERE (actor_a_id=? OR actor_b_id=?) AND ended_day IS NULL", (subject, subject)):
        i = int(b) if int(a) == subject else int(a)
        out[i] = 1.0
    for (i,) in conn.execute("SELECT actor_id FROM household_members WHERE status='active' AND household_id IN "
                             "(SELECT household_id FROM household_members WHERE actor_id=? AND status='active')", (subject,)):
        if int(i) != subject:
            out.setdefault(int(i), 0.8)
    return out


# ---- audiences ----------------------------------------------------------------------------------------------

def _aud(conn, key: str, ref: int, label: str) -> dict:
    r = conn.execute("SELECT id,label FROM audiences WHERE key=? AND ref_id=?", (key, int(ref))).fetchone()
    if r is None:
        aid = int(conn.execute("INSERT INTO audiences(key,ref_id,label) VALUES (?,?,?)", (key, int(ref), label)).lastrowid)
        return {"id": aid, "key": key, "ref": int(ref), "label": label}
    return {"id": int(r["id"]), "key": key, "ref": int(ref), "label": str(r["label"])}


def audiences_of(conn, subject: int) -> list[dict]:
    """The audiences that hold an impression of this subject, by the package's rules."""
    out = []
    for key, df in (B.data(conn).get("audiences") or {}).items():
        rule = df.get("rule")
        if rule == "org":
            for s in B.seats(conn, subject):
                out.append(_aud(conn, key, int(s["org_actor_id"]), f"{df.get('label', key)}: {B.name_of(conn, s['org_actor_id'])}"))
        elif rule == "circle":
            out.append(_aud(conn, key, subject, df.get("label", key)))
        elif rule == "home_place":
            loc = _home(conn, subject)
            if loc is not None:
                nm = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()
                out.append(_aud(conn, key, loc, f"{df.get('label', key)}: {nm[0] if nm else loc}"))
    return out


def _rule(conn, aud: dict) -> str | None:
    return ((B.data(conn).get("audiences") or {}).get(aud["key"]) or {}).get("rule")


def is_member(conn, actor: int, aud: dict) -> bool:
    rule = _rule(conn, aud)
    if rule == "org":
        return conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (int(actor), aud["ref"])).fetchone() is not None
    if rule == "circle":
        return int(actor) in kin(conn, aud["ref"])
    if rule == "home_place":
        return _home(conn, actor) == aud["ref"]
    return False


def members(conn, aud: dict) -> list[int]:
    """The named members (a crowd with no enumerable members is held as an impression only)."""
    rule = _rule(conn, aud)
    if rule == "org":
        return [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active'", (aud["ref"],))]
    if rule == "circle":
        return list(kin(conn, aud["ref"]))
    return []


# ---- weighing -----------------------------------------------------------------------------------------------

def _eff(conn, c, day: int) -> float:
    """What a claim still counts for: its confidence, decayed with age unless reinforced (a costly bad claim decays slowly)."""
    age = max(0, int(day) - int(c["day"]))
    hl = B.fig(conn, "claim_half_life_days") * (B.fig(conn, "stigma_mult") if int(c["costly"]) and float(c["valence"]) < 0 else 1.0)
    return float(c["confidence"]) * 0.5 ** (age / hl)


def weigh(conn, c, day: int) -> float:
    """A claim's weight: decayed confidence, bad news heavier, a costly act heavier than talk."""
    return (_eff(conn, c, day) * (B.fig(conn, "bad_weight") if float(c["valence"]) < 0 else B.fig(conn, "good_weight"))
            * (B.fig(conn, "costly_mult") if int(c["costly"]) else 1.0))


def _aggregate(conn, rows, day: int) -> tuple[float, float, float]:
    """(regard, force, mass) from claims: each -1..1, shrunk toward neutral by the prior so a few claims move little."""
    num = fnum = den = 0.0
    for c in rows:
        w = weigh(conn, c, day)
        num += float(c["valence"]) * w
        fnum += float(c["force"]) * w
        den += w
    prior = B.fig(conn, "prior_mass")
    return num / (den + prior), fnum / (den + prior), den


def impression(conn, aud: dict, subject: int, day: int | None = None) -> dict:
    day = B._day(conn) if day is None else int(day)
    rows = conn.execute("SELECT * FROM claims WHERE holder_kind='audience' AND holder_id=? AND subject_actor_id=?", (aud["id"], int(subject))).fetchall()
    regard, force, mass = _aggregate(conn, rows, day)
    return {"audience": aud["key"], "label": aud["label"], "regard": regard, "force": force, "mass": mass}


def own_regard(conn, actor: int, subject: int, day: int | None = None) -> tuple[float, float, float]:
    day = B._day(conn) if day is None else int(day)
    rows = conn.execute("SELECT * FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=?", (int(actor), int(subject))).fetchall()
    return _aggregate(conn, rows, day)


def regard_of(conn, actor: int, subject: int, day: int | None = None) -> tuple[float, float, float]:
    """(regard, force, mass): what he makes of the subject, his own claims drawing on the impression of the audiences he belongs to."""
    day = B._day(conn) if day is None else int(day)
    r, f, m = own_regard(conn, actor, subject, day)
    imps = [impression(conn, a, subject, day) for a in audiences_of(conn, subject) if is_member(conn, actor, a)]
    imps = [i for i in imps if i["mass"] > 0]
    if imps:
        pull = B.fig(conn, "audience_pull")
        ar = sum(i["regard"] for i in imps) / len(imps)
        af = sum(i["force"] for i in imps) / len(imps)
        return (1 - pull) * r + pull * ar, (1 - pull) * f + pull * af, m + sum(i["mass"] for i in imps)
    return r, f, m


# ---- recording ----------------------------------------------------------------------------------------------

def _effect(conn, event_type: str):
    for e in _d(conn).get("event_effects") or []:
        if any(w in str(event_type).lower() for w in e.get("match") or []):
            return e
    return None


def _per(table: dict | None, keys) -> float:
    table = table or {}
    for k in keys:
        if k in table:
            return float(table[k])
    return float(table.get("default", 0.0))


def _veto(conn, subject, holder_kind, holder_id, source, confidence, truth_event_id) -> None:
    if source not in SOURCES:
        raise ValueError(f"a claim's source is one of {SOURCES}")
    if not 0.0 <= float(confidence) <= 1.0:
        raise ValueError("confidence runs from 0 to 1")
    if conn.execute("SELECT 1 FROM actors WHERE id=?", (int(subject),)).fetchone() is None:
        raise ValueError("there is no such subject")
    if holder_kind == "actor":
        if conn.execute("SELECT 1 FROM actors WHERE id=?", (int(holder_id),)).fetchone() is None:
            raise ValueError("there is no such holder")
        if not B._alive(conn, int(holder_id)):
            raise ValueError("the dead hold no claims")
    elif conn.execute("SELECT 1 FROM audiences WHERE id=?", (int(holder_id),)).fetchone() is None:
        raise ValueError("there is no such audience")
    if truth_event_id is not None:
        ev = conn.execute("SELECT source_actor_id FROM events WHERE id=?", (int(truth_event_id),)).fetchone()
        if ev is None:
            raise ValueError("that happening is not in the record")
        about = {int(r[0]) for r in conn.execute("SELECT actor_id FROM event_targets WHERE event_id=?", (int(truth_event_id),))}
        if ev[0] is not None:
            about.add(int(ev[0]))
        if about and int(subject) not in about:
            raise ValueError("that happening is not about this subject")
        if source == "saw" and holder_kind == "actor":
            saw = {int(r[0]) for r in conn.execute("SELECT actor_id FROM event_witnesses WHERE event_id=?", (int(truth_event_id),))} | about
            if int(holder_id) not in saw:
                raise ValueError("he was not there: a claim that he saw it contradicts the record")


def record(conn, subject: int, holder_kind: str, holder_id: int, text: str, source: str, confidence: float, valence: float = 0.0,
           force: float = 0.0, costly: bool = False, *, source_ref: int | None = None, hops: int = 0, truth_event_id: int | None = None,
           knowledge_id: int | None = None, day: int | None = None, spilled: bool = False, check: bool = True) -> int:
    """Hold a claim (or reinforce the same one). Reaching a named holder also reaches the audiences he belongs to; an audience's claim
    spills onto the subject's own people. Vetoes only contradictions with established fact (`check`)."""
    day = B._day(conn) if day is None else int(day)
    text = _clip(text)
    if not text:
        raise ValueError("a claim needs its text")
    if check:
        _veto(conn, subject, holder_kind, holder_id, source, confidence, truth_event_id)
    old = conn.execute("SELECT * FROM claims WHERE subject_actor_id=? AND holder_kind=? AND holder_id=? AND text=?",
                       (int(subject), holder_kind, int(holder_id), text)).fetchone()
    if old is not None:
        conf = 1.0 - (1.0 - float(old["confidence"])) * (1.0 - float(confidence))
        conn.execute("UPDATE claims SET confidence=?,day=?,hops=MIN(hops,?),costly=MAX(costly,?),source=CASE WHEN ?='saw' THEN 'saw' ELSE source END,"
                     "truth_event_id=COALESCE(truth_event_id,?),knowledge_id=COALESCE(knowledge_id,?) WHERE id=?",
                     (conf, day, int(hops), int(bool(costly)), source, truth_event_id, knowledge_id, int(old["id"])))
        cid, fresh = int(old["id"]), False
    else:
        cid = int(conn.execute(
            """INSERT INTO claims(subject_actor_id,holder_kind,holder_id,text,source,source_ref,hops,confidence,valence,force,costly,truth_event_id,knowledge_id,
                                  spilled,first_day,day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (int(subject), holder_kind, int(holder_id), text, source, source_ref, int(hops), float(confidence), float(valence), float(force), int(bool(costly)),
             truth_event_id, knowledge_id, int(spilled), day, day)).lastrowid)
        fresh = True
    c = conn.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    if not spilled:
        if holder_kind == "actor" and int(holder_id) != int(subject):
            _reach_audiences(conn, c, day)
        elif holder_kind == "audience":
            _spill(conn, c, day)
    return cid


def _reach_audiences(conn, c, day: int) -> None:
    share = B.fig(conn, "audience_share")
    for a in audiences_of(conn, int(c["subject_actor_id"])):
        if is_member(conn, int(c["holder_id"]), a):
            record(conn, int(c["subject_actor_id"]), "audience", a["id"], c["text"], "told", float(c["confidence"]) * share, float(c["valence"]), float(c["force"]),
                   bool(c["costly"]), source_ref=int(c["holder_id"]), hops=int(c["hops"]) + 1, truth_event_id=c["truth_event_id"], day=day, check=False)


def _spill(conn, c, day: int) -> None:
    """What an audience holds of a man reaches the people connected to him (his kin and household) and the outfit he belongs to."""
    if abs(float(c["valence"])) <= 0.0:
        return
    share = B.fig(conn, "spill_share")
    s = int(c["subject_actor_id"])
    name = B.name_of(conn, s)
    targets = {i: 1.0 for i in kin(conn, s)}
    for seat in B.seats(conn, s):
        targets.setdefault(int(seat["org_actor_id"]), 0.7)
    for t, w in targets.items():
        record(conn, t, "audience", int(c["holder_id"]), f"{name}'s own: {c['text']}", "inferred", float(c["confidence"]) * share * w, float(c["valence"]) * share,
               float(c["force"]) * share, bool(c["costly"]), source_ref=s, hops=int(c["hops"]) + 1, truth_event_id=c["truth_event_id"], day=day, spilled=True, check=False)


def propose(conn, text: str, subject: int, *, holder: str | int | None = None, source: str = "inferred", confidence: float = 0.6, valence: float = 0.0,
            force: float = 0.0, costly: bool = False, truth_event_id: int | None = None, day: int | None = None) -> dict:
    """The GM proposes a claim. `holder` is an audience key (of the subject), a person's name or id, or None (the street: the
    subject's home-place audience). The engine vetoes only a contradiction with established fact."""
    subject = int(subject)
    aud = audiences_of(conn, subject)
    hk, hid, hname = "audience", None, None
    if holder is None:
        pick = [a for a in aud if _rule(conn, a) == "home_place"] or aud
        if not pick:
            raise ValueError("this subject has no audience that could hold it")
        hid, hname = pick[0]["id"], pick[0]["label"]
    elif isinstance(holder, str) and not holder.lstrip("-").isdigit() and any(a["key"] == holder for a in aud):
        a = next(a for a in aud if a["key"] == holder)
        hid, hname = a["id"], a["label"]
    else:
        hk = "actor"
        if isinstance(holder, int) or str(holder).isdigit():
            hid = int(holder)
        else:
            r = conn.execute("SELECT id FROM actors WHERE name=? COLLATE NOCASE", (str(holder),)).fetchone()
            if r is None:
                raise ValueError(f"no audience or person is called {holder}")
            hid = int(r[0])
        hname = B.name_of(conn, hid)
    cid = record(conn, subject, hk, int(hid), text, source, confidence, valence, force, costly, truth_event_id=truth_event_id, day=day)
    return {"saved": "claim", "summary": f"{hname} holds of {B.name_of(conn, subject)}: {_clip(text, 80)}", "claim_id": cid}


# ---- hearing and telling ------------------------------------------------------------------------------------

def _rel(conn, a: int, b: int):
    return conn.execute("SELECT * FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(a), int(b))).fetchone()


def hear(conn, holder: int, subject: int, text: str, confidence: float, valence: float, force: float, costly: bool, source: str, *, teller: int | None = None,
         hops: int = 1, truth_event_id: int | None = None, knowledge_id: int | None = None, day: int | None = None) -> int | None:
    """A named person takes in a claim he did not see for himself: discounted by the teller's credibility (his trust in him), closeness to the
    subject resisting bad news, resentment of the subject discounting good news."""
    if int(holder) == int(subject) and teller is None:
        return None
    conf = float(confidence)
    if teller is not None:
        r = _rel(conn, holder, teller)
        trust = float(r["trust"]) if r else 0.0
        conf *= max(B.fig(conn, "cred_floor"), min(1.0, 0.5 + trust / 200.0))
    rs = _rel(conn, holder, subject)
    if rs is not None and int(holder) != int(subject):
        close = max(0.0, (float(rs["affection"]) + float(rs["trust"])) / 200.0)
        resent = max(0.0, float(rs["resentment"]) / 100.0)
        if valence < 0:
            conf *= 1.0 - B.fig(conn, "resist") * close
        elif valence > 0:
            conf *= 1.0 - B.fig(conn, "rival_discount") * resent
    cid = record(conn, int(subject), "actor", int(holder), text, source, max(0.0, min(1.0, conf)), valence, force, costly, source_ref=teller, hops=hops,
                 truth_event_id=truth_event_id, knowledge_id=knowledge_id, day=day, check=False)
    if int(holder) == int(subject) and valence < 0:  # he hears of himself what damages him: it goes on his list
        from . import news_choices
        news_choices.hears_of_himself(conn, cid, B._day(conn) if day is None else int(day))
    return cid


def _state(conn, key: str) -> int:
    r = conn.execute("SELECT value FROM claims_state WHERE key=?", (key,)).fetchone()
    return int(r[0]) if r else -1


def _set_state(conn, key: str, v: int) -> None:
    conn.execute("INSERT INTO claims_state(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, int(v)))


def _event_subject(conn, e) -> int | None:
    if e["source_actor_id"] is not None:
        return int(e["source_actor_id"])
    r = conn.execute("SELECT actor_id FROM event_targets WHERE event_id=? ORDER BY actor_id LIMIT 1", (int(e["id"]),)).fetchone()
    return int(r[0]) if r else None


def _keys_for(conn, actor: int, subject: int) -> list[str]:
    return [a["key"] for a in audiences_of(conn, subject) if is_member(conn, actor, a)]


def from_events(conn, day: int) -> int:
    """Happenings the package says colour a name become claims: held first-hand by those who were there, and (when public) by the
    audiences the subject belongs to, in proportion to how far a public act reaches."""
    n = 0
    cur = _state(conn, "event_cursor")
    if cur < 0:  # first pass: what is older than a week is history, not news
        cur = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM events WHERE day<=?", (int(day) - WEEK,)).fetchone()[0])
    for e in conn.execute("SELECT id,day,event_type,title,summary,severity,source_actor_id FROM events WHERE id>? ORDER BY id", (cur,)).fetchall():
        eff = _effect(conn, e["event_type"])
        subject = _event_subject(conn, e) if eff else None
        if eff is None or subject is None:
            continue
        text = e["summary"] if e["summary"] and e["summary"] != e["title"] else e["title"]
        costly = bool(eff.get("costly"))
        for w in conn.execute("SELECT actor_id,witness_type,confidence FROM event_witnesses WHERE event_id=?", (int(e["id"]),)).fetchall():
            h = int(w["actor_id"])
            if h == subject or not B._alive(conn, h):
                continue
            keys = _keys_for(conn, h, subject)
            record(conn, subject, "actor", h, text, "saw" if w["witness_type"] in ("participant", "observer", "target", "source") else "told",
                   float(w["confidence"]), _per(eff.get("valence"), keys), _per(eff.get("force"), keys), costly, truth_event_id=int(e["id"]), day=int(e["day"]), check=False)
            n += 1
        vis = conn.execute("SELECT visibility FROM event_information WHERE event_id=?", (int(e["id"]),)).fetchone()
        if vis and vis[0] == "public":
            reach = B.fig(conn, "public_reach_base") + B.fig(conn, "public_reach_sev") * int(e["severity"])
            for a in audiences_of(conn, subject):
                record(conn, subject, "audience", a["id"], text, "told", min(1.0, reach), _per(eff.get("valence"), [a["key"]]), _per(eff.get("force"), [a["key"]]),
                       costly, hops=1, truth_event_id=int(e["id"]), day=int(e["day"]), check=False)
                n += 1
        cur = int(e["id"])
    _set_state(conn, "event_cursor", cur)
    return n


def from_incidents(conn, day: int) -> int:
    """The organisations' own happenings (an informing, an arrest, a killing) are claims too: held first-hand by the man it was done to and the
    head it was raised to, and by the subject's audiences when the package says such a thing is public."""
    cur = _state(conn, "incident_cursor")
    if cur < 0:
        cur = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM org_incidents WHERE day<=?", (int(day) - WEEK,)).fetchone()[0])
    n = 0
    for i in conn.execute("SELECT * FROM org_incidents WHERE id>? ORDER BY id", (cur,)).fetchall():
        cur = int(i["id"])
        eff = _effect(conn, i["kind"])
        s = i["offender_actor_id"]
        if eff is None or s is None:
            continue
        s = int(s)
        try:
            meta = json.loads(i["metadata_json"] or "{}")
        except ValueError:
            meta = {}
        text = meta.get("summary") or (f"{B.name_of(conn, s)} {i['kind']}" + (f": {B.name_of(conn, i['victim_actor_id'])}" if i["victim_actor_id"] is not None else ""))
        holders = {int(i["victim_actor_id"])} if i["victim_actor_id"] is not None else set()
        if i["raised_to_org_actor_id"] is not None:
            from .orgs import head_of
            h = head_of(conn, int(i["raised_to_org_actor_id"]))
            if h is not None:
                holders.add(int(h))
        for h in holders:
            if h != s and B._alive(conn, h):
                keys = _keys_for(conn, h, s)
                record(conn, s, "actor", h, text, "saw" if h == i["victim_actor_id"] else "told", 0.9, _per(eff.get("valence"), keys), _per(eff.get("force"), keys),
                       bool(eff.get("costly")), day=int(i["day"]), check=False)
                n += 1
        if eff.get("public"):
            reach = B.fig(conn, "public_reach_base") + B.fig(conn, "public_reach_sev") * (1 + 2 * int(i["matters"]))
            for a in audiences_of(conn, s):
                record(conn, s, "audience", a["id"], text, "told", min(1.0, reach), _per(eff.get("valence"), [a["key"]]), _per(eff.get("force"), [a["key"]]),
                       bool(eff.get("costly")), hops=1, day=int(i["day"]), check=False)
                n += 1
    _set_state(conn, "incident_cursor", cur)
    return n


def from_knowledge(conn, day: int) -> int:
    """What people come to know of those happenings (word of mouth, the existing rumour layer) becomes second-hand claims."""
    cur = _state(conn, "knowledge_cursor")
    if cur < 0:
        cur = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM knowledge WHERE learned_day<=?", (int(day) - WEEK,)).fetchone()[0])
    n = 0
    for k in conn.execute("SELECT id,knower_actor_id,belief_text,confidence,truth_event_id,learned_day FROM knowledge WHERE id>? AND truth_event_id IS NOT NULL ORDER BY id", (cur,)).fetchall():
        cur = int(k["id"])
        e = conn.execute("SELECT id,day,event_type,title,summary,source_actor_id FROM events WHERE id=?", (int(k["truth_event_id"]),)).fetchone()
        eff = _effect(conn, e["event_type"]) if e else None
        subject = _event_subject(conn, e) if eff else None
        if subject is None:
            continue
        text = e["summary"] if e["summary"] and e["summary"] != e["title"] else e["title"]
        prov = conn.execute("SELECT source_kind FROM knowledge_provenance WHERE knowledge_id=? ORDER BY id LIMIT 1", (int(k["id"]),)).fetchone()
        src = "read" if prov and prov[0] == "channel" else "told"
        keys = _keys_for(conn, int(k["knower_actor_id"]), subject)
        if hear(conn, int(k["knower_actor_id"]), subject, text, float(k["confidence"]) * B.fig(conn, "hop_factor"), _per(eff.get("valence"), keys),
                _per(eff.get("force"), keys), bool(eff.get("costly")), src, teller=None, hops=1, truth_event_id=int(e["id"]), knowledge_id=int(k["id"]), day=int(k["learned_day"])) is not None:
            n += 1
    _set_state(conn, "knowledge_cursor", cur)
    return n


def spread(conn, day: int) -> int:
    """Fresh claims are told on, person to person: to those he knows, more readily when it is bad news, more readily by a rival, each
    hop discounted. A subject can hear what is said of him this way."""
    n = 0
    window, hop = int(B.fig(conn, "tell_window")), B.fig(conn, "hop_factor")
    fresh = conn.execute("SELECT * FROM claims WHERE holder_kind='actor' AND day>=? AND day<=? AND holder_id<>subject_actor_id ORDER BY id", (int(day) - window, int(day))).fetchall()
    for c in fresh:
        h, s = int(c["holder_id"]), int(c["subject_actor_id"])
        if not B._alive(conn, h):
            continue
        rs = _rel(conn, h, s)
        rival = 1.0 + (B.fig(conn, "rival_boost") if rs is not None and float(rs["resentment"]) >= 30 and float(c["valence"]) < 0 else 0.0)
        eff = _eff(conn, c, day)
        base = B.fig(conn, "tell_rate") * (0.3 + abs(float(c["valence"]))) * (1.0 + (B.fig(conn, "tell_bad_bonus") if float(c["valence"]) < 0 else 0.0)) * rival
        for r in conn.execute("SELECT actor_b_id,familiarity FROM relationships WHERE actor_a_id=? AND familiarity>=?", (h, B.fig(conn, "tell_fam_min"))).fetchall():
            t = int(r["actor_b_id"])
            if B._rng(conn, "tell", c["id"], t, day).random() >= base * (0.5 + float(r["familiarity"]) / 100.0):
                continue
            if not B._alive(conn, t):
                continue
            if hear(conn, t, s, c["text"], eff * hop, float(c["valence"]), float(c["force"]), bool(c["costly"]), "told", teller=h, hops=int(c["hops"]) + 1,
                    truth_event_id=c["truth_event_id"], day=day) is not None:
                n += 1
    return n


def prune(conn, day: int) -> int:
    """A claim faded below the forgetting weight is forgotten (storage only: whatever is still weighed is kept)."""
    gone = []
    floor = B.fig(conn, "forget_below")
    for c in conn.execute("SELECT * FROM claims WHERE day<?", (int(day) - int(B.fig(conn, "claim_half_life_days")),)).fetchall():
        if _eff(conn, c, day) < floor:
            gone.append(int(c["id"]))
    for i in range(0, len(gone), 500):
        conn.execute(f"DELETE FROM claims WHERE id IN ({','.join('?' * len(gone[i:i + 500]))})", gone[i:i + 500])
    return len(gone)


# ---- what the claims feed ---------------------------------------------------------------------------------

def read_for(conn, observer: int, subject: int) -> dict | None:
    """What the observer holds of the subject, for the room read: where it comes from (saw, heard, read, inferred), how sure, the strongest
    thing he holds, and his regard. None when he holds nothing."""
    day = B._day(conn)
    rows = conn.execute("SELECT * FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=?", (int(observer), int(subject))).fetchall()
    reg, force, mass = regard_of(conn, observer, subject, day)
    if not rows:
        if mass <= 0:
            return None
        return {"source": "heard", "sure": min(1.0, mass), "holds": None, "regard": reg, "force": force}
    top = max(rows, key=lambda c: weigh(conn, c, day))
    word = {"saw": "saw", "told": "heard", "read": "read", "inferred": "inferred"}[top["source"]]
    return {"source": word, "sure": _eff(conn, top, day), "holds": top["text"], "regard": reg, "force": force}


def claims_about(conn, subject: int, holder: int | None = None, limit: int = 8) -> list[dict]:
    """Claims held of a subject: by one person, else by the audiences (for lookup)."""
    day = B._day(conn)
    if holder is not None:
        rows = conn.execute("SELECT * FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=?", (int(holder), int(subject))).fetchall()
        who = lambda c: B.name_of(conn, holder)
    else:
        rows = conn.execute("SELECT * FROM claims WHERE holder_kind='audience' AND subject_actor_id=?", (int(subject),)).fetchall()
        labels = {int(r["id"]): r["label"] for r in conn.execute("SELECT id,label FROM audiences")}
        who = lambda c: labels.get(int(c["holder_id"]), "?")
    rows = sorted(rows, key=lambda c: -weigh(conn, c, day))[:limit]
    return [{"holder": who(c), "claim": c["text"], "source": c["source"], "sure": round(_eff(conn, c, day), 2), "day": int(c["day"])} for c in rows]


def deterrence(conn, subject: int, audience: dict | None = None) -> float:
    """How formidable an audience holds him to be, -1 (a man who lets slights pass) to 1. Answering a slight is partly weighed against
    looking weak, so a man held weak has more reason to answer."""
    auds = [audience] if audience else audiences_of(conn, subject)
    imps = [impression(conn, a, subject) for a in auds]
    imps = [i for i in imps if i["mass"] > 0]
    return sum(i["force"] for i in imps) / len(imps) if imps else 0.0


# ---- the weekly pass ----------------------------------------------------------------------------------------

def _pull_standing(conn, subject: int, day: int) -> int:
    """Seat standing follows the outfit's own impression of the man: it moves a share of the way to where the men of the outfit hold him."""
    n = 0
    pull, prior = B.fig(conn, "standing_pull"), B.fig(conn, "standing_prior")
    for a in audiences_of(conn, subject):
        if _rule(conn, a) != "org":
            continue
        imp = impression(conn, a, subject, day)
        if imp["mass"] <= 0:
            continue
        share = imp["mass"] / (imp["mass"] + prior)
        seat = conn.execute("SELECT id,standing FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (subject, a["ref"])).fetchone()
        if seat is None:
            continue
        st = float(seat["standing"])
        tgt = (imp["regard"] + 1.0) / 2.0
        conn.execute("UPDATE org_seats SET standing=? WHERE id=?", (max(0.0, min(1.0, st + pull * share * (tgt - st))), int(seat["id"])))
        n += 1
    return n


def _access(conn, subject: int, day: int) -> int:
    """Reputation is access: a name held in regard draws approaches (an offer, a tip, a favour asked), as a happening that reaches him."""
    best = None
    for a in audiences_of(conn, subject):
        imp = impression(conn, a, subject, day)
        if imp["regard"] >= B.fig(conn, "access_regard") and (best is None or imp["regard"] > best["regard"]):
            best = imp
    if best is None:
        return 0
    p = B.fig(conn, "access_rate") * best["regard"] * best["mass"] / (best["mass"] + 1.0)
    if B._rng(conn, "access", subject, day).random() >= p:
        return 0
    B._event(conn, day, "reputation_access", f"{B.name_of(conn, subject)} is sought out",
             f"His name has weight with {best['label']}: someone comes to him with an approach, a favour asked or a tip.", subject)
    return 1


def _react(conn, subject: int, day: int) -> int:
    """The people connected to him meet what is held of him in their own days (the school gate, the shops, the parish): who was there, how
    they treated the connected person, what comes home. Same machinery for anyone's family."""
    fresh = conn.execute("SELECT * FROM claims WHERE holder_kind='audience' AND subject_actor_id=? AND day>=? AND spilled=0 AND ABS(valence)>0 ORDER BY id", (subject, int(day) - WEEK)).fetchall()
    if not fresh:
        return 0
    salience = sum(float(c["confidence"]) * abs(float(c["valence"])) for c in fresh)
    top = max(fresh, key=lambda c: weigh(conn, c, day))
    n = 0
    rate = B.fig(conn, "react_rate")
    for person in sorted(kin(conn, subject)):
        if not B._alive(conn, person):
            continue
        if B._rng(conn, "react", subject, person, day).random() >= 1.0 - math.exp(-rate * salience):
            continue
        loc = _here(conn, person)
        around = [int(r[0]) for r in conn.execute("SELECT id FROM actors WHERE current_location_id=? AND id NOT IN (?,?) AND status<>'dead' ORDER BY id", (loc, subject, person))] if loc is not None else []
        rng = B._rng(conn, "react_present", subject, person, day)
        rng.shuffle(around)
        holders = [p for p in around if conn.execute("SELECT 1 FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=?", (p, subject)).fetchone()]
        present = (holders + [p for p in around if p not in holders])[: int(B.fig(conn, "present_n"))]
        if present:
            regs = [regard_of(conn, p, subject, day)[0] for p in present]
            reg = sum(regs) / len(regs)
            fears = [float(r["fear"]) for p in present for r in [_rel(conn, p, subject)] if r is not None]
            fear = sum(fears) / len(fears) if fears else 0.0
        else:
            reg, fear = float(top["valence"]), 0.0
        t = B.fig(conn, "react_regard_t")
        band = "afraid" if fear >= B.fig(conn, "react_fear_t") else "cold" if reg <= -t else "warm" if reg >= t else "mixed"
        phrase = (_d(conn).get("circle_phrases") or {}).get(band, "watch")
        place = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone() if loc is not None else None
        who = ", ".join(B.name_of(conn, p) for p in present) or "people there"
        text = (f"{B.name_of(conn, person)} at {place[0] if place else 'the day'}: {who} {phrase} them over what is said of {B.name_of(conn, subject)}"
                f" ({_clip(top['text'], 90)})")
        routing = "first_hand" if _here(conn, subject) == loc and loc is not None else "cutaway"
        conn.execute("INSERT INTO circle_reactions(day,person_actor_id,subject_actor_id,location_id,claim_id,regard,fear,present_json,text,routing) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (day, person, subject, loc, int(top["id"]), reg, fear, "[" + ",".join(map(str, present)) + "]", text, routing))
        for p in present:  # the spill driver: how they hold him moves how they treat his people
            from .relationships import adjust_relationship
            adjust_relationship(conn, p, person, day, stance_delta=B.fig(conn, "spill_stance") * reg, fear_delta=max(0.0, fear / 100.0 * 2.0))
        if reg <= -t:
            from .relationships import adjust_relationship
            adjust_relationship(conn, person, subject, day, resentment_delta=B.fig(conn, "react_resent") * min(1.0, -reg))
        n += 1
    return n


def _come_home(conn, day: int) -> int:
    """A reaction nobody told him of reaches him when he and the person meet again (a wife tells him what was said). He then holds it
    himself: a named man hears what is said of him."""
    n = 0
    for r in conn.execute("SELECT * FROM circle_reactions WHERE told_day IS NULL AND routing='cutaway'").fetchall():
        if _here(conn, int(r["person_actor_id"])) is not None and _here(conn, int(r["person_actor_id"])) == _here(conn, int(r["subject_actor_id"])) and B._alive(conn, int(r["subject_actor_id"])):
            conn.execute("UPDATE circle_reactions SET told_day=? WHERE id=?", (day, int(r["id"])))
            c = conn.execute("SELECT * FROM claims WHERE id=?", (r["claim_id"],)).fetchone() if r["claim_id"] is not None else None
            if c is not None:
                hear(conn, int(r["subject_actor_id"]), int(r["subject_actor_id"]), SAID + c["text"], float(c["confidence"]), float(c["valence"]), float(c["force"]),
                     bool(c["costly"]), "told", teller=int(r["person_actor_id"]), hops=1, truth_event_id=c["truth_event_id"], day=day)
            n += 1
    return n


SAID = "it is said of him: "


def deliveries(conn, me: int, day: int) -> list[tuple[str, str, str]]:
    """(key, kind, text) for what reaches him through the people around him: a reaction he was there for, what came home, and what
    people told him of himself. Each is entered once by its key in the ledger; here the state is only marked."""
    out = []
    for r in conn.execute("SELECT * FROM circle_reactions WHERE subject_actor_id=? AND entered_day IS NULL AND (routing='first_hand' OR told_day IS NOT NULL) ORDER BY id", (int(me),)).fetchall():
        conn.execute("UPDATE circle_reactions SET entered_day=? WHERE id=?", (day, int(r["id"])))
        out.append((f"reaction:{r['id']}", "first_hand" if r["routing"] == "first_hand" else "home", r["text"]))
    for c in conn.execute("SELECT id,text,source_ref FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=? AND source_ref IS NOT NULL AND text NOT LIKE ? ESCAPE '!' ORDER BY id",
                          (int(me), int(me), SAID.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%")).fetchall():
        out.append((f"claim:{c['id']}", "about_him", f"{B.name_of(conn, c['source_ref'])} lets him know what is said of him: {c['text']}"))
    return out


def cutaways(conn, me: int, day: int) -> list[dict]:
    """What his people met that he was not there for and has not been told: for the GM to write a cutaway, marked as outside his
    knowledge (he learns it only if it comes home to him)."""
    out = []
    for r in conn.execute("SELECT * FROM circle_reactions WHERE subject_actor_id=? AND routing='cutaway' AND told_day IS NULL AND cutaway_day IS NULL ORDER BY id", (int(me),)).fetchall():
        conn.execute("UPDATE circle_reactions SET cutaway_day=? WHERE id=?", (day, int(r["id"])))
        out.append({"cutaway": r["text"], "note": "outside his knowledge: he hears of it only if it is told or comes home"})
    return out


def weekly(conn, day: int) -> dict:
    """The week's pass, run with the organisation lifecycle's: happenings and word of mouth become claims, claims are told on, the old
    forgotten; for everyone whose name moved, impressions settle, seat standing follows, the people around them meet it, approaches come."""
    if not enabled(conn):
        return {}
    out = {"claims_from_events": from_events(conn, day)}
    out["claims_from_incidents"] = from_incidents(conn, day)
    out["claims_from_knowledge"] = from_knowledge(conn, day)
    out["claims_told"] = spread(conn, day)
    out["claims_forgotten"] = prune(conn, day)
    subjects = [int(r[0]) for r in conn.execute("SELECT DISTINCT subject_actor_id FROM claims WHERE day>=? ORDER BY subject_actor_id", (int(day) - WEEK,))]
    st = rx = ac = 0
    for s in subjects:
        if not B._alive(conn, s):
            continue
        for a in audiences_of(conn, s):
            imp = impression(conn, a, s, day)
            conn.execute("INSERT INTO impressions(audience_id,subject_actor_id,regard,force,mass,day) VALUES (?,?,?,?,?,?) ON CONFLICT(audience_id,subject_actor_id) DO UPDATE SET "
                         "regard=excluded.regard,force=excluded.force,mass=excluded.mass,day=excluded.day", (a["id"], s, imp["regard"], imp["force"], imp["mass"], int(day)))
        st += _pull_standing(conn, s, day)
        rx += _react(conn, s, day)
        ac += _access(conn, s, day)
    out["claims_standing_moved"], out["claims_reactions"], out["claims_access"] = st, rx, ac
    out["claims_came_home"] = _come_home(conn, day)
    return out


def _register() -> None:
    from . import org_lifecycle
    org_lifecycle.on_week(weekly)


_register()
