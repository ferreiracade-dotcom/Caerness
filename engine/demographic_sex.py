"""FAMILY-02 demographic-sex resolution for named characters.

FAMILY-02 treats missing sex as incomplete state: no union proposal, no biological birth.  The v1.4
seed never encoded sex, so most named people start unresolved.  This module resolves them once, in
strict evidence order, and records which basis decided each one:

1. ``canon_text``  - a gendered title or kin noun in the seed person's own canon text
                     ("Queen", "Crown Prince", "younger sister").  Conflicting evidence is ignored.
2. ``canon_rule``  - a canon rule that constrains sex (the Grand Coven Mantle is male-only).
3. ``given_name``  - a given name with a clear gender association, including invented names with a
                     conventional gendered form (lists below).
4. ``seeded_roll`` - a deterministic 50/50 draw, matching the background population's convention.

Genuinely ambiguous names (Robin, Avery, Quinn, Morgan, Jocelin ...) and invented names without a
conventional gendered form (Dravik, Ilyan, Valen ...) are absent from the lists and fall through to
the seeded roll.  Canon persons roll on their seed identity, so the same person has the same
sex in every world built from this seed.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
from typing import Any

FEMALE_GIVEN_NAMES = frozenset("""
Abigail Ada Adele Ailsa Alice Anna Aurelia Aveline Beatrice Beryl Beth Bridget Caitlin Cara Cassia Celia
Clara Claudia Cora Daisy Daphne Della Diana Dora Edith Elaine Elin Elise Eliza Ella Elodie Elsa Elsie Emily
Erica Esther Faith Faye Fiona Flora Freya Gemma Grace Greta Halwen Harriet Hazel Helena Holly Irene Iris Ivy
Jane Janet Joan Joy Joyce June Kara Keira Laura Lauren Leah Lena Lily Liora Lola Lorna Louise Lucy Lydia
Lysa Mabel Maeve Maisie Mara Maren Marnie Martha Matilda Maud Mavis May Megan Meriel Mina Mira Miriam
Mirren Moira Molly Mona Nadia Nadine Nancy Nell Neris Nina Nora Olive Opal Paige Paula Pearl Penny Petra
Phoebe Renata Roslyn Rowena Ruth Sabine Sally Sarah Selene Sophie Stella Talia Tara Tessa Vera Violet Wendy
Willa Ysella Erin Greer Piper Skye
""".split()) | frozenset("Kessa Sable Senna Sera".split())  # invented, conventional feminine form

MALE_GIVEN_NAMES = frozenset("""
Aaron Abel Adrian Aiden Alaric Alban Alden Aldous Alec Alfred Alistair Alton Alvin Alwyn Amos Andrew Anton
Arnold Arthur Baldwin Basil Bastian Ben Benedict Bennet Beren Berengar Bernard Boyd Brady Bram Bramwell Bran
Brennan Brock Bruce Bruno Bryce Caleb Calvin Carl Carter Casimir Cassander Cassian Cedric Clay Clement Clint
Clive Clyde Cody Colby Coleman Colin Colm Conor Conrad Corbin Cormac Corvin Corwin Crispin Curtis Cuthbert
Cyril Damian Damon Daniel Darius Darren Dean Declan Dennis Derek Desmond Dexter Dominic Dorian Douglas Duncan
Dylan Eamon Edgar Edmund Edward Edwin Eli Elias Elliot Emmett Ethan Evan Everett Ezra Felix Finn Fletcher
Francis Fraser Frederick Galen Gareth Garrett Garrick Gavin George Gerald Gerard Gideon Giles Glen Godfrey
Gordon Graham Hadrian Harlan Harris Harrod Harvey Heath Hector Henry Holden Howard Hugh Hugo Iain Isaac Ivan
James Jared Jareth Jasper Jerome Joel Jonas Julian Keaton Keith Kellan Kenneth Kevin Kieran Kirk Kurt Kyle
Lance Landon Laurence Leander Leofric Leon Lester Levi Lewis Liam Lionel Lloyd Logan Lucan Luke Luther Lyle
Marcus Marek Marius Martin Marvin Mason Matthias Maurice Max Merrick Micah Miles Milo Mitchell Morris Murray
Nate Nathan Ned Neville Nevin Niall Nicholas Nico Noah Noel Nolan Oscar Osmund Osric Ossian Otis Owen Patrick
Pavel Peregrine Perry Peter Philip Piers Quentin Rafe Ralph Raymond Reece Renaud Reuben Rhett Robert Roderick
Roland Rolf Rolfe Roman Ronan Rory Ross Rufus Rupert Samuel Scott Seth Shane Silas Simeon Simon Soren Spencer
Stanley Stefan Stephen Stuart Thaddeus Theo Theodric Theron Thomas Tobias Tobin Toby Todd Tomas Torben Trevor
Tristan Troy Tucker Vaughn Victor Vincent Wade Walter Warren Wes Wesley Wilfred Winston Wyatt Zach Zane
Amory Blaine Blake Brenner Dale Dario Hollis Jude Orson Talus
""".split()) | frozenset("""
Aldren Cedran Cyran Dalen Darran Deren Doran Edran Eran Gerran Hadric Hadrin Halric Harran Jeren Jorin Jory
Olan Oren Orin Orren Orric Roderan Talen Tavian Tavin Teren Torran
""".split())  # invented, conventional masculine endings (-ric, -an, -en, -in)

# Canon-text evidence: gendered titles/kin nouns.  Pronouns are excluded because seed role text often
# uses them for *other* people; "master" is a craft/cultivation rank here, not a gendered title.
_FEMALE_WORDS = re.compile(r"\b(queen|empress|princess|duchess|countess|lady|dame|abbess|matriarch|dowager|mother|"
                           r"grandmother|daughter|wife|widow|sister|aunt|niece|mistress)\b")
_MALE_WORDS = re.compile(r"\b(king|emperor|prince|duke|lord|sir|abbot|patriarch|father|grandfather|son|husband|"
                         r"widower|brother|uncle|nephew)\b")
# Leading name tokens that are titles, not given names.  Only these prefixes of the *name* count as
# canon text, so a surname such as "Opal King" is never read as a title.
_NAME_TITLES = frozenset({"queen", "king", "prince", "princess", "crown", "emperor", "empress", "lord", "lady",
                          "sir", "dame", "father", "mother", "brother", "sister", "high", "grand", "elder",
                          "master", "captain", "bishop", "old", "young", "the"})


def _split_name(name: str) -> tuple[list[str], str | None]:
    tokens = [t for t in re.split(r"\s+", name.strip()) if t]
    titles: list[str] = []
    while tokens and tokens[0].lower().strip(".") in _NAME_TITLES:
        titles.append(tokens.pop(0).lower().strip("."))
    return titles, (tokens[0] if tokens else None)


# World Bible pronouns for named people whose seed text is silent, read by hand (an automatic pronoun
# scan misattributes too often).  Keyed by seed identity.
WORLD_BIBLE_SEX = {
    "person:voss-rannick": "male",  # "Kellan Rannick, 46 and Fifth, is his principal active family recipient"
    "person:nall-reed": "male",     # "The huge order produces him through its own depth"
}


def _canon_text_sex(name: str, payload: dict[str, Any], source_key: str | None = None) -> str | None:
    if source_key in WORLD_BIBLE_SEX:
        return WORLD_BIBLE_SEX[source_key]
    stated = str(payload.get("demographic_sex") or "").lower()
    if stated in ("male", "female"):  # the seed says so outright; no text scan needed
        return stated
    titles, _ = _split_name(name)
    text = " ".join([*titles, str(payload.get("role") or ""), str(payload.get("public_identity_text") or "")]).lower()
    female, male = bool(_FEMALE_WORDS.search(text)), bool(_MALE_WORDS.search(text))
    return "female" if female and not male else "male" if male and not female else None


def _package_names(conn: sqlite3.Connection | None):
    """(male, female) given-name sets from the active world package's name pools and groups, or None when it has none."""
    if conn is None:
        return None
    from .world_package import package_for
    pkg = package_for(conn)
    male: set[str] = set()
    female: set[str] = set()
    for g in (pkg.name_groups or {}).values():
        male.update(g.get("male", ())); female.update(g.get("female", ()))
    pools = pkg.name_pools or {}
    male.update(pools.get("male") or ()); female.update(pools.get("female") or ())
    return (male, female) if male or female else None


def family_home_groups(conn: sqlite3.Connection, groups: dict, family: str | None) -> list[dict]:
    """The name groups a family belongs to. A surname no group lists (an authored family) belongs to the group whose
    given names its living members already bear, else to one group drawn by weight from the surname, so its children
    never take names from another community."""
    if not family or not groups:
        return []
    home = [g for g in groups.values() if family in g.get("family", ())]
    if home:
        return home
    kin = [str(r[0]).split(" ")[0] for r in conn.execute("SELECT name FROM actors WHERE name LIKE ?", (f"% {family}",)).fetchall()
           if str(r[0]).endswith(f" {family}")]
    keys = sorted(groups)
    hits = {k: sum(1 for n in kin if n in groups[k].get("male", ()) or n in groups[k].get("female", ())) for k in keys}
    best = max(hits.values(), default=0)
    if best:
        tied = [k for k in keys if hits[k] == best]
        if len(tied) == 1:
            return [groups[tied[0]]]
        keys = tied
    w = [max(float(groups[k].get("weight", 1.0)), 0.0) for k in keys]
    if sum(w) <= 0:
        w = [1.0] * len(keys)
    rng = random.Random(int(hashlib.sha256(f"family-group:{family}".encode()).hexdigest()[:16], 16))
    return [groups[rng.choices(keys, weights=w)[0]]]


def package_given_pool(conn: sqlite3.Connection, sex: str, family: str | None = None) -> list[str] | None:
    """Sorted given names of this sex from the world package (the family's own group when it has one), else None
    so the caller keeps the Caerness lists."""
    from .world_package import package_for
    pkg = package_for(conn)
    key = "female" if sex == "female" else "male"
    groups = pkg.name_groups or {}
    home = family_home_groups(conn, groups, family)
    names = [n for g in (home or groups.values()) for n in g.get(key, ())]
    if not names:
        names = list((pkg.name_pools or {}).get(key) or ())
    return sorted(dict.fromkeys(names)) or None


def package_person_name(conn: sqlite3.Connection, rng, sex: str) -> tuple[str, str] | None:
    """A (given, family) pair from one weighted package name group, so the pair never crosses groups; None when the
    package has no name pools (the Caerness lists stay in force)."""
    from .world_package import package_for
    pkg = package_for(conn)
    key = "female" if sex == "female" else "male"
    groups = {k: g for k, g in (pkg.name_groups or {}).items() if g.get(key) and g.get("family")}
    if groups:
        keys = sorted(groups)
        w = [float(groups[k].get("weight", 1.0)) for k in keys]
        g = groups[rng.choices(keys, weights=w if sum(w) > 0 else None)[0]]
        return rng.choice(sorted(g[key])), rng.choice(sorted(g["family"]))
    pools = pkg.name_pools or {}
    def draw(p):
        if isinstance(p, dict):
            ks = sorted(p)
            return rng.choices(ks, weights=[float(p[k]) for k in ks])[0]
        return rng.choice(sorted(p))
    if pools.get(key) and pools.get("family"):
        return draw(pools[key]), draw(pools["family"])
    return None


def _given_name_sex(name: str, conn: sqlite3.Connection | None = None) -> str | None:
    _, given = _split_name(name)
    pk = _package_names(conn)
    if pk and given:
        in_m, in_f = given in pk[0], given in pk[1]
        if in_m != in_f:
            return "male" if in_m else "female"
    if given in FEMALE_GIVEN_NAMES:
        return "female"
    if given in MALE_GIVEN_NAMES:
        return "male"
    return None


def seeded_sex(key: str) -> str:
    """Deterministic 50/50 draw; the same key always yields the same sex."""
    return "female" if hashlib.sha256(f"demographic_sex:{key}".encode()).digest()[0] & 1 else "male"


def _mantle_male_actor_ids(conn: sqlite3.Connection) -> set[int]:
    """The Grand Coven Mantle is male-only: its holder and Mantle-eligible heirs are male."""
    ids: set[int] = set()
    try:
        for r in conn.execute("SELECT inheritor_actor_id,foremost_heir_actor_id FROM grand_coven_succession_state"):
            ids.update(int(x) for x in r if x is not None)
        ids.update(int(r[0]) for r in conn.execute("SELECT actor_id FROM grand_coven_heirs WHERE mantle_eligible=1"))
    except sqlite3.OperationalError:
        pass
    return ids


def apply_world_bible_sex_corrections(conn: sqlite3.Connection) -> int:
    """Correct weaker-evidence resolutions (given name, seeded roll) that World Bible text contradicts."""
    fixed = 0
    for key, sex in WORLD_BIBLE_SEX.items():
        row = conn.execute(
            """SELECT lp.actor_id FROM source_identity_map m JOIN actor_life_profiles lp ON lp.actor_id=m.entity_id
               WHERE m.entity_kind='actor' AND m.source_key=? AND lp.demographic_sex<>?
                 AND COALESCE(json_extract(lp.metadata_json,'$.demographic_sex_basis'),'') IN ('','given_name','seeded_roll')""",
            (key, sex),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE actor_life_profiles SET demographic_sex=?,metadata_json=json_patch(metadata_json,?) WHERE actor_id=?",
                (sex, json.dumps({"demographic_sex_basis": "canon_text", "demographic_sex_authority": "FAMILY02_SEX_RESOLUTION_V1"}), int(row[0])),
            )
            fixed += 1
    return fixed


def resolve_missing_demographic_sex(conn: sqlite3.Connection, *, actor_id: int | None = None) -> dict[str, int]:
    """Resolve named characters whose sex is NULL/'unspecified' (all, or just ``actor_id``); returns counts by basis."""
    seed_rows = {
        int(r[0]): (str(r[1]), json.loads(r[2] or "{}"))
        for r in conn.execute(
            "SELECT entity_id,source_key,source_payload_json FROM source_identity_map WHERE entity_kind='actor' AND (? IS NULL OR entity_id=?)",
            (actor_id, actor_id),
        )
    }
    mantle = _mantle_male_actor_ids(conn)
    world_seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    counts = {"canon_text": 0, "canon_rule": 0, "given_name": 0, "seeded_roll": 0}
    rows = conn.execute(
        """SELECT a.id,a.name FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
           WHERE a.actor_type='character' AND (lp.demographic_sex IS NULL OR lp.demographic_sex='unspecified')
             AND (? IS NULL OR a.id=?)
           ORDER BY a.id""",
        (actor_id, actor_id),
    ).fetchall()
    for aid, name in rows:
        aid, name = int(aid), str(name)
        source_key, payload = seed_rows.get(aid, (None, {}))
        sex, basis = _canon_text_sex(name, payload, source_key) if source_key else None, "canon_text"
        if sex is None and aid in mantle:
            sex, basis = "male", "canon_rule"
        if sex is None:
            sex, basis = _given_name_sex(name, conn), "given_name"
        if sex is None:
            sex, basis = seeded_sex(source_key or f"actor:{world_seed}:{aid}"), "seeded_roll"
        conn.execute(
            "UPDATE actor_life_profiles SET demographic_sex=?,metadata_json=json_patch(metadata_json,?) WHERE actor_id=?",
            (sex, json.dumps({"demographic_sex_basis": basis, "demographic_sex_authority": "FAMILY02_SEX_RESOLUTION_V1"}), aid),
        )
        counts[basis] += 1
    return counts
