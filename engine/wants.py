"""Wants: what a person would like to have, worked out from age, sex, temperament, work, household and circle.

Rules, words and weights come from the world package (data key `wants`), figures from its price book; a package without
them has no wants. `derive` reads only and answers for anyone. The protagonist's wants are kept (`refresh`), because the
player says which matter and which do not; a thing he says he wants is kept in his words, whatever it is."""
from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from . import design, ledger, money_records, price_book
from .world_package import package_for

YEAR = 365.0
_FILES: dict = {}
_PRONOUNS = {"female": ("she", "her", "her"), "male": ("he", "him", "his")}


def data(conn: sqlite3.Connection) -> dict:
    path = package_for(conn).data.get("wants")
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


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _words(text: str) -> str:
    return price_book._words(text)


def _name(conn, a: int) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (int(a),)).fetchone()
    return str(r[0]) if r else "someone"


def authored_work(conn: sqlite3.Connection) -> dict[int, str]:
    """What was said of people's work when they were made, where a record of it is kept."""
    out: dict[int, str] = {}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='connector_calls'").fetchone():
        for request, result in conn.execute("SELECT request_json,result_json FROM connector_calls WHERE tool='author'"):
            who = json.loads(result).get("actor_id")
            if who is not None:
                said = str((json.loads(request).get("details") or {}).get("work") or "")
                out[int(who)] = f"{out.get(int(who), '')} {said}".strip()
    return out


def shared(conn: sqlite3.Connection) -> dict:
    """What is the same for everybody on a day, read once by a caller going through many people."""
    return {"day": _day(conn), "seed": design.run_seed(conn), "book": {i["key"]: i for i in price_book.items(conn)},
            "authored": authored_work(conn), "living": float(design.figure(conn, "money_living_week_usd", 0.0) or 0.0),
            "married": {int(a) for r in conn.execute("SELECT actor_a_id,actor_b_id FROM household_unions WHERE status='active'")
                        for a in r if a is not None}}


class Person:
    """What the rules ask about one person, each read once."""

    def __init__(self, conn: sqlite3.Connection, actor_id: int, all_: dict):
        self.conn, self.id, self.day, self.all = conn, int(actor_id), all_["day"], all_
        self._head: tuple | None = None
        r = conn.execute("""SELECT a.name,a.subtype,p.birth_day,p.demographic_sex,p.life_status FROM actors a
                            LEFT JOIN actor_life_profiles p ON p.actor_id=a.id WHERE a.id=? AND a.actor_type='character'""",
                         (self.id,)).fetchone()
        self.ok = bool(r) and r[2] is not None and str(r[4] or "living") == "living"
        if not self.ok:
            return
        self.name, self.subtype, self.sex = str(r[0]), str(r[1] or ""), str(r[3] or "")
        self.age = int((self.day - int(r[2])) / YEAR)
        d = conn.execute("SELECT * FROM actor_drives WHERE actor_id=?", (self.id,)).fetchone()
        self.drives = {k: float(d[k]) for k in d.keys() if k != "actor_id"} if d else {}
        self.pay = price_book.weekly_pay(conn, self.id)
        self.cash = ledger.balance(conn, ("person", self.id))
        self.living = all_["living"]
        self._work: str | None = None

    # ---- circle ----

    def head_name(self) -> str | None:
        """Whose roof they are under, when it is not their own."""
        if self._head is None:
            r = self.conn.execute("""SELECT h.head_actor_id FROM household_members m JOIN households h ON h.id=m.household_id
                                     WHERE m.actor_id=? AND m.status='active' AND h.head_actor_id IS NOT NULL LIMIT 1""", (self.id,)).fetchone()
            self._head = (_name(self.conn, r[0]) if r and int(r[0]) != self.id else None,)
        return self._head[0]

    def heads_household(self) -> bool:
        return bool(self.conn.execute("""SELECT 1 FROM households h JOIN household_members m ON m.household_id=h.id AND m.actor_id=h.head_actor_id
                                         WHERE h.head_actor_id=? AND m.status='active'""", (self.id,)).fetchone())

    def married(self) -> bool:
        return self.id in self.all["married"]

    def kin(self) -> list[tuple[int, str]]:
        return [(int(r[0]), str(r[1])) for r in self.conn.execute(
            """SELECT k.actor_b_id,k.kin_kind FROM kinship_links k JOIN actor_life_profiles p ON p.actor_id=k.actor_b_id
               WHERE k.actor_a_id=? AND k.ended_day IS NULL AND p.life_status='living' ORDER BY k.actor_b_id""", (self.id,))]

    def young_child(self) -> int | None:
        r = self.conn.execute("""SELECT k.actor_b_id FROM kinship_links k JOIN actor_life_profiles p ON p.actor_id=k.actor_b_id
                                 WHERE k.actor_a_id=? AND k.kin_kind IN ('parent','adoptive_parent','guardian') AND k.ended_day IS NULL
                                 AND p.life_status='living' AND p.birth_day>?
                                 ORDER BY p.birth_day DESC LIMIT 1""", (self.id, self.day - int(14 * YEAR))).fetchone()
        return int(r[0]) if r else None

    def sweetheart(self, serious: bool = False) -> int | None:
        """Someone they are courting: a romance that stands between them, or a partner already married to them."""
        stages = ("serious",) if serious else ("serious", "courting", "interest", "interest_in_him")
        marks = ",".join("?" * len(stages))
        r = self.conn.execute(
            f"""SELECT CASE WHEN m.subject_actor_id=? THEN m.other_actor_id ELSE m.subject_actor_id END o FROM life_matters m
                JOIN actor_life_profiles p ON p.actor_id=CASE WHEN m.subject_actor_id=? THEN m.other_actor_id ELSE m.subject_actor_id END
                WHERE m.kind='romance' AND ? IN (m.subject_actor_id,m.other_actor_id) AND m.stage IN ({marks}) AND p.life_status='living'
                ORDER BY m.stage_day DESC LIMIT 1""", (self.id, self.id, self.id, *stages)).fetchone()
        if r:
            return int(r[0])
        if serious:
            return None
        r = self.conn.execute(
            """SELECT r.actor_b_id FROM relationships r JOIN actor_life_profiles p ON p.actor_id=r.actor_b_id
               WHERE r.actor_a_id=? AND r.affection>=55 AND p.life_status='living' AND p.demographic_sex<>? AND p.birth_day<=?
               AND ABS(p.birth_day-?)<=? AND NOT EXISTS (SELECT 1 FROM kinship_links k WHERE k.actor_a_id=r.actor_a_id
               AND k.actor_b_id=r.actor_b_id AND k.ended_day IS NULL)
               AND NOT EXISTS (SELECT 1 FROM household_unions u WHERE u.status='active' AND r.actor_b_id IN (u.actor_a_id,u.actor_b_id))
               ORDER BY r.affection DESC LIMIT 1""",
            (self.id, self.sex, self.day - int(16 * YEAR), self.day - int(self.age * YEAR), int(12 * YEAR))).fetchone()
        return int(r[0]) if r and self.age >= 16 else None

    def kin_short(self) -> int | None:
        """Close kin who cannot cover a week."""
        for other, relation in self.kin():
            if relation not in ("parent", "child", "sibling", "spouse"):
                continue
            if self.conn.execute("""SELECT 1 FROM life_matters WHERE kind='money' AND status='open' AND subject_actor_id=?""",
                                 (other,)).fetchone():
                return other
            r = self.conn.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type='cash'", (other,)).fetchone()
            age = self.conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (other,)).fetchone()
            if r and self.living and float(r[0]) < self.living and age and (self.day - int(age[0])) >= 18 * YEAR:
                return other
        return None

    # ---- work and goods ----

    def work(self) -> str:
        """Every word on record for what they do."""
        if self._work is not None:
            return self._work
        said = [self.subtype]
        q = self.conn.execute
        said += [str(r[0]) for r in q("SELECT occupation_domain FROM background_person_profiles WHERE actor_id=?", (self.id,))]
        said += [f"{r[0]} {r[1]}" for r in q("""SELECT s.role,e.name FROM enterprise_staff s JOIN civilian_enterprises e ON e.id=s.enterprise_id
                                                WHERE s.actor_id=? AND s.status='active'""", (self.id,))]
        said += [str(r[0]) for r in q("""SELECT e.name FROM agreement_terms t JOIN civilian_enterprises e ON t.debtor_ref='business:'||e.id
                                         WHERE t.ref_kind='wage' AND t.status='active' AND t.creditor_ref=?""", (f"person:{self.id}",))]
        # what was said when they were made, where the record keeps only a broad trade
        said.append(self.all["authored"].get(self.id, ""))
        self._work = _words(" ".join(said).replace("_", " "))
        return self._work

    def owns_business(self) -> bool:
        return bool(self.conn.execute("SELECT 1 FROM civilian_enterprises WHERE owner_actor_id=? AND status IN ('active','strained')",
                                      (self.id,)).fetchone())

    def has(self, lacks: dict) -> bool:
        marks = lacks.get("marks") or []
        if marks and self.conn.execute(f"""SELECT 1 FROM bearing_marks WHERE actor_id=? AND status IN ('active','quiet')
                                           AND kind IN ({','.join('?' * len(marks))})""", (self.id, *marks)).fetchone():
            return True
        words = [_words(w) for w in lacks.get("things") or []]
        for name, kind in self.conn.execute("SELECT name,kind_text FROM held_things WHERE owner_actor_id=? AND status<>'ended'", (self.id,)):
            held = _words(f"{name} {kind}")
            if any(w in held for w in words):
                return True
        return False


def _meets(p: Person, when: dict) -> int | None | bool:
    """False when the rule does not apply; otherwise the other person it is about, or None."""
    other = None
    for key, want in when.items():
        if key == "age":
            if not want[0] <= p.age <= want[1]:
                return False
        elif key == "sex":
            if p.sex != want:
                return False
        elif key == "work":
            said = p.work()
            if not any(_words(w) in said for w in want):
                return False
        elif key == "under_head":
            if bool(p.head_name()) != want:
                return False
        elif key == "head":
            if p.heads_household() != want:
                return False
        elif key == "married":
            if p.married() != want:
                return False
        elif key == "owns_business":
            if p.owns_business() != want:
                return False
        elif key in ("sweetheart", "serious"):
            got = p.sweetheart(serious=key == "serious")
            if (got is not None) != want:
                return False
            other = got if got is not None else other
        elif key == "kin_short":
            got = p.kin_short()
            if (got is not None) != want:
                return False
            other = got if got is not None else other
        elif key == "child":
            got = p.young_child()
            if (got is not None) != want:
                return False
        else:
            raise ValueError(f"wants: unknown condition {key}")
    return other


def _fill(text: str, p: Person, other: int | None) -> str:
    he, him, his = _PRONOUNS.get(p.sex, ("they", "them", "their"))
    out = text.replace("{he}", he).replace("{him}", him).replace("{his}", his).replace("{age}", str(p.age))
    if "{head}" in out:
        out = out.replace("{head}", p.head_name() or "another")
    if "{other}" in out:
        out = out.replace("{other}", _name(p.conn, other) if other is not None else "someone")
    return out


def _choose(p: Person, rule: dict, book: dict) -> dict | None:
    """The first of the rule's items within this person's reach, else the cheapest end of the list."""
    if rule.get("price_weeks"):
        return {"key": None, "price": float(round(p.living * rule["price_weeks"])), "per": None} if p.living else None
    options = [book[k] for k in rule.get("items", []) if k in book]
    if not options:
        return None
    week = p.pay or p.living or 0.0
    for item in options:
        per = item.get("per")
        weekly = item["price"] / {"a month": 4.33, "a year": 52.0}.get(per, 1.0)
        if (per and weekly <= week * 0.4) or (not per and item["price"] <= max(p.cash, week * 14)):
            return item
    return options[-1]


def derive(conn: sqlite3.Connection, actor_id: int, all_: dict | None = None) -> list[dict]:
    """What this person wants as things stand, the most pressing first. Reads only. A caller going through many people
    reads `shared` once and passes it."""
    rules = data(conn)
    if not rules:
        return []
    all_ = all_ or shared(conn)
    p = Person(conn, actor_id, all_)
    if not p.ok:
        return []
    book, seed = all_["book"], all_["seed"]
    had = {r[0]: r[1] for r in conn.execute(
        "SELECT want_key,MAX(updated_day) FROM temptations WHERE actor_id=? AND status='taken' GROUP BY want_key", (p.id,))}
    out = []
    for rule in rules["wants"]:
        if rule["key"] in had and p.day - had[rule["key"]] < rule.get("lasts_days", 365):
            continue
        other = _meets(p, rule.get("when") or {})
        if other is False or (rule.get("lacks") and p.has(rule["lacks"])):
            continue
        item = _choose(p, rule, book)
        if item is None:
            continue
        strength = float(rule.get("strength", 0.5))
        strength += sum(w * (p.drives.get(k, 0.5) - 0.5) for k, w in (rule.get("drives") or {}).items())
        strength += random.Random(f"{seed}:want:{p.id}:{rule['key']}").uniform(-0.08, 0.08)  # no two people weigh alike
        if not item.get("per") and p.cash >= item["price"]:
            strength += 0.05
        out.append({"key": rule["key"], "item": item["key"], "what": _fill(rule["what"], p, other), "reason": _fill(rule["why"], p, other),
                    "price": float(item["price"]), "per": item.get("per"), "strength": round(min(1.5, max(0.05, strength)), 3),
                    "other_actor_id": other})
    return sorted(out, key=lambda w: (-w["strength"], w["key"]))


def refresh(conn: sqlite3.Connection, actor_id: int) -> None:
    """Bring the kept wants into line with what is true now. What the player said of them stands. Does not commit."""
    if not data(conn):
        return
    day = _day(conn)
    kept = {r["key"]: r for r in conn.execute("SELECT * FROM wants WHERE actor_id=? AND source='derived'", (int(actor_id),))}
    lasts = {r["key"]: r.get("lasts_days", 365) for r in data(conn)["wants"]}
    for w in derive(conn, actor_id):
        old = kept.pop(w["key"], None)
        fields = (w["item"], w["what"], w["reason"], w["price"], w["per"], w["strength"], w["other_actor_id"])
        if old is None:
            conn.execute("""INSERT INTO wants(item,what,reason,price,per,strength,other_actor_id,actor_id,key,created_day,updated_day)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (*fields, int(actor_id), w["key"], day, day))
            continue
        if old["status"] == "met" and day - old["updated_day"] < lasts.get(w["key"], 365):
            continue  # they have it: left as it is until that wears off
        status = "open" if old["status"] in ("passed", "met") else old["status"]
        if (*fields, status) != tuple(old[k] for k in ("item", "what", "reason", "price", "per", "strength", "other_actor_id", "status")):
            conn.execute("""UPDATE wants SET item=?,what=?,reason=?,price=?,per=?,strength=?,other_actor_id=?,status=?,updated_day=?
                            WHERE id=?""", (*fields, status, day, old["id"]))
    for old in kept.values():
        if old["status"] in ("open", "matters"):
            conn.execute("UPDATE wants SET status='passed',updated_day=? WHERE id=?", (day, old["id"]))


def standing(conn: sqlite3.Connection, actor_id: int) -> list[dict]:
    """The wants that press: those kept for them (what matters first), or else worked out afresh."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM wants WHERE actor_id=?", (int(actor_id),))]
    if not rows:
        return derive(conn, actor_id)
    live = [r for r in rows if r["status"] in ("open", "matters")]
    return sorted(live, key=lambda r: (r["status"] != "matters", -r["strength"], r["key"]))


def view(conn: sqlite3.Connection, actor_id: int, limit: int = 3) -> list[dict]:
    found = standing(conn, actor_id)[:limit]
    pay = price_book.weekly_pay(conn, actor_id) if found else None
    out = []
    for w in found:
        row = {"id": w.get("id"), "want": w["what"], "why": w["reason"] or None}
        if w["price"]:
            row["price"] = money_records.fmt(conn, w["price"]) + (f" {w['per']}" if w["per"] else "")
            if pay:
                row["weeks_pay"] = round(w["price"] / pay, 1)
        if w.get("status") == "matters":
            row["matters"] = True
        out.append({k: v for k, v in row.items() if v is not None})
    return out


_SAYS = {"matters": "matters", "drop": "dropped", "met": "met"}


def say(conn: sqlite3.Connection, actor_id: int, field: str, want_id: int | None, text: str) -> dict:
    """The player's word on a want: it matters, he drops it, or he has it now. Without an id, a wish in his own words."""
    if not data(conn):
        raise ValueError("this world keeps no wants")
    word = str(field or "").strip().lower()
    if word not in _SAYS:
        raise ValueError(f"kind=want needs field: one of {', '.join(_SAYS)}")
    day = _day(conn)
    refresh(conn, actor_id)
    if want_id is None:
        wish = " ".join(str(text or "").split())[:160]
        if word != "matters" or not wish:
            raise ValueError("give subject_id (the want's id from scene), or field=matters with the wish as text")
        key = "said:" + _words(wish).strip().replace(" ", "-")[:60]
        conn.execute("""INSERT INTO wants(actor_id,key,what,reason,strength,status,source,created_day,updated_day)
                        VALUES (?,?,?,'',0.9,'matters','said',?,?) ON CONFLICT(actor_id,key) DO UPDATE SET status='matters',updated_day=?""",
                     (int(actor_id), key, wish, day, day, day))
        return {"saved": "want", "summary": f"He wants: {wish}"}
    row = conn.execute("SELECT what FROM wants WHERE id=? AND actor_id=?", (int(want_id), int(actor_id))).fetchone()
    if row is None:
        raise ValueError(f"no want {want_id} is his; scene shows the ids")
    conn.execute("UPDATE wants SET status=?,updated_day=? WHERE id=?", (_SAYS[word], day, int(want_id)))
    return {"saved": "want", "summary": f"{row[0]}: {_SAYS[word]}"}
