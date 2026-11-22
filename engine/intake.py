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
