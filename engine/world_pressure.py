"""Gap 4b: the world pushes back. Migration-time repairs (own fronts, ground, baseline relations)."""
from __future__ import annotations

import json
import sqlite3

from .underworld_rebuild import add_zone_challenger, change_relation, ensure_relation, set_zone_controller

ACTIVE_ORG = "('active','strained','fragmented')"


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def end_own_front_protection(conn: sqlite3.Connection) -> int:
    """An outfit's own controlled front (or a business its leader owns) is never protected by another outfit.
    The protection account ends; the rival lost income, files a dispute against the outfit and keeps a grudge."""
    day = _day(conn)
    ended = 0
    for a in conn.execute("SELECT * FROM underworld_protection_accounts WHERE status='active' ORDER BY id").fetchall():
        eid, prot = int(a["enterprise_id"]), int(a["protector_organization_id"])
        owner_org = conn.execute(
            f"""SELECT l.organization_id FROM underworld_business_links l JOIN underworld_organizations o ON o.id=l.organization_id
                WHERE l.enterprise_id=? AND l.link_kind IN ('owned_front','controlled_front') AND l.status='active'
                AND l.organization_id<>? AND o.status IN {ACTIVE_ORG} ORDER BY l.id LIMIT 1""", (eid, prot)).fetchone()
        if owner_org is None:
            owner_org = conn.execute(
                f"""SELECT o.id FROM civilian_enterprises e JOIN underworld_organizations o ON o.current_leader_actor_id=e.owner_actor_id
                    WHERE e.id=? AND o.id<>? AND o.status IN {ACTIVE_ORG} ORDER BY o.id LIMIT 1""", (eid, prot)).fetchone()
        if owner_org is None:
            continue
        owner = int(owner_org[0])
        meta = json.loads(a["metadata_json"] or "{}")
        meta["ended_by"] = "own_front_of_org_%d" % owner
        conn.execute("UPDATE underworld_protection_accounts SET status='ended',metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), int(a["id"])))
        conn.execute(
            """INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind,severity,status,metadata_json)
               VALUES (?,?,?,?,'protection_dispute',40,'open',?)""",
            (day, a["zone_id"], owner, prot, json.dumps({"enterprise_id": eid, "account_id": int(a["id"])}, sort_keys=True)))
        rel = ensure_relation(conn, owner, prot)
        change_relation(conn, owner, prot, kind="rival", hostility_delta=max(0.0, 50 - float(rel["hostility"])),
                        metadata={"source": "schema113_own_front"})
        ended += 1
    return ended


def claim_ground_for_outfits(conn: sqlite3.Connection) -> int:
    """An outfit with fronts or rackets in a city and no claim holds the vacant zone where they sit, else challenges it.
    Specialists, networks and canon durable families hold fronts, not ground (canon), so they are left alone."""
    done = 0
    orgs = conn.execute(
        f"""SELECT o.id,o.primary_location_id FROM underworld_organizations o WHERE o.status IN {ACTIVE_ORG}
            AND o.primary_location_id IS NOT NULL
            AND COALESCE(json_extract(o.metadata_json,'$.role'),'') <> 'specialist' AND COALESCE(json_extract(o.metadata_json,'$.source'),'') <> 'world_bible'
            AND o.organization_type <> 'network'
            AND NOT EXISTS (SELECT 1 FROM underworld_zone_claims c WHERE c.organization_id=o.id AND c.status='active')
            AND (EXISTS (SELECT 1 FROM underworld_business_links l WHERE l.organization_id=o.id AND l.status='active'
                         AND l.link_kind IN ('owned_front','controlled_front'))
                 OR EXISTS (SELECT 1 FROM underworld_racket_sites r WHERE r.organization_id=o.id AND r.status='active'))
            ORDER BY o.id""").fetchall()
    for o in orgs:
        oid, loc = int(o[0]), int(o[1])
        zones = [int(r[0]) for r in conn.execute("SELECT id FROM underworld_zones WHERE city_location_id=? AND status='active' ORDER BY id", (loc,))]
        if not zones:
            continue
        marks = f"({','.join('?' * len(zones))})"
        sit: dict[int, int] = {}
        for z, in conn.execute(f"SELECT zone_id FROM underworld_business_links WHERE organization_id=? AND status='active' AND zone_id IN {marks}", (oid, *zones)):
            sit[int(z)] = sit.get(int(z), 0) + 1
        for z, in conn.execute(f"SELECT zone_id FROM underworld_racket_sites WHERE organization_id=? AND status='active' AND zone_id IN {marks}", (oid, *zones)):
            sit[int(z)] = sit.get(int(z), 0) + 1
        for z, in conn.execute(
                f"""SELECT p.zone_id FROM underworld_protection_accounts p JOIN underworld_business_links l ON l.enterprise_id=p.enterprise_id
                    WHERE l.organization_id=? AND l.status='active' AND l.link_kind IN ('owned_front','controlled_front')
                    AND p.zone_id IN {marks}""", (oid, *zones)):
            sit[int(z)] = sit.get(int(z), 0) + 1
        held = {int(r[0]): float(r[1]) for r in conn.execute(
            f"SELECT zone_id,strength FROM underworld_zone_claims WHERE claim_kind='controller' AND status='active' AND zone_id IN {marks}", zones)}
        cand = sorted(sit, key=lambda k: (-sit[k], k))
        vacant = [z for z in cand if z not in held] or [z for z in zones if z not in held]
        meta = {"source": "schema113"}
        if vacant:
            set_zone_controller(conn, vacant[0], oid, strength=30, local_support=25, fear=35, metadata=meta)
        elif cand:
            add_zone_challenger(conn, cand[0], oid, strength=25, severity=25, metadata=meta)
        else:
            add_zone_challenger(conn, min(held, key=lambda k: (held[k], k)), oid, strength=25, severity=25, metadata=meta)
        done += 1
    return done


def seed_baseline_relations(conn: sqlite3.Connection, only_org: int | None = None) -> int:
    """Outfits sharing a city know each other: neutral or rival by overlap of activities and ground, hostility 10-40."""
    made = 0
    rows = conn.execute(f"SELECT id,primary_location_id FROM underworld_organizations WHERE status IN {ACTIVE_ORG} AND primary_location_id IS NOT NULL ORDER BY id").fetchall()
    by_city: dict[int, list[int]] = {}
    for r in rows:
        by_city.setdefault(int(r[1]), []).append(int(r[0]))
    kinds: dict[int, set[str]] = {}
    for oid, k in conn.execute("SELECT organization_id,racket_kind FROM underworld_racket_sites WHERE status='active' AND organization_id IS NOT NULL"):
        kinds.setdefault(int(oid), set()).add(str(k))
    zoned = {int(r[0]) for r in conn.execute("SELECT organization_id FROM underworld_zone_claims WHERE status='active'")}
    for orgs in by_city.values():
        for i, x in enumerate(orgs):
            for y in orgs[i + 1:]:
                a, b = (x, y) if x < y else (y, x)
                if only_org is not None and only_org not in (x, y):
                    continue
                if conn.execute("SELECT 1 FROM underworld_relations WHERE organization_a_id=? AND organization_b_id=?", (a, b)).fetchone():
                    continue
                shared = len(kinds.get(x, set()) & kinds.get(y, set()))
                both_zoned = x in zoned and y in zoned
                hostility = min(40.0, 10.0 + 8.0 * shared + (6.0 if both_zoned else 0.0) + (a * 7 + b * 3) % 7)
                kind = "rival" if (shared >= 2 or (shared >= 1 and both_zoned)) else "neutral"
                ensure_relation(conn, a, b, relation_kind=kind, hostility=hostility, respect=20)
                made += 1
    return made
