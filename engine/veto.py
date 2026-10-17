"""The veto: a proposal for a person or a holding is accepted unless it contradicts something.

There is no menu. Free text comes in; `categorise` maps it to the nearest simulation category (the commonest, `labor`, when
nothing fits) and never refuses because a word is unknown. A `Contradiction` is raised only for a canon rule, an established
fact, or an impossible person, and its message names what clashes with what, so the GM can adjust and resubmit. Anything merely
oversized is scaled down (`holdings_in_proportion`) and reported in words, not refused.
"""
from __future__ import annotations

import math
import re
import sqlite3
from typing import Any

from . import ledger
from .person_ecology import FIRST_FEMALE, FIRST_MALE, _MARTIAL, find_background_candidate


class Contradiction(ValueError):
    """The proposal clashes with a canon rule, an established fact or the scale of the place; the message says which."""


# One dict of parameters: shares of what the place already holds, never fixed tables of what may exist.
PROPORTION = {"wealth_share": 0.05, "outfit_share": 0.15, "business_share": 0.10, "outfit_population_share": 0.03}

_KEYWORDS = (
    ("physician", ("physician", "healer", "doctor", "surgeon", "apothecar", "herbal", "midwife", "nurse", "medic", "bonesetter")),
    ("soldier", ("soldier", "guard", "warden", "knight", "captain", "mercenar", "sergeant", "militia", "officer", "marshal", "warrior",
                 "swordsman", "duelist", "lancer", "archer", "general", "garrison", "cadet")),
    ("criminal", ("thief", "smuggl", "gangster", "racket", "fence", "pimp", "bandit", "outlaw", "criminal", "brothel", "gambl", "enforcer",
                  "cutpurse", "underworld", "crime boss", "extortion")),
    ("clerk", ("clerk", "scribe", "notary", "accountant", "bookkeep", "secretary", "steward", "registrar", "archivist", "official",
               "magistrate", "bailiff", "tax", "reeve")),
    ("teacher", ("teacher", "tutor", "scholar", "professor", "priest", "monk", "abbot", "instructor", "lecturer", "sage", "preacher")),
    ("hospitality", ("innkeep", "tavern", "inn", "cook", "brewer", "servant", "maid", "butler", "host", "baker", "kitchen", "barkeep", "caterer")),
    ("transport", ("carter", "sailor", "ferry", "courier", "driver", "boatman", "teamster", "navigator", "caravan", "coachman", "porter",
                   "bargeman", "shipmaster", "rider", "messenger")),
    ("artist", ("painter", "poet", "musician", "singer", "actor", "dancer", "bard", "sculpt", "playwright", "performer", "illustrator", "minstrel")),
    ("merchant", ("merchant", "trader", "shop", "peddler", "broker", "dealer", "vendor", "banker", "money", "financ", "wholesal", "factor",
                  "moneylend", "lender", "importer", "chandler", "grocer", "stallholder", "collector")),
    ("artisan", ("smith", "carpent", "mason", "cooper", "potter", "weaver", "tailor", "cobbler", "tanner", "glass", "joiner", "craft",
                 "wright", "dyer", "jeweler", "jeweller", "lamp", "chandler", "saddler", "fletcher", "cutler", "engraver")),
    ("labor", ("labor", "dock", "farm", "miner", "sweep", "hand", "digger", "woodcutter", "shepherd", "herder", "fisher", "navvy")),
)

_LEAD = re.compile(r"head|lead|lord|lady|boss|chief|captain|commander|founder|owner|proprietor|patriarch|matriarch|abbot|abbess|priorb|chair|"
                   r"ruler|king|queen|duke|baron|earl|regent|emperor|sovereign|warlord|master of|principal|director|heir")

# Female/male-coded words in a family description (a "husband" is a man): used only to catch a same-sex union.
_MALE_KIN = ("husband", "father", "brother", "son ", "uncle", "man ")
_FEMALE_KIN = ("wife", "mother", "sister", "daughter", "aunt", "woman")


def categorise(text: Any, hint: str | None = None) -> str:
    """The nearest occupation domain for free work text; `labor` when nothing fits. Never raises."""
    from .person_ecology import _OCCUPATIONS
    if hint and str(hint).strip().lower() in set(_OCCUPATIONS):
        return str(hint).strip().lower()
    t = " ".join(str(text or "").lower().replace("-", " ").split())
    if t in set(_OCCUPATIONS):
        return t
    best, score = "labor", 0
    for dom, words in _KEYWORDS:
        s = sum(len(w) for w in words if w in t)
        if s > score:
            best, score = dom, s
    return best


def norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def find_location(conn: sqlite3.Connection, ref: Any) -> int | None:
    """A place by id or by (loosely matched) name; None if the world has no such place."""
    if isinstance(ref, int) and not isinstance(ref, bool):
        return ref if conn.execute("SELECT 1 FROM locations WHERE id=?", (ref,)).fetchone() else None
    want = norm(ref)
    if not want:
        return None
    rows = conn.execute("SELECT id,name FROM locations").fetchall()
    for r in rows:
        if norm(r["name"]) == want:
            return int(r["id"])
    near = [int(r["id"]) for r in rows if want in norm(r["name"])]
    return near[0] if len(near) == 1 else None


def settlement_of(conn: sqlite3.Connection, loc: int) -> int | None:
    """The place itself or its nearest ancestor that has a population (districts count by their parent city)."""
    from .standing import _chain
    for r in _chain(conn, loc):
        if conn.execute("SELECT 1 FROM background_population_sources WHERE location_id=?", (int(r["id"]),)).fetchone():
            return int(r["id"])
    return None


def place_scale(conn: sqlite3.Connection, location_id: int) -> dict[str, float]:
    """What the place holds, from live data: population, enterprise capital and cash, household wealth, outfit members, bodies."""
    s = settlement_of(conn, int(location_id))
    scope = [int(r[0]) for r in conn.execute(
        "WITH RECURSIVE t(id) AS (SELECT ? UNION SELECT l.id FROM locations l JOIN t ON l.parent_location_id=t.id) SELECT id FROM t", (s if s is not None else int(location_id),))]
    q = ",".join("?" * len(scope))
    pop = float(conn.execute(f"SELECT COALESCE(SUM(population_estimate),0) FROM background_population_sources WHERE location_id IN ({q})", scope).fetchone()[0])
    ent = conn.execute(f"SELECT COUNT(*),COALESCE(SUM(capital+cash),0) FROM civilian_enterprises WHERE location_id IN ({q}) AND status IN ('active','strained','insolvent')", scope).fetchone()
    hh = float(conn.execute(f"SELECT COALESCE(SUM(wealth),0) FROM households WHERE location_id IN ({q}) AND status IN ('active','declining')", scope).fetchone()[0])
    org = conn.execute(f"SELECT COUNT(*),COALESCE(SUM(member_count_estimate),0) FROM underworld_organizations WHERE primary_location_id IN ({q}) AND status IN ('active','strained','fragmented')", scope).fetchone()
    inst = int(conn.execute(f"SELECT COUNT(*) FROM actors WHERE actor_type='institution' AND status='active' AND current_location_id IN ({q})", scope).fetchone()[0])
    return {"population": pop, "enterprises": float(ent[0]), "enterprise_wealth": float(ent[1]), "household_wealth": hh,
            "outfits": float(org[0]), "outfit_members": float(org[1]), "institutions": float(inst)}


# ---------------------------------------------------------------- the checks (each raises Contradiction or returns)

def canon_figure(conn: sqlite3.Connection, name: str | None) -> None:
    """The protagonist is never a canon figure: neither by name nor by likeness."""
    if not name:
        return
    want = norm(name)
    for r in conn.execute("SELECT a.name FROM actors a JOIN source_identity_map m ON m.entity_kind IN ('actor','institution') AND m.entity_id=a.id "
                          "WHERE a.actor_type='character'"):
        if norm(r["name"]) == want or (len(want.split()) >= 2 and norm(r["name"]).split()[:2] == want.split()[:2]):
            raise Contradiction(f"the name {name} is already taken by a canon figure ({r['name']}); a new person needs a new name")


def name_taken(conn: sqlite3.Connection, name: str | None) -> None:
    if name and conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
        raise Contradiction(f"the name {name} is already in use")


def name_sex(name: str | None, sex: str | None) -> str | None:
    """Names follow sex. Returns the sex the name implies (or None if the given name is unlisted, as single names may be);
    raises if it belongs to the other sex than the one stated."""
    if not name:
        return None
    given = str(name).split(" ", 1)[0]
    implied = "female" if given in FIRST_FEMALE else "male" if given in FIRST_MALE else None
    if sex in ("male", "female") and implied and implied != sex:
        raise Contradiction(f"the name {given} belongs to the other sex; names follow sex (stated {sex})")
    return implied


def same_sex_union(sex: str | None, spouse_sex: str | None, what: str = "spouse") -> None:
    if sex in ("male", "female") and spouse_sex == sex:
        raise Contradiction(f"no recognised same-sex union: a {sex} protagonist cannot have a {sex} {what}")


def stage_plausible(age: int, category: str, stage: str | None) -> None:
    if not stage:
        return
    order = ["First", "Temper", "Third", "Breach", "Fifth", "Sixth"]
    if stage not in order:
        return  # free text that is not a Stage name: no Stage claimed
    i = order.index(stage)
    if stage == "Sixth":
        raise Contradiction("the forty Sixths of the world are all known; a new person cannot be one")
    if age < 25 and i > 2:
        raise Contradiction(f"at {age} a {stage} is unheard of; under 25 at most Third")
    if age < 35 and i > 3:
        raise Contradiction(f"at {age} a {stage} is unheard of; under 35 at most Breach")
    if category not in _MARTIAL and i >= 2 and age < 45:
        raise Contradiction(f"a {category} at {stage} is all but unheard of; only a retired martial master (45 or more) keeps an ordinary trade")


def held_by_other(conn: sqlite3.Connection, name: str, role_text: str | None, *, new: bool = False) -> dict | None:
    """Joining an existing body in an ordinary role is fine; claiming its leadership is not if anyone (or canon) holds it.
    Returns {kind,id} of the existing body (None when it does not exist)."""
    want = norm(name)
    body = None
    for r in conn.execute("SELECT id,name,institution_actor_id FROM underworld_organizations"):
        if norm(r["name"]) == want:
            body = ("outfit", int(r["id"]))
    for r in conn.execute("SELECT id,name FROM actors WHERE actor_type='institution'"):
        if norm(r["name"]) == want:
            body = ("institution", int(r["id"]))
    for r in conn.execute("SELECT id,name FROM civilian_enterprises"):
        if norm(r["name"]) == want:
            body = ("business", int(r["id"]))
    leader = bool(role_text and _LEAD.search(str(role_text).lower()))
    if body is None:
        if not new and not leader:
            raise Contradiction(f"there is no body called {name} here; found it as a new one, or name one that exists")
        return None
    if not leader:
        return {"kind": body[0], "id": body[1]}
    kind, i = body
    if kind == "outfit":
        r = conn.execute("SELECT current_leader_actor_id l FROM underworld_organizations WHERE id=?", (i,)).fetchone()
        if r["l"] is not None and conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (r["l"],)).fetchone():
            raise Contradiction(f"{name} already has its leader ({conn.execute('SELECT name FROM actors WHERE id=?', (r['l'],)).fetchone()[0]})")
    elif kind == "institution":
        r = conn.execute("SELECT a.name FROM institution_memberships m JOIN actors a ON a.id=m.member_actor_id WHERE m.institution_actor_id=? "
                         "AND m.status='active' AND m.role_text='head' LIMIT 1", (i,)).fetchone()
        canon = conn.execute("SELECT 1 FROM source_identity_map WHERE entity_id=? AND entity_kind IN ('actor','institution')", (i,)).fetchone()
        if r is not None or canon:
            raise Contradiction(f"{name} already has its head{' (' + r[0] + ')' if r else ''}; a seat of canon scale is not for a newcomer")
    else:
        r = conn.execute("SELECT owner_actor_id FROM civilian_enterprises WHERE id=?", (i,)).fetchone()
        if r["owner_actor_id"] is not None:
            raise Contradiction(f"{name} already belongs to {conn.execute('SELECT name FROM actors WHERE id=?', (r['owner_actor_id'],)).fetchone()[0]}")
    return {"kind": kind, "id": i}


def kin_alive(conn: sqlite3.Connection, who: str, as_: str, age: int, *, alive: bool | None = True) -> int | None:
    """A named relative must exist (else it is only a description, returns None) and be living if claimed so;
    parent and child must be 15 to 55 years apart."""
    r = conn.execute("SELECT a.id,a.status,lp.birth_day,lp.life_status FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id "
                     "WHERE a.name=? AND a.actor_type='character'", (who,)).fetchone()
    if r is None:
        return None
    living = str(r["status"]) == "active" and str(r["life_status"] or "living") == "living"
    if alive and not living:
        raise Contradiction(f"{who} is dead and cannot be named as a living {as_}")
    if as_ in ("father", "mother", "parent") and r["birth_day"] is not None:
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        gap = (day - int(r["birth_day"])) // 365 - age
        if not 15 <= gap <= 55:
            raise Contradiction(f"{who} would be {gap} years older than him; a parent is 15 to 55 years older than the child")
    return int(r["id"])


def pool_can_supply(conn: sqlite3.Connection, *, loc: int, sex: str | None, age: int, category: str | None, stage: str | None,
                    elsewhere: bool = False, pick_seed: Any = None) -> None:
    """The population of the place must contain such a person (the reservoir is grown first, as a real reveal would)."""
    from .authoring import _pick_args
    retired = bool(category and category not in _MARTIAL and stage in ("Breach", "Fifth", "Sixth"))
    s = settlement_of(conn, loc)
    args = _pick_args(loc=s if s is not None else loc, sex=sex, age=age, work_domain=category, stage=stage, elsewhere=elsewhere, retired=retired)
    if find_background_candidate(conn, pick_seed=pick_seed, **args) is None:
        raise Contradiction("the people of that place cannot supply such a person"
                            + ("" if elsewhere else " (he could have come from elsewhere)"))


def holdings_in_proportion(conn: sqlite3.Connection, loc: int, holdings: list[dict], *, prior_wealth: float = 0.0,
                           prior_members: float = 0.0, prior_businesses: int = 0) -> tuple[list[dict], list[dict]]:
    """Scale each holding to what the place can supply. Returns (adjusted, scaled_down) with `scaled_down` entries
    {asked, got, why} in words. Nothing here refuses."""
    sc = place_scale(conn, loc)
    modest = ledger.SCALES["modest"]
    wealth_cap = max(modest, PROPORTION["wealth_share"] * (sc["enterprise_wealth"] + sc["household_wealth"])) - prior_wealth
    member_cap = max(3.0, PROPORTION["outfit_share"] * sc["outfit_members"], 0.0) - prior_members
    member_cap = min(member_cap, max(3.0, PROPORTION["outfit_population_share"] * sc["population"]))
    biz_cap = max(1, math.ceil(PROPORTION["business_share"] * max(sc["enterprises"], sc["population"] / 1000.0))) - prior_businesses
    out, down = [], []
    wealth_left, businesses = max(0.0, wealth_cap), 0
    for h in holdings:
        h = dict(h)
        kind = str(h.get("kind") or "").lower()
        is_outfit = bool(re.search(r"\b(outfit|gang|crew|band|brotherhood|syndicate|mob|ring)\b|company of", kind))
        if is_outfit:
            asked = float(h.get("members") or h.get("size") or 0) or None
            if asked is not None:
                got = max(1.0, min(asked, max(1.0, member_cap)))
                if got < asked - 0.5:
                    down.append({"asked": f"{int(asked)} men", "got": f"{int(got)} men", "why": "there aren't that many men here to follow him"})
                h["members"] = int(got)
        else:
            try:
                amt = ledger.amount_of(h.get("amount"), None) if h.get("amount") is not None else None
            except Exception:
                amt = None
            if amt is not None:
                got = min(amt, wealth_left)
                if got < amt - 0.01:
                    down.append({"asked": f"{ledger.scale_word(amt)} {kind or 'holding'}", "got": f"{ledger.scale_word(max(got, 0.2))}",
                                 "why": "the town doesn't hold that much; he starts with what it can bear"})
                wealth_left = max(0.0, wealth_left - got)
                h["amount"] = round(max(got, 0.2), 2)
            businesses += 1
            if businesses > biz_cap:
                down.append({"asked": f"{kind or 'business'} {h.get('name', '')}".strip(), "got": "none",
                             "why": "the town has room for no more of the kind"})
                continue
        out.append(h)
    return out, down


def check_proposal(conn: sqlite3.Connection, proposal: dict) -> dict:
    """Raise Contradiction for any clash; returns facts the caller needs (location, category, resolved sex, scaled_down)."""
    p = proposal
    name = p.get("name")
    canon_figure(conn, name)
    name_taken(conn, name)
    implied = name_sex(name, p.get("sex"))
    sex = p.get("sex") if p.get("sex") in ("male", "female") else implied
    age = p.get("age")
    if isinstance(age, bool) or not isinstance(age, int) or age < 0:
        raise Contradiction("age must be a whole number of years")
    loc = find_location(conn, p.get("place"))
    if loc is None:
        raise Contradiction(f"there is no place called {p.get('place')!r} in the world")
    cat = categorise(p.get("work"), p.get("category"))
    stage_plausible(age, cat, p.get("stage"))
    fam = p.get("family") or {}
    for key, text in fam.items():
        items = text if isinstance(text, list) else [text]
        for it in items:
            blob = " ".join(str(v) for v in (it.values() if isinstance(it, dict) else [it])).lower()
            if key == "spouse":
                if any(w in blob for w in _MALE_KIN) and not any(w in blob for w in _FEMALE_KIN):
                    same_sex_union(sex, "male")
                elif any(w in blob for w in _FEMALE_KIN):
                    same_sex_union(sex, "female")
            if age < 16 and key == "spouse" and blob.strip() not in ("", "none"):
                raise Contradiction("a child of that age has no spouse")
            who = it.get("name") if isinstance(it, dict) else (it if isinstance(it, str) else None)
            if who:
                role = {"parents": "parent", "children": "child", "siblings": "sibling"}.get(key, key)
                alive = it.get("alive", True) if isinstance(it, dict) else True
                kid = kin_alive(conn, who, role, age, alive=alive)
                if kid and key == "spouse":
                    sp = conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (kid,)).fetchone()
                    same_sex_union(sex, sp[0] if sp else None)
    aff = p.get("affiliation") or {}
    if aff and (aff.get("name") or aff.get("text")):
        held_by_other(conn, str(aff.get("name") or aff.get("text")), aff.get("role"), new=bool(aff.get("new")))
    pool_can_supply(conn, loc=loc, sex=sex, age=age, category=cat if p.get("work") else None, stage=p.get("stage") if p.get("stage") in
                    ("First", "Temper", "Third", "Breach", "Fifth") else None, elsewhere=bool(p.get("from_elsewhere")),
                    pick_seed=f"{p.get('draw', 0)}")
    return {"location": loc, "category": cat, "sex": sex}
