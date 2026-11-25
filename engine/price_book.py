"""What things cost, from the world package's price book (data key `price_book`; a package without one has none).

An item carries its own figure or points at a row of the package's price table, so there is one figure for each thing.
Later years scale by the table's index rows. A price is shown beside what the buyer earns in a week."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from . import money_records, world_calendar
from .world_package import package_for

_FILES: dict = {}


def _read(path) -> dict:
    if path is None:
        return {}
    path = Path(path)
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    if key not in _FILES:
        _FILES[key] = json.loads(path.read_text(encoding="utf-8"))
    return _FILES[key]


def data(conn: sqlite3.Connection) -> dict:
    return _read(package_for(conn).data.get("price_book"))


def year(conn: sqlite3.Connection) -> int | None:
    pkg = package_for(conn)
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    found = re.findall(r"\b(\d{4})\b", world_calendar.format_date(pkg, day))
    return int(found[-1]) if found else None


def _rounded(x: float) -> float:
    return round(x, 2) if x < 20 else float(round(x))


def items(conn: sqlite3.Connection) -> list[dict]:
    """Every item with this year's figure."""
    book = data(conn)
    if not book:
        return []
    table = {r["key"]: r for r in _read(package_for(conn).data.get("prices")).get("rows", [])}
    now = year(conn)
    factor = 1.0
    if now is not None and now != book.get("year") and book.get("index"):
        row = table.get(book["index"].format(year=now))
        factor = float(row["default"]) if row else 1.0
    out = []
    for item in book["items"]:
        got = dict(item)
        if item.get("ref"):
            row = table.get(item["ref"])
            if row is None or row.get("default") is None:
                continue
            low, high = row.get("range") or (row["default"], row["default"])
            got.update(price=row["default"], low=low, high=high, mark="Design proposal" if row["tag"] == "Design" else "Sourced",
                       source=str(row.get("source") or "the price table"))
        if factor != 1.0:
            for k in ("price", "low", "high"):
                got[k] = _rounded(float(got[k]) * factor)
        out.append(got)
    return out


def _words(text: str) -> str:
    """Lower case, punctuation gone, simple plurals dropped, padded so whole words can be looked for."""
    parts = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split()
    return " " + " ".join(p[:-1] if len(p) > 3 and p.endswith("s") and not p.endswith("ss") else p for p in parts) + " "


def _score(item: dict, wanted: str) -> int:
    """How well an item answers: the longer the phrases of it that are asked for, the better."""
    got = {_words(w) for w in [*item.get("words", []), item.get("group", "")] if w}
    score = sum(len(w) ** 2 for w in got if w in wanted)
    if score:
        score += sum(1 for w in _words(item["name"]).split() if f" {w} " in wanted)
    return score


def search(conn: sqlite3.Connection, query: str, limit: int = 12) -> list[dict]:
    wanted = _words(query)
    scored = [(s, n, i) for n, i in enumerate(items(conn)) if (s := _score(i, wanted))]
    return [i for _, _, i in sorted(scored, key=lambda t: (-t[0], t[1]))[:limit]]


def by_key(conn: sqlite3.Connection, key: str) -> dict | None:
    return next((i for i in items(conn) if i["key"] == key), None)


def weekly_pay(conn: sqlite3.Connection, actor_id: int) -> float | None:
    """What this person is paid by the week, where a wage is agreed."""
    got = conn.execute("SELECT SUM(amount_usd*7.0/every_days) FROM agreement_terms WHERE ref_kind='wage' AND status='active' "
                       "AND creditor_ref=? AND every_days>0", (f"person:{actor_id}",)).fetchone()[0]
    return round(float(got), 2) if got else None


def show(conn: sqlite3.Connection, item: dict, pay: float | None = None, brief: bool = False) -> dict:
    per = f" {item['per']}" if item.get("per") else ""
    out = {"item": item["name"], "price": money_records.fmt(conn, item["price"]) + per}
    if item["low"] != item["high"]:
        out["range"] = f"{money_records.fmt(conn, item['low'])} to {money_records.fmt(conn, item['high'])}"
    if pay:
        out["weeks_pay"] = round(float(item["price"]) / pay, 1)
    if not brief:
        out["basis"] = item["mark"]
        if item["mark"] == "Sourced":
            out["source"] = item["source"][:160]
    return out


def lookup(conn: sqlite3.Connection, query: str, actor_id: int | None) -> dict:
    book = items(conn)
    if not book:
        return {"found": False, "hint": "this world keeps no price book"}
    found = search(conn, query) if str(query).strip() else []
    if not found:
        return {"found": False, "groups": sorted({i["group"] for i in book}),
                "hint": "ask as 'prices <thing or group>'; for what the book lacks, price it in proportion to what it holds"}
    pay = weekly_pay(conn, actor_id) if actor_id is not None else None
    out = {"found": True, "year": year(conn), "prices": [show(conn, i, pay) for i in found]}
    if pay:
        out["weekly_pay"] = money_records.fmt(conn, pay)
    return out


def in_play(conn: sqlite3.Connection, texts: list[str], actor_id: int | None, limit: int = 5) -> list[dict]:
    """Prices of what is being bought, priced or saved for: only sentences that speak of buying count."""
    book = data(conn)
    if not book:
        return []
    cues = [_words(w) for w in book.get("purchase_words", [])]
    wanted = " "
    for text in texts:
        for sentence in re.split(r"(?<=[.!?;])\s+", str(text or "")):
            said = _words(sentence)
            if any(c in said for c in cues):
                wanted += said.strip() + " | "
    if wanted == " ":
        return []
    scored = [(s, n, i) for n, i in enumerate(items(conn))
              if (s := sum(len(w) ** 2 for w in {_words(x) for x in i.get("words", [])} if w in wanted))]
    pay = weekly_pay(conn, actor_id) if actor_id is not None else None
    return [show(conn, i, pay, brief=True) for _, _, i in sorted(scored, key=lambda t: (-t[0], t[1]))[:limit]]
