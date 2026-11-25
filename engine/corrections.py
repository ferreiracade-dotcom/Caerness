"""The game master sets the record straight on the player's word (schema 130).

An event is undone with the ties, households and feelings it made; a person's work, place, age, sex, ties, household or
money is set. The engine refuses only what cannot be: reviving the dead, moving a past event's day, and contradicting a
Fixed canon fact without a cause. Otherwise it does as told and keeps what changed, the player's words and the day.
Nothing here commits: the caller owns the transaction, so a refusal part way through changes nothing."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager

NEVER = "[never happened] "
DEAD = ("dead", "deceased")
ALIVE = ("active", "alive", "living")
OPS = ("undo_event", "person", "relationship", "kinship", "household", "cash")
STRUCTURAL = {"union", "separation", "dissolution", "household_formation", "household_split", "migration", "adoption",
              "guardianship", "birth", "service_change"}
RECIPROCAL = {"spouse": "spouse", "sibling": "sibling", "parent": "child", "child": "parent", "guardian": "ward",
              "ward": "guardian", "adoptive_parent": "adoptive_child", "adoptive_child": "adoptive_parent", "other": "other"}
# the day something happened is never moved
PAST_DAYS = {"events": {"day"}, "life_events": {"day"}, "relationship_history": {"day"}, "causal_links": {"day"},
             "interactions": {"created_day"}, "agreements": {"created_day"}}
PERSON_FIELDS = ("person", "work", "business", "role", "location", "home", "age", "birth_day", "sex", "alive", "cause")


class Refused(ValueError):
    """A correction that cannot be made; the message names why."""


# ---------------------------------------------------------------- reading

def day_of(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _me(conn) -> int | None:
    r = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _name(conn, actor_id) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()
    return str(r[0]) if r else f"person {actor_id}"


def is_dead(conn, actor_id: int) -> bool:
    a = conn.execute("SELECT status FROM actors WHERE id=?", (actor_id,)).fetchone()
    p = conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    return bool((a and a[0] in DEAD) or (p and p[0] in DEAD))


def _revival(conn, actor_id: int) -> Refused:
    return Refused(f"{_name(conn, actor_id)} is dead; the dead are not brought back")


def _number(value, prefixes: tuple[str, ...]) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = str(value).strip()
    head, _, tail = text.partition(":")
    if tail and head.lower() in prefixes:
        text = tail.strip()
    return int(text) if text.isdigit() else None


def _find(conn, value, field: str, table: str, prefixes: tuple[str, ...]) -> int:
    if value is None or str(value).strip() == "":
        raise Refused(f"{field} is required (an id or a name)")
    n = _number(value, prefixes)
    if n is not None:
        if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (n,)).fetchone():
            raise Refused(f"{field}: there is no {prefixes[0]} {n}")
        return n
    found = [r[0] for r in conn.execute(f"SELECT id FROM {table} WHERE lower(name)=lower(?)", (str(value).strip(),))]
    if len(found) != 1:
        raise Refused(f"{field}: no one {prefixes[0]} called '{value}'; give an id")
    return int(found[0])


def actor_ref(conn, value, field: str = "person") -> int:
    if str(value).strip().lower() == "me":
        me = _me(conn)
        if me is None:
            raise Refused("there is no protagonist yet")
        return me
    return _find(conn, value, field, "actors", ("person", "actor"))


def check_canon(conn, actor_ids, cause: str | None) -> None:
    """A change about someone a Fixed canon fact names needs a cause, as changing the fact itself does."""
    if len(" ".join(str(cause or "").split())) >= 8:
        return
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_facts'").fetchone():
        return
    facts = conn.execute("SELECT key,subject,text,holder_actor_id FROM world_facts WHERE tag='Fixed' ORDER BY key").fetchall()
    for aid in sorted(set(actor_ids)):
        name = _name(conn, aid)
        named = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.IGNORECASE)
        for f in facts:
            if f["holder_actor_id"] == aid or named.search(f"{f['subject']}\n{f['text']}"):
                raise Refused(f"{name} is named by the Fixed canon fact {f['key']} ({f['subject']}); give a cause (what "
                              "happened in the story that changes it) to go against it")


# ---------------------------------------------------------------- writing, and keeping what changed

class _Log:
    def __init__(self):
        self.changes: list[dict] = []

    def note(self, field: str, old, new, **about) -> None:
        if old != new:
            self.changes.append({**about, "field": field, "old": old, "new": new})

    @staticmethod
    def _where(where: dict) -> tuple[str, list]:
        return " AND ".join(f"{k} IS ?" for k in where), list(where.values())

    def rows(self, conn, table: str, where: dict) -> list[dict]:
        sql, args = self._where(where)
        return [dict(r) for r in conn.execute(f"SELECT rowid AS _row,* FROM {table} WHERE {sql}", args)]

    @contextmanager
    def watched(self, conn, table: str, where: dict):
        """Keep whatever a block changes in the rows that match."""
        before = {r["_row"]: r for r in self.rows(conn, table, where)}
        yield
        after = {r["_row"]: r for r in self.rows(conn, table, where)}
        for key in sorted(set(before) | set(after)):
            old, new = before.get(key), after.get(key)
            row = (new or old).get("id", key)
            if old is None:
                self.changes.append({"table": table, "row": row, "field": "(added)", "old": None, "new": _bare(new)})
            elif new is None:
                self.changes.append({"table": table, "row": row, "field": "(removed)", "old": _bare(old), "new": None})
            else:
                for col in old:
                    if col != "_row":
                        self.note(col, old[col], new[col], table=table, row=row)

    def update(self, conn, table: str, where: dict, values: dict) -> None:
        sql, args = self._where(where)
        keys = [r["_row"] for r in self.rows(conn, table, where)]  # the update may change the columns matched on
        for key in keys:
            with self.watched(conn, table, {"rowid": key}):
                conn.execute(f"UPDATE {table} SET {','.join(f'{k}=?' for k in values)} WHERE rowid=?", (*values.values(), key))

    def delete(self, conn, table: str, where: dict) -> None:
        for r in self.rows(conn, table, where):
            conn.execute(f"DELETE FROM {table} WHERE rowid=?", (r["_row"],))
            self.changes.append({"table": table, "row": r.get("id", r["_row"]), "field": "(removed)", "old": _bare(r), "new": None})


def _bare(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in ("_row", "created_at")}


def describe(c: dict) -> str:
    where = c.get("who") or f"{c.get('table')} {c.get('row')}"
    if c["field"] in ("(removed)", "(added)"):
        kept = c["old"] or c["new"] or {}
        short = ", ".join(f"{k}={v}" for k, v in kept.items() if v not in (None, "", "{}") and k != "id")
        return f"{where} {c['field'].strip('()')}: {short[:160]}"
    return f"{where}: {c['field']} {str(c['old'])[:60]} -> {str(c['new'])[:60]}"


# ---------------------------------------------------------------- undoing an event

def _anchor(conn, d: dict) -> dict | None:
    """The day, the people and the records an undo starts from; None when only listed rows were given."""
    out = {"day": None, "actors": set(), "interactions": set(), "events": set(), "lives": set(), "structural": False}
    if d.get("event_id") is not None:
        e = conn.execute("SELECT * FROM events WHERE id=?", (int(d["event_id"]),)).fetchone()
        if not e:
            raise Refused(f"there is no event {d['event_id']}")
        people = ([e["source_actor_id"]] if e["source_actor_id"] else []) + [
            r[0] for r in conn.execute("SELECT actor_id FROM event_targets WHERE event_id=?", (e["id"],))]
        if "death" in e["event_type"]:
            raise Refused(f"event {e['id']} is a death; the dead are not brought back")
        out.update(day=e["day"], actors=set(people), events={e["id"]})
        out["interactions"] = {r[0] for r in conn.execute(
            "SELECT source_id FROM causal_links WHERE source_kind='interaction' AND target_kind='event' AND target_id=?", (e["id"],))}
    elif d.get("life_event_id") is not None:
        e = conn.execute("SELECT * FROM life_events WHERE id=?", (int(d["life_event_id"]),)).fetchone()
        if not e:
            raise Refused(f"there is no life event {d['life_event_id']}")
        if e["event_kind"] == "death":
            raise _revival(conn, e["actor_id"])
        out.update(day=e["day"], actors={a for a in (e["actor_id"], e["related_actor_id"]) if a},
                   structural=e["event_kind"] in STRUCTURAL)
        if not e["summary"].startswith(NEVER):
            out["lives"] = {e["id"]}
        else:
            out["structural"] = False
    elif d.get("interaction_id") is not None:
        i = conn.execute("SELECT * FROM interactions WHERE id=?", (int(d["interaction_id"]),)).fetchone()
        if not i:
            raise Refused(f"there is no interaction {d['interaction_id']}")
        out.update(day=i["resolved_day"] if i["resolved_day"] is not None else i["created_day"],
                   actors={i["proposer_actor_id"], i["recipient_actor_id"]}, interactions={i["id"]})
    elif d.get("actors") or d.get("day") is not None:
        if not d.get("actors") or d.get("day") is None:
            raise Refused("give both actors and day, or an event_id, life_event_id or interaction_id")
        people = d["actors"] if isinstance(d["actors"], list) else [d["actors"]]
        out.update(day=int(d["day"]), actors={actor_ref(conn, v, "actors") for v in people}, structural=True)
        deaths = [r[0] for r in conn.execute(
            f"SELECT actor_id FROM life_events WHERE event_kind='death' AND day=? AND actor_id IN ({_marks(out['actors'])})",
            (out["day"], *out["actors"]))]
        if deaths and str(d.get("kind") or "") == "death":
            raise _revival(conn, deaths[0])
    else:
        return None
    # an exchange that made a union carries the union and its household with it
    for u in conn.execute("SELECT actor_a_id,actor_b_id,metadata_json FROM household_unions WHERE started_day=?", (out["day"],)):
        if json.loads(u["metadata_json"] or "{}").get("accepted_interaction_id") in out["interactions"]:
            out["structural"] = True
            out["actors"] |= {u["actor_a_id"], u["actor_b_id"]}
    return out


def _marks(seq) -> str:
    return ",".join("?" * len(seq)) or "NULL"


def _between(actors: set, a, b) -> bool:
    return a in actors and b in actors


def _undo_structure(conn, log: _Log, a: dict) -> None:
    """Ties and households first made or ended that day among these people are put back as they were."""
    day, actors = a["day"], a["actors"]
    for u in conn.execute("SELECT * FROM household_unions WHERE started_day=? OR ended_day=? ORDER BY id", (day, day)).fetchall():
        if not _between(actors, u["actor_a_id"], u["actor_b_id"]):
            continue
        if u["started_day"] == day:
            made_by = json.loads(u["metadata_json"] or "{}").get("accepted_interaction_id")
            if made_by:
                a["interactions"].add(int(made_by))
            log.delete(conn, "household_unions", {"id": u["id"]})
        else:
            log.update(conn, "household_unions", {"id": u["id"]}, {"status": "active", "ended_day": None})
            for k in conn.execute("SELECT id FROM kinship_links WHERE kin_kind='spouse' AND legal_status='former' AND "
                                  "((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))",
                                  (u["actor_a_id"], u["actor_b_id"], u["actor_b_id"], u["actor_a_id"])).fetchall():
                log.update(conn, "kinship_links", {"id": k["id"]}, {"legal_status": "recognized", "ended_day": None})
    for k in conn.execute("SELECT * FROM kinship_links WHERE started_day=? OR ended_day=? ORDER BY id", (day, day)).fetchall():
        if not _between(actors, k["actor_a_id"], k["actor_b_id"]):
            continue
        if k["started_day"] == day:
            log.delete(conn, "kinship_links", {"id": k["id"]})
        else:
            log.update(conn, "kinship_links", {"id": k["id"]},
                       {"ended_day": None, "legal_status": "recognized" if k["legal_status"] == "former" else k["legal_status"]})
    _undo_households(conn, log, day, actors)


def _undo_households(conn, log: _Log, day: int, actors: set) -> None:
    who = sorted(actors)
    joined = conn.execute(f"SELECT household_id,actor_id FROM household_members WHERE joined_day=? AND actor_id IN ({_marks(who)})",
                          (day, *who)).fetchall()
    left = conn.execute(f"SELECT household_id,actor_id,role FROM household_members WHERE left_day=? AND status IN ('former','absent') "
                        f"AND actor_id IN ({_marks(who)}) ORDER BY household_id", (day, *who)).fetchall()
    made = []
    for hid in sorted({j["household_id"] for j in joined}):
        h = conn.execute("SELECT created_day FROM households WHERE id=?", (hid,)).fetchone()
        others = conn.execute(f"SELECT 1 FROM household_members WHERE household_id=? AND actor_id NOT IN ({_marks(who)})",
                              (hid, *who)).fetchone()
        if h and h[0] == day and not others:
            made.append(hid)
    for j in joined:
        log.delete(conn, "household_members", {"household_id": j["household_id"], "actor_id": j["actor_id"]})
    for hid in made:
        for r in conn.execute("SELECT actor_id FROM actor_life_profiles WHERE current_household_id=?", (hid,)).fetchall():
            log.update(conn, "actor_life_profiles", {"actor_id": r[0]}, {"current_household_id": None})
        log.delete(conn, "household_members", {"household_id": hid})
        log.delete(conn, "households", {"id": hid})
    back: dict[int, int] = {}
    for m in left:
        hid, aid = m["household_id"], m["actor_id"]
        if is_dead(conn, aid):
            continue
        log.update(conn, "household_members", {"household_id": hid, "actor_id": aid}, {"status": "active", "left_day": None})
        back.setdefault(aid, hid)
        h = conn.execute("SELECT head_actor_id,status,updated_day FROM households WHERE id=?", (hid,)).fetchone()
        if m["role"] == "head" and h["head_actor_id"] != aid:  # whoever stood in for the head stands down
            for r in conn.execute("SELECT actor_id FROM household_members WHERE household_id=? AND role='head' AND actor_id<>?",
                                  (hid, aid)).fetchall():
                log.update(conn, "household_members", {"household_id": hid, "actor_id": r[0]}, {"role": "member", "authority": 20})
            log.update(conn, "households", {"id": hid}, {"head_actor_id": aid})
        if h["status"] == "dissolved" and h["updated_day"] == day:
            log.update(conn, "households", {"id": hid}, {"status": "active"})
    for aid in who:
        r = conn.execute("SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
        if r is not None and aid in back and r[0] != back[aid]:
            log.update(conn, "actor_life_profiles", {"actor_id": aid}, {"current_household_id": back[aid]})


def _undo_exchanges(conn, log: _Log, ids: set, events: set) -> None:
    from .relationships import DIRECTIONAL_FIELDS, adjust_relationship
    today = day_of(conn)
    for iid in sorted(ids):
        i = conn.execute("SELECT status,resolution_summary,resolved_day FROM interactions WHERE id=?", (iid,)).fetchone()
        if i is None:
            continue
        if i["status"] != "cancelled":
            log.update(conn, "interactions", {"id": iid}, {"status": "cancelled", "resolution_summary": NEVER + str(i["resolution_summary"] or "")})
        events |= {r[0] for r in conn.execute(
            "SELECT target_id FROM causal_links WHERE source_kind='interaction' AND source_id=? AND target_kind='event'", (iid,))}
        for h in conn.execute("SELECT * FROM relationship_history WHERE source_kind='interaction' AND source_id=? ORDER BY id DESC", (iid,)).fetchall():
            deltas = {k: -float(v) for k, v in json.loads(h["effect_json"] or "{}").items()
                      if v and k.removesuffix("_delta") in DIRECTIONAL_FIELDS}
            pair = {"actor_a_id": h["source_actor_id"], "actor_b_id": h["target_actor_id"]}
            with log.watched(conn, "relationships", pair):
                if deltas:
                    adjust_relationship(conn, h["source_actor_id"], h["target_actor_id"], today, **deltas)
            log.delete(conn, "relationship_history", {"id": h["id"]})
        for g in conn.execute("SELECT id FROM agreements WHERE source_interaction_id=? AND status='active'", (iid,)).fetchall():
            log.update(conn, "agreements", {"id": g[0]}, {"status": "cancelled"})


def _void_events(conn, log: _Log, ids: set) -> None:
    for eid in sorted(ids):
        e = conn.execute("SELECT event_type,title,summary FROM events WHERE id=?", (eid,)).fetchone()
        if e is None or e["title"].startswith(NEVER) or "death" in e["event_type"]:
            continue
        log.update(conn, "events", {"id": eid}, {"title": NEVER + e["title"], "summary": NEVER + e["summary"]})
        log.delete(conn, "knowledge", {"truth_event_id": eid})
        log.delete(conn, "event_information", {"event_id": eid})
        log.update(conn, "rumours", {"truth_event_id": eid}, {"status": "faded"})


def _void_lives(conn, log: _Log, a: dict) -> None:
    ids = set(a["lives"])
    if a["structural"]:
        actors, pair = a["actors"], len(a["actors"]) > 1
        for r in conn.execute("SELECT id,actor_id,related_actor_id FROM life_events WHERE day=? AND event_kind<>'death' AND summary NOT LIKE ?",
                              (a["day"], NEVER + "%")).fetchall():
            one, two = r["actor_id"], r["related_actor_id"]
            if (one in actors and (two is None or two in actors)) if pair else (one in actors or two in actors):
                ids.add(r["id"])
    for lid in sorted(ids):
        r = conn.execute("SELECT event_kind,summary,metadata_json FROM life_events WHERE id=?", (lid,)).fetchone()
        meta = {**json.loads(r["metadata_json"] or "{}"), "voided_kind": r["event_kind"]}
        log.update(conn, "life_events", {"id": lid},
                   {"event_kind": "other", "summary": NEVER + r["summary"], "metadata_json": json.dumps(meta, sort_keys=True)})


def _also(conn, a: dict, touched: set) -> list[dict]:
    """Other records of that day about these people, for the game master to list under `reverse` if they belong to it."""
    day, who = a["day"], sorted(a["actors"])
    if not who:
        return []
    m = _marks(who)
    queries = (
        ("events", f"SELECT id, title AS what FROM events WHERE day=? AND (source_actor_id IN ({m}) OR id IN "
                   f"(SELECT event_id FROM event_targets WHERE actor_id IN ({m})))", (day, *who, *who)),
        ("life_events", f"SELECT id, summary AS what FROM life_events WHERE day=? AND (actor_id IN ({m}) OR related_actor_id IN ({m}))", (day, *who, *who)),
        ("interactions", f"SELECT id, interaction_type||' '||status AS what FROM interactions WHERE (resolved_day=? OR created_day=?) AND "
                         f"(proposer_actor_id IN ({m}) OR recipient_actor_id IN ({m}))", (day, day, *who, *who)),
        ("kinship_links", f"SELECT id, kin_kind||' '||actor_a_id||' of '||actor_b_id AS what FROM kinship_links WHERE (started_day=? OR ended_day=?) AND "
                          f"(actor_a_id IN ({m}) OR actor_b_id IN ({m}))", (day, day, *who, *who)),
        ("enterprise_staff", f"SELECT rowid AS id, role||' at business '||enterprise_id||' ('||actor_id||')' AS what FROM enterprise_staff "
                             f"WHERE joined_day=? AND actor_id IN ({m})", (day, *who)),
        ("held_things", f"SELECT rowid AS id, 'held thing of '||owner_actor_id AS what FROM held_things WHERE created_day=? AND owner_actor_id IN ({m})", (day, *who)),
    )
    out = []
    for table, sql, args in queries:
        for r in conn.execute(sql, args).fetchall():
            if (table, r["id"]) not in touched and not str(r["what"]).startswith(NEVER):
                out.append({"table": table, "id": r["id"], "what": str(r["what"])[:120]})
    return out[:30]


def _listed(conn, log: _Log, rows: list, cause: str | None) -> None:
    """Rows the game master names, for effects that cannot be traced."""
    if not isinstance(rows, list):
        raise Refused("reverse is a list of {table, id or where, action: delete or set, values}")
    people: set[int] = set()
    for item in rows:
        table, action = str(item.get("table") or ""), str(item.get("action") or "")
        cols = [r[1] for r in conn.execute("SELECT * FROM pragma_table_info(?)", (table,))]
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            raise Refused(f"there is no table '{table}'")
        if table in ("world_state", "engine_meta", "corrections") or table.startswith(("connector_", "sqlite_")):
            raise Refused(f"'{table}' is the engine's own record and is not corrected by hand")
        where = item.get("where") if item.get("where") else ({"id": item["id"]} if item.get("id") is not None else None)
        if not isinstance(where, dict) or any(k not in cols and k != "rowid" for k in where):
            raise Refused(f"{table}: say which row, by id or where, using its columns: {', '.join(cols)}")
        if action not in ("delete", "set"):
            raise Refused(f"{table}: action is delete or set")
        values = item.get("values") or {}
        if action == "set" and (not isinstance(values, dict) or not values or any(k not in cols for k in values)):
            raise Refused(f"{table}: values must name its columns: {', '.join(cols)}")
        found = log.rows(conn, table, where)
        if not found:
            raise Refused(f"{table}: no row matches {where}")
        if action == "set" and PAST_DAYS.get(table, set()) & set(values):
            raise Refused(f"{table}: the day a past event happened is not changed")
        if table == "actors" and action == "delete":
            raise Refused("a person is not deleted from the world")
        for r in found:
            ids = {v for k, v in r.items() if v is not None and k.endswith(("actor_id", "actor_a_id", "actor_b_id"))}
            if table == "actors":
                ids.add(r["id"])
            people |= ids
            dead = [i for i in ids if is_dead(conn, i)]
            if table == "life_events" and r.get("event_kind") == "death":
                raise _revival(conn, r["actor_id"])
            if table == "events" and "death" in str(r.get("event_type")):
                raise Refused("that event is a death; the dead are not brought back")
            if dead and action == "delete" and table in ("actor_life_profiles", "background_person_profiles"):
                raise _revival(conn, dead[0])
            if dead and action == "set" and any(str(values.get(k)).lower() in ALIVE for k in ("status", "life_status")):
                raise _revival(conn, dead[0])
        if action == "delete":
            log.delete(conn, table, where)
        else:
            log.update(conn, table, where, {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in values.items()})
    check_canon(conn, people, cause)


def _undo(conn, log: _Log, d: dict) -> list[dict]:
    a = _anchor(conn, d)
    if a is None and not d.get("reverse"):
        raise Refused("say what to undo: an event_id, life_event_id, interaction_id, or actors and day; or list rows under reverse")
    also: list[dict] = []
    if a is not None:
        if a["structural"] and a["actors"]:
            _undo_structure(conn, log, a)
        events = set(a["events"])
        _undo_exchanges(conn, log, a["interactions"], events)
        _void_events(conn, log, events)
        _void_lives(conn, log, a)
        touched = {(c.get("table"), c.get("row")) for c in log.changes}
        also = _also(conn, a, touched)
        if not log.changes and not d.get("reverse"):
            raise Refused("nothing there to reverse; check the day and the people"
                          + (f". Records of that day: {also}" if also else ", or list the rows under reverse"))
        check_canon(conn, a["actors"], d.get("cause"))
    if d.get("reverse"):
        _listed(conn, log, d["reverse"], d.get("cause"))
    return also


# ---------------------------------------------------------------- setting people straight

def _person(conn, log: _Log, d: dict) -> int:
    from . import veto
    from .household_life import _stage_for_age
    from .merchant import add_enterprise_staff
    unknown = sorted(set(d) - set(PERSON_FIELDS))
    if unknown:
        raise Refused(f"cannot set {', '.join(unknown)} this way; person takes {', '.join(PERSON_FIELDS)}")
    aid = actor_ref(conn, d.get("person"))
    if d.get("alive") and is_dead(conn, aid):
        raise _revival(conn, aid)
    given = {k: d[k] for k in PERSON_FIELDS[1:-2] if d.get(k) is not None}
    if not given:
        raise Refused(f"say what to set: {', '.join(PERSON_FIELDS[1:-2])}")
    check_canon(conn, {aid}, d.get("cause"))
    day, who = day_of(conn), _name(conn, aid)
    actor = conn.execute("SELECT * FROM actors WHERE id=?", (aid,)).fetchone()

    def put(field: str, table: str, column: str, new, key: str = "actor_id") -> None:
        r = conn.execute(f"SELECT {column} FROM {table} WHERE {key}=?", (aid,)).fetchone()
        if r is not None:
            conn.execute(f"UPDATE {table} SET {column}=? WHERE {key}=?", (new, aid))
            log.note(field, r[0], new, who=who)

    for field in ("location", "home"):
        if field not in given:
            continue
        place = _find(conn, given[field], field, "locations", ("location", "place"))
        put(field, "actors", "current_location_id" if field == "location" else "home_location_id", place, "id")
        if field == "location" and aid == _me(conn):
            conn.execute("UPDATE player_state SET current_location_id=?,updated_day=? WHERE id=1", (place, day))
    if "age" in given or "birth_day" in given:
        profile = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
        if "birth_day" in given:
            birth = int(given["birth_day"])
        else:
            years = int(given["age"])
            if years < 0:
                raise Refused("an age cannot be less than nothing")
            into = (day - profile[0]) % 365 if profile and profile[0] is not None else 100  # the birthday stays where it was
            birth = day - years * 365 - into
        if birth > day:
            raise Refused("no one is born after today")
        if profile is None:
            conn.execute("INSERT INTO actor_life_profiles(actor_id,life_stage,life_status,last_review_day) VALUES (?,'adult',?,?)",
                         (aid, "deceased" if is_dead(conn, aid) else "living", day))
        put("birth_day", "actor_life_profiles", "birth_day", birth)
        put("life_stage", "actor_life_profiles", "life_stage", _stage_for_age(day - birth))
    if "sex" in given:
        sex = str(given["sex"]).strip().lower()
        if sex not in ("female", "male", "unspecified"):
            raise Refused("sex is female, male or unspecified")
        put("sex", "actor_life_profiles", "demographic_sex", sex)
    work = str(given.get("work") or "").strip()
    role = str(given.get("role") or "").strip()
    if work:
        put("occupation", "background_person_profiles", "occupation_domain", veto.categorise(work))
    if work or role:
        put("work", "actors", "subtype", work or role, "id")
    if "business" in given:
        none = str(given["business"]).strip().lower() in ("none", "no", "")
        eid = None if none else _find(conn, given["business"], "business", "civilian_enterprises", ("business",))
        for s in conn.execute("SELECT enterprise_id,role FROM enterprise_staff WHERE actor_id=? AND status='active' AND role<>'owner'", (aid,)).fetchall():
            if s["enterprise_id"] != eid:
                log.update(conn, "enterprise_staff", {"enterprise_id": s["enterprise_id"], "actor_id": aid}, {"status": "former", "left_day": day})
        if eid is not None:
            with log.watched(conn, "enterprise_staff", {"enterprise_id": eid, "actor_id": aid}):
                add_enterprise_staff(conn, eid, aid, role=role or work or str(actor["subtype"] or "worker"))
                conn.execute("UPDATE enterprise_staff SET left_day=NULL WHERE enterprise_id=? AND actor_id=?", (eid, aid))
    elif role:
        log.update(conn, "enterprise_staff", {"actor_id": aid, "status": "active"}, {"role": role})
    return aid


def _relationship(conn, log: _Log, d: dict) -> list[int]:
    from .relationships import DIRECTIONAL_FIELDS, ensure_relationship
    a, b = actor_ref(conn, d.get("from"), "from"), actor_ref(conn, d.get("to"), "to")
    values = d.get("values") or {}
    if not values or any(k not in DIRECTIONAL_FIELDS for k in values):
        raise Refused(f"values names what to set, from: {', '.join(DIRECTIONAL_FIELDS)}")
    check_canon(conn, {a, b}, d.get("cause"))
    day = day_of(conn)
    for one, two in ((a, b), (b, a)) if d.get("both") else ((a, b),):
        with log.watched(conn, "relationships", {"actor_a_id": one, "actor_b_id": two}):
            ensure_relationship(conn, one, two, day)
            conn.execute(f"UPDATE relationships SET {','.join(f'{k}=?' for k in values)},updated_day=? WHERE actor_a_id=? AND actor_b_id=?",
                         (*[float(v) for v in values.values()], day, one, two))
    return [a, b]


def _pair(a: int, b: int) -> tuple:
    return a, b, b, a


_EITHER = "((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))"


def _kinship(conn, log: _Log, d: dict) -> list[int]:
    a, b = actor_ref(conn, d.get("a"), "a"), actor_ref(conn, d.get("b"), "b")
    change, kind = str(d.get("change") or ""), str(d.get("kind") or "").strip().lower()
    if a == b:
        raise Refused("kinship is between two different people")
    if kind and kind not in RECIPROCAL:
        raise Refused(f"kind is what a is to b, one of: {', '.join(RECIPROCAL)}")
    if change not in ("add", "end", "remove") or (change == "add" and not kind):
        raise Refused("change is add (with kind: what a is to b), end or remove")
    check_canon(conn, {a, b}, d.get("cause"))
    day = day_of(conn)
    links = [k for k in conn.execute(f"SELECT * FROM kinship_links WHERE {_EITHER} ORDER BY id", _pair(a, b)).fetchall()
             if not kind or (k["kin_kind"] == (kind if k["actor_a_id"] == a else RECIPROCAL[kind]))]
    if change == "add":
        if kind == "spouse":
            other = conn.execute(f"SELECT actor_a_id,actor_b_id FROM household_unions WHERE status='active' AND "
                                 f"(actor_a_id IN (?,?) OR actor_b_id IN (?,?)) AND NOT {_EITHER}", (a, b, a, b, *_pair(a, b))).fetchone()
            if other:
                raise Refused(f"{_name(conn, other[0])} and {_name(conn, other[1])} are married: end that marriage first (change: end)")
        for one, two, what in ((a, b, kind), (b, a, RECIPROCAL[kind])):
            if not any(k["actor_a_id"] == one and k["kin_kind"] == what and k["ended_day"] is None for k in links):
                with log.watched(conn, "kinship_links", {"actor_a_id": one, "actor_b_id": two}):
                    conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?,?,'recognized',?)",
                                 (one, two, what, day))
        if kind == "spouse" and not conn.execute(f"SELECT 1 FROM household_unions WHERE status='active' AND {_EITHER}", _pair(a, b)).fetchone():
            with log.watched(conn, "household_unions", {"actor_a_id": a, "actor_b_id": b}):
                conn.execute("INSERT INTO household_unions(actor_a_id,actor_b_id,union_kind,status,started_day) VALUES (?,?,'marriage','active',?)", (a, b, day))
        return [a, b]
    if change == "end":
        links = [k for k in links if k["ended_day"] is None]
    if not links:
        raise Refused(f"there is no {kind or 'kinship'} link between {_name(conn, a)} and {_name(conn, b)}")
    married = any(k["kin_kind"] == "spouse" for k in links)
    for k in links:
        if change == "end":
            log.update(conn, "kinship_links", {"id": k["id"]}, {"ended_day": day, "legal_status": "former"})
        else:
            log.delete(conn, "kinship_links", {"id": k["id"]})
    if married:
        for u in conn.execute(f"SELECT id FROM household_unions WHERE status='active' AND {_EITHER}", _pair(a, b)).fetchall():
            if change == "end":
                log.update(conn, "household_unions", {"id": u[0]}, {"status": "dissolved", "ended_day": day})
            else:
                log.delete(conn, "household_unions", {"id": u[0]})
    return [a, b]


def _household(conn, log: _Log, d: dict) -> int:
    from .household_life import _repair_household_head
    aid = actor_ref(conn, d.get("person"))
    hid = _find(conn, d.get("household"), "household", "households", ("household",))
    change = str(d.get("change") or "")
    if change not in ("join", "leave"):
        raise Refused("change is join or leave")
    if change == "join" and is_dead(conn, aid):
        raise Refused(f"{_name(conn, aid)} is dead and does not move house")
    check_canon(conn, {aid}, d.get("cause"))
    day = day_of(conn)
    mine = [r[0] for r in conn.execute("SELECT household_id FROM household_members WHERE actor_id=? AND status='active'", (aid,))]
    if change == "leave" and hid not in mine:
        raise Refused(f"{_name(conn, aid)} is not in that household")
    leaving = [hid] if change == "leave" else [h for h in mine if h != hid]
    for old in leaving:
        log.update(conn, "household_members", {"household_id": old, "actor_id": aid}, {"status": "former", "left_day": day})
    if change == "join":
        row = conn.execute("SELECT 1 FROM household_members WHERE household_id=? AND actor_id=?", (hid, aid)).fetchone()
        with log.watched(conn, "household_members", {"household_id": hid, "actor_id": aid}):
            if row:
                conn.execute("UPDATE household_members SET status='active',left_day=NULL,role=COALESCE(?,role) WHERE household_id=? AND actor_id=?",
                             (d.get("role"), hid, aid))
            else:
                conn.execute("INSERT INTO household_members(household_id,actor_id,role,joined_day,status) VALUES (?,?,?,?,'active')",
                             (hid, aid, d.get("role") or "member", day))
        log.update(conn, "households", {"id": hid, "status": "dissolved"}, {"status": "active"})
    for h in {*leaving, hid}:
        with log.watched(conn, "households", {"id": h}), log.watched(conn, "household_members", {"household_id": h}):
            _repair_household_head(conn, h, day)
    now = hid if change == "join" else None
    held = conn.execute("SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
    if held is not None and (change == "join" or held[0] == hid):
        log.update(conn, "actor_life_profiles", {"actor_id": aid}, {"current_household_id": now})
    return aid


def _cash(conn, log: _Log, d: dict) -> str:
    from . import money_records
    holder = str(d.get("holder") or "").strip()
    if d.get("amount") is None:
        raise Refused("amount is required, as a figure")
    if holder.partition(":")[0].lower() in ("person", "actor") or ":" not in holder:
        aid = actor_ref(conn, holder or None, "holder")
        check_canon(conn, {aid}, d.get("cause"))
        ref, who = f"person:{aid}", _name(conn, aid)
    else:
        ref, who = holder, holder
    old = money_records.cash(conn, ref)
    new = money_records.set_cash(conn, ref, float(d["amount"]))
    log.note("cash", old, new, who=who)
    return ref


# ---------------------------------------------------------------- the two ways in

def preview(conn: sqlite3.Connection, details: dict) -> dict:
    """What an undo would take back; nothing is changed."""
    log = _Log()
    conn.execute("SAVEPOINT correction_preview")
    try:
        also = _undo(conn, log, dict(details))
    finally:
        conn.execute("ROLLBACK TO correction_preview")
        conn.execute("RELEASE correction_preview")
    return {"status": "preview", "would_reverse": [describe(c) for c in log.changes], "also_that_day": also}


def apply(conn: sqlite3.Connection, op: str, player_said: str, details: dict, call_id: str) -> dict:
    words = str(player_said or "").strip()
    if not words:
        raise Refused("player_said is required: quote the words in which the player approved this correction")
    if op not in OPS:
        raise Refused(f"op is one of: preview, {', '.join(OPS)}")
    log, d = _Log(), dict(details)
    also: list[dict] = []
    if op == "undo_event":
        also = _undo(conn, log, d)
    else:
        {"person": _person, "relationship": _relationship, "kinship": _kinship, "household": _household, "cash": _cash}[op](conn, log, d)
    if not log.changes:
        raise Refused("nothing to change: the record already says that")
    people = []
    for key in ("person", "from", "to", "a", "b", "holder", "actors"):
        for v in d[key] if isinstance(d.get(key), list) else [d.get(key)]:
            if v is not None:
                try:
                    people.append(_name(conn, actor_ref(conn, v)))
                except Refused:
                    people.append(str(v))
    target = ", ".join(people) or ", ".join(f"{k} {d[k]}" for k in ("event_id", "life_event_id", "interaction_id") if d.get(k) is not None) or "listed rows"
    if op == "undo_event" and d.get("day") is not None:
        target += f" (day {d['day']})"
    conn.execute("INSERT INTO corrections(day,op,target,changes_json,player_said,cause,call_id) VALUES (?,?,?,?,?,?,?)",
                 (day_of(conn), op, target, json.dumps(log.changes, ensure_ascii=False, default=str), words, d.get("cause"), call_id))
    out = {"status": "corrected", "summary": f"corrected ({op}): {target}",
           ("reversed" if op == "undo_event" else "changed"): [describe(c) for c in log.changes]}
    if also:
        out["also_that_day"] = also
    return out


def recent(conn: sqlite3.Connection, limit: int = 5) -> list[dict]:
    """The latest corrections, oldest first."""
    got = conn.execute("SELECT * FROM corrections ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in reversed(got):
        changes = json.loads(r["changes_json"])
        row = {"day": r["day"], "op": r["op"], "about": r["target"], "player_said": r["player_said"],
               "changes": [describe(c) for c in changes[:6]]}
        if len(changes) > 6:
            row["changes_more"] = len(changes) - 6
        out.append(row)
    return out
