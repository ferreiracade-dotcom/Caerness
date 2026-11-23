"""Prison J1.6: parole, appeals, pardons and release, through the law that already exists.

A sentence's life inside is decided by hearings on their own days: a parole hearing at the sentence's earliest release day (and again
after a reset span when it is denied), an appeal filed by weighing (a lawyer paid, a verdict rather than a plea, grounds), a pardon filed
rarely by a man with standing and publicity. Each outcome is a weighed chance from the man's own record: the share of the term served, his
conduct inside, whether he cooperated, the publicity and kind of the offence, whether he sits in an outfit outside ("mobsters meeting" is
what a board does not want), a lawyer. No quota and no ceiling: the figures are the data's. A sentence that is served out ends in a
release at its end day less good time earned by conduct. A vacated sentence goes back to the case's disposition and runs again through
the chain (a plea, a trial, a walk).

The same machinery serves anyone inside, the protagonist included; nothing here looks at who is who. All figures are package data
(`prison.json`, `reviews`).
"""
from __future__ import annotations

import json
import math
import sqlite3

from .prison import _event, _figure, _living, _name, _rng, leave, rules


def _cfg(conn: sqlite3.Connection) -> dict:
    return rules(conn).get("reviews") or {}


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _meta(row) -> dict:
    try:
        return json.loads(row["metadata_json"] or "{}")
    except (ValueError, TypeError, KeyError):
        return {}


def _stay_of(conn: sqlite3.Connection, s):
    sid = _meta(s).get("stay_id")
    return None if sid is None else conn.execute("SELECT * FROM inmate_stays WHERE id=?", (int(sid),)).fetchone()


def _infractions(conn: sqlite3.Connection, a: int, since: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM prison_events WHERE kind='infraction' AND actor_id=? AND day>=?", (int(a), int(since))).fetchone()[0])


def _conduct(conn: sqlite3.Connection, a: int, since: int) -> float:
    """How badly he has behaved inside, 0..1: 1 - exp(-infractions / reference)."""
    ref = _figure(_cfg(conn).get("infraction_ref"), 3.0)
    return 1.0 - math.exp(-_infractions(conn, a, since) / ref)


def _outside_seat(conn: sqlite3.Connection, a: int):
    return conn.execute("""SELECT s.* FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id
                           WHERE s.actor_id=? AND s.status IN ('active','held') AND p.sphere<>'prison' ORDER BY s.standing DESC LIMIT 1""", (int(a),)).fetchone()


def factors(conn: sqlite3.Connection, s, day: int) -> dict[str, float]:
    """Readings of a man and his sentence on a day, each 0..1 (the weighing multiplies them by the data's weights)."""
    from . import crime_response as cr, org_informing
    from .outfit_motives import _age
    a = int(s["actor_id"])
    st = _stay_of(conn, s)
    since = int(st["since_day"]) if st is not None else int(s["start_day"])
    term = max(1, int(s["term_days"]))
    pub = cr.publicity_of(conn, int(s["report_id"])) / 100.0 if s["report_id"] is not None else 0.0
    off = _cfg(conn).get("offence") or {}
    seat = _outside_seat(conn, a)
    fee = 0.0
    if s["case_id"] is not None:
        cs = conn.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (int(s["case_id"]),)).fetchone()
        fee = float(json.loads(cs[0] or "{}").get("lawyer_fee") or 0.0) if cs is not None else 0.0
    half = _figure(_cfg(conn).get("lawyer_half_fee"), 1.0)
    how = _meta(s).get("how")
    age = _age(conn, a, day)
    age_cfg = _cfg(conn).get("age") or {}
    return {
        "served": min(1.0, max(0.0, (int(day) - int(s["start_day"])) / term)),
        "infractions": _conduct(conn, a, since),
        "cooperation": 1.0 if org_informing.is_informer(conn, a) else 0.0,
        "publicity": min(1.0, max(0.0, pub)),
        "offence": _figure(off.get(s["crime_kind"], off.get("default")), 0.0),
        "association": 1.0 if seat is not None else 0.0,
        "standing": float(seat["standing"]) if seat is not None else 0.0,
        "lawyer": fee / (fee + half) if fee > 0 else 0.0,
        "verdict": 1.0 if how == "verdict_guilty" else 0.0,
        "plea": 1.0 if how == "plea" else 0.0,
        "grounds": _rng(conn, "grounds", int(s["id"])).random(),
        "age": 0.0 if age is None else max(0.0, min(1.0, (age - _figure(age_cfg.get("from"), 60.0)) / _figure(age_cfg.get("span"), 20.0))),
    }


def probability(conn: sqlite3.Connection, kind: str, s, day: int) -> float:
    """The chance a hearing of this kind goes the man's way: a logistic of the data's bias and weighted readings."""
    spec = _cfg(conn)[kind]
    f = factors(conn, s, day)
    z = _figure(spec["bias"]) + sum(_figure(w) * f.get(k, 0.0) for k, w in (spec.get("weights") or {}).items())
    return _sigmoid(z)


def release_day(conn: sqlite3.Connection, s) -> int:
    """The day a served sentence ends: its end day less the good time his conduct has earned (data `good_time.share` of the term)."""
    gt = _cfg(conn).get("good_time") or {}
    st = _stay_of(conn, s)
    since = int(st["since_day"]) if st is not None else int(s["start_day"])
    earned = int(round(int(s["term_days"]) * _figure(gt.get("share"), 0.0) * (1.0 - _conduct(conn, int(s["actor_id"]), since))))
    return int(s["end_day"]) - earned


def file_review(conn: sqlite3.Connection, kind: str, sentence_id: int, day: int, *, hearing_day: int | None = None) -> int | None:
    """File a parole, appeal or pardon for a sentence being served. Its hearing day is the data's lag unless one is given. One pending
    review of a kind at a time; None when the sentence is not being served or one is already pending."""
    s = conn.execute("SELECT * FROM sentences WHERE id=?", (int(sentence_id),)).fetchone()
    if s is None or s["status"] != "serving" or conn.execute("SELECT 1 FROM law_reviews WHERE sentence_id=? AND kind=? AND status='pending'", (int(sentence_id), kind)).fetchone():
        return None
    lag = int(_figure((_cfg(conn).get(kind) or {}).get("hearing_days"), 1.0))
    hday = int(hearing_day) if hearing_day is not None else int(day) + lag
    return int(conn.execute("INSERT INTO law_reviews(kind,sentence_id,actor_id,filed_day,hearing_day) VALUES (?,?,?,?,?)",
                            (kind, int(sentence_id), int(s["actor_id"]), int(day), hday)).lastrowid)


def file_parole(conn, sentence_id: int, day: int, *, hearing_day: int | None = None):
    return file_review(conn, "parole", sentence_id, day, hearing_day=hearing_day)


def file_appeal(conn, sentence_id: int, day: int, *, hearing_day: int | None = None):
    return file_review(conn, "appeal", sentence_id, day, hearing_day=hearing_day)


def file_pardon(conn, sentence_id: int, day: int, *, hearing_day: int | None = None):
    return file_review(conn, "pardon", sentence_id, day, hearing_day=hearing_day)


# ---- coming home ----

def _carry_ties(conn: sqlite3.Connection, st, day: int) -> int:
    """What a man takes out with him: the shot caller of his group is a friend, and every named man he fought is a rival."""
    from . import orgs
    from .relationships import adjust_relationship
    cfg = _cfg(conn).get("ties") or {}
    a, n = int(st["actor_id"]), 0
    pairs: list[tuple[int, str]] = []
    if st["group_id"] is not None:
        org = conn.execute("SELECT org_actor_id FROM facility_groups WHERE id=?", (int(st["group_id"]),)).fetchone()[0]
        head = orgs.head_of(conn, int(org))
        if head is not None and head != a:
            pairs.append((int(head), "ally"))
    for (o,) in conn.execute("SELECT DISTINCT other_actor_id FROM prison_events WHERE kind='fight' AND actor_id=? AND other_actor_id IS NOT NULL AND day>=?", (a, int(st["since_day"]))).fetchall():
        pairs.append((int(o), "rival"))
    for other, kind in pairs:
        conn.execute("INSERT OR REPLACE INTO inmate_ties(actor_a_id,actor_b_id,facility_id,since_day,kind,strength) VALUES (?,?,?,?,?,?)",
                     (a, other, int(st["facility_id"]), int(day), kind, _figure(cfg.get(kind + "_strength"), 0.5)))
        if kind == "ally":
            adjust_relationship(conn, a, other, int(day), affection_delta=_figure(cfg.get("ally_affection"), 0.0), trust_delta=_figure(cfg.get("ally_trust"), 0.0))
        else:
            adjust_relationship(conn, a, other, int(day), resentment_delta=_figure(cfg.get("rival_resentment"), 0.0), stance_delta=-_figure(cfg.get("rival_stance"), 0.0))
        n += 1
    return n


def come_home(conn: sqlite3.Connection, s, day: int, how: str) -> bool:
    """A man leaves prison: `released` (term served), `paroled` (free on conditions until the end day) or `pardoned`. His stay ends,
    his ties go with him, his temper drifts by what the place did to him, and the outside looks at him tomorrow."""
    from .crime_response import imposed
    from .org_lifecycle import mark_for_history
    a = int(s["actor_id"])
    st = _stay_of(conn, s)
    status = {"released": "released", "paroled": "paroled", "pardoned": "pardoned"}[how]
    meta = _meta(s)
    if how == "paroled":
        seats = [int(r[0]) for r in conn.execute("""SELECT s.org_actor_id FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id
                                                   WHERE s.actor_id=? AND s.status IN ('active','held') AND p.sphere<>'prison'""", (a,)).fetchall()]
        meta["parole"] = {"until": int(s["end_day"]), "bar_orgs": seats, "granted_day": int(day)}
    meta["came_home_how"] = how
    conn.execute("UPDATE sentences SET status=?, released_day=?, metadata_json=? WHERE id=?", (status, int(day), json.dumps(meta, sort_keys=True), int(s["id"])))
    conn.execute("UPDATE law_reviews SET status='moot' WHERE sentence_id=? AND status='pending'", (int(s["id"]),))
    other = conn.execute("SELECT 1 FROM sentences WHERE actor_id=? AND status='serving' AND id<>? LIMIT 1", (a, int(s["id"]))).fetchone()
    if other is None:  # he is free only when no other sentence still holds him
        conn.execute("UPDATE custody SET kind='released', until_day=? WHERE actor_id=? AND kind='held'", (int(day), a))
        if st is not None and st["status"] == "inside":
            _carry_ties(conn, st, int(day))
            leave(conn, int(st["id"]), int(day), "released")
    imposed(conn, a)
    mark_for_history(conn, a, {"released": "came home", "paroled": "was paroled", "pardoned": "was pardoned"}[how], int(day))
    try:
        from . import org_temperament
        org_temperament.drift(conn, a, "prison", int(day))
    except (ImportError, sqlite3.OperationalError):
        pass
    return True


def _vacate(conn: sqlite3.Connection, s, day: int) -> None:
    """An appeal won: the sentence is vacated, he is out on bail, and the case goes back to its disposition to run again through the chain."""
    from .crime_response import _set_case_meta, imposed
    a = int(s["actor_id"])
    st = _stay_of(conn, s)
    conn.execute("UPDATE sentences SET status='vacated', released_day=? WHERE id=?", (int(day), int(s["id"])))
    conn.execute("UPDATE custody SET kind='bailed', until_day=? WHERE actor_id=? AND case_id=? AND kind='held'", (int(day), a, s["case_id"]))
    conn.execute("UPDATE law_reviews SET status='moot' WHERE sentence_id=? AND status='pending'", (int(s["id"]),))
    if st is not None and st["status"] == "inside":
        leave(conn, int(st["id"]), int(day), "bailed")
    if s["case_id"] is not None:
        retrial = int(_figure((_cfg(conn).get("appeal") or {}).get("retrial_days"), 60.0))
        conn.execute("UPDATE law_enforcement_cases SET status='actionable', closed_day=NULL, next_review_day=? WHERE id=?", (int(day) + retrial, int(s["case_id"])))
        _set_case_meta(conn, int(s["case_id"]), stage="disposition", arrested=a, vacated_day=int(day))
    imposed(conn, a)


# ---- the process ----

def _owed(conn: sqlite3.Connection, s) -> int | None:
    """The day a parole hearing is owed for this serving sentence and not yet filed: its earliest release day, or one reset span after the
    last denial; None when one is pending, one was granted, or he would walk out at the end of his term before it."""
    if conn.execute("SELECT 1 FROM law_reviews WHERE sentence_id=? AND kind='parole' AND status='pending'", (int(s["id"]),)).fetchone():
        return None
    last = conn.execute("SELECT hearing_day,outcome FROM law_reviews WHERE sentence_id=? AND kind='parole' ORDER BY id DESC LIMIT 1", (int(s["id"]),)).fetchone()
    if last is not None and last["outcome"] != "denied":
        return None
    reset = int(_figure((_cfg(conn).get("parole") or {}).get("reset_days"), 365.0))
    when = int(s["earliest_release_day"]) if last is None else int(last["hearing_day"]) + reset
    return None if when >= release_day(conn, s) else when


def _schedule_parole(conn: sqlite3.Connection, day: int) -> int:
    """Every sentence being served has a parole hearing waiting."""
    n = 0
    for s in conn.execute("SELECT * FROM sentences WHERE status='serving' AND json_extract(metadata_json,'$.stay_id') IS NOT NULL ORDER BY id").fetchall():
        when = _owed(conn, s)
        if when is not None:
            file_review(conn, "parole", int(s["id"]), int(day), hearing_day=max(int(day) + 1, when))
            n += 1
    return n


def _hear(conn: sqlite3.Connection, rv, day: int) -> str:
    s = conn.execute("SELECT * FROM sentences WHERE id=?", (int(rv["sentence_id"]),)).fetchone()
    if s is None or s["status"] != "serving" or not _living(conn, int(rv["actor_id"])):
        conn.execute("UPDATE law_reviews SET status='moot' WHERE id=?", (int(rv["id"]),))
        return "moot"
    p = probability(conn, rv["kind"], s, int(day))
    won = _rng(conn, "hearing", int(rv["id"])).random() < p
    out = {"parole": ("granted", "denied"), "appeal": ("overturned", "denied"), "pardon": ("granted", "denied")}[rv["kind"]][0 if won else 1]
    conn.execute("UPDATE law_reviews SET status='heard', outcome=?, factors_json=? WHERE id=?",
                 (out, json.dumps({"p": round(p, 6), **{k: round(v, 4) for k, v in factors(conn, s, int(day)).items()}}, sort_keys=True), int(rv["id"])))
    st = _stay_of(conn, s)
    if st is not None:
        _event(conn, day, int(st["facility_id"]), "hearing_" + rv["kind"], int(s["actor_id"]), None, 0.0, f"{_name(conn, int(s['actor_id']))}'s {rv['kind']} was {out}")
    if won:
        if rv["kind"] == "appeal":
            _vacate(conn, s, int(day))
        else:
            come_home(conn, s, int(day), "paroled" if rv["kind"] == "parole" else "pardoned")
    return out


def process(conn: sqlite3.Connection, day: int) -> dict:
    """The hearings due, the sentences served out, and the hearings the day's sentences are owed."""
    out = {"hearings": 0, "released": 0, "scheduled": 0}
    if not _cfg(conn):
        return out
    out["scheduled"] = _schedule_parole(conn, int(day))
    for rv in conn.execute("SELECT * FROM law_reviews WHERE status='pending' AND hearing_day<=? ORDER BY hearing_day,id", (int(day),)).fetchall():
        _hear(conn, rv, int(day))
        out["hearings"] += 1
    for s in conn.execute("SELECT * FROM sentences WHERE status='serving' AND json_extract(metadata_json,'$.stay_id') IS NOT NULL ORDER BY id").fetchall():
        if not _living(conn, int(s["actor_id"])):
            continue
        if release_day(conn, s) <= int(day):
            come_home(conn, s, int(day), "released")
            out["released"] += 1
    for s in conn.execute("SELECT * FROM sentences WHERE status='paroled' AND end_day<=? ORDER BY id", (int(day),)).fetchall():
        conn.execute("UPDATE sentences SET status='released' WHERE id=?", (int(s["id"]),))
    return out


def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    """The earliest hearing, release of a served sentence or end of a parole: so a skip stops on each. (A man's good time can only fall
    with another infraction, so a computed release day is never too late.)"""
    if not _cfg(conn):
        return None
    due: list[int] = []
    r = conn.execute("SELECT MIN(hearing_day) FROM law_reviews WHERE status='pending'").fetchone()
    if r and r[0] is not None:
        due.append(int(r[0]))
    for s in conn.execute("SELECT * FROM sentences WHERE status='serving' AND json_extract(metadata_json,'$.stay_id') IS NOT NULL").fetchall():
        due.append(release_day(conn, s))
        if _owed(conn, s) is not None:
            due.append(int(after_day) + 1)  # a hearing is yet to be set
    r = conn.execute("SELECT MIN(end_day) FROM sentences WHERE status='paroled'").fetchone()
    if r and r[0] is not None:
        due.append(int(r[0]))
    due = [max(int(after_day) + 1, d) for d in due]
    d = min(due) if due else None
    return d if d is not None and d <= int(end_day) else None


# ---- the weekly part: what a man or his people file, and the conditions of parole ----

def weekly(conn: sqlite3.Connection, day: int) -> dict:
    from .crime_response import open_report
    cfg = _cfg(conn)
    out = {"appeals": 0, "pardons": 0, "violations": 0}
    if not cfg:
        return out
    ap, pd = cfg.get("appeal") or {}, cfg.get("pardon") or {}
    for s in conn.execute("SELECT * FROM sentences WHERE status='serving' AND json_extract(metadata_json,'$.stay_id') IS NOT NULL ORDER BY id").fetchall():
        a = int(s["actor_id"])
        if not _living(conn, a):
            continue
        f = factors(conn, s, int(day))
        if ap and not conn.execute("SELECT 1 FROM law_reviews WHERE sentence_id=? AND kind='appeal'", (int(s["id"]),)).fetchone() \
                and int(day) - int(s["start_day"]) <= _figure(ap["window_days"]) and f["plea"] < 1.0:
            p = 1.0 - math.exp(-_figure(ap["file_rate"]) * (1.0 + _figure(ap["lawyer_gain"]) * f["lawyer"]))
            if _rng(conn, "file_appeal", f"{day}:{s['id']}").random() < p and file_appeal(conn, int(s["id"]), int(day)):
                out["appeals"] += 1
        if pd and f["served"] >= _figure(pd["min_served"]) and not conn.execute("SELECT 1 FROM law_reviews WHERE sentence_id=? AND kind='pardon'", (int(s["id"]),)).fetchone():
            p = 1.0 - math.exp(-_figure(pd["file_rate"]) * (1.0 + _figure(pd["standing_gain"]) * f["standing"]))
            if _rng(conn, "file_pardon", f"{day}:{s['id']}").random() < p and file_pardon(conn, int(s["id"]), int(day)):
                out["pardons"] += 1
    cond = cfg.get("conditions") or {}
    if cond:
        for s in conn.execute("SELECT * FROM sentences WHERE status='paroled' AND end_day>? ORDER BY id", (int(day),)).fetchall():
            a = int(s["actor_id"])
            bar = (_meta(s).get("parole") or {}).get("bar_orgs") or []
            if not bar or not _living(conn, a):
                continue
            here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (a,)).fetchone()
            if here is None or here[0] is None:
                continue
            q = ",".join("?" * len(bar))
            men = conn.execute(f"""SELECT COUNT(*) FROM org_seats s JOIN actors x ON x.id=s.actor_id WHERE s.org_actor_id IN ({q}) AND s.status='active'
                                    AND s.actor_id<>? AND x.current_location_id=?""", (*bar, a, here[0])).fetchone()[0]
            if men and _rng(conn, "meet", f"{day}:{a}").random() < 1.0 - math.exp(-_figure(cond["meet_rate"]) * math.log1p(men)):
                open_report(conn, crime_kind=str(cond.get("violation_kind") or "racket"), day=int(day), offender_actor_id=a, location_id=here[0], public=False)
                out["violations"] += 1
    return out
