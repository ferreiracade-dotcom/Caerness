"""The politics tick, the protagonist's view and the pushes (politics P1).

One process the world clock runs next to the others. It does nothing in a world whose package carries no offices. Each time it runs
it opens and moves the races, counts the items whose day has come, answers the approvals waiting, runs the vacancy rules, seats the
convicted out, and for each whole week since it last ran draws the exposures of standing payments and lets the field shift. Elections,
votes and vacancy days are dated events: `next_due_day` names them so the skip planner stops on them. Events that touch the player
(a vote on his item or in his body, his primary or his election) go to the event log with him as the source, which is what a skip
stops for; a few things are also entered in his delivery ledger. Impressions are read lazily where they are needed.
"""
from __future__ import annotations

import json
import sqlite3

from . import civic_corruption, civic_graft, civic_seams, civic_shift, civic_votes, offices, races
from .design import figure

CURSOR = "civic_week_cursor"
LAST = "civic_last_day"
WEEK = 7


def enabled(conn) -> bool:
    return offices.enabled(conn)


def _get(conn, key: str) -> int | None:
    r = conn.execute("SELECT value FROM engine_meta WHERE key=?", (key,)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _set(conn, key: str, value: int) -> None:
    conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(int(value))))


def _player(conn) -> int | None:
    from . import player
    p = player.get_player(conn)
    return int(p["player_actor_id"]) if p is not None else None


# ---- when it next has something to do --------------------------------------------------------------------------------

def next_due_day(conn: sqlite3.Connection, after_day: int, through_day: int) -> int | None:
    if not enabled(conn):
        return None
    cands: list[int] = []
    cands.append((int(after_day) // WEEK + 1) * WEEK)  # the weekly pass falls on whole weeks of the calendar
    window = int(figure(conn, "race_open_days", 330))
    for r in conn.execute("SELECT * FROM races WHERE status='open' ORDER BY id").fetchall():
        for d in (races.filing_close(conn, r), r["primary_day"], r["election_day"]):
            if d is not None:
                cands.append(int(d))
    for r in conn.execute("SELECT result_json FROM races WHERE status='decided' ORDER BY id").fetchall():
        res = json.loads(r[0] or "{}")
        if not res.get("seated") and res.get("term_start_day") is not None:
            cands.append(int(res["term_start_day"]))
    for o in conn.execute("SELECT office_key FROM offices WHERE filled_by='elected' ORDER BY id").fetchall():
        nd = offices.next_dates(conn, o[0], int(after_day))
        if nd:
            cands.append(int(nd["election_day"]) - window)
    for (d,) in conn.execute("SELECT vote_day FROM civic_items WHERE status='open'").fetchall():
        cands.append(int(d))
    wait = int(figure(conn, "vacancy_fill_days", 21))
    for (d,) in conn.execute("SELECT since_day FROM office_vacancies WHERE status='pending'").fetchall():
        cands.append(int(d) + wait)
    cands = [d for d in cands if int(after_day) < d <= int(through_day)]
    return min(cands) if cands else None


# ---- the run -------------------------------------------------------------------------------------------------------

def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict:
    if not enabled(conn):
        return {}
    day = int(day)
    prev = _get(conn, LAST)
    prev = day - 1 if prev is None else prev
    out: dict = {}
    out["races"] = races.advance(conn, day)
    out["items"] = civic_votes.advance(conn, day)
    out["vacancies"] = offices.process_vacancies(conn, day)
    out["convicted"] = civic_corruption.convictions(conn, day)
    cur = _get(conn, CURSOR)
    cur = (day // WEEK) * WEEK - WEEK if cur is None else cur
    weeks = {"exposed": 0, "weakened": 0, "transferred": 0, "taken_up": 0, "walkouts": 0}
    while cur + WEEK <= day:
        cur += WEEK
        for k, v in civic_graft.weekly(conn, cur).items():
            weeks[k] = weeks.get(k, 0) + v
        weeks["exposed"] += len(civic_corruption.exposure_check(conn, cur))
        for k, v in civic_shift.weekly_shift(conn, cur).items():
            weeks[k] = weeks.get(k, 0) + v
        out["convicted"] += civic_corruption.convictions(conn, cur)
    out.update(weeks)
    _set(conn, CURSOR, cur)
    _set(conn, LAST, day)
    if event_logger is not None or _player(conn) is not None:
        _tell_player(conn, prev, day, event_logger)
    return out


def _sits_in(conn, actor: int, body_key: str) -> bool:
    return actor in {a for _, _, a in offices.members(conn, body_key)}


def _tell_player(conn, prev: int, day: int, logger) -> None:
    """Events and pushes for the protagonist: each is a dated happening he is part of."""
    me = _player(conn)
    if me is None:
        return
    from .simulation import SimEvent, log_event

    def emit(d: int, kind: str, title: str, text: str, ref: dict, push: str | None = None) -> None:
        if logger is not None:
            logger(day=d, event_type=f"politics:{kind}", title=title, summary=text, severity=4, source_actor_id=me)
        else:
            log_event(conn, SimEvent(day=d, event_type=f"politics:{kind}", title=title, summary=text, severity=4, source_actor_id=me))
        if push:
            civic_seams.push(conn, me, kind, push, d, ref)

    for it in conn.execute("SELECT * FROM civic_items WHERE vote_day>? AND vote_day<=? AND status<>'open' ORDER BY vote_day,id", (int(prev), int(day))).fetchall():
        sub = json.loads(it["subject_json"] or "{}")
        sponsor = sub.get("sponsor")
        if (sponsor is not None and int(sponsor) == me) or _sits_in(conn, me, it["body_office_key"]):
            what = sub.get("title") or it["item_kind"]
            emit(int(it["vote_day"]), "vote", f"A vote: {what}", f"{it['body_office_key']}: {what} {it['status']}.", {"item": int(it["id"])},
                 push=(f"The vote on {what} is in: {it['status']}." if sponsor is not None and int(sponsor) == me else None))
    for r in conn.execute("""SELECT r.*,o.office_key FROM races r JOIN offices o ON o.id=r.office_id
                             WHERE ((r.primary_day>? AND r.primary_day<=?) OR (r.election_day>? AND r.election_day<=?)) ORDER BY r.election_day,r.id""",
                          (int(prev), int(day), int(prev), int(day))).fetchall():
        if not (me in races.candidates(conn, int(r["id"])) or offices.holder(conn, r["office_key"]) == me or _backer(conn, me, r)):
            continue
        if r["primary_day"] is not None and int(prev) < int(r["primary_day"]) <= int(day):
            emit(int(r["primary_day"]), "primary", f"The primary for {r['office_key']}", f"The primary for {r['office_key']} is held.", {"race": int(r["id"])})
        if int(prev) < int(r["election_day"]) <= int(day):
            res = json.loads(r["result_json"] or "{}")
            emit(int(r["election_day"]), "election", f"Election night: {r['office_key']}", f"The count for {r['office_key']} is in.", {"race": int(r["id"])},
                 push=f"Election night for {r['office_key']}: " + (f"the winner is {_name(conn, res.get('winner'))}." if res.get("winner") is not None else "no result."))
    owed_to = {int(str(e["debtor_ref"]).split(":")[1]) for e in civic_seams.ledger_open(conn, me) if str(e["debtor_ref"]).startswith("person:")} \
        | {int(str(e["creditor_ref"]).split(":")[1]) for e in civic_seams.ledger_open(conn, me) if str(e["creditor_ref"]).startswith("person:")}
    owed_to.discard(me)
    if owed_to:
        q = ",".join("?" * len(owed_to))
        for c in conn.execute(f"SELECT id,day,offender_actor_id,crime_kind FROM crime_reports WHERE offender_actor_id IN ({q}) AND day>? AND day<=? ORDER BY day,id",
                              (*sorted(owed_to), int(prev), int(day))).fetchall():
            civic_seams.push(conn, me, "indictment", f"{_name(conn, c['offender_actor_id'])}, who you deal with, is accused of {c['crime_kind']}.", int(c["day"]), {"report": int(c["id"])})


def _backer(conn, me: int, race) -> bool:
    """He holds a seat in an organisation that has a man in the race."""
    return bool(conn.execute("""SELECT 1 FROM race_candidates c JOIN org_seats s ON s.org_actor_id=c.party_org_id AND s.actor_id=? AND s.status='active'
                                WHERE c.race_id=? LIMIT 1""", (int(me), int(race["id"]))).fetchone())


def _name(conn, actor) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (int(actor),)).fetchone() if actor is not None else None
    return r[0] if r else "no one"


# ---- the view (behind the firewall) -------------------------------------------------------------------------------------

def view(conn, observer: int, day: int) -> dict:
    """What the protagonist can know of the politics around him: the seats he holds and those near him, who owes him and whom he owes,
    the calendar ahead, how the voters hold him, and the standing payments he is part of. Nothing he is not party to."""
    me = int(observer)
    held = offices.offices_of(conn, me)
    near: list[dict] = []
    seen = set(held)
    for key in held:
        o = offices.office(conn, key)
        body = offices._json(o["body_json"], {})
        for k in (body.get("members") or []) + ([o["appointer_office_key"]] if o["appointer_office_key"] else []):
            if k and k not in seen:
                seen.add(k)
                h = offices.holder(conn, k)
                near.append({"office": k, "holder": _name(conn, h) if h is not None else None})
    owes, owed = [], []
    for e in civic_seams.ledger_open(conn, me):
        mine = e["debtor_ref"] == f"person:{me}"
        other = e["creditor_ref"] if mine else e["debtor_ref"]
        who = _name(conn, int(str(other).split(":")[1])) if str(other).startswith("person:") else str(other)
        (owes if mine else owed).append({"who": who, "what": e["purpose"] if e["purpose"] else e["ref_kind"], "kind": e["ref_kind"]})
    ahead: list[dict] = []
    for r in conn.execute("SELECT r.*,o.office_key FROM races r JOIN offices o ON o.id=r.office_id WHERE r.status='open' ORDER BY r.election_day").fetchall():
        if me in races.candidates(conn, int(r["id"])) or offices.holder(conn, r["office_key"]) == me or r["office_key"] in held:
            if r["primary_day"] is not None and int(r["primary_day"]) >= int(day):
                ahead.append({"what": f"primary for {r['office_key']}", "day": int(r["primary_day"])})
            ahead.append({"what": f"election for {r['office_key']}", "day": int(r["election_day"])})
    for it in conn.execute("SELECT * FROM civic_items WHERE status='open' AND vote_day>=? ORDER BY vote_day", (int(day),)).fetchall():
        sub = json.loads(it["subject_json"] or "{}")
        if (sub.get("sponsor") is not None and int(sub["sponsor"]) == me) or _sits_in(conn, me, it["body_office_key"]):
            ahead.append({"what": f"vote: {sub.get('title') or it['item_kind']}", "day": int(it["vote_day"])})
    key = civic_seams._electorate_key(conn)
    voters = [{"voters": r["label"], "held": r["text"], "day": int(r["day"])} for r in conn.execute(
        """SELECT a.label,c.text,c.day FROM claims c JOIN audiences a ON a.id=c.holder_id
           WHERE c.holder_kind='audience' AND c.subject_actor_id=? AND a.key=? ORDER BY c.day DESC LIMIT 8""", (me, key)).fetchall()]
    pay = []
    for a in conn.execute("""SELECT * FROM org_arrangements WHERE status='active' AND (official_actor_id=? OR go_between_actor_id=? OR (payer_kind='actor' AND payer_id=?)) ORDER BY id""",
                          (me, me, me)).fetchall():
        pay.append({"kind": a["kind"], "weekly_usd": float(a["weekly_usd"]), "official": _name(conn, a["official_actor_id"])})
    out = {"holds": held, "near": near, "owes": owes, "owed_by": owed, "ahead": sorted(ahead, key=lambda x: x["day"]), "voters": voters, "payments": pay}
    return {k: v for k, v in out.items() if v}
