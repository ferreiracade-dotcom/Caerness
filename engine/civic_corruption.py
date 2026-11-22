"""Corruption and the law (politics P1).

A standing payment to an officeholder is an `org_arrangements` row like any other (the Pad's rail); here it is also a thing that can
come to light. Each week a payment may be found out: the chance rises with its size, with the electorate's ill regard of the payee and
with the ambition of the officer who would go after him (his own drive times the rank of the office he would be taking on). Exposure
opens a report with the law, which runs the city's ordinary case process; a conviction of a kind the office's eligibility bars
vacates the seat, and the vacancy rule fills it. Nothing names a post, a party or a city: ranks and kinds are package data.
"""
from __future__ import annotations

import math
import random

from . import design, electorate, offices, org_money
from .design import figure
from .world_package import package_for, politics_rules


def _d(conn) -> dict:
    return politics_rules(package_for(conn)).get("corruption_drivers") or {}


def _f(conn, name, default: float = 0.0) -> float:
    return float(figure(conn, name, default)) if name else default


def _rng(conn, *key) -> random.Random:
    return random.Random(f"{design.run_seed(conn)}:corrupt:" + ":".join(str(k) for k in key))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def rank(conn, actor: int) -> float:
    """The rank of the highest office a person holds (the package's `office_rank`), 0 when he holds none."""
    table = politics_rules(package_for(conn)).get("office_rank") or {}
    keys = offices.offices_of(conn, int(actor))
    return max((float(table.get(k, table.get("_default", 1.0))) for k in keys), default=0.0)


def ambition(conn, agency_actor: int | None, target: int) -> float:
    """What the officer stands to gain by going after the target: his own ambition times the rank of the target's office. No ceiling."""
    if agency_actor is None:
        return 0.0
    r = conn.execute("SELECT ambition FROM actor_drives WHERE actor_id=?", (int(agency_actor),)).fetchone()
    drive = float(r[0]) if r and r[0] is not None else 0.5
    return drive * _f(conn, _d(conn).get("ambition_scale"), 0.4) * rank(conn, int(target))


def put_on(conn, payer_kind: str, payer_id: int, official: int, weekly: float, *, go_between: int | None = None, day: int,
           kind: str = "kickback") -> int:
    """A standing payment to an officeholder: the same arrangement the Pad pays, labelled political."""
    return org_money.add_arrangement(conn, kind=kind, payer_kind=payer_kind, payer_id=int(payer_id), official_actor_id=int(official),
                                     weekly_usd=float(weekly), day=int(day), go_between_actor_id=go_between, position_key=f"political:{int(official)}")


def _press(conn, actor: int, day: int) -> float:
    gs = electorate.groups(conn)
    return -sum(electorate.regard(conn, int(g["id"]), int(actor), day) for g in gs) / max(1, len(gs))


def exposure_chance(conn, arrangement, day: int) -> tuple[float, dict]:
    d = _d(conn)
    official = int(arrangement["official_actor_id"])
    inv = offices.holder(conn, d.get("investigator_office")) if d.get("investigator_office") else None
    terms = {"base": _f(conn, d.get("base"), -6.0), "size": _f(conn, d.get("size"), 0.35) * math.log1p(max(0.0, float(arrangement["weekly_usd"]))),
             "ambition": _f(conn, d.get("ambition"), 1.2) * ambition(conn, inv, official),
             "press": _f(conn, d.get("press"), 1.0) * _press(conn, official, day)}
    return _sigmoid(sum(terms.values())), terms


def exposure_check(conn, day: int) -> list[int]:
    """One weekly draw per standing payment to a living officeholder. Returns the reports opened."""
    from . import crime_response
    d = _d(conn)
    kinds = d.get("kinds") or []
    if not kinds:
        return []
    q = ",".join("?" * len(kinds))
    out: list[int] = []
    for a in conn.execute(f"SELECT * FROM org_arrangements WHERE status='active' AND kind IN ({q}) AND started_day<=? ORDER BY id", (*kinds, int(day))).fetchall():
        if not offices.offices_of(conn, int(a["official_actor_id"])):
            continue
        p, terms = exposure_chance(conn, a, day)
        if _rng(conn, a["id"], day).random() >= p:
            continue
        rid = crime_response.open_report(conn, crime_kind=d.get("crime_kind") or "bribery", day=int(day), offender_actor_id=int(a["official_actor_id"]),
                                         metadata={"arrangement_id": int(a["id"]), "payer_kind": a["payer_kind"], "payer_id": int(a["payer_id"]), "terms": terms})
        conn.execute("UPDATE org_arrangements SET status='ended', ended_day=? WHERE id=?", (int(day), int(a["id"])))
        out.append(int(rid))
    return out


def convictions(conn, day: int) -> int:
    """A holder with a sentence of a kind his office's eligibility bars leaves it, convicted; the vacancy rule fills the seat."""
    n = 0
    for t in conn.execute("SELECT t.id,t.actor_id,o.office_key FROM office_terms t JOIN offices o ON o.id=t.office_id WHERE t.end_day IS NULL ORDER BY t.id").fetchall():
        bar = (offices.spec(conn, t["office_key"]).get("eligibility") or {}).get("conviction_bar") or []
        if not bar:
            continue
        q = ",".join("?" * len(bar))
        if conn.execute(f"SELECT 1 FROM sentences WHERE actor_id=? AND crime_kind IN ({q})", (int(t["actor_id"]), *bar)).fetchone():
            offices.end_term(conn, int(t["id"]), "convicted", int(day))
            n += 1
    return n


def advance(conn, day: int) -> dict:
    return {"exposed": len(exposure_check(conn, day)), "vacated": convictions(conn, day)}
