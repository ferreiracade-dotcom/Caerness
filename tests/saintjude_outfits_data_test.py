"""Schema 116, the Saint Jude outfit and law package data, and the `outfits` switch."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NEW_FIGURES = (
    "brigades_elders brigades_middle brigades_young brigades_gift_share combine_bankers combine_controllers horsemen_officers "
    "horsemen_members horsemen_prospects horsemen_dues_share russians_men_minus_senior bolita_bankers bolita_runners executive_share "
    "homicide_honest_share bail_days case_review_days case_close_days pad_captain_officers pad_sergeant_officers pad_patrolman_officers "
    "pad_captain_weekly_usd pad_sergeant_weekly_usd pad_patrolman_weekly_usd pad_envelope_mean_check agency_capacity_low "
    "agency_capacity_mid agency_capacity_high agency_integrity_padded agency_integrity_clean evidence_threshold_homicide "
    "evidence_threshold_assault evidence_threshold_robbery evidence_threshold_racket"
).split()
TABLES = {"outfit_ranks", "outfit_crews", "outfit_holdings", "outfit_lines", "outfit_money", "outfit_agenda",
          "outfit_incidents", "pad_envelopes", "crime_reports", "custody"}
FIGURE_KEYS = ("figure", "made_men_figure", "associates_figure", "capacity", "integrity", "evidence_threshold",
               "honest_homicide_figure", "executive_share_of_boss_receipts")


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def referenced_figure_keys(*docs):
    found: set[str] = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in FIGURE_KEYS and isinstance(v, str):
                    found.add(v)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for d in docs:
        walk(d)
    return found


def grep_engine(words):
    hits = []
    for folder in ("engine", "connector"):
        for p in (ROOT / folder).rglob("*.py"):
            text = p.read_text(encoding="utf-8", errors="replace")
            for w in words:
                if w in text:
                    hits.append((str(p.relative_to(ROOT)), w))
    return hits


def run():
    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    from tests.sj_fixture import build_saintjude, connect
    from engine import design
    from engine.world_package import load_package, outfit_rules, law_rules, system_enabled
    from engine.db import SCHEMA_VERSION

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = build_saintjude(Path(tmp))
        sj = connect(db)
        os.environ["CAERNESS_DB_PATH"] = str(db)

        # schema 116
        assert SCHEMA_VERSION == 116
        assert TABLES <= tables(sj), TABLES - tables(sj)
        assert "quiet_routine" in columns(sj, "simulation_profiles")
        idx = {r[0] for r in sj.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"idx_outfit_ranks_outfit_rank", "idx_outfit_ranks_superior", "idx_outfit_lines_holder",
                "idx_outfit_agenda_actor", "idx_crime_reports_status"} <= idx
        assert sj.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 116

        # the switch, on for Saint Jude only
        assert system_enabled(sj, "outfits")
        cae_db = Path(tmp) / "caerness.db"
        os.environ["CAERNESS_DB_PATH"] = str(cae_db)
        os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
        from engine.db import connect as engine_connect, init_db
        init_db()
        cae = engine_connect()
        assert not system_enabled(cae, "outfits")
        assert TABLES <= tables(cae)  # the tables exist everywhere; only Saint Jude uses them
        assert cae.execute("SELECT COUNT(*) FROM outfit_ranks").fetchone()[0] == 0
        cae.close()
        os.environ["CAERNESS_DB_PATH"] = str(db)

        pkg = load_package("saintjude")
        orules, lrules = outfit_rules(pkg), law_rules(pkg)
        assert orules and lrules and not outfit_rules(load_package("caerness")) and not law_rules(load_package("caerness"))

        # every institution and ground place resolves
        for key, o in orules["outfits"].items():
            assert sj.execute("SELECT 1 FROM actors WHERE actor_type='institution' AND name=?", (o["institution"],)).fetchone(), key
            assert len(o.get("ground", [])) >= 1, key
            if o["shape"] == "family":
                assert len(o["ground"]) >= 2, key
            for place in o.get("ground", []):
                assert sj.execute("SELECT 1 FROM locations WHERE name=?", (place,)).fetchone(), (key, place)
            if "name_group" in o:
                assert o["name_group"] in pkg.name_groups, (key, o["name_group"])
        for a in lrules["agencies"].values():
            if a.get("institution"):
                assert sj.execute("SELECT 1 FROM actors WHERE actor_type='institution' AND name=?", (a["institution"],)).fetchone(), a
            assert a["jurisdiction"] in lrules["jurisdictions"]
            if a["jurisdiction"] in ("state", "federal"):
                assert a["pad_reaches"] is False
        pools = json.loads((ROOT / "worlds/saintjude/design_figures.json").read_text(encoding="utf-8"))["pools"]
        assert set(orules["line_kinds"]) == {k for k in pools if k != "pad"}
        for need in ("sabatini", "pellegrino", "ferrante", "vannucci"):
            assert orules["outfits"][need]["made_men_figure"].endswith(need)

        # figures: every reference exists, proposals are marked and sourced
        figs = design.package_figures(sj)
        for key in referenced_figure_keys(orules, lrules):
            assert figs.get(key) is not None, key
        for key in NEW_FIGURES:
            f = figs[key]
            assert f["mark"] == "Design proposal" and (f.get("source") or f.get("note")), key

        # the Pad tiers average to the derived mean
        assert abs(design.figure(sj, "pad_envelope_mean_check") - design.figure(sj, "pad_mean_envelope_usd_year") / 52) <= 1.0
        assert design.run_seed(sj) == sj.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0]

        # names
        g = pkg.name_groups
        assert len(g["italian"]["family"]) >= 80 and len(g["italian"]["male"]) >= 50
        assert len(g["irish"]["family"]) >= 40 and len(g["irish"]["male"]) >= 30
        assert len(g["black"]["family"]) >= 40 and len(g["black"]["male"]) >= 30
        for sex in ("male", "female", "family"):  # the merged pool follows the groups
            acc: dict[str, float] = {}
            for grp in g.values():
                for x in grp[sex]:
                    acc[x] = acc.get(x, 0) + grp["weight"] / len(grp[sex])
            assert set(acc) == set(pkg.name_pools[sex]) and all(abs(acc[k] - pkg.name_pools[sex][k]) < 1e-6 for k in acc), sex

        # nothing Saint Jude in the engine or connector
        assert grep_engine(["Sabatini", "Pellegrino", "Ferrante", "Vannucci", "Brigades", "Eastside Combine", "Horsemen", "Kerrytown"]) == []
        sj.close()
    print("saintjude_outfits_data_test passed")


if __name__ == "__main__":
    run()
