"""OPENING-01 — opening family life and opening relationships (schema 108).

The seed leaves "household membership, marriages, children … and full social networks" null where
canon does not establish them.  Null means *unknown*, not *none* (DESIGN §15.1): the opening world is
full of adults who married, were widowed, raised children and have known their kin, teachers and
colleagues for decades.  This module resolves those unknowns exactly once, at the start of a run:

* deterministically from the world seed and each person's seed identity;
* at rates that follow the World Bible's familial culture ("you belong to people before you belong
  only to yourself"; the Hearth Rites give religious weight to continuing the line) and the engine's
  own mortality curve, so a long-lived cultivator is often widowed ("outlives by decades");
* never over canon: anyone canon gives their own spouse, children or grandchildren keeps canon only;
* with every resolved fact recording its basis.

A living spouse is revealed as a low-attention persistent person (they share the household, births
and inheritance).  Children born before the opening stay latent ("latent does not mean newly created,
it means previously undescribed") until the story needs them.

During a run, ``resolve_unnamed_marriages`` lets single named adults marry into the unnamed
population at the *same* rates the opening uses — the partner already existed; the marriage is not
caused by a short named roster.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import sqlite3
from typing import Any

from .health import natural_annual_hazard

AUTHORITY = "OPENING_FAMILY_RESOLUTION_V1"
CULTIVATOR_CLASSES = {"first", "temper", "third", "breach", "fifth", "sixth"}
_SENIOR_CLASSES = {"third", "breach", "fifth", "sixth"}

# Surnames for revealed spouses.  A spouse keeps their own family name: canon does not establish a
# marital naming convention, and a shared surname would read as kinship.
_SPOUSE_SURNAMES = (
    "Alder", "Ashby", "Bennet", "Birch", "Brann", "Cairn", "Carrow", "Dale", "Dorran", "Evers", "Fenn",
    "Garland", "Grey", "Hale", "Harrow", "Hollin", "Ives", "Keene", "Lorne", "Lowe", "March", "Marr",
    "Merrin", "Mere", "North", "Oakes", "Pike", "Quill", "Reese", "Renn", "Rooke", "Senn", "Sten", "Tarn",
    "Thorne", "Toll", "Vance", "Ward", "Wren", "Yarrow",
)


def _j(v: Any) -> str:
    return json.dumps(v if v is not None else {}, sort_keys=True, ensure_ascii=False)


def _rng(key: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(f"opening_family:{key}".encode()).digest()[:8], "big"))


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _world_seed(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])


# ---------------------------------------------------------------------------------------------
# Marriage-rate model (shared by the opening draw and the run-time process)
# ---------------------------------------------------------------------------------------------

Curve = tuple[float, float, float]  # (median first-marriage age, spread, lifetime share ever married)

# Canon (World Bible): "Characters can marry happily, badly, strategically, romantically, late,
# repeatedly, or not at all"; celibacy and little interest in sex occur.  Groups therefore differ, and
# each factor below cites its canon basis.  Canon's same-sex relationships and long-term unmarried
# lovers are judged differently by region and religion and are not broadly recognized households, so
# they are not modelled as unions here.
LINEAGE_KINDS = {"clan/house", "royal house", "great house", "house", "imperial dynasty", "merchant-noble house",
                  "coastal noble house", "service family", "noble martial house"}


def first_marriage_curve(sex: str, longevity_class: str) -> Curve:
    """Base curve: Hearth familial culture makes marriage near-universal among ordinary people.

    Open-Core people marry a little later; serious martial careers (Third and above) later and less
    often, since some give their lives to the art.  Group factors adjust this per person.
    """
    median = 21.0 if sex == "female" else 24.0
    spread, share = 3.5, 0.93
    if longevity_class in CULTIVATOR_CLASSES:
        median += 2.0; spread = 5.0; share = 0.90
    if longevity_class in _SENIOR_CLASSES:
        median += 3.0; share = 0.82
    return median, spread, share


def marriage_curve_for(conn: sqlite3.Connection, actor_id: int, sex: str, longevity_class: str) -> tuple[Curve, list[str]]:
    """The person's marriage curve and the canon-grounded factors that shaped it."""
    median, spread, share = first_marriage_curve(sex, longevity_class)
    tags = ["senior_cultivator" if longevity_class in _SENIOR_CLASSES else
            "cultivator" if longevity_class in CULTIVATOR_CLASSES else "ordinary"]
    kinds = {str(r[0]) for r in conn.execute(
        """SELECT ip.institution_kind FROM institution_memberships im JOIN institution_profiles ip ON ip.actor_id=im.institution_actor_id
           WHERE im.member_actor_id=? AND im.status='active'""", (actor_id,))}
    if kinds & LINEAGE_KINDS:
        # "A clan is fundamentally reproduced through kinship, inheritance, marriage"; lineage marriage is political.
        share = max(share, 0.94); median -= 1.0; tags.append("lineage_house")
    row = conn.execute("SELECT source_payload_json FROM source_identity_map WHERE entity_kind='actor' AND entity_id=?", (actor_id,)).fetchone()
    payload = json.loads(row[0] or "{}") if row else {}
    text = " ".join(str(payload.get(k) or "") for k in ("role", "public_identity_text", "training_provenance_text")).lower()
    if payload.get("long_road"):
        # The Long Road is a travelling mode of life; becoming a "settled spouse" is one of its exits.
        share *= 0.80; median += 4.0; tags.append("long_road")
    if any(w in text for w in ("reclusive", "recluse", "hermit")):
        share *= 0.35; tags.append("canon_text:reclusive")
    elif "wander" in text:
        share *= 0.65; median += 3.0; tags.append("canon_text:wandering")
    if str(payload.get("state_sphere") or "").startswith("Greywood"):
        # Greywood's Witness culture "places stronger moral pressure around marriage".
        share = min(0.97, share + 0.03); tags.append("greywood_witness")
    return (median, spread, share), tags


def _ever_married_share(age: float, curve: Curve) -> float:
    median, spread, share = curve
    if age < 16.0:
        return 0.0
    return share * 0.5 * (1.0 + math.erf((age - median) / (spread * math.sqrt(2.0))))


def first_marriage_hazard(age: float, curve: Curve) -> float:
    """Annual probability that a never-married person of this age marries this year."""
    f0 = _ever_married_share(age, curve)
    f1 = _ever_married_share(age + 1.0, curve)
    return max(0.0, (f1 - f0) / max(1e-9, 1.0 - f0))


def remarriage_hazard(age: float) -> float:
    """Annual probability that a widowed person remarries (after at least a year of mourning)."""
    if age < 35: return 0.20
    if age < 45: return 0.12
    if age < 55: return 0.06
    if age < 65: return 0.02
    return 0.005


_DESIRED_CHILDREN = ((1, .08), (2, .20), (3, .30), (4, .25), (5, .12), (6, .05))
_OPEN_SPOUSE_STAGES = (("first", .42), ("temper", .30), ("third", .18), ("breach", .08), ("fifth", .02))
_SENIOR_SPOUSE_STAGES = (("first", .20), ("temper", .30), ("third", .28), ("breach", .16), ("fifth", .06))


def _weighted(rng: random.Random, table: tuple[tuple[Any, float], ...]) -> Any:
    x = rng.random() * sum(w for _, w in table)
    for value, w in table:
        x -= w
        if x <= 0:
            return value
    return table[-1][0]


def _draw_spouse(rng: random.Random, person_age: float, sex: str, longevity_class: str, hearth: bool = True) -> dict[str, Any]:
    """A spouse's sex, age and Core.  Being Veinborn is not being a martial artist: martial families marry
    Veinborn partners more often ("more Open-Core marriages"), but whether that partner ever became a staged
    cultivator follows canon's staging rates, which are sex-weighted (serious martial society is ~70% male)."""
    from .cultivation import VEINBORN_SHARE, staged_probability
    spouse_sex = "male" if sex == "female" else "female"
    gap = (3.0 if sex == "female" else -3.0) + rng.gauss(0.0, 3.5)
    martial = longevity_class in CULTIVATOR_CLASSES
    open_core = rng.random() < ((0.55 if hearth else 0.35) if martial else VEINBORN_SHARE[bool(hearth)])
    stage = None
    if open_core and rng.random() < staged_probability(spouse_sex, hearth, martial):
        stage = _weighted(rng, _SENIOR_SPOUSE_STAGES if longevity_class in {"fifth", "sixth"} else _OPEN_SPOUSE_STAGES)
    return {"sex": spouse_sex, "age_at_marriage": max(16.0, person_age + gap), "open_core": open_core,
            "stage": stage, "longevity_class": stage or "ordinary", "union_kind": "marriage"}


def draw_family_history(key: str, *, age: float, sex: str, longevity_class: str, curve: Curve | None = None,
                        childhood_multiplier: float = 1.0, hearth: bool = True) -> dict[str, Any]:
    """Deterministic life course up to ``age``: marriages, widowhood, remarriage and children.

    Pure: the same key and inputs always yield the same history.  Year by year it walks the person's
    adult life, drawing marriage at the first-marriage/remarriage rates, the spouse's survival from
    the engine's own mortality curve, and children while the birth parent is 18-42.  Children face the
    world's premodern childhood mortality as they grow, and a family keeps having children until it has
    the number it wants *living* (the Rites' stake in continuing the line), never more than ten births.
    """
    rng = _rng(key)
    curve = curve or first_marriage_curve(sex, longevity_class)
    desired = _weighted(rng, _DESIRED_CHILDREN)
    marriages: list[dict[str, Any]] = []
    children: list[dict[str, Any]] = []
    spouse: dict[str, Any] | None = None
    widowed_at: float | None = None
    last_birth_at = -99.0
    t = 16.0
    while t < age:
        if spouse is None:
            h = first_marriage_hazard(t, curve) if not marriages else (
                remarriage_hazard(t) if widowed_at is not None and t - widowed_at >= 1.0 else 0.0)
            if rng.random() < h:
                spouse = _draw_spouse(rng, t, sex, longevity_class, hearth)
                spouse["married_at"] = t
                marriages.append(spouse)
                widowed_at = None
        else:
            years = t - spouse["married_at"]
            spouse_age = spouse["age_at_marriage"] + years
            if rng.random() < natural_annual_hazard(spouse_age, spouse["longevity_class"]):
                spouse["died_at"] = t
                widowed_at = t
                spouse = None
            else:
                mother_age = t if sex == "female" else spouse_age
                living = sum(1 for c in children if c["alive"])
                if (living < desired and len(children) < 10 and 18.0 <= mother_age <= 42.0
                        and t - last_birth_at >= 1.0 and rng.random() < 0.30):
                    children.append({"born_at": t, "with_marriage": len(marriages) - 1, "alive": True})
                    last_birth_at = t
        t += 1.0
        for child in children:
            if child["alive"] and rng.random() < natural_annual_hazard(t - 1.0 - child["born_at"], "ordinary",
                                                                       childhood_multiplier=childhood_multiplier):
                child["alive"] = False
    for child in children:
        child["age"] = age - child["born_at"]
    if spouse is not None:
        status = "married"
        spouse["age_now"] = spouse["age_at_marriage"] + (age - spouse["married_at"])
    elif marriages:
        status = "widowed"
    else:
        status = "never_married"
    return {"status": status, "marriages": marriages, "children": children, "desired_children": desired,
            "last_birth_at": last_birth_at if children else None}


# ---------------------------------------------------------------------------------------------
# Revealing a spouse as a persistent person
# ---------------------------------------------------------------------------------------------

def _spouse_name(conn: sqlite3.Connection, key: str, sex: str) -> str:
    from .demographic_sex import FEMALE_GIVEN_NAMES, MALE_GIVEN_NAMES
    from .demographic_sex import package_person_name
    given = sorted(FEMALE_GIVEN_NAMES if sex == "female" else MALE_GIVEN_NAMES)
    rng = _rng(f"name:{key}")
    for _ in range(400):
        pk = package_person_name(conn, rng, sex)
        name = f"{pk[0]} {pk[1]}" if pk else f"{rng.choice(given)} {rng.choice(_SPOUSE_SURNAMES)}"
        if not conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
            return name
    raise RuntimeError("could not produce a unique spouse name")


def _reveal_spouse(conn: sqlite3.Connection, person_id: int, spouse: dict[str, Any], *, key: str, day: int,
                   location_id: int | None, reason: str) -> int:
    """Materialize an already-existing spouse through the latent-person path, at low attention."""
    from .continuity import set_resolution
    from .resolution_controller import _materialize_latent_person, _sync_sim_tier
    birth_day = day - int(round(spouse["age_now"] * 365.0)) - _rng(f"birthday:{key}").randrange(365)
    constraints = {
        "name": _spouse_name(conn, key, spouse["sex"]), "birth_day": birth_day, "demographic_sex": spouse["sex"],
        "open_core": bool(spouse["open_core"]), "stage": spouse["stage"].capitalize() if spouse["stage"] else None,
        "spouse_of_actor_id": person_id,
    }
    hist = {"authority": AUTHORITY, "basis": reason, "married_day": int(day - round((spouse["age_now"] - spouse["age_at_marriage"]) * 365.0))}
    cur = conn.execute(
        """INSERT INTO latent_entities(latent_kind,archetype,location_id,count_estimate,constraints_json,historical_context_json,
                                       status,created_day,updated_day,notes)
           VALUES ('person','spouse',?,1,?,?,'latent',?,?,?)""",
        (location_id, _j(constraints), _j(hist), day, day,
         "Spouse of a named person; existed before the opening, previously undescribed."),
    )
    latent = conn.execute("SELECT * FROM latent_entities WHERE id=?", (int(cur.lastrowid),)).fetchone()
    aid = _materialize_latent_person(conn, latent, day, 0.0, {"spouse_of_named_person": 1.0})
    if aid is None:
        raise RuntimeError("spouse materialization failed")
    set_resolution(conn, "actor", aid, "STRUCTURAL", day=day, reason="spouse of a named person (household, births, inheritance)",
                   source_kind="engine", review_cadence_days=365, next_review_day=day + 365,
                   metadata={"latent_entity_id": int(latent["id"]), "authority": AUTHORITY})
    _sync_sim_tier(conn, aid, "STRUCTURAL", day)
    conn.execute("UPDATE actor_life_profiles SET metadata_json=json_patch(metadata_json,?) WHERE actor_id=?",
                 (_j({"marital_status": "married", "marital_status_basis": reason, "marital_status_authority": AUTHORITY}), aid))
    from .health import configure_health_profile
    configure_health_profile(conn, aid, longevity_class=spouse["longevity_class"])
    # A staged spouse may still practise; most practise less with age.  Unstaged Veinborn do not train
    # now but may take it up later (resolve_cultivation_uptake).
    from .cultivation import calibrate_revealed_profile
    practising = bool(spouse["stage"]) and _rng(f"practising:{key}").random() < (
        0.70 if spouse["age_now"] < 35 else 0.50 if spouse["age_now"] < 50 else 0.30)
    calibrate_revealed_profile(conn, aid, active=practising)
    return aid


def _form_revealed_union(conn: sqlite3.Connection, person_id: int, spouse_id: int, *, married_day: int, day: int,
                         family_plan: dict[str, Any], basis: str, union_kind: str = "marriage") -> int:
    from .household_life import create_union
    hh = conn.execute("SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?", (person_id,)).fetchone()
    household_id = int(hh[0]) if hh and hh[0] is not None else None
    person_name = conn.execute("SELECT name FROM actors WHERE id=?", (person_id,)).fetchone()[0]
    spouse_name = conn.execute("SELECT name FROM actors WHERE id=?", (spouse_id,)).fetchone()[0]
    uid = create_union(conn, person_id, spouse_id, household_id=household_id, union_kind=union_kind,
                       create_new_household_name=None if household_id else f"Household of {person_name} and {spouse_name}")
    conn.execute("UPDATE household_unions SET started_day=?,family_plan_json=?,metadata_json=? WHERE id=?",
                 (married_day, _j(family_plan), _j({"authority": AUTHORITY, "basis": basis}), uid))
    conn.execute(
        """UPDATE kinship_links SET started_day=? WHERE kin_kind='spouse' AND ended_day IS NULL
           AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))""",
        (married_day, person_id, spouse_id, spouse_id, person_id),
    )
    _seed_pair(conn, person_id, spouse_id, "spouse", key=f"union:{uid}", started_day=married_day)
    return uid


# Births come at 30% a year once a year has passed since the last (the opening draw's own rate), so a
# birth interval is one year plus a geometric wait: about 3.3 years on average.
_BIRTH_ANNUAL_CHANCE = 0.30


def _birth_interval_days(rng: random.Random) -> int:
    return 365 + int(365.0 * rng.expovariate(_BIRTH_ANNUAL_CHANCE / (1.0 - _BIRTH_ANNUAL_CHANCE)))


def _family_plan(history: dict[str, Any], *, sex: str, person_age: float, spouse_age: float, day: int, key: str,
                 birth_parent_id: int | None, mode: str, married_day: int) -> dict[str, Any]:
    born = len(history["children"])
    remaining = max(0, int(history["desired_children"]) - sum(1 for c in history["children"] if c.get("alive", True)))
    mother_age = person_age if sex == "female" else spouse_age
    rng = _rng(f"plan:{key}")
    auto = bool(birth_parent_id is not None and remaining > 0 and mother_age <= 42.0)
    last = history.get("last_birth_at")
    anchor = day - int(round((person_age - last) * 365.0)) if last is not None else married_day
    earliest = anchor + _birth_interval_days(rng)
    if earliest <= day:
        # Already past the minimum gap: the remaining wait is memoryless at the same annual chance.
        earliest = day + max(30, int(365.0 * rng.expovariate(_BIRTH_ANNUAL_CHANCE)))
    return {
        "mode": mode, "auto_children": auto, "desired_children": remaining if auto else 0,
        "spacing_days": _birth_interval_days(rng), "earliest_next_child_day": earliest,
        "birth_parent_actor_id": birth_parent_id, "authority": "CAMPAIGN_CALIBRATION_NOT_CANON_DESTINY",
        "children_born_before": born, "family02_reproductive_state": "resolved" if birth_parent_id is not None else "unresolved_no_auto_birth",
    }


# ---------------------------------------------------------------------------------------------
# Opening family resolution
# ---------------------------------------------------------------------------------------------

def _person_rows(conn: sqlite3.Connection, day: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT a.id,a.name,COALESCE(a.home_location_id,a.current_location_id) loc,lp.birth_day,lp.demographic_sex,
                  lp.metadata_json,COALESCE(h.longevity_class,'ordinary') lc,m.source_key
           FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
           LEFT JOIN actor_health_profiles h ON h.actor_id=a.id
           LEFT JOIN source_identity_map m ON m.entity_kind='actor' AND m.entity_id=a.id
           WHERE a.actor_type='character' AND a.status='active' AND lp.life_status='living'
             AND lp.birth_day IS NOT NULL AND lp.birth_day<=? AND lp.demographic_sex IN ('female','male')
           ORDER BY a.id""",
        (day - 18 * 365,),
    ).fetchall()


def _canon_family_ids(conn: sqlite3.Connection) -> set[int]:
    """People whose *own* spouse, children or grandchildren canon records: canon alone decides them."""
    ids = {int(r[0]) for r in conn.execute(
        "SELECT actor_a_id FROM kinship_links WHERE kin_kind IN ('spouse','parent') AND ended_day IS NULL")}
    ids |= {int(r[0]) for r in conn.execute(
        "SELECT actor_a_id FROM typed_relationship_facts WHERE relation_type IN ('spouse','parent_of','grandparent_of')")}
    return ids


def _mark(conn: sqlite3.Connection, actor_id: int, patch: dict[str, Any]) -> None:
    conn.execute("UPDATE actor_life_profiles SET metadata_json=json_patch(COALESCE(metadata_json,'{}'),?) WHERE actor_id=?",
                 (_j({**patch, "marital_status_authority": AUTHORITY}), actor_id))


_PERSON_SQL = """SELECT a.id,a.name,COALESCE(a.home_location_id,a.current_location_id) loc,lp.birth_day,lp.demographic_sex,
                  lp.metadata_json,COALESCE(h.longevity_class,'ordinary') lc,m.source_key
           FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
           LEFT JOIN actor_health_profiles h ON h.actor_id=a.id
           LEFT JOIN source_identity_map m ON m.entity_kind='actor' AND m.entity_id=a.id"""


def _kids_of(conn: sqlite3.Connection, aid: int) -> int:
    return int(conn.execute("SELECT COALESCE(SUM(count_estimate),0) FROM latent_entities WHERE latent_kind='kin_group' AND archetype='children' "
                            "AND json_extract(constraints_json,'$.parent_actor_id')=?", (aid,)).fetchone()[0])


def resolve_family_for(conn: sqlite3.Connection, aid: int, *, key: str | None = None, day: int | None = None,
                       constraints: dict[str, Any] | None = None, force: bool = False, canon_family: set[int] | None = None) -> str | None:
    """Resolve one person's marital status, spouse and latent children (the loop body of `resolve_opening_family`).

    Returns the counter name it fell under, or None when the person is not eligible. `constraints` (`marital`:
    married|widowed|never_married, `children_min`, `children_max`) narrows the pure draw by rejection sampling (at most 40
    tries); an improbable request raises Contradiction naming the clash.
    """
    day = _day(conn) if day is None else int(day)
    p = conn.execute(_PERSON_SQL + " WHERE a.id=?", (int(aid),)).fetchone()
    if p is None or p["birth_day"] is None or p["demographic_sex"] not in ("female", "male"):
        return None
    meta = json.loads(p["metadata_json"] or "{}")
    if not force and (meta.get("marital_status_basis") or meta.get("marital_status_authority")):
        return "already_resolved"
    canon_family = _canon_family_ids(conn) if canon_family is None else canon_family
    if conn.execute("SELECT 1 FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?)", (aid, aid)).fetchone():
        _mark(conn, aid, {"marital_status": "married", "marital_status_basis": "canon_record" if aid in canon_family else "recorded_union"})
        return "canon_record"
    if aid in canon_family:
        # Canon records this person's children but no living spouse: leave the rest to canon.
        _mark(conn, aid, {"marital_status": "unresolved", "marital_status_basis": "canon_partial"})
        return "canon_partial"
    seed = _world_seed(conn)
    age = (day - int(p["birth_day"])) / 365.0
    sex = str(p["demographic_sex"]); lc = str(p["lc"])
    key = key or str(p["source_key"] or f"actor:{seed}:{aid}")
    curve, tags = marriage_curve_for(conn, aid, sex, lc)
    from .health import childhood_circumstance
    child_mult, child_tags = childhood_circumstance(conn, parent_ids=[aid], location_id=int(p["loc"]) if p["loc"] is not None else None)
    from .cultivation import location_in_hearth
    hearth = location_in_hearth(conn, int(p["loc"]) if p["loc"] is not None else None)
    cons = constraints or {}

    def fits(h: dict[str, Any]) -> bool:
        alive = sum(1 for c in h["children"] if c["alive"])
        return ((not cons.get("marital") or h["status"] == cons["marital"])
                and int(cons.get("children_min", 0)) <= alive <= int(cons.get("children_max", 99)))

    hist = draw_family_history(key, age=age, sex=sex, longevity_class=lc, curve=curve, childhood_multiplier=child_mult, hearth=hearth)
    if cons and not fits(hist):
        for i in range(40):
            hist = draw_family_history(f"{key}:try{i}", age=age, sex=sex, longevity_class=lc, curve=curve,
                                       childhood_multiplier=child_mult, hearth=hearth)
            if fits(hist):
                break
        else:
            from .veto import Contradiction
            raise Contradiction("the world's marriage and mortality rates make that family improbable at this age")
    status = hist["status"]
    former = [{"sex": m["sex"], "union_kind": m["union_kind"], "married_at_age": round(m["married_at"], 1), "died_at_age": round(m["died_at"], 1)}
              for m in hist["marriages"] if "died_at" in m]
    alive_children = [c for c in hist["children"] if c["alive"]]
    patch: dict[str, Any] = {
        "marital_status": status, "marital_status_basis": "opening_draw", "marriage_rate_factors": tags,
        "former_spouses_deceased": former, "children_born": len(hist["children"]),
        "latent_children_alive": len(alive_children), "childhood_circumstance": {"multiplier": child_mult, "factors": child_tags},
    }
    if status == "widowed":
        patch["widowed_day"] = day - int(round((age - hist["marriages"][-1]["died_at"]) * 365.0))
    spouse_id = None
    if status == "married":
        spouse = hist["marriages"][-1]
        married_day = day - int(round((age - spouse["married_at"]) * 365.0))
        loc = int(p["loc"]) if p["loc"] is not None else None
        spouse_id = _reveal_spouse(conn, aid, spouse, key=key, day=day, location_id=loc, reason="opening_draw")
        from .household_life import resolved_biological_birth_parent
        plan = _family_plan(hist, sex=sex, person_age=age, spouse_age=spouse["age_now"], day=day, key=key,
                            birth_parent_id=resolved_biological_birth_parent(conn, aid, spouse_id),
                            mode="OPENING_RESOLUTION_FAMILY_CONTINUITY", married_day=married_day)
        _form_revealed_union(conn, aid, spouse_id, married_day=married_day, day=day, family_plan=plan, basis="opening_draw",
                             union_kind=spouse["union_kind"])
        patch["spouse_actor_id"] = spouse_id
    if alive_children:
        conn.execute(
            """INSERT INTO latent_entities(latent_kind,archetype,location_id,count_estimate,constraints_json,historical_context_json,
                                           status,created_day,updated_day,notes)
               VALUES ('kin_group','children',?,?,?,?,'latent',?,?,?)""",
            (p["loc"], len(alive_children),
             _j({"parent_actor_id": aid, "other_parent_actor_id": spouse_id, "childhood_multiplier": child_mult,
                 "birth_days": [day - int(round(c["age"] * 365.0)) for c in alive_children]}),
             _j({"authority": AUTHORITY, "basis": "opening_draw"}), day, day,
             "Children born before the opening; existing, previously undescribed."),
        )
    _mark(conn, aid, patch)
    return status


def resolve_opening_family(conn: sqlite3.Connection) -> dict[str, int]:
    """Resolve marital status, spouses and latent children for named adults canon leaves unknown."""
    day = _day(conn)
    canon_family = _canon_family_ids(conn)
    counts = {"married": 0, "widowed": 0, "never_married": 0, "canon_record": 0, "canon_partial": 0,
              "spouses_revealed": 0, "latent_children": 0, "already_resolved": 0}
    from .world_package import package_for
    seed_is_authoritative = not package_for(conn).opening_family.get("marry_adults_on_day0", True)
    for p in _person_rows(conn, day):
        aid = int(p["id"])
        if seed_is_authoritative and p["source_key"] is not None:
            # The seed's own relationships stand: no invented day-0 spouse for a named adult of the seed.
            if not json.loads(p["metadata_json"] or "{}").get("marital_status_basis"):
                _mark(conn, aid, {"marital_status": "unresolved", "marital_status_basis": "seed_authoritative"})
            continue
        kids = _kids_of(conn, aid)
        outcome = resolve_family_for(conn, aid, day=day, canon_family=canon_family)
        if outcome is None:
            continue
        counts[outcome] += 1
        if outcome == "married":
            counts["spouses_revealed"] += 1
        if outcome in ("married", "widowed", "never_married"):
            counts["latent_children"] += _kids_of(conn, aid) - kids
    return counts


def draw_origin_family(key: str, *, age: float, sex: str, hearth: bool = True, childhood_multiplier: float = 1.0) -> dict[str, Any]:
    """Deterministic family a person grew up in: two parents (ages, survival to now) and brothers and sisters (ages, sexes,
    survival), from the engine's own mortality, desired-children and birth-interval models. Pure."""
    rng = _rng(f"origin:{key}")
    m_at = int(min(40, max(17, round(rng.gauss(26, 4.5)))))
    mother_age = age + m_at
    father_age = mother_age + int(min(12, max(-2, round(rng.gauss(3, 3.5)))))

    def lives(a_now: float, a_then: float, cls: str = "ordinary", mult: float = 1.0) -> bool:
        t = a_then
        while t < a_now:
            if rng.random() < natural_annual_hazard(t, cls, childhood_multiplier=mult):
                return False
            t += 1.0
        return True

    mother = {"age_now": mother_age, "alive": lives(mother_age, m_at)}
    father = {"age_now": father_age, "alive": lives(father_age, father_age - age)}
    n_sib = max(0, _weighted(rng, _DESIRED_CHILDREN) - 1 + rng.choice((-1, 0, 0, 1)))
    older = rng.randint(0, n_sib)
    sibs: list[dict[str, Any]] = []
    gap_age = float(m_at)
    for i in range(n_sib):
        if i < older:
            gap = (_birth_interval_days(rng)) / 365.0
            gap_age -= gap
            if gap_age < 16.0:
                break
            sib_age = age + (m_at - gap_age)
        else:
            if i == older:
                gap_age = float(m_at)
            gap_age += _birth_interval_days(rng) / 365.0
            if gap_age > 43.0:
                break
            sib_age = age - (gap_age - m_at)
            if sib_age < 0:
                break
        sibs.append({"age_now": max(0.0, sib_age), "sex": "female" if rng.random() < 0.5 else "male"})
    for s in sibs:
        s["alive"] = lives(s["age_now"], 0.0, "ordinary", childhood_multiplier)
    return {"mother": mother, "father": father, "siblings": sibs}


# ---------------------------------------------------------------------------------------------
# Opening relationships
# ---------------------------------------------------------------------------------------------

def _u(rng: random.Random, lo: float, hi: float) -> float:
    return lo + (hi - lo) * rng.random()


def _tie_values(kind: str, rng: random.Random, *, role: str = "") -> dict[str, float]:
    """Directional opening values for one side of a tie (relationships are -100..100)."""
    if kind in {"spouse", "kin"}:
        if rng.random() < 0.10:  # estrangement exists in real families
            return {"familiarity": _u(rng, 70, 90), "affection": _u(rng, -20, 10), "trust": _u(rng, -10, 20),
                    "resentment": _u(rng, 25, 55), "stance": _u(rng, -20, 5), "obligation": 15.0}
        v = {"familiarity": _u(rng, 82, 96), "affection": _u(rng, 35, 75), "trust": _u(rng, 35, 70),
             "loyalty": _u(rng, 30, 65), "respect": _u(rng, 20, 55), "obligation": 30.0}
        v["stance"] = (v["affection"] + v["trust"]) / 2.0
        return v
    if kind == "kin_extended":
        return {"familiarity": _u(rng, 50, 75), "affection": _u(rng, 15, 45), "trust": _u(rng, 20, 45),
                "loyalty": _u(rng, 10, 35), "stance": _u(rng, 15, 35), "obligation": 15.0}
    if kind == "service":  # master and servant: bound by wages and habit, not blood
        return {"familiarity": _u(rng, 40, 75), "stance": _u(rng, 10, 40), "trust": _u(rng, 25, 55), "respect": _u(rng, 25, 55),
                "loyalty": _u(rng, 40, 65), "obligation": _u(rng, 20, 40)}
    if kind == "acquaintance":
        return {"familiarity": _u(rng, 30, 65), "stance": max(-20.0, min(40.0, rng.gauss(10, 12))),
                "trust": max(-20.0, min(40.0, rng.gauss(8, 12))), "respect": _u(rng, 5, 30)}
    if kind == "teaching":
        if role == "student":
            return {"familiarity": _u(rng, 75, 90), "respect": _u(rng, 55, 80), "trust": _u(rng, 45, 70),
                    "loyalty": _u(rng, 45, 75), "affection": _u(rng, 20, 50), "stance": _u(rng, 35, 60), "obligation": _u(rng, 45, 60)}
        return {"familiarity": _u(rng, 75, 90), "trust": _u(rng, 40, 65), "affection": _u(rng, 25, 50),
                "professional_confidence": _u(rng, 45, 70), "respect": _u(rng, 20, 45), "stance": _u(rng, 30, 55), "obligation": 25.0}
    # colleague: shared institution
    v = {"familiarity": _u(rng, 35, 70), "stance": max(-30.0, min(45.0, rng.gauss(12, 12))),
         "trust": max(-30.0, min(45.0, rng.gauss(12, 14))), "respect": _u(rng, 5, 35), "loyalty": _u(rng, 5, 30)}
    if rng.random() < 0.12:  # rivalry
        v.update({"resentment": _u(rng, 20, 50), "stance": v["stance"] - _u(rng, 5, 25), "trust": v["trust"] - _u(rng, 0, 20)})
    return v


def _seed_pair(conn: sqlite3.Connection, a: int, b: int, kind: str, *, key: str, started_day: int,
               a_role: str = "", b_role: str = "") -> bool:
    from .relationships import ensure_relationship, relationship_exists
    if relationship_exists(conn, a, b) or relationship_exists(conn, b, a):
        return False
    rng = _rng(f"rel:{key}")
    ensure_relationship(conn, a, b, started_day, started_day=started_day, **_tie_values(kind, rng, role=a_role))
    ensure_relationship(conn, b, a, started_day, started_day=started_day, **_tie_values(kind, rng, role=b_role))
    return True


def _ages(conn: sqlite3.Connection, day: int) -> dict[int, float]:
    return {int(r[0]): (day - int(r[1])) / 365.0 for r in conn.execute(
        """SELECT a.id,lp.birth_day FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
           WHERE a.actor_type='character' AND a.status='active' AND lp.birth_day IS NOT NULL""")}


def resolve_opening_relationships(conn: sqlite3.Connection) -> dict[str, int]:
    """Backdated relationships from canon kin, teaching lines and shared institutions."""
    day = _day(conn)
    ages = _ages(conn, day)
    counts = {"kin": 0, "kin_extended": 0, "teaching": 0, "colleague": 0, "contact_links": 0}

    def years_ago(y: float) -> int:
        return day - int(round(max(1.0, y) * 365.0))

    for r in conn.execute("""SELECT actor_a_id,actor_b_id,kin_kind FROM kinship_links WHERE ended_day IS NULL
                             AND kin_kind IN ('parent','sibling','spouse') ORDER BY id""").fetchall():
        a, b = int(r[0]), int(r[1])
        if a not in ages or b not in ages:
            continue
        since = years_ago(min(ages[a], ages[b]) - (22 if r[2] == "spouse" else 0))
        if _seed_pair(conn, a, b, "kin", key=f"kin:{min(a,b)}:{max(a,b)}", started_day=since):
            counts["kin"] += 1
    for r in conn.execute("""SELECT actor_a_id,actor_b_id FROM typed_relationship_facts
                             WHERE relation_type IN ('grandparent_of','aunt_or_uncle_of') ORDER BY id""").fetchall():
        a, b = int(r[0]), int(r[1])
        if a in ages and b in ages and _seed_pair(conn, a, b, "kin_extended", key=f"kinx:{min(a,b)}:{max(a,b)}",
                                                  started_day=years_ago(min(ages[a], ages[b]))):
            counts["kin_extended"] += 1
    teaching = [(int(r[0]), int(r[1]), r[2]) for r in conn.execute(
        "SELECT teacher_actor_id,student_actor_id,start_day FROM teaching_relationships WHERE status='active' ORDER BY id")]
    teaching += [(int(r[0]), int(r[1]), None) for r in conn.execute(
        """SELECT actor_a_id,actor_b_id FROM typed_relationship_facts
           WHERE relation_type IN ('direct_transmission','teacher_of') ORDER BY id""")]
    for teacher, student, start in teaching:
        if teacher not in ages or student not in ages:
            continue
        rng = _rng(f"teach-since:{teacher}:{student}")
        since = int(start) if start is not None and int(start) < day else years_ago(max(1.0, ages[student] - 14.0) * _u(rng, .3, 1.0))
        if _seed_pair(conn, teacher, student, "teaching", key=f"teach:{teacher}:{student}", started_day=since,
                      a_role="teacher", b_role="student"):
            counts["teaching"] += 1
    members: dict[int, list[int]] = {}
    for r in conn.execute("""SELECT im.institution_actor_id,im.member_actor_id FROM institution_memberships im
                             JOIN actors a ON a.id=im.member_actor_id
                             WHERE im.status='active' AND a.actor_type='character' AND a.status='active'
                             ORDER BY im.institution_actor_id,im.member_actor_id""").fetchall():
        members.setdefault(int(r[0]), []).append(int(r[1]))
    from .household_life import _contact_rng
    for inst, ids in members.items():
        inst_loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (inst,)).fetchone()
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if a not in ages or b not in ages:
                    continue
                rng = _rng(f"colleague-since:{inst}:{a}:{b}")
                since = years_ago((min(ages[a], ages[b]) - 16.0) * _u(rng, .25, 1.0))
                if _seed_pair(conn, a, b, "colleague", key=f"colleague:{inst}:{a}:{b}", started_day=since):
                    counts["colleague"] += 1
                # Ongoing shared context for single adults in the same place, by the run-time contact rule.
                if not inst_loc or inst_loc[0] is None:
                    continue
                lo, hi = min(a, b), max(a, b)
                singles = conn.execute(
                    """SELECT COUNT(*) FROM actor_life_profiles lp JOIN actors x ON x.id=lp.actor_id
                       WHERE lp.actor_id IN (?,?) AND lp.life_stage='adult' AND x.current_location_id=?
                         AND NOT EXISTS (SELECT 1 FROM household_unions u WHERE u.status='active' AND (u.actor_a_id=lp.actor_id OR u.actor_b_id=lp.actor_id))""",
                    (lo, hi, int(inst_loc[0])),
                ).fetchone()[0]
                if singles != 2 or abs(ages[a] - ages[b]) > 20:
                    continue
                affinity = 35.0 + _contact_rng(conn, lo, hi, inst).random() * 55.0
                if affinity < 58.0 or conn.execute(
                        "SELECT 1 FROM social_contact_links WHERE actor_a_id=? AND actor_b_id=?", (lo, hi)).fetchone():
                    continue
                conn.execute(
                    """INSERT INTO social_contact_links(actor_a_id,actor_b_id,context_kind,context_id,affinity,started_day,
                                                       last_review_day,next_review_day,status,metadata_json)
                       VALUES (?,?,'institution',?,?,?,?,?,'active',?)""",
                    (lo, hi, inst, affinity, since, day, day + 180, _j({"authority": AUTHORITY, "basis": "opening_shared_institution"})),
                )
                counts["contact_links"] += 1
    return counts


def resolve_opening_history(conn: sqlite3.Connection) -> dict[str, int]:
    """Opening family life first (spouses exist before relationships are drawn), then relationships."""
    if conn.execute("SELECT 1 FROM engine_meta WHERE key='opening_family_resolution_version'").fetchone():
        return {}
    out = {f"opening_family_{k}": v for k, v in resolve_opening_family(conn).items()}
    out.update({f"opening_relationships_{k}": v for k, v in resolve_opening_relationships(conn).items()})
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('opening_family_resolution_version','1')")
    return out


# ---------------------------------------------------------------------------------------------
# Run-time: revealing a latent child when inheritance or succession needs them
# ---------------------------------------------------------------------------------------------

def _surname(name: str) -> str | None:
    from .demographic_sex import _split_name
    _, given = _split_name(name)
    tokens = name.split()
    return tokens[-1] if given and len(tokens) >= 2 and tokens[-1] != given else None


def _core_state(conn: sqlite3.Connection, actor_id: int | None) -> tuple[bool, str | None]:
    if actor_id is None:
        return False, None
    r = conn.execute("SELECT core_state,current_stage FROM cultivation_profiles WHERE actor_id=?", (int(actor_id),)).fetchone()
    return (bool(r and r[0] == "Open-Core"), (str(r[1]).lower() if r and r[1] else None))


def _living_latent_children(conn: sqlite3.Connection, group: sqlite3.Row, day: int) -> tuple[list[int], list[int]]:
    """Split a latent sibling group's birth days into (still living, died since the opening).

    Latent children age with the world: survival from the group's creation to today is drawn once per
    child-year (deterministic), at the family's own childhood/adult mortality.
    """
    cons = json.loads(group["constraints_json"] or "{}")
    mult = float(cons.get("childhood_multiplier") or 1.0)
    living, died = [], []
    for bd in cons.get("birth_days", []):
        alive = True
        for d in range(int(group["created_day"]), day, 365):
            if _rng(f"latent-child-survival:{int(group['id'])}:{bd}:{d}").random() < natural_annual_hazard(
                    (d - int(bd)) / 365.0, "ordinary", childhood_multiplier=mult):
                alive = False
                break
        (living if alive else died).append(int(bd))
    return living, died


def reveal_latent_adult_child(conn: sqlite3.Connection, parent_id: int, *, reason: str, day: int | None = None,
                              institution_actor_id: int | None = None, min_age: float = 18.0) -> int | None:
    """Reveal the eldest living adult child of ``parent_id`` from their latent sibling group.

    Only for a causal need (an inheritance or a lineage succession).  The child existed since before the
    opening; nothing is invented except the description (name, and a Core/Stage drawn from canon's
    hereditary propensity: "mixed ancestry raises probabilities; repeated marriage among old martial
    families concentrates them").
    """
    from .continuity import set_resolution
    from .demographic_sex import FEMALE_GIVEN_NAMES, MALE_GIVEN_NAMES, package_given_pool, package_person_name, seeded_sex
    from .household_life import add_kinship
    from .resolution_controller import _materialize_latent_person
    day = _day(conn) if day is None else int(day)
    groups = conn.execute(
        """SELECT * FROM latent_entities WHERE latent_kind='kin_group' AND archetype='children'
             AND status IN ('latent','partially_crystallized')
             AND (json_extract(constraints_json,'$.parent_actor_id')=? OR json_extract(constraints_json,'$.other_parent_actor_id')=?)
           ORDER BY id""", (parent_id, parent_id)).fetchall()
    for g in groups:
        cons = json.loads(g["constraints_json"] or "{}")
        living, died = _living_latent_children(conn, g, day)
        adults = sorted(bd for bd in living if (day - bd) / 365.0 >= min_age)
        if not adults:
            continue
        bd = adults[0]  # eldest
        parents = [x for x in (cons.get("parent_actor_id"), cons.get("other_parent_actor_id")) if x is not None]
        fid = int(cons["parent_actor_id"])
        if cons.get("other_parent_actor_id") is not None:  # children take the father's surname, whichever parent the group hangs on
            sx = lambda i: (conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (int(i),)).fetchone() or [None])[0]
            if sx(fid) == "female" and sx(cons["other_parent_actor_id"]) == "male":
                fid = int(cons["other_parent_actor_id"])
        pname = str(conn.execute("SELECT name FROM actors WHERE id=?", (fid,)).fetchone()[0])
        key = f"latent-child:{int(g['id'])}:{bd}"
        sex = seeded_sex(key)
        rng = _rng(key)
        surname = _surname(pname)
        given = package_given_pool(conn, sex, surname) or sorted(FEMALE_GIVEN_NAMES if sex == "female" else MALE_GIVEN_NAMES)
        if not surname:
            pk = package_person_name(conn, rng, sex)
            surname = pk[1] if pk else rng.choice(_SPOUSE_SURNAMES)
        name = None
        for _ in range(400):
            cand = f"{rng.choice(given)} {surname}"
            if not conn.execute("SELECT 1 FROM actors WHERE name=?", (cand,)).fetchone():
                name = cand
                break
        if name is None:
            continue
        cores = [_core_state(conn, x) for x in parents]
        open_parents = sum(1 for c in cores if c[0])
        from .cultivation import inherited_open_core_probability, location_in_hearth, staged_probability
        ploc = conn.execute("SELECT COALESCE(home_location_id,current_location_id) FROM actors WHERE id=?", (int(cons["parent_actor_id"]),)).fetchone()
        hearth = location_in_hearth(conn, int(ploc[0]) if ploc and ploc[0] is not None else None)
        open_core = rng.random() < inherited_open_core_probability(open_parents, hearth)
        martial_family = institution_actor_id is not None or any(c[1] for c in cores)
        stage = None
        if open_core and rng.random() < staged_probability(sex, hearth, martial_family):
            senior = any(c[1] in {"fifth", "sixth"} for c in cores)
            stage = _weighted(rng, _SENIOR_SPOUSE_STAGES if senior else _OPEN_SPOUSE_STAGES)
            age = (day - bd) / 365.0
            cap = "third" if age < 25 else "breach" if age < 35 else "fifth"
            order = ["first", "temper", "third", "breach", "fifth"]
            if order.index(stage) > order.index(cap):
                stage = cap
            if age < 14:
                stage = None  # a small child has no Stage yet
            elif age < 18 and stage != "first":
                stage = "first"
        loc = conn.execute("SELECT COALESCE(home_location_id,current_location_id) FROM actors WHERE id=?", (int(cons["parent_actor_id"]),)).fetchone()
        loc_id = int(loc[0]) if loc and loc[0] is not None else None
        cur = conn.execute(
            """INSERT INTO latent_entities(latent_kind,archetype,location_id,institution_actor_id,count_estimate,constraints_json,
                                           historical_context_json,status,created_day,updated_day,notes)
               VALUES ('person','child',?,?,1,?,?,'latent',?,?,?)""",
            (loc_id, institution_actor_id,
             _j({"name": name, "birth_day": bd, "demographic_sex": sex, "open_core": open_core,
                 "stage": stage.capitalize() if stage else None, "parent_actor_ids": parents}),
             _j({"authority": AUTHORITY, "basis": reason, "sibling_group_latent_id": int(g["id"])}), day, day,
             "Child born before the opening, revealed when causally needed."),
        )
        latent = conn.execute("SELECT * FROM latent_entities WHERE id=?", (int(cur.lastrowid),)).fetchone()
        aid = _materialize_latent_person(conn, latent, day, 0.0, {"heir_or_claimant": 1.0})
        if aid is None:
            continue
        if stage:
            from .health import configure_health_profile
            configure_health_profile(conn, aid, longevity_class=stage)
            # Blood members of a house are sustained by it; other revealed children hold their Stage.
            from .cultivation import calibrate_revealed_profile
            calibrate_revealed_profile(conn, aid, active=institution_actor_id is not None,
                                       resource_access=60.0 if institution_actor_id is not None else 45.0)
        for par in parents:
            if conn.execute("SELECT 1 FROM actors WHERE id=?", (int(par),)).fetchone():
                add_kinship(conn, int(par), aid, "parent", reciprocal_kind="child")
                conn.execute("UPDATE kinship_links SET started_day=? WHERE ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))",
                             (bd, int(par), aid, aid, int(par)))
                _seed_pair(conn, int(par), aid, "kin", key=f"kin:{int(par)}:{aid}", started_day=bd)
        remaining = [x for x in living if x != bd]
        revealed = list(cons.get("revealed_actor_ids", [])) + [aid]
        cons.update({"birth_days": remaining, "died_birth_days": list(cons.get("died_birth_days", [])) + died,
                     "revealed_actor_ids": revealed})
        conn.execute("UPDATE latent_entities SET constraints_json=?,count_estimate=?,status=?,updated_day=? WHERE id=?",
                     (_j(cons), max(1, len(remaining)), "partially_crystallized" if remaining else "crystallized", day, int(g["id"])))
        set_resolution(conn, "actor", aid, "TRACKED", day=day, reason=reason, source_kind="engine",
                       review_cadence_days=90, next_review_day=day + 90, metadata={"authority": AUTHORITY})
        return aid
    return None


# ---------------------------------------------------------------------------------------------
# Run-time: marriage into the unnamed population, at the opening's own rates
# ---------------------------------------------------------------------------------------------

MARRIAGE_GRID_DAYS = 30  # the household-life clock always fires on this grid


def resolve_unnamed_marriages(conn: sqlite3.Connection, day: int, *, event_logger=None) -> int:
    """Single named adults marry people from the unnamed population at the world's marriage rates.

    Draws happen only on the fixed 30-day grid (never on other household-life passes), so results
    do not depend on how a run is split into steps.  The partner already existed in the local
    population and is revealed, never conjured by demand.
    """
    if day <= 0 or day % MARRIAGE_GRID_DAYS:
        return 0
    elapsed = MARRIAGE_GRID_DAYS
    seed = _world_seed(conn)
    formed = 0
    for p in _person_rows(conn, day):
        aid = int(p["id"])
        if conn.execute("SELECT 1 FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?)", (aid, aid)).fetchone():
            continue
        meta = json.loads(p["metadata_json"] or "{}")
        if meta.get("marital_status_basis") == "canon_partial":
            continue
        age = (day - int(p["birth_day"])) / 365.0
        if age > 70.0:
            continue
        sex = str(p["demographic_sex"]); lc = str(p["lc"])
        ended = conn.execute("SELECT MAX(ended_day) FROM household_unions WHERE status<>'active' AND (actor_a_id=? OR actor_b_id=?)",
                             (aid, aid)).fetchone()[0]
        if meta.get("marital_status") == "widowed" or ended is not None:
            widowed_day = int(ended if ended is not None else (meta.get("widowed_day") or day - 365))
            annual = remarriage_hazard(age) if day - widowed_day >= 365 else 0.0
        else:
            annual = first_marriage_hazard(age, marriage_curve_for(conn, aid, sex, lc)[0])
        prob = 1.0 - (1.0 - annual) ** (elapsed / 365.0)
        key = f"unnamed-marriage:{seed}:{aid}:{day}"
        if _rng(key).random() >= prob:
            continue
        from .cultivation import location_in_hearth
        spouse = _draw_spouse(_rng(f"spouse:{key}"), age, sex, lc,
                              location_in_hearth(conn, int(p["loc"]) if p["loc"] is not None else None))
        spouse["married_at"] = age; spouse["age_now"] = spouse["age_at_marriage"]
        loc = int(p["loc"]) if p["loc"] is not None else None
        spouse_id = _reveal_spouse(conn, aid, spouse, key=key, day=day, location_id=loc, reason="run_time_marriage")
        from .household_life import resolved_biological_birth_parent
        hist = {"children": [], "desired_children": _weighted(_rng(f"desired:{key}"), _DESIRED_CHILDREN), "last_birth_at": None}
        plan = _family_plan(hist, sex=sex, person_age=age, spouse_age=spouse["age_now"], day=day, key=key,
                            birth_parent_id=resolved_biological_birth_parent(conn, aid, spouse_id), mode="RUN_TIME_MARRIAGE_FAMILY_CONTINUITY",
                            married_day=day)
        _form_revealed_union(conn, aid, spouse_id, married_day=day, day=day, family_plan=plan, basis="run_time_marriage",
                             union_kind=spouse["union_kind"])
        _mark(conn, aid, {"marital_status": "married", "marital_status_basis": "run_time_marriage", "spouse_actor_id": spouse_id})
        if event_logger:
            name = conn.execute("SELECT name FROM actors WHERE id=?", (aid,)).fetchone()[0]
            sname = conn.execute("SELECT name FROM actors WHERE id=?", (spouse_id,)).fetchone()[0]
            event_logger(day=day, event_type="life:union", title=f"Marriage: {name} and {sname}",
                         summary=f"{name} married {sname}.", severity=1, source_actor_id=aid,
                         target_actor_ids=(spouse_id,), location_id=loc)
        formed += 1
    return formed
