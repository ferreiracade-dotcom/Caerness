"""Schema 110: a campaign whose underworld was the Aldergate-only procedural city is rebuilt from canon
(docs/superpowers/plans/2026-10-17-underworld-everywhere.md, Task 5)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LIVE = "('active','strained','fragmented')"


def old_campaign(tmp: str):
    """The world as schema 109 left it: procedural Aldergate gangs only, plus a protagonist outfit, an authored gang and connector notes."""
    from engine.db import reset_db, init_db, connect
    from engine.current_seed import import_current_seed
    from engine import underworld_ecology
    from engine.activation import activate_existing_loops
    from engine.underworld_rebuild import seed_city_underworld, create_personnel
    from engine.underworld import create_underworld_organization
    from engine.player import set_player
    from engine.authoring import author
    from connector import store

    os.environ["CAERNESS_DB_PATH"] = str(Path(tmp) / "schema110.db")
    os.environ["CAERNESS_TEST_MODE"] = "1"
    reset_db(force=True, backup=False)
    init_db()
    c = connect()
    import_current_seed(c)
    real = underworld_ecology.seed_all_settlements
    underworld_ecology.seed_all_settlements = lambda conn: {}  # the old activation seeded nothing but Aldergate
    try:
        activate_existing_loops(c)
    finally:
        underworld_ecology.seed_all_settlements = real
    ald = int(c.execute("SELECT id FROM locations WHERE name='Aldergate'").fetchone()[0])
    toll = int(c.execute("SELECT id FROM locations WHERE name='Toll’s Reach'").fetchone()[0])
    seed_city_underworld(c, city_location_id=ald, force=True)
    c.execute("UPDATE underworld_organizations SET name='Iron Rooks' WHERE id=(SELECT MIN(id) FROM underworld_organizations WHERE organization_type='gang' AND primary_location_id=?)", (ald,))

    taken: set[int] = set()

    def local(place):
        """A named character who lives at the place (moved there if the seed has nobody)."""
        row = c.execute("""SELECT a.id FROM actors a WHERE a.actor_type='character' AND a.status='active' AND a.current_location_id=? AND a.home_location_id=?
                           AND NOT EXISTS (SELECT 1 FROM underworld_personnel p WHERE p.actor_id=a.id AND p.status='active') ORDER BY a.id""", (place, place)).fetchall()
        row = [r[0] for r in row if r[0] not in taken]
        if not row:
            row = [r[0] for r in c.execute("""SELECT a.id FROM actors a WHERE a.actor_type='character' AND a.status='active' AND a.current_location_id IS NOT NULL
                                              AND NOT EXISTS (SELECT 1 FROM underworld_personnel p WHERE p.actor_id=a.id AND p.status='active') ORDER BY a.id""") if r[0] not in taken]
            c.execute("UPDATE actors SET home_location_id=?,current_location_id=? WHERE id=?", (place, place, row[0]))
        taken.add(row[0])
        return row[0]
    me = local(toll)
    set_player(c, me)
    mine = create_underworld_organization(c, "mine:1", "gang", name="Hands of the Reach", founder_actor_id=me, primary_location_id=toll,
                                          member_count_estimate=6, metadata={"made_in_play": True})
    create_personnel(c, mine, role_kind="boss", actor_id=me)
    g = author(c, me, "organisation", {"name": "The Cart Lads", "type": "gang", "location_id": ald, "leader_actor_id": local(ald)}, "s110a")
    store.ensure_connector_schema(c)
    c.execute("INSERT INTO gm_notes(subject_kind,text,world_day,call_id) VALUES ('general','The Iron Rooks squeeze the carters.',0,'n1')")
    c.execute("INSERT INTO gm_notes(subject_kind,text,world_day,call_id) VALUES ('general','The ferry runs late.',0,'n2')")
    c.execute("INSERT INTO campaign_recaps(world_day,text,call_id) VALUES (0,'He paid off the Iron Rooks.','r1')")
    c.execute("INSERT INTO standing_rules(world_day,text,call_id) VALUES (0,'Never cross the Iron Rooks.','s1')")
    rewind(c)  # the bootstrap ran on the current schema; make it a schema-109 save again
    return c, ald, toll, me, mine, g["outfit_id"]


def snap(c):
    return [c.execute(q).fetchone()[0] for q in (
        "SELECT COUNT(*) FROM underworld_organizations", "SELECT COUNT(*) FROM underworld_zones", "SELECT COUNT(*) FROM underworld_personnel",
        "SELECT COUNT(*) FROM underworld_racket_sites", "SELECT COUNT(*) FROM underworld_network_presence", "SELECT COUNT(*) FROM prizefight_markets",
        "SELECT COUNT(*) FROM actors", "SELECT COUNT(*) FROM error_reports")]


def rewind(c):
    c.execute("DELETE FROM schema_migrations WHERE version>=110")
    c.execute("UPDATE engine_meta SET value='109' WHERE key='schema_version'")
    c.commit()


def run():
    from engine.db import connect, init_db
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c, ald, toll, me, mine, authored = old_campaign(tmp)
        old = c.execute(f"SELECT id,name,metadata_json FROM underworld_organizations WHERE status IN {LIVE}").fetchall()
        procedural = [r for r in old if "v060_clean_rebuild" in r["metadata_json"]]
        assert len(procedural) >= 7 and "Iron Rooks" in [r["name"] for r in procedural]
        ids = ",".join(str(r["id"]) for r in procedural)
        people = {r[0]: r[1] for r in c.execute(f"SELECT DISTINCT p.actor_id,a.current_location_id FROM underworld_personnel p JOIN actors a ON a.id=p.actor_id WHERE p.organization_id IN ({ids})")}
        assert people
        # Review 2: rows that tie other tables to the invented outfits (interests, permissions, incidents, relations).
        a_ids = [r["id"] for r in procedural]
        top, other = a_ids[0], a_ids[1]
        racket = c.execute("SELECT id FROM underworld_racket_sites WHERE organization_id=? LIMIT 1", (top,)).fetchone()
        zone = c.execute("SELECT id FROM underworld_zones WHERE city_location_id=? LIMIT 1", (ald,)).fetchone()[0]
        c.execute("INSERT INTO economic_interests(holder_organization_id,target_racket_id,interest_kind,share_fraction,started_day) VALUES (?,?, 'operator',1.0,0)", (top, racket[0]))
        c.execute("INSERT INTO economic_interests(holder_organization_id,target_racket_id,interest_kind,share_fraction,started_day) VALUES (?,?, 'revenue_share',.2,0)",
                  (mine, racket[0]))  # a survivor's share in a racket that disappears
        c.execute("INSERT INTO underworld_operating_permissions(zone_id,controller_organization_id,guest_organization_id,activity_kind,tribute_rate,started_day) VALUES (?,?,?,'gaming',.1,0)", (zone, top, mine))
        c.execute("INSERT INTO underworld_operating_permissions(zone_id,controller_organization_id,guest_organization_id,activity_kind,tribute_rate,started_day) VALUES (?,?,?,'gaming',.1,0)", (zone, mine, other))
        c.execute("INSERT INTO underworld_incidents(day,zone_id,source_organization_id,target_organization_id,incident_kind) VALUES (0,?,?,?,'poach')", (zone, top, mine))
        for a_, b_, kind_, host in ((mine, top, "war", 95), (mine, authored, "rival", 70)):
            x_, y_ = sorted((a_, b_))
            c.execute("INSERT OR REPLACE INTO underworld_relations(organization_a_id,organization_b_id,relation_kind,hostility) VALUES (?,?,?,?)", (x_, y_, kind_, host))
        c.commit()
        keep = {oid: tuple(c.execute("SELECT status,member_count_estimate,treasury,current_leader_actor_id,metadata_json FROM underworld_organizations WHERE id=?", (oid,)).fetchone()) for oid in (mine, authored)}
        keep_claims = c.execute("SELECT zone_id,status FROM underworld_zone_claims WHERE organization_id=? ORDER BY id", (authored,)).fetchall()
        keep_claims = [tuple(r) for r in keep_claims]
        c.close()

        init_db()
        c = connect()
        assert c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] >= 110
        assert int(c.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()[0]) >= 110

        # The invented city is gone; its people are not.
        for r in procedural:
            o = c.execute("SELECT status,metadata_json FROM underworld_organizations WHERE id=?", (r["id"],)).fetchone()
            assert o["status"] == "destroyed" and json.loads(o["metadata_json"])["superseded_by"] == "schema110_canon_underworld", r["name"]
            assert not c.execute("SELECT 1 FROM underworld_zone_claims WHERE organization_id=? AND status='active'", (r["id"],)).fetchone()
            assert not c.execute("SELECT 1 FROM underworld_personnel WHERE organization_id=? AND status='active'", (r["id"],)).fetchone()
            assert not c.execute("SELECT 1 FROM underworld_crews WHERE organization_id=? AND status='active'", (r["id"],)).fetchone()
            assert not c.execute("SELECT 1 FROM underworld_racket_sites WHERE organization_id=? AND status='active'", (r["id"],)).fetchone()
            assert not c.execute("SELECT 1 FROM underworld_protection_accounts WHERE protector_organization_id=? AND status='active'", (r["id"],)).fetchone()
            assert not c.execute("SELECT 1 FROM underworld_business_links WHERE organization_id=? AND status='active'", (r["id"],)).fetchone()
        for aid, where in people.items():
            a = c.execute("SELECT status,current_location_id,subtype FROM actors WHERE id=?", (aid,)).fetchone()
            assert a["status"] == "active" and a["current_location_id"] == where and not str(a["subtype"]).startswith("underworld_"), (aid, tuple(a))
            assert not c.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=? AND status='active' AND organization_id IN (%s)" % ids, (aid,)).fetchone()
        # Former members read as ordinary people: a plain trade, no outfit, no 'criminal'.
        from connector.views import lookup, _who
        dissolved_names = [r["name"] for r in procedural]
        for aid in people:
            row = c.execute("SELECT * FROM actors WHERE id=?", (aid,)).fetchone()
            assert row["subtype"].startswith("resolved_") and row["subtype"] != "resolved_criminal", row["subtype"]
            blob = json.dumps(lookup(c, row["name"])) + _who(c, row)
            assert "criminal" not in blob and "resolved" not in blob, blob
            assert not any(n in blob for n in dissolved_names), blob
        assert not c.execute("SELECT 1 FROM underworld_zones WHERE city_location_id=? AND status='active' AND metadata_json LIKE '%not_world_bible_canon%' "
                             "AND id NOT IN (SELECT zone_id FROM underworld_zone_claims WHERE status='active')", (ald,)).fetchone()

        # Review 2: nothing active still points at a destroyed outfit.
        q = ",".join(str(i) for i in a_ids)
        assert not c.execute(f"SELECT 1 FROM economic_interests WHERE status='active' AND (holder_organization_id IN ({q}) OR target_racket_id IN "
                             f"(SELECT id FROM underworld_racket_sites WHERE organization_id IN ({q})))").fetchone(), "active economic interests"
        assert not c.execute(f"SELECT 1 FROM underworld_operating_permissions WHERE status='active' AND (controller_organization_id IN ({q}) OR guest_organization_id IN ({q}))").fetchone(), "active permissions"
        assert not c.execute(f"SELECT 1 FROM underworld_incidents WHERE status='open' AND (source_organization_id IN ({q}) OR target_organization_id IN ({q}))").fetchone(), "open incidents"
        assert not c.execute(f"SELECT 1 FROM underworld_relations WHERE organization_a_id IN ({q}) OR organization_b_id IN ({q})").fetchone(), "relations"
        # The survivor's top rival was dissolved; its next hit goes to the live one.
        import random
        from engine.underworld_rebuild import _targeted_hit
        assert _targeted_hit(c, mine, random.Random(3)) is True
        tgt = c.execute("SELECT target_organization_id FROM underworld_operations WHERE organization_id=? AND operation_kind='targeted_hit' ORDER BY id DESC LIMIT 1", (mine,)).fetchone()
        assert tgt and tgt[0] == authored, tgt
        c.rollback()

        # Review 5: no seeded ward is left abandoned by a key collision with a dissolved one, and no claim sits on an abandoned ward.
        assert c.execute("SELECT COUNT(*) FROM underworld_zones WHERE status='abandoned' AND metadata_json LIKE '%procedural_calibration_from_canon_character%'").fetchone()[0] == 0
        assert not c.execute("SELECT 1 FROM underworld_zone_claims k JOIN underworld_zones z ON z.id=k.zone_id WHERE z.status='abandoned' AND k.status='active'").fetchone()

        # The protagonist's outfit and the authored gang are untouched.
        for oid, before in keep.items():
            assert tuple(c.execute("SELECT status,member_count_estimate,treasury,current_leader_actor_id,metadata_json FROM underworld_organizations WHERE id=?", (oid,)).fetchone()) == before
        assert c.execute("SELECT status FROM underworld_personnel WHERE organization_id=? AND actor_id=?", (mine, me)).fetchone()[0] == "active"
        assert [tuple(r) for r in c.execute("SELECT zone_id,status FROM underworld_zone_claims WHERE organization_id=? ORDER BY id", (authored,))] == keep_claims

        # Canon version everywhere.
        for n in ("Tallow Family", "Greyhook Wharf Company", "Saltwake Combine"):
            assert c.execute("SELECT o.status FROM underworld_organizations o JOIN actors a ON a.id=o.institution_actor_id WHERE a.name=?", (n,)).fetchone()[0] == "active", n
        assert c.execute("SELECT COUNT(*) FROM prizefight_markets WHERE market_key LIKE 'toll-%'").fetchone()[0] >= 3
        assert c.execute(f"SELECT COUNT(DISTINCT primary_location_id) FROM underworld_organizations WHERE status IN {LIVE}").fetchone()[0] >= 20

        # Notes that name a dissolved gang are reported; others are not.
        errs = [r[0] for r in c.execute("SELECT text FROM error_reports")]
        assert len(errs) == 3 and all("Iron Rooks" in e and "schema 110" in e for e in errs), errs
        rep = json.loads(c.execute("SELECT value FROM engine_meta WHERE key='schema110_report'").fetchone()[0])
        assert "Iron Rooks" in rep["dissolved"] and rep["reported_notes"] == 3, rep

        # Idempotent.
        before = snap(c)
        rewind(c)
        c.close()
        init_db()
        c = connect()
        assert snap(c) == before, (before, snap(c))
        assert c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] >= 110
        c.close()
    print("schema110_underworld_test passed")


if __name__ == "__main__":
    run()
