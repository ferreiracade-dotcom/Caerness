"""Shared fixture: a protagonist boss with an outfit, a business, a household, a crew and a bystander.

Call inside a connection opened against a copy of the packaged world (never data/caerness.db).
Everyone is an existing person revealed through person_ecology; nobody is inserted by hand.
"""
from __future__ import annotations


def _reveal(conn, loc, reason, **kw):
    from engine.person_ecology import resolve_background_person
    aid = resolve_background_person(conn, reason=reason, location_id=loc, **kw)
    if aid is None:
        raise RuntimeError(f"no one available for {reason}")
    return int(aid)


def make_boss(conn) -> dict:
    from engine import civilian
    from engine.player import set_player
    from engine.underworld import create_underworld_organization
    from engine.underworld_rebuild import create_crew, create_personnel

    loc = int(conn.execute("SELECT id FROM locations WHERE name LIKE 'Toll%Reach' ORDER BY id LIMIT 1").fetchone()[0])
    me = _reveal(conn, loc, "fixture protagonist", min_age=25, max_age=50)
    conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, me))
    set_player(conn, me)
    key = f"fixture-boss-{me}"
    outfit = create_underworld_organization(conn, key, "gang", name="Fixture Outfit", founder_actor_id=me,
                                            primary_location_id=loc, member_count_estimate=12, violence_capacity=30)
    conn.execute("UPDATE underworld_organizations SET treasury=10 WHERE id=?", (outfit,))
    create_personnel(conn, outfit, role_kind="boss", actor_id=me)
    business = civilian.create_enterprise(conn, "Fixture Stall", "shop", owner_actor_id=me, location_id=loc, cash=10)
    household = civilian.create_household(conn, "Fixture House", head_actor_id=me, location_id=loc, liquidity=5)
    crew = create_crew(conn, outfit, "Fixture Crew", size_estimate=6)
    leader = int(conn.execute("SELECT leader_actor_id FROM underworld_crews WHERE id=?", (crew,)).fetchone()[0])
    conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, leader))
    taken = {me, leader}
    bystander = None
    for _ in range(6):
        cand = _reveal(conn, loc, "fixture bystander", min_age=22, max_age=60)
        if cand not in taken and conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=?", (cand,)).fetchone() is None:
            bystander = cand
            break
        taken.add(cand)
    if bystander is None:
        raise RuntimeError("no bystander available")
    conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, bystander))
    conn.commit()
    return {"me": me, "outfit": outfit, "business": business, "household": household, "crew": crew,
            "crew_leader": leader, "bystander": bystander, "location": loc}
