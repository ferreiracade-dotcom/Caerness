"""What the outfits and their men carry into the opening: the named quarrels of the bible as dated events, old money debts between outfits,
past incidents between men (with the heat they wrote and the resentment they left), and favours owed up the ladder.

Canon first: the package's `opening_past.canon_events` and `debts.pairs` come from bible text and are written as they are. The ordinary
incidents are drawn from per-role rates (design figures `op_*`), inert records (done, nothing raised) that fade as heat by the run's own
half-life. Nothing here moves money: a debt is an unpaid sum, an incident a record, an obligation a standing favour. Deterministic: each
draw is keyed on the run seed. The words (kinds of incident, reasons) are the package's; none are fixed here.
"""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import date

from . import design, org_heat, org_motives
from .world_package import package_for


def _rng(conn: sqlite3.Connection, key: str) -> random.Random:
    return random.Random(f"{design.run_seed(conn)}:opening_past:{key}")


def _v(conn: sqlite3.Connection, spec, default: float = 0.0) -> float:
    return org_motives._value(conn, spec, default)


def _members(conn: sqlite3.Connection, orgs: dict[str, int]) -> dict[int, list[sqlite3.Row]]:
    """Active seat holders of each organisation, with role and birth day, in a fixed order."""
    out: dict[int, list[sqlite3.Row]] = {o: [] for o in orgs.values()}
    ph = ",".join("?" * len(out))
    for r in conn.execute(
            f"""SELECT s.actor_id,s.org_actor_id,s.role_key,s.superior_actor_id,s.unit_id,lp.birth_day FROM org_seats s
                JOIN actor_life_profiles lp ON lp.actor_id=s.actor_id JOIN actors a ON a.id=s.actor_id
                WHERE s.status='active' AND s.org_actor_id IN ({ph}) AND a.status='active' AND lp.birth_day IS NOT NULL
                ORDER BY s.org_actor_id,s.actor_id""", tuple(out)):
        out[int(r["org_actor_id"])].append(r)
    return out


def _age(birth_day: int, day: int) -> float:
    return (day - int(birth_day)) / 365.0


def build(conn: sqlite3.Connection) -> dict[str, int]:
    cfg = (org_motives._sphere_data(conn) or {}).get("opening_past")
    if not cfg:
        return {}
    from .relationships import ensure_relationship
    day0 = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    pkg = package_for(conn)
    start = date.fromisoformat(str(pkg.calendar["start"]))
    org_ids = {str(r["name"]): int(r["id"]) for r in conn.execute("SELECT id,name FROM actors WHERE actor_type='institution'")}
    outfit_names = [str(o["institution"]) for o in (org_motives._sphere_data(conn).get("outfits") or {}).values()]
    orgs = {n: org_ids[n] for n in outfit_names if n in org_ids}
    members = _members(conn, orgs)
    made = {"canon_events": 0, "incidents": 0, "resentments": 0, "debts": 0, "obligations": 0, "heat_rows": 0}
    events: list[tuple[int, int, int, int | None, str, dict]] = []  # day, offender, org, victim, kind, meta

    def pick(org: int, r: random.Random, day: int, min_age: float = 18.0) -> int | None:
        elig = [m for m in members.get(org, []) if _age(m["birth_day"], day) >= min_age]
        return int(r.choice(elig)["actor_id"]) if elig else None

    # canon: the named events, dated in their year
    for i, ev in enumerate(cfg.get("canon_events") or []):
        o, a = orgs.get(str(ev["offender_org"])), orgs.get(str(ev["against_org"]))
        if o is None:
            continue
        d = (date(int(ev["year"]), 7, 1) - start).days + day0
        who = pick(o, _rng(conn, f"canon:{i}"), d)
        if who is None:
            continue
        events.append((d, who, o, None, str(ev["kind"]), {"history": ev["text"], "basis": ev.get("basis"), "against_org": a, "canon": True}))
        made["canon_events"] += 1

    # ordinary past incidents, by the role's yearly chance over the years the package looks back
    years = _v(conn, cfg.get("years_back"), 8.0)
    rates = {str(k): _v(conn, v) for k, v in (cfg.get("incident_year") or {}).items()}
    same_share = _v(conn, cfg.get("victim_same_org"), 0.5)
    rivals: dict[int, list[int]] = {}
    for r in conn.execute("SELECT from_org,to_org FROM org_tension WHERE level>0 ORDER BY from_org,to_org"):
        rivals.setdefault(int(r[0]), []).append(int(r[1]))
    for org in sorted(members):
        for m in members[org]:
            rate = rates.get(str(m["role_key"]))
            if not rate:
                continue
            r = _rng(conn, f"inc:{m['actor_id']}")
            for yr in range(int(years)):
                if r.random() >= rate:
                    continue
                d = day0 - yr * 365 - r.randint(1, 365)
                if _age(m["birth_day"], d) < 16.0:
                    continue
                other = rivals.get(org) or []
                victim = None
                if r.random() < same_share or not other:
                    pool = [x for x in members[org] if int(x["actor_id"]) != int(m["actor_id"]) and _age(x["birth_day"], d) >= 16.0]
                    victim = int(r.choice(pool)["actor_id"]) if pool else None
                else:
                    victim = pick(r.choice(other), r, d, 16.0)
                if victim is None or victim == int(m["actor_id"]):
                    continue
                events.append((d, int(m["actor_id"]), org, victim, "incident", {"past": True}))
                made["incidents"] += 1

    heat = cfg.get("heat") or {}
    lo, hi = (_v(conn, x) for x in (cfg.get("resentment") or [30, 70]))
    for d, off, org, victim, kind, meta in sorted(events, key=lambda e: (e[0], e[1])):
        loc = conn.execute("SELECT ground_location_id FROM org_units u JOIN org_seats s ON s.unit_id=u.id WHERE s.actor_id=? AND s.org_actor_id=? LIMIT 1",
                           (off, org)).fetchone()
        conn.execute(
            """INSERT INTO org_incidents(day,kind,offender_actor_id,victim_actor_id,victim_line_id,location_id,matters,raised_to_org_actor_id,status,metadata_json)
               VALUES (?,?,?,?,NULL,?,0,NULL,'done',?)""",
            (d, kind, off, victim, loc[0] if loc else None, json.dumps({**meta, "opening_past": True}, sort_keys=True)))
        scale = _v(conn, heat.get("canon_scale"), 1.0) if meta.get("canon") else 1.0
        org_heat.add(conn, org, d, public=_v(conn, heat.get("public")) * scale, investigative=_v(conn, heat.get("investigative")) * scale,
                     violence=_v(conn, heat.get("violence")) * scale)
        made["heat_rows"] += 1
        if victim is not None:
            r = _rng(conn, f"resent:{d}:{off}:{victim}")
            before = int(conn.execute("SELECT COUNT(*) FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (victim, off)).fetchone()[0])
            cool = 0.5 ** (max(0, day0 - d) / 365.0 / max(0.1, _v(conn, cfg.get("resentment_half_life_years"), 2.0)))  # an old grudge has cooled
            ensure_relationship(conn, victim, off, d, started_day=d, familiarity=r.uniform(40, 70), resentment=r.uniform(lo, hi) * cool,
                                stance=-r.uniform(15, 45), trust=-r.uniform(5, 35))
            made["resentments"] += 1 - before

    # old money debts between outfits, from canon's quarrels
    from . import org_dealings
    dd = cfg.get("debts") or {}
    for i, p in enumerate(dd.get("pairs") or []):
        c, dbt = orgs.get(str(p["creditor"])), orgs.get(str(p["debtor"]))
        if c is None or dbt is None:
            continue
        r = _rng(conn, f"debt:{i}")
        amount = round(r.uniform(_v(conn, dd.get("lo"), 1000.0), _v(conn, dd.get("hi"), 10000.0)), -2)
        if org_dealings.owe(conn, c, dbt, amount, str(p["origin"]), day0 - r.randint(60, 700)) is not None:
            made["debts"] += 1

    # favours owed up the ladder
    ob = cfg.get("obligation") or {}
    share = _v(conn, ob.get("share"))
    reasons = list(ob.get("reasons") or [])
    if share > 0 and reasons:
        for org in sorted(members):
            for m in members[org]:
                sup = m["superior_actor_id"]
                if sup is None or int(sup) == int(m["actor_id"]):
                    continue
                r = _rng(conn, f"obl:{m['actor_id']}")
                if r.random() >= share:
                    continue
                name = conn.execute("SELECT name FROM actors WHERE id=?", (int(sup),)).fetchone()
                if name is None:
                    continue
                conn.execute(
                    """INSERT INTO obligations(actor_id,counterparty_actor_id,description,due_day,importance,status,source_kind,created_day,updated_day,notes)
                       VALUES (?,?,?,NULL,2,'active','opening_past',?,?,?)""",
                    (int(m["actor_id"]), int(sup), f"owes {name[0]} for {r.choice(reasons)}", day0 - r.randint(30, 900), day0,
                     "a favour owed from before the opening"))
                made["obligations"] += 1
    return made
