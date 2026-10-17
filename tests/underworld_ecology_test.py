"""Gap 4a: canon-shaped underworld in every settlement (docs/superpowers/plans/2026-10-17-underworld-everywhere.md, Task 3)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def bootstrap(tmp: str):
    from engine.db import reset_db, init_db, connect
    from engine.current_seed import import_current_seed
    from engine.activation import activate_existing_loops
    os.environ["CAERNESS_DB_PATH"] = str(Path(tmp) / "uw_ecology.db")
    os.environ["CAERNESS_TEST_MODE"] = "1"
    reset_db(force=True, backup=False)
    init_db()
    c = connect()
    import_current_seed(c)
    activate_existing_loops(c)
    c.commit()
    return c


def run():
    from engine.underworld_ecology import seed_all_settlements, seed_settlement_underworld
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = bootstrap(tmp)

        def loc(name):
            return int(c.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()[0])

        def orgs(name, typ=None):
            q = "SELECT * FROM underworld_organizations WHERE primary_location_id=? AND status IN ('active','strained','fragmented')"
            a = [loc(name)]
            if typ:
                q += " AND organization_type=?"; a.append(typ)
            return c.execute(q, a).fetchall()

        def zones(name):
            return [r["name"] for r in c.execute("SELECT name FROM underworld_zones WHERE city_location_id=? AND status='active'", (loc(name),))]

        def actor(name):
            return c.execute("SELECT * FROM actors WHERE actor_type='institution' AND name=?", (name,)).fetchone()

        def presence(inst, place):
            r = c.execute("SELECT strength FROM underworld_network_presence p JOIN actors a ON a.id=p.institution_actor_id "
                          "WHERE a.name=? AND p.location_id=?", (inst, loc(place))).fetchone()
            return r[0] if r else None

        def canon_org(name):
            return c.execute("SELECT o.* FROM underworld_organizations o JOIN actors a ON a.id=o.institution_actor_id WHERE a.name=?", (name,)).fetchone()

        toll = "Toll’s Reach"
        # Toll's Reach: broad overlap, fighting, quays.
        gh = canon_org("Greyhook Wharf Company")
        assert gh and gh["status"] == "active" and actor("Greyhook Wharf Company")["status"] == "active"
        assert int(gh["primary_location_id"]) == loc(toll) and gh["current_leader_actor_id"] is None
        assert c.execute("SELECT COUNT(*) FROM underworld_business_links WHERE organization_id=? AND status='active'", (gh["id"],)).fetchone()[0] >= 1
        assert not c.execute("SELECT 1 FROM underworld_zone_claims WHERE organization_id=? AND status='active'", (gh["id"],)).fetchone()
        assert presence("Cormorants", toll) and presence("Red Board", toll)
        mk = {r["market_key"]: r for r in c.execute("SELECT * FROM prizefight_markets WHERE status='active'")}
        ry = mk["toll-red-yard"]
        assert ry["location_id"] == loc("The Red Yard") and ry["legality"] == "licensed" and ry["coercion_profile"] == "voluntary"
        assert mk["toll-dockside-rings"]["legality"] == "tolerated"
        ww = mk["toll-red-board-warehouse-ring"]
        assert ww["legality"] == "criminal" and ww["coercion_profile"] == "coercive" and ww["location_id"] == loc(toll)
        assert {"River Quays", "Sea Quays"} <= set(zones(toll)), zones(toll)
        assert len(orgs(toll, "gang")) >= 2, len(orgs(toll, "gang"))
        spec_n = len([o for o in orgs(toll) if o["organization_type"] in ("criminal_enterprise", "network")]) - 1  # minus Greyhook
        assert spec_n >= 4, spec_n

        # Aldergate: money and paperwork, Tallow holds fronts not ground.
        tl = canon_org("Tallow Family")
        assert tl and tl["status"] == "active" and tl["organization_type"] == "criminal_dynasty"
        assert not c.execute("SELECT 1 FROM underworld_zone_claims WHERE organization_id=? AND status='active'", (tl["id"],)).fetchone()
        assert len(orgs("Aldergate", "gang")) <= 3
        kinds = {r[0] for r in c.execute("SELECT racket_kind FROM underworld_racket_sites r JOIN underworld_organizations o ON o.id=r.organization_id WHERE o.primary_location_id=?", (loc("Aldergate"),))}
        assert "high-risk debt" in kinds and kinds & {"cargo fraud", "invoice fraud", "seal manipulation"} and kinds & {"warehouse theft", "stolen goods", "seal manipulation"}, kinds
        assert not c.execute("SELECT 1 FROM underworld_organizations WHERE metadata_json LIKE '%v060_clean_rebuild%'").fetchone()

        # Saltmere, Cairnholt.
        sw = canon_org("Saltwake Combine")
        assert sw and sw["status"] == "active" and int(sw["primary_location_id"]) == loc("Saltmere")
        assert len(orgs("Cairnholt", "gang")) <= 1
        assert presence("Painted Veil", "Cairnholt") == "strong" and "Lantern District" in zones("Cairnholt")

        # A settlement canon is silent on (Mapleford, about 88,000) is plausible and small; a tiny place has no zones.
        assert 3 <= len(zones("Mapleford")) <= 5 and 2 <= len(orgs("Mapleford")) <= 8, (zones("Mapleford"), len(orgs("Mapleford")))
        c.execute("INSERT INTO locations(name,kind,political_owner) VALUES ('Tiny Ford','settlement','Underheaven Empire')")
        tid = int(c.execute("SELECT id FROM locations WHERE name='Tiny Ford'").fetchone()[0])
        c.execute("INSERT INTO background_population_sources(source_key,source_kind,bucket_key,location_id,population_estimate,urban,calibration_status,baseline_population_estimate) "
                  "VALUES ('settlement:tiny','settlement','underheaven',?,9000,1,'TEST',9000)", (tid,))
        seed_settlement_underworld(c, tid)
        assert not c.execute("SELECT 1 FROM underworld_zones WHERE city_location_id=?", (tid,)).fetchone()

        # Networks are not parked at Waymeet; the Reckoning and Mallow stay unplaced.
        for n in ("Painted Veil", "The Hush", "The Reckoning", "Cormorants", "Red Board"):
            assert actor(n)["current_location_id"] is None, n
        assert not c.execute("SELECT 1 FROM underworld_network_presence p JOIN actors a ON a.id=p.institution_actor_id WHERE a.name IN ('The Reckoning','Mallow Coven')").fetchone()
        assert presence("The Hush", "Crownhold") and presence("The Hush", "Waymeet")

        # Provenance, unique names, canon is never labelled procedural and vice versa.
        names = [r[0] for r in c.execute("SELECT name FROM underworld_organizations")]
        assert len(names) == len(set(names)), "outfit names must be unique"
        for r in c.execute("SELECT name,metadata_json FROM underworld_organizations"):
            m = json.loads(r["metadata_json"])
            assert m.get("source") in ("world_bible", "procedural"), (r["name"], m)
            assert (m["source"] == "world_bible") == (r["name"] in ("Tallow Family", "Greyhook Wharf Company", "Saltwake Combine")), r["name"]
        for r in c.execute("SELECT zone_key,metadata_json FROM underworld_zones WHERE zone_key NOT LIKE '20:%'"):
            assert json.loads(r["metadata_json"]).get("source") in ("world_bible", "procedural"), r["zone_key"]

        # Every boss is a real, located, living person who was already in the population.
        for r in c.execute("""SELECT p.actor_id,a.current_location_id,o.primary_location_id,a.status FROM underworld_personnel p
                              JOIN underworld_organizations o ON o.id=p.organization_id JOIN actors a ON a.id=p.actor_id WHERE p.role_kind='boss'"""):
            assert r["status"] == "active" and int(r["current_location_id"]) == int(r["primary_location_id"])

        # Idempotent; population sources unchanged.
        def snap():
            return [c.execute(q).fetchone()[0] for q in (
                "SELECT COUNT(*) FROM underworld_organizations", "SELECT COUNT(*) FROM underworld_zones", "SELECT COUNT(*) FROM underworld_personnel",
                "SELECT COUNT(*) FROM underworld_racket_sites", "SELECT COUNT(*) FROM underworld_network_presence", "SELECT COUNT(*) FROM prizefight_markets",
                "SELECT COUNT(*) FROM actors", "SELECT SUM(population_estimate) FROM background_population_sources")]
        before = snap()
        seed_all_settlements(c)
        assert snap() == before, (before, snap())
        c.commit()

        # 60 days run clean, and outfits outside Aldergate keep records.
        from engine.simulation import advance_connection
        advance_connection(c, 60)
        c.commit()
        far = c.execute("""SELECT COUNT(DISTINCT o.primary_location_id) FROM underworld_finance_transactions f JOIN underworld_organizations o ON o.id=f.organization_id
                           WHERE o.primary_location_id<>?""", (loc("Aldergate"),)).fetchone()[0]
        assert far >= 1, far
        # The monthly process is not city-bound: finance rows exist for outfits in at least three different settlements.
        spread = c.execute("SELECT COUNT(DISTINCT o.primary_location_id) FROM underworld_finance_transactions f JOIN underworld_organizations o ON o.id=f.organization_id").fetchone()[0]
        assert spread >= 3, spread
        c.close()
    print("underworld_ecology_test passed")


if __name__ == "__main__":
    run()
