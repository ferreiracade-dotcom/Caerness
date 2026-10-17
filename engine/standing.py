"""Standing in words: how one person stands to another, derived from facts the engine already stores.

Canon [1610] puts facts in the engine and humanisation in narration. Standing has several independent
axes ([488]-[501]); nothing here collapses them into a score, and nothing returns a number.
"""
from __future__ import annotations

import re
import sqlite3

from .cultivation import STAGES, location_in_hearth
from .embodiment import stance_band, trust_band
from .relationships import relationship_view

# What a Stage looks like to a Hearth observer ([212]-[232]). Outside the Hearth the same Stage impresses
# one step more ([297]-[318]); an outer Sixth is "a continental anomaly".
STAGE_READINGS = (
    "a developing fighter",
    "a working fighter",
    "a seasoned master",
    "an unmistakable master",
    "a great master",
    "among the strongest alive",
    "a continental anomaly",
)

# The first three steps for a cultivator with no martial life (canon [474]-[476], [5886]-[5887]: Veinborn, cultivator,
# martial artist and Churned are separate labels; a physician or clerk is not a combatant and has no healer ladder of her own).
NONMARTIAL_READINGS = (
    "lightly cultivated",
    "a practised cultivator",
    "a well-cultivated vessel",
)
# Beyond Third a non-martial cultivator is unheard of; recorded so, the person reads as a martial artist.
_NONMARTIAL_MAX_STAGE = 2
_MARTIAL_INST = re.compile(r"sect|clan|house|martial|military|school|order|service family", re.I)
_MARTIAL_WORK = re.compile(r"soldier|guard|warden|knight|fighter|champion|martial|mercenary|captain|marshal|sergeant|veteran|duellist|duelist", re.I)
_CHURN_INST = ("Concord", "Undertow", "Unsworn", "Long Road")

_AGE_BANDS = ((12, "child"), (17, "youth"), (29, "young adult"), (44, "adult"), (59, "middle-aged"), (74, "elderly"))
# A rank is read off the person only when the title is a real one. "Master" and "head" are martial and house
# titles (sect, clan, house, coven, order ...); in a trade title ("harbour master", "head cook") they are not ranks.
_MARTIAL_KIND = re.compile(r"sect|clan|house|coven|order|league|union|martial|military|school|federation|service family|royal|dynasty|council", re.I)
_MARTIAL_TITLE = re.compile(r"\b(head|master|elder|champion|captain|teacher|leader|patriarch|matriarch)\b", re.I)
_OFFICE_TITLE = re.compile(r"\b(general|admiral|commander|lord|lady|magistrate|abbot|abbess|bishop|archbishop|chancellor|prince|princess|king|queen)\b", re.I)
_TRADE_BEFORE = {"harbour", "harbor", "dock", "port", "quay", "ship", "stable", "kitchen", "yard", "wharf", "quarter", "post", "toll",
                 "bath", "band", "ring", "fight", "game", "dance", "brew", "work", "bridge", "gate", "town", "tax", "ware"}
_TRADE_AFTER = {"cook", "chef", "baker", "brewer", "groom", "gardener", "clerk", "servant", "maid", "porter", "nurse", "gatekeeper",
                "relative", "butcher", "carter", "mason", "smith", "boy", "girl", "man", "woman"}
_HOUSE_ROLES = {"steward", "clerk", "retainer", "guard", "tutor", "apprentice"}
_FAME = 60.0


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _sex(conn: sqlite3.Connection, actor_id: int) -> str | None:
    r = conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    return r[0] if r and r[0] in ("female", "male") else None


def _birth(conn: sqlite3.Connection, actor_id: int):
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    return r[0] if r else None


def _age_band(conn: sqlite3.Connection, actor_id: int, day: int) -> str | None:
    b = _birth(conn, actor_id)
    if b is None:
        return None
    years = (day - int(b)) // 365
    for limit, word in _AGE_BANDS:
        if years <= limit:
            return word
    return "aged"


def _chain(conn: sqlite3.Connection, location_id):
    out, seen, lid = [], set(), location_id
    while lid is not None and int(lid) not in seen and len(out) < 8:
        seen.add(int(lid))
        row = conn.execute("SELECT id,name,kind,parent_location_id,political_owner FROM locations WHERE id=?", (int(lid),)).fetchone()
        if not row:
            break
        out.append(row)
        lid = row["parent_location_id"]
    return out


def polity_of(conn: sqlite3.Connection, location_id) -> str | None:
    return next((str(r["political_owner"]) for r in _chain(conn, location_id) if r["political_owner"]), None)


def _short_polity(name: str) -> str:
    return name.replace("Underheaven Empire", "the Empire").replace(" Confederacy", "")


def _clean(text: str) -> str:
    return " ".join(str(text or "").replace("_", " ").split()).rstrip(". ")


def _is_rank(role: str, institution_kind: str | None) -> bool:
    """A real rank: a martial or house title in a martial or house institution, or a great office; never a trade title."""
    words = re.findall(r"[a-z'-]+", role.lower())
    pattern = _MARTIAL_TITLE if institution_kind is None or _MARTIAL_KIND.search(institution_kind) else None
    for rx in (pattern, _OFFICE_TITLE):
        if rx is None:
            continue
        for m in rx.finditer(role):
            before = re.findall(r"[a-z'-]+", role[:m.start()].lower())[-1:]
            after = re.findall(r"[a-z'-]+", role[m.end():].lower())[:1]
            if not (before and before[0] in _TRADE_BEFORE) and not (after and after[0] in _TRADE_AFTER):
                return True
    return False


def _martial_context(conn: sqlite3.Connection, aid: int) -> tuple[bool, bool]:
    """(martial artist, Churned): martial by membership of a martial institution, a fighting trade or an underworld outfit;
    Churned only through a Churn institution or a martial house of the Hearth."""
    martial = churned = False
    for name, kind, loc in conn.execute(
            """SELECT i.name,i.subtype,COALESCE(i.current_location_id,i.home_location_id) FROM institution_memberships m
               JOIN actors i ON i.id=m.institution_actor_id WHERE m.member_actor_id=? AND m.status='active'""", (aid,)):
        if any(n in str(name) for n in _CHURN_INST):
            martial = churned = True
        elif _MARTIAL_INST.search(str(kind or "")):
            martial = True
            churned = churned or bool(loc is not None and location_in_hearth(conn, loc))
    if not martial:
        from .person_ecology import has_martial_past
        martial = has_martial_past(conn, aid)  # a retired master reads as a martial artist whatever his trade now
    if not martial:
        r = conn.execute("SELECT subtype FROM actors WHERE id=?", (aid,)).fetchone()
        martial = bool(r and _MARTIAL_WORK.search(str(r[0] or ""))) or bool(conn.execute(
            "SELECT 1 FROM underworld_personnel WHERE actor_id=? AND status='active'", (aid,)).fetchone())
    return martial, churned


def _reading(conn: sqlite3.Connection, aid: int, idx: int, stage_idx: int) -> str:
    martial, churned = _martial_context(conn, aid)
    idx = min(idx, len(STAGE_READINGS) - 1)
    if not martial and stage_idx <= _NONMARTIAL_MAX_STAGE:
        return NONMARTIAL_READINGS[min(idx, len(NONMARTIAL_READINGS) - 1)]
    word = STAGE_READINGS[idx]
    if not churned:
        return word
    return "a Churned " + word[2:] if word.startswith("a ") else "Churned, " + word


def _station(conn: sqlite3.Connection, aid: int) -> tuple[str | None, bool]:
    """How the room reads someone (public roles only) and whether that is a visible rank. Secret roles, such as
    an underworld command, are never read off a person."""
    r = conn.execute("SELECT i.name FROM political_polities p JOIN actors i ON i.id=p.institution_actor_id "
                     "WHERE p.ruler_actor_id=? AND p.status='active' LIMIT 1", (aid,)).fetchone()
    if r:
        return f"ruler of {r[0]}", True
    r = conn.execute("SELECT m.role_text,i.subtype FROM institution_memberships m JOIN actors i ON i.id=m.institution_actor_id "
                     "WHERE m.member_actor_id=? AND m.status='active' AND COALESCE(m.role_text,'')<>'' ORDER BY m.id LIMIT 1", (aid,)).fetchone()
    if r:
        role = _clean(r[0])[:60]
        return role, _is_rank(role, r[1])
    r = conn.execute("SELECT h.name,h.id FROM household_members m JOIN households h ON h.id=m.household_id "
                     "WHERE m.actor_id=? AND m.role='head' AND m.status='active' ORDER BY h.id LIMIT 1", (aid,)).fetchone()
    if r:
        return f"head of the {_household_family(conn, int(r[1]), aid)} household", False
    r = conn.execute("SELECT name FROM civilian_enterprises WHERE owner_actor_id=? AND status IN ('active','strained') ORDER BY capital DESC LIMIT 1", (aid,)).fetchone()
    if r:
        return f"owner of {_clean(r[0])}"[:60], False
    return None, False


def _is_famous(conn: sqlite3.Connection, aid: int) -> bool:
    r = conn.execute("SELECT MAX(value) FROM social_reputation WHERE subject_kind='actor' AND subject_id=?", (aid,)).fetchone()
    return bool(r and r[0] is not None and float(r[0]) >= _FAME)


# ---- kin -----------------------------------------------------------------------------------------------

def _links(conn: sqlite3.Connection, aid: int, kinds: tuple[str, ...]):
    """Other ends of live links of the given kinds where aid is actor_a."""
    q = ",".join("?" * len(kinds))
    return [int(r[0]) for r in conn.execute(
        f"SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind IN ({q}) AND ended_day IS NULL "
        "AND legal_status<>'former' ORDER BY id", (aid, *kinds))]


def _parents(conn, aid):
    return [int(r[0]) for r in conn.execute(
        "SELECT actor_a_id FROM kinship_links WHERE actor_b_id=? AND kin_kind IN ('parent','adoptive_parent') "
        "AND ended_day IS NULL AND legal_status<>'former' ORDER BY id", (aid,))]


def _children(conn, aid):
    return _links(conn, aid, ("parent", "adoptive_parent"))


def _spouses(conn, aid):
    return _links(conn, aid, ("spouse",))


def _sibling_map(conn, aid) -> dict[int, bool]:
    """Sibling -> True if full. Linked siblings count, and so does anyone sharing a parent link (half if only one shared)."""
    out = {b: True for b in _links(conn, aid, ("sibling",))}
    mine = _parents(conn, aid)
    shared: dict[int, int] = {}
    for par in mine:
        for kid in _children(conn, par):
            if kid != aid:
                shared[kid] = shared.get(kid, 0) + 1
    for kid, n in shared.items():
        if kid not in out:
            out[kid] = n >= 2 or len(mine) == 1 and len(_parents(conn, kid)) == 1
    return out


def _siblings(conn, aid):
    return list(_sibling_map(conn, aid))


def _noun(sex: str | None, female: str, male: str, neutral: str) -> str:
    return female if sex == "female" else male if sex == "male" else neutral


def _kin(conn: sqlite3.Connection, observer: int, subject: int) -> str | None:
    """What the subject is to the observer, one step of marriage included."""
    ssex = _sex(conn, subject)
    if subject in _spouses(conn, observer):
        return "your " + _noun(ssex, "wife", "husband", "spouse")
    if subject in _parents(conn, observer):
        return "your " + _noun(ssex, "mother", "father", "parent")
    if subject in _children(conn, observer):
        return "your " + _noun(ssex, "daughter", "son", "child")
    sibs = _sibling_map(conn, observer)
    if subject in sibs:
        ob, sb = _birth(conn, observer), _birth(conn, subject)
        rel = "" if ob is None or sb is None or ob == sb else ("elder " if sb < ob else "younger ")
        half = "" if sibs[subject] else "half-"
        return f"your {rel}{half}" + _noun(ssex, "sister", "brother", "sibling")
    for sp in _spouses(conn, observer):
        spw = _noun(_sex(conn, sp), "wife", "husband", "spouse")
        if subject in _parents(conn, sp):
            return f"your {spw}'s " + _noun(ssex, "mother", "father", "parent")
        if subject in _siblings(conn, sp):
            return f"your {spw}'s " + _noun(ssex, "sister", "brother", "sibling")
    for ch in _children(conn, observer):
        chn = _noun(_sex(conn, ch), "daughter", "son", "child")
        if subject in _spouses(conn, ch):
            return f"your {chn}'s " + _noun(ssex, "wife", "husband", "spouse")
    for sib in _siblings(conn, observer):
        if subject in _spouses(conn, sib):
            return f"your {_noun(_sex(conn, sib), 'sister', 'brother', 'sibling')}'s " + _noun(ssex, "wife", "husband", "spouse")
    return None


# ---- household -----------------------------------------------------------------------------------------

def _household_family(conn: sqlite3.Connection, household_id: int, fallback: int | None = None) -> str:
    """The family a household goes by: its head's family name."""
    r = conn.execute("SELECT a.name FROM household_members m JOIN actors a ON a.id=m.actor_id WHERE m.household_id=? AND m.role='head' "
                     "AND m.status='active' LIMIT 1", (household_id,)).fetchone()
    if not r:
        r = conn.execute("SELECT a.name FROM households h JOIN actors a ON a.id=h.head_actor_id WHERE h.id=?", (household_id,)).fetchone()
    if not r and fallback is not None:
        r = conn.execute("SELECT name FROM actors WHERE id=?", (fallback,)).fetchone()
    return (str(r[0]).split()[-1:] or ["local"])[0] if r else "local"


def _household_word(conn: sqlite3.Connection, household_id: int) -> str:
    return f"the {_household_family(conn, household_id)} household"


def _house(conn: sqlite3.Connection, observer: int | None, subject: int) -> str | None:
    term = conn.execute(
        "SELECT t.household_id,t.service_role,h.head_actor_id FROM household_service_terms t JOIN households h ON h.id=t.household_id "
        "WHERE t.actor_id=? AND t.status='active' ORDER BY t.id LIMIT 1", (subject,)).fetchone()
    if term:
        role = _clean(term["service_role"]).lower()
        mine = observer is not None and (int(term["head_actor_id"] or 0) == observer or conn.execute(
            "SELECT 1 FROM household_members WHERE household_id=? AND actor_id=? AND status='active'",
            (term["household_id"], observer)).fetchone())
        if mine:
            return f"your {role}" if role in _HOUSE_ROLES else "a servant of your house"
        return f"{'servant' if role == 'other' else role} of {_household_word(conn, int(term['household_id']))}"
    return None


# ---- the public entry ----------------------------------------------------------------------------------

def _toward(conn: sqlite3.Connection, subject: int, observer: int) -> tuple[str | None, float]:
    row = conn.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (subject, observer)).fetchone()
    if not row:
        return None, 0.0
    r = relationship_view(conn, subject, observer)
    bits = []
    sb = stance_band(r["stance"])
    if sb != "mixed_or_neutral":
        bits.append(sb)
    tb = trust_band(r["trust"])
    if tb != "uncertain_or_moderate":
        bits.append("trusts you" if tb == "high" else "distrusts you")
    if r["fear"] >= 50:
        bits.append("fears you")
    elif r["fear"] >= 25:
        bits.append("wary of you")
    if r["resentment"] >= 35:
        bits.append("resents you")
    if r["respect"] >= 50:
        bits.append("respects you")
    elif r["respect"] <= -35:
        bits.append("holds you in contempt")
    return ("; ".join(bits) or None), r["familiarity"]


def standing(conn: sqlite3.Connection, observer_id: int | None, subject_id: int, place_id: int | None) -> dict[str, str]:
    """How `subject` stands to `observer` in words. observer None gives the public view of the subject
    (what a stranger in the room reads). Keys are omitted when unknown."""
    obs = None if observer_id is None else int(observer_id)
    subj = int(subject_id)
    day = _day(conn)
    out: dict[str, str] = {}
    age = _age_band(conn, subj, day)
    if age:
        out["age"] = age

    station, ranked = _station(conn, subj)
    kin = _kin(conn, obs, subj) if obs is not None and obs != subj else None
    house = _house(conn, obs, subj)
    toward, fam = (None, 0.0)
    if obs is not None and obs != subj:
        toward, fam = _toward(conn, subj, obs)

    # Bearing: only where the Stage is visible or known, since Presence is not a scanner [352].
    visible = bool(station and ranked)
    known = bool(kin or house or fam >= 30 or _is_famous(conn, subj))
    stage = conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?", (subj,)).fetchone()
    if stage and stage[0] in STAGES and (visible or known):
        idx = STAGES.index(stage[0]) + (0 if place_id is None or location_in_hearth(conn, place_id) else 1)
        out["bearing"] = _reading(conn, subj, idx, STAGES.index(stage[0]))
    if station:
        out["station"] = station
    if kin:
        out["kin"] = kin
    if house:
        out["house"] = house
    if toward:
        out["toward"] = toward
    if obs is not None and obs != subj:
        if kin or house or fam >= 25:
            out["knows"] = "knows you"
        elif fam > 0 or _is_famous(conn, obs):
            out["knows"] = "knows of you"
        else:
            out["knows"] = "does not know you"

    # Origin: only people with a home, and only when it is another polity than this place's.
    home = conn.execute("SELECT home_location_id FROM actors WHERE id=?", (subj,)).fetchone()
    if home and home[0] is not None and place_id is not None:
        theirs, here = polity_of(conn, home[0]), polity_of(conn, place_id)
        if theirs and here and theirs != here:
            out["from"] = f"from {_short_polity(theirs)}, an outsider here"
    return out
