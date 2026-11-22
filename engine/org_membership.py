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
    rows = conn.execute(
        """SELECT s.actor_id,s.standing,a.name,lp.birth_day FROM org_seats s JOIN actors a ON a.id=s.actor_id LEFT JOIN actor_life_profiles lp ON lp.actor_id=s.actor_id
           WHERE s.org_actor_id=? AND s.unit_id=? AND s.role_key=? AND s.status='active' AND s.inducted_day IS NULL
             AND NOT EXISTS (SELECT 1 FROM custody c WHERE c.actor_id=s.actor_id AND c.kind='held')""", (int(org), int(unit_id), sp["dependent"])).fetchall()
    scored = []
    for r in rows:
        sc = _nomination(conn, sp, r["standing"], r["name"], r["birth_day"], day)
        if sc is not None and is_living(conn, int(r["actor_id"])):
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
