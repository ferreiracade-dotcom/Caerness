"""Neighbourhood ties at the opening: who already knows whom through the street, the parish (or any organisation they belong to) and the work.

No new people. Households link their members, each business links its owner and staff, each organisation's members are tied to a few
fellow members, and people who live at the same place (below the package's group size) are tied to a few neighbours. All counts are the
package's `neighbourhood.ties` data. A link is a `social_contact_links` row (a_id < b_id); the run's own review grows or cools it.
Deterministic on the run seed.
"""
from __future__ import annotations

import json
import random
import sqlite3

from . import design
from .world_package import package_for


def _rng(conn: sqlite3.Connection, key: str) -> random.Random:
    return random.Random(f"{design.run_seed(conn)}:opening_ties:{key}")


def build(conn: sqlite3.Connection) -> dict[str, int]:
    path = package_for(conn).data.get("neighbourhood")
    if path is None:
        return {}
    cfg = (json.loads(path.read_text(encoding="utf-8")) or {}).get("ties")
    if not cfg:
        return {}
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    alive = {int(r[0]) for r in conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active'")}
    rows: dict[tuple, tuple] = {}

    def link(a: int, b: int, kind: str, ctx, r: random.Random, basis: str) -> None:
        if a == b or a not in alive or b not in alive:
            return
        lo, hi = (a, b) if a < b else (b, a)
        key = (lo, hi, kind, ctx)
        if key in rows:
            return
        aff = cfg["affinity"][kind]
        rows[key] = (lo, hi, kind, ctx, round(r.uniform(float(aff[0]), float(aff[1])), 1),
                     json.dumps({"authority": "ENGINE_DERIVED_SHARED_CONTEXT", "basis": basis, "opening": True}))

    def sample_links(members: list, k: list, kind: str, ctx, r: random.Random, basis: str) -> None:
        if len(members) < 2:
            return
        for a in members:
            n = r.randint(int(k[0]), int(k[1]))
            for b in r.sample(members, min(len(members), n + 1)):
                link(a, b, kind, ctx, r, basis)

    hh: dict[int, list[int]] = {}
    for h, a in conn.execute("SELECT household_id,actor_id FROM household_members WHERE status='active' ORDER BY household_id,actor_id"):
        hh.setdefault(int(h), []).append(int(a))
    for h, ms in hh.items():
        r = _rng(conn, f"hh:{h}")
        for i, a in enumerate(ms):
            for b in ms[i + 1:]:
                link(a, b, "household", h, r, "same household")

    ent: dict[int, list[int]] = {}
    for e, a in conn.execute("SELECT enterprise_id,actor_id FROM enterprise_staff WHERE status='active' ORDER BY enterprise_id,actor_id"):
        ent.setdefault(int(e), []).append(int(a))
    for e, o in conn.execute("SELECT id,owner_actor_id FROM civilian_enterprises"):
        if o is not None:
            ent.setdefault(int(e), []).append(int(o))
    for e, ms in ent.items():
        sample_links(sorted(set(ms)), cfg["work_each"], "work", e, _rng(conn, f"work:{e}"), "same workplace")

    inst: dict[int, list[int]] = {}
    for i, a in conn.execute("SELECT institution_actor_id,member_actor_id FROM institution_memberships WHERE status='active' ORDER BY 1,2"):
        inst.setdefault(int(i), []).append(int(a))
    for i, ms in inst.items():
        sample_links(sorted(set(ms)), cfg["institution_each"], "institution", i, _rng(conn, f"inst:{i}"), "same organisation")

    loc: dict[int, list[int]] = {}
    for l, a in conn.execute("SELECT current_location_id,id FROM actors WHERE actor_type='character' AND status='active' "
                             "AND current_location_id IS NOT NULL ORDER BY 1,2"):
        loc.setdefault(int(l), []).append(int(a))
    for l, ms in loc.items():
        if len(ms) <= int(cfg["max_group"]):
            sample_links(ms, cfg["locality_each"], "locality", l, _rng(conn, f"loc:{l}"), "same place")

    counts = {"household": 0, "work": 0, "institution": 0, "locality": 0}
    for key in rows:
        counts[key[2]] += 1
    review = day + int(cfg["review_after_days"])
    conn.executemany(
        """INSERT OR IGNORE INTO social_contact_links(actor_a_id,actor_b_id,context_kind,context_id,affinity,started_day,last_review_day,
                                                      next_review_day,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?, 'active', ?)""",
        [(v[0], v[1], v[2], v[3], v[4], day, day, review, v[5]) for v in rows.values()])
    return counts
