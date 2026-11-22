"""The push and the delivery ledger (information phase 1a, spec 7.3).

Every scene, advance and resume carries a texture block: bearing, the room read, what he reads in the others there, and the news
that reaches him (about himself and about other people, through his habits and his people). Nothing here waits to be asked.

The ledger keeps what has been delivered. A happening that reaches him is entered once; an item not yet delivered is returned again on
the next call (nothing is dropped); a delivered one is never repeated. How much one call carries follows the weight of what is waiting
(its significance, growing as it waits): there is no threshold between "full wave" and "nothing", and no tier table.
"""
from __future__ import annotations

import sqlite3

from . import bearing as B
from .design import run_seed  # noqa: F401  (kept for streams)


def enabled(conn: sqlite3.Connection) -> bool:
    return B.enabled(conn)


def _like(text: str) -> str:
    return "%" + text.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def _clip(text, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def circle(conn, me: int) -> dict[int, float]:
    """The people close to him and how close: kin, household, the men above and below him, people he has dealt with."""
    out: dict[int, float] = {}

    def put(i, w):
        if i is not None and int(i) != me and w > out.get(int(i), 0.0):
            out[int(i)] = w
    for a, b in conn.execute("SELECT actor_a_id,actor_b_id FROM kinship_links WHERE (actor_a_id=? OR actor_b_id=?) AND ended_day IS NULL", (me, me)):
        put(b if int(a) == me else a, 1.0)
    for (i,) in conn.execute("SELECT actor_id FROM household_members WHERE status='active' AND household_id IN "
                             "(SELECT household_id FROM household_members WHERE actor_id=? AND status='active')", (me,)):
        put(i, 0.8)
    for s in B.seats(conn, me):
        put(s["superior_actor_id"], 0.6)
    for (i,) in conn.execute("SELECT actor_id FROM org_seats WHERE superior_actor_id=? AND status='active'", (me,)):
        put(i, 0.6)
    for m in conn.execute("SELECT ref_actor_id FROM bearing_marks WHERE actor_id=? AND kind='retinue' AND status='active'", (me,)):
        put(m[0], 0.6)
    for i, f in conn.execute("SELECT actor_b_id,familiarity FROM relationships WHERE actor_a_id=? AND familiarity>=20", (me,)):
        put(i, 0.5 * float(f) / 100.0)
    return out


def _cursor(conn, me: int):
    r = conn.execute("SELECT * FROM texture_cursor WHERE viewer_actor_id=?", (me,)).fetchone()
    if r is None:
        mk = conn.execute("SELECT COALESCE(MAX(id),0) FROM knowledge").fetchone()[0]
        me_ = conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
        mr = conn.execute("SELECT COALESCE(MAX(id),0) FROM rumours").fetchone()[0]
        conn.execute("INSERT INTO texture_cursor(viewer_actor_id,knowledge_id,event_id,rumour_id) VALUES (?,?,?,?)", (me, mk, me_, mr))
        return None
    return r


def _violent(conn, event_type: str) -> bool:
    return any(w in str(event_type).lower() for w in B.data(conn).get("violent_event_types") or [])


def _significance(conn, me, circ, *, public: bool, severity: int, ids, event_type: str = "", mentions_him: bool = False) -> float:
    close = max((circ.get(i, 0.0) for i in ids), default=0.0)
    him = mentions_him or me in ids
    return (B.fig(conn, "sig_base") + (B.fig(conn, "sig_public") if public else 0.0) + B.fig(conn, "sig_sev") * severity
            + (B.fig(conn, "sig_him") if him else 0.0) + B.fig(conn, "sig_circle") * close
            + (B.fig(conn, "sig_violent") if _violent(conn, event_type) else 0.0))


def _via(conn, kind: str, key: str, habit: str | None) -> str:
    words = (B.data(conn).get("channels") or {}).get(kind) or []
    if kind == "read" and habit:
        return habit
    return words[sum(map(ord, key)) % len(words)] if words else kind


def _enter(conn, me, key, kind, text, via, sig, day) -> None:
    conn.execute("INSERT OR IGNORE INTO delivery_ledger(viewer_actor_id,item_key,kind,text,via,significance,first_day) VALUES (?,?,?,?,?,?,?)",
                 (me, key, kind, _clip(text, 170), via, float(sig), day))


def ingest(conn, me: int, place: int | None, day: int) -> None:
    """Enter what has reached him since the last call: what he learned, public happenings that reach him through his habits and
    his people, talk running where he is, and what came home. Each is entered once (the ledger key); the cursor only saves the scan."""
    cur = _cursor(conn, me)
    if cur is None:
        return
    circ = circle(conn, me)
    my_name = B.name_of(conn, me)
    habit = conn.execute("SELECT text FROM bearing_marks WHERE actor_id=? AND kind='habit' AND status='active' ORDER BY id DESC LIMIT 1", (me,)).fetchone()
    habit = str(habit[0]) if habit else None
    # what he learned (about himself and about others)
    for k in conn.execute("SELECT id,belief_text,truth_event_id FROM knowledge WHERE knower_actor_id=? AND id>? ORDER BY id", (me, cur["knowledge_id"])).fetchall():
        ev = conn.execute("SELECT e.event_type,e.severity,e.source_actor_id,ei.visibility FROM events e LEFT JOIN event_information ei ON ei.event_id=e.id WHERE e.id=?",
                          (int(k["truth_event_id"]),)).fetchone() if k["truth_event_id"] is not None else None
        ids = {int(r[0]) for r in conn.execute("SELECT actor_id FROM event_targets WHERE event_id=?", (int(k["truth_event_id"]),))} if ev else set()
        if ev and ev["source_actor_id"] is not None:
            ids.add(int(ev["source_actor_id"]))
        key = f"event:{k['truth_event_id']}" if ev else f"knowledge:{k['id']}"
        kind = "about_him" if me in ids or my_name in str(k["belief_text"]) else "news"
        sig = _significance(conn, me, circ, public=bool(ev and ev["visibility"] == "public"), severity=int(ev["severity"]) if ev else 1, ids=ids,
                            event_type=str(ev["event_type"]) if ev else "", mentions_him=my_name in str(k["belief_text"]))
        _enter(conn, me, key, kind, k["belief_text"], _via(conn, "told", key, None), sig, day)
    # public happenings that reach him through his habits and his people
    for e in conn.execute("""SELECT e.id,e.day,e.event_type,e.title,e.summary,e.severity,e.source_actor_id FROM events e JOIN event_information ei ON ei.event_id=e.id
                             WHERE e.id>? AND ei.visibility='public' ORDER BY e.id""", (cur["event_id"],)).fetchall():
        ids = {int(r[0]) for r in conn.execute("SELECT actor_id FROM event_targets WHERE event_id=?", (int(e["id"]),))}
        if e["source_actor_id"] is not None:
            ids.add(int(e["source_actor_id"]))
        close = max((circ.get(i, 0.0) for i in ids), default=0.0)
        score = (B.fig(conn, "reach_base") + B.fig(conn, "reach_public") + B.fig(conn, "reach_sev") * int(e["severity"]) + B.fig(conn, "reach_circle") * close
                 + (B.fig(conn, "reach_habit") if habit else 0.0)) + (1.0 if me in ids else 0.0)
        if B._rng(conn, "reach", me, e["id"]).random() >= score:
            continue
        key = f"event:{e['id']}"
        sig = _significance(conn, me, circ, public=True, severity=int(e["severity"]), ids=ids, event_type=str(e["event_type"]))
        _enter(conn, me, key, "about_him" if me in ids else "news", f"{e['title']}: {e['summary']}" if e["summary"] and e["summary"] != e["title"] else e["title"],
               _via(conn, "read", key, habit), sig, int(e["day"]))
    # talk running where he is
    if place is not None:
        for r in conn.execute("""SELECT r.id,r.text,r.truth_event_id,rl.prevalence FROM rumours r JOIN rumour_locations rl ON rl.rumour_id=r.id AND rl.location_id=?
                                 WHERE r.id>? AND r.status='circulating' ORDER BY r.id""", (place, cur["rumour_id"])).fetchall():
            if r["truth_event_id"] is not None and conn.execute("SELECT 1 FROM delivery_ledger WHERE viewer_actor_id=? AND item_key=?", (me, f"event:{r['truth_event_id']}")).fetchone():
                continue
            key = f"rumour:{r['id']}"
            sig = B.fig(conn, "sig_base") + B.fig(conn, "sig_public") * float(r["prevalence"]) + (B.fig(conn, "sig_him") if my_name in str(r["text"]) else 0.0)
            _enter(conn, me, key, "talk", r["text"], _via(conn, "talk", key, None), sig, day)
    # what came home: his own people hearing of him
    kin = [i for i, w in circ.items() if w >= 0.8]
    if kin:
        for k in conn.execute(f"SELECT id,knower_actor_id,belief_text FROM knowledge WHERE id>? AND knower_actor_id IN ({','.join('?' * len(kin))}) AND belief_text LIKE ? ESCAPE '!'",
                              (cur["knowledge_id"], *kin, _like(my_name))).fetchall():
            key = f"home:{k['id']}"
            _enter(conn, me, key, "home", f"{B.name_of(conn, k['knower_actor_id'])}: {k['belief_text']}", _via(conn, "home", key, None),
                   B.fig(conn, "sig_base") + B.fig(conn, "sig_him") + B.fig(conn, "sig_circle"), day)
    from . import claims
    if claims.enabled(conn):  # his people's days, and what others tell him of himself
        for key, kind, text in claims.deliveries(conn, me, day):
            _enter(conn, me, key, kind, text, _via(conn, "home", key, None), B.fig(conn, "sig_base") + B.fig(conn, "sig_him") + B.fig(conn, "sig_circle"), day)
    mk = conn.execute("SELECT COALESCE(MAX(id),0) FROM knowledge").fetchone()[0]
    me_ = conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
    mr = conn.execute("SELECT COALESCE(MAX(id),0) FROM rumours").fetchone()[0]
    conn.execute("UPDATE texture_cursor SET knowledge_id=?,event_id=?,rumour_id=? WHERE viewer_actor_id=?", (mk, me_, mr, me))


def deliver(conn, me: int, day: int) -> list[dict]:
    """What waits, heaviest first, until the call's attention is used (always at least the heaviest). What is not taken stays
    pending and grows heavier each day it waits; what is taken is marked delivered and never returned."""
    rows = conn.execute("SELECT * FROM delivery_ledger WHERE viewer_actor_id=? AND delivered_day IS NULL", (me,)).fetchall()
    gain = B.fig(conn, "push_age_gain")
    weighed = sorted(rows, key=lambda r: -(float(r["significance"]) * (1.0 + gain * max(0, day - int(r["first_day"])))))
    budget, used, out = B.fig(conn, "push_attention"), 0.0, []
    for r in weighed:
        w = float(r["significance"]) * (1.0 + gain * max(0, day - int(r["first_day"])))
        if out and used + w > budget:
            break
        used += w
        conn.execute("UPDATE delivery_ledger SET delivered_day=?,delivered_count=delivered_count+1 WHERE id=?", (day, int(r["id"])))
        ago = day - int(r["first_day"])
        out.append({k: v for k, v in {"what": r["text"], "via": r["via"], "kind": r["kind"], "days_ago": ago if ago > 0 else None}.items() if v is not None})
    return out


def pending_count(conn, me: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM delivery_ledger WHERE viewer_actor_id=? AND delivered_day IS NULL", (me,)).fetchone()[0])


def shown(conn, me: int, limit: int = 12) -> list[dict]:
    """The ledger of what he has been shown (for lookup), newest first."""
    return [{"what": r["text"], "via": r["via"], "when": r["delivered_day"]} for r in conn.execute(
        "SELECT text,via,delivered_day FROM delivery_ledger WHERE viewer_actor_id=? AND delivered_day IS NOT NULL ORDER BY delivered_day DESC,id DESC LIMIT ?", (me, limit))]


def block(conn, me: int, place: int | None, people: list[int], *, news: bool = True) -> dict | None:
    """The texture block for the protagonist's situation. None when the world's package supplies no presence data (nothing is added).
    `people` are the notable people in the scene. Commits nothing."""
    if not enabled(conn):
        return None
    day = B._day(conn)
    mine = B.bearing(conn, me)
    bear = {"retinue": [r["text"] for r in mine["retinue"]] or None, "signals": [s["text"] + (" (beyond his means)" if s.get("beyond_means") else "") for s in mine["signals"]] or None,
            "spending": mine["spending"]}
    forms_used: set[str] = set()
    room = []
    for p in people:
        if int(p) == me:
            continue
        rr = B.room_read(conn, me, int(p))
        shows = []
        if rr.get("placed"):
            due = B.forms_due(conn, me, int(p))
            shows = [f["key"] for f in due if B.form_known(conn, int(p), f)]
        entry = {"id": int(p), "name": B.name_of(conn, p), "toward_him": rr.get("stance"), "from": rr["from"], "sure": rr["sure"], "changed": rr.get("changed"),
                 "holds": rr.get("holds"), "reads_him_as": rr.get("reads_him_as")}
        if shows:
            entry["shows"] = shows
            forms_used.update(shows)
            if any(w in str(rr.get("stance") or "") for w in ("resents", "contemptuous")):
                entry["manner"] = "sullen, thin"
        room.append({k: v for k, v in entry.items() if v is not None})
    reads, hidden = [], []
    for p in people:
        if int(p) == me:
            continue
        r = B.reads_of(conn, me, int(p))
        read = r["read"]
        if len(read) > 3 or read.get("forms_he_knows") or read.get("forms_he_is_unsure_of"):
            reads.append(read)
            forms_used.update(read.get("forms_he_knows") or []); forms_used.update(read.get("forms_he_is_unsure_of") or [])
        if r["hidden"]:
            hidden.append(r["hidden"])
            forms_used.update(r["hidden"]["due"])
    out: dict = {"bearing": {k: v for k, v in bear.items() if v}}
    if room:
        out["room"] = room
    if reads:
        out["he_reads"] = reads
    if forms_used:
        out["form_text"] = B.form_text(conn, forms_used)
    if news:
        ingest(conn, me, place, day)
        items = deliver(conn, me, day)
        if items:
            out["news"] = items
        waiting = pending_count(conn, me)
        if waiting:
            out["more_waiting"] = waiting
    if news:
        from . import claims
        if claims.enabled(conn):
            hidden += claims.cutaways(conn, me, day)
    if hidden:
        out["outside_his_knowledge"] = hidden
    todo = B.unrecorded(conn, me)
    if todo:
        out["to_record"] = todo
    return out
