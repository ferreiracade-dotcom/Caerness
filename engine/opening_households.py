"""Households and kinship for the whole opening population, not only the seed's named people.

The packaged opening builds an organisation's people after the seed's own family resolution has run, so none of them had a spouse, children
or kin. This runs the engine's own opening-family draw (`opening_family.resolve_opening_family`: marriage at the package's rates by
name group, widowhood, remarriage, latent children) for them, and links kin that the package says are common inside one organisation.

No world words and no figures here: rates come from the package (`opening_family`). Deterministic: every draw is keyed.
"""
from __future__ import annotations

import sqlite3

from .opening_family import _day, _rng, _seed_pair, resolve_opening_family
from .world_package import package_for


def _kin_in_organisations(conn: sqlite3.Connection) -> dict[str, int]:
    cfg = package_for(conn).opening_family.get("kin_in_organisations") or {}
    prob = float(cfg.get("probability", 0.0))
    out = {"siblings": 0, "parents": 0}
    if prob <= 0:
        return out
    gap_sib = float(cfg.get("sibling_gap_years", 14))
    from .household_life import add_kinship
    rows = conn.execute(
        """SELECT a.id,a.name,s.org_actor_id,lp.birth_day FROM actors a
           JOIN org_seats s ON s.actor_id=a.id AND s.status='active'
           JOIN actor_life_profiles lp ON lp.actor_id=a.id
           WHERE a.actor_type='character' AND a.status='active' AND lp.birth_day IS NOT NULL
           ORDER BY s.org_actor_id,a.id""").fetchall()
    groups: dict[tuple[str, int], list[tuple[int, int]]] = {}
    for r in rows:
        parts = str(r["name"]).split()
        if parts:
            groups.setdefault((parts[-1], int(r["org_actor_id"])), []).append((int(r["birth_day"]), int(r["id"])))
    linked_as_younger: set[int] = set()
    for (surname, org), members in sorted(groups.items()):
        members.sort()  # oldest first
        for i in range(1, len(members)):
            bd, aid = members[i]
            older_bd, older = members[i - 1]
            gap = (bd - older_bd) / 365.0
            if aid in linked_as_younger or gap < 0:
                continue
            if _rng(f"orgkin:{surname}:{org}:{older}:{aid}").random() >= prob:
                continue
            if gap <= gap_sib:
                add_kinship(conn, older, aid, "sibling", reciprocal_kind="sibling")
                kind = "siblings"
            elif gap <= 45.0:
                add_kinship(conn, older, aid, "parent", reciprocal_kind="child")
                kind = "parents"
            else:
                continue
            _seed_pair(conn, older, aid, "kin", key=f"kin:{older}:{aid}", started_day=bd)
            linked_as_younger.add(aid)
            out[kind] += 1
    return out


def build(conn: sqlite3.Connection) -> dict[str, int]:
    """Resolve marriage and children for everyone the earlier family pass did not reach, then link kin inside organisations."""
    day = _day(conn)
    fam = resolve_opening_family(conn)
    out: dict[str, int] = {f"family_{k}": v for k, v in fam.items()}
    out.update({f"kin_{k}": v for k, v in _kin_in_organisations(conn).items()})
    out["households"] = int(conn.execute("SELECT COUNT(*) FROM households").fetchone()[0])
    out["unions"] = int(conn.execute("SELECT COUNT(*) FROM household_unions WHERE status='active'").fetchone()[0])
    return out
