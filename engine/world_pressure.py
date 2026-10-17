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


# -- schema 114: people to hurt, promote and lose; fronts that run as businesses; spread in loyalty ------------------------

_VICE = ("brothel protection", "courtesan house leverage")


def _full_members(conn: sqlite3.Connection, oid: int) -> float:
    prof = conn.execute("SELECT COALESCE(core_members,0)+COALESCE(active_members,0) FROM underworld_membership_profiles WHERE organization_id=?", (oid,)).fetchone()
    if prof and prof[0]:
        return float(prof[0])
    r = conn.execute("SELECT member_count_estimate FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    return float(r[0] or 0) if r else 0.0


def seed_named_personnel(conn: sqlite3.Connection, oid: int, rng=None) -> int:
    """Give an outfit the named people a gang of its size has: lieutenants (an underboss in a large one), a keeper of accounts, house
    enforcers and rank and file, drawn from the place's own reservoir (nobody invented). The count follows the membership's size.
    Command picks follow the leader sex rule; occupation follows Stage because the reservoir already does."""
    import random as _random
    from . import temperament as tp
    from . import underworld_ecology as ue
    from .underworld_rebuild import create_personnel, ensure_organization_culture
    org = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (oid,)).fetchone()
    if not org or org["primary_location_id"] is None:
        return 0
    loc = int(org["primary_location_id"])
    full = _full_members(conn, oid)
    have = int(conn.execute("SELECT COUNT(*) FROM underworld_personnel WHERE organization_id=? AND status='active' AND role_kind<>'boss'", (oid,)).fetchone()[0])
    from . import temperament as _tp
    cls_ = _tp.outfit_class(conn, oid)  # a fence or a lender keeps a few hands and buys the rest
    need = max(1 if full >= 6 else 0, int(round(0.10 * full))) - have  # a tenth of the membership is named; every real gang has at least one
    if need <= 0:
        return 0
    rng = rng or _random.Random(oid * 7919 + 114)
    cls = tp.outfit_class(conn, oid)
    kinds = {r[0] for r in conn.execute("SELECT racket_kind FROM underworld_racket_sites WHERE organization_id=? AND status='active'", (oid,))}
    sex_cls, p_male = ("vice", ue.P_MALE_VICE) if kinds & set(_VICE) else (("trade", ue.P_MALE_TRADE) if cls == "specialist" else ("violent", ue.P_MALE_VIOLENT))
    senior = int(conn.execute("SELECT COUNT(*) FROM underworld_personnel WHERE organization_id=? AND status='active' AND role_kind IN ('underboss','lieutenant')", (oid,)).fetchone()[0])
    keeper = conn.execute("SELECT 1 FROM underworld_personnel WHERE organization_id=? AND status='active' AND role_kind='accountant'", (oid,)).fetchone() is not None
    roles: list[str] = []
    if full >= 40 and not conn.execute("SELECT 1 FROM underworld_personnel WHERE organization_id=? AND status='active' AND role_kind='underboss'", (oid,)).fetchone():
        roles.append("underboss")
    if senior + len(roles) == 0 and full >= 14:
        roles.append("lieutenant")
    if not keeper and full >= 8 and (cls != "street" or full >= 20):
        roles.append("accountant")
    if not roles or need > len(roles):
        roles.append("enforcer")
    spare = max(0, need - len(roles))
    roles += ["lieutenant"] * max(0, int(round(full / 14.0)) - senior - roles.count("lieutenant") - roles.count("underboss"))
    roles += ["enforcer"] * int(round(spare * .3)) + ["collector"] * int(round(spare * .1)) + ["associate"] * int(round(spare * .1))
    roles += ["member"] * max(0, need - len(roles))
    roles = roles[:need]
    model = str(ensure_organization_culture(conn, oid)["membership_model"])
    crews = [int(r[0]) for r in conn.execute("SELECT id FROM underworld_crews WHERE organization_id=? AND status='active' ORDER BY id", (oid,))]
    made = 0
    for i, role in enumerate(roles):
        u = rng.random()
        status = {"sworn": "sworn_member", "blood_household": "blood_family" if u < .7 else ("employee" if u < .8 else "member"),
                  "contractual": "member" if u < .55 else ("employee" if u < .85 else "associate"),
                  "networked": "member" if u < .5 else "employee",
                  "fluid": "member" if u < .6 else ("associate" if u < .85 else "employee")}.get(model, "member")
        if role == "accountant":
            status = "employee" if model in ("contractual", "networked") else status
        try:
            if role in ("underboss", "lieutenant"):
                sex = ue._wanted_sex(conn, f"{role}:{sex_cls}", p_male, rng)
                aid = ue._person(conn, loc, role, strict=False, oid=oid, rng=rng, sex=sex)
                ue._note_sex(conn, f"{role}:{sex_cls}", aid)
                create_personnel(conn, oid, role_kind=role, actor_id=aid, membership_status=status, rng=rng)
            else:
                crew = crews[i % len(crews)] if crews and role in ("member", "enforcer", "collector", "associate") else None
                aid = ue._person(conn, loc, role, strict=False, oid=oid, rng=rng, sex=None)  # gangsters keep to their corners, not the whole town's scenes
                create_personnel(conn, oid, role_kind=role, crew_id=crew, actor_id=aid, membership_status=status, rng=rng)
            made += 1
        except (ue._NoPerson, RuntimeError):
            break
    return made


def seed_all_named_personnel(conn: sqlite3.Connection) -> int:
    n = 0
    for r in conn.execute(f"SELECT id FROM underworld_organizations WHERE status IN {ACTIVE_ORG} ORDER BY id").fetchall():
        n += seed_named_personnel(conn, int(r[0]))
    return n


def backfill_front_profiles(conn: sqlite3.Connection) -> int:
    """Every underworld front is a running business (a bug had left them with none)."""
    from .business import configure_enterprise_business
    from .underworld_rebuild import front_archetype
    n = 0
    for e in conn.execute(
            """SELECT e.id,e.name,e.enterprise_kind,l.organization_id oid FROM civilian_enterprises e
               LEFT JOIN underworld_business_links l ON l.enterprise_id=e.id AND l.status='active'
               WHERE e.metadata_json LIKE '%underworld_front%' AND e.status<>'closed' AND e.name NOT LIKE '[STRUCTURAL]%'
               AND NOT EXISTS (SELECT 1 FROM enterprise_business_profiles p WHERE p.enterprise_id=e.id) ORDER BY e.id""").fetchall():
        key = front_archetype(conn, int(e["oid"]), str(e["enterprise_kind"]), str(e["name"])) if e["oid"] is not None else "warehouse"
        configure_enterprise_business(conn, int(e["id"]), key, quality=48, capacity=48, clientele_fit=48, service_reliability=48, regulatory_pressure=25,
                                      metadata={"underworld_front": True, "generated_underworld": True, "backfilled": 114})
        n += 1
    # opening city businesses that run as businesses and belong to nobody
    from .business import _ARCHETYPES
    for e in conn.execute(
            """SELECT e.id,e.enterprise_kind FROM civilian_enterprises e WHERE e.metadata_json LIKE '%procedural_city_business%' AND e.status<>'closed'
               AND NOT EXISTS (SELECT 1 FROM enterprise_business_profiles p WHERE p.enterprise_id=e.id) ORDER BY e.id""").fetchall():
        key = {"shop": "food_shop", "service": "tavern", "workshop": "smithy"}.get(str(e["enterprise_kind"]), "warehouse")
        if key in _ARCHETYPES:
            configure_enterprise_business(conn, int(e["id"]), key, quality=50, capacity=50, clientele_fit=50, service_reliability=50,
                                          metadata={"procedural_city_business": True, "backfilled": 114})
            n += 1
    return n


def give_city_businesses_owners(conn: sqlite3.Connection) -> int:
    """A running opening business has an owner where one plausibly exists: a person of its own place, from the reservoir."""
    from .person_ecology import resolve_background_person
    n = 0
    for e in conn.execute(
            """SELECT e.id,e.location_id,p.archetype_id FROM civilian_enterprises e JOIN enterprise_business_profiles p ON p.enterprise_id=e.id
               WHERE e.metadata_json LIKE '%procedural_city_business%' AND e.owner_actor_id IS NULL AND e.institution_actor_id IS NULL
               AND e.status<>'closed' ORDER BY e.id""").fetchall():
        aid = resolve_background_person(conn, reason="Owner of an opening city business", demand_kind="business_owner", location_id=e["location_id"],
                                        occupation_domains=("merchant", "artisan", "hospitality"), min_age=26, max_age=62, economic_weight=.6, allow_elsewhere=False)
        if aid is None:
            continue
        conn.execute("UPDATE civilian_enterprises SET owner_actor_id=? WHERE id=?", (int(aid), int(e["id"])))
        n += 1
    return n


def disperse_loyalty(conn: sqlite3.Connection) -> dict[str, int]:
    """Crews and named people did not all start at exactly sixty: each starts where its bonds put it, with its own spread, and each
    crew remembers what its rackets give it today."""
    import random as _random
    from .loyalty import bond_strength, drift_target, outfit_context, _spread
    day = _day(conn)
    crews = people = 0
    for o in conn.execute(f"SELECT id FROM underworld_organizations WHERE status IN {ACTIVE_ORG} ORDER BY id").fetchall():
        oid = int(o[0])
        ctx = outfit_context(conn, oid, day)
        from .payroll import crew_earnings
        take = crew_earnings(conn, oid)
        for c in ctx["crews"]:
            rng = _random.Random(int(c["id"]) * 104729 + 114)
            cb = max(0.0, min(1.0, ctx["culture"] + 0.05 + rng.uniform(-.12, .12)))
            tgt = drift_target(cb, 0.0)
            meta = json.loads(c["metadata_json"] or "{}")
            meta["earn_ema"] = round(take.get(int(c["id"]), 0.0), 4)
            conn.execute("UPDATE underworld_crews SET loyalty=?,cohesion=?,metadata_json=? WHERE id=?",
                         (max(0.0, min(100.0, tgt + rng.gauss(0, 5))), max(0.0, min(100.0, float(c["cohesion"]) + rng.gauss(0, 6))), json.dumps(meta, sort_keys=True), int(c["id"])))
            crews += 1
        for p in conn.execute("SELECT * FROM underworld_personnel WHERE organization_id=? AND status='active' AND role_kind<>'boss'", (oid,)).fetchall():
            meta = json.loads(p["metadata_json"] or "{}")
            meta["bond_spread"] = round(_spread(int(p["actor_id"])), 4)
            b = bond_strength(conn, ctx, p, day)
            rng = _random.Random(int(p["actor_id"]) * 15485863 + 114)
            meta["bond"] = round(b, 3)
            meta["loyalty"] = round(max(0.0, min(100.0, drift_target(b, 0.0) + rng.gauss(0, 6))), 2)
            conn.execute("UPDATE underworld_personnel SET metadata_json=? WHERE actor_id=?", (json.dumps(meta, sort_keys=True), int(p["actor_id"])))
            people += 1
    return {"crews": crews, "people": people}
