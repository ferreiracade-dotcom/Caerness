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


if __name__ == "__main__":
    run()
