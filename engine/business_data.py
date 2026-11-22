"""The package's `business` data file: seasonality, dated shocks, approval kinds, venture kinds, place kinds, breach words.

The engine names no world. A file with an unknown key or word is refused at load, naming the file, the key and the word.
Caerness has no such file, so `load` is None there and every BZ1 tick is a no-op.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

BREACH_PATHS = ("tension", "debt", "grudge", "claim")
PAYOFF_KINDS = ("money", "place", "terms", "none")
BUILDING_KINDS = ("residence", "workshop", "shop", "warehouse", "hall", "temple", "fortified_residence",
                  "public_building", "bridge", "garden", "estate_improvement", "other")
_TOP = {"basis", "assumption", "extra_sectors", "seasonality", "shocks", "approval_kinds", "venture_kinds",
        "place_kinds", "breach_words"}
_BLOCKS = {"seasonality", "shocks", "approval_kinds", "venture_kinds", "place_kinds", "breach_words"}


class BusinessDataError(ValueError):
    """The business data file is wrong; the message names the file, the key and the word."""


def _bad(source: str, key: str, word: Any, why: str) -> BusinessDataError:
    return BusinessDataError(f"{source}: {key}: {word!r} {why}")


def _number(source: str, key: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _bad(source, key, value, "is not a number")
    return float(value)


def validate(data: dict, *, source: str, sectors: set[str]) -> dict:
    """Check a parsed business file against the fixed engine vocabulary and its own declared words; returns it."""
    if not isinstance(data, dict):
        raise _bad(source, "(file)", type(data).__name__, "is not an object")
    for key in data:
        if key not in _TOP:
            raise _bad(source, "(top level)", key, "is not a known key")
    for part in ("basis", "assumption"):
        for key in data.get(part) or {}:
            if key not in _BLOCKS:
                raise _bad(source, part, key, "is not a block of this file")
    known = set(sectors) | set(data.get("extra_sectors") or [])
    for sector, months in (data.get("seasonality") or {}).items():
        if sector not in known:
            raise _bad(source, "seasonality", sector, "is not a sector the package declares")
        if not isinstance(months, list) or len(months) != 12:
            raise _bad(source, f"seasonality.{sector}", months, "must be twelve monthly multipliers")
        for m in months:
            _number(source, f"seasonality.{sector}", m)
    for i, shock in enumerate(data.get("shocks") or []):
        where = f"shocks[{i}]"
        for need in ("name", "from", "sectors", "source"):
            if need not in shock:
                raise _bad(source, where, need, "is missing")
        for edge in ("from", "to"):
            if shock.get(edge) is not None:
                try:
                    date.fromisoformat(str(shock[edge]))
                except ValueError as e:
                    raise _bad(source, f"{where}.{edge}", shock[edge], "is not an ISO date") from e
        for sector, mult in shock["sectors"].items():
            if sector not in known:
                raise _bad(source, f"{where}.sectors", sector, "is not a sector the package declares")
            _number(source, f"{where}.sectors.{sector}", mult)
    approvals = set(data.get("approval_kinds") or [])
    for kind, spec in (data.get("venture_kinds") or {}).items():
        if not spec.get("stages"):
            raise _bad(source, f"venture_kinds.{kind}", "stages", "is missing or empty")
        keys = set()
        for st in spec["stages"]:
            for need in ("key", "days", "cost_share", "approvals", "driver_sector"):
                if need not in st:
                    raise _bad(source, f"venture_kinds.{kind}", need, "is missing from a stage")
            sk = st["key"]
            if sk in keys:
                raise _bad(source, f"venture_kinds.{kind}", sk, "is a repeated stage key")
            keys.add(sk)
            for a in st["approvals"]:
                if a not in approvals:
                    raise _bad(source, f"venture_kinds.{kind}.{sk}.approvals", a, "is not in approval_kinds")
            if st["driver_sector"] not in known:
                raise _bad(source, f"venture_kinds.{kind}.{sk}.driver_sector", st["driver_sector"],
                           "is not a sector the package declares")
            if _number(source, f"venture_kinds.{kind}.{sk}.days", st["days"]) <= 0:
                raise _bad(source, f"venture_kinds.{kind}.{sk}.days", st["days"], "must be above zero")
            if _number(source, f"venture_kinds.{kind}.{sk}.cost_share", st["cost_share"]) < 0:
                raise _bad(source, f"venture_kinds.{kind}.{sk}.cost_share", st["cost_share"], "must not be negative")
        if _number(source, f"venture_kinds.{kind}.stall_days", spec.get("stall_days", -1)) < 0:
            raise _bad(source, f"venture_kinds.{kind}.stall_days", spec.get("stall_days"), "must be given")
        pk = (spec.get("payoff") or {}).get("kind")
        if pk not in PAYOFF_KINDS:
            raise _bad(source, f"venture_kinds.{kind}.payoff.kind", pk, f"is not one of {PAYOFF_KINDS}")
    for kind, spec in (data.get("place_kinds") or {}).items():
        if spec.get("building_kind") not in BUILDING_KINDS:
            raise _bad(source, f"place_kinds.{kind}.building_kind", spec.get("building_kind"),
                       "is not a building kind the engine has")
        for need in ("upkeep_usd_30", "decay_per_30_unpaid", "base_capacity"):
            if need not in spec:
                raise _bad(source, f"place_kinds.{kind}", need, "is missing")
            _number(source, f"place_kinds.{kind}.{need}", spec[need])
    for word, path in (data.get("breach_words") or {}).items():
        if path not in BREACH_PATHS:
            raise _bad(source, f"breach_words.{word}", path, f"is not one of {BREACH_PATHS}")
    return data


def parse(path: Path, sectors: set[str]) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as e:
        raise BusinessDataError(f"{Path(path).name}: invalid JSON: {e}") from e
    return validate(data, source=Path(path).name, sectors=sectors)


def load(conn: sqlite3.Connection) -> dict | None:
    """The campaign package's validated business file, or None when the package has none (Caerness)."""
    from . import business
    from .world_package import package_for, pass_memo
    path = package_for(conn).data.get("business")
    if path is None:
        return None

    def _read():
        sectors = {str(a.get("sector")) for a in business.archetypes(conn).values()}
        return parse(path, sectors)
    return pass_memo(conn, f"business_data:{path}", _read)


def _need(conn: sqlite3.Connection) -> dict:
    data = load(conn)
    if data is None:
        raise BusinessDataError("this world package has no business data file")
    return data


def venture_kind(conn: sqlite3.Connection, kind: str) -> dict:
    kinds = _need(conn).get("venture_kinds") or {}
    if kind not in kinds:
        raise BusinessDataError(f"business.json: venture_kinds: {kind!r} is not a venture kind this package declares")
    return kinds[kind]


def place_kind(conn: sqlite3.Connection, kind: str) -> dict:
    kinds = _need(conn).get("place_kinds") or {}
    if kind not in kinds:
        raise BusinessDataError(f"business.json: place_kinds: {kind!r} is not a place kind this package declares")
    return kinds[kind]


def breach_path(conn: sqlite3.Connection, word: str) -> str:
    words = _need(conn).get("breach_words") or {}
    if word not in words:
        raise BusinessDataError(f"business.json: breach_words: {word!r} is not a breach word this package declares")
    return words[word]
