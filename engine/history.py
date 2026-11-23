"""Real history on the intake: documented real facts, judged against the run, with the run's departures tracked.

A real fact is proposed through the intake (shape `history`: a class, a real date, a source, the causes it needed). The
engine resolves each cause against the run and against the divergence ledger and decides: on time, earlier, later, changed
or not at all. History holds unless the run touches it, directly (a divergence shares an entity with the fact) or through a
chain of named causes; chance never moves a fact on its own. The outcome is recorded as a history entry plus a Fixed
world fact, with the reasons, so a later change needs a stated cause. No world words here: classes, delays and field
synonyms come from the package's history data.
"""
from __future__ import annotations

import json
import random
import re
import sqlite3
from calendar import monthrange
from datetime import date, timedelta
from typing import Any

from . import facts
from .authoring import AuthoringRefused

_STOP = frozenset("a an the of for in on at to by with and or from is are was were its his her their company firm corporation "
                  "business new first group inc founded founder opens opened maker makes".split())


# ---- data and dates -----------------------------------------------------------------------------------------------

def rules(conn) -> dict:
    from .world_package import history_rules, package_for
    try:
        return history_rules(package_for(conn))
    except Exception:
        return {}


def _start(conn) -> date | None:
    from .world_package import package_for
    try:
        pkg = package_for(conn)
        return date.fromisoformat(pkg.calendar["start"]) if pkg.calendar.get("kind") == "gregorian" else None
    except Exception:
        return None


def _today_day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def today_iso(conn) -> str | None:
    s = _start(conn)
    return (s + timedelta(days=_today_day(conn))).isoformat() if s else None


def day_of(conn, iso: str) -> int | None:
    s = _start(conn)
    return (date.fromisoformat(iso[:10]) - s).days if s else None


def full_date(text: str, precision: str | None = None) -> tuple[str, str]:
    """An ISO date as precise as given: a year or a month is read as its last day, so a fact is never applied early."""
    t = str(text or "").strip()
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", t)
    if not m:
        raise AuthoringRefused(f"real_date {t!r} is not an ISO date (YYYY, YYYY-MM or YYYY-MM-DD)", "input_gap")
    y, mo, d = int(m.group(1)), m.group(2), m.group(3)
    prec = "day" if d else "month" if mo else "year"
    if precision in ("day", "month", "year"):
        prec = precision if (precision == prec or prec == "day") else prec
    mo_i = int(mo) if mo else 12
    d_i = int(d) if d else monthrange(y, mo_i)[1]
    return date(y, mo_i, d_i).isoformat(), prec


def slug(what: str) -> str:
    return facts._slug(what)


def is_major(conn, klass: str) -> bool:
    return str(klass or "").lower() in {str(c).lower() for c in rules(conn).get("major_classes", [])}


def _tokens(text: str, conn=None) -> set[str]:
    toks = {w for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(w) >= 4 and w not in _STOP}
    toks |= {w[:-1] for w in toks if w.endswith("s") and len(w) > 4}  # computers = computer
    groups = (rules(conn).get("field_words") or {}) if conn is not None else {}
    for head, syns in groups.items():
        words = {head, *syns}
        low = " ".join(sorted(words)).lower()
        if any(t in low for t in toks) or any(w in str(text).lower() for w in words):
            for w in words:
                toks |= {x for x in re.findall(r"[a-z0-9]+", w.lower()) if len(x) >= 4 and x not in _STOP}
    return toks


# ---- needs --------------------------------------------------------------------------------------------------------

def _need(raw: Any) -> dict:
    if isinstance(raw, str):
        raw = {"text": raw}
    n = dict(raw) if isinstance(raw, dict) else {"text": str(raw)}
    n["text"] = str(n.get("text") or n.get("ref") or "").strip()
    n["ref"] = str(n["ref"]).strip() if n.get("ref") else None
    n["central"] = bool(n.get("central", True))
    ref_kind = (n["ref"] or "").split(":", 1)[0]
    n["substitute"] = bool(n["substitute"]) if "substitute" in n else ref_kind != "actor"
    return n


_DEAD = ("deceased", "dead", "dissolved", "defunct", "absorbed", "destroyed", "ended")


def _entry(conn, key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM history_entries WHERE key=?", (key,)).fetchone()


def _name(conn, aid: int) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (aid,)).fetchone()
    return str(r[0]) if r else f"actor {aid}"


def _divergences_on(conn, ref: str, day: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM divergences WHERE subject=? AND day<=? ORDER BY id", (ref, day)).fetchall()


def resolve_need(conn, need: dict, day: int, visited: frozenset = frozenset()) -> dict:
    """One cause against the run: state holds | bent | broken | unknown, why, the links that led there, an inherited delay
    in days, and the run date of an enabler that arrived earlier than its own real date."""
    n = _need(need)
    ref = n["ref"]
    out = {"state": "unknown", "why": n["text"], "links": [], "delay": 0, "enabler_run": None, "need": n}
    if not ref or ":" not in ref:
        return out
    kind, ident = ref.split(":", 1)
    if kind == "actor" and ident.isdigit():
        aid = int(ident)
        row = conn.execute("SELECT status FROM actors WHERE id=?", (aid,)).fetchone()
        prof = conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
        if row is None:
            return out
        if str(row[0]) in _DEAD or (prof and str(prof[0]) != "living"):
            out.update(state="broken", why=f"{_name(conn, aid)} is dead in this run", links=[f"{_name(conn, aid)} is dead"])
            return out
        out["state"] = "holds"
    elif kind in ("org", "place") and ident.isdigit():
        row = conn.execute("SELECT status FROM actors WHERE id=?", (int(ident),)).fetchone() if kind == "org" else None
        if row is not None:
            if str(row[0]) in _DEAD:
                out.update(state="broken", why=f"{_name(conn, int(ident))} no longer exists in this run",
                           links=[f"{_name(conn, int(ident))} is gone"])
                return out
            out["state"] = "holds"
    elif kind in ("history", "law", "office"):
        key = ident if ident.startswith("history:") else f"history:{ident}"
        e = _entry(conn, key)
        if e is None:
            return out
        if key in visited:
            out["state"] = "holds"
            return out
        title = e["what"]
        if e["status"] == "never" or e["outcome"] == "never":
            out.update(state="broken", why=f"{title} did not happen in this run", links=[f"{title} did not happen"])
            return out
        out["state"] = "holds"
        if e["outcome"] in ("later", "changed") or (e["run_date"] and e["run_date"] > e["real_date"]):
            late = (date.fromisoformat(e["run_date"]) - date.fromisoformat(e["real_date"])).days if e["run_date"] else 0
            out.update(state="bent", delay=max(late, 0), why=f"{title} came {e['outcome']} in this run",
                       links=[f"{title} came {e['outcome']}" + (f" ({'; '.join(json.loads(e['reasons_json']))})" if e["reasons_json"] != "[]" else "")])
        elif e["outcome"] == "earlier" and e["run_date"]:
            out["enabler_run"] = e["run_date"]
        for sub in json.loads(e["needs_json"] or "[]"):  # the chain: what this cause itself needed
            r = resolve_need(conn, sub, day, visited | {key})
            if r["state"] in ("broken", "bent") and out["state"] == "holds":
                out.update(state="bent", why=f"{title} rested on {r['why']}", links=[f"{title} rested on {r['why']}", *r["links"]],
                           delay=max(out["delay"], r["delay"]))
    elif kind == "tech":
        t = conn.execute("SELECT * FROM tech_level WHERE lower(thing)=lower(?) ORDER BY id DESC LIMIT 1", (ident,)).fetchone()
        if t is None:
            return out
        out["state"] = "holds"
        real = n.get("real_date")
        if t["available_date"] and real and t["available_date"] < str(real)[:10]:
            out["enabler_run"] = t["available_date"]
    if out["state"] in ("holds", "unknown"):  # a divergence that touches a cause that still stands bends it
        hits = _divergences_on(conn, ref, day)
        if hits:
            out.update(state="bent", why=f"{n['text'] or ref} was touched in this run: {hits[-1]['text'] or hits[-1]['cause']}",
                       links=[f"{h['text'] or h['cause']} ({h['cause']})" for h in hits])
    return out


def _niche(conn, entry: dict, day: int) -> list[sqlite3.Row]:
    """Divergences in the same field as the fact (the run got there first): word overlap with what it is about."""
    mine = _tokens(entry["what"] + " " + " ".join(str(a) for a in entry.get("about", [])), conn)
    if not mine:
        return []
    hit = []
    for d in conn.execute("SELECT * FROM divergences WHERE day<=? AND field_words!='' ORDER BY id", (day,)):
        if d["subject"].startswith("history:") or d["subject"].startswith("thing:"):
            continue
        if mine & _tokens(d["field_words"], conn):
            hit.append(d)
    for t in conn.execute("SELECT id,name,kind_text,call_id FROM held_things WHERE status!='ended' AND shape!='history' AND created_day<=?", (day,)):
        if mine & _tokens(f"{t['name']} {t['kind_text']}", conn):  # a venture the run founded in the same field: recorded now, once
            subject = f"thing:{t['id']}"
            row = conn.execute("SELECT * FROM divergences WHERE subject=? AND entry_key=?", (subject, entry["key"])).fetchone()
            if row is None:
                did = record_divergence(conn, subject, f"{t['name']} {t['kind_text']}", f"held thing {t['id']}",
                                        f"{t['name']} already holds this field", entry["key"])
                row = conn.execute("SELECT * FROM divergences WHERE id=?", (did,)).fetchone()
            hit.append(row)
    return hit


def _draw(conn, key: str, weight: str, tag: str) -> int:
    f = (rules(conn).get("delay_days") or {}).get(weight) or {"min": 60, "max": 365}
    rng = random.Random(f"{_seed(conn)}:history:{key}:{tag}")
    return int(round(rng.uniform(float(f["min"]), float(f["max"]))))


def _seed(conn) -> int:
    from . import design
    return design.run_seed(conn)


def judge(conn, entry: dict, day: int) -> dict:
    """The outcome for one fact on `day`: {"outcome", "run_date", "reasons", "links"}. `entry` carries key, what, real_date
    (ISO), needs and about. History holds by default: with no broken or bent cause and no divergence it is on time."""
    real = date.fromisoformat(entry["real_date"])
    states = [resolve_need(conn, n, day) for n in entry.get("needs", [])]
    reasons: list[str] = []
    links: list[str] = []
    broken = [s for s in states if s["state"] == "broken"]
    bent = [s for s in states if s["state"] == "bent"]
    central_broken = [(s, s["need"]) for s in broken if s["need"]["central"]]
    for d in _niche(conn, entry, day):
        sub = {"text": f"the field was taken in this run ({d['text'] or d['field_words']})", "central": True, "substitute": True}
        central_broken.append(({"why": sub["text"], "links": [f"{d['text'] or d['field_words']} ({d['cause']})"], "delay": 0}, sub))
    for s in bent:
        reasons.append(s["why"])
        links += s["links"]
    for s, _n in central_broken:
        reasons.append(s["why"])
        links += s["links"]
    for s in broken:
        if s["need"]["central"]:
            continue
        reasons.append(s["why"])  # a supporting cause is gone: later, not changed
        links += s["links"]
        bent.append({**s, "need": {**s["need"], "central": False}, "delay": 0})
    if central_broken:
        if all(n["substitute"] for _s, n in central_broken):
            delay = _draw(conn, entry["key"], "supporting", "changed")
            return {"outcome": "changed", "run_date": (real + timedelta(days=delay)).isoformat(),
                    "reasons": reasons or ["a cause it needed is gone"], "links": links}
        return {"outcome": "never", "run_date": None, "reasons": reasons or ["a cause it needed is gone and nothing could stand in"],
                "links": links}
    if bent:
        delay = max(max(int(s.get("delay") or 0) for s in bent),
                    max(_draw(conn, entry["key"], "central" if s["need"]["central"] else "supporting", f"later:{i}") for i, s in enumerate(bent)))
        return {"outcome": "later", "run_date": (real + timedelta(days=delay)).isoformat(), "reasons": reasons, "links": links}
    early = [s for s in states if s.get("enabler_run")]
    if early:
        lead = int(((rules(conn).get("lead_days") or {}).get("default")) or 0)
        n0 = early[0]["need"]
        lead = int(n0.get("lead_days") or lead)
        run = min(date.fromisoformat(s["enabler_run"]) for s in early) + timedelta(days=lead)
        if run < real:
            return {"outcome": "earlier", "run_date": run.isoformat(),
                    "reasons": [f"{s['why']} arrived earlier in this run" for s in early], "links": [l for s in early for l in s["links"]]}
    return {"outcome": "on_time", "run_date": real.isoformat(), "reasons": [], "links": []}


# ---- the ledger ---------------------------------------------------------------------------------------------------

def record_divergence(conn, subject: str, field_words: str, cause: str, text: str, entry_key: str | None = None) -> int:
    return int(conn.execute("INSERT INTO divergences(subject,field_words,day,cause,text,entry_key) VALUES (?,?,?,?,?,?)",
                            (str(subject), str(field_words or "")[:200], _today_day(conn), str(cause or "")[:200], str(text or "")[:300],
                             entry_key)).lastrowid)


# ---- proposing a real fact ----------------------------------------------------------------------------------------

def recorded(conn, details: dict) -> dict | None:
    """The recorded outcome of a fact already proposed (so a `never` is not re-proposed every session); None for a new one."""
    what = " ".join(str(details.get("what") or details.get("name") or "").split())
    if not what or not details.get("real_date"):
        return None
    e = _entry(conn, "history:" + slug(what))
    return None if e is None else _view(e) | {"status": "created", "kind": "history", "replayed": True}


def _view(e: sqlite3.Row) -> dict:
    return {"entry": e["key"], "name": e["what"], "outcome": e["outcome"], "run_date": e["run_date"], "real_date": e["real_date"],
            "reasons": json.loads(e["reasons_json"] or "[]"), "provisional": bool(e["provisional"]), "foreseen": e["status"] == "foreseen",
            "entry_status": e["status"]}


def propose(conn, me: int, p, call_id: str) -> dict:
    """The `history` shape's maker (called by the intake with a normalised Proposal)."""
    d = p.details
    klass = str(d.get("class") or d.get("kind") or "").strip().lower()
    if not klass:
        raise AuthoringRefused("a real fact needs its class (technology, firm, firm_event, person_event, law, office, price, culture or event)", "input_gap")
    if not d.get("real_date"):
        raise AuthoringRefused("a real fact needs real_date (ISO, as precise as known)", "input_gap")
    src = str(d.get("source") or "").strip()
    if not src:
        raise AuthoringRefused("a real fact needs its source: a URL and a short quote, or \"memory\" (marked to verify)", "input_gap")
    real, prec = full_date(str(d["real_date"]), d.get("precision"))
    key = "history:" + slug(p.what)
    existing = _entry(conn, key)
    if existing is not None:
        return {**_view(existing), "backing_table": "history_entries", "backing_id": int(existing["id"]), "replayed": True}
    needs = [_need(n) for n in (d.get("needs") or [])]
    about = [str(a) for a in (d.get("about") or [])]
    day = _today_day(conn)
    today = today_iso(conn)
    memory = src.lower() == "memory"
    provisional = memory and is_major(conn, klass)
    foreseen_ahead = today is not None and real > today
    entry = {"key": key, "what": p.what, "real_date": real, "needs": needs, "about": about}
    if foreseen_ahead:
        verdict = {"outcome": "default", "run_date": real, "reasons": [], "links": []}
        status = "foreseen"
    else:
        verdict = judge(conn, entry, day)
        status = "never" if verdict["outcome"] == "never" else (
            "in_force" if today is None or (verdict["run_date"] and verdict["run_date"] <= today) else "foreseen")
    cur = conn.execute(
        """INSERT INTO history_entries(key,class,what,real_date,precision,run_date,outcome,reasons_json,needs_json,source,verify,provisional,
             effects_json,status,about_json,proposed_day,judged_day,call_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (key, klass, p.what, real, prec, verdict["run_date"], verdict["outcome"], json.dumps(verdict["reasons"]), json.dumps(needs), src[:400],
         "to verify" if memory else "verified", 1 if provisional else 0, json.dumps(d.get("effects") or []), status, json.dumps(about), day,
         None if foreseen_ahead else day, str(call_id)))
    eid = int(cur.lastrowid)
    facts.ensure(conn)
    facts._put(conn, key, p.what, f"{p.what} ({klass}; real {real}" + (f", here {verdict['run_date']}" if verdict["run_date"] and verdict["run_date"] != real else "")
               + (", did not happen here" if verdict["outcome"] == "never" else "") + ")", "Fixed",
               start=verdict["run_date"] if status == "in_force" else None, source=src[:200])
    if verdict["outcome"] not in ("on_time", "default"):
        record_divergence(conn, key, p.what, f"history proposal {call_id}", f"{p.what} came {verdict['outcome']}: " + "; ".join(verdict["reasons"]), key)
    out = _view(_entry(conn, key))
    out.update({"backing_table": "history_entries", "backing_id": eid, "links": verdict["links"]})
    return out


# ---- what the run does to real history ----------------------------------------------------------------------------

def note_actor_death(conn, actor_id: int, day: int, cause: str) -> None:
    """A death in the run is a divergence when the dead man is a documented real figure or a named cause of a fact. Mortality
    decides it; the real date is calibration, never a schedule."""
    aid = int(actor_id)
    try:
        fig = conn.execute("SELECT name FROM real_figures WHERE actor_id=?", (aid,)).fetchone()
        named = conn.execute("SELECT key FROM history_entries WHERE needs_json LIKE ? OR about_json LIKE ? LIMIT 1",
                             (f'%"actor:{aid}"%', f'%"actor:{aid}"%')).fetchone()
    except sqlite3.OperationalError:  # a bare database without the history tables
        return
    if fig is None and named is None:
        return
    who = fig["name"] if fig else _name(conn, aid)
    record_divergence(conn, f"actor:{aid}", who, str(cause or "death in the run"), f"{who} died in this run")


def note_override(conn, key: str, new_text: str, cause: str | None) -> dict | None:
    """A change to a Fixed history fact. A source in the cause verifies a provisional entry; any other cause is the run changing
    history: the divergence is recorded with that cause and the entry marked superseded."""
    if not str(key).startswith("history:"):
        return None
    e = _entry(conn, key)
    if e is None:
        return None
    c = " ".join(str(cause or "").split())
    if re.search(r"https?://|^source", c, re.I) and e["provisional"]:
        conn.execute("UPDATE history_entries SET provisional=0,verify='verified',source=? WHERE key=?", (c[:400], key))
        return {"verified": True, "entry": key}
    record_divergence(conn, key, e["what"], c[:200], f"{e['what']}: {new_text}"[:300], key)
    conn.execute("UPDATE history_entries SET status='superseded' WHERE key=?", (key,))
    return {"diverged": True, "entry": key}


# ---- the package timeline as defaults -----------------------------------------------------------------------------

def soft_classes(conn) -> tuple[str, ...]:
    return tuple(rules(conn).get("soft_classes") or ("technology", "culture"))


def _timeline_keys(e: dict) -> list[str]:
    return ["history:" + slug(x) for x in [e["name"], *(e.get("aliases") or [])]]


def run_entry(conn, e: dict) -> sqlite3.Row | None:
    """The run's own entry for a timeline item, if play ever proposed it."""
    for k in _timeline_keys(e):
        r = _entry(conn, k)
        if r is not None:
            return r
    return None


def run_status(conn, e: dict, day_iso: str) -> dict:
    """Where a timeline item stands in this run on `day_iso`: not_yet | exists | never, with the run's date. The package's real
    date is the default; a history entry (earlier, later, changed, never) is the run's own answer."""
    r = run_entry(conn, e)
    if r is None:
        exists = str(e.get("exists") or "")
        return {"status": "exists" if exists and day_iso >= exists else "not_yet", "run_exists": exists or None, "reason": None, "entry": None}
    reasons = "; ".join(json.loads(r["reasons_json"] or "[]"))
    if r["status"] == "never" or r["outcome"] == "never":
        return {"status": "never", "run_exists": None, "reason": reasons or "the causes it needed did not hold", "entry": r["key"]}
    run = r["run_date"] or r["real_date"]
    return {"status": "exists" if day_iso >= run else "not_yet", "run_exists": run, "reason": reasons or None, "entry": r["key"]}


# ---- technology and the enabler check (5.10), foresight (5.11b) ---------------------------------------------------

def add_tech(conn, thing: str, exists: str, available: str | None = None, common: str | None = None, price_band: str | None = None,
             source_key: str | None = None, inventor: int | None = None) -> int:
    return int(conn.execute("INSERT INTO tech_level(thing,exists_date,available_date,common_date,price_band,source_key,inventor_actor_id) VALUES (?,?,?,?,?,?,?)",
                            (thing, exists, available or exists, common, price_band, source_key, inventor)).lastrowid)


def enabler_state(conn, text: str, day_iso: str) -> dict | None:
    """Whether a named enabler exists in this run on `day_iso`: tech_level first, then the package timeline and history entries.
    None when nothing here knows the name: history holds by default, so an unknown enabler is not a contradiction."""
    low = str(text or "").lower()
    for t in conn.execute("SELECT * FROM tech_level ORDER BY id DESC"):
        if str(t["thing"]).lower() in low or low in str(t["thing"]).lower():
            when = t["available_date"] or t["exists_date"]
            return {"name": t["thing"], "exists": bool(when) and day_iso >= when, "run_exists": when}
    from .world_package import package_for, timeline_mentions
    try:
        for e, _p in timeline_mentions(package_for(conn), str(text)):
            st = run_status(conn, e, day_iso)
            return {"name": e["name"], "exists": st["status"] == "exists", "run_exists": st["run_exists"], "never": st["status"] == "never"}
    except Exception:
        pass
    r = _entry(conn, "history:" + slug(text))
    if r is not None:
        run = r["run_date"] or r["real_date"]
        return {"name": r["what"], "exists": r["status"] == "in_force" and day_iso >= run, "run_exists": run, "never": r["status"] == "never"}
    return None


def screen(conn, p):
    """The intake's history checks on a proposal that is not itself a real fact: enablers (a missing one is a named
    contradiction), the distance ahead of the run's technology (cost, time and failure odds scale; no ceiling), and foresight (a
    bet on a foreseen real fact is judged on what the man could know). Returns (proposal, basis)."""
    from dataclasses import replace
    today = today_iso(conn)
    basis: dict = {}
    if today is None or not rules(conn):
        return p, basis
    text = f"{p.what} {p.kind_text} {p.agenda}"
    for need in p.details.get("needs_tech") or []:
        st = enabler_state(conn, str(need), today)
        builds = " ".join(str(b).lower() for b in (p.details.get("builds") or [])) + " " + text.lower()
        if st and not st["exists"] and str(need).lower() not in builds:
            when = f"it arrives {st['run_exists']}" if st.get("run_exists") and not st.get("never") else "it never came"
            raise AuthoringRefused(f"{p.what} needs {need}, which does not exist on {today} in this run ({when}); "
                                   "someone would have to build that first, and he may set out to", "contradiction")
    from .world_package import package_for, timeline_mentions
    ahead = []
    try:
        for e, _p in timeline_mentions(package_for(conn), text):
            if e.get("class") in soft_classes(conn):
                st = run_status(conn, e, today)
                if st["status"] == "not_yet" and st.get("run_exists"):
                    ahead.append((e["name"], (date.fromisoformat(st["run_exists"]) - date.fromisoformat(today)).days))
    except Exception:
        pass
    if ahead:
        fig = rules(conn).get("distance") or {}
        years = max(d for _n, d in ahead) / 365.0
        factor = 1.0 + float(fig.get("cost_per_year", 0.5)) * years
        odds = 1.0 - (1.0 - float(fig.get("failure_per_year", 0.15))) ** years
        days = int(round(years * float(fig.get("time_per_year_days", 120))))
        basis["tech_distance"] = {"items": [n for n, _d in ahead], "years_ahead": round(years, 2), "cost_factor": round(factor, 2),
                                  "failure_odds": round(odds, 3), "extra_days": days}
        p = replace(p, start_cost=p.start_cost * factor, ready_in_days=((p.ready_in_days or 0) + days) or None)
    named = foreseen_named(conn, text + " " + " ".join(str(a) for a in (p.details.get("about") or [])))
    if named:
        from . import foreknowledge
        k = foreknowledge.character_knows(conn, p.owner, " ".join(r["what"] for r in named), _today_day(conn))
        judged = "informed" if k["level"] == "informed" else "long_shot"
        basis["foresight"] = {"entries": [r["key"] for r in named], "knows": k["level"], "sources": k["sources"], "judged_as": judged}
        if judged == "long_shot" and p.income_weekly:
            p = replace(p, income_weekly=0.0)  # judged on what the character could know, never on what the player does
            basis["foresight"]["income_not_credited"] = "no income is credited for a bet on the future that he had no way to know"
    return p, basis


def foreseen_named(conn, text: str) -> list[sqlite3.Row]:
    low = " ".join(re.findall(r"[a-z0-9]+", str(text).lower()))
    out = []
    for r in conn.execute("SELECT * FROM history_entries WHERE status='foreseen'"):
        nm = " ".join(re.findall(r"[a-z0-9]+", r["what"].lower()))
        if nm and (nm in low or r["key"] in str(text)):
            out.append(r)
    return out


# ---- settling: effects at the run date, foreseen facts re-judged, what is due ----------------------------------------

def next_due(conn) -> bool:
    """True when some fact is waiting for its date (the weekly held tick then runs)."""
    return conn.execute("SELECT 1 FROM history_entries WHERE status='foreseen' LIMIT 1").fetchone() is not None


def apply_effects(conn, e: sqlite3.Row, day: int) -> list[str]:
    """The accepted fact's effects, by class, into the systems that exist. A class with no reader yet leaves a gap row."""
    done: list[str] = []
    run = e["run_date"] or e["real_date"]
    klass = str(e["class"])
    effects = json.loads(e["effects_json"] or "[]")
    if klass == "technology":
        ex = next((x for x in effects if isinstance(x, dict) and x.get("kind") == "technology"), {})
        add_tech(conn, e["what"], run, ex.get("available") or run, ex.get("common"), ex.get("price_band"), e["key"], ex.get("inventor"))
        done.append(f"{e['what']} now exists")
    for x in effects:
        if isinstance(x, dict) and x.get("kind") == "holder" and x.get("office_key") and x.get("actor_id") is not None:
            try:
                facts.fill_open(conn, str(x["office_key"]), int(x["actor_id"]), e["key"])
                done.append(f"{_name(conn, int(x['actor_id']))} took {x['office_key']}")
            except facts.FactRefused as ex_:  # the run already put someone else there: the clash is the history of this run
                record_divergence(conn, e["key"], e["what"], e["key"], f"the office went another way: {ex_}", e["key"])
    if klass in ("culture", "event"):
        from . import authoring
        from .player import get_player
        pl = get_player(conn)
        if pl:
            try:
                authoring._rumour(conn, int(pl["player_actor_id"]), {"text": f"{e['what']}"[:300]}, f"history-effect:{e['key']}")
                done.append("it is being talked about")
            except Exception:  # no place to start it from: it stays a recorded fact
                pass
    if klass in ("firm", "firm_event", "price"):
        from . import intake
        held = conn.execute("SELECT id FROM held_things WHERE backing_table='history_entries' AND backing_id=?", (e["id"],)).fetchone()
        if held is not None:
            intake.bump_gap(conn, f"history:{klass}", "history", int(held["id"]), [f"a reader for {klass} effects"])
    return done


def settle_due(conn, day: int, *, event_logger=None) -> dict:
    """Foreseen facts whose date has arrived are judged now, because the run may have changed since the GM foresaw them. On time,
    earlier, later, changed or not at all; effects apply when the fact is in force; a fact pushed to a later date waits."""
    out = {"judged": 0, "in_force": 0, "later": 0, "never": 0}
    today = today_iso(conn)
    if today is None:
        return out
    for e in conn.execute("SELECT * FROM history_entries WHERE status='foreseen' AND COALESCE(run_date,real_date)<=? ORDER BY real_date,id", (today,)).fetchall():
        entry = {"key": e["key"], "what": e["what"], "real_date": e["real_date"], "needs": json.loads(e["needs_json"] or "[]"),
                 "about": json.loads(e["about_json"] or "[]")}
        v = judge(conn, entry, int(day))
        status = "never" if v["outcome"] == "never" else ("in_force" if v["run_date"] <= today else "foreseen")
        conn.execute("UPDATE history_entries SET outcome=?,run_date=?,reasons_json=?,status=?,judged_day=? WHERE id=?",
                     (v["outcome"], v["run_date"], json.dumps(v["reasons"]), status, int(day), e["id"]))
        out["judged"] += 1
        if v["outcome"] not in ("on_time", "default") and e["outcome"] != v["outcome"]:
            record_divergence(conn, e["key"], e["what"], f"judged on its date, day {day}", f"{e['what']} came {v['outcome']}: " + "; ".join(v["reasons"]), e["key"])
        if status == "in_force":
            conn.execute("UPDATE world_facts SET start_date=? WHERE key=?", (v["run_date"], e["key"]))
            apply_effects(conn, conn.execute("SELECT * FROM history_entries WHERE id=?", (e["id"],)).fetchone(), int(day))
            out["in_force"] += 1
        elif status == "never":
            out["never"] += 1
        else:
            out["later"] += 1
    return out


def due_prompt(conn, from_day: int, to_day: int) -> list[dict]:
    """What the real world had coming between two days, for the GM to look up: package-timeline defaults and foreseen facts dated in
    the interval, of the classes the package asks about, not yet entered. A prompt, never a list the engine acts on."""
    a, b = today_iso_at(conn, from_day), today_iso_at(conn, to_day)
    if a is None or not rules(conn):
        return []
    classes = set(rules(conn).get("advance_prompt_classes") or [])
    out = []
    from .world_package import package_for
    try:
        from .world_package import _entries
        entries = _entries(package_for(conn))
    except Exception:
        entries = []
    for e in entries:
        if a < str(e.get("exists") or "") <= b and e.get("class") in classes and run_entry(conn, e) is None:
            out.append({"name": e["name"], "class": e.get("class"), "real_date": e["exists"],
                        "hint": "look up what really happened; propose it with its source through author if his sphere touches it"})
    for r in conn.execute("SELECT * FROM history_entries WHERE status='foreseen' AND real_date>? AND real_date<=?", (a, b)):
        out.append({"name": r["what"], "class": r["class"], "real_date": r["real_date"], "hint": "foreseen; judged now against what the run has done"})
    return out


def today_iso_at(conn, day: int) -> str | None:
    s = _start(conn)
    return (s + timedelta(days=int(day))).isoformat() if s else None


def view_entries(conn, limit: int = 40) -> list[dict]:
    """The GM's list: recorded facts, provisional ones first."""
    rows = conn.execute("SELECT * FROM history_entries ORDER BY provisional DESC, real_date, id LIMIT ?", (int(limit),)).fetchall()
    return [{"key": r["key"], "what": r["what"], "class": r["class"], "real_date": r["real_date"], "run_date": r["run_date"], "outcome": r["outcome"],
             "status": r["status"], "provisional": bool(r["provisional"]), "reasons": json.loads(r["reasons_json"] or "[]")} for r in rows]


def view_divergences(conn, limit: int = 40) -> list[dict]:
    return [{"subject": r["subject"], "day": r["day"], "cause": r["cause"], "text": r["text"], "entry": r["entry_key"]}
            for r in conn.execute("SELECT * FROM divergences ORDER BY id DESC LIMIT ?", (int(limit),))]
