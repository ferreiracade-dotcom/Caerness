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
    return n


def _custody_held(conn: sqlite3.Connection) -> dict[int, int]:
    return {int(a): int(s) for a, s in conn.execute("SELECT actor_id,MIN(since_day) FROM custody WHERE kind='held' GROUP BY actor_id")}


def _levels_pair(conn: sqlite3.Connection) -> tuple[int, int]:
    """(the level reviewed most often, the next one) from the package's cadence_days (level -> days between reviews)."""
    cad = sorted(((int(v), int(k)) for k, v in (org_rules(package_for(conn)).get("cadence_days") or {}).items()))
    return (cad[0][1], cad[1][1]) if len(cad) > 1 else (cad[0][1], cad[0][1])


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
        lvl_days, seat_days = _num(conn, lc, "held_level_days"), _num(conn, lc, "held_seat_days")
        if lvl_days and int(s["level"]) == high and role_level(conn, org, s["role_key"]) == high:
            soon = 1.0 if left is None else min(1.0, left / lvl_days)
            p = _num(conn, dec, "level_week", 0.0) * min(1.0, d / lvl_days) * soon * (1.0 - lw * loyal)
            if p > 0 and org_motives._roll(conn, a, int(day), "held_level") < p:
                orgs.set_level(conn, a, low, int(day), org)
                n += 1
        if seat_days:
            p = _num(conn, dec, "seat_week", 0.0) * min(1.0, d / seat_days) * (1.0 - lw * loyal)
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
