from __future__ import annotations

"""Canon-shaped underworld for every settlement (gap 4a).

Sizing order: the World Bible's character of the place (engine/underworld_canon.py), then the place's own
features (commercial context, quays), then population. Durable canon outfits hold fronts, not ground; street
gangs are small and territorial; specialists are small non-territorial outfits; networks have presence, not a seat.
Every person comes from the existing population (resolve_background_person, location-scoped); an outfit whose
boss cannot be found is not created. Draws are seeded from world_state.rng_seed and the location id.
"""

import json
import random
import sqlite3
from typing import Any

from .business import commercial_context
from .underworld import create_underworld_organization, ensure_underworld_membership_profile, _upsert_underworld_profile
from .underworld_canon import (CALIBRATION_SOURCE, CANON_NETWORKS, CANON_OUTFITS, FIGHTING, HEARTH_CITIES, KINDS,
                               REGION_DEFAULTS, SETTLEMENT_CHARACTER)
from .underworld_rebuild import (attach_front_use, create_crew, create_front, create_personnel,
                                 create_racket_site, create_zone, ensure_heat_profile, ensure_organization_culture,
                                 protect_business, racket_kind_options, set_zone_adjacency,
                                 set_zone_controller, _ensure_relations_from_borders, _leader_open_core)

MIN_ZONE_POPULATION = 15000
NEW_ZONE_SOURCE = "procedural"

SPECIALIST_RACKETS = {
    "fencing": ("stolen goods",), "smuggling": ("cargo fraud", "stolen goods"), "lending": ("high-risk debt",),
    "gaming": ("illegal gaming", "unlicensed bookmaking"), "prizefighting": ("unlicensed bookmaking", "illegal gaming"),
    "vice": ("brothel protection", "courtesan house leverage"), "brokerage": ("courtesan house leverage", "invoice fraud"),
    "labour_debt": ("high-risk debt", "invoice fraud"), "horse_theft": ("stolen goods", "warehouse theft"),
    "fraud": ("invoice fraud", "seal manipulation", "cargo fraud"),
}
SPECIALIST_NOUNS = {
    "fencing": ("Pawn House", "Trading Company", "Resale Rooms", "Salvage Stores"), "smuggling": ("Carrying Company", "Boatmen", "Night Freight", "Lighter Company"),
    "lending": ("Lending Circle", "Tallymen", "Loan Rooms", "Advance Company"), "gaming": ("Dice Rooms", "Card House", "Table Company", "Betting Rooms"),
    "prizefighting": ("Promotions", "Fight Company", "Ring Company", "Purse Men"), "vice": ("Lamp House", "Rooms", "Silk House", "Evening Company"),
    "brokerage": ("Introductions", "Agency", "Brokers", "Go-Betweens"), "labour_debt": ("Bond Company", "Ledger Men", "Contract Hirers", "Work Bonds"),
    "horse_theft": ("Bridle Men", "Stud Company", "Horse Dealers", "Paddock Men"), "fraud": ("Counting Room", "Seal and Weight", "Weighhouse", "Measure Company"),
}
# Men lead the violent trades more than the books and rooms ([624]-[626] a martial society, yet [1701] women lead gangs, fence and run books).
# Owner ruling 2026-10-17: women are clearly less likely in positions of power, the violent underworld least of all.
P_MALE_VIOLENT = .92
P_MALE_TRADE = .85
P_MALE_VICE = .70
VIOLENT_KINDS = ("prizefighting", "horse_theft")
CREW_WORDS = ("Hands", "Runners", "Lads", "Men", "Watch", "Tallymen", "Boys", "Crew")
# Canon activity text -> the racket kinds the engine models (nearest honest fit).
ACTIVITY_RACKETS = {
    "cargo substitution": "cargo fraud", "stolen goods": "stolen goods", "protection": "protection collections",
    "high-risk debt": "high-risk debt", "illegal gambling": "illegal gaming", "warehouse-record manipulation": "seal manipulation",
    "smuggling through paperwork": "invoice fraud", "forged cargo": "cargo fraud", "fencing": "stolen goods",
    "false manifests": "cargo fraud", "customs evasion": "seal manipulation", "insurance fraud": "invoice fraud",
    "elixir redistribution": "cargo fraud",
}
_GENERIC_ZONES = (
    ("Market Quarter", "market", 84, 86, 86), ("Craft Quarter", "mixed", 82, 64, 75), ("Old Quarter", "residential", 86, 52, 70),
    ("Road Gate", "transit", 66, 75, 68), ("The Yards", "labor", 80, 62, 58), ("Chandlers' Row", "commercial", 70, 80, 70),
    ("Lower Town", "residential", 88, 46, 72), ("Cross Streets", "mixed", 75, 70, 70), ("Tanners' Ward", "labor", 72, 55, 55),
    ("Temple Steps", "mixed", 78, 68, 80), ("Green Market", "market", 80, 82, 84), ("North Gate", "transit", 64, 72, 66),
)
_FIRST = ("Alden", "Bren", "Caro", "Darian", "Elias", "Garran", "Hale", "Iven", "Joren", "Kellan", "Lucan", "Marek", "Nolan", "Orin",
          "Perrin", "Rafe", "Soren", "Tomas", "Varen", "Willem")
_GANG_PREFIX = ("Black", "Red", "Iron", "Grey", "Low", "East", "Ash", "White", "Old", "River", "South", "North", "Salt", "Tin", "Stone")
_GANG_WORDS = ("Hounds", "Crows", "Hooks", "Knives", "Boars", "Lanterns", "Rooks", "Hawks", "Bells", "Foxes", "Hammers", "Jacks", "Gulls", "Wasps")


class _NoPerson(Exception):
    pass


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _rng(conn: sqlite3.Connection, lid: int, salt: int = 7001) -> random.Random:
    return random.Random(int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0]) * 1_000_003 + lid * 97 + salt)


def _population(conn: sqlite3.Connection, lid: int) -> int:
    return int(conn.execute("SELECT COALESCE(SUM(population_estimate),0) FROM background_population_sources WHERE location_id=? AND source_kind='settlement'",
                            (lid,)).fetchone()[0])


def _character(conn: sqlite3.Connection, lid: int) -> tuple[dict, str]:
    """Canon character of this place, else its region's default (parent chain, then political owner), else the Empire's."""
    row = conn.execute("SELECT name,parent_location_id,political_owner FROM locations WHERE id=?", (lid,)).fetchone()
    if row["name"] in SETTLEMENT_CHARACTER:
        return SETTLEMENT_CHARACTER[row["name"]], row["name"]
    names, parent = [], row["parent_location_id"]
    while parent is not None and len(names) < 4:
        p = conn.execute("SELECT name,parent_location_id FROM locations WHERE id=?", (parent,)).fetchone()
        if not p:
            break
        names.append(p["name"]); parent = p["parent_location_id"]
    for n in names + [row["political_owner"] or ""]:
        if n in REGION_DEFAULTS:
            return REGION_DEFAULTS[n], n
    return REGION_DEFAULTS["Underheaven Empire"], "Underheaven Empire"


def _unique_name(conn: sqlite3.Connection, make, tries: int = 80) -> str:
    for i in range(tries):
        name = make(i)
        if not conn.execute("SELECT 1 FROM underworld_organizations WHERE name=?", (name,)).fetchone() and \
           not conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
            return name
    raise RuntimeError("could not generate a unique outfit name")


def _find_person(conn: sqlite3.Connection, lid: int, role: str, *, strict: bool, oid: int, rng: random.Random, sex: str | None) -> int | None:
    from .person_ecology import resolve_background_person
    command = role in ("boss", "crew_leader")
    kw = dict(reason=f"Underworld {role} became consequential", demand_kind="underworld_personnel", location_id=lid,
              min_age=32 if role == "boss" else 24, max_age=68 if role == "boss" else 58, subtype=f"underworld_{role}",
              command_weight=1.0 if command else .55, criminal_weight=1.15, allow_elsewhere=False, demographic_sex=sex)
    aid = None
    if command and _leader_open_core(rng, float(ensure_organization_culture(conn, oid)["open_core_command_bias"]), role):
        aid = (resolve_background_person(conn, occupation_domains=("criminal",), require_open_core=True, **kw)
               or resolve_background_person(conn, occupation_domains=None, require_open_core=True, **kw))
    if aid is None:
        aid = resolve_background_person(conn, occupation_domains=("criminal",), **kw)
    if aid is None and not strict:
        aid = resolve_background_person(conn, occupation_domains=None, **kw)
    return aid


def _person(conn: sqlite3.Connection, lid: int, role: str, *, strict: bool, oid: int, rng: random.Random, sex: str | None = None) -> int:
    """A pre-existing person of this very place (never invented, never from elsewhere); command leans Open-Core as culture says.
    A wanted sex is tried first and given up on when the place has nobody of it."""
    for want in ((sex, None) if sex else (None,)):
        aid = _find_person(conn, lid, role, strict=strict, oid=oid, rng=rng, sex=want)
        if aid is not None:
            # Gangsters keep to their own corners: only a low-weight habit at the settlement as a whole (the default 0.62
            # home habit would make every scene in town a roomful of them).
            from .presence import add_presence_habit
            add_presence_habit(conn, aid, lid, habit_kind="home", weight=0.15, cadence_days=1, basis_kind="actor_home", basis_id=aid,
                               source_kind="derived", confidence=0.9)
            return aid
    raise _NoPerson(role)


def _wanted_sex(conn: sqlite3.Connection, cls: str, p_male: float, rng: random.Random) -> str:
    """Error-diffusion draw: the world's bosses of this class stay within one person of the target share, in a seeded order."""
    row = conn.execute("SELECT value FROM engine_meta WHERE key=?", (f"uw_boss_sex:{cls}",)).fetchone()
    d = json.loads(row[0]) if row else {"n": 0, "male": 0}
    n, male = int(d["n"]), int(d["male"])
    expected = p_male * (n + 1)
    if male <= expected - 1:
        return "male"
    if male >= expected:
        return "female"
    return "male" if rng.random() < expected - male else "female"


def _note_sex(conn: sqlite3.Connection, cls: str, actor_id: int) -> None:
    row = conn.execute("SELECT value FROM engine_meta WHERE key=?", (f"uw_boss_sex:{cls}",)).fetchone()
    d = json.loads(row[0]) if row else {"n": 0, "male": 0}
    sx = conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    d["n"] = int(d["n"]) + 1
    d["male"] = int(d["male"]) + (1 if sx and sx[0] == "male" else 0)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES (?,?)", (f"uw_boss_sex:{cls}", _j(d)))


def _family(conn: sqlite3.Connection, actor_id: int, lid: int, rng: random.Random) -> str:
    """The boss's family name, which is a local one; a one-word name falls back to a surname from the place's own people."""
    last = (conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()[0].split() or [""])[-1]
    if last.isalpha() and len(conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()[0].split()) > 1:
        return last
    rows = conn.execute("SELECT DISTINCT family_name FROM background_person_profiles WHERE current_location_id=? AND family_name<>'' ORDER BY family_name LIMIT 200", (lid,)).fetchall()
    return rng.choice([r[0] for r in rows if str(r[0]).isalpha()] or ["Local"])


def _new_org(conn, key, typ, name, lid, members, meta, *, institution=None, violence=(20, 50), rng) -> int:
    oid = create_underworld_organization(
        conn, key, typ, name=name, primary_location_id=lid, institution_actor_id=institution, member_count_estimate=members,
        command_depth=2 if members >= 42 else 1, violence_capacity=rng.uniform(*violence), cohesion=rng.uniform(48, 78),
        membership_stability=rng.uniform(42, 72), succession_depth=rng.uniform(8, 34), metadata=meta)
    conn.execute("UPDATE underworld_organizations SET status='active' WHERE id=?", (oid,))
    ensure_organization_culture(conn, oid, rng=rng)
    ensure_heat_profile(conn, oid)
    core = max(2, round(members * rng.uniform(.18, .34)))
    ensure_underworld_membership_profile(conn, oid, core_members=core, active_members=max(0, members - core), peripheral_associates=0,
                                         metadata={"source": meta.get("source")})
    return oid


def _rackets(conn, oid, kinds, rng, zone_id=None):
    for rk in kinds:
        try:
            create_racket_site(conn, oid, rk, zone_id=zone_id, gross_income_per_30=rng.uniform(2.5, 7.5), labor_required=rng.uniform(2, 6),
                               metadata={"opening_racket": True})
        except PermissionError:
            pass


def _seed_zones(conn, lid, n, character, ctx, rng, pop) -> list[int]:
    """Named canon districts first, then features (quays, warehouses, caravans), then generic quarters."""
    specs = []
    for d in character.get("districts", []):
        low = d.lower()
        kind = ("warehouse" if any(w in low for w in ("quay", "dock", "warehouse", "harbour")) else "caravan" if "caravan" in low
                else "commercial" if any(w in low for w in ("exchange", "contract")) else "mixed")
        specs.append((d, kind, 78, 84, 72, "world_bible"))
    if ctx["trade_flow"] >= 60 and not any(s[1] == "caravan" for s in specs):
        specs.append(("Caravan Quarter", "caravan", 70, 82, 72, NEW_ZONE_SOURCE))
    specs += [(*g, NEW_ZONE_SOURCE) for g in _GENERIC_ZONES]
    zones: list[int] = []
    seen: set[str] = set()
    for name, kind, popu, comm, vis, src in specs:
        if len(zones) >= n:
            break
        if name in seen:
            continue
        seen.add(name)
        meta = {"source": src, "locator": character["locator"]} if src == "world_bible" else \
               {"source": "procedural", "calibration": CALIBRATION_SOURCE, "population": pop}
        zid = create_zone(conn, lid, name.lower().replace(" ", "_").replace("'", ""), name, zone_kind=kind, population_scale=popu,
                          commercial_intensity=comm, street_visibility=vis, policing_pressure=max(0, min(100, ctx["regulation"] + rng.uniform(-12, 12))),
                          metadata=meta)
        anchor = conn.execute("SELECT id FROM locations WHERE name=? AND parent_location_id=?", (name, lid)).fetchone()
        if anchor:
            conn.execute("UPDATE underworld_zones SET anchor_location_id=? WHERE id=?", (int(anchor[0]), zid))
        zones.append(zid)
    for i, z in enumerate(zones):
        set_zone_adjacency(conn, z, zones[(i + 1) % len(zones)], permeability=rng.uniform(45, 80))
        if i % 4 == 0 and len(zones) > 4:
            set_zone_adjacency(conn, z, zones[(i + 2 + len(zones) // 2) % len(zones)], permeability=rng.uniform(35, 70))
    return zones


def seed_settlement_underworld(conn: sqlite3.Connection, location_id: int) -> dict[str, Any]:
    """Street gangs and specialists for one settlement. Idempotent; settlements without population are skipped."""
    lid = int(location_id)
    key = f"underworld_ecology:{lid}"
    pop = _population(conn, lid)
    if conn.execute("SELECT 1 FROM engine_meta WHERE key=?", (key,)).fetchone() or pop <= 0:
        return {"skipped": True, "zones": 0, "gangs": 0, "specialists": 0, "unstaffed": 0}
    character, basis = _character(conn, lid)
    ctx = commercial_context(conn, lid)
    rng = _rng(conn, lid)
    density = max(.3, min(2.5, character["density"] * (1 + .004 * (ctx["trade_flow"] - 50) + .003 * (ctx["traveler_flow"] - 50)
                                                        + .002 * (ctx["event_activity"] - 50))))
    inputs = {"population": pop, "density": round(density, 3), "street": character["street"], "character": basis}
    n_zones = 0 if pop < MIN_ZONE_POPULATION else max(2, min(12, round(pop / 20000)))
    zones = _seed_zones(conn, lid, n_zones, character, ctx, rng, pop) if n_zones else []
    n_gangs = min(round(density * character["street"] * pop / 60000), len(zones) // 2, 8)  # some ground always stays open
    n_spec = min(round(density * pop / 30000), 25)  # canon: Toll's Reach has dozens of specialist networks; their cost is kept down by a slow decision cadence
    meta = {"source": "procedural", "calibration": CALIBRATION_SOURCE, "inputs": inputs}
    unstaffed = gangs = specs = 0
    gang_ids: list[int] = []
    free = list(zones)
    rng.shuffle(free)
    for i in range(n_gangs):
        conn.execute("SAVEPOINT uw_org")
        try:
            place = conn.execute("SELECT name FROM locations WHERE id=?", (lid,)).fetchone()[0]
            name = _unique_name(conn, lambda k: f"{rng.choice(_GANG_PREFIX)} {rng.choice(_GANG_WORDS)}" + ("" if k < 40 else f" of {place}"))
            members = rng.randint(8, 30)
            oid = _new_org(conn, f"uw:{lid}:gang:{i}", "gang", name, lid, members, {**meta, "role": "street_gang"}, violence=(25, 62), rng=rng)
            boss = create_personnel(conn, oid, role_kind="boss", rng=rng, actor_id=_person(
                conn, lid, "boss", strict=True, oid=oid, rng=rng, sex=_wanted_sex(conn, "violent", P_MALE_VIOLENT, rng)))
            _note_sex(conn, "violent", boss)
            conn.execute("UPDATE underworld_organizations SET founder_actor_id=?,current_leader_actor_id=? WHERE id=?", (boss, boss, oid))
            zid = free.pop(0)
            set_zone_controller(conn, zid, oid, strength=rng.uniform(48, 72), local_support=rng.uniform(32, 66), fear=rng.uniform(42, 76),
                                metadata={"opening_control": True})
            crews = 1 if members < 18 else 2
            for c in range(crews):
                lsex = _wanted_sex(conn, "violent", P_MALE_VIOLENT, rng)
                lead = create_personnel(conn, oid, role_kind="crew_leader", membership_status="member", rng=rng,
                                        actor_id=_person(conn, lid, "crew_leader", strict=False, oid=oid, rng=rng, sex=lsex))
                _note_sex(conn, "violent", lead)
                create_crew(conn, oid, f"{name} {('First', 'Second')[c]} Crew", leader_actor_id=lead, home_zone_id=zid, size_estimate=members / crews, rng=rng)
            _rackets(conn, oid, racket_kind_options(conn, zid, rng, count=rng.randint(1, 3)), rng, zid)
            ents = conn.execute("SELECT id FROM civilian_enterprises WHERE location_id=? AND status IN ('active','strained') AND id NOT IN "
                                "(SELECT enterprise_id FROM underworld_protection_accounts WHERE status='active') ORDER BY id", (lid,)).fetchall()
            rng.shuffle(ents)
            for e in ents[:3]:
                protect_business(conn, oid, int(e[0]), zid, payment_per_30=rng.uniform(.35, 1.8), service_strength=rng.uniform(35, 72),
                                 fear_component=rng.uniform(35, 78), metadata={"opening_account": True})
            gang_ids.append(oid); gangs += 1
            conn.execute("RELEASE SAVEPOINT uw_org")
        except _NoPerson:
            conn.execute("ROLLBACK TO SAVEPOINT uw_org"); conn.execute("RELEASE SAVEPOINT uw_org"); unstaffed += 1
    for i in range(n_spec):
        conn.execute("SAVEPOINT uw_org")
        try:
            kind = rng.choices(KINDS, weights=[character["kinds"].get(k, 0) + .01 for k in KINDS])[0]
            members = rng.randint(3, 15)
            cls, p_male = (("violent", P_MALE_VIOLENT) if kind in VIOLENT_KINDS else ("vice", P_MALE_VICE) if kind == "vice"
                           else ("trade", P_MALE_TRADE))
            oid = _new_org(conn, f"uw:{lid}:spec:{i}", "network" if kind == "brokerage" else "criminal_enterprise", f"pending specialist {lid}.{i}", lid, members,
                           {**meta, "role": "specialist", "specialty": kind}, violence=(8, 32), rng=rng)
            boss = create_personnel(conn, oid, role_kind="boss", rng=rng, actor_id=_person(
                conn, lid, "boss", strict=True, oid=oid, rng=rng, sex=_wanted_sex(conn, cls, p_male, rng)))
            _note_sex(conn, cls, boss)
            conn.execute("UPDATE underworld_organizations SET founder_actor_id=?,current_leader_actor_id=? WHERE id=?", (boss, boss, oid))
            fam = _family(conn, boss, lid, rng)
            place = conn.execute("SELECT name FROM locations WHERE id=?", (lid,)).fetchone()[0]
            nouns = SPECIALIST_NOUNS[kind]
            try:
                name = _unique_name(conn, lambda k: f"{fam} {nouns[k % len(nouns)]}" + ("" if k < len(nouns) else f" of {place}"), tries=len(nouns) * 2)
            except RuntimeError:
                raise _NoPerson("name")
            conn.execute("UPDATE underworld_organizations SET name=? WHERE id=?", (name, oid))
            crew_word = next((w for w in CREW_WORDS if not conn.execute(
                """SELECT 1 FROM underworld_crews c JOIN underworld_organizations o ON o.id=c.organization_id
                   WHERE o.primary_location_id=? AND o.status IN ('active','strained','fragmented') AND c.name=?""", (lid, f"{fam} {w}")).fetchone()), None)
            create_crew(conn, oid, f"{fam} {crew_word or name}", leader_actor_id=boss, purpose_kind=kind, size_estimate=members, rng=rng)
            _rackets(conn, oid, rng.sample(SPECIALIST_RACKETS[kind], k=min(len(SPECIALIST_RACKETS[kind]), rng.randint(1, 2))), rng)
            # A non-territorial trade is not minded every month: its head reviews strategy every quarter, staggered.
            conn.execute("UPDATE simulation_profiles SET cadence_days=90,next_review_day=? WHERE actor_id=?", (_day(conn) + rng.randint(5, 90), boss))
            if rng.random() < .25:
                create_front(conn, oid, f"{name} {rng.choice(('Yard', 'Stores', 'Lodging'))}", "service", zone_id=None,
                             capital=rng.uniform(8, 24), cash=rng.uniform(3, 10), metadata={"opening_front": True})
            specs += 1
            conn.execute("RELEASE SAVEPOINT uw_org")
        except _NoPerson:
            conn.execute("ROLLBACK TO SAVEPOINT uw_org"); conn.execute("RELEASE SAVEPOINT uw_org"); unstaffed += 1
    if gang_ids:
        _ensure_relations_from_borders(conn, lid, rng)
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES (?,?)", (key, _j({"zones": len(zones), "gangs": gangs, "specialists": specs, "unstaffed": unstaffed})))
    return {"skipped": False, "zones": len(zones), "gangs": gangs, "specialists": specs, "unstaffed": unstaffed}


def _seed_canon_outfit(conn: sqlite3.Connection, name: str, spec: dict) -> int | None:
    """Re-adopt a World Bible outfit at its canon place: active actor, fronts, rackets, no ground, no named boss."""
    a = conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?", (name,)).fetchone()
    lid = conn.execute("SELECT id FROM locations WHERE name=?", (spec["location"],)).fetchone()
    if not a or not lid:
        return None
    aid, lid = int(a[0]), int(lid[0])
    rng = _rng(conn, lid, 7101)
    conn.execute("DELETE FROM underworld_rebuild_quarry WHERE actor_id=?", (aid,))
    conn.execute("UPDATE actors SET status='active',home_location_id=?,current_location_id=? WHERE id=?", (lid, lid, aid))
    conn.execute("UPDATE institution_profiles SET primary_location_id=? WHERE actor_id=?", (lid, aid))
    _upsert_underworld_profile(conn, aid, lid, operating_model=spec["organization_type"], legal_fronts=spec["fronts"], criminal_activities=spec["activities"],
                               continuity_depth=80, hidden_exposure=12, corrupt_access=50,
                               metadata={"source": "world_bible", "locator": spec["locator"], "named_leadership": "open", "violence": spec["violence"]})
    conn.execute("UPDATE underworld_institution_profiles SET status='active' WHERE institution_actor_id=?", (aid,))
    members = rng.randint(*spec["members"])
    meta = {"source": "world_bible", "locator": spec["locator"], "named_leadership": "open", "violence": spec["violence"],
            "fronts": spec["fronts"], "activities": spec["activities"]}
    new = not conn.execute("SELECT 1 FROM underworld_organizations WHERE organization_key=?", (f"uw-canon:{name}",)).fetchone()
    oid = create_underworld_organization(conn, f"uw-canon:{name}", spec["organization_type"], name=name, institution_actor_id=aid,
                                         primary_location_id=lid, member_count_estimate=members, command_depth=2,
                                         violence_capacity=rng.uniform(30, 50), cohesion=rng.uniform(55, 78), membership_stability=rng.uniform(55, 75),
                                         succession_depth=rng.uniform(25, 50), corrupt_access=50, metadata=meta)
    conn.execute("UPDATE underworld_organizations SET status='active' WHERE id=?", (oid,))
    if not new:
        return oid
    ensure_organization_culture(conn, oid, rng=rng)
    ensure_heat_profile(conn, oid)
    core = round(members * .3)
    ensure_underworld_membership_profile(conn, oid, core_members=core, active_members=members - core, peripheral_associates=0, metadata={"source": "world_bible"})
    # Fronts: the institution's aggregate commercial arm (made by activate_underworld_substrate), else one made here.
    ent = conn.execute("SELECT id,status FROM civilian_enterprises WHERE institution_actor_id=? ORDER BY (status IN ('active','strained')) DESC,id LIMIT 1", (aid,)).fetchone()
    if ent:
        conn.execute("UPDATE civilian_enterprises SET status='active' WHERE id=? AND status='historical'", (int(ent[0]),))
        attach_front_use(conn, oid, int(ent[0]), zone_id=None, ownership_share=1.0, organization_legal_owner=True,
                         metadata={"source": "world_bible", "locator": spec["locator"]})
    else:
        create_front(conn, oid, f"{name} aggregate fronts", "service", zone_id=None, capital=70, cash=35,
                     metadata={"source": "world_bible", "locator": spec["locator"], "fronts": spec["fronts"]})
    _rackets(conn, oid, list(dict.fromkeys(ACTIVITY_RACKETS[x] for x in spec["activities"] if x in ACTIVITY_RACKETS)), rng)
    return oid


def _seed_networks(conn: sqlite3.Connection, pops: dict[int, int]) -> int:
    """Networks have presence by place and no seat; Mallow stays unplaced (secret cells); the Reckoning is placed by owner ruling (schema 112)."""
    rows = 0
    names = {r[1]: int(r[0]) for r in conn.execute("SELECT id,name FROM locations")}
    for name, net in CANON_NETWORKS.items():
        a = conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name=?", (name,)).fetchone()
        if not a:
            continue
        aid = int(a[0])
        if name != "Mallow Coven":
            conn.execute("UPDATE actors SET home_location_id=NULL,current_location_id=NULL WHERE id=?", (aid,))
            conn.execute("UPDATE institution_profiles SET primary_location_id=NULL WHERE actor_id=?", (aid,))
        want = {names[p]: s for p, s in net["presence"] if p in names}
        rule = net.get("presence_rule", "")
        if rule == "hearth_cities":
            for p in HEARTH_CITIES:
                want.setdefault(names[p], "present")
        elif rule.startswith("min_population:"):
            for lid, pop in pops.items():
                if pop >= int(rule.split(":")[1]):
                    want.setdefault(lid, "present" if pop >= 60000 else "thin")
        for lid, strength in want.items():
            conn.execute("INSERT OR REPLACE INTO underworld_network_presence(institution_actor_id,location_id,strength,source) VALUES (?,?,?,?)",
                         (aid, lid, strength, "world_bible"))
            rows += 1
    return rows


def place_reckoning(conn: sqlite3.Connection) -> dict[str, Any]:
    """Owner ruling (schema 112): the Reckoning is present at Waymeet (strong), Cairnholt, Crownhold; Seth Carrick lives at Waymeet
    and is its elder (a member, not an underworld boss). Idempotent."""
    out: dict[str, Any] = {"presence": 0, "seth": None}
    names = {r[1]: int(r[0]) for r in conn.execute("SELECT id,name FROM locations")}
    inst = conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND name='The Reckoning'").fetchone()
    if not inst:
        return out
    iid = int(inst[0])
    for place, strength in CANON_NETWORKS["The Reckoning"]["presence"]:
        if place in names:
            conn.execute("INSERT OR REPLACE INTO underworld_network_presence(institution_actor_id,location_id,strength,source) VALUES (?,?,?,?)",
                         (iid, names[place], strength, "world_bible"))
            out["presence"] += 1
    seth = conn.execute("SELECT id FROM actors WHERE actor_type='character' AND name='Seth Carrick'").fetchone()
    if seth and "Waymeet" in names:
        sid = int(seth[0])
        conn.execute("UPDATE actors SET home_location_id=?,current_location_id=? WHERE id=?", (names["Waymeet"], names["Waymeet"], sid))
        if not conn.execute("SELECT 1 FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=? AND status='active'", (iid, sid)).fetchone():
            conn.execute("""INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status)
                            VALUES (?,?,'member','elder','active')
                            ON CONFLICT(institution_actor_id,member_actor_id,membership_kind) DO UPDATE SET status='active',role_text='elder'""", (iid, sid))
        out["seth"] = sid
    return out


def _seed_fighting_rackets(conn: sqlite3.Connection) -> int:
    """Criminal rings run a book of their own (independent racket, no territory)."""
    n = 0
    for place, specs in FIGHTING.items():
        for sp in specs:
            if sp["legality"] != "criminal":
                continue
            mk = conn.execute("SELECT id,location_id FROM prizefight_markets WHERE market_key=?", (sp["key"],)).fetchone()
            if not mk or conn.execute("SELECT 1 FROM underworld_racket_sites WHERE json_extract(metadata_json,'$.market_key')=?", (sp["key"],)).fetchone():
                continue
            create_racket_site(conn, None, "illegal gaming", zone_id=None, gross_income_per_30=4, labor_required=3,
                               metadata={"source": "world_bible", "locator": sp["locator"], "market_key": sp["key"], "network": sp.get("network")})
            n += 1
    return n


def seed_all_settlements(conn: sqlite3.Connection) -> dict[str, Any]:
    """Seed the whole world. Canon outfits and networks first (they need no population), then each settlement."""
    pops = {int(r[0]): int(r[1]) for r in conn.execute(
        "SELECT location_id,SUM(population_estimate) FROM background_population_sources WHERE source_kind='settlement' AND location_id IS NOT NULL GROUP BY location_id ORDER BY location_id")}
    canon = [n for n, spec in CANON_OUTFITS.items() if _seed_canon_outfit(conn, n, spec) is not None]
    presence = _seed_networks(conn, pops)
    totals = {"zones": 0, "gangs": 0, "specialists": 0, "unstaffed": 0}
    for lid in pops:
        r = seed_settlement_underworld(conn, lid)
        for k in totals:
            totals[k] += int(r.get(k, 0))
    rings = _seed_fighting_rackets(conn)
    q = lambda sql: int(conn.execute(sql).fetchone()[0])
    return {
        "canon_outfits": len(canon), "network_presence": presence, "fighting_rackets": rings, **totals,
        "v060_underworld_organizations": q("SELECT COUNT(*) FROM underworld_organizations WHERE status IN ('active','strained','fragmented')"),
        "v060_underworld_zones": q("SELECT COUNT(*) FROM underworld_zones WHERE status='active'"),
        "v060_underworld_crews": q("SELECT COUNT(*) FROM underworld_crews WHERE status='active'"),
        "v060_underworld_rackets": q("SELECT COUNT(*) FROM underworld_racket_sites WHERE status='active'"),
        "v060_underworld_protection_accounts": q("SELECT COUNT(*) FROM underworld_protection_accounts WHERE status='active'"),
    }


# ---------------------------------------------------------------- schema 110: rebuild an existing campaign

def _notes_to_report(conn: sqlite3.Connection, names: list[str]) -> int:
    """One error_report per GM note / recap / standing rule that names a dissolved outfit (connector tables may be absent)."""
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "error_reports" not in have or not names:
        return 0
    day = _day(conn)
    n = 0
    for table in ("gm_notes", "campaign_recaps", "standing_rules"):
        if table not in have:
            continue
        for row in conn.execute(f"SELECT id,text FROM {table}").fetchall():
            hit = [x for x in names if x in row["text"]]
            if not hit:
                continue
            cid = f"schema110:{table}:{row['id']}"
            if conn.execute("SELECT 1 FROM error_reports WHERE call_id=?", (cid,)).fetchone():
                continue
            conn.execute("INSERT INTO error_reports(world_day,text,call_id) VALUES (?,?,?)",
                         (day, f"World rebuilt (schema 110): {', '.join(hit)} no longer exists; revise this note ({table} #{row['id']}).", cid))
            n += 1
    return n


def dissolve_procedural_underworld(conn: sqlite3.Connection) -> list[str]:
    """End the Aldergate-only procedural outfits. People stay alive and in place, unaffiliated; the protagonist's and authored outfits stay."""
    me = conn.execute("SELECT player_actor_id FROM player_state WHERE player_actor_id IS NOT NULL LIMIT 1").fetchone() if \
        conn.execute("SELECT 1 FROM sqlite_master WHERE name='player_state'").fetchone() else None
    me = int(me[0]) if me else None
    dissolved: list[tuple[int, str]] = []
    for o in conn.execute("SELECT * FROM underworld_organizations WHERE status IN ('active','strained','fragmented','dormant') ORDER BY id").fetchall():
        meta = json.loads(o["metadata_json"] or "{}")
        if not (meta.get("not_world_bible_canon") and meta.get("v060_clean_rebuild")) or meta.get("authored"):
            continue
        oid = int(o["id"])
        if me is not None and (me in (o["current_leader_actor_id"], o["founder_actor_id"]) or conn.execute(
                "SELECT 1 FROM underworld_personnel WHERE organization_id=? AND actor_id=? AND status='active'", (oid, me)).fetchone()):
            continue
        dissolved.append((oid, o["name"]))
        meta["superseded_by"] = "schema110_canon_underworld"
        conn.execute("UPDATE underworld_organizations SET status='destroyed',metadata_json=? WHERE id=?", (_j(meta), oid))
        conn.execute("UPDATE underworld_crews SET status='destroyed' WHERE organization_id=? AND status IN ('active','depleted')", (oid,))
        conn.execute("UPDATE underworld_zone_claims SET status='withdrawn' WHERE organization_id=? AND status='active'", (oid,))
        conn.execute("UPDATE underworld_racket_sites SET status='abandoned' WHERE organization_id=? AND status IN ('active','suppressed')", (oid,))
        conn.execute("UPDATE underworld_protection_accounts SET status='ended' WHERE protector_organization_id=? AND status='active'", (oid,))
        conn.execute("UPDATE OR REPLACE underworld_business_links SET status='ended' WHERE organization_id=? AND status='active'", (oid,))
        # Everything that still pointed at it: interests (set_racket_status convention), permissions, incidents, relations.
        conn.execute("""UPDATE economic_interests SET status='ended',ended_day=? WHERE status IN ('active','disputed') AND (holder_organization_id=?
                        OR holder_crew_id IN (SELECT id FROM underworld_crews WHERE organization_id=?)
                        OR target_racket_id IN (SELECT id FROM underworld_racket_sites WHERE organization_id=?))""", (_day(conn), oid, oid, oid))
        conn.execute("UPDATE OR REPLACE underworld_operating_permissions SET status='revoked' WHERE status='active' AND (controller_organization_id=? OR guest_organization_id=?)", (oid, oid))
        conn.execute("UPDATE underworld_incidents SET status='expired' WHERE status IN ('open','answered') AND (source_organization_id=? OR target_organization_id=?)", (oid, oid))
        conn.execute("DELETE FROM underworld_relations WHERE organization_a_id=? OR organization_b_id=?", (oid, oid))
        people = [int(r[0]) for r in conn.execute("SELECT actor_id FROM underworld_personnel WHERE organization_id=? AND status='active'", (oid,))]
        conn.execute("UPDATE underworld_personnel SET status='retired' WHERE organization_id=? AND status='active'", (oid,))
        for a in people:  # still in a live outfit elsewhere? then the subtype stays
            if not conn.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=? AND status='active'", (a,)).fetchone():
                if str(conn.execute("SELECT subtype FROM actors WHERE id=?", (a,)).fetchone()[0] or "").startswith("underworld_"):
                    from .person_ecology import make_former_member_ordinary
                    make_former_member_ordinary(conn, a)
    # Their invented wards go too, unless somebody who survived still holds or contests one.
    conn.execute("""UPDATE underworld_zones SET status='abandoned' WHERE status='active' AND metadata_json LIKE '%not_world_bible_canon%'
                    AND id NOT IN (SELECT zone_id FROM underworld_zone_claims WHERE status='active')""")
    return [n for _, n in dissolved]


def rebuild_campaign_underworld(conn: sqlite3.Connection) -> dict[str, Any]:
    """Migration 110: dissolve the procedural city, then seed the canon version everywhere; report the dissolved names."""
    dissolved = dissolve_procedural_underworld(conn)
    has_world = conn.execute("SELECT 1 FROM background_population_sources WHERE source_kind='settlement' LIMIT 1").fetchone()
    seeded: dict[str, Any] = {}
    if has_world:  # an empty database has nothing to seed (tests bootstrap through activation instead)
        from .spectacle import activate_spectacle_substrate
        activate_spectacle_substrate(conn)
        seeded = seed_all_settlements(conn)
    reported = _notes_to_report(conn, dissolved)
    if dissolved or not conn.execute("SELECT 1 FROM engine_meta WHERE key='schema110_report'").fetchone():
        conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('schema110_report',?)",
                     (_j({"dissolved": dissolved, "reported_notes": reported, "seeded": {k: v for k, v in seeded.items() if not k.startswith("v060")}}),))
    return {"dissolved": dissolved, "reported_notes": reported, "seeded": seeded}
