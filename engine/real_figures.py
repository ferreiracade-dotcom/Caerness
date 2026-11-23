"""Real figures: documented real people in the world, within their public record.

A real person enters through the intake (shape `real_figure`) with a source for his state on the campaign's start, his public
roles and the kinds of wrongdoing on his record. He is then an ordinary actor under the engine's ordinary rules, with one
extra veto: he acts only in his public roles, and wrongdoing only of kinds on his record; a clean figure stays clean and an
invented man does the dirty work. Nothing offstage is refused for being real any more; what is refused is a contradiction
(a man the run has killed, a clean man asked to do dirty work, an invented person wearing a real name).
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
from typing import Iterable

from . import facts, history, veto
from .authoring import AuthoringRefused

_ALLOWED: set[str] = set()


@contextlib.contextmanager
def documented(name: str):
    """While the maker builds a documented figure's actor, the real-name veto lets his own name through."""
    key = veto.norm(name)
    _ALLOWED.add(key)
    try:
        yield
    finally:
        _ALLOWED.discard(key)


def allowed(name_norm: str) -> bool:
    return name_norm in _ALLOWED


def find(conn: sqlite3.Connection, name: str | None) -> sqlite3.Row | None:
    want = veto.norm(name)
    if not want:
        return None
    return conn.execute("SELECT * FROM real_figures WHERE name_norm=?", (want,)).fetchone()


def _is_dead(conn, aid: int | None) -> bool:
    if aid is None:
        return False
    from .player_operations import _living
    return not _living(conn, int(aid))


def recorded(conn, details: dict) -> dict | None:
    """A figure already in the world answers with himself; one the run has killed is refused as living."""
    ex = find(conn, details.get("name"))
    if ex is None:
        return None
    if _is_dead(conn, ex["actor_id"]):
        raise AuthoringRefused(f"{ex['name']} is dead in this run; he cannot appear as living. Use an invented man")
    return {"status": "created", "kind": "real_figure", "name": ex["name"], "actor_id": ex["actor_id"], "real_figure": "figure:" + history.slug(ex["name"]),
            "replayed": True}


def _seeded_actor(conn, name: str) -> int | None:
    """The package already holds some real people as actors (the bible's own names); proposing one documents him, never duplicates him."""
    want = veto.norm(name)
    if not any(veto.norm(r.get("name")) == want for r in veto._gazetteer(conn).get("real_people", [])):
        return None
    for r in conn.execute("SELECT id,name FROM actors WHERE actor_type='character' AND status NOT IN ('deceased','dead')"):
        if veto.norm(r["name"]) == want:
            return int(r["id"])
    return None


def propose(conn, me: int, p, call_id: str) -> dict:
    """The `real_figure` shape's maker. Details: name, source, public_roles, record (kinds of wrongdoing on his record), status
    (alive | dead | jailed, as of the campaign start), age, work, and the person fields the person maker takes."""
    from . import authoring
    d = dict(p.details)
    name = " ".join(str(d.get("name") or "").split())
    if not name:
        raise AuthoringRefused("a real person needs his name", "input_gap")
    src = str(d.get("source") or "").strip()
    if not src:
        raise AuthoringRefused(f"a real person needs his source (a URL and a short quote, or \"memory\", marked to verify) for {name}'s state on the start date", "input_gap")
    status = str(d.get("status") or "alive").lower()
    if status not in ("alive", "dead", "jailed"):
        raise AuthoringRefused("status is alive, dead or jailed", "input_gap")
    existing = find(conn, name)
    if existing is not None:
        if _is_dead(conn, existing["actor_id"]):
            raise AuthoringRefused(f"{existing['name']} is dead in this run; he cannot appear as living. Use an invented man")
        return {"backing_table": "real_figures", "backing_id": int(existing["id"]), "actor_id": existing["actor_id"], "name": existing["name"],
                "replayed": True}
    if status == "dead":
        raise AuthoringRefused(f"{name} is dead on the campaign's start according to your source; a dead real person does not act. Use an invented man")
    roles = [str(r).strip() for r in (d.get("public_roles") or []) if str(r).strip()]
    record = [str(r).strip() for r in (d.get("record") or []) if str(r).strip()]
    person = {k: v for k, v in d.items() if k in ("name", "sex", "age", "work", "category", "stage", "place", "location_id", "ties", "wants", "holds",
                                                   "from_elsewhere")}
    seeded = _seeded_actor(conn, name)
    if seeded is not None:
        out = {"actor_id": seeded, "name": name, "adopted": "an actor of this name was already in the world; he is now documented"}
    else:
        with documented(name):
            out = authoring._person(conn, me, person, call_id)
    aid = out.get("actor_id")
    memory = src.lower() == "memory"
    provisional = 1 if (memory and roles and history.is_major(conn, "office")) else 0
    rid = int(conn.execute(
        "INSERT INTO real_figures(name,name_norm,actor_id,public_roles_json,record_json,source,verify,provisional,status) VALUES (?,?,?,?,?,?,?,?,?)",
        (name, veto.norm(name), aid, json.dumps(roles), json.dumps(record), src[:400], "to verify" if memory else "verified", provisional, status)).lastrowid)
    key = "figure:" + history.slug(name)
    facts.ensure(conn)
    facts._put(conn, key, name, f"{name}: real person; public roles {', '.join(roles) or 'none given'}; on his record: {', '.join(record) or 'nothing'}",
               "Fixed", source=src[:200])
    return {**out, "backing_table": "real_figures", "backing_id": rid, "real_figure": key, "provisional": bool(provisional)}


def check_acts(conn: sqlite3.Connection, actor_ids: Iterable[int], legality: str, kind_text: str) -> None:
    """A real figure takes part in unlawful wrongdoing only of a kind on his record. Applies to any actor flagged real; no
    other actor, the protagonist included, is treated differently by it."""
    if str(legality or "").lower() != "illegal":
        return
    ids = [int(a) for a in actor_ids if a is not None]
    if not ids:
        return
    q = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT name,record_json FROM real_figures WHERE actor_id IN ({q})", ids).fetchall()
    words = history._tokens(kind_text)
    for r in rows:
        record = " ".join(json.loads(r["record_json"] or "[]"))
        if not (words & history._tokens(record)):
            raise AuthoringRefused(f"{r['name']} is a real person whose record shows no wrongdoing of this kind; "
                                   "use an invented man for the dirty work")
