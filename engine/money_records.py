"""Money records for a world that counts in a real currency: jobs with deposits and collateral, IOUs, shares and wages.

Others pay what falls due from what they have, split in proportion when it does not cover everything they owe that day.
The protagonist's own debts are his to pay: the engine only says they are due. A package without a `money` file has no
currency and nothing here ever fires.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3

from . import design, ledger

_CENT = 0.005
OPEN_ENDINGS = ("declined", "written_off", "void")
COLLATERAL = ("held", "returned", "kept")


def currency(conn: sqlite3.Connection) -> str | None:
    """The package's currency mark, or None."""
    from .world_package import package_for, pass_memo
    path = package_for(conn).data.get("money")
    if path is None:
        return None
    return pass_memo(conn, f"money:{path}", lambda: str(json.loads(path.read_text(encoding="utf-8"))["currency"]))


def fmt(conn: sqlite3.Connection, x: float) -> str:
    x = round(float(x), 2)
    return f"{currency(conn) or ''}{x:,.0f}" if x == int(x) else f"{currency(conn) or ''}{x:,.2f}"


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _me(conn) -> int | None:
    r = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    return int(r[0]) if r else None


def _holder(ref: str) -> ledger.Holder:
    kind, _, raw = ref.partition(":")
    return kind, int(raw)


def name_of(conn: sqlite3.Connection, ref: str) -> str:
    kind, i = _holder(ref)
    table = ledger._TABLES[kind]
    if table in ("households", "political_polities", "actors", "civilian_enterprises", "underworld_organizations"):
        r = conn.execute(f"SELECT name FROM {table} WHERE id=?", (i,)).fetchone()
        if r:
            return str(r[0])
    return ref


def cash(conn: sqlite3.Connection, ref: str) -> float:
    return ledger.balance(conn, _holder(ref))


def mine(conn: sqlite3.Connection) -> list[str]:
    """The refs whose money is the protagonist's to hear about: himself and the businesses he owns."""
    me = _me(conn)
    if me is None:
        return []
    return [f"person:{me}"] + [f"business:{r[0]}" for r in conn.execute(
        "SELECT id FROM civilian_enterprises WHERE owner_actor_id=? AND status='active' ORDER BY id", (me,))]


def say(conn: sqlite3.Connection, day: int, text: str, refs: tuple, deal_id: int | None = None) -> None:
    """Money news the protagonist hears, because it is his money or his debt."""
    if not set(refs) & set(mine(conn)):
        return
    from . import findings
    conn.execute("INSERT INTO money_news(day,deal_id,text) VALUES (?,?,?)", (int(day), deal_id, text))
    findings.tell(conn, _me(conn), [text], confidence=1.0)


def last_news(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COALESCE(MAX(id),0) FROM money_news").fetchone()[0])


def news_since(conn: sqlite3.Connection, news_id: int) -> list[str]:
    return [str(r[0]) for r in conn.execute("SELECT text FROM money_news WHERE id>? ORDER BY id", (int(news_id),))]


# ---- purses ----

def _has_purse(conn, actor_id: int) -> bool:
    return bool(conn.execute("""SELECT 1 FROM underworld_leader_wealth WHERE actor_id=?
                                UNION SELECT 1 FROM resources WHERE actor_id=? AND resource_type='cash'""", (actor_id, actor_id)).fetchone())


def ensure_purse(conn: sqlite3.Connection, ref: str, at_least: float = 0.0) -> None:
    """Someone nobody has counted the money of has some on him: a few weeks' living, or the sum he is seen to produce."""
    kind, i = _holder(ref)
    if kind != "person" or i == _me(conn) or _has_purse(conn, i):
        return
    rng = random.Random(f"{design.run_seed(conn)}:purse:{i}")
    weeks = rng.uniform(0.5, float(design.figure(conn, "money_pocket_weeks", 4.0)))
    have = round(max(weeks * float(design.figure(conn, "money_living_week_usd", 0.0)), float(at_least)))
    conn.execute("INSERT INTO resources(actor_id,resource_type,amount) VALUES (?,'cash',?)", (i, have))


def set_cash(conn: sqlite3.Connection, ref: str, amount: float) -> float:
    """The record of what a holder has, corrected. The caller gives and keeps the reason."""
    amount = round(float(amount), 2)
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("amount must not be negative")
    h = _holder(ref)
    ledger._check_exists(conn, h)
    if h[0] == "person" and not _has_purse(conn, h[1]):
        conn.execute("INSERT INTO resources(actor_id,resource_type,amount) VALUES (?,'cash',0)", (h[1],))
    diff = amount - ledger.balance(conn, h)
    if diff > 0:
        ledger._credit(conn, h, diff)
    elif diff < 0:
        ledger._debit(conn, h, -diff)
    return amount


def _earn(conn, ref: str, days: int, day: int) -> None:
    """Someone with no wage the world pays him still earns outside what is modelled, so a short debtor can catch up."""
    kind, i = _holder(ref)
    if kind != "person":
        return
    if conn.execute("""SELECT 1 FROM economic_flows WHERE target_actor_id=? AND flow_kind='wage' AND day>? UNION
                       SELECT 1 FROM agreement_terms WHERE ref_kind='wage' AND status='active' AND creditor_ref=?""",
                    (i, day - 31, ref)).fetchone():
        return
    got = round(float(design.figure(conn, "money_week_surplus_usd", 0.0)) * days / 7.0, 2)
    if got > 0:
        ledger.receive(conn, (kind, i), got, purpose="earnings from the unmodelled world")


# ---- deals and debts ----

def deal_row(conn: sqlite3.Connection, deal_id: int) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM deals WHERE id=?", (int(deal_id),)).fetchone()
    if not r:
        raise ValueError(f"there is no deal {deal_id}")
    return r


def paid_on(conn: sqlite3.Connection, deal_id: int) -> float:
    return float(conn.execute("SELECT COALESCE(SUM(amount_usd),0) FROM deal_payments WHERE deal_id=?", (int(deal_id),)).fetchone()[0])


def owing(conn: sqlite3.Connection, d: sqlite3.Row) -> float:
    return max(0.0, round(float(d["quote"]) - paid_on(conn, d["id"]), 2))


def add_deal(conn: sqlite3.Connection, *, customer: str, provider: str, job: str, quote: float, parts: float = 0.0,
             due_day: int | None = None, referrer: int | None = None, tags: tuple = (), note: str = "", status: str = "open",
             kind: str = "job", day: int | None = None) -> int:
    if customer == provider:
        raise ValueError("the one who pays and the one who is paid must differ")
    quote, parts = round(float(quote), 2), round(float(parts or 0.0), 2)
    if quote <= 0 or parts < 0:
        raise ValueError("the sum must be above zero (parts not below zero)")
    for ref in (customer, provider):
        ledger._check_exists(conn, _holder(ref))
    day = _day(conn) if day is None else int(day)
    return int(conn.execute(
        """INSERT INTO deals(kind,customer_ref,provider_ref,job,quote,parts,due_day,next_try_day,status,referrer_actor_id,tags_json,
                             note,created_day,updated_day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (kind, customer, provider, job, quote, parts, due_day, due_day if status == "open" else None, status, referrer,
         json.dumps([str(t).lower() for t in tags]), note, day, day)).lastrowid)


def pay_deal(conn: sqlite3.Connection, deal_id: int, amount: float, day: int, source: str) -> float:
    """Money moves from the customer to the provider; paid in full closes the deal, returns what was held and pays the shares."""
    d = deal_row(conn, deal_id)
    if d["status"] not in ("open", "quoted"):
        raise ValueError(f"deal {deal_id} is {d['status'].replace('_', ' ')}")
    amount = round(min(float(amount), owing(conn, d)), 2)
    if amount <= 0:
        return 0.0
    ledger.transfer(conn, _holder(d["customer_ref"]), _holder(d["provider_ref"]), amount, flow_kind="other",
                    purpose=f"deal {deal_id}: {d['job']}"[:200])
    conn.execute("INSERT INTO deal_payments(deal_id,day,amount_usd,source) VALUES (?,?,?,?)", (int(deal_id), int(day), amount, source))
    left = owing(conn, d)
    done = left < _CENT
    conn.execute("UPDATE deals SET status=?,next_try_day=CASE WHEN ? THEN NULL ELSE next_try_day END,updated_day=? WHERE id=?",
                 ("paid" if done else "open", done, int(day), int(deal_id)))
    held = [str(r[0]) for r in conn.execute("SELECT what FROM deal_collateral WHERE deal_id=? AND status='held'", (int(deal_id),))]
    if done:
        conn.execute("UPDATE deal_collateral SET status='returned',day=? WHERE deal_id=? AND status='held'", (int(day), int(deal_id)))
    tail = "paid in full" if done else f"still owes {fmt(conn, left)}"
    if done and held:
        tail += f"; {', '.join(held)} handed back"
    say(conn, day, f"{name_of(conn, d['customer_ref'])} paid {fmt(conn, amount)} toward {d['job']}; {tail}.",
        (d["customer_ref"], d["provider_ref"]), int(deal_id))
    if done:
        _pay_shares(conn, d, day)
    return amount


def _pay_shares(conn, d: sqlite3.Row, day: int) -> None:
    if d["kind"] != "job":
        return
    tags = set(json.loads(d["tags_json"] or "[]"))
    for rule in conn.execute("SELECT * FROM share_rules WHERE status='active' AND source_ref=? ORDER BY id", (d["provider_ref"],)).fetchall():
        to, applies = rule["recipient_ref"], rule["applies"]
        if applies == "referred" and to != f"person:{d['referrer_actor_id']}":
            continue
        if applies.startswith("tag:") and applies[4:] not in tags:
            continue
        base = float(d["quote"]) - (float(d["parts"]) if rule["basis"] == "profit" else 0.0)
        due = round(float(rule["share"]) * max(0.0, base), 2)
        if due < _CENT or to == d["provider_ref"]:
            continue
        got = 0.0
        if cash(conn, d["provider_ref"]) > _CENT:
            got = round(ledger.transfer(conn, _holder(d["provider_ref"]), _holder(to), due, flow_kind="share",
                                        purpose=f"share of deal {d['id']}", allow_partial=True), 2)
        conn.execute("INSERT INTO share_payments(rule_id,deal_id,day,amount_usd) VALUES (?,?,?,?)", (rule["id"], d["id"], int(day), got))
        if got:
            say(conn, day, f"{name_of(conn, d['provider_ref'])} paid {name_of(conn, to)} {fmt(conn, got)}, a share of {d['job']}.",
                (d["provider_ref"], to), d["id"])
        if due - got >= _CENT:
            add_deal(conn, customer=d["provider_ref"], provider=to, job=f"share of {d['job']}", quote=due - got, kind="iou",
                     due_day=int(day) + int(design.figure(conn, "money_retry_days", 7)), day=day)
            say(conn, day, f"{name_of(conn, d['provider_ref'])} still owes {name_of(conn, to)} {fmt(conn, due - got)}, a share of "
                           f"{d['job']}.", (d["provider_ref"], to), d["id"])


def close(conn: sqlite3.Connection, deal_id: int, status: str, reason: str, day: int) -> None:
    if status not in OPEN_ENDINGS:
        raise ValueError(f"status must be one of {', '.join(OPEN_ENDINGS)}")
    d = deal_row(conn, deal_id)
    conn.execute("UPDATE deals SET status=?,next_try_day=NULL,note=?,updated_day=? WHERE id=?",
                 (status, " ".join(x for x in (d["note"], reason) if x), int(day), int(deal_id)))


def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    r = conn.execute("SELECT MIN(next_try_day) FROM deals WHERE status='open' AND next_try_day>? AND next_try_day<=?",
                     (int(after_day), int(end_day))).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def process(conn: sqlite3.Connection, day: int) -> int:
    """Everything that has fallen due up to `day`, one due day at a time and one debtor at a time."""
    if currency(conn) is None:
        return 0
    n = 0
    while True:
        r = conn.execute("SELECT MIN(next_try_day) FROM deals WHERE status='open' AND next_try_day<=?", (int(day),)).fetchone()
        if r[0] is None:
            return n
        on = int(r[0])
        by_debtor: dict[str, list] = {}
        for d in conn.execute("SELECT * FROM deals WHERE status='open' AND next_try_day<=? ORDER BY next_try_day,id", (on,)).fetchall():
            by_debtor.setdefault(d["customer_ref"], []).append(d)
        for debtor in sorted(by_debtor):
            _collect(conn, debtor, by_debtor[debtor], on)
            n += len(by_debtor[debtor])


def _collect(conn, debtor: str, debts: list, day: int) -> None:
    """One debtor's due day."""
    retry = int(design.figure(conn, "money_retry_days", 7))
    if debtor == f"person:{_me(conn)}":
        for d in debts:
            conn.execute("UPDATE deals SET next_try_day=NULL WHERE id=?", (d["id"],))
            say(conn, day, f"{name_of(conn, debtor)} owes {name_of(conn, d['provider_ref'])} {fmt(conn, owing(conn, d))} for "
                           f"{d['job']}; it is due.", (debtor,), d["id"])
        return
    kind, i = _holder(debtor)
    if kind == "person":
        from .orgs import is_living
        if not is_living(conn, i):
            for d in debts:
                close(conn, d["id"], "written_off", "the debtor is dead", day)
                say(conn, day, f"{name_of(conn, debtor)} is dead; what was owed for {d['job']} will not be paid.",
                    (d["provider_ref"],), d["id"])
            return
        ensure_purse(conn, debtor)
        if any(d["tries"] for d in debts):
            _earn(conn, debtor, retry, day)
    sums = [(d, owing(conn, d)) for d in debts]
    total, have = sum(o for _, o in sums), cash(conn, debtor)
    spare = total if have + _CENT >= total else max(0.0, have - (float(design.figure(conn, "money_living_week_usd", 0.0))
                                                                 if kind == "person" else 0.0))
    for d, owes in sums:
        pay = owes if spare >= total - _CENT else math.floor(spare * owes / total * 100 + 1e-6) / 100
        conn.execute("UPDATE deals SET next_try_day=?,tries=tries+1 WHERE id=?", (day + retry, d["id"]))
        if pay >= _CENT:
            pay_deal(conn, d["id"], pay, day, "due")
        else:
            say(conn, day, f"{name_of(conn, debtor)} has not paid for {d['job']}; still owes {fmt(conn, owes)}.",
                (debtor, d["provider_ref"]), d["id"])


# ---- wages ----

def term_paid(conn: sqlite3.Connection, debtor: str, creditor: str, paid: float, short: float, purpose: str, day: int) -> None:
    if currency(conn) is None or paid + short < _CENT:
        return
    tail = f"; {fmt(conn, short)} is still owed" if short >= _CENT else ""
    head = f"{name_of(conn, debtor)} paid {name_of(conn, creditor)} {fmt(conn, paid)}" if paid >= _CENT else \
        f"{name_of(conn, debtor)} did not pay {name_of(conn, creditor)}"
    say(conn, day, f"{head} ({purpose}){tail}.", (debtor, creditor))


def set_wage(conn: sqlite3.Connection, worker: str, business: str, weekly: float, first_day: int, day: int) -> int | None:
    """The agreed weekly wage, replacing any before it between the two; zero ends it."""
    from . import agreement_terms, business_data
    for r in conn.execute("""SELECT id FROM agreement_terms WHERE ref_kind='wage' AND status='active' AND debtor_ref=? AND creditor_ref=?""",
                          (business, worker)).fetchall():
        agreement_terms.end_term(conn, r[0], day, "a new wage was agreed")
    if float(weekly) <= 0:
        return None
    return agreement_terms.add_term(
        conn, ref_kind="wage", ref_id=int(business.split(":")[1]), debtor_ref=business, creditor_ref=worker, amount_usd=float(weekly),
        first_due_day=int(first_day), every_days=7, grace_days=int(design.figure(conn, "money_wage_grace_days", 28)),
        breach_word=business_data.default(conn, "breach_word"), purpose="wage", day=day)


def on_agreed_wage(conn: sqlite3.Connection, enterprise_id: int) -> set[int]:
    """Staff this business pays by an agreed weekly wage (the monthly payroll leaves them to it)."""
    try:
        return {int(r[0].split(":")[1]) for r in conn.execute(
            "SELECT creditor_ref FROM agreement_terms WHERE ref_kind='wage' AND status='active' AND debtor_ref=?",
            (f"business:{int(enterprise_id)}",))}
    except sqlite3.OperationalError:
        return set()


# ---- what he sees ----

def _item(conn, d: sqlite3.Row, other: str) -> dict:
    from . import world_calendar
    from .world_package import current_package
    out = {"deal_id": d["id"], "who": name_of(conn, d[other]), "for": d["job"], "owing": fmt(conn, owing(conn, d))}
    if paid_on(conn, d["id"]) >= _CENT:
        out["paid"] = fmt(conn, paid_on(conn, d["id"]))
    if d["due_day"] is not None:
        out["due"] = world_calendar.format_date(current_package(conn), d["due_day"])
    held = [str(r[0]) for r in conn.execute("SELECT what FROM deal_collateral WHERE deal_id=? AND status='held'", (d["id"],))]
    if held:
        out["holding"] = ", ".join(held)
    return out


def view(conn: sqlite3.Connection, limit: int = 8) -> dict | None:
    """The protagonist's money: cash, what is owed to him and what he owes."""
    if currency(conn) is None or _me(conn) is None:
        return None
    refs = mine(conn)
    marks = ",".join("?" for _ in refs)
    out: dict = {"cash": fmt(conn, cash(conn, refs[0]))}

    def take(key: str, side: str, other: str, extra: str) -> None:
        rows = conn.execute(f"SELECT * FROM deals WHERE status='open' AND {side} IN ({marks}) {extra} ORDER BY COALESCE(due_day,1e12),id",
                            refs).fetchall()
        if rows:
            out[key] = [_item(conn, d, other) for d in rows[:limit]]
        if len(rows) > limit:
            out[f"{key}_more"] = len(rows) - limit

    take("owed_to_him", "provider_ref", "customer_ref", "AND kind='job'")
    take("ious_to_him", "provider_ref", "customer_ref", "AND kind='iou'")
    take("he_owes", "customer_ref", "provider_ref", "")
    return out


def full_view(conn: sqlite3.Connection) -> dict:
    out = view(conn, limit=50) or {}
    refs = mine(conn)
    marks = ",".join("?" for _ in refs)
    quoted = conn.execute(f"""SELECT * FROM deals WHERE status IN ('quoted','declined') AND (provider_ref IN ({marks}) OR
                              customer_ref IN ({marks})) ORDER BY id DESC LIMIT 20""", refs + refs).fetchall()
    if quoted:
        out["quotes"] = [{"deal_id": d["id"], "who": name_of(conn, d["customer_ref"]), "for": d["job"], "quote": fmt(conn, d["quote"]),
                          "status": d["status"]} for d in quoted]
    wages = conn.execute(f"""SELECT * FROM agreement_terms WHERE ref_kind='wage' AND status='active' AND (creditor_ref IN ({marks}) OR
                             debtor_ref IN ({marks})) ORDER BY id""", refs + refs).fetchall()
    if wages:
        out["wages"] = [{"worker": name_of(conn, t["creditor_ref"]), "from": name_of(conn, t["debtor_ref"]),
                         "weekly": fmt(conn, t["amount_usd"]), **({"owed": fmt(conn, t["owed_usd"])} if t["owed_usd"] > _CENT else {})}
                        for t in wages]
    shares = conn.execute(f"""SELECT * FROM share_rules WHERE status='active' AND (source_ref IN ({marks}) OR recipient_ref IN ({marks}))
                              ORDER BY id""", refs + refs).fetchall()
    if shares:
        out["shares"] = [{"to": name_of(conn, r["recipient_ref"]), "from": name_of(conn, r["source_ref"]),
                          "share": f"{r['share'] * 100:g}% of {r['basis']}", "applies": r["applies"],
                          **({"note": r["note"]} if r["note"] else {})} for r in shares]
    recent = conn.execute("SELECT day,text FROM money_news ORDER BY id DESC LIMIT 10").fetchall()
    if recent:
        out["recent"] = [{"day": r[0], "text": r[1]} for r in reversed(recent)]
    return out
