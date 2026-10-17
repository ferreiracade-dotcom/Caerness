"""Authoring: the GM's invented people, businesses, bodies and rumours become real only through existing engine paths.

The engine is a veto, not a menu (engine/veto.py): free text in, nothing refused for being unlisted. A refusal names the fact it
contradicts; where a request is only larger than the place can supply, what the world can supply is made and the rest is reported
in `scaled_down`. People are pre-existing background identities of the settlement (population-preserving); the engine never hands
the protagonist money, people, ownership of existing things or authority. The protagonist may found something new that is in
proportion to the place, paid from his own purse.
"""
from __future__ import annotations

import json
import math
import random
import re
import sqlite3
from typing import Any

from . import ledger, veto
from .household_life import _actor_is_living, _family_name, add_kinship, create_union, _has_active_union, prohibited_union_kinship_reason
from .person_ecology import FIRST_FEMALE, FIRST_MALE, _free_name, find_background_candidate, resolve_background_person
from .relationships import ensure_relationship


class AuthoringRefused(ValueError):
    """The world has no such thing here; the message says why. reason_kind: `contradiction` (a fact of the world or a canon rule
    clashes: show it as story) or `input_gap` (the request was malformed: rephrase and retry)."""

    def __init__(self, msg: str, reason_kind: str = "contradiction"):
        super().__init__(msg)
        self.reason_kind = reason_kind


STAGE_NAMES = ("First", "Temper", "Third", "Breach", "Fifth", "Sixth")


def _no(msg: str, kind: str = "contradiction"):
    raise AuthoringRefused(msg, kind)


def _domain(fn, *a, **k):
    """Calls whose ValueError is the engine's own domain refusal (a kinship or union it will not record)."""
    try:
        return fn(*a, **k)
    except AuthoringRefused:
        raise
    except ValueError as e:  # includes veto.Contradiction
        raise AuthoringRefused(str(e)) from e


def _marry(conn, aid: int, tid: int, sex: str, me_age: int, day: int, call_id: str) -> None:
    """Authored spouses have been married a while: they share one household and the union is dated in the past."""
    husband, wife = (aid, tid) if sex == "male" else (tid, aid)
    hh = conn.execute("""SELECT household_id FROM household_members WHERE actor_id=? AND status='active'
                         ORDER BY (role='head') DESC, household_id LIMIT 1""", (tid,)).fetchone()
    if hh is None:
        hh = conn.execute("SELECT current_household_id FROM actor_life_profiles WHERE actor_id=? AND current_household_id IS NOT NULL", (tid,)).fetchone()
    if hh is not None:
        uid = _domain(create_union, conn, husband, wife, household_id=int(hh[0]))
    else:
        hname = conn.execute("SELECT name FROM actors WHERE id=?", (husband,)).fetchone()[0]
        wname = conn.execute("SELECT name FROM actors WHERE id=?", (wife,)).fetchone()[0]
        uid = _domain(create_union, conn, husband, wife, create_new_household_name=f"Household of {hname} and {wname}")
    younger = min(me_age, _age(conn, tid, day))
    years = random.Random(f"{call_id}:{husband}:{wife}").randint(1, max(1, min(30, younger - 18)))
    start = day - years * 365
    conn.execute("UPDATE household_unions SET started_day=? WHERE id=?", (start, uid))
    conn.execute("""UPDATE kinship_links SET started_day=? WHERE kin_kind='spouse' AND actor_a_id IN (?,?) AND actor_b_id IN (?,?)""",
                 (start, husband, wife, husband, wife))
    conn.execute("UPDATE life_events SET day=? WHERE event_kind='union' AND day=? AND actor_id=? AND related_actor_id=?", (start, day, husband, wife))
    if hh is None:
        hid = conn.execute("SELECT household_id FROM household_unions WHERE id=?", (uid,)).fetchone()[0]
        conn.execute("UPDATE households SET created_day=? WHERE id=?", (start, hid))
        conn.execute("UPDATE life_events SET day=? WHERE event_kind='household_formation' AND day=? AND household_id=?", (start, day, hid))


def _lives_in(conn, aid: int, loc: int) -> bool:
    """He lives in the place, or in the settlement a district belongs to."""
    r = conn.execute("SELECT home_location_id,current_location_id FROM actors WHERE id=?", (aid,)).fetchone()
    here = veto.settlement_of(conn, loc)
    for x in (r[0], r[1]):
        if x is not None and (int(x) == loc or (here is not None and veto.settlement_of(conn, int(x)) == here)):
            return True
    return False


def _settled(conn, loc: int, who: int, what: str) -> int:
    """Somebody lives at the place (a district counts by its parent city), and the owner/leader is one of them."""
    pop = _population(conn, loc)
    if pop <= 0:
        _no("nobody lives there")
    if not _lives_in(conn, who, loc):
        _no(f"{what} must live there")
    return pop


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _text(v: Any, field: str, n: int) -> str:
    s = " ".join(str(v or "").split())
    if not 1 <= len(s) <= n:
        _no(f"{field} must be 1-{n} characters", "input_gap")
    return s


def _place(conn, me: int, d: dict) -> int:
    loc = d.get("location_id")
    if loc is None and d.get("place"):
        loc = veto.find_location(conn, d.get("place"))
        if loc is None:
            _no(f"there is no place called {d.get('place')!r}")
    if loc is None:
        loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(me),)).fetchone()[0]
    if loc is None or not conn.execute("SELECT 1 FROM locations WHERE id=?", (int(loc),)).fetchone():
        _no("unknown location")
    return int(loc)


def _population(conn, loc: int) -> int:
    """The people of the place; a district counts by its parent city."""
    return int(veto.place_scale(conn, loc)["population"])


def _character(conn, aid: Any, what: str) -> int:
    try:
        aid = int(aid)
    except (TypeError, ValueError):
        _no(f"{what} must be an actor id", "input_gap")
    r = conn.execute("SELECT actor_type,status FROM actors WHERE id=?", (aid,)).fetchone()
    if not r or r[0] != "character" or r[1] != "active" or not _actor_is_living(conn, aid):
        _no(f"{what} must be a living character")
    return aid


def _his_person(conn, me: int, aid: int) -> bool:
    """The protagonist, or anyone in an outfit, business or household he belongs to or controls."""
    if aid == me:
        return True
    for (org,) in conn.execute("SELECT organization_id FROM underworld_personnel WHERE actor_id=? AND status='active'", (aid,)).fetchall():
        if ledger.can_draw(conn, me, ("outfit", int(org))) or conn.execute(
                "SELECT 1 FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'", (me, org)).fetchone():
            return True
    for (eid,) in conn.execute("SELECT enterprise_id FROM enterprise_staff WHERE actor_id=? AND status='active'", (aid,)).fetchall():
        if ledger.can_draw(conn, me, ("business", int(eid))):
            return True
    for (hid,) in conn.execute("SELECT household_id FROM household_service_terms WHERE actor_id=? AND status='active'", (aid,)).fetchall():
        if ledger.can_draw(conn, me, ("household", int(hid))):
            return True
    return False


def _not_his(conn, me: int, aid: int, what: str) -> None:
    if aid == me:
        _no(f"{what} cannot be the protagonist")
    if _his_person(conn, me, aid):
        _no(f"{what} cannot be one of his people; that is for act hire")


def _age(conn, aid: int, day: int) -> int:
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
    return int((day - r[0]) // 365) if r and r[0] is not None else 0


def _sex(conn, aid: int) -> str | None:
    r = conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
    return r[0] if r else None


def _stage_name(text: Any) -> str | None:
    """Free text to a Stage name, or None when no Stage is claimed ("a quiet talent")."""
    t = str(text or "").lower()
    return next((s for s in STAGE_NAMES if s.lower() in t), None)


_TIE_WORDS = (("spouse", ("spouse", "wife", "husband", "married", "partner")), ("sibling", ("sibling", "brother", "sister")),
              ("parent", ("parent", "father", "mother", "dad", "mum")), ("child", ("child", "son", "daughter", "kid")))


def _tie_kind(text: Any) -> str:
    """Free relation text to the nearest kind of tie: spouse, sibling, parent, child, else just acquaintance."""
    t = str(text or "knows").lower()
    for kind, words in _TIE_WORDS:
        if any(w in t for w in words):
            return kind
    return "knows"


def _afford(conn, me: int, amount: float) -> float:
    """What he can put in from his own purse; money is never granted."""
    return min(float(amount), ledger.balance(conn, ("person", int(me))))


# ---------------------------------------------------------------- person

def _pick_args(*, loc, sex, age, work_domain, stage, elsewhere, retired=False, exact_stage=False, window=3) -> dict:
    return dict(location_id=loc, occupation_domains=(work_domain,) if work_domain else None,
                min_age=max(age - window, 45 if retired else 0) if age else (45 if retired else 18),
                max_age=(age + window) if age else 85, require_open_core=True if stage else None, required_stage=stage,
                demographic_sex=sex, allow_elsewhere=elsewhere, strict_stage=True, prefer_open_core=bool(stage), exact_stage=exact_stage)


def materialise_person(conn, *, loc, sex, age, work_domain, stage, elsewhere, name, pick_seed, call_id, retired=False,
                       out: dict | None = None, reason: str = "Authored in play", notes: str = "Authored in play from a pre-existing identity.",
                       pick: dict | None = None, exact_stage: bool = False, pool_loc: int | None = None, window: int = 3,
                       growth_batches: int | None = None) -> int:
    """Pick one pre-existing identity of the place, reveal it, relocate an outsider, make it TRACKED and present there."""
    day = _day(conn)
    pool = pool_loc if pool_loc is not None else veto.settlement_of(conn, loc)
    pick = pick or _pick_args(loc=pool if pool is not None else loc, sex=sex, age=age, work_domain=work_domain, stage=stage,
                              elsewhere=elsewhere, retired=retired, exact_stage=exact_stage, window=window)
    aid = resolve_background_person(conn, reason=reason, demand_kind="authoring", subtype=f"authored_{work_domain or 'person'}",
                                    name=name, pick_seed=pick_seed, growth_batches=growth_batches, **pick)
    if aid is None:
        _no(f"the settlement's population cannot supply that person{'' if elsewhere else ' (try from_elsewhere)'}; adapt the story")
    cur = int(conn.execute("SELECT current_location_id FROM actors WHERE id=?", (aid,)).fetchone()[0])
    if cur != loc:
        if veto.settlement_of(conn, cur) != veto.settlement_of(conn, loc) and out is not None:
            out["origin"] = conn.execute("SELECT name FROM locations WHERE id=?", (cur,)).fetchone()[0]
        conn.execute("UPDATE actors SET current_location_id=?,home_location_id=? WHERE id=?", (loc, loc, aid))  # an outsider has moved here
    from .resolution_controller import _sync_sim_tier
    _sync_sim_tier(conn, aid, "TRACKED", day)  # resolution already made them TRACKED; give them a life of their own
    conn.execute("UPDATE actors SET notes=? WHERE id=?", (notes, aid))
    # Whoever the GM just placed is there now, and keeps coming back: a home habit here, plus today for certain.
    from .presence import add_presence_habit, ensure_presence_profile
    ensure_presence_profile(conn, aid, base_location_id=loc, source_kind="authored", confidence=0.9, effective_from_day=day)
    add_presence_habit(conn, aid, loc, habit_kind="home", weight=0.97, cadence_days=1, basis_kind="actor_home", basis_id=aid,
                       source_kind="authored", confidence=1.0, effective_from_day=day)
    add_presence_habit(conn, aid, loc, habit_kind="frequented", weight=1.0, cadence_days=1, basis_kind="authored", basis_id=aid,
                       source_kind="authored", confidence=1.0, effective_from_day=day, effective_to_day=day)
    return aid


def _person(conn, me: int, d: dict, call_id: str) -> dict:
    sex = d.get("sex")
    if sex is not None and sex not in ("male", "female"):
        _no("sex, if given, must be male or female", "input_gap")
    age = d.get("age")
    if age is not None and (isinstance(age, bool) or not isinstance(age, int) or not 0 <= age <= 110):
        _no("age must be a whole number of years", "input_gap")
    work_text = d.get("work")
    work = veto.categorise(work_text, d.get("category")) if work_text else None
    stage = _stage_name(d.get("stage"))
    retired = bool(work and work not in ("soldier", "criminal") and stage in ("Breach", "Fifth", "Sixth"))
    if retired and age is not None and age < 45:
        _no(f"a {work} at that Stage is unheard of unless a retired master (aged 45 or more)")
    _domain(veto.stage_plausible, age if age is not None else 45, work or "soldier", stage)
    loc = _place(conn, me, d)
    elsewhere = bool(d.get("from_elsewhere", False))
    wants = _text(d["wants"], "wants", 200) if d.get("wants") is not None else None
    full = None
    if d.get("name") is not None:
        full = _text(d["name"], "name", 60)  # a single name ("Brother Tam") is a name
        _domain(veto.canon_figure, conn, full)
        _domain(veto.name_taken, conn, full)
        implied = _domain(veto.name_sex, full, sex)
        sex = sex or implied
    sex_drawn = sex is None
    if sex_drawn:  # nobody said: the name, else a seeded roll
        from .demographic_sex import seeded_sex
        sex = seeded_sex(f"authored:{call_id}")
    ties = d.get("ties") or []
    if not isinstance(ties, list) or len(ties) > 25:
        _no("ties must be a list of at most 25", "input_gap")
    seen = set()
    for t in ties:
        if not isinstance(t, dict) or t.get("actor_id") is None:
            _no("each tie needs an actor_id and, in your own words, how they are related (as)", "input_gap")
        t["_kind"] = _tie_kind(t.get("as"))
        tid = _character(conn, t.get("actor_id"), "a tie")
        if tid in seen:
            _no("a person can be tied only once to the same actor")
        seen.add(tid)
        if t["_kind"] != "knows" and tid == me:
            _no("the protagonist cannot be given new kin; only a passing acquaintance")
    notes = [int(n) for n in (d.get("from_notes") or [])]
    if notes:
        have = {r[0] for r in conn.execute(
            f"SELECT id FROM gm_notes WHERE subject_kind='general' AND id IN ({','.join('?' * len(notes))})", notes)} \
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='gm_notes'").fetchone() else set()
        for n in notes:
            if n not in have:
                _no(f"note {n} is not a general note that can be attached")

    day = _day(conn)
    pool = veto.settlement_of(conn, loc)
    pick = _pick_args(loc=pool if pool is not None else loc, sex=sex, age=age, work_domain=work, stage=stage, elsewhere=elsewhere, retired=retired)
    # A wife or a man's sibling/child carries his family name; the given name still comes from the identity.
    if full is None:
        for t in ties:
            tid = int(t["actor_id"])
            fam = _family_name(conn.execute("SELECT name FROM actors WHERE id=?", (tid,)).fetchone()[0])
            if fam and _sex(conn, tid) == "male" and (t["_kind"] in ("sibling", "child") or (t["_kind"] == "spouse" and sex == "female")):
                prof = find_background_candidate(conn, **pick)
                if prof is not None:
                    full = _free_name(conn, str(prof["given_name"]), fam, sex, int(prof["partition_id"]) * 10000 + int(prof["local_uid"]))
                break
    got: dict = {}
    down: list[dict] = []
    other = "female" if sex == "male" else "male"
    # What the people there can supply: as asked; a drawn sex may be the other one; a trade nobody there follows is relaxed and said so.
    tries = [(sex, work)] + ([(other, work)] if sex_drawn and full is None else []) + (
        [(sex, None)] + ([(other, None)] if sex_drawn and full is None else []) if work and stage is None else [])
    aid = None
    for i, (sx, wk) in enumerate(tries):
        try:
            aid = materialise_person(conn, loc=loc, sex=sx, age=age, work_domain=wk, stage=stage, elsewhere=elsewhere, name=full,
                                     pick_seed=None, call_id=call_id, retired=retired, out=got,
                                     pick=_pick_args(loc=pool if pool is not None else loc, sex=sx, age=age, work_domain=wk, stage=stage,
                                                     elsewhere=elsewhere, retired=retired))
        except AuthoringRefused:
            if i == len(tries) - 1:
                raise
            continue
        sex = sx
        if wk != work:
            down.append({"asked": str(work_text), "got": "ordinary work", "why": "nobody of that trade could be found among the people there"})
        break
    prof = conn.execute("SELECT * FROM background_person_profiles WHERE actor_id=?", (aid,)).fetchone()
    origin = got.get("origin")
    me_age = _age(conn, aid, day)

    for t in ties:
        tid, kind = int(t["actor_id"]), t["_kind"]
        if kind == "knows":
            for a, b in ((aid, tid), (tid, aid)):
                ensure_relationship(conn, a, b, day, familiarity=10)
        elif kind == "sibling":
            if abs(me_age - _age(conn, tid, day)) > 25:
                _no("siblings must be within 25 years of each other")
            _domain(add_kinship, conn, aid, tid, "sibling", reciprocal_kind="sibling")
        elif kind in ("parent", "child"):
            gap = (me_age - _age(conn, tid, day)) if kind == "parent" else (_age(conn, tid, day) - me_age)
            if not 15 <= gap <= 55:
                _no("a parent must be 15 to 55 years older than the child")
            _domain(add_kinship, conn, *((aid, tid) if kind == "parent" else (tid, aid)), "parent", reciprocal_kind="child")
        else:
            if min(me_age, _age(conn, tid, day)) < 18 or _sex(conn, tid) == sex:
                _no("no union: both must be adults of opposite sex")
            if _has_active_union(conn, tid):
                _no("no union: that person is already married")
            why = prohibited_union_kinship_reason(conn, aid, tid)
            if why:
                _no(f"no union between close kin ({why})")
            _marry(conn, aid, tid, sex, me_age, day, call_id)
    if wants:
        conn.execute("INSERT INTO goals(actor_id,description,priority,progress,status,created_day) VALUES (?,?,50,0,'active',?)", (aid, wants, day))
    for n in notes:
        conn.execute("UPDATE gm_notes SET subject_kind='actor',subject_id=? WHERE id=?", (aid, n))
    name = conn.execute("SELECT name FROM actors WHERE id=?", (aid,)).fetchone()[0]
    return {"status": "created", "kind": "person", "actor_id": aid, "name": name, "sex": sex, "age": me_age,
            "work": prof["occupation_domain"], "location": conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()[0],
            "from": origin, **({"scaled_down": down} if down else {})}


# ---------------------------------------------------------------- business

_BY_WORD = (("inn", "inn"), ("tavern", "tavern"), ("ale", "tavern"), ("cloth", "cloth_shop"), ("tailor", "tailor"), ("weav", "weaver"), ("book", "bookshop"),
            ("scribe", "bookshop"), ("ink", "bookshop"), ("medicine", "medicine_shop"), ("herb", "medicine_shop"), ("physician", "physician_practice"),
            ("healer", "physician_practice"), ("smith", "smithy"), ("forge", "smithy"), ("courier", "wholesaler"), ("warehouse", "wholesaler"),
            ("brothel", "pleasure_house"), ("gambl", "gambling_house"), ("dice", "gambling_house"), ("lend", "moneylender"), ("loan", "loan_house"),
            ("pawn", "pawnbroker"), ("lamp", "carpenter"), ("food", "food_shop"), ("bak", "food_shop"), ("grocer", "food_shop"))


def _archetype(trade: str, hint: str | None = None) -> tuple[str, str]:
    """(archetype key, enterprise kind) for free trade text: a scored keyword map over the archetypes, else a wholesaler."""
    from .business import _ARCHETYPES
    t = f"{trade} {hint or ''}".lower().replace("-", " ").replace("_", " ")
    best, score = "wholesaler", 0
    for key, a in _ARCHETYPES.items():
        words = set(key.split("_")) | set(str(a["name"]).lower().replace("/", " ").split())
        s = sum(len(w) for w in words if len(w) > 2 and w in t)
        if s > score:
            best, score = key, s
    for word, key in _BY_WORD:
        if word in t and key in _ARCHETYPES and len(word) >= score:
            best, score = key, len(word)
    return best, str(_ARCHETYPES[best]["enterprise_kind"])


def _scope(conn, loc: int) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        "WITH RECURSIVE t(id) AS (SELECT ? UNION SELECT l.id FROM locations l JOIN t ON l.parent_location_id=t.id) SELECT id FROM t",
        (veto.settlement_of(conn, loc) or loc,))]


def _authored_count(conn, loc: int, table: str) -> int:
    scope = _scope(conn, loc)
    q = ",".join("?" * len(scope))
    if table == "enterprise":
        return int(conn.execute(f"SELECT COUNT(*) FROM civilian_enterprises WHERE location_id IN ({q}) AND status IN ('active','strained','insolvent') "
                                "AND json_extract(metadata_json,'$.authored')=1", scope).fetchone()[0])
    if table == "outfit":
        return int(conn.execute(f"SELECT COUNT(*) FROM underworld_organizations WHERE primary_location_id IN ({q}) AND status IN ('active','strained','fragmented') "
                                "AND json_extract(metadata_json,'$.authored')=1", scope).fetchone()[0])
    return int(conn.execute(f"SELECT COUNT(*) FROM actors a JOIN institution_memberships m ON m.institution_actor_id=a.id AND json_extract(m.metadata_json,'$.authored')=1 "
                            f"WHERE a.actor_type='institution' AND a.status='active' AND a.current_location_id IN ({q})", scope).fetchone()[0])


def _owner_means(conn, owner: int) -> float:
    try:
        from .health import _family_means
        return _family_means(conn, [owner])[0]
    except Exception:
        return 50.0


def _founded_capital(conn, me: int) -> float:
    """What he has already put into businesses he founded (it counts against the place's proportion)."""
    return float(conn.execute("SELECT COALESCE(SUM(capital),0) FROM civilian_enterprises WHERE owner_actor_id=? "
                              "AND json_extract(metadata_json,'$.founded_by_protagonist')=1", (me,)).fetchone()[0])


def _business(conn, me: int, d: dict, call_id: str) -> dict:
    name = _text(d.get("name"), "name", 80)
    trade = _text(d.get("trade") or d.get("type") or name, "trade", 80)
    loc = _place(conn, me, d)
    owner_arg = d.get("owner_actor_id")
    founding = owner_arg is None or (str(owner_arg).lstrip("-").isdigit() and int(owner_arg) == int(me))
    owner = int(me) if founding else _character(conn, owner_arg, "owner_actor_id")
    if not founding:
        _not_his(conn, me, owner, "the owner")
    if conn.execute("SELECT 1 FROM civilian_enterprises WHERE name=? AND location_id=?", (name, loc)).fetchone():
        _no(f"a business called {name} already stands here")
    _settled(conn, loc, owner, "the owner")
    sc = veto.place_scale(conn, loc)
    cap_new = max(1, math.ceil(veto.PROPORTION["business_share"] * max(sc["enterprises"], sc["population"] / 1000.0)))
    if _authored_count(conn, loc, "enterprise") >= cap_new:
        _no("the town has no room for another business of that kind")
    archetype, kind = _archetype(trade, d.get("enterprise_kind"))
    word = d.get("amount", d.get("capital"))
    if word is not None:
        try:
            asked = ledger.amount_of(word, None)
        except ValueError as e:
            _no(str(e), "input_gap")
    else:
        asked = round(2.0 * max(0.5, _owner_means(conn, owner) / 50.0), 2)  # a modest start for the owner's means
    adj, down = veto.holdings_in_proportion(conn, loc, [{"kind": trade, "name": name, "amount": asked}],
                                            prior_wealth=_founded_capital(conn, me) if founding else 0.0)
    if not adj:
        _no("the town has no room for another business of that kind")
    means = float(adj[0]["amount"])
    if founding:  # he pays for what he founds, from his own purse; never more than he has
        got = round(_afford(conn, me, means), 2)
        if got < 0.2:
            _no("he does not have the money to found it")
        if got < means - 0.01:
            down.append({"asked": ledger.scale_word(means), "got": ledger.scale_word(got), "why": "that is all he can put into it"})
        means = got
        ledger._debit(conn, ("person", int(me)), means)
    from .civilian import create_enterprise
    from .merchant import add_enterprise_staff
    eid = create_enterprise(conn, name, kind, owner_actor_id=owner, location_id=loc, capital=means, cash=means,
                            metadata={"authored": True, "trade": trade, **({"founded_by_protagonist": True} if founding else {})})
    add_enterprise_staff(conn, eid, owner, role="owner", authority=100)
    # Like an emergent business: a real archetype, so the economy resolves it, and an ecology row.
    from .business import configure_enterprise_business
    day = _day(conn)
    configure_enterprise_business(conn, eid, archetype, quality=50, price_position=50, capacity=40, clientele_fit=50,
                                  service_reliability=50, regulatory_pressure=10, cadence_days=30, metadata={"authored": True})
    conn.execute("""INSERT INTO enterprise_ecology_state(enterprise_id,founded_day,crystallized_day,structural_origin,last_review_day,metadata_json)
                    VALUES (?,?,?,'formed_during_simulation',?,?) ON CONFLICT(enterprise_id) DO NOTHING""",
                 (eid, day, day, day, json.dumps({"authored": True, "population_delta": 0}, sort_keys=True)))
    out = {"status": "created", "kind": "business", "enterprise_id": eid, "name": name, "means": ledger.scale_word(means)}
    return {**out, **({"scaled_down": down} if down else {})}


# ---------------------------------------------------------------- organisation

def _outfit_scale(conn, loc: int) -> dict:
    """Averages of the outfits already there: members and violence per member; the ratio a new one's footing follows."""
    scope = _scope(conn, loc)
    q = ",".join("?" * len(scope))
    r = conn.execute(f"SELECT COUNT(*),COALESCE(SUM(member_count_estimate),0),COALESCE(SUM(violence_capacity),0) FROM underworld_organizations "
                     f"WHERE primary_location_id IN ({q}) AND status IN ('active','strained','fragmented')", scope).fetchone()
    n, members, viol = int(r[0]), float(r[1]), float(r[2])
    return {"count": n, "avg_members": members / n if n else 8.0, "violence_per_member": viol / members if members else 1.5}


def _claim_ground(conn, oid: int, loc: int, ratio: float) -> dict:
    """A new outfit takes a vacant zone of its town, else challenges the weakest-held one (towns without zones: none).
    Its footing is proportional to its size against the town's usual outfit."""
    from .underworld_rebuild import add_zone_challenger, set_zone_controller
    zones = [int(r[0]) for r in conn.execute("SELECT id FROM underworld_zones WHERE city_location_id=? AND status='active' ORDER BY id", (veto.settlement_of(conn, loc) or loc,))]
    held = {int(r[0]): float(r[1]) for r in conn.execute(
        "SELECT zone_id,strength FROM underworld_zone_claims WHERE claim_kind='controller' AND status='active' AND zone_id IN (%s)" % ",".join("?" * len(zones)), zones)} if zones else {}
    vacant = [z for z in zones if z not in held]
    meta = {"authored": True}
    r = max(0.15, min(1.0, ratio))
    if vacant:
        set_zone_controller(conn, vacant[0], oid, strength=round(30 * r, 1), local_support=round(25 * r, 1), fear=round(35 * r, 1), metadata=meta)
        return {"zone_id": vacant[0], "ground": "holds"}
    if held:
        z = min(held, key=lambda k: (held[k], k))
        add_zone_challenger(conn, z, oid, strength=round(25 * r, 1), severity=round(25 * r, 1), metadata=meta)
        return {"zone_id": z, "ground": "challenges"}
    return {}


def _canon_scale(conn, typ: str) -> None:
    """A kind of body whose every instance in the world is an established canon one (sects, covens, great houses, polities,
    mafia families) is canon-scale: another is held by canon, not made by a stroke of the pen. Decided from the world's data."""
    from .underworld import ORG_TYPES
    if typ in ORG_TYPES - {"gang", "crew", "other"} or re.search(r"mafia|dynasty", typ):
        _no(f"canon-scale bodies cannot be founded: every {typ} of the world is established")
    r = conn.execute("SELECT COUNT(*),SUM(EXISTS(SELECT 1 FROM source_identity_map m WHERE m.entity_id=ip.actor_id AND m.entity_kind IN ('actor','institution'))) "
                     "FROM institution_profiles ip WHERE lower(ip.institution_kind)=?", (typ,)).fetchone()
    if r[0] and r[0] == r[1]:
        _no(f"canon-scale bodies cannot be founded: every {typ} of the world is established")


_OUTFIT_WORDS = re.compile(r"gang|crew|outfit|mob|syndicate|thieves|smuggl|racket|brotherhood of|ring\b|band of")


def _organisation(conn, me: int, d: dict, call_id: str) -> dict:
    name = _text(d.get("name"), "name", 80)
    typ = _text(d.get("type") or "gang", "type", 60).lower()
    _canon_scale(conn, typ)
    loc = _place(conn, me, d)
    leader_arg = d.get("leader_actor_id")
    founding = leader_arg is None or (str(leader_arg).lstrip("-").isdigit() and int(leader_arg) == int(me))
    leader = int(me) if founding else _character(conn, leader_arg, "leader_actor_id")
    if not founding:
        _not_his(conn, me, leader, "the leader")
    if conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=? AND status='active'", (leader,)).fetchone():
        _no("that person already belongs to an outfit")
    if conn.execute("SELECT 1 FROM institution_memberships WHERE member_actor_id=? AND role_text='head' AND status='active'", (leader,)).fetchone():
        _no("that person already heads another body")
    if conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone() or conn.execute("SELECT 1 FROM underworld_organizations WHERE name=?", (name,)).fetchone():
        _no(f"the name {name} is already in use")
    _settled(conn, loc, leader, "the leader")
    sc = veto.place_scale(conn, loc)
    from .underworld import ORG_TYPES
    if _OUTFIT_WORDS.search(typ):
        org_type = "crew" if "crew" in typ else "gang"
        cap_new = max(1, math.ceil(veto.PROPORTION["outfit_share"] * sc["outfits"]))
        if _authored_count(conn, loc, "outfit") >= cap_new:
            _no("the town has no room for another outfit")
        scale = _outfit_scale(conn, loc)
        asked = d.get("members")
        if asked is None:
            asked = max(1, round(scale["avg_members"] * random.Random(f"{call_id}:size").uniform(0.25, 0.6)))
        elif isinstance(asked, bool) or not isinstance(asked, (int, float)) or asked < 1:
            _no("members must be a number of at least 1", "input_gap")
        prior = sum(float(r[0]) for r in conn.execute(
            f"SELECT member_count_estimate FROM underworld_organizations WHERE primary_location_id IN ({','.join('?' * len(_scope(conn, loc)))}) "
            "AND json_extract(metadata_json,'$.authored')=1 AND status IN ('active','strained','fragmented')", _scope(conn, loc)))
        adj, down = veto.holdings_in_proportion(conn, loc, [{"kind": "outfit", "members": int(asked)}], prior_members=prior)
        members = int(adj[0]["members"])
        from .underworld import create_underworld_organization, ensure_underworld_membership_profile
        from .underworld_rebuild import create_personnel, ensure_heat_profile
        oid = create_underworld_organization(conn, f"authored:{call_id}", org_type, name=name, founder_actor_id=leader, primary_location_id=loc,
                                             member_count_estimate=members, violence_capacity=min(100.0, round(members * scale["violence_per_member"], 1)),
                                             cohesion=50, metadata={"authored": True, **({"founded_by_protagonist": True} if founding else {})})
        create_personnel(conn, oid, role_kind="boss", actor_id=leader)
        # What every existing outfit has: a membership stock, a heat profile, a temperament, and ground in its town.
        ensure_underworld_membership_profile(conn, oid)
        ensure_heat_profile(conn, oid)
        try:
            from .temperament import ensure_temperament
            ensure_temperament(conn, oid)
        except Exception:  # the temperament is derived from the outfit's own record; absent only in old saves
            pass
        ground = _claim_ground(conn, oid, loc, members / max(1.0, scale["avg_members"]))
        out = {"status": "created", "kind": "organisation", "type": org_type, "outfit_id": oid, "name": name, **ground}
        return {**out, **({"scaled_down": down} if down else {})}
    # a body that is not an outfit: a guild, school, temple, club, company ... any such word
    cap_new = max(1, math.ceil(veto.PROPORTION["business_share"] * max(1.0, sc["institutions"])))
    if _authored_count(conn, loc, "institution") >= cap_new:
        _no(f"the town has no room for another {typ}")
    day = _day(conn)
    iid = int(conn.execute(
        "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) VALUES (?,'institution',?,?,?,'active',?,0)",
        (name, typ[:40], loc, loc, "Authored in play.")).lastrowid)
    conn.execute("INSERT INTO institution_profiles(actor_id,institution_kind,founded_day,primary_location_id) VALUES (?,?,?,?)", (iid, typ[:40], day, loc))
    conn.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) "
                 "VALUES (?,'DORMANT',180,.30,.55,?,?,3)", (iid, day, day + 180))
    conn.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json) "
                 "VALUES (?,?,'member','head','active',?,?,?)", (iid, leader, day, json.dumps(["authored in play"]), json.dumps({"authored": True})))
    from .organization_agency import ensure_agency_profile
    from .organization_lifecycle import ensure_lifecycle_profile
    ensure_agency_profile(conn, iid, governance_mode="institutional", metadata={"authored": True})
    ensure_lifecycle_profile(conn, iid, lifecycle_kind=typ[:40], metadata={"authored": True})
    return {"status": "created", "kind": "organisation", "type": typ, "institution_actor_id": iid, "name": name}


# ---------------------------------------------------------------- rumour

_SPREAD = {"whisper": (.05, .15), "narrow": (.08, .2), "local": (.15, .3), "wide": (.35, .5), "everywhere": (.55, .7), "far": (.4, .55)}


def _rumour(conn, me: int, d: dict, call_id: str) -> dict:
    text = _text(d.get("text"), "text", 300)
    loc = _place(conn, me, d)
    from .presence import actor_is_present_candidate
    hearers = d.get("heard_by") or []
    if not isinstance(hearers, list) or len(hearers) > 12:
        _no("heard_by must be a list of at most 12 actor ids", "input_gap")
    ids = []
    for h in hearers:
        h = _character(conn, h, "heard_by")
        if not actor_is_present_candidate(conn, h, loc):
            _no("everyone who hears it first must be present at the place")
        ids.append(h)
    from .information import _schedule_from_location, expose_actor_to_rumour
    day = _day(conn)
    word = str(d.get("spread") or "").lower().strip()
    if word in _SPREAD:
        reach, prev = _SPREAD[word]
    else:  # how far a story carries follows the place: it fills a small town faster than a great city
        pop = max(1.0, float(_population(conn, loc)))
        reach = round(max(.06, min(.45, .5 - .06 * math.log10(pop + 10))), 3)
        prev = round(min(.6, reach * 2), 3)
    distortion = round(.1 + .4 * (1 - reach), 3)
    rid = int(conn.execute("INSERT INTO rumours(created_day,origin_location_id,text,truth_event_id,distortion,reach,status) VALUES (?,?,?,NULL,?,?,'circulating')",
                           (day, loc, text, distortion, reach)).lastrowid)
    conn.execute("INSERT INTO rumour_locations(rumour_id,location_id,first_arrived_day,last_updated_day,prevalence,fidelity,hop_count) VALUES (?,?,?,?,?,.7,0)",
                 (rid, loc, day, day, prev))
    _schedule_from_location(conn, rid, loc, day, prev, .7, 0)
    for h in ids:
        expose_actor_to_rumour(conn, rid, h, day, loc, force=True)
    return {"status": "created", "kind": "rumour", "rumour_id": rid}


_KINDS = {"person": _person, "business": _business, "organisation": _organisation, "rumour": _rumour}
_KIND_WORDS = (("rumour", ("rumour", "rumor", "gossip", "news", "story", "word")),
               ("organisation", ("organi", "outfit", "gang", "crew", "guild", "school", "temple", "club", "company", "sect", "order", "lodge",
                                 "brotherhood", "band", "house of", "society", "militia")),
               ("business", ("business", "shop", "inn", "tavern", "stall", "workshop", "smithy", "firm", "enterprise", "trade", "store",
                             "brothel", "bakery", "mill")),
               ("person", ("person", "people", "character", "npc", "man", "woman", "someone", "figure", "neighbour", "neighbor", "friend",
                           "rival", "relative")))


def _kind_of(kind: Any, d: dict) -> str:
    """Free text `kind` to the nearest thing the engine can make. Fields present in the details settle it when the word does not."""
    k = str(kind or "").lower()
    if k in _KINDS:
        return k
    for target, words in _KIND_WORDS:
        if any(w in k for w in words):
            return target
    for target, keys in (("rumour", ("text", "heard_by", "spread")), ("organisation", ("leader_actor_id", "members")),
                         ("business", ("owner_actor_id", "trade", "amount")), ("person", ("sex", "age", "work", "stage", "ties"))):
        if any(x in d for x in keys):
            return target
    _no("say what kind of thing is being made: a person, a business, an organisation or a rumour (a household, a debt or a relation between people "
        "is made with ties, act or note)", "input_gap")


def author(conn: sqlite3.Connection, me: int, kind: str, details: dict, call_id: str) -> dict:
    """Make something invented real, or raise AuthoringRefused saying why not. All-or-nothing."""
    d = details if isinstance(details, dict) else {}
    target = _kind_of(kind, d)
    conn.execute("SAVEPOINT authoring")
    try:
        out = _KINDS[target](conn, int(me), d, str(call_id))
    except BaseException:
        conn.execute("ROLLBACK TO SAVEPOINT authoring")
        conn.execute("RELEASE SAVEPOINT authoring")
        raise  # only AuthoringRefused is a refusal; anything else is a bug and must not be stored as one
    conn.execute("RELEASE SAVEPOINT authoring")
    return out
