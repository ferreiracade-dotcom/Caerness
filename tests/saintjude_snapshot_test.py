"""Task 19: the Saint Jude 1975 starting snapshot (worlds/saintjude/seed.json)."""
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
BANNED = re.compile(r"trial|(?-i:RICO)|indict|subpoena|clerk|container|heroin|\$4M|(?<![\d.])4 million|secretly|pocket watch|"
                    r"bloodstain|caisson|Rossi|Barber Shop Hit|Harbor Sound", re.I)
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

    # Counts.
    families = [i for i in seed["institutions"] if i["category"] == "crime family"]
    assert len(families) == 4 and {f["name"] for f in families} == {
        "Sabatini Family", "Castellano Family", "Vannucci Family", "Moretti Family"}
    inst_names = {i["name"] for i in seed["institutions"]}
    outside = {"Charlestown Brigades", "Vorovskoy Syndicate", "Mercer Street Kings", "Iron Horsemen MC", "Saint Jude Police Department",
               "14th Precinct", "FBI Organized Crime Strike Force", "City Hall", "District Attorney's Office",
               "Archdiocese of Saint Jude", "Saint Jude Daily Mirror", "Saint Jude Chronicle", "Teamsters Local 814"}
    assert outside <= inst_names, outside - inst_names
    assert len(seed["persons"]) >= 40 and len(seed["places"]) >= 30 and len(seed["institutions"]) >= 40
    for need in ("Saint Jude", "Bellacorte", "Kerrytown", "Killbuck Point", "The Pines", "Oakridge", "Brighton Point", "The Hill",
                 "St. Rocco's Church", "St. Jude's Cathedral", "The Vesuvio Social and Athletic Club", "Pier 4 Diner and Fish Market",
                 "Gino's Espresso Bar", "Villa Roma", "The Pompeii Social Club and Cigar Store", "Russo and Sons Funeral Home",
                 "Mercy General Hospital", "Saint Jude Civic Arena", "Bayview Downs Racetrack", "Crown Harbor", "The Narrows Bridge",
                 "Point Pleasant", "The Ironworks", "Mercer Avenue", "East Bellacorte"):
        assert need in place_names, need
    by_name = {p["name"]: p for p in seed["places"]}
    assert by_name["Bellacorte"]["parent_ref"] == by_name["Saint Jude"]["id"] and by_name["Saint Jude"]["parent_ref"] is None

    # Chronology: Gregorian day 0 is 1 January 1975; everyone is born before it and is exactly five years younger than the codex.
    assert world_calendar.format_date(pkg, 0) == "Wednesday 1 January 1975"
    ages80 = meta["codex_1980_ages"]
    assert len(ages80) >= 35
    for p in seed["persons"]:
        assert p["life_status"] == "living" and isinstance(p["age"], int) and isinstance(p["birth_day"], int), p["name"]
        assert p["birth_day"] < 0, p["name"]
        assert p["birth_date"] == world_calendar.birth_date_for(pkg, p["birth_day"]), p["name"]
        assert (-p["birth_day"]) // 365 == p["age"], p["name"]
        assert int(p["birth_date"].split()[-1]) < 1975, p["name"]
        if p["id"] in ages80:
            assert p["age"] == ages80[p["id"]] - 5 and p["age"] != ages80[p["id"]], p["name"]
    assert set(ages80) <= {p["id"] for p in seed["persons"]}
    person = {p["name"]: p for p in seed["persons"]}

    # Back-dated posts.
    assert person["Giuseppe Vannucci"]["life_status"] == "living" and person["Giuseppe Vannucci"]["role"].startswith("Boss")
    assert person["Nicolo Vannucci"]["role"].startswith("Underboss")
    assert person["Michael Santoro"]["age"] == 24 and "Capo" not in person["Michael Santoro"]["role"]
    assert person["Matteo Castellano"]["role"].startswith("Underboss") and person["Pietro Castellano"]["role"].startswith("Boss")
    assert not person["Francis Callahan"]["role"].startswith("Mayor") and person["Raymond Doyle"]["role"].startswith("Mayor")
    notes = meta["backdating_notes"]
    assert notes
    noted = {n["person"] for n in notes}
    age_only = {n["person"] for n in meta["age_only_changes"]}
    for n in notes + meta["age_only_changes"]:
        assert set(n) >= {"person", "post_1980", "post_1975", "reason"} and n["reason"], n
    assert not noted & age_only and noted | age_only == set(ages80)  # every codex person is accounted for
    assert all(n["post_1980"] != n["post_1975"] for n in notes)
    assert all(n["post_1980"] == n["post_1975"] for n in meta["age_only_changes"])
    assert len(notes) >= 15
    added = meta["added_people"]
    assert len(added) >= 15 and {a["person"] for a in added} == {p["id"] for p in seed["persons"]} - set(ages80)
    assert meta["removed_post_1975_history"] and meta["judgement_calls"]

    # Nothing later than 1975, no pressure or secret text, no Caerness leak.
    assert all(isinstance(i.get("founded"), int) and i["founded"] <= 1975 for i in seed["institutions"])
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
    claim_ids = {c["id"] for c in seed["claims"]}
    assert claim_ids == {f"sj:claim:{k}" for k in ("harbor-war-1946", "moretti-schism-1958", "vannucci-split-1967",
                                                   "dock-strike-massacre-1973", "concrete-purge-1974")}
    assert "1977" not in json.dumps({k: seed[k] for k in ("places", "institutions", "persons", "claims")})
    assert seed["processes"] == []
    starlight = next(i for i in seed["institutions"] if i["name"] == "The Starlight Cabaret and Lounge")
    assert starlight["founded"] <= 1975 and "disco" not in starlight["notes"].replace("not a disco", "")

    # Names match sex, drawn from the package's pools; women are a clear minority and not in formal rank.
    groups = json.loads(pkg.data["names"].read_text(encoding="utf-8"))["groups"]
    male_names = {n for g in groups.values() for n in g["male"]}
    female_names = {n for g in groups.values() for n in g["female"]}
    extra_male = {"Rocco", "Aurelio", "Ignazio", "Rico", "Umberto", "Nicolo", "Agostino", "Corrado", "Cesare", "Pasquale", "Gennaro",
                  "Dante", "Arkady", "Declan", "Brendan", "Liam", "Gino", "Giuseppe", "Carmine", "Dominic", "Lorenzo", "Salvatore",
                  "Sol", "Vincent", "Darius", "Marvin", "Hector", "Harrison", "Gordon", "Roland", "Roy", "Walter", "Marcus", "Arthur",
                  "Eugene", "Leo", "Jackie", "Johnny", "Paul", "Carlo", "Louis", "Gerald", "Harold", "Edward", "Dennis", "Thomas",
                  "Patrick", "Martin", "Anthony", "Raymond", "Francis", "Michael", "Matteo", "Pietro", "Enzo", "John"}
    extra_female = {"Concetta", "Teresa", "Lucia", "Valerie", "Judith", "Maureen", "Margaret"}
    for p in seed["persons"]:
        given = p["name"].split()[0]
        assert p["demographic_sex"] in ("male", "female"), p["name"]
        if p["demographic_sex"] == "male":
            assert given in male_names | extra_male and given not in female_names - male_names, p["name"]
        else:
            assert given in female_names | extra_female and given not in male_names - female_names, p["name"]
    women = [p for p in seed["persons"] if p["demographic_sex"] == "female"]
    assert 0.05 <= len(women) / len(seed["persons"]) <= 0.15, len(women)
    assert not [w["name"] for w in women if FORMAL_POWER.search(w["role"])], "a woman holds formal power"
    assert meta["counts"]["women"] == len(women)
    sexes = {p["id"]: p["demographic_sex"] for p in seed["persons"]}
    for f in families:
        leaders = f["continuity_core"]["leadership_ids"]
        assert leaders and all(sexes[l] == "male" for l in leaders)
    underworld = [p for p in seed["persons"] if re.match(r"(Boss|Underboss|Capo|Consigliere|Soldier)\b", p["role"])]
    assert len(underworld) >= 20 and all(p["demographic_sex"] == "male" for p in underworld)

    # Money comes from prices_1975.json.
    prices = {e["key"]: e for e in json.loads(pkg.data["prices"].read_text(encoding="utf-8"))["saint_jude_estimates"]}
    valued = 0
    for i in seed["institutions"]:
        v = i["economic_state"].get("valuation_1975")
        if v:
            valued += 1
            e = prices[v["price_key"]]
            assert (v["low"], v["high"], v["unit"]) == (e["low"], e["high"], e["unit"]), i["name"]
    assert valued >= 20

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
