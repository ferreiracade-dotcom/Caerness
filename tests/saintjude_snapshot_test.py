"""The Saint Jude 1975 starting snapshot (worlds/saintjude/seed.json), built from the Saint Jude Setting Bible."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

SEED = ROOT / "worlds" / "saintjude" / "seed.json"
# Pressure, secret and plot words the snapshot must never carry in any descriptive text.
BANNED = re.compile(r"\btrials?\b|(?-i:RICO)|indict|subpoena|clerk|container|heroin|\$4M|(?<![\d.])4 million|secretly|pocket watch|"
                    r"bloodstain|caisson|Rossi|Barber Shop Hit|Harbor Sound", re.I)
# Old-codex names and groups that must not survive the rename and the 1975 rules of the new bible.
OLD_CODEX = re.compile(r"Castellano|Moretti|Petro-Star|Volkov|Neon Strip|East Bellacorte|Caisson", re.I)
# Named office holders the bible leaves Open (Part I 15.1, Part II 10, Index 7).
OPEN_HOLDERS = re.compile(r"Raymond Doyle|Haggerty|Winslow|Vance-Miller|Victor Hallam|Whitcomb|Patrick Keane|Thomas Boyle|Judith Katz|Matteo Russo|Harold Winslow")
LEAK = re.compile(r"Caerness|cultivat|\bStage\b|Vein-Root|\bSV\b|Hollow|Veinborn|martial|Salt Road|Aldergate|\bHouse\b")
FORMAL_POWER = re.compile(r"\b(Boss|Underboss|Capo|Consigliere|Mayor|Leader|President|Commissioner|(?<!Assistant )District Attorney|Judge|"
                          r"Archbishop|Special Agent in Charge|Head of|Lieutenant|Senator)\b")


def refs_of(obj):
    """Every string stored under a *_ref(s) key or a known reference list."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.endswith("_ref") and isinstance(v, str):
                out.append(v)
            elif k.endswith("_refs") or k in ("institutions", "seeded_members", "subjects", "known_at_opening",
                                              "leadership_ids", "owner_ids"):
                out += [x for x in v if isinstance(x, str)] if isinstance(v, list) else []
            elif k in ("from", "to") and isinstance(v, str) and v.startswith("sj:"):
                out.append(v)
            else:
                out += refs_of(v)
    elif isinstance(obj, list):
        for x in obj:
            out += refs_of(x)
    return out


def run():
    from engine import world_calendar
    from engine.world_package import load_package

    pkg = load_package("saintjude")
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    meta = seed["meta"]
    assert not meta.get("placeholder")

    # Ids are unique and every reference resolves.
    ids = []
    for kind in ("places", "institutions", "persons", "claims", "households"):
        ids += [x["id"] for x in seed[kind]]
    assert len(ids) == len(set(ids)), "duplicate ids"
    known = set(ids)
    for kind in ("places", "institutions", "persons", "claims", "households", "relationships", "latent_population_controls"):
        for r in refs_of(seed[kind]):
            assert r in known, (kind, r)
    place_names = {p["name"] for p in seed["places"]}
    for r in seed["routes"]:
        assert r["from_name"] in place_names and r["to_name"] in place_names, r["id"]
    assert len(place_names) == len(seed["places"])
    assert all(p["id"].startswith("sj:person:") for p in seed["persons"])

    # Counts and the four families (Part III 0: Castellano is Pellegrino, Moretti is Ferrante).
    families = [i for i in seed["institutions"] if i["category"] == "crime family"]
    assert len(families) == 4 and {f["name"] for f in families} == {
        "Sabatini Family", "Pellegrino Family", "Vannucci Family", "Ferrante Family"}
    inst_names = {i["name"] for i in seed["institutions"]}
    outside = {"Charlestown Brigades", "The Eastside Combine", "The Russians of Brighton Point", "Iron Horsemen MC",
               "The Puerto Rican Blocks", "Docks Chinatown Associations", "Saint Jude Police Department", "14th Precinct",
               "Organized Crime and Racketeering Strike Force", "FBI Saint Jude Field Office", "U.S. Attorney's Office",
               "Killbuck County Prosecutor's Office", "Marsh County Prosecutor's Office", "Oakridge Borough Police",
               "Killbuck Waterfront Commission", "Killbuck River Port Authority", "Local 402, Longshoremen", "Local 1201, Longshoremen",
               "City Hall", "Archdiocese of Saint Jude", "Saint Jude Daily Mirror", "Saint Jude Chronicle", "The Courier",
               "First Harbor National Bank", "Italian Credit Union", "Dunmore Savings Bank", "Mount Zion Hospital", "St. Anne's Hospital",
               "Saint Jude's College", "Saint Jude State University"}
    assert outside <= inst_names, outside - inst_names
    # 1975: the Kings do not exist, the Russians have no head or business, the Strike Force is not the FBI, no elected DA.
    assert not {"Mercer Street Kings", "Vorovskoy Syndicate", "Petro-Star Fuel", "District Attorney's Office",
                "FBI Organized Crime Strike Force"} & inst_names
    by_inst = {i["name"]: i for i in seed["institutions"]}
    combine, russians = by_inst["The Eastside Combine"], by_inst["The Russians of Brighton Point"]
    assert combine["continuity_core"]["leadership_ids"] == [] and russians["continuity_core"]["leadership_ids"] == []
    assert russians["owner_refs"] == [] and russians["seeded_members"] == []
    sf = by_inst["Organized Crime and Racketeering Strike Force"]["notes"]
    assert "Justice Department" in sf and "not an FBI unit" in sf
    assert "appointed by the Governor" in by_inst["Killbuck County Prosecutor's Office"]["notes"]
    assert "appointed by the Mayor" in by_inst["Saint Jude Police Department"]["notes"]
    assert len([i for i in seed["institutions"] if i["category"] == "police precinct"]) == 13
    assert len(seed["persons"]) >= 40 and len(seed["places"]) >= 60 and len(seed["institutions"]) >= 60
    for need in ("Saint Jude", "Bellacorte", "Kerrytown", "Killbuck Point", "The Pines", "Oakridge", "Brighton Point", "San Lorenzo (the Hill)",
                 "St. Rocco's Church", "St. Jude's Cathedral", "The Vesuvio Social and Athletic Club", "Pier 4 Diner", "The Fish Market",
                 "Gino's Espresso Bar", "The Villa Roma", "The Pompeii Social Club", "Russo and Sons Funeral Home",
                 "Mercy General Hospital", "Civic Arena", "Bayview Downs", "Crown Harbor", "The Narrows Bridge", "Point Pleasant",
                 "The Ironworks", "Mercer Avenue (the Strip)", "The Eastside", "The Racks", "Hunts Row", "Dunmore Avenue", "The Heights",
                 "Pescadores Row", "The Gannet Terminal", "Kosciuszko Park", "Greenwood", "Fenwick (College Hill)", "The Sixth Ward",
                 "Docks Chinatown", "The Corte", "Marsh County", "The Starlight Cabaret", "14th Precinct Station"):
        assert need in place_names, need
    by_name = {p["name"]: p for p in seed["places"]}
    assert by_name["Bellacorte"]["parent_ref"] == by_name["Saint Jude"]["id"] and by_name["Saint Jude"]["parent_ref"] is None
    # Oakridge is a Marsh County suburb, not a city district; the Racks, Hunts Row, rail yards and projects are in the Eastside.
    assert by_name["Oakridge"]["parent_ref"] == by_name["Marsh County"]["id"] and by_name["Oakridge"]["kind"] == "suburb"
    assert by_name["The Heights"]["parent_ref"] == by_name["Saint Jude"]["id"]
    assert by_name["The Racks"]["parent_ref"] == by_name["The Eastside"]["id"] and by_name["Hunts Row"]["parent_ref"] == by_name["The Racks"]["id"]
    assert by_name["Dunmore Avenue"]["parent_ref"] == by_name["The Eastside"]["id"]
    assert by_name["Pier 4 Diner"]["parent_ref"] == by_name["The North Piers"]["id"]
    assert "1.1 million" in by_name["Saint Jude"]["notes"] and "1640s" in by_name["Saint Jude"]["notes"]
    assert "East Bellacorte" not in place_names and "Oakridge Estates" not in place_names

    # Chronology: Gregorian day 0 is 1 January 1975; everyone is born before it.
    assert world_calendar.format_date(pkg, 0) == "Wednesday 1 January 1975"
    for p in seed["persons"]:
        assert p["life_status"] == "living" and isinstance(p["age"], int) and isinstance(p["birth_day"], int), p["name"]
        assert p["birth_day"] < 0, p["name"]
        assert p["birth_date"] == world_calendar.birth_date_for(pkg, p["birth_day"]), p["name"]
        assert (-p["birth_day"]) // 365 == p["age"], p["name"]
        assert int(p["birth_date"].split()[-1]) < 1975, p["name"]
    for k in ("codex_1980_ages", "backdating_notes", "age_only_changes", "added_people", "removed_post_1975_history"):
        assert k not in meta, k
    assert meta["removed_from_old_seed"] and meta["judgement_calls"] and meta["bible_silent"] and meta["open_offices"]
    assert "Setting Bible" in " ".join(meta["source_authority"])
    person = {p["name"]: p for p in seed["persons"]}

    # Part III 4.6 suggested seats, all Examples (Part III 4.6, Part V 0.2).
    assert all(p.get("canon_tag") == "Example" for p in seed["persons"])
    seats = {"Carmine Sabatini": ("Boss", 63), "Ettore Conti": ("Underboss", 58), "Corrado Bellini": ("Consigliere", 67),
             "Lorenzo DeLuca": ("Capo", 37), "Matteo Pellegrino": ("Boss", 56), "Vincent Scalise": ("Underboss", 41),
             "Agostino Maranzano": ("Consigliere", 61), "Jackie Pellegrino": ("Capo", 29), "Giuseppe Vannucci": ("Boss", 67),
             "Nicolo Vannucci": ("Underboss", 39), "Cesare Ragusa": ("Consigliere", 54), "Rico Basso": ("Capo", 34),
             "Umberto Bellomo": ("Capo", 62), "Salvatore Ferrante": ("Boss", 57), "Gennaro Ferrante": ("Underboss", 36),
             "Enzo Di Stefano": ("Consigliere", 66), "Dante Lombardo": ("Capo", 31)}
    for name, (rank, age) in seats.items():
        assert person[name]["role"].startswith(rank) and person[name]["age"] == age, name
    # The old seed's surname collisions are gone: a Ferrante or Pellegrino belongs to that family.
    inst_by_id = {i["id"]: i for i in seed["institutions"]}
    for p in seed["persons"]:
        for sur, fam in (("Ferrante", "Ferrante Family"), ("Pellegrino", "Pellegrino Family")):
            if p["name"].endswith(sur):
                assert fam in [inst_by_id[x]["name"] for x in p["institutions"]], p["name"]
    blob = json.dumps({k: v for k, v in seed.items() if k != "meta"})  # meta lists what was removed, by old name
    assert not OLD_CODEX.search(blob), OLD_CODEX.search(blob)
    assert not OPEN_HOLDERS.search(blob), OPEN_HOLDERS.search(blob)
    assert not [i for i in seed["institutions"] if i["category"] == "prosecutor" and i["continuity_core"]["leadership_ids"]]

    # Nothing later than 1975, no pressure or secret text, no Caerness leak.
    assert all(i.get("founded") is None or (isinstance(i["founded"], int) and i["founded"] <= 1975) for i in seed["institutions"])
    founded = {i["name"]: i["founded"] for i in seed["institutions"]}
    assert founded["Ferrante Family"] == 1958 and founded["Vannucci Family"] == 1967 and founded["Killbuck Waterfront Commission"] == 1954
    assert founded["St. Rocco's Parish"] == 1893 and founded["The Courier"] == 1912 and founded["City Hall"] == 1911
    assert founded["Archdiocese of Saint Jude"] is None and founded["St. Jude's Cathedral Parish"] == 1640
    texts = []
    for kind, fields in (("persons", ("current", "public_identity_text", "role", "name")), ("institutions", ("notes", "name", "category")),
                         ("places", ("notes", "name", "kind")), ("claims", ("text",))):
        for x in seed[kind]:
            for f in fields:
                texts.append((x.get("name") or x["id"], kind, f, x.get(f) or ""))
    for who, kind, f, t in texts:
        assert not LEAK.search(t), (who, f, t)
        if kind != "claims":  # claims record history, the 1974 purge among it
            assert not BANNED.search(t), (who, f, t)
    # Fixed history names no person and leaves the Open outcomes open (Part I 2.5, 2.6).
    claims = {c["id"]: c for c in seed["claims"]}
    assert set(claims) == {f"sj:claim:{k}" for k in (
        "founding-1640s", "cathedral-1868-1884", "harbor-wars-1929-1931", "harbor-war-1946", "waterfront-commission-1954",
        "ferrante-schism-1958", "vannucci-split-1967", "dolan-commission-1970-1972", "dock-strike-massacre-1973", "concrete-purge-1974")}
    assert all(c["subjects"] == [] for c in claims.values())
    for c in claims.values():
        for p in seed["persons"]:
            assert p["name"] not in c["text"], (c["id"], p["name"])
    assert "Pellegrino crews" in claims["sj:claim:dock-strike-massacre-1973"]["text"]
    assert "Who they were is Open" in claims["sj:claim:dock-strike-massacre-1973"]["text"]
    assert "Open" in claims["sj:claim:concrete-purge-1974"]["text"] and "caisson" not in blob.lower()
    assert "Who started it" in claims["sj:claim:ferrante-schism-1958"]["text"]
    assert "Four-Corner Harbor War" in claims["sj:claim:harbor-war-1946"]["text"]
    assert "1640s" in claims["sj:claim:founding-1640s"]["text"] and "1868 to 1884" in claims["sj:claim:cathedral-1868-1884"]["text"]
    assert "1977" not in json.dumps({k: seed[k] for k in ("places", "institutions", "persons", "claims")})
    assert seed["processes"] == []
    starlight = next(i for i in seed["institutions"] if i["name"] == "The Starlight Cabaret")
    assert "disco" not in starlight["notes"].replace("not a disco", "")

    # Names match sex, drawn from the package's pools; women are a clear minority and never made.
    groups = json.loads(pkg.data["names"].read_text(encoding="utf-8"))["groups"]
    male_names = {n for g in groups.values() for n in g["male"]}
    female_names = {n for g in groups.values() for n in g["female"]}
    extra_male = {"Rocco", "Aurelio", "Ignazio", "Rico", "Umberto", "Nicolo", "Agostino", "Corrado", "Cesare", "Pasquale", "Gennaro",
                  "Dante", "Declan", "Brendan", "Liam", "Gino", "Giuseppe", "Carmine", "Dominic", "Lorenzo", "Salvatore", "Ettore",
                  "Sol", "Vincent", "Darius", "Marvin", "Harrison", "Roland", "Roy", "Walter", "Arthur", "Gerald",
                  "Eugene", "Leo", "Jackie", "Johnny", "Paul", "Carlo", "Louis", "Dennis", "Thomas",
                  "Martin", "Anthony", "Francis", "Michael", "Matteo", "Enzo", "John"}
    extra_female = {"Concetta", "Teresa", "Lucia", "Valerie", "Maureen", "Margaret"}
    for p in seed["persons"]:
        given = p["name"].split()[0]
        assert p["demographic_sex"] in ("male", "female"), p["name"]
        if p["demographic_sex"] == "male":
            assert given in male_names | extra_male and given not in female_names - male_names, p["name"]
        else:
            assert given in female_names | extra_female and given not in male_names - female_names, p["name"]
    women = [p for p in seed["persons"] if p["demographic_sex"] == "female"]
    assert 0.05 <= len(women) / len(seed["persons"]) <= 0.15, len(women)
    assert not [w["name"] for w in women if FORMAL_POWER.search(w["role"])
                or re.match(r"(Boss|Underboss|Capo|Consigliere|Soldier|Associate)\b", w["role"])], "a woman holds a made rank or formal power"
    assert meta["counts"] == {"persons": len(seed["persons"]), "women": len(women), "places": len(seed["places"]),
                              "institutions": len(seed["institutions"]), "claims": len(seed["claims"]), "routes": len(seed["routes"])}
    sexes = {p["id"]: p["demographic_sex"] for p in seed["persons"]}
    for f in families:
        leaders = f["continuity_core"]["leadership_ids"]
        assert leaders and all(sexes[l] == "male" for l in leaders)
    underworld = [p for p in seed["persons"] if re.match(r"(Boss|Underboss|Capo|Consigliere|Soldier)\b", p["role"])]
    assert len(underworld) >= 20 and all(p["demographic_sex"] == "male" for p in underworld)

    # Money: the price book gives sales and margins by trade (Part VI 4.4), not valuations; none is seeded.
    rows = {r["key"]: r for r in json.loads(pkg.data["prices"].read_text(encoding="utf-8"))["rows"]}
    profiled = 0
    for i in seed["institutions"]:
        assert "valuation_1975" not in i["economic_state"], i["name"]
        t = i["economic_state"].get("trade_profile_1975")
        if t:
            profiled += 1
            assert t["sales_a_year"]["default"] == rows[f"trade_{t['trade']}_sales"]["default"], i["name"]
            assert t["net_pct_of_sales"]["default"] == rows[f"trade_{t['trade']}_net_pct"]["default"], i["name"]
    assert profiled >= 5

    # The file is exactly what the data module produces.
    import build_saintjude_seed as B
    assert B.dumps(B.build()) == SEED.read_text(encoding="utf-8"), "seed.json is stale: run tools/build_saintjude_seed.py"

    # It imports into a Saint Jude database: counts, ages, sex and kinship.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.environ["CAERNESS_DB_PATH"] = str(Path(tmp) / "snap.db")
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from engine.current_seed import import_current_seed
        from engine.db import connect, init_db
        from engine.world_package import set_campaign_package
        init_db()
        conn = connect()
        set_campaign_package(conn, "saintjude")
        res = import_current_seed(conn)
        conn.commit()
        assert res["persons"] == len(seed["persons"]) and res["places"] == len(seed["places"]) and res["institutions"] == len(seed["institutions"])
        assert conn.execute("SELECT COUNT(*) FROM actors WHERE actor_type='character'").fetchone()[0] == len(seed["persons"])
        assert conn.execute("SELECT COUNT(*) FROM kinship_links WHERE kin_kind='spouse'").fetchone()[0] == 2
        conn.close()
    print("saintjude_snapshot_test passed")


if __name__ == "__main__":
    run()
