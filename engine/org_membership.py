"""How an organisation keeps its numbers true (generic layer, driven by the package's data; names no role or organisation).

Where an organisation has a member figure and a dependent role (orgs.json `opening.member_role` / `dependent_role`, the
outfit entry's `members_figure` and `dependents_figure`) and the sphere file has a `membership` block, this layer runs in
the weekly lifecycle process (`org_lifecycle.on_week`) and on every vacancy (`org_lifecycle.on_vacancy`):

  books      a vacated inducted seat opens the books: the head gets agenda `open_books` when the inducted count is below the
             figure (the figure itself, never above the range top unless a dated cause moved it, `limit`); he asks each unit
             leader for one name (`propose_member`); the leader names the dependant with the best standing in his unit whose
             family name is in the induction `father_name_group`; the head makes him (`make_member`); the men he brought in
             answer to him. A short count with nothing open reopens the books after `books.retry_days`.
  dependants lost dependants (inducted, dead, out) are replaced one by one, at most one a week a unit, by pulling up young
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
    row = conn.execute("SELECT package_key FROM org_profiles WHERE org_actor_id=?", (int(org),)).fetchone()
    if row is None:
        return None
    outfit = (org_motives._sphere_data(conn).get("outfits") or {}).get(row[0]) or {}
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


def made_count(conn: sqlite3.Connection, org: int) -> int:
    """Inducted men in active seats."""
    return int(conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND inducted_day IS NOT NULL AND status='active'", (int(org),)).fetchone()[0])


def limit(conn: sqlite3.Connection, org: int) -> int:
    """How many inducted men the organisation may have now: its figure, but a figure moved above the top of its range
    counts only when a dated cause was logged for the move (and then only to the top of the figure's extended range,
    where it has one)."""
    sp = _spec(conn, org)
    if sp is None:
        return 0
    value = int(round(float(figure(conn, sp["figure"]))))
    rng, ext = _cache(conn)["ranges"].get(sp["figure"], (None, None))
    if not isinstance(rng, list) or value <= int(rng[1]):
        return value
    dated = conn.execute("SELECT 1 FROM design_figure_log WHERE key=? AND new_value>? AND TRIM(COALESCE(cause,''))<>'' AND cause NOT LIKE 'opening%' LIMIT 1",
                         (sp["figure"], float(rng[1]))).fetchone()
    if not dated:
        return int(rng[1])
    return min(value, int(ext[1])) if isinstance(ext, list) else value


def _father_families(conn: sqlite3.Connection) -> set[str] | None:
    group = (org_motives._sphere_data(conn).get("induction") or {}).get("father_name_group")
    if not group:
        return None
    cache = _cache(conn)["surnames"]
    if group not in cache:
        from .person_ecology import _group_families
        cache[group] = set(_group_families(conn, group))
    return cache[group]


def eligible(conn: sqlite3.Connection, org: int, unit_id: int, day: int) -> list[int]:
    """Dependants of one unit who may be inducted, best standing first: alive, not held, old enough (the kind's
    `inducted_after_age`), and, where the package says so, with a family name from the induction `father_name_group`."""
    sp = _spec(conn, org)
    if sp is None:
        return []
    surnames = _father_families(conn)
    min_age = int(sp["opening"].get("inducted_after_age") or 0)
    rows = conn.execute(
        """SELECT s.actor_id,a.name,lp.birth_day FROM org_seats s JOIN actors a ON a.id=s.actor_id LEFT JOIN actor_life_profiles lp ON lp.actor_id=s.actor_id
           WHERE s.org_actor_id=? AND s.unit_id=? AND s.role_key=? AND s.status='active' AND s.inducted_day IS NULL
             AND NOT EXISTS (SELECT 1 FROM custody c WHERE c.actor_id=s.actor_id AND c.kind='held')
           ORDER BY s.standing DESC, s.actor_id""", (int(org), int(unit_id), sp["dependent"])).fetchall()
    out = []
    for r in rows:
        if surnames is not None and str(r["name"]).split()[-1] not in surnames:
            continue
        if r["birth_day"] is not None and (int(day) - int(r["birth_day"])) // 365 < min_age:
            continue
        if is_living(conn, int(r["actor_id"])):
            out.append(int(r["actor_id"]))
    return out


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


def after_gone(conn: sqlite3.Connection, org: int, day: int, *, immediate: bool = True) -> bool:
    """Open the books if the count is below the limit and nothing about them is already open. A weekly reopening
    (`immediate` False) also waits `books.retry_days` after the last time the head's books were opened."""
    sp = _spec(conn, org)
    head = head_of(conn, org) if sp is not None else None
    if sp is None or head is None or made_count(conn, org) >= limit(conn, org) or _open_items(conn, org, int(day)):
        return False
    if not immediate:
        retry = _v(conn, (_data(conn).get("books") or {}).get("retry_days"), 28.0)
        last = conn.execute("SELECT MAX(created_day) FROM org_agenda WHERE kind='open_books' AND json_extract(metadata_json,'$.org')=?", (int(org),)).fetchone()[0]
        if last is not None and int(day) - int(last) < retry:
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
    if made_count(conn, org) >= limit(conn, org):
        return [{"kind": "close_books", "utility": _utility(conn, 1.0), "rationale": "The books are full again.", "payload": {"org": org}}]
    return [{"kind": "ask_for_names", "utility": _utility(conn, 1.0), "rationale": f"Opens the books of the {_name(conn, org)} and asks each unit leader for a name.",
             "payload": {"org": org}}]


def execute_close_books(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    return {"summary": "The books closed; there was no room."}


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
    if made_count(conn, org) >= limit(conn, org) or head_of(conn, org) is None:
        return [{"kind": "no_name", "utility": _utility(conn, 1.0), "rationale": "The books are closed.", "payload": {"org": org}}]
    pool: list[int] = []
    for (unit,) in conn.execute("SELECT id FROM org_units WHERE org_actor_id=? AND leader_actor_id=? ORDER BY id", (org, int(actor_id))).fetchall():
        pool += eligible(conn, org, int(unit), int(day))
    if not pool:
        return [{"kind": "no_name", "utility": _utility(conn, 1.0), "rationale": "He has no one fit to put forward.", "payload": {"org": org}}]
    best = max(pool, key=lambda a: (float(seat_of(conn, a, org)["standing"]), -a))
    st = float(seat_of(conn, best, org)["standing"])
    return [{"kind": "propose_member", "utility": _utility(conn, 0.5 + 0.5 * st), "target_actor_id": best,
             "rationale": f"Puts forward {_name(conn, best)}, the best of his crew (standing {st:.2f}).", "payload": {"org": org, "candidate": best}}]


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
    return {"summary": f"{_name(conn, actor_id)} put {_name(conn, cand)} forward."}


def make_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = _meta(item)
    org, cand, proposer = int(meta["org"]), int(item["subject_id"]), int(meta["proposer"])
    s = seat_of(conn, cand, org)
    sp = _spec(conn, org)
    payload = {"org": org, "candidate": cand, "proposer": proposer}
    unit = None if s is None else s["unit_id"]
    fit = s is not None and sp is not None and s["status"] == "active" and s["inducted_day"] is None and unit is not None and cand in eligible(conn, org, int(unit), int(day))
    if not fit or made_count(conn, org) >= limit(conn, org):
        return [{"kind": "decline_member", "utility": _utility(conn, 1.0), "rationale": "No room, or the man is no longer fit.", "payload": payload}]
    rivals = [r for r in conn.execute("SELECT subject_id FROM org_agenda WHERE actor_id=? AND kind='make_member' AND status='open' AND due_day<=? AND id<>? "
                                      "AND json_extract(metadata_json,'$.org')=?", (int(actor_id), int(day), int(item["id"]), org)).fetchall()
              if seat_of(conn, int(r[0]), org) is not None and seat_of(conn, int(r[0]), org)["status"] == "active"]
    mine = (float(s["standing"]), -cand)
    if any((float(seat_of(conn, int(r[0]), org)["standing"]), -int(r[0])) > mine for r in rivals):
        return []  # a better-regarded name is waiting: it is taken first
    return [{"kind": "make_member", "utility": _utility(conn, 0.5 + 0.5 * float(s["standing"])), "target_actor_id": cand,
             "rationale": f"Makes {_name(conn, cand)}, put forward by {_name(conn, proposer)}.", "payload": payload}]


def execute_decline_member(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    return {"summary": f"{_name(conn, actor_id)} turned down {_name(conn, payload['candidate'])}."}


def execute_make_member(conn, actor_id, kind, payload, day):
    org, cand = int(payload["org"]), int(payload["candidate"])
    _finish(conn, payload, day)
    s = seat_of(conn, cand, org)
    if s is None or s["status"] != "active" or s["inducted_day"] is not None or made_count(conn, org) >= limit(conn, org) or not is_living(conn, cand):
        return {"summary": "The seat was no longer to be had.", "blocked": True}
    proposer = int(payload["proposer"])
    ps = seat_of(conn, proposer, org)
    leader = proposer if ps is not None and ps["status"] == "active" else head_of(conn, org)
    induct(conn, org, cand, int(leader), int(day))
    return {"summary": f"{_name(conn, cand)} was inducted under {_name(conn, leader)}."}


# ---- dependants ----

def replace_dependants(conn: sqlite3.Connection, day: int) -> int:
    """Units short of their dependants (the organisation's figure per inducted man) take one new dependant a week with
    the weekly chance `replacement.chance_week`, pulled up from the background population."""
    data = _data(conn).get("replacement") or {}
    chance = _v(conn, data.get("chance_week"), 0.0)
    if chance <= 0.0:
        return 0
    made = 0
    for org, sp in _orgs(conn):
        ratio = float(figure(conn, sp["outfit"]["dependents_figure"])) if sp["outfit"].get("dependents_figure") else 0.0
        for unit in conn.execute("SELECT id,leader_actor_id FROM org_units WHERE org_actor_id=? AND leader_actor_id IS NOT NULL ORDER BY id", (org,)).fetchall():
            leader, uid = int(unit["leader_actor_id"]), int(unit["id"])
            men = conn.execute("SELECT COUNT(*) FROM org_seats WHERE unit_id=? AND status='active' AND inducted_day IS NOT NULL", (uid,)).fetchone()[0]
            deps = conn.execute("SELECT COUNT(*) FROM org_seats WHERE unit_id=? AND status='active' AND role_key=?", (uid, sp["dependent"])).fetchone()[0]
            if deps >= round(men * ratio) or org_motives._roll(conn, leader, int(day), "replace_dependant") >= chance:
                continue
            made += 1 if _replace_one(conn, org, sp, uid, leader, int(day), data) else 0
    return made


def _replace_one(conn: sqlite3.Connection, org: int, sp: dict, unit: int, leader: int, day: int, data: dict) -> int | None:
    from .outfit_opening import feelings_toward, pull_up, seat_subtype
    rng = random.Random(f"{run_seed(conn)}:replace:{unit}:{day}")
    role = (sp["opening"].get("roles") or {}).get(sp["dependent"]) or {}
    male = float((org_motives._sphere_data(conn).get("male_share") or {}).get(role.get("male_share_key"), 1.0))
    group = sp["outfit"].get("name_group") if rng.random() < float(sp["opening"].get("own_group_share", 1.0)) else None
    ages = tuple(int(x) for x in data["ages"])
    got = pull_up(conn, 1, stream=f"replace:{unit}:{day}", name_group=group, sex="male" if rng.random() < male else "female", ages=ages,
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


def discover_hidden(conn: sqlite3.Connection, day: int) -> int:
    """Each hidden line may be found this week; the head gets `discipline` with its holder as the subject."""
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
        add_agenda(conn, head, "discipline", int(day), subject_kind="actor", subject_id=int(holder),
                   metadata={"org": org, "line": int(ln["id"]), "holder": int(holder), "found": int(day)})
        imposed(conn, int(holder))
        n += 1
    return n


def _disc(conn: sqlite3.Connection, which: str, key: str, default: float = 0.0) -> float:
    return _v(conn, ((_data(conn).get("discipline") or {}).get(which) or {}).get(key), default)


def discipline_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    meta = _meta(item)
    org, holder = int(meta["org"]), int(meta["holder"])
    s = seat_of(conn, holder, org)
    payload = {"org": org, "line": int(meta["line"]), "holder": holder}
    if s is None or s["status"] != "active" or not is_living(conn, holder):
        return [{"kind": "drop_discipline", "utility": _utility(conn, 1.0), "rationale": "The man is gone.", "payload": payload}]
    standing, greed, aggr = float(s["standing"]), float(s["greed"]), _drive(conn, int(actor_id), "aggression")
    xs = {"discipline_fine": _disc(conn, "fine", "base") + _disc(conn, "fine", "standing") * standing,
          "discipline_demote": _disc(conn, "demote", "base") + _disc(conn, "demote", "greed") * greed,
          "discipline_kill": _disc(conn, "kill", "base") + _disc(conn, "kill", "aggression") * aggr + _disc(conn, "kill", "low_standing") * (1.0 - standing)
          + _disc(conn, "kill", "repeat") * (1.0 if conn.execute("SELECT 1 FROM org_agenda WHERE kind='discipline' AND subject_id=? AND status='resolved' AND id<? "
                                                               "AND json_extract(metadata_json,'$.org')=? LIMIT 1", (holder, int(item["id"]), org)).fetchone() else 0.0)}
    why = {"discipline_fine": f"Fines {_name(conn, holder)} the kick-up he kept back.", "discipline_demote": f"Takes the line from {_name(conn, holder)}.",
           "discipline_kill": f"Has {_name(conn, holder)} killed for holding out."}
    return [{"kind": k, "utility": _utility(conn, x), "rationale": why[k], "payload": payload, **({"target_actor_id": holder} if k == "discipline_kill" else {}),
             **({"risk": 0.8} if k == "discipline_kill" else {})} for k, x in xs.items()]


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
    return {"summary": f"{_name(conn, actor_id)} took the line from {_name(conn, holder)} and gave it to {_name(conn, taker)}."}


def execute_discipline_kill(conn, actor_id, kind, payload, day):
    from .outfit_choices import kill
    holder = int(payload["holder"])
    _finish(conn, payload, day)
    if not is_living(conn, holder):
        return {"summary": "The man was already dead.", "blocked": True}
    return {"summary": kill(conn, int(actor_id), holder, int(day), sanctioned=True)}


def execute_drop_discipline(conn, actor_id, kind, payload, day):
    _finish(conn, payload, day)
    return {"summary": "Nothing more was done about the line."}


# ---- the weekly hook and the vacancy hook ----

def _after_vacancy(conn: sqlite3.Connection, org: int, seat, day: int, why: str) -> None:
    if seat["inducted_day"] is not None and _spec(conn, org) is not None:
        after_gone(conn, org, int(day))


def _weekly(conn: sqlite3.Connection, day: int) -> dict:
    if not _data(conn):
        return {}
    out = {"expired": expire_stale(conn, day), "caught": discover_hidden(conn, day), "standing": grow_standing(conn, day), "replaced": replace_dependants(conn, day)}
    out["books"] = sum(1 for org, _sp in _orgs(conn) if after_gone(conn, org, day, immediate=False))
    return out


on_vacancy(None, _after_vacancy)
on_week(_weekly)
for _kind, _fn in (("close_books", execute_close_books), ("ask_for_names", execute_ask_for_names), ("no_name", execute_no_name),
                   ("propose_member", execute_propose_member), ("decline_member", execute_decline_member), ("make_member", execute_make_member),
                   ("discipline_fine", execute_discipline_fine), ("discipline_demote", execute_discipline_demote),
                   ("discipline_kill", execute_discipline_kill), ("drop_discipline", execute_drop_discipline)):
    register_executor(_kind, _fn)
for _kind, _fn in (("open_books", books_offers), ("propose_member", proposal_offers), ("make_member", make_offers), ("discipline", discipline_offers)):
    register_agenda_action(_kind, _fn)
