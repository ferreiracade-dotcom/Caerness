"""Bearing, the room read and what a man reads in others (information phase 1a, spec 7.2).

Everything here takes an observer and a subject; nothing is special to the protagonist (he is simply the observer or the
subject of the scene). The package's data (`presence`) supplies the forms of deference, who attends whom, and the words;
every number is a design figure. Nothing returns a score.

- bearing: retinue (recorded once, so the crew persists), signals (what he owns, what was proposed and recorded), spending.
- room_read: an observer's stance toward a subject, where it comes from (saw, heard, read, inferred) and how sure; a stranger
  reads from signals alone and may place the man or not. The read is kept, so a change shows ("was ...").
- forms: the forms of deference due to a man, which the observer would know to show and which he might get wrong. Knowing
  depends on his time in the life, whether he was taken in, and what he knows of the man. Showing one right earns regard;
  missing or getting one wrong is a slight, through the relationship the other drivers read and through talk.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3

from .design import run_seed
from .world_package import package_for

_DATA: dict = {"key": None, "data": {}}
_INTERNAL = ("retinue", "retinue_set", "in_the_life", "habit")


def data(conn: sqlite3.Connection) -> dict:
    path = package_for(conn).data.get("presence")
    if path is None:
        return {}
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    if _DATA["key"] != key:
        _DATA.update(key=key, data=json.loads(path.read_text(encoding="utf-8")))
    return _DATA["data"]


def enabled(conn: sqlite3.Connection) -> bool:
    return bool(data(conn))


def fig(conn: sqlite3.Connection, name: str) -> float:
    """A figure of the presence data (each a Design proposal, kept beside the data that names it)."""
    f = (data(conn).get("figures") or {}).get(name)
    if f is None:
        raise KeyError(f"presence figure {name} is not defined")
    return float(f["default"])


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _rng(conn, *key) -> random.Random:
    return random.Random(f"{run_seed(conn)}:presence:" + ":".join(str(k) for k in key))


def name_of(conn, aid) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (int(aid),)).fetchone() if aid is not None else None
    return str(r[0]) if r else "someone"


def _alive(conn, aid: int) -> bool:
    r = conn.execute("SELECT status FROM actors WHERE id=?", (int(aid),)).fetchone()
    return bool(r) and str(r[0]) == "active"


def _age(conn, aid: int, day: int):
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (int(aid),)).fetchone()
    return None if not r or r[0] is None else (day - int(r[0])) / 365.0


def seats(conn, aid: int) -> list:
    return conn.execute(
        """SELECT s.*,p.org_kind FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id
           WHERE s.actor_id=? AND s.status='active' ORDER BY s.level DESC,s.id""", (int(aid),)).fetchall()


def years_in_life(conn, aid: int) -> tuple[float, bool]:
    """(years, recorded): what the GM recorded; else from his earliest seat when he joined during the run; else, for a man of the
    opening, his age less the age at which he is taken to have entered. A man with no seat has no time in the life."""
    day = _day(conn)
    r = conn.execute("SELECT amount FROM bearing_marks WHERE actor_id=? AND kind='in_the_life' AND status='active' ORDER BY id DESC LIMIT 1", (int(aid),)).fetchone()
    if r and r[0] is not None:
        return float(r[0]), True
    rows = seats(conn, aid)
    if not rows:
        return 0.0, False
    joined = [int(s["joined_day"]) for s in rows if int(s["joined_day"]) > 0]
    if joined:
        return (day - min(joined)) / 365.0, False
    age = _age(conn, aid, day)
    return max(0.0, (age or 0.0) - fig(conn, "in_life_entry_age")), False


# ---- forms of deference ------------------------------------------------------------------------------------

def _match(cond: dict, rows, age):
    for s in rows:
        if cond.get("kind") and s["org_kind"] != cond["kind"]:
            continue
        if cond.get("roles") and s["role_key"] not in cond["roles"]:
            continue
        if cond.get("min_age") and (age is None or age < float(cond["min_age"])):
            continue
        return s
    return None


def forms_due(conn, subject: int, observer: int | None = None) -> list[dict]:
    """The forms of deference due to a man, from his seats (and his age) and the package's customs. With an observer, only those
    whose scope fits (same organisation, another, or either)."""
    forms = data(conn).get("forms") or []
    if not forms:
        return []
    rows = seats(conn, subject)
    if not rows:
        return []
    age = _age(conn, subject, _day(conn))
    mine = {int(s["org_actor_id"]) for s in seats(conn, observer)} if observer is not None else set()
    out = []
    for f in forms:
        hit = next((s for c in f.get("due_to") or [] if (s := _match(c, rows, age))), None)
        if hit is None:
            continue
        if observer is not None:
            same = int(hit["org_actor_id"]) in mine
            scope = f.get("scope", "any")
            if (scope == "own" and not same) or (scope == "other" and same):
                continue
        out.append(f)
    return out


def form_known(conn, observer: int, form: dict) -> bool:
    """Would the observer know this custom? A man taken in knows it; others learn it with time in the life. A fixed draw per
    (man, custom), so he knows it today if he knew it yesterday."""
    kind = form.get("known_kind")
    rows = [s for s in seats(conn, observer) if not kind or s["org_kind"] == kind]
    if any(s["inducted_day"] is not None for s in rows):
        p = fig(conn, "form_inducted")
    else:
        years = years_in_life(conn, observer)[0] if rows else 0.0
        p = 1.0 - (1.0 - fig(conn, "form_prior")) * math.exp(-fig(conn, "form_per_year") * years)
    return _rng(conn, "form", observer, form["key"]).random() < p


# ---- bearing -------------------------------------------------------------------------------------------------

def _poisson(rng: random.Random, mean: float) -> int:
    n, p, target = 0, 1.0, math.exp(-max(0.0, mean))
    while True:
        p *= rng.random()
        if p <= target:
            return n
        n += 1


def retinue(conn, subject: int) -> list[dict]:
    """Who attends him. Recorded once from his seat, so the crew persists; a man who dies or leaves is replaced. Marks the
    GM proposed (a driver, a secretary) stand with the derived ones."""
    day = _day(conn)
    spec = None
    seat = None
    for s in seats(conn, subject):
        spec = (data(conn).get("retinue") or {}).get(s["role_key"])
        if spec:
            seat = s
            break
    rows = conn.execute("SELECT * FROM bearing_marks WHERE actor_id=? AND kind='retinue' AND status='active' ORDER BY id", (int(subject),)).fetchall()
    live = []
    for m in rows:
        if m["ref_actor_id"] is not None and not (_alive(conn, int(m["ref_actor_id"])) and conn.execute(
                "SELECT 1 FROM org_seats WHERE actor_id=? AND status='active' LIMIT 1", (int(m["ref_actor_id"]),)).fetchone()):
            conn.execute("UPDATE bearing_marks SET status='gone' WHERE id=?", (int(m["id"]),))
            continue
        live.append(m)
    if spec:
        sent = conn.execute("SELECT * FROM bearing_marks WHERE actor_id=? AND kind='retinue_set' AND status='active'", (int(subject),)).fetchone()
        rng = _rng(conn, "retinue", subject, day if sent is not None else "first")
        want = int(sent["amount"]) if sent is not None else _poisson(rng, fig(conn, spec["mean"]))
        if sent is None:
            conn.execute("INSERT OR IGNORE INTO bearing_marks(actor_id,kind,text,amount,source,recorded_day) VALUES (?,?,?,?,?,?)",
                         (int(subject), "retinue_set", "derived", want, "derived", day))
        need = want - sum(1 for m in live if m["ref_actor_id"] is not None)
        if need > 0:
            taken = {int(r[0]) for r in conn.execute("SELECT ref_actor_id FROM bearing_marks WHERE kind='retinue' AND status='active' AND ref_actor_id IS NOT NULL")}
            roles = list(spec.get("from_roles") or [])
            cands = conn.execute(
                f"""SELECT s.actor_id,s.role_key,s.superior_actor_id,s.unit_id FROM org_seats s JOIN actors a ON a.id=s.actor_id
                    WHERE s.org_actor_id=? AND s.status='active' AND a.status='active' AND s.actor_id<>?
                      AND s.role_key IN ({','.join('?' * len(roles))}) ORDER BY s.actor_id""",
                (int(seat["org_actor_id"]), int(subject), *roles)).fetchall() if roles else []
            cands = [c for c in cands if int(c["actor_id"]) not in taken]
            rng.shuffle(cands)
            cands.sort(key=lambda c: (c["superior_actor_id"] != subject, c["unit_id"] != seat["unit_id"]))
            for c in cands[:need]:
                conn.execute("INSERT OR IGNORE INTO bearing_marks(actor_id,kind,text,ref_actor_id,source,recorded_day) VALUES (?,?,?,?,?,?)",
                             (int(subject), "retinue", f"{name_of(conn, c['actor_id'])} ({c['role_key']})", int(c["actor_id"]), "derived", day))
            live = conn.execute("SELECT * FROM bearing_marks WHERE actor_id=? AND kind='retinue' AND status='active' ORDER BY id", (int(subject),)).fetchall()
    return [{"id": m["ref_actor_id"], "name": name_of(conn, m["ref_actor_id"]) if m["ref_actor_id"] is not None else m["text"], "text": m["text"]} for m in live]


def spending(conn, subject: int) -> str | None:
    from .ledger import balance
    day = _day(conn)
    out = conn.execute("SELECT COALESCE(SUM(amount),0) FROM economic_flows WHERE source_actor_id=? AND day>?", (int(subject), day - 30)).fetchone()[0]
    purse = max(0.0, balance(conn, ("person", int(subject))))
    if out > 0 and out / (out + purse) >= fig(conn, "spend_free_ratio"):
        return "has been spending freely"
    return None


def signals(conn, subject: int) -> list[dict]:
    """What he wears, drives, lives in and keeps company with: what he owns and what was proposed and recorded."""
    out = [{"text": str(r["name"]), "kind": str(r["item_type"])} for r in conn.execute(
        "SELECT name,item_type FROM possessions WHERE holder_actor_id=? AND status='held' ORDER BY id", (int(subject),))]
    for m in conn.execute("SELECT kind,text,beyond_means FROM bearing_marks WHERE actor_id=? AND status='active' AND kind NOT IN (%s) ORDER BY id" %
                          ",".join("?" * len(_INTERNAL)), (int(subject), *_INTERNAL)):
        out.append({"text": str(m["text"]), "kind": str(m["kind"]), **({"beyond_means": True} if m["beyond_means"] else {})})
    return out


def bearing(conn, subject: int) -> dict:
    ret = retinue(conn, subject)
    return {"retinue": ret, "signals": signals(conn, subject), "spending": spending(conn, subject)}


def unrecorded(conn, subject: int) -> list[str]:
    """Bearing facts nobody has recorded yet, in the package's words, for the GM to propose (the engine then records them)."""
    have = {str(r[0]) for r in conn.execute("SELECT kind FROM bearing_marks WHERE actor_id=? AND status='active'", (int(subject),))}
    if conn.execute("SELECT 1 FROM possessions WHERE holder_actor_id=? AND status='held' LIMIT 1", (int(subject),)).fetchone():
        have |= {"car"}
    out = []
    for c in data(conn).get("core_marks") or []:
        if c["kind"] in have:
            continue
        if c["kind"] == "in_the_life" and years_in_life(conn, subject)[1]:
            continue
        out.append(f"{c['kind']}: {c['ask']}")
    return out


def record_mark(conn, subject: int, kind: str, text: str) -> dict:
    """Record a bearing fact the GM proposed. Vetoes only a contradiction: a time in the life longer than he has lived. A display
    that costs more than his purse (`cost N` in the text) is allowed but marked as beyond his means, and it draws talk."""
    import re
    from .ledger import balance
    kind = re.sub(r"\s+", "_", str(kind or "").strip().lower())[:40]
    text = " ".join(str(text or "").split())[:200]
    if not kind or not text:
        raise ValueError("a bearing note needs a kind (dress, car, house, company...) and text")
    day = _day(conn)
    amount = None
    cost = re.search(r"cost\s+(\d+(?:\.\d+)?)", text, re.I)
    if cost:
        amount = float(cost.group(1))
    if kind == "in_the_life":
        words = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12}
        m = re.search(r"(\d+(?:\.\d+)?|%s)\s*(year|month|week|day)" % "|".join(words), text, re.I)
        if not m:
            raise ValueError("in_the_life needs a length of time (for example '6 months' or 'two years')")
        n = float(words.get(m.group(1).lower(), m.group(1)) if not m.group(1).replace(".", "").isdigit() else m.group(1))
        amount = n / {"year": 1, "month": 12, "week": 52, "day": 365}[m.group(2).lower()]
        age = _age(conn, subject, day)
        if age is not None and amount > age:
            raise ValueError(f"he is {age:.0f}; he cannot have been in the life longer than he has lived")
        conn.execute("UPDATE bearing_marks SET status='gone' WHERE actor_id=? AND kind='in_the_life'", (int(subject),))
    beyond = 0
    if amount is not None and kind != "in_the_life" and amount > max(0.0, balance(conn, ("person", int(subject)))) * fig(conn, "beyond_means_ratio"):
        beyond = 1
    conn.execute(
        """INSERT INTO bearing_marks(actor_id,kind,text,amount,source,beyond_means,recorded_day) VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(actor_id,kind,text) DO UPDATE SET status='active',amount=excluded.amount,beyond_means=excluded.beyond_means""",
        (int(subject), kind, text, amount, "proposed", beyond, day))
    out = {"saved": "bearing", "kind": kind, "summary": f"Recorded for {name_of(conn, subject)}: {kind}: {text[:80]}"}
    if beyond:
        _event(conn, day, "display_beyond_means", f"{name_of(conn, subject)} shows more than he is known to have",
               f"{name_of(conn, subject)}: {text}", subject)
        out["costs"] = "beyond his means: it draws envy and attention, and can be read as a front"
    return out


def _event(conn, day: int, kind: str, title: str, summary: str, subject: int, severity: int = 1) -> int:
    from .information import register_event_information
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(subject),)).fetchone()
    eid = int(conn.execute("INSERT INTO events(day,event_type,title,summary,severity,location_id,source_actor_id) VALUES (?,?,?,?,?,?,?)",
                           (day, kind, title, summary, severity, loc[0] if loc else None, int(subject))).lastrowid)
    conn.execute("INSERT OR IGNORE INTO event_targets(event_id,actor_id,impact) VALUES (?,?,?)", (eid, int(subject), kind))
    register_event_information(conn, eid, day=day, visibility="limited")
    return eid


# ---- the room read -----------------------------------------------------------------------------------------

def _stance(conn, observer: int, subject: int) -> str | None:
    from .embodiment import stance_band, trust_band
    from .relationships import relationship_view
    if not conn.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(observer), int(subject))).fetchone():
        return None
    r = relationship_view(conn, observer, subject)
    bits = []
    sb = stance_band(r["stance"])
    if sb != "mixed_or_neutral":
        bits.append(str(sb).replace("_", " "))
    tb = trust_band(r["trust"])
    if tb != "uncertain_or_moderate":
        bits.append("trusts" if tb == "high" else "distrusts")
    if r["fear"] >= 50:
        bits.append("afraid")
    elif r["fear"] >= 25:
        bits.append("wary")
    if r["resentment"] >= 35:
        bits.append("resents")
    if r["respect"] >= 50:
        bits.append("respects")
    elif r["respect"] <= -35:
        bits.append("contemptuous")
    return "; ".join(bits) or None


def _like(text: str) -> str:
    return "%" + text.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def _source(conn, observer: int, subject: int) -> tuple[str, float]:
    """(saw | heard | read | inferred, how sure 0..1) from what the observer holds about the subject."""
    rows = conn.execute(
        """SELECT k.id,k.confidence,k.truth_event_id FROM knowledge k WHERE k.knower_actor_id=? AND k.belief_text LIKE ? ESCAPE '!'
           ORDER BY k.confidence DESC LIMIT 3""", (int(observer), _like(name_of(conn, subject)))).fetchall()
    fam = conn.execute("SELECT familiarity FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(observer), int(subject))).fetchone()
    fam = float(fam[0]) if fam else 0.0
    if rows:
        k = rows[0]
        prov = conn.execute("SELECT source_kind FROM knowledge_provenance WHERE knowledge_id=? ORDER BY id LIMIT 1", (int(k["id"]),)).fetchone()
        kind = str(prov[0]) if prov else "actor"
        word = {"event": "saw", "scene": "saw", "channel": "read", "rumour": "heard"}.get(kind, "heard")
        return word, max(float(k["confidence"]), fam / 100.0)
    if fam > 0:
        return "saw", fam / 100.0
    return "inferred", 0.0


def _sure(p: float) -> str:
    return "sure" if p >= 0.7 else "fairly sure" if p >= 0.4 else "guessing"


def recognises(conn, observer: int, subject: int) -> tuple[bool, float]:
    """(placed, the evidence): would the observer place the subject as the man he is? From dealings with him, being told of him,
    his own time in the life, the subject's fame, and what shows (attendants, signals). A fixed draw per pair, so he is placed
    today if he was yesterday, and more evidence only moves him toward it."""
    from .standing import _is_famous
    fam = conn.execute("SELECT familiarity FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(observer), int(subject))).fetchone()
    fam = float(fam[0]) if fam else 0.0
    told = bool(conn.execute("SELECT 1 FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE ? ESCAPE '!' LIMIT 1",
                             (int(observer), _like(name_of(conn, subject)))).fetchone())
    in_life = bool(seats(conn, subject))
    years = years_in_life(conn, observer)[0] if in_life else 0.0
    ret = len(retinue(conn, subject))
    sig = len(signals(conn, subject))
    score = (fig(conn, "recog_base") + fig(conn, "recog_familiarity") * fam / 100.0 + fig(conn, "recog_years") * (1.0 - math.exp(-years / 2.0))
             + (fig(conn, "recog_told") if told else 0.0) + (fig(conn, "recog_fame") if _is_famous(conn, subject) else 0.0)
             + fig(conn, "recog_retinue") * ret + fig(conn, "recog_signals") * sig)
    return _rng(conn, "recognise", observer, subject).random() < score, score


def room_read(conn, subject: int, observer: int) -> dict:
    """What one person in the room makes of the subject: stance, where it comes from, how sure, and whether he places him; kept,
    so a change since the last read shows."""
    day = _day(conn)
    stance = _stance(conn, observer, subject)
    src, p = _source(conn, observer, subject)
    placed, score = recognises(conn, observer, subject)
    basis = f"{src}|{stance}|{int(placed)}"
    prev = conn.execute("SELECT * FROM room_reads WHERE observer_actor_id=? AND subject_actor_id=?", (int(observer), int(subject))).fetchone()
    changed = None
    if prev is None:
        conn.execute("INSERT INTO room_reads(observer_actor_id,subject_actor_id,first_day,day,stance,source,sure,recognised,basis) VALUES (?,?,?,?,?,?,?,?,?)",
                     (int(observer), int(subject), day, day, stance, src, _sure(p), int(placed), basis))
    else:
        if prev["basis"] != basis:
            if (prev["stance"] or None) != stance:
                changed = f"was {prev['stance'] or 'no view'}"
            elif int(prev["recognised"]) != int(placed):
                changed = "now places him" if placed else "no longer places him"
            conn.execute("UPDATE room_reads SET day=?,stance=?,source=?,sure=?,recognised=?,basis=? WHERE observer_actor_id=? AND subject_actor_id=?",
                         (day, stance, src, _sure(p), int(placed), basis, int(observer), int(subject)))
    out = {"stance": stance, "from": src, "sure": _sure(p), "placed": placed}
    if not placed:
        words = data(conn).get("readings") or []
        if words:
            step = max(1e-9, fig(conn, "reading_band"))
            out["reads_him_as"] = words[min(len(words) - 1, int(score / step))]
    if changed:
        out["changed"] = changed
    return out


def reads_of(conn, observer: int, subject: int) -> dict:
    """What the observer reads in the subject: what shows (attendants, signals, spending), and, when he places him, the forms he
    knows to show and those he is unsure of. When he does not place him, what is due is returned apart, marked as outside his
    knowledge, so the GM can play a missed cue; he is never told the man's place in the life. Forms are returned by key (see form_text)."""
    b = bearing(conn, subject)
    placed, _ = recognises(conn, observer, subject)
    sees = [s["text"] for s in b["signals"]]
    out = {"id": int(subject), "name": name_of(conn, subject), "sees": sees or None,
           "with_him": len(b["retinue"]) or None, "spending": b["spending"], "placed": placed}
    due = forms_due(conn, subject, observer)
    if placed:
        known = [f["key"] for f in due if form_known(conn, observer, f)]
        unsure = [f["key"] for f in due if not form_known(conn, observer, f)]
        if known:
            out["forms_he_knows"] = known
        if unsure:
            out["forms_he_is_unsure_of"] = unsure
    hidden = None
    if not placed and due:
        seat = seats(conn, subject)[0]
        org = conn.execute("SELECT name FROM actors WHERE id=?", (int(seat["org_actor_id"]),)).fetchone()
        hidden = {"id": int(subject), "name": out["name"], "is": f"{seat['role_key']} in the {org[0] if org else 'organisation'}",
                  "due": [f["key"] for f in due], "he_does_not_read_this": True}
    return {"read": {k: v for k, v in out.items() if v is not None}, "hidden": hidden}


# ---- deference shown, right or wrong -----------------------------------------------------------------------

def form_outcome(conn, actor: int, subject: int, outcome: str, note: str | None = None) -> dict:
    """An actor showed a form of deference to the subject: shown (right), missed or wrong. Right earns regard and trust; missed or wrong
    is a slight: the one slighted holds it against him, and those looking on, who know the one slighted, think less of him. It
    becomes talk. Any actor, the protagonist included."""
    from .relationships import adjust_relationship
    outcome = str(outcome or "").strip().lower()
    if outcome not in ("shown", "missed", "wrong"):
        raise ValueError("outcome must be shown, missed or wrong")
    if int(actor) == int(subject):
        raise ValueError("a man does not show deference to himself")
    day = _day(conn)
    right = outcome == "shown"
    d = {"respect_delta": fig(conn, "form_right_respect"), "trust_delta": fig(conn, "form_right_trust")} if right else \
        {"resentment_delta": fig(conn, "form_wrong_resent"), "respect_delta": -fig(conn, "form_wrong_respect")}
    adjust_relationship(conn, int(subject), int(actor), day, **d)
    share = fig(conn, "form_witness_share")
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(subject),)).fetchone()
    looked = []
    if loc and loc[0] is not None:
        looked = [int(r[0]) for r in conn.execute(
            """SELECT a.id FROM actors a JOIN relationships r ON r.actor_a_id=a.id AND r.actor_b_id=? WHERE a.current_location_id=?
               AND a.status='active' AND a.actor_type='character' AND a.id NOT IN (?,?) AND r.familiarity>0""", (int(subject), loc[0], int(actor), int(subject)))]
    for w in looked:
        adjust_relationship(conn, w, int(actor), day, **{k: v * share for k, v in d.items() if k in ("respect_delta",)})
    conn.execute("INSERT INTO form_acts(day,actor_id,subject_actor_id,outcome,note,witnesses) VALUES (?,?,?,?,?,?)",
                 (day, int(actor), int(subject), outcome, str(note or "")[:200], len(looked)))
    a, s = name_of(conn, actor), name_of(conn, subject)
    title = f"{a} showed {s} proper respect" if right else f"{a} slighted {s} by missing the form"
    _event(conn, day, "form_" + outcome, title, f"{title}. {note or ''}".strip(), actor)
    return {"saved": "form", "outcome": outcome, "witnesses": len(looked),
            "summary": f"{a} to {s}: {outcome}" + ("; regard earned" if right else "; a slight, remembered")}


def form_text(conn, keys) -> dict[str, str]:
    """The package's words for the forms named (each once, however many people they apply to)."""
    want = set(keys)
    return {f["key"]: f["text"] for f in data(conn).get("forms") or [] if f["key"] in want}
