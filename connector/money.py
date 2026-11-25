"""The money tool: the GM records jobs, debts, shares and wages in the world's currency; the engine moves the money."""
from __future__ import annotations

from connector import store
from engine import ledger, money_records
from engine.money_records import fmt

OPS = ("set_cash", "deal", "owe", "pay", "collateral", "close", "wage", "share", "show")


def _ref(conn, value, field: str, default_kind: str = "person") -> str:
    """"me", an id, "business:3" or a person's exact name -> a holder ref."""
    if value is None or str(value).strip() == "":
        raise ValueError(f"{field} is required (an id, \"me\", business:<id> or a person's name)")
    me = money_records._me(conn)
    text = str(value).strip()
    if isinstance(value, int) or text.isdigit():
        text = f"{default_kind}:{int(text)}"
    if text != "me" and ":" not in text:
        found = [r[0] for r in conn.execute("SELECT id FROM actors WHERE lower(name)=lower(?) AND status='active'", (text,))]
        if len(found) != 1:
            raise ValueError(f"{field}: no one person called '{text}'; give an id or a holder like business:<id>")
        text = f"person:{found[0]}"
    kind, i = ledger.parse_holder(text, me, conn)
    return f"{kind}:{i}"


def _sum(conn, details: dict, field: str, required: bool = True, base: float | None = None) -> float | None:
    v = details.get(field)
    if v is None or v == "":
        if required:
            raise ValueError(f"{field} is required, as a figure")
        return None
    if v == 0:
        return 0.0
    return ledger.amount_of(v, base)


def _due(details: dict, day: int, field: str = "due_in_days") -> int | None:
    if details.get(field) is not None:
        return day + max(0, int(details[field]))
    return None


def _share(value) -> float:
    text = str(value).strip()
    x = float(text.rstrip("%").strip())
    if text.endswith("%") or x > 1:
        x /= 100.0
    if not 0 < x <= 1:
        raise ValueError("share must be above 0 and at most 100%")
    return x


def _deal_out(conn, deal_id: int) -> dict:
    d = money_records.deal_row(conn, deal_id)
    held = [r[0] for r in conn.execute("SELECT what FROM deal_collateral WHERE deal_id=? AND status='held'", (deal_id,))]
    out = {"status": d["status"], "deal_id": deal_id, "customer": money_records.name_of(conn, d["customer_ref"]),
           "provider": money_records.name_of(conn, d["provider_ref"]), "for": d["job"], "quote": fmt(conn, d["quote"]),
           "paid": fmt(conn, money_records.paid_on(conn, deal_id)), "owing": fmt(conn, money_records.owing(conn, d))}
    if held:
        out["holding"] = ", ".join(held)
    return out


def _produce(conn, ref: str, amount: float) -> None:
    """Money the story shows changing hands: someone never counted evidently had it; a counted purse must cover it."""
    counted = ref.startswith("person:") and money_records._has_purse(conn, int(ref.split(":")[1]))
    money_records.ensure_purse(conn, ref, amount)
    have = money_records.cash(conn, ref)
    if have + 0.005 < amount:
        if ref.startswith("person:") and not counted and ref != f"person:{money_records._me(conn)}":
            money_records.set_cash(conn, ref, amount)
            return
        raise ValueError(f"{money_records.name_of(conn, ref)} has only {fmt(conn, have)} on record; set_cash with a reason if that is wrong")


def _run(conn, op: str, d: dict, call_id: str) -> dict:
    day = store._day(conn)
    if op == "set_cash":
        ref = _ref(conn, d.get("holder"), "holder")
        reason = " ".join(str(d.get("reason") or "").split())
        if not reason:
            raise ValueError("set_cash needs a reason: what shows this is what they have")
        before = money_records.cash(conn, ref)
        money_records.set_cash(conn, ref, _sum(conn, d, "amount"))
        who = money_records.name_of(conn, ref)
        money_records.say(conn, day, f"{who} now has {fmt(conn, money_records.cash(conn, ref))} on record: {reason}"[:300], (ref,))
        return {"status": "set", "holder": who, "was": fmt(conn, before), "cash": fmt(conn, money_records.cash(conn, ref))}
    if op in ("deal", "owe"):
        iou = op == "owe"
        customer = _ref(conn, d.get("debtor" if iou else "customer"), "debtor" if iou else "customer")
        provider = _ref(conn, d.get("creditor" if iou else "provider") or ("me" if not iou else None),
                        "creditor" if iou else "provider")
        job = " ".join(str(d.get("what") or d.get("job") or "").split())[:200]
        if not job:
            raise ValueError("say what it is for (job, or what)")
        quote = _sum(conn, d, "amount" if iou else "quote")
        referrer = None
        if d.get("referrer") is not None:
            referrer = int(_ref(conn, d["referrer"], "referrer").split(":")[1])
        status = "quoted" if str(d.get("status") or "").lower() == "quoted" else "open"
        deposit = _sum(conn, d, "deposit", required=False, base=quote) or 0.0
        if deposit > quote + 0.005:
            raise ValueError("the deposit is more than the quote")
        deal_id = money_records.add_deal(
            conn, customer=customer, provider=provider, job=job, quote=quote, parts=_sum(conn, d, "parts", required=False) or 0.0,
            due_day=_due(d, day), referrer=referrer, tags=tuple(d.get("tags") or ()), note=str(d.get("note") or "")[:600],
            status=status, kind="iou" if iou else "job", day=day)
        if d.get("collateral"):
            conn.execute("INSERT INTO deal_collateral(deal_id,what,status,day) VALUES (?,?,'held',?)",
                         (deal_id, str(d["collateral"])[:200], day))
        if deposit:
            _produce(conn, customer, deposit)
            money_records.pay_deal(conn, deal_id, deposit, day, "recorded")
        return _deal_out(conn, deal_id)
    if op == "pay":
        if d.get("deal_id") is not None:
            deal = money_records.deal_row(conn, int(d["deal_id"]))
            amount = _sum(conn, d, "amount", base=money_records.owing(conn, deal))
            amount = min(amount, money_records.owing(conn, deal))
            _produce(conn, deal["customer_ref"], amount)
            money_records.pay_deal(conn, deal["id"], amount, day, "recorded")
            return _deal_out(conn, deal["id"])
        src, dst = _ref(conn, d.get("from") or "me", "from"), _ref(conn, d.get("to"), "to")
        amount = _sum(conn, d, "amount", base=money_records.cash(conn, src))
        what = " ".join(str(d.get("what") or "").split())[:200]
        if not what:
            raise ValueError("say what it is for (what)")
        _produce(conn, src, amount)
        ledger.transfer(conn, ledger.parse_holder(src, 0), ledger.parse_holder(dst, 0), amount, flow_kind="other", purpose=what)
        money_records.say(conn, day, f"{money_records.name_of(conn, src)} paid {money_records.name_of(conn, dst)} "
                                     f"{fmt(conn, amount)} for {what}.", (src, dst))
        return {"status": "paid", "paid": fmt(conn, amount), "cash": fmt(conn, money_records.cash(conn, src))}
    if op == "collateral":
        deal = money_records.deal_row(conn, int(d.get("deal_id") or 0))
        status = str(d.get("status") or "held").lower()
        if status not in money_records.COLLATERAL:
            raise ValueError(f"status must be one of {', '.join(money_records.COLLATERAL)}")
        what = " ".join(str(d.get("what") or "").split())[:200]
        if status == "held":
            if not what:
                raise ValueError("say what is held (what)")
            conn.execute("INSERT INTO deal_collateral(deal_id,what,status,day) VALUES (?,?,'held',?)", (deal["id"], what, day))
        else:
            done = conn.execute("""UPDATE deal_collateral SET status=?,day=? WHERE deal_id=? AND status='held'
                                   AND (?='' OR lower(what) LIKE '%'||lower(?)||'%')""", (status, day, deal["id"], what, what)).rowcount
            if not done:
                raise ValueError("nothing like that is held on this deal")
        return _deal_out(conn, deal["id"])
    if op == "close":
        money_records.close(conn, int(d.get("deal_id") or 0), str(d.get("status") or "").lower(), str(d.get("reason") or "")[:300], day)
        return _deal_out(conn, int(d["deal_id"]))
    if op == "wage":
        worker = _ref(conn, d.get("worker"), "worker")
        business = _ref(conn, d.get("business"), "business", "business")
        if not business.startswith("business:"):
            raise ValueError("business must be business:<id>")
        weekly = _sum(conn, d, "weekly")
        first = _due(d, day, "first_in_days")
        money_records.set_wage(conn, worker, business, weekly, day + 7 if first is None else max(day + 1, first), day)
        return {"status": "agreed" if weekly else "ended", "worker": money_records.name_of(conn, worker),
                "business": money_records.name_of(conn, business), "weekly": fmt(conn, weekly)}
    # share
    to = _ref(conn, d.get("to"), "to")
    source = _ref(conn, d.get("from") or "me", "from")
    applies = str(d.get("applies") or "all").strip().lower()
    if applies not in ("all", "referred") and not applies.startswith("tag:"):
        raise ValueError("applies must be all, referred or tag:<word>")
    conn.execute("UPDATE share_rules SET status='ended' WHERE recipient_ref=? AND source_ref=? AND applies=? AND status='active'",
                 (to, source, applies))
    out = {"to": money_records.name_of(conn, to), "from": money_records.name_of(conn, source), "applies": applies}
    if d.get("share") in (0, "0", "0%"):
        return {"status": "ended", **out}
    basis = str(d.get("basis") or "profit").lower()
    if basis not in ("profit", "gross"):
        raise ValueError("basis must be profit or gross")
    part = _share(d.get("share"))
    conn.execute("""INSERT INTO share_rules(recipient_ref,source_ref,basis,share,applies,note,created_day) VALUES (?,?,?,?,?,?,?)""",
                 (to, source, basis, part, applies, str(d.get("note") or "")[:600], day))
    return {"status": "agreed", **out, "share": f"{part * 100:g}% of {basis}"}


def money(conn, call_id: str, op: str, details: dict | None = None) -> dict:
    if money_records.currency(conn) is None:
        raise ValueError("this world has no currency record; use act pay")
    op = str(op or "").strip().lower()
    if op not in OPS:
        raise ValueError(f"op must be one of {', '.join(OPS)}")
    if op == "show":
        return money_records.full_view(conn)
    d = dict(details or {})
    return store.run_once(conn, call_id, "money", {"op": op, "details": d}, lambda: _run(conn, op, d, call_id))
