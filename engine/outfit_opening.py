"""Build organisations as people at the opening: one data-driven builder for any organisation with roles.

Everyone is a real person pulled up from the city's background population (never a new actor row), placed under a
role with a superior, feelings toward that superior, a personality and a simulation level. Seeded Example persons
keep their seats and count toward the drawn figures instead of adding to them.

The package says what shape each kind of organisation has (orgs.json `kinds.<kind>.opening`): a `units` layout is a head,
executives, unit leaders each on a ground of the organisation, members dealt to the units and dependants spread over the
members (a family, a company with departments, a duchy with manors); a `ranks` layout is a list of roles each filled to a
figure with a superior rule (a bank, a club, a handful). Every role word, count figure, age band and share is data."""
from __future__ import annotations

import math
import random
import sqlite3

from . import facts
from .design import figure, run_seed
from . import orgs
from .orgs import clamp01
from .person_ecology import resolve_background_people
from .relationships import ensure_relationship
from .world_package import org_rules, outfit_rules, package_for, system_enabled


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def city_location(conn: sqlite3.Connection) -> int:
    """The location that holds the city's background population source (the largest one)."""
    row = conn.execute("SELECT location_id FROM background_population_sources WHERE location_id IS NOT NULL ORDER BY population_estimate DESC, id LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("no background population source to pull outfit members from")
    return int(row[0])


def outfit_actor(conn: sqlite3.Connection, institution: str) -> int:
    row = conn.execute("SELECT id FROM actors WHERE name=? AND actor_type='institution'", (institution,)).fetchone()
    if row is None:
        raise RuntimeError(f"outfit institution {institution!r} is not an actor in this opening")
    return int(row[0])


def _seat(conn: sqlite3.Connection, actor_id: int, org_actor_id: int, role_key: str, **kw) -> int:
    return orgs.seat(conn, actor_id, org_actor_id, role_key, provenance="outfit opening", **kw)


def kind_data(rules_org: dict, spec: dict) -> dict:
    """The orgs.json entry for the organisation's kind (its shape): head, unit leader, labels and `opening`."""
    return dict((rules_org.get("kinds") or {}).get(spec["shape"]) or {})


def write_profile(conn: sqlite3.Connection, key: str, spec: dict, outfit_id: int, kind: dict | None = None) -> None:
    """What kind of organisation this institution is: its shape from outfits.json, the kind's sphere, its package key."""
    sphere = (kind or {}).get("sphere") or "underworld"
    conn.execute("INSERT OR IGNORE INTO org_profiles(org_actor_id,org_kind,sphere,package_key) VALUES (?,?,?,?)",
                 (int(outfit_id), spec["shape"], sphere, key))


def seat_subtype(role_key: str, institution: str, in_roles=()) -> str:
    """The subtype a seated person carries, worded like the seeded ones ("<Role> in the <Org>" for the roles the data
    lists in `in_roles`, "<Role> of the <Org>" for the rest).

    It must not be the pull-up default ("resolved_<occupation>"): the role-kind readers match words in the subtype,
    and an ordinary tradesman would be handed a Caerness household-retainer career."""
    return f"{role_key.capitalize()} {'in' if role_key in in_roles else 'of'} the {institution}"


def pull_up(conn: sqlite3.Connection, n: int, *, stream: str, name_group: str | None, sex: str | None,
            ages: tuple[int, int], subtype: str | None = None, criminal_weight: float = 1.0) -> list[int]:
    """A batch pull-up for one organisation role. The run seed is part of the pick seed, so a redraw is a different crowd."""
    return resolve_background_people(
        conn, n, reason="outfit_opening", demand_kind="outfit_member", subtype=subtype, location_id=city_location(conn),
        min_age=ages[0], max_age=ages[1], demographic_sex=sex, name_group=name_group, criminal_weight=criminal_weight,
        pick_seed=f"{run_seed(conn)}:outfit:{stream}",
    )


def seeded_by_rank(conn: sqlite3.Connection, outfit_id: int, rules: dict, spec: dict | None = None) -> tuple[dict[str, list[int]], list[tuple[int, str]]]:
    """Seeded members of an organisation by role, plus the ones left out. An outfit with `seed_roles` (phrase in the role
    text -> role, first match wins) reads those; otherwise the first word of the role text goes through `seed_role_to_rank`."""
    mapping = rules.get("seed_role_to_rank", {})
    phrases = list((spec or {}).get("seed_roles", {}).items())
    out: dict[str, list[int]] = {}
    unplaced: list[tuple[int, str]] = []
    for r in conn.execute(
        """SELECT m.member_actor_id,m.role_text FROM institution_memberships m JOIN actors a ON a.id=m.member_actor_id
           WHERE m.institution_actor_id=? AND m.status='active' AND a.status='active' ORDER BY m.member_actor_id""", (outfit_id,)
    ).fetchall():
        text = r["role_text"] or ""
        if phrases:
            rank = next((rk for ph, rk in phrases if ph.lower() in text.lower()), None)
        else:
            rank = mapping.get(text.split(" ", 1)[0])
        if rank is None:
            unplaced.append((int(r["member_actor_id"]), str(r["role_text"])))
        else:
            out.setdefault(rank, []).append(int(r["member_actor_id"]))
    return out, unplaced


def feelings_toward(conn: sqlite3.Connection, actor_id: int, superior_id: int, day: int, rng: random.Random) -> None:
    """How a man feels about the man over him: loyalty and respect around 30, a little resentment."""
    ensure_relationship(
        conn, actor_id, superior_id, day,
        loyalty=max(-100.0, min(100.0, rng.gauss(30, 20))), respect=max(-100.0, min(100.0, rng.gauss(30, 20))),
        resentment=max(-100.0, min(100.0, rng.gauss(10, 15))),
    )


def _age(conn: sqlite3.Connection, actor_id: int, day: int) -> int:
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (int(actor_id),)).fetchone()
    return max(0, (day - int(r[0])) // 365) if r else 40


def inducted_day_for(conn: sqlite3.Connection, actor_id: int, day: int, rng: random.Random, min_age: int) -> int:
    """Inducted a seeded 0 to (age - min_age) years before the opening."""
    return day - int(rng.uniform(0, max(0, _age(conn, actor_id, day) - min_age)) * 365)


def _fill_open_seat(conn: sqlite3.Connection, institution: str, role: str, actor_id: int) -> None:
    """A seat the setting records as an Open slot is filled by whoever sits in it."""
    subject = f"{role.capitalize()} of the {institution}".lower()
    for r in conn.execute("SELECT key,subject FROM world_facts WHERE tag='Open' AND holder_actor_id IS NULL").fetchall():
        if str(r["subject"]).lower() == subject:
            facts.fill_open(conn, r["key"], actor_id, "seated at the opening")


def _dependent_groups(conn: sqlite3.Connection, male_share: float, own_share: float, own_group: str, n: int,
                      rng: random.Random) -> list[tuple[str, str]]:
    """One (name group, sex) per dependant: `own_share` from the organisation's own group, the rest by the city's group weights."""
    groups = package_for(conn).name_groups or {}
    others = sorted((g, float(v.get("weight", 0))) for g, v in groups.items() if g != own_group and float(v.get("weight", 0)) > 0)
    out: list[tuple[str, str]] = []
    for _ in range(n):
        group = own_group if rng.random() < own_share else rng.choices([g for g, _ in others], weights=[w for _, w in others])[0]
        out.append((group, "male" if rng.random() < male_share else "female"))
    return out


def _band(roles: dict, role: str) -> tuple[int, int]:
    return int(roles[role]["ages"][0]), int(roles[role]["ages"][1])


def _build_units(conn: sqlite3.Connection, key: str, spec: dict, rules: dict, kind: dict, day: int) -> dict:
    """A head, executives, unit leaders each leading a unit on a ground, members dealt to the units, dependants over the members."""
    op = kind["opening"]
    roles = op["roles"]
    inst = spec["institution"]
    outfit_id = outfit_actor(conn, inst)
    write_profile(conn, key, spec, outfit_id, kind)
    group = spec["name_group"]
    head_role, leader_role = kind["head"], kind["unit_leader"]
    member_role, dep_role = op["member_role"], op["dependent_role"]
    in_roles = op.get("in_roles") or ()
    rng = random.Random(f"{run_seed(conn)}:outfit:{key}:structure")
    seeded, unplaced = seeded_by_rank(conn, outfit_id, rules, spec)
    members_total = int(round(figure(conn, spec["members_figure"])))
    per_member = float(figure(conn, spec["dependents_figure"]))
    execs = list(op["executives"])
    leaders_wanted = max(int(figure(conn, op["leader_minimum_figure"])),
                         math.ceil(members_total / float(figure(conn, op["members_per_leader_figure"]))))
    leaders_wanted = max(leaders_wanted, len(seeded.get(leader_role, [])))
    members_wanted = max(len(seeded.get(member_role, [])), members_total - len(execs) - leaders_wanted)
    dependents_wanted = int(round(members_total * per_member))
    inducted_age = int(op["inducted_after_age"])

    def settle(role: str, ids: list[int], wanted: int) -> list[int]:
        """Seeded people first; a seeded surplus beyond an executive seat is left out."""
        keep = ids[:wanted]
        unplaced.extend((i, f"surplus {role}") for i in ids[wanted:])
        return keep

    # Executives: one seat each, seeded or pulled.
    seat: dict[str, int] = {}
    for role in execs:
        got = settle(role, seeded.get(role, []), 1)
        if not got:
            got = pull_up(conn, 1, stream=f"{key}:{role}", name_group=group, sex=roles[role].get("sex"), ages=_band(roles, role),
                          subtype=seat_subtype(role, inst, in_roles))
        seat[role] = got[0]
    head = seat[head_role]
    for role in execs:
        _seat(conn, seat[role], outfit_id, role, unit_id=None, superior_actor_id=None if role == head_role else head,
              level=int(roles[role]["level"]), day=day, inducted_day=inducted_day_for(conn, seat[role], day, rng, inducted_age))
        if role != head_role:
            feelings_toward(conn, seat[role], head, day, rng)
        _fill_open_seat(conn, inst, role, seat[role])

    # Unit leaders, each leading a unit on a ground of the organisation.
    leaders = list(seeded.get(leader_role, []))
    leaders += pull_up(conn, leaders_wanted - len(leaders), stream=f"{key}:{leader_role}", name_group=group,
                       sex=roles[leader_role].get("sex"), ages=_band(roles, leader_role), subtype=seat_subtype(leader_role, inst, in_roles))
    grounds = [int(r[0]) for name in spec["ground"] for r in conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchall()]
    rng.shuffle(grounds)
    units: list[int] = []
    for i, leader in enumerate(leaders):
        surname = str(conn.execute("SELECT name FROM actors WHERE id=?", (leader,)).fetchone()[0]).split()[-1]
        unit = int(conn.execute(
            "INSERT INTO org_units(org_actor_id,leader_actor_id,label,ground_location_id,created_day) VALUES (?,?,?,?,?)",
            (outfit_id, leader, op["unit_label"].format(surname=surname), grounds[i % len(grounds)] if grounds else None, day)).lastrowid)
        units.append(unit)
        _seat(conn, leader, outfit_id, leader_role, unit_id=unit, superior_actor_id=head, level=int(roles[leader_role]["level"]), day=day,
              inducted_day=inducted_day_for(conn, leader, day, rng, inducted_age))
        feelings_toward(conn, leader, head, day, rng)

    # Members dealt to the units round-robin in a seeded order.
    members = list(seeded.get(member_role, []))
    members += pull_up(conn, members_wanted - len(members), stream=f"{key}:{member_role}", name_group=group,
                       sex=roles[member_role].get("sex"), ages=_band(roles, member_role), subtype=seat_subtype(member_role, inst, in_roles))
    rng.shuffle(members)
    patrons_of: list[tuple[int, int]] = list(zip(leaders, units))
    for i, s in enumerate(members):
        leader, unit = leaders[i % len(leaders)], units[i % len(units)]
        _seat(conn, s, outfit_id, member_role, unit_id=unit, superior_actor_id=leader, level=int(roles[member_role]["level"]), day=day,
              inducted_day=inducted_day_for(conn, s, day, rng, inducted_age))
        feelings_toward(conn, s, leader, day, rng)
        patrons_of.append((s, unit))

    # Dependants, spread over the unit leaders and members round-robin in a seeded order.
    dr = roles[dep_role]
    deps = list(seeded.get(dep_role, []))
    need = max(0, dependents_wanted - len(deps))
    plan = _dependent_groups(conn, float(rules["male_share"][dr["male_share_key"]]), float(op["own_group_share"]), group, need, rng)
    for (g, sex) in sorted(set(plan)):
        n = plan.count((g, sex))
        deps += pull_up(conn, n, stream=f"{key}:{dep_role}:{g}:{sex}", name_group=g, sex=sex, ages=_band(roles, dep_role),
                        subtype=seat_subtype(dep_role, inst, in_roles), criminal_weight=float(dr.get("criminal_weight", 1.0)))
    rng.shuffle(deps)
    patrons = list(patrons_of)
    rng.shuffle(patrons)
    st = dr["standing"]
    for i, a in enumerate(deps):
        sup, unit = patrons[i % len(patrons)]
        _seat(conn, a, outfit_id, dep_role, unit_id=unit, superior_actor_id=sup, level=int(dr["level"]), day=day,
              standing=clamp01(rng.gauss(float(st["mean"]), float(st["sd"]))))
        feelings_toward(conn, a, sup, day, rng)

    counts = {role: 1 for role in execs}
    counts.update({leader_role: len(leaders), member_role: len(members), dep_role: len(deps)})
    return {"counts": counts, "units": len(units), "unplaced": unplaced}


def _build_ranks(conn: sqlite3.Connection, key: str, spec: dict, rules: dict, kind: dict, day: int) -> dict:
    """Each role filled to its figure, seeded people first; who answers to whom comes from the kind's `superior` rules."""
    op = kind["opening"]
    roles = op["roles"]
    inst = spec["institution"]
    outfit_id = outfit_actor(conn, inst)
    write_profile(conn, key, spec, outfit_id, kind)
    group = spec.get("name_group")  # None (an organisation with no group of its own): the city's group weights
    male_share = float(rules["male_share"][op["male_share_key"]])
    rng = random.Random(f"{run_seed(conn)}:outfit:{key}:structure")
    seeded, unplaced = seeded_by_rank(conn, outfit_id, rules, spec)
    ranks = spec["ranks"]
    members: dict[str, list[int]] = {}
    for role, r in ranks.items():
        wanted = int(r["count"]) if r.get("count") else int(round(figure(conn, r["figure"])))
        got = list(seeded.get(role, []))[:wanted]
        unplaced.extend((i, f"surplus {role}") for i in seeded.get(role, [])[wanted:])
        plan = ["male" if rng.random() < male_share else "female" for _ in range(wanted - len(got))]
        for sex in sorted(set(plan)):
            got += pull_up(conn, plan.count(sex), stream=f"{key}:{role}:{sex}", name_group=group, sex=sex, ages=_band(roles, role),
                           subtype=seat_subtype(role, inst, op.get("in_roles") or ()), criminal_weight=1.0)
        rng.shuffle(got)
        members[role] = got
    for role, r in ranks.items():
        rule = roles[role].get("superior")
        for i, a in enumerate(members[role]):
            sup = None
            if rule and members.get(rule["role"]):
                above = members[rule["role"]]
                sup = above[0] if rule["pick"] == "first" else above[i % len(above)]
            _seat(conn, a, outfit_id, role, unit_id=None, superior_actor_id=sup, level=int(r["level"]), day=day)
            if sup is not None:
                feelings_toward(conn, a, sup, day, rng)
            else:  # no chain of command: an older man got him the job
                patrons = [m for pr in (op.get("feelings_toward") or {}).get(role, []) for m in members.get(pr, [])]
                if patrons:
                    feelings_toward(conn, a, patrons[i % len(patrons)], day, rng)
            if r.get("count") == 1:
                _fill_open_seat(conn, inst, role, a)
    return {"counts": {role: len(m) for role, m in members.items()}, "units": None, "unplaced": unplaced}


def build_org(conn: sqlite3.Connection, key: str, spec: dict, rules: dict, day: int, kind: dict | None = None) -> dict:
    """One organisation as people, in the layout its kind's `opening` data names ("units" or "ranks"). `kind` defaults to
    the package's orgs.json entry for the spec's shape. Returns {"counts": {role: n}, "units": n | None, "unplaced": [...]}."""
    if kind is None:
        kind = kind_data(org_rules(package_for(conn)), spec)
    layout = (kind.get("opening") or {}).get("layout")
    if layout == "units":
        return _build_units(conn, key, spec, rules, kind, day)
    if layout == "ranks":
        return _build_ranks(conn, key, spec, rules, kind, day)
    raise RuntimeError(f"organisation kind {spec['shape']!r} has no opening layout in the package's orgs data")


def build_all(conn: sqlite3.Connection, day: int) -> dict[str, dict]:
    """Every organisation of the package's outfits data: unit-based ones first, then the rest, in the data's order."""
    pkg = package_for(conn)
    rules, rorg = outfit_rules(pkg), org_rules(pkg)
    outfits = rules.get("outfits", {})

    def is_units(spec: dict) -> bool:
        return (kind_data(rorg, spec).get("opening") or {}).get("layout") == "units"

    out: dict[str, dict] = {}
    for want in (True, False):
        for key, spec in outfits.items():
            if is_units(spec) == want:
                out[key] = build_org(conn, key, spec, rules, day)
    return out


def build(conn: sqlite3.Connection) -> dict[str, int]:
    """Every organisation at the opening; counts by organisation and role ("<key>:<role>": 8)."""
    if not system_enabled(conn, "outfits"):
        return {}
    day = _day(conn)
    counts: dict[str, int] = {}
    for key, res in build_all(conn, day).items():
        for role, n in res["counts"].items():
            counts[f"{key}:{role}"] = n
        if res["units"] is not None:
            counts[f"{key}:units"] = res["units"]
        counts[f"{key}:unplaced_seeded"] = len(res["unplaced"])
    from . import law_opening  # after the organisations: arrangements are paid by their units' earners, and the law's people pull up from the same city
    for name, n in law_opening.build(conn, day).items():
        counts[f"law:{name}"] = n
    from . import outfit_money  # after the people: holdings need the units and men (outfit_money imports this module)
    for key, gross in outfit_money.build_holdings(conn, day).items():
        counts[f"{key}:gross_yearly"] = int(round(gross))
    return counts
