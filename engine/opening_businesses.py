"""Ordinary businesses across a world's neighbourhoods at the opening (shops, bars, garages, trades, firms), through the shared place and
business layer: each is a civilian enterprise with a business profile, a place held by its owner, an owner and staff who are real people
from the background population of that district's name groups.

No world words and no figures here. Everything (which districts, how many residents, the per-1,000 rate of each kind, the district mix,
the share of the real establishments that are named, owners, staff, money, age of the business) is the package's `neighbourhood` data
file. A world without that file builds nothing. Deterministic: every draw is keyed on the run seed and the district and index.
"""
from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from . import design
from .world_package import package_for


def _rng(conn: sqlite3.Connection, key: str) -> random.Random:
    return random.Random(f"{design.run_seed(conn)}:opening_business:{key}")


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _count(rng: random.Random, expected: float) -> int:
    base = int(expected)
    return base + (1 if rng.random() < expected - base else 0)


def _plan(conn: sqlite3.Connection, cfg: dict) -> list[dict[str, Any]]:
    """Every establishment the package asks for, in a fixed order: district, kind, owner sex and name group, staff count."""
    residents = float(cfg["residents"]["value"])
    named = float(cfg["named_share"]["value"])
    total_share = sum(float(d["share"]) for d in cfg["districts"]) or 1.0
    out: list[dict[str, Any]] = []
    for d in cfg["districts"]:
        loc = conn.execute("SELECT id FROM locations WHERE name=?", (d["location"],)).fetchone()
        if loc is None:
            continue
        pop = residents * float(d["share"]) / total_share
        gw = sorted((d.get("groups") or {}).items())
        for kind in sorted(cfg["rates_per_1000"]):
            expected = pop / 1000.0 * float(cfg["rates_per_1000"][kind]["rate"]) * float((d.get("mix") or {}).get(kind, 1.0)) * named
            rng = _rng(conn, f"{d['location']}:{kind}:count")
            for i in range(_count(rng, expected)):
                r = _rng(conn, f"{d['location']}:{kind}:{i}")
                prof = cfg["profiles"][kind]
                x = r.random() * sum(w for _, w in gw)
                group = gw[-1][0]
                for g, w in gw:
                    x -= w
                    if x <= 0:
                        group = g
                        break
                lo, hi = prof["staff"]
                out.append({"district": d["location"], "location_id": int(loc[0]), "kind": kind, "index": i, "group": group,
                            "sex": "male" if r.random() < float(prof["male_owner_share"]) else "female",
                            "staff": r.randint(int(lo), int(hi)), "rng_key": f"{d['location']}:{kind}:{i}"})
    return out


def _reveal(conn: sqlite3.Connection, want: dict[tuple[str, str | None], list[int]], *, pool_location: int, lo: int, hi: int,
            reason: str, subtype: str | None) -> dict[int, int]:
    """Reveal background people in batches by (name group, sex). `want` maps the key to the plan indices that need one; returns index -> actor id."""
    from .person_ecology import resolve_background_people
    got: dict[int, int] = {}
    for (group, sex), idxs in sorted(want.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        ids = resolve_background_people(conn, len(idxs), reason=reason, subtype=subtype, location_id=pool_location, min_age=lo, max_age=hi,
                                        demographic_sex=sex, name_group=group, pick_seed=f"opening_business:{reason}:{group}:{sex}")
        for i, a in zip(idxs, ids):
            got[i] = a
    return got


def build(conn: sqlite3.Connection) -> dict[str, int]:
    path = package_for(conn).data.get("neighbourhood")
    if path is None:
        return {}
    cfg = json.loads(path.read_text(encoding="utf-8"))
    from . import business, places
    from .business import configure_enterprise_business
    from .civilian import create_enterprise
    from .merchant import add_enterprise_staff
    from .opening_family import _seed_pair
    day = _day(conn)
    arche = business.archetypes(conn)
    plan = _plan(conn, cfg)
    city = conn.execute("SELECT id FROM locations WHERE kind='city' ORDER BY id LIMIT 1").fetchone()
    pool_loc = conn.execute("SELECT DISTINCT current_location_id FROM background_person_profiles WHERE current_location_id IS NOT NULL LIMIT 1").fetchone()
    pool_location = int((pool_loc or city)[0])
    oa, sa = cfg["owner_age"], cfg["staff_age"]
    domains = cfg.get("domains") or {}

    owner_want: dict[tuple[str, str | None], list[int]] = {}
    for i, e in enumerate(plan):
        owner_want.setdefault((e["group"], e["sex"]), []).append(i)
    owners = _reveal(conn, owner_want, pool_location=pool_location, lo=int(oa["min"]), hi=int(oa["max"]), reason="opening business owner", subtype=None)

    staff_want: dict[tuple[str, str | None], list[tuple[int, int]]] = {}
    for i, e in enumerate(plan):
        if i not in owners:
            continue
        for j in range(e["staff"]):
            r = _rng(conn, f"{e['rng_key']}:staff:{j}")
            male = float(cfg["profiles"][e["kind"]]["male_owner_share"])
            sex = "male" if r.random() < (male + 0.5) / 2.0 else "female"
            staff_want.setdefault((e["group"], sex), []).append((i, j))
    from .person_ecology import resolve_background_people
    staff_ids: dict[tuple[int, int], int] = {}
    for (group, sex), pairs in sorted(staff_want.items()):
        ids = resolve_background_people(conn, len(pairs), reason="opening business staff", location_id=pool_location, min_age=int(sa["min"]),
                                        max_age=int(sa["max"]), demographic_sex=sex, name_group=group,
                                        pick_seed=f"opening_business:staff:{group}:{sex}")
        for pair, a in zip(pairs, ids):
            staff_ids[pair] = a

    made = {"enterprises": 0, "places": 0, "staff": 0, "owners": 0, "unfilled": 0}
    used: set[str] = {str(r[0]) for r in conn.execute("SELECT name FROM civilian_enterprises")}
    for i, e in enumerate(plan):
        owner = owners.get(i)
        if owner is None:
            made["unfilled"] += 1
            continue
        kind = e["kind"]
        a = arche[kind]
        prof = cfg["profiles"][kind]
        r = _rng(conn, f"{e['rng_key']}:make")
        surname = str(conn.execute("SELECT name FROM actors WHERE id=?", (owner,)).fetchone()[0]).split()[-1]
        name = f"{surname}'s {a['name']}"
        if name in used:
            name = f"{surname}'s {a['name']}, {e['district']}"
        n = 2
        while name in used:
            name = f"{surname}'s {a['name']} {n}, {e['district']}"
            n += 1
        used.add(name)
        # the owner and staff live where the business is
        loc = int(e["location_id"])
        crew = [owner] + [staff_ids[(i, j)] for j in range(e["staff"]) if (i, j) in staff_ids]
        dom = domains.get(kind)
        for who in crew:
            conn.execute("UPDATE actors SET home_location_id=?,current_location_id=? WHERE id=?", (loc, loc, who))
            if dom:
                conn.execute("UPDATE background_person_profiles SET occupation_domain=?,social_archetype=? WHERE actor_id=?",
                             (dom, f"ordinary_{dom}", who))
        money = cfg["money"]
        rev = float(a["base_revenue"])
        capital = round(rev * r.uniform(*money["capital_months_of_revenue"]), 2)
        cash = round(rev * r.uniform(*money["cash_months_of_revenue"]), 2)
        eid = create_enterprise(conn, name, str(a["enterprise_kind"]), owner_actor_id=owner, location_id=loc, capital=capital, cash=cash,
                                metadata={"opening_business": True, "trade": kind, "district": e["district"]})
        add_enterprise_staff(conn, eid, owner, role="owner", authority=100)
        q = cfg["quality"]
        configure_enterprise_business(conn, eid, kind, quality=max(10, min(95, r.gauss(q["mean"], q["spread"]))),
                                      price_position=max(10, min(90, r.gauss(50, 12))), capacity=max(15, min(95, r.gauss(45, 15))),
                                      clientele_fit=max(10, min(95, r.gauss(50, 12))), service_reliability=max(10, min(95, r.gauss(55, 12))),
                                      regulatory_pressure=float(a.get("regulation", 0)) * 100.0, cadence_days=30,
                                      metadata={"opening_business": True})
        yo = cfg["years_open"]
        owner_age = (day - int(conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (owner,)).fetchone()[0])) / 365.0
        years = max(float(yo["min"]), min(r.expovariate(1.0 / float(yo["mean"])), max(float(yo["min"]), owner_age - 22.0)))
        founded = day - int(round(years * 365.0))
        conn.execute("""INSERT INTO enterprise_ecology_state(enterprise_id,founded_day,crystallized_day,structural_origin,last_review_day,metadata_json)
                        VALUES (?,?,?,'opening_history',?,?) ON CONFLICT(enterprise_id) DO NOTHING""",
                     (eid, founded, day, day, json.dumps({"opening_business": True, "population_delta": 0}, sort_keys=True)))
        places.make_place(conn, name=name, place_kind=str(prof["place_kind"]), location_id=loc, owner_ref=f"person:{owner}", day=founded,
                          enterprise_id=eid)
        made["places"] += 1
        made["owners"] += 1
        for who in crew[1:]:
            add_enterprise_staff(conn, eid, who, role="worker", authority=25)
            made["staff"] += 1
        for x, a1 in enumerate(crew):
            for b1 in crew[x + 1:]:
                _seed_pair(conn, a1, b1, "colleague", key=f"{e['rng_key']}:crew:{a1}:{b1}", started_day=max(founded, day - 365 * 3))
        made["enterprises"] += 1
    return made
