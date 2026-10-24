"""Build the outfits as people at the opening (Saint Jude mob minimum): the four families first.

Everyone is a real person pulled up from the city's background population (never a new actor row), placed under a
rank with a superior, feelings toward that superior, a personality and a simulation level. Seeded Example persons
keep their seats and count toward the drawn figures instead of adding to them."""
from __future__ import annotations

import math
import random
import sqlite3

from . import facts
from .design import figure, run_seed
from .outfits import add_member, clamp01
from .person_ecology import resolve_background_people
from .relationships import ensure_relationship
from .world_package import outfit_rules, package_for, system_enabled

EXEC_AGES = (50, 75)
CAPO_AGES = (38, 65)
SOLDIER_AGES = (25, 65)
ASSOCIATE_AGES = (17, 45)
# Other outfits, by rank key: elders and the men who run things are older, the youngest rung is 18-30.
GANG_AGES = {
    "elder": (45, 75), "middle": (30, 55), "young": (18, 30),
    "banker": (40, 70), "controller": (25, 55), "runner": (18, 35),
    "president": (35, 60), "officer": (28, 55), "member": (22, 50), "prospect": (18, 30),
    "senior": (50, 75), "man": (22, 55),
}
OWN_GROUP_SHARE = 0.80  # associates: share from the outfit's own name group, the rest from the city's other groups


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


def seat_subtype(rank_key: str, institution: str) -> str:
    """The subtype a seated person carries, worded like the seeded ones ("Soldier in the <Name> Family").

    It must not be the pull-up default ("resolved_<occupation>"): the role-kind readers match words in the subtype,
    and an ordinary soldier-by-trade would be handed a Caerness household-retainer career."""
    return f"{rank_key.capitalize()} {'in' if rank_key in ('capo', 'soldier') else 'of'} the {institution}"


def pull_up(conn: sqlite3.Connection, n: int, *, stream: str, name_group: str | None, sex: str | None,
            ages: tuple[int, int], subtype: str | None = None, criminal_weight: float = 1.0) -> list[int]:
    """A batch pull-up for one outfit role. The run seed is part of the pick seed, so a redraw is a different crowd."""
    return resolve_background_people(
        conn, n, reason="outfit_opening", demand_kind="outfit_member", subtype=subtype, location_id=city_location(conn),
        min_age=ages[0], max_age=ages[1], demographic_sex=sex, name_group=name_group, criminal_weight=criminal_weight,
        pick_seed=f"{run_seed(conn)}:outfit:{stream}",
    )


def seeded_by_rank(conn: sqlite3.Connection, outfit_id: int, rules: dict, spec: dict | None = None) -> tuple[dict[str, list[int]], list[tuple[int, str]]]:
    """Seeded members of an outfit by rank, plus the ones left out. A family reads the first word of the role text
    through seed_role_to_rank; an outfit with `seed_roles` (phrase in the role text -> rank, first match wins) reads those."""
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


def made_day_for(conn: sqlite3.Connection, actor_id: int, day: int, rng: random.Random) -> int:
    """Made a seeded 0 to (age - 25) years before the opening."""
    return day - int(rng.uniform(0, max(0, _age(conn, actor_id, day) - 25)) * 365)


def _fill_open_seat(conn: sqlite3.Connection, institution: str, rank: str, actor_id: int) -> None:
    """A seat the setting records as an Open slot is filled by whoever sits in it."""
    subject = f"{rank.capitalize()} of the {institution}".lower()
    for r in conn.execute("SELECT key,subject FROM world_facts WHERE tag='Open' AND holder_actor_id IS NULL").fetchall():
        if str(r["subject"]).lower() == subject:
            facts.fill_open(conn, r["key"], actor_id, "seated at the opening")


def _associate_groups(conn: sqlite3.Connection, rules: dict, own_group: str, n: int, rng: random.Random) -> list[tuple[str, str]]:
    """One (name group, sex) per associate: 80% the outfit's own group, the rest by the city's group weights."""
    groups = package_for(conn).name_groups or {}
    others = sorted((g, float(v.get("weight", 0))) for g, v in groups.items() if g != own_group and float(v.get("weight", 0)) > 0)
    male_share = float(rules["male_share"]["associate"])
    out: list[tuple[str, str]] = []
    for _ in range(n):
        group = own_group if rng.random() < OWN_GROUP_SHARE else rng.choices([g for g, _ in others], weights=[w for _, w in others])[0]
        out.append((group, "male" if rng.random() < male_share else "female"))
    return out


def build_family(conn: sqlite3.Connection, key: str, spec: dict, rules: dict, day: int) -> dict:
    inst = spec["institution"]
    outfit_id = outfit_actor(conn, inst)
    group = spec["name_group"]
    rng = random.Random(f"{run_seed(conn)}:outfit:{key}:structure")
    seeded, unplaced = seeded_by_rank(conn, outfit_id, rules)
    made_total = int(round(figure(conn, spec["made_men_figure"])))
    per_man = float(figure(conn, spec["associates_figure"]))
    execs = list(rules["executive_ranks"])
    capos_wanted = max(int(figure(conn, "capo_minimum_per_family")), math.ceil(made_total / float(figure(conn, "capo_one_per_men"))))
    capos_wanted = max(capos_wanted, len(seeded.get("capo", [])))
    soldiers_wanted = max(len(seeded.get("soldier", [])), made_total - len(execs) - capos_wanted)
    associates_wanted = int(round(made_total * per_man))

    def settle(rank: str, ids: list[int], wanted: int) -> list[int]:
        """Seeded people first; a seeded surplus beyond an executive seat is left out."""
        keep = ids[:wanted]
        unplaced.extend((i, f"surplus {rank}") for i in ids[wanted:])
        return keep

    # Executives: one seat each, seeded or pulled.
    seat: dict[str, int] = {}
    for rank in execs:
        got = settle(rank, seeded.get(rank, []), 1)
        if not got:
            got = pull_up(conn, 1, stream=f"{key}:{rank}", name_group=group, sex="male", ages=EXEC_AGES, subtype=seat_subtype(rank, inst))
        seat[rank] = got[0]
    boss = seat["boss"]
    for rank in execs:
        add_member(conn, seat[rank], outfit_id, rank, crew_id=None, superior_actor_id=None if rank == "boss" else boss, level=4,
                   day=day, made_day=made_day_for(conn, seat[rank], day, rng))
        if rank != "boss":
            feelings_toward(conn, seat[rank], boss, day, rng)
        _fill_open_seat(conn, inst, rank, seat[rank])

    # Capos, each leading a crew on a ground of the family.
    capos = list(seeded.get("capo", []))
    capos += pull_up(conn, capos_wanted - len(capos), stream=f"{key}:capo", name_group=group, sex="male", ages=CAPO_AGES, subtype=seat_subtype("capo", inst))
    grounds = [int(r[0]) for name in spec["ground"] for r in conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchall()]
    rng.shuffle(grounds)
    crews: list[int] = []
    for i, capo in enumerate(capos):
        surname = str(conn.execute("SELECT name FROM actors WHERE id=?", (capo,)).fetchone()[0]).split()[-1]
        crew = int(conn.execute(
            "INSERT INTO outfit_crews(outfit_actor_id,leader_actor_id,label,ground_location_id,created_day) VALUES (?,?,?,?,?)",
            (outfit_id, capo, f"{surname} crew", grounds[i % len(grounds)] if grounds else None, day)).lastrowid)
        crews.append(crew)
        add_member(conn, capo, outfit_id, "capo", crew_id=crew, superior_actor_id=boss, level=4, day=day,
                   made_day=made_day_for(conn, capo, day, rng))
        feelings_toward(conn, capo, boss, day, rng)

    # Soldiers dealt to the crews round-robin in a seeded order.
    soldiers = list(seeded.get("soldier", []))
    soldiers += pull_up(conn, soldiers_wanted - len(soldiers), stream=f"{key}:soldier", name_group=group, sex="male", ages=SOLDIER_AGES, subtype=seat_subtype("soldier", inst))
    rng.shuffle(soldiers)
    made_men: list[tuple[int, int]] = [(c, cr) for c, cr in zip(capos, crews)]
    for i, s in enumerate(soldiers):
        capo, crew = capos[i % len(capos)], crews[i % len(crews)]
        add_member(conn, s, outfit_id, "soldier", crew_id=crew, superior_actor_id=capo, level=3, day=day,
                   made_day=made_day_for(conn, s, day, rng))
        feelings_toward(conn, s, capo, day, rng)
        made_men.append((s, crew))

    # Associates, spread over the crew's made men (capos and soldiers) round-robin in a seeded order.
    assoc = list(seeded.get("associate", []))
    need = max(0, associates_wanted - len(assoc))
    plan = _associate_groups(conn, rules, group, need, rng)
    for (g, sex) in sorted(set(plan)):
        n = plan.count((g, sex))
        assoc += pull_up(conn, n, stream=f"{key}:associate:{g}:{sex}", name_group=g, sex=sex, ages=ASSOCIATE_AGES,
                         subtype=seat_subtype("associate", inst), criminal_weight=0.5)
    rng.shuffle(assoc)
    patrons = list(made_men)
    rng.shuffle(patrons)
    for i, a in enumerate(assoc):
        sup, crew = patrons[i % len(patrons)]
        add_member(conn, a, outfit_id, "associate", crew_id=crew, superior_actor_id=sup, level=3, day=day,
                   standing=clamp01(rng.gauss(0.3, 0.2)))
        feelings_toward(conn, a, sup, day, rng)

    return {"counts": {"boss": 1, "underboss": 1, "consigliere": 1, "capo": len(capos), "soldier": len(soldiers), "associate": len(assoc)},
            "crews": len(crews), "unplaced": unplaced}


def build_families(conn: sqlite3.Connection, day: int) -> dict:
    rules = outfit_rules(package_for(conn))
    out: dict = {}
    for key, spec in rules.get("outfits", {}).items():
        if spec.get("shape") == "family":
            out[key] = build_family(conn, key, spec, rules, day)
    return out


def build_outfit(conn: sqlite3.Connection, key: str, spec: dict, rules: dict, day: int) -> dict:
    """A non-family outfit (loyalties, banks, club, handful): each rank filled to its figure, seeded people first."""
    inst = spec["institution"]
    shape = spec["shape"]
    outfit_id = outfit_actor(conn, inst)
    group = spec.get("name_group")  # None (the club has no group of its own): the city's group weights
    male_share = float(rules["male_share"][shape])
    rng = random.Random(f"{run_seed(conn)}:outfit:{key}:structure")
    seeded, unplaced = seeded_by_rank(conn, outfit_id, rules, spec)
    ranks = spec["ranks"]
    members: dict[str, list[int]] = {}
    for rank, r in ranks.items():
        wanted = int(r["count"]) if r.get("count") else int(round(figure(conn, r["figure"])))
        got = list(seeded.get(rank, []))[:wanted]
        unplaced.extend((i, f"surplus {rank}") for i in seeded.get(rank, [])[wanted:])
        plan = ["male" if rng.random() < male_share else "female" for _ in range(wanted - len(got))]
        for sex in sorted(set(plan)):
            got += pull_up(conn, plan.count(sex), stream=f"{key}:{rank}:{sex}", name_group=group, sex=sex, ages=GANG_AGES[rank],
                           subtype=seat_subtype(rank, inst), criminal_weight=1.0)
        rng.shuffle(got)
        members[rank] = got
    top = next(iter(ranks))
    for rank, r in ranks.items():
        for i, a in enumerate(members[rank]):
            sup = None
            if shape == "banks" and rank != top and members[top]:
                sup = members[top][i % len(members[top])]
            elif shape == "club" and rank == "officer" and members.get("president"):
                sup = members["president"][0]
            elif shape == "club" and rank in ("member", "prospect") and members.get("officer"):
                sup = members["officer"][i % len(members["officer"])]
            elif shape == "handful" and rank != top and members[top]:
                sup = members[top][0]
            add_member(conn, a, outfit_id, rank, crew_id=None, superior_actor_id=sup, level=int(r["level"]), day=day)
            if sup is not None:
                feelings_toward(conn, a, sup, day, rng)
            elif shape == "loyalties" and rank == "young":  # no chain of command: an older man got him the job
                patrons = members["elder"] + members["middle"]
                if patrons:
                    feelings_toward(conn, a, patrons[i % len(patrons)], day, rng)
            if r.get("count") == 1:
                _fill_open_seat(conn, inst, rank, a)
    return {"counts": {rank: len(m) for rank, m in members.items()}, "unplaced": unplaced}


def build_other_outfits(conn: sqlite3.Connection, day: int) -> dict:
    rules = outfit_rules(package_for(conn))
    return {key: build_outfit(conn, key, spec, rules, day) for key, spec in rules.get("outfits", {}).items()
            if spec.get("shape") != "family"}


def build(conn: sqlite3.Connection) -> dict[str, int]:
    """Everything outfit-shaped at the opening; counts by outfit and rank ("sabatini:capo": 8)."""
    if not system_enabled(conn, "outfits"):
        return {}
    day = _day(conn)
    counts: dict[str, int] = {}
    for key, res in build_families(conn, day).items():
        for rank, n in res["counts"].items():
            counts[f"{key}:{rank}"] = n
        counts[f"{key}:crews"] = res["crews"]
        counts[f"{key}:unplaced_seeded"] = len(res["unplaced"])
    for key, res in build_other_outfits(conn, day).items():
        for rank, n in res["counts"].items():
            counts[f"{key}:{rank}"] = n
        counts[f"{key}:unplaced_seeded"] = len(res["unplaced"])
    from . import outfit_money  # after the people: holdings need the crews and men (outfit_money imports this module)
    for key, gross in outfit_money.build_holdings(conn, day).items():
        counts[f"{key}:gross_yearly"] = int(round(gross))
    return counts
