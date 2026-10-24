from __future__ import annotations

import json
import sqlite3
from typing import Any

WORLD_POPULATION = 52_000_000
URBAN_POPULATION = 7_172_000
RURAL_POPULATION = 44_828_000

# Accepted SCALE-01 macro denominators. These are simulation calibration, not a claim that
# every census-like figure exists in setting canon.
POPULATION_BUCKETS: dict[str, tuple[str, int, int]] = {
    "underheaven": ("Underheaven Empire", 21_000_000, 2_896_000),
    "dunmoor": ("Dunmoor", 6_800_000, 938_000),
    "greywood": ("Greywood", 5_300_000, 731_000),
    "sunreach": ("Sunreach Confederacy", 4_500_000, 621_000),
    "windmere": ("Windmere", 4_000_000, 552_000),
    "thornward": ("Thornward", 3_500_000, 483_000),
    "stormhollow": ("Stormhollow", 2_900_000, 400_000),
    "independent_frontier": ("Independent / frontier", 4_000_000, 551_000),
}

OWNER_TO_BUCKET = {
    "Underheaven Empire": "underheaven",
    "Dunmoor": "dunmoor",
    "Greywood": "greywood",
    "Sunreach Confederacy": "sunreach",
    "Windmere": "windmere",
    "Thornward": "thornward",
    "Stormhollow": "stormhollow",
}

# Exact anchors recoverable from the accepted SCALE-01 pass. Other named-settlement numbers
# below are deterministic reconstruction weights used only because the schema-71 artifact was
# not preserved in the accessible handoff. The regional and world denominators remain exact.
FIXED_SETTLEMENT_POPULATIONS = {
    "Crownhold": 520_000,
    "Saltmere": 260_000,
    "Aldergate": 210_000,
    "Cairnholt": 115_000,
    "Toll’s Reach": 110_000,
}

SETTLEMENT_WEIGHTS: dict[str, dict[str, float | None]] = {
    "underheaven": {
        "Crownhold": None, "Highford": 1.35, "Cairnholt": None, "Rivermoor": 1.20,
        "Amber Court": .55, "Toll’s Reach": None, "Redford": .75, "Blackfen": .65,
        "Stonecross": .80, "Mirehold": .70, "Aldergate": None, "Mapleford": .70,
        "Talonkeep": .80, "Eastwatch": .65, "Waymeet": .95, "Oakridge": .65,
        "Britterwatch": .60, "Verenwood": .70, "Greywatch": .70, "Stillwater": .15,
        "Bell Hollow": .18, "Lysmere": .90, "Aldenmoor": .75, "Seven Bridges": 1.05,
        "Everborn Quay": .65,
    },
    "dunmoor": {"Northwatch": 1.00, "Stoneford": .90, "Ravenfield": .95, "Northmarch": 1.25},
    "greywood": {"Eldenfell": 1.10, "Westbrook": .90, "Oakspire": 1.00, "Mistral Keep": 1.05, "Caelshore": .95},
    "windmere": {"Saltmere": None, "Stormwatch": 1.00, "Silvercove": .90},
    "sunreach": {"Goldmarsh": .90, "Highsun": 1.10, "Tidefall": .90, "Sunreach": 1.25, "Brightspine": 1.00, "Southbay": .85},
    "thornward": {"Brackenfell": .85, "Westgate": 1.05, "Harrowden": 1.00, "Alderwall": .90, "Mossford": .80, "Dunbriar": .75, "Stoneheath": .85, "Fenmere": .80},
    "stormhollow": {"Ironspike": 1.10, "Stormhollow": 1.30, "Sableton": .85, "Highcairn": .80, "Ashbarrow": .70, "Greyfen": .70, "Stonewash": .75, "Redcairn": .80},
}


def settlement_tier(population: int) -> str:
    p = int(population)
    if p < 20: return "micro-settlement"
    if p < 100: return "hamlet"
    if p < 500: return "village"
    if p < 1_500: return "large village"
    if p < 5_000: return "small town"
    if p < 12_000: return "town"
    if p < 30_000: return "large town"
    if p < 80_000: return "city"
    if p < 200_000: return "major city"
    if p < 500_000: return "great city"
    return "metropolis"


def institution_scale_band(direct_members: int) -> str:
    n = max(0, int(direct_members))
    if n < 25: return "nascent"
    if n < 100: return "small"
    if n < 500: return "local"
    if n < 1_500: return "established"
    if n < 4_000: return "large"
    if n < 10_000: return "major"
    return "great"


def gang_scale_band(active_members: int) -> str:
    n = max(0, int(active_members))
    if n <= 12: return "crew"
    if n < 30: return "small gang"
    if n < 80: return "established gang"
    if n < 200: return "large gang"
    if n < 500: return "major city gang"
    return "citywide criminal power"


def _weighted_population_map(bucket_key: str) -> dict[str, int]:
    weights = SETTLEMENT_WEIGHTS[bucket_key]
    urban_target = int(POPULATION_BUCKETS[bucket_key][2])
    fixed_total = sum(FIXED_SETTLEMENT_POPULATIONS.get(name, 0) for name in weights)
    variable = [(name, float(weight)) for name, weight in weights.items() if weight is not None]
    remaining = urban_target - fixed_total
    total_weight = sum(weight for _, weight in variable)
    values = {name: int(round((remaining * weight / total_weight) / 1000.0) * 1000) for name, weight in variable}
    residual = remaining - sum(values.values())
    if variable:
        values[max(variable, key=lambda x: x[1])[0]] += residual
    for name in weights:
        if name in FIXED_SETTLEMENT_POPULATIONS:
            values[name] = int(FIXED_SETTLEMENT_POPULATIONS[name])
    return values


def named_settlement_population_map() -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for bucket_key in SETTLEMENT_WEIGHTS:
        for name, population in _weighted_population_map(bucket_key).items():
            out[name] = (bucket_key, population)
    return out


def _package_scale(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """The active world package's own `background.scale` block, or None for Caerness."""
    try:
        from .world_package import package_for
        scale = (package_for(conn).background or {}).get("scale")
    except Exception:
        return None
    return scale if isinstance(scale, dict) and scale.get("buckets") else None


def _activate_package_scale(conn: sqlite3.Connection, scale: dict[str, Any]) -> dict[str, int]:
    """A world package's population scale: its own buckets and named settlements, not Caerness's 52m."""
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    buckets: dict[str, dict[str, Any]] = scale["buckets"]
    world_total = sum(int(b["population"]) for b in buckets.values())
    authority = str(scale.get("authority") or "PACKAGE_SCALE")
    for key, b in buckets.items():
        population, urban = int(b["population"]), int(b.get("urban", 0))
        conn.execute(
            """INSERT INTO population_scale_buckets(bucket_key,label,population_estimate,urban_population,rural_population,calibration_status,metadata_json)
               VALUES (?,?,?,?,?,'CAMPAIGN_CALIBRATION',?)
               ON CONFLICT(bucket_key) DO UPDATE SET label=excluded.label,population_estimate=excluded.population_estimate,
                 urban_population=excluded.urban_population,rural_population=excluded.rural_population,metadata_json=excluded.metadata_json""",
            (key, str(b.get("label") or key), population, urban, population - urban, json.dumps({
                "authority": authority, "world_population_denominator": world_total, "not_runtime_quota": True,
                "source": b.get("source"),
            }, sort_keys=True)),
        )
    profiles = 0
    missing: list[str] = []
    for name, s in (scale.get("settlements") or {}).items():
        row = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
        if not row:
            missing.append(name)
            continue
        population = int(s["population"])
        conn.execute(
            """INSERT INTO settlement_scale_profiles(location_id,bucket_key,population_estimate,settlement_tier,named_urban,calibration_status,updated_day,metadata_json)
               VALUES (?,?,?,?,1,'CAMPAIGN_CALIBRATION',?,?)
               ON CONFLICT(location_id) DO UPDATE SET bucket_key=excluded.bucket_key,population_estimate=excluded.population_estimate,
                 settlement_tier=excluded.settlement_tier,updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
            (int(row[0]), str(s["bucket"]), population, settlement_tier(population), day, json.dumps({
                "authority": authority, "source": s.get("source"),
            }, sort_keys=True)),
        )
        profiles += 1
    named_urban = int(conn.execute("SELECT COALESCE(SUM(population_estimate),0) FROM settlement_scale_profiles").fetchone()[0])
    urban_total = sum(int(b.get("urban", 0)) for b in buckets.values())
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('scale01_named_urban_population',?)", (str(named_urban),))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('scale01_structural_urban_population',?)", (str(urban_total - named_urban),))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('scale01_missing_named_settlements',?)", (json.dumps(missing),))
    military = 0
    if scale.get("military", True):
        for key, b in buckets.items():
            population = int(b["population"])
            conn.execute(
                """INSERT INTO military_scale_profiles(bucket_key,standing_professional,local_garrison_establishment,trained_reserve,
                       sustainable_field_capacity,emergency_mobilization_ceiling,military_age_pool,metadata_json)
                   VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bucket_key) DO NOTHING""",
                (key, int(round(population * .003)), int(round(population * .002)), int(round(population * .020)),
                 int(round(population * .015)), int(round(population * .050)), int(round(population * .200)),
                 json.dumps({"authority": authority}, sort_keys=True)),
            )
            military += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('scale01_activation_version','1')")
    return {"scale_population_buckets": len(buckets), "settlement_scale_profiles": profiles,
            "missing_scale_settlements": len(missing), "military_scale_profiles": military}


def activate_scale_authority(conn: sqlite3.Connection) -> dict[str, int]:
    pkg = _package_scale(conn)
    if pkg is not None:
        return _activate_package_scale(conn, pkg)
    day =int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    for key, (label, population, urban) in POPULATION_BUCKETS.items():
        conn.execute(
            """INSERT INTO population_scale_buckets(bucket_key,label,population_estimate,urban_population,rural_population,calibration_status,metadata_json)
               VALUES (?,?,?,?,?,'CAMPAIGN_CALIBRATION',?)
               ON CONFLICT(bucket_key) DO UPDATE SET label=excluded.label,population_estimate=excluded.population_estimate,
                 urban_population=excluded.urban_population,rural_population=excluded.rural_population,metadata_json=excluded.metadata_json""",
            (key, label, population, urban, population - urban, json.dumps({
                "authority": "SCALE01_CAMPAIGN_CALIBRATION",
                "world_population_denominator": WORLD_POPULATION,
                "not_runtime_quota": True,
            }, sort_keys=True)),
        )

    profiles = 0
    missing: list[str] = []
    for name, (bucket_key, population) in named_settlement_population_map().items():
        row = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
        if not row:
            missing.append(name)
            continue
        anchor = name in FIXED_SETTLEMENT_POPULATIONS
        conn.execute(
            """INSERT INTO settlement_scale_profiles(location_id,bucket_key,population_estimate,settlement_tier,named_urban,calibration_status,updated_day,metadata_json)
               VALUES (?,?,?,?,1,'CAMPAIGN_CALIBRATION',?,?)
               ON CONFLICT(location_id) DO UPDATE SET bucket_key=excluded.bucket_key,population_estimate=excluded.population_estimate,
                 settlement_tier=excluded.settlement_tier,updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
            (int(row[0]), bucket_key, population, settlement_tier(population), day, json.dumps({
                "authority": "SCALE01_CAMPAIGN_CALIBRATION",
                "exact_recovered_anchor": anchor,
                "reconstruction_note": None if anchor else "deterministic allocation preserving accepted regional/world denominators",
            }, sort_keys=True)),
        )
        profiles += 1

    # The independent/frontier urban share is intentionally structural rather than assigned to
    # named settlements whose geography is not crystallized. This keeps the 7.172m urban total
    # without inventing frontier city identities.
    named_urban = int(conn.execute("SELECT COALESCE(SUM(population_estimate),0) FROM settlement_scale_profiles").fetchone()[0])
    structural_urban = URBAN_POPULATION - named_urban
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('scale01_named_urban_population',?)", (str(named_urban),))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('scale01_structural_urban_population',?)", (str(structural_urban),))
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('scale01_missing_named_settlements',?)", (json.dumps(missing),))

    # Military quantities are denominators for simulation scale, not standing canon figures.
    military = 0
    for key, (_, population, _) in POPULATION_BUCKETS.items():
        standing = int(round(population * .003))
        garrison = int(round(population * .002))
        reserve = int(round(population * .020))
        sustainable = int(round(population * .015))
        emergency = int(round(population * .050))
        military_age = int(round(population * .200))
        conn.execute(
            """INSERT INTO military_scale_profiles(bucket_key,standing_professional,local_garrison_establishment,trained_reserve,
                   sustainable_field_capacity,emergency_mobilization_ceiling,military_age_pool,metadata_json)
               VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(bucket_key) DO UPDATE SET
                   standing_professional=excluded.standing_professional,local_garrison_establishment=excluded.local_garrison_establishment,
                   trained_reserve=excluded.trained_reserve,sustainable_field_capacity=excluded.sustainable_field_capacity,
                   emergency_mobilization_ceiling=excluded.emergency_mobilization_ceiling,military_age_pool=excluded.military_age_pool,
                   metadata_json=excluded.metadata_json""",
            (key, standing, garrison, reserve, sustainable, emergency, military_age,
             json.dumps({"authority":"SCALE01_CAMPAIGN_CALIBRATION","rates_are_denominator_calibration_not_canon_force_counts":True}, sort_keys=True)),
        )
        military += 1

    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('scale01_activation_version','1')")
    return {"scale_population_buckets": len(POPULATION_BUCKETS), "settlement_scale_profiles": profiles,
            "missing_scale_settlements": len(missing), "military_scale_profiles": military}


def scale_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    # SCALE-01 values remain the opening ecological calibration. POPLIFE-01 may later diverge
    # causally; expose both rather than silently overwriting the accepted opening anchor.
    total = int(conn.execute("SELECT COALESCE(SUM(population_estimate),0) FROM population_scale_buckets").fetchone()[0])
    urban = int(conn.execute("SELECT COALESCE(SUM(urban_population),0) FROM population_scale_buckets").fetchone()[0])
    named = int(conn.execute("SELECT COALESCE(SUM(population_estimate),0) FROM settlement_scale_profiles").fetchone()[0])
    live = conn.execute("SELECT COALESCE(SUM(population_estimate),0),COALESCE(SUM(CASE WHEN urban=1 THEN population_estimate ELSE 0 END),0) FROM background_population_sources").fetchone()
    live_total = int(live[0]) if live and float(live[0] or 0)>0 else total
    live_urban = int(live[1]) if live and float(live[0] or 0)>0 else urban
    return {
        "world_population": total,
        "urban_population": urban,
        "rural_population": total - urban,
        "current_world_population": live_total,
        "current_urban_population": live_urban,
        "current_rural_population": live_total-live_urban,
        "named_settlement_profiles": int(conn.execute("SELECT COUNT(*) FROM settlement_scale_profiles").fetchone()[0]),
        "named_urban_population": named,
        "structural_urban_population": urban - named,
    }
