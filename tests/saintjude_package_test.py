"""Task 16: the Saint Jude bible (worlds/saintjude/bible.md), the seven setting-bible files (Index, Parts I to VI) joined by tools/build_saintjude_bible.py."""
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
        assert res["chunks"] >= 400, res
        with connect() as conn:
            rows = conn.execute("SELECT heading_path, text FROM canon_chunks ORDER BY chunk_index").fetchall()
            assert len(rows) >= 400
            for r in rows:
                hp = r["heading_path"] or ""
                assert hp and hp != "Document", hp

            # Names: the city is Saint Jude; Bellacorte is only a district.
            assert not re.search(r"city of Bellacorte", text), "Bellacorte used as a city name"  # Bellacorte is District Four
            for old in ("Port St. Jude", "Meadowlands"):
                assert old not in text, old
            for city_use in ("Bellacorte Daily", "Bellacorte Chronicle", "Bellacorte Police", "Bellacorte MCC",
                             "Bellacorte Civic", "Archdiocese of Bellacorte", "Bellacorte State", "BCPD"):
                assert city_use not in text, city_use

            # Hard-coded character secrets and pressures appear only under an "Examples" heading, if at all.
            for needle in ("Sally Glasses", "Vinny Scales", "David Rossi", "Matty"):  # the bible names its old "Barber Shop Hit" only to withdraw it (Part I 2.5)
                for r in rows:
                    if needle in r["text"]:
                        assert "Examples" in (r["heading_path"] or ""), (needle, r["heading_path"])
            assert "Roster" not in text and "Private Vector" not in text

            # Shape: the seven files in order, each Part under its own H2, with the sections the engine leans on.
            paths = chr(10).join(r["heading_path"] for r in rows)
            heads = ("Index and Status", "Part I: The City", "Part II: The Law", "Part III: The Underworld",
                     "Part IV: The Upperworld", "Part V: The Outside Groups", "Part VI: The Price Book")
            at = [text.index("## " + h) for h in heads]
            assert at == sorted(at), at
            for need in ("The Period Mind", "Taboos: Acts and Their Consequences", "Names", "Women in Saint Jude",
                         "Price Weather", "Law Weather"):
                assert need.lower() in paths.lower(), need
            assert "A taboo is never a wall" in text and "women are never made" in text
            assert "**Content limits.** No real person acts or speaks." in text
            assert text.count("[verified") >= 100, text.count("[verified")
            assert "Pellegrino" in text and "Ferrante" in text  # the renamed families

            # The package's bible is exactly the seven source files (bible_sources.json records their hashes).
            import hashlib
            import json
            src = json.loads((PKG / "bible_sources.json").read_text(encoding="utf-8"))
            assert src["files"][0]["file"] == "Saint_Jude_Bible_Index.md" and len(src["files"]) == 7
            assert src["bible_md_sha256"] == hashlib.sha256(BIBLE.read_bytes()).hexdigest()

            # lore() finds the renamed places and the founding story.
            out = lore(conn, "Killbuck Point")
            assert out["passages"], out
            assert any("Killbuck Point" in p["text"] for p in out["passages"])
            out = lore(conn, "St. Jude's Cathedral")
            assert out["passages"] and any("athedral" in p["text"] for p in out["passages"]), out
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
    # Dates from the bible (Part II 6, 9; Part I 13; Part IV 2.3; Part VI 10): a rule is never applied early.
    ts = lambda name, day: wp.timeline_status(pkg, name, day)
    assert ts("pen register", "1979-05-31") == "exists" and ts("pen register", "1979-07-01") == "available"
    assert ts("RICO", "1970-09-30") == "not_yet" and ts("RICO", "1971-01-01") == "exists" and ts("RICO", "1973-11-01") == "available"
    assert ts("RICO used against organized crime", "1977-12-31") == "not_yet" and ts("RICO used against organized crime", "1978-01-01") == "exists"
    assert ts("RICO prosecution of a Mafia leadership", "1985-02-24") == "not_yet" and ts("RICO prosecution of a Mafia leadership", "1985-02-25") == "exists"
    assert ts("federal preventive detention", "1984-10-11") == "not_yet" and ts("Bail Reform Act of 1984", "1984-10-12") == "available"
    assert ts("Landrum-Griffin Act", "1980-01-01") == "available" and ts("union-office bar lengthened to thirteen years", "1984-10-11") == "not_yet"
    assert ts("Title III wiretap", "1968-12-31") == "available" and ts("Witness Security Program", "1971-06-01") == "exists"
    assert ts("Pick-3", "1975-05-21") == "not_yet" and ts("Pick-it", "1975-05-22") == "available"
    assert ts("Atlantic City casino", "1978-05-25") == "not_yet" and ts("Atlantic City casino", "1978-05-26") == "available"
    assert ts("Elizabeth Marine Terminal", "1962-08-14") == "not_yet" and ts("Elizabeth Marine Terminal", "1962-08-15") == "available"
    assert ts("State Commission of Investigation", "1968-12-31") == "exists" and ts("SCI", "1969-01-01") == "available"
    assert ts("forensic DNA profiling", "1985-12-31") == "not_yet" and ts("forensic DNA profiling", "1987-12-31") == "available"
    assert ts("crack cocaine", "1983-12-31") == "not_yet" and ts("crack", "1985-01-01") == "available"
    assert ts("cellular phone", "1983-12-30") == "not_yet" and ts("Bell breakup", "1984-12-30") == "not_yet"
    entries = json.loads(pkg.data["timeline"].read_text(encoding="utf-8"))
    assert isinstance(entries, list) and len(entries) >= 25
    assert all(isinstance(e.get("from_bible"), bool) for e in entries)  # every entry says whether the bible dates it
    assert all(e["from_bible"] or "Not from the bible" in e["source"] for e in entries)
    assert all(not e["from_bible"] or re.search(r"Part (I|II|III|IV|V|VI) \d", e["source"]) for e in entries)  # a bible entry cites its section
    assert not [e["name"] for e in entries if re.search(r"codex|Appendix|section A\d", e["source"], re.I)]
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
    rows = prices["rows"]  # Part VI: every row has a default or a range, a mark and a Part VI source
    assert len(rows) >= 200
    price_keys = [r["key"] for r in rows]
    assert len(price_keys) == len(set(price_keys))
    for r in rows:
        assert r.get("default") is not None or r.get("range"), r["key"]
        assert r.get("mark") and re.match(r"Part VI \d", str(r.get("source", ""))), r["key"]
        assert r.get("tag") in ("Fixed", "Open", "Weather", "Anchor", "Tendency", "Design", "Example"), r["key"]

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
    # price_refs point at Part VI 4.4 trade rows; a trade the bible is silent on has none and says so.
    assert all(a["price_refs"] or "bible silent" in a.get("price_refs_note", "") for a in arch.values())
    assert all(ref.startswith("trade_") for a in arch.values() for ref in a["price_refs"])

    # Taboos (Part III 9: 15 rows; Part V 10.4: 8 rows): who cares and a range of reactions; each is a price, not a wall.
    tdoc = json.loads(pkg.data["taboos"].read_text(encoding="utf-8"))
    taboos = tdoc["taboos"]
    assert len(taboos) == 23, list(taboos)
    assert [t["source"] for t in taboos.values()].count("Part III 9") == 15 and [t["source"] for t in taboos.values()].count("Part V 10.4") == 8
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
        assert t["kind"] == "taboo_price" and t["act"] and t["tag"] == "Fixed", key
        assert t["who_cares"] and t["typical_reactions"] and t["can_be_excused_by"], key
        assert "women" not in key or key in ("a_made_mans_wife_or_daughter", "touching_a_civilian_woman_or_child"), key
    for need in ("killing_a_police_officer", "killing_a_reporter", "striking_a_made_man", "killing_a_made_man_of_another_family",
                 "holding_out", "informing", "violence_in_a_church_or_at_a_wake", "touching_a_civilian_woman_or_child",
                 "betraying_a_compare", "lying_to_a_boss", "violence_in_the_oakridge_sanctuary", "publicly_disrespecting_a_boss"):
        assert need in taboos, need
    # The one absolute is not a priced taboo: women are never made (Part III 9, Part I 12.2).
    rules = tdoc["fixed_rules"]
    assert [r["key"] for r in rules] == ["women_are_never_made"] and rules[0]["kind"] == "fixed_rule" and rules[0]["carries_no_price"] is True
    assert "typical_reactions" not in rules[0] and "women_are_never_made" not in taboos

    # Names (Part I 14.1: 11 groups; Part I 7.1 shares): world.json's weighted pools are the merge of names.json.
    ndoc = json.loads(pkg.data["names"].read_text(encoding="utf-8"))
    names = ndoc["groups"]
    assert set(names) == {"italian", "irish", "polish_slavic", "portuguese", "black", "jewish", "old_protestant",
                          "puerto_rican_latino", "greek_lebanese_armenian", "soviet_jewish_emigre", "chinese"}
    assert abs(sum(g["weight"] for g in names.values()) - 1.0) < 1e-9
    assert names["black"]["weight"] > names["italian"]["weight"] > names["irish"]["weight"] > names["old_protestant"]["weight"] > names["polish_slavic"]["weight"]
    assert abs(names["soviet_jewish_emigre"]["weight"] - 0.2 / 92.2) < 1e-6 and ndoc["gaps"]  # Part I 7.1 gives them 0.2 percent
    for gname, g in names.items():
        for kind in ("male", "female", "family"):
            assert len(g[kind]) >= 6 and len(set(g[kind])) == len(g[kind]), (gname, kind)
    assert "Pellegrino" in names["italian"]["family"] and "Ferrante" in names["italian"]["family"] and "Gabriel" in names["italian"]["male"]
    assert "Castellano" not in names["italian"]["family"] and "Moretti" not in names["italian"]["family"]
    assert len(names["italian"]["family"]) == 27 and len(names["italian"]["female"]) == 10 and len(names["black"]["female"]) == 6
    assert [k for k, g in names.items() if g["female_source"] == "bible"] == ["italian", "black"]  # the rest are labelled fallbacks
    for kind in ("male", "female", "family"):
        pool = pkg.name_pools[kind]
        assert isinstance(pool, dict) and abs(sum(pool.values()) - 1.0) < 1e-3, kind
        expect = {}
        for g in names.values():
            for n in g[kind]:
                expect[n] = expect.get(n, 0.0) + g["weight"] / len(g[kind])
        assert set(pool) == {n for n in expect if expect[n] > 0}, kind
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
