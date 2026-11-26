"""What a player says about his own family is canon for his character (owner rule, 2026-11-23).

Pure reading and plausibility of the `family` / `family_business` parts of a protagonist proposal. Nothing here touches the
database or draws a random number except the unsaid ages, which come from a seeded stream (`unsaid_ages`).

Read: parents (each alive, dead or unsaid, with an optional age, name and work), siblings (each with a stated sex and age, or only
counted), and the family business (who owns it, who works in it). The engine refuses only a real clash with an established fact
or a statement that is very implausible for the place and time; a refusal names the clash and its reason in words.
No world words here: every phrase is ordinary English.
"""
from __future__ import annotations

import random
import re
from typing import Any

from .veto import Contradiction

_NUM = {"no": 0, "none": 0, "zero": 0, "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_ALIVE = re.compile(r"\b(alive|living|lives|live|around|still|well|healthy|with us|surviv)")
_DEAD = re.compile(r"\b(dead|died|dies|passed|deceased|late|gone|orphan|buried|killed)")
_FATHER = re.compile(r"\b(father|dad|papa|pa|pop|old man)\b")
_MOTHER = re.compile(r"\b(mother|mom|mum|mama|ma)\b")
_BROTHER = re.compile(r"\bbrothers?\b")
_SISTER = re.compile(r"\bsisters?\b")
_WORKING = ("self", "me", "myself", "protagonist", "him", "he")

# a mother bears children between these ages; a father may be older. Plausibility, not a rate: outside them the claim is refused.
MOTHER_BIRTH = (14, 52)
FATHER_BIRTH = (15, 75)
OLDEST_LIVING = 105
MIN_WORKING_AGE = 12


def _spec(alive=None, age=None, name=None, work=None) -> dict:
    return {"alive": alive, "age": age, "name": name, "work": work}


def _state_of(text: str) -> bool | None:
    dead, alive = bool(_DEAD.search(text)), bool(_ALIVE.search(text))
    if dead and not alive:
        return False
    if alive and not dead:
        return True
    return None


def _age_in(text: str) -> int | None:
    m = re.search(r"\b(\d{2,3})\b", text)
    return int(m.group(1)) if m else None


def _read_parent_item(item: Any, out: dict) -> None:
    if isinstance(item, dict):
        role = str(item.get("as") or item.get("role") or item.get("relation") or item.get("who") or item.get("kind") or "").lower()
        which = "father" if _FATHER.search(role) else "mother" if _MOTHER.search(role) else None
        if which is None:
            return
        alive = item.get("alive")
        if alive is None and item.get("status"):
            alive = _state_of(str(item["status"]).lower())
        age = item.get("age")
        out[which] = _spec(alive if alive is None else bool(alive), int(age) if isinstance(age, (int, float)) and not isinstance(age, bool) else None,
                           item.get("name"), item.get("work") or item.get("occupation"))
        return
    _read_parent_text(str(item), out)


def _read_parent_text(text: str, out: dict) -> None:
    t = text.lower()
    if re.search(r"\borphan|both (of )?(my |his |her )?parents (are |were )?(dead|gone|deceased)|both (are )?dead|parents (are |were )?(dead|deceased|gone)", t):
        out["father"], out["mother"] = _spec(False), _spec(False)
        return
    if re.search(r"\b(both|parents)\b", t) and not _FATHER.search(t) and not _MOTHER.search(t):
        st = _state_of(t)
        if st is not None:
            out["father"], out["mother"] = _spec(st), _spec(st)
            return
    for clause in re.split(r"[,;.]|\band\b|\bbut\b", t):
        which = "father" if _FATHER.search(clause) else "mother" if _MOTHER.search(clause) else None
        if which is None:
            continue
        out[which] = _spec(_state_of(clause), _age_in(clause))


def read_parents(v: Any) -> dict:
    """{"father": spec|None, "mother": spec|None}; None = unsaid."""
    out: dict[str, dict | None] = {"father": None, "mother": None}
    if v is None:
        return out
    if isinstance(v, dict):
        keyed = False
        for k, val in v.items():
            kk = str(k).lower()
            which = "father" if _FATHER.search(kk) else "mother" if _MOTHER.search(kk) else None
            if which is None:
                continue
            keyed = True
            if isinstance(val, dict):
                _read_parent_item({**val, "as": which}, out)
            elif isinstance(val, bool):
                out[which] = _spec(val)
            else:
                st = _state_of(str(val).lower())
                out[which] = _spec(st, _age_in(str(val)))
        if not keyed:
            _read_parent_item(v, out)
        return out
    for item in (v if isinstance(v, (list, tuple)) else [v]):
        _read_parent_item(item, out)
    return out


def _sibling_dict(d: dict) -> dict | None:
    role = " ".join(str(d.get(k) or "") for k in ("sex", "gender", "as", "role", "relation", "kind", "who")).lower()
    sex = "male" if re.search(r"\b(male|man|boy|brother|son)\b", role) else "female" if re.search(r"\b(female|woman|girl|sister|daughter)\b", role) else None
    age = d.get("age")
    alive = d.get("alive")
    if alive is None and d.get("status"):
        alive = _state_of(str(d["status"]).lower())
    return {"sex": sex, "age": int(age) if isinstance(age, (int, float)) and not isinstance(age, bool) else None,
            "alive": True if alive is None else bool(alive), "name": d.get("name"), "work": d.get("work") or d.get("occupation"),
            "half": bool(d.get("half")) or "half" in role, "younger": "younger" in role, "older": "older" in role}


def read_siblings(v: Any) -> list[dict] | None:
    """A list of {sex, age, alive, name, work, half}; None = unsaid; [] = stated none."""
    if v is None:
        return None
    if isinstance(v, bool):
        return [] if not v else None
    if isinstance(v, int):
        return [_sibling_dict({}) for _ in range(v)]
    if isinstance(v, dict):
        return [s for s in [_sibling_dict(v)] if s]
    items = v if isinstance(v, (list, tuple)) else [v]
    out: list[dict] = []
    for it in items:
        if isinstance(it, dict):
            s = _sibling_dict(it)
            if s:
                out.append(s)
            continue
        out.extend(_siblings_in_text(str(it)))
    return out


def _siblings_in_text(text: str) -> list[dict]:
    t = text.lower()
    if re.search(r"\b(only child|no (brothers|sisters|siblings)|none|only one)\b", t) and not re.search(r"\d", t):
        return []
    found: list[dict] = []
    # per-person phrases: "21 year old brother", "a sister, 16", "brother (18)"
    per = re.findall(r"(\d{1,2})[\s-]*(?:years?[\s-]*old|yo|y/o)?\s*(brother|sister)", t) or \
        [(b, a) for a, b in re.findall(r"(brother|sister)s?\s*[\(,:]?\s*(?:aged|age|of|is|are)?\s*(\d{1,2})\b", t)]
    if per:
        for age, word in per:
            found.append({"sex": "male" if word == "brother" else "female", "age": int(age), "alive": True, "name": None, "work": None,
                          "half": "half" in t, "younger": "younger" in t, "older": "older" in t})
        return found
    ages = [int(x) for x in re.findall(r"\b(\d{1,2})\b", t)]
    bro, sis = bool(_BROTHER.search(t)), bool(_SISTER.search(t))
    sex = "male" if bro and not sis else "female" if sis and not bro else None
    if ages:
        return [{"sex": sex, "age": a, "alive": True, "name": None, "work": None, "half": "half" in t, "younger": "younger" in t,
                 "older": "older" in t} for a in ages]
    n = None
    m = re.search(r"\b(" + "|".join(_NUM) + r"|\d+)\b(?:\s+\w+){0,2}?\s+(brothers?|sisters?|siblings?)", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUM[m.group(1)]
    elif bro or sis or "sibling" in t:
        n = 1
    return [{"sex": sex, "age": None, "alive": True, "name": None, "work": None, "half": "half" in t, "younger": "younger" in t,
             "older": "older" in t} for _ in range(n or 0)]


def read_business(proposal: dict) -> dict | None:
    """The family business the player stated: {name, type, owner, works: [self|siblings|index...]}. It is stated when the proposal names
    an owner other than himself (`family_business`, or an `affiliation` with an `owner`). Returns None otherwise."""
    for src in (proposal.get("family_business"), proposal.get("affiliation")):
        if not isinstance(src, dict):
            continue
        owner = src.get("owner") or src.get("owned_by")
        if owner is None:
            continue
        o = str(owner).lower()
        if o in _WORKING or o in ("himself", "myself"):
            continue
        who = "father" if _FATHER.search(o) else "mother" if _MOTHER.search(o) else None
        if who is None:
            continue
        works = src.get("works") or src.get("employees") or src.get("staff")
        works = [works] if isinstance(works, str) else list(works or [])
        works = [str(w).lower() for w in works]
        if src is proposal.get("affiliation") and not works:
            works = ["self"]  # he named it as where he belongs: he works there
        return {"name": src.get("name") or src.get("text"), "type": src.get("type") or src.get("trade") or src.get("kind") or src.get("name"),
                "owner": who, "works": works, "role": src.get("role")}
    return None


DRAWN_MOTHER_AT = 17


def unsaid_ages(rng: random.Random, age: int, parents: dict, sibs: list[dict]) -> None:
    """Fill the ages the player left unsaid, in place, so that each mother's age at each birth is one she can bear a child at.
    A draw inside the window; never a clamp of a stated age."""
    stated_ages = [s["age"] for s in sibs if s["age"] is not None]
    kids = [age] + stated_ages
    lo_m = max(kids) + MOTHER_BIRTH[0]
    hi_m = min(kids) + MOTHER_BIRTH[1]
    # sibling ages left unsaid: younger when the player said so, else near his own; birth spacing of about two years
    k = 0
    for s in sibs:
        if s["age"] is not None:
            continue
        k += 1
        gap = max(1, int(round(rng.gauss(2.5, 1.2)))) + 2 * (k - 1)
        older = bool(s.get("older"))
        s["age_filled"] = True
        s["age"] = age + gap if older else max(0, age - gap) if (s.get("younger") or rng.random() < 0.55) else age + gap
        kids.append(s["age"])
    from .opening_family import YOUNGEST_FATHER
    lo_m, hi_m = max(kids) + MOTHER_BIRTH[0], min(kids) + MOTHER_BIRTH[1]
    mother = parents["mother"]
    if mother is not None and mother["age"] is None and mother["alive"] is not False:
        grown = max(lo_m, min(max(kids) + DRAWN_MOTHER_AT, hi_m))  # a drawn mother was no child at her eldest's birth
        for _ in range(60):
            cand = min(kids) + int(round(rng.gauss(27, 4.5)))
            if grown <= cand <= hi_m:
                break
        else:
            cand = (grown + hi_m) // 2
        mother["age"] = cand
    father = parents["father"]
    if father is not None and father["age"] is None and father["alive"] is not False:
        base = mother["age"] if mother and mother["age"] is not None else min(kids) + 28
        grown = max(kids) + YOUNGEST_FATHER
        for _ in range(60):
            cand = base + int(round(rng.gauss(3, 3.5)))
            if cand >= grown:
                break
        else:
            cand = grown + rng.randrange(6)
        father["age"] = cand


def check(age: int, parents: dict, sibs: list[dict], business: dict | None) -> None:
    """Raise Contradiction (in words, with the reason) for a family that clashes inside itself or is very implausible for the time."""
    kids = [age] + [s["age"] for s in sibs if s["age"] is not None]
    for who, spec in parents.items():
        if spec is None or spec["alive"] is False:
            continue
        a = spec["age"]
        if a is None:
            continue
        if a > OLDEST_LIVING:
            raise Contradiction(f"his {who} cannot be {a} and alive: nobody that old is living in this city")
        lo, hi = MOTHER_BIRTH if who == "mother" else FATHER_BIRTH
        for ka in kids:
            if not lo <= a - ka <= hi:
                what = "a mother can bear a child only between about 14 and 52" if who == "mother" else "a father is at least 15 years older than his child"
                raise Contradiction(f"his {who} is {a}, so he or his sibling aged {ka} would have been born when she/he was {a - ka}: {what}; "
                                    "change the age, or make them half-siblings or step-parents")
    full = [s for s in sibs if s["age"] is not None and not s.get("half")]
    if full and max(kids) - min(kids) > MOTHER_BIRTH[1] - MOTHER_BIRTH[0] - 4:
        raise Contradiction(f"siblings {min(kids)} and {max(kids)} years old cannot share a mother: that is wider than the years a woman can bear "
                            "children; make the oldest or youngest a half-sibling")
    if business is not None:
        owner = parents.get(business["owner"])
        if owner is not None and owner["alive"] is False:
            raise Contradiction(f"his {business['owner']} is stated dead, so he cannot be the one who owns and runs the {business.get('name') or 'business'} "
                                "today; say who owns it, or that it passed to someone")
        if any(w in ("self", "me", "myself", "protagonist") for w in business["works"]) and age < MIN_WORKING_AGE:
            raise Contradiction(f"a child of {age} does not work in a shop in this world; he can help out after school at 12 or more")
        if any(w in ("siblings", "brothers", "sisters", "sons", "all") for w in business["works"]):
            for s in sibs:
                if s["age"] is not None and s["age"] < MIN_WORKING_AGE and s["alive"]:
                    raise Contradiction(f"a sibling of {s['age']} does not work there: a child under {MIN_WORKING_AGE} is not employed")
