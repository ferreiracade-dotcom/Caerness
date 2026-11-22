"""The intake: one door for everything lasting the GM narrates.

A proposal is normalised, matched to a shape (a registry; BZ1 registers makers on the floor-backed shapes), run through the
veto-only checks, made by the shape's maker when it has one, and always written as one held_things row. A shape with no
maker, or a consequence no reader understands, also bumps a depth_gaps row so the next build knows what the GM keeps
reaching for. The engine vetoes and never lists: an unclear shape lands on the `thing` floor, never a refusal.

A package without intake rules (Caerness) keeps today's behaviour: an unclear kind is still an input_gap, nothing is held.
All shape words, reader words and figures live in the package's intake data.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable

from . import authoring, ledger
from .authoring import AuthoringRefused


@dataclass(frozen=True)
class Proposal:
    what: str
    kind_text: str
    people: tuple[int, ...]
    owner: int
    location_id: int | None
    place_text: str | None
    from_ref: str
    start_cost: float
    income_weekly: float
    upkeep_weekly: float
    agenda: str
    start_day: int
    end_day: int | None
    recurrence_days: int | None
    legality: str
    knows: tuple[int, ...]
    consequences: tuple[str, ...]
    source: str | None
    real_date: str | None
    ready_in_days: int | None
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Shape:
    name: str
    words: tuple[str, ...]
    fields: tuple[str, ...]
    make: Callable[[sqlite3.Connection, int, Proposal, str], dict] | None
    floor_backed: bool


# ---- registry -----------------------------------------------------------------------------------------------------

_REGISTERED: dict[str, Shape] = {}
OWN_MONEY_TABLES: set[str] = set()  # backings whose money the layer behind them moves itself; the weekly held-thing tick leaves them alone


def register_shape(shape: Shape) -> None:
    """The latest registration for a name wins; this is how a later layer replaces `holding` or `arrangement`."""
    _REGISTERED[shape.name] = shape


def _reset_registry_for_tests() -> None:
    _REGISTERED.clear()


def _builtin(name: str, fn) -> Shape:
    words = dict(authoring._KIND_WORDS).get(name, ())
    keys = {"rumour": ("text", "heard_by", "spread"), "organisation": ("leader_actor_id", "members"),
            "business": ("owner_actor_id", "trade", "amount"), "person": ("sex", "age", "work", "stage", "ties")}[name]
    return Shape(name, tuple(words), keys, fn, False)


_BUILTIN_MAKERS = {"person": authoring._person, "business": authoring._business, "organisation": authoring._organisation,
                   "rumour": authoring._rumour}
_BUILTINS = tuple(_builtin(n, lambda conn, me, p, cid, _f=f: _f(conn, me, p.details, cid)) for n, f in _BUILTIN_MAKERS.items())
_BUILTIN_ORDER = ("rumour", "organisation", "business", "person")  # the order authoring._kind_of tries its words in


def _rules(conn) -> dict:
    from .world_package import intake_rules, package_for
    return intake_rules(package_for(conn))


def _thing() -> Shape:
    return _REGISTERED.get("thing") or Shape("thing", (), (), None, True)


def shapes(conn) -> list[Shape]:
    """The built-ins, then the package's shapes (floor-backed until something is registered), then the `thing` floor."""
    out = [_REGISTERED.get(b.name, b) for b in sorted(_BUILTINS, key=lambda s: _BUILTIN_ORDER.index(s.name))]
    rules = _rules(conn)
    if not rules:
        return out
    pkg_words = rules.get("shape_words", {})
    names = list(pkg_words) + [n for n in _REGISTERED if n not in pkg_words and n not in {b.name for b in _BUILTINS} and n != "thing"]
    for n in names:
        s = _REGISTERED.get(n)
        words = tuple(s.words) if s and s.words else tuple(pkg_words.get(n, ()))
        out.append(Shape(n, words, s.fields if s else (), s.make if s else None, s.floor_backed if s else True))
    out.append(_thing())
    return out


def _has_word(text: str, word: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(word) + r"(?:s|es)?(?![a-z])", text) is not None


def shape_for(conn, kind: str, details: dict) -> Shape:
    """Free text to a shape: an exact name, then words in `kind`, then the fields present. With intake rules and no match,
    the `thing` floor; without them, today's input_gap."""
    d = details if isinstance(details, dict) else {}
    k = str(kind or "").lower().strip()
    rules = _rules(conn)
    allshapes = shapes(conn)
    if not rules:
        name = authoring._kind_of(kind, d)  # raises the input_gap
        return next(s for s in allshapes if s.name == name)
    for s in allshapes:
        if s.name == k:
            return s
    for s in allshapes:
        if not s.words:
            continue
        if s.name in _BUILTIN_ORDER:
            # a built-in's loose substring words only count when the details carry what its maker needs (a name, or its own fields)
            if (any(w in k for w in s.words)) and (s.name != "rumour" and "name" in d or any(x in d for x in s.fields)):
                return s
        elif any(_has_word(k, w) for w in s.words):
            return s
    for s in allshapes:
        if s.fields and any(x in d for x in s.fields):
            return s
    return _thing()


# ---- normalising a proposal ---------------------------------------------------------------------------------------

def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _ints(x) -> tuple[int, ...]:
    out: list[int] = []
    for v in (x if isinstance(x, (list, tuple)) else [] if x is None else [x]):
        if isinstance(v, bool):
            continue
        try:
            i = int(v)
        except (TypeError, ValueError):
            continue
        if i not in out:
            out.append(i)
    return tuple(out)


def _weekly(raw, base: float | None = None) -> float:
    """A weekly figure from a number or words: "1,000 a month" is a week's share, "a year" is a fifty-second."""
    if raw is None or raw == "":
        return 0.0
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) if raw > 0 else 0.0
    text = str(raw).lower().replace("$", "").replace(",", "").strip()
    try:
        x = ledger.amount_of(text, base)
    except ValueError as e:
        raise AuthoringRefused(str(e), "input_gap") from e
    if "month" in text:
        return x * 7 / 30
    if "year" in text or "annum" in text:
        return x / 52
    return x


def _start(raw, base: float) -> float:
    if raw is None or raw == "":
        return 0.0
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) if raw > 0 else 0.0
    try:
        return ledger.amount_of(str(raw).lower().replace("$", "").replace(",", "").strip(), base)
    except ValueError as e:
        raise AuthoringRefused(str(e), "input_gap") from e


def normalise(conn, me: int, kind: str, details: dict) -> Proposal:
    from . import veto
    d = details if isinstance(details, dict) else {}
    what = " ".join(str(d.get("what") or d.get("name") or kind or "").split())
    if not what:
        raise AuthoringRefused("say what is being made", "input_gap")
    people = _ints(d.get("people"))
    owner = d.get("owner_actor_id", d.get("owner"))
    owner = int(owner) if isinstance(owner, int) and not isinstance(owner, bool) else int(me)
    loc, place_text = d.get("location_id"), None
    ref = d.get("place") if d.get("place") is not None else loc
    if ref is not None:
        loc = veto.find_location(conn, ref)
        if loc is None and isinstance(ref, str):
            place_text = ref.strip()[:120] or None  # an unknown place is kept as words; never refused here
    money = d.get("money")
    money = money if isinstance(money, dict) else {"start": money}
    from_ref = str(money.get("from") or "me")
    base = 0.0
    try:
        holder = ledger.parse_holder(from_ref, int(me), conn)
        base = ledger.balance(conn, holder)
    except ValueError:
        pass  # the draw check in take_in names the problem
    leg = str(d.get("legality") or "unknown").lower()
    if leg not in ("legal", "grey", "illegal", "unknown"):
        leg = "unknown"
    cons = d.get("consequences")
    cons = tuple(str(c).strip() for c in (cons if isinstance(cons, (list, tuple)) else [cons] if cons else []) if str(c).strip())
    ready = d.get("ready_in_days")
    return Proposal(
        what=what, kind_text=str(kind or "")[:120], people=people, owner=owner,
        location_id=int(loc) if loc is not None else None, place_text=place_text, from_ref=from_ref,
        start_cost=_start(money.get("start"), base),
        income_weekly=_weekly(money.get("income"), base), upkeep_weekly=_weekly(money.get("upkeep"), base),
        agenda=str(d.get("agenda") or "")[:300], start_day=int(d.get("start_day") or _day(conn)),
        end_day=int(d["end_day"]) if d.get("end_day") is not None else None,
        recurrence_days=int(d["recurrence_days"]) if d.get("recurrence_days") is not None else None,
        legality=leg, knows=_ints(d.get("knows")), consequences=cons,
        source=str(d["source"])[:200] if d.get("source") else None, real_date=str(d["real_date"])[:40] if d.get("real_date") else None,
        ready_in_days=int(ready) if isinstance(ready, (int, float)) and not isinstance(ready, bool) and ready > 0 else None,
        details=dict(d))


# ---- the door -----------------------------------------------------------------------------------------------------

_STOP = frozenset("a an the of for in on at to by with and or from is are was were his her their its my our your".split())
_ENTITY_KEYS = (("actor_id", "actors"), ("enterprise_id", "civilian_enterprises"), ("outfit_id", "underworld_organizations"),
                ("institution_actor_id", "actors"), ("rumour_id", "rumours"))


def enabled(conn) -> bool:
    return bool(_rules(conn))


def _norm_name(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(s).lower()))


def _gap_key(shape: str, kind_text: str, what: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", (kind_text or what).lower()) if w not in _STOP][:3]
    return shape + ":" + " ".join(words)


def _check_facts(conn, p: Proposal, details: dict) -> None:
    """Established facts: the living, the already-held, a place that exists. A refusal names the clash."""
    from .player_operations import _living
    for aid in dict.fromkeys((p.owner, *p.people, *p.knows)):
        if not _living(conn, aid):
            row = conn.execute("SELECT name FROM actors WHERE id=?", (aid,)).fetchone()
            raise AuthoringRefused(f"{row[0] if row else 'actor ' + str(aid)} is dead")
    loc = details.get("location_id")
    if isinstance(loc, int) and not isinstance(loc, bool) and not conn.execute("SELECT 1 FROM locations WHERE id=?", (loc,)).fetchone():
        raise AuthoringRefused("unknown location")
    want = _norm_name(p.what)
    for r in conn.execute("SELECT id,name FROM held_things WHERE owner_actor_id=? AND status IN ('building','active','failing')", (p.owner,)):
        if _norm_name(r["name"]) == want:
            raise AuthoringRefused(f"that is already held (held thing {r['id']})")


def _readers(rules: dict, p: Proposal) -> tuple[list[str], list[str]]:
    words = rules.get("readers", {})

    def match(text: str) -> list[str]:
        t = text.lower()
        return [k for k, ws in words.items() if any(_has_word(t, w) for w in ws)]

    readers: list[str] = []
    unmapped: list[str] = []
    for phrase in p.consequences:
        hit = match(phrase)
        if hit:
            readers += [h for h in hit if h not in readers]
        else:
            unmapped.append(phrase)
    for k in match(p.agenda):
        if k not in readers:
            readers.append(k)
    if p.legality == "illegal" and "heat" not in readers:
        readers.append("heat")
    return readers, unmapped


def bump_gap(conn, gap_key: str, shape: str, held_id: int, missing: list[str]) -> None:
    day = _day(conn)
    row = conn.execute("SELECT examples_json,missing_json FROM depth_gaps WHERE gap_key=?", (gap_key,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO depth_gaps(gap_key,shape,count,first_day,last_day,examples_json,missing_json) VALUES (?,?,1,?,?,?,?)",
                     (gap_key, shape, day, day, json.dumps([held_id]), json.dumps(list(missing))))
        return
    ex = (json.loads(row["examples_json"]) + [held_id])[-5:]  # a sample for the reader, not a limit on the count
    miss = json.loads(row["missing_json"])
    miss += [m for m in missing if m not in miss]
    conn.execute("UPDATE depth_gaps SET count=count+1,last_day=?,examples_json=?,missing_json=?,status='open' WHERE gap_key=?",
                 (day, json.dumps(ex), json.dumps(miss), gap_key))


def _backing(out: dict) -> tuple[str | None, int | None]:
    if out.get("backing_table") and out.get("backing_id") is not None:
        return str(out["backing_table"]), int(out["backing_id"])
    for key, table in _ENTITY_KEYS:
        if key in out:
            return table, int(out[key])
    return None, None


def take_in(conn, me: int, kind: str, details: dict, call_id: str) -> dict:
    """Everything lasting the GM narrates: shape, veto-only checks, the maker (if any), one held_things row, a gap when nothing
    deeper exists. Raises AuthoringRefused for a refusal; all-or-nothing."""
    d = details if isinstance(details, dict) else {}
    rules = _rules(conn)
    if not rules:  # a package without intake data keeps today's path exactly
        return authoring._KINDS[authoring._kind_of(kind, d)](conn, int(me), d, str(call_id))
    prior = conn.execute("SELECT id,name,shape,gap_key FROM held_things WHERE call_id=?", (str(call_id),)).fetchone()
    if prior:  # a replay: one row, no second gap bump
        return {"status": "created", "kind": prior["shape"], "held_thing_id": int(prior["id"]), "name": prior["name"],
                "replayed": True, **({"gap": prior["gap_key"]} if prior["gap_key"] else {})}
    shape = shape_for(conn, kind, d)
    p = normalise(conn, int(me), kind, d)
    _check_facts(conn, p, d)
    day = _day(conn)
    conn.execute("SAVEPOINT intake_take")
    try:
        scaled = None
        income, upkeep = p.income_weekly, p.upkeep_weekly
        if p.start_cost > 0:
            try:
                holder = ledger.parse_holder(p.from_ref, int(me), conn)
            except ValueError as e:
                raise AuthoringRefused(str(e), "input_gap") from e
            if not ledger.can_draw(conn, int(me), holder):
                raise AuthoringRefused("He has no right to draw on that purse")
            spent = ledger.spend(conn, holder, p.start_cost, purpose=p.what, allow_partial=True)
            if spent < p.start_cost - 1e-9:
                share = spent / p.start_cost
                income, upkeep = income * share, upkeep * share
                scaled = "the money on hand covered only part of it"
        out: dict[str, Any] = {}
        if shape.make is not None:
            out = dict(shape.make(conn, int(me), p, str(call_id)) or {})
        table, bid = _backing(out)
        readers, unmapped = _readers(rules, p)
        name = (str(d.get("name") or "").strip() or str(out.get("name") or "") or p.what)[:80]
        floor = shape.floor_backed and table is None
        gap = _gap_key(shape.name, p.kind_text, p.what) if (floor or unmapped) else None
        status = "building" if p.ready_in_days else "active"
        hid = int(conn.execute(
            """INSERT INTO held_things(name,kind_text,shape,backing_table,backing_id,owner_actor_id,people_json,location_id,place_text,from_ref,
                 start_cost,income_weekly,upkeep_weekly,agenda,start_day,end_day,recurrence_days,legality,knows_json,consequences_json,
                 readers_json,unmapped_json,source,real_date,depth,status,gap_key,call_id,created_day,updated_day)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'B',?,?,?,?,?)""",
            (name, p.kind_text, shape.name, table, bid, p.owner, json.dumps(list(p.people)), p.location_id, p.place_text, p.from_ref,
             p.start_cost, income, upkeep, p.agenda, p.start_day, p.end_day, p.recurrence_days, p.legality, json.dumps(list(p.knows)),
             json.dumps(list(p.consequences)), json.dumps(readers), json.dumps(unmapped), p.source, p.real_date, status, gap,
             str(call_id), day, day)).lastrowid)
        if p.ready_in_days:
            from . import commitments
            commitments.record(conn, int(me), p.what, kind="intake", due_day=day + p.ready_in_days, details={"held_thing_id": hid})
        if gap:
            bump_gap(conn, gap, shape.name, hid, unmapped if unmapped else ["a deeper model for this shape"])
        if p.knows:
            from . import findings
            for k in p.knows:
                findings.tell(conn, k, [p.what], source=p.owner)
    except BaseException:
        conn.execute("ROLLBACK TO SAVEPOINT intake_take")
        conn.execute("RELEASE SAVEPOINT intake_take")
        raise
    conn.execute("RELEASE SAVEPOINT intake_take")
    out.update({"status": "scaled_down" if scaled else "created", "kind": shape.name, "held_thing_id": hid, "name": name})
    if scaled:
        out["scaled"] = scaled
    if gap:
        out["gap"] = gap
    return out


def adopt_floor(conn, shape_name: str) -> int:
    """Re-run the now-registered maker for every active floor row of a shape; the row gains its backing and loses its gap."""
    shape = next((s for s in shapes(conn) if s.name == shape_name), None)
    if shape is None or shape.make is None:
        return 0
    n = 0
    for r in conn.execute("SELECT * FROM held_things WHERE shape=? AND backing_table IS NULL AND status IN ('building','active','failing')",
                          (shape_name,)).fetchall():
        d = {"what": r["name"], "name": r["name"], "people": json.loads(r["people_json"]), "owner": r["owner_actor_id"],
             "place": r["location_id"] if r["location_id"] is not None else r["place_text"], "agenda": r["agenda"],
             "legality": r["legality"], "money": {"start": 0, "income": r["income_weekly"], "upkeep": r["upkeep_weekly"]}}
        p = normalise(conn, int(r["owner_actor_id"]), r["kind_text"], d)
        out = dict(shape.make(conn, int(r["owner_actor_id"]), p, str(r["call_id"] or f"adopt:{r['id']}")) or {})
        table, bid = _backing(out)
        if table is None:
            continue
        conn.execute("UPDATE held_things SET backing_table=?,backing_id=?,gap_key=NULL,updated_day=? WHERE id=?", (table, bid, _day(conn), r["id"]))
        n += 1
    open_left = conn.execute("SELECT 1 FROM held_things WHERE shape=? AND backing_table IS NULL AND gap_key IS NOT NULL AND status!='ended'",
                             (shape_name,)).fetchone()
    if not open_left:
        conn.execute("UPDATE depth_gaps SET status='built' WHERE shape=?", (shape_name,))
    return n


from . import intake_business  # noqa: E402  (registers the BZ1 makers; the module imports this one, so it comes last)
intake_business.register()
