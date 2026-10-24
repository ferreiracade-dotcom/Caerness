"""Build worlds/saintjude/seed.json (the 1975 starting snapshot) from tools/saintjude_seed_data.py.

Authority is the Saint Jude Setting Bible (Index and Parts I to VI). Every named person is an Example.

Usage: python tools/build_saintjude_seed.py [--check]

Deterministic: ids are stable, lists are sorted by id, birth offsets come from a hash of the person's key.
--check exits non-zero if the file on disk differs from what the data module would produce.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import saintjude_seed_data as D  # noqa: E402
from engine import world_calendar  # noqa: E402
from engine.world_package import load_package  # noqa: E402

SEED_PATH = ROOT / "worlds" / "saintjude" / "seed.json"
PACKAGE = "saintjude"


def pid(key: str) -> str:
    return f"sj:person:{key}"


def plid(key: str) -> str:
    return f"sj:place:{key}"


def iid(key: str) -> str:
    return f"sj:institution:{key}"


def birth_offset(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 365


def _prices() -> dict:
    """Part VI 4.4 trade rows of prices_1975.json, by row key."""
    pkg = load_package(PACKAGE)
    data = json.loads(pkg.data["prices"].read_text(encoding="utf-8"))
    return {r["key"]: r for r in data["rows"]}


def _trade_profile(prices: dict, trade: str) -> dict:
    sales, net = prices[f"trade_{trade}_sales"], prices[f"trade_{trade}_net_pct"]
    return {"trade": trade, "sales_a_year": {"default": sales["default"], "range": sales["range"], "unit": sales["unit"]},
            "net_pct_of_sales": {"default": net["default"], "range": net["range"]},
            "source": f"worlds/saintjude/prices_1975.json trade_{trade}_sales and trade_{trade}_net_pct (Part VI 4.4, Design; the nearest trade)"}


def _check_refs() -> None:
    places = {p[0] for p in D.PLACES}
    people = {p["key"] for p in D.PERSONS}
    insts = {i["key"] for i in D.INSTITUTIONS}
    for key, _, _, parent, _ in D.PLACES:
        assert parent is None or parent in places, (key, parent)
    for a, b, _, _ in D.ROUTES:
        assert a in places and b in places, (a, b)
    for i in D.INSTITUTIONS:
        assert i["place"] in places, i["key"]
        assert i["founded"] is None or i["founded"] <= 1975, i["key"]
        for k in i["owners"] + i["leaders"]:
            assert k in people, (i["key"], k)
    for p in D.PERSONS:
        assert p["loc"] in places, p["key"]
        for k in p["insts"]:
            assert k in insts, (p["key"], k)
        assert p["sex"] in ("male", "female"), p["key"]
    for t, a, b, _ in D.RELATIONSHIPS:
        assert a in people and b in people, (t, a, b)
    for c in D.CLAIMS:
        for k in c[3]:
            assert k in people, c[0]
        for k in c[4] + c[5]:
            assert k in places, c[0]
    assert len({p["key"] for p in D.PERSONS}) == len(D.PERSONS)
    assert len({p["name"] for p in D.PERSONS}) == len(D.PERSONS)
    assert len({i["name"] for i in D.INSTITUTIONS}) == len(D.INSTITUTIONS)
    assert len({p[1] for p in D.PLACES}) == len(D.PLACES)


def build() -> dict:
    _check_refs()
    pkg = load_package(PACKAGE)
    prices = _prices()

    # Everyone belongs to the institutions they own or lead, so ownership never floats free of membership.
    memberships: dict[str, set[str]] = {p["key"]: set(p["insts"]) for p in D.PERSONS}
    for i in D.INSTITUTIONS:
        for k in i["owners"] + i["leaders"]:
            memberships[k].add(i["key"])
    members_of: dict[str, list[str]] = {i["key"]: [] for i in D.INSTITUTIONS}
    for k, s in memberships.items():
        for ik in s:
            members_of[ik].append(k)

    places = []
    for key, name, kind, parent, notes in sorted(D.PLACES, key=lambda x: x[0]):
        places.append({
            "id": plid(key), "name": name, "kind": kind, "state": None, "parent": None, "notes": notes,
            "canon_status": "working", "coordinates": None, "provenance": ["Saint Jude Setting Bible, Parts I to VI"],
            "parent_ref": plid(parent) if parent else None, "identity_certainty": "ESTABLISHED_IDENTITY",
            "placement_certainty": "WORKING_RELATIVE", "coordinate_status": "OPEN_NOT_REQUIRED",
            "source_anchor": "Saint Jude Setting Bible Part I 3.2, 5 and 6",
        })

    name_of = {p[0]: p[1] for p in D.PLACES}
    routes = []
    for a, b, ordinary, courier in D.ROUTES:
        routes.append({
            "id": f"sj:route:{a}--{b}", "from_name": name_of[a], "to_name": name_of[b], "ordinary": ordinary,
            "courier": courier, "cultivated_light": None, "status": "working", "coordinates_required": False,
            "provenance": "Working estimate; the bible gives no travel times",
        })
    routes.sort(key=lambda r: r["id"])

    institutions = []
    for i in sorted(D.INSTITUTIONS, key=lambda x: x["key"]):
        econ = {"resource_band": {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}[i["band"]], "liquidity": i["liquidity"],
                "asset_base": i["asset_base"], "debt_state": "NO_SPECIFIC_DEBT_SEEDED",
                "shock_buffer": {"HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}[i["band"]],
                "canon_status": "ASSUMPTION"}
        if i["trade"]:
            econ["trade_profile_1975"] = _trade_profile(prices, i["trade"])
        n = len(members_of[i["key"]])
        institutions.append({
            "id": iid(i["key"]), "name": i["name"], "category": i["category"], "current": None, "state": "Saint Jude",
            "status": "active", "place": name_of[i["place"]], "seeded_members": sorted(pid(k) for k in members_of[i["key"]]),
            "notes": i["notes"], "founded": i["founded"], "founded_basis": i["founded_basis"], "canon_tag": i["tag"],
            "owner_refs": sorted(pid(k) for k in i["owners"]),
            "provenance": [f"Saint Jude Setting Bible ({i['tag']}); founded: {i['founded_basis']}"], "place_ref": plid(i["place"]), "place_resolution": "KNOWN_WORKING",
            "continuity_core": {
                "load_bearing": bool(i["leaders"] or i["owners"]), "membership_seed_count": n,
                "membership_scale_band": "STRUCTURAL_ONLY" if n == 0 else ("SMALL" if n < 4 else "MEDIUM"),
                "leadership_ids": sorted(pid(k) for k in i["leaders"]), "owner_ids": sorted(pid(k) for k in i["owners"]),
                "succession_rule": "UNSPECIFIED_BY_CANON", "pipeline_health": "BASELINE_STABLE_TEST_ASSUMPTION",
                "active_disputes": [], "place_ref": plid(i["place"]),
                "provenance": "Runtime scaffolding only; the Saint Jude Setting Bible is the authority.",
            },
            "economic_state": econ,
        })

    persons = []
    for p in sorted(D.PERSONS, key=lambda x: x["key"]):
        offset = birth_offset(p["key"])
        birth_day = -(p["age"] * 365 + offset)
        assert (-birth_day) // 365 == p["age"]
        bd = world_calendar.birth_date_for(pkg, birth_day)
        pid_ = pid(p["key"])
        why = {"seat": "Part III 4.6 suggested starting seat", "carried": "old codex cast carried as an Example",
               "added": "added Example for institutional structure"}[p["source"]]
        persons.append({
            "id": pid_, "name": p["name"], "life_status": "living", "age": p["age"], "core_state": None,
            "current": p["current"], "long_road": False, "institutions": sorted(iid(k) for k in memberships[p["key"]]),
            "state_sphere": None, "role": p["role"], "training_provenance_text": None, "public_identity_text": p["public"],
            "demographic_sex": p["sex"], "canon_status": "working", "canon_tag": "Example", "resolution_seed": "TRACKED",
            "provenance": [f"Example (replaceable at seed): {why}"],
            "strategic_hint": p["tier"] != "DORMANT",
            "runtime_v1_1": {
                "location_status": "KNOWN_WORKING", "current_location_ref": plid(p["loc"]), "residence_ref": plid(p["loc"]),
                "location_basis": ["primary placement"], "resolution_tier": p["tier"], "resolution_reason": "named persistent seed",
            },
            "age_basis": "opening_age", "birth_day": birth_day, "birth_date": bd,
        })

    relationships = []
    for n, (typ, a, b, note) in enumerate(sorted(D.RELATIONSHIPS, key=lambda r: (r[0], r[1], r[2])), 1):
        relationships.append({"type": typ, "from": pid(a), "to": pid(b), "note": note, "provenance": "Saint Jude snapshot"})

    households = [{
        "id": "sj:household:giuseppe-lucia-vannucci", "member_refs": [pid("giuseppe-vannucci"), pid("lucia-vannucci")],
        "place_ref": plid("oakridge"), "basis": "explicit spouse relationship", "status": "KNOWN_PARTIAL",
        "marriage_or_kinship_state": "EXPLICIT_RELATIONS_ONLY", "economic_state": "NOT_SEPARATELY_QUANTIFIED",
    }]

    targets = []
    for i in sorted(D.INSTITUTIONS, key=lambda x: x["key"]):
        if i["key"] in ("sabatini", "pellegrino", "ferrante", "vannucci", "charlestown", "eastside-combine", "russians", "iron-horsemen"):
            targets.append({
                "institution_ref": iid(i["key"]), "opening_named_living": len(members_of[i["key"]]),
                "minimum_named_layer": 0 if i["key"] == "russians" else 3,
                "crystallization_rule": "ONLY_IF_SIMULATION_NEEDS_A_PERSISTENT_ACTOR_AND_CANON_CONSTRAINTS_EXIST",
            })

    claims = []
    for key, typ, text, subjects, origin, known, carriers, conf, prov in sorted(D.CLAIMS, key=lambda c: c[0]):
        claims.append({
            "id": f"sj:claim:{key}", "type": typ, "subjects": [pid(k) for k in subjects], "text": text,
            "origin_place_refs": [plid(k) for k in origin], "known_at_opening": [plid(k) for k in known],
            "carrier_types": carriers, "confidence": conf, "provenance": prov, "canon_status": "CANONICAL_HISTORY",
        })

    women = sum(1 for p in D.PERSONS if p["sex"] == "female")
    meta = {
        "title": "Saint Jude Initial World-State Seed (1975 snapshot)",
        "status": "starting snapshot built from the Saint Jude Setting Bible (October 2026); for owner review",
        "source_authority": ["Saint Jude Setting Bible: Index and Parts I to VI (worlds/saintjude/bible.md is its packaged form)"],
        "authority_rule": "The bible outranks this seed. Campaign history may add facts but may not rewrite setting canon.",
        "opening_date": "1975-01-01", "calendar_rule": "Gregorian; day 0 is Wednesday 1 January 1975; birth_day is authoritative arithmetic and birth_date its rendering.",
        "example_rule": "Every named person is an Example (Part III 4.6, Part V 0.2) with canon_tag 'Example' and may be replaced; Fixed history in the claims names no person, only roles and events.",
        "families_rule": "The four families are Sabatini, Pellegrino, Ferrante and Vannucci (Part III 0). Women are never made (Part I 12.2).",
        "open_offices_rule": "Offices and institutions are seeded; the names of their holders are Open (Part I 15.1, Part II 10, Index 7) and are not seeded.",
        "no_pressures_rule": "No pressures, secrets, deadlines or plot hooks are stored; motives are ordinary traits.",
        "open_office_holders_not_seeded": D.OPEN_OFFICE_HOLDERS,
        "bible_silent": D.BIBLE_SILENT,
        "removed_from_old_seed": [{"item": a_, "handling": b_} for a_, b_ in D.REMOVED_FROM_OLD_SEED],
        "judgement_calls": D.JUDGEMENT_CALLS,
        "counts": {"persons": len(persons), "women": women, "places": len(places), "institutions": len(institutions),
                   "claims": len(D.CLAIMS), "routes": len(routes)},
    }
    return {
        "meta": meta, "places": places, "routes": routes, "institutions": institutions, "persons": persons,
        "relationships": relationships, "households": households, "cohorts": [],
        "latent_population_controls": {"rule": "Named people are a layer over a much larger unnamed population; unnamed people become named only when the simulation needs a persistent actor.",
                                        "named_layer_targets": targets},
        "claims": claims, "processes": [],
    }


def dumps(seed: dict) -> str:
    return json.dumps(seed, indent=1, ensure_ascii=False) + "\n"


def main() -> int:
    text = dumps(build())
    if "--check" in sys.argv:
        ok = SEED_PATH.exists() and SEED_PATH.read_text(encoding="utf-8") == text
        print("seed.json up to date" if ok else "seed.json differs from the data module")
        return 0 if ok else 1
    SEED_PATH.write_text(text, encoding="utf-8", newline="\n")
    s = json.loads(text)["meta"]["counts"]
    print(f"wrote {SEED_PATH} {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
