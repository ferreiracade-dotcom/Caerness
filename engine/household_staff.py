"""Households: quantified means, a monthly income, and staff paid through gap 4b's household payroll.

Every household has means (`health._family_means` over its members), a wealth and liquidity that follow them, and an income that
keeps an ordinary household solvent (working members earn a little over their keep; wealth yields). Only households whose
means can bear it keep staff: a steward, servants, a nurse, clerks and retainers, drawn from the household's own place (a
missing pool is reported `unstaffed`, nobody is invented). Poor households do their own labour. All staff are paid by
`payroll.run_household_payroll`; there is no wage exemption.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any

from . import payroll

SOURCE = {"source": "household_staff", "not_canon": True}
YIELD = 0.05            # monthly yield on a household's wealth, credited to liquidity as income
EARN_MARGIN = 1.15      # working members earn this much over the household's keep at average means
STAFF_SHARE = 0.30      # of the wealth yield a household will spend on named wages
_CULTURE = {"dunmoor": 1.3, "thornward": 1.2}
_ROYAL = ("royal house", "imperial dynasty")


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _seed(conn) -> int:
    return int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])


def _meta(h) -> dict:
    return json.loads(h["metadata_json"] or "{}")


def _members(conn, hid: int) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        """SELECT m.actor_id FROM household_members m JOIN actors a ON a.id=m.actor_id
           WHERE m.household_id=? AND m.status='active' AND a.status='active' ORDER BY m.actor_id""", (hid,))]


def _ids(conn, hid: int) -> list[int]:
    h = conn.execute("SELECT head_actor_id FROM households WHERE id=?", (hid,)).fetchone()
    ids = _members(conn, hid)
    if h and h[0] is not None and int(h[0]) not in ids:
        ids.append(int(h[0]))
    return ids


def household_means(conn: sqlite3.Connection, hid: int) -> tuple[float, list[str]]:
    """The household's means 0-100 and the reasons (`health._family_means` over active members and the head). Households already
    quantified keep the means they were given."""
    h = conn.execute("SELECT * FROM households WHERE id=?", (hid,)).fetchone()
    meta = _meta(h)
    if meta.get("economic_basis") == "family_means" and "family_means" in meta:
        return float(meta["family_means"]), list(meta.get("family_means_tags", []))
    ids = _ids(conn, hid)
    if not ids:
        return 50.0, []
    from .health import _family_means
    return _family_means(conn, ids)


def _lineage_factor(conn, ids: list[int]) -> float:
    if not ids:
        return 1.0
    marks = ",".join("?" * len(ids))
    kinds = {str(r[0]) for r in conn.execute(
        f"""SELECT ip.institution_kind FROM institution_memberships im JOIN institution_profiles ip ON ip.actor_id=im.institution_actor_id
            WHERE im.member_actor_id IN ({marks}) AND im.status='active'""", ids)}
    if kinds & set(_ROYAL):
        return 4.0
    if "great house" in kinds:
        return 1.5
    return 1.0


def _is_player_house(conn, h) -> bool:
    p = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    return bool(p and h["head_actor_id"] is not None and int(h["head_actor_id"]) == int(p[0]))


def quantify_household(conn: sqlite3.Connection, hid: int) -> bool:
    """Give a structurally-known household a wealth and liquidity from its means. Idempotent; households that already carry
    quantified finances, and the protagonist's own, are left alone."""
    h = conn.execute("SELECT * FROM households WHERE id=?", (hid,)).fetchone()
    if h is None or h["status"] not in ("active", "declining"):
        return False
    meta = _meta(h)
    if meta.get("economic_basis") == "family_means":
        return False
    structural = meta.get("economic_resolution") == "STRUCTURAL_ONLY" or meta.get("economic_state") == "NOT_SEPARATELY_QUANTIFIED"
    if not structural or float(h["wealth"]) > 0 or float(h["liquidity"]) > 0 or _is_player_house(conn, h):
        return False
    means, tags = household_means(conn, hid)
    wealth = round(4.0 * (means / 50.0) ** 3 * _lineage_factor(conn, _ids(conn, hid)), 1)
    liquidity = max(1.0, round(0.4 * wealth, 1))
    meta.update({"economic_basis": "family_means", "economic_resolution": "QUANTIFIED", "economic_state": "QUANTIFIED_FROM_MEANS",
                 "family_means": round(means, 1), "family_means_tags": tags, **{"quantified_by": "household_staff"}})
    conn.execute("UPDATE households SET wealth=?,liquidity=?,metadata_json=? WHERE id=?",
                 (wealth, liquidity, json.dumps(meta, sort_keys=True), hid))
    return True


def _upkeep(conn, h) -> float:
    meta = _meta(h)
    members = int(conn.execute(
        """SELECT COUNT(*) FROM household_members m WHERE m.household_id=? AND m.status='active'
           AND NOT EXISTS (SELECT 1 FROM household_service_terms t WHERE t.household_id=m.household_id AND t.actor_id=m.actor_id AND t.status='active')""",
        (h["id"],)).fetchone()[0])
    counted = sum(int(v) for v in (meta.get("staff_counted") or {}).values())
    return members * 0.08 + float(h["staff_capacity"]) * 0.004 + float(h["hospitality"]) * 0.003 + counted * payroll.HOUSEHOLD_WAGE["servant"]


def _workers(conn, hid: int) -> int:
    day = _day(conn)
    return int(conn.execute(
        """SELECT COUNT(*) FROM household_members m JOIN actor_life_profiles lp ON lp.actor_id=m.actor_id JOIN actors a ON a.id=m.actor_id
           WHERE m.household_id=? AND m.status='active' AND a.status='active' AND lp.life_status='living' AND m.role IN ('head','partner','member')
           AND (?-lp.birth_day)/365 BETWEEN 16 AND 64
           AND NOT EXISTS (SELECT 1 FROM household_service_terms t WHERE t.household_id=m.household_id AND t.actor_id=m.actor_id AND t.status='active')""",
        (hid, day)).fetchone()[0])


def household_income(conn: sqlite3.Connection, hid: int) -> float:
    """Monthly income of a household quantified from its means: its working members earn a margin over its keep (more where
    means are high), and its wealth yields. Business owner draws arrive separately through the ledger."""
    h = conn.execute("SELECT * FROM households WHERE id=?", (hid,)).fetchone()
    if h is None or _meta(h).get("economic_basis") != "family_means":
        return 0.0
    means = float(_meta(h).get("family_means", 50.0))
    k = EARN_MARGIN + (means - 50.0) / 100.0
    earn = _upkeep(conn, h) * k if _workers(conn, hid) > 0 else 0.0
    return round(earn + YIELD * float(h["wealth"]), 4)


# ---------------------------------------------------------------- staff

def staff_plan(conn: sqlite3.Connection, hid: int, *, key: str) -> dict[str, Any]:
    """What staff the household's means bear: {"total", "named": [role...], "counted": {role: n}}. Never more than it can pay."""
    h = conn.execute("SELECT * FROM households WHERE id=?", (hid,)).fetchone()
    meta = _meta(h)
    plan = {"total": 0, "named": [], "counted": {}}
    if meta.get("economic_basis") not in ("family_means", "protagonist") or "dependent_house_family" in meta.get("family_means_tags", []):
        return plan  # unquantified, or a house family that is itself the retainer of its house
    from .manners_canon import culture_key
    culture = culture_key(conn, h["location_id"])
    rng = random.Random(f"{key}:plan:{hid}")
    base = payroll.HOUSEHOLD_WAGE["servant"]
    total = STAFF_SHARE * YIELD * float(h["wealth"]) / base * _CULTURE.get(culture, 1.0) * rng.uniform(0.8, 1.2)
    total = int(math.floor(total + (1 if culture == "windmere" and total >= 1 else 0)))
    if total < 1:
        return plan
    kids = int(conn.execute(
        """SELECT COUNT(*) FROM household_members m JOIN actor_life_profiles lp ON lp.actor_id=m.actor_id WHERE m.household_id=? AND m.status='active'
           AND ?-lp.birth_day < 8*365""", (hid, _day(conn))).fetchone()[0])
    roles: list[str] = []
    if total >= 3:
        roles.append("steward")
    if culture == "windmere" and total >= 2 or total >= 6:
        roles.append("clerk")
    if kids and total >= 2:
        roles.append("servant:nurse")
    extra = "guard" if culture == "thornward" else "retainer" if culture in ("dunmoor", "hearth", "churn") else "servant"
    while len(roles) < total:
        roles.append(extra if (len(roles) % 3 == 2 and total >= 4) else "servant")
    named = min(total, 3 + total // 6)
    if meta.get("economic_basis") == "protagonist":
        # The protagonist pays from his own money: never a plan he could not carry for a year (no extra money is ever granted).
        from . import ledger
        funds = float(h["liquidity"]) + (ledger.balance(conn, ("person", int(h["head_actor_id"]))) if h["head_actor_id"] is not None else 0.0)
        while roles and sum(payroll.HOUSEHOLD_WAGE.get(r.split(":")[0], .08) for r in roles) * 12 > funds:
            roles.pop()
        total, named = len(roles), min(len(roles), named)
        if total < 1:
            return plan
    plan["total"] = total
    plan["named"] = roles[:named]
    for r in roles[named:]:
        plan["counted"][r.split(":")[0]] = plan["counted"].get(r.split(":")[0], 0) + 1
    return plan


_POOL = {"steward": (("clerk", "merchant"), "male", .65), "clerk": (("clerk",), None, .5), "servant:nurse": (("hospitality", "labor"), "female", .9),
         "servant": (("hospitality", "labor"), None, .5), "guard": (("soldier", "labor"), "male", .95), "retainer": (("soldier", "labor", "hospitality"), "male", .7)}


def ensure_household_staff(conn: sqlite3.Connection, hid: int, *, key: str) -> dict[str, Any]:
    """Staff the household as its plan says, from its own place's people. Idempotent: what is already on a service term counts."""
    from .household_life import add_service_term
    from .opening_family import _seed_pair
    from .person_ecology import resolve_background_person
    h = conn.execute("SELECT * FROM households WHERE id=?", (hid,)).fetchone()
    out = {"hired": 0, "unstaffed": 0, "counted": 0, "skipped": None}
    if h["location_id"] is None:
        out["skipped"] = "no place"
        return out
    meta = _meta(h)
    if meta.get("staffed_by") == "household_staff":
        return out
    plan = staff_plan(conn, hid, key=key)
    day = _day(conn)
    rng = random.Random(f"{key}:staff:{hid}")
    from .veto import settlement_of
    place = settlement_of(conn, int(h["location_id"])) or int(h["location_id"])
    for i, role in enumerate(plan["named"]):
        domains, sex, p_sex = _POOL[role]
        want = sex if rng.random() < p_sex else {"male": "female", "female": "male", None: None}[sex]
        lo, hi = (35, 65) if role == "steward" else (18, 55)
        aid = resolve_background_person(conn, reason="household staff", demand_kind="household_staff", location_id=place,
                                        occupation_domains=domains, min_age=lo, max_age=hi, demographic_sex=want, allow_elsewhere=False,
                                        pick_seed=f"{key}:hh{hid}:{i}", subtype="resolved_household_staff")
        if aid is None:
            out["unstaffed"] += 1
            continue
        from .continuity import set_resolution
        from .resolution_controller import _sync_sim_tier
        set_resolution(conn, "actor", aid, "STRUCTURAL", day=day, reason="household staff", source_kind="engine",
                       review_cadence_days=365, next_review_day=day + 365, metadata=dict(SOURCE))
        _sync_sim_tier(conn, aid, "STRUCTURAL", day)
        term_role = role.split(":")[0]
        add_service_term(conn, hid, aid, term_role, review_in_days=90 + rng.randrange(275), loyalty=round(rng.uniform(45, 70), 1),
                         satisfaction=round(rng.uniform(45, 65), 1), renewal_bias=round(rng.uniform(40, 70), 1))
        if h["head_actor_id"] is not None:
            _seed_pair(conn, int(h["head_actor_id"]), aid, "service", key=f"{key}:svc:{hid}:{aid}", started_day=day - rng.randint(60, 1500),
                       a_role="master", b_role="servant")
        out["hired"] += 1
    counted = dict(plan["counted"])
    out["counted"] = sum(counted.values())
    meta.update({"staffed_by": "household_staff", "staff_counted": counted, "staff_plan_total": plan["total"], "staff_unstaffed": out["unstaffed"]})
    conn.execute("UPDATE households SET metadata_json=?,staff_capacity=? WHERE id=?",
                 (json.dumps(meta, sort_keys=True), float(plan["total"]) if plan["total"] else float(h["staff_capacity"]), hid))
    return out


def seed_all(conn: sqlite3.Connection) -> dict[str, Any]:
    """Quantify every structurally-known household, then staff those whose means bear it. Deterministic from the world seed."""
    key = f"hh115:{_seed(conn)}"
    rep = {"quantified": 0, "staffed_households": 0, "staff_hired": 0, "counted_staff": 0, "unstaffed": 0, "location_less": 0}
    for (hid,) in conn.execute("SELECT id FROM households WHERE status IN ('active','declining') ORDER BY id").fetchall():
        if quantify_household(conn, hid):
            rep["quantified"] += 1
        h = conn.execute("SELECT location_id FROM households WHERE id=?", (hid,)).fetchone()
        if h[0] is None:
            rep["location_less"] += 1
            continue
        s = ensure_household_staff(conn, hid, key=key)
        if s["hired"] or s["counted"]:
            rep["staffed_households"] += 1
        rep["staff_hired"] += s["hired"]
        rep["counted_staff"] += s["counted"]
        rep["unstaffed"] += s["unstaffed"]
    return rep
