"""A new protagonist: the GM and the player design the whole person; the engine only vetoes contradictions (engine/veto.py),
then materialises the proposal through existing paths and fills what was left open with a plausible lived past.

Everything drawn is deterministic from (world seed, draw) and insert-only; people are revealed from the place's own
population or its latent kin, never conjured, so the population never grows (population_delta 0).
"""
from __future__ import annotations

import json
import random
import re
import sqlite3
from typing import Any

from . import ledger, veto
from .veto import Contradiction

SOURCE = {"source": "new_character", "not_canon": True}
_STAGE_CLASS = {"First": "first", "Temper": "temper", "Third": "third", "Breach": "breach", "Fifth": "fifth"}


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _rng(key: str) -> random.Random:
    return random.Random(key)


def _age(conn, aid: int, day: int | None = None) -> int:
    day = _day(conn) if day is None else day
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
    return int((day - r[0]) // 365) if r and r[0] is not None else 0


def _name(conn, aid: int) -> str:
    return str(conn.execute("SELECT name FROM actors WHERE id=?", (aid,)).fetchone()[0])


def _settlement(conn, loc: int) -> int:
    s = veto.settlement_of(conn, loc)
    return s if s is not None else loc


def _low_attention(conn, aid: int, day: int, reason: str) -> None:
    from .continuity import set_resolution
    from .resolution_controller import _sync_sim_tier
    set_resolution(conn, "actor", aid, "STRUCTURAL", day=day, reason=reason, source_kind="engine", review_cadence_days=365,
                   next_review_day=day + 365, metadata=dict(SOURCE))
    _sync_sim_tier(conn, aid, "STRUCTURAL", day)


def _mark_actor(conn, aid: int, patch: dict) -> None:
    conn.execute("UPDATE actor_life_profiles SET metadata_json=json_patch(COALESCE(metadata_json,'{}'),?) WHERE actor_id=?",
                 (json.dumps({**SOURCE, **patch}, sort_keys=True), aid))


# ---------------------------------------------------------------- revealing kin

def _reveal_person(conn, *, key: str, sex: str, age: float, loc: int, family: str, day: int, reason: str, hearth: bool) -> int:
    """Reveal an already-existing relative through the latent-person route, at low attention, named for his sex."""
    from .cultivation import VEINBORN_SHARE, calibrate_revealed_profile
    from .demographic_sex import FEMALE_GIVEN_NAMES, MALE_GIVEN_NAMES
    from .health import configure_health_profile
    from .resolution_controller import _materialize_latent_person
    rng = _rng(f"reveal:{key}")
    given = sorted(FEMALE_GIVEN_NAMES if sex == "female" else MALE_GIVEN_NAMES)
    name = None
    for _ in range(400):
        cand = f"{rng.choice(given)} {family}"
        if not conn.execute("SELECT 1 FROM actors WHERE name=?", (cand,)).fetchone():
            name = cand
            break
    if name is None:
        raise Contradiction("no free name for a relative of that family")
    birth = day - int(round(age * 365.0)) - rng.randrange(365)
    cons = {"name": name, "birth_day": birth, "demographic_sex": sex, "open_core": rng.random() < VEINBORN_SHARE[bool(hearth)], "stage": None}
    cur = conn.execute(
        """INSERT INTO latent_entities(latent_kind,archetype,location_id,count_estimate,constraints_json,historical_context_json,status,created_day,updated_day,notes)
           VALUES ('person','kin',?,1,?,?,'latent',?,?,?)""",
        (loc, json.dumps(cons), json.dumps({**SOURCE, "basis": reason}), day, day, "Relative of a new protagonist; existed before, previously undescribed."))
    latent = conn.execute("SELECT * FROM latent_entities WHERE id=?", (int(cur.lastrowid),)).fetchone()
    aid = _materialize_latent_person(conn, latent, day, 0.0, {"kin_of_protagonist": 1.0})
    if aid is None:
        raise Contradiction("a relative could not be revealed")
    conn.execute("UPDATE latent_entities SET status='crystallized',crystallized_entity_kind='actor',crystallized_entity_id=? WHERE id=?", (aid, int(latent["id"])))
    _low_attention(conn, aid, day, reason)
    configure_health_profile(conn, aid, longevity_class="ordinary")
    calibrate_revealed_profile(conn, aid, active=False)
    _mark_actor(conn, aid, {"relation_reason": reason})
    return aid


def _kin(conn, a: int, b: int, kind: str, since: int, key: str) -> None:
    """parent (a is parent of b) | sibling; with the opening's directed tie values."""
    from .household_life import add_kinship
    from .opening_family import _seed_pair
    if kind == "parent":
        add_kinship(conn, a, b, "parent", reciprocal_kind="child")
    else:
        add_kinship(conn, a, b, "sibling", reciprocal_kind="sibling")
    conn.execute("UPDATE kinship_links SET started_day=? WHERE (actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)", (since, a, b, b, a))
    _seed_pair(conn, a, b, "kin", key=key, started_day=since)


def _family_surname(name: str) -> str:
    from .household_life import _family_name
    return _family_name(name) or name.split()[-1]


# ---------------------------------------------------------------- layers

def _family(conn, aid: int, *, key: str, proposal: dict, day: int, loc: int, sex: str, age: int) -> dict:
    from .opening_family import resolve_family_for, reveal_latent_adult_child
    fam = proposal.get("family") or {}
    cons: dict[str, Any] = {}
    sp = fam.get("spouse")
    text = " ".join(str(v) for v in ([sp] if not isinstance(sp, list) else sp)).lower() if sp is not None else ""
    if age < 16:
        cons = {"marital": "never_married", "children_max": 0}
    elif "widow" in text:
        cons["marital"] = "widowed"
    elif sp is not None and any(w in text for w in ("none", "unmarried", "single", "bachelor", "unwed")):
        cons["marital"] = "never_married"
    elif sp is not None and text:
        cons["marital"] = "married"
    ch = fam.get("children")
    if ch is not None and age >= 16:
        import re
        words = {"no": 0, "none": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
        blob = str(ch).lower()
        m = re.search(r"\d+", blob)
        n = int(m.group()) if m else next((v for w, v in words.items() if re.search(rf"\b{w}\b", blob)), None)
        if n is not None:
            cons["children_min"], cons["children_max"] = n, n
    out = {"spouse": None, "children": []}
    if age >= 16:
        try:
            outcome = resolve_family_for(conn, aid, key=f"{key}:family", day=day, constraints=cons or None)
        except Contradiction as e:
            if cons.get("marital") == "widowed":
                raise Contradiction(f"widowed at {age} is improbable here (marriage and mortality rates make it very unlikely); "
                                    "adjust the age or the family") from e
            raise
        meta = json.loads(conn.execute("SELECT metadata_json FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()[0] or "{}")
        out["spouse"] = meta.get("spouse_actor_id")
        for i in range(3):
            c = reveal_latent_adult_child(conn, aid, reason="new protagonist's child", day=day, min_age=0)
            if c is None:
                break
            out["children"].append(c)
            hh = conn.execute("SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()[0]
            if hh is not None and _age(conn, c, day) < 16:
                from .civilian import add_household_member
                add_household_member(conn, int(hh), c, role="child", authority=5, dependency=80)
                conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (hh, c))
            if out["spouse"] is not None and not conn.execute("SELECT 1 FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind='parent'", (out["spouse"], c)).fetchone():
                from .household_life import add_kinship
                add_kinship(conn, int(out["spouse"]), c, "parent", reciprocal_kind="child")
    return out


def _origin(conn, aid: int, *, key: str, proposal: dict, day: int, loc: int, sex: str, age: int, family_name: str, hearth: bool) -> dict:
    from .health import childhood_circumstance
    from .opening_family import draw_origin_family
    mult, _ = childhood_circumstance(conn, parent_ids=[aid], location_id=loc)
    o = draw_origin_family(f"{key}:origin", age=age, sex=sex, hearth=hearth, childhood_multiplier=mult)
    fam = proposal.get("family") or {}
    parents_text = str(fam.get("parents", "")).lower()
    if any(w in parents_text for w in ("dead", "orphan", "died")):
        o["mother"]["alive"] = o["father"]["alive"] = False
    rng = _rng(f"{key}:originreveal")
    revealed: dict[str, Any] = {"parents": [], "siblings": []}
    counts = {"parents_dead": 0, "parents_unnamed": 0, "siblings_alive": 0, "siblings_dead": 0}
    birth = day - age * 365
    people: dict[str, int] = {}
    for who, sx in (("father", "male"), ("mother", "female")):
        p = o[who]
        if not p["alive"]:
            counts["parents_dead"] += 1
        elif rng.random() < 0.7:
            fam_name = family_name if who == "father" else _rng(f"{key}:{who}:fam").choice(
                ("Ashby", "Marrow", "Tillet", "Penhall", "Corvane", "Hale", "Dunmere", "Raske", "Wend", "Lorne", "Brask", "Ostrey"))
            people[who] = _reveal_person(conn, key=f"{key}:{who}", sex=sx, age=p["age_now"], loc=loc, family=fam_name, day=day,
                                         reason="parent of a new protagonist", hearth=hearth)
            _kin(conn, people[who], aid, "parent", birth, f"{key}:{who}")
            revealed["parents"].append(people[who])
        else:
            counts["parents_unnamed"] += 1
    if "father" in people and "mother" in people:
        from .household_life import create_union
        uid = create_union(conn, people["father"], people["mother"],
                           create_new_household_name=f"Household of {_name(conn, people['father'])} and {_name(conn, people['mother'])}")
        start = day - int(max(1, o["mother"]["age_now"] - age - 18) * 365)
        conn.execute("UPDATE household_unions SET started_day=? WHERE id=?", (start, uid))
        conn.execute("UPDATE kinship_links SET started_day=? WHERE kin_kind='spouse' AND actor_a_id IN (?,?) AND actor_b_id IN (?,?)",
                     (start, people["father"], people["mother"], people["father"], people["mother"]))
    for i, s in enumerate(o["siblings"]):
        if not s["alive"]:
            counts["siblings_dead"] += 1
        elif rng.random() < 0.7:
            sid = _reveal_person(conn, key=f"{key}:sib{i}", sex=s["sex"], age=s["age_now"], loc=loc, family=family_name, day=day,
                                 reason="sibling of a new protagonist", hearth=hearth)
            _kin(conn, aid, sid, "sibling", day - int(min(s["age_now"], age) * 365), f"{key}:sib{i}")
            for par in people.values():
                _kin(conn, par, sid, "parent", day - int(s["age_now"] * 365), f"{key}:{par}:{sid}")
            revealed["siblings"].append(sid)
        else:
            counts["siblings_alive"] += 1
    hh = conn.execute("SELECT household_id FROM household_members WHERE actor_id=? AND status='active' ORDER BY household_id LIMIT 1",
                      (people.get("mother") or people.get("father") or 0,)).fetchone()
    if hh is not None:
        for sid in revealed["siblings"]:
            if _age(conn, sid, day) < 16 and not conn.execute("SELECT 1 FROM household_members WHERE actor_id=? AND status='active'", (sid,)).fetchone():
                from .civilian import add_household_member
                add_household_member(conn, int(hh[0]), sid, role="child", authority=5, dependency=80)
                conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (int(hh[0]), sid))
        if age < 16:  # a child lives in his parents' house
            from .civilian import add_household_member
            add_household_member(conn, int(hh[0]), aid, role="child", authority=5, dependency=80)
            conn.execute("UPDATE actor_life_profiles SET current_household_id=?,origin_household_id=? WHERE actor_id=?", (int(hh[0]), int(hh[0]), aid))
    _mark_actor(conn, aid, {"origin_family": counts})
    return {**counts, "revealed_parents": len(revealed["parents"]), "revealed_siblings": len(revealed["siblings"]), "people": people}


def _ties(conn, aid: int, *, key: str, day: int, loc: int, age: int, cat: str, affiliation: dict | None, also: list[int] | None = None) -> dict:
    from .opening_family import _seed_pair
    from .person_ecology import resolve_background_person
    s = _settlement(conn, loc)
    rng = _rng(f"{key}:ties")
    made = {"neighbours": 0, "colleagues": 0, "mentor": 0}
    lo = max(18 if age >= 18 else 0, age - 15)
    for i in range(rng.randint(4, 6)):
        n = resolve_background_person(conn, reason="neighbour of a new protagonist", demand_kind="new_character", location_id=s,
                                      min_age=lo, max_age=age + 15, allow_elsewhere=False, pick_seed=f"{key}:nb{i}",
                                      subtype="resolved_neighbour")
        if n is None:
            break
        _low_attention(conn, n, day, "neighbour of a new protagonist")
        if _seed_pair(conn, aid, n, "acquaintance", key=f"{key}:nb{i}", started_day=day - rng.randint(200, 3000)):
            made["neighbours"] += 1
    colleagues: list[int] = []
    if affiliation:
        if affiliation["kind"] == "institution":
            colleagues = [int(r[0]) for r in conn.execute(
                "SELECT member_actor_id FROM institution_memberships WHERE institution_actor_id=? AND status='active' AND member_actor_id<>? ORDER BY member_actor_id LIMIT 3",
                (affiliation["id"], aid))]
        elif affiliation["kind"] == "outfit":
            colleagues = [int(r[0]) for r in conn.execute(
                """SELECT actor_id FROM underworld_personnel WHERE organization_id=? AND status='active' AND actor_id<>?
                   ORDER BY CASE role_kind WHEN 'underboss' THEN 0 WHEN 'accountant' THEN 1 WHEN 'lieutenant' THEN 2 WHEN 'fixer' THEN 3 ELSE 4 END,
                   actor_id LIMIT 4""", (affiliation["id"], aid))]
    for x in also or []:
        if x not in colleagues and x != aid:
            colleagues.append(int(x))
    for j, c in enumerate(colleagues):
        if _seed_pair(conn, aid, c, "colleague", key=f"{key}:col{j}", started_day=day - rng.randint(100, 1500)):
            made["colleagues"] += 1
    if age >= 28:
        m = resolve_background_person(conn, reason="mentor of a new protagonist", demand_kind="new_character", location_id=s,
                                      occupation_domains=(cat,), min_age=age + 12, max_age=age + 35, allow_elsewhere=False,
                                      pick_seed=f"{key}:mentor", subtype="resolved_mentor")
        if m is not None:
            _low_attention(conn, m, day, "mentor of a new protagonist")
            start = day - int(rng.randint(8, max(9, age - 14)) * 365)
            conn.execute("""INSERT OR IGNORE INTO teaching_relationships(teacher_actor_id,student_actor_id,relation_kind,domain_key,responsibility,start_day,end_day,status,notes)
                            VALUES (?,?, 'mentor',?,50,?,?,'ended','Taught the trade; this was before the story opens.')""",
                         (m, aid, cat, start, start + 365 * 3))
            _seed_pair(conn, aid, m, "teaching", key=f"{key}:mentor", started_day=start, a_role="student", b_role="teacher")
            made["mentor"] = 1
    return made


_APT = {"merchant": "economic_aptitude", "clerk": "economic_aptitude", "physician": "medical_aptitude", "teacher": "teaching_aptitude",
        "criminal": "criminal_familiarity", "soldier": "command_aptitude"}
_WORK_PHRASE = {"labor": "hard labour", "artisan": "a craft", "artist": "the arts", "clerk": "clerking", "criminal": "the life outside the law",
                "hospitality": "hospitality work", "merchant": "trade", "physician": "healing", "soldier": "soldiering",
                "teacher": "teaching", "transport": "the carrying trades"}
_START = {"labor": 14, "hospitality": 14, "clerk": 16, "merchant": 16, "soldier": 18, "criminal": 18}


def _competence(conn, aid: int, cat: str, age: int) -> float:
    from .education import _set_competence_floor
    prof = conn.execute("SELECT * FROM background_person_profiles WHERE actor_id=?", (aid,)).fetchone()
    apt = float(prof[_APT[cat]]) if prof is not None and cat in _APT else 50.0
    years = max(0, age - _START.get(cat, 16))
    score = min(85, round(25 + 1.6 * min(years, 25) + 0.3 * (apt - 50)))
    _set_competence_floor(conn, aid, "commerce" if cat == "merchant" else cat, score, source_kind="career")
    return float(score)


def _sexword(conn, aid: int) -> str:
    return str(conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()[0])


def _knowledge(conn, aid: int, *, key: str, day: int, loc: int, cat: str, kin: list[int]) -> int:
    from .manners_canon import MANNERS, culture_key
    they = "he" if _sexword(conn, aid) == "male" else "she"
    rng = _rng(f"{key}:knowledge")
    s = _settlement(conn, loc)
    facts: list[tuple[str, str]] = []
    for r in conn.execute("SELECT l.id,l.name FROM locations l WHERE l.parent_location_id=? AND l.kind LIKE '%district%'", (s,)):
        facts.append((f"district:{r['id']}", f"{r['name']} is a quarter of {_loc(conn, s)}."))
    for r in conn.execute(
            """SELECT z.id,z.name zname,o.id oid,o.name oname,a.name boss FROM underworld_zones z
               JOIN underworld_zone_claims c ON c.zone_id=z.id AND c.claim_kind='controller' AND c.status='active'
               JOIN underworld_organizations o ON o.id=c.organization_id LEFT JOIN actors a ON a.id=o.current_leader_actor_id
               WHERE z.city_location_id=?""", (s,)):
        facts.append((f"zone:{r['id']}", f"{r['oname']} holds {r['zname']}" + (f"; {r['boss']} answers for it." if r["boss"] else ".")))
    for r in conn.execute("SELECT id,name,owner_actor_id FROM civilian_enterprises WHERE location_id=? AND status IN ('active','strained') AND name NOT LIKE '[%' "
            "AND metadata_json NOT LIKE '%STRUCTURAL%' AND metadata_json NOT LIKE '%aggregate%'", (s,)):
        owner = f", kept by {_name(conn, r['owner_actor_id'])}" if r["owner_actor_id"] else ""
        facts.append((f"business:{r['id']}", f"{r['name']} trades here{owner}."))
    for r in conn.execute("SELECT id,name FROM actors WHERE actor_type='institution' AND status='active' AND current_location_id=?", (s,)):
        facts.append((f"institution:{r['id']}", f"{r['name']} stands in {_loc(conn, s)}."))
    rng.shuffle(facts)
    facts = facts[:rng.randint(12, 25)]
    for k in kin:
        facts.append((f"person:{k}", f"{_name(conn, k)} is someone {they} know{'s' if they != 'they' else ''} well."))
    facts.append(("manners:place", MANNERS[culture_key(conn, loc)]))
    n = 0
    for fk, text in facts:
        n += conn.execute("INSERT OR IGNORE INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,truth_event_id,learned_day) VALUES (?,?,?,?,NULL,?)",
                          (aid, f"lived:{fk}", text, round(rng.uniform(0.6, 0.9), 2), -rng.randint(30, 2500))).rowcount
    return n


def _loc(conn, lid: int) -> str:
    return str(conn.execute("SELECT name FROM locations WHERE id=?", (lid,)).fetchone()[0])


def _memories(conn, aid: int, *, key: str, day: int, loc: int, cat: str, age: int, origin: dict, kin: list[int]) -> int:
    rng = _rng(f"{key}:memories")
    items = [("lived:home", f"Grew up in {_loc(conn, _settlement(conn, loc))}; the streets and their people are familiar.", .5)]
    if age >= 16:
        items.append(("lived:trade", f"Took up {_WORK_PHRASE.get(cat, 'a trade')} young and has kept at it.", .6))
    if origin.get("parents_dead") == 2:
        items.append(("lived:orphaned", "Both parents are dead; their loss shaped the years after.", .8))
    elif origin.get("parents_dead"):
        items.append(("lived:parent_lost", "Lost a parent while still young enough to remember it clearly.", .75))
    if kin:
        items.append(("lived:kin", f"Family close by: {_name(conn, kin[0])} among them.", .6))
    n = 0
    for mk, text, sig in items[:5]:
        n += conn.execute("""INSERT OR IGNORE INTO actor_memories(actor_id,memory_key,summary,valence,significance,source_kind,source_id,created_day,last_reinforced_day)
                             VALUES (?,?,?,?,?,'admin',0,?,?)""", (aid, mk, text, round(rng.uniform(-.2, .5), 2), sig, day - rng.randint(60, 2000), day)).rowcount
    return n


def _standing(conn, aid: int, *, cat: str, age: int, holds: float) -> None:
    from . import reputation
    years = max(0, age - 16)
    pub = min(14.0, 0.25 * years + 2.0 * holds)
    reputation.adjust(conn, "actor", aid, "public", pub, metadata=dict(SOURCE))
    reputation.adjust(conn, "actor", aid, "professional", min(18.0, 0.3 * years), metadata=dict(SOURCE))
    reputation.adjust(conn, "actor", aid, "commerce" if cat == "merchant" else cat, min(20.0, 0.35 * years), metadata=dict(SOURCE))


def fill_lived_past(conn: sqlite3.Connection, aid: int, *, key: str, proposal: dict) -> dict:
    """Fill what the proposal left open: family, origin family, ties, competence, knowledge, memories, standing.
    Insert-only and idempotent: a second call adds nothing. Returns counts and a words digest."""
    prof = conn.execute("SELECT metadata_json FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
    meta = json.loads(prof[0] or "{}")
    if meta.get("lived_past_key"):
        return {"already": True, "digest": meta.get("lived_past_digest", {})}
    day = _day(conn)
    row = conn.execute("""SELECT a.name,COALESCE(a.home_location_id,a.current_location_id) loc,lp.demographic_sex sex
                          FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?""", (aid,)).fetchone()
    loc, sex, age = int(row["loc"]), str(row["sex"]), _age(conn, aid, day)
    cat = veto.categorise(proposal.get("work"), proposal.get("category"))
    from .cultivation import location_in_hearth
    pr = conn.execute("SELECT current_location_id FROM background_person_profiles WHERE actor_id=?", (aid,)).fetchone()
    home_loc = int(pr[0]) if pr and pr[0] is not None else loc
    if _settlement(conn, home_loc) == _settlement(conn, loc):
        home_loc = loc  # not from elsewhere: he grew up where he lives
    hearth = location_in_hearth(conn, _settlement(conn, home_loc))
    family_name = _family_surname(str(row["name"]))
    aff = proposal.get("_affiliation")  # resolved by create_protagonist: {"kind","id"} of a body he belongs to
    # a household he already heads or belongs to is his home: a spouse joins it rather than a new house being formed around him
    home = conn.execute("SELECT household_id FROM household_members WHERE actor_id=? AND status='active' ORDER BY (role='head') DESC, household_id LIMIT 1",
                        (aid,)).fetchone()
    if home is not None:
        conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=? AND current_household_id IS NULL", (int(home[0]), aid))
    fam = _family(conn, aid, key=key, proposal=proposal, day=day, loc=loc, sex=sex, age=age)
    origin = _origin(conn, aid, key=key, proposal=proposal, day=day, loc=home_loc, sex=sex, age=age, family_name=family_name, hearth=hearth)
    ties = _ties(conn, aid, key=key, day=day, loc=loc, age=age, cat=cat, affiliation=aff, also=proposal.get("_ties_with"))
    score = _competence(conn, aid, cat, age) if age >= 14 else 0.0
    kin = [x for x in ([fam["spouse"]] if fam["spouse"] else []) + fam["children"] + list(origin["people"].values()) if x]
    nk = _knowledge(conn, aid, key=key, day=day, loc=loc, cat=cat, kin=kin)
    nm = _memories(conn, aid, key=key, day=day, loc=home_loc, cat=cat, age=age, origin=origin, kin=kin)
    _standing(conn, aid, cat=cat, age=age, holds=float(proposal.get("_holds", 0)))
    digest = {"spouse": bool(fam["spouse"]), "children": len(fam["children"]), "parents_living": origin["revealed_parents"],
              "siblings_known": origin["revealed_siblings"], "neighbours": ties["neighbours"], "colleagues": ties["colleagues"],
              "mentor": bool(ties["mentor"]), "knowledge": nk, "memories": nm}
    _mark_actor(conn, aid, {"lived_past_key": key, "lived_past_digest": digest})
    return {"already": False, "digest": digest, "competence": score}


# ================================================================ proposal -> protagonist

_VIOLENT = ("gang", "crew", "outfit", "mob", "syndicate", "thieves", "racket", "enforcer", "smuggl", "cutthroat", "bandit")
_UNIT = ("squad", "regiment", "garrison", "warband", "patrol", "captain", "platoon", "militia", "unit of")
_VICE = ("brothel", "gambl", "dice", "lend", "bookmak", "vice", "pleasure", "courtesan", "loan", "usur")
_TRADE = ("guild", "company", "firm", "house", "trading", "merchant", "clinic", "school", "workshop", "physician", "smith", "bank", "counting")
_CASH = ("cash", "savings", "coin", "purse", "money", "inheritance", "fortune", "wealth", "means", "nest egg")
_BIZ = ("shop", "inn", "tavern", "stall", "bakery", "smithy", "business", "store", "mill", "workshop", "chandl", "brewery", "farm", "stable", "market")
_RACKET = (("brothel", "brothel protection"), ("courtesan", "courtesan house leverage"), ("gambl", "illegal gaming"), ("dice", "illegal gaming"),
           ("bookmak", "unlicensed bookmaking"), ("bet", "unlicensed bookmaking"), ("lend", "high-risk debt"), ("loan", "high-risk debt"),
           ("usur", "high-risk debt"), ("stolen", "stolen goods"), ("fence", "stolen goods"), ("smuggl", "stolen goods"), ("protect", "protection collections"))
POWER_P_MALE = {"violent": 0.92, "unit": 0.85, "trade": 0.85, "vice": 0.70}
_OUTFIT_RE = re.compile(r"\b(outfit|gang|crew|band|brotherhood|syndicate|mob|ring)\b")


def _blob(v: Any) -> str:
    if isinstance(v, dict):
        return " ".join(_blob(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return " ".join(_blob(x) for x in v)
    return str(v or "")


def power_class(proposal: dict) -> str | None:
    """The sort of power role the proposal gives him (and so the male share a drawn sex follows): violent outfit, unit leader,
    trade or specialist, vice; None when he holds no power role. The shares are the owner's (92/85/85/70)."""
    aff = proposal.get("affiliation") or {}
    holdings = proposal.get("holdings") or []
    led = bool(aff and (veto._LEAD.search(str(aff.get("role") or "").lower()) or aff.get("new")))
    text = " ".join([_blob(aff), _blob(holdings), str(proposal.get("work") or "")]).lower()
    outfit = any(w in text for w in _VIOLENT)
    if not (led or outfit or any(isinstance(h, dict) and veto._LEAD.search(str(h.get("role") or "").lower()) for h in holdings)):
        return None
    for cls, words in (("violent", _VIOLENT), ("unit", _UNIT), ("vice", _VICE), ("trade", _TRADE)):
        if any(w in text for w in words):
            return cls
    return "trade" if led else None


def resolve_sex(conn, proposal: dict, key: str) -> tuple[str, bool]:
    """(sex, drawn). Stated, else implied by the name, else drawn: a power role skews male (92/85/85/70), elsewhere the population (even)."""
    if proposal.get("sex") in ("male", "female"):
        return proposal["sex"], False
    implied = veto.name_sex(proposal.get("name"), None)
    if implied:
        return implied, False
    p = POWER_P_MALE.get(power_class(proposal), 0.5)
    return ("male" if _rng(f"{key}:sex").random() < p else "female"), True


def _key(conn, proposal: dict) -> str:
    import hashlib
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    core = {k: proposal.get(k) for k in ("name", "sex", "age", "place", "work", "category", "stage", "family", "affiliation", "holdings", "ties", "from_elsewhere")}
    blob = json.dumps([seed, int(proposal.get("draw", 0) or 0), core], sort_keys=True, default=str)
    return "newchar:" + hashlib.sha1(blob.encode()).hexdigest()[:16]


def _holdings_plan(proposal: dict) -> dict:
    """Sort holdings into cash, businesses, rackets (vice under an outfit) and outfits; free text decides, the fallback is a business."""
    plan: dict[str, Any] = {"cash": 0.0, "businesses": [], "rackets": [], "outfits": []}
    aff = proposal.get("affiliation") or {}
    atext = (str(aff.get("name") or aff.get("text") or "") + " " + str(aff.get("type") or "")).lower()
    for h in proposal.get("holdings") or []:
        h = dict(h) if isinstance(h, dict) else {"kind": str(h)}
        kind = str(h.get("kind") or h.get("name") or "").lower()
        if any(w in kind for w in _CASH):
            try:
                plan["cash"] += ledger.amount_of(h.get("amount", "modest"), None)
            except ValueError:
                plan["cash"] += ledger.SCALES["modest"]
        elif _OUTFIT_RE.search(kind):
            plan["outfits"].append(h)
        elif any(w in kind for w in _VICE) or any(w in kind for w, _ in _RACKET):
            plan["rackets"].append(h)
        else:
            plan["businesses"].append(h)
    founding = bool(aff and (aff.get("new") or veto._LEAD.search(str(aff.get("role") or "").lower())))
    if founding and not plan["outfits"] and any(w in atext for w in _VIOLENT):
        plan["outfits"].append({"kind": "outfit", "name": aff.get("name") or aff.get("text"), "members": aff.get("members")})
    return plan


def create_protagonist(conn: sqlite3.Connection, proposal: dict, call_id: str, *, campaign_name: str | None = None) -> dict:
    """Preview (accept false) or create (accept true) the whole protagonist from the proposal. Deterministic from (world seed, draw,
    proposal): the preview shows exactly the person accept makes. A preview leaves no row. Contradictions come back as
    {status: refused, reason}; the GM adjusts and resubmits."""
    from .player import get_player
    p = dict(proposal or {})
    draw = int(p.get("draw", 0) or 0)
    if get_player(conn):
        return {"status": "refused", "reason": "a protagonist already exists", "reason_kind": "contradiction", "draw": draw}
    accept = bool(p.get("accept", False))
    conn.execute("SAVEPOINT newchar")
    try:
        out = _build(conn, p, call_id, campaign_name)
    except ValueError as e:  # Contradiction and the engine's own domain refusals (an AuthoringRefused) alike
        conn.execute("ROLLBACK TO SAVEPOINT newchar")
        conn.execute("RELEASE SAVEPOINT newchar")
        return {"status": "refused", "reason": str(e), "reason_kind": getattr(e, "reason_kind", "contradiction"), "draw": draw}
    except BaseException:
        conn.execute("ROLLBACK TO SAVEPOINT newchar")
        conn.execute("RELEASE SAVEPOINT newchar")
        raise
    if not accept:
        conn.execute("ROLLBACK TO SAVEPOINT newchar")
        conn.execute("RELEASE SAVEPOINT newchar")
        out.pop("actor_id", None)
        out.pop("sheet", None)
        out["status"] = "draft"
        return out
    conn.execute("RELEASE SAVEPOINT newchar")
    out["status"] = "created"
    return out


def _campaign_name() -> str:
    import os
    from pathlib import Path
    name = os.environ.get("CAERNESS_CAMPAIGN")
    if name:
        return name
    path = os.environ.get("CAERNESS_DB_PATH")
    return Path(path).stem if path else "Campaign 01"


def _join(conn, aid: int, found: dict, role: Any, day: int) -> dict:
    """He joins an existing body in an ordinary place; never a seat that is held."""
    role_text = str(role or "member")[:60]
    if found["kind"] == "institution":
        conn.execute("INSERT OR IGNORE INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,"
                     "provenance_json,metadata_json) VALUES (?,?,'ordinary_member',?, 'active',?,?,?)",
                     (found["id"], aid, role_text, day - 365, json.dumps(["new protagonist"]), json.dumps(SOURCE)))
    elif found["kind"] == "outfit":
        from .underworld_rebuild import create_personnel
        create_personnel(conn, found["id"], role_kind="member", actor_id=aid)
    else:
        from .merchant import add_enterprise_staff
        add_enterprise_staff(conn, found["id"], aid, role=role_text, authority=25)
    return found


def _build(conn, p: dict, call_id: str, campaign_name: str | None) -> dict:
    from . import authoring
    from .health import _family_means
    from .player import set_player
    key = _key(conn, p)
    draw = int(p.get("draw", 0) or 0)
    day = _day(conn)
    sex, drawn = resolve_sex(conn, p, key)
    prop = {**p, "sex": sex, "_exact": True}
    try:
        facts = veto.check_proposal(conn, prop)
    except Contradiction as e:
        if drawn and "cannot supply" in str(e):  # a drawn sex the place cannot supply is flipped; a stated one is a clash
            sex = "female" if sex == "male" else "male"
            prop = {**p, "sex": sex, "_exact": True}
            facts = veto.check_proposal(conn, prop)
        else:
            raise
    loc, cat = facts["location"], facts["category"]
    age = int(p["age"])
    stage = authoring._stage_name(p.get("stage"))
    plan = _holdings_plan(p)
    scaled_in = [dict(h, amount=h.get("amount", "modest")) for h in plan["businesses"]] + ([{"kind": "cash", "amount": plan["cash"]}] if plan["cash"] else [])
    adj, down = veto.holdings_in_proportion(conn, loc, scaled_in)
    cash = next((float(h["amount"]) for h in adj if h.get("kind") == "cash"), 0.0)
    businesses = [h for h in adj if h.get("kind") != "cash"]
    work_text = p.get("work")
    got: dict = {}
    aid = authoring.materialise_person(
        conn, loc=loc, sex=sex, age=age, work_domain=cat if work_text else None, stage=stage, elsewhere=bool(p.get("from_elsewhere")),
        name=(str(p["name"]).strip() if p.get("name") else None), pick_seed=key, call_id=call_id,
        retired=bool(work_text and cat not in ("soldier", "criminal") and stage in ("Breach", "Fifth", "Sixth")), out=got,
        reason="New protagonist", notes="Protagonist designed with the owner; not canon.", exact_stage=bool(stage), window=facts["window"], growth_batches=64)
    got_age = _age(conn, aid, day)
    if got_age != age:
        down.append({"asked": f"{age} years", "got": f"{got_age} years", "why": "he is the nearest to that age and standing the place has"})
        age = got_age
    _mark_actor(conn, aid, {"concept": str(p.get("concept") or "")[:600], "draw": draw})
    means, _tags = _family_means(conn, [aid])
    start = round(0.5 * 4.0 * (means / 50.0) ** 3 * max(0.4, min(1.2, age / 45.0)), 2) if age >= 16 else 0.0
    set_player(conn, aid, campaign_name or _campaign_name())
    funds = start + cash  # what he founds is paid in just before it is founded (below), never more than becomes capital
    if funds > 0:
        ledger._credit(conn, ("person", aid), funds)
    hid = None
    if age >= 16:
        from .civilian import create_household
        hid = create_household(conn, f"Household of {_name(conn, aid)}", head_actor_id=aid, location_id=loc,
                               wealth=round(start * 3, 2), liquidity=round(start * 1.2, 2),
                               metadata={**SOURCE, "economic_basis": "protagonist", "economic_resolution": "QUANTIFIED"})
        conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (hid, aid))
    # what he founds: outfits and businesses through the same vetted paths as `author`, paid from his own purse
    made: list[str] = []
    outfit_ids: list[int] = []
    holds = 0
    aff_resolved = None
    aff = p.get("affiliation") or {}
    oname = aff.get("name") or aff.get("text")
    atype = " ".join(str(aff.get(k) or "") for k in ("type", "kind")).strip()
    lastname = _name(conn, aid).split()[-1]
    if oname:
        found = veto.held_by_other(conn, str(oname), aff.get("role"), new=bool(aff.get("new")))
        if found is not None:
            aff_resolved = _join(conn, aid, found, aff.get("role"), day)
        else:
            text = f"{oname} {atype}".lower()
            if any(w in text for w in _VIOLENT) or plan["outfits"]:
                o = authoring._organisation(conn, aid, {"name": oname, "type": atype or "gang", "location_id": loc,
                                                        **({"members": aff["members"]} if aff.get("members") else {})}, call_id + ":o")
                outfit_ids.append(o["outfit_id"])
                aff_resolved = {"kind": "outfit", "id": o["outfit_id"]}
                down += o.get("scaled_down", [])
                made.append(f"leads {oname}, an outfit")
                holds += 2
            elif any(w in text for w in _BIZ):
                b = authoring._business(conn, aid, {"name": oname, "trade": atype or str(oname), "location_id": loc}, call_id + ":b")
                down += b.get("scaled_down", [])
                made.append(f"keeps {oname}")
                holds += 1
            else:
                o = authoring._organisation(conn, aid, {"name": oname, "type": atype or "company", "location_id": loc}, call_id + ":i")
                aff_resolved = {"kind": "institution", "id": o["institution_actor_id"]}
                made.append(f"heads {oname}")
                holds += 1
    for h in plan["outfits"]:
        if outfit_ids or not h.get("name"):
            continue
        o = authoring._organisation(conn, aid, {"name": h["name"], "type": h.get("kind") or "gang", "location_id": loc,
                                                **({"members": h["members"]} if h.get("members") else {})}, call_id + ":o")
        outfit_ids.append(o["outfit_id"])
        aff_resolved = aff_resolved or {"kind": "outfit", "id": o["outfit_id"]}
        down += o.get("scaled_down", [])
        made.append(f"leads {h['name']}")
        holds += 2
    for h in businesses:
        paid_in = float(h["amount"])
        ledger._credit(conn, ("person", aid), paid_in)
        try:
            b = authoring._business(conn, aid, {"name": h.get("name") or f"{lastname}'s {h.get('kind', 'shop')}", "trade": h.get("kind") or "shop",
                                                "amount": paid_in, "location_id": loc}, f"{call_id}:b:{h.get('name') or h.get('kind')}")
        except authoring.AuthoringRefused as e:
            ledger._debit(conn, ("person", aid), paid_in)
            down.append({"asked": str(h.get("kind") or "business"), "got": "none", "why": str(e)})
            continue
        capital = float(conn.execute("SELECT capital FROM civilian_enterprises WHERE id=?", (b["enterprise_id"],)).fetchone()[0])
        if paid_in - capital > 1e-9:  # the town bore less than was paid in: the rest goes back, he keeps nothing unearned
            ledger._debit(conn, ("person", aid), paid_in - capital)
        down += b.get("scaled_down", [])
        made.append(f"owns {b['name']}")
        holds += 1
    for h in plan["rackets"]:
        kind_text = str(h.get("kind") or h.get("name") or "").lower()
        try:
            amt = ledger.amount_of(h.get("amount", "modest"), None)
        except ValueError:
            amt = ledger.SCALES["modest"]
        if outfit_ids:
            from .underworld_rebuild import create_racket_site
            rk = next((v for w, v in _RACKET if w in kind_text), "protection collections")
            adj2, d2 = veto.holdings_in_proportion(conn, loc, [{"kind": kind_text, "amount": amt}])
            down += d2
            if adj2:
                create_racket_site(conn, outfit_ids[0], rk, zone_id=None, gross_income_per_30=round(max(1.0, float(adj2[0]["amount"]) * 2.0), 2))
                made.append(f"runs {rk}")
        else:  # no outfit: vice under his own name is a plain business
            b = authoring._business(conn, aid, {"name": h.get("name") or f"{lastname}'s {h.get('kind', 'house')}", "trade": kind_text,
                                                "amount": amt, "location_id": loc}, f"{call_id}:r:{kind_text}")
            made.append(f"owns {b['name']}")
            holds += 1
    from .opening_family import _seed_pair
    for t in p.get("ties") or []:
        who = t.get("who") if isinstance(t, dict) else None
        other = conn.execute("SELECT id FROM actors WHERE name=? AND actor_type='character' AND status='active'", (who,)).fetchone() if who else None
        if other:
            _seed_pair(conn, aid, int(other[0]), "acquaintance", key=f"{key}:tie:{who}", started_day=day - 700)
    past = fill_lived_past(conn, aid, key=key, proposal={**p, "_affiliation": aff_resolved, "_holds": holds})
    staff: dict = {}
    if hid is not None:
        from .household_staff import ensure_household_staff
        staff = ensure_household_staff(conn, hid, key=key)
    return _summary(conn, aid, past, made, down, staff, draw, got, loc)


def _summary(conn, aid: int, past: dict, made: list[str], down: list[dict], staff: dict, draw: int, got: dict, loc: int) -> dict:
    day = _day(conn)
    row = conn.execute("""SELECT a.name,lp.demographic_sex sex FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?""", (aid,)).fetchone()
    place = _loc(conn, loc)
    age = _age(conn, aid, day)
    d = past.get("digest", {})
    prof = conn.execute("SELECT occupation_domain FROM background_person_profiles WHERE actor_id=?", (aid,)).fetchone()
    work = prof["occupation_domain"] if prof else "ordinary work"

    def word(n: int) -> str:
        return {0: "no", 1: "one", 2: "two", 3: "three"}.get(n, "several")

    fam = ["married" if d.get("spouse") else "not married"]
    if d.get("children"):
        fam.append(f"{word(d['children'])} child{'ren' if d['children'] > 1 else ''} known")
    fam.append("both parents living" if d.get("parents_living") == 2 else "one parent living" if d.get("parents_living") == 1 else "no parent in the house")
    if d.get("siblings_known"):
        fam.append(f"{word(d['siblings_known'])} sibling{'s' if d['siblings_known'] > 1 else ''} nearby")
    served = int(staff.get("hired", 0)) + int(staff.get("counted", 0))
    his = "his" if row["sex"] == "male" else "her"
    out = {
        "status": "draft", "draw": draw, "actor_id": aid,
        "summary": {
            "who": f"{row['name']}, a {age}-year-old {'man' if row['sex'] == 'male' else 'woman'} of {place}"
                   + (f", come from {got['origin']}" if got.get("origin") else ""),
            "work": work,
            "family": "; ".join(fam),
            "holdings": made or [f"nothing of {his} own beyond {his} household"],
            "household": (f"a household with {word(served)} in service" if served else "a household with no servants") if age >= 16 else f"lives in the house of {his} parents",
            "standing": f"known in {place} as a {work}, as far as {his} years and holdings earn",
            "people": ("a handful of neighbours" if d.get("neighbours", 0) >= 3 else "few neighbours") + (", colleagues" if d.get("colleagues") else "")
                      + (", an old teacher" if d.get("mentor") else ""),
            "past": "a plausible past is filled in: kin, neighbours, what he has learned of the town, a few memories",
        },
        "sheet": {"history": f"{row['name']}: {', '.join(fam)}. " + ("; ".join(made) if made else "Lives by his work."), "standing": f"Known in {place}."},
    }
    if down:
        out["scaled_down"] = down
    return out
