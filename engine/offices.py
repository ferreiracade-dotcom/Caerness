"""Offices at every level: terms, holders, eligibility, the calendar and vacancies (politics P1).

The engine names no office, ward or party: every key, term, cycle, power, eligibility rule and vacancy rule comes from the package's
`politics` data. A package without it has no offices and every function here is a no-op. Eligibility is a veto with a reason, never
a quota. An office is filled by a `office_terms` row (one open term per seat); a single-seat office that has a world fact also mirrors
its holder onto `world_facts.holder_actor_id` so `lookup` and the Fixed rule keep working.
"""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import date, timedelta

from . import orgs
from .design import figure, run_seed
from .world_package import package_for, politics_rules

LEVEL = 3  # a city office-holder is simulated weekly; the mob's level-4 seats stay daily


def rules(conn) -> dict:
    return politics_rules(package_for(conn))


def enabled(conn) -> bool:
    return bool(rules(conn).get("offices"))


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _start(conn) -> date:
    return date.fromisoformat(package_for(conn).calendar["start"])


def date_of(conn, day: int) -> date:
    return _start(conn) + timedelta(days=int(day))


def day_of(conn, y: int, m: int, d: int) -> int:
    return (date(int(y), int(m), int(d)) - _start(conn)).days


def _json(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


# ---- loading -----------------------------------------------------------------------------------------------------

def load_offices(conn) -> int:
    """Make the package's offices (idempotent). Returns the number of offices."""
    for key, o in (rules(conn).get("offices") or {}).items():
        vals = (o.get("jurisdiction", ""), o.get("district"), o["filled_by"], o.get("appointer"), o.get("consent"), o.get("term_years"),
                json.dumps(o.get("cycle") or {}), json.dumps(o.get("powers") or []), json.dumps(o.get("eligibility") or {}),
                json.dumps(o.get("vacancy") or {}), json.dumps(o.get("body") or {}), int(o.get("seats", 1)))
        if conn.execute("SELECT 1 FROM offices WHERE office_key=?", (key,)).fetchone():
            conn.execute("""UPDATE offices SET jurisdiction_kind=?,jurisdiction_ref=?,filled_by=?,appointer_office_key=?,consent_office_key=?,term_years=?,
                            cycle_json=?,powers_json=?,eligibility_json=?,vacancy_json=?,body_json=?,seats=? WHERE office_key=?""", (*vals, key))
        else:
            conn.execute("""INSERT INTO offices(jurisdiction_kind,jurisdiction_ref,filled_by,appointer_office_key,consent_office_key,term_years,cycle_json,
                            powers_json,eligibility_json,vacancy_json,body_json,seats,office_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (*vals, key))
    return int(conn.execute("SELECT COUNT(*) FROM offices").fetchone()[0])


def office(conn, key: str) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM offices WHERE office_key=?", (key,)).fetchone()
    if r is None:
        raise ValueError(f"unknown office {key!r}")
    return r


def spec(conn, key: str) -> dict:
    return (rules(conn).get("offices") or {}).get(key) or {}


# ---- holders -----------------------------------------------------------------------------------------------------

def _open_terms(conn, key: str):
    return conn.execute("""SELECT t.* FROM office_terms t JOIN offices o ON o.id=t.office_id WHERE o.office_key=? AND t.end_day IS NULL
                           ORDER BY t.seat_no,t.id""", (key,)).fetchall()


def holder(conn, office_key: str, seat_no: int = 1) -> int | None:
    for t in _open_terms(conn, office_key):
        if int(t["seat_no"]) == int(seat_no) and orgs.is_living(conn, int(t["actor_id"])):
            return int(t["actor_id"])
    return None


def holders(conn, office_key: str) -> list[int]:
    """Every living holder of every seat (a body's members: see `members`)."""
    return [int(t["actor_id"]) for t in _open_terms(conn, office_key) if orgs.is_living(conn, int(t["actor_id"]))]


def members(conn, body_key: str) -> list[tuple[str, int, int]]:
    """A body's seats as (office_key, seat_no, actor) for each seat that has a holder; a held or dead member is still a member."""
    b = _json(office(conn, body_key)["body_json"], {})
    out: list[tuple[str, int, int]] = []
    keys = b.get("members") or ([b["members_of_office"]] if b.get("members_of_office") else [])
    for k in keys:
        for t in _open_terms(conn, k):
            out.append((k, int(t["seat_no"]), int(t["actor_id"])))
    return out


def offices_of(conn, actor_id: int) -> list[str]:
    return [r[0] for r in conn.execute("""SELECT o.office_key FROM office_terms t JOIN offices o ON o.id=t.office_id
                                          WHERE t.actor_id=? AND t.end_day IS NULL ORDER BY o.office_key""", (int(actor_id),))]


def _mirror(conn, key: str, actor_id: int | None, day: int) -> None:
    from . import facts
    if facts.exists(conn) and int(office(conn, key)["seats"]) == 1:
        conn.execute("UPDATE world_facts SET holder_actor_id=?,filled_day=? WHERE key=?", (actor_id, int(day) if actor_id is not None else None, key))


def seat_holder(conn, office_key: str, actor_id: int, *, how: str, day: int, seat_no: int = 1, source_id: int | None = None) -> int:
    o = office(conn, office_key)
    conn.execute("UPDATE office_terms SET end_day=?,ended_how='succeeded' WHERE office_id=? AND seat_no=? AND end_day IS NULL",
                 (int(day), int(o["id"]), int(seat_no)))
    tid = int(conn.execute("INSERT INTO office_terms(office_id,actor_id,seat_no,start_day,how,source_id) VALUES (?,?,?,?,?,?)",
                           (int(o["id"]), int(actor_id), int(seat_no), int(day), how, source_id)).lastrowid)
    conn.execute("UPDATE office_vacancies SET status='filled',filled_day=?,filled_how=? WHERE office_id=? AND seat_no=? AND status='pending'",
                 (int(day), how, int(o["id"]), int(seat_no)))
    _mirror(conn, office_key, int(actor_id), day)
    return tid


def end_term(conn, term_id: int, how: str, day: int) -> None:
    """End a term (died, resigned, convicted, defeated, removed...) and queue the vacancy under the office's own rule."""
    t = conn.execute("SELECT * FROM office_terms WHERE id=?", (int(term_id),)).fetchone()
    if t is None or t["end_day"] is not None:
        return
    conn.execute("UPDATE office_terms SET end_day=?,ended_how=? WHERE id=?", (int(day), how, int(term_id)))
    o = conn.execute("SELECT * FROM offices WHERE id=?", (t["office_id"],)).fetchone()
    _mirror(conn, o["office_key"], None, day)
    if how == "defeated" or how == "succeeded":
        return  # a new holder is being seated by the same act
    conn.execute("INSERT INTO office_vacancies(office_id,seat_no,since_day,cause,rule_json) VALUES (?,?,?,?,?)",
                 (int(o["id"]), int(t["seat_no"]), int(day), how, o["vacancy_json"]))


def vacancy_rule(conn, office_key: str) -> dict:
    return _json(office(conn, office_key)["vacancy_json"], {})


def pending_vacancies(conn) -> list[sqlite3.Row]:
    return conn.execute("""SELECT v.*,o.office_key FROM office_vacancies v JOIN offices o ON o.id=v.office_id
                           WHERE v.status='pending' ORDER BY v.id""").fetchall()


# ---- eligibility (a veto with its reason) ------------------------------------------------------------------------

def _age(conn, actor_id: int, day: int) -> float | None:
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (int(actor_id),)).fetchone()
    return None if r is None or r[0] is None else (int(day) - int(r[0])) / 365.25


def _inside(conn, loc: int | None, target: int | None) -> bool:
    """`loc` is `target` or lies under it."""
    seen = 0
    while loc is not None and seen < 20:
        if int(loc) == int(target):
            return True
        r = conn.execute("SELECT parent_location_id FROM locations WHERE id=?", (int(loc),)).fetchone()
        loc = r[0] if r else None
        seen += 1
    return False


def _district_location(conn, o: sqlite3.Row, s: dict) -> int | None:
    name = o["jurisdiction_ref"] or s.get("district")
    if not name:
        return None
    r = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
    return int(r[0]) if r else None


def eligible(conn, actor_id: int, office_key: str, day: int) -> tuple[bool, str | None]:
    """(True, None), or (False, the reason word). The same answer for any person, the protagonist included."""
    o = office(conn, office_key)
    e = _json(o["eligibility_json"], {})
    if not orgs.is_living(conn, int(actor_id)):
        return False, "not_living"
    fig = e.get("min_age_figure")
    if fig is not None:
        age = _age(conn, actor_id, day)
        if age is not None and age < float(figure(conn, fig)):
            return False, "min_age"
    res = e.get("residence")
    if res:
        home = conn.execute("SELECT COALESCE(home_location_id,current_location_id) FROM actors WHERE id=?", (int(actor_id),)).fetchone()
        home = int(home[0]) if home and home[0] is not None else None
        if res == "city":
            from .outfit_opening import city_location
            target = city_location(conn)
        else:
            target = _district_location(conn, o, spec(conn, office_key))
        # A home that is the district or lies in it passes; so does a home that is the whole (the city, not yet placed in a ward).
        if target is not None and home is not None and home != target and not _inside(conn, home, target) and not _inside(conn, target, home):
            return False, "residence"
    bar = e.get("conviction_bar") or []
    if bar:
        q = ",".join("?" * len(bar))
        if conn.execute(f"SELECT 1 FROM sentences WHERE actor_id=? AND crime_kind IN ({q})", (int(actor_id), *bar)).fetchone():
            return False, "conviction_bar"
    return True, None


# ---- the calendar ------------------------------------------------------------------------------------------------

def _general_election(year: int) -> date:
    d = date(year, 11, 1)
    while d.weekday() != 0:  # first Monday
        d += timedelta(days=1)
    return d + timedelta(days=1)


def _primary(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != 1:  # first Tuesday
        d += timedelta(days=1)
    return d


def next_dates(conn, office_key: str, after_day: int) -> dict:
    """The office's next primary and election after `after_day` ({} for a real-calendar office, which P2 dates)."""
    s = spec(conn, office_key)
    cyc = s.get("cycle") or {}
    if "every_years" not in cyc:
        return {}
    year = date_of(conn, after_day).year
    while True:
        if year >= int(cyc["first_year"]) and (year - int(cyc["first_year"])) % int(cyc["every_years"]) == 0:
            el = _general_election(year)
            if (el - _start(conn)).days > int(after_day):
                out = {"election_day": (el - _start(conn)).days, "year": year,
                       "term_start_day": (date(year + 1, 1, 1) - _start(conn)).days}
                if s.get("primary_month"):
                    out["primary_day"] = (_primary(year, int(s["primary_month"])) - _start(conn)).days
                return out
        year += 1


# ---- opening -----------------------------------------------------------------------------------------------------

def _institution(conn, key: str) -> int | None:
    r = conn.execute("SELECT entity_id FROM source_identity_map WHERE entity_kind='institution' AND source_key=?", (key,)).fetchone()
    return int(r[0]) if r else None


def build(conn, day: int) -> dict[str, int]:
    """At the opening: make the offices, keep world-fact holders as the opening term, pull up the rest of each elected or appointed
    seat. Counts by what happened; {} for a package with no politics data."""
    if not enabled(conn):
        return {}
    from . import law_opening
    out = {"offices": load_offices(conn), "seeded": 0, "pulled_up": 0}
    plan: list[tuple[str, int, dict]] = []
    for key, s in (rules(conn).get("offices") or {}).items():
        if s["filled_by"] not in ("elected", "appointed") or int(s.get("seats", 1)) < 1 or (s.get("cycle") or {}).get("real"):
            continue
        for seat in range(1, int(s.get("seats", 1)) + 1):
            if _open_terms(conn, key) and any(int(t["seat_no"]) == seat for t in _open_terms(conn, key)):
                continue
            from . import facts
            fact = conn.execute("SELECT holder_actor_id FROM world_facts WHERE key=?", (key,)).fetchone() if facts.exists(conn) else None
            if fact is not None and fact[0] is not None:
                seat_holder(conn, key, int(fact[0]), how="opening", day=day, seat_no=seat)
                out["seeded"] += 1
            else:
                plan.append((key, seat, s))
    if plan:
        rng = random.Random(f"{run_seed(conn)}:offices:sex")
        share = float(figure(conn, "male_share_city_office"))
        slots = [{"group": None, "sex": "male" if rng.random() < share else "female", "domain": (rules(conn).get("domain") or "clerk")} for _ in plan]
        people = law_opening._pull_slots(conn, "politics:offices", slots, law_opening.OFFICIAL_AGES)
        for (key, seat, s), a in zip(plan, people):
            inst = _institution(conn, s.get("institution") or rules(conn).get("institution_default"))
            law_opening._seat(conn, a, inst, str(s.get("role_text") or "office-holder"), "office", day, LEVEL)
            conn.execute("UPDATE actors SET subtype=? WHERE id=?", (str(s.get("role_text") or "office-holder"), a))
            seat_holder(conn, key, a, how="opening", day=day, seat_no=seat)
            out["pulled_up"] += 1
    return out
