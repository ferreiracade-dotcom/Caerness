"""Appointments by sponsorship (politics P1).

An appointed office is filled through a chain the package's data names: a sponsor (whoever holds the office's `sponsor` stake, an
organisation or a person) puts a man forward, the appointer (the holder of the appointer office) weighs him, and where the office
names a consenting office a holder with a courtesy block vetoes a nominee hostile to him. The man seated owes the sponsor a favour on
the ledger and a `sponsorships` row records who put him there. Nothing here names a party or a post: the chain is data and the
stakes are the field's.
"""
from __future__ import annotations

import json
import math
import random

from . import civic_field, civic_patronage, design, electorate, offices, orgs, races
from .design import figure
from .world_package import package_for, politics_rules


def _rules(conn) -> dict:
    return politics_rules(package_for(conn))


def _d(conn) -> dict:
    return _rules(conn).get("appointment_drivers") or {}


def _f(conn, name, default: float = 0.0) -> float:
    return float(figure(conn, name, default)) if name else default


def _rng(conn, *key) -> random.Random:
    return random.Random(f"{design.run_seed(conn)}:appoint:" + ":".join(str(k) for k in key))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def sponsor_actor(conn, office_key: str) -> int | None:
    """The person who sponsors for this office now: the head of the organisation that holds its sponsor stake, or the person who holds it."""
    h = civic_field.holder_of(conn, "sponsor", office_key)
    if h is None:
        return None
    return int(h[1]) if h[0] == "actor" else orgs.head_of(conn, int(h[1]))


def sponsor_of(conn, actor_id: int, office_key: str) -> int | None:
    r = conn.execute("""SELECT s.sponsor_actor_id FROM sponsorships s JOIN offices o ON o.id=s.office_id
                        WHERE s.appointee_actor_id=? AND o.office_key=? ORDER BY s.id DESC LIMIT 1""", (int(actor_id), office_key)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _pool(conn, office_key: str) -> list[int]:
    h = civic_field.holder_of(conn, "sponsor", office_key)
    if h is None:
        return []
    if h[0] == "org":
        return [int(r[0]) for r in conn.execute("SELECT DISTINCT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY actor_id", (int(h[1]),))]
    return [int(str(r[0]).split(":")[1]) for r in conn.execute("SELECT DISTINCT debtor_ref FROM agreement_terms WHERE ref_kind='favour' AND status='active' "
                                                               "AND creditor_ref=?", (f"person:{int(h[1])}",))]


def _line(conn, a: int | None, b: int | None) -> float:
    """+1 same organisation, -1 different organisations that hold stakes, 0 where either has none."""
    if a is None or b is None:
        return 0.0
    pa, pb = races.party_of(conn, int(a)), races.party_of(conn, int(b))
    return 0.0 if pa is None or pb is None else (1.0 if pa == pb else -1.0)


def _press(conn, actor: int, day: int) -> float:
    gs = electorate.groups(conn)
    return sum(electorate.regard(conn, int(g["id"]), int(actor), day) for g in gs) / max(1, len(gs))


def _nominate(conn, office_key: str, sponsor: int | None, pool: list[int], day: int, salt: str) -> int | None:
    """The sponsor's pick from those he can put forward: loyalty, standing in his organisation, debts, and a seeded spread."""
    if not pool:
        return None
    n = _d(conn).get("nominee") or {}
    h = civic_field.holder_of(conn, "sponsor", office_key)
    org = int(h[1]) if h and h[0] == "org" else None
    scores = []
    for a in pool:
        drives = conn.execute("SELECT loyalty FROM actor_drives WHERE actor_id=?", (a,)).fetchone()
        z = (_f(conn, n.get("loyalty")) * (float(drives[0]) if drives else 0.5) + _f(conn, n.get("standing")) * races._standing(conn, a, org)
             + _f(conn, n.get("debt")) * (-civic_patronage.owed(conn, a, sponsor) if sponsor is not None else 0.0)
             + _rng(conn, office_key, a, salt).gauss(0.0, _f(conn, n.get("noise_sd"))))
        scores.append(z)
    top = max(scores)
    w = [math.exp(s - top) for s in scores]
    u = _rng(conn, office_key, "pick", salt).random() * sum(w)
    acc = 0.0
    for a, wi in zip(pool, w):
        acc += wi
        if u <= acc:
            return a
    return pool[-1]


def _next_seat(conn, office_key: str) -> int | None:
    seats = int(offices.office(conn, office_key)["seats"])
    held = {int(t["seat_no"]) for t in offices._open_terms(conn, office_key)}
    return next((s for s in range(1, max(1, seats) + 1) if s not in held), None)


def fill(conn, office_key: str, day: int, seat_no: int | None = None) -> int | None:
    """Put a man in the seat through the chain. Returns the appointee, or None when nobody on the sponsor's list gets through."""
    o = offices.office(conn, office_key)
    seat = seat_no if seat_no is not None else _next_seat(conn, office_key)
    if seat is None:
        return None
    sp = sponsor_actor(conn, office_key)
    appointer = offices.holder(conn, o["appointer_office_key"]) if o["appointer_office_key"] else None
    consent_holder = offices.holder(conn, o["consent_office_key"]) if o["consent_office_key"] else None
    courtesy = bool(offices.spec(conn, office_key).get("courtesy_block"))
    a = _d(conn).get("appointer") or {}
    pool = [x for x in _pool(conn, office_key) if x != sp and offices.eligible(conn, x, office_key, int(day))[0] and not races._is_player(conn, x)]
    refused: dict[str, str] = {}
    tried = 0
    while pool:
        nominee = _nominate(conn, office_key, sp, pool, int(day), f"{seat}:{tried}")
        pool.remove(nominee)
        tried += 1
        if appointer is not None:
            z = (_f(conn, a.get("base")) + _f(conn, a.get("line")) * _line(conn, appointer, nominee) + _f(conn, a.get("press")) * _press(conn, nominee, day))
            if _rng(conn, office_key, nominee, "appointer").random() >= _sigmoid(z):
                refused[str(nominee)] = "appointer"
                continue
        if courtesy and consent_holder is not None and _line(conn, consent_holder, nominee) < 0:
            refused[str(nominee)] = "courtesy"  # a home-county senator hostile to him
            continue
        return _seat(conn, o, office_key, int(nominee), seat, sp, int(day))
    why = "no_nominee:" + json.dumps(refused, sort_keys=True)
    pend = conn.execute("SELECT id,cause FROM office_vacancies WHERE office_id=? AND seat_no=? AND status='pending' ORDER BY id DESC LIMIT 1", (int(o["id"]), seat)).fetchone()
    if pend is None:
        conn.execute("INSERT INTO office_vacancies(office_id,seat_no,since_day,cause,rule_json) VALUES (?,?,?,?,?)", (int(o["id"]), seat, int(day), why, o["vacancy_json"]))
    else:
        conn.execute("UPDATE office_vacancies SET cause=? WHERE id=?", (str(pend["cause"]).split(" | ")[0] + " | " + why, int(pend["id"])))
    return None


def put_forward(conn, actor: int, office_key: str, day: int, seat_no: int | None = None) -> int:
    """A person takes a seat by his own act (the protagonist may be appointed this way when his sponsor and appointer say yes): the same
    appointer and consent checks as any nominee. Raises ValueError with the reason when vetoed."""
    o = offices.office(conn, office_key)
    seat = seat_no if seat_no is not None else _next_seat(conn, office_key)
    if seat is None:
        raise ValueError("no_vacant_seat")
    ok, why = offices.eligible(conn, int(actor), office_key, int(day))
    if not ok:
        raise ValueError(why or "ineligible")
    appointer = offices.holder(conn, o["appointer_office_key"]) if o["appointer_office_key"] else None
    consent_holder = offices.holder(conn, o["consent_office_key"]) if o["consent_office_key"] else None
    if bool(offices.spec(conn, office_key).get("courtesy_block")) and consent_holder is not None and _line(conn, consent_holder, actor) < 0:
        raise ValueError("courtesy")
    sp = sponsor_actor(conn, office_key)
    if appointer is not None:
        a = _d(conn).get("appointer") or {}
        z = (_f(conn, a.get("base")) + _f(conn, a.get("line")) * _line(conn, appointer, actor) + _f(conn, a.get("press")) * _press(conn, actor, day))
        if _rng(conn, office_key, actor, "appointer").random() >= _sigmoid(z):
            raise ValueError("appointer")
    _seat(conn, o, office_key, int(actor), seat, sp, int(day))
    return int(actor)


def _seat(conn, o, office_key: str, nominee: int, seat: int, sponsor: int | None, day: int) -> int:
    sid = int(conn.execute("INSERT INTO sponsorships(appointee_actor_id,office_id,sponsor_actor_id,day) VALUES (?,?,?,?)", (nominee, int(o["id"]), sponsor, day)).lastrowid)
    offices.seat_holder(conn, office_key, nominee, how="appointed", day=day, seat_no=seat, source_id=sid)
    if sponsor is not None and sponsor != nominee:
        ref = civic_patronage.favour(conn, sponsor, nominee, f"appointment to {office_key}", day=day)
        conn.execute("UPDATE sponsorships SET ledger_ref=? WHERE id=?", (ref, sid))
    if civic_field.holder_of(conn, "patronage", office_key) is not None:
        civic_patronage.follow(conn, office_key, nominee, day=day, cause="appointment")
    return nominee


def review_on_change(conn, appointer_office_key: str, day: int) -> int:
    """The office has a new holder: each at-pleasure office it appoints to may change hands, by a weighed lean toward replacing an
    appointee of the other side. Returns the appointees replaced."""
    new = offices.holder(conn, appointer_office_key)
    if new is None:
        return 0
    r = _d(conn).get("replace") or {}
    n = 0
    for o in conn.execute("SELECT * FROM offices WHERE appointer_office_key=? ORDER BY id", (appointer_office_key,)).fetchall():
        key = o["office_key"]
        if not offices.spec(conn, key).get("at_pleasure"):
            continue
        for t in offices._open_terms(conn, key):
            cur = int(t["actor_id"])
            z = _f(conn, r.get("base")) + _f(conn, r.get("line")) * (-_line(conn, new, cur))
            if _rng(conn, key, cur, "replace", day).random() < _sigmoid(z):
                offices.end_term(conn, int(t["id"]), "removed", int(day))
                if fill(conn, key, day, int(t["seat_no"])) is not None:
                    n += 1
    return n
