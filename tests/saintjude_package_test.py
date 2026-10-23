"""Task 16: the Saint Jude bible (worlds/saintjude/bible.md) adapted from the Bellacorte codex."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PKG = ROOT / "worlds" / "saintjude"
BIBLE = PKG / "bible.md"
# Words that must never reach a Saint Jude player. Task 21 widens this via tools/leak_scan.FORBIDDEN.
LEAK_WORDS = ("Caerness", "cultivat", "Stage", "Vein-Root", "SV", "Hollow", "Veinborn", "martial", "Salt Road",
              "Aldergate", "House")
PLACE_KINDS = ("bar", "club", "church", "precinct", "office", "street")


def run():
    assert BIBLE.exists(), "worlds/saintjude/bible.md missing"
    text = BIBLE.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        os.environ["CAERNESS_DB_PATH"] = str(tmp / "canon.db")
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from engine import canon
        from engine.db import connect, init_db
        from connector.lore import lore

        init_db()
        res = canon.index_canon(BIBLE, force=True)
        assert res["chunks"] >= 60, res
        with connect() as conn:
            rows = conn.execute("SELECT heading_path, text FROM canon_chunks ORDER BY chunk_index").fetchall()
            assert len(rows) >= 60
            for r in rows:
                hp = r["heading_path"] or ""
                assert hp and hp != "Document", hp

            # Names: the city is Saint Jude; Bellacorte is only a district.
            assert not re.search(r"city of Bellacorte|Bellacorte, ", text), "Bellacorte used as a city name"
            for old in ("Port St. Jude", "Meadowlands"):
                assert old not in text, old
            for city_use in ("Bellacorte Daily", "Bellacorte Chronicle", "Bellacorte Police", "Bellacorte MCC",
                             "Bellacorte Civic", "Archdiocese of Bellacorte", "Bellacorte State", "BCPD"):
                assert city_use not in text, city_use

            # Hard-coded character secrets and pressures appear only under an "Examples" heading, if at all.
            for needle in ("Sally Glasses", "Vinny Scales", "David Rossi", "Matty", "Barber Shop Hit"):
                for r in rows:
                    if needle in r["text"]:
                        assert "Examples" in (r["heading_path"] or ""), (needle, r["heading_path"])
            assert "Roster" not in text and "Private Vector" not in text

            # Shape: required sections.
            paths = "\n".join(r["heading_path"] for r in rows)
            for need in ("Founding and history", "Adaptation notes", "Taboos", "Street dictionary",
                         "Technology", "Economic reference ledger"):
                assert need.lower() in paths.lower(), need
            assert "never impossible" in text
            assert text.count("Assumption:") >= 8, text.count("Assumption:")
            notes = text[text.index("## Adaptation notes"):]
            for fix in ("8.1", "8.2", "12.2", "13.2", "Pressure 2"):
                assert fix in notes, fix

            # lore() finds the renamed places and the founding story.
            out = lore(conn, "Killbuck Point")
            assert out["passages"], out
            assert any("Killbuck Point" in p["text"] for p in out["passages"])
            out = lore(conn, "founding church cathedral St. Jude's")
            assert any("cathedral" in p["text"] for p in out["passages"])
            out = lore(conn, "the Pines")
            assert any("Pines" in p["text"] for p in out["passages"])
    print("saintjude_package_test (bible) passed")


def run_sections():
    """Task 17: rulebook and creation sections, and manners."""
    import json
    for name in ("rulebook_section.md", "creation_section.md", "manners.json"):
        assert (PKG / name).is_file(), name
    try:
        from tools.leak_scan import FORBIDDEN
        words = tuple(dict.fromkeys(LEAK_WORDS + tuple(FORBIDDEN)))
    except ImportError:  # Task 21 not built yet
        words = LEAK_WORDS
    rule = (PKG / "rulebook_section.md").read_text(encoding="utf-8")
    create = (PKG / "creation_section.md").read_text(encoding="utf-8")
    manners = json.loads((PKG / "manners.json").read_text(encoding="utf-8"))
    for label, text in (("rulebook", rule), ("creation", create), ("manners", json.dumps(manners))):
        for w in words:
            assert w not in text, (label, w)
    assert "veto" in rule and "menu of" not in rule and "menu of" not in create
    for need in ("tendenc", "never choose", "Plain English", "continuity check", "not a rank number"):
        assert need.lower() in rule.lower(), need
    assert "new person" in create and "lore" in create
    for kind in PLACE_KINDS + ("default",):
        assert str(manners.get(kind, "")).strip(), kind

    # The section fills every marker of the shared core and keeps the connector's whitespace rule.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        worlds = tmp / "worlds"
        (worlds / "sjtmp").mkdir(parents=True)
        (worlds / "sjtmp" / "seed.json").write_text("{}", encoding="utf-8")
        (worlds / "sjtmp" / "world.json").write_text(json.dumps({
            "id": "sjtmp", "display_name": "Saint Jude", "calendar": {"kind": "gregorian", "start": "1975-01-01"},
            "bible_path": str(BIBLE), "seed_path": "seed.json", "seed_namespace": "x",
            "rulebook_section": str(PKG / "rulebook_section.md"), "creation_section": str(PKG / "creation_section.md"),
            "systems": {}, "data": {}}), encoding="utf-8")
        os.environ["CAERNESS_WORLDS_DIR"] = str(worlds)
        os.environ["CAERNESS_WORLD_PACKAGE"] = "sjtmp"
        try:
            from connector.session import RULEBOOK_CORE_PATH, load_creation, load_rulebook
            rb = load_rulebook()
            assert "{{" not in rb and rb.count("\n" * 3) == 0
            assert "game master for Saint Jude" in rb and "Close third person" in rb
            for w in words:
                assert w not in rb, w
            assert "Caerness" not in load_creation()
            core = RULEBOOK_CORE_PATH.read_text(encoding="utf-8")
            for key in set(re.findall(r"[{][{]world:(\w+)[}][}]", core)):
                assert "{{" + key + "}}" in rule, key
        finally:
            os.environ.pop("CAERNESS_WORLDS_DIR", None)
            os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    print("saintjude_package_test (sections) passed")


def run_data():
    """Task 18: manifest, timeline, prices, archetypes, taboos, names and mortality."""
    import datetime
    import json

    import numpy as np

    os.environ.pop("CAERNESS_WORLDS_DIR", None)
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    from engine import world_package as wp
    from engine.background_population import annual_mortality
    from engine.business import _CONTEXT_DEFAULTS

    pkg = wp.load_package("saintjude")
    assert pkg.id == "saintjude" and pkg.display_name == "Saint Jude"
    assert pkg.calendar == {"kind": "gregorian", "start": "1975-01-01"}, pkg.calendar
    assert pkg.bible_sha256 is None and pkg.seed_namespace == "saintjude_seed_v1"
    assert set(pkg.systems) == set(wp.SYSTEM_KEYS) and not any(pkg.systems.values()), pkg.systems
    assert pkg.background["stage_distribution"] is False and pkg.opening_family["marry_adults_on_day0"] is False
    assert pkg.rulebook_section and pkg.creation_section and pkg.bible_path.name == "bible.md"
    for name in ("archetypes", "manners", "timeline", "prices", "taboos", "names"):
        assert pkg.data[name].is_file(), name

    # Timeline.
    assert wp.timeline_status(pkg, "cellular phone", "1975-06-01") == "not_yet"
    assert wp.timeline_status(pkg, "pager", "1980-01-01") == "available"
    assert wp.timeline_status(pkg, "Beeper", datetime.date(1980, 1, 1)) == "available"  # alias, case, date object
    assert wp.timeline_status(pkg, "pager", "1950-01-01") == "exists"
    assert wp.timeline_status(pkg, "pager", "1940-01-01") == "not_yet"
    assert wp.timeline_status(pkg, "pager", "1999-01-01") == "available"  # never common: stays available
    assert wp.timeline_status(pkg, "personal computer", "1995-06-01") == "common"
    assert wp.timeline_status(pkg, "teleporter", "1980-01-01") == "unknown"
    assert wp.timeline_status(pkg, "Title III wiretap", "1967-12-31") == "not_yet"
    assert wp.timeline_status(pkg, "cellular phone", "1984-02-01") == "available"
    entries = json.loads(pkg.data["timeline"].read_text(encoding="utf-8"))
    assert isinstance(entries, list) and len(entries) >= 25
    iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    seen = set()
    for e in entries:
        assert e["name"] not in seen, e["name"]
        seen.add(e["name"])
        assert str(e.get("source", "")).strip(), e["name"]
        dates = [e.get(k) for k in ("exists", "available", "common")]
        assert dates[0] is not None, e["name"]
        stated = [d for d in dates if d is not None]
        for d in stated:
            assert iso.match(d), (e["name"], d)
            datetime.date.fromisoformat(d)
        assert stated == sorted(stated), (e["name"], dates)
    for need in ("pager", "cellular phone", "fax machine", "videocassette recorder", "answering machine", "Title III wiretap",
                 "RICO", "Witness Security Program", "money laundering statute"):
        assert need in seen, need

    # Prices: national benchmarks kept apart from Saint Jude estimates; every estimate has a basis and is an assumption.
    prices = json.loads(pkg.data["prices"].read_text(encoding="utf-8"))
    assert prices["year"] == 1975 and prices["currency"] == "USD"
    assert {b["key"] for b in prices["national_benchmarks"]} >= {"federal_minimum_wage", "cpi_u_annual_average", "median_family_income"}
    assert all(str(b["basis"]).strip() for b in prices["national_benchmarks"])
    mw = next(b for b in prices["national_benchmarks"] if b["key"] == "federal_minimum_wage")
    assert mw["value_1975"] == 2.10 and mw["value_1980"] == 3.10
    cpi = next(b for b in prices["national_benchmarks"] if b["key"] == "cpi_u_annual_average")
    assert abs(prices["ratios"]["goods"]["value"] - cpi["value_1975"] / cpi["value_1980"]) < 0.001
    rows = prices["saint_jude_estimates"]
    assert len(rows) >= 60
    price_keys = [r["key"] for r in rows]
    assert len(price_keys) == len(set(price_keys))
    for r in rows:
        assert str(r.get("basis", "")).strip() and r.get("assumption") is True, r["key"]
        assert 0 < r["low"] <= r["high"], r["key"]
        top = max(float(v.replace(",", "")) for v in re.findall(r"\$([\d,]+(?:\.\d+)?)", r["ledger_1980"]))
        assert 0.5 <= r["high"] / top <= 0.8, (r["key"], r["high"], top)

    # Archetypes: the same required shape as the Caerness vocabulary, built on the 1975 price rows.
    arch = json.loads(pkg.data["archetypes"].read_text(encoding="utf-8"))
    want = {"bar", "diner", "pizzeria", "social_club", "nightclub", "trucking_firm", "warehouse", "car_dealership",
            "construction_firm", "laundromat", "vending_route", "numbers_bank", "sports_book", "bakery", "butcher",
            "funeral_home", "union_local_office"}
    assert set(arch) == want, set(arch) ^ want
    kinds = {"merchant_house", "workshop", "estate", "shop", "studio", "shipping", "construction", "service", "other"}
    context = set(_CONTEXT_DEFAULTS) | {"security_inverse"}
    for key, a in arch.items():
        for need in ("name", "sector", "enterprise_kind", "base_revenue", "cost_ratio", "weights"):
            assert need in a, (key, need)
        assert a["enterprise_kind"] in kinds, key
        assert a["base_revenue"] > 0 and 0 < a["cost_ratio"] < 1.5 and 0 <= a.get("regulation", 0) <= 1
        assert a["weights"] and set(a["weights"]) <= context, (key, set(a["weights"]) - context)
        assert set(a.get("price_refs", [])) <= set(price_keys), (key, set(a.get("price_refs", [])) - set(price_keys))
        assert str(a.get("basis", "")).strip() and a.get("assumption") is True, key
    assert all(a["price_refs"] for k, a in arch.items() if k not in ("numbers_bank", "sports_book", "funeral_home"))

    # Taboos: who cares and a range of reactions; nothing is declared impossible.
    taboos = json.loads(pkg.data["taboos"].read_text(encoding="utf-8"))["taboos"]
    assert len(taboos) == 9, list(taboos)
    banned = re.compile(r"forbidden|impossible|never", re.I)

    def keys_of(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys_of(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys_of(v)

    assert not [k for k in keys_of(taboos) if banned.search(k)]
    for key, t in taboos.items():
        assert t["who_cares"] and len(t["typical_reactions"]) >= 2 and t["can_be_permitted_by"], key
    for need in ("killing_a_cop", "killing_a_reporter", "holding_out", "informing", "a_made_mans_wife",
                 "violence_in_the_oakridge_sanctuary", "disrespecting_a_boss_in_public"):
        assert need in taboos, need

    # Names: seven groups, >= 40 names in every pool, and world.json's weighted pools are the merge of names.json.
    names = json.loads(pkg.data["names"].read_text(encoding="utf-8"))["groups"]
    assert set(names) == {"italian", "irish", "black", "jewish", "russian", "puerto_rican", "wasp"}
    assert abs(sum(g["weight"] for g in names.values()) - 1.0) < 1e-9
    for gname, g in names.items():
        for kind in ("male", "female", "family"):
            assert len(g[kind]) >= 40 and len(set(g[kind])) == len(g[kind]), (gname, kind)
    for kind in ("male", "female", "family"):
        pool = pkg.name_pools[kind]
        assert isinstance(pool, dict) and abs(sum(pool.values()) - 1.0) < 1e-3, kind
        expect = {}
        for g in names.values():
            for n in g[kind]:
                expect[n] = expect.get(n, 0.0) + g["weight"] / len(g[kind])
        assert set(pool) == set(expect), kind
        assert all(abs(pool[n] - expect[n]) < 1e-5 for n in pool), kind

    # Mortality: a published-style table, assumption recorded, plausible and rising with age.
    assert pkg.mortality["model"] == "table" and pkg.mortality["assumption"] is True and pkg.mortality["source"]
    ages = np.array([30.0, 80.0]) * 365.2425
    male = annual_mortality(ages, pkg.mortality, np.array([0, 0]))
    female = annual_mortality(ages, pkg.mortality, np.array([1, 1]))
    assert 0.001 <= male[0] <= 0.004 and 0.05 <= male[1] <= 0.12 and 0.05 <= female[1] <= 0.12, (male, female)
    assert female[0] < male[0] and female[1] < male[1]
    grid = np.arange(15, 101, 5) * 365.2425
    for sex in (0, 1):
        curve = annual_mortality(grid, pkg.mortality, np.full(grid.size, sex))
        assert (np.diff(curve) > 0).all(), (sex, curve)

    # The archetypes are what the engine seeds for a Saint Jude campaign.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.environ["CAERNESS_DB_PATH"] = str(Path(tmp) / "arch.db")
        from engine.business import seed_business_archetypes
        from engine.db import connect, init_db
        init_db()
        with connect() as conn:
            wp.set_campaign_package(conn, "saintjude")
            seed_business_archetypes(conn)
            got = {r[0] for r in conn.execute("SELECT archetype_key FROM business_archetypes")}
            assert got == want, got ^ want
    print("saintjude_package_test (data) passed")


if __name__ == "__main__":
    run()
    run_sections()
    run_data()
