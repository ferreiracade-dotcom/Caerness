"""Law, officials, connected people and the Pad at the opening (mob minimum, task 8).

Everything is read from the package's law data (`law_rules`) and outfit data (`outfit_rules`): jurisdictions, rules,
agencies (one `law_enforcement_profiles` row each, plus a `law_offices` row), the level-4 seats the underworld must deal
with, the connected people the setting ties to the outfits, and the Pad: an envelope for each of `pad_officers`
officers, paid from the families' purses through a bagman (the money moves in `org_money.post_period`).

Every person is pulled up from the city's background population (never a new actor row). Level 4 people are
reviewed daily, level 3 weekly, both on a quiet routine (`orgs.set_level`). Open seats are filled with
`facts.fill_open`. No world-specific word or number lives here: names, titles and figures come from package data.
"""
from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from collections import Counter, defaultdict

from . import facts
from .design import figure, run_seed
from .law import add_rule, create_jurisdiction, create_office
from .outfit_opening import city_location, feelings_toward, outfit_actor, pull_up
from .orgs import give_personality, head_of, set_level
from .world_package import law_rules, outfit_rules, package_for, system_enabled

OFFICIAL_AGES = (40, 65)
CONNECTED_AGES = (40, 70)
# the law table's authority_kind has a closed list; the data's own kind is kept in the row's metadata
_AUTHORITY = {"municipal": "local", "county": "local"}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _rng(conn: sqlite3.Connection, key: str) -> random.Random:
    return random.Random(f"{run_seed(conn)}:law:{key}")


def _institution(conn: sqlite3.Connection, name: str | None) -> int | None:
    if not name:
        return None
    r = conn.execute("SELECT id FROM actors WHERE name=? AND actor_type='institution'", (name,)).fetchone()
    return int(r[0]) if r else None


def _location_id(conn: sqlite3.Connection, name: str | None) -> int | None:
    if not name:
        return None
    r = conn.execute("SELECT id FROM locations WHERE name=? ORDER BY id LIMIT 1", (name,)).fetchone()
    return int(r[0]) if r else None


# ---- places and precincts ----

def _chain(conn: sqlite3.Connection, location_id: int | None) -> list[int]:
    """The place and its parents up to the root."""
    out: list[int] = []
    cur = None if location_id is None else int(location_id)
    while cur is not None and cur not in out:
        out.append(cur)
        r = conn.execute("SELECT parent_location_id FROM locations WHERE id=?", (cur,)).fetchone()
        cur = int(r[0]) if r and r[0] is not None else None
    return out


def _precincts(conn: sqlite3.Connection) -> list[tuple[int, int, int]]:
    """(institution actor id, place id, profile id) of every precinct agency."""
    out = []
    for r in conn.execute("SELECT id,institution_actor_id,location_id,metadata_json FROM law_enforcement_profiles ORDER BY id"):
        if r["institution_actor_id"] is not None and json.loads(r["metadata_json"] or "{}").get("kind") == "precinct":
            out.append((int(r["institution_actor_id"]), int(r["location_id"]), int(r["id"])))
    return out


def _nearest_precinct(conn: sqlite3.Connection, location_id: int | None, precincts: list[tuple[int, int, int]]) -> tuple[int, int, int] | None:
    """The precinct whose place shares the nearest ancestor below the city root with the location (the place itself
    counts): cost is the steps from each side up to that ancestor; ties go to a stable hash of the place and precinct."""
    g = _chain(conn, location_id)
    if len(g) < 2:
        return None
    best, best_cost = None, None
    for p in precincts:
        pc = _chain(conn, p[1])
        shared = [a for a in g[:-1] if a in pc[:-1]]  # the last link is the root and never counts
        if not shared:
            continue
        cost = min(g.index(a) + pc.index(a) for a in shared)
        # equal distance (a place between two precincts): a stable hash of the place and precinct, not the lower id, so
        # a family's ground is not always dealt to the same one
        tie = hashlib.sha256(f"{run_seed(conn)}:law:precinct:{int(location_id)}:{p[0]}".encode()).hexdigest()
        if best_cost is None or (cost, tie) < best_cost:
            best, best_cost = p, (cost, tie)
    return best


def precinct_for_location(conn: sqlite3.Connection, location_id: int | None) -> int | None:
    """The institution actor id of the precinct that covers a place, or None (the department itself answers)."""
    p = _nearest_precinct(conn, location_id, _precincts(conn))
    return p[0] if p else None


def agency_for(conn: sqlite3.Connection, location_id: int | None, matter_kind: str, *, federal: bool = False) -> int | None:
    """The `law_enforcement_profiles.id` that takes a matter: federal matters by the package's federal routing, an
    organized-crime matter by its own unit, a place inside a county jurisdiction's own location by that county's
    prosecutor, otherwise the precinct that covers the place (the department's profile where none does)."""
    rules = law_rules(package_for(conn))
    routing = rules.get("agency_routing") or {}
    if not routing:
        return None

    def profile(key: str | None) -> int | None:
        if key is None:
            return None
        r = conn.execute("SELECT id FROM law_enforcement_profiles WHERE profile_key=?", (key,)).fetchone()
        return int(r[0]) if r else None

    if federal:
        fed = routing.get("federal") or {}
        return profile(fed.get(matter_kind, fed.get("default")))
    city = routing.get("city") or {}
    if matter_kind in city and city[matter_kind] != "precinct":
        return profile(city[matter_kind])
    chain = set(_chain(conn, location_id))
    for jkey, agency_key in (routing.get("county") or {}).items():
        r = conn.execute("SELECT location_id FROM law_jurisdictions WHERE jurisdiction_key=?", (jkey,)).fetchone()
        if r and r[0] is not None and int(r[0]) in chain:
            return profile(agency_key)
    p = _nearest_precinct(conn, location_id, _precincts(conn))
    if p is not None:
        return p[2]
    return profile(city.get("fallback"))


# ---- jurisdictions, rules, agencies ----

def _load_jurisdictions(conn: sqlite3.Connection, rules: dict) -> dict[str, int]:
    js = rules["jurisdictions"]
    top = max(int(j["priority"]) for j in js.values())
    ids: dict[str, int] = {}
    for key, j in js.items():
        # the data's priority puts the lowest number first; the table puts the highest first
        ids[key] = create_jurisdiction(
            conn, key, j.get("name") or key.replace("_", " ").title(), _AUTHORITY.get(j["authority_kind"], "other"),
            location_id=_location_id(conn, j.get("location")), priority=top + 1 - int(j["priority"]),
            metadata={"authority_kind": j["authority_kind"], "data_priority": int(j["priority"])})
        for rk, r in (rules.get("rules") or {}).items():
            add_rule(conn, ids[key], f"{key}:{rk}", rk.replace("_", " ").title(), "criminal",
                     evidence_threshold=100.0 * float(figure(conn, r["evidence_threshold"])),
                     metadata={"matter": rk, "jurisdiction": key})
    return ids


def _office_subject(conn: sqlite3.Connection, key: str | None) -> str | None:
    r = conn.execute("SELECT subject FROM world_facts WHERE key=?", (key,)).fetchone() if key else None
    return str(r[0]) if r else None


def _load_agencies(conn: sqlite3.Connection, rules: dict, jur: dict[str, int], day: int) -> dict[str, int]:
    """One law_enforcement_profiles row and one law_offices row per agency; returns profile ids by agency key."""
    city = city_location(conn)
    out: dict[str, int] = {}
    for key, a in rules["agencies"].items():
        inst = _institution(conn, a.get("institution"))
        home = conn.execute("SELECT home_location_id FROM actors WHERE id=?", (inst,)).fetchone() if inst else None
        loc = int(home[0]) if home and home[0] is not None else city
        name = a.get("institution") or _office_subject(conn, a.get("office")) or key
        capacity = 100.0 * float(figure(conn, a["capacity"]))
        integrity = 100.0 * float(figure(conn, a["integrity"]))
        corruption = 100.0 - integrity  # the pressure on a seat is the room its integrity leaves
        meta = {"agency_key": key, "pad_reaches": bool(a["pad_reaches"]), "kind": a.get("kind", "agency"),
                "jurisdiction": a["jurisdiction"], "authority_kind": rules["jurisdictions"][a["jurisdiction"]]["authority_kind"]}
        if a.get("note"):
            meta["note"] = a["note"]
        out[key] = int(conn.execute(
            """INSERT INTO law_enforcement_profiles(profile_key,name,location_id,institution_actor_id,authority_kind,capacity,integrity,
                   corruption_pressure,inspection_focus,last_review_day,next_review_day,status,metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?)""",
            (key, name, loc, inst, meta["authority_kind"], capacity, integrity, corruption, 50.0, day, day + 30,
             json.dumps(meta, sort_keys=True))).lastrowid)
        create_office(conn, key, name, jur[a["jurisdiction"]], location_id=loc, institution_actor_id=inst, capacity=capacity,
                      integrity=integrity, corruption_pressure=corruption, metadata=meta)
    return out


# ---- people ----

def _sex_draws(conn: sqlite3.Connection, stream: str, n: int, male_share: float) -> list[str]:
    rng = _rng(conn, f"sex:{stream}")
    return ["male" if rng.random() < male_share else "female" for _ in range(n)]


def _seeded_holder(conn: sqlite3.Connection, institution_id: int | None, role_text: str, used: set[int], seed_roles=()) -> int | None:
    """A seeded person who already holds this seat: the same role text, one of the entry's `seed_roles`, or the same
    leading title (the first word) in the same institution."""
    if institution_id is None:
        return None
    rows = conn.execute(
        """SELECT m.member_actor_id AS aid,m.role_text AS role FROM institution_memberships m JOIN actors a ON a.id=m.member_actor_id
           WHERE m.institution_actor_id=? AND m.status='active' AND a.status='active' ORDER BY m.member_actor_id""",
        (int(institution_id),)).fetchall()
    want = role_text.lower()
    exact = {want, *(str(s).lower() for s in seed_roles)}
    lead = want.replace(",", " ").split()[0]
    for r in rows:
        if int(r["aid"]) not in used and str(r["role"] or "").lower() in exact:
            return int(r["aid"])
    for r in rows:
        words = str(r["role"] or "").lower().replace(",", " ").split()
        if int(r["aid"]) not in used and words and words[0] == lead:
            return int(r["aid"])
    return None


def _seat(conn: sqlite3.Connection, actor_id: int, institution_id: int | None, role_text: str, kind: str, day: int, level: int = 4) -> None:
    """A seat is a membership with the role text (unless he already has one there), a personality, and a level."""
    give_personality(conn, actor_id, "law")
    if institution_id is not None and not conn.execute(
            "SELECT 1 FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=? AND status='active'",
            (int(institution_id), int(actor_id))).fetchone():
        conn.execute(
            """INSERT OR IGNORE INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json)
               VALUES (?,?,?,?, 'active',?,?)""", (int(institution_id), int(actor_id), kind, role_text, int(day), '["law opening"]'))
    set_level(conn, actor_id, level, day)


def _name_group_picks(conn: sqlite3.Connection, stream: str, groups: list[str], n: int) -> list[str]:
    """`n` name groups drawn from `groups` at the city's own group weights."""
    weights = package_for(conn).name_groups or {}
    gs = [g for g in groups if float((weights.get(g) or {}).get("weight", 0)) > 0] or list(groups)
    ws = [float((weights.get(g) or {}).get("weight", 1)) for g in gs]
    rng = _rng(conn, f"groups:{stream}")
    return [rng.choices(gs, weights=ws)[0] for _ in range(n)]


def _pull_slots(conn: sqlite3.Connection, stream: str, slots: list[dict], ages: tuple[int, int]) -> list[int]:
    """Pull up one person for each slot ({"group": name group or None, "sex": "male"/"female"/None, "domain": occupation
    domain, "rank": optional, "criminal_weight": optional}), batched by (group, sex) because every pull-up is a pass over
    the city's candidates. Within a batch a slot with a lower `rank` gets an older person (a captain is older than a
    patrolman). Returns the actor ids in slot order and gives each his slot's occupation domain."""
    got: dict[int, int] = {}
    batches: dict[tuple, list[int]] = defaultdict(list)
    for i, s in enumerate(slots):
        batches[(s.get("group"), s.get("sex"))].append(i)
    for (group, sex), idx in sorted(batches.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        people = pull_up(conn, len(idx), stream=f"{stream}:{group}:{sex}", name_group=group, sex=sex, ages=ages,
                         criminal_weight=float(slots[idx[0]].get("criminal_weight", 0.0)))
        if len(people) < len(idx):
            raise RuntimeError(f"law opening could not pull up {len(idx)} people for {stream} ({group}, {sex}); got {len(people)}")
        if any("rank" in slots[i] for i in idx):
            born = {int(r[0]): int(r[1]) for r in conn.execute(
                f"SELECT actor_id,birth_day FROM actor_life_profiles WHERE actor_id IN ({','.join(str(int(a)) for a in people)})")}
            people = sorted(people, key=lambda a: (born[int(a)], int(a)))  # oldest first
            idx = sorted(idx, key=lambda i: (slots[i].get("rank", 0), i))
        for i, a in zip(idx, people):
            got[i] = int(a)
    out = [got[i] for i in range(len(slots))]
    by_domain: dict[str, list[tuple]] = defaultdict(list)
    for s, a in zip(slots, out):
        by_domain[s["domain"]].append((s["domain"], f"ordinary_{s['domain']}", int(a)))
    for rows in by_domain.values():
        conn.executemany("UPDATE background_person_profiles SET occupation_domain=?,social_archetype=? WHERE actor_id=?", rows)
    return out


def outfit_head(conn: sqlite3.Connection, outfit_key: str, spec: dict) -> int | None:
    """The man at the top of an outfit: the first active holder of its kind's head role."""
    return head_of(conn, outfit_actor(conn, spec["institution"]))


def _create_institution(conn: sqlite3.Connection, name: str, domain: str, note: str) -> int:
    """An institution the bible names but the seed does not hold (a union's own body): a plain actor row."""
    return int(conn.execute(
        "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) VALUES (?,'institution',?,?,?,'active',?,0)",
        (name, f"{domain} organization", city_location(conn), city_location(conn), note)).lastrowid)


def _woman_barred(rules: dict, *tokens: str | None) -> bool:
    return any(t and t in (rules.get("no_woman_seats") or []) for t in tokens)


def _fill_officials(conn: sqlite3.Connection, rules: dict, day: int, used: set[int], heads: dict[int, int]) -> dict[str, int]:
    """The level-4 seats: each Open office in `level4_offices` and each of `level4_roles`, seeded holders first, the rest
    pulled up in one batch (age 40-65; sex by `male_share` for police, `male_share_law_official` otherwise)."""
    domains = rules.get("office_domains") or {}
    share_police = float(outfit_rules(package_for(conn))["male_share"]["pad_officer"])
    share_other = float(figure(conn, "male_share_law_official"))
    rng = _rng(conn, "offices:sex")

    def slot(domain: str, *barred: str) -> dict:
        share = share_police if domain == "soldier" else share_other
        woman = rng.random() >= share and not _woman_barred(rules, *barred)
        return {"group": None, "sex": "female" if woman else "male", "domain": domain}

    plan: list[dict] = []  # {"text","inst","aid","key","slot"}
    for key in rules["level4_offices"]:
        fact = conn.execute("SELECT subject,institution_key,holder_actor_id FROM world_facts WHERE key=?", (key,)).fetchone()
        if fact is None:
            raise RuntimeError(f"level-4 office {key!r} is not a world fact")
        inst = conn.execute("SELECT entity_id FROM source_identity_map WHERE entity_kind='institution' AND source_key=?",
                            (fact["institution_key"],)).fetchone() if fact["institution_key"] else None
        held = fact["holder_actor_id"] is not None
        plan.append({"text": str(fact["subject"]), "inst": int(inst[0]) if inst else None, "key": key,
                     "aid": int(fact["holder_actor_id"]) if held else None,
                     "slot": None if held else slot(domains.get(key, domains.get("default", "clerk")), key)})
        if held:
            used.add(plan[-1]["aid"])
    n_offices = len(plan)
    for role in rules["level4_roles"]:
        name, text, domain = role["institution"], role["role_text"], role["occupation_domain"]
        inst = _institution(conn, name)
        if inst is None:
            inst = _create_institution(conn, name, domain, "made for a seat the setting names (Part IV 2.7); no officers are seeded")
        n = int(round(figure(conn, role["figure"]))) if role.get("figure") else 1
        for _ in range(n):
            seeded = _seeded_holder(conn, inst, text, used, role.get("seed_roles", ()))
            if seeded is not None:
                used.add(seeded)
            plan.append({"text": text, "inst": inst, "key": None, "aid": seeded,
                         "slot": None if seeded is not None else slot(domain, text)})
    new = [p for p in plan if p["aid"] is None]
    people = _pull_slots(conn, "law:officials", [p["slot"] for p in new], OFFICIAL_AGES)
    for p, a in zip(new, people):
        p["aid"] = a
        used.add(a)
        conn.execute("UPDATE actors SET subtype=? WHERE id=?", (p["text"], a))
        if p["key"] is not None:
            facts.fill_open(conn, p["key"], a, "the opening needs a holder")
    for p in plan:
        _seat(conn, p["aid"], p["inst"], p["text"], "office", day)
        if p["inst"] is not None:
            heads.setdefault(p["inst"], p["aid"])
    return {"offices": n_offices, "role_holders": len(plan) - n_offices}


def _fill_connected(conn: sqlite3.Connection, oc: dict, day: int, used: set[int]) -> dict[str, int]:
    """The bankers, contractors, financiers, lawyers and association heads the setting ties to the outfits (one batch)."""
    share = float(figure(conn, "male_share_connected"))
    rng = _rng(conn, "connected:sex")
    plan: list[dict] = []
    for c in oc.get("connected", []):
        inst = _institution(conn, c.get("institution"))
        for _ in range(int(c["count"])):
            seeded = _seeded_holder(conn, inst, c["role_text"], used)
            if seeded is not None:
                used.add(seeded)
            plan.append({"c": c, "inst": inst, "aid": seeded, "slot": None if seeded is not None else
                         {"group": c.get("name_group"), "sex": "male" if rng.random() < share else "female",
                          "domain": c["occupation_domain"], "criminal_weight": 0.5}})
    new = [p for p in plan if p["aid"] is None]
    people = _pull_slots(conn, "law:connected", [p["slot"] for p in new], CONNECTED_AGES)
    for p, a in zip(new, people):
        p["aid"] = a
        used.add(a)
        conn.execute("UPDATE actors SET subtype=? WHERE id=?", (p["c"]["role_text"], a))
    for p in plan:
        c, a = p["c"], p["aid"]
        _seat(conn, a, p["inst"], c["role_text"], "connected", day)
        if c.get("tied_to"):
            boss = outfit_head(conn, c["tied_to"], oc["outfits"][c["tied_to"]])
            if boss is not None and boss != a:
                feelings_toward(conn, a, boss, day, _rng(conn, f"connected:tie:{a}"))
    return {"connected": len(plan)}


# ---- the Pad ----

def _family_precincts(conn: sqlite3.Connection, oc: dict, precincts) -> dict[str, Counter]:
    """Per family: how many of its crews work each precinct's ground."""
    out: dict[str, Counter] = {}
    for key, spec in oc["outfits"].items():
        if spec.get("shape") != "family":
            continue
        oid = outfit_actor(conn, spec["institution"])
        cnt: Counter = Counter()
        for r in conn.execute("SELECT ground_location_id FROM org_units WHERE org_actor_id=? AND ground_location_id IS NOT NULL ORDER BY id", (oid,)):
            p = _nearest_precinct(conn, r[0], precincts)
            if p is not None:
                cnt[p[0]] += 1
        out[key] = cnt
    return out


def _captain_of(conn: sqlite3.Connection, precinct_id: int, heads: dict[int, int]) -> int | None:
    return heads.get(int(precinct_id))


def _build_pad(conn: sqlite3.Connection, rules: dict, oc: dict, day: int, heads: dict[int, int]) -> dict[str, int]:
    from . import outfit_money  # the design allocation lives with the money (outfit_money imports outfit_opening)
    pad = rules["pad"]
    precincts = _precincts(conn)
    fam_prec = _family_precincts(conn, oc, precincts)
    prec_name = {p[0]: str(conn.execute("SELECT name FROM actors WHERE id=?", (p[0],)).fetchone()[0]) for p in precincts}
    fams = [f for f in sorted(fam_prec) if fam_prec[f]]
    if not fams:
        return {"pad_officers": 0}
    # the precinct captain is paid by the family with most crews on the precinct's ground
    primary: dict[int, str] = {}
    for pid in sorted({p for f in fams for p in fam_prec[f]}):
        primary[pid] = max(fams, key=lambda f: (fam_prec[f].get(pid, 0), -fams.index(f)))
    n_total = int(round(figure(conn, pad["officers_figure"])))
    tiers = pad["tiers"]
    count = {t["key"]: int(round(figure(conn, t["officers_figure"]))) for t in tiers[:-1]}
    count[tiers[-1]["key"]] = n_total - sum(count.values())
    weekly = {t["key"]: float(figure(conn, t["weekly_figure"])) for t in tiers}
    items_total = sum(count[k] * weekly[k] for k in count)
    split = outfit_money.design_allocation(conn)[pad["family_split"]]
    weight_sum = sum(float(split[f]) for f in fams)
    remaining = {f: items_total * float(split[f]) / weight_sum for f in fams}
    first = tiers[0]["key"]
    # (family, precinct, tier) slots; the captains' seats first, then the dollars go to whoever is furthest below target
    slots: list[dict] = []
    for pid, f in sorted(primary.items()):
        slots.append({"family": f, "precinct": pid, "tier": first, "captain": True})
        remaining[f] -= weekly[first]
        count[first] -= 1
    if count[first] < 0:
        raise RuntimeError("more precincts on family ground than seats in the Pad's top tier")
    tally = {f: {t["key"]: 0 for t in tiers} for f in fams}
    for t in tiers:
        for _ in range(count[t["key"]]):
            f = max(fams, key=lambda x: (remaining[x], -fams.index(x)))
            remaining[f] -= weekly[t["key"]]
            tally[f][t["key"]] += 1
    # each family's seats in a tier go round its precincts, the ones with more crews more often
    nxt: dict[tuple, int] = defaultdict(int)
    for f in fams:
        cycle = [p for p, c in sorted(fam_prec[f].items(), key=lambda kv: (-kv[1], kv[0])) for _ in range(c)]
        for t in tiers:
            for _ in range(tally[f][t["key"]]):
                slots.append({"family": f, "precinct": cycle[nxt[(f, t["key"])] % len(cycle)], "tier": t["key"], "captain": False})
                nxt[(f, t["key"])] += 1
    # people: captains are the level-4 holders; everyone else is pulled up
    groups = pad["officer_name_groups"]
    share = float(outfit_rules(package_for(conn))["male_share"]["pad_officer"])
    rng = _rng(conn, "pad:sex")
    women = int(n_total * (1.0 - share) + rng.random())  # stratified: 99 percent of 300 is 3 or 4 women
    last = tiers[-1]["key"]
    pat = [s for s in slots if s["tier"] == last]
    female_idx = set(rng.sample(range(len(pat)), min(women, len(pat))))
    for i, s in enumerate(pat):
        s["sex"] = "female" if i in female_idx else "male"
    todo: list[dict] = []
    for ti, t in enumerate(tiers):
        mine = [s for s in slots if s["tier"] == t["key"] and not s["captain"]]
        for s, g in zip(mine, _name_group_picks(conn, f"pad:{t['key']}", groups, len(mine))):
            s.update(group=g, domain="soldier", rank=ti)
            s.setdefault("sex", "male")
        todo += mine
    lo = min(int(t["ages"][0]) for t in tiers)
    hi = max(int(t["ages"][1]) for t in tiers)
    for s, a in zip(todo, _pull_slots(conn, "law:pad", todo, (lo, hi))):  # one wide band; the higher the tier, the older the man
        s["officer"] = a
    for s in slots:
        if s["captain"]:
            cap = _captain_of(conn, s["precinct"], heads)
            if cap is None:
                raise RuntimeError(f"precinct {prec_name[s['precinct']]} has no captain to carry the top envelope")
            s["officer"] = cap
    title = {t["key"]: t["title"] for t in tiers}
    n_key: Counter = Counter()
    for s in sorted(slots, key=lambda x: (x["precinct"], tiers.index(next(t for t in tiers if t["key"] == x["tier"])), not x["captain"], x["family"])):
        n_key[(s["precinct"], s["tier"])] += 1
        s["n"] = n_key[(s["precinct"], s["tier"])]
        if not s["captain"]:
            text = f"{title[s['tier']]}, {prec_name[s['precinct']]}"
            conn.execute("UPDATE actors SET subtype=? WHERE id=?", (text, s["officer"]))
            _seat(conn, s["officer"], s["precinct"], text, "member", day, level=3)
    # bagmen: sergeants of the paying family; the group is the family's seats in the precinct
    bag_max = max(1, int(round(figure(conn, pad["bagmen_figure"]))))
    sergeant = tiers[1]["key"]
    by_family: dict[str, list[dict]] = defaultdict(list)
    for s in slots:
        by_family[s["family"]].append(s)
    for f, group in by_family.items():
        anyone = [s for s in group if s["tier"] == sergeant]
        for pid in sorted({s["precinct"] for s in group}):
            there = [s for s in group if s["precinct"] == pid]
            bags = [s for s in there if s["tier"] == sergeant][:bag_max] or anyone[:1]
            for i, s in enumerate(sorted(there, key=lambda x: (x["tier"], x["n"]))):
                if s in bags:
                    s["bagman"] = s["officer"]
                elif bags:
                    s["bagman"] = bags[i % len(bags)]["officer"]
                else:
                    s["bagman"] = None
    payer = {f: outfit_actor(conn, oc["outfits"][f]["institution"]) for f in fams}
    conn.executemany(
        "INSERT INTO org_arrangements(kind,official_actor_id,payer_kind,payer_id,position_key,weekly_usd,go_between_actor_id,status,started_day) VALUES (?,?,'org',?,?,?,?,'active',?)",
        [(pad["arrangement_kind"], s["officer"], payer[s["family"]], f"{s['precinct']}:{s['tier']}:{s['n']}", weekly[s["tier"]], s.get("bagman"), day)
         for s in sorted(slots, key=lambda x: (x["precinct"], x["tier"], x["n"]))])
    return {"pad_officers": len(slots), "pad_precincts": len(primary),
            "pad_bagmen": len({s["bagman"] for s in slots if s.get("bagman") is not None})}


# ---- the opening ----

def build(conn: sqlite3.Connection, day: int | None = None) -> dict[str, int]:
    """Jurisdictions, agencies, level-4 officials, connected people and the Pad; counts by name."""
    if not system_enabled(conn, "outfits"):
        return {}
    pkg = package_for(conn)
    rules, oc = law_rules(pkg), outfit_rules(pkg)
    if not rules or conn.execute("SELECT 1 FROM law_jurisdictions WHERE jurisdiction_key='city' LIMIT 1").fetchone():
        return {}
    day = _day(conn) if day is None else int(day)
    counts: dict[str, int] = {}
    jur = _load_jurisdictions(conn, rules)
    counts["jurisdictions"] = len(jur)
    counts["rules"] = int(conn.execute("SELECT COUNT(*) FROM law_rules").fetchone()[0])
    agencies = _load_agencies(conn, rules, jur, day)
    counts["agencies"] = len(agencies)
    used: set[int] = set()
    heads: dict[int, int] = {}
    counts.update(_fill_officials(conn, rules, day, used, heads))
    for pid, head in heads.items():  # an office's presiding person is whoever heads its institution
        conn.execute("UPDATE law_offices SET presiding_actor_id=? WHERE institution_actor_id=?", (head, pid))
    counts.update(_fill_connected(conn, oc, day, used))
    counts.update(_build_pad(conn, rules, oc, day, heads))
    return counts
