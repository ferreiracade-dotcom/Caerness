"""Free-form operations: the GM states an intent, who is committed, with what, toward whom, on what conditions and over what time.

The engine maps it onto the machinery it has (player_operations, battles and duels, training, craft, public projects, treatment)
and judges it at a realistic scale: money and men are debited where they come from, an oversized ask gets what exists with the
reason in words, and only a true contradiction is refused. An intent nothing models is still accepted: it becomes a commitment
(an `obligations` row) with its costs taken and its day set, and the GM narrates within that.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from . import commitments, ledger
from . import player_operations as po

HOLDER_KINDS = ("business", "outfit", "household", "institution", "polity")
REF_KINDS = ("actor", "person", "location", "business", "outfit", "household", "institution", "polity", "crew")

_KINDS = (  # first match wins; the GM's own `kind` hint beats all of them
    ("travel", r"\b(travel|ride to|sail to|march to|journey|head (?:to|for)|set out for|go to)\b"),
    ("duel", r"\b(duel|single combat|challenge .* to a fight)\b"),
    ("battle", r"\b(battle|siege|besiege|storm the|give battle|offer battle|pitched)\b"),
    ("message", r"\b(write to|letter|send word|message|messenger|courier|summon|send for|petition)\b"),
    ("treat", r"\b(heal|treat|cure|tend|physician|nurse|set the bone|care for)\b"),
    ("train", r"\b(train|study|learn|practi[sc]e|drill|apprentice|spar|master the)\b"),
    ("craft", r"\b(craft|forge|brew|manufacture|produce|smith|weave|tan|bake)\b"),
    ("project", r"\b(build|construct|repair|fortify|rebuild|raise a (?:wall|tower|bridge|granary|market)|garrison|pave)\b"),
    ("attack", r"\b(attack|assault|raid|rob|ambush|burn|arson|set fire|kidnap|abduct|capture|kill|murder|assassinate|beat|thrash|drive off|loot|sack)\b"),
    ("trade", r"\b(buy|sell|purchase)\b.*\b(business|shop|stall|house of|inn|mill|forge)\b"),
    ("demand", r"\b(demand|extort|threaten|tribute|truce|alliance|ally|treaty|ultimatum|expel|force .* to|make .* stop|make .* tell)\b"),
    ("lend", r"\b(lend|loan)\b"),
    ("hire", r"\b(hire|recruit|enlist|muster|employ|engage|take on|conscript|levy|raise (?:a |an )?(?:company|force|band|men|troops|army)|dismiss|fire|promote)\b"),
    ("pay", r"\b(bribe|pay|donate|gift|fund|spend|tithe|endow|sponsor|grease|buy off|feast)\b"),
    ("order", r"\b(order|instruct|command|tell .* to|have .* (?:do|go|watch|guard))\b"),
)
_FOUND = re.compile(r"\b(found|establish|open|start|set up|create)\b.*\b(business|shop|stall|outfit|gang|school|company|guild|house|household|sect|inn|firm)\b")


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def parse_time(v) -> int | None:
    """Days from 3, "3", "a week", "two months", "a season"."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return max(0, int(v))
    t = str(v).lower()
    words = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "few": 3, "couple": 2}
    m = re.search(r"(\d+|\b(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|twelve|few|couple)\b)(?:\s+of)?\s*(day|week|fortnight|month|season|year)", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else words.get(m.group(1), 1)
        return n * {"day": 1, "week": 7, "fortnight": 14, "month": 30, "season": 90, "year": 365}[m.group(2)]
    m = re.match(r"^\s*(\d+)\s*$", t)
    return int(m.group(1)) if m else None


def resolve_ref(conn: sqlite3.Connection, ref) -> tuple[str, int, str]:
    """(kind, id, name) from an id, "kind:id", or a name. A name that fits several things is an input gap listing them."""
    tables = {"actor": ("actors", "name"), "location": ("locations", "name"), "business": ("civilian_enterprises", "name"),
              "outfit": ("underworld_organizations", "name"), "household": ("households", "name"), "crew": ("underworld_crews", "name")}
    if isinstance(ref, dict):
        ref = ref.get("ref") or ref.get("id") or ref.get("name")
    if isinstance(ref, int) and not isinstance(ref, bool):
        ref = f"actor:{ref}"
    text = str(ref).strip()
    kind, sep, raw = text.partition(":")
    if sep and kind in REF_KINDS and raw.strip().isdigit():
        kind = "actor" if kind == "person" else kind
        i = int(raw)
        if kind in ("institution", "polity"):
            row = conn.execute("SELECT name FROM actors WHERE id=?", (i,)).fetchone() if kind == "institution" else conn.execute(
                "SELECT a.name FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id WHERE p.id=?", (i,)).fetchone()
        else:
            row = conn.execute(f"SELECT {tables[kind][1]} FROM {tables[kind][0]} WHERE id=?", (i,)).fetchone()
        if row is None:
            raise ValueError(f"unknown {kind} {i}")
        return kind, i, str(row[0])
    if text.isdigit():
        return resolve_ref(conn, f"actor:{text}")
    found: list[tuple[str, int, str]] = []
    for kind, (table, col) in tables.items():
        rows = conn.execute(f"SELECT id,{col} FROM {table} WHERE {col}=? COLLATE NOCASE", (text,)).fetchall()
        if not rows:
            rows = conn.execute(f"SELECT id,{col} FROM {table} WHERE {col} LIKE ? AND {col} NOT LIKE '[%' LIMIT 4", (f"%{text}%",)).fetchall()
        found += [(kind, int(r[0]), str(r[1])) for r in rows]
    if len(found) == 1:
        return found[0]
    if not found:
        raise ValueError(f"nothing is known by the name {text!r}; use an id from scene or lookup")
    raise ValueError("more than one thing fits " + repr(text) + ": " + ", ".join(f"{k}:{i} {n}" for k, i, n in found[:5]))


def classify(intent: str, hint: str | None) -> str:
    h = (hint or "").lower().strip()
    known = {k for k, _ in _KINDS} | set(po.OPERATIONS) | {"plan", "found"}
    if h in known:
        return h
    low = intent.lower()
    if _FOUND.search(low):
        return "found"
    for kind, rx in _KINDS:
        if re.search(rx, low):
            return kind
    return "plan"


def _men_available(conn, me: int) -> tuple[int, str]:
    """How many men he could bring to bear: his outfit's, else the able men of the place he is in (a levy takes a fraction)."""
    org = po._my_outfit(conn, me)
    if org is not None:
        n = int(conn.execute("SELECT member_count_estimate FROM underworld_organizations WHERE id=?", (org,)).fetchone()[0])
        return max(0, n - 1), "his outfit"
    here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
    n = int(conn.execute("SELECT COUNT(*) FROM background_person_profiles WHERE current_location_id=? AND demographic_sex='male' AND (? - birth_day)/365 BETWEEN 16 AND 55",
                         (here, _day(conn))).fetchone()[0])
    return n // 3, "the place"


def _holder(targets, *, kinds=HOLDER_KINDS):
    for k, i, n in targets:
        if k in kinds:
            return k, i
    return None


def _actor_target(targets):
    for k, i, n in targets:
        if k == "actor":
            return i
    return None


def _money(f: dict, res: dict):
    for key in ("money", "amount", "cash", "price", "sum"):
        if res.get(key) is not None:
            return res[key]
    return f.get("amount")


_INTENT_KIND = (("kill", r"kill|murder|assassinate|slay|burn|arson|set fire"), ("drive_off", r"drive off|scare|chase|frighten|warn|run (?:him|them) out"))
_DEMAND_WHAT = (("information", r"tell|inform|confess|reveal|talk"), ("stop", r"\bstop|cease|desist|leave|quit|keep away|no more"), ("tribute", r"tribute"),
                ("truce", r"truce|peace"), ("alliance", r"allian|ally|treaty"), ("split", r"split|divide|share the"), ("debt", r"\bdebt|owes|owed|repay"),
                ("payment", r"pay|hand over|give|money|cash"))


def _first(rx_table, low: str, default: str) -> str:
    for key, rx in rx_table:
        if re.search(rx, low):
            return key
    return default


def run(conn: sqlite3.Connection, me: int, intent: str, f: dict, call_id: str, hint: str | None = None) -> dict:
    f = dict(f or {})
    res = dict(f.get("resources") or {})
    try:
        targets = [resolve_ref(conn, t) for t in (f.get("targets") if isinstance(f.get("targets"), list) else ([f["targets"]] if f.get("targets") else []))]
        if f.get("target") is not None:
            targets.insert(0, resolve_ref(conn, f["target"]))
        committed = []
        for a in (f.get("actors") or []):
            spec = a if isinstance(a, dict) else {"ref": a}
            kind, i, name = resolve_ref(conn, spec.get("ref") or spec.get("id") or spec.get("name"))
            committed.append({"kind": kind, "id": i, "name": name, "count": int(spec.get("count") or 1), "role": spec.get("role")})
    except ValueError as e:
        return _refuse(str(e), "input_gap")
    days = parse_time(f.get("time"))
    kind = classify(intent, hint)
    low = intent.lower()
    base = {"mapped_to": kind}
    handler = {"travel": _travel, "duel": _duel, "battle": _battle, "message": _message, "treat": _treat, "train": _train,
               "craft": _craft, "project": _project, "found": _found}.get(kind)
    try:
        if handler is not None:
            out = handler(conn, me, intent, f, res, targets, committed, days, call_id)
        elif kind in po.OPERATIONS:
            out = _operation(conn, me, kind, intent, f, res, targets, committed, days, call_id)
        else:
            out = _commit(conn, me, intent, f, res, targets, committed, days, "plan")
    except _Gap as g:
        return _refuse(str(g), "input_gap")
    if out.get("status") == "fallback":  # machinery exists but this case does not fit it: keep it as a commitment, with the reason
        why = out["summary"]
        out = _commit(conn, me, intent, f, res, targets, committed, days, kind)
        out["summary"] = f"{why} {out['summary']}"
    return {**base, **out}


class _Gap(Exception):
    pass


def _refuse(summary: str, reason_kind: str = "contradiction") -> dict:
    return {"status": "refused", "summary": summary, "reason_kind": reason_kind}


def _operation(conn, me, kind, intent, f, res, targets, committed, days, call_id) -> dict:
    low = intent.lower()
    d: dict[str, Any] = {k: v for k, v in (f.get("details") or {}).items()}
    d["_call_id"] = call_id
    money = _money(f, res)
    actor = _actor_target(targets)
    holder = _holder(targets)
    men = int(res.get("men") or 0) or sum(c["count"] for c in committed if c["kind"] == "actor" and c["count"] > 1)
    named = [c["id"] for c in committed if c["kind"] == "actor" and c["count"] == 1]
    crew = next((f"crew:{c['id']}" for c in committed if c["kind"] == "crew"), None) or d.get("crew")
    if res.get("from"):
        d["from"] = res["from"]
    if kind == "pay":
        if money is None:
            raise _Gap("Say how much: resources.money as a number, a scale word or a share.")
        d.update(amount=money, purpose=intent)
        if holder:
            d["to"] = f"{holder[0]}:{holder[1]}"
        elif actor is None:
            d["to"] = "spend"
        return po.execute(conn, me, "pay", target_actor_id=actor, details=d, intent=intent)
    if kind == "hire":
        into = holder if holder and holder[0] in ("business", "outfit", "household") else None
        if into is None:
            org = po._my_outfit(conn, me)
            if org is None:
                raise _Gap("Say where the people go: a business, outfit or household among the targets.")
            into = ("outfit", org)
        d["into"] = f"{into[0]}:{into[1]}"
        if men:
            d["count"] = men
        if res.get("wage") is not None:
            d["wage"] = res["wage"]
        if res.get("sign_on") is not None:
            d["amount"] = res["sign_on"]
        d["role"] = f.get("role") or res.get("role") or d.get("role") or ("none" if re.search(r"dismiss|fire", low) else "")
        if crew:
            d["crew"] = crew
        if actor is None and not men and not named:
            raise _Gap("Say who or how many: a target person, or resources.men.")
        return po.execute(conn, me, "hire", target_actor_id=actor, details=d, intent=intent)
    if kind == "lend":
        if actor is None or money is None:
            raise _Gap("Say who borrows (a target person) and how much (resources.money).")
        d.update(amount=money)
        if res.get("rate") is not None:
            d["rate"] = res["rate"]
        if days:
            d["due_days"] = days
        return po.execute(conn, me, "lend", target_actor_id=actor, details=d, intent=intent)
    if kind == "demand":
        if actor is None:
            raise _Gap("Say of whom: a target person.")
        d.setdefault("what", _first(_DEMAND_WHAT, low, "other" if money is None else "payment"))
        if money is not None:
            d["amount"] = money
        d["terms"] = d.get("terms") or "; ".join(str(c) for c in (f.get("conditions") or []) if c) or intent
        if named:
            d["with"] = named
        if crew:
            d["crew"] = crew
        if men:
            d["men"] = men
        d["open"] = bool(re.search(r"openly|publicly|in front of|threat", low))
        return po.execute(conn, me, "demand", target_actor_id=actor, details=d, intent=intent)
    if kind == "attack":
        d["intent_kind"] = d.get("intent_kind") or _first(_INTENT_KIND, low, "beat")
        biz = next((i for k, i, _ in targets if k == "business"), None)
        if biz is not None:
            d["business"] = f"business:{biz}"
        if re.search(r"rob|raid|loot|sack|plunder", low):
            d["loot"] = True
        if re.search(r"kidnap|abduct|capture", low):
            d["capture"] = True
        if named:
            d["with"] = named
        if crew:
            d["crew"] = crew
        if men:
            d["men"] = men
        if actor is None and biz is None:
            raise _Gap("Say who or what is attacked: a target person or business.")
        return po.execute(conn, me, "attack", target_actor_id=actor, details=d, intent=intent)
    if kind == "trade":
        biz = next((i for k, i, _ in targets if k == "business"), None)
        if biz is None or actor is None or money is None:
            raise _Gap("Say the business and the other party among the targets, and the price in resources.money.")
        d.update(business=f"business:{biz}", amount=money, deal="sell" if re.search(r"\bsell", low) else "buy")
        return po.execute(conn, me, "trade", target_actor_id=actor, details=d, intent=intent)
    if kind == "order":
        who = next((c["id"] for c in committed if c["kind"] == "actor"), actor)
        toward = actor if who != actor else None
        d["do"] = d.get("do") or f.get("do") or intent
        if toward is not None:
            d["toward"] = toward
        if money is not None:
            d["amount"] = money
        if days:
            d["time"] = days
        return po.execute(conn, me, "order", target_actor_id=who, details=d, intent=intent)
    return _refuse("That is not something the engine can carry out yet.", "input_gap")


# ---------------------------------------------------------------- commitments (nothing models it, or it does not fit)

def _commit(conn, me, intent, f, res, targets, committed, days, kind) -> dict:
    """Accept it anyway: take its costs (money, people, time) plausibly and keep it as a commitment the world can see."""
    day = _day(conn)
    pay_note: list[str] = []
    cost_words: dict[str, Any] = {}
    status = "applied"
    src_ref = res.get("from") or "me"
    try:
        src = ledger.parse_holder(src_ref, me, conn)
    except ValueError as e:
        raise _Gap(str(e))
    if not ledger.can_draw(conn, me, src):
        return _refuse("He has no right to draw on that purse.")
    men = int(res.get("men") or 0) + sum(c["count"] for c in committed if c["kind"] == "actor" and c["count"] > 1)
    span = days or max(3, min(60, 3 + men // 5))
    est_wages = 0.0
    if men:
        have, where = _men_available(conn, me)
        if men > have:
            pay_note.append(f"there aren't that many men to be had from {where}")
            status = "partial"
            men = have
        est_wages = men * 0.10 * span / 30.0
        cost_words["men"] = men
    money = _money(f, res)
    total = 0.0
    try:
        if money is not None:
            total = ledger.amount_of(money, ledger.balance(conn, src))
    except ValueError as e:
        raise _Gap(str(e))
    total += est_wages
    spent = 0.0
    if total > 0:
        spent = ledger.spend(conn, src, total, purpose=intent, allow_partial=True)
        if spent < total - 1e-9:
            pay_note.append("the money on hand would not cover all of it, so it is scaled back")
            status = "partial"
        cost_words["money"] = ledger.scale_word(spent) if spent > 0 else "nothing"
    funded = 1.0 if total <= 0 else min(1.0, spent / total)
    names = [c["name"] for c in committed]
    cid = commitments.record(
        conn, me, intent, kind=kind, due_day=day + span, importance=3,
        target_location_id=next((i for k, i, _ in targets if k == "location"), None),
        target_actor_id=_actor_target(targets),
        details={"terms": f.get("conditions"), "people": [c["id"] for c in committed if c["kind"] == "actor"], "people_names": names,
                 "men": men or None, "cost_words": cost_words, "funded": round(funded, 3), "targets": [f"{k}:{i}" for k, i, _ in targets],
                 "started_day": day, "span": span})
    in_words = "within the day" if span <= 1 else f"in about {span} days"
    summary = f"He sets it in motion; it will be settled {in_words}."
    if pay_note:
        summary += " " + "; ".join(pay_note).capitalize() + "."
    _log(conn, me, "Commitment taken on", f"{intent[:140]} ({in_words}).")
    return {"status": status, "summary": summary, "commitment_id": cid, "ready_in_days": span, "costs": cost_words,
            **({"conditions": f["conditions"]} if f.get("conditions") else {})}


def _log(conn, me, title, summary, severity: int = 1):
    from .interactions import _log_event
    return _log_event(conn, _day(conn), "player_operation", title, summary, severity, me, ())


def _found(conn, me, intent, f, res, targets, committed, days, call_id) -> dict:
    """Founding something he owns belongs to the new-character work; here it is only planned, with no money taken."""
    out = _commit(conn, me, intent, {**f, "resources": {}}, {}, targets, committed, days, "plan")
    out["summary"] = "Founding something new under his own name is done with author (a business or outfit in proportion to the place, paid from his purse); here it is only planned and nothing was spent. " + out["summary"]
    out["status"] = "partial"
    return out


# ---------------------------------------------------------------- travel, messages

def _travel(conn, me, intent, f, res, targets, committed, days, call_id) -> dict:
    loc = next((i for k, i, _ in targets if k == "location"), None)
    if loc is None:
        raise _Gap("Say where: a location among the targets.")
    return {"status": "delegate", "delegate": "travel", "target_location_id": loc, "summary": ""}


def _message(conn, me, intent, f, res, targets, committed, days, call_id) -> dict:
    """Word sent to someone elsewhere arrives after the real journey and is answered then."""
    from .actions import shortest_route
    actor = _actor_target(targets)
    if actor is None:
        raise _Gap("Say to whom: a target person.")
    if not po._living(conn, actor):
        return _refuse("There is no living person there to receive it.")
    here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
    there = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor,)).fetchone()[0]
    if there is None or here == there:
        return {"status": "fallback", "summary": "He is here; no message is needed, speak to him."}
    route = shortest_route(conn, int(here), int(there)) if here is not None else None
    if route is None:
        span = 30
        note = " No charted road joins the two places, so the word goes by roundabout hands."
    else:
        span = max(1, route[0])
        note = ""
    span = max(1, span // 2 if span > 2 else span)  # a courier rides faster than a traveller walks
    tells = f.get("tells") or []
    cid = commitments.record(conn, me, intent, kind="message", target_actor_id=actor, due_day=_day(conn) + span, importance=2,
                             details={"tells": tells, "recipient": actor, "terms": f.get("conditions")})
    return {"status": "applied", "summary": f"The word goes out; it will reach {po._name(conn, actor)} in about {span} days, and the answer comes after.{note}",
            "commitment_id": cid, "ready_in_days": span}


def settle_due(conn: sqlite3.Connection, me: int) -> list[dict]:
    """Carry out commitments whose day has come. Returns what happened, for the GM to narrate within."""
    from . import findings
    from .interactions import create_interaction, resolve_interaction
    day = _day(conn)
    done = []
    for r in conn.execute("SELECT * FROM obligations WHERE actor_id=? AND source_kind=? AND status='active' AND due_day IS NOT NULL AND due_day<=? ORDER BY due_day,id",
                          (me, commitments.SOURCE, day)).fetchall():
        d = commitments.details_of(r)
        kind = d.get("kind")
        if kind == "message":
            rid = int(d.get("recipient") or r["target_actor_id"] or 0)
            if rid and po._living(conn, rid):
                findings.tell(conn, rid, [str(t) for t in (d.get("tells") or [])], source=me)
                iid = create_interaction(conn, me, rid, "conversation", day, urgency=3, stakes=1, terms={"purpose": r["description"]},
                                         rationale="A message from the protagonist arrives", response_due_day=day)
                ir = resolve_interaction(conn, iid, day)
                result = f"The message reached {po._name(conn, rid)}. {ir.summary}"
            else:
                result = "The message could not be delivered."
        elif kind in ("order", "concession"):
            continue
        else:
            funded = float(d.get("funded", 1.0))
            result = ("It was carried out as planned." if funded >= 0.999 else
                      "It was only partly carried out: the means fell short of what was meant.")
        commitments.complete(conn, int(r["id"]))
        _log(conn, me, "Commitment settled", f"{r['description'][:120]} {result}")
        done.append({"what": r["description"], "result": result, "kind": kind})
    return done


# ---------------------------------------------------------------- the machinery that already exists

_DOMAINS = (("martial", r"sword|fight|martial|spar|arms|combat|weapon|boxing|wrestl"), ("command", r"command|lead|tactic|generalship|army"),
            ("commerce", r"trade|commerce|merchant|account|haggl|market"), ("medicine", r"medicine|heal|physic|herb|surgery"),
            ("law", r"\blaw|legal|court|statute"), ("politics", r"politic|court intrigue|diplomac|statecraft"),
            ("scholarship", r"read|scholar|letters|history|study|lore|books"), ("craft", r"craft|smith|forge|carpent|weav"),
            ("administration", r"administ|steward|manage|bureau"), ("social", r"social|etiquette|charm|persuade|speech"), ("art_culture", r"music|paint|poetry|art\b"))


def domain_for(text: str) -> str | None:
    return _first(_DOMAINS, text.lower(), "") or None


def _train(conn, me, intent, f, res, targets, committed, days, call_id) -> dict:
    from . import education
    dom = domain_for(intent) or domain_for(str(f.get("subject") or ""))
    if dom is None:
        return {"status": "fallback", "summary": "No known discipline fits that."}
    here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
    progs = conn.execute("""SELECT p.* FROM education_programs p LEFT JOIN actors i ON i.id=p.institution_actor_id
                            WHERE p.status='active' AND p.domain_key=? AND (i.current_location_id=? OR p.institution_actor_id IS NULL) ORDER BY p.min_entry_score,p.id""",
                         (dom, here)).fetchall()
    why = f"No programme in {dom.replace('_', ' ')} is run here."
    for p in progs:
        teacher = _actor_target(targets)
        try:
            eid = education.enroll(conn, me, int(p["id"]), primary_teacher_actor_id=teacher)
        except ValueError as e:
            why = f"{p['name']} would not take him: {str(e).rstrip('.').lower()}."
            continue
        _log(conn, me, "Training begun", f"He enrols in {p['name']}.")
        return {"status": "applied", "summary": f"He is taken into {p['name']}; it runs about {p['duration_days']} days and he is expected to keep to it.",
                "enrollment_id": eid, "domain": dom, "ready_in_days": int(p["duration_days"])}
    return {"status": "fallback", "summary": why + f" He will have to work at it himself (advance with that purpose practises {dom.replace('_', ' ')}).", "domain": dom}


def _craft(conn, me, intent, f, res, targets, committed, days, call_id) -> dict:
    from . import craft
    from .merchant import authorized_enterprises
    biz = next((i for k, i, _ in targets if k == "business"), None)
    owned = [int(r["id"]) for r in authorized_enterprises(conn, me, minimum_authority=60)]
    pool = [biz] if biz in owned else owned
    qty = float(res.get("quantity") or res.get("units") or 10)
    for e in pool:
        for s in conn.execute("SELECT id FROM production_sites WHERE enterprise_id=? AND active=1 ORDER BY id", (e,)):
            try:
                oid = craft.create_production_order(conn, int(s[0]), qty, due_day=_day(conn) + (days or 30), metadata={"intent": intent[:200]})
            except ValueError as ex:
                last = str(ex)
                continue
            _log(conn, me, "Work ordered", intent[:140])
            return {"status": "applied", "summary": "The work is ordered at his workshop; it will be filled over the coming days as materials and hands allow.", "production_order_id": oid}
    return {"status": "fallback", "summary": "He has no workshop that could make this."}


_PROJECTS = (("road_repair", r"road|bridge|ford|causeway|pave"), ("security_post", r"watch|guard|garrison|fort|wall|tower|post|barracks"),
             ("market_warehouse", r"market|warehouse|granary|storehouse|depot"), ("administrative_office", r"office|court|hall|bureau|registry|customs"))


def _project(conn, me, intent, f, res, targets, committed, days, call_id) -> dict:
    from . import growth
    pk = _first(_PROJECTS, intent.lower(), "")
    if not pk:
        return {"status": "fallback", "summary": "No public works fit that."}
    here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
    loc = next((i for k, i, _ in targets if k == "location"), here)
    polity = next((i for k, i, _ in targets if k == "polity"), None)
    if polity is None:
        row = conn.execute("SELECT controller_polity_id FROM territorial_control WHERE location_id=? LIMIT 1", (loc,)).fetchone()
        polity = int(row[0]) if row and row[0] is not None else None
    if polity is None:
        return {"status": "fallback", "summary": "Nobody governs that ground, so there is no one to build for."}
    if not ledger.can_draw(conn, me, ("polity", polity)):
        return {"status": "fallback", "summary": "He does not rule there, so this is a petition rather than an order."}
    money = _money(f, res)
    cash = float(ledger.amount_of(money, ledger.balance(conn, ("polity", polity)))) if money is not None else 3.0
    try:
        pid = growth.create_public_project(conn, polity, int(loc), pk, intent[:120], required_cash=cash, required_labor_days=float(days or 30) * 3.0,
                                           target_day=_day(conn) + (days or 60))
    except ValueError as e:
        return {"status": "fallback", "summary": f"The works cannot begin: {str(e).rstrip('.').lower()}."}
    _log(conn, me, "Works begun", intent[:140], 2)
    return {"status": "applied", "summary": "The works are begun on the polity's account; they are paid for and manned over time.", "project_id": pid}


def _treat(conn, me, intent, f, res, targets, committed, days, call_id) -> dict:
    from . import health
    patient = _actor_target(targets) or me
    cond = conn.execute("SELECT id FROM health_conditions WHERE actor_id=? AND status IN ('active','recovering','chronic') ORDER BY severity DESC LIMIT 1", (patient,)).fetchone()
    if cond is None:
        return _refuse(f"There is nothing wrong with {po._name(conn, patient)} that the world knows of, so there is nothing to treat.")
    kind = "herbal" if re.search(r"herb|poultice", intent.lower()) else "ordinary_medicine"
    try:
        rid = health.request_care(conn, patient, int(cond[0]), treatment_kind=kind)
    except ValueError as e:
        return {"status": "fallback", "summary": f"Care cannot be arranged: {str(e).rstrip('.').lower()}."}
    _log(conn, me, "Care sought", f"Care is sought for {po._name(conn, patient)}.")
    return {"status": "applied", "summary": f"Care is sought for {po._name(conn, patient)}; a healer will see to it as soon as one can.", "care_request_id": rid}


# ---------------------------------------------------------------- battles and duels: stages the player can steer

_BATTLE_WORDS = (("disengage", r"retreat|withdraw|fall back|flee|disengage|break off"), ("commit_reserve", r"reserve"), ("reinforce", r"reinforc|support|shore up"),
                 ("recover", r"rest|recover|regroup|rally"), ("reposition", r"flank|reposition|maneuv|shift|redeploy"), ("probe", r"probe|scout|test|feel out|skirmish"),
                 ("press", r"press|charge|attack|assault|advance|storm|push|break"), ("hold", r"hold|defend|stand|brace|wait"))
_DUEL_WORDS = (("disengage", r"yield|withdraw|break off|retreat"), ("commit", r"all in|finish|kill|commit"), ("control", r"bind|disarm|control|grapple"),
               ("conserve", r"conserve|pace|rest|wait"), ("defend", r"defend|parry|guard|block"), ("press", r"press|attack|advance|strike"), ("measure", r"measure|probe|feint|test"))


def _band_view(view: dict) -> dict:
    out = {"phase": view.get("phase"), "status": view.get("status"), "sides": []}
    for s in view.get("sides", []):
        out["sides"].append({k: s[k] for k in ("name", "status", "morale", "cohesion", "momentum") if k in s})
    return out


def _battle(conn, me, intent, f, res, targets, committed, days, call_id) -> dict:
    from . import combat
    eid = f.get("battle") or (f.get("details") or {}).get("battle")
    if eid:
        eid = int(eid)
        key = _first(_BATTLE_WORDS, intent.lower(), "hold")
        try:
            combat.submit_battle_intent(conn, eid, me, key, risk_level="high" if re.search(r"all out|reckless|at any cost", intent.lower()) else "balanced",
                                        commitment=0.8 if key in ("press", "commit_reserve") else 0.5, objective=intent[:200])
            rr = combat.resolve_battle_round(conn, eid)
        except ValueError as e:
            return _refuse(str(e))
        view = combat.battle_view(conn, eid, me)
        done = rr.get("status") == "resolved"
        out = {"status": "applied", "battle": eid, "stage": "resolved" if done else "continues", "view": _band_view(view),
               "summary": "The battle is decided." if done else "The round is fought; the battle goes on and he must say what he does next (hold, probe, press, reposition, reinforce, commit the reserve, recover, or break off).",
               "round": rr.get("sides") and [{"side": s.get("name"), "did": s.get("intent"), "morale": s.get("morale_band"), "status": s.get("status")} for s in rr["sides"]]}
        if done:
            out.update(_aftermath(conn, me, eid, rr.get("outcome") or {}))
        return out
    foe = _actor_target(targets)
    outfit = next((i for k, i, _ in targets if k == "outfit"), None)
    if foe is None and outfit is not None:
        row = conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()
        foe = int(row[0]) if row and row[0] is not None else None
    if foe is None:
        raise _Gap("Say who he fights: a target person or outfit.")
    mine, mine_where = _men_available(conn, me)
    men = int(res.get("men") or 0) or sum(c["count"] for c in committed if c["kind"] == "actor" and c["count"] > 1)
    men = min(men or mine, mine)
    theirs = int(conn.execute("SELECT member_count_estimate FROM underworld_organizations WHERE id=?", (outfit,)).fetchone()[0]) if outfit else max(3, men // 2)
    here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
    bid = combat.create_battle(conn, intent[:80], location_id=here, player_actor_id=me, objective=intent[:200], stakes=4)
    for who, n, name in ((me, men, "His force"), (foe, theirs, po._name(conn, foe) + "'s force")):
        sid = combat.add_battle_side(conn, bid, name, controller_actor_id=who, objective=intent[:120])
        left, k = max(1, n), 0
        while left > 0 and k < 6:
            chunk = min(40, left) if k < 5 else left
            cap = min(95.0, 35.0 + 25.0 * (len(str(chunk))))
            combat.add_battle_unit(conn, sid, f"{name} unit {k + 1}", commander_actor_id=who if k == 0 else None,
                                   unit_role="line", combat_capacity=cap, metadata={"men": chunk})
            left -= chunk
            k += 1
    short = "" if men >= int(res.get("men") or men) else " He has fewer men to bring than he wanted."
    _log(conn, me, "Battle joined", intent[:140], 4)
    return {"status": "applied", "battle": bid, "stage": "begins", "summary": "The two forces meet. He must say what he does (hold, probe, press, reposition, reinforce, commit the reserve, recover, or break off)." + short,
            "view": _band_view(combat.battle_view(conn, bid, me))}


def _aftermath(conn, me: int, bid: int, outcome: dict) -> dict:
    """Men lost and the hurt of the commander follow how the field went; the winner is whoever held it."""
    win = outcome.get("winner_side_id")
    mine = conn.execute("SELECT id FROM battle_sides WHERE engagement_id=? AND controller_actor_id=?", (bid, me)).fetchone()
    won = win is not None and mine is not None and int(win) == int(mine[0])
    men = sum(int(json.loads(u["metadata_json"] or "{}").get("men", 0)) for u in conn.execute("SELECT metadata_json FROM battle_units WHERE side_id=?", (mine[0],))) if mine else 0
    lost = int(round(men * (0.08 if won else 0.35)))
    org = po._my_outfit(conn, me)
    if lost and org is not None:
        conn.execute("UPDATE underworld_organizations SET member_count_estimate=MAX(1,member_count_estimate-?) WHERE id=?", (lost, org))
    return {"men_lost": lost, "won": won, "outcome": "He held the field." if won else ("The field was lost." if win is not None else "Both sides broke off.")}


def _duel(conn, me, intent, f, res, targets, committed, days, call_id) -> dict:
    from . import combat
    eid = f.get("duel") or (f.get("details") or {}).get("duel")
    if eid:
        eid = int(eid)
        try:
            combat.submit_duel_intent(conn, eid, me, _first(_DUEL_WORDS, intent.lower(), "press"), objective=intent[:200])
            rr = combat.resolve_duel_exchange(conn, eid)
        except ValueError as e:
            return _refuse(str(e))
        done = rr.get("status") == "resolved"
        return {"status": "applied", "duel": eid, "stage": "resolved" if done else "continues",
                "summary": "The duel is decided." if done else "The exchange is fought; the duel goes on and he must say what he does next.",
                "outcome": rr.get("outcome"), "harm": rr.get("harm_incidents")}
    foe = _actor_target(targets)
    if foe is None or foe == me or not po._living(conn, foe):
        raise _Gap("Say whom he fights: a living target person.")
    if not po._same_place(conn, me, foe):
        return _refuse(f"{po._name(conn, foe)} is not here.")
    here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
    did = combat.create_duel(conn, intent[:80], me, foe, location_id=here, player_actor_id=me, objective=intent[:200], stakes=3)
    _log(conn, me, "Duel begun", intent[:140], 3)
    return {"status": "applied", "duel": did, "stage": "begins", "summary": "They face each other. He must say how he opens (measure, press, defend, conserve, commit, control, or yield)."}
