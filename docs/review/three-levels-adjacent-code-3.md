# Three levels, nearby code: batch 3 of 5: Outfits and the underworld

Same review as the first file (design revision 3.1 and its contract are already with you; not repeated).
This batch settles suspicion 6 and the people side of the city sim. For each module, give the same verdict as before (keep as is, fold into the build, rework, or cut),
with the reason and function names, and when to do it.

Modules in this batch: engine/org_lifecycle.py, engine/org_membership.py, engine/org_succession.py, engine/org_coup.py, engine/org_happenings.py, engine/org_money.py.


## engine/org_lifecycle.py

```python
"""Organisation lifecycle (sphere-free): who takes a vacant unit, and what is noted for the GM's history.

This file holds `fill_unit_leader`, `mark_for_history` and the weekly lifecycle process (deaths, held men, leaving the
life, levels, the vacancy hook). Roles and labels come from the package's orgs.json (`orgs.kind_rules`).
"""
from __future__ import annotations

import json
import sqlite3

from . import orgs
from .world_package import org_rules, package_for

_DAYS_PER_YEAR = 365.0
RISE_REASON = "rose to lead a unit"  # the history note `fill_unit_leader` leaves; readers use its day as the day the seat was filled


def mark_for_history(conn: sqlite3.Connection, actor_id: int, reason: str, day: int | None = None) -> None:
    """Flag every seat he holds as owing the GM a history and record why, as an agenda row of kind `history` (an item
    that needs no action from the man himself)."""
    d = orgs._today(conn) if day is None else int(day)
    conn.execute("UPDATE org_seats SET history_due=1 WHERE actor_id=?", (int(actor_id),))
    conn.execute(
        """INSERT INTO org_agenda(actor_id,kind,due_day,subject_kind,subject_id,created_day,metadata_json) VALUES (?,?,?,?,?,?,?)""",
        (int(actor_id), "history", d, "actor", int(actor_id), d, json.dumps({"reason": str(reason)}, sort_keys=True)))


def _head_loyalty(conn: sqlite3.Connection, actor_id: int, head: int | None) -> float:
    """His loyalty to the head, 0..1: the relationship's loyalty where there is one, else his own drive."""
    if head is not None:
        r = conn.execute("SELECT loyalty FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(actor_id), int(head))).fetchone()
        if r is not None:
            return max(0.0, min(1.0, float(r[0]) / 100.0))
    d = conn.execute("SELECT loyalty FROM actor_drives WHERE actor_id=?", (int(actor_id),)).fetchone()
    return float(d[0]) if d is not None else 0.5


def unit_pool(conn: sqlite3.Connection, unit_id: int, day: int, exclude: int | None = None) -> list:
    """The men of a unit who could lead it: living, in a seat that is not the unit leader's; the inducted ones when there are any."""
    unit = conn.execute("SELECT * FROM org_units WHERE id=?", (int(unit_id),)).fetchone()
    if unit is None:
        return []
    org = int(unit["org_actor_id"])
    role = orgs.kind_rules(conn, org).get("unit_leader")
    head_role = orgs.kind_rules(conn, org).get("head")  # a man who rose to head from this unit keeps its unit id: he is no one's choice to lead it again
    old = unit["leader_actor_id"]
    members = [r for r in orgs.members(conn, org) if r["unit_id"] == int(unit_id) and r["role_key"] != role and r["role_key"] != head_role
               and (old is None or int(r["actor_id"]) != int(old)) and (exclude is None or int(r["actor_id"]) != int(exclude)) and orgs.is_living(conn, int(r["actor_id"]))]
    return [r for r in members if r["inducted_day"] is not None] or members


def fill_unit_leader(conn: sqlite3.Connection, unit_id: int, day: int, force: bool = False, chosen: int | None = None,
                     superior: int | None = None) -> int | None:
    """Give a unit whose leader is gone a new one. `chosen` is the man the deciding head named (when he is of the unit); else the
    unit member with the best standing, years inducted and loyalty to the head (inducted members first; any member when no
    one is inducted) takes the unit-leader role, under the old leader's superior (or `superior`); the men who answered to the old leader now answer to him; the lines the old leader held and the
    unit's lines stay with the unit under him. Returns the new leader's actor id; None when the unit's leader is alive,
    the kind has no unit leaders, or there is no one to take the place."""
    unit = conn.execute("SELECT * FROM org_units WHERE id=?", (int(unit_id),)).fetchone()
    if unit is None:
        return None
    org = int(unit["org_actor_id"])
    role = orgs.kind_rules(conn, org).get("unit_leader")
    old = unit["leader_actor_id"]
    if not role:
        return None
    if old is not None and not force and orgs.is_living(conn, int(old)):
        seat = orgs.seat_of(conn, int(old), org)
        if seat is not None and seat["status"] == "active" and seat["role_key"] == role:
            return None
    old_seat = orgs.seat_of(conn, int(old), org) if old is not None else None
    head = orgs.head_of(conn, org)
    pool = unit_pool(conn, unit_id, day)
    if not pool:
        return None

    def years(r) -> float:
        return 0.0 if r["inducted_day"] is None else max(0.0, (int(day) - int(r["inducted_day"])) / _DAYS_PER_YEAR)

    top = max((years(r) for r in pool), default=0.0) or 1.0
    best = max(pool, key=lambda r: (float(r["standing"]) + years(r) / top + _head_loyalty(conn, int(r["actor_id"]), head), -int(r["actor_id"])))
    named = [r for r in pool if chosen is not None and int(r["actor_id"]) == int(chosen)]
    best = named[0] if named else best
    new = int(best["actor_id"])
    if superior is None:
        superior = old_seat["superior_actor_id"] if old_seat is not None and old_seat["role_key"] == role else head
    level = int(old_seat["level"]) if old_seat is not None and old_seat["role_key"] == role else (role_level(conn, org, role) or int(best["level"]))
    conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=? WHERE actor_id=? AND org_actor_id=?", (role, superior, new, org))
    if old is not None:
        conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND superior_actor_id=? AND actor_id<>?",
                     (new, org, int(old), new))
        conn.execute("UPDATE org_lines SET holder_actor_id=? WHERE holder_actor_id=? AND unit_id=? AND status='active'", (new, int(old), int(unit_id)))
    conn.execute("UPDATE org_units SET leader_actor_id=? WHERE id=?", (new, int(unit_id)))
    label = (orgs.kind_rules(conn, org).get("labels") or {}).get(role, role)
    name = conn.execute("SELECT name FROM actors WHERE id=?", (org,)).fetchone()[0]
    conn.execute("UPDATE institution_memberships SET role_text=? WHERE institution_actor_id=? AND member_actor_id=? AND membership_kind='member'",
                 (f"{label} in the {name}", org, new))
    orgs.set_level(conn, new, level, int(day), org)
    orgs.imposed(conn, new)  # he and the men who now answer to him are looked at again tomorrow
    for (sub,) in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND superior_actor_id=? AND status='active' AND actor_id<>?",
                               (org, new, new)).fetchall():
        orgs.imposed(conn, int(sub))
    mark_for_history(conn, new, RISE_REASON, int(day))
    return new


# ---- the weekly lifecycle: who is gone, who is held, who leaves the life, and what each leaves vacant ----
# Data (orgs.json `kinds[k].lifecycle`, each value a number or a design-figure key): held_level_days (a daily man held this
# long drops to weekly), held_seat_days (held this long, the seat is given up), left_cadence_days (a man who has left the
# life is reviewed this rarely), returns_as (the role a released man takes when his own post was filled meanwhile),
# role_levels (role -> level, where the kind's opening data does not say), succession (role -> roles whose best man takes
# the post when it falls vacant, tried in order), step_back_roles / step_back_agendas (a man in one of those roles with an
# open agenda of one of those kinds is reviewed weekly).
WEEK = 7
DUE_OFFSET = 3  # a day of the week of its own, so the lifecycle does not run on the day the dependants' weeks do
_VACANCY: list = []  # (org kind or None, fn(conn, org_actor_id, seat_row, day, why))
_UNIT_VACANCY: list = []
_HEAD_VACANCY: list = []
_RETURNS: list = []
_POST_VACANCY: list = []
_WEEKLY: list = []  # (None, fn(conn, day) -> dict), run after the lifecycle's own steps


def _register(registry: list, entry, fn) -> None:
    for i, e in enumerate(registry):
        if e[0] == entry and (e[1] is fn or (getattr(e[1], "__module__", None), getattr(e[1], "__qualname__", None)) ==
                              (getattr(fn, "__module__", None), getattr(fn, "__qualname__", None))):
            registry[i] = (entry, fn)
            return
    registry.append((entry, fn))


def on_vacancy(org_kind: str | None, fn) -> None:
    """Register fn(conn, org_actor_id, seat_row, day, why) to run once for each seat that falls vacant (why: dead, out or
    held) in organisations of `org_kind` (None: every kind). The hook decides from the package's data whether it applies."""
    _register(_VACANCY, org_kind, fn)


def on_unit_vacancy(fn) -> None:
    """Register fn(conn, org_actor_id, seat_row, day, why) -> bool for a vacated unit-leader seat. True: it took the matter up (the
    head is asked to name the leader) and the best-man rule does not run."""
    _register(_UNIT_VACANCY, None, fn)


def on_head_vacancy(fn) -> None:
    """Register fn(conn, org_actor_id, seat_row, day, why) -> bool for a vacated head seat. True: it took the matter up (a
    contest) and the data's succession ladder does not run."""
    _register(_HEAD_VACANCY, None, fn)


def on_post_vacancy(fn) -> None:
    """Register fn(conn, org_actor_id, role, day) -> bool for a vacant post the kind's data gives a succession: True when it took
    the matter up (the head chooses) and the formula does not run."""
    _register(_POST_VACANCY, None, fn)


def on_return(fn) -> None:
    """Register fn(conn, org_actor_id, actor_id, day) -> bool for a released head: True when he takes his seat back."""
    _register(_RETURNS, None, fn)


def on_week(fn) -> None:
    """Register fn(conn, day) -> dict to run in the weekly lifecycle process after its own steps."""
    _register(_WEEKLY, None, fn)


def _lc(conn: sqlite3.Connection, org: int) -> dict:
    return orgs.kind_rules(conn, int(org)).get("lifecycle") or {}


def _num(conn: sqlite3.Connection, lc: dict, key: str, default: float | None = None) -> float | None:
    from .org_motives import _value
    return default if lc.get(key) is None else _value(conn, lc[key], default if default is not None else 0.0)


def role_level(conn: sqlite3.Connection, org: int, role: str) -> int | None:
    """The level a role is played at: the kind's opening data, else its lifecycle `role_levels`; None when neither says."""
    spec = ((orgs.kind_rules(conn, int(org)).get("opening") or {}).get("roles") or {}).get(role)
    if spec and spec.get("level") is not None:
        return int(spec["level"])
    lv = (_lc(conn, org).get("role_levels") or {}).get(role)
    return None if lv is None else int(lv)


def _label(conn: sqlite3.Connection, org: int, role: str) -> str:
    return (orgs.kind_rules(conn, int(org)).get("labels") or {}).get(role, role)


def membership_text(conn: sqlite3.Connection, org: int, actor: int, role: str) -> None:
    """The membership row's text for a man's (new) role: '<label> in the <organisation>'."""
    name = conn.execute("SELECT name FROM actors WHERE id=?", (int(org),)).fetchone()[0]
    conn.execute("UPDATE institution_memberships SET role_text=? WHERE institution_actor_id=? AND member_actor_id=? AND membership_kind='member'",
                 (f"{_label(conn, org, role)} in the {name}", int(org), int(actor)))


def leave_life(conn: sqlite3.Connection, actor_id: int, org_actor_id: int, day: int) -> None:
    """A man leaves the organisation: his seat becomes `out`, with the day. He keeps his actor row, his seat row and his
    records; when he holds no other active seat his simulation profile becomes DORMANT (cadence from the kind's
    `left_cadence_days`, no quiet routine). His lines pass to whoever stands in for him; his vacancy is handled by the
    next weekly pass."""
    conn.execute("UPDATE org_seats SET status='out', left_day=COALESCE(left_day,?) WHERE actor_id=? AND org_actor_id=? AND status IN ('active','held','retired')",
                 (int(day), int(actor_id), int(org_actor_id)))
    _dormant(conn, int(actor_id), int(org_actor_id), int(day))


def _dormant(conn: sqlite3.Connection, actor: int, org: int, day: int) -> bool:
    cadence = _num(conn, _lc(conn, org), "left_cadence_days")
    if cadence is None or conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND status='active' LIMIT 1", (actor,)).fetchone():
        return False
    cadence = int(cadence)
    conn.execute(
        """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,last_review_day,next_review_day,quiet_routine)
           VALUES (?,?,?,?,?,0)
           ON CONFLICT(actor_id) DO UPDATE SET tier='DORMANT',cadence_days=excluded.cadence_days,last_review_day=excluded.last_review_day,
             next_review_day=excluded.next_review_day,quiet_routine=0,forced_tier=NULL,forced_until_day=NULL""",
        (actor, "DORMANT", cadence, day, orgs.next_review_day(conn, actor, day, cadence)))
    return True


def _mark_dead(conn: sqlite3.Connection, day: int) -> int:
    rows = conn.execute(
        """SELECT s.id,s.actor_id,s.org_actor_id,s.role_key FROM org_seats s JOIN actors a ON a.id=s.actor_id LEFT JOIN actor_life_profiles lp ON lp.actor_id=s.actor_id
           WHERE s.status IN ('active','held') AND (lower(COALESCE(a.status,'active')) IN ('dead','deceased','historical')
                                                    OR COALESCE(lp.life_status,'living')<>'living')""").fetchall()
    from . import org_tension
    for sid, actor, org, role in rows:
        conn.execute("UPDATE org_seats SET status='dead', left_day=COALESCE(left_day,?) WHERE id=?", (int(day), int(sid)))
        org_tension.on_death(conn, int(actor), int(org), role, int(day))  # the other heads weigh the wake
    return len(rows)


def _live_superior(conn: sqlite3.Connection, org: int, gone_seat) -> int | None:
    """Who the men under a vacated seat answer to now: his own superior when he is active, else the head."""
    sup = gone_seat["superior_actor_id"]
    if sup is not None:
        s = orgs.seat_of(conn, int(sup), org)
        if s is not None and s["status"] == "active" and orgs.is_living(conn, int(sup)):
            return int(sup)
    head = orgs.head_of(conn, org)
    return None if head is None or head == int(gone_seat["actor_id"]) else head


def _best(conn: sqlite3.Connection, rows, head: int | None, day: int):
    def years(r) -> float:
        return 0.0 if r["inducted_day"] is None else max(0.0, (int(day) - int(r["inducted_day"])) / _DAYS_PER_YEAR)
    top = max((years(r) for r in rows), default=0.0) or 1.0
    return max(rows, key=lambda r: (float(r["standing"]) + years(r) / top + _head_loyalty(conn, int(r["actor_id"]), head), -int(r["actor_id"])))


def fill_post(conn: sqlite3.Connection, org: int, role: str, day: int, depth: int = 0) -> int | None:
    """A post the kind's `succession` names fell vacant: a registered hook may put the choice on the head's list (returns None
    for now); otherwise the data's formula (`_promote`) fills it at once."""
    if conn.execute("SELECT 1 FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active' LIMIT 1", (int(org), role)).fetchone():
        return None
    if any(fn(conn, int(org), role, int(day)) for _k, fn in list(_POST_VACANCY)):
        return None
    return _promote(conn, org, role, day, depth)


def _promote(conn: sqlite3.Connection, org: int, role: str, day: int, depth: int = 0, chosen: int | None = None) -> int | None:
    """Fill a vacant post from the roles the kind's `succession` names for it: the man the head chose (`chosen`, one of those
    roles) or else the best man of the first role that has one takes it (his own unit first gets a new leader), and the post he
    leaves is filled the same way."""
    prefs = (_lc(conn, org).get("succession") or {}).get(role)
    if not prefs or depth > 4:
        return None
    if conn.execute("SELECT 1 FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active' LIMIT 1", (int(org), role)).fetchone():
        return None
    head = orgs.head_of(conn, org)
    pick = None
    for pref in prefs:
        pool = [r for r in orgs.members(conn, org, pref) if orgs.is_living(conn, int(r["actor_id"]))]
        named = [r for r in pool if chosen is not None and int(r["actor_id"]) == int(chosen)]
        if named:
            pick = named[0]
            break
    for pref in prefs if pick is None else ():
        pool = [r for r in orgs.members(conn, org, pref) if orgs.is_living(conn, int(r["actor_id"]))]
        if pool:
            pick = _best(conn, pool, head, day)
            break
    if pick is None:
        return None
    new, left_role = int(pick["actor_id"]), pick["role_key"]
    rules = orgs.kind_rules(conn, org)
    if left_role == rules.get("unit_leader") and pick["unit_id"]:
        if not any(fn(conn, org, pick, int(day), "promoted") for _k, fn in list(_UNIT_VACANCY)):  # the head names the new leader, else the formula does
            fill_unit_leader(conn, int(pick["unit_id"]), int(day), force=True)
            conn.execute("UPDATE org_units SET leader_actor_id=NULL WHERE id=? AND leader_actor_id=?", (int(pick["unit_id"]), new))
    is_head = role == rules.get("head")
    conn.execute("UPDATE org_seats SET role_key=?, unit_id=NULL, superior_actor_id=? WHERE id=?",
                 (role, None if is_head or head is None or head == new else head, int(pick["id"])))
    membership_text(conn, org, new, role)
    lv = role_level(conn, org, role)
    if lv is not None:
        orgs.set_level(conn, new, lv, int(day), org)
    orgs.imposed(conn, new)
    mark_for_history(conn, new, f"rose to {_label(conn, org, role)}", int(day))
    fill_post(conn, org, left_role, int(day), depth + 1)
    return new


def _vacate(conn: sqlite3.Connection, seat, why: str, day: int) -> None:
    """One seat has fallen vacant: a unit leader's unit gets a new leader, a post with a succession is filled, the men who
    answered to him answer to his successor (else his superior), then the registered hooks run."""
    org, gone = int(seat["org_actor_id"]), int(seat["actor_id"])
    rules = orgs.kind_rules(conn, org)
    successor = None
    if seat["role_key"] == rules.get("unit_leader") and seat["unit_id"]:
        if not any(fn(conn, org, seat, int(day), why) for _k, fn in list(_UNIT_VACANCY)):
            successor = fill_unit_leader(conn, int(seat["unit_id"]), int(day))
        mk = conn.execute("SELECT id FROM org_agenda WHERE kind='acting' AND status='open' AND actor_id=? AND subject_id=?", (gone, org)).fetchone()
        if mk is not None:
            conn.execute("UPDATE org_agenda SET metadata_json=? WHERE id=?", (json.dumps({"unit": int(seat["unit_id"]), "acting": successor, "prior": _lc(conn, org).get("returns_as")}), int(mk["id"])))
    elif seat["role_key"] == rules.get("head") and any(fn(conn, org, seat, int(day), why) for _k, fn in list(_HEAD_VACANCY)):
        successor = None  # a contest (or a coup) decides it, over weeks
    elif seat["role_key"] in (_lc(conn, org).get("succession") or {}):
        successor = fill_post(conn, org, seat["role_key"], int(day))
    target = successor if successor is not None else _live_superior(conn, org, seat)
    if target is not None:
        conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND superior_actor_id=? AND status='active' AND actor_id<>?",
                     (target, org, gone, target))
        # the man who now answers for the gone seat must not still answer to the dead man (a unit leader whose co-leader died, a successor
        # taken from under him): he answers to the gone man's own superior, else the head, and to no one when he is the head
        mine = conn.execute("SELECT superior_actor_id FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (int(target), org)).fetchone()
        if mine is not None and mine[0] is not None and int(mine[0]) == gone:
            above = seat["superior_actor_id"]
            head = orgs.head_of(conn, org)
            up = None
            for cand in (above, head):
                if cand is not None and int(cand) not in (gone, int(target)) and orgs.seat_of(conn, int(cand), org) is not None \
                        and orgs.seat_of(conn, int(cand), org)["status"] == "active" and orgs.is_living(conn, int(cand)):
                    up = int(cand)
                    break
            conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE actor_id=? AND org_actor_id=?", (up, int(target), org))
    for (sub,) in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND superior_actor_id=?",
                               (org, target if target is not None else -1)).fetchall():
        orgs.imposed(conn, int(sub))  # the men whose superior is gone are looked at again tomorrow
    mark_for_history(conn, gone, {"dead": "died", "out": "left the life", "held": "was held for a year"}.get(why, why), int(day))
    kind = conn.execute("SELECT org_kind FROM org_profiles WHERE org_actor_id=?", (org,)).fetchone()[0]
    for k, fn in list(_VACANCY):
        if k is None or k == kind:
            fn(conn, org, seat, int(day), why)


def _process_vacancies(conn: sqlite3.Connection, day: int) -> int:
    rows = conn.execute(
        """SELECT s.* FROM org_seats s WHERE s.status IN ('dead','out','held')
             AND NOT EXISTS (SELECT 1 FROM org_agenda g WHERE g.kind='vacancy' AND g.actor_id=s.actor_id AND g.subject_id=s.org_actor_id)
           ORDER BY s.id""").fetchall()
    for seat in rows:
        _vacate(conn, seat, seat["status"], int(day))
        conn.execute(  # the marker: this seat's vacancy has been dealt with (a released man's marker is removed)
            "INSERT INTO org_agenda(actor_id,kind,due_day,subject_kind,subject_id,created_day,status,resolved_day,metadata_json) VALUES (?,?,?,?,?,?,'resolved',?,?)",
            (int(seat["actor_id"]), "vacancy", int(day), "org", int(seat["org_actor_id"]), int(day), int(day), json.dumps({"why": seat["status"]})))
    return len(rows)


def _reattach(conn: sqlite3.Connection, day: int) -> int:
    """A man in a kind with ranks who answers to no one living (taken on while his unit had no leader, or his superior is gone and the
    vacancy was settled some other way) answers to his unit's leader, else the head. Nothing is moved when there is no one to answer to."""
    n = 0
    rows = conn.execute(
        """SELECT s.id,s.actor_id,s.org_actor_id,s.unit_id,s.role_key FROM org_seats s WHERE s.status='active' AND (s.superior_actor_id IS NULL OR NOT EXISTS
             (SELECT 1 FROM org_seats t WHERE t.actor_id=s.superior_actor_id AND t.org_actor_id=s.org_actor_id AND t.status IN ('active','held')))
           ORDER BY s.id""").fetchall()
    for r in rows:
        org, a = int(r["org_actor_id"]), int(r["actor_id"])
        rules = orgs.kind_rules(conn, org)
        if rules.get("flat") or r["role_key"] == rules.get("head"):
            continue
        cands = []
        if r["unit_id"] is not None:
            u = conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (int(r["unit_id"]),)).fetchone()
            cands.append(None if u is None else u[0])
        cands.append(orgs.head_of(conn, org))
        for c in cands:
            if c is None or int(c) == a or not orgs.is_living(conn, int(c)):
                continue
            cs = orgs.seat_of(conn, int(c), org)
            if cs is not None and cs["status"] == "active":
                conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE id=?", (int(c), int(r["id"])))
                n += 1
                break
    return n


def _fill_headless(conn: sqlite3.Connection, day: int) -> int:
    """An organisation with men in it and no one in its head's seat (no contest open, no acting man) takes the matter up the way a
    vacancy does: the registered head-vacancy hooks (a contest), else the kind's own succession. A vacancy settled while the seat's
    last holder was not recorded as head (an acting man who died after stepping back) would otherwise leave a family leaderless for years."""
    n = 0
    for (org,) in conn.execute("SELECT org_actor_id FROM org_profiles ORDER BY org_actor_id").fetchall():
        org = int(org)
        rules = orgs.kind_rules(conn, org)
        head_role = rules.get("head")
        if not head_role or rules.get("flat"):
            continue
        if conn.execute("SELECT 1 FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active' LIMIT 1", (org, head_role)).fetchone():
            continue
        if not conn.execute("SELECT 1 FROM org_seats WHERE org_actor_id=? AND status='active' LIMIT 1", (org,)).fetchone():
            continue
        if conn.execute("SELECT 1 FROM org_agenda WHERE status='open' AND ((kind='contest' AND actor_id=?) OR (kind='acting_head' AND subject_id=?)) LIMIT 1", (org, org)).fetchone():
            continue
        last = conn.execute("SELECT * FROM org_seats WHERE org_actor_id=? AND role_key=? ORDER BY id DESC LIMIT 1", (org, head_role)).fetchone()
        if last is None:
            continue
        if any(fn(conn, org, last, int(day), last["status"]) for _k, fn in list(_HEAD_VACANCY)):
            n += 1
        elif head_role in (_lc(conn, org).get("succession") or {}) and fill_post(conn, org, head_role, int(day)) is not None:
            n += 1
        elif last["status"] in ("dead", "out") and _take_over(conn, org, int(day)) is not None:
            n += 1
    return n


def _take_over(conn: sqlite3.Connection, org: int, day: int) -> int | None:
    """Nobody the data names can stand or succeed (a small splinter group): the best member left, an inducted one when there is
    one, takes the head's seat, so no group is left answering to a dead man."""
    from .org_succession import install_head
    pool = [r for r in orgs.members(conn, org) if orgs.is_living(conn, int(r["actor_id"]))]
    pool = [r for r in pool if r["inducted_day"] is not None] or pool
    if not pool:
        return None
    return install_head(conn, org, int(_best(conn, pool, None, day)["actor_id"]), day, "last_resort")


def _custody_held(conn: sqlite3.Connection) -> dict[int, int]:
    return {int(a): int(s) for a, s in conn.execute("SELECT actor_id,MIN(since_day) FROM custody WHERE kind='held' GROUP BY actor_id")}


def _levels_pair(conn: sqlite3.Connection) -> tuple[int, int]:
    """(the level reviewed most often, the next one) from the package's cadence_days (level -> days between reviews)."""
    cad = sorted(((int(v), int(k)) for k, v in (org_rules(package_for(conn)).get("cadence_days") or {}).items()))
    return (cad[0][1], cad[1][1]) if len(cad) > 1 else (cad[0][1], cad[0][1])


def _channel_grip(conn: sqlite3.Connection, actor_id: int) -> float:
    """How well a man held can still reach the outside (prison channels); 0 in a world with no prison data."""
    try:
        from .prison_channels import channel_grip
        return channel_grip(conn, int(actor_id))
    except sqlite3.OperationalError:
        return 0.0


def _held_decisions(conn: sqlite3.Connection, held: dict[int, int], day: int) -> int:
    """Each week, for every active seat whose man is held, the man's superior (the head when he has none) weighs two things.
    Whether to take his daily review away: the longer he has been held, the likelier, less if his sentence is nearly served or
    he is loyal to the head. Whether to give the seat away: the same against the kind's typical seat-keeping time; a unit
    leader may instead be given an acting man (his seat is filled, and he takes it back when he is released). The figures
    `held_level_days` and `held_seat_days` are the typical durations that set these pressures, not timers."""
    from . import org_motives
    high, low = _levels_pair(conn)
    until = {int(a): u for a, u in conn.execute("SELECT actor_id,MAX(until_day) FROM custody WHERE kind='held' GROUP BY actor_id")}
    n = 0
    for s in conn.execute("SELECT * FROM org_seats WHERE status='active' AND actor_id IN (%s)" % ",".join("?" * len(held)), list(held)).fetchall() if held else []:
        a, org = int(s["actor_id"]), int(s["org_actor_id"])
        lc = _lc(conn, org)
        dec = lc.get("held_decision")
        if not dec:
            continue
        d = int(day) - held[a]
        left = None if until.get(a) is None else max(0, int(until[a]) - int(day))
        head = orgs.head_of(conn, org)
        loyal = _head_loyalty(conn, a, head)
        lw = _num(conn, dec, "loyalty_weight", 0.0)
        keep = 1.0 - _num(conn, dec, "channel_weight", 0.0) * _channel_grip(conn, a)  # a man who can still reach the outside is kept longer
        lvl_days, seat_days = _num(conn, lc, "held_level_days"), _num(conn, lc, "held_seat_days")
        if lvl_days and int(s["level"]) == high and role_level(conn, org, s["role_key"]) == high:
            soon = 1.0 if left is None else min(1.0, left / lvl_days)
            p = _num(conn, dec, "level_week", 0.0) * min(1.0, d / lvl_days) * soon * (1.0 - lw * loyal) * keep
            if p > 0 and org_motives._roll(conn, a, int(day), "held_level") < p:
                orgs.set_level(conn, a, low, int(day), org)
                n += 1
        if seat_days:
            p = _num(conn, dec, "seat_week", 0.0) * min(1.0, d / seat_days) * (1.0 - lw * loyal) * keep
            if p > 0 and org_motives._roll(conn, a, int(day), "held_seat") < p:
                rules = orgs.kind_rules(conn, org)
                if s["role_key"] == rules.get("unit_leader") and s["unit_id"] and org_motives._roll(conn, a, int(day), "held_acting") < _num(conn, dec, "acting_share", 0.0) * loyal:
                    conn.execute("INSERT INTO org_agenda(actor_id,kind,due_day,subject_kind,subject_id,created_day,metadata_json) VALUES (?,?,?,?,?,?,?)",
                                 (a, "acting", int(day), "org", org, int(day), json.dumps({"unit": int(s["unit_id"])})))
                conn.execute("UPDATE org_seats SET status='held', left_day=? WHERE id=?", (int(day), int(s["id"])))
                n += 1
    return n


def _held_and_released(conn: sqlite3.Connection, day: int) -> int:
    held = _custody_held(conn)
    n = _held_decisions(conn, held, int(day))
    for s in conn.execute("SELECT * FROM org_seats WHERE status='held'").fetchall():
        a = int(s["actor_id"])
        if a in held or not orgs.is_living(conn, a):
            continue
        _return(conn, s, int(day))
        n += 1
    return n


def _return(conn: sqlite3.Connection, seat, day: int) -> None:
    """A man released after his seat was given up takes it back when it is still free, else the role the kind says a
    returning man takes (else he is retired from the organisation). A release is something done to him."""
    org, a, role = int(seat["org_actor_id"]), int(seat["actor_id"]), seat["role_key"]
    rules = orgs.kind_rules(conn, org)
    taken = False
    if role == rules.get("unit_leader") and seat["unit_id"]:
        cur = conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (int(seat["unit_id"]),)).fetchone()
        taken = cur is not None and cur[0] is not None and int(cur[0]) != a
    elif role == rules.get("head"):
        h = orgs.head_of(conn, org)
        taken = h is not None and h != a
        if not taken and conn.execute("SELECT 1 FROM org_agenda WHERE kind='contest' AND subject_id=? AND actor_id=? AND COALESCE(json_extract(metadata_json,'$.outcome'),'')<>'returned' LIMIT 1",
                                      (a, org)).fetchone() is not None:
            taken = True  # a contest replaced him (or is still running): a seat that fell vacant again is not his to retake, and two heads follow if he does
        if taken and any(fn(conn, org, a, int(day)) for _k, fn in list(_RETURNS)):
            taken = False
    conn.execute("DELETE FROM org_agenda WHERE kind='vacancy' AND actor_id=? AND subject_id=?", (a, org))
    mk = conn.execute("SELECT * FROM org_agenda WHERE kind='acting' AND status='open' AND actor_id=? AND subject_id=?", (a, org)).fetchone()
    if mk is not None:
        conn.execute("UPDATE org_agenda SET status='resolved', resolved_day=? WHERE id=?", (int(day), int(mk["id"])))
        meta = json.loads(mk["metadata_json"] or "{}")
        acting = meta.get("acting")
        if taken and acting is not None and seat["unit_id"]:
            cur = conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (int(seat["unit_id"]),)).fetchone()
            if cur is not None and cur[0] is not None and int(cur[0]) == int(acting):
                prior = meta.get("prior") or _lc(conn, org).get("returns_as")
                if prior:  # the acting man steps back; the men who answered to him answer to the man who is back
                    conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=? WHERE actor_id=? AND org_actor_id=?", (prior, a, int(acting), org))
                    membership_text(conn, org, int(acting), prior)
                    conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND superior_actor_id=? AND status='active' AND actor_id NOT IN (?,?)",
                                 (a, org, int(acting), a, int(acting)))
                    conn.execute("UPDATE org_units SET leader_actor_id=? WHERE id=?", (a, int(seat["unit_id"])))
                    conn.execute("UPDATE org_lines SET holder_actor_id=? WHERE holder_actor_id=? AND unit_id=? AND status='active'", (a, int(acting), int(seat["unit_id"])))
                    taken = False
                    orgs.imposed(conn, int(acting))
    if taken:
        back = _lc(conn, org).get("returns_as")
        if not back:
            conn.execute("UPDATE org_seats SET status='retired' WHERE id=?", (int(seat["id"]),))
            return
        leader = conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (int(seat["unit_id"] or 0),)).fetchone()
        sup = int(leader[0]) if leader and leader[0] is not None else orgs.head_of(conn, org)
        conn.execute("UPDATE org_seats SET status='active', left_day=NULL, role_key=?, superior_actor_id=? WHERE id=?", (back, sup, int(seat["id"])))
        membership_text(conn, org, a, back)
        role = back
    else:
        conn.execute("UPDATE org_seats SET status='active', left_day=NULL WHERE id=?", (int(seat["id"]),))
        s2 = orgs.seat_of(conn, int(seat["superior_actor_id"]), org) if seat["superior_actor_id"] is not None else None
        if seat["superior_actor_id"] is not None and (s2 is None or s2["status"] != "active"):
            conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE id=?", (_live_superior(conn, org, seat), int(seat["id"])))
    lv = role_level(conn, org, role)
    orgs.set_level(conn, a, lv if lv is not None else int(seat["level"]), day, org)
    orgs.imposed(conn, a)


def _levels(conn: sqlite3.Connection, day: int) -> int:
    """Men whose role is played at level 4 drop to 3 when held over `held_level_days` or when a man in a step-back role has
    an open step-back agenda, and go back to 4 when neither holds."""
    held = _custody_held(conn)
    high, low = _levels_pair(conn)
    n = 0
    for (org,) in conn.execute("SELECT org_actor_id FROM org_profiles").fetchall():
        lc = _lc(conn, int(org))
        if not lc:
            continue
        back_roles = set(lc.get("step_back_roles") or [])
        back_kinds = list(lc.get("step_back_agendas") or [])
        stepped: set[int] = set()
        if back_roles and back_kinds:
            stepped = {int(r[0]) for r in conn.execute(
                "SELECT DISTINCT actor_id FROM org_agenda WHERE status='open' AND kind IN (%s)" % ",".join("?" * len(back_kinds)), back_kinds)}
        for s in conn.execute("SELECT * FROM org_seats WHERE org_actor_id=? AND status='active' AND level IN (?,?)", (int(org), high, low)).fetchall():
            a = int(s["actor_id"])
            if role_level(conn, int(org), s["role_key"]) != high:
                continue
            down = (a in held and int(s["level"]) == low) or (s["role_key"] in back_roles and a in stepped)  # a held man's drop is his superior's weighed decision
            if down and int(s["level"]) == high:
                orgs.set_level(conn, a, low, int(day), int(org))
                n += 1
            elif not down and int(s["level"]) == low:
                orgs.set_level(conn, a, high, int(day), int(org))
                n += 1
    return n


def _dormant_the_left(conn: sqlite3.Connection, day: int) -> int:
    n = 0
    for s in conn.execute(
            """SELECT s.actor_id,s.org_actor_id FROM org_seats s LEFT JOIN simulation_profiles p ON p.actor_id=s.actor_id
               WHERE s.status='out' AND (p.actor_id IS NULL OR p.tier<>'DORMANT')""").fetchall():
        n += 1 if _dormant(conn, int(s[0]), int(s[1]), int(day)) else 0
    return n


def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    try:
        if conn.execute("SELECT 1 FROM org_seats LIMIT 1").fetchone() is None:
            return None
    except sqlite3.OperationalError:
        return None
    due = ((int(after_day) - DUE_OFFSET) // WEEK + 1) * WEEK + DUE_OFFSET
    return due if due <= int(end_day) else None


def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict:
    out = {"died": _mark_dead(conn, int(day))}
    out["released"] = _held_and_released(conn, int(day))
    out["vacancies"] = _process_vacancies(conn, int(day))
    out["headless_taken_up"] = _fill_headless(conn, int(day))
    out["reattached"] = _reattach(conn, int(day))
    out["dormant"] = _dormant_the_left(conn, int(day))
    out["levels"] = _levels(conn, int(day))
    for _k, fn in list(_WEEKLY):
        for key, v in (fn(conn, int(day)) or {}).items():
            out[key] = out.get(key, 0) + v
    return out


from . import life_matters  # noqa: E402  (registers the weekly ordinary-life pass)
on_week(life_matters.weekly)
from . import physique  # noqa: E402  (bodies: the newly born get one, a life moves the rest)
on_week(physique.weekly)
from . import temptations  # noqa: E402,F401  (registers its own weekly pass: concrete chances tied to wants)
```

## engine/org_membership.py

```python
"""How an organisation keeps its numbers true (generic layer, driven by the package's data; names no role or organisation).

Where an organisation has a member figure and a dependent role (orgs.json `opening.member_role` / `dependent_role`, the
outfit entry's `members_figure` and `dependents_figure`) and the sphere file has a `membership` block, this layer runs in
the weekly lifecycle process (`org_lifecycle.on_week`) and on every vacancy (`org_lifecycle.on_vacancy`):

  books      a vacated inducted seat opens the books: the head gets agenda `open_books` when the inducted count is below the
             figure (the figure itself, never above the range top unless a dated cause moved it, `limit`); he asks each unit
             leader for one name (`propose_member`); the leader names the dependant with the best standing in his unit whose
             family name is in the induction `father_name_group`; the head makes him (`make_member`); the men he brought in
             answer to him. A short count with nothing open reopens the books after `books.retry_days`.
  dependants lost dependants (inducted, dead, out) are replaced one by one (each missing place has its own weekly chance, no limit per week), by pulling up young
             people from the city's background population with the organisation's name-group mix; a dependant's standing
             rises weekly while he earns.
  hidden     a hidden line is caught with a weekly chance that falls with its holder's caution; the head gets `discipline`
             with the holder as subject and may fine him (the kick-up kept back, with a penalty), take the line, or have him
             killed.

Every rate here is a design figure named in the package's `membership` block (a number or a figure key).
"""
from __future__ import annotations

import json
import random
import sqlite3

from . import ledger, org_motives, orgs
from .org_motives import _fig as figure
from .design import package_figures, run_seed
from .org_choices import register_agenda_action, register_executor
from .org_lifecycle import mark_for_history, membership_text, on_vacancy, on_week, role_level
from .orgs import add_agenda, clamp01, head_of, imposed, is_living, kind_rules, resolve_agenda, seat_of
from .relationships import adjust_relationship, ensure_relationship
from .world_package import org_rules, package_for

WEEK = 7
BOOKS_KINDS = ("open_books", "propose_member", "make_member")
_C: dict = {"key": None}


def _cache(conn: sqlite3.Connection) -> dict:
    """What the package's files say that does not change in a run (parsed once per database): figure ranges, the money
    period, the ledger kinds, the induction surnames."""
    key = orgs.db_key(conn)
    if _C["key"] != key:
        rules = org_rules(package_for(conn))
        _C.clear()
        _C.update(key=key, ranges={k: (v.get("range"), v.get("extended_range")) for k, v in package_figures(conn).items()},
                  period=int(rules.get("period_days") or 28), ledger_kinds=dict(rules.get("ledger_kinds") or {}), surnames={})
    return _C


def _data(conn: sqlite3.Connection) -> dict:
    return org_motives._sphere_data(conn).get("membership") or {}


def _v(conn: sqlite3.Connection, spec, default: float = 0.0) -> float:
    return org_motives._value(conn, spec, default)


def _name(conn: sqlite3.Connection, actor_id: int | None) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone() if actor_id is not None else None
    return str(r[0]) if r else "someone"


def _spec(conn: sqlite3.Connection, org: int) -> dict | None:
    """What this layer needs to know about one organisation, or None when the package's data does not give it a member
    figure, a member role and a dependent role."""
    if not _data(conn):
        return None
    row = conn.execute("SELECT package_key,metadata_json FROM org_profiles WHERE org_actor_id=?", (int(org),)).fetchone()
    if row is None:
        return None
    outfits = org_motives._sphere_data(conn).get("outfits") or {}
    outfit = outfits.get(row[0])
    if outfit is None and "~" in str(row[0]):  # an organisation split off another: its parent's entry with figures of its own (numbers)
        outfit = {**(outfits.get(str(row[0]).split("~")[0]) or {}), **(json.loads(row[1] or "{}").get("spec") or {})}
    outfit = outfit or {}
    opening = kind_rules(conn, org).get("opening") or {}
    if not (outfit.get("members_figure") and opening.get("member_role") and opening.get("dependent_role")):
        return None
    return {"outfit": outfit, "opening": opening, "member": opening["member_role"], "dependent": opening["dependent_role"],
            "figure": outfit["members_figure"], "key": row[0]}


def _orgs(conn: sqlite3.Connection) -> list[tuple[int, dict]]:
    out = []
    for (org,) in conn.execute("SELECT org_actor_id FROM org_profiles ORDER BY org_actor_id").fetchall():
        sp = _spec(conn, int(org))
        if sp is not None:
            out.append((int(org), sp))
    return out


def _num(conn: sqlite3.Connection, x) -> float:
    """A figure's run value, or the number itself (an organisation that split off carries plain numbers)."""
    return float(x) if isinstance(x, (int, float)) else float(figure(conn, x))


def made_count(conn: sqlite3.Connection, org: int) -> int:
    """Inducted men in active seats."""
    return int(conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND inducted_day IS NOT NULL AND status='active'", (int(org),)).fetchone()[0])


def preferred(conn: sqlite3.Connection, org: int) -> int:
    """The head's preferred number of inducted men: the organisation's figure. It is not a cap: the count drifts above and
    below it with the head's decisions (`after_gone`, `make_offers`)."""
    sp = _spec(conn, org)
    return 0 if sp is None else int(round(_num(conn, sp["figure"])))


def flag_unusual(conn: sqlite3.Connection, day: int) -> int:
    """A count outside the figure's range is not refused; it is written to the design log as unusual (needs a cause), once per
    new count, so the GM sees it."""
    n = 0
    for org, sp in _orgs(conn):
        rng, _ext = _cache(conn)["ranges"].get(sp["figure"], (None, None))
        count = made_count(conn, org)
        if not isinstance(rng, list) or float(rng[0]) <= count <= float(rng[1]):
            continue
        last = conn.execute("SELECT new_value FROM design_figure_log WHERE key=? AND cause LIKE 'unusual:%' ORDER BY id DESC LIMIT 1", (sp["figure"],)).fetchone()
        if last is not None and int(last[0]) == count:
            continue
        conn.execute("INSERT INTO design_figure_log(key,day,old_value,new_value,seed,cause) VALUES (?,?,?,?,?,?)",
                     (sp["figure"], int(day), _num(conn, sp["figure"]), float(count), run_seed(conn),
                      f"unusual: {_name(conn, org)} has {count} inducted men, outside the figure's range {rng[0]} to {rng[1]}; needs a cause"))
        n += 1
    return n


def _father_names(conn: sqlite3.Connection) -> set[str] | None:
    group = (org_motives._sphere_data(conn).get("induction") or {}).get("father_name_group")
    if not group:
        return None
    cache = _cache(conn)["surnames"]
    if group not in cache:
        from .person_ecology import _group_families
        cache[group] = set(_group_families(conn, group))
    return cache[group]


def _nomination(conn: sqlite3.Connection, sp: dict, standing: float, name: str, birth_day, day: int) -> float | None:
    """How good a name to put forward: standing, less the induction weights for being under the usual age and for a family
    name outside the induction `father_name_group` (canon: the usual rule, exceptions Open: a strong weight, not a refusal).
    None only when the package's data says the canon text is an absolute rule (`induction.veto`)."""
    ind = org_motives._sphere_data(conn).get("induction") or {}
    score = float(standing)
    min_age = int(sp["opening"].get("inducted_after_age") or 0)
    if min_age and birth_day is not None and (int(day) - int(birth_day)) // 365 < min_age:
        score -= _v(conn, ind.get("age_weight"))
    names = _father_names(conn)
    if names is not None and str(name).split()[-1] not in names:
        if ind.get("veto"):
            return None
        score -= _v(conn, ind.get("name_weight"))
    return score


def nomination_score(conn: sqlite3.Connection, org: int, actor_id: int, day: int) -> float | None:
    sp = _spec(conn, org)
    r = conn.execute("SELECT s.standing,a.name,lp.birth_day FROM org_seats s JOIN actors a ON a.id=s.actor_id LEFT JOIN actor_life_profiles lp ON lp.actor_id=s.actor_id "
                     "WHERE s.actor_id=? AND s.org_actor_id=?", (int(actor_id), int(org))).fetchone()
    return None if sp is None or r is None else _nomination(conn, sp, r["standing"], r["name"], r["birth_day"], day)


def eligible(conn: sqlite3.Connection, org: int, unit_id: int, day: int) -> list[int]:
    """The dependants of one unit who could be put forward, best name first (`_nomination`): alive and not held. Age and
    family name only weigh; no one is refused unless the data's canon note makes the name rule absolute."""
    sp = _spec(conn, org)
    if sp is None:
        return []
    from .player import protagonist_id
    me = protagonist_id(conn)  # joining is their own choice, never put forward for them
    rows = conn.execute(
        """SELECT s.actor_id,s.standing,a.name,lp.birth_day FROM org_seats s JOIN actors a ON a.id=s.actor_id LEFT JOIN actor_life_profiles lp ON lp.actor_id=s.actor_id
           WHERE s.org_actor_id=? AND s.unit_id=? AND s.role_key=? AND s.status='active' AND s.inducted_day IS NULL
             AND NOT EXISTS (SELECT 1 FROM custody c WHERE c.actor_id=s.actor_id AND c.kind='held')""", (int(org), int(unit_id), sp["dependent"])).fetchall()
    scored = []
    for r in rows:
        sc = _nomination(conn, sp, r["standing"], r["name"], r["birth_day"], day)
        if sc is not None and int(r["actor_id"]) != me and is_living(conn, int(r["actor_id"])):
            scored.append((-sc, int(r["actor_id"])))
    return [a for _sc, a in sorted(scored)]


# ---- inducting a man ----

def induct(conn: sqlite3.Connection, org: int, actor_id: int, proposer: int, day: int) -> int:
    """A dependant becomes a member: the member role, inducted today, answering to the man who put him forward; the men he
    brought in (his recruits) answer to him; he and they are looked at tomorrow and the GM is owed his history."""
    sp = _spec(conn, org)
    seat = seat_of(conn, actor_id, org)
    old_sup = seat["superior_actor_id"]
    role = sp["member"]
    conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=?, inducted_day=? WHERE id=?", (role, int(proposer), int(day), int(seat["id"])))
    membership_text(conn, org, actor_id, role)
    from .outfit_opening import feelings_toward, seat_subtype
    inst = _name(conn, org)
    conn.execute("UPDATE actors SET subtype=? WHERE id=?", (seat_subtype(role, inst, sp["opening"].get("in_roles") or ()), int(actor_id)))
    lv = role_level(conn, org, role)
    orgs.set_level(conn, actor_id, lv if lv is not None else int(seat["level"]), int(day), org)
    if conn.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(actor_id), int(proposer))).fetchone() is None:
        feelings_toward(conn, int(actor_id), int(proposer), int(day), random.Random(f"{run_seed(conn)}:induct:{int(actor_id)}"))
    brought = set()
    for (meta,) in conn.execute("SELECT metadata_json FROM org_incidents WHERE kind='recruits' AND offender_actor_id=?", (int(actor_id),)).fetchall():
        r = json.loads(meta or "{}").get("recruit")
        if r is not None:
            brought.add(int(r))
    for r in sorted(brought):
        s = seat_of(conn, r, org)
        if s is not None and s["status"] == "active" and s["superior_actor_id"] == old_sup:
            conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE id=?", (int(actor_id), int(s["id"])))
            imposed(conn, r)
    imposed(conn, int(actor_id))
    label = str(kind_rules(conn, org).get("inducted_label") or "inducted")
    mark_for_history(conn, int(actor_id), f"was {label} into the {inst}", int(day))
    return int(actor_id)


# ---- the books ----

def _stale_days(conn: sqlite3.Connection) -> int:
    return int(_v(conn, (_data(conn).get("books") or {}).get("retry_days"), 28.0))


def _open_items(conn: sqlite3.Connection, org: int, day: int) -> int:
    """Books items still alive: open, held by a man whose seat is active, and not older than the retry time past due."""
    return int(conn.execute(
        "SELECT COUNT(*) FROM org_agenda g JOIN org_seats s ON s.actor_id=g.actor_id AND s.org_actor_id=? WHERE g.status='open' AND s.status='active' AND g.due_day>=? "
        "AND g.kind IN (%s) AND json_extract(g.metadata_json,'$.org')=?" % ",".join("?" * len(BOOKS_KINDS)),
        (int(org), int(day) - _stale_days(conn), *BOOKS_KINDS, int(org))).fetchone()[0])


def expire_stale(conn: sqlite3.Connection, day: int) -> int:
    """A books item nobody answered (its holder was killed, held or left, or it is long past due) is closed, so it does
    not keep the books shut."""
    cur = conn.execute(
        "UPDATE org_agenda SET status='resolved', resolved_day=? WHERE status='open' AND kind IN (%s) AND (due_day<? OR NOT EXISTS "
        "(SELECT 1 FROM org_seats s WHERE s.actor_id=org_agenda.actor_id AND s.org_actor_id=json_extract(org_agenda.metadata_json,'$.org') AND s.status='active'))" % ",".join("?" * len(BOOKS_KINDS)),
        (int(day), *BOOKS_KINDS, int(day) - _stale_days(conn)))
    return cur.rowcount


def _short(conn: sqlite3.Connection, org: int) -> float:
    """How far under the preferred size the count is, 0 at or above it and 1 at `short_span` of it under."""
    w = (_data(conn).get("books") or {}).get("weigh") or {}
    target = max(1, preferred(conn, org))
    return clamp01((target - made_count(conn, org)) / (target * max(1e-9, _v(conn, w.get("short_span"), 0.1))))


def books_pressure(conn: sqlite3.Connection, org: int, day: int, head: int) -> float:
    """How strongly the head is drawn to open the books: men short of the figure, earners waiting (dependants of standing),
    his money, a war on (recent killings across organisations that reached him), his own ambition; and held back by law
    heat (open cases against the organisation's inducted men). Each weight and scale is a design figure."""
    w = (_data(conn).get("books") or {}).get("weigh") or {}
    sp = _spec(conn, org)
    waiting = conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active' AND standing>=?",
                           (int(org), sp["dependent"], _v(conn, w.get("waiting_standing"), 0.5))).fetchone()[0]
    war = conn.execute("SELECT COUNT(*) FROM org_incidents WHERE kind='killing' AND raised_to_org_actor_id=? AND day>?", (int(org), int(day) - 180)).fetchone()[0]
    heat = conn.execute("SELECT COUNT(*) FROM crime_reports r JOIN org_seats s ON s.actor_id=r.offender_actor_id WHERE r.status='open' AND s.org_actor_id=? AND s.inducted_day IS NOT NULL", (int(org),)).fetchone()[0]
    parts = {"short": _short(conn, org), "waiting": clamp01(waiting / max(1e-9, _v(conn, w.get("waiting_scale"), 10.0))),
             "money": clamp01(ledger.balance(conn, ("person", int(head))) / max(1e-9, _v(conn, w.get("money_scale"), 1.0))),
             "war": clamp01(war / max(1e-9, _v(conn, w.get("war_scale"), 3.0))), "ambition": _drive(conn, int(head), "ambition")}
    rest = 1.0
    for k, m in parts.items():
        rest *= 1.0 - clamp01(_v(conn, w.get("w_" + k))) * m
    return clamp01((1.0 - rest) * (1.0 - clamp01(_v(conn, w.get("w_heat"))) * clamp01(heat / max(1e-9, _v(conn, w.get("heat_scale"), 6.0)))))


def after_gone(conn: sqlite3.Connection, org: int, day: int, *, immediate: bool = True) -> bool:
    """The head weighs opening the books (`books_pressure` x the weekly `rate_week`; one draw a day from the run seed) unless
    they are open already. Nothing here compares the count with a limit: a family drifts above and below its figure."""
    sp = _spec(conn, org)
    head = head_of(conn, org) if sp is not None else None
    if sp is None or head is None or _open_items(conn, org, int(day)):
        return False
    rate = _v(conn, ((_data(conn).get("books") or {}).get("weigh") or {}).get("rate_week"), 0.0)
    if org_motives._roll(conn, head, int(day), "open_books") >= rate * books_pressure(conn, org, int(day), head):
        return False
    add_agenda(conn, head, "open_books", int(day), subject_kind="org", subject_id=int(org), metadata={"org": int(org)})
    return True


def _utility(conn: sqlite3.Connection, x: float) -> float:
    return float(figure(conn, "org_choice_utility_base", default=8.0)) + float(figure(conn, "org_choice_utility_span", default=10.0)) * clamp01(x)


def _meta(item) -> dict:
    return json.loads(item["metadata_json"] or "{}")


def _finish(conn: sqlite3.Connection, payload: dict, day: int) -> None:
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))


def _delay(conn: sqlite3.Connection) -> int:
    return int(_v(conn, (_data(conn).get("books") or {}).get("delay_days"), 3.0))


def books_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    org = int(_meta(item)["org"])
    return [{"kind": "ask_for_names", "utility": _utility(conn, 1.0), "rationale": f"Opens the books of the {_name(conn, org)} and asks each unit leader for a name.",
             "payload": {"org": org}}]


def execute_ask_for_names(conn, actor_id, kind, payload, day):
    org = int(payload["org"])
    _finish(conn, payload, day)
    asked = 0
    for (leader,) in conn.execute("SELECT DISTINCT leader_actor_id FROM org_units WHERE org_actor_id=? AND leader_actor_id IS NOT NULL ORDER BY leader_actor_id", (org,)).fetchall():
        s = seat_of(conn, int(leader), org)
        if int(leader) == int(actor_id) or s is None or s["status"] != "active" or not is_living(conn, int(leader)):
            continue
        add_agenda(conn, int(leader), "propose_member", int(day) + _delay(conn), subject_kind="org", subject_id=org, metadata={"org": org, "head": int(actor_id)})
        asked += 1
    return {"summary": f"{_name(conn, actor_id)} opened the books and asked {asked} for a name."}


def proposal_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    org = int(_meta(item)["org"])
    if head_of(conn, org) is None:
        return [{"kind": "no_name", "utility": _utility(conn, 1.0), "rationale": "There is no one to put a name to.", "payload": {"org": org}}]
    pool: list[tuple[float, int]] = []
    for (unit,) in conn.execute("SELECT id FROM org_units WHERE org_actor_id=? AND leader_actor_id=? ORDER BY id", (org, int(actor_id))).fetchall():
        pool += [(nomination_score(conn, org, a, int(day)), a) for a in eligible(conn, org, int(unit), int(day))]
    if not pool:
        return [{"kind": "no_name", "utility": _utility(conn, 1.0), "rationale": "He has no one fit to put forward.", "payload": {"org": org}}]
    from . import org_succession
    blk = org_succession.block(conn, org, "appoint")
    if not blk:
        sc, best = max(pool, key=lambda t: (t[0], -t[1]))
        return [{"kind": "propose_member", "utility": _utility(conn, 0.5 + 0.5 * clamp01(sc)), "target_actor_id": best,
                 "rationale": f"Puts forward {_name(conn, best)}, the best name in his crew ({sc:.2f}).", "payload": {"org": org, "candidate": best}}]
    names = dict((a, s) for s, a in pool)  # a leader weighs every man of his unit, not only the best name: trust, kin, favours, money, fear, merit
    ctx = {"merit": lambda c, _n=names: clamp01(_n.get(int(c), 0.0))}
    out = []
    for a in names:
        sc, parts = org_succession.weigh(conn, org, int(actor_id), a, int(day), blk, ctx, detail=True)
        lead = org_succession.lead_terms(parts)
        out.append({"kind": "propose_member", "utility": _utility(conn, sc), "target_actor_id": a,
                    "rationale": f"Puts forward {_name(conn, a)} ({sc:.2f}{', mostly ' + lead if lead else ''}).", "payload": {"org": org, "candidate": a}})
    return out


def execute_no_name(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    return {"summary": f"{_name(conn, actor_id)} had no name to give."}


def execute_propose_member(conn, actor_id, kind, payload, day):
    org, cand = int(payload["org"]), int(payload["candidate"])
    _finish(conn, payload, day)
    head = head_of(conn, org)
    if head is None:
        return {"summary": "There was no one to put the name to.", "blocked": True}
    add_agenda(conn, head, "make_member", int(day) + 1, subject_kind="actor", subject_id=cand, metadata={"org": org, "proposer": int(actor_id)})
    from . import org_succession
    blk = org_succession.block(conn, org, "appoint")
    if blk:
        passed = [a for a in eligible(conn, org, int(seat_of(conn, int(actor_id), org)["unit_id"] or 0), int(day)) if a != cand] if seat_of(conn, int(actor_id), org) is not None else []
        org_succession.paid_for(conn, org, int(actor_id), cand, int(day), blk)
        org_succession.after_choice(conn, org, int(actor_id), cand, passed, int(day), blk)
    return {"summary": f"{_name(conn, actor_id)} put {_name(conn, cand)} forward."}


def make_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    """The head weighs making the man against turning him down: the pull to make is the men short of the figure, the man's
    standing and the head's own ambition (all weights from `books.make`); the pull to refuse is the threshold figure. At the
    figure the pull is low but not nil, so a very good name can still be made and the count drifts above it."""
    meta = _meta(item)
    org, cand, proposer = int(meta["org"]), int(item["subject_id"]), int(meta["proposer"])
    s = seat_of(conn, cand, org)
    payload = {"org": org, "candidate": cand, "proposer": proposer}
    if s is None or s["status"] != "active" or s["inducted_day"] is not None or not is_living(conn, cand):
        return [{"kind": "decline_member", "utility": _utility(conn, 1.0), "rationale": "The man is no longer to be had.", "payload": payload}]
    sc = nomination_score(conn, org, cand, int(day))
    mk = (_data(conn).get("books") or {}).get("make") or {}
    rivals = [int(r[0]) for r in conn.execute("SELECT subject_id FROM org_agenda WHERE actor_id=? AND kind='make_member' AND status='open' AND due_day<=? AND id<>? "
                                              "AND json_extract(metadata_json,'$.org')=?", (int(actor_id), int(day), int(item["id"]), org)).fetchall()]
    if any((nomination_score(conn, org, r, int(day)) or -9.0, -r) > (sc if sc is not None else -9.0, -cand) for r in rivals if seat_of(conn, r, org) is not None and seat_of(conn, r, org)["status"] == "active"):
        return []  # a better name is waiting: it is weighed first
    standing = clamp01(sc if sc is not None else 0.0)
    pull = 1.0 - ((1.0 - _v(conn, mk.get("w_short")) * _short(conn, org)) * (1.0 - _v(conn, mk.get("w_standing")) * standing)
                  * (1.0 - _v(conn, mk.get("w_ambition")) * _drive(conn, int(actor_id), "ambition") * standing)
                  * (1.0 - _v(conn, mk.get("w_pressure")) * books_pressure(conn, org, int(day), int(actor_id))))
    return [{"kind": "make_member", "utility": _utility(conn, pull), "target_actor_id": cand,
             "rationale": f"Makes {_name(conn, cand)}, put forward by {_name(conn, proposer)}.", "payload": payload},
            {"kind": "decline_member", "utility": _utility(conn, _v(conn, mk.get("threshold"), 0.5)), "rationale": f"Turns down {_name(conn, cand)} for now.", "payload": payload}]


def execute_decline_member(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    return {"summary": f"{_name(conn, actor_id)} turned down {_name(conn, payload['candidate'])}."}


def execute_make_member(conn, actor_id, kind, payload, day):
    org, cand = int(payload["org"]), int(payload["candidate"])
    _finish(conn, payload, day)
    s = seat_of(conn, cand, org)
    if s is None or s["status"] != "active" or s["inducted_day"] is not None or not is_living(conn, cand):
        return {"summary": "The seat was no longer to be had.", "blocked": True}
    proposer = int(payload["proposer"])
    ps = seat_of(conn, proposer, org)
    leader = proposer if ps is not None and ps["status"] == "active" else head_of(conn, org)
    induct(conn, org, cand, int(leader), int(day))
    return {"summary": f"{_name(conn, cand)} was inducted under {_name(conn, leader)}."}


# ---- dependants ----

def replace_dependants(conn: sqlite3.Connection, day: int) -> int:
    """Each place a unit is short of its dependants (the organisation's figure per inducted man) is filled this week with the
    chance `replacement.chance_week`, drawn separately for each missing place: a crew that lost several can take more
    than one in a week. New people are pulled up from the background population."""
    data = _data(conn).get("replacement") or {}
    chance = _v(conn, data.get("chance_week"), 0.0)
    if chance <= 0.0:
        return 0
    made = 0
    for org, sp in _orgs(conn):
        ratio = _num(conn, sp["outfit"]["dependents_figure"]) if sp["outfit"].get("dependents_figure") else 0.0
        for unit in conn.execute("SELECT id,leader_actor_id FROM org_units WHERE org_actor_id=? AND leader_actor_id IS NOT NULL ORDER BY id", (org,)).fetchall():
            leader, uid = int(unit["leader_actor_id"]), int(unit["id"])
            men = conn.execute("SELECT COUNT(*) FROM org_seats WHERE unit_id=? AND status='active' AND inducted_day IS NOT NULL", (uid,)).fetchone()[0]
            deps = conn.execute("SELECT COUNT(*) FROM org_seats WHERE unit_id=? AND status='active' AND role_key=?", (uid, sp["dependent"])).fetchone()[0]
            for k in range(max(0, round(men * ratio) - deps)):
                if org_motives._roll(conn, leader, int(day), "replace_dependant" if k == 0 else f"replace_dependant:{k}") < chance:
                    made += 1 if _replace_one(conn, org, sp, uid, leader, int(day), data, k) else 0
    return made


def _replace_one(conn: sqlite3.Connection, org: int, sp: dict, unit: int, leader: int, day: int, data: dict, k: int = 0) -> int | None:
    from .outfit_opening import feelings_toward, pull_up, seat_subtype
    rng = random.Random(f"{run_seed(conn)}:replace:{unit}:{day}:{k}")
    role = (sp["opening"].get("roles") or {}).get(sp["dependent"]) or {}
    male = float((org_motives._sphere_data(conn).get("male_share") or {}).get(role.get("male_share_key"), 1.0))
    group = sp["outfit"].get("name_group") if rng.random() < float(sp["opening"].get("own_group_share", 1.0)) else None
    ages = tuple(int(x) for x in data["ages"])
    got = pull_up(conn, 1, stream=f"replace:{unit}:{day}:{k}", name_group=group, sex="male" if rng.random() < male else "female", ages=ages,
                  subtype=seat_subtype(sp["dependent"], _name(conn, org), sp["opening"].get("in_roles") or ()), criminal_weight=float(role.get("criminal_weight", 1.0)))
    if not got:
        return None
    new = int(got[0])
    patron = conn.execute(
        """SELECT s.actor_id FROM org_seats s WHERE s.unit_id=? AND s.status='active' AND s.role_key=? AND s.inducted_day IS NOT NULL
           ORDER BY (SELECT COUNT(*) FROM org_seats d WHERE d.superior_actor_id=s.actor_id AND d.status='active'), s.actor_id LIMIT 1""", (unit, sp["member"])).fetchone()
    sup = int(patron[0]) if patron else leader
    st = role.get("standing") or {"mean": 0.3, "sd": 0.2}
    lv = role_level(conn, org, sp["dependent"])
    orgs.seat(conn, new, org, sp["dependent"], unit_id=unit, superior_actor_id=sup, level=lv if lv is not None else 3, day=day,
              standing=clamp01(rng.gauss(float(st["mean"]), float(st["sd"]))), provenance="replacement")
    feelings_toward(conn, new, sup, day, rng)
    return new


def _standing_data(conn: sqlite3.Connection) -> dict:
    return _data(conn).get("standing") or {}


def seed_standing(conn: sqlite3.Connection, day: int) -> int:
    """At the opening, an inducted man's standing from his years inducted, the weight of his role and what his lines bring in a
    week (each weight and scale a design figure named in `membership.standing`); dependants keep what the opening gave them."""
    d = _standing_data(conn)
    if not d:
        return 0
    n = 0
    for org, sp in _orgs(conn):
        for s in conn.execute("SELECT id,actor_id,role_key,inducted_day FROM org_seats WHERE org_actor_id=? AND status='active' AND inducted_day IS NOT NULL", (org,)).fetchall():
            years = max(0.0, (int(day) - int(s["inducted_day"])) / 365.0)
            take = conn.execute("SELECT COALESCE(SUM(weekly_take),0) FROM org_lines WHERE holder_actor_id=? AND status='active'", (int(s["actor_id"]),)).fetchone()[0]
            v = (_v(conn, d.get("w_years")) * min(1.0, years / max(1e-9, _v(conn, d.get("years_cap"), 25.0)))
                 + _v(conn, d.get("w_role")) * _v(conn, (d.get("role_weight") or {}).get(s["role_key"]), 0.0)
                 + _v(conn, d.get("w_earn")) * min(1.0, float(take) / max(1e-9, _v(conn, d.get("earn_scale"), 1.0))))
            conn.execute("UPDATE org_seats SET standing=? WHERE id=?", (clamp01(v), int(s["id"])))
            n += 1
    return n


def move_standing(conn: sqlite3.Connection, day: int) -> int:
    """Every inducted man's standing moves weekly: a man who earned or passed money up in the last period gains
    `growth` x what is left to gain; a man taken into custody this week loses `arrest_loss`."""
    d = _standing_data(conn)
    if not d:
        return 0
    period, n = _cache(conn)["period"], 0
    flows = list(d.get("earning_flows") or [])
    g = _v(conn, d.get("growth"))
    if flows and g > 0.0:
        q = ",".join("?" * len(flows))
        n += conn.execute(
            """UPDATE org_seats SET standing=MIN(1.0, standing + ? * (1.0 - standing)) WHERE status='active' AND inducted_day IS NOT NULL AND actor_id IN
               (SELECT from_actor_id FROM org_money WHERE kind IN (%s) AND day>? AND day<=? UNION SELECT to_actor_id FROM org_money WHERE kind IN (%s) AND day>? AND day<=?)""" % (q, q),
            (g, *flows, int(day) - period, int(day), *flows, int(day) - period, int(day))).rowcount
    loss = _v(conn, d.get("arrest_loss"))
    if loss > 0.0:
        n += conn.execute(
            "UPDATE org_seats SET standing=MAX(0.0, standing - ?) WHERE status='active' AND actor_id IN (SELECT actor_id FROM custody WHERE kind='held' AND since_day>? AND since_day<=?)",
            (loss, int(day) - WEEK, int(day))).rowcount
    return n


def grow_standing(conn: sqlite3.Connection, day: int) -> int:
    """Dependants who earned in the last period gain standing: `standing_growth * (reliability + ambition)` of what is still
    to gain (a reputation grows fast at first and slowly after)."""
    g = _v(conn, _data(conn).get("standing_growth"), 0.0)
    if g <= 0.0:
        return 0
    period = _cache(conn)["period"]
    n = 0
    for org, sp in _orgs(conn):
        cur = conn.execute(
            """UPDATE org_seats SET standing=MIN(1.0, standing + ? * (reliability + COALESCE((SELECT ambition FROM actor_drives d WHERE d.actor_id=org_seats.actor_id),0.5)) * (1.0 - standing))
               WHERE org_actor_id=? AND status='active' AND role_key=? AND actor_id IN (SELECT to_actor_id FROM org_money WHERE day>? AND day<=?)""",
            (g, org, sp["dependent"], int(day) - period, int(day)))
        n += cur.rowcount
    return n


# ---- hidden lines and discipline ----

def _drive(conn: sqlite3.Connection, actor_id: int, trait: str, default: float = 0.5) -> float:
    r = conn.execute(f"SELECT {trait} FROM actor_drives WHERE actor_id=?", (int(actor_id),)).fetchone()
    return default if r is None or r[0] is None else float(r[0])


def discovery_chance(conn: sqlite3.Connection, holder: int, days: int = WEEK) -> float:
    """The chance that a hidden line is found over `days`: the per-period figure, scaled to the days, times one minus the
    holder's caution (caution is one minus his risk tolerance, so a bold man is caught more often)."""
    per = _v(conn, (_data(conn).get("hidden") or {}).get("discovery_period"), 0.0)
    period = _cache(conn)["period"]
    return per * (int(days) / period) * (1.0 - (1.0 - _drive(conn, holder, "risk_tolerance")))


def _disc(conn: sqlite3.Connection, which: str, key: str, default: float = 0.0) -> float:
    """A weight of the discipline of inducted (protected) men: the head's choice."""
    return _v(conn, ((_data(conn).get("discipline") or {}).get(which) or {}).get(key), default)


def _du(conn: sqlite3.Connection, which: str, key: str, default: float = 0.0) -> float:
    """A weight of the discipline of men who are not inducted (unprotected): their patron's choice."""
    return _v(conn, (((_data(conn).get("discipline") or {}).get("unprotected") or {}).get(which) or {}).get(key), default)


def _decider(conn: sqlite3.Connection, org: int, seat) -> int | None:
    """Who decides what is done to a man caught: the head for an inducted man (his sanction is needed to touch one); for
    anyone else his patron (his superior), else the unit leader over him, else the head."""
    head = head_of(conn, org)
    if seat["inducted_day"] is not None:
        return head
    sup = seat["superior_actor_id"]
    if sup is not None:
        ss = seat_of(conn, int(sup), org)
        if ss is not None and ss["status"] == "active" and is_living(conn, int(sup)):
            return int(sup)
    ul = orgs.unit_leader_of(conn, int(seat["actor_id"]), org)
    if ul is not None and ul != int(seat["actor_id"]) and is_living(conn, ul):
        return ul
    return head


def open_discipline(conn: sqlite3.Connection, org: int, holder: int, day: int, meta: dict) -> int | None:
    """Put a `discipline` item on the deciding man's list with the caught man as its subject; both are looked at tomorrow."""
    s = seat_of(conn, holder, org)
    decider = None if s is None else _decider(conn, org, s)
    if decider is None or decider == int(holder):
        return None
    aid = add_agenda(conn, decider, "discipline", int(day), subject_kind="actor", subject_id=int(holder),
                     metadata={**meta, "org": int(org), "holder": int(holder), "status": "protected" if s["inducted_day"] is not None else "unprotected"})
    imposed(conn, int(holder))
    imposed(conn, int(decider))
    return aid


def discover_hidden(conn: sqlite3.Connection, day: int) -> int:
    """Each hidden line may be found this week; whoever decides about its holder (`_decider`) gets `discipline`."""
    n = 0
    for ln in conn.execute("SELECT l.id,l.holder_actor_id,h.org_actor_id AS org FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id "
                           "WHERE l.hidden=1 AND l.status='active' ORDER BY l.id").fetchall():
        holder, org = ln["holder_actor_id"], int(ln["org"])
        head = head_of(conn, org)
        s = seat_of(conn, int(holder), org) if holder is not None else None
        if _spec(conn, org) is None or head is None or s is None or s["status"] != "active" or int(holder) == head:
            continue
        if org_motives._roll(conn, int(holder), int(day), "hidden_discovery") >= discovery_chance(conn, int(holder)):
            continue
        conn.execute("UPDATE org_lines SET hidden=0 WHERE id=?", (int(ln["id"]),))
        open_discipline(conn, org, int(holder), int(day), {"line": int(ln["id"]), "found": int(day)})
        _lose_standing(conn, s, _v(conn, _standing_data(conn).get("caught_loss")))  # being caught costs him face
        n += 1
    return n


def discipline_for_holdout(conn: sqlite3.Connection, actor_id: int, org: int, amount: float, since: int, incident: int, day: int) -> int | None:
    """A dependant noticed keeping money back: his patron gets `discipline` about him (no head's sanction is needed)."""
    if _spec(conn, org) is None or not _data(conn).get("discipline"):
        return None
    return open_discipline(conn, org, int(actor_id), int(day), {"amount": float(amount), "since": int(since), "incident": int(incident), "recovered": float(amount)})


def _skim(conn: sqlite3.Connection, meta: dict, day: int) -> tuple[float, float]:
    """(what was kept back, weeks it ran): a line's kick-up kept from above, or the money a dependant held out."""
    if meta.get("amount") is not None:
        return float(meta["amount"]), max(0.0, (int(day) - int(meta.get("since", day))) / WEEK)
    ln = conn.execute("SELECT * FROM org_lines WHERE id=?", (int(meta["line"]),)).fetchone() if meta.get("line") is not None else None
    return (0.0, 0.0) if ln is None else _kept_back(conn, ln, day)


def _kept_back(conn: sqlite3.Connection, ln, day: int) -> tuple[float, float]:
    """(what the line kept back from the men above, weeks it has been hidden): weekly take x weeks x the ladder shares."""
    h = _data(conn).get("hidden") or {}
    weeks = max(0.0, (int(day) - int(ln["started_day"])) / WEEK)
    return float(ln["weekly_take"]) * weeks * sum(_v(conn, k) for k in (h.get("fine_share") or [])), weeks


def _normal_week(conn: sqlite3.Connection, holder: int, day: int, unprotected: bool) -> float:
    """What the man normally moves in a week over the last four periods: the kick-up he passes up (inducted), or what he is
    paid (dependant); never below the floor figure."""
    d = _data(conn)
    span = 4 * _cache(conn)["period"]
    if unprotected:
        flow, col, floor = (d.get("discipline") or {}).get("unprotected", {}).get("earning_flow"), "to_actor_id", _du(conn, "kill", "normal_floor", 1.0)
    else:
        flow, col, floor = (d.get("hidden") or {}).get("fine_flow"), "from_actor_id", _disc(conn, "kill", "normal_floor", 1.0)
    got = conn.execute(f"SELECT COALESCE(SUM(amount),0) FROM org_money WHERE {col}=? AND kind=? AND day>? AND day<=?", (int(holder), flow, int(day) - span, int(day))).fetchone()[0]
    return max(float(got) / (span / WEEK), floor)


def _talk_risk(conn: sqlite3.Connection, holder: int, seat, day: int) -> float:
    """The risk that he talks: low loyalty, low reliability and police contact (held in the last year, or an open case naming
    him), each weighted by the package (`discipline.talk`)."""
    w = (_data(conn).get("discipline") or {}).get("talk") or {}
    police = 1.0 if (conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND since_day>? LIMIT 1", (int(holder), int(day) - 365)).fetchone()
                     or conn.execute("SELECT 1 FROM crime_reports WHERE offender_actor_id=? AND status='open' LIMIT 1", (int(holder),)).fetchone()) else 0.0
    return clamp01(_v(conn, w.get("loyalty")) * (1.0 - _drive(conn, int(holder), "loyalty")) + _v(conn, w.get("reliability")) * (1.0 - float(seat["reliability"]))
                   + _v(conn, w.get("police")) * police)


def _repeat(conn: sqlite3.Connection, item, org: int, holder: int) -> float:
    return 1.0 if conn.execute("SELECT 1 FROM org_agenda WHERE kind='discipline' AND subject_id=? AND status='resolved' AND id<? AND json_extract(metadata_json,'$.org')=? LIMIT 1",
                               (int(holder), int(item["id"]), int(org))).fetchone() else 0.0


def kill_weight(conn: sqlite3.Connection, item, org: int, holder: int, seat, decider: int, day: int) -> float:
    """How strongly the deciding man is drawn to killing the man caught. One blend with no gate: the size of the skim against
    what the man normally moves, how long it ran, whose money it hit (all of it the head's own when the man answers to him,
    otherwise the head's share of the ladder; for a dependant the patron's own money), how many know (the men under him, the
    crew), his standing, the decider's aggression, a repeat offence and, where the package gives a weight, the risk that he
    talks. A made man's weights (a negative base: killing him costs a sit-down and a break with the family) differ from an
    unprotected man's (`discipline.unprotected.kill`: no protection, so a much smaller cost)."""
    meta = _meta(item)
    prot = meta.get("status") != "unprotected"
    w = (lambda k, d=0.0: _disc(conn, "kill", k, d)) if prot else (lambda k, d=0.0: _du(conn, "kill", k, d))  # noqa: E731
    kept, weeks = _skim(conn, meta, day)
    size = clamp01(kept / (_normal_week(conn, holder, day, not prot) * 52.0) / w("size_scale", 1.0)) if kept > 0 else 0.0
    dur = clamp01(weeks / w("duration_weeks", 104.0))
    if prot:
        shares = [_v(conn, k) for k in ((_data(conn).get("hidden") or {}).get("fine_share") or [])]
        direct = seat["superior_actor_id"] is not None and int(seat["superior_actor_id"]) == int(decider)
        hit = 0.0 if meta.get("line") is None else (1.0 if direct or not shares or sum(shares) <= 0 else shares[-1] / sum(shares))
        under = conn.execute("SELECT COUNT(*) FROM org_seats WHERE superior_actor_id=? AND org_actor_id=? AND status='active'", (int(holder), int(org))).fetchone()[0]
    else:
        hit = 1.0 if seat["superior_actor_id"] is not None and int(seat["superior_actor_id"]) == int(decider) else 0.5
        under = conn.execute("SELECT COUNT(*) FROM org_seats WHERE superior_actor_id=? AND org_actor_id=? AND status='active' AND actor_id<>?", (int(seat["superior_actor_id"] or 0), int(org), int(holder))).fetchone()[0]
    face = clamp01(under / w("face_men", 5.0))
    talk = _talk_risk(conn, holder, seat, day) if w("talk") and (not prot or meta.get("reason") == "left") else 0.0  # a made man's talk risk weighs only when he left
    return (w("base") + w("size") * size + w("duration") * dur + w("hit_head") * hit + w("face") * face + w("aggression") * _drive(conn, int(decider), "aggression")
            + w("low_standing") * (1.0 - float(seat["standing"])) + w("repeat") * _repeat(conn, item, org, holder) + w("talk") * talk + (w("left") if meta.get("reason") == "left" else 0.0))


def _protected_offers(conn, actor_id, item, s, payload, org, holder, day):
    standing, greed = float(s["standing"]), float(s["greed"])
    xs = {"discipline_fine": _disc(conn, "fine", "base") + _disc(conn, "fine", "standing") * standing,
          "discipline_demote": _disc(conn, "demote", "base") + _disc(conn, "demote", "greed") * greed,
          "discipline_kill": kill_weight(conn, item, org, holder, s, int(actor_id), int(day))}
    why = {"discipline_fine": f"Fines {_name(conn, holder)} the kick-up he kept back.", "discipline_demote": f"Takes the line from {_name(conn, holder)}.",
           "discipline_kill": f"Has {_name(conn, holder)} killed for holding out."}
    return [{"kind": k, "utility": _utility(conn, x), "rationale": why[k], "payload": payload, **({"target_actor_id": holder, "risk": 0.8} if k == "discipline_kill" else {})}
            for k, x in xs.items()]


def _unprotected_offers(conn, actor_id, item, s, payload, org, holder, day):
    """What a patron does about a dependant caught skimming, with no head's sanction: make him pay it back with interest and a
    beating, cut him off, or kill him."""
    meta = _meta(item)
    kept, weeks = _skim(conn, meta, day)
    size = clamp01(kept / (_normal_week(conn, holder, day, True) * 52.0) / _du(conn, "kill", "size_scale", 1.0)) if kept > 0 else 0.0
    standing, rel = float(s["standing"]), float(s["reliability"])
    rep = _repeat(conn, item, org, holder)
    xs = {"discipline_pay_back": _du(conn, "pay_back", "base") + _du(conn, "pay_back", "small") * (1.0 - size) + _du(conn, "pay_back", "standing") * standing,
          "discipline_cut_off": _du(conn, "cut_off", "base") + _du(conn, "cut_off", "unreliable") * (1.0 - rel) + _du(conn, "cut_off", "repeat") * rep,
          "discipline_kill": kill_weight(conn, item, org, holder, s, int(actor_id), int(day))}
    why = {"discipline_pay_back": f"Makes {_name(conn, holder)} pay it back with interest, and beats him.", "discipline_cut_off": f"Cuts {_name(conn, holder)} off.",
           "discipline_kill": f"Has {_name(conn, holder)} killed for skimming."}
    return [{"kind": k, "utility": _utility(conn, x), "rationale": why[k], "payload": payload, **({"target_actor_id": holder, "risk": 0.6} if k == "discipline_kill" else {})}
            for k, x in xs.items()]


def _left_offers(conn, actor_id, item, s, payload, org, holder, day):
    """A man who left the organisation is not a clean exit: the head weighs killing him for what he might say, or letting him go."""
    watch = _utility(conn, _disc(conn, "watch", "base", 0.5))
    return [{"kind": "drop_discipline", "utility": watch, "rationale": f"Lets {_name(conn, holder)} go and keeps an eye on him.", "payload": payload},
            {"kind": "discipline_kill", "utility": _utility(conn, kill_weight(conn, item, org, holder, s, int(actor_id), int(day))), "target_actor_id": holder, "risk": 0.8,
             "rationale": f"Has {_name(conn, holder)} killed: he left, and he knows things.", "payload": payload}]


def discipline_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = _meta(item)
    org, holder = int(meta["org"]), int(meta["holder"])
    s = seat_of(conn, holder, org)
    payload = {"org": org, "line": meta.get("line"), "holder": holder, "status": meta.get("status"), "reason": meta.get("reason"),
               "amount": meta.get("amount"), "since": meta.get("since"), "recovered": meta.get("recovered")}
    left = meta.get("reason") == "left"
    if s is None or not is_living(conn, holder) or (s["status"] != "active" and not left):
        return [{"kind": "drop_discipline", "utility": _utility(conn, 1.0), "rationale": "The man is gone.", "payload": payload}]
    fn = _left_offers if left else _unprotected_offers if meta.get("status") == "unprotected" else _protected_offers
    return fn(conn, actor_id, item, s, payload, org, holder, int(day))


def _lose_standing(conn: sqlite3.Connection, seat, delta: float) -> None:
    conn.execute("UPDATE org_seats SET standing=? WHERE id=?", (clamp01(float(seat["standing"]) - delta), int(seat["id"])))


def execute_discipline_fine(conn, actor_id, kind, payload, day):
    org, holder, line = int(payload["org"]), int(payload["holder"]), int(payload["line"])
    _finish(conn, payload, day)
    h, ln, s = (_data(conn).get("hidden") or {}), conn.execute("SELECT * FROM org_lines WHERE id=?", (line,)).fetchone(), seat_of(conn, holder, org)
    if s is None or ln is None or not is_living(conn, holder):
        return {"summary": "There was no one to fine.", "blocked": True}
    weeks = max(0.0, (int(day) - int(ln["started_day"])) / WEEK)
    share = sum(_v(conn, k) for k in (h.get("fine_share") or []))
    owed = float(ln["weekly_take"]) * weeks * share * _v(conn, h.get("fine_multiple"), 1.0)
    flow = h.get("fine_flow")
    paid = 0.0
    if owed > 0.0 and flow:
        paid = ledger.transfer(conn, ("person", holder), ("person", int(actor_id)), owed,
                               flow_kind=_cache(conn)["ledger_kinds"][flow], purpose="a fine for a line kept back", allow_partial=True)
        if paid > 0.0:
            conn.execute("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,line_id,amount,org_actor_id) VALUES (?,?,?,?,?,?,?)",
                         (int(day), flow, holder, int(actor_id), line, paid, org))
    _lose_standing(conn, s, _disc(conn, "fine", "standing_loss"))
    adjust_relationship(conn, holder, int(actor_id), int(day), resentment_delta=_disc(conn, "fine", "resentment"), fear_delta=_disc(conn, "fine", "fear"))
    imposed(conn, holder)  # a fine is something done to him
    imposed(conn, int(actor_id))
    return {"summary": f"{_name(conn, actor_id)} fined {_name(conn, holder)} ${paid:,.0f} for the line he kept back."}


def execute_discipline_demote(conn, actor_id, kind, payload, day):
    org, holder, line = int(payload["org"]), int(payload["holder"]), int(payload["line"])
    _finish(conn, payload, day)
    s = seat_of(conn, holder, org)
    if s is None or not is_living(conn, holder):
        return {"summary": "There was no one to demote.", "blocked": True}
    taker = orgs.unit_leader_of(conn, holder, org)
    taker = int(actor_id) if taker is None or taker == holder else taker
    conn.execute("UPDATE org_lines SET holder_actor_id=? WHERE id=? AND holder_actor_id=?", (taker, line, holder))
    _lose_standing(conn, s, _disc(conn, "demote", "standing_loss"))
    adjust_relationship(conn, holder, int(actor_id), int(day), resentment_delta=_disc(conn, "demote", "resentment"), respect_delta=-_disc(conn, "demote", "respect"))
    imposed(conn, holder)  # his line is taken
    imposed(conn, taker)
    imposed(conn, int(actor_id))
    return {"summary": f"{_name(conn, actor_id)} took the line from {_name(conn, holder)} and gave it to {_name(conn, taker)}."}


def execute_discipline_pay_back(conn, actor_id, kind, payload, day):
    """The dependant pays back with interest and is beaten (a non-fatal harm through the harm system); his standing and his
    feelings toward the man who did it take the hit."""
    from .harm import record_harm
    org, holder = int(payload["org"]), int(payload["holder"])
    _finish(conn, payload, day)
    s = seat_of(conn, holder, org)
    if s is None or not is_living(conn, holder):
        return {"summary": "There was no one to make pay.", "blocked": True}
    kept, _weeks = _skim(conn, {k: payload.get(k) for k in ("amount", "since", "line")}, int(day))
    owed = max(0.0, kept * (1.0 + _du(conn, "pay_back", "interest")) - float(payload.get("recovered") or 0.0))
    flow, paid = (_data(conn).get("hidden") or {}).get("fine_flow"), 0.0
    if owed > 0.0 and flow:
        paid = ledger.transfer(conn, ("person", holder), ("person", int(actor_id)), owed, flow_kind=_cache(conn)["ledger_kinds"][flow],
                               purpose="what he skimmed, with interest", allow_partial=True)
        if paid > 0.0:
            conn.execute("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,line_id,amount,org_actor_id) VALUES (?,?,?,?,?,?,?)",
                         (int(day), flow, holder, int(actor_id), payload.get("line"), paid, org))
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (holder,)).fetchone()
    record_harm(conn, holder, source_kind="org_action", source_ref_id=int(day) * 10_000_000 + int(actor_id), severity=_du(conn, "pay_back", "beating"),
                intent_class="hostile", location_id=loc[0] if loc else None, metadata={"offender_actor_id": int(actor_id), "public": False})
    _lose_standing(conn, s, _du(conn, "pay_back", "standing_loss"))
    adjust_relationship(conn, holder, int(actor_id), int(day), resentment_delta=_du(conn, "pay_back", "resentment"), fear_delta=_du(conn, "pay_back", "fear"),
                        loyalty_delta=-_du(conn, "pay_back", "loyalty"))
    imposed(conn, holder)
    imposed(conn, int(actor_id))
    return {"summary": f"{_name(conn, actor_id)} made {_name(conn, holder)} pay back ${paid:,.0f} and beat him."}


def execute_discipline_cut_off(conn, actor_id, kind, payload, day):
    """The dependant is dropped: sometimes another crew of the organisation takes him (at the bottom), otherwise he is out of
    the life (the seat goes `out`; he keeps his record)."""
    from .org_lifecycle import leave_life
    org, holder = int(payload["org"]), int(payload["holder"])
    _finish(conn, payload, day)
    s = seat_of(conn, holder, org)
    if s is None or s["status"] != "active":
        return {"summary": "There was no one to cut off.", "blocked": True}
    rng = random.Random(f"{run_seed(conn)}:cutoff:{holder}:{int(day)}")
    others = [int(r[0]) for r in conn.execute("SELECT id FROM org_units WHERE org_actor_id=? AND id<>? AND leader_actor_id IS NOT NULL ORDER BY id", (org, int(s["unit_id"] or 0))).fetchall()]
    if others and rng.random() < _du(conn, "cut_off", "rehome"):
        unit = others[rng.randrange(len(others))]
        sp = _spec(conn, org)
        patron = conn.execute("SELECT s.actor_id FROM org_seats s WHERE s.unit_id=? AND s.status='active' AND s.role_key=? AND s.inducted_day IS NOT NULL ORDER BY (SELECT COUNT(*) FROM org_seats d "
                              "WHERE d.superior_actor_id=s.actor_id AND d.status='active'), s.actor_id LIMIT 1", (unit, sp["member"])).fetchone()
        sup = int(patron[0]) if patron else int(conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (unit,)).fetchone()[0])
        conn.execute("UPDATE org_seats SET unit_id=?, superior_actor_id=?, standing=0 WHERE id=?", (unit, sup, int(s["id"])))
        imposed(conn, holder)
        imposed(conn, int(actor_id))
        return {"summary": f"{_name(conn, actor_id)} cut {_name(conn, holder)} off; another crew took him on at the bottom."}
    leave_life(conn, holder, org, int(day))
    imposed(conn, int(actor_id))
    return {"summary": f"{_name(conn, actor_id)} cut {_name(conn, holder)} off; he is out of the life."}


def execute_discipline_kill(conn, actor_id, kind, payload, day):
    from .outfit_choices import kill
    holder = int(payload["holder"])
    _finish(conn, payload, day)
    if not is_living(conn, holder):
        return {"summary": "The man was already dead.", "blocked": True}
    imposed(conn, int(actor_id))
    return {"summary": kill(conn, int(actor_id), holder, int(day), sanctioned=True, fallible=True)}


def execute_drop_discipline(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    return {"summary": "Nothing more was done."}


# ---- the weekly hook and the vacancy hook ----

def _after_vacancy(conn: sqlite3.Connection, org: int, seat, day: int, why: str) -> None:
    """An inducted man gone may open the books (the head weighs it). One who walked away (`out`) is not a clean exit: the head
    gets `discipline` about him and weighs the risk that he talks; an unprotected man leaving stays low-key."""
    if seat["inducted_day"] is None or _spec(conn, org) is None:
        return
    after_gone(conn, org, int(day))
    if why == "out" and _data(conn).get("discipline") and not conn.execute("SELECT 1 FROM org_agenda WHERE kind='exiled' AND actor_id=? AND subject_id=?", (int(seat["actor_id"]), int(org))).fetchone():
        open_discipline(conn, org, int(seat["actor_id"]), int(day), {"reason": "left"})


def _weekly(conn: sqlite3.Connection, day: int) -> dict:
    if not _data(conn):
        return {}
    out = {"expired": expire_stale(conn, day), "caught": discover_hidden(conn, day), "standing": grow_standing(conn, day), "moved": move_standing(conn, day), "replaced": replace_dependants(conn, day)}
    out["books"] = sum(1 for org, _sp in _orgs(conn) if after_gone(conn, org, day, immediate=False))
    out["unusual"] = flag_unusual(conn, day)
    return out


on_vacancy(None, _after_vacancy)
on_week(_weekly)
for _kind, _fn in (("ask_for_names", execute_ask_for_names), ("no_name", execute_no_name),
                   ("propose_member", execute_propose_member), ("decline_member", execute_decline_member), ("make_member", execute_make_member),
                   ("discipline_fine", execute_discipline_fine), ("discipline_demote", execute_discipline_demote), ("discipline_pay_back", execute_discipline_pay_back), ("discipline_cut_off", execute_discipline_cut_off),
                   ("discipline_kill", execute_discipline_kill), ("drop_discipline", execute_drop_discipline)):
    register_executor(_kind, _fn)
for _kind, _fn in (("open_books", books_offers), ("propose_member", proposal_offers), ("make_member", make_offers), ("discipline", discipline_offers)):
    register_agenda_action(_kind, _fn)
```

## engine/org_succession.py

```python
"""Who holds the posts of an organisation, decided by men (generic layer, driven by the package's data; names no role).

Three things live here; `org_coup` holds the violent half (plots, coups, civil war, a split) and calls `install_head` below.

  appointments  A vacant unit-leader post is filled by the head, a name for the books is put forward by the unit leader: each
                a weighed choice on the man's agenda (`fill_unit_leader_seat`, `propose_member`), one offer per man, weighed on
                trust, kin, favours owed, money offered, merit and fear, bent by the chooser's temperament (`appoint`).
  the heir      A head holds a succession preference (an open `heir` agenda row, formed from his temperament and his
                relationships, revised over time). It is private until he shows it (the leaders and the rivals then react).
                A head who names nobody leaves the contest open.
  the contest   A vacant head seat (any cause but a coup, see org_coup) opens a `contest` row that plays out over weeks: the
                customary roles stand (weighted) and any ambitious man with standing may; every backer (unit leaders and the roles
                the data lists) backs one candidate each week on trust, kin, debts, fear, money and the late head's heir; outside
                organisations' heads weigh in; the outcome is agreed, forced (fear), bought (money), a killing, or civil war.
                An acting head holds the seat meanwhile.

Everything is data (`orgs.json` kind `lifecycle`: `appoint`, `heir`, `contest`, ...); a number or the key of a design figure.
A kind with no `contest` data keeps the older formula in `org_lifecycle._promote`.
"""
from __future__ import annotations

import json
import math
import sqlite3

from . import ledger, org_motives, orgs
from .org_choices import register_agenda_action, register_executor
from .org_lifecycle import fill_post, mark_for_history, membership_text, on_head_vacancy, on_post_vacancy, on_return, on_unit_vacancy, on_week, role_level, unit_pool
from .orgs import add_agenda, clamp01, head_of, imposed, is_living, kind_rules, seat_of
from .relationships import adjust_relationship

WEEK = 7
_KIN = ("spouse", "parent_of", "grandparent_of", "sibling_of", "child_of")


# ---- reading the package's data ----

def lifecycle(conn: sqlite3.Connection, org: int) -> dict:
    return orgs.kind_rules(conn, int(org)).get("lifecycle") or {}


def block(conn: sqlite3.Connection, org: int, name: str) -> dict:
    return lifecycle(conn, org).get(name) or {}


def v(conn: sqlite3.Connection, spec) -> float:
    """A number as written, or the run's value of the design figure it names. A figure the data does not give fails loudly:
    no number is hidden in code."""
    if spec is None:
        raise KeyError("a figure this layer needs is missing from the package's lifecycle data")
    if isinstance(spec, (int, float)) and not isinstance(spec, bool):
        return float(spec)
    x = org_motives._fig(conn, str(spec))
    if x is None:
        raise KeyError(f"design figure {spec!r} is not in the package's figures")
    return float(x)


def lean(conn: sqlite3.Connection, org: int, x: float) -> float:
    """A trait bends a rate or a weight around a floor: floor + trait (the floor is the kind's lifecycle `trait_floor`)."""
    return v(conn, lifecycle(conn, org)["trait_floor"]) + x


def name_of(conn: sqlite3.Connection, actor_id: int | None) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone() if actor_id is not None else None
    return str(r[0]) if r else "someone"


def roll(conn: sqlite3.Connection, actor: int, day: int, stream: str) -> float:
    """The one point where a seeded draw is made (org_motives._roll, which tests patch)."""
    return org_motives._roll(conn, int(actor), int(day), stream)


def pick(conn: sqlite3.Connection, actor: int, day: int, stream: str, items: list[tuple], temp: float):
    """One of (item, score) drawn with weight exp(score / temp) from one seeded draw; None for an empty list."""
    if not items:
        return None
    top = max(s for _i, s in items)
    ws = [math.exp((s - top) / max(1e-6, temp)) for _i, s in items]
    x = roll(conn, actor, day, stream) * sum(ws)
    for (item, _s), w in zip(items, ws):
        x -= w
        if x < 0:
            return item
    return items[-1][0]


def _utility(conn: sqlite3.Connection, x: float) -> float:
    return float(org_motives._fig(conn, "org_choice_utility_base", default=8.0)) + float(org_motives._fig(conn, "org_choice_utility_span", default=10.0)) * clamp01(x)


def rel(conn: sqlite3.Connection, a: int | None, b: int | None):
    if a is None or b is None:
        return None
    return conn.execute("SELECT * FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(a), int(b))).fetchone()


def drive(conn: sqlite3.Connection, actor_id: int, trait: str, org: int | None = None) -> float:
    if trait in ("greed", "reliability"):
        r = conn.execute(f"SELECT {trait} FROM org_seats WHERE actor_id=? ORDER BY (org_actor_id=?) DESC, id LIMIT 1", (int(actor_id), int(org or 0))).fetchone()
    else:
        r = conn.execute(f"SELECT {trait} FROM actor_drives WHERE actor_id=?", (int(actor_id),)).fetchone()
    return 0.5 if r is None or r[0] is None else float(r[0])


def active_seat(conn: sqlite3.Connection, actor_id: int | None, org: int):
    if actor_id is None:
        return None
    s = seat_of(conn, int(actor_id), org)
    return s if s is not None and s["status"] == "active" and is_living(conn, int(actor_id)) else None


def meta_of(row) -> dict:
    return json.loads(row["metadata_json"] or "{}")


def save_meta(conn: sqlite3.Connection, row_id: int, meta: dict) -> None:
    conn.execute("UPDATE org_agenda SET metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), int(row_id)))


def put_row(conn: sqlite3.Connection, actor: int, kind: str, day: int, subject: int | None, meta: dict, subject_kind: str = "actor") -> int:
    """An agenda row that is state, not a task for the man: no speed-up, no review of him (the weekly passes read it)."""
    return int(conn.execute(
        "INSERT INTO org_agenda(actor_id,kind,due_day,subject_kind,subject_id,created_day,metadata_json) VALUES (?,?,?,?,?,?,?)",
        (int(actor), kind, int(day), subject_kind, subject, int(day), json.dumps(meta, sort_keys=True))).lastrowid)


def close_row(conn: sqlite3.Connection, row_id: int, day: int, **extra) -> None:
    if extra:
        r = conn.execute("SELECT metadata_json FROM org_agenda WHERE id=?", (int(row_id),)).fetchone()
        save_meta(conn, row_id, {**json.loads(r[0] or "{}"), **extra})
    conn.execute("UPDATE org_agenda SET status='resolved', resolved_day=? WHERE id=?", (int(day), int(row_id)))


def contest_orgs(conn: sqlite3.Connection) -> list[int]:
    return [int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_profiles ORDER BY org_actor_id") if block(conn, int(r[0]), "contest")]


# ---- weighing a man (appointments, the heir, backing in a contest) ----
TERMS: dict = {}


def term(name: str):
    def deco(fn):
        TERMS[name] = fn
        return fn
    return deco


@term("trust")
def _t_trust(conn, org, a, c, day, ctx, blk):
    r = rel(conn, a, c)
    return 0.0 if r is None else clamp01((float(r["trust"]) + float(r["loyalty"])) / 200.0)


@term("kin")
def _t_kin(conn, org, a, c, day, ctx, blk):
    return 1.0 if conn.execute(
        "SELECT 1 FROM typed_relationship_facts WHERE status='active' AND relation_type IN (%s) AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)) LIMIT 1"
        % ",".join("?" * len(_KIN)), (*_KIN, int(a), int(c), int(c), int(a))).fetchone() else 0.0


@term("favour")
def _t_favour(conn, org, a, c, day, ctx, blk):
    r = rel(conn, a, c)
    return 0.0 if r is None else clamp01(float(r["obligation"]) / 100.0)  # what he (the chooser) owes the man


@term("money")
def _t_money(conn, org, a, c, day, ctx, blk):
    """What the man could put up: his purse x the share he would offer x his ambition, against the scale."""
    m = blk.get("money") or {}
    return clamp01(ledger.balance(conn, ("person", int(c))) * v(conn, m.get("share")) * drive(conn, int(c), "ambition") / max(1e-9, v(conn, m.get("scale"))))


@term("merit")
def _t_merit(conn, org, a, c, day, ctx, blk):
    if ctx.get("merit") is not None:
        return ctx["merit"](c)
    s = seat_of(conn, int(c), org)
    if s is None:
        return 0.0
    m = blk.get("merit") or {}
    ws, wy = v(conn, m.get("w_standing")), v(conn, m.get("w_years"))
    yrs = 0.0 if s["inducted_day"] is None else min(1.0, max(0.0, (int(day) - int(s["inducted_day"])) / 365.0) / max(1e-9, v(conn, m.get("years_cap"))))
    return (ws * float(s["standing"]) + wy * yrs) / max(1e-9, ws + wy)


@term("fear")
def _t_fear(conn, org, a, c, day, ctx, blk):
    r = rel(conn, a, c)
    return 0.0 if r is None else clamp01(float(r["fear"]) / 100.0)  # he fears the man


@term("cowed")
def _t_cowed(conn, org, a, c, day, ctx, blk):
    r = rel(conn, c, a)
    return 0.0 if r is None else clamp01(float(r["fear"]) / 100.0)  # the man fears him


@term("heir")
def _t_heir(conn, org, a, c, day, ctx, blk):
    return 1.0 if ctx.get("heir") is not None and int(ctx["heir"]) == int(c) else 0.0


@term("own")
def _t_own(conn, org, a, c, day, ctx, blk):
    return 1.0 if int(a) == int(c) else 0.0


@term("customary")
def _t_customary(conn, org, a, c, day, ctx, blk):
    return clamp01((ctx.get("customary") or {}).get(int(c), 0.0))


@term("muscle")
def _t_muscle(conn, org, a, c, day, ctx, blk):
    """In a war: the men under him against the men of the organisation, and his temper."""
    if not ctx.get("war"):
        return 0.0
    total = conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND status='active'", (int(org),)).fetchone()[0] or 1
    under = len(_under(conn, org, int(c)))
    crew = v(conn, blk["muscle_crew"])
    return clamp01(crew * under / total * v(conn, blk["muscle_scale"]) + (1.0 - crew) * drive(conn, int(c), "aggression"))


@term("resentment")
def _t_resentment(conn, org, a, c, day, ctx, blk):
    r = rel(conn, a, c)
    return 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0)


@term("tainted")
def _t_tainted(conn, org, a, c, day, ctx, blk):
    return 1.0 if ctx.get("tainted") is not None and int(ctx["tainted"]) == int(c) else 0.0


def _under(conn: sqlite3.Connection, org: int, man: int) -> list[int]:
    """Everyone below him in the chain of command (active seats)."""
    seen: set[int] = set()
    todo = [int(man)]
    while todo:
        cur = todo.pop()
        for (a,) in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND superior_actor_id=?", (int(org), cur)):
            if int(a) not in seen and int(a) != int(man):
                seen.add(int(a))
                todo.append(int(a))
    return sorted(seen)


def weigh(conn: sqlite3.Connection, org: int, chooser: int, cand: int, day: int, blk: dict, ctx: dict | None = None, *, detail: bool = False):
    """How much the chooser is drawn to the candidate, 0..1: the weighted mean of the block's `weights` terms (each a design
    figure or number), less the block's `against` terms. The chooser's temperament bends each term's weight: `temperament`
    maps a term to a trait (a drive, or the seat's greed or reliability); the bend is `temperament.weight` x (trait - 0.5) x 2.
    With `detail`, returns (score, {term: its weighted contribution}) for the rationale."""
    ctx = ctx or {}
    temper = blk.get("temperament") or {}
    bend = v(conn, temper["weight"]) if temper else 0.0
    num = den = 0.0
    parts: dict[str, float] = {}
    for key, spec in (blk.get("weights") or {}).items():
        w = v(conn, spec)
        fn = TERMS.get(key)
        if w <= 0.0 or fn is None:
            continue
        if bend and temper.get(key):
            w *= max(0.1, 1.0 + bend * (drive(conn, int(chooser), temper[key], org) - 0.5) * 2.0)
        m = w * clamp01(fn(conn, org, int(chooser), int(cand), int(day), ctx, blk))
        parts[key] = m
        num += m
        den += w
    neg = 0.0
    for key, spec in (blk.get("against") or {}).items():
        fn = TERMS.get(key)
        if fn is not None and v(conn, spec) > 0.0:
            neg += v(conn, spec) * clamp01(fn(conn, org, int(chooser), int(cand), int(day), ctx, blk))
    score = clamp01(num / den - neg) if den else 0.0
    return (score, parts) if detail else score


def lead_terms(parts: dict[str, float], n: int = 2) -> str:
    return ", ".join(k for k, x in sorted(parts.items(), key=lambda kv: -kv[1])[:n] if x > 0)


# ---- appointments ----

def paid_for(conn: sqlite3.Connection, org: int, chooser: int, cand: int, day: int, blk: dict) -> float:
    """The man chosen pays what he offered (a share of his purse, by his ambition), through the ledger and the money rows;
    he is then owed the post and the chooser is owed nothing: the chooser's obligation to him falls, his rises."""
    m = blk.get("money") or {}
    if not m:
        return 0.0
    offer = ledger.balance(conn, ("person", int(cand))) * v(conn, m.get("share")) * drive(conn, int(cand), "ambition")
    if offer <= 0.0 or not m.get("flow"):
        return 0.0
    kinds = org_motives._sphere_data(conn)  # ledger kinds come from the package's organisation data
    from .world_package import org_rules, package_for
    lk = org_rules(package_for(conn))["ledger_kinds"][m["flow"]]
    paid = ledger.transfer(conn, ("person", int(cand)), ("person", int(chooser)), offer, flow_kind=lk, purpose="what he paid for the post", allow_partial=True)
    if paid > 0.0:
        conn.execute("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,line_id,amount,org_actor_id) VALUES (?,?,?,?,?,?,?)",
                     (int(day), m["flow"], int(cand), int(chooser), None, paid, int(org)))
    return paid


def after_choice(conn: sqlite3.Connection, org: int, chooser: int, chosen: int, passed: list[int], day: int, blk: dict) -> None:
    """The man chosen trusts and owes the chooser; the men passed over resent him (more if they stood higher in the weighing)."""
    if int(chosen) != int(chooser):  # a head who names himself has no one to thank
        adjust_relationship(conn, chosen, chooser, int(day), trust_delta=v(conn, blk.get("chosen_trust")), loyalty_delta=v(conn, blk.get("chosen_loyalty")),
                            obligation_delta=v(conn, blk.get("chosen_obligation")))
    for p in passed:
        if int(p) == int(chooser):
            continue
        adjust_relationship(conn, int(p), chooser, int(day), resentment_delta=v(conn, blk.get("passed_resentment")))
        imposed(conn, int(p))
    imposed(conn, int(chosen))


def appointment_offers(conn: sqlite3.Connection, head: int, item, day: int) -> list[dict] | None:
    """One offer for each man of the vacant unit the head could name; None when the package has no `appoint` data for the
    organisation (the caller then keeps the older single offer)."""
    meta = meta_of(item)
    org, unit = int(meta.get("org") or 0), int(item["subject_id"])
    blk = block(conn, org, "appoint")
    if not blk:
        return None
    pool = unit_pool(conn, unit, int(day))
    if not pool:
        return [{"kind": "fill_unit_leader_seat", "utility": _utility(conn, 1.0), "rationale": "No one in the unit is fit; the seat is filled as it can be.", "payload": {"unit_id": unit}}]
    out = []
    for r in pool:
        a = int(r["actor_id"])
        sc, parts = weigh(conn, org, int(head), a, int(day), blk, detail=True)
        lead = lead_terms(parts)
        out.append({"kind": "fill_unit_leader_seat", "utility": _utility(conn, sc), "target_actor_id": a,
                    "rationale": f"Names {name_of(conn, a)} to lead the unit ({sc:.2f}{', mostly ' + lead if lead else ''}).", "payload": {"unit_id": unit, "candidate": a, "org": org}})
    return out


def after_appointment(conn: sqlite3.Connection, org: int, chooser: int, chosen: int, unit: int, day: int) -> None:
    blk = block(conn, org, "appoint")
    if not blk or chosen is None:
        return
    paid_for(conn, org, chooser, chosen, int(day), blk)
    after_choice(conn, org, chooser, int(chosen), [int(r["actor_id"]) for r in unit_pool(conn, unit, int(day)) if int(r["actor_id"]) != int(chosen)], int(day), blk)


def seat_the_unit(conn: sqlite3.Connection, org: int, unit: int, day: int, *, deciding: int | None = None) -> bool:
    """Put the choice of a unit's leader on the deciding man's list (the head's, else the acting head's); False when no one
    can decide it."""
    head = deciding if deciding is not None else head_of(conn, org)
    if head is None or not is_living(conn, head) or not block(conn, org, "appoint"):
        return False
    if conn.execute("SELECT 1 FROM org_agenda WHERE kind='fill_unit_leader_seat' AND status='open' AND subject_id=? AND json_extract(metadata_json,'$.org')=? LIMIT 1", (int(unit), int(org))).fetchone():
        return True
    delay = int(v(conn, block(conn, org, "appoint").get("delay_days")))
    add_agenda(conn, head, "fill_unit_leader_seat", int(day) + delay, subject_kind="unit", subject_id=int(unit), metadata={"org": int(org)})
    return True


def _unit_vacancy(conn: sqlite3.Connection, org: int, seat, day: int, why: str) -> bool:
    """A unit leader's seat fell vacant: when the unit already has a living leader there is nothing to do; else the head's list."""
    if not block(conn, org, "appoint"):
        return False
    cur = conn.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (int(seat["unit_id"]),)).fetchone()
    role = kind_rules(conn, org).get("unit_leader")
    if cur is not None and cur[0] is not None and int(cur[0]) != int(seat["actor_id"]):
        s = active_seat(conn, int(cur[0]), org)
        if s is not None and s["role_key"] == role:
            return True
    return seat_the_unit(conn, org, int(seat["unit_id"]), int(day))


def stuck_units(conn: sqlite3.Connection, day: int) -> int:
    """A unit with no living leader and nothing on anyone's list gets the choice put to the head; an item that sat open past
    the fallback time (the head is gone or never answers) is closed and the unit takes the older best-man rule, so no unit is
    leaderless for ever."""
    from .org_lifecycle import fill_unit_leader
    n = 0
    for (org,) in conn.execute("SELECT org_actor_id FROM org_profiles ORDER BY org_actor_id").fetchall():
        blk = block(conn, int(org), "appoint")
        role = kind_rules(conn, int(org)).get("unit_leader")
        if not blk or not role:
            continue
        fall = int(v(conn, blk.get("fallback_days")))
        for u in conn.execute("SELECT id,leader_actor_id FROM org_units WHERE org_actor_id=? AND status='active'", (int(org),)).fetchall():
            s = active_seat(conn, u["leader_actor_id"], int(org)) if u["leader_actor_id"] is not None else None
            if s is not None and s["role_key"] == role:
                continue
            item = conn.execute("SELECT id,due_day FROM org_agenda WHERE kind='fill_unit_leader_seat' AND status='open' AND subject_id=? AND json_extract(metadata_json,'$.org')=?",
                                (int(u["id"]), int(org))).fetchone()
            if item is not None and int(day) - int(item["due_day"]) < fall:
                continue
            if item is None and conn.execute("SELECT 1 FROM org_seats WHERE unit_id=? AND status='active' LIMIT 1", (int(u["id"]),)).fetchone() is None:
                continue
            if item is None and seat_the_unit(conn, int(org), int(u["id"]), int(day)):
                n += 1
                continue
            if item is not None:
                close_row(conn, int(item["id"]), int(day))
            n += 1 if fill_unit_leader(conn, int(u["id"]), int(day), force=True) is not None else 0
    return n


# ---- posts below the head: the head chooses among the men the data names ----

def _post_vacancy(conn: sqlite3.Connection, org: int, role: str, day: int) -> bool:
    """A post with a succession in the data fell vacant: put the choice on the head's list (the acting head's while a contest runs).
    False when the package gives no `appoint` data, there is no head to choose, or the head is not living."""
    prefs = (lifecycle(conn, org).get("succession") or {}).get(role)
    head = head_of(conn, org)
    blk = block(conn, org, "appoint")
    if not prefs or not blk or head is None or not is_living(conn, head):
        return False
    if any(meta_of(r).get("role") == role for r in conn.execute("SELECT * FROM org_agenda WHERE kind='fill_post' AND status='open' AND subject_id=?", (int(org),))):
        return True
    add_agenda(conn, head, "fill_post", int(day) + int(v(conn, blk["delay_days"])), subject_kind="org", subject_id=int(org), metadata={"org": int(org), "role": role})
    return True


def post_offers(conn: sqlite3.Connection, head: int, item, day: int) -> list[dict]:
    """One offer for each man of the roles the data lists as successors to the vacant post, weighed on the `appoint` terms and
    on how far down the data's list his role is (`post_order_decay` per place)."""
    meta = meta_of(item)
    org, role = int(meta["org"]), str(meta["role"])
    blk = block(conn, org, "appoint")
    prefs = (lifecycle(conn, org).get("succession") or {}).get(role) or []
    decay = v(conn, blk["post_order_decay"])
    cust: dict[int, float] = {}
    for i, pref in enumerate(prefs):
        for r in orgs.members(conn, org, pref):
            if is_living(conn, int(r["actor_id"])) and int(r["actor_id"]) != int(head):
                cust.setdefault(int(r["actor_id"]), decay ** i)
    payload = {"org": org, "role": role}
    if not cust:
        return [{"kind": "fill_post", "utility": _utility(conn, 1.0), "rationale": f"No one is fit for the vacant {_label(conn, org, role)}'s post.", "payload": payload}]
    out = []
    for a in sorted(cust):
        sc, parts = weigh(conn, org, int(head), a, int(day), blk, {"customary": cust}, detail=True)
        lead = lead_terms(parts)
        out.append({"kind": "fill_post", "utility": _utility(conn, sc), "target_actor_id": a,
                    "rationale": f"Names {name_of(conn, a)} {_label(conn, org, role)} ({sc:.2f}{', mostly ' + lead if lead else ''}).", "payload": {**payload, "candidate": a}})
    return out


def execute_fill_post(conn: sqlite3.Connection, actor_id: int, kind: str, payload: dict, day: int) -> dict:
    from .org_lifecycle import _promote
    org, role = int(payload["org"]), str(payload["role"])
    if payload.get("agenda_id") is not None:
        orgs.resolve_agenda(conn, int(payload["agenda_id"]), int(day))
    cand = payload.get("candidate")
    new = _promote(conn, org, role, int(day), chosen=cand)
    if new is None:
        return {"summary": "No one could take the post.", "blocked": True}
    blk = block(conn, org, "appoint")
    if cand is not None and blk:
        prefs = (lifecycle(conn, org).get("succession") or {}).get(role) or []
        passed = [int(r["actor_id"]) for pref in prefs for r in orgs.members(conn, org, pref) if int(r["actor_id"]) not in (int(new), int(actor_id))]
        paid_for(conn, org, int(actor_id), int(new), int(day), blk)
        after_choice(conn, org, int(actor_id), int(new), passed, int(day), blk)
    return {"summary": f"{name_of(conn, actor_id)} named {name_of(conn, new)} {_label(conn, org, role)}."}


def stuck_posts(conn: sqlite3.Connection, day: int) -> int:
    """A vacant post nobody put on a head's list, or whose item sat unanswered past the fallback time (no head, or one who never
    answers), is filled by the data's formula so no post stays empty for ever."""
    from .org_lifecycle import _promote
    n = 0
    for (org,) in conn.execute("SELECT org_actor_id FROM org_profiles ORDER BY org_actor_id").fetchall():
        blk = block(conn, int(org), "appoint")
        succ = lifecycle(conn, int(org)).get("succession") or {}
        if not blk or not succ:
            continue
        fall = int(v(conn, blk["fallback_days"]))
        for item in conn.execute("SELECT * FROM org_agenda WHERE kind='fill_post' AND status='open' AND subject_id=?", (int(org),)).fetchall():
            if int(day) - int(item["due_day"]) >= fall:
                close_row(conn, int(item["id"]), int(day))
                n += 1 if _promote(conn, int(org), str(meta_of(item)["role"]), int(day)) is not None else 0
    return n


# ---- the heir ----

def heir_row(conn: sqlite3.Connection, head: int):
    return conn.execute("SELECT * FROM org_agenda WHERE actor_id=? AND kind='heir' AND status='open' ORDER BY id DESC LIMIT 1", (int(head),)).fetchone()


def heir_of(conn: sqlite3.Connection, org: int, head: int, *, shown_only: bool = False) -> int | None:
    """The man the head holds as his heir while he is living and still seated; None when he names nobody."""
    r = heir_row(conn, head)
    if r is None or (shown_only and not meta_of(r).get("shown")):
        return None
    return int(r["subject_id"]) if active_seat(conn, int(r["subject_id"]), org) is not None else None


def customary(conn: sqlite3.Connection, org: int, exclude: tuple = ()) -> dict[int, float]:
    """The men of the roles the data names as the usual successors, each with the role's weight."""
    out: dict[int, float] = {}
    for role, spec in (block(conn, org, "contest").get("customary") or {}).items():
        w = v(conn, spec)
        for s in orgs.members(conn, org, role):
            if int(s["actor_id"]) not in exclude and is_living(conn, int(s["actor_id"])):
                out[int(s["actor_id"])] = max(out.get(int(s["actor_id"]), 0.0), w)
    return out


def ambitious(conn: sqlite3.Connection, org: int, exclude: tuple = ()) -> list[int]:
    """Inducted men with standing and ambition enough to want the seat though no custom names them."""
    a = block(conn, org, "contest").get("ambitious") or {}
    if not a:
        return []
    return [int(r[0]) for r in conn.execute(
        """SELECT s.actor_id FROM org_seats s JOIN actor_drives d ON d.actor_id=s.actor_id WHERE s.org_actor_id=? AND s.status='active' AND s.inducted_day IS NOT NULL
             AND s.standing>=? AND d.ambition>=? ORDER BY s.actor_id""", (int(org), v(conn, a.get("standing")), v(conn, a.get("ambition")))).fetchall()
            if int(r[0]) not in exclude and is_living(conn, int(r[0]))]


def candidates(conn: sqlite3.Connection, org: int, exclude: tuple = ()) -> dict[int, float]:
    """Everyone who could hold the head's seat: the customary men and the ambitious (weight 0 for the latter's custom)."""
    out = customary(conn, org, exclude)
    for a in ambitious(conn, org, exclude):
        out.setdefault(a, 0.0)
    return out


def _age_factor(conn: sqlite3.Connection, head: int, blk: dict, day: int) -> float:
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (int(head),)).fetchone()
    if r is None or r[0] is None:
        return 0.5
    age = (int(day) - int(r[0])) / 365.0
    return clamp01((age - v(conn, blk.get("age_from"))) / max(1e-9, v(conn, blk.get("age_span"))))


def form_heir(conn: sqlite3.Connection, org: int, head: int, day: int, *, force: bool = False) -> int | None:
    """The head settles on a man (or on no one): the candidates weighed by him on the `heir` block; a man below the `min_score`
    is no one's choice. Returns the heir's id, None when he names nobody."""
    blk = block(conn, org, "heir")
    cust = candidates(conn, org, exclude=(int(head),))
    scores = [(c, weigh(conn, org, head, c, int(day), blk, {"customary": cust})) for c in sorted(cust)]
    old = heir_row(conn, head)
    if old is not None:
        close_row(conn, int(old["id"]), int(day))
    scores = [(c, s) for c, s in scores if s >= v(conn, blk.get("min_score"))]
    chosen = pick(conn, head, int(day), "heir_pick", scores, v(conn, blk.get("pick_temp")))
    if chosen is None:
        return None
    shown = bool(old is not None and int(old["subject_id"]) == chosen and meta_of(old).get("shown"))
    put_row(conn, head, "heir", int(day), int(chosen), {"org": int(org), "shown": shown, "formed": int(day), "score": dict(scores).get(chosen)})
    return int(chosen)


def show_heir(conn: sqlite3.Connection, org: int, head: int, day: int) -> None:
    """The head makes his choice visible (he tells the unit leaders): they trust the heir more or less by their own temper, the
    men who would have wanted the seat are passed over, and all of them are looked at again."""
    r = heir_row(conn, head)
    if r is None:
        return
    blk = block(conn, org, "heir")
    heir = int(r["subject_id"])
    save_meta(conn, int(r["id"]), {**meta_of(r), "shown": True, "shown_day": int(day)})
    cust = candidates(conn, org, exclude=(int(head), heir))
    for b in backers(conn, org):
        if b in (heir, head):
            continue
        adjust_relationship(conn, b, heir, int(day), trust_delta=v(conn, blk.get("show_trust")) * lean(conn, org, drive(conn, b, "loyalty")),
                            respect_delta=v(conn, blk.get("show_respect")))
        if b in cust:
            adjust_relationship(conn, b, heir, int(day), resentment_delta=v(conn, blk.get("show_resentment")) * lean(conn, org, drive(conn, b, "ambition")))
            imposed(conn, b)
    imposed(conn, heir)
    mark_for_history(conn, head, f"showed {name_of(conn, heir)} as his heir", int(day))


def _heirs(conn: sqlite3.Connection, day: int) -> dict:
    formed = shown = 0
    for org in contest_orgs(conn):
        head = head_of(conn, org)
        blk = block(conn, org, "heir")
        if head is None or not blk or not is_living(conn, head):
            continue
        row = heir_row(conn, head)
        if row is not None and active_seat(conn, int(row["subject_id"]), org) is None:
            close_row(conn, int(row["id"]), int(day), why="gone")
            row = None
        floor = v(conn, blk.get("age_floor"))
        age = floor + (1.0 - floor) * _age_factor(conn, head, blk, day)
        if row is None:
            if roll(conn, head, int(day), "heir_form") < v(conn, blk.get("form_week")) * age and form_heir(conn, org, head, int(day)) is not None:
                formed += 1
            row = heir_row(conn, head)
            if row is None:
                continue
        if roll(conn, head, int(day), "heir_revise") < v(conn, blk.get("revise_week")):
            before = int(row["subject_id"])
            if form_heir(conn, org, head, int(day)) not in (None, before):
                formed += 1
            row = heir_row(conn, head)
            if row is None:
                continue
        if not meta_of(row).get("shown") and roll(conn, head, int(day), "heir_show") < v(conn, blk.get("show_week")) * age:
            show_heir(conn, org, head, int(day))
            shown += 1
    return {"heirs": formed, "heirs_shown": shown}


# ---- the contest ----

def backers(conn: sqlite3.Connection, org: int) -> list[int]:
    """The men who back a candidate: the unit leaders and the roles the data lists, living and seated."""
    blk = block(conn, org, "contest")
    roles = set(blk.get("backer_roles") or []) | {kind_rules(conn, org).get("unit_leader")}
    return [int(s["actor_id"]) for r in sorted(r for r in roles if r) for s in orgs.members(conn, org, r) if is_living(conn, int(s["actor_id"]))]


def backer_weight(conn: sqlite3.Connection, org: int, b: int, blk: dict) -> float:
    """A backer counts for more the more men stand behind him (his crew), up to the data's cap."""
    return 1.0 + v(conn, blk.get("crew_weight")) * min(1.0, len(_under(conn, org, b)) / max(1e-9, v(conn, blk.get("crew_scale"))))


def _label(conn: sqlite3.Connection, org: int, role: str) -> str:
    return str((kind_rules(conn, org).get("labels") or {}).get(role, role))


def _cause(conn: sqlite3.Connection, late: int, org: int, why: str) -> dict:
    """How the head went: killed by an insider, killed by someone of another organisation, or none of those (law, illness,
    accident, leaving, custody)."""
    row = conn.execute("SELECT subject_id FROM org_agenda WHERE kind='killed_by' AND actor_id=? ORDER BY id DESC LIMIT 1", (int(late),)).fetchone()
    killer = int(row[0]) if row is not None and row[0] is not None else None
    if killer is None:
        h = conn.execute("SELECT json_extract(metadata_json,'$.offender_actor_id') FROM harm_incidents WHERE actor_id=? AND json_extract(metadata_json,'$.offender_actor_id') IS NOT NULL "
                         "ORDER BY id DESC LIMIT 1", (int(late),)).fetchone()
        killer = int(h[0]) if h is not None and h[0] is not None else None
    if killer is None or why != "dead":
        return {"kind": why, "killer": None}
    inside = conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (killer, int(org))).fetchone() is not None
    return {"kind": "killed_inside" if inside else "killed_outside", "killer": killer}


def set_acting(conn: sqlite3.Connection, org: int, man: int, late: int, day: int, contest_id: int | None) -> None:
    """The man holds the head's seat while the contest runs: his seat takes the head role (his unit and lines stay), the men who
    answered to the late head answer to him, and a marker remembers the role he held."""
    rules = kind_rules(conn, org)
    s = seat_of(conn, man, org)
    put_row(conn, man, "acting_head", int(day), int(org), {"org": int(org), "prior_role": s["role_key"], "prior_superior": s["superior_actor_id"], "late": int(late), "contest": contest_id}, "org")
    conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=NULL WHERE id=?", (rules["head"], int(s["id"])))
    conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND status='active' AND superior_actor_id=? AND actor_id<>?", (man, int(org), int(late), man))
    membership_text(conn, org, man, rules["head"])
    lv = role_level(conn, org, rules["head"])
    if lv is not None:
        orgs.set_level(conn, man, lv, int(day), org)
    imposed(conn, man)
    mark_for_history(conn, man, f"took the {_label(conn, org, rules['head'])}'s seat for now", int(day))


def acting_marker(conn: sqlite3.Connection, org: int):
    return conn.execute("SELECT * FROM org_agenda WHERE kind='acting_head' AND status='open' AND subject_id=? ORDER BY id DESC LIMIT 1", (int(org),)).fetchone()


def step_back(conn: sqlite3.Connection, org: int, marker, new_head: int | None, day: int) -> None:
    """The acting man goes back to the role he held; the men who answered to him answer to the head."""
    m = meta_of(marker)
    a = int(marker["actor_id"])
    s = seat_of(conn, a, org)
    if s is not None and s["status"] == "active" and new_head != a:
        conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=? WHERE id=?", (m["prior_role"], new_head, int(s["id"])))
        membership_text(conn, org, a, m["prior_role"])
        lv = role_level(conn, org, m["prior_role"])
        if lv is not None:
            orgs.set_level(conn, a, lv, int(day), org)
        if new_head is not None:
            conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND status='active' AND superior_actor_id=? AND actor_id NOT IN (?,?)", (new_head, int(org), a, new_head, a))
        imposed(conn, a)
    close_row(conn, int(marker["id"]), int(day))


def install_head(conn: sqlite3.Connection, org: int, man: int, day: int, how: str) -> int:
    """The man holds the head's seat: any acting man steps back, the men who answered to the late head and the acting man answer
    to him; if he led a unit it is put to him to name its leader, and the post he left is filled as the data says."""
    rules = kind_rules(conn, org)
    head_role, unit_role = rules["head"], rules.get("unit_leader")
    seat = seat_of(conn, man, org)
    marker = acting_marker(conn, org)
    prior_role = None
    if marker is not None:
        if int(marker["actor_id"]) == int(man):
            prior_role = meta_of(marker)["prior_role"]
            close_row(conn, int(marker["id"]), int(day))
        else:
            step_back(conn, org, marker, int(man), int(day))
    late_ids = [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key=? AND status<>'active'", (int(org), head_role))]
    if seat["role_key"] != head_role:
        prior_role = seat["role_key"]
        if prior_role == unit_role and seat["unit_id"]:
            seat_the_unit(conn, org, int(seat["unit_id"]), int(day), deciding=int(man))
            conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=NULL WHERE id=?", (head_role, int(seat["id"])))
        else:
            conn.execute("UPDATE org_seats SET role_key=?, unit_id=NULL, superior_actor_id=NULL WHERE id=?", (head_role, int(seat["id"])))
    else:
        conn.execute("UPDATE org_seats SET superior_actor_id=NULL WHERE id=?", (int(seat["id"]),))
    # a man sitting in the head's seat when another is installed (one seated by a contest while a war ran, say) does not stay head beside him:
    # he goes back to the role the data gives a man who lost the seat, and those who answered to him answer to the new head
    back = (kind_rules(conn, org).get("lifecycle") or {}).get("returns_as")
    if back and back != head_role:
        for other in conn.execute("SELECT id,actor_id FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active' AND actor_id<>?", (int(org), head_role, int(man))).fetchall():
            conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=? WHERE id=?", (back, int(man), int(other[0])))
            membership_text(conn, org, int(other[1]), back)
            lv = role_level(conn, org, back)
            if lv is not None:
                orgs.set_level(conn, int(other[1]), lv, int(day), org)
            late_ids.append(int(other[1]))
            imposed(conn, int(other[1]))
    if late_ids:
        conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND status='active' AND superior_actor_id IN (%s) AND actor_id<>?" % ",".join("?" * len(late_ids)),
                     (int(man), int(org), *late_ids, int(man)))
    membership_text(conn, org, man, head_role)
    lv = role_level(conn, org, head_role)
    if lv is not None:
        orgs.set_level(conn, man, lv, int(day), org)
    imposed(conn, man)
    for (sub,) in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND superior_actor_id=?", (int(org), int(man))).fetchall():
        imposed(conn, int(sub))
    mark_for_history(conn, man, f"rose to {_label(conn, org, head_role)}", int(day))
    if prior_role and prior_role != head_role:
        fill_post(conn, org, prior_role, int(day))
    for late in late_ids:
        r = heir_row(conn, late)
        if r is not None:
            close_row(conn, int(r["id"]), int(day), succeeded_by=int(man), how=how)
    return int(man)


def _acting_choice(conn: sqlite3.Connection, org: int, cust: dict[int, float], blk: dict) -> int:
    """Who holds the seat meanwhile when no heir is shown: the man with the heaviest custom, then standing (`acting_standing`)."""
    w = v(conn, blk.get("acting_standing"))
    return int(sorted(cust.items(), key=lambda kv: (-(kv[1] + w * float(seat_of(conn, kv[0], org)["standing"])), kv[0]))[0][0])


def open_contest(conn: sqlite3.Connection, org: int, seat, day: int, why: str) -> bool:
    """The head's seat is vacant: a contest opens (False when the package has no contest data, or nobody could stand: the
    older formula then fills the seat)."""
    blk = block(conn, org, "contest")
    late = int(seat["actor_id"])
    if not blk:
        return False
    cust = candidates(conn, org, exclude=(late,))
    if not cust:
        return False
    live = conn.execute("SELECT * FROM org_agenda WHERE kind='contest' AND status='open' AND actor_id=? ORDER BY id DESC LIMIT 1", (int(org),)).fetchone()
    if live is not None:  # the acting head went too: the contest goes on with a new acting man
        mk = acting_marker(conn, org)
        if mk is not None and int(mk["actor_id"]) == late:
            close_row(conn, int(mk["id"]), int(day))
        set_acting(conn, org, _acting_choice(conn, org, cust, blk), late, int(day), int(live["id"]))
        return True
    cause = _cause(conn, late, org, why)
    heir = heir_of(conn, org, late)
    heir_r = heir_row(conn, late)
    shown = bool(heir_r is not None and meta_of(heir_r).get("shown"))
    meta = {"org": int(org), "late": late, "opened": int(day), "cause": cause["kind"], "killer": cause["killer"], "heir": heir, "heir_shown": shown, "stood": [],
            "picks": {}, "forced": 0, "bought": 0, "killed": 0, "war": cause["kind"] == "killed_outside"}
    cid = put_row(conn, int(org), "contest", int(day), late, meta, "actor")
    if cause["kind"] == "killed_inside":
        from . import org_coup
        if org_coup.coup(conn, org, late, int(cause["killer"]), cid, int(day)):
            return True
    acting = heir if heir is not None and shown else _acting_choice(conn, org, cust, blk)
    set_acting(conn, org, int(acting), late, int(day), cid)
    for a in {int(acting)} | ({heir} if heir is not None and shown else set()):
        imposed(conn, a)
    if cause["kind"] == "killed_outside":
        from .org_happenings import killed_across
        killed_across(conn, int(cause["killer"]), late, [seat], int(day))
    mark_for_history(conn, late, f"left the {_label(conn, org, kind_rules(conn, org)['head'])}'s seat vacant", int(day))
    return True


def _stand(conn: sqlite3.Connection, org: int, meta: dict, blk: dict, day: int, cid: int) -> dict[int, float]:
    """Who stands this week: those who stood before and are still living and seated, the acting man, the shown heir, and any
    customary or ambitious man whose draw passes (his custom weight and his ambition)."""
    cust = candidates(conn, org, exclude=(int(meta["late"]),))
    marker = acting_marker(conn, org)
    must = {int(marker["actor_id"])} if marker is not None else set()
    if meta.get("heir") is not None and meta.get("heir_shown"):
        must.add(int(meta["heir"]))
    stood = {a for a in meta["stood"] if active_seat(conn, a, org) is not None} | {a for a in must if active_seat(conn, a, org) is not None}
    for a, w in sorted(cust.items()):
        if a in stood:
            continue
        amb = drive(conn, a, "ambition")
        want = (w if w > 0.0 else v(conn, blk["ambitious"]["stand"])) * lean(conn, org, amb)
        if roll(conn, a, int(day), f"stand:{cid}") < v(conn, blk.get("stand_week")) * want:
            stood.add(a)
    meta["stood"] = sorted(stood)
    return {a: cust.get(a, 0.0) for a in stood}


def _ctx(meta: dict, cust: dict[int, float], tainted: int | None = None) -> dict:
    return {"heir": meta.get("heir"), "customary": cust, "war": bool(meta.get("war")), "tainted": tainted}


def outside_heads(conn: sqlite3.Connection, org: int) -> list[int]:
    """The heads of the other organisations of the same kind."""
    kind = conn.execute("SELECT org_kind FROM org_profiles WHERE org_actor_id=?", (int(org),)).fetchone()[0]
    return [int(r[0]) for r in conn.execute(
        "SELECT s.actor_id FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id WHERE s.org_actor_id<>? AND p.org_kind=? AND s.role_key=? AND s.status='active' ORDER BY s.actor_id",
        (int(org), kind, kind_rules(conn, org)["head"]))]


def outside_liking(conn: sqlite3.Connection, head: int, cand: int) -> float:
    """How much another outfit's head likes a man: trust and respect less resentment, 0..1."""
    r = rel(conn, int(head), int(cand))
    return 0.0 if r is None else clamp01((float(r["trust"]) + float(r["respect"])) / 200.0 - float(r["resentment"]) / 200.0)


def early(conn: sqlite3.Connection, weeks: float, scale, floor) -> float:
    """How far a young matter has got: `floor` at its start, rising to 1 as the weeks pass (1 - exp(-weeks / scale)). A quick
    agreement, war or settlement is unlikely in the first days but never impossible."""
    f = v(conn, floor)
    return f + (1.0 - f) * (1.0 - math.exp(-max(0.0, weeks) / v(conn, scale)))


def men_lost(conn: sqlite3.Connection, org: int, since: int) -> int:
    """Men of the organisation killed since a day (the `killed_by` rows)."""
    return int(conn.execute("SELECT COUNT(*) FROM org_agenda a WHERE a.kind='killed_by' AND a.created_day>=? AND EXISTS "
                            "(SELECT 1 FROM org_seats s WHERE s.actor_id=a.actor_id AND s.org_actor_id=?)", (int(since), int(org))).fetchone()[0])


def law_heat(conn: sqlite3.Connection, org: int) -> int:
    """Open cases against the organisation's inducted men."""
    return int(conn.execute("SELECT COUNT(*) FROM crime_reports r JOIN org_seats s ON s.actor_id=r.offender_actor_id WHERE r.status='open' AND s.org_actor_id=? AND s.inducted_day IS NOT NULL",
                            (int(org),)).fetchone()[0])


def pressure(conn: sqlite3.Connection, org: int, press: dict, *, opened: int, day: int, typical, spent: float, leaders: list[int]) -> float:
    """The weighted mean (0..1) of what presses a matter to an end: weariness (1 - exp(-weeks / typical): the typical duration only
    shapes the curve and ends nothing), the money spent, the men lost since it began, law heat, the other outfits' heads who like a
    front-runner (they want it settled), and the leaders' even tempers. Each weight and scale is the data's."""
    w = press["weights"]
    weeks = (int(day) - int(opened)) / WEEK
    heads = outside_heads(conn, org)
    base = v(conn, press["outside_base"])  # the neighbours' own interest in a settled house, whoever they like
    parts = {"weary": 1.0 - math.exp(-weeks / v(conn, typical)),
             "money": clamp01(float(spent) / v(conn, press["money_scale"])),
             "men": clamp01(men_lost(conn, org, opened) / v(conn, press["men_scale"])),
             "law": clamp01(law_heat(conn, org) / v(conn, press["heat_scale"])),
             "outside": (sum(clamp01(base + max(outside_liking(conn, h, c) for c in leaders)) for h in heads) / len(heads)) if heads and leaders else 0.0,
             "temper": 1.0 - (sum(drive(conn, c, "aggression") for c in leaders) / len(leaders) if leaders else 0.0)}
    den = sum(v(conn, w[k]) for k in parts)
    return sum(v(conn, w[k]) * x for k, x in parts.items()) / den


def tally(conn: sqlite3.Connection, org: int, meta: dict, blk: dict, cands: dict[int, float], day: int, cid: int) -> dict[int, float]:
    """Each backer backs one candidate (weighed; the one he backed last week is favoured by `stick`); the heads of other
    organisations add a voice for the man they like. Returns each candidate's share of the backing, 0..1."""
    ctx = _ctx(meta, cands, meta.get("tainted"))
    picks, weight = {}, {}
    for b in backers(conn, org):
        w = backer_weight(conn, org, b, blk)
        sc = [(c, weigh(conn, org, b, c, int(day), blk, ctx) + (v(conn, blk.get("stick")) if meta["picks"].get(str(b)) == c else 0.0)) for c in sorted(cands)]
        got = pick(conn, b, int(day), f"back:{cid}", sc, v(conn, blk.get("pick_temp")))
        if got is not None:
            picks[str(b)], weight[b] = got, w
    out_w = v(conn, blk["outside"]["weight"])
    voice, bs = None, v(conn, blk["outside"]["min"])
    for oh in outside_heads(conn, org):
        for c in cands:
            x = outside_liking(conn, oh, c)
            if x > bs:
                voice, bs = c, x
    total = sum(weight.values()) + (out_w if voice is not None else 0.0)
    meta["picks"] = picks
    share = {c: 0.0 for c in cands}
    for b, c in picks.items():
        share[c] += weight[int(b)] / total if total else 0.0
    if voice is not None and total:
        share[voice] += out_w / total
    return share


def _lean(conn: sqlite3.Connection, org: int, meta: dict, blk: dict, share: dict[int, float], day: int, cid: int) -> None:
    """The leaders lean on the men who back someone else: a hard man frightens them, a rich man pays them; the effect is on the
    relationships the next week's weighing reads (fear, obligation)."""
    ranked = sorted(share.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
    for c, _s in ranked:
        swing = [int(b) for b, p in meta["picks"].items() if int(p) != c and int(b) != c]
        if not swing:
            continue
        b = swing[int(roll(conn, c, int(day), f"lean_who:{cid}") * len(swing)) % len(swing)]
        if roll(conn, c, int(day), f"force:{cid}") < v(conn, blk.get("force_week")) * drive(conn, c, "aggression"):
            adjust_relationship(conn, b, c, int(day), fear_delta=v(conn, blk.get("force_fear")), resentment_delta=v(conn, blk.get("force_resentment")))
            meta["forced"] += 1
            meta.setdefault("forced_by", []).append(c)
            imposed(conn, b)
        if roll(conn, c, int(day), f"bribe:{cid}") < v(conn, blk.get("bribe_week")) * drive(conn, c, "ambition"):
            pay = ledger.balance(conn, ("person", c)) * v(conn, blk.get("bribe_share"))
            if pay > 0.0:
                from .world_package import org_rules, package_for
                lk = org_rules(package_for(conn))["ledger_kinds"][blk["bribe_flow"]]
                got = ledger.transfer(conn, ("person", c), ("person", b), pay, flow_kind=lk, purpose="what he paid for a man's backing", allow_partial=True)
                if got > 0.0:
                    adjust_relationship(conn, b, c, int(day), obligation_delta=v(conn, blk.get("bribe_obligation")))
                    meta["bought"] += 1
                    meta["spent"] = float(meta.get("spent", 0.0)) + got
                    meta.setdefault("bought_by", []).append(c)
                    imposed(conn, b)


def _finish_contest(conn: sqlite3.Connection, row, meta: dict, winner: int | None, outcome: str, day: int) -> None:
    org = int(meta["org"])
    if winner is not None:
        loser_backers = [int(b) for b, p in meta["picks"].items() if int(p) != winner]
        blk = block(conn, org, "contest")
        for b in loser_backers:
            if b != winner:
                adjust_relationship(conn, b, winner, int(day), resentment_delta=v(conn, blk.get("lose_resentment")))
        for b in [int(b) for b, p in meta["picks"].items() if int(p) == winner and int(b) != winner]:
            adjust_relationship(conn, b, winner, int(day), loyalty_delta=v(conn, blk.get("win_loyalty")))
        install_head(conn, org, winner, int(day), outcome)
        for b in meta["picks"]:
            imposed(conn, int(b))  # backers of the winner and of the men who lost: all looked at again
        rv = lifecycle(conn, org).get("rivals")
        for rival in meta.get("stood", []):
            if int(rival) != int(winner) and rv and active_seat(conn, int(rival), org) is not None:
                add_agenda(conn, int(winner), "rival", int(day) + int(v(conn, rv["delay_days"])), subject_kind="actor", subject_id=int(rival), metadata={"org": org, "rival": int(rival), "how": outcome})
    close_row(conn, int(row["id"]), int(day), **{**meta, "outcome": outcome, "winner": winner, "closed": int(day), "weeks": (int(day) - int(meta["opened"])) // WEEK})


def agree_chance(conn: sqlite3.Connection, org: int, meta: dict, blk: dict, ranked: list, day: int) -> float:
    """The chance that the contest ends in agreement this week: the weekly figure x the early factor (thin while the matter is
    young) x the front-runner's clarity (his share and his lead) mixed with the pressure to end it (weariness, money, men lost, law
    heat, outside pressure, even tempers). Never zero for long: weariness only rises."""
    ag = blk["agree"]
    s1 = ranked[0][1]
    s2 = ranked[1][1] if len(ranked) > 1 else 0.0
    clear = v(conn, ag["w_share"]) * s1 + (1.0 - v(conn, ag["w_share"])) * clamp01((s1 - s2) / v(conn, ag["lead_scale"]))
    press = pressure(conn, org, ag["press"], opened=meta["opened"], day=day, typical=ag["typical_weeks"], spent=float(meta.get("spent", 0.0)), leaders=[c for c, _s in ranked[:2]])
    weeks = (int(day) - int(meta["opened"])) / WEEK
    return v(conn, ag["week"]) * early(conn, weeks, ag["early_weeks"], ag["early_floor"]) * clamp01(v(conn, ag["w_clear"]) * clear + v(conn, ag["w_press"]) * press)


def tick_contest(conn: sqlite3.Connection, row, day: int) -> str | None:
    """One week of one contest. Returns its outcome when it ends (agreed, forced, bought, killing, civil_war, no_one). Nothing ends
    it by the calendar: each week an agreement has a chance (the front-runner's clarity and the pressure to end it, thinned while the
    matter is young), and so has a war (two real sides, bitter claimants, thinned while it is young)."""
    meta = meta_of(row)
    org, cid = int(meta["org"]), int(row["id"])
    blk = block(conn, org, "contest")
    weeks = (int(day) - int(meta["opened"])) / WEEK
    cands = _stand(conn, org, meta, blk, day, cid)
    if not cands:
        _finish_contest(conn, row, meta, None, "no_one", day)
        return "no_one"
    share = tally(conn, org, meta, blk, cands, day, cid)
    ranked = sorted(share.items(), key=lambda kv: (-kv[1], kv[0]))
    lead, s1 = ranked[0]
    s2 = ranked[1][1] if len(ranked) > 1 else 0.0
    _lean(conn, org, meta, blk, share, day, cid)
    chance = agree_chance(conn, org, meta, blk, ranked, int(day))
    if roll(conn, org, int(day), f"agree:{cid}") < chance:
        # the label names how the winner got there: leaning on men, paying them, a killing on the way, or plain agreement
        out = "forced" if lead in meta.get("forced_by", []) else "bought" if lead in meta.get("bought_by", []) else "killing" if meta["killed"] else "agreed"
        _finish_contest(conn, row, meta, lead, out, day)
        return out
    for c in sorted(cands):  # a candidate losing ground may have the man in front killed
        if c != lead and share.get(c, 0.0) < s1 and roll(conn, c, int(day), f"cut:{cid}") < v(conn, blk["kill_week"]) * drive(conn, c, "aggression") * drive(conn, c, "ambition") * (s1 - share.get(c, 0.0)):
            from .outfit_choices import kill
            kill(conn, c, lead, int(day), sanctioned=False, fallible=True)
            if not is_living(conn, lead):  # a man who lives is still the man in front: the contest is undecided and goes on next week
                meta["killed"] += 1
            break
    if len(ranked) > 1:
        from . import org_coup
        wr = blk["war"]
        tension = org_coup.tension(conn, org, [lead, ranked[1][0]])
        p_war = v(conn, wr["week"]) * early(conn, weeks, wr["early_weeks"], wr["early_floor"]) * tension * clamp01(s2 / v(conn, wr["ref_share"]))
        if roll(conn, org, int(day), f"war:{cid}") < p_war:
            _finish_contest(conn, row, meta, None, "civil_war", day)
            org_coup.start_civil_war(conn, org, [lead, ranked[1][0]], int(day), cause="contest", late=int(meta["late"]))
            return "civil_war"
    save_meta(conn, cid, meta)
    return None


def _contests(conn: sqlite3.Connection, day: int) -> dict:
    out = {"contests": 0}
    for row in conn.execute("SELECT * FROM org_agenda WHERE kind='contest' AND status='open' ORDER BY id").fetchall():
        tick_contest(conn, row, int(day))
        out["contests"] += 1
    return out


def _returned(conn: sqlite3.Connection, org: int, man: int, day: int) -> bool:
    """A head who was held and is released while his contest still runs takes his seat back; the acting man steps back."""
    row = conn.execute("SELECT * FROM org_agenda WHERE kind='contest' AND status='open' AND subject_id=? AND actor_id=?", (int(man), int(org))).fetchone()
    if row is None:
        return False
    marker = acting_marker(conn, org)
    if marker is not None:
        step_back(conn, org, marker, int(man), int(day))
    close_row(conn, int(row["id"]), int(day), outcome="returned")
    return True


def _weekly(conn: sqlite3.Connection, day: int) -> dict:
    if not contest_orgs(conn) and not any(block(conn, int(r[0]), "appoint") for r in conn.execute("SELECT org_actor_id FROM org_profiles")):
        return {}
    out = {"stuck": stuck_units(conn, int(day)) + stuck_posts(conn, int(day))}
    out.update(_heirs(conn, int(day)))
    out.update(_contests(conn, int(day)))
    from . import org_coup
    for k, n in (org_coup.weekly(conn, int(day)) or {}).items():
        out[k] = out.get(k, 0) + n
    return out


# ---- choices on the agenda (the GM sees them) ----

def _name(conn, a):
    return name_of(conn, a)


on_unit_vacancy(_unit_vacancy)
on_post_vacancy(_post_vacancy)
register_executor("fill_post", execute_fill_post)
register_agenda_action("fill_post", post_offers)
on_head_vacancy(lambda conn, org, seat, day, why: open_contest(conn, org, seat, day, why))
on_return(_returned)
on_week(_weekly)
```

## engine/org_coup.py

```python
"""The violent half of a succession (generic layer, driven by the package's data; names no role or organisation).

  plots       Before any vacancy an ambitious, backed man may plot against the living head (or against a head's shown heir): he
              sounds out the backers one by one (a `plot` agenda row holds who joined, refused, or went to the head), the plot
              can leak, and with enough backing and the nerve he strikes. Rare, temperament-driven, never scheduled.
  coups       The head killed by one of his own men (`coup`, called when the contest opens): with the backing of the unit leaders
              (set up beforehand in a plot, or the weights of the moment) he takes over and the loyalists accept him, are bought,
              or are removed; without it the factions go to war, or the loyalists kill him, or the contest runs with the stain
              on him.
  civil war   An internal war between factions that form along the unit leaders' relationships (`civil_war` agenda row): killings,
              defections and money, ending in a win (the losers killed, demoted or absorbed), a settlement, or a split.
  a split     The losing faction leaves as a new organisation of the same kind: its men, units, lines and holdings move to a new
              institution built through the ordinary org tables.

Every weight and rate is the package's data (`lifecycle.coup`, `.plot`, `.civil_war`, `.split`): a number or a design figure.
"""
from __future__ import annotations

import json
import math
import sqlite3

from . import ledger, org_motives, orgs
from .org_choices import register_agenda_action, register_executor
from .org_lifecycle import fill_post, leave_life, mark_for_history, membership_text, role_level
from .org_succession import (WEEK, active_seat, after_choice, backer_weight, backers, block, candidates, close_row, contest_orgs, drive, early, heir_of, install_head,
                             lean, meta_of, name_of, pick, pressure, put_row, rel, roll, save_meta, seat_the_unit, set_acting, acting_marker, v, weigh)
from .orgs import add_agenda, clamp01, head_of, imposed, is_living, kind_rules, seat_of
from .relationships import adjust_relationship


def _utility(conn: sqlite3.Connection, x: float) -> float:
    return float(org_motives._fig(conn, "org_choice_utility_base", default=8.0)) + float(org_motives._fig(conn, "org_choice_utility_span", default=10.0)) * clamp01(x)


def _pay(conn: sqlite3.Connection, src: int, dst: int, amount: float, flow: str | None, purpose: str) -> float:
    from .world_package import org_rules, package_for
    if amount <= 0.0:
        return 0.0
    lk = org_rules(package_for(conn))["ledger_kinds"][flow]
    return ledger.transfer(conn, ("person", int(src)), ("person", int(dst)), amount, flow_kind=lk, purpose=purpose, allow_partial=True)


def temper(conn: sqlite3.Connection, org: int, actor: int) -> float:
    """A man's own aggression, 0..1 (his outfit has no number of its own: the men differ, and the heads' drives are drawn around the package's guideline)."""
    return clamp01(drive(conn, int(actor), "aggression"))


def _kill(conn: sqlite3.Connection, killer: int, victim: int, day: int, sanctioned: bool = True) -> bool:
    """A killing the coup and contest code carries out. It can fail (the package's `internal.land` and the planned-hit rate decide), and the
    caller handles a survivor: he lives, hurt or not, knowing who tried. True when the man is dead."""
    from .outfit_choices import kill
    if is_living(conn, victim):
        kill(conn, int(killer), int(victim), int(day), sanctioned=sanctioned, fallible=True)
    return not is_living(conn, victim)


def tension(conn: sqlite3.Connection, org: int, leaders: list[int]) -> float:
    """How bitter two claimants are: their resentment of each other against their tempers, 0..1 (the share of bitterness is the data's)."""
    a, b = int(leaders[0]), int(leaders[1])
    r1, r2 = rel(conn, a, b), rel(conn, b, a)
    bitter = ((float(r1["resentment"]) if r1 else 0.0) + (float(r2["resentment"]) if r2 else 0.0)) / 200.0
    w = v(conn, block(conn, org, "civil_war")["tension_bitter"])
    return clamp01(w * clamp01(bitter) + (1.0 - w) * (drive(conn, a, "aggression") + drive(conn, b, "aggression")) / 2.0)


# ---- plots against a living head (or his heir) ----

def _plot_row(conn: sqlite3.Connection, plotter: int, target: int | None = None):
    q, a = "SELECT * FROM org_agenda WHERE kind='plot' AND status='open' AND actor_id=?", [int(plotter)]
    if target is not None:
        q += " AND subject_id=?"
        a.append(int(target))
    return conn.execute(q + " ORDER BY id DESC LIMIT 1", a).fetchone()


def _plotters(conn: sqlite3.Connection, org: int, blk: dict, head: int) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        """SELECT s.actor_id FROM org_seats s JOIN actor_drives d ON d.actor_id=s.actor_id WHERE s.org_actor_id=? AND s.status='active' AND s.inducted_day IS NOT NULL
             AND s.actor_id<>? AND s.standing>=? AND d.ambition>=? ORDER BY s.actor_id""", (int(org), int(head), v(conn, blk.get("min_standing")), v(conn, blk.get("min_ambition")))).fetchall()
            if not _plot_row(conn, int(r[0]))]


def start_chance(conn: sqlite3.Connection, org: int, p: int, target: int, head: int, day: int, blk: dict) -> float:
    """The weekly chance that the man starts a plot against the target: the rate x his ambition x how little he is bound to the
    target (loyalty) x what drives him (resentment of the target; the head's showing another man as his heir) x his nerve."""
    r = rel(conn, p, target)
    resent = 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0)
    loyal = 0.0 if r is None else clamp01(float(r["loyalty"]) / 100.0)
    heir = heir_of(conn, org, head, shown_only=True)
    blocked = 1.0 if heir is not None and heir != p and target == head else 0.0
    push = clamp01(v(conn, blk.get("w_resentment")) * resent + v(conn, blk.get("w_blocked")) * blocked)
    rate = v(conn, blk.get("heir_rate" if target != head else "start_week"))
    return rate * drive(conn, p, "ambition") * (1.0 - loyal) * push * lean(conn, org, drive(conn, p, "risk_tolerance"))


def start_plot(conn: sqlite3.Connection, org: int, plotter: int, target: int, day: int) -> int:
    imposed(conn, plotter)
    return put_row(conn, int(plotter), "plot", int(day), int(target), {"org": int(org), "started": int(day), "joined": [], "refused": [], "sounded": []})


def _respond(conn: sqlite3.Connection, org: int, blk: dict, s: int, p: int, target: int, day: int) -> str:
    """One man sounded out: he joins (trust in the plotter, fear of him, a favour owed, his own ambition against his loyalty to
    the target), refuses and keeps quiet, or goes to the head."""
    r_sp, r_st = rel(conn, s, p), rel(conn, s, target)
    trust = 0.0 if r_sp is None else clamp01((float(r_sp["trust"]) + float(r_sp["loyalty"])) / 200.0)
    fear = 0.0 if r_sp is None else clamp01(float(r_sp["fear"]) / 100.0)
    owed = 0.0 if r_sp is None else clamp01(float(r_sp["obligation"]) / 100.0)
    loyal = 0.0 if r_st is None else clamp01(float(r_st["loyalty"]) / 100.0)
    rel_s = float(seat_of(conn, s, org)["reliability"])
    r = blk.get("respond") or {}
    join = v(conn, r.get("join_base")) + v(conn, r.get("trust")) * trust + v(conn, r.get("fear")) * fear + v(conn, r.get("favour")) * owed + v(conn, r.get("ambition")) * drive(conn, s, "ambition") * (1.0 - loyal)
    tell = v(conn, r.get("tell_base")) + v(conn, r.get("loyalty")) * loyal * rel_s * (1.0 - fear)
    keep = v(conn, r.get("refuse_base"))
    return pick(conn, s, int(day), f"sound:{p}", [("join", join), ("tell", tell), ("refuse", keep)], v(conn, r.get("temp")))


def _plot_share(conn: sqlite3.Connection, org: int, meta: dict, p: int, target: int, cblk: dict) -> float:
    bs = [b for b in backers(conn, org) if b not in (p, target)]
    tot = sum(backer_weight(conn, org, b, cblk) for b in bs)
    got = sum(backer_weight(conn, org, b, cblk) for b in bs if b in meta["joined"])
    return got / tot if tot else 0.0


def _found(conn: sqlite3.Connection, org: int, row, meta: dict, how: str, day: int) -> None:
    """The plot is known: the head gets `plot_found` about the plotter."""
    target = int(row["subject_id"])
    head = head_of(conn, org)
    close_row(conn, int(row["id"]), int(day), **meta, found=how)
    if head is None or not is_living(conn, head):
        return
    add_agenda(conn, head, "plot_found", int(day), subject_kind="actor", subject_id=int(row["actor_id"]),
               metadata={"org": int(org), "holder": int(row["actor_id"]), "target": target, "joined": meta["joined"], "how": how})
    imposed(conn, int(row["actor_id"]))


def _advance_plot(conn: sqlite3.Connection, row, day: int) -> str | None:
    meta = meta_of(row)
    org, p, target = int(meta["org"]), int(row["actor_id"]), int(row["subject_id"])
    blk, cblk = block(conn, org, "plot"), block(conn, org, "contest")
    if active_seat(conn, p, org) is None or not is_living(conn, target) or seat_of(conn, target, org) is None or seat_of(conn, target, org)["status"] != "active":
        close_row(conn, int(row["id"]), int(day), **meta, ended="gone")
        return "gone"
    weeks = (int(day) - int(meta["started"])) / WEEK
    dr = blk["drop"]  # nothing ends a plot by the calendar: the weekly chance it is dropped rises with weariness, a cooled grudge and the head's temper
    r_pt = rel(conn, p, target)
    mix = (v(conn, dr["w_weary"]) * (1.0 - math.exp(-weeks / v(conn, dr["typical_weeks"]))) + v(conn, dr["w_cool"]) * (1.0 - (clamp01(float(r_pt["resentment"]) / 100.0) if r_pt else 0.0))
           + v(conn, dr["w_fear"]) * drive(conn, head_of(conn, org) or target, "aggression")) / (v(conn, dr["w_weary"]) + v(conn, dr["w_cool"]) + v(conn, dr["w_fear"]))
    if roll(conn, p, int(day), f"drop:{row['id']}") < v(conn, dr["week"]) * mix:
        close_row(conn, int(row["id"]), int(day), **meta, ended="dropped")
        return "dropped"
    if meta["sounded"] and roll(conn, p, int(day), f"leak:{row['id']}") < v(conn, blk.get("leak_week")) * len(meta["sounded"]):
        _found(conn, org, row, meta, "leak", int(day))
        return "found"
    if roll(conn, p, int(day), f"soundweek:{row['id']}") < v(conn, blk.get("sound_week")):
        pool = [b for b in backers(conn, org) if b not in (p, target) and b not in meta["sounded"]]
        sc = [(b, weigh(conn, org, p, b, int(day), {"weights": blk["sound_weights"]})) for b in pool]
        s = pick(conn, p, int(day), f"soundwho:{row['id']}", sc, v(conn, blk["sound_temp"]))
        if s is not None:
            meta["sounded"].append(s)
            how = _respond(conn, org, blk, s, p, target, int(day))
            if how == "join":
                meta["joined"].append(s)
                adjust_relationship(conn, s, p, int(day), obligation_delta=v(conn, blk.get("join_obligation")))
            elif how == "tell":
                _found(conn, org, row, meta, "betrayed", int(day))
                return "found"
            else:
                meta["refused"].append(s)
            imposed(conn, s)
    share = _plot_share(conn, org, meta, p, target, cblk)
    if meta["joined"] and share >= v(conn, blk.get("ready_share")) and roll(conn, p, int(day), f"strike:{row['id']}") < v(conn, blk.get("strike_week")) * drive(conn, p, "aggression"):
        if not _kill(conn, p, target, int(day), sanctioned=False):  # the man lived: the plot is out, and the head deals with the plotter
            _found(conn, org, row, meta, "failed", int(day))
            return "found"
        from .org_lifecycle import _process_vacancies
        _process_vacancies(conn, int(day))  # the coup follows at once, not a week later (it reads and closes this plot)
        if conn.execute("SELECT status FROM org_agenda WHERE id=?", (int(row["id"]),)).fetchone()[0] == "open":
            close_row(conn, int(row["id"]), int(day), **meta, struck=True)
        return "struck"
    save_meta(conn, int(row["id"]), meta)
    return None


def _plots(conn: sqlite3.Connection, day: int) -> dict:
    out = {"plots": 0, "plots_found": 0, "plots_struck": 0}
    for org in contest_orgs(conn):
        blk = block(conn, org, "plot")
        head = head_of(conn, org)
        if not blk or head is None:
            continue
        for row in conn.execute("SELECT * FROM org_agenda WHERE kind='plot' AND status='open' AND json_extract(metadata_json,'$.org')=? ORDER BY id", (int(org),)).fetchall():
            r = _advance_plot(conn, row, int(day))
            out["plots_found"] += 1 if r == "found" else 0
            out["plots_struck"] += 1 if r == "struck" else 0
        head = head_of(conn, org)
        if head is None:
            continue
        heir = heir_of(conn, org, head, shown_only=True)
        for p in _plotters(conn, org, blk, head):
            for target in [head] + ([heir] if heir is not None and heir != p else []):
                if roll(conn, p, int(day), f"plot:{target}") < start_chance(conn, org, p, target, head, int(day), blk):
                    start_plot(conn, org, p, target, int(day))
                    out["plots"] += 1
                    break
    return out


def plot_found_offers(conn: sqlite3.Connection, head: int, item, day: int) -> list[dict]:
    meta = meta_of(item)
    org, p = int(meta["org"]), int(item["subject_id"])
    blk = (block(conn, org, "plot").get("found") or {})
    s = seat_of(conn, p, org)
    if s is None or s["status"] != "active" or not is_living(conn, p):
        return [{"kind": "plot_pardon", "utility": _utility(conn, 1.0), "rationale": "The man is gone.", "payload": {"org": org, "holder": p}}]
    k, e, d = blk.get("kill") or {}, blk.get("exile") or {}, blk.get("pardon") or {}
    joined = clamp01(len(meta.get("joined") or []) / max(1e-9, v(conn, blk.get("joined_scale"))))
    r = rel(conn, head, p)
    fond = 0.0 if r is None else clamp01((float(r["trust"]) + float(r["affection"])) / 200.0)
    xs = {"plot_kill": v(conn, k.get("base")) + v(conn, k.get("aggression")) * drive(conn, head, "aggression") + v(conn, k.get("joined")) * joined + v(conn, k.get("low_standing")) * (1.0 - float(s["standing"])),
          "plot_exile": v(conn, e.get("base")) + v(conn, e.get("caution")) * (1.0 - drive(conn, head, "aggression")) + v(conn, e.get("joined")) * joined,
          "plot_pardon": v(conn, d.get("base")) + v(conn, d.get("fond")) * fond + v(conn, d.get("standing")) * float(s["standing"])}
    payload = {"org": org, "holder": p, "joined": meta.get("joined")}
    why = {"plot_kill": f"Has {name_of(conn, p)} killed for plotting.", "plot_exile": f"Puts {name_of(conn, p)} out of the life for plotting.", "plot_pardon": f"Lets {name_of(conn, p)}'s plot pass."}
    return [{"kind": k2, "utility": _utility(conn, x), "rationale": why[k2], "payload": payload, **({"target_actor_id": p, "risk": 0.8} if k2 == "plot_kill" else {})} for k2, x in xs.items()]


def _finish(conn: sqlite3.Connection, payload: dict, day: int) -> None:
    if payload.get("agenda_id") is not None:
        orgs.resolve_agenda(conn, int(payload["agenda_id"]), int(day))


def execute_plot_kill(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    p = int(payload["holder"])
    imposed(conn, int(actor_id))
    for j in payload.get("joined") or []:
        adjust_relationship(conn, int(j), int(actor_id), int(day), fear_delta=v(conn, block(conn, int(payload["org"]), "plot").get("found", {}).get("fear")))
        imposed(conn, int(j))
    if not _kill(conn, int(actor_id), p, int(day), sanctioned=True):
        return {"summary": f"{name_of(conn, actor_id)} tried to have {name_of(conn, p)} killed for plotting and failed."}
    return {"summary": f"{name_of(conn, actor_id)} had {name_of(conn, p)} killed for plotting."}


def execute_plot_exile(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    leave_life(conn, int(payload["holder"]), int(payload["org"]), int(day))
    imposed(conn, int(actor_id))
    return {"summary": f"{name_of(conn, actor_id)} put {name_of(conn, payload['holder'])} out."}


def execute_plot_pardon(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    p = int(payload["holder"])
    f = block(conn, int(payload["org"]), "plot").get("found") or {}
    if p != int(actor_id):
        adjust_relationship(conn, p, int(actor_id), int(day), fear_delta=v(conn, f.get("pardon_fear")), resentment_delta=v(conn, f.get("pardon_resentment")))
        imposed(conn, p)
    return {"summary": f"{name_of(conn, actor_id)} let {name_of(conn, p)}'s plot pass."}


# ---- a coup: the head killed by one of his own ----

def coup(conn: sqlite3.Connection, org: int, late: int, killer: int, cid: int, day: int) -> bool:
    """The head was killed by a man of the organisation. Returns True when this settled it (he took over, or the factions went
    to war); False when the ordinary contest should run (with the killer's stain, or after the loyalists killed him)."""
    blk, cblk = block(conn, org, "coup"), block(conn, org, "contest")
    if not blk or active_seat(conn, killer, org) is None:
        return False
    row = conn.execute("SELECT * FROM org_agenda WHERE id=?", (int(cid),)).fetchone()
    cmeta = meta_of(row)
    plot = _plot_row(conn, killer, late)
    joined = set(meta_of(plot)["joined"]) if plot is not None else set()
    if plot is not None:
        close_row(conn, int(plot["id"]), int(day), **meta_of(plot), struck=True)
    cands = candidates(conn, org, exclude=(late,))
    cands.setdefault(killer, 0.0)
    ctx = {"heir": cmeta.get("heir"), "customary": cands, "tainted": killer}
    bs = [b for b in backers(conn, org) if b != killer]
    total = with_killer = 0.0
    loyal: list[int] = []
    for b in bs:
        w = backer_weight(conn, org, b, cblk)
        total += w
        sc = [(c, weigh(conn, org, b, c, int(day), cblk, ctx)) for c in sorted(cands)]
        if b in joined or pick(conn, b, int(day), f"coupback:{cid}", sc, v(conn, cblk.get("pick_temp"))) == killer:
            with_killer += w
        else:
            loyal.append(b)
    share = with_killer / total if total else 1.0
    cmeta.update(coup_share=round(share, 3), tainted=int(killer))
    save_meta(conn, int(cid), cmeta)
    for b in bs:
        imposed(conn, b)
    if share >= v(conn, blk.get("share")):
        if loyal and roll(conn, killer, int(day), f"coupwar:{cid}") < v(conn, blk.get("backed_war")) * (1.0 - share):
            best = _loyal_leader(conn, org, loyal, cands, killer, late, int(day), cblk, ctx)
            if best is not None:
                close_row(conn, int(cid), int(day), **cmeta, outcome="civil_war")
                start_civil_war(conn, org, [killer, best], int(day), cause="coup", late=late)
                return True
        _take_over(conn, org, killer, late, loyal, int(day), blk, cblk)
        close_row(conn, int(cid), int(day), **cmeta, outcome="coup", winner=killer)
        mark_for_history(conn, late, f"was killed by {name_of(conn, killer)}, who took the seat", int(day))
        return True
    w = blk.get("unbacked") or {}
    bal = 1.0 - abs(share - 0.5) * 2.0
    aggr = max([drive(conn, b, "aggression") for b in loyal] or [0.0])
    opts = [("war", v(conn, w.get("war")) * bal), ("loyalists_kill", v(conn, w.get("loyalists_kill")) * (1.0 - share) * aggr), ("contest", v(conn, w.get("contest")))]
    how = pick(conn, killer, int(day), f"unbacked:{cid}", opts, v(conn, w.get("temp")))
    if how == "war":
        best = _loyal_leader(conn, org, loyal, cands, killer, late, int(day), cblk, ctx)
        if best is not None:
            close_row(conn, int(cid), int(day), **cmeta, outcome="civil_war")
            start_civil_war(conn, org, [killer, best], int(day), cause="coup", late=late)
            return True
    if how == "loyalists_kill" and loyal:
        avenger = max(loyal, key=lambda b: (drive(conn, b, "aggression"), -b))
        dead = _kill(conn, avenger, killer, int(day), sanctioned=True)
        adjust_relationship(conn, avenger, late, int(day), loyalty_delta=0.0)
        if dead:  # a coup leader who lives goes on as he was: the contest stays his to win or lose
            cmeta.update(avenged_by=avenger)
            cmeta["killed"] = int(cmeta.get("killed", 0)) + 1
            cmeta.pop("tainted", None)
        save_meta(conn, int(cid), cmeta)
    return False


def _loyal_leader(conn, org, loyal, cands, killer, late, day, cblk, ctx) -> int | None:
    """The man the loyalists rally round: the claimant (not the killer) most of them would back."""
    others = [c for c in sorted(cands) if c != killer]
    if not others:
        return None
    tallies = {c: 0.0 for c in others}
    for b in loyal or backers(conn, org):
        if b == killer:
            continue
        best = max(others, key=lambda c: (weigh(conn, org, b, c, int(day), cblk, ctx), -c))
        tallies[best] += 1.0
    return max(others, key=lambda c: (tallies[c], -c))


def _take_over(conn, org, killer, late, loyal, day, blk, cblk) -> None:
    """The killer holds the seat. Each loyalist accepts (trust in him, fear of him), is bought (money, his greed) or is removed
    (the killer's temper against the loyalist's loyalty to the late head)."""
    install_head(conn, org, killer, int(day), "coup")
    w = blk.get("loyalists") or {}
    for b in loyal:
        r_bk, r_bl = rel(conn, b, killer), rel(conn, b, late)
        trust = 0.0 if r_bk is None else clamp01((float(r_bk["trust"]) + float(r_bk["loyalty"])) / 200.0)
        fear = 0.0 if r_bk is None else clamp01(float(r_bk["fear"]) / 100.0)
        loyal_late = 0.0 if r_bl is None else clamp01(float(r_bl["loyalty"]) / 100.0)
        purse = clamp01(ledger.balance(conn, ("person", int(killer))) * v(conn, w.get("buy_share")) / max(1e-9, v(conn, w.get("buy_scale"))))
        opts = [("accept", v(conn, w.get("accept_base")) + v(conn, w.get("accept_trust")) * trust + v(conn, w.get("accept_fear")) * fear),
                ("bought", v(conn, w.get("buy_base")) * purse * lean(conn, org, drive(conn, b, "greed", org))),
                ("removed", v(conn, w["remove_base"]) * temper(conn, org, killer) * loyal_late * (1.0 - fear)),
                ("exile", v(conn, w["exile_base"]) + v(conn, w["exile_loyalty"]) * loyal_late * (1.0 - fear))]
        how = pick(conn, b, int(day), f"loyalist:{late}", opts, v(conn, w.get("temp")))
        if how == "bought":
            paid = _pay(conn, killer, b, ledger.balance(conn, ("person", int(killer))) * v(conn, w.get("buy_share")), w.get("flow"), "what he paid a loyalist")
            adjust_relationship(conn, b, killer, int(day), obligation_delta=v(conn, w.get("buy_obligation")))
        elif how == "removed":
            _kill(conn, killer, b, int(day), sanctioned=True)
        elif how == "exile":
            exile_man(conn, org, b, killer, int(day))
        else:
            adjust_relationship(conn, b, killer, int(day), fear_delta=v(conn, w.get("accept_fear_gain")), resentment_delta=v(conn, w.get("accept_resentment")))
        imposed(conn, b)


# ---- civil war ----

def war_row(conn: sqlite3.Connection, org: int):
    return conn.execute("SELECT * FROM org_agenda WHERE kind='civil_war' AND status='open' AND actor_id=? ORDER BY id DESC LIMIT 1", (int(org),)).fetchone()


def _factions(conn: sqlite3.Connection, org: int, meta: dict) -> dict[int, int]:
    """actor id -> faction index for every living seated man: leaders and the backers who joined a side by name; everyone else
    with the man he answers to, up the chain, until a man of a side."""
    side = {}
    for i, f in enumerate(meta["factions"]):
        side[int(f["leader"])] = i
        for m in f["members"]:
            side.setdefault(int(m), i)
    side.update({int(k): int(x) for k, x in (meta.get("overrides") or {}).items()})
    sup = {int(a): (None if s is None else int(s)) for a, s in conn.execute("SELECT actor_id,superior_actor_id FROM org_seats WHERE org_actor_id=? AND status='active'", (int(org),))}
    out = {}
    for a in sup:
        cur, seen = a, set()
        while cur is not None and cur not in side and cur not in seen:
            seen.add(cur)
            cur = sup.get(cur)
        if cur is not None and cur in side:
            out[a] = side[cur]
    return out


def start_civil_war(conn: sqlite3.Connection, org: int, leaders: list[int], day: int, *, cause: str, late: int | None = None) -> int | None:
    """Two claimants, each with the backers who weigh him above the other; the stronger holds the seat meanwhile."""
    blk = block(conn, org, "civil_war")
    if not blk or len(leaders) < 2 or war_row(conn, org) is not None:
        return None
    cblk = block(conn, org, "contest")
    ctx = {"customary": {int(x): 1.0 for x in leaders}, "war": True}
    sides = [{"leader": int(x), "members": []} for x in leaders[:2]]
    for b in backers(conn, org):
        if b in leaders:
            continue
        sc = [(i, weigh(conn, org, b, int(sides[i]["leader"]), int(day), cblk, ctx)) for i in (0, 1)]
        sides[pick(conn, b, int(day), "warside", sc, v(conn, blk["side_temp"]))]["members"].append(b)
    meta = {"org": int(org), "started": int(day), "cause": cause, "late": late, "factions": sides, "overrides": {}, "killed": [0, 0], "spent": [0.0, 0.0], "defected": 0}
    rid = put_row(conn, int(org), "civil_war", int(day), late, meta)
    side = _factions(conn, org, meta)
    strength = _strength(conn, org, meta, side, blk)
    if acting_marker(conn, org) is None and head_of(conn, org) is None:
        stronger = max((0, 1), key=lambda i: (strength[i], -i))
        set_acting(conn, org, int(sides[stronger]["leader"]), int(late if late is not None else sides[stronger]["leader"]), int(day), rid)
    for a, i in side.items():
        imposed(conn, a)
        for j, f in enumerate(sides):
            if j != i and a != int(f["leader"]):
                adjust_relationship(conn, a, int(f["leader"]), int(day), resentment_delta=v(conn, blk.get("start_resentment")))
    for f in sides:
        mark_for_history(conn, int(f["leader"]), f"led a side in the war over the {name_of(conn, org)}", int(day))
    return rid


def _strength(conn: sqlite3.Connection, org: int, meta: dict, side: dict[int, int], blk: dict) -> list[float]:
    out = [0.0, 0.0]
    dep = v(conn, blk.get("dependant_weight"))
    for a, inducted in conn.execute("SELECT actor_id,inducted_day IS NOT NULL FROM org_seats WHERE org_actor_id=? AND status='active'", (int(org),)):
        i = side.get(int(a))
        if i is not None and is_living(conn, int(a)):
            out[i] += 1.0 if inducted else dep
    for i, f in enumerate(meta["factions"]):
        out[i] += v(conn, blk["money_weight"]) * min(1.0, ledger.balance(conn, ("person", int(f["leader"]))) / max(1e-9, v(conn, blk["money_scale"]))) * v(conn, blk["money_men"])
    return out


def _war_killing(conn, org, meta, side, blk, day, rid, strength) -> None:
    weeks = (int(day) - int(meta["started"])) // WEEK
    inten = min(1.0, v(conn, blk.get("start_intensity")) + weeks / max(1.0, v(conn, blk.get("ramp_weeks"))))
    leaders = [int(f["leader"]) for f in meta["factions"]]
    opts = [(i, drive(conn, leaders[i], "aggression") * strength[i]) for i in (0, 1) if is_living(conn, leaders[i])]
    if not opts or roll(conn, org, int(day), f"warkill:{rid}") >= v(conn, blk.get("kill_week")) * inten:
        return
    atk = pick(conn, org, int(day), f"warwho:{rid}", [(i, s / max(1e-9, max(x for _j, x in opts))) for i, s in opts], v(conn, blk["target_temp"]))
    mine = [(a, drive(conn, a, "aggression")) for a, i in sorted(side.items()) if i == atk and a != leaders[atk] and seat_of(conn, a, org)["inducted_day"] is not None]
    theirs = []
    for a, i in sorted(side.items()):
        if i != atk:
            s = seat_of(conn, a, org)
            lead = v(conn, blk.get("leader_target")) if a == leaders[1 - atk] or s["role_key"] == kind_rules(conn, org).get("unit_leader") else 0.0
            theirs.append((a, float(s["standing"]) + lead + (v(conn, blk.get("men_target")) if s["inducted_day"] is not None else 0.0)))
    killer = pick(conn, org, int(day), f"warkiller:{rid}", mine, v(conn, blk["target_temp"])) if mine else leaders[atk]
    victim = pick(conn, org, int(day), f"warvictim:{rid}", theirs, v(conn, blk["target_temp"]))
    if victim is None:
        return
    dead = _kill(conn, int(killer), int(victim), int(day), sanctioned=True)
    if dead:
        meta["killed"][1 - atk] += 1
    adjust_relationship(conn, leaders[1 - atk], leaders[atk], int(day), resentment_delta=v(conn, blk.get("kill_resentment")))
    if dead and int(victim) == leaders[1 - atk]:  # his side's strongest man takes his place
        rest = [a for a, i in side.items() if i == 1 - atk and a != int(victim) and active_seat(conn, a, org) is not None]
        if rest:
            meta["factions"][1 - atk]["leader"] = max(rest, key=lambda a: (float(seat_of(conn, a, org)["standing"]), -a))


def _war_defections(conn, org, meta, side, blk, cblk, day, rid) -> None:
    ctx = {"customary": {int(f["leader"]): 1.0 for f in meta["factions"]}, "war": True}
    for b in backers(conn, org):
        i = side.get(b)
        if i is None or b == int(meta["factions"][i]["leader"]) or roll(conn, b, int(day), f"defect:{rid}") >= v(conn, blk.get("defect_week")):
            continue
        own, other = int(meta["factions"][i]["leader"]), int(meta["factions"][1 - i]["leader"])
        if weigh(conn, org, b, other, int(day), cblk, ctx) - weigh(conn, org, b, own, int(day), cblk, ctx) > v(conn, blk.get("defect_margin")):
            meta["overrides"][str(b)] = 1 - i
            meta["defected"] += 1
            adjust_relationship(conn, b, own, int(day), loyalty_delta=-v(conn, blk.get("defect_loyalty")))
            imposed(conn, b)


def tick_war(conn: sqlite3.Connection, row, day: int) -> str | None:
    meta = meta_of(row)
    org, rid = int(meta["org"]), int(row["id"])
    blk, cblk = block(conn, org, "civil_war"), block(conn, org, "contest")
    weeks = (int(day) - int(meta["started"])) / WEEK
    side = _factions(conn, org, meta)
    strength = _strength(conn, org, meta, side, blk)
    _war_killing(conn, org, meta, side, blk, day, rid, strength)
    side = _factions(conn, org, meta)
    _war_defections(conn, org, meta, side, blk, cblk, day, rid)
    side = _factions(conn, org, meta)
    for i, f in enumerate(meta["factions"]):  # the war costs money
        cost = v(conn, blk.get("cost_week")) * sum(1 for a, j in side.items() if j == i)
        if cost > 0.0 and is_living(conn, int(f["leader"])):
            meta["spent"][i] += ledger.spend(conn, ("person", int(f["leader"])), cost, purpose="paying for a war")
    strength = _strength(conn, org, meta, side, blk)
    tot = sum(strength) or 1.0
    share = [strength[0] / tot, strength[1] / tot]
    live = [active_seat(conn, int(f["leader"]), org) is not None for f in meta["factions"]]
    leaders = [int(f["leader"]) for f in meta["factions"]]
    young = early(conn, weeks, blk["early_weeks"], blk["early_floor"])  # a quick end is unlikely in the first days, never impossible
    press = pressure(conn, org, blk["press"], opened=meta["started"], day=day, typical=blk["typical_weeks"], spent=sum(meta["spent"]), leaders=leaders)
    lead_i = max((0, 1), key=lambda i: (share[i], -i))
    weak = 1 - lead_i
    out = None
    if not all(live):
        out = ("win", max((0, 1), key=lambda i: (live[i], share[i], -i)))
    else:
        p_win = v(conn, blk["win_week"]) * young * clamp01((max(share) - 0.5) / (v(conn, blk["win_share"]) - 0.5))
        r = rel(conn, leaders[weak], leaders[lead_i])
        bitter = 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0)
        men_weak = sum(1 for a, j in side.items() if j == weak and seat_of(conn, a, org)["inducted_day"] is not None)
        p_split = (v(conn, blk["split_week"]) * young * drive(conn, leaders[weak], "ambition") * lean(conn, org, bitter)
                   * clamp01(share[weak] / v(conn, blk["split_ref_share"])) * clamp01(men_weak / v(conn, blk["split_ref_men"])))
        p_settle = v(conn, blk["settle_week"]) * young * press * (1.0 - abs(share[0] - share[1])) * (1.0 - (drive(conn, leaders[0], "aggression") + drive(conn, leaders[1], "aggression")) / 2.0)
        if roll(conn, org, int(day), f"win:{rid}") < p_win:
            out = ("win", lead_i)
        elif roll(conn, org, int(day), f"split:{rid}") < p_split:
            out = ("split", lead_i)
        elif roll(conn, org, int(day), f"settle:{rid}") < p_settle:
            out = ("settle", lead_i)
    if out is None:
        save_meta(conn, rid, meta)
        return None
    how, winner = out
    _end_war(conn, row, meta, side, blk, how, int(winner), int(day))
    return how


def _end_war(conn, row, meta, side, blk, how: str, winner: int, day: int) -> None:
    org = int(meta["org"])
    wl = int(meta["factions"][winner]["leader"])
    ll = int(meta["factions"][1 - winner]["leader"])
    if active_seat(conn, wl, org) is None:  # no living man on the winning side: the other side's leader, if there is one
        wl, winner, ll = ll, 1 - winner, wl
    losers = [a for a, i in sorted(side.items()) if i == 1 - winner]
    out = {"how": how, "winner": wl}
    if how == "split":
        new = split_org(conn, org, [a for a, i in side.items() if i == 1 - winner], ll, int(day), blk)
        out["new_org"] = new
        install_head(conn, org, wl, int(day), "civil_war")
    elif how == "settle":
        install_head(conn, org, wl, int(day), "settled")
        for a, b in ((wl, ll), (ll, wl)):
            if a != b and is_living(conn, a) and is_living(conn, b):
                r = rel(conn, a, b)
                if r is not None:
                    adjust_relationship(conn, a, b, int(day), resentment_delta=-min(float(r["resentment"]), v(conn, blk.get("settle_thaw"))), trust_delta=v(conn, blk.get("settle_trust")))
        for a in losers:
            imposed(conn, a)
        if ll != wl and active_seat(conn, ll, org) is not None:
            add_agenda(conn, wl, "rival", int(day) + int(v(conn, orgs.kind_rules(conn, org)["lifecycle"]["rivals"]["delay_days"])), subject_kind="actor", subject_id=int(ll),
                       metadata={"org": int(org), "rival": int(ll), "how": "settle"})
    else:
        install_head(conn, org, wl, int(day), "civil_war")
        out["dealt"] = _deal_with_losers(conn, org, wl, losers, blk, int(day), leaders=(ll,))
    for a in side:
        imposed(conn, a)
    mark_for_history(conn, wl, f"won the war over the {name_of(conn, org)}" if how == "win" else f"ended the war over the {name_of(conn, org)} ({how})", int(day))
    close_row(conn, int(row["id"]), int(day), **{**meta, **out, "closed": int(day), "weeks": (int(day) - int(meta["started"])) // WEEK})


def demote_man(conn: sqlite3.Connection, org: int, man: int, by: int, day: int) -> None:
    """His lines pass to the man who decided, his standing goes, and the role the data says a returning man takes is his; a unit
    leader's unit and any post of the data's succession he held are put to the head to fill."""
    s = seat_of(conn, man, org)
    unit_role = kind_rules(conn, org).get("unit_leader")
    back = (orgs.kind_rules(conn, org).get("lifecycle") or {}).get("returns_as")
    old_role = s["role_key"]
    conn.execute("UPDATE org_lines SET holder_actor_id=? WHERE holder_actor_id=? AND status='active'", (int(by), int(man)))
    conn.execute("UPDATE org_seats SET standing=0 WHERE id=?", (int(s["id"]),))
    if back and old_role != back:
        conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=? WHERE id=?", (back, int(by), int(s["id"])))
        membership_text(conn, org, man, back)
        lv = role_level(conn, org, back)
        if lv is not None:
            orgs.set_level(conn, man, lv, int(day), org)
        if old_role == unit_role and s["unit_id"]:
            seat_the_unit(conn, org, int(s["unit_id"]), int(day), deciding=int(by))
        elif old_role in ((orgs.kind_rules(conn, org).get("lifecycle") or {}).get("succession") or {}):
            fill_post(conn, org, old_role, int(day))
    imposed(conn, int(man))
    imposed(conn, int(by))


def _deal_with_losers(conn, org, winner: int, losers: list[int], blk: dict, day: int, leaders: tuple = ()) -> dict:
    """What the winner does with each made man on the losing side. A side's leader and the unit leaders are weighed like any rival of
    a head (`rival_weights` for a war: killed, exiled, sidelined or kept; the data makes killing common here). The rest are killed
    (the winner's temper, the man's weight, his lack of fear), demoted, exiled or absorbed (he stays, afraid)."""
    w = blk["losers"]
    counts = {"killed": 0, "demoted": 0, "exiled": 0, "absorbed": 0}
    unit_role = kind_rules(conn, org).get("unit_leader")
    for a in losers:
        s = seat_of(conn, a, org)
        if s is None or s["status"] != "active" or s["inducted_day"] is None or not is_living(conn, a):
            continue
        if int(a) in leaders or s["role_key"] == unit_role:
            xs = rival_weights(conn, org, winner, a, "civil_war")
            how = {"keep": "absorb", "sideline": "demote", "exile": "exile", "remove": "kill"}[pick(conn, a, int(day), "loser_leader", list(xs.items()), v(conn, orgs.kind_rules(conn, org)["lifecycle"]["rivals"]["temp"]))]
        else:
            r = rel(conn, a, winner)
            fear = 0.0 if r is None else clamp01(float(r["fear"]) / 100.0)
            trust = 0.0 if r is None else clamp01((float(r["trust"]) + float(r["loyalty"])) / 200.0)
            weight = v(conn, w["standing_weight"]) * float(s["standing"])
            opts = [("kill", v(conn, w["kill_base"]) + v(conn, w["kill_aggression"]) * temper(conn, org, winner) * weight * (1.0 - fear)),
                    ("demote", v(conn, w["demote_base"]) + v(conn, w["demote_weight"]) * weight),
                    ("exile", v(conn, w["exile_base"]) + v(conn, w["exile_weight"]) * weight * (1.0 - fear)),
                    ("absorb", v(conn, w["absorb_base"]) + v(conn, w["absorb_fear"]) * fear + v(conn, w["absorb_trust"]) * trust)]
            how = pick(conn, a, int(day), "loser", opts, v(conn, w["temp"]))
        if how == "kill":
            if _kill(conn, winner, a, int(day), sanctioned=True):
                counts["killed"] += 1
        elif how == "demote":
            demote_man(conn, org, a, winner, int(day))
            adjust_relationship(conn, a, winner, int(day), resentment_delta=v(conn, w["demote_resentment"]))
            counts["demoted"] += 1
        elif how == "exile":
            exile_man(conn, org, a, winner, int(day))
            counts["exiled"] += 1
        else:
            adjust_relationship(conn, a, winner, int(day), fear_delta=v(conn, w["absorb_fear_gain"]))
            counts["absorbed"] += 1
        imposed(conn, a)
    return counts


def exile_man(conn: sqlite3.Connection, org: int, man: int, by: int, day: int) -> None:
    """Sent away (to another city or territory), retired off, told never to come back: his lines pass to the man who decided, his seat
    is out with the record kept (an `exiled` marker, so he is not a man who walked away) and he leaves the living organisation."""
    d = orgs.kind_rules(conn, org)["lifecycle"]["rivals"]["exile"]
    imposed(conn, int(man))
    conn.execute("UPDATE org_lines SET holder_actor_id=? WHERE holder_actor_id=? AND status='active'", (int(by), int(man)))
    put_row(conn, int(man), "exiled", int(day), int(org), {"org": int(org), "by": int(by)}, "org")
    leave_life(conn, int(man), int(org), int(day))
    adjust_relationship(conn, int(man), int(by), int(day), resentment_delta=v(conn, d["resentment_gain"]), fear_delta=v(conn, d["fear_gain"]))
    mark_for_history(conn, int(man), f"was sent away from the {name_of(conn, org)}", int(day))
    imposed(conn, int(by))


# ---- a split: the losing side becomes a new organisation of the same kind ----

def split_org(conn: sqlite3.Connection, org: int, men: list[int], leader: int, day: int, blk: dict) -> int | None:
    """The men (and, with their unit leader, his unit and lines) leave `org` for a new institution of the same kind, headed by
    `leader`. The new organisation is built through the org tables: an institution actor, a profile, seats, units, lines and
    holdings of its own, so the weekly layers and the money rules run on it like on any other."""
    spec = block(conn, org, "split")
    rules = kind_rules(conn, org)
    leader = int(leader)
    if active_seat(conn, leader, org) is None:
        return None
    moved = {int(a) for a in men if active_seat(conn, a, org) is not None} | {leader}
    units = {int(r[0]) for r in conn.execute("SELECT id FROM org_units WHERE org_actor_id=? AND leader_actor_id IN (%s)" % ",".join("?" * len(moved)), (int(org), *sorted(moved)))}
    uargs = sorted(units) or [-1]
    for (a,) in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND unit_id IN (%s)" % ",".join("?" * len(uargs)), (int(org), *uargs)).fetchall():
        moved.add(int(a))
    surname = name_of(conn, leader).split()[-1]
    base = str(spec.get("name") or "{surname} splinter").format(surname=surname)
    name, n = base, 1
    while conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
        n += 1
        name = f"{base} {'I' * n}" if n < 4 else f"{base} {n}"
    prof = conn.execute("SELECT * FROM org_profiles WHERE org_actor_id=?", (int(org),)).fetchone()
    inducted = [a for a in moved if seat_of(conn, a, org)["inducted_day"] is not None]
    deps = len(moved) - len(inducted)
    new = int(conn.execute("INSERT INTO actors(name,actor_type,subtype,status) VALUES (?, 'institution', ?, 'active')",
                           (name, conn.execute("SELECT subtype FROM actors WHERE id=?", (int(org),)).fetchone()[0])).lastrowid)
    n_split = int(conn.execute("SELECT COUNT(*) FROM org_profiles WHERE package_key LIKE ?", (f"{prof['package_key']}~split%",)).fetchone()[0]) + 1
    conn.execute("INSERT INTO org_profiles(org_actor_id,org_kind,sphere,package_key,metadata_json) VALUES (?,?,?,?,?)",
                 (new, prof["org_kind"], prof["sphere"], f"{str(prof['package_key']).split('~')[0]}~split{n_split}",
                  json.dumps({"split_of": int(org), "day": int(day), "spec": {"members_figure": len(inducted), "dependents_figure": round(deps / max(1, len(inducted)), 3)}}, sort_keys=True)))
    ph = ",".join("?" * len(moved))
    conn.execute(f"UPDATE org_seats SET org_actor_id=? WHERE org_actor_id=? AND actor_id IN ({ph})", (new, int(org), *sorted(moved)))
    conn.execute(f"UPDATE org_units SET org_actor_id=? WHERE id IN ({','.join('?' * len(uargs))})", (new, *uargs))
    head_role = rules["head"]
    conn.execute("UPDATE org_seats SET role_key=?, unit_id=NULL, superior_actor_id=NULL WHERE actor_id=? AND org_actor_id=?", (head_role, leader, new))
    for (a, sup, unit) in conn.execute("SELECT actor_id,superior_actor_id,unit_id FROM org_seats WHERE org_actor_id=? AND actor_id<>?", (new, leader)).fetchall():
        if sup is None or int(sup) not in moved:
            conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE actor_id=? AND org_actor_id=?", (leader, int(a), new))
    conn.execute(f"UPDATE institution_memberships SET institution_actor_id=? WHERE institution_actor_id=? AND membership_kind='member' AND member_actor_id IN ({ph})", (new, int(org), *sorted(moved)))
    for a in moved:
        membership_text(conn, new, a, seat_of(conn, a, new)["role_key"])
    lines = conn.execute(f"SELECT l.*,h.pool_key,h.share_pct,h.yearly_take,h.id AS hid FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active' "
                         f"AND (l.holder_actor_id IN ({ph}) OR l.unit_id IN ({','.join('?' * len(uargs))}))", (int(org), *sorted(moved), *uargs)).fetchall()
    holdings: dict[int, int] = {}
    for ln in lines:
        hid = int(ln["hid"])
        if hid not in holdings:
            total = conn.execute("SELECT COALESCE(SUM(weekly_take),0) FROM org_lines WHERE holding_id=? AND status='active'", (hid,)).fetchone()[0] or 1.0
            take = sum(float(x["weekly_take"]) for x in lines if int(x["hid"]) == hid)
            frac = min(1.0, take / total)
            holdings[hid] = int(conn.execute("INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,source,started_day) VALUES (?,?,?,?,'taken',?)",
                                             (new, ln["pool_key"], float(ln["share_pct"]) * frac, float(ln["yearly_take"]) * frac, int(day))).lastrowid)
            conn.execute("UPDATE org_holdings SET share_pct=share_pct*?, yearly_take=yearly_take*? WHERE id=?", (1.0 - frac, 1.0 - frac, hid))
        conn.execute("UPDATE org_lines SET holding_id=? WHERE id=?", (holdings[hid], int(ln["id"])))
    lv = role_level(conn, new, head_role)
    for a in sorted(moved):
        imposed(conn, a)
    if lv is not None:
        orgs.set_level(conn, leader, lv, int(day), new)
    mark_for_history(conn, leader, f"split from the {name_of(conn, org)} and took his men", int(day))
    return new


# ---- the new head and the men who stood against him ----

def rival_weights(conn: sqlite3.Connection, org: int, head: int, rv: int, how: str) -> dict[str, float]:
    """The head's pull toward each answer to a man who stood against him: keep, sideline, exile, remove. Each answer starts from the
    base the data gives for how the matter ended (`rivals.how[how]`: an agreed contest keeps its losers more often; a forced or bought
    one, a killing, a coup or a war removes them more often) and adds the rival's trust and fear, his resentment and ambition, his
    strength, and the head's own temper (his aggression and the outfit's lean toward violence). A missing outcome fails loudly."""
    d = orgs.kind_rules(conn, org)["lifecycle"]["rivals"]
    base = d["how"][how]
    r = rel(conn, rv, head)
    trust = 0.0 if r is None else clamp01((float(r["trust"]) + float(r["loyalty"])) / 200.0)
    fear = 0.0 if r is None else clamp01(float(r["fear"]) / 100.0)
    resent = 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0)
    from .org_succession import _under
    strength = clamp01(len(_under(conn, org, rv)) / v(conn, d["strength_scale"]))
    k, sd, ex, rm = d["keep"], d["sideline"], d["exile"], d["remove"]
    return {"keep": v(conn, base["keep"]) + v(conn, k["trust"]) * trust + v(conn, k["fear"]) * fear + v(conn, k["strength"]) * strength,
            "sideline": v(conn, base["sideline"]) + v(conn, sd["resentment"]) * resent + v(conn, sd["ambition"]) * drive(conn, rv, "ambition") * (1.0 - fear),
            "exile": v(conn, base["exile"]) + v(conn, ex["resentment"]) * resent + v(conn, ex["strength"]) * strength + v(conn, ex["caution"]) * (1.0 - temper(conn, org, head)),
            "remove": v(conn, base["remove"]) + v(conn, rm["aggression"]) * temper(conn, org, head) * resent * (1.0 - fear) * (1.0 - v(conn, rm["strength"]) * strength)}


def rival_offers(conn: sqlite3.Connection, head: int, item, day: int) -> list[dict]:
    """The new head weighs what to do about a man who stood against him (`rival_weights`), by how the matter ended."""
    meta = meta_of(item)
    org, rv = int(meta["org"]), int(item["subject_id"])
    payload = {"org": org, "rival": rv}
    s = seat_of(conn, rv, org)
    if s is None or s["status"] != "active" or not is_living(conn, rv):
        return [{"kind": "rival_keep", "utility": _utility(conn, 1.0), "rationale": "The man is gone.", "payload": payload}]
    xs = rival_weights(conn, org, head, rv, meta["how"])
    why = {"keep": f"Keeps {name_of(conn, rv)}, who stood against him.", "sideline": f"Sidelines {name_of(conn, rv)}, who stood against him.",
           "exile": f"Sends {name_of(conn, rv)} away, for standing against him.", "remove": f"Has {name_of(conn, rv)} removed, for standing against him."}
    return [{"kind": "rival_" + k2, "utility": _utility(conn, x), "rationale": why[k2], "payload": payload, **({"target_actor_id": rv, "risk": 0.8} if k2 == "remove" else {})} for k2, x in xs.items()]


def execute_rival_exile(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    org, rv = int(payload["org"]), int(payload["rival"])
    s = seat_of(conn, rv, org)
    if s is None or s["status"] != "active":
        return {"summary": "There was no one to send away.", "blocked": True}
    exile_man(conn, org, rv, int(actor_id), int(day))
    return {"summary": f"{name_of(conn, actor_id)} sent {name_of(conn, rv)} away."}


def execute_rival_keep(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    rv = int(payload["rival"])
    d = (orgs.kind_rules(conn, int(payload["org"])).get("lifecycle") or {})["rivals"]
    if rv != int(actor_id):
        adjust_relationship(conn, rv, int(actor_id), int(day), resentment_delta=-v(conn, d["keep"]["thaw"]), trust_delta=v(conn, d["keep"]["trust_gain"]))
        imposed(conn, rv)
    return {"summary": f"{name_of(conn, actor_id)} kept {name_of(conn, rv)} on."}


def execute_rival_sideline(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    org, rv = int(payload["org"]), int(payload["rival"])
    s = seat_of(conn, rv, org)
    if s is None or s["status"] != "active":
        return {"summary": "There was no one to sideline.", "blocked": True}
    d = (orgs.kind_rules(conn, org).get("lifecycle") or {})["rivals"]
    demote_man(conn, org, rv, int(actor_id), int(day))
    adjust_relationship(conn, rv, int(actor_id), int(day), resentment_delta=v(conn, d["sideline"]["resentment_gain"]))
    return {"summary": f"{name_of(conn, actor_id)} sidelined {name_of(conn, rv)}."}


def execute_rival_remove(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    rv = int(payload["rival"])
    if not is_living(conn, rv):
        return {"summary": "The man was already gone.", "blocked": True}
    imposed(conn, int(actor_id))
    _kill(conn, int(actor_id), rv, int(day), sanctioned=True)
    return {"summary": f"{name_of(conn, actor_id)} had {name_of(conn, rv)} removed."}


# ---- the weekly pass ----

def _wars(conn: sqlite3.Connection, day: int) -> dict:
    out = {"war_weeks": 0, "wars_ended": 0}
    for row in conn.execute("SELECT * FROM org_agenda WHERE kind='civil_war' AND status='open' ORDER BY id").fetchall():
        out["war_weeks"] += 1
        out["wars_ended"] += 1 if tick_war(conn, row, int(day)) else 0
    return out


def weekly(conn: sqlite3.Connection, day: int) -> dict:
    out = _plots(conn, int(day))
    for k, n in _wars(conn, int(day)).items():
        out[k] = out.get(k, 0) + n
    return out


for _kind, _fn in (("plot_kill", execute_plot_kill), ("plot_exile", execute_plot_exile), ("plot_pardon", execute_plot_pardon)):
    register_executor(_kind, _fn)
register_agenda_action("plot_found", plot_found_offers)
for _kind, _fn in (("rival_keep", execute_rival_keep), ("rival_sideline", execute_rival_sideline), ("rival_exile", execute_rival_exile), ("rival_remove", execute_rival_remove)):
    register_executor(_kind, _fn)
register_agenda_action("rival", rival_offers)
```

## engine/org_happenings.py

```python
"""The weeks of the men who depend on a patron: something good, neutral or bad now and then (underworld layer, role-free).

Every `week_days` (7) each active man in a dependent role (orgs.json `kinds[k].opening.dependent_role`) rolls once against
the package's `happenings.week_rate`; when it passes, one happening is drawn from the package's open set
(`outfits.json` `happenings.kinds`): each kind has a group (good / neutral / wrong), a base weight, a floor and motives. The
motives are readers registered with `org_motives.register_motive` under the choice name `hap_<kind>`; their weights are
package data, so a new kind is a data entry (and a reader if it needs one). A kind's weight is
`base * (floor + pressure)`; `requires` readers that read 0 shut a kind out (no open case, no informing).

  good     score  bring_earner  proves_himself  recruits  favour
  neutral  drifts  goes_straight  switches
  wrong    incident  holds_out  busted  informs

Each happening writes an `org_incidents` row (offender = the man; `matters` 1 when it raises something to another
organisation's head). A mattering `incident` puts `respond_incident` on the victim organisation's head (sit_down, kill_offender,
let_it_go); sitting down puts `pay_or_refuse` on the offender's head. Everything imposed on a man calls `orgs.imposed`
(reviewed tomorrow and daily for a few days): an incident's victim and offender, a held man, a man whose seat is taken over,
an informer's named superior when it is discovered, the recipient of a demand to pay. Names of roles come from the package
data; this module names none. Every rate and figure is a design figure.
"""
from __future__ import annotations

import json
import random
import sqlite3

from . import ledger, org_heat, org_motives, outfit_motives as om
from .design import run_seed
from .org_choices import register_agenda_action, register_executor
from .law_opening import agency_for
from .org_lifecycle import leave_life, mark_for_history
from .org_motives import _fig as figure
from .orgs import add_agenda, clamp01, head_of, imposed, is_living, kind_rules, resolve_agenda, seat_of
from .relationships import adjust_relationship
from .world_package import org_rules, package_for

WEEK = 7
_CACHE: dict = {"key": None, "data": None, "roles": None}


# ---- the package's data ----

def _data(conn: sqlite3.Connection) -> dict:
    """outfits.json `happenings` (read once per database); {} when the package has none."""
    key = org_motives.db_key(conn)
    if _CACHE["key"] != key:
        _CACHE.update(key=key, data=org_motives._sphere_data(conn).get("happenings") or {}, roles=None)
    return _CACHE["data"]


def _dependent_roles(conn: sqlite3.Connection) -> dict[str, str]:
    """org kind -> its dependent role (orgs.json kinds[k].opening.dependent_role)."""
    _data(conn)
    if _CACHE["roles"] is None:
        kinds = org_rules(package_for(conn)).get("kinds") or {}
        _CACHE["roles"] = {k: v["opening"]["dependent_role"] for k, v in kinds.items() if (v.get("opening") or {}).get("dependent_role")}
    return _CACHE["roles"]


def _v(conn, spec, default: float = 0.0) -> float:
    return org_motives._value(conn, spec, default)


def _kinds(conn: sqlite3.Connection) -> dict:
    return _data(conn).get("kinds") or {}


def group_of(conn: sqlite3.Connection) -> dict[str, str]:
    return {k: str(s["group"]) for k, s in _kinds(conn).items()}


def _name(conn: sqlite3.Connection, actor_id: int | None) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone() if actor_id is not None else None
    return str(r[0]) if r else "someone"


def _rng(conn: sqlite3.Connection, stream: str, actor: int, day: int) -> random.Random:
    return random.Random(f"{run_seed(conn)}:happening:{stream}:{int(actor)}:{int(day)}")


# ---- the man's place in his organisation ----

def _ctx(conn: sqlite3.Connection, actor_id: int):
    """(seat, org) for the first active seat in a dependent role of its organisation's kind; None otherwise."""
    roles = _dependent_roles(conn)
    for s in conn.execute("SELECT s.*,p.org_kind FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id WHERE s.actor_id=? AND s.status='active' "
                          "ORDER BY s.org_actor_id", (int(actor_id),)).fetchall():
        if roles.get(s["org_kind"]) == s["role_key"]:
            return s, int(s["org_actor_id"])
    return None


def _opening(conn: sqlite3.Connection, org: int) -> dict:
    return kind_rules(conn, org).get("opening") or {}


def _ratio(conn: sqlite3.Connection, org: int) -> float:
    key = conn.execute("SELECT package_key FROM org_profiles WHERE org_actor_id=?", (org,)).fetchone()[0]
    spec = ((org_motives._sphere_data(conn).get("outfits") or {}).get(key) or {})
    return float(figure(conn, spec["dependents_figure"])) if spec.get("dependents_figure") else 0.0


def _gain(conn: sqlite3.Connection, seat, delta: float) -> None:
    conn.execute("UPDATE org_seats SET standing=? WHERE id=?", (clamp01(float(seat["standing"]) + delta), int(seat["id"])))


def _refresh(conn: sqlite3.Connection, a: int, org: int):
    return seat_of(conn, a, org)


# ---- readers (registered under `hap_<kind>`) ----

def _drive(conn, a, trait):
    return om._drive(conn, a, trait)


def _r_ctx(fn):
    def reader(conn, actor, day):
        c = _ctx(conn, actor)
        return 0.0 if c is None else clamp01(fn(conn, actor, day, c[0], c[1]))
    return reader


def _unit_men(conn, seat, org):
    """(inducted members, dependants) in his unit."""
    if not seat["unit_id"]:
        return 0, 0
    rows = conn.execute("SELECT role_key,inducted_day FROM org_seats WHERE unit_id=? AND status='active'", (int(seat["unit_id"]),)).fetchall()
    return sum(1 for r in rows if r["inducted_day"] is not None), sum(1 for r in rows if r["role_key"] == seat["role_key"])


def _unit_short(conn, a, day, seat, org):
    men, deps = _unit_men(conn, seat, org)
    want = men * _ratio(conn, org)
    return 0.0 if want <= 0 else 1.0 - deps / want


def _other_members(conn, seat, org, day: int | None = None) -> list[int]:
    st = _day_state(conn, day)["readings"] if day is not None else {}
    k = ("others", org, seat["unit_id"])
    if k not in st:
        st[k] = [int(r[0]) for r in conn.execute(
            "SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND inducted_day IS NOT NULL AND COALESCE(unit_id,0)<>COALESCE(?,0) ORDER BY actor_id",
            (org, seat["unit_id"])) if is_living(conn, int(r[0]))]
    return st[k]


def _take_per_man(conn, patron: int, org: int, day: int | None = None) -> float:
    st = _day_state(conn, day)["readings"] if day is not None else {}
    k = ("take", int(patron), org)
    if k not in st:
        take = conn.execute("SELECT COALESCE(SUM(weekly_take),0) FROM org_lines WHERE holder_actor_id=? AND status='active'", (int(patron),)).fetchone()[0]
        deps = conn.execute("SELECT COUNT(*) FROM org_seats WHERE superior_actor_id=? AND org_actor_id=? AND status='active'", (int(patron), org)).fetchone()[0]
        st[k] = float(take) / (deps + 1)
    return st[k]


def _better_patron(conn, a, seat, org, day: int | None = None) -> tuple[int | None, float]:
    """The man of his patron's own role who offers more per man, and how much more (0..1)."""
    cur = seat["superior_actor_id"]
    if cur is None:
        return None, 0.0
    cur_seat = seat_of(conn, int(cur), org)
    if cur_seat is None:  # his patron is dead or gone and no one has taken the place yet: there is no patron to compare
        return None, 0.0
    role = cur_seat["role_key"]
    own = _take_per_man(conn, int(cur), org, day)
    best, gap = None, 0.0
    for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active' AND actor_id<>? ORDER BY actor_id", (org, role, int(cur))).fetchall():
        t = _take_per_man(conn, int(r[0]), org, day)
        g = (t - own) / t if t > 0 else 0.0
        if g > gap + 1e-12 and is_living(conn, int(r[0])):
            best, gap = int(r[0]), g
    return best, clamp01(gap)


def _arrested(conn, a, day) -> float:
    n = conn.execute("SELECT COUNT(*) FROM custody WHERE actor_id=? AND since_day>=?", (int(a), int(day) - int(org_motives._fig(conn, "motive_recent_days", default=90)))).fetchone()[0]
    return 1.0 if n else 0.0


def _open_case(conn, a, day) -> float:
    return 1.0 if conn.execute("SELECT 1 FROM crime_reports WHERE offender_actor_id=? AND status='open' LIMIT 1", (int(a),)).fetchone() else 0.0


def _kin_tie(conn, a, day) -> float:
    return 1.0 if conn.execute("SELECT 1 FROM typed_relationship_facts WHERE status='active' AND relation_type='spouse' AND (actor_a_id=? OR actor_b_id=?) LIMIT 1",
                               (int(a), int(a))).fetchone() else 0.0


def _age_late(conn, a, day) -> float:
    age = om._age(conn, a, day)
    return 0.0 if age is None else clamp01((age - float(figure(conn, "hap_age_from", default=35))) / float(figure(conn, "hap_age_span", default=25)))


def _resentment(conn, a, day, seat, org) -> float:
    r = om._rel(conn, a, seat["superior_actor_id"])
    return 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0)


_DAY: dict = {"key": None, "memo": {}, "readings": {}}


def forget_readings() -> None:
    """Drop the day's shared readings (for tests that change a man's situation between readings on one day)."""
    _DAY.update(key=None, memo={}, readings={})


def _day_state(conn: sqlite3.Connection, day: int) -> dict:
    """What every man's reading shares on one day: the places' and pools' opportunity memo and each man's readings."""
    key = (org_motives.db_key(conn), int(day))
    if _DAY["key"] != key:
        _DAY.update(key=key, memo={}, readings={})
    return _DAY


def _ground(kind: str):
    def reader(conn, actor, day):
        c = _ctx(conn, actor)
        if c is None:
            return 0.0
        st = _day_state(conn, day)
        k = ("ground", kind, c[0]["unit_id"], c[1])  # the same for every man of a unit: the places, pools and weights are his unit's
        if k not in st["readings"]:
            pools = (_kinds(conn).get(kind) or {}).get("pools") or []
            st["readings"][k] = max((om.opportunity(conn, actor, day, loc, p, st["memo"]) for loc in om._places(conn, c[0]) for p in pools), default=0.0)
        return st["readings"][k]
    return reader


def _low_heat(conn, a, day, seat, org) -> float:
    """`outfit_motives.low_heat` (his precinct is paid and no open case names him), the precinct part worked out once per unit."""
    st = _day_state(conn, day)
    k = ("paid", org, seat["unit_id"])
    if k not in st["readings"]:
        places = om._places(conn, seat)
        precinct = om.precinct_for_location(conn, places[0]) if places else None
        st["readings"][k] = precinct is not None and conn.execute(
            "SELECT 1 FROM org_arrangements WHERE payer_kind='org' AND payer_id=? AND status='active' AND position_key LIKE ? LIMIT 1", (org, f"{precinct}:%")).fetchone() is not None
    return 1.0 if st["readings"][k] and not _open_case(conn, a, day) else 0.0


def _simple(fn):
    return lambda conn, actor, day: clamp01(fn(conn, actor, day))


_READER_FACTORIES = {
    "ambition": lambda k: _simple(lambda c, a, d: _drive(c, a, "ambition")),
    "boldness": lambda k: _simple(lambda c, a, d: _drive(c, a, "risk_tolerance")),
    "temper": lambda k: _simple(lambda c, a, d: _drive(c, a, "aggression")),
    "loyal": lambda k: _simple(lambda c, a, d: _drive(c, a, "loyalty")),
    "disloyal": lambda k: _simple(lambda c, a, d: 1.0 - _drive(c, a, "loyalty")),
    "lazy": lambda k: _simple(lambda c, a, d: 1.0 - _drive(c, a, "ambition")),
    "greed": lambda k: _r_ctx(lambda c, a, d, s, o: float(s["greed"])),
    "reliable": lambda k: _r_ctx(lambda c, a, d, s, o: float(s["reliability"])),
    "need": lambda k: om.need,
    "appetite": lambda k: om.appetite,
    "low_heat": lambda k: _r_ctx(lambda c, a, d, s, o: _low_heat(c, a, d, s, o)),
    "no_cover": lambda k: _r_ctx(lambda c, a, d, s, o: 1.0 - _low_heat(c, a, d, s, o)),
    "ground": _ground,
    "age_late": lambda k: _simple(_age_late),
    "kin_tie": lambda k: _simple(_kin_tie),
    "arrested": lambda k: _simple(_arrested),
    "open_case": lambda k: _simple(_open_case),
    "resentful": lambda k: _r_ctx(_resentment),
    "unit_short": lambda k: _r_ctx(_unit_short),
    "other_member": lambda k: _r_ctx(lambda c, a, d, s, o: 1.0 if _other_members(c, s, o, d) else 0.0),
    "better_offer": lambda k: _r_ctx(lambda c, a, d, s, o: _better_patron(c, a, s, o, d)[1]),
}
_REGISTERED: set = set()


def _cached(name: str, fn):
    """A reading of a man on a day is worked out once however many kinds use it."""
    def reader(conn, actor, day):
        r = _day_state(conn, day)["readings"]
        k = (int(actor), name)
        if k not in r:
            r[k] = fn(conn, actor, day)
        return r[k]
    return reader


def _ensure_readers(conn: sqlite3.Connection) -> None:
    for kind, spec in _kinds(conn).items():
        names = [m["name"] for m in (org_motives._sphere_data(conn).get("motives") or {}).get(f"hap_{kind}", [])] + list(spec.get("requires") or [])
        for n in names:
            if (kind, n) not in _REGISTERED and n in _READER_FACTORIES:
                org_motives.register_motive(f"hap_{kind}", n, _cached(n if n != "ground" else f"ground:{kind}", _READER_FACTORIES[n](kind)))
                _REGISTERED.add((kind, n))


def kind_weights(conn: sqlite3.Connection, actor_id: int, day: int) -> dict[str, float]:
    """Each kind's weight for this man today: base * (floor + pressure), 0 when a required reader reads 0."""
    _ensure_readers(conn)
    out: dict[str, float] = {}
    for kind, spec in _kinds(conn).items():
        if any((org_motives._READERS.get((f"hap_{kind}", r)) or (lambda *_: 0.0))(conn, int(actor_id), int(day)) <= 0.0 for r in spec.get("requires") or []):
            out[kind] = 0.0
            continue
        p, _ = org_motives.pressure(conn, int(actor_id), int(day), f"hap_{kind}")
        out[kind] = _v(conn, spec["weight"]) * (float(spec.get("floor", 0.5)) + p)
    return out


def draw_kind(conn: sqlite3.Connection, actor_id: int, day: int) -> str | None:
    w = kind_weights(conn, actor_id, day)
    total = sum(w.values())
    if total <= 0:
        return None
    pick = _rng(conn, "kind", actor_id, day).random() * total
    for k in sorted(w):
        pick -= w[k]
        if pick < 0:
            return k
    return sorted(w)[-1]


# ---- records ----

def _record(conn, day, kind, offender, *, victim=None, line=None, loc=None, matters=0, raised=None, status="done", **meta) -> int:
    return int(conn.execute(
        """INSERT INTO org_incidents(day,kind,offender_actor_id,victim_actor_id,victim_line_id,location_id,matters,raised_to_org_actor_id,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (int(day), kind, int(offender), victim, line, loc, int(matters), raised, status, json.dumps(meta, sort_keys=True, default=str))).lastrowid)


def _ground_of(conn, seat):
    r = conn.execute("SELECT ground_location_id FROM org_units WHERE id=?", (seat["unit_id"],)).fetchone() if seat["unit_id"] else None
    return None if r is None else r[0]


def _pass_up(conn, a, org, seat, amount: float, day: int, purpose: str) -> float:
    sup = seat["superior_actor_id"]
    flows = org_motives.upward_flows(conn)
    if sup is None or amount <= 0:
        return 0.0
    paid = ledger.transfer(conn, ("person", int(a)), ("person", int(sup)), amount, flow_kind="tribute", purpose=purpose, allow_partial=True)
    if paid > 0 and flows:
        conn.execute("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,amount,org_actor_id) VALUES (?,?,?,?,?,?)", (int(day), flows[0], int(a), int(sup), paid, org))
    return paid


def _span(conn, lo_key: str, hi_key: str, rng: random.Random) -> float:
    lo, hi = float(figure(conn, lo_key)), float(figure(conn, hi_key))
    return lo + (hi - lo) * rng.random()


# ---- good ----

def _do_score(conn, a, seat, org, day, rng, spec, **o):
    amt = round(_span(conn, spec["take"][0], spec["take"][1], rng), 2)
    ledger.receive(conn, ("person", a), amt, purpose="a score")
    up = _pass_up(conn, a, org, seat, amt * float(figure(conn, spec["up_share"])), day, "a score kicked up")
    _gain(conn, seat, float(figure(conn, spec["standing"])))
    return {"take": amt, "kicked_up": up, "summary": f"{_name(conn, a)} made a score of ${amt:,.0f}."}


def _small_line(conn, a, seat, org, day, pool, weekly, counterpart, loc) -> int:
    from . import outfit_money
    total = float((outfit_money.design_pools(conn).get(pool) or {}).get("default_m") or 0.0) * 1_000_000.0
    holding = conn.execute("INSERT INTO org_holdings(org_actor_id,pool_key,share_pct,yearly_take,source,started_day) VALUES (?,?,?,?,'started',?)",
                           (org, pool, round(100.0 * weekly * 52.0 / total, 4) if total > 0 else 0.0, weekly * 52.0, int(day))).lastrowid
    under = org_motives._sphere_data(conn).get("under_patron") or []
    holder = int(seat["superior_actor_id"]) if seat["role_key"] in under and seat["superior_actor_id"] else int(a)
    label = (org_motives._sphere_data(conn).get("line_kinds") or {}).get(pool, pool)
    place = conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()[0] if loc else "the ground"
    who = f" through {_name(conn, counterpart)}" if counterpart else ""
    line = int(conn.execute(
        "INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,location_id,weekly_take,hidden,started_day) VALUES (?,?,?,?,?,?,0,?)",
        (holding, seat["unit_id"], holder, f"{label} in {place}{who}", loc, weekly, int(day))).lastrowid)
    from . import org_tension
    org_tension.on_line_opened(conn, org, loc, a, int(day))
    return line


def _do_bring_earner(conn, a, seat, org, day, rng, spec, **o):
    pool = rng.choice(list(spec["pools"]))
    got, new_person = _taken(conn, a, "bring_earner", seat, org, day, spec, o)
    cp = got[0] if got else None
    weekly = float(figure(conn, spec["weekly"])) * (0.5 + rng.random())
    line = _small_line(conn, a, seat, org, day, pool, weekly, cp, _ground_of(conn, seat))
    if cp is not None and seat["superior_actor_id"] is not None:
        adjust_relationship(conn, int(seat["superior_actor_id"]), cp, int(day), familiarity_delta=10.0, trust_delta=5.0)
    _gain(conn, seat, float(figure(conn, spec["standing"])))
    return {"counterpart": cp, "line_id": line, "pool": pool, "weekly": weekly, "meta": {"counterpart": cp, "new_person": bool(new_person and cp is not None)},
            "summary": f"{_name(conn, a)} brought a new line ({pool}) under {_name(conn, seat['superior_actor_id'])}."}


def _do_proves_himself(conn, a, seat, org, day, rng, spec, **o):
    _gain(conn, seat, float(figure(conn, spec["standing"])))
    if seat["superior_actor_id"] is not None:
        adjust_relationship(conn, int(seat["superior_actor_id"]), a, int(day), trust_delta=float(figure(conn, spec["trust"])),
                            respect_delta=float(figure(conn, spec["trust"])) / 2.0)
    return {"summary": f"{_name(conn, a)} did a job cleanly."}


def _recruit_request(conn, a, seat, org, day, spec) -> tuple:
    """(name group, sex, ages, subtype, criminal weight) of the man he would bring in, from the run seed."""
    from .outfit_opening import seat_subtype
    rng = _rng(conn, "recruit_params", a, day)
    op = _opening(conn, org)
    spec_o = (op.get("roles") or {}).get(seat["role_key"]) or {}
    male = float((org_motives._sphere_data(conn).get("male_share") or {}).get(spec_o.get("male_share_key"), 1.0))
    key = conn.execute("SELECT package_key FROM org_profiles WHERE org_actor_id=?", (org,)).fetchone()[0]
    ospec = (org_motives._sphere_data(conn).get("outfits") or {}).get(key) or {}
    inst = conn.execute("SELECT name FROM actors WHERE id=?", (org,)).fetchone()[0]
    group = ospec.get("name_group") if rng.random() < float(op.get("own_group_share", 1.0)) else None
    return (group, "male" if rng.random() < male else "female", tuple(int(x) for x in spec["ages"]),
            seat_subtype(seat["role_key"], inst, op.get("in_roles") or ()), float(spec_o.get("criminal_weight", 1.0)))


def _bring_request(conn, a, seat, org, day, spec) -> tuple:
    return (None, None, tuple(int(x) for x in spec["counterpart_ages"]), spec.get("counterpart_subtype"), 0.0)


_REQUESTS = {"recruits": _recruit_request, "bring_earner": _bring_request}


def _pull(conn, req: tuple, n: int, stream: str) -> list[int]:
    from .outfit_opening import pull_up
    group, sex, ages, subtype, cw = req
    return pull_up(conn, n, stream=stream, name_group=group, sex=sex, ages=ages, subtype=subtype, criminal_weight=cw)


def _counterparts_used(conn: sqlite3.Connection) -> set[int]:
    return {int(r[0]) for r in conn.execute("SELECT json_extract(metadata_json,'$.counterpart') FROM org_incidents WHERE kind='bring_earner'") if r[0] is not None}


def _nearby(conn, a, seat, day, spec, rng, used: set[int]) -> int | None:
    """An existing person who fits the counterpart (living, in the age band, not seated anywhere, not already a line's
    counterpart) in his unit's places or the city itself, or None."""
    from .outfit_opening import city_location
    places = list(dict.fromkeys([*om._places(conn, seat), city_location(conn)]))
    lo, hi = (int(x) for x in spec["counterpart_ages"])
    rows = conn.execute(
        "SELECT a.id,lp.birth_day FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.actor_type='character' AND a.status='active' "
        "AND COALESCE(lp.life_status,'living')='living' AND a.current_location_id IN (%s) AND lp.birth_day BETWEEN ? AND ? "
        "AND a.id NOT IN (SELECT actor_id FROM org_seats) ORDER BY a.id" % ",".join("?" * len(places)),
        (*places, int(day) - hi * 365, int(day) - lo * 365)).fetchall()
    fit = [int(r[0]) for r in rows if int(r[0]) not in used and not conn.execute(
        "SELECT 1 FROM typed_relationship_facts WHERE status='active' AND relation_type IN ('spouse','parent_of','child_of','sibling_of') AND (actor_a_id=? OR actor_b_id=?) "
        "AND (actor_a_id=? OR actor_b_id=?) LIMIT 1", (int(r[0]), int(r[0]), int(a), int(a))).fetchone()]
    return fit[rng.randrange(len(fit))] if fit else None


def _taken(conn, a, kind, seat, org, day, spec, o) -> tuple[list[int], bool]:
    """(who was brought for this man, whether he is a new person): from the weekly batch when there is one, otherwise
    an existing counterpart where one fits (bring_earner), otherwise one pulled up on its own."""
    batch = o.get("pulled")
    if batch is not None and a in batch:
        return batch[a]
    if kind == "bring_earner":
        near = _nearby(conn, a, seat, day, spec, _rng(conn, "nearby", a, day), _counterparts_used(conn))
        if near is not None:
            return [near], False
    return _pull(conn, _REQUESTS[kind](conn, a, seat, org, day, spec), 1, f"happening:{kind}:{a}:{day}"), True


def _do_recruits(conn, a, seat, org, day, rng, spec, **o):
    from .orgs import seat as seat_up
    from .outfit_opening import feelings_toward
    op = _opening(conn, org)
    spec_o = (op.get("roles") or {}).get(seat["role_key"]) or {}
    got, _new = _taken(conn, a, "recruits", seat, org, day, spec, o)
    if not got:
        return {"summary": "There was no one to pull up.", "skipped": True}
    new = got[0]
    st = spec_o.get("standing") or {"mean": 0.3, "sd": 0.2}
    seat_up(conn, new, org, seat["role_key"], unit_id=seat["unit_id"], superior_actor_id=seat["superior_actor_id"], level=int(seat["level"]), day=int(day),
            standing=clamp01(rng.gauss(float(st["mean"]), float(st["sd"]))), provenance="happening")
    if seat["superior_actor_id"] is not None:
        feelings_toward(conn, new, int(seat["superior_actor_id"]), int(day), rng)
    adjust_relationship(conn, new, a, int(day), familiarity_delta=10.0, trust_delta=8.0)
    _gain(conn, seat, float(figure(conn, spec["standing"])))
    return {"recruit": new, "meta": {"recruit": new, "new_person": True}, "summary": f"{_name(conn, a)} brought in {_name(conn, new)}."}


def _do_favour(conn, a, seat, org, day, rng, spec, **o):
    others = _other_members(conn, seat, org)
    if not others:
        return {"summary": "There was no one to do a favour for.", "skipped": True}
    other = others[rng.randrange(len(others))]
    adjust_relationship(conn, other, a, int(day), trust_delta=float(figure(conn, spec["trust"])), obligation_delta=float(figure(conn, spec["trust"])))
    adjust_relationship(conn, a, other, int(day), respect_delta=float(figure(conn, spec["trust"])) / 2.0)
    _gain(conn, seat, float(figure(conn, spec["standing"])))
    return {"for_actor": other, "summary": f"{_name(conn, a)} did {_name(conn, other)} a favour."}


# ---- neutral ----

def _do_drifts(conn, a, seat, org, day, rng, spec, **o):
    _gain(conn, seat, -float(figure(conn, spec["standing"])))
    return {"summary": f"{_name(conn, a)} drifted: earning less."}


def _do_goes_straight(conn, a, seat, org, day, rng, spec, **o):
    leave_life(conn, a, org, int(day))  # the seat goes `out` with the day, his profile DORMANT; the weekly lifecycle notes the history
    return {"summary": f"{_name(conn, a)} went straight."}


def _do_switches(conn, a, seat, org, day, rng, spec, **o):
    old = seat["superior_actor_id"]
    new = o.get("to")
    if new is None:
        new, _ = _better_patron(conn, a, seat, org)
    if new is None or old is None:
        return {"summary": "There was no one to switch to.", "skipped": True}
    ns = seat_of(conn, int(new), org)
    conn.execute("UPDATE org_seats SET superior_actor_id=?, unit_id=? WHERE id=?", (int(new), ns["unit_id"], int(seat["id"])))
    adjust_relationship(conn, int(old), a, int(day), resentment_delta=float(figure(conn, spec["resentment"])))
    return {"to": int(new), "summary": f"{_name(conn, a)} went to {_name(conn, new)}, leaving {_name(conn, old)}."}


# ---- wrong ----

def _victim_other_line(conn, a, seat, org, day, rng, spec):
    places = om._places(conn, seat)
    if not places:
        return None
    rows = conn.execute(
        "SELECT l.id,l.holder_actor_id,l.location_id,h.org_actor_id FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id "
        "WHERE h.org_actor_id<>? AND l.status='active' AND l.holder_actor_id IS NOT NULL AND l.location_id IN (%s) ORDER BY l.id" % ",".join("?" * len(places)),
        (org, *places)).fetchall()
    rows = [r for r in rows if is_living(conn, int(r[1]))]
    if not rows:
        return None
    r = rows[rng.randrange(len(rows))]
    return {"victim": int(r[1]), "line": int(r[0]), "loc": r[2], "org": int(r[3])}


def _seat_org(conn, actor, exclude):
    r = conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active' AND org_actor_id<>? ORDER BY org_actor_id LIMIT 1", (int(actor), exclude)).fetchone()
    return None if r is None else int(r[0])


def _victim_member(conn, a, seat, org, day, rng, spec):
    rows = [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id<>? AND status='active' AND inducted_day IS NOT NULL ORDER BY actor_id", (org,)) if is_living(conn, int(r[0]))]
    if not rows:
        return None
    v = rows[rng.randrange(len(rows))]
    return {"victim": v, "line": None, "loc": conn.execute("SELECT current_location_id FROM actors WHERE id=?", (v,)).fetchone()[0], "org": _seat_org(conn, v, org)}


def _victim_big_earner(conn, a, seat, org, day, rng, spec):
    big = float(figure(conn, spec["big_weekly"]))
    rows = conn.execute("SELECT l.id,l.holder_actor_id,l.location_id,h.org_actor_id FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id "
                        "WHERE h.org_actor_id<>? AND l.status='active' AND l.holder_actor_id IS NOT NULL AND l.weekly_take>=? ORDER BY l.id", (org, big)).fetchall()
    rows = [r for r in rows if is_living(conn, int(r[1]))]
    if not rows:
        return None
    r = rows[rng.randrange(len(rows))]
    return {"victim": int(r[1]), "line": None, "loc": r[2], "org": int(r[3])}


def _victim_officer(conn, a, seat, org, day, rng, spec):
    rows = [int(r[0]) for r in conn.execute("SELECT DISTINCT official_actor_id FROM org_arrangements WHERE status='active' ORDER BY official_actor_id") if is_living(conn, int(r[0]))]
    if not rows:
        return None
    v = rows[rng.randrange(len(rows))]
    return {"victim": v, "line": None, "loc": conn.execute("SELECT current_location_id FROM actors WHERE id=?", (v,)).fetchone()[0], "org": None}


def _victim_civilian(conn, a, seat, org, day, rng, spec):
    n = conn.execute("SELECT COUNT(*) FROM actors WHERE actor_type='character' AND status='active' AND id NOT IN (SELECT actor_id FROM org_seats)").fetchone()[0]
    if not n:
        return None
    r = conn.execute("SELECT id,current_location_id FROM actors WHERE actor_type='character' AND status='active' AND id NOT IN (SELECT actor_id FROM org_seats) "
                     "ORDER BY id LIMIT 1 OFFSET ?", (rng.randrange(n),)).fetchone()
    return {"victim": int(r[0]), "line": None, "loc": r[1], "org": None} if is_living(conn, int(r[0])) else None


_VICTIMS = {"other_line": _victim_other_line, "member": _victim_member, "big_earner": _victim_big_earner,
            "officer": _victim_officer, "civilian": _victim_civilian}


def _do_incident(conn, a, seat, org, day, rng, spec, victim_kind=None, **o):
    weights = {k: _v(conn, w) for k, w in (spec.get("victims") or {}).items()}
    if victim_kind is not None:
        weights = {victim_kind: 1.0}
    found: dict[str, dict] = {}
    for k in sorted(weights):
        if weights[k] > 0 and k in _VICTIMS:
            hit = _VICTIMS[k](conn, a, seat, org, day, rng, spec)
            if hit is not None:
                found[k] = hit
    if not found:
        return {"summary": "There was no one to hit.", "skipped": True}
    tot = sum(weights[k] for k in found)
    pick, chosen = rng.random() * tot, sorted(found)[-1]
    for k in sorted(found):
        pick -= weights[k]
        if pick < 0:
            chosen = k
            break
    return _apply_incident(conn, a, org, day, rng, spec, found[chosen], chosen)


def run_incident(conn, a: int, org: int, day: int, rng, victim: int, victim_org: int | None, kind: str = "squeeze") -> dict:
    """An incident aimed by the tension model: man `a` of `org` hurts `victim` (of `victim_org`); the same harm, record and answer as the weekly one."""
    spec = _kinds(conn).get("incident") or {}
    line = conn.execute("SELECT l.id,l.location_id FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE l.holder_actor_id=? AND l.status='active' "
                        "AND (? IS NULL OR h.org_actor_id=?) ORDER BY l.weekly_take DESC,l.id LIMIT 1", (int(victim), victim_org, victim_org)).fetchone()
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(victim),)).fetchone()
    hit = {"victim": int(victim), "line": line[0] if line else None, "loc": (loc[0] if loc and loc[0] is not None else (line[1] if line else None)), "org": victim_org}
    return _apply_incident(conn, int(a), int(org), int(day), rng, spec, hit, kind)


def _apply_incident(conn, a, org, day, rng, spec, hit, chosen) -> dict:
    v = hit["victim"]
    matters = 0 if chosen == "civilian" else 1
    raised = hit["org"] if matters and hit["org"] is not None else None
    iid = _record(conn, day, "incident", a, victim=v, line=hit["line"], loc=hit["loc"], matters=matters, raised=raised,
                  status="open" if raised is not None else "done", victim_kind=chosen, offender_org=org)
    from . import lethality, org_tension
    from .harm import record_harm
    vseats = conn.execute("SELECT org_actor_id,role_key,unit_id,superior_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (v,)).fetchall()
    key = conn.execute("SELECT package_key FROM org_profiles WHERE org_actor_id=?", (org,)).fetchone()
    key = key[0] if key else None
    sev, method, too_far = lethality.incident_roll(conn, key, _span(conn, spec["harm"][0], spec["harm"][1], rng), rng)
    harm = record_harm(conn, v, source_kind="org_incident", source_ref_id=iid, severity=round(sev, 2), intent_class="hostile", method=method,
                       location_id=hit["loc"], metadata={"offender_actor_id": a, "public": chosen == "officer", "went_too_far": too_far})
    if matters:
        org_tension.on_incident(conn, raised, org, a, v, chosen, int(day), too_far)
    by_sev = lethality.bystander_hurt(conn, key, method, rng) if too_far else None
    bystander = None
    if by_sev is not None:
        near = [int(r[0]) for r in conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' AND current_location_id IS ? AND id NOT IN (?,?) ORDER BY id",
                                                 (hit["loc"], a, v)) if is_living(conn, int(r[0]))]
        if near:
            bystander = near[rng.randrange(len(near))]
            record_harm(conn, bystander, source_kind="org_incident_bystander", source_ref_id=iid, severity=round(by_sev, 2), intent_class="accidental",
                        method=method, location_id=hit["loc"], metadata={"offender_actor_id": a, "public": True})
            imposed(conn, bystander)
    imposed(conn, a)
    if harm["outcome"] != "fatal":
        imposed(conn, v)
    if harm["outcome"] == "fatal" and matters:
        # a beating that went too far is a killing: the dead man's head answers a killing, not an incident
        conn.execute("UPDATE org_incidents SET status='done' WHERE id=?", (iid,))
        killed_across(conn, a, v, vseats, int(day))
    elif raised is not None:
        head = head_of(conn, raised)
        if head is not None and head != a:
            add_agenda(conn, head, "respond_incident", int(day) + int(figure(conn, spec["respond_delay"])), subject_kind="incident", subject_id=iid,
                       metadata={"incident": iid, "offender": a, "offender_org": org, "victim": v, "org": raised, "kind": "incident"})
    return {"incident_id": iid, "victim": v, "victim_kind": chosen, "matters": matters, "harm": harm["outcome"], "bystander": bystander,
            "summary": f"{_name(conn, a)} hit {_name(conn, v)} ({chosen}){' and killed him' if harm['outcome'] == 'fatal' else ''}."}


def _do_holds_out(conn, a, seat, org, day, rng, spec, **o):
    amt = round(_span(conn, spec["take"][0], spec["take"][1], rng), 2)
    ledger.receive(conn, ("person", a), amt, purpose="a collection kept back")
    return {"amount": amt, "meta": {"amount": amt}, "status": "open", "victim": seat["superior_actor_id"],
            "summary": f"{_name(conn, a)} kept ${amt:,.0f} back."}


def _do_busted(conn, a, seat, org, day, rng, spec, **o):
    days = int(round(_span(conn, spec["days"][0], spec["days"][1], rng)))
    conn.execute("INSERT INTO custody(actor_id,kind,charge,since_day,until_day) VALUES (?,'held',?,?,?)", (a, spec["charge"], int(day), int(day) + days))
    loc = _ground_of(conn, seat)
    conn.execute("INSERT INTO crime_reports(day,crime_kind,location_id,offender_actor_id,public,agency_profile_id,status,metadata_json) VALUES (?,?,?,?,0,?,'open',?)",
                 (int(day), spec["crime_kind"], loc, a, agency_for(conn, loc, spec["crime_kind"]), json.dumps({"source": "org_happening", "close_day": int(day) + days})))
    imposed(conn, a)
    mark_for_history(conn, a, "was arrested", int(day))
    return {"status": "done", "loc": loc, "summary": f"{_name(conn, a)} was picked up."}


def _do_informs(conn, a, seat, org, day, rng, spec, **o):
    sup = seat["superior_actor_id"]
    if sup is None:
        return {"summary": "He had no one to inform on.", "skipped": True}
    loc = _ground_of(conn, seat)
    from .crime_response import open_report  # an informant names the man: the law has a case it can work, and the evidence builds like any other
    open_report(conn, crime_kind=spec["crime_kind"], day=int(day), offender_actor_id=int(sup), location_id=loc,
                metadata={"source": "org_happening", "informant": a, "discovered": 0, "identified": True,
                          "close_day": int(day) + int(figure(conn, spec["report_days"]))})
    return {"status": "open", "victim": int(sup), "loc": loc, "summary": f"{_name(conn, a)} gave the police evidence on {_name(conn, sup)}."}


_DO = {"score": _do_score, "bring_earner": _do_bring_earner, "proves_himself": _do_proves_himself, "recruits": _do_recruits, "favour": _do_favour,
       "drifts": _do_drifts, "goes_straight": _do_goes_straight, "switches": _do_switches, "incident": _do_incident, "holds_out": _do_holds_out,
       "busted": _do_busted, "informs": _do_informs}


def happen(conn: sqlite3.Connection, actor_id: int, kind: str, day: int, **opts) -> dict | None:
    """Carry out one happening for a man (the weekly draw, or a test forcing a kind). Returns {kind, group, summary, incident_id, ...}."""
    spec = _kinds(conn).get(kind)
    c = _ctx(conn, int(actor_id))
    if spec is None or c is None or kind not in _DO:
        return None
    seat, org = c
    rng = _rng(conn, f"do:{kind}", actor_id, day)
    if "pulled" in opts:
        opts = {**opts, "pulled": (opts["pulled"] or {}).get(kind)}
    res = _DO[kind](conn, int(actor_id), seat, org, int(day), rng, spec, **opts) or {}
    res.update(kind=kind, group=spec["group"])
    if "incident_id" not in res and not res.get("skipped"):
        res["incident_id"] = _record(conn, day, kind, actor_id, victim=res.get("victim"), loc=res.get("loc"), status=res.get("status", "done"),
                                     group=spec["group"], summary=res.get("summary"), **{k: v for k, v in (res.get("meta") or {}).items()})
    return res


# ---- the weekly check-ups (a man kept money back; a report names his patron; a short arrest ends) ----

def _roll(conn, stream: str, key: int, day: int) -> float:
    return random.Random(f"{run_seed(conn)}:happening:{stream}:{int(key)}:{int(day)}").random()


def notice_holdouts(conn: sqlite3.Connection, day: int) -> int:
    spec = _kinds(conn).get("holds_out") or {}
    n = 0
    for r in conn.execute("SELECT * FROM org_incidents WHERE kind='holds_out' AND status='open' ORDER BY id").fetchall():
        a, sup = int(r["offender_actor_id"]), r["victim_actor_id"]
        if not is_living(conn, a):
            conn.execute("UPDATE org_incidents SET status='lapsed' WHERE id=?", (r["id"],))
            continue
        if _roll(conn, "notice", r["id"], day) >= float(figure(conn, spec["notice_week"])):
            continue
        amt = float(json.loads(r["metadata_json"]).get("amount") or 0.0)
        back = ledger.transfer(conn, ("person", a), ("person", int(sup)), min(amt, ledger.balance(conn, ("person", a))), flow_kind="tribute",
                               purpose="what he kept back", allow_partial=True) if sup is not None and amt > 0 and ledger.balance(conn, ("person", a)) > 0 else 0.0
        c = _ctx(conn, a)
        if c is not None:
            _gain(conn, c[0], -float(figure(conn, spec["standing"])))
        if sup is not None:
            adjust_relationship(conn, int(sup), a, int(day), resentment_delta=float(figure(conn, spec["resentment"])), trust_delta=-float(figure(conn, spec["resentment"])))
        conn.execute("UPDATE org_incidents SET status='noticed' WHERE id=?", (r["id"],))
        imposed(conn, a)  # his patron has found out: he is looked at tomorrow
        if c is not None:  # and the man who decides about him (his patron) gets `discipline` about him
            from .org_membership import discipline_for_holdout
            discipline_for_holdout(conn, a, int(c[0]["org_actor_id"]), amt, int(r["day"]), int(r["id"]), int(day))
        n += 1
    return n


def discover_informers(conn: sqlite3.Connection, day: int, force: bool = False) -> int:
    spec = _kinds(conn).get("informs") or {}
    n = 0
    for r in conn.execute("SELECT id,offender_actor_id,metadata_json FROM crime_reports WHERE status IN ('open','buried','arrest') AND json_extract(metadata_json,'$.informant') IS NOT NULL "
                          "AND COALESCE(json_extract(metadata_json,'$.discovered'),0)=0 ORDER BY id").fetchall():
        if not force and _roll(conn, "discover", r["id"], day) >= float(figure(conn, spec["discover_week"])):
            continue
        meta = json.loads(r["metadata_json"])
        meta["discovered"] = 1
        conn.execute("UPDATE crime_reports SET metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), r["id"]))
        inf, sup = int(meta["informant"]), int(r["offender_actor_id"])
        c = _ctx(conn, inf)
        org = c[1] if c else _seat_org(conn, inf, -1)
        imposed(conn, sup)  # the superior the evidence names
        imposed(conn, inf)
        inc = conn.execute("SELECT id FROM org_incidents WHERE kind='informs' AND offender_actor_id=? AND status='open' ORDER BY id DESC LIMIT 1", (inf,)).fetchone()
        if inc is not None and org is not None:
            conn.execute("UPDATE org_incidents SET matters=1, raised_to_org_actor_id=? WHERE id=?", (org, inc[0]))
            head = head_of(conn, org)
            if head is not None:
                add_agenda(conn, head, "respond_incident", int(day) + int(figure(conn, spec["respond_delay"])), subject_kind="incident", subject_id=int(inc[0]),
                           metadata={"incident": int(inc[0]), "offender": inf, "offender_org": org, "victim": sup, "org": org, "kind": "informs"})
        n += 1
    return n


def close_old(conn: sqlite3.Connection, day: int) -> None:
    """A short arrest ends; a report this layer opened closes when its time is up."""
    from . import org_temperament
    for (a,) in conn.execute("SELECT actor_id FROM custody WHERE kind='held' AND until_day IS NOT NULL AND until_day<=? AND case_id IS NULL AND agency_profile_id IS NULL ORDER BY actor_id", (int(day),)).fetchall():
        org_temperament.drift(conn, int(a), "prison", int(day))
    conn.execute("UPDATE custody SET kind='released' WHERE kind='held' AND until_day IS NOT NULL AND until_day<=? AND case_id IS NULL AND agency_profile_id IS NULL", (int(day),))
    conn.execute("UPDATE crime_reports SET status='closed' WHERE status='open' AND json_extract(metadata_json,'$.source')='org_happening' "
                 "AND json_extract(metadata_json,'$.close_day')<=?", (int(day),))


# ---- the weekly process ----

def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    if not _kinds(conn):
        return None
    due = (int(after_day) // WEEK + 1) * WEEK
    return due if due <= int(end_day) else None


def _roster(conn: sqlite3.Connection) -> list[int]:
    roles = _dependent_roles(conn)
    if not roles:
        return []
    out: list[int] = []
    for kind, role in sorted(roles.items()):
        for r in conn.execute(
                """SELECT s.actor_id FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id JOIN actors a ON a.id=s.actor_id
                   LEFT JOIN actor_life_profiles lp ON lp.actor_id=s.actor_id
                   WHERE p.org_kind=? AND s.role_key=? AND s.status='active' AND COALESCE(lp.life_status,'living')='living'
                     AND lower(COALESCE(a.status,'active')) NOT IN ('dead','deceased','historical')
                     AND NOT EXISTS (SELECT 1 FROM custody c WHERE c.actor_id=s.actor_id AND c.kind='held')
                   ORDER BY s.actor_id""", (kind, role)):
            out.append(int(r[0]))
    return sorted(set(out))


def _pull_batches(conn: sqlite3.Connection, plan: list[tuple[int, str]], day: int) -> dict[str, dict[int, tuple[list[int], bool]]]:
    """The people this week's happenings pull up, one batch per kind of request (each pull-up scans the city's
    candidates once however many it is asked for): {kind: {man: [pulled ids]}}."""
    out: dict = {}
    for kind, fn in _REQUESTS.items():
        spec = _kinds(conn).get(kind)
        groups: dict[tuple, list[int]] = {}
        used = _counterparts_used(conn) if kind == "bring_earner" else set()
        for a, k in plan:
            c = _ctx(conn, a) if k == kind else None
            if c is None:
                continue
            if kind == "bring_earner":  # an existing person where one fits; a new one only when none does
                near = _nearby(conn, a, c[0], day, spec, _rng(conn, "nearby", a, day), used)
                if near is not None:
                    used.add(near)
                    out.setdefault(kind, {})[a] = ([near], False)
                    continue
            groups.setdefault(fn(conn, a, c[0], c[1], day, spec), []).append(a)
        for i, (req, men) in enumerate(sorted(groups.items(), key=lambda kv: repr(kv[0]))):
            ids = _pull(conn, req, len(men), f"happening:{kind}:{day}:{i}")
            for j, m in enumerate(men):
                out.setdefault(kind, {})[m] = ([ids[j]] if j < len(ids) else [], True)
    return out


def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None, only_checks: bool = False) -> dict:
    data = _data(conn)
    if not data.get("kinds"):
        return {}
    out: dict = {}
    close_old(conn, day)
    out["noticed"] = notice_holdouts(conn, day)
    out["discovered"] = discover_informers(conn, day)
    if only_checks:
        return out
    rate = _v(conn, data["week_rate"])
    plan: list[tuple[int, str]] = []
    for a in _roster(conn):
        if org_motives._roll(conn, a, int(day), "happening") >= rate:  # the one point where a man's seeded draw is made (tests patch it)
            continue
        kind = draw_kind(conn, a, int(day))
        if kind is not None:
            plan.append((a, kind))
    pulled = _pull_batches(conn, plan, int(day))
    for a, kind in plan:
        res = happen(conn, a, kind, int(day), pulled=pulled)
        if res and not res.get("skipped"):
            out[kind] = out.get(kind, 0) + 1
    from . import org_temperament, org_tension
    for act, n in org_tension.process_due(conn, int(day)).items():
        out[f"tension:{act}"] = n
    from . import org_council, org_dealings, org_informing
    for mod in (org_council, org_dealings, org_informing):
        out.update(mod.process_due(conn, int(day)))
    if int(day) // WEEK % 52 == 0:
        org_temperament.age_year(conn, int(day))
    return out


# ---- the heads' agenda: respond_incident, pay_or_refuse ----

def _utility(conn: sqlite3.Connection, x: float) -> float:
    return float(figure(conn, "org_choice_utility_base", default=8.0)) + float(figure(conn, "org_choice_utility_span", default=10.0)) * clamp01(x)


def _carry(payload: dict) -> dict:
    """What a new agenda item takes over from the one just answered: not its agenda id (the provider sets the new item's own)."""
    return {k: v for k, v in payload.items() if k != "agenda_id"}


def _finish(conn, payload, day, status: str | None = None) -> None:
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))
    if status and payload.get("incident_id") is not None:
        conn.execute("UPDATE org_incidents SET status=? WHERE id=?", (status, int(payload["incident_id"])))


def respond_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = json.loads(item["metadata_json"] or "{}")
    spec = _kinds(conn).get(meta.get("kind") or "incident") or {}
    allowed = spec.get("responses") or ["sit_down", "kill_offender", "let_it_go"]
    off = int(meta["offender"])
    if not is_living(conn, off):
        return [{"kind": "let_it_go", "utility": _utility(conn, 1.0), "rationale": "The man is already dead.", "payload": {**meta, "incident_id": meta["incident"]}}]
    aggr = om._drive(conn, actor_id, "aggression")
    ohead = head_of(conn, int(meta["offender_org"])) if meta.get("offender_org") else None
    xs = {"sit_down": float(figure(conn, "hap_resp_sit")) if ohead not in (None, actor_id) else 0.0,
          "kill_offender": float(figure(conn, "hap_resp_kill")) * (0.25 + aggr) if off != int(actor_id) else 0.0,  # a man does not have himself dealt with
          "let_it_go": float(figure(conn, "hap_resp_let")) * (1.25 - aggr)}
    payload = {**meta, "incident_id": int(meta["incident"])}
    why = {"sit_down": f"Asks {_name(conn, ohead)} to sit down over {_name(conn, off)}.", "kill_offender": f"Has {_name(conn, off)} dealt with.",
           "let_it_go": f"Lets what {_name(conn, off)} did go."}
    return [{"kind": k, "utility": _utility(conn, xs[k]), "rationale": why[k], "payload": payload, **({"target_actor_id": off} if k == "kill_offender" else {})}
            for k in allowed if xs.get(k, 0.0) > 0.0]


def execute_sit_down(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day, "sat_down")
    ohead = head_of(conn, int(payload["offender_org"]))
    if ohead is None or ohead == int(actor_id):
        return {"summary": "There was no one to sit down with.", "blocked": True}
    spec = _kinds(conn).get("incident") or {}
    weeks = int(round(_span(conn, "hap_pay_weeks_lo", "hap_pay_weeks_hi", _rng(conn, "weeks", payload["incident_id"], day))))
    add_agenda(conn, ohead, "pay_or_refuse", int(day) + int(figure(conn, spec.get("respond_delay", "hap_respond_delay"))), subject_kind="incident",
               subject_id=int(payload["incident_id"]), metadata={**_carry(payload), "from": int(actor_id), "weeks": weeks})
    imposed(conn, ohead)  # the demand lands on him
    adjust_relationship(conn, int(actor_id), ohead, int(day), familiarity_delta=5.0, respect_delta=float(figure(conn, "hap_resp_sit_respect")))
    return {"summary": f"{_name(conn, actor_id)} asked {_name(conn, ohead)} to sit down."}


def execute_kill_offender(conn, actor_id, kind, payload, day):
    from .outfit_choices import kill
    off = int(payload["offender"])
    if not is_living(conn, off):
        _finish(conn, payload, day, "let_go")
        return {"summary": "The man was already dead.", "blocked": True}
    _finish(conn, payload, day, "killed")
    ohead = head_of(conn, int(payload["offender_org"])) if payload.get("offender_org") else None
    if ohead is not None and ohead != int(actor_id):
        adjust_relationship(conn, ohead, int(actor_id), int(day), resentment_delta=float(figure(conn, "hap_resp_kill_resentment")),
                            fear_delta=float(figure(conn, "hap_resp_kill_resentment")) / 2.0)
    return {"summary": kill(conn, int(actor_id), off, int(day), sanctioned=True, fallible=True)}


def execute_let_go(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day, "let_go")
    ohead = head_of(conn, int(payload["offender_org"])) if payload.get("offender_org") else None
    if ohead is not None and ohead != int(actor_id):
        adjust_relationship(conn, ohead, int(actor_id), int(day), respect_delta=-float(figure(conn, "hap_resp_let_respect")))
    return {"summary": f"{_name(conn, actor_id)} let it go."}


def pay_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = json.loads(item["metadata_json"] or "{}")
    aggr = om._drive(conn, actor_id, "aggression")
    payload = {**meta, "incident_id": int(meta["incident"])}
    return [{"kind": "pay", "utility": _utility(conn, float(figure(conn, "hap_pay_w")) * (1.25 - aggr)), "rationale": "Pays what is asked.", "payload": payload},
            {"kind": "refuse", "utility": _utility(conn, float(figure(conn, "hap_refuse_w")) * (0.25 + aggr)), "rationale": "Refuses.", "payload": payload}]


def execute_pay(conn, actor_id, kind, payload, day):
    vh = int(payload["from"])
    line = conn.execute("SELECT weekly_take FROM org_lines WHERE id=(SELECT victim_line_id FROM org_incidents WHERE id=?)", (int(payload["incident_id"]),)).fetchone()
    weekly = float(line[0]) if line and line[0] else float(figure(conn, "hap_pay_default_weekly"))
    amount = weekly * int(payload["weeks"])
    paid = ledger.transfer(conn, ("person", int(actor_id)), ("person", vh), amount, flow_kind="tribute", purpose="making good an incident", allow_partial=True)
    if paid <= 0:
        return execute_refuse(conn, actor_id, "refuse", payload, day)
    _finish(conn, payload, day, "paid")
    if paid < amount and payload.get("offender_org") is not None and payload.get("org") is not None:
        from . import org_dealings
        org_dealings.owe(conn, int(payload["org"]), int(payload["offender_org"]), amount - paid, "redress he could only part pay", int(day))
    adjust_relationship(conn, vh, int(actor_id), int(day), respect_delta=float(figure(conn, "hap_resp_sit_respect")), resentment_delta=-float(figure(conn, "hap_resp_sit_respect")))
    if payload.get("offender_org") is not None and payload.get("org") is not None:
        from . import org_tension
        org_tension.on_answer(conn, int(payload["org"]), int(payload["offender_org"]), "paid", int(day), actor=int(actor_id))
        org_tension.on_answer(conn, int(payload["offender_org"]), int(payload["org"]), "paid", int(day), actor=int(actor_id))
    return {"summary": f"{_name(conn, actor_id)} paid {_name(conn, vh)} ${paid:,.0f}."}


def execute_refuse(conn, actor_id, kind, payload, day):
    vh = int(payload["from"])
    _finish(conn, payload, day, "refused")
    adjust_relationship(conn, vh, int(actor_id), int(day), resentment_delta=float(figure(conn, "hap_resp_kill_resentment")),
                        respect_delta=-float(figure(conn, "hap_resp_let_respect")))
    imposed(conn, vh)  # the refusal lands on the man who asked
    if payload.get("offender_org") is not None and payload.get("org") is not None:
        from . import org_tension
        org_tension.on_answer(conn, int(payload["org"]), int(payload["offender_org"]), "refused_redress", int(day), actor=int(actor_id))
    if payload.get("killer_org") is not None and payload.get("victim") is not None:
        _again(conn, vh, payload, day, redress_refused=True, peace_refused=bool(payload.get("peace_refused")))  # redress for a killing was refused: it is his to answer again
    return {"summary": f"{_name(conn, actor_id)} refused {_name(conn, vh)}."}


# ---- a killing across organisations: the dead man's head answers ----

def _killing(conn: sqlite3.Connection) -> dict:
    return _data(conn).get("killing") or {}


def killed_across(conn: sqlite3.Connection, killer: int, victim: int, seats, day: int, sanctioned: bool = True, ordered_by: int | None = None) -> None:
    """A man was killed. The world notices: heat is written on the organisations involved, the pairs' tension moves, the dead man's unit and
    kin are changed by it, other heads weigh the wake. For each organisation the killer (or the man who sent him) holds no seat in, the
    dead man's head (when it has one) gets a `respond_killing` item, a `killing` incident is recorded, and the head and the dead man's
    superior are imposed on. A killing by a man with no seat and no one who sent him is the dead man's head's to hunt (`discipline_hunt`)."""
    data = _killing(conn)
    if not data:
        return
    from . import org_heat, org_temperament, org_tension
    mine = {int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (int(killer),))}
    if ordered_by is not None and int(ordered_by) != int(killer):
        sent = {int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (int(ordered_by),))}
        if sent and not (mine & sent):  # a man hired from outside: the dead man's head answers whoever hired him
            mine, killer = sent, int(ordered_by)
        elif not mine:
            mine = sent
    victim_orgs = sorted({int(s["org_actor_id"]) for s in seats})
    foreign = [o for o in victim_orgs if o not in mine]
    role = seats[0]["role_key"] if seats else None
    if org_heat.enabled(conn):
        org_heat.on_killing(conn, mine, victim_orgs, org_tension._rank(conn, role), int(day), public=bool(foreign), civilian=not seats)
    for s in seats:
        org = int(s["org_actor_id"])
        org_tension.on_death(conn, int(victim), org, s["role_key"], int(day), killed_by_org=min(mine) if mine and org not in mine else None)
        if s["unit_id"]:
            for (mate,) in conn.execute("SELECT actor_id FROM org_seats WHERE unit_id=? AND status='active' AND actor_id<>? ORDER BY actor_id", (int(s["unit_id"]), int(victim))).fetchall():
                org_temperament.drift(conn, int(mate), "unit_loss", int(day))
    for kin, kind in conn.execute(
            """SELECT CASE WHEN actor_a_id=? THEN actor_b_id ELSE actor_a_id END,kin_kind FROM kinship_links WHERE (actor_a_id=? OR actor_b_id=?)
               AND legal_status='recognized' AND ended_day IS NULL AND kin_kind IN ('parent','child','sibling','spouse')""", (int(victim), int(victim), int(victim))).fetchall():
        if is_living(conn, int(kin)):
            close = _v(conn, (((org_temperament.data(conn).get("drift") or {}).get("kin_killed")) or {}).get("close_scale"), 1.0) if kind in ("parent", "child") else 1.0
            org_temperament.drift(conn, int(kin), "kin_killed", int(day), close)
    if not mine:
        for org in victim_orgs:
            head = head_of(conn, org)
            if head is not None and head != int(victim):
                add_agenda(conn, head, "discipline_hunt", int(day) + int(figure(conn, data["delay"])), subject_kind="actor", subject_id=int(killer),
                           metadata={"victim": int(victim), "org": org, "head_wants": 0.0, "outsider": True})
                imposed(conn, head)
        return
    for s in seats:
        org = int(s["org_actor_id"])
        if org in mine:
            continue
        org_tension.on_killing(conn, int(killer), int(victim), org, mine, s["role_key"], bool(sanctioned), int(day))
        head = head_of(conn, org)
        sup = s["superior_actor_id"]
        if sup is not None:
            imposed(conn, int(sup))
        if head is None or head == int(killer):
            continue
        iid = _record(conn, day, "killing", killer, victim=int(victim), matters=1, raised=org, status="open",
                      killer_org=min(mine), role=s["role_key"])
        imposed(conn, head)
        add_agenda(conn, head, "respond_killing", int(day) + int(figure(conn, data["delay"])), subject_kind="actor", subject_id=int(victim),
                   metadata={"incident": iid, "killer": int(killer), "killer_org": min(mine), "org": org, "victim": int(victim), "role": s["role_key"],
                             "sanctioned": bool(sanctioned)})


def _size(conn, org: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND status='active'", (org,)).fetchone()[0])


def _had_sit_down(conn, victim: int) -> bool:
    return conn.execute("SELECT 1 FROM org_incidents WHERE offender_actor_id=? AND status IN ('sat_down','paid','refused') LIMIT 1", (int(victim),)).fetchone() is not None


def _kin_wanting(conn, victim: int) -> float:
    """Living close kin of the dead man (parents, children, siblings, spouse), 0..1 with two or more counting full."""
    kin = {int(r[0]) for r in conn.execute(
        """SELECT CASE WHEN actor_a_id=? THEN actor_b_id ELSE actor_a_id END FROM kinship_links
           WHERE (actor_a_id=? OR actor_b_id=?) AND legal_status='recognized' AND ended_day IS NULL AND kin_kind IN ('parent','child','sibling','spouse')""",
        (victim, victim, victim))}
    return clamp01(sum(1 for k in kin if is_living(conn, k)) / 2.0)


def _on_own_ground(conn, victim: int, org: int) -> float:
    """1 when the man was killed on the ground of his own unit: an insult as well as a loss."""
    r = conn.execute("""SELECT 1 FROM org_seats s JOIN org_units u ON u.id=s.unit_id JOIN actors a ON a.id=s.actor_id
                        WHERE s.actor_id=? AND s.org_actor_id=? AND a.current_location_id IS NOT NULL AND u.ground_location_id=a.current_location_id LIMIT 1""", (victim, org)).fetchone()
    return 1.0 if r else 0.0


def _cost(conn: sqlite3.Connection) -> dict:
    """The package's cost figures for answering a killing (outfits data `happenings.killing.cost`); every key is required."""
    return _killing(conn)["cost"]


def _need(conn, key: str) -> float:
    return _v(conn, _cost(conn)[key])


def _recent_killings(conn, day: int, *, org: int | None = None, killer_org: int | None = None, either: int | None = None) -> list:
    """The killings across outfits recorded within the lookback (data `cost.lookback_days`): a weight over memory, not a gate. `org` is the
    outfit that lost the man, `killer_org` the one that did it, `either` an outfit on either side."""
    since = int(day) - int(_need(conn, "lookback_days"))
    sql = "SELECT day,raised_to_org_actor_id,json_extract(metadata_json,'$.killer_org'),victim_actor_id FROM org_incidents WHERE kind='killing' AND day>=?"
    args: list = [since]
    if org is not None:
        sql += " AND raised_to_org_actor_id=?"
        args.append(int(org))
    if killer_org is not None:
        sql += " AND json_extract(metadata_json,'$.killer_org')=?"
        args.append(int(killer_org))
    if either is not None:
        sql += " AND (raised_to_org_actor_id=? OR json_extract(metadata_json,'$.killer_org')=?)"
        args += [int(either), int(either)]
    return conn.execute(sql, args).fetchall()


def _sees(conn, a: int | None, b: int | None) -> float:
    """How well one head thinks of another, 0..1 (respect and trust)."""
    r = om._rel(conn, a, b)
    return 0.0 if r is None else clamp01((float(r["respect"]) + float(r["trust"])) / 200.0)


def _third_heads(conn, org: int, other: int) -> list[tuple[int, int]]:
    """(head, size) of every other outfit of the same kind, from the data."""
    out = []
    for (o,) in conn.execute("SELECT org_actor_id FROM org_profiles WHERE org_actor_id NOT IN (?,?) AND org_kind=(SELECT org_kind FROM org_profiles WHERE org_actor_id=?) ORDER BY org_actor_id",
                             (int(org), int(other), int(org))).fetchall():
        h = head_of(conn, int(o))
        if h is not None:
            out.append((int(h), _size(conn, int(o))))
    return out


def _cost_factors(conn, head: int, org: int, other: int, day: int, team: int) -> dict[str, float]:
    """What carrying on a feud would cost the head of `org` against `other`: men and earnings lost to them, both sides' losses, being the
    weaker side by men and by allies, law heat after recent killings, a thin purse (what has come to him within the lookback against what a team costs), his caution, his standing, and a third head both
    would hear out. Each is 0..1 against a data figure (`cost.*_full`); none is a ceiling on anything."""
    mine, theirs = _size(conn, org), _size(conn, other)
    taken_rows = _recent_killings(conn, day, org=org, killer_org=other)
    lost = len(taken_rows)
    their_lost = len(_recent_killings(conn, day, org=other, killer_org=org))
    ohead = head_of(conn, other)
    taken = [int(r[3]) for r in taken_rows if r[3] is not None]
    earn = 0.0
    if taken:
        q = ",".join("?" * len(taken))
        earn = float(conn.execute(f"SELECT COALESCE(SUM(weekly_take),0) FROM org_lines WHERE holder_actor_id IN ({q})", taken).fetchone()[0])
    total = float(conn.execute("SELECT COALESCE(SUM(l.weekly_take),0) FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active'", (org,)).fetchone()[0])
    allies_theirs = 0.0
    broker = 0.0
    for t, tsize in _third_heads(conn, org, other):
        clout = clamp01(tsize / max(1, mine, theirs))
        allies_theirs += max(0.0, _sees(conn, t, ohead) - _sees(conn, t, head)) * clout
        broker = max(broker, min(_sees(conn, head, t), _sees(conn, ohead, t)) * clout)
    seat = conn.execute("SELECT standing FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (int(head), int(org))).fetchone()
    price = _need(conn, "price_per_man") * max(1, int(team))
    since = int(day) - int(_need(conn, "lookback_days"))
    settled = conn.execute(
        """SELECT 1 FROM org_incidents WHERE kind='killing' AND day>=? AND status IN ('settled','paid')
           AND ((raised_to_org_actor_id=? AND json_extract(metadata_json,'$.killer_org')=?) OR (raised_to_org_actor_id=? AND json_extract(metadata_json,'$.killer_org')=?)) LIMIT 1""",
        (since, int(org), int(other), int(other), int(org))).fetchone()
    return {"lost": clamp01(lost / max(1, mine) / _need(conn, "lost_share_full")),
            "both_lost": clamp01((lost + their_lost) / max(1, mine + theirs) / _need(conn, "both_share_full")),
            "lost_earnings": clamp01(earn / total / _need(conn, "earn_full")) if total > 0 else 0.0,
            "weaker": clamp01(1.0 - mine / theirs) if theirs and mine < theirs else 0.0,
            "allies_theirs": clamp01(allies_theirs / _need(conn, "allies_full")),
            "heat_own": org_heat.own_factor(conn, org, day),
            "heat_city": org_heat.city_factor(conn, day),
            "cash_thin": clamp01(1.0 - float(conn.execute("SELECT COALESCE(SUM(amount),0) FROM org_money WHERE to_actor_id=? AND day>=?", (int(head), since)).fetchone()[0]) / price) if price > 0 else 0.0,
            "cautious": 1.0 - om._drive(conn, head, "aggression"),
            "secure": clamp01(float(seat["standing"]) / _need(conn, "standing_full")) if seat is not None else 0.0,
            "broker": broker,
            "broken_peace": 1.0 if settled else 0.0}


def _killing_factors(conn, head: int, meta: dict, day: int) -> dict[str, float]:
    victim, killer = int(meta["victim"]), int(meta["killer"])
    org, korg = int(meta["org"]), int(meta["killer_org"])
    rank = _v(conn, (_killing(conn).get("role_rank") or {}).get(meta.get("role")), 0.5)
    wrong = conn.execute("SELECT status FROM org_incidents WHERE offender_actor_id=? AND kind<>'killing' AND matters=1 AND status<>'done'", (victim,)).fetchall()
    khead = head_of(conn, korg)
    r = om._rel(conn, head, khead)
    mine, theirs = _size(conn, org), _size(conn, korg)
    f = {"always": 1.0, "victim_wrong": 1.0 if wrong else 0.0, "low_role": 1.0 - rank, "high_role": rank,
         "unsanctioned": 0.0 if meta.get("sanctioned", True) else 1.0, "kin": _kin_wanting(conn, victim),
         "humiliation": _on_own_ground(conn, victim, org),
         "refused_sit": 1.0 if any(w[0] == "refused" for w in wrong) else 0.0,
         "no_sit_down": 0.0 if _had_sit_down(conn, victim) else 1.0,
         "stronger": clamp01(1.0 - theirs / mine) if mine and theirs < mine else 0.0,
         "friendly": 0.0 if r is None else clamp01((float(r["respect"]) + float(r["trust"])) / 200.0),
         "resentful": 0.0 if r is None else clamp01(float(r["resentment"]) / 100.0),
         "temper": om._drive(conn, head, "aggression"),
         "redress_refused": 1.0 if meta.get("redress_refused") else 0.0, "peace_refused": 1.0 if meta.get("peace_refused") else 0.0}
    f.update(_cost_factors(conn, head, org, korg, day, _team_size(conn, meta)))
    return f


def _blend(conn, items, factors: dict[str, float]) -> float:
    """1 - prod(1 - weight x factor) over an answer's terms, scaled by (1 - the same blend over the terms marked `against`): a weighed
    counter-term takes a share off the answer, never down to a fixed ceiling and never to a fixed count."""
    rest = against = 1.0
    for m in items:
        t = clamp01(_v(conn, m["weight"])) * clamp01(factors.get(m["name"], 0.0))
        if m.get("against"):
            against *= 1.0 - t
        else:
            rest *= 1.0 - t
    return (1.0 - rest) * against


def _against(conn, items, factors: dict[str, float]) -> float:
    """The share the counter-terms take off an answer on their own: 1 - prod(1 - weight x factor) over `items`."""
    rest = 1.0
    for m in items:
        rest *= 1.0 - clamp01(_v(conn, m["weight"])) * clamp01(factors.get(m["name"], 0.0))
    return 1.0 - rest


def killing_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = json.loads(item["metadata_json"] or "{}")
    f = _killing_factors(conn, actor_id, meta, int(day))
    why = {"accept_killing": f"Lets the killing of {_name(conn, meta['victim'])} stand.",
           "demand_redress": f"Demands redress from {_name(conn, head_of(conn, int(meta['killer_org'])))} for {_name(conn, meta['victim'])}.",
           "sit_down_peace": f"Asks for a sit-down with {_name(conn, head_of(conn, int(meta['killer_org'])))} to end it over {_name(conn, meta['victim'])}.",
           "retaliate": f"Has {_name(conn, meta['killer'])} answered for {_name(conn, meta['victim'])}."}
    return [{"kind": k, "utility": _utility(conn, _blend(conn, _killing(conn)[k], f)), "rationale": why[k], "payload": {**meta, "incident_id": int(meta["incident"])}}
            for k in ("accept_killing", "demand_redress", "sit_down_peace", "retaliate") if _killing(conn).get(k)]


def _heads(conn, actor_id, payload):
    return int(actor_id), head_of(conn, int(payload["killer_org"]))


def execute_accept_killing(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day, "accepted")
    me, other = _heads(conn, actor_id, payload)
    pts = float(figure(conn, _killing(conn)["relation_points"]))
    if other is not None:
        adjust_relationship(conn, other, me, int(day), respect_delta=-pts)  # he let it go: he is thought weaker
        adjust_relationship(conn, me, other, int(day), resentment_delta=pts / 2.0)
    from . import org_tension
    org_tension.on_answer(conn, int(payload["org"]), int(payload["killer_org"]), "accepted", int(day), actor=me)
    return {"summary": f"{_name(conn, me)} let the killing of {_name(conn, payload['victim'])} stand."}


def execute_demand_redress(conn, actor_id, kind, payload, day):
    me, other = _heads(conn, actor_id, payload)
    _finish(conn, payload, day, "redress_asked")
    if other is None:
        return {"summary": "There was no one to ask.", "blocked": True}
    weeks = int(round(_span(conn, "hap_pay_weeks_lo", "hap_pay_weeks_hi", _rng(conn, "weeks", payload["incident_id"], day))))
    add_agenda(conn, other, "pay_or_refuse", int(day) + int(figure(conn, _killing(conn)["delay"])), subject_kind="incident", subject_id=int(payload["incident_id"]),
               metadata={**_carry(payload), "incident": int(payload["incident_id"]), "from": me, "weeks": weeks, "offender": int(payload["killer"]), "offender_org": int(payload["killer_org"])})
    imposed(conn, other)
    adjust_relationship(conn, me, other, int(day), resentment_delta=float(figure(conn, _killing(conn)["relation_points"])))
    return {"summary": f"{_name(conn, me)} asked {_name(conn, other)} to make good the killing of {_name(conn, payload['victim'])}."}


_KILLING_KEYS = ("incident", "killer", "killer_org", "org", "victim", "role", "sanctioned")


def _again(conn, head: int, payload: dict, day: int, **flag) -> None:
    """Put the killing back on the dead man's head's list after the other side said no, with what was refused marked in it."""
    meta = {k: payload[k] for k in _KILLING_KEYS if k in payload}
    meta.update(flag)
    add_agenda(conn, int(head), "respond_killing", int(day) + int(figure(conn, _killing(conn)["delay"])), subject_kind="actor", subject_id=int(payload["victim"]), metadata=meta)
    imposed(conn, int(head))


def execute_sit_down_peace(conn, actor_id, kind, payload, day):
    """The head asks the other head to sit down over the killing (through a third head both hear out where there is one). The other
    head weighs it with his own costs (data `killing.settle_accept`) against a draw from the run's seed; peace settles the matter
    and eases both, a refusal puts the matter back on the first head's list marked as refused."""
    me, other = _heads(conn, actor_id, payload)
    if other is None:
        _finish(conn, payload, day, "sat_down")
        return {"summary": "There was no one to sit down with.", "blocked": True}
    org, korg = int(payload["org"]), int(payload["killer_org"])
    f = _cost_factors(conn, other, korg, org, int(day), 1)
    f.update({"always": 1.0, "temper": om._drive(conn, other, "aggression")})
    p = _blend(conn, _killing(conn)["settle_accept"], f)
    pts = float(figure(conn, _killing(conn)["relation_points"]))
    imposed(conn, other)
    if _rng(conn, "peace", int(payload["incident_id"]), day).random() < p:
        _finish(conn, payload, day, "settled")
        adjust_relationship(conn, me, other, int(day), respect_delta=pts, resentment_delta=-pts, trust_delta=pts / 2.0)
        adjust_relationship(conn, other, me, int(day), respect_delta=pts, resentment_delta=-pts, trust_delta=pts / 2.0)
        from . import org_tension
        org_tension.on_answer(conn, org, korg, "settled", int(day), actor=me)
        org_tension.on_answer(conn, korg, org, "settled", int(day), actor=other)
        return {"summary": f"{_name(conn, me)} and {_name(conn, other)} sat down and settled the killing of {_name(conn, payload['victim'])}."}
    _finish(conn, payload, day, "peace_refused")
    adjust_relationship(conn, me, other, int(day), resentment_delta=pts, respect_delta=-pts / 2.0)
    from . import org_tension
    org_tension.on_answer(conn, org, korg, "refused_peace", int(day), actor=other)
    _again(conn, me, payload, day, redress_refused=bool(payload.get("redress_refused")), peace_refused=True)
    return {"summary": f"{_name(conn, other)} would not sit down with {_name(conn, me)} over {_name(conn, payload['victim'])}."}


def _team_size(conn, payload: dict) -> int:
    """How many men go after the killer: a base and more for the victim's rank (data `killing.team`). No cap on how often."""
    t = _killing(conn).get("team") or {}
    rank = _v(conn, (_killing(conn).get("role_rank") or {}).get(payload.get("role")), 0.5)
    return max(1, int(round(_v(conn, t.get("base"), 1.0) + _v(conn, t.get("rank"), 0.0) * rank)))


def execute_retaliate(conn, actor_id, kind, payload, day):
    from .outfit_choices import execute_order_hunt
    me, other = _heads(conn, actor_id, payload)
    _finish(conn, payload, day, "retaliated")
    team = _team_size(conn, payload)
    if other is not None:
        pts = float(figure(conn, _killing(conn)["retaliate_points"]))
        adjust_relationship(conn, me, other, int(day), resentment_delta=pts)
        adjust_relationship(conn, other, me, int(day), fear_delta=pts / 2.0, resentment_delta=pts / 2.0)
    res = execute_order_hunt(conn, me, "order_hunt", {"org": int(payload["org"]), "killer": int(payload["killer"]), "team": team, "retaliation": True}, int(day))
    return {"summary": f"{_name(conn, me)} had the killing of {_name(conn, payload['victim'])} answered: {res.get('summary', '')}"}


for _kind, _fn in (("sit_down", execute_sit_down), ("kill_offender", execute_kill_offender), ("let_it_go", execute_let_go),
                   ("pay", execute_pay), ("refuse", execute_refuse), ("accept_killing", execute_accept_killing),
                   ("demand_redress", execute_demand_redress), ("sit_down_peace", execute_sit_down_peace), ("retaliate", execute_retaliate)):
    register_executor(_kind, _fn)
register_agenda_action("respond_killing", killing_offers)
register_agenda_action("respond_incident", respond_offers)
register_agenda_action("pay_or_refuse", pay_offers)

from . import org_tension  # noqa: E402,F401  (registers the tension model's executors and agenda actions)
```

## engine/org_money.py

```python
"""Organisation money: who earns a line, and the periodic posting of what lines bring in and pass up.

Sphere-free: roles, flows and the rules that move money between roles come from the package's orgs.json (see its
"_doc"). Every `period_days` from the opening, `post_period` brings each line's take in from outside (`ledger.receive`,
the only money organisations ever gain) and then moves it between existing purses with `ledger.transfer`, stage by
stage so every man holds what he passes on before he passes it. Each movement is one `org_money` row. Nothing is created
or lost inside the organisations. Arrangements with an official (`org_arrangements`) are posted after the stages, by
`post_arrangements`, in the flow their kind names in orgs.json `arrangement_kinds`.
"""
from __future__ import annotations

import hashlib
import sqlite3
from collections import defaultdict

from . import ledger
from .design import figure, run_seed
from . import orgs
from .orgs import kind_rules
from .world_package import org_rules, package_for

PERIOD_DAYS = 28  # used when the package's orgs.json gives no period_days
MIN_ROW = 0.005  # amounts below half a cent are not posted

_DEAD = ("dead", "deceased", "historical")


def _rules(conn: sqlite3.Connection) -> dict:
    return org_rules(package_for(conn))


def _period(conn: sqlite3.Connection) -> int:
    return int(_rules(conn).get("period_days") or PERIOD_DAYS)


def _inflow(conn: sqlite3.Connection) -> str | None:
    flows = _rules(conn).get("flows") or []
    return str(flows[0]) if flows else None


def _rendezvous(seed: int, tag: str, actor_id: int, candidates: list[int]) -> int | None:
    """Pick one of `candidates` for a man by a stable hash, so a tie holds until the man he is tied to goes."""
    if not candidates:
        return None
    return max(candidates, key=lambda c: hashlib.sha256(f"{seed}:{tag}:{actor_id}:{c}".encode()).digest())


def _share(conn: sqlite3.Connection, spec: dict) -> float:
    return float(figure(conn, spec["figure"], default=spec.get("default")))


# ---- who is alive to earn ----

def _is_alive(r: sqlite3.Row | None) -> bool:
    """A seat is alive when it is active and its person is living and not dead, held or out."""
    return r is not None and r["status"] == "active" and r["life_status"] == "living" and r["actor_status"] not in _DEAD


class Roster:
    """Live seats of every organisation, and who stands in for a man who cannot earn (his unit leader, then the head)."""

    def __init__(self, conn: sqlite3.Connection):
        self.seats: dict[tuple[int, int], sqlite3.Row] = {}  # (actor, org) -> seat row with life columns
        self.by_org: dict[int, list[tuple[int, sqlite3.Row]]] = defaultdict(list)
        for r in conn.execute(
            """SELECT r.*, COALESCE(lp.life_status,'living') AS life_status, lower(COALESCE(a.status,'active')) AS actor_status
               FROM org_seats r JOIN actors a ON a.id=r.actor_id LEFT JOIN actor_life_profiles lp ON lp.actor_id=r.actor_id"""):
            self.seats[(int(r["actor_id"]), int(r["org_actor_id"]))] = r
            self.by_org[int(r["org_actor_id"])].append((int(r["actor_id"]), r))
        self.kinds = {org: kind_rules(conn, org) for org in self.by_org}
        self.top: dict[int, list[int]] = defaultdict(list)  # org -> live holders of the head role, by actor id
        for org, rows in self.by_org.items():
            head = self.kinds[org].get("head")
            for a, r in rows:
                if head and r["role_key"] == head and _is_alive(r):
                    self.top[org].append(a)
        for v in self.top.values():
            v.sort()

    def seat(self, actor_id: int | None, org: int) -> sqlite3.Row | None:
        return None if actor_id is None else self.seats.get((int(actor_id), int(org)))

    def alive(self, actor_id: int | None, org: int) -> bool:
        return _is_alive(self.seat(actor_id, org))

    def head(self, org: int) -> int | None:
        top = self.top.get(int(org))
        return top[0] if top else None

    def unit_leader(self, actor_id: int, org: int) -> int | None:
        """Himself when he holds the kind's unit-leader role, else the first holder of it up his chain of superiors."""
        role = self.kinds.get(int(org), {}).get("unit_leader")
        if not role:
            return None
        seen: set[int] = set()
        cur: int | None = int(actor_id)
        while cur is not None and cur not in seen:
            seen.add(cur)
            r = self.seats.get((cur, int(org)))
            if r is None:
                return None
            if r["role_key"] == role:
                return cur
            cur = int(r["superior_actor_id"]) if r["superior_actor_id"] is not None else None
        return None

    def purse_holder(self, actor_id: int, org: int) -> int | None:
        """Who pays for this man's regime: himself or the first holder of a purse role up his chain of superiors,
        when he is alive; else the head. None when no one is alive to pay."""
        roles = set(self.kinds.get(int(org), {}).get("purse_roles") or [])
        seen: set[int] = set()
        cur: int | None = int(actor_id)
        found: int | None = None
        while roles and cur is not None and cur not in seen:
            seen.add(cur)
            r = self.seats.get((cur, int(org)))
            if r is None:
                break
            if r["role_key"] in roles:
                found = cur
                break
            cur = int(r["superior_actor_id"]) if r["superior_actor_id"] is not None else None
        if found is not None and self.alive(found, org):
            return found
        return self.head(org)

    def earner(self, actor_id: int | None, org: int) -> int | None:
        """The man who earns on this man's behalf: himself, else his unit leader, else the head; None if no one."""
        r = self.seat(actor_id, org)
        if r is None:
            return None
        if _is_alive(r):
            return int(actor_id)
        leader = self.unit_leader(int(actor_id), org)
        if leader is not None and leader != int(actor_id) and self.alive(leader, org):
            return leader
        return self.head(org)


def line_holder(conn: sqlite3.Connection, line_id: int) -> int:
    """The live earner of a line: its holder, or when he is dead, held or out, his stand-in in the line's organisation."""
    row = conn.execute(
        """SELECT l.holder_actor_id, COALESCE(h.org_actor_id,u.org_actor_id) AS org FROM org_lines l
           LEFT JOIN org_holdings h ON h.id=l.holding_id LEFT JOIN org_units u ON u.id=l.unit_id WHERE l.id=?""",
        (int(line_id),)).fetchone()
    if row is None:
        raise ValueError(f"no line {line_id}")
    earner = Roster(conn).earner(row[0], row[1]) if row[1] is not None else None
    if earner is None:
        raise RuntimeError(f"line {line_id} has no live earner")
    return earner


# ---- the posting ----

def _last_posted(conn: sqlite3.Connection) -> int | None:
    inflow = _inflow(conn)
    if inflow is None:
        return None
    r = conn.execute("SELECT MAX(day) FROM org_money WHERE kind=?", (inflow,)).fetchone()
    if r and r[0] is not None:
        return int(r[0])
    r = conn.execute("SELECT MIN(started_day) FROM org_holdings WHERE source='opening'").fetchone()
    return int(r[0]) if r and r[0] is not None else None


def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    last = _last_posted(conn)
    if last is None:
        return None
    due = max(last + _period(conn), int(after_day) + 1)
    return due if due <= end_day else None


def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict:
    last = _last_posted(conn)
    period = _period(conn)
    out: dict = {"periods": 0}
    while last is not None and last + period <= day:
        last += period
        res = post_period(conn, last, period)
        out["periods"] += 1
        for k, v in res.items():
            out[k] = out.get(k, 0) + v
    return out


class _State:
    """What one posting has worked out so far, keyed by (organisation, person)."""

    def __init__(self, conn: sqlite3.Connection, ros: Roster, day: int, days: int, seed: int):
        self.conn, self.ros, self.day, self.days, self.seed = conn, ros, day, days, seed
        self.take: dict[tuple[int, int], float] = defaultdict(float)
        self.hidden: dict[tuple[int, int], float] = defaultdict(float)
        self.take_line: dict[tuple[int, int], tuple[float, int]] = {}
        self.take_order: dict[int, list[int]] = defaultdict(list)
        self.net: dict[tuple[int, int], float] = {}
        self.kick_in: dict[tuple[int, int], float] = defaultdict(float)  # received from a man's own earners
        self.head_in: dict[tuple[int, int], float] = defaultdict(float)  # received by the head from regimes
        self.stages: dict[int, list[tuple]] = defaultdict(list)  # stage -> (flow, src, dst, amount, line_id, org)

    def add(self, stage: int, flow: str, src: int | None, dst: int, amount: float, line_id: int | None, org: int) -> None:
        self.stages[int(stage)].append((flow, src, dst, amount, line_id, org))

    def base_net(self, org: int, a: int) -> float:
        return max(0.0, self.net[(org, a)] - self.hidden.get((org, a), 0.0))


def _rule_paid_by_patron(rule: dict, org: int, st: _State) -> None:
    roles = set(rule["roles"])
    ret = _share(st.conn, rule["return_share"])
    base = _share(st.conn, rule["living"]) / (1.0 - ret) * st.days / 365.0
    cap = _share(st.conn, rule["cap"])
    by_patron: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for a, r in st.ros.by_org[org]:
        if r["role_key"] not in roles or not _is_alive(r):
            continue
        patron = st.ros.earner(r["superior_actor_id"], org)
        if patron is None or st.take.get((org, patron), 0.0) <= 0 or patron == a:
            continue
        by_patron[patron].append((a, base * (0.5 + float(r["reliability"]))))
    for patron, paid in by_patron.items():
        want = sum(e for _, e in paid)
        f = min(1.0, cap * st.take[(org, patron)] / want)
        for a, e in paid:
            e *= f
            if e < MIN_ROW:
                continue
            st.add(rule["stage"], rule["flow"], patron, a, e, None, org)
            st.add(rule["return_stage"], rule["return_flow"], a, patron, e * ret, None, org)
            st.net[(org, patron)] -= e * (1.0 - ret)


def _rule_to_superior(rule: dict, org: int, st: _State) -> None:
    roles, share = set(rule["roles"]), _share(st.conn, rule["share"])
    for a in st.take_order[org]:
        r = st.ros.seats[(a, org)]
        if r["role_key"] not in roles:
            continue
        sup = st.ros.earner(r["superior_actor_id"], org)
        if sup is None or sup == a:
            continue
        amount = share * st.base_net(org, a)
        if amount >= MIN_ROW:
            st.add(rule["stage"], rule["flow"], a, sup, amount, None, org)
            st.kick_in[(org, sup)] += amount


def _rule_regime_to_head(rule: dict, org: int, st: _State) -> None:
    roles, share = set(rule["roles"]), _share(st.conn, rule["share"])
    head = st.ros.head(org)
    for a, r in st.ros.by_org[org]:
        if r["role_key"] not in roles or not _is_alive(r):
            continue
        regime = st.base_net(org, a) if (org, a) in st.net else 0.0
        regime += st.kick_in.get((org, a), 0.0)
        if regime > 0 and head is not None:
            amount = share * regime
            if amount >= MIN_ROW:
                st.add(rule["stage"], rule["flow"], a, head, amount, None, org)
                st.head_in[(org, head)] += amount


def _rule_head_share(rule: dict, org: int, st: _State) -> None:
    roles, share = set(rule["roles"]), _share(st.conn, rule["share"])
    head_role = st.ros.kinds[org].get("head")
    receipts: dict[int, float] = defaultdict(float)
    for (o, h), v in st.head_in.items():
        if o == org:
            receipts[h] += v
    for (o, h), v in st.kick_in.items():  # a man's earners who sent straight to the head count as receipts too
        if o == org and st.ros.seats[(h, org)]["role_key"] == head_role:
            receipts[h] += v
    for h, got in receipts.items():
        for b, r in st.ros.by_org[org]:
            if r["role_key"] in roles and _is_alive(r):
                amount = share * got
                if amount >= MIN_ROW:
                    st.add(rule["stage"], rule["flow"], h, b, amount, None, org)


def _upward(rule: dict, org: int, st: _State, pick) -> None:
    """Every earner outside the head role passes a share up; `pick(a, r)` gives (destination, amount) or None."""
    head_role = st.ros.kinds[org].get("head")
    for a in st.take_order[org]:
        r = st.ros.seats[(a, org)]
        got = pick(a, r, head_role)
        if got is None:
            continue
        dst, amount = got
        if dst is not None and dst != a and amount >= MIN_ROW:
            st.add(rule["stage"], rule["flow"], a, dst, amount, None, org)


def _rule_to_head_pick(rule: dict, org: int, st: _State) -> None:
    share = _share(st.conn, rule["share"])

    def pick(a, r, head_role):
        if r["role_key"] == head_role:
            return None
        heads = [x for x in st.ros.top.get(org, []) if x != a]
        return _rendezvous(st.seed, rule["tag"], a, heads), share * st.base_net(org, a)
    _upward(rule, org, st, pick)


def _rule_to_head_via_superior(rule: dict, org: int, st: _State) -> None:
    keep = _share(st.conn, rule["keep"])

    def pick(a, r, head_role):
        sup = st.ros.earner(r["superior_actor_id"], org)
        if sup is not None and sup != a and st.ros.seats[(sup, org)]["role_key"] == head_role:
            dst = sup
        else:
            dst = _rendezvous(st.seed, rule["tag"], a, list(st.ros.top.get(org, [])))
        return dst, st.base_net(org, a) * (1.0 - keep)
    _upward(rule, org, st, pick)


def _rule_to_first_head(rule: dict, org: int, st: _State) -> None:
    share = _share(st.conn, rule["share"])

    def pick(a, r, head_role):
        if r["role_key"] == head_role:
            return None
        return st.ros.head(org), share * st.base_net(org, a)
    _upward(rule, org, st, pick)


_RULES = {
    "paid_by_patron": _rule_paid_by_patron,
    "to_superior": _rule_to_superior,
    "regime_to_head": _rule_regime_to_head,
    "head_share": _rule_head_share,
    "to_head_pick": _rule_to_head_pick,
    "to_head_via_superior": _rule_to_head_via_superior,
    "to_first_head": _rule_to_first_head,
}


def post_period(conn: sqlite3.Connection, day: int, days: int) -> dict[str, float]:
    """Post one period: bring the take in, move it up by the kinds' rules. Returns the amount by flow (plus "rows"
    and "unearned_lines", the lines left out because nobody alive could earn on them)."""
    rules = _rules(conn)
    flows = [str(f) for f in rules.get("flows") or []]
    out: dict[str, float] = {f: 0.0 for f in flows}
    out["rows"] = 0.0
    out["unearned_lines"] = 0.0
    if not flows:
        return out
    inflow = flows[0]
    st = _State(conn, Roster(conn), int(day), int(days), run_seed(conn))
    ros = st.ros

    for r in conn.execute(
        """SELECT l.id,l.holder_actor_id,l.weekly_take,l.hidden,h.org_actor_id AS org FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id
           WHERE l.status='active' AND h.status='active' AND l.started_day<=? ORDER BY l.id""", (int(day),)):
        org = int(r["org"])
        earner = ros.earner(r["holder_actor_id"], org)
        if earner is None:
            out["unearned_lines"] += 1.0
            continue
        amount = float(r["weekly_take"]) * days / 7.0
        key = (org, earner)
        if key not in st.take:
            st.take_order[org].append(earner)
        st.take[key] += amount
        if r["hidden"]:
            st.hidden[key] += amount
        if key not in st.take_line or amount > st.take_line[key][0]:
            st.take_line[key] = (amount, int(r["id"]))
    for (org, a), amount in st.take.items():
        st.add(0, inflow, None, a, amount, st.take_line[(org, a)][1], org)
    st.net = dict(st.take)  # what each earner keeps of his line take

    by_org = {org: list(k.get("rules") or []) for org, k in ros.kinds.items()}
    for pos in range(max((len(v) for v in by_org.values()), default=0)):
        for org, rl in by_org.items():
            if pos < len(rl):
                _RULES[rl[pos]["type"]](rl[pos], org, st)

    kinds = rules.get("ledger_kinds") or {}
    purpose = str(rules.get("ledger_purpose") or "{flow}")
    rows: list[tuple] = []
    entries_by_flow: dict[str, list[tuple]] = defaultdict(list)
    for stage in sorted(st.stages):
        for flow, src, dst, amount, line_id, org in st.stages[stage]:
            if flow not in out:
                raise ValueError(f"flow {flow!r} is not declared in the package's orgs.json flows")
            if flow == inflow:
                ledger.receive(conn, ("person", dst), amount, purpose=purpose.format(flow=flow))
            else:
                ledger.transfer(conn, ("person", src), ("person", dst), amount, flow_kind=kinds[flow], purpose=purpose.format(flow=flow))
            out[flow] += amount
            rows.append((int(day), flow, src, dst, line_id, amount, org))
            entries_by_flow[flow].append((src, dst, amount, line_id, org))
    conn.executemany("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,line_id,amount,org_actor_id) VALUES (?,?,?,?,?,?,?)", rows)
    out["rows"] = float(len(rows))
    paid: dict[str, float] = {}
    post_arrangements(conn, day, days, ros, take_entries=entries_by_flow.get(inflow, []), by_flow=paid)
    for flow, amount in paid.items():
        out[flow] = out.get(flow, 0.0) + amount
    return out


# ---- arrangements with an official ----

def add_arrangement(conn: sqlite3.Connection, *, kind: str, payer_kind: str, payer_id: int, official_actor_id: int,
                    weekly_usd: float, day: int, go_between_actor_id: int | None = None, position_key: str = "") -> int:
    """An active arrangement: `payer_id` (an organisation or a person, by `payer_kind` 'org' | 'actor') pays the official
    `weekly_usd` a week, through the go-between when there is one. Returns its id."""
    if payer_kind not in ("org", "actor"):
        raise ValueError(f"payer_kind must be 'org' or 'actor', not {payer_kind!r}")
    return int(conn.execute(
        """INSERT INTO org_arrangements(kind,official_actor_id,payer_kind,payer_id,position_key,weekly_usd,go_between_actor_id,status,started_day)
           VALUES (?,?,?,?,?,?,?,'active',?)""",
        (kind, int(official_actor_id), payer_kind, int(payer_id), position_key, float(weekly_usd),
         None if go_between_actor_id is None else int(go_between_actor_id), int(day))).lastrowid)


def _living(conn: sqlite3.Connection, ids: set[int]) -> set[int]:
    if not ids:
        return set()
    return {int(r[0]) for r in conn.execute(
        """SELECT a.id FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id
           WHERE a.id IN (%s) AND lower(COALESCE(a.status,'active')) NOT IN ('dead','deceased','historical')
             AND COALESCE(lp.life_status,'living')='living'""" % ",".join(str(i) for i in ids))}


def post_arrangements(conn: sqlite3.Connection, day: int, days: int, roster: Roster, *,
                      take_entries: list[tuple] | None = None, by_flow: dict[str, float] | None = None) -> float:
    """Post every active arrangement for `days`: `weekly_usd * days / 7`, in the flow its kind names in orgs.json
    `arrangement_kinds` ({flow, ledger_kind, purpose}).

    An organisation pays from the holders of its kind's `purse_roles`, each in proportion to the take of the men under
    him posted this period (`take_entries`, (from, to, amount, line, org) tuples as post_period builds them); with
    no purse roles, or no take, the head pays. A person pays from his own purse. A payer who is not alive posts nothing
    and the arrangement lapses; an official who is not alive is skipped (the position is still paid, to whoever sits in
    it next). Each amount goes through the go-between when he is alive (payer to go-between to official, one row per
    hop), else straight to the official. Returns what the payers paid out (the first hop; the officials' total when
    nothing is held back by thin purses); `by_flow`, when given, gets that amount added under the kind's flow."""
    rows = conn.execute(
        """SELECT * FROM org_arrangements WHERE status='active' AND started_day<=? AND (ended_day IS NULL OR ended_day>?) ORDER BY id""",
        (int(day), int(day))).fetchall()
    if not rows:
        return 0.0
    kinds = _rules(conn).get("arrangement_kinds") or {}
    for e in rows:
        if e["kind"] not in kinds:
            raise ValueError(f"arrangement kind {e['kind']!r} is not declared in the package's orgs.json arrangement_kinds")
    people = {int(e["official_actor_id"]) for e in rows} | {int(e["payer_id"]) for e in rows if e["payer_kind"] == "actor"} \
        | {int(e["go_between_actor_id"]) for e in rows if e["go_between_actor_id"] is not None}
    alive = _living(conn, people)
    weight: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))  # org -> purse holder -> take this period
    for _src, earner, amount, _line, org in take_entries or []:
        holder = roster.purse_holder(int(earner), int(org))
        if holder is not None:
            weight[int(org)][holder] += float(amount)

    def payers_of(org: int) -> dict[int, float]:
        head = roster.head(org)
        return dict(weight.get(org) or ({head: 1.0} if head is not None else {}))

    def book_org(actor_id: int) -> int | None:
        seats = [int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (int(actor_id),))]
        return seats[0] if len(seats) == 1 else None

    owed: dict[tuple[str, int, int, str], float] = defaultdict(float)  # (payer kind, payer, collector, kind) -> amount
    onward: dict[tuple[int, int, str], float] = defaultdict(float)  # (collector, official, kind) -> amount handed on
    onward_org: dict[tuple[int, int, str], int | None] = {}  # whose books carry the hand-off
    lapse: list[int] = []
    for e in rows:
        official, bag = int(e["official_actor_id"]), e["go_between_actor_id"]
        if official not in alive:
            continue
        pk, pid = e["payer_kind"], int(e["payer_id"])
        if (pk == "actor" and pid not in alive) or (pk == "org" and not payers_of(pid)):
            lapse.append(int(e["id"]))
            continue
        amount = float(e["weekly_usd"]) * days / 7.0
        collector = int(bag) if bag is not None and int(bag) in alive else official
        owed[(pk, pid, collector, e["kind"])] += amount
        if collector != official:
            onward[(collector, official, e["kind"])] += amount
            onward_org.setdefault((collector, official, e["kind"]), pid if pk == "org" else book_org(pid))
    paid_out = 0.0
    pay_rows: list[tuple] = []

    def pay(src: int, dst: int, amount: float, kind: str, org: int | None) -> float:
        spec = kinds[kind]
        got = ledger.transfer(conn, ("person", src), ("person", dst), amount, flow_kind=spec["ledger_kind"],
                              purpose=str(spec.get("purpose") or kind), allow_partial=True)
        if got > 0:
            pay_rows.append((int(day), spec["flow"], src, dst, None, got, org))
        return got

    for (pk, pid, collector, kind), amount in sorted(owed.items()):
        if pk == "actor":
            parts = {pid: 1.0}
            where = book_org(pid)
        else:
            parts, where = payers_of(pid), pid
        total = sum(parts.values())
        for holder, share in sorted(parts.items()):
            part = amount * share / total
            if part < MIN_ROW or holder == collector:
                continue
            got = pay(holder, collector, part, kind, where)
            paid_out += got
            if by_flow is not None:
                by_flow[kinds[kind]["flow"]] = by_flow.get(kinds[kind]["flow"], 0.0) + got
    for (collector, official, kind), amount in sorted(onward.items()):
        pay(collector, official, amount, kind, onward_org.get((collector, official, kind)))
    conn.executemany("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,line_id,amount,org_actor_id) VALUES (?,?,?,?,?,?,?)", pay_rows)
    for i in lapse:
        conn.execute("UPDATE org_arrangements SET status='lapsed', ended_day=? WHERE id=?", (int(day), i))
    return paid_out


def purse_ref(conn: sqlite3.Connection, org_id: int) -> str | None:
    """The ledger holder an organisation's own obligations are paid from: its living head's purse; None when it has none."""
    head = orgs.head_of(conn, int(org_id))
    return f"person:{head}" if head is not None and orgs.is_living(conn, head) else None
```


(End of batch 3 of 5.)
