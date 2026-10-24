"""World facts: the setting's tagged items (Fixed, Open, Weather, Anchor, Tendency, Design, Example) and who holds each Open office.

The table is created lazily (never in schema.sql) and only for a world package whose bible tags its items, so a Caerness
database is untouched. The engine does not read free text for contradictions (that is the GM's job); it keeps three rules:
a Fixed fact changes only with a stated cause, an Open slot once filled stays with its holder, and a lookup shows the tag.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

TAGS = ("Fixed", "Open", "Weather", "Anchor", "Tendency", "Design", "Example")
_TAG_RE = re.compile(r"\((" + "|".join(TAGS) + r")\b")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS world_facts (
    key TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    tag TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    source TEXT,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    institution_key TEXT,
    holder_actor_id INTEGER,
    filled_day INTEGER,
    cause TEXT
);
CREATE TABLE IF NOT EXISTS world_fact_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_key TEXT NOT NULL,
    old_text TEXT,
    new_text TEXT NOT NULL,
    cause TEXT,
    world_day INTEGER,
    call_id TEXT
);
"""

class FactRefused(ValueError):
    """A fact rule refused the change; the message names it."""


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _slug(text: str) -> str:
    return _norm(text).replace(" ", "-")


def exists(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_facts'").fetchone() is not None


def ensure(conn: sqlite3.Connection) -> None:
    for stmt in _SCHEMA.split(";"):  # not executescript: that would commit the caller's open transaction
        if stmt.strip():
            conn.execute(stmt)


def _date(conn: sqlite3.Connection, day: int | None) -> str | None:
    if day is None:
        return None
    from .world_calendar import format_date
    from .world_package import package_for
    try:
        return format_date(package_for(conn), int(day))
    except Exception:
        return f"day {day}"


def _today(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _put(conn: sqlite3.Connection, key: str, subject: str, text: str, tag: str, *, start: str | None = None, end: str | None = None,
         source: str | None = None, aliases: tuple[str, ...] | list[str] = (), institution_key: str | None = None) -> None:
    conn.execute(
        """INSERT INTO world_facts(key,subject,text,tag,start_date,end_date,source,aliases_json,institution_key) VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET subject=excluded.subject,text=excluded.text,tag=excluded.tag,start_date=excluded.start_date,
           end_date=excluded.end_date,source=excluded.source,aliases_json=excluded.aliases_json,institution_key=excluded.institution_key""",
        (key, subject, text, tag, start, end, source, json.dumps(list(aliases), ensure_ascii=False), institution_key))


def _claim_tag(cl: dict) -> str | None:
    t = cl.get("tag") or cl.get("canon_tag")
    if t in TAGS:
        return t
    # fallback for a seed with no explicit tag: the bible tag written in the provenance, e.g. "Part I 2.5 (Fixed; who Open)"
    m = _TAG_RE.search(str(cl.get("provenance") or ""))
    return m.group(1) if m else None


def load_package_facts(conn: sqlite3.Connection, package, seed: dict) -> dict[str, int]:
    """Load the tagged items of a package: seed claims, timeline entries, Example persons and the Open offices.
    Does nothing (and creates no table) for a package whose bible carries no tags, such as Caerness."""
    timeline: list[dict] = []
    path = package.data.get("timeline")
    if path is not None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        timeline = raw.get("entries", []) if isinstance(raw, dict) else raw
    tagged = any(p.get("canon_tag") for p in seed.get("persons", [])) or any(e.get("tag") for e in timeline)
    if not tagged:
        return {}
    ensure(conn)
    n = {"claims": 0, "timeline": 0, "examples": 0, "offices": 0}
    for cl in seed.get("claims", []):
        tag = _claim_tag(cl)
        if tag:
            key = "claim:" + str(cl["id"]).split(":")[-1]
            _put(conn, key, key.split(":", 1)[1].replace("-", " "), cl.get("text") or "", tag, source=str(cl.get("provenance") or ""))
            n["claims"] += 1
    for e in timeline:
        if e.get("tag") in TAGS:
            _put(conn, "timeline:" + _slug(e["name"]), e["name"], str(e.get("source") or e["name"]), e["tag"],
                 start=e.get("exists"), end=None, source=str(e.get("mark") or ""), aliases=e.get("aliases") or [])
            n["timeline"] += 1
    for p in seed.get("persons", []):
        if p.get("canon_tag") == "Example":
            _put(conn, "person:" + str(p["id"]).split(":")[-1], p["name"], str(p.get("role") or p.get("public_identity_text") or ""),
                 "Example", source="seed: any named man is replaceable")
            n["examples"] += 1
    for o in (seed.get("meta") or {}).get("open_offices") or []:  # the package's own list: subject, institution_ref, aliases, plural, source
        subject, inst = o["subject"], o.get("institution_ref")
        if o.get("plural"):  # a group of holders (judges, pastors, a board): Open, but no single holder to track
            key, text = "open:" + _slug(subject), f"{subject}: names are Open (not yet decided)."
        else:
            key, text = f"office:{_slug(inst.split(':')[-1]) if inst else 'state'}:{_slug(subject)}", f"{subject}: the holder's name is Open (not yet decided)."
        _put(conn, key, subject, text, "Open", source=str(o.get("source") or ""), aliases=o.get("aliases") or [], institution_key=inst)
        n["offices"] += 1
    return n


# ---------------------------------------------------------------- reading

def _row_view(conn: sqlite3.Connection, r: sqlite3.Row) -> dict:
    out: dict[str, Any] = {"key": r["key"], "subject": r["subject"], "tag": r["tag"], "text": r["text"][:300]}
    if r["start_date"]:
        out["from"] = r["start_date"]
    ov = conn.execute("SELECT new_text,cause FROM world_fact_overrides WHERE fact_key=? ORDER BY id DESC LIMIT 1", (r["key"],)).fetchone()
    if ov:
        out["overridden"] = {"now": ov["new_text"][:300], "cause": ov["cause"]}
    if r["tag"] == "Open" and r["key"].startswith("office:"):
        h = holder_of(conn, r["key"])
        out["holder"] = h if h else "Open: not yet decided"
    return out


def get(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    if not exists(conn):
        return None
    return conn.execute("SELECT * FROM world_facts WHERE key=?", (key,)).fetchone()


def _names(r: sqlite3.Row) -> list[str]:
    return [_norm(r["subject"])] + [_norm(a) for a in json.loads(r["aliases_json"] or "[]")]


def resolve(conn: sqlite3.Connection, text: str, *, open_only: bool = False, loose: bool = False) -> sqlite3.Row | None:
    """The fact a key or words name. Exact key, then exact subject or alias; with `loose`, a single fact whose subject contains the words."""
    if not exists(conn):
        return None
    q = str(text or "").strip()
    if not q:
        return None
    r = conn.execute("SELECT * FROM world_facts WHERE key=?", (q,)).fetchone()
    if r and (not open_only or r["key"].startswith("office:")):
        return r
    rows = conn.execute("SELECT * FROM world_facts" + (" WHERE tag='Open' AND key LIKE 'office:%'" if open_only else "")).fetchall()
    nq = _norm(q)
    nq = re.sub(r"^(the|a|an) ", "", nq)
    hit = [x for x in rows if nq in [re.sub(r"^(the|a|an) ", "", n) for n in _names(x)]]
    if len(hit) == 1:
        return hit[0]
    if hit:
        return None  # ambiguous: say the office more fully
    if loose and nq:
        part = [x for x in rows if nq in _norm(x["subject"])]
        if len(part) == 1:
            return part[0]
    return None


def search(conn: sqlite3.Connection, q: str, limit: int = 5, *, text_too: bool = True) -> list[dict]:
    if not exists(conn):
        return []
    nq = _norm(q)
    if len(nq) < 3:
        return []
    out = []
    for r in conn.execute("SELECT * FROM world_facts ORDER BY key").fetchall():
        hay = " ".join(_names(r)) + (" " + _norm(r["text"]) if text_too else "")
        if nq in hay:
            out.append(_row_view(conn, r))
            if len(out) >= limit:
                break
    return out


def view_of(conn: sqlite3.Connection, r: sqlite3.Row) -> dict:
    return _row_view(conn, r)


def holder_of(conn: sqlite3.Connection, key: str) -> dict | None:
    """The living actor holding an Open slot: {actor_id, name, since}; None when unfilled or the holder has died."""
    r = get(conn, key)
    if r is None or r["holder_actor_id"] is None:
        return None
    from .household_life import _actor_is_living
    a = conn.execute("SELECT id,name FROM actors WHERE id=?", (r["holder_actor_id"],)).fetchone()
    if a is None or not _actor_is_living(conn, int(a["id"])):
        return None
    return {"actor_id": int(a["id"]), "name": a["name"], "since": _date(conn, r["filled_day"])}


def office_of(conn: sqlite3.Connection, actor_id: int) -> list[str]:
    if not exists(conn):
        return []
    return [r["subject"] for r in conn.execute("SELECT key,subject FROM world_facts WHERE holder_actor_id=? ORDER BY key", (int(actor_id),))
            if holder_of(conn, r["key"])]


def holder_hits(conn: sqlite3.Connection, q: str) -> list[tuple[sqlite3.Row, str]]:
    """(actor row, office) for living holders of an Open office whose name or alias contains the words."""
    if not exists(conn):
        return []
    nq = _norm(q)
    out = []
    for r in conn.execute("SELECT * FROM world_facts WHERE holder_actor_id IS NOT NULL ORDER BY key").fetchall():
        if nq and any(nq in n for n in _names(r)) and holder_of(conn, r["key"]):
            a = conn.execute("SELECT * FROM actors WHERE id=?", (r["holder_actor_id"],)).fetchone()
            if a is not None:
                out.append((a, r["subject"]))
    return out


# ---------------------------------------------------------------- Open slots

def check_vacant(conn: sqlite3.Connection, key: str) -> None:
    """Raise FactRefused ("held by X since <date>") when a living actor holds the slot."""
    h = holder_of(conn, key)
    if h:
        r = get(conn, key)
        raise FactRefused(f"the {r['subject']} is held by {h['name']} since {h['since']}")


def fill_open(conn: sqlite3.Connection, key: str, actor_id: int, cause: str | None = None) -> dict:
    """Record `actor_id` as the holder of an Open slot. Refused while a living actor holds it; once filled it is held."""
    r = get(conn, key)
    if r is None or r["tag"] != "Open":
        raise FactRefused(f"{key} is not an Open slot")
    check_vacant(conn, key)
    day = _today(conn)
    conn.execute("UPDATE world_facts SET holder_actor_id=?,filled_day=?,cause=? WHERE key=?",
                 (int(actor_id), day, (cause or "authored in play")[:300], key))
    return {"key": key, "subject": r["subject"], "actor_id": int(actor_id), "since": _date(conn, day)}


# ---------------------------------------------------------------- changing a fact

def override(conn: sqlite3.Connection, key_or_words: str, new_text: str, cause: str | None, call_id: str) -> dict:
    """A GM change to a fact. A Fixed fact needs a stated cause (a retcon needs a cause event); other tags change freely."""
    r = resolve(conn, key_or_words, loose=True)
    if r is None:
        raise ValueError(f"no world fact named {key_or_words!r}")
    cause = " ".join(str(cause or "").split())
    if r["tag"] == "Fixed" and len(cause) < 8:
        raise FactRefused(f"{r['key']} is Fixed in the setting; changing it needs a stated cause (say what happened in the world that changes it)")
    conn.execute("INSERT INTO world_fact_overrides(fact_key,old_text,new_text,cause,world_day,call_id) VALUES (?,?,?,?,?,?)",
                 (r["key"], r["text"], new_text, cause[:300] or None, _today(conn), call_id))
    return {"fact": r["key"], "tag": r["tag"], "overridden": True, **({"cause": cause[:300]} if cause else {}),
            "summary": f"Fact {r['key']} ({r['tag']}) changed" + (f": {cause[:80]}" if cause else "")}
