"""Temptations: the world puts concrete chances before people, tied to what they want.

A chance has a price and a last day. It names a real place, business and person in the save, and comes from someone they
know or from something they pass. There is no beat to it: each want draws its own chances, the more the stronger it is
and the more its owner is about. The protagonist's chances are laid before him and wait for his say. Everyone else takes
theirs on the same rules, looked at coarsely (a slice of people each week, only for what they want badly), and one he
sits on can go to someone else. It runs on the weekly life cadence; the words and rates come from the package's `wants`
data, and without it nothing runs. The engine only puts the chance there: taking it or leaving it is his."""
from __future__ import annotations

import math
import random
import sqlite3

from . import design, findings, ledger, life_matters, money_records, org_lifecycle, price_book, wants

YEAR = 365.0
SEARCH = 40  # how many people near a contested chance are asked whether they want it


def _player(conn: sqlite3.Connection) -> int | None:
    r = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _today(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _name(conn: sqlite3.Connection, actor_id: int) -> str:
    return str(conn.execute("SELECT name FROM actors WHERE id=?", (int(actor_id),)).fetchone()[0])


def _chain(conn: sqlite3.Connection, place: int | None) -> list[int]:
    """A place, then each wider place it stands in."""
    out: list[int] = []
    while place is not None and place not in out:
        out.append(int(place))
        row = conn.execute("SELECT parent_location_id FROM locations WHERE id=?", (place,)).fetchone()
        place = row[0] if row else None
    return out


_FREE = "NOT EXISTS (SELECT 1 FROM inmate_stays s WHERE s.actor_id=a.id AND s.status='inside')"  # behind walls, nothing is passed


def _inside(conn: sqlite3.Connection, actor_id: int) -> bool:
    return bool(conn.execute("SELECT 1 FROM inmate_stays WHERE actor_id=? AND status='inside'", (actor_id,)).fetchone())


_UNDER = "WITH RECURSIVE under(id) AS (SELECT ? UNION SELECT l.id FROM locations l JOIN under u ON l.parent_location_id=u.id) "


def _near_businesses(conn: sqlite3.Connection, who: int, kinds: list[str], names: list[str] | None) -> list[sqlite3.Row]:
    """Open businesses of these kinds (and names) that are not their own: where they are, else the district around, else the city."""
    here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (who,)).fetchone()[0]
    marks = ",".join("?" * len(kinds))
    for place in _chain(conn, here):
        rows = conn.execute(
            _UNDER + f"""SELECT e.id,e.name,e.location_id,l.name place FROM civilian_enterprises e JOIN locations l ON l.id=e.location_id
                WHERE e.status IN ('active','strained') AND e.enterprise_kind IN ({marks}) AND e.name NOT LIKE '[%'
                AND COALESCE(e.owner_actor_id,-1)<>? AND e.location_id IN (SELECT id FROM under) ORDER BY e.id""",
            (place, *kinds, who)).fetchall()
        if names:
            rows = [r for r in rows if any(n.lower() in r["name"].lower() for n in names)]
        if rows:
            return rows
    return []


def _spot(conn: sqlite3.Connection, actor_id: int, broad: bool = False):
    """Where someone is, when it is a particular place: one with other places inside it is too wide to name, unless `broad`."""
    row = conn.execute("""SELECT l.id,l.name,EXISTS(SELECT 1 FROM locations c WHERE c.parent_location_id=l.id) wide
                          FROM actors a JOIN locations l ON l.id=a.current_location_id WHERE a.id=?""", (actor_id,)).fetchone()
    return row if row is not None and (broad or not row["wide"]) else None


def _carriers(conn: sqlite3.Connection, me: int, day: int, other: int | None) -> dict[int, float]:
    """Grown people in his life who might bring him word, the closer the likelier; never the one the want is about."""
    out = {}
    for a, w in life_matters.contacts(conn, me).items():
        r = conn.execute("""SELECT 1 FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                            WHERE a.id=? AND a.actor_type='character' AND p.birth_day<=?""", (a, day - int(16 * YEAR))).fetchone()
        if r and a != other:
            out[a] = w
    return out


def _about(conn: sqlite3.Connection, who: int, day: int) -> tuple[int, int]:
    """How many people are in their life, and how many places they have been seen in these four weeks."""
    places = conn.execute("""SELECT COUNT(DISTINCT e.location_id) FROM events e WHERE e.day>=? AND e.location_id IS NOT NULL
                             AND (e.source_actor_id=? OR e.id IN (SELECT event_id FROM event_targets WHERE actor_id=?))""",
                          (day - 28, who, who)).fetchone()[0]
    return len(life_matters.contacts(conn, who)), 1 + int(places)


def odds(conn: sqlite3.Connection, who: int, want: dict, rule: dict, about: tuple[int, int] | None = None) -> float:
    """The chance that something turns up for this want in a week: how often such things come, how much it is wanted, and
    how much its owner is about (people who might mention it, places where it might be passed)."""
    known, places = about or _about(conn, who, _today(conn))
    reach = known / (known + 8.0) + places / (places + 2.0)
    pull = float(want["strength"]) * (1.5 if want.get("status") == "matters" else 1.0)
    return min(1.0, float(rule.get("comes", 0.0)) * pull * reach)


def _asking(rng: random.Random, item: dict) -> float:
    """A chance is a fair price or better: between the low end and a little over the usual figure."""
    low, high = float(item["low"]), float(item["high"])
    x = rng.uniform(low, min(high, float(item["price"]) * 1.05))
    step = 5 if x >= 100 else 1 if x >= 20 else 0.25
    return round(min(high, max(low, round(x / step) * step)), 2)


def _compose(conn: sqlite3.Connection, me: int, day: int, want: dict, chance: dict, rng: random.Random, item: dict) -> dict | None:
    """One chance made concrete from the save, or None when the save cannot supply who or where it needs."""
    shop = carrier = None
    if chance.get("business"):
        near = _near_businesses(conn, me, chance["business"], chance.get("names"))
        if not near:
            return None
        shop = rng.choice(near)
    if chance["from"] == "contact":
        carrier = life_matters._pick(rng, _carriers(conn, me, day, want.get("other_actor_id")))
        if carrier is None:
            return None
    if shop is not None:
        place_id, place = shop["location_id"], shop["place"]
    else:
        row = _spot(conn, carrier) if carrier is not None else None
        row = row or _spot(conn, me, broad=True)
        if row is None:
            return None
        place_id, place = row[0], row[1]
    price = _asking(rng, item)
    days = rng.randint(*chance["days"])
    said = money_records.fmt(conn, price) + (f" {item['per']}" if item.get("per") else "")
    who = _name(conn, carrier) if carrier is not None else ""
    text = (chance["text"].replace("{carrier}", who).replace("{business}", shop["name"] if shop else "")
            .replace("{place}", place).replace("{price}", said).replace("{days}", str(days)))
    if place not in text:
        text = f"{text} ({place})"
    return {"text": text, "price": price, "per": item.get("per"), "carrier_actor_id": carrier,
            "business_id": shop["id"] if shop else None, "location_id": place_id, "expires_day": day + days}


def _add(conn: sqlite3.Connection, who: int, day: int, key: str, made: dict, status: str = "open", want_id: int | None = None) -> None:
    conn.execute("""INSERT INTO temptations(actor_id,want_id,want_key,text,price,per,carrier_actor_id,business_id,location_id,
                    opened_day,expires_day,status,updated_day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (who, want_id, key, made["text"], made["price"], made["per"], made["carrier_actor_id"], made["business_id"],
                  made["location_id"], day, made["expires_day"], status, day))


def _show(conn: sqlite3.Connection, who: int, rule: dict, price: float | None, day: int) -> None:
    """What having it shows of them, for those who read a person by what they have."""
    gives = rule.get("gives")
    if gives:
        conn.execute("""INSERT INTO bearing_marks(actor_id,kind,text,amount,source,recorded_day) VALUES (?,?,?,?,'derived',?)
                        ON CONFLICT(actor_id,kind,text) DO UPDATE SET status='active',amount=excluded.amount""",
                     (who, gives["kind"], gives["text"], price, day))


def _can_pay(conn: sqlite3.Connection, who: int, price: float, rng: random.Random, living: float) -> bool:
    """Counted money must cover it with a week's living left over. Someone whose money nobody has counted is likelier to
    have it the smaller the sum is beside a few weeks' living."""
    counted = conn.execute("""SELECT 1 FROM resources WHERE actor_id=? AND resource_type='cash' UNION ALL
                              SELECT 1 FROM underworld_leader_wealth WHERE actor_id=?""", (who, who)).fetchone()
    if counted:
        return ledger.balance(conn, ("person", who)) >= price + living
    return not living or rng.random() < 1.0 / (1.0 + (price / (living * 8.0)) ** 2)


def _take(conn: sqlite3.Connection, who: int, day: int, rule: dict, made: dict, living: float) -> None:
    """Someone other than the protagonist takes a chance: the money goes, and they have the thing."""
    money_records.ensure_purse(conn, f"person:{who}", at_least=made["price"] + living * 2)
    purpose = f"{rule['key'].replace('_', ' ')}: {made['text'][:80]}"
    if made["business_id"] is not None:
        ledger.transfer(conn, ("person", who), ("business", made["business_id"]), made["price"], flow_kind="other",
                        purpose=purpose, allow_partial=True)
    else:
        ledger.spend(conn, ("person", who), made["price"], purpose=purpose)
    _add(conn, who, day, rule["key"], {**made, "carrier_actor_id": None, "expires_day": day}, status="taken")
    _show(conn, who, rule, made["price"], day)


def _people_near(conn: sqlite3.Connection, place: int, day: int, but: int) -> list[int]:
    """Living grown people at this place, widening until there are enough of them to ask."""
    found: list[int] = []
    for at in _chain(conn, place):
        found = [int(r[0]) for r in conn.execute(
            _UNDER + f"""SELECT a.id FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                        WHERE a.actor_type='character' AND p.life_status='living' AND p.birth_day BETWEEN ? AND ? AND a.id<>?
                        AND a.current_location_id IN (SELECT id FROM under) AND {_FREE} ORDER BY a.id""",
            (at, day - int(71 * YEAR), day - int(17 * YEAR), but))]
        if len(found) >= SEARCH:
            break
    return found


def _contest(conn: sqlite3.Connection, me: int, day: int, by_key: dict, all_: dict) -> int:
    """What the protagonist is still sitting on may go to someone near it who wants it and can pay."""
    gone = 0
    rows = conn.execute("SELECT * FROM temptations WHERE actor_id=? AND status='open' AND opened_day<? ORDER BY id", (me, day)).fetchall()
    for row in rows:
        rule = by_key.get(row["want_key"])
        rng = random.Random(f"{all_['seed']}:contest:{row['id']}:{day}")
        if rule is None or rng.random() >= float(rule.get("contest", 0.0)):
            continue
        near = _people_near(conn, row["location_id"], day, me)
        for who in rng.sample(near, min(SEARCH, len(near))):
            if not any(w["key"] == rule["key"] for w in wants.derive(conn, who, all_)):
                continue
            if not _can_pay(conn, who, row["price"], rng, all_["living"]):
                continue
            made = {"text": f"{_name(conn, who)} took it: {row['text']}", "price": row["price"], "per": row["per"],
                    "business_id": row["business_id"], "location_id": row["location_id"]}
            _take(conn, who, day, rule, made, all_["living"])
            conn.execute("UPDATE temptations SET status='gone',taker_actor_id=?,updated_day=? WHERE id=?", (who, day, row["id"]))
            gone += 1
            break
    return gone


def _offer(conn: sqlite3.Connection, me: int, day: int, by_key: dict, book: dict) -> int:
    """What turns up for the protagonist this week: each want on its own odds."""
    if _inside(conn, me) or conn.execute("SELECT 1 FROM temptations WHERE actor_id=? AND opened_day=?", (me, day)).fetchone():
        return 0
    about = _about(conn, me, day)
    known, places = about
    opened = 0
    for want in wants.standing(conn, me):
        rule = by_key.get(want["key"])
        item = book.get(want.get("item"))
        if rule is None or item is None or not rule.get("chances"):
            continue
        rng = random.Random(f"{design.run_seed(conn)}:chance:{me}:{want['key']}:{day}")
        if rng.random() >= odds(conn, me, want, rule, about):
            continue
        # the more people he knows the more it comes by word of mouth; the more he gets about, the more he passes it
        ways = {i: (known if c["from"] == "contact" else places * 3.0) + 1.0 for i, c in enumerate(rule["chances"])}
        while ways:
            i = life_matters._pick(rng, ways)
            made = _compose(conn, me, day, want, rule["chances"][i], rng, item)
            if made is None:
                del ways[i]
                continue
            _add(conn, me, day, want["key"], made, want_id=want.get("id"))
            findings.tell(conn, me, [made["text"]], source=made["carrier_actor_id"], confidence=0.9)
            opened += 1
            break
    return opened


def _others(conn: sqlite3.Connection, me: int | None, day: int, rules: dict, by_key: dict, all_: dict) -> int:
    """This week's slice of everyone else: those who want something badly may come upon it and take it."""
    pace = rules.get("others")
    if not pace:
        return 0
    every, least = int(pace["every_weeks"]), float(pace["threshold"])
    slice_ = conn.execute(f"""SELECT a.id FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                             WHERE a.actor_type='character' AND p.life_status='living' AND p.birth_day BETWEEN ? AND ?
                             AND a.id % ?=? AND a.id<>? AND {_FREE}
                             AND NOT EXISTS (SELECT 1 FROM temptations t WHERE t.actor_id=a.id AND t.opened_day=?) ORDER BY a.id""",
                          (day - int(71 * YEAR), day - int(17 * YEAR), every, (day // 7) % every,
                           me if me is not None else -1, day)).fetchall()
    taken, book = 0, all_["book"]
    for (who,) in slice_:
        found = [w for w in wants.derive(conn, who, all_)
                 if w["strength"] >= least and w["item"] in book and by_key[w["key"]].get("chances")]
        if not found:
            continue
        want = found[0]
        rule = by_key[want["key"]]
        rng = random.Random(f"{all_['seed']}:others:{who}:{day}")
        often = float(rule.get("comes", 0.0)) * want["strength"] * float(pace["reach"]) * every
        if rng.random() >= 1.0 - math.exp(-often):
            continue
        price = _asking(rng, book[want["item"]])
        if not _can_pay(conn, who, price, rng, all_["living"]):
            continue
        kinds = [c for c in rule["chances"] if c.get("business")]
        shops = _near_businesses(conn, who, kinds[0]["business"], kinds[0].get("names")) if kinds else []
        shop = rng.choice(shops) if shops else None
        place = shop["location_id"] if shop else conn.execute("SELECT current_location_id FROM actors WHERE id=?", (who,)).fetchone()[0]
        if place is None:
            continue
        made = {"text": f"{_name(conn, who)} took {want['what']}", "price": price, "per": book[want["item"]].get("per"),
                "business_id": shop["id"] if shop else None, "location_id": place}
        _take(conn, who, day, rule, made, all_["living"])
        taken += 1
    return taken


def weekly(conn: sqlite3.Connection, day: int) -> dict:
    """A week of chances: some he sat on go to others, the old ones lapse, new ones turn up, and others take theirs."""
    rules = wants.data(conn)
    if not rules:
        return {}
    me = _player(conn)
    by_key = {r["key"]: r for r in rules["wants"]}
    all_ = {**wants.shared(conn), "day": day}
    out = {}
    if me is not None:
        out["chances_gone"] = _contest(conn, me, day, by_key, all_)
    out["chances_lapsed"] = conn.execute("UPDATE temptations SET status='lapsed',updated_day=? WHERE status='open' AND expires_day<?",
                                         (day, day)).rowcount
    if me is not None:
        wants.refresh(conn, me)
        out["chances_opened"] = _offer(conn, me, day, by_key, all_["book"])
    out["chances_taken_by_others"] = _others(conn, me, day, rules, by_key, all_)
    return {k: v for k, v in out.items() if v}


def open_for(conn: sqlite3.Connection, actor_id: int, after_id: int = 0, limit: int = 3) -> list[dict]:
    """The chances still standing, the soonest to close first."""
    day = _today(conn)
    rows = conn.execute("""SELECT t.*,w.what want FROM temptations t LEFT JOIN wants w ON w.actor_id=t.actor_id AND w.key=t.want_key
                           WHERE t.actor_id=? AND t.status='open' AND t.expires_day>=? AND t.id>? ORDER BY t.expires_day,t.id LIMIT ?""",
                        (int(actor_id), day, int(after_id), limit)).fetchall()
    return [{"id": r["id"], "chance": r["text"], "price": money_records.fmt(conn, r["price"]) + (f" {r['per']}" if r["per"] else ""),
             "days_left": r["expires_day"] - day, "want": r["want"]} for r in rows]


def gone_for(conn: sqlite3.Connection, actor_id: int, since_day: int, limit: int = 3) -> list[dict]:
    """The chances that went to someone else since a day, the latest first: what it was and who has it."""
    rows = conn.execute("""SELECT t.text,a.name FROM temptations t JOIN actors a ON a.id=t.taker_actor_id
                           WHERE t.actor_id=? AND t.status='gone' AND t.updated_day>=? ORDER BY t.updated_day DESC,t.id DESC LIMIT ?""",
                        (int(actor_id), int(since_day), limit)).fetchall()
    return [{"chance": r[0], "taken_by": r[1]} for r in rows]


def last_id(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COALESCE(MAX(id),0) FROM temptations").fetchone()[0])


_SAYS = ("taken", "refused")


def say(conn: sqlite3.Connection, actor_id: int, field: str, chance_id: int | None) -> dict:
    """What he did with a chance. Money that changes hands is recorded separately."""
    word = str(field or "").strip().lower()
    if word not in _SAYS or chance_id is None:
        raise ValueError(f"kind=chance needs subject_id (the chance's id) and field: one of {', '.join(_SAYS)}")
    row = conn.execute("SELECT * FROM temptations WHERE id=? AND actor_id=?", (int(chance_id), int(actor_id))).fetchone()
    day = _today(conn)
    if row is None or row["status"] != "open" or row["expires_day"] < day:
        raise ValueError(f"chance {chance_id} is not open to him")
    conn.execute("UPDATE temptations SET status=?,updated_day=? WHERE id=?", (word, day, int(chance_id)))
    if word == "taken":
        conn.execute("UPDATE wants SET status='met',updated_day=? WHERE actor_id=? AND key=?", (day, int(actor_id), row["want_key"]))
        rule = next((r for r in wants.data(conn).get("wants", []) if r["key"] == row["want_key"]), None)
        if rule:
            _show(conn, int(actor_id), rule, row["price"], day)
    return {"saved": "chance", "summary": f"{word}: {row['text'][:120]}"}


org_lifecycle.on_week(weekly)
