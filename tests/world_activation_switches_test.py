"""Task 7: Caerness-only activation steps are gated by the world package's system switches."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from world_package_loader_test import _write_pkg  # noqa: E402
from world_seed_import_test import _build, _fresh, _person, _seed  # noqa: E402

# Key set returned by activate_existing_loops for the Caerness opening (all systems on).
CAERNESS_OUT_KEYS = [
    "aggregate_buildings_created",
    "aggregate_enterprises_created",
    "aggregate_market_rows_created",
    "aggregate_trade_profiles",
    "aggregate_trade_reserves_created",
    "aggregate_trade_tracked_corridors",
    "authority_slots",
    "background_heads_resolved",
    "background_partitions_created",
    "background_person_profiles",
    "background_person_profiles_created",
    "background_population_baseline_total",
    "background_population_source_total",
    "background_population_sources",
    "brass_lantern_grand_sales_created",
    "business_profiles_configured",
    "canon_outfits",
    "collective_authority",
    "commercial_contexts_configured",
    "conflict_channels_configured",
    "conflict_geometry_route_rows",
    "cultivation_physiology_initialized",
    "cultivation_profiles_created",
    "cultivation_profiles_refreshed",
    "cultural_objects_created",
    "cultural_profiles_configured",
    "current_ecology_profiles_configured",
    "eastwatch_westgate_frontier",
    "economic_aggregate_enterprises_created",
    "elixir_market_conditions_configured",
    "elixir_supply_profiles_configured",
    "explicit_institution_locations_applied",
    "explicit_teaching_relationships_created",
    "family02_sex_canon_rule",
    "family02_sex_canon_text",
    "family02_sex_given_name",
    "family02_sex_seeded_roll",
    "fighting_rackets",
    "gangs",
    "grand_coven_heirs",
    "grand_coven_power_brokers",
    "grand_coven_succession_states",
    "groundbound_profiles_configured",
    "hollow_profiles",
    "informal_teaching_circles_created",
    "information_channel_location_links_created",
    "information_channels_created",
    "knowledge_assets_created",
    "knowledge_custody_created",
    "law_enforcement_profiles_created",
    "market_conditions_configured",
    "market_goods_configured",
    "merchant_enterprises_reviewed",
    "military_logistics_profiles_configured",
    "military_scale_profiles",
    "missing_scale_settlements",
    "named_incumbents",
    "named_merchant_institution_anchors_created",
    "network_presence",
    "opening_agriculture_fields_created",
    "opening_character_locations_opening_character_locations_resolved",
    "opening_character_locations_opening_characters_missing_after",
    "opening_character_locations_opening_characters_missing_before",
    "opening_character_locations_post_teaching_opening_character_locations_resolved",
    "opening_character_locations_post_teaching_opening_characters_missing_after",
    "opening_character_locations_post_teaching_opening_characters_missing_before",
    "opening_craft_facilities_created",
    "opening_craft_orders_created",
    "opening_craft_recipes_created",
    "opening_family_already_resolved",
    "opening_family_canon_partial",
    "opening_family_canon_record",
    "opening_family_latent_children",
    "opening_family_married",
    "opening_family_never_married",
    "opening_family_spouses_revealed",
    "opening_family_widowed",
    "opening_health_sites_created",
    "opening_institution_locations_post_anchors",
    "opening_institution_locations_resolved",
    "opening_law_jurisdictions_created",
    "opening_law_offices_created",
    "opening_law_rules_created",
    "opening_merchant_observations_created",
    "opening_merchant_staff_configured",
    "opening_physical_stock_bridges_created",
    "opening_political_relations_configured",
    "opening_public_treasuries_created",
    "opening_relationships_colleague",
    "opening_relationships_contact_links",
    "opening_relationships_kin",
    "opening_relationships_kin_extended",
    "opening_relationships_teaching",
    "organization_agency_profiles_created",
    "organization_lifecycle_profiles_created",
    "organization_regimes_created",
    "polities_configured",
    "polity_government_actors_configured",
    "polity_issue_states_configured",
    "polity_lifecycle_profiles",
    "population_age_cohorts",
    "population_dynamics_sources",
    "prizefight_markets",
    "prizefight_markets_created",
    "prizefighter_latent_pools_created",
    "production_sites_created",
    "professional_profile_projections",
    "professional_profiles",
    "recognized_merchant_house_enterprises",
    "religious_institutions_configured",
    "reproduction_profiles_configured",
    "routes01_added",
    "routes01_district_links",
    "scale_population_buckets",
    "settlement_scale_profiles",
    "specialists",
    "spectacle_books",
    "spectacle_books_created",
    "structural_provider_contracts",
    "structural_provider_contracts_created",
    "structural_training_cohorts_created",
    "teacher_capacity_profiles",
    "teacher_offerings",
    "teaching_competence_anchors",
    "territorial_controls_configured",
    "tournament_series",
    "training_enrollments_created",
    "training_programs_created",
    "underworld_fronts_created",
    "underworld_institution_identities_created",
    "underworld_location_updates",
    "underworld_profiles",
    "underworld_shadow_links_created",
    "underworld_working_stock_seeded",
    "unresolved_incumbents",
    "unstaffed",
    "v060_legacy_underworld_retired",
    "v060_underworld_crews",
    "v060_underworld_organizations",
    "v060_underworld_protection_accounts",
    "v060_underworld_rackets",
    "v060_underworld_zones",
    "zones",
]

# Tables that only Caerness-specific steps may fill (religious_traditions is a vocabulary seeded by init_db).
GATED_TABLE_PATTERNS = ("cultivation_%", "elixir_%", "hollow_%", "groundbinding_%", "tournament_%", "spectacle_%",
                        "religious_institutions", "religious_affiliations", "religious_offices", "religious_observance%",
                        "cultural_objects", "cultural_institution%", "aggregate_trade_%", "civilian_enterprises",
                        "underworld_%", "grand_coven_%")
CAERNESS_WORDS = ("Vein-Root", "Salt Road", "Brass Lantern", "Grand Coven", "Fenwick")


def _install_caerness(worlds: Path):
    shutil.copytree(ROOT / "worlds" / "caerness", worlds / "caerness")
    m = json.loads((worlds / "caerness" / "world.json").read_text(encoding="utf-8"))
    for k in ("bible_path", "seed_path", "rulebook_section", "creation_section"):
        if m.get(k):
            m[k] = str((ROOT / "worlds" / "caerness" / m[k]).resolve())
    (worlds / "caerness" / "world.json").write_text(json.dumps(m), encoding="utf-8")


def run():
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        good = hashlib.sha256(b"x").hexdigest()
        names = [("Ann Rossi", 40), ("Bob Rossi", 12), ("Carl Rossi", 70), ("Dina Moretti", 33), ("Ed Murphy", 55)]
        persons = [_person(f"p:{i}", n, a) for i, (n, a) in enumerate(names)]
        worlds = _build(tmp, "sj", _seed(good, persons), pkg_hash=good)
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        _install_caerness(worlds)

        from engine.activation import STEP_SWITCH, activate_existing_loops
        from engine.current_seed import import_current_seed
        from engine.world_package import load_package, set_campaign_package

        pkg = load_package("sj")
        assert all(v is False for v in pkg.systems.values())
        conn = _fresh(tmp, "sj")
        set_campaign_package(conn, "sj")
        import_current_seed(conn, package=pkg)
        out = activate_existing_loops(conn)  # package comes from the campaign
        conn.commit()
        assert set(out["skipped_steps"]) == set(STEP_SWITCH), out["skipped_steps"]
        names_like = " OR ".join("name LIKE '%s'" % p for p in GATED_TABLE_PATTERNS)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND (%s)" % names_like)]
        assert "cultivation_profiles" in tables and "elixir_batches" in tables and "hollow_practice_profiles" in tables
        for t in tables:
            n = conn.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
            assert n == 0, f"{t} has {n} rows in a world with the systems off"
        for table, col in (("market_goods", "name"), ("actors", "name"), ("locations", "name"), ("institution_profiles", "notes")):
            for word in CAERNESS_WORDS:
                n = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {col} LIKE ?', (f"%{word}%",)).fetchone()[0]
                assert n == 0, f"{word} leaked into {table}"
        assert conn.execute("SELECT COUNT(*) FROM actors WHERE name IN ('Ann Rossi','Ed Murphy')").fetchone()[0] == 2
        conn.close()

        # Caerness (all systems on) runs the identical sequence.
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        conn = _fresh(tmp, "caerness")
        import_current_seed(conn)
        out = activate_existing_loops(conn)
        assert "skipped_steps" not in out
        assert sorted(out) == sorted(CAERNESS_OUT_KEYS), set(out) ^ set(CAERNESS_OUT_KEYS)
        conn.close()
    print("world_activation_switches_test passed")


US_1980_MALE = {"0": 0.0140, "1": 0.0011, "5": 0.0006, "10": 0.0006, "15": 0.0016, "20": 0.0019, "30": 0.0021,
                "40": 0.0034, "50": 0.0087, "60": 0.0200, "70": 0.0450, "80": 0.0900, "90": 0.1700, "100": 0.3000}
POOLS = {"male": ["Carmine", "Sal", "Tommy"], "female": ["Rosa", "Gina", "Maureen"],
         "family": ["Sabatini", "Rossi", "Murphy", "Katz"]}


def run_background():
    import numpy as np

    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        good = hashlib.sha256(b"x").hexdigest()
        widower = _person("p:w", "Carmine Sabatini", 60)
        late = _person("p:l", "Rosa Sabatini", 55, life_status="deceased")
        late["death_day"] = -400
        late["death_date"] = None  # filled below once the calendar is known
        persons = [widower, late, _person("p:a", "Gina Rossi", 35), _person("p:b", "Tommy Murphy", 41)]
        worlds = _build(tmp, "sj8", _seed(good, persons), pkg_hash=good)
        # the seed needs the deceased spouse's date in the package's calendar
        from engine import world_calendar
        from engine.world_package import load_package, set_campaign_package
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        _install_caerness(worlds)
        m = json.loads((worlds / "sj8" / "world.json").read_text(encoding="utf-8"))
        m.update({"name_pools": POOLS, "mortality": {"model": "table", "table": US_1980_MALE},
                  "background": {"stage_distribution": False}, "opening_family": {"marry_adults_on_day0": False}})
        (worlds / "sj8" / "world.json").write_text(json.dumps(m), encoding="utf-8")
        pkg = load_package("sj8")
        late["death_date"] = world_calendar.format_date(pkg, late["death_day"])
        late["birth_day"] = late["death_day"] - 55 * 365
        late["birth_date"] = world_calendar.format_date(pkg, late["birth_day"])
        late["age"] = 55
        seed = _seed(good, persons)
        seed["relationships"] = [{"type": "spouse", "from": "p:w", "to": "p:l"}]
        (worlds / "sj8" / "seed.json").write_text(json.dumps(seed), encoding="utf-8")

        from engine.activation import activate_existing_loops
        from engine.current_seed import import_current_seed
        pkg = load_package("sj8")
        assert pkg.name_pools == POOLS and pkg.opening_family["marry_adults_on_day0"] is False
        conn = _fresh(tmp, "sj8")
        set_campaign_package(conn, "sj8")
        import_current_seed(conn, package=pkg)
        activate_existing_loops(conn)
        conn.commit()

        given = set(POOLS["male"]) | set(POOLS["female"])
        rows = conn.execute("SELECT given_name,family_name,current_stage FROM background_person_profiles").fetchall()
        assert len(rows) > 100
        for g, f, stage in rows:
            assert g in given and f in POOLS["family"], (g, f)
            assert stage is None
        for (name,) in conn.execute("""SELECT a.name FROM actors a WHERE a.actor_type='character' AND NOT EXISTS
                                       (SELECT 1 FROM source_identity_map m WHERE m.entity_kind='actor' AND m.entity_id=a.id)"""):
            parts = name.split()
            assert parts[0] in given and parts[1] in POOLS["family"], name
        assert conn.execute("SELECT COUNT(*) FROM cultivation_profiles").fetchone()[0] == 0
        wid = conn.execute("SELECT id FROM actors WHERE name='Carmine Sabatini'").fetchone()[0]
        assert conn.execute("SELECT COUNT(*) FROM household_unions WHERE actor_a_id=? OR actor_b_id=?", (wid, wid)).fetchone()[0] == 0
        late_id = conn.execute("SELECT id FROM actors WHERE name='Rosa Sabatini'").fetchone()[0]
        spouses = {r[0] for r in conn.execute("SELECT actor_b_id FROM kinship_links WHERE kin_kind='spouse' AND actor_a_id=?", (wid,))}
        assert spouses <= {late_id}, spouses  # only the seed's own (deceased) wife: no invented spouse
        # the package table also sets the band mortality rates
        assert abs(conn.execute("SELECT annual_mortality_rate FROM background_population_age_cohorts WHERE age_band='60_plus' LIMIT 1").fetchone()[0] - 0.045) < 1e-9
        conn.close()

    from engine.background_population import annual_mortality
    from engine.health import natural_annual_hazard
    table = {"model": "table", "table": US_1980_MALE}
    days = lambda y: np.array([y * 365.2425])
    male = np.array([0], dtype=np.uint8)
    p30 = float(annual_mortality(days(30), table, male)[0])
    p80 = float(annual_mortality(days(80), table, male)[0])
    assert 0.001 <= p30 <= 0.004 and 0.05 <= p80 <= 0.12, (p30, p80)
    assert p30 < natural_annual_hazard(30, "ordinary")
    series = [float(annual_mortality(days(y), table, male)[0]) for y in range(10, 101)]
    assert all(b >= a for a, b in zip(series, series[1:]))
    # the Caerness default is the premodern step function, unchanged
    assert abs(float(annual_mortality(days(30))[0]) - 0.0018) < 1e-12
    assert abs(float(annual_mortality(days(80))[0]) - 0.085) < 1e-12
    print("world_activation_switches_test (background) passed")


def run_archetypes():
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        worlds = tmp / "worlds"
        worlds.mkdir()
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        _install_caerness(worlds)
        d = _write_pkg(worlds, "pz", data={"archetypes": "archetypes.json"})
        pizzeria = {"name": "Pizzeria", "sector": "food", "enterprise_kind": "shop", "base_revenue": 900.0, "cost_ratio": 0.6,
                    "weights": {"food": 1.0}, "regulation": 0.1, "skill_sensitive": True, "capital_sensitive": False}
        (d / "archetypes.json").write_text(json.dumps({"pizzeria": pizzeria}), encoding="utf-8")
        from engine.authoring import _archetype
        from engine.business import archetypes, seed_business_archetypes
        from engine.world_package import set_campaign_package
        conn = _fresh(tmp, "arch")
        assert _archetype("an inn on the road", None, conn)[0] == "inn"  # Caerness: unbound campaign
        set_campaign_package(conn, "pz")
        assert list(archetypes(conn)) == ["pizzeria"]
        seed_business_archetypes(conn)
        assert [r[0] for r in conn.execute("SELECT archetype_key FROM business_archetypes")] == ["pizzeria"]
        assert _archetype("a pizzeria on Ocean Ave", None, conn) == ("pizzeria", "shop")
        assert _archetype("something odd", None, conn)[0] == "pizzeria"
        conn.close()
    print("world_activation_switches_test (archetypes) passed")


if __name__ == "__main__":
    run()
    run_background()
    run_archetypes()
